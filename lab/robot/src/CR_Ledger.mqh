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
//|   for 60 s: then the latest value is accepted and pushed. The     |
//|   walk always starts from the accepted B(T).                      |
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
#include "CR_Types.mqh"
#include "CR_Clock.mqh"
#include "CR_Journal.mqh"

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
datetime  g_led_T_built = -1;          // T of the tables
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
   g_led_T_utc = (g_led_T > 0) ? ClkServerToUtc(g_led_T) : 0;
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

// the settle rule (SPEC 5, R16) on the B(T) of one read
void LedSettle(const double v, const datetime now)
  {
   if(!g_led_acc)
     {
      if(g_led_has_cand && MathAbs(v - g_led_cand_v) <= CR_LED_TOL)
        {
         if(now - g_led_cand_t >= CR_LED_SETTLE_GAP)
           {
            g_led_acc = true;
            g_led_acc_v = v;
            g_led_has_prev = false;
            g_led_settled = true;
            g_led_move_t = 0;
           }
        }
      else
        {
         g_led_has_cand = true;
         g_led_cand_v = v;
         g_led_cand_t = now;
         g_led_settled = false;
        }
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
   if(now - g_led_move_t >= CR_LED_SETTLE_MAX)
     {
      g_led_acc_prev = g_led_acc_v;
      g_led_has_prev = true;
      g_led_acc_v = v;
      g_led_settled = true;
      g_led_move_t = 0;
      LedSettleLine("accepted", v);
      JrnPush("solde et historique en desaccord depuis 60 s : nouveau solde de depart du plan accepte (" + DoubleToString(v, 2) + ")", false);
     }
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

datetime LedPlanStart() { return (g_led_plan == CR_PLAN_UNSET) ? 0 : g_led_T; }
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

// ---- latches (SPEC 6.1, 6.2) --------------------------------------------------------------------------------------
datetime LedStopTime() { return (g_led_stop_ev >= 0) ? g_led_e[g_led_stop_ev].t : 0; }
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

bool LedDayLocked(const datetime now_srv)
  {
   if(!g_led_settled) return false;                 // no LOCK conclusion while the ledger moves (SPEC 5)
   return LedDayLockedAt(ClkServerToUtc(now_srv) + 1);
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
   g_led_T_built = -1;
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
   if(g_cfg.plan_start < 0)
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
