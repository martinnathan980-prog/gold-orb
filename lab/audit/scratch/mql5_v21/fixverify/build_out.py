import json
S = "lab/audit/scratch/mql5_v21/fixverify/"
verdict = ("PASS with 1 partial FAIL and 5 minor regressions; nothing blocks compiling (F7). All 21 fixes are present. "
 "20 meet their intent. F6 fails on its requirement that 'TRADE_RETCODE_NO_CHANGES must count as success': Sent() only "
 "accepts it when OrderSend returned true, and OrderSend does not return true for a 10025 reply. "
 "The paper engine still equals ea_twin.py. The only change in ProcessBar is AskOHL (lines 477-478). "
 "Decide runs on the first M1 bar of each new bucket (lines 880-884, twin lines 96-104). "
 "tc = ToUTC(previous bar) + 60, computed once per bucket and kept across Decide retries (line 882, twin line 99). "
 "The deadline is DeadlineUTC(tc) (lines 824 and 459, twin line 139) and expiry is bucket + 4h (lines 825 and 511, twin line 128). "
 "Replay is n > 5 (line 873). The end-of-replay block runs Reconcile, RealOnBar, Notify, then re-arms after OffsetOK (lines 897-906). "
 "Mode 0 sends no orders: every trade call is behind g_auto or InpMode. A leftover real ticket no longer blocks anything (lines 798 and 967). "
 "State and journal names are symbol + login (lines 273, 287, 301, 313, 959). SaveState does nothing before AccountReady and in the tester (line 300). "
 "The tester journal is deleted at OnInit (line 987) and keeps the name tester_journal_<symbol>.csv. "
 "compare_journal.read_journal pairs v2.10 rows correctly on a synthetic journal (" + S + "journal_check.py). "
 "Fix the 5 issues below before the mode-2 demo; issues 1-3 matter most.")
