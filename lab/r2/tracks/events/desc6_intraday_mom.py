"""Descriptive 6 (IS only): market intraday momentum (Gao, Han, Li, Zhou 2018) on release days.
Signal A: sign(prev 15:55 -> 10:00 NY)       -> return 15:30 -> 15:55
Signal B: sign(prev 15:55 -> 15:30 NY)       -> return 15:30 -> 15:55
Signal C: sign(release reaction T-1m -> 15:30) -> return 15:30 -> 15:55   (event days only)
Event days vs ordinary days.  Mid prices, bp."""
import sys

import numpy as np
import pandas as pd

from desc_common import IS_END, NY, Px, RES, gl, load_is, ny_time, release_times, tstat

syms = sys.argv[1:] or ["us500", "us100", "xauusd"]
ev = release_times()
ev = ev[(ev.t >= "2013-01-01") & (ev.t < IS_END)]
evd = pd.DatetimeIndex(ev.t).tz_convert(NY).tz_localize(None).normalize()
kind_of = dict(zip(evd, ev.kind))
for sym in syms:
    m1 = load_is(sym)
    px = Px(m1)
    days = pd.bdate_range("2013-01-02", "2021-12-31")
    d = pd.DatetimeIndex(days).tz_localize(NY).tz_convert("UTC")
    pprev = px.at(ny_time(d, "15:55", -1))
    p1000, p1530, p1555 = px.at(ny_time(d, "10:00")), px.at(ny_time(d, "15:30")), px.at(ny_time(d, "15:55"))
    w = pd.DataFrame({"day": days, "year": days.year, "first": np.log(p1000 / pprev) * 1e4, "sofar": np.log(p1530 / pprev) * 1e4,
                      "last": np.log(p1555 / p1530) * 1e4})
    w["isev"] = w.day.isin(evd)
    print(f"\n===== {sym}")
    for lab, sel in (("release days", w.isev), ("ordinary days", ~w.isev)):
        x = w[sel]
        for sn, sc in (("A first half-hour", "first"), ("B day so far", "sofar")):
            r = np.sign(x[sc]) * x["last"]
            by = r.groupby(x.year).mean()
            print(f"  {lab:14s} {sn:18s} n={r.notna().sum():4d} mean={r.mean():+5.2f} t={tstat(r):+5.2f} hit={np.mean(r.dropna() > 0):.2f} "
                  f"corr={x[sc].corr(x['last']):+.3f} yrs+={int((by > 0).sum())}/{len(by)}")
    # by kind for signal B
    w["kind"] = w.day.map(kind_of)
    for k in ("fomc", "nfp", "cpi"):
        x = w[w.kind == k]
        r = np.sign(x["sofar"]) * x["last"]
        print(f"  {k:5s} signal B: n={r.notna().sum():3d} mean={r.mean():+5.2f} t={tstat(r):+5.2f}")
