"""Stage 4 -- 'close-run' family, declared before running (7 configurations).

Descriptive finding (IS, minute level): the trend-signed return (sign of the move since the previous cash
close) is concentrated in the last 15 minutes before the Xetra close: 17:15->17:30 about +2.4 bp on ALL
days (9/9 years positive for the last 5 minutes), +2.8 bp when 0.5<=|z|<1.5, +5-6 bp when |z|>=1.5,
followed by a partial reversal after 17:30.  Stage 1's M5 (17:00, every day, stop 0.25) lost this to
stop-outs before the run.  Question: is a short hold 17:15/17:20/17:25 -> 17:30 tradable after costs?
    T 17:15 / 17:20, k 0 / 0.5 / 1.0, stop 0.25 x scale, exit 17:30;  plus T 17:25, k 0.5.
"""
from research import trial, n_trials

C0 = {"family": "mom", "times": ("17:15",), "k": 0.5, "stop_k": 0.25, "exit": "17:30"}


def v(base, **kw):
    p = dict(base)
    p.update(kw)
    return p


CONFIGS = [
    ("S4_C1_T1715_k0", v(C0, k=0.0)), ("S4_C2_T1715_k0.5", C0), ("S4_C3_T1715_k1.0", v(C0, k=1.0)),
    ("S4_C4_T1720_k0", v(C0, times=("17:20",), k=0.0)), ("S4_C5_T1720_k0.5", v(C0, times=("17:20",))),
    ("S4_C6_T1720_k1.0", v(C0, times=("17:20",), k=1.0)),
    ("S4_C7_T1725_k0.5", v(C0, times=("17:25",))),
]

if __name__ == "__main__":
    for tag, p in CONFIGS:
        r = trial(p, tag)
        print("      by year R:", r["ev"]["is"].get("by_year_R"))
    print("trials so far:", n_trials())
