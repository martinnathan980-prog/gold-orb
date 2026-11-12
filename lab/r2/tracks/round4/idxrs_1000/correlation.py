"""Weekly R correlation of the main configuration with ocm4 + noise30 (declared extra condition, |rho| <= 0.30), with
the sum of the ten and with each cluster, 2014-2021 (declared.json R15). The official trades of the ten are read with
the filter entry_time < 2022-01-01 in the same statement; a trade exiting in 2022 is dropped."""
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


def official(name, sym):
    t = pd.read_parquet(os.path.join(C.LAB, "results", "r2", "recalc", "trades", f"{name}__{sym}.parquet"),
                        columns=["entry_time", "exit_time", "R"], filters=[("entry_time", "<", C.CUT)])
    assert (t.entry_time < C.CUT).all()
    return t[t.exit_time < C.CUT]


def weekly(t):
    w = t.groupby(t.exit_time.dt.tz_convert(None).dt.to_period("W"))["R"].sum()
    return w.reindex(WEEKS, fill_value=0.0)


def daily(t):
    return t.groupby(t.exit_time.dt.tz_convert("America/New_York").dt.date)["R"].sum()


def main():
    pair = pd.read_parquet(os.path.join(C.OUT, "trades_01_main.parquet"))
    wp = weekly(pair)
    sl = {f"{n}:{s}": official(n, s) for n, s in TEN}
    ws = {k: weekly(v) for k, v in sl.items()}
    rho = lambda a, b: round(float(np.corrcoef(a.to_numpy(), b.to_numpy())[0, 1]), 3)
    out = {"period_weeks": f"{WEEKS[0]} .. {WEEKS[-1]}", "n_weeks": int(len(WEEKS)),
           "pair_weeks_with_trades": int((wp != 0).sum()), "convention": "weekly sums of R by exit week (W-SUN, UTC), "
           "every calendar week counted, Pearson; official trades read with entry_time < 2022-01-01"}
    us100 = ws["ocm4:us100"] + ws["noise30:us100"]
    r_us100 = rho(wp, us100)
    out["declared_condition"] = {"corr_with_ocm4_plus_noise30": r_us100, "bar_abs_le": 0.30, "pass": bool(abs(r_us100) <= 0.30)}
    ten = sum(ws.values())
    out["corr_with_sum_of_ten"] = rho(wp, ten)
    out["corr_with_clusters"] = {cn: rho(wp, sum(ws[f"{n}:{s}"] for n, s in mem)) for cn, mem in CLUSTERS.items()}
    out["corr_with_each_sleeve"] = {k: {"rho": rho(wp, v), "weeks_with_trades": int((v != 0).sum()),
                                        "trades_2014_2021": int(len(sl[k]))} for k, v in ws.items()}
    # information: daily (New York exit date) correlation with the us100 cluster on days the pair traded, and overlap
    dp = daily(pair)
    du = daily(pd.concat([sl["ocm4:us100"], sl["noise30:us100"]]))
    j = pd.concat([dp.rename("pair"), du.rename("us100")], axis=1).fillna(0.0)
    jj = j.loc[dp.index]
    out["information_daily_on_pair_days"] = {"n_days": int(len(jj)), "corr": round(float(jj.corr().iloc[0, 1]), 3),
                                             "share_of_pair_days_with_an_us100_sleeve_trade": round(float((jj.us100 != 0).mean()), 3)}
    C.jdump(out, os.path.join(C.OUT, "correlation.json"))
    print(out["declared_condition"], "ten:", out["corr_with_sum_of_ten"], out["corr_with_clusters"])
    print({k: v["rho"] for k, v in out["corr_with_each_sleeve"].items()})
    print(out["information_daily_on_pair_days"])


if __name__ == "__main__":
    main()
