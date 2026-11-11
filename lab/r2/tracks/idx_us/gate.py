"""PROTOCOL_V3 addendum C: "stressed market" gate on the us100 noise-area momentum sleeve (`noise30`).

Two flags, both known before 09:30 New York (file: https://squeezemetrics.com/monitor/static/DIX.csv saved as
data/ext/DIX.csv; columns `price` = S&P 500 close, `gex` = dealers' gamma estimate):
  pct(x)  share of the previous 251 values strictly below today's value (window 252, at least 126)
  G       pct(previous day's gex) < 0.33
  P       pct(sum of the last five daily log returns of price, up to the previous close) < 0.33

    python3 r2/tracks/idx_us/gate.py is     # reproduction on the in-sample trades (no 2022+ row read)
    python3 r2/tracks/idx_us/gate.py val    # the lead's single look at 2022-2025 (logged)
"""
import datetime as dt
import json
import os
import sys

import numpy as np
import pandas as pd

LAB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
OUT = os.path.join(LAB, "results", "r2", "idx_us")
FILE = os.path.join(LAB, "data", "ext", "DIX.csv")
IS_TRADES = os.path.join(OUT, "trades_is_noise30_us100.csv")
ALL_TRADES = os.path.join(LAB, "results", "r2", "recalc", "trades", "noise30__us100.parquet")


def pct(s, w=252):
    return s.rolling(w, min_periods=w // 2).apply(lambda v: (v[:-1] < v[-1]).mean(), raw=True)


def flags(cap):
    g = pd.read_csv(FILE, parse_dates=["date"]).set_index("date")
    g = g[g.index < pd.Timestamp(cap)]
    r = np.log(g.price).diff()
    f = pd.DataFrame({"g_pct": pct(g.gex.shift(1)), "p_pct": pct(r.rolling(5).sum().shift(1))})
    f["G"] = f.g_pct < 0.33
    f["P"] = f.p_pct < 0.33
    return f


def _pf(x):
    return float(x[x > 0].sum() / -x[x < 0].sum())


def _t(x):
    return float(x.mean() / x.std(ddof=1) * np.sqrt(len(x)))


def split(E, flag):
    a, b = E.R[E[flag]], E.R[~E[flag]]
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    by = {}
    better = 0
    for y, x in E.groupby(E.d.dt.year):
        fa, fb = x.R[x[flag]], x.R[~x[flag]]
        by[int(y)] = {"flag_n": int(len(fa)), "flag_R": round(float(fa.mean()), 3), "rest_n": int(len(fb)),
                      "rest_R": round(float(fb.mean()), 3)}
        better += fa.mean() > fb.mean()
    days = E.groupby("d")[flag].first()
    return {"flag_n": int(len(a)), "flag_exp_R": round(float(a.mean()), 3), "flag_pf": round(_pf(a), 2),
            "flag_t": round(_t(a), 2), "flag_win_pct": round(float((a > 0).mean() * 100), 1),
            "rest_n": int(len(b)), "rest_exp_R": round(float(b.mean()), 3), "rest_pf": round(_pf(b), 2),
            "diff_R": round(float(a.mean() - b.mean()), 3), "z": round(float((a.mean() - b.mean()) / se), 2),
            "flag_days_pct": round(float(days.mean() * 100), 1), "years_flag_better": f"{better}/{len(by)}",
            "by_year": by}


def prepare(T, cap):
    T = T.copy()
    T["t"] = pd.to_datetime(T["entry_time"], utc=True)
    T["d"] = T.t.dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
    E = T.join(flags(cap), on="d").dropna(subset=["g_pct", "p_pct"])
    return E


def weights(E, flag, lo=1.5, hi=0.75):
    out = {}
    for name, w in (("flat", np.ones(len(E))), (f"{lo}x/{hi}x", np.where(E[flag], lo, hi))):
        x = E.R * w
        d = x.groupby(E.d).sum()
        out[name] = {"avg_weight": round(float(np.mean(w)), 3), "sum_R": round(float(x.sum()), 1),
                     "daily_t": round(_t(d), 2), "worst_day_R": round(float(d.min()), 2),
                     "max_dd_R": round(float((d.cumsum() - d.cumsum().cummax()).min()), 1)}
    return out


def run_is():
    T = pd.read_csv(IS_TRADES)
    E = prepare(T[pd.to_datetime(T.entry_time, utc=True) < pd.Timestamp("2022-01-01", tz="UTC")], "2022-01-01")
    out = {"period": "is", "n": int(len(E)), "exp_R": round(float(E.R.mean()), 3), "G": split(E, "G"), "P": split(E, "P"),
           "both_flags_n": int((E.G & E.P).sum()), "neither_exp_R": round(float(E.R[~E.G & ~E.P].mean()), 3),
           "neither_n": int((~E.G & ~E.P).sum())}
    json.dump(out, open(os.path.join(OUT, "gate_is.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


def run_val():
    with open(os.path.join(LAB, "results", "val_access.log"), "a") as f:
        f.write(json.dumps({"time": dt.datetime.utcnow().isoformat(timespec="seconds"), "track": "idx_us",
                            "label": "noise30_stress_gate:lead_single_look", "period": "val"}) + "\n")
    T = pd.read_parquet(ALL_TRADES)
    T = T[(T.entry_time >= pd.Timestamp("2022-01-01", tz="UTC")) & (T.entry_time < pd.Timestamp("2026-01-01", tz="UTC"))]
    E = prepare(T, "2026-01-01")
    out = {"period": "val", "n": int(len(E)), "exp_R": round(float(E.R.mean()), 3), "pf": round(_pf(E.R), 2)}
    for fl in ("G", "P"):
        s = split(E, fl)
        yb = int(s["years_flag_better"].split("/")[0])
        s["criteria"] = {"diff>=0.10R": s["diff_R"] >= 0.10, "flag_pf>=1.25": s["flag_pf"] >= 1.25,
                         "better_in>=3/4_years": yb >= 3}
        s["criteria"]["pass"] = all(s["criteria"].values())
        s["sizing"] = weights(E, fl)
        out[fl] = s
    out["decision"] = ("P alone" if out["P"]["criteria"]["pass"] else
                       "G after 60 demo sessions" if out["G"]["criteria"]["pass"] else "no gate")
    json.dump(out, open(os.path.join(OUT, "gate_val.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    {"is": run_is, "val": run_val}[sys.argv[1]]()
