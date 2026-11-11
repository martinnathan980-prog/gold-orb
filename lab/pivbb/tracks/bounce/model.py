"""Stage H: can a model that sees the whole context of a touch pick the fades that pay?
Walk-forward gradient boosting (train on years < Y, predict Y), label = NET R of the fade in the engine
(every signal traded, FP costs). In-sample frame only (prices before 2022)."""
import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")))
from goldlab import r2  # noqa: E402
from goldlab.sim import simulate  # noqa: E402
import strategy as S  # noqa: E402

OUT = os.path.join(S.LAB, "results", "pivbb", "bounce")
FEATS = ["s", "lvl_code", "nth", "stretch15", "stretch60", "squeeze", "walk", "rsi", "mom4", "mom16", "atr15_d", "ny_hour",
         "range_used", "from_open", "d_wm", "d_pd", "div", "dow", "risk_atr", "wait_min"]
SPECS = {
    "H1_model_m5_confirmed": dict(entry="confirm", tf=5, pattern="close", window=3),
    "H2_model_blind_market": dict(entry="market"),
}


def dataset(m1, params):
    o = S.make_orders(m1, **params)
    tr = simulate(m1, o, sym="xauusd", costs=r2.costs("xauusd"), no_overlap=False)
    t = S.touches(m1, **params)
    d = tr.merge(t, left_on=["touch_i", "lvl"], right_on=["i", "level"], how="left", suffixes=("", "_t"))
    d["lvl_code"] = d.lvl.map({"D_" + k: j for j, k in enumerate(S.D_LEVELS)})
    d["dow"] = d.entry_time.dt.dayofweek
    d["year"] = d.entry_time.dt.year
    d["risk_atr"] = d.risk_ref / d.atr_d
    d["wait_min"] = d.dec_i - d.touch_i
    d["div"] = d["div"].astype(int)
    return d


def walk_forward(d, years=range(2016, 2022)):
    out = []
    for y in years:
        tr, te = d[d.year < y], d[d.year == y]
        m = HistGradientBoostingRegressor(max_depth=3, learning_rate=0.03, max_iter=150, min_samples_leaf=150, l2_regularization=1.0,
                                          random_state=0).fit(tr[FEATS], tr.R.clip(-1.5, 1.5))
        out.append(te.assign(pred=m.predict(te[FEATS])))
    return pd.concat(out)


def main():
    m1 = r2.load("xauusd", end="2022-01-01")
    for name, params in SPECS.items():
        d = dataset(m1, params)
        w = walk_forward(d)
        w["q"] = w.groupby("year").pred.transform(lambda x: pd.qcut(x, 5, labels=False, duplicates="drop"))
        tab = w.groupby("q").agg(n=("R", "size"), pred=("pred", "mean"), net_R=("R", "mean"), win=("R", lambda x: (x > 0).mean()))
        top = w[w.q == 4]
        pos = w[w.pred > 0]
        se = lambda x: float(x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 2 else float("nan")
        row = {"name": name, "stage": "H", "kind": "event-level model, walk-forward out-of-fold 2016-2021 (train on years < Y)",
               "params": {"rule": params, "model": "HistGradientBoostingRegressor(depth 3, lr 0.03, 150 trees, leaf 150) on net R", "features": FEATS},
               "n_oof": int(len(w)), "all_net_R": round(float(w.R.mean()), 4),
               "corr_pred_R": round(float(np.corrcoef(w.pred, w.R)[0, 1]), 4),
               "top_fifth": {"n": int(len(top)), "net_R": round(float(top.R.mean()), 4), "t": round(float(top.R.mean() / se(top.R)), 2),
                             "by_year": {int(y): round(float(g.R.mean()), 3) for y, g in top.groupby("year")}},
               "pred_positive": {"n": int(len(pos)), "net_R": round(float(pos.R.mean()), 4) if len(pos) else None,
                                 "t": round(float(pos.R.mean() / se(pos.R)), 2) if len(pos) > 2 else None},
               "by_fifth_net_R": {int(k): round(float(v), 4) for k, v in tab.net_R.items()}}
        print(name, "| touches traded:", len(d), "| OOF:", len(w))
        print(tab.round(4).to_string())
        print(json.dumps(row, default=str))
        with open(os.path.join(OUT, "trials.jsonl"), "a") as f:
            f.write(json.dumps(row, default=str) + "\n")


if __name__ == "__main__":
    main()
