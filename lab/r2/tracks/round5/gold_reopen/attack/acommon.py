"""Independent re-implementation (the attack) of PROTOCOL_V3 Addendum K, gold daily-reopen drift. Shared code.

Written by the attacker from the frozen text, PROTOCOL_V2 section 4 and the lab's conventions only: it does not import
the engineer's code (../common.py and the other scripts of the track) and does not use goldlab's calendar, bars,
entry_index / exit_index or simulator. goldlab is imported nowhere in this file.

IN SAMPLE ONLY. The gold FP frame is read with the parquet row filter ts < 2022-01-01 00:00 UTC (load_is), and
every function that receives timestamps asserts that none is at or after that instant. Nothing of 2022 or later is read,
so nothing is written to results/val_access.log.

Units: prices in USD per troy ounce; R = multiples of the initial risk (entry fill - stop); bp = basis points of the
entry fill price; times in UTC unless "New York" (America/New_York, daylight saving from the tz database) is written.
"""
import datetime as dt
import json
import math
import os
import sys

sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

LAB = "/home/user/gold-orb/lab"
CUT = pd.Timestamp("2022-01-01", tz="UTC")
IS_START = pd.Timestamp("2013-01-01", tz="UTC")
NY = "America/New_York"
FRAME = os.path.join(LAB, "data", "fp", "xauusd_m1.parquet")
OUT = os.path.join(LAB, "results", "r2", "round5", "gold_reopen", "attack")
ENG = os.path.join(LAB, "results", "r2", "round5", "gold_reopen")
FP = json.load(open(os.path.join(LAB, "r2", "fp_costs.json")))["xauusd"]
SLIP_MKT = FP["slip_mkt_bps"] * 1e-4      # 0.3 bp of price per market fill (entry at a bar open, time exit)
SLIP_STOP = FP["slip_stop_bps"] * 1e-4    # 1.0 bp of price per stop fill
SWAP_LONG = FP["swap_long"]               # 5.5 % a year on longs, per 17:00 New York rollover (none is crossed here)
H1_N = 480

# Addendum K: the main configuration and its six neighbours (the frozen budget of seven)
CONFIGS = [
    {"id": 1, "name": "main", "entry": "18:15", "hold": 120, "k": 2.0},
    {"id": 2, "name": "n_entry_1810", "entry": "18:10", "hold": 120, "k": 2.0},
    {"id": 3, "name": "n_entry_1830", "entry": "18:30", "hold": 120, "k": 2.0},
    {"id": 4, "name": "n_hold_96", "entry": "18:15", "hold": 96, "k": 2.0},
    {"id": 5, "name": "n_hold_144", "entry": "18:15", "hold": 144, "k": 2.0},
    {"id": 6, "name": "n_stop_1.6", "entry": "18:15", "hold": 120, "k": 1.6},
    {"id": 7, "name": "n_stop_2.4", "entry": "18:15", "hold": 120, "k": 2.4},
]


def assert_is(ts):
    """Every timestamp held must be before 2022-01-01 00:00 UTC."""
    t = pd.DatetimeIndex(ts)
    assert len(t) == 0 or t.max() < CUT, "a timestamp at or after 2022-01-01 is held"


# ------------------------------------------------------------------------------------------------ data
def load_is():
    """In-sample gold FP M1 frame (bid/ask OHLC), rows with ts < 2022-01-01 00:00 UTC filtered in the read itself."""
    df = pd.read_parquet(FRAME, filters=[("ts", "<", CUT)])
    df.index = df.index.as_unit("ns")
    assert len(df) > 0 and df.index.is_monotonic_increasing and df.index.is_unique
    assert_is(df.index)
    assert list(df.columns) == ["bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"]
    return df


