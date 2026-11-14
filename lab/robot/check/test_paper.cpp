// T3 paper: CR_Paper (SPEC 2.5, step C) fed minute by minute as CR_Main drives it; no argument = the unit worlds
// build: entry=src/CR_Paper.mqh sanitize
//
// Modes (check/test_paper.py drives the second one):
//   test_paper                 the unit worlds below on synthetic bars; exit 0 when every check holds
//   test_paper replay DIR [K]  DIR/sleeves.txt  one line per sleeve: "<symbol id>" (sleeve index = line number)
//                              DIR/bars.bin     kept bars, 80-byte records <int64 t, int32 sym, int32 s_raw, 8 doubles
//                                               bo bh bl bc ao ah al ac>, sorted by (t, sym)
//                              DIR/script.bin   rule outputs, 216-byte records of 27 eight-byte fields (see Row), sorted by
//                                               emission point then row order
//                              -> DIR/events.csv (every paper event, and SUBMITFAIL lines), DIR/open.csv (trades and
//                                 orders still open at the end), DIR/summary.json
//                              K > 1: PapOnBarrier only on minutes M with (M / 60) % K == 0 (PapOnBar's own barrier does
//                              the rest); outputs events_sparse.csv, open_sparse.csv, summary_sparse.json
// The minute contract of CR_Main (MainMinute, MainFeedBar, MainEmit): for every whole minute M, every bar starting before M
// in (t, sym) order: the OnBar outputs of that bar (orders, then exits), PapOnBar for each sleeve trading the symbol, the
// events drained; then the OnMinute(M) outputs; PapOnBarrier(M); the events drained.
#include "mock_replay.h"
#include "ea.cpp"
#include <algorithm>
#include <cinttypes>
#include <string>
#include <vector>

// ------------------------------------------------------------------ setup (the symbol rows of CR_Registry RegInit)
static void t_sym(int s, const char *base, double mkt_bps, double stop_bps)
  {
   g_sym[s].base = base;
   g_sym[s].digits = 2;
   g_sym[s].point = 0.01;
   g_sym[s].slip_mkt = mkt_bps * 1e-4;
   g_sym[s].slip_stop = stop_bps * 1e-4;
   g_sym[s].ok = true;
  }

static void t_setup(const std::vector<int> &sleeve_sym)
  {
   g_cfg = CrConfig();
   g_cfg.harness = true;
   t_sym(CR_XAU, "XAUUSD", 0.3, 1.0);
   t_sym(CR_IDX, "US100", 0.2, 0.5);
   t_sym(CR_BTC, "BTCUSD", 0.5, 1.5);
   t_sym(CR_ETH, "ETHUSD", 0.7, 2.0);
   g_nsl = (int)sleeve_sym.size();
   for(int i = 0; i < g_nsl; i++)
     {
      g_sl[i] = CrSleeveInfo();
      g_sl[i].id = i + 1;
      g_sl[i].sym = sleeve_sym[i];
      g_sl[i].sym2 = -1;
     }
   PapInit();
  }

// ------------------------------------------------------------------ the replay mode
struct Bar80 { int64_t t; int32_t sym, s_raw; double bo, bh, bl, bc, ao, ah, al, ac; };
struct Row
  {
   int64_t kind, emit_kind, emit_t, sleeve;          // kind 0 order, 1 exit; emit_kind 0 OnMinute(emit_t), 1 OnBar(bar emit_t)
   int64_t oid, side, etype;
   double  level, level2;
   int64_t t_from, t_to, after_exit_of, expiry_excl;
   double  stop, stop_dist, trail, be, target, target_dist;
   int64_t x_sched, x_gap, xh;
   double  xh_r;
   int64_t refuse, void_le, dec, group;
  };
static_assert(sizeof(Bar80) == 80, "bar record");
static_assert(sizeof(Row) == 216, "script record");

static FILE *g_evf = nullptr;
static long g_ev_count[CR_EV_N];
static long g_submit_fail = 0;

static void drain()
  {
   int n = PapEvents();
   for(int k = 0; k < n; k++)
     {
      CrPEvent e;
      if(!PapEvent(k, e)) continue;
      if(e.ev >= 0 && e.ev < CR_EV_N) g_ev_count[e.ev]++;
      if(g_evf)
         fprintf(g_evf, "%s,%d,%" PRId64 ",%d,%" PRId64 ",%" PRId64 ",%.17g,%.17g,%.17g,%d,%" PRId64 ",%d,%.17g\n", CR_EV_NAME[e.ev].c_str(),
                 e.sleeve, (int64_t)e.oid, e.side, (int64_t)e.t, (int64_t)e.bar, e.px, e.stop, e.init_stop, e.reason, (int64_t)e.x,
                 e.s_raw, e.s_paper);
     }
   PapClearEvents();
  }

static CrOrder row_order(const Row &r)
  {
   CrOrder o;
   CrOrderClear(o);
   o.sleeve = (int)r.sleeve;
   o.oid = r.oid;
   o.side = (int)r.side;
   o.etype = (int)r.etype;
   o.level = r.level;
   o.level2 = r.level2;
   o.t_from = r.t_from;
   o.t_to = r.t_to;
   o.after_exit_of = r.after_exit_of;
   o.expiry_excl = r.expiry_excl;
   o.stop = r.stop;
   o.stop_dist = r.stop_dist;
   o.trail = r.trail;
   o.be = r.be;
   o.target = r.target;
   o.target_dist = r.target_dist;
   o.x_sched = r.x_sched;
   o.x_gap = r.x_gap != 0;
   o.xh = r.xh;
   o.xh_r = r.xh_r;
   o.refuse = (int)r.refuse;
   o.void_le = r.void_le != 0;
   o.dec = r.dec;
   o.grp = (int)r.group;
   return o;
  }

static void submit(const Row &r)
  {
   bool ok;
   if(r.kind == 0) ok = PapSubmit(row_order(r));
   else
     {
      CrExit e;
      ZeroMemory(e);
      e.sleeve = (int)r.sleeve;
      e.oid = r.oid;
      e.t_from = r.t_from;
      e.t_to = r.t_to;
      e.dec = r.dec;
      ok = PapSubmitExit(e);
     }
   if(!ok)
     {
      g_submit_fail++;
      if(g_evf) fprintf(g_evf, "SUBMITFAIL,%" PRId64 ",%" PRId64 ",%" PRId64 "\n", r.sleeve, r.oid, r.kind);
     }
  }

