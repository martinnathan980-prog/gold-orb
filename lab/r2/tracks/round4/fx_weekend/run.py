"""Runs the eleven declared configurations (declared.json), IN SAMPLE ONLY, and nothing else.

  (1) main  (2)-(9) neighbours  (10) main at costs x1.5  (11) random-entry null, 200 replays, pooled
Every configuration is one line of results/r2/round4/fx_weekend/trials.jsonl, written whatever its result.
Information reported from the main's trades only (no new configuration): USD side, |z| >= 1.5 vs the rest, the mean
path at Sunday 22:00 / Monday 03:00, 08:00, 16:00 NY, the net result split into mid-to-mid move and cost paid.

    PYTHONDONTWRITEBYTECODE=1 NUMBA_CACHE_DIR=/tmp/... python3 run.py
"""
import gc
import json
import os
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import wkfade as W  # noqa: E402
from goldlab import r2  # noqa: E402
from goldlab.sim import simulate  # noqa: E402

DECL = json.load(open(os.path.join(W.RES, "declared.json")))
PRE = json.load(open(os.path.join(W.RES, "precheck.json")))
KEPT = PRE["kept"]
CFG = {c["id"]: c for c in DECL["configurations"]}
TRIALS = os.path.join(W.RES, "trials.jsonl")
PATH_TIMES = [("sun_22:00", 0, "22:00"), ("mon_03:00", 1, "03:00"), ("mon_08:00", 1, "08:00"), ("mon_16:00", 1, "16:00")]
KEEP_COLS = ["sym", "side", "entry_time", "exit_time", "entry", "exit", "stop", "reason", "swap", "pnl", "risk", "R",
             "ret", "hold_min", "sunday", "z", "thr", "F", "P", "sigma", "atr", "mfe", "mae"]


def dkey(p):
    return (p["dec"], p["q"])


def path_and_costs(m1, t):
    """Mean path (unstopped mid move from the entry bar's mid open, in the trade's direction) and cost accounting of
    the main's trades on the FP frame (half spread of the entry and exit bars + slippage + swap)."""
    idx = W.naive_utc(m1)
    N = len(idx)
    bo, ao = m1["bo"].to_numpy(float), m1["ao"].to_numpy(float)
    mid_o = (bo + ao) / 2
    hs = (ao - bo) / 2
    et = t.entry_time.dt.tz_convert("UTC").dt.tz_localize(None).values.astype("datetime64[ns]")
    ji = np.searchsorted(idx, et)
    assert (idx[ji] == et).all()
    m_in = mid_o[ji]
    side = t.side.to_numpy()
    risk = t.risk.to_numpy(float)
    out = pd.DataFrame(index=t.index)
    S = pd.DatetimeIndex(t["sunday"].to_numpy())
    xt = t.exit_time.dt.tz_convert("UTC").dt.tz_localize(None).values.astype("datetime64[ns]")
    stopped = (t.reason.to_numpy() == "stop")
    for name, add, hhmm in PATH_TIMES:
        tt = W.wall(S, add, hhmm)
        j = np.minimum(np.searchsorted(idx, tt), N - 1)
        mv = side * (mid_o[j] - m_in)
        out[f"{name}_R"] = mv / risk
        out[f"{name}_bp"] = side * np.log(mid_o[j] / m_in) * 1e4
        out[f"{name}_stopped"] = stopped & (xt <= tt)
    # cost accounting (exact on FP frames: one spread per bar)
    is_time = t.reason.to_numpy() == "time"
    xb = np.searchsorted(idx, xt - np.where(is_time, 0, 1) * W.M)
    fill_in = t.entry.to_numpy(float)
    fill_out = t.exit.to_numpy(float)
    cost_in = side * (fill_in - m_in)                       # half spread + market slippage
    # exit fill is a bid (long) / ask (short) price on bar xb: its mid equivalent is fill +/- that bar's half spread,
    # before slippage: fill_out = px * (1 -/+ slip)  ->  cost_out = hs + |px - fill_out|
    c = r2.costs(t["sym"].iloc[0])
    slip_rate = np.where(is_time, c.slip_mkt_bps, c.slip_bps) * 1e-4
    px = np.where(side > 0, fill_out / (1 - slip_rate), fill_out / (1 + slip_rate))
    cost_out = hs[xb] + np.abs(px - fill_out)
    cost = cost_in + cost_out + t.swap.to_numpy(float)
    out["cost_R"] = cost / risk
    out["cost_bp"] = cost / fill_in * 1e4
    out["gross_R"] = t.R.to_numpy(float) + out["cost_R"].to_numpy()
    out["spread_in_bp"] = 2 * hs[ji] / m_in * 1e4
    return out


