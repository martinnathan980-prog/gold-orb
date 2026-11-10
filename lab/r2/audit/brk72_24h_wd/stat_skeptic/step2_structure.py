"""Step 2: structure of the result from the regenerated trades: by year x side, concentration, clustering,
one-position vs every-signal agreement, gross erosion, R-vs-bps weighting."""
from common import *
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30); pd.set_option("display.max_rows", 200)
res = {}

def both(kind):
    out = {}
    for sym in SYMS:
        ti, tv = load_trades(sym, kind, "is"), load_trades(sym, kind, "val")
        out[sym] = pd.concat([ti.assign(per="is"), tv.assign(per="val")]).assign(sym=sym)
    return out

fp, gross, every, everyg = both("fp"), both("gross"), both("every"), both("every_gross")

print("=== by year: one-position net / gross / every-signal net / every-signal gross")
rows = []
for sym in SYMS:
    for y in sorted(fp[sym].entry_time.dt.year.unique()):
        a = fp[sym][fp[sym].entry_time.dt.year == y]; g = gross[sym][gross[sym].entry_time.dt.year == y]
        e = every[sym][every[sym].entry_time.dt.year == y]; eg = everyg[sym][everyg[sym].entry_time.dt.year == y]
        L, Sh = a[a.side > 0], a[a.side < 0]
        rows.append({"sym": sym, "year": y, "n": len(a), "expR": a.R.mean(), "sumR": a.R.sum(), "pf": pf(a.R), "t": tstat(a.R), "win": (a.R > 0).mean(),
                     "net_bp": (a.pnl / a.entry).mean() * 1e4, "gross_bp": (g.pnl / g.entry).mean() * 1e4, "gross_expR": g.R.mean(),
                     "nL": len(L), "L_R": L.R.sum(), "L_bp": (L.pnl / L.entry).mean() * 1e4 if len(L) else np.nan,
                     "nS": len(Sh), "S_R": Sh.R.sum(), "S_bp": (Sh.pnl / Sh.entry).mean() * 1e4 if len(Sh) else np.nan,
                     "ev_n": len(e), "ev_expR": e.R.mean(), "ev_bp": (e.pnl / e.entry).mean() * 1e4, "evg_bp": (eg.pnl / eg.entry).mean() * 1e4,
                     "stop_pct": (a.risk / a.entry).median() * 100})
by = pd.DataFrame(rows)
print(by.round(3).to_string(index=False))
by.to_csv(os.path.join(HERE, "by_year.csv"), index=False)

