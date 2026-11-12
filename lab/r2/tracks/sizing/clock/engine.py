"""Part 2 engine of the clock lens: multipliers of a declared variant, skip sets, the portfolio book and the
equal-swing measure of declared.json. Frames are only needed to re-simulate the chains of skip variants
(resim_symbol); everything else works from the base tables of s1_build.py."""
import os

import numpy as np
import pandas as pd

import common as C
import fits as F

FOLDS = (2018, 2019, 2020, 2021)
YEARS_ALL = (2018, 2019, 2020, 2021)


def chain(k, mode):
    ch = pd.read_parquet(os.path.join(C.BASE, f"{k}__{mode}__chain.parquet"))
    assert (ch.entry_time < C.IS_END).all() and (ch.exit_time < C.IS_END).all()
    return ch


def signals(k, mode):
    s = pd.read_parquet(os.path.join(C.BASE, f"{k}__{mode}__signals.parquet"))
    return s


def all_fits(chains, mode):
    """{(unit, dim, year): fit} for sleeves (unit = key) and families (unit = 'fam:<name>'), one cost mode"""
    out = {}
    fams = {}
    for k in C.KEYS:
        if k not in C.NO_WEEKDAY:
            fams.setdefault(C.FAMILY[k], []).append(k)
        for dim in ("H", "D"):
            for Y in FOLDS:
                out[(k, dim, Y)] = F.fit_fold(chains[k], k, dim, Y)
    for fam, ks in fams.items():
        for Y in FOLDS:
            out[(f"fam:{fam}", "D", Y)] = F.fit_fold(None, ks[0], "D", Y, [(kk, chains[kk]) for kk in ks])
    return out


def multipliers(k, times, spec, fits):
    """multiplier of each fill time (UTC) of sleeve k under variant spec; plus the per-year decisions"""
    times = pd.DatetimeIndex(times)
    yrs = times.year.to_numpy()
    low = np.ones(len(times))          # smallest multiplier < 1 selected by a 'worst' part
    has_low = np.zeros(len(times), bool)
    high = np.zeros(len(times), bool)  # selected by a 'best' part
    dec = []
    for part in spec["parts"]:
        dim = part["dim"]
        cc = F.cells(k, times, dim)
        if cc is None:
            continue
        unit = f"fam:{C.FAMILY[k]}" if part.get("family") else k
        for Y in FOLDS:
            fit = fits.get((unit, dim, Y))
            if part["rule"] == "worst":
                cell, _ = F.decide(fit, "worst", T=part["T"])
                if cell is None:
                    continue
                m = (yrs == Y) & (cc == cell)
                low[m] = np.minimum(low[m], part["m"])
                has_low[m] = True
            else:
                cell, _ = F.decide(fit, "best", F=part["F"])
                if cell is None:
                    continue
                m = (yrs == Y) & (cc == cell)
                high[m] = True
            dec.append({"part": f"{part['rule']}{dim}{'(family)' if part.get('family') else ''}", "year": Y,
                        "cell": int(cell)})
    mult = np.where(has_low, low, np.where(high, 1.5, 1.0))
    return mult, dec


def skip_set(k, sig, spec, fits):
    """oids of the orders removed by a skip variant: filled alone, fill time in a cell whose multiplier is 0"""
    s = sig[sig.filled].copy()
    mult, _ = multipliers(k, s.fill_time, spec, fits)
    return set(s.oid[mult == 0.0].tolist())


def is_skip(spec):
    return any(p["rule"] == "worst" and p["m"] == 0.0 for p in spec["parts"])


def resim_symbol(sym, m1, leader, jobs):
    """jobs: list of (vid, key, mode, skip_oids). Re-simulates each sleeve chain without the skipped orders and saves
    it to results/.../variants/<vid>__<key>__<mode>.parquet. Returns {(vid, key, mode): info}."""
    info = {}
    by_mode = {}
    for job in jobs:
        by_mode.setdefault(job[2], []).append(job)
    for mode, js in by_mode.items():
        mk = C.mode_frame(m1, mode)
        costs = C.mode_costs(sym, mode)
        orders = {}
        for vid, k, _, skip in js:
            rule = k.split("__")[0]
            if rule not in orders:
                orders[rule] = C.build_orders(rule, mk, leader)
            o = orders[rule]
            t = C.simulate_filtered(mk, o[~o.oid.isin(skip)], sym, costs)
            nref = t.attrs["refused_3spreads"]
            t = C.drop_boundary(t, mk)
            cols = ["oid", "side", "entry_time", "exit_time", "entry", "exit", "stop", "reason", "swap", "pnl", "risk",
                    "R", "hold_min"]
            t = t[cols].reset_index(drop=True)
            t.to_parquet(os.path.join(C.VAR, f"{vid}__{k}__{mode}.parquet"))
            info[(vid, k, mode)] = {"skipped_orders": len(skip), "refused_3spreads": int(nref), "n": int(len(t))}
        del mk
    return info


def variant_chain(vid, k, mode, spec):
    if is_skip(spec):
        p = os.path.join(C.VAR, f"{vid}__{k}__{mode}.parquet")
        t = pd.read_parquet(p)
        assert (t.entry_time < C.IS_END).all() and (t.exit_time < C.IS_END).all()
        return t
    return chain(k, mode)


