"""Causality truncation test of the main (declared.json D15), in sample only.

(a) DECISIONS: for each tested trade, the decisions are rebuilt on the in-sample frame cut just before the decision
    instant (rows ts < 15:55 NY of the entry day): side, decision time, scheduled exit and stop distance must be
    identical (exact) to those of the full in-sample frame.
(b) OUTCOMES: each tested trade is re-simulated alone on the frame cut just after its exit bar (rows ts <= exit bar):
    exit time, exit price, reason and R must be identical.
(c) For every trade of the main: entry bar start >= decision instant; the ATR's daily bar was complete (17:00 NY of
    the previous trading day) before the decision; time exits at a bar start >= the scheduled time, or on the last
    bar before a closure.
Tested trades: 60 drawn with numpy default_rng(1) + the first and the last trade.
Output: results/r2/round4/fomc_cycle/truncation.json
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

import json  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from goldlab.sim import simulate  # noqa: E402

P = json.load(open(os.path.join(C.OUT, "declared.json")))["configurations"][0]["params"]


def main():
    us = C.load_is("us500")
    t, o, ok = C.run(us, P)                      # reference (full in-sample frame)
    rng = np.random.default_rng(1)
    pick = sorted(set(rng.choice(len(t), 60, replace=False).tolist() + [0, len(t) - 1]))
    days = C.nyse_days()[0]
    lab = C.day_labels(days, C.FOMC, P["shift"])
    blk = C.blocks(lab, C.side_map(P["mode"], P["wm1_side"]))
    idx = us.index
    rows, bad_a, bad_b = [], 0, 0
    for k in pick:
        r = t.loc[t.index[k]]
        orow = ok.loc[t.index[k]]
        # (a) decisions on the frame cut before the decision instant
        cut_a = us[us.index < r.t_dec]
        dec_a = C.decisions(cut_a, blk, P["clock"], P["stop_k"])
        m = dec_a[(dec_a.entry_day == r.entry_day) & (dec_a.last_day == r.last_day) & (dec_a.wlabel == r.wlabel)]
        assert len(m) == 1
        m = m.iloc[0]
        a_ok = bool(m.side == r.side and m.t_dec == r.t_dec and m.t_exit_sched == r.t_exit_sched
                    and m.stop_dist == orow.stop_dist and m.atr20 == r.atr20)
        # (b) outcome on the frame cut just after the exit bar
        xbar = r.exit_time - pd.Timedelta(minutes=1) if r.reason == "stop" else r.exit_time
        cut_b = us[us.index <= xbar]
        one = pd.DataFrame({"entry_i": [int(orow.entry_i)], "side": [int(orow.side)], "etype": [0],
                            "stop_dist": [float(orow.stop_dist)], "exit_i": [int(orow.exit_i)]})
        tb = simulate(cut_b, one, sym="us500", costs=C.costs_for("us500", "fp"), no_overlap=False)
        b = tb.iloc[0]
        b_ok = bool(b.exit_time == r.exit_time and b.exit == r.exit and b.reason == r.reason and b.R == r.R)
        bad_a += not a_ok
        bad_b += not b_ok
        rows.append({"k": int(k), "week": r.wlabel, "side": int(r.side), "t_dec": str(r.t_dec), "entry_bar": str(r.entry_time),
                     "rows_cut_a": int(len(cut_a)), "stop_dist_full": float(orow.stop_dist), "stop_dist_cut": float(m.stop_dist),
                     "a_identical": a_ok, "exit_bar": str(xbar), "rows_cut_b": int(len(cut_b)), "reason": r.reason,
                     "exit_full": float(r.exit), "exit_cut": float(b.exit), "R_full": float(r.R), "R_cut": float(b.R),
                     "b_identical": b_ok})
    # (c) all trades
    tk, _ = C.idxus_lib.daily_atr(us, C.ATR_N)
    dec_ns = t.t_dec.dt.tz_convert("UTC").dt.tz_localize(None).to_numpy().astype("datetime64[ns]")
    j = np.searchsorted(tk, dec_ns, side="right") - 1
    atr_known = pd.DatetimeIndex(tk[j]).tz_localize("UTC")
    c = {"n_trades": int(len(t)),
         "entry_bar_at_or_after_decision": int((t.entry_time >= t.t_dec).sum()),
         "atr_day_complete_before_decision": int((atr_known <= t.t_dec.to_numpy()).sum()),
         "atr_day_is_previous_trading_day_or_earlier": int((pd.DatetimeIndex(tk[j]).normalize() < pd.DatetimeIndex(t.entry_day)).sum()),
         "time_exits": int((t.reason == "time").sum()),
         "time_exit_at_or_after_schedule": int(((t.reason == "time") & (t.exit_time >= t.t_exit_sched)).sum()),
         "time_exit_moved_before_a_closure": int(((t.reason == "time") & (t.exit_time < t.t_exit_sched)).sum()),
         "stop_exits": int((t.reason == "stop").sum())}
    out = {"what": "truncation test of the main (D15)", "decisions_tested": len(rows),
           "a_decisions_identical": len(rows) - bad_a, "b_outcomes_identical": len(rows) - bad_b,
           "pass": bool(bad_a == 0 and bad_b == 0 and len(rows) >= 50 and c["entry_bar_at_or_after_decision"] == len(t)
                        and c["atr_day_complete_before_decision"] == len(t)),
           "all_trades_checks": c, "rows": rows}
    C.jdump(out, os.path.join(C.OUT, "truncation.json"))
    print({k: v for k, v in out.items() if k != "rows"})


if __name__ == "__main__":
    main()
