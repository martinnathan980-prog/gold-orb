"""Idea 053 power check from the calendar alone (no price): signals of the main configuration with bars possible.
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/053_earnings_expected_runup/power.py"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
import signals as S

d = {"cal": S.load_calendar()}
sig = S.build(d, 5)
ev = S.build_events(d, 1)
det = S.detail(d, 5, 1)
first_bar = pd.Timestamp("2017-01-26", tz="UTC") + pd.Timedelta(days=35)      # D20 needs ~20 sessions of bars
ok = (sig.known_at >= first_bar)
# exit must be inside the period: event before 2022
lastev = pd.Timestamp("2021-12-31 21:00", tz="UTC")
det_in = det[(det.X <= pd.Timestamp("2021-12-30")) & (det.S >= pd.Timestamp("2017-03-01"))]
# matching each expected E with the actual release of that quarter (any 'results' row, late rows included,
# reaction session within 45 days of E): information only
from earnings_edgar import calendar
allc = calendar(end="2021-12-31")
allc["rs"] = pd.to_datetime(allc.reaction_session).dt.normalize()
rel = []
for _, r in det_in.iterrows():
    g = allc[(allc.ticker == r.market) & ((allc.rs - r.E).abs() <= pd.Timedelta(days=45))]
    if not len(g):
        rel.append("no_actual"); continue
    a = g.rs.iloc[np.argmin((g.rs - r.E).abs().to_numpy())]
    if a < r.S: rel.append("before_entry")
    elif a == r.S: rel.append("on_entry_day")
    elif a <= r.X: rel.append("inside_hold")
    elif a == r.E: rel.append("on_E")
    else: rel.append("after_E")
rel = pd.Series(rel)
out = {"calendar_rows_drop_late": int(len(d["cal"])), "signals_built_before_2022": int(len(sig)),
       "main_signals_with_entry_and_exit_in_sample": int(len(det_in)),
       "by_entry_year": {str(k): int(v) for k, v in det_in.S.dt.year.value_counts().sort_index().items()},
       "shares": int(det_in.market.nunique()),
       "actual_reaction_vs_expected": {k: int(v) for k, v in rel.value_counts().items()},
       "exit_events_before_2022": int(len(ev))}
print(json.dumps(out, indent=1))
json.dump(out, open(os.path.join(HERE, "power.json"), "w"), indent=1)
