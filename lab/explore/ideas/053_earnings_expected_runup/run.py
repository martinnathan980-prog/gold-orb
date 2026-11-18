"""Idea 053 (earnings run-up on the expected date) in sample. Reads declared.json (never writes it).
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/053_earnings_expected_runup/run.py"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
from kit import checks, judge, sim, stats, data
import signals as S

T0 = time.time()
CACHE = os.path.expanduser("~/explore_data/idea_053")
os.makedirs(CACHE, exist_ok=True)
decl = json.load(open(os.path.join(HERE, "declared.json")))
checks.declared_hash(HERE)
cfgs = decl["configurations"]
main_c = cfgs[0]
K0, M0 = main_c["k_sessions_before_E"], main_c["exit_m_sessions_before_E"]
dcal = {"cal": S.load_calendar()}

tr = checks.truncation_test(lambda x: S.build(x, K0), dcal, row_len={"cal": pd.Timedelta(0)}, cols=("known_at", "side"))
print(f"signal truncation pass={tr['pass']} {time.time()-T0:.0f}s", {k: v for k, v in tr.items() if k.startswith("n_")})
assert tr["pass"], tr
tre = checks.truncation_test(lambda x: S.build_events(x, M0), dcal, row_len={"cal": pd.Timedelta(0)})
print(f"event truncation pass={tre['pass']} {time.time()-T0:.0f}s", {k: v for k, v in tre.items() if k.startswith("n_")})
assert tre["pass"], tre

sig_main = S.build(dcal, K0)
mk = sorted(sig_main.market.unique())
bk = sim.books({t: data.load_bars(t) for t in mk})
print(f"bars loaded ({len(mk)} shares) {time.time()-T0:.0f}s")


def rule(c):
    ev = S.build_events(dcal, c["exit_m_sessions_before_E"])
    ev = ev[ev.market.isin(mk)].reset_index(drop=True)
    return dict(exit=sim.event_exit(ev, tuple(c["exit"][2])), stop=tuple(c["stop"]), target=None)


def run(c, mode="one"):
    sig = sig_main if c["k_sessions_before_E"] == K0 else S.build(dcal, c["k_sessions_before_E"])
    return sim.simulate(sig, bk, mode=mode, max_wait_h=2, **rule(c))


main = run(main_c)
neigh = {c["id"]: run(c) for c in cfgs[1:]}
every = run(main_c, "every")
print(f"simulated {time.time()-T0:.0f}s; main n={len(main)}")
null = stats.null_test(main, bk, n_draws=2000, **rule(main_c))
print(f"null pct {null['percentile']:.1f} {time.time()-T0:.0f}s")


def pf(x):
    x = np.asarray(x, float); g, l = x[x > 0].sum(), -x[x < 0].sum()
    return float(g / l) if l > 0 else None


def summ(t):
    if not len(t):
        return {"n": 0}
    return {"n": int(len(t)), "mean_R": float(t.R.mean()), "PF_net": pf(t.R), "mean_R_gross": float(t.R_gross.mean()),
            "PF_gross": pf(t.R_gross), "mean_net_bp": float(t.net_bp.mean()), "mean_gross_bp": float(t.gross_bp.mean()),
            "PF_stress": pf(t.R_stress), "win_rate_net": float((t.R > 0).mean()),
            "t_trade_net": float(t.R.mean() / t.R.std(ddof=1) * np.sqrt(len(t))) if len(t) > 2 else None}


SECTORS = {"tech": "aapl adbe amd avgo crm csco intc msft mu nvda orcl qcom".split(),
           "internet_media": "amzn baba fb googl nflx dis pypl tsla".split(),
           "finance": "bac c gs jpm ma v wfc".split(),
           "health": "jnj mrk pfe unh".split(),
           "industry_energy_consumer": "ba cat ge cvx xom hd mcd nke wmt".split()}

# match each trade with its expected E and the actual release of that quarter (information only)
det = S.detail(dcal, K0, M0)
det["known_at"] = S._at(det.S, 10)
from earnings_edgar import calendar
allc = calendar(end="2021-12-31")
allc["rs"] = pd.to_datetime(allc.reaction_session).dt.normalize()
m = main.merge(det[["market", "known_at", "E", "S", "X"]], on=["market", "known_at"], how="left")
rel = []
for _, r in m.iterrows():
    g = allc[(allc.ticker == r.market) & ((allc.rs - r.E).abs() <= pd.Timedelta(days=45))]
    if not len(g):
        rel.append("no_actual"); continue
    a = g.rs.iloc[np.argmin((g.rs - r.E).abs().to_numpy())]
    rel.append("before_entry" if a < r.S else "on_entry_day" if a == r.S else "inside_hold" if a <= r.X
               else "on_E" if a == r.E else "after_E")
m["actual"] = rel
m["exit_day_ny"] = pd.DatetimeIndex(m.exit_time).tz_convert(S.NY).tz_localize(None).normalize()
m["exit_on_X"] = m.exit_day_ny == m.X
through = m.actual.isin(["inside_hold", "on_entry_day", "before_entry"])
desc = {"main": summ(main), "by_year": {str(y): summ(g) for y, g in main.groupby(main.entry_time.dt.year)},
        "by_sector": {s: summ(main[main.market.isin(v)]) for s, v in SECTORS.items()},
        "by_market": {k: summ(g) for k, g in main.groupby("market")},
        "by_reason": {r: int(n) for r, n in main.reason.value_counts().items()},
        "hold_tdays": {str(k): int(v) for k, v in main.hold_tdays.value_counts().sort_index().items()},
        "mean_hold_h": float(main.hold_h.mean()),
        "counts_total": {w: int(sum(c.get(w, 0) for c in main.attrs["counts"].values()))
                         for w in ("signals", "stale", "no_bar", "open_at_end", "no_d20", "overlap_skipped", "taken")},
        "exit_not_on_session_E-1": int((~m.exit_on_X).sum()),
        "exit_not_on_E-1_by_reason": {r: int(n) for r, n in m[~m.exit_on_X].reason.value_counts().items()},
        "actual_release_vs_expected": {k: int(v) for k, v in m.actual.value_counts().items()},
        "release_inside_hold_or_before": {"n": int(through.sum()), "with": summ(m), "without": summ(m[~through]),
                                          "only_those": summ(m[through])},
        "neighbours": {k: summ(v) for k, v in neigh.items()}, "every": summ(every),
        "null": {k: v for k, v in null.items() if k != "means"}}

res = judge.verdict(HERE, main, neigh, every, null, corr="compute", n_configs=len(cfgs), truncation=tr,
                    event_truncation=tre,
                    data_desc="39 US shares hourly bars 2017-2021 (kit v2.1, PROVISIONAL costs); EDGAR earnings calendar drop_late; expected date = reaction + 364 days",
                    extra={"descriptive": desc})
main.to_csv(os.path.join(CACHE, "main_trades.csv"), index=False)
m.to_csv(os.path.join(CACHE, "main_trades_matched.csv"), index=False)
print(json.dumps(desc["main"]))
print("release inside hold:", json.dumps(desc["release_inside_hold_or_before"]))
print("exit not on E-1:", desc["exit_not_on_session_E-1"], desc["exit_not_on_E-1_by_reason"])
print("verdict:", res["verdict"], "failed:", res["failed_bars"])
print(res["ledger_line"])
print("dividends:", json.dumps({k: v for k, v in res.get("dividends", {}).items() if k != "by_market"}))
print(f"done {time.time()-T0:.0f}s")
