"""COT helpers of idea 016 (and, copied unchanged, of idea 022): the weekly net speculative position of 12 contracts,
indexed by the time this rule may first use it (the entry time), through kit.data.external.

Timing (scout/sources.md 5): positions of the report date (normally a Tuesday), released Friday 15:30 New York of the
same week; the release slips (usually to the next Monday) when a US federal holiday falls in that week. Rule used:
known_at = Monday 08:00 UTC after the report week's Friday; Tuesday 08:00 UTC when any US federal holiday (pandas
USFederalHolidayCalendar), Good Friday, or the federal closure of 2018-12-05 falls on Monday..Friday of the report
week (a superset of the scout's 'between the report Tuesday and Friday'). Report dates 2013-10-01..2013-11-12 and
2018-12-18..2019-03-05 (shutdown backlogs) are dropped."""
import json, os
import numpy as np, pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar, GoodFriday
from kit import data as D

CACHE = os.path.expanduser("~/explore_data/idea_016/cot_legacy.json")
CODES = {"eurusd": "099741", "usdjpy": "097741", "gbpusd": "096742", "audusd": "232741", "usdcad": "090741",
         "usdchf": "092741", "nzdusd": "112741", "xauusd": "088691", "xagusd": "084691", "us500": "13874A",
         "us100": "209742", "us30": "124603"}
FLIP = {"usdjpy": -1, "usdcad": -1, "usdchf": -1}       # futures quoted as foreign currency in USD: the CFD is the inverse
DROP = [("2013-10-01", "2013-11-12"), ("2018-12-18", "2019-03-05")]
MIN_LAG = pd.Timedelta(days=6)
START = pd.Timestamp("2013-02-01", tz="UTC")             # first signal (bars start 2013-01; D20 needs 20 days)


def closed_days():
    h = USFederalHolidayCalendar().holidays("2008-01-01", "2021-12-31")
    gf = pd.DatetimeIndex([GoodFriday.dates(f"{y}-01-01", f"{y}-12-31")[0] for y in range(2008, 2022)])
    return set(pd.DatetimeIndex(list(h) + list(gf) + [pd.Timestamp("2018-12-05")]).normalize())


def known_rule(obs):
    obs = pd.DatetimeIndex(obs).normalize()
    fri = obs + pd.to_timedelta(4 - obs.dayofweek, unit="D")
    cd = closed_days()
    hol = np.array([any((f - pd.Timedelta(days=k)) in cd for k in range(5)) for f in fri])
    k = fri + pd.to_timedelta(np.where(hol, 4, 3), unit="D") + pd.Timedelta(hours=8)
    return k.tz_localize("UTC")


def load_cot():
    """One frame indexed by known_at (UTC): columns market, net, obs. Cut at 2021-12-31 in the read."""
    rows = pd.DataFrame(json.load(open(CACHE)))
    rows["date"] = pd.to_datetime(rows.report_date_as_yyyy_mm_dd).dt.tz_localize(None).dt.normalize()
    rows = rows[rows.date <= pd.Timestamp("2021-12-31")]
    for a, b in DROP:
        rows = rows[~rows.date.between(pd.Timestamp(a), pd.Timestamp(b))]
    inv = {v: k for k, v in CODES.items()}
    out = []
    for code, g in rows.groupby("cftc_contract_market_code"):
        g = g.sort_values("date")
        L, S, OI = (pd.to_numeric(g[c]).to_numpy(float) for c in
                    ("noncomm_positions_long_all", "noncomm_positions_short_all", "open_interest_all"))
        s = D.external(g.date, (L - S) / OI, known=known_rule, min_lag=MIN_LAG, name=inv[code])
        out.append(pd.DataFrame({"market": inv[code], "net": s.to_numpy(), "obs": s.attrs["obs_date"]}, index=s.index))
    f = pd.concat(out).sort_index(kind="stable")
    f.index.name = "known_at"
    return f


def weekly_features(f, win):
    """Per market, from past rows only: d = net - previous report's net (previous report 4..10 days earlier),
    z = (d - mean of the previous `win` valid d) / their std (ddof 1), p = rank of net among the previous `win` nets
    (share strictly below + half the ties)."""
    res = []
    for mk, g in f.groupby("market", sort=True):
        g = g.copy()
        obs = pd.DatetimeIndex(g.obs)
        gap = obs.to_series().diff().dt.days.to_numpy()
        d = g.net.diff().to_numpy().copy()
        d[~((gap >= 4) & (gap <= 10))] = np.nan
        g["d"] = d
        dv = pd.Series(d, index=g.index).dropna()
        m = dv.rolling(win).mean().shift(1)
        sd = dv.rolling(win).std(ddof=1).shift(1)
        g["z"] = ((dv - m) / sd).reindex(g.index)
        net = g.net.to_numpy()
        p = np.full(len(g), np.nan)
        for i in range(win, len(g)):
            w = net[i - win:i]
            p[i] = ((w < net[i]).sum() + 0.5 * (w == net[i]).sum()) / win
        g["p"] = p
        res.append(g)
    return pd.concat(res).sort_index(kind="stable")