class Frame:
    """Plain numpy view of the frame for one cost scenario.
    spread_k scales the bid/ask half-spread around the mid of each field (1 = FP, 1.5 = stress, 0 = gross)."""

    def __init__(self, df, spread_k=1.0):
        self.ts = df.index.values.astype("datetime64[ns]").view("int64")      # UTC ns
        self.N = len(df)
        f = {c: df[c].to_numpy(np.float64) for c in df.columns}
        self.mid = {}
        for k in "ohlc":
            m = (f["b" + k] + f["a" + k]) / 2.0
            h = (f["a" + k] - f["b" + k]) / 2.0
            self.mid[k] = m
            setattr(self, "b" + k, m - spread_k * h)
            setattr(self, "a" + k, m + spread_k * h)
        self.spread_k = spread_k


def ns(t):
    return pd.Timestamp(t).value


# ------------------------------------------------------------------------------------------------ calendar (own)
def easter(y):
    """Gregorian Easter Sunday (anonymous algorithm)."""
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = (h + l_ - 7 * m + 114) % 31 + 1
    return dt.date(y, month, day)


def nth_weekday(y, month, wd, n):
    """n-th weekday wd (Monday = 0) of a month; n = -1 is the last one."""
    if n > 0:
        d = dt.date(y, month, 1)
        d += dt.timedelta(days=(wd - d.weekday()) % 7)
        return d + dt.timedelta(weeks=n - 1)
    nxt = dt.date(y + (month == 12), month % 12 + 1, 1)
    d = nxt - dt.timedelta(days=1)
    return d - dt.timedelta(days=(d.weekday() - wd) % 7)


def observed(d):
    """US rule: a holiday on Saturday is observed on Friday, on Sunday on Monday."""
    if d.weekday() == 5:
        return d - dt.timedelta(days=1)
    if d.weekday() == 6:
        return d + dt.timedelta(days=1)
    return d


def us_market_holidays(y):
    """US market (NYSE-rule) holidays of year y, observed dates -> name. New Year's Day on a Saturday is not observed
    on the Friday before (NYSE rule; 2022-01-01 -> 2021-12-31 stays a trading day)."""
    H = {}
    ny = dt.date(y, 1, 1)
    if ny.weekday() == 6:
        H[ny + dt.timedelta(days=1)] = "new_year"
    elif ny.weekday() < 5:
        H[ny] = "new_year"
    H[nth_weekday(y, 1, 0, 3)] = "martin_luther_king"
    H[nth_weekday(y, 2, 0, 3)] = "presidents"
    H[easter(y) - dt.timedelta(days=2)] = "good_friday"
    H[nth_weekday(y, 5, 0, -1)] = "memorial"
    H[observed(dt.date(y, 7, 4))] = "independence"
    H[nth_weekday(y, 9, 0, 1)] = "labor"
    H[nth_weekday(y, 11, 3, 4)] = "thanksgiving"
    H[observed(dt.date(y, 12, 25))] = "christmas"
    return H


def gold_calendar(y0=2012, y1=2022):
    """date -> (kind, name) for gold: 'closure' (no gold trading that day: New Year, Good Friday, Christmas) or
    'early' (the gold session of that day closes early: the other US market holidays, traded on the CME holiday
    schedule until about 13:00 New York, plus the day after Thanksgiving and a Monday-Thursday Christmas Eve, about
    13:45 New York). Checked against the frame's own close times in aprecheck.py."""
    cal = {}
    for y in range(y0, y1 + 1):
        for d, nm in us_market_holidays(y).items():
            cal[d] = ("closure" if nm in ("new_year", "good_friday", "christmas") else "early", nm)
        tg = nth_weekday(y, 11, 3, 4)
        cal[tg + dt.timedelta(days=1)] = ("early", "day_after_thanksgiving")
        ce = dt.date(y, 12, 24)
        if ce.weekday() < 4:
            cal[ce] = ("early", "christmas_eve")
    return cal


def next_weekday(d):
    d = d + dt.timedelta(days=1)
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d


