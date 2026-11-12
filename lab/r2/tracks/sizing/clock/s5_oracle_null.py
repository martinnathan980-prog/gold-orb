"""Stage C2 of the clock lens (declared_stageC2.json): null of the perfect-foresight bounds O1 / O2. Clock labels are
permuted within each sleeve-year (cell sizes kept), the foresight multipliers recomputed, and the pooled fp weekly
Sharpe ratio at equal swing recorded (500 permutations per dimension). Diagnostic, judges nothing; one trial.

    NUMBA_CACHE_DIR=/tmp/numba_clock PYTHONDONTWRITEBYTECODE=1 python3 s5_oracle_null.py
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

NPERM = 500
SEED = 20261112


def setup(mode="fp"):
    """book of 2019-2021 trades with week index, sleeve-year groups and clock cells"""
    ws_all = C.weeks_of_years(C.OOF)
    pos = {w: i for i, w in enumerate(ws_all)}
    R, wk, grp, cH, cD = [], [], [], [], []
    g = 0
    for k in C.KEYS:
        ch = E.chain(k, mode)
        ch = ch[ch.entry_time.dt.year.isin(C.OOF)]
        y = ch.entry_time.dt.year.to_numpy()
        h = F.cells(k, ch.entry_time, "H")
        d = F.cells(k, ch.entry_time, "D")
        for Y in C.OOF:
            iy = y == Y
            n = int(iy.sum())
            R.append(ch.R.to_numpy(float)[iy])
            wk.append(np.array([pos[w] for w in C.week_id(ch.exit_time[iy])], np.int64))
            grp.append(np.full(n, g))
            cH.append(h[iy] if h is not None else np.full(n, -1))
            cD.append(d[iy] if d is not None else np.full(n, -1))
            g += 1
    return (np.concatenate(R), np.concatenate(wk), np.concatenate(grp), np.concatenate(cH), np.concatenate(cD),
            len(ws_all), g)


def oracle_mult(R, grp, cells, ngrp):
    m = np.ones(len(R))
    for g in range(ngrp):
        ig = np.flatnonzero(grp == g)
        if not len(ig):
            continue
        cc = cells[ig]
        if (cc < 0).all():
            continue
        mu = R[ig].mean()
        if not mu > 0:
            continue
        for c in np.unique(cc):
            sel = ig[cc == c]
            m[sel] = np.clip(R[sel].mean() / mu, 0.0, 2.0)
    return m


def ratio(R, wk, nweeks, m):
    ref = np.bincount(wk, weights=R, minlength=nweeks)
    var = np.bincount(wk, weights=R * m, minlength=nweeks)
    s_ref = ref.mean() / ref.std(ddof=1)
    s_var = var.mean() / var.std(ddof=1)
    return s_var / s_ref


def main():
    done = logged_ids()
    assert "N1_oracle_null" not in done and len(done) + 1 <= 15
    R, wk, grp, cH, cD, nweeks, ngrp = setup("fp")
    rng = np.random.default_rng(SEED)
    res = {"id": "N1_oracle_null", "stage": "C2", "kind": "diagnostic null of the perfect-foresight bounds (judges nothing)",
           "n_permutations": NPERM, "seed": SEED, "trades": int(len(R)), "weeks": int(nweeks)}
    for dim, cells in (("H", cH), ("D", cD)):
        real = ratio(R, wk, nweeks, oracle_mult(R, grp, cells, ngrp))
        null = []
        for _ in range(NPERM):
            perm = cells.copy()
            for g in range(ngrp):
                ig = np.flatnonzero(grp == g)
                if len(ig) and (cells[ig] >= 0).any():
                    perm[ig] = cells[ig][rng.permutation(len(ig))]
            null.append(ratio(R, wk, nweeks, oracle_mult(R, grp, perm, ngrp)))
        null = np.array(null)
        res[dim] = {"real_ratio": round(float(real), 4), "null_mean": round(float(null.mean()), 4),
                    "null_p05": round(float(np.quantile(null, 0.05)), 4), "null_p50": round(float(np.median(null)), 4),
                    "null_p95": round(float(np.quantile(null, 0.95)), 4),
                    "share_null_at_or_above_real": round(float((null >= real).mean()), 4)}
        print(dim, res[dim], flush=True)
    C.append_trial(res)
    C.jdump(res, os.path.join(C.OUT, "stageC2_oracle_null.json"))


if __name__ == "__main__":
    main()
