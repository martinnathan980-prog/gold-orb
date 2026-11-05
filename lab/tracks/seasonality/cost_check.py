"""IS cost decomposition for already-logged configs (no new trials): gross mid move vs net, in bp."""
import numpy as np, pandas as pd
from trials import m1_is, strategy, gl
from goldlab.sim import simulate
m1 = m1_is()
mid_o = ((m1.bo + m1.ao) / 2).to_numpy()
idx_ns = m1.index.values
CF = {"T01 FRI_PM mkt": dict(entry_time="13:30", exit_time="16:45", exit_days=0, stop_atr=3.0),
      "T03 FRI_PM lim": dict(entry_time="13:30", exit_time="16:45", exit_days=0, stop_atr=3.0, entry="limit", limit_off=0.0, limit_min=60),
      "T02 WKND mkt": dict(entry_time="13:30", exit_time="22:00", exit_days=2, stop_atr=3.0),
      "T04 WKND lim": dict(entry_time="13:30", exit_time="22:00", exit_days=2, stop_atr=3.0, entry="limit", limit_off=0.0, limit_min=60)}
for nm, p in CF.items():
    o = strategy.make_orders(m1, **p)
    t = gl.cut(simulate(m1, o), "is")
    ie = np.searchsorted(idx_ns, t.entry_time.values); ix = np.searchsorted(idx_ns, (t.exit_time).values)
    ix = np.minimum(ix, len(m1) - 1)
    # mid at entry bar open and at exit bar open (time exits) ; for stops use exit price as is
    gross_mid = np.where(t.reason == "time", np.log(mid_o[ix] / mid_o[ie]), np.nan) * 1e4
    net = t.pnl / t.entry * 1e4
    gross_px = t.side * (t.exit - t.entry) / t.entry * 1e4
    print(f"{nm:16s} n={len(t)} | mean net {net.mean():+.2f} bp | gross fill-to-fill {gross_px.mean():+.2f} bp | "
          f"mid-to-mid (time exits) {np.nanmean(gross_mid):+.2f} bp | swap {(t.swap / t.entry * 1e4).mean():.2f} bp | "
          f"comm {(t.commission / t.entry * 1e4).mean():.2f} bp | net sd {net.std():.1f} bp | pf_ret {(net[net>0].sum()/-net[net<0].sum()):.3f}")
