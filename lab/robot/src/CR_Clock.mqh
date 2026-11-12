//+------------------------------------------------------------------+
//| CR_Clock.mqh - time (SPEC 2.1). Owner: step A.                    |
//|                                                                  |
//| A rule-based clock: no table to keep up to date, any year from   |
//| 1970 to 2200. check/test_clock.py compares it with zoneinfo,     |
//| pont.server_to_utc, pandas BDay, trend.add_trading_days,         |
//| idxus_lib.us_holidays, stake.prepare and the in-sample bars.     |
//| Times are UTC seconds unless a name says otherwise. A wall-clock |
//| time (server, New York, London) is the seconds of that clock     |
//| read as if it were UTC, as MQL5 does with TimeTradeServer().     |
//| Every value is a time at or after 1970.                          |
//|                                                                  |
//| Summer time, UTC instants:                                       |
//|   US  2nd Sunday of March 07:00 to 1st Sunday of November 06:00  |
//|       (before 2007: 1st Sunday of April to last Sunday of        |
//|       October, at the same hours)                                |
//|   UK  last Sunday of March 01:00 to last Sunday of October 01:00 |
//| Server = New York + 7 h (FP Markets): UTC = server - 3 h if the  |
//| US is on summer time at (server - 3 h), else server - 2 h        |
//| (pont.py:37-43). Wall clock -> UTC: a time inside the spring gap |
//| (New York 02:00-02:59, London 01:00-01:59) is read on the winter |
//| clock, so it lands 1 h later on the summer clock (New York 02:30 |
//| -> 03:30 EDT); a time of the repeated autumn hour takes the      |
//| summer-time instant (the first one).                             |
//|                                                                  |
//| Known closures (New York clock; merged when they overlap or      |
//| touch, so that Good Friday and its weekend are one closure):     |
//|   XAU  Monday-Thursday 17:00-18:00; Friday 17:00 to Sunday 18:00;|
//|        the NYSE's observed Good Friday, Christmas and New Year:  |
//|        [day before 17:00, day 18:00); the other NYSE full        |
//|        holidays (not the special closures): [13:00, 18:00); the  |
//|        Friday after Thanksgiving and a Christmas Eve half day:   |
//|        [13:45, 18:00). July 3 half days and special closures     |
//|        (2018-12-05, 2025-01-09) are normal gold days.            |
//|   IDX  Monday-Thursday 16:15-18:00; Friday 16:15 to Sunday       |
//|        18:00. No holiday closure: no US100 rule holds a position |
//|        into one; CR_Bars masks the half days after 13:15.        |
//|   CRY  Friday 16:55 to Sunday 17:00 (server Friday 23:55 to      |
//|        Monday 00:00).                                            |
//|   plus the typed windows of InpExtraClosures (below).            |
//| The broker's own session ends are not known here: the follower   |
//| passes one to ClkRealExitMinute when it has it.                  |
//|                                                                  |
//| NYSE calendar: a port of idxus_lib.us_holidays (idxus_lib.py:    |
//| 53-83): full closures and 13:00 half days by rule for any year,  |
//| Juneteenth from 2022, the special closures 2018-12-05 and        |
//| 2025-01-09; then the typed NYSE and HALF entries, which win over |
//| the rules. Weekends are not listed: ClkNyse says OPEN for them.  |
//|                                                                  |
//| InpExtraClosures: entries separated by ';', each one of          |
//|   NYSE yyyy.mm.dd                   a full NYSE closure          |
//|   HALF yyyy.mm.dd                   an NYSE 13:00 half day       |
//|   XAU|IDX|CRY yyyy.mm.dd hh:mm-yyyy.mm.dd hh:mm                  |
//|                                     a closure window, New York   |
//| Spaces and tabs may be repeated; spaces around '-' are allowed;  |
//| empty entries are skipped. Refused: another kind, a date that    |
//| does not exist or lies outside 2000-2100, a NYSE or HALF date on |
//| a weekend, a window that does not end after it starts or lasts   |
//| more than 7 days, more than 64 entries. Typed NYSE and HALF      |
//| dates change ClkNyse only, not the gold closures (a day of       |
//| mourning is a normal gold day): a gold, US100 or crypto closure  |
//| is typed as a window. MetaTrader keeps at most 255 characters    |
//| of "InpExtraClosures=value": about 6 windows or 14 dates.        |
//|                                                                  |
//| API (the S0 signatures, kept):                                   |
//|   ClkInit(extra, err)            typed closures; false and err   |
//|                                  when an entry is refused. Call  |
//|                                  it at every OnInit (it resets   |
//|                                  the closure caches)             |
//|   ClkUsDst(utc) ClkUkDst(utc)    summer time in force            |
//|   ClkServerToUtc ClkUtcToServer  server = New York + 7 h         |
//|   ClkUtcToNy ClkNyToUtc          New York wall clock             |
//|   ClkUtcToLdn ClkLdnToUtc        London wall clock               |
//|   ClkDay ClkDow ClkMinOfDay ClkYear   on the time's own clock:   |
//|                                  00:00 of its date, 0 = Sunday,  |
//|                                  minute of the day, year         |
//|   ClkServerDay(utc)              server date 00:00 (server       |
//|                                  clock) = the 17:00-NY trading   |
//|                                  day (data.py:45-49)             |
//|   ClkServerWeek(utc)             server Monday 00:00 of the week |
//|                                  (stake.py:89-91, 131)           |
//|   ClkAddTradingDays(utc, n)      n business days later, at the   |
//|                                  same server time; a weekend     |
//|                                  start counts Monday as day 1    |
//|                                  (trend/strategy.py:107-111)     |
//|   ClkBusinessDays(date, n)       pandas BDay(n) on any clock, no |
//|                                  holidays, time of day kept; n   |
//|                                  may be negative (a weekend then |
//|                                  counts Friday as day 1)         |
//|   ClkNyse(ny_date)               CR_NYSE_OPEN / FULL / HALF      |
//|   ClkInClosure(fam, utc, c0, c1) true when utc lies in a known   |
//|                                  closure; [c0, c1) = the whole   |
//|                                  merged closure, UTC (0, 0 when  |
//|                                  false)                          |
//|   ClkRealExitMinute(x, fam, gap, fri_end_utc)  follower only:    |
//|                                  the minute at whose barrier the |
//|                                  real position closes for a time |
//|                                  exit x (see the function)       |
//|   ClkRuleOffset(utc)             server - UTC by the rule, s     |
//|   ClkStr(t)                      "YYYY.MM.DD HH:MM", own clock   |
//| Added by step A:                                                 |
//|   ClkNextClosure(fam, utc, c0, c1)  the known closure holding    |
//|                                  utc, else the first one after   |
//|                                  it (false when none within 256  |
//|                                  days)                           |
//| The other Clk* functions below are internal helpers.             |
//+------------------------------------------------------------------+
#ifndef CR_CLOCK_MQH
#define CR_CLOCK_MQH
#include "CR_Types.mqh"

