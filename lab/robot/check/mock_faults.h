// mock_faults.h - scripted broker failures for the replay mock (SPEC 7, T8). Owner: J.
//
// S0 STUB: every hook is neutral (no fault). mock_replay.h includes this file after its internals (rp_pos, rp_deals,
// rp_orders, rp_syms, rp_res, rp_now ...), so a world can read and change them. Hooks:
//   mf_init()                 once after the bars, the state, the payments and the scripted deals are loaded
//                             (read the world from MOCK_FAULTS, e.g. a file name)
//   mf_copyrates_fail(sym)    true: this CopyRates call fails (-1, error 4066)
//   mf_request(req, res)      before a trade request: 0 = the normal path; 1 = handled here (set res; a requote, a
//                             timeout, a refused stop, a slow reply whose position appears later ...)
//   mf_after(req, res)        after a request (e.g. drop the SL the broker just accepted, add a duplicate)
//   mf_event(T)               at each event T, before OnTick / OnTimer (late bars, rewritten comments, a hand-removed
//                             SL, disconnections ...)
//   mf_connected()            TerminalInfoInteger(TERMINAL_CONNECTED)
//   mf_session(sym, dow, idx, from, to)   SymbolInfoSessionTrade: -1 = no information (default), 0 = false, 1 = true
#pragma once

static void mf_init() {}
static bool mf_copyrates_fail(const string &) { return false; }
static int  mf_request(MqlTradeRequest &, MqlTradeResult &) { return 0; }
static void mf_after(const MqlTradeRequest &, MqlTradeResult &) {}
static void mf_event(long) {}
static bool mf_connected() { return true; }
static int  mf_session(const string &, int, uint, datetime &, datetime &) { return -1; }
