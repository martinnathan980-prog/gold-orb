"""Stage 4 (declared after stage 3, last exploratory round): remaining ideas from the brief on the
best base so far (A3 = Asia range breakout, opposite-side stop, exit 16:00 NY two business days later).
  F1 prior-day trend: arm only the side of the last completed day's close-open
  F2 longer trend: arm only the side of close vs SMA50 (daily)
  F3 buffer 10% of range width beyond each side (fewer marginal breaks)
  F4 break-even once +1R
  F5 let it run: max hold 4 business days + trailing stop 1.0 x daily ATR
"""
from research import run, n_trials
from stage2 import BASE, ASIA

A3 = {**ASIA, "hold_days": 2}
S4 = {
    "F1_A3_trend_prevday": {**A3, "trend": "prev_day"},
    "F2_A3_trend_sma50": {**A3, "trend": "sma", "trend_n": 50},
    "F3_A3_buf0.1": {**A3, "buf_frac": 0.1},
    "F4_A3_be1R": {**A3, "be_R": 1.0},
    "F5_asia_hold4_trail1atr": {**ASIA, "hold_days": 4, "trail_atr": 1.0},
}
if __name__ == "__main__":
    for k, v in S4.items():
        run(k, {**BASE, **v}, stage="4-filters/exits")
    print("trials so far:", n_trials())
