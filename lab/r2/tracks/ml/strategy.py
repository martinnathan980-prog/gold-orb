"""Track `ml` (round 2): hourly-breakout candidate generator + small learned filter ("our own indicator").

RULE (precise enough to port to an MT5 Expert Advisor)
------------------------------------------------------
Bars   : H1 bars built from BID prices (what an MT5 chart shows), on whole clock hours.  Only
         "session bars" are used, for every market: bars whose START is at 02:00..15:00 New-York
         time, Monday..Friday (14 bars a day).  On an FP Markets server (GMT+2/+3, i.e. New York
         + 7 h all year) these are the H1 bars opening at server hours 09..22.  All look-backs
         below count session bars only (the overnight bars are ignored, in every year).
Unit   : A = simple average of (high - low) of the last `vol_n` (70 = 5 sessions) session bars,
         including the bar just closed.
Signal : at the close of a session bar that starts at 02:00..(last_dec_h-1):00 NY (so decisions
         at 03:00 .. 15:00 NY):
             close > highest high of the previous `n` session bars  -> LONG candidate
             close < lowest  low  of the previous `n` session bars  -> SHORT candidate
Filter : optional learned score (JSON model, see `score_model`), computed from the features
         listed in FEATURES; the candidate is traded only if score >= threshold.
Entry  : market order at the first M1 bar that starts at/after the hour boundary (skipped if no
         bar within `max_wait_min` minutes).
Stop   : `stop_k` x A from the fill price (fixed, no trailing).
Exit   : time exit `hold_h` hours after the decision, but never later than `exit_hm` New-York
         time the same day (default 15:55); so no position is ever held overnight.

Everything is computed from the frame given to make_orders (the cost-stress test passes wider
quotes) and only from bars that are complete at the decision time.

Warm-up: the features need 4*vol_n (=280) session bars + the seq/opp windows = 22 sessions; give
make_orders at least 8 weeks of M1 before the first trade you care about (checked: a frame that
starts 6 weeks earlier gives identical orders, results/r2/ml/warmup_test.json).  For the 2026
holdout: load from 2025-11-01 and keep the trades entered from 2026-01-01.

FINALISTS (see the dict at the bottom; decided in-sample, results/r2/ml/finalists_preval.json)
  F1_brk_ridge_filter : the rule above with stop_k=2.0, exit 15:55 NY (hold_h=13 never binds) and the frozen
                        scorecard models/B1_ridge_full.json["frozen"] (13 z-scored inputs + 5 dummies, ridge
                        regression of the trade result in R, trained on the pooled in-sample candidates of
                        us100 + ger40 + xauusd + btcusd; trade if score >= median training score).
                        Human-readable copy for the EA: models/F1_frozen_scorecard.json ; EA text spec:
                        ea_spec_F1.txt.
  F2_brk_unfiltered   : the same generator and exits without any filter (the baseline the filter must beat).
  Both on btcusd and ethusd.  `oof=True` is a RESEARCH switch (walk-forward fold models for the in-sample
  numbers); validation, holdout and the EA use the frozen model (oof=False, the default).
"""
import json
import os

import numpy as np
import pandas as pd

import goldlab as gl

NY = gl.NY
HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(HERE, "models")

DEFAULTS = {
    "n": 14,              # channel length in session bars
    "h0": 2, "h1": 16,    # session = bars starting h0 .. h1-1 New-York time, Mon-Fri
    "last_dec_h": 15,     # last decision time (NY hour); bars starting >= last_dec_h give no entry
    "vol_n": 70,          # bars in the volatility unit A
    "stop_k": 1.5,        # stop distance = stop_k * A
    "hold_h": 4.0,        # time exit this many hours after the decision ...
    "exit_hm": 1555,      # ... but not later than this NY clock time (HHMM) the same day
    "max_wait_min": 5,    # entry bar must start within this many minutes of the hour boundary
    "entry_delay_min": 0, # execution-delay probe only: send the market order this many minutes late
    "model": None,        # JSON model file name (in ./models) or None = take every candidate
    "oof": False,         # research only: score each year with the walk-forward fold model of that year
    "q": None,            # threshold key in the model's "thr" table (e.g. "0.5"); None = model default
    "rule": None,         # optional hand rule instead of a model: list of [feature, op, value]
}

