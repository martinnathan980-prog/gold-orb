// T2 data: CR_Bars and CR_Math (SPEC 2.2, step B) in the replay mock; no argument = the mock worlds below
// build: entry=src/CR_Bars.mqh subst=CR_Clock.mqh=check/dbl/CR_Clock_dbl.mqh sanitize
//
// Modes (check/test_bars.py drives the last two):
//   test_bars                         the mock worlds: barrier, missing minute (wait, GAP), late revision (LATEBAR, at
//                                     most one per 5 min), READY (SERIES_SYNCHRONIZED false, a hole that fills, a hole
//                                     that stays, short history, no history, stability), mask, store API; synthetic
//                                     bars; exit 0 when every check holds
//   test_bars math IN OUT             the rolling primitives on the series of IN, the results to OUT (binary)
//   test_bars store DIR SYM=PATH ...  [--closures S] [--timer-calls N]: replays exported bars through the store minute
//                                     by minute as CR_Main does (load at the first event, then polls); the fed bars go
//                                     to stdout (80-byte records), the daily costs to DIR/costs.bin, the hour, 4-hour
//                                     and trading-day aggregates to DIR/agg.bin, counts to DIR/summary.json
// The module's own state is the EA's (translated src/CR_Bars.mqh, src/CR_Math.mqh, with the clock double of S0).
#include "mock_replay.h"
#include "ea.cpp"
#include <cinttypes>
#include <string>
#include <vector>

// ------------------------------------------------------------------ the symbol rows of CR_Registry RegInit
static const char *W_NAME[CR_NSYM] = {"XAUUSD.r", "US100.r", "BTCUSD.r", "ETHUSD.r"};

static void ea_sym(int s, const char *base, const char *lab, int family, int comm_pts, double mkt, double stop, int depth, double model_bp)
  {
   g_sym[s].base = base;
   g_sym[s].lab = lab;
   g_sym[s].name = W_NAME[s];
   g_sym[s].family = family;
   g_sym[s].digits = 2;
   g_sym[s].point = 0.01;
   g_sym[s].comm_pts = comm_pts;
   g_sym[s].h = comm_pts * 0.5 * 0.01;                 // RegSetPoint: comm_pts / 2 x point
   g_sym[s].slip_mkt = mkt * 1e-4;
   g_sym[s].slip_stop = stop * 1e-4;
   g_sym[s].depth_days = depth;
   g_sym[s].model_bp = model_bp;
   g_sym[s].ok = true;
  }

static bool ea_setup(const string &closures, int depth_xau, int depth_other)
  {
   g_cfg = CrConfig();
   g_cfg.harness = true;
   g_cfg.push = true;
   g_cfg.tester = false;
   ea_sym(CR_XAU, "XAUUSD", "xauusd", CR_FAM_XAU, CR_XAU_COMM_PTS, 0.3, 1.0, depth_xau, 0.47);
   ea_sym(CR_IDX, "US100", "us100", CR_FAM_IDX, 0, 0.2, 0.5, depth_other, 0.37);
   ea_sym(CR_BTC, "BTCUSD", "btcusd", CR_FAM_CRY, 0, 0.5, 1.5, depth_other, 2.96);
   ea_sym(CR_ETH, "ETHUSD", "ethusd", CR_FAM_CRY, 0, 0.7, 2.0, depth_other, 13.0);
   string err;
   if(!ClkInit(closures, err)) { fprintf(stderr, "ClkInit: %s\n", err.c_str()); return false; }
   JrnInit();
   if(!BarsInit(err)) { fprintf(stderr, "BarsInit: %s\n", err.c_str()); return false; }
   return true;
  }

// ------------------------------------------------------------------ the mock world (bars only)
static void w_reset(const string &dir)
  {
   JrnClose();
   rp_syms.clear();
   rp_root = dir;
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
   rp_now = 0;
   rp_ms = 0;
   rp_pushes = 0;
  }

// the bar part of the mock's advance(T): the bar starting at T forms; a symbol without one shows its last bar closed
static void w_advance(long T)
  {
   for(RpSym &s : rp_syms)
     {
      long c = s.cur;
      while(c + 1 < (long)s.bars.size() && s.bars[c + 1].time <= T) c++;
      if(c != s.cur && c >= 0)
        {
         s.cur = c;
         s.stage = 1;
         s.tick_bid = s.bars[c].open;
         s.vis_h = s.vis_l = s.tick_bid;
         s.tick_time = s.bars[c].time;
        }
      if(c >= 0 && s.bars[c].time + 60 <= T)
        {
         s.stage = 4;
         s.tick_bid = s.bars[c].close;
         s.vis_h = s.bars[c].high;
         s.vis_l = s.bars[c].low;
         s.tick_time = s.bars[c].time + 59;
        }
     }
  }

static uint64_t g_rng = 88172645463325252ULL;
static uint64_t rnd()
  {
   g_rng ^= g_rng << 13;
   g_rng ^= g_rng >> 7;
   g_rng ^= g_rng << 17;
   return g_rng;
  }

static MqlRates w_bar(long srv, long o, long h, long l, long c, int spread)
  {
   MqlRates b = MqlRates();
   b.time = srv;
   b.open = o / 100.0;
   b.high = h / 100.0;
   b.low = l / 100.0;
   b.close = c / 100.0;
   b.spread = spread;
   b.tick_volume = 1;
   return b;
  }

// one bar per minute of [u0, u1) (UTC) outside the family's known closures; never bid-flat
static void w_gen(RpSym &s, int family, long u0, long u1, long p0)
  {
   long c = p0;
   long u = u0;
   while(u < u1)
     {
      datetime c0 = 0, c1 = 0;
      if(ClkInClosure(family, u, c0, c1) && c1 > u)
        {
         u = c1;
         continue;
        }
      long o = c + (long)(rnd() % 7) - 3;
      long cl = o + (long)(rnd() % 11) - 5;
      long h = std::max(o, cl) + 1 + (long)(rnd() % 4), l = std::min(o, cl) - 1 - (long)(rnd() % 4);
      s.bars.push_back(w_bar(ClkUtcToServer(u), o, h, l, cl, 3 + (int)(rnd() % 20)));
      c = cl;
      u += 60;
     }
  }

static RpSym &w_sym(int id)
  {
   while((int)rp_syms.size() <= id)
     {
      RpSym s;
      s.name = W_NAME[rp_syms.size()];
      s.digits = 2;
      s.point = 0.01;
      rp_syms.push_back(s);
     }
   return rp_syms[id];
  }

static void w_sort(RpSym &s)
  {
   std::sort(s.bars.begin(), s.bars.end(), [](const MqlRates &a, const MqlRates &b) { return a.time < b.time; });
  }

// ------------------------------------------------------------------ the driver (CR_Main's use of the API)
struct FedRec
  {
   int64_t t;
   int32_t sym, s_raw;
   double  bo, bh, bl, bc, ao, ah, al, ac;
  };
