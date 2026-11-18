"""Idea 055: slow trend, 50-day close breakouts on a basket of the 14 non-crypto FP markets (slow track).

    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<checkout>/lab/explore python3 -B <this file>            # the declared run
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<checkout>/lab/explore python3 -B <this file> --power    # signal count only

Reads declared.json (never writes it). Daily close = close of the last hourly bar of the 17:00-New-York trading day
(days with >= 5 bars), known at that day's 17:00 New York boundary. Long when the close is the highest of the last N
closes (itself included), short when the lowest. Exit on a condition: the close beyond the opposite X-day extreme
(long: the close is the lowest of the last X), known at the same boundary; max hold H business days; stop k x D20.

The kit's event exit is per market, not per side. Since one position per market is held and a short signal (an
N-day low close) is always also an X-day low close (X <= N), the side open at any time follows from the closes alone:
state L from an N-day-high close until the first X-day-low close, state S from an N-day-low close until the first
X-day-high close. The market's events = the X-day-low closes met in state L and the X-day-high closes met in state S.
For every long trade (entered after an N-day-high close) the first event after its entry is exactly its first X-day-low
close, and symmetrically for shorts (declared.json 'what_changed')."""
import json, os, sys, time
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
from kit import checks, costs as C, data, judge, sim, stats   # noqa: E402

MARKETS = ["xauusd", "xagusd", "us100", "us500", "us30", "ger40", "eurusd", "gbpusd", "usdjpy", "audusd",
           "usdcad", "usdchf", "nzdusd", "eurjpy"]
MIN_BARS = 5
NY = "America/New_York"
_FULL = {}      # market -> (bar open ns, trading-day label ns, label -> boundary ns map arrays)


def _prep(mk, bars):
    t = bars.index.tz_convert("UTC").as_unit("ns").asi8
    td = data.trading_day(bars.index)
    tdn = td.as_unit("ns").asi8 if hasattr(td, "as_unit") else td.asi8
    days = pd.DatetimeIndex(np.unique(tdn))
    bnd = (days + pd.Timedelta(hours=17)).tz_localize(NY).tz_convert("UTC").as_unit("ns").asi8
    return t, tdn, days.as_unit("ns").asi8, bnd


def daily(bars, mk):
    """Daily closes of complete 17:00-NY days with >= MIN_BARS bars: Series indexed by the boundary (UTC) = known_at."""
    n = len(bars)
    if n == 0:                                     # a cut before the market's first bar (us30, ger40 start 2013-09)
        return pd.Series([], dtype=float, index=pd.DatetimeIndex([], tz="UTC"))
    t0 =bars.index.tz_convert("UTC").as_unit("ns").asi8
    f = _FULL.get(mk)
    if f is None or len(f[0]) < n or n == 0 or f[0][n - 1] != t0[-1] or f[0][0] != t0[0]:
        f = _prep(mk, bars)                        # not a prefix of the cached full bars: compute afresh
    tdn = f[1][:n]
    cl = bars["close"].to_numpy(float)
    last = np.r_[np.flatnonzero(np.diff(tdn)), n - 1]
    first = np.r_[0, last[:-1] + 1]
    cnt = last - first + 1
    lab = tdn[last]
    bnd = f[3][np.searchsorted(f[2], lab)]
    ok = cnt >= MIN_BARS
    return pd.Series(cl[last][ok], index=pd.DatetimeIndex(bnd[ok]).tz_localize("UTC"))


def flags(dc, n_entry, n_exit):
    c = dc.to_numpy()
    s = pd.Series(c)
    hiN = (c >= s.rolling(n_entry, min_periods=n_entry).max().to_numpy())
    loN = (c <= s.rolling(n_entry, min_periods=n_entry).min().to_numpy())
    hiX = (c >= s.rolling(n_exit, min_periods=n_exit).max().to_numpy())
    loX = (c <= s.rolling(n_exit, min_periods=n_exit).min().to_numpy())
    return hiN, loN, hiX, loX


def make_build(n_entry):
    def build(d):
        out = []
        for mk in MARKETS:
            dc = daily(d[mk], mk)
            hiN, loN, _, _ = flags(dc, n_entry, 2)
            lg = hiN & ~loN
            sh = loN & ~hiN
            ka = dc.index
            for m_, side in ((lg, 1), (sh, -1)):
                if m_.any():
                    out.append(pd.DataFrame({"known_at": ka[m_], "side": side, "market": mk}))
        s = pd.concat(out, ignore_index=True)
        return s.sort_values(["known_at", "market"], kind="mergesort").reset_index(drop=True)
    return build


