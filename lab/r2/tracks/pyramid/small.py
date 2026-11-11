"""Track `pyramid`: the scheme on a REAL small account (minimum lots, at most 6 positions, 2 per market).

r2/tracks/stake/account.py cannot carry add-ons (one stake rule for every row, no link between a position and its
parent), so this is the smallest loop that does, with the same mechanics and the same constants:
    lots rounded DOWN to the lot step; a position is skipped when even the minimum lot would risk more than its
    budget; at most 6 positions open, 2 per market; margin check with the instrument's leverage; robot stopped
    for good at -50 %; the account is kept at its size (gains withdrawn, no compounding): every budget is a %
    of the starting balance; results booked when a position closes; a result booked in the same minute as an
    entry is not known to it.
An add-on is ONE MORE POSITION on the same market: it counts in both caps. It exists only if its parent was
really taken and is still open.
    F1  budget of the add-on = f x (base stake in money)
    F2  only where the design opens an add-on (the stop has moved); budget = base stake in money minus what the
        positions of the group REALLY open (their real lots) would lose at the stop in force (never below zero)
Ties: rows are taken in the order of the frame (pyramid.portfolio_frame): entry time; at the same minute new
trades first (by rule name), then add-ons (by rule name, lower threshold first). So when a cap is reached at the
same minute, the new trade of a rule wins over an add-on.
`price_level="today"`: every row keeps its R but its prices and stop distance are rescaled to today's price level
(r2/fp_costs.json `spread_ref_price`), with the PARENT's factor for its add-ons (the geometry of the group is kept).
"""
import numpy as np
import pandas as pd

import pyramid as P
import account as A            # r2/tracks/stake/account.py (constants only: SPEC, USD_EUR)

S = P.S


def frame(fr, price_level="today"):
    d = fr.copy()
    if price_level == "today":
        f = np.array([A.SPEC[s]["spread_ref_price"] for s in d.sym]) / d.p_entry.to_numpy()
        for c in ("entry", "risk", "pnl", "stop", "p_entry", "p_risk"):
            d[c] = d[c] * f
    for c in ("units_per_lot", "min_lot", "lot_step", "leverage"):
        d[c] = [A.SPEC[s][c] for s in d.sym]
    return d


