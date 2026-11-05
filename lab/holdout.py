"""FINAL HOLDOUT TEST (2026). Run once, after the candidate list is frozen.

Usage:
  bash lab/get_holdout.sh            # downloads 2026 M1 data into lab/holdout_raw/download/
  python3 lab/holdout.py             # builds lab/data/holdout/*.parquet, patches holes, runs candidates

Candidates come from lab/holdout_candidates.json (frozen BEFORE the download, see PROTOCOL.md).
Indicators warm up on the end of 2025 (main data); only trades entered on/after 2026-01-01 count.
Every 2026 result is written to results/holdout/ and reported, not only the best.
"""
import datetime as dt
import glob
import importlib.util
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd

LAB = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, LAB)
import goldlab as gl  # noqa: E402
from goldlab.sim import Costs  # noqa: E402
from prep_data import _drop_flat  # noqa: E402

RAW = os.path.join(LAB, "holdout_raw", "download")
HD = os.path.join(LAB, "data", "holdout")
OUT = os.path.join(LAB, "results", "holdout")
START = pd.Timestamp("2026-01-01", tz="UTC")


def _read(pattern):
    fr = []
    for p in sorted(glob.glob(os.path.join(RAW, pattern))) + sorted(glob.glob(os.path.join(RAW, "patch", pattern))):
        d = pd.read_csv(p)
        d["ts"] = pd.to_datetime(d["timestamp"], unit="ms", utc=True)
        fr.append(d.drop(columns="timestamp").set_index("ts"))
    df = pd.concat(fr).sort_index()
    return df[~df.index.duplicated(keep="first")]


def build(sym):
    b = _read(f"{sym}-m1-bid-*.csv")
    if sym == "xauusd":
        a = _read(f"{sym}-m1-ask-*.csv")
        df = b.add_prefix("b_").join(a.add_prefix("a_"), how="inner")
        df = _drop_flat(df, "b_open", "b_high", "b_low", "b_close")
        df = pd.DataFrame({"bo": df.b_open, "bh": df.b_high, "bl": df.b_low, "bc": df.b_close,
                           "ao": df.a_open, "ah": df.a_high, "al": df.a_low, "ac": df.a_close})
    else:
        from prep_data import SYNTH_SPREAD
        s = SYNTH_SPREAD.get(sym, 0.0)
        b = _drop_flat(b, "open", "high", "low", "close")
        df = pd.DataFrame({"bo": b.open, "bh": b.high, "bl": b.low, "bc": b.close,
                           "ao": b.open + s, "ah": b.high + s, "al": b.low + s, "ac": b.close + s})
    return df.astype("float64")


def short_days(df):
    cnt = pd.Series(1, index=gl.trading_day(df.index)).groupby(level=0).sum()
    return cnt[cnt < 0.5 * cnt.median()].index


def patch(sym, days):
    os.makedirs(os.path.join(RAW, "patch"), exist_ok=True)
    sides = ("bid", "ask") if sym == "xauusd" else ("bid",)
    for d in days:
        a, b = (d - pd.Timedelta(days=1)).strftime("%Y-%m-%d"), (d + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        for side in sides:
            fn = f"{sym}-m1-{side}-{a}-{b}"
            subprocess.run(["npx", "--yes", "dukascopy-node", "-i", sym, "-from", a, "-to", b, "-t", "m1",
                            "-p", side, "-f", "csv", "-r", "3", "-re", "-dir", os.path.join(RAW, "patch"),
                            "-fn", fn], capture_output=True)


def load_strategy(track):
    d = os.path.join(LAB, "tracks", track)
    sys.path.insert(0, d)
    spec = importlib.util.spec_from_file_location(f"strategy_{track}", os.path.join(d, "strategy.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    os.makedirs(HD, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    cands = json.load(open(os.path.join(LAB, "holdout_candidates.json")))
    with open(os.path.join(OUT, "holdout_access.log"), "a") as f:
        f.write(json.dumps({"time": dt.datetime.utcnow().isoformat(timespec="seconds"),
                            "candidates": [c["track"] + "/" + c["name"] for c in cands["candidates"]]}) + "\n")
    frames = {}
    for sym in sorted({c.get("sym", "xauusd") for c in cands["candidates"]}):
        df = build(sym)
        sd = [d for d in short_days(df) if not (d.month == 12 and d.day >= 24) and not (d.month == 1 and d.day <= 2)]
        if sd:
            print(f"{sym}: re-downloading {len(sd)} short days", flush=True)
            patch(sym, sd)
            df = build(sym)
        df.to_parquet(os.path.join(HD, f"{sym}_m1.parquet"))
        hist = gl.load_m1(sym, start="2025-06-01")
        full = pd.concat([hist, df[df.index > hist.index[-1]]])
        frames[sym] = full
        print(f"{sym}: holdout bars {len(df):,} {df.index[0]} -> {df.index[-1]}", flush=True)
    results = {}
    for c in cands["candidates"]:
        sym = c.get("sym", "xauusd")
        m1 = frames[sym]
        mod = load_strategy(c["track"])
        params = mod.FINALISTS[c["name"]]
        orders = mod.make_orders(m1, **params)
        key = f'{c["track"]}/{c["name"]}'
        results[key] = {"status_before_holdout": c.get("status"), "scenarios": {}}
        for sname, cdict in cands["cost_scenarios"].items():
            t = gl.simulate(m1, orders, sym=sym, costs=Costs(**cdict) if cdict else None)
            h = t[t.entry_time >= START]
            rep = gl.report(h) if len(h) else {"n": 0}
            results[key]["scenarios"][sname] = rep
            h.to_csv(os.path.join(OUT, f'trades__{c["track"]}__{c["name"]}__{sname}.csv'))
            print(key, sname, {k: rep.get(k) for k in ("n", "pf", "expectancy_R", "t_stat", "win_rate",
                                                          "long_R", "short_R", "weeks_pos_pct", "max_dd_R")}, flush=True)
        results[key]["holdout_pass_prereg"] = results[key]["scenarios"].get("prereg", {}).get("pf", 0) > 1.0
    json.dump(results, open(os.path.join(OUT, "results.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
