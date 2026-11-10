"""IS-only diagnostics of a configuration (built on a frame that ENDS on 2021-12-31: no validation data loaded)."""
from harness import *     # noqa
from goldlab.sim import simulate

def is_trades(sym, params, mode="fp"):
    m1 = r2.load(sym, end="2022-01-01")
    p = S.resolve(params)
    t = r2.run(sym, S.make_orders, p, mode, True, m1)
    return t[t.entry_time >= pd.Timestamp("2014-01-01", tz="UTC")]

def tstat(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return round(float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))), 2) if len(x) > 2 else float("nan")

def pf(x):
    x = np.asarray(x, float); g, l = x[x > 0].sum(), -x[x < 0].sum()
    return round(float(g / l), 3) if l > 0 else float("nan")

def describe(sym, params, label):
    t = is_trades(sym, params)
    g = is_trades(sym, params, "gross")
    ny = t.entry_time.dt.tz_convert("America/New_York")
    t = t.assign(hm=ny.dt.strftime("%H:%M"), year=ny.dt.year, day=ny.dt.date, bp=t.pnl / t.entry * 1e4, stop_bp=t.risk / t.entry * 1e4)
    gny = g.entry_time.dt.tz_convert("America/New_York")
    g = g.assign(year=gny.dt.year, bp=g.pnl / g.entry * 1e4)
    out = {"label": label, "sym": sym, "n": int(len(t)), "expR": round(float(t.R.mean()), 4), "pf": pf(t.R), "t": tstat(t.R)}
    out["by_side"] = {("long" if s > 0 else "short"): {"n": int(len(x)), "expR": round(float(x.R.mean()), 4), "pf": pf(x.R), "t": tstat(x.R), "bp": round(float(x.bp.mean()), 2)} for s, x in t.groupby("side")}
    out["by_entry_time"] = {k: {"n": int(len(x)), "expR": round(float(x.R.mean()), 4), "t": tstat(x.R), "bp": round(float(x.bp.mean()), 2)} for k, x in t.groupby("hm")}
    out["by_reason"] = {k: {"n": int(len(x)), "expR": round(float(x.R.mean()), 3)} for k, x in t.groupby("reason")}
    out["stop_bp_median_by_year"] = {int(k): round(float(v), 1) for k, v in t.groupby("year").stop_bp.median().items()}
    out["R_quantiles"] = {q: round(float(t.R.quantile(q)), 2) for q in (0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)}
    out["R_min_max"] = (round(float(t.R.min()), 2), round(float(t.R.max()), 2))
    h1 = g.year <= 2017
    out["gross_bp_per_trade_2014_2017"] = (int(h1.sum()), round(float(g.bp[h1].mean()), 2), tstat(g.bp[h1]))
    out["gross_bp_per_trade_2018_2021"] = (int((~h1).sum()), round(float(g.bp[~h1].mean()), 2), tstat(g.bp[~h1]))
    out["gross_R_per_trade_halves"] = (round(float(g.R[h1].mean()), 4), round(float(g.R[~h1].mean()), 4))
    out["net_bp_by_year"] = {int(k): round(float(v), 2) for k, v in t.groupby("year").bp.mean().items()}
    out["trades_per_day"] = round(float(len(t) / t.day.nunique()), 2)
    daily = t.groupby("day").R.sum()
    out["daily_R"] = {"days": int(len(daily)), "mean": round(float(daily.mean()), 4), "t": tstat(daily), "worst": round(float(daily.min()), 2), "best": round(float(daily.max()), 2)}
    # top-5 days share of total R
    out["top10_days_share_of_total_R"] = round(float(daily.sort_values(ascending=False).head(10).sum() / daily.sum()), 3)
    out["hold_min_median"] = float(t.hold_min.median())
    return out, t

if __name__ == "__main__":
    import sys
    res = {}
    for label, sym, params in [("noise_us100", "us100", dict(rule="noise")), ("ocm_atr0.3_us100", "us100", dict(rule="ocm", stop="atr", k=0.3))]:
        d, t = describe(sym, params, label)
        res[label] = d
        print(json.dumps(d, indent=None, default=str))
        print()
    json.dump(res, open(os.path.join(RES, "diag_stage2.json"), "w"), indent=1, default=str)
