//+------------------------------------------------------------------+
//| CR_Bars.mqh - bars, quotes, mask, barrier, revisions, READY and  |
//| daily cost statistics (SPEC 2.2). Owner: step B.                 |
//|                                                                  |
//| The store holds, per symbol, the KEPT closed M1 bars with the    |
//| PAPER quotes (SPEC 2.2): paper bid = NormalizeDouble(bid - h),   |
//| paper ask = NormalizeDouble(bid + spread x point + h), on all    |
//| four prices, h = g_sym[].h (gold: CR_XAU_COMM_PTS / 2 points).   |
//| Bars are read by time range only (CopyRates from, to), never by  |
//| position. Times are UTC inside; the broker's bars carry server   |
//| time (New York + 7 h).                                           |
//|                                                                  |
//| Mask (SPEC 2.2), each bar counted under its first reason:        |
//|   weekend gold and US100: Saturday or Sunday, server clock       |
//|           (prep_round2.py:53)                                    |
//|   crypto  Saturday, Sunday, or Friday from 23:55, server clock   |
//|           (build_fp_frames.py:31-33)                             |
//|   idx     US100 16:15-17:59 New York                             |
//|   xau     gold 17:00-17:59 New York                              |
//|   half    US100 13:16-17:59 New York on NYSE half days (P6;      |
//|           ClkNyse, typed HALF entries included)                  |
//| The bars left are the kept bars; masked bars still count as      |
//| broker bars for the hole scan and revisions.                     |
//| No flat-bar rule (lead decision after step B's finding 1): MT5   |
//| makes a bar only when a tick came, so it has no filler bars. The |
//| lab dropped flat bars on Dukascopy's 3-decimal bid; on the       |
//| 2-digit FP bid the same rule dropped 5,969 real in-sample bars   |
//| that the rebuilt frames keep (gold 4,905, US100 963, BTC 7,      |
//| ETH 94). Without it the kept bars equal the rebuilt frames,      |
//| except 20 gold bars of 2012-12-31 17:00-17:58 New York (xau).    |
//|                                                                  |
//| Barrier M (UTC minute; every bar starting before M is final):    |
//|   M = the current minute when every symbol has ticked in it or   |
//|   is in a known closure (ClkInClosure); else the minute that     |
//|   started at least 2 s ago (TimeTradeServer() >= M + 2 s). One   |
//|   answer per server second: the load and the replay of one pass  |
//|   agree even if a tick arrives between their two calls.          |
//| Poll (once per new barrier):                                     |
//|   - the last 3 broker bars of every symbol are read again; a     |
//|     change (a value, a bar added or gone) asks for a rebuild;    |
//|   - new bars are read from the last one to M; a minute that was  |
//|     seen ticking but whose bar is not returned makes the poll    |
//|     WAIT (retried each pass) for 30 s, then GAP (journal, push); |
//|   - a bar that shows up after its barrier passed (late) is not   |
//|     fed; it asks for a rebuild;                                  |
//|   - a rebuild is returned as CR_POLL_LATEBAR, at most one per    |
//|     5 min (a later one waits; the chain goes on meanwhile).      |
//| READY (R13), per symbol, decided at checks (BarsTimer): 2 s      |
//| after the load, then every 60 s until READY:                     |
//|   (1) SERIES_SYNCHRONIZED is true;                               |
//|   (2) depth: SERIES_FIRSTDATE <= now - depth (120 days gold, 60  |
//|       the others);                                               |
//|   (3) a second read of the load window, at least 2 s after the   |
//|       first, agrees with it (else: rebuild);                     |
//|   (4) no hole: more than 30 minutes outside the known closures   |
//|       without any broker bar, inside the current window. A hole  |
//|       gives GAP (journal, push) and is read again every 60 s:    |
//|       bars found -> rebuild; still empty after 3 re-reads with   |
//|       SERIES_SYNCHRONIZED true -> the broker's own hole (GAP     |
//|       accepted=1). An accepted hole is remembered across rebuilds |
//|       (same bounds: accepted at once, no new push).              |
//|   A symbol whose load read failed (no history yet) never blocks  |
//|   the others; its bars are taken as they come, and its history,  |
//|   if it appears later, asks for a rebuild. READY stays until the |
//|   next load. NOT_READY for 10 min: one push. BarsNotReadyFor     |
//|   tells the follower whether the first check has decided yet and |
//|   for how long the symbol has been NOT_READY since (SPEC 4.8: a  |
//|   NOT_READY exit waits for both, review F1).                     |
//| Daily cost statistics (COST, SPEC 2.6): per symbol and server    |
//| day, over the kept bars fed, the median of the raw spread and of |
//| the paper spread, in bp of the bar's opening mid.                |
//|                                                                  |
//| API (the S0 signatures; indexes are absolute since the load):    |
//|   BarsInit(err)           once at OnInit, after the symbols are  |
//|                           resolved (g_sym[].name, digits, point) |
//|   BarsReset()             forget the store                       |
//|   BarsLoad(now_srv)       read the depth of every symbol:        |
//|                           CR_LOAD_OK, or CR_LOAD_RETRY while     |
//|                           every read fails (at most 60 s)        |
//|   BarsBarrier(now_srv)    the barrier M (also notes the ticks)   |
//|   BarsPoll(M)             CR_POLL_OK / CR_POLL_WAIT /            |
//|                           CR_POLL_LATEBAR (rebuild)              |
//|   BarsNext(M, b)          next kept bar not yet fed with start   |
//|                           before M, in (time, symbol id) order   |
//|   BarsReady(sym)          READY as above                         |
//|   BarsCount(sym)          kept bars FED since the load           |
//|   BarsAt(sym, i, b)       fed bar i, 0 <= i < BarsCount (false   |
//|                           for bars dropped by the compaction:    |
//|                           the last 150,000 are always kept)      |
//|   BarsIndex(sym, t)       first fed bar starting at or after t   |
//|   BarsStart()             first kept bar of the store (UTC), 0   |
//|   BarsCost(sym, day, raw_bp, paper_bp)  daily medians (COST)     |
//|   BarsTimer(now_srv)      READY checks, GAP and NOTREADY pushes  |
//|   BarsPaperQuotes(sym, bid, ask, pbid, pask)  live paper quotes  |
//|   BarsMasked(sym, reason) masked bars since the load, by reason  |
//|   BarsNotReadyFor(sym, now_srv)  -1 before the first READY check |
//|                           since the load, 0 when READY, else the |
//|                           seconds since that first check         |
//|   BarsShut(sym, M)        minute M (UTC) is masked for the symbol|
//|                           or lies in a known closure (no order:  |
//|                           SPEC 4.1, review F2)                   |
//| Journal: READY / NOTREADY (code = symbol: bars, raw bars, first, |
//| last, masked by reason, holes, why), GAP (hole from/to, or a     |
//| live missing minute), LATEBAR (code = symbol: why and the bar),  |
//| written before the driver's own LATEBAR line.                    |
//+------------------------------------------------------------------+
#ifndef CR_BARS_MQH
#define CR_BARS_MQH
#include "CR_Types.mqh"
#include "CR_Clock.mqh"
#include "CR_Journal.mqh"
#include "CR_Math.mqh"

