//+------------------------------------------------------------------+
//| CR_Math.mqh - rolling primitives and bar aggregates. Owner: B.    |
//|                                                                  |
//| Each class reproduces one pandas call, step by step, so that a   |
//| rule fed the same series from the same start gets the same       |
//| doubles as the lab (T2 checks it against pandas 3.0.5 bit for    |
//| bit). Call Init before anything else; Clear forgets the values.  |
//| A value that is not a finite number (NaN, and also inf, which    |
//| pandas would count) is a missing value. The rules never push inf.|
//|                                                                  |
//|   CrRing        ring buffer of the last cap doubles              |
//|                   Get(0) = the oldest kept, Last(0) = the newest |
//|   CrRollSum     rolling(n, min_periods).sum() / .mean()          |
//|                   pandas roll_sum / roll_mean: Kahan sums with   |
//|                   separate add and remove compensations, the     |
//|                   "same value repeated" rule (GH#42064) and the  |
//|                   sign clamp of the mean. No periodic re-sum:    |
//|                   pandas never re-sums a fixed window, and a     |
//|                   re-sum would move the result off its bits.     |
//|   CrRollMax/Min rolling(n).max() / .min(), min_periods = n       |
//|   CrRollMedian  rolling(n, min_periods).median()                 |
//|   CrWilder      ewm(alpha = 1/n, adjust = False).mean(), NaN     |
//|                   gaps as pandas (the old weight keeps decaying) |
//|   CrMedian      median of the finite values among the first n    |
//|                   of an array (numpy / pandas median)            |
//|   CrAgg         one bucket of M1 bars at a time: bid and ask     |
//|                   aggregated apart (goldlab.data.bars) and the   |
//|                   extremes of the per-bar mids (crypto h1_bars)  |
//+------------------------------------------------------------------+
#ifndef CR_MATH_MQH
#define CR_MATH_MQH
#include "CR_Types.mqh"

//+------------------------------------------------------------------+
//| CrRing                                                           |
//+------------------------------------------------------------------+
class CrRing
  {
public:
   double   m_v[];
   int      m_cap;                        // capacity
   int      m_head;                       // slot of the oldest value
   int      m_n;                          // values kept (at most m_cap)

            CrRing() { m_cap = 0; m_head = 0; m_n = 0; }

   void Init(const int cap)
     {
      m_cap = (cap > 0) ? cap : 1;
      ArrayResize(m_v, m_cap);
      m_head = 0;
      m_n = 0;
     }

   void Clear()
     {
      m_head = 0;
      m_n = 0;
     }

   void Push(const double x)
     {
      if(m_cap <= 0) Init(1);
      if(m_n < m_cap)
        {
         m_v[(m_head + m_n) % m_cap] = x;
         m_n++;
        }
      else
        {
         m_v[m_head] = x;
         m_head = (m_head + 1) % m_cap;
        }
     }

   int Count() { return m_n; }

   // k = 0: the oldest value kept; NaN outside [0, Count())
   double Get(const int k)
     {
      if(k < 0 || k >= m_n) return CrNaN();
      return m_v[(m_head + k) % m_cap];
     }

   // k = 0: the newest value; NaN outside [0, Count())
   double Last(const int k)
     {
      if(k < 0 || k >= m_n) return CrNaN();
      return m_v[(m_head + m_n - 1 - k) % m_cap];
     }
  };

