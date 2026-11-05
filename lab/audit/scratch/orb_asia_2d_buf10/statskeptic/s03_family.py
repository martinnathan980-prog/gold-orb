"""Selection within the ORB track: re-simulate all 48 logged ORB configs on IS (patched data, orders
cut to IS dates before simulating, exactly like tracks/orb/research.py, but WITHOUT logging), build
their weekly-R matrix, estimate the effective number of independent trials, and the family-wise
null distribution of the best IS t-stat.  Also a frictionless run per config to get the gross
edge and the cost per trade (=> mean t-stat of a random-side null of each config)."""
import json
import time

from common import *  # noqa
from goldlab.sim import Costs

m1 = gl.load_m1("xauusd")
rows = [json.loads(l) for l in open(os.path.join(LAB, "results", "orb", "research_cache.jsonl"))]
FREE = Costs(commission=0.0, slip_bps=0.0, swap_long=0.0, swap_short=0.0, spread_mult=0.0)  # mid prices
IS_END = pd.Timestamp("2022-01-01")
weeks = pd.period_range("2013-01-01", "2022-01-09", freq="W")
W = np.zeros((len(weeks), len(rows)))
info = []
t0 = time.time()
for j, d in enumerate(rows):
    p = dict(d["params"])
    no_ov = p.pop("no_overlap", True)
    o = S.make_orders(m1, **p)
    o = o[pd.to_datetime(o.date) < IS_END].reset_index(drop=True)
    t = gl.cut(gl.simulate(m1, o, no_overlap=no_ov), "is")
    tf = gl.cut(gl.simulate(m1, o, costs=FREE, no_overlap=no_ov), "is")
    R = t.R.to_numpy()
    Rf = tf.R.to_numpy()
    wk = t.groupby(t.exit_time.dt.tz_convert(None).dt.to_period("W"))["R"].sum()
    k = weeks.get_indexer(wk.index)
    W[k[k >= 0], j] = wk.to_numpy()[k >= 0]
    sd = float(np.std(R, ddof=1))
    # cost per trade on the same signals (gross run may take a slightly different path; use means)
    cost = float(np.mean(Rf) - np.mean(R))
    info.append({"label": d["label"], "stage": d["stage"], "no_overlap": no_ov, "n": int(len(R)), "pf": pf(R),
                 "t": tstat(R), "exp": float(np.mean(R)), "sd": sd, "gross_exp": float(np.mean(Rf)),
                 "gross_t": tstat(Rf), "cost_R": cost,
                 "t_null_random_side": -cost / (sd / math.sqrt(len(R))),
                 "logged_pf_unpatched": d["rep"].get("pf"), "logged_t_unpatched": d["rep"].get("t_stat")})
    print(j, d["label"], {k_: round(v, 3) if isinstance(v, float) else v for k_, v in info[-1].items()}, round(time.time() - t0), flush=True)

np.save(os.path.join(HERE, "s03_weekly_R.npy"), W)
C = np.corrcoef(W.T)
ev = np.clip(np.linalg.eigvalsh(C), 0, None)[::-1]
M = len(rows)
li_ji = float(np.sum((ev >= 1).astype(float) + (ev - np.floor(ev))))
nyholt = float(1 + (M - 1) * (1 - np.var(ev, ddof=1) / M))
galwey = float(np.sum(np.sqrt(ev)) ** 2 / np.sum(ev))


def meff(sub):
    Cs = C[np.ix_(sub, sub)]
    e = np.clip(np.linalg.eigvalsh(Cs), 0, None)
    m = len(sub)
    return {"M": m, "li_ji": float(np.sum((e >= 1).astype(float) + (e - np.floor(e)))),
            "nyholt": float(1 + (m - 1) * (1 - np.var(e, ddof=1) / m)),
            "galwey": float(np.sum(np.sqrt(e)) ** 2 / np.sum(e))}


lab = [r["label"] for r in info]
stg = [r["stage"] for r in info]
fi = lab.index("F3_A3_buf0.1")
sel_14 = [i for i, s in enumerate(stg) if s.split("-")[0] in ("1", "2", "3", "4")]
asia_multi = [i for i, r in enumerate(rows) if r["params"].get("range_start") in ("00:00", "-01:00", "01:00")
              and r["params"].get("hold_days", 0) >= 1 and r["params"].get("tz") == "LDN"]
res = {"n_configs": M, "meff_all": {"li_ji": li_ji, "nyholt": nyholt, "galwey": galwey},
       "meff_stages1_4": meff(sel_14), "meff_asia_multiday": meff(asia_multi),
       "corr_F3_with": {lab[i]: round(float(C[fi, i]), 3) for i in np.argsort(-C[fi])},
       "info": info}

# family-wise null for the best IS t-stat: Z ~ MVN(mu, C)
rng = np.random.default_rng(5)
L = np.linalg.cholesky(C + 1e-9 * np.eye(M))
Z = rng.standard_normal((200_000, M)) @ L.T
mu_rand = np.array([r["t_null_random_side"] for r in info])
obs = {"t_patched": tstat(pd.read_parquet(os.path.join(HERE, "cand_trades_is.parquet")).query("cost=='normal'").R), "t_unpatched": 1.99}
fw = {}
for nm, sub in (("all48", list(range(M))), ("stages1_4", sel_14), ("asia_multiday", asia_multi)):
    for hyp, mu in (("zero_net", np.zeros(M)), ("random_side_cost_drag", mu_rand)):
        mx = (Z[:, sub] + mu[sub]).max(axis=1)
        fw[f"{nm}/{hyp}"] = {"E_max_t": round(float(mx.mean()), 3),
                             "p95_max_t": round(float(np.percentile(mx, 95)), 3),
                             "P(max>=t_patched)": round(float((mx >= obs["t_patched"]).mean()), 5),
                             "P(max>=t_unpatched)": round(float((mx >= obs["t_unpatched"]).mean()), 5),
                             "P(max>=2.0)": round(float((mx >= 2.0)).mean() if False else float((mx >= 2.0).mean()), 5)}
res["familywise_max_t"] = fw
res["observed"] = obs
json.dump(res, open(os.path.join(HERE, "s03_family.json"), "w"), indent=1, default=str)
print(json.dumps({k: v for k, v in res.items() if k != "info"}, indent=1, default=str))
