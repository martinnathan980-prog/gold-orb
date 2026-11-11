// What SondeFP.mq5 needs on top of the working imitation of MetaTrader in mock_mains.h (terminal, broker, deals, CTrade),
// so that the real code of the script can be RUN here (check/test_sonde.py). mock_mains.h is included unchanged.
// It is NOT MetaTrader: see "What this cannot prove" in test_sonde.py.
//
// Added here:
//   Sleep(ms)                  a VIRTUAL clock: nothing waits, the clock jumps; while the script "sleeps" the world moves
//                              (timeline below, stops hit by the broker, the terminal's list of positions refreshed)
//   HistorySelectByPosition    the deals of one position identifier, as far as the terminal has received them
//   CTrade::PositionClose(symbol)  transcribed from Trade.mqh (2000-2025), ref copy in lab/audit/scratch/.../ref_trade_mqh/T.mqh
//   AccountInfoInteger(ACCOUNT_TRADE_MODE)  demo / contest / real
//   OrderSend                  a layer in front of the broker of mock_mains.h (per-symbol refusals, closes refused N times,
//                              "placed" answers without price)
// Extra keys of _mock/control.txt (the keys of mock_mains.h still work: retcode_open, retcode_close, drop_sl, lag, stopped,
// terminal_trade_allowed, mql_trade_allowed, margin_mode, price.<symbol>, sym.<symbol>.<prop>, do.<n>=...):
//   account_trade_mode=0|1|2        ACCOUNT_TRADE_MODE_DEMO / _CONTEST / _REAL                       (default 0)
//   history_delay_ms=N              a deal appears in the terminal's history N virtual ms after the broker made it
//   history_delay_out_ms=N          same, exit deals only (the entry deal is there at once)
//   close_fails=N                   the first N close requests of the run are refused with close_fail_retcode (10021)
//   placed=1                        a market order that is filled is answered 10008 "placed" with price 0 and deal 0
//                                   (ASSUMPTION about what such an answer looks like; the order ticket is given)
//   no_order_ticket=1               a filled market order is answered with order = 0 (ASSUMPTION, worst case)
//   x.<symbol>.retcode_open=R       this symbol only: every opening request is answered R (10018 = market closed)
//   x.<symbol>.retcode_close=R      this symbol only: every close request is answered R
//   x.<symbol>.commission_lot=V / fee_lot=V / tick_size=V       broker settings mock_mains.h has no control key for
//   x.<symbol>.first_tick_ms=N      SymbolInfoTick fails for this symbol until the virtual clock reaches N (a market just
//                                   added to Market Watch has no quote yet; ASSUMPTION, the documentation does not say)
//   at.<ms>=<key>=<value>           when the virtual clock reaches <ms>, the line <key>=<value> is added to the control
//                                   (prices that move while the position is open, a market that reopens, stopped=1 ...)
// The log (_mock/log.txt) also gets: "SLEEP ms now", "HISTORY position visible/total", "SONDE ..." for every answer made here.
#pragma once
#define MOCK_MAINS_NO_MAIN
#include "mql5_shim.h"
// mock_mains.h defines AccountInfoInteger, SymbolInfoTick and OrderSend; they are renamed while it is read, so that the
// versions below stand in front of them. CTrade (in mock_mains.h) calls OrderSend(mk_req, mk_res) with two non-const objects: the overload
// declared here, taking a non-const request, is the better match, so every request of CTrade passes through it first.
bool mk_base_OrderSend(MqlTradeRequest &req, MqlTradeResult &res);
#define AccountInfoInteger mk_base_AccountInfoInteger
#define OrderSend mk_base_OrderSend
#define SymbolInfoTick mk_base_SymbolInfoTick
#include "mock_mains.h"
#undef AccountInfoInteger
#undef SymbolInfoTick
#undef OrderSend

// ------------------------------------------------------------------ handlers of an Expert Advisor (unused by a script)
void OnTradeTransaction(const MqlTradeTransaction &, const MqlTradeRequest &, const MqlTradeResult &) {}

