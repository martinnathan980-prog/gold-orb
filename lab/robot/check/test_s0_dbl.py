"""S0: the table-driven clock double (check/dbl/CR_Clock_dbl.mqh) equals zoneinfo on every hour 2012-2035.

    python3 -I lab/robot/check/test_s0_dbl.py

Checks, on the double translated to C++ and compiled with the spec's flags:
  * every hour from 2012-01-01 to 2036-01-01 UTC: UTC -> server, New York and London wall clocks equal zoneinfo; back
    again equal to the hour, except in the repeated hour of a fall-back day where the summer-time instant is returned
    (the rule of pont.server_to_utc); US and UK summer time flags equal zoneinfo's; the server week starts on Monday;
  * every date 2012-2035: ClkNyse equals idxus_lib.us_holidays (full, half, open);
  * AddTradingDays on every 4h UTC boundary of 2013-2021 equals trend/strategy.py add_trading_days (n = 5);
  * BusinessDays on every date 2012-2035, n = 0..5, equals pandas BDay;
  * the typed closure parser (good and bad strings) and a few known closures;
  * the public API (names and signatures) of the double equals src/CR_Clock.mqh's.
Exit 0 when everything holds.
"""
import datetime as dt
import json
import os
import re
import subprocess
import sys
from zoneinfo import ZoneInfo

os.environ.setdefault("NUMBA_CACHE_DIR", "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/numba")
sys.dont_write_bytecode = True
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROBOT = os.path.dirname(HERE)
LAB = os.path.dirname(ROBOT)
sys.path.insert(0, HERE)
sys.path.insert(0, LAB)
sys.path.insert(0, os.path.join(LAB, "r2", "tracks", "idx_us"))
from build import BUILD, build  # noqa: E402

API = ["ClkInit", "ClkUsDst", "ClkUkDst", "ClkServerToUtc", "ClkUtcToServer", "ClkUtcToNy", "ClkNyToUtc", "ClkUtcToLdn",
       "ClkLdnToUtc", "ClkDay", "ClkDow", "ClkMinOfDay", "ClkYear", "ClkServerDay", "ClkServerWeek", "ClkAddTradingDays",
       "ClkBusinessDays", "ClkNyse", "ClkInClosure", "ClkRealExitMinute", "ClkRuleOffset", "ClkStr"]
