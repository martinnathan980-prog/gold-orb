"""validation_hi -- run a SPEC at the run's CUT: every sleeve (one symbol frame in memory at a time), then the
portfolios (plain sum and capped account, with stakes), then the comparisons. Returns one result dict.

SPEC (JSON; see look_spec.json):
    name
    changes_in_look  [change ids]: THE LIST THE LEAD EDITS BEFORE THE DECLARATION. Only these changes enter the run;
                  everything that needs another change is left out mechanically (select_changes below)
    windows       {"in_sample": W, "look": W} with W = {"eval": [start, end], "years": [...], "splits": [[name, a, b]]}
                  the run uses "look" when CUT > 2022-01-01, else "in_sample"
    modes         ["fp", "stress"]            FP costs; spread and slippage x1.5 (orders rebuilt on the wider quotes)
    execs         ["lab", "live"]             as specified; as the live program would (vhi_sleeves docstring)
    live_one_position, live_friday_block      the live semantics (vhi_sleeves.run / live_orders)
    accounts      ["sum", "capped"]
    official_check  true: the ten unchanged sleeves rebuilt and compared row by row with results/r2/recalc/trades,
                  on the whole frame and on the judged window (synthesis A's CHECK FIRST: res["check_first"], the
                  first key of the output; a failure is printed loudly and synthesis A's changes are then not judged;
                  an '@payoff' reference not identical to its P0 sleeve inside the window is a WARNING line there,
                  with its counts, not a failure)
    sleeves       [{key, rule, sym, convention, change {kind, id, ...}, base, refuse, every_signal, signals}]
    portfolios    {name: {"sleeves": [keys], "stakes": {key: stake spec with an "id"}}} (or relative to P0)
    comparisons   [{"name", "ref", "var"}]                 portfolio vs portfolio (same mode / exec / account), the
                                                           variant at equal weekly swing (scale recomputed on the
                                                           judged window, vhi_book.equal_swing)
    sleeve_comparisons [{"name", "ref", "var"}]            sleeve chain vs sleeve chain ("<key>" or "<key>:base")
    criteria      {change id: {"kind": ..., ...}}          the declared criteria, computed in res["verdicts"]
                                                           (vhi_verdicts; kinds registered with register_criterion);
                                                           synthesis A's changes (kind synthesis_A_change: V1-V5 at
                                                           the FROZEN equal-swing factors) also get res["synthesis_A"]:
                                                           the passing changes together against the unchanged
                                                           portfolio, and synthesis A's item-6 report (reported)
"""
import gc
import hashlib
import json
import os
import time

import numpy as np
import pandas as pd

import vhi_book as B
import vhi_data as D
import vhi_guard as G
import vhi_lens as L
import vhi_sleeves as SL
import vhi_stakes as ST
from goldlab.sim import simulate

SYM_ORDER = ["us100", "xauusd", "btcusd", "ethusd"]
TEN_KEYS = [f"{n}__{s}" for n, s in L.TEN]


def ts(x):
    return pd.Timestamp(x, tz="UTC") if pd.Timestamp(x).tzinfo is None else pd.Timestamp(x).tz_convert("UTC")


def resolve_portfolios(spec):
    """{name: {"sleeves": [...], "stakes": {...}}}; a portfolio may be written relative to another one:
    {"base": "P0" (default), "replace": {old key: new key}, "add": [keys], "drop": [keys]}."""
    raw = spec.get("portfolios", {})
    out = {}

    def get(n, depth=0):
        if n in out:
            return out[n]
        p = raw[n]
        if "sleeves" in p:
            sl = list(p["sleeves"])
        else:
            assert depth < 10
            sl = list(get(p.get("base", "P0"), depth + 1)["sleeves"])
            for old, new in (p.get("replace") or {}).items():
                assert old in sl, f"{n}: {old} not in its base"
                sl[sl.index(old)] = new
            sl += [k for k in (p.get("add") or []) if k not in sl]
            sl = [k for k in sl if k not in (p.get("drop") or [])]
        out[n] = {"sleeves": sl, "stakes": dict(p.get("stakes") or {})}
        return out[n]

    for n in raw:
        get(n)
    return out


# ------------------------------------------------------------------------------------------------- the changes in the look
def _sleeve_key(ref):
    return ref.partition(":")[0]


def available_changes(spec):
    """{change id: {"sleeves": [keys], "stakes": [(portfolio, sleeve)]}}: every change the spec carries (a sleeve's
    change, or a portfolio stake spec, which must carry an "id")."""
    out = {}
    for s in spec["sleeves"]:
        ch = s.get("change")
        if ch:
            if not ch.get("id"):
                raise ValueError(f"sleeve {s['key']}: its change needs an 'id' (the name the list changes_in_look uses)")
            out.setdefault(ch["id"], {"sleeves": [], "stakes": []})["sleeves"].append(s["key"])
    for pn, p in (spec.get("portfolios") or {}).items():
        for k, st in (p.get("stakes") or {}).items():
            if st is None:
                continue
            if not st.get("id"):
                raise ValueError(f"portfolio {pn}: the stake rule of {k} needs an 'id' (a stake rule is a change: it "
                                 "enters the look only when changes_in_look names it)")
            out.setdefault(st["id"], {"sleeves": [], "stakes": []})["stakes"].append([pn, k])
    return out


