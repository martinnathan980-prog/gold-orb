"""Descriptive map (IS only, 2014-2021, mid prices, no costs, no stops): which documented intraday effects
exist at all in this data?  Not a strategy evaluation; cells are counted in the report as soft trials."""
import sys, json
sys.path.insert(0, "/home/user/gold-orb/lab"); sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/idx_us")
import numpy as np, pandas as pd
import goldlab as gl
from goldlab import r2
import idxus_lib as cm

def tstat(x):
    x = x[np.isfinite(x)]
    return (len(x), round(float(x.mean()), 2), round(float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))), 2)) if len(x) > 5 else (len(x), np.nan, np.nan)

out = {}
for sym in ["us100", "us500", "us30"]:
    m1 = r2.load(sym, start="2014-01-01", end="2022-01-01")
    g = cm.grid(m1)
    P, dts, half = g["P"], g["dates"], g["half"]
    yrs = np.array([d.year for d in dts])
    D = len(dts)
    op = P[:, 0]; cl = P[:, 390]
    prev_cl = np.r_[np.nan, cl[:-1]]
    # previous session must be the previous row and a full day
    prev_ok = np.r_[False, ~half[:-1]]
    prev_cl = np.where(prev_ok, prev_cl, np.nan)
    reg = ~half
    bp = lambda a, b: (b / a - 1) * 1e4
    res = {}
    # A. scales
    oc = np.abs(bp(op, cl))[reg]
    res["A_abs_open_close_bp_median"] = round(float(np.nanmedian(oc)), 1)
    res["A_abs_open_close_bp_by_year"] = {int(y): round(float(np.nanmedian(np.abs(bp(op, cl))[reg & (yrs == y)])), 1) for y in np.unique(yrs)}
    for m in (5, 15, 30):
        res[f"A_abs_move_first_{m}min_bp_median"] = round(float(np.nanmedian(np.abs(bp(op, P[:, m]))[reg])), 1)
    res["A_abs_last30_bp_median"] = round(float(np.nanmedian(np.abs(bp(P[:, 360], cl))[reg])), 1)
    # B. last half hour
    y_last = bp(P[:, 360], P[:, 389])          # 15:30 -> 15:59
    y_last60 = bp(P[:, 330], P[:, 389])
    xs = {"first30(prevclose->10:00)": bp(prev_cl, P[:, 30]), "rod(prevclose->15:30)": bp(prev_cl, P[:, 360]),
          "intraday(open->15:30)": bp(op, P[:, 360]), "mid(12:00->15:30)": bp(P[:, 150], P[:, 360]), "last(15:00->15:30)": bp(P[:, 330], P[:, 360])}
    for k, x in xs.items():
        ok = reg & np.isfinite(x) & np.isfinite(y_last)
        c = np.corrcoef(x[ok], y_last[ok])[0, 1]
        res[f"B_{k}_corr"] = round(float(c), 3)
        res[f"B_{k}_sign_trade_bp(n,mean,t)"] = tstat((np.sign(x) * y_last)[ok])
        res[f"B_{k}_sign_trade_by_year_bp"] = {int(y): round(float(np.nanmean((np.sign(x) * y_last)[ok & (yrs == y)])), 2) for y in np.unique(yrs)}
    x = xs["rod(prevclose->15:30)"]
    ok = reg & np.isfinite(x) & np.isfinite(y_last60)
    res["B_rod15:00_last60_sign_trade_bp"] = tstat((np.sign(bp(prev_cl, P[:, 330])) * y_last60)[ok])
    # conditional on the size of the day's move relative to its trailing 20-day median |move|
    ax = pd.Series(np.abs(x)); med = ax.rolling(20, min_periods=10).median().shift(1).to_numpy()
    for lab, cond in (("big(|x|>1.0*med)", np.abs(x) > med), ("vbig(|x|>2*med)", np.abs(x) > 2 * med), ("small(|x|<=med)", np.abs(x) <= med)):
        okc = reg & np.isfinite(x) & np.isfinite(y_last) & np.isfinite(med) & cond
        res[f"B_rod_{lab}_bp"] = tstat((np.sign(x) * y_last)[okc])
    # C. noise area: first breach at 30-min checks
    marks = np.arange(30, 361, 30)
    absmove = np.abs(P / op[:, None] - 1)
    sig = pd.DataFrame(absmove).rolling(14, min_periods=14).mean().shift(1).to_numpy()   # past 14 sessions only
    hi_ref = np.fmax(op, prev_cl); lo_ref = np.fmin(op, prev_cl)
    hi_ref = np.where(np.isfinite(prev_cl), hi_ref, op); lo_ref = np.where(np.isfinite(prev_cl), lo_ref, op)
    UB = hi_ref[:, None] * (1 + sig); LB = lo_ref[:, None] * (1 - sig)
    first = np.full(D, -1); side = np.zeros(D)
    for d in range(D):
        if not reg[d]: continue
        for m in marks:
            p = P[d, m]
            if not np.isfinite(p) or not np.isfinite(sig[d, m]): continue
            if p > UB[d, m]: first[d], side[d] = m, 1; break
            if p < LB[d, m]: first[d], side[d] = m, -1; break
    has = first > 0
    fut = np.full(D, np.nan); fut_next = np.full(D, np.nan)
    for d in np.nonzero(has)[0]:
        fut[d] = side[d] * bp(P[d, first[d]], P[d, 385])
    res["C_noise_first_breach_to_15:55_bp(n,mean,t)"] = tstat(fut[has])
    res["C_noise_long_bp"] = tstat(fut[has & (side > 0)]); res["C_noise_short_bp"] = tstat(fut[has & (side < 0)])
    res["C_noise_by_year_bp"] = {int(y): (int((has & (yrs == y)).sum()), round(float(np.nanmean(fut[has & (yrs == y)])), 2)) for y in np.unique(yrs)}
    res["C_noise_by_breach_time_bp"] = {f"{(570 + int(m)) // 60:02d}:{(570 + int(m)) % 60:02d}": tstat(fut[has & (first == m)]) for m in marks}
    res["C_noise_days_with_breach_pct"] = round(float(has[reg].mean() * 100), 1)
    # unconditional drift for reference: open->15:55 long
    res["Z_drift_open_to_1555_bp"] = tstat(bp(op, P[:, 385])[reg]); res["Z_drift_1530_to_1559_bp"] = tstat(y_last[reg])
    res["Z_drift_overnight(prevclose->open)_bp"] = tstat(bp(prev_cl, op)[reg])
    # D. opening-candle direction
    for m in (5, 15, 30, 60):
        s = np.sign(bp(op, P[:, m])); y = bp(P[:, m], P[:, 385])
        ok = reg & np.isfinite(s) & np.isfinite(y)
        res[f"D_dir_first_{m}min_then_hold_to_15:55_bp"] = tstat((s * y)[ok])
    # E. gap
    gap = bp(prev_cl, op)
    for lab, y in (("open->10:30", bp(op, P[:, 60])), ("open->15:55", bp(op, P[:, 385]))):
        ok = reg & np.isfinite(gap) & np.isfinite(y)
        res[f"E_gap_sign_x_{lab}_bp"] = tstat((np.sign(gap) * y)[ok])
        gmed = pd.Series(np.abs(gap)).rolling(20, min_periods=10).median().shift(1).to_numpy()
        okb = ok & np.isfinite(gmed) & (np.abs(gap) > 2 * gmed)
        res[f"E_biggap(>2xmed)_sign_x_{lab}_bp"] = tstat((np.sign(gap) * y)[okb])
    out[sym] = res
    print("=====", sym)
    for k, v in res.items():
        print(f"  {k}: {v}")
    r2.free(); del m1
json.dump(out, open("/home/user/gold-orb/lab/results/r2/idx_us/desc_map_is.json", "w"), indent=1, default=str)
