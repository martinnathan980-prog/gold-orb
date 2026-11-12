"""ger40_noise30_xetra (PROTOCOL_V3 Addendum J, rule 3): the frozen noise30 rule on the DAX's own cash clock.
IN SAMPLE ONLY.  Readings of every open detail: results/r2/round4/ger40_noise30_xetra/declared.json (R01..R21).

    make_orders(m1, lookback=14, vm=1.0, step=30, first_min=570, last_min=1020, exit_min=1045) -> orders frame
    run(m1, params, mode)  -> (trades, orders, info)    mode: 'fp' | 'stress' | 'gross'

Clock: Europe/Berlin.  Sessions: Xetra trading days (calendar fixed in advance, `xetra_holidays`), the last session of a
year treated as an early close (not a session), trading skipped on the first session of a year and on the first session
after a weekday 24 December.  For every session d and minute offset m from 09:00 Berlin the grid gives the mid price
KNOWN at 09:00+m (close of the last M1 bar that started before that instant, NaN if older than 10 min) and the index of
the first M1 bar on which a decision taken at that instant is executed (its open).  The state machine is the frozen
noise30 code (r2/tracks/idx_us/strategy.py::_noise) on that grid.

Causality: a decision at check T uses bars that started before T (closed at or before T), O of the 09:00 bar of the same
session, PC of the previous session and sigma of previous sessions only; it is executed at the open of the first bar
starting at or after T.  Tested by truncation (truncation.py).
"""
import datetime as dt
import os
import sys

SCR = "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/ger40_noise30_xetra"
os.environ.setdefault("NUMBA_CACHE_DIR", os.path.join(SCR, "numba"))
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from dateutil.easter import easter  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
RES = os.path.join(LAB, "results", "r2", "round4", "ger40_noise30_xetra")
if LAB not in sys.path:
    sys.path.insert(0, LAB)
import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
from goldlab.metrics import report  # noqa: E402
from goldlab.sim import apply_spread_mult, simulate  # noqa: E402

SYM = "ger40"
BER = "Europe/Berlin"
IS_END = pd.Timestamp("2022-01-01", tz="UTC")          # nothing at or after this instant is ever read
TRADE_START = dt.date(2014, 1, 1)                       # R01: trades from the sessions of 2014 on
T0_MIN = 540                                            # 09:00 Berlin = column 0 of the grid
N_MIN = 511                                             # columns 0..510 = 09:00 .. 17:30
PC_COL = 510                                            # price at 17:30 = close of the 17:29 bar
MAIN = {"lookback": 14, "vm": 1.0, "step": 30, "first_min": 570, "last_min": 1020, "exit_min": 1045}
_MIN = np.timedelta64(60, "s").astype("timedelta64[ns]")


# ------------------------------------------------------------------------------------------------ data
def load_is():
    """In-sample ger40 FP frame: bar start < 2022-01-01 00:00 UTC, filtered while reading (no 2022 row materialised)."""
    path = os.path.join(LAB, "data", "fp", f"{SYM}_m1.parquet")
    df = pd.read_parquet(path, filters=[("ts", "<", IS_END)])
    assert df.index.is_monotonic_increasing and df.index.max() < IS_END
    assert list(df.columns) == ["bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"], list(df.columns)
    return df


# ------------------------------------------------------------------------------------------------ calendar (R03-R05)
def xetra_holidays(y):
    """Xetra (Deutsche Boerse cash market) non-trading days of year y, rule based (fixed in advance)."""
    e = easter(y)
    h = {dt.date(y, 1, 1), e - dt.timedelta(days=2), e + dt.timedelta(days=1), dt.date(y, 5, 1),
         dt.date(y, 12, 24), dt.date(y, 12, 25), dt.date(y, 12, 26), dt.date(y, 12, 31)}
    if y <= 2021:                                       # Whit Monday and German Unity Day: holidays up to 2021 (R03)
        h |= {e + dt.timedelta(days=50), dt.date(y, 10, 3)}
    if y == 2017:
        h.add(dt.date(2017, 10, 31))                    # Reformation Day 2017
    return h


