"""Load Yahoo daily series from the cache ~/explore_data/yahoo (fetched with period2 = 2021-12-31), cut at 2021-12-31."""
import json, os
import pandas as pd
D = os.path.expanduser("~/explore_data/yahoo")
CUT = pd.Timestamp("2022-01-01")

def load(name):
    r = json.load(open(os.path.join(D, name + ".json")))["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    idx = pd.to_datetime(r["timestamp"], unit="s").normalize()
    df = pd.DataFrame({"open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"],
                       "adj": r["indicators"]["adjclose"][0]["adjclose"]}, index=idx)
    df = df[df.index < CUT].dropna()
    return df[~df.index.duplicated()]