static_assert(sizeof(FedRec) == 80, "record size");

struct AggRec
  {
   int32_t sym, kind;                 // kind 0: UTC hour, 1: UTC 4 hours, 2: trading day (server date)
   int64_t key, t_first, t_last;
   int32_t n, pad;
   double  bo, bh, bl, bc, ao, ah, al, ac, mh, ml;
  };
static_assert(sizeof(AggRec) == 120, "record size");

struct CostRec
  {
   int32_t sym, pad;
   int64_t day;
   double  raw_bp, paper_bp;
  };

struct Drv
  {
   int st = 0;                        // 0: load at the next pass, 1: live
   long gM = 0;
   int loads = 0, latebars = 0, waits = 0, retries = 0;
   long fed_load = 0, fed_total = 0;  // bars fed since the last load / in total
   bool order_ok = true, contract_ok = true;
   long last_t = -1;
   int last_sym = -1;
   long first_bad = 0;
   std::vector<FedRec> keep;          // the bars fed since the last load (worlds)
   bool keep_bars = true;
   FILE *out = nullptr;               // store mode: fed bars
   FILE *aggf = nullptr, *costf = nullptr;
   CrAgg agg[CR_NSYM][3];
   long day = 0;
   long n_agg = 0, n_cost = 0;
   std::vector<long> load_at;         // server time of each load
   std::vector<long> late_at;         // server time of each CR_POLL_LATEBAR
  };

static void agg_write(Drv &d, int sym, int kind, const CrAggBar &a)
  {
   if(!d.aggf) return;
   AggRec r = {sym, kind, a.key, a.t_first, a.t_last, a.n, 0, a.bo, a.bh, a.bl, a.bc, a.ao, a.ah, a.al, a.ac, a.mh, a.ml};
   fwrite(&r, sizeof r, 1, d.aggf);
   d.n_agg++;
  }

static long agg_key(int kind, long t) { return kind == 0 ? CrAggKey(t, 3600) : (kind == 1 ? CrAggKey(t, 14400) : ClkServerDay(t)); }
static long agg_end(int kind, long key) { return kind == 0 ? key + 3600 : (kind == 1 ? key + 14400 : ClkServerToUtc(key + 86400)); }

static void on_fed(Drv &d, const CrBar &b, long m)
  {
   if(b.t < d.last_t || (b.t == d.last_t && b.sym <= d.last_sym)) { if(d.order_ok) d.first_bad = b.t; d.order_ok = false; }
   if(!(b.t < m && b.t >= m - 60)) { if(d.contract_ok) d.first_bad = b.t; d.contract_ok = false; }
   d.last_t = b.t;
   d.last_sym = b.sym;
   d.fed_load++;
   d.fed_total++;
   FedRec r = {b.t, b.sym, b.s_raw, b.bo, b.bh, b.bl, b.bc, b.ao, b.ah, b.al, b.ac};
   if(d.out) fwrite(&r, sizeof r, 1, d.out);
   if(d.keep_bars) d.keep.push_back(r);
   if(d.aggf)
      for(int k = 0; k < 3; k++)
        {
         CrAggBar done;
         if(d.agg[b.sym][k].Add(b, agg_key(k, b.t), done)) agg_write(d, b.sym, k, done);
        }
  }

static void drv_minute(Drv &d, long m)
  {
   CrBar b;
   while(BarsNext(m, b)) on_fed(d, b, m);
   long day = ClkServerDay(m);
   if(day != d.day)
     {
      if(d.day != 0 && d.costf)
         for(int s = 0; s < CR_NSYM; s++)
           {
            double raw = 0, pap = 0;
            if(!BarsCost(s, d.day, raw, pap)) continue;
            CostRec c = {s, 0, d.day, raw, pap};
            fwrite(&c, sizeof c, 1, d.costf);
            d.n_cost++;
           }
      d.day = day;
     }
   if(d.aggf)
      for(int s = 0; s < CR_NSYM; s++)
         for(int k = 0; k < 3; k++)
           {
            CrAggBar cur;
            if(d.agg[s][k].Peek(cur) && agg_end(k, cur.key) <= m)
              {
               d.agg[s][k].Take(cur);
               agg_write(d, s, k, cur);
              }
           }
  }

// one timer pass (OnTimer: WAIT/REPLAY -> MainRebuild, LIVE -> MainLive)
static void drv_pass(Drv &d, long now)
  {
   if(d.st == 0)
     {
      if(BarsLoad(now) != CR_LOAD_OK) { d.retries++; return; }
      d.loads++;
      d.load_at.push_back(now);
      d.fed_load = 0;
      d.keep.clear();
      d.last_t = -1;
      d.last_sym = -1;
      for(int s = 0; s < CR_NSYM; s++)
         for(int k = 0; k < 3; k++) d.agg[s][k].Clear();
      long M1 = BarsBarrier(now);
      long start = BarsStart();
      d.gM = (start > 0 && start < M1) ? start : M1;
      for(long m = d.gM + 60; m <= M1; m += 60) drv_minute(d, m);
      d.gM = M1;
      d.st = 1;
      return;
     }
   BarsTimer(now);
   long M = BarsBarrier(now);
   if(M <= d.gM) return;
   int r = BarsPoll(M);
   if(r == CR_POLL_WAIT) { d.waits++; return; }
   if(r == CR_POLL_LATEBAR)
     {
      d.latebars++;
      d.late_at.push_back(now);
      d.st = 0;
      return;
     }
   if(d.gM == 0) d.gM = M - 60;
   for(long m = d.gM + 60; m <= M; m += 60) drv_minute(d, m);
   d.gM = M;
  }

// the event loop of mock_replay.h: one event per distinct bar start >= from, timer passes at T + 2, T + 3, ...
static void drv_run(Drv &d, long from, long to, int timer_calls)
  {
   std::vector<long> ev;
   for(const RpSym &s : rp_syms)
      for(const MqlRates &b : s.bars)
         if(b.time >= from && b.time < to) ev.push_back(b.time);
   std::sort(ev.begin(), ev.end());
   ev.erase(std::unique(ev.begin(), ev.end()), ev.end());
   for(long T : ev)
     {
      rp_now = T;
      rp_ms = 0;
      w_advance(T);
      for(int c = 0; c < timer_calls; c++)
        {
         rp_now = T + 2 + c;
         rp_ms = 500;
         drv_pass(d, rp_now);
        }
     }
  }

// ------------------------------------------------------------------ the journal, read back
struct JLine
  {
   long utc;
   string ev, code;
   std::map<string, string> kv;
  };