template <typename T> static bool read_all(const string &path, std::vector<T> &v)
  {
   FILE *f = fopen(path.c_str(), "rb");
   if(!f) return false;
   fseek(f, 0, SEEK_END);
   long n = ftell(f);
   fseek(f, 0, SEEK_SET);
   v.resize(n / sizeof(T));
   size_t got = v.empty() ? 0 : fread(v.data(), sizeof(T), v.size(), f);
   fclose(f);
   return got == v.size() && (size_t)n == v.size() * sizeof(T);
  }

static int replay(const string &dir, const int sparse)
  {
   const string sfx = sparse > 1 ? "_sparse" : "";
   std::vector<int> ssym;
   FILE *sf = fopen((dir + "/sleeves.txt").c_str(), "r");
   if(!sf) { fprintf(stderr, "no sleeves.txt\n"); return 2; }
   int s;
   while(fscanf(sf, "%d", &s) == 1) ssym.push_back(s);
   fclose(sf);
   if(ssym.empty() || (int)ssym.size() > CR_MAX_SL) { fprintf(stderr, "bad sleeves.txt\n"); return 2; }
   std::vector<Bar80> bars;
   std::vector<Row> rows;
   if(!read_all(dir + "/bars.bin", bars) || !read_all(dir + "/script.bin", rows)) { fprintf(stderr, "bad input files\n"); return 2; }
   t_setup(ssym);
   for(auto &c : g_ev_count) c = 0;
   g_evf = fopen((dir + "/events" + sfx + ".csv").c_str(), "w");
   std::vector<size_t> onbar, onmin;                  // row indices, each list in file order
   for(size_t i = 0; i < rows.size(); i++) (rows[i].emit_kind == 1 ? onbar : onmin).push_back(i);
   if(bars.empty()) { fprintf(stderr, "no bars\n"); return 2; }
   auto t0 = std::chrono::steady_clock::now();
   int64_t M0 = bars.front().t - bars.front().t % 60;
   int64_t M1 = bars.back().t + 60;
   if(!onmin.empty()) M0 = std::min(M0, rows[onmin.front()].emit_t);
   size_t bi = 0, ob = 0, om = 0;
   long minutes = 0, fed = 0, stray = 0;
   for(int64_t M = M0; M <= M1; M += 60)
     {
      while(bi < bars.size() && bars[bi].t < M)
        {
         const Bar80 &r = bars[bi];
         CrBar b;
         b.t = r.t;
         b.sym = r.sym;
         b.bo = r.bo; b.bh = r.bh; b.bl = r.bl; b.bc = r.bc;
         b.ao = r.ao; b.ah = r.ah; b.al = r.al; b.ac = r.ac;
         b.s_raw = r.s_raw;
         while(ob < onbar.size() && rows[onbar[ob]].emit_t < b.t) { stray++; ob++; }          // a bar that does not exist
         while(ob < onbar.size() && rows[onbar[ob]].emit_t == b.t)
           {
            const Row &w = rows[onbar[ob]];
            if(w.sleeve >= 0 && w.sleeve < g_nsl && g_sl[w.sleeve].sym != b.sym) break;        // another symbol's bar comes later
            submit(w);
            ob++;
           }
         for(int sl = 0; sl < g_nsl; sl++)
            if(g_sl[sl].sym == b.sym) PapOnBar(sl, b);
         drain();
         fed++;
         bi++;
        }
      while(om < onmin.size() && rows[onmin[om]].emit_t < M) { stray++; om++; }
      while(om < onmin.size() && rows[onmin[om]].emit_t == M) submit(rows[onmin[om++]]);
      if(sparse <= 1 || (M / 60) % sparse == 0) PapOnBarrier(M);
      drain();
      minutes++;
     }
   stray += (long)(onbar.size() - ob) + (long)(onmin.size() - om);
   double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
   fclose(g_evf);
   g_evf = nullptr;
   FILE *of = fopen((dir + "/open" + sfx + ".csv").c_str(), "w");
   fprintf(of, "what,sleeve,oid,side,fill_bar,fill_px,init_stop,stop,x,x_gap,x_pending\n");
   for(int sl = 0; sl < g_nsl; sl++)
     {
      CrTrade t;
      if(PapTrade(sl, t))
         fprintf(of, "trade,%d,%" PRId64 ",%d,%" PRId64 ",%.17g,%.17g,%.17g,%" PRId64 ",%d,%d\n", sl, (int64_t)t.oid, t.side,
                 (int64_t)t.fill_bar, t.fill_px, t.init_stop, t.stop, (int64_t)t.x_sched, t.x_gap ? 1 : 0, t.x_pending ? 1 : 0);
      CrOrder o;
      if(PapPending(sl, o)) fprintf(of, "order,%d,%" PRId64 ",%d,0,0,0,0,0,0,0\n", sl, (int64_t)o.oid, o.side);
     }
   fclose(of);
   FILE *jf = fopen((dir + "/summary" + sfx + ".json").c_str(), "w");
   fprintf(jf, "{\"bars\": %zu, \"fed\": %ld, \"minutes\": %ld, \"rows\": %zu, \"stray_rows\": %ld, \"submit_fail\": %ld, \"ms\": %.1f, \"events\": {",
           bars.size(), fed, minutes, rows.size(), stray, g_submit_fail, ms);
   bool first = true;
   for(int e = 0; e < CR_EV_N; e++)
      if(g_ev_count[e])
        {
         fprintf(jf, "%s\"%s\": %ld", first ? "" : ", ", CR_EV_NAME[e].c_str(), g_ev_count[e]);
         first = false;
        }
   fprintf(jf, "}}\n");
   fclose(jf);
   printf("replay: %zu bars, %ld minutes, %zu rows, %ld submit refusals, %.0f ms\n", bars.size(), minutes, rows.size(), g_submit_fail, ms);
   return 0;
  }

// ------------------------------------------------------------------ unit worlds
static int g_checks = 0, g_fails = 0;
static void check(bool ok, const char *what)
  {
   g_checks++;
   if(!ok)
     {
      g_fails++;
      printf("FAIL %s\n", what);
     }
  }
static bool eq(double a, double b) { return a == b; }

static std::vector<CrPEvent> g_got;
static void collect()
  {
   int n = PapEvents();
   for(int k = 0; k < n; k++)
     {
      CrPEvent e;
      if(PapEvent(k, e)) g_got.push_back(e);
     }
   PapClearEvents();
  }
static int count_ev(int ev, long oid = -1)
  {
   int n = 0;
   for(auto &e : g_got)
      if(e.ev == ev && (oid < 0 || e.oid == oid)) n++;
   return n;
  }