fs = [
 ("F1","PASS","TickTrigger (lines 910-928) no longer calls the binder. OnTick line 1009 and OnTimer line 1019 call BindManualPosition() right after CatchUp(). The binder (lines 649-680) has the guard at 651 and takes the side from fill vs init_stop (652), so it still works after the paper exits. Window [-600 s, +6 h] at 660 matches README line 22. real_id is set at 663. The stop is placed at once (lines 669-672, NormPrice per F17), then the REAL_BIND row and SaveState. Remaining edge case: problem 4."),
 ("F2","PASS","Line 873 g_replay = (n > 5). End-of-replay block (lines 897-906): g_replay=false, Reconcile, RealOnBar(r[n-1]), Notify('...bougies M1 termine'), then PlacePendings re-arm behind g_auto/br_active/side==0/expiry/!RealPositionSelected/OffsetOK. The re-arm only happens when n > 5; problem 3."),
 ("F3","PASS","g_ready and g_key at lines 89-90. FileKey() at line 273 is used at lines 287, 301 and 313. SaveState returns early when !g_ready (line 300). AccountReady (lines 954-974): waits for a login and a connection (958), key = symbol_login (959), LoadState (960), real-account guard now runs here (962-966). OnInit (lines 988-994) resets g/g_ready/g_key/g_auto, then calls AccountReady. OnTick and OnTimer return while it is false (lines 1007 and 1017). OnTradeTransaction does nothing while g_auto is false (line 1031). No Journal call can run before the account is ready. README lines 81-82 give the new file names."),
 ("F4","PASS","Decide line 798 only checks g.side. Line 836: if(g_auto) { Reconcile(); if(!RealPositionSelected()) PlacePendings(); }. AccountReady line 967 clears real_ticket in mode 0. TickTrigger and ProcessBar ignore real_ticket."),
 ("F5","PASS","Decide deletes the orders before any early return (line 797). PaperEnter deletes them too (line 462). OnDeinit deletes them on REMOVE or CHARTCLOSE (line 1001). The line-462 deletion introduces problem 1. The OnDeinit reason list leaves orphan orders on a mode, magic or symbol change (problem 3)."),
 ("F6","FAIL","Flags, PlacePendings branches, Sent() and VirtualEntry are implemented: globals at 96, reset at 586-587 and 795-796, flags set at 616/618, VirtualEntry at 622-645 called at 1010. Two of the fix's stated guarantees do not hold. (a) 'NO_CHANGES must count as success' fails: line 545 tests ok && (... || rc == TRADE_RETCODE_NO_CHANGES), and OrderSend returns false for 10025, so the false alarm on the re-anchor is still there (problem 2). (b) The fix relies on 'PlacePendings re-arms the flags after a restart (the F2 re-arm)', which is true only when n > 5. After an ordinary short restart, g_vbuy/g_vsell are lost (problem 3)."),
 ("F7","PASS","RealTimeExit (lines 756-774): one try every 15 s (760-761), success only on DONE (762), one alert per position (768-772), SaveState on close (766). OnTimer calls it at 1020 and FlushPush at 1024. PushNow at 216-221 and FlushPush at 244-249 pace pushes at 7 s with a queue of 20 (232-234). The Telegram queue is capped at 50 (238-240)."),
 ("F8","PASS","Sent() wraps the order calls at lines 613-617 and 643-644, the second-leg close at 1042, the re-anchor at 1055 and the Reconcile close at 691. The Algo Trading warning is in AccountReady (968-969). The re-anchor still raises a false alarm (problem 2)."),
 ("F9","PASS","Reconcile (lines 683-715) adopts a magic position opened while the EA was down. It takes the ATR from Build4H(dec), computes real_best from M1 bars since the open, deletes pending orders, writes REAL_ADOPT and saves state. It is called from Decide (836), at the end of replay (900) and every 60 s in OnTimer (1021-1022). Its deadline counts from the bucket start, not tc (problem 5)."),
 ("F10","PASS","RealOnBar (lines 717-754): during replay it only tracks the extreme (727). It trails at InpTrailATR x ATR (728). It closes the position when the rule stop is already crossed (737-747). Stop moves go through Sent (752). End of replay calls it once (901)."),
 ("F11","PASS","CatchUp waits for a connection and a synchronized M1 series (856-857). GAP_RESET when the gap exceeds TERMINAL_MAXBARS (861-871). Decide checks M5 sync and writes one DATA_WARN per bucket (802-814)."),
 ("F12","PASS","OnInit line 987 deletes GoldOrb/tester_journal_<symbol>.csv. SaveState skips the tester (line 300). compare_journal.read_journal (lines 27-41) pairs each EXIT with the ENTRY before it and drops duplicates. On a synthetic v2.10 journal (" + S + "journal_check.py) it found exactly the 2 complete trades and dropped the cut-off ENTRY and the GAP_RESET ENTRY."),
 ("F13","PASS","AskOHL (lines 411-430) reads ticks only outside replay. ProcessBar uses it at 477-478 and RealOnBar uses it on the short side at 720-726. This is the only change to the paper engine."),
 ("F14","PASS","Line 202: Paris date and time first, UTC in brackets."),
 ("F15","PASS","PlacePendings lines 592-603: one alert per day, with the corrected advice."),
 ("F16","PASS","OnInit lines 978-983 return INIT_PARAMETERS_INCORRECT on out-of-range inputs."),
 ("F17","PASS","LotsForRisk rounds the volume to the step's decimals (394-395). NormPrice (376-380) is used at 611, 613-617, 643-644, 669, 729, 731 and 1055."),
 ("F18","PASS","g_jbuf global at 95. Journal (lines 278-295) builds each row once, buffers up to 500, flushes in order and keeps the same columns."),
 ("F19","PASS","SaveState (298-308) writes a .tmp, checks the FileWriteStruct size and swaps it in with FileMove + REWRITE. LoadState (310-322) checks both the bytes read and the file size."),
 ("F20","PASS","real_id field at 74. RealPositionSelected (570-581) falls back to POSITION_IDENTIFIER. real_id is set at 663, 695 and 1047. The second-leg OCO test is at 1039. The GoState size changed, so an old state file is rejected once."),
 ("F21","PASS","g_tc_bucket/g_tc globals at 99. CatchUp lines 882-883 set g_tc = ToUTC(last_m1) + 60 once per bucket, so it survives Decide retries. Decide(bucket, tc) at 791 stores br_decision_utc = tc (824) and expiry = bucket + 14400 (825); LEVELS row still on bucket (827). OnTradeTransaction (1052) uses the same tc. This matches ea_twin.py (dec=tc, twin lines 99/104)."),
]
fix1 = """Line 432 becomes:
void DeletePendings();                 // declarations (definies plus bas)
void DeleteOpposite(const int side);
Line 462 becomes:
   if(g_auto) DeleteOpposite(side);   // le reel ne prend jamais le cote oppose ; l'ordre du meme cote vit jusqu'a la fin de la fenetre (Decide l'efface)
Insert after line 568 (end of DeletePendings):
// PaperEnter : n'efface que l'ordre stop oppose. Sur la bougie de decision, Decide->PlacePendings passe juste
// avant ProcessBar->PaperEnter : effacer aussi l'ordre du meme cote supprimait le trade reel.
void DeleteOpposite(const int side)
  {
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong t = OrderGetTicket(i);
      if(t == 0 || OrderGetString(ORDER_SYMBOL) != _Symbol || OrderGetInteger(ORDER_MAGIC) != InpMagic) continue;
      long ot = OrderGetInteger(ORDER_TYPE);
      if((side > 0 && ot == ORDER_TYPE_SELL_STOP) || (side < 0 && ot == ORDER_TYPE_BUY_STOP)) g_trade.OrderDelete(t);
     }
  }
F5 still holds: the opposite stop is deleted, and Decide (line 797) deletes the same-side stop at the next 4h close. The case where that level was within STOPS_LEVEL (virtual entry) stays uncovered; it is rare."""
fix2 = """Replace lines 1054-1055 with:
   double sl0 = NormPrice(g.real_fill - side * g.real_D);
   if(PositionSelectByTicket(pos) && MathAbs(PositionGetDouble(POSITION_SL) - sl0) > _Point / 2)   // rempli au niveau : stop deja juste, pas de requete (10025 = faux refus)
      Sent(g_trade.PositionModify(pos, sl0, PositionGetDouble(POSITION_TP)), "recalage du stop initial");
Optional, so the F6 rule holds everywhere: line 545 becomes
   if(rc == TRADE_RETCODE_NO_CHANGES || (ok && (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_DONE_PARTIAL || rc == TRADE_RETCODE_PLACED)))"""
