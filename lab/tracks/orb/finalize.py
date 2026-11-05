"""Write results/orb/candidates.json from the research cache (IS only), plus neighbour robustness
of the finalist.  Run BEFORE the single validation access (val_run.py adds the VAL block)."""
import json
import os

import numpy as np

import research as R
import strategy as S

FINAL = "orb_asia_2d_buf10"
FINAL_LABEL = "F3_A3_buf0.1"
NEIGHBOURS = ["A3_asia_hold2d"] + [f"N{i:02d}" for i in range(1, 15)]


def rows():
    return list(R.load_cache().values())


def compact(d):
    r = d["rep"]
    keys = ("n", "trades_per_year", "win_rate", "avg_win_R", "avg_loss_R", "expectancy_R", "pf", "t_stat",
            "total_R", "years_pos", "weeks_pos_pct", "max_dd_R", "worst_week_R", "long_n", "long_R",
            "short_n", "short_R", "avg_hold_h", "max_hold_h", "by_year_R")
    return {**{k: r.get(k) for k in keys}, "stress_pf": d["stress_pf"], "sides": d["sides"],
            "is_criteria": d["crit"]}


def main():
    rs = rows()
    by_label = {d["label"]: d for d in rs}
    fin = by_label[FINAL_LABEL]
    nb = [d for d in rs if d["label"] in NEIGHBOURS or d["label"].split("_")[0] in NEIGHBOURS]
    nb_pf = {d["label"]: d["rep"]["pf"] for d in nb}
    med = float(np.median(list(nb_pf.values())))
    out = {
        "track": "orb", "n_trials_logged": R.n_trials(),
        "finalists": {FINAL: {
            "label_in_trials": FINAL_LABEL, "params": S.FINALISTS[FINAL],
            "IS": compact(fin),
            "neighbours_pf": nb_pf, "neighbour_median_pf": round(med, 3),
            "criteria": {**{k: bool(v) for k, v in fin["crit"].items() if k != "pass"},
                         "neighbour_median_pf>=1.10": med >= 1.10},
        }},
        "all_trials_ranked_by_IS_pf": sorted(
            [{"label": d["label"], "stage": d["stage"], "n": d["rep"].get("n"), "pf": d["rep"].get("pf"),
              "t": d["rep"].get("t_stat"), "exp_R": d["rep"].get("expectancy_R"),
              "stress_pf": d["stress_pf"], "years_pos": d["rep"].get("years_pos"),
              "long_pf": d["sides"]["long"].get("pf"), "short_pf": d["sides"]["short"].get("pf"),
              "is_pass": d["crit"].get("pass")} for d in rs],
            key=lambda x: -(x["pf"] or 0)),
    }
    path = os.path.join(R.RES, "candidates.json")
    if os.path.exists(path):  # keep a VAL block if one was already written
        old = json.load(open(path))
        for k, v in old.get("finalists", {}).items():
            if k not in out["finalists"]:
                continue
            for kk, vv in v.items():  # keep VAL block, verdict, diagnostics written later
                if kk not in out["finalists"][k]:
                    out["finalists"][k][kk] = vv
            out["finalists"][k]["criteria"].update(v.get("val_criteria", {}))
        if "track_verdict" in old:
            out["track_verdict"] = old["track_verdict"]
    json.dump(out, open(path, "w"), indent=1, default=str)
    print("neighbour PFs:", nb_pf)
    print("median neighbour PF:", round(med, 3), "| trials:", R.n_trials())
    print(json.dumps(out["finalists"][FINAL]["criteria"]))


if __name__ == "__main__":
    main()