static std::vector<JLine> read_journal()
  {
   JrnClose();
   std::vector<string> files;
   if(DIR *d = opendir(rp_path("ClaudeRobot").c_str()))
     {
      while(dirent *e = readdir(d))
         if(strstr(e->d_name, ".log")) files.push_back(rp_path("ClaudeRobot") + "/" + e->d_name);
      closedir(d);
     }
   std::sort(files.begin(), files.end());
   std::vector<JLine> out;
   for(const string &p : files)
     {
      FILE *f = fopen(p.c_str(), "r");
      if(!f) continue;
      char buf[4096];
      while(fgets(buf, sizeof buf, f))
        {
         string ln(buf);
         while(!ln.empty() && (ln.back() == '\n' || ln.back() == '\r')) ln.pop_back();
         std::vector<string> part;
         size_t a = 0;
         while(true)
           {
            size_t b = ln.find('|', a);
            part.push_back(ln.substr(a, b == string::npos ? string::npos : b - a));
            if(b == string::npos) break;
            a = b + 1;
           }
         if(part.size() < 4 || part[0] != "CR") continue;
         JLine j;
         j.utc = atol(part[1].c_str());
         j.ev = part[2];
         j.code = part[3];
         for(size_t k = 4; k < part.size(); k++)
           {
            size_t q = part[k].find('=');
            if(q != string::npos) j.kv[part[k].substr(0, q)] = part[k].substr(q + 1);
           }
         out.push_back(j);
        }
      fclose(f);
     }
   return out;
  }

static int count_ev(const std::vector<JLine> &J, const string &ev, const string &code = "")
  {
   int n = 0;
   for(const JLine &j : J)
      if(j.ev == ev && (code.empty() || j.code == code)) n++;
   return n;
  }

static const JLine *first_ev(const std::vector<JLine> &J, const string &ev, const string &code, const string &key = "", const string &val = "")
  {
   for(const JLine &j : J)
      if(j.ev == ev && j.code == code && (key.empty() || (j.kv.count(key) && j.kv.at(key) == val))) return &j;
   return nullptr;
  }

// ------------------------------------------------------------------ checks
static int g_fail = 0, g_pass = 0;
static string g_world;
static void check(bool ok, const char *what, const string &detail = "")
  {
   if(ok) g_pass++;
   else
     {
      g_fail++;
      printf("FAIL [%s] %s %s\n", g_world.c_str(), what, detail.c_str());
     }
  }
static string S(long v) { return std::to_string(v); }

// a standard world: four symbols, synthetic bars from load - 3 days to load + `after` seconds (UTC)
static const long W_LOAD = 1615388400;           // 2021-03-10 15:00 UTC, a Wednesday (10:00 New York)

static void w_standard(long after)
  {
   g_rng = 88172645463325252ULL;
   long u0 = W_LOAD - 3 * 86400, u1 = W_LOAD + after;
   w_gen(w_sym(CR_XAU), CR_FAM_XAU, u0, u1, 172500);
   w_gen(w_sym(CR_IDX), CR_FAM_IDX, u0, u1, 1290000);
   w_gen(w_sym(CR_BTC), CR_FAM_CRY, u0, u1, 5400000);
   w_gen(w_sym(CR_ETH), CR_FAM_CRY, u0, u1, 180000);
  }

static void w_begin(const string &name)
  {
   g_world = name;
   w_reset("check/out/test_bars/worlds/" + name);
   rp_now = ClkUtcToServer(W_LOAD);
  }

// bars of a symbol starting in [u_from, u_before) (UTC)
static long count_bars(int sym, long u_from, long u_before)
  {
   long n = 0;
   for(const MqlRates &b : rp_syms[sym].bars)
     {
      long u = ClkServerToUtc(b.time);
      if(u >= u_from && u < u_before) n++;
     }
   return n;
  }

// 1. a clean start: READY at the first check, the barrier, every bar fed once in (time, symbol) order
static void world_clean()
  {
   w_begin("clean");
   w_standard(3600);
   ea_setup("", 2, 1);
   Drv d;
   drv_run(d, ClkUtcToServer(W_LOAD), LONG_MAX, 3);
   std::vector<JLine> J = read_journal();
   for(int s = 0; s < CR_NSYM; s++)
     {
      const JLine *r = first_ev(J, "READY", g_sym[s].base);
      check(r && r->utc == W_LOAD + 4, "READY at the first check (load + 2 s)", r ? S(r->utc - W_LOAD) : "none");
      check(BarsReady(s), "BarsReady true");
     }
   check(count_ev(J, "NOTREADY") == 0 && count_ev(J, "GAP") == 0 && count_ev(J, "LATEBAR") == 0, "no NOTREADY, GAP or LATEBAR");
   check(d.loads == 1 && d.latebars == 0 && d.waits == 0, "one load, no wait", S(d.loads) + " " + S(d.waits));
   check(d.order_ok && d.contract_ok, "bars fed in (time, symbol) order, each at the first barrier after its start");
   long last_ev = 0;
   for(const RpSym &s : rp_syms) last_ev = std::max(last_ev, (long)s.bars.back().time);
   long expect = 0;
   for(int s = 0; s < CR_NSYM; s++) expect += count_bars(s, W_LOAD - g_sym[s].depth_days * 86400L, ClkServerToUtc(last_ev));
   check(d.fed_total == expect, "every bar before the last barrier fed", S(d.fed_total) + " vs " + S(expect));
   // the store API: BarsCount / BarsAt / BarsIndex on fed bars only
   long n0 = BarsCount(CR_XAU);
   CrBar b0, b1;
   bool past = BarsAt(CR_XAU, (int)n0, b1);
   check(n0 > 0 && BarsAt(CR_XAU, 0, b0) && !past && !BarsAt(CR_XAU, -1, b1), "BarsAt bounds");
   BarsAt(CR_XAU, (int)n0 - 1, b1);
   check(BarsIndex(CR_XAU, b1.t) == n0 - 1 && BarsIndex(CR_XAU, b1.t + 1) == n0 && BarsIndex(CR_XAU, 0) == 0, "BarsIndex");
   check(BarsStart() == W_LOAD - 2 * 86400 && b0.t == W_LOAD - 2 * 86400, "BarsStart = the first bar of the gold window", S(BarsStart() - W_LOAD));
   // paper quotes of a fed bar: bid - h, bid + spread x point + h on the 2-digit grid
   const RpSym &gx = rp_syms[CR_XAU];
   const MqlRates *raw = nullptr;
   for(const MqlRates &q : gx.bars)
      if(ClkServerToUtc(q.time) == b1.t) raw = &q;
   double h = g_sym[CR_XAU].h;
   check(raw && b1.bo == rp_norm(raw->open - h, 2) && b1.ac == rp_norm(raw->close + raw->spread * 0.01 + h, 2) && b1.s_raw == raw->spread,
         "paper quotes of a stored bar");
   double pb = 0, pa = 0;
   BarsPaperQuotes(CR_XAU, 1725.00, 1725.13, pb, pa);
   check(pb == rp_norm(1725.00 - h, 2) && pa == rp_norm(1725.13 + h, 2), "BarsPaperQuotes");
   // the daily cost line of the load day: medians of the kept bars fed that day
   double raw_bp = 0, pap_bp = 0;
   long day = ClkServerDay(b1.t);
   bool okc = BarsCost(CR_XAU, day, raw_bp, pap_bp);
   std::vector<double> rv, pv;
   for(const FedRec &f : d.keep)
      if(f.sym == CR_XAU && ClkServerDay(f.t) == day)
        {
         double mid = (f.bo + f.ao) / 2;
         rv.push_back(f.s_raw * 0.01 / mid * 1e4);
         pv.push_back((f.ao - f.bo) / mid * 1e4);
        }
   auto med = [](std::vector<double> v) { std::sort(v.begin(), v.end()); size_t m = v.size() / 2; return v.size() % 2 ? v[m] : (v[m - 1] + v[m]) / 2; };
   check(okc && !rv.empty() && raw_bp == med(rv) && pap_bp == med(pv), "BarsCost = medians of the day's fed kept bars");
   check(!BarsCost(CR_XAU, day + 86400 * 30, raw_bp, pap_bp), "BarsCost false for a day without bars");
  }

