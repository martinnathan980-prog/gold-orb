"""PROTOCOL_V3 Addendum J, round 4 lead synthesis, step 1: my own recomputation of each main verdict from the
engineers' trade files (no simulation). IN SAMPLE ONLY: every file is read with entry_time AND exit_time < 2022-01-01
inside the read call (common.read_is). Output: lab/r2/tracks/round4/synthesis/verification.json.

Bars (PROTOCOL_V3 s.4, the judge's test_plan texts in results/r2/round4_ideas.json, frozen by Addendum J):
single sleeve: n >= 250, PF >= 1.12, t (per trade R) >= 2.5, >= 60 % of years positive (UTC entry year, as
goldlab.metrics.report), PF >= 1.04 at costs x1.5, neighbours' median PF >= 1.06, every-signal expectancy > 0,
hold <= 5 trading days, null percentile (share of the 200 stored null means strictly below the rule's mean) >= 97.5.
FX basket: t on daily (Monday, server date) sums of R >= 2.5, pooled PF, >= 6 of 8 pairs positive, no pair above 25 %
of the profit, plus the pooled bars above. Extra conditions as the judge declared them.
"""
import glob
import os

import numpy as np
import pandas as pd

from common import HERE, R4, TEN, CLUSTERS, read_is, official, pf, tstat, weekly, corr, sharpe, dump

COLS_MIN = ["entry_time", "exit_time", "R", "hold_min"]


def load(rule, stem, extra=()):
    f = os.path.join(R4, rule, f"{stem}.parquet")
    return read_is(f, columns=list(dict.fromkeys(COLS_MIN + list(extra))))


def core(t):
    R = t.R.to_numpy(float)
    yrs = t.groupby(t.entry_time.dt.year)["R"].sum()
    return {"n": int(len(R)), "first_entry": str(t.entry_time.min()), "last_entry": str(t.entry_time.max()),
            "pf": round(pf(R), 4), "t_trade": round(tstat(R), 3), "exp_R": round(float(R.mean()), 5),
            "total_R": round(float(R.sum()), 4), "win_rate_pct": round(float(100 * (R > 0).mean()), 2),
            "years_pos": f"{int((yrs > 0).sum())}/{len(yrs)}", "years_pos_share": float((yrs > 0).mean()),
            "by_year_R": {int(k): round(float(v), 2) for k, v in yrs.items()},
            "max_hold_h": round(float(t.hold_min.max() / 60), 2), "mean_hold_h": round(float(t.hold_min.mean() / 60), 2)}


def null_pct(rule, fname, rule_mean):
    p = os.path.join(R4, rule, fname)
    if p.endswith(".npy"):
        m = np.load(p)
    else:
        import json
        m = np.asarray(json.load(open(p))["means"], float)
    return {"replays": int(len(m)), "null_mean": round(float(m.mean()), 5),
            "null_p975": round(float(np.percentile(m, 97.5)), 5),
            "percentile": round(float((m < rule_mean).mean() * 100), 1)}


def neighbours(rule, stems):
    out = {}
    for s in stems:
        t = load(rule, s)
        out[s] = {"n": int(len(t)), "pf": round(pf(t.R), 4), "t_trade": round(tstat(t.R), 3),
                  "exp_R": round(float(t.R.mean()), 5)}
    med = float(np.median([v["pf"] for v in out.values()]))
    return out, round(med, 4)


def stems_of(rule):
    return sorted(os.path.basename(p)[:-8] for p in glob.glob(os.path.join(R4, rule, "trades_*.parquet")))


# ------------------------------------------------------------------------------------------- the ten (weekly)
ten = {f"{n}__{s}": official(n, s) for n, s in TEN}
W_TEN = {k: weekly(v, "wsun") for k, v in ten.items()}
w_sum10 = np.sum(list(W_TEN.values()), axis=0)
w_cl = {c: np.sum([W_TEN[k] for k in ks], axis=0) for c, ks in CLUSTERS.items()}