#define CR_BARS_GAP_S 1800             // a hole: more than 30 open minutes without a broker bar
#define CR_BARS_WAIT_S 30              // a ticked minute whose bar is not returned: retried 30 s, then GAP
#define CR_BARS_LATE_S 300             // at most one rebuild (LATEBAR) per 5 min
#define CR_BARS_RECHECK_S 60           // NOT_READY checks every 60 s
#define CR_BARS_STABLE_S 2             // the second read, at least 2 s after the load read
#define CR_BARS_ACCEPT 3               // a hole still there after 3 re-reads is the broker's own
#define CR_BARS_NOTREADY_PUSH_S 600    // NOT_READY for 10 min: one push
#define CR_BARS_KEEP 150000            // fed bars kept by the compaction
#define CR_BARS_COMPACT 300000         // compaction when this many bars were fed
#define CR_BARS_MAXHOLES 256           // holes remembered per symbol while NOT_READY (the oldest go first)
#define CR_BARS_MAXTICK 8
#define CR_BARS_MAXACC 64              // accepted holes remembered across rebuilds, per symbol

// mask reasons (BarsMasked)
#define CR_MASK_KEPT 0
#define CR_MASK_WEEKEND 1
#define CR_MASK_CRYPTO 2
#define CR_MASK_IDX 3
#define CR_MASK_XAU 4
#define CR_MASK_HALF 5
#define CR_MASK_N 6

string CR_MASK_NAME[CR_MASK_N] = {"kept", "m_weekend", "m_crypto", "m_idx", "m_xau", "m_half"};

// a broker bar as read (server time): the revision check compares them
struct CrRawBar
  {
   datetime t;
   double   o, h, l, c;
   int      s;
  };

// a hole: no broker bar in [a, b) (UTC), more than 30 minutes of it outside the known closures
struct CrHole
  {
   datetime a, b;
   int      reads;                     // re-reads that found it still empty (series synchronized)
   bool     said;                      // GAP written
   bool     accepted;                  // the broker's own hole (GAP accepted=1)
  };

datetime g_bars_M = 0;                 // the barrier of the last successful poll (or of the load), UTC
bool     g_bars_late = false;          // a rebuild was asked for
datetime g_bars_late_last = 0;         // server time of the last CR_POLL_LATEBAR (0 = none yet)
datetime g_bars_rev_M = 0;             // the barrier whose last-3 re-read was done
datetime g_bars_first_try = 0;         // first call of a load whose reads all failed (CR_LOAD_RETRY)
long     g_bars_late_n = 0;            // rebuilds asked for
datetime g_bars_bar_now = 0;           // BarsBarrier's last call (server time) and its answer: one answer per second, so
datetime g_bars_bar_M = 0;             // that the load and the replay of one pass agree even if a tick comes in between
long     g_bars_gap_live = 0;          // live missing minutes given up (GAP)
// holes accepted as the broker's own (UTC bounds), kept across rebuilds (BarsInit clears them): after a rebuild the
// same hole is accepted at once, without a new GAP push or three more re-reads
datetime g_bars_acc_a[CR_NSYM][CR_BARS_MAXACC];
datetime g_bars_acc_b[CR_NSYM][CR_BARS_MAXACC];
int      g_bars_nacc[CR_NSYM];

bool BarsAccepted(const int sym, const datetime a, const datetime b)
  {
   for(int i = 0; i < g_bars_nacc[sym]; i++)
      if(g_bars_acc_a[sym][i] == a && g_bars_acc_b[sym][i] == b) return true;
   return false;
  }

