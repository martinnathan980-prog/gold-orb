// T7a account: CR_Ledger and CR_Sizing (SPEC 5, 6; step I) in the replay mock's broker; no argument = the unit worlds
// build: entry=src/CR_Sizing.mqh subst=CR_Clock.mqh=check/dbl/CR_Clock_dbl.mqh
//
// Modes (check/test_account.py drives the last two):
//   test_account [DIR]        the unit worlds below (journals under DIR, default check/out/test_account/unit); exit 0
//                             when every check holds. Built with -DCR_NO_GUARD the GUARD worlds expect no latch.
//   test_account rows         the symbol and sleeve rows of this test, one per line (test_account.py compares them with
//                             src/CR_Registry.mqh and lab/r2/fp_costs.json)
//   test_account t7a TRADES PAYS WEEKS TABLE OUT [SKEW]
//                             T7a: the lab's trades (TRADES: i,t_in,t_out,time_exit,code,side,entry,risk,pnl, UTC
//                             seconds, the lab's order) and payments (PAYS: t,amount) through the mock broker. Every
//                             entry is a market intent sized by SizSize (stop_dist = the lab's risk, quote = the lab's
//                             fill); a taken trade opens a position (IN deal) and closes at its lab exit (OUT deal:
//                             SL in the minute before a stop-type exit stamp, an EA close at a time exit), with the
//                             lab's money pnl x lots x units x 0.89. After a plan stop the world does what the lab
//                             does (growth.py:194, 261-265): no more payments, and the positions still open at the
//                             next entry are dropped. Writes OUT/trades.csv, OUT/weeks.csv (B and P_in at each end of
//                             the WEEKS rows), OUT/summary.txt and the journal (SIZE lines) under OUT/ClaudeRobot.
//                             SKEW = s <= 0: each payment's deal is in the history s seconds before the balance shows
//                             it (R16); a sizing that meets SETTLE is asked again 2 s later, inside its 5-minute
//                             window, as the follower does.
// The module's state is the EA's own (translated src/CR_Sizing.mqh and src/CR_Ledger.mqh, the clock double of S0).
#include "mock_replay.h"
#include "ea.cpp"
#include <algorithm>
#include <cinttypes>
#include <cmath>
#include <cstdarg>
#include <map>
#include <string>
#include <vector>

// ------------------------------------------------------------------ the rows of CR_Registry RegInit (checked by the .py)
struct WSym
  {
   const char *name, *base, *lab;
   int family, comm_pts;
   double mkt, stop;
   int depth;
   double model_bp, units, vmin, vstep, lev;
  };
// broker specs: lab/r2/fp_costs.json (units per lot, minimum lot, lot step, leverage), the mock's defaults
static const WSym W_SYM[CR_NSYM] = {
   {"XAUUSD.r", "XAUUSD", "xauusd", CR_FAM_XAU, CR_XAU_COMM_PTS, 0.3, 1.0, 120, 0.47, 100.0, 0.01, 0.01, 500.0},
   {"US100.r", "US100", "us100", CR_FAM_IDX, 0, 0.2, 0.5, 60, 0.37, 1.0, 0.1, 0.1, 200.0},
   {"BTCUSD.r", "BTCUSD", "btcusd", CR_FAM_CRY, 0, 0.5, 1.5, 60, 2.96, 1.0, 0.01, 0.01, 50.0},
   {"ETHUSD.r", "ETHUSD", "ethusd", CR_FAM_CRY, 0, 0.7, 2.0, 60, 13.0, 1.0, 0.01, 0.01, 50.0}};
struct WSl
  {
   int id;
   const char *code, *lab;
   int kind, slot, sym, sym2, change;
   double factor;
   int refuse;
  };
static const WSl W_SL[10] = {
   {1, "N30", "noise30_us100", CR_K_N30, 0, CR_IDX, -1, CR_CH_NONE, 1.0, CR_REF_NONE},
   {2, "OC4", "ocm4_us100", CR_K_OC4, 0, CR_IDX, -1, CR_CH_NONE, 1.0, CR_REF_NONE},
   {3, "BKB", "brk72_24h_wd_btcusd", CR_K_BRK72, 0, CR_BTC, -1, CR_CH_S075, 0.771793, CR_REF_PAYOFF},
   {4, "BKE", "brk72_24h_wd_ethusd", CR_K_BRK72, 1, CR_ETH, -1, CR_CH_K1, 1.0, CR_REF_SB},
   {5, "F1B", "F1_brk_ridge_filter_btcusd", CR_K_F1, 0, CR_BTC, -1, CR_CH_NONE, 1.0, CR_REF_NONE},
   {6, "F1E", "F1_brk_ridge_filter_ethusd", CR_K_F1, 1, CR_ETH, -1, CR_CH_H2, 0.750978, CR_REF_PAYOFF},
   {7, "NQB", "nq_btc_follow_btcusd", CR_K_NQB, 0, CR_BTC, CR_IDX, CR_CH_NONE, 1.0, CR_REF_NONE},
   {8, "GFP", "GOLD_FRI_PM_xauusd", CR_K_GFP, 0, CR_XAU, -1, CR_CH_NONE, 1.0, CR_REF_NONE},
   {9, "D4H", "donch4h_stop_xauusd", CR_K_D4H, 0, CR_XAU, -1, CR_CH_NONE, 1.0, CR_REF_NONE},
   {10, "ORX", "orb_asia_2d_buf10_xauusd", CR_K_ORX, 0, CR_XAU, -1, CR_CH_NONE, 1.0, CR_REF_NONE}};
static const double W_USDEUR = 0.89;           // account.py USD_EUR, the mock's rp_usdeur
static const char *F3S = "0:3;3000:2;6000:1;12000:0.5";

static void ea_rows()
  {
   for(int s = 0; s < CR_NSYM; s++)
     {
      g_sym[s].base = W_SYM[s].base;
      g_sym[s].lab = W_SYM[s].lab;
      g_sym[s].name = W_SYM[s].name;
      g_sym[s].family = W_SYM[s].family;
      g_sym[s].digits = 2;
      g_sym[s].point = 0.01;
      g_sym[s].comm_pts = W_SYM[s].comm_pts;
      g_sym[s].h = W_SYM[s].comm_pts * 0.5 * 0.01;     // RegSetPoint: comm_pts / 2 x point
      g_sym[s].slip_mkt = W_SYM[s].mkt * 1e-4;
      g_sym[s].slip_stop = W_SYM[s].stop * 1e-4;
      g_sym[s].depth_days = W_SYM[s].depth;
      g_sym[s].model_bp = W_SYM[s].model_bp;
      g_sym[s].ok = true;
     }
   g_nsl = 0;
   for(int k = 0; k < 10; k++)
     {
      CrSleeveInfo &r = g_sl[g_nsl];
      r.id = W_SL[k].id;
      r.code = W_SL[k].code;
      r.lab = W_SL[k].lab;
      r.kind = W_SL[k].kind;
      r.slot = W_SL[k].slot;
      r.sym = W_SL[k].sym;
      r.sym2 = W_SL[k].sym2;
      r.change = W_SL[k].change;
      r.factor_on = W_SL[k].factor;
      r.refuse_on = W_SL[k].refuse;
      r.change_on = false;
      r.allowed = true;
      r.magic = CR_MAGIC_BASE + W_SL[k].id;
      g_nsl++;
     }
  }

static int mode_rows()
  {
   ea_rows();
   for(int s = 0; s < CR_NSYM; s++)
      printf("sym %d %s %s %d %d %.17g %.17g %d %.17g %.17g %.17g %.17g %.17g\n", s, W_SYM[s].base, W_SYM[s].lab, W_SYM[s].family,
             W_SYM[s].comm_pts, W_SYM[s].mkt, W_SYM[s].stop, W_SYM[s].depth, W_SYM[s].model_bp, W_SYM[s].units, W_SYM[s].vmin,
             W_SYM[s].vstep, W_SYM[s].lev);
   for(int k = 0; k < g_nsl; k++)
      printf("sleeve %d %s %s %d %d %d %d %d %.17g %d %ld\n", g_sl[k].id, g_sl[k].code.c_str(), g_sl[k].lab.c_str(), g_sl[k].kind,
             g_sl[k].slot, g_sl[k].sym, g_sl[k].sym2, g_sl[k].change, g_sl[k].factor_on, g_sl[k].refuse_on, g_sl[k].magic);
   return 0;
  }

// ------------------------------------------------------------------ checks
static int g_checks = 0, g_fails = 0;
static string g_world = "";
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
static void ck(bool c, const string &what)
  {
   g_checks++;
   if(!c)
     {
      g_fails++;
      fprintf(stderr, "FAIL [%s] %s\n", g_world.c_str(), what.c_str());
     }
  }
static void ckeq(double got, double want, const string &what) { ck(got == want, what + F(": got %.17g, want %.17g", got, want)); }
static void cknear(double got, double want, double tol, const string &what)
  {
   ck(std::fabs(got - want) <= tol, what + F(": got %.17g, want %.17g", got, want));
  }
static void ckint(long got, long want, const string &what) { ck(got == want, what + F(": got %ld, want %ld", got, want)); }

// ------------------------------------------------------------------ the mock world (broker side)
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
static long U(long srv) { return (long)ClkServerToUtc(srv); }

static void w_syms()
  {
   rp_syms.clear();
   for(int s = 0; s < CR_NSYM; s++)
     {
      RpSym x;
      x.name = W_SYM[s].name;
      x.digits = 2;
      x.point = 0.01;
      x.units = W_SYM[s].units;
      x.vmin = W_SYM[s].vmin;
      x.vstep = W_SYM[s].vstep;
      x.lev = W_SYM[s].lev;
      x.slip_mkt = W_SYM[s].mkt * 1e-4;
      x.slip_stop = W_SYM[s].stop * 1e-4;
      x.comm = 0.0;
      rp_syms.push_back(x);
     }
  }

static void w_clear_logs(const string &dir)
  {
   rp_root = dir;
   rp_mkdirs(rp_path("ClaudeRobot"));
   if(DIR *d = opendir(rp_path("ClaudeRobot").c_str()))
     {
      std::vector<string> old;
      while(dirent *e = readdir(d))
         if(strstr(e->d_name, ".log")) old.push_back(rp_path("ClaudeRobot") + "/" + e->d_name);
      closedir(d);
      for(const string &p : old) remove(p.c_str());
     }
  }

// a fresh broker, configuration and ledger
static bool w_reset(double balance, long now_srv, bool demo, long plan_start, const string &table)
  {
   JrnClose();
   rp_deals.clear();
   rp_orders.clear();
   rp_pays.clear();
   rp_pos.clear();
   rp_tx.clear();
   rp_scripted.clear();
   rp_open_orders.clear();
   rp_balance = balance;
   rp_now = now_srv;
   rp_ms = 0;
   rp_next_ticket = 70000001;
   rp_next_deal = 80000001;
   rp_account_mode = demo ? ACCOUNT_TRADE_MODE_DEMO : ACCOUNT_TRADE_MODE_REAL;
   w_syms();
   g_cfg = CrConfig();
   g_cfg.harness = true;
   g_cfg.push = true;
   g_cfg.demo = demo;
   g_cfg.trade = true;
   g_cfg.plan_start = plan_start;
   g_cfg.risk_table = table;
   g_cfg.stop_fall_pct = 25.0;
   g_cfg.stop_arm_paid = 12000.0;
   g_cfg.lock_stakes = 0.0;
   ea_rows();
   JrnInit();
   string err;
   bool ok = SizInit(err);
   if(ok) ok = LedInit(err);
   if(!ok) fprintf(stderr, "w_reset: %s\n", err.c_str());
   return ok;
  }

static void w_at(long t_srv)
  {
   rp_now = t_srv;
   rp_book_payments(rp_now);
   rp_deliver_tx();
  }

