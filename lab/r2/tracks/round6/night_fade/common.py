"""Night mean reversion on FX crosses (PROTOCOL_V3 Addendum L, round 6, rule 'night_fade'). Shared code. IN SAMPLE ONLY.

Every reading of a detail that Addendum L leaves open is written in declare.py (READINGS L1..L34) and goes into
results/r2/round6/night_fade/declared.json, with the sha256 of every code file, before any return is computed; the code
below cites the readings by number.

Pipeline (one cross at a time; nothing of 2022 or later is ever held):
    m1 = load_base(cross)                         # merged Dukascopy bid/ask + commission folded in (L1, L2)
    bk = Book(m1, cross)                          # the frame the orders are built on, with its cached bars (L6, L7)
    orders, table = make_orders(bk, params)       # decisions, signals, filter, entry checks (L3-L15, L21-L25)
    t = run_orders(bk, orders, costs(params))     # goldlab.sim.simulate, one position per cross, checks (L15-L17)
goldlab.r2's loaders and runners are never used: they read whole files (rows to 2025) and have no cost entry for crosses.
"""
import datetime as dt
import hashlib
import json
import math
import os
import sys

os.environ.setdefault("NUMBA_CACHE_DIR",
                      "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/round6_build/numba")
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

LAB = "/home/user/gold-orb/lab"
if LAB not in sys.path:
    sys.path.insert(0, LAB)
_IDX = os.path.join(LAB, "r2", "tracks", "idx_us")
if _IDX not in sys.path:
    sys.path.append(_IDX)
import dl_round6  # noqa: E402  the twelve crosses, fixed before the research
import idxus_lib  # noqa: E402  NYSE rule calendar (read-only import): us_holidays, SPECIAL_CLOSURES
import goldlab as gl  # noqa: E402
from goldlab.data import exit_index, trading_day  # noqa: E402
from goldlab.sim import Costs, apply_spread_mult, simulate  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TRACK = "round6/night_fade"
OUT = os.path.join(LAB, "results", "r2", "round6", "night_fade")
R6 = os.path.join(LAB, "data", "r6")
RAW6 = os.path.join(LAB, "data", "raw_r6")
VAL_LOG = os.path.join(LAB, "results", "val_access.log")
CUT = pd.Timestamp("2022-01-01", tz="UTC")
CUT_NS = int(CUT.as_unit("ns").value)
NY = "America/New_York"
NS_MIN = 60 * 10**9
NS_H = 60 * NS_MIN
COLS = ["bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"]
YEARS = list(range(2013, 2022))
PIP = 1e-4                                            # one pip = 0.0001 for all twelve crosses

CROSSES = list(dl_round6.CROSSES)                     # basket order (dl_round6.py)
assert CROSSES == ["eurcad", "gbpcad", "euraud", "audcad", "eurgbp", "eurchf", "gbpchf", "audnzd", "nzdcad", "cadchf",
                   "gbpaud", "eurnzd"]
# FP Markets Raw commission, 6 USD per 100,000 units of base round trip, at fixed low-end USD values of the base
# (EUR 1.05, GBP 1.20, AUD 0.65, NZD 0.60, CAD 0.70), in bp of price, exactly as listed in Addendum L (L2)
COMM_BP = {"eurcad": 0.5714, "gbpcad": 0.5000, "euraud": 0.5714, "audcad": 0.9231, "eurgbp": 0.5714, "eurchf": 0.5714,
           "gbpchf": 0.5000, "audnzd": 0.9231, "nzdcad": 1.0000, "cadchf": 0.8571, "gbpaud": 0.5000, "eurnzd": 0.5714}
BASE = {c: c[:3].upper() for c in CROSSES}
QUOTE = {c: c[3:].upper() for c in CROSSES}
AUD_NZD = [c for c in CROSSES if "aud" in c or "nzd" in c]          # the six AUD and NZD crosses (reported apart)
OTHER_SIX = [c for c in CROSSES if c not in AUD_NZD]

# --------------------------------------------------------------------------------------------- configurations
MAIN = {"name": "main", "bar_minutes": 5, "band_period": 20, "band_k": 2.0, "band_ddof": 0, "band_span_max_min": 120,
        "decision_first_ny": "17:15", "decision_last_ny": "19:55", "n_decisions_per_evening": 33,
        "cost_filter_mult": 2.0, "entry_max_delay_min": 5, "refuse_if_open_reached_target": True,
        "target_mode": "frozen_middle_band", "stop_h1_multiple": 2.0, "h1_bars": 480, "time_exit_ny": "21:00",
        "exit_gap_max_min": 30, "one_position_per_cross": True, "max_trades_per_cross_per_evening": None,
        "slip_mkt_bps": 0.1, "slip_stop_bps": 0.3}


def _cfg(i, name, role, **chg):
    p = dict(MAIN)
    p.update(chg)
    p["name"] = name
    return {"id": i, "name": name, "role": role, "change_from_main": chg, "params": p}