print("\n=== half-year gross edge (bp per trade, one-position) and cost (gross-net)")
rows = []
for sym in SYMS:
    g = gross[sym].copy(); a = fp[sym].copy()
    g["h"] = g.entry_time.dt.year.astype(str) + "H" + ((g.entry_time.dt.month - 1) // 6 + 1).astype(str)
    a["h"] = a.entry_time.dt.year.astype(str) + "H" + ((a.entry_time.dt.month - 1) // 6 + 1).astype(str)
    for h in sorted(g.h.unique()):
        gg, aa = g[g.h == h], a[a.h == h]
        rows.append({"sym": sym, "half": h, "n": len(gg), "gross_bp": (gg.pnl / gg.entry).mean() * 1e4, "net_bp": (aa.pnl / aa.entry).mean() * 1e4,
                     "gross_R": gg.R.mean(), "net_R": aa.R.mean(), "sum_net_R": aa.R.sum()})
hy = pd.DataFrame(rows)
print(hy.round(3).to_string(index=False))
hy.to_csv(os.path.join(HERE, "by_halfyear.csv"), index=False)

print("\n=== concentration")
for per in ("is", "val"):
    for sym in SYMS + ("basket",):
        t = pd.concat([fp[s] for s in SYMS]) if sym == "basket" else fp[sym]
        t = t[t.per == per].sort_values("entry_time")
        R = np.sort(t.R.to_numpy())[::-1]; n = len(R); tot = R.sum()
        d = {"n": n, "total_R": round(tot, 1)}
        for q in (0.01, 0.02, 0.05, 0.10):
            k = max(1, int(round(q * n)))
            d[f"top{int(q*100)}%_trades({k})_sumR"] = round(float(R[:k].sum()), 1)
            d[f"total_without_top{int(q*100)}%"] = round(float(R[k:].sum()), 1)
        # number of best trades that must be removed to make the total <= 0
        cs = tot - np.cumsum(R)
        d["n_best_trades_to_zero"] = int(np.argmax(cs <= 0) + 1) if (cs <= 0).any() else None
        d["pct_best_trades_to_zero"] = round(100 * d["n_best_trades_to_zero"] / n, 2) if d["n_best_trades_to_zero"] else None
        wk = t.groupby(week_key(t.exit_time)).R.sum().sort_values(ascending=False)
        d["n_weeks"] = int(len(wk)); d["top5_weeks_sumR"] = round(float(wk.iloc[:5].sum()), 1); d["top10_weeks_sumR"] = round(float(wk.iloc[:10].sum()), 1)
        csw = wk.sum() - np.cumsum(wk.to_numpy())
        d["n_best_weeks_to_zero"] = int(np.argmax(csw <= 0) + 1) if (csw <= 0).any() else None
        mo = t.groupby(pd.DatetimeIndex(t.exit_time).tz_convert(None).to_period("M")).R.sum().sort_values(ascending=False)
        d["n_months"] = int(len(mo)); d["top3_months_sumR"] = round(float(mo.iloc[:3].sum()), 1); d["months_pos_pct"] = round(float((mo > 0).mean() * 100), 1)
        csm = mo.sum() - np.cumsum(mo.to_numpy())
        d["n_best_months_to_zero"] = int(np.argmax(csm <= 0) + 1) if (csm <= 0).any() else None
        d["best_months"] = {str(k): round(float(v), 1) for k, v in mo.iloc[:4].items()}
        d["worst_months"] = {str(k): round(float(v), 1) for k, v in mo.iloc[-4:].items()}
        # skew / kurtosis of R
        r = t.R.to_numpy(); m, s = r.mean(), r.std(ddof=0)
        d["skew"] = round(float(((r - m) ** 3).mean() / s ** 3), 2); d["kurt"] = round(float(((r - m) ** 4).mean() / s ** 4), 2)
        d["median_R"] = round(float(np.median(r)), 3); d["win"] = round(float((r > 0).mean()), 3)
        res[f"conc:{per}:{sym}"] = d
        print(per, sym, json.dumps(d))

print("\n=== clustering: per-trade t vs weekly-cluster t vs monthly-cluster t; weekly autocorrelation")
for per in ("is", "val"):
    for sym in SYMS + ("basket",):
        t = pd.concat([fp[s] for s in SYMS]) if sym == "basket" else fp[sym]
        t = t[t.per == per].sort_values("entry_time")
        r = t.R.to_numpy(); n = len(r)
        d = {"n": n, "mean_R": round(float(r.mean()), 4), "t_trade": round(tstat(r), 2)}
        for nm, key in (("week", week_key(t.entry_time)), ("month", pd.DatetimeIndex(t.entry_time).tz_convert(None).to_period("M"))):
            g = pd.DataFrame({"R": r, "k": key}).groupby("k").R.agg(["sum", "count"])
            # cluster-robust variance of the mean: sum over clusters of (sum_c - n_c*mean)^2 / n^2, small-sample factor G/(G-1)
            G = len(g); e = g["sum"] - g["count"] * r.mean()
            se = math.sqrt((e ** 2).sum() * G / (G - 1)) / n
            d[f"t_cluster_{nm}"] = round(float(r.mean() / se), 2); d[f"n_{nm}s"] = int(G)
        wk = t.groupby(week_key(t.exit_time)).R.sum()
        allw = pd.period_range(wk.index.min(), wk.index.max(), freq="W"); w = wk.reindex(allw, fill_value=0.0).to_numpy()
        d["weekly_mean"] = round(float(w.mean()), 4); d["weekly_sd"] = round(float(w.std(ddof=1)), 3); d["t_weekly_series"] = round(tstat(w), 2)
        d["weekly_sharpe_ann"] = round(float(w.mean() / w.std(ddof=1) * math.sqrt(52)), 2)
        d["acf1_weekly"] = round(float(np.corrcoef(w[1:], w[:-1])[0, 1]), 3)
        d["acf1_trade"] = round(float(np.corrcoef(r[1:], r[:-1])[0, 1]), 3)
        res[f"cluster:{per}:{sym}"] = d
        print(per, sym, json.dumps(d))

print("\n=== BTC/ETH weekly R correlation and effective bets")
for per in ("is", "val"):
    w = {}
    for sym in SYMS:
        t = fp[sym][fp[sym].per == per]
        w[sym] = t.groupby(week_key(t.exit_time)).R.sum()
    idx = pd.period_range(min(x.index.min() for x in w.values()), max(x.index.max() for x in w.values()), freq="W")
    W = pd.DataFrame({k: v.reindex(idx, fill_value=0.0) for k, v in w.items()})
    if per == "is":
        W = W[W.index >= pd.Period("2018-01-01", freq="W")]
    rho = float(W.corr().iloc[0, 1]); res[f"corr_weekly:{per}"] = round(rho, 3)
    print(per, "weekly corr", round(rho, 3), "effective independent bets of 2 sleeves:", round(2 / (1 + rho), 2))

print("\n=== R-weighting vs equal-notional: does the sign of the edge depend on the weighting?")
for per in ("is", "val"):
    for sym in SYMS:
        t = fp[sym][fp[sym].per == per]
        sp = (t.risk / t.entry * 100); ret = t.pnl / t.entry * 1e4
        q = pd.qcut(sp, 4, labels=["Q1 tight stop", "Q2", "Q3", "Q4 wide stop"])
        g = pd.DataFrame({"q": q, "R": t.R, "bp": ret, "sp": sp}).groupby("q", observed=True).agg(n=("R", "size"), stop_pct=("sp", "median"), expR=("R", "mean"), bp=("bp", "mean"), sumR=("R", "sum"))
        print(per, sym, "net bp/trade", round(float(ret.mean()), 2), "| exp R", round(float(t.R.mean()), 4), "| PF on equal-notional returns", round(pf(t.ret), 3), "| corr(stop%, R)", round(float(np.corrcoef(sp, t.R)[0, 1]), 3))
        print(g.round(3).to_string())
        res[f"weighting:{per}:{sym}"] = {"net_bp": round(float(ret.mean()), 2), "exp_R": round(float(t.R.mean()), 4), "pf_ret": round(pf(t.ret), 3),
                                        "by_stop_quartile": g.round(4).reset_index().astype({"q": str}).to_dict("records")}

print("\n=== one-position vs every-signal: by year (net exp R) and the skipped signals")
for sym in SYMS:
    a, e = fp[sym], every[sym]
    key = set(a.entry_time)
    sk = e[~e.entry_time.isin(key)]
    for per in ("is", "val"):
        aa, ee, ss = a[a.per == per], e[e.per == per], sk[sk.per == per]
        print(sym, per, "taken", stats(aa), "| every", stats(ee), "| skipped-only", stats(ss))
        res[f"everysig:{per}:{sym}"] = {"taken": stats(aa), "every": stats(ee), "skipped_only": stats(ss)}
    yy = pd.DataFrame({"taken": a.groupby(a.entry_time.dt.year).R.mean(), "every": e.groupby(e.entry_time.dt.year).R.mean(),
                       "skipped": sk.groupby(sk.entry_time.dt.year).R.mean(), "n_taken": a.groupby(a.entry_time.dt.year).size(), "n_every": e.groupby(e.entry_time.dt.year).size()})
    print(yy.round(3).to_string())
json.dump(res, open(os.path.join(HERE, "step2_structure.json"), "w"), indent=1, default=str)
