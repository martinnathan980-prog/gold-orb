"""Descriptive level placebo with many seeds (no engine, no cost, every signal, mid prices, in-sample frame only).
Same decision table as the strategy (signals()), outcome = stop / target / forced exit walked on M1 mid bars.
Purpose: a finer answer to "is it the pivot or any line nearby?" than the 10 engine placebo runs. Nothing is selected here."""
import sys, json
sys.path.insert(0, "/home/user/gold-orb/lab")
import numpy as np, pandas as pd, numba as nb
from goldlab import r2
from pivbb.tracks.run import strategy as S
OUT = "/home/user/gold-orb/lab/results/pivbb/run"
m1 = r2.load("xauusd", end="2022-01-01")
c = S.context(m1)


@nb.njit(cache=True)
def walk(o, h, l, ei, xi, side, stop, tgt):
    R = np.empty(len(ei))
    for q in range(len(ei)):
        e = o[ei[q]]
        risk = side[q] * (e - stop[q])
        if risk <= 0:
            R[q] = np.nan
            continue
        r = np.nan
        for i in range(ei[q], xi[q]):
            if (side[q] == 1 and l[i] <= stop[q]) or (side[q] == -1 and h[i] >= stop[q]):
                r = -1.0
                break
            if np.isfinite(tgt[q]) and ((side[q] == 1 and h[i] >= tgt[q]) or (side[q] == -1 and l[i] <= tgt[q])):
                r = side[q] * (tgt[q] - e) / risk
                break
        if np.isnan(r):
            r = side[q] * (o[xi[q]] - e) / risk
        R[q] = r
    return R


def run(prm, seed):
    o = S.make_orders(m1, **dict(prm, placebo=seed))
    o = o[m1.index[o.entry_i.to_numpy()] >= pd.Timestamp("2013-01-01", tz="UTC")]
    R = walk(c["o"], c["h"], c["l"], o.entry_i.to_numpy(np.int64), o.exit_i.to_numpy(np.int64), o.side.to_numpy(np.int64), o["stop"].to_numpy(), o.target.to_numpy())
    R = R[np.isfinite(R)]
    R = np.clip(R, -1.5, 10)
    return {"n": int(len(R)), "mean_R": float(R.mean()), "pf": float(R[R > 0].sum() / -R[R < 0].sum())}


CAND = {"r2s2_touch_run": dict(levels=["D_R2", "D_S2"], entry="touch"),
        "outer_close_ride": dict(levels=["D_R2", "D_S2", "D_R3", "D_S3"], hours=[2, 12], target=None)}
res = {}
for name, prm in CAND.items():
    real = run(prm, None)
    pl = [run(prm, sd) for sd in range(100, 140)]
    mr = np.array([p["mean_R"] for p in pl]); pf = np.array([p["pf"] for p in pl])
    res[name] = {"real": real, "placebo_n_seeds": len(pl), "placebo_mean_R": {"mean": float(mr.mean()), "sd": float(mr.std(ddof=1)), "median": float(np.median(mr)),
                 "min": float(mr.min()), "max": float(mr.max())}, "placebo_pf": {"median": float(np.median(pf)), "min": float(pf.min()), "max": float(pf.max())},
                 "z_mean_R": float((real["mean_R"] - mr.mean()) / mr.std(ddof=1)), "seeds_at_or_above_real": int((mr >= real["mean_R"]).sum()),
                 "placebo_n_median": float(np.median([p["n"] for p in pl]))}
    print(name, json.dumps(res[name], indent=1), flush=True)
json.dump(res, open(OUT + "/placebo_descriptive_40seeds.json", "w"), indent=1)
# split of candidate A by level and direction (existing in-sample trades, no new run)
t = pd.read_csv(OUT + "/is_trades_r2s2_touch_run.csv")
t["what"] = t.lv_name + np.where(t.side > 0, " up", " down")
tab = t.groupby("what").R.agg(["size", "mean", "sum"]).round(3)
print(tab)
tab.to_csv(OUT + "/candA_by_level_direction.csv")
t["yr"] = pd.to_datetime(t.entry_time).dt.year
print(t.groupby(["yr"]).apply(lambda g: pd.Series({"n": len(g), "win": (g.R > 0).mean(), "R": g.R.sum()})).round(2).T)