def select_changes(spec, cut=None):
    """The spec restricted to the changes named in spec["changes_in_look"]: a sleeve with a change enters iff its id
    is listed; an unchanged sleeve that is the 'base' of changed sleeves (a '<sleeve>@payoff' reference) enters iff
    one of them does; the other unchanged sleeves (the ten) always enter; a portfolio enters iff all its sleeves and
    the ids of its stake rules do; a comparison iff both its portfolios; a sleeve comparison iff both its sleeves.
    Without the list, every change enters (refused for a look). Returns (selected spec, record)."""
    avail = available_changes(spec)
    lst = spec.get("changes_in_look")
    if lst is None:
        if cut is not None and G.is_look(cut):
            raise ValueError("the look's spec must name its changes in 'changes_in_look'")
        lst = sorted(avail)
    unknown = [c for c in lst if c not in avail]
    if unknown:
        raise ValueError(f"changes_in_look names unknown changes {unknown}; available: {sorted(avail)}")
    if len(set(lst)) != len(lst):
        raise ValueError("changes_in_look lists a change twice")
    chosen = set(lst)
    based = {}
    for s in spec["sleeves"]:
        if s.get("change") and s.get("base"):
            based.setdefault(s["base"], []).append(s)
    keep_sl = []
    for s in spec["sleeves"]:
        ch = s.get("change")
        if ch:
            ok = ch["id"] in chosen
        elif s["key"] in based:
            ok = any(v["change"]["id"] in chosen for v in based[s["key"]])
        else:
            ok = True
        if ok:
            keep_sl.append(s)
    kept = {s["key"] for s in keep_sl}
    for s in keep_sl:
        if s.get("base") and s["base"] not in kept:
            raise ValueError(f"{s['key']}: its base {s['base']} is not a sleeve of the spec")
    allp = resolve_portfolios(spec)
    raw = spec.get("portfolios") or {}
    keep_p = {}
    for pn, p in allp.items():
        st_ids = {st["id"] for st in (p.get("stakes") or {}).values() if st}
        if all(k in kept for k in p["sleeves"]) and st_ids <= chosen:
            keep_p[pn] = raw[pn]
    keep_c = [c for c in spec.get("comparisons", []) if c["ref"] in keep_p and c["var"] in keep_p]
    keep_sc = [c for c in spec.get("sleeve_comparisons", [])
               if _sleeve_key(c["ref"]) in kept and _sleeve_key(c["var"]) in kept]
    sel = dict(spec)
    sel.update(sleeves=keep_sl, portfolios=keep_p, comparisons=keep_c, sleeve_comparisons=keep_sc,
               changes_in_look=list(lst))
    for pn, p in keep_p.items():                         # a relative portfolio's base must have been kept
        if "sleeves" not in p:
            assert p.get("base", "P0") in keep_p, f"{pn}: its base portfolio is not in the run"
    rec = {"in_look": list(lst), "listed_in_spec": spec.get("changes_in_look") is not None,
           "available": {k: v for k, v in sorted(avail.items())},
           "included": {"sleeves": [s["key"] for s in keep_sl], "portfolios": list(keep_p),
                        "comparisons": [c["name"] for c in keep_c], "sleeve_comparisons": [c["name"] for c in keep_sc]},
           "left_out": {"sleeves": [s["key"] for s in spec["sleeves"] if s["key"] not in kept],
                        "portfolios": [p for p in allp if p not in keep_p],
                        "comparisons": [c["name"] for c in spec.get("comparisons", []) if c not in keep_c],
                        "sleeve_comparisons": [c["name"] for c in spec.get("sleeve_comparisons", []) if c not in keep_sc]}}
    return sel, rec


