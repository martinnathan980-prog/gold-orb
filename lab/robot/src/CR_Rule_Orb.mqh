//+------------------------------------------------------------------+
//| CR_Rule_Orb.mqh - ORX orb_asia_2d_buf10: London 00:00-07:00 range |
//| breakout on gold (SPEC 3). Owner: G.                              |
//|                                                                  |
//| S0 STUB: final signatures, neutral bodies.                       |
//+------------------------------------------------------------------+
#ifndef CR_RULE_ORB_MQH
#define CR_RULE_ORB_MQH
#include "CR_Types.mqh"
#include "CR_Clock.mqh"
#include "CR_Math.mqh"

class CRuleOrx
  {
public:
   int      sl;
   bool     Init(const int sleeve) { sl = sleeve; return true; }
   void     OnBar(const int sym, const CrBar &b, CrOut &out) {}
   void     OnMinute(const datetime M, CrOut &out) {}
   datetime LatestExit(const datetime open_time, const datetime comment_dec) { return 0; }
  };
#endif
