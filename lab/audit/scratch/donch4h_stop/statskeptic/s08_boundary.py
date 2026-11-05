"""Boundary null (true expectancy exactly 0 after costs, candidate's own R shape and calendar):
recentre the candidate's IS / VAL R to mean 0 and resample (iid and week clusters).
-> per-trial false-positive rates for the IS criteria and the VAL criteria, then
P(at least one of N_eff trials passes by luck) under the different nulls measured in s02/s02b/s03.
No new VAL access: VAL trades come from s01's logged cut."""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa

rng = np.random.default_rng(99)
ti = pd.read_parquet(os.path.join(HERE, "cand_trades_is.parquet"))
tv = pd.read_parquet(os.path.join(HERE, "cand_trades_val.parquet"))
TI, TSI = ti[ti.variant == "normal"], ti[ti.variant == "stress"]
TV = tv[tv.variant == "normal"]
d_stress = TI.R.mean() - TSI.R.mean()          # stress costs take ~0.03 R / trade
B = 20000


def is_pass_sample(R, yrs):
    n = len(R)
    if n < 200:
        return False, False
    t_ = R.mean() / (R.std(ddof=1) / math.sqrt(n))
    p_ = pf(R)
    ys = pd.Series(R).groupby(yrs).sum()
    yp = (ys > 0).sum() >= 2 * len(ys) / 3
    ps = pf(R - d_stress)
    core = (p_ >= 1.2) and (t_ >= 2)
    return core and yp and ps >= 1.05, core


res = {}
for mode in ("iid", "week"):
    R0 = TI.R.to_numpy() - TI.R.mean()
    yrs0 = TI.entry_time.dt.year.to_numpy()
    wk = TI.entry_time.dt.tz_convert(None).dt.to_period("W").to_numpy()
    groups = pd.Series(np.arange(len(R0))).groupby(wk).apply(lambda s: s.to_numpy()).tolist()
    full, core = 0, 0
    for _ in range(B):
        if mode == "iid":
            ix = rng.integers(0, len(R0), len(R0))
        else:
            ix = np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))])
        f_, c_ = is_pass_sample(R0[ix], yrs0[ix])
        full += f_
        core += c_
    V0 = TV.R.to_numpy() - TV.R.mean()
    vw = TV.entry_time.dt.tz_convert(None).dt.to_period("W").to_numpy()
    vg = pd.Series(np.arange(len(V0))).groupby(vw).apply(lambda s: s.to_numpy()).tolist()
    vp = 0
    vge = 0
    for _ in range(B):
        if mode == "iid":
            ix = rng.integers(0, len(V0), len(V0))
        else:
            ix = np.concatenate([vg[i] for i in rng.integers(0, len(vg), len(vg))])
        s = V0[ix]
        vp += (pf(s) >= 1.10) and (s.mean() > 0)
        vge += pf(s) >= 1.294
    res[mode] = {"alpha_IS_full": full / B, "alpha_IS_core(pf>=1.2&t>=2)": core / B,
                 "alpha_VAL_pass": vp / B, "P_VAL_pf>=1.294": vge / B}
    print(mode, res[mode], flush=True)

# collect per-trial alphas measured under the other nulls
alph = {}
for f, nm in (("s02_N1.csv", "N1 random time+side"), ("s02_N3.csv", "N3 signal times, random side"),
              ("s02_N1q.csv", "N1q random time, 63% long"), ("s02_N1L.csv", "N1L random time, long only"),
              ("s02b_N3pq.csv", "N3pq signal times, sides permuted within quarter (oracle tilt)"),
              ("s02b_N3pm.csv", "N3pm signal times, sides permuted within month (oracle tilt)"),
              ("s03_N4_day.csv", "N4 exact rule on day-mirrored gold"),
              ("s03_N4_dayd.csv", "N4d exact rule on day-mirrored gold, yearly drift kept")):
    p = os.path.join(HERE, f)
    if not os.path.exists(p):
        continue
    d = pd.read_csv(p)
    n = len(d)
    a_is = d.is_pass.mean()
    # normal-tail extrapolation for P(t>=2) when no seed passes
    from scipy import stats
    a_is_fit = float(stats.norm.sf(2.0, d.is_t.mean(), d.is_t.std()))
    alph[nm] = {"seeds": n, "alpha_IS_obs": round(float(a_is), 4), "alpha_IS_upper95": round(float(3.0 / n if a_is == 0 else a_is), 4),
                "P_t>=2_normal_fit": round(a_is_fit, 5), "alpha_VAL_obs": round(float(d.val_pass.mean()), 4),
                "alpha_both_obs": round(float((d.is_pass & d.val_pass).mean()), 4)}
alph["boundary (mean 0, candidate R shape), week-cluster"] = {
    "alpha_IS_obs": round(res["week"]["alpha_IS_full"], 4), "alpha_VAL_obs": round(res["week"]["alpha_VAL_pass"], 4)}
fw = {}
for nm, a in alph.items():
    ai = a["alpha_IS_obs"] if a["alpha_IS_obs"] > 0 else a.get("P_t>=2_normal_fit", 0)
    av = a["alpha_VAL_obs"]
    row = {}
    for N in (10, 21, 50, 130, 300):
        row[N] = [round(1 - (1 - ai) ** N, 3), round(1 - (1 - ai * av) ** N, 3)]
    fw[nm] = row
out = {"boundary": res, "per_trial_alpha": alph, "P_at_least_one_[IS_pass, IS+VAL_pass]_by_N_eff": fw,
       "stress_shift_R": round(float(d_stress), 4)}
json.dump(out, open(os.path.join(HERE, "s08_boundary.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
