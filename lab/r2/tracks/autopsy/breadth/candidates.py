"""Candidate records for the pairs that pass the breadth bar (results/r2/autopsy/breadth/candidates.json).

    PYTHONDONTWRITEBYTECODE=1 python3 candidates.py

For each qualifier: the complete rule text (re-implementable without this code), the numbers (window 2018-02 .. 2021,
FP costs, broker 3-spread rule), by year with FP costs and with costs x1.5, the earlier in-sample years, the ten-sleeve
portfolio before / after adding it (weekly sums of R), its weekly correlations, the same rule on sibling instruments
("neighbours": parameters are frozen, so the only neighbourhood is the instruments), the stop size, the truncation
test and the random-entry null.
"""
import json
import math
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common as C  # noqa: E402

COST = {
    "btcusd": "FP model: spread 22.5 USD at 76,000 (2.96 bp) in the frame with Dukascopy's intraday shape, slippage 1.5 bp stop / 0.5 bp market per side, swap long 20 %/yr, short 2 %/yr (triple Friday), no commission; FP crypto hours 24/5 (no bar from Friday 23:55 to Monday 00:00 server time)",
    "ethusd": "FP model: spread 3.0 USD at 2,300 (13.0 bp, marked uncertain in COSTS_FP.md) with Dukascopy's intraday shape, slippage 2.0 bp stop / 0.7 bp market per side, swap long 20 %/yr, short 2 %/yr (triple Friday); FP crypto hours 24/5",
    "us100": "FP model: spread 1.0 point at 27,000 (0.37 bp) with Dukascopy's intraday shape, slippage 0.5 bp stop / 0.2 bp market, swap long 4.7 %/yr, short 0 (triple Friday)",
    "jp225": "DECLARED model (no FP figure in the lab): spread 12 points at 50,000 = 2.4 bp all-in, Dukascopy JPN.IDX intraday spread shape, slippage 0.5 bp stop / 0.2 bp market, swap long 5.5 %/yr, short 0 (triple Friday); the real FP spread must be read in MT5 before anything",
    "xagusd": "FP model: spread 0.03 USD (about 5.4 bp at 55.5) with Dukascopy's intraday shape, slippage 1.5 bp stop / 0.5 bp market, swap long 6 %/yr, short 0 (triple Wednesday)",
}