void BarsAccept(const int sym, const datetime a, const datetime b)
  {
   if(BarsAccepted(sym, a, b)) return;
   if(g_bars_nacc[sym] >= CR_BARS_MAXACC)
     {
      for(int i = 1; i < g_bars_nacc[sym]; i++)
        {
         g_bars_acc_a[sym][i - 1] = g_bars_acc_a[sym][i];
         g_bars_acc_b[sym][i - 1] = g_bars_acc_b[sym][i];
        }
      g_bars_nacc[sym]--;
     }
   g_bars_acc_a[sym][g_bars_nacc[sym]] = a;
   g_bars_acc_b[sym][g_bars_nacc[sym]] = b;
   g_bars_nacc[sym]++;
  }

//+------------------------------------------------------------------+
//| helpers (no state)                                               |
//+------------------------------------------------------------------+
// the paper quotes of a broker bar (SPEC 2.2), t = its UTC start
void BarsMakeAt(const int sym, const MqlRates &r, const datetime t, CrBar &x)
  {
   double h = g_sym[sym].h, pt = g_sym[sym].point;
   int dg = g_sym[sym].digits;
   x.t = t;
   x.sym = sym;
   x.bo = NormalizeDouble(r.open - h, dg);
   x.bh = NormalizeDouble(r.high - h, dg);
   x.bl = NormalizeDouble(r.low - h, dg);
   x.bc = NormalizeDouble(r.close - h, dg);
   x.ao = NormalizeDouble(r.open + r.spread * pt + h, dg);
   x.ah = NormalizeDouble(r.high + r.spread * pt + h, dg);
   x.al = NormalizeDouble(r.low + r.spread * pt + h, dg);
   x.ac = NormalizeDouble(r.close + r.spread * pt + h, dg);
   x.s_raw = r.spread;
  }

void BarsMake(const int sym, const MqlRates &r, CrBar &x) { BarsMakeAt(sym, r, ClkServerToUtc(r.time), x); }

// live paper quotes from a raw tick (SPEC 2.2)
void BarsPaperQuotes(const int sym, const double bid, const double ask, double &pbid, double &pask)
  {
   pbid = NormalizeDouble(bid - g_sym[sym].h, g_sym[sym].digits);
   pask = NormalizeDouble(ask + g_sym[sym].h, g_sym[sym].digits);
  }

// the mask reason of one broker bar (CR_MASK_*); it reads the bar's own server time only (no flat-bar rule)
int BarsMaskReason(const int sym, const MqlRates &r)
  {
   int fam = g_sym[sym].family;
   datetime srv = r.time;
   int dow = (int)(((srv / 86400) + 4) % 7);       // 1970-01-01 was a Thursday; 0 = Sunday
   int srv_min = (int)((srv % 86400) / 60);
   if(fam != CR_FAM_CRY && (dow == 0 || dow == 6)) return CR_MASK_WEEKEND;
   if(fam == CR_FAM_CRY && (dow == 0 || dow == 6 || (dow == 5 && srv_min >= 23 * 60 + 55))) return CR_MASK_CRYPTO;
   datetime ny = srv - 7 * 3600;                  // New York wall clock = server - 7 h (SPEC 2.1)
   int ny_min = (int)((ny % 86400) / 60);
   if(fam == CR_FAM_IDX && ny_min >= 16 * 60 + 15 && ny_min < 18 * 60) return CR_MASK_IDX;
   if(fam == CR_FAM_XAU && ny_min >= 17 * 60 && ny_min < 18 * 60) return CR_MASK_XAU;
   if(fam == CR_FAM_IDX && ny_min >= 13 * 60 + 16 && ny_min < 18 * 60 && ClkNyse(ny - ny % 86400) == CR_NYSE_HALF) return CR_MASK_HALF;
   return CR_MASK_KEPT;
  }

// seconds of [a, b) (UTC minutes) outside the family's known closures, counted up to just past limit
long BarsOpenSecs(const int family, const datetime a, const datetime b, const long limit)
  {
   long open = 0;
   datetime t = a;
   int guard = 0;
   while(t < b && open <= limit && guard < 100000)
     {
      datetime c0 = 0, c1 = 0;
      if(ClkInClosure(family, t, c0, c1) && c1 > t) t = c1;
      else
        {
         open += 60;
         t += 60;
        }
      guard++;
     }
   return open;
  }

// FNV-1a over 64-bit words (unsigned arithmetic wraps the same way in MQL5 and C++)
ulong BarsMix(const ulong h, const ulong v) { return (h ^ v) * (ulong)1099511628211; }

// a fingerprint of the broker bars of r[0..k) starting before before_srv: time, prices in points, spread
void BarsChk(const int sym, const MqlRates &r[], const int k, const datetime before_srv, ulong &h, long &cnt)
  {
   double pt = g_sym[sym].point;
   h = (ulong)1469598103934665603;
   cnt = 0;
   for(int i = 0; i < k; i++)
     {
      if(r[i].time >= before_srv) break;
      h = BarsMix(h, (ulong)r[i].time);
      h = BarsMix(h, (ulong)(long)MathRound(r[i].open / pt));
      h = BarsMix(h, (ulong)(long)MathRound(r[i].high / pt));
      h = BarsMix(h, (ulong)(long)MathRound(r[i].low / pt));
      h = BarsMix(h, (ulong)(long)MathRound(r[i].close / pt));
      h = BarsMix(h, (ulong)(long)r[i].spread);
      cnt++;
     }
  }

