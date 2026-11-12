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
#include <Trade\Trade.mqh>
#include "CR_Types.mqh"
#include "CR_Journal.mqh"

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
