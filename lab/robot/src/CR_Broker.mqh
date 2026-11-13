//+------------------------------------------------------------------+
//| CR_Broker.mqh - the only sender of trade requests (SPEC 4.3, 4.4, |
//| 6.2). Owner: J.                                                   |
//|                                                                  |
//| Every request of the robot goes through this file: opens with the |
//| hands' DoOpen checks (ClaudeMains.mq5:760-860) and the post-fill  |
//| check, closes, stop moves and the guard's mark trade. It also     |
//| holds Resolve, GridStop, the robot comment, the broker's session  |
//| end, the one-intent-one-trade search (R5) and the two stable      |
//| reads of positions and orders (SPEC 4.8 a).                       |
//|                                                                  |
//| Opens (BrkOpen), in this order, nothing is sent when one fails:   |
//|   not an observer copy and the instance lock held (the gate);     |
//|   connected; Algo Trading on (terminal, program, account);        |
//|   hedging account; a tick at most 10 s old; trade mode full;      |
//|   SYMBOL_ORDER_SL accepted (else CTrade drops the stop silently); |
//|   a stop > 0 on the right side, beyond STOPS_LEVEL; the volume    |
//|   floored to the step and cut to 20 x the balance in value        |
//|   (journal cut=notional), at least the minimum lot. The request   |
//|   goes with deviation 2 spreads. After a fill: a stop the broker  |
//|   did not keep is put back (closed when that fails), and the real |
//|   money risk (side x (fill - SL) + 2h) / tick size x tick value   |
//|   loss x lots must be at most 1.25 x the sized budget, else the   |
//|   position is closed (REFUSED). Results: CR_SEND_OK (a position   |
//|   exists, even when it was refused and closed again at once:      |
//|   g_brk_refused), CR_SEND_FAIL (nothing opened), CR_SEND_UNKNOWN  |
//|   (no retcode, timeout, no connection or placed: the follower     |
//|   re-sends nothing before BrkIntentCheck allows it).              |
//| Closes and stop moves touch only the robot's own positions (magic |
//| 20261201-20261289 and the guard's mark 20261290); the hands' and  |
//| manual positions are never touched. A position that vanished      |
//| while it was being closed counts as closed (g_brk_gone).          |
//| Journal: SEND (after the request: result, retcode, s_raw,         |
//| s_paper), FILL, REFUSED, CLOSE, SLMOD, MARK.                      |
//|                                                                  |
//| API (S0 signatures kept; the rest is new):                        |
//|   BrkInit(err)                  once at OnInit                   |
//|   BrkResolve(base)              the broker's symbol name ("" =   |
//|                                 none), ClaudeMains.mq5:206-226   |
//|   BrkConnected()                terminal connected               |
//|   BrkStableRead(now_srv)        two reads of positions and       |
//|                                 orders at least 2 s apart agree  |
//|   BrkGridStop(sym, stop, side)  on the tick grid, away from the  |
//|                                 market by less than one tick     |
//|   BrkOpen(it, sl)               CR_SEND_OK / FAIL / UNKNOWN      |
//|   BrkClose(ticket, magic, why)  close a position, request magic  |
//|                                 `magic` (0 = its own); true when |
//|                                 it no longer exists              |
//|   BrkModify(ticket, sl)         move a position's stop           |
//|   BrkCloseAll(magic, why)       every robot position (GUARD:     |
//|                                 magic 20261290); true when none  |
//|                                 is left                          |
//| New: BrkGridOf, BrkComment, BrkCommentDec, BrkSessionEnd,         |
//|   BrkIntentCheck, BrkMark, BrkQuote, BrkRiskMoney, BrkTradeAllowed|
//|   BrkHedging, BrkRobotMagic, BrkOurMagic, BrkMay, BrkRobotCount.  |
//+------------------------------------------------------------------+
#ifndef CR_BROKER_MQH
#define CR_BROKER_MQH
#include <Trade\Trade.mqh>
#include "CR_Types.mqh"
#include "CR_Clock.mqh"
#include "CR_Journal.mqh"

#define CR_BRK_TICK_AGE 10              // a last tick older than 10 s: no open (ClaudeMains InpMaxTickAgeSec)
#define CR_BRK_NOTIONAL_X 20.0          // the value of a new position is cut to 20 x the balance (InpMaxNotionalX)
#define CR_BRK_RISK_X 1.25              // post-fill: the real money risk at most 1.25 x the sized budget
#define CR_BRK_DEV_SPREADS 2            // deviation: 2 spreads
#define CR_BRK_STABLE_S 2               // two reads of positions and orders at least 2 s apart
#define CR_BRK_MAGIC_LO 20261201        // sleeve positions of this robot (SPEC 2.3)
#define CR_BRK_MAGIC_HI 20261289
#define CR_BRK_SESS_MAX 43200           // a broker session end counts when at most 12 h before the known closure
#define CR_BRK_RC_PRICE_CHANGED 10020   // trade server return codes the shim does not name
#define CR_BRK_RC_TOO_MANY 10024
#define CR_BRK_RC_LOCKED 10028

