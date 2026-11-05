"""Descriptive IS-only control (no trading rule): after a 24h move crosses +-z, does gold keep going?
Compare three signals on H1 (crossing events, past-only rolling sd/beta):
  res : cumulative gold residual vs rolling-beta USD basket (as in diverge_orders)
  gold: cumulative raw gold return (plain time-series momentum, no cross-asset info)
  usd : beta * cumulative USD basket return (the dollar-driven part of gold's move)
Forward gold return (bp) over the next 24h / 72h, sign-adjusted in the direction of the signal.
Round-trip cost ~ 5.9 bp."""
import warnings

import numpy as np
import pandas as pd

import strategy as S
from common import load_bars

warnings.filterwarnings("ignore")
cache = {(s, tf): load_bars(s, tf) for s in ["xauusd", "eurusd", "gbpusd", "usdjpy"] for tf in ["1h"]}
P = S.xpanel(None, None, "1h", S.USD, cache)
P = P[P.index < pd.Timestamp("2022-01-01", tz="UTC")]
g, u = P.g, P.u
v = g.notna() & u.notna()
win = 1380
beta = S.roll_beta(g, u, win).shift(1)
res = (g - beta * u).where(v)
lg = np.log(P.close)
for n in (12, 24, 72):
    comps = {"res": res, "gold": g.where(v), "usd": (beta * u).where(v)}
    rows = []
    for name, x in comps.items():
        z = x.rolling(n, min_periods=int(0.8 * n)).sum() / (S._sd(x, win) * np.sqrt(n))
        for zin in (1.5, 2.0):
            up = (z > zin) & (z.shift(1) <= zin)
            dn = (z < -zin) & (z.shift(1) >= -zin)
            for k in (24, 72):
                fut = (lg.shift(-k) - lg) * 1e4
                f = pd.concat([fut[up], -fut[dn]]).dropna()
                yrs = f.groupby(f.index.year).mean()
                rows.append({"n": n, "sig": name, "z": zin, "k": k, "events": len(f),
                             "mean_bp": round(f.mean(), 1), "t": round(f.mean() / f.std() * np.sqrt(len(f)), 2),
                             "up_mean": round(fut[up].mean(), 1), "dn_mean": round(-fut[dn].mean(), 1),
                             "yrs+": f"{int((yrs > 0).sum())}/{len(yrs)}"})
    print(pd.DataFrame(rows).to_string(index=False))
print("corr(res, gold) h1:", round(res.corr(g), 3))
