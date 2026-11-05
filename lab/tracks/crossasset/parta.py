"""Part A - predicting gold with other markets (IS only, every config logged).

Pre-specified configs (rationale in report.md):
  A1 lead-lag: sharp USD-basket move not yet reflected in gold -> gold catch-up
  A2 divergence: cumulative gold residual vs rolling-beta USD basket -> reversion toward basket
  A3 risk-off: (a) yen shock -> gold follows the yen; (b) DAX risk-off/on European session
  A4 USD trend filter on the gold H4 breakout (confirm vs contra)
"""
import json
import sys

import pandas as pd

from common import gl, load_bars, run_and_log
import strategy as S

CONFIGS = {
    "A1a_leadlag_m5": dict(rule="leadlag", tf="5min", k_sigma=3.0, max_cover=0.5, hold_min=60, win=5760, stop_k=1.5),
    "A1b_leadlag_m15": dict(rule="leadlag", tf="15min", k_sigma=3.0, max_cover=0.5, hold_min=120, win=1920, stop_k=1.5),
    "A2a_div_h1_n24": dict(rule="diverge", tf="1h", n=24, z_in=2.0, win=1380, hold_days=1, stop_k=1.5, direction=-1),
    "A2b_div_h1_n72": dict(rule="diverge", tf="1h", n=72, z_in=2.0, win=1380, hold_days=3, stop_k=1.5, direction=-1),
    "A2c_div_asia_ldnopen": dict(rule="diverge", tf="1h", n=8, z_in=1.0, win=1380, hold_h=8, stop_k=1.5,
                                 direction=-1, at_hour=8),
    "A3a_yen_h1": dict(rule="yen", tf="1h", z_in=2.5, win=480, hold_h=8, stop_k=1.5),
    "A3a_yen_h1_ldnmorning": dict(rule="yen", tf="1h", z_in=2.5, win=480, hold_h=8, stop_k=1.5,
                                  start_hours=[7, 8, 9, 10, 11, 12], note="session chosen after descriptive IS split"),
    "A3b_riskoff_follow": dict(rule="riskoff", z_in=1.0, win=60, mode="follow", exit_min=1260, stop_k=1.0),
    "A3b_riskoff_giveback": dict(rule="riskoff", z_in=1.0, win=60, mode="giveback", hold_days=3, stop_k=1.0),
    "A4a_channel_usd_confirm": dict(rule="channel_usd", n=20, usd_n=20, mode="confirm"),
    "A4b_channel_usd_contra": dict(rule="channel_usd", n=20, usd_n=20, mode="contra"),
    # A5: residual momentum (hypothesis formed on IS after A2a/A2b + explore_resmom.py)
    "A5a_resmom_n24_h3": dict(rule="diverge", tf="1h", n=24, z_in=2.0, win=1380, hold_days=3, stop_k=1.5,
                              direction=1, note="sign flipped after A2a/A2b (IS) + descriptive check"),
    "A5b_rawmom_n24_h3_control": dict(rule="diverge", tf="1h", n=24, z_in=2.0, win=1380, hold_days=3,
                                      stop_k=1.5, direction=1, component="gold",
                                      note="control: same rule on raw gold return (no cross-asset info)"),
}
# neighbours of the best near-miss (A3a_yen_h1_ldnmorning): +-20% z, +-25% hold, session window +-1h
_BASE = CONFIGS["A3a_yen_h1_ldnmorning"]
NEIGH_YEN = {
    "N_yen_z2.0": {**_BASE, "z_in": 2.0}, "N_yen_z3.0": {**_BASE, "z_in": 3.0},
    "N_yen_hold6": {**_BASE, "hold_h": 6}, "N_yen_hold10": {**_BASE, "hold_h": 10},
    "N_yen_sess6-11": {**_BASE, "start_hours": [6, 7, 8, 9, 10, 11]},
    "N_yen_sess8-13": {**_BASE, "start_hours": [8, 9, 10, 11, 12, 13]},
}
for _k in NEIGH_YEN:
    NEIGH_YEN[_k] = {**NEIGH_YEN[_k], "note": "neighbour of A3a_yen_h1_ldnmorning"}
CONFIGS.update(NEIGH_YEN)


def make_cache():
    c = {}
    for s in ["xauusd", "eurusd", "gbpusd", "usdjpy"]:
        for tf in ["5min", "15min", "1h", "4h"]:
            c[(s, tf)] = load_bars(s, tf)
    c[("deuidxeur", "5min")] = load_bars("deuidxeur", "5min")
    c[("xauusd", "D")] = load_bars("xauusd", "D")
    return c


def run(names, m1=None, cache=None, log=True, extra=None):
    m1 = m1 if m1 is not None else gl.load_m1("xauusd")
    cache = cache if cache is not None else make_cache()
    out = {}
    for name in names:
        p = dict(CONFIGS[name]) if name in CONFIGS else dict(extra[name])
        note = p.pop("note", None)
        o = S.make_orders(m1, None, cache=cache, **p)
        cfg = {"part": "A", "name": name, **p}
        if note:
            cfg["note"] = note
        print(f"--- {name}: {len(o)} orders", flush=True)
        t, rep, rs, crit = run_and_log(m1, o, cfg, log=log)
        out[name] = (t, rep, rs, crit)
    return out


if __name__ == "__main__":
    run(sys.argv[1:] or list(CONFIGS))
