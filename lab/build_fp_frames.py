"""Build the FP Markets cost frames used by round 2:  lab/data/fp/<sym>_m1.parquet

Forward-looking cost model (PROTOCOL_V2 section 3): mid prices come from Dukascopy; the bid/ask
spread is today's FP Markets Standard spread expressed in basis points of price (r2/fp_costs.json,
converted at the average price of the last 60 trading days of the research data), with Dukascopy's
own intraday spread shape (spread / that trading day's median spread, clipped to [0.7, 6]) so that
rollover / off-hours / news widening is kept.

Usage: python3 lab/build_fp_frames.py [sym ...]
"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from goldlab.data import DATA, trading_day  # noqa: E402

SPEC = json.load(open(os.path.join(ROOT, "r2", "fp_costs.json")))


def build(sym, write=True):
    raw = pd.read_parquet(os.path.join(DATA, f"{sym}_m1.parquet"))
    raw = raw[raw.index < pd.Timestamp("2026-01-01", tz="UTC")]          # holdout is built separately
    spr = (raw.ac - raw.bc).clip(lower=0)
    mid_c = (raw.ac + raw.bc) / 2
    td = trading_day(raw.index)
    day_med = spr.groupby(td).transform("median").replace(0, np.nan)
    shape = (spr / day_med).clip(0.7, 6.0).fillna(1.0)
    ref = float(mid_c.iloc[-60 * 1380:].mean())
    bps = SPEC[sym]["spread"] / ref * 1e4
    hs = 0.5 * bps * 1e-4 * mid_c * shape
    out = pd.DataFrame(index=raw.index)
    for k in "ohlc":
        m = (raw["b" + k] + raw["a" + k]) / 2
        out["b" + k] = m - hs
        out["a" + k] = m + hs
    out = out[["bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"]].astype("float64")
    if write:
        os.makedirs(os.path.join(DATA, "fp"), exist_ok=True)
        out.to_parquet(os.path.join(DATA, "fp", f"{sym}_m1.parquet"))
    new_spr = out.ac - out.bc
    print(f"{sym}: ref price {ref:.2f} | FP spread {SPEC[sym]['spread']} = {bps:.2f} bp | modelled median spread: "
          f"first year {new_spr[: 300000].median():.4g}, last year {new_spr[-300000:].median():.4g} | "
          f"Dukascopy median last year {spr[-300000:].median():.4g} ({(spr / mid_c)[-300000:].median() * 1e4:.2f} bp)", flush=True)
    return bps


if __name__ == "__main__":
    syms = sys.argv[1:] or [s for s in SPEC if not s.startswith("_")]
    for s in syms:
        if os.path.exists(os.path.join(DATA, f"{s}_m1.parquet")):
            build(s)
        else:
            print(f"{s}: no raw parquet yet", flush=True)