def account(d, cfg, start=1000.0, base_pct=1.0, kill_dd=0.5, max_positions=6, max_per_sym=2, trend=P.TREND):
    """`d` = frame(portfolio frame); cfg = a configuration of pyramid.CONFIGS, or pyramid.REFERENCE."""
    a = S.prepare(d)
    m_ideal = P.stakes(d, cfg, list(trend))
    t_in, t_out, order_out = a["t_in"], a["t_out"], a["order_out"]
    sym = d.sym.to_numpy()
    is_add = d.is_add.to_numpy() == 1
    pid = d.pid.to_numpy()
    side = d.side.to_numpy(float)
    pnl, risk, entry, stop = d.pnl.to_numpy(float), d.risk.to_numpy(float), d.entry.to_numpy(float), d["stop"].to_numpy(float)
    upl, minlot, step, lev = (d[c].to_numpy(float) for c in ("units_per_lot", "min_lot", "lot_step", "leverage"))
    n = len(d)
    stake_money = start * base_pct / 100.0
    eq = start
    kill_level = start * (1 - kill_dd)
    open_pos = {}                       # row -> (lots, margin)
    group = {}                          # pid -> rows of the group that are open
    killed_at = None
    lots_taken = np.zeros(n)
    money = np.zeros(n)
    skip = {"parent": {"min_lot": 0, "position_cap": 0, "margin": 0},
            "addon": {"parent_not_taken": 0, "no_budget": 0, "min_lot": 0, "position_cap": 0, "margin": 0}}
    j = 0

    def close(k):
        nonlocal eq, killed_at
        lots, _ = open_pos.pop(k)
        group[pid[k]].remove(k)
        money[k] = pnl[k] * lots * upl[k] * A.USD_EUR
        eq += money[k]
        if eq <= kill_level and killed_at is None:
            killed_at = t_out[k]

    for i in range(n):
        while j < n and t_out[order_out[j]] < t_in[i]:
            k = order_out[j]
            j += 1
            if k in open_pos:
                close(k)
        if killed_at is not None:
            break
        if m_ideal[i] <= 0.0:
            continue                                       # an add-on the configuration does not open
        kind = "addon" if is_add[i] else "parent"
        if is_add[i]:
            g = group.get(pid[i], [])
            if not any((not is_add[r]) for r in g):
                skip[kind]["parent_not_taken"] += 1
                continue
            if cfg["fam"] == "F1":
                budget = stake_money * cfg["f"]
            else:
                loss = sum(open_pos[r][0] * upl[r] * A.USD_EUR * side[r] * (entry[r] - stop[i]) for r in g)
                budget = stake_money - loss
            if budget <= 1e-9:
                skip[kind]["no_budget"] += 1
                continue
        else:
            budget = stake_money
        risk_money_per_lot = risk[i] * upl[i] * A.USD_EUR
        lots = np.floor(budget / risk_money_per_lot / step[i] + 1e-9) * step[i]
        if lots < minlot[i]:
            skip[kind]["min_lot"] += 1
            continue
        if len(open_pos) >= max_positions or sum(1 for r in open_pos if sym[r] == sym[i]) >= max_per_sym:
            skip[kind]["position_cap"] += 1
            continue
        margin = lots * upl[i] * entry[i] * A.USD_EUR / lev[i]
        if sum(v[1] for v in open_pos.values()) + margin > eq:
            skip[kind]["margin"] += 1
            continue
        open_pos[i] = (lots, margin)
        group.setdefault(pid[i], []).append(i)
        lots_taken[i] = lots
    if killed_at is None:
        while j < n:
            k = order_out[j]
            j += 1
            if k in open_pos:
                close(k)
                if killed_at is not None:
                    break
    took = lots_taken > 0
    o = order_out[took[order_out]]
    bal = start + np.cumsum(money[o])
    n_par, n_add = int((~is_add).sum()), int((is_add & (m_ideal > 0)).sum())
    out = {"start": start, "base_pct": base_pct, "parents": n_par, "parents_taken": int((took & ~is_add).sum()),
           "parents_taken_pct": round(float(100 * (took & ~is_add).sum() / n_par), 1),
           "addons_designed": n_add, "addons_taken": int((took & is_add).sum()),
           "addons_taken_pct": round(float(100 * (took & is_add).sum() / n_add), 1) if n_add else None,
           "skipped": skip, "final": round(float(eq), 2),
           "killed_at": None if killed_at is None else str(pd.Timestamp(killed_at, tz="UTC"))}
    if not took.any():
        return out
    peak = np.maximum.accumulate(np.r_[start, bal])

    def per(keys):
        u, inv = np.unique(keys, return_inverse=True)
        return np.bincount(inv, weights=money[o]) / start * 100.0

    days, weeks, months = per(a["dy_out"][o]), per(a["wk_out"][o]), per(a["mo_out"][o])
    yr = np.minimum(S.server_time(pd.to_datetime(d.t_out.to_numpy()[o], utc=True)).year.to_numpy(),
                    S.server_time(pd.to_datetime(d.t_in.to_numpy(), utc=True)).year.max())
    yrs = (t_out[o][-1] - t_out[o][0]) / 1e9 / 86400 / 365.25
    out.update({
        "total_pct": round(float((eq / start - 1) * 100), 1), "per_year_pct": round(float((eq / start - 1) * 100 / yrs), 1),
        "addons_total_pct": round(float(money[took & is_add].sum() / start * 100), 1),
        "by_year_pct": {int(y): round(float(money[o][yr == y].sum() / start * 100), 1) for y in np.unique(yr)},
        "max_dd_pct": round(float(((peak - np.r_[start, bal]) / start).max() * 100), 1),
        "worst_week_pct": round(float(weeks.min()), 1), "worst_day_pct": round(float(days.min()), 1),
        "win_days_pct": round(float(100 * (days > 0).mean()), 1), "win_weeks_pct": round(float(100 * (weeks > 0).mean()), 1),
        "win_months_pct": round(float(100 * (months > 0).mean()), 1),
        "avg_real_risk_parent_eur": round(float((lots_taken * risk * upl * A.USD_EUR)[took & ~is_add].mean()), 2),
        "avg_real_risk_addon_eur": round(float((lots_taken * risk * upl * A.USD_EUR)[took & is_add].mean()), 2) if (took & is_add).any() else None,
    })
    out["total_per_max_dd"] = round(float(out["total_pct"] / out["max_dd_pct"]), 2) if out["max_dd_pct"] > 0 else None
    return out


def readings(fr, starts=(1000.0, 5000.0, 12000.0), price_level="today"):
    """Reference and the 24 configurations on each account size; plus, per size, profit at equal drawdown against
    the reference ON THE SAME ACCOUNT."""
    d = frame(fr, price_level)
    out = {}
    for s in starts:
        ref = account(d, P.REFERENCE, s)
        r = {"reference": ref}
        for name, cfg in P.CONFIGS:
            x = account(d, cfg, s)
            if "total_pct" in x and "total_pct" in ref and x["max_dd_pct"] > 0:
                x["profit_at_equal_dd_vs_ref"] = round(float(x["total_pct"] / x["max_dd_pct"] / (ref["total_pct"] / ref["max_dd_pct"])), 3)
            r[name] = x
        out[f"{s:.0f}"] = r
    return out
