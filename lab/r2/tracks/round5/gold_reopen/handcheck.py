"""Hand check of the main configuration on individual trades (in sample only). Every number is recomputed from the raw
in-sample M1 quotes with plain code that uses neither common.py's calendar, session or H1 code nor the lab simulator:
- the calendar from the `holidays` package's NYSE calendar (an independent source) plus the two gold early-close days
  (Christmas Eve, the day after Thanksgiving); the special closure 2018-12-05 is a normal gold day;
- 18:15 New York -> UTC with Python's zoneinfo; the quote test as a plain count of bars in [18:00, 18:15) New York;
- the entry bar (first bar at or after 18:15 New York) and its price (ask open + 0.3 bp);
- the 480-bar range: M1 bars grouped by UTC clock hour (integer division of the timestamp), mid high = (max bid high +
  max ask high) / 2, mid low likewise, hours ended at or before the entry bar start, the last 480, plain mean;
- stop = entry - 2 x range; a plain bar-by-bar scan of the bid lows; the exit bar (first bar at or after entry + 120
  minutes, or the last bar before a gap of more than 30 minutes) and its price (bid open - 0.3 bp, or the stop / gapped
  open - 1.0 bp); R = (exit - entry) / (entry - stop).
Trades checked (rule fixed before the run): the first stop-out (if any), two New York winter-time and two summer-time
time-exit trades drawn with numpy default_rng(7); extras: the first trade, the first entry delayed over 5 minutes and the
first trade whose exit bar starts after its scheduled time.
Output: results/r2/round5/gold_reopen/handcheck.json
"""
import datetime as dt
import os
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402  (used only for the in-sample read and the output folder)

import holidays  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

NYZ = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
NS = 10**9
NYSE = holidays.financial_holidays("NYSE", years=range(2012, 2023))


def abnormal_gold_day(d):
    """A US holiday closure or early close of gold, from an independent calendar."""
    if d in NYSE and d != dt.date(2018, 12, 5):
        return True
    if d.month == 12 and d.day == 24 and d.weekday() < 4:
        return True
    thanks = [x for x, n in NYSE.items() if x.year == d.year and "Thanksgiving" in n]
    return bool(thanks) and d == thanks[0] + dt.timedelta(days=1)


def ns(d, hh, mm):
    return int(dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=NYZ).astimezone(UTC).timestamp()) * NS


def show(t_ns):
    u = dt.datetime.fromtimestamp(t_ns / NS, UTC)
    return {"utc": u.strftime("%Y-%m-%d %H:%M"), "new_york": u.astimezone(NYZ).strftime("%Y-%m-%d %H:%M %Z")}