RULE_TEXT = {
    "donch4h_stop": (
        "Frozen rule donch4h_stop (lab/tracks/trend/strategy.py FINALISTS, parameters n=60, stop_atr=2, trail_atr=2, max_days=5, atr_n=14, "
        "both sides, no filter, UTC grid), unchanged, on {SYM}. BARS: 4-hour bars on the UTC grid (buckets starting 00, 04, 08, 12, 16, 20 UTC) "
        "built from M1 bars: high = (max M1 bid high + max M1 ask high)/2, low = (min bid low + min ask low)/2, close = (last bid close + last "
        "ask close)/2; a bucket without M1 bars is skipped; the bar is known one minute after the start of its last M1 bar (= decision time). "
        "DECISION at every 4h decision time, only if the sleeve is flat and its last trade exited on an M1 bar strictly before the first M1 bar "
        "after the decision: U = highest high and L = lowest low of the last 60 4h bars, the bar just closed included; ATR = Wilder ATR(14) of the "
        "4h bars (true range on these bars, alpha 1/14, seeded with the first true range of the history and run continuously). ENTRY: a buy-stop at U "
        "and a sell-stop at L, one cancels the other, live on every M1 bar from the first bar after the decision to the last bar before the next "
        "4h decision time; long when an M1 ask high >= U, filled at max(U, ask open) x (1 + stop slippage); short when an M1 bid low <= L, filled "
        "at min(L, bid open) x (1 - stop slippage); if both levels are touched in the same minute take the side opposite to that minute's bid "
        "move (short if bid close >= bid open, else long). STOP: initial stop = fill - side x 2 x ATR; trailing: after every M1 bar (the fill bar "
        "included) best = highest bid high since the fill for a long (lowest ask low for a short), starting at the fill price, and the stop "
        "becomes max(stop, best - 2 ATR) for a long / min(stop, best + 2 ATR) for a short, effective from the next bar; a long is out when an M1 "
        "bid low <= stop (a short when an ask high >= stop), at the stop price, or at the bar open if the bar opened beyond it, with stop "
        "slippage. TIME EXIT at market at the open of the first M1 bar at or after (decision time + 5 trading days at the same New-York wall-clock "
        "time, trading days rolling at 17:00 New York) - 5 minutes; if no bar starts within 30 minutes of that instant, at the open of the last "
        "bar before it. No target. One position at a time; positions are held through nights and weekends. Broker rule: an order whose stop is "
        "closer than 3 spreads is not taken. Costs: {COST}."),
    "orb_asia_2d_buf10": (
        "Frozen rule orb_asia_2d_buf10 (lab/tracks/orb/strategy.py FINALISTS: range 00:00-07:00 London, entry until 12:00 London, stop entry, "
        "buf_frac 0.1, stop at the opposite level, exit 16:00 New York 2 business days later, no target / trailing / filter), unchanged, on {SYM}. "
        "For each weekday London date D (London wall clock with its own daylight saving): RANGE = the M1 bars starting in [00:00, 07:00) London; "
        "at least 210 of them are required; H = highest ask high, L = lowest bid low, W = H - L (> 0). LEVELS at 07:00 London: buy = H + 0.1 W, "
        "sell = L - 0.1 W. ENTRY WINDOW: M1 bars starting in [07:00, 12:00) London. The first bar with ask high >= buy (long) or bid low <= sell "
        "(short) is the day's only signal (both in one bar: the level nearer to that bar's mid open); it consumes the day: it is taken only if "
        "the sleeve has no open trade and its previous trade did not exit on that bar or later, otherwise there is no trade that day. FILL: long at "
        "max(buy, ask open) x (1 + stop slippage), short at min(sell, bid open) x (1 - stop slippage). STOP: the opposite level, an absolute "
        "price, never moved (long stopped when an M1 bid low <= sell, short when an ask high >= buy; fill at the stop or at the bar open if "
        "gapped beyond, with stop slippage). TIME EXIT at market at the open of the first M1 bar at or after 16:00 New York on D + 2 business days "
        "(Monday -> Wednesday, Tuesday -> Thursday, Wednesday -> Friday, Thursday -> Monday, Friday -> Tuesday; held through weekends). No "
        "target, no trailing, one position at a time. Broker rule: an order whose stop is closer than 3 spreads is not taken. Costs: {COST}."),
    "brk72_24h_wd": (
        "Frozen rule brk72_24h_wd (lab/r2/tracks/crypto/strategy.py FINALISTS: n=72, stop_atr=3, hold_h=24, weekday decisions, atr_n=24) with the "
        "FP-hours exit wrapper of lab/r2/recalc.py, unchanged, on {SYM}. BARS: hourly bars on the UTC hour grid from M1 mid prices (high = max of "
        "M1 mid highs, low = min of mid lows, close = last M1 mid close); hours without M1 bars are skipped (the look-backs count existing bars); "
        "the last hour is used only once its minute :59 exists. DECISION at the end of every hourly bar whose end falls on Monday-Friday UTC, if "
        "flat: long if the bar's close > the highest close of the previous 72 hourly bars, short if < their lowest close (strict). ENTRY at "
        "market at the open of the first M1 bar starting at or after the decision (dropped if more than 5 minutes late): long at ask open x (1 + "
        "market slippage), short at bid open x (1 - market slippage). STOP fixed at fill -/+ 3 x ATR24 (ATR24 = simple mean of the last 24 hourly "
        "true ranges). TIME EXIT at market at the open of the first M1 bar at or after decision + 24 h; if no bar starts within 30 minutes of "
        "that time (daily break, weekend, holiday), at the open of the last bar before it. No target, no trailing, one position at a time; a "
        "signal whose entry bar is at or before the previous trade's exit bar is ignored. Broker rule: an order whose stop is closer than 3 "
        "spreads is not taken. Costs: {COST}."),
    "F1_brk_ridge_filter": (
        "Frozen rule F1_brk_ridge_filter (lab/r2/tracks/ml/strategy.py FINALISTS: stop_k=2.0, exit 15:55 New York, frozen scorecard "
        "models/B1_ridge_full.json['frozen'] = models/F1_frozen_scorecard.json, threshold 0.027922380451488427), unchanged, on {SYM}; the full "
        "text specification is lab/r2/tracks/ml/ea_spec_F1.txt (only the instrument changes). BARS: H1 bars from M1 BID prices on whole UTC hours; "
        "only SESSION bars count = H1 bars starting 02:00..15:00 New York, Monday-Friday (14 a day); S[0] = the session bar just closed. DECISION "
        "at the close of a session bar starting 02:00..14:00 New York: HH = max high of S[1..14], LL = min low of S[1..14]; long candidate if close "
        "S[0] > HH, short if < LL; A = mean (high - low) of S[0..69]. FILTER: score = intercept + sum coef_i x clip((x_i - mean_i)/std_i, -4, 4) "
        "+ sum coef_j x dummy_j with the 13 numeric inputs brk, bar, body, ret4, ret14, ret70, chan, vol, pos, seq, opp, pdd, dret (definitions in "
        "ea_spec_F1.txt; all are price distances divided by A and signed by the side, plus counts of earlier breakouts in the last 14 session "
        "bars and the previous New-York session's high/low/close) and the 5 dummies decision hour 8-10 / 11-12 / 13-15 New York, Monday, Friday; "
        "trade only if score >= 0.027922380451488427 (constants in the JSON, never refitted). ENTRY at market at the open of the first M1 bar "
        "at or after the hour boundary (dropped if more than 5 minutes late). STOP fixed at fill -/+ 2.0 x A. EXIT at market at the first M1 bar at "
        "or after 15:55 New York the same day. No target, no trailing, nothing held overnight, one position at a time; a candidate arriving while "
        "a trade is open is dropped. Broker rule: an order whose stop is closer than 3 spreads is not taken. Costs: {COST}."),
    "ocm4": (
        "Frozen rule ocm4 (lab/r2/tracks/idx_us/strategy.py FINALISTS: n=4, stop 0.3 x ATR14 daily, size_min 1.0, size_win 20, exit 15:55), "
        "unchanged, on {SYM}, on the New-York clock. Sessions: Monday-Friday New-York dates that are not NYSE full holidays and not 13:00 early "
        "closes, from 2014. O = mid open of the first M1 bar starting in [09:30, 09:32) New York; C = mid close of the last M1 bar starting before "
        "09:34 (at most 10 minutes old); at least 3 of the 4 bars 09:30-09:33 must exist. move = C / O - 1; med = median of |move| over the "
        "previous 20 sessions (at least 10). If |move| >= med: buy if move > 0, sell if move < 0, at market at the open of the first M1 bar starting "
        "in [09:34, 09:39]. STOP fixed at 0.3 x ATR14 from the fill, ATR14 = simple mean of the true ranges of the last 14 COMPLETED daily bars "
        "(trading days ending 17:00 New York, mid prices, days with fewer than 600 M1 bars dropped). EXIT at market at the open of the first M1 bar "
        "at or after 15:55 New York (if none within 30 minutes, the last bar before). One trade a day at most. Broker rule: an order whose stop is "
        "closer than 3 spreads is not taken. Costs: {COST}."),
}

