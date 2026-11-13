//+------------------------------------------------------------------+
//| CR_Rule_GoldFri.mqh - GFP GOLD_FRI_PM: Friday 13:30 NY buy limit  |
//| on gold (SPEC 3). Owner: G.                                       |
//|                                                                  |
//| The rule (lab/r2/tracks/overnight/strategy.py, make_orders       |
//| :100-211, _atr :71-97, FINALISTS :240-245):                      |
//|   params {tz NY, entry 13:30, exit 16:45, weekdays (4,), side 1, |
//|   stop_atr 3, atr_n 14, atr_tf 1h, entry_type limit, limit_min   |
//|   60, min_prev 0, skip_early_close True} (:243-244) and the      |
//|   default tol_min 5 (:102).                                      |
//|   ATR    Wilder ATR(14) of UTC hour bars of the gold kept bars   |
//|          (:71-97): h = (max bid high + max ask high) / 2, l =    |
//|          (min bid low + min ask low) / 2, c = mid close of the   |
//|          hour's last bar; TR = max(h - l, |h - pc|, |l - pc|),   |
//|          NaN for the first hour (np.maximum keeps NaN), so the   |
//|          Wilder mean (pandas ewm alpha 1/14, adjust False:       |
//|          CrWilder) is seeded with the second hour's TR; the      |
//|          first 14 hour rows are NaN (:96). An hour counts once   |
//|          its nominal end has passed (:78): the decision at 13:30 |
//|          reads the last hour that ended by 13:30 (the 12:00      |
//|          hour when it has bars, :157-158).                       |
//|   order  every Friday (New York date) at 13:30 New York, in      |
//|          OnMinute(13:30), when every bar before 13:30 has been   |
//|          fed: a buy limit at the paper bid close of the last kept|
//|          bar before 13:30 (:205), activation window [13:30,      |
//|          13:35] (the first kept bar within tol_min 5, :60-68),   |
//|          fills on bars starting before 14:30 (limit_min 60,      |
//|          :206-207), stop_dist 3 x ATR (:198), time exit at the   |
//|          first kept bar at or after 16:45 New York with no gap   |
//|          rule (:133, 152).                                       |
//|   skips  (SPEC 3, R8) instead of the lab's after-the-fact test   |
//|          (:129-137: no quote within 10 min of 16:45), which reads|
//|          a future bar: a NYSE full holiday or half day           |
//|          (ClkNyse: us_holidays plus the typed NYSE and HALF      |
//|          entries), a known XAU closure that starts before 16:55  |
//|          (the closure holding 13:30, or the next one: ClkNext-   |
//|          Closure), or a broker Friday session that does not hold |
//|          13:30 or ends before 16:55 (SymbolInfoSessionTrade; no  |
//|          information = no skip). In 2013-2021 this skips the     |
//|          same 26 Fridays as the lab: Good Friday, July 4,        |
//|          Christmas and New Year (no gold bar at 13:30) and the   |
//|          Friday after Thanksgiving (last bar 13:42-14:05). The   |
//|          lab also skips Fridays whose data has a hole at 16:45   |
//|          (2013-05-31 in sample, data to 16:39): the robot cannot |
//|          see a future hole, so these "GFP hole days" are listed  |
//|          by check/test_GFP.py, never silent (SPEC 7).            |
//|          Each skipped Friday writes a DEC info line: side 0,     |
//|          v1 = the reason code below, v2 = its detail.            |
//|                                                                  |
//| LatestExit (SPEC 4.8): 16:45 New York on the New York date of the|
//|   open time (the order lives 13:30-14:30 and the real fill is a  |
//|   bar later, so the date is always the decision's). The comment's|
//|   decision, when it is a Friday 13:30 New York at most 66 min    |
//|   before the open, gives the same date: it is only a cross-check.|
//+------------------------------------------------------------------+
#ifndef CR_RULE_GOLDFRI_MQH
#define CR_RULE_GOLDFRI_MQH
#include "CR_Types.mqh"
#include "CR_Clock.mqh"
#include "CR_Journal.mqh"
#include "CR_Math.mqh"

