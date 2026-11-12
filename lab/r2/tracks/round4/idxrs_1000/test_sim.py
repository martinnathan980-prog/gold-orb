"""Unit checks of common.sim_pairs on synthetic quotes (no market data): fills, stop decided on a close and executed
at the next open, slippage, missing bars, time exit, R. Run before any trial."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402


def make_G(nd=2):
    days = pd.bdate_range("2019-03-04", periods=nd)
    G = {"days": days, "t0m": np.arange(nd) * 1440 + 25_000_000}
    for i, s in enumerate(C.SYMS):
        base = [100.0, 50.0, 200.0][i]
        for c in ("bo", "bc", "ao", "ac"):
            a = np.full((nd, C.NMIN), base)
            G[(s, c)] = a + (0.01 if c[0] == "a" else -0.01)        # spread 0.02
    return G


def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    assert cond, name


def main():
    e, x, k = 30, 385, 1.5
    # 1) flat prices: time exit, net = cost only
    G = make_G()
    P = C.prepare(G)
    sdpi = 0.003
    r = C.sim_pairs(P, [0], [0], [1], [1.2], [sdpi], e, x, k)
    fS, fW = 100.01 * (1 + C.SLIP_M), 49.99 * (1 - C.SLIP_M)
    eS, eW = 99.99 * (1 - C.SLIP_M), 50.01 * (1 + C.SLIP_M)
    exp_net = np.log(eS / fS) - 1.2 * np.log(eW / fW)
    check("flat: no stop", not r["stopped"][0] and r["xc"][0] == x)
    check("flat: fills at ask/bid open with market slippage", np.isclose(r["fill_S"][0], fS) and np.isclose(r["fill_W"][0], fW))
    check("flat: net = spread + slippage of both legs", np.isclose(r["net"][0], exp_net))
    check("flat: mid result 0", np.isclose(r["mid_same"][0], 0.0))
    # 2) leg S falls at the close of bar 100 -> stop decided at 100, executed at the open of 101 with stop slippage
    G = make_G()
    for c in ("bc",):
        G[("us100", c)][0, 100:] = 100.0 * (1 - 0.006) - 0.01
    for c in ("bo",):
        G[("us100", c)][0, 101:] = 100.0 * (1 - 0.007) - 0.01
    G[("us100", "ac")][0, 100:] = 100.0 * (1 - 0.006) + 0.01
    G[("us100", "ao")][0, 101:] = 100.0 * (1 - 0.007) + 0.01
    P = C.prepare(G)
    r = C.sim_pairs(P, [0], [0], [1], [1.0], [sdpi], e, x, k)
    check("stop: decided on the close of bar 100 (offset 70)", r["stopped"][0] and r["u"][0] == 100 - e)
    check("stop: executed at the open of bar 101", r["xc"][0] == 101)
    eS = (100.0 * (1 - 0.007) - 0.01) * (1 - C.SLIP_S)
    eW = 50.01 * (1 + C.SLIP_S)
    check("stop: exit prices bid/ask open with stop slippage", np.isclose(r["exit_S"][0], eS) and np.isclose(r["exit_W"][0], eW))
    # 3) the open of bar 100 alone (a spike inside a bar that closes back) does not stop: only closes decide
    G = make_G()
    G[("us100", "bo")][0, 100] = 90.0
    P = C.prepare(G)
    r = C.sim_pairs(P, [0], [0], [1], [1.0], [sdpi], e, x, k)
    check("open spike without a close below: no stop", not r["stopped"][0])
    # 4) missing bars: S has no bar 100..120 -> its last close is used for the mark; exit bar missing -> next bar
    G = make_G()
    for c in ("bo", "bc", "ao", "ac"):
        G[("us100", c)][0, 100:121] = np.nan
        G[("us500", c)][0, 385:388] = np.nan
    P = C.prepare(G)
    r = C.sim_pairs(P, [0], [0], [1], [1.0], [sdpi], e, x, k)
    check("missing bars: no spurious stop, time exit", not r["stopped"][0] and r["xc"][0] == x)
    check("missing exit bar of W: next available open used (no fallback flag)",
          np.isclose(r["exit_W"][0], 50.01 * (1 + C.SLIP_M)) and not r["fallback"][0])
    # 5) entry bar missing for one leg -> not filled
    G = make_G()
    for c in ("bo", "ao"):
        G[("us500", c)][0, e] = np.nan
    P = C.prepare(G)
    r = C.sim_pairs(P, [0], [0], [1], [1.0], [sdpi], e, x, k)
    check("entry bar missing: not filled, no stop", (not r["filled"][0]) and (not r["stopped"][0]))
    # 6) W rises (the short leg loses): h scales its weight
    G = make_G()
    for c in ("bc", "ac"):
        G[("us500", c)][0, 200:] += 0.15
    for c in ("bo", "ao"):
        G[("us500", c)][0, 201:] += 0.15
    P = C.prepare(G)
    # mark at bar 200: ln(99.99/fS) - h ln(50.16/fW) = -0.00022 - h x 0.003415 ; stop level -0.0045
    r1 = C.sim_pairs(P, [0], [0], [1], [1.0], [sdpi], e, x, k)      # -0.00364: no stop
    r2 = C.sim_pairs(P, [0], [0], [1], [1.3], [sdpi], e, x, k)      # -0.00466: stop at 200
    check("short leg: h = 1.0 no stop", not r1["stopped"][0])
    check("short leg: h = 1.3 stop decided at bar 200", r2["stopped"][0] and r2["u"][0] == 200 - e and r2["xc"][0] == 201)
    pim = np.log(99.99 / (100.01 * (1 + C.SLIP_M))) - 1.3 * np.log(50.16 / (49.99 * (1 - C.SLIP_M)))
    check("short leg: mark value at the stop bar", np.isclose(r2["pim"][0, 200 - e], pim))
    # 7) spread floor
    ok, spS, spW = C.spread_floor_ok(P, np.array([0]), np.array([0]), np.array([1]), np.array([1.0]), np.array([0.00001]), e, k)
    check("stop floor refuses a stop closer than 3 spreads", not ok[0])
    print("all synthetic checks passed")


if __name__ == "__main__":
    main()
