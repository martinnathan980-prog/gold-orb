"""Attack hand check, in sample only: a sample of my main trades recomputed from the raw in-sample M1 rows with plain
Python loops (zoneinfo for New York time, a dict of clock hours for the H1 bars, a bar-by-bar walk for the stop and
the exit), compared with my vectorized code (acommon); then the same orders put through goldlab.sim.simulate (the
lab's engine) to show that my fills and the lab's fills agree on every trade.
Output: results/r2/round5/gold_reopen/attack/ahand.json
"""
import bisect
import datetime as dt
import os
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import acommon as A  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

NYZ = ZoneInfo("America/New_York")
UTC = dt.timezone.utc


def plain_trade(ts, f, evening, hhmm="18:15", hold=120, k=2.0, slip_m=0.3e-4, slip_s=1.0e-4):
    h, m = (int(x) for x in hhmm.split(":"))
    te = dt.datetime(evening.year, evening.month, evening.day, h, m, tzinfo=NYZ).astimezone(UTC)
    te_s = int(te.timestamp())
    i = bisect.bisect_left(ts, te_s)                  # first bar starting at or after the entry time
    t0 = ts[i]
    # H1 bars completed at t0: clock hours (UTC) whose end <= t0, from the rows of the previous 60 days
    j0 = bisect.bisect_left(ts, t0 - 60 * 86400)
    hours = {}
    for j in range(j0, i):
        hk = ts[j] // 3600
        if (hk + 1) * 3600 > t0:
            continue
        b = hours.get(hk)
        if b is None:
            hours[hk] = [f["bh"][j], f["ah"][j], f["bl"][j], f["al"][j]]
        else:
            b[0] = max(b[0], f["bh"][j]); b[1] = max(b[1], f["ah"][j]); b[2] = min(b[2], f["bl"][j]); b[3] = min(b[3], f["al"][j])
    keys = sorted(hours)[-480:]
    assert len(keys) == 480
    rng = sum((hours[q][0] + hours[q][1]) / 2 - (hours[q][2] + hours[q][3]) / 2 for q in keys) / 480.0
    entry = f["ao"][i] * (1 + slip_m)
    stop = entry - k * rng
    t_exit = t0 + hold * 60
    j = i
    while True:
        if ts[j] >= t_exit and j > i:
            ex, reason, xb = f["bo"][j] * (1 - slip_m), "time", j
            break
        if f["bl"][j] <= stop:
            px = stop if j == i else min(stop, f["bo"][j])
            ex, reason, xb = px * (1 - slip_s), "stop", j
            break
        j += 1
    return {"evening": str(evening), "entry_bar_utc": str(dt.datetime.fromtimestamp(t0, UTC)),
            "entry_bar_ny": str(dt.datetime.fromtimestamp(t0, UTC).astimezone(NYZ)),
            "last_h1_bar_used_ny": str(dt.datetime.fromtimestamp(keys[-1] * 3600, UTC).astimezone(NYZ)),
            "mean_h1_range": rng, "entry": entry, "stop": stop, "exit_bar_utc": str(dt.datetime.fromtimestamp(ts[xb], UTC)),
            "exit": ex, "reason": reason, "R": (ex - entry) / (entry - stop)}


def main():
    df = A.load_is()
    ts = (df.index.values.astype("datetime64[s]").astype(np.int64)).tolist()
    f = {c: df[c].to_numpy().tolist() for c in df.columns}
    t = pd.read_parquet(os.path.join(A.OUT, "trades_01_main.parquet"))
    rng = np.random.default_rng(11)
    picks = set([0, len(t) - 1])
    picks |= set(np.flatnonzero(t.reason.to_numpy() == "stop")[:4].tolist())
    picks |= set(np.flatnonzero(t.entry_delay_min.to_numpy() > 0)[:3].tolist())
    ev = pd.to_datetime(t.evening)
    for y in (2013, 2016, 2019, 2021):                 # first evenings after the spring and autumn switches
        sp = A.nth_weekday(y, 3, 6, 2)
        au = A.nth_weekday(y, 11, 6, 1)
        for d in (sp + dt.timedelta(days=1), sp - dt.timedelta(days=3), au + dt.timedelta(days=1), au - dt.timedelta(days=3)):
            hit = np.flatnonzero(ev.dt.date.to_numpy() == d)
            picks |= set(hit.tolist())
    hit = np.flatnonzero(ev.dt.date.to_numpy() == dt.date(2017, 1, 9))
    picks |= set(hit.tolist())
    picks |= set(rng.choice(len(t), 8, replace=False).tolist())
    rows, worst = [], 0.0
    for p in sorted(picks):
        r = t.iloc[p]
        e = pd.Timestamp(r.evening).date()
        pt = plain_trade(ts, f, e)
        d = {"mine_entry": float(r.entry), "mine_stop": float(r.stop), "mine_exit": float(r.exit), "mine_R": float(r.R),
             "mine_reason": r.reason, "mine_entry_utc": str(r.entry_time)}
        diff = max(abs(pt["entry"] - r.entry), abs(pt["stop"] - r.stop), abs(pt["exit"] - r.exit))
        dR = abs(pt["R"] - r.R)
        worst = max(worst, dR)
        rows.append({**pt, **d, "max_abs_price_diff_usd": diff, "abs_R_diff": dR, "match": bool(diff < 1e-9 and dR < 1e-9 and pt["reason"] == r.reason)})
    # same orders through the lab's engine
    sys.path.insert(0, A.LAB)
    from goldlab.sim import Costs, simulate  # noqa: E402
    c = Costs(commission=0.0, slip_bps=A.FP["slip_stop_bps"], slip_mkt_bps=A.FP["slip_mkt_bps"], swap_long=A.FP["swap_long"],
              swap_short=0.0, spread_mult=1.0, swap_triple="Wed")
    o = pd.DataFrame({"entry_i": t.entry_i.to_numpy(), "side": 1, "etype": 0, "stop_dist": t.stop_dist.to_numpy(),
                      "exit_i": t.exit_i_sched.to_numpy()})
    g = simulate(df, o, sym="xauusd", costs=c, no_overlap=True)
    g = g.sort_index()
    lab_cmp = {"n_lab": int(len(g)), "n_mine": int(len(t)), "skipped": int(g.attrs["skipped"]),
               "max_abs_entry_diff_usd": float(np.abs(g.entry.to_numpy() - t.entry.to_numpy()).max()),
               "max_abs_exit_diff_usd": float(np.abs(g.exit.to_numpy() - t.exit.to_numpy()).max()),
               "max_abs_R_diff": float(np.abs(g.R.to_numpy() - t.R.to_numpy()).max()),
               "same_reasons": bool((g.reason.to_numpy() == t.reason.to_numpy()).all()),
               "max_abs_swap": float(np.abs(g.swap.to_numpy()).max())}
    out = {"n_checked": len(rows), "all_match": bool(all(r["match"] for r in rows)), "max_abs_R_diff": worst, "trades": rows,
           "lab_engine_on_my_orders": lab_cmp}
    A.jdump(out, os.path.join(A.OUT, "ahand.json"))
    for r in rows:
        print(r["evening"], r["entry_bar_ny"], "last H1", r["last_h1_bar_used_ny"], r["reason"], round(r["R"], 4), r["match"])
    print("all match", out["all_match"], "worst dR", worst)
    print("lab engine on my orders", lab_cmp)


if __name__ == "__main__":
    main()