// ask for a rebuild (CR_POLL_LATEBAR at the next poll the 5-minute limit allows); one line per rebuild
void BarsLate(const int sym, const string why, const datetime t_utc)
  {
   if(g_bars_late) return;
   g_bars_late = true;
   g_bars_late_n++;
   long wait = 0;
   datetime now = TimeTradeServer();
   if(g_bars_late_last > 0 && (long)(now - g_bars_late_last) < CR_BARS_LATE_S) wait = CR_BARS_LATE_S - (long)(now - g_bars_late_last);
   Jrn(CR_EV_LATEBAR, JrnSymCode(sym), KV("why", why) + KT("t", t_utc) + KI("wait_s", wait));
  }

//+------------------------------------------------------------------+
//| the store of one symbol                                          |
//+------------------------------------------------------------------+
class CBarStore
  {
public:
   int      sym;
   // kept bars
   CrBar    b[];
   int      n;                         // kept bars retained in b
   long     base;                      // absolute index of b[0]
   int      fed;                       // b index of the next bar to feed
   // broker bars as read
   datetime last_srv;                  // server start of the last broker bar taken (0 = none)
   datetime first_raw;                 // server start of the first broker bar taken since the load (0 = none)
   datetime prev_end;                  // UTC end of the previous broker bar, or the window start (hole scan); 0 = none
   CrRawBar r3[3];                     // the last 3 broker bars taken
   int      n3;
   long     masked[CR_MASK_N];
   long     raw_n;
   // ticks (live GAP)
   datetime tick_srv;                  // time of the last tick seen (server)
   datetime tk[CR_BARS_MAXTICK];       // minutes seen ticking (server), after last_srv, oldest first
   int      ntk;
   datetime wait_since;                // a ticked minute's bar is awaited since (server), 0 = none
   // READY
   bool     ready;
   bool     no_data;                   // the load read failed
   bool     sync;
   bool     depth;
   bool     stable;
   bool     said;                      // a READY / NOTREADY line was written since the load
   datetime first_check;               // server time of the first READY check (decision) since the load, 0 = none yet
   string   why_said;
   bool     push10;
   datetime load_srv;                  // server time of the load
   datetime load_Msrv;                 // load barrier (server)
   datetime ws_srv;                    // load window start (server)
   ulong    chk;                       // fingerprint of the load read
   long     chk_n;
   datetime next_check;
   CrHole   holes[CR_BARS_MAXHOLES];
   int      nholes;
   long     holes_seen;
   // daily costs
   datetime cday;                      // server day of the accumulator (server midnight), 0 = none
   datetime cday_lo, cday_hi;          // its UTC bounds
   double   craw[];
   double   cpap[];
   int      cn;
   datetime lday;                      // the last finished day
   double   lraw, lpap;
   bool     lok;

            CBarStore() { sym = 0; n = 0; base = 0; fed = 0; cn = 0; }

   void Reset()
     {
      ArrayResize(b, 0, 65536);
      n = 0;
      base = 0;
      fed = 0;
      last_srv = 0;
      first_raw = 0;
      prev_end = 0;
      n3 = 0;
      for(int k = 0; k < CR_MASK_N; k++) masked[k] = 0;
      raw_n = 0;
      tick_srv = 0;
      ntk = 0;
      wait_since = 0;
      ready = false;
      no_data = false;
      sync = false;
      depth = false;
      stable = false;
      said = false;
      first_check = 0;
      why_said = "";
      push10 = false;
      load_srv = 0;
      load_Msrv = 0;
      ws_srv = 0;
      chk = 0;
      chk_n = 0;
      next_check = 0;
      nholes = 0;
      holes_seen = 0;
      cday = 0;
      cday_lo = 0;
      cday_hi = 0;
      cn = 0;
      lday = 0;
      lraw = 0.0;
      lpap = 0.0;
      lok = false;
     }

   void Add(const CrBar &x)
     {
      if(n >= ArraySize(b)) ArrayResize(b, n + 1, 65536);
      b[n] = x;
      n++;
     }

   // keep memory bounded on long runs: drop fed bars, keeping the last CR_BARS_KEEP fed ones
   void Compact()
     {
      if(fed < CR_BARS_COMPACT) return;
      int drop = fed - CR_BARS_KEEP;
      for(int i = drop; i < n; i++) b[i - drop] = b[i];
      n -= drop;
      fed -= drop;
      base += drop;
      ArrayResize(b, n, 65536);
     }

   long MaskedAll()
     {
      long s = 0;
      for(int k = 1; k < CR_MASK_N; k++) s += masked[k];
      return s;
     }

   void HoleAdd(const datetime a, const datetime bnd)
     {
      if(ready) return;                               // READY stays until the next load: later holes are the lab's too
      if((long)(bnd - a) <= CR_BARS_GAP_S) return;
      if(BarsOpenSecs(g_sym[sym].family, a, bnd, CR_BARS_GAP_S) <= CR_BARS_GAP_S) return;
      if(nholes >= CR_BARS_MAXHOLES)
        {
         for(int i = 1; i < nholes; i++) holes[i - 1] = holes[i];
         nholes--;
        }
      bool known = BarsAccepted(sym, a, bnd);          // accepted before a rebuild: the broker's own already
      holes[nholes].a = a;
      holes[nholes].b = bnd;
      holes[nholes].reads = known ? CR_BARS_ACCEPT : 0;
      holes[nholes].said = known;
      holes[nholes].accepted = known;
      nholes++;
      holes_seen++;
     }

   // one broker bar, in time order: hole scan, mask, revision copy; the kept bar is stored unless store_it is
   // false (a late bar: a rebuild was asked for)
   void Take(const MqlRates &r, const bool store_it)
     {
      datetime t = ClkServerToUtc(r.time);
      if(prev_end > 0 && t > prev_end) HoleAdd(prev_end, t);
      prev_end = t + 60;
      int why = BarsMaskReason(sym, r);
      if(n3 == 3)
        {
         r3[0] = r3[1];
         r3[1] = r3[2];
         n3 = 2;
        }
      r3[n3].t = r.time;
      r3[n3].o = r.open;
      r3[n3].h = r.high;
      r3[n3].l = r.low;
      r3[n3].c = r.close;
      r3[n3].s = r.spread;
      n3++;
      if(first_raw == 0) first_raw = r.time;
      last_srv = r.time;
      raw_n++;
      if(why != CR_MASK_KEPT)
        {
         masked[why]++;
         return;
        }
      if(!store_it) return;
      CrBar x;
      BarsMakeAt(sym, r, t, x);
      Add(x);
     }

   // a minute seen ticking (server): its bar must come
   void Ticked(const datetime m)
     {
      if(m <= last_srv) return;
      if(ntk > 0 && tk[ntk - 1] >= m) return;
      if(ntk >= CR_BARS_MAXTICK)
        {
         for(int i = 1; i < ntk; i++) tk[i - 1] = tk[i];
         ntk--;
        }
      tk[ntk] = m;
      ntk++;
     }

   // the load read of [M - depth, M); false when the read failed (no history yet)
   bool Load(const datetime Msrv, const datetime now)
     {
      load_srv = now;
      load_Msrv = Msrv;
      ws_srv = Msrv - (datetime)g_sym[sym].depth_days * 86400;
      next_check = now + CR_BARS_STABLE_S;
      if(!g_sym[sym].ok)
        {
         no_data = true;
         last_srv = Msrv - 60;
         return false;
        }
      string nm = g_sym[sym].name;
      sync = SeriesInfoInteger(nm, PERIOD_M1, SERIES_SYNCHRONIZED) != 0;
      long fd = SeriesInfoInteger(nm, PERIOD_M1, SERIES_FIRSTDATE);
      depth = (fd > 0 && fd <= (long)ws_srv);
      MqlRates r[];
      int k = CopyRates(nm, PERIOD_M1, (datetime)ws_srv, (datetime)(Msrv - 1), r);
      no_data = (k < 0);
      if(depth) prev_end = ClkServerToUtc(ws_srv);    // the window's own start counts for the hole scan
      if(k > 0)
        {
         BarsChk(sym, r, k, Msrv, chk, chk_n);
         for(int i = 0; i < k; i++)
           {
            if(r[i].time >= Msrv) break;
            Take(r[i], true);
           }
        }
      else BarsChk(sym, r, 0, Msrv, chk, chk_n);
      if(last_srv == 0) last_srv = Msrv - 60;          // polls go on from the load barrier
      return !no_data;
     }

   // the last 3 broker bars read again: false when they are the same (or the read failed)
   bool Revised(string &why)
     {
      why = "";
      if(n3 == 0 || !g_sym[sym].ok) return false;
      MqlRates r[];
      int k = CopyRates(g_sym[sym].name, PERIOD_M1, (datetime)r3[0].t, (datetime)r3[n3 - 1].t, r);
      if(k < 0) return false;
      if(k != n3)
        {
         why = "count";
         return true;
        }
      for(int i = 0; i < k; i++)
        {
         if(r[i].time != r3[i].t || r[i].open != r3[i].o || r[i].high != r3[i].h || r[i].low != r3[i].l || r[i].close != r3[i].c
            || r[i].spread != r3[i].s)
           {
            why = "value";
            return true;
           }
        }
      return false;
     }

   // new broker bars before Msrv: 0 done, 1 wait (a minute seen ticking has no bar yet)
   int Poll(const datetime Msrv, const datetime now)
     {
      if(!g_sym[sym].ok) return 0;
      MqlRates r[];
      int k = 0;
      datetime from = last_srv + 60;
      if(from <= Msrv - 1) k = CopyRates(g_sym[sym].name, PERIOD_M1, (datetime)from, (datetime)(Msrv - 1), r);
      if(k < 0) k = 0;                                 // a failed read: the ticks decide below
      datetime miss[CR_BARS_MAXTICK];
      int nmiss = 0;
      for(int j = 0; j < ntk; j++)
        {
         datetime m = tk[j];
         if(m >= Msrv || m <= last_srv) continue;
         bool found = false;
         for(int i = 0; i < k && !found; i++)
            if(r[i].time == m) found = true;
         if(!found)
           {
            miss[nmiss] = m;
            nmiss++;
           }
        }
      if(nmiss > 0)
        {
         if(wait_since == 0) wait_since = now;
         if((long)(now - wait_since) < CR_BARS_WAIT_S) return 1;
         for(int j = 0; j < nmiss; j++)
           {
            g_bars_gap_live++;
            Jrn(CR_EV_GAP, JrnSymCode(sym), KT("minute", ClkServerToUtc(miss[j])) + KI("live", 1) + KI("waited_s", (long)(now - wait_since)));
           }
         JrnPush("barre manquante " + g_sym[sym].base + " a " + ClkStr(ClkServerToUtc(miss[0])) + " UTC (" + IntegerToString(nmiss) + ")", false);
        }
      wait_since = 0;
      for(int i = 0; i < k; i++)
        {
         if(r[i].time <= last_srv) continue;
         if(r[i].time >= Msrv) break;
         datetime t = ClkServerToUtc(r[i].time);
         bool late = (t < g_bars_M);
         if(late) BarsLate(sym, "late bar", t);
         Take(r[i], !late);
        }
      int keep = 0;
      for(int j = 0; j < ntk; j++)
         if(tk[j] >= Msrv)
           {
            tk[keep] = tk[j];
            keep++;
           }
      ntk = keep;
      return 0;
     }

   // daily cost statistics of the fed kept bars (server day)
   void CostAdd(const CrBar &x)
     {
      if(cn == 0 || x.t < cday_lo || x.t >= cday_hi)
        {
         if(cn > 0)
           {
            lday = cday;
            lraw = CrMedian(craw, cn);
            lpap = CrMedian(cpap, cn);
            lok = true;
           }
         cday = ClkServerDay(x.t);
         cday_lo = ClkServerToUtc(cday);
         cday_hi = ClkServerToUtc(cday + 86400);
         cn = 0;
        }
      double mid = (x.bo + x.ao) / 2;
      if(!(mid > 0.0)) return;
      if(cn >= ArraySize(craw))
        {
         ArrayResize(craw, cn + 512);
         ArrayResize(cpap, cn + 512);
        }
      craw[cn] = x.s_raw * g_sym[sym].point / mid * 1e4;
      cpap[cn] = (x.ao - x.bo) / mid * 1e4;
      cn++;
     }

   bool Cost(const datetime day_srv, double &raw_bp, double &paper_bp)
     {
      if(cn > 0 && cday == day_srv)
        {
         raw_bp = CrMedian(craw, cn);
         paper_bp = CrMedian(cpap, cn);
         return true;
        }
      if(lok && lday == day_srv)
        {
         raw_bp = lraw;
         paper_bp = lpap;
         return true;
        }
      raw_bp = 0.0;
      paper_bp = 0.0;
      return false;
     }

   string Summary()
     {
      datetime t0 = 0, t1 = 0;
      if(n > 0)
        {
         t0 = b[0].t;
         t1 = b[n - 1].t;
        }
      string kv = KI("bars", n) + KI("raw", raw_n) + KT("first", t0) + KT("last", t1) + KI("masked", MaskedAll());
      for(int k = 1; k < CR_MASK_N; k++)
         if(masked[k] > 0) kv = kv + KI(CR_MASK_NAME[k], masked[k]);
      return kv;
     }

   // READY checks (BarsTimer): 2 s after the load, then every 60 s until READY
   void Check(const datetime now)
     {
      if(ready || !g_sym[sym].ok) return;
      if(now < next_check) return;
      next_check = now + CR_BARS_RECHECK_S;
      if(first_check == 0) first_check = now;             // the first decision since the load (READY or NOT_READY below)
      string nm = g_sym[sym].name;
      // (3) the second read of the load window agrees with the first
      if(!stable && !no_data)
        {
         MqlRates r[];
         int k = CopyRates(nm, PERIOD_M1, (datetime)ws_srv, (datetime)(load_Msrv - 1), r);
         if(k >= 0)
           {
            ulong h = 0;
            long c = 0;
            BarsChk(sym, r, k, load_Msrv, h, c);
            if(h == chk && c == chk_n) stable = true;
            else
              {
               BarsLate(sym, "load read changed", ClkServerToUtc(load_Msrv));
               chk = h;
               chk_n = c;
              }
           }
        }
      // a symbol without history at the load: its history may have come since
      if(no_data)
        {
         MqlRates r[];
         int k = CopyRates(nm, PERIOD_M1, (datetime)ws_srv, (datetime)(load_Msrv - 1), r);
         if(k > 0) BarsLate(sym, "history arrived", ClkServerToUtc(r[0].time));
         else if(k == 0)
           {
            no_data = false;
            stable = true;
           }
        }
      sync = SeriesInfoInteger(nm, PERIOD_M1, SERIES_SYNCHRONIZED) != 0;
      long fd = SeriesInfoInteger(nm, PERIOD_M1, SERIES_FIRSTDATE);
      datetime wsn = now - (datetime)g_sym[sym].depth_days * 86400;
      depth = (fd > 0 && fd <= (long)wsn);
      // (4) holes inside the current window
      datetime wsu = ClkServerToUtc(wsn);
      int open_holes = 0, new_holes = 0, keep = 0;
      for(int i = 0; i < nholes; i++)
        {
         if(holes[i].b <= wsu) continue;              // left the window: forgotten
         if(!holes[i].accepted)
           {
            if(!holes[i].said)
              {
               holes[i].said = true;
               new_holes++;
               open_holes++;
               Jrn(CR_EV_GAP, g_sym[sym].base, KT("from", holes[i].a) + KT("to", holes[i].b) + KI("min", (long)(holes[i].b - holes[i].a) / 60)
                   + KI("reads", 0) + KI("accepted", 0));
              }
            else
              {
               MqlRates r[];
               int k = CopyRates(nm, PERIOD_M1, (datetime)ClkUtcToServer(holes[i].a), (datetime)(ClkUtcToServer(holes[i].b) - 1), r);
               if(k > 0)
                 {
                  BarsLate(sym, "hole filled", holes[i].a);
                  open_holes++;
                 }
               else
                 {
                  if(k == 0 && sync) holes[i].reads++;
                  if(holes[i].reads >= CR_BARS_ACCEPT)
                    {
                     holes[i].accepted = true;
                     BarsAccept(sym, holes[i].a, holes[i].b);
                     Jrn(CR_EV_GAP, g_sym[sym].base, KT("from", holes[i].a) + KT("to", holes[i].b)
                         + KI("min", (long)(holes[i].b - holes[i].a) / 60) + KI("reads", holes[i].reads) + KI("accepted", 1));
                    }
                  else open_holes++;
                 }
              }
           }
         holes[keep] = holes[i];
         keep++;
        }
      nholes = keep;
      if(new_holes > 0)
         JrnPush("trou dans l'historique " + g_sym[sym].base + " (" + IntegerToString(new_holes) + ") : symbole pas pret", false);
      string why = "";
      if(no_data) why = why + "nodata,";
      if(!sync) why = why + "sync,";
      if(!depth) why = why + "depth,";
      if(!stable) why = why + "stable,";
      if(open_holes > 0) why = why + "holes,";
      if(why == "")
        {
         ready = true;
         Jrn(CR_EV_READY, g_sym[sym].base, Summary() + KI("holes", nholes) + KI("depth_days", g_sym[sym].depth_days));
        }
      else
        {
         why = StringSubstr(why, 0, StringLen(why) - 1);
         if(why != why_said)
           {
            Jrn(CR_EV_NOTREADY, g_sym[sym].base, KV("why", why) + Summary() + KI("holes", open_holes));
            why_said = why;
           }
         if(!push10 && (long)(now - load_srv) >= CR_BARS_NOTREADY_PUSH_S)
           {
            push10 = true;
            JrnPush(g_sym[sym].base + " pas pret depuis 10 min (" + why + ")", false);
           }
        }
      said = true;
     }
  };

