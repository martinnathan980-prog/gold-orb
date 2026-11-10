"""Blocks B (gold long through releases), C (FOMC reaction momentum), D (other ideas of the brief)."""
from runner import trial
# B: same calendar-long rule on gold
trial("xauusd", dict(rule="long", lead=5, exit="hold", hold=15, stop_atr=1.0), tag="B:prem")
trial("xauusd", dict(rule="long", lead=5, exit="hhmm", exit_hhmm="15:55", stop_atr=1.0), tag="B:day")
# C: gold reaction momentum after FOMC
for k, ex in ((5, dict(exit="hold", hold=120)), (5, dict(exit="hhmm", exit_hhmm="15:55")), (5, dict(exit="hhmm", exit_hhmm="15:55", exit_days=1)),
              (30, dict(exit="hhmm", exit_hhmm="15:55")), (30, dict(exit="hhmm", exit_hhmm="15:55", exit_days=1))):
    trial("xauusd", dict(rule="mom", kinds="fomc", k=k, stop_atr=0.5, **ex), tag="C:fomc-mom")
# D: pooled reaction momentum, all kinds, three markets
for sym in ("xauusd", "us500", "us100"):
    trial(sym, dict(rule="mom", k=5, exit="hhmm", exit_hhmm="15:55", stop_atr=0.5), tag="D:mom-all")