//+------------------------------------------------------------------+
//| CrRollSum: pandas roll_sum / roll_mean (window/aggregations.pyx) |
//| on a fixed window: the value leaving the window is removed first |
//| (its own Kahan compensation), then the new one is added.         |
//+------------------------------------------------------------------+
class CrRollSum
  {
public:
   double   m_win[];                      // the last n values pushed (missing ones included)
   int      m_n;                          // window
   int      m_minp;                       // min_periods
   int      m_k;                          // slot of the next value
   int      m_cnt;                        // values in the window (at most n)
   int      m_nobs;                       // valid values in the window
   int      m_neg;                        // negative valid values in the window (mean: sign clamp)
   double   m_sum;
   double   m_cadd;                       // compensation of the additions
   double   m_crem;                       // compensation of the removals
   long     m_same;                       // valid values in a row equal to m_prev (never lowered by a removal)
   double   m_prev;                       // the last valid value
   bool     m_prev_ok;

            CrRollSum() { m_n = 0; m_minp = 0; m_k = 0; m_cnt = 0; m_nobs = 0; m_neg = 0; m_sum = 0.0; m_cadd = 0.0; m_crem = 0.0;
                          m_same = 0; m_prev = 0.0; m_prev_ok = false; }

   void Clear()
     {
      m_k = 0;
      m_cnt = 0;
      m_nobs = 0;
      m_neg = 0;
      m_sum = 0.0;
      m_cadd = 0.0;
      m_crem = 0.0;
      m_same = 0;
      m_prev = 0.0;
      m_prev_ok = false;
     }

   void Init(const int n, const int min_periods)
     {
      m_n = (n > 0) ? n : 1;
      m_minp = (min_periods > 0) ? min_periods : 0;
      ArrayResize(m_win, m_n);
      Clear();
     }

   void Add(const double x)
     {
      if(!MathIsValidNumber(x)) return;
      m_nobs++;
      double y = x - m_cadd;
      double t = m_sum + y;
      m_cadd = t - m_sum - y;
      m_sum = t;
      if(x < 0.0) m_neg++;
      if(m_prev_ok && x == m_prev) m_same++;
      else m_same = 1;
      m_prev = x;
      m_prev_ok = true;
     }

   void Remove(const double x)
     {
      if(!MathIsValidNumber(x)) return;
      m_nobs--;
      double y = -x - m_crem;
      double t = m_sum + y;
      m_crem = t - m_sum - y;
      m_sum = t;
      if(x < 0.0) m_neg--;
     }

   // NaN (any value that is not finite) = a missing value: kept in the window, not counted
   void Push(const double x)
     {
      if(m_n <= 0) Init(1, 1);
      if(m_n == 1)
        {
         // pandas sets a window of one up afresh at every step (start >= previous end)
         m_nobs = 0;
         m_neg = 0;
         m_sum = 0.0;
         m_cadd = 0.0;
         m_crem = 0.0;
         m_same = 0;
         m_prev_ok = false;
        }
      else if(m_cnt == m_n) Remove(m_win[m_k]);
      Add(x);
      m_win[m_k] = x;
      m_k = (m_k + 1) % m_n;
      if(m_cnt < m_n) m_cnt++;
     }

   // pandas calc_sum: 0 for an empty window with min_periods 0; NaN below min_periods
   double Sum()
     {
      if(m_nobs == 0 && m_minp == 0) return 0.0;
      if(m_nobs < m_minp) return CrNaN();
      if(m_same >= m_nobs) return m_prev * m_nobs;
      return m_sum;
     }

   // pandas calc_mean: NaN for an empty window or below min_periods; a mean of one sign never shows the other sign
   double Mean()
     {
      if(m_nobs < m_minp || m_nobs <= 0) return CrNaN();
      double r = m_sum / (double)m_nobs;
      if(m_same >= m_nobs) r = m_prev;
      else if(m_neg == 0 && r < 0.0) r = 0.0;
      else if(m_neg == m_nobs && r > 0.0) r = 0.0;
      return r;
     }

   int Valid() { return m_nobs; }
  };

