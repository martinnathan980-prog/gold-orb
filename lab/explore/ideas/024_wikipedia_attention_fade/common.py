"""Idea 024: shared pieces (page list, loading of the cached Wikimedia page views, the signal build).
Views of UTC day D are KNOWN at D+2 00:00 UTC (scout/sources.md section 20). Nothing after 2021-12-31 is read."""
import json, os
import numpy as np
import pandas as pd
from kit import data as D

CACHE = os.path.expanduser("~/explore_data/idea_024/wiki")
# page -> (cached files summed, FP market)
PAGES = {"Gold": (["Gold"], "xauusd"), "Silver": (["Silver"], "xagusd"), "Euro": (["Euro"], "eurusd"),
         "Japanese_yen": (["Japanese_yen"], "usdjpy"), "S&P_500": (["SandP_500", "SandP_500_Index"], "us500"),
         "DAX": (["DAX"], "ger40"), "Pound_sterling": (["Pound_sterling"], "gbpusd"),
         "Bitcoin": (["Bitcoin"], "btcusd"), "Ethereum": (["Ethereum"], "ethusd")}
LAG = pd.Timedelta(days=2)


def raw_views(page):
    """Daily views (naive UTC date index) summed over the page's titles, cut at 2021-12-31 in the read."""
    tot = None
    for f in PAGES[page][0]:
        p = os.path.join(CACHE, f + ".json")
        if not os.path.exists(p):
            continue
        it = json.load(open(p))["items"]
        s = pd.Series({pd.Timestamp(i["timestamp"][:8]): float(i["views"]) for i in it
                       if i["timestamp"][:8] <= "20211231"})
        tot = s if tot is None else tot.add(s, fill_value=0.0)
    return None if tot is None else tot.sort_index()


def views_known(page):
    """Views indexed by the time they are KNOWN (D+2 00:00 UTC), via kit.data.external with min_lag = 2 days."""
    s = raw_views(page)
    if s is None:
        return None
    return D.external(s.index, s.values, known=lambda d: pd.DatetimeIndex(d).tz_localize("UTC") + LAG,
                      min_lag=LAG, name=page)


def zscores(vk, window=28):
    """z of log views of day D against the `window` days D-window..D-1 (past only). Input indexed by known time."""
    obs = (pd.DatetimeIndex(vk.index) - LAG).tz_localize(None)
    v = pd.Series(np.log(np.where(vk.values > 0, vk.values, np.nan)), index=obs)
    v = v.reindex(pd.date_range(obs.min(), obs.max(), freq="D")) if len(v) else v
    past = v.shift(1).rolling(window, min_periods=window)
    return (v - past.mean()) / past.std(ddof=1)


def entry_time(days):
    """07:00 UTC on D+2, moved to the next weekday when D+2 falls on a weekend."""
    t = pd.DatetimeIndex(days).tz_localize("UTC") + pd.Timedelta(days=2, hours=7)
    wd = t.dayofweek
    return t + pd.to_timedelta(np.where(wd == 5, 2, np.where(wd == 6, 1, 0)), unit="D")


def close_at(bars, times):
    """Close of the last H1 bar that ENDED at or before each time (bar end = open + 1 h)."""
    c = pd.Series(bars["close"].to_numpy(float), index=pd.DatetimeIndex(bars.index) + pd.Timedelta(hours=1))
    return D.asof_join(times, c)


def build_cfg(d, z_thr=2.0, window=28, move_days=3):
    rows = []
    for page, (_, mk) in PAGES.items():
        vk, b = d.get("views_" + page), d.get("bars_" + mk)
        if vk is None or b is None or len(vk) == 0 or len(b) == 0:
            continue
        z = zscores(vk, window)
        days = z.index[(z >= z_thr).to_numpy()]
        if not len(days):
            continue
        dd = pd.DatetimeIndex(days).tz_localize("UTC")
        c1 = close_at(b, dd + pd.Timedelta(days=1))                 # close at the end of UTC day D
        c0 = close_at(b, dd + pd.Timedelta(days=1 - move_days))     # close at the end of UTC day D - move_days
        mv = c1 - c0
        ok = np.isfinite(mv) & (mv != 0)
        ka = entry_time(days)
        rows.append(pd.DataFrame({"known_at": ka[ok], "side": (-np.sign(mv[ok])).astype(int), "market": mk,
                                  "page": page, "obs_day": days[ok]}))
    if not rows:
        return pd.DataFrame(columns=["known_at", "side", "market", "page", "obs_day"])
    out = pd.concat(rows, ignore_index=True)
    return out.sort_values(["known_at", "market"], kind="stable").reset_index(drop=True)
