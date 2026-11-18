"""Synthetic hourly bars for the tests and the template (no market data). Prices are a geometric random walk; the
calendar imitates the market's hours: 'fx' (Sunday 17:00 to Friday 17:00 New York, 24 h), 'index' (same, with a daily
break 17:00-18:00 New York), 'crypto' (24/7, then FP's weekend closure removed with data.fp_hours)."""
import numpy as np
import pandas as pd

from . import data

KIND = {"xauusd": "index", "xagusd": "index", "us100": "index", "us500": "index", "us30": "index", "ger40": "index",
        "btcusd": "crypto", "ethusd": "crypto"}
PRICE = {"xauusd": 1500.0, "xagusd": 20.0, "us100": 9000.0, "us500": 3000.0, "us30": 26000.0, "ger40": 12000.0,
         "btcusd": 20000.0, "ethusd": 1000.0, "eurusd": 1.15, "gbpusd": 1.3, "usdjpy": 110.0, "audusd": 0.75,
         "usdcad": 1.3, "usdchf": 0.95, "nzdusd": 0.7, "eurjpy": 125.0}


def calendar(kind, start="2013-01-01", end="2022-01-01"):
    t = pd.date_range(start, end, freq="h", tz="UTC", inclusive="left")
    if kind == "crypto":
        return t
    ny = t.tz_convert("America/New_York")
    s = ny + pd.Timedelta(hours=7)                       # trading-day clock: Sunday 17:00 NY = Monday 00:00
    ok = s.dayofweek < 5
    if kind == "index":
        ok &= ny.hour != 17
    return t[ok]


def bars(key, start="2013-01-01", end="2022-01-01", vol_h=0.0015, seed=0, drift_h=0.0, edge=None):
    """Bid bars for FP key `key`. edge: optional function(index) -> expected log return of each bar (planted edge).
    Each hour is a continuous Brownian path in log price: open = the previous close, close = open + x with
    x ~ N(mu, vol_h^2), and the high and low are drawn from the exact law of the path's maximum and minimum given x
    (Brownian bridge: P(max > m | x) = exp(-2 m (m - x) / vol_h^2)). So a wick is a price the path really reached and
    a stop or target touched inside a bar is crossed exactly at its level, with no free return afterwards: gross R is
    zero-mean for any stop or target (test_kit V6). The bar's max and min are drawn independently given x (their joint
    law matters only when the stop and the target are both touched in one bar). Calendar gaps carry no price jump."""
    rng = np.random.default_rng(seed)
    kind = KIND.get(key, "fx")
    t = calendar(kind, start, end)
    n = len(t)
    mu = np.full(n, drift_h) + (edge(t) if edge is not None else 0.0)
    x = mu + vol_h * rng.standard_normal(n)
    u = 1.0 - rng.random((n, 2))                                     # in (0, 1]
    up = (x + np.sqrt(x * x - 2 * vol_h ** 2 * np.log(u[:, 0]))) / 2  # >= max(0, x)
    dn = (x - np.sqrt(x * x - 2 * vol_h ** 2 * np.log(u[:, 1]))) / 2  # <= min(0, x)
    lo0 = np.log(PRICE[key]) + np.r_[0.0, np.cumsum(x)[:-1]]        # log open of each hour
    o, c, h, l = np.exp(lo0), np.exp(lo0 + x), np.exp(lo0 + up), np.exp(lo0 + dn)
    df = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": rng.integers(50, 500, n).astype(float)},
                      index=t)
    df = data.fp_hours(key, df)
    df.attrs["price_is"] = "mid" if kind == "crypto" else "bid"
    return df


