"""Stage 2A - opening-candle momentum: the candle stop is hit 76% of the time; how wide must the stop be?
ATR-multiple stops (daily ATR14), same exit (15:55).  us100 and us500 (us30 has no gross edge to protect)."""
from harness import *     # noqa
for sym in ("us100", "us500"):
    for k in (0.15, 0.3, 0.6):
        trial(sym, dict(rule="ocm", stop="atr", k=k), note=f"S2A ocm5 atr-stop k={k}")
    r2.free()
print("trials (lines, distinct):", n_trials())
