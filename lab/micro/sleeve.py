"""The smallest scale that pays its costs, as a trading rule: short moves (about an hour) on the Nasdaq.

From micro/study.py: at every scale a gradient-boosting model's most confident calls are right 53-56 % of
the time; that covers the costs only from moves of about 25 bp on the Nasdaq (about 70 points, about an
hour). This module turns it into a rule for the lab engine:

  every 3 minutes of the London / New York day the model gives P(up B before down B); when it is among its
  10 % most confident calls, enter at market on the next minute in that direction, stop B, target B,
  everything closed at 16:50 New York; one position at a time.

Walk-forward: a decision in year Y (2017-2021) uses the model trained on the years before Y; from 2022 on
the model trained on everything before 2022 (frozen). The confidence threshold is the 90th percentile of
the out-of-fold |p - 0.5| of 2017-2021, frozen too. Nothing is fitted inside make_orders.

    python3 micro/sleeve.py fit us100 25      -> micro/models/us100_B25.joblib
    python3 micro/sleeve.py is us100 25       in-sample engine metrics (logged)
    python3 micro/sleeve.py val us100 25      single validation look (logged)
"""
import os
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LAB)
import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
from goldlab.data import NY  # noqa: E402
from micro.study import OTHERS, passage, rsi  # noqa: E402

MODELS = os.path.join(LAB, "micro", "models")
_others = {}


def _other(sym):
    """Log mid price of another market, whole research period (used as a predictor only)."""
    if sym not in _others:
        m = r2.load(sym) if sym in r2.SYMS else gl.load_m1(sym)
        _others[sym] = np.log((m["bc"] + m["ac"]) / 2)
        r2.free(sym)
    return _others[sym]


def features(m1, sym):
    """Causal features at each M1 close (mid prices only, so that wider or zero spreads give the same signals)."""
    idx = m1.index
    c = (m1["bc"] + m1["ac"]) / 2
    h = ((m1["bh"] + m1["ah"]) / 2).to_numpy()
    l = ((m1["bl"] + m1["al"]) / 2).to_numpy()
    lc = np.log(c)
    r1 = lc.diff()
    sig = r1.rolling(240, min_periods=120).std()
    F = pd.DataFrame(index=idx)
    for n in (1, 2, 3, 5, 10, 15, 30, 60, 120, 240):
        F[f"ret{n}"] = (lc - lc.shift(n)) / (sig * np.sqrt(n))
    rng = pd.Series(h - l, index=idx)
    F["bar_pos"] = ((c - l) / rng.replace(0, np.nan)).fillna(0.5)
    F["bar_rng"] = rng / rng.rolling(60).mean()
    F["rsi1"] = rsi(c)
    for n, tag in ((20, "1"), (100, "5")):
        mid, sd = c.rolling(n).mean(), c.rolling(n).std(ddof=0)
        F["pb" + tag] = (c - mid) / (2 * sd.replace(0, np.nan))
        F["bw" + tag] = sd / c / sig
    F["rsi5"] = rsi(c.rolling(5).mean(), 70)
    F["vol_ratio"] = r1.rolling(15).std() / sig
    F["vol_level"] = sig * 1e4
    sg = np.sign(r1)
    F["streak"] = sg.groupby((sg != sg.shift()).cumsum()).cumcount() * sg
    for n in (60, 240, 1380):
        hi, lo = c.rolling(n).max(), c.rolling(n).min()
        F[f"pos{n}"] = ((c - lo) / (hi - lo).replace(0, np.nan)).fillna(0.5)
    ny = idx.tz_convert(NY)
    F["ny_min"] = ny.hour * 60 + ny.minute
    F["dow"] = ny.dayofweek
    for o_ in OTHERS[sym]:
        p = _other(o_).reindex(idx, method="ffill", tolerance=pd.Timedelta(minutes=3))
        for n in (1, 5, 15):
            F[f"{o_}_{n}"] = (p - p.shift(n)) / (sig * np.sqrt(n))
    ok = ((F.ny_min >= 180) & (F.ny_min < 930) & (F.dow < 5) & sig.notna() & (F.ny_min % 3 == 0)).to_numpy()
    return F.astype("float32"), c.to_numpy(), h, l, ok


def _model():
    return HistGradientBoostingClassifier(max_depth=4, learning_rate=0.06, max_iter=250, min_samples_leaf=400, l2_regularization=1.0, random_state=0)


