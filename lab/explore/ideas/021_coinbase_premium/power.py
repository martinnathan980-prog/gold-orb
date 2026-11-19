"""Power check of idea 021 from the signal data alone (Coinbase and Bitstamp BTC/USD hourly closes): no traded price,
no return. Counts signal hours and the entries a one-position, 24-hour hold would take (stop ignored: a lower bound on
the number of trades, since a stop frees the position earlier).
    EXPLORE_CACHE=~/explore_data/idea_021 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B .../power.py"""
import json, os, sys
import numpy as np, pandas as pd
from kit import data

H = pd.Timedelta(hours=1)


def premium_z(cb, bs, win_h, min_obs):
    """z of p = log(Coinbase close / Bitstamp close), stamped at the bar END (close known then). Hours kept: a Coinbase
    candle exists (it omits hours without a trade) and the Bitstamp candle has volume > 0 (Bitstamp sends flat candles
    with volume 0: a stale price). Rolling window = the p values of the last win_h hours, current one included."""
    bsv = bs[bs.volume > 0]
    j = pd.concat([cb.close.rename("c"), bsv.close.rename("b")], axis=1, join="inner").dropna()
    p = np.log(j.c / j.b)
    p.index = p.index + H
    r = p.rolling(pd.Timedelta(hours=win_h), min_periods=min_obs)
    sd = r.std()
    z = (p - r.mean()) / sd
    return z[(sd > 0) & z.notna()]


def entries(known, hold_h=24):
    out, free = [], None
    for t in known:
        if free is None or t >= free:
            out.append(t); free = t + pd.Timedelta(hours=hold_h)
    return out


if __name__ == "__main__":
    cb = data.crypto_h1("coinbase", "btcusd")
    bs = data.crypto_h1("bitstamp", "btcusd", start="2015-07")
    res = {"coinbase": [str(cb.index[0]), str(cb.index[-1]), len(cb)], "bitstamp": [str(bs.index[0]), str(bs.index[-1]), len(bs)],
           "bitstamp_zero_volume_hours": int((bs.volume <= 0).sum())}
    for win in (96, 168, 336):
        z = premium_z(cb, bs, win, int(win * 0.7))
        z = z[z.index >= "2015-08-01"]
        z = z[~data.fp_closed(z.index)]
        for thr in (1.5, 2.0, 2.5):
            sig = z[(z >= thr) | (z <= -thr)]
            e = entries(list(sig.index))
            side = np.sign(sig.reindex(e)).to_numpy()
            yrs = pd.Series(1, index=pd.DatetimeIndex(e)).groupby(pd.DatetimeIndex(e).year).sum().to_dict()
            res[f"win{win}_thr{thr}"] = {"signal_hours": int(len(sig)), "entries_24h": len(e), "long": int((side > 0).sum()),
                                         "short": int((side < 0).sum()), "by_year": {int(k): int(v) for k, v in yrs.items()}}
    print(json.dumps(res, indent=1))
    json.dump(res, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "power.json"), "w"), indent=1)
