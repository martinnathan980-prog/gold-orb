"""Engine check: M1-bar simulation vs tick-by-tick simulation on random market orders.
Uses Nov-Dec 2025 ticks (engine validation only, no strategy is evaluated)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np, pandas as pd, numba as nb
import goldlab as gl
from goldlab.sim import Costs

RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "download")

@nb.njit
def tick_run(ts, bid, ask, t_in, side, sd, td, t_out):
    n = len(t_in); res = np.zeros((n, 3))
    for k in range(n):
        i = np.searchsorted(ts, t_in[k])
        if i >= len(ts): res[k, 2] = -1; continue
        s = side[k]
        fp = ask[i] if s > 0 else bid[i]
        st = fp - s * sd[k]; tg = fp + s * td[k]
        j = i; out = -1.0; why = 2
        while j < len(ts):
            if ts[j] >= t_out[k]:
                out = bid[j] if s > 0 else ask[j]; why = 2; break
            if s > 0:
                if bid[j] <= st: out = bid[j]; why = 0; break
                if bid[j] >= tg: out = tg; why = 1; break
            else:
                if ask[j] >= st: out = ask[j]; why = 0; break
                if ask[j] <= tg: out = tg; why = 1; break
            j += 1
        res[k, 0] = s * (out - fp); res[k, 1] = why
    return res

frames = []
for m in ("11", "12"):
    t = pd.read_csv(os.path.join(RAW, f"xauusd-tick-2025-{m}-01-2025-{m}-28.csv.gz"))
    frames.append(t)
tk = pd.concat(frames)
ts = tk.timestamp.to_numpy(np.int64) * 1_000_000  # ns
m1 = gl.load_m1("xauusd", "2025-11-01", "2025-12-29")
rng = np.random.default_rng(1)
starts = m1.index[(m1.index < pd.Timestamp("2025-12-27", tz="UTC"))]
starts = starts[(starts.day <= 27)]
pick = np.sort(rng.choice(len(starts), 800, replace=False))
T = starts[pick]
side = rng.choice([-1, 1], len(T))
for dist in (3.0, 8.0, 20.0):
    o = pd.DataFrame({"entry_i": gl.entry_index(m1, T), "side": side, "stop_dist": dist, "target_dist": dist,
                      "exit_i": gl.entry_index(m1, T + pd.Timedelta(hours=6))})
    sim = gl.simulate(m1, o, costs=Costs(commission=0, slip_bps=0, swap_long=0, swap_short=0), no_overlap=False)
    t_out = m1.index[np.minimum(o.exit_i.values, len(m1) - 1)].as_unit("ns").asi8
    r = tick_run(ts, tk.bidPrice.to_numpy(), tk.askPrice.to_numpy(), T.as_unit("ns").asi8, side,
                 np.full(len(T), dist), np.full(len(T), dist), t_out)
    keep = (r[:, 2] == 0)
    tick = pd.DataFrame({"pnl": r[:, 0], "why": r[:, 1]}, index=o.index)[keep]
    j = sim.join(tick, how="inner", rsuffix="_tick")
    why_m1 = j.reason.map({"stop": 0, "target": 1, "time": 2, "gap": 0})
    agree = (why_m1 == j.why).mean()
    print(f"dist ${dist:>4}: n={len(j)} outcome agreement {agree*100:.1f}% | mean pnl M1 {j.pnl.mean():+.3f} "
          f"vs tick {j.pnl_tick.mean():+.3f} (M1 - tick = {j.pnl.mean()-j.pnl_tick.mean():+.3f}/trade)")
    dis = j[why_m1 != j.why]
    print("   disagreements M1->tick:", pd.crosstab(dis.reason, dis.why.map({0:'stop',1:'target',2:'time'})).to_dict())

# per-trade diagnostics for the last distance
d = (j.pnl - j.pnl_tick)
print("per-trade M1-tick diff: median %+.3f | p5 %+.3f | p95 %+.3f | n |diff|>5$: %d" % (d.median(), d.quantile(.05), d.quantile(.95), (d.abs()>5).sum()))
big = j[d.abs() > 5].head(5)
print(big[["side","entry_time","entry","exit","reason","pnl","pnl_tick","why"]])
spr = tk.askPrice - tk.bidPrice
print("tick spread quantiles:", spr.quantile([.5,.99,.999,.9999]).round(2).to_dict(), "max", round(spr.max(),2))

# exclude trades whose 6h window touches a hole in the tick files (they stop on the 28th of each month)
gap = ((j.entry_time >= pd.Timestamp("2025-11-27 15:00", tz="UTC")) & (j.entry_time < pd.Timestamp("2025-12-01", tz="UTC"))) | \
      (j.entry_time >= pd.Timestamp("2025-12-26 12:00", tz="UTC"))
jj = j[~gap]; dd = jj.pnl - jj.pnl_tick
print(f"clean sample n={len(jj)}: mean M1-tick {dd.mean():+.3f} $/trade (median {dd.median():+.3f}); "
      f"M1 optimistic on {(dd>0.05).mean()*100:.1f}% of trades, pessimistic on {(dd<-0.05).mean()*100:.1f}%")
print("  on stop exits only: mean diff %+.3f $" % dd[jj.reason=="stop"].mean())