CONFIGS = [
    _cfg(1, "main", "verdict (the only configuration judged)"),
    _cfg(2, "first_hour", "neighbour (1): decisions 17:15-17:55 only", decision_last_ny="17:55", n_decisions_per_evening=9),
    _cfg(3, "moving_mid", "neighbour (2): no resting target; market exit after the first M5 close back at its own "
         "middle band", target_mode="moving_middle_band"),
    _cfg(4, "width_2.5", "neighbour (3): bands +/- 2.5 sigma", band_k=2.5),
    _cfg(5, "m15", "neighbour (4): M15 bars, span limit 360 minutes, decisions 17:15-19:45", bar_minutes=15,
         band_span_max_min=360, decision_last_ny="19:45", n_decisions_per_evening=11),
    _cfg(6, "stop_3.0", "neighbour (5): stop 3.0 x the mean H1 range", stop_h1_multiple=3.0),
    _cfg(7, "one_per_night", "neighbour (6): only the first order of each cross and evening",
         max_trades_per_cross_per_evening=1),
]
CONFIG = {c["name"]: c for c in CONFIGS}


def n_decisions(p):
    """Number of decision times from decision_first_ny to decision_last_ny every bar_minutes (L8)."""
    h0, m0 = (int(x) for x in p["decision_first_ny"].split(":"))
    h1, m1 = (int(x) for x in p["decision_last_ny"].split(":"))
    span = (h1 * 60 + m1) - (h0 * 60 + m0)
    assert span % p["bar_minutes"] == 0
    return span // p["bar_minutes"] + 1


for _c in CONFIGS:
    assert n_decisions(_c["params"]) == _c["params"]["n_decisions_per_evening"], _c["name"]


# --------------------------------------------------------------------------------------------- data (L1, L2)
def assert_is(df):
    """The frame holds nothing at or after 2022-01-01 00:00 UTC (and is a clean M1 frame)."""
    assert len(df) > 0
    assert df.index.max() < CUT, "a timestamp >= 2022-01-01 is held"
    assert df.index.is_monotonic_increasing and df.index.is_unique
    assert list(df.columns) == COLS, list(df.columns)
    return df


def frame_path(cross):
    return os.path.join(R6, f"{cross}_m1.parquet")


def load_merged(cross):
    """Merged Dukascopy bid/ask frame of a cross (frames.py): rows with ts < 2022-01-01 00:00 UTC, filtered inside the
    read call (parquet row filter), index in nanoseconds (L1)."""
    assert cross in CROSSES, cross
    df = pd.read_parquet(frame_path(cross), filters=[("ts", "<", CUT)])
    df.index = df.index.as_unit("ns")
    return assert_is(df)


def fold_commission(m, cross):
    """Base frame of Addendum L: bid - h and ask + h on all four prices, h = 0.5 x c x 1e-4 x the bar's mid close
    (before folding), c = COMM_BP[cross] (L2). Mid prices are unchanged (up to the last bit)."""
    h = 0.5 * COMM_BP[cross] * 1e-4 * ((m["bc"] + m["ac"]) / 2)
    out = pd.DataFrame(index=m.index)
    for k in ("bo", "bh", "bl", "bc"):
        out[k] = m[k] - h
    for k in ("ao", "ah", "al", "ac"):
        out[k] = m[k] + h
    return out[COLS]


def load_base(cross):
    """The base frame (L1, L2): the in-sample merged frame with the commission folded into the quotes."""
    return assert_is(fold_commission(load_merged(cross), cross))


# --------------------------------------------------------------------------------------------- calendar (L3, L4)
def full_holidays(y):
    """NYSE full holidays of year y used by Addendum L: idxus_lib.us_holidays minus SPECIAL_CLOSURES (half days normal)."""
    full, _half = idxus_lib.us_holidays(y)
    return set(full) - set(idxus_lib.SPECIAL_CLOSURES)


_HOL = {}


def is_full_holiday(d):
    if d.year not in _HOL:
        _HOL[d.year] = full_holidays(d.year)
    return d in _HOL[d.year]


CAL_REASONS = ["christmas_new_year", "holiday_on_E", "holiday_on_E_plus_1"]


def calendar():
    """Every Monday-Thursday New York date E from 2013-01-01 to 2021-12-30 with its calendar status (L3): 'ok' or the
    first of CAL_REASONS that applies (E from 24 December to 1 January; E an NYSE full holiday; E+1 one)."""
    d = pd.date_range("2013-01-01", "2021-12-30", freq="D").as_unit("ns")
    d = d[d.dayofweek <= 3]
    st = []
    for x in d:
        e = x.date()
        if (e.month == 12 and e.day >= 24) or (e.month == 1 and e.day == 1):
            st.append("christmas_new_year")
        elif is_full_holiday(e):
            st.append("holiday_on_E")
        elif is_full_holiday(e + dt.timedelta(days=1)):
            st.append("holiday_on_E_plus_1")
        else:
            st.append("ok")
    return pd.DataFrame({"evening": d, "weekday": d.dayofweek, "status": st})


_EV = None


def evenings():
    """The 1,753 calendar evenings of Addendum L (naive New York dates, 2013-01-02 .. 2021-12-22)."""
    global _EV
    if _EV is None:
        c = calendar()
        _EV = pd.DatetimeIndex(c.evening[c.status == "ok"].to_numpy()).as_unit("ns")
        assert len(_EV) == 1753 and str(_EV[0].date()) == "2013-01-02" and str(_EV[-1].date()) == "2021-12-22"
    return _EV


