"""Step 0 (rule 2, FIRST CHECK, before any analysis) and the reference chains. IN SAMPLE ONLY.

For each of the ten sleeves, on the in-sample slice of its market (rows ts < 2022-01-01 cut inside the read):
  * rule 2: orders rebuilt by the registry entry, simulated with FP costs and no_overlap (exactly the official call,
    without the 3-spread refusal), compared trade by trade with the official rows entered and closed before 2022;
  * the reference chain in FP and with costs x1.5 (orders rebuilt on the x1.5 frame), 3-spread refusal, trades still
    open at the end of the slice dropped; compared with the context lens's chains (same oid, same R);
  * brk72_24h_wd ethusd: the every-signal table needed by K1 (each order taken alone);
  * the two new sleeves of Addendum H (K2, K3): orb_asia_2d_buf10 on ethusd and on btcusd, FP and x1.5.
Writes out/ref__<key>__<mode>.parquet, out/new__..., out/k1sig__brk72_24h_wd__ethusd__<mode>.parquet, out/s0_repro.json.

    NUMBA_CACHE_DIR=/tmp/synthI_numba PYTHONDONTWRITEBYTECODE=1 python3 s0_repro.py
"""
import gc
import os
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import sy_common as C  # noqa: E402


def compare_official(t, off, name, sym):
    def norm(x):
        return pd.DataFrame({"entry_ns": C.ns_of(x.entry_time), "side": x.side.to_numpy(np.int64),
                             "R": x.R.to_numpy(float), "exit_time": C.ns_of(x.exit_time),
                             "reason": x.reason.astype(str).to_numpy(), "entry_time": x.entry_time.astype(str).to_numpy()})
    a = norm(t)
    b = norm(off)
    m = a.merge(b, on=["entry_ns", "side"], how="outer", suffixes=("_mine", "_off"), indicator=True)
    m["entry_time"] = m["entry_time_mine"].fillna(m["entry_time_off"])
    both = m[m["_merge"] == "both"]
    dif = both[((both.R_mine - both.R_off).abs() > 1e-9) | (both.exit_time_mine != both.exit_time_off)
               | (both.reason_mine != both.reason_off)]
    only_mine = m[m["_merge"] == "left_only"]
    n_open_off, open_entries = C.official_open_at_end_count(name, sym)
    # my trades still open at the end of the slice (time exit placed on the last bar, or 'eod')
    return {"n_mine_all": int(len(t)), "n_official_closed_before_2022": int(len(off)),
            "official_rows_entered_before_2022_with_exit_not_before_2022": n_open_off,
            "their_entry_times": open_entries,
            "matched": int(len(both)), "rows_differing": int(len(dif)),
            "max_abs_R_diff_matched": round(float((both.R_mine - both.R_off).abs().max()), 12) if len(both) else None,
            "only_mine": [{"entry_time": str(r.entry_time), "exit_time": str(r.exit_time_mine), "reason": r.reason_mine}
                          for r in only_mine.itertuples()],
            "only_official": int((m["_merge"] == "right_only").sum()),
            "totR_mine_matched": round(float(both.R_mine.sum()), 4), "totR_official_closed": round(float(off.R.sum()), 4),
            "n_matched_equals_official": bool(len(both) == len(off))}


def ref_chain(name, sym, m1, info, key):
    out = {}
    for mode in C.MODES:
        mk = C.mode_frame(m1, mode)
        o = C.build_orders(name, mk)
        t = C.chain(mk, o, sym, mode)
        C.save_trades(t, f"ref__{key}__{mode}")
        r = {"orders": int(len(o)), "trades": int(len(t)), "refused_3spreads": len(t.attrs["refused"]),
             "total_R": round(float(t.R.sum()), 4)}
        if not key.startswith("new_"):
            ctx = C.load_ctx_chain(key, mode)
            same = len(ctx) == len(t) and (ctx.oid.to_numpy() == t.oid.to_numpy()).all() and \
                np.allclose(ctx.R.to_numpy(), t.R.to_numpy(), rtol=0, atol=1e-12)
            r["equals_context_chain"] = bool(same)
        out[mode] = r
        del mk
        gc.collect()
    info["chains"][key] = out
    print(f"   chain {key}: " + " | ".join(f"{m} n {v['trades']} R {v['total_R']} refused {v['refused_3spreads']}"
                                         f" ctx {v.get('equals_context_chain')}" for m, v in out.items()), flush=True)


