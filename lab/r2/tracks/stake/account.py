"""Track `stake` (Addendum E): the stake rules on a REAL small account. IN SAMPLE ONLY.

A variant of goldlab/portfolio.py::run_account (which is not edited) with a stake that depends on the state of the
week: same account mechanics (lots rounded DOWN to the lot step, a trade is skipped when even the minimum lot would
risk more than its budget, at most 6 positions and 2 per market, margin check with the instrument's leverage, robot
stopped for good at -50 %, compounding: the budget is a % of the current balance), plus:

    budget of a trade = base_pct % of the balance x m,   m = stake.multiplier(w, d, pw, family, open boosts)
    w  = (balance now - balance at the start of the server week) / (base_pct % of the balance at the start of the week)
    d  = (balance now - balance at the start of the server day)  / (same unit)
    pw = result of the previous server week in the same unit
    The balance moves only when a trade closes; a result booked in the same minute as an entry is not known to it.
    Same clock as stake.py (FP server time = New York + 7 h; week = Monday..Sunday; booking at the exit time).

`price_level="today"` keeps every trade's R but rescales its stop distance (and price) to today's price level
(r2/fp_costs.json `spread_ref_price`: gold 4080, us100 27000, bitcoin 76000, ether 2300), because the minimum lots
bite much harder at today's prices than at the 2018-2021 prices. It is the same in-sample trades, not new data.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stake as S  # noqa: E402

SPEC = {k: v for k, v in json.load(open(os.path.join(S.LAB, "r2", "fp_costs.json"))).items() if not k.startswith("_")}
USD_EUR = 0.89
LIMITS = dict(kill_dd=0.5, max_positions=6, max_per_sym=2)


def frame(kind="net", period="common", price_level="is", d=None):
    """In-sample trades with the instrument columns the account loop needs. A caller that holds another trades
    frame with the columns of stake.load_trades (sleeve, sym, fam, t_in, t_out, entry, risk, pnl, R; sorted by t_in)
    can pass it as `d` and give the result to `account(cfg, d=...)`."""
    d = (S.subset(kind, period) if d is None else d).copy()
    if price_level == "today":
        f = np.array([SPEC[s]["spread_ref_price"] for s in d.sym]) / d.entry.to_numpy()
        d["entry"], d["risk"], d["pnl"] = d.entry * f, d.risk * f, d.pnl * f
    for c in ("units_per_lot", "min_lot", "lot_step", "leverage"):
        d[c] = [SPEC[s][c] for s in d.sym]
    return d


def account(cfg, start=1000.0, base_pct=1.0, kind="net", period="common", price_level="is", kill_dd=0.5,
            max_positions=6, max_per_sym=2, d=None, compound=True):
    """`compound=False`: the account is kept at its starting size (gains withdrawn, losses refilled until the
    -50 % stop on the cumulated result): every budget is a % of `start`. It is the honest way to read the minimum
    lots for ONE account size, since a compounding in-sample account outgrows them within months."""
    d = frame(kind, period, price_level) if d is None else d
    a = S.prepare(d)
    p, famcap = S.params(cfg)
    t_in, t_out, order_out = a["t_in"], a["t_out"], a["order_out"]
    wk_in, wk_out, dy_in, dy_out, fam = a["wk_in"], a["wk_out"], a["dy_in"], a["dy_out"], a["fam"]
    sym = d.sym.to_numpy()
    pnl, risk, entry = d.pnl.to_numpy(float), d.risk.to_numpy(float), d.entry.to_numpy(float)
    upl, minlot, step, lev = (d[c].to_numpy(float) for c in ("units_per_lot", "min_lot", "lot_step", "leverage"))
    n = len(d)
    eq = start
    kill_level = start * (1 - kill_dd)
    open_pos = {}                       # i -> (lots, margin, boost)
    cur_wk, wk_bal, cur_dy, dy_bal, prev_res = -1, start, -1, start, {}
    killed_at = None
    lots_taken = np.zeros(n)
    mult = np.zeros(n)
    money = np.zeros(n)
    skip = {"rule_m0": 0, "min_lot": 0, "position_cap": 0, "margin": 0}
    j = 0

    def roll(week, day):
        nonlocal cur_wk, wk_bal, cur_dy, dy_bal
        if week != cur_wk:
            if cur_wk >= 0:
                prev_res[cur_wk] = (eq - wk_bal) / (base_pct / 100.0 * (wk_bal if compound else start))
            cur_wk, wk_bal = week, eq
        if day != cur_dy:
            cur_dy, dy_bal = day, eq

    for i in range(n):
        while j < n and t_out[order_out[j]] < t_in[i]:
            k = order_out[j]
            j += 1
            if k in open_pos:
                roll(wk_out[k], dy_out[k])
                lots, _, _ = open_pos.pop(k)
                money[k] = pnl[k] * lots * upl[k] * USD_EUR
                eq += money[k]
                if eq <= kill_level and killed_at is None:
                    killed_at = t_out[k]
        if killed_at is not None:
            break
        roll(wk_in[i], dy_in[i])
        unit = base_pct / 100.0 * (wk_bal if compound else start)
        w, dd_, pw = (eq - wk_bal) / unit, (eq - dy_bal) / unit, prev_res.get(wk_in[i] - 1, 0.0)
        open_boost = sum(v[2] for v in open_pos.values())
        m, b = S.multiplier(w, dd_, pw, fam[i], open_boost, p, famcap)
        if m <= 0.0:
            skip["rule_m0"] += 1
            continue
        risk_money_per_lot = risk[i] * upl[i] * USD_EUR
        lots = np.floor((eq if compound else start) * base_pct * m / 100.0 / risk_money_per_lot / step[i] + 1e-9) * step[i]
        if lots < minlot[i]:
            skip["min_lot"] += 1
            continue
        if len(open_pos) >= max_positions or sum(1 for q in open_pos if sym[q] == sym[i]) >= max_per_sym:
            skip["position_cap"] += 1
            continue
        margin = lots * upl[i] * entry[i] * USD_EUR / lev[i]
        if sum(v[1] for v in open_pos.values()) + margin > eq:
            skip["margin"] += 1
            continue
        open_pos[i] = (lots, margin, b)
        lots_taken[i], mult[i] = lots, m
    if killed_at is None:
        while j < n:
            k = order_out[j]
            j += 1
            if k in open_pos:
                lots, _, _ = open_pos.pop(k)
                money[k] = pnl[k] * lots * upl[k] * USD_EUR
                eq += money[k]
                if eq <= kill_level:
                    killed_at = t_out[k]
                    break
    took = lots_taken > 0
    o = order_out[took[order_out]]
    bal = start + np.cumsum(money[o])
    balb = np.r_[start, bal[:-1]]                       # balance before each close
    out = {"start": start, "base_pct": base_pct, "price_level": price_level, "kind": kind, "period": period,
           "n_signals": int(n), "n_taken": int(took.sum()), "taken_pct": round(float(100 * took.mean()), 1),
           "skipped": skip, "final": round(float(eq), 2),
           "killed_at": None if killed_at is None else str(pd.Timestamp(killed_at, tz="UTC"))}
    if took.sum() == 0:
        return out
    real_risk = lots_taken[took] * risk[took] * upl[took] * USD_EUR
    out["avg_real_risk_eur"] = round(float(real_risk.mean()), 2)

    def per(keys):
        """% result of each period = money of the period / balance at its first close."""
        u, first, inv = np.unique(keys, return_index=True, return_inverse=True)
        return np.bincount(inv, weights=money[o]) / (balb[first] if compound else start) * 100.0

    days, weeks, months = per(dy_out[o]), per(wk_out[o]), per(a["mo_out"][o])
    peak = np.maximum.accumulate(np.r_[start, bal])
    g, r = days[days > 0], days[days < 0]
    yrs = (t_out[o][-1] - t_out[o][0]) / 1e9 / 86400 / 365.25
    cal = np.zeros(a["nwk"])
    uw = np.unique(wk_out[o])
    cal[uw] = weeks
    out.update({
        "years": round(float(yrs), 2),
        "compound": compound,
        "per_year_pct": (round(float(((eq / start) ** (1 / yrs) - 1) * 100), 1) if eq > 0 else -100.0) if compound
        else round(float((eq / start - 1) * 100 / yrs), 1),
        "days": int(len(days)), "win_days_pct": round(float(100 * (days > 0).mean()), 1),
        "weeks": int(len(weeks)), "win_weeks_pct": round(float(100 * (weeks > 0).mean()), 1),
        "months": int(len(months)), "win_months_pct": round(float(100 * (months > 0).mean()), 1),
        "avg_green_day_pct": round(float(g.mean()), 2), "avg_red_day_pct": round(float(r.mean()), 2),
        "avg_green_week_pct": round(float(weeks[weeks > 0].mean()), 2), "avg_red_week_pct": round(float(weeks[weeks < 0].mean()), 2),
        "worst_day_pct": round(float(days.min()), 1), "worst_week_pct": round(float(weeks.min()), 1),
        "worst_month_pct": round(float(months.min()), 1),
        "max_dd_pct": round(float(((1 - np.r_[start, bal] / peak) if compound else (peak - np.r_[start, bal]) / start).max() * 100), 1),
        "longest_red_weeks": S._longest_red(cal[uw.min():uw.max() + 1]),
        "avg_mult_taken": round(float(mult[took].mean()), 2),
    })
    return out


def short(r):
    if "win_weeks_pct" not in r:
        return f"start {r['start']:.0f}: no trade"
    return (f"start {r['start']:6.0f} base {r['base_pct']:4.2f}% {r['price_level']:5s} | taken {r['taken_pct']:5.1f}% (min-lot skips {r['skipped']['min_lot']:4d},"
            f" cap {r['skipped']['position_cap']:3d}) | wk {r['win_weeks_pct']:5.1f} dy {r['win_days_pct']:5.1f} mo {r['win_months_pct']:5.1f}"
            f" | {r['per_year_pct']:+7.1f}%/y g/r day {r['avg_green_day_pct']:+5.2f}/{r['avg_red_day_pct']:+5.2f} wD {r['worst_day_pct']:5.1f}"
            f" wW {r['worst_week_pct']:5.1f} DD {r['max_dd_pct']:5.1f} red {r['longest_red_weeks']} {'KILLED ' + r['killed_at'][:10] if r['killed_at'] else ''}")
