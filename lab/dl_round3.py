"""Round-3 data: M1 bid+ask from Dukascopy, one file per symbol, side and year (research period only,
<= 2025-12-31).  FX pairs with their real spread, then US share CFDs (regular session only; history starts
in early 2017; prices are NOT adjusted for splits).
Usage: python3 lab/dl_round3.py [workers] [fx|stocks|sym1,sym2,...]      (resumable)
Output: lab/data/raw_r3/<sym>-m1-<side>-<year>.csv.gz        (lab/data is git-ignored)"""
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "data", "raw_r3")
FX = ["eurusd", "gbpusd", "usdjpy", "audusd", "usdcad", "usdchf", "nzdusd", "eurjpy"]
# 40 large, heavily traded US shares, list fixed on 2026-11-11 before any test (not chosen on results)
STOCKS = ("aapl msft amzn googl fb nvda tsla nflx amd intc csco orcl crm adbe qcom avgo mu pypl baba "
          "jpm bac c wfc gs v ma jnj pfe mrk unh xom cvx ba cat ge wmt hd dis mcd nke").split()
SYMS = {**{s: 2013 for s in FX}, **{s + "ususd": 2017 for s in STOCKS}}
LAST_YEAR = 2025


def job(sym, year, side):
    name = f"{sym}-m1-{side}-{year}"
    gz = os.path.join(OUT, name + ".csv.gz")
    if os.path.exists(gz):
        return name, "skip"
    cmd = ["npx", "--yes", "dukascopy-node", "-i", sym, "-from", f"{year}-01-01", "-to", f"{year + 1}-01-01",
           "-t", "m1", "-p", side, "-f", "csv", "-v", "true", "-r", "4", "-rp", "2000", "-fr", "-dir", OUT, "-fn", name]
    r = subprocess.run(cmd, capture_output=True, text=True)
    csv = os.path.join(OUT, name + ".csv")
    if r.returncode != 0 or not os.path.exists(csv):
        return name, "FAILED " + (r.stdout[-150:] + r.stderr[-150:]).replace("\n", " ")
    subprocess.run(["gzip", "-6", "-f", csv])
    return name, f"ok {os.path.getsize(gz) // 1024} KB"


def main():
    os.makedirs(OUT, exist_ok=True)
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    what = sys.argv[2] if len(sys.argv) > 2 else "all"
    if what == "fx":
        only = FX
    elif what == "stocks":
        only = [s + "ususd" for s in STOCKS]
    elif what == "all":
        only = list(SYMS)
    else:
        only = what.split(",")
    jobs = [(s, y, side) for s in only for y in range(SYMS.get(s, 2017), LAST_YEAR + 1) for side in ("bid", "ask")]
    with ThreadPoolExecutor(workers) as ex:
        for name, status in ex.map(lambda a: job(*a), jobs):
            print(name, status, flush=True)


if __name__ == "__main__":
    main()
