"""Idea 060: the signal build (shared by power.py and run.py). Signal data only: the 8-K results calendar and the
event session's own move (no price after the signal's known_at is read here).
Event: a results 8-K (events_edgar.idea_sessions('059'): late_suspect rows dropped), accepted at accepted_utc.
Event session S = the share's first session whose CLOSE is strictly after the acceptance (= the calendar's
event_session; checked in power.py). Abnormal move = ret_total(S) - median over the universe's shares of ret_total(S).
Signal if |abnormal| >= threshold and S not flagged 'action'; side = sign; known_at = S's close (the bar's known_at)."""
import os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
EXPLORE = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, EXPLORE)
sys.path.insert(0, os.path.join(EXPLORE, "scout"))
from kit import data  # noqa: E402

KEYS = pd.read_csv(os.path.join(EXPLORE, "kit", "universe_us.csv")).key.tolist()


def load_events():
    """The results events as a kit event table (index = acceptance time, UTC; publication lag 0: the 8-K is public
    when EDGAR accepts it), columns ticker (the share's key; NOT named 'market': kit v2.2 checks._check_row_len takes
    any frame with a 'market' column of class shares for daily bars and refuses row_len 0) and session (the calendar's event_session, New York date, for checks)."""
    from events_edgar import idea_sessions, calendar
    s = idea_sessions("059")
    cal = calendar("2021-12-31", kind="results", drop_late=True)
    acc = dict(zip(cal.accession, pd.to_datetime(cal.accepted_utc, utc=True)))
    t = pd.DatetimeIndex([acc[a] for a in s.accession]).tz_convert("UTC").tz_localize(None)
    ev = data.event_table(t, known=lambda o: o, min_lag=pd.Timedelta(0), name="results_8k",
                          ticker=s.key.astype(str).to_numpy(),
                          session=pd.to_datetime(s.session).dt.strftime("%Y-%m-%d").to_numpy())
    return ev


def make_build(threshold):
    def build(d):
        b = d["bars"]
        mv = data.session_moves(b)
        tab = pd.DataFrame({"market": b["market"].astype(str).to_numpy(), "known_at": b["known_at"].to_numpy(),
                            "ret_total": mv["ret_total"].to_numpy(float), "action": mv["action"].to_numpy(bool)})
        tab["med"] = tab.groupby("known_at")["ret_total"].transform("median")
        tab["abn"] = tab["ret_total"] - tab["med"]
        ev = d["events"]
        e = pd.DataFrame({"t": pd.DatetimeIndex(ev.index).tz_convert("UTC").as_unit("ns"),
                          "market": ev["ticker"].astype(str).to_numpy()}).sort_values("t", kind="mergesort")
        tab["t"] = pd.DatetimeIndex(tab["known_at"]).tz_convert("UTC").as_unit("ns")
        tb = tab.sort_values("t", kind="mergesort")
        # first session of the share whose close is STRICTLY after the acceptance (= the calendar's event_session)
        o = pd.merge_asof(e, tb[["t", "market", "known_at", "abn", "action"]], on="t", by="market",
                          direction="forward", allow_exact_matches=False)
        o = o.dropna(subset=["known_at"])
        o = o.drop_duplicates(["market", "known_at"])           # two results 8-Ks on one session count once
        o["action"] = o["action"].astype(bool)
        ok = np.isfinite(o["abn"].to_numpy(float)) & ~o["action"].to_numpy(bool) & \
            (np.abs(o["abn"].to_numpy(float)) >= threshold)
        o = o[ok]
        sig = pd.DataFrame({"known_at": pd.DatetimeIndex(o["known_at"]).tz_convert("UTC"),
                            "side": np.sign(o["abn"].to_numpy(float)).astype(int), "market": o["market"].to_numpy()})
        return sig.sort_values(["known_at", "market"], kind="mergesort").reset_index(drop=True)
    return build


def load_data():
    bs = {k: data.load_bars(k) for k in KEYS}
    return bs, {"bars": data.long_bars(bs), "events": load_events()}