def ny_utc_ns(dates, hhmm):
    """UTC epoch nanoseconds of the New York wall-clock time hhmm on each naive date (tz database). Evenings are
    Monday-Thursday, so no time used here falls in a daylight-saving switch (they happen at 02:00 on Sundays)."""
    h, m = (int(x) for x in hhmm.split(":"))
    loc = (pd.DatetimeIndex(dates) + pd.Timedelta(hours=h, minutes=m)).tz_localize(NY)
    return loc.tz_convert("UTC").as_unit("ns").asi8


def ny_summer(ts_utc):
    """True where the New York clock is on daylight-saving time (EDT) at these UTC instants."""
    loc = pd.DatetimeIndex(ts_utc).tz_convert(NY)
    off = np.array([x.utcoffset().total_seconds() for x in loc]) if len(loc) else np.zeros(0)
    return off == -4 * 3600


# --------------------------------------------------------------------------------------------- windows (L7, L13)
def window_mean_std(x, n):
    """Mean and population standard deviation (ddof 0) of the n values ending at each position j (NaN for j < n-1).
    Each sum runs over its own n values in a fixed sequential order (vector adds over the window offset), so a value
    depends only on its n inputs, never on the length of the series (truncation test, hand check)."""
    x = np.ascontiguousarray(x, dtype=np.float64)
    mu = np.full(len(x), np.nan)
    sd = np.full(len(x), np.nan)
    m = len(x) - n + 1
    if m <= 0:
        return mu, sd
    s = np.zeros(m)
    for j in range(n):
        s += x[j:j + m]
    mean = s / n
    v = np.zeros(m)
    for j in range(n):
        d = x[j:j + m] - mean
        v += d * d
    mu[n - 1:] = mean
    sd[n - 1:] = np.sqrt(v / n)
    return mu, sd


def window_mean(x, n):
    """Mean of the n values ending at each position j (NaN for j < n-1), summed sequentially as in window_mean_std."""
    x = np.ascontiguousarray(x, dtype=np.float64)
    out = np.full(len(x), np.nan)
    m = len(x) - n + 1
    if m <= 0:
        return out
    s = np.zeros(m)
    for j in range(n):
        s += x[j:j + m]
    out[n - 1:] = s / n
    return out


# --------------------------------------------------------------------------------------------- the frame (L6)
class Book:
    """One M1 frame of one cross (the frame the orders are built on: base, or base x1.5 for reading a) with its cached
    signal bars, bands and H1 ranges. Every quantity is computed from this frame only."""

    def __init__(self, m1, cross):
        assert_is(m1)
        self.m1 = m1
        self.cross = cross
        self.ns = m1.index.as_unit("ns").asi8
        self.ao = m1["ao"].to_numpy(np.float64)
        self.bo = m1["bo"].to_numpy(np.float64)
        self._sb = {}
        self._h1 = {}
        self._x = {}

    def bars(self, minutes, period=20, span_max_min=120):
        """Signal bars (L6, L7): goldlab.data.bars(frame, '<minutes>min') on the UTC clock grid (whole-hour New York
        offsets: the same grid), empty buckets absent; mid close of the bucket's last M1 bar; end = start + minutes;
        C = ask close - bid close of the bucket's last M1 bar; band mean and population sd of the bar and the
        period - 1 existing bars before it; usable if bar j - (period - 1) starts at most span_max_min before bar j ends."""
        key = (int(minutes), int(period), int(span_max_min))
        if key not in self._sb:
            b = gl.bars(self.m1, f"{int(minutes)}min")
            start = b.index.as_unit("ns").asi8
            close = b["c"].to_numpy(np.float64)
            C = (b["ac"] - b["bc"]).to_numpy(np.float64)
            mu, sd = window_mean_std(close, int(period))
            end = start + int(minutes) * NS_MIN
            usable = np.zeros(len(start), bool)
            q = int(period) - 1
            if len(start) > q:
                usable[q:] = (end[q:] - start[:len(start) - q]) <= int(span_max_min) * NS_MIN
            usable &= np.isfinite(mu)
            self._sb[key] = {"start": start, "end": end, "close": close, "C": C, "mu": mu, "sd": sd, "usable": usable,
                             "minutes": int(minutes)}
        return self._sb[key]

    def h1(self, n=480):
        """H1 bars (L13): goldlab.data.bars(frame, '1h'), range = mid high - mid low, end = start + 60 min, and the mean
        range of the n bars ending at each bar."""
        if n not in self._h1:
            b = gl.bars(self.m1, "1h")
            start = b.index.as_unit("ns").asi8
            rng = (b["h"] - b["l"]).to_numpy(np.float64)
            self._h1[n] = {"start": start, "end": start + NS_H, "rng": rng, "mean": window_mean(rng, n)}
        return self._h1[n]

    def h1_at(self, t_ns, n=480):
        """Number of completed H1 bars at each instant (start + 60 min <= t) and the mean range of the n most recent
        (NaN with fewer than n)."""
        h = self.h1(n)
        k = np.searchsorted(h["end"], np.asarray(t_ns, np.int64), side="right")
        mean = np.where(k >= n, h["mean"][np.maximum(k - 1, 0)], np.nan) if len(h["end"]) else np.full(len(k), np.nan)
        return k, mean

    def tradable(self, n=480, ev=None):
        """Calendar evenings on which this cross has at least n completed H1 bars at 17:15 New York (L4)."""
        E = evenings() if ev is None else pd.DatetimeIndex(ev)
        k, _ = self.h1_at(ny_utc_ns(E, "17:15"), n)
        return E[k >= n]

    def exit_at(self, E, hhmm="21:00", gap=30):
        """M1 index of the time exit at hhmm New York of each evening: goldlab.data.exit_index (first bar at or after,
        or the last bar before a gap of more than `gap` minutes) (L14)."""
        key = (hashlib.sha1(pd.DatetimeIndex(E).as_unit("ns").asi8.tobytes()).hexdigest(), hhmm, gap)
        if key not in self._x:
            if len(E) == 0:
                self._x[key] = np.zeros(0, np.int64)
            else:
                t = pd.to_datetime(ny_utc_ns(E, hhmm), unit="ns", utc=True)
                self._x[key] = exit_index(self.m1, t, max_gap_min=gap).astype(np.int64)
        return self._x[key]


