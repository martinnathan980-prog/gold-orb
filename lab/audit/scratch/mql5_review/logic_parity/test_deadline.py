"""DeadlineUTC (EA, ported) vs the lab's add_trading_days(tc, 5) - 5 min, for the six UTC
decision hours on every weekday, in both DST regimes and across the DST switch weeks.

Part A (synthetic): lab decision time tc == the EA's bucket start (normal 4h boundary).
Part B (synthetic): first bucket after the weekend: EA decides at the Sunday 20:00 UTC bucket
         start, the lab decided at the Friday close (t_close of the Friday 20:00 UTC bar).
"""
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, LAB)
sys.path.insert(0, os.path.join(LAB, "live"))
from mql5_time import DeadlineUTC  # noqa: E402
from tracks.trend.strategy import add_trading_days  # noqa: E402
from ea_twin import deadline_utc as twin_deadline  # noqa: E402

NY = "America/New_York"


def ea(t):
    return pd.Timestamp(DeadlineUTC(int(t.timestamp())), unit="s", tz="UTC")


def lab(tc):
    return add_trading_days(pd.DatetimeIndex([tc]), 5)[0] - pd.Timedelta(minutes=5)


def fmt(t):
    return t.tz_convert(NY).strftime("%a %m-%d %H:%M NY")


weeks = {"winter (EST)": "2025-01-12", "summer (EDT)": "2025-06-15",
         "US spring switch wk": "2025-03-02", "US autumn switch wk": "2025-10-26",
         "EU/US gap (Mar)": "2025-03-09", "EU/US gap (Oct-Nov)": "2025-10-26"}
tot = diff = diff_twin = 0
for label, sunday in weeks.items():
    print(f"\n=== {label}: week starting Sunday {sunday}")
    s = pd.Timestamp(sunday, tz="UTC")
    rows = []
    for d in range(6):  # Sun .. Fri
        for h in (0, 4, 8, 12, 16, 20):
            b = s + pd.Timedelta(days=d, hours=h)
            ny = b.tz_convert(NY)
            # market open at the bucket start? (Sun 18:00 NY -> Fri 17:00 NY)
            if (ny.dayofweek == 6 and ny.hour < 18) or (ny.dayofweek == 4 and ny.hour >= 17) or ny.dayofweek == 5:
                continue
            e, l_, tw = ea(b), lab(b), twin_deadline(b, 5)
            tot += 1
            diff += e != l_
            diff_twin += e != tw
            rows.append((b.strftime("%a %H:%M UTC"), fmt(b), fmt(e), fmt(l_), "SAME" if e == l_ else "DIFF",
                         "" if e == tw else "twin!=EA"))
    for r in rows:
        print("  dec %-14s (%s) -> EA %s | lab %s  %s %s" % r)
print(f"\nPart A: {tot} (bucket, tc=bucket) cases, EA != lab: {diff}, EA != twin: {diff_twin}")

print("\n=== Part B: Sunday-open window (orders live Sun 18:00 NY -> 24:00 UTC)")
for sunday in ("2025-01-12", "2025-06-15", "2025-03-09", "2025-11-02", "2024-12-29"):
    s = pd.Timestamp(sunday, tz="UTC")
    b = s + pd.Timedelta(hours=20)                          # EA decision: Sunday 20:00 UTC bucket start
    fri = s - pd.Timedelta(days=2)
    fri_close = pd.Timestamp(fri.strftime("%Y-%m-%d") + " 17:00").tz_localize(NY).tz_convert("UTC")
    for tc, why in ((fri_close, "Fri last bar 16:59 NY"), (fri_close - pd.Timedelta(minutes=1), "Fri last bar 16:58 NY")):
        print(f"  Sun {sunday}: EA dec {fmt(b)} -> {fmt(ea(b))} | lab tc {fmt(tc)} ({why}) -> {fmt(lab(tc))}"
              f" | EA with tc -> {fmt(ea(tc))}")
