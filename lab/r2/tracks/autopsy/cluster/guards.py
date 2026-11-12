"""Lens `cluster`, part 2: guards and adaptive rules on the portfolio of the ten sleeves. IN SAMPLE ONLY.

Reads the variants of results/r2/autopsy/cluster/declared.json (written before this script was first run),
evaluates each under FP costs and with costs x1.5, applies the candidate criteria fixed in declared.json, logs one
JSON line per variant in trials.jsonl, and runs the trade-level truncation test of every variant.

Truncation test (trade level): for a decision at time t (the entry of trade i), the book is cut to the trades
already offered (the prefix 0..i of the entry order); every trade of that prefix whose exit time is >= t (its
outcome not yet known at t, including trade i itself) gets an exit time far in the future and a random R. The
engine is re-run on that cut book: every decision of the prefix must be identical to the full run's.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import book as B  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

RNG = np.random.default_rng(7)
FAR = np.int64(4_000_000_000_000_000_000)      # ~2096 in ns


def equal_stakes(st, st_ref):
    """The variant rescaled so that it deploys the reference's number of base stakes."""
    s = st_ref["stakes"] / st["stakes"] if st["stakes"] > 0 else float("nan")
    return {"scale": round(s, 4), "total_R": round(st["total_R"] * s, 3), "worst_day": round(st["worst_day"] * s, 3),
            "worst_week": round(st["worst_week"] * s, 3), "max_dd": round(st["max_dd"] * s, 3)}


def branch_tests(st, ref):
    E, Er = st["exp_per_stake"], ref["exp_per_stake"]
    AL, ALr = st["avg_loss_per_stake"], ref["avg_loss_per_stake"]
    b1 = E is not None and E >= 1.20 * Er
    b2 = AL is not None and E is not None and AL <= 0.80 * ALr and E >= Er
    tot_ok = st["total_R"] >= ref["total_R"] - 1e-9
    if st["stakes"] > ref["stakes"] + 1e-9:
        tot_ok = tot_ok and st["total_R"] * ref["stakes"] / st["stakes"] >= ref["total_R"] - 1e-9
    return b1, b2, tot_ok


def years_better(st, ref, metric):
    out = {}
    for y in (2018, 2019, 2020, 2021):
        a, r = st["by_year"].get(y) or st["by_year"].get(str(y)), ref["by_year"].get(y) or ref["by_year"].get(str(y))
        if metric == "E":
            out[y] = bool(a["exp_per_stake"] is not None and a["exp_per_stake"] > r["exp_per_stake"])
        else:
            out[y] = bool(a["avg_loss_per_stake"] is not None and a["avg_loss_per_stake"] < r["avg_loss_per_stake"])
    return out


def truncation_test(a, code, p1, p2, m_full, idx_test):
    n_bad = 0
    n_checked = 0
    first_bad = None
    for i in idx_test:
        t = a["t_in"][i]
        cut = {k: (v[: i + 1].copy() if isinstance(v, np.ndarray) and len(v) == len(a["R"]) else v) for k, v in a.items()}
        unknown = cut["t_out"] >= t
        cut["t_out"][unknown] = FAR
        cut["R"][unknown] = RNG.choice([-7.0, 9.0], size=int(unknown.sum()))
        cut["order_out"] = np.argsort(cut["t_out"], kind="stable")
        m_cut, _ = B.run(cut, code, p1, p2, caps=True)
        n_checked += i + 1
        if not np.array_equal(m_cut, m_full[: i + 1]):
            n_bad += 1
            if first_bad is None:
                first_bad = int(i)
    return {"decision_points": int(len(idx_test)), "decisions_compared": int(n_checked), "points_with_a_difference": n_bad,
            "first_bad_index": first_bad, "pass": n_bad == 0}


