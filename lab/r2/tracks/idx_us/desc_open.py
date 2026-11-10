"""Descriptive study 2 (IS only, mid prices, no costs, no stops): direction of the opening candle -> rest of day.
Profile over the day, dependence on the candle length, by year, long/short, candle size."""
import sys, json
sys.path.insert(0, "/home/user/gold-orb/lab"); sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/idx_us")
import numpy as np, pandas as pd
import goldlab as gl
from goldlab import r2
import idxus_lib as cm

def ts(x):
    x = x[np.isfinite(x)]
    return (len(x), round(float(x.mean()), 2), round(float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))), 2)) if len(x) > 5 else (len(x), np.nan, np.nan)

out = {}
bp = lambda a, b: (b / a - 1) * 1e4
for sym in ["us100", "us500", "us30"]:
    m1 = r2.load(sym, start="2014-01-01", end="2022-01-01")
    g = cm.grid(m1)
    P, dts, half = g["P"], g["dates"], g["half"]
    yrs = np.array([d.year for d in dts]); reg = ~half
    op = P[:, 0]
    res = {}
    # 1. candle length dependence: sign(open->n) x (n -> 15:55)
    res["1_len_dependence_bp"] = {n: ts((np.sign(bp(op, P[:, n])) * bp(P[:, n], P[:, 385]))[reg]) for n in (1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 30, 45, 60, 90, 120)}
    # 2. profile for n = 5: cumulative signed return from 09:35 to mark
    s5 = np.sign(bp(op, P[:, 5]))
    marks = [10, 15, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330, 360, 385, 389]
    res["2_profile_n5_bp"] = {f"{(570 + m) // 60:02d}:{(570 + m) % 60:02d}": ts((s5 * bp(P[:, 5], P[:, m]))[reg]) for m in marks}
    # 3. by year, long/short
    y5 = s5 * bp(P[:, 5], P[:, 385])
    res["3_by_year_n5_bp"] = {int(y): ts(y5[reg & (yrs == y)]) for y in np.unique(yrs)}
    res["3_long_n5_bp"] = ts(y5[reg & (s5 > 0)]); res["3_short_n5_bp"] = ts(y5[reg & (s5 < 0)])
    res["3_share_long"] = round(float((s5[reg] > 0).mean()), 3)
    # 4. candle size relative to trailing median |5-min move| (20 sessions, past only)
    a5 = np.abs(bp(op, P[:, 5])); med = pd.Series(a5).rolling(20, min_periods=10).median().shift(1).to_numpy()
    rel = a5 / med
    for lab, c in (("rel<0.5", rel < 0.5), ("0.5-1", (rel >= 0.5) & (rel < 1)), ("1-2", (rel >= 1) & (rel < 2)), (">=2", rel >= 2)):
        res[f"4_size_{lab}_bp"] = ts(y5[reg & np.isfinite(rel) & c])
    # 5. does the overnight gap direction agree? (gap = prev close -> open)
    cl = P[:, 390]; prev_cl = np.r_[np.nan, cl[:-1]]
    gap = bp(prev_cl, op)
    res["5_gap_same_dir_bp"] = ts(y5[reg & (np.sign(gap) == s5)]); res["5_gap_opp_dir_bp"] = ts(y5[reg & (np.sign(gap) == -s5)])
    # 6. weekday
    wd = np.array([d.weekday() for d in dts])
    res["6_weekday_bp"] = {int(k): ts(y5[reg & (wd == k)]) for k in range(5)}
    # 7. std of the outcome (bp) and scale of the candle range
    res["7_std_outcome_bp"] = round(float(np.nanstd(y5[reg])), 1)
    out[sym] = res
    print("=====", sym)
    for k, v in res.items():
        print(f"  {k}: {v}")
    r2.free(); del m1
json.dump(out, open("/home/user/gold-orb/lab/results/r2/idx_us/desc_open_is.json", "w"), indent=1, default=str)