def corr_block(t):
    w = weekly(t, "wsun")
    return {"weeks": int(len(w)), "weeks_with_trade": int((w != 0).sum()),
            "sum_of_ten": round(corr(w, w_sum10), 3),
            **{f"cluster_{c}": round(corr(w, v), 3) for c, v in w_cl.items()},
            "own_weekly_sharpe": round(sharpe(w), 3)}


res = {}

# ------------------------------------------------------------------------------------------- IDXRS_1000
rule = "idxrs_1000"
m = load(rule, "trades_01_main", extra=["pair_type", "R_money", "S", "W"])
c = core(m)
st = load(rule, "trades_11_stress_x1.5")
nb, med = neighbours(rule, [s for s in stems_of(rule) if s[7:9] in {f"{i:02d}" for i in range(2, 11)}])
nl = null_pct(rule, "null.json", float(m.R.mean()))
pt = m.groupby("pair_type")["R"].agg(["size", "mean", "sum"])
cb = corr_block(m)
bars = {"n>=250": c["n"] >= 250, "PF>=1.12": c["pf"] >= 1.12, "t>=2.5": c["t_trade"] >= 2.5,
        "years>=60%": c["years_pos_share"] >= 0.6, "PF_x1.5>=1.04": pf(st.R) >= 1.04,
        "neighbours_median_PF>=1.06": med >= 1.06, "every_signal_exp>0 (= main, one pair a day)": c["exp_R"] > 0,
        "hold<=5 trading days": c["max_hold_h"] <= 24 * 5, "null>=97.5": nl["percentile"] >= 97.5,
        "extra |rho weekly vs ocm4+noise30|<=0.30": abs(cb["cluster_us100"]) <= 0.30,
        "extra >=2 of 3 pair types positive": int((pt["mean"] > 0).sum()) >= 2}
res[rule] = {"main": c, "money_version": {"pf": round(pf(m.R_money), 4), "t_trade": round(tstat(m.R_money), 3),
                                          "exp_R": round(float(m.R_money.mean()), 5)},
             "stress_x1.5": {"n": int(len(st)), "pf": round(pf(st.R), 4), "t_trade": round(tstat(st.R), 3),
                             "exp_R": round(float(st.R.mean()), 5)},
             "neighbours": nb, "neighbours_median_pf": med, "null": nl,
             "pair_types": {k: {"n": int(r["size"]), "exp_R": round(float(r["mean"]), 4), "sum_R": round(float(r["sum"]), 2)}
                            for k, r in pt.iterrows()},
             "correlation_wsun_2014_2021": cb, "bars": bars, "passes": bool(all(bars.values())),
             "failed_bars": [k for k, v in bars.items() if not v]}
# concentration, information
Rs = np.sort(m.R.to_numpy())[::-1]
no2020 = m[m.entry_time.dt.year != 2020]
res[rule]["concentration"] = {"best10_R": round(float(Rs[:10].sum()), 2), "best5_R": round(float(Rs[:5].sum()), 2),
                              "without_2020": {"n": int(len(no2020)), "exp_R": round(float(no2020.R.mean()), 4),
                                               "t_trade": round(tstat(no2020.R), 3), "pf": round(pf(no2020.R), 4)}}
# t needed: with the same sd, the mean would need to be x (2.5 / t)
res[rule]["t_gap"] = {"mean_needed_for_t2.5_at_same_sd": round(float(2.5 * m.R.std(ddof=1) / np.sqrt(len(m))), 4),
                      "mean_now": round(float(m.R.mean()), 4)}

