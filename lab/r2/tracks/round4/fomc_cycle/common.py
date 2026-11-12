"""FOMC-cycle even/odd weeks, long-short on us500 (PROTOCOL_V3 Addendum J, rule 4). Shared code.

IN SAMPLE ONLY: every frame is read with the parquet row filter ts < 2022-01-01 (load_is) and the slice is passed
explicitly to every function; goldlab.r2.load / r2.null_test (which read whole frames) are never called. Every reading
of a detail the frozen text leaves open is in results/r2/round4/fomc_cycle/declared.json (D1..D16), written before any
run; the code below cites them.

Pipeline:
    frame = load_is("us500")
    lab   = day_labels(nyse_days()[0], FOMC, s)        # calendar only (no price)
    blk   = blocks(lab, side_map(mode, wm1_side))       # one row per week trade
    dec   = decisions(frame, blk, clock, stop_k)        # decision / exit instants, ATR(20) known at the decision
    o     = orders(frame, dec)                          # bar indices, refusals; simulate(frame, o[ok]) ...
"""
import importlib.util
import json
import math
import os
import sys
from dataclasses import replace

os.environ.setdefault("NUMBA_CACHE_DIR", "/tmp/numba_fomc_cycle")
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

LAB = "/home/user/gold-orb/lab"
if LAB not in sys.path:
    sys.path.insert(0, LAB)
_IDX = os.path.join(LAB, "r2", "tracks", "idx_us")
if _IDX not in sys.path:
    sys.path.append(_IDX)
import idxus_lib  # noqa: E402  NYSE calendar + daily ATR of the index tracks (imported read-only)
from goldlab import r2  # noqa: E402
from goldlab.data import entry_index, exit_index  # noqa: E402
from goldlab.metrics import report  # noqa: E402
from goldlab.sim import apply_spread_mult, simulate  # noqa: E402

CUT = pd.Timestamp("2022-01-01", tz="UTC")
NY = "America/New_York"
OUT = os.path.join(LAB, "results", "r2", "round4", "fomc_cycle")
SPEC = r2.SPEC
ATR_N = 20


