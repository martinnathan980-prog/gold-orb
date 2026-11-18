"""Idea 015: seven hedged pairs, fade a 20-day z-score stretch of the pair's 16:00-NY log price (scout ideas 1, 3, 4).
Reads declared.json (never writes it). Run:
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/015_seven_pairs_reversion/run.py
"""
import json, os, sys, time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import numpy as np, pandas as pd
from kit import checks, data, judge, sim, stats

FOLDER = os.path.dirname(os.path.abspath(__file__))
DECL = json.load(open(os.path.join(FOLDER, "declared.json")))
PAIRS = DECL["pairs"]                       # name -> [leg_a, leg_b, kind, group]
LEGS = sorted({p[0] for p in PAIRS.values()} | {p[1] for p in PAIRS.values()})
GROUP = {k: v[3].split(" (")[0] for k, v in PAIRS.items()}


def load():
    d = {}
    for k in LEGS:
        b = data.load_bars(k)[["open", "high", "low", "close"]].copy()
        loc = b.index.tz_convert("America/New_York")
        # the bar that OPENS at 15:00 New York (closes at 16:00 NY), Monday-Friday: a function of the bar's own stamp
        b["is1500"] = (loc.hour == 15) & (loc.minute == 0) & (loc.dayofweek < 5)
        d[k] = b
    return d


def close16(b):
    """BID close of the 15:00-NY bar, indexed by the time it is KNOWN (bar open + 1 h = 16:00 NY)."""
    s = b["close"][b["is1500"].to_numpy()]
    return pd.Series(s.to_numpy(float), index=s.index + pd.Timedelta(hours=1))


def zscores(d, lookback):
    out = {}
    for nm, (a, b_, kind, _) in PAIRS.items():
        j = pd.concat([close16(d[a]), close16(d[b_])], axis=1, join="inner").dropna()
        x = j.iloc[:, 0].to_numpy() / j.iloc[:, 1].to_numpy() if kind == "ratio" else j.iloc[:, 0].to_numpy() * j.iloc[:, 1].to_numpy()
        c = pd.Series(np.log(x), index=j.index)
        prev = c.shift(1).rolling(lookback, min_periods=lookback)      # the `lookback` PREVIOUS days only
        out[nm] = (c - prev.mean()) / prev.std(ddof=1)
    return out


def build(d, lookback=20, z_in=2.0):
    rows = []
    for nm, z in zscores(d, lookback).items():
        m = (z.abs() >= z_in).to_numpy()
        rows.append(pd.DataFrame({"known_at": z.index[m], "side": -np.sign(z.to_numpy()[m]).astype(int), "market": nm}))
    return pd.concat(rows, ignore_index=True).sort_values(["known_at", "market"]).reset_index(drop=True)


def build_events(d, lookback=20, z_out=0.5):
    rows = []
    for nm, z in zscores(d, lookback).items():
        m = (z.abs() <= z_out).to_numpy()
        rows.append(pd.DataFrame({"known_at": z.index[m], "market": nm}))
    return pd.concat(rows, ignore_index=True).sort_values(["known_at", "market"]).reset_index(drop=True)


def figs(t):
    if len(t) == 0:
        return {"n": 0}
    s = stats.summary(t)
    keep = ("n", "PF_gross", "PF", "PF_stress", "mean_R", "mean_R_gross", "mean_R_stress", "mean_gross_bp", "mean_net_bp",
            "t_trade", "t_daily", "years_positive_frac", "by_year_R", "exit_reasons", "long_n", "long_R", "short_n",
            "short_R", "hold_h_mean")
    out = {k: s[k] for k in keep if k in s}
    out["sum_R"] = float(t.R.sum()); out["sum_R_gross"] = float(t.R_gross.sum())
    for sd, nm in ((1, "long"), (-1, "short")):
        u = t[t.side == sd]
        out[nm] = {"n": int(len(u)), "PF": stats.pf(u.R) if len(u) else None, "PF_gross": stats.pf(u.R_gross) if len(u) else None,
                   "mean_R": float(u.R.mean()) if len(u) else None, "mean_R_gross": float(u.R_gross.mean()) if len(u) else None}
    return out


