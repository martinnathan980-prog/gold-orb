"""Build parquet M1 bid/ask frames for the round-2 markets from lab/data/raw_r2/*.csv.gz
(one file per symbol / side / year, written by dl_round2.py).

Usage:  python3 lab/prep_round2.py [alias ...]
Output: lab/data/<alias>_m1.parquet   (us100, us500, us30, ger40, xagusd, btcusd, ethusd)
"""
import glob
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "data", "raw_r2")
OUT = os.path.join(ROOT, "data")

ALIAS = {"us100": "usatechidxusd", "us500": "usa500idxusd", "us30": "usa30idxusd", "ger40": "deuidxeur",
         "xagusd": "xagusd", "btcusd": "btcusd", "ethusd": "ethusd"}
CRYPTO = {"btcusd", "ethusd"}          # trade on weekends: keep Saturday / Sunday bars


def _read(sym, side):
    fr = []
    for p in sorted(glob.glob(os.path.join(RAW, f"{sym}-m1-{side}-*.csv.gz"))):
        d = pd.read_csv(p)
        if len(d) == 0:
            continue
        d["ts"] = pd.to_datetime(d["timestamp"], unit="ms", utc=True)
        fr.append(d.drop(columns="timestamp").set_index("ts"))
    if not fr:
        return None
    df = pd.concat(fr).sort_index()
    return df[~df.index.duplicated(keep="first")]


def build(alias):
    sym = ALIAS[alias]
    b, a = _read(sym, "bid"), _read(sym, "ask")
    if b is None or a is None:
        print(f"{alias}: missing raw files", file=sys.stderr)
        return
    df = b.add_prefix("b_").join(a.add_prefix("a_"), how="inner")
    # filler minutes (market closed): flat bar equal to the previous close
    flat = (df.b_open == df.b_high) & (df.b_high == df.b_low) & (df.b_low == df.b_close) & (df.b_close == df.b_close.shift(1))
    df = df[~flat]
    if alias not in CRYPTO:
        ny = df.index.tz_convert("America/New_York")
        df = df[(ny + pd.Timedelta(hours=7)).dayofweek < 5]
    bad = (df.a_close < df.b_close) | (df.a_high < df.b_high) | (df.a_low < df.b_low)
    nbad = int(bad.sum())
    df = df[~bad]
    out = pd.DataFrame({"bo": df.b_open, "bh": df.b_high, "bl": df.b_low, "bc": df.b_close,
                        "ao": df.a_open, "ah": df.a_high, "al": df.a_low, "ac": df.a_close}).astype("float64")
    out.to_parquet(os.path.join(OUT, f"{alias}_m1.parquet"))
    spr = out.ac - out.bc
    mid = (out.ac + out.bc) / 2
    by = (spr / mid * 1e4).groupby(out.index.year).median().round(2)
    print(f"{alias}: {len(out):,} bars {out.index[0]} -> {out.index[-1]} | crossed dropped {nbad} | "
          f"median spread {spr.median():.4g} ({(spr / mid).median() * 1e4:.2f} bp) | bp by year {by.to_dict()}", flush=True)


if __name__ == "__main__":
    for al in (sys.argv[1:] or list(ALIAS)):
        build(al)