def recompute(m1, ts, evening, hold=120, k=2.0, n=480):
    E = evening.date()
    d1 = E + dt.timedelta(days=1)
    target = ns(E, 18, 15)
    q = int(((ts >= ns(E, 18, 0)) & (ts < target)).sum())
    ei = int(np.searchsorted(ts, target))
    tau = int(ts[ei])
    entry = float(m1.ao.iloc[ei]) * (1 + 0.3e-4)
    lo = int(np.searchsorted(ts, tau - 60 * 86400 * NS))
    seg = m1.iloc[lo:ei]
    hour = (ts[lo:ei] // (3600 * NS)).astype(np.int64)
    g = pd.DataFrame({"hr": hour, "bh": seg.bh.to_numpy(), "ah": seg.ah.to_numpy(), "bl": seg.bl.to_numpy(),
                      "al": seg.al.to_numpy()}).groupby("hr")
    rng = ((g.bh.max() + g.ah.max()) / 2 - (g.bl.min() + g.al.min()) / 2)
    rng = rng[(rng.index.to_numpy() + 1) * 3600 * NS <= tau]
    assert len(rng) >= n
    win = rng.iloc[-n:]
    mean_rng = float(win.mean())
    stop = entry - k * mean_rng
    sched = tau + hold * 60 * NS
    xi = int(np.searchsorted(ts, sched))
    if xi >= len(ts) or ts[xi] - sched > 30 * 60 * NS:
        xi -= 1
    bl, bo = m1.bl.to_numpy(), m1.bo.to_numpy()
    reason, x_px, x_t = "time", float(bo[xi]) * (1 - 0.3e-4), int(ts[xi])
    for i in range(ei, xi):
        if bl[i] <= stop:
            px = stop if i == ei else min(stop, float(bo[i]))
            reason, x_px, x_t = "stop", px * (1 - 1.0e-4), int(ts[i]) + 60 * NS
            break
    R = (x_px - entry) / (entry - stop)
    return {"evening": str(E), "weekday": E.strftime("%A"), "calendar_ok": not (abnormal_gold_day(E) or abnormal_gold_day(d1)),
            "quotes_18_00_18_15": q, "entry_bar": show(tau), "entry_price_usd": entry,
            "entry_ask_open_usd": float(m1.ao.iloc[ei]), "entry_bid_open_usd": float(m1.bo.iloc[ei]),
            "h1_window_first": show(int(win.index[0]) * 3600 * NS), "h1_window_last": show(int(win.index[-1]) * 3600 * NS),
            "h1_mean_range_usd": mean_rng, "stop_usd": stop, "stop_distance_bp": (entry - stop) / entry * 1e4,
            "exit_reason": reason, "exit_bar": show(x_t if reason == "time" else x_t - 60 * NS), "exit_time": show(x_t),
            "exit_price_usd": x_px, "R": R, "net_bp": (x_px - entry) / entry * 1e4}


def main():
    decl, sha = C.declared()
    m1 = C.load_is()
    ts = m1.index.as_unit("ns").asi8
    t = pd.read_parquet(os.path.join(C.OUT, "trades_01_main.parquet")).reset_index(drop=True)
    rng = np.random.default_rng(7)
    picks = []
    stops = np.flatnonzero(t.reason.to_numpy() == "stop")
    if len(stops):
        picks.append(("first stop-out", int(stops[0])))
    timex = t.reason.to_numpy() == "time"
    for summer, lab in ((False, "New York winter time (EST)"), (True, "New York summer time (EDT)")):
        pool = np.flatnonzero(timex & (t.ny_summer_time.to_numpy() == summer))
        for j in rng.choice(pool, 2, replace=False):
            picks.append((lab, int(j)))
    if not len(stops):
        picks.append(("no stop-out in the sample: one more random trade", int(rng.choice(len(t)))))
    extras = [("extra: first trade", 0)]
    late = np.flatnonzero(t.entry_delay_min.to_numpy() > 5)
    if len(late):
        extras.append(("extra: first entry delayed over 5 minutes", int(late[0])))
    lx = np.flatnonzero(t.exit_shift_min.to_numpy() > 0.5)
    if len(lx):
        extras.append(("extra: first exit bar after its scheduled time", int(lx[0])))
    rows, worst = [], 0.0
    for why, j in picks + extras:
        r = t.iloc[j]
        h = recompute(m1, ts, pd.Timestamp(r.evening))
        eng = {"entry_time": str(r.entry_time), "entry": float(r.entry), "h1_mean_range": float(r.h1_mean_range),
               "stop": float(r.stop), "reason": r.reason, "exit_time": str(r.exit_time), "exit": float(r.exit), "R": float(r.R)}
        u = lambda x: dt.datetime.strptime(x["utc"], "%Y-%m-%d %H:%M").replace(tzinfo=UTC)  # noqa: E731
        ok = (h["calendar_ok"] and h["quotes_18_00_18_15"] > 0
              and pd.Timestamp(r.entry_time) == pd.Timestamp(u(h["entry_bar"]))
              and abs(eng["entry"] - h["entry_price_usd"]) < 1e-9 and abs(eng["h1_mean_range"] - h["h1_mean_range_usd"]) < 1e-9
              and abs(eng["stop"] - h["stop_usd"]) < 1e-9 and eng["reason"] == h["exit_reason"]
              and pd.Timestamp(r.exit_time) == pd.Timestamp(u(h["exit_time"]))
              and abs(eng["exit"] - h["exit_price_usd"]) < 1e-9 and abs(eng["R"] - h["R"]) < 1e-9)
        worst = max(worst, abs(eng["R"] - h["R"]))
        rows.append({"why": why, "trade_index": j, "hand": h, "engine": eng, "match": bool(ok)})
    core = rows[:len(picks)]
    out = {"declared_sha256": sha, "what": "independent recomputation of main trades from the raw in-sample M1 quotes",
           "n_checked": len(rows), "n_core": len(core), "core_regimes": sorted({r["why"] for r in core}),
           "any_stop_out_in_sample": bool(len(stops)), "all_match": all(r["match"] for r in rows), "max_abs_R_diff": worst,
           "rows": rows}
    C.jdump(out, os.path.join(C.OUT, "handcheck.json"))
    print(out["n_checked"], "checked; all match:", out["all_match"], "max |dR|:", worst)
    for r in rows:
        h = r["hand"]
        print(f"{r['why']}: evening {h['evening']} entry {h['entry_bar']['utc']} UTC = {h['entry_bar']['new_york']}, "
              f"entry {h['entry_price_usd']:.3f} (ask open {h['entry_ask_open_usd']:.3f}), range {h['h1_mean_range_usd']:.4f} USD "
              f"(H1 {h['h1_window_first']['new_york']} .. {h['h1_window_last']['new_york']}), stop {h['stop_usd']:.3f}, "
              f"exit {h['exit_reason']} at {h['exit_time']['new_york']} {h['exit_price_usd']:.3f}, R {h['R']:.4f}, match {r['match']}")


if __name__ == "__main__":
    main()
