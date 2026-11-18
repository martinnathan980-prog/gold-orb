"""Power count for idea 011 from the signal data alone (z of the ETH/BTC log ratio at 16:00 NY; no return, no price move after a signal).
Run: EXPLORE_CACHE=~/explore_data/idea_011 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/011_eth_btc_ratio/power.py"""
import os, sys
import numpy as np, pandas as pd
from kit import data
eth = data.load_bars("ethusd"); btc = data.load_bars("btcusd")
print("eth", eth.index[0], eth.index[-1], len(eth), "btc", btc.index[0], btc.index[-1], len(btc))
def c16(b):
    loc = b.index.tz_convert("America/New_York")
    m = (loc.hour == 15) & (loc.minute == 0) & (loc.dayofweek < 5)
    s = b["close"][m]; return pd.Series(s.to_numpy(float), index=s.index + pd.Timedelta(hours=1))
j = pd.concat([c16(eth), c16(btc)], axis=1, join="inner").dropna()
c = pd.Series(np.log(j.iloc[:, 0] / j.iloc[:, 1]).to_numpy(), index=j.index)
print("daily values", len(c), c.index[0], c.index[-1])
for lb in (15, 20, 30):
    p = c.shift(1).rolling(lb, min_periods=lb); z = (c - p.mean()) / p.std(ddof=1)
    for zin in (1.5, 2.0, 2.5):
        a = z.abs() >= zin
        first = a & ~a.shift(1, fill_value=False)
        # flat-gated entries: z exit |z|<=0.5 or 5 days (counted on days, from z alone)
        n = 0; hold = -1; k_in = None; zz = z.to_numpy()
        for i in range(len(zz)):
            if k_in is not None:
                if abs(zz[i]) <= 0.5 or i - k_in >= 5: k_in = None
                else: continue
            if np.isfinite(zz[i]) and abs(zz[i]) >= zin: n += 1; k_in = i
        print(f"lb {lb} zin {zin}: days {int(a.sum())}, first crossings {int(first.sum())}, gated entries ~{n}")

# Information only (not a declared rule): the same z at 4 clocks a day (each clock against its own 20 previous daily values),
# flat-gated entries across clocks with the z exit or 5 trading days (20 clock steps).
zs = []
for h in (3, 9, 15, 21):   # New York bar-open hours
    def ch(b, h=h):
        loc = b.index.tz_convert("America/New_York")
        m = (loc.hour == h) & (loc.dayofweek < 5)
        s = b["close"][m]; return pd.Series(s.to_numpy(float), index=s.index + pd.Timedelta(hours=1))
    jj = pd.concat([ch(eth), ch(btc)], axis=1, join="inner").dropna()
    cc = pd.Series(np.log(jj.iloc[:, 0] / jj.iloc[:, 1]).to_numpy(), index=jj.index)
    p = cc.shift(1).rolling(20, min_periods=20); zs.append((cc - p.mean()) / p.std(ddof=1))
z4 = pd.concat(zs).sort_index().to_numpy()
n = 0; k_in = None
for i in range(len(z4)):
    if k_in is not None:
        if abs(z4[i]) <= 0.5 or i - k_in >= 20: k_in = None
        else: continue
    if np.isfinite(z4[i]) and abs(z4[i]) >= 2: n += 1; k_in = i
print("4 clocks a day, zin 2: gated entries ~", n, "of", int((np.abs(z4) >= 2).sum()), "clock values beyond 2")
