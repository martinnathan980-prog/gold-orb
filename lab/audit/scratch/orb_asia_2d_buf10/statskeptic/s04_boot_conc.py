"""Bootstrap (iid, week-block, month-block), zero-net centred bootstrap, concentration, stability by
year/side, random-effects across years, and regime splits for the candidate (normal costs).
Uses the trades saved by s01 (VAL trades came from one logged gl.cut)."""
import json

from scipy import stats

from common import *  # noqa

ti = pd.read_parquet(os.path.join(HERE, "cand_trades_is.parquet"))
tv = pd.read_parquet(os.path.join(HERE, "cand_trades_val.parquet"))
TI, TV = ti[ti.cost == "normal"].copy(), tv[tv.cost == "normal"].copy()
TA = pd.concat([TI, TV])
out = {}
rng = np.random.default_rng(42)
B = 10000


def week_key(t):
    return t.entry_time.dt.tz_convert(None).dt.to_period("W")


def month_key(t):
    return t.entry_time.dt.tz_convert(None).dt.to_period("M")


def block_boot(t, keyf, shift=0.0, nb=B, per_start=None, per_end=None, freq="W"):
    """Resample calendar blocks (incl. empty ones) with replacement; returns arrays pf, exp, t, n."""
    R = t.R.to_numpy() - shift
    k = keyf(t)
    allk = pd.period_range(per_start, per_end, freq=freq)
    code = allk.get_indexer(k)
    assert (code >= 0).all(), "trade outside block range"
    nbk = len(allk)
    # per-block sums of positive, negative, R, R^2, count
    pos = np.bincount(code, weights=np.where(R > 0, R, 0), minlength=nbk)
    neg = np.bincount(code, weights=np.where(R < 0, -R, 0), minlength=nbk)
    s1 = np.bincount(code, weights=R, minlength=nbk)
    s2 = np.bincount(code, weights=R * R, minlength=nbk)
    cnt = np.bincount(code, minlength=nbk).astype(float)
    pfs, exs, tss, ns = (np.empty(nb) for _ in range(4))
    for b in range(nb):
        ix = rng.integers(0, nbk, nbk)
        P, Ng, S1, S2, Nn = pos[ix].sum(), neg[ix].sum(), s1[ix].sum(), s2[ix].sum(), cnt[ix].sum()
        m = S1 / Nn
        var = (S2 - Nn * m * m) / (Nn - 1)
        pfs[b], exs[b], tss[b], ns[b] = P / Ng, m, m / math.sqrt(var / Nn), Nn
    return pfs, exs, tss, ns


def iid_boot(t, shift=0.0, nb=B):
    R = t.R.to_numpy() - shift
    n = len(R)
    pfs, exs, tss = (np.empty(nb) for _ in range(3))
    for b in range(nb):
        s = R[rng.integers(0, n, n)]
        pfs[b], exs[b], tss[b] = pf(s), s.mean(), tstat(s)
    return pfs, exs, tss, np.full(nb, n)


def q(a):
    return [round(float(np.percentile(a, p)), 3) for p in (2.5, 5, 50, 95, 97.5)]


PER = {"is": ("2013-01", "2021-12"), "val": ("2022-01", "2025-12")}
boot = {}
for per, t in (("is", TI), ("val", TV)):
    a, b = PER[per]
    for nm, fn in (("iid", lambda tt, sh: iid_boot(tt, sh)),
                   ("week", lambda tt, sh: block_boot(tt, week_key, sh, per_start=a + "-01", per_end=b + "-31", freq="W")),
                   ("month", lambda tt, sh: block_boot(tt, month_key, sh, per_start=a, per_end=b, freq="M"))):
        pfs, exs, tss, ns = fn(t, 0.0)
        d = {"pf_q2.5_5_50_95_97.5": q(pfs), "exp_q": q(exs), "P(exp<=0)": round(float((exs <= 0).mean()), 4),
             "P(pf>=1.20)": round(float((pfs >= 1.20).mean()), 4), "P(pf>=1.10)": round(float((pfs >= 1.10).mean()), 4),
             "P(pf<1.0)": round(float((pfs < 1.0).mean()), 4), "sd_exp": round(float(exs.std()), 4)}
        # zero-net null: centred (demeaned) resampling -> how often does luck alone give the observed stats?
        mu = float(t.R.mean())
        pfs0, exs0, tss0, ns0 = fn(t, mu)
        d["zero_net_null"] = {"P(pf>=1.20 & t>=2)": round(float(((pfs0 >= 1.2) & (tss0 >= 2)).mean()), 4),
                              "P(pf>=obs_is_level 1.1773 & t>=1.83)": round(float(((pfs0 >= 1.1773) & (tss0 >= 1.83)).mean()), 4),
                              "P(pf>=1.10 & exp>0)": round(float(((pfs0 >= 1.10) & (exs0 > 0)).mean()), 4),
                              "P(pf>=obs)": round(float((pfs0 >= pf(t.R)).mean()), 4),
                              "pf_q": q(pfs0), "t_sd": round(float(tss0.std()), 3)}
        boot[f"{per}/{nm}"] = d
