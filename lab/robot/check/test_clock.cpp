// T1 clock: src/CR_Clock.mqh (step A): hand-made cases (no argument) and the evaluator that check/test_clock.py drives
// build: entry=src/CR_Clock.mqh sanitize
//
// No argument: the cases below, written from SPEC 2.1 (summer-time instants, conversions at the switches, NYSE dates,
//   business days, server days and weeks, closures, RealExitMinute, the typed-closure parser, the closure cache),
//   printed as one JSON line; exit 0 when every case holds. check/run_tests.py runs it under the sanitizer build.
// With arguments (check/test_clock.py also builds this file against check/dbl/CR_Clock_dbl.mqh, with -DCLK_DBL):
//   hours <in> <out> [closures]   int64 UTC instants -> 16 int64 each (see Hours)
//   pairs <in> <out> [closures]   queries of 5 int64 (op, a, b, c, d) -> 3 int64 (r0, r1, r2); ops in Eval
//   grid <op> <a> <b> <t0> <t1> <step> <out> [closures]
//                                 op at t = t0, t0 + step, ... (< t1); writes (t, r0, r1, r2) only where the result
//                                 differs from the one before (time results are written relative to t)
//   parse <in> <out>              one InpExtraClosures string per line -> "1" or "0<TAB>error"
//   str <in> <out>                ClkStr of each int64, one per line
//   bench                         nanoseconds per call of the main functions
// [closures] is an InpExtraClosures string given to ClkInit first.
#include "mock_replay.h"
#include "ea.cpp"
#include <chrono>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

static std::vector<std::string> g_fail;
static int g_cases = 0;

static void Check(const char *name, bool ok)
  {
   g_cases++;
   if(!ok) g_fail.push_back(name);
  }

static void CheckEq(const char *name, long got, long want)
  {
   g_cases++;
   if(got != want)
     {
      char b[256];
      snprintf(b, sizeof b, "%s: got %ld want %ld", name, got, want);
      g_fail.push_back(b);
     }
  }

static bool Init(const char *s)
  {
   string err;
   return ClkInit(s, err);
  }

// ---- the evaluator --------------------------------------------------------------------------------------------------
// ops:  1 UtcToServer(a)  2 UtcToNy(a)  3 UtcToLdn(a)  4 ServerToUtc(a)  5 NyToUtc(a)  6 LdnToUtc(a)  7 UsDst(a)
//       8 UkDst(a)  9 ServerDay(a)  10 ServerWeek(a)  11 Day(a)  12 Dow(a)  13 MinOfDay(a)  14 Year(a)  15 RuleOffset(a)
//      16 AddTradingDays(a, n = b)  17 BusinessDays(a, n = b)  18 Nyse(a)
//      19 InClosure(family b, a) -> (in, c0, c1)   20 NextClosure(family b, a) -> (found, c0, c1) (not in the double)
//      21 RealExitMinute(x = a, family b, gap rule c != 0, fri_end d)
static void Eval(const long *q, long *r)
  {
   long op = q[0], a = q[1], b = q[2], c = q[3], d = q[4];
   datetime c0 = 0, c1 = 0;
   r[0] = r[1] = r[2] = 0;
   switch(op)
     {
      case 1: r[0] = ClkUtcToServer(a); break;
      case 2: r[0] = ClkUtcToNy(a); break;
      case 3: r[0] = ClkUtcToLdn(a); break;
      case 4: r[0] = ClkServerToUtc(a); break;
      case 5: r[0] = ClkNyToUtc(a); break;
      case 6: r[0] = ClkLdnToUtc(a); break;
      case 7: r[0] = ClkUsDst(a) ? 1 : 0; break;
      case 8: r[0] = ClkUkDst(a) ? 1 : 0; break;
      case 9: r[0] = ClkServerDay(a); break;
      case 10: r[0] = ClkServerWeek(a); break;
      case 11: r[0] = ClkDay(a); break;
      case 12: r[0] = ClkDow(a); break;
      case 13: r[0] = ClkMinOfDay(a); break;
      case 14: r[0] = ClkYear(a); break;
      case 15: r[0] = ClkRuleOffset(a); break;
      case 16: r[0] = ClkAddTradingDays(a, (int)b); break;
      case 17: r[0] = ClkBusinessDays(a, (int)b); break;
      case 18: r[0] = ClkNyse(a); break;
      case 19:
         r[0] = ClkInClosure((int)b, a, c0, c1) ? 1 : 0;
         r[1] = c0;
         r[2] = c1;
         break;
#ifndef CLK_DBL
      case 20:
         r[0] = ClkNextClosure((int)b, a, c0, c1) ? 1 : 0;
         r[1] = c0;
         r[2] = c1;
         break;
#endif
      case 21: r[0] = ClkRealExitMinute(a, (int)b, c != 0, d); break;
      default: r[0] = r[1] = r[2] = -1;
     }
  }