// 2. the barrier: the minute starts when every symbol has ticked in it, or is closed; else 2 s later
static void world_barrier()
  {
   w_begin("barrier");
   w_standard(9 * 3600);
   // gold has no bar at W_LOAD + 600 (a silent minute while its market is open)
   RpSym &g = w_sym(CR_XAU);
   long silent = ClkUtcToServer(W_LOAD + 600);
   g.bars.erase(std::remove_if(g.bars.begin(), g.bars.end(), [&](const MqlRates &b) { return b.time == silent; }), g.bars.end());
   ea_setup("", 2, 1);
   Drv d;
   drv_run(d, ClkUtcToServer(W_LOAD), ClkUtcToServer(W_LOAD + 300), 3);
   long T = ClkUtcToServer(W_LOAD + 300);
   rp_now = T;
   w_advance(T);
   rp_now = T + 1;                                    // 1 s into the minute: every symbol ticked at T
   check(BarsBarrier(T + 1) == W_LOAD + 300, "every symbol ticked: barrier = the new minute at T + 1 s", S(BarsBarrier(T + 1) - W_LOAD));
   check(BarsBarrier(T) == W_LOAD + 300, "every symbol ticked: barrier = the new minute at T + 0 s");
   rp_now = silent;
   w_advance(silent);
   rp_now = silent + 1;
   check(BarsBarrier(silent + 1) == W_LOAD + 540, "gold silent, market open: barrier waits (previous minute)", S(BarsBarrier(silent + 1) - W_LOAD));
   check(BarsBarrier(silent + 2) == W_LOAD + 600, "gold silent: barrier = the new minute at T + 2 s");
   // 17:30 New York on that day: gold and US100 are in their daily closure, crypto ticks
   long u_close = W_LOAD - 15 * 3600 + 22 * 3600 + 30 * 60;   // 2021-03-10 22:30 UTC = 17:30 New York
   long T2 = ClkUtcToServer(u_close);
   rp_now = T2;
   w_advance(T2);
   rp_now = T2 + 1;
   check(BarsBarrier(T2 + 1) == u_close, "gold and US100 closed, crypto ticked: barrier = the new minute", S(BarsBarrier(T2 + 1) - u_close));
  }

// 3. SERIES_SYNCHRONIZED false at the load and for 5 minutes: NOT_READY (sync), then READY
static void world_unsync()
  {
   w_begin("unsync");
   w_standard(1800);
   long a = ClkUtcToServer(W_LOAD) - 10, b = ClkUtcToServer(W_LOAD) + 300;
   w_sym(CR_XAU).unsync.push_back({a, b});
   ea_setup("", 2, 1);
   Drv d;
   drv_run(d, ClkUtcToServer(W_LOAD), LONG_MAX, 3);
   std::vector<JLine> J = read_journal();
   const JLine *nr = first_ev(J, "NOTREADY", "XAUUSD");
   const JLine *r = first_ev(J, "READY", "XAUUSD");
   check(nr && nr->kv.at("why") == "sync", "NOTREADY why=sync", nr ? nr->kv.at("why") : "none");
   check(r && r->utc >= W_LOAD + 300 && r->utc <= W_LOAD + 300 + 62, "READY at the first check after the series is synchronized",
         r ? S(r->utc - W_LOAD) : "none");
   check(first_ev(J, "READY", "US100") && first_ev(J, "READY", "US100")->utc == W_LOAD + 4, "the other symbols READY at the first check");
   check(d.latebars == 0, "no rebuild");
  }

// 4. a hole that stays: GAP, three re-reads, GAP accepted=1, READY
static void world_hole_stays()
  {
   w_begin("hole_stays");
   w_standard(1800);
   long a = ClkUtcToServer(W_LOAD - 86400), b = a + 7200;      // 2021-03-09 15:00-17:00 UTC: gold open
   w_sym(CR_XAU).holes.push_back({a, b, 0});
   // later, a late revision forces a rebuild: the accepted hole must not hold gold back again
   long tr = ClkUtcToServer(W_LOAD + 900);
   w_sym(CR_XAU).revise.push_back({(double)tr, (double)(tr + 125), 0.03});
   ea_setup("", 2, 1);
   Drv d;
   drv_run(d, ClkUtcToServer(W_LOAD), LONG_MAX, 3);
   std::vector<JLine> J = read_journal();
   check(d.loads == 2 && d.load_at.size() == 2, "one rebuild after the revision", S(d.loads));
   if(d.load_at.size() == 2)
     {
      const JLine *r2 = nullptr;
      for(const JLine &j : J)
         if(j.ev == "READY" && j.code == "XAUUSD") r2 = &j;
      long l2 = ClkServerToUtc(d.load_at[1]);
      // the first pass at least 2 s after the rebuild (next minute here), not 3 re-reads later
      check(r2 && r2->utc >= l2 + 2 && r2->utc <= l2 + 62, "after the rebuild gold is READY at the first check (the hole stays accepted)",
            r2 ? S(r2->utc - l2) : "none");
      check(count_ev(J, "GAP", "XAUUSD") == 2, "no new GAP line after the rebuild", S(count_ev(J, "GAP", "XAUUSD")));
     }
   const JLine *g0 = first_ev(J, "GAP", "XAUUSD", "accepted", "0");
   const JLine *g1 = first_ev(J, "GAP", "XAUUSD", "accepted", "1");
   const JLine *r = first_ev(J, "READY", "XAUUSD");
   check(g0 && atol(g0->kv.at("from").c_str()) == ClkServerToUtc(a) - 0 && atol(g0->kv.at("to").c_str()) == ClkServerToUtc(b),
         "GAP from the hole's first missing minute to the next bar", g0 ? g0->kv.at("from") + "-" + g0->kv.at("to") : "none");
   check(g0 && g0->utc == W_LOAD + 4, "GAP at the first check");
   check(g1 && g1->utc == W_LOAD + 4 + 180 && g1->kv.at("reads") == "3", "accepted after 3 re-reads 60 s apart", g1 ? S(g1->utc - W_LOAD) : "none");
   check(r && r->utc == g1->utc, "READY with the acceptance");
   const JLine *nr = first_ev(J, "NOTREADY", "XAUUSD");
   check(nr && nr->kv.at("why") == "holes", "NOTREADY why=holes");
   check(rp_pushes >= 1, "a GAP push");
  }

