"""Realised chains (re-simulation after zero stakes), agreement, the book and the portfolio measures.

realise(skip_sets)  : {vid: {mode: {k: set(oid)}}} -> {vid: {mode: {k: chain DataFrame}}}; a sleeve without removal
                      keeps its baseline chain; a sleeve with removals is re-simulated on the in-sample frame (rows
                      ts < 2022-01-01) with those orders removed (one position, same costs), exactly as the baseline
                      chain was built (refused orders removed, trades still open at the end of the slice dropped).
book(...)           : one row per realised chain trade: sleeve, oid, fold year, exit week, stake, R, pnl.
evaluate(...)       : weekly measures on the 157 out-of-fold weeks, per year, at equal weekly swing.
"""
import gc
import time

import numpy as np
import pandas as pd

import cv_common as V
CC = V.CC

MARKET_KEYS = {
    "us100": ["ocm4__us100", "noise30__us100"],
    "xauusd": ["donch4h_stop__xauusd", "orb_asia_2d_buf10__xauusd", "GOLD_FRI_PM__xauusd"],
    "btcusd": ["brk72_24h_wd__btcusd", "F1_brk_ridge_filter__btcusd", "nq_btc_follow__btcusd"],
    "ethusd": ["brk72_24h_wd__ethusd", "F1_brk_ridge_filter__ethusd"],
}
CHAIN_COLS = ["oid", "entry_ns", "exit_ns", "side", "R"]


def to_chain(t):
    return pd.DataFrame({"oid": t.oid.to_numpy(np.int64), "entry_ns": V.ns(t.entry_time), "exit_ns": V.ns(t.exit_time),
                         "side": t.side.to_numpy(np.int64), "R": t.R.to_numpy(float)})


_BASE = {}


def baseline(k, mode):
    if (k, mode) not in _BASE:
        _BASE[(k, mode)] = to_chain(V.load_chain(k, mode))
    return _BASE[(k, mode)]


def realise(skip_sets, verbose=True):
    """skip_sets: {vid: {mode: {k: set of oids with stake 0}}}"""
    import signals as SG                     # context lens module: clear_caches()
    out = {vid: {m: {} for m in V.MODES} for vid in skip_sets}
    need = {(vid, m, k) for vid, d in skip_sets.items() for m, dd in d.items() for k, z in dd.items() if z}
    for vid, d in skip_sets.items():
        for m in V.MODES:
            for k in V.KEYS:
                if (vid, m, k) not in need:
                    out[vid][m][k] = baseline(k, m)
    if not need:
        return out
    us = CC.load_fp_is("us100")
    CC.set_leader_is(us)                     # nq_btc_follow's leader: the in-sample us100 slice only
    for sym, keys in MARKET_KEYS.items():
        todo = [(vid, m, k) for (vid, m, k) in need if k in keys]
        if not todo:
            continue
        t0 = time.time()
        m1 = us if sym == "us100" else CC.load_fp_is(sym)
        for mode in V.MODES:
            mk = CC.mode_frame(m1, mode)
            last_start = mk.index[-1]
            for k in keys:
                jobs = [vid for (vid, m, kk) in todo if m == mode and kk == k]
                if not jobs:
                    continue
                s = V.load_signals(k, mode)
                SG.clear_caches()
                o = CC.build_orders(k, mk)
                o["oid"] = np.arange(len(o), dtype=np.int64)
                assert len(o) == len(s)
                refused = set(s.oid[s.refused].tolist())

                def chain(skip):
                    tt = CC.sim(k, mk, o[~o.oid.isin(refused | skip)], mode, no_overlap=True)
                    tt = tt[tt.entry_time < V.IS_END]
                    return to_chain(tt[tt.exit_time < last_start].reset_index(drop=True))

                b = chain(set())
                ref = baseline(k, mode)
                assert len(b) == len(ref) and (b.oid.to_numpy() == ref.oid.to_numpy()).all() \
                    and np.allclose(b.R.to_numpy(), ref.R.to_numpy(), rtol=0, atol=1e-12), (k, mode)
                for vid in jobs:
                    out[vid][mode][k] = chain(set(skip_sets[vid][mode][k]))
            del mk
            gc.collect()
        if verbose:
            print(f"  realised {sym}: {len(todo)} chains in {time.time() - t0:.0f}s", flush=True)
        if sym != "us100":
            del m1
            gc.collect()
    del us
    gc.collect()
    return out


