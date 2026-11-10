"""In-sample dossier of the two finalists, written BEFORE any validation access:
full criteria (cost stress, gross, every-signal), neighbours, random-entry null (per sleeve and basket),
long/short, gross-edge erosion, 2024-25 stop sizes -> results/r2/ml/finalists_preval.json"""
import datetime as dt
import json
import sys

sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/ml")
from research import *  # noqa
from goldlab.sim import simulate
from goldlab.split import cut

GEN = {"stop_k": 2.0, "hold_h": 13.0}
FIN = {
    "F1_brk_ridge_filter": {
        "syms": ["btcusd", "ethusd"],
        "params": {**GEN, "model": "B1_ridge_full.json", "q": "0.5"},                 # frozen model (validation / holdout / EA)
        "params_is": {**GEN, "model": "B1_ridge_full.json", "oof": True, "q": "0.5"},  # walk-forward folds (in-sample numbers)
    },
    "F2_brk_unfiltered": {
        "syms": ["btcusd", "ethusd"],
        "params": dict(GEN),
        "params_is": dict(GEN),
    },
}


def null_means(sym, params, n_seeds=200, seed=0):
    """Same algorithm as r2.null_test(mode='day') but returns the per-seed (sum R, n) so that a basket null
    can be formed. Checked against r2.null_test below."""
    m1 = r2.load(sym)
    orders = S.make_orders(m1, **params).reset_index(drop=True)
    c = r2.costs(sym)
    t = cut(simulate(m1, orders, sym=sym, costs=c, no_overlap=True), "is")
    o = orders.loc[t.index]
    idx = m1.index
    fill_i = idx.searchsorted(t.entry_time.to_numpy())
    entry = t.entry.to_numpy(float)
    side = t.side.to_numpy()
    stop_rel = t.risk.to_numpy(float) / entry
    xi = o["exit_i"].to_numpy(np.int64)
    dur = np.where(xi >= 0, np.maximum(xi - fill_i, 1), -1)
    lo, hi, mod, order, bounds = r2._minute_groups(m1)
    mod_c = mod[np.clip(fill_i - lo, 0, hi - lo - 1)]
    mid = ((m1["bc"].to_numpy() + m1["ac"].to_numpy()) / 2)
    rng = np.random.default_rng(seed)
    n_bars = len(m1)
    sums, ns = [], []
    nan = np.full(len(t), np.nan)
    for _ in range(n_seeds):
        a, b = bounds[mod_c], bounds[mod_c + 1]
        ok = b > a
        pos = (a + (rng.random(len(t)) * np.maximum(b - a, 1)).astype(np.int64))
        ei = lo + order[np.minimum(pos, len(order) - 1)]
        px = mid[ei]
        no = pd.DataFrame({"entry_i": ei, "side": side, "stop_dist": stop_rel * px, "target_dist": nan,
                           "trail": nan, "be": nan,
                           "exit_i": np.where(dur >= 0, np.minimum(ei + dur, n_bars - 1), -1)})[ok]
        tn = cut(simulate(m1, no, sym=sym, costs=c, no_overlap=True), "is")
        sums.append(float(tn.R.sum()))
        ns.append(int(len(tn)))
    return float(t.R.sum()), int(len(t)), np.array(sums), np.array(ns)


def side_pf(t):
    out = {}
    for nm, s in (("long", 1), ("short", -1)):
        x = t[t.side == s].R
        g, l = x[x > 0].sum(), -x[x < 0].sum()
        out[nm] = {"n": int(len(x)), "R": round(float(x.sum()), 1), "pf": round(float(g / l), 3) if l > 0 else None,
                   "exp_R": round(float(x.mean()), 4) if len(x) else None}
    return out