// one record per UTC instant u: u, server, New York, London, ServerToUtc(server), NyToUtc(New York), LdnToUtc(London),
// UsDst, UkDst, ServerDay, ServerWeek, Day, Dow, MinOfDay, Year, RuleOffset
static void Hours(long u, long *r)
  {
   r[0] = u;
   r[1] = ClkUtcToServer(u);
   r[2] = ClkUtcToNy(u);
   r[3] = ClkUtcToLdn(u);
   r[4] = ClkServerToUtc(r[1]);
   r[5] = ClkNyToUtc(r[2]);
   r[6] = ClkLdnToUtc(r[3]);
   r[7] = ClkUsDst(u) ? 1 : 0;
   r[8] = ClkUkDst(u) ? 1 : 0;
   r[9] = ClkServerDay(u);
   r[10] = ClkServerWeek(u);
   r[11] = ClkDay(u);
   r[12] = ClkDow(u);
   r[13] = ClkMinOfDay(u);
   r[14] = ClkYear(u);
   r[15] = ClkRuleOffset(u);
  }

// grid ops: atd n | bd n | inc family | nxt family | rex family gap
static bool GridEval(const char *op, long t, long a, long b, long *r)
  {
   long q[5] = {0, t, a, b, 0}, x[3] = {0, 0, 0};
   r[0] = r[1] = r[2] = 0;
   if(!strcmp(op, "atd")) { q[0] = 16; Eval(q, x); r[0] = x[0] - t; return true; }
   if(!strcmp(op, "bd")) { q[0] = 17; Eval(q, x); r[0] = x[0] - t; return true; }
   if(!strcmp(op, "inc")) { q[0] = 19; Eval(q, x); r[0] = x[0]; r[1] = x[1]; r[2] = x[2]; return true; }
   if(!strcmp(op, "nxt")) { q[0] = 20; Eval(q, x); r[0] = x[0]; r[1] = x[1]; r[2] = x[2]; return true; }
   if(!strcmp(op, "rex"))
     {
      long qq[5] = {21, t, a, b, 0};
      Eval(qq, x);
      r[0] = (x[0] != t) ? 1 : 0;
      r[1] = (x[0] != t) ? x[0] : 0;
      return true;
     }
   return false;
  }

static int Fail(const char *what)
  {
   fprintf(stderr, "test_clock: %s\n", what);
   return 2;
  }

static bool Typed(int argc, char **argv, int k)
  {
   if(argc <= k) return true;
   string err;
   if(ClkInit(argv[k], err)) return true;
   fprintf(stderr, "test_clock: ClkInit refused the closures: %s\n", err.c_str());
   return false;
  }

