//+------------------------------------------------------------------+
//| CR_Rule_Donch.mqh - D4H donch4h_stop: 60 x 4h channel OCO with a  |
//| 2-ATR trailing stop on gold (SPEC 3). Owner: H.                   |
//|                                                                  |
//| The rule (lab/tracks/trend/strategy.py: finalist :427-429,       |
//| _donchian :235-245, _donchian_stop :257-288):                    |
//|   bars   UTC 4h bars of the kept gold M1 bars (goldlab/data.py   |
//|          bars :61-77: resample 4h, closed and labelled left).    |
//|          Bid and ask are aggregated apart (first open, max high, |
//|          min low, last close); mid h = (bh + ah) / 2, l = (bl +  |
//|          al) / 2, c = (bc + ac) / 2; t_close = the start of the  |
//|          bucket's last bar + 1 min. A bucket without a bar does  |
//|          not exist.                                              |
//|   ATR    gl.atr (data.py:88-92): TR = max(h - l, |h - pc|,       |
//|          |l - pc|), pc = the previous 4h bar's c. The first bar  |
//|          has no pc, so its TR is NaN and the Wilder mean         |
//|          (ewm alpha 1/14, adjust False: CrWilder) starts with    |
//|          the second bar's TR.                                    |
//|   levels up = the highest h, dn = the lowest l of the last 60    |
//|          4h bars, this one included (rolling(60), :261-262).     |
//|   order  after each 4h bar whose up, dn and ATR are finite: an   |
//|          OCO, buy stop at up and sell stop at dn (:279-281). It  |
//|          activates on the first kept bar at or after t_close     |
//|          (gl.entry_index, :264) and fills only on the bars of    |
//|          that bar's 4h bucket (the lab's window [i0, i1], :265). |
//|          Both levels touched in one bar: the side against the    |
//|          bar's move (_first_touch :293-318, done by CR_Paper).   |
//|          stop_dist = trail = 2 ATR (:282-283); time exit x =     |
//|          AddTradingDays(t_close, 5) - 5 min (:275) with the gap  |
//|          rule (exit_index :114-124). The paper skips the order   |
//|          whole when its trade is open, or exited, on the         |
//|          activation bar (sim.py:80).                             |
//| The order is emitted from OnBar of the first bar of the next     |
//| bucket: that bar is its activation bar, and it reaches the paper |
//| right after OnBar (SPEC 2.4). So each OCO's span ends before the |
//| next one starts.                                                 |
//| Constants (strategy.py:427-429; DEFAULTS :44-56): tf 4h, grid    |
//| utc, n 60, entry stop, stop_atr 2, trail_atr 2, max_days 5,      |
//| atr_n 14, target_r none, sides both, sess none, trend_ma 0.      |
//|                                                                  |
//| Not reproduced (SPEC 7 HOLE_RULE: the lab's test reads a future  |
//| bar): the lab keeps an order only when its exit bar comes after  |
//| its fill bar (:277, xi > hit_i). The paper exits such a trade at |
//| the first kept bar after x instead. It needs a hole of about 5   |
//| trading days in the gold data next to the fill. It never happens |
//| in sample; check/test_D4H.py counts it.                          |
//|                                                                  |
//| A rebuild starts from the load window (120 days of gold, SPEC    |
//| 2.2). The first bucket fed after Init is used only when it is    |
//| whole: its first bar starts on the 4h boundary, or the time      |
//| before that bar lies in a known gold closure. A bucket cut by    |
//| the load gives its close only (for the next bar's TR).           |
//|                                                                  |
//| LatestExit (SPEC 4.8): B = the latest 4h UTC boundary at or      |
//|   before the open time. The comment's decision is used when it   |
//|   is a whole minute at most 4 days before B (in sample at most   |
//|   70 h; the longest wait from a t_close to the next bar is       |
//|   76.5 h). Else the latest decision consistent with the open is  |
//|   taken: B, or 23:59 server on the Friday before B when B falls  |
//|   on a server weekend. AddTradingDays keeps the time of day, so a|
//|   Friday 23:59 decision exits later than a Sunday one: B alone   |
//|   would not be an upper bound there. Exit = AddTradingDays(that, |
//|   5) - 5 min.                                                    |
//+------------------------------------------------------------------+
#ifndef CR_RULE_DONCH_MQH
#define CR_RULE_DONCH_MQH
#include "CR_Types.mqh"
#include "CR_Clock.mqh"
#include "CR_Journal.mqh"
#include "CR_Math.mqh"

#define CR_D4H_TF_S 14400              // tf 4h on the UTC grid (strategy.py:427, grid utc; data.py:72 resample)
#define CR_D4H_N 60                    // channel length in 4h bars (strategy.py:427)
#define CR_D4H_ATR_N 14                // Wilder ATR length (strategy.py:428)
#define CR_D4H_STOP_ATR 2.0            // initial stop distance in ATR (strategy.py:428)
#define CR_D4H_TRAIL_ATR 2.0           // trailing distance in ATR (strategy.py:428)
#define CR_D4H_MAX_DAYS 5              // time exit: 5 New York trading days after t_close (strategy.py:428)
#define CR_D4H_BACK_S 300              // ... minus 5 minutes (strategy.py:275)
#define CR_D4H_JOIN_S 345600           // LatestExit: a comment decision at most 4 days before B

// the time exit of a decision at t_close (strategy.py:275): AddTradingDays(t_close, 5) - 5 min
datetime DonchExitTime(const datetime t_close) { return ClkAddTradingDays(t_close, CR_D4H_MAX_DAYS) - CR_D4H_BACK_S; }

