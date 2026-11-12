"""Lens `cluster`, part 1 (description, no rule is chosen here): are the losses clustered? IN SAMPLE ONLY.

Book: the ten sleeves' own chains re-simulated by repro.py (FP costs). Two views:
  * sleeve view: every trade of a sleeve's chain at unit stake (what the rule does);
  * account view: the reference account (6 positions, 2 per market, one base stake per trade).
Window: entries 2018-02-01 .. 2021-12-31 (common window) unless "whole" is said (from each frame's start).
Days / weeks: FP server clock (New York + 7 h), result booked on the EXIT time.

Outputs (results/r2/autopsy/cluster/): anatomy_*.csv and anatomy.json.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import book as B  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

RNG = np.random.default_rng(20261112)
N_PERM = 2000


def norm_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2.0))


# ---------------------------------------------------------------------------------------------------- 1. runs
def runs_one(R):
    L = R < 0
    n = len(L)
    n2 = int(L.sum())
    n1 = n - n2
    runs = 1 + int((L[1:] != L[:-1]).sum())
    mu = 2.0 * n1 * n2 / n + 1.0
    var = 2.0 * n1 * n2 * (2.0 * n1 * n2 - n) / (n * n * (n - 1.0))
    z = (runs - mu) / math.sqrt(var)
    prevL, nxtL = L[:-1], L[1:]
    p_LL = float(nxtL[prevL].mean())
    p_LW = float(nxtL[~prevL].mean())
    # permutation test of p(L|L) - p(L|W) (order of the trades shuffled within the sleeve)
    obs = p_LL - p_LW
    cnt = 0
    for _ in range(N_PERM):
        q = RNG.permutation(L)
        a, b = q[:-1], q[1:]
        if b[a].mean() - b[~a].mean() >= obs:
            cnt += 1
    out = {"n": n, "losses": n2, "p_loss": round(n2 / n, 4), "runs": runs, "runs_expected": round(mu, 1),
           "z": round(z, 2), "p_two_sided": round(2 * norm_sf(abs(z)), 4),
           "p_loss_after_loss": round(p_LL, 4), "p_loss_after_win": round(p_LW, 4),
           "perm_p_one_sided_LL_gt_LW": round((cnt + 1) / (N_PERM + 1), 4),
           "lag1_autocorr_R": round(float(np.corrcoef(R[:-1], R[1:])[0, 1]), 4),
           "meanR_after_loss": round(float(R[1:][prevL].mean()), 4), "meanR_after_win": round(float(R[1:][~prevL].mean()), 4)}
    # after k consecutive losses (k >= 1..5): next trade
    streak = np.zeros(n, np.int64)          # number of consecutive losses ending at trade i-1 (before trade i)
    c = 0
    for i in range(n):
        streak[i] = c
        c = c + 1 if L[i] else 0
    for k in range(1, 6):
        sel = streak >= k
        out[f"after_{k}plus_losses_n"] = int(sel.sum())
        out[f"after_{k}plus_losses_meanR"] = round(float(R[sel].mean()), 4) if sel.any() else None
        out[f"after_{k}plus_losses_p_loss"] = round(float(L[sel].mean()), 4) if sel.any() else None
    return out


def part_runs(d):
    rows = []
    for view, sel in (("common", d.t_in >= C.COMMON_START), ("whole", d.t_in >= d.t_in.min())):
        for s in C.SLEEVE_KEYS:
            t = d[sel & (d.sleeve == s)].sort_values("t_in")
            r = runs_one(t.R.to_numpy())
            rows.append({"window": view, "sleeve": s, **r})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------------------------------- 2. pairs
def daily(d, m, by):
    """Daily booked result (exit day, server) per group, taken trades only (m > 0) at stake m."""
    k = m > 0
    x = pd.DataFrame({"day": d.dy_out_abs.to_numpy()[k], "g": d[by].to_numpy()[k], "r": (m * d.R.to_numpy())[k]})
    return x.pivot_table(index="day", columns="g", values="r", aggfunc="sum")


def pair_stats(D, a, b):
    x = D[[a, b]].dropna()
    xa, xb = x[a].to_numpy(), x[b].to_numpy()
    la, lb = xa < 0, xb < 0
    return {"days_both": int(len(x)), "corr_daily_R": round(float(np.corrcoef(xa, xb)[0, 1]), 4),
            "p_B_red": round(float(lb.mean()), 4), "p_B_red_given_A_red": round(float(lb[la].mean()), 4),
            "p_B_red_given_A_green": round(float(lb[~la].mean()), 4), "p_both_red": round(float((la & lb).mean()), 4),
            "p_both_red_if_independent": round(float(la.mean() * lb.mean()), 4)}


def overlap_pairs(d, a, b):
    """Trades of sleeve a and sleeve b that are open at the same time (same market): R correlation by side."""
    def arr(x):
        return np.c_[x.t_in.astype("int64").to_numpy(), x.t_out.astype("int64").to_numpy(),
                     x.side.to_numpy(np.int64)].astype(np.int64), x.R.to_numpy(float)
    A, RA = arr(d[d.sleeve == a])
    Bt, RB = arr(d[d.sleeve == b])
    same, opp = [], []
    bi = np.argsort(Bt[:, 0], kind="stable")
    Bt, RB = Bt[bi], RB[bi]
    b_in = Bt[:, 0]
    for (ti, to, sd), r in zip(A, RA):
        hi = np.searchsorted(b_in, to, side="left")
        for q in range(hi):
            if Bt[q, 1] > ti:
                (same if Bt[q, 2] == sd else opp).append((r, RB[q]))
    out = {}
    for lab, v in (("same_side", same), ("opposite_side", opp)):
        v = np.array(v, float).reshape(-1, 2)
        if len(v) >= 3:
            la, lb = v[:, 0] < 0, v[:, 1] < 0
            out[lab] = {"pairs": int(len(v)), "corr_R": round(float(np.corrcoef(v[:, 0], v[:, 1])[0, 1]), 4),
                        "p_both_lose": round(float((la & lb).mean()), 4),
                        "p_both_lose_if_independent": round(float(la.mean() * lb.mean()), 4),
                        "mean_R_sum": round(float(v.sum(axis=1).mean()), 4)}
        else:
            out[lab] = {"pairs": int(len(v))}
    return out


def perm_coloss(D, cols, n_perm=N_PERM):
    """Days on which at least two of `cols` lose, against permutations of each column's results over its own days."""
    X = D[cols].to_numpy()
    def count(M):
        red = np.nan_to_num(M, nan=0.0) < 0
        return int((red.sum(axis=1) >= 2).sum())
    obs = count(X)
    sims = np.zeros(n_perm)
    for p in range(n_perm):
        Y = X.copy()
        for j in range(Y.shape[1]):
            k = ~np.isnan(Y[:, j])
            Y[k, j] = RNG.permutation(Y[k, j])
        sims[p] = count(Y)
    return {"days": int(len(X)), "days_2plus_red_observed": obs, "days_2plus_red_permuted_mean": round(float(sims.mean()), 1),
            "permuted_p95": float(np.percentile(sims, 95)), "p_one_sided": round(float(((sims >= obs).sum() + 1) / (n_perm + 1)), 4)}