// 5. a hole that fills 90 s after the load: GAP, the re-read finds the bars, LATEBAR, rebuild, READY
static void world_hole_fills()
  {
   w_begin("hole_fills");
   w_standard(1800);
   long a = ClkUtcToServer(W_LOAD - 86400), b = a + 7200;
   long u = ClkUtcToServer(W_LOAD) + 90;
   w_sym(CR_XAU).holes.push_back({a, b, u});
   ea_setup("", 2, 1);
   Drv d;
   drv_run(d, ClkUtcToServer(W_LOAD), LONG_MAX, 3);
   std::vector<JLine> J = read_journal();
   check(first_ev(J, "GAP", "XAUUSD", "accepted", "0") != nullptr, "GAP at the first check");
   check(first_ev(J, "GAP", "XAUUSD", "accepted", "1") == nullptr, "never accepted");
   const JLine *lb = first_ev(J, "LATEBAR", "XAUUSD");
   check(lb && lb->kv.at("why") == "hole filled", "LATEBAR why=hole filled", lb ? lb->kv.at("why") : "none");
   check(d.loads == 2 && d.latebars == 1, "one rebuild", S(d.loads));
   const JLine *r = nullptr;
   for(const JLine &j : J)
      if(j.ev == "READY" && j.code == "XAUUSD") r = &j;
   check(r && r->utc > ClkServerToUtc(u), "READY after the rebuild");
   check(BarsReady(CR_XAU), "BarsReady after the rebuild");
   // the hole's bars are in the store now
   int i0 = BarsIndex(CR_XAU, ClkServerToUtc(a)), i1 = BarsIndex(CR_XAU, ClkServerToUtc(b));
   check(i1 - i0 == 120, "the 120 bars of the hole are stored after the rebuild", S(i1 - i0));
  }

// 6. a live minute whose bar comes 10 s late: the poll waits, then feeds it in order, no GAP
static void world_live_wait()
  {
   w_begin("live_wait");
   w_standard(1800);
   long t1 = ClkUtcToServer(W_LOAD + 300);           // gold bar of 15:05 UTC
   w_sym(CR_XAU).holes.push_back({t1, t1 + 60, t1 + 60 + 12});
   ea_setup("", 2, 1);
   Drv d;
   drv_run(d, ClkUtcToServer(W_LOAD), LONG_MAX, 40);
   std::vector<JLine> J = read_journal();
   check(d.waits >= 5 && d.waits <= 12, "the poll waited about 10 s", S(d.waits));
   check(count_ev(J, "GAP") == 0 && d.latebars == 0, "no GAP, no rebuild");
   bool found = false;
   for(const FedRec &f : d.keep)
      if(f.sym == CR_XAU && f.t == W_LOAD + 300) found = true;
   check(found && d.order_ok && d.contract_ok, "the late bar fed in order");
  }

// 7. a live minute whose bar comes 45 s late: GAP after 30 s, the chain goes on; the bar then shows in the last-3 re-read
//    (LATEBAR, rebuild)
static void world_live_gap()
  {
   w_begin("live_gap");
   w_standard(1800);
   long t2 = ClkUtcToServer(W_LOAD + 600);
   w_sym(CR_XAU).holes.push_back({t2, t2 + 60, t2 + 60 + 45});
   ea_setup("", 2, 1);
   Drv d;
   drv_run(d, ClkUtcToServer(W_LOAD), LONG_MAX, 40);
   std::vector<JLine> J = read_journal();
   const JLine *g = first_ev(J, "GAP", "XAUUSD", "live", "1");
   check(g && atol(g->kv.at("minute").c_str()) == W_LOAD + 600, "GAP live for the missing minute");
   check(g && g->utc >= W_LOAD + 660 + 30 && g->utc <= W_LOAD + 660 + 34, "GAP after 30 s of waiting", g ? S(g->utc - W_LOAD - 660) : "none");
   const JLine *lb = first_ev(J, "LATEBAR", "XAUUSD");
   check(lb && lb->kv.at("why") == "late bar", "the bar shows after its barrier: LATEBAR why=late bar", lb ? lb->kv.at("why") : "none");
   check(d.loads == 2, "one rebuild", S(d.loads));
   int i = BarsIndex(CR_XAU, W_LOAD + 600);
   CrBar x;
   check(BarsAt(CR_XAU, i, x) && x.t == W_LOAD + 600, "the bar is stored after the rebuild");
  }

// 8. late revisions: the close of a recent bar changes -> LATEBAR; a second one 4 min later waits for the 5-min limit
static void world_revise()
  {
   w_begin("revise");
   w_standard(3600);
   long t3 = ClkUtcToServer(W_LOAD + 600), t4 = ClkUtcToServer(W_LOAD + 840);
   w_sym(CR_XAU).revise.push_back({(double)t3, (double)(t3 + 125), 0.05});
   w_sym(CR_XAU).revise.push_back({(double)t4, (double)(t4 + 125), -0.04});
   ea_setup("", 2, 1);
   Drv d;
   drv_run(d, ClkUtcToServer(W_LOAD), LONG_MAX, 3);
   std::vector<JLine> J = read_journal();
   check(d.latebars == 2 && d.loads == 3, "two rebuilds", S(d.latebars));
   if(d.late_at.size() == 2)
     {
      long first = d.late_at[0], second = d.late_at[1];
      check(first >= t3 + 125 && first <= t3 + 125 + 62, "the first LATEBAR at the first poll after the revision", S(first - t3));
      check(second - first >= 300 && second - first <= 362, "the second LATEBAR waits for the 5-minute limit", S(second - first));
     }
   int nlb = 0;
   for(const JLine &j : J)
      if(j.ev == "LATEBAR" && j.code == "XAUUSD")
        {
         nlb++;
         if(nlb == 2) check(atol(j.kv.at("wait_s").c_str()) > 0, "the second LATEBAR line says it waits", j.kv.at("wait_s"));
        }
   check(nlb == 2, "two LATEBAR lines", S(nlb));
   int i = BarsIndex(CR_XAU, W_LOAD + 600);
   CrBar x;
   const MqlRates *raw = nullptr;
   for(const MqlRates &q : rp_syms[CR_XAU].bars)
      if(q.time == t3) raw = &q;
   check(BarsAt(CR_XAU, i, x) && raw && x.bc == rp_norm(raw->close + 0.05 - g_sym[CR_XAU].h, 2), "the store holds the revised close");
  }

