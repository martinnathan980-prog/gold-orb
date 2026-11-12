"""IDXRS_1000 (PROTOCOL_V3 Addendum J, rule 1): US index relative-strength pair, 10:00 -> 15:55 New York.
Shared code. IN SAMPLE ONLY: every frame is read with the parquet row filter ts < 2022-01-01 (load_is) and the
slices are passed explicitly to every function. The frozen rule and the readings of open details are in
results/r2/round4/idxrs_1000/declared.json (written before any run).

Pipeline (everything takes the three in-sample frames explicitly):
    frames = {s: load_is(s) for s in SYMS}
    G  = build_grid(frames, sessions())            # per session x minute (09:30 .. 16:00) quotes, exact bars
    P  = prepare(G)                                 # stacked arrays, forward-filled closes, back-filled opens
    sg = signals(P, entry_min, exit_min, q, win, minv)   # ranking, threshold, h, sd_pi (past sessions only)
    tr = run_config(P, sg, k, slip_m, slip_s)       # two-leg simulation of every signal -> trades frame

Causality: the ranking of day j uses bars that STARTED before the entry minute on day j; every trailing statistic
uses sessions strictly before j (pandas rolling(...).shift(1)); the stop is decided on the close of bar t and executed
at the open of bar t + 1. truncation.py rebuilds everything on frames cut at decision times and compares.
"""
import json
import math
import os
import sys

import numpy as np
import pandas as pd

LAB = "/home/user/gold-orb/lab"
if LAB not in sys.path:
    sys.path.insert(0, LAB)
_IDX = os.path.join(LAB, "r2", "tracks", "idx_us")
if _IDX not in sys.path:
    sys.path.append(_IDX)
import idxus_lib  # noqa: E402  NYSE calendar of noise30 / ocm4 (imported read-only)
from goldlab.metrics import report  # noqa: E402
from goldlab.sim import apply_spread_mult  # noqa: E402

CUT = pd.Timestamp("2022-01-01", tz="UTC")
SYMS = ("us100", "us500", "us30")
NY = "America/New_York"
OUT = os.path.join(LAB, "results", "r2", "round4", "idxrs_1000")
SPEC = {k: v for k, v in json.load(open(os.path.join(LAB, "r2", "fp_costs.json"))).items() if not k.startswith("_")}
G0 = 570            # 09:30 New York, minute of day
NMIN = 391          # grid columns = bars starting 09:30 ... 16:00
MIN_NS = 60_000_000_000
FIRST_SESSION = "2013-09-30"     # first day with all three frames (us30 starts 2013-09-30); checked in data_check.py
LAST_SESSION = "2021-12-31"
SLIP_M = SPEC["us100"]["slip_mkt_bps"] * 1e-4      # 0.2 bp, identical for us100 / us500 / us30
SLIP_S = SPEC["us100"]["slip_stop_bps"] * 1e-4     # 0.5 bp
assert all(SPEC[s]["slip_mkt_bps"] == 0.2 and SPEC[s]["slip_stop_bps"] == 0.5 for s in SYMS)
PAIR_TYPES = {frozenset((0, 1)): "us100/us500", frozenset((0, 2)): "us100/us30", frozenset((1, 2)): "us500/us30"}


# --------------------------------------------------------------------------------------------- data
def load_is(sym, cut=CUT, cols=("bo", "bc", "ao", "ac")):
    """In-sample M1 frame: rows with ts < 2022-01-01 00:00 UTC, filtered while reading."""
    assert pd.Timestamp(cut) <= CUT
    df = pd.read_parquet(os.path.join(LAB, "data", "fp", f"{sym}_m1.parquet"), columns=list(cols),
                         filters=[("ts", "<", pd.Timestamp(cut))])
    assert len(df) and df.index.max() < CUT and df.index.is_monotonic_increasing and df.index.is_unique
    return df


