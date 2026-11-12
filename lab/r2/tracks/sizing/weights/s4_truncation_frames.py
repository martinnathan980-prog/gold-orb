"""Lens `weights`, criterion (e), test T2 (PRICE FRAMES), as declared in declared.json. IN SAMPLE ONLY.

12 decision times T (4 per out-of-fold year 2019-2021, entries of the U10 fp book drawn with seed 5, never on the day
after US Thanksgiving, where GOLD_FRI_PM's early-close filter is applied after the fact). For each T, every market's
in-sample frame is cut right after the decision (bars starting before T + 2 min: the entry bar and one more bar, which
the rules need to emit an order whose entry bar is T), the ten sleeves are re-simulated on the cut frames (FP costs,
3-spread refusal; nq_btc_follow's leader = the us100 frame cut the same way), the book is rebuilt from those trades
only (a trade not closed strictly before T is unknown), and the stakes of every decision at or before T are
recomputed for every variant (U10 and U8_noF1) and compared with the full run, trade by trade on (sleeve, entry,
side). The known trades of the cut world must equal the full chains (same exit, same R).
Output: results/r2/sizing/weights/truncation_T2.json
"""
import gc
import json
import os
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common as C  # noqa: E402
import stakes as S  # noqa: E402
from goldlab import r2  # noqa: E402

N_PER_YEAR, SEED = 4, 5
PLAN = [("us100", ["ocm4", "noise30"]), ("xauusd", ["donch4h_stop", "orb_asia_2d_buf10", "GOLD_FRI_PM"]),
        ("btcusd", ["brk72_24h_wd", "F1_brk_ridge_filter", "nq_btc_follow"]), ("ethusd", ["brk72_24h_wd", "F1_brk_ridge_filter"])]


def pick_points(b):
    rng = np.random.default_rng(SEED)
    ny = pd.to_datetime(b.t_in.to_numpy(), utc=True).tz_convert("America/New_York")
    bad = ((ny.month == 11) & (ny.dayofweek == 4) & (ny.day >= 23) & (ny.day <= 29))
    T = []
    for y in C.OOF:
        idx = np.nonzero((b.year_in.to_numpy() == y) & ~np.asarray(bad))[0]
        T += [int(x) for x in b.t_in.to_numpy()[rng.choice(idx, N_PER_YEAR, replace=False)]]
    return sorted(T)


