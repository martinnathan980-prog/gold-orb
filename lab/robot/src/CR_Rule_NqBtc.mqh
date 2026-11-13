//+------------------------------------------------------------------+
//| CR_Rule_NqBtc.mqh - NQB nq_btc_follow: BTC follows a 6-sigma      |
//| US100 impulse (SPEC 3). Reads US100 and BTC bars. Owner: F.       |
//|                                                                  |
//| The rule (lab/r2/tracks/leadlag/strategy.py xlead_orders :188-   |
//| 238, params FINALISTS["nq_btc_follow"] :328-334, sig_days 20     |
//| :189), on a one-minute grid of UTC minutes:                      |
//|   grid   starts at the first BTC bar (_grid :98-103: the grid of |
//|          the traded frame; leader bars before it are dropped,    |
//|          _on_grid :106-110). Every minute after it is a grid     |
//|          minute, markets open or not.                            |
//|   r      per market and minute g with a bar at g: log of its mid |
//|          close over the mid close of the last bar in [g-4, g-1]  |
//|          (_ffill limit 3 :113-119, _lret k 1 :122-125); NaN when |
//|          there is no such bar or no bar at g. Mid = (bc + ac)/2  |
//|          of the paper quotes (:191, set_leader :82).             |
//|   sigma  per market at g: RMS of the finite r of the 28,800 grid |
//|          minutes up to g - 1, NaN under 4,800 of them            |
//|          (_trail_rms :128-134). Two rolling sums per market, as  |
//|          pandas makes them (CrRollSum): r x r with 0 for a       |
//|          missing r, and the count of finite r. No re-sum: pandas |
//|          never re-sums, so the robot's sigma keeps its bits.     |
//|   signal g a New York weekday minute in [09:30, 16:00) (uscash   |
//|          :168, :180-184), a BTC bar at g, x = r_US100(g) finite, |
//|          sigma_L(g) and sigma_B(g) finite, |x| >= 6 sigma_L(g)   |
//|          (:217-218). Decided at the barrier g + 1, when every bar|
//|          starting before g + 1 is final.                         |
//|   order  market, side = sign(x) (dirn 1), stop_dist = 2 x        |
//|          sigma_B(g) x sqrt(60) x the BTC mid close at g (:230,   |
//|          :234), time exit x = entry + 60 min with the gap rule   |
//|          (gl.exit_index, :229). The entry is the first BTC bar   |
//|          in [g + 1, g + 2] (:223-227). The order is emitted at   |
//|          g + 1 for the bar g + 1 (x = g + 61 min); when no BTC   |
//|          bar starts at g + 1, it is emitted again at g + 2 for   |
//|          the bar g + 2 (x = g + 62 min), with the same oid, so   |
//|          that x is always 60 minutes after the real entry bar.   |
//|          void_le: the lab keeps only orders whose exit bar       |
//|          follows the entry bar (:237 exit_i > entry_i), which is |
//|          the paper's void_le. stop_dist finite and > 0, side not |
//|          0 (:237). Every signal is emitted; the paper keeps one  |
//|          trade at a time (sim.py:80). drop_duplicates (:238)     |
//|          never binds: a signal at g' > g needs a BTC bar at g',  |
//|          so the entry bar of g comes before the one of g'.       |
//|   dec    g + 1 (the barrier that decides); oid = dec x 100 + id. |
//|          Each signal also writes one DEC info line, just before  |
//|          its first order: v1 = x, v2 = sigma_L(g).               |
//| Constants: leader us100, pred lead, k 1, z 6, sess uscash,       |
//| hold 60, stop 2.0, dirn 1, sig_days 20, delay 0                  |
//| (strategy.py:188-189, :331-332).                                 |
//|                                                                  |
//| Feeding (CR_Main minute contract): OnBar keeps the bar of each   |
//| market for its minute; OnMinute(M) processes every grid minute   |
//| before M. A bar of a later minute first processes the minutes    |
//| before it (they are complete: bars come in time order), so a     |
//| skipped OnMinute changes nothing.                                |
//|                                                                  |
//| LatestExit (SPEC 4.8): the entry is at most 5 min before the     |
//| open time o, so the paper's exit is at most o + 60 min.          |
//+------------------------------------------------------------------+
#ifndef CR_RULE_NQBTC_MQH
#define CR_RULE_NQBTC_MQH
#include "CR_Types.mqh"
#include "CR_Clock.mqh"
#include "CR_Journal.mqh"
#include "CR_Math.mqh"

