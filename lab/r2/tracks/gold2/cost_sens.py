"""Diagnostic (in-sample, no new configuration): PF / expectancy of the shortlisted rules and their
2h-bar controls when ALL costs (spread and slippage) are multiplied by 1, 1.5, 2, 3; plus overlap of
the 2h controls with the legacy sleeve."""
import json, os, sys
import numpy as np, pandas as pd
from research import RES, r2, S, use, is_trades, pf, tstat
from goldlab.sim import apply_spread_mult, simulate
from goldlab.split import cut
from goldlab.metrics import report
import stageB, stageD, stageA
from overlap import overlap_stats, weekly

CFG = {
    "SQ_1h": stageD.SQ, "SQ_2h": {**stageD.SQ, **stageD.CTRL["SQ"]["ctrl_2h_bars"]},
    "TR_1h": stageD.TR, "TR_2h": {**stageD.TR, **stageD.CTRL["TR"]["ctrl_2h_bars"]},
    "legacy_4h": stageA.A["A0_ref_legacy_donch4h_stop"][0],
}
if __name__ == "__main__":
    use("xauusd")
    m1 = r2.load("xauusd")
    out = {}
    for mult in (1.0, 1.5, 2.0, 3.0):
        mk = apply_spread_mult(m1, mult)
        for k, p in CFG.items():
            t = cut(simulate(mk, S.make_orders(mk, **S.resolve(p)), sym="xauusd", costs=r2.costs("xauusd", mult), no_overlap=True), "is")
            r = report(t)
            out.setdefault(k, {})[str(mult)] = {"n": r["n"], "pf": r["pf"], "exp_R": r["expectancy_R"], "t": r["t_stat"]}
        del mk
    for k, v in out.items():
        print(k, {m: (x["pf"], x["exp_R"], x["t"]) for m, x in v.items()}, flush=True)
    leg = is_trades("xauusd", CFG["legacy_4h"])
    wl = weekly(leg)
    for k in ("SQ_2h", "TR_2h"):
        t = is_trades("xauusd", CFG[k])
        o = overlap_stats(t, leg)
        al = pd.concat([wl, weekly(t)], axis=1).fillna(0.0)
        o["weekly_R_corr_with_legacy"] = round(float(al.corr().iloc[0, 1]), 3)
        out[k]["overlap"] = o
        print(k, json.dumps(o))
    json.dump(out, open(os.path.join(RES, "cost_sensitivity_is.json"), "w"), indent=1)
