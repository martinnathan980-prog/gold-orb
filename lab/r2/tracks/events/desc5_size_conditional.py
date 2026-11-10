"""Descriptive 5 (IS only): does the continuation after a release depend on the SIZE of the first move?
r0 = P(T+5m) / P(last before T); size = |r0| / (mean |M1 return| over T-4h..T-5m)  (causal unit).
Split at the in-sample median of `size` within each kind (exploration only - a live rule would need
a fixed threshold).  Also: first move measured against the pre-release 30-minute range (bracket logic)."""
import numpy as np
import pandas as pd

from desc_common import RES, tstat

ncell = 0
for sym in ("us500", "us100", "xauusd"):
    tab = pd.read_csv(f"{RES}/evtab_{sym}.csv")
    print(f"\n===== {sym}")
    for g in ("fomc", "nfp", "cpi", "all"):
        e = (tab if g == "all" else tab[tab.kind == g]).copy()
        r0 = np.log(e.p_p5 / e.p_m1) * 1e4
        size = r0.abs() / e.vol_m1_bp
        med = size.groupby(e.kind).transform("median")
        sg = np.sign(r0)
        outside = (e.p_p5 > e.pre30_hi) | (e.p_p5 < e.pre30_lo)
        for lab, sel in (("big move  ", size > med), ("small move", size <= med), ("outside pre-30m range at T+5", outside)):
            cells = []
            for hn, hc in (("T+60", "p_p60"), ("15:55", "p_1555"), ("next 15:55", "p_next1555")):
                r1 = (sg * np.log(e[hc] / e.p_p5) * 1e4)[sel & (sg != 0)]
                ncell += 1
                cells.append(f"{hn}: {r1.mean():+6.2f} (t {tstat(r1):+5.2f}, n {r1.notna().sum()})")
            print(f"  {g:5s} {lab:30s} " + " | ".join(cells))
print("cells:", ncell)