CTrade   g_trade;                       // the one CTrade of the EA (SPEC 1, MQL5 subset)
uint     g_brk_rc = 0;                  // retcode of the last request (0 = none, or nothing sent)
string   g_brk_why = "";                // why the last call sent nothing or did not succeed ("" = none)
bool     g_brk_gone = false;            // the position of the last close or stop move no longer exists (not by us)
bool     g_brk_refused = false;         // the last BrkOpen filled, then refused the position (REFUSED)
double   g_brk_fill = 0.0;              // the last fill: price, volume, stop as listed, real money risk
double   g_brk_vol = 0.0;
double   g_brk_sl = 0.0;
double   g_brk_risk = 0.0;
bool     g_brk_listed = false;          // the last filled position was already listed after the request
bool     g_brk_may = true;              // the guards' gate: false = no request at all (instance lock lost)
long     g_brk_sent = 0;                // requests sent
ulong    g_brk_fp = 0;                  // stable read: fingerprint of the positions and orders, its size, since when
long     g_brk_fp_n = -1;
datetime g_brk_fp_t = 0;

bool BrkRobotMagic(const long m) { return m >= CR_BRK_MAGIC_LO && m <= CR_BRK_MAGIC_HI; }
bool BrkOurMagic(const long m) { return BrkRobotMagic(m) || m == CR_MAGIC_MARK; }

int BrkSymOf(const string name)
  {
   if(name == "") return -1;
   for(int s = 0; s < CR_NSYM; s++)
      if(g_sym[s].name != "" && g_sym[s].name == name) return s;
   return -1;
  }

bool BrkInit(string &err)
  {
   err = "";
   g_brk_rc = 0;
   g_brk_why = "";
   g_brk_gone = false;
   g_brk_refused = false;
   g_brk_listed = false;
   g_brk_may = true;
   g_brk_sent = 0;
   g_brk_fp = 0;
   g_brk_fp_n = -1;
   g_brk_fp_t = 0;
   g_trade.SetAsyncMode(false);
   return true;
  }

// a request may go out: not an observer copy (SPEC 4.9) and the instance lock held
bool BrkMay(string &why)
  {
   if(g_cfg.observer)
     {
      why = "observer";
      return false;
     }
   if(!g_brk_may)
     {
      why = "lock";
      return false;
     }
   return true;
  }

//+------------------------------------------------------------------+
//| Symbols and quotes                                               |
//+------------------------------------------------------------------+
bool BrkTradable(const string s)
  {
   return SymbolSelect(s, true) && SymbolInfoInteger(s, SYMBOL_TRADE_MODE) != SYMBOL_TRADE_MODE_DISABLED;
  }

// the broker's name of a market: name + ".r" (Raw account), the name, a known alias, else the first symbol starting
// with the name (ClaudeMains.mq5:206-226)
string BrkResolve(const string base)
  {
   if(BrkTradable(base + ".r")) return base + ".r";
   if(BrkTradable(base)) return base;
   string alt[];
   int na = 0;
   if(base == "US100") na = StringSplit("NAS100,USTEC,US100.cash,NDX100", ',', alt);
   if(base == "XAUUSD") na = StringSplit("GOLD", ',', alt);
   for(int a = 0; a < na; a++)
     {
      if(BrkTradable(alt[a] + ".r")) return alt[a] + ".r";
      if(BrkTradable(alt[a])) return alt[a];
     }
   int total = SymbolsTotal(false);
   for(int i = 0; i < total; i++)
     {
      string s = SymbolName(i, false);
      if(StringFind(s, base) == 0 && BrkTradable(s)) return s;
     }
   return "";
  }

bool BrkConnected() { return TerminalInfoInteger(TERMINAL_CONNECTED) != 0; }

// Algo Trading allowed by the terminal, the program and the account (ClaudeMains.mq5 TradeAllowed)
bool BrkTradeAllowed()
  {
   return TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) != 0 && MQLInfoInteger(MQL_TRADE_ALLOWED) != 0
          && AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) != 0 && AccountInfoInteger(ACCOUNT_TRADE_EXPERT) != 0;
  }

bool BrkHedging() { return AccountInfoInteger(ACCOUNT_MARGIN_MODE) == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING; }

// the last tick of a symbol: raw bid, raw ask and its server time; false without a price
bool BrkQuote(const int sym, double &bid, double &ask, datetime &t_srv)
  {
   bid = 0.0;
   ask = 0.0;
   t_srv = 0;
   if(sym < 0 || sym >= CR_NSYM || g_sym[sym].name == "") return false;
   MqlTick k;
   ZeroMemory(k);
   if(!SymbolInfoTick(g_sym[sym].name, k)) return false;
   bid = k.bid;
   ask = k.ask;
   t_srv = (datetime)k.time;
   return bid > 0.0 && ask > 0.0;
  }

