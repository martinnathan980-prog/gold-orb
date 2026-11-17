"""Shared fetch helper of the open search. Cache: ~/explore_data (never committed). Every reader cuts at 2021-12-31.
dukascopy_h1(symbol): hourly BID candles from Dukascopy, decoded (24-byte big-endian records: uint32 seconds from the
month start, open, close, low, high as uint32 points, float32 volume), divided by the symbol's point (checked by
magnitude against known prices), returned as a UTC-indexed DataFrame cut at 2021-12-31 23:59."""
import lzma, os, struct, time, urllib.request
import numpy as np
import pandas as pd

CACHE = os.path.expanduser("~/explore_data")
CUT = pd.Timestamp("2022-01-01", tz="UTC")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
POINT = {"XAUUSD": 1e3, "USDJPY": 1e3, "EURJPY": 1e3, "USA500IDXUSD": 1e3, "USATECHIDXUSD": 1e3, "DEUIDXEUR": 1e3,
         "LIGHTCMDUSD": 1e3, "EURUSD": 1e5, "GBPUSD": 1e5, "AUDUSD": 1e5, "USDCHF": 1e5, "XAGUSD": 1e3}


def _get(url, tries=8):
    for k in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60).read()
        except Exception as e:  # 429/503/network: growing waits
            if "404" in str(e):
                return b""
            time.sleep(2 * (k + 1))
    raise RuntimeError("failed " + url)


def _month(sym, y, m, side="BID"):
    d = os.path.join(CACHE, "duka", sym)
    os.makedirs(d, exist_ok=True)
    f = os.path.join(d, f"{y}_{m:02d}_{side}.bi5")
    if not os.path.exists(f):
        raw = _get(f"https://datafeed.dukascopy.com/datafeed/{sym}/{y}/{m - 1:02d}/{side}_candles_hour_1.bi5")
        time.sleep(1.0)
        open(f, "wb").write(raw)
    raw = open(f, "rb").read()
    if not raw:
        return None
    b = lzma.decompress(raw)
    rec = np.frombuffer(b, dtype=">u4,>u4,>u4,>u4,>u4,>f4")
    t0 = pd.Timestamp(year=y, month=m, day=1, tz="UTC")
    p = POINT[sym]
    return pd.DataFrame({"open": rec["f1"] / p, "high": rec["f4"] / p, "low": rec["f3"] / p, "close": rec["f2"] / p,
                         "volume": rec["f5"].astype(float)},
                        index=t0 + pd.to_timedelta(rec["f0"].astype(np.int64), unit="s"))


def dukascopy_h1(sym, start=2013, end_year=2021, side="BID"):
    end_year = min(end_year, 2021)  # never past the in-sample cut
    parts = [_month(sym, y, m, side) for y in range(start, end_year + 1) for m in range(1, 13)]
    df = pd.concat([p for p in parts if p is not None]).sort_index()
    df = df[(df.index < CUT) & (df.volume > 0)]
    return df


if __name__ == "__main__":
    import sys
    for s in sys.argv[1:]:
        d = dukascopy_h1(s)
        print(s, len(d), d.index[0], d.index[-1], d.close.iloc[[0, -1]].round(3).tolist(), flush=True)
