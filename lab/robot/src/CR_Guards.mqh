//+------------------------------------------------------------------+
//| CR_Guards.mqh - the live protections of SPEC 6 (plan stop and     |
//| disaster guard close-all and mark, daily lock, Friday close,     |
//| clock check), the instance lock (SPEC 4.9), the self-test runner. |
//| Owner: J.                                                         |
//|                                                                  |
//| The guards read the history latches of CR_Ledger (STOP, GUARD b  |
//| and c, LOCK) and add what only the live account shows:            |
//|   GUARD (a)  equity <= 50 % of ref (LedRefNow), on a settled      |
//|              ledger, the plan in force; only with InpGuard true   |
//|              (off by default: D2, review F3) and not under        |
//|              CR_NO_GUARD;                                         |
//|   FRIDAY     InpFridayCloseHHMM > 0: from that Friday server time |
//|              to Monday 00:00 (ClaudeMains.mq5 FridayClosed); a    |
//|              robot position opened before the last Friday close   |
//|              is closed at the first chance (the close was missed);|
//|   CLOCK      |TimeTradeServer - TimeGMT - rule| > 120 s, checked  |
//|              at OnInit, every 10 min (every minute while wrong)   |
//|              and at the first tick after 30 min without one (a    |
//|              market reopening): entries blocked at once; wrong    |
//|              for 10 min -> the robot positions are closed and the |
//|              robot stays flat until the offset matches again;     |
//|              skipped under MQL_TESTER (R7, R12).                  |
//| Flat (STOP for good, GUARD for good, LOCK until the next server  |
//| day, FRIDAY, CLOCK for 10 min): every robot position is closed,  |
//| retried every 10 s, every 60 s while the market is closed, with  |
//| one warning push an hour while some cannot be closed (Watch,     |
//| ClaudeMains.mq5:698-739). GUARD closes with request magic        |
//| 20261290; if the history then holds no deal of that magic after  |
//| T, one minimum lot is opened and closed with it (BrkMark) on the |
//| first open market, every 60 s until such a deal exists (MARK).   |
//| Entries: GrdEntryBlock gives the reason that blocks a new entry   |
//| now, in the order STOPPED, GUARD, LOCK, FRIDAY, CLOCK, SELFTEST, |
//| NOTRADE (observer copy, InpTrade false on the VPS, lock lost).   |
//| An observer copy concludes and journals but sends nothing.       |
//| Instance lock: a temporary global variable "CR_lock_<login>"     |
//| holding a heartbeat (GetTickCount64, ms), taken with              |
//| GlobalVariableSetOnCondition and refreshed every pass; one not   |
//| refreshed for 10 s is stale and is taken over (TAKEOVER push). A |
//| copy whose lock was taken sends nothing (g_brk_may) and tries to |
//| take it again every 10 s. OnDeinit releases it.                   |
//| Self-test (OnInit, trading blocked when it fails): GridStop on    |
//| four grids, the byte order of the lab sleeve names, the comment  |
//| round trip, the chart mode bid of the four symbols; it also runs |
//| the first clock check.                                           |
//|                                                                  |
//| API (S0 signatures kept; the rest is new):                        |
//|   GrdInit(err)                  once at OnInit                   |
//|   GrdLockTake()                 instance lock (heartbeat);       |
//|                                 false = another copy runs        |
//|   GrdLockRefresh()              every timer pass                 |
//|   GrdLockRelease()              OnDeinit                         |
//|   GrdSelfTest(why)              false blocks trading             |
//|   GrdOnTimer(now_srv)           latches, flat closes, mark, clock|
//|   GrdOnTick(now_srv)            first tick after a reopening     |
//|   GrdEntryBlock(now_srv)        CR_SK_* reason that blocks new   |
//|                                 entries now, CR_SK_NONE if none  |
//|   GrdMaySend()                  false for an observer copy (or   |
//|                                 a copy that lost the lock)       |
//| New: GrdFlat() (positions must go now), GrdFridayWindow,          |
//|   GrdLastFridayClose, GrdClockCheck.                              |
//+------------------------------------------------------------------+
#ifndef CR_GUARDS_MQH
#define CR_GUARDS_MQH
#include "CR_Types.mqh"
#include "CR_Clock.mqh"
#include "CR_Journal.mqh"
#include "CR_Ledger.mqh"
#include "CR_Broker.mqh"

