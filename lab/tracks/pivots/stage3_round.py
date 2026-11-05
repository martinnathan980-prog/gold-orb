"""Stage 3: round-number break-through refinements with an a-priori rationale (pre-declared list).
Osler (2003): stop-losses cluster just BEYOND round numbers -> enter a little beyond (offset).
Aggarwal & Lucey (2007), Lucey & O'Connor (2016): barriers strongest at '00' -> $100 grid; $25 grid
for frequency.  Multi-day hold: does the crossing start a multi-day move?  Placebo = random-phase grid."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import run, run_placebo, OUT

RN = dict(family="round", levels=("RB", "RA"), grid=50.0, mode="tbreak")
STAGE3 = {
    "rn50_tbreak_s0.4_t1_off0.05": dict(RN, stop_atr=0.4, tgt=1.0, offset_atr=0.05),
    "rn50_tbreak_s0.6_tNone_hold2": dict(RN, stop_atr=0.6, tgt=None, hold_days=2),
    "rn100_tbreak_s0.4_t1": dict(RN, grid=100.0, stop_atr=0.4, tgt=1.0),
    "rn25_tbreak_s0.4_t1": dict(RN, grid=25.0, stop_atr=0.4, tgt=1.0),
    "rn50_tbreak_s0.4_t1_win15NY": dict(RN, stop_atr=0.4, tgt=1.0, win=("LDN", 480, "NY", 900)),
}
PLACEBOS = {
    "rn50_tbreak_s0.4_t1.0": dict(RN, stop_atr=0.4, tgt=1.0),
    "rn50_tbreak_s0.6_tNone": dict(RN, stop_atr=0.6, tgt=None),
}
if __name__ == "__main__":
    res = {}
    for name, prm in STAGE3.items():
        t, rep, rs, crit = run(name, prm)
        res[name] = {"params": prm, "is": rep, "stress_pf": rs.get("pf"), "crit": crit}
    for name, prm in PLACEBOS.items():
        res[name + "/PLACEBO"] = run_placebo(name, prm)
    with open(os.path.join(OUT, "stage3_round.json"), "w") as f:
        json.dump(res, f, indent=1, default=str)
