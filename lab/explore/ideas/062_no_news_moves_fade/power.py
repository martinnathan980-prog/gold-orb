"""Idea 062, power count BEFORE the declaration: signals counted from the signal data alone (the abnormal ret_total of
the signal session, the calm filter, the no-filing set; no price after the signal session is read, no return computed).
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/062_no_news_moves_fade/power.py"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
sys.path.insert(0, HERE)
import signals as S

d = S.load_data()
out = {}
for th in (0.05, 0.06, 0.08):
    s = S.build(d, th)
    yrs = s.known_at.dt.tz_convert("America/New_York").dt.year
    out[str(th)] = {"n": int(len(s)), "days": int(s.known_at.nunique()), "long_after_fall": int((s.side > 0).sum()),
                    "short_after_rise": int((s.side < 0).sum()),
                    "by_year": {str(k): int(v) for k, v in yrs.value_counts().sort_index().items()},
                    "markets": int(s.market.nunique()), "sectors": int(s.market.map(S.sector_map()).nunique()),
                    "by_sector": {k: int(v) for k, v in s.market.map(S.sector_map()).value_counts().items()}}
out["allowed_share_sessions"] = int(len(d["allowed"]))
print(json.dumps(out, indent=1))
json.dump(out, open(os.path.join(HERE, "power.json"), "w"), indent=1)