def _year_sessions(y):
    """All weekdays of year y that are not Xetra holidays (before removing the year-end early close)."""
    hol = xetra_holidays(y)
    return [d.date() for d in pd.bdate_range(dt.date(y, 1, 1), dt.date(y, 12, 31)) if d.date() not in hol]


def calendar(y):
    """(sessions, early_close, skip) of year y.  early_close: the last session before 31 December (R04), removed from
    the sessions.  skip: sessions not traded (R05): the first session of the year (the day after the previous year's
    early close) and the first session after a weekday 24 December."""
    s = _year_sessions(y)
    early = max(d for d in s if d < dt.date(y, 12, 31))
    sess = [d for d in s if d != early]
    skip = {sess[0]}
    x24 = dt.date(y, 12, 24)
    if x24.weekday() < 5:
        after = [d for d in sess if d > x24]
        if after:
            skip.add(after[0])
    return sess, early, skip


def sessions_between(d0, d1):
    """Sessions (python dates) in [d0, d1], the early closes and the skip set of the years spanned."""
    sess, early, skip = [], set(), set()
    for y in range(d0.year, d1.year + 1):
        s, e, k = calendar(y)
        sess += [d for d in s if d0 <= d <= d1]
        early.add(e)
        skip |= k
    return sess, early, skip


def check_calendar_against_package(years=range(2016, 2022)):
    """The rule-based holidays equal the `holidays` package's XETR calendar on 2016-2021 (R03)."""
    import holidays
    out = {}
    for y in years:
        pk = set(holidays.financial_holidays("XETR", years=y).keys())
        mine = xetra_holidays(y)
        out[y] = {"equal": pk == mine, "only_package": sorted(str(d) for d in pk - mine),
                  "only_rule": sorted(str(d) for d in mine - pk)}
    return out


# ------------------------------------------------------------------------------------------------ grid (R06-R07)
def grid_generic(m1, tz, t0_min, n_min, pc_col, dates, trade_ok, o_late_max, stale_min=10, late_min=5):
    """idxus_lib.grid generalised: sessions `dates` (python dates), anchor t0 = `t0_min` minutes after midnight on the
    `tz` clock; P[d, m] = mid close of the last bar that started before t0+m (NaN if it started more than stale_min+1
    minutes before); EI[d, m] = first bar starting at/after t0+m if at most late_min minutes late, else -1;
    O = mid open of the first bar starting in [t0, t0 + o_late_max]; PC = previous row's P[:, pc_col]."""
    idx = m1.index
    iv = idx.values.astype("datetime64[ns]")
    days = pd.DatetimeIndex(pd.to_datetime(list(dates)))
    t0 = (days + pd.Timedelta(minutes=t0_min)).tz_localize(tz).tz_convert("UTC").tz_localize(None)
    t0 = t0.values.astype("datetime64[ns]")
    T = t0[:, None] + (np.arange(n_min)[None, :] * _MIN)
    pos = np.searchsorted(iv, T.ravel(), side="left").reshape(T.shape)
    mid_c = (m1["bc"].to_numpy() + m1["ac"].to_numpy()) / 2
    mid_o = (m1["bo"].to_numpy() + m1["ao"].to_numpy()) / 2
    n = len(iv)
    prev = np.clip(pos - 1, 0, n - 1)
    age = (T - iv[prev]) / np.timedelta64(60, "s")            # minutes since the START of the last bar before T
    P = np.where((pos > 0) & (age <= stale_min + 1), mid_c[prev], np.nan)
    nxt = np.clip(pos, 0, n - 1)
    late = (iv[nxt] - T) / np.timedelta64(60, "s")
    EI = np.where((pos < n) & (late <= late_min) & (late >= 0), pos, -1).astype(np.int64)
    O = np.where((pos[:, 0] < n) & (late[:, 0] <= o_late_max) & (late[:, 0] >= 0), mid_o[nxt[:, 0]], np.nan)
    PC = np.r_[np.nan, P[:-1, pc_col]]
    return {"dates": np.array(list(dates)), "t0": t0, "t0_min": t0_min, "P": P, "EI": EI, "O": O, "PC": PC,
            "trade_ok": np.asarray(trade_ok, bool), "pos": pos}