T0 = int(dt.datetime(2012, 1, 1, tzinfo=dt.timezone.utc).timestamp())
T1 = int(dt.datetime(2036, 1, 1, tzinfo=dt.timezone.utc).timestamp())
MAIN = r'''
#include "mock_replay.h"
#include "ea.cpp"
#include <cstdio>
int main(int argc, char **argv)
  {
   long t0 = atol(argv[2]), t1 = atol(argv[3]);
   FILE *f = fopen(argv[1], "wb");
   for(long u = t0; u < t1; u += 3600)
     {
      long r[10] = {u, ClkUtcToServer(u), ClkUtcToNy(u), ClkUtcToLdn(u), ClkServerToUtc(ClkUtcToServer(u)), ClkNyToUtc(ClkUtcToNy(u)),
                    ClkLdnToUtc(ClkUtcToLdn(u)), (long)ClkUsDst(u), (long)ClkUkDst(u), ClkServerWeek(u)};
      fwrite(r, 8, 10, f);
     }
   fclose(f);
   f = fopen(argv[4], "wb");                               // dates: NYSE kind and BusinessDays(0..5)
   for(long d = t0; d < t1; d += 86400)
     {
      long r[7] = {(long)ClkNyse(d), ClkBusinessDays(d, 0), ClkBusinessDays(d, 1), ClkBusinessDays(d, 2), ClkBusinessDays(d, 3),
                   ClkBusinessDays(d, 4), ClkBusinessDays(d, 5)};
      fwrite(r, 8, 7, f);
     }
   fclose(f);
   f = fopen(argv[5], "rb");                               // AddTradingDays(t, 5) on given instants
   FILE *g = fopen(argv[6], "wb");
   long t;
   while(fread(&t, 8, 1, f) == 1) { long x = ClkAddTradingDays(t, 5); fwrite(&x, 8, 1, g); }
   fclose(f);
   fclose(g);
   string err;
   const char *good[] = {"", "NYSE 2026.01.09", "HALF 2026.12.24; NYSE 2026.01.09", "XAU 2026.12.24 13:45-2026.12.26 18:00",
                         "CRY 2026.12.31 16:55-2027.01.02 17:00;IDX 2026.07.03 13:15-2026.07.05 18:00"};
   const char *bad[] = {"NYSE 2026-01-09", "XAU 2026.12.24 13:45", "FOO 2026.12.24", "XAU 2026.12.26 18:00-2026.12.24 13:45",
                        "HALF 2026.02.30", "NYSE 2026.13.01"};
   int ok_good = 0, ok_bad = 0;
   for(const char *s : good) ok_good += ClkInit(s, err) ? 1 : 0;
   for(const char *s : bad) ok_bad += ClkInit(s, err) ? 0 : 1;
   ClkInit("NYSE 2030.06.03;XAU 2030.06.05 09:00-2030.06.05 11:00", err);
   datetime c0 = 0, c1 = 0;
   // 2030-06-03 (a Monday) is a typed NYSE closure; 2030-06-05 10:00 NY (14:00 UTC) inside the typed gold window 09:00-11:00 NY
   int typed_nyse = ClkNyse(1906675200) == CR_NYSE_FULL;
   int typed_win = ClkInClosure(CR_FAM_XAU, 1906898400, c0, c1) && c0 == 1906894800 && c1 == 1906902000;
   ClkInit("", err);
   // gold weekend: Saturday 2021-01-09 12:00 UTC -> [Friday 2021-01-08 22:00 UTC, Sunday 2021-01-10 23:00 UTC)
   int wk = ClkInClosure(CR_FAM_XAU, 1610193600, c0, c1) && c0 == 1610143200 && c1 == 1610319600;
   // Good Friday 2021-04-02: gold closed from Thursday 17:00 NY (21:00 UTC) to Sunday 18:00 NY (22:00 UTC)
   int gf = ClkInClosure(CR_FAM_XAU, 1617364800, c0, c1) && c0 == 1617310800 && c1 == 1617573600;
   // crypto: Friday 2021-01-08 16:55 NY (21:55 UTC) to Sunday 17:00 NY (22:00 UTC)
   int cry = ClkInClosure(CR_FAM_CRY, 1610150400, c0, c1) && c0 == 1610142900 && c1 == 1610316000;
   int open_ = !ClkInClosure(CR_FAM_XAU, 1610370000, c0, c1);      // Monday 2021-01-11 13:00 UTC: open
   printf("{\"good\": %d, \"bad\": %d, \"typed_nyse\": %d, \"typed_window\": %d, \"gold_weekend\": %d, \"good_friday\": %d, \"crypto_weekend\": %d, \"open\": %d}\n",
          ok_good, ok_bad, typed_nyse, typed_win, wk, gf, cry, open_);
   return 0;
  }
'''


def naive_secs(x):
    return int(x.replace(tzinfo=dt.timezone.utc).timestamp())


def api_of(path):
    text = open(path).read()
    out = {}
    for m in re.finditer(r"^(datetime|bool|int|long|string|double|void)\s+(Clk\w+)\s*\(([^)]*)\)", text, re.M):
        out[m.group(2)] = re.sub(r"\s+", " ", f"{m.group(1)} {m.group(2)}({m.group(3)})").strip()
    return out


