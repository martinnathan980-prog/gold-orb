"""Idea 052 (earnings drift) in sample. Reads declared.json (never writes it).
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/052_earnings_drift/run.py"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
from kit import checks, judge, sim, stats
import signals as S

T0 = time.time()
decl = json.load(open(os.path.join(HERE, "declared.json")))
checks.declared_hash(HERE)
cfgs = decl["configurations"]
main_c = cfgs[0]
d = S.load_data()
print(f"data loaded {time.time()-T0:.0f}s")

tr = checks.truncation_test(lambda x: S.build(x, main_c["threshold"]), d, row_len=S.row_len(d),
                            cols=("known_at", "side"))
print(f"truncation pass={tr['pass']} {time.time()-T0:.0f}s", {k: v for k, v in tr.items() if k.startswith("n_")})
assert tr["pass"], tr

bk = sim.books({k: v for k, v in d.items() if k != "cal"})
sigs = {}
def sig_for(th):
    if th not in sigs:
        sigs[th] = S.build(d, th)
    return sigs[th]

def run(c, mode="one"):
    return sim.simulate(sig_for(c["threshold"]), bk, exit=tuple(c["exit"]), stop=tuple(c["stop"]), mode=mode,
                        max_wait_h=2)

main = run(main_c)
neigh = {c["id"]: run(c) for c in cfgs[1:]}
every = run(main_c, "every")
print(f"simulated {time.time()-T0:.0f}s; main n={len(main)}")
null = stats.null_test(main, bk, exit=tuple(main_c["exit"]), stop=tuple(main_c["stop"]), n_draws=2000)
print(f"null pct {null['percentile']:.1f} {time.time()-T0:.0f}s")

# descriptive figures (not judged)
def pf(x):
    x = np.asarray(x, float); g, l = x[x > 0].sum(), -x[x < 0].sum()
    return float(g / l) if l > 0 else None
def summ(t):
    if not len(t):
        return {"n": 0}
    return {"n": int(len(t)), "mean_R": float(t.R.mean()), "PF_net": pf(t.R), "mean_R_gross": float(t.R_gross.mean()),
            "PF_gross": pf(t.R_gross), "mean_net_bp": float(t.net_bp.mean()), "mean_gross_bp": float(t.gross_bp.mean()),
            "PF_stress": pf(t.R_stress), "win_rate_net": float((t.R > 0).mean())}
SECTORS = {"tech": "aapl adbe amd avgo crm csco intc msft mu nvda orcl qcom".split(),
           "internet_media": "amzn baba fb googl nflx dis pypl tsla".split(),
           "finance": "bac c gs jpm ma v wfc".split(),
           "health": "jnj mrk pfe unh".split(),
           "industry_energy_consumer": "ba cat ge cvx xom hd mcd nke wmt".split()}
desc = {"main": summ(main), "long": summ(main[main.side > 0]), "short": summ(main[main.side < 0]),
        "by_year": {str(y): summ(g) for y, g in main.groupby(main.entry_time.dt.year)},
        "by_sector": {s: summ(main[main.market.isin(v)]) for s, v in SECTORS.items()},
        "by_market": {m: summ(g) for m, g in main.groupby("market")},
        "by_reason": {r: int(n) for r, n in main.reason.value_counts().items()},
        "hold_tdays": {str(k): int(v) for k, v in main.hold_tdays.value_counts().sort_index().items()},
        "counts": main.attrs.get("counts"),
        "neighbours": {k: summ(v) for k, v in neigh.items()}, "every": summ(every),
        "move_size": {}}
mv = S.moves(d)
mv = mv[mv.move.abs() >= main_c["threshold"]].set_index(["market", "known_at"])["move"]
mm = main.set_index(["market", "known_at"]).join(mv.rename("move"))
for lo, hi in ((0.03, 0.05), (0.05, 0.08), (0.08, 1.0)):
    g = mm[(mm.move.abs() >= lo) & (mm.move.abs() < hi)]
    desc["move_size"][f"{lo}-{hi}"] = summ(g.reset_index())

res = judge.verdict(HERE, main, neigh, every, null, corr="compute", n_configs=len(cfgs), truncation=tr,
                    data_desc="40 US shares hourly bars 2017-2021 (kit v2.1, PROVISIONAL costs); EDGAR earnings calendar drop_late",
                    extra={"descriptive": desc, "null_detail": {k: v for k, v in null.items() if k != "draws"}})
main.to_csv(os.path.expanduser("~/explore_data/idea_052/main_trades.csv"), index=False)
print(json.dumps(desc["main"]), "\nlong", json.dumps(desc["long"]), "\nshort", json.dumps(desc["short"]))
print("verdict:", res["verdict"], "failed:", res["failed_bars"])
print(res["ledger_line"])
print("dividends:", json.dumps({k: v for k, v in res.get("dividends", {}).items() if k != "by_market"}))
print(f"done {time.time()-T0:.0f}s")