CBarStore g_bs[CR_NSYM];

//+------------------------------------------------------------------+
//| the API                                                          |
//+------------------------------------------------------------------+
void BarsReset()
  {
   for(int s = 0; s < CR_NSYM; s++)
     {
      g_bs[s].sym = s;
      g_bs[s].Reset();
     }
   g_bars_M = 0;
   g_bars_late = false;
   g_bars_rev_M = 0;
   g_bars_first_try = 0;
   g_bars_bar_now = 0;
   g_bars_bar_M = 0;
  }

bool BarsInit(string &err)
  {
   err = "";
   BarsReset();
   g_bars_late_last = 0;
   g_bars_late_n = 0;
   g_bars_gap_live = 0;
   for(int s = 0; s < CR_NSYM; s++) g_bars_nacc[s] = 0;
   for(int s = 0; s < CR_NSYM; s++)
      if(g_sym[s].depth_days <= 0 || !(g_sym[s].point > 0.0))
        {
         err = "bars: symbol " + g_sym[s].base + " has no depth or no point";
         return false;
        }
   return true;
  }

// the last tick of every symbol: the barrier's tick rule and the minutes whose bar must come
void BarsTicks()
  {
   for(int s = 0; s < CR_NSYM; s++)
     {
      if(!g_sym[s].ok) continue;
      MqlTick k;
      if(!SymbolInfoTick(g_sym[s].name, k)) continue;
      if(k.time <= 0) continue;
      if(k.time > g_bs[s].tick_srv) g_bs[s].tick_srv = k.time;
      g_bs[s].Ticked(k.time - k.time % 60);
     }
  }

