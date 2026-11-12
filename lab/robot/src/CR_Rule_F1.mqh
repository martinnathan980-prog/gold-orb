//+------------------------------------------------------------------+
//| CR_Rule_F1.mqh - F1B / F1E F1_brk_ridge_filter on BTC and ETH,    |
//| with H2 (F1E) behind its switch (SPEC 3). Owner: E.               |
//| The frozen scorecard comes from the generated CR_F1Model.mqh.    |
//|                                                                  |
//| S0 STUB: final signatures, neutral bodies.                       |
//+------------------------------------------------------------------+
#ifndef CR_RULE_F1_MQH
#define CR_RULE_F1_MQH
#include "CR_Types.mqh"
#include "CR_Clock.mqh"
#include "CR_Math.mqh"
#include "CR_F1Model.mqh"

class CRuleF1
  {
public:
   int      sl;
   bool     Init(const int sleeve) { sl = sleeve; return true; }
   void     OnBar(const int sym, const CrBar &b, CrOut &out) {}
   void     OnMinute(const datetime M, CrOut &out) {}
   datetime LatestExit(const datetime open_time, const datetime comment_dec) { return 0; }
  };
#endif
