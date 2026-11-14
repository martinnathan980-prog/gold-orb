"""Gold daily-reopen drift (PROTOCOL_V3 Addendum K, round 5). Shared code. IN SAMPLE ONLY.

Every reading of a detail the frozen text leaves open is in results/r2/round5/gold_reopen/declared.json (D1..D18),
written before any run; the code below cites them.

D1: the gold frame is read with the parquet row filter ts < 2022-01-01 (load_is) and installed in goldlab.r2's frame
cache (install), so that r2.evaluate / r2.run / r2.null_test only ever see the in-sample slice. goldlab.r2.load is
wrapped: it raises instead of reading a file (r2.load reads the whole file, to 2025-12-31, before slicing) and checks
that every frame it returns ends before 2022-01-01.

Pipeline:
    m1 = load_is(); install(m1)
    ev = evening_table(m1, entry, hold_min, n_h1)       # one row per candidate evening, with its status (D2-D8)
    o  = make_orders(m1, **params)                      # the 'ok' evenings as goldlab.sim orders (r2's make_orders)
    r2.evaluate("xauusd", make_orders, params)          # FP costs, costs x1.5, gross, every signal (D10-D13)
"""
import datetime as dt
import hashlib
import json
import math
import os
import sys

os.environ.setdefault("NUMBA_CACHE_DIR", "/tmp/numba_gold_reopen")
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

LAB = "/home/user/gold-orb/lab"
if LAB not in sys.path:
    sys.path.insert(0, LAB)
_IDX = os.path.join(LAB, "r2", "tracks", "idx_us")
if _IDX not in sys.path:
    sys.path.append(_IDX)
import idxus_lib  # noqa: E402  NYSE rule calendar (imported read-only), base of the robot's gold calendar (D3)
import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
from goldlab.data import entry_index, exit_index  # noqa: E402
from goldlab.metrics import report  # noqa: E402

SYM = "xauusd"
CUT = pd.Timestamp("2022-01-01", tz="UTC")
CUT_NS = int(CUT.as_unit("ns").value)
NY = "America/New_York"
TRACK = "round5/gold_reopen"
OUT = os.path.join(LAB, "results", "r2", "round5", "gold_reopen")
FRAME = os.path.join(LAB, "data", "fp", f"{SYM}_m1.parquet")
COLS = ["bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"]
LAST_EVENING = pd.Timestamp("2021-12-30")       # D2: the last Thursday before the cut
NS_MIN = 60 * 10**9
NS_H = 60 * NS_MIN


# --------------------------------------------------------------------------------------------- data (D1)
def assert_is(df):
    """The frame holds nothing at or after 2022-01-01 00:00 UTC."""
    assert len(df) > 0
    assert df.index.max() < CUT, "a timestamp >= 2022-01-01 is held"
    assert df.index.is_monotonic_increasing and df.index.is_unique
    return df


def load_is():
    """In-sample FP gold frame (8 quote columns): rows with ts < 2022-01-01 00:00 UTC, filtered inside the read call."""
    df = pd.read_parquet(FRAME, filters=[("ts", "<", CUT)])
    df.index = df.index.as_unit("ns")
    assert list(df.columns) == COLS, list(df.columns)
    return assert_is(df)


_orig_load = r2.load


def _guarded_load(sym, start=None, end=None):
    if sym not in r2._fp_cache:
        raise RuntimeError(f"r2.load would read the whole file of {sym} (rows to 2025-12-31): refused (D1)")
    out = _orig_load(sym, start, end)
    assert len(out) == 0 or out.index.max() < CUT, "r2.load returned a timestamp >= 2022-01-01"
    return out


r2.load = _guarded_load


def install(df):
    """Put the in-sample slice in r2's frame cache (the only frame r2 may use)."""
    assert_is(df)
    r2.free()
    r2._fp_cache[SYM] = df
    check_held()


def check_held():
    """No frame held by r2 reaches 2022-01-01."""
    for k, v in r2._fp_cache.items():
        assert v.index.max() < CUT, f"r2 holds {k} rows >= 2022-01-01"


