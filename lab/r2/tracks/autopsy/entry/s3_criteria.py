"""Addendum H, lens `entry` -- the candidate criteria (a)-(e) of declared.json on every part-2 cell; (f) is read from
truncation.json when it exists.  Writes results/r2/autopsy/entry/criteria.csv and verdicts.json."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import RES, YEARS, jdump, pd  # noqa: E402

DECL = json.load(open(os.path.join(RES, "declared.json")))
BASE = json.load(open(os.path.join(RES, "variants_baseline.json")))["sleeves"]


def cells():
    out = {}
    with open(os.path.join(RES, "trials.jsonl")) as fh:
        for ln in fh:
            d = json.loads(ln)
            if d.get("part") == "part2":
                out[(d["sleeve"], d["variant"]["id"], d["stop_mode"])] = d
    return out


def route_a(v, b, route):
    if route == "E":
        ok = v["exp_R"] is not None and v["exp_R"] >= b["exp_R"] + 0.20 * abs(b["exp_R"])
        if b["exp_R"] <= 0:
            ok = ok and v["exp_R"] > 0
        return bool(ok)
    return bool(v["n"] > 0 and abs(v["avg_loss_R"]) <= 0.80 * abs(b["avg_loss_R"]) and v["exp_R"] >= b["exp_R"])


def years_better(v, b, route):
    n = 0
    for y in YEARS:
        vy, by = v["by_year"].get(str(y)) or v["by_year"].get(y), b["by_year"].get(str(y)) or b["by_year"].get(y)
        if not vy or not by or not vy["n"] or not by["n"]:
            continue
        if route == "E":
            n += vy["exp_R"] > by["exp_R"]
        else:
            if vy["avg_loss_R"] is not None and by["avg_loss_R"] is not None:
                n += abs(vy["avg_loss_R"]) < abs(by["avg_loss_R"])
    return int(n)


def neighbour_ok(v, b, route):
    if route == "E":
        return bool(v["exp_R"] > b["exp_R"] and v["total_R"] >= b["total_R"])
    return bool(abs(v["avg_loss_R"]) < abs(b["avg_loss_R"]) and v["exp_R"] >= b["exp_R"])


def main():
    C = cells()
    trunc = {}
    tp = os.path.join(RES, "truncation.json")
    if os.path.exists(tp):
        trunc = json.load(open(tp)).get("cells", {})
    rows = []
    verdicts = {}
    for sl, spec in DECL["sleeves"].items():
        bf, bs = BASE[sl]["fp"]["common"], BASE[sl]["x1.5"]["common"]
        for v in spec["variants"]:
            for mode in v["stop_modes"]:
                d = C[(sl, v["id"], mode)]
                vf, vs = d["fp"]["common"], d["x1.5"]["common"]
                fill = d["fp"]["fill"]
                row = {"sleeve": sl, "variant": v["id"], "stop_mode": mode, "n_base": bf["n"], "n": vf["n"],
                       "exp_base": bf["exp_R"], "exp": vf["exp_R"],
                       "exp_change_pct": round(100 * (vf["exp_R"] - bf["exp_R"]) / abs(bf["exp_R"]), 1)
                       if bf["exp_R"] else None,
                       "avg_loss_base": bf["avg_loss_R"], "avg_loss": vf["avg_loss_R"],
                       "total_base": bf["total_R"], "total": vf["total_R"],
                       "total_gain": round(vf["total_R"] - bf["total_R"], 2),
                       "win_base": bf["win_rate"], "win": vf["win_rate"],
                       "exp_base_x1.5": bs["exp_R"], "exp_x1.5": vs["exp_R"], "total_base_x1.5": bs["total_R"],
                       "total_x1.5": vs["total_R"], "total_gain_x1.5": round(vs["total_R"] - bs["total_R"], 2),
                       "share_filled": fill["share_filled"], "n_signals_taken": fill["n_signals_taken"],
                       "variant_meanR_filled": fill["variant_meanR_filled"],
                       "rule_entry_meanR_on_filled": fill["rule_entry_meanR_on_filled"],
                       "rule_entry_meanR_on_missed": fill["rule_entry_meanR_on_missed"],
                       "rule_entry_totalR_on_missed": fill["rule_entry_totalR_on_missed"],
                       "n_missed": fill["n_missed"], "n_market_fallback": fill["n_market_fallback"],
                       "refused_legs": fill["n_refused_legs"]}
                for y in YEARS:
                    vy = vf["by_year"].get(str(y)) or {}
                    by = bf["by_year"].get(str(y)) or {}
                    row[f"exp_{y}"] = vy.get("exp_R")
                    row[f"exp_base_{y}"] = by.get("exp_R")
                    row[f"tot_{y}"] = vy.get("total_R")
                    row[f"tot_base_{y}"] = by.get("total_R")
                res = {}
                for route in ("E", "L"):
                    a = route_a(vf, bf, route)
                    b_ = vf["total_R"] >= bf["total_R"]
                    c_ = years_better(vf, bf, route)
                    d_ = route_a(vs, bs, route) and vs["total_R"] >= bs["total_R"]
                    nb_ids = spec["neighbours"][v["id"]]
                    e_ = all(neighbour_ok(C[(sl, nid, mode)]["fp"]["common"], bf, route) for nid in nb_ids)
                    res[route] = {"a": a, "b": bool(b_), "c_years": c_, "c": c_ >= 3, "d": bool(d_), "e": bool(e_),
                                  "neighbours": nb_ids}
                    res[route]["a_to_e"] = all(res[route][x] for x in ("a", "b", "c", "d", "e"))
                tk = f"{sl}|{v['id']}|{mode}"
                f_ = trunc.get(tk, {}).get("identical") if trunc else None
                for route in ("E", "L"):
                    res[route]["f"] = f_
                    row[f"{route}_a"] = res[route]["a"]
                    row[f"{route}_b"] = res[route]["b"]
                    row[f"{route}_c_years"] = res[route]["c_years"]
                    row[f"{route}_d"] = res[route]["d"]
                    row[f"{route}_e"] = res[route]["e"]
                    row[f"{route}_a_to_e"] = res[route]["a_to_e"]
                row["f_truncation_identical"] = f_
                row["candidate"] = bool((res["E"]["a_to_e"] or res["L"]["a_to_e"]) and f_ is True)
                row["passes_a_to_e"] = bool(res["E"]["a_to_e"] or res["L"]["a_to_e"])
                rows.append(row)
                verdicts[tk] = res
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(RES, "criteria.csv"), index=False)
    jdump({"what": "criteria (a)-(f) of declared.json per cell; f from truncation.json", "cells": verdicts},
          os.path.join(RES, "verdicts.json"))
    show = df[["sleeve", "variant", "stop_mode", "n", "exp_base", "exp", "exp_change_pct", "total_base", "total",
               "total_gain", "total_gain_x1.5", "share_filled", "E_a", "E_b", "E_c_years", "E_d", "E_e", "L_a",
               "L_a_to_e", "passes_a_to_e", "f_truncation_identical"]]
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 200)
    print(show.to_string(index=False))
    print("\ncells passing (a)-(e):", int(df.passes_a_to_e.sum()))
    print(df[df.passes_a_to_e][["sleeve", "variant", "stop_mode", "exp_base", "exp", "total_gain",
                                "total_gain_x1.5"]].to_string(index=False))


if __name__ == "__main__":
    main()