// ------------------------------------------------------------------ state added here
static long   sd_now_ms = 0;                       // virtual clock
static long   sd_trade_mode = 0, sd_hist_delay = 0, sd_hist_delay_out = 0, sd_close_fails = 0, sd_close_fail_rc = 10021;
static bool   sd_placed = false, sd_no_order = false;
static long   sd_close_requests = 0, sd_sleeps = 0;
static std::map<ulong, long> sd_born;              // deal -> virtual ms at which the broker made it
static std::map<string, uint> sd_rc_open, sd_rc_close;
static std::map<string, long> sd_first_tick;
static std::map<long, std::vector<string>> sd_timeline;
static std::vector<string> sd_extra;               // control lines added by the timeline
static string sd_control_seen = "\x01";

static void sd_note_deals()
  {
   for(const MkDeal &d : mk_deals)
      if(!sd_born.count(d.deal)) sd_born[d.deal] = sd_now_ms;
  }
// reads the control file through mock_mains.h, then the keys added here
static void sd_apply_control(bool first)
  {
   string raw;
   if(!mk_read(mk_path("_mock/control.txt"), raw)) raw = "";
   mk_apply_control();
   sd_trade_mode = 0; sd_hist_delay = sd_hist_delay_out = 0; sd_close_fails = 0; sd_close_fail_rc = 10021;
   sd_placed = sd_no_order = false;
   sd_rc_open.clear(); sd_rc_close.clear(); sd_first_tick.clear();
   for(const string &ln0 : mk_split(raw, '\n'))
     {
      string ln = ln0;
      StringTrimRight(ln);
      size_t p = ln.find('=');
      if(p == string::npos || p == 0) continue;
      string k = ln.substr(0, p), v = ln.substr(p + 1);
      if(k == "account_trade_mode") sd_trade_mode = atol(v.c_str());
      else if(k == "history_delay_ms") sd_hist_delay = atol(v.c_str());
      else if(k == "history_delay_out_ms") sd_hist_delay_out = atol(v.c_str());
      else if(k == "close_fails") sd_close_fails = atol(v.c_str());
      else if(k == "close_fail_retcode") sd_close_fail_rc = atol(v.c_str());
      else if(k == "placed") sd_placed = atoi(v.c_str()) != 0;
      else if(k == "no_order_ticket") sd_no_order = atoi(v.c_str()) != 0;
      else if(k.compare(0, 3, "at.") == 0 && first) sd_timeline[atol(k.c_str() + 3)].push_back(v);
      else if(k.compare(0, 2, "x.") == 0)
        {
         size_t dot = k.rfind('.');
         string name = k.substr(2, dot - 2), prop = k.substr(dot + 1);
         if(prop == "retcode_open") sd_rc_open[name] = (uint)atol(v.c_str());
         else if(prop == "retcode_close") sd_rc_close[name] = (uint)atol(v.c_str());
         else if(prop == "first_tick_ms") sd_first_tick[name] = atol(v.c_str());
         for(int i = 0; i < MK_NSYM; i++)
           {
            if(mk_sym[i].name != name) continue;
            if(prop == "commission_lot") mk_sym[i].commission_lot = atof(v.c_str());
            else if(prop == "fee_lot") mk_sym[i].fee_lot = atof(v.c_str());
            else if(prop == "tick_size") mk_sym[i].tick_size = atof(v.c_str());
           }
        }
     }
  }
// what happens in the world while the script is not looking
static void sd_world_step()
  {
   sd_note_deals();
   mk_broker_tick();                               // stops and targets hit at the current prices
   sd_note_deals();
   mk_view = mk_pos;                               // the terminal has received the trade events
  }
