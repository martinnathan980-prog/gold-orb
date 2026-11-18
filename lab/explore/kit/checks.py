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


def truncation_test(build, data, cuts=(), row_len=pd.Timedelta(hours=1), cols=("known_at", "side"), n_signal_cuts=8,
                    seed=0):
    """Rebuild the signal table on data cut at each date and compare with the full build: the signals known at or before
    the cut must be identical (same rows, same `cols`, plus 'market' if present). `data`: a frame or a dict of frames /
    series indexed by UTC time; `row_len`: how long after its index time a row is complete (1 h for hourly bars indexed
    by their open; 0 for a series indexed by the time its value is KNOWN); a dict gives one per item and must name every item (a missing one raises: a
    default of 0 would make the test blind to a bar's own close). A cut at c keeps
    the rows complete by c (index + row_len <= c). So a signal stamped known_at = t that secretly uses a bar ending
    after t, or a value known after t, changes or vanishes in the cut build and the test fails (lab round 6
    truncation.py, at signal level). `build(data)` returns a signal table with known_at. Besides the given `cuts`, the
    test cuts exactly at the known_at of n_signal_cuts signals drawn from the full build (the sharpest cut: a signal
    must be rebuildable from what is complete at its own time stamp).
    The report carries `signals_sha` (sim.signals_sha of the full build): judge.verdict requires a passing report whose
    signals_sha equals the main configuration's simulated signals (trades.attrs['signals_sha']), and at least one cut
    at a signal's own time stamp. So build the WHOLE signal table inside `build` (filters included) and simulate exactly
    build(data) (adding a 'market' column is fine)."""
    full = build(data)
    rep = {"cuts": [], "pass": True, "signals_sha": sim.signals_sha(full), "n_signals": int(len(full)), "n_signal_cuts": 0}
    if n_signal_cuts and len(full):
        ka = pd.DatetimeIndex(full.known_at)
        pick = np.random.default_rng(seed).choice(len(ka), min(n_signal_cuts, len(ka)), replace=False)
        cuts = list(cuts) + list(ka[np.sort(pick)])
        rep["n_signal_cuts"] = int(len(pick))
    keep = [c for c in (["market"] if "market" in full else []) + list(cols) if c in full]
    for c in cuts:
        c = pd.Timestamp(c)
        c = c.tz_localize("UTC") if c.tz is None else c
        part = build(_cut(data, c, row_len))
        a = full[pd.DatetimeIndex(full.known_at) <= c][keep].reset_index(drop=True)
        b = part[pd.DatetimeIndex(part.known_at) <= c][keep].reset_index(drop=True)
        same = len(a) == len(b) and all((a[k].to_numpy() == b[k].to_numpy()).all() for k in keep)
        rep["cuts"].append({"cut": str(c), "n_full": int(len(a)), "n_cut": int(len(b)), "equal": bool(same)})
        rep["pass"] &= bool(same)
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
