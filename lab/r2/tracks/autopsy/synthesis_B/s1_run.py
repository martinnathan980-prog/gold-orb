"""synthesis_B step 1: first check (R0) and the sleeve-level runs C1, N1, N2, I3 of declared.json. IN SAMPLE ONLY.

One symbol at a time (us100, xauusd, btcusd, ethusd). For each of the ten sleeves:
  * rule 2: orders rebuilt from the in-sample slice, simulated with FP costs and no_overlap (no 3-spread refusal),
    compared trade by trade with the official rows entered before 2022;
  * reference trades for the portfolios: fp and x1.5 with the 3-spread refusal; trades still open at the end of the
    slice dropped. Saved in out/ref__<name>__<sym>__<mode>.parquet.
btcusd: N2 (orb_asia_2d_buf10 on btcusd). ethusd: C1 (riskbp walk-forward on brk72_24h_wd), N1 (orb on ethusd),
I3 (donch4h_stop on ethusd, information only).

    NUMBA_CACHE_DIR=/tmp/numba_synthesis_B PYTHONDONTWRITEBYTECODE=1 python3 s1_run.py
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

PURGE = pd.Timedelta(days=7)
Q = 1 / 3


def compare_official(t, off):
    a = t[["entry_time", "side", "R", "exit_time", "reason"]].reset_index(drop=True)
    b = off[["entry_time", "side", "R", "exit_time", "reason"]].reset_index(drop=True)
    m = a.merge(b, on=["entry_time", "side"], how="outer", suffixes=("_mine", "_off"), indicator=True)
    both = m[m["_merge"] == "both"]
    dif = both[((both.R_mine - both.R_off).abs() > 1e-9) | (both.exit_time_mine != both.exit_time_off)]
    return {"n_mine": int(len(t)), "n_official": int(len(off)),
            "totR_mine": round(float(t.R.sum()), 3), "totR_official": round(float(off.R.sum()), 3),
            "matched": int(len(both)), "only_mine": int((m["_merge"] == "left_only").sum()),
            "only_official": int((m["_merge"] == "right_only").sum()), "rows_differing": int(len(dif)),
            "max_abs_R_diff_matched": round(float((both.R_mine - both.R_off).abs().max()), 9) if len(both) else None,
            "official_exits_in_2022": int((off.exit_time >= C.IS_END).sum()),
            "differing": [{"entry_time": str(r.entry_time), "side": int(r.side), "R_mine": round(float(r.R_mine), 4),
                           "R_off": round(float(r.R_off), 4), "exit_mine": str(r.exit_time_mine),
                           "exit_off": str(r.exit_time_off), "reason_mine": r.reason_mine, "reason_off": r.reason_off}
                          for r in dif.head(5).itertuples()]}


def reference_runs(rule, sym, m1, leader, info):
    """rule-2 check (fp, no refusal) + reference trades fp / stress with the refusal."""
    t0 = time.time()
    o = C.build_orders(rule, m1, leader)
    o["oid"] = np.arange(len(o), dtype=np.int64)
    t_chk = C.simulate(m1, o, sym=sym, costs=C.mode_costs(sym, "fp"), no_overlap=True)
    off = C.official(rule, sym)
    cmp = compare_official(t_chk, off)
    cmp["orders"] = int(len(o))
    rows = {}
    for mode in ("fp", "stress"):
        mk = C.mode_frame(m1, mode)
        oo = o if mode == "fp" else C.build_orders(rule, mk, leader)
        oo = oo.copy()
        oo["oid"] = np.arange(len(oo), dtype=np.int64)
        t = C.simulate_filtered(mk, oo, sym, C.mode_costs(sym, mode))
        nref = t.attrs["refused_3spreads"]
        n_all = len(t)
        t = C.drop_boundary(t, mk)
        C.save_trades(t, f"ref__{rule}__{sym}__{mode}")
        w = C.window(t)
        rows[mode] = {"orders": int(len(oo)), "refused_3spreads": int(nref), "boundary_dropped": int(n_all - len(t)),
                      "is_all": C.sstats(t.R), "window": C.sstats(w.R), "by_year": C.by_year(w),
                      "early_years": C.sstats(t[t.entry_time < C.COMMON_START].R)}
        del mk
    cmp["reference"] = rows
    cmp["sec"] = round(time.time() - t0, 1)
    ok = (cmp["n_mine"] == cmp["n_official"] and cmp["only_mine"] == 0 and cmp["only_official"] == 0
          and cmp["rows_differing"] <= cmp["official_exits_in_2022"])
    cmp["reproduced"] = bool(ok)
    info[C.key(rule, sym)] = cmp
    print(f"{rule:22s} {sym:7s} n {cmp['n_mine']}/{cmp['n_official']} totR {cmp['totR_mine']}/{cmp['totR_official']} "
          f"matched {cmp['matched']} diff {cmp['rows_differing']} (exits 2022: {cmp['official_exits_in_2022']}) "
          f"{'OK' if ok else 'MISMATCH'} | fp window {rows['fp']['window']['n']} {rows['fp']['window']['total']} "
          f"refused {rows['fp']['refused_3spreads']}/{rows['stress']['refused_3spreads']} [{cmp['sec']}s]", flush=True)


# ------------------------------------------------------------------------------------------- C1: riskbp walk-forward
def signal_table(mk, sym, mode):
    """Every order of brk72_24h_wd (wrapper included) with its own result taken alone, refusal, boundary, riskbp."""
    o = C.build_orders("brk72_24h_wd", mk)
    o["oid"] = np.arange(len(o), dtype=np.int64)
    es = C.simulate(mk, o, sym=sym, costs=C.mode_costs(sym, mode), no_overlap=False)
    last_start = mk.index[-1]
    ref = pd.Series(C.refused_mask(mk, es), index=es.oid.to_numpy())
    bnd = pd.Series((es.exit_time >= last_start).to_numpy(), index=es.oid.to_numpy())
    lab = pd.Series(es.R.to_numpy(), index=es.oid.to_numpy())
    s = pd.DataFrame({"oid": o.oid.to_numpy(), "t_dec": pd.DatetimeIndex(o.dec_time), "side": o.side.to_numpy(),
                      "stop_dist": o.stop_dist.to_numpy(float)})
    s["filled"] = s.oid.isin(es.oid)
    s["refused"] = ref.reindex(s.oid).fillna(False).to_numpy(bool)
    s["boundary"] = bnd.reindex(s.oid).fillna(False).to_numpy(bool)
    s["label"] = np.where(s.boundary, np.nan, lab.reindex(s.oid).to_numpy())
    ns = mk.index.values.astype("datetime64[ns]").astype(np.int64)
    td = s.t_dec.values.astype("datetime64[ns]").astype(np.int64)
    j = np.searchsorted(ns, td, side="left") - 1                        # last bar whose start is before D
    mid = (mk["bc"].to_numpy(np.float64) + mk["ac"].to_numpy(np.float64)) / 2
    s["P"] = np.where(j >= 0, mid[np.maximum(j, 0)], np.nan)
    s["riskbp"] = 1e4 * s.stop_dist / s.P
    s["year"] = s.t_dec.dt.year
    return o, s


def fit_fold(x, y, q):
    ok = np.isfinite(x)
    x, y = x[ok], y[ok]
    q_lo, q_hi = np.quantile(x, [q, 1 - q])
    lo, hi = x <= q_lo, x >= q_hi
    e_lo = float(y[lo].mean()) if lo.any() else np.nan
    e_hi = float(y[hi].mean()) if hi.any() else np.nan
    side = None
    if np.nanmin([e_lo, e_hi]) < 0:
        side = "lo" if e_lo < e_hi else "hi"
    return {"q_lo": float(q_lo), "q_hi": float(q_hi), "E_lo": e_lo, "E_hi": e_hi, "skip": side, "n_train": int(len(x))}


def walk_forward(s, q=Q):
    use = (s.filled & ~s.refused & ~s.boundary & np.isfinite(s.label)).to_numpy()
    first = s.t_dec.min()
    folds, skip = {}, np.zeros(len(s), bool)
    for y in range(2013, 2022):
        y0 = pd.Timestamp(f"{y}-01-01", tz="UTC")
        if first > pd.Timestamp(f"{y - 1}-01-31", tz="UTC"):
            continue
        tr = use & (s.t_dec < y0 - PURGE).to_numpy()
        if tr.sum() < 100:
            continue
        f = fit_fold(s.riskbp.to_numpy()[tr], s.label.to_numpy()[tr], q)
        te = (s.year == y).to_numpy()
        x = s.riskbp.to_numpy()
        with np.errstate(invalid="ignore"):
            m = np.zeros(len(s), bool) if f["skip"] is None else (
                (x <= f["q_lo"]) if f["skip"] == "lo" else (x >= f["q_hi"]))
        m &= te
        skip |= m
        f.update(n_test=int(te.sum()), n_skipped=int(m.sum()))
        folds[y] = f
    # the value that would be frozen for 2022: every in-sample signal with D before 2022-01-01 minus 7 days
    tr = use & (s.t_dec < C.IS_END - PURGE).to_numpy()
    f22 = fit_fold(s.riskbp.to_numpy()[tr], s.label.to_numpy()[tr], q)
    return skip, folds, f22


def run_c1(m1, sym, info):
    out = {}
    for mode in ("fp", "stress"):
        t0 = time.time()
        mk = C.mode_frame(m1, mode)
        o, s = signal_table(mk, sym, mode)
        skip, folds, f22 = walk_forward(s)
        refused = set(s.oid[s.refused].tolist())
        skipped = set(s.oid[skip].tolist())
        costs = C.mode_costs(sym, mode)

        def chain(excl):
            t = C.simulate_filtered(mk, o[~o.oid.isin(excl)], sym, costs)
            return C.drop_boundary(t, mk), t.attrs["refused_3spreads"]

        tb, rb = chain(refused)
        tv, rv = chain(refused | skipped)
        C.save_trades(tv, f"var__brk72_24h_wd_riskbp__ethusd__{mode}")
        s.to_parquet(os.path.join(C.OUT, f"signals__brk72_24h_wd__ethusd__{mode}.parquet"))
        oof = (tb.entry_time >= pd.Timestamp("2019-01-01", tz="UTC"))
        oofv = (tv.entry_time >= pd.Timestamp("2019-01-01", tz="UTC"))
        removed = set(tb.oid) - set(tv.oid)
        new = set(tv.oid) - set(tb.oid)
        out[mode] = {
            "signals": int(len(s)), "refused": int(len(refused)), "refused_in_chain_extra": [int(rb), int(rv)],
            "folds": {int(k): {kk: (round(v, 4) if isinstance(v, float) else v) for kk, v in f.items()} for k, f in folds.items()},
            "fit_for_2022": {kk: (round(v, 4) if isinstance(v, float) else v) for kk, v in f22.items()},
            "skipped_by_year": {int(y): int(skip[(s.year == y).to_numpy()].sum()) for y in sorted(s.year.unique())},
            "base_2019_2021": C.sstats(tb[oof].R), "var_2019_2021": C.sstats(tv[oofv].R),
            "base_window": C.sstats(C.window(tb).R), "var_window": C.sstats(C.window(tv).R),
            "base_by_year": C.by_year(tb), "var_by_year": C.by_year(tv),
            "baseline_trades_removed": int(len(removed)),
            "R_of_removed": round(float(tb[tb.oid.isin(removed)].R.sum()), 3),
            "new_trades": int(len(new)), "R_of_new": round(float(tv[tv.oid.isin(new)].R.sum()), 3),
            "sec": round(time.time() - t0, 1)}
        print("C1", mode, {k: out[mode][k] for k in ("base_2019_2021", "var_2019_2021", "skipped_by_year")},
              {y: round(f["q_hi"], 2) for y, f in folds.items()}, flush=True)
        del mk
        gc.collect()
    info["C1_brk72_24h_wd_riskbp__ethusd"] = out


def run_new(rule, sym, m1, info, tag):
    out = {}
    for mode in ("fp", "stress"):
        t0 = time.time()
        mk = C.mode_frame(m1, mode)
        o = C.build_orders(rule, mk)
        o["oid"] = np.arange(len(o), dtype=np.int64)
        t = C.simulate_filtered(mk, o, sym, C.mode_costs(sym, mode))
        nref, n_all = t.attrs["refused_3spreads"], len(t)
        t = C.drop_boundary(t, mk)
        C.save_trades(t, f"new__{rule}__{sym}__{mode}")
        w = C.window(t)
        out[mode] = {"orders": int(len(o)), "refused_3spreads": int(nref), "boundary_dropped": int(n_all - len(t)),
                     "window": C.sstats(w.R), "by_year": C.by_year(w),
                     "early": C.sstats(t[t.entry_time < C.COMMON_START].R), "sec": round(time.time() - t0, 1)}
        print(tag, rule, sym, mode, out[mode]["window"], {y: v["total"] for y, v in out[mode]["by_year"].items()},
              f"refused {nref}", flush=True)
        del mk
        gc.collect()
    info[f"{tag}_{rule}__{sym}"] = out


def main():
    os.makedirs(C.OUT, exist_ok=True)
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
            leader = C.leader_series(m1)
        for name in by_sym[sym]:
            reference_runs(name, sym, m1, leader, info)
        if sym == "btcusd":
            run_new("orb_asia_2d_buf10", sym, m1, info, "N2")
        if sym == "ethusd":
            run_c1(m1, sym, info)
            run_new("orb_asia_2d_buf10", sym, m1, info, "N1")
            run_new("donch4h_stop", sym, m1, info, "I3")
        del m1
        gc.collect()
        C.jdump(info, os.path.join(C.OUT, "s1_info.json"))
    C.jdump(info, os.path.join(C.OUT, "s1_info.json"))


if __name__ == "__main__":
    main()
