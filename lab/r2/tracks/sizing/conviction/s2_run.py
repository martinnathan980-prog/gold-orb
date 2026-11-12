"""PART 2: every declared variant (declared.json), FP and costs x1.5, judged on the 157 out-of-fold weeks.

stage 1  early stakes (families i, i-pool, ii) fitted walk-forward per cost mode   (cv_stakes.EARLY)
stage 2  zero stakes -> chains re-simulated on the in-sample frames                (cv_engine.realise)
stage 3  agreement stakes (family iii) on the realised chains; book; measures      (cv_engine.evaluate)
stage 4  (iv): the two best mains of distinct families by pooled FP Sharpe, combined, with 4 neighbours
stage 5  controls V21, V22 (permutation nulls, FP)
Writes trials.jsonl (one line per variant, rewritten in full by this deterministic run), part2.json, chains/."""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

import cv_common as V
import cv_engine as E
import cv_stakes as S

DECL = json.load(open(os.path.join(V.OUT, "declared.json")))
VAR = {v["id"]: v for v in DECL["variants"]}
TRIALS = os.path.join(V.OUT, "trials.jsonl")
CH_OUT = os.path.join(V.OUT, "chains")
os.makedirs(CH_OUT, exist_ok=True)

III = {"V11": (1.5, 0.5, False), "V12": (1.5, 1.0, False), "V13": (1.0, 0.5, False), "V14": (2.0, 0.5, False),
       "V15": (1.5, 0.5, True)}
COMBO_NB = {"i": ("q25", "q40"), "ii": ("V06", "V07"), "iii": ("V13", "V14")}
I_NB = {"V01": ("V02", "V03"), "V23": ("V24", "V25"), "V26": ("V27", "V28")}


# ------------------------------------------------------------------------------------------- helpers
def compact_info(vid, info):
    """fold choices, for the log"""
    out = {}
    for k, per in info.items():
        out[k] = {}
        for y, d in per.items():
            if d is None:
                out[k][y] = None
            elif "decision" in d:
                dec = d["decision"]
                out[k][y] = None if dec is None else {
                    "descriptor": dec["descriptor"], "worst": dec["worst"], "b_lo": round(dec["b_lo"], 5),
                    "b_hi": round(dec["b_hi"], 5), "t": round(dec["t"], 3), "m_worst": round(dec["m_worst"], 4),
                    "stake_worst": dec["stake_worst"], "n_train": d["n_train"],
                    **({"t_sum": round(dec["t_sum"], 3)} if "t_sum" in dec else {})}
            else:                                  # ridge fit
                out[k][y] = {"descriptors": d["descriptors"], "beta": [round(b, 5) for b in d["beta"]],
                             "b_lo": round(d["b_lo"], 5), "b_hi": round(d["b_hi"], 5),
                             "m_lo": round(d["m_lo"][k], 4), "n_train": d["n_train"], "alpha": round(d["alpha"], 1)}
    return out


def stakes_on_chains(chains, early, iii, mode, tdec):
    """final stake of every realised chain trade: early = list of per-signal stake dicts {k: array};
    iii = (agree, disagree, family) or None. Combination rule of V16 when several components."""
    comps = {}
    for j, st in enumerate(early):
        comps[f"e{j}"] = {k: st[k][chains[k].oid.to_numpy()] for k in V.KEYS}
    if iii is not None:
        status = E.agreement_status(chains, mode, family=iii[2], tdec=tdec)
        comps["iii"] = {}
        for k in V.KEYS:
            fold = pd.DatetimeIndex(tdec[k][chains[k].oid.to_numpy()].astype("datetime64[ns]")).year.to_numpy()
            s3 = E.iii_stake(status[k], iii[0], iii[1])
            s3[~np.isin(fold, V.OOF_YEARS)] = 1.0
            comps["iii"][k] = s3
    out = {}
    for k in V.KEYS:
        parts = [comps[c][k] for c in comps]
        if len(parts) == 1:
            out[k] = parts[0].astype(float)
        else:
            z = np.any([p == 0 for p in parts], axis=0)
            st = np.clip(1 + sum(p - 1 for p in parts), 0.5, 2.0)
            st[z] = 0.0
            out[k] = st
        assert (out[k] > 0).all(), (k, "a realised chain trade with stake 0")
    return out


def skipsets(early, mode):
    """oids with stake 0 in any early component"""
    z = {}
    for k in V.KEYS:
        zz = np.zeros(len(early[0][k]), bool) if early else None
        for st in early:
            zz |= st[k] == 0
        z[k] = set(np.flatnonzero(zz).tolist()) if early else set()
    return z