# --------------------------------------------------------------------------------------------- decisions (L8-L15, L25)
ST_ORDER, ST_NO_BAR, ST_BAND, ST_INSIDE, ST_COST, ST_LATE, ST_TARGET, ST_STOP0, ST_EXIT, ST_NOT_FIRST = range(10)
STATUS = {ST_ORDER: "order", ST_NO_BAR: "no_signal_bar", ST_BAND: "band_not_usable", ST_INSIDE: "no_band_crossing",
          ST_COST: "cost_filter", ST_LATE: "entry_late_over_5min", ST_TARGET: "open_already_at_target",
          ST_STOP0: "stop_distance_le_0", ST_EXIT: "exit_bar_not_after_entry_bar",
          ST_NOT_FIRST: "not_first_order_of_evening"}


def decision_table(bk, p, ev=None):
    """One row per (tradable evening, decision time) of configuration p on the frame of bk, with every quantity of the
    order and its status: 'order' or the first failed test in the order of STATUS (L25)."""
    m = int(p["bar_minutes"])
    K = n_decisions(p)
    n_h1 = int(p["h1_bars"])
    sb = bk.bars(m, int(p["band_period"]), int(p["band_span_max_min"]))
    E = bk.tradable(n_h1) if ev is None else pd.DatetimeIndex(ev)
    nE = len(E)
    t0 = ny_utc_ns(E, p["decision_first_ny"]) if nE else np.zeros(0, np.int64)
    t = (t0[:, None] + np.arange(K, dtype=np.int64)[None, :] * (m * NS_MIN)).ravel()
    e_idx = np.repeat(np.arange(nE), K)
    k_idx = np.tile(np.arange(K), nE)
    n = len(t)
    nb = len(sb["start"])
    bstart = t - m * NS_MIN                                     # the bucket that ends at the decision time (L8)
    j = np.searchsorted(sb["start"], bstart, side="left")
    jc = np.minimum(j, max(nb - 1, 0))
    has_bar = (j < nb) & (sb["start"][jc] == bstart) if nb else np.zeros(n, bool)
    usable = has_bar & sb["usable"][jc] if nb else np.zeros(n, bool)
    mu = np.where(usable, sb["mu"][jc], np.nan) if nb else np.full(n, np.nan)
    sd = np.where(usable, sb["sd"][jc], np.nan) if nb else np.full(n, np.nan)
    close = np.where(has_bar, sb["close"][jc], np.nan) if nb else np.full(n, np.nan)
    C = np.where(has_bar, sb["C"][jc], np.nan) if nb else np.full(n, np.nan)
    kb = float(p["band_k"])
    lower, upper = mu - kb * sd, mu + kb * sd
    side = np.zeros(n, np.int64)                                # strict crossings (L9)
    side[usable & (close < lower)] = 1
    side[usable & (close > upper)] = -1
    D = np.abs(close - mu)
    passes = D >= float(p["cost_filter_mult"]) * C              # equality kept (L10)
    N = len(bk.ns)
    ei = np.searchsorted(bk.ns, t, side="left").astype(np.int64)  # goldlab.data.entry_index (L11)
    eic = np.minimum(ei, N - 1)
    has_e = ei < N
    delay = np.where(has_e, bk.ns[eic] - t, np.iinfo(np.int64).max)
    late = ~has_e | (delay > int(p["entry_max_delay_min"]) * NS_MIN)
    if p.get("refuse_if_open_reached_target", True):
        reached = ((side > 0) & (bk.ao[eic] >= mu)) | ((side < 0) & (bk.bo[eic] <= mu))
    else:
        reached = np.zeros(n, bool)
    kh, mean_rng = bk.h1_at(t, n_h1)                            # completed = start + 60 min <= decision time (L13)
    stop_dist = float(p["stop_h1_multiple"]) * mean_rng
    x21 = bk.exit_at(E, p["time_exit_ny"], int(p["exit_gap_max_min"]))
    xi = x21[e_idx] if nE else np.zeros(0, np.int64)
    fails = [(ST_NO_BAR, ~has_bar), (ST_BAND, ~usable), (ST_INSIDE, side == 0), (ST_COST, ~passes), (ST_LATE, late),
             (ST_TARGET, reached), (ST_STOP0, ~(stop_dist > 0)), (ST_EXIT, xi <= ei)]
    status = np.full(n, ST_ORDER, np.int64)
    for code, mask in reversed(fails):                          # the first failed test in this order wins
        status[mask] = code
    lim = p.get("max_trades_per_cross_per_evening")
    if lim:                                                     # one_per_night: the earliest order(s) of the evening (L22)
        o = np.flatnonzero(status == ST_ORDER)
        if len(o):
            eo = e_idx[o]
            first = np.r_[True, eo[1:] != eo[:-1]]
            grp_start = np.maximum.accumulate(np.where(first, np.arange(len(o)), 0))
            rank = np.arange(len(o)) - grp_start
            status[o[rank >= int(lim)]] = ST_NOT_FIRST
    ev_col = E[e_idx] if nE else pd.DatetimeIndex([], dtype="datetime64[ns]")
    return pd.DataFrame({
        "evening": ev_col, "k": k_idx, "dec_ns": t, "has_bar": has_bar, "usable": usable, "mu": mu, "sigma": sd,
        "close": close, "C": C, "side": side, "D": D, "passes_filter": passes, "entry_i": ei, "has_entry_bar": has_e,
        "entry_delay_min": np.where(has_e, delay / NS_MIN, np.nan), "open_reached_target": reached,
        "h1_completed": kh, "h1_mean_range": mean_rng, "stop_dist": stop_dist, "exit21_i": xi, "status": status})