// tick value for a loss (falls back to the tick value)
double BrkTvl(const string nm)
  {
   double tv = SymbolInfoDouble(nm, SYMBOL_TRADE_TICK_VALUE_LOSS);
   if(!(tv > 0.0)) tv = SymbolInfoDouble(nm, SYMBOL_TRADE_TICK_VALUE);
   return tv;
  }

// the real money at risk of `lots` filled at `fill` with the stop `sl`, the round-trip commission included (SPEC 4.3):
// (side x (fill - sl) + 2h) / tick size x tick value loss x lots; -1 when the symbol gives no tick size or value
double BrkRiskMoney(const int sym, const int side, const double fill, const double sl, const double lots)
  {
   if(sym < 0 || sym >= CR_NSYM) return -1.0;
   string nm = g_sym[sym].name;
   double ts = SymbolInfoDouble(nm, SYMBOL_TRADE_TICK_SIZE), tv = BrkTvl(nm);
   if(!(ts > 0.0) || !(tv > 0.0)) return -1.0;
   return (side * (fill - sl) + 2.0 * g_sym[sym].h) / ts * tv * lots;
  }

// raw spread in points
int BrkSpreadPts(const int sym, const double bid, const double ask)
  {
   double pt = g_sym[sym].point;
   if(!(pt > 0.0)) return 0;
   return (int)MathRound((ask - bid) / pt);
  }

ulong BrkDeviation(const int sym)
  {
   double bid = 0.0, ask = 0.0;
   datetime t = 0;
   int s = 1;
   if(sym >= 0 && BrkQuote(sym, bid, ask, t)) s = BrkSpreadPts(sym, bid, ask);
   if(s < 1) s = 1;
   return (ulong)(CR_BRK_DEV_SPREADS * s);
  }

//+------------------------------------------------------------------+
//| Stops on the grid (SpikeRobot.mq5:48-66)                         |
//+------------------------------------------------------------------+
// a stop on the price grid, less than one tick AWAY from the price: for a long the largest grid price <= stop (a bid
// low on the grid touches it exactly when it touches the exact stop), for a short the smallest grid price >= stop
double BrkGridOf(const double stop, const int side, const double ts, const int dg)
  {
   if(!(ts > 0.0)) return NormalizeDouble(stop, dg);
   double k = MathFloor(stop / ts);
   double g = NormalizeDouble(k * ts, dg);
   if(side > 0)
     {
      while(g > stop)
        {
         k -= 1.0;
         g = NormalizeDouble(k * ts, dg);
        }
      while(NormalizeDouble((k + 1.0) * ts, dg) <= stop)
        {
         k += 1.0;
         g = NormalizeDouble(k * ts, dg);
        }
      return g;
     }
   while(g < stop)
     {
      k += 1.0;
      g = NormalizeDouble(k * ts, dg);
     }
   while(NormalizeDouble((k - 1.0) * ts, dg) >= stop)
     {
      k -= 1.0;
      g = NormalizeDouble(k * ts, dg);
     }
   return g;
  }

double BrkGridStop(const int sym, const double stop, const int side)
  {
   if(sym < 0 || sym >= CR_NSYM || g_sym[sym].name == "") return stop;
   string nm = g_sym[sym].name;
   double ts = SymbolInfoDouble(nm, SYMBOL_TRADE_TICK_SIZE);
   int dg = (int)SymbolInfoInteger(nm, SYMBOL_DIGITS);
   return BrkGridOf(stop, side, ts, dg);
  }

//+------------------------------------------------------------------+
//| The robot comment "CR <code> <yymmddhhmm>" (decision, UTC; SPEC  |
//| 2.3: informative only, LatestExit cross-checks it)               |
//+------------------------------------------------------------------+
string BrkComment(const string code, const datetime dec)
  {
   MqlDateTime d;
   TimeToStruct(dec, d);
   return "CR " + code + " " + StringFormat("%02d%02d%02d%02d%02d", d.year % 100, d.mon, d.day, d.hour, d.min);
  }

// the decision time a comment names (UTC), 0 when it does not parse or names another code
datetime BrkCommentDec(const string comment, const string code)
  {
   string part[];
   int n = StringSplit(comment, ' ', part);
   if(n != 3) return 0;
   if(part[0] != "CR" || part[1] != code || StringLen(part[2]) != 10) return 0;
   int v[5];
   for(int k = 0; k < 5; k++)
     {
      int a = (int)StringGetCharacter(part[2], 2 * k) - 48;
      int b = (int)StringGetCharacter(part[2], 2 * k + 1) - 48;
      if(a < 0 || a > 9 || b < 0 || b > 9) return 0;
      v[k] = 10 * a + b;
     }
   if(v[1] < 1 || v[1] > 12 || v[2] < 1 || v[2] > 31 || v[3] > 23 || v[4] > 59) return 0;
   MqlDateTime d;
   d.year = 2000 + v[0];
   d.mon = v[1];
   d.day = v[2];
   d.hour = v[3];
   d.min = v[4];
   d.sec = 0;
   d.day_of_week = 0;
   d.day_of_year = 0;
   return StructToTime(d);
  }