#define CR_CLK_Y0 1970                 // first year of the year caches
#define CR_CLK_NY 231                  // years cached: 1970 to 2200 (another year is computed at each call)
#define CR_CLK_NY4 924                 // CR_CLK_NY x 4
#define CR_CLK_HMAX 20                 // NYSE dates kept per year (at most 12 full, 3 half and 1 special)
#define CR_CLK_NYS 232                 // CR_CLK_NY + 1: the last slot holds a year outside the cache
#define CR_CLK_NH 4640                 // CR_CLK_NYS x CR_CLK_HMAX
#define CR_CLK_MAXT 64                 // typed closures kept
#define CR_CLK_TMAXLEN 604800          // longest typed window: 7 days, in seconds
#define CR_CLK_SESS_MAX 43200          // a broker session end counts when at most 12 h before a known closure
// gold holiday closure of a NYSE date (SPEC 2.1), New York clock
#define CR_CLK_G_NONE 0
#define CR_CLK_G_LONG 1                // observed Good Friday, Christmas, New Year: [day before 17:00, day 18:00)
#define CR_CLK_G_SHORT 2               // the other full holidays, special closures excepted: [13:00, 18:00)
#define CR_CLK_G_1345 3                // the Friday after Thanksgiving, a Christmas Eve half day: [13:45, 18:00)

// ---- year caches (filled at first use; they do not depend on the inputs)
bool g_clk_dok[CR_CLK_NY] = {false};   // summer-time instants computed for the year
long g_clk_dst[CR_CLK_NY4] = {0};      // per year: US on, US off, UK on, UK off (UTC)
bool g_clk_hok[CR_CLK_NY] = {false};   // NYSE dates computed for the year
int  g_clk_hspare = -1;                // year held by the spare slot CR_CLK_NY (-1 = none)
int  g_clk_hn[CR_CLK_NYS] = {0};       // NYSE dates of the slot
long g_clk_hd[CR_CLK_NH] = {0};        // day number of the date (days since 1970-01-01)
int  g_clk_hk[CR_CLK_NH] = {0};        // CR_NYSE_FULL or CR_NYSE_HALF
int  g_clk_hg[CR_CLK_NH] = {0};        // CR_CLK_G_*

// ---- typed closures (InpExtraClosures, ClkInit)
int      g_clk_nt = 0;
int      g_clk_tk[CR_CLK_MAXT];        // 0 NYSE, 1 HALF, 2 window
int      g_clk_tf[CR_CLK_MAXT];        // family of a window (-1 otherwise)
long     g_clk_tday[CR_CLK_MAXT];      // NYSE / HALF: day number of the New York date (-1 otherwise)
datetime g_clk_ta[CR_CLK_MAXT];        // window [ta, tb), UTC
datetime g_clk_tb[CR_CLK_MAXT];

// ---- closures of one family around a time (UTC), sorted and merged by ClkWorkBuild
datetime g_clk_wa[];
datetime g_clk_wb[];
int      g_clk_wn = 0;

// ---- segment cache, two slots per family (slot = 2 x family + k): a closure [sa, sb) (si = true), or a gap [sa, sb)
// ---- between closures followed by the closure [sna, snb) (0, 0: none found)
bool     g_clk_sv[6] = {false};
bool     g_clk_si[6] = {false};
datetime g_clk_sa[6] = {0};
datetime g_clk_sb[6] = {0};
datetime g_clk_sna[6] = {0};
datetime g_clk_snb[6] = {0};
int      g_clk_slast[3] = {0};         // slot (0 or 1) of the family used last; the other one is replaced

