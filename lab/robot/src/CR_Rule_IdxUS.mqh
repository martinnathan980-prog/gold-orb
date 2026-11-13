//+------------------------------------------------------------------+
//| CR_Rule_IdxUS.mqh - US100 rules N30 (noise30) and OC4 (ocm4),     |
//| their session grid and 17:00-NY daily ATR (SPEC 3). Owner: D.     |
//|                                                                  |
//| Lab code ported (lab/r2/tracks/idx_us):                          |
//|   grid       idxus_lib.py:113-158   daily ATR  idxus_lib.py:161- |
//|   noise30    strategy.py:216-257,   198, atr_at :192-198         |
//|              297-299                ocm4       strategy.py:127-  |
//|                                                168, 303-305      |
//| Both rules read the US100 kept bars only (paper quotes; US100 has|
//| no commission, so paper = broker quotes) and use MID prices      |
//| (bid + ask) / 2. New York wall clock; times are UTC inside.      |
//|                                                                  |
//| Session grid (CrIdxGrid; each rule owns one, fed the same bars). |
//|   Rows: the New York weekday dates that have at least one kept   |
//|   bar and are not NYSE full closures (idxus_lib.py:133-142). Half|
//|   days are rows; rows before 2014 count too (rolling windows).   |
//|   Tradable row: not a half day, date from 2014-01-01             |
//|   (strategy.py:66, 114-116).                                     |
//|   t0 = 09:30 New York of the row's date.                         |
//|   P(T) = mid close of the last kept bar starting before T, NaN   |
//|     when that bar started more than 11 min before T              |
//|     (stale_min 10: age <= 11, idxus_lib.py:151).                 |
//|   O = mid open of the first kept bar at or after 09:30 if it     |
//|     starts at 09:30 or 09:31, else NaN (idxus_lib.py:155).       |
//|   The bar of a decision at T (the lab's EI) = the first kept bar |
//|     in [T, T + 5 min] (late_min 5, idxus_lib.py:154): the        |
//|     activation window of the orders and exits.                   |
//|   A row's values (P at 09:34, at the 12 checks and at 16:00, O,  |
//|   the 09:30-09:33 bar count) are sampled at their minute; the    |
//|   row enters the rolling windows when the next New York date     |
//|   starts (the lab's shift(1): a row uses the rows before it).    |
//|                                                                  |
//| Daily ATR (idxus_lib.py:161-198): trading days = server dates    |
//|   (17:00 New York roll); h = max per-bar mid high, l = min       |
//|   per-bar mid low, c = mid close of the day's last bar; days with|
//|   fewer than 600 kept bars are dropped; TR = max(h - l, |h - pc|,|
//|   |l - pc|) with pc the previous KEPT day's close (np.fmax: the  |
//|   first TR is h - l); ATR = rolling(14, 14).mean of the TRs. A   |
//|   day's ATR is known from 17:00 New York of its date: the barrier|
//|   at that minute closes the day (every bar of it has been fed).  |
//|   Half days end with the P6 mask (13:15) as in the lab frames.   |
//|                                                                  |
//| N30 {lookback 14, first_min 600, step 30, last_min 930, exit_min |
//|   955, vm 1.0} (strategy.py:297-299), code :216-257.             |
//|   At each check T = 10:00, 10:30, ..., 15:30 of a tradable row   |
//|   with O finite: p = P(T), s = mean of |P/O - 1| at that check   |
//|   over the 14 previous rows (at least 9 values,                  |
//|   max(int(0.7 x 14), 1), :222); pc = the previous row's P(16:00);|
//|   hi = fmax(O, pc), lo = fmin(O, pc) (O when pc is NaN, :224-    |
//|   226); ub = hi x (1 + vm x s), lb = lo x (1 - vm x s). Void     |
//|   unless p and s are finite (:237). State pos (-1, 0, 1, blind to|
//|   paper stop-outs, 0 at the start of each row):                  |
//|     back inside (pos > 0 and p < ub, or pos < 0 and p > lb):     |
//|       CrExit of the held order, window [T, T + 5 min]; pos 0;    |
//|     then, pos 0 and p > ub (long) or p < lb (short): a market    |
//|       order, absolute stop hi (long) / lo (short), time exit     |
//|       15:55 with the gap rule; window [T, T + 5 min], or, after  |
//|       an exit at this check (a reversal, :243 'ei += 1'),        |
//|       after_exit_of that exit: the first kept bar after the      |
//|       exit's bar, if it starts before 15:55.                     |
//|   The lab skips a check whose bar does not precede the exit bar  |
//|   (ei >= xi, :237, 244): every order carries void_le, so the     |
//|   paper drops an entry whose 15:55 exit bar does not follow its  |
//|   activation bar (SPEC 2.5), as the lab never emits it; a CrExit |
//|   on such a bar exits exactly where the lab's xi does (that bar's|
//|   open, 'time'). In sample: 6 such checks (2014-12-31,           |
//|   2015-11-02..05, 2015-12-31).                                   |
//|   State commits when the check's bar is seen (the lab's EI >= 0):|
//|   a check whose window ends without a kept bar never happened    |
//|   (its exit and order are void in the paper too); the entry of a |
//|   reversal commits at the next kept bar if it starts before      |
//|   15:55. A decision still waiting at the next check cannot occur:|
//|   P(T') finite needs a bar after the waited one.                 |
//|                                                                  |
//| OC4 {n 4, stop atr, k 0.3, exit_min 955, size_min 1.0, size_win  |
//|   20, atr_n 14, sides both} (strategy.py:303-305), code :127-168.|
//|   At 09:34 of a tradable row: O and C = P(09:34) finite, at least|
//|   3 kept bars in [09:30, 09:34) (ceil(0.6 x 4), :145), move =    |
//|   C/O - 1, side = sign(move) != 0, |move| >= size_min x the      |
//|   median of |move| over the 20 previous rows (at least 10, :142),|
//|   ATR finite: market order [09:34, 09:39], stop_dist k x ATR,    |
//|   time exit 15:55 with the gap rule, void_le (the lab's xi > EI, |
//|   :154).                                                         |
//|                                                                  |
//| LatestExit (SPEC 4.8): 15:55 New York of the New York date of the|
//| open time (gap rule: the follower's RealExitMinute).             |
//| Harness diagnostics: -DCR_IDX_TRACE adds DEC info lines (N30:    |
//| p, s then ub, lb at each evaluated check; OC4: |move|, median    |
//| then ATR, bar count at 09:34).                                   |
//+------------------------------------------------------------------+
#ifndef CR_RULE_IDXUS_MQH
#define CR_RULE_IDXUS_MQH
#include "CR_Types.mqh"
#include "CR_Clock.mqh"
#include "CR_Math.mqh"

