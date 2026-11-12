"""validation_hi -- the proofs of the task's rule 3, ON IN-SAMPLE DATA ONLY (CUT = 2022-01-01).

The look's own specification (look_spec.json) is run through the look's own code path (vhi_run.run_spec) at
CUT = 2022-01-01 on its in-sample windows with EVERY available change (the spec's list changes_in_look is replaced,
in memory only, by all of them, so that every candidate is rehearsed; proof j runs the list as it stands), and every
number is compared with what the lenses published:
    (a) the ten official sleeves: trades and total R (results/r2/recalc/trades, rows read with entry_time < CUT;
        results compared on the rows also closed before CUT) and synthesis_B's first check
    (b) K1 (synthesis_B sleeve_runs C1, fp and x1.5): folds, thresholds 505.9 / 496.7 / 465.1 bp, the 2022 value
        478.3 bp, 2019-2021 395 -> 304 trades, +49.1 -> +63.9 R; the generalised walk-forward identical to
        s1_run.walk_forward. Review F4: the declared FP labels in both cost modes leave the folds, T(2022) =
        478.284 bp and the x1.5 chain unchanged (against the x1.5 run with x1.5 labels, synthesis_B's own, rerun).
        Review F5: the declared T is binding (more than 0.01 bp off raises, in the run itself); A4: so are the
        declared skip side 'hi' and n_train 2345 of 2022 (another side or count raises, in the run itself)
    (c) K2 and K3 (synthesis_B sleeve_runs N1, N2): 344 trades +155.5 R, 375 trades +194.3 R, fp and x1.5
    (d) the seven payoff variants in play and their references (results/r2/autopsy/payoff/variants_table.csv);
        review F6: the '<sleeve>@payoff' references with the payoff lens's 3-spread refusal, and trade by trade
        against the sB sleeves inside the window
    (e) the synthesis_B portfolios P0 and P2 (and P1), fp and x1.5, every field; and the harness metrics equal to
        synthesis_B's own s2_portfolio.metrics on the same book
plus the harness's own checks:
    (f) the capped account (6 positions, 2 per market) equals the cluster lens's run_engine and account.py
    (g) the live execution: with no delay and no Friday close the live chain IS the official chain; K2 as the live
        program would, against the verifier's figures quoted in synthesis_B; review F7: the Friday block tested on
        the decision instant as well as on the delayed entry bar
    (h) stakes: the stake interface reproduces P0 at stake 1, adds exactly what a sleeve-year table adds, and a
        walk-forward stake only uses outcomes known before each 1 January minus 7 days
    (i) the guard: review F1 (the declaration bound to the spec: PROTOCOL_V3.md as it stands is refused), A1 (only
        the protocol's real path is accepted: proofs.json, the rehearsal JSON, proof_i_guard.json and copies of them
        in /tmp, the scratchpad, the harness folder and lab/results/ are refused although their text quotes the
        track and the spec's sha256 -- checked again after those files are written), F2 (run once, fixed output
        path, second access), F3 / A2 / A3 (the hardened read guard: probes refused before any byte is read, the
        holdout paths and lab/ CSVs through open() included); no line written to val_access.log; every read of the
        run with its filter
    (j) look.py --cut 2022-01-01 with the spec AS IT STANDS (changes_in_look = K1, K2, K3 and synthesis A's five), in
        its own process: equal to the proofs' run on everything both contain, nothing logged; A5: its meta records
        the sha256 of every harness, lens and strategy file it imported (equal to the files, and to synthesis A's
        frozen hashes)
    (k) moving the CUT: look.py at CUT 2021-01-01 (every change) against the CUT 2022 run
    (l) review F10: the verdicts block, synthesis_B's declared criteria computed mechanically, every value equal to
        the run's own statistics and to synthesis_B's published figures
    (m) synthesis A's criteria V1-V5 (verdicts) and its report (res["synthesis_A"]) against synthesis A's published
        in-sample rehearsal of its own criteria, its changed sleeves, its frozen equal-swing factors and its
        portfolios; the check first ("stop and report") reported and gating synthesis A's verdicts

    env -u LOOK_DECLARED NUMBA_CACHE_DIR=/tmp/numba_validation_hi PYTHONDONTWRITEBYTECODE=1 \\
        python3 lab/r2/tracks/validation_hi/proofs.py

Writes lab/results/r2/validation_hi/proof_<x>_*.json, rehearsal_in_sample.json and proofs.json (index). Every
number in them is in sample (entries and exits before 2022-01-01).
"""
import copy
import hashlib
import io
import json
import math
import os
import pathlib
import sys
import tempfile
import time

if not os.environ.get("NUMBA_CACHE_DIR", "").startswith("/tmp/"):
    raise SystemExit("set NUMBA_CACHE_DIR to a directory under /tmp")
sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import vhi_guard as G  # noqa: E402

CUT = "2022-01-01"
LAB = G.LAB
OUT = os.path.join(LAB, "results", "r2", "validation_hi")
SPEC = os.path.join(HERE, "look_spec.json")


PROTOCOL = os.path.join(LAB, "PROTOCOL_V3.md")


def hi_lines():
    """Lines of val_access.log that mention the track (substring) and lines whose track is it (parsed)."""
    if not os.path.exists(G.VAL_LOG):
        return 0, 0
    with open(G.VAL_LOG) as f:
        sub = sum(1 for ln in f if "autopsy_HI_look" in ln)
    return sub, len(G.prior_look_lines())


LOG_BEFORE = hi_lines()
SPEC_SHA = hashlib.sha256(open(SPEC, "rb").read()).hexdigest()
cut = G.open_run(CUT, "proofs_in_sample")
assert not G.is_look(cut)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import vhi_book as B  # noqa: E402
import vhi_data as D  # noqa: E402
import vhi_lens as L  # noqa: E402
import vhi_run as RUN  # noqa: E402
import vhi_sleeves as SL  # noqa: E402
import vhi_stakes as ST  # noqa: E402
import vhi_verdicts as VD  # noqa: E402
from goldlab.sim import simulate  # noqa: E402

NY = "America/New_York"
K1_KEY = "brk72_24h_wd__ethusd+K1"

SYNTH_B = os.path.join(LAB, "results", "r2", "autopsy", "synthesis_B.json")
SYNTH_A = os.path.join(LAB, "results", "r2", "autopsy", "synthesis_A.json")
PAYOFF_TABLE = os.path.join(LAB, "results", "r2", "autopsy", "payoff", "variants_table.csv")
PAYOFF_TRIALS = os.path.join(LAB, "results", "r2", "autopsy", "payoff", "trials.jsonl")
ENGINE_CHECK = os.path.join(LAB, "results", "r2", "autopsy", "cluster", "engine_check.json")


# ------------------------------------------------------------------------------------------------- comparison
def decimals(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, np.integer)):
        return 0
    s = repr(float(v))
    if "e" in s or "E" in s or "inf" in s or "nan" in s:
        return 15
    return len(s.split(".")[1]) if "." in s else 0


def num(x):
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        return float(x)
    return x


def same(got, exp):
    got, exp = num(got), num(exp)
    if exp is None:
        return got is None
    if isinstance(exp, float) and math.isnan(exp):
        return got is None or (isinstance(got, float) and math.isnan(got))
    if isinstance(exp, bool):
        return bool(got) == exp
    if isinstance(exp, str):
        return str(got) == exp
    if isinstance(exp, (int, float)):
        if got is None or isinstance(got, (str, dict, list)) or (isinstance(got, float) and math.isnan(got)):
            return False
        if isinstance(exp, float) and math.isinf(exp):
            return isinstance(got, float) and math.isinf(got) and (got > 0) == (exp > 0)
        d = decimals(exp)
        tol = 1e-9 * max(1.0, abs(exp)) if d >= 12 else 0.5 * 10 ** (-d) * 1.000001 + 1e-12
        return abs(float(got) - float(exp)) <= tol
    if isinstance(exp, (list, tuple)):
        return isinstance(got, (list, tuple)) and len(got) == len(exp) and all(same(g, e) for g, e in zip(got, exp))
    return got == exp


def lookup(d, k):
    if not isinstance(d, dict):
        return None
    if k in d:
        return d[k]
    sk = str(k)
    if sk in d:
        return d[sk]
    if sk.lstrip("-").isdigit() and int(sk) in d:
        return d[int(sk)]
    return None


def compare(got, exp, prefix="", skip=()):
    rows = []
    if isinstance(exp, dict):
        for k, v in exp.items():
            if k in skip:
                continue
            rows += compare(lookup(got, k), v, f"{prefix}.{k}" if prefix else str(k), skip)
        return rows
    return [{"field": prefix, "expected": num(exp), "got": num(got), "ok": bool(same(got, exp))}]


def verdict(rows):
    bad = [r for r in rows if not r["ok"]]
    return {"checks": len(rows), "failed": len(bad), "ok": not bad, "failures": bad[:50]}


def jdump(obj, name):
    RUN.jdump(obj, os.path.join(OUT, name))


# ------------------------------------------------------------------------------------------------- (a)
def proof_a(res, sb):
    tg = sb["first_check_rule2"]["per_sleeve"]
    rows, table = [], {}
    for k in RUN.TEN_KEYS:
        o, t = res["official"][k], tg[k]
        exp = {"n_mine": t["n_mine"], "n_official": t["n_official"], "totR_mine_all": t["totR_mine"],
               "official_open_at_cut": t["official_exits_in_2022"], "rows_differing": 0, "reproduced": True,
               "mine_not_in_official_closed": t["official_exits_in_2022"], "those_open_at_frame_end_in_mine": True}
        if t["official_exits_in_2022"] == 0:
            exp["totR_official_closed_before_cut"] = t["totR_official"]
            exp["totR_mine_on_rows_closed_before_cut"] = t["totR_official"]
        r = compare(o, exp, k)
        # the only rows synthesis_B found different are the rows still open at the cut
        r.append({"field": f"{k}.synthesis_B_rows_differing_equals_rows_open_at_cut", "expected": t["rows_differing"],
                  "got": o["official_open_at_cut"], "ok": t["rows_differing"] == o["official_open_at_cut"]})
        r.append({"field": f"{k}.totals_on_rows_closed_before_cut_mine_equals_official",
                  "expected": o["totR_official_closed_before_cut"], "got": o["totR_mine_on_rows_closed_before_cut"],
                  "ok": abs(o["totR_official_closed_before_cut"] - o["totR_mine_on_rows_closed_before_cut"]) < 1e-6})
        rows += r
        table[k] = o
    v = verdict(rows)
    return {"what": "the ten official sleeves rebuilt from the cut frames (FP costs, one position, no refusal, as "
                    "r2/recalc.py) against results/r2/recalc/trades read with entry_time < CUT (counts) and "
                    "entry_time, exit_time < CUT (results); targets from synthesis_B first_check_rule2. The official "
                    "rows still open at the cut (one donch4h_stop, one orb_asia_2d_buf10 gold trade, closed in "
                    "2022 officially) are counted, never read; their in-frame twins close at the last bar.",
            "per_sleeve": table, **v, "rows": rows}


# ------------------------------------------------------------------------------------------------- (b)
def k1_got(info, main_stats, base_stats, k1ex, tb, tv):
    """A K1 run in the shape of synthesis_B sleeve_runs C1."""
    dg = info["change_diag"]
    return {"signals": dg["signals"], "refused": dg["refused_alone"],
            "refused_in_chain_extra": [info["base_refused_3spreads"], info["main_refused_3spreads"]],
            "folds": dg["folds"], "fit_for_2022": dg["fit_for_year_starting_at_cut"],
            "skipped_by_year": dg["skipped_by_year"],
            "base_2019_2021": base_stats["oof_2019_2021"], "var_2019_2021": main_stats["oof_2019_2021"],
            "base_window": base_stats["window"], "var_window": main_stats["window"],
            "base_by_year": B.by_year(tb), "var_by_year": B.by_year(tv),
            "baseline_trades_removed": k1ex["baseline_trades_removed"], "R_of_removed": k1ex["R_of_removed"],
            "new_trades": k1ex["new_trades"], "R_of_new": k1ex["R_of_new"]}


def same_trades(a, b):
    """Two chains identical trade for trade (entry / exit time, side, reason, oid, R to 1e-12)."""
    if len(a) != len(b):
        return False
    a, b = a.reset_index(drop=True), b.reset_index(drop=True)
    return bool((pd.DatetimeIndex(a.entry_time).as_unit("ns") == pd.DatetimeIndex(b.entry_time).as_unit("ns")).all()
                and (pd.DatetimeIndex(a.exit_time).as_unit("ns") == pd.DatetimeIndex(b.exit_time).as_unit("ns")).all()
                and (a.side.to_numpy() == b.side.to_numpy()).all() and (a.oid.to_numpy() == b.oid.to_numpy()).all()
                and (a.reason.astype(str).to_numpy() == b.reason.astype(str).to_numpy()).all()
                and np.allclose(a.R.to_numpy(float), b.R.to_numpy(float), rtol=0, atol=1e-12))


