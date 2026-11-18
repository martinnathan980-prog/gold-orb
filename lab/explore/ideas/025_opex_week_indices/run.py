"""Idea 025: options-expiry week on the indices (long Monday -> expiry Friday), basket us500 us100 us30 ger40.
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/025_opex_week_indices/run.py
Reads declared.json (never writes it). The kit's simulate takes one exit per call, so each (market, exit hours) group
is simulated with kit.sim.simulate and the tables are concatenated (signals_sha of the whole build(data) table);
the null is kit.stats.null_test per group, pooled draw by draw (declared in rule_main.implementation)."""
import json, os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
from kit import checks, judge, sim, stats, data  # noqa: E402

MARKETS = ["us500", "us100", "us30", "ger40"]
US = {"us500", "us100", "us30"}
NY, BER = "America/New_York", "Europe/Berlin"
END = pd.Timestamp("2022-01-01", tz="UTC")
MAX_WAIT_H = 1
N_DRAWS = 2000


def _loc(day, hh, tz):
    return (pd.Timestamp(day) + pd.Timedelta(hours=hh)).tz_localize(tz).tz_convert("UTC")


def build(d, entry_shift_h=0, exit_shift_h=0, prev_fri=False):
    """Signal table from the calendar: per market, one long per expiry week. Data is used only for each market's
    first bar (weeks before it are not built). exit_h = scheduled exit - known_at in hours (local wall clock, DST
    exact)."""
    fridays = pd.date_range("2013-01-01", "2021-12-31", freq="WOM-3FRI")
    rows = []
    for mk in MARKETS:
        b = d[mk]
        if len(b) == 0:
            continue
        first = b.index[0]
        us = mk in US
        tz = NY if us else BER
        e_hh, x_hh = (10, 16) if us else (9, 17)
        for F in fridays:
            if prev_fri:
                ka = _loc(F - pd.Timedelta(days=7), 15 if us else 17, tz)
            else:
                ka = _loc(F - pd.Timedelta(days=4), e_hh + entry_shift_h, tz)
            xa = _loc(F, x_hh + exit_shift_h, tz)
            if ka < first or ka >= END:
                continue
            rows.append((ka, 1, mk, (xa - ka) / pd.Timedelta(hours=1)))
    sig = pd.DataFrame(rows, columns=["known_at", "side", "market", "exit_h"])
    sig["known_at"] = pd.DatetimeIndex(sig.known_at).tz_convert("UTC")
    return sig.sort_values(["known_at", "market"]).reset_index(drop=True)


def run_cfg(sig, bk, stop, mode="one"):
    frames, counts = [], {}
    for (mk, h), g in sig.groupby(["market", "exit_h"], sort=True):
        t = sim.simulate(g[["known_at", "side", "market"]].reset_index(drop=True), {mk: bk[mk]}, exit=("hours", float(h)),
                         stop=stop, mode=mode, max_wait_h=MAX_WAIT_H)
        for k, v in t.attrs["counts"].get(mk, {}).items():
            counts.setdefault(mk, {}).setdefault(k, 0)
            counts[mk][k] += v
        t["exit_h_sched"] = h
        frames.append(t)
    out = pd.concat([f for f in frames if len(f)], ignore_index=True).sort_values(["entry_time", "market"]).reset_index(drop=True)
    out.attrs["counts"] = counts
    out.attrs["signals_sha"] = sim.signals_sha(sig)
    out.attrs["rule"] = {"exit": "hours per (market, row): Friday 16:00 NY / 17:00 Berlin", "stop": stop,
                         "max_wait_h": MAX_WAIT_H, "mode": mode}
    return out


