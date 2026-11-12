"""Addendum H, lens `entry`, step 0 -- FIRST CHECK (hard rule 2): reproduce the official in-sample trades of the ten
sleeves from my own in-sample slices, with the lab engine (no_overlap=True) AND with this lens's own path
(every leg alone + chain()), in FP costs and in x1.5 costs.

Output: results/r2/autopsy/entry/baseline.json, results/r2/autopsy/entry/baseline/<name>__<sym>.parquet
(my in-sample trades, FP costs, with fill bar and exit bar of each trade).
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (A_COLS_LEADER, COMMON_START, IS_END, ORDER, RES, arrays, build_orders, costs, frame_for,  # noqa
                    jdump, key, lab_orders, load_is, np, official, pd, signal_trades, sim_legs, simulate, stats,
                    window)

OUT = os.path.join(RES, "baseline")
os.makedirs(OUT, exist_ok=True)


def base_legs(o):
    legs = lab_orders(o)
    legs["sig"] = np.arange(len(legs), dtype=np.int64)
    legs["leg"] = 0
    legs["w"] = 1.0
    sigs = pd.DataFrame({"act": legs.entry_i.to_numpy(np.int64), "hold": np.full(len(legs), -1, np.int64),
                         "side": legs.side.to_numpy(np.int64)}, index=legs.sig.to_numpy())
    return legs, sigs


def compare(a, b, ka="R", kb="R"):
    """Trade sets a and b keyed on (entry_time, side): counts and R differences."""
    x = a[["entry_time", "side", ka]].rename(columns={ka: "Ra"}).merge(
        b[["entry_time", "side", kb]].rename(columns={kb: "Rb"}), on=["entry_time", "side"], how="outer",
        indicator=True)
    both = x[x._merge == "both"]
    d = (both.Ra - both.Rb).abs()
    return {"n_a": int(len(a)), "n_b": int(len(b)), "only_a": int((x._merge == "left_only").sum()),
            "only_b": int((x._merge == "right_only").sum()), "matched": int(len(both)),
            "R_identical_1e-9": int((d <= 1e-9).sum()), "max_abs_dR": float(d.max()) if len(d) else 0.0,
            "total_R_a": round(float(a[ka].sum()), 4), "total_R_b": round(float(b[kb].sum()), 4)}


def main():
    out = {"what": "first check: official in-sample trades (entry < 2022-01-01) against my own in-sample slices "
                   "(bar start < 2022-01-01 00:00 UTC); lab engine no_overlap=True and this lens's leg+chain path; "
                   "FP costs and x1.5", "sleeves": {}}
    cur = None
    m1 = m1s = A = As = leader = None
    for name, sym in ORDER:
        t0 = time.time()
        if sym != cur:
            m1 = m1s = A = As = leader = None
            m1 = load_is(sym)
            A = arrays(m1)
            m1s = frame_for(m1, True)
            As = arrays(m1s)
            leader = load_is("us100", cols=A_COLS_LEADER) if sym == "btcusd" else None
            cur = sym
        rec = {"frame_first_bar": str(m1.index[0]), "frame_last_bar": str(m1.index[-1]), "bars": int(len(m1))}
        for stress in (False, True):
            tag = "x1.5" if stress else "fp"
            fr, AA = (m1s, As) if stress else (m1, A)
            o = build_orders(name, sym, fr, leader)
            t_lab = simulate(fr, o, sym=sym, costs=costs(sym, stress), no_overlap=True)
            legs, sigs = base_legs(o)
            r = sim_legs(fr, AA, legs, sym, stress)
            tr, sg = signal_trades(sigs, legs, r)
            c = compare(t_lab, tr.reset_index())
            c["orders"] = int(len(o))
            c["lab_skipped"] = int(t_lab.attrs.get("skipped", -1))
            c["lab_nofill"] = int(t_lab.attrs.get("nofill", -1))
            taken_legs = r[sg.taken.reindex(legs.sig).to_numpy() & r.filled.to_numpy()]
            c["refused_3_spreads_taken"] = int(taken_legs.refused.sum())
            c["refused_3_spreads_every_signal"] = int(r[r.filled].refused.sum())
            sp = (taken_legs.risk / taken_legs.spread_fill)
            c["stop_in_spreads_min"] = round(float(sp.min()), 2) if len(sp) else None
            c["stop_in_spreads_median"] = round(float(sp.median()), 2) if len(sp) else None
            rec[f"lab_vs_mine_{tag}"] = c
            if not stress:
                off = official(name, sym)
                co = compare(t_lab, off)
                x = t_lab[["entry_time", "side", "R"]].merge(off[["entry_time", "side", "R", "exit_time"]],
                                                             on=["entry_time", "side"], suffixes=("_m", "_o"))
                straddle = x.exit_time >= IS_END
                dif = (x.R_m - x.R_o).abs() > 1e-9
                co["R_different_official_exit_after_2021"] = int((dif & straddle).sum())
                co["R_different_other"] = int((dif & ~straddle).sum())
                co["total_R_mine_excl_straddle"] = round(float(x.R_m[~straddle].sum()), 4)
                co["total_R_official_excl_straddle"] = round(float(x.R_o[~straddle].sum()), 4)
                rec["mine_vs_official_fp"] = co
                rec["reasons_fp"] = t_lab.reason.value_counts().to_dict()
                # keep my in-sample trades with fill / exit bars (for the anatomy)
                keep = t_lab.copy()
                keep["order_row"] = keep.index.to_numpy()
                ns = A["ns"]
                keep["fi"] = np.searchsorted(ns, keep.entry_time.dt.as_unit("ns").astype("int64").to_numpy())
                xns = (keep.exit_time.dt.as_unit("ns").astype("int64").to_numpy()
                       - np.where(keep.reason.to_numpy() == "time", 0, 60_000_000_000))
                keep["xi"] = np.searchsorted(ns, xns)
                keep = keep.reset_index(drop=True)
                keep.to_parquet(os.path.join(OUT, f"{name}__{sym}.parquet"))
                rec["is_all_fp"] = {k: v for k, v in stats(window(keep, "all"), years=None).items()}
                rec["is_common_fp"] = stats(window(keep, "common"))
                rec["pre_common_fp"] = stats(window(keep, "pre"), years=None)
            else:
                rec["is_common_x1.5"] = stats(window(t_lab, "common"))
        rec["seconds"] = round(time.time() - t0, 1)
        out["sleeves"][key(name, sym)] = rec
        lv, mo = rec["lab_vs_mine_fp"], rec["mine_vs_official_fp"]
        print(f"{name:20s} {sym:7s} lab=mine fp {lv['matched']}/{lv['n_a']} ident {lv['R_identical_1e-9']} "
              f"x1.5 {rec['lab_vs_mine_x1.5']['matched']}/{rec['lab_vs_mine_x1.5']['n_a']} "
              f"ident {rec['lab_vs_mine_x1.5']['R_identical_1e-9']} | official {mo['matched']}/{mo['n_b']} "
              f"only_mine {mo['only_a']} only_off {mo['only_b']} Rdiff_other {mo['R_different_other']} "
              f"straddle {mo['R_different_official_exit_after_2021']} | totR mine {mo['total_R_a']} "
              f"off {mo['total_R_b']} | refused {lv['refused_3_spreads_taken']} [{rec['seconds']}s]", flush=True)
    jdump(out, os.path.join(RES, "baseline.json"))


if __name__ == "__main__":
    main()