def part_pairs(d):
    sel = (d.t_in >= C.COMMON_START).to_numpy()
    dc = d[sel]
    ones = np.ones(len(dc))
    D = daily(dc, ones, "sleeve")
    rows = []
    for sym in C.MARKETS:
        sl = sorted(dc[dc.sym == sym].sleeve.unique())
        for i in range(len(sl)):
            for j in range(i + 1, len(sl)):
                r = {"market": sym, "A": sl[i], "B": sl[j], **pair_stats(D, sl[i], sl[j])}
                ov = overlap_pairs(dc, sl[i], sl[j])
                for side, v in ov.items():
                    for k, x in v.items():
                        r[f"overlap_{side}_{k}"] = x
                rows.append(r)
    pairs = pd.DataFrame(rows)
    coloss = {}
    for sym in C.MARKETS:
        sl = sorted(dc[dc.sym == sym].sleeve.unique())
        if len(sl) >= 2:
            coloss[sym] = perm_coloss(D, sl)
    # families: btc + eth together
    sl = sorted(dc[dc.fam == 2].sleeve.unique())
    coloss["crypto_family_5_sleeves"] = perm_coloss(D, sl)
    return pairs, coloss


def part_markets(d, m_ref):
    sel = (d.t_in >= C.COMMON_START).to_numpy()
    dc = d[sel]
    mr = m_ref[sel]
    out = {}
    for by in ("sym", "fam"):
        D = daily(dc, mr, by)
        cols = list(D.columns)
        corr = {}
        cond = {}
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                a, b = cols[i], cols[j]
                ps = pair_stats(D, a, b)
                key = f"{a if by == 'sym' else C.FAM_NAMES[a]}~{b if by == 'sym' else C.FAM_NAMES[b]}"
                corr[key] = ps
        out[by] = {"pairs": corr, "coloss": perm_coloss(D, cols)}
        Wk = dc.assign(r=mr * dc.R.to_numpy())[mr > 0].pivot_table(index="wk_out_abs", columns=by, values="r", aggfunc="sum")
        out[by]["weekly_corr"] = {f"{a}~{b}": round(float(Wk[[a, b]].dropna().corr().iloc[0, 1]), 4)
                                  for i, a in enumerate(Wk.columns) for b in list(Wk.columns)[i + 1:]}
    # crypto with us100 specifically: the us100 day result against each crypto sleeve's day result
    D = daily(dc, mr, "sleeve")
    us = daily(dc, mr, "sym")["us100"]
    cw = {}
    for s in sorted(dc[dc.fam == 2].sleeve.unique()):
        x = pd.concat([us.rename("us100"), D[s]], axis=1).dropna()
        la, lb = x.iloc[:, 0] < 0, x.iloc[:, 1] < 0
        cw[s] = {"days_both": int(len(x)), "corr": round(float(x.corr().iloc[0, 1]), 4),
                 "p_red": round(float(lb.mean()), 4), "p_red_given_us100_red": round(float(lb[la].mean()), 4),
                 "p_red_given_us100_green": round(float(lb[~la].mean()), 4)}
    out["crypto_sleeves_vs_us100_day"] = cw
    return out