#define CR_GRD_LOCK_STALE_MS 10000.0    // a lock not refreshed for 10 s is stale (SPEC 4.9)
#define CR_GRD_LOCK_RETRY 10            // a copy without the lock tries again every 10 s
#define CR_GRD_CLOCK_TOL 120            // |server - GMT - rule| above 120 s: CLOCK (SPEC 6.5)
#define CR_GRD_CLOCK_EVERY 600          // checked every 10 min ...
#define CR_GRD_CLOCK_BAD_EVERY 60       // ... and every minute while it is wrong
#define CR_GRD_CLOCK_FLAT 600           // wrong for 10 min: the robot positions are closed
#define CR_GRD_REOPEN_GAP 1800          // a tick after 30 min without one: a market reopening
#define CR_GRD_RETRY 10                 // forced closes: every 10 s ...
#define CR_GRD_RETRY_CLOSED 60          // ... every 60 s while the market is closed
#define CR_GRD_WARN_EVERY 3600          // one warning push an hour while positions cannot be closed
#define CR_GRD_MARK_EVERY 60            // the mark trade: every 60 s until its deal exists
#define CR_GRD_GUARD_SHARE 0.5          // GUARD (a): equity at or below 50 % of ref

string   g_grd_lock_name = "";
double   g_grd_lock_beat = 0.0;
bool     g_grd_lock_held = false;
datetime g_grd_lock_retry = 0;
bool     g_grd_stop = false;            // STOP concluded (for good, until a later InpPlanStart)
bool     g_grd_guard = false;           // GUARD latched (a, b or c)
datetime g_grd_lock_day = 0;            // server day of a LOCK (0 = none)
bool     g_grd_friday = false;
bool     g_grd_clock_bad = false;       // the offset is wrong now: no entries
bool     g_grd_clock_flat = false;      // wrong for 10 min: flat
datetime g_grd_clock_since = 0;
datetime g_grd_clock_next = 0;
long     g_grd_clock_meas = 0;
datetime g_grd_close_next = 0;
datetime g_grd_warn_t = 0;
datetime g_grd_mark_next = 0;
datetime g_grd_mark_warn = 0;
long     g_grd_mark_tries = 0;
datetime g_grd_last_tick = 0;
bool     g_grd_flat = false;
string   g_grd_flat_why = "";

//+------------------------------------------------------------------+
//| Instance lock (SPEC 4.9, R10)                                    |
//+------------------------------------------------------------------+
bool GrdLockTake()
  {
   g_grd_lock_name = "CR_lock_" + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN));
   double now_ms = (double)GetTickCount64();
   if(!GlobalVariableCheck(g_grd_lock_name) && !GlobalVariableTemp(g_grd_lock_name)) return false;   // temporary: never saved
   double v = GlobalVariableGet(g_grd_lock_name);
   bool stale = (v == 0.0) || (now_ms - v > CR_GRD_LOCK_STALE_MS) || (now_ms < v);   // (now < v: the tick counter restarted)
   if(!stale) return false;
   if(!GlobalVariableSetOnCondition(g_grd_lock_name, now_ms, v)) return false;      // another copy took it first
   g_grd_lock_held = true;
   g_grd_lock_beat = now_ms;
   g_brk_may = true;
   if(v != 0.0)
     {
      Jrn(CR_EV_TAKEOVER, "-", KD("age_ms", now_ms - v));
      JrnPush("une autre copie du robot ne repondait plus depuis plus de 10 s : cette copie prend le relais", true);
     }
   return true;
  }

void GrdLockRefresh()
  {
   if(g_grd_lock_name == "") return;
   double now_ms = (double)GetTickCount64();
   if(g_grd_lock_held)
     {
      if(GlobalVariableCheck(g_grd_lock_name) && GlobalVariableSetOnCondition(g_grd_lock_name, now_ms, g_grd_lock_beat))
        {
         g_grd_lock_beat = now_ms;
         return;
        }
      if(!GlobalVariableCheck(g_grd_lock_name))                // the variable is gone (purged): take it again
        {
         g_grd_lock_held = false;
         if(GrdLockTake()) return;
        }
      g_grd_lock_held = false;                                 // another copy took the lock: this one sends nothing
      g_brk_may = false;
      JrnError("-", "the instance lock was taken by another copy of ClaudeRobot: this copy sends nothing");
      return;
     }
   datetime now = TimeTradeServer();
   if(now >= g_grd_lock_retry || (long)(g_grd_lock_retry - now) > CR_GRD_LOCK_RETRY)
     {
      g_grd_lock_retry = now + CR_GRD_LOCK_RETRY;
      if(GrdLockTake()) Jrn(CR_EV_TAKEOVER, "-", KV("lock", "taken_again"));
     }
  }