def proof_b(res, sb, k1x):
    key = K1_KEY
    S1 = L.synthesis_B()["S1"]
    out, rows = {}, []
    c1 = sb["sleeve_runs"]["C1_K1_riskbp_brk72_ethusd"]
    for mode in ("fp", "stress"):
        r = res["sleeves"][key]["runs"][f"{mode}/lab"]
        dg = r["info"]["change_diag"]
        tb = res["_trades"][(key, "base", mode, "lab")]
        tv = res["_trades"][(key, "main", mode, "lab")]
        got = k1_got(r["info"], r["main"], r["base"], r["k1"], tb, tv)
        exp = c1[mode]
        # F4: the declared FP labels in both cost modes. synthesis_B ran x1.5 with x1.5 labels: in x1.5 only the
        # label means E_lo / E_hi of the folds can differ (compared separately below); every other field must not.
        skip = ("sec",) + (("E_lo", "E_hi") if dg["labels_mode"] != mode else ())
        rr = compare(got, exp, mode, skip=skip)
        rr.append({"field": f"{mode}.labels_mode (declared: FP labels in both cost modes)", "expected": "fp",
                   "got": dg["labels_mode"], "ok": dg["labels_mode"] == "fp"})
        # the generalised walk-forward == synthesis_B's own s1_run.walk_forward on the same signal table
        s = res["_signals"][(key, mode)]
        sk0, folds0, f220 = S1.walk_forward(s.drop(columns=["skip"]))
        same_mask = bool((sk0 == s.skip.to_numpy()).all())
        same_folds = all(folds0[y] == dg["folds_full"][y] for y in folds0) and set(folds0) == set(dg["folds_full"])
        f_next = {kk: (round(v, 4) if isinstance(v, float) else v) for kk, v in f220.items()}
        rr.append({"field": f"{mode}.walk_forward_skip_mask_identical_to_s1_run", "expected": True, "got": same_mask,
                   "ok": same_mask})
        rr.append({"field": f"{mode}.walk_forward_folds_identical_to_s1_run (exact floats)", "expected": True,
                   "got": bool(same_folds), "ok": bool(same_folds)})
        rr.append({"field": f"{mode}.fit_for_2022_identical_to_s1_run", "expected": f_next,
                   "got": dg["fit_for_year_starting_at_cut"], "ok": f_next == dg["fit_for_year_starting_at_cut"]})
        # the declared-threshold check through a FOLD (the look's case: T(2022) is a fold at CUT 2026), exercised here
        # on the in-sample folds: T(2021) = 465.1178 declared, and a wrong value refused
        ck = SL.declared_T_check({"2021": 465.1178, "2020": 496.0}, dg["folds_full"], None, cut)
        rr.append({"field": f"{mode}.declared_T_check via a fold: 2021 = 465.1178 accepted, 2020 = 496.0 flagged",
                   "expected": [True, "fold", False], "got": [ck["2021"]["same_to_0.01bp"], ck["2021"]["fitted_from"],
                                                             ck["2020"]["same_to_0.01bp"]],
                   "ok": ck["2021"]["same_to_0.01bp"] and ck["2021"]["fitted_from"] == "fold" and not ck["2020"]["same_to_0.01bp"]})
        # F5 / A4: the declared 2022 fit is binding in the run itself (it did not raise: T within 0.01 bp, skip side
        # 'hi', n_train 2345)
        ck = dg.get("declared_T_check", {}).get("2022", {})
        want_b = "checked: T within 0.01 bp, same skip side, same n_train"
        rr.append({"field": f"{mode}.F5/A4 declared 2022 fit (T 478.284 bp, skip 'hi', n_train 2345) bound in the run: "
                            "fitted within 0.01 bp, same side, same count",
                   "expected": [True, "fit_for_year_starting_at_cut", "hi", 2345, want_b],
                   "got": [ck.get("same_to_0.01bp"), ck.get("fitted_from"), ck.get("fitted_skip_side"),
                           ck.get("fitted_n_train"), ck.get("binding")],
                   "ok": ck.get("same_to_0.01bp") is True and ck.get("same_skip_side") is True
                   and ck.get("same_n_train") is True and ck.get("binding") == want_b
                   and ck.get("fitted_skip_side") == "hi" and ck.get("fitted_n_train") == 2345,
                   "fitted": ck.get("fitted"), "abs_diff_bp": ck.get("abs_diff_bp")})
        rows += rr
        out[mode] = {"got": got, "declared_T_check": dg.get("declared_T_check"),
                     "labels_mode": dg["labels_mode"], "refused_alone_in_labels_mode": dg.get("refused_alone_in_labels_mode"),
                     "max_abs_riskbp_diff_run_vs_labels_mode": dg.get("max_abs_riskbp_diff_run_vs_labels_mode"),
                     "skipped_alone_vs_kept_alone_window": {kk: r["k1"][kk] for kk in ("skipped_signals_alone", "kept_signals_alone")}}
    # ---- F4: x1.5 with the declared FP labels against x1.5 with x1.5 labels (synthesis_B's run, rerun here)
    dfp = res["sleeves"][key]["runs"]["stress/lab"]["info"]["change_diag"]
    drun = k1x["info"]["change_diag"]
    # thresholds to 1e-9 bp (the riskbp of a signal in the two cost modes differ by float rounding of the mid only:
    # max_abs_riskbp_diff_run_vs_labels_mode); skip side and counts exact
    QF, QI = ("q_lo", "q_hi"), ("skip", "n_train", "n_test", "n_skipped")
    folds_same = set(dfp["folds"]) == set(drun["folds"]) and all(
        abs(dfp["folds_full"][y][q] - drun["folds_full"][y][q]) <= 1e-9 for y in dfp["folds_full"] for q in QF) and all(
        dfp["folds_full"][y][q] == drun["folds_full"][y][q] for y in dfp["folds_full"] for q in QI)
    t22_fp, t22_run = dfp["fit_for_year_starting_at_cut_full"]["q_hi"], drun["fit_for_year_starting_at_cut_full"]["q_hi"]
    chain_main = same_trades(res["_trades"][(key, "main", "stress", "lab")], k1x["main"])
    chain_base = same_trades(res["_trades"][(key, "base", "stress", "lab")], k1x["base"])
    mask_same = bool((res["_signals"][(key, "stress")].skip.to_numpy() == k1x["signals"].skip.to_numpy()).all())
    f4 = [{"field": "F4 x1.5: folds with FP labels == folds with x1.5 labels (q_lo, q_hi to 1e-9 bp; skip side, "
                    "n_train, n_test, n_skipped exact)", "expected": True, "got": bool(folds_same), "ok": bool(folds_same)},
          {"field": "F4 x1.5: T(2022) with FP labels == with x1.5 labels == 478.284 bp", "expected": [478.284, 478.284],
           "got": [round(t22_fp, 4), round(t22_run, 4)],
           "ok": abs(t22_fp - t22_run) <= 1e-9 and abs(t22_fp - 478.284) <= SL.T_TOL_BP, "exact": [t22_fp, t22_run]},
          {"field": "F4 x1.5: skip mask identical", "expected": True, "got": mask_same, "ok": mask_same},
          {"field": "F4 x1.5: the x1.5 chain (with the skip) identical trade for trade", "expected": True,
           "got": chain_main, "ok": chain_main},
          {"field": "F4 x1.5: the x1.5 base chain (without the skip) identical trade for trade", "expected": True,
           "got": chain_base, "ok": chain_base}]
    # the x1.5-labels run reproduces synthesis_B C1 x1.5 in every field (E_lo / E_hi included)
    got_run = k1_got(k1x["info"], k1x["main_stats"], k1x["base_stats"], k1x["k1"], k1x["base"], k1x["main"])
    f4 += compare(got_run, c1["stress"], "F4.x1.5_labels_run_vs_synthesis_B_C1_stress", skip=("sec",))
    # the label means: FP labels (declared) against x1.5 labels (synthesis_B): same signs, same skipped side
    em = {}
    for y in sorted(dfp["folds"]):
        em[str(y)] = {q: {"fp_labels": dfp["folds"][y][q], "x1.5_labels_synthesis_B": c1["stress"]["folds"][str(y)][q]}
                      for q in ("E_lo", "E_hi")}
    em["fit_for_2022"] = {q: {"fp_labels": dfp["fit_for_year_starting_at_cut"][q],
                              "x1.5_labels_synthesis_B": c1["stress"]["fit_for_2022"][q]} for q in ("E_lo", "E_hi")}
    signs = all(np.sign(v[q]["fp_labels"]) == np.sign(v[q]["x1.5_labels_synthesis_B"]) for v in em.values() for q in v)
    f4.append({"field": "F4 x1.5: E_lo / E_hi with FP labels have the signs of synthesis_B's x1.5-label values (the "
                        "only fields that change)", "expected": True, "got": bool(signs), "ok": bool(signs)})
    rows += f4
    out["F4_labels"] = {"declared": "every signal taken alone with FP costs, in both cost modes (labels_mode 'fp')",
                        "x1.5_folds_identical": bool(folds_same), "T_2022_fp_labels": t22_fp, "T_2022_x1.5_labels": t22_run,
                        "x1.5_chain_identical": chain_main, "x1.5_base_chain_identical": chain_base,
                        "x1.5_E_values": em,
                        "x1.5_2019_2021_fp_labels": {"base": res["sleeves"][key]["runs"]["stress/lab"]["base"]["oof_2019_2021"],
                                                     "var": res["sleeves"][key]["runs"]["stress/lab"]["main"]["oof_2019_2021"]}}
    # ---- F5: the declared T is binding (bind_declared_T on this run's folds; and the run itself with a wrong value)
    dgf = res["sleeves"][key]["runs"]["fp/lab"]["info"]["change_diag"]
    folds, fnext = dgf["folds_full"], dgf["fit_for_year_starting_at_cut_full"]
    f5, f5_out = [], {}
    for name, dT, want in (("T(2022) = 478.284 (the spec)", {"2022": 478.284}, True),
                           ("T(2022) = 478.28 (synthesis_B's text)", {"2022": 478.28}, True),
                           ("T(2022) = 478.3 (0.016 bp off)", {"2022": 478.3}, False),
                           ("T(2021) = 465.1178 through a fold", {"2021": 465.1178}, True),
                           ("T(2020) = 496.0 through a fold (0.75 bp off)", {"2020": 496.0}, False),
                           ("T(2018) = 500 (no fit for 2018: a declared year without a fit)", {"2018": 500.0}, False),
                           ("T(2023) = 480 (a later year: not checkable at CUT 2022, recorded)", {"2023": 480.0}, True),
                           ("A4 2022 = {q_hi 478.284, skip 'hi', n_train 2345} (the spec)",
                            {"2022": {"q_hi": 478.284, "skip": "hi", "n_train": 2345}}, True),
                           ("A4 2022 with skip 'lo' (a side flip with the same T)",
                            {"2022": {"q_hi": 478.284, "skip": "lo", "n_train": 2345}}, False),
                           ("A4 2022 with skip None (a fit that would skip nothing)",
                            {"2022": {"q_hi": 478.284, "skip": None, "n_train": 2345}}, False),
                           ("A4 2022 with n_train 2344", {"2022": {"q_hi": 478.284, "skip": "hi", "n_train": 2344}}, False),
                           ("A4 2022 with n_train 2346", {"2022": {"q_hi": 478.284, "skip": "hi", "n_train": 2346}}, False),
                           ("A4 2022 with T 0.016 bp off, right side and count",
                            {"2022": {"q_hi": 478.3, "skip": "hi", "n_train": 2345}}, False),
                           ("A4 2021 = {465.1178, 'hi', 1703} through a fold",
                            {"2021": {"q_hi": 465.1178, "skip": "hi", "n_train": 1703}}, True),
                           ("A4 2021 through a fold with n_train 1702",
                            {"2021": {"q_hi": 465.1178, "skip": "hi", "n_train": 1702}}, False)):
        try:
            ck = SL.bind_declared_T(dT, folds, fnext, cut)
            accepted, why = True, ck
        except SL.DeclaredThresholdError as e:
            accepted, why = False, str(e)
        f5.append({"field": f"F5 bind_declared_T: {name} -> {'accepted' if want else 'raises'}", "expected": want,
                   "got": accepted, "ok": accepted == want})
        f5_out[name] = why
    # A4, the look's form (require_full, set by change_k1 when the CUT is a look): every declared year carries the three
    spec_dT = next(s for s in res["_spec"]["sleeves"] if s["key"] == K1_KEY)["change"]["declared_T"]
    for name, dT, want in (("A4 the look's form: the spec's declared year accepted", spec_dT, True),
                           ("A4 the look's form: a threshold alone is refused", {"2022": 478.284}, False),
                           ("A4 the look's form: q_hi and skip without n_train refused",
                            {"2022": {"q_hi": 478.284, "skip": "hi"}}, False)):
        try:
            SL.bind_declared_T(dT, folds, fnext, cut, require_full=True)
            accepted, why = True, None
        except SL.DeclaredThresholdError as e:
            accepted, why = False, str(e)
        f5.append({"field": f"A4 bind_declared_T(require_full=True): {name}", "expected": want, "got": accepted,
                   "ok": accepted == want})
        f5_out[name] = why
    f5.append({"field": "A4 the spec declares 2022 with q_hi 478.284, skip 'hi' and n_train 2345", "expected":
               {"q_hi": 478.284, "skip": "hi", "n_train": 2345}, "got": spec_dT.get("2022"),
               "ok": spec_dT.get("2022") == {"q_hi": 478.284, "skip": "hi", "n_train": 2345}})
    f5.append({"field": "F5 the run itself with declared T(2022) = 478.3: SL.run raises DeclaredThresholdError before "
                        "any trade", "expected": True, "got": k1x["bad_declared_raised"], "ok": k1x["bad_declared_raised"],
               "message": k1x["bad_declared_message"]})
    for kk, what in (("bad_side", "skip side 'lo'"), ("bad_n_train", "n_train 2344")):
        f5.append({"field": f"A4 the run itself with the declared 2022 fit's {what} (T right): SL.run raises "
                            "DeclaredThresholdError before any trade", "expected": True, "got": k1x[f"{kk}_raised"],
                   "ok": k1x[f"{kk}_raised"], "message": k1x[f"{kk}_message"]})
    rows += f5
    out["F5_binding"] = f5_out
    fp = out["fp"]["got"]
    headline = {"T_2019_2020_2021_bp": [round(fp["folds"][y]["q_hi"], 1) for y in (2019, 2020, 2021)],
                "T_2022_bp": round(fp["fit_for_2022"]["q_hi"], 1),
                "2019_2021_fp": f"{fp['base_2019_2021']['n']} -> {fp['var_2019_2021']['n']} trades, "
                                f"{fp['base_2019_2021']['total']:+.1f} -> {fp['var_2019_2021']['total']:+.1f} R"}
    task = [{"field": "task: thresholds 505.9 / 496.7 / 465.1 bp", "expected": [505.9, 496.7, 465.1],
             "got": headline["T_2019_2020_2021_bp"], "ok": headline["T_2019_2020_2021_bp"] == [505.9, 496.7, 465.1]},
            {"field": "task: 2022 value 478.3 bp", "expected": 478.3, "got": headline["T_2022_bp"],
             "ok": headline["T_2022_bp"] == 478.3},
            {"field": "task: 2019-2021 395 -> 304 trades, +49.1 -> +63.9 R (FP)",
             "expected": [395, 304, 49.1, 63.9],
             "got": [fp["base_2019_2021"]["n"], fp["var_2019_2021"]["n"], round(fp["base_2019_2021"]["total"], 1),
                     round(fp["var_2019_2021"]["total"], 1)],
             "ok": [fp["base_2019_2021"]["n"], fp["var_2019_2021"]["n"], round(fp["base_2019_2021"]["total"], 1),
                    round(fp["var_2019_2021"]["total"], 1)] == [395, 304, 49.1, 63.9]}]
    rows = task + rows
    return {"what": "K1 (brk72_24h_wd ethusd, riskbp skip refitted every 1 January) against synthesis_B sleeve_runs "
                    "C1 (fp and x1.5), every field; the harness's walk-forward (any CUT) against s1_run.walk_forward",
            "headline": headline, "detail": out, **verdict(rows), "rows": rows}


# ------------------------------------------------------------------------------------------------- (c)
def proof_c(res, sb):
    rows, out = [], {}
    for key, tg, task in (("orb_asia_2d_buf10__ethusd", "N1_K2_orb_ethusd", (344, 155.5)),
                          ("orb_asia_2d_buf10__btcusd", "N2_K3_orb_btcusd", (375, 194.3))):
        for mode in ("fp", "stress"):
            r = res["sleeves"][key]["runs"][f"{mode}/lab"]
            got = {"orders": r["info"]["orders"], "refused_3spreads": r["info"]["main_refused_3spreads"],
                   "boundary_dropped": r["info"]["main_boundary_dropped"], "window": r["main"]["window"],
                   "by_year": r["main"]["by_year"], "early": r["main"]["before_window"]}
            rows += compare(got, sb["sleeve_runs"][tg][mode], f"{key}.{mode}", skip=("sec",))
            out[f"{key}.{mode}"] = got
        w = out[f"{key}.fp"]["window"]
        rows.insert(0, {"field": f"task: {key} FP 2018-02..2021-12 {task[0]} trades {task[1]:+.1f} R",
                        "expected": list(task), "got": [w["n"], round(w["total"], 1)],
                        "ok": [w["n"], round(w["total"], 1)] == list(task)})
    return {"what": "K2 and K3: the frozen gold orb_asia_2d_buf10 on ethusd and btcusd as new sleeves, against "
                    "synthesis_B sleeve_runs N1 / N2 (fp and x1.5; the trade still open at the end of 2021 dropped)",
            "detail": out, **verdict(rows), "rows": rows}


# ------------------------------------------------------------------------------------------------- (d)
PAYOFF = [("F1_brk_ridge_filter:ethusd", "H2", "F1_brk_ridge_filter__ethusd+H2", "F1_brk_ridge_filter__ethusd@payoff"),
          ("ocm4:us100", "T1", "ocm4__us100+T1", "ocm4__us100@payoff"),
          ("donch4h_stop:xauusd", "S0.75r", "donch4h_stop__xauusd+S0.75r", "donch4h_stop__xauusd@payoff"),
          ("nq_btc_follow:btcusd", "T1", "nq_btc_follow__btcusd+T1", "nq_btc_follow__btcusd@payoff"),
          ("noise30:us100", "S0.25", "noise30__us100+S0.25", "noise30__us100@payoff"),
          ("brk72_24h_wd:btcusd", "S0.75r", "brk72_24h_wd__btcusd+S0.75r", "brk72_24h_wd__btcusd@payoff"),
          ("orb_asia_2d_buf10:xauusd", "S0.75r", "orb_asia_2d_buf10__xauusd+S0.75r", "orb_asia_2d_buf10__xauusd@payoff")]
STAT_COLS = {"n": "n", "win_rate": "win_rate", "exp_R": "exp_R", "avg_win_R": "avg_win_R", "avg_loss_R": "avg_loss_R",
             "pf": "pf", "total_R": "total_R", "t_stat": "t_stat", "max_dd_R": "max_dd_R", "worst_R": "worst_R",
             "best_R": "best_R", "avg_hold_h": "avg_hold_h", "max_hold_h": "max_hold_h"}


def r_per_bp(t, W):
    a, b = W["eval"]
    w = t[(t.entry_time >= a) & (t.entry_time < b)]
    return float((1e-4 * w.entry / w.risk).mean())


def table_row(res, key, W, ref_key=None):
    rf, rs = res["sleeves"][key]["runs"]["fp/lab"], res["sleeves"][key]["runs"]["stress/lab"]
    g = {f"fp_{c}": rf["main"]["payoff_stats"].get(s) for c, s in STAT_COLS.items()}
    g.update({"fp_sharpe_trade": rf["main"].get("sharpe_trade"), "stress_exp_R": rs["main"]["payoff_stats"].get("exp_R"),
              "stress_total_R": rs["main"]["payoff_stats"].get("total_R"),
              "stress_sharpe_trade": rs["main"].get("sharpe_trade"), "fp_bps_trade": rf["main"].get("bps_trade")})
    if ref_key is not None:
        g.update({"early_exp_R": rf["main"]["payoff_before_window"].get("exp_R"),
                  "early_n": rf["main"]["payoff_before_window"].get("n"),
                  "refused_fp": rf["info"]["change_diag"]["refused_orders"],
                  "refused_stress": rs["info"]["change_diag"]["refused_orders"]})
        rr = res["sleeves"][ref_key]["runs"]["fp/lab"]
        yv, yr = rf["main"]["payoff_by_year"], rr["main"]["payoff_by_year"]
        g["years_better"] = f"{sum(1 for y in (2018, 2019, 2020, 2021) if y in yv and y in yr and yv[y]['exp_R'] > yr[y]['exp_R'])}/4"
        tv = res["_trades"][(key, "main", "fp", "lab")]
        tr = res["_trades"][(ref_key, "main", "fp", "lab")]
        a, b = W["eval"]
        wv, wr = tv[(tv.entry_time >= a) & (tv.entry_time < b)], tr[(tr.entry_time >= a) & (tr.entry_time < b)]
        dv = float(wv.R.mean()) - float(wr.R.mean())
        dc = r_per_bp(tv, W) - r_per_bp(tr, W)
        g["cost_tol_bp_fp"] = 0.0 if dv <= 0 else (float(dv / dc) if dc > 1e-12 else float("inf"))
    return g


def proof_d(res):
    tab = pd.read_csv(PAYOFF_TABLE)
    W = res["_W"]
    trials = {}
    for ln in open(PAYOFF_TRIALS):
        d = json.loads(ln)
        trials[(d["sleeve"], d["variant"]["id"])] = d
    rows, out = [], {}
    for sl, vid, key, ref in PAYOFF:
        exp_v = tab[(tab.sleeve == sl) & (tab.variant == vid)].iloc[0].to_dict()
        exp_r = tab[(tab.sleeve == sl) & (tab.variant == "reference")].iloc[0].to_dict()
        gv, gr = table_row(res, key, W, ref), table_row(res, ref, W)
        keep = [c for c in gv if c in exp_v]
        rows += compare(gv, {c: exp_v[c] for c in keep}, f"{sl}.{vid}")
        keep_r = [c for c in gr if c in exp_r and not (isinstance(exp_r[c], float) and math.isnan(exp_r[c]))]
        rows += compare(gr, {c: exp_r[c] for c in keep_r}, f"{sl}.reference")
        # by year (fp, common window) and the H extension counts, against the lens's trials.jsonl line
        tl = trials[(sl, vid)]
        rf = res["sleeves"][key]["runs"]["fp/lab"]
        rows += compare(rf["main"]["payoff_by_year"], tl["fp"]["by_year"], f"{sl}.{vid}.by_year_fp")
        rows += compare({"censored": rf["info"]["main_boundary_dropped"]}, {"censored": tl["fp"]["censored"]},
                        f"{sl}.{vid}.fp")
        if vid.startswith("H"):
            rows += compare({"extended_orders": rf["info"]["change_diag"]["extended_orders"],
                             "extended_trades": rf["info"]["change_diag"].get("extended_trades")},
                            {"extended_orders": tl["fp"]["extended_orders"], "extended_trades": tl["fp"]["extended_trades"]},
                            f"{sl}.{vid}.fp")
        out[f"{sl}.{vid}"] = {"variant": gv, "reference": gr}
    # the harness's censoring (any symbol, any CUT) is the payoff lens's own on every in-sample lab run
    diff = {f"{k}/{r}": v["info"].get("main_payoff_rule_differs", 0)
            for k, s in res["sleeves"].items() if s["spec"].get("convention") == "payoff"
            for r, v in s["runs"].items()}
    lab_diff = sum(v for kk, v in diff.items() if kk.endswith("/lab"))
    rows.append({"field": "censoring: harness rule == payoff lens rule on every in-sample lab run (trades differing)",
                 "expected": 0, "got": lab_diff, "ok": lab_diff == 0})
    out["censoring_rule_differences_by_run"] = diff
    # F6: the '<sleeve>@payoff' references carry the payoff lens's 3-spread refusal ("refuse": true), and the run's
    # diagnostic compares each with its sB sleeve trade by trade inside the window
    spec_refs = {s["key"]: s for s in res["_spec"]["sleeves"] if s["key"].endswith("@payoff")}
    pr = res["payoff_reference_vs_sB"]
    for _, _, _, ref in PAYOFF:
        rows.append({"field": f"F6 {ref}: the reference carries the 3-spread refusal (spec 'refuse': true, applied in "
                              "every run)", "expected": True,
                     "got": bool(spec_refs[ref].get("refuse")) and all("reference_refused_orders" in v["info"]
                                                                       for v in res["sleeves"][ref]["runs"].values()),
                     "ok": bool(spec_refs[ref].get("refuse")) and all("reference_refused_orders" in v["info"]
                                                                      for v in res["sleeves"][ref]["runs"].values())})
        for r in ("fp/lab", "stress/lab"):
            v = pr[ref][r]
            rows.append({"field": f"F6 {ref} {r}: identical to the sB sleeve {ref[:-7]} trade by trade inside the window",
                         "expected": True, "got": v["identical"], "ok": v["identical"],
                         "n": [v["n_payoff_reference"], v["n_sB"]], "only": [v["only_in_payoff_reference"], v["only_in_sB"]],
                         "matched_differing": v["matched_differing"]})
    out["F6_payoff_reference_vs_sB"] = pr
    out["F6_reference_refused_orders"] = {ref: {r: v["info"].get("reference_refused_orders")
                                                for r, v in res["sleeves"][ref]["runs"].items()} for _, _, _, ref in PAYOFF}
    out["F6_live_differences_reported"] = {ref: {r: {k: v[k] for k in ("identical", "only_in_payoff_reference",
                                                                       "only_in_sB", "matched_differing")}
                                                 for r, v in pr[ref].items() if r.endswith("/live")} for _, _, _, ref in PAYOFF}
    return {"what": "the seven payoff variants in play (and their references) against "
                    "results/r2/autopsy/payoff/variants_table.csv (fp and x1.5 columns, common window "
                    "2018-02-01..2021-12-31, earlier entries, refusals, years better) and the lens's trials.jsonl "
                    "(by year, censored trades, H extensions); review F6: the references with the payoff lens's "
                    "3-spread refusal, identical to the sB sleeves trade by trade inside the window (lab, fp and x1.5; "
                    "live reported)",
            "detail": out, **verdict(rows), "rows": rows}


