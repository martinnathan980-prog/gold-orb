"""Stage B -- NEW sleeves on gold (grid declared here before running; in-sample only).

What stage A showed (FP costs, 2013-2021): the intraday session breakouts stay below the bar on gold
(PF 1.08-1.11, t 1.2-1.8, profit only on the short side) and have no gross edge on silver; the only
effect that holds on both metals is the multi-day channel breakout with a trailing stop (legacy rule:
gold PF 1.51, silver gross PF 1.38 / net 1.14).  EDA 1: no follow-through after large bars -> no rule.
Stage B therefore asks whether the channel-breakout effect can be traded FASTER (1h bars, tighter
stops, shorter channels, session / trend / contraction conditions, pullback entries)."""
import json
import os
import sys

from research import RES, run, n_configs

D = dict(family="donch", tf=60, atr_n=14, max_days=5)
B = {
    # B1: faster bars with multi-day channels (stop = trail = k x ATR14(1h); k = 4 would be the legacy rule)
    "B1_d1h_n240_k2": {**D, "n": 240, "stop_atr": 2.0, "trail_atr": 2.0},
    "B1_d1h_n240_k3": {**D, "n": 240, "stop_atr": 3.0, "trail_atr": 3.0},
    "B1_d1h_n120_k2": {**D, "n": 120, "stop_atr": 2.0, "trail_atr": 2.0},
    "B1_d1h_n120_k3": {**D, "n": 120, "stop_atr": 3.0, "trail_atr": 3.0},
    # B2: session-restricted (bracket placed only at bar closes inside the London-clock window)
    "B2_d1h_n240_k2_ldnny": {**D, "n": 240, "stop_atr": 2.0, "trail_atr": 2.0, "sess_start": 420, "sess_end": 1020},
    "B2_d1h_n240_k2_overlap": {**D, "n": 240, "stop_atr": 2.0, "trail_atr": 2.0, "sess_start": 780, "sess_end": 1020},
    "B2_d1h_n120_k2_ldnny": {**D, "n": 120, "stop_atr": 2.0, "trail_atr": 2.0, "sess_start": 420, "sess_end": 1020},
    "B2_d1h_n120_k2_overlap": {**D, "n": 120, "stop_atr": 2.0, "trail_atr": 2.0, "sess_start": 780, "sess_end": 1020},
    # B3: shorter-channel breakouts taken only in the direction of the slower channel state
    "B3_d1h_n120_tr480_k2": {**D, "n": 120, "stop_atr": 2.0, "trail_atr": 2.0, "trend_n": 480},
    "B3_d1h_n120_tr480_k3": {**D, "n": 120, "stop_atr": 3.0, "trail_atr": 3.0, "trend_n": 480},
    "B3_d1h_n48_tr240_k2": {**D, "n": 48, "stop_atr": 2.0, "trail_atr": 2.0, "trend_n": 240},
    # B4: pullback entry inside a trend (trend = last touched extreme of the 240-bar channel; the bar that
    #     makes the pb_n-bar low/high sets a stop order at its other end for the next bar)
    "B4_pb1h_tr240_pb12": dict(family="pullback", tf=60, trend_n=240, pb_n=12, stop_buf=0.25, trail_atr=2.0, max_days=5),
    "B4_pb1h_tr240_pb24": dict(family="pullback", tf=60, trend_n=240, pb_n=24, stop_buf=0.25, trail_atr=2.0, max_days=5),
    # B5: volatility-contraction breakout (short channel, only when its width <= 0.7 x its 20-day median)
    "B5_sq1h_n24_07": {**D, "n": 24, "stop_atr": 2.0, "trail_atr": 2.0, "squeeze": 0.7, "squeeze_ref": 480},
    "B5_sq1h_n48_07": {**D, "n": 48, "stop_atr": 2.0, "trail_atr": 2.0, "squeeze": 0.7, "squeeze_ref": 480},
}

if __name__ == "__main__":
    pth = os.path.join(RES, "plan_stageB.json")
    if not os.path.exists(pth):
        json.dump({"stage": "B-new-sleeves", "declared_before_running": True, "sym": "xauusd", "configs": B,
                   "rationale": __doc__}, open(pth, "w"), indent=1)
    for k, p in B.items():
        run(k, "B-new", "xauusd", p, full=True)
    print("configurations so far:", n_configs())