#ifndef CLK_DBL
// ---- hand-made cases (SPEC 2.1) -------------------------------------------------------------------------------------
static int SelfCheck()
  {
   Init("");
   // summer time: US 2021 14 Mar 07:00 - 7 Nov 06:00 UTC; UK 2021 28 Mar 01:00 - 31 Oct 01:00; US 2006 (old rule)
   // 2 Apr 07:00 - 29 Oct 06:00; 2026: US 8 Mar - 1 Nov, UK 29 Mar - 25 Oct
   const long sw[][2] = {{1615705200, 1636264800}, {1143961200, 1162101600}, {1772953200, 1793512800}};
   for(auto &p : sw)
     {
      Check("us on-1 winter", !ClkUsDst(p[0] - 1));
      Check("us on summer", ClkUsDst(p[0]));
      Check("us off-1 summer", ClkUsDst(p[1] - 1));
      Check("us off winter", !ClkUsDst(p[1]));
     }
   const long uk[][2] = {{1616893200, 1635642000}, {1774746000, 1792890000}};
   for(auto &p : uk)
     {
      Check("uk on-1 winter", !ClkUkDst(p[0] - 1));
      Check("uk on summer", ClkUkDst(p[0]));
      Check("uk off-1 summer", ClkUkDst(p[1] - 1));
      Check("uk off winter", !ClkUkDst(p[1]));
     }
   // server = New York + 7 h: Friday 2021-01-08 22:00 UTC -> Saturday 00:00 server (winter, +2 h); Friday 2021-07-09
   // 21:00 UTC -> Saturday 00:00 server (summer, +3 h)
   CheckEq("utc->srv winter", ClkUtcToServer(1610143200), 1610150400);
   CheckEq("utc->srv summer", ClkUtcToServer(1625864400), 1625875200);
   CheckEq("srv->utc winter", ClkServerToUtc(1610150400), 1610143200);
   CheckEq("srv->utc summer", ClkServerToUtc(1625875200), 1625864400);
   // spring gap: server 2021-03-14 09:30 (New York 02:30, does not exist) -> 07:30 UTC; repeated hour: server 2021-11-07
   // 08:30 (New York 01:30, twice) -> 05:30 UTC, the summer-time instant
   CheckEq("srv gap", ClkServerToUtc(1615714200), 1615707000);
   CheckEq("srv repeated", ClkServerToUtc(1636273800), 1636263000);
   CheckEq("ny gap", ClkNyToUtc(1615689000), 1615707000);
   CheckEq("ny repeated", ClkNyToUtc(1636248600), 1636263000);
   // London: 2021-03-28 01:30 (does not exist) -> 01:30 UTC (02:30 BST); 2021-10-31 01:30 (twice) -> 00:30 UTC
   CheckEq("ldn gap", ClkLdnToUtc(1616895000), 1616895000);
   CheckEq("ldn repeated", ClkLdnToUtc(1635643800), 1635640200);
   CheckEq("utc->ldn summer", ClkUtcToLdn(1625140800), 1625144400);
   // US/EU gap week: 2021-03-22 12:00 UTC: server 15:00, New York 08:00, London 12:00
   CheckEq("gap week srv", ClkUtcToServer(1616414400), 1616425200);
   CheckEq("gap week ny", ClkUtcToNy(1616414400), 1616400000);
   CheckEq("gap week ldn", ClkUtcToLdn(1616414400), 1616414400);
   CheckEq("rule offset winter", ClkRuleOffset(1610143200), 7200);
   CheckEq("rule offset summer", ClkRuleOffset(1625864400), 10800);
   // days and weeks: Friday 17:00 New York opens the Saturday server date; server Monday 2021-01-11 01:30 is in the week
   // of Monday 11 January, server Sunday 23:59 in the week of Monday 4 January
   CheckEq("server day", ClkServerDay(1610143200), 1610150400);
   CheckEq("server week monday", ClkServerWeek(1610321400), 1610323200);
   CheckEq("server week sunday", ClkServerWeek(1610315940), 1609718400);
   CheckEq("dow sunday", ClkDow(1610285879), 0);
   CheckEq("min of day", ClkMinOfDay(1610285879), 817);
   CheckEq("year end", ClkYear(1640995199), 2021);
   CheckEq("year start", ClkYear(1640995200), 2022);
   CheckEq("day", ClkDay(1610285879), 1610236800);
   // NYSE 2021: full 1 Jan, 18 Jan, 15 Feb, 2 Apr, 31 May, 5 Jul, 6 Sep, 25 Nov, 24 Dec (Christmas on a Saturday);
   // half 26 Nov; open 31 Dec (New Year 2022 on a Saturday is not observed), 2 Jul, 18 Jun (Juneteenth from 2022)
   const int f21[][2] = {{1, 1}, {1, 18}, {2, 15}, {4, 2}, {5, 31}, {7, 5}, {9, 6}, {11, 25}, {12, 24}};
   for(auto &p : f21) CheckEq("nyse 2021 full", ClkNyse((datetime)(ClkDaysFromCivil(2021, p[0], p[1]) * 86400)), CR_NYSE_FULL);
   CheckEq("nyse 2021 half", ClkNyse((datetime)(ClkDaysFromCivil(2021, 11, 26) * 86400 + 50000)), CR_NYSE_HALF);
   const int o21[][2] = {{12, 31}, {7, 2}, {6, 18}, {11, 24}, {12, 23}};
   for(auto &p : o21) CheckEq("nyse 2021 open", ClkNyse((datetime)(ClkDaysFromCivil(2021, p[0], p[1]) * 86400)), CR_NYSE_OPEN);
   // 2026: full 1 Jan, 19 Jan, 16 Feb, 3 Apr, 25 May, 19 Jun, 3 Jul (July 4 on a Saturday), 7 Sep, 26 Nov, 25 Dec;
   // half 27 Nov, 24 Dec; and 2018-12-05, 2025-01-09 (days of mourning), 2019-07-03 (half), 2022-06-20, 2023-01-02
   const int f26[][2] = {{1, 1}, {1, 19}, {2, 16}, {4, 3}, {5, 25}, {6, 19}, {7, 3}, {9, 7}, {11, 26}, {12, 25}};
   for(auto &p : f26) CheckEq("nyse 2026 full", ClkNyse((datetime)(ClkDaysFromCivil(2026, p[0], p[1]) * 86400)), CR_NYSE_FULL);
   CheckEq("nyse 2026 half nov", ClkNyse((datetime)(ClkDaysFromCivil(2026, 11, 27) * 86400)), CR_NYSE_HALF);
   CheckEq("nyse 2026 half dec", ClkNyse((datetime)(ClkDaysFromCivil(2026, 12, 24) * 86400)), CR_NYSE_HALF);
   CheckEq("nyse 2026 jul 2", ClkNyse((datetime)(ClkDaysFromCivil(2026, 7, 2) * 86400)), CR_NYSE_OPEN);
   CheckEq("nyse 2018-12-05", ClkNyse((datetime)(ClkDaysFromCivil(2018, 12, 5) * 86400)), CR_NYSE_FULL);
   CheckEq("nyse 2025-01-09", ClkNyse((datetime)(ClkDaysFromCivil(2025, 1, 9) * 86400)), CR_NYSE_FULL);
   CheckEq("nyse 2019-07-03", ClkNyse((datetime)(ClkDaysFromCivil(2019, 7, 3) * 86400)), CR_NYSE_HALF);
   CheckEq("nyse 2022-06-20", ClkNyse((datetime)(ClkDaysFromCivil(2022, 6, 20) * 86400)), CR_NYSE_FULL);
   CheckEq("nyse 2023-01-02", ClkNyse((datetime)(ClkDaysFromCivil(2023, 1, 2) * 86400)), CR_NYSE_FULL);
   CheckEq("easter 2026", ClkEaster(2026), ClkDaysFromCivil(2026, 4, 5));
   CheckEq("easter 2019", ClkEaster(2019), ClkDaysFromCivil(2019, 4, 21));
   // business days (pandas BDay): Saturday 2021-01-09 + 0 = Monday 11, + 1 = Monday 11, + 2 = Tuesday 12, - 1 = Friday 8,
   // - 5 = Monday 4; Friday 8 13:37 + 1 = Monday 11 13:37
   const long sat = 1610150400;
   CheckEq("bday sat+0", ClkBusinessDays(sat, 0), sat + 2 * 86400);
   CheckEq("bday sat+1", ClkBusinessDays(sat, 1), sat + 2 * 86400);
   CheckEq("bday sat+2", ClkBusinessDays(sat, 2), sat + 3 * 86400);
   CheckEq("bday sat-1", ClkBusinessDays(sat, -1), sat - 86400);
   CheckEq("bday sat-5", ClkBusinessDays(sat, -5), sat - 5 * 86400);
   CheckEq("bday fri+1 keeps the time", ClkBusinessDays(sat - 86400 + 49020, 1), sat + 2 * 86400 + 49020);
   // AddTradingDays: Friday 2021-01-08 17:00 NY (server Saturday 00:00) + 5 = server Friday 15 00:00 = Thursday 14
   // 22:00 UTC; Friday 2021-03-12 11:00 EST + 5 = Friday 19 11:00 EDT (15:00 UTC) across the US switch
   CheckEq("atd weekend start", ClkAddTradingDays(1610143200, 5), 1610661600);
   CheckEq("atd across the switch", ClkAddTradingDays(1615564800, 5), 1616166000);
   // closures (UTC): gold weekend Saturday 2021-01-09 12:00 -> [Friday 22:00, Sunday 23:00)
   datetime c0 = 0, c1 = 0;
   Check("xau weekend", ClkInClosure(CR_FAM_XAU, 1610193600, c0, c1) && c0 == 1610143200 && c1 == 1610319600);
   // Good Friday 2021-04-02: Thursday 17:00 NY to Sunday 18:00 NY, one closure
   Check("xau good friday", ClkInClosure(CR_FAM_XAU, 1617364800, c0, c1) && c0 == 1617310800 && c1 == 1617573600);
   // crypto: Friday 2021-01-08 16:55 NY (21:55 UTC) to Sunday 17:00 NY (22:00 UTC)
   Check("cry weekend", ClkInClosure(CR_FAM_CRY, 1610146800, c0, c1) && c0 == 1610142900 && c1 == 1610316000);
   Check("xau open monday", !ClkInClosure(CR_FAM_XAU, 1610370000, c0, c1) && c0 == 0 && c1 == 0);
   // gold daily break Tuesday 2021-01-12 17:00-18:00 NY: c0 inside, c1 outside, a second before outside
   Check("xau break", ClkInClosure(CR_FAM_XAU, 1610490600, c0, c1) && c0 == 1610488800 && c1 == 1610492400);
   Check("xau break c0", ClkInClosure(CR_FAM_XAU, 1610488800, c0, c1));
   Check("xau break c1", !ClkInClosure(CR_FAM_XAU, 1610492400, c0, c1));
   Check("xau break c0-1", !ClkInClosure(CR_FAM_XAU, 1610488799, c0, c1));
   // Thanksgiving 2021-11-25 13:00-18:00 NY (18:00-23:00 UTC)
   Check("xau thanksgiving", ClkInClosure(CR_FAM_XAU, 1637866800, c0, c1) && c0 == 1637863200 && c1 == 1637881200);
   // Christmas 2026: Thursday 24 13:45 NY (half day) + Christmas Friday [Thursday 17:00, Friday 18:00) + the weekend:
   // one closure 2026-12-24 18:45 UTC to 2026-12-27 23:00 UTC
   Check("xau christmas 2026", ClkInClosure(CR_FAM_XAU, 1798142400, c0, c1) && c0 == 1798137900 && c1 == 1798412400);
   // US100 Friday 16:15 NY to Sunday 18:00 NY; no US100 holiday closure; July 3 2019 and 2018-12-05 normal gold days
   Check("idx weekend", ClkInClosure(CR_FAM_IDX, 1610140800, c0, c1) && c0 == 1610140500 && c1 == 1610319600);
   Check("idx thanksgiving open", !ClkInClosure(CR_FAM_IDX, 1637866800, c0, c1));
   Check("xau july 3 open", !ClkInClosure(CR_FAM_XAU, 1562176800, c0, c1));
   Check("xau 2018-12-05 open", !ClkInClosure(CR_FAM_XAU, 1544032800, c0, c1));
   Check("bad family", !ClkInClosure(7, 1610193600, c0, c1));
   Check("next closure", ClkNextClosure(CR_FAM_XAU, 1610370000, c0, c1) && c0 == 1610402400 && c1 == 1610406000);
   Check("next closure inside", ClkNextClosure(CR_FAM_XAU, 1610193600, c0, c1) && c0 == 1610143200 && c1 == 1610319600);
   // RealExitMinute, gold, gap rule: Saturday -> Friday 16:59 NY; Sunday 17:29 NY (31 min before the reopening) ->
   // Friday 16:59; Sunday 17:30 and 17:40 NY (30 min or less) -> unchanged; no gap rule -> unchanged; outside -> unchanged
   CheckEq("rx weekend", ClkRealExitMinute(1610193600, CR_FAM_XAU, true, 0), 1610143140);
   CheckEq("rx 31 min before", ClkRealExitMinute(1610317740, CR_FAM_XAU, true, 0), 1610143140);
   CheckEq("rx 30 min before", ClkRealExitMinute(1610317800, CR_FAM_XAU, true, 0), 1610317800);
   CheckEq("rx 20 min before", ClkRealExitMinute(1610318400, CR_FAM_XAU, true, 0), 1610318400);
   CheckEq("rx no gap rule", ClkRealExitMinute(1610193600, CR_FAM_XAU, false, 0), 1610193600);
   CheckEq("rx outside", ClkRealExitMinute(1610370000, CR_FAM_XAU, true, 0), 1610370000);
   // Good Friday 2021-04-02 11:00 NY -> Thursday 16:59 EDT; Thanksgiving 13:30 NY -> 12:59 NY
   CheckEq("rx good friday", ClkRealExitMinute(1617375600, CR_FAM_XAU, true, 0), 1617310740);
   CheckEq("rx thanksgiving", ClkRealExitMinute(1637865000, CR_FAM_XAU, true, 0), 1637863140);
   // an earlier broker session end wins: gold ends Friday 16:55 NY (21:55 UTC): Saturday -> 16:54 NY; Friday 16:57 NY
   // (after the broker's end, before the known closure) -> 16:54 NY
   CheckEq("rx broker end", ClkRealExitMinute(1610193600, CR_FAM_XAU, true, 1610142900), 1610142840);
   CheckEq("rx broker end before c0", ClkRealExitMinute(1610143020, CR_FAM_XAU, true, 1610142900), 1610142840);
   // crypto: Saturday 00:00 UTC -> Friday 23:54 server (21:54 UTC); a broker Friday end at 23:00 server (21:00 UTC):
   // Friday 23:30 server and Saturday 01:00 UTC -> 22:59 server, Friday 22:00 server unchanged; a broker end later
   // than 23:55 server, or a stale one a week earlier, changes nothing
   CheckEq("rx cry weekend", ClkRealExitMinute(1610150400, CR_FAM_CRY, true, 0), 1610142840);
   CheckEq("rx cry early end", ClkRealExitMinute(1610141400, CR_FAM_CRY, true, 1610139600), 1610139540);
   CheckEq("rx cry early end weekend", ClkRealExitMinute(1610154000, CR_FAM_CRY, true, 1610139600), 1610139540);
   CheckEq("rx cry before the end", ClkRealExitMinute(1610136000, CR_FAM_CRY, true, 1610139600), 1610136000);
   CheckEq("rx cry late end", ClkRealExitMinute(1610150400, CR_FAM_CRY, true, 1610143080), 1610142840);
   CheckEq("rx cry stale end", ClkRealExitMinute(1610150400, CR_FAM_CRY, true, 1609534800), 1610142840);
   // the parser (SPEC 2.1 typed closures)
   const char *good[] = {"", "NYSE 2026.01.09", "HALF 2026.12.24; NYSE 2026.01.09", "XAU 2026.12.24 13:45-2026.12.26 18:00",
                         "CRY 2026.12.31 16:55-2027.01.02 17:00;IDX 2026.07.03 13:15-2026.07.05 18:00",
                         "  NYSE   2026.01.09 ;; HALF\t2026.11.27 ;", "XAU 2026.12.24 13:45 - 2026.12.26 18:00",
                         "XAU 2026.03.04 09:00-2026.03.11 09:00", "NYSE 2000.01.03", "HALF 2100.12.24"};
   const char *bad[] = {"NYSE 2026-01-09", "XAU 2026.12.24 13:45", "FOO 2026.12.24", "XAU 2026.12.26 18:00-2026.12.24 13:45",
                        "HALF 2026.02.30", "NYSE 2026.13.01", "NYSE 2026.01.10", "XAU 2026.03.04 09:00-2026.03.11 09:01",
                        "nyse 2026.01.09", "XAU 2026.12.24 24:00-2026.12.26 18:00", "XAU 2026.12.24 13:45-2026.12.24 13:45",
                        "NYSE 1999.12.31", "NYSE 2026.01.09 extra", "XAUUSD 2026.12.24 13:45-2026.12.26 18:00", "NYSE 2026.1.9",
                        "IDX 2026.07.03 13:15-2026.07.05", "XAU 2026.12.24 13:4x-2026.12.26 18:00", "NYSE 2026.01.09;FOO"};
   for(const char *s : good) Check(s, Init(s));
   for(const char *s : bad) Check(s, !Init(s));
   std::string many;
   for(int i = 0; i < 65; i++) many += "NYSE 2026.01.09;";
   Check("65 entries refused", !Init(many.c_str()));
   Check("64 entries accepted", Init(many.substr(0, 64 * 16).c_str()));
   // a refused string leaves no typed entry; typed NYSE and HALF dates win over the rules; "" clears them
   Init("NYSE 2026.01.08;FOO");
   CheckEq("refused leaves nothing", ClkNyse((datetime)(ClkDaysFromCivil(2026, 1, 8) * 86400)), CR_NYSE_OPEN);
   Check("typed init", Init("NYSE 2026.01.09;HALF 2026.12.31;HALF 2026.12.25"));
   CheckEq("typed full", ClkNyse((datetime)(ClkDaysFromCivil(2026, 1, 9) * 86400 + 3600)), CR_NYSE_FULL);
   CheckEq("typed half", ClkNyse((datetime)(ClkDaysFromCivil(2026, 12, 31) * 86400)), CR_NYSE_HALF);
   CheckEq("typed half wins", ClkNyse((datetime)(ClkDaysFromCivil(2026, 12, 25) * 86400)), CR_NYSE_HALF);
   CheckEq("typed open", ClkNyse((datetime)(ClkDaysFromCivil(2026, 1, 8) * 86400)), CR_NYSE_OPEN);
   // a typed NYSE date is not a gold closure: 2026-01-09 14:00 UTC (09:00 NY) stays open for gold
   Check("typed nyse not gold", !ClkInClosure(CR_FAM_XAU, 1767967200, c0, c1));
   Init("");
   CheckEq("cleared", ClkNyse((datetime)(ClkDaysFromCivil(2026, 1, 9) * 86400)), CR_NYSE_OPEN);
   // a typed gold window Wednesday 2021-01-13 09:00-11:00 NY: 10:00 NY -> 08:59 NY (13:59 UTC)
   Check("typed window init", Init("XAU 2021.01.13 09:00-2021.01.13 11:00"));
   Check("typed window", ClkInClosure(CR_FAM_XAU, 1610550000, c0, c1) && c0 == 1610546400 && c1 == 1610553600);
   CheckEq("rx typed window", ClkRealExitMinute(1610550000, CR_FAM_XAU, true, 0), 1610546340);
   Check("typed window not crypto", !ClkInClosure(CR_FAM_CRY, 1610550000, c0, c1));
   Init("");
   Check("typed window gone", !ClkInClosure(CR_FAM_XAU, 1610550000, c0, c1));
   // the closure cache: 10,000 pseudo-random instants of 2012-2035, asked in a scrambled order with the cache, then each
   // again on an empty cache, give the same answers
   unsigned long long seed = 12345;
   std::vector<long> tq;
   for(int i = 0; i < 10000; i++)
     {
      seed = seed * 6364136223846793005ULL + 1442695040888963407ULL;
      tq.push_back(1325376000L + (long)((seed >> 11) % (757382400ULL)));
     }
   std::vector<long> warm;
   for(long t : tq)
      for(int f = 0; f < 3; f++)
        {
         bool in = ClkInClosure(f, t, c0, c1);
         warm.push_back(in ? 1 : 0);
         warm.push_back(c0);
         warm.push_back(c1);
         bool nx = ClkNextClosure(f, t, c0, c1);
         warm.push_back(nx ? 1 : 0);
         warm.push_back(c0);
         warm.push_back(c1);
        }
   size_t k = 0;
   long cache_bad = 0;
   for(long t : tq)
      for(int f = 0; f < 3; f++)
        {
         Init("");
         bool in = ClkInClosure(f, t, c0, c1);
         cache_bad += (warm[k] != (in ? 1 : 0)) || warm[k + 1] != c0 || warm[k + 2] != c1;
         Init("");
         bool nx = ClkNextClosure(f, t, c0, c1);
         cache_bad += (warm[k + 3] != (nx ? 1 : 0)) || warm[k + 4] != c0 || warm[k + 5] != c1;
         k += 6;
        }
   CheckEq("cache = fresh", cache_bad, 0);
   printf("{\"cases\": %d, \"failed\": %zu, \"pass\": %s, \"failures\": [", g_cases, g_fail.size(), g_fail.empty() ? "true" : "false");
   for(size_t i = 0; i < g_fail.size(); i++) printf("%s\"%s\"", i ? ", " : "", g_fail[i].c_str());
   printf("]}\n");
   return g_fail.empty() ? 0 : 1;
  }

