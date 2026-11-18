"""Guards a run calls before trusting a pass."""
import hashlib
import os

import numpy as np
import pandas as pd

from . import sim
from . import stats as S


def _cut(data, c, lens):
    if isinstance(data, dict):
        if isinstance(lens, dict):
            miss = [k for k in data if k not in lens]
            if miss:
                raise ValueError(f"truncation_test: no row_len for {miss}: give each item's row length (1 h for hourly "
                                 "bars indexed by their open, 0 for a series indexed by the time its value is KNOWN)")
            return {k: _cut(v, c, lens[k]) for k, v in data.items()}
        return {k: _cut(v, c, lens) for k, v in data.items()}
    idx = pd.DatetimeIndex(data.index)
    return data[idx + lens <= c]


# Minimum cut density judge.verdict requires of a truncation report (verifier V1, 2026-11-18: a build that DROPS an
# event or signal when the future is favourable, written so that a NaN at the end of a cut keeps it, is seen only by a
# cut a few bars after a dropped row; 8 cuts at kept rows' stamps caught it in 1 seed of 10, 50 stamp cuts or 100 random
# bar-end cuts in 10 of 10).
MIN_STAMP_CUTS = 50
MIN_AFTER_CUTS = 50
MIN_RANDOM_CUTS = 100
AFTER_BARS = 24


def _bar_ends(data, lens):
    """Sorted unique int64 ns of every row's completion time (index + row_len) over all items of data."""
    if isinstance(data, dict):
        if isinstance(lens, dict):
            miss = [k for k in data if k not in lens]
            if miss:
                raise ValueError(f"truncation_test: no row_len for {miss}: give each item's row length (1 h for hourly "
                                 "bars indexed by their open, 0 for a series indexed by the time its value is KNOWN)")
            parts = [_bar_ends(v, lens[k]) for k, v in data.items()]
        else:
            parts = [_bar_ends(v, lens) for v in data.values()]
        return np.unique(np.concatenate(parts)) if parts else np.array([], np.int64)
    idx = pd.DatetimeIndex(data.index)
    idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    return np.unique((idx + pd.Timedelta(lens)).as_unit("ns").asi8)


def cuts_ok(rep):
    """(ok, why): does a truncation report carry the cut density judge.verdict requires? At least
    min(MIN_STAMP_CUTS, n_signals) cuts at rows' own time stamps, as many cuts 1-AFTER_BARS bar ends after them, and
    min(MIN_RANDOM_CUTS, bar ends available) random bar-end cuts across the history."""
    n = int(rep.get("n_signals", 0))
    need_s = min(MIN_STAMP_CUTS, n)
    if rep.get("n_signal_cuts", 0) < max(1, need_s) and n > 0:
        return False, f"too few cuts at a row's own time stamp ({rep.get('n_signal_cuts', 0)} < {max(1, need_s)})"
    if rep.get("n_after_tried", 0) < min(MIN_AFTER_CUTS, n):
        return False, f"too few cuts just after the rows' stamps ({rep.get('n_after_tried', 0)} < {min(MIN_AFTER_CUTS, n)})"
    need_r = min(MIN_RANDOM_CUTS, int(rep.get("n_bar_ends", 0)))
    if "n_random_cuts" not in rep or rep["n_random_cuts"] < need_r:
        return False, f"too few random bar-end cuts ({rep.get('n_random_cuts', 0)} < {need_r})"
    return True, "enough cuts"


