"""Recompute the finalists with the verified FP Markets Raw-account costs (PROTOCOL_V2 section 3:
"provisional costs are replaced by the verified research and all finalists are then recomputed").

What changes against the research runs: r2/fp_costs.json (Raw account: gold cheaper, indices and crypto
at their verified spreads, ETH much wider) and FP trading hours for crypto (24/5: no weekend bars, a
time exit that falls in the weekend closure is executed at the Friday close).
Rules and parameters are the frozen FINALISTS of each track; nothing is re-tuned here.

Usage:  python3 lab/r2/recalc.py [name ...]        (no name = every sleeve below)
Output: results/r2/recalc/summary.json, results/r2/recalc/trades/<name>__<sym>.parquet (IS + VAL trades,
        FP costs, one position per sleeve) and one line per sleeve on stdout.
Every validation-period read is logged (results/val_access.log, label "<name>:<sym>:recalc_raw").
"""
import importlib.util
import json
import os
import sys
import time

import pandas as pd

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LAB)
import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
from goldlab.metrics import report  # noqa: E402
from goldlab.split import cut  # noqa: E402

OUT = os.path.join(LAB, "results", "r2", "recalc")


def _mod(path, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(LAB, path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def _r2track(track):
    return _mod(f"r2/tracks/{track}/strategy.py", f"r2_{track}_strategy")


def _crypto_fp_hours(make_orders):
    """FP Markets is closed at the weekend: a time exit scheduled inside the closure is done on the last
    bar before it (lab convention gl.exit_index), instead of at the Sunday reopen with the weekend gap."""
    def wrapped(m1, **params):
        o = make_orders(m1, **params)
        if len(o):
            o = o.copy()
            o["exit_i"] = gl.exit_index(m1, pd.DatetimeIndex(o["sched_exit"]))
            o = o[o.exit_i > o.entry_i].reset_index(drop=True)
        return o
    return wrapped


def sleeves():
    """[(track, name, sym, make_orders, params)] for every finalist that passed (or was validated) so far."""
    out = []
    m = _r2track("idx_us")
    for name in ("noise30", "ocm4"):
        out.append(("idx_us", name, "us100", m.make_orders, m.FINALISTS[name]["params"]))
    m = _r2track("crypto")
    for sym in m.FINALISTS["brk72_24h_wd"]["syms"]:
        out.append(("crypto", "brk72_24h_wd", sym, _crypto_fp_hours(m.make_orders), m.FINALISTS["brk72_24h_wd"]["params"]))
    m = _r2track("leadlag")
    out.append(("leadlag", "nq_btc_follow", "btcusd", m.make_orders, m.FINALISTS["nq_btc_follow"]["params"]))
    m = _r2track("ml")
    for name in ("F1_brk_ridge_filter", "F2_brk_unfiltered"):
        for sym in m.FINALISTS[name]["syms"]:
            out.append(("ml", name, sym, m.make_orders, m.FINALISTS[name]["params"]))
    m = _r2track("overnight")
    out.append(("overnight", "GOLD_FRI_PM", "xauusd", m.make_orders, m.finalist_params("GOLD_FRI_PM", "xauusd")))
    # round-1 survivors (gold), now under the FP Raw costs (module names as in holdout.py: the numba cache is keyed on them)
    m = _mod("tracks/trend/strategy.py", "strategy_trend")
    out.append(("r1_trend", "donch4h_stop", "xauusd", m.make_orders, m.FINALISTS["donch4h_stop"]))
    m = _mod("tracks/orb/strategy.py", "strategy_orb")
    out.append(("r1_orb", "orb_asia_2d_buf10", "xauusd", m.make_orders, m.FINALISTS["orb_asia_2d_buf10"]))
    return out


KEEP = ("n", "trades_per_year", "win_rate", "pf", "t_stat", "expectancy_R", "total_R", "max_dd_R", "years_pos",
        "long_n", "long_R", "short_n", "short_R", "avg_hold_h", "max_hold_h", "by_year_R", "exit_reasons")


def _rep(t):
    r = report(t)
    return {k: r[k] for k in KEEP if k in r}


def _bps(t):
    return round(float((t["pnl"] / t["entry"]).mean() * 1e4), 2) if len(t) else 0.0


def recalc(track, name, sym, make_orders, params):
    lab = f"{name}:{sym}:recalc_raw"
    m1 = r2.load(sym)
    t = r2.run(sym, make_orders, params, "fp", True, m1)
    ts = r2.run(sym, make_orders, params, "stress", True, m1)
    tg = r2.run(sym, make_orders, params, "gross", True, m1)
    te = r2.run(sym, make_orders, params, "fp", False, m1)
    ti, tv = cut(t, "is"), cut(t, "val", track=track, label=lab)
    ev = {"sym": sym, "is": report(ti), "is_stress": report(cut(ts, "is")), "is_every_signal": report(cut(te, "is"))}
    crit = r2.is_criteria(ev)
    tvs = cut(ts, "val", track=track, label=lab + ":stress")
    tvg = cut(tg, "val", track=track, label=lab + ":gross")
    tve = cut(te, "val", track=track, label=lab + ":every")
    rv, rve = report(tv), report(tve)
    vcrit = {"pf>=1.06": rv.get("pf", 0) >= 1.06, "expectancy>0": rv.get("expectancy_R", -1) > 0,
             "every_signal_exp>0": rve.get("expectancy_R", -1) > 0}
    vcrit["pass"] = all(vcrit.values())
    os.makedirs(os.path.join(OUT, "trades"), exist_ok=True)
    keep_cols = [c for c in ("side", "entry_time", "exit_time", "entry", "exit", "stop", "reason", "swap", "pnl",
                             "risk", "R", "ret", "hold_min") if c in t.columns]
    t[keep_cols].to_parquet(os.path.join(OUT, "trades", f"{name}__{sym}.parquet"))
    return {
        "track": track, "name": name, "sym": sym, "params": params,
        "is": _rep(ti), "is_stress": _rep(cut(ts, "is")), "is_gross": _rep(cut(tg, "is")),
        "is_every_signal": _rep(cut(te, "is")),
        "is_bps_net": _bps(ti), "is_bps_gross": _bps(cut(tg, "is")),
        "is_criteria": crit,
        "val": _rep(tv), "val_stress": _rep(tvs), "val_gross": _rep(tvg), "val_every_signal": _rep(tve),
        "val_bps_net": _bps(tv), "val_bps_gross": _bps(tvg),
        "val_criteria": vcrit,
    }


def line(r):
    i, v = r["is"], r["val"]
    f = lambda d, k: d.get(k, float("nan"))
    return (f"{r['name'][:20]:20s} {r['sym']:7s} | IS n {f(i, 'n'):5} PF {f(i, 'pf'):5.2f} t {f(i, 't_stat'):5.2f} "
            f"stressPF {f(r['is_stress'], 'pf'):5.2f} {'ok ' if r['is_criteria']['pass'] else 'NO '}"
            f"| VAL n {f(v, 'n'):5} ({f(v, 'trades_per_year'):5.0f}/an) PF {f(v, 'pf'):5.2f} t {f(v, 't_stat'):5.2f} "
            f"R/trade {f(v, 'expectancy_R'):+.3f} stressPF {f(r['val_stress'], 'pf'):5.2f} "
            f"bps net {r['val_bps_net']:+6.2f} / brut {r['val_bps_gross']:+6.2f} "
            f"{'ok' if r['val_criteria']['pass'] else 'NO'} | {v.get('by_year_R')}")


if __name__ == "__main__":
    want = set(sys.argv[1:])
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "summary.json")
    res = json.load(open(path)) if os.path.exists(path) else {}
    last_sym = None
    for track, name, sym, mo, params in sleeves():
        if want and name not in want:
            continue
        if sym != last_sym:
            r2.free()
            last_sym = sym
        t0 = time.time()
        r = recalc(track, name, sym, mo, params)
        res[f"{name}:{sym}"] = r
        json.dump(res, open(path, "w"), indent=1, default=str)
        print(line(r), f"[{time.time() - t0:.0f}s]", flush=True)
