//+------------------------------------------------------------------+
//| CR_Main.mqh - event handlers, startup machine (SPEC 4.8) and the  |
//| minute driver shared by the replay and live. Owner: S0, then K.   |
//|                                                                  |
//| Startup and rebuild (SPEC 4.8):                                  |
//|   OnInit: inputs, symbols, rules, instance lock, self-test, timer|
//|   WAIT    (a) connected, ledger settled, positions and orders    |
//|           read twice 2 s apart agree                             |
//|   REPLAY  (b) ledger and history latches; (c) the history is     |
//|           replayed minute by minute through rules, paper and dry |
//|           sizing, orders off                                     |
//|   RECON   (d) reconcile (retried each pass, no new replay)       |
//|   LIVE    (e) every timer pass: protections, broker-stop         |
//|           invariant, then every new barrier minute               |
//|   LATEBAR, a reconnection after more than 60 s: back to WAIT.    |
//|   The REBUILD line says why it ran (start, latebar, reconnect);  |
//|   the LATEBAR line itself is CR_Bars' (symbol and reason).       |
//|                                                                  |
//| Lines of this file: INIT (inputs as read, K1 table as parsed),   |
//| SELFTEST (build constants, golden vectors, the guards' checks), |
//| PLAN (plan start, B(T)), REBUILD, AGG / COST / DAY (daily), and  |
//| the INIT deinit line (bars fed and masked, rebuilds).           |
//| Step K kept S0's driver and contract; it only adds the fields    |
//| above. It must keep compiling with the S0 stubs that the rule    |
//| steps' tests still use: a call into a non-S0 function is guarded |
//| by a macro only the real file defines (CR_K1_MAX, CR_GOLDEN_N).  |
//|                                                                  |
//| The minute contract (every rule relies on it):                   |
//|   for every whole UTC minute M, in increasing order:             |
//|     1. every kept bar starting before M not yet fed, in (time,   |
//|        symbol id) order: OnBar of each sleeve reading that       |
//|        symbol (its orders go to the paper at once), then the     |
//|        paper of each sleeve trading that symbol;                 |
//|     2. OnMinute(M) of every sleeve (orders to the paper);        |
//|     3. PapOnBarrier(M);                                          |
//|     4. the follower (live: orders; replay: dry).                 |
//|   OnMinute is called for EVERY minute, markets open or not.      |
//+------------------------------------------------------------------+
#ifndef CR_MAIN_MQH
#define CR_MAIN_MQH
#include "CR_Types.mqh"
#include "CR_Clock.mqh"
#include "CR_Journal.mqh"
#include "CR_Math.mqh"
#include "CR_Registry.mqh"
#include "CR_Bars.mqh"
#include "CR_Paper.mqh"
#include "CR_Ledger.mqh"
#include "CR_Sizing.mqh"
#include "CR_Broker.mqh"
#include "CR_Follower.mqh"
#include "CR_Guards.mqh"
#include "CR_Golden.mqh"

#ifndef CR_BUILD
#define CR_BUILD "src"
#endif

int      g_st = CR_ST_INIT;            // driver state CR_ST_*
datetime g_M = 0;                      // last barrier processed (UTC minute), 0 = none
bool     g_replaying = false;          // inside step (c): lines carry rp=1
datetime g_day = 0;                    // server day of the counters below
long     g_day_fed[CR_NSYM];           // kept bars fed this server day
long     g_day_dec = 0;                // orders emitted this server day
long     g_day_pev = 0;                // paper events this server day
long     g_tot_fed = 0;
datetime g_disc_since = 0;             // first pass seen disconnected (0 = connected)
int      g_rebuilds = 0;
string   g_rebuild_why = "start";      // why the next rebuild runs (REBUILD why=): start, latebar, reconnect
bool     g_plan_said = false;
datetime g_plan_push_day = 0;

