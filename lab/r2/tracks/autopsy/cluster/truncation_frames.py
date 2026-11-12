"""Lens `cluster`: literal truncation test with PRICE FRAMES (rule 3 of the task).

For a decision at time T (the entry minute of a trade), every market's in-sample frame is cut right after the
decision: bars starting before T + 2 min are kept (the entry bar T and one more bar, which the rules need to emit an
order whose entry bar is T; see the brain maps). All ten sleeves are re-simulated on the cut frames (FP costs; the
nq_btc_follow leader is the us100 frame cut the same way), the book is rebuilt from those trades only, the engine is
re-run, and every decision for a trade entered at or before T is compared with the full in-sample run.
Trades still open at the cut get a fake end (eod / time at the last bar) whose exit time is after T: they cannot
enter a decision at T. One variant of each family is tested, plus the reference.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import book as B  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from goldlab import r2  # noqa: E402

sys.path.insert(0, os.path.join(C.LAB, "r2"))
import recalc  # noqa: E402
import repro  # noqa: E402

TESTED = ["A3", "A5", "B1", "C2", "D5", "D7", "E2", "F2", "G2"]


def pick_points(stk, decl_codes):
    """One decision per tested variant where its guard changed the stake against the reference, plus 2 random ones;
    never on the day after US Thanksgiving (GOLD_FRI_PM's known after-the-fact early-close filter)."""
    rng = np.random.default_rng(11)
    sel = (stk.t_in >= C.COMMON_START).to_numpy()
    ny = stk.t_in.dt.tz_convert("America/New_York")
    bad = ((ny.dt.month == 11) & (ny.dt.dayofweek == 4) & (ny.dt.day >= 23) & (ny.dt.day <= 29)).to_numpy()
    ok = sel & ~bad
    pts = []
    for v in TESTED:
        act = np.nonzero(ok & (stk[v].to_numpy() != stk["ref"].to_numpy()))[0]
        if len(act):
            pts.append(int(rng.choice(act)))
    pts += [int(x) for x in rng.choice(np.nonzero(ok)[0], size=2, replace=False)]
    return sorted(set(pts))


def main():
    decl = {v["id"]: v for v in json.load(open(os.path.join(C.OUT, "declared.json")))["variants"]}
    stk = pd.read_parquet(os.path.join(C.OUT, "stakes_fp.parquet"))
    full = B.build("fp")
    assert len(full) == len(stk) and (full.sleeve.to_numpy() == stk.sleeve.to_numpy()).all()
    pts = pick_points(stk, decl)
    T = [stk.t_in.iloc[i] for i in pts]
    reg = repro.registry()
    cut_trades = {k: {} for k in range(len(T))}
    m = C.load_is_frame("us100")
    leader_full = m[["bo", "ao", "bc", "ac"]].copy()
    del m
    plan = [("us100", ["noise30", "ocm4"]), ("btcusd", ["brk72_24h_wd", "nq_btc_follow", "F1_brk_ridge_filter"]),
            ("ethusd", ["brk72_24h_wd", "F1_brk_ridge_filter"]),
            ("xauusd", ["GOLD_FRI_PM", "donch4h_stop", "orb_asia_2d_buf10"])]
    t0 = time.time()
    for sym, names in plan:
        m1 = C.load_is_frame(sym)
        spread = (m1["ao"] - m1["bo"]).to_numpy()
        for k, t in enumerate(T):
            end = t + pd.Timedelta(minutes=2)
            cut = m1.iloc[: int(m1.index.searchsorted(end, side="left"))]
            lead = leader_full.iloc[: int(leader_full.index.searchsorted(end, side="left"))]
            for name in names:
                track, mo, params = reg[(name, sym)]
                C.clear_rule_caches()
                if name == "nq_btc_follow":
                    sys.modules["r2_leadlag_strategy"].set_leader("us100", lead)
                tr = r2.run(sym, mo, params, "fp", True, cut)
                fi = cut.index.get_indexer(tr.entry_time)
                tr = tr[repro.KEEP].copy().reset_index(drop=True)
                tr["spread_fill"] = spread[fi]
                tr["stop_spreads"] = tr.risk.to_numpy() / tr.spread_fill.to_numpy()
                cut_trades[k][(name, sym)] = tr
        del m1
        r2.free()
        print(f"{sym} done [{time.time() - t0:.0f}s]", flush=True)
    res = {"points": [], "variants_tested": TESTED}
    a_full = B.arrays(full)
    full_m = {v: stk[v].to_numpy() for v in TESTED}
    full_m["ref"] = stk["ref"].to_numpy()
    for k, t in enumerate(T):
        d = build_from(cut_trades[k])
        a = B.arrays(d)
        row = {"T": str(t), "target_sleeve": stk.sleeve.iloc[pts[k]], "trades_in_cut_book": int(len(d))}
        # match trades entered at or before T between the cut book and the full book
        key = lambda x: x.sleeve.astype(str) + "|" + x.t_in.astype("int64").astype(str) + "|" + x.side.astype(str)
        kf = key(full)[full.t_in <= t]
        kc = key(d)[d.t_in <= t]
        common = pd.Index(kf.to_numpy()).intersection(pd.Index(kc.to_numpy()))
        row["trades_at_or_before_T_full"] = int(len(kf))
        row["trades_at_or_before_T_cut"] = int(len(kc))
        row["matched"] = int(len(common))
        pos_f = pd.Series(kf.index, index=kf.to_numpy()).loc[common].to_numpy()
        pos_c = pd.Series(kc.index, index=kc.to_numpy()).loc[common].to_numpy()
        diffs = {}
        for v in ["ref"] + TESTED:
            code, p1, p2 = (0, 0.0, 0.0) if v == "ref" else (decl[v]["code"], decl[v]["p1"], decl[v]["p2"])
            mc, _ = B.run(a, code, p1, p2, caps=True)
            diffs[v] = int((mc[pos_c] != full_m[v][pos_f]).sum())
        row["decisions_differing"] = diffs
        row["pass"] = bool(row["matched"] == row["trades_at_or_before_T_full"] == row["trades_at_or_before_T_cut"]
                           and all(x == 0 for x in diffs.values()))
        res["points"].append(row)
        print(json.dumps(row), flush=True)
    res["pass"] = all(p["pass"] for p in res["points"])
    json.dump(res, open(os.path.join(C.OUT, "truncation_frames.json"), "w"), indent=1, default=str)
    print("PASS" if res["pass"] else "FAIL")


def build_from(per):
    """Same construction as book.build, from in-memory trades."""
    fr = []
    for (name, sym), t in per.items():
        fr.append(pd.DataFrame({
            "sleeve": C.sleeve_key(name, sym), "name": name, "sym": sym,
            "t_in": pd.DatetimeIndex(t.entry_time).as_unit("ns"), "t_out": pd.DatetimeIndex(t.exit_time).as_unit("ns"),
            "side": t.side.to_numpy(np.int64), "R": t.R.to_numpy(float), "risk": t.risk.to_numpy(float),
            "entry": t.entry.to_numpy(float), "reason": t.reason.astype(str).to_numpy(),
            "hold_min": t.hold_min.to_numpy(float), "stop_spreads": t.stop_spreads.to_numpy(float),
            "mfe": t.mfe.to_numpy(float), "mae": t.mae.to_numpy(float)}))
    d = pd.concat(fr, ignore_index=True).sort_values(["t_in", "sleeve"], kind="stable").reset_index(drop=True)
    si, so = C.server_time(d.t_in), C.server_time(d.t_out)
    d["srv_in"], d["srv_out"] = si, so
    day0 = np.datetime64("1970-01-01")
    d["dy_in_abs"] = (si.values.astype("datetime64[D]") - day0).astype("int64")
    d["dy_out_abs"] = (so.values.astype("datetime64[D]") - day0).astype("int64")
    d["wk_in_abs"] = (d.dy_in_abs + 3) // 7
    d["wk_out_abs"] = (d.dy_out_abs + 3) // 7
    d["year"] = d.t_in.dt.year
    d["mk"] = d.sym.map(B.MKT_ID).astype("int64")
    d["fam"] = d.sym.map(C.FAMILY).astype("int64")
    d["sl"] = d.sleeve.map(B.SL_ID).astype("int64")
    d["ok_broker"] = d.stop_spreads >= 3.0
    return d


if __name__ == "__main__":
    main()
