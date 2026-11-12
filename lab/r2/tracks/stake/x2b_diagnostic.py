"""Diagnostic: how much better must every trade be for 'double in a month with falls under 20 %'?
The edge of every rule is multiplied by f (noise unchanged); first 4 weeks, 1,000 EUR, flat stake; 1,000 resampled paths."""
import json, sys
import numpy as np
sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/stake")
import growth as G

STAKES = (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.5, 10.0)
for s in STAKES:
    G.SCHEDULES[f"X{s:g}"] = ((), (s,))
d = G.load("val")
x = G.arrays(d, "today")
rng = np.random.default_rng(G.SEED + 7)
plan, n_weeks = G.draw_paths(x, 1000, 1, rng)
order = np.argsort(x["wk_in"], kind="stable")
first = np.searchsorted(x["wk_in"][order], np.arange(x["nwk"] + 1), side="left")
none = np.zeros(0, dtype=np.int64)
out = {}
for f in (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0):
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
            res[s].append((e[-1], (1 - e / top).max()))
    out[str(f)] = {}
    line = []
    for s in STAKES:
        a = np.array(res[s]); r = a[:, 0] / 1000.0 - 1.0
        o = dict(median=float(np.median(r) * 100), doubles=float((a[:, 0] >= 2000).mean() * 100), fall20=float((a[:, 1] >= 0.2).mean() * 100),
                 fall10=float((a[:, 1] >= 0.1).mean() * 100), fall50=float((a[:, 1] >= 0.5).mean() * 100), loses=float((r < 0).mean() * 100))
        out[str(f)][f"{s:g}"] = o
        line.append(f"{s:g}%: med {o['median']:+5.0f} dbl {o['doubles']:3.0f} f20 {o['fall20']:3.0f} f50 {o['fall50']:2.0f}")
    print(f"edge x{f:g} | " + " | ".join(line))
json.dump(out, open("/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/x2/x2b.json", "w"), indent=1)