def candidate_evenings(first=dt.date(2012, 12, 31), last=dt.date(2021, 12, 30)):
    """New York calendar dates Monday-Thursday (the evenings whose 18:00 reopen opens the trading days Tue-Fri)."""
    out, d = [], first
    while d <= last:
        if d.weekday() <= 3:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def holiday_skip(e, cal, reading="union"):
    """Addendum K 'skip US holiday closures and early closes'.
    'evening' : evening E is itself a closure / early-close day (its reopen ends a holiday closure or an early close);
    'session' : the trading day the reopen opens (next weekday) is a closure / early-close day;
    'union'   : either (no evening that either reading skips is traded)."""
    a = e in cal
    b = next_weekday(e) in cal
    return {"evening": a, "session": b, "union": a or b}[reading]


def ny_utc_ns(d, hhmm):
    """UTC ns of the New York wall-clock time hh:mm on date d (DST from the tz database)."""
    h, m = (int(x) for x in hhmm.split(":"))
    return pd.Timestamp(dt.datetime(d.year, d.month, d.day, h, m), tz=NY).tz_convert("UTC").value


# ------------------------------------------------------------------------------------------------ H1 bars (own)
class H1:
    """Clock-hour bars on the UTC grid (= New York and FP server grids, whole-hour offsets), built from the M1 rows
    that exist (an hour with no M1 row has no bar). Mid range = (max bid high + max ask high)/2 - (min bid low +
    min ask low)/2 (the lab's mid convention); bid range = max bid high - min bid low (MetaTrader chart convention,
    sensitivity only). Computed on the FP frame; the mid is the same in every cost scenario."""

    def __init__(self, fr):
        hour = fr.ts // 3_600_000_000_000
        starts = np.flatnonzero(np.r_[True, hour[1:] != hour[:-1]])
        self.start_ns = hour[starts] * 3_600_000_000_000
        bh, ah = np.maximum.reduceat(fr.bh, starts), np.maximum.reduceat(fr.ah, starts)
        bl, al = np.minimum.reduceat(fr.bl, starts), np.minimum.reduceat(fr.al, starts)
        self.rng_mid = (bh + ah) / 2.0 - (bl + al) / 2.0
        self.rng_bid = bh - bl
        self.n_m1 = np.diff(np.r_[starts, len(hour)])

    def mean_range(self, t_entry_ns, n=H1_N, kind="mid"):
        """Plain mean of (high - low) of the last n H1 bars completed at t_entry_ns (bar start + 60 min <= entry
        bar start), for each entry time. NaN when fewer than n completed bars exist. Also returns the start of the
        last bar used, to prove it ends at or before the entry."""
        r = self.rng_mid if kind == "mid" else self.rng_bid
        t = np.asarray(t_entry_ns, np.int64)
        cnt = np.searchsorted(self.start_ns, t - 3_600_000_000_000, side="right")
        out = np.full(len(t), np.nan)
        last = np.full(len(t), -1, np.int64)
        for j in range(len(t)):
            c = cnt[j]
            if c >= n:
                out[j] = r[c - n:c].mean()
                last[j] = self.start_ns[c - 1]
        return out, last


