"""Stage 2c: remaining textbook pivot variants named in the brief (fixed a-priori parameters)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import run, run_placebo, OUT
from stage2_textbook import TEXTBOOK

FADE = TEXTBOOK["tb_floor_S1R1_fade"]
BRK = TEXTBOOK["tb_floor_S1R1_break"]
VARIANTS = {
    # rejection candle: touch S1/R1, then first M15 (M5) close back inside -> market, stop 0.25 ATR beyond
    "tb_floor_S1R1_reject15": (dict(FADE, mode="reject", tf=15), True),
    "tb_floor_S1R1_reject5": (dict(FADE, mode="reject", tf=5), False),
    # acceptance on H1: H1 close beyond R1/S1
    "tb_floor_S1R1_breakH1": (dict(BRK, tf=60), False),
    # exhaustion: fade only if the day already moved >= 1 ATR before the touch
    "tb_floor_S1R1_fade_exh": (dict(FADE, rng=(1.0, 99.0)), False),
    # room to run: break only if the day's range so far < 0.6 ATR
    "tb_floor_S1R1_break_fresh": (dict(BRK, rng=(0.0, 0.6)), False),
    # weekly pivots, multi-day: fade WS1/WR1 (target WP), break WR1/WS1 on H1 close (target WR2/WS2),
    # stop 0.5 daily ATR, forced exit 16:00 NY three trading days later
    "tb_weekly_fade": (dict(family="wfloor", levels=("WS1", "WR1"), mode="fade", roles="classic",
                            stop_atr=0.5, tgt="next", hold_days=3), True),
    "tb_weekly_breakH1": (dict(family="wfloor", levels=("WS1", "WR1"), mode="break", tf=60, roles="classic",
                               stop_atr=0.5, tgt="next", hold_days=3), True),
}
if __name__ == "__main__":
    res = {}
    for name, (prm, plac) in VARIANTS.items():
        t, rep, rs, crit = run(name, prm)
        res[name] = {"params": prm, "is": rep, "stress_pf": rs.get("pf"), "crit": crit}
        if plac:
            res[name]["placebo"] = run_placebo(name, prm)
    with open(os.path.join(OUT, "stage2_variants.json"), "w") as f:
        json.dump(res, f, indent=1, default=str)
