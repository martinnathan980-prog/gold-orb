"""In-sample diagnostics of the two shortlisted rules (configurations already logged; nothing here selects
anything). Writes results/r2/crypto/finalist_diag.json. Uses 2024-2025 ONLY for the stop distance of the
orders (no trade result of the validation period is computed or read)."""
import sys, json
sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/crypto")
from helpers import *  # noqa
from goldlab.metrics import report

from final_cfg import FINAL, ALLDAYS

CFG = dict(FINAL) if (len(sys.argv) < 2 or sys.argv[1] != 'alldays') else dict(ALLDAYS)
OUTFILE = 'finalist_diag.json' if (len(sys.argv) < 2 or sys.argv[1] != 'alldays') else 'finalist_diag_alldays.json'
FX = 0.87   # USD -> EUR (lab convention, goldlab/portfolio.py)


def pf(x):
    g, l = x[x > 0].sum(), -x[x < 0].sum()
    return float(g / l) if l > 0 else float("nan")


def stats(t):
    if len(t) == 0:
        return {"n": 0}
    R = t.R.to_numpy()
    return {"n": int(len(t)), "exp_R": round(float(R.mean()), 4), "pf": round(pf(R), 3),
            "t": round(float(R.mean() / R.std(ddof=1) * np.sqrt(len(R))), 2) if len(R) > 2 else None,
            "bps": round(float((t.pnl / t.entry).mean() * 1e4), 2), "sum_R": round(float(R.sum()), 1),
            "win": round(float((R > 0).mean()), 3)}