# ---------------------------------------------------------------------------------------------------- 3. clock
def part_clock(d):
    sel = (d.t_in >= C.COMMON_START).to_numpy()
    dc = d[sel].copy()
    dc["wd"] = dc.srv_in.dt.dayofweek
    dc["hr"] = dc.srv_in.dt.hour
    rows = []
    for key, grp in (("weekday", ["wd"]), ("hour", ["hr"]), ("sleeve_weekday", ["sleeve", "wd"])):
        mu_s = dc.groupby("sleeve").R.mean()
        for g, x in dc.groupby(grp):
            g = g if isinstance(g, tuple) else (g,)
            R = x.R.to_numpy()
            sd = R.std(ddof=1) if len(R) > 1 else float("nan")
            row = {"table": key, "group": "/".join(str(v) for v in g), "n": int(len(R)), "win_rate": round(float((R > 0).mean()), 4),
                   "mean_R": round(float(R.mean()), 4), "total_R": round(float(R.sum()), 2),
                   "t_mean": round(float(R.mean() / sd * math.sqrt(len(R))), 2) if len(R) > 1 and sd > 0 else None}
            if key == "sleeve_weekday":
                diff = R - mu_s[g[0]]
                row["t_vs_sleeve_mean"] = round(float(diff.mean() / diff.std(ddof=1) * math.sqrt(len(R))), 2) if len(R) > 2 else None
            rows.append(row)
    t = pd.DataFrame(rows)
    sw = t[t.table == "sleeve_weekday"]
    note = {"sleeve_weekday_cells": int(len(sw)), "cells_abs_t_vs_sleeve_gt2": int((sw.t_vs_sleeve_mean.abs() > 2).sum()),
            "expected_by_chance_at_5pct": round(0.0455 * len(sw), 1)}
    return t, note


