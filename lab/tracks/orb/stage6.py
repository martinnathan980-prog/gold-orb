"""Stage 6 diagnostic (declared after stage 5, BEFORE any VAL access): path dependence of the hold
length.  Same F3 signal, but every session's breakout is traded (positions may overlap), for hold
1, 2, 3 days.  If the ensemble PF is flat across holds, the 2-day no-overlap PF is one lucky draw."""
from research import run, n_trials
from stage2 import BASE, ASIA

F3 = {**ASIA, "hold_days": 2, "buf_frac": 0.1}
D = {
    "D1_F3_overlap_hold1": {**F3, "hold_days": 1},
    "D2_F3_overlap_hold2": {**F3, "hold_days": 2},
    "D3_F3_overlap_hold3": {**F3, "hold_days": 3},
}
if __name__ == "__main__":
    for k, v in D.items():
        run(k, {**BASE, **v}, stage="6-diag-overlap", no_overlap=False)
    print("trials so far:", n_trials())
