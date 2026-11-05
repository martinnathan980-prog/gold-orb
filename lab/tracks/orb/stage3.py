"""Stage 3 (declared after stage 2): is the multi-day follow-through real?
  - hold-length profile on the Asia breakout: hold_days 1, 3, 4 (A3 = 2)
  - does it generalise to the other opening ranges? London 08-09 and US 09:30-09:45, hold 2 days
"""
from research import run, n_trials
from stage2 import BASE, ASIA, LDN, US

S3 = {
    "A6_asia_hold1d": {**ASIA, "hold_days": 1},
    "A7_asia_hold3d": {**ASIA, "hold_days": 3},
    "A8_asia_hold4d": {**ASIA, "hold_days": 4},
    "L5_ldn60_hold2d": {**LDN, "hold_days": 2},
    "U4_us15_hold2d": {**US, "hold_days": 2},
}
if __name__ == "__main__":
    for k, v in S3.items():
        run(k, {**BASE, **v}, stage="3-hold")
    print("trials so far:", n_trials())