def make_orders(bk, p, ev=None, table=None):
    """goldlab.sim orders of configuration p on the frame of bk: market entry (etype 0) at entry_i, stop_dist from the
    fill, the frozen middle band as an absolute target (none for moving_mid), the 21:00 time exit (moving_mid: the
    moving exit, capped by it). Returns (orders, decision table)."""
    tb = decision_table(bk, p, ev) if table is None else table
    o = tb[tb.status.to_numpy() == ST_ORDER]
    frozen = p["target_mode"] == "frozen_middle_band"
    assert frozen or p["target_mode"] == "moving_middle_band", p["target_mode"]
    ent = bk.ns[o.entry_i.to_numpy()] if len(o) else np.zeros(0, np.int64)
    orders = pd.DataFrame({
        "entry_i": o.entry_i.to_numpy(np.int64), "side": o.side.to_numpy(np.int64), "etype": 0,
        "stop_dist": o.stop_dist.to_numpy(np.float64),
        "target": o.mu.to_numpy(np.float64) if frozen else np.full(len(o), np.nan),
        "exit_i": o.exit21_i.to_numpy(np.int64),
        "cross": bk.cross, "evening": o.evening.to_numpy(), "k_dec": o.k.to_numpy(np.int64),
        "dec_utc": pd.to_datetime(o.dec_ns.to_numpy(), unit="ns").to_numpy(),
        "mu": o.mu.to_numpy(np.float64), "sigma": o.sigma.to_numpy(np.float64), "close_mid": o.close.to_numpy(np.float64),
        "D": o.D.to_numpy(np.float64), "C": o.C.to_numpy(np.float64), "entry_delay_min": o.entry_delay_min.to_numpy(),
        "h1_mean_range": o.h1_mean_range.to_numpy(np.float64), "target_px": o.mu.to_numpy(np.float64),
        "exit21_i": o.exit21_i.to_numpy(np.int64),
        "ny_summer_time": ny_summer(pd.to_datetime(ent, unit="ns", utc=True)) if len(o) else np.zeros(0, bool)})
    if not frozen:
        xi, t_end = moving_exit_i(bk, orders, p)
        orders["exit_i"] = xi
        orders["mm_trigger_end_ns"] = t_end                     # end of the moving_mid trigger bar (-1: none)
        assert (orders.exit_i > orders.entry_i).all() and (orders.exit_i <= orders.exit21_i).all()
    assert (orders.stop_dist > 0).all() and (orders.exit21_i > orders.entry_i).all()
    return orders.reset_index(drop=True), tb


def next_true(cond):
    """For each position, the first position at or after it where cond holds (len(cond) if none); one extra slot."""
    n = len(cond)
    idx = np.where(cond, np.arange(n), n)
    out = np.minimum.accumulate(idx[::-1])[::-1] if n else np.zeros(0, np.int64)
    return np.r_[out, n].astype(np.int64)


def moving_exit_i(bk, orders, p):
    """moving_mid exit (L21): the open of the first M1 bar at or after the end of the first usable signal bar that ends
    after the entry bar starts and whose mid close is >= (long) / <= (short) its own middle band, capped by the 21:00
    exit bar (which keeps its own 30-minute gap rule). No gap rule applies to the moving exit itself (review R6-1): the
    text gives the gap rule to the 21:00 exit only, and a 'last bar before the end' would take the exit price at the
    open of a minute whose own close is the trigger, i.e. before the exit signal exists. The exit bar therefore always
    starts at or after the trigger bar's end, which is after the entry bar's start, so it is always after the entry bar.
    Returns (exit_i, the trigger bar's end in UTC ns or -1 when no bar triggers)."""
    m = int(p["bar_minutes"])
    sb = bk.bars(m, int(p["band_period"]), int(p["band_span_max_min"]))
    nb = len(sb["start"])
    if len(orders) == 0:
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    x21 = orders.exit21_i.to_numpy(np.int64)
    if nb == 0:                                                             # no signal bar at all: the 21:00 exit
        return x21.copy(), np.full(len(orders), -1, np.int64)
    tau = bk.ns[orders.entry_i.to_numpy()]
    j0 = np.searchsorted(sb["start"], tau - m * NS_MIN, side="right")      # first bar with end > entry bar start
    nl = next_true(sb["usable"] & (sb["close"] >= sb["mu"]))
    ns_ = next_true(sb["usable"] & (sb["close"] <= sb["mu"]))
    side = orders.side.to_numpy()
    js = np.where(side > 0, nl[j0], ns_[j0])
    found = js < nb
    t_end = np.where(found, sb["end"][np.minimum(js, nb - 1)], -1).astype(np.int64)
    xm = np.searchsorted(bk.ns, t_end, side="left").astype(np.int64)     # first M1 bar starting at or after the end
    return np.where(found, np.minimum(x21, xm), x21).astype(np.int64), t_end


