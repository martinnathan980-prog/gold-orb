"""Block A: index long through the release (announcement premium), quick IS evaluations."""
from runner import trial
for sym in ("us500", "us100"):
    for hold in (5, 15, 30, 60):
        for stop in (0.5, 1.0):
            trial(sym, dict(rule="long", lead=5, exit="hold", hold=hold, stop_atr=stop), tag="A:prem")
    for stop in (0.5, 1.0):
        trial(sym, dict(rule="long", lead=5, exit="hhmm", exit_hhmm="15:55", stop_atr=stop), tag="A:day")
    trial(sym, dict(rule="long", lead=-5, exit="hhmm", exit_hhmm="15:55", stop_atr=1.0), tag="A:post")
