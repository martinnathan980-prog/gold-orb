"""Autopsy, lens `payoff` (PROTOCOL_V3 Addendum H): shared helpers.  IN SAMPLE ONLY.

* Price frames are read with a parquet row filter ts < 2022-01-01 00:00 UTC, so no 2022+ row is ever materialised;
  every rule and every simulation receives that slice explicitly (r2.run / recalc are never called on a full frame).
* Official trade files are read with the filter entry_time < 2022-01-01 in the same call.
* The us100 leader of nq_btc_follow is registered from the in-sample us100 slice (set_leader) BEFORE any order is
  built, so the strategy's default loader (which would read the 2022-2025 file) is never used.
* Costs: r2.costs(sym) (mode fp) and r2.costs(sym, 1.5) on the spread x1.5 frame (mode stress), exactly as r2.run.
"""
import os
import sys

os.environ.setdefault("NUMBA_CACHE_DIR", "/tmp/numba_payoff")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
sys.dont_write_bytecode = True

LAB = "/home/user/gold-orb/lab"
for p in (LAB, os.path.join(LAB, "r2")):
    if p not in sys.path:
        sys.path.insert(0, p)

import numba as nb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
from goldlab.sim import apply_spread_mult, simulate  # noqa: E402

CUT = pd.Timestamp("2022-01-01", tz="UTC")
COMMON_START = pd.Timestamp("2018-02-01", tz="UTC")
YEARS = (2018, 2019, 2020, 2021)
OUT = os.path.join(LAB, "results", "r2", "autopsy", "payoff")
CRYPTO = ("btcusd", "ethusd")
NY = "America/New_York"

