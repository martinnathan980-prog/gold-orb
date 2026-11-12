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
#include "CR_Types.mqh"
#include "CR_Clock.mqh"
#include "CR_Journal.mqh"

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
