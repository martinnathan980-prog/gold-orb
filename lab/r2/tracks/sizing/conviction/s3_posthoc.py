"""POST HOC batch (declared_addendum.json, written after V01-V28 and before this run): V30 = V05 with the nozero mapping;
V29 = permutation null of the V30 procedure (FP, 200 draws). Information only: neither can become a candidate.
Appends V30 and V29 to trials.jsonl and writes posthoc.json."""
import json
import os

import numpy as np

import cv_common as V
import cv_engine as E
import cv_stakes as S
from s2_run import compact_info

TRIALS = os.path.join(V.OUT, "trials.jsonl")
ADD = json.load(open(os.path.join(V.OUT, "declared_addendum.json")))
RULE = {v["id"]: v["rule"] for v in ADD["variants"]}


def run():
    done = {json.loads(l)["trial"] for l in open(TRIALS)}
    assert "V29" not in done and "V30" not in done, "post hoc batch already logged"
    T = {m: S.tables(m) for m in V.MODES}
    tdec = {m: {k: T[m][k][0].t_dec.to_numpy(np.int64) for k in V.KEYS} for m in V.MODES}
    base = {m: {k: E.baseline(k, m) for k in V.KEYS} for m in V.MODES}
    bref = {m: E.book(base[m], {k: np.ones(len(base[m][k])) for k in V.KEYS}, tdec[m]) for m in V.MODES}
    out = {}
    row = {"trial": "V30", "id": "V30", "family": "ii (post hoc)", "rule": RULE["V30"], "declared": "post hoc"}
    for m in V.MODES:
        st, info = S.family_ii_pool(T[m], 1.0, 1 / 3, nozero=True)
        stc = {k: st[k][base[m][k].oid.to_numpy()] for k in V.KEYS}
        ev = E.evaluate(E.book(base[m], stc, tdec[m]), bref[m])
        a, b, up = E.verdict_ab(ev)
        ev.update(a_sharpe_up_10pct=a, b_up_2_of_3_years=b, years_up=up)
        row[m] = ev
        row["folds_" + m] = compact_info("V30", info)
        print("V30", m, ev["pooled"]["sharpe"], ev["pooled"]["sharpe_ratio_vs_ref"], up,
              {y: (ev["by_year"][y]["variant"]["sharpe"], ev["by_year"][y]["ref"]["sharpe"]) for y in V.OOF_YEARS},
              flush=True)
    row["verdict"] = {"post_hoc_information_only": True}
    out["V30"] = row
    own = row["fp"]["pooled"]["sharpe_ratio_vs_ref"]
    # V29: null of the V30 procedure
    rng = np.random.default_rng(2029)
    ratios = []
    Tf = T["fp"]
    for _ in range(200):
        Tp = dict(Tf)
        for k in V.CRYPTO_BRK:
            s, tr = Tf[k]
            s2 = s.copy()
            ch_oid = tr.oid.to_numpy()
            fold = s2.year.to_numpy()[ch_oid]
            vals = s2.loc[ch_oid, V.ELIGIBLE].to_numpy(float).copy()
            for y in np.unique(fold):
                idx = np.flatnonzero(fold == y)
                vals[idx] = vals[rng.permutation(idx)]
            s2.loc[ch_oid, V.ELIGIBLE] = vals
            tr2 = s2.set_index("oid").loc[ch_oid].reset_index()
            tr2["exit_ns"], tr2["entry_ns"], tr2["R"] = tr.exit_ns.to_numpy(), tr.entry_ns.to_numpy(), tr.R.to_numpy()
            Tp[k] = (s2, tr2)
        st, _ = S.family_ii_pool(Tp, 1.0, 1 / 3, nozero=True)
        stc = {k: st[k][base["fp"][k].oid.to_numpy()] for k in V.KEYS}
        ev = E.evaluate(E.book(base["fp"], stc, tdec["fp"]), bref["fp"])
        ratios.append(ev["pooled"]["sharpe_ratio_vs_ref"])
    ratios = np.array(ratios)
    null = {"draws": 200, "seed": 2029, "of": "V30", "own_ratio": own,
            "null_mean": round(float(ratios.mean()), 4), "null_p05": round(float(np.percentile(ratios, 5)), 4),
            "null_p50": round(float(np.percentile(ratios, 50)), 4), "null_p95": round(float(np.percentile(ratios, 95)), 4),
            "null_max": round(float(ratios.max()), 4), "share_at_or_above_own": round(float((ratios >= own).mean()), 4),
            "share_at_or_above_1.10": round(float((ratios >= 1.10).mean()), 4)}
    print("V29", null, flush=True)
    out["V29"] = {"trial": "V29", "id": "V29", "family": "control (post hoc)", "rule": RULE["V29"],
                  "declared": "post hoc", "null": null, "verdict": {"post_hoc_information_only": True}}
    for vid in ("V30", "V29"):
        V.append_jsonl(TRIALS, out[vid])
    V.dump({vid: ({m: {q: out[vid][m][q] for q in ("scale_k", "pooled", "pooled_ref", "by_year", "years_up",
                                                    "stake_profile_oof", "per_sleeve_oof")} for m in V.MODES}
                  if vid == "V30" else out[vid]["null"]) for vid in out}, os.path.join(V.OUT, "posthoc.json"))


if __name__ == "__main__":
    run()
