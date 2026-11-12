"""Addendum H, lens `entry` -- causality (criterion f), FP frames, in sample.

Decision layer, every cell, every signal: each entry decision of the variant -- the limit level (placed at the open of
its placement bar), the limit fill bar, 'no fill in the window' (which triggers the market fallback), the
confirmation bar or block, the cancellation on the rule's stop price -- is recomputed by the same functions on the
price arrays CUT RIGHT AFTER ITS DECISION BAR (for a 5-minute block, with the clock at the block's end), and must be
identical to the decision made on the whole in-sample frame.
Rule layer, a sample of 25 signals per sleeve: the rule's own order (side, stop or stop distance, level, touch bar) is
rebuilt by the frozen make_orders on the in-sample frame cut right after the variant's placement bar plus three flat
provisional bars (the lab rules need their entry bar and one more bar to emit an order; the brain maps show that the
provisional bars' values do not matter), and must equal the order of the whole frame.
Writes results/r2/autopsy/entry/truncation.json.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (A_COLS_LEADER, MIN_NS, ORDER, RES, arrays, build_orders, costs, jdump, key, lab_orders,  # noqa
                    load_is, np, pd)
from variants import BIG, conf1, conf_block, lim_touch, stop_touch, build, signal_table  # noqa: E402

DECL = json.load(open(os.path.join(RES, "declared.json")))
COLS = ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac", "ns")


def cut(A, end):
    """Arrays of the bars 0..end (the frame cut right after bar `end`)."""
    return {k: A[k][:end + 1] for k in COLS}


def p0_of(name, A, side, a_bar, c):
    """The reference price recomputed from the cut arrays (market rules only)."""
    sm = c.slip_mkt_bps * 1e-4
    return A["ao"][a_bar] * (1 + sm) if side > 0 else A["bo"][a_bar] * (1 - sm)


def check_cell(name, v, mode, S, lo, A, c):
    legs, hold, info = build(name, v, mode, S, lo, A, c)
    fam = v["family"]
    side = S.side.to_numpy(np.int64)
    a = info["a"]
    w_end = info["w_end"]
    valid = info["valid"]
    n_dec = 0
    bad = []
    mo_full = (A["bo"] + A["ao"]) / 2
    mc_full = (A["bc"] + A["ac"]) / 2
    for s in np.where(valid)[0]:
        if fam in ("LIM", "HALF") and name != "GOLD_FRI_PM":
            T = cut(A, a[s])
            p0 = p0_of(name, T, side[s], a[s], c)
            lvl_t = p0 - side[s] * v["k"] * S.D.iat[s]
            n_dec += 1
            if lvl_t != info["level"][s]:
                bad.append((int(s), "level"))
        if fam in ("LIM", "HALF", "RT", "HALFRT"):
            j = info["fill_bar"][s]
            end = j if j >= 0 else w_end[s]
            T = cut(A, end)
            jt = lim_touch(T["al"], T["bh"], side[s], info["level"][s], a[s], w_end[s])
            n_dec += 1
            if jt != j:
                bad.append((int(s), "fill"))
        if fam == "CONF":
            S0 = S.S0.iat[s]
            vb = info["stop_bar"][s]
            cb = info["conf_bar"][s]
            if v["tf_min"] == 1:
                end = cb if cb >= 0 else w_end[s]
                T = cut(A, end)
                mo, mc = (T["bo"] + T["ao"]) / 2, (T["bc"] + T["ac"]) / 2
                ct = conf1(mo, mc, side[s], a[s], w_end[s])
                n_dec += 1
                if ct != cb:
                    bad.append((int(s), "conf1"))
            else:
                ns = A["ns"]
                t0 = ns[a[s]]
                n = len(ns)
                exit_c = S.exit_c.iat[s]
                t_end = min(info["t_end"][s], ns[min(max(exit_c - 1, 0), n - 1)] + MIN_NS)
                if cb >= 0:
                    T = cut(A, cb)
                    t_now = info["block_end"][s]
                else:
                    T = cut(A, w_end[s])
                    t_now = BIG
                mo, mc = (T["bo"] + T["ao"]) / 2, (T["bc"] + T["ac"]) / 2
                f5, k5, be5 = conf_block(T["ns"], mo, mc, side[s], a[s], t0, np.int64(5) * MIN_NS, t_end, t_now)
                n_dec += 1
                if k5 != cb or (cb >= 0 and be5 != info["block_end"][s]):
                    bad.append((int(s), "conf5"))
            end = vb if vb >= 0 else w_end[s]
            T = cut(A, end)
            vt = stop_touch(T["bl"], T["ah"], side[s], S0, a[s], w_end[s])
            n_dec += 1
            if vt != vb:
                bad.append((int(s), "stop_touch"))
    del mo_full, mc_full
    return {"decisions_checked": int(n_dec), "mismatches": len(bad), "examples": bad[:5],
            "identical": len(bad) == 0}


def provisional(m1, end, k=3):
    """The frame cut right after bar `end`, plus k flat provisional bars (all prices = the last closes)."""
    f = m1.iloc[:end + 1]
    last = f.iloc[-1]
    t = f.index[-1]
    idx = pd.DatetimeIndex([t + pd.Timedelta(minutes=i + 1) for i in range(k)])
    rows = pd.DataFrame({c: [last["bc"] if c[0] == "b" else last["ac"]] * k for c in f.columns}, index=idx)
    rows.index.name = f.index.name
    return pd.concat([f, rows])


def rule_layer(name, sym, m1, o, S, leader, n_sample=25, seed=11):
    rng = np.random.default_rng(seed)
    n = len(m1)
    rt = name in ("donch4h_stop", "orb_asia_2d_buf10")
    place = (S.trig.to_numpy() + 1) if rt else S.act.to_numpy()
    cand = np.where(S.ok.to_numpy() & (place < n - 5))[0]
    pick = np.sort(rng.choice(cand, size=min(n_sample, len(cand)), replace=False))
    fields = [c for c in ("side", "stop", "stop_dist", "level", "trig_i") if c in o]
    bad = []
    for s in pick:
        end = int(place[s])
        F = provisional(m1, end)
        Ld = None
        if leader is not None:
            Ld = leader[leader.index <= m1.index[end]]
        ot = build_orders(name, sym, F, Ld)
        ns_full = m1.index[int(o.entry_i.iat[s])]
        ent_t = F.index[np.minimum(ot.entry_i.to_numpy(), len(F) - 1)]
        m = np.where(ent_t == ns_full)[0]
        if len(m) != 1:
            bad.append((int(s), "order missing" if len(m) == 0 else "several"))
            continue
        r = ot.iloc[m[0]]
        for fdx in fields:
            x, y = o[fdx].iat[s], r[fdx]
            if fdx == "trig_i":
                x, y = m1.index[int(x)], F.index[int(y)]
                if x != y:
                    bad.append((int(s), fdx))
            elif not ((pd.isna(x) and pd.isna(y)) or x == y):
                bad.append((int(s), fdx))
    return {"signals_checked": int(len(pick)), "fields": fields, "mismatches": len(bad), "examples": bad[:5],
            "identical": len(bad) == 0}


def main():
    t00 = time.time()
    out = {"what": __doc__.strip().splitlines()[0], "cells": {}, "rule_layer": {}}
    cur = None
    m1 = A = leader = None
    for name, sym in ORDER:
        t0 = time.time()
        if sym != cur:
            m1 = A = leader = None
            m1 = load_is(sym)
            A = arrays(m1)
            leader = load_is("us100", cols=A_COLS_LEADER) if sym == "btcusd" else None
            cur = sym
        k = key(name, sym)
        c = costs(sym, False)
        o = build_orders(name, sym, m1, leader)
        lo = lab_orders(o)
        S = signal_table(name, sym, o, lo, A, c)
        for v in DECL["sleeves"][k]["variants"]:
            for mode in v["stop_modes"]:
                out["cells"][f"{k}|{v['id']}|{mode}"] = r = check_cell(name, v, mode, S, lo, A, c)
                if not r["identical"]:
                    print("  MISMATCH", k, v["id"], mode, r, flush=True)
        out["rule_layer"][k] = rl = rule_layer(name, sym, m1, o, S, leader)
        nd = sum(out["cells"][f"{k}|{v['id']}|{m}"]["decisions_checked"] for v in DECL["sleeves"][k]["variants"]
                 for m in v["stop_modes"])
        print(f"{k:28s} decisions {nd:7d} all identical "
              f"{all(out['cells'][f'{k}|{v[chr(105) + chr(100)]}|{m}']['identical'] for v in DECL['sleeves'][k]['variants'] for m in v['stop_modes'])}"
              f" | rule layer {rl['signals_checked']} signals, mismatches {rl['mismatches']} {rl['examples']} "
              f"[{time.time() - t0:.0f}s]", flush=True)
    out["all_identical"] = all(r["identical"] for r in out["cells"].values())
    out["rule_layer_all_identical"] = all(r["identical"] for r in out["rule_layer"].values())
    jdump(out, os.path.join(RES, "truncation.json"))
    print(f"total {time.time() - t00:.0f}s; decision layer all identical {out['all_identical']}; rule layer "
          f"{out['rule_layer_all_identical']}", flush=True)


if __name__ == "__main__":
    main()
