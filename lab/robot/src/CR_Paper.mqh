//+------------------------------------------------------------------+
//| CR_Paper.mqh - the paper engine (SPEC 2.5). Owner: C.             |
//|                                                                  |
//| A streaming port of goldlab/sim.py _run (:69-211): one chain per |
//| sleeve, one position at a time, fed with the kept closed M1 bars |
//| of the sleeve's traded symbol (paper quotes, CrBar) in time      |
//| order. It alone decides entries, the one-position rule and exits.|
//|                                                                  |
//| API (signatures fixed by S0):                                    |
//|   PapInit()        once at OnInit       PapReset()  every rebuild |
//|   PapSubmit(o)     a rule's order; false = refused (ERROR)       |
//|   PapSubmitExit(e) a rule's exit (CrExit); false = no room       |
//|   PapOnBar(sl, b)  one kept closed bar of the sleeve's symbol,   |
//|                    after the rules' OnBar for that bar           |
//|   PapOnBarrier(M)  every minute M, after OnMinute(M): windows    |
//|                    that end, hold extension, late gap revision   |
//|   PapEvents() PapEvent(k, e) PapClearEvents()   the event queue  |
//|   PapTrade(sl, t)  the open trade (a pending gap exit counts as  |
//|                    open); false when flat                        |
//|   PapPending(sl,o) the oldest order still waiting; false if none |
//|   PapLastExitBar(sl)  start of the last trade's exit bar (0)     |
//| The driver (CR_Main) feeds, for every whole UTC minute M: every  |
//| kept bar starting before M (PapOnBar after the rules' OnBar),    |
//| then OnMinute(M), then PapOnBarrier(M). So at PapOnBarrier(M)    |
//| every bar starting before M is final, and no bar starting at or  |
//| after M has been seen. PapOnBar(sl, b) first runs the sleeve's   |
//| part of the barrier at b's start (a no-op when the driver called |
//| PapOnBarrier for every minute), so a skipped barrier never lets  |
//| a bar answer a question it cannot answer.                        |
//|                                                                  |
//| How the paper reads a CrOrder ("0 = none" for every optional     |
//| field; a NaN counts as none too):                                |
//|   activation  the first kept bar b with t_from <= b.t <= t_to    |
//|               fed after PapSubmit (an order emitted from OnBar(b)|
//|               may activate on b itself). With after_exit_of = X: |
//|               the first such bar AFTER the bar where the CrExit  |
//|               of oid X resolved; void when that CrExit is void.  |
//|   skip        at activation, when the sleeve's trade is open or  |
//|               exited on b (sim.py:80): the order is gone.        |
//|   etype       0 market: fill at b's open. 1 stop, 2 limit: fill  |
//|               on bars starting before expiry_excl (sim.py:87-111)|
//|               3 OCO: buy stop at level, sell stop at level2; both|
//|               touched in one bar -> the side against the bar's   |
//|               move, bc >= bo -> short (trend/strategy.py:303-317)|
//|               then a stop entry of that side.                    |
//|   stop        absolute when set, else fill -/+ stop_dist; a stop |
//|               on the wrong side exits on the fill bar ('gap').   |
//|   target      absolute when set, else fill +/- target_dist.      |
//|   trail, be   sim.py:164-173 (from the bar's close, next bar on).|
//|   x_sched     time exit at the open of the exit bar, never on    |
//|               the fill bar (sim.py:137). x_gap false: the first  |
//|               kept bar starting at or after x. x_gap true        |
//|               (gl.exit_index): the first kept bar starting in    |
//|               [x, x + 30 min]; if none, the last kept bar before |
//|               x, unless that is the fill bar: then the first kept|
//|               bar after x.                                       |
//|   xh, xh_r    hold extension (H2, variants.py:206-233): at the   |
//|               first barrier at or after x, an open trade whose   |
//|               last processed bar c is at or after its fill bar   |
//|               and side x (mark - fill) >= xh_r x |fill - stop0|, |
//|               mark = c's bid close (long) or ask close (short),  |
//|               gets x := max(xh, x) with the same gap flag (HOLD).|
//|   refuse      at the fill, spread = ao - bo of the fill bar:     |
//|               1 (payoff): d0 < 3 x spread, d0 = |fill - stop| for|
//|               an absolute stop, else stop_dist (vhi_sleeves      |
//|               stop_distance_at_fill, variants.refuse);           |
//|               2 (synthesis_B): |fill - stop0| < 3 x spread or a  |
//|               stop on the wrong side (common.py:136-169). A      |
//|               refused order leaves no trace (PREFUSE): the sleeve|
//|               stays flat and nothing counts as exited on b.      |
//|   void_le     brk72's wrapper (recalc.py:43-53, exit_i > entry_i)|
//|               the order never existed when its exit bar (x with  |
//|               the gap rule) does not follow its ACTIVATION bar   |
//|               (entry_i): x at or before that bar (PVOID at       |
//|               activation), or no kept bar from just after it to  |
//|               x + 30 min (PVOID at that barrier, armed or filled)|
//| A CrExit of oid X: at the first kept bar e inside its window it  |
//| replaces X's time exit by "the first kept bar at or after e, not |
//| the fill bar, no gap rule, no hold" (noise30 sets exit_i = e,    |
//| reason 'time'); it is void when its window ends without a bar.   |
//|                                                                  |
//| Late gap revision (SPEC 2.5, P4). While the 30-minute question of|
//| a gap-rule exit x is open (no kept bar seen at or after x yet),  |
//| the trade keeps its last two processed bars and the stop before  |
//| the last one. When the barrier passes x + 30 min with no kept bar|
//| in [x, x + 30 min], the last processed bar L is the last kept bar|
//| before x: the paper books the time exit at L's open (PREVISE,    |
//| replacing a stop, target, trail or gap exit booked on L); if L is|
//| the fill bar the exit waits for the next kept bar; void_le with  |
//| L = the activation bar -> PVOID. The hold test of the barrier at |
//| x was made on L; the revision makes it again on the bar before L |
//| (the lab's c = exit bar - 1): HOLD to grant it, HOLD with px = 0 |
//| and x = x_sched to withdraw it. A hold granted there moves the   |
//| exit past the hole: L then stands as a bar of the trade, and the |
//| extended exit gets its own 30-minute question.                   |
//|                                                                  |
//| Orders waiting together. Two market orders of one sleeve may wait|
//| at once (each resolves at its own activation bar, in emission    |
//| order), unless one has void_le: a void_le trade can be voided    |
//| after its activation bar, and an order skipped on that bar would |
//| have been taken by the lab. Every other overlap of spans with a  |
//| waiting order is refused (PapSubmit false -> ERROR): the lab     |
//| decides such a pair with future bars. Span = [t_from, t_to] for a|
//| market order, [t_from (or its activation bar), max(t_to,         |
//| expiry_excl - 1)] otherwise. None of this occurs in the ten rules|
//| (SPEC 2.5).                                                      |
//|                                                                  |
//| Events (CrPEvent; t is the lab stamp, bar the bar that made it): |
//|   PFILL   t = bar = fill bar; px fill; stop = st0 = initial stop;|
//|           x = x_sched                                            |
//|   PEXIT   t = exit bar + 60 s ('time': the bar start); px exit;  |
//|           reason stop, target, time, trail or gap                |
//|   PSTOP   t = bar + 60 s; stop = the new stop (trail or be)      |
//|   PREVISE t = bar = L; px = the time exit at L's open; reason    |
//|           time; stop = the stop before L                         |
//|   PVOID   t = bar = the activation bar; reason void (px = fill   |
//|           when a trade existed, else 0)                          |
//|   PREFUSE t = bar = the fill bar; px the fill it would have had; |
//|           reason refused                                         |
//|   HOLD    t = the barrier; bar = c; px = the mark (0 when the    |
//|           hold is withdrawn); x = the time exit now in effect    |
//| No swap, no end-of-data exit (a trade open at the end stays open)|
//+------------------------------------------------------------------+
#ifndef CR_PAPER_MQH
#define CR_PAPER_MQH
#include "CR_Types.mqh"