# ------------------------------------------------------------------------------------------- agreement on chains
def agreement_status(chains, mode, family=False, tdec=None):
    """{k: array of status (+1 agree, -1 disagree, 0 neither) for each trade of chains[k]} computed on the given
    (realised) chains; tdec: {k: t_dec per signal oid}"""
    out = {}
    for k in V.KEYS:
        c = chains[k]
        sym = V.SYM[k]
        if family and sym in ("btcusd", "ethusd"):
            peers = [q for q in V.KEYS if V.SYM[q] in ("btcusd", "ethusd") and q != k]
        else:
            peers = [q for q in V.KEYS if V.SYM[q] == sym and q != k]
        t = tdec[k][c.oid.to_numpy()]
        n_same, n_opp = V.agreement(t, c.side.to_numpy(), [chains[q] for q in peers])
        st = np.zeros(len(c), np.int64)
        st[(n_same > 0) & (n_opp == 0)] = 1
        st[(n_opp > 0) & (n_same == 0)] = -1
        out[k] = st
    return out


def iii_stake(status, agree, disagree):
    st = np.ones(len(status))
    st[status == 1] = agree
    st[status == -1] = disagree
    return st


# ------------------------------------------------------------------------------------------- book and measures
_WEEK = {}


def week_of(ns_arr):
    return V.server_week(ns_arr)


def book(chains, stakes, tdec):
    """chains: {k: chain}; stakes: {k: stake per chain trade (aligned)}; returns the book DataFrame"""
    rows = []
    for k in V.KEYS:
        c = chains[k]
        st = np.asarray(stakes[k], float)
        assert len(st) == len(c)
        yr = pd.DatetimeIndex(tdec[k][c.oid.to_numpy()].astype("datetime64[ns]")).year.to_numpy()
        rows.append(pd.DataFrame({"sleeve": k, "oid": c.oid.to_numpy(), "fold": yr, "exit_ns": c.exit_ns.to_numpy(),
                                  "stake": st, "R": c.R.to_numpy(), "pnl": st * c.R.to_numpy()}))
    b = pd.concat(rows, ignore_index=True)
    b["week"] = week_of(b.exit_ns.to_numpy())
    return b


OOF_W = V.oof_weeks()
YEAR_W = {y: OOF_W[V.week_thursday_year(OOF_W) == y] for y in V.OOF_YEARS}


def evaluate(bk, bref):
    """measures of book bk against the reference book bref (same cost mode), at equal weekly swing"""
    w_ref = V.weekly(bref, OOF_W)
    w_var = V.weekly(bk, OOF_W)
    sd_r, sd_v = np.std(w_ref, ddof=1), np.std(w_var, ddof=1)
    k = float(sd_r / sd_v) if sd_v > 0 else float("nan")
    res = {"scale_k": round(k, 4)}
    res["pooled"] = V.measures(bk, OOF_W, scale=k, months=36)
    res["pooled_ref"] = V.measures(bref, OOF_W, scale=1.0, months=36)
    res["pooled"]["sharpe_ratio_vs_ref"] = round(res["pooled"]["sharpe"] / res["pooled_ref"]["sharpe"], 4)
    res["by_year"] = {}
    for y, wk in YEAR_W.items():
        a = V.measures(bk, wk, scale=k, months=12)
        r = V.measures(bref, wk, scale=1.0, months=12)
        a["sharpe_ratio_vs_ref"] = round(a["sharpe"] / r["sharpe"], 4) if r["sharpe"] else None
        res["by_year"][y] = {"variant": a, "ref": r}
    # stake profile of the out-of-fold decisions
    oof = bk[bk.fold.isin(V.OOF_YEARS)]
    res["stake_profile_oof"] = {str(v): int((oof.stake == v).sum()) for v in sorted(oof.stake.unique())}
    res["per_sleeve_oof"] = {}
    for kk in V.KEYS:
        a = oof[oof.sleeve == kk]
        r = bref[(bref.sleeve == kk) & bref.fold.isin(V.OOF_YEARS)]
        res["per_sleeve_oof"][kk] = {"n": int((a.stake > 0).sum()), "n_ref": int(len(r)),
                                     "stakes": round(float(a.stake.sum()), 1),
                                     "R_at_stake": round(float(a.pnl.sum()), 2), "R_ref": round(float(r.pnl.sum()), 2),
                                     "mean_R_unit": round(float(a.R.mean()), 4) if len(a) else None,
                                     "mean_R_ref": round(float(r.R.mean()), 4) if len(r) else None}
    return res


def verdict_ab(ev):
    a = ev["pooled"]["sharpe_ratio_vs_ref"] >= 1.10
    up = sum(1 for y in V.OOF_YEARS if ev["by_year"][y]["variant"]["sharpe"] > ev["by_year"][y]["ref"]["sharpe"])
    return bool(a), bool(up >= 2), int(up)
