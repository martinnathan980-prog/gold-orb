"""Standard evaluation used by every track: IS report, cost stress, pass/fail vs PROTOCOL.md."""
from dataclasses import replace

from .metrics import report
from .sim import COSTS, Costs, simulate
from .split import cut


def stressed_costs(sym="xauusd", k=1.5):
    c = COSTS.get(sym, Costs())
    return replace(c, commission=c.commission * k, slip_bps=c.slip_bps * k, spread_mult=k)


def evaluate_is(m1, orders, sym="xauusd", no_overlap=True):
    """Simulate once with normal costs and once with costs x1.5; return (trades, rep, rep_stress)
    restricted to the in-sample period."""
    t = simulate(m1, orders, sym=sym, no_overlap=no_overlap)
    ts = simulate(m1, orders, sym=sym, costs=stressed_costs(sym), no_overlap=no_overlap)
    return t, report(cut(t, "is")), report(cut(ts, "is"))


def is_criteria(rep, rep_stress=None):
    """Pre-registered in-sample criteria (PROTOCOL.md section 2)."""
    if rep.get("n", 0) == 0:
        return {"pass": False}
    yp, yn = (int(x) for x in rep["years_pos"].split("/"))
    c = {
        "n>=200": rep["n"] >= 200,
        "pf>=1.20": rep["pf"] >= 1.20,
        "t>=2": rep["t_stat"] >= 2.0,
        "years_pos>=2/3": yp >= 2 * yn / 3,
        "freq 25-750/yr": 25 <= rep["trades_per_year"] <= 750,
        "max_hold<=5d": rep["max_hold_h"] <= 5 * 24 + 72,  # 5 trading days (+ weekend)
    }
    if rep_stress is not None:
        c["stress_pf>=1.05"] = rep_stress.get("pf", 0) >= 1.05
    c["pass"] = all(c.values())
    return c


def val_criteria(rep_val):
    """Pre-registered validation criteria (2022-2025, single pre-chosen config)."""
    if rep_val.get("n", 0) == 0:
        return {"pass": False}
    c = {"pf>=1.10": rep_val["pf"] >= 1.10, "expectancy>0": rep_val["expectancy_R"] > 0}
    c["pass"] = all(c.values())
    return c