# ------------------------------------------------------------------------------------------------ sessions
def sessions(fr, h1, cfg, cal, reading="union", quote_end=None, range_kind="mid"):
    """One row per candidate evening with its status and, when tradable, its entry / exit bars and stop distance.
    quote_end: end of the quote test window (default: 18:15, or the entry time if it is earlier, so the test never
    uses a bar after the entry)."""
    if quote_end is None:
        quote_end = min("18:15", cfg["entry"])
    rows = []
    for e in candidate_evenings():
        r = {"evening": e, "weekday": e.strftime("%a"), "status": "ok"}
        q0, q1 = ny_utc_ns(e, "18:00"), ny_utc_ns(e, quote_end)
        te = ny_utc_ns(e, cfg["entry"])
        day_end = ny_utc_ns(next_weekday(e), "17:00")
        i_q0 = int(np.searchsorted(fr.ts, q0, side="left"))
        i_q1 = int(np.searchsorted(fr.ts, q1, side="left"))
        ei = int(np.searchsorted(fr.ts, te, side="left"))
        r.update(t_entry_target=te, n_quotes=i_q1 - i_q0, ei=ei)
        if holiday_skip(e, cal, reading):
            r["status"] = "holiday"
        elif i_q1 - i_q0 == 0:
            r["status"] = "no_quote_1800_1815"
        elif ei >= fr.N or fr.ts[ei] >= day_end:
            r["status"] = "no_entry_bar"
        rows.append(r)
    S = pd.DataFrame(rows)
    ok = S.status == "ok"
    ei = S.loc[ok, "ei"].to_numpy(np.int64)
    t_ent = fr.ts[ei]
    mr, last_h1 = h1.mean_range(t_ent, H1_N, range_kind)
    S["mean_h1_range"] = np.nan
    S["last_h1_start"] = -1
    S.loc[ok, "mean_h1_range"] = mr
    S.loc[ok, "last_h1_start"] = last_h1
    S.loc[ok & S.mean_h1_range.isna(), "status"] = "fewer_than_480_h1"
    ok = S.status == "ok"
    ei = S.loc[ok, "ei"].to_numpy(np.int64)
    t_ent = fr.ts[ei]
    tx = t_ent + int(cfg["hold"]) * 60_000_000_000
    xi = np.searchsorted(fr.ts, tx, side="left").astype(np.int64)
    S["xi"] = -1
    S.loc[ok, "xi"] = xi
    S["t_exit_target"] = -1
    S.loc[ok, "t_exit_target"] = tx
    bad = ok.copy()
    bad[ok] = xi >= fr.N
    S.loc[bad, "status"] = "exit_after_sample"
    ok = S.status == "ok"
    S["stop_dist"] = np.nan
    S.loc[ok, "stop_dist"] = cfg["k"] * S.loc[ok, "mean_h1_range"]
    # in sample: entry in [2013-01-01, 2022-01-01)
    pre = ok & (pd.Series(fr.ts[np.minimum(S.ei.to_numpy(), fr.N - 1)]) < IS_START.value).to_numpy()
    S.loc[pre, "status"] = "before_2013"
    return S


# ------------------------------------------------------------------------------------------------ simulator (own)
def simulate(fr, ei, xi, stop_dist, slip_mkt, slip_stop):
    """Long at the ask open of bar ei (+ market slippage); stop = entry fill - stop_dist, a resting sell stop on the
    bid from bar ei to bar xi - 1: filled at the stop, or at the bid open when a later bar opens below it, minus stop
    slippage; otherwise out at the bid open of bar xi minus market slippage. Returns a dict of arrays."""
    ei, xi = np.asarray(ei, np.int64), np.asarray(xi, np.int64)
    n = len(ei)
    entry = fr.ao[ei] * (1.0 + slip_mkt)
    stop = entry - np.asarray(stop_dist, float)
    assert (stop < fr.bo[ei]).all(), "a stop at or above the bid at entry"
    assert (xi > ei).all()
    L = int((xi - ei).max()) if n else 0
    win = ei[:, None] + np.arange(L)[None, :]
    inside = win < xi[:, None]
    winc = np.minimum(win, fr.N - 1)
    hit = (fr.bl[winc] <= stop[:, None]) & inside
    stopped = hit.any(axis=1)
    j = np.where(stopped, ei + hit.argmax(axis=1), xi)
    px_stop = np.where(j == ei, stop, np.minimum(stop, fr.bo[j]))
    exit_px = np.where(stopped, px_stop * (1.0 - slip_stop), fr.bo[xi] * (1.0 - slip_mkt))
    x_bar = np.where(stopped, j, xi)
    t_in = fr.ts[ei]
    t_out = np.where(stopped, fr.ts[j] + 60_000_000_000, fr.ts[xi])     # a stop exit is stamped at its bar's close
    risk = entry - stop
    pnl = exit_px - entry                                                # no 17:00 New York rollover is crossed
    return {"entry_i": ei, "exit_i": x_bar, "exit_i_sched": xi, "entry_time": t_in, "exit_time": t_out, "entry": entry, "stop": stop,
            "exit": exit_px, "reason": np.where(stopped, "stop", "time"), "risk": risk, "pnl": pnl, "R": pnl / risk}


