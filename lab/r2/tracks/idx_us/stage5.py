"""Stage 5 - latency-robust form of the opening-candle rule.  Stage 4 + diag3/diag6 showed that the n=5 version
earns ~1.8 bp (us100) in the single minute 09:35-09:36 (the instant the first 5-minute bar closes: a crowded
second), and that entering one minute late cuts PF from 1.31 to 1.17.  For candles of 1-4 minutes there is NO such
first-minute burst (the minute after the signal is flat to slightly negative), so a shorter candle enters BEFORE the
5-minute crowd and does not depend on being first in the queue.  Declared before running: n=3 (centre of the 1-5
range) and n=2, same stop (0.3 ATR), same size filter (>= 1.0 x median of 20 sessions), exit 15:55, on the three
indices."""
from harness import *     # noqa
for sym in ("us100", "us500", "us30"):
    for n in (3, 2):
        trial(sym, dict(rule="ocm", n=n, stop="atr", k=0.3, size_min=1.0), note=f"S5 ocm n={n} atr0.3 size1.0")
    r2.free()
print("trials (lines, distinct):", n_trials())