void GrdLockRelease()
  {
   if(g_grd_lock_held && g_grd_lock_name != "" && !GlobalVariableDel(g_grd_lock_name)) Jrn(CR_EV_ERROR, "-", KV("what", "lock not released"));
   g_grd_lock_held = false;
  }

bool GrdMaySend() { return !g_cfg.observer && g_brk_may; }

//+------------------------------------------------------------------+
//| Friday close (SPEC 6.4) and clock (SPEC 6.5)                     |
//+------------------------------------------------------------------+
// from the Friday server time InpFridayCloseHHMM to Monday 00:00 (ClaudeMains.mq5 FridayClosed)
bool GrdFridayWindow(const datetime now_srv)
  {
   int hhmm = g_cfg.friday_hhmm;
   if(hhmm <= 0) return false;
   int dow = ClkDow(now_srv);
   int mod = ClkMinOfDay(now_srv);
   return dow == 6 || dow == 0 || (dow == 5 && mod >= (hhmm / 100) * 60 + hhmm % 100);
  }

// the last Friday close at or before now (server); 0 when the Friday close is off (ClaudeMains.mq5 LastFridayClose)
datetime GrdLastFridayClose(const datetime now_srv)
  {
   int hhmm = g_cfg.friday_hhmm;
   if(hhmm <= 0) return 0;
   int dow = ClkDow(now_srv);
   datetime t = ClkDay(now_srv) - ((dow + 2) % 7) * 86400 + (hhmm / 100) * 3600 + (hhmm % 100) * 60;
   if(t > now_srv) t -= 7 * 86400;
   return t;
  }

// one clock check: the measured offset TimeTradeServer() - TimeGMT() against the rule (server = New York + 7 h)
void GrdClockCheck(const datetime now_srv)
  {
   if(g_cfg.tester)                                           // TimeGMT() = TimeTradeServer() in the tester (R12)
     {
      g_grd_clock_bad = false;
      g_grd_clock_flat = false;
      return;
     }
   datetime gmt = TimeGMT();
   long meas = (long)(now_srv - gmt);
   long rule = ClkRuleOffset(gmt);
   long d = meas - rule;
   if(d < 0) d = -d;
   g_grd_clock_meas = meas;
   if(d > CR_GRD_CLOCK_TOL)
     {
      if(!g_grd_clock_bad)
        {
         g_grd_clock_bad = true;
         g_grd_clock_since = now_srv;
         Jrn(CR_EV_CLOCK, "-", KV("state", "wrong") + KI("measured_s", meas) + KI("rule_s", rule));
         JrnPush("horloge du serveur decalee (" + IntegerToString(meas) + " s au lieu de " + IntegerToString(rule)
                 + " s) : aucune nouvelle entree", true);
        }
      if(now_srv < g_grd_clock_since) g_grd_clock_since = now_srv;
      if(!g_grd_clock_flat && (long)(now_srv - g_grd_clock_since) >= CR_GRD_CLOCK_FLAT)
        {
         g_grd_clock_flat = true;
         Jrn(CR_EV_CLOCK, "-", KV("state", "flat") + KI("measured_s", meas) + KI("rule_s", rule));
         JrnPush("horloge decalee depuis 10 min : les positions du robot sont fermees", true);
        }
      g_grd_clock_next = now_srv + CR_GRD_CLOCK_BAD_EVERY;
      return;
     }
   if(g_grd_clock_bad)
     {
      Jrn(CR_EV_CLOCK, "-", KV("state", "ok") + KI("measured_s", meas) + KI("rule_s", rule));
      JrnPush("horloge du serveur de nouveau correcte : entrees permises", false);
     }
   g_grd_clock_bad = false;
   g_grd_clock_flat = false;
   g_grd_clock_since = 0;
   g_grd_clock_next = now_srv + CR_GRD_CLOCK_EVERY;
  }

