"""Round-3 frames from lab/data/raw_r3/*.csv.gz (dl_round3.py).

    python3 lab/prep_round3.py fx                 # 8 pairs  -> data/r3/<pair>_m1.parquet and data/fp/<pair>_m1.parquet
    python3 lab/prep_round3.py stocks [tickers]   # US shares -> data/r3/<ticker>_m1.parquet and data/fp/<ticker>_m1.parquet

FX: Dukascopy bid/ask merged as in prep_round2.py, then the FP Markets Raw cost frame (build_fp_frames logic:
today's all-in spread in basis points with Dukascopy's intraday spread shape).
US shares: regular session only (09:30-16:00 New York), Dukascopy's own bid/ask for the share CFD. The cost
frame adds the commission per share to the quotes (r2/fp_costs.json -> "_stocks": commission_per_share), then
back-adjusts the prices for splits (detected as an overnight price ratio close to a usual split ratio; written
to data/r3/splits.json) so that the series is continuous; costs stay proportional.
"""
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import dl_round3  # noqa: E402
from goldlab.data import DATA, NY, trading_day  # noqa: E402

RAW = os.path.join(DATA, "raw_r3")
R3 = os.path.join(DATA, "r3")
SPEC = json.load(open(os.path.join(ROOT, "r2", "fp_costs.json")))
RATIOS = [1.5, 2, 3, 4, 5, 6, 7, 8, 10, 15, 20, 25, 50]


def _read(sym, side):
    fr = []
    for p in sorted(glob.glob(os.path.join(RAW, f"{sym}-m1-{side}-*.csv.gz"))):
        try:
            d = pd.read_csv(p)
        except pd.errors.EmptyDataError:
            continue
        if len(d):
            d["ts"] = pd.to_datetime(d["timestamp"], unit="ms", utc=True)
            fr.append(d.drop(columns="timestamp").set_index("ts"))
    if not fr:
        return None
    df = pd.concat(fr)
    return df[~df.index.duplicated(keep="first")].sort_index()


def _merge(sym):
    b, a = _read(sym, "bid"), _read(sym, "ask")
    if b is None or a is None:
        return None
    df = b.add_prefix("b_").join(a.add_prefix("a_"), how="inner")
    flat = (df.b_open == df.b_high) & (df.b_high == df.b_low) & (df.b_low == df.b_close) & (df.b_close == df.b_close.shift(1))
    if "b_volume" in df:
        flat |= (df.b_volume <= 0) & (df.a_volume <= 0)
    df = df[~flat]
    bad = (df.a_close < df.b_close) | (df.a_high < df.b_high) | (df.a_low < df.b_low)
    df = df[~bad]
    out = pd.DataFrame({"bo": df.b_open, "bh": df.b_high, "bl": df.b_low, "bc": df.b_close,
                        "ao": df.a_open, "ah": df.a_high, "al": df.a_low, "ac": df.a_close}).astype("float64")
    return out, int(bad.sum())


def fx(pair):
    r = _merge(pair)
    if r is None:
        print(pair, "missing raw files")
        return
    raw, nbad = r
    ny = raw.index.tz_convert(NY)
    raw = raw[(ny + pd.Timedelta(hours=7)).dayofweek < 5]
    os.makedirs(R3, exist_ok=True)
    raw.to_parquet(os.path.join(R3, f"{pair}_m1.parquet"))
    spr = (raw.ac - raw.bc).clip(lower=0)
    mid_c = (raw.ac + raw.bc) / 2
    day_med = spr.groupby(trading_day(raw.index)).transform("median").replace(0, np.nan)
    shape = (spr / day_med).clip(0.7, 6.0).fillna(1.0)
    ref = float(SPEC[pair].get("spread_ref_price") or mid_c.iloc[-60 * 1380:].mean())
    bps = SPEC[pair]["spread"] / ref * 1e4
    hs = 0.5 * bps * 1e-4 * mid_c * shape
    out = pd.DataFrame(index=raw.index)
    for k in "ohlc":
        m = (raw["b" + k] + raw["a" + k]) / 2
        out["b" + k], out["a" + k] = m - hs, m + hs
    out = out[["bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"]].astype("float64")
    out.to_parquet(os.path.join(DATA, "fp", f"{pair}_m1.parquet"))
    print(f"{pair}: {len(out):,} bars {out.index[0]} -> {out.index[-1]} | crossed dropped {nbad} | FP all-in {SPEC[pair]['spread']} = {bps:.2f} bp "
          f"| Dukascopy median spread last year {(spr / mid_c)[-300000:].median() * 1e4:.2f} bp | "
          f"modelled spread at 17:00-18:00 NY / median: {float(shape[(ny.hour == 17)[: len(shape)]].median()) if len(shape) else 0:.2f}", flush=True)


