"""Criterion (f) -- causality by truncation.

Test 1 (every declared checkpoint of every sleeve, every filled order of the every-signal run, FP frame):
the decision inputs (is the trade still open at the close of the decision bar d, and its state u there) are
recomputed from a frame that ENDS at bar d (bars from the order's activation bar to d; the order row as given;
no time exit inside the cut frame, the rule's own scheduled exit bar being a clock time fixed at entry) by the lab
engine, and compared with the full-frame values (exact equality of the open flag, of u, of the fill and the stop).
Every EC / NP / HC rule of the declaration is a threshold on (open, u), so equal inputs = equal decisions.

Test 2 (the variants that pass criteria a-e): for a sample of trades (all the fired ones up to 40, plus up to 40
not fired), the whole chain is rebuilt on the in-sample frame cut right after the decision bar (start of the frame
unchanged): the frozen rule's make_orders on the cut frame (leader cut too for nq_btc_follow), the same order found
again, simulated on the cut frame, decision recomputed -> compared with the full-frame decision.
Output: results/r2/autopsy/path/truncation.json
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from s2_rules import Sleeve  # noqa: E402

ORDER_COLS = ["entry_i", "side", "etype", "level", "expiry_i", "stop", "stop_dist", "target", "target_dist",
              "exit_i", "trail", "be"]


def order_row(o, k):
    r = {}
    for c in ORDER_COLS:
        if c in o.columns:
            r[c] = o.at[k, c]
    return r


def trunc_state(m1, sym, row, e0, d):
    """(open, u, fill, stop) of one order from the frame m1.iloc[e0:d+1] only."""
    fr = m1.iloc[e0:d + 1]
    r = dict(row)
    r["entry_i"] = 0
    if "expiry_i" in r and r.get("etype", 0) in (1, 2):
        r["expiry_i"] = int(min(r["expiry_i"], d) - e0)
    r["exit_i"] = -1
    t = C.sim(fr, pd.DataFrame([r]), sym, no_overlap=False)
    if len(t) == 0:
        return False, np.nan, np.nan, np.nan
    tr = t.iloc[0]
    is_open = tr.reason == "eod"
    s = int(tr.side)
    q = fr["bc"].iat[-1] if s > 0 else fr["ac"].iat[-1]
    u = s * (q - tr.entry) / abs(tr.entry - tr.stop)
    return bool(is_open), float(u), float(tr.entry), float(tr.stop)


def test1(S, cks):
    out = {}
    o = S.o
    rows = S.ta.index.to_numpy()
    for ckname, ck in cks.items():
        t0 = time.time()
        dd, is_open, u = S.decision(ck)
        ex_sched = o.loc[rows, "exit_i"].to_numpy(np.int64)
        stops = S.ta.stop.to_numpy()
        n = mism = 0
        bad = []
        for j, k in enumerate(rows):
            e0 = int(o.at[k, "entry_i"])
            d = int(dd[j])
            if d + 1 >= len(S.ns):
                continue
            op, ut, ft, st = trunc_state(S.m1, S.sym, order_row(o, k), e0, d)
            # the rule's own scheduled time exit at or before bar d closes the trade by the clock
            op = op and not (0 <= ex_sched[j] <= d)
            same = (op == bool(is_open[j])) and (not op or (ut == u[j] and ft == S.entry[j]
                                                            and st == stops[j]))
            n += 1
            if not same:
                mism += 1
                if len(bad) < 10:
                    bad.append({"order_row": int(k), "d": d, "open_full": bool(is_open[j]), "open_cut": op,
                                "u_full": float(u[j]), "u_cut": ut})
        out[ckname] = {"orders_tested": n, "identical": n - mism, "mismatches": mism, "examples": bad,
                       "seconds": round(time.time() - t0, 1)}
        print(f"   {S.name}:{S.sym} {ckname:5s} tested {n:5d} mismatches {mism} [{time.time() - t0:.0f}s]", flush=True)
    return out


def test2(name, sym, m1, leader, S, v, rng):
    """Full chain on the in-sample frame cut right after the decision bar."""
    dd, is_open, u = S.decision(v["ck"])
    if v["rule"] == "EC":
        fire = is_open & (u <= -v["x"])
    elif v["rule"] == "NP":
        fire = is_open & (u < v["y"])
    else:
        fire = is_open & (u <= 0)
    rows = S.ta.index.to_numpy()
    in_win = (S.ta.entry_time >= C.COMMON_START).to_numpy()
    fired = np.flatnonzero(fire & in_win)
    not_fired = np.flatnonzero(is_open & ~fire & in_win)
    pick = np.r_[rng.choice(fired, min(40, len(fired)), replace=False),
                 rng.choice(not_fired, min(40, len(not_fired)), replace=False)].astype(int)
    res = []
    ns = S.ns
    for j in pick:
        k = rows[j]
        d = int(dd[j])
        cut = m1.iloc[:d + 1]
        lead = None
        if leader is not None:
            lead = leader[leader.index <= m1.index[d]]
        oc = C.build_orders(name, sym, cut, lead)
        e0 = int(S.o.at[k, "entry_i"])
        same_o = oc[(oc.entry_i == e0) & (oc.side == int(S.o.at[k, "side"]))]
        found = len(same_o) == 1
        dec_cut = None
        if found:
            r = order_row(oc, same_o.index[0])
            op, ut, ft, st = trunc_state(cut, sym, r, e0, d)
            op = op and not (0 <= int(S.o.at[k, "exit_i"]) <= d)
            if v["rule"] == "EC":
                dec_cut = op and ut <= -v["x"]
            elif v["rule"] == "NP":
                dec_cut = op and ut < v["y"]
            else:
                dec_cut = op and ut <= 0
        res.append({"order_row": int(k), "entry_time": str(S.ta.entry_time.iloc[j]), "decision_bar_time": str(m1.index[d]),
                    "fired_full": bool(fire[j]), "order_found_in_cut_frame": found,
                    "fired_cut": None if dec_cut is None else bool(dec_cut),
                    "identical": found and bool(dec_cut) == bool(fire[j])})
    n_id = sum(r["identical"] for r in res)
    return {"variant": v["id"], "trades_tested": len(res), "identical": n_id, "fired_tested": int(min(40, len(fired))),
            "not_fired_tested": int(min(40, len(not_fired))), "rows": res}


def main():
    dec = json.load(open(os.path.join(C.RES, "declared.json")))
    crit = pd.read_csv(os.path.join(C.RES, "criteria.csv"))
    passing = set(crit.loc[crit.pass_a_to_e, "id"])
    cks_by = {}
    for v in dec["variants"]:
        cks_by.setdefault(v["sleeve"], {})[v["checkpoint"]] = v["ck"]
    out = {"test1": {}, "test2": {}}
    rng = np.random.default_rng(20261112)
    cur = None
    m1 = leader = None
    for name, sym in C.ORDER:
        sl = f"{name}:{sym}"
        if sym != cur:
            m1 = None
            m1 = C.load_is(sym)
            leader = C.load_is("us100", cols=["bo", "ao", "bc", "ac"]) if sym == "btcusd" else None
            cur = sym
        S = Sleeve(name, sym, m1, False, leader)
        out["test1"][sl] = test1(S, cks_by[sl])
        for v in dec["variants"]:
            if v["sleeve"] == sl and v["id"] in passing:
                t0 = time.time()
                r = test2(name, sym, m1, leader, S, v, rng)
                out["test2"][v["id"]] = r
                print(f"   test2 {v['id']}: {r['identical']}/{r['trades_tested']} identical [{time.time() - t0:.0f}s]",
                      flush=True)
        C.jdump(out, os.path.join(C.RES, "truncation.json"))


if __name__ == "__main__":
    main()
