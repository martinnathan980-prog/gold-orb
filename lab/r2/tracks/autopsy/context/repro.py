"""FIRST CHECK (Addendum H, hard rule 2): reproduce the official in-sample trades of the ten sleeves from in-sample
slices only. Writes results/r2/autopsy/context/baseline_repro.json and trades_is/<name>__<sym>.parquet (my own
in-sample chain, FP costs, one position per sleeve), which every later step uses as the baseline."""
import gc
import os
import time

import numpy as np
import pandas as pd

import common as C

TR_DIR = os.path.join(C.OUT, "trades_is")
os.makedirs(TR_DIR, exist_ok=True)
COLS = ["side", "entry_time", "exit_time", "entry", "exit", "stop", "reason", "swap", "pnl", "risk", "R", "ret",
        "hold_min"]


def compare(mine, off):
    """Row-by-row comparison on (entry_time, side)."""
    a = mine[COLS].reset_index(drop=True)
    b = off[COLS].reset_index(drop=True)
    out = {"n_official": int(len(b)), "n_mine": int(len(a)),
           "R_official": round(float(b.R.sum()), 4), "R_mine": round(float(a.R.sum()), 4)}
    m = a.merge(b, on=["entry_time", "side"], how="outer", suffixes=("_m", "_o"), indicator=True)
    out["only_mine"] = int((m._merge == "left_only").sum())
    out["only_official"] = int((m._merge == "right_only").sum())
    both = m[m._merge == "both"]
    dR = (both.R_m - both.R_o).abs()
    same = (dR < 1e-9) & (both.exit_time_m == both.exit_time_o) & (both.reason_m == both.reason_o)
    out["matched"] = int(len(both))
    out["identical"] = int(same.sum())
    out["max_abs_dR"] = round(float(dR.max()), 12) if len(both) else 0.0
    diff = both[~same]
    # differing rows: only allowed at the end of the in-sample frame (a trade still open on 2021-12-31 is closed
    # at the last bar of the slice); report how many, whether they are boundary trades, and the R difference
    out["n_differing"] = int(len(diff))
    out["differing_are_boundary"] = bool(((diff.reason_m == "eod") | (diff.exit_time_m >= C.IS_END - pd.Timedelta(days=1))).all()) if len(diff) else True
    out["sum_dR_differing"] = round(float((diff.R_m - diff.R_o).sum()), 4) if len(diff) else 0.0
    out["R_mine_minus_official"] = round(out["R_mine"] - out["R_official"], 4)
    return out


def run_one(k, m1, res):
    t0 = time.time()
    track, name, sym, mo, params = C.registry()[k]
    o = C.build_orders(k, m1)
    t = C.sim(k, m1, o, "fp", True)
    t = t[t.entry_time < C.IS_END]
    off = C.load_official(name, sym)
    r = compare(t, off)
    r["orders"] = int(len(o))
    r["skipped_by_no_overlap"] = int(t.attrs.get("skipped", -1))
    r["nofill"] = int(t.attrs.get("nofill", -1))
    r["first_entry"] = str(t.entry_time.min())
    r["last_entry"] = str(t.entry_time.max())
    r["frame_rows"] = int(len(m1))
    r["frame_first"] = str(m1.index[0])
    r["frame_last"] = str(m1.index[-1])
    r["sec"] = round(time.time() - t0, 1)
    out = t.copy()
    out["oid"] = out.index.to_numpy()
    out.reset_index(drop=True).to_parquet(os.path.join(TR_DIR, f"{k}.parquet"))
    res[k] = r
    print(k, {q: r[q] for q in ("n_official", "n_mine", "R_official", "R_mine", "identical", "n_differing",
                                  "sum_dR_differing", "only_mine", "only_official")}, flush=True)


def main():
    res = {}
    us = C.load_fp_is("us100")
    for k in ("ocm4__us100", "noise30__us100"):
        run_one(k, us, res)
    C.set_leader_is(us)                     # in-sample leader for nq_btc_follow (arrays copied)
    del us
    gc.collect()
    xau = C.load_fp_is("xauusd")
    for k in ("donch4h_stop__xauusd", "orb_asia_2d_buf10__xauusd", "GOLD_FRI_PM__xauusd"):
        run_one(k, xau, res)
    del xau
    gc.collect()
    btc = C.load_fp_is("btcusd")
    for k in ("brk72_24h_wd__btcusd", "F1_brk_ridge_filter__btcusd", "nq_btc_follow__btcusd"):
        run_one(k, btc, res)
    del btc
    gc.collect()
    eth = C.load_fp_is("ethusd")
    for k in ("brk72_24h_wd__ethusd", "F1_brk_ridge_filter__ethusd"):
        run_one(k, eth, res)
    del eth
    ok = {k: (v["only_mine"] == 0 and v["only_official"] == 0 and v["differing_are_boundary"]) for k, v in res.items()}
    C.dump({"what": "reproduction of the official in-sample trades (entry < 2022-01-01) from in-sample slices "
                    "(price rows ts < 2022-01-01 only), FP costs, no_overlap=True",
            "pass": ok, "sleeves": res}, os.path.join(C.OUT, "baseline_repro.json"))
    print("PASS" if all(ok.values()) else "FAIL", ok)


if __name__ == "__main__":
    main()