def rollovers_crossed(t_in_ns, t_out_ns):
    """Number of 17:00 New York instants in (entry, exit] (the FP server midnight, where the swap is charged)."""
    a = pd.DatetimeIndex(t_in_ns.astype("datetime64[ns]"), tz="UTC").tz_convert(NY).tz_localize(None)
    b = pd.DatetimeIndex((t_out_ns - 1).astype("datetime64[ns]"), tz="UTC").tz_convert(NY).tz_localize(None)
    da = (a - pd.Timedelta(hours=17)).normalize()          # New York wall clock: a trading day starts at 17:00
    db = (b - pd.Timedelta(hours=17)).normalize()
    return (db - da).days.to_numpy()


SCEN = {"fp": (1.0, SLIP_MKT, SLIP_STOP), "x1.5": (1.5, 1.5 * SLIP_MKT, 1.5 * SLIP_STOP), "gross": (0.0, 0.0, 0.0)}


def run_config(df, cfg, cal, scen="fp", reading="union", quote_end=None, range_kind="mid", fr_cache=None, h1=None):
    """Sessions of cfg (built on the FP frame: the mid and so the stop distance are the same in every scenario) and
    their trades in scenario scen. Returns (trades DataFrame, sessions DataFrame)."""
    fr_cache = {} if fr_cache is None else fr_cache
    if "fp" not in fr_cache:
        fr_cache["fp"] = Frame(df, 1.0)
    fr0 = fr_cache["fp"]
    h1 = H1(fr0) if h1 is None else h1
    S = sessions(fr0, h1, cfg, cal, reading, quote_end, range_kind)
    ok = S[S.status == "ok"]
    k, sm, ss = SCEN[scen]
    if scen not in fr_cache:
        fr_cache[scen] = Frame(df, k)
    fr = fr_cache[scen]
    r = simulate(fr, ok.ei.to_numpy(), ok.xi.to_numpy(), ok.stop_dist.to_numpy(), sm, ss)
    t = pd.DataFrame(r)
    t["evening"] = ok.evening.to_numpy()
    t["mean_h1_range"] = ok.mean_h1_range.to_numpy()
    t["stop_dist"] = ok.stop_dist.to_numpy()
    t["t_entry_target"] = ok.t_entry_target.to_numpy()
    t["t_exit_target"] = ok.t_exit_target.to_numpy()
    t["last_h1_start"] = ok.last_h1_start.to_numpy()
    for c in ("entry_time", "exit_time", "t_entry_target", "t_exit_target", "last_h1_start"):
        t[c] = pd.to_datetime(t[c].to_numpy(np.int64), utc=True)
    assert_is(t.entry_time)
    assert_is(t.exit_time)
    assert (t.entry_time >= IS_START).all()
    nights = rollovers_crossed(r["entry_time"], r["exit_time"])
    assert (nights == 0).all(), "a trade crosses a 17:00 New York rollover (swap would not be zero)"
    t["swap"] = 0.0
    t["hold_min"] = (t.exit_time - t.entry_time).dt.total_seconds() / 60.0
    t["entry_delay_min"] = (t.entry_time - t.t_entry_target).dt.total_seconds() / 60.0
    t["exit_delay_min"] = np.where(t.reason == "time", (t.exit_time - t.t_exit_target).dt.total_seconds() / 60.0, np.nan)
    return t, S


# ------------------------------------------------------------------------------------------------ metrics (own)
def pf(x):
    x = np.asarray(x, float)
    g, l_ = x[x > 0].sum(), -x[x < 0].sum()
    return float(g / l_) if l_ > 0 else float("inf")


