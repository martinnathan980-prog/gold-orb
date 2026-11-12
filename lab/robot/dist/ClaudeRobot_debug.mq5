#define CR_BUILD "1c83aea7fde7"
#define CR_DEBUG
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
//| S0 STUB: final class names and method signatures (the registry   |
//| dispatches on them); neutral bodies (nothing emitted).           |
//| Interface of every rule class (SPEC 2.4):                        |
//|   bool     Init(sl)          frozen constants; false = bad config |
//|   void     OnBar(sym, b, out)  each kept closed bar of its       |
//|                              symbols, time order, before the     |
//|                              paper engine                        |
//|   void     OnMinute(M, out)  after barrier M, bars before M only |
//|   datetime LatestExit(open_time, comment_dec)  SPEC 4.8 table    |
//+------------------------------------------------------------------+
#ifndef CR_RULE_IDXUS_MQH
#define CR_RULE_IDXUS_MQH
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Clock.mqh)
// (already inlined: CR_Math.mqh)

class CRuleN30
  {
public:
   int      sl;
   bool     Init(const int sleeve) { sl = sleeve; return true; }
   void     OnBar(const int sym, const CrBar &b, CrOut &out) {}
   void     OnMinute(const datetime M, CrOut &out) {}
   datetime LatestExit(const datetime open_time, const datetime comment_dec) { return 0; }
  };

class CRuleOC4
  {
public:
   int      sl;
   bool     Init(const int sleeve) { sl = sleeve; return true; }
   void     OnBar(const int sym, const CrBar &b, CrOut &out) {}
   void     OnMinute(const datetime M, CrOut &out) {}
   datetime LatestExit(const datetime open_time, const datetime comment_dec) { return 0; }
  };
#endif

// ==== end src/CR_Rule_IdxUS.mqh
// ==== begin src/CR_Rule_Brk72.mqh
//+------------------------------------------------------------------+
//| CR_Rule_Brk72.mqh - BKB / BKE brk72_24h_wd on BTC and ETH, with   |
//| S0.75r (BKB) and K1 (BKE) behind their switches (SPEC 3).         |
//| Owner: E.                                                         |
//|                                                                  |
//| S0 STUB: final signatures, neutral bodies.                       |
//|   Init(sl) parses g_cfg.k1t for the sleeve whose change is K1    |
//|   ("YYYY:T;YYYY:T", bp, 17 significant digits); a string that    |
//|   does not parse returns false (ERROR at OnInit).                |
//|   Brk72K1Known(year): a T > 0 exists for that year (the driver   |
//|   pushes "K1 with no T for the year" when the switch is on).     |
//+------------------------------------------------------------------+
#ifndef CR_RULE_BRK72_MQH
#define CR_RULE_BRK72_MQH
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Clock.mqh)
// (already inlined: CR_Math.mqh)

class CRuleBrk72
  {
public:
   int      sl;
   bool     Init(const int sleeve) { sl = sleeve; return true; }
   void     OnBar(const int sym, const CrBar &b, CrOut &out) {}
   void     OnMinute(const datetime M, CrOut &out) {}
   datetime LatestExit(const datetime open_time, const datetime comment_dec) { return 0; }
  };

bool Brk72K1Known(const int year) { return false; }
#endif

