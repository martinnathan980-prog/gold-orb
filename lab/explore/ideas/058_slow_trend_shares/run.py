"""Idea 058: slow trend on the 40 US shares, 50-session close breakouts (slow track).

    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<checkout>/lab/explore python3 -B <this file>            # the declared run
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<checkout>/lab/explore python3 -B <this file> --power    # signal count only

Reads declared.json (never writes it). Session close = close of a share's bar labelled 15:00 New York (09:30-16:00
sessions; the bar ends at 16:00); a New York date whose last bar is not labelled 15:00 (half days, sessions cut short
by a data hole) gives no session close. A signal or exit condition taken from the close of session D is stamped
known_at = 10:00 New York of the share's NEXT session in the data (the next New York date with a bar of that share),
so that the kit enters / exits at the open of the bar labelled 10:00 (never at the 09:30 opening print). This stamp is
later than the time the close is known (16:00 of D): conservative. A close with no next session in the data is dropped.

Long when the close is the highest of the last N session closes (itself included), short when the lowest. Exit on a
condition: the close beyond the opposite X-session extreme, stamped the same way; max hold H business days; stop
k x D20. As in idea 055 the kit's event exit is per market: the events of a share are those of the breakout state
machine (state L from an N-high close until the first X-low close, S from an N-low close until the first X-high close;
events = X-low closes met in L and X-high closes met in S)."""
import json, os, sys, time
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
from kit import checks, costs as C, data, judge, sim, stats   # noqa: E402

NY = "America/New_York"
CACHE = os.path.expanduser("~/explore_data/idea_058")
MARKETS = sorted(k for k in json.load(open(os.path.join(HERE, "..", "..", "kit", "extra_costs.json")))
                 if not k.startswith("_") and k != "oil")
_FULL = {}      # market -> (bar open ns, NY date (days), NY hour label, unique dates, 10:00-NY stamp ns per unique date)


