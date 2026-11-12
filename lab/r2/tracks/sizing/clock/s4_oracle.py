"""Stage C of the clock lens (declared_stageC.json): two DIAGNOSTIC bounds that use the out-of-fold outcomes
themselves (perfect foresight of each year's mean R by hour band / weekday, stakes clipped to [0, 2]). Not rules, not
candidates, judge nothing; logged in trials.jsonl as trials 10 and 11.

    NUMBA_CACHE_DIR=/tmp/numba_clock PYTHONDONTWRITEBYTECODE=1 python3 s4_oracle.py
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402

import common as C  # noqa: E402
import engine as E  # noqa: E402
import fits as F  # noqa: E402
from s3_variants import logged_ids  # noqa: E402


def oracle_mult(ch, k, dim):
    m = np.ones(len(ch))
    cc = F.cells(k, ch.entry_time, dim)
    if cc is None:
        return m
    y = ch.entry_time.dt.year.to_numpy()
    R = ch.R.to_numpy(float)
    for Y in C.OOF:
        iy = y == Y
        mu = R[iy].mean() if iy.any() else 0.0
        if not mu > 0:
            continue
        for c in np.unique(cc[iy]):
            sel = iy & (cc == c)
            m[sel] = float(np.clip(R[sel].mean() / mu, 0.0, 2.0))
    return m


def main():
    done = logged_ids()
    ids = {"O1_Horacle": "H", "O2_Doracle": "D"}
    assert not (set(ids) & done), "already logged"
    assert len(done) + len(ids) <= 15
    out = {}
    for vid, dim in ids.items():
        row = {"id": vid, "stage": "C", "kind": "diagnostic bound with perfect foresight (uses the out-of-fold outcomes; judges nothing)",
               "dim": dim, "account": "plain sum of the ten chains", "costs": {}}
        for mode in C.MODES:
            per_ref, per_var = {}, {}
            for k in C.KEYS:
                ch = E.chain(k, mode)
                per_ref[k] = (ch, np.ones(len(ch)))
                per_var[k] = (ch, oracle_mult(ch, k, dim))
            ev = E.evaluate(per_ref, per_var, C.OOF)
            ev["per_sleeve_2019_2021"] = E.per_sleeve_effect(per_ref, per_var, C.OOF)
            row["costs"][mode] = ev
        out[vid] = row
        C.append_trial(row)
        fp, st = row["costs"]["fp"], row["costs"]["stress"]
        print(f"{vid}: fp Sharpe {fp['ref']['weekly_sharpe']:.3f} -> {fp['var_equal_swing']['weekly_sharpe']:.3f} "
              f"(x{fp['sharpe_ratio']:.3f}, k {fp['scale_k']:.3f}, years up {fp['years_up']}) total@eq "
              f"{fp['ref']['total_R']:.1f} -> {fp['var_equal_swing']['total_R']:.1f} | stress x{st['sharpe_ratio']:.3f} "
              f"| by year {[(Y, fp['by_year'][Y]['ref_sharpe'], fp['by_year'][Y]['var_sharpe']) for Y in C.OOF]}")
    C.jdump(out, os.path.join(C.OUT, "stageC_oracle.json"))


if __name__ == "__main__":
    main()
