"""Structural check of the decision table and the orders (no simulation, no P&L): clock times of the F, P, entry and
exit bars in New York time, the daily bar used for sigma / ATR, counts, DST Sundays.

    PYTHONDONTWRITEBYTECODE=1 NUMBA_CACHE_DIR=/tmp/... python3 check_structure.py eurusd
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import wkfade as W  # noqa: E402


def ny(t):
    return pd.DatetimeIndex(t).tz_localize("UTC").tz_convert(W.NY)


def main(sym):
    m1 = W.load_is(sym)
    print(sym, "rows", len(m1), "first", m1.index[0], "last", m1.index[-1])
    daily = W.daily_table(m1)
    tc, sig, atr = daily
    print("full days", len(tc), "first t_close (NY)", ny(tc[:1])[0], "last", ny(tc[-1:])[0])
    d = W.decisions(m1, dec="20:00", q=75, daily=daily)
    cnt = {k: int(d[k].sum()) if d[k].dtype == bool else None for k in ("okE", "decided", "signal")}
    print("sundays", len(d), "F ok", int((d.jF >= 0).sum()), "P ok", int((d.jP >= 0).sum()), cnt,
          "signal share of decided", round(d.signal.sum() / d.decided.sum(), 3))
    print("first decided sunday", d.loc[d.decided, "sunday"].min(), "last", d.loc[d.decided, "sunday"].max())
    idx = W.naive_utc(m1)
    v = d[d.decided]
    tF = ny(idx[v.jF.to_numpy()])
    tP = ny(idx[v.jP.to_numpy()])
    okE = v.okE.to_numpy()
    tE = ny(idx[v.jE.to_numpy()[okE]])
    tD = ny(v.t_day.to_numpy())
    print("F bar NY weekday/time counts:", pd.Series(tF.strftime("%a %H:%M")).value_counts().head(4).to_dict())
    print("P bar NY weekday/time counts:", pd.Series(tP.strftime("%a %H:%M")).value_counts().head(4).to_dict())
    print("entry bar NY counts:", pd.Series(tE.strftime("%a %H:%M")).value_counts().head(4).to_dict())
    print("sigma/ATR day close NY counts:", pd.Series(tD.strftime("%a %H:%M")).value_counts().head(5).to_dict())
    assert (v.t_day.to_numpy() < v.t_dec.to_numpy()).all()
    assert (v.n_hist >= 52).all() and (v.n_hist <= 104).all()
    for ex in ("mon16", "tue12", "wed12"):
        xi, tX = W.exit_bars(m1, v, ex)
        tx = ny(idx[xi])
        print(f"exit {ex} bar NY counts:", pd.Series(tx.strftime("%a %H:%M")).value_counts().head(4).to_dict())
    # DST Sundays (second Sunday of March, first Sunday of November)
    dst = v[(v.sunday.dt.month.isin([3, 11])) & (v.sunday.dt.day <= 14)]
    for _, r in dst.head(6).iterrows():
        print("DST-month Sunday", r.sunday.date(), "P bar NY", ny([idx[r.jP]])[0], "F bar NY", ny([idx[r.jF]])[0])
    for dec in ("19:00", "21:00"):
        dd = W.decisions(m1, dec=dec, q=75, daily=daily)
        tp = ny(idx[dd.loc[dd.decided, "jP"].to_numpy()])
        print(f"dec {dec}: decided {int(dd.decided.sum())} signals {int(dd.signal.sum())} P bar NY",
              pd.Series(tp.strftime("%a %H:%M")).value_counts().head(3).to_dict())
    o = W.make_orders(m1, dtab=d, exit="mon16", stop_atr=1.0)
    print("orders", len(o), "refused", o.attrs["refused_3spreads"], "entry_i == jP+1:",
          bool((o.entry_i.to_numpy() == o.jP.to_numpy() + 1).all()),
          "stop/ATR == 1:", bool(np.allclose(o.stop_dist / o.atr, 1.0)))
    sp = (m1["ao"].to_numpy() - m1["bo"].to_numpy())[o.entry_i.to_numpy()]
    print("stop distance in spreads: min", round(float((o.stop_dist / sp).min()), 1), "median",
          round(float((o.stop_dist / sp).median()), 1))
    print("sigma bp median", round(float(np.nanmedian(v.sigma) * 1e4), 1), "ATR bp median",
          round(float(np.nanmedian(v.atr / v.P) * 1e4), 1), "|z| median", round(float(v.absz.median()), 3),
          "thr median", round(float(v.thr.median()), 3))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "eurusd")
