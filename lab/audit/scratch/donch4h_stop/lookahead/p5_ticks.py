"""P5: tick-level calibration (Jun-Dec 2025 ticks = VAL period; access logged through gl.cut).
 1. M1 bar labelling convention: M1 bar at T vs ticks in [T, T+1m) and in [T-1m, T).
 2. Timezone: minute of day (UTC) of the daily spread maximum, summer vs winter.
 3. Fill fidelity per trade, entry and exit separately: tick fill vs M1 fill (zero costs), and the
    'fast-market' fraction of the M1 trigger bar's range beyond the level that ticks actually cost.
"""
import glob
import sys
import time

sys.path.insert(0, ".")
sys.path.insert(0, "tracks/trend")
sys.path.insert(0, "audit")
import numpy as np
import pandas as pd

import goldlab as gl
import strategy as S
from goldlab.sim import Costs
from tick_sim import covered_span, tick_simulate

T0 = time.time()
m1 = gl.load_m1("xauusd")
fr = []
for f in sorted(glob.glob("../download/xauusd-tick-2025-*.csv.gz")):
    d = pd.read_csv(f, dtype={"timestamp": np.int64, "askPrice": np.float64, "bidPrice": np.float64})
    fr.append(d)
tk = pd.concat(fr).drop_duplicates("timestamp").sort_values("timestamp")
del fr
ts = tk.timestamp.to_numpy(np.int64) * 1_000_000
bid, ask = tk.bidPrice.to_numpy(), tk.askPrice.to_numpy()
del tk
print(f"ticks {len(ts):,}  {pd.Timestamp(ts[0], tz='UTC')} -> {pd.Timestamp(ts[-1], tz='UTC')}  ({time.time()-T0:.0f}s)")

# ---- 1. labelling: compare bid OHLC of M1 bars with tick aggregates in [T, T+1) vs [T-1, T)
sub = m1[(m1.index >= "2025-07-01") & (m1.index < "2025-07-08")]
mins = ts // 60_000_000_000
for shift, lab in ((0, "[T,T+1m)"), (1, "[T-1m,T)")):
    g = pd.DataFrame({"m": mins + shift, "b": bid}).groupby("m").b.agg(["first", "max", "min", "last"])
    key = sub.index.as_unit("ns").asi8 // 60_000_000_000
    gg = g.reindex(key)
    ok = gg.notna().all(axis=1).to_numpy()
    mh = np.isclose(gg["max"].to_numpy()[ok], sub.bh.to_numpy()[ok], atol=1e-3).mean()
    ml = np.isclose(gg["min"].to_numpy()[ok], sub.bl.to_numpy()[ok], atol=1e-3).mean()
    mo = np.isclose(gg["first"].to_numpy()[ok], sub.bo.to_numpy()[ok], atol=1e-3).mean()
    mc = np.isclose(gg["last"].to_numpy()[ok], sub.bc.to_numpy()[ok], atol=1e-3).mean()
    print(f"  ticks {lab}: match high {mh:.3f} low {ml:.3f} open {mo:.3f} close {mc:.3f}  (n={ok.sum()})")

# ---- 2. timezone sanity on M1: where is the daily spread spike (UTC minute of day)?
for per, a, b in (("summer(EDT) Jul-2019", "2019-07-01", "2019-08-01"), ("winter(EST) Jan-2019", "2019-01-07", "2019-02-01")):
    x = m1[(m1.index >= a) & (m1.index < b)]
    spr = (x.ac - x.bc).groupby(x.index.hour * 60 + x.index.minute).median()
    top = spr.sort_values(ascending=False).head(3)
    print(f"  {per}: widest median-spread UTC minutes {[f'{int(k)//60:02d}:{int(k)%60:02d}' for k in top.index]}"
          f" (17:00 NY = {'21:00' if 'summer' in per else '22:00'} UTC)")

# ---- 3. fill fidelity
P = S.FINALISTS["donch4h_stop"]
orders = S.make_orders(m1, **P).reset_index(drop=True)
t0 = gl.simulate(m1, orders, costs=Costs(commission=0, slip_bps=0, swap_long=0, swap_short=0))
v = gl.cut(t0, "val", track="review", label="lookahead:donch4h_stop:tick-fill-decomposition")
win = v[v.entry_time >= pd.Timestamp("2025-06-01", tz="UTC")]
act = m1.index[np.clip(orders.loc[win.index, "entry_i"].to_numpy(), 0, len(m1) - 1)]
cov = covered_span(pd.DatetimeIndex(act).as_unit("ns").asi8,
                   pd.DatetimeIndex(win.exit_time).as_unit("ns").asi8 + 3600 * 10**9, ts)
win = win[cov]
o = orders.loc[win.index]
tks = tick_simulate(m1, o, (ts, bid, ask))
both = win.join(tks, rsuffix="_tick")
both = both[np.isfinite(both.pnl_tick)]
fi = m1.index.get_indexer(both.entry_time)
xi = m1.index.get_indexer(both.exit_time - pd.Timedelta(minutes=1))
s = both.side.to_numpy()
ent_extra = s * (both.fill.to_numpy() - both.entry.to_numpy())          # >0: ticks fill worse
ext_extra = s * (both.exit.to_numpy() - both.exit_tick.to_numpy())      # >0: ticks exit worse
lvl = o.loc[both.index, "level"].to_numpy()
ah, bl, ao, bo = (m1[k].to_numpy() for k in ("ah", "bl", "ao", "bo"))
beyond_in = np.where(s > 0, ah[fi] - np.maximum(lvl, ao[fi]), np.minimum(lvl, bo[fi]) - bl[fi])
stopx = both.reason.isin(["trail", "stop"]).to_numpy()
beyond_out = np.where(s > 0, both.exit.to_numpy() - bl[xi], ah[xi] - both.exit.to_numpy())
same_fill_min = (both.t_fill.dt.floor("min") == both.entry_time).to_numpy()
same_exit_min = (both.t_exit.dt.floor("min") == (both.exit_time - pd.Timedelta(minutes=1))).to_numpy()
print(f"\n  trades with tick coverage: {len(both)}; same fill minute {same_fill_min.mean():.2f}, "
      f"same exit minute {same_exit_min.mean():.2f}, same exit reason {(both.reason == both.reason_tick).mean():.2f}")
print(f"  entry: tick worse by mean ${ent_extra.mean():.3f} median ${np.median(ent_extra):.3f} max ${ent_extra.max():.3f};"
      f" M1 trigger-bar range beyond level mean ${beyond_in.mean():.3f}"
      f" -> implied entry ffrac {ent_extra.sum() / beyond_in.sum():.3f}")
m = stopx & same_exit_min
print(f"  stop/trail exits (same minute, n={m.sum()}): tick worse by mean ${ext_extra[m].mean():.3f} median "
      f"${np.median(ext_extra[m]):.3f}; bar range beyond stop mean ${beyond_out[m].mean():.3f}"
      f" -> implied exit ffrac {ext_extra[m].sum() / beyond_out[m].sum():.3f}")
risk = (both.entry - both.stop).abs().to_numpy()
slip_budget = both.entry.to_numpy() * 1.5e-4 * 2
print(f"  round trip: tick worse by mean ${(ent_extra + ext_extra).mean():.3f} = {((ent_extra + ext_extra) / risk).mean():.4f} R;"
      f" engine slippage budget mean ${slip_budget.mean():.3f} = {(slip_budget / risk).mean():.4f} R")
print(f"  trades where tick cost > budget: {int(((ent_extra + ext_extra) > slip_budget).sum())}/{len(both)}")
print(f"time {time.time()-T0:.0f}s")
