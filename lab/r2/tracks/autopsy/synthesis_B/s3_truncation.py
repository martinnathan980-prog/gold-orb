"""synthesis_B step 3: truncation tests T1 (K1 riskbp skip) and T2 (K2 / K3 orb on crypto) of declared.json.
IN SAMPLE ONLY.

T1: for 30 brk72_24h_wd ethusd signals of 2019-2021 (15 skipped and 15 kept: the 8 nearest the threshold on each side
    plus 7 random, seed 7), the FP frame is cut to the bars that START before the decision time D, and two flat
    provisional bars stamped D and D + 1 minute are appended (the rule needs a bar at D for its market order, and the
    FP-hours wrapper drops an order whose exit bar is not after its entry bar). On that
    frame the orders, every training signal's own result, the fold threshold T(Y) and the signal's riskbp are
    recomputed: stop_dist, P, riskbp, T(Y) and the skip decision must be identical to the full-slice run.
T2: for 20 trades per instrument (seed 7) of orb_asia_2d_buf10 on ethusd and btcusd, the FP frame is cut right after
    the touch (fill) bar and 3 flat provisional bars are appended; the order of that session (entry bar time, side,
    level, stop) must be identical.

    NUMBA_CACHE_DIR=/tmp/numba_synthesis_B PYTHONDONTWRITEBYTECODE=1 python3 s3_truncation.py
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
import s1_run as S1  # noqa: E402


def provisional(m1, start, k):
    """k flat bars at start, start+1min, ... priced at the last close of m1 (no information from the future)."""
    last = m1.iloc[-1]
    idx = pd.DatetimeIndex([start + pd.Timedelta(minutes=i) for i in range(k)], name=m1.index.name)
    row = {c: (last["bc"] if c.startswith("b") else last["ac"]) for c in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac")}
    add = pd.DataFrame([row] * k, index=idx).astype("float64")
    return pd.concat([m1, add])


def t1(m1, sym="ethusd"):
    o, s = S1.signal_table(m1, sym, "fp")
    skip, folds, _ = S1.walk_forward(s)
    s = s.assign(skip=skip)
    oof = s[(s.year >= 2019) & (s.year <= 2021)].copy()
    oof["thr"] = oof.year.map({y: f["q_hi"] for y, f in folds.items()})
    oof["dist"] = (oof.riskbp - oof.thr).abs()
    rng = np.random.default_rng(7)
    pick = []
    for flag in (True, False):
        g = oof[oof.skip == flag]
        near = g.nsmallest(8, "dist").oid.tolist()
        rest = g[~g.oid.isin(near)]
        pick += near + rest.oid.to_numpy()[rng.choice(len(rest), 7, replace=False)].tolist()
    rows = []
    for oid in pick:
        r = s.set_index("oid").loc[oid]
        D = r.t_dec
        cut = m1[m1.index < D]
        mk = provisional(cut, D, 2)
        oc, sc = S1.signal_table(mk, sym, "fp")
        _, folds_c, _ = S1.walk_forward(sc)
        mine = sc[sc.t_dec == D]
        y = int(D.year)
        ok_order = len(mine) == 1
        row = {"oid": int(oid), "D": str(D), "skip_full": bool(r.skip), "found": ok_order}
        if ok_order:
            mm = mine.iloc[0]
            thr_c = folds_c[y]["q_hi"] if y in folds_c else None
            skip_c = bool(thr_c is not None and folds_c[y]["skip"] == "hi" and mm.riskbp >= thr_c)
            row.update(side_same=bool(mm.side == r.side), d_stop=float(abs(mm.stop_dist - r.stop_dist)),
                       d_P=float(abs(mm.P - r.P)), d_riskbp=float(abs(mm.riskbp - r.riskbp)),
                       d_thr=float(abs(thr_c - folds[y]["q_hi"])) if thr_c is not None else None,
                       skip_cut=skip_c, same_decision=bool(skip_c == bool(r.skip)))
        rows.append(row)
    ok = [x for x in rows if x.get("found")]
    return {"n": len(rows), "found": len(ok), "same_decision": int(sum(x["same_decision"] for x in ok)),
            "side_same": int(sum(x["side_same"] for x in ok)),
            "max_d_stop": max(x["d_stop"] for x in ok), "max_d_P": max(x["d_P"] for x in ok),
            "max_d_riskbp": max(x["d_riskbp"] for x in ok),
            "max_d_thr": max(x["d_thr"] for x in ok if x["d_thr"] is not None),
            "skipped_in_test": int(sum(x["skip_full"] for x in rows)), "rows": rows}


def t2(m1, sym):
    o = C.build_orders("orb_asia_2d_buf10", m1)
    o["oid"] = np.arange(len(o), dtype=np.int64)
    t = C.load_trades(f"new__orb_asia_2d_buf10__{sym}__fp")
    rng = np.random.default_rng(7)
    sel = t.iloc[np.sort(rng.choice(len(t), 20, replace=False))]
    rows = []
    for tr in sel.itertuples():
        ref = o.set_index("oid").loc[tr.oid]
        fill_t = tr.entry_time
        cut = m1[m1.index <= fill_t]
        mk = provisional(cut, fill_t + pd.Timedelta(minutes=1), 3)
        oc = C.build_orders("orb_asia_2d_buf10", mk)
        same_day = oc[pd.to_datetime(oc["date"]) == pd.to_datetime(ref["date"])]
        row = {"oid": int(tr.oid), "fill": str(fill_t), "found": len(same_day) == 1}
        if len(same_day) == 1:
            c = same_day.iloc[0]
            row.update(entry_bar_same=bool(mk.index[int(c.entry_i)] == m1.index[int(ref.entry_i)]),
                       side_same=bool(c.side == ref.side), d_level=float(abs(c.level - ref.level)),
                       d_stop=float(abs(c.stop - ref.stop)))
            row["identical"] = bool(row["entry_bar_same"] and row["side_same"] and row["d_level"] == 0 and row["d_stop"] == 0)
        rows.append(row)
    ok = [x for x in rows if x.get("found")]
    return {"n": len(rows), "found": len(ok), "identical": int(sum(x["identical"] for x in ok)),
            "max_d_level": max(x["d_level"] for x in ok), "max_d_stop": max(x["d_stop"] for x in ok), "rows": rows}


def main():
    res = {}
    for sym in ("ethusd", "btcusd"):
        t0 = time.time()
        m1 = C.load_is(sym)
        if sym == "ethusd":
            res["T1_riskbp_ethusd"] = t1(m1)
            r = res["T1_riskbp_ethusd"]
            print("T1", {k: r[k] for k in r if k != "rows"}, f"[{time.time() - t0:.0f}s]", flush=True)
        res[f"T2_orb_{sym}"] = t2(m1, sym)
        r = res[f"T2_orb_{sym}"]
        print("T2", sym, {k: r[k] for k in r if k != "rows"}, f"[{time.time() - t0:.0f}s]", flush=True)
        del m1
        gc.collect()
    C.jdump(res, os.path.join(C.OUT, "s3_truncation.json"))


if __name__ == "__main__":
    main()
