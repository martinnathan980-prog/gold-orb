"""Stage 4 - execution-latency robustness of the two candidates on us100: everything one minute late.
   A: checks at HH:01 / HH:31 instead of HH:00 / HH:30 (first_min 601, last 931)
   B: same 09:30-09:35 candle, market entry at 09:36 instead of 09:35."""
from harness import *     # noqa
m1 = r2.load("us100", end="2022-01-01")
o0 = S.make_orders(m1, rule="ocm", stop="atr", k=0.3, size_min=1.0)
print("sanity: base OCM orders unchanged by the new optional parameter:", len(o0), int(o0.entry_i.sum()))
trial("us100", dict(rule="noise", first_min=601, last_min=931), note="S4 A checks +1min")
trial("us100", dict(rule="ocm", stop="atr", k=0.3, size_min=1.0, delay=1), note="S4 B entry +1min")
print("trials (lines, distinct):", n_trials())
