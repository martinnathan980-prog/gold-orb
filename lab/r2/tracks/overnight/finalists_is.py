"""In-sample characterisation of the two finalists (final code) and the PRE-VALIDATION decision file.
Nothing here reads a validation-period trade: every trade frame is cut with cut(..., "is").
Usage: python3 finalists_is.py
"""
import datetime as dt
import json
import os

import numpy as np
import pandas as pd

from common import RES, S, gl, r2, trial, use, n_trials
from basket import basket_ev, bps, cluster_t, null_basket
from causality import check
from goldlab.split import cut

HALF = pd.Timestamp("2017-07-01", tz="UTC")
NEI = json.load(open(os.path.join(RES, "neighbors.json")))
KEEP = ("n", "trades_per_year", "win_rate", "avg_win_R", "avg_loss_R", "expectancy_R", "t_stat", "pf", "total_R", "max_dd_R",
        "years_pos", "weeks_pos_pct", "long_n", "long_R", "short_n", "short_R", "avg_hold_h", "max_hold_h", "by_year_R",
        "exit_reasons")


def slim(r):
    return {k: r[k] for k in KEEP if k in r}


def halves(sym, params):
    """Gross (zero-cost) and net result per trade, first vs second half of the in-sample period."""
    use(sym)
    m1 = r2.load(sym)
    out = {}
    for mode in ("gross", "fp"):
        t = cut(r2.run(sym, S.make_orders, params, mode, True, m1), "is")
        a, b = t[t.entry_time < HALF], t[t.entry_time >= HALF]
        out[mode] = {"first_half": {"n": len(a), "bp": bps(a), "R": round(float(a.R.mean()), 4)},
                     "second_half": {"n": len(b), "bp": bps(b), "R": round(float(b.R.mean()), 4)}}
    return out


def targeted_causality(sym, params, k=6, seed=3):
    """Cuts placed just after decisions and in the middle of trades (hardest cases)."""
    use(sym)
    m1 = r2.load(sym, end="2022-01-01")
    full = S.make_orders(m1, **params)
    rng = np.random.default_rng(seed)
    ok = True
    for j in rng.choice(np.arange(20, len(full)), k, replace=False):
        for off in (1, 45):
            cutp = int(full["entry_i"].iloc[j]) + off
            part = S.make_orders(m1.iloc[:cutp], **params)
            ref = full[full["entry_i"] < cutp].reset_index(drop=True)
            same = len(part) == len(ref) and bool((part["entry_i"].to_numpy() == ref["entry_i"].to_numpy()).all()) \
                and bool(np.allclose(part["stop_dist"].to_numpy(), ref["stop_dist"].to_numpy(), rtol=1e-12)) \
                and bool((part["side"].to_numpy() == ref["side"].to_numpy()).all())
            if "level" in part:
                same &= bool(np.allclose(part["level"].to_numpy(), ref["level"].to_numpy(), rtol=1e-12))
            ok &= same
    return bool(ok)


def sleeve_is(name, sym, mode, nei_pf):
    p = S.finalist_params(name, sym)
    ev = trial(sym, p, f"FINAL {name} {sym} (full, final code)", full=True, extra={"finalist": name, "final_rerun": True})
    crit = r2.is_criteria(ev, neighbor_median_pf=nei_pf)
    use(sym)
    nul = r2.null_test(sym, S.make_orders, p, mode=mode)
    ok_c, cuts = check(sym, p)
    ok_t = targeted_causality(sym, p)
    return {"sym": sym, "params": p, "is": slim(ev["is"]), "is_bps_per_trade": ev["is_bps_per_trade"],
            "is_stress": slim(ev["is_stress"]), "is_gross": slim(ev["is_gross"]),
            "is_gross_bps_per_trade": ev["is_gross_bps_per_trade"], "is_every_signal": slim(ev["is_every_signal"]),
            "neighbor_median_pf": nei_pf, "criteria": crit, "null": nul, "halves": halves(sym, p),
            "causality_random_cuts": ok_c, "causality_targeted_cuts": ok_t}


