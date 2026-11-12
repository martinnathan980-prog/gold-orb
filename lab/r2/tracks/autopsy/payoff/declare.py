"""Writes results/r2/autopsy/payoff/declared.json BEFORE any variant is simulated (rule 5).

Run once.  Refuses to overwrite an existing declaration (the declaration is frozen once written).
"""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

SLEEVES = {
    # name:sym -> units, clock exit, re-entry relevance, families
    "noise30:us100": {
        "unit": "band half-width at the entry check: s x max(O, PC) for a long, s x min(O, PC) for a short "
                "(s = 14-session mean absolute move from the 09:30 open to that check time, the rule's own band); "
                "the rule's stop is the band centre, R0 = |fill - band centre| (> 1 unit)",
        "clock_exit": "15:55 New York (orders whose exit_i is the 15:55 bar); the band-check exits are signal exits "
                      "and are kept in every variant",
        "reentry": "moot: the rule's state machine ignores stop-outs and its orders never overlap (0 skipped in "
                   "sample), so a tighter or wider stop cannot change which signals are taken",
        "hold_ext": "15:55 New York on the entry's New-York date + j business days",
        "trail_cap": "15:55 New York on the entry's New-York date + 4 business days (5 sessions in all)",
        "B1.0_from_shape": True},
    "ocm4:us100": {
        "unit": "daily ATR14 of the rule (simple mean, 17:00 NY days); stop = 0.3 unit", "clock_exit": "15:55 New York",
        "reentry": "moot: one signal a day at 09:34, flat at 15:55",
        "hold_ext": "15:55 New York on the entry's New-York date + j business days",
        "trail_cap": "15:55 New York on the entry's New-York date + 4 business days",
        "B1.0_from_shape": True},
    "brk72_24h_wd:btcusd": {
        "unit": "ATR24 of hourly mid bars (the rule's `atr`); stop = 3 units",
        "clock_exit": "decision + 24 h (weekend wrapper: the last bar before the Friday 23:55 server closure)",
        "reentry": "relevant (2914 signals for 645 trades in sample)",
        "hold_ext": "decision + 24 h x (1 + j), gl.exit_index (a time inside a closure -> the last bar before it), never "
                    "after the last bar before the weekend closure of the entry's server week",
        "trail_cap": "the last bar before the weekend closure of the entry's server week (Friday 23:54 server)",
        "B1.0_from_shape": True},
    "brk72_24h_wd:ethusd": {
        "unit": "ATR24 of hourly mid bars; stop = 3 units", "clock_exit": "decision + 24 h (weekend wrapper)",
        "reentry": "relevant", "hold_ext": "as btcusd", "trail_cap": "as btcusd", "B1.0_from_shape": False},
    "F1_brk_ridge_filter:btcusd": {
        "unit": "A = mean (high - low) of the last 70 bid session H1 bars (the rule's unit); stop = 2 units",
        "clock_exit": "15:55 New York the same day", "reentry": "relevant (604 of 1235 orders skipped in sample)",
        "hold_ext": "15:55 New York on the decision's New-York date + j business days, never after the last bar "
                    "before the weekend closure of the entry's server week",
        "trail_cap": "the last bar before the weekend closure of the entry's server week",
        "B1.0_from_shape": True},
    "F1_brk_ridge_filter:ethusd": {
        "unit": "A (as btcusd); stop = 2 units", "clock_exit": "15:55 New York the same day", "reentry": "relevant",
        "hold_ext": "as btcusd", "trail_cap": "as btcusd", "B1.0_from_shape": False},
    "nq_btc_follow:btcusd": {
        "unit": "sigma60 = sigma_btc(1 min, 20 days) x sqrt(60) x price (the rule's unit); stop = 2 units",
        "clock_exit": "entry + 60 minutes", "reentry": "relevant (1548 of 2611 signals skipped in sample)",
        "hold_ext": "entry + 60 x (1 + j) minutes (one 'session' of this rule = its own 60-minute holding clock), "
                    "gl.exit_index, never after the last bar before the weekend closure of the entry's server week",
        "trail_cap": "the last bar before the weekend closure of the entry's server week",
        "B1.0_from_shape": False},
    "GOLD_FRI_PM:xauusd": {
        "unit": "Wilder ATR14 of UTC-hour mid bars (the rule's unit); stop = 3 units", "clock_exit": "16:45 New York Friday",
        "reentry": "moot: one limit order a week, flat at 16:45 New York",
        "hold_ext": "16:45 New York on the Friday + j business days (Monday, Tuesday)",
        "trail_cap": "16:45 New York on the Friday + 4 business days", "B1.0_from_shape": False},
    "donch4h_stop:xauusd": {
        "unit": "ATR14 of 4h mid bars; stop = trail = 2 units", "clock_exit": "none (it leaves on its 2-ATR trailing "
        "stop: 477 of 493 closed in-sample trades; the 5-day time cap binds on 8)",
        "reentry": "relevant (1159 of 1654 touched brackets skipped in sample)",
        "stop_scaling": "the rule's stop IS a trailing stop: stop_dist and trail are scaled together",
        "families_not_applicable": "T and H (no clock exit). B is a no-op by construction (the 2-unit trail = 1 R "
                                   "reaches break-even exactly at +1 R): B1.0 is run once as a check",
        "B1.0_from_shape": False},
    "orb_asia_2d_buf10:xauusd": {
        "unit": "W = width of the Asian range (ask high - bid low, 00:00-07:00 London), the rule's own unit; "
                "the stop is the opposite level, R0 = |fill - stop| (about 1.2 W)",
        "clock_exit": "16:00 New York, London date + 2 business days", "reentry": "relevant (43 % of signals skipped)",
        "hold_ext": "16:00 New York on the London session date + (2 + j) business days",
        "trail_cap": "16:00 New York on the London session date + 4 business days (the rule's own hold_days maximum)",
        "B1.0_from_shape": True},
}


