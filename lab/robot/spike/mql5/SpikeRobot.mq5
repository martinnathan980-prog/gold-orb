//+------------------------------------------------------------------+
//|                                                 SpikeRobot.mq5   |
//|  Spike of the single robot: the rule brk72_24h_wd lives inside    |
//|  the Expert Advisor (bitcoin, and ether as a second instance of   |
//|  the same module). Built to be replayed offline (lab/robot/spike: |
//|  translated to C++, compiled against a mock that serves the lab's |
//|  bars minute by minute). Not for trading: no sizing (fixed lots), |
//|  no account protections.                                          |
//|                                                                  |
//|  Layout of the real robot:                                       |
//|    RobotClock.mqh    server clock <-> UTC (New York + 7 h)       |
//|    RobotJournal.mqh  one CSV journal                             |
//|    <Rule>.mqh        one class per rule; the EA owns one object  |
//|                      per (rule, market) and turns its BrkAction  |
//|                      into orders. Adding a rule = one .mqh, one  |
//|                      object, one line in OnInit, OnTimer and     |
//|                      OnDeinit (see g_eth below).                 |
//+------------------------------------------------------------------+
#property copyright "gold-orb lab"
#property version   "0.11"
#property description "Spike: rule brk72_24h_wd inside the EA, for the offline replay test."

#include <Trade\Trade.mqh>
#include "RobotClock.mqh"
#include "RobotJournal.mqh"
#include "Brk72Rule.mqh"

input string InpSymBtc      = "BTCUSD";             // Bitcoin: broker symbol name
input string InpSymEth      = "";                   // Ether: broker symbol name ("" = this module is off)
input long   InpMagic       = 20261112;             // Magic number of the robot's positions
input double InpLots        = 0.01;                 // Fixed volume (spike: no sizing)
input double InpSlipMktBps  = 0.5;                  // Paper twin, bitcoin: lab slippage on market fills (bp, r2/fp_costs.json)
input double InpSlipStopBps = 1.5;                  // Paper twin, bitcoin: lab slippage on stop fills (bp)
input double InpEthMktBps   = 0.7;                  // Paper twin, ether: market fills (bp)
input double InpEthStopBps  = 2.0;                  // Paper twin, ether: stop fills (bp)
input int    InpWarmupDays  = 20;                   // M1 history read at start (>= 7 days for 73 hour bars over a weekend)
input bool   InpDebugHours  = false;                // Journal every hour bar and every evaluation
input string InpJournal     = "spike_journal.csv";  // Journal file (MQL5\Files)

CTrade   g_trade;
CBrk72   g_btc;
CBrk72   g_eth;
bool     g_eth_on = false;
ulong    g_tk_btc = 0, g_tk_eth = 0;          // real position following each module's paper trade (0 = none)
datetime g_tb_btc = 0, g_tb_eth = 0;          // fill bar of the paper trade that this real position follows

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

void Real(const string code, const string what, const ulong ticket, const double price, const double sl)
  {
   JrnLine("REAL," + code + "," + what + "," + IntegerToString((long)ticket) + "," + JrnD(price) + "," + JrnD(sl) + ","
           + IntegerToString((long)g_trade.ResultRetcode()) + "," + JrnT(ClkServerToUtc(TimeTradeServer())));
  }

void SaveTicket(const string code, const ulong ticket, const datetime bar)
  {
   GlobalVariableSet("SPK_" + code + "_ticket", (double)ticket);
   GlobalVariableSet("SPK_" + code + "_tbar", (double)bar);
  }

void LoadTicket(const string code, ulong &ticket, datetime &bar)
  {
   ticket = GlobalVariableCheck("SPK_" + code + "_ticket") ? (ulong)GlobalVariableGet("SPK_" + code + "_ticket") : 0;
   bar = GlobalVariableCheck("SPK_" + code + "_tbar") ? (datetime)GlobalVariableGet("SPK_" + code + "_tbar") : 0;
  }