// 9. a revision between the load read and the stability read: rebuild, then READY
static void world_stable()
  {
   w_begin("stable");
   w_standard(1800);
   long t = ClkUtcToServer(W_LOAD - 7200);
   w_sym(CR_XAU).revise.push_back({(double)t, (double)(ClkUtcToServer(W_LOAD) + 3), 0.07});
   ea_setup("", 2, 1);
   Drv d;
   drv_run(d, ClkUtcToServer(W_LOAD), LONG_MAX, 3);
   std::vector<JLine> J = read_journal();
   const JLine *lb = first_ev(J, "LATEBAR", "XAUUSD");
   check(lb && lb->kv.at("why") == "load read changed", "LATEBAR why=load read changed", lb ? lb->kv.at("why") : "none");
   check(d.loads == 2 && BarsReady(CR_XAU), "rebuilt, then READY");
   check(first_ev(J, "READY", "US100") && first_ev(J, "READY", "US100")->utc == W_LOAD + 4, "the others READY at once");
  }

// 10. short history (ETH from load - 12 h, depth 1 day) and no history (BTC from load + 1 h): they do not block the
//     others; BTC's bars are taken as they come; both READY once their depth is there
static void world_depth()
  {
   w_begin("depth");
   g_rng = 7;
   long u0 = W_LOAD - 3 * 86400, u1 = W_LOAD + 2 * 86400;
   w_gen(w_sym(CR_XAU), CR_FAM_XAU, u0, u1, 172500);
   w_gen(w_sym(CR_IDX), CR_FAM_IDX, u0, u1, 1290000);
   w_gen(w_sym(CR_BTC), CR_FAM_CRY, W_LOAD + 3600, u1, 5400000);
   w_gen(w_sym(CR_ETH), CR_FAM_CRY, W_LOAD - 12 * 3600, u1, 180000);
   ea_setup("", 2, 1);
   Drv d;
   drv_run(d, ClkUtcToServer(W_LOAD), LONG_MAX, 3);
   std::vector<JLine> J = read_journal();
   check(first_ev(J, "READY", "XAUUSD") && first_ev(J, "READY", "XAUUSD")->utc == W_LOAD + 4, "gold READY at once");
   const JLine *e0 = first_ev(J, "NOTREADY", "ETHUSD");
   const JLine *b0 = first_ev(J, "NOTREADY", "BTCUSD");
   check(e0 && e0->kv.at("why") == "depth", "ETH NOTREADY why=depth", e0 ? e0->kv.at("why") : "none");
   check(b0 && b0->kv.at("why").find("nodata") != string::npos, "BTC NOTREADY why=nodata", b0 ? b0->kv.at("why") : "none");
   const JLine *er = first_ev(J, "READY", "ETHUSD"), *br = first_ev(J, "READY", "BTCUSD");
   check(er && er->utc >= W_LOAD + 12 * 3600 && er->utc <= W_LOAD + 12 * 3600 + 120, "ETH READY when it has one day", er ? S(er->utc - W_LOAD) : "none");
   check(br && br->utc >= W_LOAD + 3600 + 86400 && br->utc <= W_LOAD + 3600 + 86400 + 120, "BTC READY one day after its first bar",
         br ? S(br->utc - W_LOAD) : "none");
   check(d.loads == 1 && d.latebars == 0, "no rebuild");
   long nb = 0;
   for(const MqlRates &q : rp_syms[CR_BTC].bars)
      if(q.time < rp_syms[CR_BTC].bars.back().time) nb++;
   check(BarsCount(CR_BTC) == nb, "every BTC bar fed as it came", S(BarsCount(CR_BTC)) + " vs " + S(nb));
   check(d.order_ok && d.contract_ok, "order and minute contract");
   // a load with no history at all for every symbol: CR_LOAD_RETRY for 60 s, then CR_LOAD_OK
   rp_syms.clear();
   w_gen(w_sym(CR_XAU), CR_FAM_XAU, W_LOAD + 600, W_LOAD + 900, 172500);
   w_sym(CR_IDX);
   w_sym(CR_BTC);
   w_sym(CR_ETH);
   BarsReset();
   long t = ClkUtcToServer(W_LOAD);
   rp_now = t;
   w_advance(t);
   int r0 = BarsLoad(t), r1 = BarsLoad(t + 30), r2 = BarsLoad(t + 61);
   check(r0 == CR_LOAD_RETRY && r1 == CR_LOAD_RETRY && r2 == CR_LOAD_OK, "every read failed: RETRY for 60 s, then OK",
         S(r0) + S(r1) + S(r2));
  }

