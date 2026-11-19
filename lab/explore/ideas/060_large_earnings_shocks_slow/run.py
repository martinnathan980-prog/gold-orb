"""Idea 060: large earnings shocks held for weeks, broad universe of US shares on daily bars (slow track).
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/060_large_earnings_shocks_slow/run.py
Reads declared.json (never writes it). Order: hash -> truncation -> run -> verdict. Writes results.json, trials.jsonl,
extra.json in the idea folder and the trade tables in ~/explore_data/idea_060 (for the attack, if any)."""
import json, os, sys, time
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from signals import load_data, make_build, EXPLORE  # noqa: E402
from kit import checks, judge, sim, stats  # noqa: E402

CACHE = os.path.expanduser("~/explore_data/idea_060")
T0 = time.time()


def log(*a):
    print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)


def side_year_report(t):
    def f(x):
        if not len(x):
            return {"n": 0}
        return {"n": int(len(x)), "PF_net": stats.pf(x.R), "mean_R": float(x.R.mean()), "PF_gross": stats.pf(x.R_gross),
                "mean_R_gross": float(x.R_gross.mean()), "mean_gross_bp": float(x.gross_bp.mean()),
                "mean_net_bp": float(x.net_bp.mean()), "t_trades_net": float(stats.t_stat(x.R)),
                "t_trades_gross": float(stats.t_stat(x.R_gross))}
    yr = pd.DatetimeIndex(t.entry_time).year
    return {"all": f(t), "long": f(t[t.side > 0]), "short": f(t[t.side < 0]),
            "by_year": {int(y): f(t[yr == y]) for y in sorted(set(yr))},
            "by_year_side": {f"{int(y)}_{'long' if s > 0 else 'short'}": f(t[(yr == y) & (t.side == s)])
                             for y in sorted(set(yr)) for s in (1, -1)},
            "exit_reasons": {str(k): int(v) for k, v in t.reason.value_counts().items()},
            "mean_hold_sessions": float(t.hold_tdays.mean()), "max_hold_sessions": int(t.hold_tdays.max()),
            "mean_swap_bp": float(t.swap_bp.mean())}


def crossing_report(t):
    """Holds that cross the company's next results day: a results event_session (every results row of the calendar,
    late_suspect included) inside [entry session, exit session] (New York dates)."""
    sys.path.insert(0, os.path.join(EXPLORE, "scout"))
    from events_edgar import calendar
    cal = calendar("2021-12-31", kind="results", drop_late=False)
    rs = {}
    for k, s in zip(cal.key, pd.to_datetime(cal.event_session).dt.strftime("%Y-%m-%d")):
        rs.setdefault(k, []).append(s)
    rs = {k: np.array(sorted(v)) for k, v in rs.items()}
    e = pd.DatetimeIndex(t.entry_time).tz_convert("America/New_York").strftime("%Y-%m-%d")
    x = (pd.DatetimeIndex(t.exit_time) - pd.Timedelta(seconds=1)).tz_convert("America/New_York").strftime("%Y-%m-%d")
    cross = np.array([bool(((rs.get(m, np.array([])) >= a) & (rs.get(m, np.array([])) <= b)).any())
                      for m, a, b in zip(t.market, e, x)])
    def f(m):
        y = t[m]
        return {"n": int(m.sum()), "mean_R": float(y.R.mean()) if len(y) else None,
                "mean_R_gross": float(y.R_gross.mean()) if len(y) else None,
                "long": int((y.side > 0).sum()), "short": int((y.side < 0).sum())}
    return {"crossing": f(cross), "not_crossing": f(~cross)}


