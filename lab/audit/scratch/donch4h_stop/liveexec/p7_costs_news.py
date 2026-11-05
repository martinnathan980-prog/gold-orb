"""P7: execution-cost elasticity that matters for a retail MT5 account.
  - clustering of fills at US data releases (08:30 ET etc.), extra entry slippage there
  - slippage per side 3 / 5 bp on every market/stop fill (engine Costs)
  - broker swaps 8 %/3 % and 10 %/4 % per year (long/short)
"""
import sys
from dataclasses import replace
sys.path.insert(0, "/home/user/gold-orb/lab/audit/scratch/donch4h_stop/liveexec")
import numpy as np
import pandas as pd
from common import COSTS, HERE, fmt, gl, is_part, stats, val_part

m1 = gl.load_m1("xauusd")
o = pd.read_pickle(f"{HERE}/orders_base.pkl")
t = pd.read_pickle(f"{HERE}/trades_base.pkl")
ny = pd.DatetimeIndex(t.entry_time).tz_convert("America/New_York")
hm = ny.hour * 60 + ny.minute
news = ((hm >= 8 * 60 + 30) & (hm < 8 * 60 + 35)) | ((hm >= 10 * 60) & (hm < 10 * 60 + 5)) | ((hm >= 14 * 60) & (hm < 14 * 60 + 5))
n830 = (hm >= 8 * 60 + 30) & (hm < 8 * 60 + 35)
frames = []
x = t.copy(); x["v"] = "base"; frames.append(x)
x = t[~news].copy(); x["v"] = "excl_news_minutes"; frames.append(x)
x = t[news].copy(); x["v"] = "only_news_minutes"; frames.append(x)
for bp in (5, 10, 20):
    x = t.copy()
    extra = np.where(news, x.entry.to_numpy() * bp * 1e-4, 0.0)
    x["R"] = (x.pnl - extra) / x.risk
    x["v"] = f"news_entry_extra_{bp}bp"; frames.append(x)
for sl in (3.0, 5.0):
    x = gl.simulate(m1, o, costs=replace(COSTS["xauusd"], slip_bps=sl)); x["v"] = f"slip_{sl:.0f}bp_all_fills"; frames.append(x)
for sw in ((0.08, 0.03), (0.10, 0.04)):
    x = gl.simulate(m1, o, costs=replace(COSTS["xauusd"], swap_long=sw[0], swap_short=sw[1])); x["v"] = f"swap_{sw[0]:.2f}_{sw[1]:.2f}"; frames.append(x)
allf = pd.concat(frames, ignore_index=True, sort=False)
isf = is_part(allf)
valf = val_part(allf, "news-minute-fills-slippage-swap-elasticity")
for v in allf.v.unique():
    print(f"{v:26s} | IS {fmt(stats(isf[isf.v == v]))}\n{'':26s} | VAL {fmt(stats(valf[valf.v == v]))}")
ti = is_part(t)
nyi = pd.DatetimeIndex(ti.entry_time).tz_convert("America/New_York")
hmi = nyi.hour * 60 + nyi.minute
print("IS fills by NY minute-of-hour bucket around 08:30 ET:",
      {f"08:{m:02d}": int(((hmi == 8 * 60 + m)).sum()) for m in range(28, 36)})
print(f"IS fills in 08:30-08:34 ET: {int(((hmi >= 510) & (hmi < 515)).sum())} of {len(ti)} "
      f"(R {ti.R.to_numpy()[(hmi >= 510) & (hmi < 515)].sum():+.1f}); any news minute: {int(news[: len(t)][(t.entry_time < pd.Timestamp('2022-01-01', tz='UTC')).to_numpy()].sum())}")
mean_risk_bp = float(np.median(ti.risk / ti.entry) * 1e4)
print(f"IS median stop distance = {mean_risk_bp:.0f} bp of price -> 1 bp of extra slippage per side = {2/mean_risk_bp:.3f} R per round trip")
