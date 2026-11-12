"""validation_hi -- the proofs of the task's rule 3, ON IN-SAMPLE DATA ONLY (CUT = 2022-01-01).

The look's own specification (look_spec.json) is run through the look's own code path (vhi_run.run_spec) at
CUT = 2022-01-01 on its in-sample windows, and every number is compared with what the lenses published:
    (a) the ten official sleeves: trades and total R (results/r2/recalc/trades, rows read with entry_time < CUT;
        results compared on the rows also closed before CUT) and synthesis_B's first check
    (b) K1 (synthesis_B sleeve_runs C1, fp and x1.5): folds, thresholds 505.9 / 496.7 / 465.1 bp, the 2022 value
        478.3 bp, 2019-2021 395 -> 304 trades, +49.1 -> +63.9 R; and the generalised walk-forward identical to
        s1_run.walk_forward
    (c) K2 and K3 (synthesis_B sleeve_runs N1, N2): 344 trades +155.5 R, 375 trades +194.3 R, fp and x1.5
    (d) the seven payoff variants in play and their references (results/r2/autopsy/payoff/variants_table.csv)
    (e) the synthesis_B portfolios P0 and P2 (and P1), fp and x1.5, every field; and the harness metrics equal to
        synthesis_B's own s2_portfolio.metrics on the same book
plus the harness's own checks:
    (f) the capped account (6 positions, 2 per market) equals the cluster lens's run_engine and account.py
    (g) the live execution: with no delay and no Friday close the live chain IS the official chain; K2 as the live
        program would, against the verifier's figures quoted in synthesis_B
    (h) stakes: the stake interface reproduces P0 at stake 1, adds exactly what a sleeve-year table adds, and a
        walk-forward stake only uses outcomes known before each 1 January minus 7 days
    (i) the guard: refusals (CUT after 2022 without a declared addendum, after 2026 always, holdout paths, reads
        without the row filter), no line written to val_access.log, every read of the run with its filter

    NUMBA_CACHE_DIR=/tmp/numba_validation_hi PYTHONDONTWRITEBYTECODE=1 python3 lab/r2/tracks/validation_hi/proofs.py

Writes lab/results/r2/validation_hi/proof_<x>_*.json, rehearsal_in_sample.json and proofs.json (index). Every
number in them is in sample (entries and exits before 2022-01-01).
"""
import json
import math
import os
import sys
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


def hi_lines():
    if not os.path.exists(G.VAL_LOG):
        return 0
    with open(G.VAL_LOG) as f:
        return sum(1 for ln in f if '"autopsy_HI_look"' in ln)


LOG_BEFORE = hi_lines()
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
from goldlab.sim import simulate  # noqa: E402

