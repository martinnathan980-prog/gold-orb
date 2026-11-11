"""Construction (e) (added by this track; exit shaping at the ACCOUNT level): a daily target on the account equity.

The ten validated rules trade as they are (same entries, stops, exits, equal stake). One more rule, on the whole account:
    day P&L(t) = change of the account EQUITY (closed results + open positions marked at the last minute close)
                 since 00:00 FP server time (17:00 New York)
    when day P&L >= +g  -> close every open position at once, take no new trade until the next server day
    when day P&L <= -L  -> same (daily loss stop; L = none in most configurations)
A trade whose own exit falls inside a minute bar is booked at its real result in that minute (never marked at a
price later than its exit). The check is made on the close of every minute and the positions are closed at that minute's close (bid for a long,
ask for a short, plus the market slippage of r2/fp_costs.json when costs are on). A trade that the rule closes early
is not re-opened; a trade whose entry falls after the lock is not taken. Signals that the frozen rule skipped because
its previous trade was still open are NOT recovered (the trade list is the validated one): slightly conservative.

Day results here are EQUITY-based (open positions marked at 24:00 server time), which is what the MT5 account shows;
the reference in the same convention is the configuration g = none.
Units: base stake (1 = the risk of one trade of the validated rules). IN SAMPLE ONLY, common period 2018-02 .. 2021.

Zero-edge control: the same rule on the same trades, each trade's whole P&L path multiplied by a random sign (a trade
and its mirror image are equally likely: expectation exactly zero, gross), N_DRAWS draws.

    python3 e_daytarget.py      -> results/r2/jours/e_daytarget.json, e_daytarget_common.csv, e_days/<config>__<kind>.csv
"""
import json
import os

import numpy as np
import pandas as pd
from numba import njit

import common as C
from goldlab import r2

SYMS = ["us100", "btcusd", "ethusd", "xauusd"]
BIG = 1e18
N_DRAWS = 200
CONFIGS = [("none", BIG, BIG)] + [(f"g{g}", g, BIG) for g in (0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0)] + \
          [("g0.5_L3", 0.5, 3.0), ("g1_L3", 1.0, 3.0), ("g1_L6", 1.0, 6.0), ("g2_L4", 2.0, 4.0), ("L3_only", BIG, 3.0)]
GRID0 = pd.Timestamp("2018-01-28", tz="UTC")
GRID1 = C.IS_END_FRAME


def grid_prices():
    """bid close / ask close of the four markets on one minute grid (forward-filled), in-sample frames only."""
    grid = pd.date_range(GRID0, GRID1, freq="1min", inclusive="left")
    bid = np.zeros((len(SYMS), len(grid)))
    ask = np.zeros((len(SYMS), len(grid)))
    for k, s in enumerate(SYMS):
        from goldlab import data as _data
        df = pd.read_parquet(os.path.join(_data.DATA, "fp", f"{s}_m1.parquet"), columns=["bc", "ac"])
        df = df[(df.index >= GRID0 - pd.Timedelta(days=5)) & (df.index < C.IS_END_FRAME)]
        df = df.reindex(grid, method="ffill")
        bid[k], ask[k] = df.bc.to_numpy(float), df.ac.to_numpy(float)
    st = C.server_time(grid)
    day = (st.values.astype("datetime64[D]") - np.datetime64("1970-01-01")).astype("int64")
    return grid, bid, ask, day