def payoff_reference_vs_sB(spec, trades, W, modes, execs):
    """F6 diagnostic: every '<sleeve>@payoff' reference against the sB sleeve '<sleeve>' of the same run, trade by
    trade inside the evaluation window (matched on entry time and side): trades only in one of them, matched trades
    whose exit time, reason or R differ."""
    a, b = W["eval"]
    keys = {s["key"] for s in spec["sleeves"]}
    out = {}
    for s in spec["sleeves"]:
        k = s["key"]
        if not k.endswith("@payoff") or k[:-len("@payoff")] not in keys:
            continue
        k0 = k[:-len("@payoff")]
        out[k] = {}
        for mode in modes:
            for ex in execs:
                tp, ts_ = trades[(k, "main", mode, ex)], trades[(k0, "main", mode, ex)]
                wp = tp[(tp.entry_time >= a) & (tp.entry_time < b)][["entry_time", "side", "exit_time", "reason", "R"]]
                ws = ts_[(ts_.entry_time >= a) & (ts_.entry_time < b)][["entry_time", "side", "exit_time", "reason", "R"]]
                m = wp.merge(ws, on=["entry_time", "side"], how="outer", suffixes=("_payoff", "_sB"), indicator=True)
                both = m[m["_merge"] == "both"]
                dR = (both.R_payoff - both.R_sB).abs()
                dif = both[(dR > 1e-9) | (both.exit_time_payoff != both.exit_time_sB)
                           | (both.reason_payoff.astype(str) != both.reason_sB.astype(str))]
                out[k][f"{mode}/{ex}"] = {
                    "n_payoff_reference": int(len(wp)), "n_sB": int(len(ws)), "matched": int(len(both)),
                    "only_in_payoff_reference": int((m["_merge"] == "left_only").sum()),
                    "only_in_sB": int((m["_merge"] == "right_only").sum()), "matched_differing": int(len(dif)),
                    "max_abs_dR_matched": float(dR.max()) if len(both) else None,
                    "R_payoff_reference": round(float(wp.R.sum()), 3), "R_sB": round(float(ws.R.sum()), 3),
                    "identical": bool(len(dif) == 0 and len(both) == len(wp) == len(ws)),
                    "examples": [{"entry_time": str(r.entry_time), "side": int(r.side), "in": str(r._merge)}
                                 for r in m[m["_merge"] != "both"].head(5).itertuples()]
                    + [{"entry_time": str(r.entry_time), "side": int(r.side), "R_payoff": round(float(r.R_payoff), 4),
                        "R_sB": round(float(r.R_sB), 4), "exit_payoff": str(r.exit_time_payoff),
                        "exit_sB": str(r.exit_time_sB)} for r in dif.head(5).itertuples()]}
    return out


def windows_for(spec, cut):
    w = spec["windows"]["look" if G.is_look(cut) else "in_sample"]
    out = {"eval": (ts(w["eval"][0]), ts(w["eval"][1])), "years": [int(y) for y in w.get("years", [])],
           "judge_years": [int(y) for y in w.get("judge_years", w.get("years", []))],
           "splits": [(n, ts(a), ts(b)) for n, a, b in w.get("splits", [])]}
    assert out["eval"][1] <= cut, "the evaluation window ends after CUT"
    return out


# ------------------------------------------------------------------------------------------------- official check
def official_check(name, sym, m1, leader, W=None):
    """Rule 2 / synthesis A's CHECK FIRST: the official sleeve rebuilt on the cut frame (FP costs, one position, no
    refusal, as recalc.py) and compared row by row with the official rows closed before CUT; the official rows still
    open at CUT are counted only (neither their results nor their exit times are read) and must be the trades of this
    run still open at the frame's last bar. With W, the same on the judged window (entries W['eval'], the look:
    2022-01-01 .. 2025-12-31): count, total R, trade by trade ('window')."""
    O = SL.build_orders(name, m1, leader)
    t = simulate(m1, O, sym=sym, costs=SL.mode_costs(sym, "fp"), no_overlap=True)
    ent = D.official_entries(name, sym)
    off = D.official_closed(name, sym)
    n_off = int(len(ent))
    n_open = int(n_off - len(off))
    a = t[["entry_time", "side", "R", "exit_time", "reason"]].reset_index(drop=True)
    b = off[["entry_time", "side", "R", "exit_time", "reason"]].reset_index(drop=True)
    m = a.merge(b, on=["entry_time", "side"], how="left", suffixes=("_mine", "_off"), indicator=True)
    differs = (((m.R_mine - m.R_off).abs() > 1e-9) | (m.exit_time_mine != m.exit_time_off)
               | (m.reason_mine.astype(str) != m.reason_off.astype(str))) & (m["_merge"] == "both")
    both = m[m["_merge"] == "both"]
    only_mine = m[m["_merge"] == "left_only"]
    dif = m[differs]
    last = m1.index[-1]
    only_mine_boundary = bool(((only_mine.exit_time_mine >= last) | (only_mine.reason_mine == "eod")).all())
    res = {"n_mine": int(len(t)), "n_official": n_off, "official_open_at_cut": n_open,
           "official_closed_before_cut": int(len(off)), "matched_closed": int(len(both)),
           "mine_not_in_official_closed": int(len(only_mine)), "those_open_at_frame_end_in_mine": only_mine_boundary,
           "rows_differing": int(len(dif)),
           "max_abs_R_diff_matched": float((both.R_mine - both.R_off).abs().max()) if len(both) else None,
           "totR_mine_all": round(float(t.R.sum()), 3),
           "totR_mine_on_rows_closed_before_cut": round(float(both.R_mine.sum()), 6),
           "totR_official_closed_before_cut": round(float(off.R.sum()), 6)}
    whole = bool(res["n_mine"] == n_off and len(both) == len(off) and len(dif) == 0
                 and len(only_mine) == n_open and only_mine_boundary)
    res["reproduced_whole_frame"] = whole
    ok_w = True
    if W is not None:
        wa, wb = W["eval"]

        def inw(x, col="entry_time"):
            return ((x[col] >= wa) & (x[col] < wb)).to_numpy()

        mw = m[inw(m)]
        both_w, only_w = mw[mw["_merge"] == "both"], mw[mw["_merge"] == "left_only"]
        off_w = off[inw(off)]
        n_off_w = int(inw(ent).sum())
        n_open_w = int(n_off_w - len(off_w))
        dif_w = m[differs & inw(m)]
        bound_w = bool(((only_w.exit_time_mine >= last) | (only_w.reason_mine == "eod")).all())
        ok_w = bool(int(inw(t).sum()) == n_off_w and len(both_w) == len(off_w) and len(dif_w) == 0
                    and len(only_w) == n_open_w and bound_w)
        res["window"] = {"eval": [str(wa), str(wb)], "n_mine": int(inw(t).sum()), "n_official": n_off_w,
                         "official_open_at_cut": n_open_w, "official_closed_before_cut": int(len(off_w)),
                         "matched_closed": int(len(both_w)), "mine_not_in_official_closed": int(len(only_w)),
                         "those_open_at_frame_end_in_mine": bound_w, "rows_differing": int(len(dif_w)),
                         "totR_mine_all": round(float(t.R.to_numpy()[inw(t)].sum()), 3),
                         "totR_mine_on_rows_closed_before_cut": round(float(both_w.R_mine.sum()), 6),
                         "totR_official_closed_before_cut": round(float(off_w.R.sum()), 6),
                         "totals_equal_on_rows_closed_before_cut": bool(abs(float(both_w.R_mine.sum())
                                                                            - float(off_w.R.sum())) < 1e-6),
                         "examples_differing": [{"entry_time": str(r.entry_time), "side": int(r.side),
                                                 "R_mine": float(r.R_mine), "R_official": float(r.R_off),
                                                 "exit_mine": str(r.exit_time_mine), "exit_official": str(r.exit_time_off)}
                                                for r in dif_w.head(5).itertuples()],
                         "reproduced": ok_w}
    res["reproduced"] = bool(whole and ok_w)
    return res


