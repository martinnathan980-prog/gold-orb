"""Build, for every sleeve and cost mode (fp, stress), the table of ALL in-sample signals (every order of the rule)
with: decision time, side, risk, fill, the signal's own result taken alone (no_overlap=False), broker refusal
(stop < 3 spreads), membership of the baseline chain (no_overlap=True, refused orders removed), and the causal
descriptors of declared.json. Writes results/r2/autopsy/context/signals/<key>__<mode>.parquet and
chains/<key>__<mode>.parquet."""
import copy
import gc
import os
import time

import numpy as np
import pandas as pd

import common as C
import descr as D
import sleevefeat as SF

SIG_DIR = os.path.join(C.OUT, "signals")
CH_DIR = os.path.join(C.OUT, "chains")
os.makedirs(SIG_DIR, exist_ok=True)
os.makedirs(CH_DIR, exist_ok=True)
MODES = ("fp", "stress")


def clear_caches():
    import sys
    for name, attr in (("r2_ml_strategy", "_cache"), ("strategy_trend", "_bar_cache"), ("strategy_orb", "_daily_cache")):
        m = sys.modules.get(name)
        if m is not None:
            getattr(m, attr).clear()
    D.cm._grid_cache.clear()
    D.cm._atr_cache.clear()


def stress_market(own):
    s = copy.copy(own)
    s.spr = own.spr * 1.5           # apply_spread_mult(k=1.5) widens ask - bid by exactly 1.5, mid unchanged
    return s


def one(k, m1, own_fp, rel, rel2, mode):
    t0 = time.time()
    name = C.registry()[k][1]
    dec_f, feat_f = SF.FUNCS[name]
    mk = C.mode_frame(m1, mode)
    own = own_fp if mode == "fp" else stress_market(own_fp)
    clear_caches()
    o = C.build_orders(k, mk)
    o["oid"] = np.arange(len(o), dtype=np.int64)
    es = C.sim(k, mk, o, mode, no_overlap=False)
    last_start = mk.index[-1]
    fi = np.searchsorted(mk.index.values, es.entry_time.values.astype(mk.index.values.dtype))
    spread_fill = (mk["ao"].to_numpy() - mk["bo"].to_numpy())[fi]
    es_ref = es.risk.to_numpy() < 3 * spread_fill
    es_bnd = (es.exit_time >= last_start).to_numpy()
    refused_oids = set(es.oid[es_ref].tolist())
    keep = ~o.oid.isin(refused_oids)
    clear_caches()
    ch = C.sim(k, mk, o[keep], mode, no_overlap=True)
    ch = ch[ch.entry_time < C.IS_END]
    ch_bnd = (ch.exit_time >= last_start).to_numpy()
    ch_out = ch.loc[~ch_bnd].reset_index(drop=True)
    ch_out.to_parquet(os.path.join(CH_DIR, f"{k}__{mode}.parquet"))
    # signal table
    dec = dec_f(mk, o).reset_index(drop=True)
    fe = feat_f(mk, own, dec)
    ge = D.generic(own, dec.t_dec.to_numpy(np.int64), dec.side.to_numpy(), fe["risk"], rel, rel2)
    s = pd.DataFrame({"oid": o.oid.to_numpy(), "t_dec": dec.t_dec.to_numpy(np.int64), "side": dec.side.to_numpy()})
    for c in dec.columns:
        if c not in ("t_dec", "side"):
            s["dec_" + c] = dec[c].to_numpy()
    for c, v in fe.items():
        s[c] = v
    for c, v in ge.items():
        s[c] = v
    esi = es.set_index("oid")
    s["filled"] = s.oid.isin(esi.index)
    s["fill_ns"] = pd.Series(D.ns_of(esi.entry_time).astype(np.float64), index=esi.index).reindex(s.oid).to_numpy()
    lab = esi.R.reindex(s.oid).to_numpy()
    rs = esi.reason.reindex(s.oid).to_numpy()
    ref = pd.Series(es_ref, index=es.oid).reindex(s.oid).fillna(False).to_numpy(bool)
    bnd = pd.Series(es_bnd, index=es.oid).reindex(s.oid).fillna(False).to_numpy(bool)
    s["label"] = np.where(bnd, np.nan, lab)
    s["label_reason"] = rs
    s["refused"] = ref
    s["boundary"] = bnd
    chi = ch.set_index("oid")
    s["in_chain"] = s.oid.isin(chi.index[~ch_bnd])
    s["chain_R"] = chi.R.reindex(s.oid).to_numpy()
    s.loc[~s.in_chain, "chain_R"] = np.nan
    hr, _ = D.clock(np.where(s.filled, s.fill_ns, 0).astype(np.int64))
    s["hour"] = np.where(s.filled, hr, np.nan)
    _, dw = D.clock(s.t_dec.to_numpy(np.int64))
    s["dow"] = dw
    s["year"] = D.to_ts(s.t_dec.to_numpy(np.int64)).year
    info = {"orders": int(len(o)), "filled": int(s.filled.sum()), "refused": int(ref.sum()),
            "boundary_signals": int(bnd.sum()), "chain_n": int(len(ch_out)), "chain_boundary": int(ch_bnd.sum()),
            "chain_R": round(float(ch_out.R.sum()), 4), "sec": round(time.time() - t0, 1)}
    # sanity: the descriptor code agrees with the rule's own numbers where the rule carries them
    if "dec_over_atr_rule" in s:
        info["max_diff_trig_vs_rule"] = float(np.nanmax(np.abs(s.trig - s.dec_over_atr_rule)))
    if "dec_level_rule" in s:
        info["max_diff_level_vs_rule"] = float(np.nanmax(np.abs(s.level - s.dec_level_rule)))
    if "dec_width_rule" in s:
        info["max_diff_width_vs_rule"] = float(np.nanmax(np.abs(s.width - s.dec_width_rule)))
    s.to_parquet(os.path.join(SIG_DIR, f"{k}__{mode}.parquet"))
    del mk
    gc.collect()
    print(k, mode, info, flush=True)
    return info


