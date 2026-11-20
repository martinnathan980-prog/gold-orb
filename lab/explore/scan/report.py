"""discovery_summary.json, confirmation.json (copied as it is) and a short plain-text summary (summary.txt).

    python3 -B -m scan.report [--dir ~/explore_data/scan]

Distribution of the whole grammar: for each family and frame, on each unit, the share of rules with t > 2 and t < -2
on the discovery tables, the trade-weighted mean gross and net R; the same shares and the median t over the rule-units
with n >= N_MIN_T trades (a t on a handful of trades is huge and noisy: no mean or sd of t is reported, only shares
and medians); the counts; the eligible table; notes on the grammar's choices the reader should know."""
import argparse
import json
import math
import os
import sys

import numpy as np
import pandas as pd

from . import discover as DS
from . import grammar as G

N_MIN_T = 30
NOTES = [
    "Entry at the open of the next hourly bar after known_at, with no time limit (DIRECTION4 section 2): a Friday "
    "D1 signal enters at the Sunday reopening, an index signal of the session close at the next session's open.",
    "An H4/D1 value is stamped known at its block's scheduled end (17, 21, 01, 05, 09, 13 New York); where a block's "
    "bars stop early this is later than its last hourly bar's end, but no hourly bar lies in between, so the entry "
    "bar of every rule and the F1/F2 trend of H4/D1 signals are the same as with the end of the last hourly bar; an "
    "H1 signal on the last bar of an H4 block that stops early sees the previous H4 block for F1/F2 (GRAMMAR.md "
    "section 1).",
    "K05/K06 compare the range with the ATR(20) of the previous bar; K07's 38.2 % is measured on the shock bar's "
    "close-to-close move (GRAMMAR.md section 3).",
    "Siblings: the other exit, plus the neighbouring parameter along T01-T03, T06-T07, R01-R03, K01-K02, K03-K04 "
    "only; every other signal has only its other-exit sibling (GRAMMAR.md section 8).",
    "F1/F2 use the last H4 bar known at the signal's known_at (GRAMMAR.md section 4).",
    "Signals needing 500 bars (K01-K04, K07, H05) have no D1 signal before about 2015, T03 on D1 none before about "
    "late 2013: those D1 rules need 4 positive years out of about 4 usable ones (as pre-registered).",
    f"share_t_gt_2 counts every rule-unit; rule-units with few trades have huge, noisy t, so the shares and median t "
    f"over the rule-units with n >= {N_MIN_T} are given beside it; no mean or sd of t is reported.",
]


def _tdist(g):
    k = g[g.n >= N_MIN_T]
    return {f"rule_units_n_ge_{N_MIN_T}": int(len(k)),
            f"share_t_gt_2_n_ge_{N_MIN_T}": _f((k.t > 2).mean()) if len(k) else None,
            f"share_t_lt_-2_n_ge_{N_MIN_T}": _f((k.t < -2).mean()) if len(k) else None,
            f"median_t_n_ge_{N_MIN_T}": _f(k.t.median()) if len(k) else None}


def _f(v):
    if v is None:
        return None
    v = float(v)
    if math.isnan(v):
        return None
    if math.isinf(v):
        return "inf" if v > 0 else "-inf"
    return round(v, 4)