# ---------------------------------------------------------------------------------------------------- 4. worst days
def clusters(d, m_ref, level):
    """Connected groups of LOSING taken trades of different sleeves on the same market (level 'market') or family
    (level 'family'), same side, with overlapping holding intervals. Returns a cluster id per trade (-1 if none)."""
    k = np.nonzero((m_ref > 0) & (d.R.to_numpy() < 0))[0]
    key = d.sym.to_numpy() if level == "market" else d.fam.to_numpy().astype(str)
    cid = np.full(len(d), -1, np.int64)
    parent = {i: i for i in k}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    t_in = d.t_in.astype("int64").to_numpy()
    t_out = d.t_out.astype("int64").to_numpy()
    side = d.side.to_numpy()
    sl = d.sleeve.to_numpy()
    groups = {}
    for i in k:
        groups.setdefault((key[i], side[i]), []).append(i)
    for g, idx in groups.items():
        idx = sorted(idx, key=lambda q: t_in[q])
        active = []
        for i in idx:
            active = [q for q in active if t_out[q] > t_in[i]]
            for q in active:
                parent[find(i)] = find(q)
            active.append(i)
    roots = {}
    for i in k:
        roots.setdefault(find(i), []).append(i)
    n = 0
    for r, members in roots.items():
        if len(set(sl[members])) >= 2:
            cid[members] = n
            n += 1
    return cid


def part_worst(d, m_ref, unit="day", top=10):
    sel = (d.t_in >= C.COMMON_START).to_numpy()
    took = sel & (m_ref > 0)
    r = m_ref * d.R.to_numpy()
    col = "dy_out_abs" if unit == "day" else "wk_out_abs"
    per = pd.Series(r[took]).groupby(d[col].to_numpy()[took]).sum().sort_values()
    cm = clusters(d, np.where(took, m_ref, 0.0), "market")
    cf = clusters(d, np.where(took, m_ref, 0.0), "family")
    los = took & (d.R.to_numpy() < 0)
    rows = []
    for p, tot in per.head(top).items():
        k = took & (d[col].to_numpy() == p)
        lk = k & los
        gross_loss = -r[lk].sum()
        mk = pd.Series(r[k]).groupby(d.sym.to_numpy()[k]).sum()
        sk = pd.Series(r[k]).groupby(d.sleeve.to_numpy()[k]).sum()
        first = d.srv_out[k].min()
        rows.append({
            "unit": unit, "period": str(first.date()) if unit == "day" else f"week of {(first - pd.Timedelta(days=first.dayofweek)).date()}",
            "net_R": round(float(tot), 3), "trades": int(k.sum()), "losing_trades": int(lk.sum()),
            "gross_loss_R": round(float(gross_loss), 3),
            "sleeves_net_red": int((sk < 0).sum()), "markets_net_red": int((mk < 0).sum()),
            "worst_market": mk.idxmin(), "worst_market_net_R": round(float(mk.min()), 3),
            "worst_sleeve": sk.idxmin(), "worst_sleeve_net_R": round(float(sk.min()), 3),
            "share_loss_same_market_side_overlap_multi_sleeve": round(float(-r[lk & (cm >= 0)].sum() / gross_loss), 3) if gross_loss > 0 else None,
            "share_loss_same_family_side_overlap_multi_sleeve": round(float(-r[lk & (cf >= 0)].sum() / gross_loss), 3) if gross_loss > 0 else None,
            "by_market_net_R": {kk: round(float(v), 3) for kk, v in mk.items()},
        })
    t = pd.DataFrame(rows)
    # the same shares over ALL losing trades of the window, for comparison
    allshare = {"share_all_losses_same_market_side_overlap_multi_sleeve": round(float(-r[los & (cm >= 0)].sum() / -r[los].sum()), 4),
                "share_all_losses_same_family_side_overlap_multi_sleeve": round(float(-r[los & (cf >= 0)].sum() / -r[los].sum()), 4)}
    agg = {"sum_net_R": round(float(t.net_R.sum()), 3), "sum_gross_loss_R": round(float(t.gross_loss_R.sum()), 3),
           "loss_share_same_market_side_overlap_multi_sleeve": round(float((t.gross_loss_R * t.share_loss_same_market_side_overlap_multi_sleeve).sum() / t.gross_loss_R.sum()), 4),
           "loss_share_same_family_side_overlap_multi_sleeve": round(float((t.gross_loss_R * t.share_loss_same_family_side_overlap_multi_sleeve).sum() / t.gross_loss_R.sum()), 4),
           "periods_with_2plus_markets_red": int((t.markets_net_red >= 2).sum()),
           "periods_with_3plus_sleeves_red": int((t.sleeves_net_red >= 3).sum()), **allshare}
    return t, agg


