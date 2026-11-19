"""Idea 062, INFORMATION ONLY (declared, never judged): the main configuration with the session-open spread priced like a
close (12 bp instead of 56 bp), in a SEPARATE process. Needs EXPLORE_EXTRA_COSTS pointing at a copy of
kit/extra_costs.json with _classes.us_shares_d1.spread_bps_open = 12 (~/explore_data/idea_062/extra_costs_open12.json).
Writes info_open12.json only; never results.json or trials.jsonl.
    EXPLORE_EXTRA_COSTS=~/explore_data/idea_062/extra_costs_open12.json PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore \
        python3 -B lab/explore/ideas/062_no_news_moves_fade/info_open12.py"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
sys.path.insert(0, HERE)
import numpy as np
p = os.environ.get("EXPLORE_EXTRA_COSTS", "")
assert p and os.path.abspath(p) != os.path.abspath(os.path.join(HERE, "..", "..", "kit", "extra_costs.json")), p
from kit import checks, costs, sim
import signals as S

assert float(costs.spec(S.keys()[0])["spread_bps_open"]) == 12.0
checks.declared_hash(HERE)
c = json.load(open(os.path.join(HERE, "declared.json")))["configurations"][0]
d = S.load_data()
sig = S.build(d, c["threshold"])
bk = sim.books(S.BS)
t = sim.simulate(sig, bk, exit=tuple(c["exit"]), stop=tuple(c["stop"]), max_wait_h=96)
def pf(x):
    x = np.asarray(x, float); return float(x[x > 0].sum() / -x[x < 0].sum())
def tday(t):
    s = t.groupby(t.entry_time.dt.tz_convert("America/New_York").dt.date)["R"].sum()
    return float(s.mean() / s.std(ddof=1) * np.sqrt(len(s)))
out = {"note": "information only, open spread 12 bp (separate process), never judged",
       "n": int(len(t)), "PF_net": pf(t.R), "PF_stress": pf(t.R_stress), "PF_gross": pf(t.R_gross),
       "mean_R": float(t.R.mean()), "t_daily_net": tday(t), "mean_net_bp": float(t.net_bp.mean()),
       "mean_gross_bp": float(t.gross_bp.mean()),
       "long": {"n": int((t.side > 0).sum()), "PF_net": pf(t.R[t.side > 0]), "mean_net_bp": float(t.net_bp[t.side > 0].mean())},
       "short": {"n": int((t.side < 0).sum()), "PF_net": pf(t.R[t.side < 0]), "mean_net_bp": float(t.net_bp[t.side < 0].mean())}}
json.dump(out, open(os.path.join(HERE, "info_open12.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
