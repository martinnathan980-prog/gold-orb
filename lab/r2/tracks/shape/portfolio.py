"""Portfolio reading of track `shape` from the FROZEN selection (results/r2/shape/selection.json).

    from portfolio import table
    port, per_sleeve = table("is")      # research agent: "is" only
    port, per_sleeve = table("val")     # the lead, once (validation access is logged by gl.cut)

Three portfolios, all eleven sleeves at equal risk per trade (1 R per trade, sum of R), one position per sleeve:
  baseline  : original exits
  selected  : the frozen per-sleeve choice (a "half" choice = half the risk on the original exit, half on the
              variant: each half is booked at 0.5 R x its own R on its own exit day)
  T1_all    : information only, the most aggressive shape: a pure target at 1 x R0 on every sleeve
P&L is booked on the New York calendar day of the EXIT. Shares of winning days / weeks / months are taken over
the days (weeks, months) with at least one exit; weeks run Sunday-Saturday (a Sunday-evening reopen belongs to
the following trading week). Period: "is" = entries 2018-02-01 .. 2021-12-31 (the common period: ether data start
in January 2018 and its F1 sleeve trades from 2018-01-30), "val" = entries 2022-01-01 .. 2025-12-31.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import strategy as S  # noqa: E402
import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402

OUT = os.path.join(S.LAB, "results", "r2", "shape")
COMMON_START = {"is": "2018-02-01", "val": "2022-01-01"}


def _cut(t, period, label):
    if period == "is":
        t = gl.cut(t, "is")
    else:
        t = gl.cut(t, "val", track="shape", label=label)
    return t[t.entry_time >= pd.Timestamp(COMMON_START[period], tz="UTC")]


def _legs(t, w=1.0):
    return pd.DataFrame({"exit_time": t.exit_time.to_numpy(), "R": w * t.R.to_numpy()})


def selection():
    return json.load(open(os.path.join(OUT, "selection.json")))["selection"]


def sleeve_legs(period):
    """{scenario: {sleeve: (legs DataFrame, per-trade R array)}}"""
    sel = selection()
    out = {"baseline": {}, "selected": {}, "T1_all": {}}
    last = None
    for key, (sym, mo, params) in S.sleeves().items():
        if sym != last:
            r2.free(); last = sym
        m1 = r2.load(sym)
        lab = f"{key}:shape"
        base = _cut(r2.run(sym, mo, params, "fp", True, m1), period, lab + ":base")
        out["baseline"][key] = (_legs(base), base.R.to_numpy())
        s = sel[key]
        if s["variant"] is None:
            out["selected"][key] = out["baseline"][key]
        elif s["half"]:
            mv = S.shaped(mo, k=s["k"], be_r=s["be"])
            ta = _cut(r2.run(sym, mv, params, "fp", False, m1), period, lab + ":sel_all")
            tv = ta.loc[base.index]
            assert (tv.entry_time.to_numpy() == base.entry_time.to_numpy()).all()
            legs = pd.concat([_legs(base, 0.5), _legs(tv, 0.5)], ignore_index=True)
            out["selected"][key] = (legs, 0.5 * base.R.to_numpy() + 0.5 * tv.R.to_numpy())
        else:
            mv = S.shaped(mo, k=s["k"], be_r=s["be"])
            tv = _cut(r2.run(sym, mv, params, "fp", True, m1), period, lab + ":sel")
            out["selected"][key] = (_legs(tv), tv.R.to_numpy())
        t1 = _cut(r2.run(sym, S.shaped(mo, k=1.0), params, "fp", True, m1), period, lab + ":T1")
        out["T1_all"][key] = (_legs(t1), t1.R.to_numpy())
    r2.free()
    return out


def _calendar(legs):
    d = legs.copy()
    d["day"] = pd.DatetimeIndex(d.exit_time).tz_convert(gl.NY).tz_localize(None).normalize()
    day = d.groupby("day").R.sum()
    week = day.groupby(day.index.to_period("W-SAT")).sum()
    month = day.groupby(day.index.to_period("M")).sum()
    neg = (day < 0).to_numpy()
    streak = cur = 0
    for x in neg:
        cur = cur + 1 if x else 0
        streak = max(streak, cur)
    return {"days": len(day), "win_days": round(float((day > 0).mean()), 4), "win_weeks": round(float((week > 0).mean()), 4),
            "win_months": round(float((month > 0).mean()), 4), "total_R": round(float(day.sum()), 1),
            "worst_day": round(float(day.min()), 2), "worst_week": round(float(week.min()), 2),
            "longest_losing_streak_days": int(streak), "best_day": round(float(day.max()), 2)}


def table(period):
    """(portfolio table, per-sleeve table) for period 'is' | 'val' (common period, see module doc)."""
    if period not in ("is", "val"):
        raise ValueError(period)
    L = sleeve_legs(period)
    port, per = [], []
    for sc, d in L.items():
        legs = pd.concat([v[0] for v in d.values()], ignore_index=True)
        n = sum(len(v[1]) for v in d.values())
        port.append(dict(scenario=sc, trades=n, **_calendar(legs)))
        for key, (_, R) in d.items():
            w, l = R[R > 0].sum(), -R[R < 0].sum()
            per.append(dict(sleeve=key, scenario=sc, n=len(R), win=round(float((R > 0).mean()), 4),
                            exp=round(float(R.mean()), 4), pf=round(float(w / l), 3) if l > 0 else np.inf,
                            total_R=round(float(R.sum()), 1)))
    per = pd.DataFrame(per).pivot(index="sleeve", columns="scenario")
    return pd.DataFrame(port).set_index("scenario"), per


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "is"
    port, per = table(p)
    pd.set_option("display.width", 250)
    print(port.to_string())
    print(per.to_string())
    port.to_csv(os.path.join(OUT, f"portfolio_{p}.csv"))
    per.to_csv(os.path.join(OUT, f"portfolio_per_sleeve_{p}.csv"))
