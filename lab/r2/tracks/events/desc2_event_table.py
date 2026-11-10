"""Descriptive 2 (IS only): build one row per (event, symbol) with mid prices at fixed offsets around the
release time.  Saved to results/r2/events/evtab_<sym>.csv (in-sample events only: release < 2022-01-01)."""
import sys

import numpy as np
import pandas as pd

from desc_common import IS_END, NY, Px, RES, gl, load_is, ny_time, release_times

syms = sys.argv[1:] or ["us500", "us100", "xauusd"]
OFFS = [-1440, -240, -60, -30, -5, 1, 2, 3, 5, 10, 15, 30, 45, 60, 90, 120, 180]
ev = release_times()
ev = ev[(ev.t >= "2013-01-01") & (ev.t < IS_END)].reset_index(drop=True)
for sym in syms:
    m1 = load_is(sym)
    px = Px(m1)
    t = pd.DatetimeIndex(ev.t)
    tab = pd.DataFrame({"t": t, "kind": ev.kind.values, "year": t.year,
                        "ny": [str(x)[:16] for x in t.tz_convert(NY)]})
    tab["p_m1"] = px.before(t, 3)                      # last mid close before the release minute
    for o in OFFS:
        nm = f"p_{'m' if o < 0 else 'p'}{abs(o)}"
        if o == -1:
            continue
        tab[nm] = px.at(t + pd.Timedelta(minutes=o), 3)
    tab["p_prev1555"] = px.at(ny_time(t, "15:55", -1), 3)
    tab["p_1555"] = px.at(ny_time(t, "15:55"), 3)
    tab["p_next0930"] = px.at(ny_time(t, "09:30", 1), 3)
    tab["p_next1555"] = px.at(ny_time(t, "15:55", 1), 3)
    # pre-release range (mid) over the 30 / 60 minutes before T, release-bar extremes, first 5 minutes
    for w in (30, 60):
        hi, lo = px.hilo(t - pd.Timedelta(minutes=w), t)
        tab[f"pre{w}_hi"], tab[f"pre{w}_lo"] = hi, lo
    hi, lo = px.hilo(t, t + pd.Timedelta(minutes=1))
    tab["rb_hi"], tab["rb_lo"] = hi, lo
    hi, lo = px.hilo(t, t + pd.Timedelta(minutes=5))
    tab["f5_hi"], tab["f5_lo"] = hi, lo
    # realised vol proxy known before the event: median M5 mid range over the previous 20 trading days is heavy;
    # use the mean absolute M1 mid return over [T-240, T-5] (bp) as a cheap, causal volatility unit
    a = np.searchsorted(px.ns, px._ns(t - pd.Timedelta(minutes=240)))
    b = np.searchsorted(px.ns, px._ns(t - pd.Timedelta(minutes=5)))
    v = np.full(len(t), np.nan)
    for k in range(len(t)):
        if b[k] - a[k] > 60:
            c = px.mc[a[k]:b[k]]
            v[k] = np.mean(np.abs(np.diff(np.log(c)))) * 1e4
    tab["vol_m1_bp"] = v
    tab.to_csv(f"{RES}/evtab_{sym}.csv", index=False)
    print(sym, len(tab), "rows;", tab.notna().sum().to_dict())