static ulong w_open(int sym, int side, double vol, double px, long magic, long t_srv, double comm)
  {
   ulong ticket = rp_next_ticket++;
   RpPos p = {ticket, rp_syms[sym].name, side > 0 ? 0 : 1, vol, px, 0.0, 0.0, magic, t_srv, ""};
   rp_pos.push_back(p);
   rp_add_deal(p, p.type, DEAL_ENTRY_IN, vol, px, DEAL_REASON_EXPERT, magic, t_srv, 0.0, comm, ticket, "");
   rp_deliver_tx();
   return ticket;
  }

static void w_close(ulong ticket, double profit, int reason, long magic, long t_srv, double comm, double swap)
  {
   long i = rp_pos_index(ticket);
   if(i < 0)
     {
      ck(false, F("w_close: no position %lu", ticket));
      return;
     }
   RpPos p = rp_pos[i];
   rp_add_deal(p, p.type == 0 ? 1 : 0, DEAL_ENTRY_OUT, p.volume, p.price_open, reason, magic, t_srv, profit, comm, ticket, "");
   rp_deals.back().swap = swap;
   rp_balance += swap;
   rp_pos.erase(rp_pos.begin() + i);
   rp_deliver_tx();
  }

// a balance operation (SPEC 5 payments): booked at t_deal; the balance shows it `skew` seconds before (> 0) or after
static void w_pay(long t_deal, double amount, long skew)
  {
   RpPay p = {t_deal, t_deal - skew, amount, false};
   rp_pays.push_back(p);
   rp_book_payments(rp_now);
   rp_deliver_tx();
  }

// a deal without a position: a charge, a correction, a credit (a credit leaves the balance alone)
static void w_deal(long t_srv, int type, double profit, long magic)
  {
   RpDeal d = {rp_next_deal++, 0, 0, t_srv, "", type, DEAL_ENTRY_IN, 0.0, 0.0, 0, magic, "", 0.0, 0.0, profit};
   rp_deals.push_back(d);
   if(type != DEAL_TYPE_CREDIT) rp_balance += profit;
  }

static bool w_ready()
  {
   LedRead(rp_now);
   rp_now += 2;
   int r = LedRead(rp_now);
   ck(r == CR_LED_OK && LedSettled(), "settled after two reads 2 s apart");
   return LedSettled();
  }

static CrIntent w_intent(const string &code, int side, int etype, long stamp, double stop, double stop_dist, double quote,
                         double paper_fill, int pre)
  {
   CrIntent it = CrIntent();
   it.sleeve = CrSleeveOfCode(code);
   it.oid = stamp * 100 + (it.sleeve >= 0 ? g_sl[it.sleeve].id : 0);
   it.side = side;
   it.etype = etype;
   it.stamp = stamp;
   it.send_until = stamp + 300;
   it.stop = stop;
   it.stop_dist = stop_dist;
   it.quote = quote;
   it.paper_fill = paper_fill;
   it.skip = pre;
   return it;
  }

// the lab's lots for one intent (growth.py:295-296), written out here on its own
static double lab_lots(double B, double rate, double m, double f, double r, int sym)
  {
   double tvl = 0.01 * W_SYM[sym].units * W_USDEUR, ts = 0.01;      // the mock's tick value and size
   double per_lot = r * (tvl / ts);
   double step = W_SYM[sym].vstep;
   return std::floor(B * rate * m * f / 100.0 / per_lot / step + 1e-9) * step;
  }

static double lab_pct(double key, const std::vector<double> &thr, const std::vector<double> &pct)     // growth.py:93-98
  {
   for(size_t k = 0; k < thr.size(); k++)
      if(key < thr[k]) return pct[k];
   return pct.back();
  }

static double lab_m(double w)                                                                          // stake.py:184-185
  {
   double m = 1.0;
   if(w > 0.0) m = std::min(m, std::max(0.25, w / 4.0));
   return m;
  }

// ------------------------------------------------------------------ unit worlds
static void u_tables()
  {
   g_world = "risk tables";
   MqlArray<double> fr, pc;
   int n = 0;
   string err;
   ck(SizParseTable(F3S, fr, pc, n, err) && n == 4 && fr[0] == 0 && fr[1] == 3000 && fr[2] == 6000 && fr[3] == 12000 && pc[0] == 3 &&
      pc[1] == 2 && pc[2] == 1 && pc[3] == 0.5, "F3S parses");
   ck(SizParseTable("0:2;6000:1;12000:0.5", fr, pc, n, err) && n == 3 && fr[1] == 6000 && pc[0] == 2 && pc[2] == 0.5, "F2S parses");
   ck(SizParseTable("0:1;12000:0.5", fr, pc, n, err) && n == 2 && fr[1] == 12000 && pc[0] == 1 && pc[1] == 0.5, "F1S parses");
   ck(SizParseTable(" 0 : 3 ; 3000 : 2 ", fr, pc, n, err) && n == 2 && pc[1] == 2, "spaces are allowed");
   ck(SizParseTable("0:3;3000:2;", fr, pc, n, err) && n == 2, "one ';' may end the list");
   ck(SizParseTable("0:5", fr, pc, n, err) && n == 1 && pc[0] == 5, "5 % is allowed");
   ck(SizParseTable("0:0.25;100.5:1.5", fr, pc, n, err) && n == 2 && fr[1] == 100.5 && pc[0] == 0.25, "decimals");
   const char *bad[] = {"", "  ", ";", "abc", "0:3;3000", "0:3:1", "100:3", "0:3;3000:2;2000:1", "0:3;3000:2;3000:1", "0:0", "0:-1",
                        "0:5.5", "0:6", "-0:3", "0:3;;3000:2", "0:3x", "0:1e1", "0:nan", "0:3;3000:2;;", "1e3:2", "0:3;6000",
                        "0:.", "0:3.0.1", "0:3,3000:2", "0;3", ":3", "0:"};
   for(const char *b : bad)
     {
      err = "";
      bool ok = SizParseTable(b, fr, pc, n, err);
      ck(!ok && err != "", F("refused: '%s'", b));
     }
   string many = "0:1";
   for(int k = 1; k <= 16; k++) many += ";" + std::to_string(k * 1000) + ":1";
   ck(!SizParseTable(many, fr, pc, n, err), "17 pairs are refused");
   // SizInit, and the rate against the lab's _pct on the boundaries and on random keys
   g_cfg = CrConfig();
   g_cfg.risk_table = "0:3;3000:abc";
   ck(!SizInit(err) && err != "", "SizInit refuses a bad table");
   struct Plan { const char *s; std::vector<double> thr, pct; };
   std::vector<Plan> plans = {{F3S, {3000.0, 6000.0, 12000.0}, {3.0, 2.0, 1.0, 0.5}},
                              {"0:2;6000:1;12000:0.5", {6000.0, 12000.0}, {2.0, 1.0, 0.5}},
                              {"0:1;12000:0.5", {12000.0}, {1.0, 0.5}}};
   uint64_t rng = 0x9E3779B97F4A7C15ULL;
   for(const Plan &p : plans)
     {
      g_cfg.risk_table = p.s;
      ck(SizInit(err), F("SizInit %s", p.s));
      std::vector<double> keys = {0.0, 1.0, 2999.99, 3000.0, 3000.01, 5999.99, 6000.0, 11999.99, 12000.0, 12000.01, 1e9};
      for(int k = 0; k < 2000; k++)
        {
         rng ^= rng << 13;
         rng ^= rng >> 7;
         rng ^= rng << 17;
         keys.push_back((double)(rng % 3000000) / 100.0);
        }
      int bad_n = 0;
      for(double key : keys)
         if(SizRate(key) != lab_pct(key, p.thr, p.pct)) bad_n++;
      ck(bad_n == 0, F("%s: SizRate equals growth._pct on %zu keys (%d differ)", p.s, keys.size(), bad_n));
     }
  }

static void u_m()
  {
   g_world = "m";
   std::vector<double> ws = {-1e9, -5.0, -1e-12, 0.0, 1e-12, 0.5, 0.999999, 1.0, 1.000001, 2.0, 3.2, 3.999999, 4.0, 4.000001, 10.0, 1e9};
   for(int k = 0; k < 400; k++) ws.push_back(-2.0 + k * 0.0173);
   int bad_n = 0;
   for(double w : ws)
      if(SizM(w) != lab_m(w)) bad_n++;
   ck(bad_n == 0, F("SizM equals the cushion rule on %zu values (%d differ)", ws.size(), bad_n));
   ckeq(SizM(0.0), 1.0, "m(0)");
   ckeq(SizM(0.5), 0.25, "m(0.5)");
   ckeq(SizM(3.0), 0.75, "m(3)");
   ckeq(SizM(8.0), 1.0, "m(8)");
  }