def payoff_reference_warnings(res):
    """The '@payoff' references in the check first: for each '<sleeve>@payoff' reference (synthesis A's unchanged
    sleeve, with the payoff lens's 3-spread refusal) and each run (mode/exec), the counts of
    res['payoff_reference_vs_sB'] inside the judged window, and one WARNING line for each run where the reference is
    not identical to its P0 sleeve '<sleeve>' (a warning, not a failure: the refusal is expected to remove a few
    trades). Returns (counts, warning lines)."""
    keys = ("identical", "n_payoff_reference", "n_sB", "matched", "only_in_payoff_reference", "only_in_sB",
            "matched_differing", "R_payoff_reference", "R_sB")
    refs, warns = {}, []
    for ref, runs in (res.get("payoff_reference_vs_sB") or {}).items():
        k0 = ref[:-len("@payoff")]
        refs[ref] = {}
        for r, v in runs.items():
            info = (((res.get("sleeves") or {}).get(ref) or {}).get("runs", {}).get(r) or {}).get("info") or {}
            row = {k: v.get(k) for k in keys}
            row["orders_refused_by_the_3_spread_rule_whole_frame"] = info.get("reference_refused_orders")
            refs[ref][r] = row
            if not v.get("identical"):
                warns.append(f"WARNING (check first; a warning, not a failure): {ref} {r} is not identical to its P0 "
                             f"sleeve {k0} inside the judged window: {row['n_payoff_reference']} trades against "
                             f"{row['n_sB']}; {row['only_in_payoff_reference']} only in the reference, "
                             f"{row['only_in_sB']} only in the P0 sleeve, {row['matched_differing']} matched but "
                             f"different; total R {row['R_payoff_reference']} against {row['R_sB']}; orders refused by "
                             f"the 3-spread rule on the whole frame: "
                             f"{row['orders_refused_by_the_3_spread_rule_whole_frame']}")
    return refs, warns


