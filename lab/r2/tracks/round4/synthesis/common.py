"""PROTOCOL_V3 Addendum J, round 4: lead analyst's synthesis. Shared helpers. IN SAMPLE ONLY.

Data rules
- No price frame is read and nothing is simulated here: only trade files already written by the five engineers and the
  official trades of the ten sleeves.
- Every trade file is read with the pyarrow row filters entry_time < 2022-01-01 AND exit_time < 2022-01-01 inside the
  read call, and asserted afterwards; no 2022+ row enters the process.
- No goldlab import (my own code).
Weeks
- "wsun": weeks Monday..Sunday on UTC exit time (pandas W-SUN), the convention of the five engineers' correlations.
- "server": FP server weeks (New York + 7 h, Monday..Sunday) booked at the exit, the convention of the Addendum H/I
  syntheses (r2/tracks/sizing/synthesis/sy_common.py).
- Window 2014-2021: every calendar week from the one holding 2014-01-01 to the one holding 2021-12-31 (418 weeks);
  empty weeks count as 0. Weekly Sharpe = mean / sd(ddof=1) x sqrt(52).
Writes only in lab/r2/tracks/round4/synthesis/ and lab/results/r2/round4/synthesis.json.
Run with: NUMBA_CACHE_DIR=/tmp/r4synth_numba PYTHONDONTWRITEBYTECODE=1 python3 <script>.py
"""
import json
import os
import sys

sys.dont_write_bytecode = True
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
R4 = os.path.join(LAB, "results", "r2", "round4")
OFFICIAL = os.path.join(LAB, "results", "r2", "recalc", "trades")
CUT = pd.Timestamp("2022-01-01", tz="UTC")

TEN = [("ocm4", "us100"), ("noise30", "us100"),
       ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd"), ("GOLD_FRI_PM", "xauusd"),
       ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"),
       ("F1_brk_ridge_filter", "btcusd"), ("F1_brk_ridge_filter", "ethusd"),
       ("nq_btc_follow", "btcusd")]
CLUSTERS = {"us100": ["ocm4__us100", "noise30__us100"],
            "gold": ["donch4h_stop__xauusd", "orb_asia_2d_buf10__xauusd", "GOLD_FRI_PM__xauusd"],
            "crypto": ["brk72_24h_wd__btcusd", "brk72_24h_wd__ethusd", "F1_brk_ridge_filter__btcusd",
                       "F1_brk_ridge_filter__ethusd", "nq_btc_follow__btcusd"]}


def read_is(path, columns=None):
    """Rows entered AND exited before 2022-01-01 UTC only (both filters inside the read)."""
    t = pq.read_table(path, columns=columns,
                      filters=[("entry_time", "<", CUT), ("exit_time", "<", CUT)]).to_pandas()
    t["entry_time"] = pd.to_datetime(t["entry_time"], utc=True)
    t["exit_time"] = pd.to_datetime(t["exit_time"], utc=True)
    assert (t.entry_time < CUT).all() and (t.exit_time < CUT).all()
    return t.sort_values("entry_time", kind="stable").reset_index(drop=True)


def official(name, sym):
    return read_is(os.path.join(OFFICIAL, f"{name}__{sym}.parquet"),
                   columns=["entry_time", "exit_time", "side", "R"])


def pf(R):
    R = np.asarray(R, float)
    g, l_ = R[R > 0].sum(), -R[R < 0].sum()
    return float(g / l_) if l_ > 0 else float("inf")


def tstat(x):
    x = np.asarray(x, float)
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))) if len(x) > 2 else float("nan")


def weeks_index(conv):
    if conv == "wsun":
        return pd.period_range(pd.Period("2014-01-01", "W-SUN"), pd.Period("2021-12-31", "W-SUN"), freq="W-SUN")
    lo = (np.datetime64("2014-01-01", "D") - np.datetime64("1970-01-01", "D")).astype(np.int64)
    hi = (np.datetime64("2021-12-31", "D") - np.datetime64("1970-01-01", "D")).astype(np.int64)
    return pd.Index(np.arange((lo + 3) // 7, (hi + 3) // 7 + 1), name="server_week")


def week_of(exit_time, conv):
    if conv == "wsun":
        return exit_time.dt.tz_convert(None).dt.to_period("W-SUN")
    loc = exit_time.dt.tz_convert("America/New_York").dt.tz_localize(None) + pd.Timedelta(hours=7)
    days = (loc.values.astype("datetime64[D]") - np.datetime64("1970-01-01", "D")).astype(np.int64)
    return pd.Series((days + 3) // 7, index=exit_time.index)  # day 0 is a Thursday: Monday-based weeks


def weekly(t, conv, stake=1.0):
    wk = week_of(t.exit_time, conv)
    s = (t.R.astype(float) * stake).groupby(wk.values).sum()
    return s.reindex(weeks_index(conv), fill_value=0.0).to_numpy(np.float64)


def sharpe(w):
    w = np.asarray(w, float)
    sd = float(np.std(w, ddof=1))
    return float(np.mean(w) / sd * np.sqrt(52)) if sd > 0 else float("nan")


def corr(a, b):
    return float(np.corrcoef(np.asarray(a, float), np.asarray(b, float))[0, 1])


def dump(obj, path):
    def js(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (np.bool_,)):
            return bool(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, (pd.Timestamp,)):
            return str(o)
        raise TypeError(type(o))
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=js, ensure_ascii=False)
