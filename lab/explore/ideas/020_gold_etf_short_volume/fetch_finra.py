"""Fetch FINRA daily short-sale volume files (GLD and IAU rows only) into ~/explore_data/idea_020/raw_rows.
FNSQ + FNYX for 2012-10-01 .. 2018-07-31, CNMS for 2018-08-01 .. 2021-12-31 (scout/sources.md section 6).
Polite: 2 threads, 0.35 s pause after each request per thread. A connection error is retried once after 15 s; the
run stops after two refusals in a row (429/5xx/connection errors that fail their retry). First pass (stop after any two
refusals) hit two isolated connection resets ~500 files apart, 1,650 files in; the second pass uses this rule.
A 403 means "no file" (holiday). Resumable: one small file per download, 'NOFILE' for a 403."""
import os, sys, time, threading, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
OUT = os.path.expanduser("~/explore_data/idea_020/raw_rows")
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
SYM = ("GLD", "IAU")
refusals = [0]; lock = threading.Lock()

def jobs():
    for d in pd.bdate_range("2012-10-01", "2021-12-31"):
        ds = d.strftime("%Y%m%d"); assert ds <= "20211231"
        facs = ("FNSQ", "FNYX") if ds < "20180801" else ("CNMS",)
        for f in facs:
            yield f, ds

def one(job):
    f, ds = job
    p = os.path.join(OUT, f"{f}_{ds}.txt")
    if os.path.exists(p) or refusals[0] >= 2:
        return
    url = f"https://cdn.finra.org/equity/regsho/daily/{f}shvol{ds}.txt"
    for attempt in (0, 1):
        r = _get(url, p)
        if r != "retry": break
        time.sleep(15)
    if r == "retry":
        with lock: refusals[0] += 1
        print("refusal", url, flush=True)
    elif r == "ok":
        with lock: refusals[0] = 0
    time.sleep(0.35)

def _get(url, p):
    try:
        t = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read().decode("utf-8", "replace")
        lines = t.splitlines()
        keep = [lines[0]] + [l for l in lines[1:] if l.split("|")[1:2] and l.split("|")[1] in SYM]
        open(p + ".tmp", "w").write("\n".join(keep) + "\n"); os.replace(p + ".tmp", p)
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            open(p, "w").write("NOFILE\n"); return "nofile"
        print("error", e.code, url, flush=True); return "retry"
    except Exception as e:
        print("error", repr(e), url, flush=True); return "retry"
    return "ok"

if __name__ == "__main__":
    js = list(jobs())
    print(len(js), "files wanted", flush=True)
    with ThreadPoolExecutor(2) as ex:
        list(ex.map(one, js))
    have = len(os.listdir(OUT))
    print("done; cached", have, "of", len(js), "refusals", refusals[0], flush=True)