def load_frames(cost_mult=1.0):
    """The three in-sample frames; cost_mult != 1: widened by the lab's own goldlab.sim.apply_spread_mult (which needs
    the eight quote columns), then reduced to the four columns used here."""
    if cost_mult == 1.0:
        return {s: load_is(s) for s in SYMS}
    out = {}
    for s in SYMS:
        f = apply_spread_mult(load_is(s, cols=("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac")), cost_mult)
        out[s] = f[["bo", "bc", "ao", "ac"]].copy()
        del f
    return out


def sessions(first=FIRST_SESSION, last=LAST_SESSION):
    """NYSE full sessions (weekday, not a full closure, not a 13:00 early close), naive dates."""
    days = pd.bdate_range(first, last)
    full, half = idxus_lib.calendar_flags([d.date() for d in days])
    return days[~full & ~half]


def _tmin(index):
    return pd.DatetimeIndex(index).as_unit("ns").asi8 // MIN_NS


def build_grid(frames, days):
    """Quotes of the bar that STARTS at 09:30 + m New York (m = 0..390) of each session; NaN if no such bar."""
    t0 = (days + pd.Timedelta(minutes=G0)).tz_localize(NY).tz_convert("UTC")
    t0m = _tmin(t0)
    T = (t0m[:, None] + np.arange(NMIN)[None, :]).ravel()
    G = {"days": days, "t0m": t0m}
    for s in SYMS:
        df = frames[s]
        tm = _tmin(df.index)
        pos = np.searchsorted(tm, T)
        posc = np.minimum(pos, len(tm) - 1)
        hit = (pos < len(tm)) & (tm[posc] == T)
        for c in ("bo", "bc", "ao", "ac"):
            v = df[c].to_numpy(np.float64)
            G[(s, c)] = np.where(hit, v[posc], np.nan).reshape(len(days), NMIN)
    return G


def ffill2(a, limit=None):
    """Forward fill along minutes inside each session (optionally at most `limit` minutes old)."""
    col = np.arange(a.shape[1])[None, :]
    last = np.where(np.isfinite(a), col, -1)
    np.maximum.accumulate(last, axis=1, out=last)
    out = np.take_along_axis(a, np.maximum(last, 0), axis=1)
    bad = last < 0
    if limit is not None:
        bad |= (col - last) > limit
    out[bad] = np.nan
    return out


def bfill2(a):
    """Back fill along minutes: the quote of the first bar at or after each minute (inside the session grid)."""
    return ffill2(a[:, ::-1])[:, ::-1]


def prepare(G, ffill_limit=None):
    """Stacked (3, D, NMIN) arrays: exact bars, forward-filled closes, back-filled opens; mids."""
    st = lambda c: np.stack([G[(s, c)] for s in SYMS])
    P = {"days": G["days"], "t0m": G["t0m"]}
    for c in ("bo", "bc", "ao", "ac"):
        P[c] = st(c)
    P["mo"] = (P["bo"] + P["ao"]) / 2
    P["mc"] = (P["bc"] + P["ac"]) / 2
    for c in ("bc", "ac", "mc"):
        P[c + "_ff"] = np.stack([ffill2(P[c][i], ffill_limit) for i in range(3)])
    for c in ("bo", "ao", "mo"):
        P[c + "_bf"] = np.stack([bfill2(P[c][i]) for i in range(3)])
    return P


# --------------------------------------------------------------------------------------------- signals
def ranking(P, e):
    """r_i = ln(mid close of the bar before column e / mid open of the 09:30 bar), exact bars; S, W, D; ok mask."""
    r = np.log(P["mc"][:, :, e - 1] / P["mo"][:, :, 0]).T            # (D, 3)
    ok = np.isfinite(r).all(axis=1)
    rz = np.where(ok[:, None], r, 0.0)
    srt = np.sort(rz, axis=1)
    ok &= ~((srt[:, 2] == srt[:, 1]) | (srt[:, 0] == srt[:, 1]))     # ties: no ranking
    S, W = rz.argmax(axis=1), rz.argmin(axis=1)
    D = np.where(ok, srt[:, 2] - srt[:, 0], np.nan)
    return r, ok, S, W, D