if __name__ == "__main__":
    out = {}
    pooled = {k: {"fp": [], "stress": [], "gross": [], "every": []} for k in CFG}
    for sym in ("btcusd", "ethusd"):
        m1 = r2.load(sym)
        for name, p in CFG.items():
            d = {}
            t = gl.cut(r2.run(sym, S.make_orders, p, "fp", True, m1), "is")
            tg = gl.cut(r2.run(sym, S.make_orders, p, "gross", True, m1), "is")
            ts_ = gl.cut(r2.run(sym, S.make_orders, p, "stress", True, m1), "is")
            te = gl.cut(r2.run(sym, S.make_orders, p, "fp", False, m1), "is")
            for k, x in (("fp", t), ("stress", ts_), ("gross", tg), ("every", te)):
                pooled[name][k].append(x.assign(sym=sym))
            d["is"] = stats(t)
            d["long"] = stats(t[t.side > 0]); d["short"] = stats(t[t.side < 0])
            d["by_year"] = {int(y): {"long": stats(g[g.side > 0]), "short": stats(g[g.side < 0]), "all": stats(g)}
                            for y, g in t.groupby(t.entry_time.dt.year)}
            mid = t.entry_time.min() + (pd.Timestamp("2022-01-01", tz="UTC") - t.entry_time.min()) / 2
            d["halves_split_at"] = str(mid.date())
            d["first_half_net"] = stats(t[t.entry_time < mid]); d["second_half_net"] = stats(t[t.entry_time >= mid])
            d["first_half_gross"] = stats(tg[tg.entry_time < mid]); d["second_half_gross"] = stats(tg[tg.entry_time >= mid])
            d["y2021_net"] = stats(t[t.entry_time.dt.year == 2021]); d["y2021_gross"] = stats(tg[tg.entry_time.dt.year == 2021])
            d["ex_2017_net"] = stats(t[t.entry_time.dt.year > 2017])
            # exposure artefact of the 2017-2018 data (no weekend quotes): trades whose exit waited for the reopen
            early = t[t.entry_time.dt.year <= 2018]
            long_hold = early.hold_min > (float(p["hold_h"]) + 6) * 60
            d["2017_18_exit_delayed_by_closure"] = stats(early[long_hold]); d["2017_18_normal_exit"] = stats(early[~long_hold])
            delayed = t.hold_min > (float(p["hold_h"]) + 6) * 60
            d["is_excluding_closure_delayed_exits"] = dict(stats(t[~delayed]), n_excluded=int(delayed.sum()),
                                                           years_pos="%d/%d" % ((t[~delayed].groupby(t[~delayed].entry_time.dt.year).R.sum() > 0).sum(),
                                                                                t[~delayed].entry_time.dt.year.nunique()))
            wk = pd.DatetimeIndex(t.dec_time).dayofweek >= 5
            late = t.entry_time.dt.year >= 2019
            d["2019_21_weekend_decisions"] = stats(t[late & wk]); d["2019_21_weekday_decisions"] = stats(t[late & ~wk])
            top = np.sort(t.R.to_numpy())[::-1]; k5 = max(1, int(round(0.05 * len(t))))
            d["top5pct_share_of_total_R"] = round(float(top[:k5].sum() / t.R.sum()), 2)
            d["total_R_without_top5pct"] = round(float(top[k5:].sum()), 1)
            d["exit_reasons"] = t.reason.value_counts().to_dict()
            d["avg_win_R"] = round(float(t.R[t.R > 0].mean()), 3); d["avg_loss_R"] = round(float(t.R[t.R < 0].mean()), 3)
            d["swap_bps_per_trade"] = round(float((t.swap / t.entry).mean() * 1e4), 2)
            d["cost_bps_per_trade(gross-net)"] = round(float((tg.pnl / tg.entry).mean() * 1e4 - (t.pnl / t.entry).mean() * 1e4), 2)
            # stop distance of the orders decided in 2024-2025 (no trade simulated there)
            o = S.make_orders(m1, **p)
            oo = o[(o.dec_time >= pd.Timestamp("2024-01-01", tz="UTC")) & (o.dec_time < pd.Timestamp("2026-01-01", tz="UTC"))]
            spec = r2.SPEC[sym]
            med = float(oo.stop_dist.median())
            px = float(((m1["bc"].to_numpy() + m1["ac"].to_numpy()) / 2)[oo.entry_i.to_numpy()].mean()) if len(oo) else float("nan")
            d["stop_2024_25"] = {"median_stop_dist": round(med, 2), "p10": round(float(oo.stop_dist.quantile(0.1)), 2),
                                 "p90": round(float(oo.stop_dist.quantile(0.9)), 2),
                                 "median_stop_pct_of_price": round(float((oo.stop_dist / ((m1["bc"].to_numpy() + m1["ac"].to_numpy()) / 2)[oo.entry_i.to_numpy()]).median() * 100), 3),
                                 "min_lot_units": spec["min_lot"] * spec["units_per_lot"],
                                 "min_lot_stop_usd": round(med * spec["min_lot"] * spec["units_per_lot"], 2),
                                 "min_lot_stop_eur": round(med * spec["min_lot"] * spec["units_per_lot"] * FX, 2),
                                 "mean_price": round(px, 1),
                                 "min_lot_margin_usd": round(px * spec["min_lot"] * spec["units_per_lot"] / spec["leverage"], 2)}
            out[f"{name}:{sym}"] = d
            print(name, sym, json.dumps({k: d[k] for k in ("is", "long", "short", "first_half_gross", "second_half_gross", "y2021_gross",
                                                           "ex_2017_net", "is_excluding_closure_delayed_exits", "2017_18_exit_delayed_by_closure", "2017_18_normal_exit",
                                                           "2019_21_weekend_decisions", "2019_21_weekday_decisions",
                                                           "top5pct_share_of_total_R", "swap_bps_per_trade",
                                                           "cost_bps_per_trade(gross-net)", "stop_2024_25")}), flush=True)
        r2.free()
        # historical cost model (real Dukascopy bid/ask of the time), for information (PROTOCOL_V2 section 3c)
        raw = gl.load_m1(sym)
        for name, p in CFG.items():
            th = gl.cut(gl.simulate(raw, S.make_orders(raw, **p), sym=sym, costs=r2.costs(sym), no_overlap=True), "is")
            rep = report(th)
            out[f"{name}:{sym}"]["historical_dukascopy_spread"] = {k: rep.get(k) for k in ("n", "pf", "expectancy_R", "t_stat", "years_pos", "by_year_R")}
            out[f"{name}:{sym}"]["historical_dukascopy_spread"]["bps"] = round(float((th.pnl / th.entry).mean() * 1e4), 2)
            print(name, sym, "historical Dukascopy spread:", out[f"{name}:{sym}"]["historical_dukascopy_spread"], flush=True)
        gl.data._cache.clear()
    # basket (pooled trades of the two instruments)
    for name in CFG:
        b = {}
        for k in ("fp", "stress", "gross", "every"):
            x = pd.concat(pooled[name][k]).sort_values("entry_time")
            rep = report(x)
            b[k] = {q: rep.get(q) for q in ("n", "trades_per_year", "win_rate", "pf", "t_stat", "expectancy_R", "years_pos", "long_R", "short_R",
                                            "max_dd_R", "by_year_R", "weeks_pos_pct", "months_pos_pct")}
        out[f"{name}:basket"] = b
        print(name, "BASKET", json.dumps(b), flush=True)
    json.dump(out, open(os.path.join(OUT, OUTFILE), "w"), indent=1, default=str)
