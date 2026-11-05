"""Path-dependence of the one-position chain and execution latency.

(a) DROPOUT: a manual trader misses a random fraction q of the alerts.  Drop each OCO signal
    with prob q, re-simulate (no_overlap) -> distribution of IS / VAL PF.  Shows how much of
    the VAL pass depends on WHICH signals the one-position rule happens to take.
(b) DELAY: true side, market entry d minutes after the first touch (alert -> manual order).
One logged gl.cut per experiment for the VAL rows.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa

m1 = gl.load_m1("xauusd")
cand = pd.read_parquet(os.path.join(HERE, "cand_orders.parquet"))
NS = int(os.environ.get("SEEDS", 300))
out = {"dropout": {}, "delay": {}}
for q in (0.05, 0.10, 0.20, 0.33, 0.50):
    rows, parts = [], []
    for s in range(NS):
        rng = np.random.default_rng(31_000 + int(q * 1000) * 1000 + s)
        o = cand[rng.random(len(cand)) >= q]
        t = gl.simulate(m1, o, no_overlap=True)
        ti = gl.cut(t, "is")
        rows.append({"seed": s, "is_n": len(ti), "is_pf": pf(ti.R), "is_exp": float(ti.R.mean()), "is_t": tstat(ti.R)})
        x = t[t.entry_time >= VA_A - pd.Timedelta(days=10)].copy()
        x["seed"] = s
        parts.append(x)
    tv = gl.cut(pd.concat(parts, ignore_index=True), "val", track="review",
                label=label(f"dropout-q{q}({NS} seeds)"))
    df = pd.DataFrame(rows).set_index("seed")
    for s, g in tv.groupby("seed"):
        df.loc[s, ["val_n", "val_pf", "val_exp", "val_t"]] = [len(g), pf(g.R), float(g.R.mean()), tstat(g.R)]
    df.to_csv(os.path.join(HERE, f"s05_dropout_q{q}.csv"))
    qq = lambda c: [round(float(np.nanpercentile(df[c], p)), 3) for p in (5, 25, 50, 75, 95)]
    out["dropout"][q] = {"is_pf_q5_25_50_75_95": qq("is_pf"), "val_pf_q5_25_50_75_95": qq("val_pf"),
                         "is_t_q5_25_50_75_95": qq("is_t"), "val_t_q5_25_50_75_95": qq("val_t"),
                         "frac_is_pf_ge_1.2_and_t_ge_2": round(float(((df.is_pf >= 1.2) & (df.is_t >= 2)).mean()), 3),
                         "frac_val_pf_ge_1.1": round(float((df.val_pf >= 1.1).mean()), 3),
                         "frac_val_pf_le_1.0": round(float((df.val_pf <= 1.0).mean()), 3),
                         "frac_val_ge_actual_1.294": round(float((df.val_pf >= 1.294).mean()), 3),
                         "is_n_med": float(df.is_n.median()), "val_n_med": float(df.val_n.median())}
    print("dropout", q, out["dropout"][q], flush=True)

# delay: market entry d minutes after the touch bar (true side)
parts, rows = [], []
for d in (0, 1, 2, 5, 15, 60):
    if d == 0:
        o = cand
    else:
        ent = cand["trig_i"].to_numpy() + d
        keep = (ent < cand["exit_i"].to_numpy()) & (ent < len(m1))
        c = cand[keep]
        o = pd.DataFrame({"entry_i": ent[keep], "side": c["side"].to_numpy(), "etype": 0,
                          "stop_dist": c["stop_dist"].to_numpy(), "trail": c["trail"].to_numpy(),
                          "exit_i": c["exit_i"].to_numpy()})
    t = gl.simulate(m1, o, no_overlap=True)
    ts = gl.simulate(m1, o, costs=stressed_costs("xauusd"), no_overlap=True)
    ri, rsi = rep_pair(t, ts)
    crit = is_criteria(ri, rsi)
    out["delay"][d] = {"is_n": ri["n"], "is_pf": ri["pf"], "is_t": ri["t_stat"], "is_exp": ri["expectancy_R"],
                       "is_stress_pf": rsi["pf"], "is_pass": bool(crit["pass"]), "failed": [k for k, v in crit.items() if v is False]}
    x = t[t.entry_time >= VA_A - pd.Timedelta(days=10)].copy()
    x["delay"] = d
    parts.append(x)
tv = gl.cut(pd.concat(parts, ignore_index=True), "val", track="review", label=label("entry-delay-sweep(0,1,2,5,15,60 min)"))
for d, g in tv.groupby("delay"):
    rv = gl.report(g)
    out["delay"][int(d)].update({"val_n": rv["n"], "val_pf": rv["pf"], "val_t": rv["t_stat"],
                                 "val_exp": rv["expectancy_R"], "val_pass": bool(val_criteria(rv)["pass"])})
for d, v in out["delay"].items():
    print("delay", d, v, flush=True)
json.dump(out, open(os.path.join(HERE, "s05_dropout_delay.json"), "w"), indent=1, default=str)