def halves(tg):
    """Gross (zero-cost) edge per trade in the first and second half of the sleeve's in-sample life."""
    t0, t1 = tg.entry_time.min(), pd.Timestamp(IS_END, tz="UTC")
    mid = t0 + (t1 - t0) / 2
    out = {"split_at": str(mid.date())}
    for nm, x in (("first_half", tg[tg.entry_time < mid]), ("second_half", tg[tg.entry_time >= mid])):
        out[nm] = {"n": int(len(x)), "gross_R_per_trade": round(float(x.R.mean()), 4),
                   "gross_bps_per_trade": round(float((x.pnl / x.entry).mean() * 1e4), 2)}
    out["by_year_gross_R_per_trade"] = {int(k): round(float(v), 3) for k, v in tg.groupby(tg.entry_time.dt.year).R.mean().items()}
    out["by_year_gross_bps_per_trade"] = {int(k): round(float(v), 1) for k, v in
                                          (tg.pnl / tg.entry * 1e4).groupby(tg.entry_time.dt.year).mean().items()}
    return out


if __name__ == "__main__":
    nb = pd.read_csv(os.path.join(RES, "neighbours.csv"))
    out = {"decided_at_utc": dt.datetime.utcnow().isoformat(timespec="seconds"), "finalists": {}}
    trades = {}
    for sym in ["btcusd", "ethusd"]:
        m1_is = is_frame(sym)
        m1_full = r2.load(sym)
        for name, f in FIN.items():
            key = "F1" if name.startswith("F1") else "F2"
            p = f["params_is"]
            ev = trial(sym, p, stage="FIN", full=True, note=f"{name} full in-sample evaluation")
            nbs = nb[(nb.sym == sym) & (nb.fin == key)]
            med = float(nbs.pf.median())
            crit = r2.is_criteria(ev, neighbor_median_pf=med)
            nul = r2.null_test(sym, S.make_orders, p, mode="day")
            sR, n, sums, ns = null_means(sym, p)
            my_pct = float(((sums / np.maximum(ns, 1)) < sR / n).mean() * 100)
            t_fp = r2.run(sym, S.make_orders, p, "fp", True, m1_is)
            t_st = r2.run(sym, S.make_orders, p, "stress", True, m1_is)
            t_gr = r2.run(sym, S.make_orders, p, "gross", True, m1_is)
            t_ev = r2.run(sym, S.make_orders, p, "fp", False, m1_is)
            assert len(t_fp) == ev["is"]["n"] and abs(t_fp.R.sum() - ev["is"]["total_R"]) < 0.06, (len(t_fp), ev["is"]["n"])
            trades[(name, sym)] = {"fp": t_fp, "stress": t_st, "gross": t_gr, "every": t_ev, "null": (sR, n, sums, ns)}
            # stop distances in 2024-2025 (price data only: no trade result of 2022-25 is computed or read here)
            c = S.candidates(m1_full, **f["params"])
            c = c[S.select(c, **f["params"])]
            td = pd.DatetimeIndex(c["t_dec"])
            c24 = c[(td >= pd.Timestamp("2024-01-01", tz="UTC")) & (td < pd.Timestamp("2026-01-01", tz="UTC"))]
            sd = float(p["stop_k"]) * c24["A"]
            spec = r2.SPEC[sym]
            stop_med = float(sd.median())
            money = stop_med * spec["units_per_lot"] * spec["min_lot"]
            rep = ev["is"]
            out["finalists"].setdefault(name, {"syms": f["syms"], "params": f["params"], "params_is_walk_forward": f["params_is"], "sleeves": {}})
            out["finalists"][name]["sleeves"][sym] = {
                "is": rep, "is_bps_per_trade": ev["is_bps_per_trade"],
                "is_stress": ev["is_stress"], "is_gross": ev["is_gross"], "is_gross_bps_per_trade": ev["is_gross_bps_per_trade"],
                "is_every_signal": ev["is_every_signal"],
                "neighbour_pfs": sorted(nbs.pf.round(3).tolist()), "neighbour_median_pf": round(med, 3),
                "neighbours": nbs[["nb", "n", "pf", "expR", "t", "years"]].to_dict("records"),
                "is_criteria": crit, "null_test": nul, "null_replica_percentile": round(my_pct, 1),
                "long_short": side_pf(t_fp), "gross_edge_halves": halves(t_gr),
                "stops_2024_25": {"n_orders": int(len(c24)), "median_stop_dist_price": round(stop_med, 2),
                                  "median_stop_pct_of_price": round(float(np.median(sd.to_numpy() / m1_full["bo"].to_numpy()[c24["entry_i"].to_numpy()]) * 100), 3),
                                  "min_lot": spec["min_lot"], "units_per_lot": spec["units_per_lot"],
                                  "min_lot_stop_money_usd": round(money, 2), "min_lot_stop_money_eur_at_1.10": round(money / 1.10, 2),
                                  "orders_per_year_2024_25": round(len(c24) / 2.0, 1)},
                "is_pass": bool(crit["pass"] and nul.get("pass", False)),
            }
            print(sym, name, "| PASS" if crit["pass"] and nul.get("pass") else "| FAIL", line(ev))
            print("    crit:", crit)
            print("    null:", nul, "replica pct:", round(my_pct, 1))
            print("    stress PF", ev["is_stress"]["pf"], "gross PF", ev["is_gross"]["pf"], "gross bps", ev["is_gross_bps_per_trade"],
                  "every-signal expR", ev["is_every_signal"]["expectancy_R"], "nb median", round(med, 3))
            print("    long/short:", side_pf(t_fp))
            print("    halves:", halves(t_gr))
            print("    stops 24-25:", out["finalists"][name]["sleeves"][sym]["stops_2024_25"])
        r2.free()
    # baskets (btcusd + ethusd trades pooled)
    for name, f in FIN.items():
        tb = {k: pd.concat([trades[(name, s)][k] for s in f["syms"]]).sort_values("entry_time") for k in ("fp", "stress", "gross", "every")}
        rep = gl.report(tb["fp"])
        sR = sum(trades[(name, s)]["null"][0] for s in f["syms"])
        n = sum(trades[(name, s)]["null"][1] for s in f["syms"])
        sums = sum(trades[(name, s)]["null"][2] for s in f["syms"])
        ns = sum(trades[(name, s)]["null"][3] for s in f["syms"])
        nm = sums / np.maximum(ns, 1)
        pct = float((nm < sR / n).mean() * 100)
        ev_b = {"is": rep, "is_stress": gl.report(tb["stress"]), "is_every_signal": gl.report(tb["every"])}
        med = float(np.median([out["finalists"][name]["sleeves"][s]["neighbour_median_pf"] for s in f["syms"]]))
        crit = r2.is_criteria(ev_b, neighbor_median_pf=med)
        each_pos = all(out["finalists"][name]["sleeves"][s]["is"]["expectancy_R"] > 0 for s in f["syms"])
        # correlation of the two sleeves' daily R (same-day trades)
        dR = {s: trades[(name, s)]["fp"].groupby(trades[(name, s)]["fp"].entry_time.dt.date).R.sum() for s in f["syms"]}
        j = pd.concat(dR, axis=1).dropna()
        out["finalists"][name]["basket"] = {
            "is": rep, "is_stress": {k: ev_b["is_stress"][k] for k in ("n", "pf", "expectancy_R", "t_stat")},
            "is_gross": {k: gl.report(tb["gross"])[k] for k in ("n", "pf", "expectancy_R", "t_stat")},
            "is_every_signal": {k: ev_b["is_every_signal"][k] for k in ("n", "pf", "expectancy_R", "t_stat")},
            "is_criteria": crit, "expectancy_positive_on_each_market": each_pos,
            "null": {"rule_mean_R": round(sR / n, 4), "null_mean_R": round(float(nm.mean()), 4), "null_p95_R": round(float(np.percentile(nm, 95)), 4),
                     "null_max_R": round(float(nm.max()), 4), "percentile": round(pct, 1), "pass": bool(pct >= 97.5)},
            "same_day_R_correlation_btc_eth": round(float(j.corr().iloc[0, 1]), 3), "days_both_traded": int(len(j)),
            "is_pass": bool(crit["pass"] and pct >= 97.5 and each_pos),
        }
        print("BASKET", name, {k: rep[k] for k in ("n", "pf", "t_stat", "expectancy_R", "years_pos", "max_dd_R")}, "crit:", crit,
              "null pct:", round(pct, 1), "corr:", out["finalists"][name]["basket"]["same_day_R_correlation_btc_eth"])
    out["trials_so_far"] = n_trials()
    json.dump(out, open(os.path.join(RES, "finalists_is_dossier.json"), "w"), indent=1, default=str)
    print("trials so far:", n_trials())