def main():
    t0 = time.time()
    assert not os.path.exists(TRIALS), "trials.jsonl exists: the declared configurations run once"
    params = {i: dict(CFG[i]["params"]) for i in CFG}
    trades = {i: [] for i in range(1, 11)}
    every = []
    info = {i: {"orders": 0, "refused_3spreads": 0, "signals": 0, "decided": 0} for i in range(1, 11)}
    rng = np.random.default_rng(CFG[11]["null"]["seed"])
    n_rep = CFG[11]["null"]["replays"]
    null_sum = np.zeros(n_rep)
    null_cnt = np.zeros(n_rep)
    null_refused = 0
    null_pool = {}
    extra = []
    dec_main = []
    for sym in KEPT:
        m1 = W.load_is(sym)
        daily = W.daily_table(m1)
        dtabs = {}
        for i in range(1, 10):
            k = dkey(params[i])
            if k not in dtabs:
                dtabs[k] = W.decisions(m1, dec=params[i]["dec"], q=params[i]["q"], daily=daily)
        for i in range(1, 10):
            t, o = W.run_config(m1, sym, params[i], "fp", dtab=dtabs[dkey(params[i])])
            info[i]["orders"] += len(o)
            info[i]["refused_3spreads"] += o.attrs.get("refused_3spreads", 0)
            info[i]["signals"] += o.attrs.get("signals", 0)
            info[i]["decided"] += o.attrs.get("decided", 0)
            if len(t):
                trades[i].append(t)
            if i == 1:
                te, _ = W.run_config(m1, sym, params[1], "fp", dtab=dtabs[dkey(params[1])], no_overlap=False)
                every.append(te)
                tm = t
                d = dtabs[dkey(params[1])].copy()
                d["sym"] = sym
                dec_main.append(d)
        # (10) cost stress: decisions rebuilt on the widened quotes (mids unchanged)
        t, o = W.run_config(m1, sym, params[10], "stress")
        info[10]["orders"] += len(o)
        info[10]["refused_3spreads"] += o.attrs.get("refused_3spreads", 0)
        info[10]["signals"] += o.attrs.get("signals", 0)
        info[10]["decided"] += o.attrs.get("decided", 0)
        if len(t):
            trades[10].append(t)
        # information from the main's trades
        if len(tm):
            ex = path_and_costs(m1, tm)
            ex["sym"] = sym
            extra.append(ex)
        # (11) null: random decision weekends of the main, same pair / side / relative stop / clock / hold
        d = dtabs[dkey(params[1])]
        xi, _ = W.exit_bars(m1, d, params[1]["exit"])
        jE = d["jE"].to_numpy()
        pool = np.flatnonzero(d["decided"].to_numpy() & d["okE"].to_numpy() & (xi > jE))
        null_pool[sym] = int(len(pool))
        if len(tm) and len(pool):
            mid_o = (m1["bo"].to_numpy(float) + m1["ao"].to_numpy(float)) / 2
            spr = m1["ao"].to_numpy(float) - m1["bo"].to_numpy(float)
            n = len(tm)
            draws = rng.integers(0, len(pool), size=(n_rep, n))
            wk = pool[draws.ravel()]
            ei = jE[wk].astype(np.int64)
            sd = np.tile((tm.risk / tm.entry).to_numpy(float), n_rep) * mid_o[ei]
            no = pd.DataFrame({"entry_i": ei, "side": np.tile(tm.side.to_numpy(np.int64), n_rep), "etype": 0,
                               "stop_dist": sd, "exit_i": xi[wk].astype(np.int64),
                               "rep": np.repeat(np.arange(n_rep), n)})
            bad = no.stop_dist.to_numpy() < 3 * spr[ei]
            null_refused += int(bad.sum())
            no = no[~bad]
            tn = simulate(m1, no, sym=sym, costs=r2.costs(sym), no_overlap=False)
            tn = tn[tn.entry_time < W.IS_END]
            g = tn.groupby("rep")["R"].agg(["sum", "count"]).reindex(np.arange(n_rep), fill_value=0)
            null_sum += g["sum"].to_numpy()
            null_cnt += g["count"].to_numpy()
        print(f"{sym}: main n {len(tm)}  stress n {len(t)}  pool {len(pool)}  {time.time() - t0:.0f}s", flush=True)
        del m1, daily, dtabs
        gc.collect()

    T = {i: pd.concat(trades[i], ignore_index=True) for i in trades if trades[i]}
    TE = pd.concat(every, ignore_index=True)
    EX = pd.concat(extra)
    pooled = {i: W.pooled(T[i], KEPT) for i in T}
    every_s = W.pooled(TE, KEPT)
    rule_mean = float(T[1]["R"].mean())
    null_means = null_sum / np.maximum(null_cnt, 1)
    pct = float((null_means < rule_mean).mean() * 100)
    null_res = {"replays": n_rep, "seed": CFG[11]["null"]["seed"], "rule_mean_R": round(rule_mean, 4),
                "null_mean_R": round(float(null_means.mean()), 4), "null_sd_R": round(float(null_means.std(ddof=1)), 4),
                "null_p2.5_R": round(float(np.percentile(null_means, 2.5)), 4),
                "null_p50_R": round(float(np.percentile(null_means, 50)), 4),
                "null_p95_R": round(float(np.percentile(null_means, 95)), 4),
                "null_p97.5_R": round(float(np.percentile(null_means, 97.5)), 4),
                "null_max_R": round(float(null_means.max()), 4), "null_min_R": round(float(null_means.min()), 4),
                "percentile": round(pct, 1), "pass": bool(pct >= 97.5),
                "trades_per_replay_mean": round(float(null_cnt.mean()), 1), "refused_3spreads": null_refused,
                "weekend_pool_per_pair": null_pool}

    # ---- trials.jsonl: one line per declared configuration, losing ones too
    lines = []
    for i in range(1, 11):
        c = CFG[i]
        row = {"id": i, "label": c["label"], "role": c["role"], "params": c["params"], "costs": c["costs"],
               "pairs": KEPT, "period": "decisions 2013-2021 (first trades after the 52-weekend warm-up), entries < 2022-01-01",
               **info[i], "pooled": pooled.get(i, {"n": 0})}
        if i == 1:
            row["every_signal"] = {k: every_s[k] for k in ("n", "pf", "expectancy_R", "total_R", "t_daily")}
        lines.append(row)
    lines.append({"id": 11, "label": CFG[11]["label"], "role": "null", "params": CFG[11]["params"], "costs": "fp",
                  "pairs": KEPT, "null": null_res})
    with open(TRIALS, "w") as f:
        for row in lines:
            f.write(json.dumps(row, default=W._js) + "\n")

    # ---- criteria on the main
    p1, p10 = pooled[1], pooled[10]
    nb = [pooled[i]["pf"] for i in range(2, 10)]
    nb_med = float(np.median(nb))
    yp, yn = (int(x) for x in p1["years_pos"].split("/"))
    pp, pn = (int(x) for x in p1["pairs_pos"].split("/"))
    crit = [
        ("t on daily (Monday) sums >= 2.5", p1["t_daily"], p1["t_daily"] >= 2.5),
        ("pooled PF >= 1.12", p1["pf"], p1["pf"] >= 1.12),
        ("pooled PF >= 1.04 at costs x1.5", p10["pf"], p10["pf"] >= 1.04),
        (">= 60 % of years positive", p1["years_pos"], yp >= 0.6 * yn),
        (">= 6 of 8 pairs positive", p1["pairs_pos"], pp >= 0.65 * pn),
        ("no pair above 25 % of the profit", p1["max_pair_share"],
         p1["max_pair_share"] is not None and p1["max_pair_share"] <= 0.25),
        ("neighbours' median PF >= 1.06", round(nb_med, 3), nb_med >= 1.06),
        ("every-signal expectancy > 0", every_s["expectancy_R"], every_s["expectancy_R"] > 0),
        ("null >= 97.5th percentile", pct, pct >= 97.5),
        ("n >= 250", p1["n"], p1["n"] >= 250),
        ("max hold <= 5 trading days", p1["max_hold_h"], p1["max_hold_h"] <= 5 * 24 + 72),
    ]
    criteria = [{"criterion": a, "value": b, "pass": bool(c)} for a, b, c in crit]
    passes = all(c["pass"] for c in criteria)

    # ---- information from the main's trades (no new configuration)
    M1 = T[1].copy()
    M1["usd"] = [W.usd_side(s, int(x)) for s, x in zip(M1.sym, M1.side)]
    info_main = {
        "usd_side": {"long_usd": W.small(M1[M1.usd > 0]), "short_usd": W.small(M1[M1.usd < 0]),
                     "cross_eurjpy": W.small(M1[M1.usd == 0])},
        "abs_z_ge_1.5": W.small(M1[M1.z.abs() >= 1.5]), "abs_z_lt_1.5": W.small(M1[M1.z.abs() < 1.5]),
        "side": {"long_pair": W.small(M1[M1.side > 0]), "short_pair": W.small(M1[M1.side < 0])},
        "fade_of_up_weekend (z>0, short)": W.small(M1[M1.z > 0]), "fade_of_down_weekend (z<0, long)": W.small(M1[M1.z < 0]),
        "z_abs_distribution": {q: round(float(np.percentile(M1.z.abs(), q)), 3) for q in (5, 25, 50, 75, 95)},
        "threshold_distribution": {q: round(float(np.percentile(M1.thr, q)), 3) for q in (5, 25, 50, 75, 95)},
        "stop_bp": {q: round(float(np.percentile(M1.risk / M1.entry * 1e4, q)), 1) for q in (5, 25, 50, 75, 95)},
        "signals_per_weekend": {str(k): int(v) for k, v in M1.groupby("sunday").size().value_counts().sort_index().items()},
        "weekends_with_a_trade": int(M1.sunday.nunique()),
    }
    al = EX.loc[M1.index] if False else EX
    mp = {}
    for name, _, _ in PATH_TIMES:
        mp[name] = {"mean_move_R": round(float(al[f"{name}_R"].mean()), 4), "mean_move_bp": round(float(al[f"{name}_bp"].mean()), 2),
                    "median_move_bp": round(float(al[f"{name}_bp"].median()), 2),
                    "share_stopped_pct": round(float(al[f"{name}_stopped"].mean() * 100), 1),
                    "mean_move_R_not_stopped": round(float(al.loc[~al[f"{name}_stopped"], f"{name}_R"].mean()), 4)}
    info_main["mean_path_unstopped_mid_from_entry"] = mp
    info_main["cost_accounting"] = {
        "net_R_per_trade": round(float(M1.R.mean()), 4), "cost_R_per_trade": round(float(EX.cost_R.mean()), 4),
        "mid_to_mid_R_per_trade": round(float(EX.gross_R.mean()), 4),
        "net_bp_per_trade": round(float((M1.pnl / M1.entry).mean() * 1e4), 2),
        "cost_bp_per_trade": round(float(EX.cost_bp.mean()), 2),
        "mid_to_mid_bp_per_trade": round(float((M1.pnl / M1.entry).mean() * 1e4 + EX.cost_bp.mean()), 2),
        "entry_bar_spread_bp_median": round(float(EX.spread_in_bp.median()), 3),
        "entry_bar_spread_bp_mean": round(float(EX.spread_in_bp.mean()), 3),
        "pf_mid_to_mid": round(W._pf(EX.gross_R.to_numpy()), 3),
        "note": "accounting of the same trades (half spread of the entry and exit bars + slippage + swap), not a re-simulation; at mid prices a few stops might have been touched differently",
    }

    res = {"declared": "declared.json", "pairs_kept": KEPT, "precheck": "precheck.json",
           "configs": {i: {"label": CFG[i]["label"], "role": CFG[i]["role"], "params": CFG[i]["params"],
                           "costs": CFG[i]["costs"], **info[i], "pooled": pooled.get(i)} for i in range(1, 11)},
           "every_signal_main": every_s, "every_signal_identical_to_main":
               bool(len(TE) == len(T[1]) and np.isclose(TE.R.sum(), T[1].R.sum())),
           "null": null_res, "neighbours_pf": {CFG[i]["label"]: pooled[i]["pf"] for i in range(2, 10)},
           "neighbours_median_pf": round(nb_med, 3), "criteria_main": criteria, "passes_in_sample": passes,
           "information_main": info_main, "runtime_s": round(time.time() - t0, 1)}
    W.jdump(res, os.path.join(W.RES, "results.json"))
    for i in T:
        T[i][[c for c in KEEP_COLS if c in T[i].columns]].to_parquet(
            os.path.join(W.RES, f"trades_{i:02d}_{CFG[i]['label']}.parquet"))
    EX.to_parquet(os.path.join(W.RES, "main_path_costs.parquet"))
    pd.concat(dec_main, ignore_index=True).to_parquet(os.path.join(W.RES, "decisions_main.parquet"))
    np.save(os.path.join(W.RES, "null_means.npy"), null_means)
    print(json.dumps({k: p1[k] for k in ("n", "pf", "expectancy_R", "t_daily", "years_pos", "pairs_pos", "max_pair_share",
                                          "total_R", "long_R", "short_R", "bps_per_trade")}))
    for c in criteria:
        print(c)
    print("passes_in_sample", passes, "runtime", round(time.time() - t0), "s")


if __name__ == "__main__":
    main()
