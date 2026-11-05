"""Deterministic audit of one finalist.

Usage:  python3 lab/audit/audit.py <track> <finalist_name> [--data patched|current]

Checks (results -> lab/results/audit/<track>__<name>.json):
  1. reproduction: IS / VAL metrics under the pre-registered costs
  2. cost scenarios: x1.5 stress + broker scenarios from lab/audit/cost_scenarios.json
  3. every-signal diagnostic (no_overlap=False)
  4. causality: orders rebuilt on data truncated at random cut points must equal the full-data
     orders for every order activated well before the cut
  5. tick fidelity: M1 zero-cost simulation vs tick-by-tick simulation (Jun-Dec 2025 ticks)
  6. statistics: bootstrap CI of PF / expectancy, deflated Sharpe ratio vs the track's trials
  7. breakdowns: by year, long/short, gold-trend regime at entry
"""
import importlib.util
import json
import math
import os
import sys
from dataclasses import asdict, replace

import numpy as np
import pandas as pd

LAB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, LAB)
import goldlab as gl  # noqa: E402
from goldlab.evalkit import is_criteria, stressed_costs, val_criteria  # noqa: E402
from goldlab.sim import COSTS, Costs  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tick_sim import covered_span, load_ticks, tick_simulate  # noqa: E402

OUT = os.path.join(LAB, "results", "audit")


