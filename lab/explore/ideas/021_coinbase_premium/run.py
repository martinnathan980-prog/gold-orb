"""Idea 021: Coinbase premium (scout idea 7). Reads declared.json (never writes it), in sample only.
    EXPLORE_CACHE=~/explore_data/idea_021 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/021_coinbase_premium/run.py
(the cache folder holds the Coinbase, Bitstamp and Bitfinex hourly months; without it the kit downloads them again)."""
import json, os, sys
os.environ.setdefault("EXPLORE_CACHE", os.path.expanduser("~/explore_data/idea_021"))   # this idea's own cache
import numpy as np, pandas as pd
from kit import checks, data, judge, sim, stats

FOLDER = os.path.dirname(os.path.abspath(__file__))
H = pd.Timedelta(hours=1)
START = pd.Timestamp("2015-08-01", tz="UTC")
MK = "btcusd"


def make_build(win_h, thr):
    min_obs = int(win_h * 0.7)

    def build(d):
        """Whole signal table from the two venues' candles (indexed by candle OPEN; a close is known at open + 1 h)."""
        cb, bs = d["cb"], d["bs"]
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
        z = z[(z >= thr) | (z <= -thr)]
        return pd.DataFrame({"known_at": z.index, "side": np.where(z.to_numpy() > 0, 1, -1).astype(int)})
    return build


def main():
    decl = json.load(open(os.path.join(FOLDER, "declared.json")))
    checks.declared_hash(FOLDER)
    cfgs = decl["configurations"]
    cb = data.crypto_h1("coinbase", "btcusd")
    bs = data.crypto_h1("bitstamp", "btcusd", start="2015-07")
    d = {"cb": cb, "bs": bs}
    bars = data.load_bars(MK, 2015, venue="bitfinex", allow_holes=True)
    print("bars", bars.index[0], bars.index[-1], len(bars), bars.attrs.get("holes"), flush=True)
    c0 = cfgs[0]
    b0 = make_build(c0["win_h"], c0["thr"])
    tr = checks.truncation_test(b0, d, row_len={"cb": H, "bs": H})
    print("truncation", tr["pass"], {k: tr[k] for k in tr if "cut" in k and not isinstance(tr[k], (list, dict))}, flush=True)
    assert tr["pass"], tr
    bk = sim.books({MK: bars})
    sigs = {}

    def sig_for(c):
        k = (c["win_h"], c["thr"])
        if k not in sigs:
            sigs[k] = make_build(*k)(d).assign(market=MK)
        return sigs[k]

    def rule(c):
        return dict(exit=tuple(c["exit"]), stop=tuple(c["stop"]), target=tuple(c["target"]) if c.get("target") else None)

    run = lambda c, mode="one": sim.simulate(sig_for(c), bk, mode=mode, max_wait_h=2, **rule(c))  # noqa: E731
    mn = run(c0)
    neigh = {c["id"]: run(c) for c in cfgs[1:]}
    every = run(c0, "every")
    null = stats.null_test(mn, bk, n_draws=2000, **rule(c0))
    shift = checks.shift_test(sig_for(c0), bk, max_wait_h=2, **rule(c0))
    # information only (declared): the same main signals priced on Binance from 2017-08
    info = {}
    try:
        bn = data.load_bars(MK, 2017)
        bkn = sim.books({MK: bn})
        s2 = sig_for(c0)
        s2 = s2[s2.known_at >= bn.index[0]]
        tb = sim.simulate(s2, bkn, mode="one", max_wait_h=2, **rule(c0))
        info["binance_from_2017_08"] = stats.summary(tb)
        tf = mn[mn.known_at >= bn.index[0]]
        info["bitfinex_same_period"] = stats.summary(tf)
    except Exception as e:  # noqa: BLE001
        info["binance_error"] = repr(e)
    sides = {s: stats.summary(mn[mn.side == v]) for s, v in (("long", 1), ("short", -1))}
    neigh_sum = {k: {kk: v.get(kk) for kk in ("n", "PF_gross", "PF", "PF_stress", "t_trade", "mean_R_gross")}
                 for k, v in ((k, stats.summary(t)) for k, t in neigh.items())}
    res = judge.verdict(FOLDER, mn, neigh, every, null, corr="compute", n_configs=len(cfgs), truncation=tr,
                        data_desc="Coinbase / Bitstamp premium; trades on Bitfinex BTC/USD 1h 2015-08..2021 (6.4 years)",
                        extra={"shift_test": shift, "sides": sides, "neighbours_summary": neigh_sum, "info_only": info,
                               "counts": mn.attrs["counts"]})
    mn.to_csv(os.path.join(os.path.expanduser("~/explore_data/idea_021"), "main_trades.csv"), index=False)
    print(res["verdict"], res["failed_bars"])
    print(res["ledger_line"])
    print(json.dumps({"main": stats.summary(mn), "sides": sides, "neigh": neigh_sum, "info": info, "shift": shift},
                     default=str, indent=1))


if __name__ == "__main__":
    main()
