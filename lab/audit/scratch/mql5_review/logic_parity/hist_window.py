"""Build4H history window: how many 4h bars do InpHistoryDays*288 = 51840 M5 bars give, and how
far is the EA's Wilder ATR (seeded at the first bar of that window, partial first bar included)
from the lab's ATR (seeded in 2013)?  Also the minimum the EA accepts (60 + 14 + 2 = 76 bars)."""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, LAB)
import goldlab as gl  # noqa: E402

m1 = gl.load_m1("xauusd", start="2013-01-01", end="2026-12-31")
mid = pd.DataFrame({"h": (m1.bh + m1.ah) / 2, "l": (m1.bl + m1.al) / 2, "c": (m1.bc + m1.ac) / 2})
m5 = mid.resample("5min", label="left", closed="left").agg({"h": "max", "l": "min", "c": "last"}).dropna()
full4 = gl.bars(m1, "4h")
a_full = gl.atr(full4, 14)


def wilder_last(h, l, c, n=14):
    a = np.nan
    for i in range(1, len(h)):
        tr = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        a = tr if i == 1 else a + (tr - a) / n
    return a


rng = np.random.default_rng(0)
dec_idx = rng.choice(np.arange(2000, len(full4) - 1), 400, replace=False)
rows = []
for k in sorted(dec_idx):
    bucket = full4.index[k + 1]                       # decision for the window starting at this bucket
    p = m5.index.searchsorted(bucket) - 1             # last complete M5 bar before the bucket
    for nbars in (51840, 76 * 48):                    # EA default, and ~ the EA minimum (76 4h bars)
        w = m5.iloc[max(0, p - nbars + 2): p + 1]     # (+1 forming bar excluded by the break)
        b4 = w.resample("4h", label="left", closed="left").agg({"h": "max", "l": "min", "c": "last"}).dropna()
        a = wilder_last(b4.h.values, b4.l.values, b4.c.values)
        hi = b4.h.values[-60:].max()
        rows.append((nbars, len(b4), a / a_full.iloc[k] - 1, hi - full4.h.values[k - 59:k + 1].max()))
r = pd.DataFrame(rows, columns=["m5_bars", "n4h", "atr_rel_err", "chan_hi_diff"])
for nb, g in r.groupby("m5_bars"):
    print(f"M5 window {nb:6d}: 4h bars min {g.n4h.min()} median {int(g.n4h.median())} | "
          f"ATR rel. error max {g.atr_rel_err.abs().max():.2e} median {g.atr_rel_err.abs().median():.2e} | "
          f"channel-high diff max {g.chan_hi_diff.abs().max():.2e}")

# --- seeding only (same bar definition as the lab): Wilder ATR restarted at the first 4h bar of
# the window vs the lab's ATR seeded in 2013
print("\nseeding effect only (lab 4h bars, ATR restarted at the window start):")
h, l, c = full4.h.values, full4.l.values, full4.c.values
for n4 in (1167, 81, 76):
    errs = []
    for k in sorted(dec_idx):
        a = wilder_last(h[k - n4 + 1:k + 1], l[k - n4 + 1:k + 1], c[k - n4 + 1:k + 1])
        errs.append(a / a_full.iloc[k] - 1)
    errs = np.abs(errs)
    print(f"  {n4:5d} bars: ATR rel. error max {errs.max():.2e} median {np.median(errs):.2e}")
# --- bar definition: lab mid-high = (max bid-high + max ask-high)/2 vs max of per-bar mids
m4 = mid.resample("4h", label="left", closed="left").agg({"h": "max", "l": "min", "c": "last"}).dropna()
d_h = (full4.h - m4.h.reindex(full4.index))
d_l = (full4.l - m4.l.reindex(full4.index))
print("\n4h high: lab (max bid-high + max ask-high)/2 minus max(M1 mid-high): "
      f"mean {d_h.mean():.3f} p99 {d_h.quantile(.99):.3f} max {d_h.max():.3f}  (always >= 0: {bool((d_h >= -1e-9).all())})")
print("4h low : lab (min bid-low + min ask-low)/2 minus min(M1 mid-low):   "
      f"mean {d_l.mean():.3f} p01 {d_l.quantile(.01):.3f} min {d_l.min():.3f}  (always <= 0: {bool((d_l <= 1e-9).all())})")