def tstat(x):
    x = np.asarray(x, float)
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def metrics(t):
    R = t.R.to_numpy(float)
    yr = t.entry_time.dt.year
    by = t.groupby(yr).R.sum()
    out = {"n": int(len(R)), "pf": round(pf(R), 4), "t": round(tstat(R), 3), "expectancy_R": round(float(R.mean()), 5),
           "total_R": round(float(R.sum()), 2), "win_rate": round(float((R > 0).mean()), 4),
           "years_pos": f"{int((by > 0).sum())}/{len(by)}", "per_year_R": {int(k): round(float(v), 2) for k, v in by.items()},
           "max_hold_min": round(float(t.hold_min.max()), 1),
           "net_bp_mean": round(float((t.pnl / t.entry).mean() * 1e4), 3),
           "mean_stop_bp": round(float((t.risk / t.entry).mean() * 1e4), 2),
           "n_stop": int((t.reason == "stop").sum()),
           "n_entry_delayed": int((t.entry_delay_min > 0).sum()),
           "n_entry_delayed_over_5min": int((t.entry_delay_min > 5).sum()),
           "n_exit_bar_late_over_30min": int((t.exit_delay_min > 30).sum()),
           "first_entry": str(t.entry_time.min()), "last_exit": str(t.exit_time.max())}
    return out


def overlaps(t):
    a = t.sort_values("entry_time")
    return int((a.entry_time.to_numpy()[1:] < a.exit_time.to_numpy()[:-1]).sum())


# ------------------------------------------------------------------------------------------------ random-time null (own)
def swap_nights(t_in_ns, t_out_ns):
    """FP swap nights between entry and exit: server midnights (17:00 New York; server = New York + 7 h) crossed, the
    Wednesday one counted three times (fp_costs.json swap_triple 'Wed')."""
    a = (pd.DatetimeIndex(np.asarray(t_in_ns).astype("datetime64[ns]"), tz="UTC").tz_convert(NY).tz_localize(None)
         + pd.Timedelta(hours=7)).normalize().values.astype("datetime64[D]")
    b = (pd.DatetimeIndex((np.asarray(t_out_ns) - 1).astype("datetime64[ns]"), tz="UTC").tz_convert(NY).tz_localize(None)
         + pd.Timedelta(hours=7)).normalize().values.astype("datetime64[D]")
    return np.busday_count(a, b) + 2 * np.busday_count(a, b, weekmask=FP["swap_triple"])