def pooled_null(main, bk, stop):
    tot, cnt, parts = np.zeros(N_DRAWS), 0, []
    for i, ((mk, h), g) in enumerate(main.groupby(["market", "exit_h_sched"], sort=True)):
        r = stats.null_test(g, {mk: bk[mk]}, exit=("hours", float(h)), stop=stop, n_draws=N_DRAWS, seed=i)
        tot += r["means"] * len(g)
        cnt += len(g)
        parts.append({"market": mk, "exit_h": float(h), "n": int(len(g)), "real_mean_R": r["real_mean_R"],
                      "percentile": r["percentile"], "null_mean": r["null_mean"]})
    means = tot / cnt
    real = float(main.R.mean())
    return {"real_mean_R": real, "percentile": float((means < real).mean() * 100), "n_draws": N_DRAWS, "seed": "0..k per group",
            "mode": "every", "null_mean": float(means.mean()), "null_sd": float(means.std(ddof=1)), "means": means,
            "pooled_from_groups": parts}


def split(t):
    out = {}
    for mk, g in t.groupby("market"):
        out[mk] = {"n": int(len(g)), "PF_gross": stats.pf(g.R_gross), "PF": stats.pf(g.R), "PF_stress": stats.pf(g.R_stress),
                   "mean_R_gross": float(g.R_gross.mean()), "mean_R": float(g.R.mean()), "sum_R": float(g.R.sum()),
                   "mean_gross_bp": float(g.gross_bp.mean()), "mean_net_bp": float(g.net_bp.mean()),
                   "t_trade": stats.t_stat(g.R), "by_year_R": {int(k): float(v) for k, v in stats.by_year(g).items()}}
    return out


def main_():
    decl = json.load(open(os.path.join(HERE, "declared.json")))
    checks.declared_hash(HERE)
    d = {mk: data.load_bars(mk) for mk in MARKETS}
    tr = checks.truncation_test(build, d, ["2016-06-01 14:30", "2019-09-09 09:00"],
                                row_len={mk: pd.Timedelta(hours=1) for mk in MARKETS})
    assert tr["pass"], tr
    bk = sim.books(d)
    cfgs = decl["configurations"]
    sig_main = build(d)
    print("main signals per market:", sig_main.market.value_counts().to_dict())
    results = {}
    for c in cfgs:
        if c["id"].startswith("06"):
            s = build(d, prev_fri=True)
        else:
            s = build(d, c.get("entry_shift_h", 0), c.get("exit_shift_h", 0))
        results[c["id"]] = run_cfg(s, bk, tuple(c["stop"]))
    main = results.pop(cfgs[0]["id"])
    stop0 = tuple(cfgs[0]["stop"])
    every = run_cfg(sig_main, bk, stop0, mode="every")
    null = pooled_null(main, bk, stop0)
    main.to_csv(os.path.expanduser("~/explore_data/idea_025/main_trades.csv"), index=False)
    extra = {"by_market_main": split(main), "gross_main": {"PF_gross": stats.pf(main.R_gross),
             "mean_R_gross": float(main.R_gross.mean()), "t_daily_gross": stats.t_stat(stats.daily_sums(main, "R_gross"))},
             "neighbours_detail": {k: {"n": int(len(t)), "PF_gross": stats.pf(t.R_gross), "PF": stats.pf(t.R),
                                       "PF_stress": stats.pf(t.R_stress), "mean_R": float(t.R.mean()),
                                       "t_daily": stats.t_stat(stats.daily_sums(t))} for k, t in results.items()},
             "null_groups": null["pooled_from_groups"], "counts_every": every.attrs["counts"],
             "truncation": {k: v for k, v in tr.items() if k != "cuts"}, "sides": "long only by construction"}
    res = judge.verdict(HERE, main, results, every, null, corr="compute", n_configs=len(cfgs), truncation=tr,
                        data_desc="computed calendar; prepared H1 BID bars 2013-2021 (us30, ger40 from 2013-10)", extra=extra)
    print(res["verdict"], res["failed_bars"])
    print(res["ledger_line"])
    for k, v in res["bars"].items():
        print(f"  {k}: {v['value']} {'ok' if v['pass'] else 'FAIL'}")
    print(json.dumps(extra["by_market_main"], indent=0, default=str)[:3000])
    print(json.dumps(extra["gross_main"]), json.dumps(extra["neighbours_detail"], default=str))
    return res


if __name__ == "__main__":
    main_()
