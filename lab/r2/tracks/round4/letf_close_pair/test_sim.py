"""Unit checks of common.sim_pairs and common.signals on synthetic quotes (no market data): fills on both sides, stop
decided on a close and executed at the next open, slippage, missing bars, time exit, fallback, stop floor, the
early-close rule (R3) and the sign condition (R4). Run before any trial (declared.json R23 a)."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

BASE = {"us100": 100.0, "us30": 50.0, "us500": 200.0}
HS = 0.01        # half spread


def make_G(nd=2):
    days = pd.bdate_range("2019-03-04", periods=nd)
    G = {"tdays": days, "t0m": np.arange(nd) * 1440 + 25_000_000}
    for s in C.SYMS:
        for c in ("bo", "bc", "ao", "ac"):
            G[(s, c)] = np.full((nd, C.NMIN), BASE[s]) + (HS if c[0] == "a" else -HS)
    return G


def setq(G, s, row, col_from, mid, which=("bo", "bc", "ao", "ac"), col_to=None):
    sl = slice(col_from, col_to)
    for c in which:
        G[(s, c)][row, sl] = mid + (HS if c[0] == "a" else -HS)


def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    assert cond, name


def main():
    e, x, k, L2 = 30, 59, 1.5, C.LEG["us30"]
    sm, ss = C.SLIP_M, C.SLIP_S
    sdpi = 0.003
    # 1) flat prices, d > 0: long us100 / short us30, time exit, net = cost only
    P = C.prepare(make_G())
    r = C.sim_pairs(P, [0], L2, [1], [1.3], [sdpi], e, x, k)
    fA, fB = 100.01 * (1 + sm), 49.99 * (1 - sm)
    eA, eB = 99.99 * (1 - sm), 50.01 * (1 + sm)
    check("flat d>0: no stop, exit column = x", (not r["stopped"][0]) and r["xc"][0] == x)
    check("flat d>0: long us100 at ask open, short us30 at bid open, market slippage",
          np.isclose(r["fill_A"][0], fA) and np.isclose(r["fill_B"][0], fB))
    check("flat d>0: net = both legs' spread + slippage, us30 weighted by h",
          np.isclose(r["net"][0], np.log(eA / fA) - 1.3 * np.log(eB / fB)) and r["net"][0] < 0)
    check("flat d>0: mid result 0", np.isclose(r["mid_same"][0], 0.0))
    # 2) flat prices, d < 0: short us100 / long us30
    r = C.sim_pairs(P, [0], L2, [-1], [1.3], [sdpi], e, x, k)
    fA, fB = 99.99 * (1 - sm), 50.01 * (1 + sm)
    eA, eB = 100.01 * (1 + sm), 49.99 * (1 - sm)
    check("flat d<0: short us100 at bid open, long us30 at ask open",
          np.isclose(r["fill_A"][0], fA) and np.isclose(r["fill_B"][0], fB))
    check("flat d<0: exits at the opposite quotes, net = -ln(eA/fA) + h ln(eB/fB)",
          np.isclose(r["exit_A"][0], eA) and np.isclose(r["exit_B"][0], eB)
          and np.isclose(r["net"][0], -np.log(eA / fA) + 1.3 * np.log(eB / fB)) and r["net"][0] < 0)
    # 3) d > 0 and us100 closes 0.6 % lower from bar 40: stop decided on the close of 40, executed at the open of 41
    G = make_G()
    setq(G, "us100", 0, 40, 100.0 * (1 - 0.006), which=("bc", "ac"))
    setq(G, "us100", 0, 41, 100.0 * (1 - 0.007))
    P = C.prepare(G)
    r = C.sim_pairs(P, [0], L2, [1], [1.0], [sdpi], e, x, k)
    check("stop d>0: decided on the close of bar 40 (offset 10)", r["stopped"][0] and r["u"][0] == 40 - e)
    check("stop d>0: executed at the open of bar 41", r["xc"][0] == 41)
    check("stop d>0: us100 sold at bid open x (1 - stop slip), us30 bought at ask open x (1 + stop slip)",
          np.isclose(r["exit_A"][0], (100.0 * (1 - 0.007) - HS) * (1 - ss)) and np.isclose(r["exit_B"][0], 50.01 * (1 + ss)))
    # 4) d < 0 and us100 rises: adverse for the short us100 leg, marked at the ASK close
    G = make_G()
    setq(G, "us100", 0, 45, 100.0 * (1 + 0.0044), which=("bc", "ac"))      # mark: -ln(ask/fill) ~ -0.0045 - spread
    P = C.prepare(G)
    r = C.sim_pairs(P, [0], L2, [-1], [1.0], [sdpi], e, x, k)
    fA = 99.99 * (1 - sm)
    fB = 50.01 * (1 + sm)
    mark = -np.log((100.0 * 1.0044 + HS) / fA) + np.log(49.99 / fB)
    check("stop d<0: mark at the ask close of us100 and the bid close of us30", np.isclose(r["pim"][0, 45 - e], mark))
    check("stop d<0: decided at bar 45 and executed at 46", r["stopped"][0] and r["u"][0] == 45 - e and r["xc"][0] == 46)
    # 5) an adverse spike in the OPEN of a bar whose close comes back does not stop (decisions on closes only)
    G = make_G()
    G[("us100", "bo")][0, 40] = 90.0
    G[("us100", "ao")][0, 40] = 90.02
    P = C.prepare(G)
    r = C.sim_pairs(P, [0], L2, [1], [1.0], [sdpi], e, x, k)
    check("open spike without a close beyond the stop: no stop", not r["stopped"][0])
    # 6) missing bars: us100 has no bar 35..50 -> last close used for the mark; us30 exit bar missing -> next open
    G = make_G()
    for c in ("bo", "bc", "ao", "ac"):
        G[("us100", c)][0, 35:51] = np.nan
        G[("us30", c)][0, 59:62] = np.nan
    G[("us30", "ao")][0, 62] = 50.03
    P = C.prepare(G)
    r = C.sim_pairs(P, [0], L2, [1], [1.0], [sdpi], e, x, k)
    check("missing bars: no spurious stop, time exit column x", (not r["stopped"][0]) and r["xc"][0] == x)
    check("missing exit bar of us30: first open at / after the exit minute (62), no fallback flag",
          np.isclose(r["exit_B"][0], 50.03 * (1 + sm)) and not r["fallback"][0])
    # 7) entry bar missing for one leg -> not filled
    G = make_G()
    for c in ("bo", "ao"):
        G[("us30", c)][0, e] = np.nan
    P = C.prepare(G)
    r = C.sim_pairs(P, [0], L2, [1], [1.0], [sdpi], e, x, k)
    check("entry bar missing: not filled, no stop", (not r["filled"][0]) and (not r["stopped"][0]))
    # 8) no bar of us100 from the exit minute to the end of the grid -> last close, flagged
    G = make_G()
    for c in ("bo", "bc", "ao", "ac"):
        G[("us100", c)][0, 59:] = np.nan
    P = C.prepare(G)
    r = C.sim_pairs(P, [0], L2, [1], [1.0], [sdpi], e, x, k)
    check("no exit bar until 16:59: last close (bid close of bar 58) x (1 - slip), fallback flagged",
          r["fallback"][0] and np.isclose(r["exit_A"][0], 99.99 * (1 - sm)))
    # 9) h weights leg 2: us30 rises 0.3 % (adverse for the short us30 leg of d > 0)
    G = make_G()
    setq(G, "us30", 0, 50, 50.15, which=("bc", "ac"))
    setq(G, "us30", 0, 51, 50.15, which=("bo", "ao"))
    P = C.prepare(G)
    r1 = C.sim_pairs(P, [0], L2, [1], [1.0], [sdpi], e, x, k)       # mark ~ -0.0034 -> no stop
    r2 = C.sim_pairs(P, [0], L2, [1], [1.4], [sdpi], e, x, k)       # mark ~ -0.0047 -> stop at 50
    check("h = 1.0: no stop", not r1["stopped"][0])
    check("h = 1.4: stop decided at bar 50, executed at 51", r2["stopped"][0] and r2["u"][0] == 50 - e and r2["xc"][0] == 51)
    pim = np.log(99.99 / (100.01 * (1 + sm))) - 1.4 * np.log(50.16 / (49.99 * (1 - sm)))
    check("h = 1.4: mark value at the stop bar", np.isclose(r2["pim"][0, 50 - e], pim))
    # 10) a stop decided on the close of the bar before the exit bar is executed at the exit bar's open with stop slip
    G = make_G()
    setq(G, "us100", 0, 58, 99.0, which=("bc", "ac"))
    setq(G, "us100", 0, 59, 99.0, which=("bo", "ao"))
    P = C.prepare(G)
    r = C.sim_pairs(P, [0], L2, [1], [1.0], [sdpi], e, x, k)
    check("stop on the close of bar x-1: executed at x with stop slippage",
          r["stopped"][0] and r["xc"][0] == x and np.isclose(r["exit_A"][0], 98.99 * (1 - ss)))
    # 11) mid mode: no spread, no slippage
    P = C.prepare(make_G())
    r = C.sim_pairs(P, [0], L2, [1], [1.3], [sdpi], e, x, k, mode="mid")
    check("mid mode on flat prices: net 0", np.isclose(r["net"][0], 0.0))
    # 12) stop floor
    ok, spA, spB = C.spread_floor_ok(P, np.array([0]), L2, np.array([1.0]), np.array([0.00001]), e, k)
    check("stop floor refuses a stop closer than 3 spreads", not ok[0])
    ok, _, _ = C.spread_floor_ok(P, np.array([0]), L2, np.array([1.0]), np.array([0.003]), e, k)
    check("stop floor accepts 1.5 x 30 bp against 3 x (2 + 4) bp", ok[0])
    # 13) signals: early-close rule (R3), sign condition (R4), trailing windows exclude the current session
    nd = 70
    days = pd.bdate_range("2019-01-07", periods=nd)
    rng = np.random.default_rng(1)
    G = {"tdays": days, "t0m": np.arange(nd) * 1440 + 25_000_000}
    m100 = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, nd)))
    m30 = 50 * np.exp(np.cumsum(rng.normal(0, 0.01, nd)))
    m500 = 200 * np.exp(np.cumsum(rng.normal(0, 0.01, nd)))
    for s, m in (("us100", m100), ("us30", m30), ("us500", m500)):
        for c in ("bo", "bc", "ao", "ac"):
            a = np.repeat(m[:, None], C.NMIN, axis=1) * np.exp(rng.normal(0, 0.0005, (nd, C.NMIN)))
            G[(s, c)] = a + (HS if c[0] == "a" else -HS)
    half = np.zeros(nd, bool)
    half[30] = True
    srow = np.flatnonzero(~half)[1:]
    cal = {"tdays": days, "half": half, "srow": srow, "prev_row": srow - 1, "prev_half": half[srow - 1],
           "sessions": days[srow]}
    P = C.prepare(G)
    sg = C.signals(P, cal, thr=0.0, win=20, minv=10)
    j31 = int(np.flatnonzero(srow == 31)[0])
    check("R3: d missing on the session after an early close", np.isnan(sg["d100"][j31]) and np.isnan(sg["d2"][j31]))
    j = int(np.flatnonzero(srow == 40)[0])
    d100 = np.log(P["mc"][0, 40, 29] / P["mc"][0, 39, 59])
    check("R2: d = ln(mid close 15:29 / previous session's mid close 15:59)", np.isclose(sg["d100"][j], d100))
    sd = np.std(sg["d100"][j - 20:j][np.isfinite(sg["d100"][j - 20:j])], ddof=1)
    check("R5: sd_d over the previous 20 sessions (current excluded)", np.isclose(sg["sd_d"][j], sd))
    same = np.isfinite(sg["d100"]) & np.isfinite(sg["d2"]) & (np.sign(sg["d100"]) == np.sign(sg["d2"])) & np.isfinite(sg["sd_d"])
    check("R4: with thr = 0 the condition is exactly 'same sign'", np.array_equal(sg["cond"], same))
    r100 = np.log(P["mo"][0, srow, 59] / P["mo"][0, srow, 30])
    r30 = np.log(P["mo"][1, srow, 59] / P["mo"][1, srow, 30])
    hh = np.std(r100[j - 20:j], ddof=1) / np.std(r30[j - 20:j], ddof=1)
    check("R6: h = sd(us100) / sd(us30) of the previous 20 sessions' 15:30 -> 15:59 mid returns", np.isclose(sg["h"][j], hh))
    pi = sg["dir"] * (r100 - sg["h"] * r30)
    w = pi[j - 20:j]
    check("R7: sd_pi over the previous sessions' direction-signed hedged returns", np.isclose(sg["sdpi"][j], np.std(w[np.isfinite(w)], ddof=1)))
    print("all synthetic checks passed")


if __name__ == "__main__":
    main()