//+------------------------------------------------------------------+
//| Init and self-test                                               |
//+------------------------------------------------------------------+
bool GrdInit(string &err)
  {
   err = "";
   int hhmm = g_cfg.friday_hhmm;
   if(hhmm < 0 || hhmm / 100 > 23 || hhmm % 100 > 59)
     {
      err = "InpFridayCloseHHMM must be 0 (off) or a server time HHMM";
      return false;
     }
   g_grd_lock_beat = 0.0;
   g_grd_lock_held = false;
   g_grd_lock_retry = 0;
   g_grd_stop = false;
   g_grd_guard = false;
   g_grd_lock_day = 0;
   g_grd_friday = false;
   g_grd_clock_bad = false;
   g_grd_clock_flat = false;
   g_grd_clock_since = 0;
   g_grd_clock_next = 0;
   g_grd_clock_meas = 0;
   g_grd_close_next = 0;
   g_grd_warn_t = 0;
   g_grd_mark_next = 0;
   g_grd_mark_warn = 0;
   g_grd_mark_tries = 0;
   g_grd_last_tick = 0;
   g_grd_flat = false;
   g_grd_flat_why = "";
   return true;
  }

bool GrdNear(const double a, const double b) { return MathAbs(a - b) < 1e-7; }

bool GrdSelfTest(string &why)
  {
   why = "";
   // GridStop (SPEC 4.4): less than one tick away from the market, on four grids
   bool g = GrdNear(BrkGridOf(1234.567, 1, 0.01, 2), 1234.56) && GrdNear(BrkGridOf(1234.561, -1, 0.01, 2), 1234.57)
            && GrdNear(BrkGridOf(1234.56, 1, 0.01, 2), 1234.56) && GrdNear(BrkGridOf(1234.56, -1, 0.01, 2), 1234.56)
            && GrdNear(BrkGridOf(24950.10, 1, 0.25, 2), 24950.0) && GrdNear(BrkGridOf(25100.13, -1, 0.25, 2), 25100.25)
            && GrdNear(BrkGridOf(101.74, 1, 0.5, 1), 101.5) && GrdNear(BrkGridOf(101.26, -1, 0.5, 1), 101.5)
            && GrdNear(BrkGridOf(1.0, 1, 0.03, 2), 0.99) && GrdNear(BrkGridOf(1.0, -1, 0.03, 2), 1.02);
   if(!g)
     {
      why = "GridStop vectors";
      return false;
     }
   // the byte order of the lab sleeve names (stake.py:108: intents of one stamp are sized in this order)
   string nm[] = {"F1_brk_ridge_filter_btcusd", "F1_brk_ridge_filter_ethusd", "GOLD_FRI_PM_xauusd", "brk72_24h_wd_btcusd",
                  "brk72_24h_wd_ethusd", "donch4h_stop_xauusd", "noise30_us100", "nq_btc_follow_btcusd", "ocm4_us100",
                  "orb_asia_2d_buf10_xauusd"};
   for(int k = 1; k < ArraySize(nm); k++)
      if(CrStrCmp(nm[k - 1], nm[k]) >= 0 || CrStrCmp(nm[k], nm[k - 1]) <= 0)
        {
         why = "byte order of the sleeve names";
         return false;
        }
   // the comment round trip (LatestExit cross-check)
   datetime t0 = (datetime)1640995140;                         // 2021-12-31 23:59 UTC
   if(BrkCommentDec(BrkComment("BKB", t0), "BKB") != t0 || BrkCommentDec(BrkComment("BKB", t0), "BKE") != 0
      || BrkCommentDec("CR BKB 2113312400", "BKB") != 0)
     {
      why = "robot comment";
      return false;
     }
   // SPEC 2.2: the bars must be bid bars
   for(int s = 0; s < CR_NSYM; s++)
      if(g_sym[s].name != "" && SymbolInfoInteger(g_sym[s].name, SYMBOL_CHART_MODE) != SYMBOL_CHART_MODE_BID)
        {
         why = "chart mode of " + g_sym[s].name + " is not bid";
         return false;
        }
   GrdClockCheck(TimeTradeServer());                           // the clock at OnInit (SPEC 6.5): a wrong one blocks entries
   return true;
  }

//+------------------------------------------------------------------+
//| Timer                                                            |
//+------------------------------------------------------------------+
void GrdGuardLatch(const string src, const double eq, const double ref)
  {
   g_grd_guard = true;
   Jrn(CR_EV_GUARD, "-", KV("src", src) + KD("equity", eq) + KD("ref", ref) + KB("observer", g_cfg.observer));
   if(!g_cfg.observer)
      JrnPush("GARDE-FOU : fonds " + DoubleToString(eq, 2) + " pour une reference de " + DoubleToString(ref, 2)
              + " (50 %) : tout est ferme, arret definitif", true);
  }

