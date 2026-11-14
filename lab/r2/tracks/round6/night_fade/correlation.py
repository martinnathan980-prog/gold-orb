"""Weekly R correlation of the main configuration of night_fade with the sum of the ten sleeves, with each cluster and
with each sleeve, 2014-2021 (PROTOCOL_V3 Addendum L: Addendum K's convention, L28), in sample only.
Exactly the convention of r2/tracks/round5/gold_reopen/correlation.py: the official trades of the ten are read with the
filter entry_time < 2022-01-01 in the read statement and a trade exiting in 2022 is dropped; weekly sums of R by exit week
(W-SUN periods of the UTC exit time); every calendar week from the week of 2014-01-01 to the week of 2021-12-31 counted
(418 weeks; a week without an exit = 0); Pearson. Bar: |rho| <= 0.30.
Output: results/r2/round6/night_fade/correlation.json
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
TEN_DIR = os.path.join(C.LAB, "results", "r2", "recalc", "trades")


def official(name, sym, ten_dir=TEN_DIR):
    t = pd.read_parquet(os.path.join(ten_dir, f"{name}__{sym}.parquet"),
                        columns=["entry_time", "exit_time", "R"], filters=[("entry_time", "<", C.CUT)])
    assert (t.entry_time < C.CUT).all()
    return t[t.exit_time < C.CUT]


def weekly(t):
    w = t.groupby(t.exit_time.dt.tz_convert(None).dt.to_period("W"))["R"].sum()
    return w.reindex(WEEKS, fill_value=0.0)


def rho_raw(a, b):
    """Pearson rho of two weekly series, unrounded (NaN -> None: a constant series has no correlation)."""
    r = float(np.corrcoef(a.to_numpy(), b.to_numpy())[0, 1])
    return None if np.isnan(r) else r


def correlate(main_trades, ten_frames):
    """Correlations of the main's weekly R with the ten (dict 'name:sym' -> trades). The bar is read on the unrounded
    rho ('corr_with_sum_of_ten_raw'); the rounded figures are for display (review R6-2)."""
    rho = lambda a, b: None if rho_raw(a, b) is None else round(rho_raw(a, b), 4)  # noqa: E731
    assert len(WEEKS) == 418
    ws = {k: weekly(v) for k, v in ten_frames.items()}
    ten = sum(ws.values())
    t = main_trades
    assert (t.entry_time < C.CUT).all() and (t.exit_time < C.CUT).all()
    w = weekly(t)
    wk_of_exit = t.exit_time.dt.tz_convert(None).dt.to_period("W")
    out = {"period_weeks": f"{WEEKS[0]} .. {WEEKS[-1]}", "n_weeks": int(len(WEEKS)),
           "convention": "weekly sums of R by exit week (W-SUN, UTC), every calendar week counted, Pearson; official trades "
                         "read with entry_time < 2022-01-01, exits in 2022 dropped (as round5/gold_reopen/correlation.py)",
           "ten_trades_read": {k: int(len(v)) for k, v in ten_frames.items()},
           "main": {"weeks_with_an_exit": int((w != 0).sum()), "trades_exiting_in_these_weeks": int(wk_of_exit.isin(WEEKS).sum()),
                    "corr_with_sum_of_ten": rho(w, ten), "corr_with_sum_of_ten_raw": rho_raw(w, ten),
                    "corr_with_clusters": {cn: rho(w, sum(ws[f"{a}:{b}"] for a, b in mem)) for cn, mem in CLUSTERS.items()},
                    "corr_with_each_sleeve": {k: rho(w, v) for k, v in ws.items()}},
           "bar": "|rho with the sum of the ten| <= 0.30 (read on the unrounded rho)"}
    r = out["main"]["corr_with_sum_of_ten_raw"]
    out["pass"] = bool(r is not None and abs(r) <= 0.30)
    return out


def main():
    decl, sha = C.declared()
    ten = {f"{n}:{s}": official(n, s) for n, s in TEN}
    t = pd.read_parquet(os.path.join(C.OUT, "trades_01_main_base.parquet"))
    out = correlate(t, ten)
    out["declared_sha256"] = sha
    C.jdump(out, os.path.join(C.OUT, "correlation.json"))
    print("main", out["main"]["corr_with_sum_of_ten"], out["main"]["corr_with_clusters"])


if __name__ == "__main__":
    main()
