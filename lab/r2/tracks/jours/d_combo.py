"""Construction (d): the ten validated rules (profit) + ONE high-hit-rate daily structure sized to make most days green.

Structure = the only one of the 40 of construction (c) that keeps >= 70 % winning days with a net expectation >= 0 and
both halves positive: `mom` on us500, T = 0.10 ADR, S = 0.60 ADR (trials.jsonl: p2_00_mom_us500). Its net expectation
is +0.012 R a day with t = 1.55: indistinguishable from zero; it is used here as a "shape", not as an edge.
Size s = what the structure loses at its full stop, in base stakes (1 = the risk of one trade of the ten rules).
Day result = ten rules (booked on the server day of the exit) + s x structure result (R). Common period 2018-02 .. 2021.
Second family: the same with the account daily target of construction (e) on the ten rules (equity-based days).

Zero-edge control: ten rules = (R - sleeve mean) x random sign (Addendum E); structure = its own results with the mean
removed, shuffled among its days; 300 draws.

    python3 d_combo.py   -> results/r2/jours/d_combo.json, d_combo_common.csv
"""
import json
import os

import numpy as np
import pandas as pd

import common as C

SIZES = [0, 1, 2, 3, 5, 8, 12, 20]
STRUCT = "p2_00_mom_us500"
START, END = pd.Timestamp("2018-02-01"), pd.Timestamp("2022-01-01")


def struct_days(kind):
    t = pd.read_parquet(os.path.join(C.OUT, "c_trades", f"{STRUCT}__{kind}.parquet"))
    t = t[t.entry_time < C.IS_END]
    return C.daily(t.exit_time, t.R, START, END)


def port_days(kind):
    d = C.load_trades(kind)
    d = d[d.t_in >= C.COMMON_START]
    return C.daily(d.t_out, d.R, START, END), d


def add(a, b, s):
    idx = a.index.union(b.index)
    return a.reindex(idx, fill_value=0.0) + s * b.reindex(idx, fill_value=0.0)


if __name__ == "__main__":
    out, rows = {}, []
    X = {k: struct_days(k) for k in ("gross", "net")}
    P = {k: port_days(k) for k in ("gross", "net")}
    out["structure_alone_common"] = {k: {**C.stats(X[k]), "halves": C.halves(X[k])} for k in X}
    for fam in ("ten", "ten_g1.0", "ten_g0.5"):
        for s in SIZES:
            name = f"{fam}+{s}xmom500"
            rec = {"family": fam, "size": s}
            for kind in ("gross", "net"):
                if fam == "ten":
                    base = P[kind][0]
                else:
                    e = pd.read_csv(os.path.join(C.OUT, "e_days", f"{fam[4:]}__{kind}.csv"), index_col=0, parse_dates=True).res
                    base = e[e != 0]
                day = add(base, X[kind], s)
                st = C.stats(day)
                st["halves"] = C.halves(day)
                st["p_half_week_bootstrap_1y_50u"] = C.week_bootstrap(day)
                rec[kind] = st
                rows.append(dict(config=name, kind=kind, **{c: st[c] for c in ("days", "green_days", "green_weeks", "green_months",
                            "avg_green", "avg_red", "red_in_greens", "total", "per_year", "worst_day", "worst_week", "max_dd")}))
            if fam == "ten":
                d = P["gross"][1]
                base = (d.R - d.groupby("sleeve").R.transform("mean")).to_numpy()
                xg = X["gross"]
                xb = (xg - xg.mean()).to_numpy()
                rng = np.random.default_rng(9)
                z = []
                for b in range(300):
                    p = C.daily(d.t_out, base * rng.choice(np.array([-1.0, 1.0]), size=len(base)), START, END)
                    x = pd.Series(rng.permutation(xb), index=xg.index)
                    day = add(p, x, s)
                    st = C.stats(day)
                    st["low"] = float(day.cumsum().min())
                    z.append(st)
                z = pd.DataFrame(z)
                rec["zero_edge"] = {"green_days": round(float(z.green_days.mean()), 1), "green_weeks": round(float(z.green_weeks.mean()), 1),
                                    "avg_green": round(float(z.avg_green.mean()), 2), "avg_red": round(float(z.avg_red.mean()), 2),
                                    "worst_day_median": round(float(z.worst_day.median()), 2), "worst_week_median": round(float(z.worst_week.median()), 2),
                                    "worst_week_p5": round(float(z.worst_week.quantile(0.05)), 2),
                                    "p_lose_50_units": round(float((z.low <= -50).mean()), 3), "p_lose_25_units": round(float((z.low <= -25).mean()), 3)}
                ze = rec["zero_edge"]
                rows.append(dict(config=name, kind="zero", green_days=ze["green_days"], green_weeks=ze["green_weeks"], avg_green=ze["avg_green"],
                                 avg_red=ze["avg_red"], worst_day=ze["worst_day_median"], worst_week=ze["worst_week_median"]))
            out[name] = rec
            C.log_trial({"construction": "d_combo", "name": name, **rec}, "d_combo_trials.jsonl")
    json.dump(out, open(os.path.join(C.OUT, "d_combo.json"), "w"), indent=1)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(C.OUT, "d_combo_common.csv"), index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 300)
    print(json.dumps(out["structure_alone_common"]))
    print(df.to_string())
