"""T4 OC4 ocm4 (step D): every decision and every trade of OC4 over the whole in-sample period, against the lab.

    python3 -I lab/robot/check/test_OC4.py [--world all|is|holes|restarts] [--tag is|y2021] [--no-sanitize]
                                           [--sanitize-holes] [--full-tree] [--trace] [--fresh] [--verbose]

SPEC 7 T4/T5 for CRuleOC4 of src/CR_Rule_IdxUS.mqh. The same build, worlds (in sample, in sample with targeted holes,
in sample with restarts) and checks as test_N30.py (see its docstring; this file imports it and reuses its builds and
replays when the sources, flags and bars are unchanged): the DEC lines resolved on the frame equal the lab's make_orders
orders (entry bar, side, exit bar equal; stop_dist = 0.3 x the daily ATR within 1e-12 relative), every void the paper
makes is classified with the lab's grid (a 09:34 window without a kept bar; void_le: the 09:34 bar is the last before a
hole through 15:55, the lab's xi <= EI), the paper trades equal r2.run's (compare.cmp_trades, prices within 1e-12),
razors within 1e-9 of the size threshold listed, no ERROR, no SEND, no build warning, and the sanitizer build writes a
byte-identical journal.
In sample only: every frame and trade file is read with the 2022-01-01 cut inside the read call.
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_N30  # noqa: E402

if __name__ == "__main__":
    sys.exit(test_N30.main("OC4"))
