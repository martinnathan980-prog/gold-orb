//+------------------------------------------------------------------+
//| Brk72Rule.mqh  -  rule brk72_24h_wd (one instance per market)      |
//|                                                                  |
//| Frozen rule: lab/r2/tracks/crypto/strategy.py FINALISTS           |
//| ['brk72_24h_wd'] = {family brk, n 72, stop_atr 3.0, hold_h 24,    |
//| dow weekday} + DEFAULTS (atr_n 24, max_delay_min 5, both sides),  |
//| registered in lab/r2/recalc.py sleeves() through _crypto_fp_hours |
//| and run with no_overlap=True on the FP frame (24/5 crypto hours). |
//|                                                                  |
//|  * hour bars on the UTC grid from M1 MID prices (bid + spread/2): |
//|    o = first M1 open, h = max M1 high, l = min M1 low, c = last   |
//|    M1 close; hours without any M1 bar do not exist;               |
//|  * at the end D of a complete hour (D = whole UTC hour, Monday to |
//|    Friday by the UTC weekday of D): long if its close is above    |
//|    the highest close of the 72 previous hour bars, short if below |
//|    their lowest close (strict);                                   |
//|  * market entry at the open of the first M1 bar starting at or    |
//|    after D, dropped if it starts more than 5 minutes after D;     |
//|  * stop = fill -/+ 3 x ATR24 (simple mean of the last 24 true     |
//|    ranges of the hour bars), never moved; no target;              |
//|  * exit at the open of the first M1 bar at/after D + 24 h, or at  |
//|    the Friday 23:54 server bar when D + 24 h falls in the weekly  |
//|    closure (Friday 23:55 to Monday 00:00 server);                 |
//|  * a signal is skipped while this sleeve's trade is open and on   |
//|    the bar where that trade exits (lab/goldlab/sim.py no_overlap).|
//|                                                                  |
//| The module keeps a PAPER position with the lab simulator's        |
//| conventions (long fills at ask open x (1 + slip), stop hit on the |
//| bid low for a long and the ask high for a short; stop fill at the |
//| stop on the fill bar, else at the worse of stop and open, x slip).|
//| The paper chain decides what is skipped, whatever happens to the  |
//| real position. Real orders are asked through BrkAction.           |
//|                                                                  |
//| Calls: Init() once, Start() in OnInit (history, restart catch-up),|
//| Step() on every timer tick (does something once per new M1 bar).  |
//+------------------------------------------------------------------+
#ifndef BRK72_RULE_MQH
#define BRK72_RULE_MQH
#include "RobotClock.mqh"
#include "RobotJournal.mqh"

#define BRK_HB_CAP 4000          // hour bars kept in memory (the rule needs 73)

struct BrkHour
  {
   datetime start;               // UTC start of the hour
   double   o, h, l, c;          // mid prices
   int      cnt;                 // M1 bars in the hour
  };

struct BrkAction                 // what the robot must do NOW for this module
  {
   int      open_side;           // +1 buy, -1 sell at market, 0 nothing
   double   stop_dist;           // stop = fill -/+ stop_dist
   bool     close_now;           // close this module's real position at market
  };

