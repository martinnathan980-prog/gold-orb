"""Descriptive 7 (IS only): is the month-end night special? Nights by trading day of the month, split by the sign of
the month just ended, last cash session of the month, halves of the sample, quarter-ends.
Usage: python3 desc7_month_end_night.py     (needs the grids written by desc1_idx_grid.py)
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
    idx = P.index
    night = ((P[op] / P[pc] - 1) * 1e4).to_numpy()
    ym = idx.year * 12 + idx.month
    pos = np.arange(len(idx))
    first_pos = pd.Series(pos, index=idx).groupby(ym).transform("min").to_numpy()
    last_pos = pd.Series(pos, index=idx).groupby(ym).transform("max").to_numpy()
    tdm_f = pos - first_pos + 1
    tdm_b = pos - last_pos - 1
    okf = pd.Series(idx.day, index=idx).groupby(ym).transform("min").to_numpy() <= 4
    out.append(f"===== {sym}: nights (prev close -> open) by trading day of month of the session they END on (IS, mid, bp)")
    for k in (-3, -2, -1):
        m = tdm_b == k
        out.append(fmt(summ(night[m], yrs[m], f"night ending on TDM {k} open"), by_year=False)); n += 1
    for k in (1, 2, 3, 4):
        m = (tdm_f == k) & okf
        out.append(fmt(summ(night[m], yrs[m], f"night ending on TDM +{k} open"), by_year=(k == 1))); n += 1
    c = P[cl]
    mret = (c.shift(1) / c.shift(22) - 1).to_numpy() * 1e4      # known at the last close of the month
    m1 = (tdm_f == 1) & okf
    for lab, mm in (("month UP", mret > 0), ("month DOWN", mret < 0)):
        out.append(fmt(summ(night[m1 & mm], yrs[m1 & mm], f"month-end night | prev 21d {lab}"), by_year=False)); n += 1
    day = ((P[cl] / P[op] - 1) * 1e4).to_numpy()
    last30 = ((P[cl] / P["15:30" if us else "17:00"] - 1) * 1e4).to_numpy()
    m = tdm_b == -1
    out.append(fmt(summ(day[m], yrs[m], "last cash session of month"), by_year=False)); n += 1
    out.append(fmt(summ(last30[m], yrs[m], "last 30 min of the month"), by_year=False)); n += 1
    h1 = idx < pd.Timestamp("2017-07-01")
    out.append(fmt(summ(night[m1 & h1], yrs[m1 & h1], "month-end night | 2013..2017H1"), by_year=False))
    out.append(fmt(summ(night[m1 & ~h1], yrs[m1 & ~h1], "month-end night | 2017H2..2021"), by_year=False))
    q = np.isin(idx.month, [1, 4, 7, 10])
    out.append(fmt(summ(night[m1 & q], yrs[m1 & q], "quarter-end night"), by_year=False)); n += 1
    out.append(fmt(summ(night[m1 & ~q], yrs[m1 & ~q], "other month-end nights"), by_year=False)); n += 1
out.append(f"windows examined in this file: {n}")
txt = "\n".join(out)
print(txt)
open(f"{RES}/desc7_month_end_night.txt", "w").write(txt + "\n")
