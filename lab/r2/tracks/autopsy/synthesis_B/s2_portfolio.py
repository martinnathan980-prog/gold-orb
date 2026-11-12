"""synthesis_B step 2: the portfolios P0..P3 of declared.json and the descriptive loss anatomy. IN SAMPLE ONLY.

Reads only the trades this synthesis simulated in step 1 (out/*.parquet, all entered before 2022 and closed inside
their in-sample slice). Constant stake: every trade risks 1 R; each sleeve one position at a time; no other cap.
Window: entries 2018-02-01 .. 2021-12-31. Weeks: FP server weeks (server time = New York + 7 h, Monday-Sunday),
booked at the exit time; weeks with no exit count as 0.

    NUMBA_CACHE_DIR=/tmp/numba_synthesis_B PYTHONDONTWRITEBYTECODE=1 python3 s2_portfolio.py
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common as C  # noqa: E402

H1 = (C.COMMON_START, pd.Timestamp("2020-01-01", tz="UTC"))
H2 = (pd.Timestamp("2020-01-01", tz="UTC"), C.IS_END)


def server_time(ts):
    return pd.DatetimeIndex(ts).tz_convert(C.NY).tz_localize(None) + pd.Timedelta(hours=7)


def week_id(ts):
    d = server_time(ts).values.astype("datetime64[D]").astype(np.int64)
    return (d + 3) // 7                                  # 1970-01-01 is a Thursday: weeks start on Monday


def sleeve_sets(mode):
    ten = {C.key(n, s): C.load_trades(f"ref__{n}__{s}__{mode}") for n, s in C.SLEEVES}
    k1 = C.load_trades(f"var__brk72_24h_wd_riskbp__ethusd__{mode}")
    n1 = C.load_trades(f"new__orb_asia_2d_buf10__ethusd__{mode}")
    n2 = C.load_trades(f"new__orb_asia_2d_buf10__btcusd__{mode}")
    i3 = C.load_trades(f"new__donch4h_stop__ethusd__{mode}")
    p0 = dict(ten)
    p1 = dict(ten)
    p1["brk72_24h_wd__ethusd"] = k1
    p2 = dict(p1)
    p2["NEW_orb_asia_2d_buf10__ethusd"] = n1
    p2["NEW_orb_asia_2d_buf10__btcusd"] = n2
    p3 = dict(p2)
    p3["INFO_donch4h_stop__ethusd"] = i3
    return {"P0": p0, "P1": p1, "P2": p2, "P3": p3}


def book(per):
    fr = []
    for k, t in per.items():
        w = C.window(t)
        fr.append(pd.DataFrame({"sleeve": k, "entry_time": w.entry_time.to_numpy(), "exit_time": w.exit_time.to_numpy(),
                                "R": w.R.to_numpy(float)}))
    d = pd.concat(fr, ignore_index=True)
    d["entry_time"] = pd.to_datetime(d.entry_time, utc=True)
    d["exit_time"] = pd.to_datetime(d.exit_time, utc=True)
    return d.sort_values(["exit_time", "entry_time", "sleeve"], kind="stable").reset_index(drop=True)


def max_dd(x):
    c = np.r_[0.0, np.cumsum(np.asarray(x, float))]
    return float((np.maximum.accumulate(c) - c).max())


def longest_run(neg):
    best = cur = 0
    for v in neg:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return int(best)


def metrics(d):
    R = d.R.to_numpy(float)
    s = C.sstats(R)
    s["eur_per_100_risked"] = round(100 * s["exp"], 2)
    wk = week_id(d.exit_time)
    w0 = int(week_id(pd.DatetimeIndex([C.COMMON_START]))[0])
    w1 = int(week_id(pd.DatetimeIndex([C.IS_END - pd.Timedelta(minutes=1)]))[0])
    ws = pd.Series(R).groupby(wk).sum().reindex(range(w0, w1 + 1), fill_value=0.0)
    day = server_time(d.exit_time).normalize()
    ds = pd.Series(R).groupby(day).sum()
    s.update({
        "max_dd_R_trade_by_trade": round(max_dd(R), 2),
        "max_dd_R_weekly": round(max_dd(ws.to_numpy()), 2),
        "worst_week_R": round(float(ws.min()), 2), "best_week_R": round(float(ws.max()), 2),
        "weeks": int(len(ws)), "winning_weeks_pct": round(float((ws > 0).mean() * 100), 1),
        "losing_weeks_pct": round(float((ws < 0).mean() * 100), 1),
        "longest_losing_run_weeks": longest_run((ws < 0).to_numpy()),
        "week_mean_R": round(float(ws.mean()), 3), "week_sd_R": round(float(ws.std(ddof=1)), 3),
        "week_mean_over_sd": round(float(ws.mean() / ws.std(ddof=1)), 4),
        "weekly_sharpe_annualised": round(float(ws.mean() / ws.std(ddof=1) * np.sqrt(52)), 3),
        "worst_day_R": round(float(ds.min()), 2),
        "R_per_year": round(float(R.sum() / ((C.IS_END - C.COMMON_START).days / 365.25)), 1),
    })
    by_y = {int(y): C.sstats(g.R) for y, g in d.groupby(d.entry_time.dt.year)}
    s["by_year"] = {y: {k: v[k] for k in ("n", "exp", "total", "win", "avg_loss", "pf")} for y, v in by_y.items()}
    for nm, (a, b) in (("half_2018_02_2019_12", H1), ("half_2020_2021", H2)):
        x = d[(d.entry_time >= a) & (d.entry_time < b)]
        hs = C.sstats(x.R)
        s[nm] = {k: hs[k] for k in ("n", "exp", "total", "win", "avg_loss", "pf", "mean_over_sd")}
    s["by_sleeve"] = {k: {kk: v[kk] for kk in ("n", "exp", "total")} for k, v in
                      ((k, C.sstats(g.R)) for k, g in d.groupby("sleeve"))}
    return s


def anatomy(per_fp):
    """Descriptive, no variant: where the losses come from in the ten reference sleeves (window, FP)."""
    out = {}
    allw = []
    for k, t in per_fp.items():
        w = C.window(t).copy()
        w["mfe_R"] = w.mfe / w.risk
        w["mae_R"] = w.mae / w.risk
        w["sleeve"] = k
        allw.append(w)
    allw.append(pd.concat(allw, ignore_index=True).assign(sleeve="ALL_TEN"))
    for w in allw:
        k = w.sleeve.iloc[0]
        los, win = w[w.R < 0], w[w.R > 0]
        full = los[los.R <= -0.9]
        gl = -los.R.sum()
        lo_sorted = np.sort(los.R.to_numpy())
        top10 = lo_sorted[: max(1, int(round(0.1 * len(lo_sorted))))]
        out[k] = {
            "n": int(len(w)), "total_R": round(float(w.R.sum()), 2), "exp": round(float(w.R.mean()), 4),
            "losers": int(len(los)), "loser_share": round(len(los) / len(w), 3),
            "avg_loss_R": round(float(los.R.mean()), 3), "gross_loss_R": round(float(gl), 1),
            "gross_win_R": round(float(win.R.sum()), 1), "avg_win_R": round(float(win.R.mean()), 3),
            "full_stop_losses": int(len(full)), "full_stop_share_of_losers": round(len(full) / len(los), 3),
            "full_stop_share_of_gross_loss": round(float(-full.R.sum() / gl), 3),
            "worst_10pct_losers_share_of_gross_loss": round(float(-top10.sum() / gl), 3),
            "losses_by_exit_reason": {r: {"n": int(len(g)), "R": round(float(g.R.sum()), 1)} for r, g in los.groupby("reason")},
            "winners_whose_adverse_move_reached_0.5R": round(float((win.mae_R <= -0.5).mean()), 3),
            "winners_whose_adverse_move_reached_0.25R": round(float((win.mae_R <= -0.25).mean()), 3),
            "R_of_winners_that_first_went_0.5R_against": round(float(win[win.mae_R <= -0.5].R.sum()), 1),
            "losers_that_were_once_ahead_1R": round(float((los.mfe_R >= 1.0).mean()), 3),
            "losers_that_were_once_ahead_0.5R": round(float((los.mfe_R >= 0.5).mean()), 3),
            "median_peak_of_winners_R": round(float(win.mfe_R.median()), 3),
            "median_result_of_winners_R": round(float(win.R.median()), 3),
            "share_of_total_R_from_best_5pct_trades": round(float(np.sort(w.R.to_numpy())[::-1][: max(1, int(round(0.05 * len(w))))].sum() / w.R.sum()), 3) if w.R.sum() > 0 else None,
        }
    return out


def main():
    res = {"window": "entries 2018-02-01 .. 2021-12-31", "stake": "1 R per trade, no compounding, no cap"}
    for mode in ("fp", "stress"):
        sets = sleeve_sets(mode)
        res[mode] = {}
        for p, per in sets.items():
            d = book(per)
            res[mode][p] = metrics(d)
            m = res[mode][p]
            print(mode, p, {k: m[k] for k in ("n", "exp", "total", "win", "avg_win", "avg_loss", "pf", "mean_over_sd",
                                              "worst_week_R", "max_dd_R_trade_by_trade", "max_dd_R_weekly",
                                              "longest_losing_run_weeks", "weekly_sharpe_annualised")}, flush=True)
        if mode == "fp":
            res["anatomy_fp"] = anatomy(sets["P0"])
    C.jdump(res, os.path.join(C.OUT, "s2_portfolio.json"))
    for k, v in res["anatomy_fp"].items():
        print(k, {kk: v[kk] for kk in ("n", "losers", "avg_loss_R", "full_stop_share_of_losers", "full_stop_share_of_gross_loss",
                                       "winners_whose_adverse_move_reached_0.5R", "losers_that_were_once_ahead_1R")})


if __name__ == "__main__":
    main()
