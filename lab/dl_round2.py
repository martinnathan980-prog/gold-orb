"""Round-2 data: M1 bid+ask from Dukascopy for the new markets, one file per year, research
period only (<= 2025-12-31; the 2026 holdout is downloaded later, once, by the lead).
Usage: python3 lab/dl_round2.py            (resumable: existing .csv.gz files are skipped)
Output: lab/data/raw_r2/<sym>-m1-<side>-<year>.csv.gz   (lab/data is git-ignored)"""
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "data", "raw_r2")
SYMS = {"usatechidxusd": 2013, "usa500idxusd": 2013, "usa30idxusd": 2013, "xagusd": 2013,
        "btcusd": 2017, "ethusd": 2018, "deuidxeur": 2013}
LAST_YEAR = 2025


def job(sym, year, side):
    name = f"{sym}-m1-{side}-{year}"
    gz = os.path.join(OUT, name + ".csv.gz")
    if os.path.exists(gz):
        return name, "skip"
    cmd = ["npx", "--yes", "dukascopy-node", "-i", sym, "-from", f"{year}-01-01", "-to", f"{year + 1}-01-01",
           "-t", "m1", "-p", side, "-f", "csv", "-r", "4", "-rp", "2000", "-fr", "-dir", OUT, "-fn", name]
    r = subprocess.run(cmd, capture_output=True, text=True)
    csv = os.path.join(OUT, name + ".csv")
    if r.returncode != 0 or not os.path.exists(csv):
        return name, "FAILED " + (r.stdout[-150:] + r.stderr[-150:]).replace("\n", " ")
    subprocess.run(["gzip", "-6", "-f", csv])
    return name, f"ok {os.path.getsize(gz) // 1024} KB"


def main():
    os.makedirs(OUT, exist_ok=True)
    only = sys.argv[2].split(",") if len(sys.argv) > 2 else list(SYMS)
    jobs = [(s, y, side) for s, y0 in SYMS.items() if s in only for y in range(y0, LAST_YEAR + 1) for side in ("bid", "ask")]
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    with ThreadPoolExecutor(workers) as ex:
        for name, status in ex.map(lambda a: job(*a), jobs):
            print(name, status, flush=True)


if __name__ == "__main__":
    main()