#define CR_PAP_QMAX 8                  // orders a sleeve may hold at once (waiting for activation or for a fill)
#define CR_PAP_XMAX 8                  // rule exits a sleeve may hold at once
#define CR_PAP_QALL 128                // CR_MAX_SL x CR_PAP_QMAX
#define CR_PAP_XALL 128                // CR_MAX_SL x CR_PAP_XMAX
#define CR_PAP_GAP 1800                // gl.exit_index: a bar more than 30 min after x does not take the exit

// queued order states (0 = dead, dropped at the next compaction)
#define CR_PO_WAIT 1                   // waiting for its activation bar
#define CR_PO_ARMED 2                  // stop, limit or OCO activated, waiting for its fill
// rule exit states
#define CR_PX_WAIT 1                   // waiting for a kept bar inside its window
#define CR_PX_DONE 2                   // resolved on the bar .bar
#define CR_PX_VOID 3                   // its window ended without a kept bar
// trade states
#define CR_PT_NONE 0                   // no trade
#define CR_PT_OPEN 1                   // open (a pending gap exit included)
#define CR_PT_EXITED 2                 // exit booked on its last processed bar; a late gap revision may still replace it
// hold extension states
#define CR_PH_NONE 0                   // no hold to test
#define CR_PH_DUE 1                    // to test at the first barrier at or after x0
#define CR_PH_TENT 2                   // tested at that barrier; the gap revision of x0 tests it again
#define CR_PH_DONE 3                   // decided for good

struct CrPapOrd                        // an order of a sleeve's queue
  {
   CrOrder  o;
   int      st;                        // CR_PO_*
   datetime act;                       // activation bar start (armed)
  };

struct CrPapExit                       // a rule exit of a sleeve's list
  {
   CrExit   e;
   int      st;                        // CR_PX_*
   datetime bar;                       // start of the bar where it resolved
  };

struct CrPapTrade                      // the sleeve's trade
  {
   int      st;                        // CR_PT_*
   CrOrder  o;                         // the order it came from
   int      side;                      // +1 / -1 (OCO: the side that filled)
   int      et;                        // entry type for the fill-bar target rule (OCO: stop)
   double   lv;                        // the entry level of that rule
   datetime act, fill;                 // activation and fill bar starts
   double   fp, st0;                   // fill price, initial stop
   bool     tg_on;                     // a target exists
   double   tg;                        // the target
   double   cur, best;                 // current stop, best price since the fill (sim.py 'cur', 'best')
   bool     moved;                     // trail or break-even moved the stop
   CrBar    b_last;                    // the last processed bar of the trade
   CrBar    b_prev;                    // the one before (t = 0: none, the last bar is the fill bar)
   double   cur_prev;                  // the stop before b_last was processed
   datetime x;                         // the time exit in effect (0 = none)
   datetime x0;                        // the order's own x_sched (the hold applies to it)
   bool     xg;                        // the gap rule applies to x
   datetime q;                         // the time whose 30-minute question is open
   bool     q_open;                    // no kept bar seen at or after q yet
   bool     q_x0;                      // that question is x0's (void_le and the hold re-test belong to it)
   int      hold;                      // CR_PH_*
   bool     held;                      // the hold test passed: x = max(xh, x0)
   int      reason;                    // exit reason (CR_R_*), CR_R_NONE while open
   datetime xbar;                      // exit bar start
   double   xpx;                       // exit price
  };

