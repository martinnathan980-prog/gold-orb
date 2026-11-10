"""Stage 5 -- neighbours of the close-run candidate C7 = (T 17:25, k 0.5, stop 0.25, exit 17:30, lb 20,
anchor 17:30), declared before running (15 configurations, one parameter changed at a time).

    T 17:23 / 17:27 (the 5-minute grid neighbour 17:20 is stage 4's C5);  k 0 / 0.25 / 0.75 / 1.0;
    stop 0.15 / 0.35;  exit 17:29 / 17:31 (one-minute timing sensitivity) / 17:35;  lb 10 / 40;
    anchor 17:25 / 17:35.
"""
from research import trial, n_trials

C7 = {"family": "mom", "times": ("17:25",), "k": 0.5, "stop_k": 0.25, "exit": "17:30"}


def v(base, **kw):
    p = dict(base)
    p.update(kw)
    return p


CONFIGS = [
    ("S5_N01_T1723", v(C7, times=("17:23",))), ("S5_N02_T1727", v(C7, times=("17:27",))),
    ("S5_N03_k0.25", v(C7, k=0.25)), ("S5_N04_k0.75", v(C7, k=0.75)), ("S5_N05_k0", v(C7, k=0.0)), ("S5_N06_k1.0", v(C7, k=1.0)),
    ("S5_N07_stop0.15", v(C7, stop_k=0.15)), ("S5_N08_stop0.35", v(C7, stop_k=0.35)),
    ("S5_N09_exit1729", v(C7, exit="17:29")), ("S5_N10_exit1731", v(C7, exit="17:31")), ("S5_N11_exit1735", v(C7, exit="17:35")),
    ("S5_N12_lb10", v(C7, lb=10)), ("S5_N13_lb40", v(C7, lb=40)),
    ("S5_N14_anchor1725", v(C7, anchor="17:25")), ("S5_N15_anchor1735", v(C7, anchor="17:35")),
]

if __name__ == "__main__":
    for tag, p in CONFIGS:
        r = trial(p, tag)
        print("      by year R:", r["ev"]["is"].get("by_year_R"))
    print("trials so far:", n_trials())
