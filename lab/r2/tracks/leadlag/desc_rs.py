"""Descriptive (IS only): relative-strength intraday momentum between us100 / us500 / us30.
At decision time T (New York), rank the three indices by their return since (a) the previous cash close
(15:59 NY bar close) or (b) today's 09:30 open; forward return of each from the open of the T bar... 
(first tradable minute after the T-1 bar closed) to the 15:59 bar close.  Reported: strongest-minus-weakest
forward spread in bp (mid, no cost), t-stat by day, by year; and each leg separately."""
import sys, os
sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/leadlag")
import numpy as np, pandas as pd
import desc
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
t0 = int(pd.Timestamp("2014-01-01", tz="UTC").value // 60_000_000_000)
t1 = int(pd.Timestamp("2022-01-01", tz="UTC").value // 60_000_000_000)
n = t1 - t0
ts = pd.DatetimeIndex((np.arange(n) + t0).astype("int64") * 60_000_000_000, tz="UTC")
ny = ts.tz_convert("America/New_York")
nym = (ny.hour * 60 + ny.minute).to_numpy()
nyd = (ny.year * 10000 + ny.month * 100 + ny.day).to_numpy()
wd = ny.dayofweek.to_numpy()
syms = ["us100", "us500", "us30"]
C = {}; O = {}
for s in syms:
    c, o, sp, has = desc.grid(s, t0, t1, ffill=3)
    C[s] = c; O[s] = o
days = np.unique(nyd[(wd < 5)])
# per day: index of minute m (NY) on the grid
def at(minute):
    m = (nym == minute) & (wd < 5)
    return pd.Series(np.flatnonzero(m), index=nyd[m])
i_close = at(15 * 60 + 59)       # bar 15:59 (closes 16:00)
i_open = at(9 * 60 + 30)
rows = []
for T in (600, 630, 660, 720, 780, 840, 900, 930):
    iT = at(T)                    # entry bar starts at T; decision uses close of bar T-1
    df = pd.DataFrame({"iT": iT, "ic": i_close, "io": i_open}).dropna().astype(int)
    df["prev_ic"] = df["ic"].shift(1)
    df = df.dropna().astype(int)
    for ref in ("prevclose", "open"):
        past = {}; fwd = {}
        for s in syms:
            c = C[s]; o = O[s]
            base = c[df.prev_ic.to_numpy()] if ref == "prevclose" else o[df.io.to_numpy()]
            past[s] = np.log(c[df.iT.to_numpy() - 1] / base) * 1e4
            fwd[s] = np.log(c[df.ic.to_numpy()] / o[df.iT.to_numpy()]) * 1e4
        P = pd.DataFrame(past, index=df.index); F = pd.DataFrame(fwd, index=df.index)
        ok = P.notna().all(axis=1) & F.notna().all(axis=1)
        P, F = P[ok], F[ok]
        hi = P.to_numpy().argmax(axis=1); lo = P.to_numpy().argmin(axis=1)
        Fv = F.to_numpy()
        r_hi = Fv[np.arange(len(Fv)), hi]; r_lo = Fv[np.arange(len(Fv)), lo]
        spread = r_hi - r_lo
        disp = P.max(axis=1) - P.min(axis=1)
        yr = (P.index // 10000)
        by = pd.Series(spread).groupby(yr.to_numpy()).mean().round(2)
        tt = spread.mean() / (spread.std(ddof=1) / np.sqrt(len(spread)))
        # only days with large dispersion (top half / top quartile, rolling median would be needed for a rule; descriptive: IS quantile)
        q50, q75 = np.quantile(disp, [0.5, 0.75])
        m50 = disp.to_numpy() >= q50; m75 = disp.to_numpy() >= q75
        t50 = spread[m50].mean() / (spread[m50].std(ddof=1) / np.sqrt(m50.sum()))
        t75 = spread[m75].mean() / (spread[m75].std(ddof=1) / np.sqrt(m75.sum()))
        rows.append({"T": f"{T//60:02d}:{T%60:02d}", "ref": ref, "days": len(spread), "spread_bp": round(spread.mean(), 2), "t": round(tt, 2),
                     "long_leg": round(r_hi.mean(), 2), "short_leg": round(-r_lo.mean(), 2), "mkt": round(Fv.mean(), 2),
                     "sd": round(spread.std(), 1), "top50%disp": round(spread[m50].mean(), 2), "t50": round(t50, 2),
                     "top25%disp": round(spread[m75].mean(), 2), "t75": round(t75, 2),
                     "by_year": " ".join(f"{a}:{v}" for a, v in by.items())})
r = pd.DataFrame(rows)
r.to_csv("/home/user/gold-orb/lab/results/r2/leadlag/descriptive/relative_strength_us_indices.csv", index=False)
print(r.to_string(index=False))