def grid(m1):
    """The Xetra grid of this rule: Berlin clock, t0 = 09:00, columns to 17:30, O = open of the bar starting exactly at
    09:00 (R07), PC = previous session's price at 17:30, sessions and skipped days of R03-R05."""
    ber = m1.index[[0, -1]].tz_convert(BER)
    sess, early, skip = sessions_between(ber[0].date(), ber[1].date())
    trade_ok = [(d >= TRADE_START) and (d not in skip) for d in sess]
    g = grid_generic(m1, BER, T0_MIN, N_MIN, PC_COL, sess, trade_ok, o_late_max=0)
    g["early"], g["skip"] = early, skip
    return g


# ------------------------------------------------------------------------------------------------ rule (R08-R10)
def make_orders(m1, lookback=14, vm=1.0, step=30, first_min=570, last_min=1020, exit_min=1045, g=None,
                require_pc=True):
    """Orders of the frozen noise30 state machine on the Xetra clock.  Extra columns describe each decision.
    `g` / `require_pc=False` exist only for the reproduction check of the frozen New York noise30 (repro_check.py)."""
    g = grid(m1) if g is None else g
    EI, P, O, PC, t0, t00 = g["EI"], g["P"], g["O"], g["PC"], g["t0"], g["t0_min"]
    checks = np.arange(first_min - t00, last_min - t00 + 1, step)
    absmove = np.abs(P[:, checks] / O[:, None] - 1)
    sig = pd.DataFrame(absmove).rolling(lookback, min_periods=max(int(0.7 * lookback), 1)).mean().shift(1).to_numpy()
    hi_ref = np.where(np.isfinite(PC), np.fmax(O, PC), O)
    lo_ref = np.where(np.isfinite(PC), np.fmin(O, PC), O)
    xi = gl.exit_index(m1, pd.DatetimeIndex(t0 + (exit_min - t00) * _MIN, tz="UTC"))
    ok = g["trade_ok"] & np.isfinite(O)
    if require_pc:
        ok &= np.isfinite(PC)
    rows = {k: [] for k in ("entry_i", "side", "stop", "exit_i", "d", "j_in", "m_in", "t_in", "psig", "sig", "ub", "lb",
                            "o_px", "pc_px", "j_out", "m_out", "t_out")}
    for d in np.flatnonzero(ok):
        pos, open_k = 0, -1
        for j, m in enumerate(checks):
            p, s, ei = P[d, m], sig[d, j], EI[d, m]
            if not (np.isfinite(p) and np.isfinite(s)) or ei < 0 or ei >= xi[d]:
                continue
            ub, lb = hi_ref[d] * (1 + vm * s), lo_ref[d] * (1 - vm * s)
            if pos != 0 and ((pos > 0 and p < ub) or (pos < 0 and p > lb)):
                rows["exit_i"][open_k] = ei            # back inside the band: close at this check
                rows["j_out"][open_k] = j
                rows["m_out"][open_k] = t00 + int(m)
                rows["t_out"][open_k] = int((t0[d] + m * _MIN).astype("int64"))
                pos = 0
                ei += 1                                # a reversal at the same check goes one bar later
            if pos == 0 and ei < xi[d]:
                if p > ub or p < lb:
                    pos = 1 if p > ub else -1
                    rows["entry_i"].append(ei)
                    rows["side"].append(pos)
                    rows["stop"].append(hi_ref[d] if pos > 0 else lo_ref[d])   # hard stop: max/min(O, PC)
                    rows["exit_i"].append(xi[d])
                    rows["d"].append(int(d))
                    rows["j_in"].append(j)
                    rows["m_in"].append(t00 + int(m))
                    rows["t_in"].append(int((t0[d] + m * _MIN).astype("int64")))
                    rows["psig"].append(p)
                    rows["sig"].append(s)
                    rows["ub"].append(ub)
                    rows["lb"].append(lb)
                    rows["o_px"].append(O[d])
                    rows["pc_px"].append(PC[d])
                    rows["j_out"].append(-1)
                    rows["m_out"].append(-1)
                    rows["t_out"].append(-1)
                    open_k = len(rows["entry_i"]) - 1
    ints = ("entry_i", "side", "exit_i", "d", "j_in", "m_in", "t_in", "j_out", "m_out", "t_out")
    o = pd.DataFrame({k: np.asarray(v, np.int64 if k in ints else np.float64) for k, v in rows.items()})
    o.insert(2, "etype", np.zeros(len(o), np.int64))
    o["sdate"] = np.array([int(g["dates"][d].strftime("%Y%m%d")) for d in o["d"]], np.int64) if len(o) else \
        np.zeros(0, np.int64)
    return o.sort_values("entry_i", kind="stable").reset_index(drop=True)