def signal_world(key, seed=0, edge=0.0, hour_utc=14, hold_h=5, p_signal=1.0, start="2013-01-01", end="2022-01-01"):
    """A market and a daily signal: on each weekday D a value x_D = +1/-1 is known at D hour_utc:00 UTC; the next
    hold_h hourly bars drift by edge * x_D per bar (edge = 0: pure noise). Returns (bars, signals) with signals
    (known_at, side = x_D) on a random share p_signal of the days."""
    rng = np.random.default_rng(seed + 10_000)
    days = pd.bdate_range(start, end, inclusive="left", tz="UTC")
    x = pd.Series(rng.choice([-1, 1], len(days)), index=days)

    def drift(t):
        d = t.normalize()
        xs = x.reindex(d).to_numpy()
        h = t.hour
        on = (h >= hour_utc) & (h < hour_utc + hold_h) & np.isfinite(xs)
        return np.where(on, edge * np.nan_to_num(xs), 0.0)

    b = bars(key, start, end, seed=seed, edge=drift)
    take = rng.random(len(days)) < p_signal
    sig = pd.DataFrame({"known_at": days[take] + pd.Timedelta(hours=hour_utc), "side": x.to_numpy()[take],
                        "market": key})
    return b, sig.reset_index(drop=True)


def ten_fixture(folder, seed=0):
    """Synthetic files in the format of lab/results/r2/recalc/trades (entry_time, exit_time, R), 2013-2023, for the
    correlation tests: written to `folder` (never the lab's)."""
    import os
    from .stats import TEN
    rng = np.random.default_rng(seed)
    os.makedirs(folder, exist_ok=True)
    for n, s in TEN:
        e = pd.DatetimeIndex(np.sort(rng.choice(pd.date_range("2013-01-01", "2023-06-01", freq="h", tz="UTC"), 400,
                                                replace=False)))
        t = pd.DataFrame({"entry_time": e, "exit_time": e + pd.Timedelta(hours=30), "R": rng.standard_normal(400)})
        t.to_parquet(os.path.join(folder, f"{n}__{s}.parquet"))
    return folder


def d1_bars(start="2016-01-01", end="2021-12-31", vol_d=0.015, seed=0, price=50.0, drift_d=None, night=0.35,
            with_shares=True):
    """Kit v2.2: synthetic DAILY session bars of a US share, in the format of the prepared files (scout/prices_d1.py):
    UTC index = the session's open (09:30 New York) for every session of data.us_sessions (holidays and 13:00 half
    days by rule), open high low close, volume = the session's length in minutes (390 / 210), shares. Each session: an
    overnight gap N(0, (night x vol_d)^2) from the previous close to the open, then an intraday Brownian path from the
    open to the close with variance (1 - night^2) x vol_d^2 x minutes / 390, high and low drawn from the exact law of
    the path's max and min given its move (as bars()). drift_d: optional array (one per session) of expected log
    return added to the intraday move (a planted edge). Bars are cut at the period end like every reader."""
    rng = np.random.default_rng(seed)
    cal = data.us_sessions(start, end)
    n = len(cal)
    mins = cal.minutes.to_numpy(float)
    sd_in = vol_d * np.sqrt(max(1 - night ** 2, 0.0) * mins / 390.0)
    g = night * vol_d * rng.standard_normal(n)
    mu = np.zeros(n) if drift_d is None else np.asarray(drift_d, float)
    x = mu + sd_in * rng.standard_normal(n)
    u = 1.0 - rng.random((n, 2))
    up = (x + np.sqrt(x * x - 2 * sd_in ** 2 * np.log(u[:, 0]))) / 2
    dn = (x - np.sqrt(x * x - 2 * sd_in ** 2 * np.log(u[:, 1]))) / 2
    lo = np.log(price) + np.cumsum(g) + np.r_[0.0, np.cumsum(x)[:-1]]       # log open of each session
    df = pd.DataFrame({"open": np.exp(lo), "high": np.exp(lo + up), "low": np.exp(lo + dn), "close": np.exp(lo + x),
                       "volume": mins}, index=pd.DatetimeIndex(cal.open_utc))
    if with_shares:
        df["shares"] = rng.integers(500_000, 5_000_000, n).astype(float)
    df.index.name = "time"
    return df
