"""leadlag track - descriptive lead/lag study (IN-SAMPLE ONLY: reads the IS-only cache built from the
FP frames cut at 2022-01-01; no trading rule, no validation data).

For a directed pair (leader L -> follower F), on a regular one-minute grid:
  rL_k[t]  = leader mid log-return over the last k minutes, known at the CLOSE of bar t
  rF_k[t]  = follower's own return over the same k minutes
  u_k[t]   = beta[t] * rL_k[t] - rF_k[t]      ("leader move not yet matched"), beta = trailing 20-day
             OLS slope of follower 5-min returns on leader 5-min returns (past bars only)
  fwd_h[t] = follower mid return from the OPEN of bar t+1 (first tradable price after the leader bar
             closed) to the close of bar t+h           -> the tradable part
  gap[t]   = follower close[t] -> open[t+1]             -> NOT tradable (stale-quote catch-up)
Tails are defined on z = x / trailing sigma(x) (20 days, past only), at the IS 99th / 99.9th
percentile of |z|.  t-stats are clustered by day.
"""
import os
import sys

import numpy as np
import pandas as pd

LAB = "/home/user/gold-orb/lab"
if LAB not in sys.path:
    sys.path.insert(0, LAB)
CACHE = "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/ll"
SPEC = None


def spec():
    global SPEC
    if SPEC is None:
        import json
        SPEC = {k: v for k, v in json.load(open(os.path.join(LAB, "r2", "fp_costs.json"))).items() if not k.startswith("_")}
    return SPEC


def grid(sym, t0, t1, ffill=3):
    """Arrays on the minute grid [t0, t1): close (ffilled <= `ffill` min), open (NaN if no bar), spread bp."""
    z = np.load(os.path.join(CACHE, f"{sym}_is.npz"))
    tm = z["tmin"]
    keep = (tm >= t0) & (tm < t1)
    pos = tm[keep] - t0
    n = t1 - t0
    c = np.full(n, np.nan)
    o = np.full(n, np.nan)
    sp = np.full(n, np.nan, np.float32)
    c[pos] = z["mc"][keep]
    o[pos] = z["mo"][keep]
    sp[pos] = z["sp"][keep]
    has = np.isfinite(c)
    # limited forward fill of the close
    cf = c.copy()
    last = np.where(has, np.arange(n), -1)
    np.maximum.accumulate(last, out=last)
    age = np.arange(n) - last
    ok = (last >= 0) & (age <= ffill)
    cf = np.where(ok, c[np.maximum(last, 0)], np.nan)
    return cf, o, sp, has


def lret(c, k):
    out = np.full(len(c), np.nan)
    out[k:] = np.log(c[k:] / c[:-k])
    return out


def trailing_beta(rl5, rf5, win=5760, minobs=1000):
    """rl5, rf5: 5-minute returns sampled every 5th minute (non-overlapping). Trailing OLS slope through
    the origin over the last `win` slots, lagged one slot (past only)."""
    v = np.isfinite(rl5) & np.isfinite(rf5)
    x = np.where(v, rl5, 0.0)
    y = np.where(v, rf5, 0.0)
    sxy = pd.Series(x * y).rolling(win, min_periods=1).sum().to_numpy()
    sxx = pd.Series(x * x).rolling(win, min_periods=1).sum().to_numpy()
    cnt = pd.Series(v.astype(float)).rolling(win, min_periods=1).sum().to_numpy()
    b = np.where((cnt >= minobs) & (sxx > 0), sxy / np.where(sxx > 0, sxx, 1), np.nan)
    return np.r_[np.nan, b[:-1]]


def trailing_sigma(x, win=28800, minobs=5000):
    """Trailing RMS of x over the last `win` minutes (20 days), lagged one minute."""
    v = np.isfinite(x)
    s2 = pd.Series(np.where(v, x * x, 0.0)).rolling(win, min_periods=1).sum().to_numpy()
    cnt = pd.Series(v.astype(float)).rolling(win, min_periods=1).sum().to_numpy()
    s = np.where(cnt >= minobs, np.sqrt(s2 / np.maximum(cnt, 1)), np.nan)
    return np.r_[np.nan, s[:-1]]


def clustered(x, y, day):
    """Slope through the origin of y on x with day-clustered t; x, y finite."""
    sxx = float((x * x).sum())
    if sxx <= 0 or len(x) < 50:
        return np.nan, np.nan
    b = float((x * y).sum() / sxx)
    e = y - b * x
    g = pd.Series(x * e).groupby(day).sum().to_numpy()
    se = np.sqrt((g ** 2).sum()) / sxx
    return b, b / se if se > 0 else np.nan


def mean_t(v, day):
    """Mean of v with day-clustered t."""
    if len(v) < 5:
        return np.nan, np.nan
    g = pd.Series(v).groupby(day).sum().to_numpy()
    s = np.sqrt((g ** 2).sum())
    return float(v.mean()), float(v.sum() / s) if s > 0 else np.nan


