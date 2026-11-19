"""Idea 063: dear dollars on Bitfinex, LONG side = exact mirror of idea 042, declared post hoc.
Reads declared.json (never writes it), in sample only.
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/063_bitfinex_dear_dollars_long/run.py
Cache: ~/explore_data/idea_063 (funding/fusd_p2_1d.json = Bitfinex trade:1D:fUSD:p2 daily candles 2016-07-31..2021-12-31,
copied from idea 042's cache; crypto/ and binance/ hold the venue months, also copied)."""
import json, os
os.environ.setdefault("EXPLORE_CACHE", os.path.expanduser("~/explore_data/idea_063"))
import numpy as np, pandas as pd
from kit import checks, data, judge, sim, stats

FOLDER = os.path.dirname(os.path.abspath(__file__))
CACHE = os.environ["EXPLORE_CACHE"]
MK = "btcusd"
SIDE = +1
START = pd.Timestamp("2016-11-01", tz="UTC")
END = pd.Timestamp("2022-01-01", tz="UTC")
DAY = pd.Timedelta(days=1)


def load_funding():
    raw = json.load(open(os.path.join(CACHE, "funding", "fusd_p2_1d.json")))
    d = pd.DataFrame(raw, columns=["t", "open", "close", "high", "low", "volume"])
    obs = pd.to_datetime(d.t, unit="ms")                     # candle start D 00:00 UTC (naive)
    obs_ok = obs < pd.Timestamp("2022-01-01")                # cut in the read
    d, obs = d[obs_ok.to_numpy()], obs[obs_ok]
    # close of the candle [D, D+1) is known at its end, D+1 00:00 UTC
    return data.external(obs, d.close.to_numpy(float), known=lambda o: (pd.DatetimeIndex(o) + DAY).tz_localize("UTC"),
                         min_lag=DAY, name="fusd_p2")


def make_build(thr):
    def build(d):
        r = d["fund"]
        ka = pd.DatetimeIndex(r.index)
        m = (r.to_numpy() >= thr) & (ka.dayofweek < 5) & (ka >= START)
        return pd.DataFrame({"known_at": ka[m], "side": np.full(int(m.sum()), SIDE, dtype=int)})
    return build


