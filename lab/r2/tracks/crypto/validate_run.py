"""Single-shot validation (2022-2025) of the finalists frozen in finalists_preval.json.

  python3 validate_run.py --dry     plumbing test on the IN-SAMPLE period (no validation access)
  python3 validate_run.py           the real run: refuses to start if this track already accessed validation

Per sleeve: r2.validate (base, cost stress x1.5, every-signal; logged).  Per finalist: the two-instrument basket
(pooled trades) from the same trades, through goldlab.cut(..., "val", track, label) (logged)."""
import json, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, "/home/user/gold-orb/lab"); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import goldlab as gl
from goldlab import r2
from goldlab.metrics import report
import strategy as S

OUT = "/home/user/gold-orb/lab/results/r2/crypto"
VAL_LOG = "/home/user/gold-orb/lab/results/val_access.log"
DRY = "--dry" in sys.argv
PERIOD = "is" if DRY else "val"
KEEP = ("n", "trades_per_year", "win_rate", "avg_win_R", "avg_loss_R", "expectancy_R", "t_stat", "pf", "total_R", "max_dd_R",
        "years_pos", "weeks_pos_pct", "months_pos_pct", "long_n", "long_R", "short_n", "short_R", "avg_hold_h", "max_hold_h",
        "by_year_R", "exit_reasons")


def cutp(t, label):
    return gl.cut(t, "is") if DRY else gl.cut(t, "val", track="crypto", label=label)


def side_stats(t):
    f = lambda x: {"n": int(len(x)), "sum_R": round(float(x.R.sum()), 1), "exp_R": round(float(x.R.mean()), 4) if len(x) else None,
                   "bps": round(float((x.pnl / x.entry).mean() * 1e4), 2) if len(x) else None}
    out = {"long": f(t[t.side > 0]), "short": f(t[t.side < 0])}
    for y, g in t.groupby(t.entry_time.dt.year):
        out[int(y)] = {"long": f(g[g.side > 0]), "short": f(g[g.side < 0]), "all": f(g)}
    return out


if __name__ == "__main__":
    pre = json.load(open(os.path.join(OUT, "finalists_preval.json")))
    for name, f in S.FINALISTS.items():
        assert pre["finalists"][name]["params"] == f["params"] and pre["finalists"][name]["syms"] == f["syms"], name
    if not DRY and os.path.exists(VAL_LOG):
        acc = [json.loads(l) for l in open(VAL_LOG) if l.strip()]
        assert not any(a.get("track") == "crypto" for a in acc), "validation already accessed for this track: single shot only"
    res = {"period": PERIOD, "finalists": {}}
    pooled = {name: {"fp": [], "stress": [], "every": []} for name in S.FINALISTS}
    for sym in ("btcusd", "ethusd"):
        m1 = r2.load(sym)
        for name, f in S.FINALISTS.items():
            if sym not in f["syms"]:
                continue
            p = f["params"]
            # the frozen configuration must reproduce its logged in-sample numbers exactly
            ti = gl.cut(r2.run(sym, S.make_orders, p, "fp", True, m1), "is")
            ref = pre["finalists"][name]["sleeves"][sym]["is"]
            assert len(ti) == ref["n"] and abs(float(ti.R.mean()) - ref["expectancy_R"]) < 1e-4, (name, sym, len(ti), ti.R.mean(), ref["n"], ref["expectancy_R"])
            if DRY:
                val = {"val": report(ti), "note": "dry run on IS"}
            else:
                val = r2.validate(sym, S.make_orders, p, "crypto", f"{name}:{sym}")
            # trades for the basket and for the files (same configuration, same period)
            t = cutp(r2.run(sym, S.make_orders, p, "fp", True, m1), f"{name}:{sym}:basket")
            ts_ = cutp(r2.run(sym, S.make_orders, p, "stress", True, m1), f"{name}:{sym}:basket-stress")
            te = cutp(r2.run(sym, S.make_orders, p, "fp", False, m1), f"{name}:{sym}:basket-every")
            tg = cutp(r2.run(sym, S.make_orders, p, "gross", True, m1), f"{name}:{sym}:gross")
            for k, x in (("fp", t), ("stress", ts_), ("every", te)):
                pooled[name][k].append(x.assign(sym=sym))
            val["val_gross"] = {k: report(tg).get(k) for k in ("n", "pf", "expectancy_R", "t_stat")} if len(tg) else {"n": 0}
            val["val_gross_bps_per_trade"] = round(float((tg.pnl / tg.entry).mean() * 1e4), 2) if len(tg) else None
            val["sides_by_year"] = side_stats(t)
            wk = pd.DatetimeIndex(t.dec_time).dayofweek
            val["by_decision_weekday_R"] = {int(k): round(float(v), 1) for k, v in t.groupby(wk).R.sum().items()}
            res["finalists"].setdefault(name, {"sleeves": {}})["sleeves"][sym] = val
            cols = ["side", "entry_time", "exit_time", "entry", "exit", "stop", "reason", "swap", "pnl", "risk", "R", "hold_min", "dec_time"]
            t[cols].to_csv(os.path.join(OUT, f"trades_{PERIOD}_{name}_{sym}.csv"), index=False)
            if not DRY:
                ti[cols].to_csv(os.path.join(OUT, f"trades_is_{name}_{sym}.csv"), index=False)
            r = val["val"]
            print(name, sym, PERIOD, {k: r.get(k) for k in ("n", "pf", "expectancy_R", "t_stat", "years_pos", "long_R", "short_R", "by_year_R")},
                  "| criteria:", val.get("val_criteria"), "| every:", (val.get("val_every_signal") or {}).get("expectancy_R"),
                  "| stress pf:", (val.get("val_stress") or {}).get("pf"), flush=True)
        r2.free()
    for name in S.FINALISTS:
        b = {}
        for k in ("fp", "stress", "every"):
            x = pd.concat(pooled[name][k]).sort_values("entry_time")
            rep = report(x)
            b[k] = {q: rep.get(q) for q in KEEP}
        each_pos = all(res["finalists"][name]["sleeves"][s]["val"].get("expectancy_R", -1) > 0 for s in res["finalists"][name]["sleeves"])
        c = {"pf>=1.06": b["fp"].get("pf", 0) >= 1.06, "expectancy>0": b["fp"].get("expectancy_R", -1) > 0,
             "every_signal_exp>0": b["every"].get("expectancy_R", -1) > 0, "expectancy>0_on_each_instrument": bool(each_pos)}
        c["pass"] = all(c.values())
        b["criteria"] = c
        res["finalists"][name]["basket"] = b
        print(name, "BASKET", PERIOD, {q: b["fp"].get(q) for q in ("n", "pf", "expectancy_R", "t_stat", "years_pos", "long_R", "short_R", "by_year_R")}, c, flush=True)
    json.dump(res, open(os.path.join(OUT, "val_results_DRYRUN_is.json" if DRY else "val_results.json"), "w"), indent=1, default=str)
    print("done", PERIOD)
