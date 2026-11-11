"""Construction (b): a bounded martingale INSIDE the day on the four intraday rules. IN SAMPLE ONLY.

Trades: noise30 / ocm4 (us100), nq_btc_follow (btcusd), GOLD_FRI_PM (xauusd); entries, stops, exits untouched.
State seen by a trade at its entry minute t (FP server day, results CLOSED strictly before t, these four rules only):
    d      = sum of stake x R booked today
    streak = number of consecutive losing trades booked today (reset by a winning one)
Stake multiplier m of the trade:
    d >= lock                        -> 0   (the day is won: stop for the day)
    d <= -dstop                      -> 0   (daily loss stop)
    d <  0 and form == "double"      -> min(cap, 2 ** streak)
    d <  0 and form == "recover"     -> min(cap, max(1, (-d + lock_or_0) / a))   (a = the gain per unit stake that a
                                            winning trade is assumed to bring: one such win puts the day back to green)
    otherwise                        -> 1
Zero-edge control (Addendum E): the same rule on the same trades, each trade's result replaced by
(R - mean R of its sleeve) x a random sign, 1,000 draws.

    python3 b_marti.py     -> results/r2/jours/b_marti.json, b_marti_common.csv, b_marti_trials.jsonl (16 configurations)
"""
import json
import os

import numpy as np
import pandas as pd
from numba import njit

import common as C

BIG = 1e18
CONFIGS = [
    ("ref", dict()),
    ("lock0", dict(lock=0.01)),
    ("lock0.5", dict(lock=0.5)),
    ("dbl2_lock0", dict(form=1, cap=2, lock=0.01)),
    ("dbl4_lock0", dict(form=1, cap=4, lock=0.01)),
    ("dbl8_lock0", dict(form=1, cap=8, lock=0.01)),
    ("rec2_lock0", dict(form=2, cap=2, lock=0.01)),
    ("rec3_lock0", dict(form=2, cap=3, lock=0.01)),
    ("rec5_lock0", dict(form=2, cap=5, lock=0.01)),
    ("rec8_lock0", dict(form=2, cap=8, lock=0.01)),
    ("rec5_a0.5_lock0", dict(form=2, cap=5, a=0.5, lock=0.01)),
    ("rec5_lock0.5", dict(form=2, cap=5, lock=0.5)),
    ("rec3_lock0.3", dict(form=2, cap=3, lock=0.3)),
    ("rec5_nolock", dict(form=2, cap=5)),
    ("dbl4_nolock", dict(form=1, cap=4)),
    ("rec5_lock0_dstop5", dict(form=2, cap=5, lock=0.01, dstop=5.0)),
]
DEFAULT = dict(form=0, cap=1.0, a=1.0, lock=BIG, dstop=BIG)


@njit(cache=True)
def engine(t_in, t_out, R, dy_in, dy_out, order_out, ndy, form, cap, a, lock, dstop):
    n = len(R)
    m = np.zeros(n)
    d = np.zeros(ndy)
    streak = np.zeros(ndy)
    j = 0
    for i in range(n):
        while j < n and t_out[order_out[j]] < t_in[i]:
            k = order_out[j]
            j += 1
            if m[k] > 0.0:
                d[dy_out[k]] += m[k] * R[k]
                if R[k] < 0.0:
                    streak[dy_out[k]] += 1.0
                else:
                    streak[dy_out[k]] = 0.0
        x = d[dy_in[i]]
        if x >= lock or x <= -dstop:
            continue
        mm = 1.0
        if x < 0.0:
            if form == 1:
                mm = min(cap, 2.0 ** streak[dy_in[i]])
            elif form == 2:
                mm = min(cap, max(1.0, (-x + (lock if lock < 1e17 else 0.0)) / a))
        m[i] = mm
    return m


def prep(d):
    si, so = C.server_time(d.t_in), C.server_time(d.t_out)
    day0 = np.datetime64("1970-01-01")
    di = (si.values.astype("datetime64[D]") - day0).astype("int64")
    do = (so.values.astype("datetime64[D]") - day0).astype("int64")
    lo = min(di.min(), do.min())
    a = dict(t_in=d.t_in.values.astype("datetime64[ns]").astype("int64"), t_out=d.t_out.values.astype("datetime64[ns]").astype("int64"),
             R=d.R.to_numpy(float), dy_in=di - lo, dy_out=do - lo, ndy=int(max(di.max(), do.max()) - lo + 1), lo=lo)
    a["order_out"] = np.argsort(a["t_out"], kind="stable")
    a["wk_out"] = (do + 3) // 7
    a["wk_out"] = a["wk_out"] - a["wk_out"].min()
    return a


def stakes(a, cfg, R=None):
    c = dict(DEFAULT)
    c.update(cfg)
    return engine(a["t_in"], a["t_out"], a["R"] if R is None else R, a["dy_in"], a["dy_out"], a["order_out"], a["ndy"],
                  int(c["form"]), float(c["cap"]), float(c["a"]), float(c["lock"]), float(c["dstop"]))