//+------------------------------------------------------------------+
//| The broker's session end (SPEC 2.1: an earlier broker session end |
//| wins over a known closure; ClkRealExitMinute's fri_end_utc)      |
//+------------------------------------------------------------------+
// UTC end of the broker's last trade session before the known closure that holds x or follows it, when the market is
// not open in the minute before that closure and the session ends at most 12 h before it; 0 otherwise (no session
// information, or open until the closure)
datetime BrkSessionEnd(const int sym, const datetime x_utc)
  {
   if(sym < 0 || sym >= CR_NSYM || g_sym[sym].name == "") return 0;
   datetime c0 = 0, c1 = 0;
   if(!ClkNextClosure(g_sym[sym].family, x_utc, c0, c1)) return 0;
   datetime c0s = ClkUtcToServer(c0);
   datetime day = ClkDay(c0s - 60);                         // server date of the minute before the closure
   int dow = ClkDow(day);
   datetime best = 0;
   bool open_at = false;
   for(int k = 0; k < 16; k++)
     {
      datetime f = 0, t = 0;
      if(!SymbolInfoSessionTrade(g_sym[sym].name, (ENUM_DAY_OF_WEEK)dow, (uint)k, f, t)) break;
      datetime fs = day + f, e = day + t;                    // f, t: seconds since the start of the day
      if(fs <= c0s - 60 && c0s - 60 < e) open_at = true;
      if(e <= c0s && e > best) best = e;
     }
   if(open_at || best == 0 || (long)(c0s - best) > CR_BRK_SESS_MAX) return 0;
   return ClkServerToUtc(best);
  }

//+------------------------------------------------------------------+
//| Two reads of positions and orders 2 s apart (SPEC 4.3, 4.8 a)     |
//+------------------------------------------------------------------+
ulong BrkMix(const ulong h, const ulong v) { return (h ^ v) * (ulong)1099511628211; }

ulong BrkFingerprint(long &n)
  {
   ulong h = (ulong)1469598103934665603;
   n = 0;
   int np = PositionsTotal();
   for(int i = 0; i < np; i++)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      h = BrkMix(h, t);
      h = BrkMix(h, (ulong)PositionGetInteger(POSITION_MAGIC));
      h = BrkMix(h, (ulong)PositionGetInteger(POSITION_TYPE));
      h = BrkMix(h, (ulong)MathRound(PositionGetDouble(POSITION_VOLUME) * 100000000.0));
      h = BrkMix(h, (ulong)MathRound(PositionGetDouble(POSITION_SL) * 100000.0));
      n++;
     }
   int no = OrdersTotal();
   for(int i = 0; i < no; i++)
     {
      ulong t = OrderGetTicket(i);
      if(t == 0) continue;
      h = BrkMix(h, t);
      h = BrkMix(h, (ulong)OrderGetInteger(ORDER_STATE));
      n++;
     }
   return h;
  }

// true when the positions and open orders read now are those read at least 2 s ago (and in every read since)
bool BrkStableRead(const datetime now_srv)
  {
   long n = 0;
   ulong fp = BrkFingerprint(n);
   if(n != g_brk_fp_n || fp != g_brk_fp)
     {
      g_brk_fp = fp;
      g_brk_fp_n = n;
      g_brk_fp_t = now_srv;
      return false;
     }
   if(now_srv < g_brk_fp_t) g_brk_fp_t = now_srv;            // the server clock stepped back
   return (long)(now_srv - g_brk_fp_t) >= CR_BRK_STABLE_S;
  }

// robot positions open now (sleeve magics and the guard's mark)
int BrkRobotCount()
  {
   int c = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(BrkOurMagic(PositionGetInteger(POSITION_MAGIC))) c++;
     }
   return c;
  }

