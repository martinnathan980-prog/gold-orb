"""LETF_CLOSE_PAIR (PROTOCOL_V3 Addendum J, rule 5): Nasdaq-100 against the Dow in the last half hour of big days.
Shared code. IN SAMPLE ONLY: every frame is read with the parquet row filter ts < 2022-01-01 (load_is) and the slices
are passed explicitly to every function. The frozen rule and the readings of open details are in
results/r2/round4/letf_close_pair/declared.json (written before any run; R1..R23 below refer to it).

Pipeline (everything takes the in-sample frames explicitly):
    frames = load_frames()                          # us100, us30, us500, ts < 2022-01-01
    cal = calendar()                                # NYSE trading days (full + early closes), sessions = full ones
    P  = prepare(build_grid(frames, cal["tdays"]))  # per trading day x minute (15:00 .. 16:59 New York) quotes
    sg = signals(P, cal, **params)                  # d, sd_d, condition, h, sd_pi (previous sessions only)
    t, counts = run_config(P, sg, params)           # two-leg simulation of every signal -> trades frame

Causality: the decision of session j uses the close of the 15:29 bar of day j (known at 15:30), the close of the
previous session's 15:59 bar, and trailing statistics of sessions strictly before j (pandas rolling(...).shift(1));
the stop is decided on the close of bar t and executed at the open of bar t + 1. truncation.py rebuilds everything
on frames cut at decision times and compares.

The two-leg simulator mirrors IDXRS_1000's (r2/tracks/round4/idxrs_1000/common.sim_pairs: same fills, same mark at
exit-side closes, same stop timing, same fallbacks), with explicit sides per leg (us100 can be long or short) and a
grid that reaches 16:59 for the 16:05 exit neighbour; crosscheck_idxrs.py compares the two on every pair of the main.
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
import idxus_lib  # noqa: E402  NYSE calendar of noise30 / ocm4 / IDXRS_1000 (imported read-only)
from goldlab.metrics import report  # noqa: E402
from goldlab.sim import apply_spread_mult  # noqa: E402

CUT = pd.Timestamp("2022-01-01", tz="UTC")
LOAD_FROM = pd.Timestamp("2013-09-01", tz="UTC")   # nothing earlier is needed (first session 2013-09-30)
NY = "America/New_York"
OUT = os.path.join(LAB, "results", "r2", "round4", "letf_close_pair")
SPEC = {k: v for k, v in json.load(open(os.path.join(LAB, "r2", "fp_costs.json"))).items() if not k.startswith("_")}
SYMS = ("us100", "us30", "us500")
LEG = {s: i for i, s in enumerate(SYMS)}
G0 = 900            # grid column 0 = the bar starting 15:00 New York
NMIN = 120          # columns = bars starting 15:00 ... 16:59
MIN_NS = 60_000_000_000
CAL_FIRST = "2013-09-16"         # trading-day calendar starts before the first session (its previous trading day)
FIRST_SESSION = "2013-09-30"     # first day of the us30 frame (R1)
LAST_SESSION = "2021-12-31"
SLIP_M = SPEC["us100"]["slip_mkt_bps"] * 1e-4      # 0.2 bp, identical for us100 / us30 / us500
SLIP_S = SPEC["us100"]["slip_stop_bps"] * 1e-4     # 0.5 bp
assert all(SPEC[s]["slip_mkt_bps"] == 0.2 and SPEC[s]["slip_stop_bps"] == 0.5 for s in SYMS)


# --------------------------------------------------------------------------------------------- data
def load_is(sym, cut=CUT, cols=("bo", "bc", "ao", "ac")):
    """In-sample M1 frame: rows with 2013-09-01 <= ts < 2022-01-01 00:00 UTC, filtered while reading."""
    assert pd.Timestamp(cut) <= CUT
    df = pd.read_parquet(os.path.join(LAB, "data", "fp", f"{sym}_m1.parquet"), columns=list(cols),
                         filters=[("ts", ">=", LOAD_FROM), ("ts", "<", pd.Timestamp(cut))])
    assert len(df) and df.index.max() < CUT and df.index.is_monotonic_increasing and df.index.is_unique
    return df


def load_frames(cost_mult=1.0, syms=SYMS):
    """In-sample frames; cost_mult != 1: widened by the lab's own goldlab.sim.apply_spread_mult (which needs the eight
    quote columns, mid unchanged), then reduced to the four columns used here."""
    if cost_mult == 1.0:
        return {s: load_is(s) for s in syms}
    out = {}
    for s in syms:
        f = apply_spread_mult(load_is(s, cols=("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac")), cost_mult)
        out[s] = f[["bo", "bc", "ao", "ac"]].copy()
        del f
    return out


def calendar(first=CAL_FIRST, last=LAST_SESSION, first_session=FIRST_SESSION):
    """NYSE trading days (weekdays that are not full closures), their early-close flag, and the sessions (R1, R3):
    full sessions from `first_session`, each with the grid row of its previous trading day."""
    days = pd.bdate_range(first, last)
    full, half = idxus_lib.calendar_flags([d.date() for d in days])
    tdays, half = days[~full], half[~full]
    srow = np.flatnonzero((~half) & (tdays >= pd.Timestamp(first_session)))
    assert srow.min() >= 1
    return {"tdays": tdays, "half": half, "srow": srow, "prev_row": srow - 1, "prev_half": half[srow - 1],
            "sessions": tdays[srow]}


def _tmin(index):
    return pd.DatetimeIndex(index).as_unit("ns").asi8 // MIN_NS


def build_grid(frames, tdays):
    """Quotes of the bar that STARTS at 15:00 + m New York (m = 0..119) of each trading day; NaN if no such bar."""
    t0 = (tdays + pd.Timedelta(minutes=G0)).tz_localize(NY).tz_convert("UTC")
    t0m = _tmin(t0)
    T = (t0m[:, None] + np.arange(NMIN)[None, :]).ravel()
    G = {"tdays": tdays, "t0m": t0m}
    for s in SYMS:
        if s not in frames:
            continue
        df = frames[s]
        tm = _tmin(df.index)
        pos = np.searchsorted(tm, T)
        posc = np.minimum(pos, len(tm) - 1)
        hit = (pos < len(tm)) & (tm[posc] == T)
        for c in ("bo", "bc", "ao", "ac"):
            v = df[c].to_numpy(np.float64)
            G[(s, c)] = np.where(hit, v[posc], np.nan).reshape(len(tdays), NMIN)
    return G


def ffill2(a):
    """Forward fill along minutes inside each trading day of the grid."""
    col = np.arange(a.shape[1])[None, :]
    last = np.where(np.isfinite(a), col, -1)
    np.maximum.accumulate(last, axis=1, out=last)
    out = np.take_along_axis(a, np.maximum(last, 0), axis=1)
    out[last < 0] = np.nan
    return out


def bfill2(a):
    """Back fill along minutes: the quote of the first bar at or after each minute (inside the grid)."""
    return ffill2(a[:, ::-1])[:, ::-1]


def prepare(G):
    """Stacked (3, R, NMIN) arrays in SYMS order: exact bars, forward-filled closes, back-filled opens; mids.
    A symbol absent from the grid is all-NaN."""
    shape = (len(G["tdays"]), NMIN)
    st = lambda c: np.stack([G.get((s, c), np.full(shape, np.nan)) for s in SYMS])
    P = {"tdays": G["tdays"], "t0m": G["t0m"]}
    for c in ("bo", "bc", "ao", "ac"):
        P[c] = st(c)
    P["mo"] = (P["bo"] + P["ao"]) / 2
    P["mc"] = (P["bc"] + P["ac"]) / 2
    for c in ("bc", "ac", "mc"):
        P[c + "_ff"] = np.stack([ffill2(P[c][i]) for i in range(len(SYMS))])
    for c in ("bo", "ao", "mo"):
        P[c + "_bf"] = np.stack([bfill2(P[c][i]) for i in range(len(SYMS))])
    return P


# --------------------------------------------------------------------------------------------- signals
def _roll_sd(a, win, minv):
    """Sample sd (ddof=1) over the finite values among the previous `win` sessions (current excluded), >= minv."""
    return pd.Series(a).rolling(int(win), min_periods=int(minv)).std(ddof=1).shift(1).to_numpy()


def signals(P, cal, sig_min=930, hed_e=930, hed_x=959, thr=1.25, leg2="us30", win=60, minv=40, **_ignored):
    """Signal of every session (R2-R7). Arrays are indexed by session (cal['sessions'])."""
    L2 = LEG[leg2]
    rows, prow = cal["srow"], cal["prev_row"]
    cs, c59 = sig_min - 1 - G0, 959 - G0                               # the 15:29 bar; the previous session's 15:59 bar
    assert 0 <= cs < NMIN and 0 <= hed_e - G0 < hed_x - G0 < NMIN
    mc_sig = P["mc"][:, rows, cs]                                      # (3, D) exact bars (R2)
    mc_prev = np.where(cal["prev_half"][None, :], np.nan, P["mc"][:, prow, c59])    # R3: NaN after an early close
    with np.errstate(invalid="ignore", divide="ignore"):
        d = np.log(mc_sig / mc_prev)
        ret = np.log(P["mo"][:, rows, hed_x - G0] / P["mo"][:, rows, hed_e - G0])  # mid open -> mid open (R6)
    d100, d2 = d[0], d[L2]
    sd_d = _roll_sd(d100, win, minv)                                   # R5
    sdA, sdB = _roll_sd(ret[0], win, minv), _roll_sd(ret[L2], win, minv)
    with np.errstate(invalid="ignore", divide="ignore"):
        h = sdA / sdB                                                  # R6
    dirn = np.where(np.isfinite(d100) & (d100 != 0), np.sign(d100), np.nan)
    pi = dirn * (ret[0] - h * ret[L2])                                 # R7: every session, traded or not
    sdpi = _roll_sd(pi, win, minv)
    with np.errstate(invalid="ignore"):
        cond = (np.isfinite(d100) & np.isfinite(d2) & (d100 != 0) & (d2 != 0) & (np.sign(d100) == np.sign(d2))
                & np.isfinite(sd_d) & (np.abs(d100) >= thr * sd_d))   # R4
        take = cond & np.isfinite(h) & (h > 0) & np.isfinite(sdpi) & (sdpi > 0)
    return {"rows": rows, "L2": L2, "d": d, "d100": d100, "d2": d2, "sd_d": sd_d, "ret": ret, "sdA": sdA, "sdB": sdB,
            "h": h, "dir": dirn, "pi": pi, "sdpi": sdpi, "cond": cond, "take": take,
            "params": dict(sig_min=sig_min, hed_e=hed_e, hed_x=hed_x, thr=thr, leg2=leg2, win=win, minv=minv)}


# --------------------------------------------------------------------------------------------- two-leg simulator
def _pick(P, key_long, key_short, leg, rows, cols, side):
    """Quote of `leg` on grid rows `rows` (n,) at columns `cols` ((n,) or (n, m)): key_long where side > 0, else
    key_short."""
    rr = rows if np.ndim(cols) == 1 else rows[:, None]
    ss = side if np.ndim(cols) == 1 else side[:, None]
    return np.where(ss > 0, P[key_long][leg][rr, cols], P[key_short][leg][rr, cols])


def sim_pairs(P, rows, L2, dirs, h, sdpi, e, x, k, slip_m=SLIP_M, slip_s=SLIP_S, mode="net"):
    """Simulate n pairs on grid rows `rows`: us100 side = dir (notional N), leg L2 side = -dir (notional h N), both
    filled at the open of column e; pair mark pi on the close of each bar e .. x-1 (R9); stop when pi <= -k sdpi,
    executed at the next open; else exit at the open of the first bar at / after column x (R10).
    mode 'net' = bid/ask + slippage; 'mid' = mid prices, no slippage."""
    rows = np.asarray(rows, np.int64)
    dirs = np.asarray(dirs, float)
    h, sdpi = np.asarray(h, float), np.asarray(sdpi, float)
    n = len(rows)
    sA, sB = dirs, -dirs
    ce = np.full(n, e, np.int64)
    if mode == "net":
        fA = np.where(sA > 0, P["ao"][0][rows, e] * (1 + slip_m), P["bo"][0][rows, e] * (1 - slip_m))
        fB = np.where(sB > 0, P["ao"][L2][rows, e] * (1 + slip_m), P["bo"][L2][rows, e] * (1 - slip_m))
        km, kx, kc = ("bc_ff", "ac_ff"), ("bo_bf", "ao_bf"), ("bc_ff", "ac_ff")
    elif mode == "mid":
        fA, fB = P["mo"][0][rows, e], P["mo"][L2][rows, e]
        km, kx, kc = ("mc_ff", "mc_ff"), ("mo_bf", "mo_bf"), ("mc_ff", "mc_ff")
        slip_m = slip_s = 0.0
    else:
        raise ValueError(mode)
    filled = np.isfinite(fA) & np.isfinite(fB)
    cols = e + np.arange(x - e)[None, :].repeat(n, axis=0)
    mA = _pick(P, km[0], km[1], 0, rows, cols, sA)
    mB = _pick(P, km[0], km[1], L2, rows, cols, sB)
    with np.errstate(invalid="ignore", divide="ignore"):
        pim = sA[:, None] * np.log(mA / fA[:, None]) + h[:, None] * sB[:, None] * np.log(mB / fB[:, None])
        hit = (pim <= -(k * sdpi)[:, None]) if np.isfinite(k) else np.zeros_like(pim, bool)
    stopped = hit.any(axis=1) & filled
    u = np.where(stopped, hit.argmax(axis=1), -1)                         # column offset of the stop decision
    xc = np.where(stopped, e + u + 1, x).astype(np.int64)                  # execution column
    qA = _pick(P, kx[0], kx[1], 0, rows, xc, sA)
    qB = _pick(P, kx[0], kx[1], L2, rows, xc, sB)
    fb = ~(np.isfinite(qA) & np.isfinite(qB))                              # no bar at / after: last known close
    qA = np.where(np.isfinite(qA), qA, _pick(P, kc[0], kc[1], 0, rows, xc - 1, sA))
    qB = np.where(np.isfinite(qB), qB, _pick(P, kc[0], kc[1], L2, rows, xc - 1, sB))
    sl = np.where(stopped, slip_s, slip_m)
    eA = np.where(sA > 0, qA * (1 - sl), qA * (1 + sl))
    eB = np.where(sB > 0, qB * (1 - sl), qB * (1 + sl))
    with np.errstate(invalid="ignore", divide="ignore"):
        net = sA * np.log(eA / fA) + h * sB * np.log(eB / fB)
        money = sA * (eA / fA - 1) + h * sB * (eB / fB - 1)
    # mid-price result of the same entry / exit minutes (cost = mid result - net result)
    mfA, mfB = P["mo"][0][rows, ce], P["mo"][L2][rows, ce]
    mxA = np.where(np.isfinite(P["mo_bf"][0][rows, xc]), P["mo_bf"][0][rows, xc], P["mc_ff"][0][rows, xc - 1])
    mxB = np.where(np.isfinite(P["mo_bf"][L2][rows, xc]), P["mo_bf"][L2][rows, xc], P["mc_ff"][L2][rows, xc - 1])
    with np.errstate(invalid="ignore", divide="ignore"):
        mid_same = sA * np.log(mxA / mfA) + h * sB * np.log(mxB / mfB)
    return {"filled": filled, "stopped": stopped, "u": u, "xc": xc, "fill_A": fA, "fill_B": fB, "exit_A": eA,
            "exit_B": eB, "net": net, "money": money, "mid_same": mid_same, "fallback": fb & filled, "pim": pim}


def spread_floor_ok(P, rows, L2, h, sdpi, e, k):
    """Hard rule 4 (R12): refuse a pair whose stop k x sd_pi is closer than 3 x (spread_us100 + h x spread_leg2)."""
    spA = (P["ao"][0][rows, e] - P["bo"][0][rows, e]) / P["mo"][0][rows, e]
    spB = (P["ao"][L2][rows, e] - P["bo"][L2][rows, e]) / P["mo"][L2][rows, e]
    with np.errstate(invalid="ignore"):
        ok = (k * sdpi) >= 3 * (spA + h * spB)
    return ok, spA, spB


def run_config(P, sg, p, slip_m=SLIP_M, slip_s=SLIP_S, mode="net"):
    """Every signal of `sg`, simulated with the entry / exit / stop of `p`. Returns (trades frame in
    goldlab.metrics.report format, counts)."""
    e, x, k, L2 = p["entry_min"] - G0, p["exit_min"] - G0, float(p["k"]), sg["L2"]
    assert 0 < e < x < NMIN
    j = np.flatnonzero(sg["take"])
    rows, dirs, h, sdpi = sg["rows"][j], sg["dir"][j], sg["h"][j], sg["sdpi"][j]
    floor_ok, spA, spB = spread_floor_ok(P, rows, L2, h, sdpi, e, k)
    res = sim_pairs(P, rows, L2, dirs, h, sdpi, e, x, k, slip_m, slip_s, mode)
    keep = res["filled"] & floor_ok
    counts = {"signals": int(len(j)), "not_filled_missing_entry_bar": int((~res["filled"]).sum()),
              "refused_stop_floor": int((res["filled"] & ~floor_ok).sum()), "trades": int(keep.sum()),
              "exit_fallback_last_close": int(res["fallback"][keep].sum())}
    t = trades_frame(P, sg, j, rows, dirs, h, sdpi, res, keep, k, e, spA, spB)
    return t, counts


def trades_frame(P, sg, j, rows, dirs, h, sdpi, res, keep, k, e, spA, spB):
    t0m = P["t0m"][rows]
    t = pd.DataFrame({
        "entry_time": pd.to_datetime((t0m + e) * MIN_NS, utc=True),
        "exit_time": pd.to_datetime((t0m + res["xc"]) * MIN_NS, utc=True),
        "side": dirs.astype(np.int64), "dir": dirs.astype(np.int64), "leg2": SYMS[sg["L2"]],
        "h": h, "sd_pi": sdpi, "k": k, "d_us100": sg["d100"][j], "d_leg2": sg["d2"][j], "sd_d": sg["sd_d"][j],
        "fill_us100": res["fill_A"], "fill_leg2": res["fill_B"], "exit_us100": res["exit_A"], "exit_leg2": res["exit_B"],
        "net_pi": res["net"], "money_ret": res["money"], "mid_pi_same_exits": res["mid_same"],
        "R": res["net"] / (k * sdpi), "R_money": res["money"] / (k * sdpi),
        "reason": np.where(res["stopped"], "stop", "time"), "stop_decision_col": res["u"],
        "hold_min": (res["xc"] - e).astype(float), "session": j, "row": rows,
        "spread_us100_bp": spA * 1e4, "spread_leg2_bp": spB * 1e4, "exit_fallback": res["fallback"],
    })
    t["ret"] = t["money_ret"]
    return t[keep].reset_index(drop=True)


# --------------------------------------------------------------------------------------------- reporting helpers
def pf(x):
    x = np.asarray(x, float)
    g, l = x[x > 0].sum(), -x[x < 0].sum()
    return float(g / l) if l > 0 else float("inf")


def tstat(x):
    x = np.asarray(x, float)
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan")


def summarize(t, gross_t=None):
    """goldlab.metrics.report plus the pair's own breakdowns (bp of N, direction of the day, years)."""
    if len(t) == 0:
        return {"n": 0}
    rep = report(t)
    rep["net_bp_per_pair"] = round(float(t.net_pi.mean() * 1e4), 3)
    rep["mid_bp_per_pair_same_exits"] = round(float(t.mid_pi_same_exits.mean() * 1e4), 3)
    rep["cost_bp_per_pair"] = round(float((t.mid_pi_same_exits - t.net_pi).mean() * 1e4), 3)
    rep["money_expectancy_R"] = round(float(t.R_money.mean()), 4)
    rep["money_pf"] = round(pf(t.R_money), 3)
    rep["sd_pi_bp_median"] = round(float(t.sd_pi.median() * 1e4), 2)
    rep["h_median"] = round(float(t.h.median()), 3)
    rep["stop_share"] = round(float((t.reason == "stop").mean()), 3)
    if gross_t is not None and len(gross_t):
        rep["gross_n"] = int(len(gross_t))
        rep["gross_bp_per_pair"] = round(float(gross_t.net_pi.mean() * 1e4), 3)
        rep["gross_pf"] = round(pf(gross_t.R), 3)
        rep["gross_expectancy_R"] = round(float(gross_t.R.mean()), 4)
        rep["gross_t"] = round(tstat(gross_t.R), 2)
    names = {1: "d>0: long us100 / short leg2", -1: "d<0: short us100 / long leg2"}
    rep["by_direction"] = {names[s]: {"n": int(len(g)), "expectancy_R": round(float(g.R.mean()), 4),
                                      "pf": round(pf(g.R), 3), "total_R": round(float(g.R.sum()), 1),
                                      "t": round(tstat(g.R), 2), "net_bp": round(float(g.net_pi.mean() * 1e4), 2),
                                      "stop_share": round(float((g.reason == "stop").mean()), 3)}
                           for s, g in t.groupby("dir")}
    rep["by_year_n"] = {int(y): int(n) for y, n in t.groupby(t.entry_time.dt.year).size().items()}
    rep["by_year_pf"] = {int(y): round(pf(g.R), 3) for y, g in t.groupby(t.entry_time.dt.year)}
    rep["by_year_net_bp"] = {int(y): round(float(g.net_pi.mean() * 1e4), 2) for y, g in t.groupby(t.entry_time.dt.year)}
    rep["first_entry"], rep["last_entry"] = str(t.entry_time.min()), str(t.entry_time.max())
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
