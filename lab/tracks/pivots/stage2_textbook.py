"""Stage 2a: textbook pivot strategies, fixed a-priori parameters, each vs a pooled placebo."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import run, run_placebo, OUT

TEXTBOOK = {
    # buy S1 / sell R1 on first touch (limit), stop 0.25 ATR beyond, target P
    "tb_floor_S1R1_fade": dict(family="floor", levels=("S1", "R1"), mode="fade", roles="classic",
                               stop_atr=0.25, tgt="next"),
    # trade P as support/resistance (limit at P on first touch), target R1 / S1
    "tb_floor_P_fade": dict(family="floor", levels=("P",), mode="fade", stop_atr=0.25, tgt="next"),
    # M15 close above R1 -> long, below S1 -> short, stop 0.25 ATR back beyond the level, target R2/S2
    "tb_floor_S1R1_break": dict(family="floor", levels=("S1", "R1"), mode="break", tf=15, roles="classic",
                                stop_atr=0.25, tgt="next"),
    # Camarilla: fade H3/L3 (limit), stop 0.25 ATR beyond, target 1R
    "tb_cam_H3L3_fade": dict(family="cam", levels=("L3", "H3"), mode="fade", roles="classic",
                             stop_atr=0.25, tgt=1.0),
    # Camarilla: M15 close beyond H4/L4 -> with the break, stop 0.25 ATR back, target 2R
    "tb_cam_H4L4_break": dict(family="cam", levels=("L4", "H4"), mode="break", tf=15, roles="classic",
                              stop_atr=0.25, tgt=2.0),
}
BIAS = {
    # same with the open-vs-P bias (only buy S1 when the window opens above P, only sell R1 below P)
    "tb_floor_S1R1_fade_bias": dict(TEXTBOOK["tb_floor_S1R1_fade"], bias="with"),
    "tb_floor_S1R1_break_bias": dict(TEXTBOOK["tb_floor_S1R1_break"], bias="with"),
}

if __name__ == "__main__":
    res = {}
    for name, prm in TEXTBOOK.items():
        t, rep, rs, crit = run(name, prm)
        pl = run_placebo(name, prm)
        res[name] = {"params": prm, "is": rep, "stress_pf": rs.get("pf"), "crit": crit, "placebo": pl}
    for name, prm in BIAS.items():
        t, rep, rs, crit = run(name, prm)
        res[name] = {"params": prm, "is": rep, "stress_pf": rs.get("pf"), "crit": crit}
    with open(os.path.join(OUT, "stage2_textbook.json"), "w") as f:
        json.dump(res, f, indent=1, default=str)
