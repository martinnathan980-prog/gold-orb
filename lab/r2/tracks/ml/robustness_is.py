"""Extra in-sample robustness diagnostics for the finalists (no validation data, no new configuration):
cost multiples, random-side null, weekly block bootstrap, results by year / weekday / decision hour."""
import json
import sys

sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/ml")
from research import *  # noqa
from goldlab.sim import simulate, apply_spread_mult

GEN = {"stop_k": 2.0, "hold_h": 13.0}
P = {"F1": {**GEN, "model": "B1_ridge_full.json", "oof": True, "q": "0.5"}, "F2": dict(GEN)}
pf = lambda x: round(float(x[x > 0].sum() / -x[x < 0].sum()), 3)
out = {}
for sym in ["btcusd", "ethusd"]:
    m1 = is_frame(sym)
    for nm, p in P.items():
        o = {}
        base = r2.run(sym, S.make_orders, p, "fp", True, m1)
        # (c) cost multiples: spread AND slippage multiplied by k (orders rebuilt on the widened quotes)
        for k in (2.0, 3.0, 5.0):
            mk = apply_spread_mult(m1, k)
            t = simulate(mk, S.make_orders(mk, **p), sym=sym, costs=r2.costs(sym, k), no_overlap=True)
            o[f"costs_x{k:g}"] = {"n": int(len(t)), "pf": pf(t.R.to_numpy()), "exp_R": round(float(t.R.mean()), 4)}
            del mk
        # (a) random side at the rule's own entry times
        orders = S.make_orders(m1, **p)
        rng = np.random.default_rng(3)
        means = []
        for _ in range(200):
            oo = orders.copy()
            oo["side"] = np.where(rng.random(len(oo)) < 0.5, 1, -1)
            means.append(float(simulate(m1, oo, sym=sym, costs=r2.costs(sym), no_overlap=True).R.mean()))
        means = np.array(means)
        o["random_side_null"] = {"rule_mean_R": round(float(base.R.mean()), 4), "null_mean_R": round(float(means.mean()), 4),
                                 "null_p95_R": round(float(np.percentile(means, 95)), 4), "null_max_R": round(float(means.max()), 4),
                                 "percentile": round(float((means < base.R.mean()).mean() * 100), 1)}
        # (b) weekly block bootstrap of the in-sample R
        wk = base.groupby(base.exit_time.dt.tz_convert(None).dt.to_period("W")).R.agg(["sum", "size"])
        rng = np.random.default_rng(4)
        idx = rng.integers(0, len(wk), size=(5000, len(wk)))
        bs = wk["sum"].to_numpy()[idx].sum(axis=1) / wk["size"].to_numpy()[idx].sum(axis=1)
        o["weekly_block_bootstrap_mean_R"] = {"p2.5": round(float(np.percentile(bs, 2.5)), 4), "p50": round(float(np.percentile(bs, 50)), 4),
                                              "p97.5": round(float(np.percentile(bs, 97.5)), 4), "prob_mean_le_0": round(float((bs <= 0).mean()), 4)}
        # (d) by year, (e) by weekday and decision hour (New York)
        ny = base.entry_time.dt.tz_convert("America/New_York")
        g = base.groupby(base.entry_time.dt.year).R
        o["by_year"] = {int(y): {"n": int(n), "exp_R": round(float(m), 3), "pf": pf(x.to_numpy())} for (y, x), n, m in zip(g, g.size(), g.mean())}
        o["by_weekday_exp_R"] = {int(k): [int(n), round(float(v), 3)] for (k, v), n in zip(base.groupby(ny.dt.dayofweek).R.mean().items(), base.groupby(ny.dt.dayofweek).R.size())}
        o["by_entry_hour_ny_exp_R"] = {int(k): [int(n), round(float(v), 3)] for (k, v), n in zip(base.groupby(ny.dt.hour).R.mean().items(), base.groupby(ny.dt.hour).R.size())}
        o["full_data_years_2019_2021"] = {"n": int((base.entry_time.dt.year >= 2019).sum()), "pf": pf(base[base.entry_time.dt.year >= 2019].R.to_numpy()),
                                          "exp_R": round(float(base[base.entry_time.dt.year >= 2019].R.mean()), 4)}
        o["trades_per_trading_day"] = round(len(base) / base.entry_time.dt.date.nunique(), 2)
        o["share_of_weekdays_with_a_trade"] = round(base.entry_time.dt.date.nunique() / max(np.busday_count(base.entry_time.min().date(), base.entry_time.max().date()), 1), 2)
        out[f"{nm}:{sym}"] = o
        print(nm, sym, json.dumps(o))
    r2.free()
json.dump(out, open(os.path.join(RES, "robustness_is.json"), "w"), indent=1)
