"""Re-download the trading days of round-2 markets that look incomplete (failed day files).
Usage: python3 lab/patch_r2.py alias [alias ...]   then re-run prep_round2.py for those aliases.
Indices before 2014 are skipped (Dukascopy only quoted limited hours then)."""
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from goldlab.data import DATA, trading_day  # noqa: E402
from prep_round2 import ALIAS, CRYPTO  # noqa: E402

PATCH = os.path.join(DATA, "raw_r2", "patch")


def short_days(alias):
    m1 = pd.read_parquet(os.path.join(DATA, f"{alias}_m1.parquet"), columns=["bc"])
    key = m1.index.tz_convert("UTC").normalize().tz_localize(None) if alias in CRYPTO else trading_day(m1.index)
    cnt = pd.Series(1, index=key).groupby(level=0).sum()
    full = pd.date_range(cnt.index.min(), cnt.index.max(), freq="D" if alias in CRYPTO else "B")
    cnt = cnt.reindex(full, fill_value=0)
    days = cnt[cnt < 0.5 * cnt[cnt > 0].median()].index
    if alias not in CRYPTO:
        days = [d for d in days if d.year >= 2014 and not ((d.month == 12 and d.day >= 24) or (d.month == 1 and d.day <= 2))]
    return list(days)


def fetch(args):
    sym, side, d = args
    a, b = (d - pd.Timedelta(days=1)).strftime("%Y-%m-%d"), (d + pd.Timedelta(days=2)).strftime("%Y-%m-%d")
    name = f"{sym}-m1-{side}-{a}-{b}"
    gz = os.path.join(PATCH, name + ".csv.gz")
    if os.path.exists(gz):
        return "skip"
    r = subprocess.run(["npx", "--yes", "dukascopy-node", "-i", sym, "-from", a, "-to", b, "-t", "m1", "-p", side,
                        "-f", "csv", "-r", "4", "-rp", "1500", "-re", "-fr", "-dir", PATCH, "-fn", name],
                       capture_output=True, text=True)
    csv = os.path.join(PATCH, name + ".csv")
    if r.returncode != 0 or not os.path.exists(csv):
        return "fail"
    subprocess.run(["gzip", "-6", "-f", csv])
    return "ok"


if __name__ == "__main__":
    os.makedirs(PATCH, exist_ok=True)
    for alias in sys.argv[1:]:
        days = short_days(alias)
        jobs = [(ALIAS[alias], side, d) for d in days for side in ("bid", "ask")]
        with ThreadPoolExecutor(6) as ex:
            res = list(ex.map(fetch, jobs))
        print(f"{alias}: {len(days)} days re-downloaded -> ok {res.count('ok')}, skip {res.count('skip')}, fail {res.count('fail')}", flush=True)