// ---- inputs -> g_cfg (SPEC 1, 4.9) ----------------------------------------------------------------------------------
void MainConfig()
  {
   g_cfg.trade = InpTrade;
   g_cfg.plan_start = InpPlanStart;
   g_cfg.risk_table = InpRiskTable;
   g_cfg.stop_fall_pct = InpStopFallPct;
   g_cfg.stop_arm_paid = InpStopArmPaid;
   g_cfg.sleeves = InpSleeves;
   g_cfg.k1 = InpK1;
   g_cfg.h2 = InpH2;
   g_cfg.s075 = InpS075;
   g_cfg.k1t = InpK1T;
   g_cfg.lock_stakes = InpDailyLockStakes;
   g_cfg.friday_hhmm = InpFridayCloseHHMM;
   g_cfg.closures = InpExtraClosures;
   g_cfg.push = InpPush;
   long mode = AccountInfoInteger(ACCOUNT_TRADE_MODE);
   g_cfg.demo = (mode == ACCOUNT_TRADE_MODE_DEMO || mode == ACCOUNT_TRADE_MODE_CONTEST);
   g_cfg.vps = TerminalInfoInteger(TERMINAL_VPS) != 0;
   g_cfg.tester = MQLInfoInteger(MQL_TESTER) != 0;
   // SPEC 4.9: on the VPS copy InpTrade = false blocks entries only; off the VPS, a copy on a real account, or on a
   // demo account with InpTrade false, is an observer that sends nothing at all
   if(g_cfg.vps)
     {
      g_cfg.observer = false;
      g_cfg.entries_off = !g_cfg.trade;
     }
   else
     {
      g_cfg.observer = !g_cfg.demo || !g_cfg.trade;
      g_cfg.entries_off = g_cfg.observer;
     }
   g_cfg.selftest_ok = false;
#ifdef CR_HARNESS
   g_cfg.harness = true;
   g_cfg.script = InpScript;
   g_cfg.script_dir = InpScriptDir;
#else
   g_cfg.harness = false;
   g_cfg.script = "";
   g_cfg.script_dir = "";
#endif
  }

// SPEC 1 / T10: a build without CR_HARNESS refuses the harness constants (trading blocked)
bool MainBuildCheck(string &why)
  {
   bool ok = true;
   why = "";
#ifndef CR_HARNESS
#ifdef CR_NO_GUARD
   ok = false;
   why = "CR_NO_GUARD is set in a build without CR_HARNESS";
#endif
   if(CR_XAU_COMM_PTS != 6)
     {
      ok = false;
      why = "CR_XAU_COMM_PTS is not 6";
     }
#endif
   return ok;
  }

// the broker's names, digits and points of the four symbols
bool MainSymbols(string &err)
  {
   for(int s = 0; s < CR_NSYM; s++)
     {
      string nm = BrkResolve(g_sym[s].base);
      if(nm == "")
        {
         err = "symbol " + g_sym[s].base + " not found (show the four .r symbols in the Market Watch)";
         return false;
        }
      double pt = SymbolInfoDouble(nm, SYMBOL_POINT);
      if(pt <= 0.0)
        {
         err = "symbol " + nm + " has no point size";
         return false;
        }
      g_sym[s].name = nm;
      RegSetPoint(s, (int)SymbolInfoInteger(nm, SYMBOL_DIGITS), pt);
      g_sym[s].ok = true;
     }
   return true;
  }

string MainSwitches()
  {
   string s = "";
   for(int i = 0; i < g_nsl; i++)
      if(g_sl[i].change != CR_CH_NONE)
         s = s + KV(RegChangeName(g_sl[i].change), g_sl[i].change_on ? "on" : "off");
   return s;
  }

void MainInitLine()
  {
   string kv = KV("build", CR_BUILD) + KV("version", CR_VERSION) + KB("demo", g_cfg.demo) + KB("vps", g_cfg.vps)
               + KB("tester", g_cfg.tester) + KB("observer", g_cfg.observer) + KB("entries_off", g_cfg.entries_off)
               + KB("harness", g_cfg.harness) + KI("comm_pts", CR_XAU_COMM_PTS) + KV("risk", g_cfg.risk_table)
               + KV("sleeves", g_cfg.sleeves) + MainSwitches();
#ifdef CR_K1_MAX
   kv = kv + KV("k1t", Brk72K1Text());          // the K1 table as CR_Rule_Brk72 parsed it (17 digits; "" = none)
#endif
   for(int s = 0; s < CR_NSYM; s++) kv = kv + KV(g_sym[s].base, g_sym[s].name);
   Jrn(CR_EV_INIT, "-", kv);
  }

// bars the mask dropped since the last load, all reasons (SPEC 2.2), for the deinit line
long MainMasked(const int sym)
  {
   long n = 0;
   for(int r = 1; r < CR_MASK_N; r++) n += BarsMasked(sym, r);
   return n;
  }

