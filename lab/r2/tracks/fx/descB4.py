"""Stage B4 (descriptive, IS 2013-2021, gross mid moves in bp): does a large one-minute us100 move lead the
risk-sensitive pairs (audusd, nzdusd, usdjpy, eurjpy: all 'risk-on = up')?

Event: us100 one-minute mid log return r_t with |r_t| >= k x sigma_t, sigma_t = std of the previous 600 one-minute
returns (causal, shift 1); New York cash hours 09:30-16:00; at most one event per 60 minutes (first one kept).
The event is known at the END of us100 minute t; reference price = pair's mid close of minute t (= entry at the open
of minute t+1, before costs).  Forward signed move sign(r_t) x (pair mid close of minute t+h - reference), h in
{1, 5, 15, 30, 60} minutes; also the same-minute move (not tradable, context).
Cells: 2 thresholds (k = 4, 6) x 4 pairs x 5 horizons = 40 (+8 same-minute context cells).
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

IS_END = pd.Timestamp("2022-01-01", tz="UTC")
H = (1, 5, 15, 30, 60)


def events(k_list=(4, 6)):
    m = C.r2.load("us100", end="2022-01-01")
    mid = ((m.bc + m.ac) / 2)
    C.r2.free()
    m = None
    r = np.log(mid).diff()
    # only consecutive minutes
    cons = mid.index.to_series().diff() == pd.Timedelta(minutes=1)
    r[~cons.to_numpy()] = np.nan
    sig = r.rolling(600, min_periods=400).std().shift(1)
    z = r / sig
    ny = mid.index.tz_convert("America/New_York")
    mod = ny.hour * 60 + ny.minute
    cash = (mod >= 9 * 60 + 30) & (mod < 16 * 60)
    out = {}
    for k in k_list:
        sel = np.flatnonzero(cash & (np.abs(z.to_numpy()) >= k))
        t = mid.index[sel]
        keep, last = [], None
        for j, tt in enumerate(t):
            if last is None or tt - last >= pd.Timedelta(minutes=60):
                keep.append(j)
                last = tt
        sel = sel[keep]
        out[k] = pd.DataFrame({"t": mid.index[sel], "sign": np.sign(r.to_numpy()[sel])})
    return out


def main():
    ev = events()
    rows = []
    for sym in ("audusd", "nzdusd", "usdjpy", "eurjpy"):
        m1 = C.load_is(sym)
        s = ((m1.bc + m1.ac) / 2)
        s = s[s.index < IS_END]
        idx = s.index.values
        v = s.to_numpy()
        for k, e in ev.items():
            tv = e.t.dt.tz_convert("UTC").dt.tz_localize(None).values.astype(idx.dtype)
            i = np.searchsorted(idx, tv)
            okr = (i < len(idx)) & (idx[np.clip(i, 0, len(idx) - 1)] == tv)
            yrs = e.t.dt.year.to_numpy()
            prev = np.clip(i - 1, 0, len(idx) - 1)
            same = np.where(okr & (idx[prev] == tv - np.timedelta64(1, "m")), e.sign * np.log(v[np.clip(i, 0, len(v) - 1)] / v[prev]) * 1e4, np.nan)
            rows.append({"sym": sym, "k": k, "h": 0, **C_stats(same, yrs)})
            for h in H:
                j = np.searchsorted(idx, tv + np.timedelta64(h, "m"))
                okj = okr & (j < len(idx))
                jc = np.clip(j, 0, len(idx) - 1)
                okj &= idx[jc] == tv + np.timedelta64(h, "m")
                x = np.where(okj, e.sign * np.log(v[jc] / v[np.clip(i, 0, len(v) - 1)]) * 1e4, np.nan)
                rows.append({"sym": sym, "k": k, "h": h, **C_stats(x, yrs)})
        print(sym, "done", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(C.OUT, "descB4_us100_spill.csv"), index=False)
    print(df.drop(columns=["by_year_bp"], errors="ignore").to_string())


def C_stats(x, yrs):
    from descB import stats
    return stats(x, yrs)


if __name__ == "__main__":
    main()
