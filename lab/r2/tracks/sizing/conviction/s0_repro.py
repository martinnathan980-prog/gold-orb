"""FIRST CHECK (task rule 2): reproduce the in-sample reference of the ten sleeves before any analysis.

For each sleeve: the rule is run by its registry entry (r2/recalc.py::sleeves(), through the context lens's helpers) on
the IN-SAMPLE FP frame (rows ts < 2022-01-01 only), mode fp, one position (no_overlap=True), and compared row by row
with the official trades read with entry_time < 2022-01-01. Also checks that the context lens's chain files (used as
the baseline chains of this lens) are exactly these trades minus the trades still open when the slice ends, in both
cost modes. Writes results/r2/sizing/conviction/repro.json."""
import gc
import os
import time

import numpy as np
import pandas as pd

import cv_common as V
CC = V.CC


def compare(mine, off):
    a = mine[["entry_time", "side", "R", "exit_time", "reason"]].copy()
    b = off[["entry_time", "side", "R", "exit_time", "reason"]].copy()
    a["entry_time"] = pd.DatetimeIndex(a.entry_time).as_unit("ns")
    b["entry_time"] = pd.DatetimeIndex(b.entry_time).as_unit("ns")
    m = a.merge(b, on=["entry_time", "side"], how="outer", suffixes=("_mine", "_off"), indicator=True)
    both = m[m._merge == "both"]
    same = np.isclose(both.R_mine, both.R_off, rtol=0, atol=1e-9)
    diff = both[~same]
    return {
        "n_mine": int(len(a)), "n_official": int(len(b)),
        "totR_mine": round(float(a.R.sum()), 4), "totR_official": round(float(b.R.sum()), 4),
        "identical_rows": int(same.sum()), "only_mine": int((m._merge == "left_only").sum()),
        "only_official": int((m._merge == "right_only").sum()),
        "differing": [{"entry_time": str(r.entry_time), "side": int(r.side), "R_mine": round(float(r.R_mine), 4),
                       "R_official": round(float(r.R_off), 4), "exit_mine": str(r.exit_time_mine),
                       "exit_official": str(r.exit_time_off), "reason_mine": r.reason_mine,
                       "reason_official": r.reason_off} for r in diff.itertuples()],
    }


def run_market(sym, keys, m1, out):
    for k in keys:
        name = CC.registry()[k][1]
        res = {}
        for mode in V.MODES:
            t0 = time.time()
            mk = CC.mode_frame(m1, mode)
            import signals as SG  # context lens module (cache clearing helper)
            SG.clear_caches()
            o = CC.build_orders(k, mk)
            o["oid"] = np.arange(len(o), dtype=np.int64)
            t = CC.sim(k, mk, o, mode, no_overlap=True)
            t = t[t.entry_time < V.IS_END].reset_index(drop=True)
            last_start = mk.index[-1]
            open_at_end = (t.exit_time >= last_start).to_numpy()
            ch = V.load_chain(k, mode)
            # chain file = trades minus refused orders (stop < 3 spreads; none in fp) minus trades open at the end
            sig = V.load_signals(k, mode)
            refused = set(sig.oid[sig.refused].tolist())
            if refused:
                t2 = CC.sim(k, mk, o[~o.oid.isin(refused)], mode, no_overlap=True)
                t2 = t2[t2.entry_time < V.IS_END].reset_index(drop=True)
                open2 = (t2.exit_time >= last_start).to_numpy()
                tc = t2[~open2].reset_index(drop=True)
            else:
                tc = t[~open_at_end].reset_index(drop=True)
            same_chain = (len(tc) == len(ch) and (tc.oid.to_numpy() == ch.oid.to_numpy()).all()
                          and np.allclose(tc.R.to_numpy(), ch.R.to_numpy(), rtol=0, atol=1e-12))
            r = {"orders": int(len(o)), "orders_equal_signal_table": bool(len(o) == len(sig)),
                 "trades": int(len(t)), "totR": round(float(t.R.sum()), 4),
                 "open_at_slice_end": int(open_at_end.sum()), "refused_stop_lt_3_spreads": int(len(refused)),
                 "chain_file_n": int(len(ch)), "chain_file_R": round(float(ch.R.sum()), 4),
                 "chain_file_equals_my_trades_minus_open_and_refused": bool(same_chain),
                 "sec": round(time.time() - t0, 1)}
            if mode == "fp":
                off = V.load_official_is(name, V.SYM[k])
                r["vs_official"] = compare(t, off)
                r["official_exits_in_2022"] = int((off.exit_time >= V.IS_END).sum())
            res[mode] = r
            del mk
            gc.collect()
        print(k, {m: {q: res[m][q] for q in ("trades", "totR", "open_at_slice_end",
                                             "chain_file_equals_my_trades_minus_open_and_refused")} for m in res},
              res["fp"]["vs_official"]["n_official"], res["fp"]["vs_official"]["totR_official"],
              res["fp"]["vs_official"]["identical_rows"], flush=True)
        out[k] = res


def main():
    out = {}
    us = CC.load_fp_is("us100")
    run_market("us100", ["ocm4__us100", "noise30__us100"], us, out)
    CC.set_leader_is(us)          # nq_btc_follow's leader = the in-sample us100 slice (never the default loader)
    del us
    gc.collect()
    for sym, keys in (("xauusd", ["donch4h_stop__xauusd", "orb_asia_2d_buf10__xauusd", "GOLD_FRI_PM__xauusd"]),
                      ("btcusd", ["brk72_24h_wd__btcusd", "F1_brk_ridge_filter__btcusd", "nq_btc_follow__btcusd"]),
                      ("ethusd", ["brk72_24h_wd__ethusd", "F1_brk_ridge_filter__ethusd"])):
        m1 = CC.load_fp_is(sym)
        run_market(sym, keys, m1, out)
        del m1
        gc.collect()
    # verdict: identical row by row except trades whose official exit lies in 2022 (open when the slice ends)
    verdict = {}
    for k, r in out.items():
        vo = r["fp"]["vs_official"]
        ok = (vo["n_mine"] == vo["n_official"] and vo["only_mine"] == 0 and vo["only_official"] == 0
              and len(vo["differing"]) == r["fp"]["official_exits_in_2022"]
              and all(d["exit_official"] >= "2022" for d in vo["differing"]))
        excl = sum(d["R_official"] for d in vo["differing"])
        verdict[k] = {"reproduced": bool(ok), "n": vo["n_official"], "totR_official": vo["totR_official"],
                      "totR_mine": vo["totR_mine"], "rows_differing": len(vo["differing"]),
                      "n_without_open_trade": vo["n_official"] - len(vo["differing"]),
                      "totR_official_without_open_trade": round(vo["totR_official"] - excl, 4),
                      "chain_files_ok": bool(r["fp"]["chain_file_equals_my_trades_minus_open_and_refused"]
                                             and r["stress"]["chain_file_equals_my_trades_minus_open_and_refused"])}
    allok = all(v["reproduced"] and v["chain_files_ok"] for v in verdict.values())
    V.dump({"rule": "official rows entry_time < 2022-01-01 vs my re-run on the in-sample FP frames (ts < 2022-01-01)",
            "all_reproduced": allok, "verdict": verdict, "detail": out}, os.path.join(V.OUT, "repro.json"))
    print("ALL REPRODUCED" if allok else "NOT REPRODUCED", flush=True)


if __name__ == "__main__":
    main()
