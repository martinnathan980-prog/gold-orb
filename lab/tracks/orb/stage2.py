"""Stage 2 (declared after stage 1, before running): attack the cost share, test Crabel's
narrow-range idea, and control for intraday drift.  Families = the three stage-1 configs with a
positive estimated GROSS edge: Asia range (S1), London 08-09 (S3), US open 09:30-09:45 (S6).

  *1  stop = 0.5 x daily ATR (decoupled from the narrow range -> cost/R falls)
  *2  opposite-side stop, but skip when est. cost > 15% of risk (cost-share filter)
  A3  multi-day follow-through: hold to 16:00 NY two business days later
  A4/L4 Crabel narrow range: range width <= 0.30 (Asia) / 0.15 (London) daily ATR (~median)
  *5/L3/U3 fixed 2R target (target exits pay no slippage)
  C1/C2 drift controls: unconditional short / long at 07:00 London, stop 0.4 ATR, exit 16:00 NY
"""
from research import run, n_trials

BASE = dict(entry="stop", stop_mode="opp", target_R=None, exit_time="16:00", exit_tz="NY")
ASIA = dict(tz="LDN", range_start="00:00", range_end="07:00", entry_end="12:00")
LDN = dict(tz="LDN", range_start="08:00", range_end="09:00", entry_end="12:00")
US = dict(tz="NY", range_start="09:30", range_end="09:45", entry_end="12:00")
S2 = {
    "A1_asia_atr0.5": {**ASIA, "stop_mode": "atr", "stop_atr": 0.5},
    "A2_asia_cost15": {**ASIA, "max_cost_R": 0.15},
    "A3_asia_hold2d": {**ASIA, "hold_days": 2},
    "A4_asia_narrow0.30": {**ASIA, "max_width_atr": 0.30},
    "A5_asia_tgt2R": {**ASIA, "target_R": 2.0},
    "L1_ldn60_atr0.5": {**LDN, "stop_mode": "atr", "stop_atr": 0.5},
    "L2_ldn60_cost15": {**LDN, "max_cost_R": 0.15},
    "L3_ldn60_tgt2R": {**LDN, "target_R": 2.0},
    "L4_ldn60_narrow0.15": {**LDN, "max_width_atr": 0.15},
    "U1_us15_atr0.5": {**US, "stop_mode": "atr", "stop_atr": 0.5},
    "U2_us15_cost15": {**US, "max_cost_R": 0.15},
    "U3_us15_tgt2R": {**US, "target_R": 2.0},
    "C1_ctrl_short0700": {**ASIA, "entry": "market", "sides": "short", "stop_mode": "atr", "stop_atr": 0.4},
    "C2_ctrl_long0700": {**ASIA, "entry": "market", "sides": "long", "stop_mode": "atr", "stop_atr": 0.4},
}
if __name__ == "__main__":
    for k, v in S2.items():
        run(k, {**BASE, **v}, stage="2-cost/filters")
    print("trials so far:", n_trials())