//+------------------------------------------------------------------+
//| Calendar arithmetic (proleptic Gregorian, H. Hinnant's formulas) |
//+------------------------------------------------------------------+
// day number (days since 1970-01-01) of a calendar date
long ClkDaysFromCivil(const int y, const int m, const int d)
  {
   long yy = (long)y - ((m <= 2) ? 1 : 0);
   long era = ((yy >= 0) ? yy : yy - 399) / 400;
   long yoe = yy - era * 400;
   long mp = (m > 2) ? m - 3 : m + 9;
   long doy = (153 * mp + 2) / 5 + d - 1;
   long doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
   return era * 146097 + doe - 719468;
  }

// calendar date of a day number
void ClkCivil(const long day_no, int &y, int &m, int &d)
  {
   long z = day_no + 719468;
   long era = ((z >= 0) ? z : z - 146096) / 146097;
   long doe = z - era * 146097;
   long yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
   long doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
   long mp = (5 * doy + 2) / 153;
   d = (int)(doy - (153 * mp + 2) / 5 + 1);
   m = (int)((mp < 10) ? mp + 3 : mp - 9);
   y = (int)(yoe + era * 400 + ((m <= 2) ? 1 : 0));
  }

// day number of a time, on its own clock (floor division)
long ClkDayNo(const datetime t)
  {
   long s = (long)t;
   long q = s / 86400;
   if(s % 86400 < 0) q--;
   return q;
  }

// day of the week of a day number: 0 = Sunday ... 6 = Saturday (1970-01-01 was a Thursday)
int ClkDowOfDay(const long day_no) { return (int)(((day_no + 4) % 7 + 7) % 7); }

int ClkMonthDays(const int y, const int m)
  {
   long next_first = (m == 12) ? ClkDaysFromCivil(y + 1, 1, 1) : ClkDaysFromCivil(y, m + 1, 1);
   return (int)(next_first - ClkDaysFromCivil(y, m, 1));
  }

// day number of the n-th weekday wd (0 = Sunday ... 6 = Saturday) of a month; n = -1: the last one
long ClkNthWeekday(const int y, const int m, const int wd, const int n)
  {
   if(n < 0)
     {
      long last_day = ((m == 12) ? ClkDaysFromCivil(y + 1, 1, 1) : ClkDaysFromCivil(y, m + 1, 1)) - 1;
      return last_day - (ClkDowOfDay(last_day) - wd + 7) % 7;
     }
   long first = ClkDaysFromCivil(y, m, 1);
   return first + (wd - ClkDowOfDay(first) + 7) % 7 + 7 * (n - 1);
  }

//+------------------------------------------------------------------+
//| The time's own clock                                             |
//+------------------------------------------------------------------+
int ClkYear(const datetime t)
  {
   int y = 0, m = 0, d = 0;
   ClkCivil(ClkDayNo(t), y, m, d);
   return y;
  }

datetime ClkDay(const datetime t) { return (datetime)(ClkDayNo(t) * 86400); }
int      ClkDow(const datetime t) { return ClkDowOfDay(ClkDayNo(t)); }
int      ClkMinOfDay(const datetime t) { return (int)(((long)t - ClkDayNo(t) * 86400) / 60); }

//+------------------------------------------------------------------+
//| Summer time and the three clocks                                 |
//+------------------------------------------------------------------+
// summer-time instants of a year, UTC
void ClkDstCompute(const int y, long &us_on, long &us_off, long &uk_on, long &uk_off)
  {
   if(y >= 2007)
     {
      us_on = ClkNthWeekday(y, 3, 0, 2) * 86400 + 7 * 3600;
      us_off = ClkNthWeekday(y, 11, 0, 1) * 86400 + 6 * 3600;
     }
   else
     {
      us_on = ClkNthWeekday(y, 4, 0, 1) * 86400 + 7 * 3600;
      us_off = ClkNthWeekday(y, 10, 0, -1) * 86400 + 6 * 3600;
     }
   uk_on = ClkNthWeekday(y, 3, 0, -1) * 86400 + 3600;
   uk_off = ClkNthWeekday(y, 10, 0, -1) * 86400 + 3600;
  }

void ClkDstYear(const int y, long &us_on, long &us_off, long &uk_on, long &uk_off)
  {
   int k = y - CR_CLK_Y0;
   if(k < 0 || k >= CR_CLK_NY)
     {
      ClkDstCompute(y, us_on, us_off, uk_on, uk_off);
      return;
     }
   if(!g_clk_dok[k])
     {
      long a = 0, b = 0, c = 0, e = 0;
      ClkDstCompute(y, a, b, c, e);
      g_clk_dst[4 * k] = a;
      g_clk_dst[4 * k + 1] = b;
      g_clk_dst[4 * k + 2] = c;
      g_clk_dst[4 * k + 3] = e;
      g_clk_dok[k] = true;
     }
   us_on = g_clk_dst[4 * k];
   us_off = g_clk_dst[4 * k + 1];
   uk_on = g_clk_dst[4 * k + 2];
   uk_off = g_clk_dst[4 * k + 3];
  }

bool ClkUsDst(const datetime utc)
  {
   long a = 0, b = 0, c = 0, e = 0;
   ClkDstYear(ClkYear(utc), a, b, c, e);
   return (long)utc >= a && (long)utc < b;
  }

bool ClkUkDst(const datetime utc)
  {
   long a = 0, b = 0, c = 0, e = 0;
   ClkDstYear(ClkYear(utc), a, b, c, e);
   return (long)utc >= c && (long)utc < e;
  }

