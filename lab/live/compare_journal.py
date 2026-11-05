"""Parity check between the MT5 EA journal and the lab backtest.

1. In MT5: Strategy Tester, EA GoldOrb_Donchian4H, symbol XAUUSD, "Every tick based on real ticks",
   e.g. 2025-01-01 -> 2025-12-31, mode 0 (alerts). The EA writes
   %APPDATA%/MetaQuotes/Terminal/Common/Files/GoldOrb/tester_journal_XAUUSD.csv
2. Copy that file here and run:
       python3 lab/live/compare_journal.py tester_journal_XAUUSD.csv [--track trend --name donch4h_stop]

It matches every EA ENTRY with a lab trade of the same side entered within +/- 4 h and compares R.
Broker feeds differ from Dukascopy (spreads, quotes, server clock), so expect a high but imperfect
match rate (> 80 %) and similar total R; a low match rate means the EA and the backtest disagree.
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

LAB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, LAB)
sys.path.insert(0, os.path.join(LAB, "audit"))
import goldlab as gl  # noqa: E402
from audit import load_strategy  # noqa: E402


def read_journal(path):
    j = pd.read_csv(path, sep=";")
    j["t"] = pd.to_datetime(j["time_utc"], format="%Y.%m.%d %H:%M:%S", utc=True)
    ent = j[j.event == "ENTRY"].reset_index(drop=True)
    ext = j[j.event == "EXIT"].reset_index(drop=True)
    n = min(len(ent), len(ext))
    ea = pd.DataFrame({"entry_time": ent.t[:n], "side": ent.side[:n].astype(int), "entry": ent.price[:n],
                       "exit_time": ext.t[:n].to_numpy(), "R": ext.R[:n].to_numpy(), "reason": ext.note[:n].to_numpy()})
    return ea


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("journal")
    ap.add_argument("--track", default="trend")
    ap.add_argument("--name", default="donch4h_stop")
    ap.add_argument("--tol_h", type=float, default=4.0)
    ap.add_argument("--with_costs", action="store_true",
                    help="compare with the lab's costed R (default: zero-cost lab run, like the EA's paper R)")
    a = ap.parse_args()
    ea = read_journal(a.journal)
    if ea.empty:
        print("no completed trades in the journal")
        return
    t0, t1 = ea.entry_time.min() - pd.Timedelta(days=1), ea.entry_time.max() + pd.Timedelta(days=8)
    mod = load_strategy(a.track)
    m1 = gl.load_m1("xauusd", start=t0 - pd.Timedelta(days=120), end=t1)
    from goldlab.sim import Costs
    zero = None if a.with_costs else Costs(commission=0, slip_bps=0, swap_long=0, swap_short=0)
    lab = gl.simulate(m1, mod.make_orders(m1, **mod.FINALISTS[a.name]), costs=zero)
    lab = lab[(lab.entry_time >= ea.entry_time.min() - pd.Timedelta(hours=a.tol_h)) &
              (lab.entry_time <= ea.entry_time.max() + pd.Timedelta(hours=a.tol_h))].reset_index(drop=True)
    used, pairs = set(), []
    for i, r in ea.iterrows():
        d = (lab.entry_time - r.entry_time).abs()
        ok = (lab.side == r.side) & (d <= pd.Timedelta(hours=a.tol_h))
        cand = [k for k in lab.index[ok] if k not in used]
        if cand:
            k = min(cand, key=lambda q: d[q])
            used.add(k)
            pairs.append((i, k))
    m = pd.DataFrame([{"ea_time": ea.entry_time[i], "lab_time": lab.entry_time[k], "side": ea.side[i],
                       "ea_R": ea.R[i], "lab_R": lab.R[k]} for i, k in pairs])
    print(f"EA trades {len(ea)} | lab trades {len(lab)} | matched {len(m)} "
          f"({len(m)/len(ea):.0%} of EA, {len(m)/max(len(lab),1):.0%} of lab)")
    print(f"total R  EA {ea.R.sum():+.1f} | lab {lab.R.sum():+.1f}")
    if len(m) > 2:
        print(f"matched trades: corr(R) {np.corrcoef(m.ea_R, m.lab_R)[0,1]:.2f} | mean |dR| {np.mean(np.abs(m.ea_R-m.lab_R)):.2f}")
    un_ea = ea.drop(index=[i for i, _ in pairs])
    un_lab = lab.drop(index=[k for _, k in pairs])
    if len(un_ea):
        print("EA trades without a lab match:\n", un_ea[["entry_time", "side", "entry", "R"]].head(15).to_string())
    if len(un_lab):
        print("lab trades without an EA match:\n", un_lab[["entry_time", "side", "entry", "R"]].head(15).to_string())


if __name__ == "__main__":
    main()
