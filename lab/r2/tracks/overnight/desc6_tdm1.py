"""Descriptive 6 (IS only): first trading day of the month -- close->close split into the night and the cash session.
Usage: python3 desc6_tdm1.py     (needs the grids written by desc1_idx_grid.py)
"""
import numpy as np
import pandas as pd

from desc import RES, fmt, load_grid, summ

out, n = [], 0
for sym in ["us500", "us100", "ger40"]:
    P = load_grid(sym)
    us = sym != "ger40"
    cl, op = ("16:00", "09:30") if us else ("17:30", "09:00")
    pc = "p" + cl
    yrs = P.index.year.to_numpy()
    bp = lambda a, b: ((P[b] / P[a] - 1) * 1e4).to_numpy()
    idx = P.index
    ym = idx.year * 12 + idx.month
    pos = np.arange(len(idx))
    first_pos = pd.Series(pos, index=idx).groupby(ym).transform("min").to_numpy()
    tdm = pos - first_pos + 1
    f1 = (tdm == 1) & (idx.day <= 4)          # a real first session (within the first 4 calendar days)
    out.append(f"===== {sym}: first trading day of the month (TDM+1), IS, mid, bp; months={f1.sum()}")
    for a, b, lab in [(pc, cl, "close->close"), (pc, op, "night (prev close->open)"), (op, cl, "cash session"),
                      (op, "12:00", "open->12:00"), ("12:00", cl, "12:00->close")]:
        r = bp(a, b)
        out.append(fmt(summ(r[f1], yrs[f1], f"TDM+1 {lab}"))); n += 1
    r = bp(pc, cl)
    out.append(fmt(summ(r[~f1], yrs[~f1], "all other days close->close"), by_year=False))
    r = bp(op, cl)
    out.append(fmt(summ(r[~f1], yrs[~f1], "all other days cash session"), by_year=False))
    r = bp(pc, cl)
    s = pd.Series(r[f1], index=idx[f1]).groupby(idx[f1].month).agg(["mean", "count"]).round(1)
    out.append("TDM+1 close->close by calendar month: " + str({int(k): (float(v["mean"]), int(v["count"])) for k, v in s.iterrows()}))
out.append(f"windows examined in this file: {n}")
txt = "\n".join(out)
print(txt)
open(f"{RES}/desc6_tdm1.txt", "w").write(txt + "\n")
