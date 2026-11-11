"""What would the validated rules do under the usual rules of a funded-account ("prop firm") evaluation?

The user's capital (1,000 EUR) forces a high risk per trade for the gains to matter. An evaluation account
lends a larger notional against a fee, with hard limits. Typical two-step rules (the best-known firm's, 2026):
  step 1: +10 % before the equity is 10 % under the initial balance or a day loses 5 % of it; no time limit;
  step 2: +5 % under the same limits; then a funded account with the same limits and 80 % of the profits.
This script replays the ten validated sleeves of round 2 (results/r2/recalc/trades, 2022-2025, FP Markets
Raw costs, one position per sleeve), every trade risking the same fixed fraction of the INITIAL balance,
from a new start every 5 trading days. Results are booked on the day of the exit (Prague calendar day);
the daily limit is therefore checked on realised results only (floating losses are ignored: slightly kind).
Nothing is fitted here. Output: results/prop_sim/summary.json
"""
import json
import os

import numpy as np
import pandas as pd

LAB = os.path.dirname(os.path.abspath(__file__))
TR = os.path.join(LAB, "results", "r2", "recalc", "trades")
SLEEVES = [("noise30", "us100"), ("ocm4", "us100"), ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"),
           ("nq_btc_follow", "btcusd"), ("F1_brk_ridge_filter", "btcusd"), ("F1_brk_ridge_filter", "ethusd"),
           ("GOLD_FRI_PM", "xauusd"), ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd")]


def daily_R(a="2022-01-01", b="2026-01-01"):
    fr = []
    for name, sym in SLEEVES:
        t = pd.read_parquet(os.path.join(TR, f"{name}__{sym}.parquet"))
        t = t[(t.entry_time >= pd.Timestamp(a, tz="UTC")) & (t.entry_time < pd.Timestamp(b, tz="UTC"))]
        fr.append(t[["exit_time", "R"]])
    t = pd.concat(fr)
    day = t.exit_time.dt.tz_convert("Europe/Prague").dt.normalize().dt.tz_localize(None)
    d = t.groupby(day).R.sum()
    idx = pd.bdate_range(d.index.min(), d.index.max())
    wk = d[~d.index.isin(idx)]                               # weekend exits (none expected: crypto is 24/5)
    d = d.reindex(idx).fillna(0.0)
    return d, int(len(t)), float(wk.sum())


def phase(r, i0, risk, target, max_loss=0.10, max_day=0.05, min_days=4):
    """Return (outcome, index of the last day) for a phase starting at day i0. outcome: 'pass' | 'fail' | 'open'."""
    eq, days = 0.0, 0
    for i in range(i0, len(r)):
        x = r[i] * risk
        if x != 0:
            days += 1
        eq += x
        if x <= -max_day or eq <= -max_loss:
            return "fail", i
        if eq >= target and days >= min_days:
            return "pass", i
    return "open", len(r) - 1


def main():
    d, n, wk = daily_R()
    r = d.to_numpy()
    out = {"days": int(len(r)), "trades": n, "mean_R_per_day": round(float(r.mean()), 3), "sd_R_per_day": round(float(r.std()), 2),
           "worst_day_R": round(float(r.min()), 2), "weekend_R_ignored": round(wk, 2), "by_risk": {}}
    starts = list(range(0, len(r) - 250, 5))
    for risk in (0.0025, 0.005, 0.0075, 0.01, 0.015):
        res = {"pass1": 0, "fail1": 0, "open1": 0, "pass2": 0, "fail2": 0, "open2": 0}
        t_all, funded_ok, funded_fail, pay = [], 0, 0, []
        for s in starts:
            o1, i1 = phase(r, s, risk, 0.10)
            res[o1 + "1"] += 1
            if o1 != "pass":
                continue
            o2, i2 = phase(r, i1 + 1, risk, 0.05)
            res[o2 + "2"] += 1
            if o2 != "pass":
                continue
            t_all.append(i2 - s + 1)
            seg = r[i2 + 1:i2 + 1 + 252] * risk               # the following 12 months on the funded account
            if len(seg) < 200:
                continue
            eq = np.cumsum(seg)
            breach = np.flatnonzero((seg <= -0.05) | (eq <= -0.10))
            if len(breach):
                funded_fail += 1
                pay.append(max(float(eq[:breach[0]].max(initial=0.0)), 0.0) * 0.0)     # breached: count nothing (conservative)
            else:
                funded_ok += 1
                pay.append(float(eq[-1]))
        ns = len(starts)
        out["by_risk"][f"{risk * 100:g}%"] = {
            "starts": ns, "step1_pass_pct": round(100 * res["pass1"] / ns, 1), "step1_fail_pct": round(100 * res["fail1"] / ns, 1),
            "both_steps_pass_pct": round(100 * res["pass2"] / ns, 1),
            "median_trading_days_to_pass": int(np.median(t_all)) if t_all else None,
            "p90_days_to_pass": int(np.percentile(t_all, 90)) if t_all else None,
            "funded_12m_cases": funded_ok + funded_fail, "funded_12m_breach_pct": round(100 * funded_fail / max(funded_ok + funded_fail, 1), 1),
            "funded_12m_median_gain_pct_of_balance": round(100 * float(np.median(pay)), 1) if pay else None,
            "avg_gain_per_day_pct": round(100 * float(r.mean()) * risk, 3)}
    os.makedirs(os.path.join(LAB, "results", "prop_sim"), exist_ok=True)
    json.dump(out, open(os.path.join(LAB, "results", "prop_sim", "summary.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
