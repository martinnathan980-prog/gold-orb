//+------------------------------------------------------------------+
//| CR_Rule_Brk72.mqh - BKB / BKE brk72_24h_wd on BTC and ETH, with   |
//| S0.75r (BKB) and K1 (BKE) behind their switches (SPEC 3).         |
//| Owner: E.                                                         |
//|                                                                  |
//| The rule (lab/r2/tracks/crypto/strategy.py, wrapper              |
//| lab/r2/recalc.py:43-53):                                         |
//|   bars   UTC hour bars of the kept M1 bars (h1_bars :82-98): h = |
//|          max of the per-bar mids (bh + ah) / 2, l = min of       |
//|          (bl + al) / 2, c = (bc + ac) / 2 of the last bar. Hours |
//|          without a bar do not exist. An hour is complete at the  |
//|          barrier of its end, D = hour start + 1 h.               |
//|   signal at D (_brk :153-178): c above the highest of the 72     |
//|          previous closes -> long, below the lowest -> short;     |
//|          D on a UTC weekday (_finish :131-132).                  |
//|   ATR    mean of the last 24 true ranges (sma_atr :101-106):     |
//|          TR = max(h - l, |h - pc|, |l - pc|), the first one h - l |
//|          (pandas rolling mean: CrRollSum); finite and > 0.       |
//|   order  market, window [D, D + 5 min] (_finish :115-119),       |
//|          stop_dist 3 ATR (:139), time exit x = D + 24 h (:120)   |
//|          with the gap rule, void_le (the wrapper drops an order  |
//|          whose exit bar does not follow its entry bar).          |
//| Constants: n 72, stop_atr 3, hold_h 24, dow weekday              |
//| (strategy.py:242-243), atr_n 24, max_delay_min 5 (:52-53).       |
//|                                                                  |
//| The two changes, while their switch is on (g_sl[].change_on):    |
//|   S0.75r (BKB): stop_dist = 0.75 x (3 ATR), the lab's k x r0     |
//|          (payoff variants.py:181-187, look_spec k 0.75); refusal |
//|          1 (payoff) in the paper; stake factor in CR_Sizing.     |
//|   K1 (BKE): riskbp = 1e4 x stop_dist / P, P = c, the mid close   |
//|          of the last kept bar before D (synthesis_B s1_run.py    |
//|          :104-105); Y = the UTC year of D; with T(Y) > 0 from    |
//|          InpK1T and riskbp >= T(Y): nothing is emitted (DEC      |
//|          skip=K1), so the skipped signal blocks nothing (the     |
//|          lab removes it and re-simulates, vhi_sleeves.py         |
//|          :459-507). Otherwise a DEC info line (v1 riskbp, v2     |
//|          T(Y)) and the order, with refusal 2 (synthesis_B) in    |
//|          the paper.                                              |
//|                                                                  |
//| InpK1T (SPEC 1, 10.14): entries "YYYY:T" separated by ';',       |
//|   YYYY a year 2000-2100, T >= 0 in bp, a plain decimal number    |
//|   (digits, '.', digits, optional exponent; the lab writes 17     |
//|   significant digits). Spaces around entries and around ':' are  |
//|   allowed; empty entries are skipped; a year given twice, another|
//|   form, or more than 64 entries: refused (Init false, ERROR at   |
//|   OnInit). It is checked whatever the switch. A year with no T,  |
//|   or T = 0: K1 off for the signals of that year. Every K1 line   |
//|   carries the T it used (v2). Brk72K1Text() gives the table read |
//|   ("YYYY:T;...", 17 digits) for the driver's INIT line.          |
//|   Brk72K1Known(year): a T > 0 exists for that year.              |
//|                                                                  |
//| LatestExit (SPEC 4.8): D = the decision of the comment when it   |
//|   lies on an hour at most 10 min before open_time, else open_time|
//|   floored to the UTC hour; exit min(D + 24 h, Friday 23:54 server|
//|   of open_time's server week).                                   |
//+------------------------------------------------------------------+
#ifndef CR_RULE_BRK72_MQH
#define CR_RULE_BRK72_MQH
#include "CR_Types.mqh"
#include "CR_Clock.mqh"
#include "CR_Journal.mqh"
#include "CR_Math.mqh"