//+------------------------------------------------------------------+
//| rolling extreme of the valid values among the last n pushes      |
//| (a monotonic queue); NaN while fewer than min_periods are valid  |
//+------------------------------------------------------------------+
class CrRollExt
  {
public:
   bool     m_max;                        // true: maximum, false: minimum
   int      m_n;
   int      m_minp;
   long     m_seq;                        // values pushed so far
   uchar    m_ok[];                       // validity (1 / 0) of the last n values (ring, slot = seq % n); not bool[]:
                                          // the C++ harness cannot hold a dynamic bool array
   int      m_nobs;
   double   m_qv[];                       // queue values (ring of capacity n)
   long     m_qs[];                       // queue sequence numbers
   int      m_qh;                         // queue head slot
   int      m_qc;                         // queue length

            CrRollExt() { m_max = true; m_n = 0; m_minp = 0; m_seq = 0; m_nobs = 0; m_qh = 0; m_qc = 0; }

   void Clear()
     {
      m_seq = 0;
      m_nobs = 0;
      m_qh = 0;
      m_qc = 0;
     }

   void Init(const int n, const int min_periods, const bool is_max)
     {
      m_max = is_max;
      m_n = (n > 0) ? n : 1;
      m_minp = (min_periods > 0) ? min_periods : 0;
      ArrayResize(m_ok, m_n);
      ArrayResize(m_qv, m_n);
      ArrayResize(m_qs, m_n);
      Clear();
     }

   void Push(const double x)
     {
      if(m_n <= 0) Init(1, 1, m_max);
      int slot = (int)(m_seq % m_n);
      if(m_seq >= m_n && m_ok[slot] != 0) m_nobs--;     // the value leaving the window
      while(m_qc > 0 && m_qs[m_qh] <= m_seq - m_n)
        {
         m_qh = (m_qh + 1) % m_n;
         m_qc--;
        }
      bool ok = MathIsValidNumber(x);
      m_ok[slot] = (uchar)(ok ? 1 : 0);
      if(ok)
        {
         m_nobs++;
         while(m_qc > 0)
           {
            int back = (m_qh + m_qc - 1) % m_n;
            bool drop = m_max ? (x >= m_qv[back]) : (x <= m_qv[back]);
            if(!drop) break;
            m_qc--;
           }
         int at = (m_qh + m_qc) % m_n;
         m_qv[at] = x;
         m_qs[at] = m_seq;
         m_qc++;
        }
      m_seq++;
     }

   double Value()
     {
      if(m_qc <= 0 || m_nobs < m_minp) return CrNaN();
      return m_qv[m_qh];
     }

   int Valid() { return m_nobs; }
  };

class CrRollMax
  {
public:
   CrRollExt m_e;
   void   Init(const int n) { m_e.Init(n, n, true); }
   void   InitMinPeriods(const int n, const int min_periods) { m_e.Init(n, min_periods, true); }
   void   Clear() { m_e.Clear(); }
   void   Push(const double x) { m_e.Push(x); }
   double Value() { return m_e.Value(); }               // NaN until n valid values (min_periods = n)
   int    Valid() { return m_e.Valid(); }
  };

class CrRollMin
  {
public:
   CrRollExt m_e;
   void   Init(const int n) { m_e.Init(n, n, false); }
   void   InitMinPeriods(const int n, const int min_periods) { m_e.Init(n, min_periods, false); }
   void   Clear() { m_e.Clear(); }
   void   Push(const double x) { m_e.Push(x); }
   double Value() { return m_e.Value(); }
   int    Valid() { return m_e.Valid(); }
  };

//+------------------------------------------------------------------+
//| CrRollMedian: pandas roll_median_c (a sorted copy of the valid   |
//| values of the window instead of the skiplist; same values)       |
//+------------------------------------------------------------------+
class CrRollMedian
  {
public:
   double   m_win[];                      // the last n values pushed (ring)
   int      m_n;
   int      m_minp;
   int      m_k;                          // slot of the next value
   int      m_cnt;                        // values in the window
   double   m_s[];                        // the valid values of the window, sorted
   int      m_ns;

            CrRollMedian() { m_n = 0; m_minp = 0; m_k = 0; m_cnt = 0; m_ns = 0; }

   void Clear()
     {
      m_k = 0;
      m_cnt = 0;
      m_ns = 0;
     }

   void Init(const int n, const int min_periods)
     {
      m_n = (n > 0) ? n : 1;
      m_minp = (min_periods > 0) ? min_periods : 0;
      ArrayResize(m_win, m_n);
      ArrayResize(m_s, m_n);
      Clear();
     }

   // first slot whose value is >= x (binary search in m_s[0..m_ns))
   int Lower(const double x)
     {
      int lo = 0, hi = m_ns;
      while(lo < hi)
        {
         int mid = (lo + hi) / 2;
         if(m_s[mid] < x) lo = mid + 1;
         else hi = mid;
        }
      return lo;
     }

   void Insert(const double x)
     {
      int at = Lower(x);
      for(int i = m_ns; i > at; i--) m_s[i] = m_s[i - 1];
      m_s[at] = x;
      m_ns++;
     }

   void Erase(const double x)
     {
      int at = Lower(x);
      if(at >= m_ns || m_s[at] != x) return;            // never happens: x was inserted
      for(int i = at; i < m_ns - 1; i++) m_s[i] = m_s[i + 1];
      m_ns--;
     }

   void Push(const double x)
     {
      if(m_n <= 0) Init(1, 1);
      if(m_cnt == m_n)
        {
         double old = m_win[m_k];
         if(MathIsValidNumber(old)) Erase(old);
        }
      if(MathIsValidNumber(x)) Insert(x);
      m_win[m_k] = x;
      m_k = (m_k + 1) % m_n;
      if(m_cnt < m_n) m_cnt++;
     }

   double Value()
     {
      if(m_ns < m_minp || m_ns <= 0) return CrNaN();
      int h = m_ns / 2;
      if(m_ns % 2 == 1) return m_s[h];
      return (m_s[h] + m_s[h - 1]) / 2;
     }

   int Valid() { return m_ns; }
  };