def check_first(spec, res):
    """synthesis A's '3. CHECK FIRST' (the harness's official check): every one of the ten unchanged sleeves rebuilt
    by this pipeline equals the official recalc trades, on the whole frame and on the judged window (count, total R,
    trade by trade); otherwise synthesis A says 'stop and report': its changes are then not judged (verdicts
    adopted = null), and the failure is written at the top of the output. Shown beside it, never a failure
    ('payoff_references', 'warnings'): every '<sleeve>@payoff' reference against its P0 sleeve inside the judged
    window, with a WARNING line and the counts for each run where they are not identical."""
    want = set(TEN_KEYS)
    got = res.get("official") or {}
    rows = {k: {"reproduced": bool(v.get("reproduced")), "whole_frame": bool(v.get("reproduced_whole_frame")),
                "window": {kk: (v.get("window") or {}).get(kk) for kk in
                           ("n_mine", "n_official", "official_open_at_cut", "rows_differing",
                            "totR_mine_on_rows_closed_before_cut", "totR_official_closed_before_cut", "reproduced")}}
            for k, v in sorted(got.items())}
    missing = sorted(want - set(got))
    failed = sorted(k for k, v in rows.items() if not v["reproduced"]) + missing
    computed = bool(spec.get("official_check")) and not missing
    ok = computed and not failed
    status = ("PASSED: the ten unchanged sleeves rebuilt by the harness equal the official recalc trades (whole frame "
              "and judged window: count, total R, trade by trade)") if ok else (
        "FAILED -- STOP AND REPORT (synthesis A, 3. CHECK FIRST): the unchanged sleeves recomputed by this pipeline do "
        f"not equal the official recalc trades: {', '.join(failed) or 'the check was not computed'}. synthesis A's "
        "changes are NOT judged (verdicts adopted = null); every other number of this run is unverified.")
    refs, warns = payoff_reference_warnings(res)
    if warns:
        status += (f" -- {len(warns)} WARNING line(s): an '@payoff' reference is not identical to its P0 sleeve inside "
                   "the window (see 'warnings'; a warning, not a failure)")
    return {"what": check_first.__doc__.strip(), "computed": computed, "passed": ok, "status": status,
            "failed_or_missing": failed, "sleeves": rows, "payoff_references": refs, "warnings": warns}


def loud(progress, lines):
    bar = "!" * 100
    progress(bar)
    for ln in lines:
        progress(f"!!! {ln}")
    progress(bar)


# ------------------------------------------------------------------------------------------------- sleeve statistics
def sleeve_stats(t, W):
    """synthesis_B sstats + payoff stats of a sleeve chain on the evaluation window, by year, before the window."""
    a, b = W["eval"]
    P = L.payoff()["C"]
    w = t[(t.entry_time >= a) & (t.entry_time < b)]
    early = t[t.entry_time < a]
    out = {"window": B.sstats(w.R), "by_year": B.by_year(w), "payoff_stats": P.stats(w) if len(w) else {"n": 0},
           "payoff_by_year": P.by_year(w) if len(w) else {}, "before_window": B.sstats(early.R),
           "payoff_before_window": P.stats(early) if len(early) else {"n": 0}}
    if len(w) > 2:
        R = w.R.to_numpy(float)
        sd = float(R.std(ddof=1))
        out["sharpe_trade"] = float(R.mean() / sd) if sd > 0 else None
        out["bps_trade"] = float((w.pnl / w.entry).mean() * 1e4)
    for nm, x, y in W["splits"]:
        out[nm] = B.sstats(t[(t.entry_time >= x) & (t.entry_time < y)].R)
    return out


def k1_extras(sig, t_var, t_base, W):
    """The skipped signals taken alone against the kept ones (usable signals decided in the window); removed and new
    trades of the variant chain against the base chain."""
    a, b = W["eval"]
    s = sig[(sig.t_dec >= a) & (sig.t_dec < b)]
    use = (s.filled & ~s.refused & ~s.boundary & np.isfinite(s.label))
    sk, kp = s[use & s.skip], s[use & ~s.skip]
    rem = set(t_base.oid) - set(t_var.oid)
    new = set(t_var.oid) - set(t_base.oid)
    tb = t_base[(t_base.entry_time >= a) & (t_base.entry_time < b)]
    tv = t_var[(t_var.entry_time >= a) & (t_var.entry_time < b)]
    return {"skipped_signals_alone": B.sstats(sk.label), "kept_signals_alone": B.sstats(kp.label),
            "baseline_trades_removed": int(len(rem)), "R_of_removed": round(float(t_base[t_base.oid.isin(rem)].R.sum()), 3),
            "new_trades": int(len(new)), "R_of_new": round(float(t_var[t_var.oid.isin(new)].R.sum()), 3),
            "window_removed": int(len(set(tb.oid) - set(tv.oid))), "window_new": int(len(set(tv.oid) - set(tb.oid)))}