def main():
    decl = json.load(open(C.DECLARED))
    full_df = C.load_book("fp")
    full = S.book_frame(full_df)
    T_list = pick_points(full[full.k.isin(C.UNIVERSES["U10"])].reset_index(drop=True))
    cut_trades = {i: {} for i in range(len(T_list))}
    t0 = time.time()
    m = C.load_is("us100")
    leader_full = m[["bo", "ao", "bc", "ac"]].copy()
    del m
    gc.collect()
    for sym, names in PLAN:
        m1 = C.load_is(sym)
        for i, T in enumerate(T_list):
            end = pd.Timestamp(T, tz="UTC") + pd.Timedelta(minutes=2)
            cut = m1.iloc[: int(m1.index.searchsorted(end, side="left"))]
            lead = leader_full.iloc[: int(leader_full.index.searchsorted(end, side="left"))]
            for name in names:
                o = C.build_orders(name, cut, lead)
                t = C.simulate_filtered(cut, o, sym, C.mode_costs(sym, "fp"))
                t = t[t.entry_time < C.IS_END]
                cut_trades[i][C.key(name, sym)] = t[["side", "entry_time", "exit_time", "R"]].reset_index(drop=True)
            del cut, lead
        del m1
        r2.free()
        gc.collect()
        print(f"{sym} re-simulated at {len(T_list)} cuts [{time.time() - t0:.0f}s]", flush=True)
    res = {"what": __doc__.split("\n\n")[1], "points": []}
    full_st = {}
    for u in ("U10", "U8_noF1"):
        keys = C.UNIVERSES[u]
        b = full[full.k.isin(keys)].reset_index(drop=True)
        full_st[u] = (b, {v["id"]: S.stakes(b, keys, v) for v in decl["variants"]})
    for i, T in enumerate(T_list):
        rows = []
        for k, t in cut_trades[i].items():
            rows.append(pd.DataFrame({"k": k, "t_in": pd.DatetimeIndex(t.entry_time).as_unit("ns"),
                                      "t_out": pd.DatetimeIndex(t.exit_time).as_unit("ns"), "R": t.R.to_numpy(float),
                                      "side": t.side.to_numpy(np.int64)}))
        cb = pd.concat(rows, ignore_index=True)
        cb["ko"] = cb.k.map({k: j for j, k in enumerate(C.KEYS)}).astype(np.int64)
        cb = cb.sort_values(["t_in", "ko"], kind="stable").reset_index(drop=True)
        cb["wk_out"] = C.week_id(cb.t_out)
        cb["year_in"] = cb.t_in.dt.year.to_numpy()
        cbf = S.book_frame(cb)
        cbf = S.cut_book(cbf, T)            # trades entered after T dropped; not closed before T -> unknown
        row = {"T": str(pd.Timestamp(T, tz="UTC")), "trades_in_cut_world_at_or_before_T": int(len(cbf))}
        # the known trades of the cut world must equal the full chains
        fk = full[full.t_in.to_numpy() <= T]
        key_f = fk.k + "|" + fk.t_in.astype(str) + "|" + fk.side.astype(str)
        key_c = cbf.k + "|" + cbf.t_in.astype(str) + "|" + cbf.side.astype(str)
        row["trades_at_or_before_T_full"] = int(len(fk))
        row["matched"] = int(np.isin(key_c.to_numpy(), key_f.to_numpy()).sum())
        known = cbf.t_out.to_numpy() < S.INT_MAX
        fmap = pd.DataFrame({"t_out": fk.t_out.to_numpy(), "R": fk.R.to_numpy()}, index=key_f.to_numpy())
        kc = key_c.to_numpy()[known]
        same = (fmap.loc[kc, "t_out"].to_numpy() == cbf.t_out.to_numpy()[known]) & \
               (np.abs(fmap.loc[kc, "R"].to_numpy() - cbf.R.to_numpy()[known]) < 1e-9)
        row["known_trades"] = int(known.sum())
        row["known_trades_identical"] = int(same.sum())
        diffs = {}
        for u in ("U10", "U8_noF1"):
            keys = C.UNIVERSES[u]
            b, sts = full_st[u]
            cu = cbf[cbf.k.isin(keys)].reset_index(drop=True)
            kf = (b.k + "|" + b.t_in.astype(str) + "|" + b.side.astype(str)).to_numpy()
            pos_f = pd.Series(np.arange(len(b)), index=kf)
            kcu = (cu.k + "|" + cu.t_in.astype(str) + "|" + cu.side.astype(str)).to_numpy()
            pf = pos_f.loc[kcu].to_numpy()
            for v in decl["variants"]:
                sc = S.stakes(cu, keys, v)
                diffs[f"{u}|{v['id']}"] = int((sc != sts[v["id"]][pf]).sum())
        row["decisions_compared_per_variant"] = {u: int(cbf.k.isin(C.UNIVERSES[u]).sum()) for u in ("U10", "U8_noF1")}
        row["stakes_differing"] = {k: d for k, d in diffs.items() if d} or "none"
        row["pass"] = bool(row["matched"] == row["trades_at_or_before_T_full"] == row["trades_in_cut_world_at_or_before_T"]
                           and row["known_trades_identical"] == row["known_trades"] and all(d == 0 for d in diffs.values()))
        res["points"].append(row)
        print(json.dumps(row), flush=True)
    res["pass"] = bool(all(p["pass"] for p in res["points"]))
    C.jdump(res, os.path.join(C.OUT, "truncation_T2.json"))
    print("T2:", "PASS" if res["pass"] else "FAIL")


if __name__ == "__main__":
    main()