datetime BarsBarrier(const datetime now_srv)
  {
   if(now_srv == g_bars_bar_now && g_bars_bar_now > 0) return g_bars_bar_M;
   BarsTicks();
   datetime u = ClkServerToUtc(now_srv);
   datetime cur = u - u % 60;                     // the minute in progress
   datetime mt = (u - 2) - (u - 2) % 60;          // TimeTradeServer() >= M + 2 s
   datetime M = cur;                              // every symbol ticked in the new minute, or is closed ...
   if(mt >= cur) M = mt;
   else
     {
      datetime cur_srv = ClkUtcToServer(cur);
      for(int s = 0; s < CR_NSYM && M == cur; s++)
        {
         if(!g_sym[s].ok) continue;
         if(g_bs[s].tick_srv >= cur_srv) continue;
         datetime c0 = 0, c1 = 0;
         if(ClkInClosure(g_sym[s].family, cur, c0, c1)) continue;
         M = mt;                                  // ... else the minute that started at least 2 s ago
        }
     }
   g_bars_bar_now = now_srv;
   g_bars_bar_M = M;
   return M;
  }

int BarsLoad(const datetime now_srv)
  {
   for(int s = 0; s < CR_NSYM; s++)
     {
      g_bs[s].sym = s;
      g_bs[s].Reset();
     }
   g_bars_bar_now = 0;                            // read the ticks again for the fresh stores
   datetime M = BarsBarrier(now_srv);
   datetime Msrv = ClkUtcToServer(M);
   int ok = 0, want = 0;
   for(int s = 0; s < CR_NSYM; s++)
     {
      if(g_sym[s].ok) want++;
      if(g_bs[s].Load(Msrv, now_srv)) ok++;
     }
   if(ok == 0 && want > 0)
     {
      if(g_bars_first_try == 0) g_bars_first_try = now_srv;
      if((long)(now_srv - g_bars_first_try) < 60) return CR_LOAD_RETRY;
     }
   g_bars_first_try = 0;
   g_bars_M = M;
   g_bars_rev_M = M;
   g_bars_late = false;
   return CR_LOAD_OK;
  }

