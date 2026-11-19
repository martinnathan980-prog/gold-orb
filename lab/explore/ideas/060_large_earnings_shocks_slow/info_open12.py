"""Idea 060, INFORMATION ONLY (never judged): the main configuration with the order at the session's open priced like
an order at a close (spread_bps_open 12 instead of 56). Run in a SEPARATE process:
    EXPLORE_EXTRA_COSTS=~/explore_data/idea_060/extra_costs_open12.json PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore \
        python3 -B lab/explore/ideas/060_large_earnings_shocks_slow/info_open12.py
(the script writes that copy of kit/extra_costs.json itself when it is missing, then re-runs itself with the variable
set). Writes ~/explore_data/idea_060/info_open12.json and extra_open12.json in the idea folder; never results.json or
trials.jsonl, never calls judge.verdict."""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.expanduser("~/explore_data/idea_060")
ALT = os.path.join(CACHE, "extra_costs_open12.json")

if os.environ.get("EXPLORE_EXTRA_COSTS") != ALT:
    os.makedirs(CACHE, exist_ok=True)
    src = os.path.join(HERE, "..", "..", "kit", "extra_costs.json")
    d = json.load(open(src))
    d["_classes"]["us_shares_d1"]["spread_bps_open"] = 12.0
    json.dump(d, open(ALT, "w"), indent=1)
    env = dict(os.environ, EXPLORE_EXTRA_COSTS=ALT)
    sys.exit(subprocess.call([sys.executable, "-B", os.path.abspath(__file__)], env=env))

sys.path.insert(0, HERE)
import pandas as pd  # noqa: E402
from signals import load_data, make_build  # noqa: E402
from kit import sim, stats, costs  # noqa: E402

decl = json.load(open(os.path.join(HERE, "declared.json")))
m0 = decl["configurations"][0]
assert costs.spec("a")["spread_bps_open"] == 12.0, "the modified cost file is not in use"
bs, d = load_data()
sig = make_build(m0["threshold"])(d)
bk = sim.books(bs)
t = sim.simulate(sig, bk, max_wait_h=96, exit=tuple(m0["exit"]), stop=tuple(m0["stop"]))
day = pd.DatetimeIndex(t.entry_time).tz_convert("UTC").normalize()
yr = pd.DatetimeIndex(t.entry_time).year
f = lambda x: {"n": int(len(x)), "PF_net": stats.pf(x.R), "mean_R": float(x.R.mean()), "PF_gross": stats.pf(x.R_gross),
               "mean_net_bp": float(x.net_bp.mean()), "PF_stress": stats.pf(x.R_stress)}  # noqa: E731
out = {"note": "INFORMATION ONLY, not judged: the main configuration with spread_bps_open = 12 (open priced like a close)",
       "all": f(t), "t_daily_net": float(stats.t_stat(t.R.groupby(day).sum())), "long": f(t[t.side > 0]),
       "short": f(t[t.side < 0]), "by_year": {int(y): f(t[yr == y]) for y in sorted(set(yr))}}
json.dump(out, open(os.path.join(CACHE, "info_open12.json"), "w"), indent=1)
json.dump(out, open(os.path.join(HERE, "extra_open12.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