def variants_for(key):
    s = SLEEVES[key]
    v = []
    moot = s["reentry"].startswith("moot")
    for k in (0.25, 0.5, 0.75):
        if moot:
            v.append({"id": f"S{k}", "family": "S", "k": k, "reentry": "n/a"})
        else:
            v.append({"id": f"S{k}r", "family": "S", "k": k, "reentry": True})
            v.append({"id": f"S{k}n", "family": "S", "k": k, "reentry": False})
    v.append({"id": "S1.5", "family": "S", "k": 1.5, "reentry": "n/a" if moot else True})
    if key != "donch4h_stop:xauusd":
        for m in (1, 2, 3):
            v.append({"id": f"T{m}", "family": "T", "m": m})
        for j in (1, 2):
            v.append({"id": f"H{j}", "family": "H", "j": j})
        if not s["B1.0_from_shape"]:
            v.append({"id": "B1.0", "family": "B", "b": 1.0})
        v.append({"id": "B1.5", "family": "B", "b": 1.5})
    else:
        v.append({"id": "B1.0", "family": "B", "b": 1.0, "note": "no-op check"})
    assert len(v) <= 14, (key, len(v))
    return v


def main():
    path = os.path.join(C.OUT, "declared.json")
    if os.path.exists(path):
        raise SystemExit("declared.json already exists: the declaration is frozen")
    out = {
        "written": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "protocol": "PROTOCOL_V3.md Addendum H, lens payoff (the shape of the bet); in sample only",
        "status_when_written": "the ten official in-sample trade lists were reproduced exactly (reproduce.json); no "
                               "variant had been simulated",
        "data": {"frames": "lab/data/fp/<sym>_m1.parquet read with the row filter ts < 2022-01-01 00:00 UTC",
                 "trades": "results/r2/recalc/trades/<name>__<sym>.parquet read with entry_time < 2022-01-01",
                 "leader": "nq_btc_follow: us100 mid closes of the in-sample slice registered with set_leader"},
        "windows": {"common": "entries 2018-02-01 .. 2021-12-31 (all candidate criteria)",
                    "early": "entries before 2018-02-01 (reported separately, not a criterion)",
                    "years": "2018 (Feb-Dec), 2019, 2020, 2021 by entry date"},
        "censoring": "trades still open at the end of the in-sample frame (non-crypto: exit at the last bar by time or "
                     "eod) are excluded from every statistic, reference and variants alike (one donch4h_stop and one "
                     "orb trade in the reference)",
        "costs": {"fp": "r2.costs(sym) on the stored FP frame", "stress": "spread x1.5 frame (apply_spread_mult) and "
                  "r2.costs(sym, 1.5), orders rebuilt on the stressed quotes (same as r2.run mode 'stress')"},
        "broker_minimum_stop": "an order whose initial stop distance (the stop actually used) is closer than 3 x the "
                               "spread of its fill bar (ask - bid of that bar, in the run's own frame) is NOT TAKEN: "
                               "it is removed before the simulation, so it does not block later signals.  For every "
                               "variant the share of refused orders is reported, and a diagnostic run without the "
                               "refusal gives the share of the trades it would have taken whose stop is that close",
        "R": "R = pnl / |fill - initial stop actually used| (the simulator's R): a tighter stop means a larger "
             "position at the same money risk",
        "fill_price": "for a variant that is a multiple of the rule's stop distance and for absolute stops (noise30, "
                      "orb), R0 = |fill - rule stop| with the fill computed exactly as the simulator does (market: "
                      "ask/bid open of the entry bar x (1 +/- market slippage); stop entry: worse of level and open "
                      "x (1 +/- stop slippage); limit: better of level and open), in the run's own cost mode; the "
                      "live EA sets the stop once the fill is known",
        "families": {
            "S": "stop distance at constant money risk: initial stop at k x the rule's own stop distance from the fill "
                 "(k = 0.25, 0.5, 0.75; 1 = reference; 1.5).  donch4h_stop: its trailing distance is scaled with it. "
                 "reentry=True: the sleeve's full signal list with one position at a time (after an earlier stop-out "
                 "the sleeve takes its next signal); reentry=False: only the orders that produced a reference trade "
                 "(same cost mode), one position at a time.  1.5 is run with re-entry only (it can only lengthen "
                 "trades).  Witness: in the reentry=False / n/a runs, every reference trade is compared with its own "
                 "variant trade: how many are stopped by the tighter stop while the reference trade was not stopped, "
                 "and how many of those ended in gain in the reference",
            "T": "the clock exit is replaced by a trailing stop at m x the rule's unit (m = 1, 2, 3), from the best "
                 "price since the fill (bid high for a long, ask low for a short), updated at each M1 close and used "
                 "from the next bar (the simulator's `trail`).  The initial stop is min(rule stop distance, m x unit) "
                 "and R is measured on it.  The trade then ends on that stop or at the time cap (`trail_cap`).  "
                 "noise30 keeps its band-check exits.  Signals arriving while the trade is open are skipped",
            "H": "at the close of the last bar before the clock exit bar: if the trade is still open and is ahead by at "
                 "least 1.0 R0 marked at that close on its exit side (bid for a long, ask for a short), the clock exit "
                 "is moved to `hold_ext` (j = 1 or 2 sessions); the stop is unchanged.  Otherwise the rule's exit is "
                 "kept.  The decision for each order is computed from its own path (all orders simulated "
                 "independently), then the sleeve is simulated one position at a time",
            "B": "stop moved to the fill price once the favourable excursion reaches b x R0 (b = 1.0, 1.5), the "
                 "simulator's `be` (bid high for a long, applied from the next bar).  B1.0 is NOT re-run where the "
                 "shape track already ran it (noise30, ocm4, brk72 btcusd, F1 btcusd, orb: results/r2/shape/"
                 "variants_all.csv, whole in-sample period); its figures are quoted from there"},
        "candidate_criteria": {
            "a": "on the common window, FP costs, against the reference: expectancy per trade +20 % or more (route E); "
                 "OR |average loss| (mean R of the losing trades) at most 0.8 x the reference's with an expectancy at "
                 "least equal (route L)",
            "b": "total R on the common window, FP costs, not lower than the reference's",
            "c": "route E: expectancy above the reference's in at least 3 of the 4 years; route L: |average loss| "
                 "below the reference's in at least 3 of the 4 years",
            "d": "with costs x1.5 the same route's (a) and (b) hold against the reference with costs x1.5",
            "e": "every in-grid neighbour of the same family and re-entry mode improves on the reference in the same "
                 "direction (route E: higher expectancy and total R not lower; route L: smaller |average loss| and "
                 "expectancy not lower), FP costs, common window.  Grid neighbours: S 0.25-0.5-0.75 (1.5 has no "
                 "variant neighbour and therefore cannot qualify), T 1-2-3, H 1-2, B 1.0-1.5 (where B1.0 comes from "
                 "the shape track, its whole-period figures are used)",
            "f": "causal: truncation test (decision fields recomputed on the frame cut right after the decision bar, "
                 "plus the trade's path on frames cut inside the trade) identical",
            "ranking": "if several variants of a sleeve qualify: higher expectancy with costs x1.5 on the common window "
                       "first, then higher FP total R; at most one change per sleeve is carried forward"},
        "not_trials": "the reference run of each sleeve (fp and stress) and the diagnostic runs without the 3-spread "
                      "refusal are not variants; causality checks are not variants",
        "sleeves": {k: {**v, "variants": variants_for(k)} for k, v in SLEEVES.items()},
    }
    out["n_variants"] = {k: len(v["variants"]) for k, v in out["sleeves"].items()}
    out["n_variants_total"] = sum(out["n_variants"].values())
    json.dump(out, open(path, "w"), indent=1)
    print(out["n_variants"], out["n_variants_total"])


if __name__ == "__main__":
    main()