// ---- the grid and the daily ATR (frozen: idxus_lib.py, strategy.py)
#define CR_IDX_OPEN_MIN 570            // 09:30 New York, the grid's t0 (idxus_lib.py:143)
#define CR_IDX_STALE_S 660             // P(T): last bar at most 11 min old (stale_min 10, age <= 10 + 1, idxus_lib.py:113, 151)
#define CR_IDX_LATE_S 300              // a decision's bar: the first kept bar in [T, T + 5 min] (late_min 5, idxus_lib.py:154)
#define CR_IDX_CLOSE_MIN 960           // 16:00 New York, grid column 390 (strategy.py:223)
#define CR_IDX_EXIT_MIN 955            // exit_min 955: 15:55 New York (strategy.py:298, 304)
#define CR_IDX_FIRST_DATE 1388534400   // 2014.01.01 00:00, MIN_DATE (strategy.py:66, 114-116)
#define CR_IDX_ATR_N 14                // daily ATR(14) (strategy.py:305, atr_n 14; idxus_lib.py:161)
#define CR_IDX_ATR_MINBARS 600         // trading days with fewer kept bars are dropped (idxus_lib.py:161, 181)
// ---- N30 noise30 (strategy.py:297-299)
#define CR_N30_NCHK 12                 // checks 10:00, 10:30, ..., 15:30 (strategy.py:220)
#define CR_N30_FIRST_MIN 600           // first_min 600: 10:00
#define CR_N30_STEP_MIN 30             // step 30
#define CR_N30_LOOKBACK 14             // lookback 14
#define CR_N30_MINP 9                  // max(int(0.7 x 14), 1) (strategy.py:222)
#define CR_N30_VM 1.0                  // vm 1.0
// ---- OC4 ocm4 (strategy.py:303-305)
#define CR_OC4_N 4                     // n 4: the candle [09:30, 09:34), decision at 09:34
#define CR_OC4_MIN_CNT 3               // ceil(0.6 x 4) bars in the candle (strategy.py:145)
#define CR_OC4_WIN 20                  // size_win 20
#define CR_OC4_MINP 10                 // max(20 // 2, 1) (strategy.py:142)
#define CR_OC4_K 0.3                   // stop atr, k 0.3
#define CR_OC4_SIZE_MIN 1.0            // size_min 1.0