def save_chains(vid, mode, chains):
    df = pd.concat([c.assign(sleeve=k) for k, c in chains.items()], ignore_index=True)
    df.to_parquet(os.path.join(CH_OUT, f"{vid}__{mode}.parquet"))


def chain_changes(chains, mode):
    out = {}
    for k in V.KEYS:
        b = E.baseline(k, mode)
        bo = set(b.oid[b.exit_ns >= V.year_start_ns(2019) - 30 * V.NS_DAY].tolist())
        co = set(chains[k].oid.tolist())
        out[k] = {"removed_baseline_trades": len(set(b.oid) - co), "new_trades": len(co - set(b.oid))}
    return out


# ------------------------------------------------------------------------------------------- main
def main():
    t00 = time.time()
    if os.path.exists(TRIALS):
        os.remove(TRIALS)                       # rewritten in full: the run is deterministic
    T = {m: S.tables(m) for m in V.MODES}
    tdec = {m: {k: T[m][k][0].t_dec.to_numpy(np.int64) for k in V.KEYS} for m in V.MODES}
    base = {m: {k: E.baseline(k, m) for k in V.KEYS} for m in V.MODES}
    bref = {m: E.book(base[m], {k: np.ones(len(base[m][k])) for k in V.KEYS}, tdec[m]) for m in V.MODES}

    # stage 1: early stakes
    early, infos = {}, {}
    for vid, fn in S.EARLY.items():
        early[vid], infos[vid] = {}, {}
        for m in V.MODES:
            early[vid][m], infos[vid][m] = fn(T[m])
    print(f"stage 1 done {time.time() - t00:.0f}s", flush=True)

    # stage 2: realised chains for every early variant
    sk = {vid: {m: skipsets([early[vid][m]], m) for m in V.MODES} for vid in early}
    chains = E.realise(sk)
    for vid in chains:
        for m in V.MODES:
            save_chains(vid, m, chains[vid][m])
    print(f"stage 2 done {time.time() - t00:.0f}s", flush=True)

    results = {}

    def run_variant(vid, early_list_by_mode, iii, chains_by_mode, extra=None):
        res = {"id": vid, **{q: VAR[vid].get(q) for q in ("family", "rule")}}
        for m in V.MODES:
            st = stakes_on_chains(chains_by_mode[m], early_list_by_mode[m], iii, m, tdec[m])
            bk = E.book(chains_by_mode[m], st, tdec[m])
            ev = E.evaluate(bk, bref[m])
            a, b, up = E.verdict_ab(ev)
            ev["a_sharpe_up_10pct"], ev["b_up_2_of_3_years"], ev["years_up"] = a, b, up
            ev["chain_changes"] = chain_changes(chains_by_mode[m], m)
            sig_zero = 0
            for e in early_list_by_mode[m]:
                for k in V.KEYS:
                    yr = T[m][k][0].year.to_numpy()
                    sig_zero += int(((e[k] == 0) & np.isin(yr, V.OOF_YEARS)).sum())
            ev["oof_signals_at_zero"] = sig_zero
            res[m] = ev
        if extra:
            res.update(extra)
        results[vid] = res
        p, ps = res["fp"]["pooled"], res["stress"]["pooled"]
        print(f"{vid}: FP Sharpe {p['sharpe']:.3f} (ref {res['fp']['pooled_ref']['sharpe']:.3f}, x{p['sharpe_ratio_vs_ref']:.3f}) "
              f"yrs up {res['fp']['years_up']} | stress x{ps['sharpe_ratio_vs_ref']:.3f} yrs {res['stress']['years_up']} | "
              f"k {res['fp']['scale_k']} total {p['total_R']} (ref {res['fp']['pooled_ref']['total_R']}) "
              f"zero sig {res['fp']['oof_signals_at_zero']}", flush=True)
        return res

    # reference
    ref_res = {"id": "V00", "family": "reference", "rule": VAR["V00"]["rule"]}
    for m in V.MODES:
        ev = E.evaluate(bref[m], bref[m])
        ref_res[m] = ev
    results["V00"] = ref_res
    # stage 3: early variants and agreement variants
    for vid in S.EARLY:
        run_variant(vid, {m: [early[vid][m]] for m in V.MODES}, None, chains[vid],
                    {"folds_fp": compact_info(vid, infos[vid]["fp"]), "folds_stress": compact_info(vid, infos[vid]["stress"])})
    for vid, iii in III.items():
        run_variant(vid, {m: [] for m in V.MODES}, iii, base)
    print(f"stage 3 done {time.time() - t00:.0f}s", flush=True)

    # stage 4: combination (iv)
    shp = lambda v: results[v]["fp"]["pooled"]["sharpe"]
    i_rep = max(("V01", "V23", "V26"), key=shp)
    fam = {"i": i_rep, "ii": "V05", "iii": "V11"}
    ranked = sorted(fam, key=lambda f: -shp(fam[f]))
    A, B = ranked[0], ranked[1]
    sel = {"i_representative": i_rep, "family_sharpes": {f: round(shp(v), 4) for f, v in fam.items()},
           "A": [A, fam[A]], "B": [B, fam[B]]}
    print("combo selection", sel, flush=True)

    def comp_spec(f, which):
        """component of family f: 'main' or a combo neighbour index 0 / 1 -> (early vid or None, iii or None)"""
        if f == "iii":
            v = "V11" if which == "main" else COMBO_NB["iii"][which]
            return None, III[v], v
        if f == "ii":
            v = "V05" if which == "main" else COMBO_NB["ii"][which]
            return v, None, v
        v = i_rep if which == "main" else I_NB[i_rep][which]
        return v, None, v

    combos = {"V16": ("main", "main"), "V17": (0, "main"), "V18": (1, "main"), "V19": ("main", 0), "V20": ("main", 1)}
    for vid, (wa, wb) in combos.items():
        ea, ia, na = comp_spec(A, wa)
        eb, ib, nb = comp_spec(B, wb)
        el = [e for e in (ea, eb) if e is not None]
        iii = ia or ib
        sk_c = {vid: {m: skipsets([early[e][m] for e in el], m) for m in V.MODES}}
        ch_c = E.realise(sk_c, verbose=False)[vid]
        for m in V.MODES:
            save_chains(vid, m, ch_c[m])
        run_variant(vid, {m: [early[e][m] for e in el] for m in V.MODES}, iii, ch_c,
                    {"components": [na, nb], "selection": sel})
    print(f"stage 4 done {time.time() - t00:.0f}s", flush=True)

    # stage 5: controls (FP)
    results["V21"] = null_i(T["fp"], tdec["fp"], base["fp"], bref["fp"], results["V04"])
    results["V22"] = null_iii(tdec["fp"], base["fp"], bref["fp"], results["V11"])
    print(f"stage 5 done {time.time() - t00:.0f}s", flush=True)

    # criteria
    verdicts = criteria(results)
    for vid in ["V00"] + [v["id"] for v in DECL["variants"] if v["id"] != "V00"]:
        r = results[vid]
        row = {"trial": vid, **{q: r.get(q) for q in ("id", "family", "rule")}, "declared": True,
               "verdict": verdicts.get(vid)}
        for m in V.MODES:
            if m in r:
                row[m] = r[m]
        for q in ("folds_fp", "folds_stress", "components", "selection", "null"):
            if q in r:
                row[q] = r[q]
        V.append_jsonl(TRIALS, row)
    V.dump({"what": "part 2 of the conviction lens: every declared variant, FP and costs x1.5, 157 out-of-fold weeks "
                    "2019-2021, plain sum of the ten chains, equal weekly swing",
            "combo_selection": sel, "verdicts": verdicts,
            "results": {vid: {m: {q: r[m][q] for q in ("scale_k", "pooled", "pooled_ref", "by_year", "years_up",
                                                          "stake_profile_oof", "oof_signals_at_zero", "chain_changes",
                                                          "per_sleeve_oof") if q in r[m]}
                              for m in V.MODES if m in r} for vid, r in results.items() if vid not in ("V21", "V22")},
            "controls": {vid: results[vid]["null"] for vid in ("V21", "V22")}},
           os.path.join(V.OUT, "part2.json"))
    print(f"all done {time.time() - t00:.0f}s", flush=True)