# ---------------------------------------------------------------------------------------------------- 5. persistence
def part_persistence(d):
    """Redo of the scratch adapt_is.py, causal: trailing record = trades CLOSED before the month start; next month =
    trades ENTERED during the month; demeaned by the sleeve's expanding mean of trades closed before the month."""
    rows = []
    months = pd.date_range("2013-02-01", "2022-01-01", freq="MS", tz="UTC")
    t_in = d.t_in.astype("int64").to_numpy()
    t_out = d.t_out.astype("int64").to_numpy()
    for s in C.SLEEVE_KEYS:
        k = d.sleeve.to_numpy() == s
        ti, to, R = t_in[k], t_out[k], d.R.to_numpy()[k]
        for M0, M1 in zip(months[:-1], months[1:]):
            a, b = M0.value, M1.value
            nxt = (ti >= a) & (ti < b)
            if not nxt.any():
                continue
            past = to < a
            if past.sum() < 5:
                continue
            row = {"sleeve": s, "month": str(M0.date()), "next_n": int(nxt.sum()), "next_meanR": float(R[nxt].mean()),
                   "next_total": float(R[nxt].sum()), "expanding_mean": float(R[past].mean())}
            for L in (91, 182, 365):
                w = past & (to >= a - L * 86_400_000_000_000)
                row[f"trail{L}_n"] = int(w.sum())
                row[f"trail{L}_meanR"] = float(R[w].mean()) if w.any() else np.nan
                row[f"trail{L}_total"] = float(R[w].sum()) if w.any() else np.nan
            rows.append(row)
    P = pd.DataFrame(rows)
    summ = {}
    for win, lo in (("common", "2018-02-01"), ("whole", "2013-01-01")):
        x0 = P[P.month >= lo]
        for L in (91, 182, 365):
            x = x0[x0[f"trail{L}_n"] >= 5]
            xd = x[f"trail{L}_meanR"] - x.expanding_mean
            yd = x.next_meanR - x.expanding_mean
            # month-level weight = number of next-month trades (pooled trade-level reading)
            neg = x[x[f"trail{L}_total"] <= 0]
            pos = x[x[f"trail{L}_total"] > 0]
            wmean = lambda z: float((z.next_total.sum()) / z.next_n.sum()) if len(z) else None
            # permutation of the trailing value across sleeve-months of the same sleeve
            obs = float(np.corrcoef(xd, yd)[0, 1])
            xv, yv = xd.to_numpy(), yd.to_numpy()
            groups = [np.nonzero(x.sleeve.to_numpy() == s)[0] for s in x.sleeve.unique()]
            sims = np.zeros(1000)
            for q in range(1000):
                xs = xv.copy()
                for g in groups:
                    xs[g] = RNG.permutation(xs[g])
                sims[q] = np.corrcoef(xs, yv)[0, 1]
            summ[f"{win}_trail{L}"] = {
                "sleeve_months": int(len(x)), "corr_demeaned": round(obs, 4),
                "perm_p_one_sided": round(float(((sims >= obs).sum() + 1) / 1001), 4),
                "next_R_per_trade_after_trailing_le0": round(wmean(neg), 4) if len(neg) else None, "n_trades_after_le0": int(neg.next_n.sum()),
                "next_R_per_trade_after_trailing_gt0": round(wmean(pos), 4) if len(pos) else None, "n_trades_after_gt0": int(pos.next_n.sum()),
                "sleeve_months_le0": int(len(neg))}
    return P, summ