def state_events(hiN, loN, hiX, loX):
    st, ev = 0, np.zeros(len(hiN), bool)
    for i in range(len(hiN)):
        if st == 1 and loX[i]:
            ev[i], st = True, 0
        elif st == -1 and hiX[i]:
            ev[i], st = True, 0
        if hiN[i] and not loN[i]:
            st = 1
        elif loN[i] and not hiN[i]:
            st = -1
    return ev


def make_build_events(n_entry, n_exit):
    def build_events(d):
        out = []
        for mk in MARKETS:
            dc = daily(d[mk], mk)
            ev = state_events(*flags(dc, n_entry, n_exit))
            out.append(pd.DataFrame({"known_at": dc.index[ev], "market": mk}))
        e = pd.concat(out, ignore_index=True)
        return e.sort_values(["known_at", "market"], kind="mergesort").reset_index(drop=True)
    return build_events


def load():
    d = {}
    for mk in MARKETS:
        b = data.load_bars(mk)
        d[mk] = b
        _FULL[mk] = _prep(mk, b)
    return d


def power(d, n_entry=50, n_exit=20):
    """Signals and state-machine entries (no stop, no time exit, no price move after a signal) per market."""
    rows, tot_sig, tot_ent = {}, 0, 0
    for mk in MARKETS:
        dc = daily(d[mk], mk)
        hiN, loN, hiX, loX = flags(dc, n_entry, n_exit)
        st, ent = 0, 0
        for i in range(len(dc)):
            if st == 1 and loX[i]:
                st = 0
            elif st == -1 and hiX[i]:
                st = 0
            if hiN[i] and not loN[i]:
                ent += st != 1; st = 1
            elif loN[i] and not hiN[i]:
                ent += st != -1; st = -1
        ns = int((hiN ^ loN).sum())
        rows[mk] = {"days": int(len(dc)), "signals": ns, "regime_entries": int(ent),
                    "first": str(dc.index[0].date()), "last": str(dc.index[-1].date())}
        tot_sig += ns; tot_ent += ent
    return {"by_market": rows, "signals": tot_sig, "regime_entries_lower_bound_of_trades": tot_ent}