datetime ClkServerToUtc(const datetime srv)
  {
   datetime u3 = srv - 3 * 3600;
   return ClkUsDst(u3) ? u3 : u3 + 3600;
  }

datetime ClkUtcToServer(const datetime utc) { return utc + (ClkUsDst(utc) ? 3 * 3600 : 2 * 3600); }
datetime ClkUtcToNy(const datetime utc) { return ClkUtcToServer(utc) - 7 * 3600; }
datetime ClkNyToUtc(const datetime ny) { return ClkServerToUtc(ny + 7 * 3600); }
datetime ClkUtcToLdn(const datetime utc) { return utc + (ClkUkDst(utc) ? 3600 : 0); }

datetime ClkLdnToUtc(const datetime ldn)
  {
   datetime u = ldn - 3600;                       // the summer-time reading
   return ClkUkDst(u) ? u : ldn;
  }

datetime ClkServerDay(const datetime utc) { return ClkDay(ClkUtcToServer(utc)); }

datetime ClkServerWeek(const datetime utc)
  {
   long dn = ClkDayNo(ClkUtcToServer(utc));
   return (datetime)((dn - (ClkDowOfDay(dn) + 6) % 7) * 86400);
  }

long ClkRuleOffset(const datetime utc) { return ClkUsDst(utc) ? 3 * 3600 : 2 * 3600; }

//+------------------------------------------------------------------+
//| Business days (pandas BDay, no holidays)                         |
//+------------------------------------------------------------------+
// n business days after a day number. A weekend day first rolls to Monday (n >= 0) or to Friday (n < 0), and that
// day counts as the first one moved (pandas: Saturday + BDay(1) = Monday, Saturday + BDay(-1) = Friday, + BDay(0) =
// Monday)
long ClkBDayNo(const long day_no, const int n)
  {
   long d = day_no;
   int k = n;
   int w = ClkDowOfDay(d);
   if(w == 6 || w == 0)
     {
      if(k >= 0)
        {
         d += (w == 6) ? 2 : 1;
         if(k > 0) k--;
        }
      else
        {
         d -= (w == 6) ? 1 : 2;
         k++;
        }
     }
   while(k > 0)
     {
      d++;
      w = ClkDowOfDay(d);
      if(w != 0 && w != 6) k--;
     }
   while(k < 0)
     {
      d--;
      w = ClkDowOfDay(d);
      if(w != 0 && w != 6) k++;
     }
   return d;
  }

datetime ClkBusinessDays(const datetime date, const int n)
  {
   long dn = ClkDayNo(date);
   return (datetime)((long)date + (ClkBDayNo(dn, n) - dn) * 86400);
  }

// trend/strategy.py:107-111: the server date-time (New York + 7 h) + BDay(n), back to UTC on the New York clock. The
// result is never in a summer-time gap or repeated hour: it lies between 17:00 New York the day before a weekday and
// 17:00 on that weekday, and New York changes clocks on Sundays at 02:00.
datetime ClkAddTradingDays(const datetime utc, const int n)
  {
   datetime srv = ClkUtcToServer(utc);
   long dn = ClkDayNo(srv);
   return ClkServerToUtc((datetime)((long)srv + (ClkBDayNo(dn, n) - dn) * 86400));
  }

//+------------------------------------------------------------------+
//| NYSE calendar (port of idxus_lib.us_holidays)                    |
//+------------------------------------------------------------------+
// Easter Sunday (idxus_lib._easter: the anonymous Gregorian algorithm)
long ClkEaster(const int y)
  {
   int a = y % 19, b = y / 100, c = y % 100;
   int d = b / 4, e = b % 4;
   int f = (b + 8) / 25;
   int g = (b - f + 1) / 3;
   int h = (19 * a + b - d - g + 15) % 30;
   int i = c / 4, k = c % 4;
   int l = (32 + 2 * e + 2 * i - h - k) % 7;
   int m = (a + 11 * h + 22 * l) / 451;
   int mo = (h + l - 7 * m + 114) / 31;
   int da = (h + l - 7 * m + 114) % 31 + 1;
   return ClkDaysFromCivil(y, mo, da);
  }

// NYSE rule: a Saturday holiday is observed on the Friday before, a Sunday one on the Monday after
long ClkObserved(const long day_no)
  {
   int w = ClkDowOfDay(day_no);
   if(w == 6) return day_no - 1;
   if(w == 0) return day_no + 1;
   return day_no;
  }

// adds a date to a year slot. A date already listed keeps its kind ("half -= full"); a special closure on a rule
// holiday makes that holiday a normal gold day unless it is a long closure (idxus_lib.py:74, gen_dbl.calendars)
void ClkHolAdd(const int slot, const long day_no, const int kind, const int gold, const bool special)
  {
   int base = slot * CR_CLK_HMAX;
   int n = g_clk_hn[slot];
   for(int i = 0; i < n; i++)
      if(g_clk_hd[base + i] == day_no)
        {
         if(special && g_clk_hg[base + i] == CR_CLK_G_SHORT) g_clk_hg[base + i] = CR_CLK_G_NONE;
         return;
        }
   if(n >= CR_CLK_HMAX) return;
   g_clk_hd[base + n] = day_no;
   g_clk_hk[base + n] = kind;
   g_clk_hg[base + n] = gold;
   g_clk_hn[slot] = n + 1;
  }