# --------------------------------------------------------------------------------------------- simulation (L15-L19)
def costs(p, stress=1.0):
    """Engine costs: commission 0 (folded into the quotes), market slippage 0.1 bp, stop slippage 0.3 bp, no target
    slippage (the engine's rule), swap 0 (asserted unused, L16); x stress for costs x1.5 (L18)."""
    return Costs(commission=0.0, slip_bps=float(p["slip_stop_bps"]) * stress, slip_mkt_bps=float(p["slip_mkt_bps"]) * stress,
                 swap_long=0.0, swap_short=0.0, spread_mult=1.0)


GROSS = Costs(commission=0.0, slip_bps=0.0, slip_mkt_bps=0.0, swap_long=0.0, swap_short=0.0, spread_mult=1.0)


def check_trades(t, last_entry_ny="20:00"):
    """Asserted on every simulated trade (L16): in sample; entry and exit inside one trading day (no 17:00 New York
    rollover crossed, so the swap is 0); entry at or after 17:15 and by last_entry_ny, exit by 21:30 New York of the
    evening; swap column 0; no end-of-data exit."""
    if len(t) == 0:
        return t
    assert (t.entry_time < CUT).all() and (t.exit_time < CUT).all()
    assert not (t.reason == "eod").any()
    d0 = trading_day(t.entry_time)
    d1 = trading_day(t.exit_time - pd.Timedelta(nanoseconds=1))
    assert (d0 == d1).all(), "a trade crosses 17:00 New York"
    ev = pd.DatetimeIndex(t.evening)
    assert (d0 == ev + pd.Timedelta(days=1)).all(), "a trade outside the trading day its evening opens"
    e_ns = pd.DatetimeIndex(t.entry_time).as_unit("ns").asi8
    x_ns = pd.DatetimeIndex(t.exit_time).as_unit("ns").asi8
    assert (e_ns >= ny_utc_ns(ev, "17:15")).all() and (e_ns <= ny_utc_ns(ev, last_entry_ny)).all()
    assert (x_ns <= ny_utc_ns(ev, "21:30")).all()
    assert float(t.swap.abs().sum()) == 0.0
    return t


def exit_kinds(ns, t):
    """Exit kind of each trade (review R6-6): the engine's reason, with its 'time' split into 'time_21_00' (the exit at
    the 21:00 exit bar) and 'moving_mid' (a market exit before the 21:00 exit bar: only moving_mid's orders have one).
    Without an 'exit21_i' column (null replays) the engine's reason is kept. ns: the frame's M1 start times (UTC ns);
    the engine stamps a time exit with the start of its exit bar."""
    k = t.reason.astype(object).to_numpy().copy() if len(t) else np.zeros(0, object)
    if len(t) and "exit21_i" in t:
        xb = np.searchsorted(ns, pd.DatetimeIndex(t.exit_time).as_unit("ns").asi8, side="left")
        is_time = k == "time"
        early = is_time & (xb < t.exit21_i.to_numpy(np.int64))
        k[is_time] = "time_21_00"
        k[early] = "moving_mid"
    return k


def run_orders(bk, orders, cst, no_overlap=True, check=True, frame=None):
    """goldlab.sim.simulate on the frame of bk (or `frame`, same index) for one cross; adds the exit kind (R6-6)."""
    m1 = bk.m1 if frame is None else frame
    if frame is not None:
        assert len(frame) == len(bk.m1) and frame.index[0] == bk.m1.index[0] and frame.index[-1] == bk.m1.index[-1]
    t = simulate(m1, orders, sym=bk.cross, costs=cst, no_overlap=no_overlap)
    t["exit_kind"] = exit_kinds(bk.ns, t)
    if check:
        check_trades(t)
    return t


def stressed(m1, k=1.5):
    """Costs x1.5 frame (L18): goldlab.sim.apply_spread_mult(base, 1.5); k = 0.0 gives the gross frame (L19)."""
    return apply_spread_mult(m1, k)