# --------------------------------------------------------------------------------------------- calendar (D2, D3)
NONE, LONG, SHORT, H1345 = 0, 1, 2, 3
KIND_NAME = {NONE: "none", LONG: "closure (day before 17:00 to 18:00)", SHORT: "early close 13:00",
             H1345: "early close 13:45"}
_KINDS = {}


def gold_kinds(y):
    """Gold holiday closure kind of every NYSE holiday / half day of year y: lab/robot/SPEC.md 2.1, as read by
    lab/robot/check/test_clock.py gold_kinds (built on idxus_lib.us_holidays). Dates absent from the dict are normal."""
    full, half = idxus_lib.us_holidays(y)
    gf = idxus_lib._easter(y) - dt.timedelta(days=2)
    xmas = idxus_lib._observed(dt.date(y, 12, 25))
    j1 = dt.date(y, 1, 1)
    nyo = j1 + dt.timedelta(days=1) if j1.weekday() == 6 else (j1 if j1.weekday() < 5 else None)
    out = {}
    for d in full:
        out[d] = LONG if d in (gf, xmas, nyo) else (NONE if d in idxus_lib.SPECIAL_CLOSURES else SHORT)
    tg = idxus_lib._nth(y, 11, 3, 4)
    for d in half:
        out[d] = H1345 if (d == tg + dt.timedelta(days=1) or (d.month == 12 and d.day == 24)) else NONE
    return out


def gold_kind(d):
    """Kind of a datetime.date (NONE for a normal gold day)."""
    if d.year not in _KINDS:
        _KINDS[d.year] = gold_kinds(d.year)
    return _KINDS[d.year].get(d, NONE)


def ny_utc_ns(dates, hhmm):
    """UTC epoch nanoseconds of the New York wall-clock time hhmm on each naive date (DST from the tz database)."""
    h, m = (int(x) for x in hhmm.split(":"))
    loc = (pd.DatetimeIndex(dates) + pd.Timedelta(hours=h, minutes=m)).tz_localize(NY)
    return loc.tz_convert("UTC").as_unit("ns").asi8


def candidate_evenings(m1):
    """D2: New York dates Monday-Thursday from the frame's first New York date to 2021-12-30."""
    first = m1.index[0].tz_convert(NY).tz_localize(None).normalize()
    last = min(m1.index[-1].tz_convert(NY).tz_localize(None).normalize(), LAST_EVENING)
    d = pd.date_range(first, last, freq="D").as_unit("ns")
    return d[d.dayofweek <= 3]


# --------------------------------------------------------------------------------------------- H1 range (D6)
def h1_bars(m1):
    """The lab's H1 bars (goldlab.data.bars, mid OHLC, UTC clock hours, empty hours absent): start ns and range."""
    b = gl.bars(m1, "1h")
    return b.index.as_unit("ns").asi8, (b["h"] - b["l"]).to_numpy(np.float64)


STATUS_ORDER = ["cal_holiday_evening", "cal_holiday_next_day", "no_quote_1800_entry", "no_entry_bar", "h1_lt_480",
                "exit_not_after_entry"]