@njit(cache=True)
def engine(tin, tout, sym, side, entry, r0, rfin, sgn, bid, ask, day, g, L, slip, gross):
    """Returns (day results per grid day index, lock flag per day, result booked per trade, taken flag)."""
    N = len(day)
    d0 = day[0]
    nd = day[-1] - d0 + 1
    res = np.zeros(nd)
    lock = np.zeros(nd)
    n = len(tin)
    booked = np.zeros(n)
    taken = np.zeros(n)
    open_id = np.empty(64, np.int64)
    ms = np.zeros(n)                      # mark of each open trade at the start of the current day
    no = 0
    j = 0
    realized = 0.0
    locked = False
    cur = day[0]
    last_m = np.zeros(n)                  # last mark of each open trade
    for t in range(N):
        if day[t] != cur:
            fl = 0.0
            for q in range(no):
                i = open_id[q]
                fl += last_m[i] - ms[i]
                ms[i] = last_m[i]
            res[cur - d0] = realized + fl
            lock[cur - d0] = 1.0 if locked else 0.0
            realized = 0.0
            locked = False
            cur = day[t]
        q = 0
        while q < no:                     # natural exits
            i = open_id[q]
            if tout[i] <= t + 1:           # the exit happens inside this minute bar: booked at its real result
                realized += sgn[i] * rfin[i] - ms[i]
                booked[i] = sgn[i] * rfin[i]
                open_id[q] = open_id[no - 1]
                no -= 1
            else:
                q += 1
        while j < n and tin[j] <= t:      # entries
            if not locked and tout[j] > t + 1:
                open_id[no] = j
                no += 1
                ms[j] = 0.0
                last_m[j] = 0.0
                taken[j] = 1.0
            elif not locked:              # in and out within the same minute
                realized += sgn[j] * rfin[j]
                booked[j] = sgn[j] * rfin[j]
                taken[j] = 1.0
            j += 1
        fl = 0.0
        for q in range(no):
            i = open_id[q]
            if gross:
                p = 0.5 * (bid[sym[i], t] + ask[sym[i], t])
            else:
                p = bid[sym[i], t] if side[i] * sgn[i] > 0 else ask[sym[i], t]
            m = sgn[i] * side[i] * (p - entry[i]) / r0[i]
            if not gross:
                m -= slip[sym[i]] * p / r0[i]
            last_m[i] = m
            fl += m - ms[i]
        pnl = realized + fl
        if not locked and no >= 0 and (pnl >= g or pnl <= -L):
            for q in range(no):
                i = open_id[q]
                booked[i] = last_m[i]
            realized = pnl
            no = 0
            locked = True
    fl = 0.0
    for q in range(no):
        i = open_id[q]
        fl += last_m[i] - ms[i]
    res[cur - d0] = realized + fl
    return res, lock, booked, taken