// ==== end src/CR_Rule_Brk72.mqh
// ==== begin src/CR_Rule_F1.mqh
//+------------------------------------------------------------------+
//| CR_Rule_F1.mqh - F1B / F1E F1_brk_ridge_filter on BTC and ETH,    |
//| with H2 (F1E) behind its switch (SPEC 3). Owner: E.               |
//| The frozen scorecard comes from the generated CR_F1Model.mqh.    |
//|                                                                  |
//| S0 STUB: final signatures, neutral bodies.                       |
//+------------------------------------------------------------------+
#ifndef CR_RULE_F1_MQH
#define CR_RULE_F1_MQH
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Clock.mqh)
// (already inlined: CR_Math.mqh)
// ==== begin src/CR_F1Model.mqh
//+------------------------------------------------------------------+
//| CR_F1Model.mqh - GENERATED by tools/gen_f1_model.py (step E) from |
//| lab/r2/tracks/ml/models/B1_ridge_full.json["frozen"], refused     |
//| unless its sha256 is d191cbbcc2fc4d2cae31182f14f412069a194b69c2a9 |
//| d9ae6bca0d0f5dee644e. Constants written with %.17g.               |
//|                                                                  |
//| S0 STUB: no model (CR_F1_READY 0). Do not edit by hand.          |
//+------------------------------------------------------------------+
#ifndef CR_F1MODEL_MQH
#define CR_F1MODEL_MQH
#define CR_F1_READY 0
#define CR_F1_NNUM 0
#define CR_F1_NDUM 0
#define CR_F1_CLIP 4.0
#define CR_F1_INTERCEPT 0.0
#define CR_F1_THR 0.027922380451488427
#endif

// ==== end src/CR_F1Model.mqh

class CRuleF1
  {
public:
   int      sl;
   bool     Init(const int sleeve) { sl = sleeve; return true; }
   void     OnBar(const int sym, const CrBar &b, CrOut &out) {}
   void     OnMinute(const datetime M, CrOut &out) {}
   datetime LatestExit(const datetime open_time, const datetime comment_dec) { return 0; }
  };
#endif

// ==== end src/CR_Rule_F1.mqh
// ==== begin src/CR_Rule_NqBtc.mqh
//+------------------------------------------------------------------+
//| CR_Rule_NqBtc.mqh - NQB nq_btc_follow: BTC follows a 6-sigma      |
//| US100 impulse (SPEC 3). Reads US100 and BTC bars. Owner: F.       |
//|                                                                  |
//| S0 STUB: final signatures, neutral bodies.                       |
//+------------------------------------------------------------------+
#ifndef CR_RULE_NQBTC_MQH
#define CR_RULE_NQBTC_MQH
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Clock.mqh)
// (already inlined: CR_Math.mqh)

class CRuleNqb
  {
public:
   int      sl;
   bool     Init(const int sleeve) { sl = sleeve; return true; }
   void     OnBar(const int sym, const CrBar &b, CrOut &out) {}
   void     OnMinute(const datetime M, CrOut &out) {}
   datetime LatestExit(const datetime open_time, const datetime comment_dec) { return 0; }
  };
#endif

// ==== end src/CR_Rule_NqBtc.mqh
// ==== begin src/CR_Rule_GoldFri.mqh
//+------------------------------------------------------------------+
//| CR_Rule_GoldFri.mqh - GFP GOLD_FRI_PM: Friday 13:30 NY buy limit  |
//| on gold (SPEC 3). Owner: G.                                       |
//|                                                                  |
//| S0 STUB: final signatures, neutral bodies.                       |
//+------------------------------------------------------------------+
#ifndef CR_RULE_GOLDFRI_MQH
#define CR_RULE_GOLDFRI_MQH
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Clock.mqh)
// (already inlined: CR_Math.mqh)

class CRuleGfp
  {
public:
   int      sl;
   bool     Init(const int sleeve) { sl = sleeve; return true; }
   void     OnBar(const int sym, const CrBar &b, CrOut &out) {}
   void     OnMinute(const datetime M, CrOut &out) {}
   datetime LatestExit(const datetime open_time, const datetime comment_dec) { return 0; }
  };
#endif

// ==== end src/CR_Rule_GoldFri.mqh
// ==== begin src/CR_Rule_Orb.mqh
//+------------------------------------------------------------------+
//| CR_Rule_Orb.mqh - ORX orb_asia_2d_buf10: London 00:00-07:00 range |
//| breakout on gold (SPEC 3). Owner: G.                              |
//|                                                                  |
//| S0 STUB: final signatures, neutral bodies.                       |
//+------------------------------------------------------------------+
#ifndef CR_RULE_ORB_MQH
#define CR_RULE_ORB_MQH
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Clock.mqh)
// (already inlined: CR_Math.mqh)

