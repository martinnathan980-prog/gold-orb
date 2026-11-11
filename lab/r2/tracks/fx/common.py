"""Track `fx` (round 3): shared helpers -- in-sample-only frames, basket evaluation (PROTOCOL_V3 section 4).

* `load_is(sym)` puts into r2's cache a frame CUT at 2022-01-15 (so no 2022+ quote is ever simulated or seen;
  the extra two weeks only let trades entered before 2022-01-01 reach their exit).  Only IS trades
  (entry < 2022-01-01) are ever reported (`goldlab.split.cut(.., "is")`).
* `basket(...)` runs one rule with one parameter set on every pair, logs one trial per pair
  (r2.log_trial("fx", ...)) and returns pooled basket statistics.
"""
import gc
import json
import math
import os
import sys

import numpy as np
import pandas as pd

LAB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
if LAB not in sys.path:
    sys.path.insert(0, LAB)
import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
from goldlab import data as _data  # noqa: E402
from goldlab.metrics import report  # noqa: E402
from goldlab.split import cut  # noqa: E402

PAIRS = ["eurusd", "gbpusd", "usdjpy", "audusd", "usdcad", "usdchf", "nzdusd", "eurjpy"]
OUT = os.path.join(LAB, "results", "r2", "fx")
IS_END_FRAME = "2022-01-15"
os.makedirs(OUT, exist_ok=True)


def load_is(sym):
    """In-sample frame (cut at 2022-01-15), also installed in r2's cache so r2.* functions use it."""
    if sym in r2._fp_cache and r2._fp_cache[sym].index[-1] < pd.Timestamp(IS_END_FRAME, tz="UTC"):
        return r2._fp_cache[sym]
    r2.free()
    gc.collect()
    df = pd.read_parquet(os.path.join(_data.DATA, "fp", f"{sym}_m1.parquet"))
    df = df.iloc[:int(df.index.searchsorted(pd.Timestamp(IS_END_FRAME, tz="UTC")))].copy()
    gc.collect()
    r2._fp_cache[sym] = df
    return df


def evaluate(sym, make_orders, params, full=False, no_overlap=True):
    """Same as r2.evaluate (IS only) but on the cut frame, and also returns the IS trade frames."""
    m1 = load_is(sym)
    t = cut(r2.run(sym, make_orders, params, "fp", no_overlap, m1), "is")
    ev = {"sym": sym, "is": report(t), "is_bps_per_trade": r2._bps(t)}
    tr = {"fp": t}
    if full:
        ts = cut(r2.run(sym, make_orders, params, "stress", no_overlap, m1), "is")
        tg = cut(r2.run(sym, make_orders, params, "gross", no_overlap, m1), "is")
        ev["is_stress"], ev["is_gross"] = report(ts), report(tg)
        ev["is_gross_bps_per_trade"] = r2._bps(tg)
        tr["stress"], tr["gross"] = ts, tg
        if no_overlap:
            te = cut(r2.run(sym, make_orders, params, "fp", False, m1), "is")
            ev["is_every_signal"] = report(te)
            tr["every"] = te
    return ev, tr


def _pf(R):
    g, l = R[R > 0].sum(), -R[R < 0].sum()
    return float(g / l) if l > 0 else float("inf")


def pooled(t):
    """Basket statistics on pooled IS trades (column `sym`)."""
    if len(t) == 0:
        return {"n": 0}
    R = t["R"].to_numpy()
    td = gl.trading_day(t.entry_time)
    daily = t.groupby(td)["R"].sum()
    xd = gl.trading_day(t.exit_time)
    daily_x = t.groupby(xd)["R"].sum()
    wk = t.groupby(t.exit_time.dt.tz_convert(None).dt.to_period("W"))["R"].sum()
    wk_all = wk.reindex(pd.period_range(wk.index.min(), wk.index.max(), freq="W"), fill_value=0.0)
    yrs = t.groupby(t.entry_time.dt.year)["R"].sum()
    by_sym = t.groupby("sym")["R"].agg(["count", "mean", "sum"])
    tot = float(R.sum())
    n_days_span = np.busday_count(td.min().date(), td.max().date()) + 1
    out = {
        "n": int(len(t)), "pf": round(_pf(R), 3), "expectancy_R": round(float(R.mean()), 4), "total_R": round(tot, 1),
        "t_trades": round(float(R.mean() / (R.std(ddof=1) / math.sqrt(len(R)))), 2),
        "t_daily": round(float(daily.mean() / (daily.std(ddof=1) / math.sqrt(len(daily)))), 2),
        "n_days": int(len(daily)), "trades_per_weekday": round(len(t) / n_days_span, 2),
        "years_pos": f"{int((yrs > 0).sum())}/{len(yrs)}", "by_year_R": {int(k): round(float(v), 1) for k, v in yrs.items()},
        "win_days_pct": round(float((daily_x > 0).mean() * 100), 1),
        "weeks_pos_pct": round(float((wk_all > 0).mean() * 100), 1),
        "long_n": int((t.side > 0).sum()), "long_R": round(float(t.loc[t.side > 0, "R"].sum()), 1),
        "short_n": int((t.side < 0).sum()), "short_R": round(float(t.loc[t.side < 0, "R"].sum()), 1),
        "bps_per_trade": round(float((t["pnl"] / t["entry"]).mean() * 1e4), 2),
        "pairs_pos": f"{int((by_sym['mean'] > 0).sum())}/{len(by_sym)}",
        "max_pair_share": round(float(by_sym["sum"].max() / tot), 3) if tot > 0 else None,
        "by_sym": {s: {"n": int(r["count"]), "exp_R": round(float(r["mean"]), 4), "total_R": round(float(r["sum"]), 1)}
                   for s, r in by_sym.iterrows()},
    }
    return out


