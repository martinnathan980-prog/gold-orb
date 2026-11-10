"""EDA 1 (in-sample only, cost-free descriptive statistics; no strategy P&L): what happens after a large
bar?  For tf in (15, 60, 240) minutes: bars whose body |close-open| >= k x ATR14 (ATR of the previous bar);
mean forward mid return (signed by the bar's direction, in bp) over the next 1, 2, 4, 8 bars; t-stat;
split by direction and by half of the sample."""
import json, os, sys
import numpy as np, pandas as pd
from research import RES, r2, S

out = {}
for sym in ("xauusd", "xagusd"):
    m1 = r2.load(sym, end="2022-01-01")
    c = S.context(m1)
    out[sym] = {}
    for tf in (15, 60, 240):
        b = S.bars(c, tf)
        a = S.atr(b, 14)
        ap = np.r_[np.nan, a[:-1]]
        body = b["c"] - b["o"]
        z = body / ap
        cl = b["c"]
        nb = len(cl)
        # entry reference = mid OPEN of the first M1 bar after the bar (what a market order would see)
        en = b["en"]
        mo = (c["bo"] + c["ao"]) / 2
        ok_next = en < c["N"]
        ref = np.where(ok_next, mo[np.clip(en, 0, c["N"] - 1)], np.nan)
        gapmin = np.where(ok_next, c["t"][np.clip(en, 0, c["N"] - 1)] - b["t_close"], 1e9)
        yr = (b["t_start"].astype("datetime64[m]").astype("datetime64[Y]").astype(int) + 1970)
        rows = []
        for k in (1.5, 2.0, 2.5, 3.0):
            for H in (1, 2, 4, 8):
                fwd_c = np.r_[cl[H:], np.full(H, np.nan)]
                fr = (fwd_c - ref) / ref * 1e4
                sel = (np.abs(z) >= k) & np.isfinite(fr) & (gapmin <= 10)
                s = np.sign(z)
                x = (fr * s)[sel]
                if len(x) < 30:
                    continue
                up = (fr * s)[sel & (s > 0)]
                dn = (fr * s)[sel & (s < 0)]
                h1 = (fr * s)[sel & (yr <= 2017)]
                h2 = (fr * s)[sel & (yr >= 2018)]
                t = lambda v: round(float(v.mean() / (v.std(ddof=1) / np.sqrt(len(v)))), 2) if len(v) > 2 else None
                rows.append({"k": k, "H": H, "n": int(len(x)), "mean_bp": round(float(x.mean()), 2), "t": t(x),
                             "up_n": int(len(up)), "up_bp": round(float(up.mean()), 2), "dn_bp": round(float(dn.mean()), 2),
                             "h1_bp": round(float(h1.mean()), 2), "h2_bp": round(float(h2.mean()), 2),
                             "median_bp": round(float(np.median(x)), 2)})
        out[sym][str(tf)] = rows
        print(sym, tf, "bars", nb, "ATR median bp", round(float(np.nanmedian(a / cl) * 1e4), 1))
        print(pd.DataFrame(rows).to_string(index=False))
    r2.free(); S._CTX.clear()
json.dump(out, open(os.path.join(RES, "eda1_large_bar_followthrough.json"), "w"), indent=1)
