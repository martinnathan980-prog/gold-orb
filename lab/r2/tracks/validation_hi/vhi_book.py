"""validation_hi -- the account: the sleeves' trades assembled into one book, with stakes, plain or capped.

CLOCK (the one of stake.py, the cluster lens, synthesis_B and the sizing lenses): FP server time = New York + 7 h;
server day; server week Monday..Sunday; a trade's stake x R is booked in the day / week of its EXIT time.

PLAIN SUM   every trade of every sleeve's own one-position chain, stake m x R (m from the stake rule; m = 0: not
            taken). synthesis_B's P0..P3 and the sizing lenses' account.
CAPPED      the same trades offered in entry order (ties in one minute: ASCII order of "<rule>_<sym>", as stake.py,
            account.py and the cluster engine) to an account that holds at most 6 positions and 2 per market
            (r2/tracks/stake/account.py LIMITS); a position is open for a new entry until its exit time is STRICTLY
            before the entry time; m = 0 takes no slot; a trade not taken leaves its sleeve's chain unchanged. Run
            over the whole frame (state warm at the window start), judged on the window. Checked in the proofs
            against the cluster lens's run_engine and against account.py.

METRICS
    sB(...)       synthesis_B s2_portfolio.metrics, generalised to any window [start, end): weeks from the week of
                  `start` to the week of `end - 1 minute`, every week counted (empty = 0); max drawdown trade by trade
                  in exit order and on the weekly sums; worst week / day; longest run of losing weeks; mean / sd per
                  trade and per week; weekly Sharpe x sqrt(52); by entry year; sub-windows; by sleeve.
    swing(...)    the Addendum I measures (sizing lenses): weekly Sharpe, losing weeks, worst week, longest losing
                  run, weekly drawdown, losing trades per month, at a stake scale; by year = trades entered in the
                  year over the weeks whose Thursday falls in it (the first / last week of the window are clipped
                  into its first / last year, so no exit inside the window is lost).
    equal_swing   the variant's stakes scaled so that its weekly standard deviation over the judged window equals
                  the reference's; every amount reported at that scale.
"""
import numpy as np
import pandas as pd

NY = "America/New_York"
CAP_TOTAL, CAP_MKT = 6, 2


def server_time(ts):
    return pd.DatetimeIndex(ts).tz_convert(NY).tz_localize(None) + pd.Timedelta(hours=7)


def server_day(ts):
    return server_time(ts).values.astype("datetime64[D]").astype(np.int64)


def week_id(ts):
    return (server_day(ts) + 3) // 7                 # 1970-01-01 is a Thursday: weeks start on Monday


def week_thursday_year(w):
    return pd.DatetimeIndex((np.asarray(w, np.int64) * 7).astype("datetime64[D]")).year.to_numpy()


def week_range(start, end):
    w0 = int(week_id(pd.DatetimeIndex([start]))[0])
    w1 = int(week_id(pd.DatetimeIndex([end - pd.Timedelta(minutes=1)]))[0])
    return np.arange(w0, w1 + 1)


def weeks_of_year(Y, start, end):
    """Weeks of the window whose Thursday falls in Y; the window's first and last weeks are clipped into its first and
    last year."""
    ws = week_range(start, end)
    y = week_thursday_year(ws)
    y0, y1 = start.year, (end - pd.Timedelta(nanoseconds=1)).year
    y = np.clip(y, y0, y1)
    return ws[y == Y]


# ------------------------------------------------------------------------------------------------- book
def make_book(per_sleeve, start=None, end=None):
    """per_sleeve: {sleeve key: (trades, stakes or None, meta)} with meta = {"sym", "tie"}. Returns one frame with
    sleeve, sym, tie, side, entry_time, exit_time, R, m (stake), Rm = m x R, risk, entry, pnl; window on entry_time
    [start, end) when given; sorted by exit time, entry time, sleeve (synthesis_B's book order)."""
    fr = []
    for k, (t, m, meta) in per_sleeve.items():
        if t is None or not len(t):
            continue
        mm = np.ones(len(t)) if m is None else np.asarray(m, float)
        assert len(mm) == len(t)
        fr.append(pd.DataFrame({"sleeve": k, "sym": meta["sym"], "tie": meta.get("tie", k),
                                "oid": t["oid"].to_numpy() if "oid" in t else np.arange(len(t)),
                                "side": t.side.to_numpy(np.int64),
                                "entry_time": pd.DatetimeIndex(t.entry_time).tz_convert("UTC").as_unit("ns"),
                                "exit_time": pd.DatetimeIndex(t.exit_time).tz_convert("UTC").as_unit("ns"),
                                "R": t.R.to_numpy(float), "m": mm,
                                "risk": t.risk.to_numpy(float) if "risk" in t else np.nan,
                                "entry": t.entry.to_numpy(float) if "entry" in t else np.nan,
                                "pnl": t.pnl.to_numpy(float) if "pnl" in t else np.nan}))
    d = pd.concat(fr, ignore_index=True)
    if start is not None:
        d = d[(d.entry_time >= start) & (d.entry_time < end)]
    d["Rm"] = d.m * d.R
    return d.sort_values(["exit_time", "entry_time", "sleeve"], kind="stable").reset_index(drop=True)