def main():
    res = {}
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "gen_dbl.py")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    dbl = os.path.join(HERE, "dbl", "CR_Clock_dbl.mqh")
    a_src, a_dbl = api_of(os.path.join(ROBOT, "src", "CR_Clock.mqh")), api_of(dbl)
    api_diff = [n for n in API if a_src.get(n) != a_dbl.get(n)]
    res["api_equal"] = not api_diff
    res["api_differences"] = [(a_src.get(n), a_dbl.get(n)) for n in api_diff]
    work = os.path.join(BUILD, "test_s0_dbl")
    os.makedirs(work, exist_ok=True)
    mainp = os.path.join(BUILD, "test_s0_dbl_main.cpp")
    with open(mainp, "w") as f:
        f.write(MAIN)
    exe, warn = build(dbl, name="test_s0_dbl", main=mainp)
    res["warnings"] = len(warn)
    # inputs: 4h UTC boundaries of 2013-2021
    q = np.arange(int(pd.Timestamp("2013-01-01", tz="UTC").timestamp()), int(pd.Timestamp("2022-01-01", tz="UTC").timestamp()), 4 * 3600,
                  dtype=np.int64)
    pin, pout = os.path.join(work, "atd_in.bin"), os.path.join(work, "atd_out.bin")
    q.tofile(pin)
    ph, pd_ = os.path.join(work, "hours.bin"), os.path.join(work, "days.bin")
    out = subprocess.run([exe, ph, str(T0), str(T1), pd_, pin, pout], capture_output=True, text=True, check=True).stdout
    res["parser_and_closures"] = json.loads(out.strip().splitlines()[-1])
    H = np.fromfile(ph, np.int64).reshape(-1, 10)
    ny, ldn = ZoneInfo("America/New_York"), ZoneInfo("Europe/London")
    bad = {k: 0 for k in ("server", "ny", "london", "server_back", "ny_back", "london_back", "us_dst", "uk_dst", "week")}
    first = {}
    for row in H:
        u = int(row[0])
        t = dt.datetime.fromtimestamp(u, dt.timezone.utc)
        tn, tl = t.astimezone(ny), t.astimezone(ldn)
        wn, wl = naive_secs(tn.replace(tzinfo=None)), naive_secs(tl.replace(tzinfo=None))
        srv = wn + 7 * 3600
        rep_ny = tn.fold == 1 or (tn.replace(fold=1).utcoffset() != tn.replace(fold=0).utcoffset() and tn.dst() == dt.timedelta(0))
        rep_l = tl.replace(fold=1).utcoffset() != tl.replace(fold=0).utcoffset() and tl.dst() == dt.timedelta(0)
        exp = {"server": srv, "ny": wn, "london": wl, "server_back": u - 3600 if rep_ny else u, "ny_back": u - 3600 if rep_ny else u,
               "london_back": u - 3600 if rep_l else u, "us_dst": int(tn.dst() != dt.timedelta(0)),
               "uk_dst": int(tl.dst() != dt.timedelta(0)),
               "week": srv - srv % 86400 - ((dt.datetime.fromtimestamp(srv, dt.timezone.utc).weekday()) * 86400)}
        got = dict(zip(bad, [int(x) for x in row[1:]]))
        for k in bad:
            if got[k] != exp[k]:
                bad[k] += 1
                first.setdefault(k, (u, got[k], exp[k]))
    res["hours"] = int(len(H))
    res["hour_mismatches"] = bad
    res["first_mismatch"] = first
    import idxus_lib as cm
    D = np.fromfile(pd_, np.int64).reshape(-1, 7)
    nyse_bad, bday_bad = 0, 0
    cal = {}
    for k, row in enumerate(D):
        day = dt.date(2012, 1, 1) + dt.timedelta(days=k)
        if day.year not in cal:
            cal[day.year] = cm.us_holidays(day.year)
        full, half = cal[day.year]
        want = 1 if day in full else (2 if day in half else 0)
        nyse_bad += int(row[0]) != want
        ts = pd.Timestamp(day)
        for n in range(6):
            bday_bad += int(row[1 + n]) != naive_secs((ts + pd.offsets.BDay(n)).to_pydatetime())
    res["dates"] = int(len(D))
    res["nyse_mismatches"] = nyse_bad
    res["bday_mismatches"] = bday_bad
    from tracks.trend import strategy as trend  # noqa: E402  (lab/tracks/trend/strategy.py)
    want = trend.add_trading_days(pd.DatetimeIndex(pd.to_datetime(q, unit="s", utc=True)), 5)
    got = np.fromfile(pout, np.int64)
    wv = want.asi8 // 10 ** 9 if want.asi8.dtype == np.int64 else want.astype("int64") // 10 ** 9
    w_ok = ~pd.isna(want)
    res["add_trading_days_checked"] = int(w_ok.sum())
    res["add_trading_days_mismatches"] = int((got[w_ok] != np.asarray(want[w_ok].as_unit("s").asi8)).sum())
    p = res["parser_and_closures"]
    res["pass"] = (res["api_equal"] and res["warnings"] == 0 and all(v == 0 for v in bad.values()) and nyse_bad == 0 and bday_bad == 0
                   and res["add_trading_days_mismatches"] == 0 and p["good"] == 5 and p["bad"] == 6
                   and all(p[k] == 1 for k in ("typed_nyse", "typed_window", "gold_weekend", "good_friday", "crypto_weekend", "open")))
    print(json.dumps(res, indent=1, default=str))
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
