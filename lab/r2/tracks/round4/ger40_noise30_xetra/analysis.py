"""Correlation with the ten (declared extra condition, R17), the judge's 'reported, not judged' items (R19) and the
verdict on configuration 1 (PROTOCOL_V3 s.4 single-sleeve bars + the extra condition).  IN SAMPLE ONLY.

The official trades of the ten are read with the filters entry_time < 2022-01-01 AND exit_time < 2022-01-01 in the same
read statement (no 2022 row is materialised).  Output: correlation.json, reported.json, summary.json.

    PYTHONDONTWRITEBYTECODE=1 python3 analysis.py
"""
import json
import math
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import xetra as X  # noqa: E402

TEN = [("noise30", "us100"), ("ocm4", "us100"), ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"),
       ("nq_btc_follow", "btcusd"), ("F1_brk_ridge_filter", "btcusd"), ("F1_brk_ridge_filter", "ethusd"),
       ("GOLD_FRI_PM", "xauusd"), ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd")]
CLUSTER = {"noise30:us100": "us100", "ocm4:us100": "us100", "GOLD_FRI_PM:xauusd": "gold", "donch4h_stop:xauusd": "gold",
           "orb_asia_2d_buf10:xauusd": "gold", "brk72_24h_wd:btcusd": "crypto", "brk72_24h_wd:ethusd": "crypto",
           "F1_brk_ridge_filter:btcusd": "crypto", "F1_brk_ridge_filter:ethusd": "crypto", "nq_btc_follow:btcusd": "crypto"}
W0, W1 = pd.Timestamp("2014-01-01"), pd.Timestamp("2021-12-31")
WEEKS = pd.period_range(W0.to_period("W"), W1.to_period("W"), freq="W")


def official(name, sym):
    path = os.path.join(X.LAB, "results", "r2", "recalc", "trades", f"{name}__{sym}.parquet")
    t = pd.read_parquet(path, columns=["entry_time", "exit_time", "R", "side"],
                        filters=[("entry_time", "<", X.IS_END), ("exit_time", "<", X.IS_END)])
    assert (t.entry_time < X.IS_END).all() and (t.exit_time < X.IS_END).all()
    return t


def weekly(t):
    t = t[(t.entry_time >= pd.Timestamp(W0, tz="UTC")) & (t.entry_time < X.IS_END)]
    w = t.groupby(t.exit_time.dt.tz_convert(None).dt.to_period("W"))["R"].sum()
    return w.reindex(WEEKS, fill_value=0.0)


def rho(a, b):
    return round(float(np.corrcoef(a.to_numpy(), b.to_numpy())[0, 1]), 3) if a.std() > 0 and b.std() > 0 else None


def sharpe(w):
    sd = float(w.std(ddof=1))
    return round(float(w.mean() / sd * math.sqrt(52)), 3) if sd > 0 else None


def grp(t):
    if not len(t):
        return {"n": 0}
    R = t.R.to_numpy()
    g, l = R[R > 0].sum(), -R[R < 0].sum()
    return {"n": int(len(R)), "total_R": round(float(R.sum()), 1), "expectancy_R": round(float(R.mean()), 4),
            "pf": round(float(g / l), 3) if l > 0 else None,
            "t": round(float(R.mean() / (R.std(ddof=1) / math.sqrt(len(R)))), 2) if len(R) > 2 else None}


def correlation(t):
    ws = {f"{n}:{s}": weekly(official(n, s)) for n, s in TEN}
    S = pd.DataFrame(ws)
    ten = S.sum(axis=1)
    m = weekly(t)
    cl = {c: S[[k for k in S if CLUSTER[k] == c]].sum(axis=1) for c in ("us100", "gold", "crypto")}
    r_ten = rho(m, ten)
    return {"convention": "weekly sums of R by calendar week of the exit (pandas W, Monday-Sunday, UTC), every week from "
                          f"{WEEKS[0]} to {WEEKS[-1]} counted (empty weeks = 0), 1 R per trade, FP costs, Pearson",
            "weeks": int(len(WEEKS)), "main_weeks_with_trades": int((m != 0).sum()),
            "corr_with_sum_of_ten": r_ten, "extra_condition_abs_rho_le_0.30": bool(r_ten is not None and abs(r_ten) <= 0.30),
            "corr_with_clusters": {c: rho(m, v) for c, v in cl.items()},
            "corr_with_each_sleeve": {k: rho(m, S[k]) for k in S},
            "ten_trades_2014_2021": {k: int((official(*k.split(":")).entry_time >= pd.Timestamp(W0, tz="UTC")).sum())
                                     for k in S},
            "information_weekly_sharpe": {"main": sharpe(m), "ten": sharpe(ten), "ten_plus_main_1R": sharpe(ten + m)}}


def zsplit(t, o_main):
    """|z| >= 1.5 at the entry check (idx_eu trial 10's z, declared R19) against the rest."""
    m1 = X.load_is()
    g = X.grid(m1)
    checks = np.arange(X.MAIN["first_min"] - X.T0_MIN, X.MAIN["last_min"] - X.T0_MIN + 1, X.MAIN["step"])
    x = g["P"][:, checks] / g["PC"][:, None] - 1
    vol = np.full_like(x, np.nan)
    for j in range(x.shape[1]):
        s = pd.Series(x[:, j])
        sv = s.dropna()
        vol[:, j] = sv.rolling(20, min_periods=20).std().shift(1).reindex(s.index).to_numpy()
    d = t["d"].to_numpy(np.int64)
    j = t["j_in"].to_numpy(np.int64)
    z = x[d, j] / vol[d, j]
    big = np.isfinite(z) & (np.abs(z) >= 1.5)
    small = np.isfinite(z) & (np.abs(z) < 1.5)
    return {"definition": "z = (P(T)/PC - 1) / sample sd (ddof 1) of the same quantity at the same check over the previous "
                          "20 sessions with a value (20 required); T = the entry check",
            "abs_z_ge_1.5": grp(t[big]), "abs_z_lt_1.5": grp(t[small]), "z_undefined": grp(t[~np.isfinite(z)]),
            "abs_z_ge_1.5_long": grp(t[big & (t.side.to_numpy() > 0)]),
            "abs_z_ge_1.5_short": grp(t[big & (t.side.to_numpy() < 0)]),
            "abs_z_ge_1.5_with_trend_of_move": grp(t[big & (np.sign(x[d, j]) == t.side.to_numpy())])}


def main():
    t = pd.read_parquet(os.path.join(X.RES, "trades_01_main.parquet"))
    o = pd.read_parquet(os.path.join(X.RES, "orders_01_main.parquet"))
    lines = {x["id"]: x for x in map(json.loads, open(os.path.join(X.RES, "trials.jsonl")))}
    assert sorted(lines) == list(range(1, 12)), sorted(lines)
    corr = correlation(t)
    with open(os.path.join(X.RES, "correlation.json"), "w") as f:
        json.dump(corr, f, indent=1)
    # ---------------------------------------------------------------- reported, not judged
    yrs = t.entry_time.dt.year
    n30 = official("noise30", "us100")
    n30_days = set(n30.entry_time.dt.tz_convert("America/New_York").dt.date)
    sday = pd.to_datetime(t["sdate"].astype(str)).dt.date
    flat = ~sday.isin(n30_days).to_numpy()
    xber = t.exit_time.dt.tz_convert(X.BER)
    xmin = (xber.dt.hour * 60 + xber.dt.minute).to_numpy()
    kind = np.where(t.reason.to_numpy() == "stop", "stop", np.where(xmin < X.MAIN["exit_min"], "check_exit", "exit_1725"))
    special = set()
    from dateutil.easter import easter
    import datetime as dt
    for y in range(2014, 2022):
        for h in (easter(y) + dt.timedelta(days=50), dt.date(y, 10, 3)) + ((dt.date(2017, 10, 31),) if y == 2017 else ()):
            nxt = [d for d in X.calendar(y)[0] if d > h]
            if nxt:
                special.add(nxt[0])
    after_amb = sday.isin(special).to_numpy()
    gross = pd.read_parquet(os.path.join(X.RES, "gross_01_main.parquet"))
    rep = {"long": grp(t[t.side > 0]), "short": grp(t[t.side < 0]),
           "by_year": {int(y): grp(t[yrs == y]) for y in sorted(yrs.unique())},
           "gross_by_year_R_information": {int(y): round(float(v), 1) for y, v in
                                           gross.groupby(gross.entry_time.dt.year)["R"].sum().items()},
           "z_split_trial10": zsplit(t, o),
           "noise30_us100_flat_days": {"definition": "no official noise30 trade entered on that New York date (official "
                                                     "file rows entry and exit < 2022-01-01)",
                                       "flat": grp(t[flat]), "noise30_traded": grp(t[~flat]),
                                       "noise30_trades_2014_2021": int((n30.entry_time >= pd.Timestamp("2014-01-01", tz="UTC")).sum())},
           "exit_kind": {k: grp(t[kind == k]) for k in ("check_exit", "stop", "exit_1725")},
           "first_session_after_whit_monday_oct3_2017_10_31": grp(t[after_amb]),
           "trades_per_session": {str(k): int(v) for k, v in t.groupby("sdate").size().value_counts().sort_index().items()},
           "same_check_reversals": int((o["entry_i"].isin(o["exit_i"] + 1) & (o["j_in"] >= 0)).sum())}
    with open(os.path.join(X.RES, "reported.json"), "w") as f:
        json.dump(rep, f, indent=1)
    # ---------------------------------------------------------------- verdict on configuration 1
    r1 = lines[1]["result"]
    r10 = lines[10]["result"]
    nb = [lines[i]["result"]["pf"] for i in range(2, 10)]
    yp, yn = (int(v) for v in r1["years_pos"].split("/"))
    crit = [
        ("n >= 250", f"{r1['n']} trades (sessions 2014-2021)", r1["n"] >= 250),
        ("PF >= 1.12", f"PF {r1['pf']}", r1["pf"] >= 1.12),
        ("t >= 2.5", f"t {r1['t_stat']}", r1["t_stat"] >= 2.5),
        (">= 60 % of years positive", f"{r1['years_pos']} years positive", yp >= 0.6 * yn),
        ("PF >= 1.04 with costs x1.5", f"PF {r10['pf']} (config 10, n {r10['n']})", r10["pf"] >= 1.04),
        ("neighbours' median PF >= 1.06", f"median {float(np.median(nb)):.4f} of {nb}", float(np.median(nb)) >= 1.06),
        ("every-signal expectancy > 0", f"{lines[1]['every_signal']['expectancy_R']} R", lines[1]["every_signal"]["expectancy_R"] > 0),
        ("hold <= 5 trading days", f"max hold {r1['max_hold_h']} h", r1["max_hold_h"] <= 5 * 24 + 72),
        ("random-entry null >= 97.5th percentile", f"percentile {lines[11]['result']['percentile']}", lines[11]["result"]["pass"]),
        ("weekly R correlation with the sum of the ten <= 0.30 (2014-2021)", f"rho {corr['corr_with_sum_of_ten']}",
         corr["extra_condition_abs_rho_le_0.30"]),
    ]
    summ = {"rule": "ger40_noise30_xetra", "verdict_on": "configuration 1 (main)", "in_sample_only": True,
            "criteria": [{"criterion": a, "value": b, "pass": bool(c)} for a, b, c in crit],
            "passes_in_sample": bool(all(c for _, _, c in crit)),
            "trials": len(lines),
            "configurations": {i: {"name": lines[i]["name"], "n": lines[i]["result"].get("n"), "pf": lines[i]["result"].get("pf"),
                                   "t": lines[i]["result"].get("t_stat"), "expectancy_R": lines[i]["result"].get("expectancy_R"),
                                   "total_R": lines[i]["result"].get("total_R"), "years_pos": lines[i]["result"].get("years_pos")}
                               for i in range(1, 11)},
            "null": lines[11]["result"], "correlation": {k: corr[k] for k in ("corr_with_sum_of_ten", "corr_with_clusters")},
            "gross_main": lines[1]["gross_information"]}
    with open(os.path.join(X.RES, "summary.json"), "w") as f:
        json.dump(summ, f, indent=1)
    print(json.dumps(corr, indent=1))
    print(json.dumps(rep, indent=1))
    print(json.dumps(summ["criteria"], indent=1), "passes_in_sample:", summ["passes_in_sample"])


if __name__ == "__main__":
    main()