def main():
    decl = json.load(open(os.path.join(C.OUT, "declared.json")))
    variants = decl["variants"]
    books = {}
    for mode in ("fp", "stress"):
        d = B.build(mode)
        a = B.arrays(d)
        books[mode] = (d, a)
    ref = {}
    m_ref = {}
    for mode, (d, a) in books.items():
        m, why = B.run(a, 0, caps=True)
        m_ref[mode] = m
        ref[mode] = B.stats(d, m)
        ref[mode]["skipped_by_caps"] = int(((why == 2) & (d.t_in >= C.COMMON_START).to_numpy()).sum())
        ref[mode]["earlier_years"] = B.stats(d, m, sel=(d.t_in < C.COMMON_START).to_numpy())["by_year"]
    res = {}
    t0 = time.time()
    for v in variants:
        r = {"id": v["id"], "family": v["family"], "code": v["code"], "p1": v["p1"], "p2": v["p2"], "rule": v["rule"]}
        for mode, (d, a) in books.items():
            m, why = B.run(a, v["code"], v["p1"], v["p2"], caps=True)
            st = B.stats(d, m)
            sel = (d.t_in >= C.COMMON_START).to_numpy()
            st["skipped_by_guard"] = int(((why == 1) & sel).sum())
            st["skipped_by_caps"] = int(((why == 2) & sel).sum())
            st["reduced_stake"] = int(((m > 0) & (m < 1) & sel).sum())
            st["raised_stake"] = int(((m > 1) & sel).sum())
            st["equal_stakes"] = equal_stakes(st, ref[mode])
            st["earlier_years"] = B.stats(d, m, sel=~sel)["by_year"]
            if mode == "fp":
                st["per_sleeve"] = B.per_sleeve(d, m, m_ref[mode])
                r["_m_fp"] = m
            r[mode] = st
        res[v["id"]] = r
    print(f"evaluated {len(variants)} variants x 2 cost modes in {time.time() - t0:.0f}s", flush=True)

    # criteria
    for v in variants:
        r = res[v["id"]]
        b1, b2, tot = branch_tests(r["fp"], ref["fp"])
        s1, s2, stot = branch_tests(r["stress"], ref["stress"])
        crit = {"a_branch1_E_up_20pct": b1, "a_branch2_AL_down_20pct_E_not_lower": b2, "a": b1 or b2, "b_total_not_lower": tot}
        metric = "E" if b1 else ("AL" if b2 else "E")
        yb = years_better(r["fp"], ref["fp"], metric)
        crit["c_metric"] = metric
        crit["c_years_better"] = yb
        crit["c"] = sum(yb.values()) >= 3
        crit["d_stress_a"] = bool(s1 or s2)
        crit["d_stress_b"] = bool(stot)
        crit["d_stress"] = bool((s1 or s2) and stot)
        nb = []
        for q in v.get("neighbours", []):
            rq = res[q]["fp"]
            better = (rq["exp_per_stake"] > ref["fp"]["exp_per_stake"]) if metric == "E" else \
                (rq["avg_loss_per_stake"] < ref["fp"]["avg_loss_per_stake"] and rq["exp_per_stake"] >= ref["fp"]["exp_per_stake"])
            nb.append({"id": q, "metric_better": bool(better), "total_not_lower": bool(rq["total_R"] >= ref["fp"]["total_R"])})
        crit["e_neighbours"] = nb
        crit["e"] = bool(v.get("eligible", True) and len(nb) > 0 and all(x["metric_better"] and x["total_not_lower"] for x in nb))
        crit["eligible"] = bool(v.get("eligible", True))
        crit["candidate_before_causality"] = bool(crit["a"] and crit["b_total_not_lower"] and crit["c"] and crit["d_stress"] and crit["e"])
        r["criteria"] = crit

    # truncation test (trade level), fp book, every variant: 300 decisions where the guard changed the stake
    # against the reference (or all if fewer) + 300 random decisions of the common window
    d, a = books["fp"]
    sel_idx = np.nonzero((d.t_in >= C.COMMON_START).to_numpy())[0]
    t0 = time.time()
    for v in variants:
        r = res[v["id"]]
        m = r["_m_fp"]
        active = sel_idx[m[sel_idx] != m_ref["fp"][sel_idx]]
        pick = np.unique(np.r_[RNG.choice(active, size=min(300, len(active)), replace=False) if len(active) else np.array([], int),
                               RNG.choice(sel_idx, size=300, replace=False)]).astype(np.int64)
        r["truncation_trade_level"] = truncation_test(a, v["code"], v["p1"], v["p2"], m, pick)
        r["criteria"]["f_trade_level"] = r["truncation_trade_level"]["pass"]
    # the reference itself
    ref_trunc = truncation_test(a, 0, 0.0, 0.0, m_ref["fp"], np.unique(RNG.choice(sel_idx, size=300, replace=False)).astype(np.int64))
    print(f"truncation tests in {time.time() - t0:.0f}s", flush=True)

    # trial log: one line per variant (losing ones alike)
    with open(os.path.join(C.OUT, "trials.jsonl"), "w") as f:
        for v in variants:
            r = res[v["id"]]
            row = {k: r[k] for k in ("id", "family", "code", "p1", "p2", "rule")}
            for mode in ("fp", "stress"):
                row[mode] = {k: r[mode][k] for k in r[mode] if k not in ("per_sleeve",)}
            row["criteria"] = r["criteria"]
            row["truncation_trade_level"] = r["truncation_trade_level"]
            f.write(json.dumps(row, default=str) + "\n")
    out = {"reference": ref, "reference_truncation_trade_level": ref_trunc,
           "variants": {k: {kk: vv for kk, vv in r.items() if kk != "_m_fp"} for k, r in res.items()}}
    json.dump(out, open(os.path.join(C.OUT, "guards.json"), "w"), indent=1, default=str)
    # stakes of every variant (fp) for later checks
    pd.DataFrame({"sleeve": d.sleeve, "t_in": d.t_in, "side": d.side, "R": d.R, "ref": m_ref["fp"],
                  **{k: r["_m_fp"] for k, r in res.items()}}).to_parquet(os.path.join(C.OUT, "stakes_fp.parquet"))

    # table
    rows = []
    for k, r in [("REF", {"fp": ref["fp"], "stress": ref["stress"]})] + list(res.items()):
        f, s = r["fp"], r["stress"]
        c = r.get("criteria", {})
        rows.append({"id": k, "n": f["n_taken"], "stakes": f["stakes"], "total": f["total_R"], "E": f["exp_per_stake"],
                     "AL": f["avg_loss_per_stake"], "win": f["win_rate"], "worst_day": f["worst_day"],
                     "worst_week": f["worst_week"], "max_dd": f["max_dd"], "lose_days": f["longest_losing_days"],
                     "lose_weeks": f["longest_losing_weeks"], "stress_total": s["total_R"], "stress_E": s["exp_per_stake"],
                     "eq_total": f.get("equal_stakes", {}).get("total_R"), "eq_dd": f.get("equal_stakes", {}).get("max_dd"),
                     "a": c.get("a"), "b": c.get("b_total_not_lower"), "c": c.get("c"), "d": c.get("d_stress"), "e": c.get("e"),
                     "f": c.get("f_trade_level"), "cand": c.get("candidate_before_causality")})
    tab = pd.DataFrame(rows)
    tab.to_csv(os.path.join(C.OUT, "guards_table.csv"), index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print(tab.to_string())


if __name__ == "__main__":
    main()
