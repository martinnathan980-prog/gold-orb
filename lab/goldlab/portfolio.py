"""Account-level simulation of a portfolio of strategies ("sleeves") on a small leveraged account.

Input: trades frames from sim.simulate (one per sleeve), each with entry_time, exit_time, side, entry,
risk (price distance to the initial stop, per unit), pnl (price units per unit, after costs), R.
Each sleeve carries its instrument spec (units per lot, min lot, lot step, quote->account FX rate).

`run_account` replays all trades in time order on ONE account:
  * size = risk_pct % of CURRENT equity / (stop distance x units per lot x fx), rounded DOWN to the lot
    step; below the minimum lot the trade is skipped (or taken at min lot if `force_min_lot`);
  * margin check with the account leverage (a trade is skipped if free margin is insufficient);
  * P&L is booked at the exit time; open risk is capped by `max_open_risk_pct`;
  * the account stops for good when equity <= start x (1 - kill_dd) (the user's -50 % rule).
`bootstrap` resamples whole weeks of the (R per sleeve) history to give distributions: median monthly
growth, probability of a +50 % month, probability of hitting the kill level within N months.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Spec:
    sym: str
    units_per_lot: float = 100.0     # e.g. gold 100 oz, index 1, BTC 1
    min_lot: float = 0.01
    lot_step: float = 0.01
    fx: float = 1.0                  # value in ACCOUNT currency of 1 quote-currency unit (USD->EUR ~ 0.87)
    leverage: float = 500.0


def _prep(sleeves):
    """sleeves: list of (name, trades, Spec). Returns one frame sorted by entry time."""
    fr = []
    for name, t, spec in sleeves:
        if t is None or len(t) == 0:
            continue
        d = pd.DataFrame({
            "sleeve": name, "sym": spec.sym,
            "t_in": t.entry_time.to_numpy(), "t_out": t.exit_time.to_numpy(),
            "entry": t.entry.to_numpy(float), "risk": t.risk.to_numpy(float), "pnl": t.pnl.to_numpy(float),
            "upl": spec.units_per_lot, "min_lot": spec.min_lot, "step": spec.lot_step, "fx": spec.fx,
            "lev": spec.leverage,
        })
        fr.append(d)
    if not fr:
        return pd.DataFrame()
    return pd.concat(fr).sort_values("t_in", kind="stable").reset_index(drop=True)


def run_account(sleeves, start=1000.0, risk_pct=1.0, kill_dd=0.5, max_open_risk_pct=None,
                force_min_lot=False, weights=None, frame=None, max_positions=None, max_per_sym=None, log=None):
    """Replay on one account. `weights`: optional {sleeve: multiplier of risk_pct}.
    `max_positions` / `max_per_sym`: caps on simultaneously open positions (the limits of the MT5 "hands").
    `log`: optional list that receives one dict per trade taken (sleeve, sym, times, lots, money result).
    Returns (equity_events DataFrame indexed by time, summary dict)."""
    d = _prep(sleeves) if frame is None else frame
    if len(d) == 0:
        return pd.DataFrame(), {"n": 0}
    t_in = d.t_in.to_numpy("datetime64[ns]").astype("int64")
    t_out = d.t_out.to_numpy("datetime64[ns]").astype("int64")
    order_out = np.argsort(t_out, kind="stable")
    eq = start
    open_pos = {}                      # i -> (lots, margin, risk_money)
    j = 0
    ev_t, ev_eq = [], []
    taken = skipped_small = skipped_margin = skipped_risk = skipped_cap = 0
    sym = d.sym.to_numpy()
    killed_at = None
    kill_level = start * (1 - kill_dd)
    w = weights or {}
    for i in range(len(d)):
        # book every exit that happened before this entry
        while j < len(order_out) and t_out[order_out[j]] <= t_in[i]:
            k = order_out[j]
            j += 1
            if k in open_pos:
                lots, _, _ = open_pos.pop(k)
                eq += d.pnl[k] * lots * d.upl[k] * d.fx[k]
                ev_t.append(t_out[k]); ev_eq.append(eq)
                if eq <= kill_level and killed_at is None:
                    killed_at = t_out[k]
        if killed_at is not None:
            break
        rp = risk_pct * w.get(d.sleeve[i], 1.0)
        if rp <= 0 or not np.isfinite(d.risk[i]) or d.risk[i] <= 0:
            continue
        risk_money_per_lot = d.risk[i] * d.upl[i] * d.fx[i]
        lots = np.floor(eq * rp / 100.0 / risk_money_per_lot / d.step[i] + 1e-9) * d.step[i]
        if lots < d.min_lot[i]:
            if not force_min_lot:
                skipped_small += 1
                continue
            lots = d.min_lot[i]
        risk_money = lots * risk_money_per_lot
        if (max_positions is not None and len(open_pos) >= max_positions) or \
                (max_per_sym is not None and sum(1 for q in open_pos if sym[q] == sym[i]) >= max_per_sym):
            skipped_cap += 1
            continue
        if max_open_risk_pct is not None:
            open_risk = sum(v[2] for v in open_pos.values())
            if (open_risk + risk_money) > eq * max_open_risk_pct / 100.0:
                skipped_risk += 1
                continue
        margin = lots * d.upl[i] * d.entry[i] * d.fx[i] / d.lev[i]
        used = sum(v[1] for v in open_pos.values())
        if used + margin > eq:
            skipped_margin += 1
            continue
        open_pos[i] = (lots, margin, risk_money)
        taken += 1
        if log is not None:
            log.append({"sleeve": d.sleeve[i], "sym": sym[i], "t_in": d.t_in[i], "t_out": d.t_out[i], "lots": float(lots),
                        "risk_money": float(risk_money), "money": float(d.pnl[i] * lots * d.upl[i] * d.fx[i])})
    if killed_at is None:
        while j < len(order_out):
            k = order_out[j]
            j += 1
            if k in open_pos:
                lots, _, _ = open_pos.pop(k)
                eq += d.pnl[k] * lots * d.upl[k] * d.fx[k]
                ev_t.append(t_out[k]); ev_eq.append(eq)
                if eq <= kill_level and killed_at is None:
                    killed_at = t_out[k]
                    break
    curve = pd.Series(ev_eq, index=pd.to_datetime(ev_t, utc=True), name="equity")
    summ = {"n": int(taken), "skipped_min_lot": int(skipped_small), "skipped_margin": int(skipped_margin),
            "skipped_risk_cap": int(skipped_risk), "skipped_position_cap": int(skipped_cap), "final": round(float(eq), 2),
            "killed_at": None if killed_at is None else str(pd.Timestamp(killed_at, tz="UTC"))}
    if len(curve):
        peak = np.maximum.accumulate(np.r_[start, curve.to_numpy()])
        summ["max_dd_pct"] = round(float((1 - np.r_[start, curve.to_numpy()] / peak).max() * 100), 1)
        m = curve.resample("ME").last().ffill()
        mret = m.pct_change()
        mret.iloc[0] = m.iloc[0] / start - 1
        summ["months"] = int(len(mret))
        summ["median_month_pct"] = round(float(mret.median() * 100), 1)
        summ["months_pos_pct"] = round(float((mret > 0).mean() * 100), 1)
        summ["months_ge_50pct"] = int((mret >= 0.5).sum())
        summ["worst_month_pct"] = round(float(mret.min() * 100), 1)
        yrs = max((curve.index[-1] - curve.index[0]).days / 365.25, 1e-9)
        summ["cagr_pct"] = round(float(((eq / start) ** (1 / yrs) - 1) * 100), 1) if eq > 0 else -100.0
        dly = curve.resample("D").last().ffill().pct_change().dropna()
        summ["days_pos_pct"] = round(float((dly > 0).mean() * 100), 1)
        summ["days_neg_pct"] = round(float((dly < 0).mean() * 100), 1)
    return curve, summ


def weekly_R_table(sleeves, weights=None):
    """Sum of R per ISO week and sleeve (weights applied) -> DataFrame weeks x sleeves (0 when no trade)."""
    cols = {}
    w = weights or {}
    for name, t, _ in sleeves:
        if t is None or len(t) == 0:
            continue
        wk = t.exit_time.dt.tz_convert(None).dt.to_period("W")
        cols[name] = (t.R * w.get(name, 1.0)).groupby(wk).sum()
    tab = pd.DataFrame(cols)
    if len(tab) == 0:
        return tab
    full = pd.period_range(tab.index.min(), tab.index.max(), freq="W")
    return tab.reindex(full).fillna(0.0)


def bootstrap(sleeves, risk_pct=1.0, months=3, n_boot=2000, kill_dd=0.5, block_weeks=4, seed=0, weights=None,
              period=None):
    """Block bootstrap of weekly portfolio R (blocks of `block_weeks` consecutive weeks, all sleeves kept
    together -> preserves cross-sleeve correlation and short-term clustering).
    Idealised sizing (no lot rounding): weekly return = risk_pct% x sum of R that week, compounded.
    Returns dict of distribution stats for a horizon of `months`."""
    tab = weekly_R_table(sleeves, weights)
    if period is not None:
        a, b = pd.Period(period[0], "W"), pd.Period(period[1], "W")
        tab = tab[(tab.index >= a) & (tab.index <= b)]
    r = tab.sum(axis=1).to_numpy()
    n = len(r)
    if n < 2 * block_weeks:
        return {"weeks": n}
    rng = np.random.default_rng(seed)
    h = int(round(months * 52 / 12))
    nb = int(np.ceil(h / block_weeks))
    kill = 1 - kill_dd
    finals, killed, best_m, any50 = [], 0, [], 0
    for _ in range(n_boot):
        starts = rng.integers(0, n - block_weeks + 1, nb)
        path = np.concatenate([r[s:s + block_weeks] for s in starts])[:h]
        eq = np.cumprod(np.maximum(1e-9, 1 + risk_pct / 100.0 * path))
        dead = np.where(eq <= kill)[0]
        if len(dead):
            killed += 1
            eq = eq[:dead[0] + 1]
        finals.append(eq[-1])
        # 4-week "months"
        mm = [eq[min(k + 3, len(eq) - 1)] / (eq[k - 1] if k > 0 else 1.0) - 1 for k in range(0, len(eq), 4)]
        best_m.append(max(mm))
        any50 += int(max(mm) >= 0.5)
    f = np.array(finals)
    per_month = f ** (1.0 / months) - 1
    return {"weeks": n, "horizon_months": months, "risk_pct": risk_pct,
            "median_total_pct": round(float((np.median(f) - 1) * 100), 1),
            "p10_total_pct": round(float((np.percentile(f, 10) - 1) * 100), 1),
            "p90_total_pct": round(float((np.percentile(f, 90) - 1) * 100), 1),
            "median_per_month_pct": round(float(np.median(per_month) * 100), 1),
            "p_kill_pct": round(killed / n_boot * 100, 1),
            "p_any_month_ge_50_pct": round(any50 / n_boot * 100, 1),
            "p_end_positive_pct": round(float((f > 1).mean() * 100), 1)}
