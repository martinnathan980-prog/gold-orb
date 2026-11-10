"""Diagnostic (in-sample trades, no new configuration): is a candidate spanned by the legacy sleeve?
  * causal split: trades entered while a same-side legacy trade is open vs all others
  * weekly spanning regression  R_cand(week) = alpha + beta * R_legacy(week)
  * the same with the candidate's trades that are unrelated to a legacy entry (entered more than 4h
    before/after one and not inside a same-side legacy trade) -- NB this last split conditions on the
    future (a legacy entry within the NEXT 4h), it is a description, not a tradable filter."""
import json, os, sys
import numpy as np, pandas as pd
from research import RES, is_trades, pf, tstat
import stageA, stageB, stageD
from decomp import CFG, LEG, groups, stat


def weekly(t, idx=None):
    w = t.groupby(t.exit_time.dt.tz_convert(None).dt.to_period("W"))["R"].sum()
    return w if idx is None else w.reindex(idx, fill_value=0.0)


def ols(y, x):
    X = np.column_stack([np.ones(len(x)), x])
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y - X @ b
    s2 = res @ res / (len(y) - 2)
    cov = s2 * np.linalg.inv(X.T @ X)
    return {"alpha_R_per_week": round(float(b[0]), 4), "t_alpha": round(float(b[0] / np.sqrt(cov[0, 0])), 2),
            "beta": round(float(b[1]), 3), "t_beta": round(float(b[1] / np.sqrt(cov[1, 1])), 2),
            "corr": round(float(np.corrcoef(x, y)[0, 1]), 3)}


if __name__ == "__main__":
    leg = is_trades("xauusd", LEG)
    idx = pd.period_range("2013-01-07", "2021-12-31", freq="W")
    wl = weekly(leg, idx).to_numpy()
    out = {"legacy": {"mean_R_per_week": round(float(wl.mean()), 4), "sd": round(float(wl.std()), 3)}}
    le = leg.entry_time.to_numpy("datetime64[ns]").astype(np.int64)
    lx = leg.exit_time.to_numpy("datetime64[ns]").astype(np.int64)
    ls = leg.side.to_numpy()
    for name, p in CFG.items():
        t = is_trades("xauusd", p)
        te = t.entry_time.to_numpy("datetime64[ns]").astype(np.int64)
        k = np.searchsorted(le, te, side="right") - 1
        kc = np.clip(k, 0, None)
        inside_same = (k >= 0) & (lx[kc] > te) & (ls[kc] == t.side.to_numpy())
        R = t.R.to_numpy()
        w = weekly(t, idx).to_numpy()
        o = {"mean_R_per_week": round(float(w.mean()), 4), "sd": round(float(w.std()), 3),
             "causal_same_side_legacy_open": stat(R[inside_same]), "causal_legacy_flat_or_opposite": stat(R[~inside_same]),
             "spanning_weekly": ols(w, wl)}
        A, B, C = groups(t, leg)
        o["spanning_weekly_unrelated_trades_only"] = ols(weekly(t[C], idx).to_numpy(), wl)
        out[name] = o
        print(name, json.dumps(o), flush=True)
    json.dump(out, open(os.path.join(RES, "spanning_vs_legacy_is.json"), "w"), indent=1)
