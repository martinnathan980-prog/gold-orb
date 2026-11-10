"""Descriptive 5 (IS only): "tug of war" in the index CFDs -- does the cash session reverse the previous cash
session, and does the night continue it?  Correlations by year, conditional means by size of the previous
move, entry-time variants.  Uses the price grids saved by desc1 (IS only).
Usage: python3 desc5_idx_tugofwar.py us100 us500 ger40
"""
import sys

import numpy as np
import pandas as pd

from desc import RES, fmt, summ, tstat

SCR = "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad"


def run(sym):
    P = pd.read_pickle(f"{SCR}/P_{sym}.pkl")
    us = sym != "ger40"
    cl, op = ("16:00", "09:30") if us else ("17:30", "09:00")
    pc = "p" + cl
    yrs = P.index.year.to_numpy()
    bp = lambda a, b: (P[b] / P[a] - 1) * 1e4
    night = bp(pc, op)
    day = bp(op, cl)
    prev_day = day.shift(1)
    # the previous row must be the previous cash session actually present in the grid
    out = [f"===== {sym}: tug of war (IS, mid, bp); {len(P)} sessions"]
    n = 0
    out.append("--- correlations (all IS / by year): corr(prev day, night), corr(prev day, day), corr(night, day)")
    df = pd.DataFrame({"pd": prev_day, "n": night, "d": day, "y": yrs}).dropna()
    line = lambda a, b: f"all {df[a].corr(df[b]):+.3f} | " + " ".join(
        f"{str(y)[2:]}:{g[a].corr(g[b]):+.2f}" for y, g in df.groupby("y"))
    out.append("corr(prev day, night): " + line("pd", "n"))
    out.append("corr(prev day, day)  : " + line("pd", "d"))
    out.append("corr(night, day)     : " + line("n", "d"))
    out.append("rank corr(prev day, day): " + f"{df['pd'].rank().corr(df['d'].rank()):+.3f}"
               + " | rank corr(prev day, night): " + f"{df['pd'].rank().corr(df['n'].rank()):+.3f}")
    out.append("--- cash session by size of the PREVIOUS cash session (fixed thresholds in bp)")
    for lo, hi in [(-1e9, -100), (-100, -50), (-50, -20), (-20, 0), (0, 20), (20, 50), (50, 100), (100, 1e9)]:
        m = ((prev_day >= lo) & (prev_day < hi)).to_numpy()
        out.append(fmt(summ(day.to_numpy()[m], yrs[m], f"day | prev day in [{lo:.0f},{hi:.0f})"))); n += 1
    out.append("--- symmetric fade: sign(-prev day) * day   and   follow: sign(prev day) * night")
    fade = -np.sign(prev_day) * day
    out.append(fmt(summ(fade.to_numpy(), yrs, "fade prev day in cash session (L+S)"))); n += 1
    foll = np.sign(prev_day) * night
    out.append(fmt(summ(foll.to_numpy(), yrs, "follow prev day overnight (L+S)"))); n += 1
    out.append("--- entry/exit variants of 'long the cash session after a DOWN cash session'")
    dn = (prev_day < 0).to_numpy()
    up = (prev_day > 0).to_numpy()
    if us:
        V = [("09:30", "16:00"), ("09:30", "15:30"), ("10:00", "16:00"), ("09:30", "12:00"), ("12:00", "16:00"),
             ("09:30", "10:00"), ("10:00", "15:00"), (pc, "16:00"), (pc, "09:30"), ("04:00", "16:00"), ("08:00", "16:00")]
    else:
        V = [("09:00", "17:30"), ("09:00", "12:00"), ("12:00", "17:30"), ("10:00", "17:30"), (pc, "17:30"), (pc, "09:00")]
    for a, b in V:
        r = bp(a, b).to_numpy()
        out.append(fmt(summ(r[dn], yrs[dn], f"{a}->{b} | prev day DOWN"))); n += 1
        out.append(fmt(summ(r[up], yrs[up], f"{a}->{b} | prev day UP"))); n += 1
    out.append("--- alternative signals for the cash-session long (09:30->16:00 / 09:00->17:30)")
    cc_prev = bp(pc, cl).shift(1)
    out.append(fmt(summ(day.to_numpy()[(cc_prev < 0).to_numpy()], yrs[(cc_prev < 0).to_numpy()], "day | prev close-close DOWN"))); n += 1
    out.append(fmt(summ(day.to_numpy()[(cc_prev > 0).to_numpy()], yrs[(cc_prev > 0).to_numpy()], "day | prev close-close UP"))); n += 1
    two = ((prev_day < 0) & (day.shift(2) < 0)).to_numpy()
    out.append(fmt(summ(day.to_numpy()[two], yrs[two], "day | prev TWO days DOWN"))); n += 1
    one = ((prev_day < 0) & (day.shift(2) > 0)).to_numpy()
    out.append(fmt(summ(day.to_numpy()[one], yrs[one], "day | prev DOWN, day before UP"))); n += 1
    # the signal seen at the open: previous close -> today's open included
    pc_op = (bp(op, cl).shift(1) + night)        # approx prev open -> today's open
    m = (pc_op < 0).to_numpy()
    out.append(fmt(summ(day.to_numpy()[m], yrs[m], "day | prev open -> today's open DOWN"))); n += 1
    m = ((prev_day < 0) & (night < 0)).to_numpy()
    out.append(fmt(summ(day.to_numpy()[m], yrs[m], "day | prev day DOWN & night DOWN"))); n += 1
    m = ((prev_day < 0) & (night > 0)).to_numpy()
    out.append(fmt(summ(day.to_numpy()[m], yrs[m], "day | prev day DOWN & night UP"))); n += 1
    out.append("--- by weekday: day | prev day DOWN")
    dow = P.index.dayofweek.to_numpy()
    for d_, nm in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri"]):
        m = dn & (dow == d_)
        out.append(fmt(summ(day.to_numpy()[m], yrs[m], f"day {nm} | prev day DOWN"), by_year=False)); n += 1
    out.append("--- first vs second half of IS: day | prev day DOWN, and the unconditional day")
    h1 = (P.index < pd.Timestamp("2017-07-01"))
    for lab, m in (("2013..2017H1", h1), ("2017H2..2021", ~h1)):
        out.append(fmt(summ(day.to_numpy()[dn & m], yrs[dn & m], f"day | prev DOWN | {lab}"), by_year=False))
        out.append(fmt(summ(day.to_numpy()[up & m], yrs[up & m], f"day | prev UP   | {lab}"), by_year=False))
        out.append(fmt(summ(night.to_numpy()[up & m], yrs[up & m], f"night | prev UP | {lab}"), by_year=False))
        out.append(fmt(summ(night.to_numpy()[dn & m], yrs[dn & m], f"night | prev DOWN | {lab}"), by_year=False))
    out.append(f"windows examined in this file: {n}")
    txt = "\n".join(out)
    print(txt, flush=True)
    with open(f"{RES}/desc5_tugofwar_{sym}.txt", "w") as f:
        f.write(txt + "\n")


if __name__ == "__main__":
    for s in sys.argv[1:] or ["us100"]:
        run(s)