#define CR_GFP_DOW 5                   // weekdays (4,): pandas Friday = ClkDow 5 (strategy.py:243)
#define CR_GFP_ENTRY_MIN 810           // entry 13:30 New York (:243)
#define CR_GFP_EXIT_MIN 1005           // exit 16:45 New York (:243)
#define CR_GFP_OPEN_MIN 1015           // 16:55: a quote within 10 min of 16:45 (skip_early_close, :136)
#define CR_GFP_TOL_S 300               // tol_min 5: the first kept bar starting in [13:30, 13:35] (:65, :102)
#define CR_GFP_LIMIT_S 3600            // limit_min 60: fills on bars starting before 14:30 (:206)
#define CR_GFP_STOP_ATR 3.0            // stop_atr 3 (:243)
#define CR_GFP_ATR_N 14                // atr_n 14 (:243): Wilder 1/14 (:95), rows 0-13 NaN (:96)
#define CR_GFP_HOUR_S 3600             // atr_tf 1h: UTC hours (:76-78)
#define CR_GFP_JOIN_S 3960             // LatestExit: a real open at most 66 min after 13:30 (60 min of limit, a bar, 5 min)
// ---- reasons of a skipped Friday (DEC info v1)
#define CR_GFP_SKIP_FULL 1             // NYSE full holiday (v2 0)
#define CR_GFP_SKIP_HALF 2             // NYSE half day (v2 0)
#define CR_GFP_SKIP_CLOSURE 3          // a known XAU closure starts before 16:55 (v2 = its start, UTC)
#define CR_GFP_SKIP_SESSION 4          // the broker session does not hold 13:30 or ends before 16:55 (v2 = its end, server s of day; -1 none)
#define CR_GFP_SKIP_ATR 5              // ATR not finite or not > 0 (v2 = hour rows so far)
#define CR_GFP_SKIP_NOBAR 6            // no kept bar before 13:30 yet (v2 0)

// a broker trade session [from, to) of a day (SymbolInfoSessionTrade: seconds from 00:00, the date ignored; an end at
// or before the start, 00:00 included, runs to the end of the day): does it hold the server time of day a? end_s = its
// end in seconds of the day (86400 = midnight)
bool GfpSessionHoldsAt(const long from_s, const long to_s, const long a, long &end_s)
  {
   long f = from_s % 86400;
   long t = to_s % 86400;
   if(f < 0) f += 86400;
   if(t < 0) t += 86400;
   if(t <= f) t = 86400;
   end_s = t;
   return f <= a && a < t;
  }

// SPEC 3 GFP: the broker's Friday trade sessions of sym against 13:30 (t0) and 16:55 (t1) New York, UTC. Returns true
// (skip) when the broker lists sessions and none holds 13:30 and runs to 16:55 or later; end_s = the latest end of a
// session holding 13:30 (server seconds of the day), -1 when none holds it. No session listed: false (no
// information, no skip; the harness broker lists none).
bool GfpSessionShort(const string sym, const datetime t0, const datetime t1, long &end_s)
  {
   end_s = -1;
   long a = (long)ClkUtcToServer(t0) % 86400;
   long b = (long)ClkUtcToServer(t1) % 86400;
   if(b <= a) b = 86400;
   int n = 0;
   for(int k = 0; k < 32; k++)
     {
      datetime from = 0, to = 0;
      if(!SymbolInfoSessionTrade(sym, FRIDAY, (uint)k, from, to)) break;
      n++;
      long e = 0;
      if(!GfpSessionHoldsAt((long)from, (long)to, a, e)) continue;
      if(e > end_s) end_s = e;
      if(e >= b) return false;
     }
   return n > 0;
  }

// the time exit of a decision on New York date ny_day (00:00, New York clock): 16:45 New York, UTC
datetime GfpExitTime(const datetime ny_day) { return ClkNyToUtc(ny_day + CR_GFP_EXIT_MIN * 60); }

// the calendar part of the decision at t0 (13:30 New York of a Friday, UTC): 0 = trade, else CR_GFP_SKIP_* and v2
int GfpCalendarSkip(const datetime t0, const string sym, double &v2)
  {
   v2 = 0.0;
   datetime day = ClkDay(ClkUtcToNy(t0));
   int k = ClkNyse(day);
   if(k == CR_NYSE_FULL) return CR_GFP_SKIP_FULL;
   if(k == CR_NYSE_HALF) return CR_GFP_SKIP_HALF;
   datetime t1 = ClkNyToUtc(day + CR_GFP_OPEN_MIN * 60);
   datetime c0 = 0, c1 = 0;
   if(ClkNextClosure(CR_FAM_XAU, t0, c0, c1) && c0 < t1)
     {
      v2 = (double)c0;
      return CR_GFP_SKIP_CLOSURE;
     }
   long end_s = -1;
   if(GfpSessionShort(sym, t0, t1, end_s))
     {
      v2 = (double)end_s;
      return CR_GFP_SKIP_SESSION;
     }
   return 0;
  }

// is M (UTC) 13:30 New York on a Friday?
bool GfpIsDecision(const datetime M)
  {
   datetime ny = ClkUtcToNy(M);
   return ClkDow(ny) == CR_GFP_DOW && ClkMinOfDay(ny) == CR_GFP_ENTRY_MIN && (long)ny % 60 == 0;
  }