static void u_plan()
  {
   string err;
   // (a) a real account without InpPlanStart: UNSET, OBSERVE, no latch even after a fall of half
   g_world = "plan unset on a real account";
   w_reset(10000.0, SV(2021, 1, 11, 9, 0, 0), false, 0, F3S);
   w_ready();
   ckint(LedPlan(rp_now), CR_PLAN_UNSET, "LedPlan");
   ckint((long)LedPlanStart(), 0, "LedPlanStart");
   ulong tk = w_open(CR_XAU, 1, 0.5, 1850.0, 20261209, SV(2021, 1, 11, 9, 10, 2), 0.0);
   w_close(tk, -6000.0, DEAL_REASON_SL, 20261209, SV(2021, 1, 11, 9, 20, 30), 0.0, 0.0);
   w_at(SV(2021, 1, 11, 9, 30, 2));
   LedRead(rp_now);
   ck(!LedGuardLatched() && !LedStopLatched(), "no latch while the plan is unset");
   CrIntent it = w_intent("BKB", 1, CR_ET_MARKET, U(SV(2021, 1, 11, 9, 30, 0)), 0.0, 500.0, 30000.0, 0.0, CR_SK_NONE);
   ckint(SizSize(it, it.stamp, false), CR_SK_OBSERVE, "SizSize on an unset plan");
   ckeq(LedWeekUnit(it.stamp), 0.0, "OBSERVE sets no week unit");
   // (b) a demo account without InpPlanStart: T = the first deal (the opening deposit), B(T) = 0
   g_world = "plan 0 on a demo account";
   long t0 = SV(2021, 1, 4, 8, 0, 0);
   w_reset(0.0, t0, true, 0, F3S);
   w_pay(t0, 5000.0, 0);
   w_at(t0 + 10);
   w_ready();
   ckint(LedPlan(rp_now), CR_PLAN_OK, "LedPlan");
   ckint((long)LedPlanStart(), t0, "T = the first deal");
   ckeq(LedBT(), 0.0, "B(T) = 0 before the opening deposit");
   ckeq(LedPaidIn(U(t0)), 5000.0, "P_in counts the opening deposit");
   ckeq(LedBalance(U(t0)), 5000.0, "B at T");
   ckeq(LedRef(U(t0)), 5000.0, "ref at T");
   ckeq(LedBalance(U(t0) - 1), 0.0, "B before T");
   // (c) T still to come: FUTURE until T, then OK
   g_world = "plan start to come";
   long tf = SV(2021, 1, 11, 12, 0, 0);
   w_reset(10000.0, SV(2021, 1, 11, 9, 0, 0), true, tf, F3S);
   w_ready();
   ckint(LedPlan(rp_now), CR_PLAN_FUTURE, "LedPlan before T");
   ckint(LedPlanAt(U(rp_now)), CR_PLAN_FUTURE, "LedPlanAt before T");
   it = w_intent("BKB", 1, CR_ET_MARKET, U(SV(2021, 1, 11, 9, 0, 0)), 0.0, 500.0, 30000.0, 0.0, CR_SK_NONE);
   ckint(SizSize(it, it.stamp, false), CR_SK_OBSERVE, "OBSERVE before T");
   w_at(tf + 62);
   LedRead(rp_now);
   ckint(LedPlan(rp_now), CR_PLAN_OK, "LedPlan after T");
   it = w_intent("BKB", 1, CR_ET_MARKET, U(tf + 60), 0.0, 500.0, 30000.0, 0.0, CR_SK_NONE);
   ckint(SizSize(it, it.stamp, false), CR_SK_NONE, "sized after T");
   ckeq(LedBT(), 10000.0, "B(T) = the balance before T");
   // (d) a T after earlier manual losses: the history before T is one opening payment B(T) (R3)
   g_world = "plan start after manual losses";
   t0 = SV(2021, 1, 4, 8, 0, 0);
   long T = SV(2021, 1, 6, 0, 0, 0);
   for(int pass = 0; pass < 2; pass++)
     {
      w_reset(0.0, t0, true, pass == 0 ? T : 0, F3S);
      w_pay(t0, 12000.0, 0);
      ulong man = w_open(CR_XAU, 1, 1.0, 1850.0, 0, SV(2021, 1, 4, 10, 0, 0), 0.0);
      w_close(man, -3500.0, DEAL_REASON_CLIENT, 0, SV(2021, 1, 5, 10, 0, 0), 0.0, 0.0);
      w_at(SV(2021, 1, 7, 9, 0, 0));
      w_ready();
      ulong rob = w_open(CR_BTC, 1, 0.1, 30000.0, 20261203, SV(2021, 1, 7, 10, 0, 2), 0.0);
      w_close(rob, -300.0, DEAL_REASON_SL, 20261203, SV(2021, 1, 7, 11, 0, 30), 0.0, 0.0);
      w_at(SV(2021, 1, 7, 12, 0, 0));
      LedRead(rp_now);
      long S = U(SV(2021, 1, 7, 12, 0, 0));
      if(pass == 0)
        {
         ckeq(LedBT(), 8500.0, "B(T) = balance - deals at or after T");
         ckeq(LedPaidIn(S), 8500.0, "P_in = B(T)");
         ckeq(LedRef(S), 8500.0, "ref = B(T)");
         ckeq(LedBalance(S), 8200.0, "B after the robot loss");
         ck(!LedStopLatched() && !LedGuardLatched(), "no STOP (not armed) and no GUARD");
        }
      else
        {
         ckeq(LedBT(), 0.0, "demo, T = the first deal: B(T) = 0");
         ckeq(LedPaidIn(S), 12000.0, "P_in with the old deposit");
         ckeq(LedBalance(S), 8200.0, "B after the manual and the robot loss");
         ck(LedStopLatched(), "without a plan start the first robot close stops the robot (the R3 case)");
        }
     }
   // (e) credit deals are left out; a charge is other money (in B, not in P_in or ref)
   g_world = "credit and charge";
   w_reset(10000.0, SV(2021, 1, 11, 9, 0, 0), true, SV(2021, 1, 4, 0, 0, 0), F3S);
   w_ready();
   w_deal(SV(2021, 1, 11, 9, 5, 0), DEAL_TYPE_CREDIT, 500.0, 0);
   w_deal(SV(2021, 1, 11, 9, 6, 0), DEAL_TYPE_CHARGE, -5.0, 0);
   w_at(SV(2021, 1, 11, 9, 7, 0));
   LedRead(rp_now);
   long S = U(SV(2021, 1, 11, 9, 7, 0));
   ckeq(LedBT(), 10000.0, "B(T) leaves the credit out");
   ckeq(LedBalance(S), 9995.0, "B with the charge");
   ckeq(LedPaidIn(S), 10000.0, "P_in leaves the charge out");
   ckeq(LedRef(S), 10000.0, "ref leaves the charge out");
   ck(LedSettled(), "a credit does not unsettle the ledger");
   // input checks of LedInit
   g_world = "LedInit inputs";
   g_cfg.stop_fall_pct = 0.0;
   ck(!LedInit(err), "InpStopFallPct 0 refused");
   g_cfg.stop_fall_pct = 100.0;
   ck(!LedInit(err), "InpStopFallPct 100 refused");
   g_cfg.stop_fall_pct = 25.0;
   g_cfg.stop_arm_paid = -1.0;
   ck(!LedInit(err), "InpStopArmPaid < 0 refused");
   g_cfg.stop_arm_paid = 12000.0;
   g_cfg.lock_stakes = -1.0;
   ck(!LedInit(err), "InpDailyLockStakes < 0 refused");
   g_cfg.lock_stakes = 0.0;
   ck(LedInit(err), "good inputs accepted");
  }

static void u_stamps()
  {
   g_world = "stamps";
   w_reset(10000.0, SV(2021, 1, 11, 9, 0, 0), true, SV(2021, 1, 11, 0, 0, 0), F3S);
   w_ready();
   // a robot position closed by the broker's stop (magic 0) in minute 10:05: stamp 10:06 (UTC 08:06)
   ulong tk = w_open(CR_XAU, 1, 0.1, 1850.0, 20261209, SV(2021, 1, 11, 10, 0, 2), -0.25);
   w_at(SV(2021, 1, 11, 10, 1, 2));
   LedRead(rp_now);
   ckeq(LedBalance(U(SV(2021, 1, 11, 10, 1, 0))), 10000.0, "the opening commission waits for the close (one close event)");
   w_close(tk, -100.0, DEAL_REASON_SL, 0, SV(2021, 1, 11, 10, 5, 30), -0.25, -1.5);
   w_at(SV(2021, 1, 11, 10, 6, 1));
   LedRead(rp_now);
   ckeq(LedBalance(U(SV(2021, 1, 11, 10, 6, 0))), 10000.0, "an SL close in minute X is not known at X + 60");
   ckeq(LedBalance(U(SV(2021, 1, 11, 10, 7, 0))), 9898.0, "... and known at X + 120 (money = all its deals)");
   CrLedPos p;
   bool found = false;
   for(int k = 0; k < LedPosCount(); k++)
      if(LedPosAt(k, p) && p.id == (long)tk) found = true;
   ck(found && p.robot && p.closed && p.stamp == U(SV(2021, 1, 11, 10, 6, 0)), "stamp of a broker stop deal with magic 0 = X + 60");
   // EA close at 10:30:02: stamp 10:30; TP and SO: + 60; a close from the phone: X
   tk = w_open(CR_BTC, -1, 0.05, 30000.0, 20261205, SV(2021, 1, 11, 10, 20, 2), 0.0);
   w_close(tk, 50.0, DEAL_REASON_EXPERT, 20261205, SV(2021, 1, 11, 10, 30, 2), 0.0, 0.0);
   ulong tp = w_open(CR_ETH, 1, 0.1, 1200.0, 20261204, SV(2021, 1, 11, 10, 31, 2), 0.0);
   w_close(tp, 25.0, DEAL_REASON_TP, 0, SV(2021, 1, 11, 10, 40, 10), 0.0, 0.0);
   ulong so = w_open(CR_ETH, -1, 0.1, 1200.0, 20261206, SV(2021, 1, 11, 10, 41, 2), 0.0);
   w_close(so, -10.0, DEAL_REASON_SO, 0, SV(2021, 1, 11, 10, 45, 10), 0.0, 0.0);
   ulong mob = w_open(CR_IDX, 1, 0.1, 13000.0, 20261201, SV(2021, 1, 11, 10, 46, 2), 0.0);
   w_close(mob, 4.0, DEAL_REASON_MOBILE, 20261201, SV(2021, 1, 11, 10, 50, 40), 0.0, 0.0);
   w_at(SV(2021, 1, 11, 10, 55, 0));
   LedRead(rp_now);
   ckeq(LedBalance(U(SV(2021, 1, 11, 10, 30, 0))), 9898.0, "an EA close in minute X is not known at X");
   ckeq(LedBalance(U(SV(2021, 1, 11, 10, 31, 0))), 9948.0, "... and known at X + 60");
   ckeq(LedBalance(U(SV(2021, 1, 11, 10, 41, 0))), 9948.0, "TP in minute X: not known at X + 60");
   ckeq(LedBalance(U(SV(2021, 1, 11, 10, 42, 0))), 9973.0, "TP: known at X + 120");
   ckeq(LedBalance(U(SV(2021, 1, 11, 10, 46, 0))), 9973.0, "SO in minute X: not known at X + 60");
   ckeq(LedBalance(U(SV(2021, 1, 11, 10, 47, 0))), 9963.0, "SO: known at X + 120");
   ckeq(LedBalance(U(SV(2021, 1, 11, 10, 50, 0))), 9963.0, "a close from the phone in minute X: not known at X");
   ckeq(LedBalance(U(SV(2021, 1, 11, 10, 51, 0))), 9967.0, "... known at X + 60");
   // payments at their deal time: known at S when at or before S
   w_at(SV(2021, 1, 11, 11, 0, 0));
   w_pay(SV(2021, 1, 11, 11, 0, 0), 1000.0, 0);
   w_at(SV(2021, 1, 11, 11, 0, 30));
   w_pay(SV(2021, 1, 11, 11, 0, 30), 500.0, 0);
   // manual and hands' trades: other money at their deal time, in B, not in P_in
   ulong man = w_open(CR_XAU, 1, 0.1, 1850.0, 0, SV(2021, 1, 11, 11, 10, 0), -0.5);
   w_close(man, 40.5, DEAL_REASON_CLIENT, 0, SV(2021, 1, 11, 11, 20, 0), 0.0, 0.0);
   ulong hands = w_open(CR_IDX, -1, 0.1, 13000.0, CR_MAGIC_HANDS, SV(2021, 1, 11, 11, 25, 0), 0.0);
   w_close(hands, -7.0, DEAL_REASON_EXPERT, CR_MAGIC_HANDS, SV(2021, 1, 11, 11, 30, 0), 0.0, 0.0);
   w_at(SV(2021, 1, 11, 11, 40, 0));
   LedRead(rp_now);
   ckeq(LedBalance(U(SV(2021, 1, 11, 10, 59, 0))), 9967.0, "a payment at 11:00:00 is not known at 10:59");
   ckeq(LedBalance(U(SV(2021, 1, 11, 11, 0, 0))), 10967.0, "... and known at 11:00 (payments at or before S)");
   ckeq(LedBalance(U(SV(2021, 1, 11, 11, 1, 0))), 11467.0, "a payment at 11:00:30 is known at 11:01");
   ckeq(LedPaidIn(U(SV(2021, 1, 11, 11, 1, 0))), 11500.0, "P_in");
   ckeq(LedBalance(U(SV(2021, 1, 11, 11, 10, 0))), 11466.5, "a manual opening commission at its deal time");
   ckeq(LedBalance(U(SV(2021, 1, 11, 11, 20, 0))), 11507.0, "a manual close at its deal time");
   ckeq(LedBalance(U(SV(2021, 1, 11, 11, 30, 0))), 11500.0, "the hands' close at its deal time");
   ckeq(LedPaidIn(U(SV(2021, 1, 11, 11, 30, 0))), 11500.0, "other money is never paid in");
   ckeq(LedCloseMoney(U(SV(2021, 1, 11, 11, 31, 0))), -102.0 + 50.0 + 25.0 - 10.0 + 4.0, "robot close money only");
  }