//+------------------------------------------------------------------+
//| One intent, one trade (SPEC 4.3, R5)                             |
//+------------------------------------------------------------------+
// May the intent of `magic` stamped `stamp_utc` be sent? Reads HistorySelect(0, TimeTradeServer() + 86400) (a deal timed
// a moment after the terminal's clock is still seen). Returns
//    0  yes;
//    1  the previous trade's position (opened before the stamp) is still open: prev = its ticket; close it first;
//    2  sent already: an open order of the magic in any state, a history order set up at or after the stamp that opened
//       a position (its ORDER_POSITION_ID is its own ticket) or may still do so (no position id, not rejected, canceled
//       or expired), a DEAL_ENTRY_IN deal at or after the stamp, or a position opened at or after the stamp; `found` =
//       that position's ticket when known (0 otherwise), why = which;
//   -1  the history cannot be read now.
// Closing orders and the previous trade's OUT deal do not count (R5 d).
int BrkIntentCheck(const long magic, const datetime stamp_utc, ulong &prev, ulong &found, string &why)
  {
   prev = 0;
   found = 0;
   why = "";
   datetime now = TimeTradeServer();
   if(!HistorySelect(0, now + 86400))
     {
      why = "history";
      return -1;
     }
   datetime s_srv = ClkUtcToServer(stamp_utc);
   int no = OrdersTotal();
   for(int i = 0; i < no; i++)
     {
      ulong t = OrderGetTicket(i);
      if(t == 0) continue;
      if(OrderGetInteger(ORDER_MAGIC) != magic) continue;
      why = "open_order";
      return 2;
     }
   int nh = HistoryOrdersTotal();
   for(int i = 0; i < nh; i++)
     {
      ulong t = HistoryOrderGetTicket(i);
      if(t == 0 || HistoryOrderGetInteger(t, ORDER_MAGIC) != magic) continue;
      if((datetime)HistoryOrderGetInteger(t, ORDER_TIME_SETUP) < s_srv) continue;
      long pid = HistoryOrderGetInteger(t, ORDER_POSITION_ID);
      long st = HistoryOrderGetInteger(t, ORDER_STATE);
      if(pid == (long)t)
        {
         found = t;
         why = "order";
         return 2;
        }
      if(pid == 0 && st != ORDER_STATE_REJECTED && st != ORDER_STATE_CANCELED && st != ORDER_STATE_EXPIRED)
        {
         why = "order_pending";
         return 2;
        }
     }
   int nd = HistoryDealsTotal();
   for(int i = 0; i < nd; i++)
     {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0 || HistoryDealGetInteger(d, DEAL_MAGIC) != magic) continue;
      if(HistoryDealGetInteger(d, DEAL_ENTRY) != DEAL_ENTRY_IN) continue;
      if((datetime)HistoryDealGetInteger(d, DEAL_TIME) < s_srv) continue;
      found = (ulong)HistoryDealGetInteger(d, DEAL_POSITION_ID);
      why = "deal_in";
      return 2;
     }
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0 || PositionGetInteger(POSITION_MAGIC) != magic) continue;
      if((datetime)PositionGetInteger(POSITION_TIME) >= s_srv)
        {
         found = t;
         why = "position";
         return 2;
        }
      prev = t;
     }
   if(prev != 0)
     {
      why = "prev_open";
      return 1;
     }
   return 0;
  }

// the deal history holds an OUT deal of that position (call after HistorySelect, e.g. after BrkIntentCheck)
bool BrkPositionClosed(const long pos_id)
  {
   int nd = HistoryDealsTotal();
   for(int i = 0; i < nd; i++)
     {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0 || HistoryDealGetInteger(d, DEAL_POSITION_ID) != pos_id) continue;
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_OUT) return true;
     }
   return false;
  }

//+------------------------------------------------------------------+
//| Requests                                                         |
//+------------------------------------------------------------------+
// close a position (request magic `magic`, 0 = the position's own); true when it no longer exists afterwards. Only the
// robot's own positions (sleeve magics and the mark) are touched.
bool BrkClose(const ulong ticket, const long magic, const string why)
  {
   g_brk_rc = 0;
   g_brk_why = "";
   g_brk_gone = false;
   if(!PositionSelectByTicket(ticket))
     {
      g_brk_gone = true;
      return true;
     }
   long pm = PositionGetInteger(POSITION_MAGIC);
   if(!BrkOurMagic(pm))
     {
      g_brk_why = "not_ours";
      return false;
     }
   string gate = "";
   if(!BrkMay(gate))
     {
      g_brk_why = gate;
      return false;
     }
   string nm = PositionGetString(POSITION_SYMBOL);
   int sym = BrkSymOf(nm);
   int sx = CrSleeveOfMagic(pm);
   string code = "-";
   if(sx >= 0) code = g_sl[sx].code;
   else if(pm == CR_MAGIC_MARK) code = "MARK";
   long rm = (magic > 0) ? magic : pm;
   g_trade.SetExpertMagicNumber((ulong)rm);
   g_trade.SetTypeFillingBySymbol(nm);
   g_trade.SetDeviationInPoints(BrkDeviation(sym));
   g_brk_sent++;
   bool ok = g_trade.PositionClose(ticket);
   uint rc = g_trade.ResultRetcode();
   g_brk_rc = rc;
   double px = g_trade.ResultPrice();
   bool still = PositionSelectByTicket(ticket);
   Jrn(CR_EV_CLOSE, code, KI("ticket", (long)ticket) + KI("magic", rm) + KD("px", px) + KV("why", why) + KI("rc", (long)rc)
       + KB("ok", !still));
   if(!still)
     {
      g_brk_gone = !(ok && (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_DONE_PARTIAL));
      return true;
     }
   g_brk_why = (rc == TRADE_RETCODE_MARKET_CLOSED) ? "market_closed" : "refused";
   return false;
  }