SIBLINGS = {
    "orb_asia_2d_buf10": ["btcusd", "ethusd", "us100", "us500", "us30", "ger40", "jp225", "xagusd"] + C.FX,
    "donch4h_stop": ["btcusd", "ethusd", "us100", "us500", "us30", "jp225", "xagusd", "ger40"] + C.FX,
    "brk72_24h_wd": ["jp225", "us100", "us500", "us30", "ger40", "xauusd", "xagusd"] + C.FX,
    "F1_brk_ridge_filter": ["xagusd", "xauusd", "us500", "us30", "jp225", "us100", "ger40"] + C.FX,
    "ocm4": ["btcusd", "ethusd", "us500", "us30", "ger40", "jp225", "xauusd", "xagusd"] + C.FX,
}


def sharpe(w):
    sd = float(w.std(ddof=1))
    return float(w.mean() / sd * math.sqrt(52)) if sd > 0 else float("nan")


def maxdd(w):
    c = np.cumsum(w.to_numpy())
    peak = np.maximum.accumulate(np.r_[0.0, c])
    return float((peak - np.r_[0.0, c]).max())


def friday_cross(t):
    """Trades still open at the next Friday 16:50 New York after their entry (= Friday 23:50 FP server time, when the
    hands v1.11 close everything): share of trades and their R."""
    if not len(t):
        return {"share_pct": 0.0, "R_of_those": 0.0}
    ny = t.entry_time.dt.tz_convert(C.NY)
    days = (4 - ny.dt.dayofweek) % 7
    fri = ny.dt.normalize() + pd.to_timedelta(days, unit="D") + pd.Timedelta(hours=16, minutes=50)
    fri = fri.where(ny < fri, fri + pd.Timedelta(days=7))
    x = t.exit_time.dt.tz_convert(C.NY) > fri
    return {"share_pct": round(float(x.mean() * 100), 1), "n": int(x.sum()), "R_of_those": round(float(t.R[x.to_numpy()].sum()), 1),
            "R_of_the_others": round(float(t.R[~x.to_numpy()].sum()), 1)}


