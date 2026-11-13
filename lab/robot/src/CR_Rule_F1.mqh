//+------------------------------------------------------------------+
//| CR_Rule_F1.mqh - F1B / F1E F1_brk_ridge_filter on BTC and ETH,    |
//| with H2 (F1E) behind its switch (SPEC 3). Owner: E.               |
//| The frozen scorecard comes from the generated CR_F1Model.mqh.    |
//|                                                                  |
//| The rule (lab/r2/tracks/ml/strategy.py):                         |
//|   session bars  UTC hour bars of the BID M1 bars (_h1_bid :82-96:|
//|          o first bo, h max bh, l min bl, c last bc) whose start  |
//|          is 02:00-15:00 New York on a New York weekday           |
//|          (session_bars :99-113). Every look-back counts session  |
//|          bars only. A bar is complete at the barrier of its end. |
//|   at t_dec = the end of a session bar that starts at 02:00-14:00 |
//|          New York (candidates :116-189):                         |
//|          hh, ll = highest high, lowest low of the 14 previous    |
//|          session bars; c > hh -> long, c < ll -> short;          |
//|          A = mean of h - l over the last 70 (this one included), |
//|          A_long over 280 (pandas rolling mean: CrRollSum);       |
//|          the 15 features of FEATURES (:72-73, formulas :136-162):|
//|            brk  (c - hh) / A long, (ll - c) / A short            |
//|            bar  (h - l) / A          body  s (c - o) / A         |
//|            ret4, ret14, ret70  s (c - c[k bars ago]) / A         |
//|            chan (hh - ll) / A        vol   A / A_long            |
//|            pos  (c - L280) / (H280 - L280) long, (H280 - c) /    |
//|                 (H280 - L280) short (280 bars, this one in)      |
//|            seq, opp  breakouts of the 14 previous session bars   |
//|                 on the same / the other side                     |
//|            pdd  (c - pdh) / A long, (pdl - c) / A short          |
//|            dret s (c - pdc) / A   (pd* = the previous New York   |
//|                 date that has session bars: max h, min l, last c)|
//|            hour = New York hour of t_dec, dow = weekday (0 Mon)  |
//|          a candidate needs every feature finite and A > 0; the   |
//|          score (CR_F1Model.mqh) is journaled (DEC info: v1 score,|
//|          v2 A); it is taken when score >= CR_F1_THR.             |
//|   order  market, window [t_dec, t_dec + 5 min] (:171-178),       |
//|          stop_dist 2 A (make_orders :286), exit x = min(t_dec +  |
//|          13 h, 15:55 New York of t_dec's date) (:179-185) with   |
//|          the gap rule, void_le (the lab keeps an order only when |
//|          its exit bar follows its entry bar, :186).              |
//| Constants: stop_k 2.0, hold_h 13, model B1_ridge_full.json, q 0.5|
//| (strategy.py:295-297); n 14, h0 2, h1 16, last_dec_h 15, vol_n   |
//| 70, exit_hm 1555, max_wait_min 5 (:55-69); seq and opp windows 14|
//| (:147-148); A_long and the 280-bar extremes 4 x vol_n (:125,     |
//| 144-145).                                                        |
//|                                                                  |
//| H2 (F1E, while its switch is on; payoff variants.py:206-233,     |
//| :118-126; common.py:249-262): xh = min(15:55 New York on (t_dec's|
//| New York date + 2 business days), Friday 23:54 server of the     |
//| entry's server week), both with the gap rule; xh_r = 1.0; the    |
//| paper holds a trade still open at x that is ahead by 1 R at the  |
//| close of the bar before its exit bar (SPEC 2.5); stop unchanged; |
//| refusal 1 (payoff) in the paper; stake factor in CR_Sizing.      |
//|                                                                  |
//| LatestExit (SPEC 4.8): t_dec = the decision of the comment when  |
//| it lies on an hour at most 10 min before open_time, else         |
//| open_time floored to the UTC hour; exit 15:55 New York on t_dec's|
//| date (the H2 hold needs the paper: not applied).                 |
//+------------------------------------------------------------------+
#ifndef CR_RULE_F1_MQH
#define CR_RULE_F1_MQH
#include "CR_Types.mqh"
#include "CR_Clock.mqh"
#include "CR_Journal.mqh"
#include "CR_Math.mqh"
#include "CR_F1Model.mqh"