def same_bar_both(m1, t):
    """For trades with a resting target: True where the exit bar touched both the stop and the target (the engine
    assumed the stop first). Long: bid low <= stop and bid high >= target; short: ask high >= stop and ask low <= target."""
    if len(t) == 0:
        return np.zeros(0, bool)
    ns = m1.index.as_unit("ns").asi8
    xt = pd.DatetimeIndex(t.exit_time).as_unit("ns").asi8
    is_time = (t.reason == "time").to_numpy()
    xb = np.where(is_time, xt, xt - NS_MIN)
    xi = np.searchsorted(ns, xb)
    xi = np.minimum(xi, len(ns) - 1)
    tg = t.target_px.to_numpy(np.float64) if "target_px" in t else np.full(len(t), np.nan)
    st = t.stop.to_numpy(np.float64)
    lng = t.side.to_numpy() > 0
    bl, bh, al, ah = (m1[c].to_numpy()[xi] for c in ("bl", "bh", "al", "ah"))
    both = np.where(lng, (bl <= st) & (bh >= tg), (ah >= st) & (al <= tg))
    return both & ~is_time & np.isfinite(tg)


# --------------------------------------------------------------------------------------------- metrics (L26, L30)
def _r(x, k=4):
    """A value rounded for display (NaN -> None, infinities -> 'inf' / '-inf')."""
    if x is None:
        return None
    x = float(x)
    if math.isnan(x):
        return None
    if math.isinf(x):
        return "inf" if x > 0 else "-inf"
    return round(x, k)


def _x(x):
    """The same value unrounded, for judging (review R6-2: every bar is read on the exact value, never on a display
    value): a float that survives a JSON round trip exactly (NaN -> None, infinities -> 'inf' / '-inf')."""
    if x is None:
        return None
    x = float(x)
    if math.isnan(x):
        return None
    if math.isinf(x):
        return "inf" if x > 0 else "-inf"
    return x


def pf(R):
    """PF on R: sum of positive R / |sum of negative R|; no trade = 0; no loss = inf (0 if no gain either)."""
    R = np.asarray(R, float)
    if len(R) == 0:
        return 0.0
    g, l = R[R > 0].sum(), -R[R < 0].sum()
    if l > 0:
        return float(g / l)
    return float("inf") if g > 0 else 0.0


def t_stat(x):
    x = np.asarray(x, float)
    if len(x) < 2:
        return float("nan")
    s = x.std(ddof=1)
    return float(x.mean() / (s / math.sqrt(len(x)))) if s > 0 else float("nan")


def daily_sums(t):
    """Sum of R per trading day of entry (goldlab.data.trading_day), days with a trade (L26)."""
    if len(t) == 0:
        return pd.Series(dtype=float)
    return t.R.groupby(trading_day(t.entry_time).to_numpy()).sum()


def bp(x, entry):
    return float((np.asarray(x, float) / np.asarray(entry, float)).mean() * 1e4) if len(x) else float("nan")


