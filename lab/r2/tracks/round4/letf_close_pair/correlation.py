"""Reported, not judged (declared.json R20): weekly R correlation of the main configuration with IDXRS_1000 and with
noise30 (the judge's REPORTED line), and with the sum of the ten and each cluster, 2014-2021. Every trades file is read
with the filter entry_time < 2022-01-01 in the same statement; a trade exiting in 2022 is dropped.
Writes results/r2/round4/letf_close_pair/correlation.json."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

TEN = [("noise30", "us100"), ("ocm4", "us100"), ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"),
       ("F1_brk_ridge_filter", "btcusd"), ("F1_brk_ridge_filter", "ethusd"), ("nq_btc_follow", "btcusd"),
       ("GOLD_FRI_PM", "xauusd"), ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd")]
CLUSTERS = {"us100 (ocm4 + noise30)": [("ocm4", "us100"), ("noise30", "us100")],
            "gold (donch4h_stop + orb_asia_2d_buf10 + GOLD_FRI_PM)": [("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd"),
                                                                     ("GOLD_FRI_PM", "xauusd")],
            "crypto (brk72_24h_wd x2 + F1_brk_ridge_filter x2 + nq_btc_follow)": [
                ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"), ("F1_brk_ridge_filter", "btcusd"),
                ("F1_brk_ridge_filter", "ethusd"), ("nq_btc_follow", "btcusd")]}
WEEKS = pd.period_range(pd.Timestamp("2014-01-01").to_period("W"), pd.Timestamp("2021-12-31").to_period("W"), freq="W")
IDXRS = os.path.join(C.LAB, "results", "r2", "round4", "idxrs_1000", "trades_01_main.parquet")


def read_is(path):
    t = pd.read_parquet(path, columns=["entry_time", "exit_time", "R"], filters=[("entry_time", "<", C.CUT)])
    assert (t.entry_time < C.CUT).all()
    return t[t.exit_time < C.CUT]


def official(name, sym):
    return read_is(os.path.join(C.LAB, "results", "r2", "recalc", "trades", f"{name}__{sym}.parquet"))


def weekly(t):
    w = t.groupby(t.exit_time.dt.tz_convert(None).dt.to_period("W"))["R"].sum()
    return w.reindex(WEEKS, fill_value=0.0)


def daily(t):
    return t.groupby(t.exit_time.dt.tz_convert(C.NY).dt.date)["R"].sum()


def main():
    pair = pd.read_parquet(os.path.join(C.OUT, "trades_01_main.parquet"))
    wp = weekly(pair)
    sl = {f"{n}:{s}": official(n, s) for n, s in TEN}
    ws = {k: weekly(v) for k, v in sl.items()}
    idx = read_is(IDXRS)
    wi = weekly(idx)
    rho = lambda a, b: round(float(np.corrcoef(a.to_numpy(), b.to_numpy())[0, 1]), 3)
    out = {"period_weeks": f"{WEEKS[0]} .. {WEEKS[-1]}", "n_weeks": int(len(WEEKS)),
           "pair_weeks_with_trades": int((wp != 0).sum()),
           "convention": "weekly sums of R by exit week (W-SUN, UTC), every calendar week counted (0 without a trade), "
                         "Pearson; trades read with entry_time < 2022-01-01"}
    out["reported_by_the_judge"] = {
        "corr_with_IDXRS_1000_main": rho(wp, wi), "IDXRS_1000_trades_2014_2021": int(len(idx)),
        "corr_with_noise30": rho(wp, ws["noise30:us100"])}
    out["corr_with_sum_of_ten"] = rho(wp, sum(ws.values()))
    out["corr_with_clusters"] = {cn: rho(wp, sum(ws[f"{n}:{s}"] for n, s in mem)) for cn, mem in CLUSTERS.items()}
    out["corr_with_each_sleeve"] = {k: {"rho": rho(wp, v), "weeks_with_trades": int((v != 0).sum()),
                                        "trades_2014_2021": int(len(sl[k]))} for k, v in ws.items()}
    # information: daily (New York exit date) correlation with noise30 and IDXRS_1000 on the days the pair traded
    dp = daily(pair)
    info = {}
    for nm, tt in (("noise30", sl["noise30:us100"]), ("IDXRS_1000", idx), ("us100 cluster", pd.concat([sl["ocm4:us100"], sl["noise30:us100"]]))):
        du = daily(tt)
        j = pd.concat([dp.rename("pair"), du.rename("other")], axis=1).fillna(0.0).loc[dp.index]
        info[nm] = {"n_pair_days": int(len(j)), "corr_on_pair_days": round(float(j.corr().iloc[0, 1]), 3),
                    "share_of_pair_days_with_a_trade_of_it": round(float((j.other != 0).mean()), 3)}
    out["information_daily_on_pair_days"] = info
    C.jdump(out, os.path.join(C.OUT, "correlation.json"))
    print(out["reported_by_the_judge"], "ten:", out["corr_with_sum_of_ten"], out["corr_with_clusters"])
    print({k: v["rho"] for k, v in out["corr_with_each_sleeve"].items()})
    print(info)


if __name__ == "__main__":
    main()
