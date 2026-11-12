"""Step 0 (hard rule 2): reproduce the official in-sample trades of the ten sleeves from my own in-sample slices.

For each sleeve: frame read with bar start < 2022-01-01 (nothing later is ever in memory), orders of the frozen rule
built on that slice, lab engine with FP costs and one position per sleeve; compared with the official trades file
read with entry_time < 2022-01-01 in the same statement.  Also: how many trades have a stop closer than 3 spreads
at the fill (the broker would refuse them).

Output: results/r2/autopsy/path/baseline.json, results/r2/autopsy/path/baseline/<name>__<sym>.parquet
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


def compare(mine, off):
    a = mine[["entry_time", "side", "R", "exit_time", "reason"]].reset_index(drop=True)
    b = off[["entry_time", "side", "R", "exit_time", "reason"]].reset_index(drop=True)
    m = a.merge(b, on=["entry_time", "side"], how="outer", suffixes=("_mine", "_off"), indicator=True)
    both = m[m["_merge"] == "both"]
    straddle = both["exit_time_off"] >= C.IS_END                      # official exit after the in-sample end
    dR = (both["R_mine"] - both["R_off"]).abs()
    same = dR < 1e-9
    return {
        "n_mine": int(len(a)), "n_official": int(len(b)),
        "only_mine": int((m["_merge"] == "left_only").sum()), "only_official": int((m["_merge"] == "right_only").sum()),
        "matched": int(len(both)), "R_identical": int(same.sum()),
        "R_different": int((~same).sum()),
        "R_different_and_official_exit_after_2021": int((~same & straddle).sum()),
        "R_different_other": int((~same & ~straddle).sum()),
        "max_abs_dR_other": float(dR[~straddle].max()) if (~straddle).any() else 0.0,
        "total_R_mine": round(float(a.R.sum()), 4), "total_R_official": round(float(b.R.sum()), 4),
        "total_R_mine_excl_straddle": round(float(both.loc[~straddle, "R_mine"].sum()), 4),
        "total_R_official_excl_straddle": round(float(both.loc[~straddle, "R_off"].sum()), 4),
    }


def main():
    os.makedirs(os.path.join(C.RES, "baseline"), exist_ok=True)
    out = {"what": "official in-sample trades (entry < 2022-01-01) against my own in-sample slices; FP costs; "
                   "one position per sleeve", "sleeves": {}}
    cur = None
    m1 = leader = None
    for name, sym in C.ORDER:
        t0 = time.time()
        if sym != cur:
            m1 = None
            m1 = C.load_is(sym)
            leader = C.load_is("us100", cols=["bo", "ao", "bc", "ac"]) if sym == "btcusd" else None
            cur = sym
        o = C.build_orders(name, sym, m1, leader)
        t = C.sim(m1, o, sym, stress=False, no_overlap=True)
        off = C.official(name, sym)
        cmp_ = compare(t, off)
        fi, xi = C.fill_exit_bars(m1, t)
        spread = m1["ao"].to_numpy()[fi] - m1["bo"].to_numpy()[fi]
        too_close = int((t.risk.to_numpy() < 3 * spread).sum())
        ratio = t.risk.to_numpy() / spread
        cmp_.update({
            "frame_first_bar": str(m1.index[0]), "frame_last_bar": str(m1.index[-1]),
            "orders": int(len(o)), "skipped": int(t.attrs["skipped"]), "nofill": int(t.attrs["nofill"]),
            "stops_closer_than_3_spreads": too_close,
            "stop_in_spreads_min": round(float(ratio.min()), 2), "stop_in_spreads_median": round(float(np.median(ratio)), 1),
            "reasons": t.reason.value_counts().to_dict(),
            "n_common_window": int(((t.entry_time >= C.COMMON_START)).sum()),
            "total_R_common_window": round(float(t.loc[t.entry_time >= C.COMMON_START, "R"].sum()), 2),
            "seconds": round(time.time() - t0, 1),
        })
        out["sleeves"][f"{name}:{sym}"] = cmp_
        t.to_parquet(os.path.join(C.RES, "baseline", f"{name}__{sym}.parquet"))
        print(f"{name:20s} {sym:7s} mine {cmp_['n_mine']:5d} off {cmp_['n_official']:5d} | totR mine "
              f"{cmp_['total_R_mine']:9.3f} off {cmp_['total_R_official']:9.3f} | R diff {cmp_['R_different']} "
              f"(straddle {cmp_['R_different_and_official_exit_after_2021']}) | <3spr {too_close} "
              f"| min stop {cmp_['stop_in_spreads_min']} spreads | {cmp_['seconds']}s", flush=True)
    C.jdump(out, os.path.join(C.RES, "baseline.json"))


if __name__ == "__main__":
    main()