CrPapOrd   g_pap_q[CR_PAP_QALL];       // sleeve sl's queue: g_pap_q[sl * CR_PAP_QMAX + k], k < g_pap_qn[sl], emission order
int        g_pap_qn[CR_MAX_SL];
CrPapExit  g_pap_x[CR_PAP_XALL];       // sleeve sl's rule exits: g_pap_x[sl * CR_PAP_XMAX + k], k < g_pap_xn[sl]
int        g_pap_xn[CR_MAX_SL];
CrPapTrade g_pap_t[CR_MAX_SL];
datetime   g_pap_lx[CR_MAX_SL];        // start of the exit bar of the sleeve's last trade (0 = none)
datetime   g_pap_lx0[CR_MAX_SL];       // its value before the current trade's fill (PVOID puts it back)
datetime   g_pap_last[CR_MAX_SL];      // start of the last bar fed to the sleeve
datetime   g_pap_M = 0;                // the last barrier
CrPEvent   g_pap_ev[];
int        g_pap_evn = 0;
long       g_pap_err = 0;              // orders or exits refused by PapSubmit / PapSubmitExit, events lost

// a sleeve index the paper can hold (the fixed tables have CR_PAP_QALL / CR_PAP_QMAX rows)
bool PapSleeveOk(const int sl)
  {
   return sl >= 0 && sl < g_nsl && sl < CR_MAX_SL && sl < CR_PAP_QALL / CR_PAP_QMAX && sl < CR_PAP_XALL / CR_PAP_XMAX;
  }

//+------------------------------------------------------------------+
//| Small helpers                                                    |
//+------------------------------------------------------------------+
// an optional field is set: finite and not 0
bool PapOn(const double v) { return MathIsValidNumber(v) && v != 0.0; }

// the first barrier (whole UTC minute) after t, and at or after t
datetime PapMinAfter(const datetime t) { return t - t % 60 + 60; }
datetime PapMinFrom(const datetime t)
  {
   datetime m = t - t % 60;
   if(m < t) m += 60;
   return m;
  }

double PapSlipM(const int sl) { return g_sym[g_sl[sl].sym].slip_mkt; }
double PapSlipS(const int sl) { return g_sym[g_sl[sl].sym].slip_stop; }

void PapEmit(const int ev, const int sl, const long oid, const int side, const datetime t, const datetime bar, const double px,
             const double stop, const double st0, const int reason, const datetime x, const int s_raw, const double s_paper)
  {
   if(g_pap_evn >= ArraySize(g_pap_ev))
     {
      if(ArrayResize(g_pap_ev, g_pap_evn + 64, 256) < g_pap_evn + 1)
        {
         g_pap_err++;                                          // no memory: the event is lost (counted)
         return;
        }
     }
   g_pap_ev[g_pap_evn].ev = ev;
   g_pap_ev[g_pap_evn].sleeve = sl;
   g_pap_ev[g_pap_evn].oid = oid;
   g_pap_ev[g_pap_evn].side = side;
   g_pap_ev[g_pap_evn].t = t;
   g_pap_ev[g_pap_evn].bar = bar;
   g_pap_ev[g_pap_evn].px = px;
   g_pap_ev[g_pap_evn].stop = stop;
   g_pap_ev[g_pap_evn].init_stop = st0;
   g_pap_ev[g_pap_evn].reason = reason;
   g_pap_ev[g_pap_evn].x = x;
   g_pap_ev[g_pap_evn].s_raw = s_raw;
   g_pap_ev[g_pap_evn].s_paper = s_paper;
   g_pap_evn++;
  }

// an event of the trade on bar b
void PapEmitTr(const int ev, const int sl, const CrPapTrade &tr, const datetime t, const CrBar &b, const double px, const int reason)
  {
   PapEmit(ev, sl, tr.o.oid, tr.side, t, b.t, px, tr.cur, tr.st0, reason, tr.x, b.s_raw, b.ao - b.bo);
  }

// the last second at which a bar this order may still act on can start
datetime PapSpanEnd(const CrOrder &o)
  {
   if(o.etype == CR_ET_MARKET) return o.t_to;
   datetime e = o.expiry_excl - 1;
   if(e > o.t_to) return e;
   return o.t_to;
  }

// could the queued order a and the new order b need the same bar in a way only future bars decide?
bool PapOverlap(const CrPapOrd &a, const CrOrder &b)
  {
   if(a.o.etype == CR_ET_MARKET && b.etype == CR_ET_MARKET && !a.o.void_le && !b.void_le) return false;
   datetime a0 = a.o.t_from;
   if(a.st == CR_PO_ARMED) a0 = a.act;
   return a0 <= PapSpanEnd(b) && b.t_from <= PapSpanEnd(a.o);
  }

// index (in g_pap_x) of the latest rule exit of oid for sleeve sl, -1 when none
int PapExitFind(const int sl, const long oid)
  {
   for(int k = g_pap_xn[sl] - 1; k >= 0; k--)
      if(g_pap_x[sl * CR_PAP_XMAX + k].e.oid == oid) return sl * CR_PAP_XMAX + k;
   return -1;
  }

// drop the resolved or void rule exits that no waiting order refers to
void PapExitsCompact(const int sl)
  {
   int base = sl * CR_PAP_XMAX;
   int n = g_pap_xn[sl];
   int w = 0;
   for(int k = 0; k < n; k++)
     {
      bool keep = (g_pap_x[base + k].st == CR_PX_WAIT);
      if(!keep)
         for(int j = 0; j < g_pap_qn[sl]; j++)
            if(g_pap_q[sl * CR_PAP_QMAX + j].st == CR_PO_WAIT && g_pap_q[sl * CR_PAP_QMAX + j].o.after_exit_of == g_pap_x[base + k].e.oid)
              {
               keep = true;
               break;
              }
      if(keep)
        {
         if(w != k) g_pap_x[base + w] = g_pap_x[base + k];
         w++;
        }
     }
   g_pap_xn[sl] = w;
  }

