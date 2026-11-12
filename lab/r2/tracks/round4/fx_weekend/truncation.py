"""Causality (task rule 3): truncation tests of the main configuration, in sample only.

 A. 64 decisions (8 per pair: 5 signals + 3 non-signals drawn at random among the main's decided weekends): every
    decision quantity is recomputed on a frame CUT just after the P bar, whose high, low and close are blanked (only
    its open, the price the rule uses, survives).  F, P, sigma, z, threshold, history size, side, ATR, stop distance and
    the P bar must equal the full-frame values.  For the 40 signals, the order (entry bar = the bar after the P bar) and
    the simulated trade on a frame cut at its exit bar must equal the full-frame ones.
 B. Orders rebuilt on frames cut at 6 random times (eurusd, usdjpy) equal the full-frame orders whose scheduled exit
    is before the cut.

    PYTHONDONTWRITEBYTECODE=1 NUMBA_CACHE_DIR=/tmp/... python3 truncation.py
"""
import gc
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import wkfade as W  # noqa: E402
from goldlab import r2  # noqa: E402
from goldlab.sim import simulate  # noqa: E402

MAIN = dict(json.load(open(os.path.join(W.RES, "declared.json")))["configurations"][0]["params"])
FIELDS = ["jF", "F", "jP", "P", "sigma", "atr", "z", "thr", "n_hist", "decided", "signal", "side", "k_day"]


def same(a, b):
    if isinstance(a, (float, np.floating)) or isinstance(b, (float, np.floating)):
        if not np.isfinite(a) and not np.isfinite(b):
            return True
        return bool(np.isclose(a, b, rtol=1e-12, atol=0.0))
    return bool(a == b)


def main():
    rng = np.random.default_rng(31)
    out = {"A_decisions": [], "B_orders": []}
    for sym in W.PAIRS:
        m1 = W.load_is(sym)
        daily = W.daily_table(m1)
        d = W.decisions(m1, dec=MAIN["dec"], q=MAIN["q"], daily=daily)
        o_full = W.make_orders(m1, dtab=d, exit=MAIN["exit"], stop_atr=MAIN["stop_atr"])
        sig = np.flatnonzero(d.signal.to_numpy() & d.okE.to_numpy())
        non = np.flatnonzero(d.decided.to_numpy() & ~d.signal.to_numpy())
        pick = list(rng.choice(sig, 5, replace=False)) + list(rng.choice(non, 3, replace=False))
        for w in pick:
            row = d.iloc[w]
            j = int(row.jP)
            cut = m1.iloc[:j + 1].copy()
            for c in ("bh", "bl", "bc", "ah", "al", "ac"):
                cut.iloc[-1, cut.columns.get_loc(c)] = np.nan
            dc = W.decisions(cut, dec=MAIN["dec"], q=MAIN["q"])          # daily table rebuilt on the cut frame
            rc = dc[dc.sunday == row.sunday]
            assert len(rc) == 1
            rc = rc.iloc[0]
            diffs = [f for f in FIELDS if not same(row[f], rc[f])]
            rec = {"sym": sym, "sunday": str(row.sunday.date()), "signal": bool(row.signal), "z": round(float(row.z), 4),
                   "thr": round(float(row.thr), 4), "cut_at": str(cut.index[-1]), "fields_compared": len(FIELDS),
                   "identical": not diffs, "diffs": diffs}
            if row.signal:
                oc = W.make_orders(cut, dtab=dc, exit=MAIN["exit"], stop_atr=MAIN["stop_atr"])
                # on the cut frame the entry bar does not exist yet: the decision gives side and stop distance
                of = o_full[o_full.sunday == row.sunday].iloc[0]
                rec["order_entry_is_bar_after_P"] = bool(of.entry_i == j + 1)
                rec["stop_dist_identical"] = same(float(of.stop_dist), float(rc.atr) * MAIN["stop_atr"])
                rec["side_identical"] = bool(int(of.side) == int(rc.side))
                rec["orders_on_cut_frame"] = int((oc.sunday == row.sunday).sum())   # 0: entry bar not yet known
                # simulated trade on a frame cut at the exit bar == full-frame trade
                one = o_full[o_full.sunday == row.sunday]
                tf = simulate(m1, one, sym=sym, costs=r2.costs(sym), no_overlap=True)
                xb = int(np.searchsorted(W.naive_utc(m1), tf.exit_time.dt.tz_convert("UTC").dt.tz_localize(None)
                                         .values.astype("datetime64[ns]")[0]
                                         - (0 if tf.reason.iloc[0] == "time" else 1) * W.M))
                tc = simulate(m1.iloc[:xb + 1], one, sym=sym, costs=r2.costs(sym), no_overlap=True)
                rec["trade_R_full"] = round(float(tf.R.iloc[0]), 6)
                rec["trade_R_cut_at_exit"] = round(float(tc.R.iloc[0]), 6)
                rec["trade_identical"] = bool(np.isclose(tf.R.iloc[0], tc.R.iloc[0], rtol=0, atol=1e-12)
                                              and tf.reason.iloc[0] == tc.reason.iloc[0])
            out["A_decisions"].append(rec)
            del cut
        if sym in ("eurusd", "usdjpy"):
            cuts = np.sort(rng.integers(len(m1) // 3, len(m1) - 10, 6))
            for c in cuts:
                T = m1.index[c]
                sub = m1.iloc[:c]
                os_ = W.make_orders(sub, **MAIN)
                f = o_full[o_full.sched_exit < T - pd.Timedelta(minutes=1)]
                s = os_[os_.sched_exit < T - pd.Timedelta(minutes=1)]
                cols = ["entry_i", "side", "stop_dist", "exit_i", "z", "thr"]
                ok = len(f) == len(s) and bool(np.allclose(f[cols].to_numpy(float), s[cols].to_numpy(float),
                                                           rtol=1e-12, atol=0.0))
                out["B_orders"].append({"sym": sym, "cut": str(T), "orders_compared": int(len(f)), "identical": ok})
        print(sym, "done", flush=True)
        del m1, daily, d
        gc.collect()
    A = out["A_decisions"]
    S = [a for a in A if a["signal"]]
    out["summary"] = {
        "decisions_tested": len(A), "decisions_identical": sum(a["identical"] for a in A),
        "signals_tested": len(S),
        "orders_entry_bar_after_P": sum(a["order_entry_is_bar_after_P"] for a in S),
        "stop_and_side_identical": sum(a["stop_dist_identical"] and a["side_identical"] for a in S),
        "no_order_before_entry_bar_exists": sum(a["orders_on_cut_frame"] == 0 for a in S),
        "trades_identical_when_cut_at_exit": sum(a["trade_identical"] for a in S),
        "order_cuts_tested": len(out["B_orders"]), "order_cuts_identical": sum(b["identical"] for b in out["B_orders"]),
        "orders_compared_total": sum(b["orders_compared"] for b in out["B_orders"]),
    }
    W.jdump(out, os.path.join(W.RES, "truncation.json"))
    print(json.dumps(out["summary"], indent=1))


if __name__ == "__main__":
    main()