// ---- daily lines and reminders (server day of the barrier) ------------------------------------------------------------
void MainReminders(const datetime M, const datetime srv_day)
  {
   MqlDateTime t;
   TimeToStruct(srv_day, t);
   if(t.mon == 12 && t.day == 1)
      JrnPush("rappel : fermetures de l'an prochain a saisir dans InpExtraClosures (le labo les fournit)", false);
   if(t.mon == 1 && t.day == 1)
      JrnPush("rappel : nouveau seuil K1 de l'annee a saisir dans InpK1T (le labo le fournit)", false);
   for(int i = 0; i < g_nsl; i++)                 // weekly (Mondays): K1 is on but the lab gave no T for this year
      if(ClkDow(srv_day) == 1 && g_sl[i].change == CR_CH_K1 && g_sl[i].change_on && !Brk72K1Known(ClkYear(M)))
         JrnPush("K1 sans seuil pour " + IntegerToString(ClkYear(M)) + " : K1 inactif (" + g_sl[i].code + ")", false);
   if(LedPlan(TimeTradeServer()) == CR_PLAN_UNSET && g_plan_push_day != srv_day)
     {
      g_plan_push_day = srv_day;
      JrnPush("InpPlanStart n'est pas reglee sur le compte reel : aucune nouvelle entree", true);
     }
  }

void MainDaily(const datetime M, const bool live)
  {
   datetime d = ClkServerDay(M);
   if(d == g_day) return;
   if(g_day != 0 && live)
     {
      string kv = KT("day", g_day);
      for(int s = 0; s < CR_NSYM; s++) kv = kv + KI(g_sym[s].base, g_day_fed[s]);
      JrnAt(M, CR_EV_AGG, "-", kv + KI("dec", g_day_dec) + KI("pev", g_day_pev));
      for(int s = 0; s < CR_NSYM; s++)
        {
         double raw_bp = 0.0, paper_bp = 0.0;
         if(!BarsCost(s, g_day, raw_bp, paper_bp)) continue;
         string ck = KT("day", g_day) + KD("raw_bp", raw_bp) + KD("paper_bp", paper_bp) + KD("model_bp", g_sym[s].model_bp);
         double usd_oz = 0.0;
         int nc = 0;
         if(s == CR_XAU && LedCommission(g_day, usd_oz, nc)) ck = ck + KD("comm_usd_oz", usd_oz) + KI("comm_n", nc);
         JrnAt(M, CR_EV_COST, g_sym[s].base, ck);
         if(paper_bp > 1.5 * g_sym[s].model_bp)
            JrnPush("ecart " + g_sym[s].base + " " + DoubleToString(paper_bp, 2) + " pb, modele " + DoubleToString(g_sym[s].model_bp, 2), false);
         if(s == CR_XAU && nc > 0 && MathAbs(usd_oz - 0.06) > 0.01)
            JrnPush("commission or " + DoubleToString(usd_oz, 3) + " USD/oz au lieu de 0.06", false);
        }
      double bal = AccountInfoDouble(ACCOUNT_BALANCE), eq = AccountInfoDouble(ACCOUNT_EQUITY);
      JrnAt(M, CR_EV_DAY, "-", KT("day", g_day) + KD("balance", bal) + KD("equity", eq) + KI("bars_fed", g_tot_fed));
      JrnPush("resume du jour : solde " + DoubleToString(bal, 2) + ", fonds " + DoubleToString(eq, 2), false);
     }
   if(live) MainReminders(M, d);
   g_day = d;
   for(int s = 0; s < CR_NSYM; s++) g_day_fed[s] = 0;
   g_day_dec = 0;
   g_day_pev = 0;
  }

// ---- the minute driver ------------------------------------------------------------------------------------------------
void MainEmit(const int sl, CrOut &out, const datetime when, const bool live)
  {
   bool rp = !live;
   for(int i = 0; i < out.n_dec; i++)
     {
      out.dec[i].sleeve = sl;
      JrnDecRec(out.dec[i], when, rp);
     }
   for(int i = 0; i < out.n_ord; i++)
     {
      out.ord[i].sleeve = sl;
      JrnOrder(out.ord[i], when, rp);
      g_day_dec++;
      if(!PapSubmit(out.ord[i])) JrnError(g_sl[sl].code, "paper refused order " + JI(out.ord[i].oid) + " (two pending orders)");
     }
   for(int i = 0; i < out.n_ex; i++)
     {
      out.ex[i].sleeve = sl;
      JrnExitOrder(out.ex[i], when, rp);
      if(!PapSubmitExit(out.ex[i])) JrnError(g_sl[sl].code, "paper refused exit of " + JI(out.ex[i].oid));
     }
  }