def fit(sym, B):
    m1 = r2.load(sym, end="2022-01-01")                    # in-sample only
    F, c, h, l, ok = features(m1, sym)
    idx = m1.index
    pos = np.flatnonzero(ok)
    exit_i = gl.exit_index(m1, (idx[pos].tz_convert(NY).normalize() + pd.Timedelta(hours=16, minutes=50)).tz_convert("UTC"))
    y, _ = passage(c, h, l, pos.astype(np.int64), np.maximum(exit_i, pos + 1).astype(np.int64), float(B))
    use = (y == 1) | (y == -1)
    X, yy, yr = F.iloc[pos[use]], (y[use] == 1).astype(int), idx[pos[use]].year.to_numpy()
    models, oof = {}, []
    for Y in list(range(2017, 2022)) + [2022]:
        tr = np.flatnonzero(yr < Y)
        sel = np.random.default_rng(0).choice(tr, min(len(tr), 200_000), replace=False)
        models[Y] = _model().fit(X.iloc[sel], yy[sel])
        if Y < 2022:
            te = yr == Y
            oof.append(np.abs(models[Y].predict_proba(X[te])[:, 1] - 0.5))
    thr = float(np.quantile(np.concatenate(oof), 0.9))
    os.makedirs(MODELS, exist_ok=True)
    joblib.dump({"models": models, "thr": thr, "cols": list(F.columns), "B": float(B), "sym": sym}, os.path.join(MODELS, f"{sym}_B{B:g}.joblib"))
    print(f"{sym} B={B:g} bp: fitted on {len(X)} in-sample decisions | threshold |p-0.5| >= {thr:.4f}")


_loaded = {}


def make_orders(m1, sym="us100", B=25.0):
    key = f"{sym}_B{B:g}"
    if key not in _loaded:
        _loaded[key] = joblib.load(os.path.join(MODELS, key + ".joblib"))
    M = _loaded[key]
    F, c, h, l, ok = features(m1, sym)
    idx = m1.index
    pos = np.flatnonzero(ok)
    pos = pos[pos < len(idx) - 2]
    yr = idx[pos].year.to_numpy()
    p = np.full(len(pos), np.nan)
    for Y in np.unique(yr):
        if Y < 2017:
            continue                                        # no model existed yet
        m = M["models"][min(int(Y), 2022)]
        sel = yr == Y
        p[sel] = m.predict_proba(F.iloc[pos[sel]][M["cols"]])[:, 1]
    go = np.isfinite(p) & (np.abs(p - 0.5) >= M["thr"])
    pos, p = pos[go], p[go]
    side = np.where(p > 0.5, 1, -1)
    dist = c[pos] * B * 1e-4
    xi = gl.exit_index(m1, (idx[pos].tz_convert(NY).normalize() + pd.Timedelta(hours=16, minutes=50)).tz_convert("UTC"))
    o = pd.DataFrame({"entry_i": pos + 1, "side": side, "etype": 0, "stop_dist": dist, "target_dist": dist, "exit_i": xi, "p": p})
    return o[o.exit_i > o.entry_i].reset_index(drop=True)


if __name__ == "__main__":
    cmd, sym, B = sys.argv[1], sys.argv[2], float(sys.argv[3])
    params = {"sym": sym, "B": B}
    if cmd == "fit":
        fit(sym, B)
    elif cmd == "is":
        ev = r2.evaluate(sym, make_orders, params)
        r2.log_trial("micro", sym, params, ev)
        i, s, g, e = ev["is"], ev["is_stress"], ev["is_gross"], ev["is_every_signal"]
        print(f"IS {sym} B={B:g}: n {i['n']} ({i['trades_per_year']}/yr) win {i['win_rate']} PF {i['pf']} t {i['t_stat']} exp {i['expectancy_R']} R | years {i['years_pos']} "
              f"{i['by_year_R']} | long {i['long_R']} short {i['short_R']} | stress PF {s['pf']} | gross exp {g['expectancy_R']} | every-signal exp {e['expectancy_R']} | "
              f"hold {i['avg_hold_h']} h | criteria {r2.is_criteria(ev)}")
    elif cmd == "val":
        v = r2.validate(sym, make_orders, params, "micro", f"ml_{sym}_B{B:g}")
        r = v["val"]
        print(f"VAL {sym} B={B:g}: n {r['n']} ({r['trades_per_year']}/yr) win {r['win_rate']} PF {r['pf']} t {r['t_stat']} exp {r['expectancy_R']} R | years {r['years_pos']} "
              f"{r['by_year_R']} | long {r['long_R']} short {r['short_R']} | stress PF {v['val_stress']['pf']} | every-signal exp {v['val_every_signal']['expectancy_R']} | "
              f"criteria {v['val_criteria']}")