def signals(P, entry_min=600, exit_min=955, q=0.75, win=60, minv=40):
    e, x = entry_min - G0, exit_min - G0
    assert 0 < e < x < NMIN
    r, ok, S, W, D = ranking(P, e)
    ret = np.log(P["mo"][:, :, x] / P["mo"][:, :, e]).T               # (D, 3), entry open -> exit open, exact bars
    roll = lambda a: pd.Series(a).rolling(int(win), min_periods=int(minv))
    Q = roll(D).quantile(q).shift(1).to_numpy()
    sd = np.column_stack([roll(ret[:, i]).std(ddof=1).shift(1).to_numpy() for i in range(3)])
    ar = np.arange(len(D))
    h = np.where(ok, sd[ar, S] / sd[ar, W], np.nan)
    pi = np.where(ok, ret[ar, S] - h * ret[ar, W], np.nan)            # every ranked day, traded or not
    sdpi = roll(pi).std(ddof=1).shift(1).to_numpy()
    take = ok & np.isfinite(Q) & (D >= Q) & np.isfinite(h) & (h > 0) & np.isfinite(sdpi) & (sdpi > 0)
    return {"e": e, "x": x, "r": r, "ok": ok, "S": S, "W": W, "D": D, "Q": Q, "sd": sd, "h": h, "ret": ret, "pi": pi,
            "sdpi": sdpi, "take": take, "params": dict(entry_min=entry_min, exit_min=exit_min, q=q, win=win, minv=minv)}


# --------------------------------------------------------------------------------------------- two-leg simulator
def sim_pairs(P, d, S, W, h, sdpi, e, x, k, slip_m=SLIP_M, slip_s=SLIP_S, mode="net", exit_close=False):
    """Simulate n pairs: BUY leg S (notional N), SELL leg W (notional h N) at the open of column e of session d;
    stop decided on the close of each bar e .. x-1 when pi <= -k sdpi, executed at the next open; else exit at the
    open of the first bar at / after column x.  mode 'net' = bid/ask + slippage, 'mid' = mid prices, no slippage.
    exit_close=True (reproduction check only): exit at the close of column x (forward-filled close)."""
    d, S, W = (np.asarray(v, np.int64) for v in (d, S, W))
    h, sdpi = np.asarray(h, float), np.asarray(sdpi, float)
    n = len(d)
    if mode == "net":
        fS = P["ao"][S, d, e] * (1 + slip_m)
        fW = P["bo"][W, d, e] * (1 - slip_m)
        mS, mW, xS, xW, cS, cW = "bc_ff", "ac_ff", "bo_bf", "ao_bf", "bc_ff", "ac_ff"
    elif mode == "mid":
        fS, fW = P["mo"][S, d, e], P["mo"][W, d, e]
        mS = mW = cS = cW = "mc_ff"
        xS = xW = "mo_bf"
        slip_m = slip_s = 0.0
    else:
        raise ValueError(mode)
    filled = np.isfinite(fS) & np.isfinite(fW)
    cols = e + np.arange(x - e)[None, :]
    with np.errstate(invalid="ignore", divide="ignore"):
        pim = np.log(P[mS][S[:, None], d[:, None], cols] / fS[:, None]) \
            - h[:, None] * np.log(P[mW][W[:, None], d[:, None], cols] / fW[:, None])
        thr = -(k * sdpi)
        hit = (pim <= thr[:, None]) if np.isfinite(k) else np.zeros_like(pim, bool)
    stopped = hit.any(axis=1) & filled
    u = np.where(stopped, hit.argmax(axis=1), -1)                         # column offset of the stop decision
    xc = np.where(stopped, e + u + 1, x)                                   # execution column
    if exit_close:
        pS, pW = P[cS][S, d, x], P[cW][W, d, x]
        fb = np.zeros(n, bool)
    else:
        pS, pW = P[xS][S, d, xc], P[xW][W, d, xc]
        fb = ~(np.isfinite(pS) & np.isfinite(pW))                         # no bar at / after: last known close
        pS = np.where(np.isfinite(pS), pS, P[cS][S, d, xc - 1])
        pW = np.where(np.isfinite(pW), pW, P[cW][W, d, xc - 1])
    sl = np.where(stopped, slip_s, slip_m)
    eS, eW = pS * (1 - sl), pW * (1 + sl)
    with np.errstate(invalid="ignore", divide="ignore"):
        net = np.log(eS / fS) - h * np.log(eW / fW)
        money = (eS / fS - 1) - h * (eW / fW - 1)
    # mid-price result of the same entry / exit minutes (cost = mid result - net result)
    mfS, mfW = P["mo"][S, d, e], P["mo"][W, d, e]
    mxS = np.where(np.isfinite(P["mo_bf"][S, d, xc]), P["mo_bf"][S, d, xc], P["mc_ff"][S, d, xc - 1])
    mxW = np.where(np.isfinite(P["mo_bf"][W, d, xc]), P["mo_bf"][W, d, xc], P["mc_ff"][W, d, xc - 1])
    with np.errstate(invalid="ignore", divide="ignore"):
        mid_same = np.log(mxS / mfS) - h * np.log(mxW / mfW)
    return {"filled": filled, "stopped": stopped, "u": u, "xc": xc, "fill_S": fS, "fill_W": fW, "exit_S": eS,
            "exit_W": eW, "net": net, "money": money, "mid_same": mid_same, "fallback": fb & filled, "pim": pim}


