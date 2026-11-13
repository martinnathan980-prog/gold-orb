//+------------------------------------------------------------------+
//|                                               ClaudeRobot.mq5    |
//|  One Expert Advisor holding the ten validated rules of the lab,  |
//|  the three changes kept by the 2022-2025 look (behind switches), |
//|  their sizing and their protections, for FP Markets (Raw, .r     |
//|  symbols, hedging, 1:500) on the MetaQuotes VPS.                 |
//|  Specification: lab/robot/SPEC.md. Installed as the single file  |
//|  dist/ClaudeRobot.mq5 built by tools/amalgam.py.                 |
//|                                                                  |
//|  Every rule keeps a paper chain (the lab's simulator run on the  |
//|  broker's closed M1 bars); the account follows it with market    |
//|  orders and a broker stop on every position. Nothing is kept     |
//|  between runs: every start rebuilds everything from the broker.  |
//+------------------------------------------------------------------+
#property copyright "gold-orb lab"
#property version   "2.00"
#property description "ClaudeRobot: ten lab rules on XAUUSD, US100, BTCUSD and ETHUSD; paper chains followed by market orders with broker stops."

// ---- the 15 inputs (SPEC 1). Plain types only.
input bool     InpTrade            = true;                          // Trade (VPS copy: false = no new entry; elsewhere: observe)
input datetime InpPlanStart        = 0;                             // Plan start, server time (0: no new entry on a real account)
input string   InpRiskTable        = "0:10;3000:5;10000:2;20000:1"; // Risk table from:pct, read on max(balance, money paid in) (D2)
input double   InpStopFallPct      = 0.0;                           // Plan stop: fall of the reference, percent (0 = no plan stop)
input double   InpStopArmPaid      = 12000.0;                       // Plan stop: armed once this much has been paid in
input bool     InpGuard            = false;                         // Disaster guard at -50 % of the reference (D2: off)
input string   InpSleeves          = "ALL";                         // Codes allowed to trade (the others: paper only)
input int      InpK1               = -1;                            // K1 on BKE: -1 demo on / real off, 0 off, 1 on
input int      InpH2               = -1;                            // H2 on F1E: -1 demo on / real off, 0 off, 1 on
input int      InpS075             = -1;                            // S0.75r on BKB: -1 demo on / real off, 0 off, 1 on
input string   InpK1T              = "";                            // K1 thresholds YYYY:T;YYYY:T in bp, from the lab
input double   InpDailyLockStakes  = 0.0;                           // Daily lock in stakes (0 = off)
input int      InpFridayCloseHHMM  = 0;                             // Friday close, server HHMM (0 = off)
input string   InpExtraClosures    = "";                            // Typed closures: NYSE d; HALF d; XAU|IDX|CRY d hh:mm-d hh:mm
input bool     InpPush             = true;                          // Push notifications
#ifdef CR_HARNESS
input string   InpScript           = "";                            // Harness: codes replaying ref_lab.py orders
input string   InpScriptDir        = "ClaudeRobot\\script";         // Harness: folder of the script files
#endif

#include <Trade\Trade.mqh>
#include "CR_Types.mqh"
#include "CR_Clock.mqh"
#include "CR_Journal.mqh"
#include "CR_Math.mqh"
#include "CR_Registry.mqh"
#include "CR_Bars.mqh"
#include "CR_Paper.mqh"
#include "CR_Ledger.mqh"
#include "CR_Sizing.mqh"
#include "CR_Broker.mqh"
#include "CR_Guards.mqh"                  // before CR_Follower.mqh, which includes it (amalgam: no first include inside a guard)
#include "CR_Follower.mqh"
#include "CR_Golden.mqh"
#include "CR_Main.mqh"
