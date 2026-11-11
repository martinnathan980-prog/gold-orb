"""Micro vs macro on gold: how predictable is the next move of a given size, and does it cover the costs?

For each decision minute (London + New York hours) and each move size B (in basis points of price:
2.5 bp is about 1 USD at today's 4,000 USD gold, 5 bp about 2 USD, ... 50 bp about 20 USD), the question
is: will price first go UP by B or DOWN by B? A gradient-boosting model sees ~45 pieces of context known
at that minute (momentum on many horizons, Bollinger / RSI on 1 and 5 minutes, volatility, clock, spread,
the Nasdaq, the euro and the yen) and is trained walk-forward (each year predicted from the years before).

Break-even accuracy = (B + cost) / (2 B). Costs: optimistic = the Raw spread + commission only (0.47 bp);
lab = + 0.3 bp slippage on the market entry and 1 bp on the half of exits that are stops (1.27 bp).
In-sample only (before 2022).

    python3 micro/study.py     -> results/micro/summary.json
"""
import json
import os
import sys

import numba as nb
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LAB)
import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
from goldlab.data import NY, trading_day  # noqa: E402

OUT = os.path.join(LAB, "results", "micro")
BARRIERS = [2.5, 5.0, 7.5, 12.5, 25.0, 50.0]          # bp of price
STEP = 3                                              # one decision every 3 minutes
COST_OPT, COST_LAB = 0.47, 1.27                       # bp per round trip


@nb.njit(cache=True)
def passage(c, h, l, idx, end, bp):
    out = np.zeros(len(idx), np.int8)
    dur = np.zeros(len(idx), np.int32)
    for k in range(len(idx)):
        i = idx[k]
        up = c[i] * (1.0 + bp * 1e-4)
        dn = c[i] * (1.0 - bp * 1e-4)
        for j in range(i + 1, end[k]):
            hu, hd = h[j] >= up, l[j] <= dn
            if hu and hd:
                out[k] = 2
                dur[k] = j - i
                break
            if hu:
                out[k] = 1
                dur[k] = j - i
                break
            if hd:
                out[k] = -1
                dur[k] = j - i
                break
    return out, dur


def rsi(c, n=14):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 * up / (up + dn).replace(0, np.nan)


def other(sym, index):
    """Log mid price of another market on gold's minute grid (last known quote, at most 3 minutes old)."""
    m = (r2.load(sym, end="2022-01-01") if sym in r2.SYMS else gl.load_m1(sym, end="2022-01-01"))
    p = np.log((m["bc"] + m["ac"]) / 2)
    r2.free()
    return p.reindex(index, method="ffill", tolerance=pd.Timedelta(minutes=3))


OTHERS = {"xauusd": ("us100", "eurusd", "usdjpy"), "us100": ("xauusd", "eurusd", "usdjpy"), "btcusd": ("us100", "xauusd", "eurusd")}


def build(sym="xauusd", barriers=BARRIERS):
    m1 = r2.load(sym, end="2022-01-01")
    idx = m1.index
    c = ((m1["bc"] + m1["ac"]) / 2)
    h = ((m1["bh"] + m1["ah"]) / 2).to_numpy()
    l = ((m1["bl"] + m1["al"]) / 2).to_numpy()
    spr_bp = ((m1["ac"] - m1["bc"]) / c * 1e4)
    r2.free()
    lc = np.log(c)
    r1 = lc.diff()
    sig = r1.rolling(240, min_periods=120).std()                     # usual 1-minute move (last 4 hours)
    F = pd.DataFrame(index=idx)
    for n in (1, 2, 3, 5, 10, 15, 30, 60, 120, 240):
        F[f"ret{n}"] = (lc - lc.shift(n)) / (sig * np.sqrt(n))
    rng = pd.Series(h - l, index=idx)
    F["bar_pos"] = ((c - l) / (rng.replace(0, np.nan))).fillna(0.5)
    F["bar_rng"] = rng / rng.rolling(60).mean()
    F["rsi1"] = rsi(c)
    for n, tag in ((20, "1"), (100, "5")):                           # Bollinger %B on about 1-minute and 5-minute scales
        mid, sd = c.rolling(n).mean(), c.rolling(n).std(ddof=0)
        F["pb" + tag] = (c - mid) / (2 * sd.replace(0, np.nan))
        F["bw" + tag] = sd / c * 1e4 / (sig * 1e4)
    c5 = c.rolling(5).mean()
    F["rsi5"] = rsi(c5, 70)
    F["vol_ratio"] = r1.rolling(15).std() / sig
    F["vol_level"] = sig * 1e4
    F["streak"] = np.sign(r1).groupby((np.sign(r1) != np.sign(r1).shift()).cumsum()).cumcount() * np.sign(r1)
    for n in (60, 240, 1380):
        hi, lo = c.rolling(n).max(), c.rolling(n).min()
        F[f"pos{n}"] = ((c - lo) / (hi - lo).replace(0, np.nan)).fillna(0.5)
    F["spread"] = spr_bp
    F["spread_ratio"] = spr_bp / spr_bp.rolling(1440, min_periods=300).median()
    ny = idx.tz_convert(NY)
    F["ny_min"] = ny.hour * 60 + ny.minute
    F["dow"] = ny.dayofweek
    for o_ in OTHERS[sym]:
        p = other(o_, idx)
        for n in (1, 5, 15):
            F[f"{o_}_{n}"] = (p - p.shift(n)) * 1e4 / (sig * 1e4 * np.sqrt(n))
    # decisions: every STEP minutes between 03:00 and 15:30 New York, Monday to Friday; the trade must end the same trading day
    td = trading_day(idx).asi8
    last_of_day = np.r_[np.flatnonzero(np.diff(td)), len(td) - 1]
    end_all = last_of_day[np.searchsorted(last_of_day, np.arange(len(td)))] + 1
    ok = (F.ny_min >= 180) & (F.ny_min < 930) & (F.dow < 5) & sig.notna() & (np.arange(len(idx)) % STEP == 0)
    pos = np.flatnonzero(ok.to_numpy())
    X = F.iloc[pos].astype("float32")
    Y = {}
    cv = c.to_numpy()
    for b in barriers:
        y, d = passage(cv, h, l, pos.astype(np.int64), end_all[pos].astype(np.int64), b)
        Y[b] = (y, d)
    return X, Y, idx[pos]