static void u_ref()
  {
   g_world = "P_in and ref (R1)";
   long t = SV(2021, 1, 11, 9, 0, 0);
   w_reset(1000.0, t, true, SV(2021, 1, 4, 0, 0, 0), F3S);
   w_ready();
   struct Step { int kind; double a; };                 // 0 payment, 1 robot close
   std::vector<Step> steps = {{0, 1000.0}, {1, -500.0}, {0, 1000.0}, {0, -1000.0}, {1, 4500.0}, {0, 1000.0}, {0, -3000.0}};
   std::vector<long> stamps;
   for(size_t k = 0; k < steps.size(); k++)
     {
      long ts = SV(2021, 1, 11, 10 + (int)k, 0, 0);
      w_at(ts);
      if(steps[k].kind == 0) w_pay(ts, steps[k].a, 0);
      else
        {
         ulong tk = w_open(CR_BTC, 1, 0.1, 30000.0, 20261205, ts - 600, 0.0);
         w_close(tk, steps[k].a, DEAL_REASON_EXPERT, 20261205, ts, 0.0, 0.0);
        }
      stamps.push_back(U(ts) + 60);
     }
   w_at(SV(2021, 1, 11, 18, 0, 0));
   LedRead(rp_now);
   double wantB[] = {2000.0, 1500.0, 2500.0, 1500.0, 6000.0, 7000.0, 4000.0};
   double wantP[] = {2000.0, 2000.0, 3000.0, 3000.0, 3000.0, 4000.0, 4000.0};
   double wantR[] = {2000.0, 2000.0, 3000.0, 1800.0, 1800.0, 7000.0, 4000.0};
   for(size_t k = 0; k < steps.size(); k++)
     {
      ckeq(LedBalance(stamps[k]), wantB[k], F("B after step %zu", k));
      ckeq(LedPaidIn(stamps[k]), wantP[k], F("P_in after step %zu", k));
      ckeq(LedRef(stamps[k]), wantR[k], F("ref after step %zu", k));
     }
   ckeq(LedBalanceNow(), 4000.0, "LedBalanceNow = B after the last event");
   ckeq(LedPaidInNow(), 4000.0, "LedPaidInNow");
   ckeq(LedRefNow(), 4000.0, "LedRefNow");
   cknear(LedBalance(stamps[3]) / LedRef(stamps[3]), LedBalance(stamps[2]) / LedRef(stamps[2]), 1e-15, "a withdrawal leaves B/ref alone");
   ckeq(SizRate(MathMax(LedBalance(stamps[3]), LedPaidIn(stamps[3]))), SizRate(MathMax(LedBalance(stamps[2]), LedPaidIn(stamps[2]))),
        "a withdrawal leaves the rung alone");
   // withdrawing gains (B above P_in) lowers max(B, P_in): the rung follows SPEC 5's formula (7,000 -> 4,000: 1 % -> 2 %)
   ckeq(SizRate(MathMax(LedBalance(stamps[5]), LedPaidIn(stamps[5]))), 1.0, "rung before the withdrawal of gains");
   ckeq(SizRate(MathMax(LedBalance(stamps[6]), LedPaidIn(stamps[6]))), 2.0, "rung after it: max(B, P_in) = 4,000");
   cknear(LedBalance(stamps[6]) / LedRef(stamps[6]), LedBalance(stamps[5]) / LedRef(stamps[5]), 1e-15, "B/ref unchanged by it");
   // the worked example of R1: armed at 13,000 paid, a withdrawal during a drawdown neither disarms nor fires the stop
   g_world = "R1 withdrawal during a drawdown after arming";
   w_reset(13000.0, t, true, SV(2021, 1, 4, 0, 0, 0), F3S);
   w_ready();
   ulong tk = w_open(CR_BTC, 1, 0.5, 30000.0, 20261205, SV(2021, 1, 11, 9, 10, 2), 0.0);
   w_close(tk, -3000.0, DEAL_REASON_EXPERT, 20261205, SV(2021, 1, 11, 9, 20, 2), 0.0, 0.0);
   w_at(SV(2021, 1, 11, 9, 30, 0));
   w_pay(SV(2021, 1, 11, 9, 30, 0), -2000.0, 0);
   w_at(SV(2021, 1, 11, 9, 40, 0));
   LedRead(rp_now);
   long S = U(SV(2021, 1, 11, 9, 40, 0));
   ckeq(LedPaidIn(S), 13000.0, "P_in is gross: still armed");
   ckeq(LedRef(S), 10400.0, "ref = 13,000 x 8,000 / 10,000");
   ckeq(LedBalance(S), 8000.0, "B");
   ck(!LedStopLatched(), "8,000 > 0.75 x 10,400: no stop");
   tk = w_open(CR_BTC, 1, 0.5, 30000.0, 20261205, SV(2021, 1, 11, 9, 50, 2), 0.0);
   w_close(tk, -250.0, DEAL_REASON_EXPERT, 20261205, SV(2021, 1, 11, 10, 0, 2), 0.0, 0.0);
   w_at(SV(2021, 1, 11, 10, 1, 0));
   LedRead(rp_now);
   ck(LedStopLatched() && LedStopTime() == U(SV(2021, 1, 11, 10, 0, 0)), "7,750 <= 7,800: the plan stop fires");
  }

static void u_stop()
  {
   string err;
   long t = SV(2021, 1, 4, 9, 0, 0);
   for(int pass = 0; pass < 2; pass++)
     {
      g_world = pass == 0 ? "plan stop armed" : "plan stop not armed";
      w_reset(1000.0, t, true, SV(2021, 1, 4, 0, 0, 0), F3S);
      w_ready();
      int ndep = pass == 0 ? 11 : 10;
      for(int k = 0; k < ndep; k++)
        {
         w_at(SV(2021, 1, 4, 10 + k, 0, 0));
         w_pay(rp_now, 1000.0, 0);
        }
      ulong a = w_open(CR_ETH, 1, 1.0, 1200.0, 20261204, SV(2021, 1, 5, 9, 0, 2), 0.0);
      w_close(a, -2000.0, DEAL_REASON_SL, 0, SV(2021, 1, 5, 9, 30, 30), 0.0, 0.0);
      ulong b = w_open(CR_ETH, 1, 1.0, 1200.0, 20261204, SV(2021, 1, 5, 10, 0, 2), 0.0);
      double loss = pass == 0 ? -1001.0 : -1001.0;
      w_close(b, loss, DEAL_REASON_SL, 0, SV(2021, 1, 5, 10, 30, 30), 0.0, 0.0);
      w_at(SV(2021, 1, 5, 11, 0, 0));
      LedRead(rp_now);
      long C = U(SV(2021, 1, 5, 10, 31, 0));
      if(pass == 1)
        {
         ck(!LedStopLatched() && LedStopTime() == 0, "P_in 11,000 < 12,000: not armed, no stop");
         continue;
        }
      ckeq(LedPaidIn(C + 60), 12000.0, "P_in armed");
      ckeq(LedBalance(C + 60), 8999.0, "B");
      ck(LedStopLatched(), "8,999 <= 0.75 x 12,000: stopped");
      ckint((long)LedStopTime(), C, "the stop's stamp is the close's");
      ck(!LedStoppedAt(C) && LedStoppedAt(C + 60), "known for entries after the close's stamp only");
      CrIntent it = w_intent("BKB", 1, CR_ET_MARKET, C, 0.0, 500.0, 30000.0, 0.0, CR_SK_NONE);
      ck(SizSize(it, C, false) != CR_SK_STOPPED, "an entry stamped like the stop close is not stopped");
      it = w_intent("BKB", 1, CR_ET_MARKET, C + 60, 0.0, 500.0, 30000.0, 0.0, CR_SK_FRIDAY);
      ckint(SizSize(it, C + 60, false), CR_SK_STOPPED, "an entry after it is STOPPED (before the caller's reason)");
      // a rebuild and a restart find it again in the history
      LedReset();
      LedRead(rp_now);
      ck(LedStopLatched() && LedStopTime() == C, "the stop survives a rebuild");
      LedInit(err);
      w_ready();
      ck(LedStopLatched() && LedStopTime() == C, "the stop survives a restart");
      // a later plan start clears it
      g_cfg.plan_start = SV(2021, 1, 5, 12, 0, 0);
      LedInit(err);
      w_at(SV(2021, 1, 5, 12, 0, 5));
      w_ready();
      ck(!LedStopLatched(), "a later InpPlanStart clears the stop");
      ckeq(LedBT(), 8999.0, "B(T) of the new plan");
      ckeq(LedPaidIn(U(rp_now)), 8999.0, "P_in of the new plan");
     }
  }

static void u_guard()
  {
   string err;
#ifdef CR_NO_GUARD
   const bool on = false;
#else
   const bool on = true;
#endif
   long t = SV(2021, 1, 11, 9, 0, 0);
   // (b) after a robot close
   g_world = "guard (b) after a robot close";
   w_reset(10000.0, t, true, SV(2021, 1, 4, 0, 0, 0), F3S);
   w_ready();
   ulong a = w_open(CR_XAU, 1, 1.0, 1850.0, 20261208, SV(2021, 1, 11, 9, 10, 2), 0.0);
   w_close(a, -5000.0, DEAL_REASON_EXPERT, 20261208, SV(2021, 1, 11, 9, 20, 2), 0.0, 0.0);
   w_at(SV(2021, 1, 11, 9, 30, 0));
   LedRead(rp_now);
   long C = U(SV(2021, 1, 11, 9, 20, 0));
   ck(LedGuardLatched() == on, "B = 50 % of ref latches GUARD (b)");
   ck(!LedStopLatched(), "no STOP (P_in 10,000 < 12,000)");
   ck(LedGuardAt(C) == false && LedGuardAt(C + 60) == on, "known after the close's stamp");
   CrIntent it = w_intent("BKB", 1, CR_ET_MARKET, C + 60, 0.0, 500.0, 30000.0, 0.0, CR_SK_NONE);
   ck((SizSize(it, C + 60, false) == CR_SK_GUARD) == on, "SizSize: GUARD");
   // (b) after other money: a manual loss
   g_world = "guard (b) after a manual loss";
   w_reset(10000.0, t, true, SV(2021, 1, 4, 0, 0, 0), F3S);
   w_ready();
   ulong man = w_open(CR_XAU, 1, 1.0, 1850.0, 0, SV(2021, 1, 11, 9, 10, 0), 0.0);
   w_close(man, -5500.0, DEAL_REASON_CLIENT, 0, SV(2021, 1, 11, 9, 20, 0), 0.0, 0.0);
   w_at(SV(2021, 1, 11, 9, 30, 0));
   LedRead(rp_now);
   ck(LedGuardLatched() == on, "B 45 % of ref after a manual loss latches GUARD (b)");
   ck(LedGuardAt(U(SV(2021, 1, 11, 9, 20, 0))) == on && !LedGuardAt(U(SV(2021, 1, 11, 9, 19, 0))), "known from its deal time");
   // (c) the guard's own mark, with the balance far above half the reference; a restart keeps it (P3, R2)
   g_world = "guard (c) mark";
   w_reset(10000.0, t, true, SV(2021, 1, 4, 0, 0, 0), F3S);
   w_ready();
   ck(!LedMarkSeen() && !LedGuardLatched(), "nothing before the mark");
   ulong r = w_open(CR_BTC, 1, 0.01, 30000.0, 20261203, SV(2021, 1, 11, 9, 10, 2), 0.0);
   w_close(r, -20.0, DEAL_REASON_EXPERT, CR_MAGIC_MARK, SV(2021, 1, 11, 9, 20, 2), 0.0, 0.0);   // close-all request's magic
   ulong mk = w_open(CR_XAU, 1, 0.01, 1850.0, CR_MAGIC_MARK, SV(2021, 1, 11, 9, 21, 2), 0.0);
   w_close(mk, -0.25, DEAL_REASON_EXPERT, CR_MAGIC_MARK, SV(2021, 1, 11, 9, 21, 3), 0.0, 0.0);
   w_at(SV(2021, 1, 11, 9, 30, 0));
   LedRead(rp_now);
   ck(LedMarkSeen(), "the mark deal is seen");
   ck(LedGuardLatched() == on, "GUARD (c) with B at 99.8 % of ref");
   ckeq(LedCloseMoney(U(SV(2021, 1, 11, 9, 30, 0))), -20.0, "a robot position closed by the guard's request is a robot close");
   ckeq(LedBalance(U(SV(2021, 1, 11, 9, 30, 0))), 9979.75, "the mark trade is other money");
   LedInit(err);
   w_at(SV(2021, 1, 12, 9, 0, 0));
   w_ready();
   ck(LedGuardLatched() == on, "GUARD (c) survives a restart");
   g_cfg.plan_start = SV(2021, 1, 11, 9, 25, 0);
   LedInit(err);
   w_ready();
   ck(!LedGuardLatched() && !LedMarkSeen(), "a later InpPlanStart clears GUARD (c)");
   // a mark before T does not latch
   g_world = "guard (c) mark before T";
   w_reset(10000.0, t, true, SV(2021, 1, 11, 9, 30, 0), F3S);
   mk = w_open(CR_XAU, 1, 0.01, 1850.0, CR_MAGIC_MARK, SV(2021, 1, 11, 9, 10, 2), 0.0);
   w_close(mk, -0.25, DEAL_REASON_EXPERT, CR_MAGIC_MARK, SV(2021, 1, 11, 9, 10, 3), 0.0, 0.0);
   w_at(SV(2021, 1, 11, 9, 40, 0));
   w_ready();
   ck(!LedGuardLatched() && !LedMarkSeen(), "a mark before T is history before the plan");
  }