def tstat_diff(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    return float(a.mean() - b.mean()), float((a.mean() - b.mean()) / se)


def brief(t):
    s = stats.summary(t)
    return {k: s.get(k) for k in ("n", "PF_gross", "PF", "PF_stress", "mean_R_gross", "mean_R", "mean_gross_bp",
                                  "mean_net_bp", "t_trade", "years_positive_frac", "by_year_R")}


def main():
    decl = json.load(open(os.path.join(FOLDER, "declared.json")))
    checks.declared_hash(FOLDER)
    cfgs = decl["configurations"]
    fund = load_funding()
    d = {"fund": fund}
    print("funding", fund.index[0], fund.index[-1], len(fund), flush=True)
    bars = data.load_bars(MK, 2016, venue="bitstamp")
    print("bars", bars.index[0], bars.index[-1], len(bars), flush=True)
    c0 = cfgs[0]
    tr = checks.truncation_test(make_build(c0["thr"]), d, row_len={"fund": pd.Timedelta(0)})
    print("truncation", tr["pass"], flush=True)
    assert tr["pass"], tr
    bk = sim.books({MK: bars})
    sigs = {}

    def sig_for(c):
        if c["thr"] not in sigs:
            sigs[c["thr"]] = make_build(c["thr"])(d).assign(market=MK)
        return sigs[c["thr"]]

    def rule(c):
        return dict(exit=tuple(c["exit"]), stop=tuple(c["stop"]), target=tuple(c["target"]) if c.get("target") else None)

    run = lambda c, mode="one", b=bk: sim.simulate(sig_for(c), b, mode=mode, max_wait_h=2, **rule(c))  # noqa: E731
    mn = run(c0)
    neigh = {c["id"]: run(c) for c in cfgs[1:]}
    every = run(c0, "every")
    null = stats.null_test(mn, bk, n_draws=2000, **rule(c0))
    shift = checks.shift_test(sig_for(c0), bk, max_wait_h=2, **rule(c0))
    print("main", brief(mn), "null", null["percentile"], flush=True)

    # ---- information only (as in 042): other venues
    info = {}
    for name, loader in (("bitfinex_prices", lambda: data.load_bars(MK, 2016, venue="bitfinex", allow_holes=True)),
                         ("binance_from_2017_08", lambda: data.load_bars(MK, 2017))):
        try:
            b2 = loader()
            bk2 = sim.books({MK: b2})
            s2 = sig_for(c0)
            s2 = s2[s2.known_at >= b2.index[0] + pd.Timedelta(days=30)]
            t2 = sim.simulate(s2, bk2, mode="one", max_wait_h=2, **rule(c0))
            info[name] = brief(t2)
            info[name + "_bitstamp_same_signals"] = brief(mn[mn.known_at >= s2.known_at.min()])
        except Exception as e:  # noqa: BLE001
            info[name + "_error"] = repr(e)

    # ---- (a) by year and without 2017
    yr = pd.DatetimeIndex(mn.entry_time).year
    years = {int(y): brief(g) for y, g in mn.groupby(yr)}
    without_2017 = brief(mn[yr != 2017])
    only_2017 = brief(mn[yr == 2017])

    # ---- (b) control: the same long trade on every other weekday 00:00 UTC of 2016-11..2021
    days = pd.date_range(START, END - DAY, freq="D")
    days = days[days.dayofweek < 5]
    sig_set = set(pd.DatetimeIndex(sig_for(c0).known_at).as_unit("ns").asi8.tolist())
    oth = days[~np.isin(days.as_unit("ns").asi8, list(sig_set))]
    ctrl_sig = pd.DataFrame({"known_at": oth, "side": SIDE, "market": MK})
    ctrl = sim.simulate(ctrl_sig, bk, mode="every", max_wait_h=2, **rule(c0))
    dm_net, t_net = tstat_diff(mn.R, ctrl.R)
    dm_g, t_g = tstat_diff(mn.R_gross, ctrl.R_gross)
    cy = pd.DatetimeIndex(ctrl.entry_time).year
    control = {"other_weekdays": brief(ctrl), "n_other_days": int(len(oth)),
               "signal_minus_other_meanR_net": dm_net, "t_net_welch": t_net,
               "signal_minus_other_meanR_gross": dm_g, "t_gross_welch": t_g,
               "other_by_year_meanR_net": {int(y): float(g.R.mean()) for y, g in ctrl.groupby(cy)},
               "signal_by_year_meanR_net": {int(y): float(g.R.mean()) for y, g in mn.groupby(yr)},
               "counts": ctrl.attrs["counts"]}
    # same comparison without 2017
    dm7, t7 = tstat_diff(mn.R[yr != 2017], ctrl.R[cy != 2017])
    control["without_2017_signal_minus_other_meanR_net"] = dm7
    control["without_2017_t_net_welch"] = t7

    # ---- (c) stricter null: random long entries at 00:00 UTC on weekdays of the SAME calendar year
    b = bk[MK]
    bt = pd.DatetimeIndex(b.t.astype("datetime64[ns]")).tz_localize("UTC")
    cand_all = np.flatnonzero((bt.hour == 0) & (bt.minute == 0) & (bt.dayofweek < 5) & (bt >= START) & (bt < END))
    o = sim.outcomes(b, cand_all, np.full(len(cand_all), SIDE), rule(c0)["exit"], rule(c0)["stop"], None,
                     scenarios=("net",))
    ok = o["ok"]
    pool_y = pd.DatetimeIndex(bt[cand_all]).year.to_numpy()
    pools = {y: o["net"]["R"][ok & (pool_y == y)] for y in np.unique(pool_y)}
    rng = np.random.default_rng(63)
    tot = np.zeros(2000)
    for y, g in mn.groupby(yr):
        p = pools[y]
        tot += p[rng.integers(0, len(p), (2000, len(g)))].sum(1)
    means = tot / len(mn)
    real = float(mn.R.mean())
    null_same_year = {"real_mean_R": real, "percentile": float((means < real).mean() * 100), "n_draws": 2000,
                      "null_mean": float(means.mean()), "null_sd": float(means.std(ddof=1)), "seed": 63,
                      "pool_sizes": {int(y): int(len(p)) for y, p in pools.items()},
                      "pool_meanR_by_year": {int(y): float(p.mean()) for y, p in pools.items()},
                      "how": "each main trade re-entered long at the open of the 00:00 UTC bar of a random weekday of "
                             "its own entry year (uniform with replacement among complete trades), exit 23 h, stop "
                             "2 x D20, net costs; statistic = pooled mean net R; percentile = share of draws strictly below"}

    # ---- (d) the long side's costs as charged
    spread_slip_bp = mn.gross_bp - mn.net_bp - mn.swap_bp
    swap_R = mn.swap_bp / 1e4 * mn.entry_px / mn.stop_dist
    tot_R = mn.R_gross - mn.R
    cost = {"per_trade_mean_bp": {"spread_and_slippage": float(spread_slip_bp.mean()), "commission": 0.0,
                                  "swap": float(mn.swap_bp.mean()), "total": float((mn.gross_bp - mn.net_bp).mean())},
            "per_trade_mean_R": {"spread_and_slippage": float((tot_R - swap_R).mean()), "commission": 0.0,
                                 "swap": float(swap_R.mean()), "total": float(tot_R.mean())},
            "swap_bp_by_entry_weekday": {int(k): float(v) for k, v in
                                         mn.swap_bp.groupby(pd.DatetimeIndex(mn.entry_time).dayofweek).mean().items()},
            "note": "FP Raw btcusd: spread 22.5 USD at 76000 (Raw commission folded into the spread in "
                    "lab/r2/fp_costs.json, so commission shows as 0), slippage 0.5 bp a side at market, 1.5 bp on a "
                    "stop; long swap 0.2 a year / 360 per 17:00 New York rollover, triple on Friday"}
    side_split = {"long_n": int((mn.side > 0).sum()), "short_n": int((mn.side < 0).sum())}

    neigh_sum = {k: brief(t) for k, t in neigh.items()}
    res = judge.verdict(FOLDER, mn, neigh, every, null, corr="compute", n_configs=len(cfgs), truncation=tr,
                        data_desc="Bitfinex fUSD 2-day funding rate (daily, known at 00:00 UTC); trades on Bitstamp "
                                  "BTC/USD 1h, 2016-11..2021 (5.2 years); POST HOC mirror of 042 (long side)",
                        extra={"post_hoc": decl["post_hoc"], "shift_test": shift, "years": years,
                               "a_without_2017": without_2017, "a_only_2017": only_2017,
                               "b_control_other_weekdays": control, "c_null_same_year": null_same_year,
                               "d_costs_long": cost, "side_split": side_split,
                               "neighbours_summary": neigh_sum, "info_only": info, "counts": mn.attrs["counts"],
                               "every_summary": brief(every)})
    mn.to_csv(os.path.join(CACHE, "main_trades.csv"), index=False)
    print(res["verdict"], res["failed_bars"])
    print(res["ledger_line"])
    print(json.dumps({"main": brief(mn), "years": years, "without_2017": without_2017, "control": control,
                      "null_same_year": {k: v for k, v in null_same_year.items()}, "costs": cost, "neigh": neigh_sum,
                      "info": info, "shift": shift, "counts": mn.attrs["counts"]}, default=str, indent=1))


if __name__ == "__main__":
    main()