def null_random_time(fr, t, n_rep=200, seed=20261114, duration="clock", hold_min=120, swap=True, one_position=False):
    """Re-enter each filled trade of the rule (FP costs) at market at the open of a uniformly drawn M1 bar of the
    in-sample period, long, with the same stop distance as a fraction of the price (applied to the drawn bar's mid
    open) and the same time exit: duration 'clock' = first bar at or after entry + hold_min minutes (the rule's own
    exit), duration 'bars' = the same number of M1 bars as the rule's trade (the lab's r2.null_test convention).
    Replays are independent unless one_position=True (then, in time order, a replay entering while an earlier one is
    open is dropped, as r2.null_test does); replays whose exit bar would fall after the slice are redrawn. FP costs:
    spread and slippage as the rule, and with swap=True the long swap of fp_costs.json for every 17:00 New York
    rollover a replay crosses (the Wednesday one x3) - the rule's own trades never cross one. The first attack run
    (arun.py, attack_results.json 'null_clock' / 'null_bars') was made before the swap was added: superseded by anull.py.
    Statistic: mean R per trade; percentile = share of replay means strictly below the rule's mean R."""
    rng = np.random.default_rng(seed)
    n = len(t)
    stop_rel = (t.risk / t.entry).to_numpy(float)
    nbars = (t.exit_i_sched.to_numpy(np.int64) - t.entry_i.to_numpy(np.int64)) if duration == "bars" else None
    lo = int(np.searchsorted(fr.ts, IS_START.value, side="left"))
    hi = fr.N
    means = np.empty(n_rep)
    for k in range(n_rep):
        ei = rng.integers(lo, hi, n)
        if duration == "clock":
            xi = np.searchsorted(fr.ts, fr.ts[ei] + hold_min * 60_000_000_000, side="left")
        else:
            xi = ei + nbars
        bad = xi >= hi
        while bad.any():
            ei[bad] = rng.integers(lo, hi, int(bad.sum()))
            xi[bad] = (np.searchsorted(fr.ts, fr.ts[ei[bad]] + hold_min * 60_000_000_000, side="left")
                       if duration == "clock" else ei[bad] + nbars[bad])
            bad = xi >= hi
        sd = stop_rel * fr.mid["o"][ei]
        r = simulate(fr, ei, xi, sd, SLIP_MKT, SLIP_STOP)
        R = r["R"]
        if swap:                                    # a replay crossing the 17:00 New York rollover pays the long swap
            nights = swap_nights(r["entry_time"], r["exit_time"])
            R = (r["pnl"] - r["entry"] * SWAP_LONG / 360.0 * nights) / r["risk"]
        if one_position:                            # one position at a time, replays in time order (as r2.null_test)
            o = np.argsort(ei, kind="stable")
            keep, last = np.zeros(n, bool), -1
            for q in o:
                if ei[q] > last:
                    keep[q] = True
                    last = r["exit_i"][q]
            R = R[keep]
        means[k] = float(np.mean(R))
    cand = float(t.R.mean())
    return {"replays": int(n_rep), "seed": int(seed), "duration": duration, "swap_charged": bool(swap),
            "one_position_at_a_time": bool(one_position), "rule_mean_R": round(cand, 5),
            "null_mean_R": round(float(means.mean()), 5), "null_sd_R": round(float(means.std(ddof=1)), 5),
            "null_p50_R": round(float(np.percentile(means, 50)), 5), "null_p975_R": round(float(np.percentile(means, 97.5)), 5),
            "null_max_R": round(float(means.max()), 5),
            "percentile": round(float((means < cand).mean() * 100), 1), "pass": bool((means < cand).mean() >= 0.975)}, means


# ------------------------------------------------------------------------------------------------ correlation (own)
TEN = [("noise30", "us100"), ("ocm4", "us100"), ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"),
       ("F1_brk_ridge_filter", "btcusd"), ("F1_brk_ridge_filter", "ethusd"), ("nq_btc_follow", "btcusd"),
       ("GOLD_FRI_PM", "xauusd"), ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd")]
WEEKS = pd.period_range(pd.Timestamp("2014-01-01").to_period("W"), pd.Timestamp("2021-12-31").to_period("W"), freq="W")


def official(name, sym):
    """Official trades of one of the ten, read with the filter entry_time < 2022-01-01 in the read; exits in 2022 dropped."""
    t = pd.read_parquet(os.path.join(LAB, "results", "r2", "recalc", "trades", f"{name}__{sym}.parquet"),
                        columns=["entry_time", "exit_time", "R"], filters=[("entry_time", "<", CUT)])
    assert_is(t.entry_time)
    t = t[t.exit_time < CUT]
    assert_is(t.exit_time)
    return t


def weekly(t):
    """Weekly sums of R by exit week (W-SUN periods of the UTC exit time), every week of 2014-2021 (0 if no exit)."""
    w = t.groupby(t.exit_time.dt.tz_convert("UTC").dt.tz_localize(None).dt.to_period("W-SUN"))["R"].sum()
    return w.reindex(WEEKS, fill_value=0.0)


def corr_with_ten(t):
    ws = {f"{n}:{s}": weekly(official(n, s)) for n, s in TEN}
    ten = sum(ws.values())
    w = weekly(t)
    rho = float(np.corrcoef(w.to_numpy(), ten.to_numpy())[0, 1])
    each = {k: round(float(np.corrcoef(w.to_numpy(), v.to_numpy())[0, 1]), 4) for k, v in ws.items()}
    return {"rho": round(rho, 4), "n_weeks": int(len(WEEKS)), "first_week": str(WEEKS[0]), "last_week": str(WEEKS[-1]),
            "weeks_with_an_exit": int((w != 0).sum()), "each_sleeve": each}


def jdump(obj, path):
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=str, ensure_ascii=False)