# ------------------------------------------------------------------------------------------------- (e)
NAME_MAP = {"brk72_24h_wd__ethusd+K1": "brk72_24h_wd__ethusd", "orb_asia_2d_buf10__ethusd": "NEW_orb_asia_2d_buf10__ethusd",
            "orb_asia_2d_buf10__btcusd": "NEW_orb_asia_2d_buf10__btcusd"}


def proof_e(res, sb):
    S2 = L.synthesis_B()["S2"]
    rows, out = [], {}
    W = res["_W"]
    a, b = W["eval"]
    for p in ("P0", "P1", "P2"):
        for mode in ("fp", "stress"):
            mt = dict(res["portfolios"][p][f"{mode}/lab/sum"])
            mt["by_sleeve"] = {NAME_MAP.get(k, k): v for k, v in mt["by_sleeve"].items()}
            exp = sb["portfolio"]["results"][mode][p]
            rows += compare(mt, exp, f"{p}.{mode}")
            # synthesis_B's own metrics function on the harness's book
            d = res["_books"][(p, mode, "lab", "sum")]
            assert (d.m == 1.0).all()
            bk = pd.DataFrame({"sleeve": d.sleeve.map(lambda k: NAME_MAP.get(k, k)), "entry_time": d.entry_time,
                               "exit_time": d.exit_time, "R": d.Rm})
            theirs = S2.metrics(bk)
            mine = dict(res["portfolios"][p][f"{mode}/lab/sum"])
            mine["by_sleeve"] = {NAME_MAP.get(k, k): v for k, v in mine["by_sleeve"].items()}
            keys = [k for k in theirs if k in mine]
            rows += compare({k: mine[k] for k in keys}, {k: theirs[k] for k in keys}, f"{p}.{mode}.vs_s2_portfolio_metrics")
            out[f"{p}.{mode}"] = {k: mt[k] for k in ("n", "exp", "total", "worst_week_R", "max_dd_R_trade_by_trade",
                                                     "max_dd_R_weekly", "longest_losing_run_weeks", "week_mean_over_sd",
                                                     "weekly_sharpe_annualised", "winning_weeks_pct")}
    return {"what": "the synthesis_B portfolios P0 (ten unchanged), P1 (ten with K1), P2 (ten with K1 + K2 + K3), "
                    "fp and x1.5, plain sum at 1 R per trade, entries 2018-02-01..2021-12-31, server weeks: every "
                    "field of synthesis_B.json portfolio.results; and the harness's metrics equal to synthesis_B's "
                    "own s2_portfolio.metrics (imported) on the same book",
            "headline": out, **verdict(rows), "rows": rows}


# ------------------------------------------------------------------------------------------------- (f)
MARKETS = ("us100", "xauusd", "btcusd", "ethusd")
FAMILY = {"us100": 0, "xauusd": 1, "btcusd": 2, "ethusd": 2}


def engine_on_book(d_all):
    """The cluster lens's run_engine (imported) on a harness book (code 0: reference guard, caps 6 / 2)."""
    E = L.cluster_engine()
    d = d_all.copy()
    d["_o"] = np.arange(len(d))
    d = d.sort_values(["entry_time", "tie"], kind="stable").reset_index(drop=True)
    ties = sorted(d.tie.unique())
    sl = d.tie.map({k: i for i, k in enumerate(ties)}).to_numpy(np.int64)
    mk = d.sym.map({m: i for i, m in enumerate(MARKETS)}).to_numpy(np.int64)
    fam = d.sym.map(FAMILY).to_numpy(np.int64)
    dy_in, dy_out = B.server_day(d.entry_time), B.server_day(d.exit_time)
    wk_in, wk_out = (dy_in + 3) // 7, (dy_out + 3) // 7
    dmin, wmin = int(min(dy_in.min(), dy_out.min())), int(min(wk_in.min(), wk_out.min()))
    t_in, t_out = d.entry_time.astype("int64").to_numpy(), d.exit_time.astype("int64").to_numpy()
    m, why = E.run_engine(t_in, t_out, d.R.to_numpy(float), sl, mk, fam, d.side.to_numpy(np.int64),
                          (dy_in - dmin).astype(np.int64), (dy_out - dmin).astype(np.int64),
                          (wk_in - wmin).astype(np.int64), (wk_out - wmin).astype(np.int64), (d.m > 0).to_numpy(),
                          np.argsort(t_out, kind="stable"), len(ties), int(max(dy_in.max(), dy_out.max()) - dmin + 1),
                          int(max(wk_in.max(), wk_out.max()) - wmin + 1), 0, 0.0, 0.0, 6, 2)
    back = np.zeros(len(d))
    back[d["_o"].to_numpy()] = m
    return back


def proof_f(res):
    rows, out = [], {}
    # 1) the harness's capped account == run_engine on the harness's own books (P0, P2; fp and x1.5)
    for p in ("P0", "P2"):
        for mode in ("fp", "stress"):
            pp = RUN.resolve_portfolios(json.load(open(SPEC)))[p]
            _, _, d_all = RUN.portfolio(pp, res["_trades"], res["_signals"], res["_meta"], mode, "lab", ["capped"],
                                        res["_W"], cut)
            mine, why = B.capped_stakes(d_all)
            eng = engine_on_book(d_all)
            ok = bool(((mine > 0) == (eng > 0)).all())
            a, b = res["_W"]["eval"]
            sel = ((d_all.entry_time >= a) & (d_all.entry_time < b)).to_numpy()
            out[f"{p}.{mode}"] = {"offered_whole_frame": int(len(d_all)), "taken_whole_frame": int((mine > 0).sum()),
                                  "taken_window": int(((mine > 0) & sel).sum()),
                                  "total_R_window": round(float((d_all.R.to_numpy() * mine)[sel].sum()), 3),
                                  "cap_skips_window": int(((why == 2) & sel).sum())}
            rows.append({"field": f"{p}.{mode}: capped account == cluster run_engine (same trades taken)",
                         "expected": True, "got": ok, "ok": ok})
    # 2) on the cluster lens's own trades: its engine_check.json, and account.py on the common window
    ec = json.load(open(ENGINE_CHECK))
    cd = os.path.join(L.AUTOPSY, "cluster")
    cc = L.load_file(os.path.join(cd, "common.py"), "vhi_cluster_common")
    bk = L.load_file(os.path.join(cd, "book.py"), "vhi_cluster_book", {"common": cc, "engine": L.cluster_engine()})

    def read_my_trades_filtered(name, sym, mode):
        # the cluster lens's own reader (common.read_my_trades), with the row filter entry_time < CUT in the read
        # (the guard refuses a trades file read without it); in memory only, the lens's file is untouched
        return D.trades_file(os.path.join(cc.TRADES_DIR, f"{name}__{sym}__{mode}.parquet"))

    cc.read_my_trades = read_my_trades_filtered
    acc = L.stake_account()["A"]
    for mode in ("fp", "stress"):
        d = bk.build(mode)
        a_ = bk.arrays(d)
        m_e, w_e = bk.run(a_, 0, caps=True)
        st = bk.stats(d, m_e)
        dd = pd.DataFrame({"sleeve": d.sleeve, "sym": d.sym, "tie": d.sleeve, "side": d.side, "entry_time": d.t_in,
                           "exit_time": d.t_out, "R": d.R, "m": d.ok_broker.astype(float)})
        mine, why = B.capped_stakes(dd)
        sel = (d.t_in >= cc.COMMON_START).to_numpy()
        got = {"n_taken": int(((mine > 0) & sel).sum()), "total_R": round(float((d.R.to_numpy() * mine)[sel].sum()), 3)}
        rows += compare(got, {"n_taken": ec[mode]["capped_common"]["n_taken"], "total_R": ec[mode]["capped_common"]["total_R"]},
                        f"cluster_trades.{mode}.capped_common")
        rows += compare({"capped_skips_common": int(((why == 2) & sel).sum())},
                        {"capped_skips_common": ec[mode]["capped_skips_common"]}, f"cluster_trades.{mode}")
        same_eng = bool(((mine > 0) == (m_e > 0)).all())
        rows.append({"field": f"cluster_trades.{mode}: harness capped account == cluster engine trade by trade",
                     "expected": True, "got": same_eng, "ok": same_eng})
        dc = d[sel].reset_index(drop=True).copy()
        dc["pnl"] = dc.R * dc.risk
        fr = acc.frame(d=dc[["sleeve", "sym", "fam", "t_in", "t_out", "entry", "risk", "pnl", "R"]])
        ac = acc.account({}, start=1e9, base_pct=1.0, d=fr, compound=False, kill_dd=0.99)
        dd2 = pd.DataFrame({"sleeve": dc.sleeve, "sym": dc.sym, "tie": dc.sleeve, "side": dc.side,
                            "entry_time": dc.t_in, "exit_time": dc.t_out, "R": dc.R, "m": 1.0})
        m2, w2 = B.capped_stakes(dd2)
        rows += compare({"n_taken": int((m2 > 0).sum()), "position_cap_skips": int((w2 == 2).sum())},
                        {"n_taken": ac["n_taken"], "position_cap_skips": ac["skipped"]["position_cap"]},
                        f"account_py.{mode}.common_window")
        out[f"cluster_trades.{mode}"] = {"engine_check": ec[mode]["capped_common"], "harness": got,
                                         "account_py": {"n_taken": ac["n_taken"],
                                                        "position_cap_skips": ac["skipped"]["position_cap"]}}
    return {"what": "the capped account (6 positions, 2 per market; stake 0 takes no slot): identical to the cluster "
                    "lens's run_engine on the harness's own P0 / P2 books, and on the cluster lens's own trades it "
                    "reproduces engine_check.json and r2/tracks/stake/account.py (1e9 EUR account, no lot / margin "
                    "effect)", "detail": out, **verdict(rows), "rows": rows}


# ------------------------------------------------------------------------------------------------- (g), (h) frames pass
def friday_decision_probe(m1, sym):
    """F7 on synthetic market orders of the frame: one filled in the last bar of a Friday at or after 16:50 New York
    whose next bar is the Sunday reopen (decided at its close, inside the block; delayed entry at the reopen, outside
    it), one filled at Friday 16:40 (decided and entered before 16:50). With 'entry_bar' only the first is entered at
    the reopen; with the declared 'decision_and_entry' it is not taken; the second is taken in both."""
    idx = m1.index
    ny = idx.tz_convert(NY).tz_localize(None)
    dow, mins = ny.dayofweek.to_numpy(), (ny.hour * 60 + ny.minute).to_numpy()
    gap = (idx[1:] - idx[:-1]) > pd.Timedelta(hours=24)
    cand = np.flatnonzero((dow[:-1] == 4) & (mins[:-1] >= 16 * 60 + 50) & gap)
    cand = cand[ny[cand].year == 2021]
    if not len(cand):
        return None
    i_late = int(cand[0])
    day = ny[i_late].normalize()
    i_early = int(np.searchsorted(idx.values, (pd.Timestamp(day) + pd.Timedelta(hours=16, minutes=40)).tz_localize(NY)
                                  .tz_convert("UTC").tz_localize(None).to_datetime64().astype(idx.values.dtype)))
    o = pd.DataFrame({"entry_i": np.array([i_late, i_early], np.int64), "side": np.array([1, 1], np.int64),
                      "etype": np.array([0, 0], np.int64), "level": np.nan, "expiry_i": np.array([-1, -1], np.int64),
                      "stop": np.nan, "stop_dist": float(10 * (m1["ao"].iloc[i_late] - m1["bo"].iloc[i_late]) + 1.0),
                      "exit_i": np.array([-1, -1], np.int64), "oid": np.array([0, 1], np.int64)})
    out = {"sym": sym, "late_fill_bar": str(idx[i_late]), "late_fill_bar_ny": str(ny[i_late]),
           "late_decision_instant_ny": str(ny[i_late] + pd.Timedelta(minutes=1)),
           "late_next_bar_ny": str(ny[i_late + 1]), "early_fill_bar_ny": str(ny[i_early])}
    for fb_mode in ("entry_bar", "decision_and_entry"):
        x, li = SL.live_orders(o, m1, sym, "fp", friday_block=fb_mode)
        out[fb_mode] = {"taken_oids": x.oid.tolist(), "entry_bar_ny": [str(ny[i]) for i in x.entry_i.to_numpy()],
                        "info": li}
    out["ok"] = (out["entry_bar"]["taken_oids"] == [0, 1] and out["decision_and_entry"]["taken_oids"] == [1]
                 and out["decision_and_entry"]["info"]["blocked_decision_instant_only"] == 1)
    return out