# ---------------------------------------------------------------------------------------------------- 6. portfolio
def part_portfolio_time(d, m_ref):
    sel = (d.t_in >= C.COMMON_START).to_numpy()
    took = sel & (m_ref > 0)
    r = m_ref * d.R.to_numpy()
    days = pd.Series(r[took]).groupby(d.dy_out_abs.to_numpy()[took]).sum()
    wk = pd.Series(r[took]).groupby(d.wk_out_abs.to_numpy()[took]).sum()
    wk = wk.reindex(np.arange(wk.index.min(), wk.index.max() + 1), fill_value=0.0)
    x = days.to_numpy()
    red = x < 0
    q10 = np.percentile(x, 10)
    out = {"days": int(len(x)), "lag1_autocorr_daily": round(float(np.corrcoef(x[:-1], x[1:])[0, 1]), 4),
           "p_red_day": round(float(red.mean()), 4), "p_red_after_red_day": round(float(red[1:][red[:-1]].mean()), 4),
           "p_red_after_green_day": round(float(red[1:][~red[:-1]].mean()), 4),
           "mean_next_day_after_bottom_decile_day": round(float(x[1:][x[:-1] <= q10].mean()), 4),
           "mean_next_day_after_other_days": round(float(x[1:][x[:-1] > q10].mean()), 4),
           "bottom_decile_threshold": round(float(q10), 3),
           "weeks": int(len(wk)), "lag1_autocorr_weekly": round(float(np.corrcoef(wk.to_numpy()[:-1], wk.to_numpy()[1:])[0, 1]), 4)}
    w = wk.to_numpy()
    out["p_red_week_after_red_week"] = round(float((w[1:] < 0)[w[:-1] < 0].mean()), 4)
    out["p_red_week"] = round(float((w < 0).mean()), 4)
    # the portfolio's closed-trade sequence (exit order): runs test
    order = np.argsort(d.t_out.astype("int64").to_numpy()[took], kind="stable")
    seq = d.R.to_numpy()[took][order]
    out["portfolio_exit_order_runs"] = runs_one(seq)
    return out


def main():
    d = B.build("fp")
    a = B.arrays(d)
    m_ref, why = B.run(a, 0, caps=True)
    res = {"book": {"trades_whole": int(len(d)), "trades_common": int((d.t_in >= C.COMMON_START).sum()),
                    "reference_account_common_taken": int(((m_ref > 0) & (d.t_in >= C.COMMON_START).to_numpy()).sum())}}
    runs = part_runs(d)
    runs.to_csv(os.path.join(C.OUT, "anatomy_runs.csv"), index=False)
    pairs, coloss = part_pairs(d)
    pairs.to_csv(os.path.join(C.OUT, "anatomy_pairs_same_market.csv"), index=False)
    res["coloss_same_market_sleeve_days"] = coloss
    res["markets"] = part_markets(d, m_ref)
    clock, note = part_clock(d)
    clock.to_csv(os.path.join(C.OUT, "anatomy_weekday_hour.csv"), index=False)
    res["clock_note"] = note
    wd, aggd = part_worst(d, m_ref, "day")
    ww, aggw = part_worst(d, m_ref, "week")
    pd.concat([wd, ww]).to_csv(os.path.join(C.OUT, "anatomy_worst_days_weeks.csv"), index=False)
    res["worst_days"] = aggd
    res["worst_weeks"] = aggw
    P, summ = part_persistence(d)
    P.to_csv(os.path.join(C.OUT, "anatomy_persistence_sleeve_months.csv"), index=False)
    res["persistence"] = summ
    res["portfolio_time"] = part_portfolio_time(d, m_ref)
    json.dump(res, open(os.path.join(C.OUT, "anatomy.json"), "w"), indent=1, default=str)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print(runs[["window", "sleeve", "n", "p_loss", "runs", "runs_expected", "z", "p_two_sided", "p_loss_after_loss",
                "p_loss_after_win", "perm_p_one_sided_LL_gt_LW", "meanR_after_loss", "meanR_after_win"]].to_string())
    print(pairs.iloc[:, :12].to_string())
    print(json.dumps({k: res[k] for k in ("coloss_same_market_sleeve_days", "clock_note", "worst_days", "worst_weeks",
                                          "persistence", "portfolio_time")}, indent=1, default=str))
    print(json.dumps(res["markets"], indent=1, default=str)[:6000])
    print(wd.drop(columns=["by_market_net_R"]).to_string())
    print(ww.drop(columns=["by_market_net_R"]).to_string())


if __name__ == "__main__":
    main()
