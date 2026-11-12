"""Causality (hard rule 3): truncation test of the main configuration. The whole pipeline (grid -> signals -> two-leg
simulation) is rebuilt on the three in-sample frames CUT at each decision time, and the decision must be identical to
the one made on the full frames:
  * entry decisions (60 sessions, traded and not traded): frames cut at 10:00 New York of the session (bars that
    started before 10:00 only) -> ranked?, S, W, D, Q, h, sd_pi, take;
  * stop decisions (50 stopped pairs): frames cut at the end of the decision bar (that bar included, nothing after) ->
    same stop decision bar;
  * no-stop decisions (25 pairs with a time exit): frames cut at a random minute inside the hold -> no stop decided
    before the cut.
Writes results/r2/round4/idxrs_1000/truncation.json."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

MAIN = dict(entry_min=600, exit_min=955, q=0.75, win=60, minv=40)
K = 1.5


def cut_frames(fr, tau_min):
    return {s: f[C._tmin(f.index) < tau_min] for s, f in fr.items()}


def pipeline(fr, days):
    P = C.prepare(C.build_grid(fr, days))
    return P, C.signals(P, **MAIN)


def same(a, b):
    return bool((np.isnan(a) and np.isnan(b)) or a == b or np.isclose(a, b, rtol=1e-12, atol=0))


def main():
    rng = np.random.default_rng(11)
    days = C.sessions()
    fr = C.load_frames()
    P, sg = pipeline(fr, days)
    t, _ = C.run_config(P, sg, K)
    e, x = sg["e"], sg["x"]
    problems, checks = [], {"entry": 0, "stop": 0, "no_stop": 0}
    # ---- entry decisions
    ranked = np.flatnonzero(sg["ok"] & np.isfinite(sg["Q"]) & np.isfinite(sg["sdpi"]))
    tk = ranked[sg["take"][ranked]]
    nt = ranked[~sg["take"][ranked]]
    pick = np.r_[rng.choice(tk, 30, replace=False), rng.choice(nt, 30, replace=False)]
    for d in pick:
        tau = int(P["t0m"][d] + e)                                   # 10:00 New York of session d
        Pc, sc = pipeline(cut_frames(fr, tau), days)
        checks["entry"] += 1
        for kk in ("ok", "take", "S", "W"):
            if sc[kk][d] != sg[kk][d]:
                problems.append(f"entry {days[d].date()}: {kk} {sc[kk][d]} vs {sg[kk][d]}")
        for kk in ("D", "Q", "h", "sdpi"):
            if not same(sc[kk][d], sg[kk][d]):
                problems.append(f"entry {days[d].date()}: {kk} {sc[kk][d]} vs {sg[kk][d]}")
        # the cut frames really end before 10:00 of that day: the entry bar is unknown there
        if np.isfinite(Pc["mo"][:, d, e]).any():
            problems.append(f"entry {days[d].date()}: cut frame still holds the 10:00 bar")
    # ---- stop decisions
    ix = {s: i for i, s in enumerate(C.SYMS)}
    st = t[t.reason == "stop"]
    for _, row in st.sample(min(50, len(st)), random_state=3).iterrows():
        d, u = int(row.session), int(row.stop_decision_col)
        tau = int(P["t0m"][d] + e + u + 1)                            # end of the decision bar
        Pc, sc = pipeline(cut_frames(fr, tau), days)
        checks["stop"] += 1
        if not (sc["take"][d] and same(sc["h"][d], row.h) and same(sc["sdpi"][d], row.sd_pi)):
            problems.append(f"stop {days[d].date()}: signal differs on the cut frames")
            continue
        r = C.sim_pairs(Pc, [d], [ix[row.S]], [ix[row.W]], [sc["h"][d]], [sc["sdpi"][d]], e, x, K)
        if not (r["stopped"][0] and int(r["u"][0]) == u):
            problems.append(f"stop {days[d].date()}: decision bar {r['u'][0]} on cut frames vs {u}")
    # ---- no-stop decisions
    tm = t[t.reason == "time"]
    for _, row in tm.sample(25, random_state=5).iterrows():
        d = int(row.session)
        cutoff = int(rng.integers(1, x - e))                         # minutes after the entry
        tau = int(P["t0m"][d] + e + cutoff)
        Pc, sc = pipeline(cut_frames(fr, tau), days)
        checks["no_stop"] += 1
        r = C.sim_pairs(Pc, [d], [ix[row.S]], [ix[row.W]], [sc["h"][d]], [sc["sdpi"][d]], e, x, K)
        if r["stopped"][0] and int(r["u"][0]) < cutoff:
            problems.append(f"no-stop {days[d].date()}: a stop appears before the cut on cut frames")
    out = {"config": "main", "decisions_checked": checks, "total": int(sum(checks.values())), "problems": problems,
           "pass": not problems,
           "method": "the three in-sample frames are cut at the decision time and the whole pipeline is rebuilt; "
                     "entry decisions cut at 10:00 New York (bars that started before 10:00 only), stop decisions cut at "
                     "the end of the decision bar, no-stop checks cut at a random minute of the hold"}
    C.jdump(out, os.path.join(C.OUT, "truncation.json"))
    print(out)


if __name__ == "__main__":
    main()
