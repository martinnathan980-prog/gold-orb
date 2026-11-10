"""Descriptive 1 (IS only): data coverage at the release times and the modelled FP spread around them."""
import sys

import numpy as np
import pandas as pd

from desc_common import IS_END, MIN, NY, Px, gl, load_is, ny_time, release_times

syms = sys.argv[1:] or ["us500", "us100", "xauusd"]
ev = release_times()
ev = ev[(ev.t >= "2013-01-01") & (ev.t < IS_END)].reset_index(drop=True)
print("events IS:", ev.kind.value_counts().to_dict(), "total", len(ev))
for sym in syms:
    m1 = load_is(sym)
    px = Px(m1)
    mid = (m1.bc.to_numpy() + m1.ac.to_numpy()) / 2
    print(f"\n===== {sym}: {len(m1):,} bars {m1.index[0]} -> {m1.index[-1]}")
    # day-median spread in bp for reference
    for kind in ("fomc", "nfp", "cpi"):
        e = ev[ev.kind == kind]
        t = pd.DatetimeIndex(e.t)
        tn = px._ns(t)
        i = np.searchsorted(px.ns, tn, side="left")
        has_T = (i < len(px.ns)) & (px.ns[np.minimum(i, len(px.ns) - 1)] == tn)
        # bars within [T-30, T) and [T, T+30)
        a = np.searchsorted(px.ns, tn - 30 * MIN)
        b = np.searchsorted(px.ns, tn + 30 * MIN)
        nb_pre, nb_post = i - a, b - i
        x1555 = px.at(ny_time(t, "15:55"), 3)
        miss = t[(nb_pre < 15) | (nb_post < 15)]
        print(f"-- {kind}: n={len(e)} | bar exactly at T: {has_T.sum()} | >=15 bars in the 30 min before: {(nb_pre >= 15).sum()} "
              f"| >=15 bars in the 30 min after: {(nb_post >= 15).sum()} | price at 15:55 NY: {np.isfinite(x1555).sum()}")
        if len(miss):
            print("   thin/missing:", [str(x.tz_convert(NY))[:16] for x in miss])
        # spread profile (bp of price) at minute offsets
        offs = [-30, -10, -5, -2, -1, 0, 1, 2, 3, 4, 5, 10, 15, 30, 60]
        rows = []
        for o in offs:
            s = px.spread_at(t + pd.Timedelta(minutes=o), 0)
            p = px.at(t + pd.Timedelta(minutes=o), 0)
            bp = s / p * 1e4
            rows.append((o, np.isfinite(bp).sum(), np.nanmedian(bp), np.nanpercentile(bp[np.isfinite(bp)], 90) if np.isfinite(bp).any() else np.nan,
                         np.nanmax(bp) if np.isfinite(bp).any() else np.nan))
        print("   spread bp (close of the bar starting at T+o):  o: n / median / p90 / max")
        print("   " + " | ".join(f"{o:+d}: {n} / {md:.2f} / {p9:.2f} / {mx:.2f}" for o, n, md, p9, mx in rows))
        # typical bar range (bp) at offsets, to size the release bar
        rng = []
        for o in (-5, -1, 0, 1, 2, 5, 15):
            tt = px._ns(t + pd.Timedelta(minutes=o))
            k = np.searchsorted(px.ns, tt, side="left")
            ok = (k < len(px.ns)) & (px.ns[np.minimum(k, len(px.ns) - 1)] == tt)
            kk = k[ok]
            r = (px.mh[kk] - px.ml[kk]) / px.mo[kk] * 1e4
            rng.append((o, np.median(r) if len(r) else np.nan))
        print("   median M1 bar range bp: " + " | ".join(f"{o:+d}: {v:.1f}" for o, v in rng))