# ------------------------------------------------------------------------------------------------- portfolios
def portfolio(p, trades, signals, meta, mode, ex, accounts, W, cut):
    """One portfolio {"sleeves": [...], "stakes": {...}} in one mode and execution: stakes (pass 2), then each
    account kind. Returns ({account: metrics}, {account: judged book}, the whole-frame book with stakes)."""
    a, b = W["eval"]
    paper = B.make_book({k: (trades[(k, "main", mode, ex)], None, meta[k]) for k in p["sleeves"]})
    per, stake_info = {}, {}
    for k in p["sleeves"]:
        t = trades[(k, "main", mode, ex)]
        sr = ST.from_spec((p.get("stakes") or {}).get(k))
        if sr is None:
            per[k] = (t, None, meta[k])
            continue
        ctx = {"cut": cut, "mode": mode, "exec": ex, "sleeve": k, "sym": meta[k]["sym"], "book": paper,
               "signals": {kk: v for (kk, mm), v in signals.items() if mm == mode}, "purge": ST.PURGE}
        m = np.asarray(sr.stakes(t, ctx), float)
        stake_info[k] = {"rule": sr.name, "bounded_0_2": ST.check_bounds(m),
                         "mean": round(float(np.mean(m)), 4) if len(m) else None,
                         "zero": int((m == 0).sum()), "n": int(len(m))}
        per[k] = (t, m, meta[k])
    d_all = B.make_book(per)
    mts, bks = {}, {}
    for acc in accounts:
        d = B.apply_account(d_all, acc, a, b)
        bks[acc] = d
        mt = B.sB(d, a, b, W["splits"])
        mt["swing"] = B.swing(d, a, b, 1.0, W["judge_years"] or None)
        if acc == "capped":
            mc, why = B.capped_stakes(d_all)
            sel = ((d_all.entry_time >= a) & (d_all.entry_time < b)).to_numpy()
            mt["capped_skips_in_window"] = int(((why == 2) & sel).sum())
            mt["offered_in_window"] = int(sel.sum())
        if stake_info:
            mt["stakes"] = stake_info
        mts[acc] = mt
    return mts, bks, d_all


# ------------------------------------------------------------------------------------------------- the run
def load_plugins(spec):
    """Modules listed in spec["plugins"] (paths) are imported before the run: they may register change kinds
    (vhi_sleeves.register_change) or define stake rules (loaded by a stake spec of kind 'python')."""
    import importlib.util
    out = []
    here = os.path.dirname(os.path.abspath(__file__))
    for i, path in enumerate(spec.get("plugins", [])):
        if os.path.isabs(path):
            p = path
        elif path.startswith("lab/"):                    # relative to the repository root
            p = os.path.join(os.path.dirname(G.LAB), path)
        else:                                            # relative to this directory
            p = os.path.join(here, path)
        p = os.path.abspath(p)
        G.check_path(p)
        sp = importlib.util.spec_from_file_location(f"vhi_plugin_{i}", p)
        m = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(m)
        out.append({"path": p, "sha256": sha256(p)})
    return out


