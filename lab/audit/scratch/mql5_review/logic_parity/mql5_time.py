"""Line-for-line Python port of the EA's time functions (GoldOrb_Donchian4H.mq5 lines 99-195).

MQL5 datetime = int seconds since 1970-01-01 (no tz).  TimeToStruct().day_of_week: 0 = Sunday.
StructToTime ignores day_of_week / day_of_year.  Everything here works on plain ints, exactly
like the EA, so it can be compared against zoneinfo / pandas (the lab).
"""
import calendar
import datetime as _dt

H = 3600
D = 86400


class MqlDateTime:
    __slots__ = ("year", "mon", "day", "hour", "min", "sec", "day_of_week", "day_of_year")

    def __init__(self):
        self.year = self.mon = self.day = self.hour = self.min = self.sec = 0
        self.day_of_week = self.day_of_year = 0


def TimeToStruct(t):
    x = MqlDateTime()
    d = _dt.datetime(1970, 1, 1) + _dt.timedelta(seconds=int(t))
    x.year, x.mon, x.day, x.hour, x.min, x.sec = d.year, d.month, d.day, d.hour, d.minute, d.second
    x.day_of_week = (d.weekday() + 1) % 7          # Python Mon=0 -> MQL Sun=0
    x.day_of_year = d.timetuple().tm_yday - 1
    return x


def StructToTime(x):
    # MQL5 normalises out-of-range day like mktime; the EA never passes one (day <= 14)
    base = calendar.timegm((x.year, x.mon, 1, x.hour, x.min, x.sec, 0, 0, 0))
    return base + (x.day - 1) * D


# ----------------------------------------------------------------- EA lines 99-121
def NthSunday(year, month, n):
    d = MqlDateTime()
    d.year, d.mon, d.day = year, month, 1
    x = TimeToStruct(StructToTime(d))
    first = 1 if x.day_of_week == 0 else 1 + (7 - x.day_of_week)
    d.day = first + 7 * (n - 1)
    return StructToTime(d)


def LastSunday(year, month):
    d = MqlDateTime()
    d.year, d.mon, d.day = year, month + 1, 1
    if d.mon == 13:
        d.mon, d.year = 1, year + 1
    t = StructToTime(d) - 86400
    x = TimeToStruct(t)
    return t - x.day_of_week * 86400


# ----------------------------------------------------------------- EA lines 124-154
def IsUSDST(utc):
    x = TimeToStruct(utc)
    return NthSunday(x.year, 3, 2) + 7 * H <= utc < NthSunday(x.year, 11, 1) + 6 * H


def IsEUDST(utc):
    x = TimeToStruct(utc)
    return LastSunday(x.year, 3) + H <= utc < LastSunday(x.year, 10) + H


GO_TZ_US, GO_TZ_EU, GO_TZ_FIXED = 0, 1, 2


def RuleOffsetSecForUTC(utc, tz=GO_TZ_US, fixed_h=2):
    if tz == GO_TZ_FIXED:
        return fixed_h * H
    if tz == GO_TZ_EU:
        return 3 * H if IsEUDST(utc) else 2 * H
    return 3 * H if IsUSDST(utc) else 2 * H


def ToUTC(server_time, tz=GO_TZ_US):
    return server_time - RuleOffsetSecForUTC(server_time - 2 * H, tz)


def ToServer(utc, tz=GO_TZ_US):
    return utc + RuleOffsetSecForUTC(utc, tz)


def NYfromUTC(utc):
    return utc - (4 if IsUSDST(utc) else 5) * H


def UTCfromNY(ny):
    return ny + (4 if IsUSDST(ny + 5 * H) else 5) * H


def ParisFromUTC(utc):
    return utc + (2 if IsEUDST(utc) else 1) * H


# ----------------------------------------------------------------- EA lines 158-195
def DeadlineUTC(decision_utc, days=5):
    td = NYfromUTC(decision_utc) + 7 * H
    added = 0
    while added < days:
        td += 86400
        x = TimeToStruct(td)
        if 1 <= x.day_of_week <= 5:
            added += 1
    ny = td - 7 * H - 300
    y = TimeToStruct(ny)
    mins = y.hour * 60 + y.min
    weekend = (y.day_of_week == 6) or (y.day_of_week == 0 and mins < 18 * 60) or (y.day_of_week == 5 and mins >= 17 * 60)
    brk = 17 * 60 <= mins < 18 * 60
    if weekend:
        while True:
            z = TimeToStruct(ny)
            if z.day_of_week == 5:
                break
            ny -= 86400
    if weekend or brk:
        w = TimeToStruct(ny)
        w.hour, w.min, w.sec = 16, 59, 0
        ny = StructToTime(w)
    return UTCfromNY(ny)


def BucketUTC(utc):
    return (int(utc) // 14400) * 14400