# ------------------------------------------------------------------------------------------------ simulation (R11-R12)
def mode_frame(m1, mode):
    if mode == "fp":
        return m1
    if mode == "stress":
        return apply_spread_mult(m1, 1.5)
    if mode == "gross":
        return apply_spread_mult(m1, 0.0)
    raise ValueError(mode)


def mode_costs(mode):
    if mode == "fp":
        return r2.costs(SYM)
    if mode == "stress":
        return r2.costs(SYM, 1.5)
    if mode == "gross":
        return r2.GROSS
    raise ValueError(mode)


def simulate_filtered(mk, orders, costs, min_spreads=3.0, no_overlap=True, max_iter=20):
    """simulate() with the broker's minimum stop distance (R12): a trade whose initial stop is closer to its fill than
    `min_spreads` spreads of its fill bar (ask open - bid open), or already crossed at the fill, is refused: its order
    is removed and the configuration re-simulated until no taken trade violates the rule."""
    o = orders.reset_index(drop=True).copy()
    o["oid"] = np.arange(len(o), dtype=np.int64)
    spr_all = mk["ao"].to_numpy() - mk["bo"].to_numpy()
    idx = mk.index
    refused = []
    t = None
    for _ in range(max_iter):
        t = simulate(mk, o, sym=SYM, costs=costs, no_overlap=no_overlap)
        if not len(t) or min_spreads is None:
            break
        fi = idx.searchsorted(t.entry_time)
        bad = (t["risk"].to_numpy() < min_spreads * spr_all[fi]) & (t["reason"].to_numpy() != "gap")
        bad |= t["reason"].to_numpy() == "gap"
        if not bad.any():
            break
        ids = t["oid"].to_numpy()[bad]
        refused.extend(int(i) for i in ids)
        o = o[~o["oid"].isin(ids)]
    t = t.copy()
    t.attrs["refused_3spreads"] = len(refused)
    t.attrs["refused_oids"] = refused
    return t


def run(m1, params, mode="fp", no_overlap=True):
    """One configuration on the in-sample slice in one cost mode.  Returns (trades, orders, info)."""
    mk = mode_frame(m1, mode)
    o = make_orders(mk, **params)
    t = simulate_filtered(mk, o, mode_costs(mode), min_spreads=None if mode == "gross" else 3.0, no_overlap=no_overlap)
    assert (t.entry_time < IS_END).all()
    t = t[t.entry_time >= pd.Timestamp(TRADE_START, tz="UTC")]
    info = {"orders": int(len(o)), "refused_3spreads": int(t.attrs.get("refused_3spreads", 0)),
            "skipped_overlap": int(t.attrs.get("skipped", 0))}
    return t, o, info


def summary(t):
    """goldlab.metrics.report of a trades frame + bp per trade and per-year counts."""
    if t is None or not len(t):
        return {"n": 0}
    r = report(t)
    r["bps_per_trade"] = round(float((t["pnl"] / t["entry"]).mean() * 1e4), 3)
    r["by_year_n"] = {int(k): int(v) for k, v in t.groupby(t.entry_time.dt.year).size().items()}
    r["swap_total"] = round(float(t["swap"].sum()), 6)
    return r
