"""IS-only: relation between the two leads on us100 (and their us500 versions): daily-R correlation, combined stats,
basket (pooled) statistics with a day-clustered t-stat."""
from diag import *    # noqa

def daily(t):
    d = t.entry_time.dt.tz_convert("America/New_York").dt.date
    return t.groupby(d.values).R.sum()

def pooled(ts):
    t = pd.concat(ts).sort_values("entry_time")
    rep = gl.report(t)
    dd = daily(t)
    # day-clustered t: mean trade R with clustering by NY date = t of daily sums scaled
    n_days = len(dd)
    clus_t = float(dd.mean() / (dd.std(ddof=1) / np.sqrt(n_days)))
    return {"n": rep["n"], "pf": rep["pf"], "t_naive": rep["t_stat"], "t_day_clustered": round(clus_t, 2), "expR": rep["expectancy_R"],
            "years_pos": rep["years_pos"], "max_dd_R": rep["max_dd_R"], "long_R": rep["long_R"], "short_R": rep["short_R"], "by_year_R": rep["by_year_R"]}

cfg = {"noise": dict(rule="noise"), "ocm_size": dict(rule="ocm", stop="atr", k=0.3, size_min=1.0), "ocm_all": dict(rule="ocm", stop="atr", k=0.3)}
T = {}
for sym in ("us100", "us500"):
    for k, p in cfg.items():
        T[(sym, k)] = is_trades(sym, p)
    r2.free()
D = pd.DataFrame({f"{s}:{k}": daily(t) for (s, k), t in T.items()}).fillna(0.0)
print("daily-R correlation matrix (all IS sessions with any trade, zeros when no trade):")
print(D.corr().round(2).to_string())
res = {"corr": D.corr().round(3).to_dict()}
for name, keys in {"noise us100+us500 basket": [("us100", "noise"), ("us500", "noise")],
                   "ocm_size us100+us500 basket": [("us100", "ocm_size"), ("us500", "ocm_size")],
                   "ocm_all us100+us500 basket": [("us100", "ocm_all"), ("us500", "ocm_all")],
                   "us100 noise + ocm_size (two sleeves)": [("us100", "noise"), ("us100", "ocm_size")],
                   "all four sleeves": [("us100", "noise"), ("us500", "noise"), ("us100", "ocm_size"), ("us500", "ocm_size")]}.items():
    r = pooled([T[k] for k in keys])
    res[name] = r
    print(name, json.dumps(r, default=str))
# same-day direction agreement between noise first trade and ocm_size on us100
a = T[("us100", "noise")]; b = T[("us100", "ocm_size")]
da = a.assign(day=a.entry_time.dt.tz_convert("America/New_York").dt.date).groupby("day").side.first()
db = b.assign(day=b.entry_time.dt.tz_convert("America/New_York").dt.date).groupby("day").side.first()
j = pd.concat([da, db], axis=1, keys=["noise", "ocm"]).dropna()
print("days with both a noise trade and an ocm_size trade:", len(j), "| same direction:", round(float((j.noise == j.ocm).mean()), 3))
json.dump(res, open(os.path.join(RES, "diag_corr_basket.json"), "w"), indent=1, default=str)
