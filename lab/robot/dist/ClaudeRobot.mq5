#define CR_BUILD "1ca53085c0c1"
// ==== begin src/ClaudeRobot.mq5
//+------------------------------------------------------------------+
//|                                               ClaudeRobot.mq5    |
//|  One Expert Advisor holding the ten validated rules of the lab,  |
//|  the three changes kept by the 2022-2025 look (behind switches), |
//|  their sizing and their protections, for FP Markets (Raw, .r     |
//|  symbols, hedging, 1:500) on the MetaQuotes VPS.                 |
//|  Specification: lab/robot/SPEC.md. Installed as the single file  |
//|  dist/ClaudeRobot.mq5 built by tools/amalgam.py.                 |
//|                                                                  |
//|  Every rule keeps a paper chain (the lab's simulator run on the  |
//|  broker's closed M1 bars); the account follows it with market    |
//|  orders and a broker stop on every position. Nothing is kept     |
//|  between runs: every start rebuilds everything from the broker.  |
//+------------------------------------------------------------------+
#property copyright "gold-orb lab"
#property version   "2.00"
#property description "ClaudeRobot: ten lab rules on XAUUSD, US100, BTCUSD and ETHUSD; paper chains followed by market orders with broker stops."

// ---- the 14 inputs (SPEC 1). Plain types only.
input bool     InpTrade            = true;                          // Trade (VPS copy: false = no new entry; elsewhere: observe)
input datetime InpPlanStart        = 0;                             // Plan start, server time (0: no new entry on a real account)
input string   InpRiskTable        = "0:3;3000:2;6000:1;12000:0.5"; // Risk table from:pct, read on max(balance, money paid in) (F3S)
input double   InpStopFallPct      = 25.0;                          // Plan stop: fall of the reference, percent
input double   InpStopArmPaid      = 12000.0;                       // Plan stop: armed once this much has been paid in
input string   InpSleeves          = "ALL";                         // Codes allowed to trade (the others: paper only)
input int      InpK1               = -1;                            // K1 on BKE: -1 demo on / real off, 0 off, 1 on
input int      InpH2               = -1;                            // H2 on F1E: -1 demo on / real off, 0 off, 1 on
input int      InpS075             = -1;                            // S0.75r on BKB: -1 demo on / real off, 0 off, 1 on
input string   InpK1T              = "";                            // K1 thresholds YYYY:T;YYYY:T in bp, from the lab
input double   InpDailyLockStakes  = 0.0;                           // Daily lock in stakes (0 = off)
input int      InpFridayCloseHHMM  = 0;                             // Friday close, server HHMM (0 = off)
input string   InpExtraClosures    = "";                            // Typed closures: NYSE d; HALF d; XAU|IDX|CRY d hh:mm-d hh:mm
input bool     InpPush             = true;                          // Push notifications
#ifdef CR_HARNESS
input string   InpScript           = "";                            // Harness: codes replaying ref_lab.py orders
input string   InpScriptDir        = "ClaudeRobot\\script";         // Harness: folder of the script files
#endif

#include <Trade\Trade.mqh>
// ==== begin src/CR_Types.mqh
//+------------------------------------------------------------------+
//| CR_Types.mqh - shared types of ClaudeRobot (owner: S0)            |
//|                                                                  |
//| Every module includes this file. It holds the constants, the     |
//| structs of SPEC.md 2.4 (bars, orders, exits, paper events,       |
//| intents), the symbol and sleeve tables (rows filled by           |
//| CR_Registry.mqh), the configuration read from the inputs, the    |
//| journal event codes and a byte-order string compare.             |
//| Times are UTC seconds unless a name says otherwise (srv = server |
//| clock, ny = New York wall clock).                                 |
//+------------------------------------------------------------------+
#ifndef CR_TYPES_MQH
#define CR_TYPES_MQH

// ---- compile-time constants (SPEC 1). Harness builds pass other values with -D; the self-test refuses them in a
// ---- build without CR_HARNESS (SPEC 7, T10).
#ifndef CR_XAU_COMM_PTS
#define CR_XAU_COMM_PTS 6              // gold round-trip commission in points (0.06 USD/oz, FP Raw), SPEC 2.2
#endif
#define CR_VERSION "2.00"

// ---- sizes
#define CR_NSYM 4                      // symbols
#define CR_MAX_SL 16                   // capacity of the sleeve table (g_nsl rows are used)
#define CR_OUT_MAX 8                   // orders, exits or decisions a rule may emit in one call

// ---- symbol ids (also the tie order of bars that start in the same minute, SPEC 2.4)
#define CR_XAU 0
#define CR_IDX 1                       // US100
#define CR_BTC 2
#define CR_ETH 3

// ---- market families (known closures, typed InpExtraClosures: XAU | IDX | CRY)
#define CR_FAM_XAU 0
#define CR_FAM_IDX 1
#define CR_FAM_CRY 2

// ---- rule kinds (one class each; CR_Registry dispatches on them)
#define CR_K_NONE 0
#define CR_K_N30 1
#define CR_K_OC4 2
#define CR_K_BRK72 3
#define CR_K_F1 4
#define CR_K_NQB 5
#define CR_K_GFP 6
#define CR_K_D4H 7
#define CR_K_ORX 8
#define CR_K_SCRIPT 9                  // harness only (CR_HARNESS): replays a file of lab orders

// ---- the three kept changes (SPEC 3.9) and their refusals (SPEC 2.5)
#define CR_CH_NONE 0
#define CR_CH_K1 1
#define CR_CH_H2 2
#define CR_CH_S075 3
#define CR_REF_NONE 0
#define CR_REF_PAYOFF 1                // payoff lens: d0 < 3 x spread
#define CR_REF_SB 2                    // synthesis_B: |fp - st| < 3 x spread or stop on the wrong side

// ---- order entry types (CrOrder.etype)
#define CR_ET_MARKET 0
#define CR_ET_STOP 1
#define CR_ET_LIMIT 2
#define CR_ET_OCO 3                    // buy stop at level, sell stop at level2; side decided at the fill

// ---- exit reasons: the values of goldlab/sim.py REASONS, then the robot's own
#define CR_R_NONE -1
#define CR_R_STOP 0
#define CR_R_TARGET 1
#define CR_R_TIME 2
#define CR_R_TRAIL 3
#define CR_R_EOD 4
#define CR_R_NOFILL 5
#define CR_R_SKIP 6
#define CR_R_GAP 7
#define CR_R_VOID 8                    // void_le order whose exit bar does not follow its entry bar (PVOID)
#define CR_R_REFUSED 9                 // 3-spread refusal (PREFUSE)
#define CR_R_RULE 10                   // reserved: the paper books a CrExit as a time exit (reason time, as the lab's exit_i)

// ---- decision records without an order (CrDec.what)
#define CR_DEC_SKIP_K1 1               // v1 = riskbp, v2 = T(Y)
#define CR_DEC_INFO 2                  // free diagnostic (v1, v2)

// ---- skip reasons of the account (SIZE / MISSED lines), in the lab's check order (SPEC 5)
#define CR_SK_NONE 0
#define CR_SK_STOPPED 1
#define CR_SK_GUARD 2
#define CR_SK_LOCK 3
#define CR_SK_FRIDAY 4
#define CR_SK_CLOCK 5
#define CR_SK_NOTREADY 6
#define CR_SK_OBSERVE 7
#define CR_SK_SETTLE 8
#define CR_SK_PREV_OPEN 9
#define CR_SK_MIN_LOT 10
#define CR_SK_CAP 11
#define CR_SK_MARGIN 12
#define CR_SK_NOTALLOWED 13            // code not in InpSleeves (paper only)
#define CR_SK_NOTRADE 14               // InpTrade false / observer
#define CR_SK_LATE 15                  // past stamp + 5 min
#define CR_SK_EXITED 16                // paper trade already exited (MISSED reason=exited)
#define CR_SK_SELFTEST 17              // self-test failed

// ---- intent states (follower)
#define CR_IS_WAIT 0
#define CR_IS_SENT 1
#define CR_IS_UNKNOWN 2
#define CR_IS_OPEN 3
#define CR_IS_DONE 4
#define CR_IS_MISSED 5

// ---- results of module calls used by the driver
#define CR_LOAD_OK 0
#define CR_LOAD_RETRY 1
#define CR_POLL_OK 0
#define CR_POLL_WAIT 1                 // a bar that ticked is not returned yet: retry (30 s, then GAP)
#define CR_POLL_LATEBAR 2              // one of the last 3 bars changed: rebuild
#define CR_LED_OK 0
#define CR_LED_MOVING 1                // B(T) not the same in two reads 2 s apart (SETTLE)
#define CR_PLAN_OK 0
#define CR_PLAN_UNSET 1                // InpPlanStart 0 on a real account: OBSERVE
#define CR_PLAN_FUTURE 2               // InpPlanStart still to come: OBSERVE
#define CR_SEND_OK 0
#define CR_SEND_FAIL 1
#define CR_SEND_UNKNOWN 2

// ---- NYSE day kinds (CR_Clock ClkNyse)
#define CR_NYSE_OPEN 0
#define CR_NYSE_FULL 1
#define CR_NYSE_HALF 2

// ---- magic numbers (SPEC 2.3)
#define CR_MAGIC_BASE 20261200         // sleeve positions: 20261200 + id, ids 1..89
#define CR_MAGIC_MARK 20261290         // the disaster guard's own mark (SPEC 6.2)
#define CR_MAGIC_HANDS 20261110        // the old hands (never touched)

// ---- driver states (CR_Main)
#define CR_ST_INIT 0
#define CR_ST_WAIT 1
#define CR_ST_REPLAY 2
#define CR_ST_LIVE 3
#define CR_ST_HALT 4
#define CR_ST_RECON 5                  // (d) reconcile, retried each pass without a new replay

// ---- journal events (SPEC 2.6); names in CR_EV_NAME below, same order
#define CR_EV_INIT 0
#define CR_EV_SELFTEST 1
#define CR_EV_PLAN 2
#define CR_EV_READY 3
#define CR_EV_NOTREADY 4
#define CR_EV_DEC 5
#define CR_EV_PFILL 6
#define CR_EV_PEXIT 7
#define CR_EV_PSTOP 8
#define CR_EV_PREVISE 9
#define CR_EV_PVOID 10
#define CR_EV_PREFUSE 11
#define CR_EV_HOLD 12
#define CR_EV_SIZE 13
#define CR_EV_SEND 14
#define CR_EV_FILL 15
#define CR_EV_SLMOD 16
#define CR_EV_SLFIX 17
#define CR_EV_CLOSE 18
#define CR_EV_REFUSED 19
#define CR_EV_ADOPT 20
#define CR_EV_ORPHAN 21
#define CR_EV_DUP 22
#define CR_EV_MISSED 23
#define CR_EV_LATEBAR 24
#define CR_EV_GAP 25
#define CR_EV_REBUILD 26
#define CR_EV_SETTLE 27
#define CR_EV_CLOCK 28
#define CR_EV_STOP 29
#define CR_EV_GUARD 30
#define CR_EV_MARK 31
#define CR_EV_LOCK 32
#define CR_EV_COST 33
#define CR_EV_TAKEOVER 34
#define CR_EV_WATCH 35
#define CR_EV_ERROR 36
#define CR_EV_AGG 37                   // daily aggregate counts (bars fed per symbol, events)
#define CR_EV_DAY 38                   // daily summary
#define CR_EV_BAR 39                   // debug build only: one line per fed bar
#define CR_EV_N 40

string CR_EV_NAME[CR_EV_N] = {"INIT", "SELFTEST", "PLAN", "READY", "NOTREADY", "DEC", "PFILL", "PEXIT", "PSTOP", "PREVISE",
                              "PVOID", "PREFUSE", "HOLD", "SIZE", "SEND", "FILL", "SLMOD", "SLFIX", "CLOSE", "REFUSED",
                              "ADOPT", "ORPHAN", "DUP", "MISSED", "LATEBAR", "GAP", "REBUILD", "SETTLE", "CLOCK", "STOP",
                              "GUARD", "MARK", "LOCK", "COST", "TAKEOVER", "WATCH", "ERROR", "AGG", "DAY", "BAR"};

//+------------------------------------------------------------------+
//| Structs (SPEC 2.4). No strings inside the structs that are       |
//| copied per bar or per order: they stay plain old data.           |
//+------------------------------------------------------------------+
// one kept closed M1 bar of one symbol, with the PAPER quotes (SPEC 2.2: bid - h, bid + s x point + h)
struct CrBar
  {
   datetime t;                         // UTC start
   int      sym;                       // symbol id
   double   bo, bh, bl, bc;            // paper bid open, high, low, close
   double   ao, ah, al, ac;            // paper ask open, high, low, close
   int      s_raw;                     // the broker's raw spread, points
  };

// an order of a rule for its paper chain (SPEC 2.4). "0 = none" for trail, be, target, target_dist, xh, x_sched.
struct CrOrder
  {
   int      sleeve;                    // sleeve index (0-based row of g_sl)
   long     oid;                       // decision x 100 + sleeve id
   int      side;                      // +1 / -1 (0 for OCO until the fill)
   int      etype;                     // CR_ET_*
   double   level;                     // stop / limit level (OCO: buy stop)
   double   level2;                    // OCO: sell stop
   datetime t_from, t_to;              // activation window: first kept bar starting inside [t_from, t_to]
   long     after_exit_of;             // activate on the first kept bar after the exit bar of this oid (before t_to)
   datetime expiry_excl;               // pending orders fill only on bars starting before this time
   double   stop;                      // absolute stop (0 = use stop_dist)
   double   stop_dist;                 // stop distance from the fill
   double   trail;                     // trailing distance
   double   be;                        // break-even trigger distance
   double   target;                    // absolute target
   double   target_dist;               // target distance from the fill
   datetime x_sched;                   // scheduled time exit x
   bool     x_gap;                     // the gap rule (gl.exit_index, 30 min) applies to x
   datetime xh;                        // hold extension exit (H2), 0 = none
   double   xh_r;                      // hold extension: ahead by at least xh_r x risk
   int      refuse;                    // CR_REF_*
   bool     void_le;                   // void when the exit bar does not follow the entry bar (brk72 wrapper)
   datetime dec;                       // decision time (UTC)
   int      group;                     // multi-leg group number (0 = none)
  };

// an exit asked by a rule: the open trade of order oid exits at the first kept bar inside [t_from, t_to]
struct CrExit
  {
   int      sleeve;
   long     oid;
   datetime t_from, t_to;
   datetime dec;
  };

// a decision record without an order (DEC line), e.g. a K1 skip
struct CrDec
  {
   int      sleeve;
   datetime dec;
   int      side;
   int      what;                      // CR_DEC_*
   double   v1, v2;
  };

// what a rule emits in one OnBar or OnMinute call
struct CrOut
  {
   int      n_ord;
   CrOrder  ord[CR_OUT_MAX];
   int      n_ex;
   CrExit   ex[CR_OUT_MAX];
   int      n_dec;
   CrDec    dec[CR_OUT_MAX];
  };

// a paper engine event (SPEC 2.5): PFILL, PEXIT, PSTOP, PREVISE, PVOID, PREFUSE, HOLD
struct CrPEvent
  {
   int      ev;                        // CR_EV_*
   int      sleeve;
   long     oid;
   int      side;
   datetime t;                         // lab time stamp: entry = fill bar start; exit = exit bar start (+60 s unless time)
   datetime bar;                       // start of the bar that produced the event
   double   px;                        // fill or exit price (paper)
   double   stop;                      // the stop after the event
   double   init_stop;                 // initial stop
   int      reason;                    // CR_R_* for exits
   datetime x;                         // scheduled exit after the event (HOLD: the extended one)
   int      s_raw;                     // raw spread of that bar
   double   s_paper;                   // paper spread of that bar (ao - bo)
  };

// the open trade of a sleeve as the paper sees it (follower, reconcile, LatestExit)
struct CrTrade
  {
   int      sleeve;
   long     oid;
   int      side;
   int      etype;
   datetime act_bar;                   // activation bar start
   datetime fill_bar;                  // fill bar start
   double   fill_px;
   double   init_stop;
   double   stop;                      // current stop
   bool     moved;                     // trail / break-even moved the stop
   datetime x_sched;
   bool     x_gap;
   bool     x_pending;                 // a gap exit waits for its barrier (the trade has not ended)
   datetime dec;
   int      group;
  };

// an order of the account (follower -> sizing -> broker), SPEC 4.1-4.3, 5
struct CrIntent
  {
   int      sleeve;
   long     oid;
   int      side;
   int      etype;                     // etype of the paper order
   datetime stamp;                     // UTC minute (market: activation minute; pending: fill bar)
   datetime send_until;                // stamp + 5 min
   double   paper_fill;                // paper fill price (pending orders; market: 0)
   double   stop;                      // absolute paper stop (0 = distance)
   double   stop_dist;
   double   quote;                     // raw quote at sizing: ask (long) / bid (short)
   double   r;                         // risk per unit used for sizing (SPEC 4.2)
   bool     late;                      // sized on max(paper risk, quote risk)
   double   lots;
   int      skip;                      // CR_SK_*
   double   budget;                    // money at risk sized (account currency)
   double   rate, m, f, B, P_in, unit, w;
   int      state;                     // CR_IS_*
   ulong    ticket;
  };

// one row of the symbol table (rows: CR_Registry RegInit)
struct CrSymInfo
  {
   string   base;                      // "XAUUSD"
   string   lab;                       // "xauusd"
   string   name;                      // the broker's name ("XAUUSD.r"), resolved at OnInit
   int      family;                    // CR_FAM_*
   int      digits;                    // live; harness 2
   double   point;                     // live; harness 0.01
   int      comm_pts;                  // round-trip commission in points (XAU: CR_XAU_COMM_PTS)
   double   h;                         // paper half commission, price units = comm_pts / 2 x point
   double   slip_mkt;                  // lab slippage, fraction of price (bps x 1e-4)
   double   slip_stop;
   int      depth_days;                // history replayed at start (SPEC 2.2)
   double   model_bp;                  // fp_costs.json spread in bp of the mid (COST line)
   bool     ok;                        // resolved and selected
  };

// one row of the sleeve table (rows: CR_Registry RegInit)
struct CrSleeveInfo
  {
   int      id;                        // 1..89 (magic = 20261200 + id)
   string   code;                      // "N30"
   string   lab;                       // lab sleeve name, sort key in byte order ("noise30_us100")
   int      kind;                      // CR_K_*
   int      slot;                      // index of the rule object inside its kind
   int      sym;                       // traded symbol
   int      sym2;                      // second symbol read (NQB: US100), -1 = none
   int      change;                    // CR_CH_* carried by this sleeve
   double   factor_on;                 // stake factor while the change is on (H2 0.750978, S0.75r 0.771793)
   int      refuse_on;                 // refusal while the change is on (CR_REF_*)
   bool     change_on;                 // resolved at OnInit by ChangeOn()
   bool     allowed;                   // code listed in InpSleeves (the others are paper only)
   long     magic;
  };

// the inputs and what OnInit derives from the account (filled by CR_Main from the inputs; tests set it directly)
struct CrConfig
  {
   bool     trade;                     // InpTrade
   datetime plan_start;                // InpPlanStart (server time; 0 = unset)
   string   risk_table;                // InpRiskTable
   double   stop_fall_pct;             // InpStopFallPct
   double   stop_arm_paid;             // InpStopArmPaid
   string   sleeves;                   // InpSleeves
   int      k1, h2, s075;              // InpK1, InpH2, InpS075: -1, 0, 1
   string   k1t;                       // InpK1T
   double   lock_stakes;               // InpDailyLockStakes
   int      friday_hhmm;               // InpFridayCloseHHMM
   string   closures;                  // InpExtraClosures
   bool     push;                      // InpPush
   bool     demo;                      // ACCOUNT_TRADE_MODE is DEMO or CONTEST
   bool     vps;                       // TERMINAL_VPS
   bool     tester;                    // MQL_TESTER
   bool     observer;                  // sends nothing at all (SPEC 4.9)
   bool     entries_off;               // InpTrade false on the VPS copy: no new entry, the rest runs
   bool     harness;                   // CR_HARNESS build
   bool     selftest_ok;               // self-test passed (trading blocked otherwise)
   string   script;                    // harness only: codes whose rule is replaced by CR_Rule_Script ("" = none)
   string   script_dir;                // harness only: folder of the script files under MQL5/Files
  };

// ---- the tables and the configuration (one instance each)
CrSymInfo    g_sym[CR_NSYM];
CrSleeveInfo g_sl[CR_MAX_SL];
int          g_nsl = 0;                // rows used in g_sl
CrConfig     g_cfg;

//+------------------------------------------------------------------+
//| Small helpers every module may use                               |
//+------------------------------------------------------------------+
double CrNaN() { return MathSqrt(-1.0); }
bool   CrFinite(const double x) { return MathIsValidNumber(x); }

// byte-order compare of two strings (stake.py:108 sorts sleeve names this way): <0, 0, >0
int CrStrCmp(const string a, const string b)
  {
   int na = StringLen(a), nb = StringLen(b);
   int n = (na < nb) ? na : nb;
   for(int i = 0; i < n; i++)
     {
      int ca = (int)StringGetCharacter(a, i), cb = (int)StringGetCharacter(b, i);
      if(ca != cb) return (ca < cb) ? -1 : 1;
     }
   if(na == nb) return 0;
   return (na < nb) ? -1 : 1;
  }

void CrOrderClear(CrOrder &o)
  {
   ZeroMemory(o);
   o.sleeve = -1;
   o.refuse = CR_REF_NONE;
  }

void CrOutClear(CrOut &out)
  {
   out.n_ord = 0;
   out.n_ex = 0;
   out.n_dec = 0;
  }

// add an order / exit / decision to a rule's output; false when CR_OUT_MAX is reached (the driver journals ERROR)
bool CrOutOrder(CrOut &out, const CrOrder &o)
  {
   if(out.n_ord >= CR_OUT_MAX) return false;
   out.ord[out.n_ord] = o;
   out.n_ord++;
   return true;
  }

bool CrOutExit(CrOut &out, const CrExit &e)
  {
   if(out.n_ex >= CR_OUT_MAX) return false;
   out.ex[out.n_ex] = e;
   out.n_ex++;
   return true;
  }

bool CrOutDec(CrOut &out, const CrDec &d)
  {
   if(out.n_dec >= CR_OUT_MAX) return false;
   out.dec[out.n_dec] = d;
   out.n_dec++;
   return true;
  }

// oid of a decision (SPEC 2.4): decision x 100 + sleeve id
long CrOid(const datetime dec, const int sleeve_id) { return (long)dec * 100 + sleeve_id; }

// sleeve index of a magic number, -1 when it is not a sleeve position of this robot
int CrSleeveOfMagic(const long magic)
  {
   for(int i = 0; i < g_nsl; i++)
      if(g_sl[i].magic == magic) return i;
   return -1;
  }

// sleeve index of a code ("N30"), -1 when unknown
int CrSleeveOfCode(const string code)
  {
   for(int i = 0; i < g_nsl; i++)
      if(g_sl[i].code == code) return i;
   return -1;
  }
#endif

// ==== end src/CR_Types.mqh
// ==== begin src/CR_Clock.mqh
//+------------------------------------------------------------------+
//| CR_Clock.mqh - time (SPEC 2.1). Owner: step A.                    |
//|                                                                  |
//| A rule-based clock: no table to keep up to date, any year from   |
//| 1970 to 2200. check/test_clock.py compares it with zoneinfo,     |
//| pont.server_to_utc, pandas BDay, trend.add_trading_days,         |
//| idxus_lib.us_holidays, stake.prepare and the in-sample bars.     |
//| Times are UTC seconds unless a name says otherwise. A wall-clock |
//| time (server, New York, London) is the seconds of that clock     |
//| read as if it were UTC, as MQL5 does with TimeTradeServer().     |
//| Every value is a time at or after 1970.                          |
//|                                                                  |
//| Summer time, UTC instants:                                       |
//|   US  2nd Sunday of March 07:00 to 1st Sunday of November 06:00  |
//|       (before 2007: 1st Sunday of April to last Sunday of        |
//|       October, at the same hours)                                |
//|   UK  last Sunday of March 01:00 to last Sunday of October 01:00 |
//| Server = New York + 7 h (FP Markets): UTC = server - 3 h if the  |
//| US is on summer time at (server - 3 h), else server - 2 h        |
//| (pont.py:37-43). Wall clock -> UTC: a time inside the spring gap |
//| (New York 02:00-02:59, London 01:00-01:59) is read on the winter |
//| clock, so it lands 1 h later on the summer clock (New York 02:30 |
//| -> 03:30 EDT); a time of the repeated autumn hour takes the      |
//| summer-time instant (the first one).                             |
//|                                                                  |
//| Known closures (New York clock; merged when they overlap or      |
//| touch, so that Good Friday and its weekend are one closure):     |
//|   XAU  Monday-Thursday 17:00-18:00; Friday 17:00 to Sunday 18:00;|
//|        the NYSE's observed Good Friday, Christmas and New Year:  |
//|        [day before 17:00, day 18:00); the other NYSE full        |
//|        holidays (not the special closures): [13:00, 18:00); the  |
//|        Friday after Thanksgiving and a Christmas Eve half day:   |
//|        [13:45, 18:00). July 3 half days and special closures     |
//|        (2018-12-05, 2025-01-09) are normal gold days.            |
//|   IDX  Monday-Thursday 16:15-18:00; Friday 16:15 to Sunday       |
//|        18:00. No holiday closure: no US100 rule holds a position |
//|        into one; CR_Bars masks the half days after 13:15.        |
//|   CRY  Friday 16:55 to Sunday 17:00 (server Friday 23:55 to      |
//|        Monday 00:00).                                            |
//|   plus the typed windows of InpExtraClosures (below).            |
//| The broker's own session ends are not known here: the follower   |
//| passes one to ClkRealExitMinute when it has it.                  |
//|                                                                  |
//| NYSE calendar: a port of idxus_lib.us_holidays (idxus_lib.py:    |
//| 53-83): full closures and 13:00 half days by rule for any year,  |
//| Juneteenth from 2022, the special closures 2018-12-05 and        |
//| 2025-01-09; then the typed NYSE and HALF entries, which win over |
//| the rules. Weekends are not listed: ClkNyse says OPEN for them.  |
//|                                                                  |
//| InpExtraClosures: entries separated by ';', each one of          |
//|   NYSE yyyy.mm.dd                   a full NYSE closure          |
//|   HALF yyyy.mm.dd                   an NYSE 13:00 half day       |
//|   XAU|IDX|CRY yyyy.mm.dd hh:mm-yyyy.mm.dd hh:mm                  |
//|                                     a closure window, New York   |
//| Spaces and tabs may be repeated; spaces around '-' are allowed;  |
//| empty entries are skipped. Refused: another kind, a date that    |
//| does not exist or lies outside 2000-2100, a NYSE or HALF date on |
//| a weekend, a window that does not end after it starts or lasts   |
//| more than 7 days, more than 64 entries. Typed NYSE and HALF      |
//| dates change ClkNyse only, not the gold closures (a day of       |
//| mourning is a normal gold day): a gold, US100 or crypto closure  |
//| is typed as a window. MetaTrader keeps at most 255 characters    |
//| of "InpExtraClosures=value": about 6 windows or 14 dates.        |
//|                                                                  |
//| API (the S0 signatures, kept):                                   |
//|   ClkInit(extra, err)            typed closures; false and err   |
//|                                  when an entry is refused. Call  |
//|                                  it at every OnInit (it resets   |
//|                                  the closure caches)             |
//|   ClkUsDst(utc) ClkUkDst(utc)    summer time in force            |
//|   ClkServerToUtc ClkUtcToServer  server = New York + 7 h         |
//|   ClkUtcToNy ClkNyToUtc          New York wall clock             |
//|   ClkUtcToLdn ClkLdnToUtc        London wall clock               |
//|   ClkDay ClkDow ClkMinOfDay ClkYear   on the time's own clock:   |
//|                                  00:00 of its date, 0 = Sunday,  |
//|                                  minute of the day, year         |
//|   ClkServerDay(utc)              server date 00:00 (server       |
//|                                  clock) = the 17:00-NY trading   |
//|                                  day (data.py:45-49)             |
//|   ClkServerWeek(utc)             server Monday 00:00 of the week |
//|                                  (stake.py:89-91, 131)           |
//|   ClkAddTradingDays(utc, n)      n business days later, at the   |
//|                                  same server time; a weekend     |
//|                                  start counts Monday as day 1    |
//|                                  (trend/strategy.py:107-111)     |
//|   ClkBusinessDays(date, n)       pandas BDay(n) on any clock, no |
//|                                  holidays, time of day kept; n   |
//|                                  may be negative (a weekend then |
//|                                  counts Friday as day 1)         |
//|   ClkNyse(ny_date)               CR_NYSE_OPEN / FULL / HALF      |
//|   ClkInClosure(fam, utc, c0, c1) true when utc lies in a known   |
//|                                  closure; [c0, c1) = the whole   |
//|                                  merged closure, UTC (0, 0 when  |
//|                                  false)                          |
//|   ClkRealExitMinute(x, fam, gap, fri_end_utc)  follower only:    |
//|                                  the minute at whose barrier the |
//|                                  real position closes for a time |
//|                                  exit x (see the function)       |
//|   ClkRuleOffset(utc)             server - UTC by the rule, s     |
//|   ClkStr(t)                      "YYYY.MM.DD HH:MM", own clock   |
//| Added by step A:                                                 |
//|   ClkNextClosure(fam, utc, c0, c1)  the known closure holding    |
//|                                  utc, else the first one after   |
//|                                  it (false when none within 256  |
//|                                  days)                           |
//| The other Clk* functions below are internal helpers.             |
//+------------------------------------------------------------------+
#ifndef CR_CLOCK_MQH
#define CR_CLOCK_MQH
// (already inlined: CR_Types.mqh)

#define CR_CLK_Y0 1970                 // first year of the year caches
#define CR_CLK_NY 231                  // years cached: 1970 to 2200 (another year is computed at each call)
#define CR_CLK_NY4 924                 // CR_CLK_NY x 4
#define CR_CLK_HMAX 20                 // NYSE dates kept per year (at most 12 full, 3 half and 1 special)
#define CR_CLK_NYS 232                 // CR_CLK_NY + 1: the last slot holds a year outside the cache
#define CR_CLK_NH 4640                 // CR_CLK_NYS x CR_CLK_HMAX
#define CR_CLK_MAXT 64                 // typed closures kept
#define CR_CLK_TMAXLEN 604800          // longest typed window: 7 days, in seconds
#define CR_CLK_SESS_MAX 43200          // a broker session end counts when at most 12 h before a known closure
// gold holiday closure of a NYSE date (SPEC 2.1), New York clock
#define CR_CLK_G_NONE 0
#define CR_CLK_G_LONG 1                // observed Good Friday, Christmas, New Year: [day before 17:00, day 18:00)
#define CR_CLK_G_SHORT 2               // the other full holidays, special closures excepted: [13:00, 18:00)
#define CR_CLK_G_1345 3                // the Friday after Thanksgiving, a Christmas Eve half day: [13:45, 18:00)

// ---- year caches (filled at first use; they do not depend on the inputs)
bool g_clk_dok[CR_CLK_NY] = {false};   // summer-time instants computed for the year
long g_clk_dst[CR_CLK_NY4] = {0};      // per year: US on, US off, UK on, UK off (UTC)
bool g_clk_hok[CR_CLK_NY] = {false};   // NYSE dates computed for the year
int  g_clk_hspare = -1;                // year held by the spare slot CR_CLK_NY (-1 = none)
int  g_clk_hn[CR_CLK_NYS] = {0};       // NYSE dates of the slot
long g_clk_hd[CR_CLK_NH] = {0};        // day number of the date (days since 1970-01-01)
int  g_clk_hk[CR_CLK_NH] = {0};        // CR_NYSE_FULL or CR_NYSE_HALF
int  g_clk_hg[CR_CLK_NH] = {0};        // CR_CLK_G_*

// ---- typed closures (InpExtraClosures, ClkInit)
int      g_clk_nt = 0;
int      g_clk_tk[CR_CLK_MAXT];        // 0 NYSE, 1 HALF, 2 window
int      g_clk_tf[CR_CLK_MAXT];        // family of a window (-1 otherwise)
long     g_clk_tday[CR_CLK_MAXT];      // NYSE / HALF: day number of the New York date (-1 otherwise)
datetime g_clk_ta[CR_CLK_MAXT];        // window [ta, tb), UTC
datetime g_clk_tb[CR_CLK_MAXT];

// ---- closures of one family around a time (UTC), sorted and merged by ClkWorkBuild
datetime g_clk_wa[];
datetime g_clk_wb[];
int      g_clk_wn = 0;

// ---- segment cache, two slots per family (slot = 2 x family + k): a closure [sa, sb) (si = true), or a gap [sa, sb)
// ---- between closures followed by the closure [sna, snb) (0, 0: none found)
bool     g_clk_sv[6] = {false};
bool     g_clk_si[6] = {false};
datetime g_clk_sa[6] = {0};
datetime g_clk_sb[6] = {0};
datetime g_clk_sna[6] = {0};
datetime g_clk_snb[6] = {0};
int      g_clk_slast[3] = {0};         // slot (0 or 1) of the family used last; the other one is replaced

//+------------------------------------------------------------------+
//| Calendar arithmetic (proleptic Gregorian, H. Hinnant's formulas) |
//+------------------------------------------------------------------+
// day number (days since 1970-01-01) of a calendar date
long ClkDaysFromCivil(const int y, const int m, const int d)
  {
   long yy = (long)y - ((m <= 2) ? 1 : 0);
   long era = ((yy >= 0) ? yy : yy - 399) / 400;
   long yoe = yy - era * 400;
   long mp = (m > 2) ? m - 3 : m + 9;
   long doy = (153 * mp + 2) / 5 + d - 1;
   long doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
   return era * 146097 + doe - 719468;
  }

// calendar date of a day number
void ClkCivil(const long day_no, int &y, int &m, int &d)
  {
   long z = day_no + 719468;
   long era = ((z >= 0) ? z : z - 146096) / 146097;
   long doe = z - era * 146097;
   long yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
   long doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
   long mp = (5 * doy + 2) / 153;
   d = (int)(doy - (153 * mp + 2) / 5 + 1);
   m = (int)((mp < 10) ? mp + 3 : mp - 9);
   y = (int)(yoe + era * 400 + ((m <= 2) ? 1 : 0));
  }

// day number of a time, on its own clock (floor division)
long ClkDayNo(const datetime t)
  {
   long s = (long)t;
   long q = s / 86400;
   if(s % 86400 < 0) q--;
   return q;
  }

// day of the week of a day number: 0 = Sunday ... 6 = Saturday (1970-01-01 was a Thursday)
int ClkDowOfDay(const long day_no) { return (int)(((day_no + 4) % 7 + 7) % 7); }

int ClkMonthDays(const int y, const int m)
  {
   long next_first = (m == 12) ? ClkDaysFromCivil(y + 1, 1, 1) : ClkDaysFromCivil(y, m + 1, 1);
   return (int)(next_first - ClkDaysFromCivil(y, m, 1));
  }

// day number of the n-th weekday wd (0 = Sunday ... 6 = Saturday) of a month; n = -1: the last one
long ClkNthWeekday(const int y, const int m, const int wd, const int n)
  {
   if(n < 0)
     {
      long last_day = ((m == 12) ? ClkDaysFromCivil(y + 1, 1, 1) : ClkDaysFromCivil(y, m + 1, 1)) - 1;
      return last_day - (ClkDowOfDay(last_day) - wd + 7) % 7;
     }
   long first = ClkDaysFromCivil(y, m, 1);
   return first + (wd - ClkDowOfDay(first) + 7) % 7 + 7 * (n - 1);
  }

//+------------------------------------------------------------------+
//| The time's own clock                                             |
//+------------------------------------------------------------------+
int ClkYear(const datetime t)
  {
   int y = 0, m = 0, d = 0;
   ClkCivil(ClkDayNo(t), y, m, d);
   return y;
  }

datetime ClkDay(const datetime t) { return (datetime)(ClkDayNo(t) * 86400); }
int      ClkDow(const datetime t) { return ClkDowOfDay(ClkDayNo(t)); }
int      ClkMinOfDay(const datetime t) { return (int)(((long)t - ClkDayNo(t) * 86400) / 60); }

//+------------------------------------------------------------------+
//| Summer time and the three clocks                                 |
//+------------------------------------------------------------------+
// summer-time instants of a year, UTC
void ClkDstCompute(const int y, long &us_on, long &us_off, long &uk_on, long &uk_off)
  {
   if(y >= 2007)
     {
      us_on = ClkNthWeekday(y, 3, 0, 2) * 86400 + 7 * 3600;
      us_off = ClkNthWeekday(y, 11, 0, 1) * 86400 + 6 * 3600;
     }
   else
     {
      us_on = ClkNthWeekday(y, 4, 0, 1) * 86400 + 7 * 3600;
      us_off = ClkNthWeekday(y, 10, 0, -1) * 86400 + 6 * 3600;
     }
   uk_on = ClkNthWeekday(y, 3, 0, -1) * 86400 + 3600;
   uk_off = ClkNthWeekday(y, 10, 0, -1) * 86400 + 3600;
  }

void ClkDstYear(const int y, long &us_on, long &us_off, long &uk_on, long &uk_off)
  {
   int k = y - CR_CLK_Y0;
   if(k < 0 || k >= CR_CLK_NY)
     {
      ClkDstCompute(y, us_on, us_off, uk_on, uk_off);
      return;
     }
   if(!g_clk_dok[k])
     {
      long a = 0, b = 0, c = 0, e = 0;
      ClkDstCompute(y, a, b, c, e);
      g_clk_dst[4 * k] = a;
      g_clk_dst[4 * k + 1] = b;
      g_clk_dst[4 * k + 2] = c;
      g_clk_dst[4 * k + 3] = e;
      g_clk_dok[k] = true;
     }
   us_on = g_clk_dst[4 * k];
   us_off = g_clk_dst[4 * k + 1];
   uk_on = g_clk_dst[4 * k + 2];
   uk_off = g_clk_dst[4 * k + 3];
  }

bool ClkUsDst(const datetime utc)
  {
   long a = 0, b = 0, c = 0, e = 0;
   ClkDstYear(ClkYear(utc), a, b, c, e);
   return (long)utc >= a && (long)utc < b;
  }

bool ClkUkDst(const datetime utc)
  {
   long a = 0, b = 0, c = 0, e = 0;
   ClkDstYear(ClkYear(utc), a, b, c, e);
   return (long)utc >= c && (long)utc < e;
  }

datetime ClkServerToUtc(const datetime srv)
  {
   datetime u3 = srv - 3 * 3600;
   return ClkUsDst(u3) ? u3 : u3 + 3600;
  }

datetime ClkUtcToServer(const datetime utc) { return utc + (ClkUsDst(utc) ? 3 * 3600 : 2 * 3600); }
datetime ClkUtcToNy(const datetime utc) { return ClkUtcToServer(utc) - 7 * 3600; }
datetime ClkNyToUtc(const datetime ny) { return ClkServerToUtc(ny + 7 * 3600); }
datetime ClkUtcToLdn(const datetime utc) { return utc + (ClkUkDst(utc) ? 3600 : 0); }

datetime ClkLdnToUtc(const datetime ldn)
  {
   datetime u = ldn - 3600;                       // the summer-time reading
   return ClkUkDst(u) ? u : ldn;
  }

datetime ClkServerDay(const datetime utc) { return ClkDay(ClkUtcToServer(utc)); }

datetime ClkServerWeek(const datetime utc)
  {
   long dn = ClkDayNo(ClkUtcToServer(utc));
   return (datetime)((dn - (ClkDowOfDay(dn) + 6) % 7) * 86400);
  }

long ClkRuleOffset(const datetime utc) { return ClkUsDst(utc) ? 3 * 3600 : 2 * 3600; }

//+------------------------------------------------------------------+
//| Business days (pandas BDay, no holidays)                         |
//+------------------------------------------------------------------+
// n business days after a day number. A weekend day first rolls to Monday (n >= 0) or to Friday (n < 0), and that
// day counts as the first one moved (pandas: Saturday + BDay(1) = Monday, Saturday + BDay(-1) = Friday, + BDay(0) =
// Monday)
long ClkBDayNo(const long day_no, const int n)
  {
   long d = day_no;
   int k = n;
   int w = ClkDowOfDay(d);
   if(w == 6 || w == 0)
     {
      if(k >= 0)
        {
         d += (w == 6) ? 2 : 1;
         if(k > 0) k--;
        }
      else
        {
         d -= (w == 6) ? 1 : 2;
         k++;
        }
     }
   while(k > 0)
     {
      d++;
      w = ClkDowOfDay(d);
      if(w != 0 && w != 6) k--;
     }
   while(k < 0)
     {
      d--;
      w = ClkDowOfDay(d);
      if(w != 0 && w != 6) k++;
     }
   return d;
  }

datetime ClkBusinessDays(const datetime date, const int n)
  {
   long dn = ClkDayNo(date);
   return (datetime)((long)date + (ClkBDayNo(dn, n) - dn) * 86400);
  }

// trend/strategy.py:107-111: the server date-time (New York + 7 h) + BDay(n), back to UTC on the New York clock. The
// result is never in a summer-time gap or repeated hour: it lies between 17:00 New York the day before a weekday and
// 17:00 on that weekday, and New York changes clocks on Sundays at 02:00.
datetime ClkAddTradingDays(const datetime utc, const int n)
  {
   datetime srv = ClkUtcToServer(utc);
   long dn = ClkDayNo(srv);
   return ClkServerToUtc((datetime)((long)srv + (ClkBDayNo(dn, n) - dn) * 86400));
  }

//+------------------------------------------------------------------+
//| NYSE calendar (port of idxus_lib.us_holidays)                    |
//+------------------------------------------------------------------+
// Easter Sunday (idxus_lib._easter: the anonymous Gregorian algorithm)
long ClkEaster(const int y)
  {
   int a = y % 19, b = y / 100, c = y % 100;
   int d = b / 4, e = b % 4;
   int f = (b + 8) / 25;
   int g = (b - f + 1) / 3;
   int h = (19 * a + b - d - g + 15) % 30;
   int i = c / 4, k = c % 4;
   int l = (32 + 2 * e + 2 * i - h - k) % 7;
   int m = (a + 11 * h + 22 * l) / 451;
   int mo = (h + l - 7 * m + 114) / 31;
   int da = (h + l - 7 * m + 114) % 31 + 1;
   return ClkDaysFromCivil(y, mo, da);
  }

// NYSE rule: a Saturday holiday is observed on the Friday before, a Sunday one on the Monday after
long ClkObserved(const long day_no)
  {
   int w = ClkDowOfDay(day_no);
   if(w == 6) return day_no - 1;
   if(w == 0) return day_no + 1;
   return day_no;
  }

// adds a date to a year slot. A date already listed keeps its kind ("half -= full"); a special closure on a rule
// holiday makes that holiday a normal gold day unless it is a long closure (idxus_lib.py:74, gen_dbl.calendars)
void ClkHolAdd(const int slot, const long day_no, const int kind, const int gold, const bool special)
  {
   int base = slot * CR_CLK_HMAX;
   int n = g_clk_hn[slot];
   for(int i = 0; i < n; i++)
      if(g_clk_hd[base + i] == day_no)
        {
         if(special && g_clk_hg[base + i] == CR_CLK_G_SHORT) g_clk_hg[base + i] = CR_CLK_G_NONE;
         return;
        }
   if(n >= CR_CLK_HMAX) return;
   g_clk_hd[base + n] = day_no;
   g_clk_hk[base + n] = kind;
   g_clk_hg[base + n] = gold;
   g_clk_hn[slot] = n + 1;
  }

void ClkHolBuild(const int slot, const int y)
  {
   g_clk_hn[slot] = 0;
   long jan1 = ClkDaysFromCivil(y, 1, 1);
   int w1 = ClkDowOfDay(jan1);
   if(w1 == 0) ClkHolAdd(slot, jan1 + 1, CR_NYSE_FULL, CR_CLK_G_LONG, false);            // New Year on a Sunday: Monday
   else if(w1 != 6) ClkHolAdd(slot, jan1, CR_NYSE_FULL, CR_CLK_G_LONG, false);           // (a Saturday one is not observed)
   ClkHolAdd(slot, ClkNthWeekday(y, 1, 1, 3), CR_NYSE_FULL, CR_CLK_G_SHORT, false);      // Martin Luther King
   ClkHolAdd(slot, ClkNthWeekday(y, 2, 1, 3), CR_NYSE_FULL, CR_CLK_G_SHORT, false);      // Presidents' day
   ClkHolAdd(slot, ClkEaster(y) - 2, CR_NYSE_FULL, CR_CLK_G_LONG, false);                // Good Friday
   ClkHolAdd(slot, ClkNthWeekday(y, 5, 1, -1), CR_NYSE_FULL, CR_CLK_G_SHORT, false);     // Memorial day
   if(y >= 2022) ClkHolAdd(slot, ClkObserved(ClkDaysFromCivil(y, 6, 19)), CR_NYSE_FULL, CR_CLK_G_SHORT, false);   // Juneteenth
   ClkHolAdd(slot, ClkObserved(ClkDaysFromCivil(y, 7, 4)), CR_NYSE_FULL, CR_CLK_G_SHORT, false);
   ClkHolAdd(slot, ClkNthWeekday(y, 9, 1, 1), CR_NYSE_FULL, CR_CLK_G_SHORT, false);      // Labor day
   long tg = ClkNthWeekday(y, 11, 4, 4);                                                  // Thanksgiving
   ClkHolAdd(slot, tg, CR_NYSE_FULL, CR_CLK_G_SHORT, false);
   ClkHolAdd(slot, ClkObserved(ClkDaysFromCivil(y, 12, 25)), CR_NYSE_FULL, CR_CLK_G_LONG, false);
   if(y == 2018) ClkHolAdd(slot, ClkDaysFromCivil(2018, 12, 5), CR_NYSE_FULL, CR_CLK_G_NONE, true);   // days of mourning
   if(y == 2025) ClkHolAdd(slot, ClkDaysFromCivil(2025, 1, 9), CR_NYSE_FULL, CR_CLK_G_NONE, true);
   ClkHolAdd(slot, tg + 1, CR_NYSE_HALF, CR_CLK_G_1345, false);                            // Friday after Thanksgiving
   long jul4 = ClkDaysFromCivil(y, 7, 4);
   int w4 = ClkDowOfDay(jul4);
   if(w4 >= 2 && w4 <= 5) ClkHolAdd(slot, jul4 - 1, CR_NYSE_HALF, CR_CLK_G_NONE, false);  // July 3 before a Tuesday-Friday July 4
   long dec24 = ClkDaysFromCivil(y, 12, 24);
   int w24 = ClkDowOfDay(dec24);
   if(w24 >= 1 && w24 <= 4) ClkHolAdd(slot, dec24, CR_NYSE_HALF, CR_CLK_G_1345, false);  // Christmas Eve, Monday-Thursday
  }

int ClkHolSlot(const int y)
  {
   int k = y - CR_CLK_Y0;
   if(k >= 0 && k < CR_CLK_NY)
     {
      if(!g_clk_hok[k])
        {
         ClkHolBuild(k, y);
         g_clk_hok[k] = true;
        }
      return k;
     }
   if(g_clk_hspare != y)
     {
      ClkHolBuild(CR_CLK_NY, y);
      g_clk_hspare = y;
     }
   return CR_CLK_NY;
  }

// the built-in NYSE kind of a New York date (day number), and its gold closure kind
int ClkHolKind(const long day_no, int &gold)
  {
   gold = CR_CLK_G_NONE;
   int y = 0, m = 0, d = 0;
   ClkCivil(day_no, y, m, d);
   int slot = ClkHolSlot(y);
   int base = slot * CR_CLK_HMAX;
   for(int i = 0; i < g_clk_hn[slot]; i++)
      if(g_clk_hd[base + i] == day_no)
        {
         gold = g_clk_hg[base + i];
         return g_clk_hk[base + i];
        }
   return CR_NYSE_OPEN;
  }

int ClkNyse(const datetime ny_date)
  {
   long dn = ClkDayNo(ny_date);
   int typed = CR_NYSE_OPEN;
   for(int i = 0; i < g_clk_nt; i++)
     {
      if(g_clk_tday[i] != dn) continue;
      if(g_clk_tk[i] == 0) typed = CR_NYSE_FULL;
      else if(g_clk_tk[i] == 1 && typed == CR_NYSE_OPEN) typed = CR_NYSE_HALF;
     }
   if(typed != CR_NYSE_OPEN) return typed;
   int gold = 0;
   return ClkHolKind(dn, gold);
  }

//+------------------------------------------------------------------+
//| Known closures                                                   |
//+------------------------------------------------------------------+
void ClkWorkPut(const datetime a, const datetime b)
  {
   if(b <= a) return;
   if(g_clk_wn >= ArraySize(g_clk_wa))
     {
      int cap = g_clk_wn + 64;
      if(ArrayResize(g_clk_wa, cap) != cap) return;
      if(ArrayResize(g_clk_wb, cap) != cap) return;
     }
   g_clk_wa[g_clk_wn] = a;
   g_clk_wb[g_clk_wn] = b;
   g_clk_wn++;
  }

// a closure given on the New York clock
void ClkWorkPutNy(const datetime ny0, const datetime ny1) { ClkWorkPut(ClkNyToUtc(ny0), ClkNyToUtc(ny1)); }

// the built-in closures that a New York date (day number) brings
void ClkDayClosures(const int fam, const long day_no)
  {
   datetime d = (datetime)(day_no * 86400);       // 00:00 of the New York date, New York clock
   int w = ClkDowOfDay(day_no);
   if(fam == CR_FAM_XAU)
     {
      if(w >= 1 && w <= 4) ClkWorkPutNy(d + 17 * 3600, d + 18 * 3600);
      if(w == 5) ClkWorkPutNy(d + 17 * 3600, d + 2 * 86400 + 18 * 3600);
      int g = CR_CLK_G_NONE;
      if(ClkHolKind(day_no, g) != CR_NYSE_OPEN)
        {
         if(g == CR_CLK_G_LONG) ClkWorkPutNy(d - 86400 + 17 * 3600, d + 18 * 3600);
         if(g == CR_CLK_G_SHORT) ClkWorkPutNy(d + 13 * 3600, d + 18 * 3600);
         if(g == CR_CLK_G_1345) ClkWorkPutNy(d + 13 * 3600 + 45 * 60, d + 18 * 3600);
        }
     }
   else if(fam == CR_FAM_IDX)
     {
      if(w >= 1 && w <= 4) ClkWorkPutNy(d + 16 * 3600 + 15 * 60, d + 18 * 3600);
      if(w == 5) ClkWorkPutNy(d + 16 * 3600 + 15 * 60, d + 2 * 86400 + 18 * 3600);
     }
   else if(fam == CR_FAM_CRY)
     {
      if(w == 5) ClkWorkPutNy(d + 16 * 3600 + 55 * 60, d + 2 * 86400 + 17 * 3600);
     }
  }

// every closure of a family that overlaps [lo, hi), UTC, sorted by start, overlapping or touching ones merged. A
// date brings closures from 17:00 the day before to 18:00 two days after, so the dates read cover every overlap.
void ClkWorkBuild(const int fam, const datetime lo, const datetime hi)
  {
   g_clk_wn = 0;
   long d0 = ClkDayNo(ClkUtcToNy(lo)) - 3, d1 = ClkDayNo(ClkUtcToNy(hi)) + 1;
   for(long dn = d0; dn <= d1; dn++) ClkDayClosures(fam, dn);
   for(int i = 0; i < g_clk_nt; i++)
      if(g_clk_tk[i] == 2 && g_clk_tf[i] == fam && g_clk_tb[i] > lo && g_clk_ta[i] < hi) ClkWorkPut(g_clk_ta[i], g_clk_tb[i]);
   for(int i = 1; i < g_clk_wn; i++)              // insertion sort by start (the list is nearly sorted)
     {
      datetime a = g_clk_wa[i], b = g_clk_wb[i];
      int j = i - 1;
      while(j >= 0 && g_clk_wa[j] > a)
        {
         g_clk_wa[j + 1] = g_clk_wa[j];
         g_clk_wb[j + 1] = g_clk_wb[j];
         j--;
        }
      g_clk_wa[j + 1] = a;
      g_clk_wb[j + 1] = b;
     }
   int m = 0;
   for(int i = 0; i < g_clk_wn; i++)
     {
      if(m > 0 && g_clk_wa[i] <= g_clk_wb[m - 1])
        {
         if(g_clk_wb[i] > g_clk_wb[m - 1]) g_clk_wb[m - 1] = g_clk_wb[i];
         continue;
        }
      g_clk_wa[m] = g_clk_wa[i];
      g_clk_wb[m] = g_clk_wb[i];
      m++;
     }
   g_clk_wn = m;
  }

// fills slot s with the segment holding t: its closure, or the gap and the next closure. The window [t - w, t + w)
// doubles until the answer lies at least one day inside it (typed windows may chain closures), at most 256 days.
void ClkSegCompute(const int fam, const datetime t, const int s)
  {
   long w = 8;
   for(int pass = 0; pass < 6; pass++)
     {
      datetime lo = (datetime)((long)t - w * 86400), hi = (datetime)((long)t + w * 86400);
      ClkWorkBuild(fam, lo, hi);
      int j = -1;                                 // last closure starting at or before t
      for(int i = 0; i < g_clk_wn; i++)
        {
         if(g_clk_wa[i] > t) break;
         j = i;
        }
      bool final_pass = (pass == 5);
      bool inside = (j >= 0 && t < g_clk_wb[j]);
      if(inside && (final_pass || (g_clk_wa[j] > lo + 86400 && g_clk_wb[j] < hi - 86400)))
        {
         g_clk_si[s] = true;
         g_clk_sa[s] = g_clk_wa[j];
         g_clk_sb[s] = g_clk_wb[j];
         g_clk_sna[s] = g_clk_wa[j];
         g_clk_snb[s] = g_clk_wb[j];
         return;
        }
      bool has_next = (j + 1 < g_clk_wn);
      if(!inside && (final_pass || (has_next && g_clk_wb[j + 1] < hi - 86400)))
        {
         g_clk_si[s] = false;
         g_clk_sa[s] = (j >= 0) ? g_clk_wb[j] : lo;
         g_clk_sb[s] = has_next ? g_clk_wa[j + 1] : hi;
         g_clk_sna[s] = has_next ? g_clk_wa[j + 1] : (datetime)0;
         g_clk_snb[s] = has_next ? g_clk_wb[j + 1] : (datetime)0;
         return;
        }
      w *= 2;
     }
  }

// the cache slot whose segment holds t (computed when neither slot of the family does)
int ClkSeg(const int fam, const datetime t)
  {
   int s0 = 2 * fam, s1 = 2 * fam + 1;
   if(g_clk_sv[s0] && t >= g_clk_sa[s0] && t < g_clk_sb[s0])
     {
      g_clk_slast[fam] = 0;
      return s0;
     }
   if(g_clk_sv[s1] && t >= g_clk_sa[s1] && t < g_clk_sb[s1])
     {
      g_clk_slast[fam] = 1;
      return s1;
     }
   int k = 1 - g_clk_slast[fam];
   int s = 2 * fam + k;
   ClkSegCompute(fam, t, s);
   g_clk_sv[s] = true;
   g_clk_slast[fam] = k;
   return s;
  }

bool ClkInClosure(const int family, const datetime utc, datetime &c0, datetime &c1)
  {
   c0 = 0;
   c1 = 0;
   if(family < CR_FAM_XAU || family > CR_FAM_CRY) return false;
   int s = ClkSeg(family, utc);
   if(!g_clk_si[s]) return false;
   c0 = g_clk_sa[s];
   c1 = g_clk_sb[s];
   return true;
  }

bool ClkNextClosure(const int family, const datetime utc, datetime &c0, datetime &c1)
  {
   c0 = 0;
   c1 = 0;
   if(family < CR_FAM_XAU || family > CR_FAM_CRY) return false;
   int s = ClkSeg(family, utc);
   if(g_clk_snb[s] <= 0) return false;
   c0 = g_clk_sna[s];
   c1 = g_clk_snb[s];
   return true;
  }

//+------------------------------------------------------------------+
//| The follower's exit minute (SPEC 2.1, 4.5)                       |
//+------------------------------------------------------------------+
// x: the paper's scheduled time exit (UTC); gap_rule: the rule's exit uses the gap rule (gl.exit_index, 30 min);
// fri_end_utc: the broker's session end before the closure x falls in or before (SymbolInfoSessionTrade), 0 when the
// follower has none; for crypto, the broker's Friday session end of x's week. Let [c0, c1) be the known closure
// holding x, else the next one. The closure starts at e0 = fri_end_utc when that is earlier than c0 by at most 12 h
// (an earlier broker session end wins), else at c0. Then:
//   gap rule and e0 <= x < c1 - 30 min                  -> e0 - 1 min (the last minute before the closure; the lab
//                                                          exits at the last bar before it, gl.exit_index)
//   crypto with fri_end_utc > 0, result in [e0 - 1 min, c1) -> e0 - 1 min (never after the broker's Friday
//                                                          session end - 1 min)
//   else x (an exit in the last 30 min of a closure waits for the reopening, as the lab's exit does)
// For a given x and session end it never changes (the closures are fixed after ClkInit): the follower may compute it
// once per trade, and again after a HOLD moves x.
datetime ClkRealExitMinute(const datetime x, const int family, const bool gap_rule, const datetime fri_end_utc)
  {
   datetime c0 = 0, c1 = 0;
   if(!ClkNextClosure(family, x, c0, c1)) return x;
   datetime e0 = c0;
   if(fri_end_utc > 0 && fri_end_utc < c0 && (long)c0 - (long)fri_end_utc <= CR_CLK_SESS_MAX) e0 = fri_end_utc;
   datetime r = x;
   if(gap_rule && x >= e0 && x < c1 - 30 * 60) r = e0 - 60;
   if(family == CR_FAM_CRY && fri_end_utc > 0 && r >= e0 - 60 && r < c1) r = e0 - 60;
   return r;
  }

//+------------------------------------------------------------------+
//| Typed closures (InpExtraClosures)                                |
//+------------------------------------------------------------------+
// the value of n decimal digits of s at pos, -1 when one is not a digit
int ClkDigits(const string s, const int pos, const int n)
  {
   int v = 0;
   for(int i = 0; i < n; i++)
     {
      int c = (int)StringGetCharacter(s, pos + i);
      if(c < '0' || c > '9') return -1;
      v = v * 10 + (c - '0');
     }
   return v;
  }

// "yyyy.mm.dd" at pos -> day number, -1 when it is not a date of 2000-2100
long ClkParseDate(const string s, const int pos)
  {
   if(StringGetCharacter(s, pos + 4) != '.' || StringGetCharacter(s, pos + 7) != '.') return -1;
   int y = ClkDigits(s, pos, 4), m = ClkDigits(s, pos + 5, 2), d = ClkDigits(s, pos + 8, 2);
   if(y < 2000 || y > 2100 || m < 1 || m > 12 || d < 1) return -1;
   if(d > ClkMonthDays(y, m)) return -1;
   return ClkDaysFromCivil(y, m, d);
  }

// "hh:mm" at pos -> seconds after 00:00, -1 when it does not parse
int ClkParseHhmm(const string s, const int pos)
  {
   if(StringGetCharacter(s, pos + 2) != ':') return -1;
   int h = ClkDigits(s, pos, 2), m = ClkDigits(s, pos + 3, 2);
   if(h < 0 || h > 23 || m < 0 || m > 59) return -1;
   return h * 3600 + m * 60;
  }

// one space between words, none around '-', no space or tab at either end
string ClkNormalize(const string s)
  {
   string out = "";
   bool blank = false;
   int n = StringLen(s);
   for(int i = 0; i < n; i++)
     {
      ushort c = StringGetCharacter(s, i);
      if(c == ' ' || c == '\t' || c == '\r' || c == '\n')
        {
         blank = true;
         continue;
        }
      int len = StringLen(out);
      if(blank && len > 0 && c != '-' && StringGetCharacter(out, len - 1) != '-') out = out + " ";
      blank = false;
      out = out + StringSubstr(s, i, 1);
     }
   return out;
  }

void ClkTypedAdd(const int kind, const int fam, const long day_no, const datetime a, const datetime b)
  {
   g_clk_tk[g_clk_nt] = kind;
   g_clk_tf[g_clk_nt] = fam;
   g_clk_tday[g_clk_nt] = day_no;
   g_clk_ta[g_clk_nt] = a;
   g_clk_tb[g_clk_nt] = b;
   g_clk_nt++;
  }

// one entry of InpExtraClosures; false and why when it is refused (an empty entry is accepted and adds nothing)
bool ClkParseEntry(const string raw, string &why)
  {
   why = "";
   string p = ClkNormalize(raw);
   if(p == "") return true;
   if(g_clk_nt >= CR_CLK_MAXT)
     {
      why = "more than 64 entries";
      return false;
     }
   string kind = StringSubstr(p, 0, 4);
   if(kind == "NYSE" || kind == "HALF")
     {
      long dn = -1;
      if(StringLen(p) == 15 && StringGetCharacter(p, 4) == ' ') dn = ClkParseDate(p, 5);
      if(dn < 0)
        {
         why = "expected '" + kind + " yyyy.mm.dd' with a date of 2000-2100";
         return false;
        }
      int w = ClkDowOfDay(dn);
      if(w == 0 || w == 6)
        {
         why = "the date is a Saturday or a Sunday";
         return false;
        }
      ClkTypedAdd((kind == "NYSE") ? 0 : 1, -1, dn, (datetime)0, (datetime)0);
      return true;
     }
   string f3 = StringSubstr(p, 0, 3);
   int fam = -1;
   if(f3 == "XAU") fam = CR_FAM_XAU;
   if(f3 == "IDX") fam = CR_FAM_IDX;
   if(f3 == "CRY") fam = CR_FAM_CRY;
   if(fam < 0)
     {
      why = "the kind must be NYSE, HALF, XAU, IDX or CRY";
      return false;
     }
   long d0 = -1, d1 = -1;                         // "XAU yyyy.mm.dd hh:mm-yyyy.mm.dd hh:mm"
   int m0 = -1, m1 = -1;
   if(StringLen(p) == 37 && StringGetCharacter(p, 3) == ' ' && StringGetCharacter(p, 14) == ' ' && StringGetCharacter(p, 20) == '-'
      && StringGetCharacter(p, 31) == ' ')
     {
      d0 = ClkParseDate(p, 4);
      m0 = ClkParseHhmm(p, 15);
      d1 = ClkParseDate(p, 21);
      m1 = ClkParseHhmm(p, 32);
     }
   if(d0 < 0 || d1 < 0 || m0 < 0 || m1 < 0)
     {
      why = "expected '" + f3 + " yyyy.mm.dd hh:mm-yyyy.mm.dd hh:mm' (New York clock, dates of 2000-2100)";
      return false;
     }
   datetime a = (datetime)(d0 * 86400 + m0), b = (datetime)(d1 * 86400 + m1);
   if(b <= a)
     {
      why = "the window does not end after it starts";
      return false;
     }
   if((long)b - (long)a > CR_CLK_TMAXLEN)
     {
      why = "the window lasts more than 7 days";
      return false;
     }
   ClkTypedAdd(2, fam, -1, ClkNyToUtc(a), ClkNyToUtc(b));
   return true;
  }

bool ClkInit(const string extra, string &err)
  {
   err = "";
   g_clk_nt = 0;
   for(int s = 0; s < 6; s++) g_clk_sv[s] = false;
   string e = extra;
   StringTrimLeft(e);
   StringTrimRight(e);
   if(e == "") return true;
   string part[];
   int n = StringSplit(e, ';', part);
   for(int i = 0; i < n; i++)
     {
      string why = "";
      if(!ClkParseEntry(part[i], why))
        {
         err = "InpExtraClosures: entry " + IntegerToString(i + 1) + " '" + part[i] + "': " + why;
         g_clk_nt = 0;
         return false;
        }
     }
   return true;
  }

string ClkStr(const datetime t) { return TimeToString(t, TIME_DATE | TIME_MINUTES); }
#endif

// ==== end src/CR_Clock.mqh
// ==== begin src/CR_Journal.mqh
//+------------------------------------------------------------------+
//| CR_Journal.mqh - journal and pushes (SPEC 2.6). Owner: S0.        |
//|                                                                  |
//| One line per event: CR|<utc>|<EVENT>|<code>|k=v|...              |
//|   utc   = lab time of the event, integer UTC seconds             |
//|   code  = sleeve code, symbol base name, or "-"                   |
//|   doubles are written with DoubleToString(x, -16): 17 digits,    |
//|   an exact round trip; booleans 0/1; times integer seconds.      |
//| Lines go to Print (live) and to MQL5/Files/ClaudeRobot/          |
//| <yyyymmdd>.log (server date; files older than 30 days removed).  |
//| Lines written while the history is replayed carry rp=1.          |
//| Pushes (French, ASCII): "Robot Claude : ..." with the hands'     |
//| limits (ClaudeMains.mq5:161-184): at most 2 a second and 5 a     |
//| minute, of which 2 are kept for urgent messages.                 |
//+------------------------------------------------------------------+
#ifndef CR_JOURNAL_MQH
#define CR_JOURNAL_MQH
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Clock.mqh)

#define CR_JRN_KEEP_DAYS 30

string   CR_JRN_DIR = "ClaudeRobot";   // MQL5/Files/ClaudeRobot (a variable: "a" + "b" of two literals is not C++)

int      g_jrn_h = INVALID_HANDLE;
datetime g_jrn_day = 0;                // server date of the open file
bool     g_jrn_print = true;           // also Print each line (the harness turns it off)
bool     g_jrn_file = true;            // write the daily file
long     g_jrn_lines = 0;
datetime g_push_sec = 0, g_push_min = 0;
int      g_push_n = 0, g_push_m = 0;
long     g_push_sent = 0, g_push_dropped = 0;
long     g_jrn_file_errors = 0;          // file calls that failed (the journal still goes to Print)

string CR_REASON_NAME[11] = {"stop", "target", "time", "trail", "eod", "nofill", "skip", "gap", "void", "refused", "rule"};

string JT(const datetime t) { return IntegerToString((long)t); }
string JD(const double x) { return DoubleToString(x, -16); }
string JI(const long v) { return IntegerToString(v); }
string JB(const bool b) { return b ? "1" : "0"; }
string KV(const string k, const string v) { return "|" + k + "=" + v; }
string KD(const string k, const double v) { return "|" + k + "=" + JD(v); }
string KI(const string k, const long v) { return "|" + k + "=" + JI(v); }
string KT(const string k, const datetime v) { return "|" + k + "=" + JT(v); }
string KB(const string k, const bool v) { return "|" + k + "=" + JB(v); }

string JrnReason(const int r)
  {
   if(r < 0 || r > 10) return "none";
   return CR_REASON_NAME[r];
  }

string JrnCode(const int sl)
  {
   if(sl < 0 || sl >= g_nsl) return "-";
   return g_sl[sl].code;
  }

string JrnSymCode(const int sym)
  {
   if(sym < 0 || sym >= CR_NSYM) return "-";
   return g_sym[sym].base;
  }

// yyyymmdd of a server date
string JrnDayName(const datetime srv_day)
  {
   MqlDateTime d;
   TimeToStruct(srv_day, d);
   return IntegerToString(d.year * 10000 + d.mon * 100 + d.day);
  }

// remove the daily files older than CR_JRN_KEEP_DAYS days (names are yyyymmdd.log)
void JrnPurge(const datetime srv_day)
  {
   if(g_cfg.harness) return;                      // the harness keeps the whole journal
   string limit = JrnDayName(srv_day - CR_JRN_KEEP_DAYS * 86400);
   string found = "";
   long h = FileFindFirst(CR_JRN_DIR + "\\*.log", found);
   if(h == INVALID_HANDLE) return;
   do
     {
      if(StringLen(found) == 12 && CrStrCmp(StringSubstr(found, 0, 8), limit) < 0)
        {
         bool gone = FileDelete(CR_JRN_DIR + "\\" + found);
         if(!gone) g_jrn_file_errors++;
        }
     }
   while(FileFindNext(h, found));
   FileFindClose(h);
  }

void JrnClose()
  {
   if(g_jrn_h != INVALID_HANDLE) FileClose(g_jrn_h);
   g_jrn_h = INVALID_HANDLE;
   g_jrn_day = 0;
  }

void JrnOpenDay(const datetime srv_day)
  {
   JrnClose();
   if(!g_jrn_file) return;
   bool made = FolderCreate(CR_JRN_DIR);
   if(!made) g_jrn_file_errors++;
   string path = CR_JRN_DIR + "\\" + JrnDayName(srv_day) + ".log";
   g_jrn_h = FileOpen(path, FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ);
   if(g_jrn_h == INVALID_HANDLE) g_jrn_file_errors++;
   else
     {
      bool at_end = FileSeek(g_jrn_h, 0, SEEK_END);
      if(!at_end) g_jrn_file_errors++;
     }
   g_jrn_day = srv_day;
   JrnPurge(srv_day);
  }

void JrnInit()
  {
   g_jrn_print = !g_cfg.harness;                  // the harness reads the files; Print would double them in its log
   g_jrn_lines = 0;
   g_push_sec = 0;
   g_push_min = 0;
   g_push_n = 0;
   g_push_m = 0;
   JrnOpenDay(ClkDay(TimeTradeServer()));
  }

// the one writer: CR|<utc>|<EVENT>|<code><kv>
void JrnAt(const datetime utc, const int ev, const string code, const string kv)
  {
   string name = (ev >= 0 && ev < CR_EV_N) ? CR_EV_NAME[ev] : "EV" + IntegerToString(ev);
   string line = "CR|" + JT(utc) + "|" + name + "|" + code + kv;
   datetime d = ClkDay(TimeTradeServer());
   if(g_jrn_file && d != g_jrn_day) JrnOpenDay(d);
   if(g_jrn_h != INVALID_HANDLE)
     {
      FileWriteString(g_jrn_h, line + "\n");
      if(g_cfg.tester || !g_cfg.harness) FileFlush(g_jrn_h);
     }
   if(g_jrn_print) Print(line);
   g_jrn_lines++;
  }

// an event stamped now (the server clock converted to UTC)
void Jrn(const int ev, const string code, const string kv) { JrnAt(ClkServerToUtc(TimeTradeServer()), ev, code, kv); }

// push notification with the hands' limits; returns false when it was dropped
bool JrnPush(const string msg, const bool urgent)
  {
   datetime now = TimeTradeServer();
   if(!g_cfg.push || g_cfg.tester) return true;
   if(now != g_push_sec)
     {
      g_push_sec = now;
      g_push_n = 0;
     }
   if(now - now % 60 != g_push_min)
     {
      g_push_min = now - now % 60;
      g_push_m = 0;
     }
   if(g_push_n >= 2 || g_push_m >= (urgent ? 5 : 3))
     {
      g_push_dropped++;
      return false;
     }
   g_push_n++;
   g_push_m++;
   bool sent = SendNotification("Robot Claude : " + msg);
   if(sent) g_push_sent++;
   else g_push_dropped++;
   return sent;
  }

// an ERROR line and an urgent push
void JrnError(const string code, const string what)
  {
   string w = what;
   StringReplace(w, "|", "/");
   Jrn(CR_EV_ERROR, code, KV("what", w));
   JrnPush("ERREUR " + code + " : " + w, true);
  }

// ---- the lines of the driver (CR_Main) -----------------------------------------------------------------------------
string JrnRp(const bool rp) { return rp ? "|rp=1" : ""; }

// DEC line of an order (every field: compare.py checks them against ref_lab.py's orders)
void JrnOrder(const CrOrder &o, const datetime when, const bool rp)
  {
   string kv = KV("what", "ord") + KI("oid", o.oid) + KI("side", o.side) + KI("et", o.etype) + KD("lv", o.level)
               + KD("lv2", o.level2) + KT("tf", o.t_from) + KT("tt", o.t_to) + KI("ax", o.after_exit_of)
               + KT("exp", o.expiry_excl) + KD("st", o.stop) + KD("sd", o.stop_dist) + KD("tr", o.trail) + KD("be", o.be)
               + KD("tg", o.target) + KD("td", o.target_dist) + KT("x", o.x_sched) + KB("xg", o.x_gap) + KT("xh", o.xh)
               + KD("xr", o.xh_r) + KI("ref", o.refuse) + KB("vle", o.void_le) + KI("grp", o.group) + KT("at", when);
   JrnAt(o.dec != 0 ? o.dec : when, CR_EV_DEC, JrnCode(o.sleeve), kv + JrnRp(rp));
  }

void JrnExitOrder(const CrExit &e, const datetime when, const bool rp)
  {
   string kv = KV("what", "exit") + KI("oid", e.oid) + KT("tf", e.t_from) + KT("tt", e.t_to) + KT("at", when);
   JrnAt(e.dec != 0 ? e.dec : when, CR_EV_DEC, JrnCode(e.sleeve), kv + JrnRp(rp));
  }

void JrnDecRec(const CrDec &d, const datetime when, const bool rp)
  {
   string what = (d.what == CR_DEC_SKIP_K1) ? "skip" : "info";
   string kv = KV("what", what) + KI("side", d.side) + KD("v1", d.v1) + KD("v2", d.v2) + KT("at", when);
   if(d.what == CR_DEC_SKIP_K1) kv = kv + KV("skip", "K1") + KD("riskbp", d.v1) + KD("T", d.v2);
   JrnAt(d.dec != 0 ? d.dec : when, CR_EV_DEC, JrnCode(d.sleeve), kv + JrnRp(rp));
  }

// PFILL, PEXIT, PSTOP, PREVISE, PVOID, PREFUSE, HOLD (SPEC 2.5)
void JrnPaper(const CrPEvent &e, const bool rp)
  {
   string kv = KI("oid", e.oid) + KI("side", e.side) + KT("bar", e.bar) + KD("px", e.px) + KD("stop", e.stop)
               + KD("st0", e.init_stop) + KT("x", e.x);
   if(e.ev == CR_EV_PEXIT || e.ev == CR_EV_PREVISE || e.ev == CR_EV_PVOID || e.ev == CR_EV_PREFUSE)
      kv = kv + KV("reason", JrnReason(e.reason));
   kv = kv + KI("s_raw", e.s_raw) + KD("s_paper", e.s_paper);
   JrnAt(e.t, e.ev, JrnCode(e.sleeve), kv + JrnRp(rp));
  }

// the bar dump of the debug build (CR_DEBUG): one line per fed bar
void JrnBar(const CrBar &b)
  {
   string kv = KD("bo", b.bo) + KD("bh", b.bh) + KD("bl", b.bl) + KD("bc", b.bc) + KD("ao", b.ao) + KD("ah", b.ah)
               + KD("al", b.al) + KD("ac", b.ac) + KI("s_raw", b.s_raw);
   JrnAt(b.t, CR_EV_BAR, JrnSymCode(b.sym), kv);
  }
#endif

// ==== end src/CR_Journal.mqh
// ==== begin src/CR_Math.mqh
//+------------------------------------------------------------------+
//| CR_Math.mqh - rolling primitives and bar aggregates. Owner: B.    |
//|                                                                  |
//| Each class reproduces one pandas call, step by step, so that a   |
//| rule fed the same series from the same start gets the same       |
//| doubles as the lab (T2 checks it against pandas 3.0.5 bit for    |
//| bit). Call Init before anything else; Clear forgets the values.  |
//| A value that is not a finite number (NaN, and also inf, which    |
//| pandas would count) is a missing value. The rules never push inf.|
//|                                                                  |
//|   CrRing        ring buffer of the last cap doubles              |
//|                   Get(0) = the oldest kept, Last(0) = the newest |
//|   CrRollSum     rolling(n, min_periods).sum() / .mean()          |
//|                   pandas roll_sum / roll_mean: Kahan sums with   |
//|                   separate add and remove compensations, the     |
//|                   "same value repeated" rule (GH#42064) and the  |
//|                   sign clamp of the mean. No periodic re-sum:    |
//|                   pandas never re-sums a fixed window, and a     |
//|                   re-sum would move the result off its bits.     |
//|   CrRollMax/Min rolling(n).max() / .min(), min_periods = n       |
//|   CrRollMedian  rolling(n, min_periods).median()                 |
//|   CrWilder      ewm(alpha = 1/n, adjust = False).mean(), NaN     |
//|                   gaps as pandas (the old weight keeps decaying) |
//|   CrMedian      median of the finite values among the first n    |
//|                   of an array (numpy / pandas median)            |
//|   CrAgg         one bucket of M1 bars at a time: bid and ask     |
//|                   aggregated apart (goldlab.data.bars) and the   |
//|                   extremes of the per-bar mids (crypto h1_bars)  |
//+------------------------------------------------------------------+
#ifndef CR_MATH_MQH
#define CR_MATH_MQH
// (already inlined: CR_Types.mqh)

//+------------------------------------------------------------------+
//| CrRing                                                           |
//+------------------------------------------------------------------+
class CrRing
  {
public:
   double   m_v[];
   int      m_cap;                        // capacity
   int      m_head;                       // slot of the oldest value
   int      m_n;                          // values kept (at most m_cap)

            CrRing() { m_cap = 0; m_head = 0; m_n = 0; }

   void Init(const int cap)
     {
      m_cap = (cap > 0) ? cap : 1;
      ArrayResize(m_v, m_cap);
      m_head = 0;
      m_n = 0;
     }

   void Clear()
     {
      m_head = 0;
      m_n = 0;
     }

   void Push(const double x)
     {
      if(m_cap <= 0) Init(1);
      if(m_n < m_cap)
        {
         m_v[(m_head + m_n) % m_cap] = x;
         m_n++;
        }
      else
        {
         m_v[m_head] = x;
         m_head = (m_head + 1) % m_cap;
        }
     }

   int Count() { return m_n; }

   // k = 0: the oldest value kept; NaN outside [0, Count())
   double Get(const int k)
     {
      if(k < 0 || k >= m_n) return CrNaN();
      return m_v[(m_head + k) % m_cap];
     }

   // k = 0: the newest value; NaN outside [0, Count())
   double Last(const int k)
     {
      if(k < 0 || k >= m_n) return CrNaN();
      return m_v[(m_head + m_n - 1 - k) % m_cap];
     }
  };

//+------------------------------------------------------------------+
//| CrRollSum: pandas roll_sum / roll_mean (window/aggregations.pyx) |
//| on a fixed window: the value leaving the window is removed first |
//| (its own Kahan compensation), then the new one is added.         |
//+------------------------------------------------------------------+
class CrRollSum
  {
public:
   double   m_win[];                      // the last n values pushed (missing ones included)
   int      m_n;                          // window
   int      m_minp;                       // min_periods
   int      m_k;                          // slot of the next value
   int      m_cnt;                        // values in the window (at most n)
   int      m_nobs;                       // valid values in the window
   int      m_neg;                        // negative valid values in the window (mean: sign clamp)
   double   m_sum;
   double   m_cadd;                       // compensation of the additions
   double   m_crem;                       // compensation of the removals
   long     m_same;                       // valid values in a row equal to m_prev (never lowered by a removal)
   double   m_prev;                       // the last valid value
   bool     m_prev_ok;

            CrRollSum() { m_n = 0; m_minp = 0; m_k = 0; m_cnt = 0; m_nobs = 0; m_neg = 0; m_sum = 0.0; m_cadd = 0.0; m_crem = 0.0;
                          m_same = 0; m_prev = 0.0; m_prev_ok = false; }

   void Clear()
     {
      m_k = 0;
      m_cnt = 0;
      m_nobs = 0;
      m_neg = 0;
      m_sum = 0.0;
      m_cadd = 0.0;
      m_crem = 0.0;
      m_same = 0;
      m_prev = 0.0;
      m_prev_ok = false;
     }

   void Init(const int n, const int min_periods)
     {
      m_n = (n > 0) ? n : 1;
      m_minp = (min_periods > 0) ? min_periods : 0;
      ArrayResize(m_win, m_n);
      Clear();
     }

   void Add(const double x)
     {
      if(!MathIsValidNumber(x)) return;
      m_nobs++;
      double y = x - m_cadd;
      double t = m_sum + y;
      m_cadd = t - m_sum - y;
      m_sum = t;
      if(x < 0.0) m_neg++;
      if(m_prev_ok && x == m_prev) m_same++;
      else m_same = 1;
      m_prev = x;
      m_prev_ok = true;
     }

   void Remove(const double x)
     {
      if(!MathIsValidNumber(x)) return;
      m_nobs--;
      double y = -x - m_crem;
      double t = m_sum + y;
      m_crem = t - m_sum - y;
      m_sum = t;
      if(x < 0.0) m_neg--;
     }

   // NaN (any value that is not finite) = a missing value: kept in the window, not counted
   void Push(const double x)
     {
      if(m_n <= 0) Init(1, 1);
      if(m_n == 1)
        {
         // pandas sets a window of one up afresh at every step (start >= previous end)
         m_nobs = 0;
         m_neg = 0;
         m_sum = 0.0;
         m_cadd = 0.0;
         m_crem = 0.0;
         m_same = 0;
         m_prev_ok = false;
        }
      else if(m_cnt == m_n) Remove(m_win[m_k]);
      Add(x);
      m_win[m_k] = x;
      m_k = (m_k + 1) % m_n;
      if(m_cnt < m_n) m_cnt++;
     }

   // pandas calc_sum: 0 for an empty window with min_periods 0; NaN below min_periods
   double Sum()
     {
      if(m_nobs == 0 && m_minp == 0) return 0.0;
      if(m_nobs < m_minp) return CrNaN();
      if(m_same >= m_nobs) return m_prev * m_nobs;
      return m_sum;
     }

   // pandas calc_mean: NaN for an empty window or below min_periods; a mean of one sign never shows the other sign
   double Mean()
     {
      if(m_nobs < m_minp || m_nobs <= 0) return CrNaN();
      double r = m_sum / (double)m_nobs;
      if(m_same >= m_nobs) r = m_prev;
      else if(m_neg == 0 && r < 0.0) r = 0.0;
      else if(m_neg == m_nobs && r > 0.0) r = 0.0;
      return r;
     }

   int Valid() { return m_nobs; }
  };

//+------------------------------------------------------------------+
//| rolling extreme of the valid values among the last n pushes      |
//| (a monotonic queue); NaN while fewer than min_periods are valid  |
//+------------------------------------------------------------------+
class CrRollExt
  {
public:
   bool     m_max;                        // true: maximum, false: minimum
   int      m_n;
   int      m_minp;
   long     m_seq;                        // values pushed so far
   uchar    m_ok[];                       // validity (1 / 0) of the last n values (ring, slot = seq % n); not bool[]:
                                          // the C++ harness cannot hold a dynamic bool array
   int      m_nobs;
   double   m_qv[];                       // queue values (ring of capacity n)
   long     m_qs[];                       // queue sequence numbers
   int      m_qh;                         // queue head slot
   int      m_qc;                         // queue length

            CrRollExt() { m_max = true; m_n = 0; m_minp = 0; m_seq = 0; m_nobs = 0; m_qh = 0; m_qc = 0; }

   void Clear()
     {
      m_seq = 0;
      m_nobs = 0;
      m_qh = 0;
      m_qc = 0;
     }

   void Init(const int n, const int min_periods, const bool is_max)
     {
      m_max = is_max;
      m_n = (n > 0) ? n : 1;
      m_minp = (min_periods > 0) ? min_periods : 0;
      ArrayResize(m_ok, m_n);
      ArrayResize(m_qv, m_n);
      ArrayResize(m_qs, m_n);
      Clear();
     }

   void Push(const double x)
     {
      if(m_n <= 0) Init(1, 1, m_max);
      int slot = (int)(m_seq % m_n);
      if(m_seq >= m_n && m_ok[slot] != 0) m_nobs--;     // the value leaving the window
      while(m_qc > 0 && m_qs[m_qh] <= m_seq - m_n)
        {
         m_qh = (m_qh + 1) % m_n;
         m_qc--;
        }
      bool ok = MathIsValidNumber(x);
      m_ok[slot] = (uchar)(ok ? 1 : 0);
      if(ok)
        {
         m_nobs++;
         while(m_qc > 0)
           {
            int back = (m_qh + m_qc - 1) % m_n;
            bool drop = m_max ? (x >= m_qv[back]) : (x <= m_qv[back]);
            if(!drop) break;
            m_qc--;
           }
         int at = (m_qh + m_qc) % m_n;
         m_qv[at] = x;
         m_qs[at] = m_seq;
         m_qc++;
        }
      m_seq++;
     }

   double Value()
     {
      if(m_qc <= 0 || m_nobs < m_minp) return CrNaN();
      return m_qv[m_qh];
     }

   int Valid() { return m_nobs; }
  };

class CrRollMax
  {
public:
   CrRollExt m_e;
   void   Init(const int n) { m_e.Init(n, n, true); }
   void   InitMinPeriods(const int n, const int min_periods) { m_e.Init(n, min_periods, true); }
   void   Clear() { m_e.Clear(); }
   void   Push(const double x) { m_e.Push(x); }
   double Value() { return m_e.Value(); }               // NaN until n valid values (min_periods = n)
   int    Valid() { return m_e.Valid(); }
  };

class CrRollMin
  {
public:
   CrRollExt m_e;
   void   Init(const int n) { m_e.Init(n, n, false); }
   void   InitMinPeriods(const int n, const int min_periods) { m_e.Init(n, min_periods, false); }
   void   Clear() { m_e.Clear(); }
   void   Push(const double x) { m_e.Push(x); }
   double Value() { return m_e.Value(); }
   int    Valid() { return m_e.Valid(); }
  };

//+------------------------------------------------------------------+
//| CrRollMedian: pandas roll_median_c (a sorted copy of the valid   |
//| values of the window instead of the skiplist; same values)       |
//+------------------------------------------------------------------+
class CrRollMedian
  {
public:
   double   m_win[];                      // the last n values pushed (ring)
   int      m_n;
   int      m_minp;
   int      m_k;                          // slot of the next value
   int      m_cnt;                        // values in the window
   double   m_s[];                        // the valid values of the window, sorted
   int      m_ns;

            CrRollMedian() { m_n = 0; m_minp = 0; m_k = 0; m_cnt = 0; m_ns = 0; }

   void Clear()
     {
      m_k = 0;
      m_cnt = 0;
      m_ns = 0;
     }

   void Init(const int n, const int min_periods)
     {
      m_n = (n > 0) ? n : 1;
      m_minp = (min_periods > 0) ? min_periods : 0;
      ArrayResize(m_win, m_n);
      ArrayResize(m_s, m_n);
      Clear();
     }

   // first slot whose value is >= x (binary search in m_s[0..m_ns))
   int Lower(const double x)
     {
      int lo = 0, hi = m_ns;
      while(lo < hi)
        {
         int mid = (lo + hi) / 2;
         if(m_s[mid] < x) lo = mid + 1;
         else hi = mid;
        }
      return lo;
     }

   void Insert(const double x)
     {
      int at = Lower(x);
      for(int i = m_ns; i > at; i--) m_s[i] = m_s[i - 1];
      m_s[at] = x;
      m_ns++;
     }

   void Erase(const double x)
     {
      int at = Lower(x);
      if(at >= m_ns || m_s[at] != x) return;            // never happens: x was inserted
      for(int i = at; i < m_ns - 1; i++) m_s[i] = m_s[i + 1];
      m_ns--;
     }

   void Push(const double x)
     {
      if(m_n <= 0) Init(1, 1);
      if(m_cnt == m_n)
        {
         double old = m_win[m_k];
         if(MathIsValidNumber(old)) Erase(old);
        }
      if(MathIsValidNumber(x)) Insert(x);
      m_win[m_k] = x;
      m_k = (m_k + 1) % m_n;
      if(m_cnt < m_n) m_cnt++;
     }

   double Value()
     {
      if(m_ns < m_minp || m_ns <= 0) return CrNaN();
      int h = m_ns / 2;
      if(m_ns % 2 == 1) return m_s[h];
      return (m_s[h] + m_s[h - 1]) / 2;
     }

   int Valid() { return m_ns; }
  };

//+------------------------------------------------------------------+
//| CrWilder: pandas ewm(alpha = 1/n, adjust = False).mean()         |
//| (window/aggregations.pyx ewm, ignore_na = False, min_periods 1). |
//| alpha goes through the centre of mass as in pandas: com = (1 -   |
//| a) / a (ewm.py get_center_of_mass), then alpha = 1 / (1 + com).  |
//| Known pandas 3.0.5 oddity: for com = 1 exactly (n = 2) its       |
//| result after a NaN differs from its own formula; no rule uses    |
//| n = 2.                                                           |
//+------------------------------------------------------------------+
class CrWilder
  {
public:
   int      m_n;
   double   m_alpha;
   double   m_owf;                        // old weight factor 1 - alpha
   double   m_w;                          // the weighted value
   bool     m_has;                        // m_w holds a value (an observation was seen)
   double   m_oldw;                       // weight of the old value
   long     m_count;                      // values pushed (missing ones included)
   long     m_nobs;                       // observations

            CrWilder() { m_n = 0; m_alpha = 1.0; m_owf = 0.0; m_w = 0.0; m_has = false; m_oldw = 1.0; m_count = 0; m_nobs = 0; }

   void Clear()
     {
      m_w = 0.0;
      m_has = false;
      m_oldw = 1.0;
      m_count = 0;
      m_nobs = 0;
     }

   void Init(const int n)
     {
      m_n = (n > 0) ? n : 1;
      double a0 = 1.0 / m_n;
      double com = (1.0 - a0) / a0;
      m_alpha = 1.0 / (1.0 + com);
      m_owf = 1.0 - m_alpha;
      Clear();
     }

   double Value()
     {
      if(m_nobs < 1) return CrNaN();
      return m_w;
     }

   // returns the new value (NaN until the first observation)
   double Push(const double x)
     {
      if(m_n <= 0) Init(1);
      bool obs = MathIsValidNumber(x);
      if(obs) m_nobs++;
      if(m_count == 0)
        {
         if(obs)
           {
            m_w = x;
            m_has = true;
           }
         m_oldw = 1.0;
        }
      else if(m_has)
        {
         m_oldw *= m_owf;                                // ignore_na = False: the old weight decays across a gap
         if(obs)
           {
            if(m_w != x)
              {
               m_w = m_oldw * m_w + m_alpha * x;
               m_w /= (m_oldw + m_alpha);
              }
            m_oldw = 1.0;                                // adjust = False
           }
        }
      else if(obs)
        {
         m_w = x;
         m_has = true;
        }
      m_count++;
      return Value();
     }

   int  Count() { return (int)m_count; }                // values pushed, NaN included (the pandas row number + 1)
   long Nobs() { return m_nobs; }                       // observations
  };

//+------------------------------------------------------------------+
//| median of the finite values among v[0..n) (numpy median: the     |
//| middle value, or the mean of the two middle ones); NaN if none   |
//+------------------------------------------------------------------+
double CrMedian(const double &v[], const int n)
  {
   int k = (n < ArraySize(v)) ? n : ArraySize(v);
   if(k <= 0) return CrNaN();
   double t[];
   ArrayResize(t, k);
   int m = 0;
   for(int i = 0; i < k; i++)
      if(MathIsValidNumber(v[i]))
        {
         t[m] = v[i];
         m++;
        }
   if(m == 0) return CrNaN();
   ArrayResize(t, m);
   ArraySort(t);
   int h = m / 2;
   if(m % 2 == 1) return t[h];
   return (t[h - 1] + t[h]) / 2;
  }

//+------------------------------------------------------------------+
//| CrAgg: one bucket of kept M1 bars at a time. The caller gives    |
//| each bar its bucket key (UTC grid: CrAggKey(t, 3600); the 17:00- |
//| NY trading day: ClkServerDay(t)) and decides when a bucket is    |
//| complete (Take), e.g. when the barrier reaches its end. Fields:  |
//|   bid and ask aggregated apart (first open, max high, min low,   |
//|   last close): goldlab.data.bars, mid h = (bh + ah) / 2;         |
//|   mh, ml = max / min of the per-bar mids (bh + ah) / 2 and       |
//|   (bl + al) / 2: crypto/strategy.py h1_bars;                     |
//|   n bars, the first and last bar starts (t_close = t_last + 60). |
//+------------------------------------------------------------------+
struct CrAggBar
  {
   datetime key;                          // bucket key given by the caller
   datetime t_first, t_last;              // start of the first and of the last bar
   int      n;                            // bars
   double   bo, bh, bl, bc;               // bid: first open, max high, min low, last close
   double   ao, ah, al, ac;               // ask, the same
   double   mh, ml;                       // max of (bh + ah) / 2, min of (bl + al) / 2 over the bars
  };

datetime CrAggKey(const datetime t, const int period_s) { return t - t % period_s; }

class CrAgg
  {
public:
   CrAggBar m_cur;
   bool     m_open;

            CrAgg() { m_open = false; }

   void Clear() { m_open = false; }

   void Start(const CrBar &b, const datetime key)
     {
      m_cur.key = key;
      m_cur.t_first = b.t;
      m_cur.t_last = b.t;
      m_cur.n = 1;
      m_cur.bo = b.bo;
      m_cur.bh = b.bh;
      m_cur.bl = b.bl;
      m_cur.bc = b.bc;
      m_cur.ao = b.ao;
      m_cur.ah = b.ah;
      m_cur.al = b.al;
      m_cur.ac = b.ac;
      m_cur.mh = (b.bh + b.ah) / 2;
      m_cur.ml = (b.bl + b.al) / 2;
      m_open = true;
     }

   // adds bar b (time order) to the bucket `key`; true when b opens a new bucket while another was open:
   // `done` is then the bucket that ended
   bool Add(const CrBar &b, const datetime key, CrAggBar &done)
     {
      if(!m_open)
        {
         Start(b, key);
         return false;
        }
      if(key != m_cur.key)
        {
         done = m_cur;
         Start(b, key);
         return true;
        }
      m_cur.t_last = b.t;
      m_cur.n++;
      if(b.bh > m_cur.bh) m_cur.bh = b.bh;
      if(b.bl < m_cur.bl) m_cur.bl = b.bl;
      if(b.ah > m_cur.ah) m_cur.ah = b.ah;
      if(b.al < m_cur.al) m_cur.al = b.al;
      m_cur.bc = b.bc;
      m_cur.ac = b.ac;
      double mh = (b.bh + b.ah) / 2, ml = (b.bl + b.al) / 2;
      if(mh > m_cur.mh) m_cur.mh = mh;
      if(ml < m_cur.ml) m_cur.ml = ml;
      return false;
     }

   // closes the open bucket (the caller knows it is complete); false when none is open
   bool Take(CrAggBar &done)
     {
      if(!m_open) return false;
      done = m_cur;
      m_open = false;
      return true;
     }

   // the open bucket, without closing it
   bool Peek(CrAggBar &cur)
     {
      if(!m_open) return false;
      cur = m_cur;
      return true;
     }
  };
#endif

// ==== end src/CR_Math.mqh
// ==== begin src/CR_Registry.mqh
//+------------------------------------------------------------------+
//| CR_Registry.mqh - symbol table, sleeve table, rule dispatch and   |
//| the change switches (SPEC 1, 2.3, 3.9). Owner: S0.                |
//|                                                                  |
//| Adding a rule = one rule file, one RegSleeve row below with its  |
//| case lines in the four Rules* functions, one reference entry in  |
//| check/ref_lab.py.                                                |
//+------------------------------------------------------------------+
#ifndef CR_REGISTRY_MQH
#define CR_REGISTRY_MQH
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Clock.mqh)
// (already inlined: CR_Journal.mqh)
// ==== begin src/CR_Rule_IdxUS.mqh
//+------------------------------------------------------------------+
//| CR_Rule_IdxUS.mqh - US100 rules N30 (noise30) and OC4 (ocm4),     |
//| their session grid and 17:00-NY daily ATR (SPEC 3). Owner: D.     |
//|                                                                  |
//| Lab code ported (lab/r2/tracks/idx_us):                          |
//|   grid       idxus_lib.py:113-158   daily ATR  idxus_lib.py:161- |
//|   noise30    strategy.py:216-257,   198, atr_at :192-198         |
//|              297-299                ocm4       strategy.py:127-  |
//|                                                168, 303-305      |
//| Both rules read the US100 kept bars only (paper quotes; US100 has|
//| no commission, so paper = broker quotes) and use MID prices      |
//| (bid + ask) / 2. New York wall clock; times are UTC inside.      |
//|                                                                  |
//| Session grid (CrIdxGrid; each rule owns one, fed the same bars). |
//|   Rows: the New York weekday dates that have at least one kept   |
//|   bar and are not NYSE full closures (idxus_lib.py:133-142). Half|
//|   days are rows; rows before 2014 count too (rolling windows).   |
//|   Tradable row: not a half day, date from 2014-01-01             |
//|   (strategy.py:66, 114-116).                                     |
//|   t0 = 09:30 New York of the row's date.                         |
//|   P(T) = mid close of the last kept bar starting before T, NaN   |
//|     when that bar started more than 11 min before T              |
//|     (stale_min 10: age <= 11, idxus_lib.py:151).                 |
//|   O = mid open of the first kept bar at or after 09:30 if it     |
//|     starts at 09:30 or 09:31, else NaN (idxus_lib.py:155).       |
//|   The bar of a decision at T (the lab's EI) = the first kept bar |
//|     in [T, T + 5 min] (late_min 5, idxus_lib.py:154): the        |
//|     activation window of the orders and exits.                   |
//|   A row's values (P at 09:34, at the 12 checks and at 16:00, O,  |
//|   the 09:30-09:33 bar count) are sampled at their minute; the    |
//|   row enters the rolling windows when the next New York date     |
//|   starts (the lab's shift(1): a row uses the rows before it).    |
//|                                                                  |
//| Daily ATR (idxus_lib.py:161-198): trading days = server dates    |
//|   (17:00 New York roll); h = max per-bar mid high, l = min       |
//|   per-bar mid low, c = mid close of the day's last bar; days with|
//|   fewer than 600 kept bars are dropped; TR = max(h - l, |h - pc|,|
//|   |l - pc|) with pc the previous KEPT day's close (np.fmax: the  |
//|   first TR is h - l); ATR = rolling(14, 14).mean of the TRs. A   |
//|   day's ATR is known from 17:00 New York of its date: the barrier|
//|   at that minute closes the day (every bar of it has been fed).  |
//|   Half days end with the P6 mask (13:15) as in the lab frames.   |
//|                                                                  |
//| N30 {lookback 14, first_min 600, step 30, last_min 930, exit_min |
//|   955, vm 1.0} (strategy.py:297-299), code :216-257.             |
//|   At each check T = 10:00, 10:30, ..., 15:30 of a tradable row   |
//|   with O finite: p = P(T), s = mean of |P/O - 1| at that check   |
//|   over the 14 previous rows (at least 9 values,                  |
//|   max(int(0.7 x 14), 1), :222); pc = the previous row's P(16:00);|
//|   hi = fmax(O, pc), lo = fmin(O, pc) (O when pc is NaN, :224-    |
//|   226); ub = hi x (1 + vm x s), lb = lo x (1 - vm x s). Void     |
//|   unless p and s are finite (:237). State pos (-1, 0, 1, blind to|
//|   paper stop-outs, 0 at the start of each row):                  |
//|     back inside (pos > 0 and p < ub, or pos < 0 and p > lb):     |
//|       CrExit of the held order, window [T, T + 5 min]; pos 0;    |
//|     then, pos 0 and p > ub (long) or p < lb (short): a market    |
//|       order, absolute stop hi (long) / lo (short), time exit     |
//|       15:55 with the gap rule; window [T, T + 5 min], or, after  |
//|       an exit at this check (a reversal, :243 'ei += 1'),        |
//|       after_exit_of that exit: the first kept bar after the      |
//|       exit's bar, if it starts before 15:55.                     |
//|   The lab skips a check whose bar does not precede the exit bar  |
//|   (ei >= xi, :237, 244): every order carries void_le, so the     |
//|   paper drops an entry whose 15:55 exit bar does not follow its  |
//|   activation bar (SPEC 2.5), as the lab never emits it; a CrExit |
//|   on such a bar exits exactly where the lab's xi does (that bar's|
//|   open, 'time'). In sample: 6 such checks (2014-12-31,           |
//|   2015-11-02..05, 2015-12-31).                                   |
//|   State commits when the check's bar is seen (the lab's EI >= 0):|
//|   a check whose window ends without a kept bar never happened    |
//|   (its exit and order are void in the paper too); the entry of a |
//|   reversal commits at the next kept bar if it starts before      |
//|   15:55. A decision still waiting at the next check cannot occur:|
//|   P(T') finite needs a bar after the waited one.                 |
//|                                                                  |
//| OC4 {n 4, stop atr, k 0.3, exit_min 955, size_min 1.0, size_win  |
//|   20, atr_n 14, sides both} (strategy.py:303-305), code :127-168.|
//|   At 09:34 of a tradable row: O and C = P(09:34) finite, at least|
//|   3 kept bars in [09:30, 09:34) (ceil(0.6 x 4), :145), move =    |
//|   C/O - 1, side = sign(move) != 0, |move| >= size_min x the      |
//|   median of |move| over the 20 previous rows (at least 10, :142),|
//|   ATR finite: market order [09:34, 09:39], stop_dist k x ATR,    |
//|   time exit 15:55 with the gap rule, void_le (the lab's xi > EI, |
//|   :154).                                                         |
//|                                                                  |
//| LatestExit (SPEC 4.8): 15:55 New York of the New York date of the|
//| open time (gap rule: the follower's RealExitMinute).             |
//| Harness diagnostics: -DCR_IDX_TRACE adds DEC info lines (N30:    |
//| p, s then ub, lb at each evaluated check; OC4: |move|, median    |
//| then ATR, bar count at 09:34).                                   |
//+------------------------------------------------------------------+
#ifndef CR_RULE_IDXUS_MQH
#define CR_RULE_IDXUS_MQH
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Clock.mqh)
// (already inlined: CR_Math.mqh)

// ---- the grid and the daily ATR (frozen: idxus_lib.py, strategy.py)
#define CR_IDX_OPEN_MIN 570            // 09:30 New York, the grid's t0 (idxus_lib.py:143)
#define CR_IDX_STALE_S 660             // P(T): last bar at most 11 min old (stale_min 10, age <= 10 + 1, idxus_lib.py:113, 151)
#define CR_IDX_LATE_S 300              // a decision's bar: the first kept bar in [T, T + 5 min] (late_min 5, idxus_lib.py:154)
#define CR_IDX_CLOSE_MIN 960           // 16:00 New York, grid column 390 (strategy.py:223)
#define CR_IDX_EXIT_MIN 955            // exit_min 955: 15:55 New York (strategy.py:298, 304)
#define CR_IDX_FIRST_DATE 1388534400   // 2014.01.01 00:00, MIN_DATE (strategy.py:66, 114-116)
#define CR_IDX_ATR_N 14                // daily ATR(14) (strategy.py:305, atr_n 14; idxus_lib.py:161)
#define CR_IDX_ATR_MINBARS 600         // trading days with fewer kept bars are dropped (idxus_lib.py:161, 181)
// ---- N30 noise30 (strategy.py:297-299)
#define CR_N30_NCHK 12                 // checks 10:00, 10:30, ..., 15:30 (strategy.py:220)
#define CR_N30_FIRST_MIN 600           // first_min 600: 10:00
#define CR_N30_STEP_MIN 30             // step 30
#define CR_N30_LOOKBACK 14             // lookback 14
#define CR_N30_MINP 9                  // max(int(0.7 x 14), 1) (strategy.py:222)
#define CR_N30_VM 1.0                  // vm 1.0
// ---- OC4 ocm4 (strategy.py:303-305)
#define CR_OC4_N 4                     // n 4: the candle [09:30, 09:34), decision at 09:34
#define CR_OC4_MIN_CNT 3               // ceil(0.6 x 4) bars in the candle (strategy.py:145)
#define CR_OC4_WIN 20                  // size_win 20
#define CR_OC4_MINP 10                 // max(20 // 2, 1) (strategy.py:142)
#define CR_OC4_K 0.3                   // stop atr, k 0.3
#define CR_OC4_SIZE_MIN 1.0            // size_min 1.0

//+------------------------------------------------------------------+
//| CrIdxGrid: the session grid and the daily ATR                    |
//+------------------------------------------------------------------+
class CrIdxGrid
  {
public:
   // ---- the New York date being built (a grid row when m_row and one of its kept bars was fed)
   datetime m_date;                    // New York date 00:00 (wall clock), 0 = none yet
   bool     m_row;                     // weekday and not an NYSE full closure (idxus_lib.py:136-141)
   bool     m_half;                    // NYSE 13:00 half day
   bool     m_trad;                    // a row that may trade: not a half day, from 2014-01-01
   bool     m_bar;                     // a kept bar of this date was fed
   datetime m_x;                       // 15:55 New York (UTC): the rules' time exit
   double   m_O;                       // mid open of the first bar at or after 09:30 if it starts before 09:32
   int      m_cnt;                     // kept bars in [09:30, 09:34)
   double   m_C;                       // P(09:34)
   double   m_p[CR_N30_NCHK];          // P at the N30 checks
   double   m_cl;                      // P(16:00)
   int      m_mod;                     // New York minute of the day of the last OnMinute barrier
   // ---- the rows before the current date
   double   m_pc;                      // the previous row's P(16:00)
   CrRollSum    m_sig[CR_N30_NCHK];    // N30: |P/O - 1| at each check, rolling(14, 9) over the rows
   CrRollMedian m_med;                 // OC4: |C/O - 1|, rolling(20, 10) median over the rows
   // ---- the last kept bar fed
   datetime m_last_t;                  // its start (0 = none)
   double   m_last_c;                  // its mid close
   // ---- the daily ATR: 17:00-NY trading days = server dates
   datetime m_dday;                    // server date of the day being summed (0 = none open)
   datetime m_dknown;                  // its end, 17:00 New York (UTC): its ATR is known from then
   int      m_dn;                      // its kept bars
   double   m_dh, m_dl, m_dc;          // max per-bar mid high, min per-bar mid low, last mid close
   double   m_dpc;                     // close of the previous kept day (NaN: none yet)
   CrRollSum m_trs;                    // rolling(14, 14) mean of the kept days' true ranges
   double   m_atr;                     // ATR of the last kept day that ended (NaN until 14 of them)

   void Init()
     {
      m_date = 0;
      m_row = false;
      m_half = false;
      m_trad = false;
      m_bar = false;
      m_x = 0;
      m_O = CrNaN();
      m_cnt = 0;
      m_C = CrNaN();
      for(int j = 0; j < CR_N30_NCHK; j++)
        {
         m_p[j] = CrNaN();
         m_sig[j].Init(CR_N30_LOOKBACK, CR_N30_MINP);
        }
      m_cl = CrNaN();
      m_mod = -1;
      m_pc = CrNaN();
      m_med.Init(CR_OC4_WIN, CR_OC4_MINP);
      m_last_t = 0;
      m_last_c = CrNaN();
      m_dday = 0;
      m_dknown = 0;
      m_dn = 0;
      m_dh = 0.0;
      m_dl = 0.0;
      m_dc = 0.0;
      m_dpc = CrNaN();
      m_trs.Init(CR_IDX_ATR_N, CR_IDX_ATR_N);
      m_atr = CrNaN();
     }

   // |x/O - 1| of the current row (strategy.py:139-141, 221), NaN when x or O is missing
   double AbsMove(const double x)
     {
      if(!CrFinite(x) || !CrFinite(m_O)) return CrNaN();
      return MathAbs(x / m_O - 1);
     }

   // P(T): the mid close of the last kept bar starting before T, NaN when it started more than 11 min before T
   double PAt(const datetime T)
     {
      if(m_last_t <= 0 || m_last_t >= T) return CrNaN();
      if((long)(T - m_last_t) > CR_IDX_STALE_S) return CrNaN();
      return m_last_c;
     }

   // the current date ends: it becomes a row of the rolling windows when it was a weekday, not a full closure, with a bar
   void DayClose()
     {
      if(m_date == 0 || !m_row || !m_bar) return;
      for(int j = 0; j < CR_N30_NCHK; j++) m_sig[j].Push(AbsMove(m_p[j]));
      m_med.Push(AbsMove(m_C));
      m_pc = m_cl;                                             // strategy.py:223-224: the previous ROW's 16:00 price
     }

   void DayOpen(const datetime ny_date)
     {
      m_date = ny_date;
      int dow = ClkDow(ny_date);
      int kind = ClkNyse(ny_date);
      m_row = (dow >= 1 && dow <= 5 && kind != CR_NYSE_FULL);
      m_half = (kind == CR_NYSE_HALF);
      m_trad = m_row && !m_half && ny_date >= (datetime)CR_IDX_FIRST_DATE;
      m_bar = false;
      m_x = ClkNyToUtc(ny_date + CR_IDX_EXIT_MIN * 60);
      m_O = CrNaN();
      m_cnt = 0;
      m_C = CrNaN();
      for(int j = 0; j < CR_N30_NCHK; j++) m_p[j] = CrNaN();
      m_cl = CrNaN();
     }

   // move forward to New York date ny_date (dates only move forward: bars and barriers come in time order)
   void ToDate(const datetime ny_date)
     {
      if(ny_date <= m_date) return;
      DayClose();
      DayOpen(ny_date);
     }

   // the trading day being summed has ended: a kept day gives a true range and the ATR known from its end
   void AtrClose()
     {
      if(m_dday == 0) return;
      if(m_dn >= CR_IDX_ATR_MINBARS)
        {
         double tr = m_dh - m_dl;                              // np.fmax(h - l, np.fmax(|h - pc|, |l - pc|)): NaN pc ignored
         if(CrFinite(m_dpc))
           {
            double a = MathAbs(m_dh - m_dpc);
            double c = MathAbs(m_dl - m_dpc);
            double m = (a >= c) ? a : c;
            if(m > tr) tr = m;
           }
         m_trs.Push(tr);
         m_atr = m_trs.Mean();
         m_dpc = m_dc;
        }
      m_dday = 0;
     }

   void AtrAdd(const CrBar &b)
     {
      datetime X = ClkServerDay(b.t);
      if(m_dday != 0 && X != m_dday) AtrClose();               // (the barrier at its end closes it first)
      double mh = (b.bh + b.ah) / 2;
      double ml = (b.bl + b.al) / 2;
      if(m_dday == 0)
        {
         m_dday = X;
         m_dknown = ClkServerToUtc(X + 86400);                 // 00:00 server of the next date = 17:00 New York of X
         m_dn = 0;
         m_dh = mh;
         m_dl = ml;
        }
      else
        {
         if(mh > m_dh) m_dh = mh;
         if(ml < m_dl) m_dl = ml;
        }
      m_dc = (b.bc + b.ac) / 2;
      m_dn++;
     }

   // one kept US100 bar, in time order
   void OnBar(const CrBar &b)
     {
      datetime ny = ClkUtcToNy(b.t);
      datetime d = ClkDay(ny);
      if(d > m_date) ToDate(d);                                // the first bar of a load comes before any barrier
      if(d == m_date)
        {
         m_bar = true;
         int mod = ClkMinOfDay(ny);
         if(mod >= CR_IDX_OPEN_MIN && mod < CR_IDX_OPEN_MIN + CR_OC4_N) m_cnt++;
         if(!CrFinite(m_O) && (mod == CR_IDX_OPEN_MIN || mod == CR_IDX_OPEN_MIN + 1)) m_O = (b.bo + b.ao) / 2;
        }
      m_last_t = b.t;
      m_last_c = (b.bc + b.ac) / 2;
      AtrAdd(b);
     }

   // barrier M (every kept bar starting before M has been fed): the date, the ATR day, the P samples of minute M
   void OnMinute(const datetime M)
     {
      datetime ny = ClkUtcToNy(M);
      ToDate(ClkDay(ny));
      if(m_dday != 0 && M >= m_dknown) AtrClose();
      m_mod = ClkMinOfDay(ny);
      if(m_mod == CR_IDX_OPEN_MIN + CR_OC4_N) m_C = PAt(M);
      int j = CheckIndex();
      if(j >= 0) m_p[j] = PAt(M);
      if(m_mod == CR_IDX_CLOSE_MIN) m_cl = PAt(M);
     }

   // the N30 check of the last barrier's minute: 0..11, -1 when it is not a check
   int CheckIndex()
     {
      int k = m_mod - CR_N30_FIRST_MIN;
      if(k < 0 || k % CR_N30_STEP_MIN != 0) return -1;
      k = k / CR_N30_STEP_MIN;
      if(k >= CR_N30_NCHK) return -1;
      return k;
     }
  };

// the latest time exit of a position opened at open_time (SPEC 4.8): 15:55 New York of its New York date, gap rule
datetime IdxLatestExit(const datetime open_time)
  {
   datetime ny = ClkUtcToNy(open_time);
   return ClkNyToUtc(ClkDay(ny) + CR_IDX_EXIT_MIN * 60);
  }

#ifdef CR_IDX_TRACE
void IdxTrace(CrOut &out, const int sl, const datetime M, const int side, const double v1, const double v2)
  {
   CrDec d;
   d.sleeve = sl;
   d.dec = M;
   d.side = side;
   d.what = CR_DEC_INFO;
   d.v1 = v1;
   d.v2 = v2;
   CrOutDec(out, d);
  }
#endif

//+------------------------------------------------------------------+
//| CRuleN30: noise30_us100                                          |
//+------------------------------------------------------------------+
class CRuleN30
  {
public:
   int       sl;
   CrIdxGrid m_g;
   datetime  m_day;                    // the grid date the state belongs to
   int       m_pos;                    // the lab's state: -1, 0, 1 (blind to paper stop-outs)
   long      m_open;                   // oid of the order the state holds (0 = none)
   // a decision waiting for its bar
   bool      m_wait;
   datetime  m_wt;                     // its check time T
   bool      m_wexit;                  // it exits the held order
   int       m_wside;                  // the side it enters (0 = none)
   long      m_woid;                   // the oid of that entry
   bool      m_wrev;                   // the entry follows the exit (after_exit_of): it commits at the next bar
   bool      m_wseen;                  // the check's bar was seen
   datetime  m_wto;                    // a reversal's entry: the last start of the bar after the exit's (15:54)

   bool Init(const int sleeve)
     {
      sl = sleeve;
      m_g.Init();
      m_day = 0;
      m_pos = 0;
      m_open = 0;
      m_wait = false;
      m_wt = 0;
      m_wexit = false;
      m_wside = 0;
      m_woid = 0;
      m_wrev = false;
      m_wseen = false;
      m_wto = 0;
      return true;
     }

   // the state is per row (strategy.py:234): a new New York date starts flat
   void DayCheck()
     {
      if(m_g.m_date == m_day) return;
      m_day = m_g.m_date;
      m_pos = 0;
      m_open = 0;
      m_wait = false;
     }

   void Commit(const int pos, const long oid)
     {
      m_pos = pos;
      m_open = oid;
     }

   void OnBar(const int sym, const CrBar &b, CrOut &out)
     {
      if(sym != CR_IDX) return;
      m_g.OnBar(b);
      DayCheck();
      if(!m_wait) return;
      if(!m_wseen)
        {
         if(b.t < m_wt || b.t > m_wt + CR_IDX_LATE_S) return;
         m_wseen = true;                                       // the check's bar (the lab's ei): its decision stands
         if(m_wexit) Commit(0, 0);
         if(m_wrev) return;                                    // the reversal's entry waits for the next bar
         if(m_wside != 0) Commit(m_wside, m_woid);
         m_wait = false;
         return;
        }
      if(b.t <= m_wto) Commit(m_wside, m_woid);               // the bar after the exit's (strategy.py:243 'ei += 1')
      m_wait = false;
     }

   void OnMinute(const datetime M, CrOut &out)
     {
      m_g.OnMinute(M);
      DayCheck();
      if(m_wait)
        {
         if(!m_wseen && M > m_wt + CR_IDX_LATE_S) m_wait = false;   // no kept bar in [T, T + 5 min]: the check never was
         else if(m_wseen && M > m_wto) m_wait = false;         // no kept bar after the exit's before 15:55: no entry
        }
      int j = m_g.CheckIndex();
      if(j < 0 || !m_g.m_trad || !CrFinite(m_g.m_O)) return;
      double p = m_g.m_p[j];
      double s = m_g.m_sig[j].Mean();
      if(!CrFinite(p) || !CrFinite(s)) return;
      if(m_wait) return;                                       // cannot occur (header); the check is skipped
      double O = m_g.m_O, pc = m_g.m_pc;
      double hi = O, lo = O;                                   // np.fmax(O, pc), np.fmin(O, pc); O when pc is NaN
      if(CrFinite(pc))
        {
         if(pc > hi) hi = pc;
         if(pc < lo) lo = pc;
        }
      double ub = hi * (1 + CR_N30_VM * s);
      double lb = lo * (1 - CR_N30_VM * s);
#ifdef CR_IDX_TRACE
      IdxTrace(out, sl, M, m_pos, p, s);
      IdxTrace(out, sl, M, m_pos, ub, lb);
#endif
      bool ex = (m_pos > 0 && p < ub) || (m_pos < 0 && p > lb);
      int side = 0;
      if(ex || m_pos == 0)
        {
         if(p > ub) side = 1;
         else if(p < lb) side = -1;
        }
      if(!ex && side == 0) return;
      if(ex)
        {
         CrExit e;
         e.sleeve = sl;
         e.oid = m_open;
         e.t_from = M;
         e.t_to = M + CR_IDX_LATE_S;
         e.dec = M;
         CrOutExit(out, e);
        }
      long oid = 0;
      if(side != 0)
        {
         CrOrder o;
         CrOrderClear(o);
         o.sleeve = sl;
         oid = CrOid(M, g_sl[sl].id);
         o.oid = oid;
         o.side = side;
         o.etype = CR_ET_MARKET;
         o.t_from = M;
         o.t_to = M + CR_IDX_LATE_S;
         if(ex)
           {
            o.after_exit_of = m_open;                          // the first kept bar after the exit's bar
            o.t_to = m_g.m_x - 60;                             // ... if it starts before 15:55 (the lab's ei + 1 < xi)
           }
         o.stop = (side > 0) ? hi : lo;                        // the centre of the noise area (strategy.py:250)
         o.x_sched = m_g.m_x;
         o.x_gap = true;                                       // gl.exit_index (strategy.py:119-121, 227)
         o.void_le = true;                                     // the lab's ei < xi (strategy.py:237, 244)
         o.dec = M;
         CrOutOrder(out, o);
        }
      m_wait = true;
      m_wt = M;
      m_wexit = ex;
      m_wside = side;
      m_woid = oid;
      m_wrev = ex && side != 0;
      m_wseen = false;
      m_wto = m_g.m_x - 60;
     }

   datetime LatestExit(const datetime open_time, const datetime comment_dec) { return IdxLatestExit(open_time); }
  };

//+------------------------------------------------------------------+
//| CRuleOC4: ocm4_us100                                             |
//+------------------------------------------------------------------+
class CRuleOC4
  {
public:
   int       sl;
   CrIdxGrid m_g;

   bool Init(const int sleeve)
     {
      sl = sleeve;
      m_g.Init();
      return true;
     }

   void OnBar(const int sym, const CrBar &b, CrOut &out)
     {
      if(sym != CR_IDX) return;
      m_g.OnBar(b);
     }

   void OnMinute(const datetime M, CrOut &out)
     {
      m_g.OnMinute(M);
      if(m_g.m_mod != CR_IDX_OPEN_MIN + CR_OC4_N || !m_g.m_trad) return;
      double O = m_g.m_O, C = m_g.m_C;
      if(!CrFinite(O) || !CrFinite(C) || m_g.m_cnt < CR_OC4_MIN_CNT) return;
      double move = C / O - 1;                                 // strategy.py:139
      int side = 0;
      if(move > 0) side = 1;
      else if(move < 0) side = -1;
      double amove = MathAbs(move);
      double med = m_g.m_med.Value();                          // the 20 previous rows (shift(1))
      double atr = m_g.m_atr;                                  // the last trading day ended by 09:34
#ifdef CR_IDX_TRACE
      IdxTrace(out, sl, M, side, amove, med);
      IdxTrace(out, sl, M, side, atr, (double)m_g.m_cnt);
#endif
      if(side == 0 || !CrFinite(atr) || !CrFinite(med)) return;
      if(!(amove >= CR_OC4_SIZE_MIN * med)) return;
      CrOrder o;
      CrOrderClear(o);
      o.sleeve = sl;
      o.oid = CrOid(M, g_sl[sl].id);
      o.side = side;
      o.etype = CR_ET_MARKET;
      o.t_from = M;
      o.t_to = M + CR_IDX_LATE_S;                              // the lab's EI[:, 4] (late_min 5)
      o.stop_dist = CR_OC4_K * atr;                            // strategy.py:162
      o.x_sched = m_g.m_x;
      o.x_gap = true;
      o.void_le = true;                                        // the lab's xi > EI (strategy.py:154)
      o.dec = M;
      CrOutOrder(out, o);
     }

   datetime LatestExit(const datetime open_time, const datetime comment_dec) { return IdxLatestExit(open_time); }
  };
#endif

// ==== end src/CR_Rule_IdxUS.mqh
// ==== begin src/CR_Rule_Brk72.mqh
//+------------------------------------------------------------------+
//| CR_Rule_Brk72.mqh - BKB / BKE brk72_24h_wd on BTC and ETH, with   |
//| S0.75r (BKB) and K1 (BKE) behind their switches (SPEC 3).         |
//| Owner: E.                                                         |
//|                                                                  |
//| The rule (lab/r2/tracks/crypto/strategy.py, wrapper              |
//| lab/r2/recalc.py:43-53):                                         |
//|   bars   UTC hour bars of the kept M1 bars (h1_bars :82-98): h = |
//|          max of the per-bar mids (bh + ah) / 2, l = min of       |
//|          (bl + al) / 2, c = (bc + ac) / 2 of the last bar. Hours |
//|          without a bar do not exist. An hour is complete at the  |
//|          barrier of its end, D = hour start + 1 h.               |
//|   signal at D (_brk :153-178): c above the highest of the 72     |
//|          previous closes -> long, below the lowest -> short;     |
//|          D on a UTC weekday (_finish :131-132).                  |
//|   ATR    mean of the last 24 true ranges (sma_atr :101-106):     |
//|          TR = max(h - l, |h - pc|, |l - pc|), the first one h - l |
//|          (pandas rolling mean: CrRollSum); finite and > 0.       |
//|   order  market, window [D, D + 5 min] (_finish :115-119),       |
//|          stop_dist 3 ATR (:139), time exit x = D + 24 h (:120)   |
//|          with the gap rule, void_le (the wrapper drops an order  |
//|          whose exit bar does not follow its entry bar).          |
//| Constants: n 72, stop_atr 3, hold_h 24, dow weekday              |
//| (strategy.py:242-243), atr_n 24, max_delay_min 5 (:52-53).       |
//|                                                                  |
//| The two changes, while their switch is on (g_sl[].change_on):    |
//|   S0.75r (BKB): stop_dist = 0.75 x (3 ATR), the lab's k x r0     |
//|          (payoff variants.py:181-187, look_spec k 0.75); refusal |
//|          1 (payoff) in the paper; stake factor in CR_Sizing.     |
//|   K1 (BKE): riskbp = 1e4 x stop_dist / P, P = c, the mid close   |
//|          of the last kept bar before D (synthesis_B s1_run.py    |
//|          :104-105); Y = the UTC year of D; with T(Y) > 0 from    |
//|          InpK1T and riskbp >= T(Y): nothing is emitted (DEC      |
//|          skip=K1), so the skipped signal blocks nothing (the     |
//|          lab removes it and re-simulates, vhi_sleeves.py         |
//|          :459-507). Otherwise a DEC info line (v1 riskbp, v2     |
//|          T(Y)) and the order, with refusal 2 (synthesis_B) in    |
//|          the paper.                                              |
//|                                                                  |
//| InpK1T (SPEC 1, 10.14): entries "YYYY:T" separated by ';',       |
//|   YYYY a year 2000-2100, T >= 0 in bp, a plain decimal number    |
//|   (digits, '.', digits, optional exponent; the lab writes 17     |
//|   significant digits). Spaces around entries and around ':' are  |
//|   allowed; empty entries are skipped; a year given twice, another|
//|   form, or more than 64 entries: refused (Init false, ERROR at   |
//|   OnInit). It is checked whatever the switch. A year with no T,  |
//|   or T = 0: K1 off for the signals of that year. Every K1 line   |
//|   carries the T it used (v2). Brk72K1Text() gives the table read |
//|   ("YYYY:T;...", 17 digits) for the driver's INIT line.          |
//|   Brk72K1Known(year): a T > 0 exists for that year.              |
//|                                                                  |
//| LatestExit (SPEC 4.8): D = the decision of the comment when it   |
//|   lies on an hour at most 10 min before open_time, else open_time|
//|   floored to the UTC hour; exit min(D + 24 h, Friday 23:54 server|
//|   of open_time's server week).                                   |
//+------------------------------------------------------------------+
#ifndef CR_RULE_BRK72_MQH
#define CR_RULE_BRK72_MQH
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Clock.mqh)
// (already inlined: CR_Journal.mqh)
// (already inlined: CR_Math.mqh)

#define CR_BRK_N 72                    // channel of closes (strategy.py:243)
#define CR_BRK_ATR_N 24                // ATR bars (strategy.py:52)
#define CR_BRK_STOP_ATR 3.0            // stop distance in ATR (strategy.py:243)
#define CR_BRK_HOLD_S 86400            // hold_h 24: exit = D + int(round(24 x 60)) minutes (strategy.py:120, 243)
#define CR_BRK_WAIT_S 300              // max_delay_min 5: first bar within 5 min of D (strategy.py:53, 119)
#define CR_BRK_S075_K 0.75             // S0.75r: k (look_spec.json brk72_24h_wd__btcusd+S0.75r)
#define CR_BRK_JOIN_S 600              // LatestExit: an open time at most 10 min after its decision
#define CR_K1_MAX 64                   // InpK1T entries

// ---- the K1 table read from InpK1T (one per EA: K1 belongs to BKE only)
int    g_brk_k1_year[CR_K1_MAX];
double g_brk_k1_t[CR_K1_MAX];
int    g_brk_k1_n = 0;

bool Brk72Digit(const ushort ch) { return ch >= '0' && ch <= '9'; }

// a plain decimal number without sign: digits, optionally '.' and digits, optionally e or E, a sign and digits
bool Brk72IsNumber(const string s)
  {
   int n = StringLen(s);
   int i = 0, d = 0;
   while(i < n && Brk72Digit(StringGetCharacter(s, i)))
     {
      i++;
      d++;
     }
   if(d == 0) return false;
   if(i < n && StringGetCharacter(s, i) == '.')
     {
      i++;
      int f = 0;
      while(i < n && Brk72Digit(StringGetCharacter(s, i)))
        {
         i++;
         f++;
        }
      if(f == 0) return false;
     }
   if(i < n && (StringGetCharacter(s, i) == 'e' || StringGetCharacter(s, i) == 'E'))
     {
      i++;
      if(i < n && (StringGetCharacter(s, i) == '+' || StringGetCharacter(s, i) == '-')) i++;
      int e = 0;
      while(i < n && Brk72Digit(StringGetCharacter(s, i)))
        {
         i++;
         e++;
        }
      if(e == 0) return false;
     }
   return i == n;
  }

// InpK1T -> the K1 table; false and why when the text is refused (the table is then empty)
bool Brk72ParseK1T(const string text, string &why)
  {
   g_brk_k1_n = 0;
   why = "";
   string t = text;
   StringTrimLeft(t);
   StringTrimRight(t);
   if(t == "") return true;
   string part[];
   int n = StringSplit(t, ';', part);
   for(int k = 0; k < n; k++)
     {
      string e = part[k];
      StringTrimLeft(e);
      StringTrimRight(e);
      if(e == "") continue;
      int c = StringFind(e, ":");
      if(c < 0 || StringFind(e, ":", c + 1) >= 0)
        {
         why = "'" + e + "' is not YYYY:T";
         g_brk_k1_n = 0;
         return false;
        }
      string ys = StringSubstr(e, 0, c);
      string ts = StringSubstr(e, c + 1);
      StringTrimLeft(ys);
      StringTrimRight(ys);
      StringTrimLeft(ts);
      StringTrimRight(ts);
      bool year_ok = (StringLen(ys) == 4);
      for(int i = 0; i < StringLen(ys) && year_ok; i++)
         if(!Brk72Digit(StringGetCharacter(ys, i))) year_ok = false;
      int y = year_ok ? (int)StringToInteger(ys) : 0;
      if(!year_ok || y < 2000 || y > 2100)
        {
         why = "'" + e + "': the year must be 2000-2100";
         g_brk_k1_n = 0;
         return false;
        }
      if(!Brk72IsNumber(ts))
        {
         why = "'" + e + "': T must be a number of bp (e.g. 465.1178140105435)";
         g_brk_k1_n = 0;
         return false;
        }
      double v = StringToDouble(ts);
      if(!MathIsValidNumber(v) || v < 0.0)
        {
         why = "'" + e + "': T must be finite and >= 0";
         g_brk_k1_n = 0;
         return false;
        }
      for(int j = 0; j < g_brk_k1_n; j++)
         if(g_brk_k1_year[j] == y)
           {
            why = "year " + IntegerToString(y) + " given twice";
            g_brk_k1_n = 0;
            return false;
           }
      if(g_brk_k1_n >= CR_K1_MAX)
        {
         why = "more than " + IntegerToString(CR_K1_MAX) + " entries";
         g_brk_k1_n = 0;
         return false;
        }
      g_brk_k1_year[g_brk_k1_n] = y;
      g_brk_k1_t[g_brk_k1_n] = v;
      g_brk_k1_n++;
     }
   return true;
  }

// T(year) of the K1 table, 0 when the year has none
double Brk72K1T(const int year)
  {
   for(int j = 0; j < g_brk_k1_n; j++)
      if(g_brk_k1_year[j] == year) return g_brk_k1_t[j];
   return 0.0;
  }

// a T > 0 exists for that year (CR_Main pushes "K1 with no T for the year" when the switch is on and this is false)
bool Brk72K1Known(const int year) { return Brk72K1T(year) > 0.0; }

// the table as the EA understood it: "YYYY:T;..." with 17 significant digits
string Brk72K1Text()
  {
   string s = "";
   for(int j = 0; j < g_brk_k1_n; j++)
     {
      if(j > 0) s = s + ";";
      s = s + IntegerToString(g_brk_k1_year[j]) + ":" + DoubleToString(g_brk_k1_t[j], -16);
     }
   return s;
  }

// K1's risk in bp: 1e4 x stop_dist / P, P = the mid close of the last kept bar before the decision (s1_run.py:105)
double Brk72RiskBp(const double stop_dist, const double p) { return 1e4 * stop_dist / p; }

// Friday 23:54 server of the server week of utc, as UTC (the last crypto bar before the weekend closure)
datetime Brk72FridayEnd(const datetime utc)
  {
   datetime srv = ClkUtcToServer(utc);
   long day = (long)ClkDay(srv);
   int mon0 = (ClkDow(srv) + 6) % 7;                         // 0 = Monday ... 6 = Sunday
   long fri = day + (long)(4 - mon0) * 86400 + 23 * 3600 + 54 * 60;
   return ClkServerToUtc((datetime)fri);
  }

class CRuleBrk72
  {
public:
   int       sl;
   int       m_sym;                    // traded and read symbol
   int       m_id;                     // sleeve id (oid = decision x 100 + id)
   bool      m_k1;                     // K1 in force (BKE, switch on)
   bool      m_s075;                   // S0.75r in force (BKB, switch on)
   int       m_refuse;                 // refusal of the orders (CR_REF_*): the change's while it is on
   CrAgg     m_agg;                    // the UTC hour being filled
   long      m_nh;                     // hour bars since Init
   double    m_pc;                     // close of the previous hour bar
   CrRollSum m_tr;                     // ATR24: rolling mean of the true ranges
   CrRollMax m_cmax;                   // highest of the 72 previous closes
   CrRollMin m_cmin;                   // lowest of the 72 previous closes

   bool Init(const int sleeve)
     {
      sl = sleeve;
      m_sym = g_sl[sl].sym;
      m_id = g_sl[sl].id;
      bool on = g_sl[sl].change_on;
      m_k1 = on && g_sl[sl].change == CR_CH_K1;
      m_s075 = on && g_sl[sl].change == CR_CH_S075;
      m_refuse = on ? g_sl[sl].refuse_on : CR_REF_NONE;
      m_agg.Clear();
      m_nh = 0;
      m_pc = 0.0;
      m_tr.Init(CR_BRK_ATR_N, CR_BRK_ATR_N);
      m_cmax.Init(CR_BRK_N);
      m_cmin.Init(CR_BRK_N);
      if(g_sl[sl].change == CR_CH_K1)
        {
         string why = "";
         if(!Brk72ParseK1T(g_cfg.k1t, why))
           {
            JrnError(g_sl[sl].code, "InpK1T refused: " + why);
            return false;
           }
        }
      return true;
     }

   // an hour bar is complete (its end D has passed the barrier): ATR, channel, signal, order
   void Hour(const CrAggBar &hb, CrOut &out)
     {
      double h = hb.mh;
      double l = hb.ml;
      double c = (hb.bc + hb.ac) / 2;
      double tr = h - l;                                     // sma_atr: the first true range is h - l
      if(m_nh > 0)
        {
         double a = MathAbs(h - m_pc);
         double b = MathAbs(l - m_pc);
         if(a > tr) tr = a;
         if(b > tr) tr = b;
        }
      m_tr.Push(tr);
      double atr = m_tr.Mean();
      double hi = m_cmax.Value();                            // c.rolling(72).max().shift(1): NaN until 72 closes
      double lo = m_cmin.Value();
      m_cmax.Push(c);
      m_cmin.Push(c);
      m_pc = c;
      m_nh++;
      int side = 0;
      if(CrFinite(hi) && c > hi) side = 1;
      else if(CrFinite(lo) && c < lo) side = -1;
      if(side == 0) return;
      datetime D = hb.key + 3600;
      int dow = ClkDow(D);                                   // UTC weekday of the decision: 1 = Monday ... 5 = Friday
      if(dow < 1 || dow > 5) return;
      if(!CrFinite(atr) || !(atr > 0.0)) return;
      double sd = atr * CR_BRK_STOP_ATR;
      if(m_k1)
        {
         double riskbp = Brk72RiskBp(sd, c);
         double T = Brk72K1T(ClkYear(D));
         CrDec d;
         ZeroMemory(d);
         d.sleeve = sl;
         d.dec = D;
         d.side = side;
         d.v1 = riskbp;
         d.v2 = T;
         d.what = CR_DEC_INFO;
         bool skip = (T > 0.0 && riskbp >= T);
         if(skip) d.what = CR_DEC_SKIP_K1;
         if(!CrOutDec(out, d)) JrnError(g_sl[sl].code, "more than CR_OUT_MAX decisions at " + IntegerToString((long)D));
         if(skip) return;
        }
      if(m_s075) sd = CR_BRK_S075_K * sd;
      CrOrder o;
      CrOrderClear(o);
      o.sleeve = sl;
      o.oid = CrOid(D, m_id);
      o.side = side;
      o.etype = CR_ET_MARKET;
      o.t_from = D;
      o.t_to = D + CR_BRK_WAIT_S;
      o.stop_dist = sd;
      o.x_sched = D + CR_BRK_HOLD_S;
      o.x_gap = true;
      o.refuse = m_refuse;
      o.void_le = true;
      o.dec = D;
      if(!CrOutOrder(out, o)) JrnError(g_sl[sl].code, "more than CR_OUT_MAX orders at " + IntegerToString((long)D));
     }

   void OnBar(const int sym, const CrBar &b, CrOut &out)
     {
      if(sym != m_sym) return;
      CrAggBar done;
      ZeroMemory(done);
      // a bar of a new hour while the old one is still open: never under the minute contract (OnMinute closes every
      // hour at its end); the old hour is then decided here, before this bar reaches the paper
      if(m_agg.Add(b, CrAggKey(b.t, 3600), done)) Hour(done, out);
     }

   void OnMinute(const datetime M, CrOut &out)
     {
      if(M % 3600 != 0) return;
      CrAggBar cur;
      ZeroMemory(cur);
      if(!m_agg.Peek(cur) || cur.key + 3600 > M) return;
      m_agg.Take(cur);
      Hour(cur, out);
     }

   datetime LatestExit(const datetime open_time, const datetime comment_dec)
     {
      datetime D = open_time - open_time % 3600;
      if(comment_dec > 0 && comment_dec % 3600 == 0 && comment_dec <= open_time && (long)(open_time - comment_dec) <= CR_BRK_JOIN_S)
         D = comment_dec;
      datetime x = D + CR_BRK_HOLD_S;
      datetime fri = Brk72FridayEnd(open_time);
      if(fri < x) x = fri;
      return x;
     }
  };
#endif

// ==== end src/CR_Rule_Brk72.mqh
// ==== begin src/CR_Rule_F1.mqh
//+------------------------------------------------------------------+
//| CR_Rule_F1.mqh - F1B / F1E F1_brk_ridge_filter on BTC and ETH,    |
//| with H2 (F1E) behind its switch (SPEC 3). Owner: E.               |
//| The frozen scorecard comes from the generated CR_F1Model.mqh.    |
//|                                                                  |
//| The rule (lab/r2/tracks/ml/strategy.py):                         |
//|   session bars  UTC hour bars of the BID M1 bars (_h1_bid :82-96:|
//|          o first bo, h max bh, l min bl, c last bc) whose start  |
//|          is 02:00-15:00 New York on a New York weekday           |
//|          (session_bars :99-113). Every look-back counts session  |
//|          bars only. A bar is complete at the barrier of its end. |
//|   at t_dec = the end of a session bar that starts at 02:00-14:00 |
//|          New York (candidates :116-189):                         |
//|          hh, ll = highest high, lowest low of the 14 previous    |
//|          session bars; c > hh -> long, c < ll -> short;          |
//|          A = mean of h - l over the last 70 (this one included), |
//|          A_long over 280 (pandas rolling mean: CrRollSum);       |
//|          the 15 features of FEATURES (:72-73, formulas :136-162):|
//|            brk  (c - hh) / A long, (ll - c) / A short            |
//|            bar  (h - l) / A          body  s (c - o) / A         |
//|            ret4, ret14, ret70  s (c - c[k bars ago]) / A         |
//|            chan (hh - ll) / A        vol   A / A_long            |
//|            pos  (c - L280) / (H280 - L280) long, (H280 - c) /    |
//|                 (H280 - L280) short (280 bars, this one in)      |
//|            seq, opp  breakouts of the 14 previous session bars   |
//|                 on the same / the other side                     |
//|            pdd  (c - pdh) / A long, (pdl - c) / A short          |
//|            dret s (c - pdc) / A   (pd* = the previous New York   |
//|                 date that has session bars: max h, min l, last c)|
//|            hour = New York hour of t_dec, dow = weekday (0 Mon)  |
//|          a candidate needs every feature finite and A > 0; the   |
//|          score (CR_F1Model.mqh) is journaled (DEC info: v1 score,|
//|          v2 A); it is taken when score >= CR_F1_THR.             |
//|   order  market, window [t_dec, t_dec + 5 min] (:171-178),       |
//|          stop_dist 2 A (make_orders :286), exit x = min(t_dec +  |
//|          13 h, 15:55 New York of t_dec's date) (:179-185) with   |
//|          the gap rule, void_le (the lab keeps an order only when |
//|          its exit bar follows its entry bar, :186).              |
//| Constants: stop_k 2.0, hold_h 13, model B1_ridge_full.json, q 0.5|
//| (strategy.py:295-297); n 14, h0 2, h1 16, last_dec_h 15, vol_n   |
//| 70, exit_hm 1555, max_wait_min 5 (:55-69); seq and opp windows 14|
//| (:147-148); A_long and the 280-bar extremes 4 x vol_n (:125,     |
//| 144-145).                                                        |
//|                                                                  |
//| H2 (F1E, while its switch is on; payoff variants.py:206-233,     |
//| :118-126; common.py:249-262): xh = min(15:55 New York on (t_dec's|
//| New York date + 2 business days), Friday 23:54 server of the     |
//| entry's server week), both with the gap rule; xh_r = 1.0; the    |
//| paper holds a trade still open at x that is ahead by 1 R at the  |
//| close of the bar before its exit bar (SPEC 2.5); stop unchanged; |
//| refusal 1 (payoff) in the paper; stake factor in CR_Sizing.      |
//|                                                                  |
//| LatestExit (SPEC 4.8): t_dec = the decision of the comment when  |
//| it lies on an hour at most 10 min before open_time, else         |
//| open_time floored to the UTC hour; exit 15:55 New York on t_dec's|
//| date (the H2 hold needs the paper: not applied).                 |
//+------------------------------------------------------------------+
#ifndef CR_RULE_F1_MQH
#define CR_RULE_F1_MQH
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Clock.mqh)
// (already inlined: CR_Journal.mqh)
// (already inlined: CR_Math.mqh)
// ==== begin src/CR_F1Model.mqh
//+------------------------------------------------------------------+
//| CR_F1Model.mqh - GENERATED by tools/gen_f1_model.py (step E) from |
//| lab/r2/tracks/ml/models/B1_ridge_full.json["frozen"], refused     |
//| unless its sha256 is d191cbbcc2fc4d2cae31182f14f412069a194b69c2a9 |
//| d9ae6bca0d0f5dee644e. Constants written with %.17g.               |
//| Do not edit by hand: run the generator again.                    |
//|                                                                  |
//| The F1 score (ml/strategy.py score_model :208-212, _design       |
//| :195-205), computed by CR_Rule_F1.mqh:                           |
//|   z_k = (x[NUM_FEAT[k]] - MEAN[k]) / STD[k], clipped to +/- CLIP |
//|   d_j = 1 when DUM_LO[j] <= x[DUM_FEAT[j]] <= DUM_HI[j], else 0  |
//|   score = INTERCEPT + (sum of z_k COEF[k], then d_j COEF[NNUM+j])|
//|   taken when score >= THR (thr["0.5"], FINALISTS q 0.5)          |
//| x = the 15 features in ml/strategy.py FEATURES order (:72-73):   |
//|   0 brk 1 bar 2 body 3 ret4 4 ret14 5 ret70 6 chan 7 vol 8 pos   |
//|   9 seq 10 opp 11 pdd 12 dret 13 hour 14 dow                     |
//+------------------------------------------------------------------+
#ifndef CR_F1MODEL_MQH
#define CR_F1MODEL_MQH
#define CR_F1_READY 1
#define CR_F1_SHA256 "d191cbbcc2fc4d2cae31182f14f412069a194b69c2a9d9ae6bca0d0f5dee644e"
#define CR_F1_NFEAT 15
#define CR_F1_NNUM 13
#define CR_F1_NDUM 5
#define CR_F1_NCOEF 18
#define CR_F1_CLIP 4.0
#define CR_F1_INTERCEPT 0.032528141279623765
#define CR_F1_THR 0.027922380451488427
// numeric inputs, in the model's order: brk bar body ret4 ret14 ret70 chan vol pos seq opp pdd dret
int    CR_F1_NUM_FEAT[CR_F1_NNUM] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12};
double CR_F1_MEAN[CR_F1_NNUM] = {0.71308500532092667, 1.5512737966187637, 0.96420960913068066, 2.4333467452078184, 3.8241508644527737, 4.0824629164437747, 4.4349323545265333, 1.0078719035322139, 0.68484222660145089, 1.7847717168865993, 0.36221861548232304, 1.6489239385765191, 3.0019510735028621};
double CR_F1_STD[CR_F1_NNUM] = {1.0511332012630918, 1.0720187093476934, 0.91673678364706634, 1.731594003005934, 2.4829650691631393, 6.7213277986039959, 2.1091572540703774, 0.22219138168277339, 0.28476548894509579, 1.7956728607877703, 0.77154477408543654, 2.2594491593427279, 2.2025607863709356};
// dummies, in the model's order: hour[8,10] hour[11,12] hour[13,15] dow[0,0] dow[4,4]
int    CR_F1_DUM_FEAT[CR_F1_NDUM] = {13, 13, 13, 14, 14};
double CR_F1_DUM_LO[CR_F1_NDUM] = {8.0, 11.0, 13.0, 0.0, 4.0};
double CR_F1_DUM_HI[CR_F1_NDUM] = {10.0, 12.0, 15.0, 0.0, 4.0};
// coefficients: the numeric inputs, then the dummies
double CR_F1_COEF[CR_F1_NCOEF] = {0.035527166091874569, -0.050994331929108266, 0.034536705278292515, -0.0015449850158405674, -0.030416538524942669, -0.01640644279761903, -0.0070119590679045395, 0.0024333042070126937, 0.030212171905429814, -0.021233724822965584, 0.0046822092122707215, 0.051648228535775498, 0.021970078931120976, 0.0083146713414126716, -0.021782492699578576, -0.038427865708166545, 0.021395951701033221, 0.0094393321135737458};
#endif

// ==== end src/CR_F1Model.mqh

#define CR_F1_CHAN 14                  // n: channel of the previous session bars (strategy.py:56)
#define CR_F1_H0 2                     // session bars start at New York hours h0 .. h1 - 1 (:57)
#define CR_F1_H1 16
#define CR_F1_LAST_DEC_H 15            // last decision hour, New York (:58)
#define CR_F1_VOL_N 70                 // A (:59, 124)
#define CR_F1_VOL_LONG 280             // A_long, H280, L280: 4 x vol_n (:125, 144-145)
#define CR_F1_SEQ_N 14                 // seq / opp windows (:147-148)
#define CR_F1_RET_MAX 70               // the longest close look-back (ret70, :141)
#define CR_F1_STOP_K 2.0               // stop_k (:297)
#define CR_F1_HOLD_S 46800             // hold_h 13: x = t_dec + int(round(13 x 60)) minutes (:183, 297)
#define CR_F1_EXIT_MIN 955             // exit_hm 1555: 15:55 New York, minutes of the day (:62, 181-182)
#define CR_F1_WAIT_S 300               // max_wait_min 5 (:63, 177-178)
#define CR_F1_H2_BDAYS 2               // H2: hold to 15:55 New York two business days later (look_spec j 2)
#define CR_F1_H2_R 1.0                 // H2: ahead by at least 1 R (variants.py:221)
#define CR_F1_JOIN_S 600               // LatestExit: an open time at most 10 min after its decision

// 15:55 New York on the New York date of t (UTC)
datetime F1ExitClock(const datetime t)
  {
   datetime ny = ClkUtcToNy(t);
   return ClkNyToUtc((datetime)((long)ClkDay(ny) + CR_F1_EXIT_MIN * 60));
  }

// Friday 23:54 server of the server week of t, as UTC (payoff common.py:255-259)
datetime F1FridayEnd(const datetime t)
  {
   datetime srv = ClkUtcToServer(t);
   long day = (long)ClkDay(srv);
   int mon0 = (ClkDow(srv) + 6) % 7;                         // 0 = Monday ... 6 = Sunday
   long fri = day + (long)(4 - mon0) * 86400 + 23 * 3600 + 54 * 60;
   return ClkServerToUtc((datetime)fri);
  }

class CRuleF1
  {
public:
   int       sl;
   int       m_sym;                    // traded and read symbol
   int       m_id;                     // sleeve id (oid = decision x 100 + id)
   bool      m_h2;                     // H2 in force (F1E, switch on)
   int       m_refuse;                 // refusal of the orders (CR_REF_*): the change's while it is on
   CrAgg     m_agg;                    // the UTC hour being filled
   long      m_nb;                     // session bars since Init
   CrRollSum m_a;                      // A: rolling mean of h - l over 70 session bars
   CrRollSum m_al;                     // A_long: over 280
   CrRollMax m_hh;                     // highest high of the 14 previous session bars (read before the push)
   CrRollMin m_ll;                     // lowest low of the 14 previous session bars
   CrRollMax m_hhl;                    // highest high of the last 280, this one included
   CrRollMin m_lll;                    // lowest low of the last 280, this one included
   CrRing    m_c;                      // the last 71 closes
   int       m_flag[CR_F1_SEQ_N];      // breakouts of the last 14 session bars: +1 up, -1 down, 0 none (ring)
   int       m_kflag;                  // slot of the next flag
   int       m_nflag;                  // flags kept (at most 14)
   datetime  m_day;                    // New York date of the current day's session bars (0 = none yet)
   double    m_dh, m_dl, m_dc;         // its high, low and last close so far
   bool      m_pd;                     // a previous New York date with session bars exists
   double    m_pdh, m_pdl, m_pdc;      // that date's high, low and last close
   double    m_x[];                    // the 15 features of the candidate (FEATURES order)

   bool Init(const int sleeve)
     {
      sl = sleeve;
      m_sym = g_sl[sl].sym;
      m_id = g_sl[sl].id;
      bool on = g_sl[sl].change_on;
      m_h2 = on && g_sl[sl].change == CR_CH_H2;
      m_refuse = on ? g_sl[sl].refuse_on : CR_REF_NONE;
      m_agg.Clear();
      m_nb = 0;
      m_a.Init(CR_F1_VOL_N, CR_F1_VOL_N);
      m_al.Init(CR_F1_VOL_LONG, CR_F1_VOL_LONG);
      m_hh.Init(CR_F1_CHAN);
      m_ll.Init(CR_F1_CHAN);
      m_hhl.Init(CR_F1_VOL_LONG);
      m_lll.Init(CR_F1_VOL_LONG);
      m_c.Init(CR_F1_RET_MAX + 1);
      for(int k = 0; k < CR_F1_SEQ_N; k++) m_flag[k] = 0;
      m_kflag = 0;
      m_nflag = 0;
      m_day = 0;
      m_dh = 0.0;
      m_dl = 0.0;
      m_dc = 0.0;
      m_pd = false;
      m_pdh = 0.0;
      m_pdl = 0.0;
      m_pdc = 0.0;
      ArrayResize(m_x, CR_F1_NFEAT);
      return true;
     }

   // the frozen scorecard (CR_F1Model.mqh) on the features m_x
   double Score()
     {
      double s = 0.0;
      for(int k = 0; k < CR_F1_NNUM; k++)
        {
         double z = (m_x[CR_F1_NUM_FEAT[k]] - CR_F1_MEAN[k]) / CR_F1_STD[k];
         if(z < -CR_F1_CLIP) z = -CR_F1_CLIP;
         if(z > CR_F1_CLIP) z = CR_F1_CLIP;
         s = s + z * CR_F1_COEF[k];
        }
      for(int j = 0; j < CR_F1_NDUM; j++)
        {
         double v = m_x[CR_F1_DUM_FEAT[j]];
         double d = (v >= CR_F1_DUM_LO[j] && v <= CR_F1_DUM_HI[j]) ? 1.0 : 0.0;
         s = s + d * CR_F1_COEF[CR_F1_NNUM + j];
        }
      return CR_F1_INTERCEPT + s;
     }

   // a complete session bar: the look-back state, then the candidate of its end
   void Session(const CrAggBar &hb, const int ny_hour, const int ny_dow0, const datetime ny_date, CrOut &out)
     {
      double o = hb.bo;
      double h = hb.bh;
      double l = hb.bl;
      double c = hb.bc;
      double rng = h - l;
      if(m_day != ny_date)                                   // the previous date with session bars (:152-157)
        {
         if(m_day != 0)
           {
            m_pd = true;
            m_pdh = m_dh;
            m_pdl = m_dl;
            m_pdc = m_dc;
           }
         m_day = ny_date;
         m_dh = h;
         m_dl = l;
         m_dc = c;
        }
      else
        {
         if(h > m_dh) m_dh = h;
         if(l < m_dl) m_dl = l;
         m_dc = c;
        }
      double hh = m_hh.Value();                              // h.shift(1).rolling(14).max(): NaN until 14 bars
      double ll = m_ll.Value();
      bool up = CrFinite(hh) && c > hh;
      bool dn = CrFinite(ll) && c < ll;
      double s_up = CrNaN(), s_dn = CrNaN();                 // up / dn .shift(1).rolling(14).sum()
      if(m_nflag >= CR_F1_SEQ_N)
        {
         int nu = 0, nd = 0;
         for(int k = 0; k < CR_F1_SEQ_N; k++)
           {
            if(m_flag[k] > 0) nu++;
            if(m_flag[k] < 0) nd++;
           }
         s_up = (double)nu;
         s_dn = (double)nd;
        }
      m_a.Push(rng);
      m_al.Push(rng);
      m_hhl.Push(h);
      m_lll.Push(l);
      m_c.Push(c);
      double A = m_a.Mean();
      double AL = m_al.Mean();
      double hhl = m_hhl.Value();
      double lll = m_lll.Value();
      double c4 = m_c.Last(4), c14 = m_c.Last(14), c70 = m_c.Last(70);
      m_hh.Push(h);                                          // for the next bars
      m_ll.Push(l);
      m_flag[m_kflag] = up ? 1 : (dn ? -1 : 0);
      m_kflag = (m_kflag + 1) % CR_F1_SEQ_N;
      if(m_nflag < CR_F1_SEQ_N) m_nflag++;
      m_nb++;
      int sig = up ? 1 : (dn ? -1 : 0);
      int dec_hour = ny_hour + 1;
      if(sig == 0 || dec_hour > CR_F1_LAST_DEC_H) return;
      if(!CrFinite(A) || !(A > 0.0)) return;
      if(!CrFinite(AL) || !(AL > 0.0)) return;               // A / 0 or A / NaN: not a finite feature
      double den = hhl - lll;
      if(!CrFinite(den) || !(den > 0.0)) return;
      double s = (double)sig;
      m_x[0] = (up ? c - hh : ll - c) / A;                     // brk
      m_x[1] = rng / A;                                        // bar
      m_x[2] = s * (c - o) / A;                                // body
      m_x[3] = s * (c - c4) / A;                               // ret4
      m_x[4] = s * (c - c14) / A;                              // ret14
      m_x[5] = s * (c - c70) / A;                              // ret70
      m_x[6] = (hh - ll) / A;                                  // chan
      m_x[7] = A / AL;                                         // vol
      m_x[8] = (up ? c - lll : hhl - c) / den;                 // pos
      m_x[9] = up ? s_up : s_dn;                               // seq
      m_x[10] = up ? s_dn : s_up;                              // opp
      m_x[11] = m_pd ? (up ? c - m_pdh : m_pdl - c) / A : CrNaN();   // pdd
      m_x[12] = m_pd ? s * (c - m_pdc) / A : CrNaN();          // dret
      m_x[13] = (double)dec_hour;                              // hour
      m_x[14] = (double)ny_dow0;                               // dow
      for(int k = 0; k < CR_F1_NFEAT; k++)
         if(!CrFinite(m_x[k])) return;
      datetime t_dec = hb.key + 3600;
      double score = Score();
      CrDec d;
      ZeroMemory(d);
      d.sleeve = sl;
      d.dec = t_dec;
      d.side = sig;
      d.what = CR_DEC_INFO;
      d.v1 = score;
      d.v2 = A;
      if(!CrOutDec(out, d)) JrnError(g_sl[sl].code, "more than CR_OUT_MAX decisions at " + IntegerToString((long)t_dec));
      if(!(score >= CR_F1_THR)) return;
      datetime x0 = t_dec + CR_F1_HOLD_S;
      datetime cap = F1ExitClock(t_dec);
      if(cap < x0) x0 = cap;
      CrOrder od;
      CrOrderClear(od);
      od.sleeve = sl;
      od.oid = CrOid(t_dec, m_id);
      od.side = sig;
      od.etype = CR_ET_MARKET;
      od.t_from = t_dec;
      od.t_to = t_dec + CR_F1_WAIT_S;
      od.stop_dist = CR_F1_STOP_K * A;
      od.x_sched = x0;
      od.x_gap = true;
      od.refuse = m_refuse;
      od.void_le = true;
      od.dec = t_dec;
      if(m_h2)
        {
         datetime ny = ClkUtcToNy(t_dec);
         datetime xa = ClkNyToUtc((datetime)((long)ClkBusinessDays(ClkDay(ny), CR_F1_H2_BDAYS) + CR_F1_EXIT_MIN * 60));
         datetime xb = F1FridayEnd(t_dec);                   // the entry bar lies in t_dec's server day
         od.xh = (xa < xb) ? xa : xb;
         od.xh_r = CR_F1_H2_R;
        }
      if(!CrOutOrder(out, od)) JrnError(g_sl[sl].code, "more than CR_OUT_MAX orders at " + IntegerToString((long)t_dec));
     }

   // an hour bar is complete: a session bar or nothing
   void Hour(const CrAggBar &hb, CrOut &out)
     {
      datetime ny = ClkUtcToNy(hb.key);
      int ny_hour = ClkMinOfDay(ny) / 60;
      int dow = ClkDow(ny);                                  // 0 = Sunday
      if(ny_hour < CR_F1_H0 || ny_hour >= CR_F1_H1 || dow < 1 || dow > 5) return;
      Session(hb, ny_hour, dow - 1, ClkDay(ny), out);
     }

   void OnBar(const int sym, const CrBar &b, CrOut &out)
     {
      if(sym != m_sym) return;
      CrAggBar done;
      ZeroMemory(done);
      // a bar of a new hour while the old one is still open: never under the minute contract (OnMinute closes every
      // hour at its end); the old hour is then decided here, before this bar reaches the paper
      if(m_agg.Add(b, CrAggKey(b.t, 3600), done)) Hour(done, out);
     }

   void OnMinute(const datetime M, CrOut &out)
     {
      if(M % 3600 != 0) return;
      CrAggBar cur;
      ZeroMemory(cur);
      if(!m_agg.Peek(cur) || cur.key + 3600 > M) return;
      m_agg.Take(cur);
      Hour(cur, out);
     }

   datetime LatestExit(const datetime open_time, const datetime comment_dec)
     {
      datetime t_dec = open_time - open_time % 3600;
      if(comment_dec > 0 && comment_dec % 3600 == 0 && comment_dec <= open_time && (long)(open_time - comment_dec) <= CR_F1_JOIN_S)
         t_dec = comment_dec;
      datetime x0 = t_dec + CR_F1_HOLD_S;
      datetime cap = F1ExitClock(t_dec);
      if(cap < x0) x0 = cap;
      return x0;
     }
  };
#endif

// ==== end src/CR_Rule_F1.mqh
// ==== begin src/CR_Rule_NqBtc.mqh
//+------------------------------------------------------------------+
//| CR_Rule_NqBtc.mqh - NQB nq_btc_follow: BTC follows a 6-sigma      |
//| US100 impulse (SPEC 3). Reads US100 and BTC bars. Owner: F.       |
//|                                                                  |
//| The rule (lab/r2/tracks/leadlag/strategy.py xlead_orders :188-   |
//| 238, params FINALISTS["nq_btc_follow"] :328-334, sig_days 20     |
//| :189), on a one-minute grid of UTC minutes:                      |
//|   grid   starts at the first BTC bar (_grid :98-103: the grid of |
//|          the traded frame; leader bars before it are dropped,    |
//|          _on_grid :106-110). Every minute after it is a grid     |
//|          minute, markets open or not.                            |
//|   r      per market and minute g with a bar at g: log of its mid |
//|          close over the mid close of the last bar in [g-4, g-1]  |
//|          (_ffill limit 3 :113-119, _lret k 1 :122-125); NaN when |
//|          there is no such bar or no bar at g. Mid = (bc + ac)/2  |
//|          of the paper quotes (:191, set_leader :82).             |
//|   sigma  per market at g: RMS of the finite r of the 28,800 grid |
//|          minutes up to g - 1, NaN under 4,800 of them            |
//|          (_trail_rms :128-134). Two rolling sums per market, as  |
//|          pandas makes them (CrRollSum): r x r with 0 for a       |
//|          missing r, and the count of finite r. No re-sum: pandas |
//|          never re-sums, so the robot's sigma keeps its bits.     |
//|   signal g a New York weekday minute in [09:30, 16:00) (uscash   |
//|          :168, :180-184), a BTC bar at g, x = r_US100(g) finite, |
//|          sigma_L(g) and sigma_B(g) finite, |x| >= 6 sigma_L(g)   |
//|          (:217-218). Decided at the barrier g + 1, when every bar|
//|          starting before g + 1 is final.                         |
//|   order  market, side = sign(x) (dirn 1), stop_dist = 2 x        |
//|          sigma_B(g) x sqrt(60) x the BTC mid close at g (:230,   |
//|          :234), time exit x = entry + 60 min with the gap rule   |
//|          (gl.exit_index, :229). The entry is the first BTC bar   |
//|          in [g + 1, g + 2] (:223-227). The order is emitted at   |
//|          g + 1 for the bar g + 1 (x = g + 61 min); when no BTC   |
//|          bar starts at g + 1, it is emitted again at g + 2 for   |
//|          the bar g + 2 (x = g + 62 min), with the same oid, so   |
//|          that x is always 60 minutes after the real entry bar.   |
//|          void_le: the lab keeps only orders whose exit bar       |
//|          follows the entry bar (:237 exit_i > entry_i), which is |
//|          the paper's void_le. stop_dist finite and > 0, side not |
//|          0 (:237). Every signal is emitted; the paper keeps one  |
//|          trade at a time (sim.py:80). drop_duplicates (:238)     |
//|          never binds: a signal at g' > g needs a BTC bar at g',  |
//|          so the entry bar of g comes before the one of g'.       |
//|   dec    g + 1 (the barrier that decides); oid = dec x 100 + id. |
//|          Each signal also writes one DEC info line, just before  |
//|          its first order: v1 = x, v2 = sigma_L(g).               |
//| Constants: leader us100, pred lead, k 1, z 6, sess uscash,       |
//| hold 60, stop 2.0, dirn 1, sig_days 20, delay 0                  |
//| (strategy.py:188-189, :331-332).                                 |
//|                                                                  |
//| Feeding (CR_Main minute contract): OnBar keeps the bar of each   |
//| market for its minute; OnMinute(M) processes every grid minute   |
//| before M. A bar of a later minute first processes the minutes    |
//| before it (they are complete: bars come in time order), so a     |
//| skipped OnMinute changes nothing.                                |
//|                                                                  |
//| LatestExit (SPEC 4.8): the entry is at most 5 min before the     |
//| open time o, so the paper's exit is at most o + 60 min.          |
//+------------------------------------------------------------------+
#ifndef CR_RULE_NQBTC_MQH
#define CR_RULE_NQBTC_MQH
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Clock.mqh)
// (already inlined: CR_Journal.mqh)
// (already inlined: CR_Math.mqh)

#define CR_NQB_Z 6.0                   // z: |x| >= 6 sigma_L (strategy.py:332, :217)
#define CR_NQB_STOP 2.0                // stop: 2 sigma_B sqrt(hold) x price (strategy.py:332, :234)
#define CR_NQB_HOLD_MIN 60.0           // hold in minutes, inside the stop's sqrt (strategy.py:332, :234)
#define CR_NQB_HOLD_S 3600             // hold: time exit 60 min after the entry bar (strategy.py:229)
#define CR_NQB_WIN 28800               // sigma window: sig_days 20 x 1440 grid minutes (strategy.py:189, :195)
#define CR_NQB_MINOBS 4800             // at least win // 6 finite returns (strategy.py:196)
#define CR_NQB_FFILL 3                 // the previous close may be 3 minutes older than g - 1 (_ffill, strategy.py:113)
#define CR_NQB_SESS_A 570              // uscash: from 09:30 New York (strategy.py:168)
#define CR_NQB_SESS_B 960              // to 16:00 New York, excluded; the exit need not fall inside (strategy.py:168, :183)
#define CR_NQB_DIRN 1                  // dirn: trade the side of the leader's move (strategy.py:233, :331)
#define CR_NQB_L 0                     // series of the leader (US100)
#define CR_NQB_F 1                     // series of the follower (BTC)

class CRuleNqb
  {
public:
   int       sl;
   int       m_id;                     // sleeve id (oid = decision x 100 + id)
   int       m_sym[2];                 // symbol id of the leader and of the follower
   bool      m_started;                // the grid has started (the first BTC bar was seen)
   long      m_next;                   // next grid minute to process (minutes since 1970)
   bool      m_pend[2];                // a bar waits for its grid minute
   long      m_pend_m[2];              // its minute
   double    m_pend_c[2];              // its mid close
   bool      m_last_ok[2];             // a bar was processed on the grid
   long      m_last_m[2];              // minute of the last bar processed (the forward fill)
   double    m_last_c[2];              // its mid close
   CrRollSum m_s2[2];                  // rolling sum of r x r (0 for a missing r), 28,800 grid minutes
   CrRollSum m_n[2];                   // rolling sum of 1 for a finite r, 0 otherwise
   bool      m_pd;                     // the signal of the last grid minute: its first entry minute is still to be seen
   long      m_pd_g;                   // its decision minute g
   int       m_pd_side;
   double    m_pd_sd;
   long      m_g;                      // the last grid minute processed (tests and diagnosis)
   double    m_r[2];                   // its r: x = r of the leader, r of BTC
   double    m_sig[2];                 // its sigma: RMS of the window that ends at the minute before
   long      m_signals;                // signals since Init

   bool Init(const int sleeve)
     {
      sl = sleeve;
      m_id = g_sl[sl].id;
      m_sym[CR_NQB_L] = g_sl[sl].sym2;
      m_sym[CR_NQB_F] = g_sl[sl].sym;
      m_started = false;
      m_next = 0;
      for(int s = 0; s < 2; s++)
        {
         m_pend[s] = false;
         m_pend_m[s] = 0;
         m_pend_c[s] = 0.0;
         m_last_ok[s] = false;
         m_last_m[s] = 0;
         m_last_c[s] = 0.0;
         m_s2[s].Init(CR_NQB_WIN, 1);
         m_n[s].Init(CR_NQB_WIN, 1);
         m_r[s] = CrNaN();
         m_sig[s] = CrNaN();
        }
      m_pd = false;
      m_pd_g = 0;
      m_pd_side = 0;
      m_pd_sd = 0.0;
      m_g = 0;
      m_signals = 0;
      if(m_sym[CR_NQB_L] < 0 || m_sym[CR_NQB_L] >= CR_NSYM || m_sym[CR_NQB_L] == m_sym[CR_NQB_F]) return false;
      return true;
     }

   // sigma of series s over the window pushed so far (_trail_rms :131-133, before its one-minute lag)
   double Rms(const int s)
     {
      double cnt = m_n[s].Sum();
      if(!(cnt >= CR_NQB_MINOBS)) return CrNaN();
      double s2 = m_s2[s].Sum();
      if(s2 < 0.0) s2 = 0.0;                                   // np.maximum(s2, 0.0)
      return MathSqrt(s2 / cnt);                               // cnt >= 4,800: np.maximum(cnt, 1.0) is cnt
     }

   // an order of the signal decided at minute g, for the entry bar of minute e (g + 1, or g + 2 the second time)
   void Emit(const long g, const long e, const int side, const double sd, CrOut &out)
     {
      datetime dec = (datetime)((g + 1) * 60);
      CrOrder o;
      CrOrderClear(o);
      o.sleeve = sl;
      o.oid = CrOid(dec, m_id);
      o.side = side;
      o.etype = CR_ET_MARKET;
      o.t_from = (datetime)(e * 60);
      o.t_to = o.t_from;
      o.stop_dist = sd;
      o.x_sched = o.t_from + CR_NQB_HOLD_S;
      o.x_gap = true;
      o.void_le = true;
      o.dec = dec;
      if(!CrOutOrder(out, o)) JrnError(g_sl[sl].code, "more than CR_OUT_MAX orders at " + IntegerToString((long)dec));
     }

   // one grid minute g: the returns, the sigmas (lagged), the second entry minute of the signal of g - 1, the signal of g
   void GridMinute(const long g, CrOut &out)
     {
      bool has[2];
      double c[2];
      for(int s = 0; s < 2; s++)
        {
         has[s] = m_pend[s] && m_pend_m[s] == g;
         c[s] = has[s] ? m_pend_c[s] : 0.0;
         m_sig[s] = Rms(s);                                    // the window ends at g - 1 (np.r_[nan, s[:-1]])
         double r = CrNaN();
         if(has[s] && m_last_ok[s] && g - 1 - m_last_m[s] <= CR_NQB_FFILL) r = MathLog(c[s] / m_last_c[s]);
         m_r[s] = r;
         bool ok = CrFinite(r);
         m_s2[s].Push(ok ? r * r : 0.0);
         m_n[s].Push(ok ? 1.0 : 0.0);
         if(has[s])
           {
            m_last_ok[s] = true;
            m_last_m[s] = g;
            m_last_c[s] = c[s];
            m_pend[s] = false;
           }
        }
      m_g = g;
      if(m_pd)
        {
         // the first entry minute of the signal of g - 1 had no BTC bar: its order is emitted again for the next minute
         if(m_pd_g == g - 1 && !has[CR_NQB_F]) Emit(m_pd_g, g + 1, m_pd_side, m_pd_sd, out);
         m_pd = false;
        }
      double x = m_r[CR_NQB_L];
      double sig_l = m_sig[CR_NQB_L];
      double sig_b = m_sig[CR_NQB_F];
      if(!has[CR_NQB_F] || !CrFinite(x) || !CrFinite(sig_l) || !CrFinite(sig_b)) return;
      if(!(MathAbs(x) >= CR_NQB_Z * sig_l)) return;
      datetime ny = ClkUtcToNy((datetime)(g * 60));
      int mod = ClkMinOfDay(ny);
      int dow = ClkDow(ny);                                    // 1 = Monday ... 5 = Friday
      if(mod < CR_NQB_SESS_A || mod >= CR_NQB_SESS_B || dow < 1 || dow > 5) return;
      int side = 0;
      if(x > 0.0) side = CR_NQB_DIRN;
      else if(x < 0.0) side = -CR_NQB_DIRN;
      double sd = CR_NQB_STOP * sig_b * MathSqrt(CR_NQB_HOLD_MIN) * c[CR_NQB_F];
      if(side == 0 || !CrFinite(sd) || !(sd > 0.0)) return;
      m_signals++;
      CrDec d;
      ZeroMemory(d);
      d.sleeve = sl;
      d.dec = (datetime)((g + 1) * 60);
      d.side = side;
      d.what = CR_DEC_INFO;
      d.v1 = x;
      d.v2 = sig_l;
      if(!CrOutDec(out, d)) JrnError(g_sl[sl].code, "more than CR_OUT_MAX decisions at " + IntegerToString((long)d.dec));
      Emit(g, g + 1, side, sd, out);
      m_pd = true;
      m_pd_g = g;
      m_pd_side = side;
      m_pd_sd = sd;
     }

   // every grid minute up to gmax, in order
   void ProcessUpTo(const long gmax, CrOut &out)
     {
      while(m_next <= gmax)
        {
         GridMinute(m_next, out);
         m_next++;
        }
     }

   void OnBar(const int sym, const CrBar &b, CrOut &out)
     {
      int s = -1;
      if(sym == m_sym[CR_NQB_F]) s = CR_NQB_F;
      else if(sym == m_sym[CR_NQB_L]) s = CR_NQB_L;
      if(s < 0) return;
      long m = (long)b.t / 60;
      double c = (b.bc + b.ac) / 2;
      if(!m_started)
        {
         if(s == CR_NQB_L)
           {
            m_pend[s] = true;                                  // kept only if the grid starts in its minute
            m_pend_m[s] = m;
            m_pend_c[s] = c;
            return;
           }
         m_started = true;
         m_next = m;
         if(m_pend[CR_NQB_L] && m_pend_m[CR_NQB_L] != m) m_pend[CR_NQB_L] = false;
        }
      if(m < m_next) return;                                   // a bar of a minute already processed: never under the contract
      if(m > m_next) ProcessUpTo(m - 1, out);                  // the minutes before this bar are complete
      m_pend[s] = true;
      m_pend_m[s] = m;
      m_pend_c[s] = c;
     }

   void OnMinute(const datetime M, CrOut &out)
     {
      if(!m_started) return;
      long gmax = (long)M / 60 - 1;
      if(gmax >= m_next) ProcessUpTo(gmax, out);
     }

   datetime LatestExit(const datetime open_time, const datetime comment_dec)
     {
      return open_time + CR_NQB_HOLD_S;
     }
  };
#endif

// ==== end src/CR_Rule_NqBtc.mqh
// ==== begin src/CR_Rule_GoldFri.mqh
//+------------------------------------------------------------------+
//| CR_Rule_GoldFri.mqh - GFP GOLD_FRI_PM: Friday 13:30 NY buy limit  |
//| on gold (SPEC 3). Owner: G.                                       |
//|                                                                  |
//| The rule (lab/r2/tracks/overnight/strategy.py, make_orders       |
//| :100-211, _atr :71-97, FINALISTS :240-245):                      |
//|   params {tz NY, entry 13:30, exit 16:45, weekdays (4,), side 1, |
//|   stop_atr 3, atr_n 14, atr_tf 1h, entry_type limit, limit_min   |
//|   60, min_prev 0, skip_early_close True} (:243-244) and the      |
//|   default tol_min 5 (:102).                                      |
//|   ATR    Wilder ATR(14) of UTC hour bars of the gold kept bars   |
//|          (:71-97): h = (max bid high + max ask high) / 2, l =    |
//|          (min bid low + min ask low) / 2, c = mid close of the   |
//|          hour's last bar; TR = max(h - l, |h - pc|, |l - pc|),   |
//|          NaN for the first hour (np.maximum keeps NaN), so the   |
//|          Wilder mean (pandas ewm alpha 1/14, adjust False:       |
//|          CrWilder) is seeded with the second hour's TR; the      |
//|          first 14 hour rows are NaN (:96). An hour counts once   |
//|          its nominal end has passed (:78): the decision at 13:30 |
//|          reads the last hour that ended by 13:30 (the 12:00      |
//|          hour when it has bars, :157-158).                       |
//|   order  every Friday (New York date) at 13:30 New York, in      |
//|          OnMinute(13:30), when every bar before 13:30 has been   |
//|          fed: a buy limit at the paper bid close of the last kept|
//|          bar before 13:30 (:205), activation window [13:30,      |
//|          13:35] (the first kept bar within tol_min 5, :60-68),   |
//|          fills on bars starting before 14:30 (limit_min 60,      |
//|          :206-207), stop_dist 3 x ATR (:198), time exit at the   |
//|          first kept bar at or after 16:45 New York with no gap   |
//|          rule (:133, 152).                                       |
//|   skips  (SPEC 3, R8) instead of the lab's after-the-fact test   |
//|          (:129-137: no quote within 10 min of 16:45), which reads|
//|          a future bar: a NYSE full holiday or half day           |
//|          (ClkNyse: us_holidays plus the typed NYSE and HALF      |
//|          entries), a known XAU closure that starts before 16:55  |
//|          (the closure holding 13:30, or the next one: ClkNext-   |
//|          Closure), or a broker Friday session that does not hold |
//|          13:30 or ends before 16:55 (SymbolInfoSessionTrade; no  |
//|          information = no skip). In 2013-2021 this skips the     |
//|          same 26 Fridays as the lab: Good Friday, July 4,        |
//|          Christmas and New Year (no gold bar at 13:30) and the   |
//|          Friday after Thanksgiving (last bar 13:42-14:05). The   |
//|          lab also skips Fridays whose data has a hole at 16:45   |
//|          (2013-05-31 in sample, data to 16:39): the robot cannot |
//|          see a future hole, so these "GFP hole days" are listed  |
//|          by check/test_GFP.py, never silent (SPEC 7).            |
//|          Each skipped Friday writes a DEC info line: side 0,     |
//|          v1 = the reason code below, v2 = its detail.            |
//|                                                                  |
//| LatestExit (SPEC 4.8): 16:45 New York on the New York date of the|
//|   open time (the order lives 13:30-14:30 and the real fill is a  |
//|   bar later, so the date is always the decision's). The comment's|
//|   decision, when it is a Friday 13:30 New York at most 66 min    |
//|   before the open, gives the same date: it is only a cross-check.|
//+------------------------------------------------------------------+
#ifndef CR_RULE_GOLDFRI_MQH
#define CR_RULE_GOLDFRI_MQH
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Clock.mqh)
// (already inlined: CR_Journal.mqh)
// (already inlined: CR_Math.mqh)

#define CR_GFP_DOW 5                   // weekdays (4,): pandas Friday = ClkDow 5 (strategy.py:243)
#define CR_GFP_ENTRY_MIN 810           // entry 13:30 New York (:243)
#define CR_GFP_EXIT_MIN 1005           // exit 16:45 New York (:243)
#define CR_GFP_OPEN_MIN 1015           // 16:55: a quote within 10 min of 16:45 (skip_early_close, :136)
#define CR_GFP_TOL_S 300               // tol_min 5: the first kept bar starting in [13:30, 13:35] (:65, :102)
#define CR_GFP_LIMIT_S 3600            // limit_min 60: fills on bars starting before 14:30 (:206)
#define CR_GFP_STOP_ATR 3.0            // stop_atr 3 (:243)
#define CR_GFP_ATR_N 14                // atr_n 14 (:243): Wilder 1/14 (:95), rows 0-13 NaN (:96)
#define CR_GFP_HOUR_S 3600             // atr_tf 1h: UTC hours (:76-78)
#define CR_GFP_JOIN_S 3960             // LatestExit: a real open at most 66 min after 13:30 (60 min of limit, a bar, 5 min)
// ---- reasons of a skipped Friday (DEC info v1)
#define CR_GFP_SKIP_FULL 1             // NYSE full holiday (v2 0)
#define CR_GFP_SKIP_HALF 2             // NYSE half day (v2 0)
#define CR_GFP_SKIP_CLOSURE 3          // a known XAU closure starts before 16:55 (v2 = its start, UTC)
#define CR_GFP_SKIP_SESSION 4          // the broker session does not hold 13:30 or ends before 16:55 (v2 = its end, server s of day; -1 none)
#define CR_GFP_SKIP_ATR 5              // ATR not finite or not > 0 (v2 = hour rows so far)
#define CR_GFP_SKIP_NOBAR 6            // no kept bar before 13:30 yet (v2 0)

// a broker trade session [from, to) of a day (SymbolInfoSessionTrade: seconds from 00:00, the date ignored; an end at
// or before the start, 00:00 included, runs to the end of the day): does it hold the server time of day a? end_s = its
// end in seconds of the day (86400 = midnight)
bool GfpSessionHoldsAt(const long from_s, const long to_s, const long a, long &end_s)
  {
   long f = from_s % 86400;
   long t = to_s % 86400;
   if(f < 0) f += 86400;
   if(t < 0) t += 86400;
   if(t <= f) t = 86400;
   end_s = t;
   return f <= a && a < t;
  }

// SPEC 3 GFP: the broker's Friday trade sessions of sym against 13:30 (t0) and 16:55 (t1) New York, UTC. Returns true
// (skip) when the broker lists sessions and none holds 13:30 and runs to 16:55 or later; end_s = the latest end of a
// session holding 13:30 (server seconds of the day), -1 when none holds it. No session listed: false (no
// information, no skip; the harness broker lists none).
bool GfpSessionShort(const string sym, const datetime t0, const datetime t1, long &end_s)
  {
   end_s = -1;
   long a = (long)ClkUtcToServer(t0) % 86400;
   long b = (long)ClkUtcToServer(t1) % 86400;
   if(b <= a) b = 86400;
   int n = 0;
   for(int k = 0; k < 32; k++)
     {
      datetime from = 0, to = 0;
      if(!SymbolInfoSessionTrade(sym, FRIDAY, (uint)k, from, to)) break;
      n++;
      long e = 0;
      if(!GfpSessionHoldsAt((long)from, (long)to, a, e)) continue;
      if(e > end_s) end_s = e;
      if(e >= b) return false;
     }
   return n > 0;
  }

// the time exit of a decision on New York date ny_day (00:00, New York clock): 16:45 New York, UTC
datetime GfpExitTime(const datetime ny_day) { return ClkNyToUtc(ny_day + CR_GFP_EXIT_MIN * 60); }

// the calendar part of the decision at t0 (13:30 New York of a Friday, UTC): 0 = trade, else CR_GFP_SKIP_* and v2
int GfpCalendarSkip(const datetime t0, const string sym, double &v2)
  {
   v2 = 0.0;
   datetime day = ClkDay(ClkUtcToNy(t0));
   int k = ClkNyse(day);
   if(k == CR_NYSE_FULL) return CR_GFP_SKIP_FULL;
   if(k == CR_NYSE_HALF) return CR_GFP_SKIP_HALF;
   datetime t1 = ClkNyToUtc(day + CR_GFP_OPEN_MIN * 60);
   datetime c0 = 0, c1 = 0;
   if(ClkNextClosure(CR_FAM_XAU, t0, c0, c1) && c0 < t1)
     {
      v2 = (double)c0;
      return CR_GFP_SKIP_CLOSURE;
     }
   long end_s = -1;
   if(GfpSessionShort(sym, t0, t1, end_s))
     {
      v2 = (double)end_s;
      return CR_GFP_SKIP_SESSION;
     }
   return 0;
  }

// is M (UTC) 13:30 New York on a Friday?
bool GfpIsDecision(const datetime M)
  {
   datetime ny = ClkUtcToNy(M);
   return ClkDow(ny) == CR_GFP_DOW && ClkMinOfDay(ny) == CR_GFP_ENTRY_MIN && (long)ny % 60 == 0;
  }

class CRuleGfp
  {
public:
   int       sl;
   int       m_sym;                    // gold
   int       m_id;                     // sleeve id (oid = decision x 100 + id)
   CrAgg     m_agg;                    // the UTC hour being filled
   CrWilder  m_atr;                    // Wilder ATR(14) of the hour bars
   long      m_nh;                     // hour rows pushed (the lab's row number + 1)
   double    m_pc;                     // close of the previous hour row
   bool      m_bar;                    // a kept bar was seen
   double    m_bc;                     // paper bid close of the last kept bar

   bool Init(const int sleeve)
     {
      sl = sleeve;
      m_sym = g_sl[sl].sym;
      m_id = g_sl[sl].id;
      m_agg.Clear();
      m_atr.Init(CR_GFP_ATR_N);
      m_nh = 0;
      m_pc = 0.0;
      m_bar = false;
      m_bc = 0.0;
      return m_sym == CR_XAU;                                 // a gold rule: its calendar is the XAU one
     }

   // an hour row is complete: its true range enters the Wilder mean (_atr :89-95)
   void HourDone(const CrAggBar &hb)
     {
      double h = (hb.bh + hb.ah) / 2;
      double l = (hb.bl + hb.al) / 2;
      double c = (hb.bc + hb.ac) / 2;
      double tr = CrNaN();                                    // the first row: pc is NaN, np.maximum keeps it
      if(m_nh > 0)
        {
         double a = MathAbs(h - m_pc);
         double b = MathAbs(l - m_pc);
         double m = (a >= b) ? a : b;
         tr = h - l;
         if(m > tr) tr = m;
        }
      m_atr.Push(tr);
      m_pc = c;
      m_nh++;
     }

   // the ATR the lab reads at a decision: NaN during the warm-up (rows 0-13)
   double AtrNow()
     {
      if(m_nh <= CR_GFP_ATR_N) return CrNaN();
      return m_atr.Value();
     }

   void SkipLine(const datetime M, const int code, const double v2, CrOut &out)
     {
      CrDec d;
      ZeroMemory(d);
      d.sleeve = sl;
      d.dec = M;
      d.side = 0;
      d.what = CR_DEC_INFO;
      d.v1 = (double)code;
      d.v2 = v2;
      if(!CrOutDec(out, d)) JrnError(g_sl[sl].code, "more than CR_OUT_MAX decisions at " + IntegerToString((long)M));
     }

   void DecideAt(const datetime M, CrOut &out)
     {
      double v2 = 0.0;
      int code = GfpCalendarSkip(M, g_sym[m_sym].name, v2);
      double atr = AtrNow();
      if(code == 0 && !m_bar) code = CR_GFP_SKIP_NOBAR;
      if(code == 0 && !(CrFinite(atr) && atr > 0.0))
        {
         code = CR_GFP_SKIP_ATR;
         v2 = (double)m_nh;
        }
      if(code != 0)
        {
         SkipLine(M, code, v2, out);
         return;
        }
      CrOrder o;
      CrOrderClear(o);
      o.sleeve = sl;
      o.oid = CrOid(M, m_id);
      o.side = 1;
      o.etype = CR_ET_LIMIT;
      o.level = m_bc;
      o.t_from = M;
      o.t_to = M + CR_GFP_TOL_S;
      o.expiry_excl = M + CR_GFP_LIMIT_S;
      o.stop_dist = CR_GFP_STOP_ATR * atr;
      o.x_sched = GfpExitTime(ClkDay(ClkUtcToNy(M)));
      o.x_gap = false;
      o.dec = M;
      if(!CrOutOrder(out, o)) JrnError(g_sl[sl].code, "more than CR_OUT_MAX orders at " + IntegerToString((long)M));
     }

   void OnBar(const int sym, const CrBar &b, CrOut &out)
     {
      if(sym != m_sym) return;
      CrAggBar done;
      ZeroMemory(done);
      // a bar of a new hour while the old one is open: under the minute contract OnMinute has closed it already
      if(m_agg.Add(b, CrAggKey(b.t, CR_GFP_HOUR_S), done)) HourDone(done);
      m_bc = b.bc;
      m_bar = true;
     }

   void OnMinute(const datetime M, CrOut &out)
     {
      CrAggBar cur;
      ZeroMemory(cur);
      if(m_agg.Peek(cur) && cur.key + CR_GFP_HOUR_S <= M)   // every bar of that hour has been fed
        {
         m_agg.Take(cur);
         HourDone(cur);
        }
      if(GfpIsDecision(M)) DecideAt(M, out);
     }

   datetime LatestExit(const datetime open_time, const datetime comment_dec)
     {
      datetime day = ClkDay(ClkUtcToNy(open_time));
      if(comment_dec > 0 && comment_dec <= open_time && (long)(open_time - comment_dec) <= CR_GFP_JOIN_S && GfpIsDecision(comment_dec))
         day = ClkDay(ClkUtcToNy(comment_dec));
      return GfpExitTime(day);
     }
  };
#endif

// ==== end src/CR_Rule_GoldFri.mqh
// ==== begin src/CR_Rule_Orb.mqh
//+------------------------------------------------------------------+
//| CR_Rule_Orb.mqh - ORX orb_asia_2d_buf10: London 00:00-07:00 range |
//| breakout on gold (SPEC 3). Owner: G.                              |
//|                                                                  |
//| The rule (lab/tracks/orb/strategy.py: sessions :139-181,         |
//| make_orders :184-271, _range_stats :72-92, _first_touch :95-119, |
//| FINALISTS :276-287):                                             |
//|   params {tz LDN, range 00:00-07:00, entry_end 12:00, entry stop,|
//|   buf_frac 0.1, buf_abs 0, stop_mode opp, exit_time 16:00 NY,    |
//|   hold_days 2, min_bars_frac 0.5, sides both, no target, no      |
//|   break-even, no trail, no width or cost filter} (:276-287).     |
//|   days   London weekday dates (:144-145).                        |
//|   range  the kept bars starting in [00:00, 07:00) London of the  |
//|          date: H = max ask high, L = min bid low, n bars         |
//|          (:156-164). Valid when n >= 210 (0.5 x 420 minutes,     |
//|          :167-169) and W = H - L > 0 (:200). Levels H + 0.1 W    |
//|          and L - 0.1 W (:202-204).                               |
//|   touch  the first kept bar starting in [07:00, 12:00) London    |
//|          whose ask high reaches the upper level (long) or whose  |
//|          bid low reaches the lower one (short); both in one bar: |
//|          the level nearer the bar's mid open, a tie long         |
//|          (_first_touch :104-118). It uses the day up, whatever   |
//|          the paper's state (the lab finds it on the bars alone). |
//|   order  from OnBar of that bar, before the paper sees it: a stop|
//|          order at the touched level, window = that bar (t_from = |
//|          t_to = its start) and filling only on it (expiry_excl = |
//|          start + 60 s; the lab's expiry_i = entry_i, :265),      |
//|          absolute stop = the other level (:246-247), time exit at|
//|          the first kept bar at or after 16:00 New York on        |
//|          BusinessDays(London date, 2), no gap rule (:149-152,    |
//|          159). The paper skips it when the sleeve is busy        |
//|          (sim.py:80), as the lab does.                           |
//|   Bit for bit: H, L and n come from the same bars; W, the buffer,|
//|   the levels and the tie test use the lab's own expressions in   |
//|   its order (0.1 x W + 0.0, H + buf, L - buf, 0.5 x (ao + bo)).  |
//|   A weekday whose range is not valid writes one DEC info line at |
//|   its first bar in [07:00, 12:00): side 0, v1 = 1 (fewer than    |
//|   210 bars; v2 = n) or 2 (W not > 0; v2 = W).                    |
//|                                                                  |
//| Retired ids: SPEC 2.3. Ids 11 and 12 were this rule on BTC and   |
//|   ETH (K2, K3); they failed the 2022-2025 look and are dropped   |
//|   for good, like every id 11-19. Init refuses a retired id and a |
//|   symbol other than gold, so a registry row for them cannot run. |
//|                                                                  |
//| LatestExit (SPEC 4.8): 16:00 New York on BusinessDays(London date|
//|   of the open time, 2). The order fills in [07:00, 12:00) London |
//|   and the real fill comes one bar later, so the London date of   |
//|   the open is the decision's; a comment decision in that window  |
//|   of the same date, before the open, gives the same exit.        |
//+------------------------------------------------------------------+
#ifndef CR_RULE_ORB_MQH
#define CR_RULE_ORB_MQH
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Clock.mqh)
// (already inlined: CR_Journal.mqh)
// (already inlined: CR_Math.mqh)

#define CR_ORX_RANGE_END_MIN 420       // range 00:00-07:00 London (strategy.py:278)
#define CR_ORX_ENTRY_END_MIN 720       // entry_end 12:00 London (:279)
#define CR_ORX_MIN_BARS 210            // min_bars_frac 0.5 x 420 expected minutes (:285, :167-169)
#define CR_ORX_BUF_FRAC 0.1            // buf_frac 0.1 (:280)
#define CR_ORX_BUF_ABS 0.0             // buf_abs 0.0 (:280)
#define CR_ORX_EXIT_MIN 960            // exit_time 16:00, exit_tz NY (:283)
#define CR_ORX_HOLD_DAYS 2             // hold_days 2 business days (:283, :149)
#define CR_ORX_RETIRED_LO 11           // SPEC 2.3: ids 11-19 retired (11, 12 = this rule on BTC, ETH)
#define CR_ORX_RETIRED_HI 19
// ---- an invalid range (DEC info v1)
#define CR_ORX_SKIP_BARS 1             // fewer than 210 range bars (v2 = n)
#define CR_ORX_SKIP_WIDTH 2            // W = H - L not > 0 (v2 = W)

// the time exit of a London date (00:00, London clock): 16:00 New York on BusinessDays(date, 2) (:149-152), UTC
datetime OrxExitTime(const datetime ldn_day)
  {
   return ClkNyToUtc(ClkBusinessDays(ldn_day, CR_ORX_HOLD_DAYS) + CR_ORX_EXIT_MIN * 60);
  }

// is t (UTC) inside the entry window [07:00, 12:00) of a London weekday?
bool OrxInWindow(const datetime t)
  {
   datetime ldn = ClkUtcToLdn(t);
   int dow = ClkDow(ldn);
   int mod = ClkMinOfDay(ldn);
   return dow >= 1 && dow <= 5 && mod >= CR_ORX_RANGE_END_MIN && mod < CR_ORX_ENTRY_END_MIN;
  }

class CRuleOrx
  {
public:
   int       sl;
   int       m_sym;                    // gold
   int       m_id;                     // sleeve id (oid = decision x 100 + id)
   datetime  m_day;                    // London date (00:00, London clock) of the range below, 0 = none
   int       m_n;                      // range bars
   double    m_hi;                     // max ask high of the range bars
   double    m_lo;                     // min bid low of the range bars
   bool      m_used;                   // m_day's entry window is used up (a touch, or an invalid range)

   bool Init(const int sleeve)
     {
      sl = sleeve;
      m_sym = g_sl[sl].sym;
      m_id = g_sl[sl].id;
      m_day = 0;
      m_n = 0;
      m_hi = 0.0;
      m_lo = 0.0;
      m_used = false;
      if(m_id >= CR_ORX_RETIRED_LO && m_id <= CR_ORX_RETIRED_HI) return false;
      return m_sym == CR_XAU;
     }

   void SkipLine(const datetime t, const int code, const double v2, CrOut &out)
     {
      CrDec d;
      ZeroMemory(d);
      d.sleeve = sl;
      d.dec = t;
      d.side = 0;
      d.what = CR_DEC_INFO;
      d.v1 = (double)code;
      d.v2 = v2;
      if(!CrOutDec(out, d)) JrnError(g_sl[sl].code, "more than CR_OUT_MAX decisions at " + IntegerToString((long)t));
     }

   // bar b of the entry window of m_day, the day not used up yet
   void WindowBar(const CrBar &b, CrOut &out)
     {
      if(m_n < CR_ORX_MIN_BARS)
        {
         SkipLine(b.t, CR_ORX_SKIP_BARS, (double)m_n, out);
         m_used = true;
         return;
        }
      double w = m_hi - m_lo;
      if(!(w > 0.0))
        {
         SkipLine(b.t, CR_ORX_SKIP_WIDTH, w, out);
         m_used = true;
         return;
        }
      double buf = CR_ORX_BUF_FRAC * w + CR_ORX_BUF_ABS;
      double buy = m_hi + buf;
      double sell = m_lo - buf;
      bool up = (b.ah >= buy);
      bool dn = (b.bl <= sell);
      if(!up && !dn) return;
      int side = up ? 1 : -1;
      if(up && dn)
        {
         double mo = 0.5 * (b.ao + b.bo);
         side = (MathAbs(buy - mo) <= MathAbs(mo - sell)) ? 1 : -1;
        }
      m_used = true;
      CrOrder o;
      CrOrderClear(o);
      o.sleeve = sl;
      o.oid = CrOid(b.t, m_id);
      o.side = side;
      o.etype = CR_ET_STOP;
      o.level = (side > 0) ? buy : sell;
      o.t_from = b.t;
      o.t_to = b.t;
      o.expiry_excl = b.t + 60;
      o.stop = (side > 0) ? sell : buy;
      o.x_sched = OrxExitTime(m_day);
      o.x_gap = false;
      o.dec = b.t;
      if(!CrOutOrder(out, o)) JrnError(g_sl[sl].code, "more than CR_OUT_MAX orders at " + IntegerToString((long)b.t));
     }

   void OnBar(const int sym, const CrBar &b, CrOut &out)
     {
      if(sym != m_sym) return;
      datetime ldn = ClkUtcToLdn(b.t);
      int dow = ClkDow(ldn);
      if(dow < 1 || dow > 5) return;                           // London weekdays only (:145)
      datetime day = ClkDay(ldn);
      if(day != m_day)
        {
         m_day = day;
         m_n = 0;
         m_hi = 0.0;
         m_lo = 0.0;
         m_used = false;
        }
      int mod = ClkMinOfDay(ldn);
      if(mod < CR_ORX_RANGE_END_MIN)                             // the range [00:00, 07:00) (_range_stats :79-91)
        {
         if(m_n == 0 || b.ah > m_hi) m_hi = b.ah;
         if(m_n == 0 || b.bl < m_lo) m_lo = b.bl;
         m_n++;
         return;
        }
      if(mod >= CR_ORX_ENTRY_END_MIN || m_used) return;
      WindowBar(b, out);
     }

   void OnMinute(const datetime M, CrOut &out) {}

   datetime LatestExit(const datetime open_time, const datetime comment_dec)
     {
      datetime day = ClkDay(ClkUtcToLdn(open_time));
      if(comment_dec > 0 && comment_dec <= open_time && OrxInWindow(comment_dec) && ClkDay(ClkUtcToLdn(comment_dec)) == day)
         day = ClkDay(ClkUtcToLdn(comment_dec));
      return OrxExitTime(day);
     }
  };
#endif

// ==== end src/CR_Rule_Orb.mqh
// ==== begin src/CR_Rule_Donch.mqh
//+------------------------------------------------------------------+
//| CR_Rule_Donch.mqh - D4H donch4h_stop: 60 x 4h channel OCO with a  |
//| 2-ATR trailing stop on gold (SPEC 3). Owner: H.                   |
//|                                                                  |
//| The rule (lab/tracks/trend/strategy.py: finalist :427-429,       |
//| _donchian :235-245, _donchian_stop :257-288):                    |
//|   bars   UTC 4h bars of the kept gold M1 bars (goldlab/data.py   |
//|          bars :61-77: resample 4h, closed and labelled left).    |
//|          Bid and ask are aggregated apart (first open, max high, |
//|          min low, last close); mid h = (bh + ah) / 2, l = (bl +  |
//|          al) / 2, c = (bc + ac) / 2; t_close = the start of the  |
//|          bucket's last bar + 1 min. A bucket without a bar does  |
//|          not exist.                                              |
//|   ATR    gl.atr (data.py:88-92): TR = max(h - l, |h - pc|,       |
//|          |l - pc|), pc = the previous 4h bar's c. The first bar  |
//|          has no pc, so its TR is NaN and the Wilder mean         |
//|          (ewm alpha 1/14, adjust False: CrWilder) starts with    |
//|          the second bar's TR.                                    |
//|   levels up = the highest h, dn = the lowest l of the last 60    |
//|          4h bars, this one included (rolling(60), :261-262).     |
//|   order  after each 4h bar whose up, dn and ATR are finite: an   |
//|          OCO, buy stop at up and sell stop at dn (:279-281). It  |
//|          activates on the first kept bar at or after t_close     |
//|          (gl.entry_index, :264) and fills only on the bars of    |
//|          that bar's 4h bucket (the lab's window [i0, i1], :265). |
//|          Both levels touched in one bar: the side against the    |
//|          bar's move (_first_touch :293-318, done by CR_Paper).   |
//|          stop_dist = trail = 2 ATR (:282-283); time exit x =     |
//|          AddTradingDays(t_close, 5) - 5 min (:275) with the gap  |
//|          rule (exit_index :114-124). The paper skips the order   |
//|          whole when its trade is open, or exited, on the         |
//|          activation bar (sim.py:80).                             |
//| The order is emitted from OnBar of the first bar of the next     |
//| bucket: that bar is its activation bar, and it reaches the paper |
//| right after OnBar (SPEC 2.4). So each OCO's span ends before the |
//| next one starts.                                                 |
//| Constants (strategy.py:427-429; DEFAULTS :44-56): tf 4h, grid    |
//| utc, n 60, entry stop, stop_atr 2, trail_atr 2, max_days 5,      |
//| atr_n 14, target_r none, sides both, sess none, trend_ma 0.      |
//|                                                                  |
//| Not reproduced (SPEC 7 HOLE_RULE: the lab's test reads a future  |
//| bar): the lab keeps an order only when its exit bar comes after  |
//| its fill bar (:277, xi > hit_i). The paper exits such a trade at |
//| the first kept bar after x instead. It needs a hole of about 5   |
//| trading days in the gold data next to the fill. It never happens |
//| in sample; check/test_D4H.py counts it.                          |
//|                                                                  |
//| A rebuild starts from the load window (120 days of gold, SPEC    |
//| 2.2). The first bucket fed after Init is used only when it is    |
//| whole: its first bar starts on the 4h boundary, or the time      |
//| before that bar lies in a known gold closure. A bucket cut by    |
//| the load gives its close only (for the next bar's TR).           |
//|                                                                  |
//| LatestExit (SPEC 4.8): B = the latest 4h UTC boundary at or      |
//|   before the open time. The comment's decision is used when it   |
//|   is a whole minute at most 4 days before B (in sample at most   |
//|   70 h; the longest wait from a t_close to the next bar is       |
//|   76.5 h). Else the latest decision consistent with the open is  |
//|   taken: B, or 23:59 server on the Friday before B when B falls  |
//|   on a server weekend. AddTradingDays keeps the time of day, so a|
//|   Friday 23:59 decision exits later than a Sunday one: B alone   |
//|   would not be an upper bound there. Exit = AddTradingDays(that, |
//|   5) - 5 min.                                                    |
//+------------------------------------------------------------------+
#ifndef CR_RULE_DONCH_MQH
#define CR_RULE_DONCH_MQH
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Clock.mqh)
// (already inlined: CR_Journal.mqh)
// (already inlined: CR_Math.mqh)

#define CR_D4H_TF_S 14400              // tf 4h on the UTC grid (strategy.py:427, grid utc; data.py:72 resample)
#define CR_D4H_N 60                    // channel length in 4h bars (strategy.py:427)
#define CR_D4H_ATR_N 14                // Wilder ATR length (strategy.py:428)
#define CR_D4H_STOP_ATR 2.0            // initial stop distance in ATR (strategy.py:428)
#define CR_D4H_TRAIL_ATR 2.0           // trailing distance in ATR (strategy.py:428)
#define CR_D4H_MAX_DAYS 5              // time exit: 5 New York trading days after t_close (strategy.py:428)
#define CR_D4H_BACK_S 300              // ... minus 5 minutes (strategy.py:275)
#define CR_D4H_JOIN_S 345600           // LatestExit: a comment decision at most 4 days before B

// the time exit of a decision at t_close (strategy.py:275): AddTradingDays(t_close, 5) - 5 min
datetime DonchExitTime(const datetime t_close) { return ClkAddTradingDays(t_close, CR_D4H_MAX_DAYS) - CR_D4H_BACK_S; }

// is the bucket `key` whole when t, the first bar fed since Init, opens it? Yes when t is the boundary itself, or when
// a known gold closure covers [key, t) (a session that opened inside the bucket). Else the load may have cut it.
bool DonchWhole(const datetime t, const datetime key)
  {
   if(t == key) return true;
   datetime c0 = 0, c1 = 0;
   if(!ClkInClosure(CR_FAM_XAU, key, c0, c1)) return false;
   return c1 >= t;
  }

class CRuleDonch
  {
public:
   int       sl;
   int       m_sym;                    // traded and read symbol (gold)
   int       m_id;                     // sleeve id (oid = t_close x 100 + id)
   CrAgg     m_agg;                    // the 4h bucket being filled
   CrWilder  m_atr;                    // Wilder ATR of the 4h true ranges
   CrRollMax m_up;                     // highest mid high of the last 60 4h bars
   CrRollMin m_dn;                     // lowest mid low of the last 60 4h bars
   double    m_pc;                     // mid close of the previous 4h bar
   bool      m_has_pc;                 // m_pc holds a value
   bool      m_started;                // a bar was fed since Init
   bool      m_whole;                  // the open bucket is whole (only the first one may not be)
   long      m_n4;                     // 4h bars pushed since Init

   bool Init(const int sleeve)
     {
      sl = sleeve;
      m_sym = g_sl[sl].sym;
      m_id = g_sl[sl].id;
      m_agg.Clear();
      m_atr.Init(CR_D4H_ATR_N);
      m_up.Init(CR_D4H_N);
      m_dn.Init(CR_D4H_N);
      m_pc = 0.0;
      m_has_pc = false;
      m_started = false;
      m_whole = true;
      m_n4 = 0;
      return m_sym == CR_XAU;
     }

   // the 4h bar q is complete and b, the first bar of the next bucket, is its activation bar: true range, ATR,
   // channel, then the OCO
   void Bucket(const CrAggBar &q, const bool whole, const CrBar &b, CrOut &out)
     {
      double h = (q.bh + q.ah) / 2;
      double l = (q.bl + q.al) / 2;
      double c = (q.bc + q.ac) / 2;
      if(!whole)
        {
         m_pc = c;                                           // a bucket cut by the load: its close is still right
         m_has_pc = true;
         return;
        }
      double tr = CrNaN();                                   // the first bar: pc = c.shift(1) is NaN, so is its TR
      if(m_has_pc)
        {
         tr = h - l;                                         // np.maximum(h - l, np.maximum(|h - pc|, |l - pc|))
         double a = MathAbs(h - m_pc);
         double d = MathAbs(l - m_pc);
         if(d > a) a = d;
         if(a > tr) tr = a;
        }
      double atr = m_atr.Push(tr);
      m_up.Push(h);
      m_dn.Push(l);
      m_pc = c;
      m_has_pc = true;
      m_n4++;
      double up = m_up.Value();                              // NaN until 60 bars (rolling(60), min_periods 60)
      double dn = m_dn.Value();
      if(!CrFinite(up) || !CrFinite(dn) || !CrFinite(atr)) return;   // :266
      if(!(atr > 0.0)) return;                               // a zero stop: the paper refuses it (never on real data)
      datetime tc = q.t_last + 60;
      CrOrder o;
      CrOrderClear(o);
      o.sleeve = sl;
      o.oid = CrOid(tc, m_id);
      o.side = 0;
      o.etype = CR_ET_OCO;
      o.level = up;                                          // buy stop (:281, side > 0)
      o.level2 = dn;                                         // sell stop
      o.t_from = b.t;                                        // the first kept bar at or after t_close
      o.t_to = b.t;
      o.expiry_excl = CrAggKey(b.t, CR_D4H_TF_S) + CR_D4H_TF_S;   // fills on the bars of b's bucket only
      o.stop_dist = atr * CR_D4H_STOP_ATR;
      o.trail = atr * CR_D4H_TRAIL_ATR;
      o.x_sched = DonchExitTime(tc);
      o.x_gap = true;
      o.dec = tc;
      if(!CrOutOrder(out, o)) JrnError(g_sl[sl].code, "more than CR_OUT_MAX orders at " + IntegerToString((long)tc));
     }

   void OnBar(const int sym, const CrBar &b, CrOut &out)
     {
      if(sym != m_sym) return;
      datetime key = CrAggKey(b.t, CR_D4H_TF_S);
      CrAggBar done;
      ZeroMemory(done);
      if(!m_agg.Add(b, key, done))
        {
         if(!m_started)                                      // b opened the first bucket since Init
           {
            m_started = true;
            m_whole = DonchWhole(b.t, key);
           }
         return;
        }
      bool whole = m_whole;
      m_whole = true;                                        // the bucket b opens follows a bar of this chain
      Bucket(done, whole, b, out);
     }

   void OnMinute(const datetime M, CrOut &out) {}

   datetime LatestExit(const datetime open_time, const datetime comment_dec)
     {
      datetime B = CrAggKey(open_time, CR_D4H_TF_S);
      if(comment_dec > 0 && comment_dec % 60 == 0 && comment_dec <= B && (long)(B - comment_dec) <= CR_D4H_JOIN_S)
         return DonchExitTime(comment_dec);
      datetime tc = B;
      datetime srv = ClkUtcToServer(B);
      int dow = ClkDow(srv);                                 // 0 = Sunday ... 6 = Saturday
      if(dow == 6 || dow == 0)
        {
         datetime sat = ClkDay(srv);                         // 00:00 server on the Saturday of that weekend
         if(dow == 0) sat = sat - 86400;
         tc = ClkServerToUtc(sat - 60);                      // 23:59 server on the Friday before
        }
      return DonchExitTime(tc);
     }
  };
#endif

// ==== end src/CR_Rule_Donch.mqh
#ifdef CR_HARNESS
// ==== begin src/CR_Rule_Script.mqh
//+------------------------------------------------------------------+
//| CR_Rule_Script.mqh - harness-only rule (CR_HARNESS). Owner: S0.   |
//|                                                                  |
//| Replays a file of lab orders written by check/ref_lab.py: each   |
//| row is a CrOrder and the barrier minute at which it is emitted.  |
//| A sleeve listed in the harness input InpScript gets this rule in |
//| place of its own (step J tests the execution with it, SPEC 8).   |
//| File MQL5/Files/<InpScriptDir>/<code>.csv, a header line, then   |
//| emit,oid,side,etype,level,level2,t_from,t_to,after_exit_of,      |
//| expiry_excl,stop,stop_dist,trail,be,target,target_dist,x_sched,  |
//| x_gap,xh,xh_r,refuse,void_le,dec,group                           |
//| (UTC seconds; doubles with 17 significant digits; rows sorted by |
//| emit). An order whose emit minute lies before the first barrier  |
//| the driver processes is history and is not emitted.             |
//+------------------------------------------------------------------+
#ifndef CR_RULE_SCRIPT_MQH
#define CR_RULE_SCRIPT_MQH
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Journal.mqh)

#define CR_SCRIPT_COLS 24

class CRuleScript
  {
public:
   int      sl;
   CrOrder  m_ord[];
   datetime m_emit[];
   int      m_n;
   int      m_next;
   bool     m_loaded;

   bool Init(const int sleeve)
     {
      sl = sleeve;
      m_n = 0;
      m_next = 0;
      m_loaded = false;
      ArrayResize(m_ord, 0, 1024);
      ArrayResize(m_emit, 0, 1024);
      string path = g_cfg.script_dir + "\\" + g_sl[sl].code + ".csv";
      int h = FileOpen(path, FILE_READ | FILE_TXT | FILE_ANSI | FILE_SHARE_READ);
      if(h == INVALID_HANDLE)
        {
         JrnError(g_sl[sl].code, "script file missing: " + path);
         return false;
        }
      FileReadString(h);                         // the header line
      string f[];
      while(!FileIsEnding(h))
        {
         string line = FileReadString(h);
         if(StringLen(line) < 10) continue;
         int k = StringSplit(line, ',', f);
         if(k != CR_SCRIPT_COLS)
           {
            FileClose(h);
            JrnError(g_sl[sl].code, "script row with " + IntegerToString(k) + " fields");
            return false;
           }
         CrOrder o;
         CrOrderClear(o);
         o.sleeve = sl;
         o.oid = StringToInteger(f[1]);
         o.side = (int)StringToInteger(f[2]);
         o.etype = (int)StringToInteger(f[3]);
         o.level = StringToDouble(f[4]);
         o.level2 = StringToDouble(f[5]);
         o.t_from = (datetime)StringToInteger(f[6]);
         o.t_to = (datetime)StringToInteger(f[7]);
         o.after_exit_of = StringToInteger(f[8]);
         o.expiry_excl = (datetime)StringToInteger(f[9]);
         o.stop = StringToDouble(f[10]);
         o.stop_dist = StringToDouble(f[11]);
         o.trail = StringToDouble(f[12]);
         o.be = StringToDouble(f[13]);
         o.target = StringToDouble(f[14]);
         o.target_dist = StringToDouble(f[15]);
         o.x_sched = (datetime)StringToInteger(f[16]);
         o.x_gap = StringToInteger(f[17]) != 0;
         o.xh = (datetime)StringToInteger(f[18]);
         o.xh_r = StringToDouble(f[19]);
         o.refuse = (int)StringToInteger(f[20]);
         o.void_le = StringToInteger(f[21]) != 0;
         o.dec = (datetime)StringToInteger(f[22]);
         o.group = (int)StringToInteger(f[23]);
         ArrayResize(m_ord, m_n + 1, 1024);
         ArrayResize(m_emit, m_n + 1, 1024);
         m_ord[m_n] = o;
         m_emit[m_n] = (datetime)StringToInteger(f[0]);
         m_n++;
        }
      FileClose(h);
      m_loaded = true;
      return true;
     }

   void OnBar(const int sym, const CrBar &b, CrOut &out) {}

   void OnMinute(const datetime M, CrOut &out)
     {
      while(m_next < m_n && m_emit[m_next] <= M)
        {
         if(m_emit[m_next] == M && !CrOutOrder(out, m_ord[m_next]))
            JrnError(g_sl[sl].code, "script: more than CR_OUT_MAX orders at " + IntegerToString((long)M));
         m_next++;
        }
     }

   // the scheduled exit of the order whose activation matches the position's open time (0 when unknown)
   datetime LatestExit(const datetime open_time, const datetime comment_dec)
     {
      for(int i = m_n - 1; i >= 0; i--)
         if(m_ord[i].t_from <= open_time && open_time <= m_ord[i].t_to + 300) return m_ord[i].x_sched;
      return 0;
     }
  };
#endif

// ==== end src/CR_Rule_Script.mqh
#endif

// ---- one object per sleeve, by kind (no pointers: SPEC 1, MQL5 subset)
CRuleN30   g_r_n30;
CRuleOC4   g_r_oc4;
CRuleBrk72 g_r_brk[2];
CRuleF1    g_r_f1[2];
CRuleNqb   g_r_nqb;
CRuleGfp   g_r_gfp;
CRuleDonch g_r_d4h;
CRuleOrx   g_r_orx;
#ifdef CR_HARNESS
CRuleScript g_r_scr[CR_MAX_SL];
#endif

// ---- the frozen equal-swing stake factors (synthesis_A.json proposed_validation_look item 7; look_spec.json)
#define CR_FACTOR_H2 0.750978
#define CR_FACTOR_S075 0.771793

void RegSym(const int s, const string base, const string lab, const int family, const int comm_pts, const double slip_mkt_bps,
            const double slip_stop_bps, const int depth_days, const double model_bp)
  {
   g_sym[s].base = base;
   g_sym[s].lab = lab;
   g_sym[s].name = "";
   g_sym[s].family = family;
   g_sym[s].digits = 2;                         // read live at OnInit (CR_Main); 2 in the harness
   g_sym[s].point = 0.01;
   g_sym[s].comm_pts = comm_pts;
   g_sym[s].h = comm_pts * 0.5 * 0.01;
   g_sym[s].slip_mkt = slip_mkt_bps * 1e-4;
   g_sym[s].slip_stop = slip_stop_bps * 1e-4;
   g_sym[s].depth_days = depth_days;
   g_sym[s].model_bp = model_bp;
   g_sym[s].ok = false;
  }

void RegSleeve(const int id, const string code, const string lab, const int kind, const int slot, const int sym, const int sym2,
               const int change, const double factor_on, const int refuse_on)
  {
   int i = g_nsl;
   g_sl[i].id = id;
   g_sl[i].code = code;
   g_sl[i].lab = lab;
   g_sl[i].kind = kind;
   g_sl[i].slot = slot;
   g_sl[i].sym = sym;
   g_sl[i].sym2 = sym2;
   g_sl[i].change = change;
   g_sl[i].factor_on = factor_on;
   g_sl[i].refuse_on = refuse_on;
   g_sl[i].change_on = false;
   g_sl[i].allowed = true;
   g_sl[i].magic = CR_MAGIC_BASE + id;
   g_nsl++;
  }

// the static rows (no terminal call): symbols then sleeves (SPEC 2.3; slippage fp_costs.json; COST model bp SPEC 2.6)
void RegInit()
  {
   //     id      base      lab       family      commission       mkt  stop  depth  model bp
   RegSym(CR_XAU, "XAUUSD", "xauusd", CR_FAM_XAU, CR_XAU_COMM_PTS, 0.3, 1.0, 120, 0.47);
   RegSym(CR_IDX, "US100", "us100", CR_FAM_IDX, 0, 0.2, 0.5, 60, 0.37);
   RegSym(CR_BTC, "BTCUSD", "btcusd", CR_FAM_CRY, 0, 0.5, 1.5, 60, 2.96);
   RegSym(CR_ETH, "ETHUSD", "ethusd", CR_FAM_CRY, 0, 0.7, 2.0, 60, 13.0);
   g_nsl = 0;
   //        id code   lab sleeve (sort key)            kind        slot sym     sym2    change      factor          refusal
   RegSleeve(1, "N30", "noise30_us100", CR_K_N30, 0, CR_IDX, -1, CR_CH_NONE, 1.0, CR_REF_NONE);
   RegSleeve(2, "OC4", "ocm4_us100", CR_K_OC4, 0, CR_IDX, -1, CR_CH_NONE, 1.0, CR_REF_NONE);
   RegSleeve(3, "BKB", "brk72_24h_wd_btcusd", CR_K_BRK72, 0, CR_BTC, -1, CR_CH_S075, CR_FACTOR_S075, CR_REF_PAYOFF);
   RegSleeve(4, "BKE", "brk72_24h_wd_ethusd", CR_K_BRK72, 1, CR_ETH, -1, CR_CH_K1, 1.0, CR_REF_SB);
   RegSleeve(5, "F1B", "F1_brk_ridge_filter_btcusd", CR_K_F1, 0, CR_BTC, -1, CR_CH_NONE, 1.0, CR_REF_NONE);
   RegSleeve(6, "F1E", "F1_brk_ridge_filter_ethusd", CR_K_F1, 1, CR_ETH, -1, CR_CH_H2, CR_FACTOR_H2, CR_REF_PAYOFF);
   RegSleeve(7, "NQB", "nq_btc_follow_btcusd", CR_K_NQB, 0, CR_BTC, CR_IDX, CR_CH_NONE, 1.0, CR_REF_NONE);
   RegSleeve(8, "GFP", "GOLD_FRI_PM_xauusd", CR_K_GFP, 0, CR_XAU, -1, CR_CH_NONE, 1.0, CR_REF_NONE);
   RegSleeve(9, "D4H", "donch4h_stop_xauusd", CR_K_D4H, 0, CR_XAU, -1, CR_CH_NONE, 1.0, CR_REF_NONE);
   RegSleeve(10, "ORX", "orb_asia_2d_buf10_xauusd", CR_K_ORX, 0, CR_XAU, -1, CR_CH_NONE, 1.0, CR_REF_NONE);
  }

// the paper half commission once the symbol's point is known (SPEC 2.2: h = comm_pts / 2 x point)
void RegSetPoint(const int s, const int digits, const double point)
  {
   g_sym[s].digits = digits;
   g_sym[s].point = point;
   g_sym[s].h = g_sym[s].comm_pts * 0.5 * point;
  }

string RegChangeName(const int ch)
  {
   if(ch == CR_CH_K1) return "K1";
   if(ch == CR_CH_H2) return "H2";
   if(ch == CR_CH_S075) return "S0.75r";
   return "-";
  }

// SPEC 3.9: -1 = on for a demo or contest account, off for a real one; 0 = off; 1 = on. Resolved once at OnInit.
bool ChangeSwitchOn(const int sw) { return sw == 1 || (sw == -1 && g_cfg.demo); }

void ChangeOn()
  {
   for(int i = 0; i < g_nsl; i++)
     {
      int sw = 0;
      if(g_sl[i].change == CR_CH_K1) sw = g_cfg.k1;
      else if(g_sl[i].change == CR_CH_H2) sw = g_cfg.h2;
      else if(g_sl[i].change == CR_CH_S075) sw = g_cfg.s075;
      g_sl[i].change_on = (g_sl[i].change != CR_CH_NONE) && ChangeSwitchOn(sw);
      if(g_sl[i].change_on && !g_cfg.demo)
        {
         Jrn(CR_EV_INIT, g_sl[i].code, KV("change", RegChangeName(g_sl[i].change)) + KV("on_real", "1"));
         JrnPush("le changement " + RegChangeName(g_sl[i].change) + " est actif sur le compte REEL (" + g_sl[i].code + ")", true);
        }
     }
  }

// stake factor and refusal of a sleeve as resolved (off: the official rule, factor 1, no refusal)
double RegStakeFactor(const int sl) { return g_sl[sl].change_on ? g_sl[sl].factor_on : 1.0; }
int    RegRefuse(const int sl) { return g_sl[sl].change_on ? g_sl[sl].refuse_on : CR_REF_NONE; }

// InpSleeves: "ALL" or codes separated by commas; false on an unknown code
bool RegParseSleeves(const string s, string &err)
  {
   string t = s;
   StringTrimLeft(t);
   StringTrimRight(t);
   bool all = (t == "ALL" || t == "all");
   for(int i = 0; i < g_nsl; i++) g_sl[i].allowed = all;
   if(all) return true;
   if(t == "") return true;                     // nothing allowed: every sleeve is paper only
   string part[];
   int n = StringSplit(t, ',', part);
   for(int k = 0; k < n; k++)
     {
      string c = part[k];
      StringTrimLeft(c);
      StringTrimRight(c);
      int sl = CrSleeveOfCode(c);
      if(sl < 0)
        {
         err = "InpSleeves: unknown code '" + c + "'";
         return false;
        }
      g_sl[sl].allowed = true;
     }
   return true;
  }

#ifdef CR_HARNESS
// harness: the sleeves listed in g_cfg.script replay ref_lab.py's orders through CR_Rule_Script
bool RegApplyScript(string &err)
  {
   if(g_cfg.script == "") return true;
   string part[];
   int n = StringSplit(g_cfg.script, ',', part);
   for(int k = 0; k < n; k++)
     {
      int sl = CrSleeveOfCode(part[k]);
      if(sl < 0)
        {
         err = "InpScript: unknown code '" + part[k] + "'";
         return false;
        }
      g_sl[sl].kind = CR_K_SCRIPT;
      g_sl[sl].slot = sl;
     }
   return true;
  }
#endif

// the input checks of SPEC 1 that belong to the registry (switches, sleeves); false -> ERROR at OnInit
bool RegCheckInputs(string &err)
  {
   if(g_cfg.k1 < -1 || g_cfg.k1 > 1 || g_cfg.h2 < -1 || g_cfg.h2 > 1 || g_cfg.s075 < -1 || g_cfg.s075 > 1)
     {
      err = "InpK1, InpH2 and InpS075 must be -1, 0 or 1";
      return false;
     }
   if(!RegParseSleeves(g_cfg.sleeves, err)) return false;
#ifdef CR_HARNESS
   if(!RegApplyScript(err)) return false;
#endif
   return true;
  }

// ---- dispatch (one case per kind) -----------------------------------------------------------------------------------
// Init every rule object afresh (OnInit and every rebuild); false and err on a bad configuration (e.g. InpK1T)
bool RulesInit(string &err)
  {
   for(int sl = 0; sl < g_nsl; sl++)
     {
      bool ok = true;
      int k = g_sl[sl].slot;
      switch(g_sl[sl].kind)
        {
         case CR_K_N30: ok = g_r_n30.Init(sl); break;
         case CR_K_OC4: ok = g_r_oc4.Init(sl); break;
         case CR_K_BRK72: ok = g_r_brk[k].Init(sl); break;
         case CR_K_F1: ok = g_r_f1[k].Init(sl); break;
         case CR_K_NQB: ok = g_r_nqb.Init(sl); break;
         case CR_K_GFP: ok = g_r_gfp.Init(sl); break;
         case CR_K_D4H: ok = g_r_d4h.Init(sl); break;
         case CR_K_ORX: ok = g_r_orx.Init(sl); break;
#ifdef CR_HARNESS
         case CR_K_SCRIPT: ok = g_r_scr[k].Init(sl); break;
#endif
         default: ok = false;
        }
      if(!ok)
        {
         err = "rule " + g_sl[sl].code + ": Init refused its configuration";
         return false;
        }
     }
   return true;
  }

void RulesOnBar(const int sl, const int sym, const CrBar &b, CrOut &out)
  {
   int k = g_sl[sl].slot;
   switch(g_sl[sl].kind)
     {
      case CR_K_N30: g_r_n30.OnBar(sym, b, out); break;
      case CR_K_OC4: g_r_oc4.OnBar(sym, b, out); break;
      case CR_K_BRK72: g_r_brk[k].OnBar(sym, b, out); break;
      case CR_K_F1: g_r_f1[k].OnBar(sym, b, out); break;
      case CR_K_NQB: g_r_nqb.OnBar(sym, b, out); break;
      case CR_K_GFP: g_r_gfp.OnBar(sym, b, out); break;
      case CR_K_D4H: g_r_d4h.OnBar(sym, b, out); break;
      case CR_K_ORX: g_r_orx.OnBar(sym, b, out); break;
#ifdef CR_HARNESS
      case CR_K_SCRIPT: g_r_scr[k].OnBar(sym, b, out); break;
#endif
      default: break;
     }
  }

void RulesOnMinute(const int sl, const datetime M, CrOut &out)
  {
   int k = g_sl[sl].slot;
   switch(g_sl[sl].kind)
     {
      case CR_K_N30: g_r_n30.OnMinute(M, out); break;
      case CR_K_OC4: g_r_oc4.OnMinute(M, out); break;
      case CR_K_BRK72: g_r_brk[k].OnMinute(M, out); break;
      case CR_K_F1: g_r_f1[k].OnMinute(M, out); break;
      case CR_K_NQB: g_r_nqb.OnMinute(M, out); break;
      case CR_K_GFP: g_r_gfp.OnMinute(M, out); break;
      case CR_K_D4H: g_r_d4h.OnMinute(M, out); break;
      case CR_K_ORX: g_r_orx.OnMinute(M, out); break;
#ifdef CR_HARNESS
      case CR_K_SCRIPT: g_r_scr[k].OnMinute(M, out); break;
#endif
      default: break;
     }
  }

// SPEC 4.8 table: the latest time exit of a position opened at open_time (0 = unknown)
datetime RulesLatestExit(const int sl, const datetime open_time, const datetime comment_dec)
  {
   int k = g_sl[sl].slot;
   datetime x = 0;
   switch(g_sl[sl].kind)
     {
      case CR_K_N30: x = g_r_n30.LatestExit(open_time, comment_dec); break;
      case CR_K_OC4: x = g_r_oc4.LatestExit(open_time, comment_dec); break;
      case CR_K_BRK72: x = g_r_brk[k].LatestExit(open_time, comment_dec); break;
      case CR_K_F1: x = g_r_f1[k].LatestExit(open_time, comment_dec); break;
      case CR_K_NQB: x = g_r_nqb.LatestExit(open_time, comment_dec); break;
      case CR_K_GFP: x = g_r_gfp.LatestExit(open_time, comment_dec); break;
      case CR_K_D4H: x = g_r_d4h.LatestExit(open_time, comment_dec); break;
      case CR_K_ORX: x = g_r_orx.LatestExit(open_time, comment_dec); break;
#ifdef CR_HARNESS
      case CR_K_SCRIPT: x = g_r_scr[k].LatestExit(open_time, comment_dec); break;
#endif
      default: x = 0;
     }
   return x;
  }

// does sleeve sl read symbol sym (its traded symbol or its second one)?
bool RegReads(const int sl, const int sym) { return g_sl[sl].sym == sym || g_sl[sl].sym2 == sym; }
#endif

// ==== end src/CR_Registry.mqh
// ==== begin src/CR_Bars.mqh
//+------------------------------------------------------------------+
//| CR_Bars.mqh - bars, quotes, mask, barrier, revisions, READY and  |
//| daily cost statistics (SPEC 2.2). Owner: step B.                 |
//|                                                                  |
//| The store holds, per symbol, the KEPT closed M1 bars with the    |
//| PAPER quotes (SPEC 2.2): paper bid = NormalizeDouble(bid - h),   |
//| paper ask = NormalizeDouble(bid + spread x point + h), on all    |
//| four prices, h = g_sym[].h (gold: CR_XAU_COMM_PTS / 2 points).   |
//| Bars are read by time range only (CopyRates from, to), never by  |
//| position. Times are UTC inside; the broker's bars carry server   |
//| time (New York + 7 h).                                           |
//|                                                                  |
//| Mask (SPEC 2.2), each bar counted under its first reason:        |
//|   weekend gold and US100: Saturday or Sunday, server clock       |
//|           (prep_round2.py:53)                                    |
//|   crypto  Saturday, Sunday, or Friday from 23:55, server clock   |
//|           (build_fp_frames.py:31-33)                             |
//|   idx     US100 16:15-17:59 New York                             |
//|   xau     gold 17:00-17:59 New York                              |
//|   half    US100 13:16-17:59 New York on NYSE half days (P6;      |
//|           ClkNyse, typed HALF entries included)                  |
//| The bars left are the kept bars; masked bars still count as      |
//| broker bars for the hole scan and revisions.                     |
//| No flat-bar rule (lead decision after step B's finding 1): MT5   |
//| makes a bar only when a tick came, so it has no filler bars. The |
//| lab dropped flat bars on Dukascopy's 3-decimal bid; on the       |
//| 2-digit FP bid the same rule dropped 5,969 real in-sample bars   |
//| that the rebuilt frames keep (gold 4,905, US100 963, BTC 7,      |
//| ETH 94). Without it the kept bars equal the rebuilt frames,      |
//| except 20 gold bars of 2012-12-31 17:00-17:58 New York (xau).    |
//|                                                                  |
//| Barrier M (UTC minute; every bar starting before M is final):    |
//|   M = the current minute when every symbol has ticked in it or   |
//|   is in a known closure (ClkInClosure); else the minute that     |
//|   started at least 2 s ago (TimeTradeServer() >= M + 2 s). One   |
//|   answer per server second: the load and the replay of one pass  |
//|   agree even if a tick arrives between their two calls.          |
//| Poll (once per new barrier):                                     |
//|   - the last 3 broker bars of every symbol are read again; a     |
//|     change (a value, a bar added or gone) asks for a rebuild;    |
//|   - new bars are read from the last one to M; a minute that was  |
//|     seen ticking but whose bar is not returned makes the poll    |
//|     WAIT (retried each pass) for 30 s, then GAP (journal, push); |
//|   - a bar that shows up after its barrier passed (late) is not   |
//|     fed; it asks for a rebuild;                                  |
//|   - a rebuild is returned as CR_POLL_LATEBAR, at most one per    |
//|     5 min (a later one waits; the chain goes on meanwhile).      |
//| READY (R13), per symbol, decided at checks (BarsTimer): 2 s      |
//| after the load, then every 60 s until READY:                     |
//|   (1) SERIES_SYNCHRONIZED is true;                               |
//|   (2) depth: SERIES_FIRSTDATE <= now - depth (120 days gold, 60  |
//|       the others);                                               |
//|   (3) a second read of the load window, at least 2 s after the   |
//|       first, agrees with it (else: rebuild);                     |
//|   (4) no hole: more than 30 minutes outside the known closures   |
//|       without any broker bar, inside the current window. A hole  |
//|       gives GAP (journal, push) and is read again every 60 s:    |
//|       bars found -> rebuild; still empty after 3 re-reads with   |
//|       SERIES_SYNCHRONIZED true -> the broker's own hole (GAP     |
//|       accepted=1). An accepted hole is remembered across rebuilds |
//|       (same bounds: accepted at once, no new push).              |
//|   A symbol whose load read failed (no history yet) never blocks  |
//|   the others; its bars are taken as they come, and its history,  |
//|   if it appears later, asks for a rebuild. READY stays until the |
//|   next load. NOT_READY for 10 min: one push.                     |
//| Daily cost statistics (COST, SPEC 2.6): per symbol and server    |
//| day, over the kept bars fed, the median of the raw spread and of |
//| the paper spread, in bp of the bar's opening mid.                |
//|                                                                  |
//| API (the S0 signatures; indexes are absolute since the load):    |
//|   BarsInit(err)           once at OnInit, after the symbols are  |
//|                           resolved (g_sym[].name, digits, point) |
//|   BarsReset()             forget the store                       |
//|   BarsLoad(now_srv)       read the depth of every symbol:        |
//|                           CR_LOAD_OK, or CR_LOAD_RETRY while     |
//|                           every read fails (at most 60 s)        |
//|   BarsBarrier(now_srv)    the barrier M (also notes the ticks)   |
//|   BarsPoll(M)             CR_POLL_OK / CR_POLL_WAIT /            |
//|                           CR_POLL_LATEBAR (rebuild)              |
//|   BarsNext(M, b)          next kept bar not yet fed with start   |
//|                           before M, in (time, symbol id) order   |
//|   BarsReady(sym)          READY as above                         |
//|   BarsCount(sym)          kept bars FED since the load           |
//|   BarsAt(sym, i, b)       fed bar i, 0 <= i < BarsCount (false   |
//|                           for bars dropped by the compaction:    |
//|                           the last 150,000 are always kept)      |
//|   BarsIndex(sym, t)       first fed bar starting at or after t   |
//|   BarsStart()             first kept bar of the store (UTC), 0   |
//|   BarsCost(sym, day, raw_bp, paper_bp)  daily medians (COST)     |
//|   BarsTimer(now_srv)      READY checks, GAP and NOTREADY pushes  |
//|   BarsPaperQuotes(sym, bid, ask, pbid, pask)  live paper quotes  |
//|   BarsMasked(sym, reason) masked bars since the load, by reason  |
//| Journal: READY / NOTREADY (code = symbol: bars, raw bars, first, |
//| last, masked by reason, holes, why), GAP (hole from/to, or a     |
//| live missing minute), LATEBAR (code = symbol: why and the bar),  |
//| written before the driver's own LATEBAR line.                    |
//+------------------------------------------------------------------+
#ifndef CR_BARS_MQH
#define CR_BARS_MQH
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Clock.mqh)
// (already inlined: CR_Journal.mqh)
// (already inlined: CR_Math.mqh)

#define CR_BARS_GAP_S 1800             // a hole: more than 30 open minutes without a broker bar
#define CR_BARS_WAIT_S 30              // a ticked minute whose bar is not returned: retried 30 s, then GAP
#define CR_BARS_LATE_S 300             // at most one rebuild (LATEBAR) per 5 min
#define CR_BARS_RECHECK_S 60           // NOT_READY checks every 60 s
#define CR_BARS_STABLE_S 2             // the second read, at least 2 s after the load read
#define CR_BARS_ACCEPT 3               // a hole still there after 3 re-reads is the broker's own
#define CR_BARS_NOTREADY_PUSH_S 600    // NOT_READY for 10 min: one push
#define CR_BARS_KEEP 150000            // fed bars kept by the compaction
#define CR_BARS_COMPACT 300000         // compaction when this many bars were fed
#define CR_BARS_MAXHOLES 256           // holes remembered per symbol while NOT_READY (the oldest go first)
#define CR_BARS_MAXTICK 8
#define CR_BARS_MAXACC 64              // accepted holes remembered across rebuilds, per symbol

// mask reasons (BarsMasked)
#define CR_MASK_KEPT 0
#define CR_MASK_WEEKEND 1
#define CR_MASK_CRYPTO 2
#define CR_MASK_IDX 3
#define CR_MASK_XAU 4
#define CR_MASK_HALF 5
#define CR_MASK_N 6

string CR_MASK_NAME[CR_MASK_N] = {"kept", "m_weekend", "m_crypto", "m_idx", "m_xau", "m_half"};

// a broker bar as read (server time): the revision check compares them
struct CrRawBar
  {
   datetime t;
   double   o, h, l, c;
   int      s;
  };

// a hole: no broker bar in [a, b) (UTC), more than 30 minutes of it outside the known closures
struct CrHole
  {
   datetime a, b;
   int      reads;                     // re-reads that found it still empty (series synchronized)
   bool     said;                      // GAP written
   bool     accepted;                  // the broker's own hole (GAP accepted=1)
  };

datetime g_bars_M = 0;                 // the barrier of the last successful poll (or of the load), UTC
bool     g_bars_late = false;          // a rebuild was asked for
datetime g_bars_late_last = 0;         // server time of the last CR_POLL_LATEBAR (0 = none yet)
datetime g_bars_rev_M = 0;             // the barrier whose last-3 re-read was done
datetime g_bars_first_try = 0;         // first call of a load whose reads all failed (CR_LOAD_RETRY)
long     g_bars_late_n = 0;            // rebuilds asked for
datetime g_bars_bar_now = 0;           // BarsBarrier's last call (server time) and its answer: one answer per second, so
datetime g_bars_bar_M = 0;             // that the load and the replay of one pass agree even if a tick comes in between
long     g_bars_gap_live = 0;          // live missing minutes given up (GAP)
// holes accepted as the broker's own (UTC bounds), kept across rebuilds (BarsInit clears them): after a rebuild the
// same hole is accepted at once, without a new GAP push or three more re-reads
datetime g_bars_acc_a[CR_NSYM][CR_BARS_MAXACC];
datetime g_bars_acc_b[CR_NSYM][CR_BARS_MAXACC];
int      g_bars_nacc[CR_NSYM];

bool BarsAccepted(const int sym, const datetime a, const datetime b)
  {
   for(int i = 0; i < g_bars_nacc[sym]; i++)
      if(g_bars_acc_a[sym][i] == a && g_bars_acc_b[sym][i] == b) return true;
   return false;
  }

void BarsAccept(const int sym, const datetime a, const datetime b)
  {
   if(BarsAccepted(sym, a, b)) return;
   if(g_bars_nacc[sym] >= CR_BARS_MAXACC)
     {
      for(int i = 1; i < g_bars_nacc[sym]; i++)
        {
         g_bars_acc_a[sym][i - 1] = g_bars_acc_a[sym][i];
         g_bars_acc_b[sym][i - 1] = g_bars_acc_b[sym][i];
        }
      g_bars_nacc[sym]--;
     }
   g_bars_acc_a[sym][g_bars_nacc[sym]] = a;
   g_bars_acc_b[sym][g_bars_nacc[sym]] = b;
   g_bars_nacc[sym]++;
  }

//+------------------------------------------------------------------+
//| helpers (no state)                                               |
//+------------------------------------------------------------------+
// the paper quotes of a broker bar (SPEC 2.2), t = its UTC start
void BarsMakeAt(const int sym, const MqlRates &r, const datetime t, CrBar &x)
  {
   double h = g_sym[sym].h, pt = g_sym[sym].point;
   int dg = g_sym[sym].digits;
   x.t = t;
   x.sym = sym;
   x.bo = NormalizeDouble(r.open - h, dg);
   x.bh = NormalizeDouble(r.high - h, dg);
   x.bl = NormalizeDouble(r.low - h, dg);
   x.bc = NormalizeDouble(r.close - h, dg);
   x.ao = NormalizeDouble(r.open + r.spread * pt + h, dg);
   x.ah = NormalizeDouble(r.high + r.spread * pt + h, dg);
   x.al = NormalizeDouble(r.low + r.spread * pt + h, dg);
   x.ac = NormalizeDouble(r.close + r.spread * pt + h, dg);
   x.s_raw = r.spread;
  }

void BarsMake(const int sym, const MqlRates &r, CrBar &x) { BarsMakeAt(sym, r, ClkServerToUtc(r.time), x); }

// live paper quotes from a raw tick (SPEC 2.2)
void BarsPaperQuotes(const int sym, const double bid, const double ask, double &pbid, double &pask)
  {
   pbid = NormalizeDouble(bid - g_sym[sym].h, g_sym[sym].digits);
   pask = NormalizeDouble(ask + g_sym[sym].h, g_sym[sym].digits);
  }

// the mask reason of one broker bar (CR_MASK_*); it reads the bar's own server time only (no flat-bar rule)
int BarsMaskReason(const int sym, const MqlRates &r)
  {
   int fam = g_sym[sym].family;
   datetime srv = r.time;
   int dow = (int)(((srv / 86400) + 4) % 7);       // 1970-01-01 was a Thursday; 0 = Sunday
   int srv_min = (int)((srv % 86400) / 60);
   if(fam != CR_FAM_CRY && (dow == 0 || dow == 6)) return CR_MASK_WEEKEND;
   if(fam == CR_FAM_CRY && (dow == 0 || dow == 6 || (dow == 5 && srv_min >= 23 * 60 + 55))) return CR_MASK_CRYPTO;
   datetime ny = srv - 7 * 3600;                  // New York wall clock = server - 7 h (SPEC 2.1)
   int ny_min = (int)((ny % 86400) / 60);
   if(fam == CR_FAM_IDX && ny_min >= 16 * 60 + 15 && ny_min < 18 * 60) return CR_MASK_IDX;
   if(fam == CR_FAM_XAU && ny_min >= 17 * 60 && ny_min < 18 * 60) return CR_MASK_XAU;
   if(fam == CR_FAM_IDX && ny_min >= 13 * 60 + 16 && ny_min < 18 * 60 && ClkNyse(ny - ny % 86400) == CR_NYSE_HALF) return CR_MASK_HALF;
   return CR_MASK_KEPT;
  }

// seconds of [a, b) (UTC minutes) outside the family's known closures, counted up to just past limit
long BarsOpenSecs(const int family, const datetime a, const datetime b, const long limit)
  {
   long open = 0;
   datetime t = a;
   int guard = 0;
   while(t < b && open <= limit && guard < 100000)
     {
      datetime c0 = 0, c1 = 0;
      if(ClkInClosure(family, t, c0, c1) && c1 > t) t = c1;
      else
        {
         open += 60;
         t += 60;
        }
      guard++;
     }
   return open;
  }

// FNV-1a over 64-bit words (unsigned arithmetic wraps the same way in MQL5 and C++)
ulong BarsMix(const ulong h, const ulong v) { return (h ^ v) * (ulong)1099511628211; }

// a fingerprint of the broker bars of r[0..k) starting before before_srv: time, prices in points, spread
void BarsChk(const int sym, const MqlRates &r[], const int k, const datetime before_srv, ulong &h, long &cnt)
  {
   double pt = g_sym[sym].point;
   h = (ulong)1469598103934665603;
   cnt = 0;
   for(int i = 0; i < k; i++)
     {
      if(r[i].time >= before_srv) break;
      h = BarsMix(h, (ulong)r[i].time);
      h = BarsMix(h, (ulong)(long)MathRound(r[i].open / pt));
      h = BarsMix(h, (ulong)(long)MathRound(r[i].high / pt));
      h = BarsMix(h, (ulong)(long)MathRound(r[i].low / pt));
      h = BarsMix(h, (ulong)(long)MathRound(r[i].close / pt));
      h = BarsMix(h, (ulong)(long)r[i].spread);
      cnt++;
     }
  }

// ask for a rebuild (CR_POLL_LATEBAR at the next poll the 5-minute limit allows); one line per rebuild
void BarsLate(const int sym, const string why, const datetime t_utc)
  {
   if(g_bars_late) return;
   g_bars_late = true;
   g_bars_late_n++;
   long wait = 0;
   datetime now = TimeTradeServer();
   if(g_bars_late_last > 0 && (long)(now - g_bars_late_last) < CR_BARS_LATE_S) wait = CR_BARS_LATE_S - (long)(now - g_bars_late_last);
   Jrn(CR_EV_LATEBAR, JrnSymCode(sym), KV("why", why) + KT("t", t_utc) + KI("wait_s", wait));
  }

//+------------------------------------------------------------------+
//| the store of one symbol                                          |
//+------------------------------------------------------------------+
class CBarStore
  {
public:
   int      sym;
   // kept bars
   CrBar    b[];
   int      n;                         // kept bars retained in b
   long     base;                      // absolute index of b[0]
   int      fed;                       // b index of the next bar to feed
   // broker bars as read
   datetime last_srv;                  // server start of the last broker bar taken (0 = none)
   datetime first_raw;                 // server start of the first broker bar taken since the load (0 = none)
   datetime prev_end;                  // UTC end of the previous broker bar, or the window start (hole scan); 0 = none
   CrRawBar r3[3];                     // the last 3 broker bars taken
   int      n3;
   long     masked[CR_MASK_N];
   long     raw_n;
   // ticks (live GAP)
   datetime tick_srv;                  // time of the last tick seen (server)
   datetime tk[CR_BARS_MAXTICK];       // minutes seen ticking (server), after last_srv, oldest first
   int      ntk;
   datetime wait_since;                // a ticked minute's bar is awaited since (server), 0 = none
   // READY
   bool     ready;
   bool     no_data;                   // the load read failed
   bool     sync;
   bool     depth;
   bool     stable;
   bool     said;                      // a READY / NOTREADY line was written since the load
   string   why_said;
   bool     push10;
   datetime load_srv;                  // server time of the load
   datetime load_Msrv;                 // load barrier (server)
   datetime ws_srv;                    // load window start (server)
   ulong    chk;                       // fingerprint of the load read
   long     chk_n;
   datetime next_check;
   CrHole   holes[CR_BARS_MAXHOLES];
   int      nholes;
   long     holes_seen;
   // daily costs
   datetime cday;                      // server day of the accumulator (server midnight), 0 = none
   datetime cday_lo, cday_hi;          // its UTC bounds
   double   craw[];
   double   cpap[];
   int      cn;
   datetime lday;                      // the last finished day
   double   lraw, lpap;
   bool     lok;

            CBarStore() { sym = 0; n = 0; base = 0; fed = 0; cn = 0; }

   void Reset()
     {
      ArrayResize(b, 0, 65536);
      n = 0;
      base = 0;
      fed = 0;
      last_srv = 0;
      first_raw = 0;
      prev_end = 0;
      n3 = 0;
      for(int k = 0; k < CR_MASK_N; k++) masked[k] = 0;
      raw_n = 0;
      tick_srv = 0;
      ntk = 0;
      wait_since = 0;
      ready = false;
      no_data = false;
      sync = false;
      depth = false;
      stable = false;
      said = false;
      why_said = "";
      push10 = false;
      load_srv = 0;
      load_Msrv = 0;
      ws_srv = 0;
      chk = 0;
      chk_n = 0;
      next_check = 0;
      nholes = 0;
      holes_seen = 0;
      cday = 0;
      cday_lo = 0;
      cday_hi = 0;
      cn = 0;
      lday = 0;
      lraw = 0.0;
      lpap = 0.0;
      lok = false;
     }

   void Add(const CrBar &x)
     {
      if(n >= ArraySize(b)) ArrayResize(b, n + 1, 65536);
      b[n] = x;
      n++;
     }

   // keep memory bounded on long runs: drop fed bars, keeping the last CR_BARS_KEEP fed ones
   void Compact()
     {
      if(fed < CR_BARS_COMPACT) return;
      int drop = fed - CR_BARS_KEEP;
      for(int i = drop; i < n; i++) b[i - drop] = b[i];
      n -= drop;
      fed -= drop;
      base += drop;
      ArrayResize(b, n, 65536);
     }

   long MaskedAll()
     {
      long s = 0;
      for(int k = 1; k < CR_MASK_N; k++) s += masked[k];
      return s;
     }

   void HoleAdd(const datetime a, const datetime bnd)
     {
      if(ready) return;                               // READY stays until the next load: later holes are the lab's too
      if((long)(bnd - a) <= CR_BARS_GAP_S) return;
      if(BarsOpenSecs(g_sym[sym].family, a, bnd, CR_BARS_GAP_S) <= CR_BARS_GAP_S) return;
      if(nholes >= CR_BARS_MAXHOLES)
        {
         for(int i = 1; i < nholes; i++) holes[i - 1] = holes[i];
         nholes--;
        }
      bool known = BarsAccepted(sym, a, bnd);          // accepted before a rebuild: the broker's own already
      holes[nholes].a = a;
      holes[nholes].b = bnd;
      holes[nholes].reads = known ? CR_BARS_ACCEPT : 0;
      holes[nholes].said = known;
      holes[nholes].accepted = known;
      nholes++;
      holes_seen++;
     }

   // one broker bar, in time order: hole scan, mask, revision copy; the kept bar is stored unless store_it is
   // false (a late bar: a rebuild was asked for)
   void Take(const MqlRates &r, const bool store_it)
     {
      datetime t = ClkServerToUtc(r.time);
      if(prev_end > 0 && t > prev_end) HoleAdd(prev_end, t);
      prev_end = t + 60;
      int why = BarsMaskReason(sym, r);
      if(n3 == 3)
        {
         r3[0] = r3[1];
         r3[1] = r3[2];
         n3 = 2;
        }
      r3[n3].t = r.time;
      r3[n3].o = r.open;
      r3[n3].h = r.high;
      r3[n3].l = r.low;
      r3[n3].c = r.close;
      r3[n3].s = r.spread;
      n3++;
      if(first_raw == 0) first_raw = r.time;
      last_srv = r.time;
      raw_n++;
      if(why != CR_MASK_KEPT)
        {
         masked[why]++;
         return;
        }
      if(!store_it) return;
      CrBar x;
      BarsMakeAt(sym, r, t, x);
      Add(x);
     }

   // a minute seen ticking (server): its bar must come
   void Ticked(const datetime m)
     {
      if(m <= last_srv) return;
      if(ntk > 0 && tk[ntk - 1] >= m) return;
      if(ntk >= CR_BARS_MAXTICK)
        {
         for(int i = 1; i < ntk; i++) tk[i - 1] = tk[i];
         ntk--;
        }
      tk[ntk] = m;
      ntk++;
     }

   // the load read of [M - depth, M); false when the read failed (no history yet)
   bool Load(const datetime Msrv, const datetime now)
     {
      load_srv = now;
      load_Msrv = Msrv;
      ws_srv = Msrv - (datetime)g_sym[sym].depth_days * 86400;
      next_check = now + CR_BARS_STABLE_S;
      if(!g_sym[sym].ok)
        {
         no_data = true;
         last_srv = Msrv - 60;
         return false;
        }
      string nm = g_sym[sym].name;
      sync = SeriesInfoInteger(nm, PERIOD_M1, SERIES_SYNCHRONIZED) != 0;
      long fd = SeriesInfoInteger(nm, PERIOD_M1, SERIES_FIRSTDATE);
      depth = (fd > 0 && fd <= (long)ws_srv);
      MqlRates r[];
      int k = CopyRates(nm, PERIOD_M1, (datetime)ws_srv, (datetime)(Msrv - 1), r);
      no_data = (k < 0);
      if(depth) prev_end = ClkServerToUtc(ws_srv);    // the window's own start counts for the hole scan
      if(k > 0)
        {
         BarsChk(sym, r, k, Msrv, chk, chk_n);
         for(int i = 0; i < k; i++)
           {
            if(r[i].time >= Msrv) break;
            Take(r[i], true);
           }
        }
      else BarsChk(sym, r, 0, Msrv, chk, chk_n);
      if(last_srv == 0) last_srv = Msrv - 60;          // polls go on from the load barrier
      return !no_data;
     }

   // the last 3 broker bars read again: false when they are the same (or the read failed)
   bool Revised(string &why)
     {
      why = "";
      if(n3 == 0 || !g_sym[sym].ok) return false;
      MqlRates r[];
      int k = CopyRates(g_sym[sym].name, PERIOD_M1, (datetime)r3[0].t, (datetime)r3[n3 - 1].t, r);
      if(k < 0) return false;
      if(k != n3)
        {
         why = "count";
         return true;
        }
      for(int i = 0; i < k; i++)
        {
         if(r[i].time != r3[i].t || r[i].open != r3[i].o || r[i].high != r3[i].h || r[i].low != r3[i].l || r[i].close != r3[i].c
            || r[i].spread != r3[i].s)
           {
            why = "value";
            return true;
           }
        }
      return false;
     }

   // new broker bars before Msrv: 0 done, 1 wait (a minute seen ticking has no bar yet)
   int Poll(const datetime Msrv, const datetime now)
     {
      if(!g_sym[sym].ok) return 0;
      MqlRates r[];
      int k = 0;
      datetime from = last_srv + 60;
      if(from <= Msrv - 1) k = CopyRates(g_sym[sym].name, PERIOD_M1, (datetime)from, (datetime)(Msrv - 1), r);
      if(k < 0) k = 0;                                 // a failed read: the ticks decide below
      datetime miss[CR_BARS_MAXTICK];
      int nmiss = 0;
      for(int j = 0; j < ntk; j++)
        {
         datetime m = tk[j];
         if(m >= Msrv || m <= last_srv) continue;
         bool found = false;
         for(int i = 0; i < k && !found; i++)
            if(r[i].time == m) found = true;
         if(!found)
           {
            miss[nmiss] = m;
            nmiss++;
           }
        }
      if(nmiss > 0)
        {
         if(wait_since == 0) wait_since = now;
         if((long)(now - wait_since) < CR_BARS_WAIT_S) return 1;
         for(int j = 0; j < nmiss; j++)
           {
            g_bars_gap_live++;
            Jrn(CR_EV_GAP, JrnSymCode(sym), KT("minute", ClkServerToUtc(miss[j])) + KI("live", 1) + KI("waited_s", (long)(now - wait_since)));
           }
         JrnPush("barre manquante " + g_sym[sym].base + " a " + ClkStr(ClkServerToUtc(miss[0])) + " UTC (" + IntegerToString(nmiss) + ")", false);
        }
      wait_since = 0;
      for(int i = 0; i < k; i++)
        {
         if(r[i].time <= last_srv) continue;
         if(r[i].time >= Msrv) break;
         datetime t = ClkServerToUtc(r[i].time);
         bool late = (t < g_bars_M);
         if(late) BarsLate(sym, "late bar", t);
         Take(r[i], !late);
        }
      int keep = 0;
      for(int j = 0; j < ntk; j++)
         if(tk[j] >= Msrv)
           {
            tk[keep] = tk[j];
            keep++;
           }
      ntk = keep;
      return 0;
     }

   // daily cost statistics of the fed kept bars (server day)
   void CostAdd(const CrBar &x)
     {
      if(cn == 0 || x.t < cday_lo || x.t >= cday_hi)
        {
         if(cn > 0)
           {
            lday = cday;
            lraw = CrMedian(craw, cn);
            lpap = CrMedian(cpap, cn);
            lok = true;
           }
         cday = ClkServerDay(x.t);
         cday_lo = ClkServerToUtc(cday);
         cday_hi = ClkServerToUtc(cday + 86400);
         cn = 0;
        }
      double mid = (x.bo + x.ao) / 2;
      if(!(mid > 0.0)) return;
      if(cn >= ArraySize(craw))
        {
         ArrayResize(craw, cn + 512);
         ArrayResize(cpap, cn + 512);
        }
      craw[cn] = x.s_raw * g_sym[sym].point / mid * 1e4;
      cpap[cn] = (x.ao - x.bo) / mid * 1e4;
      cn++;
     }

   bool Cost(const datetime day_srv, double &raw_bp, double &paper_bp)
     {
      if(cn > 0 && cday == day_srv)
        {
         raw_bp = CrMedian(craw, cn);
         paper_bp = CrMedian(cpap, cn);
         return true;
        }
      if(lok && lday == day_srv)
        {
         raw_bp = lraw;
         paper_bp = lpap;
         return true;
        }
      raw_bp = 0.0;
      paper_bp = 0.0;
      return false;
     }

   string Summary()
     {
      datetime t0 = 0, t1 = 0;
      if(n > 0)
        {
         t0 = b[0].t;
         t1 = b[n - 1].t;
        }
      string kv = KI("bars", n) + KI("raw", raw_n) + KT("first", t0) + KT("last", t1) + KI("masked", MaskedAll());
      for(int k = 1; k < CR_MASK_N; k++)
         if(masked[k] > 0) kv = kv + KI(CR_MASK_NAME[k], masked[k]);
      return kv;
     }

   // READY checks (BarsTimer): 2 s after the load, then every 60 s until READY
   void Check(const datetime now)
     {
      if(ready || !g_sym[sym].ok) return;
      if(now < next_check) return;
      next_check = now + CR_BARS_RECHECK_S;
      string nm = g_sym[sym].name;
      // (3) the second read of the load window agrees with the first
      if(!stable && !no_data)
        {
         MqlRates r[];
         int k = CopyRates(nm, PERIOD_M1, (datetime)ws_srv, (datetime)(load_Msrv - 1), r);
         if(k >= 0)
           {
            ulong h = 0;
            long c = 0;
            BarsChk(sym, r, k, load_Msrv, h, c);
            if(h == chk && c == chk_n) stable = true;
            else
              {
               BarsLate(sym, "load read changed", ClkServerToUtc(load_Msrv));
               chk = h;
               chk_n = c;
              }
           }
        }
      // a symbol without history at the load: its history may have come since
      if(no_data)
        {
         MqlRates r[];
         int k = CopyRates(nm, PERIOD_M1, (datetime)ws_srv, (datetime)(load_Msrv - 1), r);
         if(k > 0) BarsLate(sym, "history arrived", ClkServerToUtc(r[0].time));
         else if(k == 0)
           {
            no_data = false;
            stable = true;
           }
        }
      sync = SeriesInfoInteger(nm, PERIOD_M1, SERIES_SYNCHRONIZED) != 0;
      long fd = SeriesInfoInteger(nm, PERIOD_M1, SERIES_FIRSTDATE);
      datetime wsn = now - (datetime)g_sym[sym].depth_days * 86400;
      depth = (fd > 0 && fd <= (long)wsn);
      // (4) holes inside the current window
      datetime wsu = ClkServerToUtc(wsn);
      int open_holes = 0, new_holes = 0, keep = 0;
      for(int i = 0; i < nholes; i++)
        {
         if(holes[i].b <= wsu) continue;              // left the window: forgotten
         if(!holes[i].accepted)
           {
            if(!holes[i].said)
              {
               holes[i].said = true;
               new_holes++;
               open_holes++;
               Jrn(CR_EV_GAP, g_sym[sym].base, KT("from", holes[i].a) + KT("to", holes[i].b) + KI("min", (long)(holes[i].b - holes[i].a) / 60)
                   + KI("reads", 0) + KI("accepted", 0));
              }
            else
              {
               MqlRates r[];
               int k = CopyRates(nm, PERIOD_M1, (datetime)ClkUtcToServer(holes[i].a), (datetime)(ClkUtcToServer(holes[i].b) - 1), r);
               if(k > 0)
                 {
                  BarsLate(sym, "hole filled", holes[i].a);
                  open_holes++;
                 }
               else
                 {
                  if(k == 0 && sync) holes[i].reads++;
                  if(holes[i].reads >= CR_BARS_ACCEPT)
                    {
                     holes[i].accepted = true;
                     BarsAccept(sym, holes[i].a, holes[i].b);
                     Jrn(CR_EV_GAP, g_sym[sym].base, KT("from", holes[i].a) + KT("to", holes[i].b)
                         + KI("min", (long)(holes[i].b - holes[i].a) / 60) + KI("reads", holes[i].reads) + KI("accepted", 1));
                    }
                  else open_holes++;
                 }
              }
           }
         holes[keep] = holes[i];
         keep++;
        }
      nholes = keep;
      if(new_holes > 0)
         JrnPush("trou dans l'historique " + g_sym[sym].base + " (" + IntegerToString(new_holes) + ") : symbole pas pret", false);
      string why = "";
      if(no_data) why = why + "nodata,";
      if(!sync) why = why + "sync,";
      if(!depth) why = why + "depth,";
      if(!stable) why = why + "stable,";
      if(open_holes > 0) why = why + "holes,";
      if(why == "")
        {
         ready = true;
         Jrn(CR_EV_READY, g_sym[sym].base, Summary() + KI("holes", nholes) + KI("depth_days", g_sym[sym].depth_days));
        }
      else
        {
         why = StringSubstr(why, 0, StringLen(why) - 1);
         if(why != why_said)
           {
            Jrn(CR_EV_NOTREADY, g_sym[sym].base, KV("why", why) + Summary() + KI("holes", open_holes));
            why_said = why;
           }
         if(!push10 && (long)(now - load_srv) >= CR_BARS_NOTREADY_PUSH_S)
           {
            push10 = true;
            JrnPush(g_sym[sym].base + " pas pret depuis 10 min (" + why + ")", false);
           }
        }
      said = true;
     }
  };

CBarStore g_bs[CR_NSYM];

//+------------------------------------------------------------------+
//| the API                                                          |
//+------------------------------------------------------------------+
void BarsReset()
  {
   for(int s = 0; s < CR_NSYM; s++)
     {
      g_bs[s].sym = s;
      g_bs[s].Reset();
     }
   g_bars_M = 0;
   g_bars_late = false;
   g_bars_rev_M = 0;
   g_bars_first_try = 0;
   g_bars_bar_now = 0;
   g_bars_bar_M = 0;
  }

bool BarsInit(string &err)
  {
   err = "";
   BarsReset();
   g_bars_late_last = 0;
   g_bars_late_n = 0;
   g_bars_gap_live = 0;
   for(int s = 0; s < CR_NSYM; s++) g_bars_nacc[s] = 0;
   for(int s = 0; s < CR_NSYM; s++)
      if(g_sym[s].depth_days <= 0 || !(g_sym[s].point > 0.0))
        {
         err = "bars: symbol " + g_sym[s].base + " has no depth or no point";
         return false;
        }
   return true;
  }

// the last tick of every symbol: the barrier's tick rule and the minutes whose bar must come
void BarsTicks()
  {
   for(int s = 0; s < CR_NSYM; s++)
     {
      if(!g_sym[s].ok) continue;
      MqlTick k;
      if(!SymbolInfoTick(g_sym[s].name, k)) continue;
      if(k.time <= 0) continue;
      if(k.time > g_bs[s].tick_srv) g_bs[s].tick_srv = k.time;
      g_bs[s].Ticked(k.time - k.time % 60);
     }
  }

datetime BarsBarrier(const datetime now_srv)
  {
   if(now_srv == g_bars_bar_now && g_bars_bar_now > 0) return g_bars_bar_M;
   BarsTicks();
   datetime u = ClkServerToUtc(now_srv);
   datetime cur = u - u % 60;                     // the minute in progress
   datetime mt = (u - 2) - (u - 2) % 60;          // TimeTradeServer() >= M + 2 s
   datetime M = cur;                              // every symbol ticked in the new minute, or is closed ...
   if(mt >= cur) M = mt;
   else
     {
      datetime cur_srv = ClkUtcToServer(cur);
      for(int s = 0; s < CR_NSYM && M == cur; s++)
        {
         if(!g_sym[s].ok) continue;
         if(g_bs[s].tick_srv >= cur_srv) continue;
         datetime c0 = 0, c1 = 0;
         if(ClkInClosure(g_sym[s].family, cur, c0, c1)) continue;
         M = mt;                                  // ... else the minute that started at least 2 s ago
        }
     }
   g_bars_bar_now = now_srv;
   g_bars_bar_M = M;
   return M;
  }

int BarsLoad(const datetime now_srv)
  {
   for(int s = 0; s < CR_NSYM; s++)
     {
      g_bs[s].sym = s;
      g_bs[s].Reset();
     }
   g_bars_bar_now = 0;                            // read the ticks again for the fresh stores
   datetime M = BarsBarrier(now_srv);
   datetime Msrv = ClkUtcToServer(M);
   int ok = 0, want = 0;
   for(int s = 0; s < CR_NSYM; s++)
     {
      if(g_sym[s].ok) want++;
      if(g_bs[s].Load(Msrv, now_srv)) ok++;
     }
   if(ok == 0 && want > 0)
     {
      if(g_bars_first_try == 0) g_bars_first_try = now_srv;
      if((long)(now_srv - g_bars_first_try) < 60) return CR_LOAD_RETRY;
     }
   g_bars_first_try = 0;
   g_bars_M = M;
   g_bars_rev_M = M;
   g_bars_late = false;
   return CR_LOAD_OK;
  }

int BarsPoll(const datetime M)
  {
   datetime now = TimeTradeServer();
   if(g_bars_late && (g_bars_late_last == 0 || (long)(now - g_bars_late_last) >= CR_BARS_LATE_S))
     {
      g_bars_late_last = now;
      return CR_POLL_LATEBAR;
     }
   datetime Msrv = ClkUtcToServer(M);
   if(M > g_bars_rev_M)
     {
      g_bars_rev_M = M;
      for(int s = 0; s < CR_NSYM; s++)
        {
         string why = "";
         if(g_bs[s].Revised(why)) BarsLate(s, "revised " + why, ClkServerToUtc(g_bs[s].r3[0].t));
        }
      if(g_bars_late && (g_bars_late_last == 0 || (long)(now - g_bars_late_last) >= CR_BARS_LATE_S))
        {
         g_bars_late_last = now;
         return CR_POLL_LATEBAR;
        }
     }
   bool wait = false;
   for(int s = 0; s < CR_NSYM; s++)
      if(g_bs[s].Poll(Msrv, now) == 1) wait = true;
   if(wait) return CR_POLL_WAIT;
   g_bars_M = M;
   return CR_POLL_OK;
  }

bool BarsNext(const datetime M, CrBar &x)
  {
   int best = -1;
   datetime bt = 0;
   for(int s = 0; s < CR_NSYM; s++)
     {
      if(g_bs[s].fed >= g_bs[s].n) continue;
      datetime t = g_bs[s].b[g_bs[s].fed].t;
      if(t >= M) continue;
      if(best < 0 || t < bt)
        {
         best = s;
         bt = t;
        }
     }
   if(best < 0) return false;
   x = g_bs[best].b[g_bs[best].fed];
   g_bs[best].fed++;
   g_bs[best].CostAdd(x);
   g_bs[best].Compact();
   return true;
  }

void BarsTimer(const datetime now_srv)
  {
   for(int s = 0; s < CR_NSYM; s++) g_bs[s].Check(now_srv);
  }

bool BarsReady(const int sym)
  {
   if(sym < 0 || sym >= CR_NSYM) return false;
   return g_bs[sym].ready;
  }

int BarsCount(const int sym)
  {
   if(sym < 0 || sym >= CR_NSYM) return 0;
   return (int)(g_bs[sym].base + g_bs[sym].fed);
  }

bool BarsAt(const int sym, const int i, CrBar &x)
  {
   if(sym < 0 || sym >= CR_NSYM) return false;
   long k = (long)i - g_bs[sym].base;
   if(k < 0 || k >= g_bs[sym].fed) return false;
   x = g_bs[sym].b[(int)k];
   return true;
  }

int BarsIndex(const int sym, const datetime t_utc)
  {
   if(sym < 0 || sym >= CR_NSYM) return 0;
   int lo = 0, hi = g_bs[sym].fed;
   while(lo < hi)
     {
      int mid = (lo + hi) / 2;
      if(g_bs[sym].b[mid].t < t_utc) lo = mid + 1;
      else hi = mid;
     }
   return (int)(g_bs[sym].base + lo);
  }

datetime BarsStart()
  {
   datetime t = 0;
   for(int s = 0; s < CR_NSYM; s++)
      if(g_bs[s].n > 0 && (t == 0 || g_bs[s].b[0].t < t)) t = g_bs[s].b[0].t;
   return t;
  }

bool BarsCost(const int sym, const datetime day_srv, double &raw_bp, double &paper_bp)
  {
   if(sym < 0 || sym >= CR_NSYM)
     {
      raw_bp = 0.0;
      paper_bp = 0.0;
      return false;
     }
   return g_bs[sym].Cost(day_srv, raw_bp, paper_bp);
  }

long BarsMasked(const int sym, const int reason)
  {
   if(sym < 0 || sym >= CR_NSYM || reason < 0 || reason >= CR_MASK_N) return 0;
   if(reason == CR_MASK_KEPT) return g_bs[sym].raw_n - g_bs[sym].MaskedAll();
   return g_bs[sym].masked[reason];
  }
#endif

// ==== end src/CR_Bars.mqh
// ==== begin src/CR_Paper.mqh
//+------------------------------------------------------------------+
//| CR_Paper.mqh - the paper engine (SPEC 2.5). Owner: C.             |
//|                                                                  |
//| A streaming port of goldlab/sim.py _run (:69-211): one chain per |
//| sleeve, one position at a time, fed with the kept closed M1 bars |
//| of the sleeve's traded symbol (paper quotes, CrBar) in time      |
//| order. It alone decides entries, the one-position rule and exits.|
//|                                                                  |
//| API (signatures fixed by S0):                                    |
//|   PapInit()        once at OnInit       PapReset()  every rebuild |
//|   PapSubmit(o)     a rule's order; false = refused (ERROR)       |
//|   PapSubmitExit(e) a rule's exit (CrExit); false = no room       |
//|   PapOnBar(sl, b)  one kept closed bar of the sleeve's symbol,   |
//|                    after the rules' OnBar for that bar           |
//|   PapOnBarrier(M)  every minute M, after OnMinute(M): windows    |
//|                    that end, hold extension, late gap revision   |
//|   PapEvents() PapEvent(k, e) PapClearEvents()   the event queue  |
//|   PapTrade(sl, t)  the open trade (a pending gap exit counts as  |
//|                    open); false when flat                        |
//|   PapPending(sl,o) the oldest order still waiting; false if none |
//|   PapLastExitBar(sl)  start of the last trade's exit bar (0)     |
//| The driver (CR_Main) feeds, for every whole UTC minute M: every  |
//| kept bar starting before M (PapOnBar after the rules' OnBar),    |
//| then OnMinute(M), then PapOnBarrier(M). So at PapOnBarrier(M)    |
//| every bar starting before M is final, and no bar starting at or  |
//| after M has been seen. PapOnBar(sl, b) first runs the sleeve's   |
//| part of the barrier at b's start (a no-op when the driver called |
//| PapOnBarrier for every minute), so a skipped barrier never lets  |
//| a bar answer a question it cannot answer.                        |
//|                                                                  |
//| How the paper reads a CrOrder ("0 = none" for every optional     |
//| field; a NaN counts as none too):                                |
//|   activation  the first kept bar b with t_from <= b.t <= t_to    |
//|               fed after PapSubmit (an order emitted from OnBar(b)|
//|               may activate on b itself). With after_exit_of = X: |
//|               the first such bar AFTER the bar where the CrExit  |
//|               of oid X resolved; void when that CrExit is void.  |
//|   skip        at activation, when the sleeve's trade is open or  |
//|               exited on b (sim.py:80): the order is gone.        |
//|   etype       0 market: fill at b's open. 1 stop, 2 limit: fill  |
//|               on bars starting before expiry_excl (sim.py:87-111)|
//|               3 OCO: buy stop at level, sell stop at level2; both|
//|               touched in one bar -> the side against the bar's   |
//|               move, bc >= bo -> short (trend/strategy.py:303-317)|
//|               then a stop entry of that side.                    |
//|   stop        absolute when set, else fill -/+ stop_dist; a stop |
//|               on the wrong side exits on the fill bar ('gap').   |
//|   target      absolute when set, else fill +/- target_dist.      |
//|   trail, be   sim.py:164-173 (from the bar's close, next bar on).|
//|   x_sched     time exit at the open of the exit bar, never on    |
//|               the fill bar (sim.py:137). x_gap false: the first  |
//|               kept bar starting at or after x. x_gap true        |
//|               (gl.exit_index): the first kept bar starting in    |
//|               [x, x + 30 min]; if none, the last kept bar before |
//|               x, unless that is the fill bar: then the first kept|
//|               bar after x.                                       |
//|   xh, xh_r    hold extension (H2, variants.py:206-233): at the   |
//|               first barrier at or after x, an open trade whose   |
//|               last processed bar c is at or after its fill bar   |
//|               and side x (mark - fill) >= xh_r x |fill - stop0|, |
//|               mark = c's bid close (long) or ask close (short),  |
//|               gets x := max(xh, x) with the same gap flag (HOLD).|
//|   refuse      at the fill, spread = ao - bo of the fill bar:     |
//|               1 (payoff): d0 < 3 x spread, d0 = |fill - stop| for|
//|               an absolute stop, else stop_dist (vhi_sleeves      |
//|               stop_distance_at_fill, variants.refuse);           |
//|               2 (synthesis_B): |fill - stop0| < 3 x spread or a  |
//|               stop on the wrong side (common.py:136-169). A      |
//|               refused order leaves no trace (PREFUSE): the sleeve|
//|               stays flat and nothing counts as exited on b.      |
//|   void_le     brk72's wrapper (recalc.py:43-53, exit_i > entry_i)|
//|               the order never existed when its exit bar (x with  |
//|               the gap rule) does not follow its ACTIVATION bar   |
//|               (entry_i): x at or before that bar (PVOID at       |
//|               activation), or no kept bar from just after it to  |
//|               x + 30 min (PVOID at that barrier, armed or filled)|
//| A CrExit of oid X: at the first kept bar e inside its window it  |
//| replaces X's time exit by "the first kept bar at or after e, not |
//| the fill bar, no gap rule, no hold" (noise30 sets exit_i = e,    |
//| reason 'time'); it is void when its window ends without a bar.   |
//|                                                                  |
//| Late gap revision (SPEC 2.5, P4). While the 30-minute question of|
//| a gap-rule exit x is open (no kept bar seen at or after x yet),  |
//| the trade keeps its last two processed bars and the stop before  |
//| the last one. When the barrier passes x + 30 min with no kept bar|
//| in [x, x + 30 min], the last processed bar L is the last kept bar|
//| before x: the paper books the time exit at L's open (PREVISE,    |
//| replacing a stop, target, trail or gap exit booked on L); if L is|
//| the fill bar the exit waits for the next kept bar; void_le with  |
//| L = the activation bar -> PVOID. The hold test of the barrier at |
//| x was made on L; the revision makes it again on the bar before L |
//| (the lab's c = exit bar - 1): HOLD to grant it, HOLD with px = 0 |
//| and x = x_sched to withdraw it. A hold granted there moves the   |
//| exit past the hole: L then stands as a bar of the trade, and the |
//| extended exit gets its own 30-minute question.                   |
//|                                                                  |
//| Orders waiting together. Two market orders of one sleeve may wait|
//| at once (each resolves at its own activation bar, in emission    |
//| order), unless one has void_le: a void_le trade can be voided    |
//| after its activation bar, and an order skipped on that bar would |
//| have been taken by the lab. Every other overlap of spans with a  |
//| waiting order is refused (PapSubmit false -> ERROR): the lab     |
//| decides such a pair with future bars. Span = [t_from, t_to] for a|
//| market order, [t_from (or its activation bar), max(t_to,         |
//| expiry_excl - 1)] otherwise. None of this occurs in the ten rules|
//| (SPEC 2.5).                                                      |
//|                                                                  |
//| Events (CrPEvent; t is the lab stamp, bar the bar that made it): |
//|   PFILL   t = bar = fill bar; px fill; stop = st0 = initial stop;|
//|           x = x_sched                                            |
//|   PEXIT   t = exit bar + 60 s ('time': the bar start); px exit;  |
//|           reason stop, target, time, trail or gap                |
//|   PSTOP   t = bar + 60 s; stop = the new stop (trail or be)      |
//|   PREVISE t = bar = L; px = the time exit at L's open; reason    |
//|           time; stop = the stop before L                         |
//|   PVOID   t = bar = the activation bar; reason void (px = fill   |
//|           when a trade existed, else 0)                          |
//|   PREFUSE t = bar = the fill bar; px the fill it would have had; |
//|           reason refused                                         |
//|   HOLD    t = the barrier; bar = c; px = the mark (0 when the    |
//|           hold is withdrawn); x = the time exit now in effect    |
//| No swap, no end-of-data exit (a trade open at the end stays open)|
//+------------------------------------------------------------------+
#ifndef CR_PAPER_MQH
#define CR_PAPER_MQH
// (already inlined: CR_Types.mqh)

#define CR_PAP_QMAX 8                  // orders a sleeve may hold at once (waiting for activation or for a fill)
#define CR_PAP_XMAX 8                  // rule exits a sleeve may hold at once
#define CR_PAP_QALL 128                // CR_MAX_SL x CR_PAP_QMAX
#define CR_PAP_XALL 128                // CR_MAX_SL x CR_PAP_XMAX
#define CR_PAP_GAP 1800                // gl.exit_index: a bar more than 30 min after x does not take the exit

// queued order states (0 = dead, dropped at the next compaction)
#define CR_PO_WAIT 1                   // waiting for its activation bar
#define CR_PO_ARMED 2                  // stop, limit or OCO activated, waiting for its fill
// rule exit states
#define CR_PX_WAIT 1                   // waiting for a kept bar inside its window
#define CR_PX_DONE 2                   // resolved on the bar .bar
#define CR_PX_VOID 3                   // its window ended without a kept bar
// trade states
#define CR_PT_NONE 0                   // no trade
#define CR_PT_OPEN 1                   // open (a pending gap exit included)
#define CR_PT_EXITED 2                 // exit booked on its last processed bar; a late gap revision may still replace it
// hold extension states
#define CR_PH_NONE 0                   // no hold to test
#define CR_PH_DUE 1                    // to test at the first barrier at or after x0
#define CR_PH_TENT 2                   // tested at that barrier; the gap revision of x0 tests it again
#define CR_PH_DONE 3                   // decided for good

struct CrPapOrd                        // an order of a sleeve's queue
  {
   CrOrder  o;
   int      st;                        // CR_PO_*
   datetime act;                       // activation bar start (armed)
  };

struct CrPapExit                       // a rule exit of a sleeve's list
  {
   CrExit   e;
   int      st;                        // CR_PX_*
   datetime bar;                       // start of the bar where it resolved
  };

struct CrPapTrade                      // the sleeve's trade
  {
   int      st;                        // CR_PT_*
   CrOrder  o;                         // the order it came from
   int      side;                      // +1 / -1 (OCO: the side that filled)
   int      et;                        // entry type for the fill-bar target rule (OCO: stop)
   double   lv;                        // the entry level of that rule
   datetime act, fill;                 // activation and fill bar starts
   double   fp, st0;                   // fill price, initial stop
   bool     tg_on;                     // a target exists
   double   tg;                        // the target
   double   cur, best;                 // current stop, best price since the fill (sim.py 'cur', 'best')
   bool     moved;                     // trail or break-even moved the stop
   CrBar    b_last;                    // the last processed bar of the trade
   CrBar    b_prev;                    // the one before (t = 0: none, the last bar is the fill bar)
   double   cur_prev;                  // the stop before b_last was processed
   datetime x;                         // the time exit in effect (0 = none)
   datetime x0;                        // the order's own x_sched (the hold applies to it)
   bool     xg;                        // the gap rule applies to x
   datetime q;                         // the time whose 30-minute question is open
   bool     q_open;                    // no kept bar seen at or after q yet
   bool     q_x0;                      // that question is x0's (void_le and the hold re-test belong to it)
   int      hold;                      // CR_PH_*
   bool     held;                      // the hold test passed: x = max(xh, x0)
   int      reason;                    // exit reason (CR_R_*), CR_R_NONE while open
   datetime xbar;                      // exit bar start
   double   xpx;                       // exit price
  };

CrPapOrd   g_pap_q[CR_PAP_QALL];       // sleeve sl's queue: g_pap_q[sl * CR_PAP_QMAX + k], k < g_pap_qn[sl], emission order
int        g_pap_qn[CR_MAX_SL];
CrPapExit  g_pap_x[CR_PAP_XALL];       // sleeve sl's rule exits: g_pap_x[sl * CR_PAP_XMAX + k], k < g_pap_xn[sl]
int        g_pap_xn[CR_MAX_SL];
CrPapTrade g_pap_t[CR_MAX_SL];
datetime   g_pap_lx[CR_MAX_SL];        // start of the exit bar of the sleeve's last trade (0 = none)
datetime   g_pap_lx0[CR_MAX_SL];       // its value before the current trade's fill (PVOID puts it back)
datetime   g_pap_last[CR_MAX_SL];      // start of the last bar fed to the sleeve
datetime   g_pap_M = 0;                // the last barrier
CrPEvent   g_pap_ev[];
int        g_pap_evn = 0;
long       g_pap_err = 0;              // orders or exits refused by PapSubmit / PapSubmitExit, events lost

// a sleeve index the paper can hold (the fixed tables have CR_PAP_QALL / CR_PAP_QMAX rows)
bool PapSleeveOk(const int sl)
  {
   return sl >= 0 && sl < g_nsl && sl < CR_MAX_SL && sl < CR_PAP_QALL / CR_PAP_QMAX && sl < CR_PAP_XALL / CR_PAP_XMAX;
  }

//+------------------------------------------------------------------+
//| Small helpers                                                    |
//+------------------------------------------------------------------+
// an optional field is set: finite and not 0
bool PapOn(const double v) { return MathIsValidNumber(v) && v != 0.0; }

// the first barrier (whole UTC minute) after t, and at or after t
datetime PapMinAfter(const datetime t) { return t - t % 60 + 60; }
datetime PapMinFrom(const datetime t)
  {
   datetime m = t - t % 60;
   if(m < t) m += 60;
   return m;
  }

double PapSlipM(const int sl) { return g_sym[g_sl[sl].sym].slip_mkt; }
double PapSlipS(const int sl) { return g_sym[g_sl[sl].sym].slip_stop; }

void PapEmit(const int ev, const int sl, const long oid, const int side, const datetime t, const datetime bar, const double px,
             const double stop, const double st0, const int reason, const datetime x, const int s_raw, const double s_paper)
  {
   if(g_pap_evn >= ArraySize(g_pap_ev))
     {
      if(ArrayResize(g_pap_ev, g_pap_evn + 64, 256) < g_pap_evn + 1)
        {
         g_pap_err++;                                          // no memory: the event is lost (counted)
         return;
        }
     }
   g_pap_ev[g_pap_evn].ev = ev;
   g_pap_ev[g_pap_evn].sleeve = sl;
   g_pap_ev[g_pap_evn].oid = oid;
   g_pap_ev[g_pap_evn].side = side;
   g_pap_ev[g_pap_evn].t = t;
   g_pap_ev[g_pap_evn].bar = bar;
   g_pap_ev[g_pap_evn].px = px;
   g_pap_ev[g_pap_evn].stop = stop;
   g_pap_ev[g_pap_evn].init_stop = st0;
   g_pap_ev[g_pap_evn].reason = reason;
   g_pap_ev[g_pap_evn].x = x;
   g_pap_ev[g_pap_evn].s_raw = s_raw;
   g_pap_ev[g_pap_evn].s_paper = s_paper;
   g_pap_evn++;
  }

// an event of the trade on bar b
void PapEmitTr(const int ev, const int sl, const CrPapTrade &tr, const datetime t, const CrBar &b, const double px, const int reason)
  {
   PapEmit(ev, sl, tr.o.oid, tr.side, t, b.t, px, tr.cur, tr.st0, reason, tr.x, b.s_raw, b.ao - b.bo);
  }

// the last second at which a bar this order may still act on can start
datetime PapSpanEnd(const CrOrder &o)
  {
   if(o.etype == CR_ET_MARKET) return o.t_to;
   datetime e = o.expiry_excl - 1;
   if(e > o.t_to) return e;
   return o.t_to;
  }

// could the queued order a and the new order b need the same bar in a way only future bars decide?
bool PapOverlap(const CrPapOrd &a, const CrOrder &b)
  {
   if(a.o.etype == CR_ET_MARKET && b.etype == CR_ET_MARKET && !a.o.void_le && !b.void_le) return false;
   datetime a0 = a.o.t_from;
   if(a.st == CR_PO_ARMED) a0 = a.act;
   return a0 <= PapSpanEnd(b) && b.t_from <= PapSpanEnd(a.o);
  }

// index (in g_pap_x) of the latest rule exit of oid for sleeve sl, -1 when none
int PapExitFind(const int sl, const long oid)
  {
   for(int k = g_pap_xn[sl] - 1; k >= 0; k--)
      if(g_pap_x[sl * CR_PAP_XMAX + k].e.oid == oid) return sl * CR_PAP_XMAX + k;
   return -1;
  }

// drop the resolved or void rule exits that no waiting order refers to
void PapExitsCompact(const int sl)
  {
   int base = sl * CR_PAP_XMAX;
   int n = g_pap_xn[sl];
   int w = 0;
   for(int k = 0; k < n; k++)
     {
      bool keep = (g_pap_x[base + k].st == CR_PX_WAIT);
      if(!keep)
         for(int j = 0; j < g_pap_qn[sl]; j++)
            if(g_pap_q[sl * CR_PAP_QMAX + j].st == CR_PO_WAIT && g_pap_q[sl * CR_PAP_QMAX + j].o.after_exit_of == g_pap_x[base + k].e.oid)
              {
               keep = true;
               break;
              }
      if(keep)
        {
         if(w != k) g_pap_x[base + w] = g_pap_x[base + k];
         w++;
        }
     }
   g_pap_xn[sl] = w;
  }

// drop the orders marked dead (st 0), keeping the emission order
void PapOrdersCompact(const int sl)
  {
   int base = sl * CR_PAP_QMAX;
   int n = g_pap_qn[sl];
   int w = 0;
   for(int k = 0; k < n; k++)
     {
      if(g_pap_q[base + k].st == 0) continue;
      if(w != k) g_pap_q[base + w] = g_pap_q[base + k];
      w++;
     }
   g_pap_qn[sl] = w;
  }

//+------------------------------------------------------------------+
//| Exits of a trade                                                 |
//+------------------------------------------------------------------+
// book an exit of the open trade on bar b (PEXIT); a stop, target, trail or gap exit stays open to a late gap revision
// while the 30-minute question of its time exit is open
void PapBookExit(const int sl, CrPapTrade &tr, const CrBar &b, const double px, const int reason)
  {
   tr.reason = reason;
   tr.xbar = b.t;
   tr.xpx = px;
   g_pap_lx[sl] = b.t;
   datetime t = b.t + 60;
   if(reason == CR_R_TIME) t = b.t;                           // sim.py:284: + 1 minute unless 'time'
   PapEmitTr(CR_EV_PEXIT, sl, tr, t, b, px, reason);
   if(reason != CR_R_TIME && tr.q_open) tr.st = CR_PT_EXITED;
   else tr.st = CR_PT_NONE;
  }

// sim.py:136-204 on one bar of the open trade; first = the fill bar (no time exit there, sim.py:137 'i > fi')
void PapManage(const int sl, CrPapTrade &tr, const CrBar &b, const bool first)
  {
   if(!first)
     {
      tr.b_prev = tr.b_last;
      tr.cur_prev = tr.cur;
      tr.b_last = b;
      if(tr.x > 0 && b.t >= tr.x)
        {
         double sm = PapSlipM(sl);
         double pxt = (tr.side > 0) ? b.bo * (1 - sm) : b.ao * (1 + sm);
         PapBookExit(sl, tr, b, pxt, CR_R_TIME);
         return;
        }
     }
   double ss = PapSlipS(sl);
   double cur0 = tr.cur;
   if(tr.side > 0)
     {
      bool hit_stop = (b.bl <= tr.cur);
      bool hit_tgt = tr.tg_on && (b.bh >= tr.tg);
      if(first && tr.et == CR_ET_STOP && hit_tgt && !(b.ao < tr.lv)) hit_tgt = false;
      if(first && tr.et == CR_ET_LIMIT) hit_tgt = false;
      if(hit_stop)
        {
         double px = first ? tr.cur : MathMin(tr.cur, b.bo);
         PapBookExit(sl, tr, b, px * (1 - ss), tr.moved ? CR_R_TRAIL : CR_R_STOP);
         return;
        }
      if(hit_tgt)
        {
         PapBookExit(sl, tr, b, first ? tr.tg : MathMax(tr.tg, b.bo), CR_R_TARGET);
         return;
        }
      if(b.bh > tr.best) tr.best = b.bh;
      if(PapOn(tr.o.trail) && tr.best - tr.o.trail > tr.cur)
        {
         tr.cur = tr.best - tr.o.trail;
         tr.moved = true;
        }
      if(PapOn(tr.o.be) && tr.best - tr.fp >= tr.o.be && tr.fp > tr.cur)
        {
         tr.cur = tr.fp;
         tr.moved = true;
        }
     }
   else
     {
      bool hit_stop = (b.ah >= tr.cur);
      bool hit_tgt = tr.tg_on && (b.al <= tr.tg);
      if(first && tr.et == CR_ET_STOP && hit_tgt && !(b.bo > tr.lv)) hit_tgt = false;
      if(first && tr.et == CR_ET_LIMIT) hit_tgt = false;
      if(hit_stop)
        {
         double px = first ? tr.cur : MathMax(tr.cur, b.ao);
         PapBookExit(sl, tr, b, px * (1 + ss), tr.moved ? CR_R_TRAIL : CR_R_STOP);
         return;
        }
      if(hit_tgt)
        {
         PapBookExit(sl, tr, b, first ? tr.tg : MathMin(tr.tg, b.ao), CR_R_TARGET);
         return;
        }
      if(b.al < tr.best) tr.best = b.al;
      if(PapOn(tr.o.trail) && tr.best + tr.o.trail < tr.cur)
        {
         tr.cur = tr.best + tr.o.trail;
         tr.moved = true;
        }
      if(PapOn(tr.o.be) && tr.fp - tr.best >= tr.o.be && tr.fp < tr.cur)
        {
         tr.cur = tr.fp;
         tr.moved = true;
        }
     }
   if(tr.cur != cur0) PapEmitTr(CR_EV_PSTOP, sl, tr, b.t + 60, b, tr.cur, CR_R_NONE);
  }

//+------------------------------------------------------------------+
//| Fills                                                            |
//+------------------------------------------------------------------+
// does order o fill on bar b? side, fill price, entry type and level of the fill-bar target rule (sim.py:87-111;
// OCO: trend/strategy.py:303-317, then a stop entry of the side touched)
bool PapTryFill(const int sl, const CrOrder &o, const CrBar &b, int &side, double &fp, int &et, double &lv)
  {
   side = o.side;
   et = o.etype;
   lv = o.level;
   fp = 0.0;
   if(o.etype == CR_ET_MARKET)
     {
      double sm = PapSlipM(sl);
      fp = (side > 0) ? b.ao * (1 + sm) : b.bo * (1 - sm);
      return true;
     }
   double ss = PapSlipS(sl);
   if(o.etype == CR_ET_STOP)
     {
      if(side > 0 && b.ah >= lv)
        {
         fp = MathMax(lv, b.ao) * (1 + ss);
         return true;
        }
      if(side < 0 && b.bl <= lv)
        {
         fp = MathMin(lv, b.bo) * (1 - ss);
         return true;
        }
      return false;
     }
   if(o.etype == CR_ET_LIMIT)
     {
      if(side > 0 && b.al <= lv)
        {
         fp = MathMin(lv, b.ao);
         return true;
        }
      if(side < 0 && b.bh >= lv)
        {
         fp = MathMax(lv, b.bo);
         return true;
        }
      return false;
     }
   if(o.etype == CR_ET_OCO)
     {
      bool hu = (b.ah >= o.level);
      bool hd = (b.bl <= o.level2);
      if(!hu && !hd) return false;
      if(hu && hd) side = (b.bc >= b.bo) ? -1 : 1;
      else side = hu ? 1 : -1;
      et = CR_ET_STOP;
      if(side > 0)
        {
         lv = o.level;
         fp = MathMax(lv, b.ao) * (1 + ss);
        }
      else
        {
         lv = o.level2;
         fp = MathMin(lv, b.bo) * (1 - ss);
        }
      return true;
     }
   return false;
  }

// the fill of order o on bar b: refusal, the new trade, its gap exit or the management of the fill bar
void PapOpen(const int sl, CrPapTrade &tr, const CrOrder &o, const datetime act, const CrBar &b, const int side, const double fp,
             const int et, const double lv)
  {
   double st = PapOn(o.stop) ? o.stop : fp - side * o.stop_dist;          // sim.py:117
   bool wrong = (side > 0 && st >= fp) || (side < 0 && st <= fp);         // sim.py:122
   double spread = b.ao - b.bo;
   bool refused = false;
   if(o.refuse == CR_REF_PAYOFF)
     {
      double d0 = PapOn(o.stop) ? MathAbs(fp - o.stop) : o.stop_dist;
      refused = (d0 < 3.0 * spread);
     }
   else if(o.refuse == CR_REF_SB)
      refused = (MathAbs(fp - st) < 3.0 * spread) || wrong;
   if(refused)
     {
      PapEmit(CR_EV_PREFUSE, sl, o.oid, side, b.t, b.t, fp, st, st, CR_R_REFUSED, o.x_sched, b.s_raw, spread);
      return;
     }
   g_pap_lx0[sl] = g_pap_lx[sl];
   tr.st = CR_PT_OPEN;
   tr.o = o;
   tr.side = side;
   tr.et = et;
   tr.lv = lv;
   tr.act = act;
   tr.fill = b.t;
   tr.fp = fp;
   tr.st0 = st;
   tr.tg_on = PapOn(o.target) || PapOn(o.target_dist);                    // sim.py:118-119
   tr.tg = 0.0;
   if(PapOn(o.target)) tr.tg = o.target;
   else if(PapOn(o.target_dist)) tr.tg = fp + side * o.target_dist;
   tr.cur = st;
   tr.best = fp;
   tr.moved = false;
   tr.b_last = b;
   ZeroMemory(tr.b_prev);
   tr.cur_prev = st;
   tr.x = o.x_sched;
   tr.x0 = o.x_sched;
   tr.xg = o.x_gap;
   tr.q = o.x_sched;
   tr.q_open = o.x_gap && o.x_sched > b.t;                                // x at or before the fill bar: exit at the next bar
   tr.q_x0 = tr.q_open;
   tr.hold = CR_PH_NONE;
   if(o.xh > 0 && o.x_sched > b.t) tr.hold = CR_PH_DUE;                   // x at or before the fill bar: never at the clock
   tr.held = false;
   tr.reason = CR_R_NONE;
   tr.xbar = 0;
   tr.xpx = 0.0;
   PapEmit(CR_EV_PFILL, sl, o.oid, side, b.t, b.t, fp, st, st, CR_R_NONE, o.x_sched, b.s_raw, spread);
   if(wrong)
     {
      double ss = PapSlipS(sl);
      double px = (side > 0) ? b.bo * (1 - ss) : b.ao * (1 + ss);
      PapBookExit(sl, tr, b, px, CR_R_GAP);
      return;
     }
   PapManage(sl, tr, b, true);
  }

//+------------------------------------------------------------------+
//| Hold extension and late gap revision                             |
//+------------------------------------------------------------------+
// variants.hold_decision: ahead by at least xh_r x the initial risk at the close of bar c, c at or after the fill bar
bool PapHoldPass(const CrPapTrade &tr, const CrBar &c)
  {
   if(c.t == 0 || c.t < tr.fill) return false;
   double mark = (tr.side > 0) ? c.bc : c.ac;
   return tr.side * (mark - tr.fp) >= tr.o.xh_r * MathAbs(tr.fp - tr.st0);
  }

void PapEmitHold(const int sl, const CrPapTrade &tr, const datetime M, const CrBar &c, const bool grant)
  {
   double mark = 0.0;
   if(grant) mark = (tr.side > 0) ? c.bc : c.ac;
   PapEmit(CR_EV_HOLD, sl, tr.o.oid, tr.side, M, c.t, mark, tr.cur, tr.st0, CR_R_NONE, tr.x, c.s_raw, c.ao - c.bo);
  }

// the test passed (variants.H: exit_i = max(ext, exit_i))
void PapHoldGrant(const int sl, CrPapTrade &tr, const datetime M, const CrBar &c)
  {
   tr.held = true;
   tr.x = tr.x0;
   if(tr.o.xh > tr.x0) tr.x = tr.o.xh;
   PapEmitHold(sl, tr, M, c, true);
  }

// the first barrier at or after x0, the trade open: the test on its last processed bar, which is the last kept bar
// before x0 (final unless the gap rule moves x0's exit bar back to that bar: then the revision tests again)
void PapHoldAtBarrier(const int sl, CrPapTrade &tr, const datetime M)
  {
   tr.hold = CR_PH_DONE;
   if(tr.q_open && tr.q_x0) tr.hold = CR_PH_TENT;
   if(PapHoldPass(tr, tr.b_last)) PapHoldGrant(sl, tr, M, tr.b_last);
  }

// the barrier passed q + 30 min and no kept bar started at or after q: the trade's last processed bar L is the last
// kept bar before q, and gl.exit_index puts the exit there
void PapRevise(const int sl, CrPapTrade &tr, const datetime M)
  {
   bool x0q = tr.q_x0;
   tr.q_open = false;
   tr.q_x0 = false;
   bool lfill = (tr.b_last.t == tr.fill);
   if(x0q && tr.o.void_le && tr.b_last.t == tr.act)
     {
      PapEmitTr(CR_EV_PVOID, sl, tr, tr.act, tr.b_last, tr.fp, CR_R_VOID);   // the wrapper drops the order: no trade at all
      g_pap_lx[sl] = g_pap_lx0[sl];
      tr.st = CR_PT_NONE;
      return;
     }
   if(x0q && (tr.hold == CR_PH_DUE || tr.hold == CR_PH_TENT))
     {
      tr.hold = CR_PH_DONE;
      if(!lfill && PapHoldPass(tr, tr.b_prev))                // the lab's c = (exit bar L) - 1 = the bar before L
        {
         if(!tr.held) PapHoldGrant(sl, tr, M, tr.b_prev);
         if(tr.x > tr.x0)                                      // the exit moved past the hole: L stays a bar of the trade
           {
            if(tr.xg)
              {
               tr.q = tr.x;                                    // the extended exit has its own question (x > x0 > L)
               tr.q_open = true;
              }
            return;
           }
        }
      else if(tr.held)
        {
         tr.held = false;                                      // withdrawn: the exit bar is L (or the bar after the fill)
         tr.x = tr.x0;
         PapEmitHold(sl, tr, M, tr.b_last, false);
        }
     }
   if(lfill)
     {
      if(tr.st == CR_PT_EXITED) tr.st = CR_PT_NONE;             // its exit on the fill bar stands
      return;                                                  // an open trade exits at the next kept bar (sim.py:137)
     }
   double sm = PapSlipM(sl);
   double px = (tr.side > 0) ? tr.b_last.bo * (1 - sm) : tr.b_last.ao * (1 + sm);
   tr.cur = tr.cur_prev;
   tr.reason = CR_R_TIME;
   tr.xbar = tr.b_last.t;
   tr.xpx = px;
   g_pap_lx[sl] = tr.b_last.t;
   PapEmitTr(CR_EV_PREVISE, sl, tr, tr.b_last.t, tr.b_last, px, CR_R_TIME);
   tr.st = CR_PT_NONE;
  }

// a new kept bar b for the sleeve: an exit booked on the previous bar stands, and an open question is answered
void PapTradeNewBar(CrPapTrade &tr, const CrBar &b)
  {
   if(tr.st == CR_PT_EXITED)
     {
      tr.st = CR_PT_NONE;
      return;
     }
   if(tr.st != CR_PT_OPEN || !tr.q_open || b.t < tr.q) return;
   tr.q_open = false;                                         // a kept bar starts in [q, q + 30 min]: q's exit bar is b
   if(!tr.q_x0) return;
   tr.q_x0 = false;
   if(tr.hold == CR_PH_TENT) tr.hold = CR_PH_DONE;            // the decision of the barrier at x0 stands
   if(tr.held && tr.xg && tr.x > b.t)
     {
      tr.q = tr.x;
      tr.q_open = true;
     }
  }

//+------------------------------------------------------------------+
//| Rule exits and orders on a bar                                   |
//+------------------------------------------------------------------+
// a rule exit resolves on the first kept bar inside its window: oid's time exit becomes "this bar, no gap rule"
void PapExitsOnBar(const int sl, const CrBar &b)
  {
   int base = sl * CR_PAP_XMAX;
   for(int k = 0; k < g_pap_xn[sl]; k++)
     {
      if(g_pap_x[base + k].st != CR_PX_WAIT) continue;
      if(b.t < g_pap_x[base + k].e.t_from || b.t > g_pap_x[base + k].e.t_to) continue;
      g_pap_x[base + k].st = CR_PX_DONE;
      g_pap_x[base + k].bar = b.t;
      long oid = g_pap_x[base + k].e.oid;
      if(g_pap_t[sl].st == CR_PT_OPEN && g_pap_t[sl].o.oid == oid)
        {
         g_pap_t[sl].x = b.t;
         g_pap_t[sl].xg = false;
         g_pap_t[sl].q_open = false;
         g_pap_t[sl].q_x0 = false;
         g_pap_t[sl].hold = CR_PH_NONE;
         g_pap_t[sl].held = false;
        }
      for(int j = 0; j < g_pap_qn[sl]; j++)
         if(g_pap_q[sl * CR_PAP_QMAX + j].o.oid == oid)
           {
            g_pap_q[sl * CR_PAP_QMAX + j].o.x_sched = b.t;
            g_pap_q[sl * CR_PAP_QMAX + j].o.x_gap = false;
            g_pap_q[sl * CR_PAP_QMAX + j].o.xh = 0;
           }
     }
  }

// does the waiting order o activate on bar b?
bool PapActivates(const int sl, const CrOrder &o, const CrBar &b)
  {
   if(b.t < o.t_from || b.t > o.t_to) return false;
   if(o.after_exit_of == 0) return true;
   int k = PapExitFind(sl, o.after_exit_of);
   if(k < 0) return false;
   return g_pap_x[k].st == CR_PX_DONE && g_pap_x[k].bar < b.t;
  }

// the sleeve's queue on bar b, in emission order: armed orders try to fill, waiting orders activate
void PapOrdersOnBar(const int sl, const CrBar &b)
  {
   int base = sl * CR_PAP_QMAX;
   int n = g_pap_qn[sl];
   for(int k = 0; k < n; k++)
     {
      int i = base + k;
      if(g_pap_q[i].st == CR_PO_WAIT)
        {
         if(!PapActivates(sl, g_pap_q[i].o, b)) continue;
         if(g_pap_q[i].o.void_le && g_pap_q[i].o.x_sched > 0 && g_pap_q[i].o.x_sched <= b.t)
           {
            PapEmit(CR_EV_PVOID, sl, g_pap_q[i].o.oid, g_pap_q[i].o.side, b.t, b.t, 0.0, 0.0, 0.0, CR_R_VOID, g_pap_q[i].o.x_sched,
                    b.s_raw, b.ao - b.bo);
            g_pap_q[i].st = 0;                                 // the wrapper drops it: it skips nothing and blocks nothing
            continue;
           }
         bool busy = (g_pap_t[sl].st == CR_PT_OPEN) || (g_pap_lx[sl] != 0 && g_pap_lx[sl] == b.t);   // sim.py:80
         if(busy)
           {
            g_pap_q[i].st = 0;
            continue;
           }
         g_pap_q[i].act = b.t;
         if(g_pap_q[i].o.etype != CR_ET_MARKET)
           {
            g_pap_q[i].st = CR_PO_ARMED;
            if(b.t >= g_pap_q[i].o.expiry_excl)
              {
               g_pap_q[i].st = 0;                              // no bar of its window may fill it (sim.py 'nofill')
               continue;
              }
           }
        }
      else if(g_pap_q[i].st == CR_PO_ARMED)
        {
         if(b.t >= g_pap_q[i].o.expiry_excl)
           {
            g_pap_q[i].st = 0;
            continue;
           }
         if(g_pap_t[sl].st == CR_PT_OPEN) continue;            // (cannot happen: PapSubmit refuses overlaps)
        }
      else continue;
      int side = 0, et = 0;
      double fp = 0.0, lv = 0.0;
      if(!PapTryFill(sl, g_pap_q[i].o, b, side, fp, et, lv)) continue;
      CrOrder o;
      o = g_pap_q[i].o;
      datetime act = g_pap_q[i].act;
      g_pap_q[i].st = 0;
      PapOpen(sl, g_pap_t[sl], o, act, b, side, fp, et, lv);
     }
   PapOrdersCompact(sl);
  }

//+------------------------------------------------------------------+
//| Barrier                                                          |
//+------------------------------------------------------------------+
void PapOrdersOnBarrier(const int sl, const datetime M)
  {
   int base = sl * CR_PAP_QMAX;
   for(int k = 0; k < g_pap_qn[sl]; k++)
     {
      int i = base + k;
      if(g_pap_q[i].st == CR_PO_WAIT)
        {
         if(g_pap_q[i].o.t_to < M)
           {
            g_pap_q[i].st = 0;                                 // its window ended without an activation
            continue;
           }
         if(g_pap_q[i].o.after_exit_of != 0)
           {
            int x = PapExitFind(sl, g_pap_q[i].o.after_exit_of);
            if(x >= 0 && g_pap_x[x].st == CR_PX_VOID) g_pap_q[i].st = 0;   // void with its exit
           }
        }
      else if(g_pap_q[i].st == CR_PO_ARMED)
        {
         // void_le: no kept bar after the activation bar up to x + 30 min -> the exit bar is the activation bar. That is
         // known at the first barrier after x + 30 min, unless the order expired at an earlier barrier: the two are taken
         // in the order of their own barriers, so PapOnBar's barrier, which may see both at once, decides as the minutes do
         if(g_pap_q[i].o.void_le && g_pap_q[i].o.x_gap && g_pap_q[i].o.x_sched > g_pap_q[i].act && M > g_pap_q[i].o.x_sched + CR_PAP_GAP
            && g_pap_last[sl] == g_pap_q[i].act && PapMinAfter(g_pap_q[i].o.x_sched + CR_PAP_GAP) < PapMinFrom(g_pap_q[i].o.expiry_excl))
           {
            PapEmit(CR_EV_PVOID, sl, g_pap_q[i].o.oid, g_pap_q[i].o.side, g_pap_q[i].act, g_pap_q[i].act, 0.0, 0.0, 0.0, CR_R_VOID,
                    g_pap_q[i].o.x_sched, 0, 0.0);
            g_pap_q[i].st = 0;
            continue;
           }
         if(g_pap_q[i].o.expiry_excl <= M) g_pap_q[i].st = 0;  // no fill (sim.py 'nofill')
        }
     }
   PapOrdersCompact(sl);
  }

void PapExitsOnBarrier(const int sl, const datetime M)
  {
   int base = sl * CR_PAP_XMAX;
   for(int k = 0; k < g_pap_xn[sl]; k++)
      if(g_pap_x[base + k].st == CR_PX_WAIT && g_pap_x[base + k].e.t_to < M) g_pap_x[base + k].st = CR_PX_VOID;
  }

// the sleeve's part of barrier M: every bar of its symbol starting before M has been fed
void PapSleeveBarrier(const int sl, const datetime M)
  {
   PapExitsOnBarrier(sl, M);
   PapOrdersOnBarrier(sl, M);
   PapExitsCompact(sl);
   if(g_pap_t[sl].st == CR_PT_OPEN && g_pap_t[sl].hold == CR_PH_DUE && M >= g_pap_t[sl].x0) PapHoldAtBarrier(sl, g_pap_t[sl], M);
   for(int guard = 0; guard < 4; guard++)                    // x0's question, then the extended exit's
     {
      if(g_pap_t[sl].st == CR_PT_NONE || !g_pap_t[sl].q_open || M <= g_pap_t[sl].q + CR_PAP_GAP) break;
      PapRevise(sl, g_pap_t[sl], M);
     }
  }

//+------------------------------------------------------------------+
//| API                                                              |
//+------------------------------------------------------------------+
void PapReset()
  {
   for(int i = 0; i < CR_PAP_QALL; i++) ZeroMemory(g_pap_q[i]);
   for(int i = 0; i < CR_PAP_XALL; i++) ZeroMemory(g_pap_x[i]);
   for(int sl = 0; sl < CR_MAX_SL; sl++)
     {
      g_pap_qn[sl] = 0;
      g_pap_xn[sl] = 0;
      ZeroMemory(g_pap_t[sl]);
      g_pap_t[sl].st = CR_PT_NONE;
      g_pap_t[sl].reason = CR_R_NONE;
      g_pap_lx[sl] = 0;
      g_pap_lx0[sl] = 0;
      g_pap_last[sl] = 0;
     }
   g_pap_M = 0;
   g_pap_evn = 0;
  }

void PapInit()
  {
   ArrayResize(g_pap_ev, 0, 256);
   g_pap_err = 0;
   PapReset();
  }

bool PapSubmit(const CrOrder &o)
  {
   int sl = o.sleeve;
   bool ok = PapSleeveOk(sl);
   if(ok) ok = (o.etype >= CR_ET_MARKET && o.etype <= CR_ET_OCO);
   if(ok && o.etype != CR_ET_OCO) ok = (o.side == 1 || o.side == -1);
   if(ok) ok = PapOn(o.stop) || PapOn(o.stop_dist);              // every trade needs a stop (sim.py:256)
   if(ok) ok = (g_pap_qn[sl] < CR_PAP_QMAX);
   if(ok)
      for(int k = 0; k < g_pap_qn[sl]; k++)
         if(PapOverlap(g_pap_q[sl * CR_PAP_QMAX + k], o))
           {
            ok = false;
            break;
           }
   if(!ok)
     {
      g_pap_err++;
      return false;
     }
   int i = sl * CR_PAP_QMAX + g_pap_qn[sl];
   g_pap_q[i].o = o;
   g_pap_q[i].st = CR_PO_WAIT;
   g_pap_q[i].act = 0;
   g_pap_qn[sl]++;
   return true;
  }

bool PapSubmitExit(const CrExit &e)
  {
   int sl = e.sleeve;
   if(!PapSleeveOk(sl))
     {
      g_pap_err++;
      return false;
     }
   if(g_pap_xn[sl] >= CR_PAP_XMAX) PapExitsCompact(sl);
   if(g_pap_xn[sl] >= CR_PAP_XMAX)
     {
      g_pap_err++;
      return false;
     }
   int i = sl * CR_PAP_XMAX + g_pap_xn[sl];
   g_pap_x[i].e = e;
   g_pap_x[i].st = CR_PX_WAIT;
   g_pap_x[i].bar = 0;
   g_pap_xn[sl]++;
   return true;
  }

void PapOnBar(const int sl, const CrBar &b)
  {
   if(!PapSleeveOk(sl)) return;
   if(b.sym != g_sl[sl].sym || b.t <= g_pap_last[sl]) return;
   PapSleeveBarrier(sl, b.t);                                   // (a no-op after PapOnBarrier(b.t))
   PapExitsOnBar(sl, b);                                        // (0) rule exits resolve on their first kept bar
   PapTradeNewBar(g_pap_t[sl], b);                              // (0') a new bar settles an exited trade and a question
   if(g_pap_t[sl].st == CR_PT_OPEN) PapManage(sl, g_pap_t[sl], b, false);   // (1) the open trade
   PapOrdersOnBar(sl, b);                                       // (2) armed orders, then activations
   g_pap_last[sl] = b.t;
  }

void PapOnBarrier(const datetime M)
  {
   if(M > g_pap_M) g_pap_M = M;
   for(int sl = 0; sl < g_nsl; sl++)
     {
      if(!PapSleeveOk(sl)) break;
      PapSleeveBarrier(sl, M);
     }
  }

int PapEvents() { return g_pap_evn; }

bool PapEvent(const int k, CrPEvent &e)
  {
   if(k < 0 || k >= g_pap_evn) return false;
   e = g_pap_ev[k];
   return true;
  }

void PapClearEvents() { g_pap_evn = 0; }

bool PapTrade(const int sl, CrTrade &t)
  {
   if(!PapSleeveOk(sl)) return false;
   if(g_pap_t[sl].st != CR_PT_OPEN) return false;
   t.sleeve = sl;
   t.oid = g_pap_t[sl].o.oid;
   t.side = g_pap_t[sl].side;
   t.etype = g_pap_t[sl].o.etype;
   t.act_bar = g_pap_t[sl].act;
   t.fill_bar = g_pap_t[sl].fill;
   t.fill_px = g_pap_t[sl].fp;
   t.init_stop = g_pap_t[sl].st0;
   t.stop = g_pap_t[sl].cur;
   t.moved = g_pap_t[sl].moved;
   t.x_sched = g_pap_t[sl].x;
   t.x_gap = g_pap_t[sl].xg;
   t.x_pending = (g_pap_t[sl].x > 0 && g_pap_M >= g_pap_t[sl].x);
   t.dec = g_pap_t[sl].o.dec;
   t.group = g_pap_t[sl].o.group;
   return true;
  }

bool PapPending(const int sl, CrOrder &o)
  {
   if(!PapSleeveOk(sl)) return false;
   if(g_pap_qn[sl] <= 0) return false;
   o = g_pap_q[sl * CR_PAP_QMAX].o;
   return true;
  }

datetime PapLastExitBar(const int sl)
  {
   if(sl < 0 || sl >= CR_MAX_SL) return 0;
   return g_pap_lx[sl];
  }
#endif

// ==== end src/CR_Paper.mqh
// ==== begin src/CR_Ledger.mqh
//+------------------------------------------------------------------+
//| CR_Ledger.mqh - the account ledger from the deal history (SPEC 5) |
//| and the history latches of SPEC 6 (STOP, GUARD b and c, daily     |
//| lock). Owner: I.                                                  |
//|                                                                  |
//| No state survives a restart: every read rebuilds the ledger from |
//| HistorySelect(0, TimeTradeServer() + 86400) and ACCOUNT_BALANCE. |
//| Deals never change once made, so a read parses only the deals    |
//| added since the last read; the cache is dropped when the history |
//| list is not the one already read, and at every rebuild.          |
//|                                                                  |
//| Plan start T (server clock, SPEC 5, R3):                          |
//|   InpPlanStart > 0      T; a T still to come is PLAN_FUTURE       |
//|   0, demo or contest    T = the first deal of the history (push)  |
//|   0, real account       PLAN_UNSET: OBSERVE, no latch at all      |
//|   B(T) = ACCOUNT_BALANCE - money of the deals at or after T,      |
//|   money = profit + swap + commission + fee, credit deals left out |
//|   (ClaudeMains.mq5:586), rounded to the cent. B(T) counts as one  |
//|   opening payment at T: no history before T is needed.            |
//|                                                                  |
//| Events after T (UTC seconds), in the lab's order (growth.py:182): |
//|   PAY    a DEAL_TYPE_BALANCE deal (amount in its money), at its   |
//|          deal time                                                |
//|   OTHER  money that is neither a payment nor a robot close:       |
//|          manual and hands' trades, the guard's mark, charges,     |
//|          corrections; at its deal time; in B, never in w          |
//|   CLOSE  one per closed robot position (opening deal magic        |
//|          20261201-20261289; deals attach by DEAL_POSITION_ID, so  |
//|          a broker stop deal with magic 0 counts): money = all its |
//|          deals at or after T, stamped like the lab (sim.py:283-   |
//|          284): closing deal by SL, TP or SO in minute X ->        |
//|          X + 60 s, any other close -> X                           |
//|   Sorted by time; at one time PAY, then OTHER, then CLOSE (by     |
//|   position id, which is the opening order). Known at a stamp S:   |
//|   PAY and OTHER at or before S, CLOSE before S (growth.py:189-    |
//|   215: a result booked in the minute of an entry is not known to  |
//|   it). That set is a prefix of the sorted list (LedKnown).        |
//|                                                                  |
//| Walk from B = P_in = ref = B(T) (growth.py:162-253):              |
//|   deposit A > 0      B += A; P_in += A; ref = max(ref + A, B)     |
//|   withdrawal A < 0   B += A; ref = ref x B_after / B_before:      |
//|                      neither B/ref nor the rung moves (R1); P_in  |
//|                      never falls, so the stop never disarms       |
//|   OTHER M            B += M                                       |
//|   CLOSE M            B += M; plan stop (SPEC 6.1): P_in >= arm    |
//|                      and B <= ref x (1 - fall / 100) -> STOP      |
//|   after any event    GUARD (b): ref > 0 and B <= 50 % of ref      |
//|   GUARD (c)          a deal of magic 20261290 at or after T       |
//|   CR_NO_GUARD (T7 harness builds only): GUARD never latches.      |
//|   A later InpPlanStart clears STOP and GUARD: only events after T |
//|   are walked.                                                     |
//|                                                                  |
//| Settle (SPEC 5, R16, Capital's rule ClaudeMains.mq5:596-603):     |
//|   B(T) is accepted once two reads at least 2 s apart agree. A     |
//|   read whose B(T) differs from the accepted value (a deal and the |
//|   balance out of step) is MOVING: nothing is sized and no STOP,   |
//|   GUARD or LOCK is concluded until B(T) is back (to the accepted  |
//|   value or the one accepted before it), or until it has differed  |
//|   for 60 s: then the latest value is accepted and pushed. At the  |
//|   start the same 60 s run from the first read. The walk always    |
//|   starts from the accepted B(T).                                  |
//|                                                                  |
//| Week unit (SPEC 5, growth.py:228-275): set at the week's first    |
//|   ledger event, a robot close or a sizing request (SizWeekUnit in |
//|   CR_Sizing computes it; the follower calls SizWeekUnit for a     |
//|   MISSED reason=exited intent). R = that event's time; unit =     |
//|   rate(max(B(R), P_in(R)))% x B(R). w(S) = (B(S) - base) / unit   |
//|   with base = B(R) plus the payments and other money known at S   |
//|   but not at R, added in order: the robot close money of the      |
//|   week before S, as the lab computes it (eq - wk_base).           |
//|                                                                  |
//| Daily lock (SPEC 6.3): with X = InpDailyLockStakes > 0, locked    |
//|   when the robot close money stamped in the server day reaches    |
//|   -X x rate(max(B_d, P_d)) / 100 x B_d, B_d and P_d at the start  |
//|   of the server day. Booked money only: rebuilt from the history. |
//|   A LOCK is concluded only on a settled ledger; once concluded it |
//|   holds for the rest of that server day, also while B(T) moves.   |
//|                                                                  |
//| Journal: SETTLE (state=moving, ok, accepted), PLAN (demo plan     |
//|   from the first deal, with a push), and one STOP and one GUARD   |
//|   line (src=history...) when the history shows the latch on a     |
//|   settled ledger. The guards (CR_Guards) act on the latches and   |
//|   push; the ledger itself closes nothing.                         |
//|                                                                  |
//| API (signatures of the S0 stub kept; the rest is new):            |
//|   LedInit(err)              once at OnInit (after SizInit)        |
//|   LedReset()                rebuild: deals re-read, week units    |
//|                             forgotten (settle state kept)         |
//|   LedRead(now_srv)          CR_LED_OK (settled) or CR_LED_MOVING  |
//|   LedSettled()              B(T) accepted and not moving          |
//|   LedOnTransaction()        OnTradeTransaction: read again soon   |
//|   LedOnTimer(now_srv)       a read once a minute, after a         |
//|                             transaction, every second while       |
//|                             unsettled                             |
//|   LedPlan(now_srv)          CR_PLAN_OK / UNSET / FUTURE           |
//|   LedPlanAt(S)              the plan state at stamp S (UTC)       |
//|   LedPlanStart()            T (server time), 0 = unset or the     |
//|                             start of the history                  |
//|   LedBT()                   B(T) the walk starts from             |
//|   LedBalance(S) LedPaidIn(S) LedRef(S)   at stamp S (UTC)         |
//|   LedCloseMoney(S)          robot close money stamped before S    |
//|   LedBalanceNow() LedPaidInNow() LedRefNow()   after every event  |
//|                             read so far (GUARD (a): equity <= 50 %|
//|                             of LedRefNow on a settled ledger)     |
//|   LedStopLatched() LedStopTime() LedStoppedAt(S)       STOP       |
//|   LedGuardLatched() LedGuardAt(S) LedMarkSeen()        GUARD      |
//|   LedDayLocked(now_srv) LedDayLockedAt(S)              LOCK       |
//|   LedWeekUnit(S) LedSetWeekUnit(S, unit) LedWeekRoll(S) LedWeekW(S)|
//|   LedPosCount() LedPosAt(k, p)   the positions of the history     |
//|   LedSetRates(from, pct, n) LedRate(key)   the risk table (SizInit)|
//|   LedCommission(day, usd_oz, n)  gold commission of a server day  |
//| Every stamp S is a UTC time; now_srv is TimeTradeServer().        |
//+------------------------------------------------------------------+
#ifndef CR_LEDGER_MQH
#define CR_LEDGER_MQH
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Clock.mqh)
// (already inlined: CR_Journal.mqh)

#define CR_LED_TOL 0.005                // two B(T) values closer than half a cent are the same
#define CR_LED_SETTLE_GAP 2             // two reads at least 2 s apart must agree (SPEC 5)
#define CR_LED_SETTLE_MAX 60            // a B(T) that differs for 60 s is accepted (SPEC 5; Capital's SETTLE_SEC)
#define CR_LED_READ_EVERY 60            // a read once a minute and after each transaction (SPEC 5)
#define CR_LED_GUARD_SHARE 0.5          // GUARD (b): B at or below 50 % of ref (SPEC 6.2)
#define CR_LED_KEY_SHIFT 23             // sort key = (time << 23) | (kind << 21) | index
#define CR_LED_KIND_SHIFT 21
#define CR_LED_MAX_EV 2097151           // events of one ledger at most (21 bits)
#define CR_LED_MAX_WEEKS 16             // week units kept (the current week, and a few for late intents)
#define CR_EK_PAY 0                     // event kinds, in their order at one time
#define CR_EK_OTHER 1
#define CR_EK_CLOSE 2
#define CR_MAGIC_ROBOT_LO 20261201      // sleeve positions of this robot (SPEC 2.3, 4.7)
#define CR_MAGIC_ROBOT_HI 20261289

// one deal of the history (MT5 never changes a deal once made)
struct CrLedDeal
  {
   ulong    ticket;
   datetime t_srv;                     // DEAL_TIME (server clock)
   int      type;                      // DEAL_TYPE_*
   int      entry;                     // DEAL_ENTRY_*
   long     magic;
   long     pos;                       // DEAL_POSITION_ID (0 = none)
   int      reason;                    // DEAL_REASON_*
   double   volume;
   double   price;
   double   money;                     // profit + swap + commission + fee
   double   comm;                      // commission alone (the COST line)
   int      sym;                       // symbol id, -1 = another symbol
  };

// one position of the history (its deals attach by DEAL_POSITION_ID)
struct CrLedPos
  {
   long     id;                        // position identifier (the opening order's ticket)
   long     magic;                     // magic of its opening deal (no opening deal: the first sleeve magic seen)
   bool     robot;                     // a sleeve position of this robot
   int      sym;                       // symbol id, -1 = another symbol
   int      side;                      // +1 buy, -1 sell, 0 = no opening deal in the history
   datetime t_in;                      // opening deal, UTC (0 = not in the history)
   double   vol_in;
   double   px_in;
   double   vol_out;
   bool     closed;
   datetime t_out_srv;                 // last closing deal, server clock
   int      reason_out;                // its DEAL_REASON
   datetime stamp;                     // close stamp, UTC (lab convention); 0 while open
   double   money;                     // money of its deals at or after T
  };

// one ledger event after T and the state right after it
struct CrLedEv
  {
   datetime t;                         // UTC: deal time (PAY, OTHER) or close stamp (CLOSE)
   int      kind;                      // CR_EK_*
   double   amount;
   int      pos;                       // position row (CLOSE), -1 otherwise
   double   eq;                        // B after the event
   double   paid;                      // P_in after the event
   double   ref;                       // ref after the event
   double   cm;                        // robot close money since T, after the event
  };

CrLedDeal g_led_d[];                   // the deal cache, in the history list order
int       g_led_nd = 0;
datetime  g_led_first_srv = 0;         // earliest deal time of the cache (0 = no deal)
CrLedPos  g_led_p[];                   // positions, by increasing id
long      g_led_pid[];                 // their ids
int       g_led_np = 0;
CrLedEv   g_led_e[];                   // events after T, sorted
long      g_led_key[];                 // their sort keys, increasing
int       g_led_ne = 0;
bool      g_led_tables = false;        // positions and events match the cache and T
datetime  g_led_T_built = 0;           // T of the tables (meaningful while g_led_tables is true)
datetime  g_led_T = 0;                 // plan start in use (server clock), 0 = the start of the history
datetime  g_led_T_utc = 0;
int       g_led_plan = CR_PLAN_UNSET;
double    g_led_bt = 0.0;              // B(T) of the walk (the accepted value)
double    g_led_bt_read = 0.0;         // B(T) of the last read
bool      g_led_walked = false;
long      g_led_mark_key = -1;         // GUARD (c): first deal of magic 20261290 at or after T (key of an OTHER event)
long      g_led_stop_key = -1;         // STOP: key of the close event that latched it
int       g_led_stop_ev = -1;
long      g_led_guard_key = -1;        // GUARD (b): key of the event that latched it
int       g_led_guard_ev = -1;
bool      g_led_rep_stop = false;      // STOP concluded on a settled ledger (kept until LedInit)
bool      g_led_rep_guard = false;
bool      g_led_said_plan = false;
datetime  g_led_lock_day = 0;          // server day of a LOCK concluded on a settled ledger (0 = none)
// settle (SPEC 5)
bool      g_led_acc = false;           // a B(T) has been accepted
double    g_led_acc_v = 0.0;
bool      g_led_has_prev = false;      // the value accepted before the current one
double    g_led_acc_prev = 0.0;
bool      g_led_has_cand = false;      // before the first acceptance: the first read of a run of equal reads
double    g_led_cand_v = 0.0;
datetime  g_led_cand_t = 0;
datetime  g_led_move_t = 0;            // first read of the current movement (0 = none)
bool      g_led_settled = false;
datetime  g_led_last_read = 0;
bool      g_led_dirty = true;
long      g_led_reads = 0;
// the week units (the first sizing or close of each week)
datetime  g_led_wk0[];                 // week start: UTC instant of the server Monday 00:00
double    g_led_wku[];
datetime  g_led_wkr[];                 // the week's first event (R)
int       g_led_nwk = 0;
// the risk table, for the daily lock (a copy of SizInit's table)
double    g_led_rf[];
double    g_led_rp[];
int       g_led_rn = 0;

bool LedRobotMagic(const long m) { return m >= CR_MAGIC_ROBOT_LO && m <= CR_MAGIC_ROBOT_HI; }

int LedSymId(const string name)
  {
   if(name == "") return -1;
   for(int s = 0; s < CR_NSYM; s++)
      if(g_sym[s].name != "" && g_sym[s].name == name) return s;
   return -1;
  }

// the risk table (SPEC 1 InpRiskTable): pct of the last pair with from <= key (growth.py:93-98)
void LedSetRates(const double &from[], const double &pct[], const int n)
  {
   g_led_rn = 0;
   if(n <= 0) return;
   ArrayResize(g_led_rf, n);
   ArrayResize(g_led_rp, n);
   for(int k = 0; k < n; k++)
     {
      g_led_rf[k] = from[k];
      g_led_rp[k] = pct[k];
     }
   g_led_rn = n;
  }

double LedRate(const double key)
  {
   if(g_led_rn <= 0) return 0.0;
   double r = g_led_rp[0];
   for(int k = 1; k < g_led_rn; k++)
      if(key >= g_led_rf[k]) r = g_led_rp[k];
   return r;
  }

long LedKey(const datetime t, const int kind)
  {
   long u = (long)t;
   if(u < 0) u = 0;
   return (u << CR_LED_KEY_SHIFT) | ((long)kind << CR_LED_KIND_SHIFT);
  }

// first event whose key is at or above `key`
int LedLower(const long key)
  {
   int lo = 0, hi = g_led_ne;
   while(lo < hi)
     {
      int mid = (lo + hi) / 2;
      if(g_led_key[mid] < key) lo = mid + 1;
      else hi = mid;
     }
   return lo;
  }

// number of events known at stamp S: PAY and OTHER at or before S, CLOSE before S
int LedKnown(const datetime S) { return LedLower(LedKey(S, CR_EK_CLOSE)); }

int LedFindPos(const long id)
  {
   int lo = 0, hi = g_led_np - 1;
   while(lo <= hi)
     {
      int mid = (lo + hi) / 2;
      if(g_led_pid[mid] == id) return mid;
      if(g_led_pid[mid] < id) lo = mid + 1;
      else hi = mid - 1;
     }
   return -1;
  }

// the cache follows HistorySelect's list (called right after it); true when it changed
bool LedLoadDeals()
  {
   int total = HistoryDealsTotal();
   bool same = (total >= g_led_nd);
   for(int i = 0; same && i < g_led_nd; i++)
      if(HistoryDealGetTicket(i) != g_led_d[i].ticket) same = false;
   bool changed = false;
   if(!same)
     {
      g_led_nd = 0;
      g_led_first_srv = 0;
      changed = true;
     }
   if(total > g_led_nd)
     {
      if(ArrayResize(g_led_d, total, 1000) < total) return changed;
      for(int i = g_led_nd; i < total; i++)
        {
         ulong t = HistoryDealGetTicket(i);
         CrLedDeal x;
         x.ticket = t;
         x.t_srv = (datetime)HistoryDealGetInteger(t, DEAL_TIME);
         x.type = (int)HistoryDealGetInteger(t, DEAL_TYPE);
         x.entry = (int)HistoryDealGetInteger(t, DEAL_ENTRY);
         x.magic = HistoryDealGetInteger(t, DEAL_MAGIC);
         x.pos = HistoryDealGetInteger(t, DEAL_POSITION_ID);
         x.reason = (int)HistoryDealGetInteger(t, DEAL_REASON);
         x.volume = HistoryDealGetDouble(t, DEAL_VOLUME);
         x.price = HistoryDealGetDouble(t, DEAL_PRICE);
         x.comm = HistoryDealGetDouble(t, DEAL_COMMISSION);
         x.money = HistoryDealGetDouble(t, DEAL_PROFIT) + HistoryDealGetDouble(t, DEAL_SWAP) + x.comm + HistoryDealGetDouble(t, DEAL_FEE);
         x.sym = LedSymId(HistoryDealGetString(t, DEAL_SYMBOL));
         g_led_d[i] = x;
         if(x.t_srv > 0 && (g_led_first_srv == 0 || x.t_srv < g_led_first_srv)) g_led_first_srv = x.t_srv;
        }
      g_led_nd = total;
      changed = true;
     }
   return changed;
  }

// T and the plan state (SPEC 5)
void LedPlanCompute(const datetime now_srv)
  {
   if(g_cfg.plan_start > 0)
     {
      g_led_T = g_cfg.plan_start;
      g_led_plan = (g_led_T > now_srv) ? CR_PLAN_FUTURE : CR_PLAN_OK;
     }
   else if(g_cfg.demo)
     {
      g_led_T = g_led_first_srv;                  // 0: no deal yet, the plan starts with the history
      g_led_plan = CR_PLAN_OK;
      if(g_led_T > 0 && !g_led_said_plan)
        {
         g_led_said_plan = true;
         Jrn(CR_EV_PLAN, "-", KV("src", "first_deal") + KT("T", g_led_T));
         JrnPush("compte de demo sans InpPlanStart : le plan part de la premiere transaction (" + ClkStr(g_led_T) + ", heure serveur)", false);
        }
     }
   else
     {
      g_led_T = 0;                                // B(T) still settles; nothing is concluded (OBSERVE)
      g_led_plan = CR_PLAN_UNSET;
     }
   g_led_T_utc = (g_led_T > 0) ? ClkServerToUtc(g_led_T) : (datetime)0;
  }

// B(T) = ACCOUNT_BALANCE - money of the deals at or after T, credit deals left out, to the cent
double LedReadBT()
  {
   double s = 0.0;
   for(int i = 0; i < g_led_nd; i++)
      if(g_led_d[i].type != DEAL_TYPE_CREDIT && g_led_d[i].t_srv >= g_led_T) s += g_led_d[i].money;
   return NormalizeDouble(AccountInfoDouble(ACCOUNT_BALANCE) - s, 2);
  }

bool LedTradeDeal(const int type) { return type == DEAL_TYPE_BUY || type == DEAL_TYPE_SELL; }

// close stamp of a position closed by a deal at server time t_srv with that reason (sim.py:283-284)
datetime LedStamp(const datetime t_srv, const int reason)
  {
   datetime u = ClkServerToUtc(t_srv);
   datetime x = u - u % 60;
   if(reason == DEAL_REASON_SL || reason == DEAL_REASON_TP || reason == DEAL_REASON_SO) x += 60;
   return x;
  }

// positions and events from the cache and T
void LedBuild()
  {
   // positions: the ids of the trade deals, sorted, once each
   long ids[];
   int n = 0;
   ArrayResize(ids, g_led_nd > 0 ? g_led_nd : 1);
   for(int i = 0; i < g_led_nd; i++)
      if(LedTradeDeal(g_led_d[i].type) && g_led_d[i].pos > 0)
        {
         ids[n] = g_led_d[i].pos;
         n++;
        }
   ArrayResize(ids, n);
   if(n > 1) ArraySort(ids);
   int u = 0;
   for(int i = 0; i < n; i++)
      if(u == 0 || ids[i] != ids[u - 1])
        {
         ids[u] = ids[i];
         u++;
        }
   ArrayResize(g_led_pid, u > 0 ? u : 1);
   ArrayResize(g_led_p, u > 0 ? u : 1);
   long any_magic[];
   ArrayResize(any_magic, u > 0 ? u : 1);
   for(int k = 0; k < u; k++)
     {
      g_led_pid[k] = ids[k];
      g_led_p[k].id = ids[k];
      g_led_p[k].magic = 0;
      g_led_p[k].robot = false;
      g_led_p[k].sym = -1;
      g_led_p[k].side = 0;
      g_led_p[k].t_in = 0;
      g_led_p[k].vol_in = 0.0;
      g_led_p[k].px_in = 0.0;
      g_led_p[k].vol_out = 0.0;
      g_led_p[k].closed = false;
      g_led_p[k].t_out_srv = 0;
      g_led_p[k].reason_out = -1;
      g_led_p[k].stamp = 0;
      g_led_p[k].money = 0.0;
      any_magic[k] = 0;
     }
   g_led_np = u;
   // attach the trade deals to their positions
   for(int i = 0; i < g_led_nd; i++)
     {
      if(!LedTradeDeal(g_led_d[i].type) || g_led_d[i].pos <= 0) continue;
      int k = LedFindPos(g_led_d[i].pos);
      if(k < 0) continue;
      if(g_led_p[k].sym < 0) g_led_p[k].sym = g_led_d[i].sym;
      if(any_magic[k] == 0 && LedRobotMagic(g_led_d[i].magic)) any_magic[k] = g_led_d[i].magic;
      if(g_led_d[i].entry == DEAL_ENTRY_IN)
        {
         datetime tu = ClkServerToUtc(g_led_d[i].t_srv);
         if(g_led_p[k].side == 0 || tu < g_led_p[k].t_in)
           {
            g_led_p[k].t_in = tu;
            g_led_p[k].px_in = g_led_d[i].price;
            g_led_p[k].side = (g_led_d[i].type == DEAL_TYPE_BUY) ? 1 : -1;
            g_led_p[k].magic = g_led_d[i].magic;
           }
         g_led_p[k].vol_in += g_led_d[i].volume;
        }
      else
        {
         g_led_p[k].vol_out += g_led_d[i].volume;
         if(g_led_d[i].t_srv >= g_led_p[k].t_out_srv)
           {
            g_led_p[k].t_out_srv = g_led_d[i].t_srv;
            g_led_p[k].reason_out = g_led_d[i].reason;
           }
        }
      if(g_led_d[i].t_srv >= g_led_T) g_led_p[k].money += g_led_d[i].money;
     }
   for(int k = 0; k < u; k++)
     {
      if(g_led_p[k].side == 0) g_led_p[k].magic = any_magic[k];
      g_led_p[k].robot = LedRobotMagic(g_led_p[k].magic);
      bool out = (g_led_p[k].t_out_srv > 0);
      g_led_p[k].closed = out && (g_led_p[k].side == 0 || g_led_p[k].vol_out >= g_led_p[k].vol_in - 1e-8);
      if(g_led_p[k].closed) g_led_p[k].stamp = LedStamp(g_led_p[k].t_out_srv, g_led_p[k].reason_out);
     }
   // events after T: payments and other money in list order, then robot closes in id order (their tie orders)
   int ne = 0;
   for(int i = 0; i < g_led_nd; i++)
     {
      if(g_led_d[i].t_srv < g_led_T || g_led_d[i].type == DEAL_TYPE_CREDIT) continue;
      if(LedTradeDeal(g_led_d[i].type))
        {
         int k = (g_led_d[i].pos > 0) ? LedFindPos(g_led_d[i].pos) : -1;
         if(k >= 0 && g_led_p[k].robot) continue;
        }
      ne++;
     }
   for(int k = 0; k < u; k++)
      if(g_led_p[k].robot && g_led_p[k].closed && g_led_p[k].t_out_srv >= g_led_T) ne++;
   if(ne > CR_LED_MAX_EV)
     {
      JrnError("-", "the deal history holds more events than the ledger can sort (" + IntegerToString(ne) + ")");
      ne = CR_LED_MAX_EV;
     }
   CrLedEv tmp[];
   long keys[];
   ArrayResize(tmp, ne > 0 ? ne : 1);
   ArrayResize(keys, ne > 0 ? ne : 1);
   int m = 0;
   g_led_mark_key = -1;
   for(int i = 0; i < g_led_nd && m < ne; i++)
     {
      if(g_led_d[i].t_srv < g_led_T || g_led_d[i].type == DEAL_TYPE_CREDIT) continue;
      datetime tu = ClkServerToUtc(g_led_d[i].t_srv);
      if(g_led_d[i].magic == CR_MAGIC_MARK)
        {
         long mk = LedKey(tu, CR_EK_OTHER);
         if(g_led_mark_key < 0 || mk < g_led_mark_key) g_led_mark_key = mk;
        }
      int kind = CR_EK_OTHER;
      if(g_led_d[i].type == DEAL_TYPE_BALANCE) kind = CR_EK_PAY;
      else if(LedTradeDeal(g_led_d[i].type))
        {
         int k = (g_led_d[i].pos > 0) ? LedFindPos(g_led_d[i].pos) : -1;
         if(k >= 0 && g_led_p[k].robot) continue;
        }
      tmp[m].t = tu;
      tmp[m].kind = kind;
      tmp[m].amount = g_led_d[i].money;
      tmp[m].pos = -1;
      keys[m] = LedKey(tu, kind) | (long)m;
      m++;
     }
   for(int k = 0; k < u && m < ne; k++)
     {
      if(!g_led_p[k].robot || !g_led_p[k].closed || g_led_p[k].t_out_srv < g_led_T) continue;
      tmp[m].t = g_led_p[k].stamp;
      tmp[m].kind = CR_EK_CLOSE;
      tmp[m].amount = g_led_p[k].money;
      tmp[m].pos = k;
      keys[m] = LedKey(g_led_p[k].stamp, CR_EK_CLOSE) | (long)m;
      m++;
     }
   ArrayResize(keys, m);
   if(m > 1) ArraySort(keys);
   ArrayResize(g_led_e, m > 0 ? m : 1);
   ArrayResize(g_led_key, m > 0 ? m : 1);
   long mask = ((long)1 << CR_LED_KIND_SHIFT) - 1;
   for(int j = 0; j < m; j++)
     {
      int src = (int)(keys[j] & mask);
      g_led_e[j] = tmp[src];
      g_led_key[j] = keys[j];
     }
   g_led_ne = m;
   g_led_tables = true;
   g_led_T_built = g_led_T;
   g_led_walked = false;
  }

// the cumulative state after each event and the history latches (growth.py:189-253)
void LedWalk()
  {
   double eq = g_led_bt, paid = g_led_bt, ref = g_led_bt, cm = 0.0;
   double keep = 1.0 - g_cfg.stop_fall_pct / 100.0;
   bool latch = (g_led_plan != CR_PLAN_UNSET);
   g_led_stop_key = -1;
   g_led_stop_ev = -1;
   g_led_guard_key = -1;
   g_led_guard_ev = -1;
   for(int k = 0; k < g_led_ne; k++)
     {
      double a = g_led_e[k].amount;
      int kind = g_led_e[k].kind;
      if(kind == CR_EK_PAY)
        {
         double before = eq;
         eq = eq + a;
         if(a > 0.0)
           {
            paid = paid + a;
            ref = MathMax(ref + a, eq);
           }
         else if(a < 0.0 && before > 0.0) ref = ref * eq / before;
        }
      else if(kind == CR_EK_OTHER) eq = eq + a;
      else
        {
         eq = eq + a;
         cm = cm + a;
         if(latch && g_led_stop_key < 0 && paid >= g_cfg.stop_arm_paid && eq <= ref * keep)
           {
            g_led_stop_key = g_led_key[k];
            g_led_stop_ev = k;
           }
        }
#ifndef CR_NO_GUARD
      if(latch && g_led_guard_key < 0 && ref > 0.0 && eq <= CR_LED_GUARD_SHARE * ref)
        {
         g_led_guard_key = g_led_key[k];
         g_led_guard_ev = k;
        }
#endif
      g_led_e[k].eq = eq;
      g_led_e[k].paid = paid;
      g_led_e[k].ref = ref;
      g_led_e[k].cm = cm;
     }
   g_led_walked = true;
  }

void LedSettleLine(const string state, const double v)
  {
   Jrn(CR_EV_SETTLE, "-", KV("state", state) + KD("B_T", v) + KD("accepted", g_led_acc_v) + KT("T", g_led_T));
  }

// the 60-s rule: the latest B(T) is accepted, journaled and pushed
void LedSettleAccept(const double v)
  {
   if(g_led_acc)
     {
      g_led_acc_prev = g_led_acc_v;
      g_led_has_prev = true;
     }
   g_led_acc = true;
   g_led_acc_v = v;
   g_led_settled = true;
   g_led_move_t = 0;
   LedSettleLine("accepted", v);
   JrnPush("solde et historique en desaccord depuis 60 s : nouveau solde de depart du plan accepte (" + DoubleToString(v, 2) + ")", false);
  }

// the settle rule (SPEC 5, R16) on the B(T) of one read
void LedSettle(const double v, const datetime now)
  {
   if(!g_led_acc)
     {
      // the start: two equal reads at least 2 s apart; a B(T) that still moves 60 s after the first read is accepted
      if(g_led_move_t == 0 || now < g_led_move_t) g_led_move_t = now;
      bool same = g_led_has_cand && MathAbs(v - g_led_cand_v) <= CR_LED_TOL;
      if(!same)
        {
         g_led_has_cand = true;
         g_led_cand_v = v;
         g_led_cand_t = now;
        }
      if(same && now - g_led_cand_t >= CR_LED_SETTLE_GAP)
        {
         g_led_acc = true;
         g_led_acc_v = v;
         g_led_has_prev = false;
         g_led_settled = true;
         g_led_move_t = 0;
        }
      else if(now - g_led_move_t >= CR_LED_SETTLE_MAX) LedSettleAccept(v);
      else g_led_settled = false;
      return;
     }
   bool cur = MathAbs(v - g_led_acc_v) <= CR_LED_TOL;
   bool back = !cur && g_led_has_prev && MathAbs(v - g_led_acc_prev) <= CR_LED_TOL;
   if(cur || back)
     {
      if(back)
        {
         double x = g_led_acc_v;
         g_led_acc_v = g_led_acc_prev;
         g_led_acc_prev = x;
        }
      if(!g_led_settled) LedSettleLine("ok", v);
      g_led_settled = true;
      g_led_move_t = 0;
      return;
     }
   if(g_led_move_t == 0 || now < g_led_move_t)
     {
      g_led_move_t = now;
      LedSettleLine("moving", v);
     }
   g_led_settled = false;
   if(now - g_led_move_t >= CR_LED_SETTLE_MAX) LedSettleAccept(v);
  }

// STOP and GUARD lines, once each, on a settled ledger
void LedSay()
  {
   if(!g_led_settled) return;
   if(g_led_stop_ev >= 0 && !g_led_rep_stop)
     {
      g_led_rep_stop = true;
      int k = g_led_stop_ev;
      JrnAt(g_led_e[k].t, CR_EV_STOP, "-", KV("src", "history") + KD("B", g_led_e[k].eq) + KD("ref", g_led_e[k].ref)
            + KD("P_in", g_led_e[k].paid) + KD("fall_pct", g_cfg.stop_fall_pct) + KD("arm", g_cfg.stop_arm_paid));
     }
#ifndef CR_NO_GUARD
   if((g_led_guard_ev >= 0 || g_led_mark_key >= 0) && !g_led_rep_guard)
     {
      g_led_rep_guard = true;
      if(g_led_guard_ev >= 0)
        {
         int k = g_led_guard_ev;
         JrnAt(g_led_e[k].t, CR_EV_GUARD, "-", KV("src", "history_b") + KD("B", g_led_e[k].eq) + KD("ref", g_led_e[k].ref));
        }
      else Jrn(CR_EV_GUARD, "-", KV("src", "history_c") + KT("mark_utc", (datetime)(g_led_mark_key >> CR_LED_KEY_SHIFT)));
     }
#endif
  }

// one read of the history (SPEC 5): CR_LED_OK when the ledger is settled, else CR_LED_MOVING
int LedRead(const datetime now_srv)
  {
   g_led_last_read = now_srv;
   g_led_dirty = false;
   g_led_reads++;
   if(!HistorySelect(0, now_srv + 86400))
     {
      g_led_settled = false;
      return CR_LED_MOVING;
     }
   bool changed = LedLoadDeals();
   if(g_led_nd == 0 && !(AccountInfoDouble(ACCOUNT_BALANCE) > 0.0))
     {
      g_led_settled = false;                        // no deal and no balance: the account is not loaded yet
      return CR_LED_MOVING;
     }
   LedPlanCompute(now_srv);
   if(changed || !g_led_tables || g_led_T != g_led_T_built) LedBuild();
   double v = LedReadBT();
   g_led_bt_read = v;
   LedSettle(v, now_srv);
   double start = g_led_acc ? g_led_acc_v : v;
   if(!g_led_walked || start != g_led_bt)
     {
      g_led_bt = start;
      LedWalk();
     }
   LedSay();
   return g_led_settled ? CR_LED_OK : CR_LED_MOVING;
  }

bool LedSettled() { return g_led_settled; }
void LedOnTransaction() { g_led_dirty = true; }

void LedOnTimer(const datetime now_srv)
  {
   bool due = g_led_dirty || !g_led_settled || now_srv - g_led_last_read >= CR_LED_READ_EVERY || now_srv < g_led_last_read;
   if(due && (now_srv != g_led_last_read || g_led_dirty)) LedRead(now_srv);
  }

// ---- plan ---------------------------------------------------------------------------------------------------------
int LedPlan(const datetime now_srv)
  {
   if(g_cfg.plan_start > 0) return (g_cfg.plan_start > now_srv) ? CR_PLAN_FUTURE : CR_PLAN_OK;
   return g_cfg.demo ? CR_PLAN_OK : CR_PLAN_UNSET;
  }

// the plan at stamp S (UTC): UNSET on a real account without InpPlanStart; FUTURE before T
int LedPlanAt(const datetime S)
  {
   if(g_led_plan == CR_PLAN_UNSET) return CR_PLAN_UNSET;
   if(g_led_T > 0 && S < g_led_T_utc) return CR_PLAN_FUTURE;
   return CR_PLAN_OK;
  }

datetime LedPlanStart() { return (g_led_plan == CR_PLAN_UNSET) ? (datetime)0 : g_led_T; }
double   LedBT() { return g_led_bt; }

// ---- the state at a stamp S (UTC) ---------------------------------------------------------------------------------
double LedBalance(const datetime S)
  {
   int k = LedKnown(S);
   return (k > 0) ? g_led_e[k - 1].eq : g_led_bt;
  }

double LedPaidIn(const datetime S)
  {
   int k = LedKnown(S);
   return (k > 0) ? g_led_e[k - 1].paid : g_led_bt;
  }

double LedRef(const datetime S)
  {
   int k = LedKnown(S);
   return (k > 0) ? g_led_e[k - 1].ref : g_led_bt;
  }

// robot close money stamped before S since T
double LedCloseMoney(const datetime S)
  {
   int k = LedKnown(S);
   return (k > 0) ? g_led_e[k - 1].cm : 0.0;
  }

// the state after every event of the history read last (GUARD (a) compares the equity with LedRefNow)
double LedBalanceNow() { return (g_led_ne > 0) ? g_led_e[g_led_ne - 1].eq : g_led_bt; }
double LedPaidInNow() { return (g_led_ne > 0) ? g_led_e[g_led_ne - 1].paid : g_led_bt; }
double LedRefNow() { return (g_led_ne > 0) ? g_led_e[g_led_ne - 1].ref : g_led_bt; }

// ---- latches (SPEC 6.1, 6.2) --------------------------------------------------------------------------------------
datetime LedStopTime() { return (g_led_stop_ev >= 0) ? g_led_e[g_led_stop_ev].t : (datetime)0; }
bool     LedStoppedAt(const datetime S) { return g_led_stop_key >= 0 && g_led_stop_key < LedKey(S, CR_EK_CLOSE); }
bool     LedStopLatched() { return g_led_rep_stop || (g_led_settled && g_led_stop_ev >= 0); }
bool     LedMarkSeen() { return g_led_mark_key >= 0; }

bool LedGuardAt(const datetime S)
  {
#ifdef CR_NO_GUARD
   return false;
#else
   long lim = LedKey(S, CR_EK_CLOSE);
   return (g_led_guard_key >= 0 && g_led_guard_key < lim) || (g_led_mark_key >= 0 && g_led_mark_key < lim);
#endif
  }

bool LedGuardLatched()
  {
#ifdef CR_NO_GUARD
   return false;
#else
   return g_led_rep_guard || (g_led_settled && (g_led_guard_ev >= 0 || g_led_mark_key >= 0));
#endif
  }

// ---- daily lock (SPEC 6.3) ----------------------------------------------------------------------------------------
bool LedDayLockedAt(const datetime S)
  {
   if(!(g_cfg.lock_stakes > 0.0) || g_led_plan == CR_PLAN_UNSET) return false;
   datetime d0 = ClkServerToUtc(ClkServerDay(S));
   int kd = LedKnown(d0), ks = LedKnown(S);
   double bd = (kd > 0) ? g_led_e[kd - 1].eq : g_led_bt;
   double pd = (kd > 0) ? g_led_e[kd - 1].paid : g_led_bt;
   double cd = (kd > 0) ? g_led_e[kd - 1].cm : 0.0;
   double cs = (ks > 0) ? g_led_e[ks - 1].cm : 0.0;
   double lim = g_cfg.lock_stakes * LedRate(MathMax(bd, pd)) / 100.0 * bd;
   return lim > 0.0 && cs - cd <= -lim;
  }

// LOCK now: concluded only on a settled ledger (SPEC 5); a LOCK concluded earlier holds for the rest of its server day
bool LedDayLocked(const datetime now_srv)
  {
   datetime S = ClkServerToUtc(now_srv) + 1;
   datetime day = ClkServerDay(S);
   if(g_led_lock_day != 0 && g_led_lock_day == day && g_cfg.lock_stakes > 0.0) return true;
   if(!g_led_settled) return false;
   if(!LedDayLockedAt(S)) return false;
   g_led_lock_day = day;
   return true;
  }

// ---- week unit (SPEC 5) -------------------------------------------------------------------------------------------
datetime LedWeekStart(const datetime S) { return ClkServerToUtc(ClkServerWeek(S)); }

int LedWkFind(const datetime w0)
  {
   for(int j = 0; j < g_led_nwk; j++)
      if(g_led_wk0[j] == w0) return j;
   return -1;
  }

// the week's first ledger event at or before S: its stored roll, else the first robot close stamped in [week start, S),
// else S itself (a sizing request)
datetime LedWeekRoll(const datetime S)
  {
   datetime w0 = LedWeekStart(S);
   int j = LedWkFind(w0);
   if(j >= 0) return g_led_wkr[j];
   long lim = LedKey(S, CR_EK_CLOSE);
   for(int k = LedLower(LedKey(w0, CR_EK_PAY)); k < g_led_ne && g_led_key[k] < lim; k++)
      if(g_led_e[k].kind == CR_EK_CLOSE) return g_led_e[k].t;
   return S;
  }

double LedWeekUnit(const datetime S)
  {
   int j = LedWkFind(LedWeekStart(S));
   return (j >= 0) ? g_led_wku[j] : 0.0;
  }

void LedSetWeekUnit(const datetime S, const double unit)
  {
   datetime w0 = LedWeekStart(S);
   if(LedWkFind(w0) >= 0 || !(unit > 0.0)) return;
   datetime r = LedWeekRoll(S);
   if(g_led_nwk >= CR_LED_MAX_WEEKS)
     {
      for(int j = 1; j < g_led_nwk; j++)
        {
         g_led_wk0[j - 1] = g_led_wk0[j];
         g_led_wku[j - 1] = g_led_wku[j];
         g_led_wkr[j - 1] = g_led_wkr[j];
        }
      g_led_nwk--;
     }
   ArrayResize(g_led_wk0, g_led_nwk + 1, CR_LED_MAX_WEEKS);
   ArrayResize(g_led_wku, g_led_nwk + 1, CR_LED_MAX_WEEKS);
   ArrayResize(g_led_wkr, g_led_nwk + 1, CR_LED_MAX_WEEKS);
   g_led_wk0[g_led_nwk] = w0;
   g_led_wku[g_led_nwk] = unit;
   g_led_wkr[g_led_nwk] = r;
   g_led_nwk++;
  }

// robot close money of S's week before S, in units (0 when the week has no unit yet)
double LedWeekW(const datetime S)
  {
   int j = LedWkFind(LedWeekStart(S));
   if(j < 0 || !(g_led_wku[j] > 0.0)) return 0.0;
   int kr = LedKnown(g_led_wkr[j]), ks = LedKnown(S);
   double base = (kr > 0) ? g_led_e[kr - 1].eq : g_led_bt;
   for(int k = kr; k < ks; k++)
      if(g_led_e[k].kind != CR_EK_CLOSE) base = base + g_led_e[k].amount;
   double b = (ks > 0) ? g_led_e[ks - 1].eq : g_led_bt;
   return (b - base) / g_led_wku[j];
  }

// ---- positions ----------------------------------------------------------------------------------------------------
int LedPosCount() { return g_led_np; }

bool LedPosAt(const int k, CrLedPos &p)
  {
   if(k < 0 || k >= g_led_np) return false;
   p = g_led_p[k];
   return true;
  }

// ---- gold commission of a server day (SPEC 2.6 COST): USD per oz round trip from DEAL_COMMISSION -------------------
bool LedCommission(const datetime day_srv, double &usd_per_oz, int &n)
  {
   usd_per_oz = 0.0;
   n = 0;
   string nm = g_sym[CR_XAU].name;
   if(nm == "") return false;
   double ts = SymbolInfoDouble(nm, SYMBOL_TRADE_TICK_SIZE), tv = SymbolInfoDouble(nm, SYMBOL_TRADE_TICK_VALUE);
   double cs = SymbolInfoDouble(nm, SYMBOL_TRADE_CONTRACT_SIZE);
   if(!(ts > 0.0) || !(tv > 0.0) || !(cs > 0.0)) return false;
   double q = tv / (ts * cs);                       // account currency per USD
   double c = 0.0, oz = 0.0;
   for(int i = 0; i < g_led_nd; i++)
     {
      if(g_led_d[i].sym != CR_XAU || !LedTradeDeal(g_led_d[i].type) || ClkDay(g_led_d[i].t_srv) != day_srv) continue;
      int k = (g_led_d[i].pos > 0) ? LedFindPos(g_led_d[i].pos) : -1;
      if(k < 0 || !g_led_p[k].robot) continue;
      c += MathAbs(g_led_d[i].comm);
      oz += g_led_d[i].volume * cs;
      n++;
     }
   if(n == 0 || !(oz > 0.0)) return false;
   usd_per_oz = 2.0 * c / oz / q;                   // a side per oz, then the round trip
   return true;
  }

// ---- init, reset --------------------------------------------------------------------------------------------------
void LedForgetWeeks()
  {
   g_led_nwk = 0;
   ArrayResize(g_led_wk0, 0);
   ArrayResize(g_led_wku, 0);
   ArrayResize(g_led_wkr, 0);
  }

// a rebuild (SPEC 4.8): the deals are read again from the broker and the week units come back with the replay's
// sizing requests; the settle state and the latches already concluded are kept
void LedReset()
  {
   g_led_nd = 0;
   g_led_first_srv = 0;
   g_led_np = 0;
   g_led_ne = 0;
   g_led_tables = false;
   g_led_T_built = 0;
   g_led_walked = false;
   g_led_dirty = true;
   LedForgetWeeks();
  }

bool LedInit(string &err)
  {
   err = "";
   if(!(g_cfg.stop_fall_pct > 0.0 && g_cfg.stop_fall_pct < 100.0))
     {
      err = "InpStopFallPct must lie between 0 and 100 (excluded)";
      return false;
     }
   if(!(g_cfg.stop_arm_paid >= 0.0))
     {
      err = "InpStopArmPaid must be 0 or more";
      return false;
     }
   if(!(g_cfg.lock_stakes >= 0.0))
     {
      err = "InpDailyLockStakes must be 0 or more";
      return false;
     }
   if((long)g_cfg.plan_start < 0)
     {
      err = "InpPlanStart must be a server time (0 = unset)";
      return false;
     }
   if(g_cfg.lock_stakes > 0.0 && g_led_rn <= 0)
     {
      err = "the daily lock needs the risk table (SizInit runs before LedInit)";
      return false;
     }
   LedReset();
   g_led_T = 0;
   g_led_T_utc = 0;
   g_led_plan = CR_PLAN_UNSET;
   g_led_bt = 0.0;
   g_led_bt_read = 0.0;
   g_led_mark_key = -1;
   g_led_stop_key = -1;
   g_led_stop_ev = -1;
   g_led_guard_key = -1;
   g_led_guard_ev = -1;
   g_led_rep_stop = false;
   g_led_rep_guard = false;
   g_led_said_plan = false;
   g_led_lock_day = 0;
   g_led_acc = false;
   g_led_acc_v = 0.0;
   g_led_has_prev = false;
   g_led_acc_prev = 0.0;
   g_led_has_cand = false;
   g_led_cand_v = 0.0;
   g_led_cand_t = 0;
   g_led_move_t = 0;
   g_led_settled = false;
   g_led_last_read = 0;
   g_led_reads = 0;
   return true;
  }
#endif

// ==== end src/CR_Ledger.mqh
// ==== begin src/CR_Sizing.mqh
//+------------------------------------------------------------------+
//| CR_Sizing.mqh - risk table, cushion multiplier, lots, the account |
//| checks in the lab's order (SPEC 5). Owner: I.                     |
//|                                                                  |
//| The lab's sizing (growth.py engine with the plan's key 1 and the  |
//| cushion_only stake rule, stake.py:166-192, account.py:95-115):    |
//|   rate(key)  pct of the last pair "from:pct" with from <= key,    |
//|              key = max(B, P_in) (growth.py:93-98, 118)             |
//|   unit       rate(max(B_w, P_in,w)) / 100 x B_w at the week's     |
//|              first ledger event (growth.py:274); w = robot close  |
//|              money of the week before S / unit (CR_Ledger)        |
//|   m          1 if w <= 0, else min(1, max(0.25, w / 4))            |
//|   lots       floor(B x rate x m x f / 100 / per_lot / step +      |
//|              1e-9) x step (growth.py:296), per_lot = r x          |
//|              tick_value_loss / tick_size; f = the stake factor of |
//|              a change while its switch is on (H2 0.750978,        |
//|              S0.75r 0.771793; g_sl rows of CR_Registry), else 1   |
//|   r (SPEC 4.2, P1)  quote_p = (quote + side x h) x (1 + side x    |
//|              sm), quote = ask (long) or bid (short), h = the      |
//|              paper half commission, sm = the lab's market slip;   |
//|              market: r = stop_dist, or side x (quote_p - stop)    |
//|              for an absolute stop; stop, limit, OCO (sent one bar |
//|              late): r = max(side x (paper fill - stop),           |
//|              side x (quote_p - stop)), late = 1                   |
//| Checks, in order (SPEC 5; the lab's order growth.py:291-309):     |
//|   NOTALLOWED (the caller's: the code is not in InpSleeves)        |
//|   SETTLE     the ledger moves: a wait, no line, nothing computed  |
//|   OBSERVE    plan unset on a real account, or the stamp is before |
//|              T                                                    |
//|   -- the week unit is set here (every sizing request sets it) --  |
//|   STOPPED, GUARD, LOCK   the history latches known at S           |
//|   the caller's reason    FRIDAY, CLOCK, NOTREADY, PREV_OPEN,      |
//|              NOTRADE ... (the follower puts it in it.skip)        |
//|   MIN_LOT    never rounded up (also: r <= 0 or B <= 0, why=...)    |
//|   CAP        6 robot positions, or 2 on the symbol, counting the  |
//|              positions closed with a stamp at or after S          |
//|   MARGIN     sum of OrderCalcMargin of those positions (at their  |
//|              open price) + the new one (at the quote) > B          |
//| Skips never touch the paper. Each call but SETTLE writes a SIZE   |
//| line: lots, want (lots before the checks), skip, B, P_in, rate,   |
//| m, f, unit, w, r, budget, late, quote (rp=1 in the replay).       |
//|                                                                  |
//| API (S0 signatures kept; the rest is new):                        |
//|   SizInit(err)                 parse g_cfg.risk_table; false =    |
//|                                ERROR at OnInit; copies the table  |
//|                                into the ledger (daily lock)       |
//|   SizParseTable(s, from, pct, n, err)   the parser itself: pairs  |
//|                                "from:pct" separated by ';' (one   |
//|                                ';' may end the list), plain       |
//|                                decimals, from[0] = 0, from        |
//|                                strictly increasing, pct in        |
//|                                (0, 5], at most 16 pairs           |
//|   SizRate(key)  SizM(w)  SizFactor(sl)  SizRisk(it)               |
//|   SizWeekUnit(S)               sets the week unit if the week has |
//|                                none; the follower calls it for a  |
//|                                MISSED reason=exited intent        |
//|   SizSize(it, S, dry)          lots and skip of an intent at      |
//|                                stamp S; on entry it.skip holds    |
//|                                the caller's reason (CR_SK_NONE if |
//|                                none); dry = the replay: no read   |
//|                                of the history, and only positions |
//|                                opened before the stamp's minute   |
//|                                count; returns it.skip             |
//|   SizSkipName(code)            journal name of a CR_SK_* code     |
//| CR_Registry is not included: it pulls the rule files in. The      |
//| stake factor is read from the g_sl row as RegStakeFactor does.    |
//+------------------------------------------------------------------+
#ifndef CR_SIZING_MQH
#define CR_SIZING_MQH
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Ledger.mqh)

#define CR_SIZ_MAX_PAIRS 16             // pairs of InpRiskTable at most
#define CR_SIZ_PCT_MAX 5.0              // a rate above 5 % per trade is refused (SPEC 1)
#define CR_SIZ_MAX_POS 6                // account.py LIMITS max_positions
#define CR_SIZ_MAX_SYM 2                // account.py LIMITS max_per_sym

double g_siz_from[];                   // the parsed InpRiskTable
double g_siz_pct[];
int    g_siz_n = 0;

string CR_SK_NAME[18] = {"none", "stopped", "guard", "lock", "friday", "clock", "notready", "observe", "settle", "prev_open",
                         "min_lot", "cap", "margin", "notallowed", "notrade", "late", "exited", "selftest"};

string SizSkipName(const int k)
  {
   if(k < 0 || k > 17) return "code" + IntegerToString(k);
   return CR_SK_NAME[k];
  }

// a plain decimal: digits with at most one '.', no sign, no exponent
bool SizNumber(const string s, double &v)
  {
   string t = s;
   StringTrimLeft(t);
   StringTrimRight(t);
   int len = StringLen(t);
   if(len == 0 || len > 24) return false;
   int digits = 0, dots = 0;
   for(int i = 0; i < len; i++)
     {
      int c = (int)StringGetCharacter(t, i);
      if(c >= '0' && c <= '9') digits++;
      else if(c == '.') dots++;
      else return false;
     }
   if(digits == 0 || dots > 1) return false;
   v = StringToDouble(t);
   return MathIsValidNumber(v);
  }

bool SizParseTable(const string s, double &from[], double &pct[], int &n, string &err)
  {
   n = 0;
   err = "";
   string t = s;
   StringTrimLeft(t);
   StringTrimRight(t);
   if(t == "")
     {
      err = "InpRiskTable is empty";
      return false;
     }
   string part[];
   int np = StringSplit(t, ';', part);
   if(np > 0)
     {
      string last = part[np - 1];
      StringTrimLeft(last);
      StringTrimRight(last);
      if(last == "") np--;                         // one ';' may end the list
     }
   if(np <= 0)
     {
      err = "InpRiskTable has no pair";
      return false;
     }
   if(np > CR_SIZ_MAX_PAIRS)
     {
      err = "InpRiskTable has more than 16 pairs";
      return false;
     }
   ArrayResize(from, np);
   ArrayResize(pct, np);
   for(int k = 0; k < np; k++)
     {
      string kv[];
      double f = 0.0, p = 0.0;
      if(StringSplit(part[k], ':', kv) != 2 || !SizNumber(kv[0], f) || !SizNumber(kv[1], p))
        {
         err = "InpRiskTable: '" + part[k] + "' is not a pair from:pct of plain numbers";
         return false;
        }
      if(k == 0 && f != 0.0)
        {
         err = "InpRiskTable must start with the pair 0:pct";
         return false;
        }
      if(k > 0 && !(f > from[k - 1]))
        {
         err = "InpRiskTable: the 'from' values must increase ('" + part[k] + "')";
         return false;
        }
      if(!(p > 0.0 && p <= CR_SIZ_PCT_MAX))
        {
         err = "InpRiskTable: a rate must be above 0 and at most 5 % ('" + part[k] + "')";
         return false;
        }
      from[k] = f;
      pct[k] = p;
     }
   n = np;
   return true;
  }

bool SizInit(string &err)
  {
   err = "";
   int n = 0;
   g_siz_n = 0;
   if(!SizParseTable(g_cfg.risk_table, g_siz_from, g_siz_pct, n, err)) return false;
   g_siz_n = n;
   LedSetRates(g_siz_from, g_siz_pct, n);
   return true;
  }

// pct of the last pair with from <= key (the table that SizInit gave the ledger)
double SizRate(const double key) { return LedRate(key); }

// the cushion_only stake rule (stake.py:166-192 with prot_k 4, prot_min 0.25)
double SizM(const double w)
  {
   if(w <= 0.0) return 1.0;
   double m = w / 4.0;
   if(m < 0.25) m = 0.25;
   if(m > 1.0) m = 1.0;
   return m;
  }

// the stake factor of a sleeve as resolved at OnInit (CR_Registry RegStakeFactor: off = 1)
double SizFactor(const int sl)
  {
   if(sl < 0 || sl >= g_nsl) return 1.0;
   return g_sl[sl].change_on ? g_sl[sl].factor_on : 1.0;
  }

// risk per unit for the sizing (SPEC 4.2, P1); sets it.late
double SizRisk(CrIntent &it)
  {
   int s = g_sl[it.sleeve].sym;
   double qp = (it.quote + it.side * g_sym[s].h) * (1.0 + it.side * g_sym[s].slip_mkt);
   if(it.etype == CR_ET_MARKET)
     {
      it.late = false;
      if(it.stop != 0.0) return it.side * (qp - it.stop);
      return it.stop_dist;
     }
   it.late = true;
   double st = (it.stop != 0.0) ? it.stop : it.paper_fill - it.side * it.stop_dist;
   double r1 = it.side * (it.paper_fill - st);
   double r2 = it.side * (qp - st);
   return (r2 > r1) ? r2 : r1;
  }

// the week unit of S's week, set at the week's first ledger event (growth.py:228-233, 274)
double SizWeekUnit(const datetime S)
  {
   double u = LedWeekUnit(S);
   if(u > 0.0) return u;
   datetime r = LedWeekRoll(S);
   double bw = LedBalance(r), pw = LedPaidIn(r);
   u = MathMax(SizRate(MathMax(bw, pw)) / 100.0 * bw, 1e-9);
   LedSetWeekUnit(S, u);
   return u;
  }

void SizLine(const CrIntent &it, const datetime S, const bool dry, const double want, const string why)
  {
   string kv = KI("oid", it.oid) + KI("side", it.side) + KI("et", it.etype) + KD("lots", it.lots) + KD("want", want)
               + KV("skip", SizSkipName(it.skip)) + KD("B", it.B) + KD("P_in", it.P_in) + KD("rate", it.rate) + KD("m", it.m)
               + KD("f", it.f) + KD("unit", it.unit) + KD("w", it.w) + KD("r", it.r) + KD("budget", it.budget)
               + KB("late", it.late) + KD("quote", it.quote);
   if(why != "") kv = kv + KV("why", why);
   JrnAt(S, CR_EV_SIZE, JrnCode(it.sleeve), kv + JrnRp(dry));
  }

int SizSize(CrIntent &it, const datetime S, const bool dry)
  {
   int pre = it.skip;
   it.skip = CR_SK_NONE;
   it.lots = 0.0;
   it.budget = 0.0;
   it.rate = 0.0;
   it.m = 0.0;
   it.B = 0.0;
   it.P_in = 0.0;
   it.unit = 0.0;
   it.w = 0.0;
   it.r = 0.0;
   it.late = (it.etype != CR_ET_MARKET);
   it.f = SizFactor(it.sleeve);
   if(it.sleeve < 0 || it.sleeve >= g_nsl)
     {
      it.skip = CR_SK_NOTREADY;
      JrnError("-", "SizSize: no sleeve row " + IntegerToString(it.sleeve));
      return it.skip;
     }
   if(pre == CR_SK_NOTALLOWED)
     {
      it.skip = pre;
      SizLine(it, S, dry, 0.0, "");
      return it.skip;
     }
   if(!dry) LedRead(TimeTradeServer());            // the latest history: a position opened a moment ago counts
   if(!LedSettled())
     {
      it.skip = CR_SK_SETTLE;                      // a wait inside the intent's window (SPEC 5): no line
      return it.skip;
     }
   if(LedPlanAt(S) != CR_PLAN_OK)
     {
      it.skip = CR_SK_OBSERVE;
      SizLine(it, S, dry, 0.0, "");
      return it.skip;
     }
   it.unit = SizWeekUnit(S);
   it.B = LedBalance(S);
   it.P_in = LedPaidIn(S);
   it.w = LedWeekW(S);
   it.m = SizM(it.w);
   it.rate = SizRate(MathMax(it.B, it.P_in));
   int g = CR_SK_NONE;
   if(LedStoppedAt(S)) g = CR_SK_STOPPED;
   else if(LedGuardAt(S)) g = CR_SK_GUARD;
   else if(LedDayLockedAt(S)) g = CR_SK_LOCK;
   else if(pre != CR_SK_NONE) g = pre;
   if(g != CR_SK_NONE)
     {
      it.skip = g;
      SizLine(it, S, dry, 0.0, "");
      return it.skip;
     }
   int s = g_sl[it.sleeve].sym;
   string nm = g_sym[s].name;
   it.r = SizRisk(it);
   double tvl = SymbolInfoDouble(nm, SYMBOL_TRADE_TICK_VALUE_LOSS), ts = SymbolInfoDouble(nm, SYMBOL_TRADE_TICK_SIZE);
   double step = SymbolInfoDouble(nm, SYMBOL_VOLUME_STEP), vmin = SymbolInfoDouble(nm, SYMBOL_VOLUME_MIN);
   if(!(tvl > 0.0) || !(ts > 0.0) || !(step > 0.0))
     {
      it.skip = CR_SK_NOTREADY;
      SizLine(it, S, dry, 0.0, "symbol");
      return it.skip;
     }
   if(!(it.r > 0.0) || !MathIsValidNumber(it.r))
     {
      it.skip = CR_SK_MIN_LOT;
      SizLine(it, S, dry, 0.0, "risk");
      return it.skip;
     }
   if(!(it.B > 0.0))
     {
      it.skip = CR_SK_MIN_LOT;
      SizLine(it, S, dry, 0.0, "balance");
      return it.skip;
     }
   double per_lot = it.r * (tvl / ts);
   it.budget = it.B * it.rate * it.m * it.f / 100.0;
   double lots = MathFloor(it.B * it.rate * it.m * it.f / 100.0 / per_lot / step + 1e-9) * step;
   if(lots < vmin)
     {
      it.skip = CR_SK_MIN_LOT;
      SizLine(it, S, dry, lots, "");
      return it.skip;
     }
   int nall = 0, nsym = 0;
   double used = 0.0;
   bool mok = true;
   int np = LedPosCount();
   CrLedPos p;
   for(int k = 0; k < np; k++)
     {
      if(!LedPosAt(k, p) || !p.robot) continue;
      if(dry && !(p.t_in < S)) continue;            // the replay: only positions opened before the stamp's minute
      if(p.closed && p.stamp < S) continue;          // booked before S: no longer open for the lab
      nall++;
      if(p.sym == s) nsym++;
      if(p.sym >= 0 && p.side != 0)
        {
         double mg = 0.0;
         if(OrderCalcMargin(p.side > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, g_sym[p.sym].name, p.vol_in, p.px_in, mg)) used += mg;
         else mok = false;
        }
     }
   if(nall >= CR_SIZ_MAX_POS || nsym >= CR_SIZ_MAX_SYM)
     {
      it.skip = CR_SK_CAP;
      SizLine(it, S, dry, lots, "n=" + IntegerToString(nall) + ",sym=" + IntegerToString(nsym));
      return it.skip;
     }
   double q = (it.quote > 0.0) ? it.quote : it.paper_fill;
   double mnew = 0.0;
   if(!mok || !(q > 0.0) || !OrderCalcMargin(it.side > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, nm, lots, q, mnew))
     {
      it.skip = CR_SK_MARGIN;
      SizLine(it, S, dry, lots, "calc");
      return it.skip;
     }
   if(used + mnew > it.B)
     {
      it.skip = CR_SK_MARGIN;
      SizLine(it, S, dry, lots, "");
      return it.skip;
     }
   it.lots = lots;
   SizLine(it, S, dry, lots, "");
   return it.skip;
  }
#endif

// ==== end src/CR_Sizing.mqh
// ==== begin src/CR_Broker.mqh
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
// (already included: <Trade\Trade.mqh>)
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Clock.mqh)
// (already inlined: CR_Journal.mqh)

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

// ==== end src/CR_Broker.mqh
// ==== begin src/CR_Guards.mqh
//+------------------------------------------------------------------+
//| CR_Guards.mqh - the live protections of SPEC 6 (plan stop and     |
//| disaster guard close-all and mark, daily lock, Friday close,     |
//| clock check), the instance lock (SPEC 4.9), the self-test runner. |
//| Owner: J.                                                         |
//|                                                                  |
//| The guards read the history latches of CR_Ledger (STOP, GUARD b  |
//| and c, LOCK) and add what only the live account shows:            |
//|   GUARD (a)  equity <= 50 % of ref (LedRefNow), on a settled      |
//|              ledger, the plan in force (not under CR_NO_GUARD);   |
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
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Clock.mqh)
// (already inlined: CR_Journal.mqh)
// (already inlined: CR_Ledger.mqh)
// (already inlined: CR_Broker.mqh)

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
   bool settled = LedSettled();
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
   // GUARD (SPEC 6.2): (b, c) from the history, (a) on the live equity
   if(!g_grd_guard)
     {
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

// ==== end src/CR_Guards.mqh
// ==== begin src/CR_Follower.mqh
//+------------------------------------------------------------------+
//| CR_Follower.mqh - the account follows the paper (SPEC 4): intents,|
//| sizing calls, stops, exits, duplicates, reconcile, NOT_READY      |
//| exits by LatestExit, the broker-stop invariant, the observer's    |
//| WATCH. Owner: J.                                                  |
//|                                                                  |
//| One real position per sleeve follows one paper trade (its oid).  |
//| Nothing is stored: every rebuild forgets the follower's state and |
//| FolReconcile maps the broker's positions onto the replayed chain. |
//|                                                                  |
//| Entries (SPEC 4.1). A market order becomes an intent at the       |
//|   barrier of the minute M where it activates: the first waiting   |
//|   market order of the sleeve's paper queue (emission order) whose |
//|   window holds M (after_exit_of: its exit resolved on an earlier  |
//|   bar), the sleeve's paper trade ended on an earlier bar, not void|
//|   at activation (void_le, x <= M), not refused by the 3-spread    |
//|   test on the live paper quote, and the symbol ticked in minute M |
//|   (else it is armed and the first tick of M makes the intent).    |
//|   Stamp = M. A stop, limit or OCO order becomes an intent at its  |
//|   PFILL on bar i, stamp i, sent at barrier i + 1, unless its paper|
//|   trade already exited (stopped, gap, revised or voided on its    |
//|   fill bar): MISSED reason=exited, which still sets the week unit |
//|   (P5). A market fill whose activation was not seen (no tick seen |
//|   in its minute) becomes a late intent the same way, with the     |
//|   paper's own stop. Intents are sized in the order (stamp, lab    |
//|   sleeve name in byte order) and are sendable until stamp + 5 min,|
//|   then MISSED (the reason the intent waited for, else late).     |
//| Sizing (SPEC 5): SizSize with the caller's reason: NOTALLOWED     |
//|   (InpSleeves), the guards' block (STOPPED, GUARD, LOCK, FRIDAY,  |
//|   CLOCK, SELFTEST, NOTRADE), NOTREADY; SETTLE makes it wait. A    |
//|   skip is final: the sleeve stays busy until its paper trade ends.|
//| Send (SPEC 4.3): BrkIntentCheck first (one intent, one trade): a  |
//|   position of the previous trade is closed first (the intent      |
//|   waits; at the window's end MISSED reason=prev_open); an order,  |
//|   deal or position already made at or after the stamp is adopted |
//|   and nothing is sent again. Broker stop = GridStop(paper stop +  |
//|   side x h); a market order with a distance stop starts from the  |
//|   quote: GridStop(quote_p - side x stop_dist + side x h), quote_p |
//|   as SizRisk. After an unknown result nothing is re-sent before   |
//|   the connection is up, the ledger settled and two reads of the   |
//|   positions and orders 2 s apart agree; BrkIntentCheck decides.   |
//|   A transient refusal is tried again (1, 2, 4 ... 30 s) inside    |
//|   the window; a stop already crossed by the price: MISSED stop.   |
//| Stops (SPEC 4.4, R4), every pass and at every barrier, for every  |
//|   robot position, NOT_READY sleeves included: no stop 5 s after   |
//|   POSITION_TIME -> the expected stop is put back, else the        |
//|   position is closed (SLFIX); for a READY sleeve the stop must be |
//|   the expected one (the paper stop of its trade, or the stop sent |
//|   before its PFILL): PositionModify, kept and tried again every   |
//|   10 s when refused (STOPS_LEVEL, FREEZE_LEVEL); an expected stop |
//|   the price has already crossed -> close.                         |
//| Exits (SPEC 4.5): at the barrier of ClkRealExitMinute(x) for the  |
//|   paper's time exit x of the followed trade (with the broker's    |
//|   session end); when that is x itself the close waits for the     |
//|   symbol's first tick at or after x, as the paper's exit bar; at  |
//|   the symbol's first tick inside a rule exit's window (CrExit,    |
//|   N30); when the paper trade ends (PEXIT, PREVISE, PVOID,         |
//|   PREFUSE). Closes are tried again every 10 s, 60 s while the     |
//|   market is closed, with one warning push.                        |
//| Duplicates (R5): at every barrier one position per magic: a newer |
//|   extra one is closed (DUP), an older unknown one too (ORPHAN).   |
//| Reconcile (SPEC 4.8 d), after the replay, once connected, the    |
//|   ledger settled, two stable reads, and every robot position the |
//|   history holds open listed (at most 60 s): positions of retired  |
//|   ids and marks are closed; each sleeve is reconciled when READY  |
//|   (a NOT_READY sleeve keeps its positions, their stops, and closes|
//|   them at LatestExit(POSITION_TIME, comment) with the gap rule):  |
//|   a same-side position opened within 5 min of the open paper      |
//|   trade's stamp -> ADOPT (its stop reset); one matching a market  |
//|   order still waiting in the paper queue -> ADOPT for that order; |
//|   any other -> ORPHAN (an extra newer one: DUP); a paper trade    |
//|   without position -> nothing if the history shows its position   |
//|   closed, an intent inside its send window, else MISSED (the dry  |
//|   sizing's skip, else late).                                      |
//| Replay (live = false): every PFILL is sized dry in the same order |
//|   (SizSize dry: week units, SIZE rp=1); a stop, limit or OCO fill |
//|   that exited on its bar is MISSED exited (rp=1). Nothing is sent.|
//| Observer (SPEC 4.9): no request at all; WATCH pushes when a robot |
//|   position outlives its paper exit, or its LatestExit, by 5 min.  |
//|                                                                  |
//| The paper engine gives no API for its queue, its rule exits and  |
//| the order of its trade: FolQAt, FolOrderOf and FolExitDue read   |
//| CR_Paper's tables (g_pap_q, g_pap_x, g_pap_t) and never change   |
//| them.                                                            |
//|                                                                  |
//| API (S0 signatures kept):                                        |
//|   FolInit(err)                  once at OnInit                   |
//|   FolReset()                    forget the intents (rebuild)     |
//|   FolOnPaperEvent(e, live)      every paper event, in order      |
//|   FolOnMinute(M, live)          after barrier M: entries, exits, |
//|                                 duplicates (live = false: the    |
//|                                 replay, dry sizing, no order)    |
//|   FolOnTimer(now_srv)           every timer pass: invariant,     |
//|                                 retries, watch                   |
//|   FolReconcile(now_srv)         SPEC 4.8 (d); false = not yet    |
//|   FolOnTransaction(trans)       OnTradeTransaction               |
//+------------------------------------------------------------------+
#ifndef CR_FOLLOWER_MQH
#define CR_FOLLOWER_MQH
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Clock.mqh)
// (already inlined: CR_Journal.mqh)
// (already inlined: CR_Registry.mqh)
// (already inlined: CR_Bars.mqh)
// (already inlined: CR_Paper.mqh)
// (already inlined: CR_Ledger.mqh)
// (already inlined: CR_Sizing.mqh)
// (already inlined: CR_Broker.mqh)
// (already inlined: CR_Guards.mqh)

#define CR_FOL_WINDOW 300               // an intent is sendable until stamp + 5 min (the lab's tolerance)
#define CR_FOL_ADOPT 300                // ADOPT: opened within 5 min of the paper trade's stamp
#define CR_FOL_RETRY 10                 // closes and stop moves: again in 10 s ...
#define CR_FOL_RETRY_CLOSED 60          // ... 60 s while the market is closed
#define CR_FOL_NOSL 5                   // no stop 5 s after POSITION_TIME: put it back, or close (SLFIX)
#define CR_FOL_WATCH 300                // observer: a position 5 min past its exit -> WATCH
#define CR_FOL_LIST_WAIT 60             // reconcile waits at most 60 s for the positions the history holds open
#define CR_FOL_LISTING 30               // a filled position not listed for 30 s is taken as closed
#define CR_FOL_SEND_MAX 30              // a refused send is tried again after 1, 2, 4 ... 30 s
#define CR_FOL_CMAX 64                  // positions waiting to be closed at once
#define CR_FOL_WMAX 64                  // positions already reported by WATCH

// close reasons (CLOSE why=)
#define CR_FW_TIME 0
#define CR_FW_RULE 1
#define CR_FW_PAPER 2
#define CR_FW_REVISE 3
#define CR_FW_VOID 4
#define CR_FW_PREFUSE 5
#define CR_FW_ORPHAN 6
#define CR_FW_DUP 7
#define CR_FW_SLFIX 8
#define CR_FW_LATEST 9
#define CR_FW_PREV 10
#define CR_FW_CROSSED 11
#define CR_FW_REFUSED 12
#define CR_FW_MARK 13
#define CR_FW_N 14
string CR_FW_NAME[CR_FW_N] = {"time", "rule", "paper", "revise", "void", "prefuse", "orphan", "dup", "slfix", "latest_exit",
                              "prev", "crossed", "refused", "mark"};

struct CrFolClose                       // a position to close, tried again until it is gone
  {
   ulong    ticket;
   long     magic;
   int      why;                        // CR_FW_*
   datetime next;                       // next attempt (server)
   int      tries;
   bool     warned;
  };

struct CrFol                            // one sleeve
  {
   long     oid;                        // the paper trade the real position follows (0 = none)
   ulong    ticket;                     // its position (0 = none open)
   int      side;
   datetime stamp;                      // its intent's stamp (UTC)
   double   sl_send;                    // the stop sent with it (expected until the paper trade's own stop)
   datetime t_open;                     // server time of its send (a fill listed late)
   int      ist;                        // the intent: CR_IS_WAIT, UNKNOWN, OPEN, DONE, MISSED
   CrIntent it;
   datetime it_next;                    // its next attempt (server)
   int      it_tries;
   bool     sized;                      // SizSize answered: it.lots, it.budget
   int      last_why;                   // the reason the intent last waited for (CR_SK_*)
   long     last_oid;                   // the last paper oid an intent was decided for
   long     arm_oid;                    // a market order waiting for the symbol's first tick in minute arm_M
   datetime arm_M;
   bool     xarm;                       // an exit waiting for the symbol's first tick at or after xarm_t
   datetime xarm_t;
   int      xarm_why;
   datetime md_next;                    // next stop move attempt (server)
   bool     ready;
   bool     rec_due;                    // reconcile still to do (the sleeve was NOT_READY)
   bool     ev_fill;                    // a PFILL in the drain of this barrier
   CrPEvent fill;
   bool     ev_end;                     // ... whose trade ended in the same drain
   long     end_oid;                    // the last paper trade that ended and why (CR_FW_*)
   int      end_why;
   long     lf_oid;                     // the last fill (WATCH)
   datetime lf_bar;
   int      lf_side;
   long     le_oid;                     // the last end of that fill, its stamp
   datetime le_t;
   long     dry_oid;                    // the replay's sizing of the last fill
   int      dry_skip;
  };

CrFol      g_fol[CR_MAX_SL];
string     g_fol_why[CR_MAX_SL];        // why the intent last waited, when it is not a sizing reason (the MISSED reason)
CrFolClose g_fol_cl[CR_FOL_CMAX];
int        g_fol_ncl = 0;
ulong      g_fol_watch[CR_FOL_WMAX];
int        g_fol_nwatch = 0;
datetime   g_fol_M = 0;                 // the last barrier processed live (UTC)
datetime   g_fol_rec_t0 = 0;            // first reconcile attempt of a rebuild (server)

//+------------------------------------------------------------------+
//| A read-only view of the paper's queue, rule exits and trade      |
//+------------------------------------------------------------------+
bool FolQAt(const int sl, const int k, CrOrder &o, int &st)
  {
   if(sl < 0 || sl >= CR_MAX_SL || k < 0 || k >= g_pap_qn[sl]) return false;
   int i = sl * CR_PAP_QMAX + k;
   o = g_pap_q[i].o;
   st = g_pap_q[i].st;
   return true;
  }

// the order oid is still in the paper queue (waiting for its activation or its fill)
bool FolOrderWaiting(const int sl, const long oid)
  {
   if(oid == 0) return false;
   CrOrder o;
   int st = 0;
   for(int k = 0; k < g_pap_qn[sl]; k++)
      if(FolQAt(sl, k, o, st) && st != 0 && o.oid == oid) return true;
   return false;
  }

// the paper order of oid: the trade's own (also once it ended) or a queued one
bool FolOrderOf(const int sl, const long oid, CrOrder &o)
  {
   if(oid == 0 || sl < 0 || sl >= CR_MAX_SL) return false;
   if(g_pap_t[sl].o.oid == oid)
     {
      o = g_pap_t[sl].o;
      return true;
     }
   int st = 0;
   for(int k = 0; k < g_pap_qn[sl]; k++)
      if(FolQAt(sl, k, o, st) && o.oid == oid) return true;
   return false;
  }

// a rule exit (CrExit) of oid still waiting whose window holds minute M
bool FolExitDue(const int sl, const long oid, const datetime M)
  {
   int base = sl * CR_PAP_XMAX;
   for(int k = 0; k < g_pap_xn[sl]; k++)
     {
      int i = base + k;
      if(g_pap_x[i].st != CR_PX_WAIT || g_pap_x[i].e.oid != oid) continue;
      if(g_pap_x[i].e.t_from <= M && M <= g_pap_x[i].e.t_to) return true;
     }
   return false;
  }

//+------------------------------------------------------------------+
//| Small helpers                                                    |
//+------------------------------------------------------------------+
bool FolReady(const int sl)
  {
   if(!BarsReady(g_sl[sl].sym)) return false;
   if(g_sl[sl].sym2 >= 0 && !BarsReady(g_sl[sl].sym2)) return false;
   return true;
  }

// the symbol ticked in minute m (UTC): its last tick lies in that minute, or later with a broker bar at m
bool FolTicked(const int sym, const datetime m)
  {
   double bid = 0.0, ask = 0.0;
   datetime t = 0;
   if(!BrkQuote(sym, bid, ask, t)) return false;
   datetime ms = ClkUtcToServer(m);
   if(t < ms) return false;
   if(t < ms + 60) return true;
   MqlRates r[];
   int n = CopyRates(g_sym[sym].name, PERIOD_M1, (datetime)ms, (datetime)ms, r);
   return n > 0 && r[0].time == ms;
  }

// the symbol ticked at or after minute m (UTC)
bool FolTickedFrom(const int sym, const datetime m)
  {
   double bid = 0.0, ask = 0.0;
   datetime t = 0;
   if(!BrkQuote(sym, bid, ask, t)) return false;
   return t >= ClkUtcToServer(m);
  }

// the open positions of a magic, oldest first (POSITION_TIME, then ticket)
int FolPositions(const long magic, ulong &tk[], datetime &tm[])
  {
   int n = 0;
   ArrayResize(tk, 0);
   ArrayResize(tm, 0);
   int total = PositionsTotal();
   for(int i = 0; i < total; i++)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0 || PositionGetInteger(POSITION_MAGIC) != magic) continue;
      datetime pt = (datetime)PositionGetInteger(POSITION_TIME);
      ArrayResize(tk, n + 1);
      ArrayResize(tm, n + 1);
      int j = n;
      while(j > 0 && (tm[j - 1] > pt || (tm[j - 1] == pt && tk[j - 1] > t)))
        {
         tk[j] = tk[j - 1];
         tm[j] = tm[j - 1];
         j--;
        }
      tk[j] = t;
      tm[j] = pt;
      n++;
     }
   return n;
  }

int FolPosSide()
  {
   return (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
  }

// the decision time encoded in an oid (SPEC 2.4: decision x 100 + sleeve id)
datetime FolDec(const long oid) { return (datetime)(oid / 100); }

// LatestExit of a position (SPEC 4.8 table, P9): from POSITION_TIME, the comment only as a cross-check, then the real
// exit minute with the gap rule (a NOT_READY sleeve closes before a known closure); 0 = unknown
datetime FolLatestExit(const int sl, const datetime open_srv, const string comment)
  {
   datetime o = ClkServerToUtc(open_srv);
   datetime cdec = BrkCommentDec(comment, g_sl[sl].code);
   datetime x = RulesLatestExit(sl, o, cdec);
   if(x <= 0) return 0;
   int s = g_sl[sl].sym;
   return ClkRealExitMinute(x, g_sym[s].family, true, BrkSessionEnd(s, x));
  }

//+------------------------------------------------------------------+
//| Closes, tried again until the position is gone                   |
//+------------------------------------------------------------------+
int FolClFind(const ulong ticket)
  {
   for(int k = 0; k < g_fol_ncl; k++)
      if(g_fol_cl[k].ticket == ticket) return k;
   return -1;
  }

bool FolClosing(const ulong ticket) { return FolClFind(ticket) >= 0; }

void FolClDrop(const int k)
  {
   for(int j = k + 1; j < g_fol_ncl; j++) g_fol_cl[j - 1] = g_fol_cl[j];
   g_fol_ncl--;
  }

bool FolClTry(const int k, const datetime now)
  {
   ulong t = g_fol_cl[k].ticket;
   int why = g_fol_cl[k].why;
   g_fol_cl[k].tries++;
   if(BrkClose(t, g_fol_cl[k].magic, CR_FW_NAME[why])) return true;
   bool shut = (g_brk_rc == TRADE_RETCODE_MARKET_CLOSED);
   g_fol_cl[k].next = now + (shut ? CR_FOL_RETRY_CLOSED : CR_FOL_RETRY);
   if(!g_fol_cl[k].warned)
     {
      int sl = CrSleeveOfMagic(g_fol_cl[k].magic);
      string code = (sl >= 0) ? g_sl[sl].code : "-";
      string cause = shut ? "marche ferme" : (BrkTradeAllowed() ? "refus du courtier" : "trading automatique desactive dans MT5");
      if(JrnPush("ATTENTION : la position " + IntegerToString((long)t) + " (" + code + ") devrait etre fermee (" + CR_FW_NAME[why]
                 + ") et ne l'est pas (" + cause + "), nouvel essai", true))
         g_fol_cl[k].warned = true;                           // dropped by the push limits: said at the next attempt
     }
   return false;
  }

// close a robot position for `why` now, then every 10 s (60 s while the market is closed) until it is gone; true when
// it was added to the list (the caller journals ORPHAN, DUP, SLFIX only then)
bool FolCloseReq(const ulong ticket, const long magic, const int why, const datetime now)
  {
   if(ticket == 0 || !GrdMaySend()) return false;
   int k = FolClFind(ticket);
   bool added = false;
   if(k < 0)
     {
      if(g_fol_ncl >= CR_FOL_CMAX)
        {
         JrnError("-", "more than 64 positions to close at once");
         return false;
        }
      k = g_fol_ncl;
      g_fol_cl[k].ticket = ticket;
      g_fol_cl[k].magic = magic;
      g_fol_cl[k].why = why;
      g_fol_cl[k].next = 0;
      g_fol_cl[k].tries = 0;
      g_fol_cl[k].warned = false;
      g_fol_ncl++;
      added = true;
     }
   if(now < g_fol_cl[k].next && (long)(g_fol_cl[k].next - now) <= 120) return added;   // (beyond 120 s: the clock stepped back)
   if(FolClTry(k, now)) FolClDrop(k);
   return added;
  }

void FolCloseRun(const datetime now)
  {
   for(int k = g_fol_ncl - 1; k >= 0; k--)
     {
      if(!PositionSelectByTicket(g_fol_cl[k].ticket))
        {
         FolClDrop(k);
         continue;
        }
      if(now < g_fol_cl[k].next && (long)(g_fol_cl[k].next - now) <= 120) continue;
      if(!GrdMaySend()) continue;
      if(FolClTry(k, now)) FolClDrop(k);
     }
  }

//+------------------------------------------------------------------+
//| Intents                                                          |
//+------------------------------------------------------------------+
void FolIntentNew(const int sl, const long oid, const int side, const int etype, const datetime stamp, const double fill,
                  const double stop, const double stop_dist)
  {
   CrIntent it;
   ZeroMemory(it);
   it.sleeve = sl;
   it.oid = oid;
   it.side = side;
   it.etype = etype;
   it.stamp = stamp;
   it.send_until = stamp + CR_FOL_WINDOW;
   it.paper_fill = fill;
   it.stop = stop;
   it.stop_dist = stop_dist;
   it.skip = CR_SK_NONE;
   it.state = CR_IS_WAIT;
   g_fol[sl].it = it;
   g_fol[sl].ist = CR_IS_WAIT;
   g_fol[sl].sized = false;
   g_fol[sl].it_next = 0;
   g_fol[sl].it_tries = 0;
   g_fol[sl].last_why = CR_SK_NONE;
   g_fol[sl].last_oid = oid;
   g_fol[sl].arm_oid = 0;
   g_fol_why[sl] = "";
  }

void FolMarketIntent(const int sl, const CrOrder &o, const datetime M)
  {
   bool abs_stop = PapOn(o.stop);
   FolIntentNew(sl, o.oid, o.side, CR_ET_MARKET, M, 0.0, abs_stop ? o.stop : 0.0, abs_stop ? 0.0 : o.stop_dist);
  }

void FolMissedTxt(const int sl, const long oid, const datetime stamp, const string reason, const bool dry)
  {
   JrnAt(dry ? stamp : ClkServerToUtc(TimeTradeServer()), CR_EV_MISSED, g_sl[sl].code,
         KI("oid", oid) + KT("stamp", stamp) + KV("reason", reason) + JrnRp(dry));
   if(!dry && !g_cfg.observer)
      JrnPush("MISSED " + g_sl[sl].code + " : trade " + IntegerToString(oid) + " non envoye (" + reason + ")", false);
  }

void FolMissed(const int sl, const long oid, const datetime stamp, const int reason, const bool dry)
  {
   if(reason == CR_SK_EXITED) SizWeekUnit(stamp);              // still the week's sizing event (SPEC 4.1, P5)
   FolMissedTxt(sl, oid, stamp, SizSkipName(reason), dry);
  }

// the 3-spread refusal of the paper (SPEC 2.5) on the live paper quote: the paper would refuse this market order at its fill
bool FolRefusedNow(const int sl, const CrOrder &o)
  {
   if(o.refuse == CR_REF_NONE) return false;
   int s = g_sl[sl].sym;
   double bid = 0.0, ask = 0.0;
   datetime t = 0;
   if(!BrkQuote(s, bid, ask, t)) return false;
   double pb = 0.0, pa = 0.0;
   BarsPaperQuotes(s, bid, ask, pb, pa);
   double sm = g_sym[s].slip_mkt;
   double fp = (o.side > 0) ? pa * (1 + sm) : pb * (1 - sm);
   double spread = pa - pb;
   if(o.refuse == CR_REF_PAYOFF)
     {
      double d0 = PapOn(o.stop) ? MathAbs(fp - o.stop) : o.stop_dist;
      return d0 < 3.0 * spread;
     }
   double st = PapOn(o.stop) ? o.stop : fp - o.side * o.stop_dist;
   bool wrong = (o.side > 0 && st >= fp) || (o.side < 0 && st <= fp);
   return MathAbs(fp - st) < 3.0 * spread || wrong;
  }

// the market order of the sleeve's paper queue that activates at minute M (SPEC 4.1); false when none
bool FolActivating(const int sl, const datetime M, CrOrder &o)
  {
   CrBar b;
   ZeroMemory(b);
   b.t = M;
   b.sym = g_sl[sl].sym;
   int st = 0;
   for(int k = 0; k < g_pap_qn[sl]; k++)
     {
      if(!FolQAt(sl, k, o, st) || st != CR_PO_WAIT || o.etype != CR_ET_MARKET) continue;
      if(!PapActivates(sl, o, b)) continue;
      if(o.void_le && o.x_sched > 0 && o.x_sched <= M) continue;   // void at activation (PVOID): no trade
      if(o.oid == g_fol[sl].last_oid) return false;               // decided already: the paper fills it on bar M
      if(FolRefusedNow(sl, o)) continue;                         // the paper refuses it (PREFUSE): the next one may fill
      return true;
     }
   return false;
  }

bool FolIntentActive(const int sl)
  {
   int st = g_fol[sl].ist;
   return st == CR_IS_WAIT || st == CR_IS_SENT || st == CR_IS_UNKNOWN;
  }

// the broker stop of an intent's order (SPEC 4.4): the paper trade's current stop once it is filled (a trail may have
// moved it since the fill), else from the order
double FolSendStop(const int sl, const CrIntent &it)
  {
   int s = g_sl[sl].sym;
   double h = g_sym[s].h;
   CrTrade t;
   ZeroMemory(t);
   if(PapTrade(sl, t) && t.oid == it.oid) return BrkGridStop(s, t.stop + t.side * h, t.side);
   if(it.etype == CR_ET_MARKET && it.stop == 0.0)
     {
      double qp = (it.quote + it.side * h) * (1.0 + it.side * g_sym[s].slip_mkt);
      return BrkGridStop(s, qp - it.side * it.stop_dist + it.side * h, it.side);
     }
   double st = (it.stop != 0.0) ? it.stop : it.paper_fill - it.side * it.stop_dist;
   return BrkGridStop(s, st + it.side * h, it.side);
  }

void FolAdopt(const int sl, const ulong ticket, const long oid, const datetime stamp, const string why)
  {
   if(!PositionSelectByTicket(ticket)) return;
   g_fol[sl].oid = oid;
   g_fol[sl].ticket = ticket;
   g_fol[sl].side = FolPosSide();
   g_fol[sl].stamp = stamp;
   g_fol[sl].sl_send = PositionGetDouble(POSITION_SL);
   g_fol[sl].t_open = (datetime)PositionGetInteger(POSITION_TIME);
   g_fol[sl].ist = CR_IS_OPEN;
   g_fol[sl].last_oid = oid;
   g_fol[sl].md_next = 0;
   g_fol[sl].arm_oid = 0;
   Jrn(CR_EV_ADOPT, g_sl[sl].code, KI("oid", oid) + KI("ticket", (long)ticket) + KT("open", ClkServerToUtc(g_fol[sl].t_open))
       + KT("stamp", stamp) + KV("why", why));
  }

// an intent whose order, deal or position already exists: take its position, else the trade is over
void FolIntentFound(const int sl, const ulong found, const string why, const datetime now)
  {
   ulong t = 0;
   if(found != 0 && PositionSelectByTicket(found) && PositionGetInteger(POSITION_MAGIC) == g_sl[sl].magic) t = found;
   if(t == 0)
     {
      ulong tk[];
      datetime tm[];
      int np = FolPositions(g_sl[sl].magic, tk, tm);
      datetime s_srv = ClkUtcToServer(g_fol[sl].it.stamp);
      for(int k = 0; k < np && t == 0; k++)
         if(tm[k] >= s_srv && !FolClosing(tk[k])) t = tk[k];
     }
   if(t != 0)
     {
      FolAdopt(sl, t, g_fol[sl].it.oid, g_fol[sl].it.stamp, why);
      return;
     }
   if(why == "order_pending" || why == "open_order")
     {
      g_fol[sl].ist = CR_IS_UNKNOWN;                           // an order may still make the position: wait
      g_fol[sl].it_next = now + 2;
      return;
     }
   g_fol[sl].oid = g_fol[sl].it.oid;
   g_fol[sl].ist = CR_IS_DONE;
   g_fol[sl].ticket = 0;
   if(found != 0 && !BrkPositionClosed((long)found))
     {
      // the history made the position but the terminal does not list it yet: it is followed, and taken as closed only
      // when it is still not listed 30 s later (FolMapPositions)
      g_fol[sl].ticket = found;
      g_fol[sl].side = g_fol[sl].it.side;
      g_fol[sl].stamp = g_fol[sl].it.stamp;
      g_fol[sl].sl_send = 0.0;
      g_fol[sl].t_open = now;
      g_fol[sl].ist = CR_IS_OPEN;
      Jrn(CR_EV_ADOPT, g_sl[sl].code, KI("oid", g_fol[sl].it.oid) + KI("ticket", (long)found) + KT("stamp", g_fol[sl].it.stamp)
          + KV("why", why) + KB("listed", false));
     }                                                         // else opened and closed already: busy until the paper exits
  }

bool FolBefore(const int a, const int b)
  {
   if(g_fol[a].it.stamp != g_fol[b].it.stamp) return g_fol[a].it.stamp < g_fol[b].it.stamp;
   return CrStrCmp(g_sl[a].lab, g_sl[b].lab) < 0;
  }

int FolSendGap(const int tries)
  {
   int g = 1;
   for(int k = 0; k < tries && g < CR_FOL_SEND_MAX; k++) g = g * 2;
   if(g > CR_FOL_SEND_MAX) g = CR_FOL_SEND_MAX;
   return g;
  }

// a broker refusal worth trying again inside the window
bool FolTransient(const string why, const uint rc)
  {
   if(why == "no_connection" || why == "no_price" || why == "old_price" || why == "algo_trading_off" || why == "lock") return true;
   if(why != "refused") return false;
   return rc != TRADE_RETCODE_INVALID_STOPS && rc != TRADE_RETCODE_NO_MONEY && rc != 10014 && rc != 10017;   // volume, trade disabled
  }

// one step of a waiting intent (SPEC 4.1-4.3)
void FolIntentStep(const int sl, const datetime now)
  {
   datetime nu = ClkServerToUtc(now);
   long magic = g_sl[sl].magic;
   int s = g_sl[sl].sym;
   if(nu >= g_fol[sl].it.send_until)
     {
      g_fol[sl].ist = CR_IS_MISSED;
      if(g_fol_why[sl] != "") FolMissedTxt(sl, g_fol[sl].it.oid, g_fol[sl].it.stamp, g_fol_why[sl], false);
      else FolMissed(sl, g_fol[sl].it.oid, g_fol[sl].it.stamp, (g_fol[sl].last_why != CR_SK_NONE) ? g_fol[sl].last_why : CR_SK_LATE, false);
      return;
     }
   if(now < g_fol[sl].it_next && (long)(g_fol[sl].it_next - now) <= 120) return;
   // the paper trade behind the intent ended before it was sent: nothing to send (P5)
   CrTrade t;
   ZeroMemory(t);
   bool open = PapTrade(sl, t);
   if(!(open && t.oid == g_fol[sl].it.oid) && !FolOrderWaiting(sl, g_fol[sl].it.oid) && g_fol[sl].ist == CR_IS_WAIT)
     {
      g_fol[sl].ist = CR_IS_MISSED;
      FolMissed(sl, g_fol[sl].it.oid, g_fol[sl].it.stamp, CR_SK_EXITED, false);
      return;
     }
   if(g_fol[sl].ist == CR_IS_UNKNOWN)
     {
      // after an unknown result: connected, ledger settled, two stable reads, then the history decides (R5)
      g_fol[sl].last_why = CR_SK_SETTLE;
      g_fol_why[sl] = "unknown_result";
      if(!BrkConnected() || LedRead(now) != CR_LED_OK || !BrkStableRead(now))
        {
         g_fol[sl].it_next = now + 1;
         return;
        }
      ulong prev0 = 0, found0 = 0;
      string why0 = "";
      int c0 = BrkIntentCheck(magic, g_fol[sl].it.stamp, prev0, found0, why0);
      if(c0 < 0)
        {
         g_fol[sl].it_next = now + 1;
         return;
        }
      if(c0 == 2)
        {
         FolIntentFound(sl, found0, why0, now);
         return;
        }
      g_fol[sl].ist = CR_IS_WAIT;                              // nothing was made: the request may go again
      g_fol_why[sl] = "";
     }
   if(!g_fol[sl].sized)
     {
      int pre = CR_SK_NONE;
      if(!g_sl[sl].allowed) pre = CR_SK_NOTALLOWED;
      else
        {
         // the lab's order (SPEC 5): STOPPED, GUARD, LOCK, FRIDAY, CLOCK, NOTREADY, then the EA's own: SELFTEST, NOTRADE
         pre = GrdEntryBlock(now);
         bool hard = (pre == CR_SK_STOPPED || pre == CR_SK_GUARD || pre == CR_SK_LOCK || pre == CR_SK_FRIDAY || pre == CR_SK_CLOCK);
         if(!hard && (!FolReady(sl) || g_fol[sl].rec_due)) pre = CR_SK_NOTREADY;
        }
      double bid = 0.0, ask = 0.0;
      datetime tq = 0;
      bool q = BrkQuote(s, bid, ask, tq);
      g_fol[sl].it.quote = q ? ((g_fol[sl].it.side > 0) ? ask : bid) : 0.0;
      if(!q && pre == CR_SK_NONE)
        {
         g_fol[sl].last_why = CR_SK_NOTREADY;
         g_fol[sl].it_next = now + 1;
         return;
        }
      g_fol[sl].it.skip = pre;
      int sk = SizSize(g_fol[sl].it, g_fol[sl].it.stamp, false);
      if(sk == CR_SK_SETTLE)
        {
         g_fol[sl].last_why = CR_SK_SETTLE;
         g_fol_why[sl] = "";
         g_fol[sl].it_next = now + 1;
         return;
        }
      if(sk != CR_SK_NONE)
        {
         g_fol[sl].ist = CR_IS_DONE;                           // skipped: the sleeve stays busy until its paper trade ends
         return;
        }
      g_fol[sl].sized = true;
     }
   // one intent, one trade (R5)
   ulong prev = 0, found = 0;
   string why = "";
   int c = BrkIntentCheck(magic, g_fol[sl].it.stamp, prev, found, why);
   if(c < 0)
     {
      g_fol[sl].it_next = now + 1;
      return;
     }
   if(c == 2)
     {
      FolIntentFound(sl, found, why, now);
      return;
     }
   if(c == 1)
     {
      g_fol[sl].last_why = CR_SK_PREV_OPEN;                    // the previous trade's position goes first
      g_fol_why[sl] = "";
      FolCloseReq(prev, magic, CR_FW_PREV, now);
      g_fol[sl].it_next = now + 1;
      return;
     }
   double bid2 = 0.0, ask2 = 0.0;
   datetime tq2 = 0;
   if(BrkQuote(s, bid2, ask2, tq2)) g_fol[sl].it.quote = (g_fol[sl].it.side > 0) ? ask2 : bid2;
   double sl_px = FolSendStop(sl, g_fol[sl].it);
   int r = BrkOpen(g_fol[sl].it, sl_px);
   if(r == CR_SEND_OK)
     {
      g_fol[sl].oid = g_fol[sl].it.oid;
      g_fol[sl].ticket = g_fol[sl].it.ticket;
      g_fol[sl].side = g_fol[sl].it.side;
      g_fol[sl].stamp = g_fol[sl].it.stamp;
      g_fol[sl].sl_send = sl_px;
      g_fol[sl].t_open = now;
      g_fol[sl].md_next = 0;
      g_fol[sl].ist = CR_IS_OPEN;
      if(g_brk_refused)                                        // REFUSED (journaled by the broker): busy until the paper exits
        {
         FolCloseReq(g_fol[sl].it.ticket, magic, CR_FW_REFUSED, now);
         g_fol[sl].ticket = 0;
         g_fol[sl].ist = CR_IS_DONE;
        }
      return;
     }
   if(r == CR_SEND_UNKNOWN)
     {
      g_fol[sl].ist = CR_IS_UNKNOWN;
      g_fol[sl].it_next = now + 2;
      return;
     }
   if(g_brk_why == "stop_side")                                // the price already crossed the stop: the trade would end at once
     {
      g_fol[sl].ist = CR_IS_MISSED;
      FolMissed(sl, g_fol[sl].it.oid, g_fol[sl].it.stamp, CR_SK_EXITED, false);
      return;
     }
   if(FolTransient(g_brk_why, g_brk_rc))
     {
      g_fol_why[sl] = (g_brk_why == "refused") ? "refused_" + IntegerToString((long)g_brk_rc) : g_brk_why;
      if(g_brk_why != "refused")
        {
         g_fol[sl].it_next = now + 1;                          // a check before any request (no fresh tick, no connection):
         return;                                               // free to try again at every pass
        }
      g_fol[sl].it_next = now + FolSendGap(g_fol[sl].it_tries);   // a broker refusal: 1, 2, 4 ... 30 s
      g_fol[sl].it_tries++;
      return;
     }
   g_fol[sl].ist = CR_IS_MISSED;
   Jrn(CR_EV_REFUSED, g_sl[sl].code, KI("oid", g_fol[sl].it.oid) + KV("why", g_brk_why) + KI("rc", (long)g_brk_rc) + KB("final", true));
   Jrn(CR_EV_MISSED, g_sl[sl].code, KI("oid", g_fol[sl].it.oid) + KT("stamp", g_fol[sl].it.stamp) + KV("reason", "refused")
       + KI("rc", (long)g_brk_rc));
   JrnPush("REFUSED " + g_sl[sl].code + " : ordre " + IntegerToString(g_fol[sl].it.oid) + " refuse (" + g_brk_why + ")", true);
  }

void FolIntents(const datetime now)
  {
   int ord[CR_MAX_SL];
   int n = 0;
   for(int sl = 0; sl < g_nsl && sl < CR_MAX_SL; sl++)
      if(g_fol[sl].ist == CR_IS_WAIT || g_fol[sl].ist == CR_IS_UNKNOWN)
        {
         ord[n] = sl;
         n++;
        }
   for(int a = 1; a < n; a++)                                  // by (stamp, lab sleeve name in byte order): stake.py:108
     {
      int x = ord[a];
      int b = a;
      while(b > 0 && FolBefore(x, ord[b - 1]))
        {
         ord[b] = ord[b - 1];
         b--;
        }
      ord[b] = x;
     }
   for(int k = 0; k < n; k++) FolIntentStep(ord[k], now);
  }

//+------------------------------------------------------------------+
//| Stops and the broker-stop invariant (SPEC 4.4, R4)               |
//+------------------------------------------------------------------+
// the stop the followed position of a sleeve must carry; false when unknown
bool FolExpectedStop(const int sl, double &ex)
  {
   ex = 0.0;
   if(g_fol[sl].oid == 0) return false;
   CrTrade t;
   ZeroMemory(t);
   if(PapTrade(sl, t) && t.oid == g_fol[sl].oid)
     {
      int s = g_sl[sl].sym;
      ex = BrkGridStop(s, t.stop + t.side * g_sym[s].h, t.side);
      return true;
     }
   if(FolOrderWaiting(sl, g_fol[sl].oid) && g_fol[sl].sl_send > 0.0)
     {
      ex = g_fol[sl].sl_send;                                  // its paper fill is not processed yet
      return true;
     }
   return false;
  }

void FolSlfix(const int sl, const ulong t, const long m, const string why, const datetime now)
  {
   if(FolCloseReq(t, m, CR_FW_SLFIX, now))
     {
      string code = (sl >= 0) ? g_sl[sl].code : "-";
      Jrn(CR_EV_SLFIX, code, KI("ticket", (long)t) + KV("why", why));
      JrnPush("SLFIX " + code + " : position " + IntegerToString((long)t) + " sans stop chez le courtier, fermee (" + why + ")", true);
     }
  }

void FolInvariant(const datetime now)
  {
   if(!GrdMaySend()) return;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      long m = PositionGetInteger(POSITION_MAGIC);
      if(!BrkRobotMagic(m) || FolClosing(t)) continue;
      int side = FolPosSide();
      double cur = PositionGetDouble(POSITION_SL);
      datetime opened = (datetime)PositionGetInteger(POSITION_TIME);
      string nm = PositionGetString(POSITION_SYMBOL);
      int sl = CrSleeveOfMagic(m);
      int s = BrkSymOf(nm);
      if(sl < 0 || s < 0) continue;                            // reconcile closes positions of no sleeve
      double ex = 0.0;
      bool known = (g_fol[sl].ticket == t && !g_fol[sl].rec_due && FolReady(sl) && FolExpectedStop(sl, ex));
      double bid = 0.0, ask = 0.0;
      datetime tq = 0;
      bool q = BrkQuote(s, bid, ask, tq);
      bool crossed = known && q && ((side > 0 && ex >= bid) || (side < 0 && ex <= ask));
      if(!(cur > 0.0))
        {
         if((long)(now - opened) < CR_FOL_NOSL) continue;     // the broker may show it a moment later
         if(known && !crossed && BrkModify(t, ex)) continue;
         FolSlfix(sl, t, m, known ? (crossed ? "crossed" : "refused") : "no_expected_stop", now);
         continue;
        }
      if(!known) continue;
      double pt = g_sym[s].point;
      if(!(pt > 0.0)) pt = 0.01;
      if(MathAbs(cur - ex) < pt / 2) continue;
      if(crossed)
        {
         if(FolCloseReq(t, m, CR_FW_CROSSED, now))
            Jrn(CR_EV_SLMOD, g_sl[sl].code, KI("ticket", (long)t) + KD("from", cur) + KD("to", ex) + KV("why", "crossed_close"));
         continue;
        }
      if(now < g_fol[sl].md_next && (long)(g_fol[sl].md_next - now) <= 120) continue;
      if(!BrkModify(t, ex) && !g_brk_gone) g_fol[sl].md_next = now + CR_FOL_RETRY;   // the old stop stays; again in 10 s
     }
  }

//+------------------------------------------------------------------+
//| The live barrier                                                 |
//+------------------------------------------------------------------+
// the sleeve's positions: the followed one, an intent's position listed late, the others (DUP, ORPHAN)
void FolMapPositions(const int sl, const datetime now)
  {
   long magic = g_sl[sl].magic;
   ulong tk[];
   datetime tm[];
   int np = FolPositions(magic, tk, tm);
   int keep = -1;
   if(g_fol[sl].ticket != 0)
     {
      for(int k = 0; k < np; k++)
         if(tk[k] == g_fol[sl].ticket) keep = k;
      if(keep < 0 && (long)(now - g_fol[sl].t_open) >= CR_FOL_LISTING) g_fol[sl].ticket = 0;   // closed (stop, forced close)
     }
   if(keep < 0 && g_fol[sl].ticket == 0 && (g_fol[sl].ist == CR_IS_UNKNOWN || g_fol[sl].ist == CR_IS_OPEN))
     {
      datetime s_srv = ClkUtcToServer(g_fol[sl].it.stamp);
      for(int k = 0; k < np && keep < 0; k++)
         if(tm[k] >= s_srv && !FolClosing(tk[k])) keep = k;
      if(keep >= 0) FolAdopt(sl, tk[keep], g_fol[sl].it.oid, g_fol[sl].it.stamp, "listed_late");
     }
   if(g_fol[sl].ticket != 0 && keep < 0) return;               // the fill is not listed yet: decide nothing about the others
   for(int k = 0; k < np; k++)
     {
      if(k == keep || FolClosing(tk[k])) continue;
      if(keep >= 0 && tm[k] >= tm[keep])
        {
         if(FolCloseReq(tk[k], magic, CR_FW_DUP, now))
           {
            Jrn(CR_EV_DUP, g_sl[sl].code, KI("ticket", (long)tk[k]) + KI("kept", (long)tk[keep]));
            JrnPush("DUP " + g_sl[sl].code + " : position en double " + IntegerToString((long)tk[k]) + " fermee", true);
           }
        }
      else if(FolCloseReq(tk[k], magic, CR_FW_ORPHAN, now))
        {
         Jrn(CR_EV_ORPHAN, g_sl[sl].code, KI("ticket", (long)tk[k]) + KV("why", "no_paper_trade"));
         JrnPush("ORPHAN " + g_sl[sl].code + " : position " + IntegerToString((long)tk[k]) + " fermee (aucun trade papier ne la porte)", true);
        }
     }
  }

void FolSleeveMinute(const int sl, const datetime M, const datetime now)
  {
   int s = g_sl[sl].sym;
   long magic = g_sl[sl].magic;
   bool ready = FolReady(sl) && !g_fol[sl].rec_due;
   CrTrade t;
   ZeroMemory(t);
   bool open = PapTrade(sl, t);
   // 1. a paper fill: a stop, limit or OCO intent (SPEC 4.1), or a market fill whose activation was not seen
   if(g_fol[sl].ev_fill)
     {
      CrPEvent e = g_fol[sl].fill;
      if(e.oid != g_fol[sl].last_oid && e.oid != g_fol[sl].oid)
        {
         CrOrder o;
         ZeroMemory(o);
         bool have = FolOrderOf(sl, e.oid, o);
         int et = have ? o.etype : CR_ET_MARKET;
         bool alive = open && t.oid == e.oid && !g_fol[sl].ev_end;
         g_fol[sl].last_oid = e.oid;
         if(!alive) FolMissed(sl, e.oid, e.bar, CR_SK_EXITED, false);
         else if(et == CR_ET_MARKET) FolIntentNew(sl, e.oid, e.side, CR_ET_MARKET, e.bar, 0.0, e.init_stop, 0.0);
         else FolIntentNew(sl, e.oid, e.side, et, e.bar, e.px, e.init_stop, 0.0);
        }
     }
   if(!ready || !GrdMaySend()) return;                         // a NOT_READY sleeve keeps its positions (FolNotReadyExits)
   // 2. the positions of the magic
   FolMapPositions(sl, now);
   // 3. the followed position against the paper (SPEC 4.5)
   ulong tk = g_fol[sl].ticket;
   if(tk != 0 && PositionSelectByTicket(tk) && !FolClosing(tk))
     {
      long X = g_fol[sl].oid;
      bool trade_x = open && t.oid == X;
      if(!trade_x && !FolOrderWaiting(sl, X))
        {
         int why = (g_fol[sl].end_oid == X) ? g_fol[sl].end_why : CR_FW_PAPER;
         FolCloseReq(tk, magic, why, now);                     // the paper trade ended
        }
      else if(trade_x)
        {
         if(t.x_sched > 0)
           {
            datetime rx = ClkRealExitMinute(t.x_sched, g_sym[s].family, t.x_gap, BrkSessionEnd(s, t.x_sched));
            if(M >= rx)
              {
               if(rx < t.x_sched || FolTickedFrom(s, t.x_sched)) FolCloseReq(tk, magic, CR_FW_TIME, now);
               else
                 {
                  g_fol[sl].xarm = true;                       // the paper's exit bar is the first bar at or after x
                  g_fol[sl].xarm_t = t.x_sched;
                  g_fol[sl].xarm_why = CR_FW_TIME;
                 }
              }
           }
         if(!FolClosing(tk) && FolExitDue(sl, X, M))
           {
            if(FolTicked(s, M)) FolCloseReq(tk, magic, CR_FW_RULE, now);
            else
              {
               g_fol[sl].xarm = true;
               g_fol[sl].xarm_t = M;
               g_fol[sl].xarm_why = CR_FW_RULE;
              }
           }
        }
     }
   // 4. a market order activating at M
   if(!open && !FolIntentActive(sl))
     {
      CrOrder o;
      ZeroMemory(o);
      if(FolActivating(sl, M, o))
        {
         if(FolTicked(s, M)) FolMarketIntent(sl, o, M);
         else
           {
            g_fol[sl].arm_oid = o.oid;                         // the first tick of minute M makes the intent
            g_fol[sl].arm_M = M;
           }
        }
     }
  }

void FolClearEvents()
  {
   for(int sl = 0; sl < CR_MAX_SL; sl++)
     {
      g_fol[sl].ev_fill = false;
      g_fol[sl].ev_end = false;
     }
  }

//+------------------------------------------------------------------+
//| The replay: dry sizing (SPEC 4.8 c)                              |
//+------------------------------------------------------------------+
void FolDryFill(const int sl)
  {
   CrPEvent e = g_fol[sl].fill;
   CrOrder o;
   ZeroMemory(o);
   bool have = FolOrderOf(sl, e.oid, o);
   int et = have ? o.etype : CR_ET_MARKET;
   g_fol[sl].dry_oid = e.oid;
   if(et != CR_ET_MARKET && g_fol[sl].ev_end)
     {
      g_fol[sl].dry_skip = CR_SK_EXITED;
      FolMissed(sl, e.oid, e.bar, CR_SK_EXITED, true);
      return;
     }
   int s = g_sl[sl].sym;
   double sm = g_sym[s].slip_mkt, h = g_sym[s].h;
   CrIntent it;
   ZeroMemory(it);
   it.sleeve = sl;
   it.oid = e.oid;
   it.side = e.side;
   it.etype = et;
   it.stamp = e.bar;
   it.send_until = e.bar + CR_FOL_WINDOW;
   it.quote = (e.side > 0) ? e.px / (1.0 + sm) - h : e.px / (1.0 - sm) + h;   // the raw quote of the paper's fill
   if(et == CR_ET_MARKET)
     {
      bool abs_stop = have && PapOn(o.stop);
      it.stop = abs_stop ? o.stop : (have ? 0.0 : e.init_stop);
      it.stop_dist = (have && !abs_stop) ? o.stop_dist : 0.0;
     }
   else
     {
      it.paper_fill = e.px;
      it.stop = e.init_stop;
     }
   it.skip = g_sl[sl].allowed ? CR_SK_NONE : CR_SK_NOTALLOWED;
   SizSize(it, e.bar, true);
   g_fol[sl].dry_skip = it.skip;
  }

void FolDryMinute(const datetime M)
  {
   int ord[CR_MAX_SL];
   int n = 0;
   for(int sl = 0; sl < g_nsl && sl < CR_MAX_SL; sl++)
      if(g_fol[sl].ev_fill)
        {
         ord[n] = sl;
         n++;
        }
   for(int a = 1; a < n; a++)
     {
      int x = ord[a];
      int b = a;
      while(b > 0 && (g_fol[x].fill.bar < g_fol[ord[b - 1]].fill.bar
                      || (g_fol[x].fill.bar == g_fol[ord[b - 1]].fill.bar && CrStrCmp(g_sl[x].lab, g_sl[ord[b - 1]].lab) < 0)))
        {
         ord[b] = ord[b - 1];
         b--;
        }
      ord[b] = x;
     }
   for(int k = 0; k < n; k++) FolDryFill(ord[k]);
   FolClearEvents();
  }

//+------------------------------------------------------------------+
//| Reconcile (SPEC 4.8 d)                                           |
//+------------------------------------------------------------------+
bool FolListed(const long id)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetInteger(POSITION_IDENTIFIER) == id) return true;
     }
   return false;
  }

// every robot position the deal history holds open is listed (positions listed late after a restart)
bool FolListComplete()
  {
   int np = LedPosCount();
   CrLedPos p;
   for(int k = 0; k < np; k++)
     {
      if(!LedPosAt(k, p) || !p.robot || p.closed || p.side == 0) continue;
      if(!FolListed(p.id)) return false;
     }
   return true;
  }

// the history holds a position of the sleeve opened within 5 min of stamp and closed since
bool FolHistoryClosed(const int sl, const datetime stamp)
  {
   int np = LedPosCount();
   CrLedPos p;
   for(int k = 0; k < np; k++)
     {
      if(!LedPosAt(k, p) || !p.robot || p.magic != g_sl[sl].magic || !p.closed || p.side == 0) continue;
      if(MathAbs((long)(p.t_in - stamp)) <= CR_FOL_ADOPT) return true;
     }
   return false;
  }

// a market order of the paper queue, still waiting, of that side, whose window holds the minute of `open_utc`
bool FolWaitingFor(const int sl, const datetime open_utc, const int side, CrOrder &o)
  {
   datetime m = open_utc - open_utc % 60;
   int st = 0;
   for(int k = 0; k < g_pap_qn[sl]; k++)
     {
      if(!FolQAt(sl, k, o, st) || st != CR_PO_WAIT || o.etype != CR_ET_MARKET || o.side != side) continue;
      if(o.t_from <= m && m <= o.t_to) return true;
     }
   return false;
  }

void FolRecSleeve(const int sl, const datetime now)
  {
   g_fol[sl].rec_due = false;
   long magic = g_sl[sl].magic;
   CrTrade t;
   ZeroMemory(t);
   bool open = PapTrade(sl, t);
   ulong tk[];
   datetime tm[];
   int np = FolPositions(magic, tk, tm);
   int keep = -1;
   for(int k = 0; k < np; k++)
     {
      if(FolClosing(tk[k]) || !PositionSelectByTicket(tk[k])) continue;
      int side = FolPosSide();
      datetime ou = ClkServerToUtc(tm[k]);
      if(keep < 0 && open && side == t.side && MathAbs((long)(ou - t.fill_bar)) <= CR_FOL_ADOPT)
        {
         keep = k;
         FolAdopt(sl, tk[k], t.oid, t.fill_bar, "reconcile");
         continue;
        }
      CrOrder o;
      ZeroMemory(o);
      if(keep < 0 && !open && FolWaitingFor(sl, ou, side, o))
        {
         keep = k;
         FolAdopt(sl, tk[k], o.oid, ou - ou % 60, "reconcile_waiting");
         continue;
        }
      if(keep >= 0)
        {
         if(FolCloseReq(tk[k], magic, CR_FW_DUP, now))
           {
            Jrn(CR_EV_DUP, g_sl[sl].code, KI("ticket", (long)tk[k]) + KI("kept", (long)tk[keep]) + KV("at", "reconcile"));
            JrnPush("DUP " + g_sl[sl].code + " : position en double " + IntegerToString((long)tk[k]) + " fermee", true);
           }
        }
      else if(FolCloseReq(tk[k], magic, CR_FW_ORPHAN, now))
        {
         Jrn(CR_EV_ORPHAN, g_sl[sl].code, KI("ticket", (long)tk[k]) + KV("why", open ? "not_the_paper_trade" : "no_paper_trade")
             + KV("at", "reconcile"));
         JrnPush("ORPHAN " + g_sl[sl].code + " : position " + IntegerToString((long)tk[k]) + " fermee (aucun trade papier ne la porte)", true);
        }
     }
   if(!open || keep >= 0) return;
   // a paper trade without position
   g_fol[sl].last_oid = t.oid;
   if(FolHistoryClosed(sl, t.fill_bar))
     {
      g_fol[sl].oid = t.oid;                                   // its position closed already (its stop): busy until the paper exits
      g_fol[sl].ticket = 0;
      g_fol[sl].ist = CR_IS_DONE;
      return;
     }
   if(ClkServerToUtc(now) < t.fill_bar + CR_FOL_WINDOW)
     {
      if(t.etype == CR_ET_MARKET) FolIntentNew(sl, t.oid, t.side, CR_ET_MARKET, t.fill_bar, 0.0, t.init_stop, 0.0);
      else FolIntentNew(sl, t.oid, t.side, t.etype, t.fill_bar, t.fill_px, t.init_stop, 0.0);
      return;
     }
   int why = (g_fol[sl].dry_oid == t.oid && g_fol[sl].dry_skip != CR_SK_NONE) ? g_fol[sl].dry_skip : CR_SK_LATE;
   g_fol[sl].ist = CR_IS_MISSED;
   FolMissed(sl, t.oid, t.fill_bar, why, false);
  }

bool FolReconcile(const datetime now_srv)
  {
   if(!BrkConnected()) return false;
   if(LedRead(now_srv) != CR_LED_OK) return false;
   if(!BrkStableRead(now_srv)) return false;
   if(g_fol_rec_t0 == 0 || now_srv < g_fol_rec_t0) g_fol_rec_t0 = now_srv;
   if(!FolListComplete())
     {
      if((long)(now_srv - g_fol_rec_t0) < CR_FOL_LIST_WAIT) return false;
      Jrn(CR_EV_ERROR, "-", KV("what", "positions of the history still not listed after 60 s: reconcile goes on"));
     }
   g_fol_rec_t0 = 0;
   // positions of no sleeve (retired ids) and marks left open
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      long m = PositionGetInteger(POSITION_MAGIC);
      if(m == CR_MAGIC_MARK)
        {
         FolCloseReq(t, m, CR_FW_MARK, now_srv);
         continue;
        }
      if(!BrkRobotMagic(m) || CrSleeveOfMagic(m) >= 0) continue;
      if(FolCloseReq(t, m, CR_FW_ORPHAN, now_srv))
        {
         Jrn(CR_EV_ORPHAN, "-", KI("ticket", (long)t) + KI("magic", m) + KV("why", "no_sleeve") + KV("at", "reconcile"));
         JrnPush("ORPHAN : position " + IntegerToString((long)t) + " (magic " + IntegerToString(m) + ", aucune regle) fermee", true);
        }
     }
   for(int sl = 0; sl < g_nsl && sl < CR_MAX_SL; sl++)
     {
      g_fol[sl].rec_due = true;
      g_fol[sl].ready = FolReady(sl);
      if(g_fol[sl].ready) FolRecSleeve(sl, now_srv);
     }
   return true;
  }

//+------------------------------------------------------------------+
//| Timer: armed entries and exits, NOT_READY exits, WATCH           |
//+------------------------------------------------------------------+
void FolArmed(const int sl, const datetime now)
  {
   int s = g_sl[sl].sym;
   if(g_fol[sl].arm_oid != 0)
     {
      datetime M = g_fol[sl].arm_M;
      CrTrade t;
      ZeroMemory(t);
      CrOrder o;
      ZeroMemory(o);
      if(M != g_fol_M) g_fol[sl].arm_oid = 0;                  // its barrier is gone: the next one decides again
      else if(!PapTrade(sl, t) && !FolIntentActive(sl) && FolActivating(sl, M, o) && o.oid == g_fol[sl].arm_oid && FolTicked(s, M))
         FolMarketIntent(sl, o, M);                            // sent by FolIntents in the same pass
     }
   if(g_fol[sl].xarm)
     {
      ulong tk = g_fol[sl].ticket;
      if(tk == 0 || !PositionSelectByTicket(tk) || FolClosing(tk)) g_fol[sl].xarm = false;
      else if(FolTickedFrom(s, g_fol[sl].xarm_t))
        {
         g_fol[sl].xarm = false;
         FolCloseReq(tk, g_sl[sl].magic, g_fol[sl].xarm_why, now);
        }
     }
  }

// positions of NOT_READY sleeves keep their stops and close at LatestExit(POSITION_TIME, comment) (SPEC 4.8, P9)
void FolNotReadyExits(const datetime now)
  {
   if(!GrdMaySend()) return;
   datetime nu = ClkServerToUtc(now);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      long m = PositionGetInteger(POSITION_MAGIC);
      int sl = CrSleeveOfMagic(m);
      if(sl < 0 || !BrkRobotMagic(m) || FolClosing(t)) continue;
      if(FolReady(sl) && !g_fol[sl].rec_due) continue;
      datetime opened = (datetime)PositionGetInteger(POSITION_TIME);
      string cm = PositionGetString(POSITION_COMMENT);
      datetime x = FolLatestExit(sl, opened, cm);
      if(x > 0 && nu >= x) FolCloseReq(t, m, CR_FW_LATEST, now);
     }
  }

bool FolWatched(const ulong t)
  {
   for(int k = 0; k < g_fol_nwatch; k++)
      if(g_fol_watch[k] == t) return true;
   return false;
  }

// the observer copy (SPEC 4.9, R10): a robot position 5 min past its paper exit, or its LatestExit -> WATCH
void FolWatch(const datetime now)
  {
   datetime nu = ClkServerToUtc(now);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      long m = PositionGetInteger(POSITION_MAGIC);
      int sl = CrSleeveOfMagic(m);
      if(sl < 0 || !BrkRobotMagic(m) || FolWatched(t)) continue;
      int side = FolPosSide();
      datetime opened = (datetime)PositionGetInteger(POSITION_TIME);
      string cm = PositionGetString(POSITION_COMMENT);
      datetime ou = ClkServerToUtc(opened);
      CrTrade tr;
      ZeroMemory(tr);
      if(PapTrade(sl, tr) && tr.side == side && MathAbs((long)(ou - tr.fill_bar)) <= CR_FOL_ADOPT) continue;   // it follows the paper
      datetime due = 0;
      if(g_fol[sl].le_oid != 0 && g_fol[sl].le_oid == g_fol[sl].lf_oid && g_fol[sl].lf_side == side
         && MathAbs((long)(ou - g_fol[sl].lf_bar)) <= CR_FOL_ADOPT)
         due = g_fol[sl].le_t + CR_FOL_WATCH;
      else
        {
         datetime x = FolLatestExit(sl, opened, cm);
         if(x > 0) due = x + CR_FOL_WATCH;
        }
      if(due == 0 || nu <= due) continue;
      if(g_fol_nwatch < CR_FOL_WMAX)
        {
         g_fol_watch[g_fol_nwatch] = t;
         g_fol_nwatch++;
        }
      Jrn(CR_EV_WATCH, g_sl[sl].code, KI("ticket", (long)t) + KT("due", due) + KT("open", ou));
      JrnPush("WATCH " + g_sl[sl].code + " : la position " + IntegerToString((long)t)
              + " est encore ouverte apres sa sortie prevue (la copie du VPS est-elle arretee ?)", true);
     }
  }

//+------------------------------------------------------------------+
//| API                                                              |
//+------------------------------------------------------------------+
void FolResetAll()
  {
   for(int sl = 0; sl < CR_MAX_SL; sl++)
     {
      ZeroMemory(g_fol[sl]);
      g_fol_why[sl] = "";
      g_fol[sl].ist = CR_IS_DONE;
      g_fol[sl].end_why = CR_FW_PAPER;
      g_fol[sl].dry_skip = CR_SK_NONE;
     }
   g_fol_ncl = 0;
   g_fol_nwatch = 0;
   g_fol_M = 0;
   g_fol_rec_t0 = 0;
  }

bool FolInit(string &err)
  {
   err = "";
   FolResetAll();
   return true;
  }

void FolReset() { FolResetAll(); }

void FolOnPaperEvent(const CrPEvent &e, const bool live)
  {
   int sl = e.sleeve;
   if(sl < 0 || sl >= g_nsl || sl >= CR_MAX_SL) return;
   if(e.ev == CR_EV_PFILL)
     {
      g_fol[sl].ev_fill = true;
      g_fol[sl].fill = e;
      g_fol[sl].ev_end = false;
      g_fol[sl].lf_oid = e.oid;
      g_fol[sl].lf_bar = e.bar;
      g_fol[sl].lf_side = e.side;
      return;
     }
   if(e.ev != CR_EV_PEXIT && e.ev != CR_EV_PREVISE && e.ev != CR_EV_PVOID && e.ev != CR_EV_PREFUSE) return;
   int why = CR_FW_PAPER;
   if(e.ev == CR_EV_PEXIT && e.reason == CR_R_TIME) why = CR_FW_TIME;
   if(e.ev == CR_EV_PREVISE) why = CR_FW_REVISE;
   if(e.ev == CR_EV_PVOID) why = CR_FW_VOID;
   if(e.ev == CR_EV_PREFUSE) why = CR_FW_PREFUSE;
   if(g_fol[sl].ev_fill && g_fol[sl].fill.oid == e.oid) g_fol[sl].ev_end = true;
   g_fol[sl].end_oid = e.oid;
   g_fol[sl].end_why = why;
   if(e.oid == g_fol[sl].lf_oid && e.ev != CR_EV_PREFUSE)
     {
      g_fol[sl].le_oid = e.oid;
      g_fol[sl].le_t = e.t;
     }
  }

void FolOnMinute(const datetime M, const bool live)
  {
   if(!live)
     {
      FolDryMinute(M);
      return;
     }
   datetime now = TimeTradeServer();
   g_fol_M = M;
   for(int sl = 0; sl < g_nsl && sl < CR_MAX_SL; sl++) FolSleeveMinute(sl, M, now);
   FolIntents(now);
   FolInvariant(now);
   FolClearEvents();
  }

void FolOnTimer(const datetime now_srv)
  {
   for(int sl = 0; sl < g_nsl && sl < CR_MAX_SL; sl++)
     {
      bool r = FolReady(sl);
      if(r && g_fol[sl].rec_due) FolRecSleeve(sl, now_srv);    // NOT_READY at reconcile, READY now
      g_fol[sl].ready = r;
     }
   for(int sl = 0; sl < g_nsl && sl < CR_MAX_SL; sl++) FolArmed(sl, now_srv);
   FolIntents(now_srv);
   FolCloseRun(now_srv);
   FolInvariant(now_srv);
   FolNotReadyExits(now_srv);
   if(g_cfg.observer) FolWatch(now_srv);
  }

void FolOnTransaction(const MqlTradeTransaction &trans) {}
#endif

// ==== end src/CR_Follower.mqh
// ==== begin src/CR_Golden.mqh
//+------------------------------------------------------------------+
//| CR_Golden.mqh - GENERATED by tools/gen_golden.py (step K): the    |
//| self-test vectors of SPEC 7 T10, each computed by the lab's own  |
//| code (zoneinfo, pont, us_holidays, trend.add_trading_days,       |
//| pandas BDay, ml/strategy.py, the brk72 orders, growth._pct,      |
//| pandas ewm and rolling). Do not edit by hand: run the generator. |
//|                                                                  |
//| GoldenCheck(why), called by CR_Main at OnInit after the build    |
//| constants check: false (and why) on the first vector the EA does |
//| not reproduce, which blocks trading (SELFTEST ok=0). Times are   |
//| compared exactly; doubles within 1e-12 relative (SPEC 7); the    |
//| rates of the risk tables exactly. The NYSE dates use the rules   |
//| (ClkHolKind), so a typed InpExtraClosures entry cannot fail it.  |
//| The risk tables go through SizParseTable and LedRate; the live   |
//| table (InpRiskTable) is put back afterwards.                     |
//+------------------------------------------------------------------+
#ifndef CR_GOLDEN_MQH
#define CR_GOLDEN_MQH
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Clock.mqh)
// (already inlined: CR_Journal.mqh)
// (already inlined: CR_Math.mqh)
// (already inlined: CR_Ledger.mqh)
// (already inlined: CR_Sizing.mqh)
// (already inlined: CR_Rule_Brk72.mqh)
// (already inlined: CR_Rule_F1.mqh)
// (already inlined: CR_Rule_Orb.mqh)
#define CR_GOLDEN_N 322                // vectors checked (SELFTEST golden=)
#define CR_GOLD_REL 1e-12               // doubles: relative tolerance (SPEC 7)
#define CR_GOLD_NCLK 60
#define CR_GOLD_NNYSE 40
#define CR_GOLD_NATD 20
#define CR_GOLD_NBDAY 20
#define CR_GOLD_NORX 10
#define CR_GOLD_NF1 30
#define CR_GOLD_NRBP 10
#define CR_GOLD_NRISK 3
#define CR_GOLD_NKEY 11
#define CR_GOLD_NSER 48

// clock: utc, server, New York, London, server -> utc (pont), US summer time, UK summer time (7 per row)
long CR_GOLD_CLK[] = {
   1331449199, 1331456399, 1331431199, 1331449199, 1331449199, 0, 0,
   1331449200, 1331460000, 1331434800, 1331449200, 1331449200, 1, 0,
   1332637199, 1332647999, 1332622799, 1332637199, 1332637199, 1, 0,
   1332637200, 1332648000, 1332622800, 1332640800, 1332637200, 1, 1,
   1351385999, 1351396799, 1351371599, 1351389599, 1351385999, 1, 1,
   1351386000, 1351396800, 1351371600, 1351386000, 1351386000, 1, 0,
   1352008799, 1352019599, 1351994399, 1352008799, 1352008799, 1, 0,
   1352008800, 1352016000, 1351990800, 1352008800, 1352005200, 0, 0,
   1356998400, 1357005600, 1356980400, 1356998400, 1356998400, 0, 0,
   1363201200, 1363212000, 1363186800, 1363201200, 1363201200, 1, 0,
   1383231600, 1383242400, 1383217200, 1383231600, 1383231600, 1, 0,
   1457852399, 1457859599, 1457834399, 1457852399, 1457852399, 0, 0,
   1457852400, 1457863200, 1457838000, 1457852400, 1457852400, 1, 0,
   1459040399, 1459051199, 1459025999, 1459040399, 1459040399, 1, 0,
   1459040400, 1459051200, 1459026000, 1459044000, 1459040400, 1, 1,
   1477789199, 1477799999, 1477774799, 1477792799, 1477789199, 1, 1,
   1477789200, 1477800000, 1477774800, 1477789200, 1477789200, 1, 0,
   1478411999, 1478422799, 1478397599, 1478411999, 1478411999, 1, 0,
   1478412000, 1478419200, 1478394000, 1478412000, 1478408400, 0, 0,
   1514757599, 1514764799, 1514739599, 1514757599, 1514757599, 0, 0,
   1529069400, 1529080200, 1529055000, 1529073000, 1529069400, 1, 1,
   1552503600, 1552514400, 1552489200, 1552503600, 1552503600, 1, 0,
   1572534000, 1572544800, 1572519600, 1572534000, 1572534000, 1, 0,
   1583017200, 1583024400, 1582999200, 1583017200, 1583017200, 0, 0,
   1583650799, 1583657999, 1583632799, 1583650799, 1583650799, 0, 0,
   1583650800, 1583661600, 1583636400, 1583650800, 1583650800, 1, 0,
   1585443599, 1585454399, 1585429199, 1585443599, 1585443599, 1, 0,
   1585443600, 1585454400, 1585429200, 1585447200, 1585443600, 1, 1,
   1603587599, 1603598399, 1603573199, 1603591199, 1603587599, 1, 1,
   1603587600, 1603598400, 1603573200, 1603587600, 1603587600, 1, 0,
   1604210399, 1604221199, 1604195999, 1604210399, 1604210399, 1, 0,
   1604210400, 1604217600, 1604192400, 1604210400, 1604206800, 0, 0,
   1640995140, 1641002340, 1640977140, 1640995140, 1640995140, 0, 0,
   1656705600, 1656716400, 1656691200, 1656709200, 1656705600, 1, 1,
   1709208000, 1709215200, 1709190000, 1709208000, 1709208000, 0, 0,
   1710053999, 1710061199, 1710035999, 1710053999, 1710053999, 0, 0,
   1710054000, 1710064800, 1710039600, 1710054000, 1710054000, 1, 0,
   1711846799, 1711857599, 1711832399, 1711846799, 1711846799, 1, 0,
   1711846800, 1711857600, 1711832400, 1711850400, 1711846800, 1, 1,
   1729990799, 1730001599, 1729976399, 1729994399, 1729990799, 1, 1,
   1729990800, 1730001600, 1729976400, 1729990800, 1729990800, 1, 0,
   1730613599, 1730624399, 1730599199, 1730613599, 1730613599, 1, 0,
   1730613600, 1730620800, 1730595600, 1730613600, 1730610000, 0, 0,
   1762061400, 1762072200, 1762047000, 1762061400, 1762061400, 1, 0,
   1772953199, 1772960399, 1772935199, 1772953199, 1772953199, 0, 0,
   1772953200, 1772964000, 1772938800, 1772953200, 1772953200, 1, 0,
   1773255600, 1773266400, 1773241200, 1773255600, 1773255600, 1, 0,
   1793286000, 1793296800, 1793271600, 1793286000, 1793286000, 1, 0,
   1793512799, 1793523599, 1793498399, 1793512799, 1793512799, 1, 0,
   1794560400, 1794567600, 1794542400, 1794560400, 1794560400, 0, 0,
   1893794400, 1893801600, 1893776400, 1893794400, 1893794400, 0, 0,
   2057209199, 2057216399, 2057191199, 2057209199, 2057209199, 0, 0,
   2057209200, 2057220000, 2057194800, 2057209200, 2057209200, 1, 0,
   2058397199, 2058407999, 2058382799, 2058397199, 2058397199, 1, 0,
   2058397200, 2058408000, 2058382800, 2058400800, 2058397200, 1, 1,
   2077145999, 2077156799, 2077131599, 2077149599, 2077145999, 1, 1,
   2077146000, 2077156800, 2077131600, 2077146000, 2077146000, 1, 0,
   2077768799, 2077779599, 2077754399, 2077768799, 2077768799, 1, 0,
   2077768800, 2077776000, 2077750800, 2077768800, 2077765200, 0, 0,
   2082754800, 2082762000, 2082736800, 2082754800, 2082754800, 0, 0};
// NYSE: New York date 00:00, kind (0 open, 1 full closure, 2 13:00 half day)
long CR_GOLD_NYSE[] = {
   1364515200, 1, 1372809600, 2, 1387843200, 2, 1390176000, 1,
   1428019200, 1, 1448582400, 2, 1455494400, 1, 1482710400, 1,
   1483315200, 1, 1544054400, 0, 1527465600, 1, 1530576000, 2,
   1543968000, 1, 1545609600, 2, 1562198400, 1, 1567382400, 1,
   1574899200, 1, 1574985600, 2, 1593734400, 1, 1623974400, 0,
   1640304000, 1, 1640908800, 0, 1655683200, 1, 1672617600, 1,
   1687132800, 1, 1705276800, 1, 1719964800, 2, 1736380800, 1,
   1739750400, 1, 1766534400, 2, 1775174400, 1, 1783036800, 1,
   1798070400, 2, 1813276800, 1, 1820188800, 1, 1829606400, 1,
   1839283200, 1, 1606262400, 0, 1671753600, 0, 1794614400, 0};
// AddTradingDays: utc, n, result utc
long CR_GOLD_ATD[] = {
   1357333200, 5, 1357938000, 1457730000, 1, 1457985600,
   1457776800, 1, 1457946000, 1457856000, 2, 1458028800,
   1478289600, 1, 1478552400, 1546293600, 5, 1546898400,
   1555603200, 3, 1556035200, 1577217600, 5, 1577822400,
   1582927140, 1, 1583186340, 1604026800, 5, 1604635200,
   1615582800, 5, 1616184000, 1625230800, 10, 1626440400,
   1636138800, -1, 1636052400, 1641038400, 0, 1641211200,
   1709244000, 2, 1709589600, 1762056000, 1, 1762146000,
   1772827200, 5, 1773428400, 1794603600, 5, 1795208400,
   1924642800, 3, 1924988400, 2066760000, 5, 2067364800};
// BusinessDays: date 00:00, n, result
long CR_GOLD_BDAY[] = {
   1357344000, 1, 1357516800, 1357344000, -1, 1357257600,
   1357344000, 0, 1357516800, 1357430400, 0, 1357516800,
   1456704000, 2, 1456876800, 1514505600, 2, 1514851200,
   1527811200, -3, 1527552000, 1574812800, 2, 1574985600,
   1583452800, 5, 1584057600, 1609372800, 1, 1609459200,
   1617321600, 2, 1617667200, 1640908800, -10, 1639699200,
   1640995200, 2, 1641254400, 1720051200, 2, 1720396800,
   1735862400, 10, 1737072000, 1794528000, 2, 1794873600,
   1794614400, -2, 1794441600, 1803600000, 3, 1804032000,
   1945814400, 1, 1945987200, 2082412800, 4, 2082931200};
// ORX time exit: London date 00:00, 16:00 New York on BusinessDays(date, 2) as utc
long CR_GOLD_ORX[] = {
   1357084800, 1357333200, 1395964800, 1396382400, 1446076800, 1446498000,
   1458777600, 1459195200, 1541030400, 1541451600, 1577404800, 1577826000,
   1582761600, 1583182800, 1616716800, 1617134400, 1635379200, 1635796800,
   1794441600, 1794862800};
// F1: the 15 features (FEATURES order), then the score (16 per row); the threshold is 0.027922380451488427
double CR_GOLD_F1[] = {
   1.1640130919902554, 0.49309794866657003, -0.23843439838702665, 2.921307444073542,
   3.838668005964406, -2.7612215822421819, 3.0550563031361766, 1.3519289174877493,
   0.21791760787179923, 0.0, 1.0, 1.1640130919902554,
   1.6282697229262664, 3.0, 1.0, 0.027894567582274814,
   0.067018267432784773, 1.075323765260457, 0.60587456834637277, 1.7611461042345689,
   3.1207491168197912, 9.8706871956034519, 3.7004556491276897, 1.4709293313430676,
   0.98583253085601041, 2.0, 0.0, 2.266693282144757,
   3.2522660553802849, 13.0, 2.0, 0.027813632718021175,
   0.013132051177002486, 0.89065574188935881, 0.76491663342887384, 2.3275262825854308,
   4.2955040608545545, -2.5196011954425117, 5.1069682999594637, 1.2245597878703833,
   0.80708260465019788, 4.0, 0.0, 2.5205800029704766,
   4.8681694342150115, 15.0, 1.0, 0.028049717274621036,
   0.1522696619248029, 3.1196291936022815, 1.3980841937136474, 3.2134259716899143,
   1.8002550660357917, -10.471456900555438, 9.414387727312663, 1.1783130215810056,
   0.31937750230171741, 0.0, 1.0, -7.3378176208399886,
   1.842446609137067, 14.0, 3.0, -0.26896924274476058,
   1.0217220893099039, 2.0695197101410412, 1.9040657275416191, 1.9832152488893682,
   5.6149877568281497, -4.9265680083370915, 4.9508453260238214, 0.9203161552470438,
   0.24028762277083057, 3.0, 0.0, 1.0217220893099039,
   2.1508661680698866, 5.0, 2.0, -0.035064054705454789,
   0.18512132928403785, 2.5129212858524594, 0.9164099827322042, 4.7178538006920254,
   6.6955678507505807, 8.8538546049832849, 7.2759977250737133, 0.60155088162172243,
   0.6721354534799604, 4.0, 0.0, 5.244805366716788,
   7.0158763020503558, 12.0, 0.0, -0.0035088202236979379,
   1.0995173187417873, 2.263889692813474, 1.463451397683126, 3.0639667560727877,
   7.4579818053734073, 10.77921793728164, 6.4982830545955297, 0.8191067274049928,
   0.76316461373636202, 6.0, 0.0, 5.9589445196320519,
   7.3589156852128976, 14.0, 1.0, 0.019968798758145945,
   1.2964153208358025, 1.2846957423252581, 1.0486181762472546, 2.0505963956329905,
   2.6225264688168197, 3.6676569974863495, 2.7071546846205137, 0.89003930074907911,
   0.58093612752823831, 3.0, 0.0, 1.2964153208358025,
   1.9044575692109789, 3.0, 1.0, 0.042035155238064628,
   0.10570309597223217, 1.249935821038368, 0.66850345468943662, 0.61561696808279665,
   7.9423916412499684, 18.536910927826298, 9.3454177594187975, 1.080899353026475,
   0.65894137791836049, 3.0, 0.0, 5.9509520567898306,
   6.9987565411836643, 10.0, 0.0, 0.064159159970363047,
   0.4882514144489053, 0.84266600149582638, 0.6509667536599183, 1.3226255985125277,
   1.8697794999958777, -2.3579888471566242, 2.4818528712854429, 1.3091333466671151,
   0.70818786092298258, 0.0, 0.0, 0.4882514144489053,
   1.9335006281608413, 8.0, 2.0, 0.089789911451164245,
   0.46453165976805855, 1.5852642206575209, 1.2180646533520796, 2.9177860182276225,
   8.0460624035292536, 3.0533027316411068, 9.1605058785800004, 1.2593674525602709,
   0.41948096703539123, 3.0, 1.0, 6.3544301022898972,
   9.4165164861243422, 9.0, 0.0, 0.13208267894869757,
   11.166743138166888, 0.65520876662336847, 0.10067071837437386, 13.890996771369927,
   11.606266329841963, -0.591081833516091, 3.1204682446329293, 1.1042385094777756,
   0.39247973965413246, 0.0, 2.0, 11.166743138166888,
   13.651698469476392, 3.0, 0.0, 0.41594531684539493,
   0.42911296005664429, 0.88729235202266665, 0.75032770667470428, 1.0477855373770548,
   2.2950506763778971, 4.0573384954227558, 3.1692029437191933, 0.59829144671066403,
   0.76477331064219534, 2.0, 0.0, 0.42911296005664429,
   0.63196495083449189, 3.0, 4.0, 0.027861675781709835,
   1.0489451706528019, 2.4264300200670346, 2.2115616808566312, 2.0440004347005081,
   7.8114160156080006, 6.5583540020045303, 7.3346260803060375, 1.0981956665652575,
   0.94338954217372339, 1.0, 0.0, 1.51664262134578,
   3.2008650505965481, 10.0, 3.0, 0.027837958725240072,
   0.40440988914783282, 1.2291625344260217, 0.4640983873759158, 2.1650316828455618,
   2.7360290497498747, 18.567797088639651, 4.0072814253331579, 1.536993623625887,
   0.99375646269422202, 1.0, 0.0, 0.58094905707614986,
   3.0078111362975637, 9.0, 2.0, 0.027820461415442539,
   0.37583590605917627, 1.5786978407933092, -0.62130360995323053, 2.455255161128767,
   6.6628550203800199, 19.816944362919585, 6.4534255041796644, 1.0237780417534221,
   0.96619796664027446, 6.0, 0.0, 0.37583590605917627,
   1.3070512701882631, 3.0, 1.0, -0.18784436790720721,
   0.19067078863945505, 0.92072407688574109, 0.69484010767399029, 0.44643444858460457,
   3.3672815516301999, -1.8184406784068572, 3.8926524834617169, 0.46483368476869419,
   0.27474314687186246, 2.0, 0.0, 1.0950657861161119,
   3.937146340874961, 15.0, 4.0, -0.028226906652761147,
   1.5220908685055339, 3.4952338739478881, 1.5994544569149407, 2.9061832487910126,
   2.968700141255324, -3.508652980123061, 2.707589281713588, 1.1924582334019018,
   0.20661800182147838, 0.0, 1.0, 1.5220908685055339,
   2.9201368905181297, 5.0, 2.0, -0.0017938215928163387,
   0.046219774221655414, 0.74998792928382596, 0.31473426946026911, 1.036811512498359,
   2.5179708160674483, 3.3511229243250615, 2.8236109542805599, 1.0078801851021151,
   0.88181872792715177, 1.0, 0.0, 0.24054339625207311,
   0.4998912649545626, 5.0, 1.0, 0.018854319942894628,
   0.1190988790841718, 0.74647872101705637, 0.47643178905484773, 0.936951945754954,
   3.6525245342990051, 3.2316901857819427, 3.5414229259272041, 1.3975850468845126,
   0.88952507599623998, 0.0, 1.0, 0.18260549944743856,
   1.0639962773827498, 4.0, 3.0, 0.038953465621718149,
   0.64759735196369428, 1.9064475529497618, 1.8407086250604348, 1.0033655181510928,
   6.9669071165169738, 9.275594841656245, 7.4868720265145088, 0.48913396937645126,
   0.55376166421371675, 3.0, 0.0, 6.5209054732353087,
   6.8228855234274022, 13.0, 1.0, 0.061291433862136244,
   0.6772725271747948, 1.1415620659301042, 1.0273363306286516, 1.7198786865341757,
   4.7943520907811044, 15.585449336380476, 5.3277117278614581, 1.4204183592596056,
   0.99784980464774087, 2.0, 0.0, 2.0546726612572987,
   4.3377471297543311, 7.0, 0.0, 0.087868908101299464,
   2.8925021497206496, 3.449143515258096, 3.3376216277625925, 4.8952493793274092,
   9.1596063639656418, 4.8952493793274092, 6.7128851194613839, 0.63505839005711406,
   0.19316017729092408, 2.0, 0.0, 7.0446989576721224,
   9.345476087806869, 14.0, 0.0, 0.13680573081613689,
   10.861717296806482, 0.87806353670874393, -5.9504086639892355e-05, 11.785027333101651,
   11.397511927564452, 19.052672084024756, 2.4962708144506665, 0.96209768180268618,
   0.97831276312859983, 0.0, 1.0, 10.861717296806482,
   12.058567619363206, 3.0, 0.0, 0.41276118800307271,
   10.164013091990256, 18.49309794866657, 26.761565601612972, 38.921307444073541,
   48.838668005964408, 51.238778417757821, 66.055056303136183, 73.351928917487754,
   81.217917607871797, 90.0, 100.0, 109.16401309199026,
   118.62826972292626, 8.0, 0.0, 0.27584629233565422,
   -7.8359869080097448, -17.50690205133343, -27.238434398387028, -33.078692555926459,
   -41.161331994035592, -56.761221582242179, -59.944943696863824, -70.648071082512246,
   -80.782082392128203, -90.0, -98.0, -106.83598690800974,
   -115.37173027707374, 10.0, 4.0, -0.16332538327897433,
   1.1640130919902554, 0.49309794866657003, -0.23843439838702665, 2.921307444073542,
   3.838668005964406, -2.7612215822421819, 3.0550563031361766, 1.3519289174877493,
   0.21791760787179923, 0.0, 1.0, 1.1640130919902554,
   1.6282697229262664, 11.0, 1.0, 0.0061120748826962376,
   5.0640130919902555, 8.2930979486665706, 11.461565601612973, 18.521307444073543,
   23.338668005964408, 20.638778417757816, 30.355056303136177, 32.55192891748775,
   35.317917607871799, 39.0, 43.899999999999999, 47.964013091990253,
   52.328269722926265, 12.0, 4.0, 0.25900509795644783,
   -2.9359869080097445, -7.7069020513334294, -12.538434398387025, -13.478692555926457,
   -16.661331994035592, -27.36122158224218, -25.64494369686382, -31.448071082512246,
   -36.682082392128201, -41.0, -44.099999999999994, -48.03598690800974,
   -51.671730277073728, 13.0, 2.0, -0.20073327466840252,
   101.16401309199026, 200.49309794866656, 299.76156560161297, 402.92130744407353,
   503.83866800596439, 597.23877841775777, 703.05505630313621, 801.35192891748773,
   900.21791760787175, 1000.0, 1101.0, 1201.1640130919902,
   1301.6282697229262, 15.0, 5.0, 0.20770780358504176};
// K1 riskbp: stop_dist, P (mid close of the last bar before the decision), the lab's 1e4 x stop_dist / P
double CR_GOLD_RBP[] = {
   51.224999999999952, 995.70000000000005, 514.46218740584459,
   43.850000000000037, 566.60000000000002, 773.91457818566948,
   16.537500000000001, 124.59999999999999, 1327.2471910112361,
   16.181250000000034, 247.44999999999999, 653.91998383511964,
   15.193750000000005, 136.5, 1113.0952380952385,
   5.1687500000000064, 206.0, 250.91019417475761,
   7.8749999999999929, 356.20000000000005, 221.08366086468254,
   82.925000000000097, 1732.2, 478.72647500288701,
   103.11874999999975, 2720.8500000000004, 378.99461565319564,
   113.73125000000016, 3628.75, 313.41715466758569};
// ... and the decision of each (utc), for the message
long CR_GOLD_RBP_T[] = {
   1515128400, 1527156000, 1542765600, 1559278800, 1574654400,
   1588143600, 1602241200, 1615856400, 1628114400, 1640822400};
// risk tables: the keys, then per plan the number of pairs and the rate at each key
double CR_GOLD_KEYS[] = {
   0.0, 999.99000000000001, 2999.9899999999998, 3000.0, 3000.0100000000002, 5999.9899999999998,
   6000.0, 11999.99, 12000.0, 50000.0, 10000000.0};
int CR_GOLD_RISK_NP[] = {
   4, 3, 2};
double CR_GOLD_RISK[] = {
   3.0, 3.0, 3.0, 2.0, 2.0, 2.0, 1.0, 1.0, 0.5, 0.5, 0.5,
   2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 1.0, 1.0, 0.5, 0.5, 0.5,
   1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.5, 0.5, 0.5};
string CR_GOLD_RISK_TXT[] = {"0:3;3000:2;6000:1;12000:0.5", "0:2;6000:1;12000:0.5", "0:1;12000:0.5"};
string CR_GOLD_RISK_NAME[] = {"F3S", "F2S", "F1S"};
// the series (1 = NaN in the _NAN tables), pandas ewm(alpha=1/14, adjust=False).mean() and rolling(14, 9).mean()
double CR_GOLD_X[] = {
   0.0, 1.5800000000000001, 1.0900000000000001, 3.71, 1.01, 3.3599999999999999, 1.6200000000000001, 1.73,
   2.6400000000000001, 1.1599999999999999, 1.3500000000000001, 0.66000000000000003, 2.6499999999999999, 0.87, 2.4900000000000002, 2.6000000000000001,
   0.76000000000000001, 0.0, 6.7800000000000002, 2.6499999999999999, 2.8199999999999998, 6.2699999999999996, 1.6599999999999999, 1.97,
   0.46999999999999997, 2.8900000000000001, 0.46000000000000002, 2.1899999999999999, 1.5700000000000001, 0.40000000000000002, 0.0, 0.0,
   1.1000000000000001, 0.0, 0.0, 0.0, 0.0, 1.8300000000000001, 3.54, 0.44,
   3.6899999999999999, 3.75, 0.70999999999999996, 1.1000000000000001, 0.72999999999999998, 0.68000000000000005, 0.87, 0.93000000000000005};
int CR_GOLD_X_NAN[] = {
   1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0,
   0, 0, 0, 0, 0, 0, 1, 1, 0, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
double CR_GOLD_WIL[] = {
   0.0, 1.5800000000000001, 1.5450000000000002, 1.6996428571428572,
   1.6503826530612244, 1.7724981778425657, 1.761605450853811, 1.7593479186499676,
   1.8222516387463987, 1.7749479502645134, 1.7445945252456196, 1.6671234877280754,
   1.7373289528903557, 1.6753768848267589, 1.7335642501962762, 1.7954525180393994,
   1.7214916238937281, 1.7214916238937281, 2.1084813357269949, 2.1471612403179239,
   2.1952211517237865, 2.486276783743516, 2.4272570134761224, 2.3945957982278281,
   2.257124669782983, 2.30233005051277, 2.1707350469047153, 2.17211111498295,
   2.1291031781984535, 2.0055958083271355, 2.0055958083271355, 2.0055958083271355,
   1.9314224784349003, 1.9314224784349003, 1.9314224784349003, 1.9314224784349003,
   1.9314224784349003, 1.9219126899470831, 2.0374903549508629, 1.9233839010258014,
   2.0495707652382444, 2.1710299962926558, 2.0666707108431805, 1.9976228029258105,
   1.9070783170025383, 1.8194298657880712, 1.751613446803209, 1.6929267720315513};
int CR_GOLD_WIL_NAN[] = {
   1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
double CR_GOLD_SMA[] = {
   0.0, 0.0, 0.0, 0.0,
   0.0, 0.0, 0.0, 0.0,
   0.0, 1.9888888888888887, 1.925, 1.8100000000000001,
   1.8799999999999999, 1.8023076923076924, 1.8514285714285716, 1.9242857142857144,
   1.9007142857142856, 1.7615384615384617, 2.2053846153846157, 2.1507692307692308,
   2.2430769230769232, 2.592307692307692, 2.516923076923077, 2.5792307692307692,
   2.5115384615384615, 2.6830769230769231, 2.5146153846153849, 2.6161538461538458,
   2.5453846153846151, 2.3761538461538461, 2.5108333333333333, 2.5108333333333333,
   2.0375000000000001, 1.9818181818181819, 1.8980000000000001, 1.4122222222222223,
   0.0, 0.0, 0.0, 0.0,
   0.0, 0.0, 0.0, 0.0,
   1.8766666666666667, 1.7570000000000001, 1.734, 1.6609090909090909};
int CR_GOLD_SMA_NAN[] = {
   1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0};

CRuleF1   g_gold_f1;                   // scratch objects of the self-test (never the sleeves' own)
CrWilder  g_gold_w;
CrRollSum g_gold_s;

bool GoldNear(const double a, const double b)
  {
   if(!MathIsValidNumber(a) || !MathIsValidNumber(b)) return false;
   double m = MathAbs(b);
   if(m < 1.0) m = 1.0;
   return MathAbs(a - b) <= CR_GOLD_REL * m;
  }

string GoldMsg(const string what, const int k, const string got, const string want)
  {
   return "golden " + what + " " + IntegerToString(k) + ": got " + got + ", want " + want;
  }

bool GoldClock(string &why)
  {
   for(int k = 0; k < CR_GOLD_NCLK; k++)
     {
      int b = 7 * k;
      datetime u = (datetime)CR_GOLD_CLK[b];
      long srv = (long)ClkUtcToServer(u), ny = (long)ClkUtcToNy(u), ldn = (long)ClkUtcToLdn(u);
      long back = (long)ClkServerToUtc((datetime)CR_GOLD_CLK[b + 1]);
      long us = ClkUsDst(u) ? 1 : 0, uk = ClkUkDst(u) ? 1 : 0;
      if(srv != CR_GOLD_CLK[b + 1] || ny != CR_GOLD_CLK[b + 2] || ldn != CR_GOLD_CLK[b + 3] || back != CR_GOLD_CLK[b + 4]
         || us != CR_GOLD_CLK[b + 5] || uk != CR_GOLD_CLK[b + 6])
        {
         why = GoldMsg("clock", k, JI(srv) + "/" + JI(ny) + "/" + JI(ldn) + "/" + JI(back) + "/" + JI(us) + JI(uk),
                       JI(CR_GOLD_CLK[b + 1]) + "/" + JI(CR_GOLD_CLK[b + 2]) + "/" + JI(CR_GOLD_CLK[b + 3]) + "/"
                       + JI(CR_GOLD_CLK[b + 4]) + "/" + JI(CR_GOLD_CLK[b + 5]) + JI(CR_GOLD_CLK[b + 6]));
         return false;
        }
     }
   return true;
  }

bool GoldCalendar(string &why)
  {
   for(int k = 0; k < CR_GOLD_NNYSE; k++)
     {
      int gold = 0;
      long kind = ClkHolKind(ClkDayNo((datetime)CR_GOLD_NYSE[2 * k]), gold);
      if(kind != CR_GOLD_NYSE[2 * k + 1])
        {
         why = GoldMsg("nyse", k, JI(kind), JI(CR_GOLD_NYSE[2 * k + 1]));
         return false;
        }
     }
   for(int k = 0; k < CR_GOLD_NATD; k++)
     {
      long got = (long)ClkAddTradingDays((datetime)CR_GOLD_ATD[3 * k], (int)CR_GOLD_ATD[3 * k + 1]);
      if(got != CR_GOLD_ATD[3 * k + 2])
        {
         why = GoldMsg("add_trading_days", k, JI(got), JI(CR_GOLD_ATD[3 * k + 2]));
         return false;
        }
     }
   for(int k = 0; k < CR_GOLD_NBDAY; k++)
     {
      long got = (long)ClkBusinessDays((datetime)CR_GOLD_BDAY[3 * k], (int)CR_GOLD_BDAY[3 * k + 1]);
      if(got != CR_GOLD_BDAY[3 * k + 2])
        {
         why = GoldMsg("business_days", k, JI(got), JI(CR_GOLD_BDAY[3 * k + 2]));
         return false;
        }
     }
   for(int k = 0; k < CR_GOLD_NORX; k++)
     {
      long got = (long)OrxExitTime((datetime)CR_GOLD_ORX[2 * k]);
      if(got != CR_GOLD_ORX[2 * k + 1])
        {
         why = GoldMsg("orx_exit", k, JI(got), JI(CR_GOLD_ORX[2 * k + 1]));
         return false;
        }
     }
   return true;
  }

bool GoldScores(string &why)
  {
   ArrayResize(g_gold_f1.m_x, CR_F1_NFEAT);
   for(int k = 0; k < CR_GOLD_NF1; k++)
     {
      int b = (CR_F1_NFEAT + 1) * k;
      for(int j = 0; j < CR_F1_NFEAT; j++) g_gold_f1.m_x[j] = CR_GOLD_F1[b + j];
      double s = g_gold_f1.Score();
      if(!GoldNear(s, CR_GOLD_F1[b + CR_F1_NFEAT]))
        {
         why = GoldMsg("f1_score", k, JD(s), JD(CR_GOLD_F1[b + CR_F1_NFEAT]));
         return false;
        }
     }
   for(int k = 0; k < CR_GOLD_NRBP; k++)
     {
      double r = Brk72RiskBp(CR_GOLD_RBP[3 * k], CR_GOLD_RBP[3 * k + 1]);
      if(!GoldNear(r, CR_GOLD_RBP[3 * k + 2]))
        {
         why = GoldMsg("riskbp", k, JD(r), JD(CR_GOLD_RBP[3 * k + 2]) + " (decision " + JI(CR_GOLD_RBP_T[k]) + ")");
         return false;
        }
     }
   return true;
  }

bool GoldRisk(string &why)
  {
   bool ok = true;
   for(int t = 0; t < CR_GOLD_NRISK && ok; t++)
     {
      double fr[], pc[];
      int n = 0;
      string err = "";
      if(!SizParseTable(CR_GOLD_RISK_TXT[t], fr, pc, n, err) || n != CR_GOLD_RISK_NP[t])
        {
         why = GoldMsg("risk_table", t, CR_GOLD_RISK_NAME[t] + " parsed into " + IntegerToString(n) + " pairs " + err,
                       IntegerToString(CR_GOLD_RISK_NP[t]) + " pairs");
         ok = false;
         break;
        }
      LedSetRates(fr, pc, n);
      for(int k = 0; k < CR_GOLD_NKEY; k++)
        {
         double got = LedRate(CR_GOLD_KEYS[k]);
         double want = CR_GOLD_RISK[t * CR_GOLD_NKEY + k];
         if(got != want)
           {
            why = GoldMsg("risk_table", t, CR_GOLD_RISK_NAME[t] + " at " + JD(CR_GOLD_KEYS[k]) + ": " + JD(got), JD(want));
            ok = false;
            break;
           }
        }
     }
   LedSetRates(g_siz_from, g_siz_pct, g_siz_n);        // the live table (InpRiskTable) again
   return ok;
  }

bool GoldSeries(string &why)
  {
   g_gold_w.Init(14);
   g_gold_s.Init(14, 9);
   for(int k = 0; k < CR_GOLD_NSER; k++)
     {
      double x = (CR_GOLD_X_NAN[k] != 0) ? CrNaN() : CR_GOLD_X[k];
      double w = g_gold_w.Push(x);
      g_gold_s.Push(x);
      double m = g_gold_s.Mean();
      bool wn = !MathIsValidNumber(w), mn = !MathIsValidNumber(m);
      if(wn != (CR_GOLD_WIL_NAN[k] != 0) || (!wn && !GoldNear(w, CR_GOLD_WIL[k])))
        {
         why = GoldMsg("wilder", k, JD(w), (CR_GOLD_WIL_NAN[k] != 0) ? "nan" : JD(CR_GOLD_WIL[k]));
         return false;
        }
      if(mn != (CR_GOLD_SMA_NAN[k] != 0) || (!mn && !GoldNear(m, CR_GOLD_SMA[k])))
        {
         why = GoldMsg("sma", k, JD(m), (CR_GOLD_SMA_NAN[k] != 0) ? "nan" : JD(CR_GOLD_SMA[k]));
         return false;
        }
     }
   return true;
  }

bool GoldenCheck(string &why)
  {
   why = "";
   if(!GoldClock(why)) return false;
   if(!GoldCalendar(why)) return false;
   if(!GoldScores(why)) return false;
   if(!GoldRisk(why)) return false;
   if(!GoldSeries(why)) return false;
   return true;
  }
#endif

// ==== end src/CR_Golden.mqh
// ==== begin src/CR_Main.mqh
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
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Clock.mqh)
// (already inlined: CR_Journal.mqh)
// (already inlined: CR_Math.mqh)
// (already inlined: CR_Registry.mqh)
// (already inlined: CR_Bars.mqh)
// (already inlined: CR_Paper.mqh)
// (already inlined: CR_Ledger.mqh)
// (already inlined: CR_Sizing.mqh)
// (already inlined: CR_Broker.mqh)
// (already inlined: CR_Follower.mqh)
// (already inlined: CR_Guards.mqh)
// (already inlined: CR_Golden.mqh)

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

// ==== end src/CR_Main.mqh

// ==== end src/ClaudeRobot.mq5
