"""Idea 042: dear dollars on Bitfinex (scout idea 28). Reads declared.json (never writes it), in sample only.
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/042_bitfinex_margin_rate/run.py
Cache: ~/explore_data/idea_042 (funding/fusd_p2_1d.json = Bitfinex trade:1D:fUSD:p2 daily candles 2016-07-31..2021-12-31,
fetched once; crypto/ and binance/ hold the venue months; without them the kit downloads them again)."""
import json, os, sys
os.environ.setdefault("EXPLORE_CACHE", os.path.expanduser("~/explore_data/idea_042"))
import numpy as np, pandas as pd
from kit import checks, data, judge, sim, stats

FOLDER = os.path.dirname(os.path.abspath(__file__))
CACHE = os.environ["EXPLORE_CACHE"]
MK = "btcusd"
START = pd.Timestamp("2016-11-01", tz="UTC")
DAY = pd.Timedelta(days=1)


def load_funding():
    raw = json.load(open(os.path.join(CACHE, "funding", "fusd_p2_1d.json")))
    d = pd.DataFrame(raw, columns=["t", "open", "close", "high", "low", "volume"])
    obs = pd.to_datetime(d.t, unit="ms")                     # candle start D 00:00 UTC (naive)
    obs_ok = obs < pd.Timestamp("2022-01-01")
    d, obs = d[obs_ok.to_numpy()], obs[obs_ok]
    # close of the candle [D, D+1) is known at its end, D+1 00:00 UTC
    return data.external(obs, d.close.to_numpy(float), known=lambda o: (pd.DatetimeIndex(o) + DAY).tz_localize("UTC"),
                         min_lag=DAY, name="fusd_p2")


def make_build(thr):
    def build(d):
        r = d["fund"]
        ka = pd.DatetimeIndex(r.index)
        m = (r.to_numpy() >= thr) & (ka.dayofweek < 5) & (ka >= START)
        return pd.DataFrame({"known_at": ka[m], "side": np.full(int(m.sum()), -1, dtype=int)})
    return build


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
    info = {}
    for name, loader in (("bitfinex_prices", lambda: data.load_bars(MK, 2016, venue="bitfinex", allow_holes=True)),
                         ("binance_from_2017_08", lambda: data.load_bars(MK, 2017))):
        try:
            b2 = loader()
            bk2 = sim.books({MK: b2})
            s2 = sig_for(c0)
            s2 = s2[s2.known_at >= b2.index[0] + pd.Timedelta(days=30)]
            t2 = sim.simulate(s2, bk2, mode="one", max_wait_h=2, **rule(c0))
            info[name] = stats.summary(t2)
            info[name + "_bitstamp_same_signals"] = stats.summary(mn[mn.known_at >= s2.known_at.min()])
        except Exception as e:  # noqa: BLE001
            info[name + "_error"] = repr(e)
    years = {int(y): stats.summary(g) for y, g in mn.groupby(pd.DatetimeIndex(mn.entry_time).year)}
    neigh_sum = {k: {kk: v.get(kk) for kk in ("n", "PF_gross", "PF", "PF_stress", "t_trade", "mean_R_gross", "mean_R")}
                 for k, v in ((k, stats.summary(t)) for k, t in neigh.items())}
    res = judge.verdict(FOLDER, mn, neigh, every, null, corr="compute", n_configs=len(cfgs), truncation=tr,
                        data_desc="Bitfinex fUSD 2-day funding rate (daily, known at 00:00 UTC); trades on Bitstamp "
                                  "BTC/USD 1h, 2016-11..2021 (5.2 years)",
                        extra={"shift_test": shift, "years": years, "neighbours_summary": neigh_sum,
                               "info_only": info, "counts": mn.attrs["counts"], "every_summary": stats.summary(every)})
    mn.to_csv(os.path.join(CACHE, "main_trades.csv"), index=False)
    print(res["verdict"], res["failed_bars"])
    print(res["ledger_line"])
    print(json.dumps({"main": stats.summary(mn), "years": years, "neigh": neigh_sum, "info": info, "shift": shift,
                      "counts": mn.attrs["counts"]}, default=str, indent=1))


if __name__ == "__main__":
    main()
