"""Power count of idea 052 from the signal data alone (moves up to the signal time; no price after a signal)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
import signals as S

d = S.load_data()
cal = d["cal"]
m = S.moves(d)
out = {"calendar_rows_drop_late": int(len(cal)), "events_with_reaction_bars": int(len(m)),
       "events_by_reaction_year": {str(k): int(v) for k, v in m.groupby(pd.DatetimeIndex(m.session).year).size().items()},
       "abs_move_quantiles": {str(q): float(m.move.abs().quantile(q)) for q in (0.25, 0.5, 0.75, 0.9)}}
for th in (0.02, 0.025, 0.03, 0.04):
    s = m[m.move.abs() >= th]
    out[f"th{th}"] = {"n": int(len(s)), "long": int((s.move > 0).sum()), "short": int((s.move < 0).sum()),
                      "markets": int(s.market.nunique()),
                      "by_year": {str(k): int(v) for k, v in s.groupby(pd.DatetimeIndex(s.session).year).size().items()},
                      "max_market_n": int(s.groupby("market").size().max())}
# windows of 5 business days that hold a holiday (the declared ('bdays', 5) exit is then one session early)
s = m[m.move.abs() >= 0.03]
hol = 0
for tk, g in s.groupby("market"):
    days = pd.DatetimeIndex(sorted(set(d[tk].index.tz_convert(S.NY).tz_localize(None).normalize())))
    for r in pd.DatetimeIndex(g.session):
        end = r + pd.offsets.BDay(5)
        if ((days > r) & (days <= end)).sum() < 5 and end <= days[-1]:
            hol += 1
out["th0.03_windows_with_a_holiday_or_missing_day"] = hol
print(json.dumps(out, indent=1))
json.dump(out, open(os.path.join(HERE, "power.json"), "w"), indent=1)