def add_chain_context():
    """second pass: prev / oth24 from the baseline chains of all sleeves (same cost mode)"""
    for mode in MODES:
        chains = {k: pd.read_parquet(os.path.join(CH_DIR, f"{k}__{mode}.parquet")) for k in C.KEYS}
        for k in C.KEYS:
            p = os.path.join(SIG_DIR, f"{k}__{mode}.parquet")
            s = pd.read_parquet(p)
            cc = D.chain_context(s.t_dec.to_numpy(np.int64), chains[k], [chains[q] for q in C.KEYS if q != k])
            for c, v in cc.items():
                s[c] = v
            s.to_parquet(p)


def main():
    infos = {}
    us = C.load_fp_is("us100")
    us_mk = D.Market(us)                     # own market of the us100 sleeves
    us_rel = D.Market(us, hourly=False)      # related market of crypto (and rel2 of gold)
    jpy = D.Market(C.load_raw_is("usdjpy", ["bc", "ac", "bh", "ah", "bl", "al"]), hourly=False)
    for k in ("ocm4__us100", "noise30__us100"):
        for mode in MODES:
            infos[f"{k}__{mode}"] = one(k, us, us_mk, jpy, None, mode)
    C.set_leader_is(us)
    del us, us_mk, jpy
    gc.collect()
    eur = D.Market(C.load_raw_is("eurusd", ["bc", "ac", "bh", "ah", "bl", "al"]), hourly=False)
    xau = C.load_fp_is("xauusd")
    own = D.Market(xau)
    for k in ("donch4h_stop__xauusd", "orb_asia_2d_buf10__xauusd", "GOLD_FRI_PM__xauusd"):
        for mode in MODES:
            infos[f"{k}__{mode}"] = one(k, xau, own, eur, us_rel, mode)
    del xau, own, eur
    gc.collect()
    for sym, keys in (("btcusd", ("brk72_24h_wd__btcusd", "F1_brk_ridge_filter__btcusd", "nq_btc_follow__btcusd")),
                      ("ethusd", ("brk72_24h_wd__ethusd", "F1_brk_ridge_filter__ethusd"))):
        m1 = C.load_fp_is(sym)
        own = D.Market(m1)
        for k in keys:
            for mode in MODES:
                infos[f"{k}__{mode}"] = one(k, m1, own, us_rel, None, mode)
        del m1, own
        gc.collect()
    add_chain_context()
    C.dump(infos, os.path.join(C.OUT, "signals_info.json"))


if __name__ == "__main__":
    main()