def _load_season_calendar():
    p = os.path.join(LAB, "tracks", "seasonality", "calendars.py")
    spec = importlib.util.spec_from_file_location("seasonality_calendars_fomc_cycle", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# D1/D2: the scheduled FOMC statement days, cut at < 2022-01-01 on import (the later dates are never used)
FOMC = pd.DatetimeIndex([d for d in _load_season_calendar().FOMC if d < pd.Timestamp("2022-01-01")])


# --------------------------------------------------------------------------------------------- data
def load_is(sym, cut=CUT):
    """In-sample M1 frame (8 quote columns): rows with ts < 2022-01-01 00:00 UTC, filtered while reading."""
    assert pd.Timestamp(cut) <= CUT
    df = pd.read_parquet(os.path.join(LAB, "data", "fp", f"{sym}_m1.parquet"),
                         filters=[("ts", "<", pd.Timestamp(cut))])
    df.index = df.index.as_unit("ns")
    assert len(df) and df.index.max() < CUT and df.index.is_monotonic_increasing and df.index.is_unique
    return df


def nyse_days(first="2012-12-03", last="2021-12-31"):
    """NYSE trading days (D2): weekdays that are not full closures; early closes kept. Returns (days, is_half)."""
    assert pd.Timestamp(last) < pd.Timestamp("2022-01-01")
    d = pd.bdate_range(first, last)
    full, half = idxus_lib.calendar_flags([x.date() for x in d])
    return d[~full], half[~full]


# --------------------------------------------------------------------------------------------- calendar
def day_labels(days, fomc=FOMC, s=0):
    """Week label of every NYSE day (D3). week: -1 = W-1, 0..6 = W0..W6, -2 = no week (ignored / before the data).
    cycle: index in `fomc` of the day 0 the label refers to (the NEXT day 0 for W-1)."""
    pos = days.get_indexer(fomc)
    assert (pos >= 0).all(), "a day 0 is not an NYSE day"
    assert (np.diff(pos) >= 12).all()
    n = len(days)
    i = np.arange(n)
    j = np.searchsorted(pos - 1 + s, i, side="right") - 1          # current cycle (-1: before the first)
    jn = j + 1                                                     # next cycle
    has_next = jn < len(pos)
    t = np.where(j >= 0, i - pos[np.clip(j, 0, None)], -999)
    u = np.where(has_next, i - pos[np.clip(jn, 0, len(pos) - 1)], 999)
    wm1 = has_next & (u >= -6 + s) & (u <= -2 + s)
    week = np.full(n, -2)
    cyc = np.full(n, -1)
    week[wm1] = -1
    cyc[wm1] = jn[wm1]
    for k in range(7):
        m = (~wm1) & (j >= 0) & (t >= 5 * k - 1 + s) & (t <= 5 * k + 3 + s)
        week[m] = k
        cyc[m] = j[m]
    return pd.DataFrame({"day": days, "i": i, "cycle": cyc, "week": week, "t": t, "u": u, "s": s})


def side_map(mode="both", wm1_side=0):
    """D4: week -> position. 'both': long even weeks, short odd weeks; 'long_even': long even weeks only."""
    if mode == "both":
        m = {k: (1 if k % 2 == 0 else -1) for k in range(7)}
    elif mode == "long_even":
        m = {k: (1 if k % 2 == 0 else 0) for k in range(7)}
    else:
        raise ValueError(mode)
    m[-1] = int(wm1_side)
    m[-2] = 0
    return m


def blocks(lab, smap, fomc=FOMC):
    """One row per week trade: maximal runs of NYSE days with the same (cycle, week) label and a non-zero side (D4).
    Flags a block cut by the end of the in-sample day list before its nominal end (D6: exit outside the sample)."""
    s = int(lab.s.iloc[0])
    side = lab.week.map(smap).astype(int).to_numpy()
    key = lab.cycle.to_numpy() * 100 + lab.week.to_numpy()
    bid = np.cumsum(np.r_[True, key[1:] != key[:-1]]) - 1
    df = lab.assign(side=side, bid=bid)
    df = df[df.side != 0]
    g = df.groupby("bid", sort=True)
    b = g.agg(first_i=("i", "first"), last_i=("i", "last"), n_days=("i", "size"), week=("week", "first"),
              cycle=("cycle", "first"), side=("side", "first"), t_first=("t", "first"), t_last=("t", "last"),
              u_last=("u", "last")).reset_index()
    assert (b.last_i - b.first_i + 1 == b.n_days).all()      # runs are contiguous
    assert (b.first_i >= 1).all()
    days = lab.day.to_numpy()
    b["entry_day"] = pd.DatetimeIndex(days[b.first_i - 1])   # NYSE day before the week's first day (D5)
    b["first_day"] = pd.DatetimeIndex(days[b.first_i])
    b["last_day"] = pd.DatetimeIndex(days[b.last_i])
    b["day0"] = pd.DatetimeIndex(fomc[b.cycle.to_numpy()])
    nominal_end = np.where(b.week >= 0, b.t_last == 5 * b.week + 3 + s, b.u_last == -2 + s)
    b["truncated"] = (b.last_i == len(lab) - 1) & ~nominal_end
    b["wlabel"] = np.where(b.week >= 0, "W" + b.week.astype(str), "W-1")
    return b


# --------------------------------------------------------------------------------------------- orders
def ny_time(dates, hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    return (pd.DatetimeIndex(dates) + pd.Timedelta(hours=h, minutes=m)).tz_localize(NY).tz_convert("UTC")


def decisions(frame, blk, clock="15:55", stop_k=3.0):
    """Decision instant (clock NY on the entry day), scheduled exit (clock NY on the last day), ATR(20) of the daily
    bars known at the decision (D7: last trading day completed at 17:00 NY at or before it), stop distance."""
    te = ny_time(blk.entry_day, clock)
    tx = ny_time(blk.last_day, clock)
    atr = idxus_lib.atr_at(frame, te.tz_localize(None).values.astype("datetime64[ns]"), ATR_N)
    d = blk.copy()
    d["t_dec"] = te
    d["t_exit_sched"] = tx
    d["atr20"] = atr
    d["stop_dist"] = float(stop_k) * atr
    return d


def orders(frame, dec):
    """Bar indices (D5, D6) and refusals (D6, D7). Returns all decisions with a `status`; simulate o[o.status=='ok']."""
    N = len(frame)
    ei = entry_index(frame, dec.t_dec)
    xi = exit_index(frame, dec.t_exit_sched)
    eic = np.minimum(ei, N - 1)
    spread0 = frame["ao"].to_numpy()[eic] - frame["bo"].to_numpy()[eic]
    st = np.full(len(dec), "ok", dtype=object)
    bad_exit = (dec.t_exit_sched >= CUT).to_numpy() | dec.truncated.to_numpy()
    no_atr = ~np.isfinite(dec.stop_dist.to_numpy())
    no_bar = ei >= N
    not_before = (~no_bar) & (xi <= ei)
    close_stop = dec.stop_dist.to_numpy() < 3.0 * spread0
    for mask, name in ((close_stop, "stop_lt_3_spreads"), (not_before, "entry_not_before_exit"),
                       (no_bar, "no_entry_bar"), (no_atr, "no_atr20"), (bad_exit, "exit_after_sample")):
        st[mask] = name                                       # the last one written wins (most basic reason)
    o = dec.copy()
    o["entry_i"] = ei
    o["exit_i"] = xi
    o["etype"] = 0
    o["spread0"] = spread0
    o["status"] = st
    idx = frame.index
    o["entry_bar"] = idx[eic]
    o["exit_bar"] = idx[np.clip(xi, 0, N - 1)]
    o["entry_delay_min"] = (o.entry_bar - o.t_dec).dt.total_seconds() / 60
    o["exit_shift_min"] = (o.exit_bar - o.t_exit_sched).dt.total_seconds() / 60
    return o


SIM_COLS = ["entry_i", "side", "etype", "stop_dist", "exit_i", "wlabel", "week", "n_days", "day0", "entry_day",
            "last_day", "atr20", "t_dec", "t_exit_sched", "entry_delay_min", "exit_shift_min"]


def costs_for(sym, cmode):
    if cmode == "fp":
        return r2.costs(sym)
    if cmode == "x1.5":                                       # D9: spread, slippage AND swap x 1.5
        c = r2.costs(sym, 1.5)
        return replace(c, swap_long=SPEC[sym]["swap_long"] * 1.5, swap_short=SPEC[sym]["swap_short"] * 1.5)
    if cmode == "gross":
        return r2.GROSS
    raise ValueError(cmode)


SPREAD_MULT = {"fp": 1.0, "x1.5": 1.5, "gross": 0.0}


def build(frame, p, days=None):
    """Orders of configuration p (dict of declared params) on `frame` (already spread-scaled if needed)."""
    if days is None:
        days = nyse_days()[0]
    lab = day_labels(days, FOMC, int(p["shift"]))
    blk = blocks(lab, side_map(p["mode"], p["wm1_side"]))
    dec = decisions(frame, blk, p["clock"], p["stop_k"])
    return orders(frame, dec)


def run(frame_fp, p, cmode=None):
    """Simulate configuration p. The orders are rebuilt on the spread-scaled frame (as r2.run). Returns (trades, orders)."""
    cmode = cmode or p["costs"]
    fr = apply_spread_mult(frame_fp, SPREAD_MULT[cmode])
    o = build(fr, p)
    ok = o[o.status == "ok"][SIM_COLS].reset_index(drop=True)
    t = simulate(fr, ok, sym=p["sym"], costs=costs_for(p["sym"], cmode), no_overlap=False)
    assert len(t) == len(ok) and t.attrs["skipped"] == 0 and t.attrs["nofill"] == 0
    assert (t.entry_time < CUT).all() and (t.exit_time < CUT).all()
    return t, o, ok


# --------------------------------------------------------------------------------------------- metrics
def _r(x, k=4):
    return None if x is None or not np.isfinite(x) else round(float(x), k)


def pf(x):
    x = np.asarray(x, float)
    g, l = x[x > 0].sum(), -x[x < 0].sum()
    return float(g / l) if l > 0 else float("inf")


def summarize(t, o=None):
    rep = report(t)
    out = {k: v for k, v in rep.items()}
    out["bp_net_per_trade"] = _r((t.pnl / t.entry).mean() * 1e4, 2)
    out["bp_swap_per_trade"] = _r((t.swap / t.entry).mean() * 1e4, 2)
    out["bp_swap_per_long_trade"] = _r((t.swap[t.side > 0] / t.entry[t.side > 0]).mean() * 1e4, 2) if (t.side > 0).any() else None
    out["mean_risk_bp"] = _r((t.risk / t.entry).mean() * 1e4, 1)
    out["max_hold_nyse_days"] = int(t.n_days.max())
    out["n_partial_weeks"] = int((t.n_days < 5).sum())
    out["n_hold_over_192h"] = int((t.hold_min / 60 > 192).sum())
    out["n_stop_exits"] = int((t.reason == "stop").sum())
    out["n_entry_delayed_over_5min"] = int((t.entry_delay_min > 5).sum())
    out["n_exit_moved_before_closure"] = int((t.exit_shift_min < -1).sum())
    yrs = t.groupby(t.entry_time.dt.year)["R"]
    out["by_year"] = {int(y): {"n": int(g.size), "R": round(float(g.sum()), 2), "mean_R": round(float(g.mean()), 4),
                               "pf": _r(pf(g), 3)} for y, g in yrs}
    bw = {}
    for w, g in t.groupby("wlabel"):
        bw[w] = {"n": int(len(g)), "side": int(g.side.iloc[0]), "mean_R": _r(g.R.mean()), "sum_R": round(float(g.R.sum()), 2),
                 "pf": _r(pf(g.R), 3), "bp_net": _r((g.pnl / g.entry).mean() * 1e4, 2), "full_weeks": int((g.n_days == 5).sum())}
    out["by_week_label"] = bw
    for side, nm in ((1, "long"), (-1, "short")):
        g = t[t.side == side]
        out[nm] = {"n": int(len(g)), "mean_R": _r(g.R.mean()) if len(g) else None, "sum_R": round(float(g.R.sum()), 2),
                   "pf": _r(pf(g.R), 3) if len(g) else None, "bp_net": _r((g.pnl / g.entry).mean() * 1e4, 2) if len(g) else None}
    if o is not None:
        out["decisions_by_status"] = {k: int(v) for k, v in o.status.value_counts().items()}
    return out


# --------------------------------------------------------------------------------------------- null (D10)
def null_time(frame, ok, t, sym, n_seeds=200, seed=0):
    """Random-time null on the in-sample slice: same sides, stop distances (fraction of price), time-exit delays (bars)."""
    idx = frame.index
    fill_i = idx.get_indexer(t.entry_time)
    assert (fill_i >= 0).all()
    xi = ok.loc[t.index, "exit_i"].to_numpy(np.int64)
    dur = np.maximum(xi - fill_i, 1)
    stop_rel = (t.risk / t.entry).to_numpy(float)
    side = t.side.to_numpy()
    mid = ((frame["bc"].to_numpy() + frame["ac"].to_numpy()) / 2)
    N = len(frame)
    assert (N - dur > 0).all()
    rng = np.random.default_rng(seed)
    c = costs_for(sym, "fp")
    means, longs, shorts = [], [], []
    for _ in range(n_seeds):
        ei = rng.integers(0, N - dur)                          # ei + dur <= N - 1: the whole replay is in sample
        no = pd.DataFrame({"entry_i": ei, "side": side, "stop_dist": stop_rel * mid[ei], "exit_i": ei + dur})
        tn = simulate(frame, no, sym=sym, costs=c, no_overlap=False)
        assert len(tn) == len(no) and (tn.exit_time < CUT).all()
        means.append(float(tn.R.mean()))
        longs.append(float(tn.R[tn.side > 0].mean()) if (tn.side > 0).any() else np.nan)
        shorts.append(float(tn.R[tn.side < 0].mean()) if (tn.side < 0).any() else np.nan)
    means = np.array(means)
    cand = float(t.R.mean())
    return {"n_trades": int(len(t)), "replays": int(n_seeds), "seed": int(seed), "mode": "time",
            "rule_mean_R": round(cand, 4), "null_mean_R": round(float(means.mean()), 4),
            "null_sd_R": round(float(means.std(ddof=1)), 4), "null_p50_R": round(float(np.percentile(means, 50)), 4),
            "null_p95_R": round(float(np.percentile(means, 95)), 4), "null_p975_R": round(float(np.percentile(means, 97.5)), 4),
            "null_max_R": round(float(means.max()), 4),
            "null_long_trades_mean_R": round(float(np.nanmean(longs)), 4) if np.isfinite(longs).any() else None,
            "null_short_trades_mean_R": round(float(np.nanmean(shorts)), 4) if np.isfinite(shorts).any() else None,
            "percentile": round(float((means < cand).mean() * 100), 1),
            "pass": bool((means < cand).mean() >= 0.975)}, means


# --------------------------------------------------------------------------------------------- io
def jdump(obj, path):
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=str, ensure_ascii=False)


def t_stat(x):
    x = np.asarray(x, float)
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")