out["bootstrap"] = boot

# ---------------------------------------------------------------- concentration
def conc(t):
    R = np.sort(t.R.to_numpy())[::-1]
    tot = R.sum()
    n = len(R)
    res = {"n": n, "total_R": round(float(tot), 1)}
    for f in (0.01, 0.05, 0.10):
        k = max(1, int(round(f * n)))
        res[f"top{int(f * 100)}pct_trades_share_of_total"] = round(float(R[:k].sum() / tot), 2)
    for k in (5, 10, 20, 50):
        rest = R[k:]
        res[f"pf_without_top{k}"] = round(pf(rest), 3)
        res[f"exp_without_top{k}"] = round(float(rest.mean()), 4)
    wk = t.groupby(week_key(t)).R.sum().sort_values(ascending=False)
    for k in (5, 10, 20):
        res[f"top{k}_weeks_share_of_total"] = round(float(wk.iloc[:k].sum() / tot), 2)
    mo = t.groupby(month_key(t)).R.sum().sort_values(ascending=False)
    res["top3_months_share"] = round(float(mo.iloc[:3].sum() / tot), 2)
    res["top_month"] = [str(mo.index[0]), round(float(mo.iloc[0]), 1)]
    res["max_R_trade"] = round(float(R[0]), 2)
    return res


out["concentration"] = {"is": conc(TI), "val": conc(TV), "is+val": conc(TA)}

# leave-one-year-out
def loyo(t):
    yrs = t.entry_time.dt.year
    res = {}
    for y in sorted(yrs.unique()):
        s = t[yrs != y]
        res[int(y)] = {"pf_without": round(pf(s.R), 3), "t_without": round(tstat(s.R), 2)}
    return res


out["leave_one_year_out"] = {"is": loyo(TI), "is+val": loyo(TA)}

# ---------------------------------------------------------------- stability by year and side
yr = TA.entry_time.dt.year
by = []
for y, g in TA.groupby(yr):
    R = g.R.to_numpy()
    s = g.side.to_numpy()
    by.append({"year": int(y), "n": len(R), "sumR": round(float(R.sum()), 1), "exp": round(float(R.mean()), 4),
               "se": round(float(R.std(ddof=1) / math.sqrt(len(R))), 4), "pf": round(pf(R), 3), "t": round(tstat(R), 2),
               "long_n": int((s > 0).sum()), "long_R": round(float(R[s > 0].sum()), 1), "long_pf": round(pf(R[s > 0]), 3),
               "short_n": int((s < 0).sum()), "short_R": round(float(R[s < 0].sum()), 1), "short_pf": round(pf(R[s < 0]), 3)})
out["by_year"] = by
yd = pd.DataFrame(by)


def random_effects(df):
    """DerSimonian-Laird across years of per-trade mean R."""
    y, se = df.exp.to_numpy(), df.se.to_numpy()
    w = 1 / se ** 2
    fe = float(np.sum(w * y) / np.sum(w))
    Q = float(np.sum(w * (y - fe) ** 2))
    k = len(y)
    c = np.sum(w) - np.sum(w ** 2) / np.sum(w)
    tau2 = max(0.0, (Q - (k - 1)) / c)
    wr = 1 / (se ** 2 + tau2)
    re = float(np.sum(wr * y) / np.sum(wr))
    re_se = float(math.sqrt(1 / np.sum(wr)))
    return {"k": k, "fixed_mean": round(fe, 4), "Q": round(Q, 2), "p_Q": round(float(1 - stats.chi2.cdf(Q, k - 1)), 4),
            "I2": round(max(0.0, (Q - (k - 1)) / Q), 3) if Q > 0 else 0.0, "tau": round(math.sqrt(tau2), 4),
            "re_mean": round(re, 4), "re_se": round(re_se, 4), "re_t": round(re / re_se, 2),
            "pred_sd_new_year_mean_R(excl sampling)": round(math.sqrt(tau2), 4)}


out["random_effects_years"] = {"is": random_effects(yd[yd.year <= 2021]), "is+val": random_effects(yd),
                               "val": random_effects(yd[yd.year >= 2022])}
# Welch ANOVA-like: Kruskal across years (distribution-free)
out["kruskal_years_is+val_p"] = round(float(stats.kruskal(*[g.R.to_numpy() for _, g in TA.groupby(yr)]).pvalue), 4)

# side by period: difference short - long
def side_diff(t):
    a, b = t.R[t.side > 0].to_numpy(), t.R[t.side < 0].to_numpy()
    d = b.mean() - a.mean()
    se = math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    return {"long_exp": round(float(a.mean()), 4), "short_exp": round(float(b.mean()), 4), "short_minus_long": round(float(d), 4),
            "t": round(float(d / se), 2), "long_t": round(tstat(a), 2), "short_t": round(tstat(b), 2)}


