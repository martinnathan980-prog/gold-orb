"""Stage A -- CONFIRMATORY re-tests under FP costs of the round-1 gross-positive rules, with their
round-1 parameters (pre-declared here, before any FP-cost result was seen; no re-tuning).
Gold first, then the same rules with the same parameters on silver (independent check)."""
import json
import os
import sys

from research import RES, run, n_configs

ORB = dict(family="orb", exit_min=960, exit_tz="NY", hold_days=0, buf_frac=0.0)
A = {
    # label: (params, round-1 reference)
    "A1_orb_asia_00-07ldn": ({**ORB, "tz": "LDN", "range_start": 0, "range_end": 420, "entry_end": 720},
                             "orb S1: gross +0.109 R, net -0.025 R, PF 0.95"),
    "A2_orb_ldn_0800-0830": ({**ORB, "tz": "LDN", "range_start": 480, "range_end": 510, "entry_end": 720},
                             "orb S2: gross +0.190 R, net -0.097 R, PF 0.88"),
    "A3_orb_ldn_0800-0900": ({**ORB, "tz": "LDN", "range_start": 480, "range_end": 540, "entry_end": 720},
                             "orb S3: gross +0.143 R, net -0.085 R, PF 0.88"),
    "A4_orb_us_0930-0945": ({**ORB, "tz": "NY", "range_start": 570, "range_end": 585, "entry_end": 720},
                            "orb S6: gross +0.162 R, net -0.098 R, PF 0.85"),
    "A5_orb_asia_2d_buf10": ({**ORB, "tz": "LDN", "range_start": 0, "range_end": 420, "entry_end": 720,
                              "buf_frac": 0.1, "hold_days": 2},
                             "orb finalist F3: IS PF 1.196 t 1.99 (failed IS narrowly); its VAL AND the 2026 holdout "
                             "were already consumed in round 1 -> informative only, cannot be a clean finalist"),
    "A6_rn100_break_fresh": (dict(family="rn", grid=100.0, win_start_ldn=480, win_end_ny=720, exit_ny=960,
                                  stop_atr=0.4, tgt_r=1.0),
                             "pivots finalist: IS PF 1.379 t 2.26 n 225; FAILED VAL (PF 0.84; 0.94 even at zero "
                             "commission and slippage) -> known VAL failure, informative only"),
    "A0_ref_legacy_donch4h_stop": (dict(family="donch", tf=240, n=60, stop_atr=2.0, trail_atr=2.0, max_days=5, atr_n=14),
                                   "round-1 survivor, REFERENCE ONLY (legacy sleeve of the lead; not a candidate here): "
                                   "needed to measure how much new sleeves duplicate it"),
}
SILVER = ["A1_orb_asia_00-07ldn", "A2_orb_ldn_0800-0830", "A3_orb_ldn_0800-0900", "A4_orb_us_0930-0945",
          "A5_orb_asia_2d_buf10", "A0_ref_legacy_donch4h_stop"]

if __name__ == "__main__":
    plan = {"stage": "A-confirmatory", "declared_before_running": True,
            "xauusd": {k: {"params": v[0], "round1": v[1]} for k, v in A.items()},
            "xagusd": SILVER,
            "note": "rn100 is not run on silver (a 100-dollar grid has no meaning there)."}
    pth = os.path.join(RES, "plan_stageA.json")
    if not os.path.exists(pth):
        json.dump(plan, open(pth, "w"), indent=1)
    which = sys.argv[1] if len(sys.argv) > 1 else "xauusd"
    if which == "xauusd":
        for k, (p, _) in A.items():
            run(k, "A-confirmatory", "xauusd", p, full=True)
    else:
        for k in SILVER:
            run(k, "A-confirmatory-silver", "xagusd", A[k][0], full=True)
    print("configurations so far:", n_configs())
