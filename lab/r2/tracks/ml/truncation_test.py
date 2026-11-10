"""Causality proof: orders built on data cut at random times must equal the orders built on the full
in-sample frame up to those times (run: python3 truncation_test.py)."""
import json
import sys

import numpy as np

sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/ml")
from research import *  # noqa

GEN = {"stop_k": 2.0, "hold_h": 13.0}
CONFIGS = {
    "baseline": GEN,
    "model_frozen": {**GEN, "model": "B1_ridge_full.json", "q": "0.5"},
    "model_oof": {**GEN, "model": "B1_ridge_full.json", "oof": True, "q": "0.5"},
}
out = {}
rng = np.random.default_rng(7)
for sym in sys.argv[1:] or ["btcusd", "ethusd", "xauusd"]:
    m1 = is_frame(sym)
    N = len(m1)
    cuts = sorted(rng.integers(int(N * 0.35), N - 1, 4).tolist())
    for name, p in CONFIGS.items():
        full = S.make_orders(m1, **p)
        for k in cuts:
            part = S.make_orders(m1.iloc[:k], **p)
            ref = full[full.entry_i < k].reset_index(drop=True)
            same_n = len(ref) == len(part)
            ok_cols = {}
            if same_n:
                for c in ("entry_i", "side", "cid"):
                    ok_cols[c] = bool((ref[c].to_numpy() == part[c].to_numpy()).all())
                ok_cols["stop_dist"] = bool(np.allclose(ref["stop_dist"].to_numpy(), part["stop_dist"].to_numpy(), rtol=0, atol=1e-9))
                inner = ref["exit_i"].to_numpy() < k - 60          # exits that fall inside the cut data
                ok_cols["exit_i"] = bool((ref["exit_i"].to_numpy()[inner] == part["exit_i"].to_numpy()[inner]).all())
            res = {"cut_time": str(m1.index[k]), "orders_before_cut": int(len(ref)), "orders_on_cut_data": int(len(part)),
                   "identical": bool(same_n and all(ok_cols.values())), "cols": ok_cols}
            out.setdefault(sym, {}).setdefault(name, []).append(res)
            print(sym, name, res)
    r2.free()
json.dump(out, open(os.path.join(RES, "truncation_test.json"), "w"), indent=1)
print("ALL IDENTICAL:", all(r["identical"] for s in out.values() for c in s.values() for r in c))