//+------------------------------------------------------------------+
//| CrIdxGrid: the session grid and the daily ATR                    |
//+------------------------------------------------------------------+
class CrIdxGrid
  {
public:
   // ---- the New York date being built (a grid row when m_row and one of its kept bars was fed)
   datetime m_date;                    // New York date 00:00 (wall clock), 0 = none yet
   bool     m_row;                     // weekday and not an NYSE full closure (idxus_lib.py:136-141)
   bool     m_half;                    // NYSE 13:00 half day
   bool     m_trad;                    // a row that may trade: not a half day, from 2014-01-01
   bool     m_bar;                     // a kept bar of this date was fed
   datetime m_x;                       // 15:55 New York (UTC): the rules' time exit
   double   m_O;                       // mid open of the first bar at or after 09:30 if it starts before 09:32
   int      m_cnt;                     // kept bars in [09:30, 09:34)
   double   m_C;                       // P(09:34)
   double   m_p[CR_N30_NCHK];          // P at the N30 checks
   double   m_cl;                      // P(16:00)
   int      m_mod;                     // New York minute of the day of the last OnMinute barrier
   // ---- the rows before the current date
   double   m_pc;                      // the previous row's P(16:00)
   CrRollSum    m_sig[CR_N30_NCHK];    // N30: |P/O - 1| at each check, rolling(14, 9) over the rows
   CrRollMedian m_med;                 // OC4: |C/O - 1|, rolling(20, 10) median over the rows
   // ---- the last kept bar fed
   datetime m_last_t;                  // its start (0 = none)
   double   m_last_c;                  // its mid close
   // ---- the daily ATR: 17:00-NY trading days = server dates
   datetime m_dday;                    // server date of the day being summed (0 = none open)
   datetime m_dknown;                  // its end, 17:00 New York (UTC): its ATR is known from then
   int      m_dn;                      // its kept bars
   double   m_dh, m_dl, m_dc;          // max per-bar mid high, min per-bar mid low, last mid close
   double   m_dpc;                     // close of the previous kept day (NaN: none yet)
   CrRollSum m_trs;                    // rolling(14, 14) mean of the kept days' true ranges
   double   m_atr;                     // ATR of the last kept day that ended (NaN until 14 of them)

   void Init()
     {
      m_date = 0;
      m_row = false;
      m_half = false;
      m_trad = false;
      m_bar = false;
      m_x = 0;
      m_O = CrNaN();
      m_cnt = 0;
      m_C = CrNaN();
      for(int j = 0; j < CR_N30_NCHK; j++)
        {
         m_p[j] = CrNaN();
         m_sig[j].Init(CR_N30_LOOKBACK, CR_N30_MINP);
        }
      m_cl = CrNaN();
      m_mod = -1;
      m_pc = CrNaN();
      m_med.Init(CR_OC4_WIN, CR_OC4_MINP);
      m_last_t = 0;
      m_last_c = CrNaN();
      m_dday = 0;
      m_dknown = 0;
      m_dn = 0;
      m_dh = 0.0;
      m_dl = 0.0;
      m_dc = 0.0;
      m_dpc = CrNaN();
      m_trs.Init(CR_IDX_ATR_N, CR_IDX_ATR_N);
      m_atr = CrNaN();
     }

   // |x/O - 1| of the current row (strategy.py:139-141, 221), NaN when x or O is missing
   double AbsMove(const double x)
     {
      if(!CrFinite(x) || !CrFinite(m_O)) return CrNaN();
      return MathAbs(x / m_O - 1);
     }

   // P(T): the mid close of the last kept bar starting before T, NaN when it started more than 11 min before T
   double PAt(const datetime T)
     {
      if(m_last_t <= 0 || m_last_t >= T) return CrNaN();
      if((long)(T - m_last_t) > CR_IDX_STALE_S) return CrNaN();
      return m_last_c;
     }

   // the current date ends: it becomes a row of the rolling windows when it was a weekday, not a full closure, with a bar
   void DayClose()
     {
      if(m_date == 0 || !m_row || !m_bar) return;
      for(int j = 0; j < CR_N30_NCHK; j++) m_sig[j].Push(AbsMove(m_p[j]));
      m_med.Push(AbsMove(m_C));
      m_pc = m_cl;                                             // strategy.py:223-224: the previous ROW's 16:00 price
     }

   void DayOpen(const datetime ny_date)
     {
      m_date = ny_date;
      int dow = ClkDow(ny_date);
      int kind = ClkNyse(ny_date);
      m_row = (dow >= 1 && dow <= 5 && kind != CR_NYSE_FULL);
      m_half = (kind == CR_NYSE_HALF);
      m_trad = m_row && !m_half && ny_date >= (datetime)CR_IDX_FIRST_DATE;
      m_bar = false;
      m_x = ClkNyToUtc(ny_date + CR_IDX_EXIT_MIN * 60);
      m_O = CrNaN();
      m_cnt = 0;
      m_C = CrNaN();
      for(int j = 0; j < CR_N30_NCHK; j++) m_p[j] = CrNaN();
      m_cl = CrNaN();
     }

   // move forward to New York date ny_date (dates only move forward: bars and barriers come in time order)
   void ToDate(const datetime ny_date)
     {
      if(ny_date <= m_date) return;
      DayClose();
      DayOpen(ny_date);
     }

   // the trading day being summed has ended: a kept day gives a true range and the ATR known from its end
   void AtrClose()
     {
      if(m_dday == 0) return;
      if(m_dn >= CR_IDX_ATR_MINBARS)
        {
         double tr = m_dh - m_dl;                              // np.fmax(h - l, np.fmax(|h - pc|, |l - pc|)): NaN pc ignored
         if(CrFinite(m_dpc))
           {
            double a = MathAbs(m_dh - m_dpc);
            double c = MathAbs(m_dl - m_dpc);
            double m = (a >= c) ? a : c;
            if(m > tr) tr = m;
           }
         m_trs.Push(tr);
         m_atr = m_trs.Mean();
         m_dpc = m_dc;
        }
      m_dday = 0;
     }

   void AtrAdd(const CrBar &b)
     {
      datetime X = ClkServerDay(b.t);
      if(m_dday != 0 && X != m_dday) AtrClose();               // (the barrier at its end closes it first)
      double mh = (b.bh + b.ah) / 2;
      double ml = (b.bl + b.al) / 2;
      if(m_dday == 0)
        {
         m_dday = X;
         m_dknown = ClkServerToUtc(X + 86400);                 // 00:00 server of the next date = 17:00 New York of X
         m_dn = 0;
         m_dh = mh;
         m_dl = ml;
        }
      else
        {
         if(mh > m_dh) m_dh = mh;
         if(ml < m_dl) m_dl = ml;
        }
      m_dc = (b.bc + b.ac) / 2;
      m_dn++;
     }

   // one kept US100 bar, in time order
   void OnBar(const CrBar &b)
     {
      datetime ny = ClkUtcToNy(b.t);
      datetime d = ClkDay(ny);
      if(d > m_date) ToDate(d);                                // the first bar of a load comes before any barrier
      if(d == m_date)
        {
         m_bar = true;
         int mod = ClkMinOfDay(ny);
         if(mod >= CR_IDX_OPEN_MIN && mod < CR_IDX_OPEN_MIN + CR_OC4_N) m_cnt++;
         if(!CrFinite(m_O) && (mod == CR_IDX_OPEN_MIN || mod == CR_IDX_OPEN_MIN + 1)) m_O = (b.bo + b.ao) / 2;
        }
      m_last_t = b.t;
      m_last_c = (b.bc + b.ac) / 2;
      AtrAdd(b);
     }

   // barrier M (every kept bar starting before M has been fed): the date, the ATR day, the P samples of minute M
   void OnMinute(const datetime M)
     {
      datetime ny = ClkUtcToNy(M);
      ToDate(ClkDay(ny));
      if(m_dday != 0 && M >= m_dknown) AtrClose();
      m_mod = ClkMinOfDay(ny);
      if(m_mod == CR_IDX_OPEN_MIN + CR_OC4_N) m_C = PAt(M);
      int j = CheckIndex();
      if(j >= 0) m_p[j] = PAt(M);
      if(m_mod == CR_IDX_CLOSE_MIN) m_cl = PAt(M);
     }

   // the N30 check of the last barrier's minute: 0..11, -1 when it is not a check
   int CheckIndex()
     {
      int k = m_mod - CR_N30_FIRST_MIN;
      if(k < 0 || k % CR_N30_STEP_MIN != 0) return -1;
      k = k / CR_N30_STEP_MIN;
      if(k >= CR_N30_NCHK) return -1;
      return k;
     }
  };

