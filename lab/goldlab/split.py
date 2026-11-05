"""Data periods and research bookkeeping.

IS       2013-01-01 .. 2021-12-31   research / tuning (free use)
VAL      2022-01-01 .. 2025-12-31   validation: ONLY the final pre-chosen config(s) of a track.
                                     Every access is logged to results/val_access.log.
HOLDOUT  2026-01-01 .. latest        not on disk; downloaded once at the very end by the lead.

Load the full M1 history to compute indicators (warm-up), then cut trades with `cut()`.
"""
import datetime as _dt
import json
import os

import pandas as pd

RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")

PERIODS = {
    "is": ("2013-01-01", "2022-01-01"),
    "val": ("2022-01-01", "2026-01-01"),
    "is+val": ("2013-01-01", "2026-01-01"),
    "holdout": ("2026-01-01", "2100-01-01"),
}


def cut(trades, period, track=None, label=None):
    """Keep trades whose entry falls in `period`. Accessing 'val' / 'is+val' requires
    track+label and is logged."""
    a, b = PERIODS[period]
    if period in ("val", "is+val", "holdout"):
        if not track or not label:
            raise ValueError("validation access needs track= and label= (it is logged)")
        os.makedirs(RESULTS, exist_ok=True)
        with open(os.path.join(RESULTS, "val_access.log"), "a") as f:
            f.write(json.dumps({"time": _dt.datetime.utcnow().isoformat(timespec="seconds"),
                                "track": track, "label": label, "period": period}) + "\n")
    ts = trades.entry_time
    return trades[(ts >= pd.Timestamp(a, tz="UTC")) & (ts < pd.Timestamp(b, tz="UTC"))]


def log_trial(track, config, metrics):
    """Append one evaluated configuration (IS metrics) to results/<track>/trials.jsonl.
    EVERY configuration you evaluate must be logged: the trial count is part of the evidence."""
    d = os.path.join(RESULTS, track)
    os.makedirs(d, exist_ok=True)
    keep = {k: v for k, v in metrics.items() if k not in ("by_year_R", "exit_reasons")}
    with open(os.path.join(d, "trials.jsonl"), "a") as f:
        f.write(json.dumps({"config": config, "is": keep}, default=str) + "\n")
