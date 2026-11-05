"""Convert the raw Dukascopy CSV.gz files in ../download into clean parquet files.

Usage:  python3 lab/prep_data.py

Outputs (lab/data/, git-ignored, regenerate any time):
  xauusd_m1.parquet   M1 bars, bid + ask OHLC, UTC, flat filler minutes removed
  <sym>_m1.parquet    other instruments (bid only in the raw data; ask = bid + fixed spread)
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "..", "download")
OUT = os.path.join(ROOT, "data")

# Fixed spreads (price units) for instruments with bid-only data: typical retail ECN all-in.
SYNTH_SPREAD = {
    "eurusd": 0.00010,   # 1.0 pip incl. commission equivalent
    "gbpusd": 0.00015,
    "usdjpy": 0.012,
    "deuidxeur": 1.5,    # DAX points
    "lightcmdusd": 0.04, # WTI
}


def _read(path):
    df = pd.read_csv(path)
    df["ts"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return df.drop(columns="timestamp").drop_duplicates("ts").set_index("ts").sort_index()


def _drop_flat(df, col_o, col_h, col_l, col_c):
    """Remove filler minutes (market closed): O=H=L=C and equal to previous close,
    and anything on a weekend trading day (Sat/Sun, day boundary 17:00 New York)."""
    flat = (df[col_o] == df[col_h]) & (df[col_h] == df[col_l]) & (df[col_l] == df[col_c])
    same = df[col_c] == df[col_c].shift(1)
    df = df[~(flat & same)]
    ny = df.index.tz_convert("America/New_York")
    tday = (ny + pd.Timedelta(hours=7)).dayofweek
    return df[tday < 5]


def _read_all(pattern):
    """Read main files + download/patch/ files matching `pattern`; main data wins on duplicates,
    patch files only fill minutes that are missing (failed downloads)."""
    main = sorted(glob.glob(os.path.join(RAW, pattern)))
    patch = sorted(glob.glob(os.path.join(RAW, "patch", pattern)))
    df = pd.concat([_read(p) for p in main] + [_read(p) for p in patch])
    df = df[~df.index.duplicated(keep="first")].sort_index()
    return df, len(patch)


def prep_gold():
    b, nb = _read_all("xauusd-m1-bid-*.csv.gz")
    a, na = _read_all("xauusd-m1-ask-*.csv.gz")
    df = b.add_prefix("bid_").join(a.add_prefix("ask_"), how="inner")
    df = _drop_flat(df, "bid_open", "bid_high", "bid_low", "bid_close")
    # sanity: ask >= bid
    bad = (df.ask_close < df.bid_close) | (df.ask_low < df.bid_low - 5)
    df = df[~bad]
    df.columns = [c.replace("bid_open", "bo").replace("bid_high", "bh").replace("bid_low", "bl")
                  .replace("bid_close", "bc").replace("ask_open", "ao").replace("ask_high", "ah")
                  .replace("ask_low", "al").replace("ask_close", "ac") for c in df.columns]
    df = df.astype("float64")
    df.to_parquet(os.path.join(OUT, "xauusd_m1.parquet"))
    spr = df.ac - df.bc
    print(f"xauusd: {len(df):,} bars {df.index[0]} -> {df.index[-1]}  median spread {spr.median():.3f}"
          f"  (patch files: {nb} bid, {na} ask)")


def prep_other():
    syms = sorted({os.path.basename(p).split("-")[0] for p in glob.glob(os.path.join(RAW, "*-m1-bid-*.csv.gz"))})
    for sym in syms:
        if sym == "xauusd":
            continue
        b, nb = _read_all(f"{sym}-m1-bid-*.csv.gz")
        b = _drop_flat(b, "open", "high", "low", "close")
        s = SYNTH_SPREAD.get(sym, 0.0)
        df = pd.DataFrame({
            "bo": b.open, "bh": b.high, "bl": b.low, "bc": b.close,
            "ao": b.open + s, "ah": b.high + s, "al": b.low + s, "ac": b.close + s,
        }).astype("float64")
        df.to_parquet(os.path.join(OUT, f"{sym}_m1.parquet"))
        print(f"{sym}: {len(df):,} bars {df.index[0]} -> {df.index[-1]}  synthetic spread {s}  (patch files: {nb})")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    prep_gold()
    prep_other()
