"""Sanity checks of the simulator: random trades must lose roughly the costs, no free money."""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np, pandas as pd
import goldlab as gl

m1 = gl.load_m1("xauusd")
h1 = gl.bars(m1, "1h")
a = gl.atr(h1, 14)
rng = np.random.default_rng(0)
for label, sides in (("random both", None), ("random long", 1), ("random short", -1)):
    pick = np.sort(rng.choice(np.arange(50, len(h1) - 30), 6000, replace=False))
    b = h1.iloc[pick]
    ei = gl.entry_index(m1, b.t_close)
    sd = rng.choice([-1, 1], len(b)) if sides is None else np.full(len(b), sides)
    o = pd.DataFrame({"entry_i": ei, "side": sd, "stop_dist": a.iloc[pick].values,
                      "target_dist": a.iloc[pick].values,
                      "exit_i": gl.entry_index(m1, b.t_close + pd.Timedelta(hours=24))})
    t0 = time.time()
    t = gl.simulate(m1, o)
    dt = time.time() - t0
    r = gl.report(gl.cut(t, "is"))
    print(f"{label:13s} n={r['n']} win={r['win_rate']} expR={r['expectancy_R']} pf={r['pf']} "
          f"longR={r['long_R']} shortR={r['short_R']} skip={t.attrs['skipped']} ({dt:.2f}s)")
    cost = (t.commission + t.swap).mean()
    spread_cost = ((m1.ac - m1.bc).iloc[t.index.size and gl.entry_index(m1, t.entry_time)]).mean()
    print(f"   mean commission+swap/trade ${cost:.3f}, mean entry spread ${spread_cost:.3f}, mean risk ${t.risk.mean():.2f}")
# buy & hold reference in IS
p0, p1 = m1.loc[:"2021-12-31"].bc.iloc[[0, -1]]
print(f"gold IS buy&hold: {p0:.1f} -> {p1:.1f}  ({(p1/p0-1)*100:.1f}%)")
