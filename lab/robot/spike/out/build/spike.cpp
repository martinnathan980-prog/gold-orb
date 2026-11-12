//+------------------------------------------------------------------+
//|                                                 SpikeRobot.mq5   |
//|  Spike of the single robot: ONE rule (brk72_24h_wd on bitcoin)    |
//|  lives inside the Expert Advisor. Built to be replayed offline   |
//|  (lab/robot/spike: translated to C++, compiled against a mock    |
//|  that serves the lab's bars minute by minute). Not for trading:  |
//|  no sizing (fixed lots), no account protections.                 |
//|                                                                  |
//|  Layout of the real robot:                                       |
//|    RobotClock.mqh    server clock <-> UTC (New York + 7 h)       |
//|    RobotJournal.mqh  one CSV journal                             |
//|    <Rule>.mqh        one class per rule; the EA owns one object  |
//|                      per (rule, market) and turns its BrkAction  |
//|                      into orders. Adding a rule = one .mqh, one  |
//|                      object, one line in OnInit and in OnTimer.  |
//+------------------------------------------------------------------+
// #property copyright "gold-orb lab"
// #property version   "0.10"
// #property description "Spike: rule brk72_24h_wd (bitcoin) inside the EA, for the offline replay test."

#include "mql5_shim.h"
#include "RobotClock.mqh.cpp"
#include "RobotJournal.mqh.cpp"
#include "Brk72Rule.mqh.cpp"

const string InpSymBtc = mock_input<string>("InpSymBtc", "BTCUSD");             // Bitcoin: broker symbol name
const long InpMagic = mock_input<long>("InpMagic", 20261112);             // Magic number of the robot's positions
const double InpLots = mock_input<double>("InpLots", 0.01);                 // Fixed volume (spike: no sizing)
const double InpSlipMktBps = mock_input<double>("InpSlipMktBps", 0.5);                  // Paper twin: lab slippage on market fills (bp, r2/fp_costs.json)
const double InpSlipStopBps = mock_input<double>("InpSlipStopBps", 1.5);                  // Paper twin: lab slippage on stop fills (bp)
const int InpWarmupDays = mock_input<int>("InpWarmupDays", 20);                   // M1 history read at start (>= 7 days for 73 hour bars over a weekend)
const bool InpDebugHours = mock_input<bool>("InpDebugHours", false);                // Journal every hour bar and every evaluation
const string InpJournal = mock_input<string>("InpJournal", "spike_journal.csv");  // Journal file (MQL5\Files)

CTrade   g_trade;
CBrk72   g_btc;
ulong    g_ticket = 0;            // real position of g_btc (0 = none)
datetime g_ticket_bar = 0;        // fill bar of the paper trade that this real position follows

string TicketGv() { return "SPK_" + g_btc.code + "_ticket"; }
string TicketBarGv() { return "SPK_" + g_btc.code + "_tbar"; }

// stop on the price grid, one tick at most AWAY from the price: for a long, the largest grid price <= stop
// (a bid low on the grid touches it exactly when it touches the exact stop); for a short, the smallest >= stop
double GridStop(const string sym, const double stop, const int side)
  {
   double ts = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
   int dg = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   if(ts <= 0) return NormalizeDouble(stop, dg);
   double k = MathFloor(stop / ts);
   double g = NormalizeDouble(k * ts, dg);
   if(side > 0)
     {
      while(g > stop) { k -= 1; g = NormalizeDouble(k * ts, dg); }
      while(NormalizeDouble((k + 1) * ts, dg) <= stop) { k += 1; g = NormalizeDouble(k * ts, dg); }
      return g;
     }
   while(g < stop) { k += 1; g = NormalizeDouble(k * ts, dg); }
   while(NormalizeDouble((k - 1) * ts, dg) >= stop) { k -= 1; g = NormalizeDouble(k * ts, dg); }
   return g;
  }

void Real(const string what, const ulong ticket, const double price, const double sl)
  {
   JrnLine("REAL," + g_btc.code + "," + what + "," + IntegerToString((long)ticket) + "," + JrnD(price) + "," + JrnD(sl) + ","
           + IntegerToString((long)g_trade.ResultRetcode()) + "," + JrnT(ClkServerToUtc(TimeTradeServer())));
  }

