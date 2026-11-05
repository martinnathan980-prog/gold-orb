"""Bootstrap (iid, week-cluster, moving blocks), autocorrelation, concentration, stability by
year x side, regime dependence, rolling windows -- on the candidate's own IS and VAL trades
(VAL rows come from the single logged cut in s01; no new VAL access here)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa
from scipy import stats

ti = pd.read_parquet(os.path.join(HERE, "cand_trades_is.parquet"))
tv = pd.read_parquet(os.path.join(HERE, "cand_trades_val.parquet"))
TI, TV = ti[ti.variant == "normal"].copy(), tv[tv.variant == "normal"].copy()
EI, EV = ti[ti.variant == "every"].copy(), tv[tv.variant == "every"].copy()
rng = np.random.default_rng(12345)
B = 10000
out = {}


def boot_stats(samples):
    pfs = np.array([pf(s) for s in samples])
    ex = np.array([s.mean() for s in samples])
    q = lambda a: [round(float(np.nanpercentile(a, p)), 3) for p in (2.5, 5, 50, 95, 97.5)]
    return {"pf_q2.5_5_50_95_97.5": q(pfs), "exp_q2.5_5_50_95_97.5": q(ex),
            "P_exp<=0": round(float((ex <= 0).mean()), 4), "P_pf<1.10": round(float((pfs < 1.10).mean()), 4),
            "P_pf<1.20": round(float((pfs < 1.20).mean()), 4)}


def iid(R):
    return [R[rng.integers(0, len(R), len(R))] for _ in range(B)]


def cluster(t, freq):
    key = t.entry_time.dt.tz_convert(None).dt.to_period(freq)
    groups = [g.R.to_numpy() for _, g in t.groupby(key)]
    k = len(groups)
    res = []
    for _ in range(B):
        pick = rng.integers(0, k, k)
        res.append(np.concatenate([groups[i] for i in pick]))
    return res, k


def moving_block(t, weeks):
    """moving-block bootstrap on the calendar: blocks of `weeks` consecutive calendar weeks
    (empty weeks included), concatenated until the original span is covered."""
    wk = t.entry_time.dt.tz_convert(None).dt.to_period("W")
    allw = pd.period_range(wk.min(), wk.max(), freq="W")
    pos = {p: i for i, p in enumerate(allw)}
    wi = wk.map(pos).to_numpy()
    R = t.R.to_numpy()
    by_w = [R[wi == i] for i in range(len(allw))]
    nW = len(allw)
    nb = int(np.ceil(nW / weeks))
    res = []
    for _ in range(B // 2):
        starts = rng.integers(0, nW - weeks + 1, nb)
        res.append(np.concatenate([np.concatenate(by_w[s:s + weeks]) for s in starts]))
    return res


for per, t in (("is", TI), ("val", TV)):
    R = t.R.to_numpy()
    d = {"n": len(R), "pf": round(pf(R), 3), "exp": round(float(R.mean()), 4), "t": round(tstat(R), 2),
         "sd": round(float(R.std(ddof=1)), 3), "skew": round(float(stats.skew(R)), 2),
         "kurt_excess": round(float(stats.kurtosis(R)), 2)}
    d["iid"] = boot_stats(iid(R))
    cw, kw = cluster(t, "W")
    d["week_cluster"] = boot_stats(cw)
    d["week_cluster"]["n_weeks_with_trades"] = kw
    cm, km = cluster(t, "M")
    d["month_cluster"] = boot_stats(cm)
    d["month_cluster"]["n_months"] = km
    d["moving_block_4w"] = boot_stats(moving_block(t, 4))
    d["moving_block_13w"] = boot_stats(moving_block(t, 13))
    # cluster-robust t (weekly sums): t of weekly mean under iid weeks
    wsum = t.groupby(t.entry_time.dt.tz_convert(None).dt.to_period("W")).R.sum()
    wcnt = t.groupby(t.entry_time.dt.tz_convert(None).dt.to_period("W")).R.size()
    # ratio estimator variance (cluster-robust SE of the per-trade mean)
    mu = R.mean()
    resid = (wsum - mu * wcnt).to_numpy()
    se_cl = math.sqrt((resid ** 2).sum()) / len(R) * math.sqrt(len(resid) / (len(resid) - 1))
    d["t_cluster_week"] = round(float(mu / se_cl), 2)
    msum = t.groupby(t.entry_time.dt.tz_convert(None).dt.to_period("M")).R.sum()
    mcnt = t.groupby(t.entry_time.dt.tz_convert(None).dt.to_period("M")).R.size()
    resid = (msum - mu * mcnt).to_numpy()
    se_m = math.sqrt((resid ** 2).sum()) / len(R) * math.sqrt(len(resid) / (len(resid) - 1))
    d["t_cluster_month"] = round(float(mu / se_m), 2)
    # autocorrelation of trade R in sequence
    ac = [round(float(pd.Series(R).autocorr(l)), 3) for l in (1, 2, 3, 5, 10)]
    lb = stats.chi2.sf(len(R) * (len(R) + 2) * sum((pd.Series(R).autocorr(l) ** 2) / (len(R) - l) for l in range(1, 11)), 10)
    d["autocorr_lag1_2_3_5_10"] = ac
    d["ljungbox10_p"] = round(float(lb), 3)
    # concentration
    Rs = np.sort(R)[::-1]
    tot = R.sum()
    conc = {}
    for frac in (0.01, 0.05, 0.10):
        k = max(1, int(round(frac * len(R))))
        conc[f"top{int(frac*100)}pct_share"] = round(float(Rs[:k].sum() / tot), 2)
    for k in (1, 3, 5, 10, 25):
        rest = Rs[k:]
        conc[f"pf_without_top{k}"] = round(pf(rest), 3)
        conc[f"exp_without_top{k}"] = round(float(rest.mean()), 4)
    # how many top trades must be removed for PF < 1.0 / exp <= 0
    cs = np.cumsum(Rs)
    conc["n_top_trades_to_zero_total"] = int(np.argmax(tot - cs <= 0) + 1)
    conc["largest_win_R"] = round(float(Rs[0]), 2)
    conc["mean_win_R_top10"] = [round(float(x), 2) for x in Rs[:10]]
    wk = t.groupby(t.exit_time.dt.tz_convert(None).dt.to_period("W")).R.sum().sort_values(ascending=False)
    conc["top5_weeks_share"] = round(float(wk.iloc[:5].sum() / tot), 2)
    conc["top10_weeks_share"] = round(float(wk.iloc[:10].sum() / tot), 2)
    conc["n_top_weeks_to_zero"] = int(np.argmax(tot - np.cumsum(wk.to_numpy()) <= 0) + 1)
    conc["n_weeks"] = int(len(wk))
    mo = t.groupby(t.exit_time.dt.tz_convert(None).dt.to_period("M")).R.sum().sort_values(ascending=False)
    conc["top3_months_share"] = round(float(mo.iloc[:3].sum() / tot), 2)
    conc["top3_months"] = {str(k): round(float(v), 1) for k, v in mo.iloc[:3].items()}
    yr = t.groupby(t.entry_time.dt.year).R.sum().sort_values(ascending=False)
    best = yr.index[0]
    rest = t[t.entry_time.dt.year != best].R.to_numpy()
    conc["best_year"] = int(best)
    conc["best_year_share"] = round(float(yr.iloc[0] / tot), 2)
    conc["pf_without_best_year"] = round(pf(rest), 3)
    conc["t_without_best_year"] = round(tstat(rest), 2)
    rest2 = t[~t.entry_time.dt.year.isin(yr.index[:2])].R.to_numpy()
    conc["pf_without_best_2_years"] = round(pf(rest2), 3)
    conc["t_without_best_2_years"] = round(tstat(rest2), 2)
    d["concentration"] = conc
    # by year x side
    tab = {}
    for y, g in t.groupby(t.entry_time.dt.year):
        row = {}
        for nm, m in (("all", g.side != 0), ("long", g.side > 0), ("short", g.side < 0)):
            r = g.R[m].to_numpy()
            row[nm] = [int(len(r)), round(float(r.sum()), 1), round(pf(r), 2) if len(r) else None]
        tab[int(y)] = row
    d["by_year"] = tab
    # heterogeneity of yearly mean R (Kruskal + one-way ANOVA)
    groups = [g.R.to_numpy() for _, g in t.groupby(t.entry_time.dt.year)]
    d["years_anova_p"] = round(float(stats.f_oneway(*groups).pvalue), 3)
    d["years_kruskal_p"] = round(float(stats.kruskal(*groups).pvalue), 3)
    Rl, Rsh = t.R[t.side > 0].to_numpy(), t.R[t.side < 0].to_numpy()
    d["long"] = {"n": len(Rl), "exp": round(float(Rl.mean()), 4), "t": round(tstat(Rl), 2), "pf": round(pf(Rl), 3)}
    d["short"] = {"n": len(Rsh), "exp": round(float(Rsh.mean()), 4), "t": round(tstat(Rsh), 2), "pf": round(pf(Rsh), 3)}
    d["long_vs_short_welch_p"] = round(float(stats.ttest_ind(Rl, Rsh, equal_var=False).pvalue), 3)
    # rolling 12m windows (monthly steps): PF and exp
    t2 = t.set_index(t.entry_time.dt.tz_convert(None))
    months = pd.period_range(t2.index.min().to_period("M"), t2.index.max().to_period("M"), freq="M")
    roll = []
    for i in range(len(months) - 11):
        a, b = months[i].start_time, months[i + 11].end_time
        r = t2.R[(t2.index >= a) & (t2.index <= b)].to_numpy()
        if len(r) > 10:
            roll.append((str(months[i]), len(r), pf(r), r.mean()))
    rp = np.array([x[2] for x in roll])
    d["rolling12m"] = {"n_windows": len(roll), "frac_pf_gt_1": round(float((rp > 1).mean()), 3),
                       "frac_pf_gt_1.2": round(float((rp > 1.2).mean()), 3),
                       "pf_q5_25_50_75_95": [round(float(np.percentile(rp, p)), 2) for p in (5, 25, 50, 75, 95)],
                       "worst": [roll[int(np.argmin(rp))][0], round(float(rp.min()), 2)],
                       "best": [roll[int(np.argmax(rp))][0], round(float(rp.max()), 2)]}
    out[per] = d

# regimes: gold trend / volatility at the decision, causal
m1 = gl.load_m1("xauusd")
D = S.daily_bars(m1)
dc = pd.Series(D["c"].to_numpy(), index=pd.DatetimeIndex(D["t_close"]))
dc = dc[~dc.index.duplicated()].sort_index()
h4 = S.bars_cached(m1, "4h")
a4 = gl.atr(h4, 14)
a4 = pd.Series(a4.to_numpy() / h4["c"].to_numpy(), index=pd.DatetimeIndex(h4["t_close"]))
a4rank = a4.rolling(6 * 250, min_periods=300).rank(pct=True)          # trailing 1y percentile of ATR%
reg = {}
for per, t in (("is", TI), ("val", TV)):
    dt = pd.DatetimeIndex(t["dec_time"])
    pos = np.searchsorted(dc.index.values, dt.values, side="right") - 1
    rr = {}
    for L in (20, 60, 200):
        ma = dc.rolling(L).mean()
        above = (dc > ma).to_numpy()[pos]
        trend_up = above
        for nm, m in (("up", trend_up), ("down", ~trend_up)):
            for sn, sm in (("long", t.side.to_numpy() > 0), ("short", t.side.to_numpy() < 0)):
                r = t.R.to_numpy()[m & sm]
                rr[f"ma{L}_{nm}_{sn}"] = [int(len(r)), round(float(r.sum()), 1), round(pf(r), 2) if len(r) else None,
                                          round(tstat(r), 2) if len(r) > 2 else None]
        with_tr = ((t.side.to_numpy() > 0) & trend_up) | ((t.side.to_numpy() < 0) & ~trend_up)
        for nm, m in (("with_trend", with_tr), ("counter_trend", ~with_tr)):
            r = t.R.to_numpy()[m]
            rr[f"ma{L}_{nm}"] = [int(len(r)), round(float(r.sum()), 1), round(pf(r), 2), round(tstat(r), 2)]
    pa = np.searchsorted(a4rank.index.values, dt.values, side="right") - 1
    vr = a4rank.to_numpy()[pa]
    for lo_, hi_ in ((0, 1 / 3), (1 / 3, 2 / 3), (2 / 3, 1.01)):
        m = (vr >= lo_) & (vr < hi_)
        r = t.R.to_numpy()[m]
        rr[f"vol_tercile_{lo_:.2f}"] = [int(len(r)), round(float(r.sum()), 1), round(pf(r), 2), round(tstat(r), 2)]
    reg[per] = rr
out["regimes"] = reg
# every-signal concentration of the VAL year 2025
for per, e in (("is", EI), ("val", EV)):
    out[f"every_{per}_by_year"] = {int(y): [int(len(g)), round(float(g.R.sum()), 1), round(pf(g.R), 2)]
                                   for y, g in e.groupby(e.entry_time.dt.year)}


def cl_se(t, freq):
    R = t.R.to_numpy()
    mu = R.mean()
    k = t.entry_time.dt.tz_convert(None).dt.to_period(freq)
    s = t.groupby(k).R.sum()
    c = t.groupby(k).R.size()
    resid = (s - mu * c).to_numpy()
    return float(math.sqrt((resid ** 2).sum()) / len(R) * math.sqrt(len(resid) / (len(resid) - 1)))


# every-signal mean with overlap-robust (calendar-cluster) standard errors; skipped-only too
for per, e, tk in (("is", EI, TI), ("val", EV, TV)):
    sk = e[~e.oid.isin(set(tk.oid))]
    row = {}
    for nm, x in (("every", e), ("skipped", sk), ("taken", tk)):
        se_w, se_m = cl_se(x, "W"), cl_se(x, "M")
        row[nm] = {"n": len(x), "mean": round(float(x.R.mean()), 4), "se_week": round(se_w, 4), "se_month": round(se_m, 4),
                   "z_vs_0_month": round(float(x.R.mean() / se_m), 2),
                   "z_vs_IS_chain_0.123_month": round(float((x.R.mean() - 0.1233) / se_m), 2)}
    # paired: taken minus skipped, month-cluster bootstrap
    km_t = tk.entry_time.dt.tz_convert(None).dt.to_period("M")
    km_s = sk.entry_time.dt.tz_convert(None).dt.to_period("M")
    allm = sorted(set(km_t) | set(km_s))
    gt = {m: g.R.to_numpy() for m, g in tk.groupby(km_t)}
    gs = {m: g.R.to_numpy() for m, g in sk.groupby(km_s)}
    diffs = []
    for _ in range(5000):
        pick = [allm[i] for i in rng.integers(0, len(allm), len(allm))]
        a = np.concatenate([gt.get(m, np.empty(0)) for m in pick])
        b = np.concatenate([gs.get(m, np.empty(0)) for m in pick])
        diffs.append(a.mean() - b.mean())
    diffs = np.array(diffs)
    row["taken_minus_skipped"] = {"obs": round(float(tk.R.mean() - sk.R.mean()), 4),
                                  "boot_month_q5_50_95": [round(float(np.percentile(diffs, p)), 4) for p in (5, 50, 95)],
                                  "boot_sd": round(float(diffs.std()), 4)}
    out[f"every_signal_inference_{per}"] = row
json.dump(out, open(os.path.join(HERE, "s04_boot_conc.json"), "w"), indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