// move a position's stop to sl_ask put on the tick grid away from the market (BrkGridStop); true when that stop is in
// place afterwards. A stop is never removed (sl <= 0 refused); a stop on the wrong side of the price or inside
// STOPS_LEVEL is not sent (g_brk_why = stop_side); the broker refuses a move inside FREEZE_LEVEL (10029): the follower
// keeps the old stop and tries again 10 s later.
bool BrkModify(const ulong ticket, const double sl_ask)
  {
   g_brk_rc = 0;
   g_brk_why = "";
   g_brk_gone = false;
   if(!MathIsValidNumber(sl_ask) || !(sl_ask > 0.0))
     {
      g_brk_why = "no_stop";
      return false;
     }
   if(!PositionSelectByTicket(ticket))
     {
      g_brk_gone = true;
      g_brk_why = "gone";
      return false;
     }
   long pm = PositionGetInteger(POSITION_MAGIC);
   if(!BrkOurMagic(pm))
     {
      g_brk_why = "not_ours";
      return false;
     }
   string gate = "";
   if(!BrkMay(gate))
     {
      g_brk_why = gate;
      return false;
     }
   string nm = PositionGetString(POSITION_SYMBOL);
   int sym = BrkSymOf(nm);
   int side = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
   double sl = BrkGridStop(sym, sl_ask, side);
   double cur = PositionGetDouble(POSITION_SL), tp = PositionGetDouble(POSITION_TP);
   double pt = SymbolInfoDouble(nm, SYMBOL_POINT);
   if(!(pt > 0.0)) pt = 0.01;
   if(cur > 0.0 && MathAbs(sl - cur) < pt / 2) return true;   // already in place (the server would answer 10025)
   double bid = 0.0, ask = 0.0;
   datetime tt = 0;
   if(sym < 0 || !BrkQuote(sym, bid, ask, tt))
     {
      g_brk_why = "no_price";
      return false;
     }
   double lvl = (double)SymbolInfoInteger(nm, SYMBOL_TRADE_STOPS_LEVEL) * pt;
   if((side > 0 && !(sl <= bid - lvl && sl < bid)) || (side < 0 && !(sl >= ask + lvl && sl > ask)))
     {
      g_brk_why = "stop_side";
      return false;
     }
   int sx = CrSleeveOfMagic(pm);
   string code = (sx >= 0) ? g_sl[sx].code : "-";
   g_trade.SetExpertMagicNumber((ulong)pm);
   g_brk_sent++;
   bool ok = g_trade.PositionModify(ticket, sl, tp);
   uint rc = g_trade.ResultRetcode();
   g_brk_rc = rc;
   bool done = ok && (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_NO_CHANGES);
   if(!done && !PositionSelectByTicket(ticket)) g_brk_gone = true;
   Jrn(CR_EV_SLMOD, code, KI("ticket", (long)ticket) + KD("from", cur) + KD("to", sl) + KI("rc", (long)rc) + KB("ok", done));
   if(!done) g_brk_why = g_brk_gone ? "gone" : ((rc == TRADE_RETCODE_FROZEN) ? "freeze" : "refused");
   return done;
  }

// every robot position (sleeve magics and the mark), each closed with request magic `magic` (0 = its own); true when
// none is left
bool BrkCloseAll(const long magic, const string why)
  {
   bool all = true;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      long m = PositionGetInteger(POSITION_MAGIC);
      if(!BrkOurMagic(m)) continue;
      if(!BrkClose(t, magic > 0 ? magic : m, why)) all = false;
     }
   return all && BrkRobotCount() == 0;
  }

int BrkFail(const string why)
  {
   g_brk_why = why;
   return CR_SEND_FAIL;
  }