#define CR_BRK_N 72                    // channel of closes (strategy.py:243)
#define CR_BRK_ATR_N 24                // ATR bars (strategy.py:52)
#define CR_BRK_STOP_ATR 3.0            // stop distance in ATR (strategy.py:243)
#define CR_BRK_HOLD_S 86400            // hold_h 24: exit = D + int(round(24 x 60)) minutes (strategy.py:120, 243)
#define CR_BRK_WAIT_S 300              // max_delay_min 5: first bar within 5 min of D (strategy.py:53, 119)
#define CR_BRK_S075_K 0.75             // S0.75r: k (look_spec.json brk72_24h_wd__btcusd+S0.75r)
#define CR_BRK_JOIN_S 600              // LatestExit: an open time at most 10 min after its decision
#define CR_K1_MAX 64                   // InpK1T entries

// ---- the K1 table read from InpK1T (one per EA: K1 belongs to BKE only)
int    g_brk_k1_year[CR_K1_MAX];
double g_brk_k1_t[CR_K1_MAX];
int    g_brk_k1_n = 0;

bool Brk72Digit(const ushort ch) { return ch >= '0' && ch <= '9'; }

// a plain decimal number without sign: digits, optionally '.' and digits, optionally e or E, a sign and digits
bool Brk72IsNumber(const string s)
  {
   int n = StringLen(s);
   int i = 0, d = 0;
   while(i < n && Brk72Digit(StringGetCharacter(s, i)))
     {
      i++;
      d++;
     }
   if(d == 0) return false;
   if(i < n && StringGetCharacter(s, i) == '.')
     {
      i++;
      int f = 0;
      while(i < n && Brk72Digit(StringGetCharacter(s, i)))
        {
         i++;
         f++;
        }
      if(f == 0) return false;
     }
   if(i < n && (StringGetCharacter(s, i) == 'e' || StringGetCharacter(s, i) == 'E'))
     {
      i++;
      if(i < n && (StringGetCharacter(s, i) == '+' || StringGetCharacter(s, i) == '-')) i++;
      int e = 0;
      while(i < n && Brk72Digit(StringGetCharacter(s, i)))
        {
         i++;
         e++;
        }
      if(e == 0) return false;
     }
   return i == n;
  }

// InpK1T -> the K1 table; false and why when the text is refused (the table is then empty)
bool Brk72ParseK1T(const string text, string &why)
  {
   g_brk_k1_n = 0;
   why = "";
   string t = text;
   StringTrimLeft(t);
   StringTrimRight(t);
   if(t == "") return true;
   string part[];
   int n = StringSplit(t, ';', part);
   for(int k = 0; k < n; k++)
     {
      string e = part[k];
      StringTrimLeft(e);
      StringTrimRight(e);
      if(e == "") continue;
      int c = StringFind(e, ":");
      if(c < 0 || StringFind(e, ":", c + 1) >= 0)
        {
         why = "'" + e + "' is not YYYY:T";
         g_brk_k1_n = 0;
         return false;
        }
      string ys = StringSubstr(e, 0, c);
      string ts = StringSubstr(e, c + 1);
      StringTrimLeft(ys);
      StringTrimRight(ys);
      StringTrimLeft(ts);
      StringTrimRight(ts);
      bool year_ok = (StringLen(ys) == 4);
      for(int i = 0; i < StringLen(ys) && year_ok; i++)
         if(!Brk72Digit(StringGetCharacter(ys, i))) year_ok = false;
      int y = year_ok ? (int)StringToInteger(ys) : 0;
      if(!year_ok || y < 2000 || y > 2100)
        {
         why = "'" + e + "': the year must be 2000-2100";
         g_brk_k1_n = 0;
         return false;
        }
      if(!Brk72IsNumber(ts))
        {
         why = "'" + e + "': T must be a number of bp (e.g. 465.1178140105435)";
         g_brk_k1_n = 0;
         return false;
        }
      double v = StringToDouble(ts);
      if(!MathIsValidNumber(v) || v < 0.0)
        {
         why = "'" + e + "': T must be finite and >= 0";
         g_brk_k1_n = 0;
         return false;
        }
      for(int j = 0; j < g_brk_k1_n; j++)
         if(g_brk_k1_year[j] == y)
           {
            why = "year " + IntegerToString(y) + " given twice";
            g_brk_k1_n = 0;
            return false;
           }
      if(g_brk_k1_n >= CR_K1_MAX)
        {
         why = "more than " + IntegerToString(CR_K1_MAX) + " entries";
         g_brk_k1_n = 0;
         return false;
        }
      g_brk_k1_year[g_brk_k1_n] = y;
      g_brk_k1_t[g_brk_k1_n] = v;
      g_brk_k1_n++;
     }
   return true;
  }