void MainDrain(const bool live)
  {
   int n = PapEvents();
   for(int k = 0; k < n; k++)
     {
      CrPEvent e;
      if(!PapEvent(k, e)) continue;
      JrnPaper(e, !live);
      g_day_pev++;
      FolOnPaperEvent(e, live);
     }
   PapClearEvents();
  }

void MainFeedBar(const CrBar &b, const bool live)
  {
   CrOut out;
   for(int sl = 0; sl < g_nsl; sl++)
     {
      if(!RegReads(sl, b.sym)) continue;
      CrOutClear(out);
      RulesOnBar(sl, b.sym, b, out);
      MainEmit(sl, out, b.t, live);
     }
   for(int sl = 0; sl < g_nsl; sl++)
      if(g_sl[sl].sym == b.sym) PapOnBar(sl, b);
   MainDrain(live);
   g_day_fed[b.sym]++;
   g_tot_fed++;
#ifdef CR_DEBUG
   JrnBar(b);
#endif
  }

void MainMinute(const datetime M, const bool live)
  {
   CrBar b;
   while(BarsNext(M, b)) MainFeedBar(b, live);
   MainDaily(M, live);                            // after the feed: every bar fed so far starts before M
   CrOut out;
   for(int sl = 0; sl < g_nsl; sl++)
     {
      CrOutClear(out);
      RulesOnMinute(sl, M, out);
      MainEmit(sl, out, M, live);
     }
   PapOnBarrier(M);
   MainDrain(live);
   FolOnMinute(M, live);
   g_M = M;
  }

// ---- (a) wait -------------------------------------------------------------------------------------------------------
bool MainWait(const datetime now)
  {
   if(!BrkConnected()) return false;
   if(LedRead(now) != CR_LED_OK) return false;
   if(!LedSettled()) return false;
   if(!BrkStableRead(now)) return false;
   if(!g_plan_said)
     {
      int ps = LedPlan(now);
      string st = (ps == CR_PLAN_OK) ? "ok" : ((ps == CR_PLAN_UNSET) ? "unset" : "future");
      Jrn(CR_EV_PLAN, "-", KT("T", LedPlanStart()) + KV("state", st) + KB("demo", g_cfg.demo) + KD("B_T", LedBT())
          + KV("risk", g_cfg.risk_table));
      g_plan_said = true;
     }
   return true;
  }

// ---- (b)-(d) rebuild ------------------------------------------------------------------------------------------------
bool MainRebuild(const datetime now)
  {
   ulong t0 = GetTickCount64();
   if(BarsLoad(now) != CR_LOAD_OK) return false;
   string err = "";
   PapReset();
   FolReset();
   LedReset();
   if(!RulesInit(err))
     {
      JrnError("-", err);
      g_st = CR_ST_HALT;
      return false;
     }
   if(LedRead(now) != CR_LED_OK) return false;
   datetime M1 = BarsBarrier(now);
   datetime start = BarsStart();
   g_M = (start > 0 && start < M1) ? start : M1;
   long minutes = 0;
   g_replaying = true;
   for(datetime m = g_M + 60; m <= M1; m += 60)
     {
      MainMinute(m, false);
      minutes++;
     }
   g_replaying = false;
   g_M = M1;
   g_rebuilds++;
   Jrn(CR_EV_REBUILD, "-", KI("n", g_rebuilds) + KV("why", g_rebuild_why) + KT("from", start) + KT("to", M1) + KI("minutes", minutes)
       + KI("ms", (long)(GetTickCount64() - t0)));
   return true;
  }

