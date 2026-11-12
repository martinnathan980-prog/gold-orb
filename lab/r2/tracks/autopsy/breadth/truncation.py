"""Causality proof for each qualifying pair (task rule 3): the decision of a trade is identical when the frame is cut
right after its decision bar.

    PYTHONDONTWRITEBYTECODE=1 python3 truncation.py rule:sym [rule:sym ...]      (default: the qualifiers of analysis.json)

For up to 40 trades of the window (fixed seed), the in-sample frame is cut:
  * market and limit entries (noise30, ocm4, brk72_24h_wd, F1, nq_btc_follow, GOLD_FRI_PM): right after the decision
    bar, i.e. every bar from the order's activation bar on is removed;
  * stop entries (donch4h_stop, orb_asia_2d_buf10): right after the touch bar (the order row only exists once touched);
then 3 flat provisional bars (prices = last real close, stamped at the real next bar's time and +1, +2 minutes) are
appended, because the frozen make_orders functions only emit an order once its entry bar and one more bar exist (lab
maps).  nq_btc_follow also gets its us100 leader cut at the same instant.  The order is rebuilt and must be identical
(entry time, side, etype, stop or stop distance, level, trail).  GOLD_FRI_PM pairs also get the early-close check: every
Friday order of the cut frames versus the full frame (the lab's filter drops a day with no quote after 16:45 New York,
which is only known later).
Output: results/r2/autopsy/breadth/truncation.json
"""
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common as C  # noqa: E402

FIELDS = ["side", "etype", "stop", "stop_dist", "level", "trail"]


def provisional(m1, cut, k=3):
    """Frame of the bars before `cut` plus k flat bars stamped at the real time of bar `cut` and +1, +2 minutes."""
    head = m1.iloc[:cut]
    t_next = m1.index[cut] if cut < len(m1) else m1.index[-1] + pd.Timedelta(minutes=1)
    last = head.iloc[-1]
    px = {c: last["bc"] if c.startswith("b") else last["ac"] for c in m1.columns}
    idx = pd.DatetimeIndex([t_next + pd.Timedelta(minutes=j) for j in range(k)], name=m1.index.name)
    prov = pd.DataFrame({c: [px[c]] * k for c in m1.columns}, index=idx).astype("float64")
    return pd.concat([head, prov])


def same(a, b):
    for f in FIELDS:
        va, vb = a.get(f, np.nan), b.get(f, np.nan)
        try:
            va, vb = float(va), float(vb)
        except (TypeError, ValueError):
            if va != vb:
                return False, f
            continue
        if np.isnan(va) and np.isnan(vb):
            continue
        if np.isnan(va) != np.isnan(vb) or not np.isclose(va, vb, rtol=1e-9, atol=1e-12):
            return False, f
    return True, None


def test_pair(rule, sym, k=40, seed=7):
    m1 = C.load_is(sym)
    leader = C.leader_series(C.load_is("us100")) if rule == "nq_btc_follow" else None
    t, o, info = C.run_rule(rule, sym, m1, "fp", leader=leader)
    tw = C.window(t)
    rng = np.random.default_rng(seed)
    pick = np.sort(rng.choice(len(tw), size=min(k, len(tw)), replace=False))
    idx = m1.index
    res = []
    for j in pick:
        tr = tw.iloc[j]
        row = o.iloc[int(tr["oid"])]
        e = int(row["entry_i"])
        if rule == "donch4h_stop":
            cut = int(row["trig_i"]) + 1
        elif rule == "orb_asia_2d_buf10":
            cut = e + 1
        else:
            cut = e
        mc = provisional(m1, cut)
        lead_c = leader[leader.index < idx[cut]] if leader is not None else None
        oc = C.build_orders(rule, mc, leader=lead_c)
        t_entry = idx[e]
        hit = oc[mc.index[oc["entry_i"].clip(upper=len(mc) - 1).to_numpy()] == t_entry] if len(oc) else oc
        if not len(hit):
            res.append({"entry_time": str(t_entry), "found": False, "identical": False, "field": "order missing"})
            continue
        ok, fld = same(hit.iloc[0].to_dict(), row.to_dict())
        res.append({"entry_time": str(t_entry), "found": True, "identical": bool(ok), "field": fld,
                    "cut_after": str(idx[cut - 1])})
    out = {"rule": rule, "instrument": sym, "tested": len(res), "identical": int(sum(r["identical"] for r in res)),
           "missing": int(sum(not r["found"] for r in res)), "cases": res}
    if rule == "GOLD_FRI_PM":
        out["early_close_check"] = friday_check(m1, o)
    C.clear_rule_caches()
    return out


def friday_check(m1, o_full):
    """Every Friday 13:30 New York of the window: does the cut frame (cut at the 13:30 bar) emit an order the full frame
    does not have (or the reverse)?"""
    idx = m1.index
    ny = idx.tz_convert(C.NY)
    sel = (idx >= C.COMMON_START) & (ny.dayofweek == 4) & (ny.hour == 13) & (ny.minute >= 30) & (ny.minute <= 35)
    firsts = pd.Series(np.flatnonzero(sel)).groupby(ny[sel].date).first().to_numpy()
    full_times = set(idx[o_full["entry_i"].to_numpy()])
    extra, missing = [], []
    for e in firsts:
        mc = provisional(m1, int(e))
        oc = C.build_orders("GOLD_FRI_PM", mc)
        has = bool(len(oc)) and (mc.index[oc["entry_i"].clip(upper=len(mc) - 1).to_numpy()] == idx[e]).any()
        if has and idx[e] not in full_times:
            extra.append(str(idx[e]))
        if not has and idx[e] in full_times:
            missing.append(str(idx[e]))
    return {"fridays": int(len(firsts)), "order_in_cut_not_in_full": extra, "order_in_full_not_in_cut": missing}


def main(args):
    if args:
        pairs = [a.split(":") for a in args]
    else:
        an = json.load(open(os.path.join(C.RES, "analysis.json")))
        pairs = [(r["rule"], r["instrument"]) for r in an["ranking"]]
    path = os.path.join(C.RES, "truncation.json")
    allres = json.load(open(path)) if os.path.exists(path) else {}
    for rule, sym in pairs:
        r = test_pair(rule, sym)
        allres[f"{rule}:{sym}"] = r
        C.jdump(allres, path)
        print(rule, sym, "tested", r["tested"], "identical", r["identical"], "missing", r["missing"],
              r.get("early_close_check", ""), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
