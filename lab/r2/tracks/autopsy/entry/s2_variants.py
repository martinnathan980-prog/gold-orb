"""Addendum H, lens `entry`, part 2 -- the declared variants (results/r2/autopsy/entry/declared.json), every cell
(variant x stop mode) in FP costs and in x1.5 costs, in sample only.  One line per cell in trials.jsonl.

Per cell and cost mode: statistics of the sleeve on the common window (and before it), and the filled / missed
split: among the signals the variant's one-position chain takes, the share whose new entry is filled, the R of the
filled ones, and for filled and missed signals alike the R the rule's own entry would have made on them (each
signal's original order simulated alone).  The baseline of each cost mode is the rule itself through the same path.
"""
import datetime as dt
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (A_COLS_LEADER, COMMON_START, ORDER, RES, arrays, build_orders, costs, frame_for, jdump,  # noqa
                    jline, key, lab_orders, load_is, np, pd, signal_trades, sim_legs, stats, window)
from variants import build, signal_table  # noqa: E402

DECL = json.load(open(os.path.join(RES, "declared.json")))
CELLS_DIR = os.path.join(RES, "cells")
os.makedirs(CELLS_DIR, exist_ok=True)


def base_run(fr, A, o, lo, sym, stress):
    legs = lo.copy()
    legs["sig"] = np.arange(len(lo), dtype=np.int64)
    legs["leg"] = 0
    legs["w"] = 1.0
    res = sim_legs(fr, A, legs, sym, stress)
    sigs = pd.DataFrame({"act": lo.entry_i.to_numpy(np.int64), "hold": np.full(len(lo), -1, np.int64),
                         "side": lo.side.to_numpy(np.int64)}, index=legs.sig.to_numpy())
    tr, sg = signal_trades(sigs, legs, res, len(A["ns"]))
    return tr, sg, res


def summarise(tr):
    t = tr[~tr.censored]
    return {"common": stats(window(t, "common")), "pre": stats(window(t, "pre"), years=None),
            "n_censored": int(tr.censored.sum())}


def fill_split(S, sg, legs, res, base_res, A, tr):
    """Filled / missed split on the signals taken by the chain whose activation is in the common window."""
    ns = A["ns"]
    act_t = ns[np.minimum(S.act.to_numpy(np.int64), len(ns) - 1)]
    in_common = act_t >= COMMON_START.value
    ok = (res.filled & ~res.refused).to_numpy()
    lg = legs.leg.to_numpy()
    sig = legs.sig.to_numpy()
    pull = np.zeros(len(S), bool)               # the new entry (limit / retest / confirmation entry) was filled
    fall = np.zeros(len(S), bool)               # market fallback taken
    pull[sig[(lg == 1) & ok]] = True
    fall[sig[(lg == 2) & ok]] = True
    taken = sg.taken.to_numpy() & in_common
    bR = base_res.R.to_numpy(float)
    bF = (base_res.filled & ~base_res.refused).to_numpy()
    trR = pd.Series(tr[~tr.censored].R)
    vR = trR.reindex(np.arange(len(S))).to_numpy()
    f_ = taken & pull
    m_ = taken & ~pull
    m_b = m_ & bF
    out = {"n_signals_taken": int(taken.sum()), "n_new_entry_filled": int(f_.sum()),
           "share_filled": round(float(f_.sum() / taken.sum()), 4) if taken.sum() else None,
           "variant_meanR_filled": round(float(np.nanmean(vR[f_])), 4) if f_.sum() else None,
           "variant_totalR_filled": round(float(np.nansum(vR[f_])), 2),
           "rule_entry_meanR_on_filled": round(float(bR[f_ & bF].mean()), 4) if (f_ & bF).sum() else None,
           "rule_entry_totalR_on_filled": round(float(bR[f_ & bF].sum()), 2),
           "n_missed": int(m_.sum()),
           "rule_entry_meanR_on_missed": round(float(bR[m_b].mean()), 4) if m_b.sum() else None,
           "rule_entry_totalR_on_missed": round(float(bR[m_b].sum()), 2),
           "n_market_fallback": int((taken & fall).sum()),
           "variant_meanR_fallback": round(float(np.nanmean(vR[taken & fall])), 4) if (taken & fall).sum() else None,
           "variant_totalR_fallback": round(float(np.nansum(vR[taken & fall])), 2),
           "n_refused_legs": int(res.refused.sum())}
    return out


