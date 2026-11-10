"""Truncation test: orders built on data cut at random minutes must equal the orders built on the full frame
up to those minutes (same entry bar, side, stop / trail / target distances, decision and scheduled exit time).

Usage: python3 causality_check.py [n_cuts]      (in-sample data only; writes results/r2/crypto/causality.json)
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/gold-orb/lab")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from goldlab import r2  # noqa: E402

import strategy as S  # noqa: E402

OUT = "/home/user/gold-orb/lab/results/r2/crypto"
COLS = ["entry_i", "side", "etype", "stop_dist", "trail", "target_dist", "dec_time", "sched_exit"]


def check(sym, params, n_cuts=12, seed=0, m1=None):
    m1 = r2.load(sym, end="2022-01-01") if m1 is None else m1
    full = S.make_orders(m1, **params)
    rng = np.random.default_rng(seed)
    cuts = sorted(rng.integers(len(m1) // 3, len(m1) - 1, n_cuts).tolist())
    # add cuts right at / around hour boundaries (the delicate cases)
    ts = S.ts_ms(m1)
    for c in list(cuts[:4]):
        hb = int(np.searchsorted(ts, (ts[c] // S.H_MS + 1) * S.H_MS))
        cuts += [hb - 1, hb, hb + 1]
    res = []
    for c in sorted(set(cuts)):
        part = m1.iloc[:c]                       # last row = bar c-1
        o = S.make_orders(part, **params)
        f = full[full.entry_i < c].reset_index(drop=True)
        same_n = len(o) == len(f)
        same = same_n and all(
            (o[k].to_numpy() == f[k].to_numpy()).all() if o[k].dtype.kind in "iM" or k in ("dec_time", "sched_exit")
            else np.allclose(o[k].to_numpy(float), f[k].to_numpy(float), rtol=0, atol=1e-9, equal_nan=True)
            for k in COLS)
        # exit bar: identical whenever the scheduled exit is before the cut
        if same:
            early = (f["sched_exit"] < m1.index[c - 1]).to_numpy()
            same = bool((o["exit_i"].to_numpy()[early] == f["exit_i"].to_numpy()[early]).all())
        res.append({"cut": str(m1.index[c - 1]), "n_trunc": int(len(o)), "n_full_upto": int(len(f)), "equal": bool(same)})
    return res


if __name__ == "__main__":
    n_cuts = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    cfgs = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "causality_cfgs.json")))
    out = {}
    for name, c in cfgs.items():
        for sym in c["syms"]:
            r = check(sym, c["params"], n_cuts)
            r2.free()
            ok = all(x["equal"] for x in r)
            out[f"{name}:{sym}"] = {"all_equal": ok, "cuts": r}
            print(name, sym, "ALL EQUAL" if ok else "MISMATCH", [x for x in r if not x["equal"]][:3], flush=True)
    json.dump(out, open(os.path.join(OUT, "causality.json"), "w"), indent=1)
