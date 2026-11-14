"""Round 6 frames (PROTOCOL_V3 Addendum L, night_fade): data/r6/<cross>_m1.parquet from data/raw_r6. IN SAMPLE ONLY.

For each of the twelve crosses of dl_round6.py:
  - the 9 bid and 9 ask files of 2013-2021 (data/raw_r6/<cross>-m1-<side>-<year>.csv.gz) are read one by one with
    pyarrow.dataset, with the row filter timestamp < 2022-01-01 00:00 UTC applied inside the read call (to_table);
  - they are merged exactly as prep_round3._merge (imported, not copied: prep_round3._read is replaced by the filtered
    reader below, which keeps _read's semantics: files in sorted order, duplicates dropped keeping the first, sorted):
    inner join of bid and ask on the minute, flat bid minutes and minutes with zero volume on both sides dropped,
    crossed minutes (ask close < bid close, ask high < bid high or ask low < bid low) dropped;
  - the weekday rule of prep_round3.fx: keep minutes whose (New York time + 7 h).dayofweek < 5;
  - written with its 'ts' index (UTC, nanoseconds) to data/r6/<cross>_m1.parquet; max(ts) < 2022-01-01 asserted.
The base frame of Addendum L (commission folded into the quotes) is NOT stored: common.load_base builds it in memory
from this frame (one formula, h = 0.5 x c x 1e-4 x the bar's mid close on all four bid and ask prices).
A summary of the build goes to data/r6/frames_info.json (rows, first and last bar, minutes dropped by each rule).

    python3 -I frames.py            # all twelve crosses (skips a cross whose frame exists)
    python3 -I frames.py eurcad     # one cross
"""
import glob
import json
import os
import sys

sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow.compute as pc  # noqa: E402
import pyarrow.dataset as pds  # noqa: E402

LAB = "/home/user/gold-orb/lab"
if LAB not in sys.path:
    sys.path.insert(0, LAB)
import dl_round6  # noqa: E402  (the fixed list of crosses and years)
import prep_round3  # noqa: E402  (its _merge is used as is; its fx() is never called: it writes data/r3 and data/fp)
from goldlab.data import NY  # noqa: E402

RAW6 = os.path.join(LAB, "data", "raw_r6")
R6 = os.path.join(LAB, "data", "r6")
CUT = pd.Timestamp("2022-01-01", tz="UTC")
CUT_MS = int(CUT.value // 10**6)
YEARS = list(range(dl_round6.FIRST_YEAR, dl_round6.LAST_YEAR + 1))
assert YEARS == list(range(2013, 2022))
INFO = os.path.join(R6, "frames_info.json")


def read_side_r6(sym, side):
    """Replacement of prep_round3._read for data/raw_r6, with the in-sample filter inside the read call."""
    files = sorted(glob.glob(os.path.join(RAW6, f"{sym}-m1-{side}-*.csv.gz")))
    years = [int(os.path.basename(p).split("-")[-1].split(".")[0]) for p in files]
    assert years == YEARS, (sym, side, years)          # exactly the 2013-2021 files, nothing later exists or is read
    fr = []
    for p in files:
        if os.path.getsize(p) == 0:
            continue
        tbl = pds.dataset(p, format="csv").to_table(filter=pc.field("timestamp") < CUT_MS)
        if tbl.num_rows == 0:
            continue
        d = tbl.to_pandas()
        assert int(d["timestamp"].max()) < CUT_MS
        d["ts"] = pd.to_datetime(d["timestamp"], unit="ms", utc=True)
        fr.append(d.drop(columns="timestamp").set_index("ts"))
    if not fr:
        return None
    df = pd.concat(fr)
    return df[~df.index.duplicated(keep="first")].sort_index()


def build(sym):
    """Merge, weekday rule, write; returns the build summary of the cross."""
    prep_round3._read = read_side_r6                     # _merge looks _read up in its module at call time
    b, a = read_side_r6(sym, "bid"), read_side_r6(sym, "ask")
    n_bid, n_ask = len(b), len(a)
    n_inner = int(len(b.index.intersection(a.index)))
    r = prep_round3._merge(sym)
    assert r is not None, sym
    raw, nbad = r
    n_merged = len(raw)
    ny = raw.index.tz_convert(NY)
    keep = (ny + pd.Timedelta(hours=7)).dayofweek < 5   # prep_round3.fx's weekday rule (Sunday 17:00 to Friday 17:00 NY)
    out = raw[keep].copy()
    out.index = out.index.as_unit("ns")
    out.index.name = "ts"
    assert list(out.columns) == ["bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"]
    assert out.index.is_monotonic_increasing and out.index.is_unique
    assert out.index.max() < CUT, "a timestamp >= 2022-01-01 is held"
    assert np.isfinite(out.to_numpy()).all()
    os.makedirs(R6, exist_ok=True)
    path = os.path.join(R6, f"{sym}_m1.parquet")
    out.to_parquet(path)
    info = {"cross": sym, "file": os.path.relpath(path, LAB), "rows": int(len(out)),
            "first_bar_utc": str(out.index[0]), "last_bar_utc": str(out.index[-1]),
            "max_ts_before_2022": bool(out.index.max() < CUT),
            "raw_bid_minutes": int(n_bid), "raw_ask_minutes": int(n_ask),
            "minutes_with_bid_and_ask": n_inner,
            "dropped_flat_or_zero_volume": int(n_inner - n_merged - nbad),
            "dropped_crossed": int(nbad),
            "dropped_weekday_rule": int(n_merged - len(out)),
            "bytes_on_disk": int(os.path.getsize(path))}
    print(json.dumps(info), flush=True)
    return info


def main(args):
    crosses = args or dl_round6.CROSSES
    for c in crosses:
        assert c in dl_round6.CROSSES, c
    info = {}
    if os.path.exists(INFO):
        info = json.load(open(INFO))
    for c in crosses:
        if os.path.exists(os.path.join(R6, f"{c}_m1.parquet")) and c in info and not args:
            print(c, "exists, skipped", flush=True)
            continue
        info[c] = build(c)
        with open(INFO, "w") as f:
            json.dump(info, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1:])