def frames_pass(res, sb):
    """One more pass over the four frames: the live-chain identity, K2 live against the verifier, signal tables for
    the stake checks; on ethusd the K1 reruns of proof b (x1.5 with x1.5 labels; a wrong declared T) and the Friday
    decision-instant probe."""
    rows_g, out_g = [], {}
    leader = None
    signals = {}
    k1x = {}
    reg = L.registry()
    for sym in RUN.SYM_ORDER:
        m1 = D.frame(sym)
        if sym == "us100":
            leader = D.leader_series(m1)
        for name, s in L.TEN:
            if s != sym:
                continue
            O = SL.build_orders(name, m1, leader)
            costs = SL.mode_costs(sym, "fp")
            t_off = simulate(m1, O, sym=sym, costs=costs, no_overlap=True)
            x = O.copy()
            x["act_i"] = x.entry_i.to_numpy(np.int64)
            t_lc = SL.live_chain(m1, x, sym, costs)
            cols = ["entry_time", "exit_time", "side", "reason"]
            ok = len(t_off) == len(t_lc) and all((t_off[c].to_numpy() == t_lc[c].to_numpy()).all() for c in cols) \
                and bool(np.allclose(t_off.R.to_numpy(), t_lc.R.to_numpy(), rtol=0, atol=1e-12))
            rows_g.append({"field": f"{name}__{sym}: live_chain with no delay and no Friday close == official chain",
                           "expected": True, "got": bool(ok), "ok": bool(ok)})
            if name == "brk72_24h_wd" and sym == "ethusd":
                signals[("brk72_24h_wd__ethusd", "fp")] = ST.generic_signal_table(
                    m1, O, sym, "fp", lambda oo: simulate(m1, oo, sym=sym, costs=costs, no_overlap=False))
        if sym == "ethusd":
            # proof b (F4): K1 in x1.5 with x1.5 labels (synthesis_B's own run) on the same frame
            k1spec = copy.deepcopy(next(s for s in res["_spec"]["sleeves"] if s["key"] == K1_KEY))
            k1spec["change"]["labels_mode"] = "run"
            o_, i_ = SL.run(k1spec, m1, "stress", "lab", keep_signals=True)
            W = res["_W"]
            k1x = {"info": i_, "main": o_["main"], "base": o_["base"], "signals": o_["signals"],
                   "main_stats": RUN.sleeve_stats(o_["main"], W), "base_stats": RUN.sleeve_stats(o_["base"], W),
                   "k1": RUN.k1_extras(o_["signals"], o_["main"], o_["base"], W)}
            # proof b (F5): the run itself with a declared T(2022) 0.016 bp off must raise
            bad = copy.deepcopy(k1spec)
            bad["change"]["labels_mode"] = "fp"
            bad["change"]["declared_T"] = {"2022": 478.3}
            try:
                SL.run(bad, m1, "fp", "lab")
                k1x.update(bad_declared_raised=False, bad_declared_message=None)
            except SL.DeclaredThresholdError as e:
                k1x.update(bad_declared_raised=True, bad_declared_message=str(e))
            # A4: the same run with the right T but another skip side, or another number of training signals
            for kk, dT in (("bad_side", {"2022": {"q_hi": 478.284, "skip": "lo", "n_train": 2345}}),
                           ("bad_n_train", {"2022": {"q_hi": 478.284, "skip": "hi", "n_train": 2344}})):
                bad = copy.deepcopy(k1spec)
                bad["change"]["labels_mode"] = "fp"
                bad["change"]["declared_T"] = dT
                try:
                    SL.run(bad, m1, "fp", "lab")
                    k1x.update({f"{kk}_raised": False, f"{kk}_message": None})
                except SL.DeclaredThresholdError as e:
                    k1x.update({f"{kk}_raised": True, f"{kk}_message": str(e)})
            # F7: the Friday block on the decision instant, on synthetic orders of this frame
            fpb = friday_decision_probe(m1, sym)
            out_g["F7_friday_decision_instant_probe"] = fpb
            rows_g.append({"field": "F7: an order filled in the last Friday bar after 16:50 New York (decided inside the "
                                    "block, delayed entry at the Sunday reopen) is entered at the reopen with "
                                    "'entry_bar' and not taken with the declared 'decision_and_entry'; one filled at "
                                    "16:40 is taken in both", "expected": True, "got": bool(fpb and fpb["ok"]),
                           "ok": bool(fpb and fpb["ok"])})
            # K2 run as the live program would, the verifier's way (one-position test at the delayed entry bar,
            # trade still open at the end of 2021 kept) and the harness's way (rule's test, open trade dropped)
            for mode, exp_n, exp_R in (("fp", 392, 142.1), ("stress", 392, 127.9)):
                mk = SL.mode_frame(m1, mode)
                costs = SL.mode_costs(sym, mode)
                O = SL.build_orders("orb_asia_2d_buf10", mk)
                x, li = SL.live_orders(O, mk, sym, mode)
                bad = SL.live_refuse(mk, x, sym, mode)
                tv = simulate(mk, x[~bad], sym=sym, costs=costs, no_overlap=True)
                tv = tv[tv.entry_time >= pd.Timestamp("2018-02-01", tz="UTC")]
                got = [int(len(tv)), round(float(tv.R.sum()), 1)]
                rows_g.append({"field": f"K2 ethusd {mode}: entry +1 min at market and Friday 16:50 NY close, the "
                                        f"verifier's one-position test (synthesis_B: {exp_n} trades, {exp_R:+.1f} R)",
                               "expected": [exp_n, exp_R], "got": got, "ok": got == [exp_n, exp_R]})
                h = res["sleeves"]["orb_asia_2d_buf10__ethusd"]["runs"][f"{mode}/live"]["main"]["window"]
                # the harness's default live run (spec live_one_position = entry_bar) is the verifier's way with the
                # trade still open at the end of the frame dropped
                tvc = tv[tv.exit_time < mk.index[-1]]
                same_default = [h.get("n"), h.get("total")] == [int(len(tvc)), round(float(tvc.R.sum()), 2)]
                rows_g.append({"field": f"K2 ethusd {mode}: the harness's live run (declared default 'entry_bar') == the "
                                        "verifier's way without the trade still open at the end of 2021",
                               "expected": [int(len(tvc)), round(float(tvc.R.sum()), 2)], "got": [h.get("n"), h.get("total")],
                               "ok": same_default})
                spec_k2 = {"key": "k2", "rule": "orb_asia_2d_buf10", "sym": sym, "convention": "sB", "change": {"kind": "new"}}
                alt = {}
                for sem in ("rule", "lab_chain"):
                    o_, i_ = SL.run(spec_k2, m1, mode, "live", None, live_one_position=sem)
                    w_ = o_["main"][(o_["main"].entry_time >= pd.Timestamp("2018-02-01", tz="UTC"))]
                    alt[sem] = {"n": int(len(w_)), "total": round(float(w_.R.sum()), 2),
                                "exp": round(float(w_.R.mean()), 4) if len(w_) else None,
                                "overlapping_live_trades": i_.get("main_live", {}).get("overlapping_live_trades")}
                # the rule's one-position test on the same live orders, open trade kept: which
                # trades differ, and is every difference a signal whose activation bar is the previous exit bar?
                th = SL.live_chain(mk, x[~bad], sym, costs)
                th = th[th.entry_time >= pd.Timestamp("2018-02-01", tz="UTC")]
                kv, kh = set(tv.oid), set(th.oid)
                only_v = tv[tv.oid.isin(kv - kh)]
                tva = simulate(mk, x[~bad], sym=sym, costs=costs, no_overlap=True)
                xb = SL.exit_bar(mk, tva)
                prev_exit = pd.Series(xb, index=tva.oid.to_numpy()).shift(1)
                act = pd.Series(tva.act_i.to_numpy(), index=tva.oid.to_numpy())
                exit_minute = [bool(act[o] == prev_exit[o]) for o in only_v.oid]
                out_g[f"K2_ethusd_{mode}"] = {
                    "verifier_way_incl_open_trade": {"n": got[0], "total": got[1], "exp": round(float(tv.R.mean()), 4)},
                    "harness_default_entry_bar_open_trade_dropped": h,
                    "alternative_rule_open_trade_dropped": alt["rule"],
                    "alternative_lab_chain_open_trade_dropped": alt["lab_chain"],
                    "rule_way_incl_open_trade": {"n": int(len(th)), "total": round(float(th.R.sum()), 2)},
                    "trades_only_in_verifier_way": int(len(only_v)), "R_of_those": round(float(only_v.R.sum()), 3),
                    "trades_only_in_harness_way": int(len(kh - kv)),
                    "every_difference_is_a_signal_at_the_previous_trades_exit_bar": bool(all(exit_minute)),
                    "explanation": "the verifier's run (the harness's declared default 'entry_bar') applies the "
                                   "one-position test at the DELAYED entry bar, so a touch in the very bar where the "
                                   "previous trade exits is taken one minute later; the alternative 'rule' keeps the "
                                   "rule's own test at the rule's bar (that touch is ignored, as in the lab); "
                                   "'lab_chain' takes only the lab chain's trades (no extra trade after a Friday "
                                   "close). Which one the robot does is a declaration of the look.",
                    "reasons_verifier_way": tv.reason.value_counts().to_dict()}
                rows_g.append({"field": f"K2 ethusd {mode}: every trade the verifier's way adds over the 'rule' "
                                        "alternative is a signal at the previous trade's exit bar",
                               "expected": True,
                               "got": out_g[f"K2_ethusd_{mode}"]["every_difference_is_a_signal_at_the_previous_trades_exit_bar"],
                               "ok": out_g[f"K2_ethusd_{mode}"]["every_difference_is_a_signal_at_the_previous_trades_exit_bar"]})
                del mk
        if sym == "us100":
            # the example change plugin (example_plugins.py): an empty skip set gives the reference chain; a skip set
            # removes those signals and the chain is re-simulated (a skipped signal never blocks)
            import example_plugins  # noqa: F401  (registers the change kind "skip_ny_hours")
            ref = res["_trades"][("noise30__us100", "main", "fp", "lab")]
            s0 = {"key": "x", "rule": "noise30", "sym": "us100", "convention": "sB",
                  "change": {"kind": "skip_ny_hours", "hours": []}}
            t0_, _ = SL.run(s0, m1, "fp", "lab", leader)
            same0 = len(t0_["main"]) == len(ref) and bool((t0_["main"].R.to_numpy() == ref.R.to_numpy()).all())
            s1 = dict(s0, change={"kind": "skip_ny_hours", "hours": [12, 13]})
            t1_, i1 = SL.run(s1, m1, "fp", "lab", leader)
            hrs = pd.DatetimeIndex(t1_["main"].entry_time).tz_convert("America/New_York").hour
            none_left = not bool(np.isin(hrs, [12, 13]).any())
            out_g["example_change_plugin"] = {"empty_skip_equals_reference": same0, "skipped_orders": i1["change_diag"]["skipped"],
                                              "trades_ref": int(len(ref)), "trades_with_skip": int(len(t1_["main"])),
                                              "no_trade_left_in_skipped_hours": none_left}
            rows_g.append({"field": "example change plugin skip_ny_hours: empty set == reference chain; skipped hours "
                                    "absent from the re-simulated chain", "expected": [True, True],
                           "got": [same0, none_left], "ok": same0 and none_left})
        del m1
        L.clear_rule_caches()
    # every sleeve in sample, lab against live (information)
    for k in RUN.TEN_KEYS + ["brk72_24h_wd__ethusd+K1", "orb_asia_2d_buf10__ethusd", "orb_asia_2d_buf10__btcusd"]:
        out_g[f"lab_vs_live.{k}"] = {m: {"lab": res["sleeves"][k]["runs"][f"{m}/lab"]["main"]["window"],
                                         "live": res["sleeves"][k]["runs"][f"{m}/live"]["main"]["window"]}
                                     for m in ("fp", "stress")}
    # F7 over every live run of the proofs' run: signals decided inside the Friday block whose delayed entry bar is
    # after the reopen (blocked by the decision-instant test only), and Friday closes executed at a later reopen
    dec, reo = {}, {}
    for k, s in res["sleeves"].items():
        for r, v in s["runs"].items():
            if not r.endswith("/live"):
                continue
            for ch in ("main", "base"):
                li = v["info"].get(f"{ch}_live")
                if li:
                    dec[f"{k}/{ch}/{r}"] = li.get("blocked_decision_instant_only", 0)
                    if li.get("friday_close_orders_at_a_later_reopen"):
                        reo[f"{k}/{ch}/{r}"] = li["friday_close_orders_at_a_later_reopen"]
    out_g["F7_blocked_by_the_decision_instant_only"] = {"total": int(sum(dec.values())), "live_runs": len(dec),
                                                         "nonzero": {k: v for k, v in dec.items() if v}}
    out_g["F7_friday_close_orders_at_a_later_reopen"] = {
        "by_run": reo, "us100": {k: v for k, v in reo.items() if "__us100" in k},
        "note": "orders whose Friday close falls on a bar that starts more than 60 minutes after Friday 16:50 New York "
                "(the market already shut then: us100 about 16:15 New York, or an early-closed Friday): such a "
                "position is closed at the open of the next bar, the reopen"}
    rows_g.append({"field": "F7 in sample: no signal of any live run is decided inside the Friday block with its delayed "
                            "entry bar after the reopen (the review's census: 0)", "expected": 0,
                   "got": out_g["F7_blocked_by_the_decision_instant_only"]["total"],
                   "ok": out_g["F7_blocked_by_the_decision_instant_only"]["total"] == 0})
    rows_g.append({"field": "F7 the spec declares live_one_position 'entry_bar' and live_friday_block 'decision_and_entry', "
                            "and the run used them", "expected": ["entry_bar", "decision_and_entry"],
                   "got": [res["live_one_position"], res["live_friday_block"]],
                   "ok": [res["live_one_position"], res["live_friday_block"]] == ["entry_bar", "decision_and_entry"]})
    return rows_g, out_g, signals, k1x


def proof_h(res, signals):
    rows, out = [], {}
    spec = json.load(open(SPEC))
    P = RUN.resolve_portfolios(spec)
    W = res["_W"]
    a, b = W["eval"]
    base = P["P0"]
    ref_sum = res["portfolios"]["P0"]["fp/lab/sum"]
    ref_cap = res["portfolios"]["P0"]["fp/lab/capped"]
    # 1) stake 1 on every sleeve == P0
    p1 = {"sleeves": base["sleeves"], "stakes": {k: {"kind": "const", "m": 1.0} for k in base["sleeves"]}}
    m1, _, _ = RUN.portfolio(p1, res["_trades"], res["_signals"], res["_meta"], "fp", "lab", ["sum", "capped"], W, cut)
    for acc, ref in (("sum", ref_sum), ("capped", ref_cap)):
        keys = ("n", "total", "exp", "worst_week_R", "max_dd_R_weekly", "weekly_sharpe_annualised", "by_year")
        rows += compare({k: m1[acc][k] for k in keys}, {k: ref[k] for k in keys}, f"const_1.{acc}")
    # 2) a sleeve-year table adds exactly that sleeve-year's R
    k = "noise30__us100"
    p2 = {"sleeves": base["sleeves"], "stakes": {k: {"kind": "sleeve_year", "table": {"2020": 2.0}}}}
    m2, _, _ = RUN.portfolio(p2, res["_trades"], res["_signals"], res["_meta"], "fp", "lab", ["sum"], W, cut)
    t = res["_trades"][(k, "main", "fp", "lab")]
    add = float(t[(t.entry_time >= pd.Timestamp("2020-01-01", tz="UTC")) & (t.entry_time < pd.Timestamp("2021-01-01", tz="UTC"))].R.sum())
    exp_total = round(ref_sum["total"] + add, 2)
    rows.append({"field": "sleeve_year {2020: 2} on noise30: P0 total + noise30's 2020 R", "expected": exp_total,
                 "got": m2["sum"]["total"], "ok": abs(m2["sum"]["total"] - exp_total) <= 0.011})
    # 3) a walk-forward stake (terciles of riskbp on brk72 ethusd, refitted every 1 January)
    sigs = dict(res["_signals"])
    sigs.update(signals)
    k = "brk72_24h_wd__ethusd"
    rule = ST.WFTerciles("riskbp", (1.5, 1.0, 0.5))
    p3 = {"sleeves": base["sleeves"], "stakes": {k: None}}
    tt = res["_trades"][(k, "main", "fp", "lab")]
    ctx = {"cut": cut, "mode": "fp", "exec": "lab", "sleeve": k, "sym": "ethusd", "book": None,
           "signals": {kk: v for (kk, mm), v in sigs.items() if mm == "fp"}, "purge": ST.PURGE}
    mm = rule.stakes(tt, ctx)
    fits = rule.fits[(k, "fp", "lab")]
    causal = all(f is None or pd.Timestamp(f["last_outcome_used"]) < pd.Timestamp(f"{Y}-01-01", tz="UTC") - ST.PURGE
                 for Y, f in fits.items())
    rows.append({"field": "wf_terciles riskbp brk72 ethusd: every yearly fit uses only outcomes known before "
                          "1 January minus 7 days", "expected": True, "got": bool(causal), "ok": bool(causal)})
    rows.append({"field": "wf_terciles stakes within [0, 2]", "expected": True, "got": ST.check_bounds(mm),
                 "ok": ST.check_bounds(mm)})
    per = {kk: (res["_trades"][(kk, "main", "fp", "lab")], None, res["_meta"][kk]) for kk in base["sleeves"]}
    per[k] = (tt, mm, res["_meta"][k])
    d = B.apply_account(B.make_book(per), "sum", a, b)
    sw = B.equal_swing(res["_books"][("P0", "fp", "lab", "sum")][lambda x: x.entry_time >= pd.Timestamp("2019-01-01", tz="UTC")],
                       d[d.entry_time >= pd.Timestamp("2019-01-01", tz="UTC")],
                       pd.Timestamp("2019-01-01", tz="UTC"), b, [2019, 2020, 2021])
    out["wf_terciles_example"] = {"fits": fits, "stakes_mean_by_year": pd.Series(mm).groupby(pd.DatetimeIndex(tt.entry_time).year).mean().round(4).to_dict(),
                                  "equal_swing_vs_P0_2019_2021": {"scale_k": sw["scale_k"], "sharpe_ratio": sw["sharpe_ratio"],
                                                                  "years_up": sw["years_up"]},
                                  "note": "a mechanics example of the stake interface, not a candidate (not declared, not judged)"}
    # 3b) a stake rule loaded from a file (the 'python' kind: how a sizing-lens rule enters the look)
    k = "noise30__us100"
    sr = ST.from_spec({"kind": "python", "module": "example_plugins.py", "factory": "HourBandStake",
                       "args": {"bands": [[10, 12], [12, 14], [14, 16]], "m_low": 0.5}})
    paper = B.make_book({kk: (res["_trades"][(kk, "main", "fp", "lab")], None, res["_meta"][kk]) for kk in base["sleeves"]})
    tn = res["_trades"][(k, "main", "fp", "lab")]
    mn = sr.stakes(tn, {"cut": cut, "mode": "fp", "exec": "lab", "sleeve": k, "sym": "us100", "book": paper,
                        "signals": {}, "purge": ST.PURGE})
    fits_n = sr.fits[(k, "fp", "lab")]
    causal_n = all(f is None or "last_outcome_used" not in f or
                   pd.Timestamp(f["last_outcome_used"]) < pd.Timestamp(f"{Y}-01-01", tz="UTC") - ST.PURGE
                   for Y, f in fits_n.items())
    rows.append({"field": "python stake plugin (example HourBandStake on noise30): loaded from its file, stakes in "
                          "[0, 2], every yearly fit uses only outcomes known before 1 January minus 7 days",
                 "expected": [True, True], "got": [ST.check_bounds(mn), bool(causal_n)],
                 "ok": ST.check_bounds(mn) and bool(causal_n)})
    out["python_stake_plugin_example"] = {"fits": fits_n, "share_at_m_low": round(float((mn == 0.5).mean()), 4),
                                          "note": "mechanics example only, not a candidate"}
    # 4) riskbp of the generic signal table against synthesis_B's K1 table (same orders, same prices)
    sB_s = res["_signals"][("brk72_24h_wd__ethusd+K1", "fp")].set_index("oid")
    g_s = signals[("brk72_24h_wd__ethusd", "fp")].set_index("oid")
    j = sB_s.join(g_s[["riskbp", "label"]], rsuffix="_g", how="inner")
    okr = j.riskbp.notna() & j.riskbp_g.notna()
    out["generic_signal_table_vs_K1_table"] = {"orders": int(len(j)),
                                               "max_abs_riskbp_diff": float((j.riskbp - j.riskbp_g)[okr].abs().max()),
                                               "orders_with_riskbp_diff_over_1bp": int(((j.riskbp - j.riskbp_g)[okr].abs() > 1).sum()),
                                               "labels_identical": bool(np.allclose(j.label.fillna(-999), j.label_g.fillna(-999), atol=1e-12))}
    rows.append({"field": "generic signal table labels (each order alone) identical to synthesis_B's K1 table",
                 "expected": True, "got": out["generic_signal_table_vs_K1_table"]["labels_identical"],
                 "ok": out["generic_signal_table_vs_K1_table"]["labels_identical"]})
    return {"what": "the stake interface (Addendum I hook): stake 1 reproduces P0 in both accounts; a sleeve-year "
                    "table adds exactly its sleeve-year R; a walk-forward stake refitted every 1 January uses only "
                    "outcomes known before 1 January minus 7 days and stays within [0, 2]",
            "detail": out, **verdict(rows), "rows": rows}


