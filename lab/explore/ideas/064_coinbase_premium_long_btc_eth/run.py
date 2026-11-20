"""Idea 064: Coinbase premium, buying side only, basket of btcusd and ethusd. Reads declared.json (never writes it),
in sample only.
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/064_coinbase_premium_long_btc_eth/run.py
(EXPLORE_CACHE defaults to ~/explore_data/idea_064: Coinbase, Bitstamp and Bitfinex hourly months; without it the kit
downloads them again)."""
import json, os
os.environ.setdefault("EXPLORE_CACHE", os.path.expanduser("~/explore_data/idea_064"))   # this idea's own cache
import numpy as np, pandas as pd
from kit import checks, data, judge, sim, stats

FOLDER = os.path.dirname(os.path.abspath(__file__))
CACHE = os.environ["EXPLORE_CACHE"]
H = pd.Timedelta(hours=1)
START = pd.Timestamp("2015-08-01", tz="UTC")
MKS = ("btcusd", "ethusd")


def make_build(win_h, thr):
    min_obs = int(win_h * 0.7)

    def one(cb, bs, mk):
        bsv = bs[bs.volume > 0]
        j = pd.concat([cb.close.rename("c"), bsv.close.rename("b")], axis=1, join="inner").dropna()
        p = np.log(j.c / j.b)
        p.index = p.index + H                                   # known at the candle's end
        r = p.rolling(pd.Timedelta(hours=win_h), min_periods=min_obs)
        sd = r.std()
        z = (p - r.mean()) / sd
        ok = (sd > 0) & z.notna() & (z.index >= START)
        z = z[ok]
        z = z[~data.fp_closed(z.index)]
        z = z[z >= thr]                                          # buying side only
        return pd.DataFrame({"known_at": z.index, "side": np.ones(len(z), dtype=int), "market": mk})

    def build(d):
        """Whole signal table of both markets (candles indexed by OPEN; a close is known at open + 1 h)."""
        out = pd.concat([one(d["cb_btc"], d["bs_btc"], "btcusd"), one(d["cb_eth"], d["bs_eth"], "ethusd")],
                        ignore_index=True)
        return out.sort_values(["known_at", "market"], kind="mergesort").reset_index(drop=True)
    return build


def rule(c):
    return dict(exit=tuple(c["exit"]), stop=tuple(c["stop"]), target=tuple(c["target"]) if c.get("target") else None)


def by_q(t):
    e = pd.DatetimeIndex(t.entry_time)
    return {f"{y}Q{q}": int(v) for (y, q), v in pd.Series(1, index=e).groupby([e.year, e.quarter]).size().items()}


def by_y(t):
    e = pd.DatetimeIndex(t.entry_time)
    return {int(y): int(v) for y, v in pd.Series(1, index=e).groupby(e.year).size().items()}


def nsum(n):
    keep = ("percentile", "real_mean_R", "null_mean", "null_p50", "null_p975", "n_draws", "within", "year_strata",
            "year_dense_share", "year_room_share", "year_no_room", "joint_groups")
    return {k: n.get(k) for k in keep if k in n}


