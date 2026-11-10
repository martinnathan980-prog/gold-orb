"""In-sample diagnostics of the finalist candidate (no new configuration; IS trades only)."""
from common import *
import json
from goldlab.split import cut
F = {"rule": "xlead", "leader": "us100", "pred": "lead", "sess": "uscash", "dirn": 1, "k": 1, "z": 6, "hold": 60, "stop": 2.0}
SYM = "btcusd"
use(SYM)
m1 = r2.load(SYM)

def is_trades(mode, no_overlap=True):
    return cut(r2.run(SYM, strategy.make_orders, F, mode, no_overlap, m1), "is")      # IS ONLY

t = is_trades("fp"); g = is_trades("gross"); s = is_trades("stress")
out = {}
bp = lambda x: float((x.pnl / x.entry).mean() * 1e4)
# 1) gross / net edge per trade by year and by half
mid = pd.Timestamp("2019-10-01", tz="UTC")
out["by_year"] = {}
for y, gy in g.groupby(g.entry_time.dt.year):
    ty = t[t.entry_time.dt.year == y]
    out["by_year"][int(y)] = {"n": int(len(ty)), "gross_bps": round(bp(gy), 2), "net_bps": round(bp(ty), 2), "net_R": round(float(ty.R.sum()), 1),
                              "net_pf": round(float(ty.R[ty.R > 0].sum() / -ty.R[ty.R < 0].sum()), 3)}
h1g, h2g = g[g.entry_time < mid], g[g.entry_time >= mid]
h1t, h2t = t[t.entry_time < mid], t[t.entry_time >= mid]
out["halves"] = {"first_half_2017-06..2019-09": {"n": int(len(h1t)), "gross_bps": round(bp(h1g), 2), "net_bps": round(bp(h1t), 2), "net_expR": round(float(h1t.R.mean()), 4)},
                 "second_half_2019-10..2021-12": {"n": int(len(h2t)), "gross_bps": round(bp(h2g), 2), "net_bps": round(bp(h2t), 2), "net_expR": round(float(h2t.R.mean()), 4)}}
# 2) concentration
day = t.entry_time.dt.tz_convert("America/New_York").dt.date
byday = t.groupby(day)["R"].sum().sort_values(ascending=False)
tot = float(t.R.sum())
out["concentration"] = {"total_R": round(tot, 1), "n_days_traded": int(len(byday)), "top5_days_R": round(float(byday.head(5).sum()), 1),
                        "top10_days_R": round(float(byday.head(10).sum()), 1), "top10_days": [str(d) for d in byday.head(10).index],
                        "worst5_days_R": round(float(byday.tail(5).sum()), 1),
                        "share_days_positive": round(float((byday > 0).mean()), 3)}
m20 = (t.entry_time >= pd.Timestamp("2020-02-20", tz="UTC")) & (t.entry_time < pd.Timestamp("2020-04-15", tz="UTC"))
x = t[~m20]
out["ex_covid_crash_2020-02-20..04-14"] = {"n": int(len(x)), "expR": round(float(x.R.mean()), 4), "pf": round(float(x.R[x.R > 0].sum() / -x.R[x.R < 0].sum()), 3),
                                           "t": round(float(x.R.mean() / (x.R.std(ddof=1) / np.sqrt(len(x)))), 2), "R_in_window": round(float(t[m20].R.sum()), 1), "n_in_window": int(m20.sum())}
mo = t.groupby(t.entry_time.dt.tz_convert(None).dt.to_period("M"))["R"].sum()
out["months"] = {"n": int(len(mo)), "positive": int((mo > 0).sum()), "best": round(float(mo.max()), 1), "worst": round(float(mo.min()), 1)}
# 3) day-clustered t (trades of the same day are not independent)
dsum = t.groupby(day)["R"].sum()
out["t_by_day_cluster"] = round(float(dsum.sum() / np.sqrt((dsum ** 2).sum())), 2)
wk = t.groupby(t.entry_time.dt.tz_convert(None).dt.to_period("W"))["R"].sum()
out["t_by_week_cluster"] = round(float(wk.sum() / np.sqrt((wk ** 2).sum())), 2)
# 4) entry time of day, trades per active day, side split
ny = t.entry_time.dt.tz_convert("America/New_York")
hh = (ny.dt.hour * 60 + ny.dt.minute)
bins = pd.cut(hh, [570, 600, 660, 720, 780, 840, 900, 961], right=False, labels=["09:30", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00"])
out["by_entry_time_NY"] = {str(k): {"n": int(len(v)), "expR": round(float(v.R.mean()), 4), "bps": round(bp(v), 2)} for k, v in t.groupby(bins, observed=True)}
out["side"] = {"long": {"n": int((t.side > 0).sum()), "expR": round(float(t[t.side > 0].R.mean()), 4), "bps": round(bp(t[t.side > 0]), 2), "gross_bps": round(bp(g[g.side > 0]), 2)},
               "short": {"n": int((t.side < 0).sum()), "expR": round(float(t[t.side < 0].R.mean()), 4), "bps": round(bp(t[t.side < 0]), 2), "gross_bps": round(bp(g[g.side < 0]), 2)}}
out["exit_reason"] = {k: {"n": int(len(v)), "meanR": round(float(v.R.mean()), 3)} for k, v in t.groupby("reason")}
out["cost_per_trade_bps"] = round(bp(g) - bp(t), 2)
out["stop_bps_of_price_IS_median"] = round(float((t.risk / t.entry).median() * 1e4), 1)
# 5) stop distance in 2024-2025 (orders only: no P&L is looked at) and money value on the minimum lot
o = strategy.make_orders(m1, **F)
et = m1.index[o.entry_i.to_numpy()]
m = (et >= pd.Timestamp("2024-01-01", tz="UTC")) & (et < pd.Timestamp("2026-01-01", tz="UTC"))
sd = o.stop_dist[m]
sp = r2.SPEC[SYM]
out["stop_2024_25"] = {"n_orders": int(m.sum()), "median_stop_dist_usd": round(float(sd.median()), 1), "p90": round(float(sd.quantile(0.9)), 1),
                       "min_lot": sp["min_lot"], "units_per_lot": sp["units_per_lot"],
                       "money_on_min_lot_usd": round(float(sd.median()) * sp["min_lot"] * sp["units_per_lot"], 2)}
json.dump(out, open(os.path.join(RES, "diag_nq_btc.json"), "w"), indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
