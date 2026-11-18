"""Power count of idea 054 from the signal data alone (moves up to 10:00 New York; no price after a signal).
Also checks the early-close list against the bars (days whose last bar is labelled 12:00 New York on most shares)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
import signals as S

d = S.load_data()
cal = d["cal"]
m = S.moves(d)
out = {"calendar_rows_drop_late": int(len(cal)), "events_with_reaction_bars": int(len(m)),
       "events_by_reaction_year": {str(k): int(v) for k, v in m.groupby(pd.DatetimeIndex(m.session).year).size().items()},
       "abs_move_quantiles": {str(q): float(m.move.abs().quantile(q)) for q in (0.25, 0.5, 0.75, 0.9)}}
for th in (0.015, 0.02, 0.025, 0.03):
    s = m[m.move.abs() >= th]
    out[f"th{th}"] = {"n": int(len(s)), "long": int((s.move > 0).sum()), "short": int((s.move < 0).sum()),
                      "markets": int(s.market.nunique()),
                      "by_year": {str(k): int(v) for k, v in s.groupby(pd.DatetimeIndex(s.session).year).size().items()},
                      "max_market_n": int(s.groupby("market").size().max())}
# early closes seen in the bars: per NY date, share of shares whose last bar is labelled 12:00
last_h = []
for tk in S.tickers():
    ny = d[tk].index.tz_convert(S.NY)
    s = pd.Series(ny.hour, index=ny.tz_localize(None).normalize())
    last_h.append(s.groupby(level=0).max().rename(tk))
lh = pd.concat(last_h, axis=1)
frac12 = (lh <= 12).sum(axis=1) / lh.notna().sum(axis=1)
seen = sorted(str(x.date()) for x in frac12.index[frac12 > 0.5])
out["early_closes_in_bars"] = seen
out["early_closes_declared"] = [str(x.date()) for x in S.HALF_DAYS]
# events on early-close sessions (excluded) and events whose 10:00 bar is missing (bar existence only)
allm = []
for tk, g in cal.groupby("ticker"):
    if tk in d:
        allm += [(tk, x) for x in pd.DatetimeIndex(g.reaction_session) if x in S.HALF_DAYS]
out["events_on_early_closes"] = [f"{a} {b.date()}" for a, b in allm]
miss10 = 0
s2 = m[m.move.abs() >= 0.02]
for tk, g in s2.groupby("market"):
    t = d[tk].index
    miss10 += int((~pd.DatetimeIndex(g.known_at).isin(t)).sum())
out["th0.02_signals_without_a_bar_opening_at_10"] = miss10
print(json.dumps(out, indent=1))
json.dump(out, open(os.path.join(HERE, "power.json"), "w"), indent=1)
