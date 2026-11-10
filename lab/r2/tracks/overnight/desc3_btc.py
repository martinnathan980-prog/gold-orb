"""Descriptive 3 (IS only): bitcoin hour-of-day (UTC), weekday, weekend and session patterns.
Mid returns in bp.  Data: Dukascopy BTCUSD CFD, IS = 2017-05 .. 2021-12 (no Saturday quotes before 2019,
complete weekends only from 2021).   Usage: python3 desc3_btc.py
"""
import json

import numpy as np
import pandas as pd

from desc import RES, NY, Px, cal_dates, fmt, load_is, local_times, r2, summ

SCR = "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad"


def run(sym="btcusd"):
    m1 = load_is(sym)
    px = Px(m1)
    days = cal_dates(m1, "UTC")
    P = pd.DataFrame({f"{h:02d}": px.at(local_times(days, f"{h:02d}:00", "UTC")) for h in range(24)}, index=days)
    P["24"] = P["00"].shift(-1)
    yrs = P.index.year.to_numpy()
    dow = P.index.dayofweek.to_numpy()
    out = [f"===== {sym}: IS {days[0].date()} .. {days[-1].date()}, mid returns in bp, UTC clock"]
    n = 0
    out.append("--- A. hour of day (UTC), all days")
    cells = []
    for h in range(24):
        r = (P[f"{h + 1:02d}"] / P[f"{h:02d}"] - 1) * 1e4
        d = summ(r.to_numpy(), yrs, f"{h:02d}->{h + 1:02d} UTC")
        cells.append(d); out.append(fmt(d)); n += 1
    tt = np.array([c["t"] for c in cells])
    out.append(f"cells: 24; |t|>2: {int((np.abs(tt) > 2).sum())} (chance 1.1); |t|>3: {int((np.abs(tt) > 3).sum())} (chance 0.06)")
    out.append("--- B. hour of day, Monday-Friday only (comparable across all years)")
    wk = dow < 5
    for h in range(24):
        r = (P[f"{h + 1:02d}"] / P[f"{h:02d}"] - 1) * 1e4
        out.append(fmt(summ(r.to_numpy()[wk], yrs[wk], f"{h:02d}->{h + 1:02d} UTC Mon-Fri"))); n += 1
    out.append("--- C. blocks (all days where quoted)")
    B = [("00", "08", "Asia 00-08"), ("08", "13", "Europe 08-13"), ("13", "21", "US 13-21"), ("21", "24", "late 21-24"),
         ("21", "23", "21-23"), ("22", "24", "22-24"), ("20", "24", "20-24"), ("00", "04", "00-04"), ("04", "08", "04-08"),
         ("13", "16", "13-16"), ("16", "21", "16-21"), ("00", "24", "full day 00-24"), ("08", "21", "08-21"),
         ("14", "20", "US cash 14-20")]
    for a, b, lab in B:
        r = (P[b] / P[a] - 1) * 1e4
        out.append(fmt(summ(r.to_numpy(), yrs, lab))); n += 1
    out.append("--- D. weekday, full UTC day 00->24 (weekends: mostly 2019+)")
    full = (P["24"] / P["00"] - 1) * 1e4
    for d_, nm in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
        out.append(fmt(summ(full.to_numpy()[dow == d_], yrs[dow == d_], f"{nm} 00->24"))); n += 1
    out.append("--- E. weekend windows")
    fri = P.index[dow == 4]
    y_f = fri.year.to_numpy()
    a = px.at(local_times(fri, "21:00", "UTC"))
    for (dd, hh_, lab) in [(2, "22:00", "Fri 21:00 -> Sun 22:00"), (3, "00:00", "Fri 21:00 -> Mon 00:00"),
                           (3, "08:00", "Fri 21:00 -> Mon 08:00"), (3, "13:00", "Fri 21:00 -> Mon 13:00")]:
        b = px.at(local_times(fri + pd.Timedelta(days=dd), hh_, "UTC"))
        out.append(fmt(summ((b / a - 1) * 1e4, y_f, lab))); n += 1
    sun = P.index[dow == 6]
    a = px.at(local_times(sun, "22:00", "UTC"))
    for (dd, hh_, lab) in [(1, "08:00", "Sun 22:00 -> Mon 08:00"), (1, "13:00", "Sun 22:00 -> Mon 13:00"),
                           (1, "21:00", "Sun 22:00 -> Mon 21:00")]:
        b = px.at(local_times(sun + pd.Timedelta(days=dd), hh_, "UTC"))
        out.append(fmt(summ((b / a - 1) * 1e4, sun.year.to_numpy(), lab))); n += 1
    out.append("--- F. New-York clock windows (US equity session), Mon-Fri")
    wd = days[days.dayofweek < 5]
    yw = wd.year.to_numpy()
    for t0, t1, d1, lab in [("09:30", "16:00", 0, "NY 09:30->16:00 (US cash)"), ("16:00", "09:30", 1, "NY 16:00->09:30 next (US night)"),
                            ("16:00", "20:00", 0, "NY 16:00->20:00"), ("17:00", "19:00", 0, "NY 17:00->19:00"),
                            ("20:00", "04:00", 1, "NY 20:00->04:00 next"), ("04:00", "09:30", 0, "NY 04:00->09:30")]:
        a = px.at(local_times(wd, t0, NY))
        b = px.at(local_times(wd + pd.Timedelta(days=d1), t1, NY))
        out.append(fmt(summ((b / a - 1) * 1e4, yw, lab))); n += 1
    out.append(f"windows examined in this file: {n}")
    txt = "\n".join(out)
    print(txt, flush=True)
    with open(f"{RES}/desc3_btc.txt", "w") as f:
        f.write(txt + "\n")
    P.to_pickle(f"{SCR}/P_btc_hours.pkl")
    r2.free()


if __name__ == "__main__":
    run()