static const CrPEvent *last_ev(int ev, long oid)
  {
   const CrPEvent *p = nullptr;
   for(auto &e : g_got)
      if(e.ev == ev && e.oid == oid) p = &e;
   return p;
  }

// a synthetic world: bars of one symbol (sym 0, XAU slippage) at given minutes; flat prices unless set
struct World
  {
   std::vector<CrBar> bars;
   const int64_t T0 = 1600000020 - 1600000020 % 60;   // a whole minute (2020-09-13)
   CrBar &add(int minute, double o, double h, double l, double c, double spread = 0.1)
     {
      CrBar b;
      ZeroMemory(b);
      b.t = T0 + 60LL * minute;
      b.sym = 0;
      b.bo = o; b.bh = h; b.bl = l; b.bc = c;
      b.ao = o + spread; b.ah = h + spread; b.al = l + spread; b.ac = c + spread;
      b.s_raw = (int)(spread * 100 + 0.5);
      bars.push_back(b);
      return bars.back();
     }
   void flat(int from, int to, double p) { for(int m = from; m < to; m++) add(m, p, p + 0.05, p - 0.05, p); }
   int64_t t(int minute) const { return T0 + 60LL * minute; }
  };

// outputs a world emits: at OnMinute(minute) or OnBar(bar at minute)
struct Out { int minute; bool onbar; bool is_exit; CrOrder o; CrExit e; };

// barrier_every: 1 = PapOnBarrier every minute (the driver's contract); 0 = never (PapOnBar's own barrier does the work)
static void run_world(const World &w, std::vector<Out> outs, int until_minute, int nsl = 1, int barrier_every = 1)
  {
   t_setup(std::vector<int>(nsl, 0));
   g_got.clear();
   size_t bi = 0;
   for(int m = -1; m <= until_minute; m++)
     {
      int64_t M = w.T0 + 60LL * m;
      while(bi < w.bars.size() && w.bars[bi].t < M)
        {
         const CrBar &b = w.bars[bi];
         for(auto &u : outs)
            if(u.onbar && w.t(u.minute) == b.t && !u.is_exit) { if(!PapSubmit(u.o)) g_got.push_back(CrPEvent{-1, u.o.sleeve, u.o.oid}); }
         for(auto &u : outs)
            if(u.onbar && w.t(u.minute) == b.t && u.is_exit) PapSubmitExit(u.e);
         for(int sl = 0; sl < g_nsl; sl++) PapOnBar(sl, b);
         collect();
         bi++;
        }
      for(auto &u : outs)
         if(!u.onbar && w.t(u.minute) == M && !u.is_exit) { if(!PapSubmit(u.o)) g_got.push_back(CrPEvent{-1, u.o.sleeve, u.o.oid}); }
      for(auto &u : outs)
         if(!u.onbar && w.t(u.minute) == M && u.is_exit) PapSubmitExit(u.e);
      if(barrier_every > 0 && (m + 1) % barrier_every == 0) PapOnBarrier(M);
      collect();
     }
  }

// the trade-level events of the last run (every event but HOLD's barrier time), to compare two drivers
static std::vector<std::string> trade_lines()
  {
   std::vector<std::string> v;
   for(auto &e : g_got)
     {
      char buf[256];
      snprintf(buf, sizeof(buf), "%d,%ld,%d,%ld,%ld,%.17g,%.17g,%d,%ld", e.ev, (long)e.oid, e.side, e.ev == CR_EV_HOLD ? 0L : (long)e.t,
               (long)e.bar, e.px, e.stop, e.reason, (long)e.x);
      v.push_back(buf);
     }
   return v;
  }

static CrOrder mk(long oid, int side, int etype, int64_t from, int64_t to, int sl = 0)
  {
   CrOrder o;
   CrOrderClear(o);
   o.sleeve = sl;
   o.oid = oid;
   o.side = side;
   o.etype = etype;
   o.t_from = from;
   o.t_to = to;
   o.stop_dist = 100.0;
   o.dec = from;
   return o;
  }
static Out at_min(int minute, const CrOrder &o) { Out u; u.minute = minute; u.onbar = false; u.is_exit = false; u.o = o; ZeroMemory(u.e); return u; }
static Out at_bar(int minute, const CrOrder &o) { Out u = at_min(minute, o); u.onbar = true; return u; }
static Out ex_min(int minute, long oid, int64_t from, int64_t to)
  {
   Out u;
   u.minute = minute; u.onbar = false; u.is_exit = true;
   CrOrderClear(u.o);
   ZeroMemory(u.e);
   u.e.sleeve = 0; u.e.oid = oid; u.e.t_from = from; u.e.t_to = to;
   return u;
  }