// ---- bench ------------------------------------------------------------------------------------------------------------
static double Ns(std::chrono::steady_clock::time_point a, long n)
  {
   return std::chrono::duration<double, std::nano>(std::chrono::steady_clock::now() - a).count() / (double)n;
  }

static int Bench()
  {
   Init("");
   const long t0 = 1356998400L, n = 4000000;      // 2013-01-01, minutes forward
   long acc = 0;
   datetime c0 = 0, c1 = 0;
   auto a = std::chrono::steady_clock::now();
   for(long i = 0; i < n; i++) acc += ClkServerToUtc(t0 + 60 * i);
   double s2u = Ns(a, n);
   a = std::chrono::steady_clock::now();
   for(long i = 0; i < n; i++) acc += ClkUtcToNy(t0 + 60 * i);
   double u2n = Ns(a, n);
   a = std::chrono::steady_clock::now();
   for(long i = 0; i < n; i++) acc += ClkInClosure((int)(i % 3), t0 + 60 * i, c0, c1) ? 1 : 0;
   double inc = Ns(a, n);
   a = std::chrono::steady_clock::now();
   for(long i = 0; i < n; i++) acc += ClkRealExitMinute(t0 + 60 * i, CR_FAM_XAU, true, 0);
   double rex = Ns(a, n);
   a = std::chrono::steady_clock::now();
   const long m = 400000;
   for(long i = 0; i < m; i++)                    // two far-apart instants in turn (barrier now, an exit days ahead)
     {
      acc += ClkInClosure(CR_FAM_XAU, t0 + 60 * i, c0, c1) ? 1 : 0;
      acc += ClkRealExitMinute(t0 + 60 * i + 5 * 86400 + 600, CR_FAM_XAU, true, 0);
     }
   double alt = Ns(a, 2 * m);
   a = std::chrono::steady_clock::now();
   for(long i = 0; i < m; i++) acc += ClkAddTradingDays(t0 + 14400 * i, 5);
   double atd = Ns(a, m);
   a = std::chrono::steady_clock::now();
   for(long i = 0; i < m; i++) acc += ClkNyse(t0 + 86400 * (i % 9000));
   double nyse = Ns(a, m);
   a = std::chrono::steady_clock::now();
   for(long i = 0; i < m; i++)                    // the worst case: a fresh closure computation each call
     {
      g_clk_sv[0] = false;
      g_clk_sv[1] = false;
      acc += ClkInClosure(CR_FAM_XAU, t0 + 3600 * i, c0, c1) ? 1 : 0;
     }
   double fresh = Ns(a, m);
   printf("{\"ns_server_to_utc\": %.1f, \"ns_utc_to_ny\": %.1f, \"ns_in_closure_sequential\": %.1f, \"ns_real_exit_sequential\": %.1f,"
          " \"ns_closure_alternating\": %.1f, \"ns_add_trading_days\": %.1f, \"ns_nyse\": %.1f, \"ns_closure_uncached\": %.1f, \"acc\": %ld}\n",
          s2u, u2n, inc, rex, alt, atd, nyse, fresh, acc);
   return 0;
  }
