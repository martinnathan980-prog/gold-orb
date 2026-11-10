"""Descriptive 1 (IS only): half-hour grid of mid returns over the 24 h trading day for the index CFDs.
US indices: New-York clock, trading day D = evening session of the previous calendar day (from 18:30 NY)
+ the day itself up to the 16:00 cash close.   ger40: Berlin clock, previous Xetra close 17:30 -> 17:30.
Usage: python3 desc1_idx_grid.py us500 [us100 ger40]
"""
import json
import sys

import numpy as np
import pandas as pd

from desc import RES, NY, BER, Px, cal_dates, fmt, load_is, local_times, r2, summ

SCR = "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad"


def hh(a, b):
    """half-hour labels from minute a to minute b inclusive"""
    return [f"{m // 60:02d}:{m % 60:02d}" for m in range(a, b + 1, 30)]


CFG = {
    "us": dict(tz=NY, close="16:00", open="09:30", eve=hh(18 * 60 + 30, 23 * 60 + 30), day=hh(0, 16 * 60),
               W=[("p16:00", "09:30", "close->open (whole night)"), ("09:30", "16:00", "open->close (cash session)"),
                  ("p16:00", "16:00", "close->close"),
                  ("p16:00", "e18:30", "close->18:30 (break+rollover)"), ("e18:30", "02:00", "18:30->02:00 (Asia)"),
                  ("e20:00", "02:00", "20:00->02:00"), ("p16:00", "02:00", "close->02:00"),
                  ("02:00", "03:00", "02:00->03:00 (EU open)"), ("02:00", "04:00", "02:00->04:00"),
                  ("03:00", "04:00", "03:00->04:00"), ("01:00", "04:00", "01:00->04:00"), ("00:00", "04:00", "00:00->04:00"),
                  ("04:00", "08:00", "04:00->08:00"), ("08:00", "09:30", "08:00->09:30"), ("04:00", "09:30", "04:00->09:30"),
                  ("02:00", "09:30", "02:00->09:30"), ("e18:30", "09:30", "18:30->09:30"), ("e20:00", "09:30", "20:00->09:30"),
                  ("e18:30", "04:00", "18:30->04:00"), ("e20:00", "04:00", "20:00->04:00"), ("p16:00", "04:00", "close->04:00"),
                  ("09:30", "10:00", "09:30->10:00"), ("10:00", "15:00", "10:00->15:00"), ("15:00", "16:00", "15:00->16:00"),
                  ("15:30", "16:00", "15:30->16:00"), ("09:30", "12:00", "09:30->12:00"), ("12:00", "16:00", "12:00->16:00")]),
    "de": dict(tz=BER, close="17:30", open="09:00", eve=hh(18 * 60, 23 * 60 + 30), day=hh(0, 17 * 60 + 30),
               W=[("p17:30", "09:00", "xetra close->open (whole night)"), ("09:00", "17:30", "xetra open->close"),
                  ("p17:30", "17:30", "close->close"),
                  ("p17:30", "e22:00", "17:30->22:00 (US afternoon)"), ("e22:00", "00:30", "22:00->00:30 (break+rollover)"),
                  ("p17:30", "08:00", "17:30->08:00"), ("e22:00", "08:00", "22:00->08:00"), ("e22:00", "09:00", "22:00->09:00"),
                  ("00:30", "08:00", "00:30->08:00 (Asia)"), ("02:30", "08:00", "02:30->08:00"), ("00:30", "09:00", "00:30->09:00"),
                  ("08:00", "09:00", "08:00->09:00"), ("09:00", "10:00", "09:00->10:00"), ("09:00", "12:00", "09:00->12:00"),
                  ("12:00", "15:30", "12:00->15:30"), ("15:30", "17:30", "15:30->17:30 (US open)"),
                  ("08:00", "17:30", "08:00->17:30")]),
}


def run(sym):
    c = CFG["de" if sym == "ger40" else "us"]
    tz = c["tz"]
    m1 = load_is(sym)
    px = Px(m1)
    days = cal_dates(m1, tz)
    days = days[days.dayofweek < 5]
    cols, P = [], []
    prev = days - pd.to_timedelta(np.where(days.dayofweek == 0, 3, 1), unit="D")
    P.append(px.at(local_times(prev, c["close"], tz))); cols.append("p" + c["close"])
    for g in c["eve"]:
        P.append(px.at(local_times(days - pd.Timedelta(days=1), g, tz))); cols.append("e" + g)
    for g in c["day"]:
        P.append(px.at(local_times(days, g, tz))); cols.append(g)
    P = pd.DataFrame(np.array(P).T, index=days, columns=cols)
    P = P[P[c["open"]].notna() & P[c["close"]].notna()]      # full cash sessions only
    yrs = P.index.year.to_numpy()
    out = [f"===== {sym}: IS half-hour grid ({tz} clock), mid returns in bp; {len(P)} cash sessions "
           f"{P.index[0].date()} .. {P.index[-1].date()}"]
    cells = []
    for a, b in zip(cols[:-1], cols[1:]):
        r = (P[b] / P[a] - 1) * 1e4
        d = summ(r, yrs, f"{a}->{b}")
        cells.append(d)
        out.append(fmt(d))
    tt = np.array([x.get("t", np.nan) for x in cells])
    out.append(f"cells: {len(cells)}; |t|>2: {int((np.abs(tt) > 2).sum())} (chance {0.0455 * len(cells):.1f}); "
               f"|t|>3: {int((np.abs(tt) > 3).sum())} (chance {0.0027 * len(cells):.1f})")
    out.append("--- aggregated windows")
    agg = []
    for a, b, lab in c["W"]:
        d = summ((P[b] / P[a] - 1) * 1e4, yrs, lab)
        agg.append(d)
        out.append(fmt(d))
    out.append(f"aggregated windows examined: {len(c['W'])}")
    txt = "\n".join(out)
    print(txt, flush=True)
    with open(f"{RES}/desc1_grid_{sym}.txt", "w") as f:
        f.write(txt + "\n")
    json.dump({"cells": cells, "agg": agg}, open(f"{RES}/desc1_grid_{sym}.json", "w"))
    P.to_pickle(f"{SCR}/P_{sym}.pkl")
    r2.free()


if __name__ == "__main__":
    for s in sys.argv[1:] or ["us500"]:
        run(s)
