"""Weekly correlation of the main configuration with the ten sleeves, 2014-2021 (in sample only).

Weekly series = sum of R per calendar week of the EXIT (Monday-Sunday, UTC; the breadth lens's convention), every
calendar week from the week of 2014-01-01 to the week of 2021-12-31 counted (empty weeks = 0), trades entered
2014-01-01 .. 2021-12-31.  The official trades of the ten are read with the filter entry_time < 2022-01-01 in the same
read statement.  Clusters: us100 = noise30 + ocm4; gold = GOLD_FRI_PM + donch4h_stop + orb_asia_2d_buf10;
crypto = brk72_24h_wd (btc, eth) + F1_brk_ridge_filter (btc, eth) + nq_btc_follow.
Also: the same on the ten's common window 2018-02 .. 2021-12, the main's weekly Sharpe, and the ten's weekly Sharpe
with the main added at 1 R per trade (information).

    PYTHONDONTWRITEBYTECODE=1 python3 correlation.py
"""
import math
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import wkfade as W  # noqa: E402

TEN = [("noise30", "us100"), ("ocm4", "us100"), ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"),
       ("nq_btc_follow", "btcusd"), ("F1_brk_ridge_filter", "btcusd"), ("F1_brk_ridge_filter", "ethusd"),
       ("GOLD_FRI_PM", "xauusd"), ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd")]
CLUSTER = {"noise30:us100": "us100", "ocm4:us100": "us100", "GOLD_FRI_PM:xauusd": "gold", "donch4h_stop:xauusd": "gold",
           "orb_asia_2d_buf10:xauusd": "gold", "brk72_24h_wd:btcusd": "crypto", "brk72_24h_wd:ethusd": "crypto",
           "F1_brk_ridge_filter:btcusd": "crypto", "F1_brk_ridge_filter:ethusd": "crypto",
           "nq_btc_follow:btcusd": "crypto"}


def official(name, sym):
    path = os.path.join(W.LAB, "results", "r2", "recalc", "trades", f"{name}__{sym}.parquet")
    t = pd.read_parquet(path, filters=[("entry_time", "<", W.IS_END)])
    assert (t.entry_time < W.IS_END).all()
    return t


def weekly(t, start, end):
    weeks = pd.period_range(start.tz_convert(None), (end - pd.Timedelta(seconds=1)).tz_convert(None), freq="W")
    if t is None or not len(t):
        return pd.Series(0.0, index=weeks)
    t = t[(t.entry_time >= start) & (t.entry_time < end)]
    w = t.groupby(t.exit_time.dt.tz_convert(None).dt.to_period("W"))["R"].sum()
    return w.reindex(weeks, fill_value=0.0)


def sharpe(w):
    sd = float(w.std(ddof=1))
    return float(w.mean() / sd * math.sqrt(52)) if sd > 0 else float("nan")


def corr(a, b):
    return round(float(np.corrcoef(a, b)[0, 1]), 3) if a.std() > 0 and b.std() > 0 else None


def block(main, start, end):
    m = weekly(main, start, end)
    S = pd.DataFrame({f"{n}:{s}": weekly(official(n, s), start, end) for n, s in TEN})
    ten = S.sum(axis=1)
    cl = {c: S[[k for k in S if CLUSTER[k] == c]].sum(axis=1) for c in ("us100", "gold", "crypto")}
    out = {"weeks": int(len(m)), "main_trades": int(((main.entry_time >= start) & (main.entry_time < end)).sum()),
           "main_total_R": round(float(m.sum()), 1), "main_weekly_sharpe_ann": round(sharpe(m), 3),
           "corr_sum_of_ten": corr(m, ten), "corr_clusters": {c: corr(m, v) for c, v in cl.items()},
           "corr_sleeves": {k: corr(m, S[k]) for k in S},
           "ten_weekly_sharpe_ann": round(sharpe(ten), 3), "ten_total_R": round(float(ten.sum()), 1),
           "ten_plus_main_weekly_sharpe_ann": round(sharpe(ten + m), 3),
           "delta_sharpe_adding_main_at_1R": round(sharpe(ten + m) - sharpe(ten), 3),
           "ten_trades": int(sum(((official(n, s).entry_time >= start) & (official(n, s).entry_time < end)).sum()
                                 for n, s in TEN))}
    return out


def main():
    t = pd.read_parquet(os.path.join(W.RES, "trades_01_main.parquet"))
    assert (t.entry_time < W.IS_END).all()
    res = {"convention": "sum of R per calendar week of the exit (Mon-Sun, UTC), every week counted, 1 R per trade, "
                         "FP costs; Pearson correlation of weekly sums",
           "window_2014_2021": block(t, pd.Timestamp("2014-01-01", tz="UTC"), W.IS_END),
           "window_2018_02_2021 (common window of the ten, information)": block(t, pd.Timestamp("2018-02-01", tz="UTC"),
                                                                              W.IS_END)}
    W.jdump(res, os.path.join(W.RES, "correlation.json"))
    import json
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
