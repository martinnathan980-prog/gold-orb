"""Stage 2C - opening-candle momentum with a size filter: trade only when the first 5-minute move is at least the
median absolute 5-minute opening move of the previous 20 sessions (the descriptive study showed that small opening
candles carry no information).  Stop 0.3 ATR, exit 15:55."""
from harness import *     # noqa
for sym in ("us100", "us500"):
    trial(sym, dict(rule="ocm", stop="atr", k=0.3, size_min=1.0), note="S2C ocm5 atr0.3 size>=1.0")
    r2.free()
print("trials (lines, distinct):", n_trials())
