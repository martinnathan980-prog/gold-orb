"""Stage 3 -- declared before running (after stage 2 and the null tests).

3A  late momentum: where does the decision-time plateau start?  (15:30 was poor, 16:00-17:00 good)
    T 15:45, T 16:15;  anchor 17:25 / 17:35 (is the 'previous cash close' definition a knife edge?)
3B  morning momentum (grid 09:30,10:00,10:30; k 1.5; stop 0.5): is the morning part an edge of its own?
    exit 16:00 (before the late sleeve enters)
"""
from research import trial, n_trials
from stage2 import M1, B0, v

B3 = v(B0, times=("09:30", "10:00", "10:30"))
CONFIGS = [
    ("S3_A18_T1545", v(M1, times=("15:45",))), ("S3_A19_T1615", v(M1, times=("16:15",))),
    ("S3_A20_anchor1725", v(M1, anchor="17:25")), ("S3_A21_anchor1735", v(M1, anchor="17:35")),
    ("S3_B09_grid_exit1600", v(B3, exit="16:00")),
]

if __name__ == "__main__":
    for tag, p in CONFIGS:
        r = trial(p, tag)
        print("      by year R:", r["ev"]["is"].get("by_year_R"))
    print("trials so far:", n_trials())
