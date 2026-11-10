"""Permutation test of the learned filter: the outcomes R are shuffled among the candidates of the same market
and year (so every year keeps its own average), then the WHOLE walk-forward is redone. If the filter only
found noise, the real out-of-fold gain (mean R of the selected candidates minus mean R of all candidates,
every candidate taken on its own) should look like the shuffled ones."""
import json
import sys

sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/ml")
from research import *  # noqa
import wf

POOL = ["us100", "ger40", "xauusd", "btcusd"]
GEN = {"stop_k": 2.0, "hold_h": 13.0}
REC = {"type": "ridge", "num": wf.NUM_FULL, "dummies": wf.DUM_FULL, "alpha": 1000.0}
Q = "0.5"
NPERM = 500


def gains(model, d, eth):
    out = {}
    o = d[np.isfinite(d["score"])]
    for sym in POOL:
        g = o[o.sym == sym]
        out[sym] = float(g[g["pass_" + Q]].R.mean() - g.R.mean())
    out["pool4"] = float(o[o["pass_" + Q]].R.mean() - o.R.mean())
    # ethusd is never in the training pool: score it with the fold models
    sel = np.zeros(len(eth), bool)
    has = np.zeros(len(eth), bool)
    for y, spec in model["folds"].items():
        m = (eth.year == int(y)).to_numpy()
        if m.any():
            sel[m] = S.score_model(eth[m], spec) >= spec["thr"][Q]
            has[m] = True
    e = eth[has]
    out["ethusd"] = float(e[sel[has]].R.mean() - e.R.mean())
    b = pd.concat([o[o.sym == "btcusd"][["R"]].assign(p=o[o.sym == "btcusd"]["pass_" + Q].to_numpy()),
                   e[["R"]].assign(p=sel[has])])
    out["btc+eth"] = float(b[b.p].R.mean() - b.R.mean())
    return out


if __name__ == "__main__":
    tabs = {s: table(s, GEN, "X1") for s in POOL}
    eth = table("ethusd", GEN, "X1")
    eth = eth[np.isfinite(eth.R)].reset_index(drop=True)
    model, d = wf.fit("perm_tmp", REC, tabs, GEN, save=False)
    real = gains(model, d, eth)
    print("real out-of-fold gain (R per candidate):", {k: round(v, 4) for k, v in real.items()})
    rows = []
    for seed in range(NPERM):
        m, dp = wf.fit("perm_tmp", REC, tabs, GEN, save=False, shuffle_seed=1000 + seed)
        rng = np.random.default_rng(5000 + seed)
        ep = eth.copy()
        ep["R"] = ep.groupby("year")["R"].transform(lambda x: rng.permutation(x.to_numpy()))
        rows.append(gains(m, dp, ep))
    p = pd.DataFrame(rows)
    res = {"n_perm": NPERM, "q": Q, "statistic": "mean R of selected OOF candidates minus mean R of all OOF candidates (every candidate on its own)"}
    for k in real:
        res[k] = {"real_gain_R": round(real[k], 4), "perm_mean": round(float(p[k].mean()), 4), "perm_sd": round(float(p[k].std()), 4),
                  "perm_p95": round(float(p[k].quantile(0.95)), 4), "perm_max": round(float(p[k].max()), 4),
                  "percentile_of_real": round(float((p[k] < real[k]).mean() * 100), 1)}
        print(k, res[k])
    json.dump(res, open(os.path.join(RES, "permutation_test.json"), "w"), indent=1)