# numeric features (all scale-free: price distances are divided by A and signed by the trade side)
FEATURES = ["brk", "bar", "body", "ret4", "ret14", "ret70", "chan", "vol", "pos", "seq", "opp",
            "pdd", "dret", "hour", "dow"]

_cache = {}


def _key(m1):
    return (id(m1), len(m1), int(m1.index[0].value), int(m1.index[-1].value))


def _h1_bid(m1):
    """H1 bars from BID M1 bars (label = start, UTC). Fast numpy aggregation."""
    ts = m1.index.asi8
    unit = 3600 * 10 ** 9 if m1.index.unit == "ns" else None
    if unit is None:
        ts = m1.index.as_unit("ns").asi8
        unit = 3600 * 10 ** 9
    hid = ts // unit
    starts = np.flatnonzero(np.r_[True, hid[1:] != hid[:-1]])
    ends = np.r_[starts[1:], len(hid)] - 1
    bo, bh, bl, bc = (m1[k].to_numpy(np.float64) for k in ("bo", "bh", "bl", "bc"))
    idx = pd.DatetimeIndex(hid[starts] * unit, tz="UTC")
    return pd.DataFrame({"o": bo[starts], "h": np.maximum.reduceat(bh, starts),
                         "l": np.minimum.reduceat(bl, starts), "c": bc[ends],
                         "nbar": ends - starts + 1}, index=idx)


def session_bars(m1, h0=2, h1=16):
    k = _key(m1) + ("sess", h0, h1)
    if k not in _cache:
        if len(_cache) > 6:
            _cache.clear()
        b = _h1_bid(m1)
        ny = gl.local(b.index, NY)
        keep = (ny.hour >= h0) & (ny.hour < h1) & (ny.dayofweek < 5)
        b = b[keep].copy()
        ny = ny[keep]
        b["ny_hour"] = ny.hour
        b["ny_dow"] = ny.dayofweek
        b["ny_date"] = ny.tz_localize(None).normalize()
        _cache[k] = b
    return _cache[k]


