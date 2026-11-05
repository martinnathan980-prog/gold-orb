"""Descriptive IS-only: does gold LEAD the cheaper markets (EURUSD, USDJPY, DAX)?
Target: forward log return of the target market over k bars after the decision bar close (bp).
Features (last bar): gold return, gold residual vs USD basket, the target's own last return.
Compare effect sizes with the target's round-trip cost (EURUSD 1.3 bp, USDJPY 1.7, DAX 2.3)."""
import warnings

import numpy as np
import pandas as pd

import strategy as S
from common import load_bars
from explore_leadlag import nw_t

warnings.filterwarnings("ignore")
for tf, win, ks in (("5min", 5760, (1, 3, 12)), ("15min", 1920, (1, 4)), ("1h", 1380, (1, 4, 8))):
    cache = {(s, tf): load_bars(s, tf) for s in ["xauusd", "eurusd", "gbpusd", "usdjpy", "deuidxeur"]}
    P = S.xpanel(None, None, tf, S.USD + ["deuidxeur"], cache)
    P = P[P.index < pd.Timestamp("2022-01-01", tz="UTC")]
    beta = S.roll_beta(P.g, P.u, win).shift(1)
    P["res"] = P.g - beta * P.u
    rows = []
    for tgt in ["eurusd", "usdjpy", "deuidxeur"]:
        lp = np.log(cache[(tgt, tf)]["c"]).reindex(P.index)
        for k in ks:
            fut = (lp.shift(-k) - lp) * 1e4
            for x in ["g", "res", tgt]:
                m = P[x].notna() & fut.notna()
                b, t = nw_t(fut[m].to_numpy(), P[x][m].to_numpy(), L=max(10, k))
                xs, fu = P[x][m], fut[m]
                hi, lo = xs > xs.quantile(0.99), xs < xs.quantile(0.01)
                rows.append({"tf": tf, "target": tgt, "k": k, "x": x, "slope": round(b, 4), "t_nw": round(t, 2),
                             "fut|hi": round(fu[hi].mean(), 2), "fut|lo": round(fu[lo].mean(), 2),
                             "hi-lo": round(fu[hi].mean() - fu[lo].mean(), 2)})
    print(pd.DataFrame(rows).to_string(index=False))
