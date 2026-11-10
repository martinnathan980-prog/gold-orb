"""Stage A re-run of the 18 breakout configurations (identical parameters) after fixing a bookkeeping bug:
the extra order column `exit_time` (scheduled exit) overwrote the engine's real exit time in the trades frame,
so swaps were charged up to the scheduled exit and average holds were overstated for stopped / trailed trades.
Trials 1-26 in trials.jsonl carry that (pessimistic) bias; these lines replace trials 1-9 and 14-22.
The `sess` trials are unaffected in substance (no rollover inside the hold) and `pull` was rejected anyway."""
import sys
sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/crypto")
from helpers import *  # noqa
from stageA import GRID

if __name__ == "__main__":
    for sym in ("btcusd", "ethusd"):
        for p in GRID:
            if p["family"] == "brk":
                run_trial(sym, p, full=False, stage="A-rerun", note="same config as stage A, after exit_time column fix")
        r2.free()
