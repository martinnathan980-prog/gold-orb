"""Checks of the implementation before the declared runs (no trade of the Xetra rule is simulated here).

1. The rule-based Xetra holidays equal the `holidays` package's XETR calendar on 2016-2021 (declared R03).
2. Reproduction of the FROZEN noise30 (r2/tracks/idx_us/strategy.py, imported read-only) on the us100 in-sample slice:
   this module's grid + state machine, set to the New York clock of noise30 (t0 09:30, O tolerance < 2 min, PC fallback
   to O, NYSE sessions and early closes of idxus_lib), must give exactly the same orders (entry bar, side, stop, exit
   bar).  This shows that the state machine and the grid are the frozen ones; only the clock, the anchors and the
   calendar of declared.json differ.
3. Facts of the Xetra grid on the ger40 in-sample slice: sessions, early closes, skipped sessions, sessions without O or
   without PC.
Output: results/r2/round4/ger40_noise30_xetra/repro_check.json

    PYTHONDONTWRITEBYTECODE=1 python3 repro_check.py
"""
import importlib.util
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import xetra as X  # noqa: E402

NOISE30 = {"lookback": 14, "first_min": 600, "step": 30, "last_min": 930, "exit_min": 955, "vm": 1.0}


def frozen_strategy():
    path = os.path.join(X.LAB, "r2", "tracks", "idx_us", "strategy.py")
    sys.path.insert(0, os.path.dirname(path))
    spec = importlib.util.spec_from_file_location("r4_ger40x_idx_us_strategy", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_us100_is():
    df = pd.read_parquet(os.path.join(X.LAB, "data", "fp", "us100_m1.parquet"), filters=[("ts", "<", X.IS_END)])
    assert df.index.is_monotonic_increasing and df.index.max() < X.IS_END
    return df


def repro_noise30():
    st = frozen_strategy()
    m1 = load_us100_is()
    o_frozen = st.make_orders(m1, rule="noise", **NOISE30)
    gf = st.cm.grid(m1)
    trade_ok = (~gf["half"]) & np.array([d >= st.MIN_DATE for d in gf["dates"]], bool)
    g = X.grid_generic(m1, "America/New_York", 570, 391, 390, list(gf["dates"]), trade_ok, o_late_max=1)
    o_mine = X.make_orders(m1, g=g, require_pc=False, **NOISE30)
    cols = ["entry_i", "side", "stop", "exit_i"]
    a = o_frozen[cols].reset_index(drop=True)
    b = o_mine[cols].reset_index(drop=True)
    same_len = len(a) == len(b)
    eq = same_len and bool((a[["entry_i", "side", "exit_i"]].to_numpy() == b[["entry_i", "side", "exit_i"]].to_numpy()).all()
                           and np.allclose(a["stop"].to_numpy(), b["stop"].to_numpy(), rtol=0, atol=0))
    grid_eq = bool(np.array_equal(gf["P"], g["P"], equal_nan=True) and np.array_equal(gf["EI"], g["EI"])
                   and np.array_equal(gf["O"], g["O"], equal_nan=True))
    return {"frame": "us100 in-sample slice (ts < 2022-01-01)", "orders_frozen": int(len(a)), "orders_this_module": int(len(b)),
            "identical_orders": bool(eq), "identical_grid_P_EI_O": grid_eq,
            "first_entry": str(m1.index[int(a.entry_i.iloc[0])]) if len(a) else None,
            "last_entry": str(m1.index[int(a.entry_i.iloc[-1])]) if len(a) else None}


def xetra_facts():
    m1 = X.load_is()
    g = X.grid(m1)
    d = g["dates"]
    yrs = np.array([x.year for x in d])
    traded = g["trade_ok"] & np.isfinite(g["O"]) & np.isfinite(g["PC"])
    in_window = np.array([x >= X.TRADE_START for x in d])
    out = {"frame_first_bar": str(m1.index[0]), "frame_last_bar": str(m1.index[-1]), "bars": int(len(m1)),
           "sessions_in_frame": int(len(d)), "first_session": str(d[0]), "last_session": str(d[-1]),
           "early_closes_removed": sorted(str(x) for x in g["early"] if d[0] <= x <= d[-1]),
           "skipped_sessions_2014_2021": sorted(str(x) for x in g["skip"] if X.TRADE_START <= x <= d[-1]),
           "sessions_2014_2021": int(in_window.sum()),
           "sessions_2014_2021_without_O_0900_bar": [str(x) for x in d[in_window & ~np.isfinite(g["O"])]],
           "sessions_2014_2021_without_PC": [str(x) for x in d[in_window & ~np.isfinite(g["PC"])]],
           "tradable_sessions_2014_2021": int((traded & in_window).sum()),
           "tradable_sessions_by_year": {int(y): int((traded & (yrs == y)).sum()) for y in range(2014, 2022)}}
    return out


def main():
    res = {"calendar_vs_holidays_package_XETR": {str(k): v for k, v in X.check_calendar_against_package().items()}}
    res["noise30_reproduction_us100"] = repro_noise30()
    res["xetra_grid_facts"] = xetra_facts()
    path = os.path.join(X.RES, "repro_check.json")
    with open(path, "w") as f:
        json.dump(res, f, indent=1, default=str)
    print(json.dumps(res, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main()