void ClkHolBuild(const int slot, const int y)
  {
   g_clk_hn[slot] = 0;
   long jan1 = ClkDaysFromCivil(y, 1, 1);
   int w1 = ClkDowOfDay(jan1);
   if(w1 == 0) ClkHolAdd(slot, jan1 + 1, CR_NYSE_FULL, CR_CLK_G_LONG, false);            // New Year on a Sunday: Monday
   else if(w1 != 6) ClkHolAdd(slot, jan1, CR_NYSE_FULL, CR_CLK_G_LONG, false);           // (a Saturday one is not observed)
   ClkHolAdd(slot, ClkNthWeekday(y, 1, 1, 3), CR_NYSE_FULL, CR_CLK_G_SHORT, false);      // Martin Luther King
   ClkHolAdd(slot, ClkNthWeekday(y, 2, 1, 3), CR_NYSE_FULL, CR_CLK_G_SHORT, false);      // Presidents' day
   ClkHolAdd(slot, ClkEaster(y) - 2, CR_NYSE_FULL, CR_CLK_G_LONG, false);                // Good Friday
   ClkHolAdd(slot, ClkNthWeekday(y, 5, 1, -1), CR_NYSE_FULL, CR_CLK_G_SHORT, false);     // Memorial day
   if(y >= 2022) ClkHolAdd(slot, ClkObserved(ClkDaysFromCivil(y, 6, 19)), CR_NYSE_FULL, CR_CLK_G_SHORT, false);   // Juneteenth
   ClkHolAdd(slot, ClkObserved(ClkDaysFromCivil(y, 7, 4)), CR_NYSE_FULL, CR_CLK_G_SHORT, false);
   ClkHolAdd(slot, ClkNthWeekday(y, 9, 1, 1), CR_NYSE_FULL, CR_CLK_G_SHORT, false);      // Labor day
   long tg = ClkNthWeekday(y, 11, 4, 4);                                                  // Thanksgiving
   ClkHolAdd(slot, tg, CR_NYSE_FULL, CR_CLK_G_SHORT, false);
   ClkHolAdd(slot, ClkObserved(ClkDaysFromCivil(y, 12, 25)), CR_NYSE_FULL, CR_CLK_G_LONG, false);
   if(y == 2018) ClkHolAdd(slot, ClkDaysFromCivil(2018, 12, 5), CR_NYSE_FULL, CR_CLK_G_NONE, true);   // days of mourning
   if(y == 2025) ClkHolAdd(slot, ClkDaysFromCivil(2025, 1, 9), CR_NYSE_FULL, CR_CLK_G_NONE, true);
   ClkHolAdd(slot, tg + 1, CR_NYSE_HALF, CR_CLK_G_1345, false);                            // Friday after Thanksgiving
   long jul4 = ClkDaysFromCivil(y, 7, 4);
   int w4 = ClkDowOfDay(jul4);
   if(w4 >= 2 && w4 <= 5) ClkHolAdd(slot, jul4 - 1, CR_NYSE_HALF, CR_CLK_G_NONE, false);  // July 3 before a Tuesday-Friday July 4
   long dec24 = ClkDaysFromCivil(y, 12, 24);
   int w24 = ClkDowOfDay(dec24);
   if(w24 >= 1 && w24 <= 4) ClkHolAdd(slot, dec24, CR_NYSE_HALF, CR_CLK_G_1345, false);  // Christmas Eve, Monday-Thursday
  }

int ClkHolSlot(const int y)
  {
   int k = y - CR_CLK_Y0;
   if(k >= 0 && k < CR_CLK_NY)
     {
      if(!g_clk_hok[k])
        {
         ClkHolBuild(k, y);
         g_clk_hok[k] = true;
        }
      return k;
     }
   if(g_clk_hspare != y)
     {
      ClkHolBuild(CR_CLK_NY, y);
      g_clk_hspare = y;
     }
   return CR_CLK_NY;
  }

// the built-in NYSE kind of a New York date (day number), and its gold closure kind
int ClkHolKind(const long day_no, int &gold)
  {
   gold = CR_CLK_G_NONE;
   int y = 0, m = 0, d = 0;
   ClkCivil(day_no, y, m, d);
   int slot = ClkHolSlot(y);
   int base = slot * CR_CLK_HMAX;
   for(int i = 0; i < g_clk_hn[slot]; i++)
      if(g_clk_hd[base + i] == day_no)
        {
         gold = g_clk_hg[base + i];
         return g_clk_hk[base + i];
        }
   return CR_NYSE_OPEN;
  }

int ClkNyse(const datetime ny_date)
  {
   long dn = ClkDayNo(ny_date);
   int typed = CR_NYSE_OPEN;
   for(int i = 0; i < g_clk_nt; i++)
     {
      if(g_clk_tday[i] != dn) continue;
      if(g_clk_tk[i] == 0) typed = CR_NYSE_FULL;
      else if(g_clk_tk[i] == 1 && typed == CR_NYSE_OPEN) typed = CR_NYSE_HALF;
     }
   if(typed != CR_NYSE_OPEN) return typed;
   int gold = 0;
   return ClkHolKind(dn, gold);
  }

