"""Round-6 data: M1 bid+ask from Dukascopy for FX crosses, one file per symbol, side and year.
In-sample years only (2013-2021): the 2022-2025 files are fetched later, and only if a declared single look
needs them. The list was fixed on 2026-11-14 before any test of round 6 (the night-scalper crosses named by
public MQL5 sellers and signals, a superset; the declaration in PROTOCOL_V3 Addendum L picks the basket).
Usage: python3 lab/dl_round6.py [workers] [sym1,sym2,...]      (resumable)
Output: lab/data/raw_r6/<sym>-m1-<side>-<year>.csv.gz        (lab/data is git-ignored)"""
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "data", "raw_r6")
CROSSES = ["eurcad", "gbpcad", "euraud", "audcad", "eurgbp", "eurchf", "gbpchf", "audnzd", "nzdcad", "cadchf",
           "gbpaud", "eurnzd"]
FIRST_YEAR, LAST_YEAR = 2013, 2021


def job(sym, year, side):
    name = f"{sym}-m1-{side}-{year}"
    gz = os.path.join(OUT, name + ".csv.gz")
    if os.path.exists(gz):
        return name, "skip"
    cmd = ["npx", "--yes", "dukascopy-node", "-i", sym, "-from", f"{year}-01-01", "-to", f"{year + 1}-01-01",
           "-t", "m1", "-p", side, "-f", "csv", "-v", "true", "-r", "6", "-rp", "3000", "-fr", "-dir", OUT, "-fn", name]
    r = subprocess.run(cmd, capture_output=True, text=True)
    csv = os.path.join(OUT, name + ".csv")
    if r.returncode != 0 or not os.path.exists(csv):
        return name, "FAILED " + (r.stdout[-150:] + r.stderr[-150:]).replace("\n", " ")
    subprocess.run(["gzip", "-6", "-f", csv])
    return name, f"ok {os.path.getsize(gz) // 1024} KB"


def main():
    os.makedirs(OUT, exist_ok=True)
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    only = sys.argv[2].split(",") if len(sys.argv) > 2 else CROSSES
    jobs = [(s, y, side) for s in only for y in range(FIRST_YEAR, LAST_YEAR + 1) for side in ("bid", "ask")]
    with ThreadPoolExecutor(workers) as ex:
        for name, status in ex.map(lambda a: job(*a), jobs):
            print(name, status, flush=True)


if __name__ == "__main__":
    main()
