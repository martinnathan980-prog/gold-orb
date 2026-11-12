"""Measurement correction (no new variant): the first run of stage A and stage C split the years by ENTRY year for the
per-year Sharpe, so the few trades entered in late December that exit in the first week of the next year were left
out of both years' series. The pooled 2019-2021 figures (criteria a and c) did not have this defect. A year is now the
weeks of that year sliced from the pooled weekly series. Same rules, same fits, same re-simulated chains (read from
results/.../variants/); appended to trials.jsonl as correction lines that do not count as new trials.

    NUMBA_CACHE_DIR=/tmp/numba_clock PYTHONDONTWRITEBYTECODE=1 python3 s3b_remeasure.py
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402

import common as C  # noqa: E402
import engine as E  # noqa: E402
from s3_variants import STAGE_A  # noqa: E402
from s4_oracle import oracle_mult  # noqa: E402


def main():
    chains = {m: {k: E.chain(k, m) for k in C.KEYS} for m in C.MODES}
    fits = {m: E.all_fits(chains[m], m) for m in C.MODES}
    out = {}
    jobs = [(vid, {"parts": p}, None) for vid, p in STAGE_A.items()] + [("O1_Horacle", None, "H"), ("O2_Doracle", None, "D")]
    for vid, spec, odim in jobs:
        row = {"id": vid, "correction_of": vid, "counts_as_new_trial": False,
               "correction": "per-year weekly Sharpe now computed on the weeks of each year sliced from the pooled weekly series",
               "costs": {}}
        for mode in C.MODES:
            per_ref, per_var = {}, {}
            for k in C.KEYS:
                ch = chains[mode][k]
                per_ref[k] = (ch, np.ones(len(ch)))
                if spec is None:
                    per_var[k] = (ch, oracle_mult(ch, k, odim))
                else:
                    tv = E.variant_chain(vid, k, mode, spec)
                    mult, _ = E.multipliers(k, tv.entry_time, spec, fits[mode])
                    per_var[k] = (tv, mult)
            ev = E.evaluate(per_ref, per_var, C.OOF)
            ev["per_sleeve_2019_2021"] = E.per_sleeve_effect(per_ref, per_var, C.OOF)
            ev["early_2018_info_only"] = E.evaluate(per_ref, per_var, (2018,))
            row["costs"][mode] = ev
        fp, st = row["costs"]["fp"], row["costs"]["stress"]
        crit = {"a": bool(fp["sharpe_ratio"] >= 1.10), "a_ratio": fp["sharpe_ratio"],
                "b": bool(fp["years_up"] >= 2), "b_years_up": fp["years_up"],
                "c": bool(st["sharpe_ratio"] >= 1.10), "c_ratio": st["sharpe_ratio"],
                "f_stakes": bool(fp["max_effective_stake"] <= 2.0 and st["max_effective_stake"] <= 2.0)}
        crit["a_b_c"] = bool(crit["a"] and crit["b"] and crit["c"])
        row["criteria_abc"] = crit
        out[vid] = row
        C.append_trial(row)
        print(f"{vid:11s} fp x{fp['sharpe_ratio']:.3f} years up {fp['years_up']} "
              f"{[(Y, fp['by_year'][Y]['ref_sharpe'], fp['by_year'][Y]['var_sharpe']) for Y in C.OOF]} "
              f"| stress x{st['sharpe_ratio']:.3f} years up {st['years_up']} | 2018 x{fp['early_2018_info_only']['sharpe_ratio']:.3f}")
    C.jdump(out, os.path.join(C.OUT, "stageA_C_remeasured.json"))


if __name__ == "__main__":
    main()
