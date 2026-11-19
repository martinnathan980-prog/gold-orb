"""Idea 043: the Korean premium signal (shared by power.py and run.py; attack.py does NOT import it).
k(T) = Upbit KRW-BTC price / (Bitstamp BTC/USD x KRW per USD, last H.10 rate published) - 1, at T = 00:00 UTC.
  - Upbit daily candle dated D (00:00 UTC D to 00:00 UTC D+1; trade_price = last trade of the day) is complete at
    D+1 00:00 UTC: item 'up' indexed by the candle's open, row length 1 day.
  - Bitstamp hourly candle opening at T-1h (close = last trade before T) is complete at T: item 'bs', row length 1 h.
  - FRED DEXKOUS (H.10 noon buying rate in New York) observed on day D is published in the weekly H.10 release on the
    Monday after D's week (Tuesday after a Monday holiday) at 16:15 New York: known on the Wednesday 00:00 UTC after
    the Friday that ends D's week (item 'won', indexed by its known time, row length 0).
Signals: T on Monday to Friday 00:00 UTC (all in FP's crypto trading hours) where k(T) >= thr; side -1 (sell)."""
import os
import numpy as np
import pandas as pd
from kit import data

UPBIT_CSV = os.path.expanduser("~/explore_data/idea_043/upbit/krw_btc_daily.csv")
START = pd.Timestamp("2017-09-26", tz="UTC")       # first T with an Upbit candle complete (that of 2017-09-25)
D1, H1 = pd.Timedelta(days=1), pd.Timedelta(hours=1)


def h10_known(dates):
    d = pd.DatetimeIndex(dates).normalize()
    fri = d + pd.to_timedelta(np.clip(4 - np.asarray(d.weekday), 0, None), unit="D")   # weekend obs (none in DEXKOUS) stay put
    return (fri + pd.Timedelta(days=5)).tz_localize("UTC")


def load_inputs():
    u = pd.read_csv(UPBIT_CSV)
    up = pd.DataFrame({"krw": u.trade_price.to_numpy(float)},
                      index=pd.DatetimeIndex(pd.to_datetime(u.candle_date_time_utc)).tz_localize("UTC"))
    up = data.cut(up)
    bs = data.crypto_h1("bitstamp", "btcusd", start="2017-09")
    won = data.fred("DEXKOUS", known=h10_known, start="2017-01-01")
    return {"up": up, "bs": bs, "won": won}


def premium(d):
    """k at each weekday 00:00 UTC from START, NaN where an input is missing. Index = T (known time)."""
    up, bs, won = d["up"], d["bs"], d["won"]
    upk = pd.Series(up["krw"].to_numpy(float), index=up.index + D1)          # known at the candle's end
    bsk = pd.Series(bs["close"].to_numpy(float), index=bs.index + H1)        # known at the candle's end
    if len(upk) == 0:
        return pd.Series(dtype=float)
    days = pd.date_range(START, upk.index.max(), freq="D", tz="UTC")
    days = days[days.weekday < 5]
    krw = upk.reindex(days)                                                  # the candle ending exactly at T
    usd = bsk.reindex(days)                                                  # the Bitstamp hour ending exactly at T
    fx = pd.Series(data.asof_join(days, won), index=days)                    # last H.10 rate published by T
    return krw / (usd * fx) - 1.0


def make_build(thr):
    def build(d):
        k = premium(d)
        k = k[np.isfinite(k.to_numpy()) & (k.to_numpy() >= thr)]
        return pd.DataFrame({"known_at": k.index, "side": np.full(len(k), -1, dtype=int)})
    return build