def main():
    decl = json.load(open(os.path.join(FOLDER, "declared.json")))
    checks.declared_hash(FOLDER)
    cfgs = decl["configurations"]
    d = {"cb_btc": data.crypto_h1("coinbase", "btcusd"),
         "bs_btc": data.crypto_h1("bitstamp", "btcusd", start="2015-07"),
         "cb_eth": data.crypto_h1("coinbase", "ethusd", start="2017-07"),
         "bs_eth": data.crypto_h1("bitstamp", "ethusd")}
    bars = {"btcusd": data.load_bars("btcusd", 2015, venue="bitfinex", allow_holes=True),
            "ethusd": data.load_bars("ethusd", 2017, venue="bitfinex", allow_holes=True)}
    for k, b in bars.items():
        print("bars", k, b.index[0], b.index[-1], len(b), b.attrs.get("holes"), flush=True)
    c0 = cfgs[0]
    b0 = make_build(c0["win_h"], c0["thr"])
    tr = checks.truncation_test(b0, d, row_len={k: H for k in d})
    print("truncation", tr["pass"], flush=True)
    assert tr["pass"], tr
    bk = sim.books(bars)
    sigs = {}

    def sig_for(c):
        k = (c["win_h"], c["thr"])
        if k not in sigs:
            sigs[k] = make_build(*k)(d)
        return sigs[k]

    run = lambda c, mode="one": sim.simulate(sig_for(c), bk, mode=mode, max_wait_h=2, **rule(c))  # noqa: E731
    mn = run(c0)
    print("main", stats.summary(mn)["n"], flush=True)
    neigh = {c["id"]: run(c) for c in cfgs[1:]}
    every = run(c0, "every")
    null = stats.null_test(mn, bk, n_draws=2000, **rule(c0))
    print("null", null.get("percentile"), flush=True)
    null_year = stats.null_test(mn, bk, n_draws=2000, within="year", **rule(c0))
    print("null_year", null_year.get("percentile"), flush=True)
    shift = checks.shift_test(sig_for(c0), bk, max_wait_h=2, **rule(c0))
    # information only (declared): each leg alone, with its own judged null and same-year null
    legs = {}
    for mk in MKS:
        t = mn[mn.market == mk]
        tb = {mk: bk[mk]}
        ln = stats.null_test(t, tb, n_draws=2000, **rule(c0))
        ly = stats.null_test(t, tb, n_draws=2000, within="year", **rule(c0))
        ev = every[every.market == mk]
        legs[mk] = {"summary": stats.summary(t), "null": nsum(ln), "null_same_year": nsum(ly),
                    "every_signal": {"n": int(len(ev)), "mean_R": float(ev.R.mean()) if len(ev) else None},
                    "trades_by_year": by_y(t), "trades_by_quarter": by_q(t),
                    "neighbours": {k: stats.summary(v[v.market == mk]).get("mean_R") for k, v in neigh.items()}}
        print("leg", mk, legs[mk]["summary"]["n"], legs[mk]["summary"]["mean_R"], ln.get("percentile"),
              ly.get("percentile"), flush=True)
    eth = legs["ethusd"]
    cond1 = bool(eth["summary"]["mean_R"] > 0 and (eth["null_same_year"].get("percentile") or 0) >= 90)
    neigh_sum = {k: {kk: v.get(kk) for kk in ("n", "PF_gross", "PF", "PF_stress", "t_daily", "t_trade", "mean_R",
                                               "mean_R_gross", "mean_net_bp", "mean_gross_bp")}
                 for k, v in ((k, stats.summary(t)) for k, t in neigh.items())}
    res = judge.verdict(FOLDER, mn, neigh, every, null, corr="compute", n_configs=len(cfgs), truncation=tr,
                        data_desc="Coinbase / Bitstamp premium per coin, long only; trades on Bitfinex 1h, btcusd "
                                  "2015-08..2021 (6.4 y), ethusd 2017-08..2021 (4.4 y)",
                        extra={"shift_test": shift, "legs": legs, "lead_condition_1_ether": cond1,
                               "neighbours_summary": neigh_sum, "counts": mn.attrs["counts"],
                               "basket_trades_by_year": by_y(mn), "basket_trades_by_quarter": by_q(mn),
                               "basket_null_same_year": nsum(null_year)},
                        null_year=null_year)
    mn.to_csv(os.path.join(CACHE, "main_trades.csv"), index=False)
    print(res["verdict"], res["failed_bars"])
    print(res["ledger_line"])
    print(json.dumps({"main": stats.summary(mn), "legs": legs, "cond1": cond1, "neigh": neigh_sum, "shift": shift,
                      "null": nsum(null), "null_year": nsum(null_year)}, default=str, indent=1))


if __name__ == "__main__":
    main()