if __name__ == "__main__":
    out = {"written_utc": dt.datetime.utcnow().isoformat(timespec="seconds"), "track": "overnight",
           "statement": "Finalists chosen on in-sample data only (entries before 2022-01-01). No validation-period trade "
                        "of any configuration of this track had been simulated-and-looked-at when this file was written "
                        "(r2.evaluate / r2.null_test cut every trade frame to IS; results/val_access.log has no "
                        "'overnight' entry before this timestamp).",
           "finalists": {}}

    # ---------------- GOLD_FRI_PM
    g = sleeve_is("GOLD_FRI_PM", "xauusd", "time", NEI["gold"]["median_neighbor_pf"])
    out["finalists"]["GOLD_FRI_PM"] = {
        "syms": ["xauusd"], "judged_as": "single sleeve", "null_mode": "time",
        "rule": "Fridays only: buy-limit at the last bid before 13:30 New York, valid 60 min; stop 3 x ATR(14, 1h); exit 16:45 "
                "New York; no trade on early-close days. Round-1 definition (seasonality FRI_PM_LIM), untouched.",
        "sleeves": {"xauusd": g}, "is_pass": bool(g["criteria"]["pass"] and g["null"]["pass"]),
        "caveats": ["pre-declared re-check of a round-1 rule: its 2022-2025 gross drift was already seen in round 1 "
                    "(+3.4 bp per Friday, t 1.85) -> validation is NOT an independent test for this sleeve",
                    "edge concentrated in 2013-2016; 2017-2021 about flat (see halves / by_year_R)",
                    "about 45 trades a year, expectancy about +0.03 R: a very small contributor"]}

    # ---------------- MONTH_END_NIGHT (basket)
    sy = S.FINALISTS["MONTH_END_NIGHT"]["syms"]
    nb = NEI["month_end"]
    sl = {s: sleeve_is("MONTH_END_NIGHT", s, "time", nb["median_neighbor_pf_by_sleeve"][s]) for s in sy}
    sleeves = [(s, S.finalist_params("MONTH_END_NIGHT", s)) for s in sy]
    ev, pooled, per = basket_ev(sleeves)
    crit = r2.is_criteria(ev, neighbor_median_pf=nb["median_neighbor_pf"])
    nulb = null_basket(sleeves, n_seeds=200, sync=True)
    gq = pooled["gross"]
    fq = pooled["fp"]
    hb = {"gross": {"first_half": {"n": int((gq.entry_time < HALF).sum()), "bp": bps(gq[gq.entry_time < HALF])},
                    "second_half": {"n": int((gq.entry_time >= HALF).sum()), "bp": bps(gq[gq.entry_time >= HALF])}},
          "fp": {"first_half": {"n": int((fq.entry_time < HALF).sum()), "bp": bps(fq[fq.entry_time < HALF]),
                                "R": round(float(fq.R[fq.entry_time < HALF].mean()), 4)},
                 "second_half": {"n": int((fq.entry_time >= HALF).sum()), "bp": bps(fq[fq.entry_time >= HALF]),
                                 "R": round(float(fq.R[fq.entry_time >= HALF].mean()), 4)}}}
    # concentration: share of the total R made by the 5 best nights (all sleeves of a night summed)
    night = fq.groupby(fq.entry_time.dt.tz_convert("America/New_York").dt.floor("D"))["R"].sum().sort_values(ascending=False)
    conc = {"nights": int(len(night)), "total_R": round(float(night.sum()), 1), "top5_R": round(float(night.head(5).sum()), 1),
            "worst5_R": round(float(night.tail(5).sum()), 1), "nights_positive_pct": round(float((night > 0).mean() * 100), 1),
            "total_R_without_top5": round(float(night.iloc[5:].sum()), 1)}
    out["finalists"]["MONTH_END_NIGHT"] = {
        "syms": sy, "judged_as": "basket (same rule and settings, trades pooled; expectancy positive on each market)",
        "null_mode": "time (basket: one random moment per month-end, shared by the three sleeves)",
        "rule": "Last weekday of the month, 5 minutes before the cash close of the index's own exchange (15:55 New York for "
                "us500/us100, 17:25 Frankfurt for ger40): buy at market; stop 1 x ATR(14) of completed daily bars; exit at the "
                "next cash open (09:30 New York / 09:00 Frankfurt).",
        "sleeves": sl,
        "basket": {"is": slim(ev["is"]), "is_bps_per_trade": ev["is_bps_per_trade"], "is_stress": slim(ev["is_stress"]),
                   "is_gross": slim(ev["is_gross"]), "is_gross_bps_per_trade": ev["is_gross_bps_per_trade"],
                   "is_every_signal": slim(ev["is_every_signal"]), "cluster_t_by_night": ev["cluster_t"],
                   "n_nights": ev["n_clusters"], "neighbor_median_pf": nb["median_neighbor_pf"], "criteria": crit,
                   "null": nulb, "halves": hb, "concentration": conc},
        "is_pass": bool(crit["pass"] and nulb["pass"]),
        "caveats": ["only about 11 trades a year per index (33 a year for the basket); the three sleeves trade the same "
                    "nights and are highly correlated: about 99 independent observations (cluster t in 'basket')",
                    "the whole edge comes from 2017-2021; 2013-2016 is flat (see halves) -- not eroding, but not stable",
                    "selected after looking at about 40 turn-of-month cells in the descriptive phase (the classical "
                    "-1..+3 turn-of-month window shows nothing in-sample)",
                    "long index exposure through one night (often a weekend): crash risk; financing included; "
                    "dividend adjustments of the US cash-index CFDs are not modelled (they favour the long side)",
                    "us500 alone fails the random-entry null (95.5th percentile); the basket passes (synchronised null)"]}

    out["n_trial_log_lines_at_decision"] = n_trials()
    out["rejected_near_miss"] = {
        "BTC_LATE": "bitcoin long 17:05->19:00 New York every day, stop 2 x ATR(14,1h): gross t 3.67 / PF 1.32 but net of FP "
                    "costs PF 1.168, t 2.05 (< 2.5), random-entry null 96.5th percentile (< 97.5): fails; NOT validated "
                    "(its 2022-2025 data stays untouched for a later round, e.g. once the FP bitcoin cost is verified)"}
    r2.free()
    json.dump(out, open(os.path.join(RES, "finalists_preval.json"), "w"), indent=1, default=str)
    for nm, f in out["finalists"].items():
        print(f"=== {nm}: IS pass = {f['is_pass']}")
        for s, d in f["sleeves"].items():
            r = d["is"]
            print(f"  {s}: n={r['n']} PF={r['pf']} t={r['t_stat']} expR={r['expectancy_R']} yrs={r['years_pos']} bp={d['is_bps_per_trade']} "
                  f"gross_bp={d['is_gross_bps_per_trade']} stressPF={d['is_stress']['pf']} grossPF={d['is_gross']['pf']} "
                  f"everyR={d['is_every_signal']['expectancy_R']} neighPF={d['neighbor_median_pf']} null={d['null']['percentile']} "
                  f"crit={d['criteria']} halves={d['halves']} causal={d['causality_random_cuts']}/{d['causality_targeted_cuts']}")
        if "basket" in f:
            b = f["basket"]
            print("  BASKET:", {k: b["is"][k] for k in ("n", "pf", "t_stat", "expectancy_R", "years_pos", "max_dd_R", "win_rate")},
                  "cluster_t", b["cluster_t_by_night"], "stress", b["is_stress"]["pf"], "gross", b["is_gross"]["pf"],
                  "null", b["null"], "crit", b["criteria"], "halves", b["halves"], "conc", b["concentration"])
