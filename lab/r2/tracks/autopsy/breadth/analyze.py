"""PART 2 analysis: results table, correlations with the ten sleeves, pooled readings, chance passes, ranking.

    PYTHONDONTWRITEBYTECODE=1 python3 analyze.py

Reads trials.jsonl and trades/ (written by run_pairs.py) and the official trades of the ten sleeves (rows with
entry_time < 2022-01-01, read with that filter).  Window: trades entered 2018-02-01 .. 2021-12-31.
Writes pairs_results.csv, correlations.csv, pooled.csv, chance_passes.csv and analysis.json.
"""
import json
import math
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common as C  # noqa: E402

TR = os.path.join(C.RES, "trades")
YEARS_IN_WINDOW = (C.IS_END - C.COMMON_START).days / 365.25
GROUP = {**{s: "fx" for s in C.FX}, **{s: "shares" for s in C.STOCKS}, "xauusd": "metals", "xagusd": "metals",
         "us100": "indices", "us500": "indices", "us30": "indices", "ger40": "indices", "jp225": "indices",
         "btcusd": "crypto", "ethusd": "crypto"}


def trials():
    rows = [json.loads(ln) for ln in open(os.path.join(C.RES, "trials.jsonl")) if ln.strip()]
    return {r["id"]: r for r in rows}


def load_tr(rule, sym, mode="fp"):
    p = os.path.join(TR, f"{rule}__{sym}__{mode}.parquet")
    if not os.path.exists(p):
        return pd.DataFrame(columns=["entry_time", "exit_time", "R", "side", "pnl", "entry"])
    t = pd.read_parquet(p)
    assert (t.entry_time < C.IS_END).all()
    return t


def sharpe(w):
    sd = float(w.std(ddof=1))
    return float(w.mean() / sd * math.sqrt(52)) if sd > 0 else float("nan")


def daily_t(t):
    """PROTOCOL_V3 basket t: t of the daily sums of R (days with at least one trade, New-York date of entry)."""
    if not len(t):
        return float("nan")
    ds = t.groupby(t.entry_time.dt.tz_convert(C.NY).dt.date)["R"].sum()
    return float(ds.mean() / ds.std(ddof=1) * math.sqrt(len(ds))) if len(ds) > 2 else float("nan")


def zero_edge_pass_prob(t_fp, gross_exp, stress_shift, n_draw=500, seed=11):
    """Probability that the pair passes the breadth bar if it had NO gross edge: every net R is shifted by the pair's
    own gross expectancy (costs kept), trades are resampled within each calendar year (counts kept), and the three
    criteria are checked (stress = the same draw minus the pair's own fp-to-stress cost difference per trade)."""
    if not len(t_fp) or not np.isfinite(gross_exp):
        return float("nan")
    rng = np.random.default_rng(seed)
    R0 = t_fp["R"].to_numpy() - gross_exp
    yr = t_fp.entry_time.dt.year.to_numpy()
    groups = [np.flatnonzero(yr == y) for y in C.YEARS]
    ok = 0
    for _ in range(n_draw):
        parts, ypos = [], 0
        for g in groups:
            if not len(g):
                continue
            d = R0[g[rng.integers(0, len(g), len(g))]]
            parts.append(d)
            ypos += d.sum() > 0
        x = np.concatenate(parts) if parts else np.array([])
        if not len(x):
            continue
        gp, gl_ = x[x > 0].sum(), -x[x < 0].sum()
        pf = gp / gl_ if gl_ > 0 else np.inf
        st = (x - stress_shift).sum() > 0
        ok += (pf >= 1.15) and (ypos >= 3) and st
    return ok / n_draw


