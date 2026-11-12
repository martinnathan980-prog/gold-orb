//+------------------------------------------------------------------+
//| CR_Rule_Donch.mqh - D4H donch4h_stop: 60 x 4h channel OCO with a  |
//| 2-ATR trailing stop on gold (SPEC 3). Owner: H.                   |
//|                                                                  |
//| S0 STUB: final signatures, neutral bodies.                       |
//+------------------------------------------------------------------+
#ifndef CR_RULE_DONCH_MQH
#define CR_RULE_DONCH_MQH
#include "CR_Types.mqh"
#include "CR_Clock.mqh"
#include "CR_Math.mqh"

class CRuleDonch
  {
public:
   int      sl;
   bool     Init(const int sleeve) { sl = sleeve; return true; }
   void     OnBar(const int sym, const CrBar &b, CrOut &out) {}
   void     OnMinute(const datetime M, CrOut &out) {}
   datetime LatestExit(const datetime open_time, const datetime comment_dec) { return 0; }
  };
#endif
