"""Descriptive 2 (IS only): overnight / intraday returns of the index CFDs conditional on what came before
(reversal vs continuation), by weekday and around the turn of the month.  Uses the price grids saved by
desc1_idx_grid.py (IS only).   Usage: python3 desc2_idx_cond.py us500 [us100 ger40]
"""
import sys

import numpy as np
import pandas as pd

from desc import RES, fmt, load_grid, summ



def run(sym):
    P = load_grid(sym)
    us = sym != "ger40"
    cl, op = ("16:00", "09:30") if us else ("17:30", "09:00")
    pc = "p" + cl
    yrs = P.index.year.to_numpy()
    bp = lambda a, b: (P[b] / P[a] - 1) * 1e4
    night = bp(pc, op)                       # previous close -> open
    day = bp(op, cl)                         # open -> close of day D
    cc = bp(pc, cl)
    # previous day's components (aligned on the row of day D): shift by one cash session
    prev_day = day.shift(1)
    prev_cc = cc.shift(1)
    prev_night = night.shift(1)
    if us:
        last2h_prev = bp("14:00", "16:00").shift(1)
        last1h_prev = bp("15:00", "16:00").shift(1)
        wins = {"night close->open": night, "close->04:00": bp(pc, "04:00"), "close->02:00": bp(pc, "02:00"),
                "eve 18:30->09:30": bp("e18:30", "09:30"), "eve 20:00->04:00": bp("e20:00", "04:00"),
                "02:00->09:30": bp("02:00", "09:30"), "04:00->09:30": bp("04:00", "09:30")}
    else:
        last2h_prev = bp("15:30", "17:30").shift(1)
        last1h_prev = bp("16:30", "17:30").shift(1)
        wins = {"night close->open": night, "22:00->09:00": bp("e22:00", "09:00"), "17:30->22:00": bp(pc, "e22:00"),
                "00:30->09:00": bp("00:30", "09:00"), "22:00->08:00": bp("e22:00", "08:00")}
    out = [f"===== {sym}: conditional returns (IS, mid, bp); {len(P)} sessions"]
    nwin = 0

    def add(label, r, mask=None):
        nonlocal nwin
        nwin += 1
        x = r if mask is None else r[mask]
        y = yrs if mask is None else yrs[np.asarray(mask)]
        out.append(fmt(summ(x.to_numpy(), y, label)))

    out.append("--- A. night windows conditional on the PREVIOUS cash session (open->close) sign")
    for k, r in wins.items():
        add(f"{k} | prev day DOWN", r, (prev_day < 0).to_numpy())
        add(f"{k} | prev day UP", r, (prev_day > 0).to_numpy())
    out.append("--- B. night close->open by size of previous cash-session move (fixed thresholds, bp)")
    for lo, hi in [(-1e9, -100), (-100, -50), (-50, -20), (-20, 0), (0, 20), (20, 50), (50, 100), (100, 1e9)]:
        add(f"night | prev day in [{lo:.0f},{hi:.0f})", night, ((prev_day >= lo) & (prev_day < hi)).to_numpy())
    out.append("--- C. night conditional on previous last 2h / last 1h / previous close-to-close")
    add("night | prev last2h DOWN", night, (last2h_prev < 0).to_numpy())
    add("night | prev last2h UP", night, (last2h_prev > 0).to_numpy())
    add("night | prev last1h DOWN", night, (last1h_prev < 0).to_numpy())
    add("night | prev last1h UP", night, (last1h_prev > 0).to_numpy())
    add("night | prev close-close DOWN", night, (prev_cc < 0).to_numpy())
    add("night | prev close-close UP", night, (prev_cc > 0).to_numpy())
    add("night | prev last2h < -30bp", night, (last2h_prev < -30).to_numpy())
    add("night | prev last2h > +30bp", night, (last2h_prev > 30).to_numpy())
    out.append("--- D. cash session conditional on the night before it (gap) and on previous day")
    add("day | night UP", day, (night > 0).to_numpy())
    add("day | night DOWN", day, (night < 0).to_numpy())
    add("day | night > +30bp", day, (night > 30).to_numpy())
    add("day | night < -30bp", day, (night < -30).to_numpy())
    add("day | prev day DOWN", day, (prev_day < 0).to_numpy())
    add("day | prev day UP", day, (prev_day > 0).to_numpy())
    if us:
        f30 = bp("09:30", "10:00")
        add("09:30->10:00 | night UP", f30, (night > 0).to_numpy())
        add("09:30->10:00 | night DOWN", f30, (night < 0).to_numpy())
        l30 = bp("15:30", "16:00")
        gap10 = bp(pc, "10:00")
        add("15:30->16:00 | close->10:00 UP", l30, (gap10 > 0).to_numpy())
        add("15:30->16:00 | close->10:00 DOWN", l30, (gap10 < 0).to_numpy())
        r1530 = bp("09:30", "15:30")
        add("15:30->16:00 | 09:30->15:30 UP", l30, (r1530 > 0).to_numpy())
        add("15:30->16:00 | 09:30->15:30 DOWN", l30, (r1530 < 0).to_numpy())
    out.append("--- E. weekday (of the cash session D; the night is the one that ENDS on D's open)")
    dow = P.index.dayofweek.to_numpy()
    for d, nm in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri"]):
        add(f"night ending {nm} open", night, dow == d)
    for d, nm in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri"]):
        add(f"cash session {nm}", day, dow == d)
    out.append("--- F. turn of month: trading day of month (TDM; +1 = first session of the month, -1 = last)")
    idx = P.index
    ym = idx.year * 12 + idx.month
    first_pos = pd.Series(np.arange(len(idx)), index=idx).groupby(ym).transform("min").to_numpy()
    last_pos = pd.Series(np.arange(len(idx)), index=idx).groupby(ym).transform("max").to_numpy()
    pos = np.arange(len(idx))
    tdm_fwd = pos - first_pos + 1          # 1,2,3..
    tdm_back = pos - last_pos - 1          # -1 (last), -2, ...
    for k in (-4, -3, -2, -1):
        add(f"close->close TDM {k}", cc, tdm_back == k)
    for k in (1, 2, 3, 4, 5):
        add(f"close->close TDM +{k}", cc, tdm_fwd == k)
    tom = (tdm_back == -1) | (tdm_fwd <= 3)
    add("close->close ToM (-1..+3)", cc, tom)
    add("close->close rest of month", cc, ~tom)
    add("night ToM (-1..+3)", night, tom)
    add("night rest of month", night, ~tom)
    add("cash session ToM (-1..+3)", day, tom)
    add("cash session rest of month", day, ~tom)
    out.append(f"windows examined in this file: {nwin}")
    txt = "\n".join(out)
    print(txt, flush=True)
    with open(f"{RES}/desc2_cond_{sym}.txt", "w") as f:
        f.write(txt + "\n")


if __name__ == "__main__":
    for s in sys.argv[1:] or ["us500"]:
        run(s)
