// T9 execution: CR_Broker, CR_Guards and CR_Ledger (SPEC 4.3, 4.4, 4.9, 5, 6; step J) in the replay mock's broker
// build: entry=src/CR_Guards.mqh sanitize
//
// Modes:
//   test_exec [DIR]          every unit world below (journals under DIR, default check/out/test_exec); exit 0 when every
//                            check holds
//   test_exec hands [DIR]    the same worlds, then one line per test of the hands (lab/live_ai/check/test_mains.py) that
//                            SPEC 7 T9 ports: "HANDS <id> PASS|FAIL|PART <what is checked>" (check/test_hands_port.py
//                            reads them). Built with -DCR_EXEC_SIZING (test_hands_port.py does it: an entry that also
//                            includes CR_Sizing.mqh) the sizing ports O8-O11 run too.
// The worlds drive the EA's own functions (translated src/CR_Broker.mqh, CR_Guards.mqh, CR_Ledger.mqh, CR_Clock.mqh,
// CR_Journal.mqh) against the mock's broker: positions, orders, deals, payments, the fault hooks of mock_faults.h.
#include "mock_replay.h"
// Test doubles for what the mock answers with constants: the terminal's and the EA's Algo Trading flags, the symbol's
// trade mode and order mode, a tick size (and tick value) other than the point, the digits. Only the EA's calls are
// redirected (the macros come after the mock and before ea.cpp); a property not set here gets the mock's answer.
static std::map<std::pair<string, int>, long> x_sym_i;
static std::map<std::pair<string, int>, double> x_sym_d;
static std::map<int, int> x_term_i, x_mql_i;
static long x_SymbolInfoInteger(const string name, ENUM_SYMBOL_INFO_INTEGER p)
  {
   auto it = x_sym_i.find({name, (int)p});
   return it != x_sym_i.end() ? it->second : SymbolInfoInteger(name, p);
  }
static double x_SymbolInfoDouble(const string name, ENUM_SYMBOL_INFO_DOUBLE p)
  {
   auto it = x_sym_d.find({name, (int)p});
   return it != x_sym_d.end() ? it->second : SymbolInfoDouble(name, p);
  }
static int x_TerminalInfoInteger(ENUM_TERMINAL_INFO_INTEGER p)
  {
   auto it = x_term_i.find((int)p);
   return it != x_term_i.end() ? it->second : TerminalInfoInteger(p);
  }
static int x_MQLInfoInteger(ENUM_MQL_INFO_INTEGER p)
  {
   auto it = x_mql_i.find((int)p);
   return it != x_mql_i.end() ? it->second : MQLInfoInteger(p);
  }
#define SymbolInfoInteger x_SymbolInfoInteger
#define SymbolInfoDouble x_SymbolInfoDouble
#define TerminalInfoInteger x_TerminalInfoInteger
#define MQLInfoInteger x_MQLInfoInteger
#include "ea.cpp"
#undef SymbolInfoInteger
#undef SymbolInfoDouble
#undef TerminalInfoInteger
#undef MQLInfoInteger
#include <cmath>
#include <cstdarg>
#include <map>
#include <string>
#include <vector>

// ------------------------------------------------------------------ rows (as CR_Registry RegInit; the mock's specs)
struct XSym { const char *name, *base, *lab; int family; double mkt, stop, units, vmin, vstep, lev; };
static const XSym X_SYM[CR_NSYM] = {
   {"XAUUSD.r", "XAUUSD", "xauusd", CR_FAM_XAU, 0.3, 1.0, 100.0, 0.01, 0.01, 500.0},
   {"US100.r", "US100", "us100", CR_FAM_IDX, 0.2, 0.5, 1.0, 0.1, 0.1, 200.0},
   {"BTCUSD.r", "BTCUSD", "btcusd", CR_FAM_CRY, 0.5, 1.5, 1.0, 0.01, 0.01, 50.0},
   {"ETHUSD.r", "ETHUSD", "ethusd", CR_FAM_CRY, 0.7, 2.0, 1.0, 0.01, 0.01, 50.0}};
struct XSl { int id; const char *code, *lab; int sym; };
static const XSl X_SL[10] = {{1, "N30", "noise30_us100", CR_IDX}, {2, "OC4", "ocm4_us100", CR_IDX}, {3, "BKB", "brk72_24h_wd_btcusd", CR_BTC},
                             {4, "BKE", "brk72_24h_wd_ethusd", CR_ETH}, {5, "F1B", "F1_brk_ridge_filter_btcusd", CR_BTC},
                             {6, "F1E", "F1_brk_ridge_filter_ethusd", CR_ETH}, {7, "NQB", "nq_btc_follow_btcusd", CR_BTC},
                             {8, "GFP", "GOLD_FRI_PM_xauusd", CR_XAU}, {9, "D4H", "donch4h_stop_xauusd", CR_XAU},
                             {10, "ORX", "orb_asia_2d_buf10_xauusd", CR_XAU}};