def spread_floor_ok(P, d, S, W, h, sdpi, e, k):
    """Hard rule 4: refuse a pair whose stop k x sd_pi is closer than 3 x (spread_S + h x spread_W) at the entry open."""
    spS = (P["ao"][S, d, e] - P["bo"][S, d, e]) / P["mo"][S, d, e]
    spW = (P["ao"][W, d, e] - P["bo"][W, d, e]) / P["mo"][W, d, e]
    return (k * sdpi) >= 3 * (spS + h * spW), spS, spW


def run_config(P, sg, k=1.5, slip_m=SLIP_M, slip_s=SLIP_S, mode="net"):
    """Every signal of `sg`, simulated. Returns (trades DataFrame in goldlab.metrics.report format, counts)."""
    e, x = sg["e"], sg["x"]
    d = np.flatnonzero(sg["take"])
    S, W, h, sdpi = sg["S"][d], sg["W"][d], sg["h"][d], sg["sdpi"][d]
    floor_ok, spS, spW = spread_floor_ok(P, d, S, W, h, sdpi, e, k)
    res = sim_pairs(P, d, S, W, h, sdpi, e, x, k, slip_m, slip_s, mode)
    keep = res["filled"] & floor_ok
    counts = {"signals": int(len(d)), "not_filled_missing_bar": int((~res["filled"]).sum()),
              "refused_stop_floor": int((res["filled"] & ~floor_ok).sum()), "trades": int(keep.sum()),
              "exit_fallback_last_close": int(res["fallback"][keep].sum())}
    t = trades_frame(P, sg, d, S, W, h, sdpi, res, keep, k, spS, spW)
    return t, counts


