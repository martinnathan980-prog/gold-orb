"""Idea 062 (large moves without news in a calm market, faded; broad universe, daily bars) in sample. Reads declared.json (never writes it).
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/062_no_news_moves_fade/run.py"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
from kit import checks, judge, sim, stats
import signals as S

CACHE = os.path.expanduser("~/explore_data/idea_062")
os.makedirs(CACHE, exist_ok=True)
T0 = time.time()
decl = json.load(open(os.path.join(HERE, "declared.json")))
checks.declared_hash(HERE)
cfgs = decl["configurations"]
main_c = cfgs[0]
d = S.load_data()
t1 = time.time(); S.build(d, main_c["threshold"])
print(f"data loaded {t1-T0:.0f}s; one build {time.time()-t1:.1f}s", flush=True)

tr = checks.truncation_test(lambda x: S.build(x, main_c["threshold"]), d,
                            row_len={"bars": "known_at", "allowed": pd.Timedelta(0)}, cols=("known_at", "side"))
print(f"truncation pass={tr['pass']} {time.time()-T0:.0f}s", {k: v for k, v in tr.items() if k.startswith("n_")}, flush=True)
assert tr["pass"], {k: v for k, v in tr.items() if k != "failures"}

bk = sim.books(S.BS)
sigs = {}
def sig_for(th):
    if th not in sigs:
        sigs[th] = S.build(d, th)
    return sigs[th]
def rule(c):
    return dict(exit=tuple(c["exit"]), stop=tuple(c["stop"]))
def run(c, mode="one"):
    return sim.simulate(sig_for(c["threshold"]), bk, mode=mode, max_wait_h=96, **rule(c))

main = run(main_c)
neigh = {c["id"]: run(c) for c in cfgs[1:]}
every = run(main_c, "every")
print(f"simulated {time.time()-T0:.0f}s; main n={len(main)}", flush=True)
null = stats.null_test(main, bk, n_draws=2000, **rule(main_c))
print(f"null pct {null['percentile']:.1f} {time.time()-T0:.0f}s", flush=True)
sh = checks.shift_test(sig_for(main_c["threshold"]), bk, max_wait_h=96, **rule(main_c))
mc = checks.min_commission_test(sig_for(main_c["threshold"]), bk, max_wait_h=96, **rule(main_c))

# descriptive figures (reported, not judged)
SEC = S.sector_map()
def pf(x):
    x = np.asarray(x, float); g, l = x[x > 0].sum(), -x[x < 0].sum()
    return float(g / l) if l > 0 else None
def tday(t):
    if len(t) < 3:
        return None
    s = t.groupby(t.entry_time.dt.tz_convert("America/New_York").dt.date)["R"].sum()
    return float(s.mean() / s.std(ddof=1) * np.sqrt(len(s))) if s.std(ddof=1) > 0 else None
def summ(t):
    if not len(t):
        return {"n": 0}
    return {"n": int(len(t)), "mean_R": float(t.R.mean()), "PF_net": pf(t.R), "t_daily_net": tday(t),
            "mean_R_gross": float(t.R_gross.mean()), "PF_gross": pf(t.R_gross), "PF_stress": pf(t.R_stress),
            "mean_net_bp": float(t.net_bp.mean()), "mean_gross_bp": float(t.gross_bp.mean()),
            "win_rate_net": float((t.R > 0).mean())}
yr = main.entry_time.dt.tz_convert("America/New_York").dt.year
desc = {"main": summ(main), "long": summ(main[main.side > 0]), "short": summ(main[main.side < 0]),
        "by_year": {str(y): summ(g) for y, g in main.groupby(yr)},
        "by_year_side": {f"{y}_{'long' if s > 0 else 'short'}": summ(g) for (y, s), g in main.groupby([yr, main.side])},
        "by_sector": {s: summ(g) for s, g in main.groupby(main.market.map(SEC))},
        "by_sector_side": {f"{s}_{'long' if sd > 0 else 'short'}": summ(g)
                           for (s, sd), g in main.groupby([main.market.map(SEC), main.side])},
        "by_reason": {r: int(n) for r, n in main.reason.value_counts().items()},
        "hold": {str(k): int(v) for k, v in main.hold_tdays.value_counts().sort_index().items()} if "hold_tdays" in main else None,
        "counts": main.attrs.get("counts"),
        "neighbours": {k: summ(v) for k, v in neigh.items()}, "every": summ(every),
        "n_signals": {str(th): int(len(s)) for th, s in sigs.items()}}

res = judge.verdict(HERE, main, neigh, every, null, corr="compute", n_configs=len(cfgs), truncation=tr,
                    groups="sector", min_commission=mc,
                    data_desc="382 US shares (S&P 500 list minus the lab's 40), daily bars 2017-2021 (kit v2.2, Yahoo, "
                              "PROVISIONAL costs); EDGAR filing calendar idea_sessions('062', results_ahead=0) (no filing in s-2..s); calm sessions (median |ret_total| < 2 %); survivors only",
                    extra={"descriptive": desc, "shift": sh,
                           "null_detail": {k: v for k, v in null.items() if k != "draws"}})
main.to_csv(os.path.join(CACHE, "main_trades.csv"), index=False)
every.to_csv(os.path.join(CACHE, "every_trades.csv"), index=False)
for k in ("main", "long", "short"):
    print(k, json.dumps(desc[k]))
print("verdict:", res["verdict"], "failed:", res["failed_bars"])
print(res["ledger_line"])
print("dividends:", json.dumps({k: v for k, v in res.get("dividends", {}).items() if k != "by_market"}, default=str))
print(f"done {time.time()-T0:.0f}s")
