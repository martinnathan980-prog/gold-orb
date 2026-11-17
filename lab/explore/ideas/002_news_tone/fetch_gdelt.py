"""Fetch GDELT 1.0 daily event files (https://data.gdeltproject.org/events/YYYYMMDD.export.CSV.zip), 2013-04-01..2021-12-31
(in-sample only; never later), stream each zip and keep only a daily aggregate in ~/explore_data/gdelt/<date>.json.
Columns (0-based, 58-col format): 28 EventRootCode, 31 NumMentions, 34 AvgTone. The file of day D holds the events
ADDED on D (published about 06:00 UTC on D+1)."""
import io, json, os, sys, time, zipfile, csv, urllib.request, datetime as dt
from concurrent.futures import ProcessPoolExecutor as ThreadPoolExecutor
OUT = os.path.expanduser("~/explore_data/gdelt")
END = dt.date(2021, 12, 31)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
csv.field_size_limit(10**8)

def one(d):
    f = os.path.join(OUT, d.strftime("%Y%m%d") + ".json")
    if os.path.exists(f) or d > END:
        return
    url = f"https://data.gdeltproject.org/events/{d:%Y%m%d}.export.CSV.zip"
    for k in range(6):
        try:
            raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120).read()
            break
        except Exception as e:
            if "404" in str(e):
                json.dump({"missing": True}, open(f, "w")); return
            time.sleep(3 * (k + 1))
    else:
        print("FAIL", d, flush=True); return
    z = zipfile.ZipFile(io.BytesIO(raw))
    n = m = 0; st = stm = 0.0; conf = 0; confm = 0
    with z.open(z.namelist()[0]) as fh:
        for row in csv.reader(io.TextIOWrapper(fh, "utf-8", errors="replace"), delimiter="\t"):
            if len(row) < 35:
                continue
            try:
                mm = int(row[31]); t = float(row[34])
            except ValueError:
                continue
            n += 1; m += mm; st += t; stm += t * mm
            if row[28] in ("18", "19", "20"):
                conf += 1; confm += mm
    json.dump({"n": n, "mentions": m, "tone_sum": st, "tone_msum": stm, "conf_n": conf, "conf_m": confm}, open(f + ".tmp", "w"))
    os.replace(f + ".tmp", f)

if __name__ == "__main__":
    days = [dt.date(2013, 4, 1) + dt.timedelta(i) for i in range((END - dt.date(2013, 4, 1)).days + 1)]
    with ThreadPoolExecutor(8) as ex:
        for i, _ in enumerate(ex.map(one, days, chunksize=4)):
            if i % 200 == 0:
                print(i, flush=True)
    print("DONE", flush=True)
