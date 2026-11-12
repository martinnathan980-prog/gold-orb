"""Pre-checks declared by the judge (not trials; no P&L is computed):
 (a) for each pair, the share of the calendar Sundays 2014-01-05 .. 2021-12-26 with an M1 bar starting in
     [20:00, 20:15) NY; below 90 % the pair is dropped before the run;
 (b) frame spread (ask open - bid open, bp of mid) of the first bar in [20:00, 20:15) NY: Sundays against Mon-Thu.
Information only (coverage, no prices of any outcome): the same coverage at 19:00 / 21:00 (neighbours 4 / 5) and the
share of Fridays with a bar in [16:50, 17:05) NY (the F price).

    PYTHONDONTWRITEBYTECODE=1 NUMBA_CACHE_DIR=/tmp/... python3 precheck.py
"""
import gc
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import wkfade as W  # noqa: E402

A, B = pd.Timestamp("2014-01-05"), pd.Timestamp("2021-12-26")


def first_bar(idx, t):
    N = len(idx)
    j = np.searchsorted(idx, t, side="left")
    ok = (j < N) & (idx[np.minimum(j, N - 1)] < t + W.TOL)
    return np.minimum(j, N - 1), ok


def main():
    out = {"window": "calendar Sundays 2014-01-05 .. 2021-12-26 (and the weekdays / Fridays of the same span)",
           "rule": "pair dropped before the run if the Sunday 20:00 NY coverage is below 90 %", "pairs": {}}
    for sym in W.PAIRS:
        m1 = W.load_is(sym)
        idx = W.naive_utc(m1)
        mid_o = (m1["bo"].to_numpy(float) + m1["ao"].to_numpy(float)) / 2
        spr_o = (m1["ao"].to_numpy(float) - m1["bo"].to_numpy(float))
        days = pd.date_range(A, B, freq="D")
        suns = days[days.dayofweek == 6]
        wkd = days[days.dayofweek <= 3]                        # Monday-Thursday
        fris = days[days.dayofweek == 4]
        r = {"sundays": int(len(suns))}
        for hhmm in ("19:00", "20:00", "21:00"):
            _, ok = first_bar(idx, W.wall(suns, 0, hhmm))
            r[f"sunday_{hhmm}_coverage_pct"] = round(float(ok.mean() * 100), 2)
        _, okf = first_bar(idx, W.wall(fris, 0, "16:50"))
        r["friday_1650_coverage_pct"] = round(float(okf.mean() * 100), 2)
        js, oks = first_bar(idx, W.wall(suns, 0, "20:00"))
        jw, okw = first_bar(idx, W.wall(wkd, 0, "20:00"))
        bs = spr_o[js[oks]] / mid_o[js[oks]] * 1e4
        bw = spr_o[jw[okw]] / mid_o[jw[okw]] * 1e4
        q = lambda x: {"median": round(float(np.median(x)), 3), "p25": round(float(np.percentile(x, 25)), 3),
                       "p75": round(float(np.percentile(x, 75)), 3), "p90": round(float(np.percentile(x, 90)), 3),
                       "n": int(len(x))}
        r["spread_bp_sunday_2000"] = q(bs)
        r["spread_bp_mon_thu_2000"] = q(bw)
        r["sunday_over_weekday_median"] = round(float(np.median(bs) / np.median(bw)), 2)
        r["dropped"] = bool(r["sunday_20:00_coverage_pct"] < 90.0)
        out["pairs"][sym] = r
        print(sym, r, flush=True)
        del m1, idx, mid_o, spr_o
        gc.collect()
    out["kept"] = [s for s in W.PAIRS if not out["pairs"][s]["dropped"]]
    out["dropped"] = [s for s in W.PAIRS if out["pairs"][s]["dropped"]]
    W.jdump(out, os.path.join(W.RES, "precheck.json"))
    print("kept", out["kept"], "dropped", out["dropped"])


if __name__ == "__main__":
    main()
