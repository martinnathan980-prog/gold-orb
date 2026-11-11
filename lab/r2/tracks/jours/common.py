"""Track `jours` (PROTOCOL_V3, Addendum E, family 2 and 3): GREEN DAYS. IN SAMPLE ONLY.

Everything here is cut at 2022-01-01: trades files right after they are read (`load_trades`), price frames at
2022-01-15 (r2/tracks/fx/common.py::load_is: the two extra weeks only let December 2021 trades reach their exit)
and only trades ENTERED before 2022-01-01 are ever kept or reported.

CLOCK (the same as track `stake`): FP Markets server time = New York local time + 7 h. A day is a server calendar
day, a week runs Monday..Sunday in server time, a result is booked on the day of its EXIT.

UNITS: every result is in units of the BASE STAKE (R0 = the money risked on one trade of the validated rules at
its original stop; at a 1 % stake, 1 unit = 1 % of the account).
"""
import gc
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
if LAB not in sys.path:
    sys.path.insert(0, LAB)

OUT = os.path.join(LAB, "results", "r2", "jours")
os.makedirs(OUT, exist_ok=True)
NET_DIR = os.path.join(LAB, "results", "r2", "recalc", "trades")
GROSS_DIR = os.path.join(LAB, "results", "r2", "stake", "trades_gross_is")
SLEEVES = [("noise30", "us100"), ("ocm4", "us100"), ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"),
           ("nq_btc_follow", "btcusd"), ("F1_brk_ridge_filter", "btcusd"), ("F1_brk_ridge_filter", "ethusd"),
           ("GOLD_FRI_PM", "xauusd"), ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd")]
INTRADAY = ["noise30_us100", "ocm4_us100", "nq_btc_follow_btcusd", "GOLD_FRI_PM_xauusd"]
IS_END = pd.Timestamp("2022-01-01", tz="UTC")
IS_END_FRAME = pd.Timestamp("2022-01-15", tz="UTC")
COMMON_START = pd.Timestamp("2018-02-01", tz="UTC")


def server_time(ts):
    """UTC timestamps -> naive FP server time (New York local time + 7 h)."""
    return pd.DatetimeIndex(ts).tz_convert("America/New_York").tz_localize(None) + pd.Timedelta(hours=7)


def load_trades(kind="net"):
    """The ten validated sleeves, IN SAMPLE ONLY (entry < 2022-01-01), sorted by entry time."""
    fr = []
    for name, sym in SLEEVES:
        t = pd.read_parquet(os.path.join(NET_DIR if kind == "net" else GROSS_DIR, f"{name}__{sym}.parquet"))
        t = t[t.entry_time < IS_END]                       # the cut comes first
        fr.append(pd.DataFrame({"sleeve": f"{name}_{sym}", "sym": sym, "t_in": t.entry_time.to_numpy(),
                                "t_out": t.exit_time.to_numpy(), "R": t.R.to_numpy(float),
                                "entry": t.entry.to_numpy(float), "risk": t.risk.to_numpy(float),
                                "pnl": t.pnl.to_numpy(float), "side": t.side.to_numpy()}))
    d = pd.concat(fr, ignore_index=True)
    d["t_in"] = pd.to_datetime(d.t_in, utc=True)
    d["t_out"] = pd.to_datetime(d.t_out, utc=True)
    d = d.sort_values(["t_in", "sleeve"], kind="stable").reset_index(drop=True)
    assert (d.t_in < IS_END).all()
    return d


def load_is(sym):
    """In-sample M1 frame (cut at 2022-01-15)."""
    from goldlab import data as _data
    df = pd.read_parquet(os.path.join(_data.DATA, "fp", f"{sym}_m1.parquet"))
    df = df.iloc[:int(df.index.searchsorted(IS_END_FRAME))].copy()
    gc.collect()
    assert df.index[-1] < IS_END_FRAME
    return df


def daily(t_out, res, start=None, end=None):
    """Sum of results per server day of exit -> Series indexed by server day (only days with a booked result)."""
    s = pd.Series(np.asarray(res, float), index=server_time(t_out).normalize())
    s = s.groupby(level=0).sum()
    if start is not None:
        s = s[s.index >= pd.Timestamp(start)]
    if end is not None:
        s = s[s.index < pd.Timestamp(end)]
    return s


def stats(day, years=None):
    """Calendar statistics of a daily series (units of base stake)."""
    day = day[day != 0.0]
    if len(day) == 0:
        return {"days": 0}
    wk = day.groupby(day.index.to_period("W-SUN")).sum()
    mo = day.groupby(day.index.to_period("M")).sum()
    g, r = day[day > 0], day[day < 0]
    eq = day.cumsum()
    dd = float((eq.cummax().clip(lower=0) - eq).max())
    yrs = years if years else max((day.index[-1] - day.index[0]).days / 365.25, 1e-9)
    ag, ar = (float(g.mean()) if len(g) else 0.0), (float(-r.mean()) if len(r) else 0.0)
    return {"days": int(len(day)), "green_days": round(float((day > 0).mean()) * 100, 1),
            "green_weeks": round(float((wk > 0).mean()) * 100, 1), "green_months": round(float((mo > 0).mean()) * 100, 1),
            "avg_green": round(ag, 3), "avg_red": round(ar, 3), "red_in_greens": round(ar / ag, 2) if ag > 0 else None,
            "total": round(float(day.sum()), 1), "per_year": round(float(day.sum()) / yrs, 1),
            "worst_day": round(float(day.min()), 2), "worst_week": round(float(wk.min()), 2),
            "worst_month": round(float(mo.min()), 2), "max_dd": round(dd, 2), "best_day": round(float(day.max()), 2),
            "p5_day": round(float(day.quantile(0.05)), 2), "p1_day": round(float(day.quantile(0.01)), 2)}


def halves(day):
    """Totals of the two halves of the sample (by number of days)."""
    day = day[day != 0.0]
    h = len(day) // 2
    return round(float(day.iloc[:h].sum()), 2), round(float(day.iloc[h:].sum()), 2)


def log_trial(rec, name="trials.jsonl"):
    with open(os.path.join(OUT, name), "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def week_bootstrap(day, n=1000, seed=7, half=50.0, horizon_weeks=52):
    """Whole-week bootstrap of a daily series: distribution of 1-year paths. Returns the chance that the running
    loss reaches `half` units (= half the account at a 1 % base stake, no compounding) within a year."""
    rng = np.random.default_rng(seed)
    wk = day.groupby(day.index.to_period("W-SUN")).sum().to_numpy()
    idx = rng.integers(0, len(wk), size=(n, horizon_weeks))
    paths = wk[idx].cumsum(axis=1)
    return float((paths.min(axis=1) <= -half).mean())
