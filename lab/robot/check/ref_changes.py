"""References of the three kept changes (SPEC 7): K1 on BKE, S0.75r on BKB, H2 on F1E, from the lab's OWN code.
Owner: step E (S0 wrote the first version). Called by check/ref_lab.py, one change per fresh process:
    python3 -I lab/robot/check/ref_lab.py --change K1 [--frame official|rebuilt --tag T]
and by step E's tests (check/test_changes.py), which give their own output folder (run_change's `out`).

Each change: the frame is read first (row filter ts < 2022-01-01 inside the read call); then
vhi_guard.open_run("2022-01-01", ...) (in sample: no access line; it installs the read guard); then
vhi_sleeves.run(spec, m1, "fp", "lab", every_signal=True, keep_signals=True) for the look spec's sleeve
  brk72_24h_wd__ethusd+K1          (its declared_T removed: the in-sample folds are fitted, not checked)
  brk72_24h_wd__btcusd+S0.75r
  F1_brk_ridge_filter__ethusd+H2
and, for the change's own orders and diagnostics, the same functions run() calls (vhi_sleeves.build_orders and the
registered change builder). Writes under <out>/changes/<id>/:
  trades.parquet        the changed chain (run()'s "main"), plus ea_oid
  base.parquet          K1: the chain without the skip
  every_signal.parquet  every order of the change taken alone
  rule_orders.parquet   the rule's own orders O (oid = row of O), with ea_oid and their entry and exit bar starts
  orders.parquet        the orders the change simulates (K1: the skipped and refused-alone signals removed; S0.75r:
                        the new stop distance; H2: the held orders' exit moved), with ea_oid and bar starts
  signals.parquet       K1: the signal table (t_dec, riskbp, refused, skip ...), with ea_oid
and returns the summary: the K1 folds' T(Y) with 17 significant digits and the InpK1T string of the folds that skip
the high side, the skipped ea_oids, the held order ids of H2 (lab oids and ea_oids), the refused counts.
ea_oid = the robot's order id: decision (UTC seconds) x 100 + sleeve id (SPEC 2.3, 2.4): BKB 3, BKE 4, F1E 6.
"""
import copy
import json
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROBOT = os.path.dirname(HERE)
LAB = os.path.dirname(ROBOT)
VHI = os.path.join(LAB, "r2", "tracks", "validation_hi")
CUT = pd.Timestamp("2022-01-01", tz="UTC")
CHANGES = {"K1": {"code": "BKE", "sid": 4, "key": "brk72_24h_wd__ethusd+K1"},
           "S0.75r": {"code": "BKB", "sid": 3, "key": "brk72_24h_wd__btcusd+S0.75r"},
           "H2": {"code": "F1E", "sid": 6, "key": "F1_brk_ridge_filter__ethusd+H2"}}


def look_sleeve(key):
    spec = json.load(open(os.path.join(VHI, "look_spec.json")))
    for s in spec["sleeves"]:
        if s["key"] == key:
            s = copy.deepcopy(s)
            if s.get("change", {}).get("kind") == "k1_riskbp":
                s["change"].pop("declared_T", None)          # in sample: the folds are fitted (SPEC 7)
            return s
    raise KeyError(key)


def read_frame(sym, kind, tag):
    if kind == "official":
        p = os.path.join(LAB, "data", "fp", f"{sym}_m1.parquet")
    else:
        p = os.path.join(HERE, "out", "frames", f"{sym}_{tag}.parquet")
    m1 = pd.read_parquet(p, filters=[("ts", "<", CUT)])
    assert len(m1) and m1.index.max() < CUT
    return m1


def g17(x):
    return "%.17g" % float(x)


def secs(ts):
    return pd.DatetimeIndex(ts).tz_convert("UTC").as_unit("s").asi8.astype(np.int64)


