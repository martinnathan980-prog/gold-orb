"""Idea 038 (scout idea 24): power check from the signal data alone (FRED VXNCLS, VIXCLS; no price, no return).
PYTHONDONTWRITEBYTECODE=1 python3 -B power.py   -> power.json next to this file. Cache: ~/explore_data/idea_038."""
import os, sys, json
os.environ["EXPLORE_CACHE"] = os.path.expanduser("~/explore_data/idea_038")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import numpy as np, pandas as pd
from kit import data
rule = data.rule_local_close("17:45")            # CBOE files rewritten ~17:31 NY; FRED shows D on D+1
vxn = data.fred("VXNCLS", known=rule, start="2011-01-01"); vix = data.fred("VIXCLS", known=rule, start="2011-01-01")
vxn.attrs = {}; vix.attrs = {}
df = pd.concat({"vxn": vxn, "vix": vix}, axis=1).dropna()
x = np.log(df.vxn / df.vix)
out = {"source": "FRED VXNCLS, VIXCLS (fredgraph.csv, cut 2021-12-31), z on past 60 trading days incl. D",
       "first_obs": str(df.index[0]), "last_obs": str(df.index[-1]), "counted_from": "2013-01-01 (prepared bars 2013-2021)",
       "rows": {}}
for L, th, hold in [(60, 2.0, 3), (60, 1.5, 3), (60, 2.5, 3), (40, 2.0, 3), (90, 2.0, 3), (60, 2.0, 1)]:
    z = (x - x.rolling(L).mean()) / x.rolling(L).std()
    z = z[z.index >= pd.Timestamp("2013-01-01", tz="UTC")]
    hit = z[z.abs() >= th]
    pos = {d: i for i, d in enumerate(z.index)}; n1, last = 0, -99
    for d in hit.index:                              # one position at a time, hold = `hold` trading days
        if pos[d] >= last + hold: n1 += 1; last = pos[d]
    ep = int(((z.abs() >= th) & ~(z.abs() >= th).shift(1, fill_value=False)).sum())
    out["rows"][f"L{L}_th{th}_hold{hold}"] = {"signal_days": int(len(hit)), "z_high": int((hit > 0).sum()),
        "z_low": int((hit < 0).sum()), "episodes": ep, "trades_one_position": n1,
        "by_year": {str(k): int(v) for k, v in hit.groupby(hit.index.year).size().items()}}
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "power.json"), "w"), indent=1)
print(json.dumps(out["rows"], indent=1))
