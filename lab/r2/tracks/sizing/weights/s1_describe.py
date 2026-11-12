"""Lens `weights`, PART 1 (description, no variant): each sleeve's mean, standard deviation and Sharpe of R per
trade and per week, by year; correlations of weekly R between sleeves; does a sleeve's past predict its next year?
IN SAMPLE ONLY (the reference chains of s0_repro.py: entries and exits before 2022-01-01).

Conventions (common.py): plain sum of the ten one-position chains, 1 R per trade; weekly R = sum of R booked in the FP
server week (Mon-Sun, New York + 7 h) of the exit; every calendar week counted from the sleeve's first trade
(empty week = 0); the year of a week = the year of its Thursday; per-trade statistics by UTC year of the entry.
Weekly Sharpe = mean / sd (ddof 1) x sqrt(52); per-trade Sharpe = mean / sd of R per trade (not annualised).

Also a HINDSIGHT BOUND (description only, not a variant, judges nothing, not causal by construction): the best
static stakes in [0, 2] (F1 <= 1) chosen with the 2019-2021 weekly R themselves, i.e. the ceiling that no
per-sleeve weighting fitted on earlier years can beat on these weeks.

Output: results/r2/sizing/weights/part1.json, part1_by_year.csv, part1_corr_<window>_<mode>.csv
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.optimize import minimize  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

import common as C  # noqa: E402

WINDOWS = {"common_2018_02_2021_12": None, "oof_2019_2021": C.OOF}


def weeks_between(w0, w1):
    return np.arange(int(w0), int(w1) + 1)


def common_weeks():
    """server weeks whose Thursday is in [2018-02-01, 2021-12-31]"""
    ws = C.weeks_of_years((2018, 2019, 2020, 2021))
    thu = pd.DatetimeIndex((ws * 7).astype("datetime64[D]"))
    return ws[thu >= pd.Timestamp("2018-02-01")]


def weekly_of(t, weeks):
    s = pd.Series(t.R.to_numpy(float)).groupby(C.week_id(t.exit_time)).sum()
    return s.reindex(weeks, fill_value=0.0)


def wstats(x):
    x = np.asarray(x, float)
    n = len(x)
    if n < 2:
        return {"weeks": int(n)}
    sd = float(x.std(ddof=1))
    return {"weeks": int(n), "mean": round(float(x.mean()), 4), "sd": round(sd, 4),
            "sharpe_ann": round(float(x.mean() / sd * np.sqrt(52)), 3) if sd > 0 else None,
            "losing_weeks_pct": round(float(100 * (x < 0).mean()), 1), "empty_weeks_pct": round(float(100 * (x == 0).mean()), 1),
            "worst_week": round(float(x.min()), 3), "total": round(float(x.sum()), 2)}


def tstats(R, weeks_n=None):
    s = C.sstats(R)
    if weeks_n:
        s["trades_per_week"] = round(len(R) / weeks_n, 3)
    return s


def describe_mode(mode):
    out = {"by_sleeve": {}, "rows": []}
    chains = {k: C.load_chain(k, mode) for k in C.KEYS}
    last_w = int(C.week_id(pd.DatetimeIndex([pd.Timestamp("2021-12-31 12:00", tz="UTC")]))[0])
    W = {}
    for k, t in chains.items():
        w0 = int(C.week_id(pd.DatetimeIndex([t.entry_time.min()]))[0])
        weeks = weeks_between(w0, last_w)
        ws = weekly_of(t, weeks)
        W[k] = ws
        wy = C.week_year(weeks)
        ty = t.entry_time.dt.year.to_numpy()
        rec = {"first_entry": str(t.entry_time.min()), "years": {}}
        for y in sorted(set(ty)):
            sel_w = wy == y
            r = {"trade": tstats(t.R.to_numpy()[ty == y], int(sel_w.sum())), "week": wstats(ws.to_numpy()[sel_w])}
            rec["years"][int(y)] = r
            out["rows"].append({"mode": mode, "sleeve": k, "year": int(y), "n": r["trade"]["n"],
                                "mean_R": r["trade"].get("exp"), "sd_R": r["trade"].get("sd"),
                                "sharpe_trade": r["trade"].get("mean_over_sd"),
                                "trades_per_week": r["trade"].get("trades_per_week"),
                                "weeks": r["week"].get("weeks"), "mean_week": r["week"].get("mean"),
                                "sd_week": r["week"].get("sd"), "sharpe_week_ann": r["week"].get("sharpe_ann"),
                                "losing_weeks_pct": r["week"].get("losing_weeks_pct"), "total_R": r["trade"].get("total")})
        cw = common_weeks()
        ow = C.weeks_of_years(C.OOF)
        rec["whole_history"] = {"trade": tstats(t.R.to_numpy(), len(weeks)), "week": wstats(ws.to_numpy())}
        sel = t.entry_time >= C.COMMON_START
        rec["common_2018_02_2021_12"] = {"trade": tstats(t.R.to_numpy()[sel.to_numpy()], len(cw)),
                                         "week": wstats(ws.reindex(cw, fill_value=0.0).to_numpy())}
        sel = (t.entry_time.dt.year >= 2019).to_numpy()
        rec["oof_2019_2021"] = {"trade": tstats(t.R.to_numpy()[sel], len(ow)),
                                "week": wstats(ws.reindex(ow, fill_value=0.0).to_numpy())}
        out["by_sleeve"][k] = rec
    # correlations of weekly R between sleeves
    out["corr"] = {}
    for wname, years in WINDOWS.items():
        weeks = common_weeks() if years is None else C.weeks_of_years(years)
        M = pd.DataFrame({C.SHORT[k]: W[k].reindex(weeks, fill_value=0.0) for k in C.KEYS})
        cm = M.corr()
        cm.round(4).to_csv(os.path.join(C.OUT, f"part1_corr_{wname}_{mode}.csv"))
        iu = np.triu_indices(len(cm), 1)
        vals = cm.to_numpy()[iu]
        names = [(cm.index[i], cm.columns[j]) for i, j in zip(*iu)]
        order = np.argsort(-vals)
        port = M.sum(axis=1)
        var_diag = float((M.var(ddof=1)).sum())
        out["corr"][wname] = {
            "weeks": int(len(weeks)), "matrix": {a: {b: round(float(cm.loc[a, b]), 4) for b in cm.columns} for a in cm.index},
            "mean_pairwise": round(float(vals.mean()), 4),
            "top_pairs": [{"pair": f"{names[i][0]} ~ {names[i][1]}", "r": round(float(vals[i]), 4)} for i in order[:8]],
            "bottom_pairs": [{"pair": f"{names[i][0]} ~ {names[i][1]}", "r": round(float(vals[i]), 4)} for i in order[-5:]],
            "portfolio_week": wstats(port.to_numpy()),
            "portfolio_variance_share_from_covariances": round(1 - var_diag / float(port.var(ddof=1)), 4)}
    # correlation by year (mean pairwise) and the crypto breakout block
    cryp = ["brk72_24h_wd__btcusd", "brk72_24h_wd__ethusd", "F1_brk_ridge_filter__btcusd", "F1_brk_ridge_filter__ethusd"]
    out["corr_by_year"] = {}
    for y in (2018, 2019, 2020, 2021):
        weeks = C.weeks_of_years((y,))
        if y == 2018:
            weeks = common_weeks()[C.week_year(common_weeks()) == 2018]
        M = pd.DataFrame({k: W[k].reindex(weeks, fill_value=0.0) for k in C.KEYS})
        cm = M.corr().to_numpy()
        iu = np.triu_indices(len(cm), 1)
        idx = [C.KEYS.index(k) for k in cryp]
        sub = cm[np.ix_(idx, idx)][np.triu_indices(4, 1)]
        out["corr_by_year"][y] = {"mean_pairwise_all": round(float(cm[iu].mean()), 4),
                                  "mean_pairwise_crypto_breakouts": round(float(sub.mean()), 4),
                                  "brk72_btc~F1_btc": round(float(cm[idx[0], idx[2]]), 4),
                                  "brk72_eth~F1_eth": round(float(cm[idx[1], idx[3]]), 4),
                                  "brk72_btc~brk72_eth": round(float(cm[idx[0], idx[1]]), 4)}
    # does the past predict the next year at the sleeve level? (rank correlation across sleeves)
    out["persistence"] = persistence(chains, W)
    out["reference_portfolio"] = reference_portfolio(chains)
    out["hindsight_bound"] = hindsight_bound(W)
    return out


def persistence(chains, W):
    """Spearman correlation across sleeves between (a) the expanding past (all trades closed before Y-01-01 - 7 days,
    weekly mean / variance and per-trade mean) and (b) the realised year Y (per-trade mean R, weekly Sharpe)."""
    res = {}
    for y in (2016, 2017, 2018, 2019, 2020, 2021):
        cut = pd.Timestamp(f"{y}-01-01", tz="UTC") - C.PURGE
        rows = []
        for k, t in chains.items():
            past = t[t.exit_time < cut]
            if len(past) < 30:
                continue
            w0 = int(C.week_id(pd.DatetimeIndex([t.entry_time.min()]))[0])
            # complete server weeks ending at or before the cut
            cut_srv = C.server_naive(pd.DatetimeIndex([cut]))[0]
            wl = int(((cut_srv - pd.Timestamp("1970-01-01")).days + 3) // 7) - 1
            ws = W[k].reindex(weeks_between(w0, wl), fill_value=0.0).to_numpy()
            if len(ws) < 26:
                continue
            nxt = t[t.entry_time.dt.year == y]
            wn = W[k].reindex(C.weeks_of_years((y,)), fill_value=0.0).to_numpy()
            rows.append({"k": k, "past_mean_trade": past.R.mean(), "past_mv": ws.mean() / ws.var(ddof=1),
                         "past_sharpe_week": ws.mean() / ws.std(ddof=1),
                         "next_mean_trade": nxt.R.mean() if len(nxt) else np.nan,
                         "next_sharpe_week": wn.mean() / wn.std(ddof=1) if wn.std(ddof=1) > 0 else np.nan})
        d = pd.DataFrame(rows).dropna()
        if len(d) < 4:
            continue
        res[y] = {"sleeves": int(len(d)),
                  "rho_past_mean_trade_vs_next_mean_trade": round(float(spearmanr(d.past_mean_trade, d.next_mean_trade)[0]), 3),
                  "rho_past_mv_vs_next_sharpe_week": round(float(spearmanr(d.past_mv, d.next_sharpe_week)[0]), 3),
                  "rho_past_sharpe_week_vs_next_sharpe_week": round(float(spearmanr(d.past_sharpe_week, d.next_sharpe_week)[0]), 3),
                  "table": {C.SHORT[r.k]: {"past_mean_trade": round(float(r.past_mean_trade), 4),
                                           "next_mean_trade": round(float(r.next_mean_trade), 4),
                                           "past_sharpe_week_ann": round(float(r.past_sharpe_week * np.sqrt(52)), 3),
                                           "next_sharpe_week_ann": round(float(r.next_sharpe_week * np.sqrt(52)), 3)}
                            for r in d.itertuples()}}
    return res


def reference_portfolio(chains):
    """equal stakes, the ten sleeves (U10) and without the two F1 sleeves (U8): weekly statistics by year (2018 = the
    weeks from 2018-02-01), pooled 2019-2021, with the trade counts."""
    out = {}
    for uname, keys in C.UNIVERSES.items():
        b = pd.concat([chains[k].assign(k=k) for k in keys], ignore_index=True)
        rec = {}
        for y in (2018, 2019, 2020, 2021):
            weeks = common_weeks()[C.week_year(common_weeks()) == 2018] if y == 2018 else C.weeks_of_years((y,))
            bb = b[(b.entry_time >= C.COMMON_START)]
            ws = weekly_of(bb, weeks).to_numpy()
            rec[y] = {**wstats(ws), "trades_entered": int((bb.entry_time.dt.year == y).sum()),
                      "longest_losing_run_weeks": C.longest_run(ws < 0)}
        ow = C.weeks_of_years(C.OOF)
        bb = b[b.entry_time.dt.year >= 2019]
        ws = weekly_of(bb, ow).to_numpy()
        rec["pooled_2019_2021"] = {**wstats(ws), "trades_entered": int(len(bb)),
                                   "losing_trades_per_month": round(float((bb.R < 0).sum()) / 36, 2),
                                   "longest_losing_run_weeks": C.longest_run(ws < 0), "max_dd_weekly": round(C.max_dd(ws), 2)}
        out[uname] = rec
    return out


def hindsight_bound(W):
    """Description only: the static stakes (one per sleeve, in [0, 2], F1 <= 1) that maximise the pooled 2019-2021
    weekly Sharpe of the ten sleeves, found WITH those very weeks (hindsight, not causal). Also per year."""
    out = {}
    for uname, keys in C.UNIVERSES.items():
        rec = {}
        for label, years in (("pooled_2019_2021", C.OOF), ("2019", (2019,)), ("2020", (2020,)), ("2021", (2021,))):
            weeks = C.weeks_of_years(years)
            M = np.column_stack([W[k].reindex(weeks, fill_value=0.0).to_numpy() for k in keys])
            ub = np.array([1.0 if k in C.F1_KEYS else 2.0 for k in keys])
            mu, S = M.mean(0), np.cov(M, rowvar=False)

            def neg(w):
                v = float(w @ S @ w)
                return -float(w @ mu) / np.sqrt(v) if v > 0 else 0.0
            best = None
            for s in range(8):
                x0 = np.random.default_rng(s).uniform(0.2, 1.0, len(keys)) * ub if s else np.ones(len(keys))
                x0 = np.minimum(x0, ub)
                r = minimize(neg, x0, bounds=[(0.0, u) for u in ub], method="L-BFGS-B")
                if best is None or r.fun < best.fun:
                    best = r
            sh_eq = float(M.sum(1).mean() / M.sum(1).std(ddof=1) * np.sqrt(52))
            sh_best = float(-neg(best.x) * np.sqrt(52))
            rec[label] = {"weeks": int(len(weeks)), "sharpe_equal": round(sh_eq, 3), "sharpe_best_static": round(sh_best, 3),
                          "gain_pct": round(100 * (sh_best / sh_eq - 1), 1),
                          "stakes_relative": {C.SHORT[k]: round(float(x), 3) for k, x in zip(keys, best.x / max(best.x.max(), 1e-12))}}
        out[uname] = rec
    return out


def main():
    res = {"what": "PART 1 of the weights lens: description of the ten reference chains, in sample only "
                   "(entries and exits before 2022-01-01; FP costs and costs x1.5).",
           "conventions": C.__doc__.split("Account used")[1].strip()}
    rows = []
    for mode in C.MODES:
        d = describe_mode(mode)
        rows += d.pop("rows")
        res[mode] = d
        print(mode, "done", flush=True)
    pd.DataFrame(rows).to_csv(os.path.join(C.OUT, "part1_by_year.csv"), index=False)
    C.jdump(res, os.path.join(C.OUT, "part1.json"))


if __name__ == "__main__":
    main()