def evening_table(m1, entry="18:15", hold_min=120, n_h1=480, h1=None):
    """One row per candidate evening with every quantity of D2-D8 and its status ('ok' or the first failed test in
    STATUS_ORDER). Causal: an evening's quantities use bars that start before its entry bar (the H1 window), the
    existence of bars before the entry (quote test) and the entry / exit bar positions."""
    assert m1.index.max() < CUT
    ins = m1.index.as_unit("ns").asi8
    N = len(ins)
    E = candidate_evenings(m1)
    nE = len(E)
    kind_e = np.array([gold_kind(d.date()) for d in E], dtype=np.int64)
    kind_n = np.array([gold_kind((d + pd.Timedelta(days=1)).date()) for d in E], dtype=np.int64)
    q_end = min(entry, "18:15")                                   # D4: [18:00, min(entry, 18:15)) New York
    q0, q1 = ny_utc_ns(E, "18:00"), ny_utc_ns(E, q_end)
    n_quotes = np.searchsorted(ins, q1, side="left") - np.searchsorted(ins, q0, side="left")
    t_target = ny_utc_ns(E, entry)                                # D5
    ei = np.searchsorted(ins, t_target, side="left").astype(np.int64)
    eic = np.minimum(ei, N - 1)
    s_end = ny_utc_ns(E + pd.Timedelta(days=1), "17:00")          # end of the trading day the reopen opens
    has_bar = (ei < N) & (ins[eic] < s_end)
    tau = np.where(has_bar, ins[eic], t_target)                   # entry bar start (the entry instant)
    hs, hr = h1_bars(m1) if h1 is None else h1                    # D6
    k = np.searchsorted(hs + NS_H, tau, side="right")             # completed H1 bars: start + 60 min <= entry bar start
    enough = k >= n_h1
    mean_rng = np.full(nE, np.nan)
    h1_first = np.full(nE, -1, np.int64)
    h1_last = np.full(nE, -1, np.int64)
    for j in np.flatnonzero(enough):
        mean_rng[j] = hr[k[j] - n_h1:k[j]].mean()
        h1_first[j] = hs[k[j] - n_h1]
        h1_last[j] = hs[k[j] - 1]
    t_exit = tau + int(hold_min) * NS_MIN                         # D8
    xi = exit_index(m1, pd.to_datetime(t_exit, unit="ns", utc=True)).astype(np.int64)
    xic = np.clip(xi, 0, N - 1)
    fails = {"cal_holiday_evening": kind_e != NONE, "cal_holiday_next_day": kind_n != NONE,
             "no_quote_1800_entry": n_quotes <= 0, "no_entry_bar": ~has_bar, "h1_lt_480": ~enough,
             "exit_not_after_entry": xi <= ei}
    status = np.full(nE, "ok", dtype=object)
    for name in reversed(STATUS_ORDER):                           # the first failed test in STATUS_ORDER wins
        status[fails[name]] = name
    to_ts = lambda v: pd.to_datetime(np.where(v >= 0, v, 0), unit="ns", utc=True)  # noqa: E731
    out = pd.DataFrame({
        "evening": E, "weekday": E.dayofweek, "kind_evening": kind_e, "kind_next_day": kind_n,
        "n_quotes_window": n_quotes, "t_target": to_ts(t_target), "entry_i": ei, "has_entry_bar": has_bar,
        "entry_bar": to_ts(np.where(has_bar, ins[eic], -1)), "entry_delay_min": (tau - t_target) / NS_MIN,
        "n_h1_completed": k, "h1_mean_range": mean_rng, "h1_first": to_ts(h1_first), "h1_last": to_ts(h1_last),
        "t_exit_sched": to_ts(t_exit), "exit_i": xi, "exit_bar": to_ts(ins[xic]),
        "exit_shift_min": (ins[xic] - t_exit) / NS_MIN, "status": status})
    for name, m in fails.items():
        out["fail_" + name] = m
    return out


def make_orders(m1, entry="18:15", hold_min=120, stop_k=2.0, n_h1=480, name=None):
    """r2's make_orders: the 'ok' evenings of evening_table as goldlab.sim market orders, long, stop_dist = stop_k x
    mean H1 range, time exit at exit_i (D5-D9). Built only from the frame it is given (r2.run's contract)."""
    ev = evening_table(m1, entry, hold_min, n_h1)
    ok = ev[ev.status == "ok"]
    summer = (ok.entry_bar.dt.tz_convert(NY).apply(lambda x: x.dst() != pd.Timedelta(0))).to_numpy(bool)
    o = pd.DataFrame({
        "entry_i": ok.entry_i.to_numpy(np.int64), "side": 1, "etype": 0,
        "stop_dist": float(stop_k) * ok.h1_mean_range.to_numpy(np.float64),
        "exit_i": ok.exit_i.to_numpy(np.int64),
        "evening": ok.evening.to_numpy(), "weekday": ok.weekday.to_numpy(np.int64),
        "t_target_utc": ok.t_target.dt.tz_convert(None).to_numpy(), "entry_delay_min": ok.entry_delay_min.to_numpy(),
        "h1_mean_range": ok.h1_mean_range.to_numpy(np.float64),
        "h1_first_utc": ok.h1_first.dt.tz_convert(None).to_numpy(), "h1_last_utc": ok.h1_last.dt.tz_convert(None).to_numpy(),
        "t_exit_sched_utc": ok.t_exit_sched.dt.tz_convert(None).to_numpy(), "exit_shift_min": ok.exit_shift_min.to_numpy(),
        "ny_summer_time": summer})
    assert (o.stop_dist > 0).all() and (o.exit_i > o.entry_i).all()
    return o