# ------------------------------------------------------------------------------------------- FX weekend (basket)
rule = "fx_weekend"
m = load(rule, "trades_01_main", extra=["sym", "side"])
c = core(m)
loc = m.entry_time.dt.tz_convert("America/New_York").dt.tz_localize(None) + pd.Timedelta(hours=7)
day = loc.dt.normalize()
dsum = m.R.groupby(day.values).sum()
by_pair = m.groupby("sym")["R"].agg(["size", "mean", "sum"])
prof = by_pair["sum"].clip(lower=0)
st = load(rule, "trades_10_main_costs_x1.5")
nb, med = neighbours(rule, [s for s in stems_of(rule) if s[7:9] in {f"{i:02d}" for i in range(2, 10)}])
nl = null_pct(rule, "null_means.npy", float(m.R.mean()))
yrs_srv = m.R.groupby(loc.dt.year.values).sum()
cb = corr_block(m)
total = float(m.R.sum())
bars = {"t daily(Monday) sums>=2.5": tstat(dsum) >= 2.5, "pooled PF>=1.12": c["pf"] >= 1.12,
        "pooled PF_x1.5>=1.04": pf(st.R) >= 1.04, "years>=60%": c["years_pos_share"] >= 0.6,
        ">=6 of 8 pairs positive": int((by_pair["mean"] > 0).sum()) >= 6,
        "no pair >25% of profit": bool(total > 0 and (prof / total).max() <= 0.25),
        "neighbours_median_PF>=1.06": med >= 1.06, "every_signal_exp>0 (= main)": c["exp_R"] > 0,
        "null>=97.5": nl["percentile"] >= 97.5, "n>=250": c["n"] >= 250, "hold<=5 trading days": c["max_hold_h"] <= 120}
res[rule] = {"main": c, "t_daily_sums": round(tstat(dsum), 3), "days": int(len(dsum)),
             "years_pos_server_year": f"{int((yrs_srv > 0).sum())}/{len(yrs_srv)}",
             "pairs": {k: {"n": int(r["size"]), "exp_R": round(float(r["mean"]), 4), "sum_R": round(float(r["sum"]), 2)}
                       for k, r in by_pair.iterrows()},
             "stress_x1.5": {"n": int(len(st)), "pf": round(pf(st.R), 4), "exp_R": round(float(st.R.mean()), 5)},
             "neighbours": nb, "neighbours_median_pf": med, "null": nl, "correlation_wsun_2014_2021": cb,
             "bars": bars, "passes": bool(all(bars.values())), "failed_bars": [k for k, v in bars.items() if not v]}

# ------------------------------------------------------------------------------------------- ger40 noise30 Xetra
rule = "ger40_noise30_xetra"
m = load(rule, "trades_01_main", extra=["side"])
c = core(m)
st = load(rule, "trades_10_main_costs_x1.5")
nb, med = neighbours(rule, [s for s in stems_of(rule) if s[7:9] in {f"{i:02d}" for i in range(2, 10)}])
nl = null_pct(rule, "null_means.npy", float(m.R.mean()))
cb = corr_block(m)
bars = {"n>=250": c["n"] >= 250, "PF>=1.12": c["pf"] >= 1.12, "t>=2.5": c["t_trade"] >= 2.5,
        "years>=60%": c["years_pos_share"] >= 0.6, "PF_x1.5>=1.04": pf(st.R) >= 1.04,
        "neighbours_median_PF>=1.06": med >= 1.06, "every_signal_exp>0 (reported identical to main)": c["exp_R"] > 0,
        "hold<=5 trading days": c["max_hold_h"] <= 120, "null>=97.5": nl["percentile"] >= 97.5,
        "extra |rho weekly vs sum of ten|<=0.30": abs(cb["sum_of_ten"]) <= 0.30}
res[rule] = {"main": c, "stress_x1.5": {"n": int(len(st)), "pf": round(pf(st.R), 4), "exp_R": round(float(st.R.mean()), 5)},
             "neighbours": nb, "neighbours_median_pf": med, "null": nl, "correlation_wsun_2014_2021": cb,
             "bars": bars, "passes": bool(all(bars.values())), "failed_bars": [k for k, v in bars.items() if not v]}

# ------------------------------------------------------------------------------------------- FOMC cycle
rule = "fomc_cycle"
m = load(rule, "trades_01_main", extra=["side"])
c = core(m)
st = load(rule, "trades_09_stress_x1.5")
nb, med = neighbours(rule, [s for s in stems_of(rule) if s[7:9] in {f"{i:02d}" for i in range(2, 7)}])
g = load(rule, "trades_07_mech_ger40")
nl = null_pct(rule, "null_means_10_main.npy", float(m.R.mean()))
cb = corr_block(m)
bars = {"n>=250": c["n"] >= 250, "PF>=1.12": c["pf"] >= 1.12, "t>=2.5": c["t_trade"] >= 2.5,
        "years>=60%": c["years_pos_share"] >= 0.6, "PF_x1.5>=1.04 (spread, slippage and swap x1.5)": pf(st.R) >= 1.04,
        "neighbours_median_PF>=1.06": med >= 1.06, "every_signal_exp>0 (= main)": c["exp_R"] > 0,
        "null>=97.5": nl["percentile"] >= 97.5, "extra ger40 expectancy>0": float(g.R.mean()) > 0}
