"""Runs the seven declared configurations of the gold daily-reopen drift (declared.json), IN SAMPLE ONLY.

For each configuration: goldlab.r2.evaluate (FP costs, costs x1.5, gross, every signal) logged with goldlab.r2.log_trial
(results/r2/round5/gold_reopen/trials.jsonl, the trial budget), then the trade frames of the same runs (goldlab.r2.run,
checked equal to r2.evaluate's reports) saved as small parquet files. Then the random-time null of the main
(goldlab.r2.null_test, mode 'time', 200 replays, seed 0; D14). Outputs in results/r2/round5/gold_reopen/:
run.json, trials.jsonl, trades_*.parquet, null.json, null_means.npy.

    python3 run.py --smoke   # structure only (counts, columns, times): no result is printed or written
    python3 run.py           # the declared run (refuses to run twice: trials.jsonl is written once)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

import json  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402

from goldlab import r2  # noqa: E402
from goldlab.metrics import report  # noqa: E402
from goldlab.split import cut  # noqa: E402

COST_TXT = {
    "fp": "FP frame bid/ask (spread 0.19 USD at 4,080 USD, Dukascopy intraday shape) + r2.costs('xauusd'): market slippage "
          "0.3 bp per side, stop slippage 1.0 bp, long swap 5.5 %/yr per 17:00 New York rollover (none crossed)",
    "stress": "costs x1.5 (r2.run 'stress'): spread x1.5 around the mid, slippage x1.5 (market 0.45 bp, stop 1.5 bp)",
    "gross": "mid quotes, no cost at all (r2.run 'gross'), information only"}
KEYS = ("n", "pf", "t_stat", "expectancy_R", "total_R", "years_pos", "win_rate", "max_dd_R")


def same_report(a, b):
    return all(a.get(k) == b.get(k) for k in ("n", "pf", "t_stat", "expectancy_R", "total_R", "years_pos"))


def save(t, name):
    p = os.path.join(C.OUT, f"trades_{name}.parquet")
    t.to_parquet(p)
    return os.path.basename(p)


def run_config(c):
    p = c["params"]
    ev = r2.evaluate(C.SYM, C.make_orders, p)                       # IS cut inside (goldlab.split.cut 'is')
    C.check_held()
    t = {m: cut(r2.run(C.SYM, C.make_orders, p, m), "is") for m in ("fp", "stress", "gross")}
    t["every"] = cut(r2.run(C.SYM, C.make_orders, p, "fp", no_overlap=False), "is")
    C.check_held()
    for m, tt in t.items():
        assert (tt.entry_time < C.CUT).all() and (tt.exit_time < C.CUT).all()
    assert float(t["fp"].swap.abs().sum()) == 0.0 and float(t["stress"].swap.abs().sum()) == 0.0   # D10
    chk = {"fp": same_report(report(t["fp"]), ev["is"]), "stress": same_report(report(t["stress"]), ev["is_stress"]),
           "gross": same_report(report(t["gross"]), ev["is_gross"]),
           "every": same_report(report(t["every"]), ev["is_every_signal"])}
    assert all(chk.values()), chk
    tf, te = t["fp"], t["every"]
    ident = len(te) == len(tf) and bool((te.entry_time.to_numpy() == tf.entry_time.to_numpy()).all()) \
        and bool(np.array_equal(te.R.to_numpy(), tf.R.to_numpy()))
    ev_table = C.evening_table(C.r2.load(C.SYM), p["entry"], p["hold_min"], p["n_h1"])
    line = {"id": c["id"], "name": c["name"], "role": c["role"], "params": p,
            "period": "in sample: entries and exits 2013-01-01 .. 2021-12-31 UTC (frame cut at ts < 2022-01-01)",
            "costs": COST_TXT["fp"], "first_entry": str(tf.entry_time.min()), "last_exit": str(tf.exit_time.max()),
            "evenings_by_status": {k: int(v) for k, v in ev_table.status.value_counts().items()},
            "is": C.summarize(tf),
            "is_stress": dict({k: report(t["stress"]).get(k) for k in KEYS}, bp_net_per_trade=round(C.bp(t["stress"]), 3),
                              by_year_R=report(t["stress"])["by_year_R"], n_stop_exits=int((t["stress"].reason == "stop").sum()),
                              costs=COST_TXT["stress"]),
            "is_gross": dict({k: report(t["gross"]).get(k) for k in KEYS}, bp_gross_per_trade=round(C.bp(t["gross"]), 3),
                             by_year_bp={int(y): round(C.bp(g), 3) for y, g in t["gross"].groupby(t["gross"].entry_time.dt.year)},
                             costs=COST_TXT["gross"]),
            "every_signal": {"n": int(len(te)), "expectancy_R": round(float(te.R.mean()), 4),
                             "identical_to_main_run": ident,
                             "note": "one order per session, holds <= 144 min, sessions ~24 h apart: no order is ever skipped"},
            "r2_evaluate": ev, "r2_reports_equal_trade_frames": chk}
    files = {"fp": save(tf, f"{c['id']:02d}_{c['name']}")}
    if c["id"] == 1:
        files["stress"] = save(t["stress"], "01_main_costs_x1.5")
        files["gross"] = save(t["gross"], "01_main_gross")
    line["trade_files"] = files
    return line, ev


def null_main(p, decl):
    """r2.null_test on the installed in-sample slice; the replay means are recorded around r2.simulate (D14)."""
    rec = []
    sim0 = r2.simulate

    def recording(m1, orders, sym="xauusd", costs=None, no_overlap=True):
        tt = sim0(m1, orders, sym=sym, costs=costs, no_overlap=no_overlap)
        ti = cut(tt, "is")
        rec.append((int(len(ti)), float(ti.R.mean()) if len(ti) else 0.0, int(tt.attrs.get("skipped", 0)),
                    bool(len(tt) == 0 or tt.exit_time.max() < C.CUT)))
        return tt

    nd = decl["null"]
    r2.simulate = recording
    t0 = time.time()
    try:
        nul = r2.null_test(C.SYM, C.make_orders, p, n_seeds=nd["n_seeds"], mode=nd["mode"], period=nd["period"],
                           no_overlap=nd["no_overlap"], seed=nd["seed"])
    finally:
        r2.simulate = sim0
    C.check_held()
    assert len(rec) == 1 + nd["n_seeds"], len(rec)
    assert all(r[3] for r in rec)
    means = np.array([r[1] for r in rec[1:]])
    cand = rec[0][1]
    pct = round(float((means < cand).mean() * 100), 1)
    assert pct == nul["percentile"] and abs(cand - nul["rule_mean_R"]) < 5e-5, (pct, nul)
    out = dict(nul)
    out.update({"function": "goldlab.r2.null_test", "n_seeds": nd["n_seeds"], "seed": nd["seed"], "no_overlap": nd["no_overlap"],
                "null_sd_R": round(float(means.std(ddof=1)), 4), "null_p975_R": round(float(np.percentile(means, 97.5)), 4),
                "null_p50_R": round(float(np.percentile(means, 50)), 4),
                "replay_trades_min_max": [int(min(r[0] for r in rec[1:])), int(max(r[0] for r in rec[1:]))],
                "replay_orders_skipped_by_one_position_mean": round(float(np.mean([r[2] for r in rec[1:]])), 1),
                "recorded_percentile_equals_r2": True, "seconds": round(time.time() - t0, 1)})
    return out, means


def main(smoke=False):
    decl, sha = C.declared()
    tri = os.path.join(C.OUT, "trials.jsonl")
    if not smoke:
        assert not os.path.exists(tri), "trials.jsonl exists: the declared run is done once"
    val0 = C.sha256(C.VAL_LOG)
    m1 = C.load_is()
    C.install(m1)
    cfgs = decl["configurations"]
    if smoke:
        for c in cfgs:
            o = C.make_orders(r2.load(C.SYM), **c["params"])
            print(c["name"], "orders", len(o), "first", o.t_target_utc.min(), "last", o.t_target_utc.max())
        t = r2.run(C.SYM, C.make_orders, cfgs[0]["params"], "fp")
        print("main trades", len(t), "columns", list(t.columns))
        print("first entry", t.entry_time.min(), "last exit", t.exit_time.max(), "max hold min", float(t.hold_min.max()),
              "swap sum", float(t.swap.sum()), "skipped", t.attrs["skipped"], "nofill", t.attrs["nofill"])
        C.check_held()
        return
    t_start = time.time()
    lines, evs = [], []
    for c in cfgs:
        line, ev = run_config(c)
        lines.append(line)
        evs.append(ev)
        print(f"computed {c['id']} {c['name']}", flush=True)
    for c, ev in zip(cfgs, evs):                                     # one line per configuration (D17), all seven at once
        r2.log_trial(C.TRACK, C.SYM, c["params"], ev)
    nul, means = null_main(cfgs[0]["params"], decl)
    np.save(os.path.join(C.OUT, "null_means.npy"), means)
    C.jdump(nul, os.path.join(C.OUT, "null.json"))
    val1 = C.sha256(C.VAL_LOG)
    assert val0 == val1, "results/val_access.log changed"
    C.check_held()
    out = {"what": "gold daily-reopen drift (PROTOCOL_V3 Addendum K), seven declared configurations, in sample only",
           "declared_sha256": sha, "declared_utc": decl["_written_utc"], "configs": lines, "null_main": nul,
           "trials_logged": sum(1 for _ in open(tri)), "val_access_log_sha256_before": val0, "val_access_log_sha256_after": val1,
           "seconds": round(time.time() - t_start, 1)}
    assert out["trials_logged"] == len(cfgs) == 7
    C.jdump(out, os.path.join(C.OUT, "run.json"))
    for l in lines:
        s = l["is"]
        print(l["name"], {k: s[k] for k in ("n", "pf", "t_stat", "expectancy_R", "total_R", "years_pos", "bp_net_per_trade")},
              "stress pf", l["is_stress"]["pf"], "gross bp", l["is_gross"]["bp_gross_per_trade"],
              "every-signal identical", l["every_signal"]["identical_to_main_run"])
    print("null", json.dumps(nul))


if __name__ == "__main__":
    main(smoke="--smoke" in sys.argv)
