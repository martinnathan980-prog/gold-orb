//+------------------------------------------------------------------+
//| CR_Rule_Brk72.mqh - BKB / BKE brk72_24h_wd on BTC and ETH, with   |
//| S0.75r (BKB) and K1 (BKE) behind their switches (SPEC 3).         |
//| Owner: E.                                                         |
//|                                                                  |
//| S0 STUB: final signatures, neutral bodies.                       |
//|   Init(sl) parses g_cfg.k1t for the sleeve whose change is K1    |
//|   ("YYYY:T;YYYY:T", bp, 17 significant digits); a string that    |
//|   does not parse returns false (ERROR at OnInit).                |
//|   Brk72K1Known(year): a T > 0 exists for that year (the driver   |
//|   pushes "K1 with no T for the year" when the switch is on).     |
//+------------------------------------------------------------------+
#ifndef CR_RULE_BRK72_MQH
#define CR_RULE_BRK72_MQH
#include "CR_Types.mqh"
#include "CR_Clock.mqh"
#include "CR_Math.mqh"

class CRuleBrk72
  {
public:
   int      sl;
   bool     Init(const int sleeve) { sl = sleeve; return true; }
   void     OnBar(const int sym, const CrBar &b, CrOut &out) {}
   void     OnMinute(const datetime M, CrOut &out) {}
   datetime LatestExit(const datetime open_time, const datetime comment_dec) { return 0; }
  };

bool Brk72K1Known(const int year) { return false; }
#endif
