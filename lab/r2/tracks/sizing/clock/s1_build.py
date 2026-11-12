"""Step 1 of the clock lens: FIRST CHECK (hard rule 2) and the base tables. IN SAMPLE ONLY.

One symbol at a time (us100, xauusd, btcusd, ethusd), each frame cut at 2022-01-01 while it is read.
For each of the ten sleeves:
  * rule 2: orders rebuilt from the in-sample slice, simulated with FP costs and one position at a time (no 3-spread
    refusal, as recalc.py), compared trade by trade with the official rows entered before 2022 (count of rows from
    a read of entry_time / exit_time only; results compared on the rows closed before 2022);
  * for fp and stress (x1.5): the signal table (every order of the rule, simulated alone: fill time, exit time,
    result, 3-spread refusal, still open at the end of the slice) and the reference chain (one position at a time,
    3-spread refusal, trades still open at the end of the slice dropped) = synthesis_B's P0 convention.
No band statistic is computed here.

    NUMBA_CACHE_DIR=/tmp/numba_clock PYTHONDONTWRITEBYTECODE=1 python3 s1_build.py
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


def check_official(rule, sym, m1, leader):
    o = C.build_orders(rule, m1, leader)
    t = C.simulate(m1, o, sym=sym, costs=C.mode_costs(sym, "fp"), no_overlap=True)
    t = t[t.entry_time < C.IS_END]
    n_off, n_off_2022 = C.official_count(rule, sym)
    off = C.official_closed(rule, sym)
    last_start = m1.index[-1]
    mine_open = t[t.exit_time >= last_start]            # still open at the end of the slice (no in-sample result)
    mine = t[t.exit_time < last_start]
    a = mine[["entry_time", "side", "R", "exit_time", "reason"]].reset_index(drop=True)
    b = off[["entry_time", "side", "R", "exit_time", "reason"]].reset_index(drop=True)
    m = a.merge(b, on=["entry_time", "side"], how="outer", suffixes=("_mine", "_off"), indicator=True)
    both = m[m["_merge"] == "both"]
    dif = both[((both.R_mine - both.R_off).abs() > 1e-9) | (both.exit_time_mine != both.exit_time_off)
               | (both.reason_mine != both.reason_off)]
    res = {"orders": int(len(o)), "n_mine_entered": int(len(t)), "n_official_entered": n_off,
           "n_mine_open_at_slice_end": int(len(mine_open)), "n_official_closed_in_2022": n_off_2022,
           "n_mine_closed": int(len(mine)), "n_official_closed": int(len(off)),
           "matched_closed": int(len(both)), "only_mine": int((m["_merge"] == "left_only").sum()),
           "only_official": int((m["_merge"] == "right_only").sum()), "rows_differing": int(len(dif)),
           "totR_mine_closed": round(float(mine.R.sum()), 4), "totR_official_closed": round(float(off.R.sum()), 4),
           "max_abs_R_diff": round(float((both.R_mine - both.R_off).abs().max()), 12) if len(both) else None,
           "open_trades_entry": [str(x) for x in mine_open.entry_time]}
    res["reproduced"] = bool(res["n_mine_entered"] == n_off and res["n_mine_open_at_slice_end"] == n_off_2022
                             and res["only_mine"] == 0 and res["only_official"] == 0 and res["rows_differing"] == 0
                             and abs(res["totR_mine_closed"] - res["totR_official_closed"]) < 1e-6)
    return res


def base_tables(rule, sym, m1, leader, mode):
    k = C.key(rule, sym)
    mk = C.mode_frame(m1, mode)
    o = C.build_orders(rule, mk, leader)
    costs = C.mode_costs(sym, mode)
    es = C.simulate(mk, o, sym=sym, costs=costs, no_overlap=False)
    last_start = mk.index[-1]
    sig = pd.DataFrame({"oid": o.oid.to_numpy(), "side": o.side.to_numpy(), "entry_i": o.entry_i.to_numpy(np.int64)})
    esi = es.set_index("oid")
    sig["filled"] = sig.oid.isin(esi.index).to_numpy()
    sig["fill_time"] = pd.to_datetime(esi.entry_time.reindex(sig.oid).to_numpy(), utc=True)
    sig["exit_time"] = pd.to_datetime(esi.exit_time.reindex(sig.oid).to_numpy(), utc=True)
    sig["R_alone"] = esi.R.reindex(sig.oid).to_numpy()
    ref = pd.Series(C.refused_mask(mk, es), index=es.oid.to_numpy())
    sig["refused"] = ref.reindex(sig.oid).fillna(False).to_numpy(bool)
    sig["boundary"] = (sig.exit_time >= last_start).fillna(False).to_numpy(bool)
    ch = C.simulate_filtered(mk, o, sym, costs)
    nref = ch.attrs["refused_3spreads"]
    n_all = len(ch)
    ch = C.drop_boundary(ch, mk)
    cols = ["oid", "side", "entry_time", "exit_time", "entry", "exit", "stop", "reason", "swap", "pnl", "risk", "R",
            "hold_min"]
    ch = ch[cols].reset_index(drop=True)
    sig["in_chain"] = sig.oid.isin(ch.oid).to_numpy()
    sig.to_parquet(os.path.join(C.BASE, f"{k}__{mode}__signals.parquet"))
    ch.to_parquet(os.path.join(C.BASE, f"{k}__{mode}__chain.parquet"))
    w = ch[(ch.entry_time >= C.COMMON_START)]
    info = {"orders": int(len(o)), "filled_alone": int(sig.filled.sum()), "refused_alone": int(sig.refused.sum()),
            "chain_refused_3spreads": int(nref), "chain_boundary_dropped": int(n_all - len(ch)),
            "chain_all": C.sstats(ch.R), "chain_2018_02_2021": C.sstats(w.R),
            "chain_2019_2021": C.sstats(ch[ch.entry_time >= pd.Timestamp("2019-01-01", tz="UTC")].R)}
    del mk
    return info


def main():
    info = {"what": "first check (rule 2) and base tables of the clock lens", "sleeves": {}, "frames": {}}
    by_sym = {}
    for name, sym in C.SLEEVES:
        by_sym.setdefault(sym, []).append(name)
    leader = None
    for sym in ("us100", "xauusd", "btcusd", "ethusd"):
        t0 = time.time()
        m1 = C.load_is(sym)
        info["frames"][sym] = {"bars": int(len(m1)), "first": str(m1.index[0]), "last": str(m1.index[-1])}
        print(f"== {sym}: {len(m1)} bars {m1.index[0]} .. {m1.index[-1]} [{time.time() - t0:.0f}s]", flush=True)
        if sym == "us100":
            leader = C.leader_series(m1)
        for rule in by_sym[sym]:
            t1 = time.time()
            k = C.key(rule, sym)
            chk = check_official(rule, sym, m1, leader)
            r = {"check": chk}
            for mode in C.MODES:
                r[mode] = base_tables(rule, sym, m1, leader, mode)
            r["sec"] = round(time.time() - t1, 1)
            info["sleeves"][k] = r
            print(f"{k:28s} entered {chk['n_mine_entered']}/{chk['n_official_entered']} open-at-end "
                  f"{chk['n_mine_open_at_slice_end']}/{chk['n_official_closed_in_2022']} closed R "
                  f"{chk['totR_mine_closed']}/{chk['totR_official_closed']} diff {chk['rows_differing']} "
                  f"{'OK' if chk['reproduced'] else 'MISMATCH'} | fp window {r['fp']['chain_2018_02_2021']} "
                  f"stress window n {r['stress']['chain_2018_02_2021']['n']} R {r['stress']['chain_2018_02_2021']['total']} "
                  f"refused {r['fp']['chain_refused_3spreads']}/{r['stress']['chain_refused_3spreads']} [{r['sec']}s]",
                  flush=True)
        del m1
        gc.collect()
        C.jdump(info, os.path.join(C.OUT, "s1_info.json"))
    # P0 of synthesis_B (window 2018-02-01 .. 2021-12-31, fp, plain sum)
    for mode in C.MODES:
        n = sum(info["sleeves"][k][mode]["chain_2018_02_2021"]["n"] for k in C.KEYS)
        tot = sum(info["sleeves"][k][mode]["chain_2018_02_2021"]["total"] for k in C.KEYS)
        info[f"P0_{mode}"] = {"n": n, "total_R": round(tot, 2)}
    info["all_reproduced"] = all(info["sleeves"][k]["check"]["reproduced"] for k in C.KEYS)
    C.jdump(info, os.path.join(C.OUT, "s1_info.json"))
    print("P0 fp", info["P0_fp"], "stress", info["P0_stress"], "all reproduced:", info["all_reproduced"])


if __name__ == "__main__":
    main()
