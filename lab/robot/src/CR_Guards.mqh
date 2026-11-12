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
#include "CR_Types.mqh"
#include "CR_Journal.mqh"
#include "CR_Ledger.mqh"
#include "CR_Broker.mqh"

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
