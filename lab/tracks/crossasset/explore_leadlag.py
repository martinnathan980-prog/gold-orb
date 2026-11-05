"""Descriptive IS-only analysis (no trading rule, no trial): cross-asset lead-lag for gold.

Master index = gold bars. Predictor closes are reindexed on the gold bar START labels (same
interval, both closed at the decision time = nominal bar end).  Features over the last L bars:
  u_L   USD basket = mean(dlog EURUSD, dlog GBPUSD, -dlog USDJPY)  (u > 0 = weaker dollar)
  res_L gold residual = gold_L - beta*u_L (beta: rolling, past only)
  jpy_L, dax_L, oil_L, gold_L
Target: gold log return from close t to close t+k (bp).  Compared to ~5.7 bp IS round-trip cost.
"""
import warnings

import numpy as np
import pandas as pd

from common import load_bars

warnings.filterwarnings("ignore")
PRED = ["eurusd", "gbpusd", "usdjpy", "deuidxeur", "lightcmdusd"]


def panel(rule):
    g = load_bars("xauusd", rule)
    end = pd.Timestamp("2022-01-01", tz="UTC") if rule != "D" else pd.Timestamp("2022-01-01")
    g = g[g.index < end]
    p = pd.DataFrame({"xauusd": np.log(g["c"])})
    for s in PRED:
        b = load_bars(s, rule)
        p[s] = np.log(b["c"]).reindex(p.index)
    return p


def nw_t(y, x, L=10):
    x = x - x.mean()
    yc = y - y.mean()
    b = (x * yc).sum() / (x * x).sum()
    e = yc - b * x
    gg = x * e
    s = (gg * gg).sum()
    for l in range(1, L + 1):
        s += 2 * (1 - l / (L + 1)) * (gg[l:] * gg[:-l]).sum()
    return b, b / (np.sqrt(s) / (x * x).sum())


def feats(p, L, beta_win):
    d = p.diff(L) * 1e4
    f = pd.DataFrame(index=p.index)
    f["gold"] = d["xauusd"]
    f["u"] = (d["eurusd"] + d["gbpusd"] - d["usdjpy"]) / 3
    f["jpy"] = d["usdjpy"]
    f["dax"] = d["deuidxeur"]
    f["oil"] = d["lightcmdusd"]
    r1 = p.diff() * 1e4
    u1 = (r1["eurusd"] + r1["gbpusd"] - r1["usdjpy"]) / 3
    g1 = r1["xauusd"]
    mp = beta_win // 2
    cov = (g1 * u1).rolling(beta_win, min_periods=mp).mean() - \
        g1.rolling(beta_win, min_periods=mp).mean() * u1.rolling(beta_win, min_periods=mp).mean()
    beta = (cov / u1.rolling(beta_win, min_periods=mp).var()).shift(L)
    f["res"] = f["gold"] - beta * f["u"]
    return f, beta


def analyse(rule, beta_win, Ls, horizons, qs=0.99):
    p = panel(rule)
    print(f"\n######## {rule}: bars={len(p)}")
    for L in Ls:
        f, beta = feats(p, L, beta_win)
        cc = f.corr()["gold"].round(3).to_dict()
        print(f"--- lookback L={L} bars | median beta={beta.median():.2f} | contemporaneous corr: {cc}")
        rows = []
        for k in horizons:
            fut = (p["xauusd"].shift(-k) - p["xauusd"]) * 1e4
            for name in ["u", "res", "gold", "jpy", "dax", "oil"]:
                x = f[name]
                m = x.notna() & fut.notna()
                if m.sum() < 500:
                    continue
                b, t = nw_t(fut[m].to_numpy(), x[m].to_numpy(), L=max(10, k + L))
                xs, fu = x[m], fut[m]
                hi, lo = xs > xs.quantile(qs), xs < xs.quantile(1 - qs)
                rows.append({"L": L, "k": k, "x": name, "slope": round(b, 4), "t_nw": round(t, 2),
                             "corr": round(np.corrcoef(xs, fu)[0, 1], 4),
                             "fut|hi": round(fu[hi].mean(), 1), "fut|lo": round(fu[lo].mean(), 1),
                             "hi-lo": round(fu[hi].mean() - fu[lo].mean(), 1), "n_tail": int(hi.sum()),
                             "sd_fut": round(fu.std(), 1)})
        print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    analyse("5min", 288 * 20, [1, 3], [1, 3, 6, 12])
    analyse("15min", 96 * 20, [1, 4], [1, 4, 8])
    analyse("1h", 24 * 60, [1, 4, 12], [1, 4, 8, 24])
    analyse("D", 120, [1, 3], [1, 3, 5], qs=0.95)
