"""Diagnostics on IS trades frames (no new configurations are evaluated here)."""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from run import SCRATCH, m1_is, gl  # noqa: E402


def cost_decomp(t, m1):
    """Approximate per-trade costs in R: half spread at entry+exit, slippage, commission, swap."""
    ix = m1.index
    ei = np.searchsorted(ix.values, t.entry_time.values)
    xt = t.exit_time - pd.Timedelta(minutes=1) * (t.reason != "time")
    xi = np.minimum(np.searchsorted(ix.values, xt.values), len(ix) - 1)
    spr_e = (m1.ao.values[ei] - m1.bo.values[ei])
    spr_x = (m1.ao.values[xi] - m1.bo.values[xi])
    slip = 1.5e-4 * t.entry.values * (1 + (t.reason.isin(["stop", "time", "trail", "gap"])).values)
    c_spread = (spr_e + spr_x) / 2
    risk = t.risk.values
    out = pd.DataFrame({"R": t.R.values,
                        "spread_R": c_spread / risk, "slip_R": slip / risk,
                        "comm_R": t.commission.values / risk, "swap_R": t.swap.values / risk})
    out["gross_R"] = out.R + out.spread_R + out.slip_R + out.comm_R + out.swap_R
    return out


def worst(t, k=10):
    cols = ["side", "entry_time", "exit_time", "entry", "exit", "stop", "reason", "R"]
    return t.nsmallest(k, "R")[cols]


def worst_weeks(t, k=5):
    return gl.weekly_R(t).nsmallest(k)


if __name__ == "__main__":
    m1 = m1_is()
    for k in [int(x) for x in sys.argv[1:]]:
        t = pd.read_pickle(os.path.join(SCRATCH, f"t_{k:03d}.pkl"))
        d = cost_decomp(t, m1)
        m = d.mean()
        print(f"#{k:03d} n={len(t)} net={m.R:+.3f}R gross~={m.gross_R:+.3f}R  costs: spread={m.spread_R:.3f} "
              f"slip={m.slip_R:.3f} comm={m.comm_R:.3f} swap={m.swap_R:.3f}  (median risk ${t.risk.median():.2f})")