// SPEC 4.3: an intent as a market order with its broker stop sl_ask (see the header). The stop is put on the tick grid
// away from the market first (BrkGridStop: the follower's stops are on it already, so nothing moves for them).
int BrkOpen(CrIntent &it, const double sl_ask)
  {
   g_brk_rc = 0;
   g_brk_why = "";
   g_brk_gone = false;
   g_brk_refused = false;
   g_brk_listed = false;
   g_brk_fill = 0.0;
   g_brk_vol = 0.0;
   g_brk_sl = 0.0;
   g_brk_risk = 0.0;
   it.ticket = 0;
   if(it.sleeve < 0 || it.sleeve >= g_nsl) return BrkFail("sleeve");
   string gate = "";
   if(!BrkMay(gate)) return BrkFail(gate);
   int sym = g_sl[it.sleeve].sym;
   string code = g_sl[it.sleeve].code;
   string nm = g_sym[sym].name;
   if(!BrkConnected()) return BrkFail("no_connection");
   if(!BrkTradeAllowed()) return BrkFail("algo_trading_off");
   if(!BrkHedging()) return BrkFail("not_hedging");
   if(it.side != 1 && it.side != -1) return BrkFail("side");
   double bid = 0.0, ask = 0.0;
   datetime tt = 0;
   if(!BrkQuote(sym, bid, ask, tt)) return BrkFail("no_price");
   if((long)(TimeTradeServer() - tt) > CR_BRK_TICK_AGE) return BrkFail("old_price");
   if(SymbolInfoInteger(nm, SYMBOL_TRADE_MODE) != SYMBOL_TRADE_MODE_FULL) return BrkFail("not_tradable");
   if((SymbolInfoInteger(nm, SYMBOL_ORDER_MODE) & SYMBOL_ORDER_SL) == 0) return BrkFail("no_order_sl");
   double pt = SymbolInfoDouble(nm, SYMBOL_POINT);
   double ts = SymbolInfoDouble(nm, SYMBOL_TRADE_TICK_SIZE);
   double tv = BrkTvl(nm);
   if(!(pt > 0.0) || !(ts > 0.0) || !(tv > 0.0)) return BrkFail("no_tick_value");
   if(!MathIsValidNumber(sl_ask) || !(sl_ask > 0.0)) return BrkFail("no_stop");
   double sl = BrkGridStop(sym, sl_ask, it.side);
   double lvl = (double)SymbolInfoInteger(nm, SYMBOL_TRADE_STOPS_LEVEL) * pt;
   if((it.side > 0 && !(sl <= bid - lvl && sl < bid)) || (it.side < 0 && !(sl >= ask + lvl && sl > ask))) return BrkFail("stop_side");
   double vmin = SymbolInfoDouble(nm, SYMBOL_VOLUME_MIN), vstep = SymbolInfoDouble(nm, SYMBOL_VOLUME_STEP);
   double vmax = SymbolInfoDouble(nm, SYMBOL_VOLUME_MAX);
   if(!(vstep > 0.0)) vstep = vmin;
   if(!MathIsValidNumber(it.lots) || !(it.lots > 0.0) || !(vstep > 0.0)) return BrkFail("volume");
   double price = (it.side > 0) ? ask : bid;
   double want = it.lots;
   double lots = want;
   string cut = "-";
   if(vmax > 0.0 && lots > vmax)
     {
      lots = vmax;
      cut = "vmax";
     }
   double n1 = price / ts * tv;                                // value of one lot (RiskMoney with a stop at 0)
   double bal = AccountInfoDouble(ACCOUNT_BALANCE);
   if(n1 > 0.0 && lots * n1 > CR_BRK_NOTIONAL_X * bal)
     {
      lots = CR_BRK_NOTIONAL_X * bal / n1;
      cut = "notional";
     }
   lots = NormalizeDouble(MathFloor(lots / vstep + 1e-9) * vstep, 8);
   if(!(lots >= vmin)) return BrkFail(cut == "notional" ? "notional" : "volume");
   int spts = BrkSpreadPts(sym, bid, ask);
   double s_paper = (ask - bid) + 2.0 * g_sym[sym].h;
   ulong dev = (ulong)(CR_BRK_DEV_SPREADS * (spts > 0 ? spts : 1));
   string cm = BrkComment(code, (datetime)(it.oid / 100));
   g_trade.SetExpertMagicNumber((ulong)g_sl[it.sleeve].magic);
   g_trade.SetDeviationInPoints(dev);
   g_trade.SetTypeFillingBySymbol(nm);
   g_brk_sent++;
   bool ok = (it.side > 0) ? g_trade.Buy(lots, nm, 0.0, sl, 0.0, cm) : g_trade.Sell(lots, nm, 0.0, sl, 0.0, cm);
   uint rc = g_trade.ResultRetcode();
   g_brk_rc = rc;
   bool done = (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_DONE_PARTIAL);
   bool filled = ok && done;
   bool unknown = !filled && (done || rc == 0 || rc == TRADE_RETCODE_TIMEOUT || rc == TRADE_RETCODE_CONNECTION || rc == TRADE_RETCODE_PLACED);
   string res = filled ? "filled" : (unknown ? "unknown" : "refused");
   Jrn(CR_EV_SEND, code, KI("oid", it.oid) + KI("side", it.side) + KD("lots", lots) + KD("want", want) + KD("sl", sl) + KD("bid", bid)
       + KD("ask", ask) + KT("stamp", it.stamp) + KI("dev", (long)dev) + KV("cut", cut) + KV("result", res) + KI("rc", (long)rc)
       + KI("s_raw", spts) + KD("s_paper", s_paper));
   if(!filled)
     {
      if(unknown)
        {
         g_brk_why = "unknown";
         g_brk_fp_n = -1;                                      // the two stable reads must both come after this answer
         return CR_SEND_UNKNOWN;
        }
      Jrn(CR_EV_REFUSED, code, KI("oid", it.oid) + KV("why", "broker") + KI("rc", (long)rc));
      return BrkFail("refused");
     }
   ulong ticket = g_trade.ResultOrder();                       // hedging: the position ticket is the opening order's ticket
   double fill = g_trade.ResultPrice(), got = g_trade.ResultVolume();
   bool seen = (ticket > 0 && PositionSelectByTicket(ticket));  // (MT5 may list it a moment later)
   double sl_listed = 0.0;
   if(seen)
     {
      fill = PositionGetDouble(POSITION_PRICE_OPEN);
      got = PositionGetDouble(POSITION_VOLUME);
      sl_listed = PositionGetDouble(POSITION_SL);
     }
   if(!(fill > 0.0)) fill = price;
   if(!(got > 0.0)) got = lots;
   it.ticket = ticket;
   string bad = "";
   if(seen && !(sl_listed > 0.0))                               // the broker did not keep the stop: put it back
     {
      if(BrkModify(ticket, sl)) sl_listed = sl;
      else bad = "no_sl";
     }
   double sl_eff = (sl_listed > 0.0) ? sl_listed : sl;
   double risk = BrkRiskMoney(sym, it.side, fill, sl_eff, got);
   if(bad == "" && it.budget > 0.0 && risk > CR_BRK_RISK_X * it.budget) bad = "risk";
   g_brk_fill = fill;
   g_brk_vol = got;
   g_brk_sl = sl_eff;
   g_brk_risk = risk;
   g_brk_listed = seen;
   Jrn(CR_EV_FILL, code, KI("oid", it.oid) + KI("ticket", (long)ticket) + KI("side", it.side) + KD("px", fill) + KD("lots", got)
       + KD("sl", sl_eff) + KB("listed", seen) + KD("risk", risk) + KD("budget", it.budget) + KT("stamp", it.stamp) + KI("s_raw", spts)
       + KD("s_paper", s_paper));
   if(bad != "")
     {
      g_brk_refused = true;
      g_brk_why = bad;
      Jrn(CR_EV_REFUSED, code, KI("oid", it.oid) + KI("ticket", (long)ticket) + KV("why", bad) + KD("risk", risk) + KD("budget", it.budget)
          + KD("limit", CR_BRK_RISK_X * it.budget));
      JrnPush("REFUSED " + code + " : position " + IntegerToString((long)ticket) + " refermee (" + bad + ", risque "
              + DoubleToString(risk, 2) + " pour " + DoubleToString(CR_BRK_RISK_X * it.budget, 2) + ")", true);
      if(seen) BrkClose(ticket, g_sl[it.sleeve].magic, "refused_" + bad);
      g_brk_why = bad;                                         // (the close above reset it; g_brk_rc keeps the close's answer)
     }
   return CR_SEND_OK;
  }

