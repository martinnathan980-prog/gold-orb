"""Idea 030: weekly cross-sectional reversal across the seven dollar pairs (basket of 7 markets).
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/030_weekly_reversal_dollar_pairs/run.py
Reads declared.json (never writes it). Each configuration builds its own signal table (lookback, K, entry hour) and is
simulated with kit.sim.simulate on the 7 markets in one call; the null is kit.stats.null_test on the main trades."""
import json, os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
from kit import checks, judge, sim, stats, data  # noqa: E402

# currency -> (pair, +1 if the pair is xxxusd (currency is the base), -1 if usdxxx)
CCY = [("EUR", "eurusd", 1), ("GBP", "gbpusd", 1), ("JPY", "usdjpy", -1), ("AUD", "audusd", 1),
       ("CAD", "usdcad", -1), ("CHF", "usdchf", -1), ("NZD", "nzdusd", 1)]
MARKETS = [p for _, p, _ in CCY]
END = pd.Timestamp("2022-01-01", tz="UTC")
H = pd.Timedelta(hours=1)
STALE = pd.Timedelta(hours=72)
MAX_WAIT_H = 1
N_DRAWS = 2000
CACHE = os.path.expanduser("~/explore_data/idea_030")


def _px_at(b, times):
    """Close of the last bar whose END (open + 1 h) is <= t and > t - 72 h; NaN otherwise."""
    if len(b) == 0:
        return np.full(len(times), np.nan)
    end = (pd.DatetimeIndex(b.index) + H).as_unit("ns").asi8
    c = b["close"].to_numpy(float)
    t = pd.DatetimeIndex(times).as_unit("ns").asi8
    k = np.searchsorted(end, t, side="right") - 1
    ok = (k >= 0)
    kc = np.clip(k, 0, None)
    ok &= end[kc] > t - STALE.value
    return np.where(ok, c[kc], np.nan)


def build(d, lookback_days=7, k=2, ka_hour=8):
    """Whole signal table: per Friday T = 20:00 UTC, rank the 7 currencies' log return vs USD over lookback_days; buy
    the k weakest, sell the k strongest; known_at = the next Monday ka_hour:00 UTC."""
    T = pd.date_range("2013-01-04", "2021-12-31", freq="W-FRI", tz="UTC") + pd.Timedelta(hours=20)
    ka = T.normalize() + pd.Timedelta(days=3) + pd.Timedelta(hours=ka_hour)
    keep = ka < END
    T, ka = T[keep], ka[keep]
    T0 = T - pd.Timedelta(days=lookback_days)
    R = np.empty((len(T), len(CCY)))
    for j, (_, p, sgn) in enumerate(CCY):
        R[:, j] = sgn * np.log(_px_at(d[p], T) / _px_at(d[p], T0))
    rows = []
    for i in np.flatnonzero(np.isfinite(R).all(1)):
        order = np.argsort(R[i], kind="stable")            # ascending: weakest first; ties by the fixed CCY order
        for j in order[:k]:                                # buy the weak currency
            rows.append((ka[i], int(CCY[j][2]), CCY[j][1], "buy_weak", CCY[j][0]))
        for j in order[::-1][:k]:                          # sell the strong currency
            rows.append((ka[i], -int(CCY[j][2]), CCY[j][1], "sell_strong", CCY[j][0]))
    sig = pd.DataFrame(rows, columns=["known_at", "side", "market", "role", "ccy"])
    sig["known_at"] = pd.DatetimeIndex(sig.known_at).tz_convert("UTC")
    return sig.sort_values(["known_at", "market"]).reset_index(drop=True)


def run_cfg(sig, bk, c, mode="one"):
    t = sim.simulate(sig[["known_at", "side", "market"]], bk, exit=tuple(c["exit"]), stop=tuple(c["stop"]), mode=mode,
                     max_wait_h=MAX_WAIT_H)
    t["role"] = sig["role"].to_numpy()[t.sig.to_numpy()]
    t["ccy"] = sig["ccy"].to_numpy()[t.sig.to_numpy()]
    return t


def _fig(g):
    return {"n": int(len(g)), "PF_gross": stats.pf(g.R_gross), "PF": stats.pf(g.R), "PF_stress": stats.pf(g.R_stress),
            "mean_R_gross": float(g.R_gross.mean()), "mean_R": float(g.R.mean()), "sum_R": float(g.R.sum()),
            "mean_gross_bp": float(g.gross_bp.mean()), "mean_net_bp": float(g.net_bp.mean()),
            "t_trade": stats.t_stat(g.R), "t_trade_gross": stats.t_stat(g.R_gross)}