def stats(t, gross=None, per_cross=True, crosses=None):
    """Reported figures of a trade frame (one cross or pooled; column 'cross'): Addendum L 'reported, not judged' (L30).
    gross: the gross replay of the SAME orders as this reading (base and reading b: the base orders; reading a: its own
    rebuilt orders, review R6-3), for the gross and cost bp. Every figure a bar is judged on is also stored unrounded
    as '<name>_raw' (review R6-2); the rounded figures are for display only."""
    crosses = CROSSES if crosses is None else crosses
    n = int(len(t))
    out = {"n": n}
    if n == 0:
        out.update({"pf": 0.0, "pf_raw": 0.0, "t_daily": None, "t_daily_raw": None, "expectancy_R": None,
                    "expectancy_R_raw": None, "total_R": 0.0, "total_R_raw": 0.0, "max_hold_h": None, "max_hold_h_raw": None,
                    "years_pos": 0, "by_year_R": {y: 0.0 for y in YEARS}})
        if per_cross and "cross" in t:
            out.update({"crosses_positive": 0, "max_cross_share": None, "max_cross_share_raw": None})
        return out
    R = t.R.to_numpy(np.float64)
    assert np.isfinite(R).all(), "non-finite R"
    daily = daily_sums(t)
    yrs = t.R.groupby(t.entry_time.dt.year.to_numpy()).sum()
    win, loss = R > 0, R < 0
    aw = float(R[win].mean()) if win.any() else 0.0
    al = float(R[loss].mean()) if loss.any() else 0.0
    ret_bp = (t.pnl / t.entry).to_numpy() * 1e4
    tgt = (t.target_px - t.entry).abs().to_numpy() if "target_px" in t else np.full(n, np.nan)
    pf_, td_, mh_ = pf(R), t_stat(daily.to_numpy()), float(t.hold_min.max()) / 60
    out.update({
        "pf": _r(pf_, 4), "pf_raw": _x(pf_), "t_daily": _r(td_, 3), "t_daily_raw": _x(td_), "n_days": int(len(daily)),
        "t_trades": _r(t_stat(R), 3),
        "expectancy_R": _r(R.mean(), 5), "expectancy_R_raw": _x(R.mean()), "total_R": _r(R.sum(), 3),
        "total_R_raw": _x(R.sum()), "win_rate": _r(win.mean(), 4),
        "avg_win_R": _r(aw, 4), "avg_loss_R": _r(al, 4), "win_loss_ratio": _r(aw / abs(al), 4) if al < 0 else "inf",
        "years_pos": int(sum(1 for y in YEARS if float(yrs.get(y, 0.0)) > 0)),
        "by_year_R": {int(y): _r(float(yrs.get(y, 0.0)), 3) for y in YEARS},
        "by_year_n": {int(y): int((t.entry_time.dt.year == y).sum()) for y in YEARS},
        "long": _side(t[t.side > 0]), "short": _side(t[t.side < 0]),
        "exits": {k: int(v) for k, v in t.reason.value_counts().items()},
        "hold_min_mean": _r(t.hold_min.mean(), 2), "hold_min_max": _r(t.hold_min.max(), 2),
        "max_hold_h": _r(mh_, 3), "max_hold_h_raw": _x(mh_),
        "bp_net_per_trade": _r(ret_bp.mean(), 4),
        "stop_dist_pips_mean": _r((t.risk / PIP).mean(), 3), "stop_dist_pips_median": _r((t.risk / PIP).median(), 3),
        "stop_dist_bp_mean": _r((t.risk / t.entry).mean() * 1e4, 3),
        "target_dist_pips_mean": _r(np.nanmean(tgt) / PIP, 3) if np.isfinite(tgt).any() else None,
        "target_dist_pips_median": _r(np.nanmedian(tgt) / PIP, 3) if np.isfinite(tgt).any() else None,
        "target_dist_bp_mean": _r(np.nanmean(tgt / t.entry.to_numpy()) * 1e4, 3) if np.isfinite(tgt).any() else None,
    })
    if "exit_kind" in t:                                  # 'time' split into the 21:00 exit and moving_mid exits (R6-6)
        out["exits_by_kind"] = {k: int(v) for k, v in pd.Series(t.exit_kind).value_counts().items()}
    if gross is not None and len(gross):
        g = float((gross.pnl / gross.entry).mean() * 1e4)
        out["bp_gross_per_trade"] = _r(g, 4)
        out["bp_cost_per_trade"] = _r(g - ret_bp.mean(), 4)
        out["n_gross"] = int(len(gross))
    if per_cross and "cross" in t:
        tot = float(R.sum())
        g = t.groupby("cross").R
        cnt, mean, ssum = g.count(), g.mean(), g.sum()
        out["by_cross"] = {c: {"n": int(cnt.get(c, 0)), "expectancy_R": _r(mean.get(c, np.nan), 5),
                               "expectancy_R_raw": _x(mean.get(c, np.nan)),
                               "total_R": _r(float(ssum.get(c, 0.0)), 3),
                               "share_of_pooled_R": _r(float(ssum.get(c, 0.0)) / tot, 4) if tot > 0 else None}
                           for c in crosses}
        out["crosses_positive"] = int(sum(1 for c in crosses if cnt.get(c, 0) > 0 and float(mean.get(c, 0.0)) > 0))
        share = max(float(ssum.get(c, 0.0)) for c in crosses) / tot if tot > 0 else None
        out["max_cross_share"] = _r(share, 4)
        out["max_cross_share_raw"] = _x(share)
    return out


def _side(t):
    if len(t) == 0:
        return {"n": 0}
    R = t.R.to_numpy(np.float64)
    return {"n": int(len(t)), "total_R": _r(R.sum(), 3), "expectancy_R": _r(R.mean(), 5), "pf": _r(pf(R), 4),
            "win_rate": _r((R > 0).mean(), 4)}


SHORT_KEYS = ("n", "pf", "pf_raw", "t_daily", "t_daily_raw", "t_trades", "expectancy_R", "expectancy_R_raw", "total_R",
              "total_R_raw", "years_pos", "win_rate", "avg_win_R", "avg_loss_R", "bp_net_per_trade", "bp_gross_per_trade",
              "bp_cost_per_trade", "n_gross", "max_hold_h", "max_hold_h_raw", "exits", "exits_by_kind",
              "crosses_positive", "max_cross_share", "max_cross_share_raw")


def short(s):
    return {k: s[k] for k in SHORT_KEYS if k in s}


# --------------------------------------------------------------------------------------------- io and the declaration
def _default(o):
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return None if not np.isfinite(o) else float(o)
    return str(o)


def jdump(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, default=_default, ensure_ascii=False)


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


CODE_FILES = ["common.py", "frames.py", "declare.py", "precheck.py", "truncation.py", "test_synthetic.py", "handcheck.py",
              "run.py", "null.py", "correlation.py", "verdict.py"]


def code_hashes():
    return {f: sha256(os.path.join(HERE, f)) for f in CODE_FILES}


def check_frames(decl):
    """The twelve frames are byte for byte those whose sha256 declared.json recorded (L34)."""
    bad = [c for c, h in decl["frames_sha256"].items() if sha256(frame_path(c)) != h]
    assert not bad, f"frames changed after the declaration: {bad}"


def declared(out=OUT, check_code=True):
    """declared.json after checking it is byte for byte the file whose sha256 declare.py recorded, and that no code file
    changed since (L34)."""
    p = os.path.join(out, "declared.json")
    rec = open(os.path.join(out, "declared.sha256")).read().split()[0]
    assert sha256(p) == rec, "declared.json changed after it was written"
    d = json.load(open(p, encoding="utf-8"))
    if check_code:
        now = code_hashes()
        bad = {f: (h, now.get(f)) for f, h in d["code_sha256"].items() if now.get(f) != h}
        assert not bad, f"code changed after the declaration: {sorted(bad)}"
    return d, rec