def build(sdir):
    st = pd.read_csv(os.path.join(sdir, "unit_stats.csv"))
    with open(os.path.join(sdir, "frozen_candidates.json")) as f:
        fz = json.load(f)
    conf = None
    cp = os.path.join(sdir, "confirmation.json")
    if os.path.isfile(cp):
        with open(cp) as f:
            conf = json.load(f)
    ddir = os.path.join(sdir, "discovery")
    man = fz["discovery_manifest"]
    n_sig = n_tr = 0
    cells = cells_tr = 0
    for m in man["markets"]:
        a = DS.load_market(ddir, m)
        n_sig += int(a["c_signals"].sum())
        n_tr += int(a["c_trades"].sum())
        cells += len(a["c_rule"])
        cells_tr += int((a["c_trades"] > 0).sum())
    dist = []
    for (fam, fr, unit), g in st.groupby(["family", "frame", "unit"], sort=True):
        n = g.n.sum()
        dist.append({"family": fam, "frame": fr, "unit": unit, "rules": int(len(g)),
                     "share_t_gt_2": _f((g.t > 2).mean()), "share_t_lt_-2": _f((g.t < -2).mean()),
                     "mean_R_gross": _f((g.mean_R_gross * g.n).sum() / n) if n else None,
                     "mean_R_net": _f((g.mean_R * g.n).sum() / n) if n else None, "trades": int(n), **_tdist(g)})
    fam_tot = []
    for (fam, b), g in st.groupby(["family", "basket"], sort=True):
        n = g.n.sum()
        fam_tot.append({"family": fam, "units": "baskets" if b else "single markets", "rule_units": int(len(g)),
                        "share_t_gt_2": _f((g.t > 2).mean()), "share_t_lt_-2": _f((g.t < -2).mean()),
                        "mean_R_gross": _f((g.mean_R_gross * g.n).sum() / n) if n else None,
                        "mean_R_net": _f((g.mean_R * g.n).sum() / n) if n else None, **_tdist(g)})
    el = st[st.eligible].sort_values(["t"], ascending=False)
    cols = ["rule", "unit", "n", "t", "PF", "PF_stress", "years_pos", "markets_pos_frac", "max_market_share",
            "mean_R", "mean_R_gross", "sibling_t_max"]
    elig = [{k: (_f(v) if isinstance(v, (float, np.floating)) else (int(v) if isinstance(v, (np.integer,)) else v))
             for k, v in r.items()} for r in el[cols].to_dict("records")]
    summ = {"what": "DIRECTION4 discovery summary (bars before 2019-01-01)",
            "rules_sha256": fz["rules_sha256"], "source": man["source"],
            "counts": {"rules": int(st.rule.nunique()), "markets": len(man["markets"]), "rule_market_cells": cells,
                       "cells_with_trades": cells_tr, "signals": n_sig, "trades": n_tr,
                       "rule_unit_cells_evaluated": int(len(st)), "eligible_rule_units": int(st.eligible.sum()),
                       "basket_units_with_t_ge_2.5": int(((st.t >= 2.5) & st.basket).sum()),
                       "single_units_with_t_ge_3": int(((st.t >= 3.0) & ~st.basket).sum()),
                       "candidates": len(fz["candidates"]),
                       "confirmed": None if conf is None else conf["n_confirmed"]},
            "by_family": fam_tot, "by_family_frame_unit": dist, "eligible": elig,
            "candidates": [{"order": c["order"], "rule": c["rule"], "unit": c["unit"], "t": c["discovery"]["t"]}
                           for c in fz["candidates"]],
            "skipped_for_correlation": fz["skipped_for_correlation"], "notes": NOTES}
    with open(os.path.join(sdir, "discovery_summary.json"), "w") as f:
        json.dump(summ, f, indent=1, sort_keys=True)
    L = [f"DIRECTION4 scan ({man['source']}); rules sha256 {fz['rules_sha256']}",
         f"discovery (before 2019): {summ['counts']['rules']} rules, {cells} rule-market cells, {n_tr} trades, "
         f"{len(st)} rule-unit cells, {int(st.eligible.sum())} eligible",
         "by family (baskets / single markets): share t>2, share t<-2, mean gross R, mean net R; "
         f"over n >= {N_MIN_T}: rule-units, share t>2, median t"]
    for r in fam_tot:
        L.append(f"  {r['family']:<12} {r['units']:<15} {r['share_t_gt_2']} {r['share_t_lt_-2']} "
                 f"{r['mean_R_gross']} {r['mean_R_net']}; {r[f'rule_units_n_ge_{N_MIN_T}']} "
                 f"{r[f'share_t_gt_2_n_ge_{N_MIN_T}']} {r[f'median_t_n_ge_{N_MIN_T}']}")
    if not fz["candidates"]:
        L.append("selection: nothing (no eligible rule-unit above the thresholds); the scan stops here")
    else:
        L.append(f"selection: {len(fz['candidates'])} frozen candidates")
        res = {(r["rule"], r["unit"]): r for r in (conf or {}).get("results", [])}
        for c in fz["candidates"]:
            r = res.get((c["rule"], c["unit"]))
            tail = "" if r is None else (f" -> 2019-2021: n {r['n']}, t {r.get('t_daily')}, PF {r.get('PF')}, "
                                         f"null {r.get('null_pct')}: {'CONFIRMED' if r['confirmed'] else 'not confirmed'}")
            L.append(f"  {c['order']:>2} {c['stage']:<6} {c['rule']:<18} {c['unit']:<6} t {c['discovery']['t']}{tail}")
    if conf is not None:
        L.append(f"confirmed: {conf['n_confirmed']} of {conf['n_candidates']} (about 1 in 24 expected by chance "
                 "if nothing is real); each survivor goes to the lab's ordinary protocol")
    L.append("notes:")
    L.extend("  - " + x for x in NOTES)
    txt = "\n".join(L) + "\n"
    with open(os.path.join(sdir, "summary.txt"), "w") as f:
        f.write(txt)
    return summ, txt


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=DS.SCAN_DIR)
    a = ap.parse_args(argv)
    _, txt = build(a.dir)
    print(txt, end="")


if __name__ == "__main__":
    sys.exit(main())
