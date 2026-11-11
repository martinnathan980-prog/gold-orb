"""Novelty (in-sample): daily results of the candidates against the two gold rules already in the portfolio."""
import sys, json, importlib.util
sys.path.insert(0, "/home/user/gold-orb/lab")
import numpy as np, pandas as pd
import goldlab as gl
from goldlab import r2
from goldlab.split import cut
from pivbb.tracks.run import strategy as S
OUT = "/home/user/gold-orb/lab/results/pivbb/run"


def mod(path, name):
    sp = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(sp); sys.modules[name] = m; sp.loader.exec_module(m)
    return m


trend = mod("/home/user/gold-orb/lab/tracks/trend/strategy.py", "strategy_trend")
orb = mod("/home/user/gold-orb/lab/tracks/orb/strategy.py", "strategy_orb")
CAND = {"r2s2_touch_run": dict(levels=["D_R2", "D_S2"], entry="touch"),
        "outer_close_ride": dict(levels=["D_R2", "D_S2", "D_R3", "D_S3"], hours=[2, 12], target=None)}
T = {"donch4h_stop": cut(r2.run("xauusd", trend.make_orders, trend.FINALISTS["donch4h_stop"], "fp"), "is"),
     "orb_asia_2d_buf10": cut(r2.run("xauusd", orb.make_orders, orb.FINALISTS["orb_asia_2d_buf10"], "fp"), "is")}
for k, p in CAND.items():
    T[k] = cut(r2.run("xauusd", S.make_orders, p, "fp"), "is")
m1 = r2.load("xauusd", end="2022-01-01")
mid = ((m1["bc"] + m1["ac"]) / 2)
td = gl.trading_day(m1.index)
dclose = mid.groupby(td).last()                      # mark at the end of each trading day
days = dclose.index


def daily_mtm(t):
    """Daily result in R, marked to market at each 17:00 New York close; costs land on the exit day."""
    out = pd.Series(0.0, index=days)
    d0 = gl.trading_day(t.entry_time); d1 = gl.trading_day(t.exit_time - pd.Timedelta(seconds=1))
    for e, x, a, b, s, pe, R, risk in zip(t.entry_time, t.exit_time, d0, d1, t.side, t.entry, t.R, t.risk):
        b = min(b, days[-1])                     # a trade entered in-sample that exits after it is booked on the last in-sample day
        if a == b or risk <= 0:
            out[b] += R
            continue
        ds = days[(days >= a) & (days < b)]
        prev, acc = pe, 0.0
        for d in ds:
            r = s * (dclose[d] - prev) / risk
            out[d] += r; acc += r; prev = dclose[d]
        out[b] += R - acc
    return out


DM = pd.DataFrame({k: daily_mtm(t) for k, t in T.items()})
DM = DM[(DM.index >= "2013-01-01")]
res = {"n_trades": {k: int(len(t)) for k, t in T.items()}, "daily_mtm_corr": DM.corr().round(3).to_dict(),
       "weekly_corr": DM.groupby(DM.index.to_period("W")).sum().corr().round(3).to_dict()}
act = DM.copy()
for c in CAND:
    for leg in ("donch4h_stop", "orb_asia_2d_buf10"):
        both = (DM[c] != 0) & (DM[leg] != 0)
        res[f"{c}|{leg}"] = {"days_both_active": int(both.sum()), "days_cand_active": int((DM[c] != 0).sum()),
                             "corr_on_days_both_active": round(float(DM.loc[both, [c, leg]].corr().iloc[0, 1]), 3),
                             "cand_mean_R_per_day_when_legacy_flat": round(float(DM.loc[(DM[c] != 0) & (DM[leg] == 0), c].mean()), 4),
                             "cand_mean_R_per_day_when_legacy_active": round(float(DM.loc[both, c].mean()), 4)}
# same-side overlap at the entry
for c in CAND:
    t = T[c]
    for leg in ("donch4h_stop", "orb_asia_2d_buf10"):
        L = T[leg]
        le = L.entry_time.to_numpy("datetime64[ns]").astype(np.int64); lx = L.exit_time.to_numpy("datetime64[ns]").astype(np.int64); ls = L.side.to_numpy()
        te = t.entry_time.to_numpy("datetime64[ns]").astype(np.int64)
        k = np.searchsorted(le, te, side="right") - 1
        inside = (k >= 0) & (lx[np.clip(k, 0, None)] > te)
        same = inside & (ls[np.clip(k, 0, None)] == t.side.to_numpy())
        opp = inside & ~same
        R = t.R.to_numpy()
        res[f"{c}|{leg}"].update(share_entered_while_legacy_open_same_side=round(float(same.mean()), 3), exp_R_same_side=round(float(R[same].mean()), 4) if same.any() else None,
                                 share_legacy_open_opposite=round(float(opp.mean()), 3), exp_R_opposite=round(float(R[opp].mean()), 4) if opp.any() else None,
                                 share_legacy_flat=round(float((~inside).mean()), 3), exp_R_legacy_flat=round(float(R[~inside].mean()), 4), n_legacy_flat=int((~inside).sum()))
print(json.dumps(res, indent=1))
json.dump(res, open(OUT + "/novelty.json", "w"), indent=1)