def _prep(bars):
    t = bars.index.tz_convert("UTC").as_unit("ns").asi8
    loc = bars.index.tz_convert(NY)
    day = (loc.tz_localize(None).normalize().as_unit("ns").asi8 // 86_400_000_000_000).astype(np.int64)
    hr = np.asarray(loc.hour, np.int64)
    ud = np.unique(day)
    st = (pd.DatetimeIndex((ud * 86_400_000_000_000).astype("datetime64[ns]")) + pd.Timedelta(hours=10)) \
        .tz_localize(NY).tz_convert("UTC").as_unit("ns").asi8
    return t, day, hr, ud, st


def sessions(bars, mk):
    """Session closes of share mk: (closes array, known_at stamps = next session's 10:00 NY, UTC DatetimeIndex)."""
    n = len(bars)
    if n == 0:
        return np.zeros(0), pd.DatetimeIndex([], tz="UTC")
    t0 = bars.index.tz_convert("UTC").as_unit("ns").asi8
    f = _FULL.get(mk)
    if f is None or len(f[0]) < n or f[0][n - 1] != t0[-1] or f[0][0] != t0[0]:
        f = _prep(bars)                            # not a prefix of the cached full bars: compute afresh
    day, hr = f[1][:n], f[2][:n]
    cl = bars["close"].to_numpy(float)
    last = np.r_[np.flatnonzero(np.diff(day)), n - 1]
    gday = day[last]
    nxt = np.r_[gday[1:], -1]                      # next session date in the data (-1: none)
    ok = (hr[last] == 15) & (nxt >= 0)
    stamp = f[4][np.searchsorted(f[3], nxt[ok])]
    return cl[last][ok], pd.DatetimeIndex(stamp).tz_localize("UTC")


def flags(c, n_entry, n_exit):
    s = pd.Series(c)
    hiN = c >= s.rolling(n_entry, min_periods=n_entry).max().to_numpy()
    loN = c <= s.rolling(n_entry, min_periods=n_entry).min().to_numpy()
    hiX = c >= s.rolling(n_exit, min_periods=n_exit).max().to_numpy()
    loX = c <= s.rolling(n_exit, min_periods=n_exit).min().to_numpy()
    return hiN, loN, hiX, loX


def make_build(n_entry):
    def build(d):
        out = []
        for mk in MARKETS:
            c, ka = sessions(d[mk], mk)
            if len(c) == 0:
                continue
            hiN, loN, _, _ = flags(c, n_entry, 2)
            for m_, side in ((hiN & ~loN, 1), (loN & ~hiN, -1)):
                if m_.any():
                    out.append(pd.DataFrame({"known_at": ka[m_], "side": side, "market": mk}))
        s = pd.concat(out, ignore_index=True) if out else \
            pd.DataFrame({"known_at": pd.DatetimeIndex([], tz="UTC"), "side": [], "market": []})
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
            c, ka = sessions(d[mk], mk)
            if len(c) == 0:
                continue
            ev = state_events(*flags(c, n_entry, n_exit))
            out.append(pd.DataFrame({"known_at": ka[ev], "market": mk}))
        e = pd.concat(out, ignore_index=True)
        return e.sort_values(["known_at", "market"], kind="mergesort").reset_index(drop=True)
    return build_events


def load():
    d = {}
    for mk in MARKETS:
        b = data.load_bars(mk)
        d[mk] = b
        _FULL[mk] = _prep(b)
    return d


def power(d, n_entry=50, n_exit=20):
    """Signals and state-machine entries (no stop, no time exit, no price move after a signal) per share."""
    rows, tot_sig, tot_ent = {}, 0, 0
    for mk in MARKETS:
        c, ka = sessions(d[mk], mk)
        hiN, loN, hiX, loX = flags(c, n_entry, n_exit)
        st, ent = 0, 0
        for i in range(len(c)):
            if st == 1 and loX[i]:
                st = 0
            elif st == -1 and hiX[i]:
                st = 0
            if hiN[i] and not loN[i]:
                ent += st != 1; st = 1
            elif loN[i] and not hiN[i]:
                ent += st != -1; st = -1
        ns = int((hiN ^ loN).sum())
        rows[mk] = {"sessions": int(len(c)), "signals": ns, "long": int((hiN & ~loN).sum()),
                    "short": int((loN & ~hiN).sum()), "regime_entries": int(ent),
                    "first": str(ka[0].date()), "last": str(ka[-1].date())}
        tot_sig += ns; tot_ent += ent
    return {"by_market": rows, "signals": tot_sig, "regime_entries_lower_bound_of_trades": tot_ent}


def main_run():
    folder = HERE
    decl = json.load(open(os.path.join(folder, "declared.json")))
    checks.declared_hash(folder)
    assert decl.get("track") == "slow"
    cfgs = decl["configurations"]
    MW = float(decl["rule_main"]["max_wait_h"])
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
        return sim.simulate(sig, bk, mode=mode, max_wait_h=MW, **rule_of(c))

    rule0 = rule_of(c0)
    sig0 = build(d)
    main = sim.simulate(sig0, bk, max_wait_h=MW, **rule0)
    neigh = {c["id"]: run(c) for c in cfgs[1:]}
    every = sim.simulate(sig0, bk, mode="every", max_wait_h=MW, **rule0)
    print("simulated", len(main), "trades;", f"{time.time() - t0:.0f}s", flush=True)
    null = stats.null_test(main, bk, n_draws=2000, **rule0)
    print("null pct", null["percentile"], f"{time.time() - t0:.0f}s", flush=True)
    shift = checks.shift_test(sig0, bk, max_wait_h=MW, **rule0)

    def summ(t):
        if not len(t):
            return {"n": 0}
        return {"n": int(len(t)), "PF": stats.pf(t.R), "PF_gross": stats.pf(t.R_gross), "PF_stress": stats.pf(t.R_stress),
                "mean_R": float(t.R.mean()), "mean_R_gross": float(t.R_gross.mean()),
                "mean_net_bp": float(t.net_bp.mean()), "mean_gross_bp": float(t.gross_bp.mean()),
                "mean_swap_bp": float(t.swap_bp.mean()), "sum_R": float(t.R.sum()), "sum_R_gross": float(t.R_gross.sum()),
                "t_trade": stats.t_stat(t.R.to_numpy()), "t_trade_gross": stats.t_stat(t.R_gross.to_numpy()),
                "hold_tdays_median": float(t.hold_tdays.median())}
    groups = {"tech": ["aapl", "adbe", "amd", "amzn", "avgo", "crm", "csco", "fb", "googl", "intc", "msft", "mu", "nflx",
                       "nvda", "orcl", "pypl", "qcom", "tsla", "baba"],
              "financials": ["bac", "c", "gs", "jpm", "ma", "v", "wfc"],
              "health": ["jnj", "mrk", "pfe", "unh"],
              "industry_energy": ["ba", "cat", "ge", "cvx", "xom"],
              "consumer": ["dis", "hd", "mcd", "nke", "wmt"]}
    assert sorted(sum(groups.values(), [])) == MARKETS
    cnt = main.attrs["counts"]
    ex_bar = {(r.market, int(r.exit_i)) for r in main.itertuples() if r.reason == "event"}
    rev_lost = 0
    for mk, g in sig0.groupby("market"):
        tq = pd.DatetimeIndex(g.known_at).as_unit("ns").asi8
        ei = np.searchsorted(bk[mk].t, tq, side="left")
        taken = set(main.loc[main.market == mk, "entry_i"].astype(int))
        for e_ in ei:
            if (mk, int(e_)) in ex_bar and int(e_) not in taken:
                rev_lost += 1
    extra = {
        "gross_net_by_side": {"long": summ(main[main.side > 0]), "short": summ(main[main.side < 0]), "all": summ(main)},
        "by_market": {mk: summ(main[main.market == mk]) for mk in MARKETS},
        "by_group": {g: summ(main[main.market.isin(v)]) for g, v in groups.items()},
        "by_year_R_gross": {int(k): float(v) for k, v in main.groupby(main.entry_time.dt.year).R_gross.sum().items()},
        "by_year_R_net": {int(k): float(v) for k, v in main.groupby(main.entry_time.dt.year).R.sum().items()},
        "by_year_side_R_net": {f"{int(k[0])}_{'L' if k[1] > 0 else 'S'}": float(v)
                               for k, v in main.groupby([main.entry_time.dt.year, main.side]).R.sum().items()},
        "exit_reasons": main.reason.value_counts().to_dict(),
        "neighbours": {k: summ(v) for k, v in neigh.items()},
        "every_signal": summ(every),
        "counts": cnt, "reversal_signals_lost_to_one_position": int(rev_lost),
        "entry_clock_NY": pd.DatetimeIndex(main.entry_time).tz_convert(NY).strftime("%H:%M").value_counts().to_dict(),
        "shift_test": shift, "power": power(d, c0["n_entry"], c0["n_exit"]),
        "null_summary": {k: null[k] for k in null if k != "means"},
    }
    res = judge.verdict(folder, main, neigh, every, null, corr="compute", n_configs=len(cfgs), truncation=tr,
                        event_truncation=tre, max_hold_tdays=40,
                        data_desc="prepared hourly BID bars of the 40 US shares 2017-2021 (kit v2.1, PROVISIONAL costs)",
                        extra=extra)
    main.to_parquet(os.path.join(CACHE, "main_trades.parquet"))
    every.to_parquet(os.path.join(CACHE, "every_trades.parquet"))
    json.dump(extra, open(os.path.join(folder, "extra.json"), "w"), indent=1, default=str)
    print(res["verdict"], res["failed_bars"])
    print(res["ledger_line"])
    print(json.dumps(res.get("dividends"), default=str)[:3000])
    print(f"done in {time.time() - t0:.0f}s")
    return res


if __name__ == "__main__":
    if "--power" in sys.argv:
        print(json.dumps(power(load()), indent=1))
    else:
        main_run()