static void sd_timeline_until(long end_ms)
  {
   while(!sd_timeline.empty() && sd_timeline.begin()->first <= end_ms)
     {
      sd_now_ms = std::max(sd_now_ms, sd_timeline.begin()->first);
      string raw;
      mk_read(mk_path("_mock/control.txt"), raw);
      for(const string &ln : sd_timeline.begin()->second)
        {
         raw += ln + "\n";
         mk_log("SONDE", mk_fmt("timeline at %ld ms: ", sd_now_ms) + ln);
        }
      sd_timeline.erase(sd_timeline.begin());
      mk_write("_mock/control.txt", raw);
      sd_apply_control(false);
      sd_world_step();
     }
  }

// ------------------------------------------------------------------ built-ins mock_mains.h does not have
// Sleep (docs: "suspends execution of the current Expert Advisor or script"; a script being removed is not delayed)
void Sleep(int milliseconds)
  {
   sd_sleeps++;
   sd_note_deals();
   if(mk_stopped) { mk_log("SLEEP", mk_fmt("%d (stopped: returns at once) now=%ld", milliseconds, sd_now_ms)); return; }
   long end = sd_now_ms + (milliseconds > 0 ? milliseconds : 0);
   sd_timeline_until(end);
   sd_now_ms = end;
   sd_world_step();
   mk_log("SLEEP", mk_fmt("%d now=%ld", milliseconds, sd_now_ms));
  }
long AccountInfoInteger(ENUM_ACCOUNT_INFO_INTEGER p)
  {
   if(p == ACCOUNT_TRADE_MODE) return sd_trade_mode;
   return mk_base_AccountInfoInteger(p);
  }
bool SymbolInfoTick(const string name, MqlTick &k)
  {
   auto it = sd_first_tick.find(name);
   if(it != sd_first_tick.end() && sd_now_ms < it->second) { k = MqlTick(); return false; }
   return mk_base_SymbolInfoTick(name, k);
  }
// docs: "Retrieves the history of deals and orders having the specified position identifier"
// (a position identifier is the ticket of the order that opened the position; here MkPos.ident / MkDeal.position)
bool HistorySelectByPosition(long position_id)
  {
   sd_note_deals();
   mk_hist.clear();
   int all = 0;
   for(int i = 0; i < (int)mk_deals.size(); i++)
     {
      const MkDeal &d = mk_deals[i];
      if((long)d.position != position_id) continue;
      all++;
      long delay = sd_hist_delay + (d.entry != 0 ? sd_hist_delay_out : 0);
      if(sd_born[d.deal] + delay <= sd_now_ms) mk_hist.push_back(i);
     }
   mk_log("HISTORY", mk_fmt("position %ld: %d of %d deals visible at %ld ms", position_id, (int)mk_hist.size(), all, sd_now_ms));
   return true;
  }

// ------------------------------------------------------------------ in front of the broker
bool mk_base_OrderSend(MqlTradeRequest &req, MqlTradeResult &res)
  {
   const MqlTradeRequest &creq = req;
   bool is_deal = req.action == TRADE_ACTION_DEAL, is_close = is_deal && req.position != 0, is_open = is_deal && req.position == 0;
   uint forced = 0;
   if(is_close)
     {
      sd_close_requests++;
      if(sd_close_requests <= sd_close_fails) forced = (uint)sd_close_fail_rc;
      else if(sd_rc_close.count(req.symbol)) forced = sd_rc_close[req.symbol];
     }
   else if(is_open && sd_rc_open.count(req.symbol)) forced = sd_rc_open[req.symbol];
   if(forced && mk_term_allowed && mk_mql_allowed)
     {
      res = MqlTradeResult();
      MkSym *s = mk_find(req.symbol);
      bool ret = mk_answer(res, forced, s);
      mk_log("SONDE", mk_fmt("%s %s position=%lu volume=%.8g sl=%.10g -> retcode=%u (answer made by mock_sonde.h) ret=%d",
                             is_close ? "close" : "open", req.symbol.c_str(), req.position, req.volume, req.sl, forced, ret ? 1 : 0));
      return ret;
     }
   bool ret = mk_base_OrderSend(creq, res);
   if(ret && is_open && res.retcode == MK_DONE)
     {
      if(sd_placed) { res.retcode = MK_PLACED; res.price = 0.0; res.deal = 0; mk_log("SONDE", "the answer is turned into 10008 placed, price 0, deal 0"); }
      if(sd_no_order) { res.order = 0; mk_log("SONDE", "the answer is given without the order ticket"); }
     }
   sd_note_deals();
   return ret;
  }

