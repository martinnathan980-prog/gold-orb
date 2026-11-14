"""Weekly R correlation of the main with the sum of the ten sleeves, with each cluster and with each sleeve, 2014-2021
(declared.json D15), in sample only. Exactly the convention of r2/tracks/round4/fomc_cycle/correlation.py: the official
trades of the ten are read with the filter entry_time < 2022-01-01 in the read statement and a trade exiting in 2022 is
dropped; weekly sums of R by exit week (W-SUN, UTC); every calendar week from the week of 2014-01-01 to the week of
2021-12-31 counted (a week without an exit = 0); Pearson.
Output: results/r2/round5/gold_reopen/correlation.json
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

TEN = [("noise30", "us100"), ("ocm4", "us100"), ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"),
       ("F1_brk_ridge_filter", "btcusd"), ("F1_brk_ridge_filter", "ethusd"), ("nq_btc_follow", "btcusd"),
       ("GOLD_FRI_PM", "xauusd"), ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd")]
CLUSTERS = {"us100 opening momentum (ocm4 + noise30)": [("ocm4", "us100"), ("noise30", "us100")],
            "gold (donch4h_stop + orb_asia_2d_buf10 + GOLD_FRI_PM)": [("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd"),
                                                                     ("GOLD_FRI_PM", "xauusd")],
            "crypto (brk72_24h_wd x2 + F1_brk_ridge_filter x2 + nq_btc_follow)": [
                ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"), ("F1_brk_ridge_filter", "btcusd"),
                ("F1_brk_ridge_filter", "ethusd"), ("nq_btc_follow", "btcusd")]}
WEEKS = pd.period_range(pd.Timestamp("2014-01-01").to_period("W"), pd.Timestamp("2021-12-31").to_period("W"), freq="W")


def official(name, sym):
    t = pd.read_parquet(os.path.join(C.LAB, "results", "r2", "recalc", "trades", f"{name}__{sym}.parquet"),
                        columns=["entry_time", "exit_time", "R"], filters=[("entry_time", "<", C.CUT)])
    assert (t.entry_time < C.CUT).all()
    return t[t.exit_time < C.CUT]


def weekly(t):
    w = t.groupby(t.exit_time.dt.tz_convert(None).dt.to_period("W"))["R"].sum()
    return w.reindex(WEEKS, fill_value=0.0)


def main():
    decl, sha = C.declared()
    rho = lambda a, b: round(float(np.corrcoef(a.to_numpy(), b.to_numpy())[0, 1]), 3)  # noqa: E731
    out = {"declared_sha256": sha, "period_weeks": f"{WEEKS[0]} .. {WEEKS[-1]}", "n_weeks": int(len(WEEKS)),
           "convention": "weekly sums of R by exit week (W-SUN, UTC), every calendar week counted, Pearson; official trades "
                         "read with entry_time < 2022-01-01, exits in 2022 dropped (as round4/fomc_cycle/correlation.py)"}
    sl = {f"{n}:{s}": official(n, s) for n, s in TEN}
    ws = {k: weekly(v) for k, v in sl.items()}
    ten = sum(ws.values())
    out["ten_trades_read"] = {k: int(len(v)) for k, v in sl.items()}
    t = pd.read_parquet(os.path.join(C.OUT, "trades_01_main.parquet"))
    assert (t.entry_time < C.CUT).all() and (t.exit_time < C.CUT).all()
    w = weekly(t)
    wk_of_exit = t.exit_time.dt.tz_convert(None).dt.to_period("W")
    out["main"] = {"weeks_with_an_exit": int((w != 0).sum()), "trades_exiting_in_these_weeks": int(wk_of_exit.isin(WEEKS).sum()),
                   "corr_with_sum_of_ten": rho(w, ten),
                   "corr_with_clusters": {cn: rho(w, sum(ws[f"{a}:{b}"] for a, b in mem)) for cn, mem in CLUSTERS.items()},
                   "corr_with_each_sleeve": {k: rho(w, v) for k, v in ws.items()}}
    out["bar"] = "|rho with the sum of the ten| <= 0.30 (D15)"
    out["pass"] = bool(abs(out["main"]["corr_with_sum_of_ten"]) <= 0.30)
    C.jdump(out, os.path.join(C.OUT, "correlation.json"))
    print("main", out["main"]["corr_with_sum_of_ten"], out["main"]["corr_with_clusters"])
    print("  ", out["main"]["corr_with_each_sleeve"])


if __name__ == "__main__":
    main()
