"""Lens `weights`, step 0 (task rule 2, FIRST CHECK): reproduce the official in-sample trades of the ten sleeves,
then build the reference chains (fp and stress) that every later step uses. IN SAMPLE ONLY.

One market at a time (us100 first: its slice is the leader of nq_btc_follow; then xauusd, btcusd, ethusd):
  * the frame is read with the row filter ts < 2022-01-01 (common.load_is);
  * rule 2: orders rebuilt by the frozen rule from that slice, simulated with FP costs and no_overlap (the call of
    r2/recalc.py:98, without any refusal), compared trade by trade with the official rows entered AND closed
    before 2022 (both filters in the read); the official rows entered before 2022 but closed in 2022 are counted
    (entry_time / exit_time only) and their result is not read;
  * reference chains: fp and costs x1.5 (orders rebuilt on the widened quotes, slippage x1.5), with the broker's
    3-spread minimum stop (no such trade expected in sample) and without the trades still open at the end of the
    slice. Saved to results/r2/sizing/weights/chains/<name>__<sym>__<mode>.parquet.
Output: results/r2/sizing/weights/repro.json

    NUMBA_CACHE_DIR=/tmp/numba_weights PYTHONDONTWRITEBYTECODE=1 python3 s0_repro.py
"""
import gc
import os
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common as C  # noqa: E402


def compare_official(t, off, n_off_entered, n_off_exit22):
    a = t[["entry_time", "side", "R", "exit_time", "reason"]].reset_index(drop=True)
    b = off[["entry_time", "side", "R", "exit_time", "reason"]].reset_index(drop=True)
    m = a.merge(b, on=["entry_time", "side"], how="outer", suffixes=("_mine", "_off"), indicator=True)
    both = m[m["_merge"] == "both"]
    dif = both[((both.R_mine - both.R_off).abs() > 1e-9) | (both.exit_time_mine != both.exit_time_off)
               | (both.reason_mine.astype(str) != both.reason_off.astype(str))]
    only_mine = m[m["_merge"] == "left_only"]
    # my trades that the official file closed in 2022 (entered before 2022): open at the end of my slice
    last_entries = only_mine[["entry_time", "side", "exit_time_mine", "reason_mine", "R_mine"]]
    return {"n_mine_all": int(len(t)), "n_official_entered_before_2022": int(n_off_entered),
            "n_official_entered_before_2022_closed_in_2022": int(n_off_exit22),
            "n_official_closed_before_2022": int(len(off)),
            "totR_official_closed_before_2022": round(float(off.R.sum()), 6),
            "matched_on_entry_and_side": int(len(both)), "only_mine": int(len(only_mine)),
            "only_official": int((m["_merge"] == "right_only").sum()),
            "matched_rows_differing": int(len(dif)),
            "max_abs_R_diff_matched": float((both.R_mine - both.R_off).abs().max()) if len(both) else None,
            "totR_mine_on_matched": round(float(both.R_mine.sum()), 6),
            "mine_not_in_official_closed": [{"entry_time": str(r.entry_time), "side": int(r.side),
                                             "my_exit": str(r.exit_time_mine), "my_reason": str(r.reason_mine)}
                                            for r in last_entries.itertuples()]}