def capped_stakes(d, cap_total=CAP_TOTAL, cap_mkt=CAP_MKT):
    """The capped account on book d (whole frame, any order). Returns (m_taken aligned with d, why) where why is
    0 taken, 1 stake 0, 2 position cap."""
    order = np.lexsort((d.tie.to_numpy().astype(str), d.entry_time.astype("int64").to_numpy()))
    t_in = d.entry_time.astype("int64").to_numpy()
    t_out = d.exit_time.astype("int64").to_numpy()
    sym = d.sym.to_numpy().astype(str)
    m = d.m.to_numpy(float)
    out_m = np.zeros(len(d))
    why = np.zeros(len(d), np.int64)
    open_ = []                                   # (t_out, sym) of the positions taken
    for i in order:
        ti = t_in[i]
        if open_:
            open_ = [p for p in open_ if not (p[0] < ti)]
        if m[i] <= 0.0:
            why[i] = 1
            continue
        if len(open_) >= cap_total or sum(1 for p in open_ if p[1] == sym[i]) >= cap_mkt:
            why[i] = 2
            continue
        open_.append((t_out[i], sym[i]))
        out_m[i] = m[i]
    return out_m, why


def apply_account(d_all, account, start, end):
    """Book of the account kind ('sum' | 'capped') judged on [start, end): only taken trades (m > 0)."""
    d = d_all.copy()
    if account == "capped":
        mc, why = capped_stakes(d)
        d["why"] = why
        d["m"] = mc
    elif account != "sum":
        raise ValueError(account)
    d = d[(d.entry_time >= start) & (d.entry_time < end)]
    d = d[d.m > 0].copy()
    d["Rm"] = d.m * d.R
    return d.sort_values(["exit_time", "entry_time", "sleeve"], kind="stable").reset_index(drop=True)


# ------------------------------------------------------------------------------------------------- statistics
def sstats(R):
    """synthesis_B common.sstats (same rounding)."""
    R = np.asarray(R, float)
    R = R[np.isfinite(R)]
    n = len(R)
    if n == 0:
        return {"n": 0}
    w, l = R[R > 0], R[R < 0]
    return {"n": int(n), "exp": round(float(R.mean()), 4), "total": round(float(R.sum()), 2),
            "win": round(float((R > 0).mean()), 4), "avg_win": round(float(w.mean()), 4) if len(w) else 0.0,
            "avg_loss": round(float(l.mean()), 4) if len(l) else 0.0,
            "pf": round(float(w.sum() / -l.sum()), 3) if len(l) and l.sum() < 0 else None,
            "sd": round(float(R.std(ddof=1)), 4) if n > 1 else None,
            "mean_over_sd": round(float(R.mean() / R.std(ddof=1)), 4) if n > 1 and R.std(ddof=1) > 0 else None}


def by_year(t, col="R"):
    if t is None or not len(t):
        return {}
    return {int(y): sstats(g[col]) for y, g in t.groupby(pd.DatetimeIndex(t.entry_time).year)}


def max_dd(x):
    c = np.r_[0.0, np.cumsum(np.asarray(x, float))]
    return float((np.maximum.accumulate(c) - c).max())


def longest_run(neg):
    best = cur = 0
    for v in neg:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return int(best)


def weekly(d, start, end, col="Rm"):
    ws = week_range(start, end)
    if not len(d):
        return pd.Series(0.0, index=ws)
    return pd.Series(d[col].to_numpy(float)).groupby(week_id(d.exit_time)).sum().reindex(ws, fill_value=0.0)


def sB(d, start, end, splits=None, name_map=None):
    """synthesis_B's s2_portfolio.metrics on book d (taken trades, Rm = stake x R), window [start, end)."""
    R = d.Rm.to_numpy(float)
    s = sstats(R)
    if not s.get("n"):
        return s
    s["eur_per_100_risked"] = round(100 * s["exp"], 2)
    stakes = float(d.m.sum())
    s["stakes"] = round(stakes, 3)
    s["exp_per_stake"] = round(float(R.sum() / stakes), 4) if stakes > 0 else None
    ws = weekly(d, start, end)
    ds = pd.Series(R).groupby(server_time(d.exit_time).normalize()).sum()
    s.update({
        "max_dd_R_trade_by_trade": round(max_dd(R), 2),
        "max_dd_R_weekly": round(max_dd(ws.to_numpy()), 2),
        "worst_week_R": round(float(ws.min()), 2), "best_week_R": round(float(ws.max()), 2),
        "weeks": int(len(ws)), "winning_weeks_pct": round(float((ws > 0).mean() * 100), 1),
        "losing_weeks_pct": round(float((ws < 0).mean() * 100), 1),
        "longest_losing_run_weeks": longest_run((ws < 0).to_numpy()),
        "week_mean_R": round(float(ws.mean()), 3), "week_sd_R": round(float(ws.std(ddof=1)), 3),
        "week_mean_over_sd": round(float(ws.mean() / ws.std(ddof=1)), 4),
        "weekly_sharpe_annualised": round(float(ws.mean() / ws.std(ddof=1) * np.sqrt(52)), 3),
        "worst_day_R": round(float(ds.min()), 2),
        "R_per_year": round(float(R.sum() / ((end - start).days / 365.25)), 1),
    })
    yy = pd.DatetimeIndex(d.entry_time).year
    s["by_year"] = {int(y): {k: v[k] for k in ("n", "exp", "total", "win", "avg_loss", "pf")}
                    for y, v in ((y, sstats(g.Rm)) for y, g in d.groupby(yy))}
    for nm, a, b in (splits or []):
        x = d[(d.entry_time >= a) & (d.entry_time < b)]
        hs = sstats(x.Rm)
        s[nm] = {k: hs.get(k) for k in ("n", "exp", "total", "win", "avg_loss", "pf", "mean_over_sd")}
    nm = name_map or {}
    s["by_sleeve"] = {nm.get(k, k): {kk: v[kk] for kk in ("n", "exp", "total")}
                      for k, v in ((k, sstats(g.Rm)) for k, g in d.groupby("sleeve"))}
    return s