def checks(legs, res, info):
    """The simulator used exactly the decided entries: a limit leg fills on the pre-resolved bar, a market leg on its
    entry bar."""
    lg = legs.leg.to_numpy()
    et = legs.etype.to_numpy()
    fi = res.fi.to_numpy()
    filled = res.filled.to_numpy()
    sig = legs.sig.to_numpy()
    bad_lim = 0
    if "fill_bar" in info:
        m = (lg == 1) & (et == 2)
        bad_lim = int((~filled[m]).sum() + (fi[m & filled] != info["fill_bar"][sig[m & filled]]).sum())
    m = (et == 0) & (lg > 0)
    bad_mkt = int((~filled[m]).sum() + (fi[m & filled] != legs.entry_i.to_numpy()[m & filled]).sum())
    return {"limit_fill_bar_mismatch": bad_lim, "market_fill_bar_mismatch": bad_mkt}


def main():
    t00 = time.time()
    lines = []
    base_all = {}
    cur = None
    m1 = m1s = A = As = leader = None
    for name, sym in ORDER:
        k = key(name, sym)
        spec = DECL["sleeves"][k]
        t0 = time.time()
        if sym != cur:
            m1 = m1s = A = As = leader = None
            m1 = load_is(sym)
            A = arrays(m1)
            m1s = frame_for(m1, True)
            As = arrays(m1s)
            leader = load_is("us100", cols=A_COLS_LEADER) if sym == "btcusd" else None
            cur = sym
        cell = {}
        trades_out = []
        base_all[k] = {}
        for stress in (False, True):
            tag = "x1.5" if stress else "fp"
            fr, AA = (m1s, As) if stress else (m1, A)
            c = costs(sym, stress)
            o = build_orders(name, sym, fr, leader)
            lo = lab_orders(o)
            tr0, sg0, res0 = base_run(fr, AA, o, lo, sym, stress)
            base_all[k][tag] = summarise(tr0)
            S = signal_table(name, sym, o, lo, AA, c)
            for v in spec["variants"]:
                for mode in v["stop_modes"]:
                    legs, hold, info = build(name, v, mode, S, lo, AA, c)
                    res = sim_legs(fr, AA, legs, sym, stress)
                    sigs = pd.DataFrame({"act": S.act.to_numpy(np.int64), "hold": hold,
                                         "side": S.side.to_numpy(np.int64)}, index=np.arange(len(S)))
                    tr, sg = signal_trades(sigs, legs, res, len(AA["ns"]))
                    r = summarise(tr)
                    r["fill"] = fill_split(S, sg, legs, res, res0, AA, tr)
                    r["checks"] = checks(legs, res, info)
                    cell.setdefault((v["id"], mode), {})[tag] = r
                    tt = tr.reset_index().rename(columns={"index": "sig"})
                    tt["cell"] = f"{v['id']}|{mode}"
                    tt["cost"] = tag
                    trades_out.append(tt[["cell", "cost", "sig", "R", "entry_time", "exit_time", "n_legs",
                                          "censored"]])
            b = tr0.reset_index().rename(columns={"index": "sig"})
            b["cell"] = "BASE"
            b["cost"] = tag
            trades_out.append(b[["cell", "cost", "sig", "R", "entry_time", "exit_time", "n_legs", "censored"]])
        pd.concat(trades_out, ignore_index=True).to_parquet(os.path.join(CELLS_DIR, f"{name}__{sym}.parquet"))
        ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        for v in spec["variants"]:
            for mode in v["stop_modes"]:
                rr = cell[(v["id"], mode)]
                lines.append({"part": "part2", "sleeve": k, "variant": v, "stop_mode": mode, "ts": ts,
                              "fp": rr["fp"], "x1.5": rr["x1.5"]})
                f, s = rr["fp"]["common"], rr["x1.5"]["common"]
                bf, bs = base_all[k]["fp"]["common"], base_all[k]["x1.5"]["common"]
                print(f"{k:28s} {v['id']:11s} {mode:5s} | fp n {f['n']:4d} exp {f['exp_R']:+.4f} (base "
                      f"{bf['exp_R']:+.4f}) tot {f['total_R']:8.2f} (base {bf['total_R']:8.2f}) avgL "
                      f"{f.get('avg_loss_R', 0):+.3f} ({bf['avg_loss_R']:+.3f}) | x1.5 exp {s['exp_R']:+.4f} "
                      f"({bs['exp_R']:+.4f}) tot {s['total_R']:8.2f} ({bs['total_R']:8.2f}) | filled "
                      f"{rr['fp']['fill']['share_filled']} chk {rr['fp']['checks']} {rr['x1.5']['checks']}",
                      flush=True)
        print(f"   [{time.time() - t0:.1f}s]", flush=True)
    with open(os.path.join(RES, "trials.jsonl"), "a") as fh:
        for ln in lines:
            fh.write(jline(ln) + "\n")
    jdump({"what": "baseline of each sleeve through this lens's path, censored trades left out", "sleeves": base_all},
          os.path.join(RES, "variants_baseline.json"))
    print(f"total {time.time() - t00:.0f}s, {len(lines)} cells", flush=True)


if __name__ == "__main__":
    main()