res[rule] = {"main": c, "stress_x1.5": {"n": int(len(st)), "pf": round(pf(st.R), 4), "exp_R": round(float(st.R.mean()), 5)},
             "neighbours": nb, "neighbours_median_pf": med, "null": nl,
             "ger40_mechanism": {"n": int(len(g)), "pf": round(pf(g.R), 4), "exp_R": round(float(g.R.mean()), 5)},
             "correlation_wsun_2014_2021": cb, "bars": bars, "passes": bool(all(bars.values())),
             "failed_bars": [k for k, v in bars.items() if not v],
             "note": "hold is judged in NYSE trading days by the engineer (max 5); not recomputed here"}

# ------------------------------------------------------------------------------------------- LETF close pair
rule = "letf_close_pair"
m = load(rule, "trades_01_main", extra=["dir"])
c = core(m)
st = load(rule, "trades_10_stress_x1.5")
nb, med = neighbours(rule, [s for s in stems_of(rule) if s[7:9] in {f"{i:02d}" for i in range(2, 10)}])
nl = null_pct(rule, "null.json", float(m.R.mean()))
cb = corr_block(m)
pf5, pf6 = nb["trades_05_n_exit_1557"]["pf"], nb["trades_06_n_exit_1605"]["pf"]
bars = {"n>=250": c["n"] >= 250, "PF>=1.12": c["pf"] >= 1.12, "t>=2.5": c["t_trade"] >= 2.5,
        "years>=60%": c["years_pos_share"] >= 0.6, "PF_x1.5>=1.04": pf(st.R) >= 1.04,
        "neighbours_median_PF>=1.06": med >= 1.06, "every_signal_exp>0 (= main, one pair a day)": c["exp_R"] > 0,
        "hold<=5 trading days": c["max_hold_h"] <= 120, "null>=97.5": nl["percentile"] >= 97.5,
        "extra knife-edge PF(5)>=1.06 and PF(6)>=1.06": pf5 >= 1.06 and pf6 >= 1.06}
res[rule] = {"main": c, "stress_x1.5": {"n": int(len(st)), "pf": round(pf(st.R), 4), "exp_R": round(float(st.R.mean()), 5)},
             "neighbours": nb, "neighbours_median_pf": med, "null": nl, "correlation_wsun_2014_2021": cb,
             "bars": bars, "passes": bool(all(bars.values())), "failed_bars": [k for k, v in bars.items() if not v]}

res["_ten_check"] = {"trades": int(sum(len(v) for v in ten.values())),
                     "total_R": round(float(sum(v.R.sum() for v in ten.values())), 2),
                     "weekly_sharpe_wsun": round(sharpe(w_sum10), 4), "weeks": int(len(w_sum10))}
res["_any_pass"] = any(v["passes"] for k, v in res.items() if not k.startswith("_"))
dump(res, os.path.join(HERE, "verification.json"))

for k, v in res.items():
    if k.startswith("_"):
        print(k, v)
        continue
    mc = v["main"]
    print(f"{k:22s} n {mc['n']:5d} PF {mc['pf']:.3f} t {mc['t_trade']:+.2f} exp {mc['exp_R']:+.4f} "
          f"years {mc['years_pos']} x1.5 PF {v['stress_x1.5']['pf']:.3f} nbmed {v['neighbours_median_pf']:.3f} "
          f"null {v['null']['percentile']:.1f} rho10 {v['correlation_wsun_2014_2021']['sum_of_ten']:+.3f} "
          f"pass {v['passes']} failed {v['failed_bars']}")
