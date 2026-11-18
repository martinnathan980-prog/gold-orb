"""Hourly BTC/USD and ETH/USD candles from Bitfinex's public API (scout/sources.md 13; lead's ruling b: crypto trades
before Binance's 2017-08 start may be priced on a dollar venue). Cached in ~/explore_data/bitfinex (never in git).
The kit has no Bitfinex reader: this file adds one on top of kit.data (period cut, FP crypto closure removed).
Bars: UTC bar-open index, open high low close volume, price_is 'mid' (trade prices, as Binance). Hours without a trade
are absent (as in the API)."""
import json, os, time, urllib.request
import pandas as pd
from kit import data as D

KEYS = {"btcusd": ("trade:1h:tBTCUSD", "2014-06-01"), "ethusd": ("trade:1h:tETHUSD", "2016-03-09")}
END = "2021-12-31 23:00"
UA = {"User-Agent": "gold-orb-research/1.0"}


def _fetch(key, start):
    s = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    e = int(pd.Timestamp(END, tz="UTC").timestamp() * 1000)
    out = []
    while s <= e:
        url = f"https://api-pub.bitfinex.com/v2/candles/{key}/hist?limit=10000&start={s}&end={e}&sort=1"
        for k in range(5):
            try:
                j = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read())
                break
            except Exception:
                time.sleep(5 * (k + 1))
        else:
            raise RuntimeError(f"bitfinex {key}: failed at {s}")
        if not j:
            break
        out += j
        s = j[-1][0] + 1
        time.sleep(2.0)
    d = pd.DataFrame(out, columns=["t", "open", "close", "high", "low", "volume"]).drop_duplicates("t").sort_values("t")
    d = d[d.t <= e]
    d.index = pd.to_datetime(d.pop("t"), unit="ms", utc=True)
    d.index.name = "time"
    return d[["open", "high", "low", "close", "volume"]].astype(float)


def load(fp_key):
    key, start = KEYS[fp_key]
    cdir = os.path.join(D.cache_dir(), "bitfinex"); os.makedirs(cdir, exist_ok=True)
    p = os.path.join(cdir, f"{fp_key}_1h.parquet")
    if not os.path.isfile(p):
        _fetch(key, start).to_parquet(p)
    b = pd.read_parquet(p)
    b = b[b.index < pd.Timestamp("2022-01-01", tz="UTC")]
    b = D.cut(b)
    b = D.fp_hours(fp_key, b)
    b.attrs["price_is"], b.attrs["market"], b.attrs["source"] = "mid", fp_key, "bitfinex 1h trade candles"
    return b


if __name__ == "__main__":
    import sys
    for k in sys.argv[1:] or KEYS:
        b = load(k)
        print(k, len(b), b.index.min(), b.index.max())