# --------------------------------------------------------------------------------------------- metrics
def _r(x, k=4):
    return None if x is None or not np.isfinite(x) else round(float(x), k)


def pf(x):
    x = np.asarray(x, float)
    g, l = x[x > 0].sum(), -x[x < 0].sum()
    return float(g / l) if l > 0 else float("inf")


def t_stat(x):
    x = np.asarray(x, float)
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def bp(t):
    """Mean result per trade in basis points of the entry fill (r2._bps)."""
    return float((t.pnl / t.entry).mean() * 1e4)


WD = {0: "Monday evening", 1: "Tuesday evening", 2: "Wednesday evening", 3: "Thursday evening"}


def summarize(t):
    """The lab's report plus the declared extras (D18)."""
    assert (t.entry_time < CUT).all() and (t.exit_time < CUT).all()
    out = dict(report(t))
    out["bp_net_per_trade"] = _r(bp(t), 3)
    out["mean_risk_bp"] = _r((t.risk / t.entry).mean() * 1e4, 2)
    out["median_risk_bp"] = _r((t.risk / t.entry).median() * 1e4, 2)
    out["mean_h1_range_usd"] = _r(t.h1_mean_range.mean(), 4)
    out["swap_total_usd_per_oz"] = _r(t.swap.sum(), 6)
    out["n_stop_exits"] = int((t.reason == "stop").sum())
    out["n_time_exits"] = int((t.reason == "time").sum())
    out["n_entry_delayed_over_0min"] = int((t.entry_delay_min > 0).sum())
    out["n_entry_delayed_over_5min"] = int((t.entry_delay_min > 5).sum())
    out["n_exit_moved_before_gap"] = int((t.exit_shift_min < -0.5).sum())
    out["max_hold_min"] = _r(t.hold_min.max(), 1)
    ov = t.entry_time.to_numpy()[1:] < t.exit_time.to_numpy()[:-1]
    out["overlapping_trades"] = int(ov.sum())
    yrs = t.groupby(t.entry_time.dt.year)
    out["by_year"] = {int(y): {"n": int(len(g)), "R": round(float(g.R.sum()), 2), "mean_R": _r(g.R.mean()),
                               "pf": _r(pf(g.R), 3), "bp_net": _r(bp(g), 3)} for y, g in yrs}
    out["by_weekday"] = {WD[int(w)]: {"n": int(len(g)), "mean_R": _r(g.R.mean()), "sum_R": round(float(g.R.sum()), 2),
                                      "pf": _r(pf(g.R), 3), "bp_net": _r(bp(g), 3)} for w, g in t.groupby("weekday")}
    out["by_ny_dst"] = {("summer time (EDT, entry 22:xx UTC)" if s else "winter time (EST, entry 23:xx UTC)"):
                        {"n": int(len(g)), "mean_R": _r(g.R.mean()), "sum_R": round(float(g.R.sum()), 2),
                         "pf": _r(pf(g.R), 3), "bp_net": _r(bp(g), 3)} for s, g in t.groupby("ny_summer_time")}
    return out


# --------------------------------------------------------------------------------------------- io
def _default(o):
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    return str(o)


def jdump(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, default=_default, ensure_ascii=False)


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def declared():
    """declared.json, after checking that it is byte for byte the file whose sha256 declare.py recorded."""
    p = os.path.join(OUT, "declared.json")
    rec = open(os.path.join(OUT, "declared.sha256")).read().split()[0]
    assert sha256(p) == rec, "declared.json changed after it was written"
    return json.load(open(p, encoding="utf-8")), rec


VAL_LOG = os.path.join(LAB, "results", "val_access.log")