//+------------------------------------------------------------------+
//| CrWilder: pandas ewm(alpha = 1/n, adjust = False).mean()         |
//| (window/aggregations.pyx ewm, ignore_na = False, min_periods 1). |
//| alpha goes through the centre of mass as in pandas: com = (1 -   |
//| a) / a (ewm.py get_center_of_mass), then alpha = 1 / (1 + com).  |
//| Known pandas 3.0.5 oddity: for com = 1 exactly (n = 2) its       |
//| result after a NaN differs from its own formula; no rule uses    |
//| n = 2.                                                           |
//+------------------------------------------------------------------+
class CrWilder
  {
public:
   int      m_n;
   double   m_alpha;
   double   m_owf;                        // old weight factor 1 - alpha
   double   m_w;                          // the weighted value
   bool     m_has;                        // m_w holds a value (an observation was seen)
   double   m_oldw;                       // weight of the old value
   long     m_count;                      // values pushed (missing ones included)
   long     m_nobs;                       // observations

            CrWilder() { m_n = 0; m_alpha = 1.0; m_owf = 0.0; m_w = 0.0; m_has = false; m_oldw = 1.0; m_count = 0; m_nobs = 0; }

   void Clear()
     {
      m_w = 0.0;
      m_has = false;
      m_oldw = 1.0;
      m_count = 0;
      m_nobs = 0;
     }

   void Init(const int n)
     {
      m_n = (n > 0) ? n : 1;
      double a0 = 1.0 / m_n;
      double com = (1.0 - a0) / a0;
      m_alpha = 1.0 / (1.0 + com);
      m_owf = 1.0 - m_alpha;
      Clear();
     }

   double Value()
     {
      if(m_nobs < 1) return CrNaN();
      return m_w;
     }

   // returns the new value (NaN until the first observation)
   double Push(const double x)
     {
      if(m_n <= 0) Init(1);
      bool obs = MathIsValidNumber(x);
      if(obs) m_nobs++;
      if(m_count == 0)
        {
         if(obs)
           {
            m_w = x;
            m_has = true;
           }
         m_oldw = 1.0;
        }
      else if(m_has)
        {
         m_oldw *= m_owf;                                // ignore_na = False: the old weight decays across a gap
         if(obs)
           {
            if(m_w != x)
              {
               m_w = m_oldw * m_w + m_alpha * x;
               m_w /= (m_oldw + m_alpha);
              }
            m_oldw = 1.0;                                // adjust = False
           }
        }
      else if(obs)
        {
         m_w = x;
         m_has = true;
        }
      m_count++;
      return Value();
     }

   int  Count() { return (int)m_count; }                // values pushed, NaN included (the pandas row number + 1)
   long Nobs() { return m_nobs; }                       // observations
  };