// 11. the mask: one bar of every reason, a real NYSE half day (2021-11-26) and a typed HALF day (2021-03-03)
static void world_mask()
  {
   w_begin("mask");
   g_rng = 99;
   // weekday bars of 2021-03-03 (typed HALF) and 2021-11-26 (NYSE half day), 12:00-17:00 New York, US100 and gold
   auto day_bars = [](int sym, long ny0, long p) {
      long c = p;
      for(long ny = ny0 + 12 * 3600; ny < ny0 + 18 * 3600 + 30 * 60; ny += 60)
        {
         long o = c + 1, cl = o + 2;
         w_sym(sym).bars.push_back(w_bar(ny + 7 * 3600, o, cl + 3, o - 3, cl, 5));
         c = cl;
        }
   };
   long d1 = 1614729600, d2 = 1637884800;            // 2021-03-03, 2021-11-26 (00:00 of the New York date)
   day_bars(CR_IDX, d1, 1290000);
   day_bars(CR_IDX, d2, 1600000);
   day_bars(CR_XAU, d1, 172500);
   // bid-flat bars (O = H = L = C), equal to the previous close or not: all kept, since the robot has no flat-bar rule
   // (MT5 makes a bar only when a tick came; lead decision after step B's finding 1)
   RpSym &g = w_sym(CR_XAU);
   long last = g.bars.back().time;
   long pc = (long)llround(g.bars.back().close * 100);
   g.bars.push_back(w_bar(last + 60, pc, pc, pc, pc, 7));                    // flat, equal to the previous close
   g.bars.push_back(w_bar(last + 120, pc + 5, pc + 5, pc + 5, pc + 5, 7));   // flat, not the previous close
   g.bars.push_back(w_bar(last + 180, pc + 5, pc + 5, pc + 5, pc + 5, 7));   // flat, equal to the previous close
   // server Saturday 10:00 for gold; crypto Friday 23:56 server and Saturday 01:00 server
   g.bars.push_back(w_bar(d1 + 3 * 86400 + 10 * 3600, 172600, 172610, 172590, 172605, 5));   // 2021-03-06 is a Saturday
   w_sym(CR_BTC).bars.push_back(w_bar(d1 + 2 * 86400 + 23 * 3600 + 56 * 60, 5400000, 5400100, 5399900, 5400050, 300));
   w_sym(CR_BTC).bars.push_back(w_bar(d1 + 3 * 86400 + 3600, 5400000, 5400100, 5399900, 5400060, 300));
   w_sym(CR_BTC).bars.push_back(w_bar(d1 + 2 * 86400 + 23 * 3600 + 54 * 60, 5400000, 5400100, 5399900, 5400070, 300));
   w_sym(CR_ETH).bars.push_back(w_bar(d1 + 10 * 3600, 180000, 180050, 179950, 180020, 40));
   for(RpSym &s : rp_syms) w_sort(s);
   ea_setup("HALF 2021.03.03", 2, 1);
   Drv d;
   long from = rp_syms[CR_XAU].bars.front().time;
   for(const RpSym &s : rp_syms) from = std::min(from, (long)s.bars.front().time);
   drv_run(d, from, LONG_MAX, 1);
   // expected: US100 on both half days keeps 12:00-13:15 (76 bars), masks 13:16-16:14 (half, 179 bars) and 16:15-17:59
   // (idx, 105 bars); the bars from 18:00 on are kept again (the next trading day)
   check(ClkNyse(d1) == CR_NYSE_HALF && ClkNyse(d2) == CR_NYSE_HALF, "both days are half days for the clock");
   check(BarsMasked(CR_IDX, CR_MASK_HALF) == 2 * 179, "US100 half-day bars after 13:15 masked", S(BarsMasked(CR_IDX, CR_MASK_HALF)));
   // 2021-11-26 is a Friday: from 17:00 New York it is server Saturday (weekend, counted first)
   check(BarsMasked(CR_IDX, CR_MASK_IDX) == 105 + 45, "US100 16:15-17:59 masked (Friday: to 16:59)", S(BarsMasked(CR_IDX, CR_MASK_IDX)));
   // (the 18:29 bar is the last event of the world: still forming, never read)
   check(BarsMasked(CR_IDX, CR_MASK_WEEKEND) == 89, "US100 Friday 17:00-18:28 masked as server weekend", S(BarsMasked(CR_IDX, CR_MASK_WEEKEND)));
   int k1315 = BarsIndex(CR_IDX, d1 + 13 * 3600 + 15 * 60 + 5 * 3600);
   CrBar x;
   check(BarsAt(CR_IDX, k1315, x) && x.t == d1 + 18 * 3600 + 15 * 60, "the 13:15 bar of the half day is kept");
   check(BarsAt(CR_IDX, k1315 + 1, x) && x.t == d1 + 23 * 3600, "the next kept bar is 18:00 New York", S(x.t - d1));
   check(BarsMasked(CR_XAU, CR_MASK_XAU) == 60, "gold 17:00-17:59 New York masked", S(BarsMasked(CR_XAU, CR_MASK_XAU)));
   check(BarsMasked(CR_XAU, CR_MASK_HALF) == 0, "gold is not masked on half days");
   check(BarsMasked(CR_XAU, CR_MASK_WEEKEND) == 1, "gold server Saturday masked");
   // gold: 390 bars of 12:00-18:29 New York, 3 bid-flat bars, 1 Saturday bar; 60 + 1 masked, the 3 flat bars kept
   check(BarsMasked(CR_XAU, CR_MASK_KEPT) == 390 - 60 + 3, "gold kept bars: the three bid-flat bars included",
         S(BarsMasked(CR_XAU, CR_MASK_KEPT)));
   for(int k = 1; k <= 3; k++)
     {
      datetime tf = ClkServerToUtc(last + 60 * k);
      check(BarsAt(CR_XAU, BarsIndex(CR_XAU, tf), x) && x.t == tf && x.bo == x.bh && x.bh == x.bl && x.bl == x.bc,
            "bid-flat gold bar fed as a kept bar", S(k));
     }
   check(BarsMasked(CR_BTC, CR_MASK_CRYPTO) == 2, "crypto Friday 23:56 server and Saturday masked", S(BarsMasked(CR_BTC, CR_MASK_CRYPTO)));
   check(BarsMasked(CR_BTC, CR_MASK_KEPT) == 1, "crypto Friday 23:54 server kept", S(BarsMasked(CR_BTC, CR_MASK_KEPT)));
   check(BarsMasked(CR_ETH, CR_MASK_KEPT) == 1, "ETH weekday bar kept");
   check(d.order_ok && d.contract_ok, "order and minute contract");
  }

// 12. compaction keeps absolute indexes: 400,000 fed bars of one symbol
static void world_compact()
  {
   w_begin("compact");
   g_rng = 5;
   RpSym &b = w_sym(CR_BTC);
   long c = 5400000;
   // crypto bars on every minute outside FP's crypto weekend (server Friday 23:55 to Monday 00:00): all kept
   for(long u = W_LOAD; (long)b.bars.size() < 410000; u += 60)
     {
      long srv = ClkUtcToServer(u);
      int dow = (int)(((srv / 86400) + 4) % 7), mn = (int)((srv % 86400) / 60);
      if(dow == 0 || dow == 6 || (dow == 5 && mn >= 23 * 60 + 55)) continue;
      long o = c + 1, cl = o + (long)(rnd() % 5) - 2;
      b.bars.push_back(w_bar(srv, o, std::max(o, cl) + 2, std::min(o, cl) - 2, cl, 300));
      c = cl;
     }
   w_sym(CR_ETH);
   rp_syms[CR_XAU].bars.clear();
   rp_syms[CR_IDX].bars.clear();
   ea_setup("", 2, 1);
   Drv d;
   d.keep_bars = false;
   drv_run(d, 0, LONG_MAX, 1);
   long n = BarsCount(CR_BTC);
   CrBar x;
   check(n == (long)b.bars.size() - 1, "every bar fed", S(n));
   check(!BarsAt(CR_BTC, 0, x), "the oldest bars were dropped by the compaction");
   check(BarsAt(CR_BTC, (int)n - 150000, x) && BarsAt(CR_BTC, (int)n - 1, x), "the last 150,000 fed bars are kept");
   check(BarsAt(CR_BTC, (int)n - 1, x) && BarsIndex(CR_BTC, x.t) == n - 1, "absolute BarsIndex after the compaction");
   check(d.order_ok && d.contract_ok, "order and minute contract");
  }

static int run_worlds()
  {
   world_clean();
   world_barrier();
   world_unsync();
   world_hole_stays();
   world_hole_fills();
   world_live_wait();
   world_live_gap();
   world_revise();
   world_stable();
   world_depth();
   world_mask();
   world_compact();
   JrnClose();
   printf("{\"worlds_checks\": %d, \"failed\": %d}\n", g_pass + g_fail, g_fail);
   return g_fail == 0 ? 0 : 1;
  }