def main_run():
    folder = HERE
    decl = json.load(open(os.path.join(folder, "declared.json")))
    checks.declared_hash(folder)
    assert decl.get("track") == "slow"
    cfgs = decl["configurations"]
    t0 = time.time()
    d = load()
    rl = {mk: pd.Timedelta(hours=1) for mk in MARKETS}
    c0 = cfgs[0]
    build = make_build(c0["n_entry"])
    build_ev = make_build_events(c0["n_entry"], c0["n_exit"])
    tr = checks.truncation_test(build, d, row_len=rl)
    print("truncation (signals):", tr["pass"], tr["n_signal_cuts"], tr["n_after_cuts"], tr["n_random_cuts"],
          f"{time.time() - t0:.0f}s", flush=True)
    tre = checks.truncation_test(build_ev, d, row_len=rl)
    print("truncation (events):", tre["pass"], tre["n_signal_cuts"], tre["n_after_cuts"], tre["n_random_cuts"],
          f"{time.time() - t0:.0f}s", flush=True)
    assert tr["pass"] and tre["pass"], (tr["n_failed_cuts"], tre["n_failed_cuts"])
    bk = sim.books({mk: d[mk] for mk in MARKETS})

    def rule_of(c):
        ev = make_build_events(c["n_entry"], c["n_exit"])(d)
        return dict(exit=sim.event_exit(ev, ("bdays", c["max_hold_bdays"])), stop=tuple(c["stop"]))

    def run(c, mode="one"):
        sig = build(d) if c is c0 else make_build(c["n_entry"])(d)
        return sim.simulate(sig, bk, mode=mode, **rule_of(c))

    rule0 = rule_of(c0)
    main = sim.simulate(build(d), bk, **rule0)
    neigh = {c["id"]: run(c) for c in cfgs[1:]}
    every = sim.simulate(build(d), bk, mode="every", **rule0)
    print("simulated", len(main), "trades;", f"{time.time() - t0:.0f}s", flush=True)
    null = stats.null_test(main, bk, n_draws=2000, **rule0)
    print("null pct", null["percentile"], f"{time.time() - t0:.0f}s", flush=True)
    shift = checks.shift_test(build(d), bk, **rule0)

    # descriptive extras (not judged): gross, sides, markets, groups, years, reasons, reversals skipped
    def summ(t):
        if not len(t):
            return {"n": 0}
        return {"n": int(len(t)), "PF": stats.pf(t.R), "PF_gross": stats.pf(t.R_gross), "PF_stress": stats.pf(t.R_stress),
                "mean_R": float(t.R.mean()), "mean_R_gross": float(t.R_gross.mean()),
                "mean_net_bp": float(t.net_bp.mean()), "mean_gross_bp": float(t.gross_bp.mean()),
                "mean_swap_bp": float(t.swap_bp.mean()), "sum_R": float(t.R.sum()), "sum_R_gross": float(t.R_gross.sum()),
                "t_trade": stats.t_stat(t.R.to_numpy()), "t_trade_gross": stats.t_stat(t.R_gross.to_numpy()),
                "hold_tdays_median": float(t.hold_tdays.median())}
    groups = {"metals": ["xauusd", "xagusd"], "indices": ["us100", "us500", "us30", "ger40"],
              "fx": ["eurusd", "gbpusd", "usdjpy", "audusd", "usdcad", "usdchf", "nzdusd", "eurjpy"]}
    cnt = main.attrs["counts"]
    # reversals lost to the kit's one-position rule: a signal entering at the very bar a kept trade of the same market
    # exits on its event (the opposite side's breakout at the same close)
    ex_bar = {(r.market, int(r.exit_i)) for r in main.itertuples() if r.reason == "event"}
    allsig = build(d)
    rev_lost = 0
    for mk, g in allsig.groupby("market"):
        tq = pd.DatetimeIndex(g.known_at).as_unit("ns").asi8
        ei = np.searchsorted(bk[mk].t, tq, side="left")
        taken = set(main.loc[main.market == mk, "entry_i"].astype(int))
        for e_, s_ in zip(ei, g.side):
            if (mk, int(e_)) in ex_bar and int(e_) not in taken:
                rev_lost += 1
    extra = {
        "gross_net_by_side": {"long": summ(main[main.side > 0]), "short": summ(main[main.side < 0]), "all": summ(main)},
        "by_market": {mk: summ(main[main.market == mk]) for mk in MARKETS},
        "by_group": {g: summ(main[main.market.isin(v)]) for g, v in groups.items()},
        "by_year_R_gross": {int(k): float(v) for k, v in main.groupby(main.entry_time.dt.year).R_gross.sum().items()},
        "by_year_R_net": {int(k): float(v) for k, v in main.groupby(main.entry_time.dt.year).R.sum().items()},
        "exit_reasons": main.reason.value_counts().to_dict(),
        "neighbours": {k: summ(v) for k, v in neigh.items()},
        "every_signal": summ(every),
        "counts": cnt, "reversal_signals_lost_to_one_position": int(rev_lost),
        "shift_test": shift, "power": power(d, c0["n_entry"], c0["n_exit"]),
        "null_summary": {k: null[k] for k in null if k != "means"},
    }
    res = judge.verdict(folder, main, neigh, every, null, corr="compute", n_configs=len(cfgs), truncation=tr,
                        event_truncation=tre, max_hold_tdays=40,
                        data_desc="prepared hourly BID bars of 14 FP markets 2013-2021 (us30, ger40 from 2013-09)",
                        extra=extra)
    main.to_parquet(os.path.expanduser("~/explore_data/idea_055/main_trades.parquet"))
    every.to_parquet(os.path.expanduser("~/explore_data/idea_055/every_trades.parquet"))
    json.dump(extra, open(os.path.join(folder, "extra.json"), "w"), indent=1, default=str)
    print(res["verdict"], res["failed_bars"])
    print(res["ledger_line"])
    print(f"done in {time.time() - t0:.0f}s")
    return res


if __name__ == "__main__":
    if "--power" in sys.argv:
        print(json.dumps(power(load()), indent=1))
    else:
        main_run()
