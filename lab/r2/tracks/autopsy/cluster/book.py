"""Lens `cluster`: assembly of the ten sleeves' in-sample trades into one book, and the portfolio statistics.

Units: R = multiples of the base stake, no compounding. Period of judgement: entries in the common window
2018-02-01 .. 2021-12-31 (the engine itself runs over the whole in-sample history so that its state -- open
positions, paper records -- is warm on 2018-02-01). Days / weeks are FP server days / weeks of the EXIT time.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import engine as E  # noqa: E402

MKT_ID = {m: i for i, m in enumerate(C.MARKETS)}
SL_ID = {k: i for i, k in enumerate(C.SLEEVE_KEYS)}
CAPS = dict(cap_total=6, cap_mkt=2)


def build(mode="fp"):
    fr = []
    for name, sym in C.SLEEVES:
        t = C.read_my_trades(name, sym, mode)
        fr.append(pd.DataFrame({
            "sleeve": C.sleeve_key(name, sym), "name": name, "sym": sym,
            "t_in": pd.DatetimeIndex(t.entry_time).as_unit("ns"), "t_out": pd.DatetimeIndex(t.exit_time).as_unit("ns"),
            "side": t.side.to_numpy(np.int64), "R": t.R.to_numpy(float), "risk": t.risk.to_numpy(float),
            "entry": t.entry.to_numpy(float), "reason": t.reason.astype(str).to_numpy(),
            "hold_min": t.hold_min.to_numpy(float), "stop_spreads": t.stop_spreads.to_numpy(float),
            "mfe": t.mfe.to_numpy(float), "mae": t.mae.to_numpy(float)}))
    d = pd.concat(fr, ignore_index=True)
    d = d.sort_values(["t_in", "sleeve"], kind="stable").reset_index(drop=True)
    assert (d.t_in < C.IS_END).all() and (d.t_out > d.t_in).all()
    si, so = C.server_time(d.t_in), C.server_time(d.t_out)
    d["srv_in"], d["srv_out"] = si, so
    day0 = np.datetime64("1970-01-01")
    d["dy_in_abs"] = (si.values.astype("datetime64[D]") - day0).astype("int64")
    d["dy_out_abs"] = (so.values.astype("datetime64[D]") - day0).astype("int64")
    d["wk_in_abs"] = (d.dy_in_abs + 3) // 7
    d["wk_out_abs"] = (d.dy_out_abs + 3) // 7
    d["mo_out_abs"] = so.year * 12 + so.month - 1
    d["year"] = d.t_in.dt.year
    d["mk"] = d.sym.map(MKT_ID).astype("int64")
    d["fam"] = d.sym.map(C.FAMILY).astype("int64")
    d["sl"] = d.sleeve.map(SL_ID).astype("int64")
    d["ok_broker"] = d.stop_spreads >= 3.0
    return d


def arrays(d):
    dmin = int(min(d.dy_in_abs.min(), d.dy_out_abs.min()))
    wmin = int(min(d.wk_in_abs.min(), d.wk_out_abs.min()))
    a = dict(
        t_in=d.t_in.astype("int64").to_numpy(), t_out=d.t_out.astype("int64").to_numpy(), R=d.R.to_numpy(float).copy(),
        sl=d.sl.to_numpy(np.int64), mk=d.mk.to_numpy(np.int64), fam=d.fam.to_numpy(np.int64),
        side=d.side.to_numpy(np.int64),
        dy_in=(d.dy_in_abs - dmin).to_numpy(np.int64), dy_out=(d.dy_out_abs - dmin).to_numpy(np.int64),
        wk_in=(d.wk_in_abs - wmin).to_numpy(np.int64), wk_out=(d.wk_out_abs - wmin).to_numpy(np.int64),
        ok_broker=d.ok_broker.to_numpy(bool))
    a["order_out"] = np.argsort(a["t_out"], kind="stable")
    a["n_days"] = int(max(a["dy_in"].max(), a["dy_out"].max()) + 1)
    a["n_weeks"] = int(max(a["wk_in"].max(), a["wk_out"].max()) + 1)
    a["dmin"], a["wmin"] = dmin, wmin
    return a


def run(a, code=0, p1=0.0, p2=0.0, caps=True, R=None):
    ct, cm = (CAPS["cap_total"], CAPS["cap_mkt"]) if caps else (10**9, 10**9)
    return E.run_engine(a["t_in"], a["t_out"], a["R"] if R is None else R, a["sl"], a["mk"], a["fam"], a["side"],
                        a["dy_in"], a["dy_out"], a["wk_in"], a["wk_out"], a["ok_broker"], a["order_out"],
                        len(C.SLEEVE_KEYS), a["n_days"], a["n_weeks"], int(code), float(p1), float(p2), ct, cm)


def _longest_neg_run(x):
    best = cur = 0
    for v in x:
        cur = cur + 1 if v < 0 else 0
        best = max(best, cur)
    return int(best)


def stats(d, m, sel=None, R=None):
    """Portfolio statistics of stakes m on the trades of d selected by `sel` (default: common window)."""
    R = d.R.to_numpy(float) if R is None else R
    if sel is None:
        sel = (d.t_in >= C.COMMON_START).to_numpy()
    took = sel & (m > 0)
    r = m * R
    n = int(took.sum())
    stakes = float(m[took].sum())
    total = float(r[took].sum())
    los = took & (R < 0)
    win = took & (R > 0)
    out = {"n_offered": int(sel.sum()), "n_taken": n, "stakes": round(stakes, 3), "total_R": round(total, 3),
           "exp_per_stake": round(total / stakes, 5) if stakes > 0 else None,
           "exp_per_trade_taken": round(total / n, 5) if n else None,
           "avg_loss_per_stake": round(float(-r[los].sum() / m[los].sum()), 5) if los.any() else None,
           "avg_loss_per_losing_trade": round(float(-r[los].mean()), 5) if los.any() else None,
           "win_rate": round(float(win.sum() / n), 4) if n else None,
           "pf": round(float(r[win].sum() / -r[los].sum()), 4) if los.any() else None}
    # days / weeks of the exit time (server clock)
    dy = d.dy_out_abs.to_numpy()[took]
    wk = d.wk_out_abs.to_numpy()[took]
    rr = r[took]
    days = pd.Series(rr).groupby(dy).sum()
    weeks_traded = pd.Series(rr).groupby(wk).sum()
    allw = np.arange(weeks_traded.index.min(), weeks_traded.index.max() + 1)
    weeks = weeks_traded.reindex(allw, fill_value=0.0)
    order = np.argsort(d.t_out.astype("int64").to_numpy()[took], kind="stable")
    cum = np.cumsum(rr[order])
    dd = float((np.maximum.accumulate(np.r_[0.0, cum]) - np.r_[0.0, cum]).max())
    out.update({"days": int(len(days)), "win_days_pct": round(float(100 * (days > 0).mean()), 2),
                "weeks": int(len(weeks)), "win_weeks_pct": round(float(100 * (weeks_traded > 0).mean()), 2),
                "worst_day": round(float(days.min()), 3), "worst_week": round(float(weeks.min()), 3),
                "max_dd": round(dd, 3), "longest_losing_days": _longest_neg_run(days.to_numpy()),
                "longest_losing_weeks": _longest_neg_run(weeks.to_numpy())})
    yrs = d.year.to_numpy()[took]
    by = {}
    for y in sorted(set(d.year.to_numpy()[sel])):
        k = yrs == y
        mm = m[took][k]
        rk = rr[k]
        lk = R[took][k] < 0
        by[int(y)] = {"n": int(k.sum()), "stakes": round(float(mm.sum()), 3), "total_R": round(float(rk.sum()), 3),
                      "exp_per_stake": round(float(rk.sum() / mm.sum()), 5) if mm.sum() > 0 else None,
                      "avg_loss_per_stake": round(float(-rk[lk].sum() / mm[lk].sum()), 5) if lk.any() else None}
    out["by_year"] = by
    return out


def per_sleeve(d, m, m_ref, sel=None):
    """What the guard changes, sleeve by sleeve (unit-stake R of the trades it removes or shrinks)."""
    if sel is None:
        sel = (d.t_in >= C.COMMON_START).to_numpy()
    R = d.R.to_numpy(float)
    out = {}
    for s in C.SLEEVE_KEYS:
        k = sel & (d.sleeve.to_numpy() == s)
        removed = k & (m_ref > 0) & (m <= 0)
        added = k & (m_ref <= 0) & (m > 0)
        out[s] = {"n_ref": int((k & (m_ref > 0)).sum()), "n_taken": int((k & (m > 0)).sum()),
                  "R_ref": round(float((m_ref * R)[k].sum()), 3), "R_variant": round(float((m * R)[k].sum()), 3),
                  "n_removed": int(removed.sum()), "R_of_removed": round(float(R[removed].sum()), 3),
                  "n_added": int(added.sum()), "R_of_added": round(float(R[added].sum()), 3)}
    return out
