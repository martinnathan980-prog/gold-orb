"""Idea 036 power check: count the main configuration's signal days from VIXCLS and ^GSPC closes only (no price move
after a signal, no return). Run before the declaration."""
import os, sys
os.environ.setdefault("EXPLORE_CACHE", os.path.expanduser("~/explore_data/idea_036"))
os.environ.setdefault("EXPLORE_H1_DIR", os.path.expanduser("~/explore_data/h1"))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import numpy as np, pandas as pd
from kit import data
vix = data.fred("VIXCLS", known=data.rule_local_close("16:30"))
spx = data.yahoo_daily("^GSPC", known=data.rule_local_close("16:30"))
v = pd.Series(vix.to_numpy(), index=pd.DatetimeIndex(vix.attrs["obs_date"]))
s = pd.Series(spx.to_numpy(), index=pd.DatetimeIndex(spx.index.tz_convert("America/New_York").tz_localize(None).normalize()))
for rvn, win, p in [(20, 500, 0.8), (20, 500, 0.75), (20, 500, 0.85), (20, 250, 0.8)]:
    rv = np.log(s).diff().rolling(rvn).std() * np.sqrt(252) * 100
    x = (v - rv).dropna()
    thr = x.shift(1).rolling(win).quantile(p)
    sig = x[(x > thr) & thr.notna()]
    sig = sig[(sig.index >= "2013-01-01") & (sig.index < "2021-12-31")]
    print(rvn, win, p, "signals 2013-2021:", len(sig), sig.groupby(sig.index.year).size().to_dict())
