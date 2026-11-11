"""Truncation test: orders built on data cut at random times must equal the orders built on the whole
in-sample frame, for every order decided before the cut."""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")))
from goldlab import r2  # noqa: E402
import strategy as S  # noqa: E402

CONFIGS = {
    "market": {},
    "limit": {"entry": "limit"},
    "confirm_m5_close_mid15": {"entry": "confirm", "tf": 5, "tgt": "mid15", "stretch15": (1.0, 99), "in_band": True},
    "confirm_m15_wick_prev": {"entry": "confirm", "tf": 15, "pattern": "wick", "window": 2, "tgt": "prev"},
    "confirm_m15_engulf": {"entry": "confirm", "tf": 15, "pattern": "engulf", "window": 3},
    "fail_m1_hold60": {"entry": "confirm", "tf": 1, "pattern": "fail", "window": 15, "hold": 60},
    "conf_any_div": {"conf": "any"},
    "div": {"div": True},
    "wm": {"fam": "WM"},
    "placebo3": {"placebo": 3},
    "range_exhausted_1.5": {"range_used": (1.5, 99)},
    "all_lines_range1.5": {"fam": "ALL", "range_used": (1.5, 99)},
    "asia_squeeze_hold240": {"ny": (18, 3), "squeeze": (0, 1.0), "hold": 240, "tgt": None},
}
CONFIGS.update({"finalist_" + k: v for k, v in S.FINALISTS.items()})


def main(n_cuts=6, seed=7):
    m1 = r2.load("xauusd", end="2022-01-01")
    rng = np.random.default_rng(seed)
    cuts = np.sort(rng.integers(600_000, len(m1) - 5000, n_cuts))
    full = {k: S.make_orders(m1, **p) for k, p in CONFIGS.items()}
    out = []
    for cut in cuts:
        sub = m1.iloc[:cut]
        for k, p in CONFIGS.items():
            S._CTX.clear()
            a = S.make_orders(sub, **p)
            b = full[k]
            # orders whose entry bar exists in the cut frame with one more bar behind it
            a = a[a.entry_i < cut - 1].reset_index(drop=True)
            b = b[b.entry_i < cut - 1].reset_index(drop=True)
            same = len(a) == len(b)
            if same and len(a):
                for col in ("entry_i", "side", "etype", "touch_i", "dec_i"):
                    same &= bool((a[col].to_numpy() == b[col].to_numpy()).all())
                for col in ("stop", "target", "level"):
                    same &= bool(np.allclose(a[col].to_numpy(float), b[col].to_numpy(float), equal_nan=True, rtol=0, atol=1e-9))
                same &= bool((np.minimum(a.exit_i, cut - 1).to_numpy() == np.minimum(b.exit_i, cut - 1).to_numpy()).all())
            out.append({"cut": str(m1.index[cut]), "config": k, "orders_before_cut": int(len(b)), "identical": bool(same)})
            print(out[-1], flush=True)
    S._CTX.clear()
    json.dump(out, open(os.path.join(S.LAB, "results", "pivbb", "bounce", "causality.json"), "w"), indent=1)
    print("ALL IDENTICAL:", all(r["identical"] for r in out))


if __name__ == "__main__":
    main()
