"""Independent re-computation (the lead's, not the scan's code) of the scan's first candidate on the real bars:
K01|H1|F0|24h on gbpusd = follow an hourly move beyond 3 sd of the 500 previous hourly returns, hold 24 h, stop 2 x D20.
The signal is recomputed here from the bars; the trades go through kit.sim.simulate (the judge's simulator)."""
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, "lab/explore")
from kit import data as D, sim, stats as ST, costs as C

b = D.load_bars("gbpusd")
print("bars", len(b), b.index[0], b.index[-1], list(b.columns)[:8], b.attrs.get("source"))
c = b["close"].to_numpy(float)
r = np.full(len(c), np.nan)
r[1:] = np.log(c[1:] / c[:-1])
z = np.full(len(c), np.nan)
for t in range(501, len(c)):                       # plain loop on purpose: the 500 returns t-500 .. t-1
    w = r[t - 500:t]
    z[t] = r[t] / w.std(ddof=1)
up = z > 3
dn = z < -3
ok_prev = ~np.isnan(np.roll(z, 1))
ok_prev[0] = False
buy = up & ~np.roll(up, 1) & ok_prev
sell = dn & ~np.roll(dn, 1) & ok_prev
idx = pd.DatetimeIndex(b.index)
ka = idx + pd.Timedelta(hours=1)
sig = pd.concat([pd.DataFrame({"known_at": ka[buy], "side": 1}), pd.DataFrame({"known_at": ka[sell], "side": -1})])
sig = sig.sort_values("known_at").reset_index(drop=True)
print("signals", len(sig), "buy", int(buy.sum()), "sell", int(sell.sum()))
tr = sim.simulate(sig, b, exit=("hours", 24), stop=("d20", 2.0), mode="one", max_wait_h=None, market="gbpusd")
et = pd.DatetimeIndex(tr["entry_time"])
for name, m in (("discovery (<2019)", et < pd.Timestamp("2019-01-01", tz="UTC")),
                ("confirmation 2019-2021", (et >= pd.Timestamp("2019-01-01", tz="UTC")) & (et < pd.Timestamp("2022-01-01", tz="UTC")))):
    g = tr[np.asarray(m)]
    R = g["R"].to_numpy(float)
    pf = R[R > 0].sum() / -R[R < 0].sum()
    day = C.trading_day(pd.DatetimeIndex(g["entry_time"]))
    ds = pd.Series(R).groupby(np.asarray(day)).sum()
    t = ds.mean() / (ds.std(ddof=1) / np.sqrt(len(ds)))
    yrs = pd.Series(R).groupby(np.asarray(pd.DatetimeIndex(g["entry_time"]).year)).agg(["size", "sum"])
    print(f"{name}: n {len(g)}, PF {pf:.4f}, mean R {R.mean():.5f}, gross {g['R_gross'].mean():.5f}, t(daily) {t:.3f}, "
          f"long {int((g['side'] > 0).sum())} short {int((g['side'] < 0).sum())}")
    print(yrs.round(2).T.to_string())
    top = g.assign(R=R).nlargest(5, "R")[["entry_time", "side", "R"]]
    print("  five best trades:", [(str(a)[:16], int(s), round(float(x), 2)) for a, s, x in top.to_numpy()])
    print("  share of the total R from the best 5 trades:", round(float(top["R"].sum() / R.sum()), 2) if R.sum() else None)