//+------------------------------------------------------------------+
//| Known closures                                                   |
//+------------------------------------------------------------------+
void ClkWorkPut(const datetime a, const datetime b)
  {
   if(b <= a) return;
   if(g_clk_wn >= ArraySize(g_clk_wa))
     {
      int cap = g_clk_wn + 64;
      if(ArrayResize(g_clk_wa, cap) != cap) return;
      if(ArrayResize(g_clk_wb, cap) != cap) return;
     }
   g_clk_wa[g_clk_wn] = a;
   g_clk_wb[g_clk_wn] = b;
   g_clk_wn++;
  }

// a closure given on the New York clock
void ClkWorkPutNy(const datetime ny0, const datetime ny1) { ClkWorkPut(ClkNyToUtc(ny0), ClkNyToUtc(ny1)); }

// the built-in closures that a New York date (day number) brings
void ClkDayClosures(const int fam, const long day_no)
  {
   datetime d = (datetime)(day_no * 86400);       // 00:00 of the New York date, New York clock
   int w = ClkDowOfDay(day_no);
   if(fam == CR_FAM_XAU)
     {
      if(w >= 1 && w <= 4) ClkWorkPutNy(d + 17 * 3600, d + 18 * 3600);
      if(w == 5) ClkWorkPutNy(d + 17 * 3600, d + 2 * 86400 + 18 * 3600);
      int g = CR_CLK_G_NONE;
      if(ClkHolKind(day_no, g) != CR_NYSE_OPEN)
        {
         if(g == CR_CLK_G_LONG) ClkWorkPutNy(d - 86400 + 17 * 3600, d + 18 * 3600);
         if(g == CR_CLK_G_SHORT) ClkWorkPutNy(d + 13 * 3600, d + 18 * 3600);
         if(g == CR_CLK_G_1345) ClkWorkPutNy(d + 13 * 3600 + 45 * 60, d + 18 * 3600);
        }
     }
   else if(fam == CR_FAM_IDX)
     {
      if(w >= 1 && w <= 4) ClkWorkPutNy(d + 16 * 3600 + 15 * 60, d + 18 * 3600);
      if(w == 5) ClkWorkPutNy(d + 16 * 3600 + 15 * 60, d + 2 * 86400 + 18 * 3600);
     }
   else if(fam == CR_FAM_CRY)
     {
      if(w == 5) ClkWorkPutNy(d + 16 * 3600 + 55 * 60, d + 2 * 86400 + 17 * 3600);
     }
  }

// every closure of a family that overlaps [lo, hi), UTC, sorted by start, overlapping or touching ones merged. A
// date brings closures from 17:00 the day before to 18:00 two days after, so the dates read cover every overlap.
void ClkWorkBuild(const int fam, const datetime lo, const datetime hi)
  {
   g_clk_wn = 0;
   long d0 = ClkDayNo(ClkUtcToNy(lo)) - 3, d1 = ClkDayNo(ClkUtcToNy(hi)) + 1;
   for(long dn = d0; dn <= d1; dn++) ClkDayClosures(fam, dn);
   for(int i = 0; i < g_clk_nt; i++)
      if(g_clk_tk[i] == 2 && g_clk_tf[i] == fam && g_clk_tb[i] > lo && g_clk_ta[i] < hi) ClkWorkPut(g_clk_ta[i], g_clk_tb[i]);
   for(int i = 1; i < g_clk_wn; i++)              // insertion sort by start (the list is nearly sorted)
     {
      datetime a = g_clk_wa[i], b = g_clk_wb[i];
      int j = i - 1;
      while(j >= 0 && g_clk_wa[j] > a)
        {
         g_clk_wa[j + 1] = g_clk_wa[j];
         g_clk_wb[j + 1] = g_clk_wb[j];
         j--;
        }
      g_clk_wa[j + 1] = a;
      g_clk_wb[j + 1] = b;
     }
   int m = 0;
   for(int i = 0; i < g_clk_wn; i++)
     {
      if(m > 0 && g_clk_wa[i] <= g_clk_wb[m - 1])
        {
         if(g_clk_wb[i] > g_clk_wb[m - 1]) g_clk_wb[m - 1] = g_clk_wb[i];
         continue;
        }
      g_clk_wa[m] = g_clk_wa[i];
      g_clk_wb[m] = g_clk_wb[i];
      m++;
     }
   g_clk_wn = m;
  }

// fills slot s with the segment holding t: its closure, or the gap and the next closure. The window [t - w, t + w)
// doubles until the answer lies at least one day inside it (typed windows may chain closures), at most 256 days.
void ClkSegCompute(const int fam, const datetime t, const int s)
  {
   long w = 8;
   for(int pass = 0; pass < 6; pass++)
     {
      datetime lo = (datetime)((long)t - w * 86400), hi = (datetime)((long)t + w * 86400);
      ClkWorkBuild(fam, lo, hi);
      int j = -1;                                 // last closure starting at or before t
      for(int i = 0; i < g_clk_wn; i++)
        {
         if(g_clk_wa[i] > t) break;
         j = i;
        }
      bool final_pass = (pass == 5);
      bool inside = (j >= 0 && t < g_clk_wb[j]);
      if(inside && (final_pass || (g_clk_wa[j] > lo + 86400 && g_clk_wb[j] < hi - 86400)))
        {
         g_clk_si[s] = true;
         g_clk_sa[s] = g_clk_wa[j];
         g_clk_sb[s] = g_clk_wb[j];
         g_clk_sna[s] = g_clk_wa[j];
         g_clk_snb[s] = g_clk_wb[j];
         return;
        }
      bool has_next = (j + 1 < g_clk_wn);
      if(!inside && (final_pass || (has_next && g_clk_wb[j + 1] < hi - 86400)))
        {
         g_clk_si[s] = false;
         g_clk_sa[s] = (j >= 0) ? g_clk_wb[j] : lo;
         g_clk_sb[s] = has_next ? g_clk_wa[j + 1] : hi;
         g_clk_sna[s] = has_next ? g_clk_wa[j + 1] : (datetime)0;
         g_clk_snb[s] = has_next ? g_clk_wb[j + 1] : (datetime)0;
         return;
        }
      w *= 2;
     }
  }