#endif

int main(int argc, char **argv)
  {
   std::string mode = (argc < 2) ? "" : argv[1];
#ifndef CLK_DBL
   if(argc < 2) return SelfCheck();
   if(mode == "bench") return Bench();
#endif
   if(mode == "hours" || mode == "pairs")
     {
      if(argc < 4) return Fail("usage: hours|pairs <in> <out> [closures]");
      if(!Typed(argc, argv, 4)) return 3;
      FILE *f = fopen(argv[2], "rb"), *g = fopen(argv[3], "wb");
      if(!f || !g) return Fail("cannot open the files");
      if(mode == "hours")
        {
         long u, r[16];
         while(fread(&u, 8, 1, f) == 1)
           {
            Hours(u, r);
            fwrite(r, 8, 16, g);
           }
        }
      else
        {
         long q[5], r[3];
         while(fread(q, 8, 5, f) == 5)
           {
            Eval(q, r);
            fwrite(r, 8, 3, g);
           }
        }
      fclose(f);
      fclose(g);
      return 0;
     }
   if(mode == "grid")
     {
      if(argc < 9) return Fail("usage: grid <op> <a> <b> <t0> <t1> <step> <out> [closures]");
      if(!Typed(argc, argv, 9)) return 3;
      long a = atol(argv[3]), b = atol(argv[4]), t0 = atol(argv[5]), t1 = atol(argv[6]), step = atol(argv[7]);
      FILE *g = fopen(argv[8], "wb");
      if(!g || step <= 0) return Fail("bad grid");
      long prev[3] = {0, 0, 0}, r[3];
      bool first = true;
      for(long t = t0; t < t1; t += step)
        {
         if(!GridEval(argv[2], t, a, b, r)) return Fail("unknown grid op");
         if(first || r[0] != prev[0] || r[1] != prev[1] || r[2] != prev[2])
           {
            long row[4] = {t, r[0], r[1], r[2]};
            fwrite(row, 8, 4, g);
            prev[0] = r[0];
            prev[1] = r[1];
            prev[2] = r[2];
            first = false;
           }
        }
      fclose(g);
      return 0;
     }
   if(mode == "parse")
     {
      if(argc < 4) return Fail("usage: parse <in> <out>");
      FILE *f = fopen(argv[2], "r"), *g = fopen(argv[3], "w");
      if(!f || !g) return Fail("cannot open the files");
      char line[8192];
      while(fgets(line, sizeof line, f))
        {
         size_t n = strlen(line);
         if(n && line[n - 1] == '\n') line[--n] = 0;
         string err;
         bool ok = ClkInit(line, err);
         fprintf(g, "%d\t%s\n", ok ? 1 : 0, err.c_str());
        }
      fclose(f);
      fclose(g);
      Init("");
      return 0;
     }
   if(mode == "str")
     {
      if(argc < 4) return Fail("usage: str <in> <out>");
      FILE *f = fopen(argv[2], "rb"), *g = fopen(argv[3], "w");
      if(!f || !g) return Fail("cannot open the files");
      long u;
      while(fread(&u, 8, 1, f) == 1) fprintf(g, "%s\n", ClkStr(u).c_str());
      fclose(f);
      fclose(g);
      return 0;
     }
   return Fail("unknown mode");
  }
