//+------------------------------------------------------------------+
//| CR_Rule_NqBtc.mqh - NQB nq_btc_follow: BTC follows a 6-sigma      |
//| US100 impulse (SPEC 3). Reads US100 and BTC bars. Owner: F.       |
//|                                                                  |
//| S0 STUB: final signatures, neutral bodies.                       |
//+------------------------------------------------------------------+
#ifndef CR_RULE_NQBTC_MQH
#define CR_RULE_NQBTC_MQH
#include "CR_Types.mqh"
#include "CR_Clock.mqh"
#include "CR_Math.mqh"

class CRuleNqb
  {
public:
   int      sl;
   bool     Init(const int sleeve) { sl = sleeve; return true; }
   void     OnBar(const int sym, const CrBar &b, CrOut &out) {}
   void     OnMinute(const datetime M, CrOut &out) {}
   datetime LatestExit(const datetime open_time, const datetime comment_dec) { return 0; }
  };
#endif
