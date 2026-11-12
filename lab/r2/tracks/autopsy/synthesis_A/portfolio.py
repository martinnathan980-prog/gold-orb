"""Lead synthesis A: in-sample portfolio of the ten sleeves, unchanged against the five kept changes.  IN SAMPLE ONLY.

Reads only the simulated trades of synth.py (work/<name>__<sym>__<variant>__<mode>.parquet, all entries < 2022,
censored trades already removed).  No new simulation.  One trials.jsonl line per portfolio assembly.

    python3 portfolio.py        -> work/portfolio.json
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("NUMBA_CACHE_DIR", "/tmp/numba_synthesis_A")
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True
import synth as S  # noqa: E402

NY = S.NY
MAIN0, CUT = S.MAIN0, S.CUT
EARLY0 = pd.Timestamp("2013-01-01", tz="UTC")


def load(name, sym, variant, mode):
    t = pd.read_parquet(os.path.join(S.WORK, f"{name}__{sym}__{variant}__{mode}.parquet"))
    assert (t.entry_time < CUT).all() and (t.exit_time <= pd.Timestamp("2022-01-01 00:00", tz="UTC")).all()
    t = t.copy()
    t["sleeve"] = f"{name}:{sym}"
    return t


def server_days(ts):
    srv = pd.DatetimeIndex(ts).tz_convert(NY).tz_localize(None) + pd.Timedelta(hours=7)
    return (srv.values.astype("datetime64[D]") - np.datetime64("1970-01-01")).astype(np.int64)


def week_id(ts):
    """FP server weeks (server = New York + 7 h), starting Monday 00:00 server."""
    return (server_days(ts) + 3) // 7


def weekly(t, w0, w1, col="Rw"):
    """Weekly sums of R booked at the exit over the weeks w0..w1 (empty weeks = 0)."""
    wk = week_id(t.exit_time)
    s = pd.Series(t[col].to_numpy(float)).groupby(wk).sum()
    return s.reindex(np.arange(w0, w1 + 1), fill_value=0.0)


def longest_run(neg):
    best = cur = 0
    for v in neg:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best


def measures(t, w0, w1, col="Rw"):
    """Per-trade and weekly measures of a set of trades whose R (scaled or not) is in column `col`."""
    R = t[col].to_numpy(float)
    n = len(R)
    pos, neg = R[R > 0], R[R < 0]
    sd = float(R.std(ddof=1))
    o = t.sort_values(["exit_time", "entry_time"])
    cum = np.cumsum(o[col].to_numpy(float))
    dd_trade = float((np.maximum.accumulate(np.r_[0.0, cum]) - np.r_[0.0, cum]).max())
    W = weekly(t, w0, w1, col)
    wc = np.cumsum(W.to_numpy())
    dd_week = float((np.maximum.accumulate(np.r_[0.0, wc]) - np.r_[0.0, wc]).max())
    wsd = float(W.std(ddof=1))
    return {
        "n_trades": n,
        "expectancy_R": round(float(R.mean()), 4),
        "euros_per_100_risked": round(float(R.mean()) * 100, 2),
        "win_rate": round(float((R > 0).mean()), 4),
        "avg_win_R": round(float(pos.mean()), 4),
        "avg_loss_R": round(float(neg.mean()), 4),
        "profit_factor": round(float(pos.sum() / -neg.sum()), 3),
        "total_R": round(float(R.sum()), 2),
        "mean_over_sd_per_trade": round(float(R.mean()) / sd, 4),
        "sd_R_per_trade": round(sd, 4),
        "weeks": int(len(W)),
        "worst_week_R": round(float(W.min()), 2),
        "best_week_R": round(float(W.max()), 2),
        "losing_weeks_share": round(float((W < 0).mean()), 4),
        "longest_losing_run_weeks": int(longest_run((W < 0).to_numpy())),
        "max_drawdown_R_trades_exit_order": round(dd_trade, 2),
        "max_drawdown_R_weekly": round(dd_week, 2),
        "weekly_mean_R": round(float(W.mean()), 4),
        "weekly_sd_R": round(wsd, 4),
        "weekly_sharpe": round(float(W.mean()) / wsd * np.sqrt(52), 4) if wsd > 0 else None,
        "by_entry_year_total_R": {int(y): round(float(g[col].sum()), 2) for y, g in t.groupby(t.entry_time.dt.year)},
    }


def win(t, w):
    if w == "main":
        return t[(t.entry_time >= MAIN0) & (t.entry_time < CUT)]
    return t[t.entry_time < MAIN0]


def week_bounds(w, t=None):
    """Main window: the weeks from the one holding 2018-02-01 to the one holding 2021-12-31 (205 weeks).
    Early window: from the week of the first early entry to the week of the last early exit."""
    if w == "main":
        return int(week_id(pd.DatetimeIndex([MAIN0]))[0]), int(week_id(pd.DatetimeIndex([pd.Timestamp("2021-12-31 20:00", tz="UTC")]))[0])
    return int(week_id(pd.DatetimeIndex([t.entry_time.min()]))[0]), int(week_id(pd.DatetimeIndex([t.exit_time.max()]))[0])


def main():
    modes = ("fp", "stress")
    T = {}
    for name, sym in S.TEN:
        for mode in modes:
            T[(name, sym, "ref", mode)] = load(name, sym, "ref", mode)
            if (name, sym) in S.CHANGE:
                v = S.CHANGE[(name, sym)]
                T[(name, sym, v, mode)] = load(name, sym, v, mode)
    out = {"written": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "weeks": "FP server weeks, Monday start, R booked at the exit, empty weeks = 0",
           "windows": {"main": "entries 2018-02-01..2021-12-31", "early": "entries before 2018-02-01 (sleeves that trade then)"}}
    # ---- per changed sleeve: sleeve-level figures and the equal-swing factor (main window, fp)
    factor = {}
    sleeves = {}
    for (name, sym), v in S.CHANGE.items():
        key = f"{name}:{sym}"
        d = {"change": v}
        for mode in modes:
            for lab, var in (("unchanged", "ref"), ("changed", v)):
                for w in ("main", "early"):
                    t = win(T[(name, sym, var, mode)], w).assign(Rw=lambda x: x.R)
                    if len(t) > 2:
                        b0, b1 = week_bounds(w, t)
                        m = measures(t, b0, b1)
                        d[f"{lab}_{mode}_{w}"] = {k: m[k] for k in ("n_trades", "expectancy_R", "win_rate", "avg_win_R", "avg_loss_R",
                                                                  "profit_factor", "total_R", "mean_over_sd_per_trade", "weekly_sd_R",
                                                                  "weekly_sharpe", "worst_week_R", "max_drawdown_R_trades_exit_order",
                                                                  "by_entry_year_total_R")}
        c = d["unchanged_fp_main"]["weekly_sd_R"] / d["changed_fp_main"]["weekly_sd_R"]
        factor[key] = c
        d["equal_swing_factor"] = round(c, 4)
        for mode in modes:
            for w in ("main", "early"):
                k = f"changed_{mode}_{w}"
                if k in d:
                    d[f"changed_equal_swing_total_R_{mode}_{w}"] = round(d[k]["total_R"] * c, 2)
                    d[f"gain_equal_swing_total_R_{mode}_{w}"] = round(d[k]["total_R"] * c - d[f"unchanged_{mode}_{w}"]["total_R"], 2)
                    d[f"gain_weekly_sharpe_{mode}_{w}"] = round(d[k]["weekly_sharpe"] - d[f"unchanged_{mode}_{w}"]["weekly_sharpe"], 4)
        sleeves[key] = d
    out["changed_sleeves"] = sleeves
    out["equal_swing_factors_frozen"] = {k: round(v, 6) for k, v in factor.items()}

    # ---- portfolio assemblies
    def assemble(changes, scale, mode):
        parts = []
        for name, sym in S.TEN:
            key = f"{name}:{sym}"
            if (name, sym) in changes:
                t = T[(name, sym, S.CHANGE[(name, sym)], mode)]
                c = factor[key] if scale else 1.0
            else:
                t, c = T[(name, sym, "ref", mode)], 1.0
            parts.append(t.assign(Rw=t.R * c))
        return pd.concat(parts, ignore_index=True)

    all_changes = set(S.CHANGE)
    plans = [("unchanged", set(), False), ("all_five_constant_stake", all_changes, False),
             ("all_five_equal_swing", all_changes, True)]
    for ch in S.CHANGE:
        lab = f"{ch[0]}:{ch[1]}:{S.CHANGE[ch]}"
        plans.append((f"only_{lab}_constant_stake", {ch}, False))
        plans.append((f"only_{lab}_equal_swing", {ch}, True))
    port = {}
    for lab, ch, scale in plans:
        for mode in modes:
            P = assemble(ch, scale, mode)
            r = {w: measures(win(P, w), *week_bounds(w, win(P, w))) for w in ("main", "early")}
            port[f"{lab}|{mode}"] = r
            S.log({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "kind": "assembly", "portfolio": lab,
                   "mode": mode, "changes": sorted(f"{a}:{b}:{S.CHANGE[(a, b)]}" for a, b in ch),
                   "equal_swing": scale, "main": r["main"], "early": r["early"]})
    out["portfolios"] = port

    # ---- deltas against the unchanged portfolio
    keys = ("n_trades", "expectancy_R", "euros_per_100_risked", "win_rate", "avg_win_R", "avg_loss_R", "profit_factor",
            "total_R", "worst_week_R", "max_drawdown_R_trades_exit_order", "max_drawdown_R_weekly",
            "longest_losing_run_weeks", "losing_weeks_share", "mean_over_sd_per_trade", "weekly_sharpe")
    deltas = {}
    for lab, ch, scale in plans[1:]:
        for mode in modes:
            for w in ("main", "early"):
                a, b = port[f"unchanged|{mode}"][w], port[f"{lab}|{mode}"][w]
                deltas[f"{lab}|{mode}|{w}"] = {k: round(b[k] - a[k], 4) for k in keys}
    out["deltas_vs_unchanged"] = deltas
    json.dump(out, open(os.path.join(S.WORK, "portfolio.json"), "w"), indent=1, default=str)
    for lab, ch, scale in plans[:3]:
        for mode in modes:
            m = port[f"{lab}|{mode}"]["main"]
            print(f"{lab:28s} {mode:6s} n {m['n_trades']} exp {m['expectancy_R']:+.4f} win {m['win_rate']:.3f} "
                  f"aw {m['avg_win_R']:.3f} al {m['avg_loss_R']:.3f} PF {m['profit_factor']:.3f} tot {m['total_R']:.1f} "
                  f"worstwk {m['worst_week_R']:.2f} DDtr {m['max_drawdown_R_trades_exit_order']:.2f} DDwk {m['max_drawdown_R_weekly']:.2f} "
                  f"run {m['longest_losing_run_weeks']} m/sd {m['mean_over_sd_per_trade']:.4f} wkSh {m['weekly_sharpe']:.3f} "
                  f"losewk {m['losing_weeks_share']:.3f} weeks {m['weeks']}")
    print(json.dumps(out["equal_swing_factors_frozen"]))


if __name__ == "__main__":
    main()