// is the bucket `key` whole when t, the first bar fed since Init, opens it? Yes when t is the boundary itself, or when
// a known gold closure covers [key, t) (a session that opened inside the bucket). Else the load may have cut it.
bool DonchWhole(const datetime t, const datetime key)
  {
   if(t == key) return true;
   datetime c0 = 0, c1 = 0;
   if(!ClkInClosure(CR_FAM_XAU, key, c0, c1)) return false;
   return c1 >= t;
  }

class CRuleDonch
  {
public:
   int       sl;
   int       m_sym;                    // traded and read symbol (gold)
   int       m_id;                     // sleeve id (oid = t_close x 100 + id)
   CrAgg     m_agg;                    // the 4h bucket being filled
   CrWilder  m_atr;                    // Wilder ATR of the 4h true ranges
   CrRollMax m_up;                     // highest mid high of the last 60 4h bars
   CrRollMin m_dn;                     // lowest mid low of the last 60 4h bars
   double    m_pc;                     // mid close of the previous 4h bar
   bool      m_has_pc;                 // m_pc holds a value
   bool      m_started;                // a bar was fed since Init
   bool      m_whole;                  // the open bucket is whole (only the first one may not be)
   long      m_n4;                     // 4h bars pushed since Init

   bool Init(const int sleeve)
     {
      sl = sleeve;
      m_sym = g_sl[sl].sym;
      m_id = g_sl[sl].id;
      m_agg.Clear();
      m_atr.Init(CR_D4H_ATR_N);
      m_up.Init(CR_D4H_N);
      m_dn.Init(CR_D4H_N);
      m_pc = 0.0;
      m_has_pc = false;
      m_started = false;
      m_whole = true;
      m_n4 = 0;
      return m_sym == CR_XAU;
     }

   // the 4h bar q is complete and b, the first bar of the next bucket, is its activation bar: true range, ATR,
   // channel, then the OCO
   void Bucket(const CrAggBar &q, const bool whole, const CrBar &b, CrOut &out)
     {
      double h = (q.bh + q.ah) / 2;
      double l = (q.bl + q.al) / 2;
      double c = (q.bc + q.ac) / 2;
      if(!whole)
        {
         m_pc = c;                                           // a bucket cut by the load: its close is still right
         m_has_pc = true;
         return;
        }
      double tr = CrNaN();                                   // the first bar: pc = c.shift(1) is NaN, so is its TR
      if(m_has_pc)
        {
         tr = h - l;                                         // np.maximum(h - l, np.maximum(|h - pc|, |l - pc|))
         double a = MathAbs(h - m_pc);
         double d = MathAbs(l - m_pc);
         if(d > a) a = d;
         if(a > tr) tr = a;
        }
      double atr = m_atr.Push(tr);
      m_up.Push(h);
      m_dn.Push(l);
      m_pc = c;
      m_has_pc = true;
      m_n4++;
      double up = m_up.Value();                              // NaN until 60 bars (rolling(60), min_periods 60)
      double dn = m_dn.Value();
      if(!CrFinite(up) || !CrFinite(dn) || !CrFinite(atr)) return;   // :266
      if(!(atr > 0.0)) return;                               // a zero stop: the paper refuses it (never on real data)
      datetime tc = q.t_last + 60;
      CrOrder o;
      CrOrderClear(o);
      o.sleeve = sl;
      o.oid = CrOid(tc, m_id);
      o.side = 0;
      o.etype = CR_ET_OCO;
      o.level = up;                                          // buy stop (:281, side > 0)
      o.level2 = dn;                                         // sell stop
      o.t_from = b.t;                                        // the first kept bar at or after t_close
      o.t_to = b.t;
      o.expiry_excl = CrAggKey(b.t, CR_D4H_TF_S) + CR_D4H_TF_S;   // fills on the bars of b's bucket only
      o.stop_dist = atr * CR_D4H_STOP_ATR;
      o.trail = atr * CR_D4H_TRAIL_ATR;
      o.x_sched = DonchExitTime(tc);
      o.x_gap = true;
      o.dec = tc;
      if(!CrOutOrder(out, o)) JrnError(g_sl[sl].code, "more than CR_OUT_MAX orders at " + IntegerToString((long)tc));
     }

   void OnBar(const int sym, const CrBar &b, CrOut &out)
     {
      if(sym != m_sym) return;
      datetime key = CrAggKey(b.t, CR_D4H_TF_S);
      CrAggBar done;
      ZeroMemory(done);
      if(!m_agg.Add(b, key, done))
        {
         if(!m_started)                                      // b opened the first bucket since Init
           {
            m_started = true;
            m_whole = DonchWhole(b.t, key);
           }
         return;
        }
      bool whole = m_whole;
      m_whole = true;                                        // the bucket b opens follows a bar of this chain
      Bucket(done, whole, b, out);
     }

   void OnMinute(const datetime M, CrOut &out) {}

   datetime LatestExit(const datetime open_time, const datetime comment_dec)
     {
      datetime B = CrAggKey(open_time, CR_D4H_TF_S);
      if(comment_dec > 0 && comment_dec % 60 == 0 && comment_dec <= B && (long)(B - comment_dec) <= CR_D4H_JOIN_S)
         return DonchExitTime(comment_dec);
      datetime tc = B;
      datetime srv = ClkUtcToServer(B);
      int dow = ClkDow(srv);                                 // 0 = Sunday ... 6 = Saturday
      if(dow == 6 || dow == 0)
        {
         datetime sat = ClkDay(srv);                         // 00:00 server on the Saturday of that weekend
         if(dow == 0) sat = sat - 86400;
         tc = ClkServerToUtc(sat - 60);                      // 23:59 server on the Friday before
        }
      return DonchExitTime(tc);
     }
  };
#endif
