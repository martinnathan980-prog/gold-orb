"""Lead-only tool: prepared hourly BID bars (in sample only) from the lab's own one-minute files, for kit.data.load_bars.
The lab's minute files exist only on the lead's machine (lab/data, not in git). Rows are filtered INSIDE the parquet
read (ts < 2022-01-01 UTC): nothing of 2022 or later is loaded. Output: <out>/<key>.parquet with a UTC bar-open index
'time' (the hour that holds the minutes: a bar labelled 14:00 holds 14:00-14:59, also when the market opened at 14:30),
columns open high low close (BID) and volume (= number of one-minute bars in the hour, not traded volume).
Usage: python3 -B lab/explore/lead/build_h1_from_lab.py <out dir> key=relative/path_m1.parquet [key=...]"""
import json
import os
import sys

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

LAB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data")


def build(key, rel, out):
    p = os.path.join(LAB, rel)
    tstype = pq.ParquetFile(p).schema_arrow.field("ts").type
    tz = "UTC" if getattr(tstype, "tz", None) else None
    end = pa.scalar(pd.Timestamp("2022-01-01", tz=tz).to_pydatetime(), type=tstype)
    start = pa.scalar(pd.Timestamp("2013-01-01", tz=tz).to_pydatetime(), type=tstype)
    df = pq.read_table(p, columns=["ts", "bo", "bh", "bl", "bc"], filters=[("ts", "<", end), ("ts", ">=", start)]).to_pandas()
    if "ts" not in df.columns:
        df = df.reset_index()
    ts = pd.DatetimeIndex(df.ts)
    ts = ts.tz_localize("UTC") if ts.tz is None else ts.tz_convert("UTC")
    assert ts.max() < pd.Timestamp("2022-01-01", tz="UTC") and ts.is_monotonic_increasing, key
    g = df.groupby(ts.floor("h"), sort=True)
    o = pd.DataFrame({"open": g["bo"].first(), "high": g["bh"].max(), "low": g["bl"].min(), "close": g["bc"].last(),
                      "volume": g["bo"].size().astype(float)})
    o.index.name = "time"
    o.to_parquet(os.path.join(out, f"{key}.parquet"))
    return {"rows_m1": int(len(df)), "bars_h1": int(len(o)), "first": str(o.index[0]), "last": str(o.index[-1]),
            "median_close": float(o.close.median()), "bars_per_day_median": float(o.groupby(o.index.normalize()).size().median())}


if __name__ == "__main__":
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    info_p = os.path.join(out, "info.json")
    info = json.load(open(info_p)) if os.path.exists(info_p) else {"made_from": "lab/data M1 BID (Dukascopy), in sample only", "markets": {}}
    for a in sys.argv[2:]:
        key, rel = a.split("=", 1)
        info["markets"][key] = build(key, rel, out)
        print(key, info["markets"][key], flush=True)
    json.dump(info, open(info_p, "w"), indent=1)
