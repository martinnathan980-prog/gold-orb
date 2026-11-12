"""validation_hi -- data readers. Every read carries the row filter of the run's CUT (vhi_guard checks it again).

frame(sym)              FP-cost M1 frame of `sym`, rows with bar start ts < CUT (filtered while reading)
official_count(...)     official rows of a sleeve entered before CUT: count, and how many of them closed at/after CUT
                        (reads entry_time and exit_time only)
official_closed(...)    official rows entered AND closed before CUT (both filters in the read): no result realised
                        at or after CUT is ever read
"""
import os

import numpy as np
import pandas as pd

import vhi_guard as G

LAB = G.LAB
FP_DIR = os.path.join(LAB, "data", "fp")


def frame(sym):
    cut = G.current_cut()
    df = pd.read_parquet(os.path.join(FP_DIR, f"{sym}_m1.parquet"), filters=[("ts", "<", cut)])
    df.attrs = {}
    assert len(df) and df.index.is_monotonic_increasing and df.index.is_unique and df.index.max() < cut
    return df


def leader_series(m1_us100):
    """us100 mid closes of the cut slice: the leader of nq_btc_follow (synthesis_B's convention)."""
    return ((m1_us100["bc"] + m1_us100["ac"]) / 2).astype("float64")


def official_count(name, sym):
    cut = G.current_cut()
    t = pd.read_parquet(os.path.join(G.OFFICIAL_DIR, f"{name}__{sym}.parquet"), columns=["entry_time", "exit_time"],
                        filters=[("entry_time", "<", cut)])
    assert (t.entry_time < cut).all()
    return int(len(t)), int((t.exit_time >= cut).sum())


def official_closed(name, sym):
    cut = G.current_cut()
    t = pd.read_parquet(os.path.join(G.OFFICIAL_DIR, f"{name}__{sym}.parquet"),
                        filters=[("entry_time", "<", cut), ("exit_time", "<", cut)])
    t.attrs = {}                         # the file's attrs describe the full-period run: never carried
    assert (t.entry_time < cut).all() and (t.exit_time < cut).all()
    return t.sort_values("entry_time", kind="stable").reset_index(drop=True)


def trades_file(path, extra_filters=()):
    """Any in-sample trades file of a lens (entry_time < CUT in the read; asserted)."""
    cut = G.current_cut()
    t = pd.read_parquet(path, filters=[("entry_time", "<", cut)] + list(extra_filters))
    t.attrs = {}
    assert (t.entry_time < cut).all()
    return t


def ns(ts):
    return pd.DatetimeIndex(ts).tz_convert("UTC").as_unit("ns").asi8


def bar_index(m1, ts):
    """Index of the bar whose start equals each timestamp (asserted present)."""
    i = np.searchsorted(m1.index.values, pd.DatetimeIndex(ts).tz_convert("UTC").values.astype(m1.index.values.dtype))
    return i