# ------------------------------------------------------------------------------------------------- (i)
def plan_tests():
    """F1 / A1 / F2 on look.plan (pure: nothing is opened, read or logged beyond the declared text and the access log).
    The temporary declaration quotes the sha256 of a DUMMY spec, never the real one. A1 refuses it (it is not the
    protocol); to exercise the F2 rules behind the declaration, vhi_guard.DECLARED_PATH is pointed at the temporary
    text for those plan() calls only (restored in `finally`; open_run is never called meanwhile)."""
    import importlib.util
    sp = importlib.util.spec_from_file_location("vhi_look_entry", os.path.join(HERE, "look.py"))
    LK = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(LK)
    raw_real = open(SPEC, "rb").read()
    raw = json.dumps({"name": "vhi_proof_dummy_spec"}).encode()
    sha = hashlib.sha256(raw).hexdigest()
    tmp = tempfile.mkdtemp(prefix="vhi_plan_")
    decl = os.path.join(tmp, "addendum_test.md")
    with open(decl, "w") as f:
        f.write(f"Addendum (test text): the look {G.TRACK} is declared; spec sha256 {sha}.\n")
    log0, log1 = os.path.join(tmp, "log_empty.log"), os.path.join(tmp, "log_one.log")
    open(log0, "w").close()
    with open(log1, "w") as f:
        f.write(json.dumps({"time": "2026-01-02T00:00:00+00:00", "track": G.TRACK, "label": "look:x:y", "period": "val"}) + "\n")
    lookd, lookd2 = os.path.join(tmp, "look"), os.path.join(tmp, "look_started")
    os.makedirs(lookd)
    os.makedirs(lookd2)
    open(os.path.join(lookd2, "vhi_proof_dummy_spec__cut2026-01-01.started"), "w").close()
    env = {"LOOK_DECLARED": decl}
    rows, out = [], {}

    def attempt(name, want_ok, **kw):
        try:
            p = LK.plan(**kw)
            got, why = True, {k: p[k] for k in ("out", "marker", "label", "stem", "is_look")}
        except G.GuardError as e:
            got, why = False, str(e)[:300]
        rows.append({"field": f"plan: {name}", "expected": want_ok, "got": got, "ok": got == want_ok})
        out[name] = why
        return why

    saved_decl = G.DECLARED_PATH
    try:
        attempt("the real spec with LOOK_DECLARED = PROTOCOL_V3.md as it stands: refused (F1)", False,
                cut="2026-01-01", raw=raw_real, env={"LOOK_DECLARED": PROTOCOL})
        attempt("the real spec without LOOK_DECLARED: refused", False, cut="2026-01-01", raw=raw_real, env={})
        attempt("A1: a dummy spec with a declaration in /tmp quoting the track and its sha256: refused (not the "
                "protocol's path)", False, cut="2026-01-01", raw=raw, env=env, log_path=log0, look_dir=lookd)
        # ---- behind A1 (the temporary text plays the protocol for the plan() calls below only)
        G.DECLARED_PATH = os.path.realpath(decl)
        attempt("a dummy spec whose sha256 the declaration does not quote (the real spec + the test text): refused",
                False, cut="2026-01-01", raw=raw_real, env=env, log_path=log0, look_dir=lookd)
        p = attempt("a look of the dummy spec, declaration quoting its sha256, no earlier access: allowed (plan only)",
                    True, cut="2026-01-01", raw=raw, env=env, log_path=log0, look_dir=lookd)
        fixed = isinstance(p, dict) and p["out"] == os.path.join(lookd, "vhi_proof_dummy_spec__cut2026-01-01.json") \
            and p["marker"] == os.path.join(lookd, "vhi_proof_dummy_spec__cut2026-01-01.started") \
            and p["label"] == f"look:vhi_proof_dummy_spec:{sha[:12]}"
        rows.append({"field": "plan: the look's output and '.started' marker paths are fixed, the label carries the spec "
                              "sha256[:12]; nothing was created", "expected": True,
                     "got": bool(fixed and not os.listdir(lookd)), "ok": bool(fixed and not os.listdir(lookd))})
        attempt("a look with --out: refused (F2: fixed output path)", False, cut="2026-01-01", raw=raw, env=env,
                out_arg=os.path.join(tmp, "elsewhere.json"), log_path=log0, look_dir=lookd)
        attempt("a look when val_access.log already holds an autopsy_HI_look line: refused (F2: run once)", False,
                cut="2026-01-01", raw=raw, env=env, log_path=log1, look_dir=lookd)
        attempt("a look when a '.started' marker exists: refused (F2)", False, cut="2026-01-01", raw=raw, env=env,
                log_path=log0, look_dir=lookd2)
        p2 = attempt("a second access with its reason after a logged first access: allowed (plan only)", True,
                     cut="2026-01-01", raw=raw, env=env, log_path=log1, look_dir=lookd,
                     second_access="the first run crashed after its access line")
        sec = isinstance(p2, dict) and p2["stem"].endswith("__access2") \
            and p2["label"].endswith(":second_access:the first run crashed after its access line")
        rows.append({"field": "plan: a second access writes its reason into the label and gets the suffix __access2",
                     "expected": True, "got": bool(sec), "ok": bool(sec)})
        attempt("a second access with an empty reason: refused", False, cut="2026-01-01", raw=raw, env=env,
                log_path=log1, look_dir=lookd, second_access="  ")
        attempt("--second-access without an earlier access: refused", False, cut="2026-01-01", raw=raw, env=env,
                log_path=log0, look_dir=lookd, second_access="no reason")
        attempt("a rehearsal (CUT 2022-01-01) with --out: allowed", True, cut="2022-01-01", raw=raw, env={},
                out_arg=os.path.join(tmp, "rehearsal.json"))
        attempt("a rehearsal with --second-access: refused", False, cut="2022-01-01", raw=raw, env={}, second_access="x")
        attempt("CUT 2026-01-02 with a declaration quoting the spec's sha256: refused", False, cut="2026-01-02", raw=raw,
                env=env, log_path=log0, look_dir=lookd)
    finally:
        G.DECLARED_PATH = saved_decl
        for d_ in (lookd, lookd2):
            for fn in os.listdir(d_):
                os.unlink(os.path.join(d_, fn))
            os.rmdir(d_)
        for fn in os.listdir(tmp):
            os.unlink(os.path.join(tmp, fn))
        os.rmdir(tmp)
    rows.append({"field": "A1: vhi_guard.DECLARED_PATH is the protocol again after the plan tests", "expected": PROTOCOL,
                 "got": G.DECLARED_PATH, "ok": G.DECLARED_PATH == PROTOCOL == "/home/user/gold-orb/lab/PROTOCOL_V3.md"})
    # the real access log and look directory: the look has never run
    prior, started = G.check_run_once()
    rows.append({"field": "the real val_access.log has no autopsy_HI_look line and results/r2/validation_hi/look/ "
                          "no '.started' marker (check_run_once passes)", "expected": [0, 0],
                 "got": [len(prior), len(started)], "ok": len(prior) == 0 and len(started) == 0})
    return rows, out


def _open_close(path, mode="r"):
    """open() then close at once, nothing read (a probe that would only create a handle if the guard failed)."""
    f = open(path, mode)
    f.close()


def guard_probes():
    """F3, A2, A3: reads the hardened guard must refuse inside this very process (each raises before any byte is
    read). Probes of sensitive files either use a path that does not exist (a failing guard then raises
    FileNotFoundError, which counts as NOT refused, and nothing is read) or only open and close a handle; the
    numpy / pyarrow CSV probes read a harmless one-line CSV written for the purpose under lab/results/r2/validation_hi/
    (deleted afterwards)."""
    import bz2
    import csv
    import gzip
    import pyarrow.csv as pacsv
    import pyarrow.json as pajson
    FR = os.path.join(LAB, "data", "fp", "ethusd_m1.parquet")
    SK = os.path.join(LAB, "r2", "audit", "brk72_24h_wd", "stat_skeptic", "trades", "every_val_ethusd.parquet")
    HO = os.path.join(LAB, "results", "holdout")
    VALCSV = os.path.join(LAB, "results", "trend", "trades_val_donch4h_stop.csv")     # validation trades: never read
    HARMLESS = os.path.join(OUT, ".vhi_probe_harmless.csv")                           # a, 1 (written here, deleted)
    ABSENT_CSV = os.path.join(OUT, ".vhi_probe_absent.csv")
    import pyarrow.dataset as pads
    import pyarrow.fs as pafs
    import pyarrow.parquet as pq
    import pyarrow.parquet.core as pqc
    link_dir = tempfile.mkdtemp(prefix="vhi_link_")
    link = os.path.join(link_dir, "harmless.parquet")
    os.symlink(FR, link)
    link_ho = os.path.join(link_dir, "harmless.txt")
    os.symlink(os.path.join(HO, "holdout_stdout.txt"), link_ho)
    with open(HARMLESS, "w") as f:                                                    # write mode: allowed
        f.write("a\n1\n")
    c = pd.Timestamp(CUT, tz="UTC")
    tries = {
        "frame_without_row_filter": lambda: pd.read_parquet(FR),
        "frame_with_filter_after_cut": lambda: pd.read_parquet(FR, filters=[("ts", "<", pd.Timestamp("2022-01-02", tz="UTC"))]),
        "frame_with_entry_time_filter (lab/data needs ts)": lambda: pd.read_parquet(FR, filters=[("entry_time", "<", c)]),
        "frame_with_filesystem_argument": lambda: pd.read_parquet(FR, filters=[("ts", "<", c)], filesystem=pafs.LocalFileSystem()),
        "official_trades_without_entry_filter": lambda: pd.read_parquet(os.path.join(G.OFFICIAL_DIR, "brk72_24h_wd__ethusd.parquet")),
        "holdout_dir": lambda: pd.read_parquet(os.path.join(LAB, "data", "holdout", "anything.parquet")),
        "F3a open file object (builtins.open of an FP frame)": lambda: open(FR, "rb"),
        "F3a buffer source": lambda: pd.read_parquet(io.BytesIO(b"PAR1"), filters=[("ts", "<", c)]),
        "F3a bytes path": lambda: pd.read_parquet(os.fsencode(FR), filters=[("ts", "<", c)]),
        "F3a file:// URI": lambda: pd.read_parquet("file://" + FR, filters=[("ts", "<", c)]),
        "F3a symlink to an FP frame, no filter (realpath)": lambda: pd.read_parquet(link),
        "F3b validation trades outside lab/data and lab/results, no filter (stat_skeptic every_val_ethusd)":
            lambda: pd.read_parquet(SK),
        "F3b the same with an entry_time filter after the CUT": lambda: pd.read_parquet(
            SK, filters=[("entry_time", "<", pd.Timestamp("2023-01-01", tz="UTC"))]),
        "F3c pyarrow.parquet.core.read_table without filter": lambda: pqc.read_table(FR),
        "F3c pyarrow.parquet.read_pandas without filter": lambda: pq.read_pandas(FR),
        "F3c pyarrow.parquet.ParquetFile": lambda: pq.ParquetFile(FR),
        "F3c pyarrow.parquet.ParquetDataset without filter": lambda: pq.ParquetDataset(FR),
        "F3c pyarrow.dataset.dataset": lambda: pads.dataset(FR),
        "F3c pyarrow.parquet.read_metadata (row-group statistics)": lambda: pq.read_metadata(FR),
        "F3d csv under lab/ not on the allowlist (results/trend/trades_val_donch4h_stop.csv)":
            lambda: pd.read_csv(os.path.join(LAB, "results", "trend", "trades_val_donch4h_stop.csv")),
        "F3d csv from a buffer": lambda: pd.read_csv(io.StringIO("a\n1\n")),
        "F3d raw data csv dated 2026 (lab/data/vx)": lambda: pd.read_csv(os.path.join(LAB, "data", "vx", "VX_2026-01-21.csv")),
        "open() of lab/data via pathlib": lambda: pathlib.Path(FR).read_bytes(),
        "open() of lab/holdout_raw": lambda: open(os.path.join(LAB, "holdout_raw", "download",
                                                              "xauusd-m1-bid-2026-01-01-2026-11-05.csv")),
        "open() of a file dated 2026 (results/live/brain_maps_2026-11-11.json)":
            lambda: open(os.path.join(LAB, "results", "live", "brain_maps_2026-11-11.json")),
        "nq_default_leader_loader": lambda: L.registry()["rules"]["nq_btc_follow"][1].__globals__["_LEADERS"].clear()
        or L.registry()["rules"]["nq_btc_follow"][1].__globals__["_leader"]("us100"),
        "val_access_log_at_cut_2022": lambda: G.log_access("should_not_be_written"),
        "open_run of a look in this process (no LOOK_DECLARED; one CUT per process)":
            lambda: G.open_run("2026-01-01", "should_not_be_written", spec_sha=SPEC_SHA,
                               marker=os.path.join(G.LOOK_DIR, "never.started")),
        # ---- A2: a 'holdout' component under lab/, and results/holdout_run.log, at every CUT, every reader
        "A2 open() of results/holdout/holdout_stdout.txt (opened and closed if it passed, nothing read)":
            lambda: _open_close(os.path.join(HO, "holdout_stdout.txt")),
        "A2 open() of results/holdout_run.log (opened and closed if it passed, nothing read)":
            lambda: _open_close(os.path.join(LAB, "results", "holdout_run.log")),
        "A2 pathlib read of a path under results/holdout/ (absent)":
            lambda: pathlib.Path(HO, "__vhi_probe_absent__.json").read_text(),
        "A2 pathlib read of results/holdout_run.log through a path with a '..' component (absent twin name)":
            lambda: pathlib.Path(LAB, "results", "r2", "..", "holdout_run.log.__absent__").read_bytes(),
        "A2 a symlink in /tmp to results/holdout/holdout_stdout.txt (realpath; opened and closed if it passed)":
            lambda: _open_close(link_ho),
        "A2 open() in append mode of a path under results/holdout/ (any mode is refused; a folder that does not exist, "
        "so nothing could be created)":
            lambda: _open_close(os.path.join(HO, "__vhi_absent_dir__", "x.txt"), "a"),
        "A2 parquet under results/holdout/ with a filter at the CUT (absent)":
            lambda: pd.read_parquet(os.path.join(HO, "__absent__.parquet"), filters=[("entry_time", "<", c)]),
        "A2 pandas csv under results/holdout/ (absent)": lambda: pd.read_csv(os.path.join(HO, "__absent__.csv")),
        "A2 open() of lab/holdout.py (a lab file whose name carries 'holdout')":
            lambda: _open_close(os.path.join(LAB, "holdout.py")),
        "A2 open() of lab/holdout_candidates.json": lambda: _open_close(os.path.join(LAB, "holdout_candidates.json")),
        "A2 open() of an audit file named *holdout* (lab/audit/scratch/donch4h_stop/statskeptic/s07_holdout.json)":
            lambda: _open_close(os.path.join(LAB, "audit", "scratch", "donch4h_stop", "statskeptic", "s07_holdout.json")),
        "A2 pyarrow.json.read_json under results/holdout/ (absent)":
            lambda: pajson.read_json(os.path.join(HO, "__absent__.json")),
        # ---- A3: CSV files under lab/ through open(), whatever reads them, except the allowlist
        "A3 open() of results/trend/trades_val_donch4h_stop.csv (validation trades; opened and closed if it passed)":
            lambda: _open_close(VALCSV),
        "A3 csv.reader(open(...)) of the same file": lambda: csv.reader(open(VALCSV)),
        "A3 pathlib read_text of a lab CSV (absent)": lambda: pathlib.Path(ABSENT_CSV).read_text(),
        "A3 open() of a lab *.csv.gz (absent)": lambda: _open_close(ABSENT_CSV + ".gz", "rb"),
        "A3 gzip.open of a lab *.csv.gz (absent)": lambda: gzip.open(ABSENT_CSV + ".gz").close(),
        "A3 bz2.open of a lab *.csv.bz2 (absent)": lambda: bz2.open(ABSENT_CSV + ".bz2").close(),
        "A3 open() in r+ mode of a lab CSV (reading)": lambda: _open_close(HARMLESS, "r+"),
        "A3 numpy.loadtxt of a lab CSV (a harmless one written here)": lambda: np.loadtxt(HARMLESS, skiprows=1),
        "A3 numpy.genfromtxt of a lab CSV (the harmless one)": lambda: np.genfromtxt(HARMLESS, skip_header=1),
        "A3 pyarrow.csv.read_csv of a lab CSV off the allowlist (the harmless one)": lambda: pacsv.read_csv(HARMLESS),
        "A3 pyarrow.csv.open_csv of a lab CSV off the allowlist (the harmless one)": lambda: pacsv.open_csv(HARMLESS),
        "A3 pyarrow.csv.read_csv of a buffer": lambda: pacsv.read_csv(io.BytesIO(b"a\n1\n")),
    }
    controls = {
        "A3 open() of the allowlisted results/r2/autopsy/payoff/variants_table.csv is allowed":
            lambda: _open_close(os.path.join(LAB, G.CSV_ALLOW[0])),
        "A3 open() of a lab CSV in write mode is allowed (only reading modes are refused)":
            lambda: _open_close(HARMLESS, "a"),
        "A2 a JSON under lab/results/ that is not holdout can still be opened (recorded)":
            lambda: _open_close(ENGINE_CHECK),
    }
    rows = []
    L.registry()                                         # built before counting (its imports read source files)
    n0 = len(G.reads())
    try:
        for name, fn in tries.items():
            try:
                fn()
                refused, why = False, None
            except G.GuardError as e:
                refused, why = True, str(e)[:200]
            except Exception as e:  # noqa: BLE001 -- e.g. FileNotFoundError: the guard let it through
                refused, why = False, f"NOT REFUSED BY THE GUARD: {e!r}"[:200]
            rows.append({"field": f"refused in process: {name}", "expected": True, "got": refused, "ok": refused,
                         "why": why})
        nothing = len(G.reads()) == n0 and not os.path.exists(os.path.join(G.LOOK_DIR, "never.started"))
        rows.append({"field": "the refused probes recorded no read and wrote no marker", "expected": True,
                     "got": nothing, "ok": nothing})
        for name, fn in controls.items():
            try:
                fn()
                allowed, why = True, None
            except Exception as e:  # noqa: BLE001
                allowed, why = False, repr(e)[:200]
            rows.append({"field": f"control: {name}", "expected": True, "got": allowed, "ok": allowed, "why": why})
    finally:
        os.unlink(link)
        os.unlink(link_ho)
        os.rmdir(link_dir)
        if os.path.exists(HARMLESS):
            os.unlink(HARMLESS)
    from numpy.lib import _datasource as npds
    installed = all(getattr(f, "__vhi_guarded__", False) for f in (
        pd.read_parquet, pd.read_csv, pq.read_table, pqc.read_table, pq.read_pandas, pads.dataset, open, io.open,
        npds._file_openers._file_openers[None], bz2._builtin_open, pacsv.read_csv, pacsv.open_csv, pajson.read_json))
    rows.append({"field": "the guard wraps pandas.read_parquet / read_csv, pyarrow.parquet(.core).read_table, read_pandas, "
                          "pyarrow.dataset.dataset, builtins.open and io.open, numpy's file opener, bz2's open, "
                          "pyarrow.csv.read_csv / open_csv and pyarrow.json.read_json", "expected": True,
                 "got": installed, "ok": installed})
    return rows


