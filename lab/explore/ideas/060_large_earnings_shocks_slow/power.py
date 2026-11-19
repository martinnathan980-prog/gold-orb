"""Idea 060, power first: count the signals from the signal data alone (no price after a signal is read).
Writes ~/explore_data/idea_060/power.json and power.json in the idea folder."""
import json, os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from signals import load_data, make_build, HERE  # noqa: E402

t0 = time.time()
bs, d = load_data()
ev = d["events"]
print("events", len(ev), "bars rows", len(d["bars"]), f"{time.time()-t0:.0f}s")
# check: the session found by the build (first close strictly after acceptance) equals the calendar's event_session
b = d["bars"]
ka = pd.DatetimeIndex(b["known_at"]).as_unit("ns").asi8
mk = b["market"].astype(str).to_numpy()
mism, miss = 0, 0
g = {}
for k in np.unique(mk):
    g[k] = (ka[mk == k], pd.DatetimeIndex(b.index[mk == k]).tz_convert("America/New_York").strftime("%Y-%m-%d"))
for t, k, s in zip(pd.DatetimeIndex(ev.index).as_unit("ns").asi8, ev.ticker, ev.session):
    if k not in g:
        miss += 1; continue
    kk, dd = g[k]
    i = np.searchsorted(kk, t, side="right")
    if i >= len(kk):
        miss += 1; continue
    if dd[i] != s:
        mism += 1
out = {"events": int(len(ev)), "session_mismatch_vs_calendar": mism, "no_bar": miss}
for thr in (0.06, 0.08, 0.10):
    s = make_build(thr)(d)
    y = pd.DatetimeIndex(s.known_at).year
    out[f"thr_{thr}"] = {"n": int(len(s)), "long": int((s.side > 0).sum()), "short": int((s.side < 0).sum()),
                         "days": int(s.known_at.nunique()), "markets": int(s.market.nunique()),
                         "by_year": {int(k): int(v) for k, v in pd.Series(y).value_counts().sort_index().items()}}
    print(thr, out[f"thr_{thr}"])
out["note"] = ("signal counts before the one-position filter and before D20 availability (a share's first 20 sessions "
               "have no D20); with a 40-session hold one position per share can only drop signals within 40 sessions "
               "of an earlier one of the same share, i.e. almost none (results are about 63 sessions apart)")
for p in (os.path.expanduser("~/explore_data/idea_060/power.json"), os.path.join(HERE, "power.json")):
    json.dump(out, open(p, "w"), indent=1)
print(json.dumps(out, indent=1), f"{time.time()-t0:.0f}s")