// drop the orders marked dead (st 0), keeping the emission order
void PapOrdersCompact(const int sl)
  {
   int base = sl * CR_PAP_QMAX;
   int n = g_pap_qn[sl];
   int w = 0;
   for(int k = 0; k < n; k++)
     {
      if(g_pap_q[base + k].st == 0) continue;
      if(w != k) g_pap_q[base + w] = g_pap_q[base + k];
      w++;
     }
   g_pap_qn[sl] = w;
  }

//+------------------------------------------------------------------+
//| Exits of a trade                                                 |
//+------------------------------------------------------------------+
// book an exit of the open trade on bar b (PEXIT); a stop, target, trail or gap exit stays open to a late gap revision
// while the 30-minute question of its time exit is open
void PapBookExit(const int sl, CrPapTrade &tr, const CrBar &b, const double px, const int reason)
  {
   tr.reason = reason;
   tr.xbar = b.t;
   tr.xpx = px;
   g_pap_lx[sl] = b.t;
   datetime t = b.t + 60;
   if(reason == CR_R_TIME) t = b.t;                           // sim.py:284: + 1 minute unless 'time'
   PapEmitTr(CR_EV_PEXIT, sl, tr, t, b, px, reason);
   if(reason != CR_R_TIME && tr.q_open) tr.st = CR_PT_EXITED;
   else tr.st = CR_PT_NONE;
  }

// sim.py:136-204 on one bar of the open trade; first = the fill bar (no time exit there, sim.py:137 'i > fi')
void PapManage(const int sl, CrPapTrade &tr, const CrBar &b, const bool first)
  {
   if(!first)
     {
      tr.b_prev = tr.b_last;
      tr.cur_prev = tr.cur;
      tr.b_last = b;
      if(tr.x > 0 && b.t >= tr.x)
        {
         double sm = PapSlipM(sl);
         double pxt = (tr.side > 0) ? b.bo * (1 - sm) : b.ao * (1 + sm);
         PapBookExit(sl, tr, b, pxt, CR_R_TIME);
         return;
        }
     }
   double ss = PapSlipS(sl);
   double cur0 = tr.cur;
   if(tr.side > 0)
     {
      bool hit_stop = (b.bl <= tr.cur);
      bool hit_tgt = tr.tg_on && (b.bh >= tr.tg);
      if(first && tr.et == CR_ET_STOP && hit_tgt && !(b.ao < tr.lv)) hit_tgt = false;
      if(first && tr.et == CR_ET_LIMIT) hit_tgt = false;
      if(hit_stop)
        {
         double px = first ? tr.cur : MathMin(tr.cur, b.bo);
         PapBookExit(sl, tr, b, px * (1 - ss), tr.moved ? CR_R_TRAIL : CR_R_STOP);
         return;
        }
      if(hit_tgt)
        {
         PapBookExit(sl, tr, b, first ? tr.tg : MathMax(tr.tg, b.bo), CR_R_TARGET);
         return;
        }
      if(b.bh > tr.best) tr.best = b.bh;
      if(PapOn(tr.o.trail) && tr.best - tr.o.trail > tr.cur)
        {
         tr.cur = tr.best - tr.o.trail;
         tr.moved = true;
        }
      if(PapOn(tr.o.be) && tr.best - tr.fp >= tr.o.be && tr.fp > tr.cur)
        {
         tr.cur = tr.fp;
         tr.moved = true;
        }
     }
   else
     {
      bool hit_stop = (b.ah >= tr.cur);
      bool hit_tgt = tr.tg_on && (b.al <= tr.tg);
      if(first && tr.et == CR_ET_STOP && hit_tgt && !(b.bo > tr.lv)) hit_tgt = false;
      if(first && tr.et == CR_ET_LIMIT) hit_tgt = false;
      if(hit_stop)
        {
         double px = first ? tr.cur : MathMax(tr.cur, b.ao);
         PapBookExit(sl, tr, b, px * (1 + ss), tr.moved ? CR_R_TRAIL : CR_R_STOP);
         return;
        }
      if(hit_tgt)
        {
         PapBookExit(sl, tr, b, first ? tr.tg : MathMin(tr.tg, b.ao), CR_R_TARGET);
         return;
        }
      if(b.al < tr.best) tr.best = b.al;
      if(PapOn(tr.o.trail) && tr.best + tr.o.trail < tr.cur)
        {
         tr.cur = tr.best + tr.o.trail;
         tr.moved = true;
        }
      if(PapOn(tr.o.be) && tr.fp - tr.best >= tr.o.be && tr.fp < tr.cur)
        {
         tr.cur = tr.fp;
         tr.moved = true;
        }
     }
   if(tr.cur != cur0) PapEmitTr(CR_EV_PSTOP, sl, tr, b.t + 60, b, tr.cur, CR_R_NONE);
  }