def load_strategy(track):
    d = os.path.join(LAB, "tracks", track)
    sys.path.insert(0, d)
    spec = importlib.util.spec_from_file_location(f"strategy_{track}", os.path.join(d, "strategy.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod          # lets numba's on-disk cache re-import the module
    spec.loader.exec_module(mod)
    return mod


def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def norm_ppf(p):
    # Acklam's rational approximation (sufficient here)
    from scipy.stats import norm
    return float(norm.ppf(p))


def deflated_sharpe(R, trials_path):
    """Bailey & Lopez de Prado DSR on per-trade Sharpe, using the dispersion of the per-trade
    Sharpe ratios of all logged trials of the track."""
    R = np.asarray(R, float)
    R = R[np.isfinite(R)]
    T = len(R)
    sr = R.mean() / R.std(ddof=1)
    srs = []
    if os.path.exists(trials_path):
        for line in open(trials_path):
            try:
                m = json.loads(line)["is"]
                if m.get("n", 0) > 30 and m.get("t_stat") is not None:
                    srs.append(m["t_stat"] / math.sqrt(m["n"]))
            except Exception:
                pass
    N = max(len(srs), 1)
    v = float(np.var(srs, ddof=1)) if len(srs) > 2 else 0.0
    g = 0.5772156649
    sr0 = math.sqrt(v) * ((1 - g) * norm_ppf(1 - 1.0 / N) + g * norm_ppf(1 - 1.0 / (N * math.e))) if N > 1 else 0.0
    skew = float(pd.Series(R).skew())
    kurt = float(pd.Series(R).kurt()) + 3
    den = math.sqrt(max(1e-12, 1 - skew * sr + (kurt - 1) / 4 * sr * sr))
    dsr = norm_cdf((sr - sr0) * math.sqrt(T - 1) / den)
    psr = norm_cdf(sr * math.sqrt(T - 1) / den)
    return {"sr_per_trade": round(sr, 4), "n_trials": N, "sr_trials_sd": round(math.sqrt(v), 4),
            "sr0_expected_max": round(sr0, 4), "psr_vs_0": round(psr, 4), "dsr": round(dsr, 4)}


def bootstrap(R, n_boot=5000, seed=0):
    R = np.asarray(R, float)
    R = R[np.isfinite(R)]
    rng = np.random.default_rng(seed)
    pf, ex = [], []
    for _ in range(n_boot):
        s = R[rng.integers(0, len(R), len(R))]
        g, l = s[s > 0].sum(), -s[s < 0].sum()
        pf.append(g / l if l > 0 else np.nan)
        ex.append(s.mean())
    q = lambda a: [round(float(np.nanpercentile(a, p)), 3) for p in (5, 50, 95)]
    return {"pf_p5_p50_p95": q(pf), "exp_p5_p50_p95": q(ex), "p_exp_le_0": round(float(np.mean(np.array(ex) <= 0)), 4)}


def causality(mod, params, m1, cuts=5, seed=1, margin_days=8):
    """Rebuild orders on truncated data; orders activated > margin before the cut must match."""
    full = mod.make_orders(m1, **params).reset_index(drop=True)
    ts_full = m1.index[np.clip(full.entry_i.to_numpy(), 0, len(m1) - 1)]
    rng = np.random.default_rng(seed)
    lo, hi = int(len(m1) * 0.2), int(len(m1) * 0.95)
    res = []
    cols = [c for c in ("side", "etype", "level", "stop", "stop_dist", "target", "target_dist", "trail", "be")
            if c in full.columns]
    for cut in sorted(rng.integers(lo, hi, cuts)):
        sub = m1.iloc[:cut]
        o = mod.make_orders(sub, **params).reset_index(drop=True)
        lim = sub.index[-1] - pd.Timedelta(days=margin_days)
        a = full[(ts_full <= lim)].copy()
        ts_o = sub.index[np.clip(o.entry_i.to_numpy(), 0, len(sub) - 1)]
        b = o[(ts_o <= lim)].copy()
        same_n = len(a) == len(b)
        mism = None
        if same_n and len(a):
            ea = a.entry_i.to_numpy()
            eb = b.entry_i.to_numpy()
            ok = np.array_equal(ea, eb)
            for c in cols:
                x, y = a[c].to_numpy(float), b[c].to_numpy(float)
                ok &= bool(np.all((np.isclose(x, y, rtol=0, atol=1e-9)) | (np.isnan(x) & np.isnan(y))))
            mism = not ok
        res.append({"cut": str(sub.index[-1]), "n_full": int(len(a)), "n_trunc": int(len(b)),
                    "identical": bool(same_n and not mism)})
    return {"cuts": res, "pass": all(r["identical"] for r in res)}


def regime_split(t, m1):
    d = gl.bars(m1, "D")
    ma = d.c.rolling(60).mean()
    up = (d.c > ma).astype(float)
    up.index = d.t_close
    lab = up.reindex(pd.DatetimeIndex(t.entry_time), method="ffill").to_numpy()
    out = {}
    for name, mask in (("gold_above_60d_ma", lab == 1), ("gold_below_60d_ma", lab == 0)):
        sub = t[mask]
        for side, sname in ((1, "long"), (-1, "short")):
            s = sub[sub.side == side]
            if len(s):
                out[f"{name}/{sname}"] = {"n": int(len(s)), "R": round(float(s.R.sum()), 1),
                                          "pf": gl.report(s)["pf"] if len(s) > 2 else None}
    return out


def main():
    track, name = sys.argv[1], sys.argv[2]
    mod = load_strategy(track)
    params = mod.FINALISTS[name]
    m1 = gl.load_m1("xauusd")
    orders = mod.make_orders(m1, **params)
    res = {"track": track, "name": name, "params": {k: (None if isinstance(v, float) and math.isnan(v) else v)
                                                     for k, v in params.items()}}
    lab = f"audit:{track}:{name}"

    def run(costs=None, no_overlap=True):
        return gl.simulate(m1, orders, sym="xauusd", costs=costs, no_overlap=no_overlap)

    t = run()
    rep_is, rep_val = gl.report(gl.cut(t, "is")), gl.report(gl.cut(t, "val", track="audit", label=lab))
    ts_ = run(stressed_costs("xauusd"))
    res["prereg"] = {"is": rep_is, "val": rep_val,
                     "is_criteria": is_criteria(rep_is, gl.report(gl.cut(ts_, "is"))),
                     "val_criteria": val_criteria(rep_val)}
    res["stress_x1.5"] = {"is": gl.report(gl.cut(ts_, "is")),
                          "val": gl.report(gl.cut(ts_, "val", track="audit", label=lab))}
    scen_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cost_scenarios.json")
    res["scenarios"] = {}
    if os.path.exists(scen_path):
        for sname, c in json.load(open(scen_path)).items():
            cc = Costs(**c)
            tt = run(cc)
            ri = gl.report(gl.cut(tt, "is"))
            rv = gl.report(gl.cut(tt, "val", track="audit", label=lab))
            stress = replace(cc, commission=cc.commission * 1.5, slip_bps=cc.slip_bps * 1.5,
                             spread_mult=cc.spread_mult * 1.5)
            rs = gl.report(gl.cut(run(stress), "is"))
            res["scenarios"][sname] = {"costs": c, "is": ri, "val": rv,
                                       "is_criteria": is_criteria(ri, rs), "val_criteria": val_criteria(rv)}
    te = run(no_overlap=False)
    res["every_signal"] = {"is": gl.report(gl.cut(te, "is")),
                           "val": gl.report(gl.cut(te, "val", track="audit", label=lab))}
    res["causality"] = causality(mod, params, m1)
    # tick fidelity on the trades the M1 simulator actually took in Jun-Dec 2025
    ticks = load_ticks()
    t0 = run(Costs(commission=0, slip_bps=0, swap_long=0, swap_short=0))
    win = t0[(t0.entry_time >= pd.Timestamp("2025-06-01", tz="UTC"))]
    act = m1.index[np.clip(orders.reset_index(drop=True).loc[win.index, "entry_i"].to_numpy(), 0, len(m1) - 1)]
    cov = covered_span(pd.DatetimeIndex(act).as_unit("ns").asi8,
                       pd.DatetimeIndex(win.exit_time).as_unit("ns").asi8 + 3600 * 10**9, ticks[0])
    win = win[cov]
    if len(win):
        o = orders.reset_index(drop=True).loc[win.index]
        tk = tick_simulate(m1, o, ticks)
        both = win.join(tk, rsuffix="_tick")
        both = both[np.isfinite(both.pnl_tick)]
        d = both.pnl - both.pnl_tick
        res["tick_fidelity"] = {"n": int(len(both)), "mean_m1_minus_tick_usd": round(float(d.mean()), 3),
                                "median": round(float(d.median()), 3),
                                "share_m1_better": round(float((d > 0.05).mean()), 3),
                                "share_m1_worse": round(float((d < -0.05).mean()), 3),
                                "m1_R_sum": round(float((both.pnl / both.risk).sum()), 2),
                                "tick_R_sum": round(float((both.pnl_tick / both.risk).sum()), 2),
                                "slippage_budget_per_trade_usd": round(float(
                                    (both.entry * COSTS["xauusd"].slip_bps * 1e-4 * 2).mean()), 3)}
    else:
        res["tick_fidelity"] = {"n": 0}
    R_is = gl.cut(t, "is").R.to_numpy()
    res["bootstrap_is"] = bootstrap(R_is)
    res["bootstrap_val"] = bootstrap(gl.cut(t, "val", track="audit", label=lab).R.to_numpy())
    res["deflated_sharpe_is"] = deflated_sharpe(R_is, os.path.join(LAB, "results", track, "trials.jsonl"))
    res["regimes_is"] = regime_split(gl.cut(t, "is"), m1)
    res["regimes_val"] = regime_split(gl.cut(t, "val", track="audit", label=lab), m1)
    top = t.sort_values("R", ascending=False)
    k = max(1, int(0.05 * len(t)))
    res["top5pct_share_of_total_R"] = round(float(top.R.iloc[:k].sum() / t.R.sum()), 2) if t.R.sum() else None
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, f"{track}__{name}.json"), "w") as f:
        json.dump(res, f, indent=1, default=str)
    keys = ("n", "trades_per_year", "win_rate", "pf", "t_stat", "expectancy_R", "years_pos", "long_R", "short_R")
    print(f"== {track}/{name}")
    for blk in ("prereg", "stress_x1.5", "every_signal"):
        for per in ("is", "val"):
            r = res[blk][per]
            print(f"{blk:13s} {per:3s}", {k: r.get(k) for k in keys})
    for sname, s in res["scenarios"].items():
        for per in ("is", "val"):
            r = s[per]
            print(f"{sname:13s} {per:3s}", {k: r.get(k) for k in keys})
        print(f"{sname:13s} IS crit pass={s['is_criteria']['pass']} VAL pass={s['val_criteria']['pass']}")
    print("prereg IS crit:", res["prereg"]["is_criteria"], "VAL:", res["prereg"]["val_criteria"])
    print("causality:", res["causality"])
    print("tick:", res["tick_fidelity"])
    print("bootstrap IS:", res["bootstrap_is"], "| VAL:", res["bootstrap_val"])
    print("DSR IS:", res["deflated_sharpe_is"])
    print("regimes IS:", res["regimes_is"])
    print("regimes VAL:", res["regimes_val"])
    print("top5% share:", res["top5pct_share_of_total_R"])


if __name__ == "__main__":
    main()