//+------------------------------------------------------------------+
//| median of the finite values among v[0..n) (numpy median: the     |
//| middle value, or the mean of the two middle ones); NaN if none   |
//+------------------------------------------------------------------+
double CrMedian(const double &v[], const int n)
  {
   int k = (n < ArraySize(v)) ? n : ArraySize(v);
   if(k <= 0) return CrNaN();
   double t[];
   ArrayResize(t, k);
   int m = 0;
   for(int i = 0; i < k; i++)
      if(MathIsValidNumber(v[i]))
        {
         t[m] = v[i];
         m++;
        }
   if(m == 0) return CrNaN();
   ArrayResize(t, m);
   ArraySort(t);
   int h = m / 2;
   if(m % 2 == 1) return t[h];
   return (t[h - 1] + t[h]) / 2;
  }

//+------------------------------------------------------------------+
//| CrAgg: one bucket of kept M1 bars at a time. The caller gives    |
//| each bar its bucket key (UTC grid: CrAggKey(t, 3600); the 17:00- |
//| NY trading day: ClkServerDay(t)) and decides when a bucket is    |
//| complete (Take), e.g. when the barrier reaches its end. Fields:  |
//|   bid and ask aggregated apart (first open, max high, min low,   |
//|   last close): goldlab.data.bars, mid h = (bh + ah) / 2;         |
//|   mh, ml = max / min of the per-bar mids (bh + ah) / 2 and       |
//|   (bl + al) / 2: crypto/strategy.py h1_bars;                     |
//|   n bars, the first and last bar starts (t_close = t_last + 60). |
//+------------------------------------------------------------------+
struct CrAggBar
  {
   datetime key;                          // bucket key given by the caller
   datetime t_first, t_last;              // start of the first and of the last bar
   int      n;                            // bars
   double   bo, bh, bl, bc;               // bid: first open, max high, min low, last close
   double   ao, ah, al, ac;               // ask, the same
   double   mh, ml;                       // max of (bh + ah) / 2, min of (bl + al) / 2 over the bars
  };

datetime CrAggKey(const datetime t, const int period_s) { return t - t % period_s; }

class CrAgg
  {
public:
   CrAggBar m_cur;
   bool     m_open;

            CrAgg() { m_open = false; }

   void Clear() { m_open = false; }

   void Start(const CrBar &b, const datetime key)
     {
      m_cur.key = key;
      m_cur.t_first = b.t;
      m_cur.t_last = b.t;
      m_cur.n = 1;
      m_cur.bo = b.bo;
      m_cur.bh = b.bh;
      m_cur.bl = b.bl;
      m_cur.bc = b.bc;
      m_cur.ao = b.ao;
      m_cur.ah = b.ah;
      m_cur.al = b.al;
      m_cur.ac = b.ac;
      m_cur.mh = (b.bh + b.ah) / 2;
      m_cur.ml = (b.bl + b.al) / 2;
      m_open = true;
     }

   // adds bar b (time order) to the bucket `key`; true when b opens a new bucket while another was open:
   // `done` is then the bucket that ended
   bool Add(const CrBar &b, const datetime key, CrAggBar &done)
     {
      if(!m_open)
        {
         Start(b, key);
         return false;
        }
      if(key != m_cur.key)
        {
         done = m_cur;
         Start(b, key);
         return true;
        }
      m_cur.t_last = b.t;
      m_cur.n++;
      if(b.bh > m_cur.bh) m_cur.bh = b.bh;
      if(b.bl < m_cur.bl) m_cur.bl = b.bl;
      if(b.ah > m_cur.ah) m_cur.ah = b.ah;
      if(b.al < m_cur.al) m_cur.al = b.al;
      m_cur.bc = b.bc;
      m_cur.ac = b.ac;
      double mh = (b.bh + b.ah) / 2, ml = (b.bl + b.al) / 2;
      if(mh > m_cur.mh) m_cur.mh = mh;
      if(ml < m_cur.ml) m_cur.ml = ml;
      return false;
     }

   // closes the open bucket (the caller knows it is complete); false when none is open
   bool Take(CrAggBar &done)
     {
      if(!m_open) return false;
      done = m_cur;
      m_open = false;
      return true;
     }

   // the open bucket, without closing it
   bool Peek(CrAggBar &cur)
     {
      if(!m_open) return false;
      cur = m_cur;
      return true;
     }
  };
#endif