static void worlds()
  {
   const double SM = 0.3e-4, SS = 1.0e-4;            // XAU market and stop slippage (fp_costs.json)
   // W1: market long, stop hit on a later bar at the worse of stop and open; stamps
   {
      World w;
      w.flat(0, 10, 100.0);
      w.add(10, 100.0, 100.5, 99.9, 100.2);           // fill bar
      w.add(11, 100.2, 100.3, 100.1, 100.2);
      w.add(12, 98.0, 98.2, 97.5, 98.0);              // opens below the stop
      w.flat(13, 20, 98.0);
      CrOrder o = mk(1, 1, CR_ET_MARKET, w.t(10), w.t(10));
      o.stop_dist = 1.5;
      run_world(w, {at_min(10, o)}, 25);
      const CrPEvent *f = last_ev(CR_EV_PFILL, 1), *x = last_ev(CR_EV_PEXIT, 1);
      double fp = 100.1 * (1 + SM);
      check(f && f->t == w.t(10) && eq(f->px, fp) && eq(f->init_stop, fp - 1.5), "W1 fill at ask open x (1 + slip_mkt), stop = fill - dist");
      check(x && x->t == w.t(12) + 60 && x->reason == CR_R_STOP && eq(x->px, MathMin(fp - 1.5, 98.0) * (1 - SS)), "W1 stop at the open (gap), + 60 s");
      CrTrade t;
      check(!PapTrade(0, t) && PapLastExitBar(0) == w.t(12), "W1 flat after, last exit bar");
   }
   // W2: short time exit at the first bar at or after x (no gap rule), stamp = bar start; never on the fill bar
   {
      World w;
      w.flat(0, 30, 100.0);
      w.bars.erase(w.bars.begin() + 15, w.bars.begin() + 20);   // a hole 15-19
      CrOrder o = mk(2, -1, CR_ET_MARKET, w.t(10), w.t(10));
      o.x_sched = w.t(16);
      run_world(w, {at_min(10, o)}, 35);
      const CrPEvent *x = last_ev(CR_EV_PEXIT, 2);
      check(x && x->t == w.t(20) && x->reason == CR_R_TIME && eq(x->px, 100.1 * (1 + SM)), "W2 time exit at the first bar at or after x, ask open x (1 + slip_mkt)");
      CrOrder o2 = mk(3, -1, CR_ET_MARKET, w.t(10), w.t(10));
      o2.x_sched = w.t(5);                                       // x before the fill: exit at the next bar
      run_world(w, {at_min(10, o2)}, 35);
      x = last_ev(CR_EV_PEXIT, 3);
      check(x && x->t == w.t(11) && x->reason == CR_R_TIME, "W2 x at or before the fill bar: exit at the next bar (sim.py:137)");
   }
   // W3: the gap rule. x = minute 40 inside a hole 31-99: the last kept bar before x is 30 -> PREVISE at 30's open;
   //     a stop exit booked on bar 30 is replaced by it
   {
      World w;
      w.flat(0, 30, 100.0);
      w.add(30, 100.0, 100.05, 95.0, 95.0);            // the stop is hit on bar 30
      w.flat(100, 130, 95.0);
      CrOrder o = mk(4, 1, CR_ET_MARKET, w.t(10), w.t(10));
      o.stop_dist = 2.0;
      o.x_sched = w.t(40);
      o.x_gap = true;
      run_world(w, {at_min(10, o)}, 140);
      const CrPEvent *x = last_ev(CR_EV_PEXIT, 4), *r = last_ev(CR_EV_PREVISE, 4);
      check(x && x->reason == CR_R_STOP && x->t == w.t(30) + 60, "W3 the stop exit is booked on bar 30 first");
      check(r && r->t == w.t(30) && r->reason == CR_R_TIME && eq(r->px, 100.0 * (1 - SM)), "W3 PREVISE: the time exit at the open of the last bar before x");
      bool at_barrier = false;
      for(size_t k = 0; k < g_got.size(); k++)
         if(g_got[k].ev == CR_EV_PREVISE && g_got[k].oid == 4) at_barrier = true;
      check(at_barrier && PapLastExitBar(0) == w.t(30), "W3 exit bar 30 kept");
      // the same with a bar at minute 70 (inside x + 30 min): the stop exit stands
      World w2;
      w2.flat(0, 30, 100.0);
      w2.add(30, 100.0, 100.05, 95.0, 95.0);
      w2.flat(70, 130, 95.0);
      run_world(w2, {at_min(10, o)}, 140);
      check(count_ev(CR_EV_PREVISE, 4) == 0 && last_ev(CR_EV_PEXIT, 4) && last_ev(CR_EV_PEXIT, 4)->reason == CR_R_STOP,
            "W3 a kept bar in [x, x + 30 min]: no revision");
   }
   // W4: the gap rule lands on the fill bar: the exit waits for the first kept bar after x (no restore)
   {
      World w;
      w.flat(0, 11, 100.0);
      w.flat(200, 230, 100.0);
      CrOrder o = mk(5, 1, CR_ET_MARKET, w.t(10), w.t(10));
      o.x_sched = w.t(40);
      o.x_gap = true;
      run_world(w, {at_min(10, o)}, 240);
      const CrPEvent *x = last_ev(CR_EV_PEXIT, 5);
      check(count_ev(CR_EV_PREVISE, 5) == 0 && x && x->t == w.t(200) && x->reason == CR_R_TIME, "W4 L = fill bar: exit at the next kept bar");
      // void_le: the same order never existed (PVOID), and an order activating later is free
      CrOrder v = o;
      v.oid = 6;
      v.void_le = true;
      CrOrder n2 = mk(7, -1, CR_ET_MARKET, w.t(200), w.t(200));
      run_world(w, {at_min(10, v), at_min(200, n2)}, 240);
      check(count_ev(CR_EV_PVOID, 6) == 1 && count_ev(CR_EV_PEXIT, 6) == 0 && count_ev(CR_EV_PFILL, 7) == 1, "W4 void_le late: PVOID, sleeve free");
      check(PapLastExitBar(0) == 0, "W4 PVOID leaves no exit bar");
      // void_le at activation (x at or before the activation bar)
      CrOrder v2 = mk(8, 1, CR_ET_MARKET, w.t(10), w.t(10));
      v2.void_le = true;
      v2.x_gap = true;
      v2.x_sched = w.t(10);
      run_world(w, {at_min(10, v2)}, 30);
      check(count_ev(CR_EV_PVOID, 8) == 1 && count_ev(CR_EV_PFILL, 8) == 0, "W4 void_le at activation");
   }
   // W5: OCO both levels touched in one bar: bc >= bo -> short, bc < bo -> long; fill as a stop entry of that side
   {
      World w;
      w.flat(0, 10, 100.0);
      w.add(10, 100.0, 101.0, 99.0, 100.5);            // bc >= bo -> short
      w.flat(11, 20, 100.0);
      CrOrder o = mk(9, 0, CR_ET_OCO, w.t(10), w.t(10));
      o.level = 100.6;
      o.level2 = 99.5;
      o.expiry_excl = w.t(15);
      o.stop_dist = 5.0;
      run_world(w, {at_min(10, o)}, 25);
      const CrPEvent *f = last_ev(CR_EV_PFILL, 9);
      check(f && f->side == -1 && eq(f->px, MathMin(99.5, 100.0) * (1 - SS)), "W5 OCO both touched, bc >= bo: short at min(level2, bo) x (1 - slip)");
      World w2;
      w2.flat(0, 10, 100.0);
      w2.add(10, 100.0, 101.0, 99.0, 99.8);            // bc < bo -> long
      w2.flat(11, 20, 100.0);
      run_world(w2, {at_min(10, o)}, 25);
      f = last_ev(CR_EV_PFILL, 9);
      check(f && f->side == 1 && eq(f->px, MathMax(100.6, 100.1) * (1 + SS)), "W5 OCO both touched, bc < bo: long at max(level, ao) x (1 + slip)");
   }
   // W6: one position: skipped while open and on the exit bar; a refused order leaves no trace (the next one is taken)
   {
      World w;
      w.flat(0, 60, 100.0);
      CrOrder a = mk(10, 1, CR_ET_MARKET, w.t(10), w.t(10));
      a.x_sched = w.t(20);
      CrOrder b = mk(11, 1, CR_ET_MARKET, w.t(15), w.t(15));          // while a is open
      CrOrder c = mk(12, 1, CR_ET_MARKET, w.t(20), w.t(20));          // on a's exit bar
      CrOrder d = mk(13, 1, CR_ET_MARKET, w.t(21), w.t(21));          // the bar after: taken
      d.x_sched = w.t(25);
      run_world(w, {at_min(10, a), at_min(15, b), at_min(20, c), at_min(21, d)}, 40);
      check(count_ev(CR_EV_PFILL, 11) == 0 && count_ev(CR_EV_PFILL, 12) == 0 && count_ev(CR_EV_PFILL, 13) == 1, "W6 skip while open and on the exit bar");
      CrOrder r = mk(14, 1, CR_ET_MARKET, w.t(30), w.t(30));
      r.stop_dist = 0.2;                                               // < 3 x spread 0.1
      r.refuse = CR_REF_PAYOFF;
      CrOrder s = mk(15, 1, CR_ET_MARKET, w.t(30), w.t(30));          // same bar, after it
      run_world(w, {at_min(30, r), at_min(30, s)}, 40);
      check(count_ev(CR_EV_PREFUSE, 14) == 1 && count_ev(CR_EV_PFILL, 14) == 0 && count_ev(CR_EV_PFILL, 15) == 1, "W6 refuse 1: no trace, the next order is taken");
      CrOrder r2 = mk(16, 1, CR_ET_MARKET, w.t(30), w.t(30));
      r2.stop = 100.5;                                                 // wrong side
      r2.refuse = CR_REF_SB;
      run_world(w, {at_min(30, r2)}, 40);
      check(count_ev(CR_EV_PREFUSE, 16) == 1 && count_ev(CR_EV_PEXIT, 16) == 0, "W6 refuse 2: a stop on the wrong side is refused");
      CrOrder g = r2;
      g.oid = 17;
      g.refuse = CR_REF_NONE;
      run_world(w, {at_min(30, g)}, 40);
      const CrPEvent *x = last_ev(CR_EV_PEXIT, 17);
      check(x && x->reason == CR_R_GAP && x->t == w.t(30) + 60 && eq(x->px, 100.0 * (1 - SS)), "W6 wrong-side stop without refusal: 'gap' on the fill bar");
   }
   // W7: two pending entries at once -> PapSubmit false; two market orders may wait together
   {
      World w;
      w.flat(0, 60, 100.0);
      CrOrder a = mk(20, 1, CR_ET_STOP, w.t(10), w.t(10));
      a.level = 200.0;
      a.expiry_excl = w.t(30);
      CrOrder b = mk(21, 1, CR_ET_MARKET, w.t(12), w.t(12));
      CrOrder c = mk(22, 1, CR_ET_MARKET, w.t(10), w.t(11));
      CrOrder d = mk(23, -1, CR_ET_MARKET, w.t(11), w.t(12));
      run_world(w, {at_min(10, a), at_min(10, b)}, 40);
      bool refused = false;
      for(auto &e : g_got) if(e.ev == -1 && e.oid == 21) refused = true;
      check(refused, "W7 an order overlapping a waiting stop entry is refused");
      run_world(w, {at_min(10, c), at_min(10, d)}, 40);
      check(count_ev(CR_EV_PFILL, 22) == 1 && count_ev(CR_EV_PFILL, 23) == 0, "W7 two market orders: the first activation wins");
   }
   // W8: trail and break-even: PSTOP after the bar, 'trail' reason
   {
      World w;
      w.flat(0, 10, 100.0);
      w.add(10, 100.0, 100.2, 99.9, 100.1);
      w.add(11, 100.1, 103.0, 100.0, 102.9);           // best 103.0 -> stop 103 - 1 = 102
      w.add(12, 102.9, 102.95, 101.5, 101.6);          // hits 102
      w.flat(13, 20, 101.6);
      CrOrder o = mk(30, 1, CR_ET_MARKET, w.t(10), w.t(10));
      o.stop_dist = 2.0;
      o.trail = 1.0;
      run_world(w, {at_min(10, o)}, 25);
      const CrPEvent *p = last_ev(CR_EV_PSTOP, 30), *x = last_ev(CR_EV_PEXIT, 30);
      check(p && eq(p->stop, 103.0 - 1.0) && p->t == w.t(11) + 60, "W8 PSTOP after the bar's close");
      check(x && x->reason == CR_R_TRAIL && eq(x->px, MathMin(102.0, 102.9) * (1 - SS)), "W8 trail exit");
   }
   // W9: hold extension. x = 30 (gap rule), xh = 60. Ahead at bar 29 -> HOLD at the barrier 30; bar 31 confirms -> the
   //     trade runs to 60. With a hole 30-99 the re-test reads bar 28 (not ahead) -> HOLD withdrawn, PREVISE at 29.
   {
      World w;
      w.flat(0, 28, 100.0);
      w.add(28, 100.0, 100.1, 99.9, 100.0);            // not ahead at 28
      w.add(29, 100.0, 105.0, 100.0, 104.0);           // ahead at 29 (bid close 104 - fill 100.1003 >= 2)
      w.flat(30, 100, 104.0);
      CrOrder o = mk(40, 1, CR_ET_MARKET, w.t(10), w.t(10));
      o.stop_dist = 2.0;
      o.x_sched = w.t(30);
      o.x_gap = true;
      o.xh = w.t(60);
      o.xh_r = 1.0;
      run_world(w, {at_min(10, o)}, 120);
      const CrPEvent *h = last_ev(CR_EV_HOLD, 40), *x = last_ev(CR_EV_PEXIT, 40);
      check(h && h->x == w.t(60) && h->t == w.t(30) && eq(h->px, 104.0), "W9 HOLD at the first barrier at or after x");
      check(x && x->t == w.t(60) && x->reason == CR_R_TIME, "W9 held to xh");
      World w2 = w;
      w2.bars.erase(std::remove_if(w2.bars.begin(), w2.bars.end(), [&](const CrBar &b) { return b.t >= w.t(30) && b.t < w.t(100); }), w2.bars.end());
      run_world(w2, {at_min(10, o)}, 130);
      int holds = count_ev(CR_EV_HOLD, 40);
      const CrPEvent *r = last_ev(CR_EV_PREVISE, 40);
      h = last_ev(CR_EV_HOLD, 40);
      check(holds == 2 && h && h->x == w.t(30) && eq(h->px, 0.0), "W9 gap at x: the re-test on the bar before L withdraws the hold");
      check(r && r->t == w.t(29) && r->reason == CR_R_TIME, "W9 then the time exit at L's open (PREVISE)");
      // the opposite: not ahead at 29, ahead at 28 -> no HOLD at the barrier, HOLD at the revision, and it then exits at
      // L again once the barrier passes xh + 30 min with no bar (exit_index(xh) = L)
      World w3;
      w3.flat(0, 28, 100.0);
      w3.add(28, 100.0, 105.0, 100.0, 104.0);
      w3.add(29, 104.0, 104.1, 100.0, 100.0);
      w3.flat(200, 230, 100.0);
      run_world(w3, {at_min(10, o)}, 240);
      h = last_ev(CR_EV_HOLD, 40);
      r = last_ev(CR_EV_PREVISE, 40);
      check(count_ev(CR_EV_HOLD, 40) == 1 && h && h->x == w.t(60) && h->t == w.t(30) + 31 * 60, "W9 re-test grants the hold at the revision");
      check(r && r->t == w.t(29) && r->x == w.t(60), "W9 the extended exit falls in the same hole: L again");
   }
   // W10: a rule exit and an order after it (N30's reversal): the exit at the first bar of its window, the new order at
   //      the next kept bar; a rule exit whose window has no bar is void, and so is its after_exit_of order
   {
      World w;
      w.flat(0, 40, 100.0);
      w.bars.erase(w.bars.begin() + 30, w.bars.begin() + 36);   // no bar 30-35
      CrOrder a = mk(50, 1, CR_ET_MARKET, w.t(5), w.t(5));
      a.x_sched = w.t(39);
      CrOrder b = mk(51, -1, CR_ET_MARKET, w.t(20), w.t(25));
      b.after_exit_of = 50;
      run_world(w, {at_min(5, a), at_min(20, b), ex_min(20, 50, w.t(20), w.t(25))}, 45);
      const CrPEvent *x = last_ev(CR_EV_PEXIT, 50), *f = last_ev(CR_EV_PFILL, 51);
      check(x && x->t == w.t(20) && x->reason == CR_R_TIME, "W10 the rule exit: time exit at the first bar of its window");
      check(f && f->t == w.t(21), "W10 after_exit_of: the next kept bar");
      CrOrder c = mk(52, -1, CR_ET_MARKET, w.t(30), w.t(39));
      c.after_exit_of = 50;
      run_world(w, {at_min(5, a), at_min(30, c), ex_min(30, 50, w.t(30), w.t(35))}, 45);
      check(count_ev(CR_EV_PFILL, 52) == 0 && last_ev(CR_EV_PEXIT, 50) && last_ev(CR_EV_PEXIT, 50)->t == w.t(39), "W10 a void rule exit voids its order");
   }
   // W11: an order emitted from OnBar(b) activates on b (ORX: window = expiry = that bar)
   {
      World w;
      w.flat(0, 10, 100.0);
      w.add(10, 100.0, 101.0, 99.9, 100.8);
      w.flat(11, 20, 100.8);
      CrOrder o = mk(60, 1, CR_ET_STOP, w.t(10), w.t(10));
      o.level = 100.5;
      o.expiry_excl = w.t(11);
      o.stop = 99.0;
      run_world(w, {at_bar(10, o)}, 25);
      const CrPEvent *f = last_ev(CR_EV_PFILL, 60);
      check(f && f->t == w.t(10) && eq(f->px, MathMax(100.5, 100.1) * (1 + SS)), "W11 OnBar order fills on its own bar");
      CrTrade t;
      check(PapTrade(0, t) && t.oid == 60 && t.fill_bar == w.t(10) && !t.x_pending, "W11 PapTrade");
   }
   // W12: PapTrade shows a pending gap exit; PapPending shows a waiting order; PapReset clears everything
   {
      World w;
      w.flat(0, 31, 100.0);
      w.flat(100, 110, 100.0);
      CrOrder o = mk(70, 1, CR_ET_MARKET, w.t(10), w.t(10));
      o.x_sched = w.t(40);
      o.x_gap = true;
      run_world(w, {at_min(10, o)}, 50);                // barrier 50: past x, the question still open (no bar 31-99)
      CrTrade t;
      check(PapTrade(0, t) && t.x_pending && t.x_sched == w.t(40), "W12 a pending gap exit counts as open");
      CrOrder p = mk(71, 1, CR_ET_LIMIT, w.t(60), w.t(60));
      p.level = 1.0;
      p.expiry_excl = w.t(200);
      check(PapSubmit(p), "W12 a waiting order is accepted while a trade is open");
      CrOrder q;
      check(PapPending(0, q) && q.oid == 71, "W12 PapPending");
      PapReset();
      check(!PapTrade(0, t) && !PapPending(0, q) && PapEvents() == 0 && PapLastExitBar(0) == 0, "W12 PapReset");
   }
   // W13: the hold test passes but xh <= x0: HOLD with x = x0 (variants.H: max(ext, exit_i)), the exit stays at x0's bar
   {
      World w;
      w.flat(0, 29, 100.0);
      w.add(29, 100.0, 105.0, 100.0, 104.0);
      w.flat(30, 60, 104.0);
      CrOrder o = mk(80, 1, CR_ET_MARKET, w.t(10), w.t(10));
      o.stop_dist = 2.0;
      o.x_sched = w.t(30);
      o.x_gap = true;
      o.xh = w.t(20);
      o.xh_r = 1.0;
      run_world(w, {at_min(10, o)}, 70);
      const CrPEvent *h = last_ev(CR_EV_HOLD, 80), *x = last_ev(CR_EV_PEXIT, 80);
      check(count_ev(CR_EV_HOLD, 80) == 1 && h && h->x == w.t(30) && eq(h->px, 104.0), "W13 HOLD on a pass even when xh <= x0 (x stays x0)");
      check(x && x->t == w.t(30) && x->reason == CR_R_TIME && eq(x->px, 104.0 * (1 - SM)), "W13 time exit at x0's bar");
   }
   // W14: a market order whose window overlaps a void_le order's is refused, in either order (a void decided after the
   //      activation bar would have freed that bar for the other order); a later window is accepted
   {
      World w;
      CrOrder a = mk(81, 1, CR_ET_MARKET, w.t(10), w.t(15));
      a.void_le = true;
      a.x_gap = true;
      a.x_sched = w.t(40);
      CrOrder b = mk(82, -1, CR_ET_MARKET, w.t(12), w.t(14));
      CrOrder c = mk(83, -1, CR_ET_MARKET, w.t(20), w.t(25));
      t_setup({0});
      bool ok1 = PapSubmit(a), ok2 = PapSubmit(b), ok3 = PapSubmit(c);
      check(ok1 && !ok2 && ok3, "W14 overlap with a void_le order refused; a later window accepted");
      t_setup({0});
      ok1 = PapSubmit(b);
      ok2 = PapSubmit(a);
      check(ok1 && !ok2, "W14 refused in the other order too");
   }
   // W15: a driver that never calls PapOnBarrier: PapOnBar's own barrier gives the same trades, revisions, voids and holds
   {
      std::vector<std::pair<World, CrOrder>> cases;
      World a;
      a.flat(0, 30, 100.0);
      a.add(30, 100.0, 100.05, 95.0, 95.0);
      a.flat(100, 130, 95.0);
      CrOrder oa = mk(84, 1, CR_ET_MARKET, a.t(10), a.t(10));
      oa.stop_dist = 2.0;
      oa.x_sched = a.t(40);
      oa.x_gap = true;
      cases.push_back({a, oa});                                  // stop on L, then PREVISE
      World b;
      b.flat(0, 28, 100.0);
      b.add(28, 100.0, 100.1, 99.9, 100.0);
      b.add(29, 100.0, 105.0, 100.0, 104.0);
      b.flat(100, 130, 104.0);
      CrOrder ob = mk(85, 1, CR_ET_MARKET, b.t(10), b.t(10));
      ob.stop_dist = 2.0;
      ob.x_sched = b.t(30);
      ob.x_gap = true;
      ob.xh = b.t(60);
      ob.xh_r = 1.0;
      cases.push_back({b, ob});                                  // HOLD granted on L, withdrawn by the revision, PREVISE
      World c = b;
      c.bars.erase(std::remove_if(c.bars.begin(), c.bars.end(), [&](const CrBar &x) { return x.t >= b.t(100); }), c.bars.end());
      c.flat(30, 100, 104.0);
      cases.push_back({c, ob});                                  // HOLD confirmed by bar 30, held to 60
      World d;
      d.flat(0, 11, 100.0);
      d.flat(100, 120, 100.0);
      CrOrder od = mk(86, 1, CR_ET_MARKET, d.t(10), d.t(10));
      od.void_le = true;
      od.x_gap = true;
      od.x_sched = d.t(40);
      cases.push_back({d, od});                                  // late PVOID of a filled order
      CrOrder oe = mk(87, 1, CR_ET_STOP, d.t(10), d.t(10));
      oe.level = 200.0;
      oe.expiry_excl = d.t(300);
      oe.void_le = true;
      oe.x_gap = true;
      oe.x_sched = d.t(40);
      cases.push_back({d, oe});                                  // late PVOID of an armed order
      int k = 0;
      for(auto &cs : cases)
        {
         run_world(cs.first, {at_min(10, cs.second)}, 140);
         std::vector<std::string> full = trade_lines();
         run_world(cs.first, {at_min(10, cs.second)}, 140, 1, 0);
         std::vector<std::string> sparse = trade_lines();
         std::sort(full.begin(), full.end());
         std::sort(sparse.begin(), sparse.end());
         char what[96];
         snprintf(what, sizeof(what), "W15 case %d: no PapOnBarrier call, the same %zu events", k++, full.size());
         check(!full.empty() && full == sparse, what);
        }
   }
   // W16: the trade is stopped on L (the last bar before a hole at x0) and the revision's re-test on the bar before L
   //      grants the hold: with xh after the hole the stop exit stands; with xh in the same hole exit_index(xh) is L too
   //      and the time exit at L's open replaces it (PREVISE)
   {
      World w;
      w.flat(0, 28, 100.0);
      w.add(28, 100.0, 105.0, 100.0, 104.0);          // ahead at 28
      w.add(29, 104.0, 104.1, 97.0, 97.5);            // the stop (fill - 2) is hit on 29
      w.flat(100, 200, 97.5);
      CrOrder o = mk(88, 1, CR_ET_MARKET, w.t(10), w.t(10));
      o.stop_dist = 2.0;
      o.x_sched = w.t(30);
      o.x_gap = true;
      o.xh = w.t(150);
      o.xh_r = 1.0;
      run_world(w, {at_min(10, o)}, 210);
      double fp = 100.1 * (1 + SM);
      const CrPEvent *x = last_ev(CR_EV_PEXIT, 88), *h = last_ev(CR_EV_HOLD, 88);
      check(x && x->reason == CR_R_STOP && x->t == w.t(29) + 60 && eq(x->px, (fp - 2.0) * (1 - SS)), "W16 stop exit on L");
      check(count_ev(CR_EV_HOLD, 88) == 1 && h && h->x == w.t(150) && eq(h->px, 104.0) && h->t == w.t(61) && count_ev(CR_EV_PREVISE, 88) == 0,
            "W16 the revision grants the hold (mark of the bar before L): the stop exit stands");
      o.xh = w.t(60);
      run_world(w, {at_min(10, o)}, 210);
      const CrPEvent *r = last_ev(CR_EV_PREVISE, 88);
      check(r && r->t == w.t(29) && r->reason == CR_R_TIME && eq(r->px, 104.0 * (1 - SM)) && r->x == w.t(60) && r->bar == w.t(29),
            "W16 xh in the same hole: PREVISE at L's open after the barrier passes xh + 30 min");
   }
   // W17: a rule exit that resolves while its order still waits for a fill: the exit comes at the bar after the fill
   {
      World w;
      w.flat(0, 20, 100.0);
      w.add(20, 100.0, 101.5, 99.9, 101.2);
      w.flat(21, 40, 101.2);
      CrOrder a = mk(89, 1, CR_ET_STOP, w.t(10), w.t(10));
      a.level = 101.0;
      a.expiry_excl = w.t(30);
      a.stop_dist = 5.0;
      a.x_sched = w.t(35);
      Out e = ex_min(12, 89, w.t(12), w.t(15));
      run_world(w, {at_min(10, a), e}, 45);
      const CrPEvent *f = last_ev(CR_EV_PFILL, 89), *x = last_ev(CR_EV_PEXIT, 89);
      check(f && f->t == w.t(20) && eq(f->px, 101.0 * (1 + SS)) && x && x->t == w.t(21) && x->reason == CR_R_TIME,
            "W17 a rule exit resolved before the fill: time exit at the bar after the fill (sim.py:137)");
   }
   // W18: a refused limit entry: PREFUSE at its fill bar, no trade, nothing counts as an exit
   {
      World w;
      w.flat(0, 15, 100.0);
      w.add(15, 100.0, 100.05, 99.4, 99.6);
      w.flat(16, 40, 99.6);
      CrOrder a = mk(90, 1, CR_ET_LIMIT, w.t(10), w.t(10));
      a.level = 99.5;
      a.expiry_excl = w.t(30);
      a.stop_dist = 0.2;
      a.refuse = CR_REF_PAYOFF;
      run_world(w, {at_min(10, a)}, 45);
      const CrPEvent *r = last_ev(CR_EV_PREFUSE, 90);
      CrTrade t;
      check(r && r->t == w.t(15) && eq(r->px, 99.5) && count_ev(CR_EV_PFILL, 90) == 0 && !PapTrade(0, t) && PapLastExitBar(0) == 0,
            "W18 refused limit entry: PREFUSE at the fill bar, flat, no exit bar");
   }
   // W19: an armed void_le stop entry with no kept bar from its activation bar to x + 30 min: PVOID at that barrier;
   //      with a bar inside [x, x + 30 min] it stays armed
   {
      World w;
      w.flat(0, 11, 100.0);
      w.flat(100, 120, 100.0);
      CrOrder a = mk(91, 1, CR_ET_STOP, w.t(10), w.t(10));
      a.level = 200.0;
      a.expiry_excl = w.t(300);
      a.void_le = true;
      a.x_gap = true;
      a.x_sched = w.t(40);
      run_world(w, {at_min(10, a)}, 130);
      const CrPEvent *v = last_ev(CR_EV_PVOID, 91);
      check(count_ev(CR_EV_PVOID, 91) == 1 && v && v->t == w.t(10) && count_ev(CR_EV_PFILL, 91) == 0, "W19 armed void_le order: PVOID");
      World w2;
      w2.flat(0, 11, 100.0);
      w2.add(50, 100.0, 100.05, 99.95, 100.0);
      w2.flat(100, 120, 100.0);
      run_world(w2, {at_min(10, a)}, 130);
      CrOrder q;
      check(count_ev(CR_EV_PVOID, 91) == 0 && PapPending(0, q) && q.oid == 91, "W19 a bar in [x, x + 30 min]: still armed");
   }
   // W20: stopped on its fill bar while its gap question is open; the revision finds L = the fill bar: the stop exit
   //      stands (no PREVISE); with void_le the order never existed (PVOID, no exit bar left)
   {
      World w;
      w.flat(0, 10, 100.0);
      w.add(10, 100.0, 100.05, 99.9, 100.0);
      w.flat(100, 130, 100.0);
      CrOrder a = mk(92, 1, CR_ET_MARKET, w.t(10), w.t(10));
      a.stop_dist = 0.1;
      a.x_sched = w.t(40);
      a.x_gap = true;
      run_world(w, {at_min(10, a)}, 140);
      const CrPEvent *x = last_ev(CR_EV_PEXIT, 92);
      double fp = 100.1 * (1 + SM);
      check(x && x->reason == CR_R_STOP && x->t == w.t(10) + 60 && eq(x->px, (fp - 0.1) * (1 - SS)) && count_ev(CR_EV_PREVISE, 92) == 0
            && PapLastExitBar(0) == w.t(10), "W20 stopped on the fill bar, L = fill bar: the stop exit stands");
      a.void_le = true;
      run_world(w, {at_min(10, a)}, 140);
      check(count_ev(CR_EV_PVOID, 92) == 1 && PapLastExitBar(0) == 0, "W20 void_le: PVOID, no exit bar left");
   }
   // W22: an armed void_le order whose void (first barrier after x + 30 min) and expiry fall in one hole: the earlier of
   //      the two barriers decides, with or without PapOnBarrier calls (void 9 minutes before the expiry: PVOID; void at
   //      the expiry's own barrier: the expiry, no event)
   {
      World w;
      w.flat(0, 11, 100.0);
      w.flat(200, 220, 100.0);
      for(int k = 0; k < 2; k++)
        {
         CrOrder a = mk(96 + k, 1, CR_ET_STOP, w.t(10), w.t(10));
         a.level = 200.0;
         a.void_le = true;
         a.x_gap = true;
         a.x_sched = w.t(40);
         a.expiry_excl = (k == 0) ? w.t(80) : w.t(71);          // void decided at barrier 71
         int n[2];
         for(int mode = 0; mode < 2; mode++)
           {
            run_world(w, {at_min(10, a)}, 230, 1, mode == 0 ? 1 : 0);
            n[mode] = count_ev(CR_EV_PVOID, 96 + k);
           }
         char what[96];
         snprintf(what, sizeof(what), "W22 %s: %s with and without barrier calls", k == 0 ? "void before expiry" : "void at the expiry",
                  k == 0 ? "PVOID" : "no PVOID");
         check(n[0] == n[1] && n[0] == (k == 0 ? 1 : 0), what);
        }
   }
   // W21: an order activating on the bar where the trade took its target is skipped; the next bar is free
   {
      World w;
      w.flat(0, 12, 100.0);
      w.add(12, 100.0, 101.0, 99.95, 100.9);
      w.flat(13, 30, 100.9);
      CrOrder a = mk(93, 1, CR_ET_MARKET, w.t(10), w.t(10));
      a.target_dist = 0.5;
      CrOrder b = mk(94, -1, CR_ET_MARKET, w.t(12), w.t(12));
      CrOrder c = mk(95, -1, CR_ET_MARKET, w.t(13), w.t(13));
      run_world(w, {at_min(10, a), at_min(12, b), at_min(13, c)}, 35);
      const CrPEvent *x = last_ev(CR_EV_PEXIT, 93);
      double fp = 100.1 * (1 + SM);
      check(x && x->reason == CR_R_TARGET && x->t == w.t(12) + 60 && eq(x->px, MathMax(fp + 0.5, 100.0)) && count_ev(CR_EV_PFILL, 94) == 0
            && count_ev(CR_EV_PFILL, 95) == 1, "W21 skip on the exit bar (target), taken on the next bar");
   }
  }

int main(int argc, char **argv)
  {
   if(argc >= 3 && string(argv[1]) == "replay") return replay(argv[2], argc >= 4 ? atoi(argv[3]) : 1);
   worlds();
   printf("test_paper worlds: %d checks, %d failed\n", g_checks, g_fails);
   return g_fails == 0 ? 0 : 1;
  }