// the latest time exit of a position opened at open_time (SPEC 4.8): 15:55 New York of its New York date, gap rule
datetime IdxLatestExit(const datetime open_time)
  {
   datetime ny = ClkUtcToNy(open_time);
   return ClkNyToUtc(ClkDay(ny) + CR_IDX_EXIT_MIN * 60);
  }

#ifdef CR_IDX_TRACE
void IdxTrace(CrOut &out, const int sl, const datetime M, const int side, const double v1, const double v2)
  {
   CrDec d;
   d.sleeve = sl;
   d.dec = M;
   d.side = side;
   d.what = CR_DEC_INFO;
   d.v1 = v1;
   d.v2 = v2;
   CrOutDec(out, d);
  }
#endif

//+------------------------------------------------------------------+
//| CRuleN30: noise30_us100                                          |
//+------------------------------------------------------------------+
class CRuleN30
  {
public:
   int       sl;
   CrIdxGrid m_g;
   datetime  m_day;                    // the grid date the state belongs to
   int       m_pos;                    // the lab's state: -1, 0, 1 (blind to paper stop-outs)
   long      m_open;                   // oid of the order the state holds (0 = none)
   // a decision waiting for its bar
   bool      m_wait;
   datetime  m_wt;                     // its check time T
   bool      m_wexit;                  // it exits the held order
   int       m_wside;                  // the side it enters (0 = none)
   long      m_woid;                   // the oid of that entry
   bool      m_wrev;                   // the entry follows the exit (after_exit_of): it commits at the next bar
   bool      m_wseen;                  // the check's bar was seen
   datetime  m_wto;                    // a reversal's entry: the last start of the bar after the exit's (15:54)

   bool Init(const int sleeve)
     {
      sl = sleeve;
      m_g.Init();
      m_day = 0;
      m_pos = 0;
      m_open = 0;
      m_wait = false;
      m_wt = 0;
      m_wexit = false;
      m_wside = 0;
      m_woid = 0;
      m_wrev = false;
      m_wseen = false;
      m_wto = 0;
      return true;
     }

   // the state is per row (strategy.py:234): a new New York date starts flat
   void DayCheck()
     {
      if(m_g.m_date == m_day) return;
      m_day = m_g.m_date;
      m_pos = 0;
      m_open = 0;
      m_wait = false;
     }

   void Commit(const int pos, const long oid)
     {
      m_pos = pos;
      m_open = oid;
     }

   void OnBar(const int sym, const CrBar &b, CrOut &out)
     {
      if(sym != CR_IDX) return;
      m_g.OnBar(b);
      DayCheck();
      if(!m_wait) return;
      if(!m_wseen)
        {
         if(b.t < m_wt || b.t > m_wt + CR_IDX_LATE_S) return;
         m_wseen = true;                                       // the check's bar (the lab's ei): its decision stands
         if(m_wexit) Commit(0, 0);
         if(m_wrev) return;                                    // the reversal's entry waits for the next bar
         if(m_wside != 0) Commit(m_wside, m_woid);
         m_wait = false;
         return;
        }
      if(b.t <= m_wto) Commit(m_wside, m_woid);               // the bar after the exit's (strategy.py:243 'ei += 1')
      m_wait = false;
     }

   void OnMinute(const datetime M, CrOut &out)
     {
      m_g.OnMinute(M);
      DayCheck();
      if(m_wait)
        {
         if(!m_wseen && M > m_wt + CR_IDX_LATE_S) m_wait = false;   // no kept bar in [T, T + 5 min]: the check never was
         else if(m_wseen && M > m_wto) m_wait = false;         // no kept bar after the exit's before 15:55: no entry
        }
      int j = m_g.CheckIndex();
      if(j < 0 || !m_g.m_trad || !CrFinite(m_g.m_O)) return;
      double p = m_g.m_p[j];
      double s = m_g.m_sig[j].Mean();
      if(!CrFinite(p) || !CrFinite(s)) return;
      if(m_wait) return;                                       // cannot occur (header); the check is skipped
      double O = m_g.m_O, pc = m_g.m_pc;
      double hi = O, lo = O;                                   // np.fmax(O, pc), np.fmin(O, pc); O when pc is NaN
      if(CrFinite(pc))
        {
         if(pc > hi) hi = pc;
         if(pc < lo) lo = pc;
        }
      double ub = hi * (1 + CR_N30_VM * s);
      double lb = lo * (1 - CR_N30_VM * s);
#ifdef CR_IDX_TRACE
      IdxTrace(out, sl, M, m_pos, p, s);
      IdxTrace(out, sl, M, m_pos, ub, lb);
#endif
      bool ex = (m_pos > 0 && p < ub) || (m_pos < 0 && p > lb);
      int side = 0;
      if(ex || m_pos == 0)
        {
         if(p > ub) side = 1;
         else if(p < lb) side = -1;
        }
      if(!ex && side == 0) return;
      if(ex)
        {
         CrExit e;
         e.sleeve = sl;
         e.oid = m_open;
         e.t_from = M;
         e.t_to = M + CR_IDX_LATE_S;
         e.dec = M;
         CrOutExit(out, e);
        }
      long oid = 0;
      if(side != 0)
        {
         CrOrder o;
         CrOrderClear(o);
         o.sleeve = sl;
         oid = CrOid(M, g_sl[sl].id);
         o.oid = oid;
         o.side = side;
         o.etype = CR_ET_MARKET;
         o.t_from = M;
         o.t_to = M + CR_IDX_LATE_S;
         if(ex)
           {
            o.after_exit_of = m_open;                          // the first kept bar after the exit's bar
            o.t_to = m_g.m_x - 60;                             // ... if it starts before 15:55 (the lab's ei + 1 < xi)
           }
         o.stop = (side > 0) ? hi : lo;                        // the centre of the noise area (strategy.py:250)
         o.x_sched = m_g.m_x;
         o.x_gap = true;                                       // gl.exit_index (strategy.py:119-121, 227)
         o.void_le = true;                                     // the lab's ei < xi (strategy.py:237, 244)
         o.dec = M;
         CrOutOrder(out, o);
        }
      m_wait = true;
      m_wt = M;
      m_wexit = ex;
      m_wside = side;
      m_woid = oid;
      m_wrev = ex && side != 0;
      m_wseen = false;
      m_wto = m_g.m_x - 60;
     }

   datetime LatestExit(const datetime open_time, const datetime comment_dec) { return IdxLatestExit(open_time); }
  };

