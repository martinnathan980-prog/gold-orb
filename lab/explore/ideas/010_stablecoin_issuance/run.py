"""Idea 010: fast USDT issuance -> long btcusd and ethusd for 5 days (basket of 2). In-sample test of declared.json.
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/010_stablecoin_issuance/run.py
Reads declared.json (never writes it): hash -> truncation -> main, neighbours, every-signal, null -> verdict."""
import json, os, sys, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
from kit import checks, judge, sim, stats, data as D
import bitfinex_bars as BF

FOLDER = HERE
URL = ("https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets=usdt&metrics=SplyCur&frequency=1d"
       "&start_time=2014-10-01&end_time=2021-12-31&page_size=10000")


def usdt_supply():
    p = os.path.join(D.cache_dir(), "cm", "usdt.json")
    if not os.path.isfile(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write(urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "research"}), timeout=60).read())
    j = json.load(open(p))
    assert not j.get("next_page_token")
    d = pd.DataFrame(j["data"])
    obs = pd.to_datetime(d.time).dt.tz_localize(None)
    assert obs.max() <= pd.Timestamp("2021-12-31")
    return D.external(obs, d.SplyCur.astype(float).to_numpy(), known=lambda o: D.known_at(o, lag_days=2, time="00:00", tz="UTC"),
                      min_lag=pd.Timedelta(days=2), name="usdt_supply")


FIRST_BAR = {}   # first allowed signal time per market (first Bitfinex bar + 30 days, for D20), set in main()


def build(d, q=0.7, window_days=365, growth_days=7, markets=("btcusd", "ethusd")):
    """WHOLE signal table: one row per signal day and market. d['usdt'] is indexed by known_at; its observation dates
    are known_at - 2 days (daily rows)."""
    s = d["usdt"]
    obs = pd.DatetimeIndex(s.index).tz_convert("UTC").tz_localize(None) - pd.Timedelta(days=2)
    S = pd.Series(s.to_numpy(), index=obs).asfreq("D")
    g = np.log(S / S.shift(growth_days))
    thr = g.rolling(window_days, min_periods=window_days // 2).quantile(q)
    on = (g > thr) & (g > 0)
    days = on[on].index
    ka = (days + pd.Timedelta(days=2)).tz_localize("UTC")
    rows = []
    for m in markets:
        first = FIRST_BAR[m]
        k = ka[ka >= first]
        rows.append(pd.DataFrame({"known_at": k, "side": 1, "market": m}))
    out = pd.concat(rows).sort_values(["known_at", "market"], kind="stable").reset_index(drop=True)
    return out


def figs(t):
    f = lambda x: {"n": int(len(x)), "PF_gross": stats.pf(x.R_gross), "PF": stats.pf(x.R), "PF_stress": stats.pf(x.R_stress),
                   "mean_R": float(x.R.mean()) if len(x) else None, "sum_R": float(x.R.sum())}
    return {"all": f(t), "by_market": {m: f(g) for m, g in t.groupby("market")},
            "by_year_R_gross": {int(k): float(v) for k, v in stats.by_year(t, "R_gross").items()},
            "t_daily_gross": stats.t_stat(stats.daily_sums(t, "R_gross"))}


def main():
    decl = json.load(open(os.path.join(FOLDER, "declared.json")))
    checks.declared_hash(FOLDER)
    cfgs, mks = decl["configurations"], decl["markets"]
    bars = {m: BF.load(m) for m in mks}
    FIRST_BAR.update({m: bars[m].index.min() + pd.Timedelta(days=30) for m in mks})
    d = {"usdt": usdt_supply()}
    c0 = cfgs[0]
    mk = lambda c: (lambda dd: build(dd, c["q"], c["window_days"], c["growth_days"]))
    b0 = mk(c0)
    tr = checks.truncation_test(b0, d, ["2016-06-01 12:00", "2018-03-06 08:00", "2020-09-09 09:00"],
                                row_len={"usdt": pd.Timedelta(0)})
    assert tr["pass"], tr
    sig = b0(d)
    print("signals", len(sig), sig.groupby("market").size().to_dict())
    bk = sim.books(bars)
    run = lambda s, c, mode="one": sim.simulate(s, bk, exit=tuple(c["exit"]), stop=tuple(c["stop"]), mode=mode)
    main_t = run(sig, c0)
    neigh = {c["id"]: run(mk(c)(d), c) for c in cfgs[1:]}
    every = run(sig, c0, "every")
    null = stats.null_test(main_t, bk, exit=tuple(c0["exit"]), stop=tuple(c0["stop"]), n_draws=2000)
    shift = checks.shift_test(sig, bk, exit=tuple(c0["exit"]), stop=tuple(c0["stop"]))
    extra = {"shift_test": shift, "main_figures": figs(main_t), "counts": main_t.attrs.get("counts"),
             "neighbour_figures": {k: figs(t)["all"] for k, t in neigh.items()}}
    res = judge.verdict(FOLDER, main_t, neigh, every, null, corr="compute", n_configs=len(cfgs), truncation=tr,
                        data_desc="Coin Metrics USDT SplyCur (known D+2), Bitfinex 1h BTC 2015-2021, ETH 2016-2021",
                        extra=extra)
    json.dump(extra, open(os.path.join(FOLDER, "extra_figures.json"), "w"), indent=1, default=str)
    print(res["verdict"], res["failed_bars"])
    print(res["ledger_line"])
    print(json.dumps(extra["main_figures"], indent=1, default=str))
    print(json.dumps({k: {"value": v["value"], "pass": v["pass"]} for k, v in res["bars"].items()}, indent=1, default=str))
    print(json.dumps(extra["neighbour_figures"], indent=1, default=str))


if __name__ == "__main__":
    main()
