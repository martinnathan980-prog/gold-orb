"""Regime-preserving permutation nulls at the candidate's own signal times.

N3pq / N3pm: the realized breakout sides of all OCO signals are shuffled WITHIN each calendar
quarter / month (keeps the slow long/short tilt = 'beta to the regime', destroys the
day-level direction information).  Same mechanism as N3/C3 (market entry at the bar after the
first touch, true C3 = IS PF 1.25 / VAL PF 1.246).  One logged VAL cut per family."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa

m1 = gl.load_m1("xauusd")
cand = pd.read_parquet(os.path.join(HERE, "cand_orders.parquet"))
ent = cand["trig_i"].to_numpy() + 1
kk = (ent < cand["exit_i"].to_numpy()) & (ent < len(m1))
c3 = cand[kk].reset_index(drop=True)
ent = ent[kk]
when = m1.index[np.clip(ent, 0, len(m1) - 1)].tz_convert(None)
NS = int(os.environ.get("SEEDS", 300))
stress = stressed_costs("xauusd")
out = {}
for fam, freq in (("N3pq", "Q"), ("N3pm", "M")):
    grp = pd.PeriodIndex(when, freq=freq).asi8
    order = np.argsort(grp, kind="stable")
    bounds = np.flatnonzero(np.diff(grp[order])) + 1
    segs = np.split(order, bounds)
    rows, parts = [], []
    for s in range(NS):
        rng = np.random.default_rng(66_000 + (0 if freq == "Q" else 5000) + s)
        side = c3.side.to_numpy().copy()
        for sg in segs:
            side[sg] = side[rng.permutation(sg)]
        o = pd.DataFrame({"entry_i": ent, "side": side, "etype": 0, "stop_dist": 2 * c3.atr.to_numpy(),
                          "trail": 2 * c3.atr.to_numpy(), "exit_i": c3.exit_i.to_numpy()})
        t = gl.simulate(m1, o, no_overlap=True)
        ts = gl.simulate(m1, o, costs=stress, no_overlap=True)
        ri, rsi = rep_pair(t, ts)
        crit = is_criteria(ri, rsi)
        rows.append({"seed": s, "is_n": ri["n"], "is_pf": ri["pf"], "is_t": ri["t_stat"], "is_pass": bool(crit["pass"])})
        x = t[t.entry_time >= VA_A - pd.Timedelta(days=10)].copy()
        x["seed"] = s
        parts.append(x)
    tv = gl.cut(pd.concat(parts, ignore_index=True), "val", track="review",
                label=label(f"null-{fam}({NS} seeds, side permuted within {freq})"))
    df = pd.DataFrame(rows).set_index("seed")
    for s, g in tv.groupby("seed"):
        rv = gl.report(g)
        df.loc[s, ["val_n", "val_pf", "val_t", "val_pass", "val_long_share"]] = [rv["n"], rv["pf"], rv["t_stat"],
                                                                                 bool(val_criteria(rv)["pass"]),
                                                                                 float((g.side > 0).mean())]
    df["val_pass"] = df["val_pass"].astype(bool)
    df.to_csv(os.path.join(HERE, f"s02b_{fam}.csv"))
    q = lambda c: [round(float(np.percentile(df[c].astype(float), p)), 3) for p in (5, 50, 95)] + [round(float(df[c].max()), 3)]
    out[fam] = {"seeds": NS, "is_pf_q5_50_95_max": q("is_pf"), "is_t_q5_50_95_max": q("is_t"),
                "val_pf_q5_50_95_max": q("val_pf"), "val_t_q5_50_95_max": q("val_t"),
                "frac_is_pass": round(float(df.is_pass.mean()), 4), "frac_val_pass": round(float(df.val_pass.mean()), 4),
                "frac_is_pf_ge_1.25(C3)": round(float((df.is_pf >= 1.25).mean()), 4),
                "frac_val_pf_ge_1.246(C3)": round(float((df.val_pf >= 1.246).mean()), 4),
                "val_long_share_med": round(float(df.val_long_share.median()), 3)}
    print(fam, json.dumps(out[fam]), flush=True)
json.dump(out, open(os.path.join(HERE, "s02b_perm.json"), "w"), indent=1)