class CRuleGfp
  {
public:
   int       sl;
   int       m_sym;                    // gold
   int       m_id;                     // sleeve id (oid = decision x 100 + id)
   CrAgg     m_agg;                    // the UTC hour being filled
   CrWilder  m_atr;                    // Wilder ATR(14) of the hour bars
   long      m_nh;                     // hour rows pushed (the lab's row number + 1)
   double    m_pc;                     // close of the previous hour row
   bool      m_bar;                    // a kept bar was seen
   double    m_bc;                     // paper bid close of the last kept bar

   bool Init(const int sleeve)
     {
      sl = sleeve;
      m_sym = g_sl[sl].sym;
      m_id = g_sl[sl].id;
      m_agg.Clear();
      m_atr.Init(CR_GFP_ATR_N);
      m_nh = 0;
      m_pc = 0.0;
      m_bar = false;
      m_bc = 0.0;
      return m_sym == CR_XAU;                                 // a gold rule: its calendar is the XAU one
     }

   // an hour row is complete: its true range enters the Wilder mean (_atr :89-95)
   void HourDone(const CrAggBar &hb)
     {
      double h = (hb.bh + hb.ah) / 2;
      double l = (hb.bl + hb.al) / 2;
      double c = (hb.bc + hb.ac) / 2;
      double tr = CrNaN();                                    // the first row: pc is NaN, np.maximum keeps it
      if(m_nh > 0)
        {
         double a = MathAbs(h - m_pc);
         double b = MathAbs(l - m_pc);
         double m = (a >= b) ? a : b;
         tr = h - l;
         if(m > tr) tr = m;
        }
      m_atr.Push(tr);
      m_pc = c;
      m_nh++;
     }

   // the ATR the lab reads at a decision: NaN during the warm-up (rows 0-13)
   double AtrNow()
     {
      if(m_nh <= CR_GFP_ATR_N) return CrNaN();
      return m_atr.Value();
     }

   void SkipLine(const datetime M, const int code, const double v2, CrOut &out)
     {
      CrDec d;
      ZeroMemory(d);
      d.sleeve = sl;
      d.dec = M;
      d.side = 0;
      d.what = CR_DEC_INFO;
      d.v1 = (double)code;
      d.v2 = v2;
      if(!CrOutDec(out, d)) JrnError(g_sl[sl].code, "more than CR_OUT_MAX decisions at " + IntegerToString((long)M));
     }

   void DecideAt(const datetime M, CrOut &out)
     {
      double v2 = 0.0;
      int code = GfpCalendarSkip(M, g_sym[m_sym].name, v2);
      double atr = AtrNow();
      if(code == 0 && !m_bar) code = CR_GFP_SKIP_NOBAR;
      if(code == 0 && !(CrFinite(atr) && atr > 0.0))
        {
         code = CR_GFP_SKIP_ATR;
         v2 = (double)m_nh;
        }
      if(code != 0)
        {
         SkipLine(M, code, v2, out);
         return;
        }
      CrOrder o;
      CrOrderClear(o);
      o.sleeve = sl;
      o.oid = CrOid(M, m_id);
      o.side = 1;
      o.etype = CR_ET_LIMIT;
      o.level = m_bc;
      o.t_from = M;
      o.t_to = M + CR_GFP_TOL_S;
      o.expiry_excl = M + CR_GFP_LIMIT_S;
      o.stop_dist = CR_GFP_STOP_ATR * atr;
      o.x_sched = GfpExitTime(ClkDay(ClkUtcToNy(M)));
      o.x_gap = false;
      o.dec = M;
      if(!CrOutOrder(out, o)) JrnError(g_sl[sl].code, "more than CR_OUT_MAX orders at " + IntegerToString((long)M));
     }

   void OnBar(const int sym, const CrBar &b, CrOut &out)
     {
      if(sym != m_sym) return;
      CrAggBar done;
      ZeroMemory(done);
      // a bar of a new hour while the old one is open: under the minute contract OnMinute has closed it already
      if(m_agg.Add(b, CrAggKey(b.t, CR_GFP_HOUR_S), done)) HourDone(done);
      m_bc = b.bc;
      m_bar = true;
     }

   void OnMinute(const datetime M, CrOut &out)
     {
      CrAggBar cur;
      ZeroMemory(cur);
      if(m_agg.Peek(cur) && cur.key + CR_GFP_HOUR_S <= M)   // every bar of that hour has been fed
        {
         m_agg.Take(cur);
         HourDone(cur);
        }
      if(GfpIsDecision(M)) DecideAt(M, out);
     }

   datetime LatestExit(const datetime open_time, const datetime comment_dec)
     {
      datetime day = ClkDay(ClkUtcToNy(open_time));
      if(comment_dec > 0 && comment_dec <= open_time && (long)(open_time - comment_dec) <= CR_GFP_JOIN_S && GfpIsDecision(comment_dec))
         day = ClkDay(ClkUtcToNy(comment_dec));
      return GfpExitTime(day);
     }
  };
#endif
