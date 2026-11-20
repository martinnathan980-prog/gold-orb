"""Synthetic worlds for the tests and the timing runs (no market data): 'noise' = the kit's synth.bars (Brownian
bars, no edge); 'planted' = the same law with one planted edge: after every signal of R07 on H1 (three closes down in
a row: buy; up: sell), the next 24 hourly bars drift by PLANT_EDGE x vol in the signal's direction. The planted world
is generated bar by bar (a signal depends on the closes so far, the drift on the signals so far), with highs and lows
from the exact law of a Brownian path's max and min given the bar's move (as kit.synth.bars)."""
import numpy as np
import pandas as pd

from kit import data as D
from kit import synth as S

VOL_H = 0.0015
PLANT_EDGE = 0.03          # drift per hourly bar, in units of the bar's sd, for 24 bars after each planted signal
PLANT_RULE = "R07|H1|F0|24h"
OIL_AS = ("xagusd", 3.0)   # synthetic oil: the 'index' calendar of synth with silver's law, price x3 (about 60 USD)


def _seed(market, seed):
    from .grammar import MARKETS
    return int(seed) * 100 + MARKETS.index(market)


def noise_bars(market, seed=0, start="2013-01-01", end="2022-01-01"):
    if market == "oil":
        b = S.bars(OIL_AS[0], start, end, vol_h=VOL_H, seed=_seed(market, seed))
        b = b.copy()
        for k in ("open", "high", "low", "close"):
            b[k] = b[k] * OIL_AS[1]
        b.attrs["price_is"] = "bid"
        return b
    return S.bars(market, start, end, vol_h=VOL_H, seed=_seed(market, seed))


def planted_bars(market, seed=0, start="2013-01-01", end="2022-01-01", edge=PLANT_EDGE):
    key = OIL_AS[0] if market == "oil" else market
    kind = S.KIND.get(key, "fx")
    t = S.calendar(kind, start, end)
    t = t[~D.fp_closed(t)] if D.fp_markets()[key]["weekdays_only"] else t
    n = len(t)
    rng = np.random.default_rng(_seed(market, seed) + 7)
    eps = rng.standard_normal(n)
    u = 1.0 - rng.random((n, 2))
    drift = np.zeros(n + 25)
    x = np.empty(n)
    lc = np.empty(n)                 # log close
    p0 = np.log(S.PRICE[key] * (OIL_AS[1] if market == "oil" else 1.0))
    prev_on_dn = prev_on_up = False
    for i in range(n):
        x[i] = drift[i] * VOL_H + VOL_H * eps[i]
        lc[i] = (lc[i - 1] if i else p0) + x[i]
        if i >= 3:
            dn = lc[i] < lc[i - 1] < lc[i - 2] < lc[i - 3]
            up = lc[i] > lc[i - 1] > lc[i - 2] > lc[i - 3]
        else:
            dn = up = False
        if dn and not prev_on_dn and i >= 4:
            drift[i + 1:i + 25] += edge
        if up and not prev_on_up and i >= 4:
            drift[i + 1:i + 25] -= edge
        prev_on_dn, prev_on_up = dn, up
    upw = (x + np.sqrt(x * x - 2 * VOL_H ** 2 * np.log(u[:, 0]))) / 2
    dnw = (x - np.sqrt(x * x - 2 * VOL_H ** 2 * np.log(u[:, 1]))) / 2
    lo0 = np.r_[p0, lc[:-1]]
    df = pd.DataFrame({"open": np.exp(lo0), "high": np.exp(lo0 + upw), "low": np.exp(lo0 + dnw), "close": np.exp(lc),
                       "volume": 60.0}, index=t)
    df.attrs["price_is"] = "bid"
    return df


def fat_bars(market, seed=0, start="2013-01-01", end="2022-01-01", df=3.0):
    """Like noise_bars but with Student-t (df 3) hourly moves scaled to the same sd, rare jumps of 20 sd and drift
    regimes of 600 bars (+/- 0.25 sd a bar), so that shocks and long moves occur on every frame (the truncation tests
    need signals of every rule); wicks from the Brownian bridge with the bar's own scale. For tests only."""
    key = OIL_AS[0] if market == "oil" else market
    t = S.calendar(S.KIND.get(key, "fx"), start, end)
    t = t[~D.fp_closed(t)] if D.fp_markets()[key]["weekdays_only"] else t
    n = len(t)
    rng = np.random.default_rng(_seed(market, seed) + 5)
    x = VOL_H * rng.standard_t(df, n) / np.sqrt(df / (df - 2.0))
    x += np.where(rng.random(n) < 0.0005, 20 * VOL_H * rng.choice([-1.0, 1.0], n), 0.0)    # rare jumps
    reg = np.repeat(rng.choice([-1.0, 0.0, 0.0, 1.0], n // 600 + 1), 600)[:n]               # drift regimes
    x += 0.25 * VOL_H * reg
    sc = np.maximum(np.abs(x), VOL_H)
    u = 1.0 - rng.random((n, 2))
    upw = (x + np.sqrt(x * x - 2 * sc ** 2 * np.log(u[:, 0]))) / 2
    dnw = (x - np.sqrt(x * x - 2 * sc ** 2 * np.log(u[:, 1]))) / 2
    p0 = np.log(S.PRICE[key] * (OIL_AS[1] if market == "oil" else 1.0))
    lo0 = p0 + np.r_[0.0, np.cumsum(x)[:-1]]
    b = pd.DataFrame({"open": np.exp(lo0), "high": np.exp(lo0 + upw), "low": np.exp(lo0 + dnw),
                      "close": np.exp(lo0 + x), "volume": 60.0}, index=t)
    b.attrs["price_is"] = "bid"
    return b


def _oil_gaps(b, market, seed):
    """Synthetic oil: a reopen gap of about 1e-6 at every bar (the kit refuses bars that copy the vendor's raw zero gap
    at a listed roll, kit.data.check_adjusted); high and low widened to hold the open."""
    if market != "oil":
        return b
    rng = np.random.default_rng(_seed(market, seed) + 99)
    b = b.copy()
    o = b["open"].to_numpy() * np.exp(1e-6 * rng.standard_normal(len(b)))
    b["open"] = o
    b["high"] = np.maximum(b["high"].to_numpy(), o)
    b["low"] = np.minimum(b["low"].to_numpy(), o)
    b.attrs["price_is"] = "bid"
    return b


def bars(market, world, seed=0, start="2013-01-01", end="2022-01-01"):
    if world == "noise":
        return _oil_gaps(noise_bars(market, seed, start, end), market, seed)
    if world == "planted":
        return _oil_gaps(planted_bars(market, seed, start, end), market, seed)
    if world == "fat":
        return _oil_gaps(fat_bars(market, seed, start, end), market, seed)
    raise ValueError(f"unknown synthetic world {world!r}")
