"""Stage 7 - latency profile of candidate A (noise-area, us100): the whole check grid shifted by +2 and +5 minutes
(the +1 minute shift is in stage 4, the +15 / +30 minute shifts are the first_min neighbours of stage 3)."""
from harness import *     # noqa
for sh in (2, 5):
    trial("us100", dict(rule="noise", first_min=600 + sh, last_min=930 + sh), note=f"S7 A checks +{sh}min")
print("trials (lines, distinct):", n_trials())