bool GrdLockToday(const datetime now_srv)
  {
   return g_grd_lock_day != 0 && g_grd_lock_day == ClkDay(now_srv) && g_cfg.lock_stakes > 0.0;
  }

// close every robot position for the flat reason `why` (request magic `magic`, 0 = its own), with the retry rhythm
void GrdCloseFlat(const datetime now_srv, const long magic, const string why)
  {
   if(!GrdMaySend() || BrkRobotCount() == 0) return;
   if(now_srv < g_grd_close_next && (long)(g_grd_close_next - now_srv) <= 120) return;   // (beyond 120 s: the clock stepped back)
   int bad = 0, shut = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      long m = PositionGetInteger(POSITION_MAGIC);
      if(!BrkOurMagic(m)) continue;
      if(BrkClose(t, magic > 0 ? magic : m, why)) continue;
      bad++;
      if(g_brk_rc == TRADE_RETCODE_MARKET_CLOSED) shut++;
     }
   if(bad == 0)
     {
      g_grd_close_next = 0;
      return;
     }
   g_grd_close_next = now_srv + ((shut == bad) ? CR_GRD_RETRY_CLOSED : CR_GRD_RETRY);
   if((long)(now_srv - g_grd_warn_t) >= CR_GRD_WARN_EVERY || now_srv < g_grd_warn_t)
     {
      string cause = (shut == bad) ? "marche ferme" : (BrkTradeAllowed() ? "refus du courtier" : "trading automatique desactive dans MT5");
      if(JrnPush("ATTENTION : " + IntegerToString(bad) + " position(s) du robot devraient etre fermees et ne le sont pas (" + cause + ")",
                 true))
         g_grd_warn_t = now_srv;                               // dropped by the push limits: said again at the next attempt
     }
  }

void GrdOnTimer(const datetime now_srv)
  {
   // STOP (SPEC 6.1): from the history, concluded on a settled ledger only
   if(!g_grd_stop && LedStopLatched())
     {
      g_grd_stop = true;
      Jrn(CR_EV_STOP, "-", KV("src", "guards") + KD("B", LedBalanceNow()) + KD("ref", LedRefNow()) + KD("P_in", LedPaidInNow())
          + KB("observer", g_cfg.observer));
      if(!g_cfg.observer)
         JrnPush("STOP du plan : le solde est tombe de " + DoubleToString(g_cfg.stop_fall_pct, 0)
                 + " % sous la reference : tout est ferme, arret definitif", true);
     }
#ifndef CR_NO_GUARD
   // GUARD (SPEC 6.2): (b, c) from the history, (a) on the live equity; never with InpGuard false
   if(!g_grd_guard && !g_cfg.guard_off)
     {
      bool settled = LedSettled();
      if(LedGuardLatched()) GrdGuardLatch("history", AccountInfoDouble(ACCOUNT_EQUITY), LedRefNow());
      else if(settled && LedPlan(now_srv) == CR_PLAN_OK)
        {
         double ref = LedRefNow(), eq = AccountInfoDouble(ACCOUNT_EQUITY);
         if(ref > 0.0 && eq <= CR_GRD_GUARD_SHARE * ref) GrdGuardLatch("equity", eq, ref);
        }
     }
#endif
   // LOCK (SPEC 6.3): until the next server day
   if(g_cfg.lock_stakes > 0.0 && LedDayLocked(now_srv) && g_grd_lock_day != ClkDay(now_srv))
     {
      g_grd_lock_day = ClkDay(now_srv);
      Jrn(CR_EV_LOCK, "-", KD("stakes", g_cfg.lock_stakes) + KB("observer", g_cfg.observer));
      if(!g_cfg.observer) JrnPush("perte max du jour atteinte : tout est ferme, reprise demain", true);
     }
   bool lock_on = GrdLockToday(now_srv);
   // FRIDAY (SPEC 6.4) and CLOCK (SPEC 6.5)
   g_grd_friday = GrdFridayWindow(now_srv);
   if(!g_cfg.tester && (now_srv >= g_grd_clock_next || (long)(g_grd_clock_next - now_srv) > CR_GRD_CLOCK_EVERY)) GrdClockCheck(now_srv);
   // flat
   g_grd_flat = g_grd_stop || g_grd_guard || lock_on || g_grd_friday || g_grd_clock_flat;
   g_grd_flat_why = "";
   long magic = 0;
   if(g_grd_stop) g_grd_flat_why = "stop";
   else if(g_grd_guard)
     {
      g_grd_flat_why = "guard";
      magic = CR_MAGIC_MARK;
     }
   else if(lock_on) g_grd_flat_why = "lock";
   else if(g_grd_friday) g_grd_flat_why = "friday";
   else if(g_grd_clock_flat) g_grd_flat_why = "clock";
   if(g_grd_flat) GrdCloseFlat(now_srv, magic, g_grd_flat_why);
   // a Friday close missed (the terminal was off): positions opened before it are closed at the first chance
   datetime lfc = GrdLastFridayClose(now_srv);
   if(!g_grd_flat && lfc > 0 && GrdMaySend() && (now_srv >= g_grd_close_next || (long)(g_grd_close_next - now_srv) > 120))
     {
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         ulong t = PositionGetTicket(i);
         if(t == 0) continue;
         long m = PositionGetInteger(POSITION_MAGIC);
         if(!BrkOurMagic(m) || (datetime)PositionGetInteger(POSITION_TIME) >= lfc) continue;
         if(BrkClose(t, m, "friday_missed"))
            JrnPush("fermeture du vendredi manquee : position " + IntegerToString((long)t) + " fermee", false);
         else g_grd_close_next = now_srv + ((g_brk_rc == TRADE_RETCODE_MARKET_CLOSED) ? CR_GRD_RETRY_CLOSED : CR_GRD_RETRY);
        }
     }