static void u_lock()
  {
   g_world = "daily lock";
   long t = SV(2021, 1, 12, 9, 0, 0);
   w_reset(10000.0, t, true, SV(2021, 1, 4, 0, 0, 0), F3S);
   g_cfg.lock_stakes = 2.0;                             // limit 2 x 1 % x 10,000 = 200
   w_ready();
   ulong a = w_open(CR_ETH, 1, 1.0, 1200.0, 20261204, SV(2021, 1, 12, 9, 50, 2), 0.0);
   w_close(a, -150.0, DEAL_REASON_EXPERT, 20261204, SV(2021, 1, 12, 10, 0, 2), 0.0, 0.0);
   ulong b = w_open(CR_ETH, 1, 1.0, 1200.0, 20261204, SV(2021, 1, 12, 10, 20, 2), 0.0);
   w_close(b, -60.0, DEAL_REASON_EXPERT, 20261204, SV(2021, 1, 12, 10, 30, 2), 0.0, 0.0);
   w_at(SV(2021, 1, 12, 10, 31, 0));
   LedRead(rp_now);
   ck(!LedDayLockedAt(U(SV(2021, 1, 12, 10, 30, 0))), "-150 > -200: not locked");
   ck(LedDayLockedAt(U(SV(2021, 1, 12, 10, 31, 0))), "-210 <= -200: locked");
   ck(LedDayLocked(rp_now), "LedDayLocked now");
   CrIntent it = w_intent("F1E", 1, CR_ET_MARKET, U(SV(2021, 1, 12, 10, 31, 0)), 0.0, 50.0, 1200.0, 0.0, CR_SK_NONE);
   ckint(SizSize(it, it.stamp, false), CR_SK_LOCK, "SizSize: LOCK");
   ck(!LedDayLockedAt(U(SV(2021, 1, 13, 0, 0, 1))), "the next server day is free");
   w_at(SV(2021, 1, 13, 0, 1, 0));
   LedRead(rp_now);
   ck(!LedDayLocked(rp_now), "LedDayLocked the next day");
   g_cfg.lock_stakes = 0.0;
   ck(!LedDayLockedAt(U(SV(2021, 1, 12, 10, 31, 0))), "InpDailyLockStakes 0: never");
   // a LOCK concluded on a settled ledger holds while the ledger moves later that day
   g_world = "daily lock kept while the ledger moves";
   w_reset(10000.0, t, true, SV(2021, 1, 4, 0, 0, 0), F3S);
   g_cfg.lock_stakes = 2.0;
   w_ready();
   a = w_open(CR_ETH, 1, 1.0, 1200.0, 20261204, SV(2021, 1, 12, 9, 50, 2), 0.0);
   w_close(a, -210.0, DEAL_REASON_EXPERT, 20261204, SV(2021, 1, 12, 10, 0, 2), 0.0, 0.0);
   w_at(SV(2021, 1, 12, 10, 1, 0));
   LedRead(rp_now);
   ck(LedSettled() && LedDayLocked(rp_now), "-210 <= -200 on a settled ledger: LOCK");
   w_pay(SV(2021, 1, 12, 10, 41, 0), 100.0, 30);      // the balance shows it 30 s before its deal
   w_at(SV(2021, 1, 12, 10, 40, 35));
   LedRead(rp_now);
   ck(!LedSettled() && LedDayLocked(rp_now), "the LOCK holds while the ledger moves");
   w_at(SV(2021, 1, 13, 0, 1, 0));
   LedRead(rp_now);
   ck(LedSettled() && !LedDayLocked(rp_now), "and ends with the server day");
   // no LOCK conclusion while the ledger moves: the limit is reached during a movement
   g_world = "daily lock not concluded while the ledger moves";
   w_reset(10000.0, SV(2021, 1, 14, 9, 0, 0), true, SV(2021, 1, 4, 0, 0, 0), F3S);
   g_cfg.lock_stakes = 2.0;
   w_ready();
   w_at(SV(2021, 1, 14, 10, 40, 0));
   w_pay(SV(2021, 1, 14, 10, 41, 0), 100.0, 30);      // the balance shows it 30 s before its deal
   a = w_open(CR_ETH, 1, 1.0, 1200.0, 20261204, SV(2021, 1, 14, 10, 30, 2), 0.0);
   w_close(a, -210.0, DEAL_REASON_EXPERT, 20261204, SV(2021, 1, 14, 10, 40, 10), 0.0, 0.0);
   w_at(SV(2021, 1, 14, 10, 40, 35));
   LedRead(rp_now);
   ck(!LedSettled() && !LedDayLocked(rp_now), "not concluded while unsettled");
   ck(LedDayLockedAt(U(SV(2021, 1, 14, 10, 41, 0))), "(the history alone would lock)");
   w_at(SV(2021, 1, 14, 10, 41, 0));
   LedRead(rp_now);
   ck(LedSettled() && LedDayLocked(rp_now), "concluded once settled");
  }

static void u_settle()
  {
   g_world = "settle";
   long t0 = SV(2021, 1, 11, 9, 0, 0);
   w_reset(10000.0, t0, true, SV(2021, 1, 4, 0, 0, 0), F3S);
   ckint(LedRead(t0), CR_LED_MOVING, "first read: not yet settled");
   ckint(LedRead(t0 + 1), CR_LED_MOVING, "1 s later: not yet");
   ckint(LedRead(t0 + 2), CR_LED_OK, "2 s later: settled");
   rp_now = t0 + 2;
   // the balance shows a deposit 30 s before its deal
   long t1 = t0 + 100;
   w_pay(t1, 1000.0, 30);
   rp_now = t1 - 30;
   ckint(LedRead(rp_now), CR_LED_MOVING, "+30: the balance before the deal moves B(T)");
   CrIntent it = w_intent("BKB", 1, CR_ET_MARKET, U(t1 - 60), 0.0, 500.0, 30000.0, 0.0, CR_SK_NONE);
   long lines0 = g_jrn_lines;
   ckint(SizSize(it, it.stamp, true), CR_SK_SETTLE, "no sizing while it moves");
   ckint(g_jrn_lines - lines0, 0, "SETTLE writes no SIZE line (a wait)");
   ckeq(LedWeekUnit(it.stamp), 0.0, "SETTLE sets no week unit");
   ckeq(LedBalance(U(t1)), 10000.0, "the walk keeps the accepted B(T)");
   rp_now = t1 - 10;
   ckint(LedRead(rp_now), CR_LED_MOVING, "still moving");
   w_at(t1);
   ckint(LedRead(rp_now), CR_LED_OK, "the deal arrives: settled at once");
   ckeq(LedPaidIn(U(t1)), 11000.0, "the deposit is paid in");
   // the deal 30 s before the balance
   long t2 = t1 + 200;
   w_at(t2);
   w_pay(t2, 1000.0, -30);
   ckint(LedRead(rp_now), CR_LED_MOVING, "-30: the deal before the balance moves B(T)");
   w_at(t2 + 29);
   ckint(LedRead(rp_now), CR_LED_MOVING, "still moving at +29 s");
   w_at(t2 + 30);
   ckint(LedRead(rp_now), CR_LED_OK, "settled when the balance shows it");
   // 90 s out of step: accepted after 60 s, then back to the old value at once
   long t3 = t2 + 400;
   w_at(t3 - 95);
   w_pay(t3, 1000.0, 90);
   w_at(t3 - 90);
   ckint(LedRead(rp_now), CR_LED_MOVING, "+90: moving");
   long pushes0 = rp_pushes;
   w_at(t3 - 31);
   ckint(LedRead(rp_now), CR_LED_MOVING, "59 s of movement: still moving");
   w_at(t3 - 30);
   ckint(LedRead(rp_now), CR_LED_OK, "60 s of movement: the latest value is accepted");
   ck(rp_pushes > pushes0, "... and pushed");
   ckeq(LedBT(), 11000.0, "the walk starts from the accepted value (10,000 + the deposit shown early)");
   w_at(t3);
   ckint(LedRead(rp_now), CR_LED_OK, "the deal arrives: back to the value accepted before, settled at once");
   ckeq(LedBT(), 10000.0, "B(T) back");
   ckeq(LedPaidIn(U(t3)), 13000.0, "the three deposits are paid in");
   // a withdrawal shown before its deal never latches GUARD
   g_world = "settle and guard";
   w_reset(10000.0, t0, true, SV(2021, 1, 4, 0, 0, 0), F3S);
   w_ready();
   w_pay(t0 + 60, -6000.0, 30);
   w_at(t0 + 30);
   LedRead(rp_now);
   ck(!LedSettled() && !LedGuardLatched(), "unsettled: no GUARD from the half balance");
   w_at(t0 + 60);
   LedRead(rp_now);
   ck(LedSettled() && !LedGuardLatched(), "settled: a withdrawal leaves B/ref alone, no GUARD");
   ckeq(LedRef(U(t0 + 60)), 4000.0, "ref = 10,000 x 4,000 / 10,000");
   // the account not loaded yet: no deal and no balance
   g_world = "settle on an empty terminal";
   w_reset(0.0, t0, true, 0, F3S);
   ckint(LedRead(t0), CR_LED_MOVING, "no deal and no balance: not ready");
   ckint(LedRead(t0 + 5), CR_LED_MOVING, "... still not ready");
   ckint(LedRead(t0 + 70), CR_LED_MOVING, "... never accepted while empty");
   // a start where B(T) never holds still: the latest value is accepted 60 s after the first read, and pushed
   g_world = "settle at the start, B(T) moving";
   w_reset(10000.0, t0, true, SV(2021, 1, 4, 0, 0, 0), F3S);
   long pushes1 = rp_pushes;
   bool moving = true;
   for(int k = 0; k < 60; k++)
     {
      rp_balance += 1.0;                                // the balance changes at every read, the history does not
      moving = moving && LedRead(t0 + k) == CR_LED_MOVING;
     }
   ck(moving && !LedSettled(), "59 s of movement from the first read: not settled");
   ckint(rp_pushes - pushes1, 0, "no push yet");
   rp_balance += 1.0;
   ckint(LedRead(t0 + 60), CR_LED_OK, "60 s after the first read: the latest value is accepted");
   ckeq(LedBT(), 10061.0, "B(T) = the latest value");
   ck(rp_pushes > pushes1, "... and pushed");
   ckint(LedRead(t0 + 61), CR_LED_OK, "the same value 1 s later: settled");
  }

