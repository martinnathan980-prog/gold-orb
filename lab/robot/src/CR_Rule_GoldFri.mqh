//+------------------------------------------------------------------+
//| CR_Rule_GoldFri.mqh - GFP GOLD_FRI_PM: Friday 13:30 NY buy limit  |
//| on gold (SPEC 3). Owner: G.                                       |
//|                                                                  |
//| S0 STUB: final signatures, neutral bodies.                       |
//+------------------------------------------------------------------+
#ifndef CR_RULE_GOLDFRI_MQH
#define CR_RULE_GOLDFRI_MQH
#include "CR_Types.mqh"
#include "CR_Clock.mqh"
#include "CR_Math.mqh"

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
