"""Idea 057 run (in sample only). Reads declared.json (never writes it).
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<repo>/lab/explore python3 -B <this file>"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
import numpy as np, pandas as pd
from kit import checks, judge, sim, stats, data
import rule

MAX_WAIT_H = 1


def summ(t, col="R"):
    if not len(t):
        return {"n": 0}
    x = t[col].to_numpy(float)
    return {"n": int(len(x)), "pf": float(stats.pf(x)), "mean": float(x.mean()), "t": float(stats.t_stat(x))}


def main():
    decl = json.load(open(os.path.join(HERE, "declared.json")))
    checks.declared_hash(HERE)
    cfgs = decl["configurations"]
    bars = data.load_bars("oil")
    d = {"bars": bars}
    c0 = cfgs[0]
    build_main = lambda dd: rule.build(dd, thr_mult=c0["thr_mult"], window=c0["window"])   # noqa: E731
    tr = checks.truncation_test(build_main, d, row_len={"bars": pd.Timedelta(hours=1)})
    print("truncation:", tr["pass"], tr["n_failed_cuts"], "cuts", len(tr["cuts"]), tr["density_why"])
    assert tr["pass"], "truncation test failed"
    bk = sim.books({"oil": bars})

    def run(c, mode="one"):
        s = rule.build(d, thr_mult=c["thr_mult"], window=c["window"]).assign(market="oil")
        return sim.simulate(s, bk, exit=tuple(c["exit"]), stop=tuple(c["stop"]), mode=mode, max_wait_h=MAX_WAIT_H)

    sig = build_main(d).assign(market="oil")
    rule0 = dict(exit=tuple(c0["exit"]), stop=tuple(c0["stop"]))
    main_t = sim.simulate(sig, bk, mode="one", max_wait_h=MAX_WAIT_H, **rule0)
    neigh = {c["id"]: run(c) for c in cfgs[1:]}
    every = sim.simulate(sig, bk, mode="every", max_wait_h=MAX_WAIT_H, **rule0)
    null = stats.null_test(main_t, bk, n_draws=2000, **rule0)
    shift = checks.shift_test(sig, bk, max_wait_h=MAX_WAIT_H, **rule0)
    # diagnostics (reported, not judged)
    diag = {"counts": main_t.attrs["counts"],
            "gross": summ(main_t, "R_gross"), "net": summ(main_t, "R"), "stress": summ(main_t, "R_stress"),
            "long": {"gross": summ(main_t[main_t.side > 0], "R_gross"), "net": summ(main_t[main_t.side > 0], "R")},
            "short": {"gross": summ(main_t[main_t.side < 0], "R_gross"), "net": summ(main_t[main_t.side < 0], "R")},
            "by_year_net": {int(y): float(g.R.sum()) for y, g in main_t.groupby(main_t.entry_time.dt.year)},
            "by_year_gross": {int(y): float(g.R_gross.sum()) for y, g in main_t.groupby(main_t.entry_time.dt.year)},
            "wed": summ(main_t[main_t.entry_time.dt.tz_convert(rule.NY).dt.dayofweek == 2], "R"),
            "thu": summ(main_t[main_t.entry_time.dt.tz_convert(rule.NY).dt.dayofweek == 3], "R"),
            "mean_gross_bp": float(main_t.gross_bp.mean()), "mean_net_bp": float(main_t.net_bp.mean()),
            "reasons": main_t.reason.value_counts().to_dict(),
            "neighbours": {k: {"net": summ(v, "R"), "gross": summ(v, "R_gross")} for k, v in neigh.items()},
            "shift_test": shift}
    res = judge.verdict(HERE, main_t, neigh, every, null, corr="compute", n_configs=len(cfgs), truncation=tr,
                        data_desc="oil prepared hourly bars 2013-2021 (9 years), roll-adjusted (kit v2.1)",
                        extra={"diagnostics": diag})
    main_t.to_csv(os.path.expanduser("~/explore_data/idea_057/main_trades.csv"), index=False)
    print(json.dumps(diag, indent=1, default=str))
    print("VERDICT:", res["verdict"], "failed:", res["failed_bars"])
    print(res["ledger_line"])


if __name__ == "__main__":
    main()
