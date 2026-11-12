//+------------------------------------------------------------------+
//| RobotClock.mqh  -  server clock <-> UTC, shared by every rule     |
//|                                                                  |
//| FP Markets server clock = New York + 7 h: UTC+2 while New York    |
//| is on standard time, UTC+3 during US daylight saving time. The    |
//| offset is a whole number of hours, so a server hour is a UTC hour |
//| (the lab's hour grid is UTC: r2/tracks/crypto/strategy.py).        |
//| Same rule as lab/live_ai/pont.py server_to_utc and as             |
//| lab/build_fp_frames.py (srv = New York + 7 h).                    |
//| The US clock changes on Sundays (markets closed), so converting a |
//| server time with the offset of (server - 2 h) is exact whenever a |
//| market is open.                                                  |
//+------------------------------------------------------------------+
#ifndef ROBOT_CLOCK_MQH
#define ROBOT_CLOCK_MQH

// n-th Sunday (n = 1, 2, ...) of a month, at 00:00 of that day (same clock as the inputs)
datetime ClkNthSunday(const int year, const int month, const int n)
  {
   MqlDateTime d;
   ZeroMemory(d);
   d.year = year;
   d.mon = month;
   d.day = 1;
   datetime first = StructToTime(d);
   MqlDateTime x;
   TimeToStruct(first, x);
   int day = 1 + (7 - x.day_of_week) % 7 + 7 * (n - 1);
   return first + (day - 1) * 86400;
  }

// US daylight saving time: 2nd Sunday of March 07:00 UTC (02:00 EST) to 1st Sunday of November 06:00 UTC (02:00 EDT)
bool ClkUsDst(const datetime utc)
  {
   MqlDateTime x;
   TimeToStruct(utc, x);
   datetime a = ClkNthSunday(x.year, 3, 2) + 7 * 3600;
   datetime b = ClkNthSunday(x.year, 11, 1) + 6 * 3600;
   return utc >= a && utc < b;
  }

int      ClkOffsetSec(const datetime utc)   { return ClkUsDst(utc) ? 3 * 3600 : 2 * 3600; }
datetime ClkServerToUtc(const datetime srv) { return srv - ClkOffsetSec(srv - 2 * 3600); }
datetime ClkUtcToServer(const datetime utc) { return utc + ClkOffsetSec(utc); }

// day of the week of a time on its own clock (0 = Sunday ... 6 = Saturday, as MqlDateTime.day_of_week)
int ClkDow(const datetime t)
  {
   MqlDateTime x;
   TimeToStruct(t, x);
   return x.day_of_week;
  }

// HHMM of a time on its own clock
int ClkHHMM(const datetime t)
  {
   MqlDateTime x;
   TimeToStruct(t, x);
   return x.hour * 100 + x.min;
  }

// "YYYY.MM.DD HH:MM" for the journal (its own clock)
string ClkStr(const datetime t)
  {
   return TimeToString(t, TIME_DATE | TIME_MINUTES);
  }
#endif