// the cache slot whose segment holds t (computed when neither slot of the family does)
int ClkSeg(const int fam, const datetime t)
  {
   int s0 = 2 * fam, s1 = 2 * fam + 1;
   if(g_clk_sv[s0] && t >= g_clk_sa[s0] && t < g_clk_sb[s0])
     {
      g_clk_slast[fam] = 0;
      return s0;
     }
   if(g_clk_sv[s1] && t >= g_clk_sa[s1] && t < g_clk_sb[s1])
     {
      g_clk_slast[fam] = 1;
      return s1;
     }
   int k = 1 - g_clk_slast[fam];
   int s = 2 * fam + k;
   ClkSegCompute(fam, t, s);
   g_clk_sv[s] = true;
   g_clk_slast[fam] = k;
   return s;
  }

bool ClkInClosure(const int family, const datetime utc, datetime &c0, datetime &c1)
  {
   c0 = 0;
   c1 = 0;
   if(family < CR_FAM_XAU || family > CR_FAM_CRY) return false;
   int s = ClkSeg(family, utc);
   if(!g_clk_si[s]) return false;
   c0 = g_clk_sa[s];
   c1 = g_clk_sb[s];
   return true;
  }

bool ClkNextClosure(const int family, const datetime utc, datetime &c0, datetime &c1)
  {
   c0 = 0;
   c1 = 0;
   if(family < CR_FAM_XAU || family > CR_FAM_CRY) return false;
   int s = ClkSeg(family, utc);
   if(g_clk_snb[s] <= 0) return false;
   c0 = g_clk_sna[s];
   c1 = g_clk_snb[s];
   return true;
  }

//+------------------------------------------------------------------+
//| The follower's exit minute (SPEC 2.1, 4.5)                       |
//+------------------------------------------------------------------+
// x: the paper's scheduled time exit (UTC); gap_rule: the rule's exit uses the gap rule (gl.exit_index, 30 min);
// fri_end_utc: the broker's session end before the closure x falls in or before (SymbolInfoSessionTrade), 0 when the
// follower has none; for crypto, the broker's Friday session end of x's week. Let [c0, c1) be the known closure
// holding x, else the next one. The closure starts at e0 = fri_end_utc when that is earlier than c0 by at most 12 h
// (an earlier broker session end wins), else at c0. Then:
//   gap rule and e0 <= x < c1 - 30 min                  -> e0 - 1 min (the last minute before the closure; the lab
//                                                          exits at the last bar before it, gl.exit_index)
//   crypto with fri_end_utc > 0, result in [e0 - 1 min, c1) -> e0 - 1 min (never after the broker's Friday
//                                                          session end - 1 min)
//   else x (an exit in the last 30 min of a closure waits for the reopening, as the lab's exit does)
// For a given x and session end it never changes (the closures are fixed after ClkInit): the follower may compute it
// once per trade, and again after a HOLD moves x.
datetime ClkRealExitMinute(const datetime x, const int family, const bool gap_rule, const datetime fri_end_utc)
  {
   datetime c0 = 0, c1 = 0;
   if(!ClkNextClosure(family, x, c0, c1)) return x;
   datetime e0 = c0;
   if(fri_end_utc > 0 && fri_end_utc < c0 && (long)c0 - (long)fri_end_utc <= CR_CLK_SESS_MAX) e0 = fri_end_utc;
   datetime r = x;
   if(gap_rule && x >= e0 && x < c1 - 30 * 60) r = e0 - 60;
   if(family == CR_FAM_CRY && fri_end_utc > 0 && r >= e0 - 60 && r < c1) r = e0 - 60;
   return r;
  }

//+------------------------------------------------------------------+
//| Typed closures (InpExtraClosures)                                |
//+------------------------------------------------------------------+
// the value of n decimal digits of s at pos, -1 when one is not a digit
int ClkDigits(const string s, const int pos, const int n)
  {
   int v = 0;
   for(int i = 0; i < n; i++)
     {
      int c = (int)StringGetCharacter(s, pos + i);
      if(c < '0' || c > '9') return -1;
      v = v * 10 + (c - '0');
     }
   return v;
  }

// "yyyy.mm.dd" at pos -> day number, -1 when it is not a date of 2000-2100
long ClkParseDate(const string s, const int pos)
  {
   if(StringGetCharacter(s, pos + 4) != '.' || StringGetCharacter(s, pos + 7) != '.') return -1;
   int y = ClkDigits(s, pos, 4), m = ClkDigits(s, pos + 5, 2), d = ClkDigits(s, pos + 8, 2);
   if(y < 2000 || y > 2100 || m < 1 || m > 12 || d < 1) return -1;
   if(d > ClkMonthDays(y, m)) return -1;
   return ClkDaysFromCivil(y, m, d);
  }