def split(t, col):
    out = {}
    for v, g in t.groupby(col):
        f = _fig(g)
        if col == "market":
            f["by_year_R"] = {int(k): float(x) for k, x in stats.by_year(g).items()}
        out[str(v)] = f
    return out


def main_():
    decl = json.load(open(os.path.join(HERE, "declared.json")))
    checks.declared_hash(HERE)
    os.makedirs(CACHE, exist_ok=True)
    d = {mk: data.load_bars(mk) for mk in MARKETS}
    tr = checks.truncation_test(build, d, ["2016-06-01 14:30", "2019-09-09 09:00", "2017-03-06 08:00"],
                                row_len={mk: H for mk in MARKETS})
    assert tr["pass"], tr
    bk = sim.books(d)
    cfgs = decl["configurations"]
    sig_main = build(d, cfgs[0]["lookback_days"], cfgs[0]["k"], cfgs[0]["ka_hour_monday_utc"])
    print("main signals:", len(sig_main), "weeks:", sig_main.known_at.nunique(), sig_main.market.value_counts().to_dict())
    results = {}
    for c in cfgs:
        s = sig_main if c is cfgs[0] else build(d, c["lookback_days"], c["k"], c["ka_hour_monday_utc"])
        results[c["id"]] = run_cfg(s, bk, c)
    main = results.pop(cfgs[0]["id"])
    c0 = cfgs[0]
    every = run_cfg(sig_main, bk, c0, mode="every")
    null = stats.null_test(main, bk, exit=tuple(c0["exit"]), stop=tuple(c0["stop"]), n_draws=N_DRAWS)
    shift = checks.shift_test(sig_main[["known_at", "side", "market"]], bk, exit=tuple(c0["exit"]), stop=tuple(c0["stop"]))
    main.to_csv(os.path.join(CACHE, "main_trades.csv"), index=False)
    extra = {"by_market_main": split(main, "market"), "by_side_main": split(main, "side"),
             "by_role_main": split(main, "role"), "by_ccy_main": split(main, "ccy"),
             "gross_main": {"PF_gross": stats.pf(main.R_gross), "mean_R_gross": float(main.R_gross.mean()),
                            "t_daily_gross": stats.t_stat(stats.daily_sums(main, "R_gross")),
                            "mean_gross_bp": float(main.gross_bp.mean()), "mean_net_bp": float(main.net_bp.mean()),
                            "mean_swap_bp": float(main.swap_bp.mean())},
             "neighbours_detail": {k: {"n": int(len(t)), "PF_gross": stats.pf(t.R_gross), "PF": stats.pf(t.R),
                                       "PF_stress": stats.pf(t.R_stress), "mean_R": float(t.R.mean()),
                                       "mean_R_gross": float(t.R_gross.mean()),
                                       "t_daily": stats.t_stat(stats.daily_sums(t))} for k, t in results.items()},
             "shift_test": shift, "counts_every": every.attrs["counts"],
             "exit_reasons_main": main.reason.value_counts().to_dict(),
             "truncation": {k: v for k, v in tr.items() if k != "cuts"}}
    res = judge.verdict(HERE, main, results, every, null, corr="compute", n_configs=len(cfgs), truncation=tr,
                        data_desc="prices only; prepared H1 BID bars of the 7 dollar pairs 2013-2021", extra=extra)
    print(res["verdict"], res["failed_bars"])
    print(res["ledger_line"])
    for k, v in res["bars"].items():
        print(f"  {k}: {v['value']} {'ok' if v['pass'] else 'FAIL'}")
    for k in ("gross_main", "by_side_main", "by_role_main", "by_market_main", "neighbours_detail", "shift_test",
              "exit_reasons_main"):
        print(k, json.dumps(extra[k], default=str))
    print("main summary", json.dumps({k: v for k, v in res["main"].items() if k != "by_year_R"}, default=str))
    print("by_year_R", res["main"].get("by_year_R"))
    print("null", {k: v for k, v in null.items() if k != "means"})
    print("selection", json.dumps(res["selection"], default=str))
    return res


if __name__ == "__main__":
    main_()
