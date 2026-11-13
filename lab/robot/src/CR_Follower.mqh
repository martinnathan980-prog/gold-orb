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
//|   test on the live paper quote, M neither masked for the symbol   |
//|   nor in a known closure (BarsShut: the paper can never fill on a |
//|   masked bar, review F2), and the symbol ticked in minute M (else |
//|   it is armed and the first tick of M makes the intent). An       |
//|   observer makes the same intents (sized NOTRADE, never sent), so |
//|   its journal equals the VPS copy's with InpTrade false (F6).     |
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
//| Send (SPEC 4.3): just before every request the entry blocks are  |
//|   read again (GrdEntryBlock, READY, review F4) and no request goes |
//|   in a minute that is masked or in a known closure (BarsShut,     |
//|   F2): the intent waits inside its window, then MISSED with that  |
//|   reason. BrkIntentCheck first (one intent, one trade): a         |
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
//|   the price has already crossed -> close. A position of a         |
//|   NOT_READY or unfollowed sleeve has no expected stop: its stop   |
//|   must lie on the right side of the market; one that a fresh quote|
//|   has crossed for 2 min (the broker did not execute it) is closed |
//|   (SLFIX why=wrong_side, review F8).                              |
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
//|   them at LatestExit(POSITION_TIME, comment) with the gap rule,   |
//|   only once the first READY check since the load has decided and  |
//|   the sleeve has been NOT_READY for 10 min: review F1):           |
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
#include "CR_Types.mqh"
#include "CR_Clock.mqh"
#include "CR_Journal.mqh"
#include "CR_Registry.mqh"
#include "CR_Bars.mqh"
#include "CR_Paper.mqh"
#include "CR_Ledger.mqh"
#include "CR_Sizing.mqh"
#include "CR_Broker.mqh"
#include "CR_Guards.mqh"

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
#define CR_FOL_NOTREADY_WAIT 600        // NOT_READY exits: 10 min of NOT_READY after the first READY check of the load (F1)
#define CR_FOL_WRONG_S 120              // an unknown position's stop crossed by a fresh quote for 2 min -> closed (F8)
#define CR_FOL_FRESH_S 10               // a quote at most 10 s old is fresh

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
ulong      g_fol_ws_tk[CR_FOL_CMAX];    // positions of no expected stop whose stop a fresh quote has crossed (F8) ...
datetime   g_fol_ws_t[CR_FOL_CMAX];     // ... since when (server) ...
datetime   g_fol_ws_last[CR_FOL_CMAX];  // ... and the last fresh quote that showed it (server)
int        g_fol_nws = 0;

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
   if(BarsShut(g_sl[sl].sym, M)) return false;                  // a masked minute or a known closure: no bar the paper keeps
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
   // just before the request: the entry blocks again (a STOP, GUARD, LOCK, FRIDAY or CLOCK that came after the sizing,
   // a sleeve no longer READY: review F4), and never a request in a masked minute or a known closure (review F2); the
   // intent waits inside its window, then MISSED with that reason
   int blk = GrdEntryBlock(now);
   if(blk == CR_SK_NONE && (!FolReady(sl) || g_fol[sl].rec_due)) blk = CR_SK_NOTREADY;
   if(blk != CR_SK_NONE || BarsShut(s, nu))
     {
      g_fol[sl].last_why = (blk != CR_SK_NONE) ? blk : CR_SK_LATE;
      g_fol_why[sl] = (blk != CR_SK_NONE) ? "" : "market_shut";
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

// a position with no expected stop whose stop fresh quotes have shown crossed: true once that has lasted CR_FOL_WRONG_S
// (the broker did not execute the stop); a fresh quote on the right side forgets it; more than 70 s without a fresh quote
// showing it (a market that closed meanwhile) starts the count again
bool FolWrongSide(const ulong t, const bool wrong, const datetime now)
  {
   int k = -1;
   for(int j = 0; j < g_fol_nws; j++)
      if(g_fol_ws_tk[j] == t) k = j;
   if(!wrong)
     {
      if(k >= 0)
        {
         for(int j = k + 1; j < g_fol_nws; j++)
           {
            g_fol_ws_tk[j - 1] = g_fol_ws_tk[j];
            g_fol_ws_t[j - 1] = g_fol_ws_t[j];
            g_fol_ws_last[j - 1] = g_fol_ws_last[j];
           }
         g_fol_nws--;
        }
      return false;
     }
   if(k >= 0 && (now < g_fol_ws_last[k] || (long)(now - g_fol_ws_last[k]) > 70)) g_fol_ws_t[k] = now;   // a gap: again
   if(k < 0)
     {
      if(g_fol_nws >= CR_FOL_CMAX) return false;
      k = g_fol_nws;
      g_fol_ws_tk[k] = t;
      g_fol_ws_t[k] = now;
      g_fol_nws++;
     }
   g_fol_ws_last[k] = now;
   return (long)(now - g_fol_ws_t[k]) >= CR_FOL_WRONG_S;
  }

// forget the positions of FolWrongSide that are no longer open
void FolWrongSideTidy()
  {
   for(int j = g_fol_nws - 1; j >= 0; j--)
      if(!PositionSelectByTicket(g_fol_ws_tk[j])) FolWrongSide(g_fol_ws_tk[j], false, 0);
  }

void FolInvariant(const datetime now)
  {
   if(!GrdMaySend()) return;
   FolWrongSideTidy();
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
      if(!known)
        {
         // NOT_READY or unfollowed (SPEC 4.4): no expected stop, but the stop must lie on the right side of the market; only a
         // fresh quote decides (a stale one changes nothing)
         if(q && (long)(now - tq) <= CR_FOL_FRESH_S)
           {
            bool wrong = (side > 0 && cur >= bid) || (side < 0 && cur <= ask);
            if(FolWrongSide(t, wrong, now)) FolSlfix(sl, t, m, "wrong_side", now);
           }
         continue;
        }
      FolWrongSide(t, false, now);
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
   if(!ready) return;                                          // a NOT_READY sleeve keeps its positions (FolNotReadyExits)
   bool may = GrdMaySend();                                    // an observer (or a copy without the lock) sends nothing:
   // 2. the positions of the magic                            // steps 2 and 3 are skipped, step 4 makes its intents
   if(may) FolMapPositions(sl, now);
   // 3. the followed position against the paper (SPEC 4.5)
   ulong tk = may ? g_fol[sl].ticket : 0;
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
   // 4. a market order activating at M (an observer's intent is sized NOTRADE and never sent: its journal then equals the
   //    VPS copy's with InpTrade false, SPEC 10.2 and 10.12, review F6)
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

// -1 while one of the sleeve's symbols has had no READY check since the load, else how long (s) the sleeve has been
// NOT_READY since that first check (0 = READY)
long FolNotReadyFor(const int sl, const datetime now)
  {
   long a = BarsNotReadyFor(g_sl[sl].sym, now);
   if(a < 0) return -1;
   if(g_sl[sl].sym2 >= 0)
     {
      long b = BarsNotReadyFor(g_sl[sl].sym2, now);
      if(b < 0) return -1;
      if(b > a) a = b;
     }
   return a;
  }

// positions of NOT_READY sleeves keep their stops and close at LatestExit(POSITION_TIME, comment) (SPEC 4.8, P9), only
// once the first READY check since the load has decided and the sleeve has stayed NOT_READY for 10 min: every rebuild
// starts NOT_READY, and a symbol becomes READY 2 s after the load (about 3 min with an accepted hole), when the
// reconcile adopts the positions of the open paper trades (review F1)
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
      if(FolNotReadyFor(sl, now) < CR_FOL_NOTREADY_WAIT) continue;
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
   g_fol_nws = 0;
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