SYNTH_B = os.path.join(LAB, "results", "r2", "autopsy", "synthesis_B.json")
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
def proof_b(res, sb):
    key = "brk72_24h_wd__ethusd+K1"
    S1 = L.synthesis_B()["S1"]
    out, rows = {}, []
    for mode in ("fp", "stress"):
        r = res["sleeves"][key]["runs"][f"{mode}/lab"]
        dg = r["info"]["change_diag"]
        tb = res["_trades"][(key, "base", mode, "lab")]
        tv = res["_trades"][(key, "main", mode, "lab")]
        got = {"signals": dg["signals"], "refused": dg["refused_alone"],
               "refused_in_chain_extra": [r["info"]["base_refused_3spreads"], r["info"]["main_refused_3spreads"]],
               "folds": dg["folds"], "fit_for_2022": dg["fit_for_year_starting_at_cut"],
               "skipped_by_year": dg["skipped_by_year"],
               "base_2019_2021": r["base"]["oof_2019_2021"], "var_2019_2021": r["main"]["oof_2019_2021"],
               "base_window": r["base"]["window"], "var_window": r["main"]["window"],
               "base_by_year": B.by_year(tb), "var_by_year": B.by_year(tv),
               "baseline_trades_removed": r["k1"]["baseline_trades_removed"], "R_of_removed": r["k1"]["R_of_removed"],
               "new_trades": r["k1"]["new_trades"], "R_of_new": r["k1"]["R_of_new"]}
        exp = sb["sleeve_runs"]["C1_K1_riskbp_brk72_ethusd"][mode]
        rr = compare(got, exp, mode, skip=("sec",))
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
        rows += rr
        out[mode] = {"got": got, "declared_T_check": dg.get("declared_T_check"),
                     "skipped_alone_vs_kept_alone_window": {kk: r["k1"][kk] for kk in ("skipped_signals_alone", "kept_signals_alone")}}
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
    return {"what": "the seven payoff variants in play (and their references) against "
                    "results/r2/autopsy/payoff/variants_table.csv (fp and x1.5 columns, common window "
                    "2018-02-01..2021-12-31, earlier entries, refusals, years better) and the lens's trials.jsonl "
                    "(by year, censored trades, H extensions)",
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
def frames_pass(res, sb):
    """One more pass over the four frames: the live-chain identity, K2 live against the verifier, signal tables for
    the stake checks."""
    rows_g, out_g = [], {}
    leader = None
    signals = {}
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
    return rows_g, out_g, signals


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
def proof_i():
    rows = []
    st = G.self_test()
    for k, v in st.items():
        if isinstance(v, dict):
            rows.append({"field": f"guard.{k}", "expected": v["expected_allowed"], "got": v["allowed"], "ok": v["ok"]})
    # reads the guard must refuse inside this very process (they raise before any byte is read)
    tries = {"frame_without_row_filter": lambda: pd.read_parquet(os.path.join(LAB, "data", "fp", "ethusd_m1.parquet")),
             "frame_with_filter_after_cut": lambda: pd.read_parquet(os.path.join(LAB, "data", "fp", "ethusd_m1.parquet"),
                                                                    filters=[("ts", "<", pd.Timestamp("2022-01-02", tz="UTC"))]),
             "official_trades_without_entry_filter": lambda: pd.read_parquet(
                 os.path.join(G.OFFICIAL_DIR, "brk72_24h_wd__ethusd.parquet")),
             "holdout_dir": lambda: pd.read_parquet(os.path.join(LAB, "data", "holdout", "anything.parquet")),
             "nq_default_leader_loader": lambda: L.registry()["rules"]["nq_btc_follow"][1].__globals__["_LEADERS"].clear()
             or L.registry()["rules"]["nq_btc_follow"][1].__globals__["_leader"]("us100"),
             "val_access_log_at_cut_2022": lambda: G.log_access("should_not_be_written")}
    for name, fn in tries.items():
        try:
            fn()
            refused = False
        except G.GuardError:
            refused = True
        rows.append({"field": f"refused in process: {name}", "expected": True, "got": refused, "ok": refused})
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
    rows.append({"field": "val_access.log lines with track autopsy_HI_look: before and after the proofs",
                 "expected": [0, 0], "got": [LOG_BEFORE, after], "ok": LOG_BEFORE == 0 and after == 0})
    rd = G.reads()
    bad = [r for r in rd if ("data/" in r["path"] or "recalc/trades" in r["path"]) and "2022-01-01" not in r["filters"]]
    rows.append({"field": "every frame / official trades read of the run carries a row filter at 2022-01-01",
                 "expected": 0, "got": len(bad), "ok": not bad})
    return {"what": "the guard of the harness (vhi_guard): CUT rules, refused reads, the access log untouched",
            "reads": rd, **verdict(rows), "rows": rows}


# ------------------------------------------------------------------------------------------------- (j)
def proof_j(res):
    """The single command of the look, run at CUT 2022-01-01 (a rehearsal: nothing logged), in its own process:
    its output must equal this run's, number for number."""
    import subprocess
    env = {k: v for k, v in os.environ.items() if k != "LOOK_DECLARED"}
    out = os.path.join(OUT, "rehearsal", "autopsy_HI_look__cut2022-01-01.json")
    t0 = time.time()
    p = subprocess.run([sys.executable, os.path.join(HERE, "look.py"), "--cut", "2022-01-01", "--spec", SPEC],
                       env=env, capture_output=True, text=True, timeout=3000, cwd="/tmp")
    rows = [{"field": "look.py --cut 2022-01-01 exits 0", "expected": 0, "got": p.returncode, "ok": p.returncode == 0,
             "stderr_tail": p.stderr.strip()[-500:]}]
    if p.returncode == 0:
        with open(out) as f:
            theirs = json.load(f, parse_constant=lambda c: None)
        mine = RUN.canonical(RUN.strip_private(res))
        for part in ("portfolios", "comparisons", "sleeve_comparisons", "official"):
            same_part = theirs[part] == mine[part]
            rows.append({"field": f"look.py rehearsal == proofs run: {part}", "expected": True, "got": same_part,
                         "ok": same_part})
        same_sl = all(theirs["sleeves"][k]["runs"][r]["main"] == mine["sleeves"][k]["runs"][r]["main"]
                      for k in mine["sleeves"] for r in mine["sleeves"][k]["runs"])
        rows.append({"field": "look.py rehearsal == proofs run: every sleeve run", "expected": True, "got": same_sl,
                     "ok": same_sl})
        rows.append({"field": "rehearsal did not log an access (meta.is_look False)", "expected": False,
                     "got": theirs["meta"]["is_look"], "ok": theirs["meta"]["is_look"] is False})
    return {"what": "the look's entry point (look.py) run end to end at CUT 2022-01-01 in its own process: same "
                    "numbers as the proofs' run, nothing logged", "output": out, "seconds": round(time.time() - t0, 1),
            **verdict(rows), "rows": rows}


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
    spec["windows"]["in_sample"] = {"eval": ["2020-01-01", "2021-01-01"], "years": [2020], "judge_years": [2020],
                                    "splits": [["h1_2020", "2020-01-01", "2020-07-01"], ["h2_2020", "2020-07-01", "2021-01-01"]]}
    for s in spec["sleeves"]:
        if (s.get("change") or {}).get("kind") == "k1_riskbp":
            s["change"]["declared_T"] = {"2021": 465.1178}
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
        rows.append({"field": "K1: declared-T check at CUT 2021 (T(2021) = 465.1178)", "expected": True,
                     "got": dg["declared_T_check"]["2021"]["same_to_0.01bp"], "ok": dg["declared_T_check"]["2021"]["same_to_0.01bp"]})
    out["frames_cut2021"] = r21["frames"]
    out["output"] = jp
    return {"what": proof_k.__doc__.strip(), "detail": out, **verdict(rows), "rows": rows}


# ------------------------------------------------------------------------------------------------- main
def main():
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    spec = json.load(open(SPEC))
    sb = json.load(open(SYNTH_B))
    res = RUN.run_spec(spec, cut)
    print(f"run_spec done [{time.time() - t0:.0f}s]", flush=True)
    proofs = {}
    proofs["a_official_trades"] = proof_a(res, sb)
    proofs["b_K1"] = proof_b(res, sb)
    proofs["c_K2_K3"] = proof_c(res, sb)
    proofs["d_payoff_variants"] = proof_d(res)
    proofs["e_portfolios_P0_P1_P2"] = proof_e(res, sb)
    proofs["f_capped_account"] = proof_f(res)
    rows_g, out_g, signals = frames_pass(res, sb)
    proofs["g_live_execution"] = {"what": "the live execution (entry one minute late at market, Friday 16:50 New "
                                          "York close): K2 run this way reproduces the verifiers' figures quoted in "
                                          "synthesis_B (392 trades, +142.1 R; x1.5 +127.9 R) and the harness's "
                                          "declared default is that run without the trade still open at the end of "
                                          "2021; the alternative chain resolver ('rule') returns the official chain "
                                          "trade for trade when there is no delay and no Friday close, and differs "
                                          "from the default only by signals at the previous trade's exit minute",
                                  "detail": out_g, **verdict(rows_g), "rows": rows_g}
    proofs["h_stakes"] = proof_h(res, signals)
    proofs["i_guard"] = proof_i()
    proofs["j_entry_point_rehearsal"] = proof_j(res)
    proofs["k_moving_the_cut"] = proof_k(res)
    files = {}
    for k, v in proofs.items():
        name = f"proof_{k}.json"
        jdump(v, name)
        files[k] = os.path.join(OUT, name)
    rehearsal = RUN.strip_private(res)
    rehearsal["note"] = ("look_spec.json run at CUT 2022-01-01 on its in-sample windows by the look's own code path: "
                         "every number is in sample")
    jdump(rehearsal, "rehearsal_in_sample.json")
    index = {"cut": str(cut), "spec": SPEC, "spec_sha256": RUN.sha256(SPEC), "seconds": round(time.time() - t0, 1),
             "all_ok": all(v["ok"] for v in proofs.values()),
             "proofs": {k: {"ok": v["ok"], "checks": v["checks"], "failed": v["failed"], "file": files[k],
                            "what": v["what"]} for k, v in proofs.items()},
             "rehearsal": os.path.join(OUT, "rehearsal_in_sample.json")}
    jdump(index, "proofs.json")
    for k, v in index["proofs"].items():
        print(f"{k:28s} {'OK ' if v['ok'] else 'FAIL'} {v['checks']:5d} checks, {v['failed']} failed", flush=True)
    print("all_ok", index["all_ok"], f"[{time.time() - t0:.0f}s]")


if __name__ == "__main__":
    main()