def trades_frame(P, sg, d, S, W, h, sdpi, res, keep, k, spS=None, spW=None):
    e = sg["e"]
    t0m = P["t0m"][d]
    entry_time = pd.to_datetime((t0m + e) * MIN_NS, utc=True)
    exit_time = pd.to_datetime((t0m + res["xc"]) * MIN_NS, utc=True)
    side100 = np.where(S == 0, 1, np.where(W == 0, -1, 0))
    t = pd.DataFrame({
        "entry_time": entry_time, "exit_time": exit_time, "side": side100,
        "S": [SYMS[i] for i in S], "W": [SYMS[i] for i in W],
        "pair_type": [PAIR_TYPES[frozenset((a, b))] for a, b in zip(S, W)],
        "h": h, "sd_pi": sdpi, "k": k, "D": sg["D"][d], "Q": sg["Q"][d],
        "fill_S": res["fill_S"], "fill_W": res["fill_W"], "exit_S": res["exit_S"], "exit_W": res["exit_W"],
        "net_pi": res["net"], "money_ret": res["money"], "mid_pi_same_exits": res["mid_same"],
        "R": res["net"] / (k * sdpi), "R_money": res["money"] / (k * sdpi),
        "reason": np.where(res["stopped"], "stop", "time"), "stop_decision_col": res["u"],
        "hold_min": (res["xc"] - e).astype(float), "session": d,
    })
    t["ret"] = t["money_ret"]
    if spS is not None:
        t["spread_S_bp"], t["spread_W_bp"] = spS * 1e4, spW * 1e4
    t = t[keep].reset_index(drop=True)
    return t


# --------------------------------------------------------------------------------------------- reporting helpers
def pf(x):
    x = np.asarray(x, float)
    g, l = x[x > 0].sum(), -x[x < 0].sum()
    return float(g / l) if l > 0 else float("inf")


def summarize(t, gross_t=None):
    """goldlab.metrics.report plus the pair's own breakdowns (bp of N, pair types, side of us100)."""
    if len(t) == 0:
        return {"n": 0}
    rep = report(t)
    rep["net_bp_per_pair"] = round(float(t.net_pi.mean() * 1e4), 3)
    rep["mid_bp_per_pair_same_exits"] = round(float(t.mid_pi_same_exits.mean() * 1e4), 3)
    rep["cost_bp_per_pair"] = round(float((t.mid_pi_same_exits - t.net_pi).mean() * 1e4), 3)
    rep["money_expectancy_R"] = round(float(t.R_money.mean()), 4)
    rep["money_pf"] = round(pf(t.R_money), 3)
    rep["sd_pi_bp_median"] = round(float(t.sd_pi.median() * 1e4), 1)
    rep["h_median"] = round(float(t.h.median()), 3)
    rep["stop_share"] = round(float((t.reason == "stop").mean()), 3)
    if gross_t is not None and len(gross_t):
        rep["gross_bp_per_pair"] = round(float(gross_t.net_pi.mean() * 1e4), 3)
        rep["gross_pf"] = round(pf(gross_t.R), 3)
        rep["gross_expectancy_R"] = round(float(gross_t.R.mean()), 4)
    bt = {}
    for nm, g in t.groupby("pair_type"):
        bt[nm] = {"n": int(len(g)), "expectancy_R": round(float(g.R.mean()), 4), "pf": round(pf(g.R), 3),
                  "total_R": round(float(g.R.sum()), 1), "net_bp": round(float(g.net_pi.mean() * 1e4), 2),
                  "t": round(float(g.R.mean() / (g.R.std(ddof=1) / math.sqrt(len(g)))), 2) if len(g) > 2 else None}
    rep["by_pair_type"] = bt
    sides = {1: "us100_long", -1: "us100_short", 0: "us100_not_in_pair"}
    rep["by_side_of_us100"] = {sides[s]: {"n": int(len(g)), "expectancy_R": round(float(g.R.mean()), 4),
                                          "pf": round(pf(g.R), 3), "total_R": round(float(g.R.sum()), 1)}
                               for s, g in t.groupby("side")}
    rep["by_year_n"] = {int(y): int(n) for y, n in t.groupby(t.entry_time.dt.year).size().items()}
    return rep


def jdump(obj, path):
    def conv(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (np.bool_,)):
            return bool(o)
        if isinstance(o, (pd.Timestamp,)):
            return o.isoformat()
        return str(o)
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=conv)
