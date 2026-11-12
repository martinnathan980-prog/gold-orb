//+------------------------------------------------------------------+
//| CR_Paper.mqh - the paper engine (SPEC 2.5): a streaming port of   |
//| goldlab/sim.py _run per sleeve, gap rule, late gap revision,     |
//| hold extension, 3-spread refusals, void_le. Owner: C.             |
//|                                                                  |
//| S0 STUB: final signatures, neutral bodies (no trade, no event).  |
//| API (C keeps these signatures):                                  |
//|   PapInit()                 once at OnInit                       |
//|   PapReset()                every sleeve flat, no order (rebuild)|
//|   PapSubmit(o)              a rule's order; false = ERROR (two   |
//|                             pending orders of one sleeve)        |
//|   PapSubmitExit(e)          a rule's exit (CrExit)               |
//|   PapOnBar(sl, b)           one kept closed bar of the sleeve's  |
//|                             traded symbol, after the rules'      |
//|                             OnBar for that bar                   |
//|   PapOnBarrier(M)           every sleeve, once per barrier M:    |
//|                             windows that end, late gap revision, |
//|                             hold extension                       |
//|   PapEvents() PapEvent(k, e) PapClearEvents()   the event queue  |
//|   PapTrade(sl, t)           the open trade (a pending gap exit   |
//|                             counts as open); false when flat     |
//|   PapPending(sl, o)         the order waiting for its activation |
//|                             or fill; false when none             |
//|   PapLastExitBar(sl)        start of the last trade's exit bar   |
//| Slippage and the symbol of each sleeve: g_sl[] and g_sym[].      |
//+------------------------------------------------------------------+
#ifndef CR_PAPER_MQH
#define CR_PAPER_MQH
#include "CR_Types.mqh"

void     PapInit() {}
void     PapReset() {}
bool     PapSubmit(const CrOrder &o) { return true; }
bool     PapSubmitExit(const CrExit &e) { return true; }
void     PapOnBar(const int sl, const CrBar &b) {}
void     PapOnBarrier(const datetime M) {}
int      PapEvents() { return 0; }
bool     PapEvent(const int k, CrPEvent &e) { return false; }
void     PapClearEvents() {}
bool     PapTrade(const int sl, CrTrade &t) { return false; }
bool     PapPending(const int sl, CrOrder &o) { return false; }
datetime PapLastExitBar(const int sl) { return 0; }
#endif