# ------------------------------------------------------------------------------------------- criteria
def criteria(results):
    out = {}
    for v in DECL["variants"]:
        vid = v["id"]
        if vid in ("V00", "V21", "V22"):
            continue
        r = results[vid]
        a, b = r["fp"]["a_sharpe_up_10pct"], r["fp"]["b_up_2_of_3_years"]
        c = r["stress"]["a_sharpe_up_10pct"] and r["stress"]["b_up_2_of_3_years"]
        nbs = v.get("neighbours")
        d = bool(nbs) and all(results[n]["fp"]["pooled"]["sharpe_ratio_vs_ref"] > 1.0 for n in nbs)
        f = vid != "V10"
        out[vid] = {"a": a, "b": b, "c": bool(c), "d": d, "f": f, "is_main": bool(v.get("main")),
                    "fp_ratio": r["fp"]["pooled"]["sharpe_ratio_vs_ref"],
                    "stress_ratio": r["stress"]["pooled"]["sharpe_ratio_vs_ref"],
                    "years_up_fp": r["fp"]["years_up"], "years_up_stress": r["stress"]["years_up"],
                    "neighbour_fp_ratios": {n: results[n]["fp"]["pooled"]["sharpe_ratio_vs_ref"] for n in (nbs or [])},
                    "candidate_before_truncation": bool(a and b and c and d and f)}
    return out


