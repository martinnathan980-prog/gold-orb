"""Attack precheck (timestamps and calendar only, no price is used): in sample only.

1. My gold holiday calendar (acommon.gold_calendar, built from the US holiday rules) against the frame's own close
   time of every weekday (last M1 bar before 17:00 New York) and its reopen (first bar at or after 18:00 New York).
2. Candidate evenings and skips by reason and year, for the three readings of 'skip US holiday closures and early
   closes' (evening / session / union).
3. Evenings next to the US daylight-saving switches: the UTC time of 18:15 New York (22:15 in summer time, 23:15 in
   winter time) and the FP server time (New York + 7 h).
Output: results/r2/round5/gold_reopen/attack/aprecheck.json
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import acommon as A  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


def main():
    df = A.load_is()
    fr = A.Frame(df)
    h1 = A.H1(fr)
    cal = A.gold_calendar()
    out = {"frame": {"rows": int(fr.N), "first_bar_utc": str(df.index[0]), "last_bar_utc": str(df.index[-1])}}
    # 1. calendar against the frame's close / reopen times
    ny = df.index.tz_convert(A.NY).tz_localize(None)
    d = pd.DataFrame({"date": ny.normalize(), "m": ny.hour * 60 + ny.minute})
    close = d[d.m < 17 * 60].groupby("date").m.max()
    reopen = d[d.m >= 18 * 60].groupby("date").m.min()
    fmt = lambda v: None if pd.isna(v) else f"{int(v) // 60:02d}:{int(v) % 60:02d}"
    rows = []
    for day in pd.bdate_range("2013-01-01", "2021-12-31"):
        dd = day.date()
        c = close.get(day, np.nan)
        kind = cal.get(dd, (None, None))
        early_in_data = (not pd.isna(c)) and c < 16 * 60 + 30
        closed_in_data = pd.isna(c)
        if kind[0] is not None or early_in_data or closed_in_data:
            rows.append({"date": str(dd), "weekday": day.strftime("%a"), "calendar": kind[0], "holiday": kind[1],
                         "frame_close_ny": fmt(c), "frame_reopen_ny": fmt(reopen.get(day, np.nan)),
                         "agree": (kind[0] == "closure" and closed_in_data) or (kind[0] == "early" and early_in_data)
                         or (kind[0] is None and not early_in_data and not closed_in_data)})
    out["calendar_vs_frame"] = {"days_listed": len(rows), "disagreements": [r for r in rows if not r["agree"]],
                                "all": rows}
    # 2. skips by reason and year for each reading (main configuration timing)
    cfg = A.CONFIGS[0]
    for reading in ("union", "session", "evening"):
        S = A.sessions(fr, h1, cfg, cal, reading)
        S["year"] = [e.year for e in S.evening]
        tab = S.groupby(["year", "status"]).size().unstack(fill_value=0)
        out[f"sessions_{reading}"] = {"candidates": int(len(S)), "by_status": {k: int(v) for k, v in S.status.value_counts().items()},
                                      "by_year": {int(y): {k: int(v) for k, v in r.items()} for y, r in tab.iterrows()},
                                      "holiday_evenings": [str(e) for e in S.evening[S.status == "holiday"]]}
    # union-only list of the quote-test failures (data holes and odd reopens)
    S = A.sessions(fr, h1, cfg, cal, "union")
    out["no_quote_evenings"] = [str(e) for e in S.evening[S.status == "no_quote_1800_1815"]]
    out["no_entry_bar_evenings"] = [str(e) for e in S.evening[S.status == "no_entry_bar"]]
    out["fewer_than_480_h1_evenings"] = [str(e) for e in S.evening[S.status == "fewer_than_480_h1"]]
    # 18:10 neighbour: quote window [18:00, 18:10) versus [18:00, 18:15)
    c2 = A.CONFIGS[1]
    S10a = A.sessions(fr, h1, c2, cal, "union")                 # window ends at the entry, 18:10
    S10b = A.sessions(fr, h1, c2, cal, "union", quote_end="18:15")
    diff = S10a.status != S10b.status
    out["n_entry_1810_quote_window_difference"] = [{"evening": str(e), "window_1810": a, "window_1815": b}
                                                   for e, a, b in zip(S10a.evening[diff], S10a.status[diff], S10b.status[diff])]
    # 3. DST switch evenings
    dst = []
    for y in range(2013, 2022):
        spring = A.nth_weekday(y, 3, 6, 2)             # second Sunday of March
        autumn = A.nth_weekday(y, 11, 6, 1)            # first Sunday of November
        for sw, nm in ((spring, "spring"), (autumn, "autumn")):
            for e in (sw - dt.timedelta(days=4), sw - dt.timedelta(days=3), sw + dt.timedelta(days=1), sw + dt.timedelta(days=2)):
                te = pd.Timestamp(A.ny_utc_ns(e, "18:15"), tz="UTC")
                srv = te.tz_convert(A.NY).tz_localize(None) + pd.Timedelta(hours=7)
                st = S.loc[S.evening == e, "status"]
                dst.append({"switch": nm, "evening": str(e), "weekday": e.strftime("%a"), "entry_1815_ny_in_utc": str(te),
                            "fp_server_time": str(srv), "status": st.iloc[0] if len(st) else "not a candidate"})
    out["dst_evenings"] = dst
    # H1 bars: count, and bars per hour
    out["h1"] = {"bars": int(len(h1.start_ns)), "m1_rows_per_h1_median": float(np.median(h1.n_m1)),
                 "h1_with_fewer_than_30_m1": int((h1.n_m1 < 30).sum())}
    A.jdump(out, os.path.join(A.OUT, "aprecheck.json"))
    print({k: out[f"sessions_{k}"]["by_status"] for k in ("union", "session", "evening")})
    print("calendar disagreements with the frame:")
    for r in out["calendar_vs_frame"]["disagreements"]:
        print("  ", r)
    print("no quote:", out["no_quote_evenings"])
    print("no entry bar:", out["no_entry_bar_evenings"])
    print("fewer than 480:", out["fewer_than_480_h1_evenings"])
    print("18:10 window difference:", out["n_entry_1810_quote_window_difference"])
    print("holiday per year (union):", {y: r.get("holiday", 0) for y, r in out["sessions_union"]["by_year"].items()})
    for r in dst[:8]:
        print("  ", r)


if __name__ == "__main__":
    main()