def run_sleeve(rule, sym, m1, leader, info):
    k = C.key(rule, sym)
    t0 = time.time()
    o = C.build_orders(rule, m1, leader)
    t_chk = C.simulate(m1, o, sym=sym, costs=C.mode_costs(sym, "fp"), no_overlap=True)
    n_ent, n_x22 = C.official_count(rule, sym)
    off = C.official_closed(rule, sym)
    cmp = compare_official(t_chk, off, n_ent, n_x22)
    cmp["orders_fp"] = int(len(o))
    # reproduced: every official row closed before 2022 found with the same exit, reason and R; my only extra
    # trades are the ones the official file closed in 2022 (entered before 2022, open at the end of my slice)
    cmp["reproduced"] = bool(cmp["only_official"] == 0 and cmp["matched_rows_differing"] == 0
                             and cmp["matched_on_entry_and_side"] == cmp["n_official_closed_before_2022"]
                             and cmp["only_mine"] == cmp["n_official_entered_before_2022_closed_in_2022"]
                             and cmp["n_mine_all"] == cmp["n_official_entered_before_2022"])
    rows = {}
    for mode in C.MODES:
        mk = C.mode_frame(m1, mode)
        oo = o if mode == "fp" else C.build_orders(rule, mk, leader)
        t = C.simulate_filtered(mk, oo, sym, C.mode_costs(sym, mode))
        nref, n_all = t.attrs["refused_3spreads"], len(t)
        t = C.drop_boundary(t, mk)
        t = t[[c for c in C.CHAIN_COLS if c in t.columns]].reset_index(drop=True)
        t.to_parquet(C.chain_path(k, mode))
        w = t[t.entry_time >= C.COMMON_START]
        rows[mode] = {"orders": int(len(oo)), "refused_3spreads": int(nref), "boundary_dropped": int(n_all - len(t)),
                      "all": C.sstats(t.R), "first_entry": str(t.entry_time.min()),
                      "window_2018_02_2021_12": C.sstats(w.R)}
        if mode != "fp":
            del mk
    # the fp chain must equal the rule-2 run minus the boundary trades (no refusal in sample)
    tf = C.load_chain(k, "fp")
    chk = t_chk[t_chk.exit_time < m1.index[-1]].reset_index(drop=True)
    cmp["fp_chain_equals_rule2_run_minus_boundary"] = bool(
        len(tf) == len(chk) and np.allclose(tf.R.to_numpy(), chk.R.to_numpy(), rtol=0, atol=1e-12)
        and (tf.entry_time.to_numpy() == chk.entry_time.to_numpy()).all())
    cmp["chains"] = rows
    cmp["sec"] = round(time.time() - t0, 1)
    info[k] = cmp
    print(f"{rule:22s} {sym:7s} official entered<2022 {n_ent} (closed 2022: {n_x22}) | mine {cmp['n_mine_all']} | "
          f"matched {cmp['matched_on_entry_and_side']} differing {cmp['matched_rows_differing']} | "
          f"R official(closed<2022) {cmp['totR_official_closed_before_2022']:.3f} mine(matched) "
          f"{cmp['totR_mine_on_matched']:.3f} | {'OK' if cmp['reproduced'] else 'MISMATCH'} | "
          f"fp window {rows['fp']['window_2018_02_2021_12']['n']} {rows['fp']['window_2018_02_2021_12']['total']} "
          f"stress window {rows['stress']['window_2018_02_2021_12']['n']} {rows['stress']['window_2018_02_2021_12']['total']} "
          f"refused {rows['fp']['refused_3spreads']}/{rows['stress']['refused_3spreads']} [{cmp['sec']}s]", flush=True)


def main():
    info = {}
    by_sym = {}
    for name, sym in C.SLEEVES:
        by_sym.setdefault(sym, []).append(name)
    leader = None
    for sym in ("us100", "xauusd", "btcusd", "ethusd"):
        t0 = time.time()
        m1 = C.load_is(sym)
        print(f"== {sym}: {len(m1)} bars {m1.index[0]} .. {m1.index[-1]} [{time.time() - t0:.0f}s]", flush=True)
        info[f"frame__{sym}"] = {"bars": int(len(m1)), "first": str(m1.index[0]), "last": str(m1.index[-1])}
        if sym == "us100":
            leader = m1[["bo", "ao", "bc", "ac"]].copy()
        for name in by_sym[sym]:
            run_sleeve(name, sym, m1, leader, info)
            gc.collect()
        del m1
        r2_free()
        gc.collect()
        C.jdump(info, os.path.join(C.OUT, "repro.json"))
    # portfolio check against synthesis_B's P0 (entries 2018-02-01 .. 2021-12-31, fp): 5,205 trades, +788.59 R
    for mode in C.MODES:
        b = C.load_book(mode)
        w = b[b.t_in >= C.COMMON_START]
        info[f"P0_{mode}"] = {"n": int(len(w)), "total_R": round(float(w.R.sum()), 3),
                              "by_sleeve": {k: {"n": int((w.k == k).sum()), "total_R": round(float(w.R[w.k == k].sum()), 3)}
                                            for k in C.KEYS}}
        print(mode, "P0 window", info[f"P0_{mode}"]["n"], info[f"P0_{mode}"]["total_R"], flush=True)
    info["all_ten_reproduced"] = bool(all(info[C.key(n, s)]["reproduced"] for n, s in C.SLEEVES))
    info["P0_matches_synthesis_B"] = bool(info["P0_fp"]["n"] == 5205 and abs(info["P0_fp"]["total_R"] - 788.59) < 0.01)
    C.jdump(info, os.path.join(C.OUT, "repro.json"))
    print("ALL REPRODUCED" if info["all_ten_reproduced"] else "NOT REPRODUCED", "| P0 =", info["P0_matches_synthesis_B"])


def r2_free():
    from goldlab import r2
    r2.free()


if __name__ == "__main__":
    main()
