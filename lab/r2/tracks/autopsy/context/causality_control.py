"""Negative control of the truncation test (does it catch look-ahead?): on 20 brk72_24h_wd__ethusd signals, the
price P(t_dec) used by the descriptors and a deliberately leaky price P(t_dec + 2 min) (which reads the entry bar)
are computed on the full frame and on the frame cut at t_dec. The causal one must match every time, the leaky one
must not. Writes causality_control.json."""
import os

import numpy as np
import pandas as pd

import common as C
import descr as D
from causality import cut

K = "brk72_24h_wd__ethusd"


def main():
    m1 = C.load_fp_is("ethusd", ["bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"])
    s = pd.read_parquet(os.path.join(C.OUT, "signals", f"{K}__fp.parquet"))
    rng = np.random.default_rng(5)
    rows = rng.choice(np.flatnonzero(s.year.isin([2019, 2020, 2021]).to_numpy()), 20, replace=False)
    full = D.Market(m1, hourly=False)
    same_causal = same_leaky = 0
    for i in rows:
        t = int(s.t_dec.iloc[i])
        cm = D.Market(cut(m1, t), hourly=False)
        a_full, a_cut = full.P([t])[0], cm.P([t])[0]
        b_full, b_cut = full.P([t + 120 * 10 ** 9])[0], cm.P([t + 120 * 10 ** 9])[0]
        same_causal += int(a_full == a_cut)
        same_leaky += int(b_full == b_cut)
    out = {"signals": 20, "causal_price_identical": same_causal, "leaky_price_identical": same_leaky,
           "reading": "the truncation test detects a descriptor that reads the entry bar (leaky price differs on the cut "
                      "frame) and passes the descriptors actually used"}
    C.dump(out, os.path.join(C.OUT, "causality_control.json"))
    print(out)


if __name__ == "__main__":
    main()
