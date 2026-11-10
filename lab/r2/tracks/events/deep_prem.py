"""Deep dive (IS ONLY) on the calendar-long rule: by kind, by year, halves (gross), exits, MAE, release-minute stops."""
import json, sys
import numpy as np, pandas as pd
from runner import use, trial, RES, gl, r2, S

P = dict(rule="long", lead=5, exit="hold", hold=15, stop_atr=1.0)
out = {}
for sym in (sys.argv[1:] or ["us500", "us100"]):
    ev = trial(sym, P, full=True, tag="F:prem-full")
    m1 = use(sym)
    p = S.resolve(P)
    t = gl.cut(r2.run(sym, S.make_orders, p, "fp", True, m1), "is")
    g = gl.cut(r2.run(sym, S.make_orders, p, "gross", True, m1), "is")
    t = t.assign(bps=t.pnl / t.entry * 1e4, year=t.entry_time.dt.year)
    g = g.assign(bps=g.pnl / g.entry * 1e4, year=g.entry_time.dt.year)
    ts = lambda x: float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))) if len(x) > 2 else float("nan")
    print(f"--- {sym}: exits {t.reason.value_counts().to_dict()} | R: min {t.R.min():.2f} p5 {t.R.quantile(.05):.2f} med {t.R.median():.3f} p95 {t.R.quantile(.95):.2f} max {t.R.max():.2f} sd {t.R.std():.3f}")
    print(f"    stop distance bp: median {np.median(t.risk / t.entry) * 1e4:.0f}; MAE/stop: p50 {np.median(-t.mae / t.risk):.2f} p90 {np.quantile(-t.mae / t.risk, .9):.2f} p99 {np.quantile(-t.mae / t.risk, .99):.2f} max {(-t.mae / t.risk).max():.2f}")
    bk = {}
    for k, x in t.groupby("kind"):
        gx = g[g.kind == k]
        bk[k] = dict(n=len(x), net_bps=round(x.bps.mean(), 2), gross_bps=round(gx.bps.mean(), 2), expR=round(x.R.mean(), 4), t=round(ts(x.R), 2), win=round((x.R > 0).mean(), 2))
        print(f"    {k:5s} {bk[k]}")
    by = t.groupby("year").agg(n=("R", "size"), R=("R", "sum"), bps=("bps", "mean")).round(2)
    print("    by year:", {int(y): (int(r.n), float(r.R), float(r.bps)) for y, r in by.iterrows()})
    mid = pd.Timestamp("2017-07-01", tz="UTC")
    h1, h2 = g[g.entry_time < mid], g[g.entry_time >= mid]
    n1, n2 = t[t.entry_time < mid], t[t.entry_time >= mid]
    print(f"    GROSS bps/trade: first half (2013-06..2017-06) {h1.bps.mean():+.2f} (t {ts(h1.bps):+.2f}, n {len(h1)}) | second half (2017-07..2021-12) {h2.bps.mean():+.2f} (t {ts(h2.bps):+.2f}, n {len(h2)})")
    print(f"    NET   bps/trade: first half {n1.bps.mean():+.2f} | second half {n2.bps.mean():+.2f} ; net R first {n1.R.mean():+.4f} second {n2.R.mean():+.4f}")
    # five worst and best trades
    w = t.nsmallest(5, "R")[["entry_time", "kind", "R", "bps", "reason"]]
    print("    worst:", [(str(r.entry_time)[:16], r.kind, round(r.R, 2), round(r.bps, 1), r.reason) for r in w.itertuples()])
    b = t.nlargest(5, "R")[["entry_time", "kind", "R", "bps", "reason"]]
    print("    best: ", [(str(r.entry_time)[:16], r.kind, round(r.R, 2), round(r.bps, 1), r.reason) for r in b.itertuples()])
    # robustness to outliers: winsorised t, t without the 5 best trades
    R = t.R.to_numpy(); lo, hi = np.percentile(R, [2.5, 97.5]); wR = np.clip(R, lo, hi)
    R5 = np.sort(R)[:-5]
    print(f"    t winsorised(2.5%) {ts(pd.Series(wR)):+.2f} | t without 5 best {ts(pd.Series(R5)):+.2f} | sign test: {int((R > 0).sum())}/{len(R)} wins")
    out[sym] = dict(by_kind=bk, by_year={int(y): float(r.R) for y, r in by.iterrows()},
                    gross_first_half_bps=round(float(h1.bps.mean()), 2), gross_second_half_bps=round(float(h2.bps.mean()), 2),
                    net_first_half_R=round(float(n1.R.mean()), 4), net_second_half_R=round(float(n2.R.mean()), 4),
                    t_wins=round(ts(pd.Series(wR)), 2), t_drop5=round(ts(pd.Series(R5)), 2), exits=t.reason.value_counts().to_dict(),
                    crit=r2.is_criteria(ev))
    print("    criteria:", out[sym]["crit"])
json.dump(out, open(f"{RES}/deep_prem.json", "w"), indent=1, default=str)
