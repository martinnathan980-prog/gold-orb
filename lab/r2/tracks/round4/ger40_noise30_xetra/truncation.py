"""Causality proof (task rule 3, declared R20): truncation test on 70 decisions of configuration 1.  IN SAMPLE ONLY.

40 entries and 30 check exits are drawn (seed 7) among the 2014-2021 decisions of configuration 1.  For a decision at
check time T, the in-sample slice is cut at T (every bar starting at or after T is removed: the frame then holds only
bars that are closed at T), and 3 provisional bars are appended at the real start time of the next bar and +1, +2
minutes, in three variants: flat at the last real close, the same +3 %, the same -3 %.  The orders are rebuilt on each
cut frame.  The decision must be identical in every variant:
  entry: an order with the same decision time, entry bar, side and stop;
  check exit: the open order with the same entry gets the same exit bar at the same decision time
(an exit decided on the close of the bar ending at T is executed at the open of the next bar, the first bar starting at
or after T), and the whole set of orders decided at or before T (entry bar, side, stop; exit bar when the exit was
decided at or before T) must equal the full frame's.  Output: results/r2/round4/ger40_noise30_xetra/truncation.json

    PYTHONDONTWRITEBYTECODE=1 python3 truncation.py
"""
import json
import os
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import xetra as X  # noqa: E402

VARIANTS = {"flat": 1.0, "up3pct": 1.03, "down3pct": 0.97}


def provisional(m1, cut, mult, k=3):
    head = m1.iloc[:cut]
    t_next = m1.index[cut] if cut < len(m1) else m1.index[-1] + pd.Timedelta(minutes=1)
    last = head.iloc[-1]
    b, a = float(last["bc"]) * mult, float(last["ac"]) * mult
    idx = pd.DatetimeIndex([t_next + pd.Timedelta(minutes=j) for j in range(k)], name=m1.index.name)
    prov = pd.DataFrame({c: [b if c.startswith("b") else a] * k for c in m1.columns}, index=idx).astype("float64")
    return pd.concat([head, prov])


def decided_set(o, T, with_exit):
    s = o[o["t_in"] <= T]
    ent = set(zip(s["t_in"], s["entry_i"], s["side"], s["stop"]))
    ex = set(zip(s.loc[(s["t_out"] >= 0) & (s["t_out"] <= T), "t_in"], s.loc[(s["t_out"] >= 0) & (s["t_out"] <= T), "exit_i"],
                 s.loc[(s["t_out"] >= 0) & (s["t_out"] <= T), "t_out"])) if with_exit else set()
    return ent, ex


def main(n_entries=40, n_exits=30, seed=7):
    t0 = time.time()
    m1 = X.load_is()
    o = X.make_orders(m1, **X.MAIN)
    iv = m1.index.values.astype("datetime64[ns]").astype("int64")
    start = pd.Timestamp(X.TRADE_START, tz="UTC").value
    ent = o[o["t_in"] >= start]
    exi = o[(o["t_out"] >= start)]
    rng = np.random.default_rng(seed)
    pick_e = ent.iloc[np.sort(rng.choice(len(ent), n_entries, replace=False))]
    pick_x = exi.iloc[np.sort(rng.choice(len(exi), n_exits, replace=False))]
    cases = [("entry", r) for _, r in pick_e.iterrows()] + [("exit", r) for _, r in pick_x.iterrows()]
    res = []
    for kind, r in cases:
        T = int(r["t_in"] if kind == "entry" else r["t_out"])
        cut = int(np.searchsorted(iv, T, side="left"))
        full_ent, full_ex = decided_set(o, T, True)
        row = {"kind": kind, "T_berlin": str(pd.Timestamp(T, tz="UTC").tz_convert(X.BER)),
               "cut_after_bar": str(m1.index[cut - 1]), "variants": {}}
        if kind == "entry":
            row.update(entry_bar=str(m1.index[int(r["entry_i"])]), side=int(r["side"]), stop=float(r["stop"]),
                       reversal=bool(int(r["entry_i"]) == cut + 1))
        else:
            row.update(exit_bar=str(m1.index[int(r["exit_i"])]), side=int(r["side"]))
        for vn, mult in VARIANTS.items():
            mc = provisional(m1, cut, mult)
            oc = X.make_orders(mc, **X.MAIN)
            if kind == "entry":
                hit = oc[(oc["t_in"] == T) & (oc["entry_i"] == r["entry_i"]) & (oc["side"] == r["side"])
                         & (oc["stop"] == r["stop"])]
                same_decision = bool(len(hit) == 1)
            else:
                hit = oc[(oc["t_in"] == r["t_in"]) & (oc["entry_i"] == r["entry_i"])]
                same_decision = bool(len(hit) == 1 and int(hit["exit_i"].iloc[0]) == int(r["exit_i"])
                                     and int(hit["t_out"].iloc[0]) == T)
            c_ent, c_ex = decided_set(oc, T, True)
            row["variants"][vn] = {"same_decision": same_decision, "same_set_decided_by_T": bool(c_ent == full_ent),
                                   "same_exits_decided_by_T": bool(c_ex == full_ex), "orders_decided_by_T": len(c_ent)}
        row["identical"] = all(v["same_decision"] and v["same_set_decided_by_T"] and v["same_exits_decided_by_T"]
                               for v in row["variants"].values())
        res.append(row)
    # every order of the full frame: execution bar starts at or after its decision time; signal price from a bar that
    # started before it (checked on the grid: P at T is the close of the last bar starting before T)
    exec_ok = bool((iv[o["entry_i"].to_numpy()] >= o["t_in"].to_numpy()).all())
    ex_rows = o[o["t_out"] >= 0]
    exit_ok = bool((iv[ex_rows["exit_i"].to_numpy()] >= ex_rows["t_out"].to_numpy()).all())
    out = {"configuration": 1, "decisions_tested": len(res), "entries": n_entries, "check_exits": n_exits, "seed": seed,
           "variants": list(VARIANTS), "identical": int(sum(x["identical"] for x in res)),
           "reversal_entries_in_sample": int(sum(1 for x in res if x.get("reversal"))),
           "all_orders_execute_at_or_after_decision": exec_ok, "all_check_exits_execute_at_or_after_decision": exit_ok,
           "sec": round(time.time() - t0, 1), "cases": res}
    with open(os.path.join(X.RES, "truncation.json"), "w") as f:
        json.dump(out, f, indent=1)
    print({k: v for k, v in out.items() if k != "cases"})
    bad = [x for x in res if not x["identical"]]
    print("not identical:", len(bad), bad[:3])


if __name__ == "__main__":
    main()
