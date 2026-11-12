"""Stage D of the clock lens (declared_stageD.json): POST HOC, information only. X1 / X3 = the autopsy's clock cells
as fixed stakes (0.5 / skip); X2 = P8_HDhalf fitted once in-fold (every chain trade closed before 2021-12-25).
Trials 13-15.

    NUMBA_CACHE_DIR=/tmp/numba_clock PYTHONDONTWRITEBYTECODE=1 python3 s6_stageD.py
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
from s3_variants import STAGE_A, logged_ids  # noqa: E402

FRIDAY_SLEEVES = ("ocm4__us100", "brk72_24h_wd__btcusd", "brk72_24h_wd__ethusd", "F1_brk_ridge_filter__btcusd",
                  "F1_brk_ridge_filter__ethusd", "nq_btc_follow__btcusd")


def autopsy_mult(k, times, low):
    times = pd.DatetimeIndex(times)
    m = np.ones(len(times))
    if k in C.NO_WEEKDAY:
        return m
    h = C.local_hours(times, C.NY)
    sel = h >= 12.0
    if k == "nq_btc_follow__btcusd":
        sel |= (h >= 9.5) & (h < 9.5 + 17 / 60)
    if k in FRIDAY_SLEEVES:
        sel |= C.server_weekday(times) == 4
    m[sel] = low
    return m


def main():
    t0 = time.time()
    ids = ("X1_autopsy_half", "X2_infold_HDhalf", "X3_autopsy_skip")
    done = logged_ids()
    assert not (set(ids) & done) and len(done) + len(ids) <= 15, (len(done), sorted(done))
    chains = {m: {k: E.chain(k, m) for k in C.KEYS} for m in C.MODES}
    sigs = {m: {k: E.signals(k, m) for k in C.KEYS} for m in C.MODES}
    # X2: in-fold fits (cutoff 2021-12-25) used for every year
    fits_in = {}
    for mode in C.MODES:
        f = {}
        for k in C.KEYS:
            for dim in ("H", "D"):
                fit = F.fit_fold(chains[mode][k], k, dim, 2022)
                for Y in E.FOLDS:
                    f[(k, dim, Y)] = fit
        fits_in[mode] = f
    spec_x2 = {"parts": STAGE_A["P8_HDhalf"]}
    # X3: skip sets and re-simulation
    jobs = {}
    for mode in C.MODES:
        for k in C.KEYS:
            s = sigs[mode][k]
            s = s[s.filled]
            m = autopsy_mult(k, s.fill_time, 0.0)
            yrs = pd.DatetimeIndex(s.fill_time).year.to_numpy()
            skip = set(s.oid[(m == 0.0) & (yrs >= 2018)].tolist())       # stakes act from 2018 on, as every variant
            jobs.setdefault(k.split("__")[1], []).append(("X3_autopsy_skip", k, mode, skip))
    resim = {}
    leader = None
    for sym in ("us100", "xauusd", "btcusd", "ethusd"):
        m1 = C.load_is(sym)
        if sym == "us100":
            leader = C.leader_series(m1)
        resim.update(E.resim_symbol(sym, m1, leader, jobs[sym]))
        del m1
        gc.collect()
    print(f"resimulated [{time.time() - t0:.0f}s]", flush=True)
    out = {}
    for vid in ids:
        row = {"id": vid, "stage": "D", "kind": "post hoc, information only (cannot be a candidate)", "costs": {},
               "account": "plain sum of the ten chains"}
        for mode in C.MODES:
            per_ref, per_var = {}, {}
            for k in C.KEYS:
                ch = chains[mode][k]
                per_ref[k] = (ch, np.ones(len(ch)))
                if vid == "X1_autopsy_half":
                    yrs = ch.entry_time.dt.year.to_numpy()
                    m = np.where(yrs >= 2018, autopsy_mult(k, ch.entry_time, 0.5), 1.0)
                    per_var[k] = (ch, m)
                elif vid == "X2_infold_HDhalf":
                    m, _ = E.multipliers(k, ch.entry_time, spec_x2, fits_in[mode])
                    per_var[k] = (ch, m)
                else:
                    tv = pd.read_parquet(os.path.join(C.VAR, f"X3_autopsy_skip__{k}__{mode}.parquet"))
                    assert (tv.entry_time < C.IS_END).all() and (tv.exit_time < C.IS_END).all()
                    yrs = tv.entry_time.dt.year.to_numpy()
                    chk = np.where(yrs >= 2018, autopsy_mult(k, tv.entry_time, 0.0), 1.0)
                    assert (chk > 0).all(), (k, mode)
                    per_var[k] = (tv, np.ones(len(tv)))
            ev = E.evaluate(per_ref, per_var, C.OOF)
            ev["per_sleeve_2019_2021"] = E.per_sleeve_effect(per_ref, per_var, C.OOF)
            ev["early_2018_info_only"] = E.evaluate(per_ref, per_var, (2018,))
            row["costs"][mode] = ev
        if vid == "X2_infold_HDhalf":
            row["infold_fits_fp"] = {f"{k}|{dim}": {kk: fits_in['fp'][(k, dim, 2019)][kk] for kk in ("worst", "worst_mean", "n_train", "mean_train")}
                                     for k in C.KEYS for dim in ("H", "D") if fits_in["fp"][(k, dim, 2019)] is not None
                                     and fits_in["fp"][(k, dim, 2019)]["acts"]}
        if vid == "X3_autopsy_skip":
            row["resim"] = {f"{k}|{mode}": resim[("X3_autopsy_skip", k, mode)] for k in C.KEYS for mode in C.MODES}
        fp, st = row["costs"]["fp"], row["costs"]["stress"]
        row["criteria_abc_info_only"] = {"a_ratio": fp["sharpe_ratio"], "b_years_up": fp["years_up"], "c_ratio": st["sharpe_ratio"]}
        out[vid] = row
        C.append_trial(row)
        print(f"{vid:17s} fp Sharpe {fp['ref']['weekly_sharpe']:.3f} -> {fp['var_equal_swing']['weekly_sharpe']:.3f} "
              f"(x{fp['sharpe_ratio']:.3f}, k {fp['scale_k']:.3f}, years up {fp['years_up']}) total@eq "
              f"{fp['ref']['total_R']:.1f} -> {fp['var_equal_swing']['total_R']:.1f} | stress x{st['sharpe_ratio']:.3f} "
              f"| {[(Y, fp['by_year'][Y]['ref_sharpe'], fp['by_year'][Y]['var_sharpe']) for Y in C.OOF]} "
              f"| 2018 x{fp['early_2018_info_only']['sharpe_ratio']:.3f}", flush=True)
    C.jdump(out, os.path.join(C.OUT, "stageD.json"))


if __name__ == "__main__":
    main()
