"""Lens `cluster`: self-checks of the portfolio engine before any guard is evaluated.

1. Without caps the reference takes every trade: its total equals the sum of R, and on the common window it equals
   the stake study's net reference (787.4 R, 5,207 trades) up to the two trades open at the end of 2021 (closed at
   the last in-sample bar here, closed in 2022 in the official files).
2. With caps (6 positions, 2 per market) the engine takes exactly the trades that r2/tracks/stake/account.py takes
   (an independent loop, run here on a 1e9 EUR account so that minimum lots and margin never bind).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import book as B  # noqa: E402

import numpy as np  # noqa: E402

sys.path.insert(0, os.path.join(C.LAB, "r2", "tracks", "stake"))
import account as A  # noqa: E402


def main():
    out = {}
    for mode in ("fp", "stress"):
        d = B.build(mode)
        a = B.arrays(d)
        sel_c = (d.t_in >= C.COMMON_START).to_numpy()
        m0, w0 = B.run(a, 0, caps=False)
        m1, w1 = B.run(a, 0, caps=True)
        st0 = B.stats(d, m0)
        st1 = B.stats(d, m1)
        res = {"n_whole": int(len(d)), "sum_R_whole": round(float(d.R.sum()), 3),
               "uncapped_whole_total": round(float((m0 * d.R.to_numpy()).sum()), 3),
               "uncapped_common": {k: st0[k] for k in ("n_taken", "total_R", "worst_day", "worst_week", "max_dd")},
               "capped_common": {k: st1[k] for k in ("n_taken", "total_R", "worst_day", "worst_week", "max_dd")},
               "capped_skips_whole": int((w1 == 2).sum()), "capped_skips_common": int(((w1 == 2) & sel_c).sum()),
               "broker_refusals": int((w1 == 3).sum())}
        # independent loop: account.py on a huge account (no minimum-lot / margin / kill effects), common window
        dc = d[sel_c].reset_index(drop=True).copy()
        dc["pnl"] = dc.R * dc.risk
        fr = A.frame(d=dc[["sleeve", "sym", "fam", "t_in", "t_out", "entry", "risk", "pnl", "R"]])
        acc = A.account({}, start=1e9, base_pct=1.0, d=fr, compound=False, kill_dd=0.99)
        ae = B.arrays(B_like(d, sel_c))
        me, we = B.run(ae, 0, caps=True)
        res["account_py_common"] = {"n_taken": acc["n_taken"], "position_cap_skips": acc["skipped"]["position_cap"],
                                    "min_lot_skips": acc["skipped"]["min_lot"], "margin_skips": acc["skipped"]["margin"]}
        res["engine_on_same_frame"] = {"n_taken": int((me > 0).sum()), "position_cap_skips": int((we == 2).sum())}
        res["engine_equals_account_py"] = bool(acc["n_taken"] == int((me > 0).sum())
                                               and acc["skipped"]["position_cap"] == int((we == 2).sum()))
        out[mode] = res
        print(mode, json.dumps(res, indent=1))
    json.dump(out, open(os.path.join(C.OUT, "engine_check.json"), "w"), indent=1)


def B_like(d, sel):
    """The same book restricted to the common window (engine state starts empty there, as account.py does)."""
    return d[sel].reset_index(drop=True)


if __name__ == "__main__":
    main()
