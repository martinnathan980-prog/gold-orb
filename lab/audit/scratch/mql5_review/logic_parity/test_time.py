"""Check the ported EA time functions against zoneinfo (tzdata) for 2013-2030."""
import datetime as dt
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from mql5_time import (H, IsEUDST, IsUSDST, LastSunday, NthSunday, NYfromUTC, ParisFromUTC,  # noqa: E402
                       ToServer, ToUTC, UTCfromNY, GO_TZ_EU, GO_TZ_US, TimeToStruct)

NY, PAR, ATH = ZoneInfo("America/New_York"), ZoneInfo("Europe/Paris"), ZoneInfo("Europe/Athens")
UTC = dt.timezone.utc


def ts(d):
    return int(d.replace(tzinfo=UTC).timestamp())


def off(z, t):
    return int(dt.datetime.fromtimestamp(t, UTC).astimezone(z).utcoffset().total_seconds())


bad = []
print("year  US-DST start (UTC)      US-DST end (UTC)        EU start             EU end")
for y in range(2013, 2031):
    s, e = NthSunday(y, 3, 2) + 7 * H, NthSunday(y, 11, 1) + 6 * H
    es, ee = LastSunday(y, 3) + H, LastSunday(y, 10) + H
    f = lambda t: dt.datetime.fromtimestamp(t, UTC).strftime("%a %m-%d %H:%M")
    print(y, f(s), "|", f(e), "|", f(es), "|", f(ee))
    # exact transition instants from zoneinfo
    for (t, z, want_dst) in ((s, NY, True), (e, NY, False), (es, PAR, True), (ee, PAR, False)):
        before, after = off(z, t - 1), off(z, t)
        if before == after:
            bad.append(("no transition at", y, z, f(t)))

# hour-by-hour (every 15 min) comparison 2013-2030
t0, t1 = ts(dt.datetime(2013, 1, 1)), ts(dt.datetime(2031, 1, 1))
n = 0
mism = {"US": 0, "EU": 0, "NYfromUTC": 0, "Paris": 0, "ToUTC_US": 0, "ToUTC_EU": 0,
        "ToUTC_US_open": 0, "ToUTC_EU_open": 0, "UTCfromNY": 0, "UTCfromNY_open": 0}
examples = {}
for t in range(t0, t1, 900):
    n += 1
    us = off(NY, t) == -4 * H
    eu = off(PAR, t) == 2 * H
    if IsUSDST(t) != us:
        mism["US"] += 1; examples.setdefault("US", t)
    if IsEUDST(t) != eu:
        mism["EU"] += 1; examples.setdefault("EU", t)
    if NYfromUTC(t) != t + off(NY, t):
        mism["NYfromUTC"] += 1
    if ParisFromUTC(t) != t + off(PAR, t):
        mism["Paris"] += 1
    # server clock = NY + 7h (US rule) / EET-EEST (EU rule = Athens)
    srv_us = t + off(NY, t) + 7 * H
    srv_eu = t + off(ATH, t)
    wd = dt.datetime.fromtimestamp(t, UTC).astimezone(NY)
    # market open?  Sun 18:00 NY -> Fri 17:00 NY, minus the 17:00-18:00 daily break
    mo = not (wd.weekday() == 5 or (wd.weekday() == 6 and wd.hour < 18) or (wd.weekday() == 4 and wd.hour >= 17)
              or wd.hour == 17)
    if ToUTC(srv_us, GO_TZ_US) != t:
        mism["ToUTC_US"] += 1; examples.setdefault("ToUTC_US", t)
        if mo:
            mism["ToUTC_US_open"] += 1
    if ToServer(t, GO_TZ_US) != srv_us:
        mism.setdefault("ToServer_US", 0); mism["ToServer_US"] += 1
    if ToUTC(srv_eu, GO_TZ_EU) != t:
        mism["ToUTC_EU"] += 1; examples.setdefault("ToUTC_EU", t)
        if mo:
            mism["ToUTC_EU_open"] += 1
    # UTCfromNY on the NY wall clock
    ny_wall = t + off(NY, t)
    if UTCfromNY(ny_wall) != t:
        mism["UTCfromNY"] += 1; examples.setdefault("UTCfromNY", t)
        if mo:
            mism["UTCfromNY_open"] += 1
print(f"\nchecked {n} instants (every 15 min 2013-2030)")
for k, v in mism.items():
    ex = examples.get(k)
    exs = dt.datetime.fromtimestamp(ex, UTC).strftime("%Y-%m-%d %H:%M %a UTC") if ex else ""
    print(f"  {k:16s} mismatches {v:6d}  {exs}")
print("transition sanity:", "OK" if not bad else bad)
# day_of_week convention check
print("TimeToStruct(2026-11-01 00:00).day_of_week =", TimeToStruct(ts(dt.datetime(2026, 11, 1))).day_of_week, "(Sunday -> 0)")