static void u_week()
  {
   g_world = "week unit and w";
   w_reset(10000.0, SV(2021, 1, 11, 0, 30, 0), true, SV(2021, 1, 4, 0, 0, 0), F3S);
   w_ready();
   // Monday 2021-01-11: the week's first event is a robot close stamped 10:00 server (+300)
   ulong a = w_open(CR_BTC, 1, 0.1, 30000.0, 20261203, SV(2021, 1, 11, 9, 0, 2), 0.0);
   w_close(a, 300.0, DEAL_REASON_EXPERT, 20261203, SV(2021, 1, 11, 10, 0, 2), 0.0, 0.0);
   w_at(SV(2021, 1, 11, 12, 0, 2));
   long S1 = U(SV(2021, 1, 11, 12, 0, 0));
   CrIntent it = w_intent("F1B", 1, CR_ET_MARKET, S1, 0.0, 500.0, 30000.0, 0.0, CR_SK_NONE);
   SizSize(it, S1, false);
   ckint((long)LedWeekRoll(S1), U(SV(2021, 1, 11, 10, 0, 0)), "R = the first robot close of the week");
   ckeq(it.unit, 100.0, "unit = rate(10,000) x B before the close");
   ckeq(it.w, 3.0, "w = 300 / 100");
   ckeq(it.m, 0.75, "m = w / 4");
   ckeq(it.B, 10300.0, "B at the sizing");
   ckeq(it.lots, lab_lots(10300.0, 1.0, 0.75, 1.0, 500.0, CR_BTC), "lots");
   // Tuesday: a payment, a robot close and a charge; payments and other money never count in w
   w_at(SV(2021, 1, 12, 9, 0, 0));
   w_pay(SV(2021, 1, 12, 9, 0, 0), 1000.0, 0);
   ulong b = w_open(CR_ETH, -1, 1.0, 1200.0, 20261204, SV(2021, 1, 12, 9, 30, 2), 0.0);
   w_close(b, -100.0, DEAL_REASON_EXPERT, 20261204, SV(2021, 1, 12, 10, 0, 2), 0.0, 0.0);
   w_deal(SV(2021, 1, 12, 11, 0, 0), DEAL_TYPE_CHARGE, -50.0, 0);
   w_at(SV(2021, 1, 12, 12, 0, 2));
   long S2 = U(SV(2021, 1, 12, 12, 0, 0));
   it = w_intent("F1B", 1, CR_ET_MARKET, S2, 0.0, 500.0, 30000.0, 0.0, CR_SK_NONE);
   SizSize(it, S2, false);
   ckeq(it.unit, 100.0, "the unit stays the week's");
   ckeq(it.B, 11150.0, "B");
   ckeq(it.w, 2.0, "w = (300 - 100) / 100");
   ckeq(it.m, 0.5, "m");
   ckeq(it.rate, 1.0, "rate(max(11,150, 11,000))");
   // Monday 2021-01-18: the first event is the sizing itself
   w_at(SV(2021, 1, 18, 12, 0, 2));
   long S3 = U(SV(2021, 1, 18, 12, 0, 0));
   it = w_intent("F1B", 1, CR_ET_MARKET, S3, 0.0, 500.0, 30000.0, 0.0, CR_SK_NONE);
   SizSize(it, S3, false);
   ckint((long)LedWeekRoll(S3), S3, "R = the sizing");
   ckeq(it.unit, 111.5, "unit = 1 % x 11,150");
   ckeq(it.w, 0.0, "w = 0");
   ckeq(it.m, 1.0, "m = 1");
   // Monday 2021-01-25: a close stamped exactly at the first sizing's stamp is after it (the lab's order)
   long S4 = U(SV(2021, 1, 25, 12, 0, 0));
   ulong c = w_open(CR_ETH, 1, 1.0, 1200.0, 20261206, SV(2021, 1, 25, 11, 0, 2), 0.0);
   w_close(c, 223.0, DEAL_REASON_EXPERT, 20261206, SV(2021, 1, 25, 12, 0, 1), 0.0, 0.0);
   w_at(SV(2021, 1, 25, 12, 0, 2));
   it = w_intent("BKB", 1, CR_ET_MARKET, S4, 0.0, 500.0, 30000.0, 0.0, CR_SK_NONE);
   SizSize(it, S4, false);
   ckint((long)LedWeekRoll(S4), S4, "R = the sizing, not the close stamped in the same minute");
   ckeq(it.B, 11150.0, "the close is not known to the entry of its minute");
   ckeq(it.unit, 111.5, "unit from B before that close");
   w_at(SV(2021, 1, 25, 13, 0, 2));
   long S5 = U(SV(2021, 1, 25, 13, 0, 0));
   it = w_intent("BKB", 1, CR_ET_MARKET, S5, 0.0, 500.0, 30000.0, 0.0, CR_SK_NONE);
   SizSize(it, S5, false);
   ckeq(it.w, 2.0, "w = 223 / 111.5");
   // a MISSED reason=exited intent sets the unit of an empty week (SizWeekUnit)
   long S6 = U(SV(2021, 2, 1, 12, 0, 0));
   w_at(SV(2021, 2, 1, 12, 0, 2));
   LedRead(rp_now);
   double u6 = SizWeekUnit(S6);
   ckeq(u6, 113.73, "SizWeekUnit sets the unit");
   ckeq(LedWeekUnit(S6 + 3600), 113.73, "... for the whole week");
   // a rebuild forgets the units: the replay's sizing requests set them again
   LedReset();
   LedRead(rp_now);
   ckeq(LedWeekUnit(S6), 0.0, "LedReset forgets the week units");
  }

static void u_lots()
  {
   g_world = "lots, stake factors, min lot";
   w_reset(10000.0, SV(2021, 1, 11, 9, 0, 2), true, SV(2021, 1, 4, 0, 0, 0), F3S);
   w_ready();
   long S = U(SV(2021, 1, 11, 9, 0, 0));
   CrIntent it = w_intent("BKB", 1, CR_ET_MARKET, S, 0.0, 500.0, 30000.0, 0.0, CR_SK_NONE);
   ckint(SizSize(it, S, false), CR_SK_NONE, "taken");
   ckeq(it.lots, 0.22, "BKB: floor(100 / 445 / 0.01) x 0.01");
   ckeq(it.lots, lab_lots(10000.0, 1.0, 1.0, 1.0, 500.0, CR_BTC), "lots = the lab's formula");
   ckeq(it.budget, 100.0, "budget");
   ckeq(it.f, 1.0, "f = 1 while the switch is off");
   int bkb = CrSleeveOfCode("BKB"), f1e = CrSleeveOfCode("F1E"), bke = CrSleeveOfCode("BKE");
   g_sl[bkb].change_on = true;
   g_sl[f1e].change_on = true;
   g_sl[bke].change_on = true;
   it = w_intent("BKB", 1, CR_ET_MARKET, S, 0.0, 500.0, 30000.0, 0.0, CR_SK_NONE);
   SizSize(it, S, false);
   ckeq(it.f, 0.771793, "S0.75r on: f = 0.771793");
   ckeq(it.lots, lab_lots(10000.0, 1.0, 1.0, 0.771793, 500.0, CR_BTC), "S0.75r lots");
   ckeq(it.lots, 0.17, "S0.75r: 0.17");
   it = w_intent("F1E", -1, CR_ET_MARKET, S, 0.0, 20.0, 1200.0, 0.0, CR_SK_NONE);
   SizSize(it, S, false);
   ckeq(it.f, 0.750978, "H2 on: f = 0.750978");
   ckeq(it.lots, lab_lots(10000.0, 1.0, 1.0, 0.750978, 20.0, CR_ETH), "H2 lots");
   it = w_intent("BKE", 1, CR_ET_MARKET, S, 0.0, 20.0, 1200.0, 0.0, CR_SK_NONE);
   SizSize(it, S, false);
   ckeq(it.f, 1.0, "K1 on: no stake factor");
   g_sl[bkb].change_on = false;
   g_sl[f1e].change_on = false;
   g_sl[bke].change_on = false;
   // the minimum lot is never rounded up
   it = w_intent("BKB", 1, CR_ET_MARKET, S, 0.0, 50000.0, 30000.0, 0.0, CR_SK_NONE);
   ckint(SizSize(it, S, false), CR_SK_MIN_LOT, "BKB with a 50,000 USD stop: below 0.01 lot");
   ckeq(it.lots, 0.0, "no lots");
   it = w_intent("N30", 1, CR_ET_MARKET, S, 0.0, 1200.0, 13000.0, 0.0, CR_SK_NONE);
   ckint(SizSize(it, S, false), CR_SK_MIN_LOT, "US100: 0.0936 lot is below 0.1");
   it = w_intent("N30", 1, CR_ET_MARKET, S, 0.0, 50.0, 13000.0, 0.0, CR_SK_NONE);
   ckint(SizSize(it, S, false), CR_SK_NONE, "US100 with a 50-point stop");
   ckeq(it.lots, lab_lots(10000.0, 1.0, 1.0, 1.0, 50.0, CR_IDX), "US100 lots, step 0.1");
   // market with an absolute stop: r = side x (quote_p - stop) with the market slip (N30)
   it = w_intent("N30", 1, CR_ET_MARKET, S, 13000.0, 0.0, 13050.0, 0.0, CR_SK_NONE);
   SizSize(it, S, false);
   ckeq(it.r, 1.0 * ((13050.0 + 1 * 0.0) * (1.0 + 1 * 0.2e-4) - 13000.0), "r of an absolute-stop market intent");
   ck(!it.late, "a market intent is not late");
   it = w_intent("N30", 1, CR_ET_MARKET, S, 13000.0, 0.0, 12990.0, 0.0, CR_SK_NONE);
   ckint(SizSize(it, S, false), CR_SK_MIN_LOT, "a quote beyond the stop: r <= 0, no lots");
   // late intents (stop, limit, OCO): r = max(paper risk, quote risk), with h (gold, 3 points as in a release build)
   g_sym[CR_XAU].h = 0.03;
   it = w_intent("D4H", 1, CR_ET_STOP, S, 1840.0, 0.0, 1851.2, 1850.0, CR_SK_NONE);
   SizSize(it, S, false);
   double qp = (1851.2 + 0.03) * (1.0 + 0.3e-4);
   ckeq(it.r, qp - 1840.0, "late long: the quote risk is the larger");
   ck(it.late, "late = 1");
   it = w_intent("D4H", 1, CR_ET_OCO, S, 0.0, 10.0, 1849.0, 1850.0, CR_SK_NONE);
   SizSize(it, S, false);
   ckeq(it.r, 10.0, "late long: the paper risk is the larger (distance stop)");
   it = w_intent("ORX", -1, CR_ET_STOP, S, 1860.0, 0.0, 1849.0, 1850.0, CR_SK_NONE);
   SizSize(it, S, false);
   double qs = (1849.0 - 0.03) * (1.0 - 0.3e-4);
   ckeq(it.r, -1.0 * (qs - 1860.0), "late short: the quote risk");
   ckeq(it.lots, lab_lots(10000.0, 1.0, 1.0, 1.0, -1.0 * (qs - 1860.0), CR_XAU), "late lots on the larger risk");
   g_sym[CR_XAU].h = 0.0;
  }