class CBrk72
  {
public:
   // ---- parameters
   string   sym;                 // broker symbol name
   string   code;                // short sleeve code: position comment, journal, global variables
   int      n_chan;              // 72
   int      atr_n;               // 24
   double   stop_atr;            // 3.0
   int      hold_sec;            // 24 h
   int      max_delay_sec;       // 5 min
   int      fri_last_hhmm;       // 2354: start of the last M1 bar before the weekly closure (server clock)
   int      warmup_days;         // M1 history read at start (the rule needs 73 hour bars: 7 calendar days at least)
   double   slip_mkt, slip_stop; // paper twin only: the lab's slippage (r2/fp_costs.json), fraction of price
   double   point;
   int      digits;
   bool     debug_hours;         // journal every hour bar (HB) and every evaluation (EV)
   bool     rebuild_chain;       // no saved state: replay the history through the paper engine (the chain the lab would have)
   bool     quiet;               // no journal while the history is rebuilt
   // ---- hour bars
   BrkHour  hb[];
   int      nhb;
   bool     acc_on;
   BrkHour  acc;
   // ---- bar clock (server times)
   datetime last_closed;         // last closed M1 bar processed
   datetime cur_bar;             // forming M1 bar seen at the last call
   int      retry;               // calls that could not read the bar that just closed
   bool     started;             // Start() has read the history
   // ---- signal of the hour just completed
   datetime sig_dec;             // D (UTC), 0 = none
   int      sig_side;
   double   sig_atr;
   // ---- paper position
   int      pos_side;
   datetime pos_dec;             // D (UTC)
   datetime pos_exit_at;         // scheduled exit (UTC)
   datetime pos_fill_bar;        // fill bar (server time)
   datetime last_exit_bar;       // exit bar of the last paper trade (server time)
   double   pos_fill, pos_stop, pos_atr;

   void Init(const string symbol, const string sleeve, const double slip_mkt_bps, const double slip_stop_bps,
             const int warm_days, const bool dbg, const bool rebuild)
     {
      rebuild_chain = rebuild;
      sym = symbol;
      code = sleeve;
      n_chan = 72;
      atr_n = 24;
      stop_atr = 3.0;
      hold_sec = 24 * 3600;
      max_delay_sec = 5 * 60;
      fri_last_hhmm = 2354;
      warmup_days = warm_days;
      slip_mkt = slip_mkt_bps * 1e-4;
      slip_stop = slip_stop_bps * 1e-4;
      point = SymbolInfoDouble(sym, SYMBOL_POINT);
      digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
      debug_hours = dbg;
      quiet = false;
      ArrayResize(hb, 0, BRK_HB_CAP);
      nhb = 0;
      acc_on = false;
      ZeroMemory(acc);
      last_closed = 0;
      cur_bar = 0;
      retry = 0;
      started = false;
      sig_dec = 0;
      sig_side = 0;
      sig_atr = 0.0;
      pos_side = 0;
      pos_dec = 0;
      pos_exit_at = 0;
      pos_fill_bar = 0;
      last_exit_bar = 0;
      pos_fill = 0.0;
      pos_stop = 0.0;
      pos_atr = 0.0;
     }

   // ask price of a bar field as the broker quotes it: bid + spread, on the price grid
   double AskOf(const double bid, const int spread) { return NormalizeDouble(bid + spread * point, digits); }

   // ------------------------------------------------------------- persistence (terminal restart: OnInit again)
   string GvName(const string k) { return "SPK_" + code + "_" + k; }

   void SaveState()
     {
      GlobalVariableSet(GvName("side"), pos_side);
      GlobalVariableSet(GvName("dec"), (double)pos_dec);
      GlobalVariableSet(GvName("xat"), (double)pos_exit_at);
      GlobalVariableSet(GvName("fbar"), (double)pos_fill_bar);
      GlobalVariableSet(GvName("fill"), pos_fill);
      GlobalVariableSet(GvName("stop"), pos_stop);
      GlobalVariableSet(GvName("atr"), pos_atr);
      GlobalVariableSet(GvName("lastx"), (double)last_exit_bar);
      GlobalVariableSet(GvName("lclose"), (double)last_closed);
      GlobalVariableSet(GvName("cbar"), (double)cur_bar);
      GlobalVariablesFlush();
     }

   bool RestoreState()
     {
      if(!GlobalVariableCheck(GvName("lclose"))) return false;
      pos_side = (int)GlobalVariableGet(GvName("side"));
      pos_dec = (datetime)GlobalVariableGet(GvName("dec"));
      pos_exit_at = (datetime)GlobalVariableGet(GvName("xat"));
      pos_fill_bar = (datetime)GlobalVariableGet(GvName("fbar"));
      pos_fill = GlobalVariableGet(GvName("fill"));
      pos_stop = GlobalVariableGet(GvName("stop"));
      pos_atr = GlobalVariableGet(GvName("atr"));
      last_exit_bar = (datetime)GlobalVariableGet(GvName("lastx"));
      last_closed = (datetime)GlobalVariableGet(GvName("lclose"));
      cur_bar = (datetime)GlobalVariableGet(GvName("cbar"));
      return true;
     }

   // ------------------------------------------------------------- hour bars and signal
   void PushHour()
     {
      if(!acc_on) return;
      if(nhb >= BRK_HB_CAP)
        {
         int drop = BRK_HB_CAP / 2;
         for(int i = drop; i < nhb; i++) hb[i - drop] = hb[i];
         nhb -= drop;
        }
      if(ArraySize(hb) < nhb + 1) ArrayResize(hb, nhb + 1, BRK_HB_CAP);
      hb[nhb] = acc;
      nhb++;
      acc_on = false;
      if(debug_hours && !quiet)
         JrnLine("HB," + code + "," + JrnT(acc.start) + "," + JrnD(acc.o) + "," + JrnD(acc.h) + "," + JrnD(acc.l) + ","
                 + JrnD(acc.c) + "," + IntegerToString(acc.cnt));
      Evaluate();
     }

   void Evaluate()
     {
      sig_dec = 0;
      sig_side = 0;
      sig_atr = 0.0;
      int j = nhb - 1;
      if(j < n_chan || j < atr_n) return;                 // 73 hour bars at least (72 previous closes)
      double hi = -DBL_MAX, lo = DBL_MAX;
      for(int i = j - n_chan; i < j; i++)
        {
         if(hb[i].c > hi) hi = hb[i].c;
         if(hb[i].c < lo) lo = hb[i].c;
        }
      int side = (hb[j].c > hi) ? 1 : ((hb[j].c < lo) ? -1 : 0);
      double sum = 0.0;
      for(int i = j - atr_n + 1; i <= j; i++)
        {
         double pc = hb[i - 1].c;
         double tr = MathMax(hb[i].h - hb[i].l, MathMax(MathAbs(hb[i].h - pc), MathAbs(hb[i].l - pc)));
         sum += tr;
        }
      sig_dec = hb[j].start + 3600;
      sig_side = side;
      sig_atr = sum / atr_n;
      if(debug_hours && !quiet)
         JrnLine("EV," + code + "," + JrnT(sig_dec) + "," + IntegerToString(side) + "," + JrnD(hi) + "," + JrnD(lo) + ","
                 + JrnD(sig_atr));
     }

   void Accumulate(const datetime t, const double mo, const double mh, const double ml, const double mc)
     {
      datetime u = ClkServerToUtc(t);
      datetime hs = u - u % 3600;
      if(acc_on && hs != acc.start) PushHour();          // only when bars are read in a batch (start, catch-up)
      if(!acc_on)
        {
         acc.start = hs;
         acc.o = mo;
         acc.h = mh;
         acc.l = ml;
         acc.c = mc;
         acc.cnt = 1;
         acc_on = true;
         return;
        }
      if(mh > acc.h) acc.h = mh;
      if(ml < acc.l) acc.l = ml;
      acc.c = mc;
      acc.cnt++;
     }

   // ------------------------------------------------------------- paper position
   // exit time for a decision at D (UTC): D + 24 h, or the Friday 23:54 server bar if D + 24 h falls in the weekly closure
   datetime ExitAt(const datetime dec_utc)
     {
      datetime x = dec_utc + hold_sec;
      datetime s = ClkUtcToServer(x);
      int dow = ClkDow(s);
      int back = -1;
      if(dow == 6) back = 1;
      else if(dow == 0) back = 2;
      else if(dow == 5 && ClkHHMM(s) > fri_last_hhmm) back = 0;
      if(back < 0) return x;
      datetime fri = s - s % 86400 - back * 86400 + (fri_last_hhmm / 100) * 3600 + (fri_last_hhmm % 100) * 60;
      return ClkServerToUtc(fri);
     }

   void PaperEnter(const datetime t, const double bo, const double ao)
     {
      pos_side = sig_side;
      pos_fill = (pos_side > 0) ? ao * (1 + slip_mkt) : bo * (1 - slip_mkt);
      pos_atr = sig_atr;
      pos_stop = pos_fill - pos_side * (pos_atr * stop_atr);
      pos_dec = sig_dec;
      pos_exit_at = ExitAt(sig_dec);
      pos_fill_bar = t;
      SaveState();
     }

   void PaperExit(const datetime t, const double px, const string why)
     {
      JrnLine("TRD," + code + "," + JrnT(pos_dec) + "," + JrnT(ClkServerToUtc(pos_fill_bar)) + "," + IntegerToString(pos_side)
              + "," + JrnD(pos_fill) + "," + JrnD(pos_stop) + "," + JrnT(ClkServerToUtc(t)) + "," + JrnD(px) + "," + why + ","
              + JrnD(pos_atr) + "," + JrnT(pos_exit_at));
      pos_side = 0;
      last_exit_bar = t;
      SaveState();
     }

   // ------------------------------------------------------------- one M1 bar
   // at the OPEN of bar t (live: its first tick; catch-up: a bar that closed while nothing ran)
   void AtOpen(const datetime t, const double bid_open, const int spread, const bool live, BrkAction &act)
     {
      datetime u = ClkServerToUtc(t);
      double bo = bid_open;
      double ao = AskOf(bid_open, spread);
      // 1) the hour accumulated so far is complete once a bar starts at or after its end
      if(acc_on && acc.start + 3600 <= u) PushHour();
      // 2) paper time exit at this open (never on the fill bar)
      if(pos_side != 0 && t > pos_fill_bar && u >= pos_exit_at)
        {
         PaperExit(t, (pos_side > 0) ? bo * (1 - slip_mkt) : ao * (1 + slip_mkt), "time");
         act.close_now = true;
        }
      // 3) the decision whose first M1 bar at or after D is this one
      if(sig_dec != 0)
        {
         string st;
         if(last_closed != 0 && ClkServerToUtc(last_closed) >= sig_dec) st = "no_entry_bar";
         else if((long)u - (long)sig_dec > max_delay_sec) st = "late_bar";
         else
           {
            int dow = ClkDow(sig_dec);
            if(dow == 0 || dow == 6) st = "weekend";
            else if(!(sig_atr > 0)) st = "atr0";
            else if(pos_side != 0) st = "busy";
            else if(t <= last_exit_bar) st = "exit_bar";
            else st = live ? "taken" : "taken_paper";
           }
         if(sig_side != 0 && !quiet)
            JrnLine("DEC," + code + "," + JrnT(sig_dec) + "," + IntegerToString(sig_side) + "," + JrnD(sig_atr) + ","
                    + JrnD(sig_atr * stop_atr) + "," + JrnT(u) + "," + st);
         if(sig_side != 0 && (st == "taken" || st == "taken_paper"))
           {
            PaperEnter(t, bo, ao);
            if(live)
              {
               act.open_side = pos_side;
               act.stop_dist = pos_atr * stop_atr;
              }
           }
         sig_dec = 0;
        }
     }

   // at the CLOSE of bar b
   void AtClose(const MqlRates &b)
     {
      double bo = b.open, bh = b.high, bl = b.low, bc = b.close;
      double ao = AskOf(bo, b.spread), ah = AskOf(bh, b.spread), al = AskOf(bl, b.spread), ac = AskOf(bc, b.spread);
      if(pos_side != 0 && b.time >= pos_fill_bar)
        {
         bool first = (b.time == pos_fill_bar);
         if(pos_side > 0 && bl <= pos_stop)
            PaperExit(b.time, (first ? pos_stop : MathMin(pos_stop, bo)) * (1 - slip_stop), "stop");
         else if(pos_side < 0 && ah >= pos_stop)
            PaperExit(b.time, (first ? pos_stop : MathMax(pos_stop, ao)) * (1 + slip_stop), "stop");
        }
      Accumulate(b.time, (bo + ao) / 2, (bh + ah) / 2, (bl + al) / 2, (bc + ac) / 2);
      last_closed = b.time;
     }

   // ------------------------------------------------------------- drivers
   // OnInit (and OnTimer until it succeeds): rebuild the hour bars from history; after a restart, replay the bars that
   // closed while the robot was off. False (nothing changed) when the terminal cannot give the bars yet.
   bool Start(BrkAction &act)
     {
      MqlRates cur[];
      if(CopyRates(sym, PERIOD_M1, 0, 1, cur) != 1) return false;
      datetime upto = cur[0].time;
      MqlRates r[];
      int n = CopyRates(sym, PERIOD_M1, (datetime)(upto - warmup_days * 86400), (datetime)(upto - 1), r);   // by date range
      if(n < 0) return false;                             // history not available yet (e.g. just after a restart)
      bool restored = RestoreState();
      datetime lc = last_closed, cb = cur_bar;
      started = true;
      int i = 0;
      if(!restored && rebuild_chain)                      // no saved state (first start, VPS migration): rebuild the chain
        {
         for(; i < n; i++)
           {
            if(r[i].time >= upto) break;
            AtOpen(r[i].time, r[i].open, r[i].spread, false, act);
            AtClose(r[i]);
           }
         act.close_now = false;                           // nothing real to close: the robot was not running
         cur_bar = 0;
         return true;
        }
      quiet = true;
      for(; i < n; i++)
        {
         if(r[i].time >= upto) break;
         if(restored && r[i].time > lc) break;
         double ao = AskOf(r[i].open, r[i].spread), ah = AskOf(r[i].high, r[i].spread);
         double al = AskOf(r[i].low, r[i].spread), ac = AskOf(r[i].close, r[i].spread);
         Accumulate(r[i].time, (r[i].open + ao) / 2, (r[i].high + ah) / 2, (r[i].low + al) / 2, (r[i].close + ac) / 2);
        }
      quiet = false;
      sig_dec = 0;                                        // signals of the history are not acted upon
      if(!restored)
        {
         last_closed = (i > 0) ? r[i - 1].time : 0;
         cur_bar = 0;
         return true;
        }
      last_closed = lc;
      cur_bar = cb;
      for(; i < n; i++)
        {
         if(r[i].time >= upto) break;
         if(r[i].time != cb) AtOpen(r[i].time, r[i].open, r[i].spread, false, act);
         AtClose(r[i]);
        }
      return true;
     }

   // every timer tick: true when a new M1 bar has started (act then says what to do now)
   bool Step(BrkAction &act)
     {
      act.open_side = 0;
      act.stop_dist = 0.0;
      act.close_now = false;
      if(!started) return Start(act);                     // the history could not be read in OnInit: try again now
      MqlRates cur[];
      if(CopyRates(sym, PERIOD_M1, 0, 1, cur) != 1) return false;
      datetime t0 = cur[0].time;
      if(t0 == cur_bar) return false;
      // bars that closed since the last call (normally one: the bar that was forming)
      MqlRates r[];
      datetime from = (last_closed > 0) ? last_closed + 60 : cur_bar;      // no history at all: from the first bar seen
      int n = (from > 0 && from < t0) ? CopyRates(sym, PERIOD_M1, (datetime)from, (datetime)(t0 - 1), r) : 0;
      bool seen = (cur_bar == 0 || cur_bar <= last_closed);
      for(int i = 0; i < n; i++)
         if(r[i].time == cur_bar) seen = true;
      if(!seen && retry < 30)                             // the bar that just closed is not readable yet: next tick
        {
         retry++;
         return false;
        }
      retry = 0;
      for(int i = 0; i < n; i++)
        {
         if(r[i].time <= last_closed || r[i].time >= t0) continue;
         if(r[i].time != cur_bar) AtOpen(r[i].time, r[i].open, r[i].spread, false, act);
         AtClose(r[i]);
        }
      cur_bar = t0;
      AtOpen(t0, cur[0].open, cur[0].spread, true, act);
      GlobalVariableSet(GvName("lclose"), (double)last_closed);
      GlobalVariableSet(GvName("cbar"), (double)cur_bar);
      return true;
     }
  };
#endif
