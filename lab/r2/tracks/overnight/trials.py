"""All engine trials of the overnight track, by batch (each configuration is logged by common.trial).
Usage: python3 trials.py <batch> [<batch> ...]
"""
import importlib.util
import os
import sys

from common import LAB, S, r2, trial

WD = (0, 1, 2, 3, 4)
ALL = (0, 1, 2, 3, 4, 5, 6)


def gold_predeclared():
    """PRE-DECLARED single re-check: round-1 gold Friday-afternoon / weekend drift, round-1 definition
    (the two round-1 finalists, parameters untouched), now under FP costs."""
    spec = importlib.util.spec_from_file_location("seasonality_strategy", os.path.join(LAB, "tracks", "seasonality", "strategy.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for name, p in mod.FINALISTS.items():
        trial("xauusd", dict(p), f"gold R1 {name} (pre-declared)", full=True, make_orders=mod.make_orders,
              extra={"rule": "round1.seasonality." + name})


def btc_stops():
    """Bitcoin late-US-day drift: 17:05 -> 19:00 New York, every day; stop width."""
    for k in (1.0, 2.0, 3.0):
        trial("btcusd", dict(tz="NY", entry="17:05", exit="19:00", weekdays=ALL, side=1, stop_atr=k, atr_tf="1h"),
              f"btc 17:05->19:00 NY stop {k}xATR1h")


def idx_night():
    """Overnight drift of the index CFDs, with financing: cash close -> next cash open."""
    for sym in ("us500", "us100"):
        trial(sym, dict(tz="NY", entry="15:55", exit="09:30", exit_next=True, weekdays=WD, side=1, stop_atr=1.0, atr_tf="D"),
              "night 15:55->09:30 NY, always")
    trial("ger40", dict(tz="BER", entry="17:25", exit="09:00", exit_next=True, weekdays=WD, side=1, stop_atr=1.0, atr_tf="D",
                        sess_open="09:00", sess_close="17:30"), "night 17:25->09:00 Berlin, always")


def idx_night_up():
    """Same night, only after an UP cash session (overnight continuation)."""
    for sym in ("us500", "us100"):
        trial(sym, dict(tz="NY", entry="15:55", exit="09:30", exit_next=True, weekdays=WD, side=1, stop_atr=1.0, atr_tf="D",
                        cond="sess_up"), "night 15:55->09:30 NY | session up")
    trial("ger40", dict(tz="BER", entry="17:25", exit="09:00", exit_next=True, weekdays=WD, side=1, stop_atr=1.0, atr_tf="D",
                        cond="sess_up", sess_open="09:00", sess_close="17:30"), "night 17:25->09:00 Berlin | session up")


def idx_evening():
    """Evening session -> next cash open (no financing: entry after the 17:00 NY rollover). Data: 2013-15, 2018+."""
    for sym in ("us500", "us100"):
        trial(sym, dict(tz="NY", entry="18:30", exit="09:30", exit_next=True, weekdays=(6, 0, 1, 2, 3), side=1, stop_atr=1.0,
                        atr_tf="D"), "evening 18:30->09:30 NY, always")
        trial(sym, dict(tz="NY", entry="18:30", exit="09:30", exit_next=True, weekdays=(0, 1, 2, 3), side=1, stop_atr=1.0,
                        atr_tf="D", cond="sess_up"), "evening 18:30->09:30 NY | session up")


def idx_fade():
    """Cash session after a DOWN cash session (intraday reversal), long only; and the symmetric fade."""
    for sym in ("us100", "us500"):
        for k in (0.5, 1.0):
            trial(sym, dict(tz="NY", entry="09:30", exit="16:00", weekdays=WD, side=1, stop_atr=k, atr_tf="D",
                            cond="prev_sess_down"), f"cash 09:30->16:00 | prev session down, stop {k}xATR(D)")
        trial(sym, dict(tz="NY", entry="09:30", exit="16:00", weekdays=WD, stop_atr=1.0, atr_tf="D", cond="fade_prev_sess"),
              "cash 09:30->16:00 fade prev session (L+S)")
    trial("ger40", dict(tz="BER", entry="09:00", exit="17:30", weekdays=WD, side=1, stop_atr=1.0, atr_tf="D",
                        cond="prev_sess_down", sess_open="09:00", sess_close="17:30"), "xetra 09:00->17:30 | prev session down")


def idx_month_end():
    """Turn of the month: the night from the last cash close of the month to the first cash open (one config)."""
    for sym in ("us500", "us100"):
        trial(sym, dict(tz="NY", entry="15:55", exit="09:30", exit_next=True, weekdays=WD, side=1, stop_atr=1.0, atr_tf="D",
                        cond="month_end"), "month-end night 15:55->09:30 NY")
    trial("ger40", dict(tz="BER", entry="17:25", exit="09:00", exit_next=True, weekdays=WD, side=1, stop_atr=1.0, atr_tf="D",
                        cond="month_end", sess_open="09:00", sess_close="17:30"), "month-end night 17:25->09:00 Berlin")


def btc_full():
    """Bitcoin late-day drift, base config with cost stress / gross / every-signal (re-run of trial 4 -> trial 23)."""
    trial("btcusd", dict(tz="NY", entry="17:05", exit="19:00", weekdays=ALL, side=1, stop_atr=2.0, atr_tf="1h"),
          "btc 17:05->19:00 NY stop 2.0xATR1h (FULL re-run of trial 4)", full=True, extra={"rerun_of": 4})


def btc_limit():
    """Bitcoin late-day drift with a passive entry: buy-limit at the last bid, valid 30 minutes (trial 27)."""
    trial("btcusd", dict(tz="NY", entry="17:05", exit="19:00", weekdays=ALL, side=1, stop_atr=2.0, atr_tf="1h",
                         entry_type="limit", limit_min=30), "btc 17:05->19:00 NY, LIMIT at last bid 30min, stop 2.0xATR1h", full=True)


# order in which the batches were run on 2026-11-10 (then neighbors.py gold btc month_end, finalists_is.py,
# validate_finalists.py, diag_gold.py market):
#   gold_predeclared, btc_stops, idx_night, idx_night_up, idx_evening, idx_fade, btc_full, idx_month_end, btc_limit
BATCHES = {f.__name__: f for f in (gold_predeclared, btc_stops, idx_night, idx_night_up, idx_evening, idx_fade, idx_month_end,
                                   btc_full, btc_limit)}

if __name__ == "__main__":
    for b in sys.argv[1:]:
        print(f"--- batch {b}: {BATCHES[b].__doc__.strip().splitlines()[0]}", flush=True)
        BATCHES[b]()
    r2.free()
