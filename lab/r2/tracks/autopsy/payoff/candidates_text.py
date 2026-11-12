"""Writes results/r2/autopsy/payoff/candidates.json: one complete, re-implementable specification per candidate
(variants passing criteria a-f), ranked per sleeve by the declared rule, with the figures from summary.json."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

D_TEXT = {
    "noise30": "D = |F - band centre|, the rule's own stop price being the band centre max(O, PC) for a long / min(O, PC) "
               "for a short (O = 09:30 NY mid open, PC = previous session 16:00 mid)",
    "ocm4": "D = 0.3 x ATR14 (simple mean of 14 true ranges of mid daily bars, days ending 17:00 NY, last completed day)",
    "brk72_24h_wd": "D = 3 x ATR24 (mean true range of the last 24 hourly mid bars, UTC hours, frozen at the decision)",
    "F1_brk_ridge_filter": "D = 2 x A (A = mean high-low of the last 70 bid session H1 bars 02:00-15:00 NY)",
    "nq_btc_follow": "D = 2 x sigma60, sigma60 = (20-day RMS of BTC 1-min mid log returns) x sqrt(60) x BTC mid close "
                     "of the decision bar",
    "donch4h_stop": "D = 2 x ATR14 of 4h mid bars (Wilder), which is also the rule's trailing distance",
    "orb_asia_2d_buf10": "D = |F - opposite pending level| (the rule's own stop price)",
}
UNIT_TEXT = {"ocm4": "U = ATR14 daily (D = 0.3 U)", "nq_btc_follow": "U = sigma60 (D = 2 U)"}
CLOCK = {"noise30": "15:55 New York", "ocm4": "15:55 New York", "F1_brk_ridge_filter": "15:55 New York",
         "brk72_24h_wd": "decision + 24 h (the weekend wrapper moves it to the last bar before the Friday 23:55 server closure)",
         "nq_btc_follow": "entry + 60 min"}
EXT = {"ocm4": "15:55 NY on the entry's NY date + j business days (a time inside a closure -> the open of the last M1 "
               "bar before it, lab convention gl.exit_index)",
       "F1_brk_ridge_filter": "15:55 NY on the decision's NY date + j business days, never later than the open of the "
                              "last M1 bar before the weekend closure of the entry's server week (Friday 23:54 server)",
       "brk72_24h_wd": "decision + 24 x (1 + j) h through gl.exit_index (a time inside a closure -> the last bar before "
                       "it), never later than the Friday 23:54 server bar of the entry's server week"}
CAP = {"ocm4": "15:55 NY on the 4th business day after the entry's NY date (open of the first M1 bar at/after it; "
               "inside a closure: the last bar before it)",
       "nq_btc_follow": "the open of the last M1 bar before the weekend closure of the entry's server week (Friday 23:54 "
                        "server = 16:54 NY)"}
REENTRY = {True: "With re-entry: one position at a time over the sleeve's full signal list (after a stop-out the next "
                 "signal whose entry bar is after the exit bar is taken)",
           False: "Without re-entry: only the signals that the UNCHANGED rule takes; the EA keeps a shadow copy of the "
                  "unchanged rule's trade (same entry, rule stop and clock exit) and ignores every signal arriving while "
                  "that shadow trade is open, even when the real (tighter-stop) trade is already closed",
           "n/a": "Re-entry cannot occur for this rule (one signal a day / a week, or noise30's state machine which "
                  "ignores stop-outs), so the signal list is unchanged"}


def fmt(c):
    return (f"n {c['n']}, win {c['win_rate']:.3f}, exp {c['exp_R']:+.4f} R, avg win {c['avg_win_R']:+.3f}, avg loss "
            f"{c['avg_loss_R']:+.3f}, PF {c['pf']:.3f}, total {c['total_R']:+.1f} R, max DD {c['max_dd_R']:.1f} R")


def change_text(name, sym, spec):
    f = spec["family"]
    base = (f"Sleeve {name} on {sym}: the frozen rule (entries, filters, order types, rule stop, exits as registered in "
            f"lab/r2/recalc.py) with ONE change. F = actual fill price, side = +1 long / -1 short, {D_TEXT[name]}. ")
    if f == "S":
        k = spec["k"]
        s = (f"CHANGE: the initial stop is placed at F - side x {k} x D (distance {k} D from the fill) instead of "
             f"F - side x D; the position size is risk money / ({k} x D), i.e. the same money risk per trade, so R is "
             f"measured on the new stop. ")
        if name == "donch4h_stop":
            s += f"The trailing distance is scaled the same way ({k} x 2 x ATR14(4h) from the best bid high / ask low). "
        else:
            s += "The stop never moves. "
        s += ("Every other exit is unchanged. An order whose new stop distance is below 3 x the bid-ask spread of its fill "
              "bar is not sent (it does not block later signals). " + REENTRY[spec["reentry"]] + ".")
        return base + s
    if f == "T":
        m = spec["m"]
        return base + (f"CHANGE: the clock exit ({CLOCK[name]}) is removed. {UNIT_TEXT[name]}. From the fill, a trailing "
                       f"stop at distance {m} x U from the best price since the fill (bid high for a long, ask low for a "
                       f"short), recomputed at each M1 bar close and applied from the next bar; the initial stop distance is "
                       f"min(D, {m} U) and the position size / R use it. The trade ends on that stop or at the time cap: "
                       f"{CAP[name]}. One position at a time over the full signal list (signals arriving while the "
                       f"trade is open are ignored). Orders whose initial stop is below 3 spreads are not sent.")
    if f == "H":
        j = spec["j"]
        return base + (f"CHANGE: at the close of the M1 bar just before the clock-exit bar ({CLOCK[name]}), if the trade is "
                       f"still open and side x (exit-side close - F) >= 1.0 x D (exit side: bid close for a long, ask close "
                       f"for a short), the clock exit is postponed to {EXT[name].replace('j business', f'{j} business').replace('(1 + j)', f'(1 + {j})')}; "
                       f"the stop stays where it is (no trailing, no break-even). Otherwise the rule's own clock exit is "
                       f"executed. One position at a time over the full signal list (signals arriving during the "
                       f"extension are ignored).")
    if f == "B":
        b = spec["b"]
        return base + (f"CHANGE: once the favourable excursion since the fill (bid high - F for a long, F - ask low for a "
                       f"short, measured at each M1 bar close) reaches {b} x D, the stop is moved to F from the next M1 bar "
                       f"on. Nothing else changes.")
    raise ValueError(f)


def main():
    s = json.load(open(os.path.join(C.OUT, "summary.json")))
    ranks = {(r["sleeve"], r["variant"]): r for r in s["candidates_ranked"]}
    out = []
    for key, t in s["variants"].items():
        name, sym = key.split(":")
        ref = t["reference"]
        byv = {v["variant"]: v for v in t["variants"]}
        for v in t["variants"]:
            if not v["candidate"]:
                continue
            r = ranks[(key, v["variant"])]
            cr = v["criteria"]
            rf, vf = ref["risk_fp"], v["risk_fp"]
            nb = []
            for x in cr["neighbours"]:
                if x in byv:
                    c = byv[x]["fp"]
                    nb.append(f"{x}: exp {c['exp_R']:+.4f} R, total {c['total_R']:+.1f} R")
                else:
                    nb.append(f"{x}: shape track BE1 (whole in-sample period) exp +{__import__('evaluate').SHAPE_BE1[key]['exp_R']} "
                              f"vs {__import__('evaluate').SHAPE_BE1[key]['base_exp_R']}, total "
                              f"{__import__('evaluate').SHAPE_BE1[key]['total_R']} vs {__import__('evaluate').SHAPE_BE1[key]['base_total_R']}")
            yv = {y: x["exp_R"] for y, x in v["by_year_fp"].items()}
            yr = {y: x["exp_R"] for y, x in ref["by_year_fp"].items()}
            cau = v["causality"]
            wit = v["witness_fp"]
            extra = ""
            if wit and v["spec"]["family"] == "S" and v["spec"].get("reentry") in (False, "n/a"):
                extra = (f"; witness (reference trades): {wit['stopped_earlier_by_tighter_stop']} of {wit['ref_trades']} "
                         f"exit earlier on the tighter stop, {wit['of_which_reference_ended_in_gain']} of them had ended in "
                         f"gain in the reference ({wit['reference_R_given_up_on_those']:+.1f} reference R given up)")
            if v.get("extended_trades_fp"):
                extra += f"; {v['extended_trades_fp']} trades extended"
            out.append({
                "id": f"{key}:{v['variant']}", "sleeve": key, "family": v["spec"]["family"],
                "rank_for_its_sleeve": int(r["rank_declared"]), "rank_by_sharpe_info_only": int(r["rank_sharpe_info_only"]),
                "change": change_text(name, sym, v["spec"]),
                "parameters": json.dumps(v["spec"]),
                "before": f"reference, entries 2018-02-01..2021-12-31, FP costs: {fmt(ref['fp'])}; per-trade Sharpe "
                          f"{rf['sharpe_trade']:.3f}; {rf['bps_trade']:.1f} bp/trade at constant notional",
                "after": f"same window and costs: {fmt(v['fp'])}; per-trade Sharpe {vf['sharpe_trade']:.3f} "
                         f"(x{vf['sharpe_ratio_vs_ref']:.2f}); {vf['bps_trade']:.1f} bp/trade; exp {cr['exp_gain_pct']:+.0f} %; "
                         + (f"extra cost per trade that would erase the lead {vf['cost_tol_bp']:.1f} bp; "
                            if vf['cost_tol_bp'] < 1000 else "not more cost-sensitive than the reference; ")
                         + f"entries before 2018-02-01 (not a criterion{'; ETH: January 2018 only' if sym == 'ethusd' else ''}): "
                         f"n {v['early'].get('n')}, exp {v['early'].get('exp_R')} vs ref {ref['early'].get('exp_R')}{extra}",
                "by_year": "exp R variant vs reference: " + ", ".join(f"{y} {yv.get(y, 0):+.3f} vs {yr.get(y, 0):+.3f}"
                                                                        for y in sorted(yr)) + f" (better in {cr['years_better']})",
                "with_costs_x1_5": f"exp {v['stress']['exp_R']:+.4f} vs {ref['stress']['exp_R']:+.4f} R, total "
                                   f"{v['stress']['total_R']:+.1f} vs {ref['stress']['total_R']:+.1f} R, n {v['stress']['n']}; "
                                   f"refused stops < 3 spreads: {v['refused_orders_fp']} orders ({100 * v['refused_share_of_orders_fp']:.2f} %) "
                                   f"with FP costs, {v['refused_orders_stress']} ({100 * v['refused_share_of_orders_stress']:.2f} %) with x1.5",
                "neighbours": "; ".join(nb) + f" (reference exp {ref['fp']['exp_R']:+.4f}, total {ref['fp']['total_R']:+.1f}); all improve",
                "causality_test": f"truncation test: decision recomputed on frames cut right after the decision bar "
                                  f"{cau['decision']} identical; trade path on frames cut inside the trade {cau['path']} identical",
                "code_file": "/home/user/gold-orb/lab/r2/tracks/autopsy/payoff/variants.py"})
    out.sort(key=lambda d: (d["sleeve"], d["rank_for_its_sleeve"]))
    json.dump(out, open(os.path.join(C.OUT, "candidates.json"), "w"), indent=1)
    print(len(out))
    for d in out:
        if d["rank_for_its_sleeve"] == 1:
            print(json.dumps(d, indent=1))


if __name__ == "__main__":
    main()
