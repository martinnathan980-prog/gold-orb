"""Track `fx`, PROTOCOL_V3 addendum D: Tokyo fixing on settlement days (USD/JPY).

Frozen rule `B6_tokyo_gotobi`: on gotobi days (5th, 10th, 15th, 20th, 25th, last day of the month; moved back to the
previous Japanese bank business day), except Bank of Japan decision days, SELL USDJPY at market at 09:55 Tokyo,
cover at market at 11:55 Tokyo, disaster stop 3 x ATR(24) of hourly bars.  Fallback `B7_tokyo_gotobi_fri`: the same
on gotobi days or Fridays.  Tokyo has no daylight saving time: 09:55 Tokyo = 00:55 UTC.

    python3 r2/tracks/fx/tokyo.py is       # in sample (2013-2021) on a grid of all-in costs; nothing after 2021 is read
    python3 r2/tracks/fx/tokyo.py dry B6_tokyo_gotobi 0.95     # the validation code path on the in-sample frame (dry run)
    python3 r2/tracks/fx/tokyo.py val B6_tokyo_gotobi 0.95     # the lead's single look, at the measured cost (logged)
"""
import json
import math
import os
import sys

import holidays
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import strategy as S  # noqa: E402
import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
from goldlab.metrics import report  # noqa: E402
from goldlab.sim import apply_spread_mult, simulate  # noqa: E402

SYM = "usdjpy"
FRAME_BP = 0.7115                                   # all-in cost of the lab frame, constant in basis points
GRID = (0.7115, 0.80, 0.90, 0.95, 1.00, 1.10, 1.20, 1.40)
RULES = {"B6_tokyo_gotobi": dict(days="gotobi", entry="09:55", exit="11:55", stop_atr=3.0, atr_n=24),
         "B7_tokyo_gotobi_fri": dict(days="gotobi_fri", entry="09:55", exit="11:55", stop_atr=3.0, atr_n=24)}
_JP = holidays.country_holidays("JP", years=range(2012, 2027))
BOJ = {pd.Timestamp(d) for v in json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "boj_decisions.json"))).values()
       for d in v}


def bank_day(d):
    return d.dayofweek < 5 and d.date() not in _JP and (d.month, d.day) not in ((12, 31), (1, 2), (1, 3))


def gotobi(start="2013-01-01", end="2026-01-01"):
    out = set()
    for per in pd.period_range(start, pd.Timestamp(end) - pd.Timedelta(days=1), freq="M"):
        for dd in (5, 10, 15, 20, 25, per.days_in_month):
            d = pd.Timestamp(per.year, per.month, dd)
            while not bank_day(d):
                d -= pd.Timedelta(days=1)
            out.add(d)
    return pd.DatetimeIndex(sorted(out))


def trade_days(kind, start="2013-01-01", end="2026-01-01"):
    g = set(gotobi(start, end))
    if kind == "gotobi_fri":
        fr = pd.date_range(start, pd.Timestamp(end) - pd.Timedelta(days=1), freq="W-FRI")
        g |= {d for d in fr if bank_day(d)}
    elif kind == "bank_days":                      # diagnostic only (mechanism check)
        g = {d for d in pd.bdate_range(start, pd.Timestamp(end) - pd.Timedelta(days=1)) if bank_day(d)}
    elif kind == "holidays":                       # diagnostic only: weekdays on which Japanese banks are closed
        g = {d for d in pd.bdate_range(start, pd.Timestamp(end) - pd.Timedelta(days=1)) if not bank_day(d)}
    elif kind != "gotobi":
        raise ValueError(kind)
    if kind in ("gotobi", "gotobi_fri"):
        g -= BOJ
    return pd.DatetimeIndex(sorted(d for d in g if pd.Timestamp(start) <= d < pd.Timestamp(end)))