// ------------------------------------------------------------------ checks
static int g_checks = 0, g_fails = 0;
static string g_world = "";
static std::map<string, int> g_wfail;                // failures per world
static string F(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
static string F(const char *fmt, ...)
  {
   char b[2048];
   va_list ap;
   va_start(ap, fmt);
   vsnprintf(b, sizeof b, fmt, ap);
   va_end(ap);
   return b;
  }
static bool ck(bool c, const string &what)
  {
   g_checks++;
   if(!c)
     {
      g_fails++;
      g_wfail[g_world]++;
      fprintf(stderr, "FAIL [%s] %s\n", g_world.c_str(), what.c_str());
     }
   return c;
  }
static bool cknear(double got, double want, double tol, const string &what)
  {
   return ck(std::fabs(got - want) <= tol, what + F(": got %.17g, want %.17g", got, want));
  }

// ------------------------------------------------------------------ the world
static string g_dir = "check/out/test_exec";

static long SV(int y, int mo, int d, int h, int mi, int s)        // a server wall-clock time
  {
   struct tm t = {};
   t.tm_year = y - 1900;
   t.tm_mon = mo - 1;
   t.tm_mday = d;
   t.tm_hour = h;
   t.tm_min = mi;
   t.tm_sec = s;
   return (long)timegm(&t);
  }

static void x_rows()
  {
   for(int s = 0; s < CR_NSYM; s++)
     {
      g_sym[s].base = X_SYM[s].base;
      g_sym[s].lab = X_SYM[s].lab;
      g_sym[s].name = X_SYM[s].name;
      g_sym[s].family = X_SYM[s].family;
      g_sym[s].digits = 2;
      g_sym[s].point = 0.01;
      g_sym[s].comm_pts = 0;
      g_sym[s].h = 0.0;
      g_sym[s].slip_mkt = X_SYM[s].mkt * 1e-4;
      g_sym[s].slip_stop = X_SYM[s].stop * 1e-4;
      g_sym[s].depth_days = 60;
      g_sym[s].model_bp = 1.0;
      g_sym[s].ok = true;
     }
   g_nsl = 0;
   for(int k = 0; k < 10; k++)
     {
      CrSleeveInfo &r = g_sl[g_nsl];
      r.id = X_SL[k].id;
      r.code = X_SL[k].code;
      r.lab = X_SL[k].lab;
      r.kind = CR_K_SCRIPT;
      r.slot = k;
      r.sym = X_SL[k].sym;
      r.sym2 = -1;
      r.change = CR_CH_NONE;
      r.factor_on = 1.0;
      r.refuse_on = CR_REF_NONE;
      r.change_on = false;
      r.allowed = true;
      r.magic = CR_MAGIC_BASE + X_SL[k].id;
      g_nsl++;
     }
  }

// a fresh terminal, broker, configuration, ledger, broker gate and guards at server time now_srv
static void x_reset(const string &world, long now_srv, double balance, bool demo = true)
  {
   g_world = world;
   JrnClose();
   rp_root = g_dir + "/" + world;
   rp_mkdirs(rp_path("ClaudeRobot"));
   rp_mkdirs(rp_path("_mock"));
   if(DIR *d = opendir(rp_path("ClaudeRobot").c_str()))
     {
      std::vector<string> old;
      while(dirent *e = readdir(d))
         if(strstr(e->d_name, ".log")) old.push_back(rp_path("ClaudeRobot") + "/" + e->d_name);
      closedir(d);
      for(const string &p : old) remove(p.c_str());
     }
   if(rp_log) fclose(rp_log);
   rp_log = fopen(rp_path("_mock/log.txt").c_str(), "w");
   rp_deals.clear();
   rp_orders.clear();
   rp_pays.clear();
   rp_pos.clear();
   rp_tx.clear();
   rp_scripted.clear();
   rp_open_orders.clear();
   rp_gv.clear();
   rp_gv_time.clear();
   rp_gv_temp.clear();
   mf_acts.clear();
   mf_hidden.clear();
   mf_late.clear();
   mf_sess.clear();
   mf_disc_until = 0;
   mf_beat_until = 0;
   x_sym_i.clear();
   x_sym_d.clear();
   x_term_i.clear();
   x_mql_i.clear();
   rp_balance = balance;
   rp_now = now_srv;
   rp_ms = 0;
   rp_next_ticket = 70000001;
   rp_next_deal = 80000001;
   rp_account_mode = demo ? ACCOUNT_TRADE_MODE_DEMO : ACCOUNT_TRADE_MODE_REAL;
   rp_gmt_shift = 0;
   rp_tester = 0;
   rp_stop_magic0 = 0;
   rp_pushes = 0;
   rp_syms.clear();
   for(int s = 0; s < CR_NSYM; s++)
     {
      RpSym x;
      x.name = X_SYM[s].name;
      x.units = X_SYM[s].units;
      x.vmin = X_SYM[s].vmin;
      x.vstep = X_SYM[s].vstep;
      x.lev = X_SYM[s].lev;
      x.slip_mkt = X_SYM[s].mkt * 1e-4;
      x.slip_stop = X_SYM[s].stop * 1e-4;
      x.comm = 0.0;
      rp_syms.push_back(x);
     }
   g_cfg = CrConfig();
   g_cfg.harness = true;
   g_cfg.push = true;
   g_cfg.demo = demo;
   g_cfg.trade = true;
   g_cfg.plan_start = 0;
   g_cfg.risk_table = "0:3;3000:2;6000:1;12000:0.5";
   g_cfg.stop_fall_pct = 25.0;
   g_cfg.stop_arm_paid = 12000.0;
   g_cfg.selftest_ok = true;
   x_rows();
   g_push_sec = 0;
   g_push_min = 0;
   g_push_n = 0;
   g_push_m = 0;
   JrnInit();
   string err;
   double from[] = {0.0}, pct[] = {1.0};
   MqlArray<double> f, p;
   f.v.assign(from, from + 1);
   p.v.assign(pct, pct + 1);
   LedSetRates(f, p, 1);
   bool ok = LedInit(err);
   if(ok) ok = BrkInit(err);
   if(ok) ok = GrdInit(err);
   ck(ok, "reset: " + err);
  }

// symbol s quotes bid with a spread of `spread` points, its last tick at server time t (default now)
static void x_quote(int s, double bid, int spread, long t = -1)
  {
   RpSym &x = rp_syms[s];
   MqlRates b = MqlRates();
   b.time = (t < 0 ? rp_now : t) - ((t < 0 ? rp_now : t) % 60);
   b.open = b.high = b.low = b.close = bid;
   b.spread = spread;
   b.tick_volume = 1;
   x.bars.assign(1, b);
   x.cur = 0;
   x.stage = 1;
   x.tick_bid = bid;
   x.vis_h = x.vis_l = bid;
   x.tick_time = t < 0 ? rp_now : t;
  }

// symbol s quoted in steps of ts (tick value to match: ts x units x 0.89 EUR a lot), optionally with `digits` digits
static void x_tick(int s, double ts, int digits = -1)
  {
   string nm = X_SYM[s].name;
   double tv = ts * X_SYM[s].units * rp_usdeur;
   x_sym_d[{nm, (int)SYMBOL_TRADE_TICK_SIZE}] = ts;
   x_sym_d[{nm, (int)SYMBOL_TRADE_TICK_VALUE}] = tv;
   x_sym_d[{nm, (int)SYMBOL_TRADE_TICK_VALUE_LOSS}] = tv;
   if(digits >= 0) x_sym_i[{nm, (int)SYMBOL_DIGITS}] = digits;
  }

static void x_at(long t_srv)
  {
   rp_now = t_srv;
   rp_book_payments(rp_now);
   rp_book_scripted(rp_now);
   rp_deliver_tx();
  }

static CrIntent x_intent(const string &code, int side, double lots, double budget = 0.0, long stamp_utc = 0)
  {
   CrIntent it = CrIntent();
   it.sleeve = CrSleeveOfCode(code);
   it.stamp = stamp_utc ? stamp_utc : (long)ClkServerToUtc(rp_now) - ((long)ClkServerToUtc(rp_now) % 60);
   it.oid = (long)it.stamp * 100 + (it.sleeve >= 0 ? g_sl[it.sleeve].id : 0);
   it.side = side;
   it.etype = CR_ET_MARKET;
   it.send_until = it.stamp + 300;
   it.lots = lots;
   it.budget = budget;
   return it;
  }

static void x_fault(const string &what, const std::vector<string> &args)   // a request modifier due now (n as mf_init reads it)
  {
   MfAct a;
   a.t = 0;
   a.what = what;
   a.a = args;
   if(what == "refuse_open" || what == "refuse_close" || what == "refuse_sltp") a.left = (int)mf_arg(a, 1, 1);
   else if(what == "timeout_open_done" || what == "timeout_open_none" || what == "dup_open") a.left = (int)mf_arg(a, 0, 1);
   else if(what == "slow_open" || what == "drop_sl" || what == "deal_future") a.left = (int)mf_arg(a, 1, 1);
   mf_acts.push_back(a);
  }

static size_t x_requests() { return rp_orders.size(); }      // every request leaves a history order (FILLED or REJECTED)
static long x_count(const string &ev)                         // journal lines of an event in this world
  {
   long n = 0;
   if(DIR *d = opendir(rp_path("ClaudeRobot").c_str()))
     {
      while(dirent *e = readdir(d))
        {
         if(!strstr(e->d_name, ".log")) continue;
         FILE *f = fopen((rp_path("ClaudeRobot") + "/" + e->d_name).c_str(), "r");
         if(!f) continue;
         char line[4096];
         string key = "|" + ev + "|";
         FileFlush(g_jrn_h);
         while(fgets(line, sizeof line, f))
            if(strstr(line, key.c_str())) n++;
         fclose(f);
        }
      closedir(d);
     }
   return n;
  }
static long x_pushes_with(const string &txt)
  {
   fflush(rp_log);
   FILE *f = fopen(rp_path("_mock/log.txt").c_str(), "r");
   if(!f) return 0;
   long n = 0;
   char line[4096];
   while(fgets(line, sizeof line, f))
      if(strncmp(line, "PUSH ", 5) == 0 && strstr(line, txt.c_str())) n++;
   fclose(f);
   return n;
  }
static ulong x_hand(int s, int side, double vol, long magic = 777, double sl = 0.0)   // a position opened by hand / another robot
  {
   double bid = rp_syms[s].tick_bid, ask = rp_ask(rp_syms[s], bid, rp_syms[s].bars[0].spread);
   double px = side > 0 ? ask : bid;
   ulong ord = rp_add_order(rp_syms[s].name, side > 0 ? 0 : 1, ORDER_STATE_FILLED, 0, magic, vol, px, sl, 0.0, "hand");
   RpPos p = {ord, rp_syms[s].name, side > 0 ? 0 : 1, vol, px, sl, 0.0, magic, rp_now, "hand"};
   rp_pos.push_back(p);
   rp_add_deal(p, p.type, DEAL_ENTRY_IN, vol, px, DEAL_REASON_CLIENT, magic, rp_now, 0.0, 0.0, ord, "hand");
   rp_deliver_tx();
   return ord;
  }
static bool x_listed(ulong t) { return rp_pos_index(t) >= 0; }
static double x_sl(ulong t) { long i = rp_pos_index(t); return i >= 0 ? rp_pos[i].sl : -1.0; }

// ------------------------------------------------------------------ hands results (T9)
struct XHand { string id, what; int state; };                 // state 1 pass, 0 fail, 2 partial (a check the mock cannot make)
static std::vector<XHand> g_hands;
static void hand(const string &id, bool ok, const string &what, bool partial = false)
  {
   g_hands.push_back({id, what, ok ? (partial ? 2 : 1) : 0});
   ck(ok, "hands " + id + ": " + what);
  }

//+------------------------------------------------------------------+
//| Broker: GridStop, Resolve, comment                               |
//+------------------------------------------------------------------+
static void w_grid()
  {
   x_reset("grid", SV(2021, 6, 15, 10, 0, 0), 1000.0);
   struct GV { double x; int side; double ts; int dg; double want; };
   GV v[] = {{1234.567, 1, 0.01, 2, 1234.56}, {1234.561, -1, 0.01, 2, 1234.57}, {1234.56, 1, 0.01, 2, 1234.56}, {1234.56, -1, 0.01, 2, 1234.56},
             {24950.10, 1, 0.25, 2, 24950.0}, {24950.10, -1, 0.25, 2, 24950.25}, {25100.13, -1, 0.25, 2, 25100.25}, {24950.25, 1, 0.25, 2, 24950.25},
             {101.74, 1, 0.5, 1, 101.5}, {101.26, -1, 0.5, 1, 101.5}, {1.0, 1, 0.03, 2, 0.99}, {1.0, -1, 0.03, 2, 1.02}, {0.99, 1, 0.03, 2, 0.99},
             {36999.995, 1, 0.01, 2, 36999.99}, {36999.995, -1, 0.01, 2, 37000.0}};
   bool all = true;
   for(const GV &g : v)
     {
      double got = BrkGridOf(g.x, g.side, g.ts, g.dg);
      bool ok = std::fabs(got - g.want) < 1e-9 && std::fabs(got / g.ts - std::round(got / g.ts)) < 1e-6;
      bool away = g.side > 0 ? got <= g.x + 1e-12 && g.x - got < g.ts : got >= g.x - 1e-12 && got - g.x < g.ts;
      all &= ck(ok && away, F("GridStop(%.4f, %d, tick %.2f) = %.4f, want %.4f", g.x, g.side, g.ts, got, g.want));
     }
   ck(all, "BrkGridOf: on the step, away from the market by less than one step, kept when already on it");
   // the broker's own symbol grid (point 0.01 here)
   ck(BrkGridStop(CR_XAU, 1800.005, 1) == 1800.0 && BrkGridStop(CR_XAU, 1800.005, -1) == 1800.01, "BrkGridStop on the gold grid");
   // the comment
   datetime t0 = (datetime)SV(2021, 12, 31, 23, 59, 0);
   string cm = BrkComment("BKB", t0);
   ck(cm == "CR BKB 2112312359", "comment " + cm);
   ck(BrkCommentDec(cm, "BKB") == t0 && BrkCommentDec(cm, "BKE") == 0 && BrkCommentDec("CR BKB 21123123", "BKB") == 0
      && BrkCommentDec("hello", "BKB") == 0 && BrkCommentDec("CR BKB 2113312359", "BKB") == 0, "comment parse");
  }

static void w_tick()
  {
   x_reset("tick", SV(2021, 6, 15, 16, 0, 2), 100000.0);
   x_tick(CR_IDX, 0.25);
   x_quote(CR_IDX, 25000.0, 150);                              // bid 25000.00, ask 25001.50
   // T1: a stop off the step goes on the step away from the market (long down, short up) and is accepted; the answer and
   // the risk are those of the stop placed; a stop on the step is unchanged; no tick size: refused, nothing sent
   CrIntent a = x_intent("N30", 1, 0.1);
   bool t1 = BrkOpen(a, 24950.10) == CR_SEND_OK && x_sl(a.ticket) == 24950.0 && g_brk_sl == 24950.0;
   long ia = rp_pos_index(a.ticket);
   double risk_a = ia >= 0 ? (rp_pos[ia].price_open - 24950.0) / 0.25 * (0.25 * 0.89) * 0.1 : -1.0;
   t1 &= std::fabs(g_brk_risk - risk_a) < 1e-9;
   CrIntent b = x_intent("OC4", -1, 0.1);
   t1 &= BrkOpen(b, 25050.13) == CR_SEND_OK && x_sl(b.ticket) == 25050.25 && g_brk_sl == 25050.25;
   CrIntent c = x_intent("N30", 1, 0.1);
   t1 &= BrkOpen(c, 24950.25) == CR_SEND_OK && x_sl(c.ticket) == 24950.25;
   x_sym_d[{"US100.r", (int)SYMBOL_TRADE_TICK_SIZE}] = 0.0;
   size_t n0 = x_requests();
   CrIntent z = x_intent("N30", 1, 0.1);
   t1 &= BrkOpen(z, 24950.25) == CR_SEND_FAIL && g_brk_why == "no_tick_value" && x_requests() == n0;
   x_tick(CR_IDX, 0.25);
   hand("T1", t1, F("tick 0.25: a stop off the step is placed on the step away from the market (24950.10 -> 24950.00 long, 25050.13 -> "
                    "25050.25 short), the risk is that of the stop placed (%.4f EUR); on the step: unchanged; no tick size: refused, "
                    "nothing sent", g_brk_risk));
   // T2: a stop move is put on the step first; a move onto the stop in place sends nothing
   bool t2 = BrkModify(a.ticket, 24960.10) && x_sl(a.ticket) == 24960.0;
   size_t n1 = x_requests();
   t2 &= BrkModify(a.ticket, 24960.20) && x_sl(a.ticket) == 24960.0 && x_requests() == n1;
   t2 &= BrkModify(a.ticket, 24970.25) && x_sl(a.ticket) == 24970.25;
   t2 &= BrkModify(b.ticket, 25040.13) && x_sl(b.ticket) == 25040.25;
   hand("T2", t2, "tick 0.25: a stop move goes on the step away from the market before every check (24960.10 -> 24960.00, short "
        "25040.13 -> 25040.25); on the step already: unchanged; onto the stop in place: nothing sent");
   // T3: the broker keeps no stop: the stop put back is on the step
   x_fault("drop_sl", {"0", "1", "0"});
   CrIntent d = x_intent("OC4", 1, 0.1);
   bool t3 = BrkOpen(d, 24950.10) == CR_SEND_OK && !g_brk_refused && x_sl(d.ticket) == 24950.0;
   hand("T3", t3, "tick 0.25, the broker drops the stop of the order: the stop put back is on the step (24950.00)");
   // X12: a position left without a stop gets a stop on the step back
   long id = rp_pos_index(d.ticket);
   if(id >= 0) rp_pos[id].sl = 0.0;
   bool x12 = BrkModify(d.ticket, 24960.10) && x_sl(d.ticket) == 24960.0;
   hand("X12", x12, "tick 0.25: a position left without a stop gets a stop on the step (24960.10 -> 24960.00)");
   // X9: a stop that lands on or beyond the price once on the step is refused, nothing sent (the 3-spread minimum retires)
   size_t n2 = x_requests();
   CrIntent e1 = x_intent("N30", 1, 0.1), e2 = x_intent("OC4", -1, 0.1), e3 = x_intent("N30", 1, 0.1), e4 = x_intent("OC4", 1, 0.1);
   bool x9 = BrkOpen(e1, 25000.10) == CR_SEND_FAIL && g_brk_why == "stop_side" && BrkOpen(e2, 25001.40) == CR_SEND_FAIL
             && g_brk_why == "stop_side" && x_requests() == n2;
   x9 &= BrkOpen(e3, 24995.60) == CR_SEND_OK && x_sl(e3.ticket) == 24995.5 && BrkOpen(e4, 24995.70) == CR_SEND_OK && x_sl(e4.ticket) == 24995.5;
   hand("X9", x9, "tick 0.25: a stop on or beyond the price once on the step (long 25000.10 -> 25000.00 = bid, short 25001.40 -> 25001.50 "
        "= ask) is refused, nothing sent; 24995.60 and 24995.70 -> 24995.50 are placed (the hands' 3-spread minimum retires with O20)");
   // X11: tick 0.5 on a one-digit market, tick 0.03
   x_reset("tick_odd", SV(2021, 6, 15, 16, 0, 2), 100000.0);
   x_tick(CR_IDX, 0.5, 1);
   x_quote(CR_IDX, 25000.0, 150);
   CrIntent f = x_intent("N30", 1, 0.1);
   bool x11 = BrkOpen(f, 24950.30) == CR_SEND_OK && x_sl(f.ticket) == 24950.0;
   x_tick(CR_IDX, 0.03, 2);
   CrIntent g = x_intent("OC4", 1, 0.1);
   x11 &= BrkOpen(g, 24950.30) == CR_SEND_OK;
   double k = x_sl(g.ticket) / 0.03;
   x11 &= std::fabs(k - std::round(k)) < 1e-6 && x_sl(g.ticket) <= 24950.30 && 24950.30 - x_sl(g.ticket) < 0.03;
   hand("X11", x11, F("tick 0.5 on a one-digit market (24950.30 -> 24950.0) and tick 0.03 (24950.30 -> %.2f): the stop placed is a "
                      "multiple of the tick, away from the market", x_sl(g.ticket)));
  }

static void w_resolve()
  {
   x_reset("resolve", SV(2021, 6, 15, 10, 0, 0), 1000.0);
   rp_syms.push_back(RpSym());
   rp_syms.back().name = "NAS100.r";
   rp_syms.push_back(RpSym());
   rp_syms.back().name = "GOLD";
   rp_syms.push_back(RpSym());
   rp_syms.back().name = "ETHUSD.x";
   ck(BrkResolve("XAUUSD") == "XAUUSD.r" && BrkResolve("US100") == "US100.r", "the .r names first");
   rp_syms[1].name = "US100.zz";                              // no US100.r, no US100: the alias NAS100.r
   ck(BrkResolve("US100") == "NAS100.r", "US100 alias " + BrkResolve("US100"));
   rp_syms[0].name = "XAUUSD.q";                              // no XAUUSD.r: XAUUSD... prefix comes after the alias GOLD
   ck(BrkResolve("XAUUSD") == "GOLD", "XAUUSD alias " + BrkResolve("XAUUSD"));
   rp_syms[3].name = "ETHUSDm";
   ck(BrkResolve("ETHUSD") == "ETHUSD.x" || BrkResolve("ETHUSD") == "ETHUSDm", "prefix fallback " + BrkResolve("ETHUSD"));
   bool unk = BrkResolve("DOGEUSD") == "" && BrkResolve("JPN225") == "";
   hand("O4", unk && BrkResolve("XAUUSD") != "", "an unknown market resolves to nothing (no order possible); the broker's own name is found");
  }

//+------------------------------------------------------------------+
//| Broker: opens (DoOpen's checks), post-fill check, results         |
//+------------------------------------------------------------------+
static void w_open_checks()
  {
   x_reset("open_checks", SV(2021, 6, 15, 10, 0, 2), 1000.0);
   for(int s = 0; s < CR_NSYM; s++) x_quote(s, s == CR_XAU ? 1800.0 : (s == CR_IDX ? 14000.0 : (s == CR_BTC ? 40000.0 : 2500.0)), 20);
   size_t n0 = x_requests();
   CrIntent it = x_intent("ORX", 1, 0.05);
   // O1: no stop: 0, negative, NaN
   bool o1 = BrkOpen(it, 0.0) == CR_SEND_FAIL && g_brk_why == "no_stop" && BrkOpen(it, -1795.0) == CR_SEND_FAIL && BrkOpen(it, CrNaN()) == CR_SEND_FAIL;
   hand("O1", o1 && x_requests() == n0 && rp_pos.empty(), "an open without a stop (0, negative, NaN) is refused before anything is sent");
   // O2: wrong side; the right side is placed
   bool o2 = BrkOpen(it, 1800.5) == CR_SEND_FAIL && g_brk_why == "stop_side";
   CrIntent sh = x_intent("ORX", -1, 0.05);
   o2 &= BrkOpen(sh, 1799.5) == CR_SEND_FAIL && g_brk_why == "stop_side" && x_requests() == n0;
   int r = BrkOpen(sh, 1805.0);
   o2 &= r == CR_SEND_OK && x_listed(sh.ticket) && x_sl(sh.ticket) == 1805.0 && rp_pos.back().magic == 20261210;
   hand("O2", o2, "a stop on the wrong side is refused (nothing sent); the right side is placed at the broker with the stop asked");
   // O3: stops level 50 points on gold: 0.40 under the bid refused, 0.60 accepted
   rp_syms[CR_XAU].stops_level = 50;
   size_t n1 = x_requests();
   bool o3 = BrkOpen(it, 1799.6) == CR_SEND_FAIL && g_brk_why == "stop_side" && x_requests() == n1;
   o3 &= BrkOpen(it, 1799.4) == CR_SEND_OK;
   rp_syms[CR_XAU].stops_level = 0;
   hand("O3", o3, "a stop inside the broker's stops level is refused before sending; beyond it the open goes");
   // O5: an invalid side
   CrIntent bad = x_intent("ORX", 0, 0.05);
   size_t n2 = x_requests();
   bool o5 = BrkOpen(bad, 1795.0) == CR_SEND_FAIL && g_brk_why == "side";
   bad.side = 2;
   o5 &= BrkOpen(bad, 1795.0) == CR_SEND_FAIL && x_requests() == n2;
   hand("O5", o5, "an invalid side is refused before sending");
   // O18: NaN volume
   CrIntent nv = x_intent("ORX", 1, CrNaN());
   bool o18 = BrkOpen(nv, 1795.0) == CR_SEND_FAIL && g_brk_why == "volume" && x_requests() == n2;
   o18 &= !BrkModify(sh.ticket, CrNaN()) && g_brk_why == "no_stop";
   hand("O18", o18, "a NaN stop or volume is refused by the robot itself (open and stop move), nothing sent");
   // O17: lot step 0.5 on US100: 0.77 -> 0.5, 0.49 -> refused (minimum 0.5)
   rp_syms[CR_IDX].vstep = 0.5;
   rp_syms[CR_IDX].vmin = 0.5;
   CrIntent ix = x_intent("N30", 1, 0.77);
   r = BrkOpen(ix, 13950.0);
   bool o17 = r == CR_SEND_OK && std::fabs(g_brk_vol - 0.5) < 1e-12;
   CrIntent ix2 = x_intent("OC4", 1, 0.49);
   o17 &= BrkOpen(ix2, 13950.0) == CR_SEND_FAIL && g_brk_why == "volume";
   rp_syms[CR_IDX].vstep = 0.1;
   rp_syms[CR_IDX].vmin = 0.1;
   hand("O17", o17, "the volume is floored to the lot step (0.5): 0.77 -> 0.5, never rounded up; under the minimum lot: refused");
   // O21: notional at most 20 x balance (1000 EUR): gold 1800 x 100 x 0.89 = 160,200 EUR a lot -> 0.12 lot at most
   CrIntent big = x_intent("GFP", 1, 5.0);
   r = BrkOpen(big, 1795.0);
   bool o21 = r == CR_SEND_OK && std::fabs(g_brk_vol - 0.12) < 1e-12;
   rp_balance = 50.0;                                          // 20 x 50 = 1000 EUR: even 0.01 lot (1,602 EUR) is too much
   CrIntent big2 = x_intent("D4H", 1, 0.5);
   size_t n3 = x_requests();
   o21 &= BrkOpen(big2, 1795.0) == CR_SEND_FAIL && g_brk_why == "notional" && x_requests() == n3;
   rp_balance = 1000.0;
   hand("O21", o21, "the value of a position is cut to 20 x the balance (cut=notional); refused when even the minimum lot is worth more");
   // O22: a tick older than 10 s
   x_quote(CR_BTC, 40000.0, 20, rp_now - 11);
   CrIntent bt = x_intent("BKB", 1, 0.01);
   bool o22 = BrkOpen(bt, 39000.0) == CR_SEND_FAIL && g_brk_why == "old_price";
   x_quote(CR_BTC, 40000.0, 20, rp_now - 10);
   o22 &= BrkOpen(bt, 39000.0) == CR_SEND_OK;
   hand("O22", o22, "a last tick older than 10 s: refused (the volume would be sized on it); 10 s old: sent");
   // O12: no price (the market has no tick yet), the server says closed (10018)
   rp_syms[CR_ETH].cur = -1;
   CrIntent et = x_intent("BKE", 1, 0.1);
   bool o12 = BrkOpen(et, 2400.0) == CR_SEND_FAIL && g_brk_why == "no_price";
   x_quote(CR_ETH, 2500.0, 20);
   size_t nq = x_requests();
   for(long mode : {3L, 0L, 1L})                               // close only, disabled, long only
     {
      x_sym_i[{"ETHUSD.r", (int)SYMBOL_TRADE_MODE}] = mode;
      o12 &= BrkOpen(et, 2400.0) == CR_SEND_FAIL && g_brk_why == "not_tradable";
     }
   x_sym_i.clear();
   o12 &= x_requests() == nq;
   x_fault("refuse_open", {"10018", "1", "0"});
   o12 &= BrkOpen(et, 2400.0) == CR_SEND_FAIL && g_brk_rc == 10018 && g_brk_why == "refused";
   hand("O12", o12, "a market not fully tradable (close only, disabled, long only) or without a price: refused before sending; the "
        "server's 'market closed' (10018): a refusal with its code; nothing open");
   // O13: server refusals reported with their code; 10031 (no connection) is an unknown result
   bool o13 = true;
   size_t np0 = rp_pos.size();
   for(uint code : {10006u, 10004u, 10019u})
     {
      x_fault("refuse_open", {std::to_string(code), "1", "0"});
      o13 &= BrkOpen(et, 2400.0) == CR_SEND_FAIL && g_brk_rc == code;
     }
   x_fault("refuse_open", {"10031", "1", "0"});
   o13 &= BrkOpen(et, 2400.0) == CR_SEND_UNKNOWN && g_brk_rc == 10031;
   hand("O13", o13 && rp_pos.size() == np0, "a refusal of the trade server is reported with its code and nothing is open; 'no connection' "
        "is an unknown result (nothing is sent again before the one-intent-one-trade search)");
   // O16: the Algo Trading button off: opens refused without reaching the broker; MetaTrader refuses the closes (10027)
   CrIntent ok16 = x_intent("BKE", 1, 0.1);
   bool o16 = BrkOpen(ok16, 2400.0) == CR_SEND_OK;
   x_term_i[(int)TERMINAL_TRADE_ALLOWED] = 0;
   size_t n16 = x_requests();
   CrIntent e16 = x_intent("F1E", 1, 0.1);
   o16 &= BrkOpen(e16, 2400.0) == CR_SEND_FAIL && g_brk_why == "algo_trading_off" && x_requests() == n16;
   x_fault("refuse_close", {"10027", "1", "0"});               // (the terminal's own refusal: the mock does not know the button)
   o16 &= !BrkClose(ok16.ticket, 0, "o16") && g_brk_rc == 10027 && x_listed(ok16.ticket);
   x_term_i.clear();
   x_mql_i[(int)MQL_TRADE_ALLOWED] = 0;                        // the EA's own "Allow Algo Trading" box
   o16 &= BrkOpen(e16, 2400.0) == CR_SEND_FAIL && g_brk_why == "algo_trading_off";
   x_mql_i.clear();
   o16 &= BrkClose(ok16.ticket, 0, "o16") && !x_listed(ok16.ticket) && BrkOpen(e16, 2400.0) == CR_SEND_OK;
   hand("O16", o16, "Algo Trading off (terminal button or the EA's box): opens refused before reaching the broker; a close refused by "
        "MetaTrader (10027) leaves the position; button back on: close and open work");
   // O19: a market whose orders cannot carry a stop: no position is opened without one
   x_sym_i[{"ETHUSD.r", (int)SYMBOL_ORDER_MODE}] = SYMBOL_ORDER_MARKET | SYMBOL_ORDER_LIMIT | SYMBOL_ORDER_STOP | SYMBOL_ORDER_TP;
   size_t n19 = x_requests();
   size_t p19 = rp_pos.size();
   CrIntent e19 = x_intent("BKE", 1, 0.1);
   bool o19 = BrkOpen(e19, 2400.0) == CR_SEND_FAIL && g_brk_why == "no_order_sl" && x_requests() == n19 && rp_pos.size() == p19;
   x_sym_i.clear();
   hand("O19", o19, "a market where the broker takes no stop inside the order (SYMBOL_ORDER_MODE without SYMBOL_ORDER_SL): refused "
        "before anything is sent, no position without a stop");
   // the request itself: magic, deviation 2 spreads, comment, no target
   x_quote(CR_XAU, 1800.0, 25);
   CrIntent dv = x_intent("ORX", -1, 0.02);
   BrkOpen(dv, 1810.0);
   long i = rp_pos_index(dv.ticket);
   ck(i >= 0 && rp_pos[i].magic == 20261210 && rp_deviation == 50 && rp_pos[i].tp == 0.0
      && rp_pos[i].comment == BrkComment("ORX", (datetime)(dv.oid / 100)), "magic, deviation 2 spreads, no target, comment");
   hand("X10", i >= 0 && rp_pos[i].tp == 0.0, "the robot sends no target: every request carries tp = 0 (the targets of the hands retire)");
   // observer: nothing at all
   g_cfg.observer = true;
   size_t n4 = x_requests();
   ulong dvt = dv.ticket;
   CrIntent dv2 = dv;
   ck(BrkOpen(dv2, 1810.0) == CR_SEND_FAIL && g_brk_why == "observer" && !BrkClose(dvt, 0, "x") && g_brk_why == "observer"
      && !BrkModify(dvt, 1811.0) && g_brk_why == "observer" && x_requests() == n4 && x_listed(dvt), "an observer copy sends nothing");
   g_cfg.observer = false;
   g_brk_may = false;
   ck(BrkOpen(dv2, 1810.0) == CR_SEND_FAIL && g_brk_why == "lock" && !BrkClose(dvt, 0, "x") && x_requests() == n4,
      "a copy without the instance lock sends nothing");
   g_brk_may = true;
   // not hedging
   rp_account_mode = ACCOUNT_TRADE_MODE_DEMO;
  }

static void w_postfill()
  {
   x_reset("postfill", SV(2021, 6, 15, 10, 0, 2), 1000.0);
   x_quote(CR_XAU, 1800.0, 13);
   // O23: the fill 2.00 worse than the quote: risk at the real fill; within 1.25 x budget kept, over -> closed (REFUSED)
   rp_syms[CR_XAU].slip_mkt = 2.0 / 1800.13;                  // ask 1800.13 x (1 + slip) = 1802.13
   CrIntent a = x_intent("ORX", 1, 0.02, 10.0);                // budget 10 EUR; stop 5.00 under the quote, 7.00 under the fill
   int r = BrkOpen(a, 1795.13);
   double risk = (1802.13 - 1795.13) / 0.01 * (0.01 * 100 * 0.89) * 0.02;
   bool o23 = r == CR_SEND_OK && !g_brk_refused && x_listed(a.ticket) && std::fabs(g_brk_risk - risk) < 1e-6;   // 12.46 <= 12.50
   rp_syms[CR_XAU].slip_mkt = 3.0 / 1800.13;                  // 8.00 under the fill: 14.24 > 12.50
   CrIntent b = x_intent("GFP", 1, 0.02, 10.0);
   r = BrkOpen(b, 1795.13);
   o23 &= r == CR_SEND_OK && g_brk_refused && g_brk_why == "risk" && !x_listed(b.ticket);
   hand("O23", o23, "a fill worse than the quote: the risk is taken at the price really obtained; within 1.25 x the budget the position "
        "stays, beyond it is closed at once (REFUSED, push)");
   ck(x_count("REFUSED") == 1 && x_pushes_with("REFUSED") == 1, "REFUSED journaled and pushed once");
   // O25: refused and its own close refused too: the position is still there (the follower closes it at its next passes)
   x_fault("refuse_close", {"10006", "1", "0"});
   CrIntent c = x_intent("D4H", 1, 0.02, 10.0);
   r = BrkOpen(c, 1795.13);
   hand("O25", r == CR_SEND_OK && g_brk_refused && x_listed(c.ticket), "a refused fill whose close is refused too stays open and is "
        "returned to the follower (OK + REFUSED), which closes it at its next passes (T8 worlds)");
   rp_syms[CR_XAU].slip_mkt = 0.3e-4;
   // O24 / T3 / X12: the broker keeps no stop: put back (on the step), else closed
   x_fault("drop_sl", {"0", "1", "0"});
   CrIntent d = x_intent("BKB", 1, 0.01, 1000.0);
   x_quote(CR_BTC, 40000.0, 20);
   r = BrkOpen(d, 39000.0);
   bool o24 = r == CR_SEND_OK && x_listed(d.ticket) && x_sl(d.ticket) == 39000.0 && !g_brk_refused;
   x_fault("drop_sl", {"0", "1", "0"});
   x_fault("refuse_sltp", {"10016", "1", "0"});
   CrIntent e = x_intent("F1B", 1, 0.01, 1000.0);
   r = BrkOpen(e, 39000.0);
   o24 &= r == CR_SEND_OK && g_brk_refused && g_brk_why == "no_sl" && !x_listed(e.ticket);
   hand("O24", o24, "a position the broker leaves without a stop gets it back at once; when that is refused it is closed (REFUSED "
        "no_sl); a stop removed later is put back by the invariant (T8 world 'stops')");
   // O26: the stop put back on a position the broker left naked is worth at most 1.25 x the budget, else the position goes
   x_quote(CR_XAU, 1800.0, 13);
   rp_syms[CR_XAU].slip_mkt = 2.0 / 1800.13;                  // fill 1802.13: 7.00 to the stop 1795.13 = 12.46 EUR for 0.02 lot
   x_fault("drop_sl", {"0", "1", "0"});
   CrIntent n1 = x_intent("ORX", 1, 0.02, 10.0);
   bool o26 = BrkOpen(n1, 1795.13) == CR_SEND_OK && !g_brk_refused && x_sl(n1.ticket) == 1795.13;
   rp_syms[CR_XAU].slip_mkt = 3.0 / 1800.13;                  // fill 1803.13: 8.00 = 14.24 EUR > 12.50
   x_fault("drop_sl", {"0", "1", "0"});
   CrIntent n2 = x_intent("GFP", 1, 0.02, 10.0);
   o26 &= BrkOpen(n2, 1795.13) == CR_SEND_OK && g_brk_refused && g_brk_why == "risk" && !x_listed(n2.ticket);
   rp_syms[CR_XAU].slip_mkt = 0.3e-4;
   hand("O26", o26, "a position the broker left without a stop gets the stop of the order back only while the risk at that stop is "
        "within 1.25 x the budget (12.46 for 12.50: kept); beyond (14.24): closed (REFUSED risk). A stop removed later is put back "
        "at the paper's stop by the follower (T8 world 'stops')");
   // unknown results: a timeout, no retcode
   x_fault("timeout_open_done", {"1", "0"});
   CrIntent u = x_intent("NQB", 1, 0.01);
   ck(BrkOpen(u, 39000.0) == CR_SEND_UNKNOWN && g_brk_rc == TRADE_RETCODE_TIMEOUT, "a timeout is an unknown result");
  }

//+------------------------------------------------------------------+
//| Broker: closes, stop moves, close-all                            |
//+------------------------------------------------------------------+
static void w_close_modify()
  {
   x_reset("close_modify", SV(2021, 6, 15, 10, 0, 2), 1000.0);
   for(int s = 0; s < CR_NSYM; s++) x_quote(s, s == CR_XAU ? 1800.0 : (s == CR_IDX ? 14000.0 : (s == CR_BTC ? 40000.0 : 2500.0)), 13);
   CrIntent a = x_intent("ORX", 1, 0.02);
   BrkOpen(a, 1795.0);
   // M1: the robot moves its stop both ways (to the paper's stop); a stop at or beyond the price, or too close, is not sent
   size_t n0 = x_requests();
   bool m1 = BrkModify(a.ticket, 1797.0) && x_sl(a.ticket) == 1797.0 && BrkModify(a.ticket, 1794.0) && x_sl(a.ticket) == 1794.0;
   m1 &= !BrkModify(a.ticket, 1800.0) && g_brk_why == "stop_side" && !BrkModify(a.ticket, 1801.0) && x_sl(a.ticket) == 1794.0;
   rp_syms[CR_XAU].stops_level = 100;
   m1 &= !BrkModify(a.ticket, 1799.5) && g_brk_why == "stop_side";
   rp_syms[CR_XAU].stops_level = 0;
   hand("M1", m1, "stop moves go both ways to the paper's stop (the hands' 'only toward the price' does not apply: the paper decides); "
        "a stop at or beyond the price or inside STOPS_LEVEL is not sent", false);
   (void)n0;
   // M2: unknown ticket refused; a stop can never be removed
   size_t n1 = x_requests();
   bool m2 = !BrkModify(424242, 1797.0) && g_brk_gone && !BrkModify(a.ticket, 0.0) && !BrkModify(a.ticket, -1.0) && x_sl(a.ticket) == 1794.0;
   hand("M2", m2 && x_requests() == n1, "a stop move of an unknown position is refused; a stop is never removed (0 or below refused)");
   // M3: another magic: never touched
   ulong hand_t = x_hand(CR_XAU, 1, 0.01, 20261110, 1700.0);
   ulong other = x_hand(CR_ETH, -1, 0.01, 777, 2600.0);
   bool m3 = !BrkModify(hand_t, 1750.0) && g_brk_why == "not_ours" && !BrkClose(hand_t, 0, "x") && !BrkClose(other, 0, "x")
             && x_sl(hand_t) == 1700.0 && x_listed(hand_t) && x_listed(other);
   hand("M3", m3, "the hands' (20261110) and other robots' or manual positions are never modified or closed");
   // M4: the values in place: true, nothing sent
   size_t n2 = x_requests();
   hand("M4", BrkModify(a.ticket, 1794.0) && x_requests() == n2, "a stop move to the stop in place answers ok without a request (no 10025)");
   // freeze level: the broker refuses (10029), the stop stays
   rp_syms[CR_XAU].freeze_level = 1000;
   ck(!BrkModify(a.ticket, 1796.0) && g_brk_rc == TRADE_RETCODE_FROZEN && g_brk_why == "freeze" && x_sl(a.ticket) == 1794.0, "freeze level");
   rp_syms[CR_XAU].freeze_level = 0;
   // C1: close at the market; closing twice: nothing sent, gone
   double bid = rp_syms[CR_XAU].tick_bid;
   bool c1 = BrkClose(a.ticket, 20261210, "test") && !g_brk_gone && !x_listed(a.ticket);
   const RpDeal &dl = rp_deals.back();
   c1 &= dl.entry == DEAL_ENTRY_OUT && dl.position == a.ticket && dl.magic == 20261210 && std::fabs(dl.price - bid * (1 - 0.3e-4)) < 1e-9;
   size_t n3 = x_requests();
   c1 &= BrkClose(a.ticket, 20261210, "again") && g_brk_gone && x_requests() == n3;
   hand("C1", c1, "a close goes at the market (the deal carries the request's magic); closing a position already gone sends nothing");
   // C5: a position that disappears as it is closed or modified: no stale retcode
   CrIntent b = x_intent("GFP", 1, 0.02);
   BrkOpen(b, 1795.0);
   long ib = rp_pos_index(b.ticket);
   rp_close_at(ib, 1795.0, DEAL_REASON_SL, rp_now, 20261208);
   bool c5 = BrkClose(b.ticket, 0, "race") && g_brk_gone && g_brk_rc == 0;
   c5 &= !BrkModify(b.ticket, 1796.0) && g_brk_gone && g_brk_rc == 0;
   hand("C5", c5, "a position gone (its stop hit) just as it is closed or modified: 'gone', not the previous order's retcode");
   // C3 / C4: close-all: every robot position on every market, the others untouched; false while one cannot be closed
   CrIntent p1 = x_intent("BKB", 1, 0.01), p2 = x_intent("N30", -1, 0.1), p3 = x_intent("D4H", 1, 0.01);
   BrkOpen(p1, 39000.0);
   BrkOpen(p2, 14100.0);
   BrkOpen(p3, 1790.0);
   ulong mark = x_hand(CR_XAU, 1, 0.01, CR_MAGIC_MARK, 1780.0);
   x_fault("refuse_close", {"10018", "1", "20261209"});
   bool c4 = !BrkCloseAll(0, "test") && x_listed(p3.ticket) && !x_listed(p1.ticket) && !x_listed(p2.ticket) && !x_listed(mark);
   hand("C4", c4, "close-all answers false while a position could not be closed (market closed)");
   bool c3 = BrkCloseAll(CR_MAGIC_MARK, "guard") && !x_listed(p3.ticket) && x_listed(hand_t) && x_listed(other) && rp_deals.back().magic == CR_MAGIC_MARK;
   hand("C3", c3, "close-all closes every robot position on every market (GUARD: requests of magic 20261290), never the hands' or "
        "another robot's");
   ck(BrkRobotCount() == 0, "no robot position left");
  }

//+------------------------------------------------------------------+
//| Broker: one intent, one trade (R5); stable reads                 |
//+------------------------------------------------------------------+
static void w_intent_check()
  {
   x_reset("intent_check", SV(2021, 6, 15, 10, 0, 2), 1000.0);
   x_quote(CR_BTC, 40000.0, 20);
   long magic = 20261203;
   long stamp = (long)ClkServerToUtc(SV(2021, 6, 15, 10, 0, 0));
   ulong prev = 0, found = 0;
   string why;
   ck(BrkIntentCheck(magic, stamp, prev, found, why) == 0, "nothing: may send");
   // an open order of the magic, any state
   RpOrder oo = {90000001, "BTCUSD.r", 4, ORDER_STATE_PLACED, rp_now, rp_now, 0, magic, 0.01, 41000.0, 0, 0, 3, ""};
   rp_open_orders.push_back(oo);
   ck(BrkIntentCheck(magic, stamp, prev, found, why) == 2 && why == "open_order", "an open order blocks");
   rp_open_orders.clear();
   // a rejected history order does not block; a filled one that opened a position does
   rp_add_order("BTCUSD.r", 0, ORDER_STATE_REJECTED, 0, magic, 0.01, 0, 39000, 0, "");
   ck(BrkIntentCheck(magic, stamp, prev, found, why) == 0, "a rejected order does not block");
   // the previous trade's position (opened before the stamp) and its closing order and OUT deal do not block, but the
   // position must go first
   rp_now = SV(2021, 6, 15, 9, 0, 2);
   CrIntent old = x_intent("BKB", 1, 0.01);
   BrkOpen(old, 39000.0);
   rp_now = SV(2021, 6, 15, 10, 0, 3);
   ck(BrkIntentCheck(magic, stamp, prev, found, why) == 1 && prev == old.ticket, "the previous trade's position: close it first");
   BrkClose(old.ticket, magic, "prev");
   ck(BrkIntentCheck(magic, stamp, prev, found, why) == 0, "its closing order and OUT deal (at or after the stamp) do not block (R5 d)");
   // an IN deal at or after the stamp blocks, also stamped after the terminal's clock (R5 e)
   CrIntent now_it = x_intent("BKB", 1, 0.01, 0.0, stamp);
   BrkOpen(now_it, 39000.0);
   for(RpDeal &d : rp_deals)
      if(d.position == now_it.ticket) d.time += 30;
   for(RpOrder &o : rp_orders)
      if(o.ticket == now_it.ticket) { o.setup += 30; o.done += 30; }
   long ip = rp_pos_index(now_it.ticket);
   RpPos keep = rp_pos[ip];
   rp_pos.erase(rp_pos.begin() + ip);                          // not listed yet
   int c = BrkIntentCheck(magic, stamp, prev, found, why);
   ck(c == 2 && (why == "order" || why == "deal_in") && found == now_it.ticket, "an order or IN deal timed after the clock still blocks: " + why);
   ck(!BrkPositionClosed((long)now_it.ticket), "its position is not closed");
   rp_pos.push_back(keep);
   // a position opened at or after the stamp
   for(RpOrder &o : rp_orders) o.setup = 0;
   for(RpDeal &d : rp_deals) d.time = 0;
   ck(BrkIntentCheck(magic, stamp, prev, found, why) == 2 && why == "position", "a position at or after the stamp blocks");
   // stable reads
   long t = SV(2021, 6, 15, 11, 0, 0);
   rp_now = t;
   g_brk_fp_n = -1;
   bool s0 = BrkStableRead(t), s1 = BrkStableRead(t + 1), s2 = BrkStableRead(t + 2);
   x_hand(CR_BTC, 1, 0.01, 777);
   bool s3 = BrkStableRead(t + 3), s4 = BrkStableRead(t + 4), s5 = BrkStableRead(t + 5);
   bool s6 = BrkStableRead(t + 5 - 3600);                      // the clock steps back an hour: the 2 s count again from there
   bool s7 = BrkStableRead(t + 7 - 3600);
   ck(!s0 && !s1 && s2 && !s3 && !s4 && s5 && !s6 && s7, F("stable reads %d%d%d %d%d%d %d%d", s0, s1, s2, s3, s4, s5, s6, s7));
  }

//+------------------------------------------------------------------+
//| Guards: lock, clock, Friday, flat closes, GUARD (a), mark         |
//+------------------------------------------------------------------+
static void w_lock()
  {
   x_reset("lock", SV(2021, 6, 15, 10, 0, 2), 1000.0);
   bool take = GrdLockTake();
   ck(take && g_grd_lock_held && rp_gv.count("CR_lock_12345678") && rp_gv_temp.count("CR_lock_12345678"), "the lock is taken, temporary");
   rp_now += 1;
   GrdLockRefresh();
   ck(g_grd_lock_held && g_brk_may, "refreshed");
   // a second copy while this one runs
   double held_beat = g_grd_lock_beat;
   g_grd_lock_held = false;
   bool second = GrdLockTake();
   ck(!second && rp_gv["CR_lock_12345678"] == held_beat, "a second copy is refused while the heartbeat is fresh");
   // another copy took the lock while this one stalled: this copy stops sending
   g_grd_lock_held = true;
   rp_gv["CR_lock_12345678"] = held_beat + 12345.0;
   rp_now += 1;
   GrdLockRefresh();
   ck(!g_grd_lock_held && !g_brk_may && x_count("ERROR") == 1, "a lock taken by another copy: this copy sends nothing");
   // a crashed copy: its heartbeat is 11 s old -> taken over after the 10 s retry
   rp_now += 11;
   GrdLockRefresh();
   ck(g_grd_lock_held && g_brk_may && x_count("TAKEOVER") >= 1, "the stale lock (11 s) is taken over");
   GrdLockRelease();
   ck(!rp_gv.count("CR_lock_12345678") && !g_grd_lock_held, "released at OnDeinit");
  }

static void w_clock()
  {
   long t = SV(2021, 3, 16, 10, 0, 0);
   x_reset("clock", t, 1000.0);
   GrdClockCheck(t);
   ck(!g_grd_clock_bad && GrdEntryBlock(t) == CR_SK_NONE, "the rule offset: no CLOCK");
   rp_gmt_shift = 3600;                                        // the computer clock 1 h off
   rp_now = t + 600;
   GrdOnTimer(rp_now);
   ck(g_grd_clock_bad && !g_grd_clock_flat && GrdEntryBlock(rp_now) == CR_SK_CLOCK && x_count("CLOCK") == 1, "CLOCK: entries blocked at once");
   bool early = false;
   for(int k = 1; k < 10; k++)
     {
      rp_now = t + 600 + 60 * k;
      GrdOnTimer(rp_now);
      early |= g_grd_clock_flat;
     }
   rp_now = t + 600 + 599;
   GrdOnTimer(rp_now);
   early |= g_grd_clock_flat;
   ck(!early && x_count("CLOCK") == 1, "not flat before 10 min (checked every 60 s while wrong)");
   rp_now = t + 600 + 600;
   GrdOnTimer(rp_now);
   ck(g_grd_clock_flat && GrdFlat() && x_count("CLOCK") == 2, "wrong for 10 min: flat");
   rp_gmt_shift = 0;
   rp_now = t + 1300;
   GrdOnTimer(rp_now);
   ck(!g_grd_clock_bad && !g_grd_clock_flat && GrdEntryBlock(rp_now) == CR_SK_NONE, "the offset matches again: entries");
   rp_tester = 1;
   g_cfg.tester = true;
   rp_now = t + 2000;
   GrdClockCheck(rp_now);
   ck(!g_grd_clock_bad, "the tester mode never checks (TimeGMT = TimeTradeServer there)");
   // R12: the server clock steps back an hour: the next checks still come
   g_cfg.tester = false;
   rp_tester = 0;
   rp_now = t + 4000;
   GrdOnTimer(rp_now);
   rp_now = t + 4000 - 3600;
   rp_gmt_shift = 3600;
   GrdOnTimer(rp_now);
   hand("R12", g_grd_clock_bad, "the server clock steps back an hour: the periodic work (clock check, ledger read, retries) still runs, "
        "it never waits for the old clock to come back");
  }

static void w_friday()
  {
   long fri = SV(2021, 10, 8, 21, 0, 0);
   x_reset("friday", fri, 1000.0);
   g_cfg.friday_hhmm = 2200;
   x_quote(CR_BTC, 40000.0, 20);
   x_quote(CR_XAU, 1800.0, 13);
   CrIntent a = x_intent("BKB", 1, 0.01), b = x_intent("ORX", 1, 0.01);
   BrkOpen(a, 39000.0);
   BrkOpen(b, 1790.0);
   ulong hd = x_hand(CR_XAU, 1, 0.01, 20261110);
   GrdOnTimer(fri);
   ck(x_listed(a.ticket) && GrdEntryBlock(fri) == CR_SK_NONE, "before the Friday close: nothing");
   rp_now = SV(2021, 10, 8, 22, 0, 0);
   x_quote(CR_BTC, 40000.0, 20);
   x_quote(CR_XAU, 1800.0, 13);
   GrdOnTimer(rp_now);
   bool f1 = !x_listed(a.ticket) && !x_listed(b.ticket) && x_listed(hd);
   for(long t : {SV(2021, 10, 8, 22, 0, 10), SV(2021, 10, 9, 12, 0, 0), SV(2021, 10, 10, 23, 59, 40)}) f1 &= GrdEntryBlock(t) == CR_SK_FRIDAY;
   f1 &= GrdEntryBlock(SV(2021, 10, 11, 0, 0, 5)) == CR_SK_NONE;
   hand("F1", f1, "the Friday close (InpFridayCloseHHMM 2200): every robot position closed at 22:00 server, entries blocked all week-end, "
        "back on Monday 00:00; the hands' position untouched");
   // F2: refused while the market is closed: every 60 s; another refusal: every 10 s; warned once
   rp_now = SV(2021, 10, 15, 21, 59, 0);
   CrIntent c = x_intent("ORX", 1, 0.01);
   x_quote(CR_XAU, 1800.0, 13);
   BrkOpen(c, 1790.0);
   x_fault("refuse_close", {"10018", "2", "0"});
   x_fault("refuse_close", {"10006", "1", "0"});
   long t0 = SV(2021, 10, 15, 22, 0, 1);
   size_t n0 = rp_orders.size();
   long w0 = x_pushes_with("ATTENTION");
   rp_now = t0;
   GrdOnTimer(rp_now);                                         // refused 10018
   rp_now = t0 + 11;
   GrdOnTimer(rp_now);                                         // not before 60 s
   bool f2 = x_listed(c.ticket) && rp_orders.size() == n0;
   rp_now = t0 + 60;
   GrdOnTimer(rp_now);                                         // refused 10018 again
   rp_now = t0 + 120;
   GrdOnTimer(rp_now);                                         // refused 10006: then every 10 s
   rp_now = t0 + 130;
   GrdOnTimer(rp_now);                                         // done
   f2 &= !x_listed(c.ticket) && x_pushes_with("ATTENTION") - w0 == 1 && x_pushes_with("marche ferme") >= 1;
   hand("F2", f2, "a Friday close refused: tried every 60 s while the market is closed, every 10 s for another refusal, closed once the "
        "broker accepts; one warning push an hour");
   // F3: missed (the terminal was off on Friday evening): closed at the first pass after
   rp_now = SV(2021, 10, 22, 21, 0, 0);
   x_quote(CR_XAU, 1800.0, 13);
   CrIntent d = x_intent("D4H", 1, 0.01);
   ck(BrkOpen(d, 1790.0) == CR_SEND_OK, "the Friday position");
   rp_now = SV(2021, 10, 25, 0, 10, 0);
   x_quote(CR_XAU, 1800.0, 13);
   CrIntent e = x_intent("GFP", 1, 0.01);                      // opened this week: not concerned
   BrkOpen(e, 1790.0);
   g_grd_close_next = 0;
   GrdOnTimer(rp_now);
   hand("F3", !x_listed(d.ticket) && x_listed(e.ticket) && x_pushes_with("fermeture du vendredi manquee") == 1,
        "a Friday close missed (terminal off): a position opened before it is closed at the first pass after, with a push; one "
        "opened since is left alone");
   // F4: a forced close that fails because the Algo Trading button is off: the warning says so; closed once it is back on
   rp_now = SV(2021, 10, 29, 21, 50, 0);
   x_quote(CR_XAU, 1800.0, 13);
   CrIntent f4 = x_intent("ORX", 1, 0.01);
   BrkOpen(f4, 1790.0);
   x_term_i[(int)TERMINAL_TRADE_ALLOWED] = 0;
   x_fault("refuse_close", {"10027", "1", "0"});               // MetaTrader's own refusal
   g_grd_warn_t = 0;
   g_grd_close_next = 0;
   rp_now = SV(2021, 10, 29, 22, 0, 1);
   GrdOnTimer(rp_now);
   bool f4ok = x_listed(f4.ticket) && x_pushes_with("ne le sont pas (trading automatique desactive dans MT5)") == 1;
   x_term_i.clear();
   rp_now += 11;
   GrdOnTimer(rp_now);
   f4ok &= !x_listed(f4.ticket);
   hand("F4", f4ok, "a forced close refused because the Algo Trading button is off: 'ATTENTION : 1 position(s) ... (trading automatique "
        "desactive dans MT5)'; closed at the retry 10 s later once the button is back on");
  }

static void w_guard_live()
  {
   long t = SV(2021, 8, 6, 10, 0, 0);
   x_reset("guard_live", t, 10000.0);
   x_quote(CR_XAU, 1800.0, 13);
   x_quote(CR_BTC, 40000.0, 20);
   CrIntent a = x_intent("BKB", 1, 0.01);
   BrkOpen(a, 39000.0);
   ulong hd = x_hand(CR_XAU, 1, 3.0, 777);
   LedRead(t);
   rp_now = t + 2;
   LedRead(rp_now);
   ck(LedSettled(), "settled");
   GrdOnTimer(rp_now);
   ck(!g_grd_guard, "no guard at 100 %");
   x_quote(CR_XAU, 1780.0, 13);                                // -20 x 300 oz x 0.89 = -5,340 EUR floating
   rp_now += 1;
   GrdOnTimer(rp_now);
   bool latched = g_grd_guard && GrdEntryBlock(rp_now) == CR_SK_GUARD;
   ck(latched && !x_listed(a.ticket) && x_listed(hd) && rp_deals.back().magic == CR_MAGIC_MARK, "GUARD (a): robot closed with the mark magic");
   LedRead(rp_now + 1);
   ck(LedMarkSeen(), "the close deal is the mark: (c) holds after a restart");
   // no robot position at the latch: the mark trade, refused 3 times while the market is closed, every 60 s
   long t2 = SV(2021, 8, 9, 10, 0, 0);
   x_reset("guard_mark", t2, 10000.0);
   for(int s = 0; s < CR_NSYM; s++) x_quote(s, s == CR_XAU ? 1800.0 : (s == CR_IDX ? 14000.0 : (s == CR_BTC ? 40000.0 : 2500.0)), 13);
   g_grd_guard = true;
   LedRead(t2);
   rp_now = t2 + 2;
   LedRead(rp_now);
   x_fault("refuse_open", {"10018", "8", "20261290"});        // two passes of four markets
   long mk[4];
   long offs[4] = {0, 30, 60, 120};                            // passes at +0, +30 (too early), +60, +120
   long t2p = rp_now;
   for(int k = 0; k < 4; k++)
     {
      rp_now = t2p + offs[k];
      for(int s = 0; s < CR_NSYM; s++) x_quote(s, rp_syms[s].tick_bid, 13);
      GrdOnTimer(rp_now);
      mk[k] = x_count("MARK");
     }
   int n_mark = 0;
   for(const RpDeal &d : rp_deals) n_mark += (d.magic == CR_MAGIC_MARK);
   LedRead(rp_now + 1);
   ck(mk[0] == 5 && mk[1] == 5 && mk[2] == 10 && mk[3] == 11 && n_mark == 2 && x_pushes_with("marque") == 1 && LedMarkSeen()
      && BrkRobotCount() == 0, F("the mark: four markets refused (market closed) twice, 60 s apart, then made and closed at once "
                                 "(MARK lines %ld %ld %ld %ld, %d deals)", mk[0], mk[1], mk[2], mk[3], n_mark));
   // InpGuard false (SPEC 6.2 v2.1, the default of D2): the same fall to 50 % latches nothing, no close, no mark; and a
   // mark already in the history (c) is ignored
   long t3 = SV(2021, 8, 10, 10, 0, 0);
   x_reset("guard_off", t3, 10000.0);
   g_cfg.guard_off = true;
   x_quote(CR_XAU, 1800.0, 13);
   x_quote(CR_BTC, 40000.0, 20);
   CrIntent b = x_intent("BKB", 1, 0.01);
   BrkOpen(b, 39000.0);
   ulong hd2 = x_hand(CR_XAU, 1, 3.0, 777);
   LedRead(t3);
   rp_now = t3 + 2;
   LedRead(rp_now);
   x_quote(CR_XAU, 1780.0, 13);                                // the same -5,340 EUR floating: equity at 46.6 % of ref
   rp_now += 1;
   GrdOnTimer(rp_now);
   ck(!g_grd_guard && GrdEntryBlock(rp_now) != CR_SK_GUARD && x_listed(b.ticket) && x_listed(hd2) && x_count("MARK") == 0,
      "InpGuard false: equity at 50 % of ref latches nothing, the robot position stays, no mark");
   g_cfg.guard_off = false;
   x_reset("guard_off_history", t3 + 3600, 10000.0);
   x_quote(CR_XAU, 1800.0, 13);
   x_quote(CR_BTC, 40000.0, 20);
   CrIntent c = x_intent("BKB", 1, 0.01);
   BrkOpen(c, 39000.0);
   x_quote(CR_BTC, 40010.0, 20);
   rp_now += 5;
   BrkClose(c.ticket, CR_MAGIC_MARK, "guard");                 // a close with the mark's magic: GUARD (c) for the history
   rp_now += 5;
   LedRead(rp_now);
   rp_now += 3;
   LedRead(rp_now);
   bool on_latched = LedGuardLatched();
   g_cfg.guard_off = true;
   bool off_latched = LedGuardLatched() || LedGuardAt(ClkServerToUtc(rp_now) + 60);
   g_cfg.guard_off = false;
   ck(LedMarkSeen() && on_latched && !off_latched, "a mark in the history latches GUARD (c) with InpGuard true, nothing with false");
  }

//+------------------------------------------------------------------+
//| Push limits (S0's JrnPush with the hands' limits) and retries    |
//+------------------------------------------------------------------+
static void w_push()
  {
   long t = SV(2021, 6, 15, 10, 0, 0);
   x_reset("push", t, 1000.0);
   int sent = 0;
   for(int k = 0; k < 6; k++) sent += JrnPush("test " + std::to_string(k), true) ? 1 : 0;
   hand("N1", sent == 2 && rp_pushes == 2, "never more than 2 pushes in the same second; the others are journaled only");
   rp_now = t + 1;
   for(int k = 0; k < 6; k++) { rp_now = t + 1 + k; sent += JrnPush("u " + std::to_string(k), true) ? 1 : 0; }
   long urgent_n = rp_pushes;
   long p0 = rp_pushes;
   for(int k = 0; k < 6; k++) { rp_now = t + 120 + k; JrnPush("v " + std::to_string(k), false); }
   long plain_n = rp_pushes - p0;
   hand("N2", urgent_n == 5 && plain_n == 3, F("never more than 5 pushes in a minute, the last 2 kept for the urgent ones (%ld urgent, "
                                               "%ld others)", urgent_n, plain_n));
   // N3: the warning that positions cannot be closed, dropped by the limit, is pushed again at the next attempt
   x_reset("push_n3", SV(2021, 6, 15, 10, 1, 0), 1000.0);
   x_quote(CR_XAU, 1800.0, 13);
   CrIntent a = x_intent("ORX", 1, 0.01);
   BrkOpen(a, 1790.0);
   g_grd_stop = true;
   JrnPush("a", true);
   JrnPush("b", true);                                         // the second's two pushes are used
   x_fault("refuse_close", {"10018", "5", "0"});
   GrdOnTimer(rp_now);
   long w1 = x_pushes_with("ATTENTION");
   rp_now += 60;
   GrdOnTimer(rp_now);
   long w2 = x_pushes_with("ATTENTION");
   hand("N3", w1 == 0 && w2 == 1, "the warning that positions cannot be closed is not lost when the push limit is used: pushed at the "
        "next attempt");
   // R19: the clock steps back an hour while a forced close waits for its retry: the retries go on
   rp_now -= 3600;
   x_fault("refuse_close", {"10006", "0", "0"});
   for(MfAct &m : mf_acts) m.left = 0;
   GrdOnTimer(rp_now);
   hand("R19", !x_listed(a.ticket), "the server clock steps back an hour while a forced close waits for its retry: the retry still comes");
  }

//+------------------------------------------------------------------+
//| Ledger: the reference of SPEC 5 (K7-K19, X4-X8 rewritten), D7     |
//+------------------------------------------------------------------+
static double x_gain(double amount, long magic = 777)          // money that is not a payment (a hand trade's result)
  {
   ulong ord = rp_add_order("XAUUSD.r", 0, ORDER_STATE_FILLED, 0, magic, 1.0, 1800.0, 0, 0, "");
   RpPos p = {ord, "XAUUSD.r", 0, 1.0, 1800.0, 0, 0, magic, rp_now, ""};
   rp_add_deal(p, 0, DEAL_ENTRY_IN, 1.0, 1800.0, DEAL_REASON_CLIENT, magic, rp_now, 0.0, 0.0, ord, "");
   rp_now += 1;
   rp_add_deal(p, 1, DEAL_ENTRY_OUT, 1.0, 1800.0, DEAL_REASON_CLIENT, magic, rp_now, amount, 0.0, ord, "");
   rp_now += 1;
   return rp_balance;
  }
static void x_pay(double amount)
  {
   RpPay p = {rp_now, rp_now, amount, false};
   rp_pays.push_back(p);
   rp_book_payments(rp_now);
   rp_now += 1;
  }
static bool x_settle()
  {
   LedRead(rp_now);
   rp_now += 2;
   LedRead(rp_now);
   return LedSettled();
  }

static void w_reference()
  {
   // the plan from the first deal on a demo account: B(T) = 1000 (an opening deposit), then the hands' sequences
   struct Case { const char *id; std::vector<std::pair<char, double>> ops; double ref, paid; bool guard; const char *what; };
   std::vector<Case> cases = {
      {"K7", {{'g', 300}, {'p', -300}}, 1000.0 * 1000.0 / 1300.0, 1000, false,
       "gains withdrawn (1000 grown to 1300, 300 withdrawn): ref x 1000/1300 = 769.23 (SPEC 5: a withdrawal moves neither B/ref nor "
       "the rung); the hands kept 1000"},
      {"K8", {{'g', 2000}, {'p', -2600}}, 1000.0 * 400.0 / 3000.0, 1000, false,
       "most withdrawn (3000 -> 400): ref 133.33, no guard; the hands put the reference at what was left"},
      {"K9", {{'g', -300}, {'p', 300}}, 1300.0, 1300, false, "a deposit after a loss (700 + 300): ref = max(1000 + 300, 1000) = 1300"},
      {"K10", {{'g', 500}, {'p', 500}}, 2000.0, 1500, false, "a deposit after gains (1500 + 500): ref = max(1500, 2000) = 2000"},
      {"K11", {{'p', -600}}, 400.0, 1000, false, "600 of 1000 withdrawn: ref 400, never a guard on a withdrawal"},
      {"K16", {{'c', -30}, {'r', 10}, {'k', 500}, {'b', 500}, {'g', -0.32}}, 1000.0, 1000, false,
       "a charge, a correction, a credit, a bonus and trades move B, never ref (only DEAL_TYPE_BALANCE does)"},
      {"K17", {{'g', 2000}, {'p', -2600}, {'p', 600}}, 0.0, 1600, false,
       "a withdrawal then a deposit seen in the same read: each against the balance right after it"},
      {"X4", {{'p', -1000}, {'p', 200}}, 200.0, 1200, false, "everything withdrawn then 200 deposited: ref = 200"},
      {"X6", {{'g', 2000}, {'p', -2600}, {'p', -390}}, 1000.0 * 400.0 / 3000.0 * 10.0 / 400.0, 1000, false,
       "a withdrawal larger than ref in two steps: ref never below 0 (here 3.33), the guard still works"},
   };
   for(Case &c : cases)
     {
      long t = SV(2021, 6, 15, 10, 0, 0);
      x_reset(string("ref_") + c.id, t, 0.0);
      x_pay(1000.0);                                           // the opening payment: the first deal (T on a demo account)
      x_settle();
      double ref = 1000.0, eq = 1000.0, paid = 1000.0;
      for(auto &op : c.ops)
        {
         if(op.first == 'g') { x_gain(op.second); eq += op.second; }
         else if(op.first == 'p')
           {
            double before = eq;
            x_pay(op.second);
            eq += op.second;
            if(op.second > 0) { paid += op.second; ref = std::max(ref + op.second, eq); }
            else if(before > 0) ref = ref * eq / before;
           }
         else
           {
            int type = op.first == 'c' ? DEAL_TYPE_CHARGE : (op.first == 'r' ? DEAL_TYPE_CORRECTION : (op.first == 'k' ? DEAL_TYPE_CREDIT : DEAL_TYPE_BONUS));
            RpDeal d = {rp_next_deal++, 0, 0, rp_now, "", type, DEAL_ENTRY_IN, 0.0, 0.0, 0, 0, "", 0.0, 0.0, op.second};
            rp_deals.push_back(d);
            if(type != DEAL_TYPE_CREDIT) { rp_balance += op.second; eq += op.second; }
            rp_now += 1;
           }
        }
      if(c.ref == 0.0) c.ref = ref;
      bool ok = x_settle();
      bool good = ok && std::fabs(LedRefNow() - c.ref) < 1e-6 && std::fabs(LedRefNow() - ref) < 1e-6 && std::fabs(LedPaidInNow() - paid) < 1e-6
                  && std::fabs(LedBalanceNow() - eq) < 1e-6 && LedGuardLatched() == c.guard;
      hand(c.id, good, string(c.what) + F(" [ref %.4f, P_in %.2f, B %.2f]", LedRefNow(), LedPaidInNow(), LedBalanceNow()));
     }
   // X8: the daily lock's baseline after a deposit and a withdrawal: B at the day's start; payments are never losses
     {
      x_reset("ref_X8", SV(2021, 6, 14, 10, 0, 0), 0.0);
      g_cfg.lock_stakes = 1.0;
      x_pay(1000.0);
      x_settle();
      rp_now = SV(2021, 6, 15, 9, 0, 0);
      x_pay(500.0);
      x_pay(-200.0);
      bool s8 = x_settle();
      bool no_lock = s8 && !LedDayLocked(rp_now) && std::fabs(LedRefNow() - 1300.0) < 1e-6;
      x_quote(CR_XAU, 1800.0, 13);
      CrIntent a = x_intent("ORX", 1, 0.02);
      BrkOpen(a, 1794.0);                                      // -11.01 EUR at the stop: more than 1 stake of 1 % x 1000 (B at 00:00)
      rp_close_at(rp_pos_index(a.ticket), 1794.0, DEAL_REASON_SL, rp_now + 30, 0);
      rp_now += 120;
      x_settle();
      datetime d0 = ClkServerToUtc(ClkServerDay((datetime)rp_now));
      double day_cm = LedCloseMoney(ClkServerToUtc(rp_now)) - LedCloseMoney(d0);
      bool lock = LedDayLocked(rp_now) && day_cm < -11.0 && day_cm > -11.02 && std::fabs(LedBalance(d0) - 1000.0) < 1e-6;
      hand("X8", no_lock && lock, F("the daily-loss baseline after a deposit (500) and a withdrawal (200): B at the day's start (%.2f), "
                                    "payments never count as a loss (no lock), the robot's -11.01 does (lock); ref 1300 (SPEC 5)",
                                    LedBalance(d0)));
     }
   // K12 / K19: counted once across re-reads, rebuilds and any list order
   x_reset("ref_K12", SV(2021, 6, 15, 10, 0, 0), 0.0);
   x_pay(1500.0);
   x_settle();
   x_pay(100.0);
   x_pay(200.0);
   x_pay(-50.0);
   x_settle();
   double r1 = LedRefNow();
   LedReset();
   x_settle();
   double r2 = LedRefNow();
   std::reverse(rp_deals.begin(), rp_deals.end());
   LedReset();
   x_settle();
   double r3 = LedRefNow();
   double want = std::max(1500.0 + 100.0, 1600.0);
   want = std::max(want + 200.0, 1800.0);
   want = want * 1750.0 / 1800.0;
   hand("K12", std::fabs(r1 - want) < 1e-6 && r1 == r2, F("an operation is counted once, also after a rebuild: ref %.4f", r1));
   hand("K19", r1 == r3, "the history listed newest first: the same ledger (events are sorted by time, kind, position)");
   // K15: a deposit while a position is open: the balance right after it, not the equity (P10)
   x_reset("ref_K15", SV(2021, 6, 15, 10, 0, 0), 0.0);
   x_pay(1000.0);
   x_settle();
   x_quote(CR_XAU, 1800.0, 13);
   x_hand(CR_XAU, 1, 0.02, 777);
   x_quote(CR_XAU, 1850.0, 13);                                // +88 EUR floating
   x_pay(100.0);
   x_settle();
   hand("K15", std::fabs(LedRefNow() - 1100.0) < 1e-6, F("a deposit with a position open: ref = max(1000 + 100, balance 1100) = %.2f "
                                                          "(the hands took the equity, P10)", LedRefNow()));
   // K18: the history is not read at every pass: once a minute, after a transaction, every second while unsettled
   x_reset("ref_K18", SV(2021, 6, 15, 10, 0, 0), 0.0);
   x_pay(1000.0);
   x_settle();
   long r0 = g_led_reads;
   for(int k = 0; k < 40; k++) { rp_now += 1; LedOnTimer(rp_now); }
   hand("K18", g_led_reads - r0 <= 1, F("%ld reads of the history in 40 idle passes", g_led_reads - r0));
   // K13/K14/X7: a later plan start clears the latches and B(T) = the balance then
   x_reset("ref_X7", SV(2021, 6, 15, 10, 0, 0), 0.0);
   x_pay(1000.0);
   x_settle();
   x_gain(-600.0);                                             // B 400 <= 50 % of ref: GUARD (b)
   x_settle();
   bool latched = LedGuardLatched();
   x_pay(1000.0);
   x_pay(-200.0);
   x_settle();
   g_cfg.plan_start = rp_now + 10;
   rp_now += 20;
   string e7;
   LedInit(e7);                                                // a changed input restarts the EA (OnInit)
   x_settle();
   hand("X7", latched && !LedGuardLatched() && std::fabs(LedBT() - 1200.0) < 1e-6 && std::fabs(LedRefNow() - 1200.0) < 1e-6,
        F("a later InpPlanStart clears STOP and GUARD: B(T) = the balance then (%.2f), earlier operations forgotten", LedBT()));
   hand("K13", latched, "the guard's latch after a loss stays in the history (no file or global variable is needed)");
   hand("K14", std::fabs(LedBT() - 1200.0) < 1e-6, "InpStartBalance is gone: B(T) comes from the balance at the plan start");
   // D7: a broker stop deal with magic 0 is still the robot's (attached by position id); a hand position's stop is not
   long t = SV(2021, 6, 14, 10, 0, 0);
   x_reset("ref_D7", t, 0.0);
   g_cfg.lock_stakes = 1.0;                                    // 1 stake: 1 % of 1000 = 10 EUR (table 0:1 in these worlds)
   x_pay(1000.0);
   x_settle();
   rp_now = SV(2021, 6, 15, 10, 0, 0);
   x_settle();
   ck(!LedDayLocked(rp_now), "no lock before the stop");
   x_quote(CR_XAU, 1800.0, 13);
   CrIntent a = x_intent("ORX", 1, 0.02);
   BrkOpen(a, 1794.0);
   long ia = rp_pos_index(a.ticket);
   rp_close_at(ia, 1794.0, DEAL_REASON_SL, rp_now + 30, 0);    // the stop deal carries magic 0: -10.68 EUR
   ulong hd = x_hand(CR_XAU, 1, 0.05, 777);
   rp_close_at(rp_pos_index(hd), 1700.0, DEAL_REASON_SL, rp_now + 40, 0);   // a hand position stopped: -445 EUR, not the robot's
   rp_now += 60;
   x_settle();
   bool locked = LedDayLocked(rp_now);
   CrLedPos p;
   bool robot = false;
   for(int k = 0; k < LedPosCount(); k++)
      if(LedPosAt(k, p) && p.id == (long)a.ticket) robot = p.robot && p.closed;
   hand("D7", locked && robot && std::fabs(LedCloseMoney(ClkServerToUtc(rp_now)) - (-(1800.13 * (1 + 0.3e-4) - 1794.0) * 100 * 0.89 * 0.02)) < 0.01,
        F("the daily lock counts a stop deal of magic 0 as the robot's (by position id), not a hand position's stop (close money %.2f)",
          LedCloseMoney(ClkServerToUtc(rp_now))));
  }

#ifdef CR_EXEC_SIZING
//+------------------------------------------------------------------+
//| Sizing ports (O7-O11): CR_Sizing on the mock's broker            |
//+------------------------------------------------------------------+
static void w_sizing()
  {
   long t = SV(2021, 6, 15, 10, 0, 0);
   x_reset("sizing", t, 0.0);
   g_cfg.risk_table = "0:1";
   string err;
   ck(SizInit(err), "SizInit " + err);
   x_pay(1000.0);
   x_settle();
   for(int s = 0; s < CR_NSYM; s++) x_quote(s, s == CR_XAU ? 1800.0 : (s == CR_IDX ? 14000.0 : (s == CR_BTC ? 40000.0 : 2500.0)), 13);
   // O7: lots = floor(B x rate / per_lot / step) x step; the real loss at the stop stays within the budget (+ fill slippage)
   CrIntent it = x_intent("ORX", 1, 0.0);
   it.stop_dist = 5.0;
   it.quote = 1800.13;
   int sk = SizSize(it, it.stamp, false);
   double per_lot = 5.0 * (0.01 * 100 * 0.89 / 0.01);
   double want = std::floor(1000.0 * 1.0 / 100.0 / per_lot / 0.01 + 1e-9) * 0.01;
   bool o7 = sk == CR_SK_NONE && std::fabs(it.lots - want) < 1e-12 && std::fabs(it.budget - 10.0) < 1e-9;
   double st = BrkGridStop(CR_XAU, (1800.13 * (1 + 0.3e-4)) - 5.0, 1);
   int r = BrkOpen(it, st);
   long ip = rp_pos_index(it.ticket);
   if(r == CR_SEND_OK && ip >= 0)
     {
      rp_close_at(ip, st, DEAL_REASON_SL, rp_now + 30, 20261210);
      double loss = -rp_deals.back().profit;
      o7 &= loss <= it.budget * 1.25 && std::fabs(loss - g_brk_risk) < 0.01;
     }
   hand("O7", o7, F("lots from the budget (1 %% of 1000 = 10 EUR, 5.00 of stop: %.2f lot); the loss at the broker stop equals the risk "
                    "computed at the fill, within 1.25 x the budget", want));
   // O8: even the minimum lot risks too much: MIN_LOT, never rounded up
   CrIntent m = x_intent("GFP", 1, 0.0);
   m.stop_dist = 20.0;
   m.quote = 1800.13;
   hand("O8", SizSize(m, m.stamp, false) == CR_SK_MIN_LOT && m.lots == 0.0, "the minimum lot would risk more than the budget: MIN_LOT "
        "skip, never rounded up");
   // O10: at most 2 robot positions per market; the hands' and manual positions do not count
   x_reset("sizing_caps_sym", t, 0.0);
   g_cfg.risk_table = "0:1";
   SizInit(err);
   x_pay(100000.0);
   x_settle();
   for(int s = 0; s < CR_NSYM; s++) x_quote(s, s == CR_XAU ? 1800.0 : (s == CR_IDX ? 14000.0 : (s == CR_BTC ? 40000.0 : 2500.0)), 13);
   const char *two[] = {"GFP", "D4H"};
   for(const char *c : two)
     {
      CrIntent o = x_intent(c, 1, 0.01);
      BrkOpen(o, 1782.0);
     }
   x_hand(CR_IDX, 1, 0.1, 777);
   x_hand(CR_IDX, 1, 0.1, 20261110);
   x_hand(CR_IDX, -1, 0.1, 0);
   rp_now += 60;
   x_settle();
   CrIntent g3 = x_intent("ORX", 1, 0.0);
   g3.stop_dist = 5.0;
   g3.quote = 1800.13;
   CrIntent n3 = x_intent("N30", 1, 0.0);
   n3.stop_dist = 20.0;
   n3.quote = 14000.13;
   int k10 = SizSize(g3, (datetime)ClkServerToUtc(rp_now), false), k10b = SizSize(n3, (datetime)ClkServerToUtc(rp_now), false);
   hand("O10", k10 == CR_SK_CAP && k10b == CR_SK_NONE, F("at most 2 robot positions per market: a third on gold is CAP (%s); US100 with 3 "
                                                         "positions of the hands, by hand and of another robot is sized (%s)",
                                                         SizSkipName(k10).c_str(), SizSkipName(k10b).c_str()));
   // O9: at most 6 robot positions in all
   x_reset("sizing_caps", t, 0.0);
   g_cfg.risk_table = "0:1";
   SizInit(err);
   x_pay(100000.0);
   x_settle();
   for(int s = 0; s < CR_NSYM; s++) x_quote(s, s == CR_XAU ? 1800.0 : (s == CR_IDX ? 14000.0 : (s == CR_BTC ? 40000.0 : 2500.0)), 13);
   const char *codes[] = {"GFP", "D4H", "BKB", "F1B", "BKE", "F1E"};
   for(const char *c : codes)
     {
      CrIntent o = x_intent(c, 1, 0.01);
      int s = g_sl[CrSleeveOfCode(c)].sym;
      BrkOpen(o, rp_syms[s].tick_bid * 0.99);
     }
   rp_now += 60;
   x_settle();
   CrIntent n7 = x_intent("N30", 1, 0.0);
   n7.stop_dist = 20.0;
   n7.quote = 14000.13;
   int k9 = SizSize(n7, (datetime)ClkServerToUtc(rp_now), false);
   hand("O9", k9 == CR_SK_CAP && BrkRobotCount() == 6, F("at most 6 robot positions in all: with 6 open (2 gold, 2 BTC, 2 ETH) an "
                                                         "entry on US100 is CAP (%s)", SizSkipName(k9).c_str()));
   // O11: margin: the sum of OrderCalcMargin of the open positions and the new one above B -> MARGIN
   x_reset("sizing_margin", t, 0.0);
   g_cfg.risk_table = "0:5";
   SizInit(err);
   x_pay(1000.0);
   x_settle();
   x_quote(CR_BTC, 40000.0, 13);
   x_quote(CR_ETH, 2500.0, 13);
   CrIntent pre = x_intent("BKE", 1, 1.0);
   BrkOpen(pre, 2400.0);                                       // 1 lot of ETH: 2,500 x 0.89 / 50 = 44.50 EUR of margin
   rp_now += 60;
   x_settle();
   // 5 % of 1000 = 50 EUR over 40.00 of stop (35.60 EUR a lot): 1.40 lot of BTC = 996.80 EUR of margin; with the ETH: 1041.30 > B
   CrIntent mg = x_intent("BKB", 1, 0.0);
   mg.stop_dist = 40.0;
   mg.quote = 40000.13;
   int sm = SizSize(mg, (datetime)ClkServerToUtc(rp_now), false);
   rp_close_at(rp_pos_index(pre.ticket), 2500.0, DEAL_REASON_EXPERT, rp_now, 20261204);
   rp_now += 120;
   x_settle();
   CrIntent mg2 = x_intent("BKB", 1, 0.0);
   mg2.stop_dist = 40.0;
   mg2.quote = 40000.13;
   int sm2 = SizSize(mg2, (datetime)ClkServerToUtc(rp_now), false);
   hand("O11", sm == CR_SK_MARGIN && sm2 == CR_SK_NONE && std::fabs(mg2.lots - 1.40) < 1e-9,
        F("the margin of the open robot positions and the new one above B (44.50 + 996.80 > 1000): MARGIN skip (%s); the ETH position "
          "closed: %.2f lot taken (%s)", SizSkipName(sm).c_str(), mg2.lots, SizSkipName(sm2).c_str()));
  }
#endif

int main(int argc, char **argv)
  {
   bool hands_mode = argc > 1 && string(argv[1]) == "hands";
   if(argc > 1 && !hands_mode) g_dir = argv[1];
   if(argc > 2 && hands_mode) g_dir = argv[2];
   rp_quiet = 1;
   w_grid();
   w_tick();
   w_resolve();
   w_open_checks();
   w_postfill();
   w_close_modify();
   w_intent_check();
   w_lock();
   w_clock();
   w_friday();
   w_guard_live();
   w_push();
   w_reference();
#ifdef CR_EXEC_SIZING
   w_sizing();
#endif
   JrnClose();
   if(rp_log) fclose(rp_log);
   if(hands_mode)
      for(const XHand &h : g_hands) printf("HANDS %s %s %s\n", h.id.c_str(), h.state == 1 ? "PASS" : (h.state == 2 ? "PART" : "FAIL"), h.what.c_str());
   printf("test_exec: %d checks, %d failed%s\n", g_checks, g_fails, g_fails ? "" : " - all worlds pass");
   for(const auto &kv : g_wfail) printf("  failed in %s: %d\n", kv.first.c_str(), kv.second);
   return g_fails ? 1 : 0;
  }
