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
#include "CR_Types.mqh"
#include "CR_Journal.mqh"
#include "CR_Registry.mqh"
#include "CR_Paper.mqh"
#include "CR_Ledger.mqh"
#include "CR_Sizing.mqh"
#include "CR_Broker.mqh"

bool FolInit(string &err) { err = ""; return true; }
void FolReset() {}
void FolOnPaperEvent(const CrPEvent &e, const bool live) {}
void FolOnMinute(const datetime M, const bool live) {}
void FolOnTimer(const datetime now_srv) {}
bool FolReconcile(const datetime now_srv) { return true; }
void FolOnTransaction(const MqlTradeTransaction &trans) {}
#endif
