"""P5: minimum position size and margin (MT5 XAUUSD: 1 lot = 100 oz, min 0.01 lot = 1 oz, step 0.01;
ESMA retail leverage 1:20 on gold -> margin 5 % of notional; margin close-out at 50 % margin level).
Stop distance = |fill - stop| per oz.  Uses VAL trades (2022-2025), 2025 in particular.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa: F401,F403

t = pd.read_pickle(os.path.join(HERE, "trades_base.pkl"))
tv = val_part(t, "sizing: 2022-2025 stop distances, lot rounding, ESMA 1:20 margin, drawdowns")
ti = is_part(t)
y25 = tv[tv.entry_time.dt.year == 2025]
q = lambda x: {p: round(float(np.percentile(x, p)), 2) for p in (5, 10, 25, 50, 75, 90, 95)}
print("2025: n", len(y25), "stop distance $/oz percentiles:", q(y25.risk), "min", round(y25.risk.min(), 2),
      "max", round(y25.risk.max(), 2), "| mean entry price", round(y25.entry.mean(), 0))
for yr, g in tv.groupby(tv.entry_time.dt.year):
    print(f"  {yr}: median stop ${g.risk.median():.2f}  (p10 {g.risk.quantile(.1):.2f}, p90 {g.risk.quantile(.9):.2f}) "
          f"median as % of price {100 * (g.risk / g.entry).median():.3f}%")
print("IS median stop $", round(ti.risk.median(), 2), "| as % of price", round(100 * (ti.risk / ti.entry).median(), 3))
med = y25.risk.median()
for r in (0.005, 0.01):
    print(f"risk {r:.1%}: account for 0.01 lot (1 oz) at the 2025 median stop = ${med / r:,.0f}; "
          f"at p90 ${y25.risk.quantile(.9) / r:,.0f}; at max ${y25.risk.max() / r:,.0f}")

rows = []
for E in (1000, 2000, 3000, 5000, 10000, 20000, 50000):
    for r in (0.005, 0.01):
        ideal_oz = r * E / y25.risk.to_numpy()
        lots = np.floor(ideal_oz / 1.0 + 1e-9) / 100        # 0.01 lot = 1 oz, round down
        oz = lots * 100
        skip = oz < 1                                          # min lot would exceed target risk
        oz_forced = np.maximum(oz, 1)                          # alternative: force the min lot
        act = oz * y25.risk.to_numpy() / E
        act_f = oz_forced * y25.risk.to_numpy() / E
        marg = oz_forced * y25.entry.to_numpy() / 20 / E       # margin as share of equity
        Rr = y25.R.to_numpy()
        # $ result of 2025 with exact fractional sizing vs lot-rounded (skip) vs forced min lot (no compounding)
        pnl_exact = (Rr * r * E).sum()
        pnl_round = (Rr * act * E).sum()
        pnl_force = (Rr * act_f * E).sum()
        rows.append({"equity_usd": E, "risk": f"{r:.1%}", "skip_share": round(float(skip.mean()), 3),
                     "act_risk_med%": round(float(np.median(act[~skip]) * 100), 3) if (~skip).any() else None,
                     "act_risk_p5%": round(float(np.percentile(act[~skip], 5) * 100), 3) if (~skip).any() else None,
                     "forced_risk_max%": round(float(act_f.max() * 100), 2),
                     "margin_med%": round(float(np.median(marg) * 100), 1), "margin_p95%": round(float(np.percentile(marg, 95) * 100), 1),
                     "margin_max%": round(float(marg.max() * 100), 1),
                     "pnl2025_exact": round(pnl_exact), "pnl2025_lots_skip": round(pnl_round), "pnl2025_minlot_forced": round(pnl_force)})
res = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(res.to_string(index=False))
res.to_csv(os.path.join(HERE, "p5_sizing.csv"), index=False)


def dd_stats(g, r):
    R = g.R.to_numpy()
    eq = np.cumprod(1 + R * r)
    peak = np.maximum.accumulate(eq)
    dd = 1 - eq / peak
    cum = np.cumsum(R)
    ddR = (np.maximum.accumulate(np.r_[0, cum]) - np.r_[0, cum]).max()
    # longest losing streak and longest underwater stretch (trades)
    ls, cur = 0, 0
    for x in R:
        cur = cur + 1 if x < 0 else 0
        ls = max(ls, cur)
    uw, cu = 0, 0
    for i in range(len(eq)):
        cu = cu + 1 if eq[i] < peak[i] else 0
        uw = max(uw, cu)
    return {"maxDD_R": round(float(ddR), 1), f"maxDD_%@{r:.1%}": round(float(dd.max() * 100), 1),
            "losing_streak": ls, "underwater_trades": uw}


for nm, g in (("IS", ti), ("VAL", tv)):
    for r in (0.005, 0.01):
        print(nm, dd_stats(g, r))
# underwater duration in calendar time (VAL, 1 %)
R = tv.R.to_numpy()
cum = np.cumsum(R)
pk = np.maximum.accumulate(cum)
at_peak = tv.exit_time.dt.tz_convert(None).to_numpy()[cum >= pk]
gaps = np.diff(np.r_[tv.entry_time.dt.tz_convert(None).min().to_datetime64(), at_peak, tv.exit_time.dt.tz_convert(None).max().to_datetime64()]).astype("timedelta64[D]").astype(int)
print("VAL longest time between equity highs (days):", int(gaps.max()))
R = ti.R.to_numpy(); cum = np.cumsum(R); pk = np.maximum.accumulate(cum)
at_peak = ti.exit_time.dt.tz_convert(None).to_numpy()[cum >= pk]
gaps = np.diff(np.r_[ti.entry_time.dt.tz_convert(None).min().to_datetime64(), at_peak, ti.exit_time.dt.tz_convert(None).max().to_datetime64()]).astype("timedelta64[D]").astype(int)
print("IS longest time between equity highs (days):", int(gaps.max()))