fix3 = """After line 99:
bool     g_rearm = false;               // mode 2 : re-armer la fenetre en cours apres un (re)demarrage
In OnInit, after line 991:
   g_rearm = true;    // OnDeinit a pu retirer les ordres ; g_vbuy/g_vsell ne survivent pas a un redemarrage
Line 836 becomes:
      if(g_auto) { g_rearm = false; Reconcile(); if(!RealPositionSelected()) PlacePendings(); }
In the end-of-replay block, after line 905 and still inside the block:
      g_rearm = false;                  // deja re-arme ci-dessus
Before line 907 (SaveState(); at the end of CatchUp):
   if(g_rearm)   // 1re bougie traitee apres un (re)demarrage sans rattrapage (n <= 5)
     {
      g_rearm = false;
      if(g_auto)
        {
         Reconcile();
         if(g.br_active != 0 && g.side == 0 && ToUTC(TimeCurrent()) < g.br_expiry_utc && !RealPositionSelected() && OffsetOK())
            PlacePendings();
        }
     }
Line 1001 becomes:
   if(g_auto && reason != REASON_CLOSE && reason != REASON_ACCOUNT) DeletePendings();   // retire, parametres, graphique, modele, recompilation : pas d'ordre orphelin ; re-arme au redemarrage
The re-arm runs only after a new closed M1 bar has been processed, so never while the market is closed (no false 'market closed' refusal at a weekend restart). Orders are kept on REASON_CLOSE so that Reconcile can adopt a fill made during the shutdown."""
fix4 = """Insert after line 651 in BindManualPosition:
   if(g.side == 0 && g.br_active != 0 && g.br_trigger_sent != 0) return;   // cassure signalee, ENTRY papier a la cloture de la M1 : attendre (sinon rattachement au trade precedent)
br_active is set to 0 by PaperEnter. The binder therefore resumes within about 60 s of the alert and binds to the new trade, which has the right ATR and deadline."""
fix5 = """Line 703 becomes:
      bool same = (g.entry_utc != 0 && BucketUTC(g.entry_utc) == dec && ((g.fill > g.init_stop) ? 1 : -1) == g.real_side);
      g.real_deadline_utc = same ? g.deadline_utc : DeadlineUTC(dec, InpMaxDays);   // = papier : echeance depuis t_close (F21)"""
