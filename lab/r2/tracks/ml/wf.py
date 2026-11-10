"""Walk-forward training of the candidate filter (track `ml`, round 2).

fit(name, recipe, tabs) trains, for every out-of-fold year Y, a model on the pooled candidates decided before
(1 Jan Y - PURGE_DAYS) and stores it with its thresholds; plus the frozen model on all in-sample candidates.
Everything the strategy needs is written to models/<name>.json (pure numbers: no pickle)."""
import json
import os

import numpy as np
import pandas as pd

import strategy as S

PURGE_DAYS = 5
OOF_YEARS = list(range(2016, 2022))
IS_END = pd.Timestamp("2022-01-01", tz="UTC")
NUM_FULL = ["brk", "bar", "body", "ret4", "ret14", "ret70", "chan", "vol", "pos", "seq", "opp", "pdd", "dret"]
DUM_FULL = [["hour", 8, 10], ["hour", 11, 12], ["hour", 13, 15], ["dow", 0, 0], ["dow", 4, 4]]
QS = ["0.5", "0.25", "0.4", "0.6"]


def pooled(tabs):
    d = pd.concat([tabs[s] for s in tabs], ignore_index=True)
    d = d[np.isfinite(d["R"])].copy()
    d["t_dec"] = pd.to_datetime(d["t_dec"], utc=True)
    return d.sort_values(["t_dec", "sym"]).reset_index(drop=True)


def _target(d, recipe):
    if recipe["type"] == "logit":
        return (d["R"].to_numpy() > 0).astype(float)
    lo, hi = recipe.get("clip_R", [-2.0, 4.0])
    return np.clip(d["R"].to_numpy(float), lo, hi)


def _fit_one(train, recipe):
    """Fit one model on a training table; returns the JSON spec (with thresholds from the TRAINING scores)."""
    y = _target(train, recipe)
    if recipe["type"] in ("ridge", "logit"):
        num = recipe["num"]
        X0 = train[num].to_numpy(float)
        mu = X0.mean(axis=0)
        sd = X0.std(axis=0)
        sd = np.where(sd > 0, sd, 1.0)
        spec = {"type": "linear", "num": num, "mean": mu.tolist(), "std": sd.tolist(), "clip": 4.0,
                "dummies": recipe.get("dummies", [])}
        X = S._design(train, spec)
        if recipe["type"] == "ridge":
            from sklearn.linear_model import Ridge
            m = Ridge(alpha=float(recipe["alpha"]), fit_intercept=True).fit(X, y)
            spec["coef"] = m.coef_.tolist()
            spec["intercept"] = float(m.intercept_)
        else:
            from sklearn.linear_model import LogisticRegression
            m = LogisticRegression(C=float(recipe["C"]), max_iter=2000).fit(X, y)
            spec["coef"] = m.coef_[0].tolist()
            spec["intercept"] = float(m.intercept_[0])
    elif recipe["type"] == "gbt":
        from sklearn.ensemble import GradientBoostingRegressor
        num = recipe["num"]
        m = GradientBoostingRegressor(max_depth=int(recipe["depth"]), n_estimators=int(recipe["trees"]),
                                      learning_rate=float(recipe["lr"]), min_samples_leaf=int(recipe["min_leaf"]),
                                      subsample=float(recipe["subsample"]), random_state=0)
        m.fit(train[num].to_numpy(float), y)
        trees = []
        for est in m.estimators_[:, 0]:
            t = est.tree_
            trees.append({"feat": t.feature.tolist(), "thr": t.threshold.tolist(),
                          "left": t.children_left.tolist(), "right": t.children_right.tolist(),
                          "val": t.value[:, 0, 0].tolist(), "depth": int(t.max_depth)})
        spec = {"type": "trees", "num": num, "init": float(m.init_.constant_[0, 0]), "lr": float(recipe["lr"]),
                "trees": trees}
    else:
        raise ValueError(recipe["type"])
    sc = S.score_model(train, spec)
    spec["thr"] = {q: float(np.quantile(sc, 1 - float(q))) for q in QS}
    if recipe["type"] != "logit":
        spec["thr"]["abs0"] = 0.0
    spec["q_default"] = recipe.get("q_default", "0.5")
    spec["n_train"] = int(len(train))
    return spec


def fit(name, recipe, tabs, gen, years=OOF_YEARS, save=True, shuffle_seed=None):
    """Walk-forward fit. Returns (model dict, pooled table with column `score` = out-of-fold score, NaN where
    no fold). shuffle_seed: permutation test (labels shuffled within market x year before anything else)."""
    d = pooled(tabs)
    if shuffle_seed is not None:
        rng = np.random.default_rng(shuffle_seed)
        d["R"] = d.groupby(["sym", "year"])["R"].transform(lambda x: rng.permutation(x.to_numpy()))
    d["score"] = np.nan
    for q in QS + ["abs0"]:
        d["pass_" + q] = False
    model = {"name": name, "recipe": recipe, "gen": gen, "purge_days": PURGE_DAYS, "folds": {}}
    for y in years:
        cut = pd.Timestamp(f"{y}-01-01", tz="UTC") - pd.Timedelta(days=PURGE_DAYS)
        train = d[d["t_dec"] < cut]
        test = d["year"] == y
        if len(train) < 500 or not test.any():
            continue
        spec = _fit_one(train, recipe)
        model["folds"][str(y)] = spec
        sc = S.score_model(d[test], spec)
        d.loc[test, "score"] = sc
        for q, th in spec["thr"].items():
            d.loc[test, "pass_" + q] = sc >= th
    train = d[d["t_dec"] < IS_END - pd.Timedelta(days=PURGE_DAYS)]
    model["frozen"] = _fit_one(train, recipe)
    if save:
        os.makedirs(S.MODEL_DIR, exist_ok=True)
        with open(os.path.join(S.MODEL_DIR, name + ".json"), "w") as f:
            json.dump(model, f)
    return model, d


def oof_summary(d, q):
    """Out-of-fold diagnostics on the candidate table (every candidate taken on its own)."""
    o = d[np.isfinite(d["score"])]
    out = {}
    for sym, g in list(o.groupby("sym")) + [("POOL", o)]:
        sel = g[g["pass_" + q]]
        ic = float(pd.Series(g["score"]).corr(pd.Series(g["R"].clip(-2, 4)), method="spearman"))
        out[sym] = {"n_all": int(len(g)), "R_all": round(float(g.R.mean()), 4), "n_sel": int(len(sel)),
                    "R_sel": round(float(sel.R.mean()), 4) if len(sel) else None,
                    "R_rej": round(float(g[~g["pass_" + q]].R.mean()), 4) if len(sel) < len(g) else None,
                    "ic": round(ic, 4)}
    return out