// T(year) of the K1 table, 0 when the year has none
double Brk72K1T(const int year)
  {
   for(int j = 0; j < g_brk_k1_n; j++)
      if(g_brk_k1_year[j] == year) return g_brk_k1_t[j];
   return 0.0;
  }

// a T > 0 exists for that year (CR_Main pushes "K1 with no T for the year" when the switch is on and this is false)
bool Brk72K1Known(const int year) { return Brk72K1T(year) > 0.0; }

// the table as the EA understood it: "YYYY:T;..." with 17 significant digits
string Brk72K1Text()
  {
   string s = "";
   for(int j = 0; j < g_brk_k1_n; j++)
     {
      if(j > 0) s = s + ";";
      s = s + IntegerToString(g_brk_k1_year[j]) + ":" + DoubleToString(g_brk_k1_t[j], -16);
     }
   return s;
  }

// K1's risk in bp: 1e4 x stop_dist / P, P = the mid close of the last kept bar before the decision (s1_run.py:105)
double Brk72RiskBp(const double stop_dist, const double p) { return 1e4 * stop_dist / p; }

// Friday 23:54 server of the server week of utc, as UTC (the last crypto bar before the weekend closure)
datetime Brk72FridayEnd(const datetime utc)
  {
   datetime srv = ClkUtcToServer(utc);
   long day = (long)ClkDay(srv);
   int mon0 = (ClkDow(srv) + 6) % 7;                         // 0 = Monday ... 6 = Sunday
   long fri = day + (long)(4 - mon0) * 86400 + 23 * 3600 + 54 * 60;
   return ClkServerToUtc((datetime)fri);
  }

