"""Empirical nulls with the candidate's exact trade structure (same engine, same costs, same
2xATR14(4h) initial + trailing stop, same 5-NY-trading-day time stop, one position at a time).

N1   random 4h decision bars (Bernoulli p, calibrated so IS n ~ candidate's 499), entry at a
     uniformly random M1 bar inside the next 4h window (market, slippage), random side 50/50.
N1L  same, long only.        N1S  same, short only.
N1q  same, P(long)=0.63 (the candidate's VAL long share; IS share is 0.49).
N3   the candidate's OWN signal times (every OCO first-touch, all 2646 signals): market entry
     at the bar after the touch, side = coin flip.  C3 = same mechanism, true side (control).
     F3 = same mechanism, always the opposite side (fade).
For each seed: IS report (+ costs x1.5 IS report) -> goldlab.evalkit.is_criteria;
VAL report -> val_criteria.  VAL rows of each family are obtained with ONE logged gl.cut.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa

SEEDS = int(os.environ.get("SEEDS", 400))
m1 = gl.load_m1("xauusd")
g = h4_grid(m1)
cand = pd.read_parquet(os.path.join(HERE, "cand_orders.parquet"))
stress = stressed_costs("xauusd")


def sim_pair(o):
    return gl.simulate(m1, o, no_overlap=True), gl.simulate(m1, o, costs=stress, no_overlap=True)


# ---------------------------------------------------------------- calibrate p_place (IS only)
def is_n(p, seeds=8):
    ns = []
    for s in range(seeds):
        o = random_orders(g, np.random.default_rng(900 + s), p)
        ns.append(len(gl.cut(gl.simulate(m1, o, no_overlap=True), "is")))
    return float(np.median(ns))


cal = {}
for p in (0.045, 0.05, 0.055, 0.06, 0.065):
    cal[p] = is_n(p)
    print("calib p", p, "IS n median", cal[p], flush=True)
P = min(cal, key=lambda p: abs(cal[p] - 499))
print("chosen p_place", P, flush=True)


def fam_random(p_long):
    def f(rng):
        return random_orders(g, rng, P, p_long=p_long)
    return f


def fam_sig(mode):
    base = cand.copy()
    ent = base["trig_i"].to_numpy() + 1
    keep = (ent < base["exit_i"].to_numpy()) & (ent < len(m1))
    base = base[keep].reset_index(drop=True)
    ent = ent[keep]

    def f(rng):
        s = base["side"].to_numpy()
        if mode == "random":
            s = np.where(rng.random(len(s)) < 0.5, 1, -1)
        elif mode == "fade":
            s = -s
        return pd.DataFrame({"entry_i": ent, "side": s, "etype": 0, "stop_dist": 2.0 * base["atr"].to_numpy(),
                             "trail": 2.0 * base["atr"].to_numpy(), "exit_i": base["exit_i"].to_numpy()})
    return f


FAMS = {"N1": (fam_random(0.5), SEEDS), "N1L": (fam_random(1.0), SEEDS // 2), "N1S": (fam_random(0.0), SEEDS // 2),
        "N1q": (fam_random(0.63), SEEDS // 2), "N3": (fam_sig("random"), SEEDS),
        "C3": (fam_sig("true"), 1), "F3": (fam_sig("fade"), 1)}

out = {"p_place": P, "calibration": cal, "families": {}}
for name, (fn, ns) in FAMS.items():
    t0 = time.time()
    rows, val_parts = [], []
    for s in range(ns):
        rng = np.random.default_rng(10_000 * (1 + list(FAMS).index(name)) + s)
        o = fn(rng)
        t, ts = sim_pair(o)
        ri, rsi = rep_pair(t, ts)
        crit = is_criteria(ri, rsi)
        ti = gl.cut(t, "is")
        rows.append({"seed": s, "is_n": ri["n"], "is_pf": ri["pf"], "is_t": ri["t_stat"], "is_exp": ri["expectancy_R"],
                     "is_years": ri["years_pos"], "is_stress_pf": rsi["pf"], "is_pass": bool(crit["pass"]),
                     "is_pass_core": bool(crit["pf>=1.20"] and crit["t>=2"]),
                     "is_long_pf": pf(ti.R[ti.side > 0]), "is_short_pf": pf(ti.R[ti.side < 0]),
                     "is_long_share": float((ti.side > 0).mean())})
        tt = t[t.entry_time >= VA_A - pd.Timedelta(days=10)].copy()   # pre-filter only to save memory;
        tt["seed"] = s                                                 # the VAL cut itself is gl.cut below
        val_parts.append(tt)
    allv = pd.concat(val_parts, ignore_index=True)
    tv = gl.cut(allv, "val", track="review", label=label(f"null-{name}({ns} seeds, VAL reports)"))
    df = pd.DataFrame(rows).set_index("seed")
    for s, grp in tv.groupby("seed"):
        rv = gl.report(grp)
        vc = val_criteria(rv)
        df.loc[s, ["val_n", "val_pf", "val_t", "val_exp", "val_pass", "val_long_pf", "val_short_pf", "val_long_share"]] = [
            rv["n"], rv["pf"], rv["t_stat"], rv["expectancy_R"], bool(vc["pass"]),
            pf(grp.R[grp.side > 0]), pf(grp.R[grp.side < 0]), float((grp.side > 0).mean())]
    df["val_pass"] = df["val_pass"].astype(bool)
    df.to_csv(os.path.join(HERE, f"s02_{name}.csv"))
    q = lambda c, p: round(float(np.nanpercentile(df[c].astype(float), p)), 3)
    summ = {"seeds": ns,
            "is_n_med": float(df.is_n.median()), "val_n_med": float(df.val_n.median()),
            "is_pf_p5_50_95_max": [q("is_pf", 5), q("is_pf", 50), q("is_pf", 95), round(float(df.is_pf.max()), 3)],
            "is_t_p5_50_95_max": [q("is_t", 5), q("is_t", 50), q("is_t", 95), round(float(df.is_t.max()), 2)],
            "is_t_mean_sd": [round(float(df.is_t.mean()), 3), round(float(df.is_t.std()), 3)],
            "is_exp_mean": round(float(df.is_exp.mean()), 4),
            "val_pf_p5_50_95_max": [q("val_pf", 5), q("val_pf", 50), q("val_pf", 95), round(float(df.val_pf.max()), 3)],
            "val_t_mean_sd": [round(float(df.val_t.mean()), 3), round(float(df.val_t.std()), 3)],
            "val_exp_mean": round(float(df.val_exp.mean()), 4),
            "frac_is_pass": round(float(df.is_pass.mean()), 4), "frac_is_core": round(float(df.is_pass_core.mean()), 4),
            "frac_val_pass": round(float(df.val_pass.mean()), 4),
            "frac_both": round(float((df.is_pass & df.val_pass).mean()), 4),
            "frac_is_pf_ge_1.35": round(float((df.is_pf >= 1.35).mean()), 4),
            "frac_val_pf_ge_1.294": round(float((df.val_pf >= 1.294).mean()), 4),
            "is_long_pf_med": q("is_long_pf", 50), "is_short_pf_med": q("is_short_pf", 50),
            "val_long_pf_med": q("val_long_pf", 50), "val_short_pf_med": q("val_short_pf", 50),
            "secs": round(time.time() - t0, 1)}
    if ns == 1:
        summ["row"] = df.iloc[0].to_dict()
    out["families"][name] = summ
    print(name, json.dumps(summ, default=str), flush=True)
    json.dump(out, open(os.path.join(HERE, "s02_nulls_random.json"), "w"), indent=1, default=str)