def study(sym="xauusd", BARRIERS=BARRIERS, COST_OPT=COST_OPT, COST_LAB=COST_LAB, first_year=2017, price=4000.0):
    os.makedirs(OUT, exist_ok=True)
    X, Y, t = build(sym, BARRIERS)
    year = t.year.to_numpy()
    print(f"decision minutes: {len(X)} ({len(X) / len(np.unique(t.date)):.0f} a day), features: {X.shape[1]}", flush=True)
    rows = []
    for b in BARRIERS:
        y, d = Y[b]
        use = (y == 1) | (y == -1)
        amb, none = float((y == 2).mean()), float((y == 0).mean())
        yy = (y[use] == 1).astype(int)
        Xu, yr = X[use], year[use]
        p = np.full(len(yy), np.nan)
        for Yr in range(first_year, 2022):
            tr, te = yr < Yr, yr == Yr
            if tr.sum() > 200_000:                       # enough to learn from, and keeps the fit fast
                sel = np.random.default_rng(0).choice(np.flatnonzero(tr), 200_000, replace=False)
            else:
                sel = np.flatnonzero(tr)
            m = HistGradientBoostingClassifier(max_depth=4, learning_rate=0.06, max_iter=250, min_samples_leaf=400,
                                               l2_regularization=1.0, random_state=0).fit(Xu.iloc[sel], yy[sel])
            p[te] = m.predict_proba(Xu[te])[:, 1]
        te = np.isfinite(p)
        acc = float(((p[te] > 0.5) == yy[te]).mean())
        auc = float(roc_auc_score(yy[te], p[te]))
        conf = np.abs(p[te] - 0.5)
        top = conf >= np.quantile(conf, 0.9)             # the tenth of the calls the model is most sure about
        acc_top = float(((p[te][top] > 0.5) == yy[te][top]).mean())
        days = len(np.unique(t[use][te].date))
        be_opt, be_lab = (b + COST_OPT) / (2 * b), (b + COST_LAB) / (2 * b)
        rows.append({"move_bp": b, "usd_at_4000": round(b * price / 1e4, 1), "minutes_median": float(np.median(d[use])),
                     "undecidable_pct": round(100 * amb, 1), "no_move_pct": round(100 * none, 1),
                     "accuracy_all": round(acc, 4), "auc": round(auc, 4), "accuracy_best_tenth": round(acc_top, 4),
                     "needed_optimistic": round(be_opt, 4), "needed_lab": round(be_lab, 4),
                     "net_bp_best_tenth_optimistic": round((2 * acc_top - 1) * b - COST_OPT, 2),
                     "net_bp_best_tenth_lab": round((2 * acc_top - 1) * b - COST_LAB, 2),
                     "best_tenth_trades_per_day": round(top.sum() / days, 1),
                     "accuracy_best_tenth_by_year": {int(Y_): round(float(((p[te][top & (yr[te] == Y_)] > 0.5) == yy[te][top & (yr[te] == Y_)]).mean()), 3)
                                                     for Y_ in range(first_year, 2022)}})
        print(json.dumps(rows[-1]), flush=True)
    json.dump(rows, open(os.path.join(OUT, "summary.json" if sym == "xauusd" else f"summary_{sym}.json"), "w"), indent=1)


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "xauusd"
    if which == "xauusd":
        study()
    elif which == "us100":       # spread 1.0 pt at 27,000 = 0.37 bp; lab = + 0.2 bp entry slippage + 0.5 bp on the half of exits that are stops
        study("us100", [2.5, 5.0, 7.5, 12.5, 25.0, 50.0], 0.37, 0.82, 2017, 27000.0)
    elif which == "btcusd":      # spread 22.5 USD at 76,000 = 2.96 bp; lab = + 0.5 bp + 0.75 bp
        study("btcusd", [10.0, 20.0, 40.0, 80.0, 160.0], 2.96, 4.21, 2019, 76000.0)
