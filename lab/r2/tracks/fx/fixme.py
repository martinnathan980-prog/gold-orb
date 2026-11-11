"""Track `fx`, PROTOCOL_V3 addendum B: month-end London fix reversal signed by the S&P 500 month-to-date.

Frozen rule `B5_fix_me_spx` (see the addendum for the mechanism and the pass rules):
  date    last weekday of the calendar month that is neither an England bank holiday nor a NYSE holiday
  sign    official S&P 500 closes: previous session's close above the last close of the previous calendar month
          -> buy dollars against the six currencies; below -> sell dollars
  entry   market, open of the first M1 bar at/after 16:02 London (at most 5 minutes late)
  stop    1.5 x ATR(24) of complete hourly mid bars, from the fill;  exit  market at 16:30 London

    python3 r2/tracks/fx/fixme.py is        # in-sample run, neighbours, null (frames cut at 2022-01-15)
    python3 r2/tracks/fx/fixme.py dry       # the validation code path on the in-sample frames (no 2022+ data read)
    python3 r2/tracks/fx/fixme.py val       # the lead's single validation look (logged)

S&P 500 closes: column `price` of https://squeezemetrics.com/monitor/static/DIX.csv saved as data/ext/DIX.csv.
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
from goldlab.sim import apply_spread_mult, simulate  # noqa: E402

SIX = ["eurusd", "gbpusd", "audusd", "nzdusd", "usdcad", "usdchf"]
NAME = "B5_fix_me_spx"
FROZEN = dict(dec="16:02", exit="16:30", stop_atr=1.5, atr_n=24)
NEIGHBOURS = [dict(FROZEN, dec=d) for d in ("16:00", "16:01", "16:03", "16:04")] + \
             [dict(FROZEN, exit=x) for x in ("16:20", "16:45")]
SPX_FILE = os.path.join(C.LAB, "data", "ext", "DIX.csv")
_UK = holidays.country_holidays("GB", subdiv="ENG", years=range(2012, 2027))
_NY = holidays.financial_holidays("NYSE", years=range(2012, 2027))

# research override used only by the null / placebo runs: (days, usd side per day)
_OVERRIDE = None


def both_open(d):
    return d.dayofweek < 5 and d.date() not in _UK and d.date() not in _NY


def month_ends(start="2013-01-01", end="2026-01-01"):
    out = []
    for m in pd.period_range(start, pd.Timestamp(end) - pd.Timedelta(days=1), freq="M"):
        d = m.to_timestamp(how="end").normalize()
        while not both_open(d):
            d -= pd.Timedelta(days=1)
        out.append(d)
    return pd.DatetimeIndex(out)


def open_days(start, end):
    d = pd.bdate_range(start, pd.Timestamp(end) - pd.Timedelta(days=1))
    return d[[both_open(x) for x in d]]


def spx_closes(cap):
    px = pd.read_csv(SPX_FILE, parse_dates=["date"]).set_index("date")["price"]
    return px[px.index < pd.Timestamp(cap)]


def spx_mtd(days, cap, px=None):
    """S&P 500 month-to-date return known before the open of each day: previous session's close against the last
    close of the previous calendar month. `cap` = no close at or after this date is read."""
    px = spx_closes(cap) if px is None else px
    per = px.index.to_period("M")
    last_of_month = px.groupby(per).last()
    out = []
    for d in days:
        prev = px[px.index < d]
        base = last_of_month.get(d.to_period("M") - 1, np.nan)
        out.append(prev.iloc[-1] / base - 1 if len(prev) and np.isfinite(base) else np.nan)
    return pd.Series(out, index=days)


def make_orders(m1, pair=None, dec="16:02", exit="16:30", stop_atr=1.5, atr_n=24, max_delay_min=5):
    idx = S._idx(m1)
    lo = pd.Timestamp(idx[0]).normalize()
    hi = pd.Timestamp(idx[-1]).normalize()
    if _OVERRIDE is None:
        days = month_ends("2013-01-01", "2026-01-01")
        days = days[(days >= lo) & (days <= hi)]
        # the sign never reads a close later than the day before the trade (prev = closes strictly before d)
        usd = np.sign(spx_mtd(days, hi + pd.Timedelta(days=1)).to_numpy())
    else:
        days, usd = _OVERRIDE
        k = (days >= lo) & (days <= hi)
        days, usd = days[k], np.asarray(usd)[k]
    usd = np.where(np.isfinite(usd), usd, 0)
    side = (usd * S._usd_side(pair)).astype(np.int64)
    tdec, texit = S._at(days, dec), S._at(days, exit)
    atr = S._atr_at(m1, idx, tdec, atr_n)
    p = {"max_delay_min": max_delay_min, "sides": "both", "stop_atr": stop_atr}
    return S._market(m1, p, idx, tdec, texit, side, atr, extra={"usd": usd})


# ------------------------------------------------------------------------------------------------------------
def _date(t):
    return t.entry_time.dt.tz_convert(S.LDN).dt.tz_localize(None).dt.normalize()


def per_date(T):
    """Basket net bp of each date = mean over the pairs traded that date of 1e4 * pnl / entry."""
    bp = T["pnl"] / T["entry"] * 1e4
    return bp.groupby(_date(T)).mean()


def _t(x):
    x = np.asarray(x, float)
    return float(x.mean() / x.std(ddof=1) * math.sqrt(len(x))) if len(x) > 2 else float("nan")


def date_stats(T, mtd=None):
    d = per_date(T)
    bp = T["pnl"] / T["entry"] * 1e4
    by_pair = bp.groupby(T["sym"]).mean()
    by_year = d.groupby(d.index.year).mean()
    s = d.sort_values()
    out = {"dates": int(len(d)), "trades": int(len(T)), "net_bp_per_date": round(float(d.mean()), 2),
           "t_dates": round(_t(d), 2), "dates_pos_pct": round(float((d > 0).mean() * 100), 1),
           "pairs_pos": f"{int((by_pair > 0).sum())}/{len(by_pair)}",
           "by_pair_bp": {k: round(float(v), 2) for k, v in by_pair.items()},
           "years_pos": f"{int((by_year > 0).sum())}/{len(by_year)}",
           "by_year_bp": {int(k): round(float(v), 2) for k, v in by_year.items()},
           "without_best5_bp": round(float(s[:-5].mean()), 2), "worst_date_bp": round(float(s.iloc[0]), 1),
           "best_date_bp": round(float(s.iloc[-1]), 1),
           "stops": int((T["reason"] == "stop").sum()) if "reason" in T else None}
    if mtd is not None:
        m = mtd.reindex(d.index)
        up, dn = d[m > 0], d[m < 0]
        out["up_months"] = {"n": int(len(up)), "bp": round(float(up.mean()), 2), "t": round(_t(up), 2)}
        out["down_months"] = {"n": int(len(dn)), "bp": round(float(dn.mean()), 2), "t": round(_t(dn), 2)}
    return out


def _run_pair(sym, m1, params, mode, mult=1.5):
    pr = dict(params, pair=sym)
    if mode == "fp":
        t = simulate(m1, make_orders(m1, **pr), sym=sym, costs=r2.costs(sym), no_overlap=False)
    elif mode == "stress":
        mk = apply_spread_mult(m1, mult)
        t = simulate(mk, make_orders(mk, **pr), sym=sym, costs=r2.costs(sym, mult), no_overlap=False)
    else:
        mk = apply_spread_mult(m1, 0.0)
        t = simulate(mk, make_orders(mk, **pr), sym=sym, costs=r2.GROSS, no_overlap=False)
    t = t.copy()
    t["sym"] = sym
    return t


def sign_check(cap, start="2013-01-01"):
    """Diagnostic: the same sign computed from the lab's us500 frame (mid close of the last M1 bar before
    16:00 New York) against the official closes."""
    m1 = C.load_is("us500") if cap <= "2022-01-01" else r2.load("us500")
    ny = m1.index.tz_convert(gl.NY)
    k = (ny.hour * 60 + ny.minute) < 16 * 60
    mid = ((m1.bc + m1.ac) / 2)[k]
    d = pd.DatetimeIndex(ny[k].tz_localize(None).normalize())
    px = pd.Series(mid.to_numpy(), index=d).groupby(level=0).last()
    px = px[(px.index.dayofweek < 5) & (px.index < pd.Timestamp(cap))]
    days = month_ends(start, cap)
    a = np.sign(spx_mtd(days, cap))
    b = np.sign(spx_mtd(days, cap, px=px))
    ok = a.notna() & b.notna()
    diff = days[ok & (a != b)]
    r2.free("us500")
    return {"dates_compared": int(ok.sum()), "different": [str(x.date()) for x in diff]}


# ------------------------------------------------------------------------------------------------------------
def run_is():
    global _OVERRIDE
    out = {"name": NAME, "params": FROZEN, "pairs": SIX}
    res = C.basket(NAME, make_orders, FROZEN, syms=SIX, full=True, pass_pair=True, save_trades=True, tag="frozen")
    print(C.short(res), flush=True)
    print("   criteria", res["criteria"], flush=True)
    T = pd.read_parquet(os.path.join(C.OUT, f"trades_{NAME}_fp.parquet"))
    mtd = spx_mtd(month_ends("2013-01-01", "2022-01-01"), "2022-01-01")
    ds = date_stats(T, mtd)
    Tg = pd.read_parquet(os.path.join(C.OUT, f"trades_{NAME}_gross.parquet"))
    ds["gross_bp_per_date"] = round(float(per_date(Tg).mean()), 2)
    print("   per date", json.dumps(ds), flush=True)
    out.update({k: res[k] for k in ("fp", "stress", "gross", "every", "criteria")})
    out["per_date"] = ds
    # neighbours
    nb = []
    for p in NEIGHBOURS:
        r = C.basket(NAME, make_orders, p, syms=SIX, full=False, pass_pair=True, tag="neighbour")
        nb.append({"params": p, "pf": r["fp"]["pf"], "t_daily": r["fp"]["t_daily"], "bps": r["fp"]["bps_per_trade"]})
        print("   neighbour", p["dec"], p["exit"], "PF", r["fp"]["pf"], "tD", r["fp"]["t_daily"], "bp", r["fp"]["bps_per_trade"], flush=True)
    out["neighbours"] = nb
    out["neighbours_median_pf"] = float(np.median([x["pf"] for x in nb]))
    # null: every both-open weekday, both sides, simulated once per pair; then resampled
    days = open_days("2013-01-01", "2022-01-01")
    tab = {}
    for sym in SIX:
        m1 = C.load_is(sym)
        for u in (1, -1):
            _OVERRIDE = (days, np.full(len(days), u))
            t = gl.cut(_run_pair(sym, m1, FROZEN, "fp"), "is")
            tab[(sym, u)] = (t["pnl"] / t["entry"] * 1e4).groupby(_date(t)).first()
    _OVERRIDE = None
    A = pd.DataFrame({k: v for k, v in tab.items()})
    real_days = pd.DatetimeIndex(sorted(set(_date(T))))
    usd_real = T.groupby(_date(T))["side"].first() * T.groupby(_date(T))["sym"].first().map(S._usd_side)
    pool = A.index.difference(real_days)
    rng = np.random.default_rng(7)
    sides = usd_real.reindex(real_days).to_numpy()
    up = A.xs(1, axis=1, level=1).mean(axis=1)
    dn = A.xs(-1, axis=1, level=1).mean(axis=1)
    null = []
    for _ in range(1000):
        pick = rng.choice(len(pool), size=len(real_days), replace=False)
        dd = pool[pick]
        null.append(float(np.nanmean(np.where(sides > 0, up.reindex(dd).to_numpy(), dn.reindex(dd).to_numpy()))))
    real = float(per_date(T).mean())
    null = np.array(null)
    out["null"] = {"real_bp": round(real, 2), "null_mean_bp": round(float(null.mean()), 2),
                   "null_p95_bp": round(float(np.quantile(null, 0.95)), 2),
                   "null_p975_bp": round(float(np.quantile(null, 0.975)), 2),
                   "percentile": round(float((null < real).mean() * 100), 1),
                   "other_days_buy_usd_bp": round(float(up.reindex(pool).mean()), 2),
                   "other_days_sell_usd_bp": round(float(dn.reindex(pool).mean()), 2)}
    print("   null", out["null"], flush=True)
    out["sign_check_us500_frame"] = sign_check("2022-01-01")
    print("   sign check", out["sign_check_us500_frame"], flush=True)
    c = dict(res["criteria"])
    c["neighbours_median_pf>=1.06"] = out["neighbours_median_pf"] >= 1.06
    c["null>=97.5"] = out["null"]["percentile"] >= 97.5
    c["pass"] = all(v for k, v in c.items() if k != "pass")
    out["is_criteria"] = c
    print("   IS criteria", c, flush=True)
    C.save(out, f"{NAME}_is.json")
    return out


def look(period):
    """period="val": the lead's single look at 2022-2025 (PROTOCOL_V3 addendum B), logged in results/val_access.log.
    period="is": the same code path on the in-sample frames (dry run; must give the figures of run_is)."""
    val = period == "val"
    a, b = ("2022-01-01", "2026-01-01") if val else ("2013-01-01", "2022-01-01")
    pools = {"fp": [], "x2": [], "x15": []}
    for sym in SIX:
        if val:
            r2.free()
            m1 = r2.load(sym)
        else:
            m1 = C.load_is(sym)
        for k, mode, mult in (("fp", "fp", 1.0), ("x2", "stress", 2.0), ("x15", "stress", 1.5)):
            t = _run_pair(sym, m1, FROZEN, mode, mult)
            pools[k].append(gl.cut(t, "val", track="fx", label=f"{NAME}:lead_single_look:{sym}:{k}") if val else gl.cut(t, "is"))
    r2.free()
    T = {k: pd.concat(v, ignore_index=True) for k, v in pools.items()}
    if val:
        keep = ["sym", "side", "entry_time", "exit_time", "entry", "exit", "stop", "reason", "pnl", "risk", "R", "usd"]
        T["fp"][[c for c in keep if c in T["fp"].columns]].to_parquet(os.path.join(C.OUT, f"trades_{NAME}_val.parquet"))
    mtd = spx_mtd(month_ends(a, b), b)
    ds = date_stats(T["fp"], mtd)
    pooled = C.pooled(T["fp"])
    x2 = float(per_date(T["x2"]).mean())
    yp = int(ds["years_pos"].split("/")[0])
    yn = int(ds["years_pos"].split("/")[1])
    pp = int(ds["pairs_pos"].split("/")[0])
    ypr = int(pooled["years_pos"].split("/")[0])
    c = {"net>=1.5bp": ds["net_bp_per_date"] >= 1.5, "t_dates>=2.0": ds["t_dates"] >= 2.0,
         "dates_pos>=60%": ds["dates_pos_pct"] >= 60.0, "pairs_pos>=5/6": pp >= 5, "years_pos>=75%": yp >= 0.75 * yn,
         "costs_x2>0": x2 > 0, "pooled_pf>=1.06": pooled["pf"] >= 1.06, "expectancy_R>0": pooled["expectancy_R"] > 0,
         "years_pos_R>=75%": ypr >= 0.75 * yn}
    c["pass"] = all(c.values())
    out = {"name": NAME, "period": period, "params": FROZEN, "per_date": ds, "pooled_R": pooled,
           "costs_x2_bp_per_date": round(x2, 2), "costs_x1.5_pooled": C.pooled(T["x15"]),
           "criteria": c, "sign_check_us500_frame": sign_check(b, start=a)}
    if val:
        C.save(out, f"{NAME}_val.json")
    print(json.dumps(out, indent=1, default=str))
    return out


if __name__ == "__main__":
    {"is": run_is, "dry": lambda: look("is"), "val": lambda: look("val")}[sys.argv[1]]()