static void u_caps()
  {
   g_world = "caps";
   w_reset(10000.0, SV(2021, 1, 11, 8, 0, 0), true, SV(2021, 1, 4, 0, 0, 0), F3S);
   w_ready();
   ulong d4h = w_open(CR_XAU, 1, 0.1, 1850.0, 20261209, SV(2021, 1, 11, 8, 0, 2), 0.0);
   ulong orx = w_open(CR_XAU, -1, 0.1, 1850.0, 20261210, SV(2021, 1, 11, 8, 30, 2), 0.0);
   w_open(CR_XAU, 1, 1.0, 1850.0, 0, SV(2021, 1, 11, 8, 40, 0), 0.0);       // a manual position: never counted
   w_at(SV(2021, 1, 11, 9, 0, 2));
   long S = U(SV(2021, 1, 11, 9, 0, 0));
   CrIntent it = w_intent("GFP", 1, CR_ET_LIMIT, S, 0.0, 10.0, 1850.0, 1850.0, CR_SK_NONE);
   ckint(SizSize(it, S, false), CR_SK_CAP, "a third gold position: CAP (2 per symbol)");
   it = w_intent("BKB", 1, CR_ET_MARKET, S, 0.0, 500.0, 30000.0, 0.0, CR_SK_NONE);
   ckint(SizSize(it, S, false), CR_SK_NONE, "bitcoin is free");
   // ORX closed by its stop in minute 09:59: stamp 10:00; still counted at 10:00, not at 10:01
   w_close(orx, -50.0, DEAL_REASON_SL, 0, SV(2021, 1, 11, 9, 59, 30), 0.0, 0.0);
   w_at(SV(2021, 1, 11, 10, 0, 2));
   S = U(SV(2021, 1, 11, 10, 0, 0));
   it = w_intent("GFP", 1, CR_ET_LIMIT, S, 0.0, 10.0, 1850.0, 1850.0, CR_SK_NONE);
   ckint(SizSize(it, S, false), CR_SK_CAP, "a close stamped at S still counts");
   w_at(SV(2021, 1, 11, 10, 1, 2));
   S = U(SV(2021, 1, 11, 10, 1, 0));
   it = w_intent("GFP", 1, CR_ET_LIMIT, S, 0.0, 10.0, 1850.0, 1850.0, CR_SK_NONE);
   ckint(SizSize(it, S, false), CR_SK_NONE, "a close stamped before S does not");
   // D4H closed by the EA at 10:30:02: stamp 10:30, counted at 10:30
   w_close(d4h, 20.0, DEAL_REASON_EXPERT, 20261209, SV(2021, 1, 11, 10, 30, 2), 0.0, 0.0);
   ulong g2 = w_open(CR_XAU, 1, 0.1, 1850.0, 20261208, SV(2021, 1, 11, 10, 1, 3), 0.0);
   w_at(SV(2021, 1, 11, 10, 30, 3));
   S = U(SV(2021, 1, 11, 10, 30, 0));
   it = w_intent("ORX", 1, CR_ET_STOP, S, 1840.0, 0.0, 1850.0, 1850.0, CR_SK_NONE);
   ckint(SizSize(it, S, false), CR_SK_CAP, "an EA close in minute S counts at S");
   // six positions at most
   w_close(g2, 0.0, DEAL_REASON_EXPERT, 20261208, SV(2021, 1, 11, 10, 40, 2), 0.0, 0.0);
   const char *codes[6] = {"GFP", "D4H", "N30", "OC4", "BKB", "F1B"};
   const int syms[6] = {CR_XAU, CR_XAU, CR_IDX, CR_IDX, CR_BTC, CR_BTC};
   for(int k = 0; k < 6; k++)
      w_open(syms[k], 1, syms[k] == CR_IDX ? 0.1 : 0.01, syms[k] == CR_XAU ? 1850.0 : (syms[k] == CR_IDX ? 13000.0 : 30000.0),
             g_sl[CrSleeveOfCode(codes[k])].magic, SV(2021, 1, 11, 11, k, 2), 0.0);
   w_at(SV(2021, 1, 11, 12, 0, 2));
   S = U(SV(2021, 1, 11, 12, 0, 0));
   it = w_intent("BKE", 1, CR_ET_MARKET, S, 0.0, 20.0, 1200.0, 0.0, CR_SK_NONE);
   ckint(SizSize(it, S, false), CR_SK_CAP, "a seventh position: CAP");
   // the replay (dry) counts only the positions opened before the stamp's minute
   g_world = "caps in the replay";
   w_reset(10000.0, SV(2021, 1, 11, 8, 0, 0), true, SV(2021, 1, 4, 0, 0, 0), F3S);
   w_ready();
   w_open(CR_XAU, 1, 0.1, 1850.0, 20261209, SV(2021, 1, 11, 8, 0, 2), 0.0);
   w_open(CR_XAU, -1, 0.1, 1850.0, 20261210, SV(2021, 1, 11, 9, 0, 2), 0.0);
   w_at(SV(2021, 1, 11, 9, 1, 2));
   LedRead(rp_now);
   S = U(SV(2021, 1, 11, 9, 0, 0));
   it = w_intent("GFP", 1, CR_ET_LIMIT, S, 0.0, 10.0, 1850.0, 1850.0, CR_SK_NONE);
   ckint(SizSize(it, S, true), CR_SK_NONE, "dry: a position opened in the stamp's minute is not counted");
   it = w_intent("GFP", 1, CR_ET_LIMIT, S, 0.0, 10.0, 1850.0, 1850.0, CR_SK_NONE);
   ckint(SizSize(it, S, false), CR_SK_CAP, "live: every robot position counts");
  }

static void u_margin()
  {
   g_world = "margin";
   w_reset(1000.0, SV(2021, 1, 11, 8, 0, 0), true, SV(2021, 1, 4, 0, 0, 0), F3S);
   w_ready();
   ulong a = w_open(CR_BTC, 1, 1.0, 50000.0, 20261203, SV(2021, 1, 11, 8, 0, 2), 0.0);     // margin 890
   w_at(SV(2021, 1, 11, 9, 0, 2));
   long S = U(SV(2021, 1, 11, 9, 0, 0));
   CrIntent it = w_intent("F1B", 1, CR_ET_MARKET, S, 0.0, 100.0, 50000.0, 0.0, CR_SK_NONE);
   ckint(SizSize(it, S, false), CR_SK_MARGIN, "890 + 0.33 lot x 50,000 x 0.89 / 50 > 1,000: MARGIN");
   w_close(a, 0.0, DEAL_REASON_EXPERT, 20261203, SV(2021, 1, 11, 9, 10, 2), 0.0, 0.0);
   w_at(SV(2021, 1, 11, 9, 11, 2));
   S = U(SV(2021, 1, 11, 9, 11, 0));
   it = w_intent("F1B", 1, CR_ET_MARKET, S, 0.0, 100.0, 50000.0, 0.0, CR_SK_NONE);
   ckint(SizSize(it, S, false), CR_SK_NONE, "the margin is free again");
   ckeq(it.lots, lab_lots(1000.0, 3.0, 1.0, 1.0, 100.0, CR_BTC), "3 % below 3,000");
  }

static void u_order()
  {
   g_world = "check order";
   w_reset(10000.0, SV(2021, 1, 11, 9, 0, 2), true, SV(2021, 1, 4, 0, 0, 0), F3S);
   w_ready();
   long S = U(SV(2021, 1, 11, 9, 0, 0));
   CrIntent it = w_intent("BKB", 1, CR_ET_MARKET, S, 0.0, 500.0, 30000.0, 0.0, CR_SK_NOTALLOWED);
   ckint(SizSize(it, S, false), CR_SK_NOTALLOWED, "NOTALLOWED first");
   ckeq(LedWeekUnit(S), 0.0, "a paper-only sleeve sets no week unit");
   it = w_intent("BKB", 1, CR_ET_MARKET, S, 0.0, 500.0, 30000.0, 0.0, CR_SK_PREV_OPEN);
   ckint(SizSize(it, S, false), CR_SK_PREV_OPEN, "the caller's reason");
   ckeq(LedWeekUnit(S), 100.0, "a sizing request skipped by the caller's reason sets the unit");
   ckeq(it.B, 10000.0, "the line carries B");
   CrIntent bad = w_intent("BKB", 1, CR_ET_MARKET, S, 0.0, 500.0, 30000.0, 0.0, CR_SK_NONE);
   bad.sleeve = 99;
   ckint(SizSize(bad, S, false), CR_SK_NOTREADY, "an unknown sleeve row is refused");
  }

static void u_commission()
  {
   g_world = "gold commission";
   w_reset(10000.0, SV(2021, 1, 11, 8, 0, 0), true, SV(2021, 1, 4, 0, 0, 0), F3S);
   w_ready();
   ulong a = w_open(CR_XAU, 1, 1.0, 1850.0, 20261209, SV(2021, 1, 11, 8, 0, 2), -3.0 * W_USDEUR);
   w_close(a, 10.0, DEAL_REASON_EXPERT, 20261209, SV(2021, 1, 11, 12, 0, 2), -3.0 * W_USDEUR, 0.0);
   ulong m = w_open(CR_XAU, 1, 1.0, 1850.0, 0, SV(2021, 1, 11, 9, 0, 2), -9.0);              // manual: not counted
   w_close(m, 0.0, DEAL_REASON_CLIENT, 0, SV(2021, 1, 11, 9, 5, 2), -9.0, 0.0);
   w_at(SV(2021, 1, 11, 13, 0, 0));
   LedRead(rp_now);
   double usd = 0.0;
   int n = 0;
   ck(LedCommission(SV(2021, 1, 11, 0, 0, 0), usd, n) && n == 2, "two gold robot deals that day");
   cknear(usd, 0.06, 1e-12, "3 USD per side per lot = 0.06 USD per oz round trip");
   ck(!LedCommission(SV(2021, 1, 12, 0, 0, 0), usd, n) && n == 0, "none the next day");
  }

static void u_history_order()
  {
   g_world = "history order";
   std::vector<double> want;
   std::vector<long> stamps;
   for(int pass = 0; pass < 3; pass++)
     {
      w_reset(5000.0, SV(2021, 1, 11, 8, 0, 0), true, SV(2021, 1, 4, 0, 0, 0), F3S);
      w_pay(SV(2021, 1, 11, 8, 0, 0), 1000.0, 0);
      for(int k = 0; k < 8; k++)
        {
         ulong t = w_open(k % 2 ? CR_BTC : CR_ETH, 1, 0.1, 1000.0, 20261203 + (k % 2), SV(2021, 1, 11, 9, 0, 2 + k), 0.0);
         w_close(t, 10.0 * (k - 3), k % 3 ? DEAL_REASON_SL : DEAL_REASON_EXPERT, 0, SV(2021, 1, 11, 10, k % 4, 30), 0.0, 0.0);
        }
      w_at(SV(2021, 1, 11, 12, 0, 0));
      if(pass == 1) std::reverse(rp_deals.begin(), rp_deals.end());     // the history listed backwards
      w_ready();
      if(pass == 2)
        {
         // a deal that appears inside the cached list: the cache is read again
         RpDeal d = {rp_next_deal++, 0, 0, SV(2021, 1, 11, 10, 2, 45), "", DEAL_TYPE_CHARGE, DEAL_ENTRY_IN, 0.0, 0.0, 0, 0, "", 0.0, 0.0, -1.0};
         rp_deals.insert(rp_deals.begin() + 3, d);
         rp_balance += -1.0;
         w_at(SV(2021, 1, 11, 12, 1, 0));
         LedRead(rp_now);
        }
      for(int mi = 0; mi <= 6; mi++)
        {
         long S = U(SV(2021, 1, 11, 10, mi, 0));
         double b = LedBalance(S);
         if(pass == 0)
           {
            want.push_back(b);
            stamps.push_back(S);
           }
         else if(pass == 1) ckeq(b, want[mi], F("the same B at 10:%02d whatever the list order", mi));
         else ckeq(b, want[mi] - (mi >= 3 ? 1.0 : 0.0), F("the inserted charge counts from 10:03 (B at 10:%02d)", mi));
        }
     }
  }

static int mode_units(const string &dir)
  {
   w_clear_logs(dir);
   u_tables();
   u_m();
   u_plan();
   u_stamps();
   u_ref();
   u_stop();
   u_guard();
   u_lock();
   u_settle();
   u_week();
   u_lots();
   u_caps();
   u_margin();
   u_order();
   u_commission();
   u_history_order();
   JrnClose();
#ifdef CR_NO_GUARD
   const char *ng = "CR_NO_GUARD";
#else
   const char *ng = "guard on";
#endif
   printf("unit worlds (%s): %d checks, %d failed\n", ng, g_checks, g_fails);
   return g_fails ? 1 : 0;
  }