def declared_file_probes(stage):
    """A1 (the recheck's L1b): files whose text quotes the track and the spec's sha256 -- the harness's own outputs
    proofs.json, the rehearsal JSONs and proof_i_guard.json, and copies of proofs.json in /tmp (named PROTOCOL_V3.md),
    the scratchpad, the harness folder and lab/results/, and a symlink in /tmp to proofs.json -- are refused as
    LOOK_DECLARED by the path rule, through resolve_cut and look.plan on environment dicts (the process environment
    is never set; no run is opened; nothing is logged). `stage` 'after_write' runs once proofs.json, proof_i_guard.json
    and the rehearsal hold this run's spec sha256: the content rule alone would then accept them. The copies are
    deleted afterwards."""
    import importlib.util
    import shutil
    sp = importlib.util.spec_from_file_location(f"vhi_look_entry_a1_{stage}", os.path.join(HERE, "look.py"))
    LK = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(LK)
    raw_real = open(SPEC, "rb").read()
    targets = {"results/r2/validation_hi/proofs.json": os.path.join(OUT, "proofs.json"),
               "results/r2/validation_hi/proof_i_guard.json": os.path.join(OUT, "proof_i_guard.json"),
               "results/r2/validation_hi/rehearsal/autopsy_HI_look__cut2022-01-01.json":
                   os.path.join(OUT, "rehearsal", "autopsy_HI_look__cut2022-01-01.json"),
               "results/r2/validation_hi/rehearsal_in_sample.json": os.path.join(OUT, "rehearsal_in_sample.json")}
    src = targets["results/r2/validation_hi/proofs.json"]
    tmpd = tempfile.mkdtemp(prefix="vhi_a1_")
    os.makedirs(SCRATCH, exist_ok=True)
    places = {"a copy of proofs.json in /tmp named PROTOCOL_V3.md": os.path.join(tmpd, "PROTOCOL_V3.md"),
              "a copy of proofs.json in the scratchpad": os.path.join(SCRATCH, f"vhi_a1_copy_of_proofs_{stage}.json"),
              "a copy of proofs.json in the harness folder": os.path.join(HERE, f".vhi_a1_copy_of_proofs_{stage}.json"),
              "a copy of proofs.json under lab/results/": os.path.join(OUT, f".vhi_a1_copy_of_proofs_{stage}.json"),
              "a symlink in /tmp to proofs.json": os.path.join(tmpd, "link_to_proofs.json")}
    rows, out = [], {}
    made = []
    try:
        if os.path.exists(src):
            for nm, p in places.items():
                if nm.startswith("a symlink"):
                    os.symlink(src, p)
                else:
                    shutil.copyfile(src, p)
                made.append(p)
        for nm, p in list(targets.items()) + list(places.items()):
            if not os.path.lexists(p):
                continue
            d = G.declaration_check(p, SPEC_SHA)
            try:
                G.resolve_cut("2026-01-01", {"LOOK_DECLARED": p}, spec_sha=SPEC_SHA)
                r_ok, why = True, None
            except G.GuardError as e:
                r_ok, why = False, str(e)
            try:
                LK.plan("2026-01-01", raw_real, env={"LOOK_DECLARED": p}, log_path=os.path.join(tmpd, "no.log"),
                        look_dir=os.path.join(tmpd, "look"))
                p_ok = True
            except G.GuardError:
                p_ok = False
            by_path = bool(why and "(A1)" in why)
            want_content = stage == "after_write" and not nm.endswith("rehearsal_in_sample.json")
            ok = (not r_ok) and (not p_ok) and by_path and (d["ok"] if want_content else True)
            rows.append({"field": f"A1 ({stage}): LOOK_DECLARED = {nm}: refused by the path rule (resolve_cut and "
                                  "look.plan)" + (" although its text quotes the track and the spec sha256 (the content "
                                                  "rule alone would accept it)" if want_content else ""),
                         "expected": [False, False, True] + ([True] if want_content else []),
                         "got": [r_ok, p_ok, by_path] + ([d["ok"]] if want_content else []), "ok": bool(ok),
                         "real_path": d["real_path"], "why": (why or "")[:250]})
            out[nm] = {"real_path": d["real_path"], "content_rule_alone": d["ok"], "refused": not r_ok,
                       "refused_by_the_path_rule": by_path}
    finally:
        for p in made:
            if os.path.lexists(p):
                os.unlink(p)
        shutil.rmtree(tmpd, ignore_errors=True)
    left = [p for p in made if os.path.lexists(p)]
    rows.append({"field": f"A1 ({stage}): every copy made for the probes is deleted", "expected": [], "got": left,
                 "ok": not left})
    return rows, out


def proof_i():
    rows = []
    st = G.self_test(spec_sha=SPEC_SHA, protocol=PROTOCOL)
    for k, v in st.items():
        if isinstance(v, dict):
            rows.append({"field": f"guard.{k}", "expected": v["expected_allowed"], "got": v["allowed"], "ok": v["ok"],
                         **({"why": v["why"]} if v.get("why") else {})})
    prot = st.get("PROTOCOL_V3.md_as_it_stands", {})
    refused_p = prot.get("ok") is True and st["cut_2026_LOOK_DECLARED_PROTOCOL_V3.md_as_it_stands_refused"]["ok"]
    rows.append({"field": "F1: LOOK_DECLARED=PROTOCOL_V3.md as it stands is refused for the look (resolve_cut with an "
                          "environment dict; the process environment is never set)", "expected": True,
                 "got": refused_p, "ok": refused_p, "protocol_sha256": prot.get("sha256"),
                 "protocol_contains_autopsy_HI_look": prot.get("contains_track"),
                 "protocol_contains_the_spec_sha256": prot.get("contains_spec_sha256"), "spec_sha256": SPEC_SHA})
    pr, pout = plan_tests()
    rows += pr
    a1_rows, a1_out = declared_file_probes("before_write")
    rows += a1_rows
    rows += guard_probes()
    # the entry point itself, asked for the look without a declared addendum: refused before anything is read
    import subprocess
    env = {k: v for k, v in os.environ.items() if k != "LOOK_DECLARED"}
    p = subprocess.run([sys.executable, os.path.join(HERE, "look.py"), "--cut", "2026-01-01"], env=env,
                       capture_output=True, text=True, timeout=600, cwd="/tmp")
    refused_cli = p.returncode != 0 and "REFUSED" in (p.stdout + p.stderr)
    rows.append({"field": "look.py --cut 2026-01-01 without LOOK_DECLARED: refused (exit code, message)",
                 "expected": True, "got": refused_cli, "ok": refused_cli,
                 "message": (p.stdout + p.stderr).strip()[-300:]})
    p2 = subprocess.run([sys.executable, os.path.join(HERE, "look.py"), "--cut", "2026-01-02"], env=env,
                        capture_output=True, text=True, timeout=600, cwd="/tmp")
    refused_cli2 = p2.returncode != 0 and "REFUSED" in (p2.stdout + p2.stderr)
    rows.append({"field": "look.py --cut 2026-01-02: refused (after the 2026 boundary)", "expected": True,
                 "got": refused_cli2, "ok": refused_cli2, "message": (p2.stdout + p2.stderr).strip()[-300:]})
    after = hi_lines()
    rows.append({"field": "val_access.log lines mentioning / with track autopsy_HI_look: before and after the proofs",
                 "expected": [[0, 0], [0, 0]], "got": [list(LOG_BEFORE), list(after)],
                 "ok": tuple(LOG_BEFORE) == (0, 0) and tuple(after) == (0, 0)})
    started = G.started_markers()
    rows.append({"field": "no '.started' marker in results/r2/validation_hi/look/", "expected": [], "got": started,
                 "ok": not started})
    rd = G.reads()
    cutp = pd.Timestamp(CUT, tz="UTC")
    pq_reads = [r for r in rd if r["kind"] in ("pandas.read_parquet", "pyarrow.parquet.read_table",
                                               "pyarrow.parquet.read_pandas", "pyarrow.parquet.ParquetDataset")]
    bad = [r for r in pq_reads if r["bound"] is None or pd.Timestamp(r["bound"]) > cutp]
    rows.append({"field": "F3b every parquet read of the process carries a row filter (ts | entry_time | t_dec) < t with "
                          "t <= 2022-01-01", "expected": 0, "got": len(bad), "ok": not bad, "parquet_reads": len(pq_reads)})
    csv = [r for r in rd if r["kind"].startswith("pandas.read_") and r not in pq_reads]
    bad_csv = [r for r in csv if r["path"] not in G.CSV_ALLOW and not os.path.isabs(r["path"])]
    rows.append({"field": "F3d every CSV read under lab/ is on the allowlist (results/r2/autopsy/payoff/variants_table.csv)",
                 "expected": 0, "got": len(bad_csv), "ok": not bad_csv, "csv_reads": [r["path"] for r in csv]})
    opens = sorted({r["path"] for r in rd if r["kind"] == "open"})
    bad_open = [p for p in opens if p.startswith("data/") or p.startswith("holdout_raw") or "2026" in os.path.basename(p)]
    rows.append({"field": "every open() under lab/ of the process: none under lab/data or the holdout, none dated 2026",
                 "expected": 0, "got": len(bad_open), "ok": not bad_open})
    return {"what": "the guard of the harness (vhi_guard): F1 the declaration bound to the spec (PROTOCOL_V3.md as it "
                    "stands refused), A1 only the protocol's real path accepted as LOOK_DECLARED (the harness's "
                    "outputs and copies of them refused, also once they quote this run's spec sha256: rows "
                    "'A1 (after_write)', added after those files are written), F2 run once / fixed output / second "
                    "access, F3 / A2 / A3 the hardened read guard (probes refused before any byte is read: the "
                    "holdout component rule and lab/ CSVs through open() included), CUT rules, the access log "
                    "untouched, every read of the process with its filter",
            "plan_tests": pout, "A1_before_write": a1_out, "opens_under_lab": opens, "reads": rd, **verdict(rows),
            "rows": rows}


# ------------------------------------------------------------------------------------------------- (j)
TEN_PLUS = RUN.TEN_KEYS + [K1_KEY, "orb_asia_2d_buf10__ethusd", "orb_asia_2d_buf10__btcusd"]
SA_IDS = ["ocm4_T1", "F1eth_H2", "brk72btc_S0.75r", "donch4h_S0.75r", "orbxau_S0.75r"]
SA_SLEEVES = ["ocm4__us100@payoff", "ocm4__us100+T1", "F1_brk_ridge_filter__ethusd@payoff",
              "F1_brk_ridge_filter__ethusd+H2", "brk72_24h_wd__btcusd@payoff", "brk72_24h_wd__btcusd+S0.75r",
              "donch4h_stop__xauusd@payoff", "donch4h_stop__xauusd+S0.75r", "orb_asia_2d_buf10__xauusd@payoff",
              "orb_asia_2d_buf10__xauusd+S0.75r"]
# A5: files the look must record, relative to lab/ (harness, lenses, strategy modules, rules registry, simulator)
CODE_EXPECTED = (["r2/tracks/validation_hi/" + f for f in ("look.py", "vhi_guard.py", "vhi_run.py", "vhi_sleeves.py",
                                                            "vhi_lens.py", "vhi_data.py", "vhi_book.py", "vhi_stakes.py",
                                                            "vhi_verdicts.py")]
                 + ["r2/tracks/autopsy/synthesis_B/common.py", "r2/tracks/autopsy/synthesis_B/s1_run.py",
                    "r2/tracks/autopsy/synthesis_B/s2_portfolio.py", "r2/tracks/autopsy/payoff/common.py",
                    "r2/tracks/autopsy/payoff/variants.py", "r2/tracks/autopsy/synthesis_A/portfolio.py",
                    "r2/tracks/idx_us/strategy.py", "r2/tracks/crypto/strategy.py", "r2/tracks/ml/strategy.py",
                    "r2/tracks/leadlag/strategy.py", "r2/tracks/overnight/strategy.py", "tracks/trend/strategy.py",
                    "tracks/orb/strategy.py", "r2/recalc.py", "goldlab/sim.py", "goldlab/r2.py"])


def proof_j(res, sa):
    """The single command of the look, run at CUT 2022-01-01 (a rehearsal: nothing logged) with the spec AS IT STANDS
    (its list changes_in_look: K1, K2, K3 and synthesis A's five), in its own process: it runs exactly the ten, K1,
    K2, K3, the five changed sleeves and their references, and their portfolios / comparisons / verdicts; every
    number it shares with the proofs' run (every change) is equal; the check first and synthesis A's block are in its
    output; A5: its meta records the sha256 of every harness, lens and strategy file it imported."""
    import subprocess
    env = {k: v for k, v in os.environ.items() if k != "LOOK_DECLARED"}
    out = os.path.join(OUT, "rehearsal", "autopsy_HI_look__cut2022-01-01.json")
    t0 = time.time()
    p = subprocess.run([sys.executable, os.path.join(HERE, "look.py"), "--cut", "2022-01-01", "--spec", SPEC],
                       env=env, capture_output=True, text=True, timeout=3000, cwd="/tmp")
    rows = [{"field": "look.py --cut 2022-01-01 exits 0", "expected": 0, "got": p.returncode, "ok": p.returncode == 0,
             "stderr_tail": p.stderr.strip()[-500:]}]
    detail = {}
    if p.returncode == 0:
        with open(out) as f:
            theirs = json.load(f, parse_constant=lambda c: None)
        mine = RUN.canonical(RUN.strip_private(res))
        file_list = json.load(open(SPEC))["changes_in_look"]
        ch = theirs["changes"]
        rows.append({"field": "the rehearsal ran the spec's list changes_in_look as it stands", "expected": file_list,
                     "got": ch["in_look"], "ok": ch["in_look"] == file_list})
        want_p = ["P0", "P1", "P2", "P0+orb_eth", "P0+orb_btc", "P0|F1eth_H2", "P0|ocm4_T1", "P0|donch4h_S0.75r",
                  "P0|brk72btc_S0.75r", "P0|orbxau_S0.75r"]
        want_sl = sorted(TEN_PLUS + SA_SLEEVES)
        rows.append({"field": "with K1, K2, K3 and synthesis A's five: the ten + K1 + K2 + K3 sleeves and the five "
                              "changed sleeves with their '@payoff' references (not the refuted nq T1 / noise30 S0.25), "
                              "no stake rule, no plugin; portfolios P0, P1, P2, P0+orb_eth, P0+orb_btc and P0|<each of "
                              "the five>",
                     "expected": [want_sl, want_p], "got": [sorted(theirs["sleeves"]), list(theirs["portfolios"])],
                     "ok": sorted(theirs["sleeves"]) == want_sl and list(theirs["portfolios"]) == want_p
                     and not any(v.get("stakes") for v in theirs["meta"]["spec"]["portfolios"].values())
                     and not theirs["meta"]["spec"].get("plugins") and not theirs["plugins"]})
        want_v = ["K1", "K2", "K3"] + SA_IDS
        vd = theirs["verdicts"]
        okv = (sorted(vd) == sorted(want_v) and all(vd[c].get("declared") and not vd[c].get("error") for c in want_v)
               and all(vd[c]["kind"] == "synthesis_A_change" for c in SA_IDS))
        rows.append({"field": "verdicts: one per listed change, each with its declared criterion and no error "
                              "(synthesis_B's for K1-K3, synthesis A's V1-V5 for the five)", "expected": want_v,
                     "got": list(vd), "ok": bool(okv)})
        for part in ("portfolios", "comparisons", "sleeve_comparisons", "verdicts"):
            names = list(theirs[part])
            same_part = bool(names) and all(theirs[part][n] == mine[part].get(n) for n in names)
            rows.append({"field": f"look.py rehearsal == proofs run: {part} ({', '.join(names)})", "expected": True,
                         "got": same_part, "ok": same_part})
        same_off = theirs["official"] == mine["official"]
        rows.append({"field": "look.py rehearsal == proofs run: official check of the ten", "expected": True,
                     "got": same_off, "ok": same_off})
        cf = theirs.get("check_first") or {}
        rows.append({"field": "the check first (synthesis A) is the FIRST key of the rehearsal's output, computed and "
                              "passed, equal to the proofs run's", "expected": ["check_first", True, True, True],
                     "got": [next(iter(theirs)), cf.get("computed"), cf.get("passed"), cf == mine.get("check_first")],
                     "ok": next(iter(theirs)) == "check_first" and cf.get("computed") is True and cf.get("passed") is True
                     and cf == mine.get("check_first")})
        same_sa = theirs.get("synthesis_A") == mine.get("synthesis_A") and theirs["synthesis_A"].get("changes") == SA_IDS \
            and not theirs["synthesis_A"].get("error")
        rows.append({"field": "look.py rehearsal == proofs run: synthesis A's block (the passing changes together, item "
                              "6), its five changes in the spec's order, no error", "expected": True, "got": bool(same_sa),
                     "ok": bool(same_sa)})
        # A5: the code the rehearsal executed
        code = theirs["meta"].get("code_sha256") or {}
        missing = [f for f in CODE_EXPECTED if f not in code]
        wrong = [f for f, v in code.items() if v.get("sha256") != RUN.sha256(os.path.join(LAB, f))]
        errs = [f for f, v in code.items() if v.get("error")]
        rows.append({"field": "A5: the rehearsal's meta records the sha256 of every harness, lens and strategy file it "
                              "imported (the harness, synthesis_B and payoff lens modules, synthesis A's portfolio.py, "
                              "the seven strategy modules, recalc.py, goldlab), each equal to the file",
                     "expected": [[], [], []], "got": [missing, wrong, errs], "ok": not missing and not wrong and not errs,
                     "files_recorded": len(code)})
        fz = sa["frozen_files_sha256"]
        rec = dict({f: v.get("sha256") for f, v in code.items()}, **(theirs["meta"].get("files_opened_sha256") or {}))
        cmpz = {f: [h, rec.get(f)] for f, h in fz.items() if f in rec}
        okz = bool(cmpz) and all(a == b for a, b in cmpz.values())
        rows.append({"field": "A5: every file synthesis A froze that the rehearsal imported or opened has synthesis A's "
                              "frozen sha256 (portfolio.py, goldlab, recalc.py, costs, the strategies, the F1 model)",
                     "expected": True, "got": okz, "ok": okz, "compared": sorted(cmpz),
                     "frozen_not_used_by_the_harness": sorted(f for f in fz if f not in rec)})
        def untimed(run):                                # every field of a sleeve run but its timing ('sec')
            return {kk: ({i: w for i, w in v.items() if i != "sec"} if kk == "info" else v) for kk, v in run.items()}

        same_sl = all(untimed(theirs["sleeves"][k]["runs"][r]) == untimed(mine["sleeves"][k]["runs"][r])
                      for k in theirs["sleeves"] for r in theirs["sleeves"][k]["runs"])
        rows.append({"field": "look.py rehearsal == proofs run: every sleeve run (stats and info)", "expected": True,
                     "got": same_sl, "ok": same_sl})
        rows.append({"field": "rehearsal did not log an access (meta.is_look False, no marker)", "expected": [False, None],
                     "got": [theirs["meta"]["is_look"], theirs["meta"]["marker"]],
                     "ok": theirs["meta"]["is_look"] is False and theirs["meta"]["marker"] is None})
        rd = theirs["meta"]["reads"]
        pqr = [r for r in rd if r["kind"] in ("pandas.read_parquet", "pyarrow.parquet.read_table")]
        badr = [r for r in pqr if r["bound"] is None or pd.Timestamp(r["bound"]) > pd.Timestamp(CUT, tz="UTC")]
        csvr = [r for r in rd if r["kind"].startswith("pandas.read_c")]
        rows.append({"field": "the rehearsal's every parquet read carries a row filter at or before 2022-01-01; it read "
                              "no CSV", "expected": [0, 0], "got": [len(badr), len(csvr)],
                     "ok": not badr and not csvr, "parquet_reads": len(pqr)})
        detail = {"changes": ch, "check_first": theirs.get("check_first"), "verdicts": theirs["verdicts"],
                  "synthesis_A": theirs.get("synthesis_A"), "reads": rd, "code_sha256": code,
                  "files_opened_sha256": theirs["meta"].get("files_opened_sha256")}
    return {"what": "the look's entry point (look.py) run end to end at CUT 2022-01-01 in its own process with the spec "
                    "as it stands (changes_in_look K1, K2, K3 and synthesis A's five): the right sleeves, portfolios "
                    "and verdicts, the check first and synthesis A's block, the same numbers as the proofs' run, "
                    "nothing logged, the imported code's sha256 recorded (A5)", "output": out,
            "seconds": round(time.time() - t0, 1), "detail": detail, **verdict(rows), "rows": rows}


