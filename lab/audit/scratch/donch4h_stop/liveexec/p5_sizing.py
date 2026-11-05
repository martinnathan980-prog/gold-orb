"""P5: minimum position size and margin (MT5 XAUUSD: 1 lot = 100 oz, min lot 0.01 = 1 oz, step 0.01;
ESMA retail leverage 1:20 on gold = 5 % margin).  Stop distance = 2 x ATR14(4h) per oz.
"""
import sys
sys.path.insert(0, "/home/user/gold-orb/lab/audit/scratch/donch4h_stop/liveexec")
import numpy as np
import pandas as pd
from common import HERE, gl, is_part, val_part

EURUSD = 1.17   # approx. late-2025 level, used only to express account sizes in EUR
t = pd.read_pickle(f"{HERE}/trades_base.pkl")
o = pd.read_pickle(f"{HERE}/orders_base.pkl")
m1 = gl.load_m1("xauusd")
tv = val_part(t, "sizing-2025-stop-distance-and-dollar-PF")
# all touched brackets (incl. those not taken), dated by their trigger time
ob = pd.DataFrame({"entry_time": m1.index[o.trig_i.to_numpy()], "risk": o.stop_dist.to_numpy(),
                   "px": o.level.to_numpy()})
obv = val_part(ob, "sizing-2025-bracket-stop-distance")
for lab, d, px in (("2025 trades", tv[tv.entry_time.dt.year == 2025].risk, tv[tv.entry_time.dt.year == 2025].entry),
                   ("Q4-2025 trades", tv[tv.entry_time >= pd.Timestamp("2025-10-01", tz="UTC")].risk,
                    tv[tv.entry_time >= pd.Timestamp("2025-10-01", tz="UTC")].entry),
                   ("2025 brackets", obv[obv.entry_time.dt.year == 2025].risk, obv[obv.entry_time.dt.year == 2025].px),
                   ("IS 2013-21 trades", is_part(t).risk, is_part(t).entry)):
    q = np.percentile(d, [5, 10, 50, 90, 95])
    print(f"{lab:18s} n={len(d):4d} stop $/oz p5 {q[0]:.1f} p10 {q[1]:.1f} median {q[2]:.1f} p90 {q[3]:.1f} p95 {q[4]:.1f} | "
          f"price median {np.median(px):.0f} | stop as % of price median {100*np.median(d/px):.2f}%")
d25 = tv[tv.entry_time.dt.year == 2025]
med = float(np.median(d25.risk)); p10 = float(np.percentile(d25.risk, 10)); p90 = float(np.percentile(d25.risk, 90))
pxm = float(np.median(d25.entry)); pxq4 = float(np.median(tv[tv.entry_time >= pd.Timestamp("2025-10-01", tz="UTC")].entry))
print(f"\nmedian 2025 stop = ${med:.1f}/oz -> 0.01 lot (1 oz) risks ${med:.0f}")
for r in (0.005, 0.01):
    for nm, rk in (("median", med), ("p90", p90), ("p10", p10)):
        a1 = rk / r
        print(f"  risk {r:.1%} @ {nm} stop ${rk:.1f}: account for 1 x 0.01 lot = ${a1:,.0f} (EUR {a1/EURUSD:,.0f}); "
              f"for <=10% rounding error (>=10 steps) = ${10*a1:,.0f} (EUR {10*a1/EURUSD:,.0f})")
for nm, px in (("2025 median price", pxm), ("Q4-2025 median price", pxq4)):
    print(f"margin 1:20 per 0.01 lot at {nm} ${px:,.0f}: ${px/20:,.0f} | notional per 0.01 lot ${px:,.0f}")
for r in (0.005, 0.01):
    lev = pxm * r / med
    print(f"risk {r:.1%}, median stop: notional/equity = {lev:.2f}x, margin used = {100*lev/20:.1f}% of equity; "
          f"at p10 stop: {pxm*r/p10:.2f}x, margin {100*pxm*r/p10/20:.1f}%")


def dollar_run(tt, A, r):
    risk = tt.risk.to_numpy(); pnl = tt.pnl.to_numpy()
    lots = np.floor(A * r / (risk * 100) / 0.01 + 1e-9) * 0.01
    under = lots < 0.01
    lots = np.where(under, 0.01, lots)                        # what the EA does (LotsForRisk returns vmin)
    oz = lots * 100
    eff = oz * risk / A
    usd = pnl * oz
    g, l = usd[usd > 0].sum(), -usd[usd < 0].sum()
    return {"pf_usd": round(g / l, 3), "eff_risk_med%": round(100 * np.median(eff), 2), "eff_risk_p90%": round(100 * np.percentile(eff, 90), 2),
            "eff_risk_max%": round(100 * eff.max(), 2), "min_lot_forced%": round(100 * under.mean(), 1),
            "net_usd": round(usd.sum(), 0)}


Rv = tv.R.to_numpy(); pfR = Rv[Rv > 0].sum() / -Rv[Rv < 0].sum()
print(f"\nVAL 2022-25 (n={len(tv)}): PF in R = {pfR:.3f}; fixed account, floor-to-0.01 sizing, min lot forced:")
for A in (2000, 5000, 10000, 25000, 50000):
    for r in (0.005, 0.01):
        print(f"  ${A:>6,} (EUR {A/EURUSD:,.0f}) risk {r:.1%}: {dollar_run(tv, A, r)}")
ti = is_part(t)
Ri = ti.R.to_numpy(); print(f"IS 2013-21 (n={len(ti)}): PF in R = {Ri[Ri>0].sum()/-Ri[Ri<0].sum():.3f}")
for A in (2000, 5000, 10000):
    for r in (0.005, 0.01):
        print(f"  ${A:>6,} risk {r:.1%}: {dollar_run(ti, A, r)}")
