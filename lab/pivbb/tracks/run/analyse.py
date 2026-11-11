"""In-sample diagnostics of the two candidates (trades are cut to the in-sample period right after the engine run)."""
import sys, json
sys.path.insert(0, "/home/user/gold-orb/lab")
import numpy as np, pandas as pd
from goldlab import r2
from goldlab.split import cut
from pivbb.tracks.run import strategy as S
OUT = "/home/user/gold-orb/lab/results/pivbb/run"
CAND = {"r2s2_touch_run": dict(levels=["D_R2", "D_S2"], entry="touch"),
        "outer_close_ride": dict(levels=["D_R2", "D_S2", "D_R3", "D_S3"], hours=[2, 12], target=None)}
res = {}
T = {}
for name, prm in CAND.items():
    t = cut(r2.run("xauusd", S.make_orders, prm, "fp"), "is").copy()
    g = cut(r2.run("xauusd", S.make_orders, prm, "gross"), "is").copy()
    T[name] = t
    t.to_csv(f"{OUT}/is_trades_{name}.csv")
    yr = t.entry_time.dt.year
    gy = g.entry_time.dt.year
    R = t.R.to_numpy()
    srt = np.sort(R)[::-1]
    d = {"n": len(t), "sum_R": round(float(R.sum()), 1), "mean_R": round(float(R.mean()), 4), "median_R": round(float(np.median(R)), 3),
         "max_R": round(float(R.max()), 2), "min_R": round(float(R.min()), 2), "top5_R": [round(float(x), 2) for x in srt[:5]],
         "sum_R_without_top10": round(float(srt[10:].sum()), 1), "mean_R_winsor_5R": round(float(np.clip(R, -5, 5).mean()), 4),
         "R_gt_5": int((R > 5).sum()), "R_lt_m1.5": int((R < -1.5).sum()),
         "risk_atr_quantiles": [round(float(x), 3) for x in np.quantile(t.risk / t.atr_d, [0.01, 0.05, 0.25, 0.5, 0.75, 0.95])],
         "by_reason": t.groupby("reason").R.agg(["size", "mean"]).round(3).to_dict("index"),
         "by_level": t.groupby("lv_name").R.agg(["size", "mean", "sum"]).round(3).to_dict("index"),
         "by_side": t.groupby("side").R.agg(["size", "mean", "sum"]).round(3).to_dict("index"),
         "by_year_net": t.groupby(yr).R.agg(["size", "mean", "sum"]).round(3).to_dict("index"),
         "by_year_gross_meanR": g.groupby(gy).R.mean().round(3).to_dict(),
         "gross_R_2013_2017": round(float(g.R[gy <= 2017].mean()), 4), "gross_R_2018_2021": round(float(g.R[gy >= 2018].mean()), 4),
         "net_R_2013_2017": round(float(t.R[yr <= 2017].mean()), 4), "net_R_2018_2021": round(float(t.R[yr >= 2018].mean()), 4),
         "gross_bps_2013_2017": round(float((g.pnl / g.entry)[gy <= 2017].mean() * 1e4), 2), "gross_bps_2018_2021": round(float((g.pnl / g.entry)[gy >= 2018].mean() * 1e4), 2),
         "n_2013_2017": int((yr <= 2017).sum()), "n_2018_2021": int((yr >= 2018).sum()),
         "median_stop_usd_2020_2021": round(float(t.risk[yr >= 2020].median()), 2), "p90_stop_usd_2020_2021": round(float(t.risk[yr >= 2020].quantile(0.9)), 2),
         "median_hold_min": float(t.hold_min.median()), "trades_per_year": round(len(t) / 8.94, 1),
         "days_with_trade": int(t.entry_time.dt.date.nunique()),
         "by_hour_NY": t.groupby(t.entry_time.dt.tz_convert("America/New_York").dt.hour // 3 * 3).R.agg(["size", "mean"]).round(3).to_dict("index")}
    # t-stat with winsorised R and by-day clustering
    daily = t.groupby(t.entry_time.dt.tz_convert("America/New_York").dt.date).R.sum()
    d["t_daily_cluster"] = round(float(daily.mean() / daily.std(ddof=1) * np.sqrt(len(daily))), 2)
    w = np.clip(R, -3, 3)
    d["t_winsor_3R"] = round(float(w.mean() / w.std(ddof=1) * np.sqrt(len(w))), 2)
    res[name] = d
    print(name, json.dumps(d, indent=1, default=str))
json.dump(res, open(OUT + "/candidate_diagnostics.json", "w"), indent=1, default=str)
# overlap between the two candidates
da = T["r2s2_touch_run"].groupby(T["r2s2_touch_run"].entry_time.dt.date).R.sum()
db = T["outer_close_ride"].groupby(T["outer_close_ride"].entry_time.dt.date).R.sum()
j = pd.concat([da, db], axis=1).fillna(0)
print("corr of daily R between the two candidates:", j.corr().iloc[0, 1])
