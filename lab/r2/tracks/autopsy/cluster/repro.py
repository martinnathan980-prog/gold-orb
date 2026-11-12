"""Lens `cluster`, step 0 (Addendum H, rule 2): reproduce the official in-sample trades of the ten sleeves from
in-sample frames only, under FP costs (mode 'fp') and with costs x1.5 (mode 'stress').

Each market's frame is read with the row filter ts < 2022-01-01 (common.load_is_frame) and that slice is passed
explicitly to r2.run(sym, make_orders, params, mode, True, m1) -- the same call as r2/recalc.py:98 -- for every
sleeve of the registry r2/recalc.py::sleeves(). The leader of nq_btc_follow (us100) is registered with set_leader()
from the in-sample us100 frame, never from the default loader.

Output (results/r2/autopsy/cluster/): trades_is/<name>__<sym>__<mode>.parquet, repro.json.
Each trade also carries the spread of its fill bar and its stop distance in spreads (the broker refuses a stop
closer than 3 spreads: such trades are later counted as not taken).
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from goldlab import r2  # noqa: E402

sys.path.insert(0, os.path.join(C.LAB, "r2"))
import recalc  # noqa: E402  (registry only: nothing is run on a full frame)

KEEP = ["side", "entry_time", "exit_time", "entry", "exit", "stop", "reason", "swap", "pnl", "risk", "R", "ret",
        "hold_min", "mfe", "mae"]


def registry():
    want = set(C.SLEEVES)
    out = {}
    for track, name, sym, mo, params in recalc.sleeves():
        if (name, sym) in want:
            out[(name, sym)] = (track, mo, params)
    assert set(out) == want, set(want) - set(out)
    return out


def compare(mine, off):
    """Per-trade comparison on (entry_time, side)."""
    a = mine.reset_index(drop=True)
    b = off.reset_index(drop=True)
    ns = lambda s: pd.DatetimeIndex(s).as_unit("ns").asi8
    ka = ns(a.entry_time) // 60_000_000_000 * 10 + (a.side.to_numpy() > 0)
    kb = ns(b.entry_time) // 60_000_000_000 * 10 + (b.side.to_numpy() > 0)
    ia = pd.Series(np.arange(len(a)), index=ka)
    ib = pd.Series(np.arange(len(b)), index=kb)
    assert ia.index.is_unique and ib.index.is_unique
    common = ia.index.intersection(ib.index)
    da = a.iloc[ia[common].to_numpy()].reset_index(drop=True)
    db = b.iloc[ib[common].to_numpy()].reset_index(drop=True)
    dR = (da.R - db.R).abs().to_numpy()
    same_exit = ns(da.exit_time) == ns(db.exit_time)
    same = (dR < 1e-9) & same_exit & (da.reason.astype(str).to_numpy() == db.reason.astype(str).to_numpy())
    diff_rows = []
    for k in np.nonzero(~same)[0]:
        diff_rows.append({"entry_time": str(da.entry_time[k]), "side": int(da.side[k]),
                          "mine": {"exit_time": str(da.exit_time[k]), "reason": str(da.reason[k]), "R": round(float(da.R[k]), 6)},
                          "official_R": round(float(db.R[k]), 6), "official_reason": str(db.reason[k])})
    return {"n_mine": int(len(a)), "n_official": int(len(b)), "n_matched_on_entry_and_side": int(len(common)),
            "only_mine": int(len(a) - len(common)), "only_official": int(len(b) - len(common)),
            "n_identical": int(same.sum()), "max_abs_dR_identical": float(dR[same].max()) if same.any() else None,
            "total_R_mine": round(float(a.R.sum()), 6), "total_R_official": round(float(b.R.sum()), 6),
            "different_trades": diff_rows}


def run_market(sym, sleeves, reg, leader=None):
    m1 = C.load_is_frame(sym)
    spread = (m1["ao"] - m1["bo"]).to_numpy()
    rows = {}
    for name in sleeves:
        track, mo, params = reg[(name, sym)]
        res = {"track": track, "params": params, "frame": [str(m1.index[0]), str(m1.index[-1]), int(len(m1))]}
        for mode in ("fp", "stress"):
            C.clear_rule_caches()
            if name == "nq_btc_follow":
                sys.modules["r2_leadlag_strategy"].set_leader("us100", leader)
            t0 = time.time()
            t = r2.run(sym, mo, params, mode, True, m1)
            dt = time.time() - t0
            assert (t.entry_time < C.IS_END).all()
            fi = m1.index.get_indexer(t.entry_time)
            assert (fi >= 0).all()
            sp = spread[fi] * (1.5 if mode == "stress" else 1.0)
            out = t[KEEP].copy().reset_index(drop=True)
            out["spread_fill"] = sp
            out["stop_spreads"] = out.risk.to_numpy() / sp
            out.to_parquet(os.path.join(C.TRADES_DIR, f"{name}__{sym}__{mode}.parquet"))
            res[mode] = {"n": int(len(out)), "total_R": round(float(out.R.sum()), 6),
                         "mean_R": round(float(out.R.mean()), 6), "orders": int(t.attrs.get("orders", -1)),
                         "skipped": int(t.attrs.get("skipped", -1)), "nofill": int(t.attrs.get("nofill", -1)),
                         "reasons": out.reason.astype(str).value_counts().to_dict(),
                         "stop_lt_3_spreads": int((out.stop_spreads < 3).sum()),
                         "min_stop_spreads": round(float(out.stop_spreads.min()), 2),
                         "first_entry": str(out.entry_time.min()), "last_entry": str(out.entry_time.max()),
                         "seconds": round(dt, 1)}
            if mode == "fp":
                res["vs_official"] = compare(out, C.read_official_is(name, sym))
            print(f"{name:20s} {sym:7s} {mode:6s} n={len(out):5d} R={out.R.sum():8.2f} [{dt:.0f}s]", flush=True)
        rows[f"{name}:{sym}"] = res
    del m1
    return rows


def main():
    os.makedirs(C.TRADES_DIR, exist_ok=True)
    reg = registry()
    res = {}
    # us100 first: its in-sample frame also gives the leader of nq_btc_follow (mid closes / opens only)
    m = C.load_is_frame("us100")
    leader = m[["bo", "ao", "bc", "ac"]].copy()
    del m
    plan = [("us100", ["noise30", "ocm4"]), ("btcusd", ["brk72_24h_wd", "nq_btc_follow", "F1_brk_ridge_filter"]),
            ("ethusd", ["brk72_24h_wd", "F1_brk_ridge_filter"]),
            ("xauusd", ["GOLD_FRI_PM", "donch4h_stop", "orb_asia_2d_buf10"])]
    for sym, names in plan:
        res.update(run_market(sym, names, reg, leader))
        r2.free()
    json.dump(res, open(os.path.join(C.OUT, "repro.json"), "w"), indent=1, default=str)
    for k, v in res.items():
        c = v["vs_official"]
        print(f"{k:32s} mine {c['n_mine']:5d} / official {c['n_official']:5d}; identical {c['n_identical']:5d};"
              f" total R {c['total_R_mine']:9.3f} / {c['total_R_official']:9.3f}; differing {len(c['different_trades'])}")


if __name__ == "__main__":
    main()
