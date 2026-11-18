"""Idea 054: signal build (earnings day, follow the move read at 10:00 New York). Imported by power.py and run.py
(not by attack.py).

For each results row of the EDGAR calendar (drop_late=True): reaction session R (column reaction_session = first
regular session starting strictly after the 8-K acceptance time). Move = close of the FIRST bar of R (labelled 09:00
New York, runs 09:30-10:00) / close of the last bar of the previous session present in the share's bars - 1. Known at
the END of the first bar (10:00 New York). Signal if |move| >= th: side = sign(move). Sessions that are NYSE early
closes (13:00, a list fixed in advance by the exchange calendar) give no signal. Only ratios of prices are used.
"""
import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
EXPLORE = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(EXPLORE, "scout"))
NY = "America/New_York"
# NYSE scheduled early closes (13:00 New York) 2017-2021, published by the exchange a year or more in advance
HALF_DAYS = pd.DatetimeIndex(["2017-07-03", "2017-11-24", "2018-07-03", "2018-11-23", "2018-12-24", "2019-07-03",
                              "2019-11-29", "2019-12-24", "2020-11-27", "2020-12-24", "2021-11-26"])


def tickers():
    import json
    j = json.load(open(os.path.join(EXPLORE, "kit", "extra_costs.json")))
    return sorted(k for k in j if not k.startswith("_") and k != "oil")


def load_calendar():
    from earnings_edgar import calendar
    cal = calendar(end="2021-12-31", drop_late=True)
    cal = cal[["ticker", "accepted_utc", "reaction_session"]].copy()
    cal["reaction_session"] = pd.to_datetime(cal["reaction_session"]).dt.normalize()
    cal = cal.set_index(pd.DatetimeIndex(cal.pop("accepted_utc")).rename("known")).sort_index()
    return cal          # indexed by the acceptance time (UTC), the time the release is known


def session_table(b):
    """Per session (NY date) of one share's bars: close of the 09:00-labelled bar (c09), its open time (UTC ns), and the
    previous present session's last close (prev_last)."""
    if not len(b):
        return pd.DataFrame(columns=["c09", "t09", "last", "prev_last"])
    ny = b.index.tz_convert(NY)
    day = ny.tz_localize(None).normalize()
    close = b["close"].to_numpy(float)
    dv = day.values
    last_mask = np.r_[dv[1:] != dv[:-1], True]
    st = pd.DataFrame({"last": pd.Series(close[last_mask], index=dv[last_mask])})
    st["prev_last"] = st["last"].shift(1)
    m09 = (ny.hour == 9)
    st["c09"] = pd.Series(close[m09], index=dv[m09])
    st["t09"] = pd.Series(b.index[m09].as_unit("ns").asi8, index=dv[m09])
    return st


def moves(d):
    """One row per calendar event with a computable move: market, reaction session, known_at, move."""
    cal = d["cal"]
    rows = []
    for tk, g in cal.groupby("ticker"):
        if tk not in d:
            continue
        st = session_table(d[tk])
        if not len(st):
            continue
        sess = pd.DatetimeIndex(g["reaction_session"].to_numpy())
        sel = st.reindex(sess)
        ok = sel["c09"].notna().to_numpy() & sel["prev_last"].notna().to_numpy() & ~sess.isin(HALF_DAYS)
        if not ok.any():
            continue
        s = sel[ok]
        rows.append(pd.DataFrame({
            "market": tk, "session": s.index,
            "known_at": pd.DatetimeIndex(s["t09"].astype("int64").to_numpy()).tz_localize("UTC") + pd.Timedelta(hours=1),
            "move": s["c09"].to_numpy() / s["prev_last"].to_numpy() - 1.0}))
    if not rows:
        return pd.DataFrame(columns=["market", "session", "known_at", "move"])
    return pd.concat(rows, ignore_index=True)


def build(d, th=0.02):
    m = moves(d)
    m = m[m["move"].abs() >= th]
    out = pd.DataFrame({"known_at": pd.DatetimeIndex(m["known_at"]), "side": np.sign(m["move"]).astype(int).to_numpy(),
                        "market": m["market"].to_numpy()})
    return out.sort_values(["known_at", "market"]).reset_index(drop=True)


def load_data():
    from kit import data
    d = {"cal": load_calendar()}
    for tk in tickers():
        d[tk] = data.load_bars(tk)
    return d


def row_len(d):
    return {k: (pd.Timedelta(0) if k == "cal" else pd.Timedelta(hours=1)) for k in d}