def truncation_test(build, data, cuts=(), row_len=pd.Timedelta(hours=1), cols=("known_at", "side"),
                    n_signal_cuts=MIN_STAMP_CUTS, seed=0, n_random_cuts=MIN_RANDOM_CUTS, n_after_cuts=None):
    """Rebuild the signal table on data cut at each date and compare with the full build: the signals known at or before
    the cut must be identical (same rows, same `cols`, plus 'market' if present). `data`: a frame or a dict of frames /
    series indexed by UTC time; `row_len`: how long after its index time a row is complete (1 h for hourly bars indexed
    by their open; 0 for a series indexed by the time its value is KNOWN); a dict gives one per item and must name every item (a missing one raises: a
    default of 0 would make the test blind to a bar's own close). A cut at c keeps
    the rows complete by c (index + row_len <= c). So a signal stamped known_at = t that secretly uses a bar ending
    after t, or a value known after t, changes or vanishes in the cut build and the test fails (lab round 6
    truncation.py, at signal level). `build(data)` returns a signal table with known_at.
    Cuts, besides the given `cuts` (verifier V1: dense by default):
      - n_signal_cuts (50) cuts exactly at the known_at of signals drawn from the full build (the sharpest cut for a
        signal that uses data after its own stamp: it vanishes or changes);
      - n_after_cuts (default = as many) cuts 1-24 bar ends after drawn signals' stamps, and n_random_cuts (100) cuts at
        random bar ends (index + row_len of the data) across the history: they catch a build that DROPS a row when the
        future is favourable (a row kept only because the future is NaN at the end of a cut reappears in the cut build;
        no cut at a kept row's own stamp lands on a dropped one).
    The report carries the counts; judge.verdict requires checks.cuts_ok (>= min(50, n) stamp cuts, >= min(50, n)
    after-cuts, >= min(100, bar ends) random cuts). A row dropped only by a look-ahead of h bars is seen by a cut in the
    h bar ends after it: the test is sampled, so a very rare dropped row can still slip through (README 'limits').
    The report carries `signals_sha` (sim.signals_sha of the full build): judge.verdict requires a passing report whose
    signals_sha equals the main configuration's simulated signals (trades.attrs['signals_sha']). So build the WHOLE
    signal table inside `build` (filters included) and simulate exactly build(data) (adding a 'market' column is fine).
    EVENT builds (exit on a condition): a build returning a table WITHOUT 'side' (columns known_at = when the exit
    condition is known to be true, optional market) is tested the same way; the report then carries `events_sha`
    (sim.events_sha of the full build, signals_sha None) and `events_by_key` (sha per market key, '*' for a table without
    market), and judge.verdict binds it to the events each simulated market used (pass it as event_truncation=)."""
    full = build(data)
    ends = _bar_ends(data, row_len)                       # also refuses a dict without a row_len for every item
    is_ev = "side" not in full
    rep = {"cuts": [], "pass": True, "signals_sha": None if is_ev else sim.signals_sha(full), "n_signals": int(len(full)),
           "n_signal_cuts": 0, "n_after_cuts": 0, "n_after_tried": 0, "n_random_cuts": 0}
    if is_ev:
        rep["events_sha"] = sim.events_sha(full)
        rep["events_by_key"] = sim.events_by_key(full)
    rng = np.random.default_rng(seed)
    cuts = [pd.Timestamp(c) for c in cuts]
    if n_signal_cuts and len(full):
        ka = pd.DatetimeIndex(full.known_at)
        pick = rng.choice(len(ka), min(n_signal_cuts, len(ka)), replace=False)
        stamps = ka[np.sort(pick)]
        cuts += list(stamps)
        rep["n_signal_cuts"] = int(len(pick))
        na = len(pick) if n_after_cuts is None else min(int(n_after_cuts), len(pick))
        if na and len(ends):
            sa = (stamps.tz_convert("UTC") if stamps.tz is not None else stamps.tz_localize("UTC")).as_unit("ns").asi8
            sel = np.sort(rng.choice(len(sa), na, replace=False))
            pos = np.searchsorted(ends, sa[sel], side="right") + rng.integers(0, AFTER_BARS, na)
            okp = pos < len(ends)
            cuts += list(pd.DatetimeIndex(ends[pos[okp]].astype("datetime64[ns]")).tz_localize("UTC"))
            rep["n_after_cuts"] = int(okp.sum())          # a stamp at the very end of the data has no bar end after it
            rep["n_after_tried"] = int(na)
    if n_random_cuts and len(ends) > 1:
        pool = ends[:-1]                                  # a cut at the last bar end is the full build
        if len(full):
            ka = pd.DatetimeIndex(full.known_at)
            ka = (ka.tz_convert("UTC") if ka.tz is not None else ka.tz_localize("UTC")).as_unit("ns").asi8
            lo, hi = ka.min() - 7 * 86400 * 10 ** 9, ka.max() + 7 * 86400 * 10 ** 9
            pool = pool[(pool >= lo) & (pool <= hi)] if ((pool >= lo) & (pool <= hi)).any() else pool
        rep["n_bar_ends"] = int(len(pool))
        pr = np.sort(rng.choice(len(pool), min(n_random_cuts, len(pool)), replace=False))
        cuts += list(pd.DatetimeIndex(pool[pr].astype("datetime64[ns]")).tz_localize("UTC"))
        rep["n_random_cuts"] = int(len(pr))
    else:
        rep["n_bar_ends"] = int(max(len(ends) - 1, 0))
    keep = [c for c in (["market"] if "market" in full else []) + list(cols) if c in full]
    fka = pd.DatetimeIndex(full.known_at)
    for c in cuts:
        c = c.tz_localize("UTC") if c.tz is None else c
        part = build(_cut(data, c, row_len))
        a = full[fka <= c][keep].reset_index(drop=True)
        b = part[pd.DatetimeIndex(part.known_at) <= c][keep].reset_index(drop=True)
        same = len(a) == len(b) and all((a[k].to_numpy() == b[k].to_numpy()).all() for k in keep)
        rep["cuts"].append({"cut": str(c), "n_full": int(len(a)), "n_cut": int(len(b)), "equal": bool(same)})
        rep["pass"] &= bool(same)
    rep["n_failed_cuts"] = int(sum(not x["equal"] for x in rep["cuts"]))
    rep["density_ok"], rep["density_why"] = cuts_ok(rep)
    return rep


def shift_test(signals, bars, delay_extra_h=1.0, **rule):
    """The same signals entered one bar (delay_extra_h hours) later: reported, not judged. A rule whose result
    collapses with a one-hour delay lives on the entry bar itself: look for look-ahead or a fragile clock."""
    d0 = float(rule.pop("delay_h", 0.0))
    a = sim.simulate(signals, bars, delay_h=d0, **rule)
    b = sim.simulate(signals, bars, delay_h=d0 + delay_extra_h, **rule)
    f = lambda t: {"n": int(len(t)), "PF": S.pf(t.R), "mean_R": float(t.R.mean()) if len(t) else None,  # noqa: E731
                   "PF_gross": S.pf(t.R_gross)}
    return {"base": f(a), "shifted": f(b), "delay_extra_h": delay_extra_h}


def declared_hash(idea_dir):
    """sha256 of declared.json; raises if it does not match declared.sha256 (first token) or if either is missing.
    judge.verdict calls it itself (bar 'declared_hash')."""
    h = hashlib.sha256(open(os.path.join(idea_dir, "declared.json"), "rb").read()).hexdigest()
    want = open(os.path.join(idea_dir, "declared.sha256")).read().split()[0].strip()
    if h != want:
        raise AssertionError(f"declared.json changed after declaration: {h} != {want}")
    return h