def main():
    t0 = time.time()
    checks.declared_hash(FOLDER)
    cfgs = DECL["configurations"]
    d = load()
    rl = {k: pd.Timedelta(hours=1) for k in d}
    c0 = cfgs[0]
    bmain = lambda dd: build(dd, c0["lookback"], c0["z_in"])
    emain = lambda dd: build_events(dd, c0["lookback"], c0["z_out"])
    tr = checks.truncation_test(bmain, d, row_len=rl, cols=("known_at", "side"))
    print("truncation signals:", tr["pass"], {k: tr[k] for k in tr if k.startswith("n_")}, f"{time.time()-t0:.0f}s")
    tre = checks.truncation_test(emain, d, row_len=rl, cols=("known_at",))
    print("truncation events:", tre["pass"], {k: tre[k] for k in tre if k.startswith("n_")}, f"{time.time()-t0:.0f}s")
    assert tr["pass"] and tre["pass"]

    lb = sim.books({k: v[["open", "high", "low", "close"]] for k, v in d.items()})
    bk = {nm: sim.pair_book(nm, a, b_, lb[a], lb[b_], kind=kind) for nm, (a, b_, kind, _) in PAIRS.items()}
    cache = {}

    def run(c, mode="one"):
        key_s, key_e = (c["lookback"], c["z_in"]), (c["lookback"], c["z_out"])
        if ("s",) + key_s not in cache:
            cache[("s",) + key_s] = build(d, *key_s)
        if ("e",) + key_e not in cache:
            cache[("e",) + key_e] = build_events(d, *key_e)
        rule = dict(exit=sim.event_exit(cache[("e",) + key_e], tuple(c["max_hold"])), stop=tuple(c["stop"]))
        return sim.simulate(cache[("s",) + key_s], bk, mode=mode, **rule), rule, cache[("s",) + key_s]

    main_t, rule, sig = run(c0)
    sig_full = bmain(d)
    assert sim.signals_sha(sig_full) == sim.signals_sha(sig)
    neigh = {c["id"]: run(c)[0] for c in cfgs[1:]}
    every = run(c0, "every")[0]
    print("simulated", len(main_t), "main trades;", {k: len(v) for k, v in neigh.items()}, f"{time.time()-t0:.0f}s")
    null = stats.null_test(main_t, bk, n_draws=2000, **rule)
    print("null pct", null.get("percentile"), "joint groups", null.get("joint_groups"), f"{time.time()-t0:.0f}s")

    extra = {"counts": main_t.attrs["counts"],
             "per_pair": {m: figs(main_t[main_t.market == m]) for m in PAIRS},
             "per_group": {g: figs(main_t[main_t.market.map(GROUP) == g]) for g in sorted(set(GROUP.values()))},
             "basket": figs(main_t),
             "neighbours": {k: {"n": int(len(v)), "PF": stats.pf(v.R), "PF_gross": stats.pf(v.R_gross),
                                "t_daily": stats.t_stat(stats.daily_sums(v))} for k, v in neigh.items()},
             "every_signal": {"n": int(len(every)), "mean_R": float(every.R.mean()), "mean_R_gross": float(every.R_gross.mean())}}
    res = judge.verdict(FOLDER, main_t, neigh, every, null, truncation=tr, event_truncation=tre, n_configs=len(cfgs),
                        data_desc="prices only; prepared H1 BID bars of 12 legs 2013-2021, 7 hedged pairs",
                        extra=extra)
    print("VERDICT:", res["verdict"], "failed:", res["failed_bars"])
    print(res["ledger_line"])
    for m, f in extra["per_pair"].items():
        print(f"  {m:15s} n {f['n']:4d} PFg {f.get('PF_gross', 0):.2f} PF {f.get('PF', 0):.2f} sumR {f.get('sum_R', 0):7.1f} "
              f"sumRg {f.get('sum_R_gross', 0):7.1f} long {f['long']['mean_R']} short {f['short']['mean_R']}")
    for g, f in extra["per_group"].items():
        print(f"  [{g}] n {f['n']} PFg {f['PF_gross']:.2f} PF {f['PF']:.2f} PFs {f['PF_stress']:.2f} t_daily {f['t_daily']:.2f}")
    b = extra["basket"]
    print(f"  basket gross PF {b['PF_gross']:.3f} meanRg {b['mean_R_gross']:.3f} net PF {b['PF']:.3f} meanR {b['mean_R']:.3f}; "
          f"long {b['long']} short {b['short']}")
    print("neighbours", extra["neighbours"])
    print(f"done {time.time()-t0:.0f}s")
    return res


if __name__ == "__main__":
    main()