def trades_arrays(kind, grid):
    d = C.load_trades(kind)
    d = d[d.t_in >= C.COMMON_START].reset_index(drop=True)
    g0 = grid[0].value
    a = dict(tin=((d.t_in.astype("int64") - g0) // 60_000_000_000).to_numpy(np.int64) if False else
             ((d.t_in.values.astype("datetime64[ns]").astype("int64") - g0) // 60_000_000_000),
             tout=-(-(d.t_out.values.astype("datetime64[ns]").astype("int64") - g0) // 60_000_000_000),
             sym=d.sym.map({s: k for k, s in enumerate(SYMS)}).to_numpy(np.int64), side=d.side.to_numpy(np.int64),
             entry=d.entry.to_numpy(float), r0=d.risk.to_numpy(float), rfin=d.R.to_numpy(float))
    return d, a


def series(res, day):
    idx = pd.to_datetime((np.arange(len(res)) + day[0]).astype("datetime64[D]"))
    s = pd.Series(res, index=idx)
    return s[(s.index >= pd.Timestamp("2018-02-01")) & (s.index < pd.Timestamp("2022-01-01"))]


if __name__ == "__main__":
    grid, bid, ask, day = grid_prices()
    slip = np.array([r2.SPEC[s]["slip_mkt_bps"] * 1e-4 for s in SYMS])
    os.makedirs(os.path.join(C.OUT, "e_days"), exist_ok=True)
    out, rows = {}, []
    tr = {k: trades_arrays(k, grid) for k in ("gross", "net")}
    for name, g, L in CONFIGS:
        rec = {"g": None if g > 1e17 else g, "L": None if L > 1e17 else L}
        for kind in ("gross", "net"):
            d, a = tr[kind]
            one = np.ones(len(d))
            res, lock, booked, taken = engine(a["tin"], a["tout"], a["sym"], a["side"], a["entry"], a["r0"], a["rfin"], one,
                                              bid, ask, day, g, L, slip, kind == "gross")
            s = series(res, day)
            s.to_csv(os.path.join(C.OUT, "e_days", f"{name}__{kind}.csv"), header=["res"])
            st = C.stats(s)
            lk = series(lock, day)
            st.update(trades_taken=int(taken.sum()), trades=int(len(d)), locked_days_pct=round(float(lk[s != 0].mean() * 100), 1),
                      halves=C.halves(s), flat_weekdays=int(((s == 0) & (s.index.dayofweek < 5)).sum()))
            rec[kind] = st
            rows.append(dict(config=name, kind=kind, **{c: st[c] for c in ("days", "green_days", "green_weeks", "green_months",
                        "avg_green", "avg_red", "red_in_greens", "total", "per_year", "worst_day", "worst_week", "max_dd", "locked_days_pct")}))
        d, a = tr["gross"]
        rng = np.random.default_rng(3)
        z = []
        for b in range(N_DRAWS):
            sg = rng.choice(np.array([-1.0, 1.0]), size=len(d))
            res, _, _, _ = engine(a["tin"], a["tout"], a["sym"], a["side"], a["entry"], a["r0"], a["rfin"], sg, bid, ask, day,
                                  g, L, slip, True)
            s = series(res, day)
            st = C.stats(s)
            st["low"] = float(s.cumsum().min())
            z.append(st)
        z = pd.DataFrame(z)
        rec["zero_edge"] = {"green_days": round(float(z.green_days.mean()), 1), "green_weeks": round(float(z.green_weeks.mean()), 1),
                            "green_months": round(float(z.green_months.mean()), 1), "avg_green": round(float(z.avg_green.mean()), 2),
                            "avg_red": round(float(z.avg_red.mean()), 2), "total_mean": round(float(z.total.mean()), 1),
                            "total_p5": round(float(z.total.quantile(0.05)), 1), "worst_day_median": round(float(z.worst_day.median()), 2),
                            "worst_week_median": round(float(z.worst_week.median()), 2), "worst_week_p5": round(float(z.worst_week.quantile(0.05)), 2),
                            "p_lose_50_units": round(float((z.low <= -50).mean()), 3), "p_lose_25_units": round(float((z.low <= -25).mean()), 3)}
        ze = rec["zero_edge"]
        rows.append(dict(config=name, kind="zero", green_days=ze["green_days"], green_weeks=ze["green_weeks"], green_months=ze["green_months"],
                         avg_green=ze["avg_green"], avg_red=ze["avg_red"], total=ze["total_mean"], worst_day=ze["worst_day_median"],
                         worst_week=ze["worst_week_median"]))
        out[name] = rec
        C.log_trial({"construction": "e_daytarget", "name": name, **rec}, "e_daytarget_trials.jsonl")
        print(name, "done", flush=True)
    # account realism: fixed 1,000 EUR, 1 % stake = 10 EUR a trade, lots rounded down to the step, trade skipped below
    # the minimum lot (no compounding; position caps of the MT5 hands not modelled here). Net only.
    d, a = tr["net"]
    w = np.zeros(len(d))
    for k, (sym, risk) in enumerate(zip(d.sym, d.risk)):
        sp = r2.SPEC[sym]
        per_lot = risk * sp["units_per_lot"] * 0.89
        lots = np.floor(10.0 / per_lot / sp["lot_step"] + 1e-9) * sp["lot_step"]
        w[k] = lots * per_lot / 10.0 if lots >= sp["min_lot"] else 0.0
    out["account_1000_eur_fixed_1pct"] = {"trades_sizable_pct": round(float((w > 0).mean() * 100), 1), "mean_stake_when_taken": round(float(w[w > 0].mean()), 2)}
    for name, g, L in CONFIGS:
        if name not in ("none", "g0.5", "g1.0", "g1.5", "g2.0"):
            continue
        res, lock, booked, taken = engine(a["tin"], a["tout"], a["sym"], a["side"], a["entry"], a["r0"], a["rfin"], w, bid, ask, day,
                                          g, L, slip, False)
        st = C.stats(series(res, day))
        out["account_1000_eur_fixed_1pct"][name] = st
        rows.append(dict(config=name + "@1000EUR", kind="net", **{c: st[c] for c in ("days", "green_days", "green_weeks", "green_months",
                    "avg_green", "avg_red", "red_in_greens", "total", "per_year", "worst_day", "worst_week", "max_dd")}))
    json.dump(out, open(os.path.join(C.OUT, "e_daytarget.json"), "w"), indent=1)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(C.OUT, "e_daytarget_common.csv"), index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 300)
    print(df.to_string())
