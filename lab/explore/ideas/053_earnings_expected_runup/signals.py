"""Idea 053: signal and exit-event build (earnings run-up on the EXPECTED date). Imported by power.py and run.py
(not by attack.py).

For each quarterly results row P of the EDGAR calendar (calendar(end='2021-12-31', drop_late=True)), known at its
EDGAR acceptance time: E = the first regular NYSE session on or after (P's reaction session + 364 days), sessions
from the NYSE full-day holiday RULES (kit.data._nyse_holidays) plus the one special closure of the period
(2018-12-05, announced 2018-12-01). Entry: open of the bar labelled 10:00 New York of the session k sessions before
E (known_at = that bar's open; the date was computable a year earlier). Exit event: the open of the bar labelled
15:00 New York of the session m sessions before E (12:00 on the rule-known 13:00 early-close days). Long only.
Uses no price at all (so no absolute level).
"""
import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
EXPLORE = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(EXPLORE, "scout"))
sys.path.insert(0, EXPLORE)
NY = "America/New_York"
SPECIAL_CLOSURES = [pd.Timestamp("2018-12-05")]          # national day of mourning (G. H. W. Bush), announced 2018-12-01
# NYSE 13:00 early closes by rule (July 3 when a weekday before a weekday July 4, day after Thanksgiving, Dec 24 on a
# weekday that is not itself the observed Christmas): 2016-2022
EARLY_CLOSES = [pd.Timestamp(x) for x in (
    "2016-11-25", "2017-07-03", "2017-11-24", "2018-07-03", "2018-11-23", "2018-12-24", "2019-07-03", "2019-11-29",
    "2019-12-24", "2020-11-27", "2020-12-24", "2021-11-26", "2022-11-25")]


def tickers():
    import json
    j = json.load(open(os.path.join(EXPLORE, "kit", "extra_costs.json")))
    return sorted(k for k in j if not k.startswith("_") and k != "oil")


def sessions():
    from kit import data
    hol = set(pd.Timestamp(h) for h in data._nyse_holidays(2016, 2023)) | set(SPECIAL_CLOSURES)
    days = pd.bdate_range("2016-01-01", "2023-12-31")
    return pd.DatetimeIndex([d for d in days if d not in hol])


SESS = sessions()
EARLY = set(EARLY_CLOSES)


def load_calendar():
    from earnings_edgar import calendar
    cal = calendar(end="2021-12-31", drop_late=True)
    cal = cal[["ticker", "accepted_utc", "reaction_session"]].copy()
    cal["reaction_session"] = pd.to_datetime(cal["reaction_session"]).dt.normalize()
    cal = cal.set_index(pd.DatetimeIndex(cal.pop("accepted_utc")).rename("known")).sort_index()
    return cal          # indexed by the acceptance time (UTC), the time the release is known


def expected(cal):
    """Per calendar row: index of E in SESS (E = first session >= reaction + 364 days)."""
    target = pd.DatetimeIndex(cal["reaction_session"]) + pd.Timedelta(days=364)
    return np.searchsorted(SESS.values, target.values, side="left")


def _at(days, hh):
    return (pd.DatetimeIndex(days) + pd.Timedelta(hours=hh)).tz_localize(NY).tz_convert("UTC")


def build(d, k=5):
    cal = d["cal"]
    iE = expected(cal)
    S = SESS[iE - k]
    out = pd.DataFrame({"known_at": _at(S, 10), "side": 1, "market": cal["ticker"].to_numpy()})
    out = out[out["known_at"] < pd.Timestamp("2022-01-01", tz="UTC")]
    return out.sort_values(["known_at", "market"]).reset_index(drop=True)


def build_events(d, m=1):
    cal = d["cal"]
    iE = expected(cal)
    X = SESS[iE - m]
    hh = np.where(np.isin(X.values, np.array(sorted(EARLY), dtype="datetime64[ns]")), 12, 15)
    t = pd.DatetimeIndex([(x + pd.Timedelta(hours=int(h))) for x, h in zip(X, hh)]).tz_localize(NY).tz_convert("UTC")
    out = pd.DataFrame({"known_at": t, "market": cal["ticker"].to_numpy()})
    out = out[out["known_at"] < pd.Timestamp("2022-01-01", tz="UTC")]
    return out.sort_values(["known_at", "market"]).reset_index(drop=True)


def detail(d, k=5, m=1):
    """Diagnostic table (one row per calendar row): P's reaction, E, entry session, exit session."""
    cal = d["cal"]
    iE = expected(cal)
    return pd.DataFrame({"market": cal["ticker"].to_numpy(), "P_reaction": cal["reaction_session"].to_numpy(),
                         "E": SESS[iE], "S": SESS[iE - k], "X": SESS[iE - m]})
