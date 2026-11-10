"""Descriptive 4 (IS only): zoom on the bitcoin late-US-day drift found in desc3 (21-23 UTC / 17-19 NY).
30-minute cells on the New-York clock and on the UTC clock, by year, weekdays vs weekends, and by DST regime
(to see which clock the effect follows).   Usage: python3 desc4_btc_late.py
"""
import numpy as np
import pandas as pd

from desc import RES, NY, Px, cal_dates, fmt, load_is, local_times, r2, summ


def run(sym="btcusd"):
    m1 = load_is(sym)
    px = Px(m1)
    out = [f"===== {sym}: zoom on the late-day window (IS, mid, bp)"]
    n = 0
    for tz, lab, start in ((NY, "NY", 15 * 60), ("UTC", "UTC", 19 * 60)):
        days = cal_dates(m1, tz)
        yrs = days.year.to_numpy()
        wk = days.dayofweek.to_numpy() < 5
        out.append(f"--- 30-min cells, {lab} clock, all days")
        for m in range(start, start + 6 * 60, 30):
            a = px.at(local_times(days, m % 1440, tz) + pd.Timedelta(days=m // 1440))
            b = px.at(local_times(days, (m + 30) % 1440, tz) + pd.Timedelta(days=(m + 30) // 1440))
            r = (b / a - 1) * 1e4
            l2 = f"{(m // 60) % 24:02d}:{m % 60:02d}->{((m + 30) // 60) % 24:02d}:{(m + 30) % 60:02d} {lab}"
            out.append(fmt(summ(r, yrs, l2))); n += 1
    # which clock?  NY 17->19 split by DST regime (summer: 21-23 UTC, winter: 22-24 UTC)
    days = cal_dates(m1, NY)
    yrs = days.year.to_numpy()
    t17 = local_times(days, "17:00", NY)
    summer = (t17.hour == 21)
    out.append("--- which clock? windows by US DST regime")
    for t0, t1, tz, lab in [("17:00", "19:00", NY, "NY 17->19"), ("16:00", "18:00", NY, "NY 16->18"),
                            ("18:00", "20:00", NY, "NY 18->20"), ("16:00", "17:00", NY, "NY 16->17"),
                            ("17:00", "18:00", NY, "NY 17->18"), ("18:00", "19:00", NY, "NY 18->19")]:
        a = px.at(local_times(days, t0, tz)); b = px.at(local_times(days, t1, tz))
        r = (b / a - 1) * 1e4
        out.append(fmt(summ(r[summer], yrs[summer], lab + " | US summer time"))); n += 1
        out.append(fmt(summ(r[~summer], yrs[~summer], lab + " | US winter time"))); n += 1
    out.append("--- NY 17->19 by weekday (Sat/Sun only where quoted: mostly 2019+)")
    a = px.at(local_times(days, "17:00", NY)); b = px.at(local_times(days, "19:00", NY))
    r = (b / a - 1) * 1e4
    dow = days.dayofweek.to_numpy()
    for d_, nm in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
        out.append(fmt(summ(r[dow == d_], yrs[dow == d_], f"NY 17->19 {nm}"))); n += 1
    out.append(fmt(summ(r[dow < 5], yrs[dow < 5], "NY 17->19 Mon-Fri"))); n += 1
    out.append(fmt(summ(r[dow < 4], yrs[dow < 4], "NY 17->19 Mon-Thu"))); n += 1
    out.append("--- candidate windows (NY clock), all days / first vs second half of IS")
    half = days < pd.Timestamp("2019-09-01")
    for t0, t1, lab in [("17:00", "19:00", "NY 17:00->19:00"), ("17:05", "19:00", "NY 17:05->19:00"),
                        ("17:00", "18:30", "NY 17:00->18:30"), ("17:00", "20:00", "NY 17:00->20:00"),
                        ("16:30", "19:00", "NY 16:30->19:00"), ("17:30", "19:00", "NY 17:30->19:00"),
                        ("17:00", "19:30", "NY 17:00->19:30")]:
        a = px.at(local_times(days, t0, NY)); b = px.at(local_times(days, t1, NY))
        r = (b / a - 1) * 1e4
        out.append(fmt(summ(r, yrs, lab))); n += 1
        out.append(fmt(summ(r[half], yrs[half], lab + " | 2017-05..2019-08"), by_year=False))
        out.append(fmt(summ(r[~half], yrs[~half], lab + " | 2019-09..2021-12"), by_year=False))
    out.append(f"windows examined in this file: {n}")
    txt = "\n".join(out)
    print(txt, flush=True)
    with open(f"{RES}/desc4_btc_late.txt", "w") as f:
        f.write(txt + "\n")
    r2.free()


if __name__ == "__main__":
    run()