@njit(cache=True)
def _quick(res, dy_out, wk_out, ndy, nwk):
    d = np.zeros(ndy)
    w = np.zeros(nwk)
    has = np.zeros(ndy)
    hasw = np.zeros(nwk)
    for i in range(len(res)):
        if res[i] != 0.0:
            d[dy_out[i]] += res[i]
            w[wk_out[i]] += res[i]
            has[dy_out[i]] = 1.0
            hasw[wk_out[i]] = 1.0
    gd = 0.0
    nd = 0.0
    eq = 0.0
    low = 0.0
    wd = 0.0
    for k in range(ndy):
        if has[k] > 0:
            nd += 1
            if d[k] > 0:
                gd += 1
            eq += d[k]
            low = min(low, eq)
            wd = min(wd, d[k])
    gw = 0.0
    nw = 0.0
    ww = 0.0
    for k in range(nwk):
        if hasw[k] > 0:
            nw += 1
            if w[k] > 0:
                gw += 1
            ww = min(ww, w[k])
    return gd / nd, gw / nw, wd, ww, low, eq


def zero_edge(d, cfg, n=1000, seed=11):
    """Addendum E control on frame d (columns sleeve, t_in, t_out, R): rule applied to no-edge results."""
    a = prep(d)
    mean = d.groupby("sleeve").R.transform("mean").to_numpy()
    base = d.R.to_numpy(float) - mean
    rng = np.random.default_rng(seed)
    nwk = int(a["wk_out"].max()) + 1
    rows = np.zeros((n, 6))
    for b in range(n):
        R = base * rng.choice(np.array([-1.0, 1.0]), size=len(base))
        m = stakes(a, cfg, R)
        rows[b] = _quick(m * R, a["dy_out"], a["wk_out"], a["ndy"], nwk)
    return {"green_days": round(float(rows[:, 0].mean() * 100), 1), "green_weeks": round(float(rows[:, 1].mean() * 100), 1),
            "worst_day_median": round(float(np.median(rows[:, 2])), 2), "worst_day_p5": round(float(np.quantile(rows[:, 2], 0.05)), 2),
            "worst_week_median": round(float(np.median(rows[:, 3])), 2), "worst_week_p5": round(float(np.quantile(rows[:, 3], 0.05)), 2),
            "total_mean": round(float(rows[:, 5].mean()), 1), "total_p5": round(float(np.quantile(rows[:, 5], 0.05)), 1),
            "p_lose_50_units": round(float((rows[:, 4] <= -50).mean()), 4), "p_lose_25_units": round(float((rows[:, 4] <= -25).mean()), 4)}


if __name__ == "__main__":
    out, rows = {}, []
    for name, cfg in CONFIGS:
        rec = {"config": cfg}
        for kind in ("gross", "net"):
            allt = C.load_trades(kind)
            for per in ("common", "whole"):
                d = allt if per == "whole" else allt[allt.t_in >= C.COMMON_START]
                d = d.reset_index(drop=True)
                intr = d[d.sleeve.isin(C.INTRADAY)].reset_index(drop=True)
                rest = d[~d.sleeve.isin(C.INTRADAY)]
                a = prep(intr)
                m = stakes(a, cfg)
                res = m * intr.R.to_numpy()
                day4 = C.daily(intr.t_out, res)
                s4 = C.stats(day4)
                s4.update(trades_taken=int((m > 0).sum()), trades=int(len(m)), mean_stake=round(float(m[m > 0].mean()), 2),
                          max_stake=float(m.max()), halves=C.halves(day4))
                day10 = C.daily(pd.concat([intr.t_out, rest.t_out]), np.concatenate([res, rest.R.to_numpy()]))
                s10 = C.stats(day10)
                rec[f"{kind}_{per}_intraday4"] = s4
                rec[f"{kind}_{per}_ten"] = s10
                if per == "common":
                    for scope, s in (("intraday4", s4), ("ten", s10)):
                        rows.append(dict(config=name, kind=kind, scope=scope, **{c: s[c] for c in (
                            "days", "green_days", "green_weeks", "green_months", "avg_green", "avg_red", "red_in_greens", "total",
                            "worst_day", "worst_week", "max_dd")}))
                if kind == "gross" and per == "common":
                    rec["zero_edge_common_intraday4"] = zero_edge(intr[["sleeve", "t_in", "t_out", "R"]], cfg)
                    z = rec["zero_edge_common_intraday4"]
                    rows.append(dict(config=name, kind="zero", scope="intraday4", green_days=z["green_days"],
                                     green_weeks=z["green_weeks"], total=z["total_mean"], worst_day=z["worst_day_median"],
                                     worst_week=z["worst_week_median"]))
        out[name] = rec
        C.log_trial({"construction": "b_marti", "name": name, **rec}, "b_marti_trials.jsonl")
    json.dump(out, open(os.path.join(C.OUT, "b_marti.json"), "w"), indent=1)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(C.OUT, "b_marti_common.csv"), index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 300)
    print(df.sort_values(["scope", "kind"], kind="stable").to_string())