def main():
    T = trials()
    print(len(T), "pairs logged")
    # official sleeves, window, weekly
    sl_w = {}
    for name, sym in C.SLEEVES:
        sl_w[f"{name}:{sym}"] = C.weekly(C.window(C.official(name, sym)))
    W = pd.DataFrame(sl_w)
    P = W.sum(axis=1)
    base = {"weeks": int(len(P)), "total_R": round(float(P.sum()), 1), "R_per_year": round(float(P.sum()) / YEARS_IN_WINDOW, 1),
            "weekly_sharpe_ann": round(sharpe(P), 3), "win_weeks_pct": round(float((P > 0).mean() * 100), 1),
            "trades": int(sum(len(C.window(C.official(n, s))) for n, s in C.SLEEVES))}
    rows, corr_rows = [], []
    for pid in sorted(T):
        r = T[pid]
        rule, sym = r["rule"], r["instrument"]
        f, s, g = r["fp"], r["stress"], r["gross"]
        t = C.window(load_tr(rule, sym, "fp"))
        w = C.weekly(t)
        cr = {k: (round(float(np.corrcoef(w, W[k])[0, 1]), 3) if w.std() > 0 and W[k].std() > 0 else None) for k in W}
        c_sum = round(float(np.corrcoef(w, P)[0, 1]), 3) if w.std() > 0 else None
        P2 = P + w
        d_sh = round(sharpe(P2) - sharpe(P), 3) if len(t) else None
        stress_shift = (f.get("expectancy_R", 0) - s.get("expectancy_R", 0)) if f.get("n") and s.get("n") else 0.0
        zp = zero_edge_pass_prob(t, g.get("expectancy_R", float("nan")) if g.get("n") else float("nan"), stress_shift)
        b = r["breadth_criteria"]
        row = {"id": pid, "rule": rule, "instrument": sym, "group": GROUP.get(sym, "?"), "n": f.get("n", 0),
               "trades_per_year": round(f.get("n", 0) / YEARS_IN_WINDOW, 1), "win_rate": f.get("win_rate"),
               "avg_win_R": f.get("avg_win_R"), "avg_loss_R": f.get("avg_loss_R"), "exp_R": f.get("expectancy_R"),
               "t": f.get("t_stat"), "pf": f.get("pf"), "total_R": f.get("total_R"), "max_dd_R": f.get("max_dd_R"),
               "R_2018": (f.get("by_year_R") or {}).get("2018", (f.get("by_year_R") or {}).get(2018)),
               "R_2019": (f.get("by_year_R") or {}).get("2019", (f.get("by_year_R") or {}).get(2019)),
               "R_2020": (f.get("by_year_R") or {}).get("2020", (f.get("by_year_R") or {}).get(2020)),
               "R_2021": (f.get("by_year_R") or {}).get("2021", (f.get("by_year_R") or {}).get(2021)),
               "years_pos": f.get("years_2018_2021_pos"), "long_R": f.get("long_R"), "short_R": f.get("short_R"),
               "bps_per_trade": f.get("bps_per_trade"), "avg_hold_h": f.get("avg_hold_h"),
               "stress_n": s.get("n", 0), "stress_pf": s.get("pf"), "stress_exp_R": s.get("expectancy_R"), "stress_total_R": s.get("total_R"),
               "gross_pf": g.get("pf"), "gross_exp_R": g.get("expectancy_R"), "gross_bps": g.get("bps_per_trade"),
               "refused_3spreads_fp": r.get("refused_3spreads_fp"), "orders_fp": r.get("orders_fp"),
               "early_n": r.get("fp_before_2018_02", {}).get("n", 0), "early_pf": r.get("fp_before_2018_02", {}).get("pf"),
               "early_exp_R": r.get("fp_before_2018_02", {}).get("expectancy_R"),
               "early_total_R": r.get("fp_before_2018_02", {}).get("total_R"),
               "corr_sum10": c_sum, "corr_max_sleeve": max([v for v in cr.values() if v is not None], default=None),
               "extra_R_per_year": round(float(t.R.sum()) / YEARS_IN_WINDOW, 1) if len(t) else 0.0,
               "delta_sharpe_portfolio": d_sh, "zero_edge_pass_prob": None if not np.isfinite(zp) else round(zp, 3),
               "pass_pf": b["pf>=1.15"], "pass_years": b["years_pos>=3of4"], "pass_stress": b["stress_positive"],
               "breadth_pass": b["pass"], "v2_pass_info": r["v2_criteria_info"].get("pass")}
        rows.append(row)
        corr_rows.append({"id": pid, "rule": rule, "instrument": sym, "corr_sum10": c_sum, **cr})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(C.RES, "pairs_results.csv"), index=False)
    pd.DataFrame(corr_rows).to_csv(os.path.join(C.RES, "correlations.csv"), index=False)

    # pooled readings (information only)
    pooled = []
    for rule in C.RULES:
        for grp in ("fx", "shares", "metals", "indices", "crypto"):
            sub = df[(df.rule == rule) & (df.group == grp)]
            if not len(sub):
                continue
            ts = [C.window(load_tr(rule, s, "fp")) for s in sub.instrument]
            ts = [x.assign(instrument=s) for x, s in zip(ts, sub.instrument) if len(x)]
            if not ts:
                continue
            tt = pd.concat(ts)
            Rv = tt.R.to_numpy()
            gp, gl_ = Rv[Rv > 0].sum(), -Rv[Rv < 0].sum()
            by_i = tt.groupby("instrument").R.sum()
            pooled.append({"rule": rule, "group": grp, "instruments": int(len(sub)), "n": int(len(tt)),
                           "pf": round(float(gp / gl_), 3) if gl_ > 0 else None, "exp_R": round(float(Rv.mean()), 4),
                           "total_R": round(float(Rv.sum()), 1), "t_daily_sums": round(daily_t(tt), 2),
                           "instruments_positive": int((by_i > 0).sum()),
                           "years_pos": int(sum(1 for y in C.YEARS if tt[tt.entry_time.dt.year == y].R.sum() > 0))})
    pdf = pd.DataFrame(pooled)
    pdf.to_csv(os.path.join(C.RES, "pooled.csv"), index=False)

    # chance passes
    exp_false = float(np.nansum(df.zero_edge_pass_prob.astype(float)))
    n_pass = int(df.breadth_pass.sum())
    df[["id", "rule", "instrument", "breadth_pass", "zero_edge_pass_prob"]].to_csv(os.path.join(C.RES, "chance_passes.csv"), index=False)

    # ranking of qualifiers
    q = df[df.breadth_pass].sort_values(["delta_sharpe_portfolio", "extra_R_per_year"], ascending=False)
    rank = [{"rank": i + 1, **{k: rr[k] for k in ("id", "rule", "instrument", "n", "pf", "exp_R", "t", "total_R",
                                                  "years_pos", "stress_pf", "stress_total_R", "extra_R_per_year",
                                                  "corr_sum10", "corr_max_sleeve", "delta_sharpe_portfolio",
                                                  "zero_edge_pass_prob")}} for i, (_, rr) in enumerate(q.iterrows())]
    # all qualifiers together
    allw = P.copy()
    for rr in rank:
        allw = allw + C.weekly(C.window(load_tr(rr["rule"], rr["instrument"], "fp")))
    together = {"total_R": round(float(allw.sum()), 1), "R_per_year": round(float(allw.sum()) / YEARS_IN_WINDOW, 1),
                "weekly_sharpe_ann": round(sharpe(allw), 3), "win_weeks_pct": round(float((allw > 0).mean() * 100), 1)}
    out = {"window": "trades entered 2018-02-01 .. 2021-12-31, FP costs, broker 3-spread minimum stop applied to the new pairs",
           "portfolio_ten_sleeves": base, "pairs_run": int(len(df)), "breadth_passes": n_pass,
           "expected_passes_if_no_pair_had_a_gross_edge": round(exp_false, 1),
           "ranking": rank, "ten_plus_all_qualifiers": together,
           "pooled": pooled}
    C.jdump(out, os.path.join(C.RES, "analysis.json"))
    pd.set_option("display.width", 250)
    print(json.dumps(base))
    print("passes", n_pass, "expected by chance", round(exp_false, 1))
    print(pd.DataFrame(rank).to_string())
    print(pdf.to_string())


if __name__ == "__main__":
    main()
