"""Idea 059 (large earnings shocks, broad universe on daily bars): data loading and the signal build.
Every feature is computed INSIDE build from the bars passed to it (kit v2.2: ratios only, row_len='known_at').
Event session S of a results 8-K = the first session that closes after its EDGAR acceptance (events_edgar
idea_sessions('059'), late_suspect rows dropped). Abnormal move = ret_total(S) (data.session_moves: dividend added
back) minus the median ret_total of the universe's shares on S. No signal on a session flagged 'action'.
Signal known at S's close (the bar's known_at); side = sign of the abnormal move; entry = next session's open (kit)."""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
EXPLORE = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, EXPLORE)
sys.path.insert(0, os.path.join(EXPLORE, "scout"))
from kit import data

UNIV = os.path.join(EXPLORE, "kit", "universe_us.csv")
BS = {}


def sector_map():
    u = pd.read_csv(UNIV)
    return dict(zip(u.key, u.sector))


def keys():
    return list(pd.read_csv(UNIV).key)


def load_events():
    from events_edgar import idea_sessions
    s = idea_sessions("059")
    acc = pd.DatetimeIndex(s.accepted_et).tz_convert("UTC").tz_localize(None)
    sess = pd.to_datetime(s.session.astype(str)).dt.strftime("%Y-%m-%d").to_numpy()
    return data.event_table(acc, known=lambda o: pd.DatetimeIndex(o).tz_localize("UTC"), min_lag=pd.Timedelta(0),
                            name="results_8k", share=s.key.to_numpy(), session=sess)
    # the label column is named "share", not "market": checks._check_row_len treats any item with a "market" column of
    # class shares as daily session bars and refuses row_len 0, although this table is indexed by acceptance times


def load_data():
    global BS
    BS = {k: data.load_bars(k) for k in keys()}
    return {"bars": data.long_bars(BS), "events": load_events()}


def moves(d):
    """Abnormal move of every share-session: ret_total minus the median ret_total of the universe that session."""
    b = d["bars"]
    mv = data.session_moves(b)
    t = pd.DatetimeIndex(b.index)
    rt = mv["ret_total"].to_numpy(float)
    med = pd.Series(rt).groupby(t.asi8).transform("median").to_numpy()   # NaN (a share's first bar) skipped
    return pd.DataFrame({"market": b["market"].astype(str).to_numpy(),
                         "date": t.tz_convert("UTC").floor("D").tz_localize(None),   # 09:30 NY open: same date in UTC
                         "known_at": pd.DatetimeIndex(b["known_at"]), "abn": rt - med,
                         "action": mv["action"].to_numpy(bool)})


def build(d, threshold=0.08):
    m = moves(d)
    ev = d["events"]
    e = pd.DataFrame({"market": ev["share"].astype(str).to_numpy(),
                      "date": pd.to_datetime(ev["session"].astype(str).to_numpy())}).drop_duplicates()
    j = e.merge(m, on=["market", "date"], how="inner")
    j = j[np.isfinite(j.abn) & ~j.action & (j.abn.abs() >= threshold)]
    out = pd.DataFrame({"known_at": pd.DatetimeIndex(j.known_at), "side": np.sign(j.abn).astype(int).to_numpy(),
                        "market": j.market.to_numpy()})
    return out.sort_values(["known_at", "market"], kind="mergesort").reset_index(drop=True)