def k1_signal_table(m1, sym, info):
    """brk72_24h_wd ethusd: every order with its own result taken alone, refusal, boundary, P and riskbp."""
    res = {}
    for mode in C.MODES:
        mk = C.mode_frame(m1, mode)
        o = C.build_orders("brk72_24h_wd", mk)
        es = C.every_signal(mk, o, sym, mode)
        last_start = mk.index[-1]
        ref = pd.Series(C.refused_mask(mk, es), index=es.oid.to_numpy())
        bnd = pd.Series((es.exit_time >= last_start).to_numpy(), index=es.oid.to_numpy())
        lab = pd.Series(es.R.to_numpy(), index=es.oid.to_numpy())
        s = pd.DataFrame({"oid": o.oid.to_numpy(), "t_dec": C.ns_of(o.dec_time), "side": o.side.to_numpy(),
                          "stop_dist": o.stop_dist.to_numpy(float)})
        s["filled"] = s.oid.isin(es.oid).to_numpy()
        s["refused"] = ref.reindex(s.oid).fillna(False).to_numpy(bool)
        s["boundary"] = bnd.reindex(s.oid).fillna(False).to_numpy(bool)
        s["label"] = np.where(s.boundary, np.nan, lab.reindex(s.oid).to_numpy())
        ns = C.ns_of(mk.index)
        j = np.searchsorted(ns, s.t_dec.to_numpy(np.int64), side="left") - 1
        mid = (mk["bc"].to_numpy(np.float64) + mk["ac"].to_numpy(np.float64)) / 2
        s["P"] = np.where(j >= 0, mid[np.maximum(j, 0)], np.nan)
        s["riskbp"] = 1e4 * s.stop_dist / s.P
        s["year"] = pd.DatetimeIndex(s.t_dec.to_numpy().astype("datetime64[ns]")).year
        s.to_parquet(os.path.join(C.OUT, f"k1sig__brk72_24h_wd__ethusd__{mode}.parquet"))
        # the context lens's table of the same orders must agree on side, P and riskbp
        ctx = C.load_ctx_signals("brk72_24h_wd__ethusd", mode)
        res[mode] = {"signals": int(len(s)), "filled": int(s.filled.sum()), "refused": int(s.refused.sum()),
                     "boundary": int(s.boundary.sum()),
                     "context_same_n": bool(len(ctx) == len(s)),
                     "context_max_abs_diff_riskbp": float(np.nanmax(np.abs(ctx.riskbp.to_numpy() - s.riskbp.to_numpy()))),
                     "context_max_abs_diff_label": float(np.nanmax(np.abs(ctx.label.to_numpy() - s.label.to_numpy()))),
                     "context_side_equal": bool((ctx.side.to_numpy() == s.side.to_numpy()).all())}
        del mk
        gc.collect()
    info["k1_signal_table"] = res
    print("   K1 signal table:", res, flush=True)


def main():
    os.makedirs(C.OUT, exist_ok=True)
    info = {"rule2": {}, "chains": {}, "frames": {}}
    for sym in ("us100", "xauusd", "btcusd", "ethusd"):
        t0 = time.time()
        m1 = C.load_is(sym)
        info["frames"][sym] = {"bars": int(len(m1)), "first": str(m1.index[0]), "last": str(m1.index[-1])}
        print(f"== {sym}: {len(m1)} bars {m1.index[0]} .. {m1.index[-1]} [{time.time() - t0:.1f}s]", flush=True)
        if sym == "us100":
            C.set_leader_is(m1)
        for name in C.BY_SYM[sym]:
            key = f"{name}__{sym}"
            t1 = time.time()
            o = C.build_orders(name, m1)
            t = C.simulate(m1, o, sym=sym, costs=C.mode_costs(sym, "fp"), no_overlap=True)
            off = C.official_closed(name, sym)
            cmp = compare_official(t, off, name, sym)
            ok = (cmp["rows_differing"] == 0 and cmp["only_official"] == 0 and cmp["n_matched_equals_official"]
                  and len(cmp["only_mine"]) == cmp["official_rows_entered_before_2022_with_exit_not_before_2022"])
            cmp["reproduced"] = bool(ok)
            info["rule2"][key] = cmp
            print(f"{name:22s} {sym:7s} mine {cmp['n_mine_all']} | official closed {cmp['n_official_closed_before_2022']}"
                  f" (+{cmp['official_rows_entered_before_2022_with_exit_not_before_2022']} exit 2022, not read) | matched "
                  f"{cmp['matched']} differing {cmp['rows_differing']} | R matched {cmp['totR_mine_matched']} vs official "
                  f"{cmp['totR_official_closed']} | only mine {cmp['only_mine']} | {'OK' if ok else 'MISMATCH'} "
                  f"[{time.time() - t1:.1f}s]", flush=True)
            del t, o
            ref_chain(name, sym, m1, info, key)
        if sym == "btcusd":
            ref_chain("orb_asia_2d_buf10", sym, m1, info, "new_orb_asia_2d_buf10__btcusd")
        if sym == "ethusd":
            k1_signal_table(m1, sym, info)
            ref_chain("orb_asia_2d_buf10", sym, m1, info, "new_orb_asia_2d_buf10__ethusd")
        del m1
        gc.collect()
        C.dump(info, os.path.join(C.OUT, "s0_repro.json"))
    tot_n = sum(v["matched"] for v in info["rule2"].values())
    tot_R = sum(v["totR_official_closed"] for v in info["rule2"].values())
    info["all_ten_reproduced"] = all(v["reproduced"] for v in info["rule2"].values())
    info["official_closed_total"] = {"trades": tot_n, "R": round(tot_R, 3)}
    C.dump(info, os.path.join(C.OUT, "s0_repro.json"))
    print("ALL TEN REPRODUCED:", info["all_ten_reproduced"], info["official_closed_total"], flush=True)


if __name__ == "__main__":
    main()