// ------------------------------------------------------------------ CTrade::PositionClose(symbol), from Trade.mqh
static bool sd_select_position(const string &symbol)          // CTrade::SelectPosition
  {
   if(mk_hedging())
     {
      for(const MkPos &p : mk_view)                           // PositionGetSymbol(i) selects the position
        {
         mk_selected = p.ticket;
         if(p.symbol == symbol && (long)mk_magic == p.magic) return true;
        }
      return false;
     }
   for(const MkPos &p : mk_view)                              // PositionSelect(symbol)
      if(p.symbol == symbol) { mk_selected = p.ticket; return true; }
   return false;
  }
bool CTrade::PositionClose(const string symbol, const ulong deviation)
  {
   bool partial_close = false;
   int  retry_count = 10;
   uint retcode = MK_REJECT;
   if(IsStopped()) { mk_res.retcode = MK_CLIENT_DISABLES_AT; return false; }
   mk_clear();
   if(!mk_filling_check(symbol)) return false;
   do
     {
      if(sd_select_position(symbol))
        {
         if((ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) { mk_req.type = ORDER_TYPE_SELL; mk_req.price = SymbolInfoDouble(symbol, SYMBOL_BID); }
         else { mk_req.type = ORDER_TYPE_BUY; mk_req.price = SymbolInfoDouble(symbol, SYMBOL_ASK); }
        }
      else
        {
         mk_res.retcode = retcode;                            // position not found
         return false;
        }
      mk_req.action = TRADE_ACTION_DEAL; mk_req.symbol = symbol; mk_req.volume = PositionGetDouble(POSITION_VOLUME);
      mk_req.magic = mk_magic; mk_req.deviation = (deviation == ULONG_MAX) ? mk_deviation : deviation;
      mk_req.position = (ulong)PositionGetInteger(POSITION_TICKET);
      double max_volume = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
      if(mk_req.volume > max_volume) { mk_req.volume = max_volume; partial_close = true; }
      else partial_close = false;
      if(mk_hedging()) return mk_base_OrderSend(mk_req, mk_res);
      if(!mk_base_OrderSend(mk_req, mk_res))
        {
         if(--retry_count != 0) continue;
         if(retcode == MK_DONE_PARTIAL) mk_res.retcode = retcode;
         return false;
        }
      retcode = MK_DONE_PARTIAL;
      if(partial_close) Sleep(1000);
     }
   while(partial_close);
   return true;
  }

// ------------------------------------------------------------------ one run of the script
static int sd_run(void (*on_start)())
  {
   const char *root = getenv("MOCK_FILES");
   mk_root = root ? root : ".";
   mkdir(mk_path("_mock").c_str(), 0755);
   for(int i = 0; i < MK_NSYM; i++) mk_sym[i] = MK_DEFAULTS[i];
   if(const char *e = getenv("MOCK_MISSING"))
      for(const string &m : mk_split(e, ','))
         for(int i = 0; i < MK_NSYM; i++)
            if(mk_sym[i].name == m) mk_sym[i].hidden = true;
   mk_load_state();
   sd_apply_control(true);
   sd_note_deals();
   for(auto &kv : sd_born) kv.second = -1000000000;          // deals made before the run are in the history
   mk_log("MOCK", "start");
   on_start();
   mk_view = mk_pos;
   mk_save_state();
   mk_log("MOCK", mk_fmt("end now=%ld sleeps=%ld close_requests=%ld", sd_now_ms, sd_sleeps, sd_close_requests));
   return 0;
  }
