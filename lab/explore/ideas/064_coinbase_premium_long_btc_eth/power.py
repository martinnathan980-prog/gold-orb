"""Power check of idea 064 from the signal data alone (Coinbase and Bitstamp hourly closes of btcusd and ethusd): no
traded price, no return. Counts the LONG signal hours (z >= thr) and the entries a one-position 24-hour hold would take
(stop ignored: a lower bound on the trades, since a stop frees the position earlier), by year and by quarter.
    EXPLORE_CACHE=~/explore_data/idea_064 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B .../power.py"""
import json, os
os.environ.setdefault("EXPLORE_CACHE", os.path.expanduser("~/explore_data/idea_064"))
import numpy as np, pandas as pd
from kit import data

H = pd.Timedelta(hours=1)
START = {"btcusd": "2015-08-01", "ethusd": "2015-08-01"}


def premium_z(cb, bs, win_h, min_obs):
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
    res = {}
    for mk, bs_start in (("btcusd", "2015-07"), ("ethusd", None)):
        cb = data.crypto_h1("coinbase", mk) if mk == "btcusd" else data.crypto_h1("coinbase", mk, start="2017-07")  # Bitstamp ETH starts 2017-08
        bs = data.crypto_h1("bitstamp", mk, start=bs_start) if bs_start else data.crypto_h1("bitstamp", mk)
        r = {"coinbase": [str(cb.index[0]), str(cb.index[-1]), len(cb)], "bitstamp": [str(bs.index[0]), str(bs.index[-1]), len(bs)],
             "bitstamp_zero_volume_hours": int((bs.volume <= 0).sum())}
        for win in (96, 168, 336):
            z = premium_z(cb, bs, win, int(win * 0.7))
            z = z[z.index >= START[mk]]
            z = z[~data.fp_closed(z.index)]
            if win == 168:
                r["first_z"] = str(z.index[0])
            for thr in (1.5, 2.0, 2.5):
                if win != 168 and thr != 2.0:
                    continue
                sig = z[z >= thr]
                e = pd.DatetimeIndex(entries(list(sig.index)))
                r[f"win{win}_thr{thr}"] = {"signal_hours": int(len(sig)), "long_entries_24h": len(e),
                    "by_year": {int(k): int(v) for k, v in pd.Series(1, index=e).groupby(e.year).sum().items()},
                    "by_quarter": {f"{k[0]}Q{k[1]}": int(v) for k, v in pd.Series(1, index=e).groupby([e.year, e.quarter]).sum().items()}}
        res[mk] = r
    print(json.dumps(res, indent=1))
    json.dump(res, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "power.json"), "w"), indent=1)