void Execute(CBrk72 &m, const BrkAction &a)
  {
   // the real position must follow the paper one: time exit, paper flat (or on another trade) while it is still there
   if(g_ticket != 0 && (a.close_now || m.pos_side == 0 || m.pos_fill_bar != g_ticket_bar))
     {
      if(PositionSelectByTicket(g_ticket))
        {
         bool ok = g_trade.PositionClose(g_ticket);
         Real(a.close_now ? "close_time" : "close_orphan", g_ticket, g_trade.ResultPrice(), 0.0);
         if(ok) g_ticket = 0;
        }
      else
         g_ticket = 0;                                    // closed by its stop at the broker
      GlobalVariableSet(TicketGv(), (double)g_ticket);
     }
   if(a.open_side == 0) return;
   MqlTick k;
   ZeroMemory(k);
   if(!SymbolInfoTick(m.sym, k)) return;
   double sl0 = (a.open_side > 0) ? GridStop(m.sym, k.ask - a.stop_dist, 1) : GridStop(m.sym, k.bid + a.stop_dist, -1);
   bool ok = (a.open_side > 0) ? g_trade.Buy(InpLots, m.sym, 0.0, sl0, 0.0, m.code) : g_trade.Sell(InpLots, m.sym, 0.0, sl0, 0.0, m.code);
   uint rc = g_trade.ResultRetcode();
   if(!ok || (rc != TRADE_RETCODE_DONE && rc != TRADE_RETCODE_PLACED))
     {
      Real("open_refused", 0, 0.0, sl0);
      return;
     }
   g_ticket = g_trade.ResultOrder();                      // hedging account: the position ticket is the order ticket
   g_ticket_bar = m.pos_fill_bar;
   double fill = g_trade.ResultPrice();
   Real(a.open_side > 0 ? "open_buy" : "open_sell", g_ticket, fill, sl0);
   double sl = GridStop(m.sym, fill - a.open_side * a.stop_dist, a.open_side);    // the lab's stop: from the fill
   if(sl != sl0)
     {
      bool okm = g_trade.PositionModify(g_ticket, sl, 0.0);
      Real(okm ? "modify" : "modify_refused", g_ticket, fill, sl);
     }
   GlobalVariableSet(TicketGv(), (double)g_ticket);
   GlobalVariableSet(TicketBarGv(), (double)g_ticket_bar);
   GlobalVariablesFlush();
  }

int OnInit()
  {
   if(!SymbolSelect(InpSymBtc, true))
     {
      Print("SpikeRobot: unknown symbol ", InpSymBtc);
      return INIT_FAILED;
     }
   if(!JrnOpen(InpJournal, true))
     {
      Print("SpikeRobot: journal not writable");
      return INIT_FAILED;
     }
   g_trade.SetExpertMagicNumber((ulong)InpMagic);
   g_trade.SetDeviationInPoints(50);
   g_btc.Init(InpSymBtc, "B72B", InpSlipMktBps, InpSlipStopBps, InpWarmupDays, InpDebugHours);
   g_ticket = GlobalVariableCheck(TicketGv()) ? (ulong)GlobalVariableGet(TicketGv()) : 0;
   g_ticket_bar = GlobalVariableCheck(TicketBarGv()) ? (datetime)GlobalVariableGet(TicketBarGv()) : 0;
   BrkAction a;
   ZeroMemory(a);
   g_btc.Start(a);
   Execute(g_btc, a);
   JrnLine("INIT," + g_btc.code + "," + JrnT(ClkServerToUtc(TimeTradeServer())) + "," + IntegerToString(g_btc.nhb) + ","
           + IntegerToString(g_btc.pos_side));
   if(!EventSetTimer(1)) return INIT_FAILED;
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   g_btc.SaveState();
   GlobalVariableSet(TicketGv(), (double)g_ticket);
   GlobalVariableSet(TicketBarGv(), (double)g_ticket_bar);
   GlobalVariablesFlush();
   JrnClose();
  }

void OnTimer()
  {
   BrkAction a;
   ZeroMemory(a);
   if(g_btc.Step(a)) Execute(g_btc, a);
  }

void OnTick()
  {
  }
