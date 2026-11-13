//+------------------------------------------------------------------+
//| CR_Rule_Orb.mqh - ORX orb_asia_2d_buf10: London 00:00-07:00 range |
//| breakout on gold (SPEC 3). Owner: G.                              |
//|                                                                  |
//| The rule (lab/tracks/orb/strategy.py: sessions :139-181,         |
//| make_orders :184-271, _range_stats :72-92, _first_touch :95-119, |
//| FINALISTS :276-287):                                             |
//|   params {tz LDN, range 00:00-07:00, entry_end 12:00, entry stop,|
//|   buf_frac 0.1, buf_abs 0, stop_mode opp, exit_time 16:00 NY,    |
//|   hold_days 2, min_bars_frac 0.5, sides both, no target, no      |
//|   break-even, no trail, no width or cost filter} (:276-287).     |
//|   days   London weekday dates (:144-145).                        |
//|   range  the kept bars starting in [00:00, 07:00) London of the  |
//|          date: H = max ask high, L = min bid low, n bars         |
//|          (:156-164). Valid when n >= 210 (0.5 x 420 minutes,     |
//|          :167-169) and W = H - L > 0 (:200). Levels H + 0.1 W    |
//|          and L - 0.1 W (:202-204).                               |
//|   touch  the first kept bar starting in [07:00, 12:00) London    |
//|          whose ask high reaches the upper level (long) or whose  |
//|          bid low reaches the lower one (short); both in one bar: |
//|          the level nearer the bar's mid open, a tie long         |
//|          (_first_touch :104-118). It uses the day up, whatever   |
//|          the paper's state (the lab finds it on the bars alone). |
//|   order  from OnBar of that bar, before the paper sees it: a stop|
//|          order at the touched level, window = that bar (t_from = |
//|          t_to = its start) and filling only on it (expiry_excl = |
//|          start + 60 s; the lab's expiry_i = entry_i, :265),      |
//|          absolute stop = the other level (:246-247), time exit at|
//|          the first kept bar at or after 16:00 New York on        |
//|          BusinessDays(London date, 2), no gap rule (:149-152,    |
//|          159). The paper skips it when the sleeve is busy        |
//|          (sim.py:80), as the lab does.                           |
//|   Bit for bit: H, L and n come from the same bars; W, the buffer,|
//|   the levels and the tie test use the lab's own expressions in   |
//|   its order (0.1 x W + 0.0, H + buf, L - buf, 0.5 x (ao + bo)).  |
//|   A weekday whose range is not valid writes one DEC info line at |
//|   its first bar in [07:00, 12:00): side 0, v1 = 1 (fewer than    |
//|   210 bars; v2 = n) or 2 (W not > 0; v2 = W).                    |
//|                                                                  |
//| Retired ids: SPEC 2.3. Ids 11 and 12 were this rule on BTC and   |
//|   ETH (K2, K3); they failed the 2022-2025 look and are dropped   |
//|   for good, like every id 11-19. Init refuses a retired id and a |
//|   symbol other than gold, so a registry row for them cannot run. |
//|                                                                  |
//| LatestExit (SPEC 4.8): 16:00 New York on BusinessDays(London date|
//|   of the open time, 2). The order fills in [07:00, 12:00) London |
//|   and the real fill comes one bar later, so the London date of   |
//|   the open is the decision's; a comment decision in that window  |
//|   of the same date, before the open, gives the same exit.        |
//+------------------------------------------------------------------+
#ifndef CR_RULE_ORB_MQH
#define CR_RULE_ORB_MQH
#include "CR_Types.mqh"
#include "CR_Clock.mqh"
#include "CR_Journal.mqh"
#include "CR_Math.mqh"

#define CR_ORX_RANGE_END_MIN 420       // range 00:00-07:00 London (strategy.py:278)
#define CR_ORX_ENTRY_END_MIN 720       // entry_end 12:00 London (:279)
#define CR_ORX_MIN_BARS 210            // min_bars_frac 0.5 x 420 expected minutes (:285, :167-169)
#define CR_ORX_BUF_FRAC 0.1            // buf_frac 0.1 (:280)
#define CR_ORX_BUF_ABS 0.0             // buf_abs 0.0 (:280)
#define CR_ORX_EXIT_MIN 960            // exit_time 16:00, exit_tz NY (:283)
#define CR_ORX_HOLD_DAYS 2             // hold_days 2 business days (:283, :149)
#define CR_ORX_RETIRED_LO 11           // SPEC 2.3: ids 11-19 retired (11, 12 = this rule on BTC, ETH)
#define CR_ORX_RETIRED_HI 19
// ---- an invalid range (DEC info v1)
#define CR_ORX_SKIP_BARS 1             // fewer than 210 range bars (v2 = n)
#define CR_ORX_SKIP_WIDTH 2            // W = H - L not > 0 (v2 = W)

// the time exit of a London date (00:00, London clock): 16:00 New York on BusinessDays(date, 2) (:149-152), UTC
datetime OrxExitTime(const datetime ldn_day)
  {
   return ClkNyToUtc(ClkBusinessDays(ldn_day, CR_ORX_HOLD_DAYS) + CR_ORX_EXIT_MIN * 60);
  }