//+------------------------------------------------------------------+
//| Fills                                                            |
//+------------------------------------------------------------------+
// does order o fill on bar b? side, fill price, entry type and level of the fill-bar target rule (sim.py:87-111;
// OCO: trend/strategy.py:303-317, then a stop entry of the side touched)
bool PapTryFill(const int sl, const CrOrder &o, const CrBar &b, int &side, double &fp, int &et, double &lv)
  {
   side = o.side;
   et = o.etype;
   lv = o.level;
   fp = 0.0;
   if(o.etype == CR_ET_MARKET)
     {
      double sm = PapSlipM(sl);
      fp = (side > 0) ? b.ao * (1 + sm) : b.bo * (1 - sm);
      return true;
     }
   double ss = PapSlipS(sl);
   if(o.etype == CR_ET_STOP)
     {
      if(side > 0 && b.ah >= lv)
        {
         fp = MathMax(lv, b.ao) * (1 + ss);
         return true;
        }
      if(side < 0 && b.bl <= lv)
        {
         fp = MathMin(lv, b.bo) * (1 - ss);
         return true;
        }
      return false;
     }
   if(o.etype == CR_ET_LIMIT)
     {
      if(side > 0 && b.al <= lv)
        {
         fp = MathMin(lv, b.ao);
         return true;
        }
      if(side < 0 && b.bh >= lv)
        {
         fp = MathMax(lv, b.bo);
         return true;
        }
      return false;
     }
   if(o.etype == CR_ET_OCO)
     {
      bool hu = (b.ah >= o.level);
      bool hd = (b.bl <= o.level2);
      if(!hu && !hd) return false;
      if(hu && hd) side = (b.bc >= b.bo) ? -1 : 1;
      else side = hu ? 1 : -1;
      et = CR_ET_STOP;
      if(side > 0)
        {
         lv = o.level;
         fp = MathMax(lv, b.ao) * (1 + ss);
        }
      else
        {
         lv = o.level2;
         fp = MathMin(lv, b.bo) * (1 - ss);
        }
      return true;
     }
   return false;
  }

// the fill of order o on bar b: refusal, the new trade, its gap exit or the management of the fill bar
void PapOpen(const int sl, CrPapTrade &tr, const CrOrder &o, const datetime act, const CrBar &b, const int side, const double fp,
             const int et, const double lv)
  {
   double st = PapOn(o.stop) ? o.stop : fp - side * o.stop_dist;          // sim.py:117
   bool wrong = (side > 0 && st >= fp) || (side < 0 && st <= fp);         // sim.py:122
   double spread = b.ao - b.bo;
   bool refused = false;
   if(o.refuse == CR_REF_PAYOFF)
     {
      double d0 = PapOn(o.stop) ? MathAbs(fp - o.stop) : o.stop_dist;
      refused = (d0 < 3.0 * spread);
     }
   else if(o.refuse == CR_REF_SB)
      refused = (MathAbs(fp - st) < 3.0 * spread) || wrong;
   if(refused)
     {
      PapEmit(CR_EV_PREFUSE, sl, o.oid, side, b.t, b.t, fp, st, st, CR_R_REFUSED, o.x_sched, b.s_raw, spread);
      return;
     }
   g_pap_lx0[sl] = g_pap_lx[sl];
   tr.st = CR_PT_OPEN;
   tr.o = o;
   tr.side = side;
   tr.et = et;
   tr.lv = lv;
   tr.act = act;
   tr.fill = b.t;
   tr.fp = fp;
   tr.st0 = st;
   tr.tg_on = PapOn(o.target) || PapOn(o.target_dist);                    // sim.py:118-119
   tr.tg = 0.0;
   if(PapOn(o.target)) tr.tg = o.target;
   else if(PapOn(o.target_dist)) tr.tg = fp + side * o.target_dist;
   tr.cur = st;
   tr.best = fp;
   tr.moved = false;
   tr.b_last = b;
   ZeroMemory(tr.b_prev);
   tr.cur_prev = st;
   tr.x = o.x_sched;
   tr.x0 = o.x_sched;
   tr.xg = o.x_gap;
   tr.q = o.x_sched;
   tr.q_open = o.x_gap && o.x_sched > b.t;                                // x at or before the fill bar: exit at the next bar
   tr.q_x0 = tr.q_open;
   tr.hold = CR_PH_NONE;
   if(o.xh > 0 && o.x_sched > b.t) tr.hold = CR_PH_DUE;                   // x at or before the fill bar: never at the clock
   tr.held = false;
   tr.reason = CR_R_NONE;
   tr.xbar = 0;
   tr.xpx = 0.0;
   PapEmit(CR_EV_PFILL, sl, o.oid, side, b.t, b.t, fp, st, st, CR_R_NONE, o.x_sched, b.s_raw, spread);
   if(wrong)
     {
      double ss = PapSlipS(sl);
      double px = (side > 0) ? b.bo * (1 - ss) : b.ao * (1 + ss);
      PapBookExit(sl, tr, b, px, CR_R_GAP);
      return;
     }
   PapManage(sl, tr, b, true);
  }

//+------------------------------------------------------------------+
//| Hold extension and late gap revision                             |
//+------------------------------------------------------------------+
// variants.hold_decision: ahead by at least xh_r x the initial risk at the close of bar c, c at or after the fill bar
bool PapHoldPass(const CrPapTrade &tr, const CrBar &c)
  {
   if(c.t == 0 || c.t < tr.fill) return false;
   double mark = (tr.side > 0) ? c.bc : c.ac;
   return tr.side * (mark - tr.fp) >= tr.o.xh_r * MathAbs(tr.fp - tr.st0);
  }

void PapEmitHold(const int sl, const CrPapTrade &tr, const datetime M, const CrBar &c, const bool grant)
  {
   double mark = 0.0;
   if(grant) mark = (tr.side > 0) ? c.bc : c.ac;
   PapEmit(CR_EV_HOLD, sl, tr.o.oid, tr.side, M, c.t, mark, tr.cur, tr.st0, CR_R_NONE, tr.x, c.s_raw, c.ao - c.bo);
  }

// the test passed (variants.H: exit_i = max(ext, exit_i))
void PapHoldGrant(const int sl, CrPapTrade &tr, const datetime M, const CrBar &c)
  {
   tr.held = true;
   tr.x = tr.x0;
   if(tr.o.xh > tr.x0) tr.x = tr.o.xh;
   PapEmitHold(sl, tr, M, c, true);
  }

