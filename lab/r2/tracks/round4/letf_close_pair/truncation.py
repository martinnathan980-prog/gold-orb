"""Causality (hard rule 3, declared.json R23 d): truncation test of the main configuration. The whole pipeline
(calendar -> grid -> signals -> two-leg simulation) is rebuilt on the in-sample frames CUT at each decision time,
and the decision must be identical to the one made on the full frames:
  * entry decisions (60 sessions: 30 traded, 30 not traded): frames cut at 15:30 New York of the session (bars that
    started before 15:30 only) -> d_us100, d_us30, sd_d, h, sd_pi, condition, take;
  * stop decisions (50 stopped pairs): frames cut at the end of the decision bar (that bar included, nothing after)
    -> same stop decision bar;
  * no-stop decisions (25 pairs with a time exit): frames cut at a random minute inside the hold -> no stop decided
    before the cut.
Writes results/r2/round4/letf_close_pair/truncation.json."""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

DECL = json.load(open(os.path.join(C.OUT, "declared.json")))
MAIN = DECL["configurations"][0]["params"]
assert DECL["configurations"][0]["name"] == "main"


def cut_frames(fr, tau_min):
    return {s: f[C._tmin(f.index) < tau_min] for s, f in fr.items()}


def pipeline(fr, cal):
    P = C.prepare(C.build_grid(fr, cal["tdays"]))
    return P, C.signals(P, cal, **MAIN)


def same(a, b):
    return bool((np.isnan(a) and np.isnan(b)) or a == b or np.isclose(a, b, rtol=1e-12, atol=0))


def main():
    rng = np.random.default_rng(11)
    cal = C.calendar()
    fr = C.load_frames(syms=("us100", "us30"))
    P, sg = pipeline(fr, cal)
    t, _ = C.run_config(P, sg, MAIN)
    e, x, k, L2 = MAIN["entry_min"] - C.G0, MAIN["exit_min"] - C.G0, MAIN["k"], sg["L2"]
    problems, checks = [], {"entry": 0, "stop": 0, "no_stop": 0}
    # ---- entry decisions
    ready = np.flatnonzero(np.isfinite(sg["sd_d"]) & np.isfinite(sg["sdpi"]) & np.isfinite(sg["d100"]))
    tk, nt = ready[sg["take"][ready]], ready[~sg["take"][ready]]
    pick = np.r_[rng.choice(tk, 30, replace=False), rng.choice(nt, 30, replace=False)]
    for j in pick:
        row = int(sg["rows"][j])
        tau = int(P["t0m"][row] + 30)                                 # 15:30 New York of session j
        Pc, sc = pipeline(cut_frames(fr, tau), cal)
        checks["entry"] += 1
        for kk in ("cond", "take"):
            if sc[kk][j] != sg[kk][j]:
                problems.append(f"entry {cal['sessions'][j].date()}: {kk} {sc[kk][j]} vs {sg[kk][j]}")
        for kk in ("d100", "d2", "sd_d", "h", "sdpi", "dir"):
            if not same(sc[kk][j], sg[kk][j]):
                problems.append(f"entry {cal['sessions'][j].date()}: {kk} {sc[kk][j]} vs {sg[kk][j]}")
        if np.isfinite(Pc["mo"][:, row, 30:]).any():                    # the cut frames end before 15:30 that day
            problems.append(f"entry {cal['sessions'][j].date()}: cut frame still holds a bar at or after 15:30")
    # ---- stop decisions
    st = t[t.reason == "stop"]
    for _, tr in st.sample(min(50, len(st)), random_state=3).iterrows():
        j, row, u = int(tr.session), int(tr.row), int(tr.stop_decision_col)
        tau = int(P["t0m"][row] + e + u + 1)                          # end of the decision bar
        Pc, sc = pipeline(cut_frames(fr, tau), cal)
        checks["stop"] += 1
        if not (sc["take"][j] and same(sc["h"][j], tr.h) and same(sc["sdpi"][j], tr.sd_pi) and sc["dir"][j] == tr.dir):
            problems.append(f"stop {cal['sessions'][j].date()}: signal differs on the cut frames")
            continue
        r = C.sim_pairs(Pc, [row], L2, [sc["dir"][j]], [sc["h"][j]], [sc["sdpi"][j]], e, x, k)
        if not (r["stopped"][0] and int(r["u"][0]) == u):
            problems.append(f"stop {cal['sessions'][j].date()}: decision bar {r['u'][0]} on cut frames vs {u}")
    # ---- no-stop decisions
    tm = t[t.reason == "time"]
    for _, tr in tm.sample(25, random_state=5).iterrows():
        j, row = int(tr.session), int(tr.row)
        cutoff = int(rng.integers(1, x - e))                          # minutes after the entry
        tau = int(P["t0m"][row] + e + cutoff)
        Pc, sc = pipeline(cut_frames(fr, tau), cal)
        checks["no_stop"] += 1
        r = C.sim_pairs(Pc, [row], L2, [sc["dir"][j]], [sc["h"][j]], [sc["sdpi"][j]], e, x, k)
        if r["stopped"][0] and int(r["u"][0]) < cutoff:
            problems.append(f"no-stop {cal['sessions'][j].date()}: a stop appears before the cut on cut frames")
    out = {"config": "main", "decisions_checked": checks, "total": int(sum(checks.values())), "problems": problems,
           "pass": not problems, "stops_in_main": int(len(st)),
           "method": "the in-sample frames are cut at the decision time and the whole pipeline is rebuilt; entry "
                     "decisions cut at 15:30 New York (bars that started before 15:30 only), stop decisions cut at the "
                     "end of the decision bar, no-stop checks cut at a random minute of the hold"}
    C.jdump(out, os.path.join(C.OUT, "truncation.json"))
    print(out)


if __name__ == "__main__":
    main()