def _utc(days, hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    return (days + pd.Timedelta(hours=h - 9, minutes=m)).values.astype("datetime64[ns]")


def make_orders(m1, days="gotobi", entry="09:55", exit="11:55", stop_atr=3.0, atr_n=24, max_delay_min=5):
    idx = S._idx(m1)
    d = trade_days(days)
    d = d[(d >= pd.Timestamp(idx[0]).normalize()) & (d <= pd.Timestamp(idx[-1]).normalize())]
    tdec, texit = _utc(d, entry), _utc(d, exit)
    atr = S._atr_at(m1, idx, tdec, atr_n)
    p = {"max_delay_min": max_delay_min, "sides": "both", "stop_atr": stop_atr}
    return S._market(m1, p, idx, tdec, texit, np.full(len(d), -1, np.int64), atr)


def at_cost(base, bp):
    """The frame with its all-in cost scaled to `bp` basis points (the intraday shape is kept)."""
    return base if abs(bp - FRAME_BP) < 1e-9 else apply_spread_mult(base, bp / FRAME_BP)


def _eval(name, params, bp, base, log=False, null=False):
    r2._fp_cache[SYM] = at_cost(base, bp)
    ev, tr = C.evaluate(SYM, make_orders, params, full=True)
    if log:
        r2.log_trial("fx", SYM, {"name": name, "cost_bp": bp, **params}, ev)
    t = tr["fp"]
    out = {"n": ev["is"]["n"], "pf": ev["is"]["pf"], "t": ev["is"]["t_stat"], "exp_R": ev["is"]["expectancy_R"],
           "years_pos": ev["is"]["years_pos"], "bps_net": ev["is_bps_per_trade"], "bps_gross": ev["is_gross_bps_per_trade"],
           "stress_pf": ev["is_stress"]["pf"], "win_pct": round(float((t.pnl > 0).mean() * 100), 1),
           "stops": int((t.reason == "stop").sum()), "by_year_R": ev["is"].get("by_year_R")}
    if null:
        nt = r2.null_test(SYM, make_orders, params, n_seeds=200, mode="time")
        out["null_percentile"] = nt.get("percentile")
        out["null_mean_R"] = nt.get("null_mean_R")
    return ev, out


def run_is():
    base = C.load_is(SYM)
    res = {"sym": SYM, "frame_cost_bp": FRAME_BP, "rules": RULES, "gotobi_days_skipped_for_boj_is": len(set(gotobi("2013-01-01", "2022-01-01")) & BOJ),
           "grid": {}}
    for name, params in RULES.items():
        res["grid"][name] = []
        for bp in GRID:
            first = abs(bp - FRAME_BP) < 1e-9
            ev, o = _eval(name, params, bp, base, log=first, null=bp in (FRAME_BP, 0.95, 1.20))
            nb = []
            if name == "B6_tokyo_gotobi":
                for ch in (dict(entry="09:50"), dict(entry="10:00"), dict(exit="11:00"), dict(exit="13:00"), dict(exit="15:00")):
                    evn, on = _eval(name + ":neighbour", dict(params, **ch), bp, base, log=first)
                    nb.append({"change": ch, "pf": on["pf"], "t": on["t"], "bps_net": on["bps_net"]})
                o["neighbours"] = nb
                o["neighbours_median_pf"] = float(np.median([x["pf"] for x in nb]))
            c = r2.is_criteria(ev, o.get("neighbours_median_pf"))
            if "null_percentile" in o:
                c["null>=97.5"] = bool(o["null_percentile"] >= 97.5)
                c["pass"] = bool(all(v for k, v in c.items() if k != "pass"))
            o["cost_bp"], o["criteria"] = bp, c
            res["grid"][name].append(o)
            print(f"{name:20s} cost {bp:5.2f} bp | n {o['n']} PF {o['pf']:.2f} t {o['t']:.2f} R/trade {o['exp_R']:+.3f} net {o['bps_net']:+.2f} bp "
                  f"(gross {o['bps_gross']:+.2f}) win {o['win_pct']}% years {o['years_pos']} stressPF {o['stress_pf']:.2f} "
                  f"nbPF {o.get('neighbours_median_pf', float('nan')):.2f} null {o.get('null_percentile', '-')} | "
                  f"{'PASS' if c['pass'] else 'no'} {[k for k, v in c.items() if not v and k != 'pass']}", flush=True)
    # mechanism, in sample: fall of the mid from 09:55 to 10:05 Tokyo on bank business days vs bank holidays
    mid = ((base.bo + base.ao) / 2)
    res["mechanism_is"] = mechanism(mid, "2013-01-01", "2022-01-01")
    print("mechanism (in sample):", res["mechanism_is"], flush=True)
    r2.free()
    C.save(res, "tokyo_is.json")
    return res


def mechanism(mid, start, end):
    idx = mid.index.tz_convert("UTC").tz_localize(None)
    s = pd.Series(mid.to_numpy(), index=idx)
    out = {}
    for kind in ("bank_days", "holidays", "gotobi"):
        d = trade_days(kind, start, end)
        a = s.reindex(d + pd.Timedelta(minutes=55))
        b = s.reindex(d + pd.Timedelta(minutes=65))
        x = (-(b.to_numpy() / a.to_numpy() - 1) * 1e4)
        x = x[np.isfinite(x)]
        out[kind] = {"n": int(len(x)), "fall_bp": round(float(x.mean()), 2) if len(x) else None,
                     "t": round(float(x.mean() / x.std(ddof=1) * math.sqrt(len(x))), 2) if len(x) > 2 else None}
    return out


def run_val(name, bp, period="val"):
    """period="val": the lead's single look at 2022-2025 (addendum D and its clarification), at the measured all-in
    cost `bp`; logged. period="is": the same code path on the in-sample frame (dry run, nothing logged or saved)."""
    bp = float(bp)
    val = period == "val"
    a, b = ("2022-01-01", "2026-01-01") if val else ("2013-01-01", "2022-01-01")
    params = RULES[name]
    r2.free()
    base = r2.load(SYM) if val else C.load_is(SYM)
    f = at_cost(base, bp)
    lab = f"{name}:lead_single_look:cost_{bp:g}bp"

    def cut(t, suffix=""):
        return gl.cut(t, "val", track="fx", label=lab + suffix) if val else gl.cut(t, "is")

    def sim(frame, prm, stress=1.0):
        return simulate(frame, make_orders(frame, **prm), sym=SYM, costs=r2.costs(SYM, stress), no_overlap=True)

    t = cut(sim(f, params))
    ts = cut(sim(apply_spread_mult(f, 1.5), params, 1.5), ":stress")
    r = report(t)
    bp_net = t.pnl / t.entry * 1e4
    day = t.entry_time.dt.tz_convert("UTC").dt.tz_localize(None).dt.normalize()
    by_day = bp_net.groupby(day).sum()
    wo_best = bp_net.drop(bp_net.idxmax())
    yp, yn = (int(x) for x in r["years_pos"].split("/"))
    mech = mechanism((base.bo + base.ao) / 2, a, b)
    c = {"mean>0": float(bp_net.mean()) > 0, "t>=1.5": r["t_stat"] >= 1.5, "pf>=1.06": r["pf"] >= 1.06, "years_pos>=75%": yp >= 0.75 * yn,
         "positive_without_best_day": float(wo_best.mean()) > 0,
         "mechanism_t>=3": (mech["bank_days"]["t"] or 0) >= 3,
         "absent_on_holidays": (mech["holidays"]["t"] is None) or mech["holidays"]["t"] < 2}
    c["pass"] = all(c.values())
    # diagnostics declared as NON-criteria in the clarification of addendum D
    diag = {"t_on_bp_fixed_lot": round(float(bp_net.mean() / bp_net.std(ddof=1) * math.sqrt(len(bp_net))), 2)}
    x25 = t[~((t.entry_time.dt.month == 12) & (t.entry_time.dt.day == 25))]
    r25 = report(x25)
    diag["without_25_december"] = {"n": r25["n"], "pf": r25["pf"], "t": r25["t_stat"], "net_bp": round(float((x25.pnl / x25.entry).mean() * 1e4), 2)}
    for e in ("09:54", "09:56"):
        td = cut(sim(f, dict(params, entry=e)), ":diag_entry_" + e)
        rd = report(td)
        diag["entry_" + e] = {"n": rd["n"], "pf": rd["pf"], "t": rd["t_stat"], "net_bp": round(float((td.pnl / td.entry).mean() * 1e4), 2)}
    out = {"name": name, "period": period, "cost_bp": bp, "params": params,
           "result": {k: r.get(k) for k in ("n", "pf", "t_stat", "expectancy_R", "total_R", "years_pos", "by_year_R", "win_rate")},
           "net_bp_per_trade": round(float(bp_net.mean()), 2), "net_bp_without_best_day": round(float(wo_best.mean()), 2),
           "best_day": str(by_day.idxmax().date()), "stress": {k: report(ts).get(k) for k in ("pf", "expectancy_R", "t_stat")},
           "mechanism": mech, "criteria": c, "diagnostics_not_criteria": diag}
    if val:
        t[[k for k in ("side", "entry_time", "exit_time", "entry", "exit", "stop", "reason", "pnl", "risk", "R") if k in t.columns]].to_parquet(
            os.path.join(C.OUT, f"trades_{name}_val.parquet"))
        C.save(out, f"tokyo_val_{name}.json")
    print(json.dumps(out, indent=1, default=str))
    r2.free()
    return out


if __name__ == "__main__":
    if sys.argv[1] == "is":
        run_is()
    elif sys.argv[1] == "val":
        run_val(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == "dry":                     # same code path on the in-sample frame, nothing logged
        run_val(sys.argv[2], sys.argv[3], period="is")
