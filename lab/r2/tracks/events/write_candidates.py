"""candidates.json: the finalist with IS + validation numbers, and the rejected ideas (IS only)."""
import json
from runner import RES, S, n_trials
rows = [json.loads(l) for l in open(f"{RES}/trials_full.jsonl")]
pre = json.load(open(f"{RES}/finalists_preval.json"))
val = json.load(open(f"{RES}/validation.json"))
fin = pre["finalists"]["EV_PREM_LONG"]
sl = {}
for sym in fin["syms"]:
    s, v = fin["sleeves"][sym], val[f"EV_PREM_LONG:{sym}"]
    sl[sym] = {"is": s["is"], "is_bps_per_trade": s["is_bps_per_trade"], "is_gross_bps_per_trade": s["is_gross_bps_per_trade"],
               "is_gross_pf": s["is_gross"]["pf"], "is_stress_pf": s["is_stress"]["pf"], "is_every_signal_expR": s["is_every_signal"]["expectancy_R"],
               "neighbor_median_pf": s["neighbors"]["median_pf_pm20"], "null_percentile": s["null_time"]["percentile"],
               "gross_bps_first_half": s["gross_bps_first_half"], "gross_bps_second_half": s["gross_bps_second_half"],
               "median_stop_2024_25": s["median_stop_2024_25"], "min_lot_stop_money_usd": s["min_lot_stop_money_usd"],
               "is_criteria": s["is_criteria"], "val": v["val"], "val_bps_per_trade": v["val_bps_per_trade"],
               "val_stress_pf": v["val_stress"].get("pf"), "val_every_signal_expR": v["val_every_signal"].get("expectancy_R"),
               "val_criteria": v["val_criteria"], "val_by_kind": v["diag"]["by_kind"], "val_by_year": v["diag"]["by_year"]}
def best(tag_prefix):
    out = []
    for r in rows:
        if r["tag"].startswith(tag_prefix):
            e = r["ev"]["is"]
            out.append({"sym": r["sym"], "tag": r["tag"], "n": e.get("n"), "pf": e.get("pf"), "t": e.get("t_stat"), "expR": e.get("expectancy_R"),
                        "bps": r["ev"].get("is_bps_per_trade"), "years_pos": e.get("years_pos"),
                        "params": {k: v for k, v in r["params"].items() if S.DEFAULTS.get(k) != v}})
    return out
out = {
    "track": "events", "n_trials_logged": n_trials(),
    "n_distinct_sym_params": len(set(json.dumps([r["sym"], r["params"]], sort_keys=True) for r in rows)),
    "verdict": "NOTHING SURVIVES: the only rule that passed the in-sample criteria failed the single-shot validation.",
    "finalists": {"EV_PREM_LONG": {"rule": fin["rule"], "params": S.FINALISTS["EV_PREM_LONG"]["params"], "syms": fin["syms"], "sleeves": sl,
                                   "basket_is": fin["basket_is"], "basket_val": val["EV_PREM_LONG:basket"], "passes": False}},
    "rejected_is": {
        "gold FOMC reaction momentum (not sent to validation: n=70, edge gone after mid-2017)": best("C:") + best("F:mom"),
        "index long from T-5m to the close / from T+5m to the close": best("A:day") + best("A:post"),
        "gold long through the release": best("B:"),
        "reaction momentum, all releases": best("D:mom-all"),
        "breakout bracket on the pre-release range (active from T+2m)": best("D:brk"),
        "pre-FOMC 24h drift (Lucca-Moench)": best("D:pre-fomc"),
        "FOMC reaction momentum on the indices": best("D:fomc-mom-idx"),
        "fade of the NFP reaction on the indices": best("D:nfp-fade"),
    },
}
json.dump(out, open(f"{RES}/candidates.json", "w"), indent=1, default=str)
print("written", f"{RES}/candidates.json", "| trials", out["n_trials_logged"], "| distinct", out["n_distinct_sym_params"])