def run_spec(spec, cut, progress=print):
    import vhi_verdicts as VD
    plugins = load_plugins(spec)
    spec_all = spec
    spec, selection = select_changes(spec_all, cut)
    W = windows_for(spec, cut)
    modes, execs = spec.get("modes", ["fp", "stress"]), spec.get("execs", ["lab"])
    lop = spec.get("live_one_position", "entry_bar")
    lfb = spec.get("live_friday_block", "decision_and_entry")
    sleeves = spec["sleeves"]
    keys = [s["key"] for s in sleeves]
    assert len(keys) == len(set(keys)), "duplicate sleeve keys"
    by_sym = {}
    for s in sleeves:
        by_sym.setdefault(s["sym"], []).append(s)
    syms = [x for x in SYM_ORDER if x in by_sym] + sorted(x for x in by_sym if x not in SYM_ORDER)
    need_leader = any(s["rule"] == "nq_btc_follow" for s in sleeves)
    res = {"check_first": None,                          # synthesis A's CHECK FIRST: the first thing of the output
           "spec": spec.get("name"), "cut": str(cut), "windows": {"eval": [str(x) for x in W["eval"]],
                                                                  "years": W["years"], "splits": [[n, str(a), str(b)] for n, a, b in W["splits"]]},
           "changes": selection,
           "frames": {}, "official": {}, "sleeves": {}, "portfolios": {}, "comparisons": {}, "sleeve_comparisons": {},
           "plugins": plugins, "live_one_position": lop, "live_friday_block": lfb}
    progress(f"== changes in this run: {selection['in_look']} ({len(sleeves)} sleeves, "
             f"{len(selection['included']['portfolios'])} portfolios)")
    trades = {}          # (key, chain, mode, exec) -> DataFrame
    signals = {}         # (key, mode) -> signal table (K1 / generic)
    leader = None
    if need_leader and "us100" not in by_sym:
        m = D.frame("us100")
        leader = D.leader_series(m)
        del m
    official_done = set()
    for sym in syms:
        t0 = time.time()
        m1 = D.frame(sym)
        res["frames"][sym] = {"bars": int(len(m1)), "first": str(m1.index[0]), "last": str(m1.index[-1])}
        progress(f"== {sym}: {len(m1)} bars {m1.index[0]} .. {m1.index[-1]} [{time.time() - t0:.0f}s]")
        if sym == "us100" and need_leader:
            leader = D.leader_series(m1)
        for s in by_sym[sym]:
            k = s["key"]
            if spec.get("official_check") and not s.get("change") and f"{s['rule']}__{sym}" in TEN_KEYS \
                    and (s["rule"], sym) not in official_done:
                res["official"][f"{s['rule']}__{sym}"] = official_check(s["rule"], sym, m1, leader, W)
                official_done.add((s["rule"], sym))
                o = res["official"][f"{s['rule']}__{sym}"]
                ow = o.get("window") or {}
                progress(f"   official {s['rule']:20s} {sym}: n {o['n_mine']}/{o['n_official']} open at cut "
                         f"{o['official_open_at_cut']} differing {o['rows_differing']} | window n "
                         f"{ow.get('n_mine')}/{ow.get('n_official')} differing {ow.get('rows_differing')} -> "
                         f"{'OK' if o['reproduced'] else 'MISMATCH'}")
                if not o["reproduced"]:
                    loud(progress, [f"OFFICIAL CHECK (synthesis A's CHECK FIRST) FAILED for {s['rule']}__{sym}: the "
                                    "rebuilt sleeve differs from the official recalc trades",
                                    "the run continues so that nothing is lost; synthesis A's changes will not be judged"])
            res["sleeves"][k] = {"spec": s, "runs": {}}
            for mode in modes:
                for ex in execs:
                    out, info = SL.run(s, m1, mode, ex, leader, every_signal=bool(s.get("every_signal")),
                                       keep_signals=True, live_one_position=lop, live_friday_block=lfb)
                    for chain in ("main", "base", "every_signal"):
                        if chain in out:
                            trades[(k, chain, mode, ex)] = out[chain]
                    if "signals" in out and ex == "lab":
                        signals[(k, mode)] = out["signals"]
                    if s.get("signals") and ex == "lab" and (k, mode) not in signals:
                        mk = SL.mode_frame(m1, mode)
                        O = SL.build_orders(s["rule"], mk, leader)
                        costs = SL.mode_costs(sym, mode)
                        signals[(k, mode)] = ST.generic_signal_table(
                            mk, O, sym, mode, lambda oo: simulate(mk, oo, sym=sym, costs=costs, no_overlap=False))
                        del mk
                    r = {"info": info, "main": sleeve_stats(out["main"], W)}
                    if "base" in out:
                        r["base"] = sleeve_stats(out["base"], W)
                        if s.get("change", {}).get("kind") == "k1_riskbp":
                            r["k1"] = k1_extras(out["signals"], out["main"], out["base"], W)
                    if "every_signal" in out:
                        r["every_signal"] = sleeve_stats(out["every_signal"], W)["window"]
                    res["sleeves"][k]["runs"][f"{mode}/{ex}"] = r
                    progress(f"   {k:44s} {mode:6s} {ex:4s} n {r['main']['window'].get('n', 0):5d} "
                             f"tot {r['main']['window'].get('total', 0):8.2f} [{info['sec']}s]")
            gc.collect()
        del m1
        L.clear_rule_caches()
        gc.collect()
    res["_trades"] = trades
    res["_signals"] = signals
    res["payoff_reference_vs_sB"] = payoff_reference_vs_sB(spec, trades, W, modes, execs)
    res["check_first"] = check_first(spec, res)
    if not res["check_first"]["passed"]:
        loud(progress, [res["check_first"]["status"]])
    else:
        progress(f"== check first: {res['check_first']['status']}")
    for w in res["check_first"]["warnings"]:
        progress(w)
    # ------------------------------------------------------------------------------------------- portfolios
    a, b = W["eval"]
    meta = {s["key"]: {"sym": s["sym"], "tie": f"{s['rule']}_{s['sym']}"} for s in sleeves}
    books = {}
    res["portfolio_sleeves"] = {n: p["sleeves"] for n, p in resolve_portfolios(spec).items()}
    for pname, p in resolve_portfolios(spec).items():
        res["portfolios"][pname] = {}
        for mode in modes:
            for ex in execs:
                mts, bks, _ = portfolio(p, trades, signals, meta, mode, ex, spec.get("accounts", ["sum"]), W, cut)
                for acc in mts:
                    books[(pname, mode, ex, acc)] = bks[acc]
                    res["portfolios"][pname][f"{mode}/{ex}/{acc}"] = mts[acc]
                progress(f"   portfolio {pname:16s} {mode:6s} {ex:4s} " + " | ".join(
                    f"{acc} n {mts[acc].get('n', 0)} tot {mts[acc].get('total', 0)}" for acc in mts))
    for c in spec.get("comparisons", []):
        res["comparisons"][c["name"]] = {}
        # the judged window of the comparison: its own "window" ([start, end]) or the judge years of the run
        if c.get("window"):
            ca, cb = ts(c["window"][0]), ts(c["window"][1])
        elif W["judge_years"]:
            ca, cb = ts(f"{min(W['judge_years'])}-01-01"), ts(f"{max(W['judge_years']) + 1}-01-01")
        else:
            ca, cb = a, b
        ca, cb = max(ca, a), min(cb, b)
        jy = [y for y in (W["judge_years"] or []) if ca.year <= y <= (cb - pd.Timedelta(nanoseconds=1)).year] or None
        for (pn, mode, ex, acc), d in books.items():
            if pn != c["ref"]:
                continue
            dv = books[(c["var"], mode, ex, acc)]
            sub = lambda x: x[(x.entry_time >= ca) & (x.entry_time < cb)]
            r = B.equal_swing(sub(d), sub(dv), ca, cb, jy)
            r["window"] = [str(ca), str(cb)]
            res["comparisons"][c["name"]][f"{mode}/{ex}/{acc}"] = r
    for c in spec.get("sleeve_comparisons", []):
        res["sleeve_comparisons"][c["name"]] = {}
        for mode in modes:
            for ex in execs:
                def get(x):
                    k, _, ch = x.partition(":")
                    return trades[(k, ch or "main", mode, ex)]
                tr, tv = get(c["ref"]), get(c["var"])
                sr, sv = sleeve_stats(tr, W), sleeve_stats(tv, W)
                yrs = W["years"]
                up = [y for y in yrs if y in sv["by_year"] and y in sr["by_year"] and sv["by_year"][y]["exp"] > sr["by_year"][y]["exp"]]
                res["sleeve_comparisons"][c["name"]][f"{mode}/{ex}"] = {
                    "ref": sr["window"], "var": sv["window"],
                    "d_exp": round(sv["window"].get("exp", 0) - sr["window"].get("exp", 0), 4),
                    "d_total": round(sv["window"].get("total", 0) - sr["window"].get("total", 0), 2),
                    "years_exp_up": up}
    res["_books"] = books
    res["_meta"] = meta
    res["_W"] = W
    res["_spec"] = spec
    res["verdicts"] = VD.compute(spec, res, W)
    for cid, v in res["verdicts"].items():
        progress(f"   verdict {cid:16s} " + ("no criterion declared" if not v.get("declared") else
                                            f"ERROR {v['error']}" if v.get("error") else
                                            f"adopted {v['adopted']} ({sum(c['pass'] for c in v['criteria'])}/"
                                            f"{len(v['criteria'])} criteria)"
                                            + (f" {v['V']}" if v.get("V") else "")
                                            + (" -- NOT JUDGED: check first failed" if v.get("stopped_by_check_first")
                                               else "")))
    res["synthesis_A"] = VD.synthesis_A_block(spec, res, W, res["verdicts"])
    if res["synthesis_A"].get("changes"):
        sa = res["synthesis_A"]
        progress(f"   synthesis A: passing {sa.get('passing')} ; together vs unchanged: "
                 + json.dumps(sa.get("together_vs_unchanged_headline"), default=str))
    if not res["check_first"]["passed"]:
        loud(progress, [res["check_first"]["status"]])
    return res


