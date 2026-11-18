"""Idea 051, power check only (CHARTER 'Power first'): count the main configuration's signals from the signal data alone
(the weekend move itself; no price after the signal, no return). Writes power.json beside this file.
    EXPLORE_CACHE=~/explore_data/idea_051 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/051_btc_weekend_long_history/power.py
Weekend move = close of the bar opening Sunday 16:00 New York (the last price before FP's reopening at Sunday 17:00 NY,
known at 17:00) / close of the bar opening Friday 16:00 New York (the last hourly close before Friday 17:00 NY) - 1,
both on one venue throughout (Bitstamp BTC/USD hourly, kit.data.crypto_h1, raw venue hours incl. the weekend).
A weekend is counted only if each reference bar has at least one traded hour (volume > 0) in the 6 hours ending at it
(guards against Bitstamp's flat outage candles, e.g. 2015-01-05..09)."""
import json, os
import pandas as pd
from kit import data

NY = "America/New_York"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "power.json")


def weekend_moves(d):
    ny = d.index.tz_convert(NY)
    act = (d.volume > 0).astype(int).rolling(6, min_periods=1).sum()
    fri = d[(ny.dayofweek == 4) & (ny.hour == 16)]
    sun = d[(ny.dayofweek == 6) & (ny.hour == 16)]
    fk = (fri.index.tz_convert(NY) + pd.Timedelta(days=2)).normalize().tz_localize(None)
    sk = sun.index.tz_convert(NY).normalize().tz_localize(None)
    f = pd.DataFrame({"f": fri.close.to_numpy(), "fa": act[fri.index].to_numpy()}, index=fk)
    s = pd.DataFrame({"s": sun.close.to_numpy(), "sa": act[sun.index].to_numpy()}, index=sk)
    j = f.join(s, how="inner")
    j["move"] = j.s / j.f - 1
    j["active"] = (j.fa > 0) & (j.sa > 0)
    return j


if __name__ == "__main__":
    d = data.crypto_h1("bitstamp", "btcusd", start="2012-11")
    j = weekend_moves(d)
    out = {"venue": "bitstamp btcusd 1h (raw venue hours, weekend included)", "bars": [str(d.index[0]), str(d.index[-1])],
           "rows": int(len(d)), "missing_hours": int(len(pd.date_range(d.index[0], d.index[-1], freq="h").difference(d.index)))}
    for start in ("2013-01-01", "2012-11-01"):
        jj = j[(j.index >= start) & j.active]
        m = jj.move
        out[f"from_{start}"] = {
            "weekends": int(len(jj)), "inactive_dropped": int(((j.index >= start) & ~j.active).sum()),
            "signals": {str(th): {"all": int((m.abs() >= th).sum()), "up": int((m >= th).sum()), "down": int((m <= -th).sum())}
                        for th in (0.015, 0.02, 0.025, 0.03)},
            "main_2pct_by_year": {int(k): int(v) for k, v in (m.abs() >= 0.02).groupby(m.index.year).sum().items()}}
    n_main = out["from_2013-01-01"]["signals"]["0.02"]["all"]
    out["main_n"] = n_main
    out["verdict"] = "insufficient_data" if n_main < 250 else "enough"
    json.dump(out, open(OUT, "w"), indent=1)
    print(json.dumps(out, indent=1))
