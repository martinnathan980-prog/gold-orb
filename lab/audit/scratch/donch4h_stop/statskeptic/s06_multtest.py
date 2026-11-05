"""Selection / multiple testing inside the trend track (IS only, no VAL access).

Re-runs the 48 configurations logged BEFORE the finalist decision (patched data; IS cut),
builds their weekly R series (calendar weeks of IS, empty = 0), then:
  * effective number of independent tests from the eigenvalues of the correlation matrix
    (Nyholt 2004, Li & Ji 2005, Galwey 2009)
  * max-t under a global zero-edge null: MVN with the empirical correlation
  * White's Reality Check and Hansen's SPA (stationary block bootstrap of weeks, mean block
    4 weeks), statistic = t of mean weekly R
  * deflated Sharpe ratio recomputed under alternative variance assumptions
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa
from scipy import stats

m1 = gl.load_m1("xauusd")
cfgs = []
for i, line in enumerate(open(os.path.join(LAB, "results", "trend", "trials.jsonl"))):
    if i >= 48:
        break
    c = json.loads(line)["config"]
    c = {k: v for k, v in c.items() if not k.startswith("_") and k != "no_overlap"}
    for k, v in list(c.items()):
        if v is None:
            c[k] = float("nan")
    cfgs.append(c)
weeks = pd.period_range("2013-01-01", "2021-12-31", freq="W")
W = np.zeros((len(weeks), len(cfgs)))
info = []
t0 = time.time()
for j, c in enumerate(cfgs):
    S._bar_cache.clear()
    o = S.make_orders(m1, **c)
    t = gl.cut(gl.simulate(m1, o, no_overlap=True), "is")
    wk = t.groupby(t.exit_time.dt.tz_convert(None).dt.to_period("W")).R.sum()
    W[:, j] = wk.reindex(weeks, fill_value=0.0).to_numpy()
    R = t.R.to_numpy()
    info.append({"j": j, "cfg": {k: v for k, v in c.items() if k in ("family", "tf", "n", "entry", "stop_atr", "trail_atr",
                                                                     "target_r", "max_days", "sess", "trend_ma", "anchor",
                                                                     "k", "lookback", "vol", "hold_days", "nr", "atr_n")},
                 "n": len(R), "pf": round(pf(R), 3), "t": round(tstat(R), 2), "exp": round(float(R.mean()), 4),
                 "sr_trade": float(R.mean() / R.std(ddof=1))})
    print(j, info[-1]["n"], info[-1]["pf"], info[-1]["t"], round(time.time() - t0, 1), flush=True)
np.save(os.path.join(HERE, "s06_weekly_R.npy"), W)
json.dump(info, open(os.path.join(HERE, "s06_trial_info.json"), "w"), indent=1, default=str)

cand_j = 37
C = np.corrcoef(W.T)
ev = np.linalg.eigvalsh(C)[::-1]
M = len(cfgs)
nyholt = 1 + (M - 1) * (1 - np.var(ev, ddof=1) / M)
liji = float(np.sum((ev >= 1).astype(float) + (np.abs(ev) - np.floor(np.abs(ev)))))
galwey = float(np.sum(np.sqrt(np.clip(ev, 0, None))) ** 2 / np.sum(np.clip(ev, 0, None)))
res = {"M": M, "N_eff_nyholt": round(float(nyholt), 1), "N_eff_liji": round(liji, 1), "N_eff_galwey": round(galwey, 1),
       "top_eigen_share": [round(float(x / M), 3) for x in ev[:5]],
       "corr_with_candidate": {"median": round(float(np.median(np.delete(C[cand_j], cand_j))), 3),
                               "q90": round(float(np.percentile(np.delete(C[cand_j], cand_j), 90)), 3)}}
# MVN max-t under global zero-edge null (statistic = per-trade t ~ N(0,1), corr ~ weekly corr)
rng = np.random.default_rng(7)
L = np.linalg.cholesky(C + 1e-9 * np.eye(M))
Z = rng.standard_normal((200_000, M)) @ L.T
mx = Z.max(axis=1)
res["mvn_global_null"] = {"P_max_t>=2.0": round(float((mx >= 2.0).mean()), 4),
                          "P_max_t>=2.35": round(float((mx >= 2.35).mean()), 4),
                          "max_t_q50_90_95": [round(float(np.percentile(mx, p)), 2) for p in (50, 90, 95)]}
# same with only the 'plausible' configs (observed t > -1): poor configs rarely produce false winners
ok = np.array([x["t"] > -1.0 for x in info])
Z2 = Z[:, ok]
mx2 = Z2.max(axis=1)
res["mvn_null_plausible_only"] = {"n_cfg": int(ok.sum()), "P_max_t>=2.0": round(float((mx2 >= 2.0).mean()), 4),
                                  "P_max_t>=2.35": round(float((mx2 >= 2.35).mean()), 4)}


# Reality check / SPA on weekly series
def stat_t(X):
    mu = X.mean(0)
    sd = X.std(0, ddof=1)
    return mu / (sd / math.sqrt(len(X)))


T = len(weeks)
obs = stat_t(W)
mu = W.mean(0)
sd = W.std(0, ddof=1)
res["obs_week_t_candidate"] = round(float(obs[cand_j]), 2)
res["obs_week_t_max"] = round(float(obs.max()), 2)
res["obs_week_t_argmax"] = int(np.argmax(obs))
thr = -math.sqrt(2 * math.log(math.log(T)))
center_rc = mu
center_spa = np.where(obs >= thr, mu, 0.0)   # SPA_c: keep poor configs at their (negative) mean
Bn = 4000
mx_rc, mx_spa = np.empty(Bn), np.empty(Bn)
p_geom = 1 / 4.0
for b in range(Bn):
    # stationary bootstrap indices
    idx = np.empty(T, np.int64)
    i = rng.integers(T)
    for k in range(T):
        if k > 0 and rng.random() < p_geom:
            i = rng.integers(T)
        idx[k] = i
        i = (i + 1) % T
    Xb = W[idx]
    mb = Xb.mean(0)
    mx_rc[b] = ((mb - center_rc) / (sd / math.sqrt(T))).max()
    mx_spa[b] = ((mb - center_spa) / (sd / math.sqrt(T))).max()
res["reality_check_p_candidate"] = round(float((mx_rc >= obs[cand_j]).mean()), 4)
res["spa_c_p_candidate"] = round(float((mx_spa >= obs[cand_j]).mean()), 4)
res["rc_max_t_q50_90_95"] = [round(float(np.percentile(mx_rc, p)), 2) for p in (50, 90, 95)]
# single-test bootstrap p (no selection) for reference
single = np.empty(Bn)
for b in range(Bn):
    idx = np.empty(T, np.int64)
    i = rng.integers(T)
    for k in range(T):
        if k > 0 and rng.random() < p_geom:
            i = rng.integers(T)
        idx[k] = i
        i = (i + 1) % T
    single[b] = (W[idx, cand_j].mean() - mu[cand_j]) / (sd[cand_j] / math.sqrt(T))
res["single_test_p_candidate"] = round(float((single >= obs[cand_j]).mean()), 4)

# deflated Sharpe (per-trade SR) under alternative assumptions
Rc = gl.cut(gl.simulate(m1, S.make_orders(m1, **PARAMS), no_overlap=True), "is").R.to_numpy()
sr = Rc.mean() / Rc.std(ddof=1)
n = len(Rc)
sk, ku = stats.skew(Rc), stats.kurtosis(Rc, fisher=False)
g = 0.5772156649


def dsr(var_sr, N):
    sr0 = math.sqrt(var_sr) * ((1 - g) * stats.norm.ppf(1 - 1 / N) + g * stats.norm.ppf(1 - 1 / (N * math.e)))
    den = math.sqrt(1 - sk * sr + (ku - 1) / 4 * sr * sr)
    return float(stats.norm.cdf((sr - sr0) * math.sqrt(n - 1) / den)), sr0


srs = np.array([x["sr_trade"] for x in info])
d = {}
for nm, v in (("empirical_var_all48", float(np.var(srs, ddof=1))),
              ("empirical_var_plausible", float(np.var(srs[ok], ddof=1))),
              ("null_var_1_over_n", 1.0 / n)):
    for N in (5, 10, 20, 48):
        p_, s0 = dsr(v, N)
        d[f"{nm}|N={N}"] = [round(p_, 3), round(s0, 4)]
res["dsr_variants"] = d
res["candidate_sr_trade"] = round(float(sr), 4)
json.dump(res, open(os.path.join(HERE, "s06_multtest.json"), "w"), indent=1)
print(json.dumps(res, indent=1))
