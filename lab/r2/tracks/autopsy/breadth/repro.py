"""FIRST CHECK (task rule 2): reproduce the official in-sample trades of the ten sleeves from my own in-sample slices
with the harness used for the new pairs (common.run_rule), before any new pair is simulated.

    NUMBA_CACHE_DIR=/tmp/... PYTHONDONTWRITEBYTECODE=1 python3 repro.py

Compared with results/r2/recalc/trades/<name>__<sym>.parquet rows with entry_time < 2022-01-01: number of trades,
total R, and trade by trade (entry time, side, R).  The official files come from a run on the whole 2013-2025
frame, so a trade entered in 2021 and closed in 2022 cannot be identical on a slice that ends on 2021-12-31
(it is closed at the last in-sample bar): such boundary trades are listed, not hidden.
Also counted: official trades the broker would refuse (stop closer than 3 spreads of the fill bar).
Output: results/r2/autopsy/breadth/repro.json
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common as C  # noqa: E402


def compare(mine, off):
    a = mine[["entry_time", "side", "R", "exit_time"]].reset_index(drop=True)
    b = off[["entry_time", "side", "R", "exit_time"]].reset_index(drop=True)
    m = a.merge(b, on=["entry_time", "side"], how="outer", suffixes=("_mine", "_off"), indicator=True)
    both = m[m["_merge"] == "both"]
    dif = both[(both.R_mine - both.R_off).abs() > 1e-6]
    return {"matched": int(len(both)), "only_mine": int((m["_merge"] == "left_only").sum()),
            "only_official": int((m["_merge"] == "right_only").sum()), "R_differs": int(len(dif)),
            "max_abs_R_diff": round(float((both.R_mine - both.R_off).abs().max()), 9) if len(both) else None,
            "differing_rows": [{"entry_time": str(r.entry_time), "side": int(r.side), "R_mine": round(float(r.R_mine), 4),
                                "R_off": round(float(r.R_off), 4), "exit_mine": str(r.exit_time_mine),
                                "exit_off": str(r.exit_time_off)} for r in dif.head(10).itertuples()]}


def main():
    out = {}
    by_sym = {}
    for name, sym in C.SLEEVES:
        by_sym.setdefault(sym, []).append(name)
    leader = C.leader_series(C.load_is("us100"))
    for sym in ["us100", "btcusd", "ethusd", "xauusd"]:
        m1 = C.load_is(sym)
        assert m1.index.max() < C.IS_END
        for name in by_sym[sym]:
            t, o, info = C.run_rule(name, sym, m1, "fp", leader=leader, min_spreads=None)
            off = C.official(name, sym)
            cmp = compare(t, off)
            fi = m1.index.searchsorted(off.entry_time)
            spr = (m1["ao"].to_numpy() - m1["bo"].to_numpy())[np.clip(fi, 0, len(m1) - 1)]
            refuse = int(((off.risk.to_numpy() < 3 * spr) | (off.reason.to_numpy() == "gap")).sum())
            row = {"n_mine": int(len(t)), "n_official": int(len(off)), "totR_mine": round(float(t.R.sum()), 3),
                   "totR_official": round(float(off.R.sum()), 3),
                   "official_exits_after_2021": int((off.exit_time >= C.IS_END).sum()),
                   "official_R_of_those": round(float(off.R[off.exit_time >= C.IS_END].sum()), 3),
                   "compare": cmp, "orders": info["orders"],
                   "official_refused_by_3spread_rule": refuse,
                   "common_window": {"n_mine": int(len(C.window(t))), "n_official": int(len(C.window(off))),
                                     "totR_mine": round(float(C.window(t).R.sum()), 3),
                                     "totR_official": round(float(C.window(off).R.sum()), 3)}}
            row["reproduced"] = bool(row["n_mine"] == row["n_official"] and cmp["only_mine"] == 0
                                     and cmp["only_official"] == 0 and cmp["R_differs"] <= row["official_exits_after_2021"])
            out[f"{name}:{sym}"] = row
            print(f"{name:22s} {sym:7s} n {row['n_mine']:5d}/{row['n_official']:5d} totR {row['totR_mine']:9.3f}/"
                  f"{row['totR_official']:9.3f} | matched {cmp['matched']} only_mine {cmp['only_mine']} only_off "
                  f"{cmp['only_official']} Rdiff {cmp['R_differs']} (boundary {row['official_exits_after_2021']}) "
                  f"| refused@3spr {refuse} | {'OK' if row['reproduced'] else 'MISMATCH'}", flush=True)
        del m1
    C.jdump(out, os.path.join(C.RES, "repro.json"))


if __name__ == "__main__":
    main()
