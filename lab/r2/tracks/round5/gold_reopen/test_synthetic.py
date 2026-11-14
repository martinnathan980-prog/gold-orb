"""Checks the order builder and the r2 code paths on a SYNTHETIC gold-like frame (no market data is read).

The frame (2019-05-01 .. 2019-07-31, made-up prices) has bars every minute except the gold closures (daily 17:00-17:59
New York, Friday 17:00 to Sunday 18:00, the 13:00-18:00 early close of Thursday 2019-07-04) and three planted holes:
  - Wednesday 2019-06-19: no bar 18:00-18:14 New York           -> skipped, no quote (D4)
  - Tuesday 2019-06-25: no bar 18:15 New York                   -> entry at 18:16, delay 1 minute (D5)
  - Wednesday 2019-06-26: no bar 20:00-20:59 New York           -> exit moved to the last bar before the hole (D8)
Expected: Wednesday 2019-07-03 skipped (next day is an early close), Thursday 2019-07-04 skipped (its own early
close), May evenings skipped until 480 completed H1 bars exist, the stop distance equal to 2 x the mean H1 range of an
independent hourly groupby, fills as sim.py says, every-signal run equal to the plain run, and r2.null_test running
(mode 'time', 5 replays) on the installed frame.

    python3 test_synthetic.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from goldlab import r2  # noqa: E402
from goldlab.split import cut  # noqa: E402

NY = C.NY


def synthetic_frame():
    utc = pd.date_range("2019-05-01 00:00", "2019-07-31 23:59", freq="min", tz="UTC").as_unit("ns")
    ny = utc.tz_convert(NY)
    hm = ny.hour * 60 + ny.minute
    wd = ny.dayofweek
    keep = ~((hm >= 17 * 60) & (hm < 18 * 60))                      # daily closure
    keep &= ~((wd == 4) & (hm >= 17 * 60)) & ~(wd == 5) & ~((wd == 6) & (hm < 18 * 60))   # weekend
    d = ny.tz_localize(None).normalize()

    def hole(day, h0, m0, h1, m1):
        return ~((d == pd.Timestamp(day)) & (hm >= h0 * 60 + m0) & (hm < h1 * 60 + m1))
    keep &= hole("2019-07-04", 13, 0, 18, 0)                         # Independence Day: early close 13:00
    keep &= hole("2019-06-19", 18, 0, 18, 15)
    keep &= hole("2019-06-25", 18, 15, 18, 16)
    keep &= hole("2019-06-26", 20, 0, 21, 0)
    idx = utc[keep]
    i = np.arange(len(idx), dtype=float)
    mid = 1300 + 5 * np.sin(i / 700.0) + 0.002 * i / 60
    half_sp = 0.10 + 0.05 * (np.sin(i / 37.0) > 0)
    amp = 0.20 + 0.15 * np.abs(np.sin(i / 53.0))
    f = pd.DataFrame(index=idx)
    f["bo"] = mid - half_sp
    f["bh"] = mid - half_sp + amp
    f["bl"] = mid - half_sp - amp
    f["bc"] = mid - half_sp + 0.3 * amp * np.sin(i)
    f["ao"] = f["bo"] + 2 * half_sp
    f["ah"] = f["bh"] + 2 * half_sp
    f["al"] = f["bl"] + 2 * half_sp
    f["ac"] = f["bc"] + 2 * half_sp
    f.index.name = "ts"
    return f[C.COLS]


def main():
    m1 = synthetic_frame()
    C.assert_is(m1)
    ev = C.evening_table(m1, "18:15", 120, 480)
    st = dict(zip(ev.evening.dt.strftime("%Y-%m-%d"), ev.status))
    row = lambda day: ev[ev.evening == pd.Timestamp(day)].iloc[0]  # noqa: E731
    checks = {}
    checks["no Sunday / Friday evening"] = bool(ev.weekday.max() <= 3)
    checks["2019-06-19 no quote"] = st["2019-06-19"] == "no_quote_1800_entry"
    checks["2019-07-03 next day early close"] = st["2019-07-03"] == "cal_holiday_next_day"
    checks["2019-07-04 own early close"] = st["2019-07-04"] == "cal_holiday_evening"
    checks["2019-04-30 (frame starts 20:00 New York) no quote"] = st["2019-04-30"] == "no_quote_1800_entry"
    checks["May warm-up skipped"] = all(v == "h1_lt_480" for k, v in st.items() if "2019-05-01" <= k < "2019-05-20")
    r = row("2019-06-25")
    checks["2019-06-25 entry 18:16 (delay 1)"] = (r.status == "ok" and r.entry_delay_min == 1.0
                                                 and r.entry_bar.tz_convert(NY).strftime("%H:%M") == "18:16")
    r = row("2019-06-26")
    checks["2019-06-26 exit before the hole"] = (r.status == "ok"
                                                and r.exit_bar.tz_convert(NY).strftime("%H:%M") == "19:59"
                                                and r.exit_shift_min == -16.0)
    r = row("2019-06-20")
    checks["2019-06-20 entry 18:15, exit 20:15"] = (r.entry_bar.tz_convert(NY).strftime("%H:%M") == "18:15"
                                                   and r.exit_bar.tz_convert(NY).strftime("%H:%M") == "20:15")
    # independent hourly range: groupby on the UTC hour floor
    hh = m1.index.floor("h")
    g = pd.DataFrame({"h": (m1.bh.to_numpy() + 0), "ah": m1.ah.to_numpy(), "l": m1.bl.to_numpy(), "al": m1.al.to_numpy()},
                     index=hh).groupby(level=0)
    rng = ((g.h.max() + g.ah.max()) / 2 - (g.l.min() + g.al.min()) / 2)
    ok = ev[ev.status == "ok"]
    worst = 0.0
    for _, r in ok.iterrows():
        done = rng[rng.index + pd.Timedelta(hours=1) <= r.entry_bar]
        exp = float(done.iloc[-480:].mean())
        worst = max(worst, abs(exp - r.h1_mean_range))
    checks["H1 mean range = independent groupby (max abs diff < 1e-9 USD)"] = worst < 1e-9
    checks["no 18:00 H1 bar in the window"] = bool((ok.h1_last.dt.tz_convert(NY).dt.hour == 16).all())
    # r2 paths on the installed synthetic frame
    C.install(m1)
    p = {"name": "main", "entry": "18:15", "hold_min": 120, "stop_k": 2.0, "n_h1": 480}
    t = r2.run(C.SYM, C.make_orders, p, "fp")
    o = C.make_orders(m1, **p)
    checks["one trade per ok evening"] = len(t) == len(ok) == len(o)
    ei = o.entry_i.to_numpy()
    xi = o.exit_i.to_numpy()
    e_exp = m1.ao.to_numpy()[ei] * (1 + 0.3e-4)
    checks["entry = ask open x (1 + 0.3 bp)"] = bool(np.allclose(t.entry.to_numpy(), e_exp, rtol=0, atol=1e-9))
    tm = t.reason.to_numpy() == "time"
    x_exp = m1.bo.to_numpy()[xi] * (1 - 0.3e-4)
    checks["time exit = bid open of exit bar x (1 - 0.3 bp)"] = bool(np.allclose(t.exit.to_numpy()[tm], x_exp[tm], rtol=0, atol=1e-9))
    checks["stop = entry - 2 x range"] = bool(np.allclose(t.stop.to_numpy(), e_exp - 2 * o.h1_mean_range.to_numpy(), rtol=0, atol=1e-9))
    checks["R = pnl / stop distance"] = bool(np.allclose(t.R.to_numpy(), t.pnl.to_numpy() / (2 * o.h1_mean_range.to_numpy()), atol=1e-12))
    checks["no swap"] = float(t.swap.abs().sum()) == 0.0
    te = r2.run(C.SYM, C.make_orders, p, "fp", no_overlap=False)
    checks["every signal = plain"] = len(te) == len(t) and bool(np.allclose(te.R.to_numpy(), t.R.to_numpy(), atol=0))
    ts = r2.run(C.SYM, C.make_orders, p, "stress")
    checks["stress: same entries, worse entry fills"] = (len(ts) == len(t) and bool((ts.entry.to_numpy() > t.entry.to_numpy()).all()))
    ev2 = r2.evaluate(C.SYM, C.make_orders, p)
    checks["r2.evaluate runs, n = cut trades"] = ev2["is"]["n"] == len(cut(t, "is"))
    nul = r2.null_test(C.SYM, C.make_orders, p, n_seeds=5, mode="time", seed=0)
    checks["r2.null_test mode time runs"] = nul.get("mode") == "time" and nul.get("n") == len(cut(t, "is"))
    C.check_held()
    try:
        r2.load("us100")
        checks["guard refuses an uncached symbol"] = False
    except RuntimeError:
        checks["guard refuses an uncached symbol"] = True
    for k, v in checks.items():
        print(("PASS " if v else "FAIL ") + k)
    print("evenings", len(ev), "statuses", ev.status.value_counts().to_dict())
    assert all(checks.values()), "synthetic checks failed"
    print("all synthetic checks pass")


if __name__ == "__main__":
    main()
