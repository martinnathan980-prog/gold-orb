"""Find trading days with missing M1 data (failed downloads) and re-download them.

Usage:  python3 lab/patch_holes.py            # writes ../download/patch/*.csv.gz
Then re-run prep_data.py, which merges download/patch/ into the parquet files.
"""
import os
import subprocess
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from goldlab.data import load_m1, trading_day  # noqa: E402

PATCH = os.path.join(ROOT, "..", "download", "patch")
SYMS = {"xauusd": ("bid", "ask"), "eurusd": ("bid",), "gbpusd": ("bid",), "usdjpy": ("bid",),
        "deuidxeur": ("bid",), "lightcmdusd": ("bid",)}


def short_days(sym, frac=0.5):
    m1 = load_m1(sym)
    cnt = pd.Series(1, index=trading_day(m1.index)).groupby(level=0).sum()
    return cnt[cnt < frac * cnt.median()].index


def main():
    os.makedirs(PATCH, exist_ok=True)
    for sym, sides in SYMS.items():
        days = short_days(sym)
        print(f"{sym}: {len(days)} short trading days", flush=True)
        for d in days:
            a = (d - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            b = (d + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            for side in sides:
                name = f"{sym}-m1-{side}-{a}-{b}.csv"
                if os.path.exists(os.path.join(PATCH, name + ".gz")):
                    continue
                cmd = ["npx", "--yes", "dukascopy-node", "-i", sym, "-from", a, "-to", b, "-t", "m1",
                       "-p", side, "-f", "csv", "-r", "3", "-re", "-dir", PATCH, "-fn", name[:-4]]
                r = subprocess.run(cmd, capture_output=True, text=True)
                if r.returncode != 0:
                    print("  failed", name, r.stderr[-200:], flush=True)
                    continue
                subprocess.run(["gzip", "-9", "-f", os.path.join(PATCH, name)])
        print(f"{sym}: done", flush=True)


if __name__ == "__main__":
    main()
