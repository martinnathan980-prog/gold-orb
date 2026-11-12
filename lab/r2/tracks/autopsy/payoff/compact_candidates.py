"""Compact, complete specifications of the candidates for the structured result:
results/r2/autopsy/payoff/candidates_compact.json (same content as candidates.json, shorter wording)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

D = {"noise30": "D = |F - band centre|, band centre = max(O,PC) long / min(O,PC) short (O 09:30 NY mid open, PC previous 16:00 mid)",
     "ocm4": "D = 0.3 x ATR14 daily (simple mean, 17:00 NY days)",
     "brk72_24h_wd": "D = 3 x ATR24 of hourly mid bars",
     "F1_brk_ridge_filter": "D = 2 x A (A = mean high-low of the last 70 bid session H1 bars)",
     "nq_btc_follow": "D = 2 x U, U = sigma60 = 20-day RMS of BTC 1-min mid log returns x sqrt(60) x BTC mid close of the decision bar",
     "donch4h_stop": "D = 2 x ATR14(4h) = its trailing distance",
     "orb_asia_2d_buf10": "D = |F - opposite pending level| (the rule's stop)"}
RE = {True: "with re-entry: one position at a time over all signals",
      False: "without re-entry: only signals the unchanged rule takes (a shadow copy of the unchanged trade blocks signals until it would have closed)",
      "n/a": "re-entry impossible for this rule (signal list unchanged)"}


def change(name, sym, sp):
    h = f"{name} {sym}, frozen rule except (F = fill price, side +1/-1, {D[name]}): "
    f = sp["family"]
    if f == "S":
        k = sp["k"]
        t = (f"initial stop at F - side x {k} x D, size = risk money / ({k} D) (same money risk, R on the new stop); "
             + (f"trail also {k} x 2 ATR14(4h) from the best bid high/ask low; " if name == "donch4h_stop" else "stop fixed; ")
             + f"other exits unchanged; order not sent if {k} D < 3 x spread of the fill bar; {RE[sp['reentry']]}.")
        return h + t
    if f == "T":
        m = sp["m"]
        cap = ("15:55 NY on entry date + 4 business days" if name == "ocm4" else
               "last M1 bar before the weekend closure of the entry's server week (Friday 23:54 server)")
        clk = "15:55 NY exit" if name == "ocm4" else "entry+60 min exit"
        return h + (f"{clk} removed; trailing stop {m} x U (U = {'ATR14 daily' if name == 'ocm4' else 'sigma60'}) from the best "
                    f"bid high (long) / ask low (short) since the fill, updated at each M1 close, used from the next bar; initial "
                    f"stop distance min(D, {m} U), size on it; time cap at the open of the first M1 bar at/after {cap} (inside a "
                    f"closure: last bar before it); one position at a time; order not sent if the initial stop < 3 spreads.")
    if f == "H":
        j = sp["j"]
        if name == "brk72_24h_wd":
            clk, ext = "decision+24 h exit (weekend wrapper)", f"decision + {24 * (1 + j)} h (gl.exit_index), capped at the Friday 23:54 server bar"
        elif name == "F1_brk_ridge_filter":
            clk, ext = "15:55 NY exit", f"15:55 NY on the decision date + {j} business days, capped at the last bar before the weekend closure"
        else:
            clk, ext = "15:55 NY exit", f"15:55 NY on the entry date + {j} business days (inside a closure: last bar before it)"
        return h + (f"at the close of the M1 bar before the {clk} bar, if the trade is open and side x (bid close long / ask "
                    f"close short - F) >= D, the exit moves to {ext}; stop unchanged; otherwise the rule's exit; one position "
                    f"at a time (signals during the extension ignored).")
    if f == "B":
        return h + (f"once the favourable excursion since the fill (bid high - F long, F - ask low short, at M1 closes) "
                    f"reaches {sp['b']} x D, the stop moves to F from the next M1 bar; nothing else changes.")
    raise ValueError(f)


def st(c, r=None):
    return (f"n {c['n']}, win {100 * c['win_rate']:.1f} %, exp {c['exp_R']:+.3f} R, avg win {c['avg_win_R']:+.2f}, avg loss "
            f"{c['avg_loss_R']:+.2f}, PF {c['pf']:.2f}, total {c['total_R']:+.1f} R, max DD {c['max_dd_R']:.1f} R")


def main():
    s = json.load(open(os.path.join(C.OUT, "summary.json")))
    full = {d["id"]: d for d in json.load(open(os.path.join(C.OUT, "candidates.json")))}
    out = []
    for key, t in s["variants"].items():
        name, sym = key.split(":")
        ref = t["reference"]
        byv = {v["variant"]: v for v in t["variants"]}
        for v in t["variants"]:
            if not v["candidate"]:
                continue
            fid = f"{key}:{v['variant']}"
            cr = v["criteria"]
            rf, vf = ref["risk_fp"], v["risk_fp"]
            nb = "; ".join((f"{x} exp {byv[x]['fp']['exp_R']:+.3f}, total {byv[x]['fp']['total_R']:+.1f}" if x in byv
                            else f"{x} (shape track, whole period) exp +7 % vs its base") for x in cr["neighbours"])
            yv = {y: x["exp_R"] for y, x in v["by_year_fp"].items()}
            yr = {y: x["exp_R"] for y, x in ref["by_year_fp"].items()}
            w = v["witness_fp"]
            extra = ""
            if w and v["spec"]["family"] == "S" and v["spec"].get("reentry") in (False, "n/a"):
                extra = f"; {w['stopped_earlier_by_tighter_stop']}/{w['ref_trades']} reference trades exit earlier, {w['of_which_reference_ended_in_gain']} of them were reference winners"
            if v.get("extended_trades_fp"):
                extra += f"; {v['extended_trades_fp']} trades extended"
            ctol = (f"lead survives {vf['cost_tol_bp']:.1f} bp extra cost/trade" if vf["cost_tol_bp"] < 1000 else
                    "not more cost-sensitive")
            early = f"before 2018-02 (not a criterion{', ETH Jan-2018 only' if sym == 'ethusd' else ''}): exp {v['early'].get('exp_R')} vs {ref['early'].get('exp_R')} (n {v['early'].get('n')})"
            out.append({
                "id": fid, "sleeve": key, "rank_for_its_sleeve": full[fid]["rank_for_its_sleeve"],
                "change": change(name, sym, v["spec"]),
                "parameters": json.dumps({k: x for k, x in v["spec"].items() if k != "id"}),
                "before": f"reference 2018-02..2021, FP costs: {st(ref['fp'])}, Sharpe/trade {rf['sharpe_trade']:.3f}",
                "after": (f"{st(v['fp'])}, Sharpe/trade {vf['sharpe_trade']:.3f} (x{vf['sharpe_ratio_vs_ref']:.2f}), exp "
                          f"{cr['exp_gain_pct']:+.0f} %; {ctol}; {early}{extra}"),
                "by_year": ", ".join(f"{y} {yv.get(y, 0):+.3f} vs {yr.get(y, 0):+.3f}" for y in sorted(yr)) + f" ({cr['years_better']} better)",
                "with_costs_x1_5": (f"exp {v['stress']['exp_R']:+.3f} vs {ref['stress']['exp_R']:+.3f}, total "
                                    f"{v['stress']['total_R']:+.1f} vs {ref['stress']['total_R']:+.1f} R; stops < 3 spreads refused: "
                                    f"{v['refused_orders_fp']} (FP) / {v['refused_orders_stress']} (x1.5) orders"),
                "neighbours": nb + " (all improve on the reference)",
                "causality_test": f"truncation: decision {v['causality']['decision']} identical, path {v['causality']['path']} identical",
                "code_file": "/home/user/gold-orb/lab/r2/tracks/autopsy/payoff/variants.py"})
    out.sort(key=lambda d: (d["sleeve"], d["rank_for_its_sleeve"]))
    json.dump(out, open(os.path.join(C.OUT, "candidates_compact.json"), "w"), indent=1)
    print(len(out), sum(len(json.dumps(d)) for d in out))


if __name__ == "__main__":
    main()