def strip_private(res):
    return {k: v for k, v in res.items() if not k.startswith("_")}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def imported_code_sha256(extra_paths=()):
    """A5: the sha256 of every file under lab/ that the process imported (every module in sys.modules whose file is
    under lab/: the harness, the lenses, the strategy modules, recalc.py, goldlab), keyed by its path relative to lab/,
    with the module names it was imported as; `extra_paths` (files loaded by path, e.g. plugins) are added. A file the
    guard refuses to open, or that cannot be read, is recorded with its error instead of a hash (never raises)."""
    import sys
    out = {}
    items = [(n, getattr(m, "__file__", None)) for n, m in list(sys.modules.items())]
    items += [(f"<loaded by path {i}>", p) for i, p in enumerate(extra_paths)]
    for name, f in items:
        if not f or not isinstance(f, str):
            continue
        p = os.path.realpath(f)
        if not (p == G.LAB_REAL or p.startswith(G.LAB_REAL + os.sep)) or not os.path.isfile(p):
            continue
        rel = os.path.relpath(p, G.LAB_REAL)
        if rel in out:
            out[rel]["modules"].append(name)
            continue
        try:
            out[rel] = {"sha256": sha256(p), "modules": [name]}
        except (OSError, G.GuardError) as e:
            out[rel] = {"sha256": None, "error": str(e)[:200], "modules": [name]}
    return dict(sorted(out.items()))


def opened_files_sha256(reads):
    """A5 (beside the code): the sha256 of every non-data file under lab/ the run opened for reading (G.reads() kind
    'open': configuration such as r2/fp_costs.json and the F1 model JSON); never raises."""
    out = {}
    for r in reads:
        if r.get("kind") != "open":
            continue
        rel = r["path"]
        if rel in out or os.path.isabs(rel):
            continue
        p = os.path.join(G.LAB_REAL, rel)
        try:
            out[rel] = sha256(p)
        except (OSError, G.GuardError) as e:
            out[rel] = f"error: {str(e)[:200]}"
    return dict(sorted(out.items()))


def js_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp,)):
        return str(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, set):
        return sorted(o)
    return str(o)


def canonical(obj):
    """obj as it reads back from its JSON file (NaN -> None), for exact comparisons between runs."""
    return json.loads(json.dumps(obj, default=js_default), parse_constant=lambda c: None)


def jdump(obj, path):
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=js_default)
