"""PART 2 of the clock lens: the declared variants (declared.json stage A; declared_stageB.json stage B), walk-forward
inside the sample, judged on the portfolio of the ten sleeves at equal weekly swing (2019-2021, FP costs; x1.5).
Every variant run is logged as one line of trials.jsonl (losing ones too).

    NUMBA_CACHE_DIR=/tmp/numba_clock PYTHONDONTWRITEBYTECODE=1 python3 s3_variants.py A      # stage A (9 primaries)
    NUMBA_CACHE_DIR=/tmp/numba_clock PYTHONDONTWRITEBYTECODE=1 python3 s3_variants.py B      # stage B (neighbours)
"""
import gc
import json
import os
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402

import common as C  # noqa: E402
import engine as E  # noqa: E402

STAGE_A = {
    "P1_H0": [{"dim": "H", "rule": "worst", "T": 0.02, "m": 0.0}],
    "P2_Hhalf": [{"dim": "H", "rule": "worst", "T": 0.02, "m": 0.5}],
    "P3_D0": [{"dim": "D", "rule": "worst", "T": 0.02, "m": 0.0}],
    "P4_Dhalf": [{"dim": "D", "rule": "worst", "T": 0.02, "m": 0.5}],
    "P5_Hbest": [{"dim": "H", "rule": "best", "F": 2.0}],
    "P6_Dbest": [{"dim": "D", "rule": "best", "F": 2.0}],
    "P7_HD0": [{"dim": "H", "rule": "worst", "T": 0.02, "m": 0.0}, {"dim": "D", "rule": "worst", "T": 0.02, "m": 0.0}],
    "P8_HDhalf": [{"dim": "H", "rule": "worst", "T": 0.02, "m": 0.5}, {"dim": "D", "rule": "worst", "T": 0.02, "m": 0.5}],
    "P9_FDhalf": [{"dim": "D", "rule": "worst", "T": 0.02, "m": 0.5, "family": True}],
}
STAGE_B_FILE = os.path.join(C.OUT, "declared_stageB.json")


def specs(stage):
    if stage == "A":
        return {vid: {"parts": p} for vid, p in STAGE_A.items()}
    d = C.jload(STAGE_B_FILE)
    return {v["id"]: {"parts": v["parts"]} for v in d["variants"]}


def logged_ids():
    if not os.path.exists(C.TRIALS):
        return set()
    with open(C.TRIALS) as f:
        return {json.loads(line)["id"] for line in f if line.strip()}


def main(stage):
    t0 = time.time()
    sp = specs(stage)
    done = logged_ids()
    clash = set(sp) & done
    if clash:
        raise SystemExit(f"already logged, not re-run: {sorted(clash)}")
    assert len(done) + len(sp) <= 15, "budget of 15 variants exceeded"
    chains = {m: {k: E.chain(k, m) for k in C.KEYS} for m in C.MODES}
    sigs = {m: {k: E.signals(k, m) for k in C.KEYS} for m in C.MODES}
    fits = {m: E.all_fits(chains[m], m) for m in C.MODES}
    # ---------------------------------------------------------------- skip variants: re-simulate the chains
    jobs = {}
    for vid, spec in sp.items():
        if not E.is_skip(spec):
            continue
        for mode in C.MODES:
            for k in C.KEYS:
                sk = E.skip_set(k, sigs[mode][k], spec, fits[mode])
                jobs.setdefault(k.split("__")[1], []).append((vid, k, mode, sk))
    resim = {}
    if jobs:
        leader = None
        for sym in ("us100", "xauusd", "btcusd", "ethusd"):
            m1 = C.load_is(sym)
            if sym == "us100":
                leader = C.leader_series(m1)
            if sym in jobs:
                resim.update(E.resim_symbol(sym, m1, leader, jobs[sym]))
            del m1
            gc.collect()
            print(f"resimulated {sym} [{time.time() - t0:.0f}s]", flush=True)
    # ---------------------------------------------------------------- evaluate
    out = {}
    for vid, spec in sp.items():
        row = {"id": vid, "stage": stage, "parts": spec["parts"], "account": "plain sum of the ten chains",
               "costs": {}, "decisions": {}}
        for mode in C.MODES:
            per_ref, per_var = {}, {}
            decs = {}
            for k in C.KEYS:
                ch = chains[mode][k]
                per_ref[k] = (ch, np.ones(len(ch)))
                tv = E.variant_chain(vid, k, mode, spec)
                mult, dec = E.multipliers(k, tv.entry_time, spec, fits[mode])
                if E.is_skip(spec):
                    assert (mult > 0).all(), (vid, k, mode, "a trade of a skip chain falls in a skipped cell")
                per_var[k] = (tv, mult)
                decs[k] = dec
            ev = E.evaluate(per_ref, per_var, C.OOF)
            ev["per_sleeve_2019_2021"] = E.per_sleeve_effect(per_ref, per_var, C.OOF)
            ev["early_2018_info_only"] = E.evaluate(per_ref, per_var, (2018,))
            row["costs"][mode] = ev
            row["decisions"][mode] = decs
            if (vid, "brk72_24h_wd__btcusd", mode) in resim:
                row.setdefault("resim", {})[mode] = {k: resim[(vid, k, mode)] for k in C.KEYS if (vid, k, mode) in resim}
        fp, st = row["costs"]["fp"], row["costs"]["stress"]
        crit = {"a": bool(fp["sharpe_ratio"] >= 1.10), "a_ratio": fp["sharpe_ratio"],
                "b": bool(fp["years_up"] >= 2), "b_years_up": fp["years_up"],
                "c": bool(st["sharpe_ratio"] >= 1.10), "c_ratio": st["sharpe_ratio"],
                "f_stakes": bool(fp["max_effective_stake"] <= 2.0 and st["max_effective_stake"] <= 2.0)}
        crit["a_b_c"] = bool(crit["a"] and crit["b"] and crit["c"])
        row["criteria_abc"] = crit
        out[vid] = row
        C.append_trial(row)
        print(f"{vid:11s} fp Sharpe {fp['ref']['weekly_sharpe']:.3f} -> {fp['var_equal_swing']['weekly_sharpe']:.3f} "
              f"(x{fp['sharpe_ratio']:.3f}, years up {fp['years_up']}, k {fp['scale_k']:.3f}) total@eq "
              f"{fp['ref']['total_R']:.1f} -> {fp['var_equal_swing']['total_R']:.1f} | stress x{st['sharpe_ratio']:.3f} "
              f"| by year {[ (Y, fp['by_year'][Y]['ref_sharpe'], fp['by_year'][Y]['var_sharpe']) for Y in C.OOF]} "
              f"| 2018 info x{fp['early_2018_info_only']['sharpe_ratio']:.3f} | abc {crit['a_b_c']}", flush=True)
    C.jdump(out, os.path.join(C.OUT, f"stage{stage}.json"))
    print(f"done [{time.time() - t0:.0f}s]")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "A")