// the first barrier at or after x0, the trade open: the test on its last processed bar, which is the last kept bar
// before x0 (final unless the gap rule moves x0's exit bar back to that bar: then the revision tests again)
void PapHoldAtBarrier(const int sl, CrPapTrade &tr, const datetime M)
  {
   tr.hold = CR_PH_DONE;
   if(tr.q_open && tr.q_x0) tr.hold = CR_PH_TENT;
   if(PapHoldPass(tr, tr.b_last)) PapHoldGrant(sl, tr, M, tr.b_last);
  }

// the barrier passed q + 30 min and no kept bar started at or after q: the trade's last processed bar L is the last
// kept bar before q, and gl.exit_index puts the exit there
void PapRevise(const int sl, CrPapTrade &tr, const datetime M)
  {
   bool x0q = tr.q_x0;
   tr.q_open = false;
   tr.q_x0 = false;
   bool lfill = (tr.b_last.t == tr.fill);
   if(x0q && tr.o.void_le && tr.b_last.t == tr.act)
     {
      PapEmitTr(CR_EV_PVOID, sl, tr, tr.act, tr.b_last, tr.fp, CR_R_VOID);   // the wrapper drops the order: no trade at all
      g_pap_lx[sl] = g_pap_lx0[sl];
      tr.st = CR_PT_NONE;
      return;
     }
   if(x0q && (tr.hold == CR_PH_DUE || tr.hold == CR_PH_TENT))
     {
      tr.hold = CR_PH_DONE;
      if(!lfill && PapHoldPass(tr, tr.b_prev))                // the lab's c = (exit bar L) - 1 = the bar before L
        {
         if(!tr.held) PapHoldGrant(sl, tr, M, tr.b_prev);
         if(tr.x > tr.x0)                                      // the exit moved past the hole: L stays a bar of the trade
           {
            if(tr.xg)
              {
               tr.q = tr.x;                                    // the extended exit has its own question (x > x0 > L)
               tr.q_open = true;
              }
            return;
           }
        }
      else if(tr.held)
        {
         tr.held = false;                                      // withdrawn: the exit bar is L (or the bar after the fill)
         tr.x = tr.x0;
         PapEmitHold(sl, tr, M, tr.b_last, false);
        }
     }
   if(lfill)
     {
      if(tr.st == CR_PT_EXITED) tr.st = CR_PT_NONE;             // its exit on the fill bar stands
      return;                                                  // an open trade exits at the next kept bar (sim.py:137)
     }
   double sm = PapSlipM(sl);
   double px = (tr.side > 0) ? tr.b_last.bo * (1 - sm) : tr.b_last.ao * (1 + sm);
   tr.cur = tr.cur_prev;
   tr.reason = CR_R_TIME;
   tr.xbar = tr.b_last.t;
   tr.xpx = px;
   g_pap_lx[sl] = tr.b_last.t;
   PapEmitTr(CR_EV_PREVISE, sl, tr, tr.b_last.t, tr.b_last, px, CR_R_TIME);
   tr.st = CR_PT_NONE;
  }

// a new kept bar b for the sleeve: an exit booked on the previous bar stands, and an open question is answered
void PapTradeNewBar(CrPapTrade &tr, const CrBar &b)
  {
   if(tr.st == CR_PT_EXITED)
     {
      tr.st = CR_PT_NONE;
      return;
     }
   if(tr.st != CR_PT_OPEN || !tr.q_open || b.t < tr.q) return;
   tr.q_open = false;                                         // a kept bar starts in [q, q + 30 min]: q's exit bar is b
   if(!tr.q_x0) return;
   tr.q_x0 = false;
   if(tr.hold == CR_PH_TENT) tr.hold = CR_PH_DONE;            // the decision of the barrier at x0 stands
   if(tr.held && tr.xg && tr.x > b.t)
     {
      tr.q = tr.x;
      tr.q_open = true;
     }
  }

//+------------------------------------------------------------------+
//| Rule exits and orders on a bar                                   |
//+------------------------------------------------------------------+
// a rule exit resolves on the first kept bar inside its window: oid's time exit becomes "this bar, no gap rule"
void PapExitsOnBar(const int sl, const CrBar &b)
  {
   int base = sl * CR_PAP_XMAX;
   for(int k = 0; k < g_pap_xn[sl]; k++)
     {
      if(g_pap_x[base + k].st != CR_PX_WAIT) continue;
      if(b.t < g_pap_x[base + k].e.t_from || b.t > g_pap_x[base + k].e.t_to) continue;
      g_pap_x[base + k].st = CR_PX_DONE;
      g_pap_x[base + k].bar = b.t;
      long oid = g_pap_x[base + k].e.oid;
      if(g_pap_t[sl].st == CR_PT_OPEN && g_pap_t[sl].o.oid == oid)
        {
         g_pap_t[sl].x = b.t;
         g_pap_t[sl].xg = false;
         g_pap_t[sl].q_open = false;
         g_pap_t[sl].q_x0 = false;
         g_pap_t[sl].hold = CR_PH_NONE;
         g_pap_t[sl].held = false;
        }
      for(int j = 0; j < g_pap_qn[sl]; j++)
         if(g_pap_q[sl * CR_PAP_QMAX + j].o.oid == oid)
           {
            g_pap_q[sl * CR_PAP_QMAX + j].o.x_sched = b.t;
            g_pap_q[sl * CR_PAP_QMAX + j].o.x_gap = false;
            g_pap_q[sl * CR_PAP_QMAX + j].o.xh = 0;
           }
     }
  }

// does the waiting order o activate on bar b?
bool PapActivates(const int sl, const CrOrder &o, const CrBar &b)
  {
   if(b.t < o.t_from || b.t > o.t_to) return false;
   if(o.after_exit_of == 0) return true;
   int k = PapExitFind(sl, o.after_exit_of);
   if(k < 0) return false;
   return g_pap_x[k].st == CR_PX_DONE && g_pap_x[k].bar < b.t;
  }