// the guard's mark (SPEC 6.2): one minimum lot opened and closed at once with magic 20261290 and a broker stop 1 % away,
// on symbol sym; true when the opening deal exists (the close is retried by the guard's close-all when it fails)
bool BrkMark(const int sym, string &why)
  {
   why = "";
   g_brk_rc = 0;
   if(!BrkMay(why)) return false;
   if(!BrkConnected())
     {
      why = "no_connection";
      return false;
     }
   if(!BrkTradeAllowed())
     {
      why = "algo_trading_off";
      return false;
     }
   double bid = 0.0, ask = 0.0;
   datetime tt = 0;
   if(!BrkQuote(sym, bid, ask, tt))
     {
      why = "no_price";
      return false;
     }
   if((long)(TimeTradeServer() - tt) > CR_BRK_TICK_AGE)
     {
      why = "market_closed";
      return false;
     }
   string nm = g_sym[sym].name;
   double vmin = SymbolInfoDouble(nm, SYMBOL_VOLUME_MIN);
   double sl = BrkGridStop(sym, bid * 0.99, 1);
   g_trade.SetExpertMagicNumber((ulong)CR_MAGIC_MARK);
   g_trade.SetTypeFillingBySymbol(nm);
   g_trade.SetDeviationInPoints(BrkDeviation(sym));
   g_brk_sent++;
   bool ok = g_trade.Buy(vmin, nm, 0.0, sl, 0.0, "CR MARK");
   uint rc = g_trade.ResultRetcode();
   g_brk_rc = rc;
   bool filled = ok && (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_DONE_PARTIAL);
   ulong t = filled ? g_trade.ResultOrder() : 0;
   bool closed = false;
   if(filled && t > 0)
     {
      g_trade.SetExpertMagicNumber((ulong)CR_MAGIC_MARK);
      g_brk_sent++;
      bool c = g_trade.PositionClose(t);
      closed = c && !PositionSelectByTicket(t);
     }
   Jrn(CR_EV_MARK, g_sym[sym].base, KI("ticket", (long)t) + KD("lots", vmin) + KD("sl", sl) + KI("rc", (long)rc) + KB("open", filled)
       + KB("closed", closed));
   if(!filled) why = "refused";
   return filled;
  }
#endif
