"""Stage 2b: event-study-informed hypothesis -- key levels (round $50, PDH/PDL) BREAK THROUGH at
first touch.  Resting stop order at the level, window 08:00 London -> 12:00 NY, forced exit 16:00 NY.
Grid (a priori, same for both families): stop {0.25, 0.4, 0.6} x ATR, target {1R, 2R, none}."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import run, OUT

BASE = {
    "rn50": dict(family="round", levels=("RB", "RA"), grid=50.0, mode="tbreak"),
    "pdhl": dict(family="pdhl", levels=("PDL", "PDH"), mode="tbreak", roles="classic"),
}
if __name__ == "__main__":
    res = {}
    for fam, base in BASE.items():
        for sa in (0.25, 0.4, 0.6):
            for tg in (1.0, 2.0, None):
                name = f"{fam}_tbreak_s{sa}_t{tg}"
                prm = dict(base, stop_atr=sa, tgt=tg)
                t, rep, rs, crit = run(name, prm)
                res[name] = {"params": prm, "is": rep, "stress_pf": rs.get("pf"), "crit": crit}
    with open(os.path.join(OUT, "stage2_breakout.json"), "w") as f:
        json.dump(res, f, indent=1, default=str)
