"""REPRODUCTION CHECK (declared in the test plan, not a trial): the two-leg code (common.sim_pairs) with h = 1, stops
off, no costs and desc_rs.py's own sample and whole-sample dispersion quantiles must reproduce the 10:00 'open' row of
results/r2/leadlag/descriptive/relative_strength_us_indices.csv: +2.69 bp on all days, +8.06 bp on the top quartile.

desc_rs.py conventions mirrored (declared.json R20): weekdays 2014-01-01 .. 2021-12-31 (New York dates); the close of
a bar forward-filled up to 3 minutes; the 09:30 and 10:00 opens must exist; ranking on ln(close 09:59 / open 09:30);
forward = mid open of the 10:00 bar -> mid close of the 15:59 bar; spread = strongest - weakest (h = 1)."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

TARGET = {"days": 1982, "spread_bp": 2.69, "t": 2.92, "long_leg": 3.12, "short_leg": -0.43, "top50%disp": 4.71,
          "t50": 3.03, "top25%disp": 8.06, "t75": 3.19,
          "by_year": {2014: 2.4, 2015: -1.94, 2016: 3.68, 2017: 3.62, 2018: 4.74, 2019: 2.22, 2020: 1.34, 2021: 5.37}}


def tstat(v):
    return float(v.mean() / (v.std(ddof=1) / np.sqrt(len(v))))


def main():
    fr = C.load_frames()
    days = pd.bdate_range("2014-01-01", "2021-12-31")
    G = C.build_grid(fr, days)
    P = C.prepare(G, ffill_limit=3)
    e, x = 30, 389                                           # 10:00 bar (entry open), 15:59 bar (exit at its close)
    r = np.log(P["mc_ff"][:, :, e - 1] / P["mo"][:, :, 0]).T * 1e4
    ok = np.isfinite(r).all(axis=1) & np.isfinite(P["mo"][:, :, e]).all(axis=0) & np.isfinite(P["mc_ff"][:, :, x]).all(axis=0)
    d = np.flatnonzero(ok)
    rr = r[d]
    S, W = rr.argmax(axis=1), rr.argmin(axis=1)
    res = C.sim_pairs(P, d, S, W, np.ones(len(d)), np.ones(len(d)), e, x, k=np.inf, mode="mid", exit_close=True)
    spread = res["net"] * 1e4
    legS = np.log(P["mc_ff"][S, d, x] / P["mo"][S, d, e]) * 1e4
    legW = np.log(P["mc_ff"][W, d, x] / P["mo"][W, d, e]) * 1e4
    disp = rr.max(axis=1) - rr.min(axis=1)
    q50, q75 = np.quantile(disp, [0.5, 0.75])
    m50, m75 = disp >= q50, disp >= q75
    yr = days[d].year.to_numpy()
    got = {"days": int(len(d)), "spread_bp": round(float(spread.mean()), 2), "t": round(tstat(spread), 2),
           "long_leg": round(float(legS.mean()), 2), "short_leg": round(float(-legW.mean()), 2),
           "top50%disp": round(float(spread[m50].mean()), 2), "t50": round(tstat(spread[m50]), 2),
           "top25%disp": round(float(spread[m75].mean()), 2), "t75": round(tstat(spread[m75]), 2),
           "by_year": {int(y): round(float(spread[yr == y].mean()), 2) for y in np.unique(yr)}}
    diffs = {}
    for k, v in TARGET.items():
        if k == "by_year":
            diffs[k] = {y: round(got[k].get(y, np.nan) - v[y], 2) for y in v}
        else:
            diffs[k] = round(got[k] - v, 2)
    exact = all(abs(v) < 0.006 for k, v in diffs.items() if k != "by_year") and \
        all(abs(v) < 0.006 for v in diffs["by_year"].values())
    out = {"what": "reproduction check of desc_rs.py 10:00 'open' row (not a trial)", "target_csv_row": TARGET,
           "reproduced": got, "difference": diffs, "exact_to_2_decimals": bool(exact),
           "pass": bool(abs(diffs["spread_bp"]) <= 0.01 and abs(diffs["top25%disp"]) <= 0.01),
           "dispersion_cut_bp": {"q50": round(float(q50), 2), "q75": round(float(q75), 2)}}
    C.jdump(out, os.path.join(C.OUT, "repro.json"))
    print(out)


if __name__ == "__main__":
    main()