// ------------------------------------------------------------------ T7a: the lab's trades through the mock broker
struct T7Trade
  {
   long i, t_in, t_out;
   int time_exit, side, sl, sym;
   double entry, risk, pnl, lots;
   bool taken, dropped;
   int skip;
   double m, w, unit, B, P_in, rate, budget;
  };
struct T7Pay
  {
   long t;
   double amount;
  };

static std::vector<string> csv_fields(const char *line)
  {
   std::vector<string> f;
   string cur;
   for(const char *p = line; *p && *p != '\n' && *p != '\r'; p++)
     {
      if(*p == ',')
        {
         f.push_back(cur);
         cur.clear();
        }
      else cur += *p;
     }
   f.push_back(cur);
   return f;
  }

static int mode_t7a(int argc, char **argv)
  {
   if(argc < 7)
     {
      fprintf(stderr, "usage: test_account t7a TRADES PAYS WEEKS TABLE OUT [SKEW]\n");
      return 2;
     }
   string out = argv[6];
   long skew = (argc >= 8) ? atol(argv[7]) : 0;
   if(skew > 0)
     {
      fprintf(stderr, "t7a: SKEW must be 0 or negative (the deal before the balance)\n");
      return 2;
     }
   std::vector<T7Trade> tr;
   std::vector<T7Pay> pays;
   std::vector<long> weeks;
   char line[1024];
   FILE *f = fopen(argv[2], "r");
   if(!f || !fgets(line, sizeof line, f)) return 2;
   ea_rows();
   while(fgets(line, sizeof line, f))
     {
      std::vector<string> x = csv_fields(line);
      if(x.size() < 9) continue;
      T7Trade t = T7Trade();
      t.i = atol(x[0].c_str());
      t.t_in = atol(x[1].c_str());
      t.t_out = atol(x[2].c_str());
      t.time_exit = atoi(x[3].c_str());
      t.sl = CrSleeveOfCode(x[4]);
      t.side = atoi(x[5].c_str());
      t.entry = strtod(x[6].c_str(), nullptr);
      t.risk = strtod(x[7].c_str(), nullptr);
      t.pnl = strtod(x[8].c_str(), nullptr);
      if(t.sl < 0)
        {
         fprintf(stderr, "unknown code %s\n", x[4].c_str());
         return 2;
        }
      t.sym = g_sl[t.sl].sym;
      t.skip = -1;
      tr.push_back(t);
     }
   fclose(f);
   f = fopen(argv[3], "r");
   if(!f || !fgets(line, sizeof line, f)) return 2;
   while(fgets(line, sizeof line, f))
     {
      std::vector<string> x = csv_fields(line);
      if(x.size() < 2) continue;
      pays.push_back({atol(x[0].c_str()), strtod(x[1].c_str(), nullptr)});
     }
   fclose(f);
   f = fopen(argv[4], "r");
   if(!f || !fgets(line, sizeof line, f)) return 2;
   while(fgets(line, sizeof line, f))
     {
      std::vector<string> x = csv_fields(line);
      if(x.size() < 2) continue;
      weeks.push_back(atol(x[1].c_str()));
     }
   fclose(f);
   if(tr.empty() || weeks.size() < 2) return 2;
   // the world: 1,000 EUR in the account before the plan start, a week before the first entry
   long T = ClkUtcToServer(tr[0].t_in) - 7 * 86400;
   w_clear_logs(out);
   if(!w_reset(1000.0, T + 1, true, T, argv[5])) return 3;
   g_cfg.push = false;
   rp_now = T + 1;
   LedRead(rp_now);
   rp_now = T + 3;
   if(LedRead(rp_now) != CR_LED_OK) return 4;
   std::vector<long> tin_sorted;
   for(const T7Trade &t : tr) tin_sorted.push_back(t.t_in);
   std::sort(tin_sorted.begin(), tin_sorted.end());
   // mock-level events: (server time, kind 0 payment / 1 closing deal / 2 sizing) -> index
   std::multimap<std::pair<long, int>, long> q;
   for(size_t k = 0; k < pays.size(); k++) q.insert({{ClkUtcToServer(pays[k].t), 0}, (long)k});
   for(size_t k = 0; k < tr.size(); k++) q.insert({{ClkUtcToServer(tr[k].t_in) + 2, 2}, (long)k});
   long n_pay = 0, n_pay_skipped = 0, n_dropped = 0, n_out = 0, reads = 0, n_wait = 0, n_wait_trades = 0, n_window = 0;
   std::vector<char> waited(tr.size(), 0);
   bool late_stop = false;
   while(!q.empty())
     {
      auto it = q.begin();
      long ts = it->first.first;
      int kind = it->first.second;
      long idx = it->second;
      q.erase(it);
      rp_now = ts;
      if(kind == 0)
        {
         LedRead(rp_now);
         reads++;
         long C = (long)LedStopTime();
         if(C > 0 && C < pays[idx].t)
           {
            n_pay_skipped++;                          // stopped: the lab pays nothing in any more (growth.py:194)
            continue;
           }
         RpPay p = {ts, ts - skew, pays[idx].amount, false};          // the balance shows it at t_deal - skew
         rp_pays.push_back(p);
         rp_book_payments(rp_now);
         rp_deliver_tx();
         n_pay++;
        }
      else if(kind == 1)
        {
         T7Trade &x = tr[idx];
         if(x.dropped) continue;
         LedRead(rp_now);
         reads++;
         long C = (long)LedStopTime();
         if(C > 0)
           {
            auto nx = std::upper_bound(tin_sorted.begin(), tin_sorted.end(), C);
            bool drop = (nx != tin_sorted.end()) ? (x.t_out >= *nx) : (x.t_out > C);
            if(drop)
              {
               if(nx == tin_sorted.end()) late_stop = true;   // after the last entry the lab drops at once: not handled here
               x.dropped = true;
               n_dropped++;
               continue;
              }
           }
         double money = x.pnl * x.lots * W_SYM[x.sym].units * W_USDEUR;   // growth.py:236
         long pi = rp_pos_index((ulong)x.i + 1);
         if(pi < 0)
           {
            ck(false, F("trade %ld: no position", x.i));
            continue;
           }
         RpPos p = rp_pos[pi];
         rp_add_deal(p, p.type == 0 ? 1 : 0, DEAL_ENTRY_OUT, p.volume, p.price_open, x.time_exit ? DEAL_REASON_EXPERT : DEAL_REASON_SL,
                     g_sl[x.sl].magic, rp_now, money, 0.0, p.ticket, "");
         rp_pos.erase(rp_pos.begin() + pi);
         rp_deliver_tx();
         n_out++;
        }
      else
        {
         T7Trade &x = tr[idx];
         CrIntent itn = w_intent(g_sl[x.sl].code, x.side, CR_ET_MARKET, x.t_in, 0.0, x.risk, x.entry, x.entry, CR_SK_NONE);
         itn.oid = x.i;
         int sk = SizSize(itn, x.t_in, false);
         reads++;
         if(sk == CR_SK_SETTLE)
           {
            // the ledger moves: the intent waits inside its window (SPEC 5) and is sized again 2 s later
            n_wait++;
            if(!waited[idx]) n_wait_trades++;
            waited[idx] = 1;
            if(rp_now + 2 <= ClkUtcToServer(x.t_in) + 300) q.insert({{rp_now + 2, 2}, idx});
            else
              {
               n_window++;
               ck(false, F("trade %ld: still SETTLE at the end of its window", x.i));
               x.skip = sk;
              }
            continue;
           }
         x.skip = sk;
         x.m = itn.m;
         x.w = itn.w;
         x.unit = itn.unit;
         x.B = itn.B;
         x.P_in = itn.P_in;
         x.rate = itn.rate;
         x.budget = itn.budget;
         if(sk != CR_SK_NONE) continue;
         x.taken = true;
         x.lots = itn.lots;
         ulong ticket = (ulong)x.i + 1;                // one ticket per lab trade, in the lab's order
         RpPos p = {ticket, rp_syms[x.sym].name, x.side > 0 ? 0 : 1, x.lots, x.entry, 0.0, 0.0, g_sl[x.sl].magic, rp_now, ""};
         rp_pos.push_back(p);
         rp_add_deal(p, p.type, DEAL_ENTRY_IN, x.lots, x.entry, DEAL_REASON_EXPERT, g_sl[x.sl].magic, rp_now, 0.0, 0.0, ticket, "");
         rp_deliver_tx();
         long t_close = x.time_exit ? ClkUtcToServer(x.t_out) + 2 : ClkUtcToServer(x.t_out - 60) + 30;
         if(t_close <= rp_now) ck(false, F("trade %ld closes before it opens", x.i));
         q.insert({{t_close, 1}, idx});
        }
     }
   rp_now += 120;
   LedRead(rp_now);
   string p_tr = out + "/trades.csv", p_wk = out + "/weeks.csv", p_su = out + "/summary.txt";
   FILE *ft = fopen(p_tr.c_str(), "w");
   FILE *fw = fopen(p_wk.c_str(), "w");
   FILE *fs = fopen(p_su.c_str(), "w");
   if(!ft || !fw || !fs) return 5;
   fprintf(ft, "i,skip,lots,m,w,unit,B,P_in,rate,budget,dropped\n");
   long cnt[CR_SK_SELFTEST + 1] = {0};
   for(const T7Trade &x : tr)
     {
      fprintf(ft, "%ld,%d,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%d\n", x.i, x.skip, x.lots, x.m, x.w, x.unit, x.B, x.P_in, x.rate,
              x.budget, x.dropped ? 1 : 0);
      if(x.skip >= 0 && x.skip <= CR_SK_SELFTEST) cnt[x.skip]++;
     }
   fprintf(fw, "w,end_srv,B,P_in\n");
   for(size_t k = 0; k + 1 < weeks.size(); k++)
     {
      long S = U(weeks[k + 1]) - 1;
      fprintf(fw, "%zu,%ld,%.17g,%.17g\n", k, weeks[k + 1], LedBalance(S), LedPaidIn(S));
     }
   fprintf(fs, "trades %zu\npayments %zu\npayments_booked %ld\npayments_skipped %ld\nclosing_deals %ld\ndropped %ld\nstop_utc %ld\n"
           "late_stop %d\nreads %ld\ndeals %zu\nstop_latched %d\nguard_latched %d\nsettled %d\nskew %ld\nsettle_waits %ld\n"
           "settle_wait_trades %ld\nsettle_past_window %ld\nfails %d\n", tr.size(), pays.size(), n_pay, n_pay_skipped, n_out, n_dropped,
           (long)LedStopTime(), late_stop ? 1 : 0, reads, rp_deals.size(), LedStopLatched() ? 1 : 0, LedGuardLatched() ? 1 : 0,
           LedSettled() ? 1 : 0, skew, n_wait, n_wait_trades, n_window, g_fails);
   for(int k = 0; k <= CR_SK_SELFTEST; k++) fprintf(fs, "skip_%s %ld\n", SizSkipName(k).c_str(), cnt[k]);
   fclose(ft);
   fclose(fw);
   fclose(fs);
   JrnClose();
   printf("t7a %s: %zu trades, taken %ld, min_lot %ld, cap %ld, margin %ld, stopped %ld, stop %ld, reads %ld\n", argv[5], tr.size(),
          cnt[CR_SK_NONE], cnt[CR_SK_MIN_LOT], cnt[CR_SK_CAP], cnt[CR_SK_MARGIN], cnt[CR_SK_STOPPED], (long)LedStopTime(), reads);
   return g_fails ? 1 : 0;
  }

int main(int argc, char **argv)
  {
   if(argc >= 2 && string(argv[1]) == "rows") return mode_rows();
   if(argc >= 2 && string(argv[1]) == "t7a") return mode_t7a(argc, argv);
   return mode_units(argc >= 2 ? argv[1] : "check/out/test_account/unit");
  }
