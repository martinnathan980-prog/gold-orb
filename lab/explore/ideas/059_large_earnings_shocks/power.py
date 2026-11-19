"""Idea 059, power count BEFORE the declaration: signals of the main rule counted from the signal data alone (the
abnormal ret_total of the results' event session; no price after the signal session is read, no return computed).
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/059_large_earnings_shocks/power.py"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
sys.path.insert(0, HERE)
import signals as S

d = S.load_data()
out = {}
for th in (0.06, 0.08, 0.10):
    s = S.build(d, th)
    yrs = s.known_at.dt.tz_convert("America/New_York").dt.year
    out[str(th)] = {"n": int(len(s)), "days": int(s.known_at.nunique()), "up": int((s.side > 0).sum()),
                    "down": int((s.side < 0).sum()), "by_year": {str(k): int(v) for k, v in yrs.value_counts().sort_index().items()},
                    "markets": int(s.market.nunique()), "sectors": int(s.market.map(S.sector_map()).nunique())}
out["events_in_window"] = int(len(d["events"]))
print(json.dumps(out, indent=1))
json.dump(out, open(os.path.join(HERE, "power.json"), "w"), indent=1)
