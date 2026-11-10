"""Descriptive 3 (IS only): drift windows and reaction-continuation cells around FOMC / NFP / CPI.
Mid prices, log returns in bp.  Cells are counted (multiple-testing tally)."""
import sys

import numpy as np
import pandas as pd

from desc_common import RES, line, tstat

syms = sys.argv[1:] or ["us500", "us100", "xauusd"]
groups = ["fomc", "nfp", "cpi", "all"]
ncell = 0
big = []


def lr(a, b):
    return np.log(b / a) * 1e4


for sym in syms:
    tab = pd.read_csv(f"{RES}/evtab_{sym}.csv")
    print(f"\n================ {sym} ================")
    for g in groups:
        e = tab if g == "all" else tab[tab.kind == g]
        y = e.year.values
        print(f"--- {sym} / {g}  (n events {len(e)})")
        print(" unconditional drift windows (long side, bp)")
        U = [("pre: T-24h -> T-5m", lr(e.p_m1440, e.p_m5)),
             ("pre: prev 15:55 -> T-5m", lr(e.p_prev1555, e.p_m5)),
             ("pre: T-4h -> T-5m", lr(e.p_m240, e.p_m5)),
             ("reaction: T-1m(last) -> T+5m", lr(e.p_m1, e.p_p5)),
             ("post: T+5m -> 15:55", lr(e.p_p5, e.p_1555)),
             ("T-5m -> 15:55", lr(e.p_m5, e.p_1555)),
             ("day: prev 15:55 -> 15:55", lr(e.p_prev1555, e.p_1555)),
             ("next day: 15:55 -> next 15:55", lr(e.p_1555, e.p_next1555))]
        for lab, r in U:
            ncell += 1
            s = line(lab, r, y)
            print("  ", s)
            tt = tstat(r)
            if np.isfinite(tt) and abs(tt) >= 2.5:
                big.append((sym, g, lab, round(float(np.nanmean(r)), 2), round(tt, 2)))
        print(" continuation: sign(P(T+k) - P(last before T)) x return from T+k to horizon (bp)")
        hz = [("T+30", "p_p30", 30), ("T+60", "p_p60", 60), ("T+120", "p_p120", 120), ("15:55", "p_1555", 999), ("next 15:55", "p_next1555", 9999)]
        for k in (1, 2, 5, 15, 30):
            pk = e[f"p_p{k}"]
            r0 = lr(e.p_m1, pk)
            sg = np.sign(r0)
            cells = []
            for hn, hc, hm in hz:
                if hm <= k:
                    continue
                r1 = sg * lr(pk, e[hc])
                r1 = r1.where(sg != 0)
                ncell += 1
                tt = tstat(r1)
                cells.append(f"{hn}: {np.nanmean(r1):+6.2f} (t {tt:+5.2f}, n {int(np.isfinite(r1).sum())})")
                if np.isfinite(tt) and abs(tt) >= 2.5:
                    big.append((sym, g, f"cont k={k} -> {hn}", round(float(np.nanmean(r1)), 2), round(tt, 2)))
            print(f"   k={k:2d}m  mean|r0|={np.nanmean(np.abs(r0)):5.1f}bp | " + " | ".join(cells))
print(f"\ncells examined: {ncell}; expected |t|>=2.5 by chance (two-sided, independent): {ncell * 0.0124:.1f}")
print("cells with |t| >= 2.5:")
for b in big:
    print("  ", b)
