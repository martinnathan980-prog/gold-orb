"""Stage 1 -- screen of canonical, untuned rules (declared before running; 12 configurations).

ORB family (stop at the opposite side of the range, no target, no trailing, both sides):
  O1 round-1 rule under real costs: range 09:00-10:00 Berlin (= 08-09 London), entries until 17:00, exit 21:00
  O2 same, exit at the cash close 17:30
  O3 / O4 range 09:00-09:30 / 09:00-09:15, exit 17:30
  O5 pre-market range 08:00-09:00, breakout after the cash open, exit 17:30
  O6 / O7 US cash open: range 09:30-10:00 New York, exit 21:45 Berlin / 17:30 Berlin
Momentum family (anchor = previous cash close 17:30, 20-day scale, continuation, stop 0.5 x scale):
  M1 decision 16:00, |z| >= 1.5, exit 17:30         (market intraday momentum into the close)
  M2 decision 12:00, |z| >= 1.5, exit 17:30         (morning trend continued into the afternoon)
  M3 first 30-min mark 09:30..16:30 with |z| >= 1.5 (noise-band style breakout), exit 17:30
  M4 decision 09:05, |z| >= 1.0, exit 17:30         (overnight gap continued after the cash open)
  M5 decision 17:00, every day, stop 0.25 x scale   (last half-hour momentum, Gao et al.)
"""
from research import trial, n_trials

GRID = tuple(f"{h:02d}:{m:02d}" for h in range(9, 17) for m in (0, 30) if (h, m) >= (9, 30))
CONFIGS = [
    ("S1_O1_orb0900_60_x2100", {"family": "orb", "rs": "09:00", "re": "10:00", "entry_end": "17:00", "exit": "21:00"}),
    ("S1_O2_orb0900_60_x1730", {"family": "orb", "rs": "09:00", "re": "10:00", "entry_end": "17:00", "exit": "17:30"}),
    ("S1_O3_orb0900_30_x1730", {"family": "orb", "rs": "09:00", "re": "09:30", "entry_end": "17:00", "exit": "17:30"}),
    ("S1_O4_orb0900_15_x1730", {"family": "orb", "rs": "09:00", "re": "09:15", "entry_end": "17:00", "exit": "17:30"}),
    ("S1_O5_orb0800_60_x1730", {"family": "orb", "rs": "08:00", "re": "09:00", "entry_end": "17:00", "exit": "17:30"}),
    ("S1_O6_orbUS_30_x2145", {"family": "orb", "rs": "09:30@NY", "re": "10:00@NY", "entry_end": "21:00", "exit": "21:45"}),
    ("S1_O7_orbUS_30_x1730", {"family": "orb", "rs": "09:30@NY", "re": "10:00@NY", "entry_end": "17:15", "exit": "17:30"}),
    ("S1_M1_mom1600_k1.5", {"family": "mom", "times": ("16:00",), "k": 1.5, "stop_k": 0.5, "exit": "17:30"}),
    ("S1_M2_mom1200_k1.5", {"family": "mom", "times": ("12:00",), "k": 1.5, "stop_k": 0.5, "exit": "17:30"}),
    ("S1_M3_momgrid_k1.5", {"family": "mom", "times": GRID, "k": 1.5, "stop_k": 0.5, "exit": "17:30"}),
    ("S1_M4_gap0905_k1.0", {"family": "mom", "times": ("09:05",), "k": 1.0, "stop_k": 0.5, "exit": "17:30"}),
    ("S1_M5_last30_all", {"family": "mom", "times": ("17:00",), "k": 0.0, "stop_k": 0.25, "exit": "17:30"}),
]

if __name__ == "__main__":
    for tag, p in CONFIGS:
        r = trial(p, tag)
        print("      by year R:", r["ev"]["is"].get("by_year_R"))
    print("trials so far:", n_trials())
