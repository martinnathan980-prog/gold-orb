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
#include "CR_Types.mqh"
#include "CR_Clock.mqh"
#include "CR_Math.mqh"

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
