"""Lead synthesis A, rule 3: truncation tests of the five kept changes on the whole pipeline.  IN SAMPLE ONLY.

For a sample of trades of 2018-02..2021 (half where the change acts, half random; FP costs), the pipeline
(frozen rule rebuilt on the cut frame, the change, broker refusal, one position at a time) is re-run on the in-sample
frame cut
  (a) at a random bar c with fill bar + 2 <= c <= exit bar - 1: the trade must exist with the same fill and initial
      stop and still be open at the end of the cut frame (closed there by 'time' or 'eod');
  (b) right after its exit bar (frame ends at exit bar + 1): same exit bar, exit price, reason and R;
  (c) H2 only: the hold decision recomputed on the frame that ends at the decision bar (the bar before the 15:55 NY
      clock bar), the trade simulated alone to the end of that frame: open at its close and ahead by >= 1 R0.

    python3 truncation.py <sym>      -> work/truncation_<sym>.json
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import synth as S  # noqa: E402
from goldlab.sim import simulate  # noqa: E402

N_ACT, N_RND = 15, 15


def pipeline(name, sym, f, variant):
    O = S.build_orders(name, sym, f)
    o, _ = S.make_variant(name, sym, f, O, False, variant)
    return simulate(f, o, sym=sym, costs=S.costs(sym, False), no_overlap=True), O


def bar_of(m1, ts):
    return int(np.searchsorted(m1.index.values, pd.DatetimeIndex([ts]).values.astype(m1.index.values.dtype)[0]))


def test_sleeve(name, sym, m1, rng):
    variant = S.CHANGE[(name, sym)]
    full = pd.read_parquet(os.path.join(S.WORK, f"{name}__{sym}__{variant}__fp.parquet"))
    full = full[(full.entry_time >= S.MAIN0)].reset_index(drop=True)
    if variant == "T1":
        act = full.hold_min > 6.5 * 60
    elif variant == "H2":
        act = full["ahead"].astype(bool)
    else:
        act = full.reason.isin(["stop", "trail"])
    ia = rng.choice(np.flatnonzero(act.to_numpy()), size=min(N_ACT, int(act.sum())), replace=False)
    if int((~act).sum()) > 0:
        ir = rng.choice(np.flatnonzero(~act.to_numpy()), size=min(N_RND, int((~act).sum())), replace=False)
    else:   # every trade is one where the change acts (donch4h_stop: all exits are stops or trails): more of them
        rest = np.setdiff1d(np.flatnonzero(act.to_numpy()), ia)
        ir = rng.choice(rest, size=min(N_RND, len(rest)), replace=False)
    res = {"variant": variant, "sampled_acting": int(len(ia)), "sampled_other": int(len(ir)),
           "a_tested": 0, "a_identical": 0, "b_tested": 0, "b_identical": 0, "c_tested": 0, "c_identical": 0,
           "mismatches": []}
    for k in np.r_[ia, ir]:
        tr = full.iloc[int(k)]
        fb = bar_of(m1, tr.entry_time)
        xet = tr.exit_time - pd.Timedelta(minutes=0 if tr.reason == "time" else 1)
        xb = bar_of(m1, xet)
        # (b) cut right after the exit bar
        f = m1.iloc[: xb + 2]
        t, _ = pipeline(name, sym, f, variant)
        m = t[(t.entry_time == tr.entry_time) & (t.side == tr.side)]
        res["b_tested"] += 1
        ok = len(m) == 1 and m.exit_time.iloc[0] == tr.exit_time and m.reason.iloc[0] == tr.reason \
            and abs(m.exit.iloc[0] - tr.exit) < 1e-9 and abs(m.R.iloc[0] - tr.R) < 1e-9
        res["b_identical"] += int(ok)
        if not ok:
            res["mismatches"].append({"test": "b", "entry_time": str(tr.entry_time), "found": len(m)})
        # (a) cut inside the trade
        if xb - fb >= 3:
            c = int(rng.integers(fb + 2, xb))
            f = m1.iloc[: c + 1]
            t, _ = pipeline(name, sym, f, variant)
            m = t[(t.entry_time == tr.entry_time) & (t.side == tr.side)]
            res["a_tested"] += 1
            ok = len(m) == 1 and abs(m.entry.iloc[0] - tr.entry) < 1e-9 and abs(m.stop.iloc[0] - tr.stop) < 1e-9 \
                and m.reason.iloc[0] in ("time", "eod") and bar_of(f, m.exit_time.iloc[0] - pd.Timedelta(minutes=0 if m.reason.iloc[0] == "time" else 1)) == c
            res["a_identical"] += int(ok)
            if not ok:
                res["mismatches"].append({"test": "a", "entry_time": str(tr.entry_time), "cut_bar": c, "found": len(m),
                                          "reason": (m.reason.iloc[0] if len(m) else None)})
        # (c) H2: decision at the bar before the clock bar, on the frame that ends there
        if variant == "H2":
            Ofull = S.build_orders(name, sym, m1)
            row = Ofull[(Ofull.entry_i == fb) & (Ofull.side == tr.side)]
            if len(row) == 1:
                d = int(row.exit_i.iloc[0]) - 1          # the rule's clock exit bar - 1
                if d > fb:
                    f = m1.iloc[: d + 1]
                    O = S.build_orders(name, sym, f)
                    r = O[(O.entry_i == fb) & (O.side == tr.side)].copy()
                    r["exit_i"] = -1
                    t1 = simulate(f, r, sym=sym, costs=S.costs(sym, False), no_overlap=False)
                    dec = False
                    if len(t1) == 1 and t1.reason.iloc[0] == "eod":
                        mark = f["bc"].to_numpy()[d] if tr.side > 0 else f["ac"].to_numpy()[d]
                        dec = bool(tr.side * (mark - t1.entry.iloc[0]) >= t1.risk.iloc[0])
                    res["c_tested"] += 1
                    ok = dec == bool(tr["ahead"])
                    res["c_identical"] += int(ok)
                    if not ok:
                        res["mismatches"].append({"test": "c", "entry_time": str(tr.entry_time), "full": bool(tr["ahead"]),
                                                  "cut": dec})
    return res


def main(sym):
    m1 = S.load_is(sym)
    rng = np.random.default_rng(20261112)
    out = {"written": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "sym": sym}
    for name in S.BY_SYM[sym]:
        if (name, sym) in S.CHANGE:
            t0 = time.time()
            r = test_sleeve(name, sym, m1, rng)
            out[f"{name}:{sym}"] = r
            print(name, sym, {k: v for k, v in r.items() if k != "mismatches"}, "mismatches", r["mismatches"][:5],
                  f"[{time.time() - t0:.0f}s]", flush=True)
    json.dump(out, open(os.path.join(S.WORK, f"truncation_{sym}.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main(sys.argv[1])
