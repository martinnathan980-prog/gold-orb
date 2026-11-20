"""Trades of the scan through kit.sim.simulate, and their per-rule aggregates (GRAMMAR.md 'Simulation').

One call of sim.simulate per market and exit length, holding every rule of that exit as its own `rule` (the kit's
one-position filter works per market AND rule): mode 'one', exit ('hours', N), stop ('d20', 2.0), the kit's FP costs
(net, stress = x1.5, gross), max_wait_h = MAX_WAIT_H = None: a signal is entered at the open of the first hourly bar
opening at or after its known_at, however long the market is shut in between (DIRECTION4 section 2: "A signal known
at a bar's end enters at the open of the next hourly bar", with no time limit; a Friday D1 signal enters at the
Sunday reopening, an index signal of the session close at the next session's open).

Aggregates per rule (over the trades whose entry falls in [t0, t1)): daily sums by entry trading day (17:00 New York,
kit.costs.trading_day) of net R, R at costs x1.5 and gross R with the number of trades; and by calendar year of entry
(UTC, as kit.stats.by_year): n, sums of positive and negative net R and stress R (for PF), sums of R, R_stress, R_gross."""
import numpy as np
import pandas as pd

from kit import costs as C
from kit import sim

from . import grammar as G
from . import signals as SG

MAX_WAIT_H = None     # no limit: entry at the next hourly bar, as DIRECTION4 section 2 is written
EPOCH = pd.Timestamp("1970-01-01")