def book(per_sleeve, years):
    """trades of every sleeve with fill time in `years`: columns sleeve, entry_time, exit_time, R, mult, pnl = mult x R"""
    fr = []
    for k, (t, mult) in per_sleeve.items():
        y = t.entry_time.dt.year.to_numpy()
        m = np.isin(y, list(years))
        fr.append(pd.DataFrame({"sleeve": k, "entry_time": t.entry_time.to_numpy()[m],
                                "exit_time": t.exit_time.to_numpy()[m], "R": t.R.to_numpy(float)[m],
                                "mult": np.asarray(mult, float)[m]}))
    d = pd.concat(fr, ignore_index=True)
    d["entry_time"] = pd.to_datetime(d.entry_time, utc=True)
    d["exit_time"] = pd.to_datetime(d.exit_time, utc=True)
    d["pnl"] = d.mult * d.R
    return d


def measures(d, years, scale=1.0, months=None):
    """weekly measures of a book at a stake scale (scale multiplies every pnl)"""
    ws = C.weekly(d, years) * scale
    x = ws.to_numpy()
    taken = d.mult > 0
    los = int(((d.R < 0) & taken).sum())
    months = months if months is not None else 12 * len(years)
    out = {"weeks": int(len(x)), "weekly_sharpe": round(C.sharpe(x), 4), "week_mean": round(float(x.mean()), 4),
           "week_sd": round(float(x.std(ddof=1)), 4), "total_R": round(float(x.sum()), 2),
           "losing_weeks_pct": round(float((x < 0).mean() * 100), 1), "worst_week_R": round(float(x.min()), 2),
           "longest_losing_run_weeks": C.longest_run(x < 0), "max_dd_weekly_R": round(C.max_dd(x), 2),
           "trades_taken": int(taken.sum()), "losing_trades": los, "losing_trades_per_month": round(los / months, 1),
           "trades_per_month": round(int(taken.sum()) / months, 1),
           "mean_mult_of_taken": round(float(d.mult[taken].mean()), 4) if taken.any() else None}
    return out


def evaluate(per_ref, per_var, years=C.OOF):
    """reference and variant on the pooled years and each year; the variant scaled to the reference's weekly sd.
    A year = the weeks of that year sliced from the pooled weekly series (trades booked at their exit week)."""
    bref = book(per_ref, years)
    bvar = book(per_var, years)
    wr = C.weekly(bref, years)
    wv0 = C.weekly(bvar, years)
    sd_ref = float(wr.std(ddof=1))
    sd_var = float(wv0.std(ddof=1))
    k = sd_ref / sd_var if sd_var > 0 else float("nan")
    wv = wv0 * k
    out = {"scale_k": round(k, 4), "max_effective_stake": round(k * float(bvar.mult.max()), 4),
           "ref": measures(bref, years), "var_raw": measures(bvar, years), "var_equal_swing": measures(bvar, years, k),
           "by_year": {}}
    out["sharpe_ratio"] = round(out["var_equal_swing"]["weekly_sharpe"] / out["ref"]["weekly_sharpe"], 4)
    wy = C.week_year(wr.index.to_numpy())
    for Y in years:
        m = wy == Y
        xr, xv = wr.to_numpy()[m], wv.to_numpy()[m]
        out["by_year"][Y] = {"weeks": int(m.sum()), "ref_sharpe": round(C.sharpe(xr), 4), "var_sharpe": round(C.sharpe(xv), 4),
                             "ref_total": round(float(xr.sum()), 2), "var_total_equal_swing": round(float(xv.sum()), 2),
                             "ref_losing_weeks_pct": round(float((xr < 0).mean() * 100), 1),
                             "var_losing_weeks_pct": round(float((xv < 0).mean() * 100), 1),
                             "ref_worst_week": round(float(xr.min()), 2), "var_worst_week": round(float(xv.min()), 2),
                             "ref_trades_entered": int((bref.entry_time.dt.year == Y).sum()),
                             "var_trades_entered": int(((bvar.entry_time.dt.year == Y) & (bvar.mult > 0)).sum()),
                             "up": bool(C.sharpe(xv) > C.sharpe(xr))}
    out["years_up"] = int(sum(out["by_year"][Y]["up"] for Y in years))
    return out


def per_sleeve_effect(per_ref, per_var, years=C.OOF):
    """what the variant did inside each sleeve on `years` (raw stakes): trades, R of the trades given each multiplier"""
    res = {}
    for k in per_ref:
        tr, mr = per_ref[k]
        tv, mv = per_var[k]
        yr = tr.entry_time.dt.year.isin(years).to_numpy()
        yv = tv.entry_time.dt.year.isin(years).to_numpy()
        mv = np.asarray(mv, float)
        row = {"ref_n": int(yr.sum()), "ref_R": round(float(tr.R.to_numpy()[yr].sum()), 2),
               "var_n": int(yv.sum()), "var_R_raw": round(float((tv.R.to_numpy() * mv)[yv].sum()), 2)}
        for m in (0.5, 1.5):
            sel = yv & (mv == m)
            row[f"n_at_{m}"] = int(sel.sum())
            row[f"meanR_at_{m}"] = round(float(tv.R.to_numpy()[sel].mean()), 4) if sel.any() else None
        removed = set(tr.oid[yr]) - set(tv.oid[yv])
        added = set(tv.oid[yv]) - set(tr.oid[yr])
        row["removed_trades"] = len(removed)
        row["removed_meanR"] = round(float(tr.R[tr.oid.isin(removed) & yr].mean()), 4) if removed else None
        row["added_trades"] = len(added)
        row["added_meanR"] = round(float(tv.R[tv.oid.isin(added) & yv].mean()), 4) if added else None
        res[k] = row
    return res
