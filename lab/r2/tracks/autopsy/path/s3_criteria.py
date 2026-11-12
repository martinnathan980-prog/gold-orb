"""Part 2 -- the candidate criteria of declared.json, (a) to (e), on every simulated variant (trials.jsonl).
(f), the truncation test, is s4_truncation.py.  Output: results/r2/autopsy/path/criteria.csv
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


def crit_a(v, b):
    """Returns (pass, route)."""
    ev, eb = v["exp_R"], b["exp_R"]
    exp_ok = ev >= eb + 0.20 * abs(eb) and (eb > 0 or ev > 0)
    loss_ok = abs(v["avg_loss_R"]) <= 0.80 * abs(b["avg_loss_R"]) and ev >= eb
    if exp_ok:
        return True, "exp"
    if loss_ok:
        return True, "loss"
    return False, None


def years_better(v, b, route):
    k = 0
    for y in C.YEARS:
        vy, by = v["by_year"].get(str(y), v["by_year"].get(y)), b["by_year"].get(str(y), b["by_year"].get(y))
        if not vy or not by or vy["n"] == 0 or by["n"] == 0:
            continue
        if route == "loss":
            if vy["avg_loss_R"] is not None and by["avg_loss_R"] is not None and abs(vy["avg_loss_R"]) < abs(by["avg_loss_R"]):
                k += 1
        else:
            if vy["exp_R"] > by["exp_R"]:
                k += 1
    return k


def main():
    dec = json.load(open(os.path.join(C.RES, "declared.json")))
    trials = [json.loads(l) for l in open(os.path.join(C.RES, "trials.jsonl"))]
    base = json.load(open(os.path.join(C.RES, "variants_baseline.json")))
    assert len(trials) == dec["n_variants"] == len({t["id"] for t in trials})
    T = {t["id"]: t for t in trials}
    rows = []
    for t in trials:
        sl = t["sleeve"]
        bf, bs = base[sl]["fp"]["common"], base[sl]["stress"]["common"]
        vf, vs = t["fp"]["common"], t["stress"]["common"]
        a, route = crit_a(vf, bf)
        b_ = vf["total_R"] >= bf["total_R"]
        c_n = years_better(vf, bf, route or "exp")
        c = c_n >= 3
        a_s, _ = crit_a(vs, bs)
        d = a_s and vs["total_R"] >= bs["total_R"]
        # neighbours: same sleeve and rule, one step in one grid coordinate
        gi, gj = t["grid"]
        nb = [u for u in trials if u["sleeve"] == sl and u["rule"] == t["rule"] and u["id"] != t["id"]
              and abs(u["grid"][0] - gi) + abs(u["grid"][1] - gj) == 1]
        nb_ok = [u["fp"]["common"]["exp_R"] > bf["exp_R"] and u["fp"]["common"]["total_R"] >= bf["total_R"] for u in nb]
        e = len(nb) > 0 and all(nb_ok)
        pre_v, pre_b = t["fp"]["pre"], base[sl]["fp"]["pre"]
        rows.append({
            "id": t["id"], "sleeve": sl, "rule": t["rule"], "checkpoint": t["checkpoint"],
            "x": t["params"].get("x"), "y": t["params"].get("y"),
            "n_base": bf["n"], "n_var": vf["n"], "n_fired": vf["n_fired"], "n_new_trades": t["fp"]["n_new_trades"],
            "exp_base": bf["exp_R"], "exp_var": vf["exp_R"], "exp_change_pct": round((vf["exp_R"] - bf["exp_R"]) / abs(bf["exp_R"]) * 100, 1),
            "total_base": bf["total_R"], "total_var": vf["total_R"], "total_change": round(vf["total_R"] - bf["total_R"], 2),
            "avg_loss_base": bf["avg_loss_R"], "avg_loss_var": vf["avg_loss_R"],
            "avg_loss_change_pct": round((abs(vf["avg_loss_R"]) - abs(bf["avg_loss_R"])) / abs(bf["avg_loss_R"]) * 100, 1),
            "win_base": bf["win_rate"], "win_var": vf["win_rate"], "pf_base": bf["pf"], "pf_var": vf["pf"],
            "years_better": c_n,
            "by_year_total_change": {y: round(vf["by_year"][str(y)]["total_R"] - bf["by_year"][str(y)]["total_R"], 2) for y in C.YEARS},
            "stress_exp_base": bs["exp_R"], "stress_exp_var": vs["exp_R"],
            "stress_total_change": round(vs["total_R"] - bs["total_R"], 2),
            "pre_n": pre_v.get("n", 0), "pre_total_change": round(pre_v.get("total_R", 0) - pre_b.get("total_R", 0), 2) if pre_b.get("n", 0) else None,
            "pre_exp_base": pre_b.get("exp_R"), "pre_exp_var": pre_v.get("exp_R"),
            "neighbours": [u["id"] for u in nb], "neighbours_improve": nb_ok,
            "a": a, "a_route": route, "b": b_, "c": c, "d": d, "e": e,
            "pass_a_to_e": a and b_ and c and d and e})
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(C.RES, "criteria.csv"), index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 200)
    cols = ["id", "n_var", "n_fired", "n_new_trades", "exp_base", "exp_var", "exp_change_pct", "total_change",
            "avg_loss_change_pct", "years_better", "stress_total_change", "pre_total_change", "a", "b", "c", "d", "e"]
    print(df[cols].to_string(index=False))
    print("pass a-e:", df.pass_a_to_e.sum())


if __name__ == "__main__":
    main()
