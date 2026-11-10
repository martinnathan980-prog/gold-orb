"""Descriptive statistics on the IN-SAMPLE period only (bars before 2022-01-01). No trading rule, no costs.

Purpose: decide which rule families deserve engine trials (trend persistence by horizon, breakout
follow-through, session momentum). Every table printed here is listed in the report with its number of cells.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/gold-orb/lab")
import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402

OUT = "/home/user/gold-orb/lab/results/r2/crypto"
IS_END = "2022-01-01"
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 40)
pd.set_option("display.max_rows", 400)


def h1_frame(sym):
    m1 = r2.load(sym, end=IS_END)
    mid_o = (m1.bo + m1.ao) / 2
    mid_h = (m1.bh + m1.ah) / 2
    mid_l = (m1.bl + m1.al) / 2
    mid_c = (m1.bc + m1.ac) / 2
    g = pd.DataFrame({"o": mid_o, "h": mid_h, "l": mid_l, "c": mid_c, "n": 1.0})
    h = g.resample("1h", label="left", closed="left").agg({"o": "first", "h": "max", "l": "min", "c": "last", "n": "sum"})
    h = h[h.n > 0]
    r2.free()
    return h


def wk_t(x, idx):
    """t-stat of the mean of x with weekly clustering (mean of weekly sums / its standard error)."""
    s = pd.Series(np.asarray(x, float), index=idx).dropna()
    if len(s) < 30:
        return float("nan")
    w = s.groupby(s.index.tz_localize(None).to_period("W")).sum()
    cnt = s.groupby(s.index.tz_localize(None).to_period("W")).size()
    # ratio estimator: mean = sum(w)/sum(cnt); se via weekly residuals
    m = w.sum() / cnt.sum()
    res = w - m * cnt
    se = np.sqrt((res ** 2).sum()) / cnt.sum()
    return float(m / se) if se > 0 else float("nan")


res = {}
for sym in ("btcusd", "ethusd"):
    h = h1_frame(sym)
    # regular hourly grid; hours with no data are NaN (closures / holes)
    full = pd.date_range(h.index[0], h.index[-1], freq="1h")
    c = h.c.reindex(full)
    lc = np.log(c)
    d = {}
    # ---- 1. variance ratios of hourly returns, by year (hours inside holes dropped)
    r1 = lc.diff()
    vr = {}
    for y in sorted(set(full.year)):
        row = {}
        v1 = r1[r1.index.year == y].var()
        for k in (2, 4, 8, 24, 48, 96):
            rk = lc.diff(k)
            row[k] = round(float(rk[rk.index.year == y].var() / (k * v1)), 3)
        vr[int(y)] = row
    d["variance_ratio_by_year"] = vr
    print(sym, "variance ratios (k hours vs 1 hour) by year")
    print(pd.DataFrame(vr).T.to_string())
    # ---- 2. time-series momentum: sign of past L-hour return -> next H-hour return (bp), evaluated every 4 hours
    rows = []
    step = c.index.hour % 4 == 0
    for L in (4, 12, 24, 72, 168):
        past = lc - lc.shift(L)
        for H in (4, 12, 24):
            fwd = lc.shift(-H) - lc
            x = (np.sign(past) * fwd)[step].dropna()
            row = {"L": L, "H": H, "mean_bp": round(float(x.mean() * 1e4), 1), "t_wk": round(wk_t(x.values, x.index), 2)}
            for y in sorted(set(x.index.year)):
                row[str(y)] = round(float(x[x.index.year == y].mean() * 1e4), 1)
            lg = (fwd[step][past[step] > 0]).dropna()
            sh = (-fwd[step][past[step] < 0]).dropna()
            row["long_bp"] = round(float(lg.mean() * 1e4), 1)
            row["short_bp"] = round(float(sh.mean() * 1e4), 1)
            rows.append(row)
    d["tsmom"] = rows
    print(sym, "TSMOM: sign(past L h) x next H h return, bp, sampled every 4 h")
    print(pd.DataFrame(rows).to_string(index=False))
    # ---- 3. breakout follow-through: H1 close beyond the prior N-bar high/low (bars, not hours) -> next H hours
    hb = h.copy()
    rows = []
    for N in (24, 72, 168):
        up = hb.h.rolling(N).max().shift(1)
        dn = hb.l.rolling(N).min().shift(1)
        sig = np.where(hb.c > up, 1, np.where(hb.c < dn, -1, 0))
        sig = pd.Series(sig, index=hb.index)
        # first breakout of a run: no same-direction breakout in the previous 6 bars
        prev_same = pd.concat([(sig.shift(k) == sig) for k in range(1, 7)], axis=1).any(axis=1)
        first = (sig != 0) & ~prev_same
        for H in (4, 12, 24, 48):
            fwd = (lc.shift(-H) - lc).reindex(hb.index)
            for label, mask in (("all", sig != 0), ("first", first)):
                x = (sig * fwd)[mask].dropna()
                row = {"N": N, "H": H, "events": label, "n": int(len(x)), "mean_bp": round(float(x.mean() * 1e4), 1),
                       "t_wk": round(wk_t(x.values, x.index), 2),
                       "long_bp": round(float(fwd[mask & (sig > 0)].mean() * 1e4), 1),
                       "short_bp": round(float(-fwd[mask & (sig < 0)].mean() * 1e4), 1)}
                for y in sorted(set(x.index.year)):
                    row[str(y)] = round(float(x[x.index.year == y].mean() * 1e4), 1)
                rows.append(row)
    d["breakout"] = rows
    print(sym, "Breakout follow-through: close beyond prior N-bar extreme -> signed next-H-hour return (bp)")
    print(pd.DataFrame(rows).to_string(index=False))
    # unconditional drift for comparison (bp per H hours)
    d["drift_bp"] = {H: round(float((lc.shift(-H) - lc).mean() * 1e4), 1) for H in (4, 12, 24, 48)}
    print("unconditional drift bp:", d["drift_bp"])
    # ---- 4. hour-of-day volatility (abs hourly return, bp) and weekday/weekend vol
    ar = r1.abs() * 1e4
    d["abs_ret_bp_by_hour_utc"] = {int(k): round(float(v), 1) for k, v in ar.groupby(ar.index.hour).median().items()}
    we = ar.index.dayofweek >= 5
    d["abs_ret_bp_weekday_median"] = round(float(ar[~we].median()), 1)
    d["abs_ret_bp_weekend_median"] = round(float(ar[we].median()), 1)
    print("median |1h ret| bp by UTC hour:", d["abs_ret_bp_by_hour_utc"])
    print("weekday", d["abs_ret_bp_weekday_median"], "weekend", d["abs_ret_bp_weekend_median"])
    # ---- 5. session momentum (UTC): Asia 00-08, Europe 08-13, US 13-21, late 21-24
    days = pd.date_range(full[0].normalize(), full[-1].normalize(), freq="D")
    px = lambda hh, off=0: lc.reindex(days + pd.Timedelta(hours=hh) + pd.Timedelta(days=off))
    seg = {"asia": (px(8).values - px(0).values), "eu": (px(13).values - px(8).values),
           "us": (px(21).values - px(13).values), "late": (px(0, 1).values - px(21).values),
           "prev24": (px(0).values - px(0, -1).values)}
    S = pd.DataFrame(seg, index=days)
    rows = []
    for a, b in (("asia", "eu"), ("asia", "us"), ("eu", "us"), ("us", "late"), ("prev24", "asia"), ("prev24", "eu"), ("prev24", "us")):
        if a == "us" and b == "late":
            x = (np.sign(S[a]) * S[b]).dropna()
        else:
            x = (np.sign(S[a]) * S[b]).dropna()
        row = {"signal": a, "traded": b, "n": int(len(x)), "mean_bp": round(float(x.mean() * 1e4), 1),
               "t": round(float(x.mean() / x.std() * np.sqrt(len(x))), 2)}
        for y in sorted(set(x.index.year)):
            row[str(y)] = round(float(x[x.index.year == y].mean() * 1e4), 1)
        rows.append(row)
    # next-day same-session continuation (us -> next asia)
    x = (np.sign(S["us"]) * S["asia"].shift(-1)).dropna()
    row = {"signal": "us", "traded": "next asia", "n": int(len(x)), "mean_bp": round(float(x.mean() * 1e4), 1),
           "t": round(float(x.mean() / x.std() * np.sqrt(len(x))), 2)}
    for y in sorted(set(x.index.year)):
        row[str(y)] = round(float(x[x.index.year == y].mean() * 1e4), 1)
    rows.append(row)
    d["session_momentum"] = rows
    print(sym, "Session momentum: sign(signal session return) x traded session return (bp)")
    print(pd.DataFrame(rows).to_string(index=False))
    res[sym] = d

json.dump(res, open(os.path.join(OUT, "descriptive_is.json"), "w"), indent=1, default=str)
