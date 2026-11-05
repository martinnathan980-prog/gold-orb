"""Stage 4 (last exploration batch, pre-declared): 'first touch of the day only' for round-number
break-through (fresh stop clusters), and the random-phase placebo of the $100 intraday rule."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import run, run_placebo, OUT
from stage3_round import STAGE3, RN

STAGE4 = {
    "rn100_tbreak_s0.4_t1_fresh": dict(STAGE3["rn100_tbreak_s0.4_t1"], fresh=True),
    "rn50_tbreak_s0.4_t1_fresh": dict(RN, stop_atr=0.4, tgt=1.0, fresh=True),
}
if __name__ == "__main__":
    res = {}
    for name, prm in STAGE4.items():
        t, rep, rs, crit = run(name, prm)
        res[name] = {"params": prm, "is": rep, "stress_pf": rs.get("pf"), "crit": crit}
    res["rn100_tbreak_s0.4_t1/PLACEBO"] = run_placebo("rn100_tbreak_s0.4_t1", STAGE3["rn100_tbreak_s0.4_t1"])
    with open(os.path.join(OUT, "stage4_fresh.json"), "w") as f:
        json.dump(res, f, indent=1, default=str)
