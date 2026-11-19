"""Idea 062 (large moves without news in a calm market: fade them; broad universe on daily bars): data and signal build.
Every feature is computed INSIDE build from the bars passed to it (kit v2.2: ratios only, row_len='known_at').
Session s of share k is a candidate when events_edgar.idea_sessions('062', results_ahead=0) lists (k, s): no 8-K / 8-K/A
of any kind and no 10-Q / 10-K with event_session in s-2..s, and no results-like session in s-2..s (all known at the
close of s). Each allowed share-session enters data.event_table stamped at the CLOSE of s (data.us_sessions close_utc).
Calm market: median over the universe's shares of |ret_total| on s < 2 %. Abnormal move = ret_total(s) minus the median
ret_total of the universe that session. No signal on a session flagged 'action'. |abn| >= threshold -> side = -sign(abn)
(fade), known at s's close (the bar's known_at); entry = next session's open (kit)."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
EXPLORE = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, EXPLORE)
sys.path.insert(0, os.path.join(EXPLORE, "scout"))
from kit import data

UNIV = os.path.join(EXPLORE, "kit", "universe_us.csv")
CALM = 0.02
BS = {}


def sector_map():
    u = pd.read_csv(UNIV)
    return dict(zip(u.key, u.sector))


def keys():
    return list(pd.read_csv(UNIV).key)


def load_allowed():
    from events_edgar import idea_sessions
    s = idea_sessions("062", results_ahead=0)
    obs = pd.DatetimeIndex(pd.to_datetime(s.session.astype(str)))
    ses = data.us_sessions("2016-01-01")
    close = pd.Series(ses.close_utc.to_numpy(), index=pd.DatetimeIndex(ses.index).normalize())
    missing = ~obs.isin(close.index)
    assert not missing.any(), obs[missing][:5]

    def known(o):
        return pd.DatetimeIndex(close.reindex(pd.DatetimeIndex(o).normalize()).to_numpy()).tz_convert("UTC")
    return data.event_table(obs, known=known, min_lag=pd.Timedelta(0), name="no_filing_sessions",
                            share=s.key.to_numpy(), session=obs.strftime("%Y-%m-%d").to_numpy())
    # label column "share", not "market" (as idea 059: a "market" column of class shares makes the truncation test
    # treat the item as daily bars and refuse row_len 0)


def load_data():
    global BS
    BS = {k: data.load_bars(k) for k in keys()}
    return {"bars": data.long_bars(BS), "allowed": load_allowed()}


def moves(d):
    b = d["bars"]
    mv = data.session_moves(b)
    t = pd.DatetimeIndex(b.index)
    rt = mv["ret_total"].to_numpy(float)
    g = pd.Series(rt).groupby(t.asi8)
    med = g.transform("median").to_numpy()                        # NaN (a share's first bar) skipped
    medabs = pd.Series(np.abs(rt)).groupby(t.asi8).transform("median").to_numpy()
    return pd.DataFrame({"market": b["market"].astype(str).to_numpy(),
                         "date": t.tz_convert("UTC").floor("D").tz_localize(None),
                         "known_at": pd.DatetimeIndex(b["known_at"]), "abn": rt - med, "medabs": medabs,
                         "action": mv["action"].to_numpy(bool)})


def build(d, threshold=0.06):
    m = moves(d)
    m = m[np.isfinite(m.abn) & ~m.action & (m.medabs < CALM) & (m.abn.abs() >= threshold)]
    al = d["allowed"]
    e = pd.DataFrame({"market": al["share"].astype(str).to_numpy(),
                      "date": pd.to_datetime(al["session"].astype(str).to_numpy())}).drop_duplicates()
    j = m.merge(e, on=["market", "date"], how="inner")
    out = pd.DataFrame({"known_at": pd.DatetimeIndex(j.known_at), "side": (-np.sign(j.abn)).astype(int).to_numpy(),
                        "market": j.market.to_numpy()})
    return out.sort_values(["known_at", "market"], kind="mergesort").reset_index(drop=True)