// ---- (e) live -------------------------------------------------------------------------------------------------------
void MainLive(const datetime now)
  {
   if(!BrkConnected())
     {
      if(g_disc_since == 0) g_disc_since = now;
      return;
     }
   if(g_disc_since != 0)
     {
      bool longcut = (now - g_disc_since > 60);
      g_disc_since = 0;
      if(longcut)
        {
         g_st = CR_ST_WAIT;                       // a reconnection after more than 60 s reruns (a)-(d)
         g_rebuild_why = "reconnect";
         return;
        }
     }
   LedOnTimer(now);
   GrdOnTimer(now);
   FolOnTimer(now);
   BarsTimer(now);
   datetime M = BarsBarrier(now);
   if(M <= g_M) return;
   int r = BarsPoll(M);
   if(r == CR_POLL_WAIT) return;
   if(r == CR_POLL_LATEBAR)
     {
      g_st = CR_ST_WAIT;                          // CR_Bars wrote the LATEBAR line (symbol, reason); REBUILD says why=latebar
      g_rebuild_why = "latebar";
      return;
     }
   if(g_M == 0) g_M = M - 60;
   for(datetime m = g_M + 60; m <= M; m += 60) MainMinute(m, true);
  }

// ---- handlers -------------------------------------------------------------------------------------------------------
int OnInit()
  {
   MainConfig();
   JrnInit();
   RegInit();
   string err = "";
   bool ok = RegCheckInputs(err);
   if(ok) ok = ClkInit(g_cfg.closures, err);
   if(ok) ok = SizInit(err);
   if(ok) ok = MainSymbols(err);
   if(ok)
     {
      ChangeOn();
      ok = RulesInit(err);
     }
   if(ok) ok = BarsInit(err);
   if(ok)
     {
      PapInit();
      ok = LedInit(err);
     }
   if(ok) ok = BrkInit(err);
   if(ok) ok = FolInit(err);
   if(ok) ok = GrdInit(err);
   if(!ok)
     {
      JrnError("-", err);
      g_st = CR_ST_HALT;
      return INIT_PARAMETERS_INCORRECT;
     }
   if(!GrdLockTake())
     {
      JrnError("-", "another copy of ClaudeRobot runs on this terminal");
      g_st = CR_ST_HALT;
      return INIT_FAILED;
     }
   string why = "";
   bool st = MainBuildCheck(why);
   if(st) st = GoldenCheck(why);
   if(st) st = GrdSelfTest(why);
   g_cfg.selftest_ok = st;
   MainInitLine();
   string gk = "";
#ifdef CR_GOLDEN_N
   gk = KI("golden", CR_GOLDEN_N);              // vectors of CR_Golden.mqh (T10), all checked when ok=1
#endif
   Jrn(CR_EV_SELFTEST, "-", KB("ok", st) + KV("why", why) + gk);
   if(!st) JrnPush("auto-test en echec, aucune entree : " + why, true);
   bool timer = g_cfg.tester ? EventSetTimer(1) : EventSetMillisecondTimer(100);
   if(!timer)
     {
      JrnError("-", "the timer was refused");
      return INIT_FAILED;
     }
   g_st = CR_ST_WAIT;
   g_M = 0;
   g_day = 0;
   g_plan_said = false;
   g_rebuild_why = "start";
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   string mk = "";
   for(int s = 0; s < CR_NSYM; s++) mk = mk + KI("masked_" + g_sym[s].base, MainMasked(s));
   Jrn(CR_EV_INIT, "-", KI("deinit", reason) + KI("lines", g_jrn_lines) + KI("bars_fed", g_tot_fed) + KI("rebuilds", g_rebuilds) + mk);
   GrdLockRelease();
   JrnClose();
  }

void OnTick() { GrdOnTick(TimeTradeServer()); }

void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request, const MqlTradeResult &result)
  {
   LedOnTransaction();
   FolOnTransaction(trans);
  }

void OnTimer()
  {
   datetime now = TimeTradeServer();
   GrdLockRefresh();
   if(g_st == CR_ST_HALT || g_st == CR_ST_INIT) return;
   if(g_st == CR_ST_WAIT)
     {
      if(!MainWait(now)) return;
      g_st = CR_ST_REPLAY;
     }
   if(g_st == CR_ST_REPLAY)
     {
      if(!MainRebuild(now)) return;
      g_st = CR_ST_RECON;
     }
   if(g_st == CR_ST_RECON)
     {
      if(!FolReconcile(now)) return;              // (d): the barriers that pass meanwhile are processed once live
      g_st = CR_ST_LIVE;
     }
   MainLive(now);
  }

#endif
