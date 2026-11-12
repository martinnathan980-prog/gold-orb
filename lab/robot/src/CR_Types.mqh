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
