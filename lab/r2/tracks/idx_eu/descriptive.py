"""Descriptive statistics behind the idx_eu report -- IN-SAMPLE ONLY (frames are cut at 2022-01-01).

No trading rule is simulated here.  Output: results/r2/idx_eu/descriptive_is.txt
  A. data coverage (Berlin hours with data) and modelled FP spread by hour and year
  B. mean return by 30-minute bucket (drift by time of day)
  C. continuation after a move from the previous cash close, by decision time and size of the move
  D. minute-by-minute trend-signed returns around the 17:30 Xetra close
  E. the same on the RAW Dukascopy bid/ask (is the run-up tradable at real quotes? is it a bar-boundary gap?)
"""
import io
import os
import sys

sys.path.insert(0, "/home/user/gold-orb/lab")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402

OUT = "/home/user/gold-orb/lab/results/r2/idx_eu"
TZ = "Europe/Berlin"
END = "2022-01-01"
buf = io.StringIO()


def P(*a):
    print(*a)
    print(*a, file=buf)


def tstat(x):
    x = pd.Series(x).dropna()
    return float(x.mean() / x.std(ddof=1) * np.sqrt(len(x))) if len(x) > 2 else float("nan")


def grid(frame, cols, times, exact=False, tol=3):
    """DataFrame (index = Berlin weekdays) of frame[col] at the first bar at/after each clock time."""
    iv = frame.index.values
    loc = frame.index[[0, -1]].tz_convert(TZ).tz_localize(None).normalize()
    days = pd.bdate_range(loc[0], loc[1])
    out = {}
    for (h, m) in times:
        t = (days + pd.Timedelta(hours=h, minutes=m)).tz_localize(TZ, ambiguous="NaT", nonexistent="NaT") \
            .tz_convert("UTC").tz_localize(None).values.astype(iv.dtype)
        i = np.searchsorted(iv, t)
        ic = np.clip(i, 0, len(iv) - 1)
        ok = (i < len(iv)) & ((iv[ic] == t) if exact else ((iv[ic] - t) <= np.timedelta64(tol, "m")))
        for c in cols:
            out[(c, f"{h:02d}:{m:02d}")] = np.where(ok, cols[c][ic], np.nan)
    return pd.DataFrame(out, index=days)