// "hh:mm" at pos -> seconds after 00:00, -1 when it does not parse
int ClkParseHhmm(const string s, const int pos)
  {
   if(StringGetCharacter(s, pos + 2) != ':') return -1;
   int h = ClkDigits(s, pos, 2), m = ClkDigits(s, pos + 3, 2);
   if(h < 0 || h > 23 || m < 0 || m > 59) return -1;
   return h * 3600 + m * 60;
  }

// one space between words, none around '-', no space or tab at either end
string ClkNormalize(const string s)
  {
   string out = "";
   bool blank = false;
   int n = StringLen(s);
   for(int i = 0; i < n; i++)
     {
      ushort c = StringGetCharacter(s, i);
      if(c == ' ' || c == '\t' || c == '\r' || c == '\n')
        {
         blank = true;
         continue;
        }
      int len = StringLen(out);
      if(blank && len > 0 && c != '-' && StringGetCharacter(out, len - 1) != '-') out = out + " ";
      blank = false;
      out = out + StringSubstr(s, i, 1);
     }
   return out;
  }

void ClkTypedAdd(const int kind, const int fam, const long day_no, const datetime a, const datetime b)
  {
   g_clk_tk[g_clk_nt] = kind;
   g_clk_tf[g_clk_nt] = fam;
   g_clk_tday[g_clk_nt] = day_no;
   g_clk_ta[g_clk_nt] = a;
   g_clk_tb[g_clk_nt] = b;
   g_clk_nt++;
  }

// one entry of InpExtraClosures; false and why when it is refused (an empty entry is accepted and adds nothing)
bool ClkParseEntry(const string raw, string &why)
  {
   why = "";
   string p = ClkNormalize(raw);
   if(p == "") return true;
   if(g_clk_nt >= CR_CLK_MAXT)
     {
      why = "more than 64 entries";
      return false;
     }
   string kind = StringSubstr(p, 0, 4);
   if(kind == "NYSE" || kind == "HALF")
     {
      long dn = -1;
      if(StringLen(p) == 15 && StringGetCharacter(p, 4) == ' ') dn = ClkParseDate(p, 5);
      if(dn < 0)
        {
         why = "expected '" + kind + " yyyy.mm.dd' with a date of 2000-2100";
         return false;
        }
      int w = ClkDowOfDay(dn);
      if(w == 0 || w == 6)
        {
         why = "the date is a Saturday or a Sunday";
         return false;
        }
      ClkTypedAdd((kind == "NYSE") ? 0 : 1, -1, dn, (datetime)0, (datetime)0);
      return true;
     }
   string f3 = StringSubstr(p, 0, 3);
   int fam = -1;
   if(f3 == "XAU") fam = CR_FAM_XAU;
   if(f3 == "IDX") fam = CR_FAM_IDX;
   if(f3 == "CRY") fam = CR_FAM_CRY;
   if(fam < 0)
     {
      why = "the kind must be NYSE, HALF, XAU, IDX or CRY";
      return false;
     }
   long d0 = -1, d1 = -1;                         // "XAU yyyy.mm.dd hh:mm-yyyy.mm.dd hh:mm"
   int m0 = -1, m1 = -1;
   if(StringLen(p) == 37 && StringGetCharacter(p, 3) == ' ' && StringGetCharacter(p, 14) == ' ' && StringGetCharacter(p, 20) == '-'
      && StringGetCharacter(p, 31) == ' ')
     {
      d0 = ClkParseDate(p, 4);
      m0 = ClkParseHhmm(p, 15);
      d1 = ClkParseDate(p, 21);
      m1 = ClkParseHhmm(p, 32);
     }
   if(d0 < 0 || d1 < 0 || m0 < 0 || m1 < 0)
     {
      why = "expected '" + f3 + " yyyy.mm.dd hh:mm-yyyy.mm.dd hh:mm' (New York clock, dates of 2000-2100)";
      return false;
     }
   datetime a = (datetime)(d0 * 86400 + m0), b = (datetime)(d1 * 86400 + m1);
   if(b <= a)
     {
      why = "the window does not end after it starts";
      return false;
     }
   if((long)b - (long)a > CR_CLK_TMAXLEN)
     {
      why = "the window lasts more than 7 days";
      return false;
     }
   ClkTypedAdd(2, fam, -1, ClkNyToUtc(a), ClkNyToUtc(b));
   return true;
  }

bool ClkInit(const string extra, string &err)
  {
   err = "";
   g_clk_nt = 0;
   for(int s = 0; s < 6; s++) g_clk_sv[s] = false;
   string e = extra;
   StringTrimLeft(e);
   StringTrimRight(e);
   if(e == "") return true;
   string part[];
   int n = StringSplit(e, ';', part);
   for(int i = 0; i < n; i++)
     {
      string why = "";
      if(!ClkParseEntry(part[i], why))
        {
         err = "InpExtraClosures: entry " + IntegerToString(i + 1) + " '" + part[i] + "': " + why;
         g_clk_nt = 0;
         return false;
        }
     }
   return true;
  }

string ClkStr(const datetime t) { return TimeToString(t, TIME_DATE | TIME_MINUTES); }
#endif