// the sleeve's queue on bar b, in emission order: armed orders try to fill, waiting orders activate
void PapOrdersOnBar(const int sl, const CrBar &b)
  {
   int base = sl * CR_PAP_QMAX;
   int n = g_pap_qn[sl];
   for(int k = 0; k < n; k++)
     {
      int i = base + k;
      if(g_pap_q[i].st == CR_PO_WAIT)
        {
         if(!PapActivates(sl, g_pap_q[i].o, b)) continue;
         if(g_pap_q[i].o.void_le && g_pap_q[i].o.x_sched > 0 && g_pap_q[i].o.x_sched <= b.t)
           {
            PapEmit(CR_EV_PVOID, sl, g_pap_q[i].o.oid, g_pap_q[i].o.side, b.t, b.t, 0.0, 0.0, 0.0, CR_R_VOID, g_pap_q[i].o.x_sched,
                    b.s_raw, b.ao - b.bo);
            g_pap_q[i].st = 0;                                 // the wrapper drops it: it skips nothing and blocks nothing
            continue;
           }
         bool busy = (g_pap_t[sl].st == CR_PT_OPEN) || (g_pap_lx[sl] != 0 && g_pap_lx[sl] == b.t);   // sim.py:80
         if(busy)
           {
            g_pap_q[i].st = 0;
            continue;
           }
         g_pap_q[i].act = b.t;
         if(g_pap_q[i].o.etype != CR_ET_MARKET)
           {
            g_pap_q[i].st = CR_PO_ARMED;
            if(b.t >= g_pap_q[i].o.expiry_excl)
              {
               g_pap_q[i].st = 0;                              // no bar of its window may fill it (sim.py 'nofill')
               continue;
              }
           }
        }
      else if(g_pap_q[i].st == CR_PO_ARMED)
        {
         if(b.t >= g_pap_q[i].o.expiry_excl)
           {
            g_pap_q[i].st = 0;
            continue;
           }
         if(g_pap_t[sl].st == CR_PT_OPEN) continue;            // (cannot happen: PapSubmit refuses overlaps)
        }
      else continue;
      int side = 0, et = 0;
      double fp = 0.0, lv = 0.0;
      if(!PapTryFill(sl, g_pap_q[i].o, b, side, fp, et, lv)) continue;
      CrOrder o;
      o = g_pap_q[i].o;
      datetime act = g_pap_q[i].act;
      g_pap_q[i].st = 0;
      PapOpen(sl, g_pap_t[sl], o, act, b, side, fp, et, lv);
     }
   PapOrdersCompact(sl);
  }

//+------------------------------------------------------------------+
//| Barrier                                                          |
//+------------------------------------------------------------------+
void PapOrdersOnBarrier(const int sl, const datetime M)
  {
   int base = sl * CR_PAP_QMAX;
   for(int k = 0; k < g_pap_qn[sl]; k++)
     {
      int i = base + k;
      if(g_pap_q[i].st == CR_PO_WAIT)
        {
         if(g_pap_q[i].o.t_to < M)
           {
            g_pap_q[i].st = 0;                                 // its window ended without an activation
            continue;
           }
         if(g_pap_q[i].o.after_exit_of != 0)
           {
            int x = PapExitFind(sl, g_pap_q[i].o.after_exit_of);
            if(x >= 0 && g_pap_x[x].st == CR_PX_VOID) g_pap_q[i].st = 0;   // void with its exit
           }
        }
      else if(g_pap_q[i].st == CR_PO_ARMED)
        {
         // void_le: no kept bar after the activation bar up to x + 30 min -> the exit bar is the activation bar. That is
         // known at the first barrier after x + 30 min, unless the order expired at an earlier barrier: the two are taken
         // in the order of their own barriers, so PapOnBar's barrier, which may see both at once, decides as the minutes do
         if(g_pap_q[i].o.void_le && g_pap_q[i].o.x_gap && g_pap_q[i].o.x_sched > g_pap_q[i].act && M > g_pap_q[i].o.x_sched + CR_PAP_GAP
            && g_pap_last[sl] == g_pap_q[i].act && PapMinAfter(g_pap_q[i].o.x_sched + CR_PAP_GAP) < PapMinFrom(g_pap_q[i].o.expiry_excl))
           {
            PapEmit(CR_EV_PVOID, sl, g_pap_q[i].o.oid, g_pap_q[i].o.side, g_pap_q[i].act, g_pap_q[i].act, 0.0, 0.0, 0.0, CR_R_VOID,
                    g_pap_q[i].o.x_sched, 0, 0.0);
            g_pap_q[i].st = 0;
            continue;
           }
         if(g_pap_q[i].o.expiry_excl <= M) g_pap_q[i].st = 0;  // no fill (sim.py 'nofill')
        }
     }
   PapOrdersCompact(sl);
  }

void PapExitsOnBarrier(const int sl, const datetime M)
  {
   int base = sl * CR_PAP_XMAX;
   for(int k = 0; k < g_pap_xn[sl]; k++)
      if(g_pap_x[base + k].st == CR_PX_WAIT && g_pap_x[base + k].e.t_to < M) g_pap_x[base + k].st = CR_PX_VOID;
  }

// the sleeve's part of barrier M: every bar of its symbol starting before M has been fed
void PapSleeveBarrier(const int sl, const datetime M)
  {
   PapExitsOnBarrier(sl, M);
   PapOrdersOnBarrier(sl, M);
   PapExitsCompact(sl);
   if(g_pap_t[sl].st == CR_PT_OPEN && g_pap_t[sl].hold == CR_PH_DUE && M >= g_pap_t[sl].x0) PapHoldAtBarrier(sl, g_pap_t[sl], M);
   for(int guard = 0; guard < 4; guard++)                    // x0's question, then the extended exit's
     {
      if(g_pap_t[sl].st == CR_PT_NONE || !g_pap_t[sl].q_open || M <= g_pap_t[sl].q + CR_PAP_GAP) break;
      PapRevise(sl, g_pap_t[sl], M);
     }
  }