//+------------------------------------------------------------------+
//| CRuleOC4: ocm4_us100                                             |
//+------------------------------------------------------------------+
class CRuleOC4
  {
public:
   int       sl;
   CrIdxGrid m_g;

   bool Init(const int sleeve)
     {
      sl = sleeve;
      m_g.Init();
      return true;
     }

   void OnBar(const int sym, const CrBar &b, CrOut &out)
     {
      if(sym != CR_IDX) return;
      m_g.OnBar(b);
     }

   void OnMinute(const datetime M, CrOut &out)
     {
      m_g.OnMinute(M);
      if(m_g.m_mod != CR_IDX_OPEN_MIN + CR_OC4_N || !m_g.m_trad) return;
      double O = m_g.m_O, C = m_g.m_C;
      if(!CrFinite(O) || !CrFinite(C) || m_g.m_cnt < CR_OC4_MIN_CNT) return;
      double move = C / O - 1;                                 // strategy.py:139
      int side = 0;
      if(move > 0) side = 1;
      else if(move < 0) side = -1;
      double amove = MathAbs(move);
      double med = m_g.m_med.Value();                          // the 20 previous rows (shift(1))
      double atr = m_g.m_atr;                                  // the last trading day ended by 09:34
#ifdef CR_IDX_TRACE
      IdxTrace(out, sl, M, side, amove, med);
      IdxTrace(out, sl, M, side, atr, (double)m_g.m_cnt);
#endif
      if(side == 0 || !CrFinite(atr) || !CrFinite(med)) return;
      if(!(amove >= CR_OC4_SIZE_MIN * med)) return;
      CrOrder o;
      CrOrderClear(o);
      o.sleeve = sl;
      o.oid = CrOid(M, g_sl[sl].id);
      o.side = side;
      o.etype = CR_ET_MARKET;
      o.t_from = M;
      o.t_to = M + CR_IDX_LATE_S;                              // the lab's EI[:, 4] (late_min 5)
      o.stop_dist = CR_OC4_K * atr;                            // strategy.py:162
      o.x_sched = m_g.m_x;
      o.x_gap = true;
      o.void_le = true;                                        // the lab's xi > EI (strategy.py:154)
      o.dec = M;
      CrOutOrder(out, o);
     }

   datetime LatestExit(const datetime open_time, const datetime comment_dec) { return IdxLatestExit(open_time); }
  };
#endif
