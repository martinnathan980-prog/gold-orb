"""Idea 022: fade speculators COT net position at a three-year extreme (basket of 12 markets).
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/022_cot_extremes/run.py
Reads declared.json (never writes it): hash -> truncation -> main, neighbours, every-signal, null -> verdict.
Writes results.json and trials.jsonl (by kit.judge.verdict) and extra_figures.json (gross, sides, markets)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
from kit import checks, judge, sim, stats, data as D
import cot_lib as L

FOLDER = HERE
_FEAT = {}


def features(cot, win):
    key = (win, len(cot), str(cot.index.max()))
    if key not in _FEAT:
        _FEAT[key] = L.weekly_features(cot, win)
    return _FEAT[key]


def build(d, q=0.10, win=156):
    """WHOLE signal table: p >= 1-q -> sell, p <= q -> buy (flipped for usdjpy/usdcad/usdchf), known_at = the COT
    value's known-at time (= the entry time)."""
    w = features(d["cot"], win)
    p = w.p.to_numpy()
    ext = np.isfinite(p) & ((p >= 1 - q - 1e-12) | (p <= q + 1e-12))
    w = w[(pd.DatetimeIndex(w.index) >= L.START) & ext]
    flip = w.market.map(lambda m: L.FLIP.get(m, 1)).to_numpy()
    side = (np.where(w.p.to_numpy() >= 0.5, -1, 1) * flip).astype(int)
    out = pd.DataFrame({"known_at": pd.DatetimeIndex(w.index), "side": side, "market": w.market.to_numpy()})
    return out.sort_values(["known_at", "market"], kind="stable").reset_index(drop=True)


def side_market_figs(t):
    f = lambda x: {"n": int(len(x)), "PF_gross": stats.pf(x.R_gross), "PF": stats.pf(x.R), "PF_stress": stats.pf(x.R_stress),
                   "mean_R_gross": float(x.R_gross.mean()) if len(x) else None, "mean_R": float(x.R.mean()) if len(x) else None,
                   "sum_R": float(x.R.sum())}
    return {"all": f(t), "long": f(t[t.side > 0]), "short": f(t[t.side < 0]),
            "by_market": {m: f(g) for m, g in t.groupby("market")},
            "by_year_R_gross": {int(k): float(v) for k, v in stats.by_year(t, "R_gross").items()},
            "t_daily_gross": stats.t_stat(stats.daily_sums(t, "R_gross"))}


def main():
    decl = json.load(open(os.path.join(FOLDER, "declared.json")))
    checks.declared_hash(FOLDER)
    cfgs, mks = decl["configurations"], decl["markets"]
    d = {"cot": L.load_cot()}
    c0 = cfgs[0]
    b0 = lambda dd: build(dd, c0["p_extreme"], c0["p_window_weeks"])
    tr = checks.truncation_test(b0, d, ["2015-06-01 12:00", "2017-03-06 08:00", "2019-09-09 09:00", "2021-06-01"],
                                row_len={"cot": pd.Timedelta(0)})
    assert tr["pass"], tr
    sig = b0(d)
    print("signals", len(sig), "weeks", sig.known_at.nunique())
    bk = sim.books({m: D.load_bars(m) for m in mks})
    run = lambda s, c, mode="one": sim.simulate(s, bk, exit=tuple(c["exit"]), stop=tuple(c["stop"]), mode=mode)
    main_t = run(sig, c0)
    neigh = {c["id"]: run(build(d, c["p_extreme"], c["p_window_weeks"]), c) for c in cfgs[1:]}
    every = run(sig, c0, "every")
    null = stats.null_test(main_t, bk, exit=tuple(c0["exit"]), stop=tuple(c0["stop"]), n_draws=2000)
    shift = checks.shift_test(sig, bk, exit=tuple(c0["exit"]), stop=tuple(c0["stop"]))
    extra = {"shift_test": shift, "main_figures": side_market_figs(main_t),
             "neighbour_figures": {k: side_market_figs(t)["all"] for k, t in neigh.items()}}
    res = judge.verdict(FOLDER, main_t, neigh, every, null, corr="compute", n_configs=len(cfgs), truncation=tr,
                        data_desc="CFTC COT legacy (Socrata), H1 BID bars 2013-2021", extra=extra)
    json.dump(extra, open(os.path.join(FOLDER, "extra_figures.json"), "w"), indent=1, default=str)
    print(res["verdict"], res["failed_bars"])
    print(res["ledger_line"])
    print(json.dumps(extra["main_figures"], indent=1, default=str))
    print(json.dumps({k: {"value": v["value"], "pass": v["pass"]} for k, v in res["bars"].items()}, indent=1, default=str))
    print(json.dumps(res["neighbours"], indent=1))


if __name__ == "__main__":
    main()
