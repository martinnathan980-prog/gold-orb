"""Second pass (in-sample only, touches before 2022):
1. magnet test with a distance-matched placebo: each level mirrored around the day's open
2. can a model that sees the whole context (Bollinger, momentum, clock, level, ...) tell bounce from break?
   walk-forward gradient boosting, real levels vs placebo levels, and what its best calls would have earned."""
import os
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LAB)
from pivbb import events as E  # noqa: E402

OUT = os.path.join(LAB, "results", "pivbb")
FEATS = ["s", "lvl", "nth_level", "nth_any", "stretch15", "stretch60", "bw", "squeeze", "mid_slope", "walk", "rsi", "mom4", "mom16",
         "atr15_d", "ny_hour", "dow", "from_open", "range_used", "trend20", "gap"]


def magnet():
    g = E.Gold()
    D = g.D
    real = E.build(g)
    # mirror every level around today's open: same distance, other side
    L = g.level_sets()
    orig = g.level_sets
    g.level_sets = lambda seed=None: {k: 2 * D.o.to_numpy() - v for k, v in L.items()}
    mir = E.build(g)
    g.level_sets = orig
    real, mir = real[real.t < "2022-01-01"], mir[mir.t < "2022-01-01"]
    days = real.day.nunique()
    rows = []
    for lv in ["D_P", "D_R1", "D_S1", "D_R2", "D_S2", "W_P", "W_R1", "W_S1", "M_P", "PDH", "PDL"]:
        a, b = real[real.level == lv].day.nunique(), mir[mir.level == lv].day.nunique()
        se = np.sqrt((a + b) / 2) / days
        rows.append({"level": lv, "touched_days_real": round(a / days, 3), "mirror": round(b / days, 3), "diff": round((a - b) / days, 3),
                     "z": round((a - b) / days / (se * np.sqrt(2)), 1)})
    print("1. share of days on which the level is touched: real level vs its mirror image around the day's open")
    print(pd.DataFrame(rows).to_string(index=False))


def prep(d):
    d = d[d.y25.isin([0, 1])].copy()
    d["lvl"] = d.level.astype("category").cat.set_categories(sorted(E.Gold.level_sets.__code__.co_consts and
                                                            ["D_S3", "D_S2", "D_S1", "D_P", "D_R1", "D_R2", "D_R3", "W_S2", "W_S1", "W_P", "W_R1",
                                                             "W_R2", "M_S1", "M_P", "M_R1", "PDH", "PDL"])).cat.codes
    d["year"] = pd.DatetimeIndex(d.t).year
    return d


def walk_forward(d, years=range(2017, 2022)):
    out = []
    for y in years:
        tr, te = d[d.year < y], d[d.year == y]
        m = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=200, l2_regularization=1.0,
                                           random_state=0).fit(tr[FEATS], tr.y25)
        out.append(te.assign(p=m.predict_proba(te[FEATS])[:, 1]))
    return pd.concat(out)


def model():
    ev = pd.read_parquet(os.path.join(OUT, "events.parquet"))
    ev = ev[ev.t < "2022-01-01"]
    real = walk_forward(prep(ev[ev.seed < 0]))
    auc = roc_auc_score(real.y25, real.p)
    print(f"\n2. model on real levels, each year predicted from the years before it (2017-2021): {len(real)} touches, "
          f"AUC {auc:.3f} (0.500 = coin toss) | bounce rate {real.y25.mean():.3f}")
    by = [roc_auc_score(g.y25, g.p) for _, g in real.groupby("year")]
    print("   AUC by year:", [round(a, 3) for a in by])
    aucs = []
    for sd in range(4):
        p = walk_forward(prep(ev[ev.seed == sd]))
        aucs.append(roc_auc_score(p.y25, p.p))
    print("   same model on placebo levels (4 seeds): AUC", [round(a, 3) for a in aucs])
    # what the model's calls earn: fade when it expects a bounce, follow when it expects a break
    # stake = the barrier (0.25 dATR); cost = spread at the touch + 0.8 bp of slippage
    real["cost_R"] = (real.spread + 0.8e-4 * real.px) / (0.25 * real.atr_d)
    real["q"] = pd.qcut(real.p, 10, labels=False)
    tab = real.groupby("q").agg(n=("y25", "size"), p_model=("p", "mean"), bounce=("y25", "mean"), cost_R=("cost_R", "mean"))
    tab["fade_net_R"] = 2 * tab.bounce - 1 - tab.cost_R
    tab["follow_net_R"] = 1 - 2 * tab.bounce - tab.cost_R
    print("   touches sorted in ten groups by the model's bounce probability:")
    print(tab.round(3).to_string())
    lo = real[real.q == 0]
    print(f"   group expected to break (lowest tenth): {len(lo)} trades in 5 years = {len(lo) / 5:.0f} a year, following nets "
          f"{(1 - 2 * lo.y25 - lo.cost_R).mean():+.3f} R per trade, by year:",
          {int(y): round(float((1 - 2 * g.y25 - g.cost_R).mean()), 3) for y, g in lo.groupby('year')})
    hi = real[real.q == 9]
    print(f"   group expected to bounce (highest tenth): {len(hi)} trades, fading nets {(2 * hi.y25 - 1 - hi.cost_R).mean():+.3f} R per trade, by year:",
          {int(y): round(float((2 * g.y25 - 1 - g.cost_R).mean()), 3) for y, g in hi.groupby('year')})
    # which information does the model use?
    from sklearn.inspection import permutation_importance
    d = prep(ev[ev.seed < 0])
    tr, te = d[d.year < 2020], d[d.year >= 2020]
    m = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=200, l2_regularization=1.0,
                                       random_state=0).fit(tr[FEATS], tr.y25)
    imp = permutation_importance(m, te[FEATS], te.y25, scoring="roc_auc", n_repeats=5, random_state=0)
    print("   what the model leans on (loss of AUC when the information is scrambled):",
          {f: round(float(v), 4) for f, v in sorted(zip(FEATS, imp.importances_mean), key=lambda z: -z[1])[:8]})


if __name__ == "__main__":
    magnet()
    model()
