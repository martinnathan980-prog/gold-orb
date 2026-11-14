"""Verdict of night_fade (PROTOCOL_V3 Addendum L) on the MAIN configuration, in sample only (L26, L30).

Collects run.json, null.json, correlation.json, precheck.json and the hand checks into results.json; nothing is simulated
here. The verdict is read on the main only: pass = all twelve bars. Everything else is 'reported, not judged':
the main's entries by hour, weekday and daylight-saving regime, first against later trades of the evening, drops by filter,
evenings skipped by reason and cross, the minutes 16:55-17:30, stop and target in one bar, x1.5 fills past the target,
expectancy by D / C, the AUD and NZD crosses against the other six, winning days / weeks / months, worst evening and week,
maximum drawdown, crosses open at once and currency stacking, the account check at 7 % of 1,000 EUR (0.01 lot, 1:500),
the break-even extra cost, the named tail evenings, and the comparison with what Addendum L said before the run.

    python3 -I verdict.py
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from goldlab.data import trading_day  # noqa: E402

EUR_CROSS = {"CAD": "eurcad", "AUD": "euraud", "GBP": "eurgbp", "CHF": "eurchf", "NZD": "eurnzd"}
ACCOUNT_EUR, RISK_PCT, MIN_LOT, LOT_STEP, LEVERAGE, UNITS = 1000.0, 7.0, 0.01, 0.01, 500.0, 100_000


def J(out, name):
    p = os.path.join(out, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


NEIGHBOURS = ("first_hour", "moving_mid", "width_2.5", "m15", "stop_3.0", "one_per_night")


def num(x):
    """A stored figure as a float ('inf' / '-inf' strings -> infinities, None -> NaN, which fails every bar)."""
    if x == "inf":
        return float("inf")
    if x == "-inf":
        return float("-inf")
    return float("nan") if x is None else float(x)


def criteria(run, nul, cor, n_kept):
    """The twelve bars of Addendum L on the main (L26). Every bar is read on the UNROUNDED figure ('<name>_raw' in
    run.json, 'percentile_raw' in null.json, 'corr_with_sum_of_ten_raw' in correlation.json; review R6-2): the rounded
    figures are shown next to them for display only. A missing raw figure raises (never a silent fall-back)."""
    cf = {c["name"]: c for c in run["configs"]}
    m = cf["main"]["results"]["pooled"]
    b, sa, sb, ev = m["base"], m["stress_a"], m["stress_b"], m["every"]
    nb = {k: cf[k]["results"]["pooled"]["base"]["pf"] for k in NEIGHBOURS}
    nb_raw = {k: cf[k]["results"]["pooled"]["base"]["pf_raw"] for k in NEIGHBOURS}
    med = float(np.median([num(v) for v in nb_raw.values()]))
    need_pos = (65 * n_kept + 99) // 100                      # 65 % rounded up: 8 of 12 (L26)
    share, total = num(b.get("max_cross_share_raw")), num(b["total_R_raw"])
    rho = num(cor["main"]["corr_with_sum_of_ten_raw"]) if cor else float("nan")
    pct = num(nul["percentile_raw"]) if nul else float("nan")
    crit = {
        "n>=250": {"value": b["n"], "pass": b["n"] >= 250},
        "pf>=1.12": {"value": b["pf"], "value_raw": b["pf_raw"], "pass": num(b["pf_raw"]) >= 1.12},
        "t_daily>=2.5": {"value": b.get("t_daily"), "value_raw": b["t_daily_raw"], "pass": num(b["t_daily_raw"]) >= 2.5},
        "years_pos>=6/9": {"value": f"{b.get('years_pos', 0)}/9", "pass": b.get("years_pos", 0) >= 6},
        "stress_pf>=1.04_both_readings": {"value": {"a_rebuilt": sa["pf"], "b_same_orders": sb["pf"]},
                                          "value_raw": {"a_rebuilt": sa["pf_raw"], "b_same_orders": sb["pf_raw"]},
                                          "pass": num(sa["pf_raw"]) >= 1.04 and num(sb["pf_raw"]) >= 1.04},
        "crosses_positive": {"value": f"{b.get('crosses_positive', 0)}/{n_kept}", "threshold": need_pos,
                             "pass": b.get("crosses_positive", 0) >= need_pos},
        "max_cross_share<=25%": {"value": b.get("max_cross_share"), "value_raw": b.get("max_cross_share_raw"),
                                 "total_R_raw": b["total_R_raw"], "pass": total > 0 and share <= 0.25},
        "neighbours_median_pf>=1.06": {"value": round(med, 4), "value_raw": med, "neighbours": nb,
                                       "neighbours_raw": nb_raw, "pass": med >= 1.06},
        "every_signal_exp>0": {"value": ev.get("expectancy_R"), "value_raw": ev["expectancy_R_raw"], "n": ev["n"],
                               "pass": num(ev["expectancy_R_raw"]) > 0},
        "max_hold<=5_trading_days": {"value_h": b.get("max_hold_h"), "value_h_raw": b["max_hold_h_raw"],
                                     "pass": b["n"] > 0 and num(b["max_hold_h_raw"]) <= 192},
        "null>=97.5pct": {"value": nul["percentile"] if nul else None, "value_raw": pct, "pass": pct >= 97.5},
        "abs_weekly_corr_with_ten<=0.30": {"value": cor["main"]["corr_with_sum_of_ten"] if cor else None,
                                           "value_raw": rho, "pass": abs(rho) <= 0.30},
    }
    assert len(crit) == 12
    return crit, all(v["pass"] for v in crit.values())


def sweep_max(starts, ends):
    """Maximum number of intervals [start, end) open at once (an exit at t frees its slot before an entry at t)."""
    if len(starts) == 0:
        return 0, {}
    ev = np.r_[np.asarray(ends, np.int64), np.asarray(starts, np.int64)]
    kind = np.r_[np.zeros(len(ends), np.int64), np.ones(len(starts), np.int64)]   # exits (0) sort before entries (1)
    order = np.lexsort((kind, ev))
    step = np.where(kind[order] == 1, 1, -1)
    level = np.cumsum(step)
    at_entry = level[kind[order] == 1]
    return int(level.max()), {int(k): int(v) for k, v in pd.Series(at_entry).value_counts().sort_index().items()}


def ny(ts):
    return pd.DatetimeIndex(ts).tz_convert(C.NY)


def rate_asof(load, cross, times):
    """Mid close of the last M1 bar of `cross` at or before each UTC time (in-sample frame)."""
    m = load(cross)
    ns = m.index.as_unit("ns").asi8
    i = np.searchsorted(ns, pd.DatetimeIndex(times).as_unit("ns").asi8, side="right") - 1
    mid = ((m.bc + m.ac) / 2).to_numpy()
    return mid[np.maximum(i, 0)]


def account_check(t, load):
    """7 % of 1,000 EUR per trade at the stop: lots against the 0.01 minimum and step, margin at 1:500 (reported)."""
    if len(t) == 0:
        return {"n": 0}
    rates = {q: rate_asof(load, EUR_CROSS[q], t.entry_time) for q in EUR_CROSS}
    eur_per_quote = np.array([1.0 / rates[C.QUOTE[c]][i] for i, c in enumerate(t.cross)])
    eur_per_base = np.array([1.0 if C.BASE[c] == "EUR" else 1.0 / rates[C.BASE[c]][i] for i, c in enumerate(t.cross)])
    risk_eur_per_lot = t.risk.to_numpy() * UNITS * eur_per_quote
    budget = ACCOUNT_EUR * RISK_PCT / 100
    lots_exact = budget / risk_eur_per_lot
    lots = np.floor(lots_exact / LOT_STEP + 1e-9) * LOT_STEP
    below = lots < MIN_LOT
    risk_at_min = MIN_LOT * risk_eur_per_lot / ACCOUNT_EUR * 100
    margin = np.maximum(lots, MIN_LOT) * UNITS * eur_per_base / LEVERAGE
    s_ns = pd.DatetimeIndex(t.entry_time).as_unit("ns").asi8
    e_ns = pd.DatetimeIndex(t.exit_time).as_unit("ns").asi8
    times = np.r_[e_ns, s_ns]
    kinds = np.r_[np.zeros(len(e_ns), np.int64), np.ones(len(s_ns), np.int64)]   # exits free margin before entries
    delta = np.r_[-margin, margin]
    peak_margin = float(np.max(np.cumsum(delta[np.lexsort((kinds, times))])))
    daily = t.R.groupby(trading_day(t.entry_time).to_numpy()).sum()
    return {"account_eur": ACCOUNT_EUR, "risk_pct": RISK_PCT, "leverage": LEVERAGE, "min_lot": MIN_LOT,
            "lots_median": round(float(np.median(lots_exact)), 4), "lots_p10": round(float(np.percentile(lots_exact, 10)), 4),
            "lots_p90": round(float(np.percentile(lots_exact, 90)), 4),
            "trades_below_min_lot": int(below.sum()), "share_below_min_lot": round(float(below.mean()), 4),
            "risk_pct_at_min_lot_median_when_below": round(float(np.median(risk_at_min[below])), 3) if below.any() else None,
            "margin_eur_per_trade_median": round(float(np.median(margin)), 2),
            "peak_margin_eur_all_open_trades": round(peak_margin, 2),
            "worst_evening_eur_at_7pct_per_R": round(float(daily.min()) * budget, 2),
            "eur_rates": "mid close of the EUR cross's last M1 bar at or before the entry (in-sample frames)"}


def reported_main(out, run, load, kept):
    """Main-only figures (reported, not judged)."""
    tb = pd.read_parquet(os.path.join(out, "trades_01_main_base.parquet"))
    tbx = pd.read_parquet(os.path.join(out, "trades_01_main_stress_b.parquet"))
    tax = pd.read_parquet(os.path.join(out, "trades_01_main_stress_a.parquet"))
    tg = pd.read_parquet(os.path.join(out, "trades_01_main_gross.parquet"))
    t = tb.sort_values(["entry_time", "cross"], kind="stable").reset_index(drop=True)
    rep = {}
    if len(t) == 0:
        return {"n": 0}
    R = t.R
    grp = lambda key: {str(k): {"n": int(len(g)), "expectancy_R": round(float(g.R.mean()), 5),  # noqa: E731
                                "total_R": round(float(g.R.sum()), 3), "pf": round(C.pf(g.R), 4) if C.pf(g.R) != float("inf") else "inf",
                                "win_rate": round(float((g.R > 0).mean()), 4)} for k, g in t.groupby(key)}
    e_ny = ny(t.entry_time)
    t["ny_hour"] = e_ny.hour
    t["weekday_of_evening"] = pd.DatetimeIndex(t.evening).day_name()
    t["dst"] = np.where(t.ny_summer_time.astype(bool), "summer time (EDT)", "winter time (EST)")
    rep["by_entry_ny_hour"] = grp("ny_hour")
    rep["by_weekday_of_evening"] = grp("weekday_of_evening")
    rep["by_dst_regime"] = grp("dst")
    t["rank_in_evening"] = t.groupby(["cross", "evening"]).cumcount()
    t["first_or_later"] = np.where(t.rank_in_evening == 0, "first trade of the cross and evening", "later trade")
    rep["first_vs_later"] = grp("first_or_later")
    cf = {c["name"]: c for c in run["configs"]}
    rep["drops_by_filter"] = cf["main"]["results"]["pooled"]["extras"]["status_counts"]
    rep["drops_by_filter_stress_a"] = cf["main"]["results"]["pooled"]["extras"]["status_counts_stress_a"]
    rep["skipped_by_one_position"] = cf["main"]["results"]["pooled"]["extras"]["skipped_by_one_position"]
    rep["evenings_by_cross"] = run["evenings"]
    mod_e = e_ny.hour * 60 + e_ny.minute
    xb = pd.DatetimeIndex(t.exit_time) - pd.to_timedelta(np.where(t.reason == "time", 0, 1), unit="min")
    x_ny = ny(xb)
    mod_x = x_ny.hour * 60 + x_ny.minute
    win = lambda mm: (mm >= 16 * 60 + 55) & (mm < 17 * 60 + 30)  # noqa: E731
    sub = lambda mask: {"n": int(mask.sum()), "total_R": round(float(R[mask].sum()), 3),  # noqa: E731
                        "expectancy_R": round(float(R[mask].mean()), 5) if mask.any() else None}
    rep["minutes_16_55_17_30"] = {"entries": sub(np.asarray(win(mod_e))),
                                  "stop_exits": sub(np.asarray(win(mod_x)) & (t.reason == "stop").to_numpy()),
                                  "target_exits": sub(np.asarray(win(mod_x)) & (t.reason == "target").to_numpy())}
    rep["stop_and_target_in_one_m1_bar"] = {"n": int(t.same_bar_stop_and_target.astype(bool).sum()),
                                            "share": round(float(t.same_bar_stop_and_target.astype(bool).mean()), 5)}
    rep["x1.5_fills_already_past_target"] = {"stress_b_same_orders": int(tbx.fill_past_target.astype(bool).sum()),
                                             "stress_a_rebuilt": int(tax.fill_past_target.astype(bool).sum())}
    dc = t.D / t.C
    t["dc_bucket"] = np.where(dc < 3, "2-3", np.where(dc < 4, "3-4", ">=4"))
    rep["expectancy_by_D_over_C"] = grp("dc_bucket")
    t["group"] = np.where(t.cross.isin(C.AUD_NZD), "AUD and NZD crosses", "other six")
    rep["aud_nzd_vs_other_six"] = grp("group")
    daily = t.R.groupby(trading_day(t.exit_time - pd.Timedelta(nanoseconds=1)).to_numpy()).sum()
    wk = t.R.groupby(t.exit_time.dt.tz_convert(None).dt.to_period("W").to_numpy()).sum()
    all_wk = pd.period_range(pd.Timestamp("2013-01-01").to_period("W"), pd.Timestamp("2021-12-31").to_period("W"), freq="W")
    wk_all = wk.reindex(all_wk, fill_value=0.0)
    mo = t.R.groupby(t.exit_time.dt.tz_convert(None).dt.to_period("M").to_numpy()).sum()
    cum = np.cumsum(t.sort_values("exit_time", kind="stable").R.to_numpy())
    peak = np.maximum.accumulate(np.r_[0.0, cum])
    rep["winning_days_weeks_months"] = {
        "days_with_a_trade": int(len(daily)), "winning_days_share": round(float((daily > 0).mean()), 4),
        "weeks_with_a_trade": int(len(wk)), "winning_weeks_share_of_weeks_with_a_trade": round(float((wk > 0).mean()), 4),
        "winning_weeks_share_of_all_weeks_2013_2021": round(float((wk_all > 0).mean()), 4),
        "months_with_a_trade": int(len(mo)), "winning_months_share": round(float((mo > 0).mean()), 4)}
    rep["worst_evening"] = {"trading_day": str(daily.idxmin())[:10], "R": round(float(daily.min()), 3)}
    rep["worst_week"] = {"week": str(wk.idxmin()), "R": round(float(wk.min()), 3)}
    rep["max_drawdown_R_by_exit_time"] = round(float((peak - np.r_[0.0, cum]).max()), 3)
    s_ns = pd.DatetimeIndex(t.entry_time).as_unit("ns").asi8
    e_ns = pd.DatetimeIndex(t.exit_time).as_unit("ns").asi8
    mx, dist = sweep_max(s_ns, e_ns)
    rep["crosses_open_at_once"] = {"max": mx, "distribution_at_entry": dist}
    stack = {}
    for ccy in sorted(set(C.BASE.values()) | set(C.QUOTE.values())):
        for direction, sgn in (("long", 1), ("short", -1)):
            m = np.array([(C.BASE[c] == ccy and s * sgn > 0) or (C.QUOTE[c] == ccy and s * sgn < 0)
                          for c, s in zip(t.cross, t.side)])
            stack[f"{ccy} {direction}"] = sweep_max(s_ns[m], e_ns[m])[0] if m.any() else 0
    rep["most_open_trades_on_one_currency_and_side"] = {"max": max(stack.values()) if stack else 0, "by_currency_side": stack}
    rep["account_check"] = account_check(t, load)
    inv = (t.entry / t.risk).to_numpy()
    x = float(t.R.sum() / inv.sum())
    cost_bp = cf["main"]["results"]["pooled"]["base"].get("bp_cost_per_trade")
    rep["break_even_extra_cost_per_round_trip"] = {
        "bp_of_price": round(x * 1e4, 4),
        "multiple_of_modelled_cost": round(x * 1e4 / cost_bp, 3) if cost_bp not in (None, 0) else None,
        "modelled_cost_bp_per_trade": cost_bp,
        "how": "the same trades and exit levels; an extra cost x (fraction of price) per round trip lowers each R by "
               "x x entry / risk; x = sum R / sum(entry / risk)"}
    named = {}
    for d in ("2016-10-06", "2019-01-02"):
        s = t[pd.DatetimeIndex(t.evening) == pd.Timestamp(d)]
        named[f"evening {d}"] = {"n": int(len(s)), "total_R": round(float(s.R.sum()), 3),
                                 "trades": [{"cross": r.cross, "side": int(r.side), "entry_ny": str(ny([r.entry_time])[0])[:16],
                                             "reason": r.reason, "R": round(float(r.R), 4)} for r in s.itertuples()]}
    wkm = (pd.DatetimeIndex(t.evening) >= pd.Timestamp("2021-11-22")) & (pd.DatetimeIndex(t.evening) <= pd.Timestamp("2021-11-26"))
    s = t[wkm]
    named["week of 2021-11-22"] = {"n": int(len(s)), "total_R": round(float(s.R.sum()), 3),
                                   "by_cross": {c: round(float(g.R.sum()), 3) for c, g in s.groupby("cross")}}
    s = t[(t.cross == "eurchf") & (t.entry_time < pd.Timestamp("2015-01-15", tz="UTC"))]
    named["eurchf before 2015-01-15"] = {"n": int(len(s)), "total_R": round(float(s.R.sum()), 3),
                                         "expectancy_R": round(float(s.R.mean()), 5) if len(s) else None}
    rep["named_evenings_kept_in_the_test"] = named
    rep["gross_reading"] = {"n": int(len(tg)), "pf": round(C.pf(tg.R), 4) if len(tg) else 0.0,
                            "bp_per_trade": round(float((tg.pnl / tg.entry).mean() * 1e4), 4) if len(tg) else None}
    return rep


def priors(run):
    m = {c["name"]: c for c in run["configs"]}["main"]["results"]["pooled"]
    b = m["base"]
    return {"said_before_the_run": ("a few thousand to about 15,000 trades, 60-75 % winners, a gross PF above 1 and, if it "
                                    "fails, failing on PF, costs x 1.5 and years; the null can pass even then; |rho| with the "
                                    "ten below 0.1; PF 1.12 needs a net mean of about 5.7 % of the mean |R|; 683917: 70.5 % "
                                    "winners, average win / average loss 0.75; prior of an in-sample pass about 8 %"),
            "measured": {"n": b["n"], "win_rate": b.get("win_rate"), "win_loss_ratio": b.get("win_loss_ratio"),
                         "pf": b.get("pf"), "gross_pf": m["gross"].get("pf"), "stress_a_pf": m["stress_a"].get("pf"),
                         "stress_b_pf": m["stress_b"].get("pf"), "years_pos": b.get("years_pos"),
                         "net_mean_over_mean_abs_R": None}}


def verdict_all(out, load, decl, sha):
    run, nul, cor, pre = J(out, "run.json"), J(out, "null.json"), J(out, "correlation.json"), J(out, "precheck.json")
    hce, hcx = J(out, "handcheck_entry.json"), J(out, "handcheck_exit.json")
    for x in (run, nul, cor):
        assert x is not None and x.get("declared_sha256") == sha, "an input is missing or was not made under this declaration"
    kept = decl["crosses_kept"]
    tri = os.path.join(out, "trials.jsonl")
    assert C.sha256(tri) == run["trials_sha256"], "trials.jsonl is not the file the run wrote (run.json's sha256)"
    trials = [json.loads(x) for x in open(tri)]
    assert len(trials) == 7 * (len(kept) + 1) == run["trials_logged"]
    crit, main_pass = criteria(run, nul, cor, len(kept))
    tb = pd.read_parquet(os.path.join(out, "trades_01_main_base.parquet"))
    pr = priors(run)
    if len(tb):
        pr["measured"]["net_mean_over_mean_abs_R"] = round(float(tb.R.mean() / tb.R.abs().mean()), 4)
    res = {"what": "night_fade (PROTOCOL_V3 Addendum L, round 6): verdict on the main configuration, in sample 2013-2021",
           "declared_sha256": sha, "declared_utc": decl.get("_written_utc"), "crosses_kept": kept,
           "main_pass": bool(main_pass),
           "verdict_text": ("PASS in sample: next step is the independent re-implementation attack" if main_pass else
                            "FAIL in sample: final; nothing is attacked, nothing is kept, no look at 2022-2025 is declared"),
           "criteria": crit,
           "configurations_pooled": {c["name"]: c["results"]["pooled"] for c in run["configs"]},
           "reported_main": reported_main(out, run, load, kept), "priors": pr,
           "null": nul, "correlation": cor["main"] if cor else None,
           "handcheck_entry": {k: hce[k] for k in ("n_checked", "all_match")} if hce else None,
           "handcheck_exit": {k: hcx[k] for k in ("n_checked", "all_match")} if hcx else None,
           "precheck_frames": pre.get("frames_summary") if pre else None,
           "trials_logged": len(trials),
           "in_sample_only": {"val_access_log_unchanged": run["val_access_log_sha256_before"] == run["val_access_log_sha256_after"],
                              "val_access_log_sha256": run["val_access_log_sha256_after"]}}
    C.jdump(res, os.path.join(out, "results.json"))
    return res


def main():
    decl, sha = C.declared()
    res = verdict_all(C.OUT, C.load_base, decl, sha)
    print(json.dumps({"main_pass": res["main_pass"], "criteria": {k: (v.get("value", v.get("value_h")), v["pass"])
                                                                  for k, v in res["criteria"].items()}}, indent=1, default=str))


if __name__ == "__main__":
    main()