//+------------------------------------------------------------------+
//| API                                                              |
//+------------------------------------------------------------------+
void PapReset()
  {
   for(int i = 0; i < CR_PAP_QALL; i++) ZeroMemory(g_pap_q[i]);
   for(int i = 0; i < CR_PAP_XALL; i++) ZeroMemory(g_pap_x[i]);
   for(int sl = 0; sl < CR_MAX_SL; sl++)
     {
      g_pap_qn[sl] = 0;
      g_pap_xn[sl] = 0;
      ZeroMemory(g_pap_t[sl]);
      g_pap_t[sl].st = CR_PT_NONE;
      g_pap_t[sl].reason = CR_R_NONE;
      g_pap_lx[sl] = 0;
      g_pap_lx0[sl] = 0;
      g_pap_last[sl] = 0;
     }
   g_pap_M = 0;
   g_pap_evn = 0;
  }

void PapInit()
  {
   ArrayResize(g_pap_ev, 0, 256);
   g_pap_err = 0;
   PapReset();
  }

bool PapSubmit(const CrOrder &o)
  {
   int sl = o.sleeve;
   bool ok = PapSleeveOk(sl);
   if(ok) ok = (o.etype >= CR_ET_MARKET && o.etype <= CR_ET_OCO);
   if(ok && o.etype != CR_ET_OCO) ok = (o.side == 1 || o.side == -1);
   if(ok) ok = PapOn(o.stop) || PapOn(o.stop_dist);              // every trade needs a stop (sim.py:256)
   if(ok) ok = (g_pap_qn[sl] < CR_PAP_QMAX);
   if(ok)
      for(int k = 0; k < g_pap_qn[sl]; k++)
         if(PapOverlap(g_pap_q[sl * CR_PAP_QMAX + k], o))
           {
            ok = false;
            break;
           }
   if(!ok)
     {
      g_pap_err++;
      return false;
     }
   int i = sl * CR_PAP_QMAX + g_pap_qn[sl];
   g_pap_q[i].o = o;
   g_pap_q[i].st = CR_PO_WAIT;
   g_pap_q[i].act = 0;
   g_pap_qn[sl]++;
   return true;
  }

bool PapSubmitExit(const CrExit &e)
  {
   int sl = e.sleeve;
   if(!PapSleeveOk(sl))
     {
      g_pap_err++;
      return false;
     }
   if(g_pap_xn[sl] >= CR_PAP_XMAX) PapExitsCompact(sl);
   if(g_pap_xn[sl] >= CR_PAP_XMAX)
     {
      g_pap_err++;
      return false;
     }
   int i = sl * CR_PAP_XMAX + g_pap_xn[sl];
   g_pap_x[i].e = e;
   g_pap_x[i].st = CR_PX_WAIT;
   g_pap_x[i].bar = 0;
   g_pap_xn[sl]++;
   return true;
  }

void PapOnBar(const int sl, const CrBar &b)
  {
   if(!PapSleeveOk(sl)) return;
   if(b.sym != g_sl[sl].sym || b.t <= g_pap_last[sl]) return;
   PapSleeveBarrier(sl, b.t);                                   // (a no-op after PapOnBarrier(b.t))
   PapExitsOnBar(sl, b);                                        // (0) rule exits resolve on their first kept bar
   PapTradeNewBar(g_pap_t[sl], b);                              // (0') a new bar settles an exited trade and a question
   if(g_pap_t[sl].st == CR_PT_OPEN) PapManage(sl, g_pap_t[sl], b, false);   // (1) the open trade
   PapOrdersOnBar(sl, b);                                       // (2) armed orders, then activations
   g_pap_last[sl] = b.t;
  }

void PapOnBarrier(const datetime M)
  {
   if(M > g_pap_M) g_pap_M = M;
   for(int sl = 0; sl < g_nsl; sl++)
     {
      if(!PapSleeveOk(sl)) break;
      PapSleeveBarrier(sl, M);
     }
  }

int PapEvents() { return g_pap_evn; }

bool PapEvent(const int k, CrPEvent &e)
  {
   if(k < 0 || k >= g_pap_evn) return false;
   e = g_pap_ev[k];
   return true;
  }

void PapClearEvents() { g_pap_evn = 0; }

bool PapTrade(const int sl, CrTrade &t)
  {
   if(!PapSleeveOk(sl)) return false;
   if(g_pap_t[sl].st != CR_PT_OPEN) return false;
   t.sleeve = sl;
   t.oid = g_pap_t[sl].o.oid;
   t.side = g_pap_t[sl].side;
   t.etype = g_pap_t[sl].o.etype;
   t.act_bar = g_pap_t[sl].act;
   t.fill_bar = g_pap_t[sl].fill;
   t.fill_px = g_pap_t[sl].fp;
   t.init_stop = g_pap_t[sl].st0;
   t.stop = g_pap_t[sl].cur;
   t.moved = g_pap_t[sl].moved;
   t.x_sched = g_pap_t[sl].x;
   t.x_gap = g_pap_t[sl].xg;
   t.x_pending = (g_pap_t[sl].x > 0 && g_pap_M >= g_pap_t[sl].x);
   t.dec = g_pap_t[sl].o.dec;
   t.group = g_pap_t[sl].o.group;
   return true;
  }

bool PapPending(const int sl, CrOrder &o)
  {
   if(!PapSleeveOk(sl)) return false;
   if(g_pap_qn[sl] <= 0) return false;
   o = g_pap_q[sl * CR_PAP_QMAX].o;
   return true;
  }

datetime PapLastExitBar(const int sl)
  {
   if(sl < 0 || sl >= CR_MAX_SL) return 0;
   return g_pap_lx[sl];
  }
#endif