def dec_secs(o):
    """the decision of each order, UTC seconds: brk72 'dec_time', F1 'cid' (nanoseconds)"""
    if "dec_time" in o:
        return secs(o["dec_time"])
    if "cid" in o:
        return (o["cid"].to_numpy(np.int64) // 1_000_000_000).astype(np.int64)
    raise KeyError("no decision column")


def with_bars(o, m1, sid):
    """ea_oid and the start of the entry and exit bars (NaT beyond the frame)"""
    o = o.reset_index(drop=True).copy()
    n = len(m1)
    o["ea_oid"] = dec_secs(o) * 100 + sid
    ei = o["entry_i"].to_numpy(np.int64)
    o["entry_t"] = pd.DatetimeIndex(m1.index[np.clip(ei, 0, n - 1)]).where(ei < n)
    if "exit_i" in o:
        xi = o["exit_i"].to_numpy(np.int64)
        o["exit_t"] = pd.DatetimeIndex(m1.index[np.clip(xi, 0, n - 1)]).where((xi >= 0) & (xi < n))
    for c in o.columns:
        if o[c].dtype == object:
            o[c] = o[c].astype(str)
    return o


def run_change(cid, kind, tag, out):
    t0 = time.time()
    ch = CHANGES[cid]
    spec = look_sleeve(ch["key"])
    m1 = read_frame(spec["sym"], kind, tag)                   # the frame first, then the guard (SPEC 7)
    for p in (LAB, VHI):
        if p not in sys.path:
            sys.path.insert(0, p)
    import vhi_guard as G
    G.open_run("2022-01-01", f"robot_ref_{cid}")
    import vhi_sleeves as S
    res_out, info = S.run(spec, m1, "fp", "lab", every_signal=True, keep_signals=True)
    mk = S.mode_frame(m1, "fp")
    O = S.build_orders(spec["rule"], mk)
    o, extra = S.CHANGES[spec["change"]["kind"]](spec, mk, O, "fp", {"m1": m1})
    d = os.path.join(out, "changes", cid)
    os.makedirs(d, exist_ok=True)
    sid = ch["sid"]
    ea_of = dict(zip(O["oid"].to_numpy(np.int64).tolist(), (dec_secs(O) * 100 + sid).tolist()))

    def save_trades(t, name):
        t = t.copy()
        t["ea_oid"] = [ea_of[int(x)] for x in t["oid"].to_numpy()]
        t.to_parquet(os.path.join(d, name))

    save_trades(res_out["main"], "trades.parquet")
    if "base" in res_out:
        save_trades(res_out["base"], "base.parquet")
    if "every_signal" in res_out:
        save_trades(res_out["every_signal"], "every_signal.parquet")
    with_bars(O, mk, sid).to_parquet(os.path.join(d, "rule_orders.parquet"))
    with_bars(o, mk, sid).to_parquet(os.path.join(d, "orders.parquet"))
    t = res_out["main"]
    res = {"change": cid, "code": ch["code"], "key": ch["key"], "frame": kind, "tag": tag, "bars": int(len(m1)),
           "first_bar": str(m1.index[0]), "last_bar": str(m1.index[-1]), "orders_rule": int(len(O)),
           "orders_change": int(len(o)), "trades": int(len(t)), "R_sum": float(t.R.sum()) if len(t) else 0.0,
           "refused_3spreads": int(info.get("main_refused_3spreads", 0)), "info": info}
    if cid == "K1":
        sig = res_out.get("signals")
        if sig is not None:
            sig = sig.copy()
            sig["ea_oid"] = secs(sig["t_dec"]) * 100 + sid
            sig.to_parquet(os.path.join(d, "signals.parquet"))
            res["skipped_ea_oids"] = sorted(int(x) for x in sig.loc[sig["skip"], "ea_oid"])
        folds = info["change_diag"]["folds_full"]
        res["folds"] = {str(y): {"q_hi": g17(f["q_hi"]), "q_lo": g17(f["q_lo"]), "skip": f["skip"], "n_train": f.get("n_train"),
                                 "n_skipped": f.get("n_skipped")} for y, f in folds.items()}
        res["k1t_input"] = ";".join(f"{y}:{g17(f['q_hi'])}" for y, f in sorted(folds.items()) if f["skip"] == "hi")
        res["folds_skipping_low_side"] = sorted(int(y) for y, f in folds.items() if f["skip"] == "lo")
        res["skipped"] = int(info["change_diag"]["skipped"])
        res["refused_alone"] = int(info["change_diag"]["refused_alone"])
        res["base_trades"] = int(len(res_out["base"]))
        res["note"] = f"K1 skipped {res['skipped']} signals; InpK1T {res['k1t_input']}"
    elif cid == "H2":
        held = sorted(int(x) for x in extra.get("ahead_oids", set()))
        res["held_oids"] = held
        res["held_ea_oids"] = sorted(ea_of[x] for x in held)
        tro = set(int(x) for x in t["oid"].to_numpy())
        res["held_trades_ea_oids"] = sorted(ea_of[x] for x in held if x in tro)
        res["held_trades"] = int(info["change_diag"].get("extended_trades", 0))
        res["refused_orders"] = int(extra.get("diag", {}).get("refused_orders", 0))
        res["note"] = f"H2 held {res['held_trades']} trades ({len(held)} orders ahead at the clock exit)"
    else:
        res["refused_orders"] = int(extra.get("diag", {}).get("refused_orders", 0))
        res["note"] = f"S0.75r refused {res['refused_orders']} orders"
    res["sec"] = round(time.time() - t0, 1)
    return res
