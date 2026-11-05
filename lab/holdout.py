"""FINAL HOLDOUT TEST (2026). Run once, after the candidate list is frozen.

Usage:
  bash lab/get_holdout.sh            # downloads 2026 M1 data into lab/holdout_raw/download/
  python3 lab/holdout.py             # builds lab/data/holdout/*.parquet, patches holes, runs candidates

Candidates come from lab/holdout_candidates.json (frozen BEFORE the download, see PROTOCOL.md).
Indicators warm up on the end of 2025 (main data); only trades entered on/after 2026-01-01 count.
Every 2026 result is written to results/holdout/ and reported, not only the best.
"""
import datetime as dt
import glob
import importlib.util
import json
import os
import subprocess
import sys

from dataclasses import replace

import numpy as np
import pandas as pd

LAB = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, LAB)
import goldlab as gl  # noqa: E402
from goldlab.sim import Costs  # noqa: E402
from prep_data import _drop_flat  # noqa: E402

RAW = os.path.join(LAB, "holdout_raw", "download")
HD = os.path.join(LAB, "data", "holdout")
OUT = os.path.join(LAB, "results", "holdout")
START = pd.Timestamp("2026-01-01", tz="UTC")


def _read(pattern):
    fr = []
    for p in sorted(glob.glob(os.path.join(RAW, pattern))) + sorted(glob.glob(os.path.join(RAW, "patch", pattern))):
        d = pd.read_csv(p)
        d["ts"] = pd.to_datetime(d["timestamp"], unit="ms", utc=True)
        fr.append(d.drop(columns="timestamp").set_index("ts"))
    df = pd.concat(fr).sort_index()
    return df[~df.index.duplicated(keep="first")]


def build(sym):
    b = _read(f"{sym}-m1-bid-*.csv")
    if sym == "xauusd":
        a = _read(f"{sym}-m1-ask-*.csv")
        df = b.add_prefix("b_").join(a.add_prefix("a_"), how="inner")
        df = _drop_flat(df, "b_open", "b_high", "b_low", "b_close")
        bad = (df.a_close < df.b_close) | (df.a_low < df.b_low - 5)      # same filter as prep_data.py
        df = df[~bad]
        df = pd.DataFrame({"bo": df.b_open, "bh": df.b_high, "bl": df.b_low, "bc": df.b_close,
                           "ao": df.a_open, "ah": df.a_high, "al": df.a_low, "ac": df.a_close})
    else:
        from prep_data import SYNTH_SPREAD
        s = SYNTH_SPREAD.get(sym, 0.0)
        b = _drop_flat(b, "open", "high", "low", "close")
        df = pd.DataFrame({"bo": b.open, "bh": b.high, "bl": b.low, "bc": b.close,
                           "ao": b.open + s, "ah": b.high + s, "al": b.low + s, "ac": b.close + s})
    return df.astype("float64")


def short_days(df):
    cnt = pd.Series(1, index=gl.trading_day(df.index)).groupby(level=0).sum()
    return cnt[cnt < 0.5 * cnt.median()].index


def gap_days(df, min_gap_min=15):
    """Trading days containing an unexpected hole > min_gap_min minutes (not the 17:00-18:00 NY
    daily break, not the weekend). Those days are re-downloaded once (partial download failures)."""
    idx = df.index
    d = np.diff(idx.asi8) / 6e10
    out = set()
    ny = idx.tz_convert("America/New_York")
    for k in np.where(d > min_gap_min)[0]:
        a, b = ny[k], ny[k + 1]
        ta = a.hour * 60 + a.minute
        daily_break = 16 * 60 + 40 <= ta <= 17 * 60 and (b - a) <= pd.Timedelta(hours=1, minutes=40)
        weekend = a.dayofweek == 4 and ta >= 16 * 60 + 40 and b.dayofweek == 6
        if not (daily_break or weekend):
            out.add(gl.trading_day(pd.DatetimeIndex([idx[k]]))[0])
    return sorted(out)


