"""Structure check BEFORE any simulation (in sample only): timestamps, the calendar and the H1 ranges. No return is
computed and no order is simulated.

- the in-sample slice: first / last bar, rows, max(ts) < 2022-01-01 asserted;
- candidate evenings (Monday-Thursday New York) and sessions per year; skipped evenings by reason (first failed test,
  and each test on its own); the calendar-skipped evenings listed with their holiday kind;
- the minute of the first bar after the 17:00-17:59 New York closure on every candidate evening (the reopen minute);
- entry bars printed in UTC and New York in both daylight-saving regimes and around the switches;
- the 480-bar H1 range at a few dates (USD per ounce and bp of the entry bar's mid open), with its window;
- entry delays, exits moved before a gap, and the evenings where the 18:10 neighbour's quote window [18:00, 18:10)
  and the main's [18:00, 18:15) disagree;
- expected n per configuration.
Output: results/r2/round5/gold_reopen/precheck.json
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

NY = C.NY
IS0 = pd.Timestamp("2013-01-01", tz="UTC")


def fmt(ts):
    return {"utc": ts.strftime("%Y-%m-%d %H:%M"), "new_york": ts.tz_convert(NY).strftime("%Y-%m-%d %H:%M %Z")}


def main():
    decl, sha = C.declared()
    m1 = C.load_is()
    C.assert_is(m1)
    h1 = C.h1_bars(m1)
    hs = pd.to_datetime(h1[0], unit="ns", utc=True)
    out = {"declared_sha256": sha,
           "frame": {"file": "lab/data/fp/xauusd_m1.parquet (read with the filter ts < 2022-01-01 00:00 UTC)",
                     "first_bar": fmt(m1.index[0]), "last_bar": fmt(m1.index[-1]), "rows": int(len(m1)),
                     "max_ts_before_2022": bool(m1.index.max() < C.CUT),
                     "h1_bars": int(len(hs)),
                     "h1_bars_starting_17h_new_york": [str(x.tz_convert(NY)) for x in hs[hs.tz_convert(NY).hour == 17]],
                     "m1_bars_17h_new_york": int((m1.index.tz_convert(NY).hour == 17).sum())}}
    tabs = {}
    for name, entry, hold in (("main", "18:15", 120), ("e1810", "18:10", 120), ("e1830", "18:30", 120),
                              ("h96", "18:15", 96), ("h144", "18:15", 144)):
        tabs[name] = C.evening_table(m1, entry, hold, 480, h1=h1)
    ev = tabs["main"]
    ev["year"] = ev.evening.dt.year
    is_ev = ev[ev.evening >= pd.Timestamp("2013-01-01")]
    out["candidate_evenings"] = {"first": str(ev.evening.iloc[0].date()), "last": str(ev.evening.iloc[-1].date()),
                                 "n": int(len(ev)), "n_from_2013": int(len(is_ev))}
    per_year = {}
    for y, g in ev.groupby("year"):
        per_year[int(y)] = {"candidates": int(len(g)), "sessions_main": int((g.status == "ok").sum()),
                            "skipped_first_reason": {k: int(v) for k, v in g[g.status != "ok"].status.value_counts().items()}}
    out["per_year"] = per_year
    out["skipped_by_first_reason_all_years"] = {k: int(v) for k, v in ev[ev.status != "ok"].status.value_counts().items()}
    out["each_test_on_its_own_all_years"] = {k: int(ev["fail_" + k].sum()) for k in C.STATUS_ORDER}
    cal = ev[(ev.kind_evening != C.NONE) | (ev.kind_next_day != C.NONE)]
    out["calendar_skipped_evenings"] = [
        {"evening": str(r.evening.date()), "weekday": r.evening.strftime("%A"),
         "evening_day_kind": C.KIND_NAME[int(r.kind_evening)], "next_day": str((r.evening + pd.Timedelta(days=1)).date()),
         "next_day_kind": C.KIND_NAME[int(r.kind_next_day)], "quotes_18_00_18_15": int(r.n_quotes_window)}
        for r in cal.itertuples()]
    out["calendar_skips_per_year"] = {int(y): int(v) for y, v in cal.groupby(cal.evening.dt.year).size().items()}
    nq = ev[(ev.status == "no_quote_1800_entry")]
    out["no_quote_evenings"] = [{"evening": str(r.evening.date()), "weekday": r.evening.strftime("%A")} for r in nq.itertuples()]
    # reopen minute: first bar at or after 17:00 New York of each candidate evening that passes the calendar
    ins = m1.index.as_unit("ns").asi8
    pc = ev[(ev.kind_evening == C.NONE) & (ev.kind_next_day == C.NONE)]
    t17 = C.ny_utc_ns(pc.evening, "17:00")
    j = np.minimum(np.searchsorted(ins, t17), len(ins) - 1)
    first_after = pd.to_datetime(ins[j], unit="ns", utc=True).tz_convert(NY)
    mins = (first_after - pd.DatetimeIndex(pc.evening).tz_localize(NY)).total_seconds() / 60
    lab = np.where(mins < 18 * 60, "before 18:00", np.where(mins == 18 * 60, "18:00", np.where(mins == 18 * 60 + 1, "18:01",
                   np.where(mins < 18 * 60 + 15, "18:02-18:14", np.where(mins < 24 * 60, "18:15 or later, same evening", "next day or later")))))
    out["reopen_minute_counts"] = {k: int(v) for k, v in pd.Series(lab).value_counts().items()}
    # entry bars in both regimes and around the switches
    picks = ["2013-02-05", "2013-07-09", "2015-01-13", "2015-07-14", "2019-03-07", "2019-03-11", "2019-10-31", "2019-11-04",
             "2020-01-14", "2020-07-14", "2021-12-30"]
    rows = []
    for d in picks:
        r = ev[ev.evening == pd.Timestamp(d)]
        if not len(r):
            continue
        r = r.iloc[0]
        rows.append({"evening": d, "weekday": r.evening.strftime("%A"), "status": r.status,
                     "target_18_15_new_york": fmt(r.t_target), "entry_bar": fmt(r.entry_bar) if r.has_entry_bar else None,
                     "scheduled_exit": fmt(r.t_exit_sched), "exit_bar": fmt(r.exit_bar)})
    out["entry_bar_examples"] = rows
    # the 480-bar range at a few dates
    ok = ev[ev.status == "ok"]
    mid_o = (m1.bo.to_numpy() + m1.ao.to_numpy()) / 2
    pick_r = [ok.index[0], ok.index[len(ok) // 4], ok.index[len(ok) // 2]]
    covid = ok[ok.evening >= pd.Timestamp("2020-03-16")]
    if len(covid):
        pick_r.append(covid.index[0])
    pick_r.append(ok.index[-1])
    rr = []
    for i in pick_r:
        r = ev.loc[i]
        px = float(mid_o[int(r.entry_i)])
        rr.append({"evening": str(r.evening.date()), "entry_bar": fmt(r.entry_bar), "n_h1_completed": int(r.n_h1_completed),
                   "window_first_h1": fmt(r.h1_first), "window_last_h1": fmt(r.h1_last),
                   "window_span_days": round((r.h1_last - r.h1_first).total_seconds() / 86400, 1),
                   "mean_h1_range_usd": round(float(r.h1_mean_range), 4), "entry_bar_mid_open_usd": round(px, 3),
                   "mean_h1_range_bp": round(float(r.h1_mean_range) / px * 1e4, 2),
                   "stop_distance_2x_bp": round(2 * float(r.h1_mean_range) / px * 1e4, 2)})
    out["h1_range_examples"] = rr
    okr = ok.h1_mean_range.to_numpy() / mid_o[ok.entry_i.to_numpy()] * 1e4
    out["h1_range_bp_over_sessions"] = {"min": round(float(okr.min()), 2), "median": round(float(np.median(okr)), 2),
                                        "max": round(float(okr.max()), 2)}
    out["h1_window_last_bar_new_york_hour"] = {int(k): int(v) for k, v in ok.h1_last.dt.tz_convert(NY).dt.hour.value_counts().items()}
    # delays and moved exits (main)
    out["entry_delays_main"] = {"over_0_min": int((ok.entry_delay_min > 0).sum()), "over_5_min": int((ok.entry_delay_min > 5).sum()),
                                "list": [{"evening": str(r.evening.date()), "entry_bar": fmt(r.entry_bar), "delay_min": float(r.entry_delay_min)}
                                         for r in ok[ok.entry_delay_min > 0].itertuples()]}
    for name in ("main", "h96", "h144"):
        t = tabs[name]
        o = t[t.status == "ok"]
        out[f"exits_moved_before_gap_{name}"] = [{"evening": str(r.evening.date()), "scheduled": fmt(r.t_exit_sched),
                                                  "exit_bar": fmt(r.exit_bar), "shift_min": float(r.exit_shift_min)}
                                                 for r in o[o.exit_shift_min < -0.5].itertuples()]
        out[f"exits_after_scheduled_time_{name}"] = int((o.exit_shift_min > 0.5).sum())
    a = tabs["main"].set_index("evening")
    b = tabs["e1810"].set_index("evening")
    diff = a.index[(a.fail_no_quote_1800_entry != b.fail_no_quote_1800_entry).to_numpy()]
    out["quote_window_1810_vs_1815_disagree"] = [str(d.date()) for d in diff]
    out["status_disagreements_vs_main"] = {
        k: [{"evening": str(d.date()), "main": a.status[d], k: tabs[k].set_index("evening").status[d]}
            for d in a.index[(a.status != tabs[k].set_index("evening").status).to_numpy()]] for k in ("e1810", "e1830", "h96", "h144")}
    # expected n per configuration (entries 2013-2021); stop neighbours share the main's sessions
    out["expected_n"] = {k: int(((t.status == "ok") & (t.entry_bar >= IS0)).sum()) for k, t in tabs.items()}
    out["expected_n"]["stop_1.6_and_2.4"] = out["expected_n"]["main"]
    out["max_entry_or_exit_bar_before_2022"] = bool(max(t[t.status == "ok"].exit_bar.max() for t in tabs.values()) < C.CUT)
    assert out["max_entry_or_exit_bar_before_2022"]
    C.jdump(out, os.path.join(C.OUT, "precheck.json"))
    print({k: out[k] for k in ("frame", "candidate_evenings", "skipped_by_first_reason_all_years", "each_test_on_its_own_all_years",
                               "calendar_skips_per_year", "reopen_minute_counts", "expected_n", "h1_range_bp_over_sessions",
                               "h1_window_last_bar_new_york_hour")})
    print("sessions per year", {y: v["sessions_main"] for y, v in per_year.items()})
    print("no-quote evenings", [r["evening"] for r in out["no_quote_evenings"]])
    print("delays", {k: v for k, v in out["entry_delays_main"].items() if k != "list"}, out["entry_delays_main"]["list"][:10])
    for name in ("main", "h96", "h144"):
        print("moved exits", name, out[f"exits_moved_before_gap_{name}"], "late exits", out[f"exits_after_scheduled_time_{name}"])
    print("quote window disagreements", out["quote_window_1810_vs_1815_disagree"])
    print("status disagreements", {k: v for k, v in out["status_disagreements_vs_main"].items()})
    for r in out["entry_bar_examples"]:
        print(r)
    for r in out["h1_range_examples"]:
        print(r)


if __name__ == "__main__":
    main()
