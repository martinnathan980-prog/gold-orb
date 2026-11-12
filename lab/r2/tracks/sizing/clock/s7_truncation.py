"""Truncation test of the clock lens (hard rule 3; declared.json criterion e). IN SAMPLE ONLY, fp.
(e1) For every sleeve and every fold Y in 2018..2021: the frame (and the us100 leader of nq_btc_follow) is cut at the
     fold's cutoff (rows ts < 1 January Y - 7 days); orders and the reference chain are rebuilt on the cut frame; its
     closed trades must equal the full-slice chain's trades closed before the cutoff, and the hour-band / weekday
     training tables and their worst / best choices must be identical.
(e2) For the two skip variants that acted most (P3_D0, P1_H0): up to 10 skipped orders and 10 kept trades per acting
     sleeve in 2019-2021 (seed 7): the frame is cut 2 bars after the fill bar, orders rebuilt, every order simulated
     alone on the cut frame to get its fill time, the skip rule applied with the fold's fit from (e1), and the chain
     re-simulated on the cut frame: a kept trade must be present with the same fill time and side (and multiplier 1);
     a skipped order must fall in the skipped cell and be absent from the cut chain.
No variant is evaluated here (no trial).

    NUMBA_CACHE_DIR=/tmp/numba_clock PYTHONDONTWRITEBYTECODE=1 python3 s7_truncation.py
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
import engine as E  # noqa: E402
import fits as F  # noqa: E402
from s3_variants import STAGE_A  # noqa: E402

SKIP_VARIANTS = ("P3_D0", "P1_H0")


def same_fit(a, b):
    if a is None or b is None:
        return a is None and b is None
    if a["n_train"] != b["n_train"] or a["acts"] != b["acts"] or a["worst"] != b["worst"] or a["best"] != b["best"]:
        return False
    if set(a["table"]) != set(b["table"]):
        return False
    return all(a["table"][c][0] == b["table"][c][0] and abs(a["table"][c][1] - b["table"][c][1]) < 1e-12 for c in a["table"])


def cut_frame(df, t):
    return df.iloc[:int(df.index.searchsorted(t, side="left"))]


def e1_sleeve(k, m1, leader_full, full_chain):
    rule, sym = k.split("__")
    res = {}
    fits_cut = {}
    for Y in E.FOLDS:
        cut = F.cutoff(Y)
        mc = cut_frame(m1, cut)
        lead = None if leader_full is None else leader_full[leader_full.index < cut]
        if len(mc) < 1000:
            res[Y] = {"frame_rows": int(len(mc)), "note": "no data before the cutoff"}
            for dim in ("H", "D"):
                fits_cut[(k, dim, Y)] = F.fit_fold(full_chain.iloc[:0], k, dim, Y)
            continue
        o = C.build_orders(rule, mc, lead)
        t = C.simulate_filtered(mc, o, sym, C.mode_costs(sym, "fp"))
        t = C.drop_boundary(t, mc)
        t = t[t.exit_time < cut]
        f = full_chain[full_chain.exit_time < cut]
        a = t[["entry_time", "side", "exit_time", "R"]].reset_index(drop=True)
        b = f[["entry_time", "side", "exit_time", "R"]].reset_index(drop=True)
        same_trades = len(a) == len(b) and (a.entry_time.values == b.entry_time.values).all() and \
            (a.side.values == b.side.values).all() and (a.exit_time.values == b.exit_time.values).all() and \
            bool(np.allclose(a.R.values, b.R.values, rtol=0, atol=1e-12))
        r = {"frame_rows": int(len(mc)), "train_trades_cut": int(len(a)), "train_trades_full": int(len(b)),
             "same_trades": bool(same_trades)}
        for dim in ("H", "D"):
            fc = F.fit_fold(t, k, dim, Y)
            ff = F.fit_fold(full_chain, k, dim, Y)
            fits_cut[(k, dim, Y)] = fc
            r[f"same_fit_{dim}"] = bool(same_fit(fc, ff))
        res[Y] = r
    return res, fits_cut


def e2_variant(vid, k, m1, leader_full, fits_full, fits_cut, rng):
    rule, sym = k.split("__")
    spec = {"parts": STAGE_A[vid]}
    sig = E.signals(k, "fp")
    full_v = pd.read_parquet(os.path.join(C.VAR, f"{vid}__{k}__fp.parquet"))
    sk = E.skip_set(k, sig, spec, fits_full)
    s = sig[sig.filled & sig.fill_time.dt.year.isin(C.OOF).to_numpy()]
    skipped = s[s.oid.isin(sk)]
    kept = full_v[full_v.entry_time.dt.year.isin(C.OOF)]
    if not len(skipped):
        return None
    pick_s = skipped.iloc[rng.choice(len(skipped), size=min(10, len(skipped)), replace=False)]
    pick_k = kept.iloc[rng.choice(len(kept), size=min(10, len(kept)), replace=False)]
    out = {"n_skipped_tested": int(len(pick_s)), "n_kept_tested": int(len(pick_k)), "fail": 0, "examples": []}
    costs = C.mode_costs(sym, "fp")
    cases = [("skipped", r.fill_time, int(r.side)) for r in pick_s.itertuples()] + \
            [("kept", r.entry_time, int(r.side)) for r in pick_k.itertuples()]
    for kind, ft, side in cases:
        fi = int(m1.index.searchsorted(ft))
        assert m1.index[fi] == ft
        mc = m1.iloc[:fi + 3]                                   # fill bar + 2 more bars
        tcut = mc.index[-1] + pd.Timedelta(minutes=1)
        lead = None if leader_full is None else leader_full[leader_full.index < tcut]
        o = C.build_orders(rule, mc, lead)
        es = C.simulate(mc, o, sym=sym, costs=costs, no_overlap=False)
        # skip set from the cut frame only: fill times on the cut frame, fold fits from frames cut at the cutoff (e1)
        sc = pd.DataFrame({"oid": es.oid.to_numpy(), "fill_time": es.entry_time.to_numpy(), "filled": True})
        sc["fill_time"] = pd.to_datetime(sc.fill_time, utc=True)
        mult, _ = E.multipliers(k, sc.fill_time, spec, fits_cut)
        skip = set(sc.oid[mult == 0.0].tolist())
        ch = C.simulate_filtered(mc, o[~o.oid.isin(skip)], sym, costs)
        present = ((ch.entry_time == ft) & (ch.side == side)).any()
        m_here = float(E.multipliers(k, pd.DatetimeIndex([ft]), spec, fits_cut)[0][0])
        if kind == "kept":
            ok = bool(present and m_here == 1.0)
        else:
            ok = bool((not present) and m_here == 0.0)
        if not ok:
            out["fail"] += 1
            if len(out["examples"]) < 5:
                out["examples"].append({"kind": kind, "fill_time": str(ft), "side": side, "present": bool(present),
                                        "mult_cut": m_here})
    out["pass"] = out["fail"] == 0
    return out


def main():
    t0 = time.time()
    res = {"what": "truncation test of the clock lens (fp)", "e1": {}, "e2": {}}
    chains = {k: E.chain(k, "fp") for k in C.KEYS}
    fits_full = E.all_fits(chains, "fp")
    by_sym = {}
    for name, sym in C.SLEEVES:
        by_sym.setdefault(sym, []).append(C.key(name, sym))
    leader = None
    rng = np.random.default_rng(7)
    fits_cut_all = {}
    for sym in ("us100", "xauusd", "btcusd", "ethusd"):
        m1 = C.load_is(sym)
        if sym == "us100":
            leader = C.leader_series(m1)
        for k in by_sym[sym]:
            lead = leader if k.startswith("nq_btc_follow") else None
            r, fc = e1_sleeve(k, m1, lead, chains[k])
            res["e1"][k] = r
            fits_cut_all.update(fc)
            print(k, "e1", {Y: (v.get("same_trades"), v.get("same_fit_H"), v.get("same_fit_D")) for Y, v in r.items()},
                  f"[{time.time() - t0:.0f}s]", flush=True)
        for vid in SKIP_VARIANTS:
            for k in by_sym[sym]:
                lead = leader if k.startswith("nq_btc_follow") else None
                fits_k = {key: v for key, v in fits_full.items()}
                fits_c = {key: v for key, v in fits_full.items()}
                fits_c.update({key: v for key, v in fits_cut_all.items() if key[0] == k})
                r = e2_variant(vid, k, m1, lead, fits_k, fits_c, rng)
                if r is None:
                    continue
                res["e2"][f"{vid}|{k}"] = r
                print(vid, k, "e2", {q: r[q] for q in ("n_skipped_tested", "n_kept_tested", "fail")},
                      f"[{time.time() - t0:.0f}s]", flush=True)
        del m1
        gc.collect()
    e1_ok = all(v.get("same_trades", True) and v.get("same_fit_H", True) and v.get("same_fit_D", True)
                for r in res["e1"].values() for v in r.values())
    e2_ok = all(r["pass"] for r in res["e2"].values())
    res["pass_e1"] = bool(e1_ok)
    res["pass_e2"] = bool(e2_ok)
    res["sec"] = round(time.time() - t0, 1)
    C.jdump(res, os.path.join(C.OUT, "truncation.json"))
    print("e1", "PASS" if e1_ok else "FAIL", "| e2", "PASS" if e2_ok else "FAIL")


if __name__ == "__main__":
    main()
