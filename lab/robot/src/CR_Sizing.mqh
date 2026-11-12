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
#include "CR_Types.mqh"
#include "CR_Ledger.mqh"

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