def study(L, F, sessions, ks=(1, 5, 15), hs=(1, 5, 15, 30), start="2014-01-01", end="2022-01-01", years=False):
    """sessions: dict name -> boolean function of (ny_minute_of_day, berlin_minute_of_day, weekday) arrays."""
    t0 = int(pd.Timestamp(start, tz="UTC").value // 60_000_000_000)
    t1 = int(pd.Timestamp(end, tz="UTC").value // 60_000_000_000)
    cL, oL, spL, hasL = grid(L, t0, t1)
    cF, oF, spF, hasF = grid(F, t0, t1)
    n = t1 - t0
    ts = pd.DatetimeIndex((np.arange(n) + t0).astype("int64") * 60_000_000_000, tz="UTC")
    ny = ts.tz_convert("America/New_York")
    be = ts.tz_convert("Europe/Berlin")
    nym = (ny.hour * 60 + ny.minute).to_numpy()
    bem = (be.hour * 60 + be.minute).to_numpy()
    wd = ny.dayofweek.to_numpy()
    year = ts.year.to_numpy()
    day = ((np.arange(n) + t0 + 7 * 60 - 5 * 60) // 1440)          # ~17:00 NY trading day (clustering only)
    del ts, ny, be
    # trailing beta from non-overlapping 5-min returns
    rl5 = lret(cL, 5)
    rf5 = lret(cF, 5)
    sl = slice(4, None, 5)
    b5 = trailing_beta(rl5[sl], rf5[sl])
    beta = np.full(n, np.nan)
    beta[sl] = b5
    beta = pd.Series(beta).ffill(limit=5).to_numpy()
    both_live = hasL & hasF
    rt_cost = np.full(n, np.nan)
    rt_cost[:-1] = spF[1:] + 2 * spec()[F]["slip_mkt_bps"]            # spread of the entry bar + 2 x market slippage
    rows = []
    fw = {}
    oF1 = np.r_[oF[1:], np.nan]
    for h in hs:
        ch = np.r_[cF[h:], np.full(h, np.nan)]
        fw[h] = np.log(ch / oF1) * 1e4
    gap = np.log(oF1 / cF) * 1e4
    sess_masks = {nm: fn(nym, bem, wd) for nm, fn in sessions.items()}
    for k in ks:
        rl = lret(cL, k) * 1e4
        rf = lret(cF, k) * 1e4
        preds = {"lead": rl, "unmatched": beta * rl - rf}
        for pn, x in preds.items():
            x = np.where(hasL, x, np.nan)                            # leader bar must exist at t (fresh quote)
            sg = trailing_sigma(x)
            z = x / sg
            for sn, sm in sess_masks.items():
                base = sm & np.isfinite(z) & np.isfinite(oF1) & np.isfinite(gap)
                if base.sum() < 5000:
                    continue
                az = np.abs(z[base])
                q99, q999 = np.quantile(az, [0.99, 0.999])
                for h in hs:
                    y = fw[h]
                    m = base & np.isfinite(y)
                    b, tb = clustered(x[m], y[m], day[m])
                    row = {"L": L, "F": F, "sess": sn, "pred": pn, "k": k, "h": h, "n": int(m.sum()),
                           "slope": round(b, 4), "t_slope": round(tb, 1)}
                    for tn, q in (("1%", q99), ("0.1%", q999)):
                        mt = m & (np.abs(z) >= q)
                        sgn = np.sign(x[mt])
                        mu, tt = mean_t(sgn * y[mt], day[mt])
                        mg, _ = mean_t(sgn * gap[mt], day[mt])
                        row.update({f"n_{tn}": int(mt.sum()), f"days_{tn}": int(len(np.unique(day[mt]))),
                                    f"absx_{tn}": round(float(np.abs(x[mt]).mean()), 1),
                                    f"fwd_{tn}": round(mu, 2), f"t_{tn}": round(tt, 1),
                                    f"gap_{tn}": round(mg, 2),
                                    f"cost_{tn}": round(float(np.nanmean(rt_cost[mt])), 2)})
                        if years and tn == "1%":
                            yy = pd.Series(sgn * y[mt]).groupby(year[mt]).mean().round(2)
                            row["by_year_1%"] = " ".join(f"{a}:{v}" for a, v in yy.items())
                    rows.append(row)
    return pd.DataFrame(rows)


# session masks (ny minute of day, berlin minute of day, weekday)
S_ALL = lambda ny, be, wd: np.ones(len(ny), bool)
S_USCASH = lambda ny, be, wd: (ny >= 570) & (ny < 955) & (wd < 5)                 # 09:30-15:55 NY
S_PREUS = lambda ny, be, wd: (ny >= 120) & (ny < 570) & (wd < 5)                  # 02:00-09:30 NY (Europe)
S_NIGHT = lambda ny, be, wd: ((ny >= 1080) | (ny < 120))                          # 18:00-02:00 NY (Asia)
S_XETRA = lambda ny, be, wd: (be >= 540) & (be < 1050) & (wd < 5)                 # 09:00-17:30 Berlin
S_EUREX_PM = lambda ny, be, wd: (be >= 1050) & (be < 1320) & (wd < 5)             # 17:30-22:00 Berlin
S_DAXOFF = lambda ny, be, wd: ((be >= 1320) | (be < 480))                         # 22:00-08:00 Berlin (synthetic DAX)
S_EUAM = lambda ny, be, wd: (be >= 480) & (be < 540) & (wd < 5)                   # 08:00-09:00 Berlin