# ------------------------------------------------------------------------------------------- controls
def null_i(T, tdec, base, bref, own, n=200, seed=2021):
    rng = np.random.default_rng(seed)
    ratios = []
    for _ in range(n):
        Tp = {}
        for k, (s, tr) in T.items():
            s2 = s.copy()
            ch_oid = tr.oid.to_numpy()
            fold = s2.year.to_numpy()[ch_oid]
            vals = s2.loc[ch_oid, V.ELIGIBLE].to_numpy(float).copy()
            for y in np.unique(fold):
                idx = np.flatnonzero(fold == y)
                vals[idx] = vals[rng.permutation(idx)]
            s2.loc[ch_oid, V.ELIGIBLE] = vals
            tr2 = s2.set_index("oid").loc[ch_oid].reset_index()
            tr2["exit_ns"], tr2["entry_ns"], tr2["R"] = tr.exit_ns.to_numpy(), tr.entry_ns.to_numpy(), tr.R.to_numpy()
            Tp[k] = (s2, tr2)
        st, _ = S.family_i(Tp, 1 / 3, nozero=True)
        stc = {k: st[k][base[k].oid.to_numpy()] for k in V.KEYS}
        ev = E.evaluate(E.book(base, stc, tdec), bref)
        ratios.append(ev["pooled"]["sharpe_ratio_vs_ref"])
    ratios = np.array(ratios)
    own_r = own["fp"]["pooled"]["sharpe_ratio_vs_ref"]
    null = {"draws": n, "seed": seed, "of": "V04", "own_ratio": own_r,
            "null_mean": round(float(ratios.mean()), 4), "null_p05": round(float(np.percentile(ratios, 5)), 4),
            "null_p50": round(float(np.percentile(ratios, 50)), 4), "null_p95": round(float(np.percentile(ratios, 95)), 4),
            "null_max": round(float(ratios.max()), 4), "share_at_or_above_own": round(float((ratios >= own_r).mean()), 4),
            "share_at_or_above_1.10": round(float((ratios >= 1.10).mean()), 4)}
    print("V21 null_i", null, flush=True)
    return {"id": "V21", "family": "control", "rule": VAR["V21"]["rule"], "null": null}


def null_iii(tdec, base, bref, own, n=200, seed=2022):
    rng = np.random.default_rng(seed)
    status = E.agreement_status(base, "fp", tdec=tdec)
    ratios = []
    for _ in range(n):
        stc = {}
        for k in V.KEYS:
            c = base[k]
            fold = pd.DatetimeIndex(tdec[k][c.oid.to_numpy()].astype("datetime64[ns]")).year.to_numpy()
            stt = status[k].copy()
            for y in V.OOF_YEARS:
                idx = np.flatnonzero(fold == y)
                stt[idx] = stt[rng.permutation(idx)]
            s3 = E.iii_stake(stt, 1.5, 0.5)
            s3[~np.isin(fold, V.OOF_YEARS)] = 1.0
            stc[k] = s3
        ev = E.evaluate(E.book(base, stc, tdec), bref)
        ratios.append(ev["pooled"]["sharpe_ratio_vs_ref"])
    ratios = np.array(ratios)
    own_r = own["fp"]["pooled"]["sharpe_ratio_vs_ref"]
    null = {"draws": n, "seed": seed, "of": "V11", "own_ratio": own_r,
            "null_mean": round(float(ratios.mean()), 4), "null_p05": round(float(np.percentile(ratios, 5)), 4),
            "null_p50": round(float(np.percentile(ratios, 50)), 4), "null_p95": round(float(np.percentile(ratios, 95)), 4),
            "null_max": round(float(ratios.max()), 4), "share_at_or_above_own": round(float((ratios >= own_r).mean()), 4)}
    print("V22 null_iii", null, flush=True)
    return {"id": "V22", "family": "control", "rule": VAR["V22"]["rule"], "null": null}


if __name__ == "__main__":
    main()
