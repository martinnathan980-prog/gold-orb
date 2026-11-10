"""Stage 2B - full IS evaluation (cost stress x1.5, gross, every-signal) of the two leads from stages 1-2A:
noise-area canonical (paper parameters) and opening-candle momentum with a 0.3 ATR stop."""
from harness import *     # noqa
for sym in ("us100", "us500"):
    ev = trial(sym, dict(rule="noise"), full=True, note="S2B noise canonical FULL")
    print("   criteria:", r2.is_criteria(ev))
    ev = trial(sym, dict(rule="ocm", stop="atr", k=0.3), full=True, note="S2B ocm5 atr0.3 FULL")
    print("   criteria:", r2.is_criteria(ev))
    r2.free()
print("trials (lines, distinct):", n_trials())