def main():
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 80)
    m1 = r2.load("ger40", end=END)
    ber = m1.index.tz_convert(TZ)
    mid_o = ((m1.bo + m1.ao) / 2).to_numpy()
    P("=== A. coverage and modelled spread (FP frame, in-sample) ===")
    P("first/last bar:", m1.index[0], m1.index[-1], "| bars:", len(m1))
    P("bars per Berlin weekday by year:", (pd.Series(1, index=ber.year).groupby(level=0).sum()
                                           / pd.Series(ber.tz_localize(None).normalize()).groupby(ber.year).nunique().to_numpy()).round(0).to_dict())
    sp = ((m1.ac - m1.bc) / ((m1.ac + m1.bc) / 2) * 1e4).to_numpy()
    tab = pd.DataFrame({"bp": sp, "h": ber.hour, "yr": ber.year}).groupby(["yr", "h"]).bp.median().unstack(0).round(2)
    P("median modelled spread in bp of price, by Berlin hour (rows) and year (columns); nominal FP spread = 0.62 bp:")
    P(tab.to_string())

    g = grid(m1, {"p": mid_o}, [(h, m) for h in range(8, 22) for m in range(0, 60, 5)])["p"]
    L = np.log(g)
    L = L[g["17:30"].notna()]
    P("\n=== B. mean return by 30-minute bucket, bp (t) ; first half = before 2018 ===")
    t30 = [c for c in L.columns if c.endswith(":00") or c.endswith(":30")]
    for a, b in zip(t30[:-1], t30[1:]):
        r = (L[b] - L[a]) * 1e4
        P(f"  {a}-{b}: {r.mean():+.2f} ({tstat(r):+.1f})  sd {r.std():.1f} | first half {r[r.index < '2018-01-01'].mean():+.2f}, second {r[r.index >= '2018-01-01'].mean():+.2f}")
    pc = L["17:30"].shift(1)
    gap = (L["09:00"] - pc) * 1e4
    P(f"  overnight (prev 17:30 -> 09:00): {gap.mean():+.2f} bp ({tstat(gap):+.1f}); cash day 09:00->17:30: {((L['17:30'] - L['09:00']) * 1e4).mean():+.2f} bp")

    P("\n=== C. continuation of the move since the previous cash close: mean of sign(x_T) * return(T -> exit), bp (t) [n] ===")
    P("    z = x_T / std of x_T over the previous 20 days")
    for X in ("17:30", "21:55"):
        P(f"  exit {X}:")
        for T in ("09:05", "09:30", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "15:30", "15:45", "16:00", "16:30", "17:00", "17:15", "17:25"):
            x = (L[T] - pc) * 1e4
            z = x / x.rolling(20).std().shift(1)
            y = (L[X] - L[T]) * 1e4
            cells = []
            for lo, hi in ((0, 0.5), (0.5, 1.0), (1.0, 1.5), (1.5, 99)):
                m = (z.abs() >= lo) & (z.abs() < hi) & y.notna()
                s = (np.sign(x) * y)[m]
                cells.append(f"|z| {lo}-{hi}: {s.mean():+5.1f} ({tstat(s):+4.1f}) [{int(m.sum())}]")
            P(f"    T={T}  " + "  ".join(cells))
    P("  same with the 09:00 open as anchor (exit 17:30), |z|>=1.5 only:")
    for T in ("10:00", "12:00", "14:00", "16:00"):
        x = (L[T] - L["09:00"]) * 1e4
        z = x / x.rolling(20).std().shift(1)
        s = (np.sign(x) * (L["17:30"] - L[T]) * 1e4)[z.abs() >= 1.5]
        P(f"    T={T}: {s.mean():+.1f} ({tstat(s):+.1f}) [{len(s.dropna())}]")

    P("\n=== D. trend-signed 1-minute mid returns around the close (sign = move prev close -> 17:00), bp (t) ===")
    mins = [(17, m) for m in range(0, 51)]
    M = grid(m1, {"p": mid_o}, mins, exact=True)["p"]
    LM = np.log(M).reindex(L.index)
    x = (L["17:00"] - pc) * 1e4
    z = x / x.rolling(20).std().shift(1)
    sg = np.sign(x)
    segs = [("17:00", "17:15"), ("17:15", "17:25"), ("17:25", "17:28"), ("17:28", "17:29"), ("17:29", "17:30"), ("17:30", "17:31"),
            ("17:31", "17:35"), ("17:35", "17:36"), ("17:36", "17:45")]
    for nm, mask in (("all days", z.notna()), ("|z|<0.5", z.abs() < 0.5), ("0.5<=|z|<1.5", (z.abs() >= 0.5) & (z.abs() < 1.5)), ("|z|>=1.5", z.abs() >= 1.5)):
        cells = []
        for a, b in segs:
            r = ((LM[b] - LM[a]) * 1e4 * sg)[mask]
            cells.append(f"{a}-{b}: {r.mean():+.2f} ({tstat(r):+.1f})")
        P(f"  {nm:<13s} n={int(mask.sum()):4d}  " + " | ".join(cells))
    r = ((LM["17:30"] - LM["17:25"]) * 1e4 * sg)
    P("  17:25->17:30, all days, by year:", r.groupby(r.index.year).mean().round(2).to_dict())
    r2.free()

    P("\n=== E. RAW Dukascopy bid/ask around the close (in-sample) ===")
    raw = gl.load_m1("ger40", end=END)
    cols = {k: raw[k].to_numpy() for k in ("bo", "ao", "bc", "ac")}
    G = grid(raw, cols, [(17, m) for m in range(24, 34)], exact=True)
    BO, AO, BC, AC = G["bo"], G["ao"], G["bc"], G["ac"]
    MID = (BO + AO) / 2
    MIDC = (BC + AC) / 2
    P("  raw spread in points at the bar open, median:", {c: round(float((AO[c] - BO[c]).median()), 2) for c in ("17:25", "17:29", "17:30", "17:31", "17:32")})
    prev = np.log(MID["17:30"]).ffill().shift(1)
    x = (np.log(MID["17:25"]) - prev) * 1e4
    z = x / x.rolling(20).std().shift(1)
    sg = np.sign(x)
    days = MID.index
    for nm, mask in (("all days", z.notna()), ("|z|>=0.5", z.abs() >= 0.5), ("|z|>=1.5", z.abs() >= 1.5)):
        P(f"  {nm} (n={int(mask.sum())}):")
        for a, b in (("17:25", "17:29"), ("17:25", "17:30"), ("17:25", "17:31")):
            mid = ((np.log(MID[b]) - np.log(MID[a])) * 1e4 * sg)[mask]
            ent = pd.Series(np.where(sg > 0, AO[a], BO[a]), index=days)
            ext = pd.Series(np.where(sg > 0, BO[b], AO[b]), index=days)
            rt = ((np.log(ext) - np.log(ent)) * 1e4 * sg)[mask]
            P(f"    {a}->{b}: mid {mid.mean():+.2f} ({tstat(mid):+.1f}) | round trip at raw quotes (enter on the offer side, exit on the bid side) {rt.mean():+.2f} ({tstat(rt):+.1f})")
    P("  is the move a jump at the bar boundary?  all days, signed bp:")
    for m in ("17:28", "17:29", "17:30"):
        nxt = f"17:{int(m[3:]) + 1:02d}"
        inbar = ((np.log(MIDC[m]) - np.log(MID[m])) * 1e4 * sg)[z.notna()]
        gapb = ((np.log(MID[nxt]) - np.log(MIDC[m])) * 1e4 * sg)[z.notna()]
        P(f"    bar {m}: open->close {inbar.mean():+.2f} ({tstat(inbar):+.1f}) | close -> next open {gapb.mean():+.2f} ({tstat(gapb):+.1f})")
    with open(os.path.join(OUT, "descriptive_is.txt"), "w") as f:
        f.write(buf.getvalue())


if __name__ == "__main__":
    main()
