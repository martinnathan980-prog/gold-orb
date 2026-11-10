"""Descriptive 4 (IS only): is the long drift on release days different from the same clock window on
ordinary days?  Windows (New York): 08:25 -> 15:55 (NFP / CPI clock), 13:55 -> 15:55 (FOMC clock),
prev 15:55 -> 15:55 (close to close).  Mid prices, bp."""
import sys

import numpy as np
import pandas as pd

from desc_common import IS_END, NY, Px, RES, gl, load_is, ny_time, release_times, tstat

syms = sys.argv[1:] or ["us500", "us100", "xauusd"]
ev = release_times()
ev = ev[(ev.t >= "2013-01-01") & (ev.t < IS_END)]
evd = {k: set(pd.DatetimeIndex(ev.t[ev.kind == k]).tz_convert(NY).tz_localize(None).normalize()) for k in ("fomc", "nfp", "cpi")}
allev = evd["fomc"] | evd["nfp"] | evd["cpi"]
out = []
for sym in syms:
    m1 = load_is(sym)
    px = Px(m1)
    days = pd.bdate_range("2013-01-02", "2021-12-31")
    d = pd.DatetimeIndex(days).tz_localize(NY)
    tt = lambda hhmm, sh=0: ny_time(d.tz_convert("UTC"), hhmm, sh)
    p0825, p1355, p1555 = px.at(tt("08:25")), px.at(tt("13:55")), px.at(tt("15:55"))
    pprev = px.at(tt("15:55", -1))
    w = pd.DataFrame({"day": days, "am": np.log(p1555 / p0825) * 1e4, "pm": np.log(p1555 / p1355) * 1e4,
                      "cc": np.log(p1555 / pprev) * 1e4, "on": np.log(p0825 / pprev) * 1e4})
    w["year"] = w.day.dt.year
    is_nc = w.day.isin(evd["nfp"] | evd["cpi"])
    is_f = w.day.isin(evd["fomc"])
    is_any = w.day.isin(allev)
    print(f"\n===== {sym}")

    def cmp(lab, col, sel, other):
        a, b = w.loc[sel, col].dropna(), w.loc[other, col].dropna()
        diff = a.mean() - b.mean()
        se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
        by = (w[sel].groupby("year")[col].mean() - w[other].groupby("year")[col].mean())
        print(f"  {lab:46s} event n={len(a):4d} mean={a.mean():+6.2f} (t {tstat(a):+5.2f}) | other n={len(b):4d} mean={b.mean():+6.2f} "
              f"(t {tstat(b):+5.2f}) | diff={diff:+6.2f} t={diff / se:+5.2f} | yrs diff>0: {(by > 0).sum()}/{by.notna().sum()}")
        out.append({"sym": sym, "cell": lab, "event_mean": round(a.mean(), 2), "other_mean": round(b.mean(), 2),
                    "diff": round(diff, 2), "t_diff": round(diff / se, 2)})

    cmp("NFP+CPI days 08:25->15:55 vs other days", "am", is_nc, ~is_any)
    cmp("FOMC days 13:55->15:55 vs other days", "pm", is_f, ~is_any)
    cmp("all release days close->close vs other", "cc", is_any, ~is_any)
    cmp("NFP+CPI days prev close->08:25 vs other", "on", is_nc, ~is_any)
    # the event-day long window as one series: 08:25->15:55 on NFP/CPI days, 13:55->15:55 on FOMC days
    evwin = pd.concat([w.loc[is_nc, ["year", "am"]].rename(columns={"am": "r"}), w.loc[is_f, ["year", "pm"]].rename(columns={"pm": "r"})])
    print(f"  event window long (T-5m -> 15:55), all kinds: n={evwin.r.notna().sum()} mean={evwin.r.mean():+.2f} t={tstat(evwin.r):+.2f} "
          f"by year: {evwin.groupby('year').r.mean().round(1).to_dict()}")
    first = evwin[evwin.year <= 2017].r
    second = evwin[evwin.year > 2017].r
    print(f"    2013-2017: mean {first.mean():+.2f} (t {tstat(first):+.2f}, n {first.notna().sum()}) | 2018-2021: mean {second.mean():+.2f} "
          f"(t {tstat(second):+.2f}, n {second.notna().sum()})")
    print(f"  ordinary days: 08:25->15:55 by year {w[~is_any].groupby('year').am.mean().round(1).to_dict()}")
pd.DataFrame(out).to_csv(f"{RES}/desc4_eventday_vs_other.csv", index=False)