def months_in(start, end):
    """Calendar months in [start, end) (exact when both are month starts, else days / 30.44)."""
    if start == start.normalize() and end == end.normalize() and start.day == 1 and end.day == 1:
        return int((end.year - start.year) * 12 + (end.month - start.month))
    return int(round((end - start).days / (365.25 / 12)))


def swing(d, start, end, scale=1.0, years=None):
    """Addendum I measures of book d on [start, end) at a stake scale (sizing lenses' `measures`)."""
    ws = weekly(d, start, end) * scale
    x = ws.to_numpy()
    los = int((d.R < 0).sum())
    months = months_in(start, end)
    sd = float(x.std(ddof=1)) if len(x) > 1 else float("nan")
    out = {"weeks": int(len(x)), "weekly_sharpe": round(float(x.mean() / sd * np.sqrt(52)), 4) if sd > 0 else None,
           "week_mean": round(float(x.mean()), 4), "week_sd": round(sd, 4), "total_R": round(float(x.sum()), 2),
           "losing_weeks_pct": round(float((x < 0).mean() * 100), 1), "worst_week_R": round(float(x.min()), 2),
           "longest_losing_run_weeks": longest_run(x < 0), "max_dd_weekly_R": round(max_dd(x), 2),
           "trades_taken": int(len(d)), "losing_trades": los, "months": months,
           "losing_trades_per_month": round(los / months, 1) if months else None,
           "trades_per_month": round(len(d) / months, 1) if months else None,
           "mean_stake_of_taken": round(float(d.m.mean()), 4) if len(d) else None}
    if years:
        out["by_year"] = {}
        for Y in years:
            dy = d[pd.DatetimeIndex(d.entry_time).year == Y]
            wsy = weeks_of_year(Y, start, end)
            sy = pd.Series(dy.Rm.to_numpy(float)).groupby(week_id(dy.exit_time)).sum().reindex(wsy, fill_value=0.0) \
                * scale if len(dy) else pd.Series(0.0, index=wsy)
            xy = sy.to_numpy()
            sdy = float(xy.std(ddof=1)) if len(xy) > 1 else float("nan")
            out["by_year"][int(Y)] = {"weeks": int(len(xy)), "weekly_sharpe": round(float(xy.mean() / sdy * np.sqrt(52)), 4)
                                      if sdy > 0 else None, "total_R": round(float(xy.sum()), 2),
                                      "trades_taken": int(len(dy)), "worst_week_R": round(float(xy.min()), 2) if len(xy) else None}
    return out


def equal_swing(ref, var, start, end, years=None):
    """Reference and variant books on [start, end); the variant scaled to the reference's weekly sd."""
    sd_ref = float(weekly(ref, start, end).std(ddof=1))
    sd_var = float(weekly(var, start, end).std(ddof=1))
    k = sd_ref / sd_var if sd_var > 0 else float("nan")
    out = {"scale_k": round(k, 4), "max_effective_stake": round(k * float(var.m.max()), 4) if len(var) else None,
           "ref": swing(ref, start, end, 1.0, years), "var_raw": swing(var, start, end, 1.0, years),
           "var_equal_swing": swing(var, start, end, k, years)}
    rs, vs = out["ref"]["weekly_sharpe"], out["var_equal_swing"]["weekly_sharpe"]
    out["sharpe_ratio"] = round(vs / rs, 4) if rs else None
    if years:
        out["years_up"] = int(sum(1 for Y in years if out["var_equal_swing"]["by_year"][Y]["weekly_sharpe"] is not None
                                  and out["ref"]["by_year"][Y]["weekly_sharpe"] is not None
                                  and out["var_equal_swing"]["by_year"][Y]["weekly_sharpe"]
                                  > out["ref"]["by_year"][Y]["weekly_sharpe"]))
    return out
