"""Diagnostic (not a declared plan): what "double the first 1,000 EUR in a month" asks of the ten rules as they are.
Flat risk per trade, 1,000 EUR, the first 4 weeks, 2,000 resampled paths, paper and half edge. Validation trades (logged)."""
import json, os, sys
import numpy as np
sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/stake")
import growth as G

STAKES = (1.0, 2.0, 3.0, 5.0, 7.5, 10.0, 15.0, 20.0, 30.0)
for s in STAKES:
    G.SCHEDULES[f"X{s:g}"] = ((), (s,))
d = G.load("val")
x = G.arrays(d, "today")
rng = np.random.default_rng(G.SEED + 7)
plan, n_weeks = G.draw_paths(x, 2000, 1, rng)
order = np.argsort(x["wk_in"], kind="stable")
first = np.searchsorted(x["wk_in"][order], np.arange(x["nwk"] + 1), side="left")
none = np.zeros(0, dtype=np.int64)
out = {}
for f in (1.0, 0.5):
    pnl = G.with_edge(x, f)
    res = {s: [] for s in STAKES}
    for k in range(len(plan)):
        parts = [order[first[w]:first[w + 1]] for w in plan[k]]
        idx = np.concatenate(parts)
        pos = np.repeat(np.arange(n_weeks), [len(q) for q in parts]).astype(np.int64)
        t_in = pos * G.WEEK + x["off_in"][idx]; t_out = pos * G.WEEK + x["off_out"][idx]
        t = (t_in, t_out, pos, pos + (x["wk_out"][idx] - x["wk_in"][idx]), t_in // G.DAY, t_out // G.DAY)
        pk = G.pack(x, idx, t, n_weeks)
        for s in STAKES:
            eq, pd_, c = G.run_one(pk, pnl, f"X{s:g}", none, none, np.zeros(0))
            e = np.r_[1000.0, eq[:4]]
            top = np.maximum.accumulate(e)
            res[s].append((e[-1], (1 - e / top).max(), c[6], c[2], c[0]))
    out[str(f)] = {}
    for s in STAKES:
        a = np.array(res[s])
        r = a[:, 0] / 1000.0 - 1.0
        out[str(f)][f"{s:g}"] = dict(median_month_pct=float(np.median(r) * 100), p10=float(np.percentile(r, 10) * 100), p90=float(np.percentile(r, 90) * 100),
                                    doubles_pct=float((a[:, 0] >= 2000).mean() * 100), up50_pct=float((a[:, 0] >= 1500).mean() * 100),
                                    loses_pct=float((a[:, 0] < 1000).mean() * 100),
                                    fall20_pct=float((a[:, 1] >= 0.2).mean() * 100), fall50_pct=float((a[:, 1] >= 0.5).mean() * 100),
                                    ends_under_half_pct=float((a[:, 0] <= 500).mean() * 100), wiped_pct=float((a[:, 2] > 0).mean() * 100),
                                    fall_median_pct=float(np.median(a[:, 1]) * 100), fall_p90_pct=float(np.percentile(a[:, 1], 90) * 100),
                                    taken_median=float(np.median(a[:, 4])), minlot_skips_median=float(np.median(a[:, 3])))
        o = out[str(f)][f"{s:g}"]
        print(f"edge x{f} stake {s:5g} %: month 1 median {o['median_month_pct']:+7.1f} % (1 in 10: {o['p10']:+7.1f} .. {o['p90']:+7.1f}) | doubles {o['doubles_pct']:5.1f} % | +50 % {o['up50_pct']:5.1f} % | "
              f"ends in loss {o['loses_pct']:5.1f} % | fall >= 20 % {o['fall20_pct']:5.1f} % | fall >= 50 % {o['fall50_pct']:5.1f} % | wiped {o['wiped_pct']:5.1f} % | fall median {o['fall_median_pct']:5.1f} % (1 in 10: {o['fall_p90_pct']:5.1f}) | trades {o['taken_median']:.0f}")
json.dump(out, open("/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/x2/x2.json", "w"), indent=1)
