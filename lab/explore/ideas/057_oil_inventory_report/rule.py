"""Idea 057: the signal build (EIA weekly petroleum report calendar built from the rule + the release bar's move).
Imported by run.py only (attack.py must not import it)."""
import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

NY = "America/New_York"


def report_calendar(start="2013-01-01", end="2021-12-31"):
    """EIA Weekly Petroleum Status Report, built from the rule (no fetched schedule): Wednesday 10:30 New York; in a
    week with a US federal holiday (observed date) on Monday, Tuesday or Wednesday, Thursday 11:00 New York.
    Returns a DataFrame: date (NY calendar date of the release), rel_hour (NY hour of the bar that holds the release:
    10 on Wednesdays, 11 on Thursdays). Depends on the calendar only (no data)."""
    weds = pd.date_range(start, end, freq="W-WED")
    hol = USFederalHolidayCalendar().holidays(pd.Timestamp(start) - pd.Timedelta(days=7),
                                              pd.Timestamp(end) + pd.Timedelta(days=7))
    hol = set(pd.DatetimeIndex(hol).normalize())
    rows = []
    for w in weds:
        moved = any((w - pd.Timedelta(days=k)) in hol for k in (0, 1, 2))
        d = w + pd.Timedelta(days=1) if moved else w
        if d > pd.Timestamp(end):
            continue
        rows.append((d, 11 if moved else 10))
    return pd.DataFrame(rows, columns=["date", "rel_hour"])


CAL = report_calendar()


def hour_moves(bars):
    """Per bar: NY date, NY hour, move = close / open - 1 (a ratio: oil is back-adjusted), |move|."""
    ny = bars.index.tz_convert(NY)
    mv = bars["close"].to_numpy(float) / bars["open"].to_numpy(float) - 1.0
    return pd.DataFrame({"date": ny.tz_localize(None).normalize(), "hour": ny.hour, "move": mv,
                         "t_open": bars.index}, index=np.arange(len(bars)))


def build(d, thr_mult=1.0, window=60):
    """Whole signal table. For each report day of CAL: the bar labelled rel_hour:00 New York on that date (it holds
    the release); usual size = median |move| of the bars at the same NY hour over the previous `window` trading days
    that have that bar (the report day's own bar excluded; all days included, report days too); signal if
    |move| > thr_mult x usual size; side = sign(move); known_at = the bar's END (open + 1 h)."""
    bars = d["bars"]
    hm = hour_moves(bars)
    out = []
    for h in (10, 11):
        g = hm[hm.hour == h].drop_duplicates("date", keep="first").set_index("date")
        med = g["move"].abs().rolling(window, min_periods=window).median().shift(1)
        cal = CAL[CAL.rel_hour == h]
        x = g.reindex(cal["date"].to_numpy())
        m = med.reindex(cal["date"].to_numpy())
        ok = x["move"].notna().to_numpy() & m.notna().to_numpy()
        mv, mm = x["move"].to_numpy()[ok], m.to_numpy()[ok]
        sel = (np.abs(mv) > thr_mult * mm) & (mv != 0)
        t_open = pd.DatetimeIndex(x["t_open"].to_numpy()[ok][sel])
        t_open = t_open.tz_localize("UTC") if t_open.tz is None else t_open.tz_convert("UTC")
        out.append(pd.DataFrame({"known_at": t_open + pd.Timedelta(hours=1),
                                 "side": np.sign(mv[sel]).astype(int)}))
    s = pd.concat(out, ignore_index=True).sort_values("known_at").reset_index(drop=True)
    return s


def count_report_bars(d):
    """Power: report days whose release bar exists (no threshold), by year."""
    hm = hour_moves(d["bars"])
    n = 0
    for h in (10, 11):
        dates = set(hm.loc[hm.hour == h, "date"])
        n += sum(1 for x in CAL.loc[CAL.rel_hour == h, "date"] if x in dates)
    return n
