"""Lens `cluster` (PROTOCOL_V3, Addendum H): shared helpers. IN SAMPLE ONLY.

Every price frame is read with a parquet row filter `ts < 2022-01-01`, so no 2022+ bar ever enters memory; every
trades file is read with the filter `entry_time < 2022-01-01` in the same statement. Nothing here writes outside
`lab/r2/tracks/autopsy/cluster/` and `lab/results/r2/autopsy/cluster/`.

Clock (the one of `r2/tracks/stake/stake.py`): FP server time = New York local time + 7 h.
    day   = server calendar day, week = Monday..Sunday (server), month = server month.
    a trade's result is booked in the day / week of its EXIT time; a state seen at an entry uses only trades whose
    exit time is STRICTLY before the entry time.
"""
import os
import sys

os.environ.setdefault("NUMBA_CACHE_DIR", "/tmp/numba_cluster_lens")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

LAB = "/home/user/gold-orb/lab"
if LAB not in sys.path:
    sys.path.insert(0, LAB)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(LAB, "results", "r2", "autopsy", "cluster")
TRADES_DIR = os.path.join(OUT, "trades_is")
OFFICIAL_DIR = os.path.join(LAB, "results", "r2", "recalc", "trades")

IS_END = pd.Timestamp("2022-01-01", tz="UTC")
COMMON_START = pd.Timestamp("2018-02-01", tz="UTC")

# the ten sleeves (same list and order as r2/tracks/stake/stake.py SLEEVES)
SLEEVES = [("noise30", "us100"), ("ocm4", "us100"), ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"),
           ("nq_btc_follow", "btcusd"), ("F1_brk_ridge_filter", "btcusd"), ("F1_brk_ridge_filter", "ethusd"),
           ("GOLD_FRI_PM", "xauusd"), ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd")]
MARKETS = ("us100", "xauusd", "btcusd", "ethusd")
FAMILY = {"us100": 0, "xauusd": 1, "btcusd": 2, "ethusd": 2}
FAM_NAMES = ("us100", "gold", "crypto")


def sleeve_key(name, sym):
    return f"{name}_{sym}"


# tie-break among entries of the same minute: ASCII order of name_sym (as in stake.build_frame / account.py)
SLEEVE_KEYS = sorted(sleeve_key(n, s) for n, s in SLEEVES)


def load_is_frame(sym):
    """FP-cost M1 frame of `sym`, IN SAMPLE ONLY: the parquet is read with the row filter ts < 2022-01-01."""
    path = os.path.join(LAB, "data", "fp", f"{sym}_m1.parquet")
    df = pd.read_parquet(path, filters=[("ts", "<", IS_END)])
    assert len(df) and df.index.max() < IS_END and df.index.is_monotonic_increasing and df.index.is_unique
    return df


def read_official_is(name, sym):
    """Official trades of one sleeve, rows with entry_time < 2022-01-01 only (filter applied by the read itself)."""
    t = pd.read_parquet(os.path.join(OFFICIAL_DIR, f"{name}__{sym}.parquet"), filters=[("entry_time", "<", IS_END)])
    assert (t.entry_time < IS_END).all()
    return t


def read_my_trades(name, sym, mode):
    """Trades re-simulated by repro.py on the in-sample frames (mode 'fp' or 'stress')."""
    t = pd.read_parquet(os.path.join(TRADES_DIR, f"{name}__{sym}__{mode}.parquet"))
    assert (t.entry_time < IS_END).all()
    return t


def server_time(ts):
    """UTC timestamps -> naive FP server time (New York local time + 7 h)."""
    return pd.DatetimeIndex(ts).tz_convert("America/New_York").tz_localize(None) + pd.Timedelta(hours=7)


def clear_rule_caches():
    """The rule modules cache bars keyed on id(frame) and its ends: clear them before every call."""
    for mname, mod in list(sys.modules.items()):
        if mod is None:
            continue
        if not (mname.startswith("r2_") or mname.startswith("strategy_") or mname == "idxus_lib"):
            continue
        for attr in ("_cache", "_bar_cache", "_daily_cache", "_grid_cache", "_atr_cache"):
            c = getattr(mod, attr, None)
            if isinstance(c, dict):
                c.clear()