#define CR_F1_CHAN 14                  // n: channel of the previous session bars (strategy.py:56)
#define CR_F1_H0 2                     // session bars start at New York hours h0 .. h1 - 1 (:57)
#define CR_F1_H1 16
#define CR_F1_LAST_DEC_H 15            // last decision hour, New York (:58)
#define CR_F1_VOL_N 70                 // A (:59, 124)
#define CR_F1_VOL_LONG 280             // A_long, H280, L280: 4 x vol_n (:125, 144-145)
#define CR_F1_SEQ_N 14                 // seq / opp windows (:147-148)
#define CR_F1_RET_MAX 70               // the longest close look-back (ret70, :141)
#define CR_F1_STOP_K 2.0               // stop_k (:297)
#define CR_F1_HOLD_S 46800             // hold_h 13: x = t_dec + int(round(13 x 60)) minutes (:183, 297)
#define CR_F1_EXIT_MIN 955             // exit_hm 1555: 15:55 New York, minutes of the day (:62, 181-182)
#define CR_F1_WAIT_S 300               // max_wait_min 5 (:63, 177-178)
#define CR_F1_H2_BDAYS 2               // H2: hold to 15:55 New York two business days later (look_spec j 2)
#define CR_F1_H2_R 1.0                 // H2: ahead by at least 1 R (variants.py:221)
#define CR_F1_JOIN_S 600               // LatestExit: an open time at most 10 min after its decision

// 15:55 New York on the New York date of t (UTC)
datetime F1ExitClock(const datetime t)
  {
   datetime ny = ClkUtcToNy(t);
   return ClkNyToUtc((datetime)((long)ClkDay(ny) + CR_F1_EXIT_MIN * 60));
  }

// Friday 23:54 server of the server week of t, as UTC (payoff common.py:255-259)
datetime F1FridayEnd(const datetime t)
  {
   datetime srv = ClkUtcToServer(t);
   long day = (long)ClkDay(srv);
   int mon0 = (ClkDow(srv) + 6) % 7;                         // 0 = Monday ... 6 = Sunday
   long fri = day + (long)(4 - mon0) * 86400 + 23 * 3600 + 54 * 60;
   return ClkServerToUtc((datetime)fri);
  }

