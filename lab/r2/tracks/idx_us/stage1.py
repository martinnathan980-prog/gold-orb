"""Stage 1 - screen: one canonical configuration per documented idea, same settings on the three indices."""
from harness import *     # noqa
for sym in ("us100", "us500", "us30"):
    trial(sym, dict(rule="ocm"), note="S1 ocm5 candle-stop")
    trial(sym, dict(rule="orb"), note="S1 orb15 range-stop")
    trial(sym, dict(rule="noise"), note="S1 noise-area 30min")
    if sym == "us100":
        trial(sym, dict(rule="last"), note="S1 last30 rod")
    r2.free()
print("trials (lines, distinct):", n_trials())