def basket_criteria(b):
    """PROTOCOL_V3 section 4 basket criteria (those computable from the pooled runs)."""
    p = b["fp"]
    if p.get("n", 0) == 0:
        return {"pass": False}
    yp, yn = (int(x) for x in p["years_pos"].split("/"))
    pp, pn = (int(x) for x in p["pairs_pos"].split("/"))
    c = {"n>=250": p["n"] >= 250, "pf>=1.12": p["pf"] >= 1.12, "t_daily>=2.5": p["t_daily"] >= 2.5,
         "years_pos>=60%": yp >= 0.6 * yn, "pairs_pos>=65%": pp >= 0.65 * pn,
         "max_pair_share<=25%": p["max_pair_share"] is not None and p["max_pair_share"] <= 0.25}
    if "stress" in b:
        c["stress_pf>=1.04"] = b["stress"]["pf"] >= 1.04
    if "every" in b:
        c["every_signal_exp>0"] = b["every"]["expectancy_R"] > 0
    c["pass"] = all(c.values())
    return c


def basket(name, make_orders, params, syms=PAIRS, full=False, log=True, save_trades=False, tag=None):
    """Run one configuration on every pair; one r2.log_trial per pair; pooled statistics."""
    pools = {}
    per = {}
    for sym in syms:
        ev, tr = evaluate(sym, make_orders, params, full=full)
        if log:
            r2.log_trial("fx", sym, {"name": name, **params} if tag is None else {"name": name, "tag": tag, **params}, ev)
        per[sym] = {k: v for k, v in ev.items() if k != "sym"}
        for k, t in tr.items():
            if len(t):
                t = t.copy()
                t["sym"] = sym
                pools.setdefault(k, []).append(t)
    res = {"name": name, "params": params, "per_pair": per}
    for k, lst in pools.items():
        T = pd.concat(lst, ignore_index=True)
        res[k] = pooled(T)
        if save_trades:
            keep = [c for c in ("sym", "side", "entry_time", "exit_time", "entry", "exit", "stop", "reason", "swap", "pnl",
                                "risk", "R", "ret", "hold_min") if c in T.columns]
            T[keep].to_parquet(os.path.join(OUT, f"trades_{name}_{k}.parquet"))
    if "gross" in res:
        res["gross_bps_per_trade"] = res["gross"]["bps_per_trade"]
    res["criteria"] = basket_criteria(res)
    return res


def short(res):
    p = res.get("fp", {})
    s = (f"{res['name'][:28]:28s} n {p.get('n', 0):5d} PF {p.get('pf', 0):5.2f} expR {p.get('expectancy_R', 0):+.3f} "
         f"tD {p.get('t_daily', 0):5.2f} bps {p.get('bps_per_trade', 0):+5.2f} yrs {p.get('years_pos')} pairs {p.get('pairs_pos')} "
         f"maxsh {p.get('max_pair_share')} L/S {p.get('long_R')}/{p.get('short_R')}")
    if "gross" in res:
        s += f" | gross bps {res['gross']['bps_per_trade']:+.2f} PF {res['gross']['pf']:.2f} stressPF {res['stress']['pf']:.2f} every {res['every']['expectancy_R']:+.3f}"
    return s


def save(obj, fname):
    with open(os.path.join(OUT, fname), "w") as f:
        json.dump(obj, f, indent=1, default=str)
