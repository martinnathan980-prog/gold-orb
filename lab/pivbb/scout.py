"""First pass on the pivot + Bollinger events (in-sample only: touches before 2022).
Every table compares the real levels with the placebo levels (mean and spread over the placebo seeds)."""
import os
import sys

import numpy as np
import pandas as pd

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(LAB, "results", "pivbb")
ev = pd.read_parquet(os.path.join(OUT, "events.parquet"))
ev = ev[ev.t < "2022-01-01"]
real, plc = ev[ev.seed < 0], ev[ev.seed >= 0]
days = real.day.nunique()
print(f"in-sample: {days} trading days | real touches {len(real)} ({len(real) / days:.1f} a day) | placebo {len(plc) / plc.seed.nunique():.0f} per seed")


def versus(mask_fn, col="y25", label=""):
    """Bounce rate (bounce / (bounce + break)) on real levels vs placebo seeds."""
    r = real[mask_fn(real)]
    r = r[r[col].isin([0, 1])]
    ps = []
    for _, p in plc[mask_fn(plc)].groupby("seed"):
        p = p[p[col].isin([0, 1])]
        if len(p):
            ps.append(p[col].mean())
    ps = np.array(ps)
    z = (r[col].mean() - ps.mean()) / ps.std(ddof=1) if len(ps) > 1 and ps.std(ddof=1) > 0 else np.nan
    return {"what": label, "n": len(r), "real": round(r[col].mean(), 3), "placebo": round(ps.mean(), 3),
            "placebo_sd": round(ps.std(ddof=1), 3), "z": round(z, 1)}


# A. does price go to the pivots more than to random lines?
print("\nA. share of days on which the level is touched at least once")
rows = []
for lv in ["D_P", "D_R1", "D_S1", "D_R2", "D_S2", "D_R3", "D_S3", "W_P", "W_R1", "W_S1", "M_P", "PDH", "PDL"]:
    r = real[real.level == lv].day.nunique() / days
    p = plc[plc.level == lv].groupby("seed").day.nunique() / days
    rows.append({"level": lv, "real": round(r, 3), "placebo": round(p.mean(), 3), "placebo_sd": round(p.std(), 3), "z": round((r - p.mean()) / p.std(), 1)})
print(pd.DataFrame(rows).to_string(index=False))

# B. at the touch: bounce or break? (0.25 daily ATR each way, until the end of the trading day)
print("\nB. bounce rate at the touch, by level (barrier 0.25 dATR)")
rows = [versus(lambda d: d.level.notna(), label="all levels")]
for fam in ["D", "W", "M", "PD"]:
    rows.append(versus(lambda d, f=fam: d.fam == f, label=f"family {fam}"))
for lv in ["D_P", "D_R1", "D_S1", "D_R2", "D_S2", "D_R3", "D_S3"]:
    rows.append(versus(lambda d, l=lv: d.level == l, label=lv))
rows.append(versus(lambda d: d.nth_level == 0, label="first touch of the level today"))
rows.append(versus(lambda d: d.nth_level >= 1, label="later touches"))
for col in ("y15", "y50"):
    rows.append(versus(lambda d: d.level.notna(), col=col, label=f"all levels, barrier {col[1:]}% dATR"))
print(pd.DataFrame(rows).to_string(index=False))

# C. Bollinger state at the touch
print("\nC. bounce rate by Bollinger state (daily pivots only, barrier 0.25 dATR)")
D = lambda d: d.fam == "D"
rows = []
for lo, hi in [(-9, 0), (0, 0.5), (0.5, 1.0), (1.0, 1.5), (1.5, 9)]:
    rows.append(versus(lambda d, a=lo, b=hi: D(d) & (d.stretch15 >= a) & (d.stretch15 < b), label=f"level at {lo}..{hi} bands from the 15-min average"))
for lo, hi in [(0, 0.6), (0.6, 1.0), (1.0, 1.6), (1.6, 99)]:
    rows.append(versus(lambda d, a=lo, b=hi: D(d) & (d["squeeze"] >= a) & (d["squeeze"] < b), label=f"band width {lo}..{hi} x its usual width"))
for w in [(0, 0), (1, 2), (3, 8)]:
    rows.append(versus(lambda d, a=w[0], b=w[1]: D(d) & (d.walk >= a) & (d.walk <= b), label=f"{w[0]}-{w[1]} of the last 8 closes outside the band"))
for lo, hi in [(0, 30), (30, 50), (50, 70), (70, 101)]:
    rows.append(versus(lambda d, a=lo, b=hi: D(d) & (d.rsi >= a) & (d.rsi < b), label=f"RSI {lo}-{hi} (in the direction of arrival)"))
rows.append(versus(lambda d: D(d) & (d.stretch15 >= 1.0) & (d.rsi >= 70), label="beyond the band AND RSI >= 70 (the classic fade)"))
rows.append(versus(lambda d: D(d) & (d.stretch15 >= 1.0) & (d["squeeze"] >= 1.6), label="beyond the band AND band expanding"))
rows.append(versus(lambda d: D(d) & (d.stretch15 < 0.5) & (d["squeeze"] < 0.6), label="inside the band AND squeeze"))
for lo, hi in [(18, 24), (0, 3), (3, 8), (8, 12), (12, 17)]:
    rows.append(versus(lambda d, a=lo, b=hi: D(d) & (d.ny_hour >= a) & (d.ny_hour < b), label=f"New York hour {lo}-{hi}"))
print(pd.DataFrame(rows).to_string(index=False))

# D. run to the next pivot
print("\nD. after touching a daily pivot: reach the NEXT pivot before the PREVIOUS one? (rate minus the driftless odds)")
def race(d):
    d = d[(d.fam == "D") & d.race.isin([0, 1])]
    return (d.race - d.race_odds).mean(), len(d)
rows = []
for lab, f in [("all touches", lambda d: d.level.notna()), ("beyond the band", lambda d: d.stretch15 >= 1.0),
               ("band expanding (>1.6x)", lambda d: d["squeeze"] >= 1.6), ("3+ closes outside the band", lambda d: d.walk >= 3),
               ("strong momentum (mom16 >= 6 ATR)", lambda d: d.mom16 >= 6), ("squeeze (<0.6x)", lambda d: d["squeeze"] < 0.6)]:
    r, n = race(real[f(real)])
    ps = np.array([race(p[f(p)])[0] for _, p in plc.groupby("seed")])
    rows.append({"what": lab, "n": n, "real_excess": round(r, 3), "placebo_excess": round(ps.mean(), 3), "placebo_sd": round(ps.std(ddof=1), 3),
                 "z": round((r - ps.mean()) / ps.std(ddof=1), 1)})
print(pd.DataFrame(rows).to_string(index=False))