class CRuleF1
  {
public:
   int       sl;
   int       m_sym;                    // traded and read symbol
   int       m_id;                     // sleeve id (oid = decision x 100 + id)
   bool      m_h2;                     // H2 in force (F1E, switch on)
   int       m_refuse;                 // refusal of the orders (CR_REF_*): the change's while it is on
   CrAgg     m_agg;                    // the UTC hour being filled
   long      m_nb;                     // session bars since Init
   CrRollSum m_a;                      // A: rolling mean of h - l over 70 session bars
   CrRollSum m_al;                     // A_long: over 280
   CrRollMax m_hh;                     // highest high of the 14 previous session bars (read before the push)
   CrRollMin m_ll;                     // lowest low of the 14 previous session bars
   CrRollMax m_hhl;                    // highest high of the last 280, this one included
   CrRollMin m_lll;                    // lowest low of the last 280, this one included
   CrRing    m_c;                      // the last 71 closes
   int       m_flag[CR_F1_SEQ_N];      // breakouts of the last 14 session bars: +1 up, -1 down, 0 none (ring)
   int       m_kflag;                  // slot of the next flag
   int       m_nflag;                  // flags kept (at most 14)
   datetime  m_day;                    // New York date of the current day's session bars (0 = none yet)
   double    m_dh, m_dl, m_dc;         // its high, low and last close so far
   bool      m_pd;                     // a previous New York date with session bars exists
   double    m_pdh, m_pdl, m_pdc;      // that date's high, low and last close
   double    m_x[];                    // the 15 features of the candidate (FEATURES order)

   bool Init(const int sleeve)
     {
      sl = sleeve;
      m_sym = g_sl[sl].sym;
      m_id = g_sl[sl].id;
      bool on = g_sl[sl].change_on;
      m_h2 = on && g_sl[sl].change == CR_CH_H2;
      m_refuse = on ? g_sl[sl].refuse_on : CR_REF_NONE;
      m_agg.Clear();
      m_nb = 0;
      m_a.Init(CR_F1_VOL_N, CR_F1_VOL_N);
      m_al.Init(CR_F1_VOL_LONG, CR_F1_VOL_LONG);
      m_hh.Init(CR_F1_CHAN);
      m_ll.Init(CR_F1_CHAN);
      m_hhl.Init(CR_F1_VOL_LONG);
      m_lll.Init(CR_F1_VOL_LONG);
      m_c.Init(CR_F1_RET_MAX + 1);
      for(int k = 0; k < CR_F1_SEQ_N; k++) m_flag[k] = 0;
      m_kflag = 0;
      m_nflag = 0;
      m_day = 0;
      m_dh = 0.0;
      m_dl = 0.0;
      m_dc = 0.0;
      m_pd = false;
      m_pdh = 0.0;
      m_pdl = 0.0;
      m_pdc = 0.0;
      ArrayResize(m_x, CR_F1_NFEAT);
      return true;
     }

   // the frozen scorecard (CR_F1Model.mqh) on the features m_x
   double Score()
     {
      double s = 0.0;
      for(int k = 0; k < CR_F1_NNUM; k++)
        {
         double z = (m_x[CR_F1_NUM_FEAT[k]] - CR_F1_MEAN[k]) / CR_F1_STD[k];
         if(z < -CR_F1_CLIP) z = -CR_F1_CLIP;
         if(z > CR_F1_CLIP) z = CR_F1_CLIP;
         s = s + z * CR_F1_COEF[k];
        }
      for(int j = 0; j < CR_F1_NDUM; j++)
        {
         double v = m_x[CR_F1_DUM_FEAT[j]];
         double d = (v >= CR_F1_DUM_LO[j] && v <= CR_F1_DUM_HI[j]) ? 1.0 : 0.0;
         s = s + d * CR_F1_COEF[CR_F1_NNUM + j];
        }
      return CR_F1_INTERCEPT + s;
     }

   // a complete session bar: the look-back state, then the candidate of its end
   void Session(const CrAggBar &hb, const int ny_hour, const int ny_dow0, const datetime ny_date, CrOut &out)
     {
      double o = hb.bo;
      double h = hb.bh;
      double l = hb.bl;
      double c = hb.bc;
      double rng = h - l;
      if(m_day != ny_date)                                   // the previous date with session bars (:152-157)
        {
         if(m_day != 0)
           {
            m_pd = true;
            m_pdh = m_dh;
            m_pdl = m_dl;
            m_pdc = m_dc;
           }
         m_day = ny_date;
         m_dh = h;
         m_dl = l;
         m_dc = c;
        }
      else
        {
         if(h > m_dh) m_dh = h;
         if(l < m_dl) m_dl = l;
         m_dc = c;
        }
      double hh = m_hh.Value();                              // h.shift(1).rolling(14).max(): NaN until 14 bars
      double ll = m_ll.Value();
      bool up = CrFinite(hh) && c > hh;
      bool dn = CrFinite(ll) && c < ll;
      double s_up = CrNaN(), s_dn = CrNaN();                 // up / dn .shift(1).rolling(14).sum()
      if(m_nflag >= CR_F1_SEQ_N)
        {
         int nu = 0, nd = 0;
         for(int k = 0; k < CR_F1_SEQ_N; k++)
           {
            if(m_flag[k] > 0) nu++;
            if(m_flag[k] < 0) nd++;
           }
         s_up = (double)nu;
         s_dn = (double)nd;
        }
      m_a.Push(rng);
      m_al.Push(rng);
      m_hhl.Push(h);
      m_lll.Push(l);
      m_c.Push(c);
      double A = m_a.Mean();
      double AL = m_al.Mean();
      double hhl = m_hhl.Value();
      double lll = m_lll.Value();
      double c4 = m_c.Last(4), c14 = m_c.Last(14), c70 = m_c.Last(70);
      m_hh.Push(h);                                          // for the next bars
      m_ll.Push(l);
      m_flag[m_kflag] = up ? 1 : (dn ? -1 : 0);
      m_kflag = (m_kflag + 1) % CR_F1_SEQ_N;
      if(m_nflag < CR_F1_SEQ_N) m_nflag++;
      m_nb++;
      int sig = up ? 1 : (dn ? -1 : 0);
      int dec_hour = ny_hour + 1;
      if(sig == 0 || dec_hour > CR_F1_LAST_DEC_H) return;
      if(!CrFinite(A) || !(A > 0.0)) return;
      if(!CrFinite(AL) || !(AL > 0.0)) return;               // A / 0 or A / NaN: not a finite feature
      double den = hhl - lll;
      if(!CrFinite(den) || !(den > 0.0)) return;
      double s = (double)sig;
      m_x[0] = (up ? c - hh : ll - c) / A;                     // brk
      m_x[1] = rng / A;                                        // bar
      m_x[2] = s * (c - o) / A;                                // body
      m_x[3] = s * (c - c4) / A;                               // ret4
      m_x[4] = s * (c - c14) / A;                              // ret14
      m_x[5] = s * (c - c70) / A;                              // ret70
      m_x[6] = (hh - ll) / A;                                  // chan
      m_x[7] = A / AL;                                         // vol
      m_x[8] = (up ? c - lll : hhl - c) / den;                 // pos
      m_x[9] = up ? s_up : s_dn;                               // seq
      m_x[10] = up ? s_dn : s_up;                              // opp
      m_x[11] = m_pd ? (up ? c - m_pdh : m_pdl - c) / A : CrNaN();   // pdd
      m_x[12] = m_pd ? s * (c - m_pdc) / A : CrNaN();          // dret
      m_x[13] = (double)dec_hour;                              // hour
      m_x[14] = (double)ny_dow0;                               // dow
      for(int k = 0; k < CR_F1_NFEAT; k++)
         if(!CrFinite(m_x[k])) return;
      datetime t_dec = hb.key + 3600;
      double score = Score();
      CrDec d;
      ZeroMemory(d);
      d.sleeve = sl;
      d.dec = t_dec;
      d.side = sig;
      d.what = CR_DEC_INFO;
      d.v1 = score;
      d.v2 = A;
      if(!CrOutDec(out, d)) JrnError(g_sl[sl].code, "more than CR_OUT_MAX decisions at " + IntegerToString((long)t_dec));
      if(!(score >= CR_F1_THR)) return;
      datetime x0 = t_dec + CR_F1_HOLD_S;
      datetime cap = F1ExitClock(t_dec);
      if(cap < x0) x0 = cap;
      CrOrder od;
      CrOrderClear(od);
      od.sleeve = sl;
      od.oid = CrOid(t_dec, m_id);
      od.side = sig;
      od.etype = CR_ET_MARKET;
      od.t_from = t_dec;
      od.t_to = t_dec + CR_F1_WAIT_S;
      od.stop_dist = CR_F1_STOP_K * A;
      od.x_sched = x0;
      od.x_gap = true;
      od.refuse = m_refuse;
      od.void_le = true;
      od.dec = t_dec;
      if(m_h2)
        {
         datetime ny = ClkUtcToNy(t_dec);
         datetime xa = ClkNyToUtc((datetime)((long)ClkBusinessDays(ClkDay(ny), CR_F1_H2_BDAYS) + CR_F1_EXIT_MIN * 60));
         datetime xb = F1FridayEnd(t_dec);                   // the entry bar lies in t_dec's server day
         od.xh = (xa < xb) ? xa : xb;
         od.xh_r = CR_F1_H2_R;
        }
      if(!CrOutOrder(out, od)) JrnError(g_sl[sl].code, "more than CR_OUT_MAX orders at " + IntegerToString((long)t_dec));
     }

   // an hour bar is complete: a session bar or nothing
   void Hour(const CrAggBar &hb, CrOut &out)
     {
      datetime ny = ClkUtcToNy(hb.key);
      int ny_hour = ClkMinOfDay(ny) / 60;
      int dow = ClkDow(ny);                                  // 0 = Sunday
      if(ny_hour < CR_F1_H0 || ny_hour >= CR_F1_H1 || dow < 1 || dow > 5) return;
      Session(hb, ny_hour, dow - 1, ClkDay(ny), out);
     }

   void OnBar(const int sym, const CrBar &b, CrOut &out)
     {
      if(sym != m_sym) return;
      CrAggBar done;
      ZeroMemory(done);
      // a bar of a new hour while the old one is still open: never under the minute contract (OnMinute closes every
      // hour at its end); the old hour is then decided here, before this bar reaches the paper
      if(m_agg.Add(b, CrAggKey(b.t, 3600), done)) Hour(done, out);
     }

   void OnMinute(const datetime M, CrOut &out)
     {
      if(M % 3600 != 0) return;
      CrAggBar cur;
      ZeroMemory(cur);
      if(!m_agg.Peek(cur) || cur.key + 3600 > M) return;
      m_agg.Take(cur);
      Hour(cur, out);
     }

   datetime LatestExit(const datetime open_time, const datetime comment_dec)
     {
      datetime t_dec = open_time - open_time % 3600;
      if(comment_dec > 0 && comment_dec % 3600 == 0 && comment_dec <= open_time && (long)(open_time - comment_dec) <= CR_F1_JOIN_S)
         t_dec = comment_dec;
      datetime x0 = t_dec + CR_F1_HOLD_S;
      datetime cap = F1ExitClock(t_dec);
      if(cap < x0) x0 = cap;
      return x0;
     }
  };
#endif
