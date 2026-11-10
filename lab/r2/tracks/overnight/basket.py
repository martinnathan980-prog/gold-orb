"""Basket evaluation (PROTOCOL_V2 section 4: one rule, same settings, several markets, trades pooled) and a
basket version of the random-entry null with SYNCHRONISED random times (the sleeves of a basket trade the same
nights, so their random replays must also share their dates, otherwise the null would be too easy to beat).
IS only.  Nothing here touches the validation period (trades are cut with cut(.., "is")).
"""
import json
import os

import numpy as np
import pandas as pd

from common import RES, S, gl, r2, use
from goldlab.metrics import report
from goldlab.sim import simulate
from goldlab.split import cut


def pooled_is(sleeves, modes=("fp", "stress", "gross", "every"), make_orders=None):
    """sleeves: list of (sym, params). Returns {mode: pooled IS trades} and {sym: {mode: trades}}."""
    mo = make_orders or S.make_orders
    per = {}
    for sym, params in sleeves:
        use(sym)
        m1 = r2.load(sym)
        d = {}
        for mode in modes:
            if mode == "every":
                t = r2.run(sym, mo, params, "fp", False, m1)
            else:
                t = r2.run(sym, mo, params, mode, True, m1)
            t = cut(t, "is").copy()
            t["sym"] = sym
            d[mode] = t
        per[sym] = d
    pooled = {mode: pd.concat([per[s][mode] for s, _ in sleeves]).sort_values("entry_time") for mode in modes}
    return pooled, per


def bps(t):
    return round(float((t["pnl"] / t["entry"]).mean() * 1e4), 2) if len(t) else 0.0


def cluster_t(t, freq="D"):
    """t-stat of the mean R when trades entered on the same day (all sleeves) are averaged first."""
    g = t.groupby(t.entry_time.dt.tz_convert("America/New_York").dt.floor(freq))["R"].mean()
    return round(float(g.mean() / (g.std(ddof=1) / np.sqrt(len(g)))), 2), int(len(g))


def basket_ev(sleeves, make_orders=None):
    pooled, per = pooled_is(sleeves, make_orders=make_orders)
    ev = {"sym": "+".join(s for s, _ in sleeves), "is": report(pooled["fp"]), "is_bps_per_trade": bps(pooled["fp"]),
          "is_stress": report(pooled["stress"]), "is_gross": report(pooled["gross"]),
          "is_gross_bps_per_trade": bps(pooled["gross"]), "is_every_signal": report(pooled["every"])}
    ct, nc = cluster_t(pooled["fp"])
    ev["cluster_t"] = ct
    ev["n_clusters"] = nc
    return ev, pooled, per


def null_basket(sleeves, n_seeds=200, seed=0, make_orders=None, sync=True):
    """Random-entry null (mode 'time') for a basket. Each rule trade is replayed at market at a random moment
    of the IS period with the same side, stop distance (relative to price) and duration in bars; with
    sync=True all the trades entered on the same New-York date (across sleeves) share ONE random moment."""
    mo = make_orders or S.make_orders
    info = []
    for sym, params in sleeves:
        use(sym)
        m1 = r2.load(sym)
        orders = mo(m1, **params).reset_index(drop=True)
        t = cut(simulate(m1, orders, sym=sym, costs=r2.costs(sym), no_overlap=True), "is")
        o = orders.loc[t.index]
        idx = m1.index
        fill_i = idx.searchsorted(t.entry_time.to_numpy())
        entry = t.entry.to_numpy(float)
        xi = o["exit_i"].to_numpy(np.int64)
        hi = int(idx.searchsorted(pd.Timestamp("2022-01-01", tz="UTC")))
        info.append({"sym": sym, "side": t.side.to_numpy(), "stop_rel": t.risk.to_numpy(float) / entry,
                     "dur": np.maximum(xi - fill_i, 1), "R": t.R.to_numpy(),
                     "day": t.entry_time.dt.tz_convert("America/New_York").dt.floor("D").to_numpy(), "hi": hi})
        if len(info) == 1:
            ref_ns = idx.values[:hi].astype("datetime64[ns]").astype(np.int64)
    all_days = np.unique(np.concatenate([d["day"] for d in info]))
    rule_mean = float(np.concatenate([d["R"] for d in info]).mean())
    rng = np.random.default_rng(seed)
    draws = ref_ns[rng.integers(0, len(ref_ns) - 2, (n_seeds, len(all_days)))]     # one random moment per rule date
    sum_r, cnt = np.zeros(n_seeds), np.zeros(n_seeds)
    for d in info:
        use(d["sym"])
        m1 = r2.load(d["sym"])
        ns = m1.index.values[:d["hi"]].astype("datetime64[ns]").astype(np.int64)
        mid = (m1["bc"].to_numpy() + m1["ac"].to_numpy()) / 2
        c = r2.costs(d["sym"])
        col = np.searchsorted(all_days, d["day"])
        for k in range(n_seeds):
            if sync:
                ei = np.minimum(np.searchsorted(ns, draws[k, col], side="left"), d["hi"] - 2)
            else:
                ei = rng.integers(0, d["hi"] - 2, len(d["side"]))
            no = pd.DataFrame({"entry_i": ei, "side": d["side"], "stop_dist": d["stop_rel"] * mid[ei],
                               "exit_i": np.minimum(ei + d["dur"], len(m1) - 1)})
            tn = cut(simulate(m1, no, sym=d["sym"], costs=c, no_overlap=True), "is")
            sum_r[k] += float(tn.R.sum())
            cnt[k] += len(tn)
    r2.free()
    means = sum_r / np.maximum(cnt, 1)
    return {"n": int(sum(len(d["R"]) for d in info)), "mode": "time", "sync": bool(sync), "rule_mean_R": round(rule_mean, 4),
            "null_mean_R": round(float(means.mean()), 4), "null_p95_R": round(float(np.percentile(means, 95)), 4),
            "null_p975_R": round(float(np.percentile(means, 97.5)), 4), "null_max_R": round(float(means.max()), 4),
            "percentile": round(float((means < rule_mean).mean() * 100), 1), "pass": bool((means < rule_mean).mean() >= 0.975)}