def candidates(m1, **params):
    """All breakout candidates of the frame with their features (one row per candidate).
    Columns: t_dec (UTC decision time = hour boundary), side, A, entry_i, exit_i + FEATURES."""
    p = {**DEFAULTS, **params}
    n, vol_n = int(p["n"]), int(p["vol_n"])
    b = session_bars(m1, int(p["h0"]), int(p["h1"]))
    o, h, l, c = (b[k] for k in "ohlc")
    rng = h - l
    A = rng.rolling(vol_n).mean()
    A_long = rng.rolling(4 * vol_n).mean()
    hh = h.shift(1).rolling(n).max()
    ll = l.shift(1).rolling(n).min()
    up = (c > hh).to_numpy()
    dn = (c < ll).to_numpy()
    sig = np.where(up, 1, np.where(dn, -1, 0))
    side = pd.Series(sig, index=b.index)
    s = side.to_numpy().astype(float)
    f = pd.DataFrame(index=b.index)
    f["side"] = sig
    f["A"] = A
    f["brk"] = np.where(up, c - hh, ll - c) / A
    f["bar"] = rng / A
    f["body"] = s * (c - o) / A
    f["ret4"] = s * (c - c.shift(4)) / A
    f["ret14"] = s * (c - c.shift(14)) / A
    f["ret70"] = s * (c - c.shift(70)) / A
    f["chan"] = (hh - ll) / A
    f["vol"] = A / A_long
    hh_l = h.rolling(4 * vol_n).max()
    ll_l = l.rolling(4 * vol_n).min()
    f["pos"] = np.where(up, c - ll_l, hh_l - c) / (hh_l - ll_l)
    same_up = pd.Series(up.astype(float), index=b.index).shift(1).rolling(14).sum()
    same_dn = pd.Series(dn.astype(float), index=b.index).shift(1).rolling(14).sum()
    f["seq"] = np.where(up, same_up, same_dn)
    f["opp"] = np.where(up, same_dn, same_up)
    # previous session day: high, low, close
    day = b["ny_date"]
    g = b.groupby("ny_date", sort=True)
    dd = pd.DataFrame({"pdh": g["h"].max(), "pdl": g["l"].min(), "pdc": g["c"].last()}).shift(1)
    pdh = dd["pdh"].reindex(day).to_numpy()
    pdl = dd["pdl"].reindex(day).to_numpy()
    pdc = dd["pdc"].reindex(day).to_numpy()
    f["pdd"] = np.where(up, c - pdh, pdl - c) / A
    f["dret"] = s * (c - pdc) / A
    dec_hour = b["ny_hour"].to_numpy() + 1
    f["hour"] = dec_hour.astype(float)
    f["dow"] = b["ny_dow"].to_numpy().astype(float)
    f["t_dec"] = b.index + pd.Timedelta(hours=1)
    ok = (sig != 0) & (dec_hour <= int(p["last_dec_h"])) & np.isfinite(f[FEATURES].to_numpy()).all(axis=1) \
        & (A.to_numpy() > 0)
    f = f[ok].copy()
    if len(f) == 0:
        f["entry_i"] = np.array([], np.int64)
        f["exit_i"] = np.array([], np.int64)
        return f
    # entry: first M1 bar at/after the hour boundary, within max_wait_min
    t_dec = pd.DatetimeIndex(f["t_dec"])
    t_send = t_dec + pd.Timedelta(minutes=int(p["entry_delay_min"]))
    ei = gl.entry_index(m1, t_send)
    N = len(m1)
    eic = np.minimum(ei, N - 1)
    wait = (m1.index.values[eic] - t_send.tz_localize(None).values) / np.timedelta64(1, "m")
    good = (ei < N) & (wait <= float(p["max_wait_min"]))
    # time exit: hold_h hours after the decision, capped at exit_hm NY the same day
    ny = t_dec.tz_convert(NY)
    hm = int(p["exit_hm"])
    cap = (ny.normalize() + pd.Timedelta(hours=hm // 100, minutes=hm % 100)).tz_convert("UTC")
    xt = t_dec + pd.Timedelta(minutes=int(round(float(p["hold_h"]) * 60)))
    xt = xt.where(xt <= cap, cap)
    xi = gl.exit_index(m1, xt)
    good &= xi > ei
    f["entry_i"] = ei
    f["exit_i"] = xi
    return f[good]


# ----------------------------------------------------------------------------------------------
# model scoring (pure numpy, mirrors what the EA will do)
# ----------------------------------------------------------------------------------------------
def _design(f, spec):
    """Design matrix for a model spec: numeric features (z-scored with the model's own mean/std,
    clipped at +/- clip) plus dummies declared in spec['dummies'] = [[feature, lo, hi], ...]."""
    cols = []
    for name, mu, sd in zip(spec["num"], spec["mean"], spec["std"]):
        z = (f[name].to_numpy(float) - mu) / sd
        cols.append(np.clip(z, -spec.get("clip", 4.0), spec.get("clip", 4.0)))
    for name, lo, hi in spec.get("dummies", []):
        v = f[name].to_numpy(float)
        cols.append(((v >= lo) & (v <= hi)).astype(float))
    return np.column_stack(cols) if cols else np.zeros((len(f), 0))


def score_model(f, spec):
    """Score candidates with one model spec (dict from the JSON)."""
    if spec["type"] == "linear":      # ridge / logistic: score = intercept + w . x
        X = _design(f, spec)
        return spec["intercept"] + X @ np.asarray(spec["coef"], float)
    if spec["type"] == "trees":       # shallow boosted trees on raw features
        X = f[spec["num"]].to_numpy(float)
        out = np.full(len(f), float(spec["init"]))
        for tr in spec["trees"]:
            node = np.zeros(len(f), np.int64)
            feat = np.asarray(tr["feat"]); thr = np.asarray(tr["thr"], float)
            left = np.asarray(tr["left"]); right = np.asarray(tr["right"]); val = np.asarray(tr["val"], float)
            for _ in range(int(tr["depth"])):
                isleaf = feat[node] < 0
                go_left = X[np.arange(len(f)), np.maximum(feat[node], 0)] <= thr[node]
                nxt = np.where(go_left, left[node], right[node])
                node = np.where(isleaf, node, nxt)
            out += spec["lr"] * val[node]
        return out
    raise ValueError(spec["type"])


_model_cache = {}


def load_model(name):
    path = name if os.path.isabs(name) else os.path.join(MODEL_DIR, name)
    mt = os.path.getmtime(path)
    if _model_cache.get(path, (None, None))[0] != mt:
        _model_cache[path] = (mt, json.load(open(path)))
    return _model_cache[path][1]


def _thr(spec, q):
    t = spec["thr"]
    if isinstance(t, dict):
        return float(t[str(q)] if q is not None else t[spec.get("q_default", sorted(t)[0])])
    return float(t)


def select(f, **params):
    """Boolean mask of the candidates that pass the filter (model / hand rule / none)."""
    p = {**DEFAULTS, **params}
    keep = np.ones(len(f), bool)
    if p["rule"]:
        for name, op, val in p["rule"]:
            v = f[name].to_numpy(float)
            keep &= (v >= val) if op == ">=" else (v <= val)
    if p["model"]:
        m = load_model(p["model"])
        if p["oof"]:
            # research only: each candidate is scored by the fold model trained on earlier years;
            # years without a fold (warm-up years) give no trade; years after the last fold use `frozen`
            keep_m = np.zeros(len(f), bool)
            yrs = pd.DatetimeIndex(f["t_dec"]).year.to_numpy()
            folds = {int(k): v for k, v in m["folds"].items()}
            last = max(folds)
            for y in np.unique(yrs):
                spec = folds.get(int(y), m["frozen"] if y > last else None)
                if spec is None:
                    continue
                sel = yrs == y
                keep_m[sel] = score_model(f[sel], spec) >= _thr(spec, p["q"])
        else:
            spec = m["frozen"]
            keep_m = score_model(f, spec) >= _thr(spec, p["q"])
        keep &= keep_m
    return keep


def make_orders(m1, **params):
    p = {**DEFAULTS, **params}
    f = candidates(m1, **p)
    f = f[select(f, **p)]
    return pd.DataFrame({
        "entry_i": f["entry_i"].to_numpy(np.int64),
        "side": f["side"].to_numpy(np.int64),
        "etype": 0,
        "stop_dist": float(p["stop_k"]) * f["A"].to_numpy(float),
        "exit_i": f["exit_i"].to_numpy(np.int64),
        "cid": pd.DatetimeIndex(f["t_dec"]).asi8,
    })


# Finalists (decided on in-sample evidence only, see results/r2/ml/finalists_preval.json).
# F1 = generator + learned filter (frozen model: pooled ridge scorecard, threshold = median training score).
# F2 = the same generator without any filter (the baseline the filter must beat).
FINALISTS = {
    "F1_brk_ridge_filter": {"syms": ["btcusd", "ethusd"],
                            "params": {"stop_k": 2.0, "hold_h": 13.0, "model": "B1_ridge_full.json", "q": "0.5"}},
    "F2_brk_unfiltered": {"syms": ["btcusd", "ethusd"],
                          "params": {"stop_k": 2.0, "hold_h": 13.0}},
}
