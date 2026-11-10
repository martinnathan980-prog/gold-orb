"""Block D2: remaining ideas of the brief (documentation trials)."""
from runner import trial
# breakout bracket on the pre-release 30-minute range, active from T+2m (first minute untradeable), pooled events
for sym in ("us100", "us500", "xauusd"):
    trial(sym, dict(rule="brk", k=2, pre_win=30, valid=30, buf_atr=0.0, exit="hold", hold=120, stop_atr=0.5), tag="D:brk")
# pre-FOMC drift (Lucca & Moench): long 24 h before the statement, out 5 minutes before it
for sym in ("us500", "us100"):
    trial(sym, dict(rule="long", kinds="fomc", lead=1440, exit="hold", hold=-5, stop_atr=1.0), tag="D:pre-fomc")
# FOMC reaction momentum on the indices (same settings as the gold variants)
for sym in ("us500", "us100"):
    trial(sym, dict(rule="mom", kinds="fomc", k=5, stop_atr=0.5, exit="hhmm", exit_hhmm="15:55", exit_days=1), tag="D:fomc-mom-idx")
# fade of the NFP reaction on the indices
for sym in ("us500", "us100"):
    trial(sym, dict(rule="fade", kinds="nfp", k=5, exit="hold", hold=60, stop_atr=0.5), tag="D:nfp-fade")
