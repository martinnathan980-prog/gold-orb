"""Daily GLD+IAU off-exchange short-volume share from the cached FINRA rows (fetch_finra.py). No price is read here.
Returns a frame indexed by observation date (naive) with short, total, share, n_files; dates <= 2021-12-31 only."""
import os, glob
import pandas as pd
RAW = os.path.expanduser("~/explore_data/idea_020/raw_rows")

def daily_share():
    rows, nofile = [], []
    for p in sorted(glob.glob(os.path.join(RAW, "*_*.txt"))):
        fac, ds = os.path.basename(p)[:-4].split("_")
        if ds > "20211231":
            continue
        lines = open(p).read().splitlines()
        if lines and lines[0] == "NOFILE":
            nofile.append((fac, ds)); continue
        hdr = lines[0].split("|")
        iS, iT, iY = hdr.index("ShortVolume"), hdr.index("TotalVolume"), hdr.index("Symbol")
        for l in lines[1:]:
            f = l.split("|")
            if len(f) == len(hdr) and f[iY] in ("GLD", "IAU"):
                rows.append((ds, fac, f[iY], float(f[iS]), float(f[iT])))
    d = pd.DataFrame(rows, columns=["date", "fac", "sym", "short", "total"])
    nf = pd.DataFrame(nofile, columns=["fac", "date"])
    # a day counts only if every facility file of that day exists (FNSQ and FNYX before 2018-08-01, CNMS after)
    need = lambda ds: 2 if ds < "20180801" else 1
    g = d.groupby("date").agg(short=("short", "sum"), total=("total", "sum"), n_files=("fac", "nunique"))
    g = g[[n == need(ds) for ds, n in zip(g.index, g.n_files)]]
    g = g[g.total > 0]
    g["share"] = g.short / g.total
    g.index = pd.to_datetime(g.index, format="%Y%m%d")
    g.attrs["nofile"] = nf
    return g[g.index <= "2021-12-31"]

def zscore(share, window):
    """z of day D over the `window` observations ending at D inclusive (all known at D's file time); NaN before."""
    m = share.rolling(window, min_periods=window).mean()
    s = share.rolling(window, min_periods=window).std(ddof=1)
    return (share - m) / s