int BarsPoll(const datetime M)
  {
   datetime now = TimeTradeServer();
   if(g_bars_late && (g_bars_late_last == 0 || (long)(now - g_bars_late_last) >= CR_BARS_LATE_S))
     {
      g_bars_late_last = now;
      return CR_POLL_LATEBAR;
     }
   datetime Msrv = ClkUtcToServer(M);
   if(M > g_bars_rev_M)
     {
      g_bars_rev_M = M;
      for(int s = 0; s < CR_NSYM; s++)
        {
         string why = "";
         if(g_bs[s].Revised(why)) BarsLate(s, "revised " + why, ClkServerToUtc(g_bs[s].r3[0].t));
        }
      if(g_bars_late && (g_bars_late_last == 0 || (long)(now - g_bars_late_last) >= CR_BARS_LATE_S))
        {
         g_bars_late_last = now;
         return CR_POLL_LATEBAR;
        }
     }
   bool wait = false;
   for(int s = 0; s < CR_NSYM; s++)
      if(g_bs[s].Poll(Msrv, now) == 1) wait = true;
   if(wait) return CR_POLL_WAIT;
   g_bars_M = M;
   return CR_POLL_OK;
  }

bool BarsNext(const datetime M, CrBar &x)
  {
   int best = -1;
   datetime bt = 0;
   for(int s = 0; s < CR_NSYM; s++)
     {
      if(g_bs[s].fed >= g_bs[s].n) continue;
      datetime t = g_bs[s].b[g_bs[s].fed].t;
      if(t >= M) continue;
      if(best < 0 || t < bt)
        {
         best = s;
         bt = t;
        }
     }
   if(best < 0) return false;
   x = g_bs[best].b[g_bs[best].fed];
   g_bs[best].fed++;
   g_bs[best].CostAdd(x);
   g_bs[best].Compact();
   return true;
  }

