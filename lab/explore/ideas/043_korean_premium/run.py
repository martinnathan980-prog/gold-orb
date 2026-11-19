"""Idea 043: Korean premium (scout idea 29). Reads declared.json (never writes it), in sample only.
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/043_korean_premium/run.py
Cache: ~/explore_data/idea_043 (Upbit daily candles from fetch_upbit.py, Bitstamp and Binance hourly months, FRED)."""
import json, os, sys
os.environ.setdefault("EXPLORE_CACHE", os.path.expanduser("~/explore_data/idea_043"))
FOLDER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, FOLDER)
import numpy as np, pandas as pd
from kit import checks, data, judge, sim, stats
import premium as P

MK = "btcusd"
H = pd.Timedelta(hours=1)


def main():
    decl = json.load(open(os.path.join(FOLDER, "declared.json")))
    checks.declared_hash(FOLDER)
    cfgs = decl["configurations"]
    d = P.load_inputs()
    bars = data.load_bars(MK, 2017)
    print("bars", bars.index[0], bars.index[-1], len(bars), flush=True)
    c0 = cfgs[0]
    b0 = P.make_build(c0["thr"])
    tr = checks.truncation_test(b0, d, row_len={"up": pd.Timedelta(days=1), "bs": H, "won": pd.Timedelta(0)})
    print("truncation", tr["pass"], {k: tr[k] for k in tr if "cut" in k and not isinstance(tr[k], (list, dict))}, flush=True)
    assert tr["pass"], tr
    bk = sim.books({MK: bars})
    sigs = {}

    def sig_for(c):
        if c["thr"] not in sigs:
            sigs[c["thr"]] = P.make_build(c["thr"])(d).assign(market=MK)
        return sigs[c["thr"]]

    def rule(c):
        return dict(exit=tuple(c["exit"]), stop=tuple(c["stop"]), target=tuple(c["target"]) if c.get("target") else None)

    run = lambda c, mode="one": sim.simulate(sig_for(c), bk, mode=mode, max_wait_h=2, **rule(c))  # noqa: E731
    mn = run(c0)
    neigh = {c["id"]: run(c) for c in cfgs[1:]}
    every = run(c0, "every")
    null = stats.null_test(mn, bk, n_draws=2000, **rule(c0))
    shift = checks.shift_test(sig_for(c0), bk, max_wait_h=2, **rule(c0))
    keys = ("n", "PF_gross", "PF", "PF_stress", "t_trade", "mean_R_gross", "mean_R")
    by_year = {str(y): {k: v.get(k) for k in keys} for y, v in
               ((y, stats.summary(g)) for y, g in mn.groupby(pd.DatetimeIndex(mn.entry_time).year))}
    neigh_sum = {k: {kk: v.get(kk) for kk in keys} for k, v in ((k, stats.summary(t)) for k, t in neigh.items())}
    res = judge.verdict(FOLDER, mn, neigh, every, null, corr="compute", n_configs=len(cfgs), truncation=tr,
                        data_desc="Upbit KRW-BTC / (Bitstamp BTC/USD x H.10 won rate); trades on Binance BTCUSDT 1h "
                                  "2017-09..2021 (4.3 years)",
                        extra={"shift_test": shift, "by_year": by_year, "neighbours_summary": neigh_sum,
                               "counts": mn.attrs["counts"], "every_summary": stats.summary(every)})
    mn.to_csv(os.path.expanduser("~/explore_data/idea_043/main_trades.csv"), index=False)
    print(res["verdict"], res["failed_bars"])
    print(res["ledger_line"])
    print(json.dumps({"main": stats.summary(mn), "by_year": by_year, "neigh": neigh_sum, "shift": shift,
                      "counts": mn.attrs["counts"]}, default=str, indent=1))


if __name__ == "__main__":
    main()