class CRuleOrx
  {
public:
   int      sl;
   bool     Init(const int sleeve) { sl = sleeve; return true; }
   void     OnBar(const int sym, const CrBar &b, CrOut &out) {}
   void     OnMinute(const datetime M, CrOut &out) {}
   datetime LatestExit(const datetime open_time, const datetime comment_dec) { return 0; }
  };
#endif

// ==== end src/CR_Rule_Orb.mqh
// ==== begin src/CR_Rule_Donch.mqh
//+------------------------------------------------------------------+
//| CR_Rule_Donch.mqh - D4H donch4h_stop: 60 x 4h channel OCO with a  |
//| 2-ATR trailing stop on gold (SPEC 3). Owner: H.                   |
//|                                                                  |
//| S0 STUB: final signatures, neutral bodies.                       |
//+------------------------------------------------------------------+
#ifndef CR_RULE_DONCH_MQH
#define CR_RULE_DONCH_MQH
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Clock.mqh)
// (already inlined: CR_Math.mqh)

class CRuleDonch
  {
public:
   int      sl;
   bool     Init(const int sleeve) { sl = sleeve; return true; }
   void     OnBar(const int sym, const CrBar &b, CrOut &out) {}
   void     OnMinute(const datetime M, CrOut &out) {}
   datetime LatestExit(const datetime open_time, const datetime comment_dec) { return 0; }
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
//|   flat    bid O = H = L = C and equal to the previous raw bar's  |
//|           bid close (prep_round2.py:49, prep_data.py:39-41)      |
//|   weekend gold and US100: Saturday or Sunday, server clock       |
//|           (prep_round2.py:53)                                    |
//|   crypto  Saturday, Sunday, or Friday from 23:55, server clock   |
//|           (build_fp_frames.py:31-33)                             |
//|   idx     US100 16:15-17:59 New York                             |
//|   xau     gold 17:00-17:59 New York                              |
//|   half    US100 13:16-17:59 New York on NYSE half days (P6;      |
//|           ClkNyse, typed HALF entries included)                  |
//| The bars left are the kept bars; masked bars still count as      |
//| broker bars for the flat rule, the hole scan and revisions.      |
//|                                                                  |
//| Barrier M (UTC minute; every bar starting before M is final):    |
//|   M = the current minute when every symbol has ticked in it or   |
//|   is in a known closure (ClkInClosure); else the minute that     |
//|   started at least 2 s ago (TimeTradeServer() >= M + 2 s).       |
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
//|       accepted=1).                                               |
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
#define CR_MASK_FLAT 1
#define CR_MASK_WEEKEND 2
#define CR_MASK_CRYPTO 3
#define CR_MASK_IDX 4
#define CR_MASK_XAU 5
#define CR_MASK_HALF 6
#define CR_MASK_N 7

string CR_MASK_NAME[CR_MASK_N] = {"kept", "m_flat", "m_weekend", "m_crypto", "m_idx", "m_xau", "m_half"};

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

// the mask reason of one broker bar (CR_MASK_*); prev_ok / prev_c: the previous broker bar's bid close
int BarsMaskReason(const int sym, const MqlRates &r, const bool prev_ok, const double prev_c)
  {
   if(prev_ok && r.open == r.high && r.high == r.low && r.low == r.close && r.close == prev_c) return CR_MASK_FLAT;
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
   if(g_bars_late_last > 0 && now - g_bars_late_last < CR_BARS_LATE_S) wait = CR_BARS_LATE_S - (long)(now - g_bars_late_last);
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
   double   prev_c;                    // bid close of the previous broker bar (flat rule)
   bool     prev_ok;
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
      prev_c = 0.0;
      prev_ok = false;
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

   // one broker bar, in time order: hole scan, mask, flat-rule state, revision copy; the kept bar is stored
   // unless store_it is false (a late bar: a rebuild was asked for)
   void Take(const MqlRates &r, const bool store_it)
     {
      datetime t = ClkServerToUtc(r.time);
      if(prev_end > 0 && t > prev_end) HoleAdd(prev_end, t);
      prev_end = t + 60;
      int why = BarsMaskReason(sym, r, prev_ok, prev_c);
      prev_c = r.close;
      prev_ok = true;
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
      MqlRates p[];
      int np = CopyRates(nm, PERIOD_M1, (datetime)(ws_srv - 1), 1, p);
      if(np == 1 && p[0].time < ws_srv)
        {
         prev_c = p[0].close;
         prev_ok = true;
        }
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
      datetime miss = 0;
      for(int j = 0; j < ntk && miss == 0; j++)
        {
         datetime m = tk[j];
         if(m >= Msrv || m <= last_srv) continue;
         bool found = false;
         for(int i = 0; i < k && !found; i++)
            if(r[i].time == m) found = true;
         if(!found) miss = m;
        }
      if(miss != 0)
        {
         if(wait_since == 0) wait_since = now;
         if((long)(now - wait_since) < CR_BARS_WAIT_S) return 1;
         g_bars_gap_live++;
         Jrn(CR_EV_GAP, JrnSymCode(sym), KT("minute", ClkServerToUtc(miss)) + KI("live", 1) + KI("waited_s", (long)(now - wait_since)));
         JrnPush("barre manquante " + g_sym[sym].base + " a " + ClkStr(ClkServerToUtc(miss)) + " UTC", false);
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
//| CR_Paper.mqh - the paper engine (SPEC 2.5): a streaming port of   |
//| goldlab/sim.py _run per sleeve, gap rule, late gap revision,     |
//| hold extension, 3-spread refusals, void_le. Owner: C.             |
//|                                                                  |
//| S0 STUB: final signatures, neutral bodies (no trade, no event).  |
//| API (C keeps these signatures):                                  |
//|   PapInit()                 once at OnInit                       |
//|   PapReset()                every sleeve flat, no order (rebuild)|
//|   PapSubmit(o)              a rule's order; false = ERROR (two   |
//|                             pending orders of one sleeve)        |
//|   PapSubmitExit(e)          a rule's exit (CrExit)               |
//|   PapOnBar(sl, b)           one kept closed bar of the sleeve's  |
//|                             traded symbol, after the rules'      |
//|                             OnBar for that bar                   |
//|   PapOnBarrier(M)           every sleeve, once per barrier M:    |
//|                             windows that end, late gap revision, |
//|                             hold extension                       |
//|   PapEvents() PapEvent(k, e) PapClearEvents()   the event queue  |
//|   PapTrade(sl, t)           the open trade (a pending gap exit   |
//|                             counts as open); false when flat     |
//|   PapPending(sl, o)         the order waiting for its activation |
//|                             or fill; false when none             |
//|   PapLastExitBar(sl)        start of the last trade's exit bar   |
//| Slippage and the symbol of each sleeve: g_sl[] and g_sym[].      |
//+------------------------------------------------------------------+
#ifndef CR_PAPER_MQH
#define CR_PAPER_MQH
// (already inlined: CR_Types.mqh)

void     PapInit() {}
void     PapReset() {}
bool     PapSubmit(const CrOrder &o) { return true; }
bool     PapSubmitExit(const CrExit &e) { return true; }
void     PapOnBar(const int sl, const CrBar &b) {}
void     PapOnBarrier(const datetime M) {}
int      PapEvents() { return 0; }
bool     PapEvent(const int k, CrPEvent &e) { return false; }
void     PapClearEvents() {}
bool     PapTrade(const int sl, CrTrade &t) { return false; }
bool     PapPending(const int sl, CrOrder &o) { return false; }
datetime PapLastExitBar(const int sl) { return 0; }
#endif

// ==== end src/CR_Paper.mqh
// ==== begin src/CR_Ledger.mqh
//+------------------------------------------------------------------+
//| CR_Ledger.mqh - the account ledger from the deal history (SPEC 5) |
//| and the history latches of SPEC 6 (STOP, GUARD b and c, daily     |
//| lock). Owner: I.                                                  |
//|                                                                  |
//| S0 STUB: final signatures, neutral ("allowed") bodies.           |
//| API (I keeps these signatures):                                  |
//|   LedInit(err)              once at OnInit                       |
//|   LedReset()                forget everything (rebuild)          |
//|   LedRead(now_srv)          read HistorySelect(0, now + 86400):  |
//|                             CR_LED_OK or CR_LED_MOVING (SETTLE)  |
//|   LedSettled()              B(T) equal in two reads 2 s apart,   |
//|                             or accepted after 60 s               |
//|   LedOnTransaction()        OnTradeTransaction: read again soon  |
//|   LedOnTimer(now_srv)       the reads of SPEC 5 (once a minute,  |
//|                             after a transaction)                 |
//|   LedPlan(now_srv)          CR_PLAN_OK / UNSET / FUTURE          |
//|   LedPlanStart()            T (server time), 0 when unset        |
//|   LedBalance(S) LedPaidIn(S) LedRef(S)   B, P_in, ref at stamp S |
//|   LedStopLatched()          plan stop STOP from the history      |
//|   LedGuardLatched()         GUARD (b) or (c) from the history    |
//|   LedMarkSeen()             a deal of magic 20261290 after T     |
//|   LedDayLocked(now_srv)     daily lock in force                  |
//|   LedWeekUnit(S)            the week unit (0 = not set yet)      |
//|   LedSetWeekUnit(S, unit)   set it at the week's first event     |
//|   LedWeekW(S)               robot close money of the week / unit |
//|   LedCommission(day, usd_oz, n)  gold commission of the day      |
//+------------------------------------------------------------------+
#ifndef CR_LEDGER_MQH
#define CR_LEDGER_MQH
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Clock.mqh)
// (already inlined: CR_Journal.mqh)

bool     LedInit(string &err) { err = ""; return true; }
void     LedReset() {}
int      LedRead(const datetime now_srv) { return CR_LED_OK; }
bool     LedSettled() { return true; }
void     LedOnTransaction() {}
void     LedOnTimer(const datetime now_srv) {}
int      LedPlan(const datetime now_srv) { return CR_PLAN_OK; }
datetime LedPlanStart() { return 0; }
double   LedBalance(const datetime S) { return AccountInfoDouble(ACCOUNT_BALANCE); }
double   LedPaidIn(const datetime S) { return 0.0; }
double   LedRef(const datetime S) { return 0.0; }
bool     LedStopLatched() { return false; }
bool     LedGuardLatched() { return false; }
bool     LedMarkSeen() { return false; }
bool     LedDayLocked(const datetime now_srv) { return false; }
double   LedWeekUnit(const datetime S) { return 0.0; }
void     LedSetWeekUnit(const datetime S, const double unit) {}
double   LedWeekW(const datetime S) { return 0.0; }

bool LedCommission(const datetime day_srv, double &usd_per_oz, int &n)
  {
   usd_per_oz = 0.0;
   n = 0;
   return false;
  }
#endif

// ==== end src/CR_Ledger.mqh
// ==== begin src/CR_Sizing.mqh
//+------------------------------------------------------------------+
//| CR_Sizing.mqh - risk table, cushion multiplier, lots, the account |
//| checks in the lab's order (SPEC 5). Owner: I.                     |
//|                                                                  |
//| S0 STUB: final signatures, neutral bodies (nothing sized).       |
//| API (I keeps these signatures):                                  |
//|   SizInit(err)                 parse g_cfg.risk_table (SPEC 1:   |
//|                                "from:pct;..."); false = ERROR    |
//|   SizParseTable(s, from, pct, n, err)   the parser itself        |
//|   SizRate(key)                 pct of the last pair with         |
//|                                from <= key (key = max(B, P_in))  |
//|   SizM(w)                      1 if w <= 0, else                 |
//|                                min(1, max(0.25, w / 4))          |
//|   SizSize(it, S, dry)          lots and skip reason of an intent |
//|                                at stamp S (dry: replay, nothing  |
//|                                is sent); returns it.skip         |
//+------------------------------------------------------------------+
#ifndef CR_SIZING_MQH
#define CR_SIZING_MQH
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Ledger.mqh)

bool SizParseTable(const string s, double &from[], double &pct[], int &n, string &err)
  {
   n = 0;
   err = "";
   return true;
  }

bool   SizInit(string &err) { err = ""; return true; }
double SizRate(const double key) { return 0.0; }
double SizM(const double w) { return 1.0; }

int SizSize(CrIntent &it, const datetime S, const bool dry)
  {
   it.lots = 0.0;
   it.skip = CR_SK_NONE;
   return it.skip;
  }
#endif

// ==== end src/CR_Sizing.mqh
// ==== begin src/CR_Broker.mqh
//+------------------------------------------------------------------+
//| CR_Broker.mqh - the only sender of trade requests (SPEC 4.3,      |
//| 4.4): open, close, modify with the hands' checks, GridStop,      |
//| Resolve, the one-intent-one-trade search. Owner: J.               |
//|                                                                  |
//| S0 STUB: final signatures; sends nothing.                        |
//| API (J keeps these signatures):                                  |
//|   BrkInit(err)                  once at OnInit                   |
//|   BrkResolve(base)              the broker's symbol name ("" =   |
//|                                 none), ClaudeMains.mq5:206-226   |
//|   BrkConnected()                terminal connected               |
//|   BrkStableRead(now_srv)        two reads of positions and       |
//|                                 orders 2 s apart agree           |
//|   BrkGridStop(sym, stop, side)  on the tick grid, away from the  |
//|                                 market by less than one tick     |
//|   BrkOpen(it, sl)               CR_SEND_OK / FAIL / UNKNOWN      |
//|   BrkClose(ticket, magic, why)  close a position with a magic    |
//|   BrkModify(ticket, sl)         move a position's stop           |
//|   BrkCloseAll(magic, why)       every robot position (GUARD:     |
//|                                 magic 20261290)                  |
//+------------------------------------------------------------------+
#ifndef CR_BROKER_MQH
#define CR_BROKER_MQH
// (already included: <Trade\Trade.mqh>)
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Journal.mqh)

CTrade g_trade;                        // the one CTrade of the EA (SPEC 1, MQL5 subset)

bool BrkInit(string &err) { err = ""; return true; }

string BrkResolve(const string base)
  {
   if(SymbolSelect(base + ".r", true)) return base + ".r";
   if(SymbolSelect(base, true)) return base;
   return "";
  }

bool   BrkConnected() { return TerminalInfoInteger(TERMINAL_CONNECTED) != 0; }
bool   BrkStableRead(const datetime now_srv) { return true; }
double BrkGridStop(const int sym, const double stop, const int side) { return stop; }
int    BrkOpen(CrIntent &it, const double sl) { return CR_SEND_FAIL; }
bool   BrkClose(const ulong ticket, const long magic, const string why) { return false; }
bool   BrkModify(const ulong ticket, const double sl) { return false; }
bool   BrkCloseAll(const long magic, const string why) { return false; }
#endif

// ==== end src/CR_Broker.mqh
// ==== begin src/CR_Follower.mqh
//+------------------------------------------------------------------+
//| CR_Follower.mqh - the account follows the paper (SPEC 4): intents,|
//| sizing calls, stops, exits, duplicates, reconcile, NOT_READY      |
//| exits by LatestExit, the broker-stop invariant. Owner: J.         |
//|                                                                  |
//| S0 STUB: final signatures; does nothing.                         |
//| API (J keeps these signatures):                                  |
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
// (already inlined: CR_Journal.mqh)
// (already inlined: CR_Registry.mqh)
// (already inlined: CR_Paper.mqh)
// (already inlined: CR_Ledger.mqh)
// (already inlined: CR_Sizing.mqh)
// (already inlined: CR_Broker.mqh)

bool FolInit(string &err) { err = ""; return true; }
void FolReset() {}
void FolOnPaperEvent(const CrPEvent &e, const bool live) {}
void FolOnMinute(const datetime M, const bool live) {}
void FolOnTimer(const datetime now_srv) {}
bool FolReconcile(const datetime now_srv) { return true; }
void FolOnTransaction(const MqlTradeTransaction &trans) {}
#endif

// ==== end src/CR_Follower.mqh
// ==== begin src/CR_Guards.mqh
//+------------------------------------------------------------------+
//| CR_Guards.mqh - the live protections of SPEC 6 (plan stop and     |
//| disaster guard close-all and mark, daily lock, Friday close,     |
//| clock check), the instance lock and watch (SPEC 4.9), the        |
//| self-test runner. Owner: J.                                       |
//|                                                                  |
//| S0 STUB: final signatures, neutral bodies.                       |
//| API (J keeps these signatures):                                  |
//|   GrdInit(err)                  once at OnInit                   |
//|   GrdLockTake()                 instance lock (heartbeat);       |
//|                                 false = another copy runs        |
//|   GrdLockRefresh()              every timer pass                 |
//|   GrdLockRelease()              OnDeinit                         |
//|   GrdSelfTest(why)              false blocks trading             |
//|   GrdOnTimer(now_srv)           equity guard, clock check, locks |
//|   GrdOnTick(now_srv)            first tick after a reopening     |
//|   GrdEntryBlock(now_srv)        CR_SK_* reason that blocks new   |
//|                                 entries now, CR_SK_NONE if none  |
//|   GrdMaySend()                  false for an observer copy       |
//+------------------------------------------------------------------+
#ifndef CR_GUARDS_MQH
#define CR_GUARDS_MQH
// (already inlined: CR_Types.mqh)
// (already inlined: CR_Journal.mqh)
// (already inlined: CR_Ledger.mqh)
// (already inlined: CR_Broker.mqh)

bool GrdInit(string &err) { err = ""; return true; }
bool GrdLockTake() { return true; }
void GrdLockRefresh() {}
void GrdLockRelease() {}
bool GrdSelfTest(string &why) { why = ""; return true; }
void GrdOnTimer(const datetime now_srv) {}
void GrdOnTick(const datetime now_srv) {}
int  GrdEntryBlock(const datetime now_srv) { return CR_SK_NONE; }
bool GrdMaySend() { return !g_cfg.observer; }
#endif

// ==== end src/CR_Guards.mqh
// ==== begin src/CR_Golden.mqh
//+------------------------------------------------------------------+
//| CR_Golden.mqh - GENERATED by tools/gen_golden.py (step K): the    |
//| self-test vectors of T10 (clock instants, NYSE dates,            |
//| AddTradingDays, BusinessDays, F1 scores, riskbp, risk tables,    |
//| Wilder and SMA series), checked at OnInit.                       |
//|                                                                  |
//| S0 STUB: no vector; GoldenCheck passes. Do not edit by hand.     |
//+------------------------------------------------------------------+
#ifndef CR_GOLDEN_MQH
#define CR_GOLDEN_MQH
// (already inlined: CR_Types.mqh)

bool GoldenCheck(string &why)
  {
   why = "";
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
   for(int s = 0; s < CR_NSYM; s++) kv = kv + KV(g_sym[s].base, g_sym[s].name);
   Jrn(CR_EV_INIT, "-", kv);
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
      Jrn(CR_EV_PLAN, "-", KT("T", LedPlanStart()) + KV("state", st) + KB("demo", g_cfg.demo) + KD("B_T", LedBalance(LedPlanStart()))
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
   Jrn(CR_EV_REBUILD, "-", KI("n", g_rebuilds) + KT("from", start) + KT("to", M1) + KI("minutes", minutes)
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
      Jrn(CR_EV_LATEBAR, "-", KT("M", M));
      g_st = CR_ST_WAIT;
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
   Jrn(CR_EV_SELFTEST, "-", KB("ok", st) + KV("why", why));
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
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   Jrn(CR_EV_INIT, "-", KI("deinit", reason) + KI("lines", g_jrn_lines) + KI("bars_fed", g_tot_fed) + KI("rebuilds", g_rebuilds));
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