def port_stats(w, n_trades):
    yrs = (C.IS_END - C.COMMON_START).days / 365.25
    return {"trades": int(n_trades), "total_R": round(float(w.sum()), 1), "R_per_year": round(float(w.sum()) / yrs, 1),
            "weekly_sharpe_ann": round(sharpe(w), 3), "win_weeks_pct": round(float((w > 0).mean() * 100), 1),
            "worst_week_R": round(float(w.min()), 1), "max_drawdown_R_weekly": round(maxdd(w), 1)}


def main():
    T = {json.loads(l)["id"]: json.loads(l) for l in open(os.path.join(C.RES, "trials.jsonl")) if l.strip()}
    res = pd.read_csv(os.path.join(C.RES, "pairs_results.csv"))
    inv = pd.read_csv(os.path.join(C.RES, "inventory_pairs.csv"))
    an = json.load(open(os.path.join(C.RES, "analysis.json")))
    tr = json.load(open(os.path.join(C.RES, "truncation.json"))) if os.path.exists(os.path.join(C.RES, "truncation.json")) else {}
    nl = json.load(open(os.path.join(C.RES, "null.json"))) if os.path.exists(os.path.join(C.RES, "null.json")) else {}
    corr = pd.read_csv(os.path.join(C.RES, "correlations.csv")).set_index("id")
    W = pd.DataFrame({f"{n}:{s}": C.weekly(C.window(C.official(n, s))) for n, s in C.SLEEVES})
    P = W.sum(axis=1)
    n0 = sum(len(C.window(C.official(n, s))) for n, s in C.SLEEVES)
    before = port_stats(P, n0)
    out = {"portfolio_before": before, "candidates": []}
    for rk in an["ranking"]:
        pid, rule, sym = rk["id"], rk["rule"], rk["instrument"]
        r = T[pid]
        t = C.window(pd.read_parquet(os.path.join(C.RES, "trades", f"{rule}__{sym}__fp.parquet")))
        ts = C.window(pd.read_parquet(os.path.join(C.RES, "trades", f"{rule}__{sym}__stress.parquet")))
        w = C.weekly(t)
        after = port_stats(P + w, n0 + len(t))
        risk_pct = (t.risk / t.entry * 100)
        t21 = t[t.entry_time.dt.year == 2021]
        sib = []
        for s in SIBLINGS.get(rule, []):
            if s == sym:
                continue
            m = res[(res.rule == rule) & (res.instrument == s)]
            if len(m):
                x = m.iloc[0]
                sib.append(f"{s}: run here, n {int(x.n)}, PF {x.pf}, t {x.t}, {int(x.years_pos)}/4 years, stress PF {x.stress_pf} -> {'PASS' if x.breadth_pass else 'fail'}")
                continue
            m = inv[(inv.rule == rule) & (inv.instrument == s)]
            if len(m):
                x = m.iloc[0]
                sib.append(f"{s}: {x.status} ({x.evidence})")
        cand = {
            "rank": rk["rank"], "id": pid, "rule": rule, "instrument": sym,
            "change": RULE_TEXT[rule].format(SYM=sym, COST=COST[sym]),
            "parameters": r["params"],
            "window": "trades entered 2018-02-01 .. 2021-12-31",
            "fp": {k: r["fp"].get(k) for k in ("n", "trades_per_year", "win_rate", "avg_win_R", "avg_loss_R", "expectancy_R", "t_stat", "pf",
                                               "total_R", "max_dd_R", "long_n", "long_R", "short_n", "short_R", "avg_hold_h", "bps_per_trade",
                                               "by_year_R", "exit_reasons")},
            "stress_x1_5": {k: r["stress"].get(k) for k in ("n", "pf", "expectancy_R", "t_stat", "total_R", "by_year_R")},
            "gross": {k: r["gross"].get(k) for k in ("n", "pf", "expectancy_R", "bps_per_trade")},
            "earlier_in_sample_years": {k: r["fp_before_2018_02"].get(k) for k in ("n", "pf", "expectancy_R", "t_stat", "total_R", "by_year_R")},
            "refused_by_3_spread_rule": r["refused_3spreads_fp"],
            "open_at_friday_1650_NY_hands_close": friday_cross(t),
            "top5pct_trades_share_of_total_R": round(float(np.sort(t.R.to_numpy())[::-1][: max(1, int(0.05 * len(t)))].sum() / t.R.sum()), 2),
            "stop_distance_pct_of_price": {"median": round(float(risk_pct.median()), 3), "p10": round(float(risk_pct.quantile(0.1)), 3),
                                           "p90": round(float(risk_pct.quantile(0.9)), 3),
                                           "median_2021": round(float((t21.risk / t21.entry * 100).median()), 3) if len(t21) else None},
            "portfolio_before": before, "portfolio_after": after,
            "delta_weekly_sharpe": rk["delta_sharpe_portfolio"], "extra_R_per_year": rk["extra_R_per_year"],
            "weekly_correlation": {k: v for k, v in corr.loc[pid].to_dict().items() if k not in ("rule", "instrument")},
            "neighbours_same_rule_other_instruments": sib,
            "zero_edge_pass_probability": rk["zero_edge_pass_prob"],
            "truncation_test": {k: v for k, v in tr.get(f"{rule}:{sym}", {}).items() if k != "cases"},
            "random_entry_null": nl.get(f"{rule}:{sym}"),
            "code_file": "lab/r2/tracks/autopsy/breadth/run_pairs.py (common.py run_rule; rule code unchanged in " +
                         {"donch4h_stop": "lab/tracks/trend/strategy.py", "orb_asia_2d_buf10": "lab/tracks/orb/strategy.py",
                          "brk72_24h_wd": "lab/r2/tracks/crypto/strategy.py + lab/r2/recalc.py::_crypto_fp_hours",
                          "F1_brk_ridge_filter": "lab/r2/tracks/ml/strategy.py", "ocm4": "lab/r2/tracks/idx_us/strategy.py"}[rule] + ")",
        }
        out["candidates"].append(cand)
        print(pid, rule, sym, "after", after, "| stop median %", cand["stop_distance_pct_of_price"]["median"])
    # all qualifiers together, and the best two
    tw = P.copy()
    n_all = n0
    for c in out["candidates"]:
        t = C.window(pd.read_parquet(os.path.join(C.RES, "trades", f"{c['rule']}__{c['instrument']}__fp.parquet")))
        tw = tw + C.weekly(t)
        n_all += len(t)
    out["portfolio_with_all_qualifiers"] = port_stats(tw, n_all)
    C.jdump(out, os.path.join(C.RES, "candidates.json"))
    print("before", before)
    print("with all", out["portfolio_with_all_qualifiers"])


if __name__ == "__main__":
    main()