# ------------------------------------------------------------------------------------------------- (k)
SCRATCH = os.environ.get("VHI_SCRATCH", "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/vhi")


def proof_k(res):
    """MOVING THE CUT, as the look will: the same spec run by look.py at CUT 2021-01-01 (in sample) must give, for
    every sleeve, chain, cost mode and execution, exactly the trades of the CUT 2022-01-01 run that entered and
    closed inside the shorter frame -- the harness's results do not depend on where the frame ends except for the
    trades it cannot finish. K1's fit for the year starting at that CUT must be the CUT-2022 run's 2021 fold."""
    import subprocess
    spec = json.load(open(SPEC))
    spec["name"] = "pseudo_look_cut2021"
    spec["changes_in_look"] = list(RUN.available_changes(spec))      # every change, as the proofs' run
    spec["windows"]["in_sample"] = {"eval": ["2020-01-01", "2021-01-01"], "years": [2020], "judge_years": [2020],
                                    "splits": [["h1_2020", "2020-01-01", "2020-07-01"], ["h2_2020", "2020-07-01", "2021-01-01"]]}
    for s in spec["sleeves"]:
        if (s.get("change") or {}).get("kind") == "k1_riskbp":    # binding at CUT 2021 (the fit for 2021), A4 form
            s["change"]["declared_T"] = {"2021": {"q_hi": 465.1178, "skip": "hi", "n_train": 1703}}
    os.makedirs(SCRATCH, exist_ok=True)
    sp = os.path.join(SCRATCH, "pseudo_look_cut2021_spec.json")
    with open(sp, "w") as f:
        json.dump(spec, f, indent=1)
    env = {k: v for k, v in os.environ.items() if k != "LOOK_DECLARED"}
    t0 = time.time()
    p = subprocess.run([sys.executable, os.path.join(HERE, "look.py"), "--cut", "2021-01-01", "--spec", sp], env=env,
                       capture_output=True, text=True, timeout=3000, cwd="/tmp")
    rows = [{"field": "look.py --cut 2021-01-01 exits 0", "expected": 0, "got": p.returncode, "ok": p.returncode == 0,
             "stderr_tail": p.stderr.strip()[-500:]}]
    out = {"spec": sp, "seconds": round(time.time() - t0, 1)}
    if p.returncode != 0:
        return {"what": proof_k.__doc__, "detail": out, **verdict(rows), "rows": rows}
    jp = os.path.join(OUT, "rehearsal", "pseudo_look_cut2021__cut2021-01-01.json")
    with open(jp) as f:
        r21 = json.load(f, parse_constant=lambda c: None)
    t21 = D.trades_file(r21["meta"]["trades_file"])
    last = {sym: pd.Timestamp(v["last"]) for sym, v in r21["frames"].items()}
    cut21 = pd.Timestamp("2021-01-01", tz="UTC")
    n_keys, n_trades, bad = 0, 0, []
    for (k, chain, mode, ex), t22 in res["_trades"].items():
        sym = res["_meta"][k]["sym"]
        a = t22[(t22.entry_time < cut21) & (t22.exit_time < last[sym])].sort_values(["entry_time", "side"], kind="stable")
        b = t21[(t21.sleeve == k) & (t21.chain == chain) & (t21["mode"] == mode) & (t21["exec"] == ex)]
        b = b.sort_values(["entry_time", "side"], kind="stable")
        ok = len(a) == len(b)
        if ok and len(a):
            ok = bool((pd.DatetimeIndex(a.entry_time).as_unit("ns") == pd.DatetimeIndex(b.entry_time).as_unit("ns")).all()
                      and (pd.DatetimeIndex(a.exit_time).as_unit("ns") == pd.DatetimeIndex(b.exit_time).as_unit("ns")).all()
                      and (a.side.to_numpy() == b.side.to_numpy()).all()
                      and (a.reason.astype(str).to_numpy() == b.reason.astype(str).to_numpy()).all()
                      and np.allclose(a.R.to_numpy(float), b.R.to_numpy(float), rtol=0, atol=1e-12))
        n_keys += 1
        n_trades += len(a)
        if not ok:
            bad.append({"key": f"{k}/{chain}/{mode}/{ex}", "n_cut2022_restricted": int(len(a)), "n_cut2021": int(len(b))})
    rows.append({"field": "every sleeve x chain x mode x execution: trades at CUT 2021 == trades of the CUT 2022 run "
                          "entered and closed inside the 2021 frame", "expected": 0, "got": len(bad), "ok": not bad,
                 "chains_compared": n_keys, "trades_compared": n_trades, "mismatches": bad[:20]})
    off_ok = all(v["reproduced"] for v in r21["official"].values())
    rows.append({"field": "official check at CUT 2021: the ten sleeves reproduced (rows still open at the cut "
                          "counted, not read)", "expected": True, "got": off_ok, "ok": off_ok})
    k1 = [s for s in r21["sleeves"].values() if (s["spec"].get("change") or {}).get("kind") == "k1_riskbp"]
    if k1:
        dg = k1[0]["runs"]["fp/lab"]["info"]["change_diag"]
        f21 = dg["fit_for_year_starting_at_cut"]
        f22 = res["sleeves"]["brk72_24h_wd__ethusd+K1"]["runs"]["fp/lab"]["info"]["change_diag"]["folds"]["2021"] \
            if "2021" in res["sleeves"]["brk72_24h_wd__ethusd+K1"]["runs"]["fp/lab"]["info"]["change_diag"]["folds"] \
            else res["sleeves"]["brk72_24h_wd__ethusd+K1"]["runs"]["fp/lab"]["info"]["change_diag"]["folds"][2021]
        same_fit = all(f21[q] == f22[q] for q in ("q_lo", "q_hi", "E_lo", "E_hi", "skip", "n_train"))
        rows.append({"field": "K1: fit for the year starting at CUT 2021 == the CUT-2022 run's 2021 fold", "expected": True,
                     "got": same_fit, "ok": same_fit, "fit_cut2021": f21})
        c21 = dg["declared_T_check"]["2021"]
        rows.append({"field": "K1: declared fit checked at CUT 2021 (T(2021) = 465.1178, skip 'hi', n_train 1703: A4 at a "
                              "moved CUT)", "expected": [True, True, True],
                     "got": [c21["same_to_0.01bp"], c21.get("same_skip_side"), c21.get("same_n_train")],
                     "ok": c21["same_to_0.01bp"] is True and c21.get("same_skip_side") is True
                     and c21.get("same_n_train") is True})
    out["frames_cut2021"] = r21["frames"]
    out["output"] = jp
    return {"what": proof_k.__doc__.strip(), "detail": out, **verdict(rows), "rows": rows}


# ------------------------------------------------------------------------------------------------- (l)
def proof_l(res, sb):
    """F10: the verdicts block. Every criterion value equals the run's own statistic (rounded as the run reports it)
    and synthesis_B's published figure where there is one; a change without a declared criterion is reported as
    such. In sample the verdicts only check the machinery (the window is 2018-02 .. 2021-12, not the look's)."""
    V = res["verdicts"]
    rows, out = [], {"verdicts": RUN.canonical(V)}
    sl = res["sleeves"]
    c1 = sb["sleeve_runs"]["C1_K1_riskbp_brk72_ethusd"]

    def chk(field, got, exp, nd):
        ok = got is not None and exp is not None and round(float(got), nd) == round(float(exp), nd)
        rows.append({"field": field, "expected": exp, "got": got, "ok": bool(ok)})

    # K1
    k1 = V["K1"]
    crit = {r["criterion"]: r for r in k1["criteria"]}
    for mode in ("fp", "stress"):
        r = crit[f"{mode}/lab: expectancy per trade with the skip > without"]
        run = sl[K1_KEY]["runs"][f"{mode}/lab"]
        chk(f"K1 {mode}: expectancy with the skip == the run's var window (synthesis_B C1 var_window)", r["value"],
            c1[mode]["var_window"]["exp"], 4)
        chk(f"K1 {mode}: expectancy without == the run's base window (synthesis_B C1 base_window)", r["reference"],
            c1[mode]["base_window"]["exp"], 4)
        chk(f"K1 {mode}: same, against the run's own sleeve stats", r["value"], run["main"]["window"]["exp"], 4)
        r2 = crit[f"{mode}/lab: total R with the skip >= without"]
        chk(f"K1 {mode}: total R with / without the skip == synthesis_B C1 var / base window",
            r2["value"], c1[mode]["var_window"]["total"], 2)
        chk(f"K1 {mode}: total R without the skip == synthesis_B C1 base window", r2["reference"],
            c1[mode]["base_window"]["total"], 2)
    rs = crit["skipped signals taken alone (FP costs): mean R < that of the kept signals"]
    k1x = sl[K1_KEY]["runs"]["fp/lab"]["k1"]
    chk("K1: skipped signals alone (mean R) == the run's k1 extras", rs["value"], k1x["skipped_signals_alone"]["exp"], 4)
    chk("K1: kept signals alone (mean R) == the run's k1 extras", rs["reference"], k1x["kept_signals_alone"]["exp"], 4)
    rows.append({"field": "K1: the skipped / kept signals are labelled with FP costs", "expected": "fp",
                 "got": rs.get("labels_mode"), "ok": rs.get("labels_mode") == "fp"})
    # K2, K3
    for cid, key, tag, with_ in (("K2", "orb_asia_2d_buf10__ethusd", "N1_K2_orb_ethusd", "P0+orb_eth"),
                                 ("K3", "orb_asia_2d_buf10__btcusd", "N2_K3_orb_btcusd", "P0+orb_btc")):
        v = V[cid]
        crit = {r["criterion"].split(": ", 1)[1]: r for r in v["criteria"]}
        n = sb["sleeve_runs"][tag]
        run = sl[key]["runs"]
        chk(f"{cid}: PF (FP) == synthesis_B {tag} window pf", crit["profit factor >= 1.06"]["value"], n["fp"]["window"]["pf"], 3)
        chk(f"{cid}: expectancy (FP) == synthesis_B window exp", crit["expectancy per trade > 0"]["value"],
            n["fp"]["window"]["exp"], 4)
        chk(f"{cid}: every-signal expectancy == the run's every-signal chain",
            crit["every-signal expectancy (each signal taken alone) > 0"]["value"], run["fp/lab"]["every_signal"]["exp"], 4)
        yr = crit["total R positive in at least 3 of the 4 years"]["total_R_by_year"]
        exp_y = {int(y): w["total"] for y, w in n["fp"]["by_year"].items()}
        oky = all(round(yr[y], 2) == exp_y[y] for y in exp_y) and set(yr) == set(exp_y)
        rows.append({"field": f"{cid}: total R by year (FP) == synthesis_B {tag} by_year", "expected": exp_y,
                     "got": {y: round(x, 2) for y, x in yr.items()}, "ok": bool(oky)})
        chk(f"{cid}: expectancy x1.5 == synthesis_B window exp (stress)",
            crit["expectancy per trade > 0 with costs x1.5"]["value"], n["stress"]["window"]["exp"], 4)
        wk = crit[f"weekly mean / sd of R of {with_} >= that of P0"]
        chk(f"{cid}: weekly mean / sd of {with_} == the run's portfolio metric", wk["value"],
            res["portfolios"][with_]["fp/lab/sum"]["week_mean_over_sd"], 4)
        chk(f"{cid}: weekly mean / sd of P0 == the run's portfolio metric == synthesis_B P0", wk["reference"],
            sb["portfolio"]["results"]["fp"]["P0"]["week_mean_over_sd"], 4)
        lv = v["readings"]["fp/live"]
        chk(f"{cid}: the live reading (FP) == the run's live window expectancy", lv["expectancy"],
            run["fp/live"]["main"]["window"]["exp"], 4)
        rows.append({"field": f"{cid}: the live reading is not a criterion (readings, outside 'criteria')", "expected": True,
                     "got": "as_the_live_program_would" in v["readings"] and len(v["criteria"]) == 6,
                     "ok": "as_the_live_program_would" in v["readings"] and len(v["criteria"]) == 6})
    # every criterion's pass flag is its rule applied to its value (every declared change: K1-K3 and synthesis A's)
    ops = {">": lambda a, b: a > b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b}
    decl = [c for c, v in V.items() if v.get("declared")]
    flags = all(r["pass"] == (r["value"] is not None and r["reference"] is not None and ops[r["rule"]](r["value"], r["reference"]))
                for cid in decl for r in V[cid]["criteria"])
    adopt = all(V[c]["adopted"] == all(r["pass"] for r in V[c]["criteria"]) for c in decl)
    rows.append({"field": "every pass flag == its rule applied to its value and reference; adopted == all pass "
                          f"({', '.join(decl)})", "expected": True, "got": bool(flags and adopt), "ok": bool(flags and adopt)})
    errs = [c for c in decl if V[c].get("error")]
    rows.append({"field": "no criterion raised (verdict entries without 'error')", "expected": [], "got": errs,
                 "ok": not errs})
    undeclared = [c for c, v in V.items() if not v.get("declared")]
    want_und = [c for c in res["changes"]["in_look"] if c not in (res["_spec"].get("criteria") or {})]
    rows.append({"field": "the changes without a declared criterion (here only the refuted nq_T1 and noise30_S0.25, "
                          "rehearsed but not listed) are reported 'declared: false' (the hook)",
                 "expected": want_und, "got": undeclared,
                 "ok": undeclared == want_und and sorted(undeclared) == sorted(["nq_T1", "noise30_S0.25"])})
    out["in_sample_adopted"] = {c: V[c]["adopted"] for c in decl}
    return {"what": proof_l.__doc__.strip(), "detail": out, **verdict(rows), "rows": rows}


# ------------------------------------------------------------------------------------------------- (m)
SA_KEY = {"ocm4_T1": ("ocm4:us100", "T1"), "F1eth_H2": ("F1_brk_ridge_filter:ethusd", "H2"),
          "brk72btc_S0.75r": ("brk72_24h_wd:btcusd", "S0.75r"), "donch4h_S0.75r": ("donch4h_stop:xauusd", "S0.75r"),
          "orbxau_S0.75r": ("orb_asia_2d_buf10:xauusd", "S0.75r")}


def _near(got, exp, units=1.0):
    """got within `units` units of the last decimal of exp (exp as published, rounded)."""
    if exp is None or got is None:
        return got is None and exp is None
    if isinstance(exp, (int, np.integer)) and not isinstance(exp, bool):
        return isinstance(got, (int, np.integer, float)) and float(got) == float(exp)
    d = decimals(exp)
    return abs(float(got) - float(exp)) <= units * 10 ** (-d) * 1.000001 + 1e-12


