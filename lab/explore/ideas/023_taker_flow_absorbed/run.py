"""Idea 023: aggressive order flow absorbed (scout idea 9). Reads declared.json (never writes it), in sample only.
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/023_taker_flow_absorbed/run.py
(cache: ~/explore_data/idea_023 holds the Binance monthly klines; without it the kit downloads them again)."""
import json, os
os.environ.setdefault("EXPLORE_CACHE", os.path.expanduser("~/explore_data/idea_023"))   # this idea's own cache
import numpy as np, pandas as pd
from kit import checks, data, judge, sim, stats

FOLDER = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.expanduser("~/explore_data/idea_023")
H = pd.Timedelta(hours=1)
SYMS = {"btcusd": "BTCUSDT", "ethusd": "ETHUSDT"}
END = pd.Timestamp("2022-01-01", tz="UTC")


def blocks(k):
    """4-hour UTC blocks (00, 04 ... 20) of hourly klines indexed by kline OPEN; a block needs its 4 hours and
    volume > 0. Returned index = block END (when its taker share, open and close are all known)."""
    g = k.groupby(k.index.floor("4h"))
    b = pd.DataFrame({"open": g.open.first(), "close": g.close.last(), "vol": g.volume.sum(),
                      "tb": g.taker_buy_base.sum(), "n": g.open.size()})
    b = b[(b.n == 4) & (b.vol > 0)]
    b.index = b.index + pd.Timedelta(hours=4)
    return b


def make_build(win, thr):
    def build(d):
        out = []
        for mk in SYMS:
            b = blocks(d[mk])
            s = b.tb / b.vol
            r = s.rolling(win, min_periods=int(win * 0.7))
            z = (s - r.mean()) / r.std()
            ret = b.close / b.open - 1
            start_wd = (b.index - pd.Timedelta(hours=4)).dayofweek < 5
            ok = z.notna() & start_wd & ~data.fp_closed(b.index) & (b.index < END)
            short = ok & (z >= thr) & (ret <= 0)
            long_ = ok & (z <= -thr) & (ret >= 0)
            m = short | long_
            out.append(pd.DataFrame({"known_at": b.index[m], "side": np.where(short[m], -1, 1).astype(int),
                                     "market": mk}))
        return pd.concat(out, ignore_index=True).sort_values(["known_at", "market"], ignore_index=True)
    return build


def rule(c):
    return dict(exit=tuple(c["exit"]), stop=tuple(c["stop"]), target=tuple(c["target"]) if c.get("target") else None)


def summ(t):
    s = stats.summary(t)
    return {k: s.get(k) for k in ("n", "PF_gross", "PF", "PF_stress", "t_trade", "t_daily", "mean_R_gross", "mean_R",
                                  "sum_R") if k in s}


def main():
    decl = json.load(open(os.path.join(FOLDER, "declared.json")))
    checks.declared_hash(FOLDER)
    cfgs = decl["configurations"]
    d = {mk: data.binance_klines(sym, "1h") for mk, sym in SYMS.items()}
    bars = {mk: data.load_bars(mk, 2017) for mk in SYMS}
    for mk, b in bars.items():
        print(mk, "bars", b.index[0], b.index[-1], len(b), b.attrs.get("source"), flush=True)
    c0 = cfgs[0]
    b0 = make_build(c0["win_blocks"], c0["thr"])
    tr = checks.truncation_test(b0, d, row_len={mk: H for mk in SYMS}, cols=("known_at", "side"))
    print("truncation", tr["pass"], flush=True)
    assert tr["pass"], tr
    bk = sim.books(bars)
    sigs = {}

    def sig_for(c):
        k = (c["win_blocks"], c["thr"])
        if k not in sigs:
            sigs[k] = make_build(*k)(d)
        return sigs[k]

    run = lambda c, mode="one": sim.simulate(sig_for(c), bk, mode=mode, max_wait_h=2, **rule(c))  # noqa: E731
    mn = run(c0)
    neigh = {c["id"]: run(c) for c in cfgs[1:]}
    every = run(c0, "every")
    null = stats.null_test(mn, bk, n_draws=2000, **rule(c0))
    shift = checks.shift_test(sig_for(c0), bk, max_wait_h=2, **rule(c0))
    sides = {s: summ(mn[mn.side == v]) for s, v in (("long", 1), ("short", -1))}
    per_market = {m: summ(mn[mn.market == m]) for m in SYMS}
    per_market_side = {f"{m}_{s}": summ(mn[(mn.market == m) & (mn.side == v)]) for m in SYMS
                       for s, v in (("long", 1), ("short", -1))}
    yrs = mn.assign(y=pd.DatetimeIndex(mn.entry_time).year).groupby("y").agg(
        n=("R", "size"), sum_R=("R", "sum"), sum_R_gross=("R_gross", "sum")).round(3).to_dict("index")
    neigh_sum = {k: summ(t) for k, t in neigh.items()}
    res = judge.verdict(FOLDER, mn, neigh, every, null, corr="compute", n_configs=len(cfgs), truncation=tr,
                        data_desc="Binance BTCUSDT / ETHUSDT 1h klines (taker-buy volume) 2017-08..2021 (4.4 years)",
                        extra={"shift_test": shift, "sides": sides, "per_market": per_market,
                               "per_market_side": per_market_side, "years": yrs, "neighbours_summary": neigh_sum,
                               "every_signal": summ(every), "counts": mn.attrs["counts"]})
    os.makedirs(CACHE, exist_ok=True)
    mn.to_csv(os.path.join(CACHE, "main_trades.csv"), index=False)
    print(res["verdict"], res["failed_bars"])
    print(res["ledger_line"])
    print(json.dumps({"main": summ(mn), "sides": sides, "per_market": per_market, "per_market_side": per_market_side,
                      "years": yrs, "neigh": neigh_sum, "every": summ(every), "shift": shift,
                      "null_pct": null.get("percentile") if isinstance(null, dict) else None},
                     default=str, indent=1))


if __name__ == "__main__":
    main()
