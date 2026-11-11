"""Build the research tables (in-sample only): touches + context for the real levels and 10 placebo level sets,
and the net R (engine, FP costs, every touch) of concrete follow / fade trades."""
import os, sys, time
sys.path.insert(0, "/home/user/gold-orb/lab")
import numpy as np, pandas as pd
from goldlab import r2
from goldlab.sim import simulate
from pivbb.tracks.policy import strategy as S

OUT = "/home/user/gold-orb/lab/results/pivbb/policy"
TRADES = {"T1": dict(stop=0.25, target=0.25, hold=None), "T2": dict(stop=0.25, target=0.50, hold=None),
          "T3": dict(stop=0.25, target=None, hold=120), "T4": dict(stop=0.25, target=None, hold=None)}

if __name__ == "__main__":
    m1 = r2.load("xauusd", end="2022-01-01")
    print("IS frame", m1.index[0], m1.index[-1], len(m1), flush=True)
    c = r2.costs("xauusd")
    ctx = S.Ctx(m1)
    parts = []
    for seed in [None] + list(range(10)):
        t0 = time.time()
        ev = S.events(ctx, seed)
        ok = S.tradable(ev)
        for name, tr in TRADES.items():
            for arm, sg in (("follow", 1), ("fade", -1)):
                o = S.trade_orders(ev, sg * ev.s.to_numpy().astype(np.int64), **tr)
                t = simulate(m1, o[ok], sym="xauusd", costs=c, no_overlap=False)
                col = np.full(len(ev), np.nan)
                col[t.index.to_numpy()] = t.R.to_numpy()
                ev[f"R_{arm}_{name}"] = col
        ev["seed"] = -1 if seed is None else seed
        parts.append(ev)
        print("seed", seed, len(ev), "touches", round(time.time() - t0, 1), "s", flush=True)
    ev = pd.concat(parts, ignore_index=True)
    ev.to_parquet(os.path.join(OUT, "events_policy_is.parquet"))
    print("saved", ev.shape)