def main():
    folder = HERE
    decl = json.load(open(os.path.join(folder, "declared.json")))
    checks.declared_hash(folder)
    assert decl["track"] == "slow"
    cfgs = decl["configurations"]
    os.makedirs(CACHE, exist_ok=True)
    bs, d = load_data()
    log("data", len(d["bars"]), "rows,", len(d["events"]), "events")
    builds = {thr: make_build(thr) for thr in sorted({c["threshold"] for c in cfgs})}
    m0 = cfgs[0]
    build = builds[m0["threshold"]]
    sig = build(d)
    log("main signals", len(sig))
    tr = checks.truncation_test(build, d, row_len={"bars": "known_at", "events": pd.Timedelta(0)})
    log("truncation", tr["pass"], {k: tr.get(k) for k in ("n_cuts", "n_signal_cuts", "n_after_cuts", "n_random_cuts")})
    json.dump({k: v for k, v in tr.items() if isinstance(v, (int, float, str, bool, type(None)))},
              open(os.path.join(CACHE, "truncation.json"), "w"), indent=1, default=str)
    assert tr["pass"], "truncation test failed"
    sigs = {thr: (sig if thr == m0["threshold"] else b(d)) for thr, b in builds.items()}
    bk = sim.books(bs)
    log("books")

    def rule(c):
        return dict(exit=tuple(c["exit"]), stop=tuple(c["stop"]))

    def run(c, mode="one"):
        return sim.simulate(sigs[c["threshold"]], bk, max_wait_h=96, mode=mode, **rule(c))
    main_t = run(m0)
    log("main", len(main_t), "PF net", stats.pf(main_t.R), "PF gross", stats.pf(main_t.R_gross))
    neigh = {c["id"]: run(c) for c in cfgs[1:]}
    every = run(m0, "every")
    log("neighbours + every done")
    null = stats.null_test(main_t, bk, n_draws=2000, **rule(m0))
    log("null pct", null["percentile"])
    sh = checks.shift_test(sig, bk, max_wait_h=96, **rule(m0))
    mc = checks.min_commission_test(sig, bk, max_wait_h=96, **rule(m0))
    log("shift, min commission done")
    extra = {"main": side_year_report(main_t), "next_results": crossing_report(main_t),
             "neighbours": {k: side_year_report(v)["all"] | {"long": side_year_report(v)["long"],
                                                              "short": side_year_report(v)["short"]}
                            for k, v in neigh.items()},
             "every": side_year_report(every)["all"], "shift": sh, "min_commission": mc,
             "counts_main": main_t.attrs.get("counts", {}) and
             {k: int(sum(c.get(k, 0) for c in main_t.attrs["counts"].values()))
              for k in ("signals", "stale", "no_bar", "open_at_end", "no_d20", "overlap_skipped", "taken")},
             "survivors_only": "today's S&P 500 list: 183 companies that left the index since 2017 are missing; the long "
                               "side after up-shocks is flattered, the short side after down-shocks lacks its best cases"}
    json.dump(extra, open(os.path.join(folder, "extra.json"), "w"), indent=1, default=str)
    main_t.to_parquet(os.path.join(CACHE, "main_trades.parquet"))
    every.to_parquet(os.path.join(CACHE, "every_trades.parquet"))
    sig.to_parquet(os.path.join(CACHE, "main_signals.parquet"))
    res = judge.verdict(folder, main_t, neigh, every, null, n_configs=len(cfgs), truncation=tr,
                        max_hold_tdays=40, groups="sector", min_commission=mc,
                        idea=decl["idea"],
                        data_desc="EDGAR 8-K results calendar + Yahoo daily bars of 382 S&P 500 shares (not the lab's 40), "
                                  "2017-2021, survivors only",
                        extra={"shift": sh, "next_results": extra["next_results"],
                               "long_short": {k: extra["main"][k] for k in ("long", "short")}})
    log("VERDICT", res["verdict"], "failed:", res["failed_bars"])
    print(res["ledger_line"])
    json.dump({"verdict": res["verdict"], "failed_bars": res["failed_bars"], "ledger_line": res["ledger_line"]},
              open(os.path.join(CACHE, "verdict_short.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