# the ten sleeves of the study (F2_brk_unfiltered is in recalc.sleeves() but is not one of the ten)
TEN = [("noise30", "us100"), ("ocm4", "us100"),
       ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"),
       ("F1_brk_ridge_filter", "btcusd"), ("F1_brk_ridge_filter", "ethusd"), ("nq_btc_follow", "btcusd"),
       ("GOLD_FRI_PM", "xauusd"), ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd")]


def load_is(sym):
    """In-sample M1 frame of `sym`: rows with ts < 2022-01-01 00:00 UTC only (filter applied while reading)."""
    df = pd.read_parquet(os.path.join(LAB, "data", "fp", f"{sym}_m1.parquet"), filters=[("ts", "<", CUT)])
    assert len(df) and df.index.max() < CUT and df.index.is_monotonic_increasing
    return df


def load_official(name, sym):
    """Official trades of a sleeve, rows with entry_time < 2022-01-01 only (filter applied while reading)."""
    t = pd.read_parquet(os.path.join(LAB, "results", "r2", "recalc", "trades", f"{name}__{sym}.parquet"),
                        filters=[("entry_time", "<", CUT)])
    assert (t.entry_time < CUT).all()
    return t.sort_values("entry_time").reset_index(drop=True)


_REG = None


def registry():
    """{(name, sym): (track, make_orders, params)} for the ten sleeves, exactly as lab/r2/recalc.py registers them
    (the crypto breakout through its weekend wrapper)."""
    global _REG
    if _REG is None:
        import recalc
        out = {}
        for track, name, sym, mo, params in recalc.sleeves():
            if (name, sym) in TEN:
                out[(name, sym)] = (track, mo, params)
        assert len(out) == 10, sorted(out)
        _REG = out
    return _REG


def set_leader_is(us100_frame):
    """Register the IN-SAMPLE us100 mid closes as the leader of nq_btc_follow (never the default loader)."""
    _, mo, _ = registry()[("nq_btc_follow", "btcusd")]
    g = mo.__globals__
    g["clear_leaders"]()
    g["set_leader"]("us100", us100_frame)
    assert "us100" in g["_LEADERS"]


def clear_caches(mo):
    """Strategy caches keyed on id(frame) (ml, trend, orb): cleared before each call on a new frame."""
    g = mo.__globals__
    for k in ("_cache", "_bar_cache", "_daily_cache"):
        if k in g and isinstance(g[k], dict):
            g[k].clear()
    # the crypto wrapper closes over the crypto module: nothing cached there


def build_orders(name, sym, m1):
    """Base orders of the frozen rule on frame m1 (fp or stress frame), with a stable order id `oid`."""
    _, mo, params = registry()[(name, sym)]
    clear_caches(mo)
    o = mo(m1, **params).reset_index(drop=True)
    o["oid"] = np.arange(len(o), dtype=np.int64)
    return o


def costs(sym, stress):
    return r2.costs(sym, 1.5 if stress else 1.0)


def frames(sym):
    """(fp frame, stress frame) of the in-sample slice; the stress frame is the spread x1.5 copy (r2.run 'stress')."""
    m1 = load_is(sym)
    return m1, apply_spread_mult(m1, 1.5)


def sim(m1, orders, sym, stress, no_overlap=True):
    return simulate(m1, orders, sym=sym, costs=costs(sym, stress), no_overlap=no_overlap)


# ----------------------------------------------------------------------------------------- fills
@nb.njit(cache=True)
def _fills(bo, ao, bl, ah, al, bh, entry_i, side, etype, level, expiry_i, slip, slip_m):
    """Fill bar and fill price of each order exactly as goldlab.sim._run computes them (no_overlap aside)."""
    n = len(entry_i)
    N = len(bo)
    fb = np.full(n, -1, np.int64)
    fp = np.full(n, np.nan)
    for k in range(n):
        i0 = entry_i[k]
        if i0 < 0 or i0 >= N:
            continue
        s = side[k]
        if etype[k] == 0:
            fb[k] = i0
            fp[k] = ao[i0] * (1 + slip_m) if s > 0 else bo[i0] * (1 - slip_m)
            continue
        lv = level[k]
        jmax = min(expiry_i[k], N - 1)
        for i in range(i0, jmax + 1):
            if etype[k] == 1:
                if s > 0 and ah[i] >= lv:
                    fb[k] = i
                    fp[k] = max(lv, ao[i]) * (1 + slip)
                    break
                if s < 0 and bl[i] <= lv:
                    fb[k] = i
                    fp[k] = min(lv, bo[i]) * (1 - slip)
                    break
            else:
                if s > 0 and al[i] <= lv:
                    fb[k] = i
                    fp[k] = min(lv, ao[i])
                    break
                if s < 0 and bh[i] >= lv:
                    fb[k] = i
                    fp[k] = max(lv, bo[i])
                    break
    return fb, fp


def fills(m1, o, sym, stress):
    c = costs(sym, stress)
    n = len(o)
    col = lambda k, d: o[k].to_numpy() if k in o else np.full(n, d)
    fb, fp = _fills(m1["bo"].to_numpy(np.float64), m1["ao"].to_numpy(np.float64), m1["bl"].to_numpy(np.float64),
                    m1["ah"].to_numpy(np.float64), m1["al"].to_numpy(np.float64), m1["bh"].to_numpy(np.float64),
                    o["entry_i"].to_numpy(np.int64), o["side"].to_numpy(np.int64),
                    col("etype", 0).astype(np.int64), col("level", np.nan).astype(np.float64),
                    col("expiry_i", -1).astype(np.int64), c.slip_bps * 1e-4,
                    (c.slip_mkt_bps if c.slip_mkt_bps >= 0 else c.slip_bps) * 1e-4)
    return fb, fp


# ----------------------------------------------------------------------------------------- trades post-processing
def exit_bar(m1, t):
    """M1 index of each trade's exit bar (exit_time is the bar start for time exits, start + 1 min otherwise)."""
    et = t.exit_time - pd.to_timedelta(np.where(t.reason.to_numpy() == "time", 0, 1), unit="m")
    return np.searchsorted(m1.index.values, et.values.astype(m1.index.values.dtype), side="left")


def censored(m1, t, sym):
    """Trades still open when the in-sample frame ends (closed artificially at its last bar): their true result
    needs 2022 prices, so they are excluded from every statistic.  Crypto frames end on a scheduled closure, which
    is a real exit point for every crypto rule (lab convention), so nothing is censored there."""
    if not len(t):
        return np.zeros(0, bool)
    if sym in CRYPTO:
        return (t.reason == "eod").to_numpy()
    xb = exit_bar(m1, t)
    return ((xb >= len(m1) - 1) & t.reason.isin(["time", "eod"]).to_numpy()) | (t.reason == "eod").to_numpy()


def finalize(m1, t, sym):
    """Drop censored trades; add the year and window labels."""
    c = censored(m1, t, sym)
    t = t[~c].copy()
    t.attrs["censored"] = int(c.sum())
    t["year"] = t.entry_time.dt.year
    return t


def window(t, w):
    if w == "common":
        return t[(t.entry_time >= COMMON_START) & (t.entry_time < CUT)]
    if w == "early":
        return t[t.entry_time < COMMON_START]
    if w == "whole":
        return t[t.entry_time < CUT]
    raise ValueError(w)


def stats(t):
    """Per-trade statistics in R (net of the costs of the run)."""
    R = t["R"].to_numpy(float)
    R = R[np.isfinite(R)]
    n = len(R)
    if n == 0:
        return {"n": 0}
    pos, neg = R[R > 0], R[R < 0]
    cum = np.cumsum(R)
    dd = float((np.maximum.accumulate(np.r_[0.0, cum]) - np.r_[0.0, cum]).max())
    out = {"n": n, "win_rate": round(float((R > 0).mean()), 4), "exp_R": round(float(R.mean()), 4),
           "avg_win_R": round(float(pos.mean()), 4) if len(pos) else 0.0,
           "avg_loss_R": round(float(neg.mean()), 4) if len(neg) else 0.0,
           "pf": round(float(pos.sum() / -neg.sum()), 3) if len(neg) else float("inf"),
           "total_R": round(float(R.sum()), 2),
           "t_stat": round(float(R.mean() / (R.std(ddof=1) / np.sqrt(n))), 2) if n > 2 else 0.0,
           "max_dd_R": round(dd, 2),
           "worst_R": round(float(R.min()), 3), "best_R": round(float(R.max()), 3),
           "avg_hold_h": round(float(t["hold_min"].mean() / 60), 2), "max_hold_h": round(float(t["hold_min"].max() / 60), 2),
           "reasons": {k: int(v) for k, v in t["reason"].value_counts().items()}}
    return out


def by_year(t):
    out = {}
    for y, g in t.groupby(t.entry_time.dt.year):
        R = g["R"].to_numpy(float)
        neg = R[R < 0]
        out[int(y)] = {"n": int(len(R)), "total_R": round(float(R.sum()), 2), "exp_R": round(float(R.mean()), 4),
                       "avg_loss_R": round(float(neg.mean()), 4) if len(neg) else 0.0,
                       "win_rate": round(float((R > 0).mean()), 4)}
    return out


def server_time(ts):
    """UTC -> naive FP server time (New York + 7 h)."""
    return pd.DatetimeIndex(ts).tz_convert(NY).tz_localize(None) + pd.Timedelta(hours=7)


def ny_clock(dates, hh, mm):
    """UTC timestamps of New-York wall clock hh:mm on naive calendar dates."""
    loc = pd.DatetimeIndex(dates).normalize() + pd.Timedelta(hours=hh, minutes=mm)
    return loc.tz_localize(NY, ambiguous="NaT", nonexistent="shift_forward").tz_convert("UTC")


def friday_close_time(entry_ts):
    """Crypto: scheduled UTC time of the Friday 23:54 server bar of the server week of each entry (a calendar value)."""
    srv = server_time(entry_ts)
    fri = srv.normalize() + pd.to_timedelta(4 - srv.dayofweek, unit="D") + pd.Timedelta(hours=23, minutes=54)
    return (fri - pd.Timedelta(hours=7)).tz_localize(NY, ambiguous="NaT", nonexistent="shift_forward").tz_convert("UTC")


def friday_close_bar(m1, entry_ts):
    """Crypto: index of the last bar before the weekend closure of the server week of each entry (lab convention:
    the time exit is done at the open of the Friday 23:54 server bar; gl.exit_index moves it to the last bar before
    a closure when that bar is missing)."""
    return gl.exit_index(m1, friday_close_time(entry_ts))
