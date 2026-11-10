"""Write the finalist decision (results/r2/gold2/finalists_preval.json) BEFORE any validation access.
Everything in it comes from in-sample evaluations already logged."""
import json, os, sys
import numpy as np, pandas as pd
from research import RES, LAB, r2, S, load_detail, key_of, n_configs

NAME = "sq24_breakout_1h"
RULE = ("XAUUSD, 1h bars on UTC hours (mid prices). After every 1h bar close, if the sleeve is flat: H = highest mid-high and "
        "L = lowest mid-low of the last 24 bars (the bar just closed included), W = H - L, Wref = median of W over the previous "
        "480 bars (at least 240 values). If W <= 0.7 x Wref, place an OCO pair valid until the next 1h bar closes: buy-stop at H "
        "(triggers on ask), sell-stop at L (triggers on bid); the first touched is the trade, the other is cancelled. Stop-loss "
        "2 x ATR14(1h, Wilder, value at the decision bar) from the fill price; trailing stop at the same distance from the best "
        "bid-high (long) / ask-low (short) since entry, updated at each M1 close; time stop 5 New-York trading days after the "
        "decision bar close minus 5 minutes (last bar before a closure). One position at a time; fixed % risk per trade.")

if __name__ == "__main__":
    out_path = os.path.join(RES, "finalists_preval.json")
    if os.path.exists(out_path):
        sys.exit("finalists_preval.json already exists: not overwritten")
    val_log = os.path.join(LAB, "results", "val_access.log")
    n_val = sum(1 for l in open(val_log) if '"gold2"' in l) if os.path.exists(val_log) else 0
    assert n_val == 0, "validation was already accessed by this track"
    f = S.FINALISTS[NAME]
    d = load_detail()[key_of("xauusd", f["params"])]
    nb = json.load(open(os.path.join(RES, "neighbours.json")))["SQ"]
    nul = json.load(open(os.path.join(RES, "null_tests.json")))
    dg = json.load(open(os.path.join(RES, "diag_shortlist_is.json")))["SQ"]
    chk = json.load(open(os.path.join(RES, "finalist_checks_preval.json")))
    cs = json.load(open(os.path.join(RES, "cost_sensitivity_is.json")))["SQ_1h"]
    span = json.load(open(os.path.join(RES, "spanning_vs_legacy_is.json")))["SQ_1h"]
    dec = json.load(open(os.path.join(RES, "decomposition_vs_legacy_is.json")))["SQ_1h"]
    crit = dict(d["crit"])
    crit["neighbors_median_pf>=1.06"] = nb["neighbour_median_pf"] >= 1.06
    crit["null_percentile>=97.5"] = nul["SQ:xauusd:day"]["percentile"] >= 97.5
    crit["pass"] = all(v for k, v in crit.items() if k != "pass")
    out = {
        "written_utc": pd.Timestamp.now("UTC").isoformat(timespec="seconds"),
        "track": "gold2",
        "configurations_logged_before_validation": n_configs(),
        "validation_accesses_by_this_track_before_this_file": n_val,
        "honesty_note": ("Gold validation data (2022-2025) was consulted in round 1 for OTHER rules and I have read those reports "
                         "(legacy 4h breakout: VAL PF 1.23 one-position, 0.91 every-signal, profit long-only; rn100: VAL fail; "
                         "orb_asia_2d: VAL nominal pass and 2026 holdout already used). No validation number of any gold2 "
                         "configuration was seen before this file was written."),
        "decision": ("ONE finalist, one sleeve (xauusd). Chosen on in-sample evidence only: the pre-declared volatility-contraction "
                     "breakout B5_sq1h_n24_07 is the only stage-B rule that passes every in-sample criterion AND is not spanned by "
                     "the legacy 4h sleeve (weekly-R correlation 0.15, spanning alpha t = 2.3, 87 % of its trades entered while "
                     "the legacy sleeve is flat or opposite)."),
        "not_selected": {
            "B3_d1h_n48_tr240_k2 (trend-aligned 2-day breakout)": "passes IS (PF 1.23, t 2.55, 9/9 years) but is spanned by the legacy "
                "sleeve (weekly correlation 0.57, alpha t 1.1); its trades unrelated to a legacy entry lose (-0.11 R, t -2.0).",
            "B1 1h multi-day channels (n240 k2/k3, n120 k3)": "pass IS but duplicate the legacy sleeve (98 % / 55 % of trades inside "
                "legacy trades, weekly correlation 0.72-0.82, alpha t ~1.0).",
            "A5_orb_asia_2d_buf10 (round-1 ORB finalist)": "passes IS under FP costs (PF 1.31, t 2.94) but its VAL and the 2026 holdout "
                "were already consumed in round 1: no clean test is left. Lead's call as a legacy candidate; not submitted.",
            "A6_rn100_break_fresh": "n 228 < 250, and it already failed VAL in round 1 (PF 0.84; 0.94 at zero commission/slippage).",
            "2h-bar version of the finalist (control)": "IS PF 1.28, sturdier to costs (PF 1.13 at costs x2 vs 1.04) but more correlated "
                "with the legacy sleeve (0.33, alpha t 1.65); the pre-declared 1h base is kept (no selection among bar sizes).",
        },
        "finalists": {
            NAME: {
                "syms": f["syms"], "params": S.resolve(f["params"]), "rule": RULE,
                "sleeves": {"xauusd": {
                    "is": d["is"], "is_bps_per_trade": d["is_bps"], "is_stress": d["stress"], "is_gross": d["gross"],
                    "is_gross_bps_per_trade": d["gross_bps"], "is_every_signal": d["every"],
                    "neighbours": nb, "null_test_day": nul["SQ:xauusd:day"], "null_test_time": nul["SQ:xauusd:time"],
                    "long_net": dg["long_net"], "short_net": dg["short_net"], "long_gross": dg["long_gross"], "short_gross": dg["short_gross"],
                    "gross_first_half_2013-2017H1": dg["half1_gross_2013-2017H1"], "gross_second_half_2017H2-2021": dg["half2_gross_2017H2-2021"],
                    "net_first_half": dg["half1_net_2013-2017H1"], "net_second_half": dg["half2_net_2017H2-2021"],
                    "gross_by_year": dg["gross_by_year"], "net_by_session": dg["net_by_session"],
                    "top5pct_share_of_total_R": dg["top5pct_share_of_total_R"], "total_R_without_top5pct": dg["total_R_without_top5pct"],
                    "cost_R_per_trade": dg["cost_R_per_trade"], "cost_sensitivity_pf_exp_t": cs,
                    "timing_probes": chk["timing_probes"], "stop_2024_2025": chk["stop_2024-2025"], "stop_2025": chk["stop_2025"],
                    "relation_to_legacy_sleeve": {"spanning": span, "decomposition": dec},
                    "is_criteria": crit,
                }},
                "silver_same_params": "xagusd IS: gross PF 1.40 (+0.139 R) but net PF 0.98 (-0.009 R) under FP costs -> no silver sleeve, no basket.",
            }
        },
    }
    json.dump(out, open(out_path, "w"), indent=1, default=str)
    print(json.dumps(out["finalists"][NAME]["sleeves"]["xauusd"]["is_criteria"]))
    print("written", out_path, "configs:", out["configurations_logged_before_validation"])
