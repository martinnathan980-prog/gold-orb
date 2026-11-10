"""Neighbour robustness of the two finalists (F1 = ridge-filtered breakout, F2 = unfiltered breakout) on
btcusd and ethusd. Every generator neighbour needs new labels on the 4 pool markets and a new walk-forward fit."""
import json
import sys

sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/ml")
from research import *  # noqa
import wf

POOL = ["us100", "ger40", "xauusd", "btcusd"]
BASE = {"stop_k": 2.0, "hold_h": 13.0}
GEN_NB = {
    "n11": {**BASE, "n": 11}, "n17": {**BASE, "n": 17},
    "stop1.6": {**BASE, "stop_k": 1.6}, "stop2.4": {**BASE, "stop_k": 2.4},
    "exit1455": {**BASE, "exit_hm": 1455}, "exit1655": {**BASE, "hold_h": 14.0, "exit_hm": 1655},
    "vol56": {**BASE, "vol_n": 56}, "vol84": {**BASE, "vol_n": 84},
}
REC = {"type": "ridge", "num": wf.NUM_FULL, "dummies": wf.DUM_FULL, "alpha": 1000.0}

if __name__ == "__main__":
    # phase 1: labels (every candidate taken on its own, in-sample frame) for each neighbour generator
    for sym in POOL:
        for tag, gen in GEN_NB.items():
            table(sym, gen, "NB_" + tag, gross=False)
        r2.free()
    # phase 2: walk-forward fits
    for tag, gen in GEN_NB.items():
        tabs = {s: table(s, gen, "NB_" + tag) for s in POOL}
        wf.fit("N_" + tag, REC, tabs, gen)
    tabs = {s: table(s, BASE, "X1") for s in POOL}
    m, _ = wf.fit("N_q", REC, tabs, BASE)                      # same model as B1, with the 0.4 / 0.6 thresholds
    b1 = json.load(open(os.path.join(S.MODEL_DIR, "B1_ridge_full.json")))
    assert np.allclose(m["frozen"]["coef"], b1["frozen"]["coef"]) and all(
        np.allclose(m["folds"][y]["coef"], b1["folds"][y]["coef"]) for y in b1["folds"])
    wf.fit("N_alpha500", {**REC, "alpha": 500.0}, tabs, BASE)
    wf.fit("N_alpha2000", {**REC, "alpha": 2000.0}, tabs, BASE)
    # phase 3: trials
    rows = []
    for sym in ["btcusd", "ethusd"]:
        for tag, gen in GEN_NB.items():
            ev = trial(sym, {**gen, "model": f"N_{tag}.json", "oof": True, "q": "0.5"}, stage="NB-F1", note=f"F1 neighbour {tag}")
            rows.append({"sym": sym, "fin": "F1", "nb": tag, "n": ev["is"]["n"], "pf": ev["is"]["pf"], "expR": ev["is"]["expectancy_R"], "t": ev["is"]["t_stat"], "years": ev["is"]["years_pos"]})
            print(sym, "F1", tag, line(ev))
            ev = trial(sym, gen, stage="NB-F2", note=f"F2 neighbour {tag}")
            rows.append({"sym": sym, "fin": "F2", "nb": tag, "n": ev["is"]["n"], "pf": ev["is"]["pf"], "expR": ev["is"]["expectancy_R"], "t": ev["is"]["t_stat"], "years": ev["is"]["years_pos"]})
            print(sym, "F2", tag, line(ev))
        for tag, p in {"q0.4": {**BASE, "model": "N_q.json", "oof": True, "q": "0.4"},
                       "q0.6": {**BASE, "model": "N_q.json", "oof": True, "q": "0.6"},
                       "alpha500": {**BASE, "model": "N_alpha500.json", "oof": True, "q": "0.5"},
                       "alpha2000": {**BASE, "model": "N_alpha2000.json", "oof": True, "q": "0.5"}}.items():
            ev = trial(sym, p, stage="NB-F1", note=f"F1 neighbour {tag}")
            rows.append({"sym": sym, "fin": "F1", "nb": tag, "n": ev["is"]["n"], "pf": ev["is"]["pf"], "expR": ev["is"]["expectancy_R"], "t": ev["is"]["t_stat"], "years": ev["is"]["years_pos"]})
            print(sym, "F1", tag, line(ev))
        r2.free()
    d = pd.DataFrame(rows)
    d.to_csv(os.path.join(RES, "neighbours.csv"), index=False)
    print(d.groupby(["fin", "sym"]).pf.agg(["median", "min", "max", "size"]).round(3))
    print("trials so far:", n_trials())
