"""Stage A - pre-declared screen (written before any engine evaluation).

Three families, untuned exits, both instruments, IS only, quick evaluation (FP costs):
  brk  : close-channel breakout, n in {24, 72, 168} H1 bars x exits {stop 3 ATR + 12 h, stop 3 ATR + 24 h,
         stop 2.5 ATR + trailing 2.5 ATR + 72 h}
  sess : Asia -> Europe timed momentum (decision 08:00 UTC, sign of the 00:00-08:00 move), exit 13:00 or 21:00 UTC
  pull : pullback in the 7-day trend (new 6- or 24-bar close extreme against the trend), stop 3 ATR, 24 h
"Promising" bar for stage B (declared now): PF >= 1.10 and t >= 1.5 on at least one instrument with the other
instrument's expectancy > 0, and the short side not losing on both instruments.
"""
import json, sys
sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/crypto")
from helpers import *  # noqa

GRID = []
for n in (24, 72, 168):
    GRID.append({"family": "brk", "n": n, "stop_atr": 3.0, "hold_h": 12})
    GRID.append({"family": "brk", "n": n, "stop_atr": 3.0, "hold_h": 24})
    GRID.append({"family": "brk", "n": n, "stop_atr": 2.5, "trail_atr": 2.5, "hold_h": 72})
GRID.append({"family": "sess", "dec_h": 8, "look_h": 8, "stop_atr": 3.0, "hold_h": 5})
GRID.append({"family": "sess", "dec_h": 8, "look_h": 8, "stop_atr": 3.0, "hold_h": 13})
GRID.append({"family": "pull", "trend_n": 168, "pb_n": 6, "stop_atr": 3.0, "hold_h": 24})
GRID.append({"family": "pull", "trend_n": 168, "pb_n": 24, "stop_atr": 3.0, "hold_h": 24})

if __name__ == "__main__":
    for sym in ("btcusd", "ethusd"):
        for p in GRID:
            run_trial(sym, p, full=False, stage="A")
        r2.free()
