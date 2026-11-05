"""Performance metrics on a trades frame from sim.simulate (R-multiple based)."""
import json
import math

import numpy as np
import pandas as pd


def _pf(x):
    g, l = x[x > 0].sum(), -x[x < 0].sum()
    return float(g / l) if l > 0 else (float("inf") if g > 0 else float("nan"))


def max_dd(cum):
    peak = np.maximum.accumulate(np.r_[0.0, cum])
    return float((peak - np.r_[0.0, cum]).max())


def report(t, risk_pct=0.5):
    """Key stats. R = pnl / initial risk. Equity assumes `risk_pct`% of equity risked per trade."""
    if len(t) == 0:
        return {"n": 0}
    R = t["R"].to_numpy()
    R = R[np.isfinite(R)]
    yrs = t.entry_time.dt.year
    span_years = max((t.exit_time.max() - t.entry_time.min()).days / 365.25, 1e-9)
    by_year = t.groupby(yrs)["R"].sum()
    wk = t.groupby(t.exit_time.dt.tz_convert(None).dt.to_period("W"))["R"].sum()
    # all calendar weeks in the span (weeks without trades count as flat)
    all_wk = pd.period_range(wk.index.min(), wk.index.max(), freq="W")
    wk_all = wk.reindex(all_wk, fill_value=0.0)
    mo = t.groupby(t.exit_time.dt.tz_convert(None).dt.to_period("M"))["R"].sum()
    eq = np.cumprod(1 + R * risk_pct / 100)
    cumR = np.cumsum(R)
    out = {
        "n": int(len(R)),
        "trades_per_year": round(len(R) / span_years, 1),
        "win_rate": round(float((R > 0).mean()), 3),
        "avg_win_R": round(float(R[R > 0].mean()), 3) if (R > 0).any() else 0.0,
        "avg_loss_R": round(float(R[R < 0].mean()), 3) if (R < 0).any() else 0.0,
        "expectancy_R": round(float(R.mean()), 4),
        "t_stat": round(float(R.mean() / (R.std(ddof=1) / math.sqrt(len(R)))), 2) if len(R) > 2 else 0.0,
        "pf": round(_pf(R), 3),
        "total_R": round(float(R.sum()), 1),
        "max_dd_R": round(max_dd(cumR), 1),
        "years_pos": f"{int((by_year > 0).sum())}/{len(by_year)}",
        "weeks_pos_pct": round(float((wk_all > 0).mean() * 100), 1),
        "weeks_neg_pct": round(float((wk_all < 0).mean() * 100), 1),
        "months_pos_pct": round(float((mo > 0).mean() * 100), 1),
        "worst_week_R": round(float(wk_all.min()), 1),
        "long_n": int((t.side > 0).sum()),
        "long_R": round(float(t.loc[t.side > 0, "R"].sum()), 1),
        "short_n": int((t.side < 0).sum()),
        "short_R": round(float(t.loc[t.side < 0, "R"].sum()), 1),
        "avg_hold_h": round(float(t.hold_min.mean() / 60), 1),
        "max_hold_h": round(float(t.hold_min.max() / 60), 1),
        "pf_ret": round(_pf(t["ret"].to_numpy()), 3),
        f"equity_x_{risk_pct}pct": round(float(eq[-1]), 2),
        f"cagr_{risk_pct}pct": round(float(eq[-1] ** (1 / span_years) - 1) * 100, 1),
        f"maxdd_{risk_pct}pct": round(float(1 - np.exp(-max_dd(np.log(eq)))) * 100, 1),
        "by_year_R": {int(k): round(float(v), 1) for k, v in by_year.items()},
        "exit_reasons": t.reason.value_counts().to_dict(),
    }
    return out


def show(rep, title=""):
    if title:
        print(f"== {title}")
    short = {k: v for k, v in rep.items() if k not in ("by_year_R", "exit_reasons")}
    print(json.dumps(short))
    if "by_year_R" in rep:
        print("   by year R:", rep["by_year_R"], "| exits:", rep["exit_reasons"])


def weekly_R(t):
    return t.groupby(t.exit_time.dt.tz_convert(None).dt.to_period("W"))["R"].sum()