#define CR_NQB_Z 6.0                   // z: |x| >= 6 sigma_L (strategy.py:332, :217)
#define CR_NQB_STOP 2.0                // stop: 2 sigma_B sqrt(hold) x price (strategy.py:332, :234)
#define CR_NQB_HOLD_MIN 60.0           // hold in minutes, inside the stop's sqrt (strategy.py:332, :234)
#define CR_NQB_HOLD_S 3600             // hold: time exit 60 min after the entry bar (strategy.py:229)
#define CR_NQB_WIN 28800               // sigma window: sig_days 20 x 1440 grid minutes (strategy.py:189, :195)
#define CR_NQB_MINOBS 4800             // at least win // 6 finite returns (strategy.py:196)
#define CR_NQB_FFILL 3                 // the previous close may be 3 minutes older than g - 1 (_ffill, strategy.py:113)
#define CR_NQB_SESS_A 570              // uscash: from 09:30 New York (strategy.py:168)
#define CR_NQB_SESS_B 960              // to 16:00 New York, excluded; the exit need not fall inside (strategy.py:168, :183)
#define CR_NQB_DIRN 1                  // dirn: trade the side of the leader's move (strategy.py:233, :331)
#define CR_NQB_L 0                     // series of the leader (US100)
#define CR_NQB_F 1                     // series of the follower (BTC)

