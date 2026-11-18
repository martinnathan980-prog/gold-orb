"""Idea 052: signal build (earnings reaction at 15:00 New York). Imported by power.py and run.py (not by attack.py).

For each results row of the EDGAR calendar (drop_late=True): reaction session R (first regular session starting after
the 8-K acceptance time, column reaction_session). Move = close of the bar labelled 14:00 New York on R / the last close
of the previous session in the share's bars - 1. Known at the END of that bar (15:00 New York). Signal if |move| >= th:
side = sign(move). Only ratios of prices are used (bars are split-adjusted).
"""
import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
EXPLORE = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(EXPLORE, "scout"))
NY = "America/New_York"


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
    """Per session (NY date) of one share's bars: close of the 14:00-labelled bar, its open time (UTC ns), last close."""
    if not len(b):
        return pd.DataFrame(columns=["c14", "t14", "last"])
    ny = b.index.tz_convert(NY)
    day = ny.tz_localize(None).normalize()
    close = b["close"].to_numpy(float)
    dv = day.values
    last_mask = np.r_[dv[1:] != dv[:-1], True]
    last = pd.Series(close[last_mask], index=dv[last_mask])
    m14 = (ny.hour == 14)
    c14 = pd.Series(close[m14], index=dv[m14])
    t14 = pd.Series(b.index[m14].as_unit("ns").asi8, index=dv[m14])
    st = pd.DataFrame({"last": last})
    st["prev_last"] = st["last"].shift(1)
    st["c14"] = c14
    st["t14"] = t14
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
        sel = st.reindex(g["reaction_session"].to_numpy())
        ok = sel["c14"].notna().to_numpy() & sel["prev_last"].notna().to_numpy()
        if not ok.any():
            continue
        s = sel[ok]
        rows.append(pd.DataFrame({
            "market": tk, "session": s.index,
            "known_at": pd.DatetimeIndex(s["t14"].astype("int64").to_numpy()).tz_localize("UTC") + pd.Timedelta(hours=1),
            "move": s["c14"].to_numpy() / s["prev_last"].to_numpy() - 1.0}))
    if not rows:
        return pd.DataFrame(columns=["market", "session", "known_at", "move"])
    return pd.concat(rows, ignore_index=True)


def build(d, th=0.03):
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