// ------------------------------------------------------------------ math mode
// IN: int64 nseries; per series int64 L + L doubles; int64 nops; per op int64 series, code, n, minp
// OUT: per op, L doubles. Codes: 1 sum, 2 mean, 3 max, 4 min, 5 median, 6 Wilder, 7 ring Last(minp), 8 ring Get(minp),
//      9 CrMedian of the last n values, 10 max with min_periods, 11 min with min_periods, 12 sum Valid()
static int run_math(const char *in, const char *outp)
  {
   FILE *f = fopen(in, "rb");
   if(!f) return 2;
   int64_t ns = 0;
   if(fread(&ns, 8, 1, f) != 1) return 2;
   std::vector<std::vector<double>> ser((size_t)ns);
   for(auto &v : ser)
     {
      int64_t L = 0;
      if(fread(&L, 8, 1, f) != 1) return 2;
      v.resize((size_t)L);
      if(L && fread(v.data(), 8, (size_t)L, f) != (size_t)L) return 2;
     }
   int64_t nops = 0;
   if(fread(&nops, 8, 1, f) != 1) return 2;
   FILE *o = fopen(outp, "wb");
   for(int64_t k = 0; k < nops; k++)
     {
      int64_t q[4];
      if(fread(q, 8, 4, f) != 4) return 2;
      const std::vector<double> &x = ser[(size_t)q[0]];
      int code = (int)q[1], n = (int)q[2], minp = (int)q[3];
      std::vector<double> r(x.size());
      CrRollSum rs;
      CrRollMax mx;
      CrRollMin mn;
      CrRollMedian md;
      CrWilder w;
      CrRing ring;
      rs.Init(n, minp);
      if(code == 10) mx.InitMinPeriods(n, minp);
      else mx.Init(n);
      if(code == 11) mn.InitMinPeriods(n, minp);
      else mn.Init(n);
      md.Init(n, minp);
      w.Init(n);
      ring.Init(n);
      MqlArray<double> win;
      for(size_t i = 0; i < x.size(); i++)
        {
         double v = x[i], y = 0;
         switch(code)
           {
            case 1: rs.Push(v); y = rs.Sum(); break;
            case 2: rs.Push(v); y = rs.Mean(); break;
            case 3: case 10: mx.Push(v); y = mx.Value(); break;
            case 4: case 11: mn.Push(v); y = mn.Value(); break;
            case 5: md.Push(v); y = md.Value(); break;
            case 6: y = w.Push(v); break;
            case 7: ring.Push(v); y = ring.Last(minp); break;
            case 8: ring.Push(v); y = ring.Get(minp); break;
            case 9:
              {
               size_t a = i + 1 >= (size_t)n ? i + 1 - (size_t)n : 0;
               win.v.assign(x.begin() + (long)a, x.begin() + (long)i + 1);
               y = CrMedian(win, (int)win.v.size());
               break;
              }
            case 12: rs.Push(v); y = rs.Valid(); break;
            default: y = 0;
           }
         r[i] = y;
        }
      fwrite(r.data(), 8, r.size(), o);
     }
   fclose(o);
   fclose(f);
   return 0;
  }

// ------------------------------------------------------------------ store mode
static int run_store(int argc, char **argv)
  {
   string dir = argv[2];
   string closures;
   int timer_calls = 1;
   std::vector<std::pair<int, string>> files;
   for(int i = 3; i < argc; i++)
     {
      string a = argv[i];
      if(a == "--closures" && i + 1 < argc) closures = argv[++i];
      else if(a == "--timer-calls" && i + 1 < argc) timer_calls = atoi(argv[++i]);
      else
        {
         size_t q = a.find('=');
         int id = -1;
         for(int s = 0; s < CR_NSYM; s++)
            if(a.substr(0, q) == W_NAME[s]) id = s;
         if(id < 0) { fprintf(stderr, "unknown symbol %s\n", a.c_str()); return 2; }
         files.push_back({id, a.substr(q + 1)});
        }
     }
   g_world = "store";
   w_reset(dir);
   for(int s = 0; s < CR_NSYM; s++) w_sym(s);
   for(auto &p : files)
      if(!rp_load_bars(rp_syms[p.first], p.second.c_str())) { fprintf(stderr, "cannot read %s\n", p.second.c_str()); return 2; }
   long from = LONG_MAX, last = 0;
   for(const RpSym &s : rp_syms)
      if(!s.bars.empty())
        {
         from = std::min(from, (long)s.bars.front().time);
         last = std::max(last, (long)s.bars.back().time);
        }
   rp_now = from;
   ea_setup(closures, 120, 60);
   Drv d;
   d.keep_bars = false;
   static char buf[1 << 22];
   setvbuf(stdout, buf, _IOFBF, sizeof buf);
   d.out = stdout;
   d.aggf = fopen((dir + "/agg.bin").c_str(), "wb");
   d.costf = fopen((dir + "/costs.bin").c_str(), "wb");
   auto t0 = std::chrono::steady_clock::now();
   drv_run(d, from, LONG_MAX, timer_calls);
   double sec = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
   fflush(stdout);
   fclose(d.aggf);
   fclose(d.costf);
   JrnClose();
   FILE *j = fopen((dir + "/summary.json").c_str(), "w");
   fprintf(j, "{\"loads\": %d, \"latebars\": %d, \"waits\": %d, \"retries\": %d, \"fed\": %ld, \"order_ok\": %d, \"contract_ok\": %d, "
              "\"first_bad\": %ld, \"last_event_srv\": %ld, \"last_event_utc\": %ld, \"agg\": %ld, \"costs\": %ld, \"sec\": %.3f, "
              "\"comm_pts\": %d, \"h_xau\": %.17g, \"gap_live\": %ld, \"late_asked\": %ld, \"masked\": {",
           d.loads, d.latebars, d.waits, d.retries, d.fed_total, d.order_ok ? 1 : 0, d.contract_ok ? 1 : 0, d.first_bad, last,
           (long)ClkServerToUtc(last), d.n_agg, d.n_cost, sec, (int)CR_XAU_COMM_PTS, g_sym[CR_XAU].h, g_bars_gap_live, g_bars_late_n);
   for(int s = 0; s < CR_NSYM; s++)
     {
      fprintf(j, "%s\"%s\": {", s ? ", " : "", g_sym[s].base.c_str());
      for(int k = 0; k < CR_MASK_N; k++) fprintf(j, "%s\"%s\": %ld", k ? ", " : "", CR_MASK_NAME[k].c_str(), BarsMasked(s, k));
      fprintf(j, ", \"ready\": %d, \"count\": %d}", BarsReady(s) ? 1 : 0, BarsCount(s));
     }
   fprintf(j, "}}\n");
   fclose(j);
   return 0;
  }

int main(int argc, char **argv)
  {
   if(argc >= 2 && strcmp(argv[1], "math") == 0 && argc == 4) return run_math(argv[2], argv[3]);
   if(argc >= 3 && strcmp(argv[1], "store") == 0) return run_store(argc, argv);
   return run_worlds();
  }