class CRuleNqb
  {
public:
   int       sl;
   int       m_id;                     // sleeve id (oid = decision x 100 + id)
   int       m_sym[2];                 // symbol id of the leader and of the follower
   bool      m_started;                // the grid has started (the first BTC bar was seen)
   long      m_next;                   // next grid minute to process (minutes since 1970)
   bool      m_pend[2];                // a bar waits for its grid minute
   long      m_pend_m[2];              // its minute
   double    m_pend_c[2];              // its mid close
   bool      m_last_ok[2];             // a bar was processed on the grid
   long      m_last_m[2];              // minute of the last bar processed (the forward fill)
   double    m_last_c[2];              // its mid close
   CrRollSum m_s2[2];                  // rolling sum of r x r (0 for a missing r), 28,800 grid minutes
   CrRollSum m_n[2];                   // rolling sum of 1 for a finite r, 0 otherwise
   bool      m_pd;                     // the signal of the last grid minute: its first entry minute is still to be seen
   long      m_pd_g;                   // its decision minute g
   int       m_pd_side;
   double    m_pd_sd;
   long      m_g;                      // the last grid minute processed (tests and diagnosis)
   double    m_r[2];                   // its r: x = r of the leader, r of BTC
   double    m_sig[2];                 // its sigma: RMS of the window that ends at the minute before
   long      m_signals;                // signals since Init

   bool Init(const int sleeve)
     {
      sl = sleeve;
      m_id = g_sl[sl].id;
      m_sym[CR_NQB_L] = g_sl[sl].sym2;
      m_sym[CR_NQB_F] = g_sl[sl].sym;
      m_started = false;
      m_next = 0;
      for(int s = 0; s < 2; s++)
        {
         m_pend[s] = false;
         m_pend_m[s] = 0;
         m_pend_c[s] = 0.0;
         m_last_ok[s] = false;
         m_last_m[s] = 0;
         m_last_c[s] = 0.0;
         m_s2[s].Init(CR_NQB_WIN, 1);
         m_n[s].Init(CR_NQB_WIN, 1);
         m_r[s] = CrNaN();
         m_sig[s] = CrNaN();
        }
      m_pd = false;
      m_pd_g = 0;
      m_pd_side = 0;
      m_pd_sd = 0.0;
      m_g = 0;
      m_signals = 0;
      if(m_sym[CR_NQB_L] < 0 || m_sym[CR_NQB_L] >= CR_NSYM || m_sym[CR_NQB_L] == m_sym[CR_NQB_F]) return false;
      return true;
     }

   // sigma of series s over the window pushed so far (_trail_rms :131-133, before its one-minute lag)
   double Rms(const int s)
     {
      double cnt = m_n[s].Sum();
      if(!(cnt >= CR_NQB_MINOBS)) return CrNaN();
      double s2 = m_s2[s].Sum();
      if(s2 < 0.0) s2 = 0.0;                                   // np.maximum(s2, 0.0)
      return MathSqrt(s2 / cnt);                               // cnt >= 4,800: np.maximum(cnt, 1.0) is cnt
     }

   // an order of the signal decided at minute g, for the entry bar of minute e (g + 1, or g + 2 the second time)
   void Emit(const long g, const long e, const int side, const double sd, CrOut &out)
     {
      datetime dec = (datetime)((g + 1) * 60);
      CrOrder o;
      CrOrderClear(o);
      o.sleeve = sl;
      o.oid = CrOid(dec, m_id);
      o.side = side;
      o.etype = CR_ET_MARKET;
      o.t_from = (datetime)(e * 60);
      o.t_to = o.t_from;
      o.stop_dist = sd;
      o.x_sched = o.t_from + CR_NQB_HOLD_S;
      o.x_gap = true;
      o.void_le = true;
      o.dec = dec;
      if(!CrOutOrder(out, o)) JrnError(g_sl[sl].code, "more than CR_OUT_MAX orders at " + IntegerToString((long)dec));
     }

   // one grid minute g: the returns, the sigmas (lagged), the second entry minute of the signal of g - 1, the signal of g
   void GridMinute(const long g, CrOut &out)
     {
      bool has[2];
      double c[2];
      for(int s = 0; s < 2; s++)
        {
         has[s] = m_pend[s] && m_pend_m[s] == g;
         c[s] = has[s] ? m_pend_c[s] : 0.0;
         m_sig[s] = Rms(s);                                    // the window ends at g - 1 (np.r_[nan, s[:-1]])
         double r = CrNaN();
         if(has[s] && m_last_ok[s] && g - 1 - m_last_m[s] <= CR_NQB_FFILL) r = MathLog(c[s] / m_last_c[s]);
         m_r[s] = r;
         bool ok = CrFinite(r);
         m_s2[s].Push(ok ? r * r : 0.0);
         m_n[s].Push(ok ? 1.0 : 0.0);
         if(has[s])
           {
            m_last_ok[s] = true;
            m_last_m[s] = g;
            m_last_c[s] = c[s];
            m_pend[s] = false;
           }
        }
      m_g = g;
      if(m_pd)
        {
         // the first entry minute of the signal of g - 1 had no BTC bar: its order is emitted again for the next minute
         if(m_pd_g == g - 1 && !has[CR_NQB_F]) Emit(m_pd_g, g + 1, m_pd_side, m_pd_sd, out);
         m_pd = false;
        }
      double x = m_r[CR_NQB_L];
      double sig_l = m_sig[CR_NQB_L];
      double sig_b = m_sig[CR_NQB_F];
      if(!has[CR_NQB_F] || !CrFinite(x) || !CrFinite(sig_l) || !CrFinite(sig_b)) return;
      if(!(MathAbs(x) >= CR_NQB_Z * sig_l)) return;
      datetime ny = ClkUtcToNy((datetime)(g * 60));
      int mod = ClkMinOfDay(ny);
      int dow = ClkDow(ny);                                    // 1 = Monday ... 5 = Friday
      if(mod < CR_NQB_SESS_A || mod >= CR_NQB_SESS_B || dow < 1 || dow > 5) return;
      int side = 0;
      if(x > 0.0) side = CR_NQB_DIRN;
      else if(x < 0.0) side = -CR_NQB_DIRN;
      double sd = CR_NQB_STOP * sig_b * MathSqrt(CR_NQB_HOLD_MIN) * c[CR_NQB_F];
      if(side == 0 || !CrFinite(sd) || !(sd > 0.0)) return;
      m_signals++;
      CrDec d;
      ZeroMemory(d);
      d.sleeve = sl;
      d.dec = (datetime)((g + 1) * 60);
      d.side = side;
      d.what = CR_DEC_INFO;
      d.v1 = x;
      d.v2 = sig_l;
      if(!CrOutDec(out, d)) JrnError(g_sl[sl].code, "more than CR_OUT_MAX decisions at " + IntegerToString((long)d.dec));
      Emit(g, g + 1, side, sd, out);
      m_pd = true;
      m_pd_g = g;
      m_pd_side = side;
      m_pd_sd = sd;
     }

   // every grid minute up to gmax, in order
   void ProcessUpTo(const long gmax, CrOut &out)
     {
      while(m_next <= gmax)
        {
         GridMinute(m_next, out);
         m_next++;
        }
     }

   void OnBar(const int sym, const CrBar &b, CrOut &out)
     {
      int s = -1;
      if(sym == m_sym[CR_NQB_F]) s = CR_NQB_F;
      else if(sym == m_sym[CR_NQB_L]) s = CR_NQB_L;
      if(s < 0) return;
      long m = (long)b.t / 60;
      double c = (b.bc + b.ac) / 2;
      if(!m_started)
        {
         if(s == CR_NQB_L)
           {
            m_pend[s] = true;                                  // kept only if the grid starts in its minute
            m_pend_m[s] = m;
            m_pend_c[s] = c;
            return;
           }
         m_started = true;
         m_next = m;
         if(m_pend[CR_NQB_L] && m_pend_m[CR_NQB_L] != m) m_pend[CR_NQB_L] = false;
        }
      if(m < m_next) return;                                   // a bar of a minute already processed: never under the contract
      if(m > m_next) ProcessUpTo(m - 1, out);                  // the minutes before this bar are complete
      m_pend[s] = true;
      m_pend_m[s] = m;
      m_pend_c[s] = c;
     }

   void OnMinute(const datetime M, CrOut &out)
     {
      if(!m_started) return;
      long gmax = (long)M / 60 - 1;
      if(gmax >= m_next) ProcessUpTo(gmax, out);
     }

   datetime LatestExit(const datetime open_time, const datetime comment_dec)
     {
      return open_time + CR_NQB_HOLD_S;
     }
  };
#endif