class CRuleBrk72
  {
public:
   int       sl;
   int       m_sym;                    // traded and read symbol
   int       m_id;                     // sleeve id (oid = decision x 100 + id)
   bool      m_k1;                     // K1 in force (BKE, switch on)
   bool      m_s075;                   // S0.75r in force (BKB, switch on)
   int       m_refuse;                 // refusal of the orders (CR_REF_*): the change's while it is on
   CrAgg     m_agg;                    // the UTC hour being filled
   long      m_nh;                     // hour bars since Init
   double    m_pc;                     // close of the previous hour bar
   CrRollSum m_tr;                     // ATR24: rolling mean of the true ranges
   CrRollMax m_cmax;                   // highest of the 72 previous closes
   CrRollMin m_cmin;                   // lowest of the 72 previous closes

   bool Init(const int sleeve)
     {
      sl = sleeve;
      m_sym = g_sl[sl].sym;
      m_id = g_sl[sl].id;
      bool on = g_sl[sl].change_on;
      m_k1 = on && g_sl[sl].change == CR_CH_K1;
      m_s075 = on && g_sl[sl].change == CR_CH_S075;
      m_refuse = on ? g_sl[sl].refuse_on : CR_REF_NONE;
      m_agg.Clear();
      m_nh = 0;
      m_pc = 0.0;
      m_tr.Init(CR_BRK_ATR_N, CR_BRK_ATR_N);
      m_cmax.Init(CR_BRK_N);
      m_cmin.Init(CR_BRK_N);
      if(g_sl[sl].change == CR_CH_K1)
        {
         string why = "";
         if(!Brk72ParseK1T(g_cfg.k1t, why))
           {
            JrnError(g_sl[sl].code, "InpK1T refused: " + why);
            return false;
           }
        }
      return true;
     }

   // an hour bar is complete (its end D has passed the barrier): ATR, channel, signal, order
   void Hour(const CrAggBar &hb, CrOut &out)
     {
      double h = hb.mh;
      double l = hb.ml;
      double c = (hb.bc + hb.ac) / 2;
      double tr = h - l;                                     // sma_atr: the first true range is h - l
      if(m_nh > 0)
        {
         double a = MathAbs(h - m_pc);
         double b = MathAbs(l - m_pc);
         if(a > tr) tr = a;
         if(b > tr) tr = b;
        }
      m_tr.Push(tr);
      double atr = m_tr.Mean();
      double hi = m_cmax.Value();                            // c.rolling(72).max().shift(1): NaN until 72 closes
      double lo = m_cmin.Value();
      m_cmax.Push(c);
      m_cmin.Push(c);
      m_pc = c;
      m_nh++;
      int side = 0;
      if(CrFinite(hi) && c > hi) side = 1;
      else if(CrFinite(lo) && c < lo) side = -1;
      if(side == 0) return;
      datetime D = hb.key + 3600;
      int dow = ClkDow(D);                                   // UTC weekday of the decision: 1 = Monday ... 5 = Friday
      if(dow < 1 || dow > 5) return;
      if(!CrFinite(atr) || !(atr > 0.0)) return;
      double sd = atr * CR_BRK_STOP_ATR;
      if(m_k1)
        {
         double riskbp = Brk72RiskBp(sd, c);
         double T = Brk72K1T(ClkYear(D));
         CrDec d;
         ZeroMemory(d);
         d.sleeve = sl;
         d.dec = D;
         d.side = side;
         d.v1 = riskbp;
         d.v2 = T;
         d.what = CR_DEC_INFO;
         bool skip = (T > 0.0 && riskbp >= T);
         if(skip) d.what = CR_DEC_SKIP_K1;
         if(!CrOutDec(out, d)) JrnError(g_sl[sl].code, "more than CR_OUT_MAX decisions at " + IntegerToString((long)D));
         if(skip) return;
        }
      if(m_s075) sd = CR_BRK_S075_K * sd;
      CrOrder o;
      CrOrderClear(o);
      o.sleeve = sl;
      o.oid = CrOid(D, m_id);
      o.side = side;
      o.etype = CR_ET_MARKET;
      o.t_from = D;
      o.t_to = D + CR_BRK_WAIT_S;
      o.stop_dist = sd;
      o.x_sched = D + CR_BRK_HOLD_S;
      o.x_gap = true;
      o.refuse = m_refuse;
      o.void_le = true;
      o.dec = D;
      if(!CrOutOrder(out, o)) JrnError(g_sl[sl].code, "more than CR_OUT_MAX orders at " + IntegerToString((long)D));
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
      datetime D = open_time - open_time % 3600;
      if(comment_dec > 0 && comment_dec % 3600 == 0 && comment_dec <= open_time && (long)(open_time - comment_dec) <= CR_BRK_JOIN_S)
         D = comment_dec;
      datetime x = D + CR_BRK_HOLD_S;
      datetime fri = Brk72FridayEnd(open_time);
      if(fri < x) x = fri;
      return x;
     }
  };
#endif