def proof_m(res, sa):
    """synthesis A's criteria V1-V5 (res['verdicts'], kind synthesis_A_change) and its report (res['synthesis_A']) on
    the in-sample window 2018-02..2021-12, against synthesis A's published in-sample rehearsal of its own criteria
    (synthesis_A.json criteria_rehearsal_in_sample, main window, FP and x1.5: sleeve weekly Sharpe unchanged / changed,
    ten-sleeve portfolio weekly Sharpe unchanged / with the change at its frozen factor, total R at a constant stake,
    the equal-swing gain by entry year, V1, V2, V3, V5), its changed sleeves (changed_sleeves_detail), its frozen
    equal-swing factors (portfolio.equal_swing_factors, reproduced from the in-sample weekly sd as synthesis A computes
    them), its portfolios through its own frozen measures() (unchanged, all five at a constant stake and at equal
    swing, each change alone); the check first reported first and gating synthesis A's verdicts ('stop and report')."""
    V, S, spec, W = res["verdicts"], res["synthesis_A"], res["_spec"], res["_W"]
    crit = spec["criteria"]
    cr, det, port = sa["criteria_rehearsal_in_sample"], sa["changed_sleeves_detail"], sa["portfolio"]
    rows, out = [], {}
    LFL = "portfolio_like_for_like (P0 with the unchanged sleeve in the changed sleeve's convention, not a criterion)"

    def add(field, *, got, exp, ok, **kw):
        rows.append({"field": field, "expected": exp, "got": got, "ok": bool(ok), **kw})

    ms_ = S.get("measures") or {}
    add("synthesis A's block computed without error, its five changes in the spec's order, frozen measures() loaded "
        "with its declared sha256", got=[S.get("changes"), ms_.get("sha256"), S.get("error") or ms_.get("error")],
        exp=[SA_IDS, L.SYNTH_A_PORTFOLIO_SHA256, None],
        ok=S.get("changes") == SA_IDS and ms_.get("sha256") == L.SYNTH_A_PORTFOLIO_SHA256 and not S.get("error")
        and not ms_.get("error"))
    add("the judged weeks are synthesis A's 205 weeks of 2018-02-01..2021-12-31", got=ms_.get("weeks", [0, 0, 0])[2],
        exp=205, ok=ms_.get("weeks", [0, 0, 0])[2] == 205)
    for cid in SA_IDS:
        sk, vv = SA_KEY[cid]
        c, v = crit[cid], V[cid]
        e_all = cr[f"{sk}:{vv}"]["main"]
        f = float(c["frozen_factor"])
        add(f"{cid}: the spec's frozen factor == synthesis A's declared / published factor", got=f,
            exp=port["equal_swing_factors"][sk], ok=f == port["equal_swing_factors"][sk])
        # the factor reproduced as synthesis A computes it: weekly sd of the unchanged and changed sleeves (FP, in sample)
        # rounded to 4 decimals by its measures(), their ratio rounded to 6 decimals
        rep = S["report_item_6"]["fp"][f"sleeve_{cid}"]
        k_rep = round(rep["unchanged"]["weekly_sd_R"] / rep["changed_constant_stake"]["weekly_sd_R"], 6)
        add(f"{cid}: the frozen factor reproduced from this run's in-sample weekly sd (synthesis A's computation)",
            got=k_rep, exp=f, ok=k_rep == f)
        for mode in ("fp", "stress"):
            e, vals = e_all[mode], v["values"][mode]
            sh = vals["sleeve_weekly_sharpe"]
            add(f"{cid} {mode}: sleeve weekly Sharpe [unchanged, changed] == synthesis A's rehearsal",
                got=[round(x, 4) for x in sh], exp=e["sleeve_weekly_sharpe"],
                ok=all(_near(g, x, 0.5) for g, x in zip(sh, e["sleeve_weekly_sharpe"])))
            ps = vals["portfolio_weekly_sharpe_frozen_factor"]
            add(f"{cid} {mode}: ten-sleeve portfolio weekly Sharpe [P0, with the change at its frozen factor] == synthesis "
                "A's rehearsal", got=[round(x, 4) for x in ps], exp=e["portfolio_weekly_sharpe_equal_swing"],
                ok=all(_near(g, x, 0.5) for g, x in zip(ps, e["portfolio_weekly_sharpe_equal_swing"])))
            tr = vals["total_R_constant_stake"]
            add(f"{cid} {mode}: sleeve total R at a constant stake [unchanged, changed] == synthesis A's rehearsal",
                got=[round(x, 2) for x in tr], exp=e["total_R_constant_stake"],
                ok=all(_near(g, x, 0.5) for g, x in zip(tr, e["total_R_constant_stake"])))
            rws = [r for r in v["criteria"] if r["criterion"].split(" ", 1)[1].startswith(f"{mode}/")]
            v1 = all(r["pass"] for r in rws if "weekly Sharpe" in r["criterion"])
            v2 = all(r["pass"] for r in rws if "total R at a constant stake" in r["criterion"])
            add(f"{cid} {mode}: the V1 test (sleeve and portfolio weekly Sharpe up) == synthesis A's rehearsal", got=v1,
                exp=e["V1_gain_per_unit_of_swing"], ok=v1 == e["V1_gain_per_unit_of_swing"])
            add(f"{cid} {mode}: the V2 test (total R not lower) == synthesis A's rehearsal", got=v2,
                exp=e["V2_total_R_not_lower"], ok=v2 == e["V2_total_R_not_lower"])
        e = e_all["fp"]
        r4 = next(r for r in v["criteria"] if r["test"] == "V4")
        g_sa = {int(y): round(round(r4["total_R_changed_by_entry_year"][y], 2) * f
                              - round(r4["total_R_unchanged_by_entry_year"][y], 2), 2) for y in r4["gain_by_entry_year"]}
        exp_g = {int(y): x for y, x in e["equal_swing_gain_by_entry_year"].items()}
        add(f"{cid} fp: the equal-swing gain by entry year (rounded as synthesis A's rehearsal.py) == synthesis A's",
            got=g_sa, exp=exp_g, ok=g_sa == exp_g, unrounded=r4["gain_by_entry_year"])
        yp = f"{r4['value']}/{len(r4['gain_by_entry_year'])}"
        add(f"{cid} fp: years with a positive gain == synthesis A's", got=yp, exp=e["years_positive"],
            ok=yp == e["years_positive"])
        add(f"{cid}: V3 (V1 and V2 with costs x1.5) == synthesis A's", got=v["V"]["V3"], exp=e_all["V3_holds_with_x1_5"],
            ok=v["V"]["V3"] == e_all["V3_holds_with_x1_5"])
        add(f"{cid}: V5 (expectancy > 0, PF >= 1.06) == synthesis A's", got=v["V"]["V5"],
            exp=e["V5_changed_sleeve_exp_pos_and_pf_1_06"], ok=v["V"]["V5"] == e["V5_changed_sleeve_exp_pos_and_pf_1_06"])
        sa_pass = bool(e["V1_gain_per_unit_of_swing"] and e["V2_total_R_not_lower"] and e_all["V3_holds_with_x1_5"]
                       and int(e["years_positive"].split("/")[0]) >= 3 and e["V5_changed_sleeve_exp_pos_and_pf_1_06"])
        add(f"{cid}: adopted (V1-V5 and the check first) == synthesis A's criteria applied to its own rehearsal "
            "(in sample, where the change was picked)", got=v["adopted"], exp=sa_pass, ok=v["adopted"] == sa_pass)
        add(f"{cid}: no rounding tie; the same verdict at synthesis A's rounding",
            got=[v["rounding_tie"], v["same_verdict_at_synthesis_A_rounding"]], exp=[False, True],
            ok=v["rounding_tie"] is False and v["same_verdict_at_synthesis_A_rounding"] is True)
        idt = [v["readings"][f"{m}/lab"]["unchanged_sleeve_identical_to_the_P0_sleeve_in_the_window"] for m in ("fp", "stress")]
        eqp = [v["readings"][f"{m}/lab"][LFL]["equals_P0"] for m in ("fp", "stress")]
        add(f"{cid}: the unchanged sleeve '@payoff' is identical to P0's sleeve in the window (lab, FP and x1.5), so the "
            "like-for-like portfolio's weekly Sharpe is P0's (to 1e-12)", got=idt + eqp, exp=[True, True, True, True],
            ok=all(idt) and all(eqp), diff=[v["readings"][f"{m}/lab"][LFL]["diff_from_P0"] for m in ("fp", "stress")])
        # the changed sleeves' measures (frozen measures() on this run's trades) == changed_sleeves_detail
        for mode in ("fp", "stress"):
            r6 = S["report_item_6"][mode][f"sleeve_{cid}"]
            for lab_, key in (("unchanged", "unchanged"), ("changed", "changed_constant_stake")):
                exp_m = det[sk][f"{lab_}_{mode}_main"]
                got_m = {k: r6[key].get(k) for k in exp_m}
                rows += compare(got_m, exp_m, f"{cid}.{mode}.{lab_}_sleeve (changed_sleeves_detail)")
        # my unrounded criteria values == synthesis A's frozen measures() on the same trades
        for mode in ("fp", "stress"):
            r6, vals = S["report_item_6"][mode][f"sleeve_{cid}"], v["values"][mode]
            ms = [r6["unchanged"]["weekly_sharpe"], r6["changed_constant_stake"]["weekly_sharpe"]]
            mt = [r6["unchanged"]["total_R"], r6["changed_constant_stake"]["total_R"]]
            okk = all(_near(g, x, 0.5) for g, x in zip(vals["sleeve_weekly_sharpe"], ms)) and \
                all(_near(g, x, 0.5) for g, x in zip(vals["total_R_constant_stake"], mt))
            add(f"{cid} {mode}: the verdict's unrounded sleeve weekly Sharpe and total R == synthesis A's frozen measures() "
                "on the same trades", got=[vals["sleeve_weekly_sharpe"], vals["total_R_constant_stake"]], exp=[ms, mt],
                ok=okk)
            onl = S["report_item_6"][mode][f"only_{cid}_equal_swing"]["weekly_sharpe"]
            add(f"{cid} {mode}: the portfolio weekly Sharpe of the verdict == synthesis A's frozen measures() of "
                f"only_{cid}_equal_swing", got=vals["portfolio_weekly_sharpe_frozen_factor"][1], exp=onl,
                ok=_near(vals["portfolio_weekly_sharpe_frozen_factor"][1], onl, 0.5))
        # each change alone (FP), against synthesis A's portfolio.each_change_alone_weekly_sharpe
        for sc in ("constant_stake", "equal_swing"):
            got = S["report_item_6"]["fp"][f"only_{cid}_{sc}"]["weekly_sharpe"]
            exp = port["each_change_alone_weekly_sharpe"][f"only_{sk}:{vv}_{sc}"]["main"]
            add(f"{cid} fp: weekly Sharpe of the ten with only this change at a {sc.replace('_', ' ')} == synthesis A's",
                got=got, exp=exp, ok=_near(got, exp, 1.0))
    # the portfolios (frozen measures() on this run's books) == synthesis A's portfolio.main_2018_02_to_2021_12
    pm = port["main_2018_02_to_2021_12"]
    for mode in ("fp", "stress"):
        for nm in ("unchanged", "all_five_constant_stake", "all_five_equal_swing"):
            got_m, exp_m = S["report_item_6"][mode][nm], pm[nm][mode]
            # synthesis A scaled by the unrounded ratio, the look by the 6-decimal frozen factor: one unit of the last
            # published decimal for the equal-swing figures, exact otherwise
            units = 1.0 if nm.endswith("equal_swing") else 0.5
            for k, x in exp_m.items():
                if isinstance(x, dict):
                    for y, xv in x.items():
                        gv = (got_m.get(k) or {}).get(int(y), (got_m.get(k) or {}).get(str(y)))
                        add(f"{mode}.{nm}.{k}.{y} == synthesis A's portfolio", got=gv, exp=xv, ok=_near(gv, xv, units))
                else:
                    add(f"{mode}.{nm}.{k} == synthesis A's portfolio", got=got_m.get(k), exp=x,
                        ok=_near(got_m.get(k), x, units))
    # in sample every change passes: the passing changes together are the five; the headline is the all-five portfolio
    same5 = S["report_item_6"]["fp"].get("passing_equal_swing") == S["report_item_6"]["fp"].get("all_five_equal_swing")
    add("in sample (where the changes were picked) all five pass, so the 'passing together' portfolio is the all-five one",
        got=[S.get("passing"), same5], exp=[SA_IDS, True], ok=S.get("passing") == SA_IDS and same5)
    hd = (S.get("together_vs_unchanged_headline") or {}).get("fp", {})
    hw = hd.get("weekly_sharpe_unchanged_vs_together_equal_swing")
    add("the headline 'together vs unchanged' (FP) is P0 2.8729 against the five together at equal swing 3.4777",
        got=hw, exp=[2.8729, 3.4777], ok=hw is not None and all(_near(g, x, 1.0) for g, x in zip(hw, [2.8729, 3.4777])))
    # the check first: first key, computed, passed, and gating synthesis A's verdicts
    cf = res["check_first"]
    add("the check first (synthesis A's '3. CHECK FIRST', the official check) is computed and passes on the ten, "
        "whole frame and window", got=[cf["computed"], cf["passed"], cf["failed_or_missing"]], exp=[True, True, []],
        ok=cf["computed"] and cf["passed"] and not cf["failed_or_missing"])
    add("the check first is the first key of the run's result", got=next(iter(res)), exp="check_first",
        ok=next(iter(res)) == "check_first")
    cfp = all(V[c]["check_first_passed"] for c in SA_IDS)
    add("each synthesis A verdict records the check first as passed", got=cfp, exp=True, ok=cfp)
    # a failed check first, simulated on a copy of the result: synthesis A's changes are not judged, K1-K3 untouched,
    # the status says STOP AND REPORT (pure: no data read)
    fake = dict(res)
    off = copy.deepcopy(res["official"])
    k0 = RUN.TEN_KEYS[0]
    off[k0]["reproduced"] = False
    fake["official"] = off
    cf_bad = RUN.check_first(res["_spec"], fake)
    fake["check_first"] = cf_bad
    vbad = VD.compute(res["_spec"], fake, W)
    okb = (cf_bad["passed"] is False and cf_bad["status"].startswith("FAILED -- STOP AND REPORT")
           and cf_bad["failed_or_missing"] == [k0]
           and all(vbad[c]["adopted"] is None and vbad[c].get("stopped_by_check_first") for c in SA_IDS)
           and all(vbad[c]["adopted_if_judged"] == V[c]["adopted"] for c in SA_IDS)
           and all(RUN.canonical(vbad[c]) == RUN.canonical(V[c]) for c in ("K1", "K2", "K3")))
    add("a failed check first (simulated on a copy: one official sleeve not reproduced) -> status 'FAILED -- STOP AND "
        "REPORT', synthesis A's five not judged (adopted null, values kept), K1-K3 unchanged", got=bool(okb), exp=True,
        ok=okb, status=cf_bad["status"][:200])
    cf_missing = RUN.check_first(res["_spec"], dict(res, official={k: v for k, v in res["official"].items() if k != k0}))
    add("a check first with a sleeve missing is not passed", got=cf_missing["passed"], exp=False,
        ok=cf_missing["passed"] is False)
    out["verdicts"] = {c: RUN.canonical(V[c]) for c in SA_IDS}
    out["synthesis_A"] = RUN.canonical({k: v for k, v in S.items() if k != "report_item_6"})
    out["check_first"] = cf
    return {"what": proof_m.__doc__.strip(), "detail": out, **verdict(rows), "rows": rows}


# ------------------------------------------------------------------------------------------------- main
def main():
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    raw = open(SPEC, "rb").read()
    assert hashlib.sha256(raw).hexdigest() == SPEC_SHA, "look_spec.json changed while the proofs ran"
    spec_file = json.loads(raw)
    spec = copy.deepcopy(spec_file)
    spec["changes_in_look"] = list(RUN.available_changes(spec))      # every available change is rehearsed (in memory)
    sb = json.load(open(SYNTH_B))
    sa = json.load(open(SYNTH_A))
    res = RUN.run_spec(spec, cut)
    print(f"run_spec done [{time.time() - t0:.0f}s]", flush=True)
    rows_g, out_g, signals, k1x = frames_pass(res, sb)
    print(f"frames pass done [{time.time() - t0:.0f}s]", flush=True)
    proofs = {}
    proofs["a_official_trades"] = proof_a(res, sb)
    proofs["b_K1"] = proof_b(res, sb, k1x)
    proofs["c_K2_K3"] = proof_c(res, sb)
    proofs["d_payoff_variants"] = proof_d(res)
    proofs["e_portfolios_P0_P1_P2"] = proof_e(res, sb)
    proofs["f_capped_account"] = proof_f(res)
    proofs["g_live_execution"] = {"what": "the live execution (entry one minute late at market, Friday 16:50 New "
                                          "York close): K2 run this way reproduces the verifiers' figures quoted in "
                                          "synthesis_B (392 trades, +142.1 R; x1.5 +127.9 R) and the harness's "
                                          "declared default is that run without the trade still open at the end of "
                                          "2021; the alternative chain resolver ('rule') returns the official chain "
                                          "trade for trade when there is no delay and no Friday close, and differs "
                                          "from the default only by signals at the previous trade's exit minute; "
                                          "review F7: the Friday block tested on the decision instant as well (a "
                                          "synthetic order shows the rule acting; no in-sample signal is concerned)",
                                  "detail": out_g, **verdict(rows_g), "rows": rows_g}
    proofs["h_stakes"] = proof_h(res, signals)
    proofs["i_guard"] = proof_i()
    proofs["j_entry_point_rehearsal"] = proof_j(res, sa)
    proofs["k_moving_the_cut"] = proof_k(res)
    proofs["l_verdicts"] = proof_l(res, sb)
    proofs["m_synthesis_A_criteria"] = proof_m(res, sa)
    files = {k: os.path.join(OUT, f"proof_{k}.json") for k in proofs}
    rehearsal = RUN.strip_private(res)
    rehearsal["note"] = ("look_spec.json run at CUT 2022-01-01 on its in-sample windows by the look's own code path, "
                         "with EVERY available change (its list changes_in_look replaced in memory by all of them; the "
                         "list as it stands is rehearsed by proof j): every number is in sample")
    rehearsal["imported_code_sha256"] = RUN.imported_code_sha256()

    def write_all():
        for k, v in proofs.items():
            jdump(v, os.path.basename(files[k]))
        index = {"cut": str(cut), "spec": SPEC, "spec_sha256": RUN.sha256(SPEC), "seconds": round(time.time() - t0, 1),
                 "changes_in_look_of_the_spec": spec_file["changes_in_look"],
                 "changes_rehearsed_by_the_proofs_run": spec["changes_in_look"],
                 "all_ok": all(v["ok"] for v in proofs.values()),
                 "proofs": {k: {"ok": v["ok"], "checks": v["checks"], "failed": v["failed"], "file": files[k],
                                "what": v["what"]} for k, v in proofs.items()},
                 "rehearsal": os.path.join(OUT, "rehearsal_in_sample.json"),
                 "rehearsal_of_the_spec_as_it_stands": os.path.join(OUT, "rehearsal", "autopsy_HI_look__cut2022-01-01.json"),
                 "harness_sha256": {f: RUN.sha256(os.path.join(HERE, f)) for f in sorted(os.listdir(HERE))
                                    if f.endswith((".py", ".json")) and not f.startswith(".")},
                 "protocol_sha256_at_proof_time": next((r.get("protocol_sha256") for r in proofs["i_guard"]["rows"]
                                                        if r.get("protocol_sha256")), None)}
        assert index["spec_sha256"] == SPEC_SHA, "look_spec.json changed while the proofs ran"
        jdump(index, "proofs.json")
        return index

    jdump(rehearsal, "rehearsal_in_sample.json")
    write_all()
    # A1, once more now that proofs.json, proof_i_guard.json and the rehearsals quote this run's spec sha256: refused
    # by the path rule (their content alone would pass); the rows are added to proof i and every file is rewritten
    a1_rows, a1_out = declared_file_probes("after_write")
    pi = proofs["i_guard"]
    pi["rows"] += a1_rows
    pi["A1_after_write"] = a1_out
    vi = verdict(pi["rows"])
    pi.update(checks=vi["checks"], failed=vi["failed"], ok=vi["ok"], failures=vi["failures"])
    index = write_all()
    for k, v in index["proofs"].items():
        print(f"{k:28s} {'OK ' if v['ok'] else 'FAIL'} {v['checks']:5d} checks, {v['failed']} failed", flush=True)
    print("all_ok", index["all_ok"], f"[{time.time() - t0:.0f}s]")


if __name__ == "__main__":
    main()
