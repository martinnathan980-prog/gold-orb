"""Addendum H, lens `entry` -- summary.json: every table this lens reports (baseline check, part-1 anatomy, every
part-2 cell with its criteria, the candidates with their years, neighbours and fill split, the decomposition of the
orb_asia retest gain, causality, trial counts).  In sample only; FP costs unless said otherwise."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (COMMON_START, MIN_NS, RES, arrays, build_orders, costs, jdump, lab_orders, load_is, np,  # noqa
                    pd)
from variants import build, signal_table  # noqa: E402

DECL = json.load(open(os.path.join(RES, "declared.json")))


def trial_lines():
    p1, p2 = [], []
    with open(os.path.join(RES, "trials.jsonl")) as fh:
        for ln in fh:
            d = json.loads(ln)
            (p2 if d.get("part") == "part2" else p1).append(d)
    return p1, p2


def orb_decomposition():
    """Entry-price improvement of the retest over the rule's own stop fill, per filled signal, in units of the rule's
    stop distance D: the stop slippage avoided, the touch bar's open beyond the level, a retest bar opening below the
    level; and the minutes from the touch bar to the retest fill.  Computed from the pre-resolved fill bars (every
    signal of the rule, before the one-position chain)."""
    name, sym = "orb_asia_2d_buf10", "xauusd"
    m1 = load_is(sym)
    A = arrays(m1)
    out = {}
    for stress in (False, True):
        fr = m1 if not stress else __import__("goldlab.sim", fromlist=["apply_spread_mult"]).apply_spread_mult(m1, 1.5)
        AA = A if not stress else arrays(fr)
        c = costs(sym, stress)
        o = build_orders(name, sym, fr)
        lo = lab_orders(o)
        S = signal_table(name, sym, o, lo, AA, c)
        side, trig, lv, D, F = (S.side.to_numpy(), S.trig.to_numpy(), S.level.to_numpy(), S.D.to_numpy(),
                                S.P0.to_numpy())
        raw = np.where(side > 0, np.maximum(lv, AA["ao"][trig]), np.minimum(lv, AA["bo"][trig]))
        t = pd.DatetimeIndex(fr.index[np.minimum(S.act.to_numpy(), len(fr) - 1)])
        for vid in ("RT30_skip", "RT120_skip", "RT300_skip"):
            v = [x for x in DECL["sleeves"]["orb_asia_2d_buf10:xauusd"]["variants"] if x["id"] == vid][0]
            legs, hold, info = build(name, v, "price", S, lo, AA, c)
            j = info["fill_bar"]
            ok = j >= 0
            jj = np.maximum(j, 0)
            fill = np.where(side > 0, np.minimum(lv, AA["ao"][jj]), np.maximum(lv, AA["bo"][jj]))
            for wname, w in (("common", t >= COMMON_START), ("pre", t < COMMON_START)):
                m = ok & w
                slip = side[m] * (F[m] - raw[m]) / D[m]
                over = side[m] * (raw[m] - lv[m]) / D[m]
                below = side[m] * (lv[m] - fill[m]) / D[m]
                tot = slip + over + below
                mins = (AA["ns"][j[m]] - AA["ns"][trig[m]]) / MIN_NS
                out[f"{'x1.5' if stress else 'fp'}|{vid}|{wname}"] = {
                    "signals": int(w.sum()), "retest_filled": int(m.sum()),
                    "share_filled": round(float(m.sum() / w.sum()), 4),
                    "mean_R_gain_from_slippage_avoided": round(float(slip.mean()), 4),
                    "mean_R_gain_from_touch_open_beyond_level": round(float(over.mean()), 4),
                    "mean_R_gain_from_fill_below_level": round(float(below.mean()), 4),
                    "mean_R_gain_total": round(float(tot.mean()), 4),
                    "median_R_gain_total": round(float(np.median(tot)), 4),
                    "minutes_touch_to_fill_median": float(np.median(mins)),
                    "minutes_touch_to_fill_p90": float(np.quantile(mins, .9)),
                    "median_D_usd": round(float(np.median(D[w])), 3),
                    "median_1bp_in_R": round(float(np.median(F[w] * 1e-4 / D[w])), 4)}
    return out


def main():
    p1, p2 = trial_lines()
    crit = pd.read_csv(os.path.join(RES, "criteria.csv"))
    base = json.load(open(os.path.join(RES, "baseline.json")))
    vbase = json.load(open(os.path.join(RES, "variants_baseline.json")))["sleeves"]
    trunc = json.load(open(os.path.join(RES, "truncation.json")))
    cells = {(d["sleeve"], d["variant"]["id"], d["stop_mode"]): d for d in p2}

    # baseline check table
    btab = []
    for k, v in base["sleeves"].items():
        mo = v["mine_vs_official_fp"]
        btab.append({"sleeve": k, "official_is_trades": mo["n_b"], "my_is_trades": mo["n_a"], "matched": mo["matched"],
                     "official_total_R": mo["total_R_b"], "my_total_R": mo["total_R_a"],
                     "R_different_straddling_the_cut": mo["R_different_official_exit_after_2021"],
                     "R_different_other": mo["R_different_other"],
                     "official_total_R_excl_straddle": mo["total_R_official_excl_straddle"],
                     "my_total_R_excl_straddle": mo["total_R_mine_excl_straddle"],
                     "lab_engine_equals_lens_path_fp": v["lab_vs_mine_fp"]["R_identical_1e-9"] == v["lab_vs_mine_fp"]["n_a"],
                     "lab_engine_equals_lens_path_x1.5":
                         v["lab_vs_mine_x1.5"]["R_identical_1e-9"] == v["lab_vs_mine_x1.5"]["n_a"],
                     "frame_first_bar": v["frame_first_bar"], "frame_last_bar": v["frame_last_bar"],
                     "common_n": vbase[k]["fp"]["common"]["n"], "common_exp_R": vbase[k]["fp"]["common"]["exp_R"],
                     "common_total_R": vbase[k]["fp"]["common"]["total_R"],
                     "common_win_rate": vbase[k]["fp"]["common"]["win_rate"],
                     "common_avg_loss_R": vbase[k]["fp"]["common"]["avg_loss_R"],
                     "common_x1.5_exp_R": vbase[k]["x1.5"]["common"]["exp_R"],
                     "common_x1.5_total_R": vbase[k]["x1.5"]["common"]["total_R"],
                     "pre_n": vbase[k]["fp"]["pre"]["n"], "pre_total_R": vbase[k]["fp"]["pre"]["total_R"]})

    # candidates: the cells that pass (a)-(f)
    cand = []
    for _, r in crit[crit.candidate].iterrows():
        d = cells[(r.sleeve, r.variant, r.stop_mode)]
        b = vbase[r.sleeve]
        years = {}
        for cost in ("fp", "x1.5"):
            for y, yy in d[cost]["common"]["by_year"].items():
                by = b[cost]["common"]["by_year"][y]
                years[f"{cost}|{y}"] = {"n": yy["n"], "exp_R": yy["exp_R"], "total_R": yy["total_R"],
                                        "avg_loss_R": yy["avg_loss_R"], "base_n": by["n"], "base_exp_R": by["exp_R"],
                                        "base_total_R": by["total_R"], "base_avg_loss_R": by["avg_loss_R"]}
            for y, yy in d[cost]["pre"]["by_year"].items():
                by = b[cost]["pre"]["by_year"].get(y, {})
                years[f"{cost}|pre|{y}"] = {"n": yy["n"], "exp_R": yy["exp_R"], "total_R": yy["total_R"],
                                            "base_n": by.get("n"), "base_exp_R": by.get("exp_R"),
                                            "base_total_R": by.get("total_R")}
        nb = DECL["sleeves"][r.sleeve]["neighbours"][r.variant]
        cand.append({"sleeve": r.sleeve, "variant": r.variant, "stop_mode": r.stop_mode,
                     "route": "E" if r.E_a_to_e else "L",
                     "fp_common": d["fp"]["common"], "x1.5_common": d["x1.5"]["common"],
                     "fp_pre": d["fp"]["pre"], "x1.5_pre": d["x1.5"]["pre"],
                     "base_fp_common": b["fp"]["common"], "base_x1.5_common": b["x1.5"]["common"],
                     "base_fp_pre": b["fp"]["pre"], "base_x1.5_pre": b["x1.5"]["pre"],
                     "fill_fp": d["fp"]["fill"], "fill_x1.5": d["x1.5"]["fill"], "years": years,
                     "neighbours": {n: {"exp_R": cells[(r.sleeve, n, r.stop_mode)]["fp"]["common"]["exp_R"],
                                        "total_R": cells[(r.sleeve, n, r.stop_mode)]["fp"]["common"]["total_R"],
                                        "avg_loss_R": cells[(r.sleeve, n, r.stop_mode)]["fp"]["common"]["avg_loss_R"]}
                                    for n in nb},
                     "truncation": trunc["cells"][f"{r.sleeve}|{r.variant}|{r.stop_mode}"]})
    # declared ranking per sleeve: larger common FP total-R gain, then larger x1.5 gain
    for sl in sorted({c["sleeve"] for c in cand}):
        cs = [c for c in cand if c["sleeve"] == sl]
        cs.sort(key=lambda c: (-(c["fp_common"]["total_R"] - c["base_fp_common"]["total_R"]),
                               -(c["x1.5_common"]["total_R"] - c["base_x1.5_common"]["total_R"])))
        for i, c in enumerate(cs):
            c["rank_declared"] = i + 1

    # families: how often a family helps, per sleeve (common window, FP)
    fam = []
    for (sl, vid, mode), d in cells.items():
        b = vbase[sl]["fp"]["common"]
        f = d["fp"]["common"]
        fam.append({"sleeve": sl, "family": d["variant"]["family"], "variant": vid, "stop_mode": mode,
                    "total_gain": round(f["total_R"] - b["total_R"], 2),
                    "exp_change_pct": round(100 * (f["exp_R"] - b["exp_R"]) / abs(b["exp_R"]), 1),
                    "share_filled": d["fp"]["fill"]["share_filled"],
                    "rule_entry_meanR_filled": d["fp"]["fill"]["rule_entry_meanR_on_filled"],
                    "rule_entry_meanR_missed": d["fp"]["fill"]["rule_entry_meanR_on_missed"]})
    fam = pd.DataFrame(fam)
    fam_sum = fam.groupby("family").agg(cells=("total_gain", "size"), cells_total_R_not_lower=("total_gain",
                                        lambda x: int((x >= 0).sum())), median_total_gain=("total_gain", "median"),
                                        worst_total_gain=("total_gain", "min"), best_total_gain=("total_gain", "max"))
    fam_sum = fam_sum.reset_index().to_dict("records")

    anat = {nm: pd.read_csv(os.path.join(RES, f"anatomy_{nm}.csv")).to_dict("records")
            for nm in ("path", "comeback", "late", "first_minutes")}
    out = {
        "what": "Addendum H, lens entry (getting in better): in sample only (entries before 2022-01-01, frames cut at "
                "2021-12-31 23:59 UTC at read time); FP costs unless marked x1.5; common window 2018-02-01..2021-12-31; "
                "a trade still open at the end of the in-sample frame is left out of the statistics",
        "declared_utc": DECL["written_utc"],
        "trials": {"part2_cells": len(p2), "part2_entry_variants": len(p2) // 2,
                   "part1_descriptive_late_entry_runs": len(p1),
                   "budget": DECL["budget"]},
        "baseline_check": btab,
        "anatomy": anat,
        "cells": crit.to_dict("records"),
        "families_summary": fam_sum,
        "candidates": cand,
        "orb_retest_decomposition": orb_decomposition(),
        "truncation": {"decision_layer_all_identical": trunc["all_identical"],
                       "decision_layer_decisions_checked": int(sum(v["decisions_checked"]
                                                                   for v in trunc["cells"].values())),
                       "rule_layer_all_identical": trunc["rule_layer_all_identical"],
                       "rule_layer_signals_checked": int(sum(v["signals_checked"]
                                                             for v in trunc["rule_layer"].values()))},
    }
    sc = os.path.join(RES, "selfcheck_orb.json")
    if os.path.exists(sc):
        out["selfcheck_orb_independent_loop"] = json.load(open(sc))
    jdump(out, os.path.join(RES, "summary.json"))
    print("candidates:", [(c["sleeve"], c["variant"], c["stop_mode"], c["rank_declared"]) for c in cand])
    print(json.dumps(fam_sum, indent=0))
    for k, v in out["orb_retest_decomposition"].items():
        print(k, v)


if __name__ == "__main__":
    main()
