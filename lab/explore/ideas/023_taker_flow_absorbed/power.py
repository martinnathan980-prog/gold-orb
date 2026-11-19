"""Idea 023 power check: signals of the main rule counted from the signal data alone (taker-buy share and the block's
own open/close, no price move after a signal, no return of a trade). Writes power.json.
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/023_taker_flow_absorbed/power.py"""
import json, os
os.environ.setdefault("EXPLORE_CACHE", os.path.expanduser("~/explore_data/idea_023"))
import numpy as np, pandas as pd
from kit import data

FOLDER = os.path.dirname(os.path.abspath(__file__))
H = pd.Timedelta(hours=1)


def blocks(k):
    """4-hour blocks (00, 04 ... 20 UTC) of Binance 1h klines; a block needs its 4 hours. Index = block END
    (the time its taker share and its close are known)."""
    g = k.groupby(k.index.floor("4h"))
    b = pd.DataFrame({"open": g.open.first(), "close": g.close.last(), "high": g.high.max(), "low": g.low.min(),
                      "vol": g.volume.sum(), "tb": g.taker_buy_base.sum(), "n": g.open.size()})
    b = b[(b.n == 4) & (b.vol > 0)]
    b.index = b.index + pd.Timedelta(hours=4)
    return b


def signals(b, win=180, thr=1.5):
    s = b.tb / b.vol
    r = s.rolling(win, min_periods=int(win * 0.7))
    z = (s - r.mean()) / r.std()
    ret = b.close / b.open - 1
    start_wd = (b.index - pd.Timedelta(hours=4)).dayofweek < 5            # block started Monday..Friday UTC
    ok = z.notna() & start_wd & ~data.fp_closed(b.index)
    short = ok & (z >= thr) & (ret <= 0)
    long_ = ok & (z <= -thr) & (ret >= 0)
    return pd.DataFrame({"known_at": b.index[short | long_],
                         "side": np.where(short[short | long_], -1, 1)})


def one_pos(t, hold_h=12):
    last, n = None, 0
    for x in t:
        if last is None or x >= last + pd.Timedelta(hours=hold_h):   # entry at known_at, exit at known_at + 12 h
            n += 1; last = x
    return n


if __name__ == "__main__":
    out = {}
    for sym in ("BTCUSDT", "ETHUSDT"):
        k = data.binance_klines(sym, "1h")
        b = blocks(k)
        res = {"blocks": int(len(b)), "first": str(b.index[0]), "last": str(b.index[-1])}
        for thr in (1.5, 2.0):
            s = signals(b, thr=thr)
            res[f"thr{thr}"] = {"signals": int(len(s)), "long": int((s.side == 1).sum()), "short": int((s.side == -1).sum()),
                                "one_position_12h": one_pos(s.known_at),
                                "by_year": s.known_at.dt.year.value_counts().sort_index().to_dict()}
        out[sym] = res
    tot = {f"thr{t}": sum(out[s][f"thr{t}"]["one_position_12h"] for s in out) for t in (1.5, 2.0)}
    out["basket_one_position"] = tot
    print(json.dumps(out, indent=1, default=str))
    json.dump(out, open(os.path.join(FOLDER, "power.json"), "w"), indent=1, default=str)