problems = [
 {"severity":"minor","line":"462 (PaperEnter) with 836 and 883-885 (Decide->PlacePendings runs before ProcessBar on the same bar)",
  "problem":("Regression from F5 in mode 2. On the decision bar (the first M1 bar of a 4h bucket), CatchUp calls Decide at line 883. "
   "Decide calls PlacePendings at 836 using the tick that comes after that bar closed. Only then does ProcessBar at 885 run the same bar. "
   "If that bar already crossed a level, the paper enters, and PaperEnter line 462 'if(g_auto) DeletePendings();' deletes the two stops "
   "placed a few ms earlier. When the price is already back inside the channel at decision time, the market path at 613/614 does not fire either, "
   "so mode 2 gets no trade while the paper and the lab do. v2.0 kept the same-side stop live. Twin replay 2013-2026 (" + S + "scenarios.py, out_scenarios.txt): "
   "16 of 787 trades enter on the decision bar. 5 of those are back inside at decision time (+6.72 R in total, including +5.64 R on 2017-12-27). "
   "The v2.0 same-side stop would have filled 4 of the 5 later in the window."),
  "fix":fix1},
 {"severity":"minor","line":"1054-1055 (OnTradeTransaction stop re-anchor), 545 (Sent)",
  "problem":("F6 requires TRADE_RETCODE_NO_CHANGES to count as success. Line 545 accepts it only when ok == true. "
   "[MQL5 OrderSend](https://www.mql5.com/en/docs/trading/ordersend) says it returns true only 'if the order is successfully accepted by the trade server'. "
   "A 10025 'No changes in request' reply ([return codes](https://mql5.com/en/docs/constants/errorswarnings/enum_trade_return_codes)) is not an acceptance, "
   "so CTrade::PositionModify returns false. The re-anchor target NormPrice(fill - D) is the SL the order already has in two common cases. "
   "One is a stop that fills exactly at NormPrice(br_hi/br_lo), whose SL is NormPrice(hi - D) or NormPrice(lo + D) (lines 615/617). "
   "The other is a market order (613/614/643/644) that fills at the requested price. Both are normal on a demo account. "
   "The result is an ORDER_FAIL row and a push 'recalage du stop initial REFUSE par le courtier (No changes)' on most mode-2 fills during the demo-vs-paper protocol. "
   "No trading impact; this rests on OrderSend returning false for 10025, which its documentation implies."),
  "fix":fix2},
 {"severity":"minor","line":"897-906 (re-arm only when n > 5), 1001 (OnDeinit), 96, 988-991",
  "problem":("Mode 2 is re-armed only after a replay. (a) A restart with 5 or fewer bars to catch up (a normal terminal restart or recompile) loses the globals g_vbuy/g_vsell. "
   "A level that was within STOPS_LEVEL then has no order and no virtual entry for the rest of the window. "
   "This contradicts F6's premise that the F2 re-arm restores them. (b) After remove plus re-attach within 5 minutes, OnDeinit (line 1001) has deleted both stops. "
   "Nothing re-places them until the next 4h close, while the reloaded paper still has br_active = 1. "
   "(c) OnDeinit deletes only on REASON_REMOVE or REASON_CHARTCLOSE. Switching mode 2 to 0 or 1, changing InpMagic, changing the chart symbol or applying a template "
   "leaves live stops that the new instance never manages. On a broker without SPECIFIED expiry such a GTC stop can fill days later "
   "as a position with a fixed SL, no trailing stop and no time exit."),
  "fix":fix3},
 {"severity":"minor","line":"651-660 (BindManualPosition)",
  "problem":("Edge case of the F1 binder. While the paper is flat after a trade P1 and a new same-side breakout alert fires, a trader who opens within about a minute "
   "(before the ENTRY is recorded at the M1 close) is bound to P1: sig, entry_utc, g.atr and g.deadline_utc all still describe P1, "
   "and 'opened <= P1.entry + 6 h' holds. Twin 2013-2026 has 5 of 787 trades that re-enter on the same side within 6 h of the previous entry "
   "(2.2-5.8 h; " + S + "out_scenarios.txt). For those, P1's ATR is 14-33% smaller, so the stop is that much tighter than the rule's. "
   "The deadline is 4 h early, and the REAL_BIND push shows the wrong exit time."),
  "fix":fix4},
 {"severity":"minor","line":"698-703 (Reconcile)",
  "problem":("F9 and F21 disagree. Reconcile sets real_deadline_utc = DeadlineUTC(BucketUTC(fill), ...), counted from the bucket start. "
   "The paper and OnTradeTransaction (line 1052) count from tc (the close of the previous bar). For the Sunday-open, holiday and data-hole windows, "
   "a position adopted after downtime gets a later time exit than the paper: Fri 15:55 NY instead of Thu 16:55 NY for the Sunday window in EDT. "
   "F21's analysis found no historical trade held long enough for this to matter."),
  "fix":fix5},
]
out = {"lens":"FIX VERIFICATION & REGRESSIONS (EA v2.10 vs final.fixes F1-F21 and lab/live/ea_twin.py)","verdict":verdict,
       "fix_status":[{"id":a,"status":b,"evidence":c} for a,b,c in fs],"problems":problems}
open("/home/user/gold-orb/lab/audit/scratch/mql5_v21/fixverify/structured_output.json","w").write(json.dumps(out, ensure_ascii=True))
print(len(json.dumps(out)))