// is t (UTC) inside the entry window [07:00, 12:00) of a London weekday?
bool OrxInWindow(const datetime t)
  {
   datetime ldn = ClkUtcToLdn(t);
   int dow = ClkDow(ldn);
   int mod = ClkMinOfDay(ldn);
   return dow >= 1 && dow <= 5 && mod >= CR_ORX_RANGE_END_MIN && mod < CR_ORX_ENTRY_END_MIN;
  }

class CRuleOrx
  {
public:
   int       sl;
   int       m_sym;                    // gold
   int       m_id;                     // sleeve id (oid = decision x 100 + id)
   datetime  m_day;                    // London date (00:00, London clock) of the range below, 0 = none
   int       m_n;                      // range bars
   double    m_hi;                     // max ask high of the range bars
   double    m_lo;                     // min bid low of the range bars
   bool      m_used;                   // m_day's entry window is used up (a touch, or an invalid range)

   bool Init(const int sleeve)
     {
      sl = sleeve;
      m_sym = g_sl[sl].sym;
      m_id = g_sl[sl].id;
      m_day = 0;
      m_n = 0;
      m_hi = 0.0;
      m_lo = 0.0;
      m_used = false;
      if(m_id >= CR_ORX_RETIRED_LO && m_id <= CR_ORX_RETIRED_HI) return false;
      return m_sym == CR_XAU;
     }

   void SkipLine(const datetime t, const int code, const double v2, CrOut &out)
     {
      CrDec d;
      ZeroMemory(d);
      d.sleeve = sl;
      d.dec = t;
      d.side = 0;
      d.what = CR_DEC_INFO;
      d.v1 = (double)code;
      d.v2 = v2;
      if(!CrOutDec(out, d)) JrnError(g_sl[sl].code, "more than CR_OUT_MAX decisions at " + IntegerToString((long)t));
     }

   // bar b of the entry window of m_day, the day not used up yet
   void WindowBar(const CrBar &b, CrOut &out)
     {
      if(m_n < CR_ORX_MIN_BARS)
        {
         SkipLine(b.t, CR_ORX_SKIP_BARS, (double)m_n, out);
         m_used = true;
         return;
        }
      double w = m_hi - m_lo;
      if(!(w > 0.0))
        {
         SkipLine(b.t, CR_ORX_SKIP_WIDTH, w, out);
         m_used = true;
         return;
        }
      double buf = CR_ORX_BUF_FRAC * w + CR_ORX_BUF_ABS;
      double buy = m_hi + buf;
      double sell = m_lo - buf;
      bool up = (b.ah >= buy);
      bool dn = (b.bl <= sell);
      if(!up && !dn) return;
      int side = up ? 1 : -1;
      if(up && dn)
        {
         double mo = 0.5 * (b.ao + b.bo);
         side = (MathAbs(buy - mo) <= MathAbs(mo - sell)) ? 1 : -1;
        }
      m_used = true;
      CrOrder o;
      CrOrderClear(o);
      o.sleeve = sl;
      o.oid = CrOid(b.t, m_id);
      o.side = side;
      o.etype = CR_ET_STOP;
      o.level = (side > 0) ? buy : sell;
      o.t_from = b.t;
      o.t_to = b.t;
      o.expiry_excl = b.t + 60;
      o.stop = (side > 0) ? sell : buy;
      o.x_sched = OrxExitTime(m_day);
      o.x_gap = false;
      o.dec = b.t;
      if(!CrOutOrder(out, o)) JrnError(g_sl[sl].code, "more than CR_OUT_MAX orders at " + IntegerToString((long)b.t));
     }

   void OnBar(const int sym, const CrBar &b, CrOut &out)
     {
      if(sym != m_sym) return;
      datetime ldn = ClkUtcToLdn(b.t);
      int dow = ClkDow(ldn);
      if(dow < 1 || dow > 5) return;                           // London weekdays only (:145)
      datetime day = ClkDay(ldn);
      if(day != m_day)
        {
         m_day = day;
         m_n = 0;
         m_hi = 0.0;
         m_lo = 0.0;
         m_used = false;
        }
      int mod = ClkMinOfDay(ldn);
      if(mod < CR_ORX_RANGE_END_MIN)                             // the range [00:00, 07:00) (_range_stats :79-91)
        {
         if(m_n == 0 || b.ah > m_hi) m_hi = b.ah;
         if(m_n == 0 || b.bl < m_lo) m_lo = b.bl;
         m_n++;
         return;
        }
      if(mod >= CR_ORX_ENTRY_END_MIN || m_used) return;
      WindowBar(b, out);
     }

   void OnMinute(const datetime M, CrOut &out) {}

   datetime LatestExit(const datetime open_time, const datetime comment_dec)
     {
      datetime day = ClkDay(ClkUtcToLdn(open_time));
      if(comment_dec > 0 && comment_dec <= open_time && OrxInWindow(comment_dec) && ClkDay(ClkUtcToLdn(comment_dec)) == day)
         day = ClkDay(ClkUtcToLdn(comment_dec));
      return OrxExitTime(day);
     }
  };
#endif