def day_number(entry_time):
    """Trading day (17:00 New York) of each entry as int days since 1970-01-01."""
    td = C.trading_day(pd.DatetimeIndex(entry_time))
    return ((td - EPOCH) // pd.Timedelta(days=1)).to_numpy().astype(np.int64)


def simulate_rules(market, book, tables, rule_list, rule_index):
    """Trades of the given rules on one market: {exit_h: trades DataFrame (column rule = global rule index)}."""
    out = {}
    by_exit = {}
    for r in rule_list:
        by_exit.setdefault(r["exit_h"], []).append(r)
    for hrs in sorted(by_exit):
        sig = SG.rule_signals(tables, by_exit[hrs], rule_index)
        if len(sig) == 0:
            continue
        sig["market"] = market
        tr = sim.simulate(sig, {market: book}, exit=("hours", hrs), stop=G.STOP, mode="one", max_wait_h=MAX_WAIT_H)
        out[hrs] = tr
    return out


def aggregate(trades_by_exit, t0=None, t1=None):
    """Per-rule aggregates of the trades entered in [t0, t1): dict of arrays
    daily: rule, day, R, Rs, Rg, n   years: rule, year, n, pos, neg, pos_s, neg_s, R, Rs, Rg."""
    cols = []
    for hrs in sorted(trades_by_exit):
        t = trades_by_exit[hrs]
        if len(t) == 0:
            continue
        et = pd.DatetimeIndex(t["entry_time"])
        keep = np.ones(len(t), bool)
        if t0 is not None:
            keep &= np.asarray(et >= pd.Timestamp(t0))
        if t1 is not None:
            keep &= np.asarray(et < pd.Timestamp(t1))
        if not keep.any():
            continue
        cols.append(pd.DataFrame({"rule": t["rule"].to_numpy(np.int64)[keep], "day": day_number(et[keep]),
                                  "year": np.asarray(et[keep].year, np.int64), "R": t["R"].to_numpy(float)[keep],
                                  "Rs": t["R_stress"].to_numpy(float)[keep], "Rg": t["R_gross"].to_numpy(float)[keep]}))
    if not cols:
        z = np.zeros(0)
        zi = np.zeros(0, np.int64)
        return {"d_rule": zi, "d_day": zi, "d_R": z, "d_Rs": z, "d_Rg": z, "d_n": zi,
                "y_rule": zi, "y_year": zi, "y_n": zi, "y_pos": z, "y_neg": z, "y_pos_s": z, "y_neg_s": z,
                "y_R": z, "y_Rs": z, "y_Rg": z}
    a = pd.concat(cols, ignore_index=True)
    a = a.sort_values(["rule", "day", "year", "R", "Rs", "Rg"], kind="mergesort").reset_index(drop=True)
    d = a.groupby(["rule", "day"], sort=True).agg(R=("R", "sum"), Rs=("Rs", "sum"), Rg=("Rg", "sum"),
                                                  n=("R", "size")).reset_index()
    a["pos"] = np.where(a.R > 0, a.R, 0.0)
    a["neg"] = np.where(a.R < 0, -a.R, 0.0)
    a["pos_s"] = np.where(a.Rs > 0, a.Rs, 0.0)
    a["neg_s"] = np.where(a.Rs < 0, -a.Rs, 0.0)
    y = a.groupby(["rule", "year"], sort=True).agg(n=("R", "size"), pos=("pos", "sum"), neg=("neg", "sum"),
                                                   pos_s=("pos_s", "sum"), neg_s=("neg_s", "sum"), R=("R", "sum"),
                                                   Rs=("Rs", "sum"), Rg=("Rg", "sum")).reset_index()
    return {"d_rule": d.rule.to_numpy(np.int64), "d_day": d.day.to_numpy(np.int64), "d_R": d.R.to_numpy(float),
            "d_Rs": d.Rs.to_numpy(float), "d_Rg": d.Rg.to_numpy(float), "d_n": d.n.to_numpy(np.int64),
            "y_rule": y.rule.to_numpy(np.int64), "y_year": y.year.to_numpy(np.int64), "y_n": y.n.to_numpy(np.int64),
            "y_pos": y.pos.to_numpy(float), "y_neg": y.neg.to_numpy(float), "y_pos_s": y.pos_s.to_numpy(float),
            "y_neg_s": y.neg_s.to_numpy(float), "y_R": y.R.to_numpy(float), "y_Rs": y.Rs.to_numpy(float),
            "y_Rg": y.Rg.to_numpy(float)}


def signal_counts(tables, rule_list, rule_index, bar_index=None):
    """Number of signals (after the filter) of each rule: (global indices, counts, enterable) where enterable counts
    the signals with a bar opening at or after their known_at (within MAX_WAIT_H when it is not None; bar times only,
    no price; -1 without bar_index)."""
    idx, cnt, ent = [], [], []
    bt = None if bar_index is None else pd.DatetimeIndex(bar_index).as_unit("ns").asi8
    for r in rule_list:
        t = tables.get((r["signal"], r["frame"]))
        n, e = 0, (0 if bt is not None else -1)
        if t is not None and len(t):
            m = SG.filter_mask(r["filter"], t["side"].to_numpy(), t["trend"].to_numpy(), t["adx"].to_numpy(),
                               t["hour_ny"].to_numpy())
            n = int(m.sum())
            if bt is not None and n:
                ka = pd.DatetimeIndex(t["known_at"]).as_unit("ns").asi8[m]
                k = np.searchsorted(bt, ka, side="left")
                ok = k < len(bt)
                wait = bt[np.clip(k, 0, len(bt) - 1)] - ka
                if MAX_WAIT_H is not None:
                    ok &= wait <= MAX_WAIT_H * sim.NS_H
                e = int(ok.sum())
        idx.append(rule_index[r["id"]])
        cnt.append(n)
        ent.append(e)
    return np.asarray(idx, np.int64), np.asarray(cnt, np.int64), np.asarray(ent, np.int64)


def sim_counts(trades_by_exit):
    """Skip counts of the kit (summed over the market's simulate calls)."""
    tot = {}
    for t in trades_by_exit.values():
        for _, c in t.attrs.get("counts", {}).items():
            for k, v in c.items():
                tot[k] = tot.get(k, 0) + int(v)
    return tot
