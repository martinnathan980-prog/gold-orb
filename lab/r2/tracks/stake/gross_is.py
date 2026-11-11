"""Track `stake` (Addendum E): the IN-SAMPLE trades of the ten validated rules WITHOUT costs.

The saved trades (results/r2/recalc/trades) carry the FP Markets costs. Addendum E asks for every figure
"without and with costs", so this script re-runs the ten frozen rules in `gross` mode (mid prices, no spread,
no slippage, no swap) on price frames CUT at 2022-01-15 (r2/tracks/fx/common.py::load_is) and keeps only the
trades entered before 2022-01-01. Nothing from 2022 onward is simulated beyond the two weeks that let
December 2021 trades reach their exit, and nothing after 2022-01-01 is reported.

It also re-runs the `fp` mode on the same cut frames and checks that it reproduces the saved in-sample trades
(a check that the re-run is the same rule).

    python3 lab/r2/tracks/stake/gross_is.py      -> results/r2/stake/trades_gross_is/<name>__<sym>.parquet
                                                    results/r2/stake/gross_is_check.json
"""
import importlib.util
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, LAB)
from goldlab import r2  # noqa: E402
from goldlab.split import cut  # noqa: E402

OUT = os.path.join(LAB, "results", "r2", "stake")
TEN = [("noise30", "us100"), ("ocm4", "us100"), ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"),
       ("nq_btc_follow", "btcusd"), ("F1_brk_ridge_filter", "btcusd"), ("F1_brk_ridge_filter", "ethusd"),
       ("GOLD_FRI_PM", "xauusd"), ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd")]
IS_END = pd.Timestamp("2022-01-01", tz="UTC")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


if __name__ == "__main__":
    recalc = _load(os.path.join(LAB, "r2", "recalc.py"), "r2_recalc")
    fxc = _load(os.path.join(LAB, "r2", "tracks", "fx", "common.py"), "fx_common")
    os.makedirs(os.path.join(OUT, "trades_gross_is"), exist_ok=True)
    want = set(sys.argv[1:])
    path = os.path.join(OUT, "gross_is_check.json")
    check = json.load(open(path)) if os.path.exists(path) else {}
    sl = [s for s in recalc.sleeves() if (s[1], s[2]) in TEN]
    sl.sort(key=lambda s: s[2])
    for track, name, sym, mo, params in sl:
        if want and sym not in want:
            continue
        m1 = fxc.load_is(sym)
        assert m1.index[-1] < pd.Timestamp("2022-01-15", tz="UTC")
        keep = ["side", "entry_time", "exit_time", "entry", "exit", "stop", "reason", "swap", "pnl", "risk", "R", "ret",
                "hold_min"]
        tg = cut(r2.run(sym, mo, params, "gross", True, m1), "is")
        tn = cut(r2.run(sym, mo, params, "fp", True, m1), "is")
        assert (tg.entry_time < IS_END).all() and (tn.entry_time < IS_END).all()
        tg[[c for c in keep if c in tg.columns]].to_parquet(os.path.join(OUT, "trades_gross_is", f"{name}__{sym}.parquet"))
        saved = pd.read_parquet(os.path.join(LAB, "results", "r2", "recalc", "trades", f"{name}__{sym}.parquet"))
        saved = saved[saved.entry_time < IS_END]
        same = len(saved) == len(tn) and bool(np.allclose(saved.R.to_numpy(), tn.R.to_numpy(), atol=1e-9))
        check[f"{name}__{sym}"] = {"n_saved_net": int(len(saved)), "n_rerun_net": int(len(tn)), "rerun_net_identical": same,
                                   "sum_R_saved_net": round(float(saved.R.sum()), 2),
                                   "sum_R_rerun_net": round(float(tn.R.sum()), 2),
                                   "n_gross": int(len(tg)), "sum_R_gross": round(float(tg.R.sum()), 2),
                                   "mean_R_net": round(float(saved.R.mean()), 4), "mean_R_gross": round(float(tg.R.mean()), 4)}
        print(name, sym, check[f"{name}__{sym}"], flush=True)
        json.dump(check, open(path, "w"), indent=1)
