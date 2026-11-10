"""Stage 2 -- declared before running, after reading stage 1 (25 configurations).

Stage 1 reading: opening-range breakouts are weak (net PF 0.94-1.08, t <= 1.3, long side only); the
momentum family anchored on the previous cash close works: M1 (16:00, |z|>=1.5) PF 1.67 t 3.5, M3 (first
30-min mark 09:30-16:30) PF 1.42 t 3.3, M4 (gap 09:05, |z|>=1) PF 1.37 t 2.7.  The M3 break-down shows two
components: entries at 09:30-10:30 (gap days) and the late-day continuation; entries 11:00-16:30 add nothing.

2A  late momentum: one change at a time around M1 = (T 16:00, k 1.5, stop 0.5, exit 17:30, lb 20)
    k 1.0 / 1.25 / 1.75 / 2.0;  T 15:30 / 16:30 / 17:00;  stop 0.25 / 0.35 / 0.75 / 1.0;
    exit 17:25 / 17:35;  lb 10 / 40;  late grids (16:00,16:30,17:00) and (15:00..17:00 every 30 min)
2B  morning (gap) momentum: T 09:30 k 1.5 stop 0.5 exit 17:30 as base;
    T 09:05;  grid (09:30,10:00,10:30);  stop 1.0 / 0.25;  k 2.0;  exit 21:45 / 16:00
"""
from research import trial, n_trials

M1 = {"family": "mom", "times": ("16:00",), "k": 1.5, "stop_k": 0.5, "exit": "17:30"}
B0 = {"family": "mom", "times": ("09:30",), "k": 1.5, "stop_k": 0.5, "exit": "17:30"}


def v(base, **kw):
    p = dict(base)
    p.update(kw)
    return p


CONFIGS = [
    ("S2_A01_k1.0", v(M1, k=1.0)), ("S2_A02_k1.25", v(M1, k=1.25)), ("S2_A03_k1.75", v(M1, k=1.75)), ("S2_A04_k2.0", v(M1, k=2.0)),
    ("S2_A05_T1530", v(M1, times=("15:30",))), ("S2_A06_T1630", v(M1, times=("16:30",))), ("S2_A07_T1700", v(M1, times=("17:00",))),
    ("S2_A08_stop0.25", v(M1, stop_k=0.25)), ("S2_A09_stop0.35", v(M1, stop_k=0.35)), ("S2_A10_stop0.75", v(M1, stop_k=0.75)),
    ("S2_A11_stop1.0", v(M1, stop_k=1.0)),
    ("S2_A12_exit1725", v(M1, exit="17:25")), ("S2_A13_exit1735", v(M1, exit="17:35")),
    ("S2_A14_lb10", v(M1, lb=10)), ("S2_A15_lb40", v(M1, lb=40)),
    ("S2_A16_grid1600-1700", v(M1, times=("16:00", "16:30", "17:00"))),
    ("S2_A17_grid1500-1700", v(M1, times=("15:00", "15:30", "16:00", "16:30", "17:00"))),
    ("S2_B01_T0930_k1.5", B0), ("S2_B02_T0905_k1.5", v(B0, times=("09:05",))),
    ("S2_B03_grid0930-1030", v(B0, times=("09:30", "10:00", "10:30"))),
    ("S2_B04_T0930_stop1.0", v(B0, stop_k=1.0)), ("S2_B05_T0930_stop0.25", v(B0, stop_k=0.25)),
    ("S2_B06_T0930_k2.0", v(B0, k=2.0)),
    ("S2_B07_T0930_exit2145", v(B0, exit="21:45")), ("S2_B08_T0930_exit1600", v(B0, exit="16:00")),
]

if __name__ == "__main__":
    for tag, p in CONFIGS:
        r = trial(p, tag)
        print("      by year R:", r["ev"]["is"].get("by_year_R"))
    print("trials so far:", n_trials())
