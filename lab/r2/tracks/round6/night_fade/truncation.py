"""Truncation test of night_fade (PROTOCOL_V3 Addendum L) BEFORE the run, in sample only (L32).

For at least 50 decisions per cross (main configuration, base frame): mu, sigma, side, D, C, the cost-filter result and the
stop distance recomputed on the frame CUT at the decision time (rows with ts < decision time: every M1 bar that has ended
by then, nothing later) must be exactly equal to the full-frame values. Decisions sampled with numpy default_rng(0), crosses
in basket order: 40 decisions with a band crossing (all of them if fewer) and 20 with a usable band and no crossing, drawn
among the tradable evenings of 2013-2021. No exit, no return.
Output: results/r2/round6/night_fade/truncation.json
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

import time  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

N_SIGNAL, N_QUIET, SEED = 40, 20, 0
FIELDS = ("mu", "sigma", "side", "D", "C", "passes_filter", "stop_dist", "usable", "has_bar")


def same(a, b):
    if isinstance(a, (bool, np.bool_)) or isinstance(b, (bool, np.bool_)):
        return bool(a) == bool(b)
    a, b = float(a), float(b)
    return (a == b) or (np.isnan(a) and np.isnan(b))


def main(crosses=None):
    t0 = time.time()
    crosses = C.CROSSES if crosses is None else crosses
    p = C.CONFIG["main"]["params"]
    rng = np.random.default_rng(SEED)
    out = {"what": "truncation test: decision quantities on frames cut at the decision time vs the full frame",
           "config": "main", "seed": SEED, "per_cross": {}}
    for c in crosses:
        full = C.load_base(c)
        bk = C.Book(full, c)
        tb = C.decision_table(bk, p)
        sig = np.flatnonzero((tb.usable & (tb.side != 0)).to_numpy())
        quiet = np.flatnonzero((tb.usable & (tb.side == 0)).to_numpy())
        pick = np.r_[rng.choice(sig, min(N_SIGNAL, len(sig)), replace=False),
                     rng.choice(quiet, min(N_QUIET, len(quiet)), replace=False)]
        pick = np.sort(pick)
        rows, bad = [], []
        for i in pick:
            r = tb.iloc[int(i)]
            t = int(r.dec_ns)
            hi = int(np.searchsorted(bk.ns, t, side="left"))
            cut = full.iloc[:hi]
            assert len(cut) == 0 or cut.index.as_unit("ns").asi8.max() < t
            bc = C.Book(cut, c)
            tc = C.decision_table(bc, p, ev=pd.DatetimeIndex([r.evening]))
            rc = tc[tc.k == r.k].iloc[0]
            assert int(rc.dec_ns) == t
            eq = {f: same(r[f], rc[f]) for f in FIELDS}
            row = {"evening": str(pd.Timestamp(r.evening).date()), "k": int(r.k),
                   "decision_utc": str(pd.Timestamp(t, unit="ns", tz="UTC")), "cut_rows": hi,
                   "side": int(r.side), "status_full": C.STATUS[int(r.status)], "all_equal": all(eq.values())}
            if not row["all_equal"]:
                row["full"] = {f: (r[f].item() if hasattr(r[f], "item") else r[f]) for f in FIELDS}
                row["cut"] = {f: (rc[f].item() if hasattr(rc[f], "item") else rc[f]) for f in FIELDS}
                bad.append(row)
            rows.append(row)
        out["per_cross"][c] = {"n_tested": len(rows), "n_with_band_crossing": int(sum(1 for r in rows if r["side"] != 0)),
                               "n_orders_among_them": int(sum(1 for r in rows if r["status_full"] == "order")),
                               "all_equal": not bad, "failures": bad,
                               "years_covered": sorted({r["evening"][:4] for r in rows}),
                               "sample": rows[:5]}
        print(c, "tested", len(rows), "crossings", out["per_cross"][c]["n_with_band_crossing"], "all equal", not bad,
              round(time.time() - t0, 1), "s", flush=True)
        del full, bk, tb
    out["all_equal"] = all(v["all_equal"] for v in out["per_cross"].values())
    out["min_tested_per_cross"] = min(v["n_tested"] for v in out["per_cross"].values())
    out["seconds"] = round(time.time() - t0, 1)
    out["code_sha256"] = C.code_hashes()
    C.jdump(out, os.path.join(C.OUT, "truncation.json"))
    print("all equal", out["all_equal"], "min tested", out["min_tested_per_cross"])
    return out


if __name__ == "__main__":
    main()