#ifndef CR_NO_GUARD
   // the guard's mark (SPEC 6.2): a deal of magic 20261290 after T keeps GUARD latched across restarts (c)
   if(g_grd_guard && GrdMaySend() && BrkRobotCount() == 0 && (now_srv >= g_grd_mark_next || (long)(g_grd_mark_next - now_srv) > CR_GRD_MARK_EVERY))
     {
      LedRead(now_srv);
      if(!LedMarkSeen() && LedPlan(now_srv) != CR_PLAN_UNSET)
        {
         g_grd_mark_next = now_srv + CR_GRD_MARK_EVERY;
         g_grd_mark_tries++;
         string why = "no_open_market";
         bool ok = false;
         for(int s = 0; s < CR_NSYM && !ok; s++)
            if(g_sym[s].ok && g_sym[s].name != "") ok = BrkMark(s, why);
         if(!ok)
           {
            Jrn(CR_EV_MARK, "-", KV("state", "failed") + KV("why", why) + KI("tries", g_grd_mark_tries));
            if((long)(now_srv - g_grd_mark_warn) >= CR_GRD_WARN_EVERY || now_srv < g_grd_mark_warn)
              {
               if(JrnPush("GARDE-FOU : la marque (1 lot minimum, magic 20261290) n'a pas pu etre passee (" + why + "), nouvel essai chaque minute", true))
                  g_grd_mark_warn = now_srv;
              }
           }
        }
     }
#endif
  }

// the first tick after a market reopening: the clock is checked (SPEC 6.5)
void GrdOnTick(const datetime now_srv)
  {
   bool reopen = (g_grd_last_tick > 0 && (long)(now_srv - g_grd_last_tick) >= CR_GRD_REOPEN_GAP);
   g_grd_last_tick = now_srv;
   if(reopen && !g_cfg.tester) GrdClockCheck(now_srv);
  }

// positions must be flat now (STOP, GUARD, LOCK, FRIDAY, CLOCK for 10 min)
bool GrdFlat() { return g_grd_flat; }

int GrdEntryBlock(const datetime now_srv)
  {
   if(g_grd_stop) return CR_SK_STOPPED;
   if(g_grd_guard) return CR_SK_GUARD;
   if(GrdLockToday(now_srv)) return CR_SK_LOCK;
   if(GrdFridayWindow(now_srv)) return CR_SK_FRIDAY;
   if(g_grd_clock_bad) return CR_SK_CLOCK;
   if(!g_cfg.selftest_ok) return CR_SK_SELFTEST;
   if(g_cfg.observer || g_cfg.entries_off || !g_brk_may) return CR_SK_NOTRADE;
   return CR_SK_NONE;
  }
#endif