// the module's requests -> real orders; the real position follows the paper one (lab conventions)
void Execute(CBrk72 &m, const BrkAction &a, ulong &ticket, datetime &ticket_bar)
  {
   // time exit, or paper flat (or on another trade) while the real position is still there
   if(ticket != 0 && (a.close_now || m.pos_side == 0 || m.pos_fill_bar != ticket_bar))
     {
      if(PositionSelectByTicket(ticket))
        {
         bool ok = g_trade.PositionClose(ticket);
         Real(m.code, a.close_now ? "close_time" : "close_orphan", ticket, g_trade.ResultPrice(), 0.0);
         if(ok) ticket = 0;
        }
      else
         ticket = 0;                                      // closed by its stop at the broker
      SaveTicket(m.code, ticket, ticket_bar);
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
      Real(m.code, "open_refused", 0, 0.0, sl0);
      return;
     }
   ticket = g_trade.ResultOrder();                        // hedging account: the position ticket is the order ticket
   ticket_bar = m.pos_fill_bar;
   double fill = g_trade.ResultPrice();
   Real(m.code, a.open_side > 0 ? "open_buy" : "open_sell", ticket, fill, sl0);
   double sl = GridStop(m.sym, fill - a.open_side * a.stop_dist, a.open_side);    // the lab's stop: from the fill
   if(sl != sl0)
     {
      bool okm = g_trade.PositionModify(ticket, sl, 0.0);
      Real(m.code, okm ? "modify" : "modify_refused", ticket, fill, sl);
     }
   SaveTicket(m.code, ticket, ticket_bar);
   GlobalVariablesFlush();
  }

bool StartModule(CBrk72 &m, const string sym, const string code, const double mkt_bps, const double stop_bps, ulong &ticket,
                 datetime &ticket_bar)
  {
   if(!SymbolSelect(sym, true))
     {
      Print("SpikeRobot: unknown symbol ", sym);
      return false;
     }
   m.Init(sym, code, mkt_bps, stop_bps, InpWarmupDays, InpDebugHours);
   LoadTicket(code, ticket, ticket_bar);
   BrkAction a;
   ZeroMemory(a);
   if(m.Start(a)) Execute(m, a, ticket, ticket_bar);           // else Step() tries again at every timer tick
   JrnLine("INIT," + code + "," + JrnT(ClkServerToUtc(TimeTradeServer())) + "," + IntegerToString(m.nhb) + "," + IntegerToString(m.pos_side));
   return true;
  }

int OnInit()
  {
   if(!JrnOpen(InpJournal, true))
     {
      Print("SpikeRobot: journal not writable");
      return INIT_FAILED;
     }
   g_trade.SetExpertMagicNumber((ulong)InpMagic);
   g_trade.SetDeviationInPoints(50);
   if(!StartModule(g_btc, InpSymBtc, "B72B", InpSlipMktBps, InpSlipStopBps, g_tk_btc, g_tb_btc)) return INIT_FAILED;
   g_eth_on = (InpSymEth != "");
   if(g_eth_on && !StartModule(g_eth, InpSymEth, "B72E", InpEthMktBps, InpEthStopBps, g_tk_eth, g_tb_eth)) return INIT_FAILED;
   if(!EventSetTimer(1)) return INIT_FAILED;
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   g_btc.SaveState();
   SaveTicket(g_btc.code, g_tk_btc, g_tb_btc);
   if(g_eth_on)
     {
      g_eth.SaveState();
      SaveTicket(g_eth.code, g_tk_eth, g_tb_eth);
     }
   GlobalVariablesFlush();
   JrnClose();
  }

void OnTimer()
  {
   BrkAction a;
   ZeroMemory(a);
   if(g_btc.Step(a)) Execute(g_btc, a, g_tk_btc, g_tb_btc);
   if(g_eth_on)
     {
      ZeroMemory(a);
      if(g_eth.Step(a)) Execute(g_eth, a, g_tk_eth, g_tb_eth);
     }
  }

void OnTick()
  {
  }