def patch(sym, days):
    os.makedirs(os.path.join(RAW, "patch"), exist_ok=True)
    sides = ("bid", "ask") if sym == "xauusd" else ("bid",)
    for d in days:
        a, b = (d - pd.Timedelta(days=1)).strftime("%Y-%m-%d"), (d + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        for side in sides:
            fn = f"{sym}-m1-{side}-{a}-{b}"
            subprocess.run(["npx", "--yes", "dukascopy-node", "-i", sym, "-from", a, "-to", b, "-t", "m1",
                            "-p", side, "-f", "csv", "-r", "3", "-re", "-dir", os.path.join(RAW, "patch"),
                            "-fn", fn], capture_output=True)


def load_strategy(track):
    d = os.path.join(LAB, "tracks", track)
    sys.path.insert(0, d)
    spec = importlib.util.spec_from_file_location(f"strategy_{track}", os.path.join(d, "strategy.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    os.makedirs(HD, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    cands = json.load(open(os.path.join(LAB, "holdout_candidates.json")))
    with open(os.path.join(OUT, "holdout_access.log"), "a") as f:
        f.write(json.dumps({"time": dt.datetime.utcnow().isoformat(timespec="seconds"),
                            "candidates": [c["track"] + "/" + c["name"] for c in cands["candidates"]]}) + "\n")
    frames = {}
    for sym in sorted({c.get("sym", "xauusd") for c in cands["candidates"]}):
        df = build(sym)
        hol = lambda d: (d.month == 12 and d.day >= 24) or (d.month == 1 and d.day <= 2)
        sd = sorted({d for d in list(short_days(df)) + gap_days(df) if not hol(d)})
        if sd:
            print(f"{sym}: re-downloading {len(sd)} days with holes", flush=True)
            patch(sym, sd)
            df = build(sym)
            print(f"{sym}: remaining days with holes after patch: {len([d for d in gap_days(df) if not hol(d)])}", flush=True)
        df.to_parquet(os.path.join(HD, f"{sym}_m1.parquet"))
        hist = gl.load_m1(sym)                      # full history: same one-position chain as the audits
        full = pd.concat([hist, df[df.index > hist.index[-1]]])
        frames[sym] = full
        print(f"{sym}: holdout bars {len(df):,} {df.index[0]} -> {df.index[-1]}", flush=True)
    results = {}
    for c in cands["candidates"]:
        sym = c.get("sym", "xauusd")
        m1 = frames[sym]
        mod = load_strategy(c["track"])
        params = mod.FINALISTS[c["name"]]
        key = f'{c["track"]}/{c["name"]}'
        results[key] = {"status_before_holdout": c.get("status"), "decisive_scenario": c["decisive_scenario"],
                        "scenarios": {}}
        for sname, cdict in cands["cost_scenarios"].items():
            t = gl.sim.simulate_rebuilt(m1, mod.make_orders, params, sym=sym,
                                        costs=Costs(**cdict) if cdict else None)
            h = t[t.entry_time >= START]
            rep = gl.report(h) if len(h) else {"n": 0}
            results[key]["scenarios"][sname] = rep
            h.to_csv(os.path.join(OUT, f'trades__{c["track"]}__{c["name"]}__{sname}.csv'))
            print(key, sname, {k: rep.get(k) for k in ("n", "pf", "expectancy_R", "t_stat", "win_rate",
                                                          "long_R", "short_R", "weeks_pos_pct", "max_dd_R")}, flush=True)
        # diagnostic (not a criterion): every signal traded, decisive scenario
        dc = cands["cost_scenarios"][c["decisive_scenario"]]
        te = gl.sim.simulate_rebuilt(m1, mod.make_orders, params, sym=sym, costs=Costs(**dc) if dc else None,
                                     no_overlap=False)
        he = te[te.entry_time >= START]
        results[key]["every_signal_decisive"] = gl.report(he) if len(he) else {"n": 0}
        # informational variants (declared before the download, not criteria)
        cc = Costs(**dc) if dc else gl.sim.COSTS["xauusd"]
        mk = gl.sim.apply_spread_mult(m1, cc.spread_mult)
        c1 = replace(cc, spread_mult=1.0)
        orders = mod.make_orders(mk, **params).reset_index(drop=True)
        base = gl.simulate(mk, orders, sym=sym, costs=c1)
        late = orders.loc[base.index].copy()
        late["etype"] = 0
        late["level"] = np.nan
        late["expiry_i"] = -1
        late["entry_i"] = gl.entry_index(mk, base.entry_time + pd.Timedelta(minutes=5))
        tl = gl.simulate(mk, late.reset_index(drop=True), sym=sym, costs=c1)
        hl = tl[tl.entry_time >= START]
        results[key]["late_market_entry_5min"] = gl.report(hl) if len(hl) else {"n": 0}
        if "grid" in getattr(mod, "_DEFAULTS", {}) or c["track"] == "trend":
            try:
                tg = gl.sim.simulate_rebuilt(m1, mod.make_orders, dict(params, grid="ny17"), sym=sym, costs=cc)
                hg = tg[tg.entry_time >= START]
                results[key]["mt5_server_grid_ny17"] = gl.report(hg) if len(hg) else {"n": 0}
            except Exception as e:  # noqa: BLE001
                results[key]["mt5_server_grid_ny17"] = {"error": str(e)}
        hb = base[base.entry_time >= START]
        results[key]["open_at_end_of_data"] = int((hb.exit_time >= m1.index[-1]).sum())
        # random-side null at the same entry times, same stop distance / trail / time exit (200 seeds)
        if len(hb) >= 5:
            o0 = orders.loc[hb.index]
            nul = pd.DataFrame({"entry_i": gl.entry_index(mk, hb.entry_time), "stop_dist": hb.risk.to_numpy(),
                                "trail": o0["trail"].to_numpy() if "trail" in o0 else np.nan,
                                "exit_i": o0["exit_i"].to_numpy()})
            rng = np.random.default_rng(2026)
            pfs = []
            for _ in range(200):
                nul["side"] = rng.choice([-1, 1], len(nul))
                tn = gl.simulate(mk, nul, sym=sym, costs=c1, no_overlap=False)
                g_, l_ = tn.R[tn.R > 0].sum(), -tn.R[tn.R < 0].sum()
                pfs.append(g_ / l_ if l_ > 0 else np.nan)
            pfs = np.array(pfs, float)
            cand_pf = results[key]["scenarios"][c["decisive_scenario"]].get("pf", np.nan)
            results[key]["random_side_null"] = {
                "pf_p5_p50_p95": [round(float(np.nanpercentile(pfs, q)), 3) for q in (5, 50, 95)],
                "candidate_percentile": round(float(np.mean(pfs < cand_pf) * 100), 1)}
        for k_ in ("every_signal_decisive", "late_market_entry_5min", "mt5_server_grid_ny17"):
            if k_ in results[key]:
                r_ = results[key][k_]
                print(key, k_, {k: r_.get(k) for k in ("n", "pf", "expectancy_R", "long_R", "short_R")}, flush=True)
        print(key, "random_side_null", results[key].get("random_side_null"), "| open at end:",
              results[key]["open_at_end_of_data"], flush=True)
        pf = results[key]["scenarios"].get(c["decisive_scenario"], {}).get("pf", 0) or 0
        results[key]["holdout_pf_decisive"] = pf
        results[key]["holdout_pass"] = pf > 1.0
        results[key]["reading"] = ("strong support" if pf >= 1.4 else "consistent but weak" if pf > 1.0 else
                                   "weakly against" if pf >= 0.8 else "strong evidence against")
    m = frames["xauusd"]
    h = m[m.index >= START]
    results["_context"] = {"gold_2026_first_bid": float(h.bc.iloc[0]), "gold_2026_last_bid": float(h.bc.iloc[-1]),
                           "gold_2026_change_pct": round(float(h.bc.iloc[-1] / h.bc.iloc[0] - 1) * 100, 1),
                           "last_bar": str(h.index[-1])}
    print("context:", results["_context"])
    json.dump(results, open(os.path.join(OUT, "results.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