def stock(tk):
    r = _merge(tk + "ususd")
    if r is None:
        print(tk, "missing raw files")
        return None
    raw, nbad = r
    ny = raw.index.tz_convert(NY)
    mins = ny.hour * 60 + ny.minute
    raw = raw[(mins >= 570) & (mins < 960) & (ny.dayofweek < 5)]
    ny = raw.index.tz_convert(NY)
    day = pd.Series(ny.date, index=raw.index)
    mid = (raw.bc + raw.ac) / 2
    d = pd.DataFrame({"o": ((raw.bo + raw.ao) / 2).groupby(day).first(), "c": mid.groupby(day).last(), "n": mid.groupby(day).size()})
    ratio = (d.c.shift(1) / d.o).dropna()
    splits = {}
    for dt, x in ratio.items():
        for q in RATIOS:
            if abs(x / q - 1) < 0.04 or abs(x * q - 1) < 0.04:          # split or reverse split
                splits[str(dt)] = q if abs(x / q - 1) < 0.04 else 1 / q
                break
    os.makedirs(R3, exist_ok=True)
    raw.to_parquet(os.path.join(R3, f"{tk}_m1.parquet"))
    c = float(SPEC["_stocks"]["commission_per_share"])
    out = raw.copy()
    for k in "ohlc":
        out["b" + k] -= c
        out["a" + k] += c
    factor = pd.Series(1.0, index=d.index)
    for dt, q in splits.items():
        factor[factor.index < pd.Timestamp(dt).date()] /= q
    f = day.map(factor).to_numpy()
    out = out.mul(f, axis=0)
    out.to_parquet(os.path.join(DATA, "fp", f"{tk}_m1.parquet"))
    spr = (raw.ac - raw.bc) / mid * 1e4
    first5 = (mins[(mins >= 570) & (mins < 960) & (raw.index.tz_convert(NY).dayofweek < 5)] < 575) if False else None
    m2 = ny.hour * 60 + ny.minute
    info = {"ticker": tk, "bars": int(len(raw)), "first": str(raw.index[0]), "last": str(raw.index[-1]), "days": int(len(d)),
            "full_days_pct": round(float((d.n >= 385).mean() * 100), 1), "crossed_dropped": nbad, "splits": splits,
            "price_last": round(float(mid.iloc[-1]), 2),
            "spread_bp_median": round(float(spr.median()), 2), "spread_bp_0930_0935": round(float(spr[m2 < 575].median()), 2),
            "spread_bp_0934": round(float(spr[m2 == 574].median()), 2), "spread_bp_last_year": round(float(spr[-98000:].median()), 2),
            "commission_bp_round_trip_last": round(float(2 * c / mid.iloc[-1] * 1e4), 2)}
    print(json.dumps(info), flush=True)
    return info


if __name__ == "__main__":
    what = sys.argv[1]
    if what == "fx":
        for p in (sys.argv[2:] or dl_round3.FX):
            fx(p)
    else:
        infos = [stock(t) for t in (sys.argv[2:] or dl_round3.STOCKS)]
        infos = [i for i in infos if i]
        old = {}
        pth = os.path.join(R3, "stocks_info.json")
        if os.path.exists(pth):
            old = {i["ticker"]: i for i in json.load(open(pth))}
        old.update({i["ticker"]: i for i in infos})
        json.dump(list(old.values()), open(pth, "w"), indent=1)