void BarsTimer(const datetime now_srv)
  {
   for(int s = 0; s < CR_NSYM; s++) g_bs[s].Check(now_srv);
  }

bool BarsReady(const int sym)
  {
   if(sym < 0 || sym >= CR_NSYM) return false;
   return g_bs[sym].ready;
  }

int BarsCount(const int sym)
  {
   if(sym < 0 || sym >= CR_NSYM) return 0;
   return (int)(g_bs[sym].base + g_bs[sym].fed);
  }

bool BarsAt(const int sym, const int i, CrBar &x)
  {
   if(sym < 0 || sym >= CR_NSYM) return false;
   long k = (long)i - g_bs[sym].base;
   if(k < 0 || k >= g_bs[sym].fed) return false;
   x = g_bs[sym].b[(int)k];
   return true;
  }

int BarsIndex(const int sym, const datetime t_utc)
  {
   if(sym < 0 || sym >= CR_NSYM) return 0;
   int lo = 0, hi = g_bs[sym].fed;
   while(lo < hi)
     {
      int mid = (lo + hi) / 2;
      if(g_bs[sym].b[mid].t < t_utc) lo = mid + 1;
      else hi = mid;
     }
   return (int)(g_bs[sym].base + lo);
  }

datetime BarsStart()
  {
   datetime t = 0;
   for(int s = 0; s < CR_NSYM; s++)
      if(g_bs[s].n > 0 && (t == 0 || g_bs[s].b[0].t < t)) t = g_bs[s].b[0].t;
   return t;
  }

bool BarsCost(const int sym, const datetime day_srv, double &raw_bp, double &paper_bp)
  {
   if(sym < 0 || sym >= CR_NSYM)
     {
      raw_bp = 0.0;
      paper_bp = 0.0;
      return false;
     }
   return g_bs[sym].Cost(day_srv, raw_bp, paper_bp);
  }

// -1: no READY check has decided since the load; 0: READY; else the seconds the symbol has been NOT_READY since its first
// check (SPEC 4.8: positions of NOT_READY sleeves close at LatestExit only after that first decision and a wait)
long BarsNotReadyFor(const int sym, const datetime now_srv)
  {
   if(sym < 0 || sym >= CR_NSYM) return -1;
   if(g_bs[sym].ready) return 0;
   if(g_bs[sym].first_check == 0) return -1;
   return (long)(now_srv - g_bs[sym].first_check);
  }

// minute M (UTC) is masked for the symbol (SPEC 2.2: the bar of M would not be kept) or lies in a known closure of its
// family (SPEC 2.1): no order is sent in it (SPEC 4.1, review F2)
bool BarsShut(const int sym, const datetime M)
  {
   if(sym < 0 || sym >= CR_NSYM) return true;
   MqlRates r;
   ZeroMemory(r);
   r.time = ClkUtcToServer(M - M % 60);
   if(BarsMaskReason(sym, r) != CR_MASK_KEPT) return true;
   datetime c0 = 0, c1 = 0;
   return ClkInClosure(g_sym[sym].family, M - M % 60, c0, c1);
  }

long BarsMasked(const int sym, const int reason)
  {
   if(sym < 0 || sym >= CR_NSYM || reason < 0 || reason >= CR_MASK_N) return 0;
   if(reason == CR_MASK_KEPT) return g_bs[sym].raw_n - g_bs[sym].MaskedAll();
   return g_bs[sym].masked[reason];
  }
#endif