out["side"] = {"is": side_diff(TI), "val": side_diff(TV), "is+val": side_diff(TA)}
# interaction: (short-long)_IS - (short-long)_VAL
a, b = out["side"]["is"], out["side"]["val"]
se_i = abs(a["short_minus_long"] / a["t"]) if a["t"] else np.nan
se_v = abs(b["short_minus_long"] / b["t"]) if b["t"] else np.nan
out["side"]["flip_test"] = {"diff_of_diffs": round(a["short_minus_long"] - b["short_minus_long"], 4),
                            "t": round((a["short_minus_long"] - b["short_minus_long"]) / math.sqrt(se_i ** 2 + se_v ** 2), 2)}

# ---------------------------------------------------------------- regimes (causal, known at entry)
m1 = gl.load_m1("xauusd")
d = gl.bars(m1, "D")
d = d[["o", "h", "l", "c", "t_close"]].copy()
d["ret20"] = d.c / d.c.shift(20) - 1
d["ma60"] = d.c.rolling(60).mean()
d["atr14"] = gl.atr(d, 14) / d.c
d["atr_rel"] = d.atr14 / d.atr14.rolling(250, min_periods=120).median()
d["er20"] = (d.c - d.c.shift(20)).abs() / (d.c.diff().abs().rolling(20).sum())   # Kaufman efficiency ratio
d = d.dropna(subset=["t_close"])
feat = d.set_index(pd.DatetimeIndex(d.t_close))[["c", "ret20", "ma60", "atr_rel", "er20"]]


def attach(t):
    f = feat.reindex(pd.DatetimeIndex(t.entry_time), method="ffill")
    t = t.copy()
    for c in f.columns:
        t[c] = f[c].to_numpy()
    t["aligned20"] = np.sign(t.ret20) == t.side
    t["above_ma60"] = t.c > t.ma60
    return t


def split(t, col, bins=None, labels=None):
    res = {}
    if bins is None:
        groups = t.groupby(col)
    else:
        groups = t.groupby(pd.cut(t[col], bins=bins, labels=labels), observed=True)
    for k, g in groups:
        R = g.R.to_numpy()
        if len(R) < 5:
            continue
        res[str(k)] = {"n": len(R), "pf": round(pf(R), 3), "exp": round(float(R.mean()), 4), "t": round(tstat(R), 2),
                       "sumR": round(float(R.sum()), 1)}
    return res


reg = {}
for per, t in (("is", TI), ("val", TV)):
    t = attach(t)
    # terciles from IS only (fixed thresholds)
    if per == "is":
        thr_atr = np.nanpercentile(t.atr_rel, [33.3, 66.7])
        thr_er = np.nanpercentile(t.er20, [33.3, 66.7])
    reg[per] = {"trend_aligned_20d": split(t, "aligned20"), "above_ma60_x_side": split(t.assign(k=t.above_ma60.map({True: "above", False: "below"}) + "/" + t.side.map({1: "long", -1: "short"})), "k"),
                "vol_regime(atr_rel IS terciles)": split(t, "atr_rel", bins=[-np.inf, thr_atr[0], thr_atr[1], np.inf], labels=["lowvol", "midvol", "highvol"]),
                "trendiness(ER20 IS terciles)": split(t, "er20", bins=[-np.inf, thr_er[0], thr_er[1], np.inf], labels=["choppy", "mid", "trending"]),
                "dow": split(t.assign(dow=t.entry_time.dt.tz_convert("Europe/London").dt.dayofweek), "dow")}
out["regimes"] = reg
out["regime_thresholds"] = {"atr_rel": [round(float(x), 3) for x in thr_atr], "er20": [round(float(x), 3) for x in thr_er]}

# yearly gold return vs yearly side R (is the side split just the year's drift?)
dc = d.set_index(pd.DatetimeIndex(d.t_close)).c
yret = dc.groupby(dc.index.year).last() / dc.groupby(dc.index.year).first() - 1
yd["gold_ret"] = yd.year.map(yret)
yd["long_minus_short_R"] = yd.long_R - yd.short_R
yd["absret"] = yd.gold_ret.abs()
out["yearly_vs_gold"] = {"corr(long_minus_short_R, gold_ret)": round(float(np.corrcoef(yd.long_minus_short_R, yd.gold_ret)[0, 1]), 3),
                         "corr(total_R, |gold_ret|)": round(float(np.corrcoef(yd.sumR, yd.absret)[0, 1]), 3),
                         "spearman(total_R, |gold_ret|)": round(float(stats.spearmanr(yd.sumR, yd.absret).correlation), 3),
                         "table": yd[["year", "gold_ret", "sumR", "long_R", "short_R"]].round(3).to_dict("records")}
json.dump(out, open(os.path.join(HERE, "s04_boot_conc.json"), "w"), indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
