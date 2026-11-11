"""Diagnostics on the logged candidates A / B (no new configuration): basket daily-sum t, halves, by-year,
volatility regime, bear years, weeks, stop distance 2020-2021 on the minimum lot. IS trades only (CSV of stage3b)."""
import json, numpy as np, pandas as pd
from common import *
out = {}
def tstat(x):
    x = np.asarray(x, float); return float(x.mean() / x.std(ddof=1) * np.sqrt(len(x))) if len(x) > 2 else 0.0
lines = []
for nm, syms in (("A", ["us500", "us100", "us30", "ger40"]), ("B", ["us500", "us100", "us30"])):
    allt = []
    for sym in syms:
        t = pd.read_csv(f"{RES}/trades_{nm}_{sym}.csv", parse_dates=["entry_time", "exit_time"])
        t["sym"] = sym; allt.append(t)
        h1, h2 = t[t.entry_time < "2018-01-01"], t[t.entry_time >= "2018-01-01"]
        wk = t.groupby(t.exit_time.dt.tz_convert(None).dt.to_period("W")).R.sum()
        # volatility regime: stop distance (= 2.5 ATR) relative to price vs its trailing 250-trade-day median is not
        # available per day here; use the ATR/price of the trade itself vs the median of PRIOR trades' ATR/price (causal)
        risk_rel = (t.entry - t.stop).abs() / t.entry
        prior_med = risk_rel.expanding().median().shift(1)
        hv = risk_rel > prior_med
        bear = t.entry_time.dt.year.isin([2015, 2018, 2020])
        s20 = t[(t.entry_time >= "2020-01-01")]
        stop_pts = (s20.entry - s20.stop).abs().median()
        d = {"n": len(t), "win_rate": round((t.R > 0).mean(), 3), "exp_R": round(t.R.mean(), 4), "t": round(tstat(t.R), 2),
             "net_bp": round(((t.pnl / t.entry) * 1e4).mean(), 2), "gross_bp": round(t.gross_bp.mean(), 2),
             "swap_bp": round((t.swap / t.entry * 1e4).mean(), 2),
             "gross_bp_2014_17": round(h1.gross_bp.mean(), 2), "gross_bp_2018_21": round(h2.gross_bp.mean(), 2),
             "by_year_R": t.groupby(t.entry_time.dt.year).R.sum().round(2).to_dict(),
             "weeks_with_trade_pos_pct": round((wk > 0).mean() * 100, 1),
             "highvol_n_expR": [int(hv.sum()), round(t.R[hv].mean(), 4)], "lowvol_n_expR": [int((~hv).sum()), round(t.R[~hv].mean(), 4)],
             "bear_years_n_expR": [int(bear.sum()), round(t.R[bear].mean(), 4)], "other_years_n_expR": [int((~bear).sum()), round(t.R[~bear].mean(), 4)],
             "median_stop_pts_2020_21": round(stop_pts, 1),
             "min_lot_risk_ccy_2020_21": round(stop_pts * r2.SPEC[sym]["units_per_lot"] * r2.SPEC[sym]["min_lot"], 1),
             "quote": r2.SPEC[sym]["quote"],
             "avg_win_R": round(t.R[t.R > 0].mean(), 3), "avg_loss_R": round(t.R[t.R < 0].mean(), 3),
             "stop_exits": int((t.reason == "stop").sum())}
        out[f"{nm}_{sym}"] = d
        lines.append(f"{nm} {sym:<6} " + json.dumps(d))
    b = pd.concat(allt)
    day = b.entry_time.dt.tz_convert(gl.NY).dt.date
    ds = b.groupby(day).R.sum()
    pos = b.R[b.R > 0].sum(); neg = -b.R[b.R < 0].sum()
    by_sym_profit = b.groupby("sym").R.sum()
    out[f"{nm}_basket"] = {"n_trades": len(b), "n_days": len(ds), "t_daily_sums": round(tstat(ds), 2), "pooled_pf": round(pos / neg, 3),
                           "pooled_exp_R": round(b.R.mean(), 4), "share_instruments_positive": float((by_sym_profit > 0).mean()),
                           "R_by_sym": by_sym_profit.round(1).to_dict(),
                           "years_pos": f"{int((b.groupby(b.entry_time.dt.year).R.sum() > 0).sum())}/{b.entry_time.dt.year.nunique()}",
                           "mean_trades_per_trade_day": round(len(b) / len(ds), 2)}
    lines.append(f"{nm} basket " + json.dumps(out[f'{nm}_basket']))
# correlation of daily R between us500 and us100 for A
txt = "\n".join(lines); print(txt)
open(f"{RES}/diag.txt", "w").write(txt + "\n")
json.dump(out, open(f"{RES}/diag.json", "w"), indent=1, default=str)
