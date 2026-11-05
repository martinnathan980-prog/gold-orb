"""Diagnostic (NOT new trials): every config already logged in trials.jsonl is re-simulated with
zero costs (mid-price fills, no slippage / commission / swap) to separate 'no signal' from
'signal eaten by costs'.  Output: results/crossasset/gross_vs_net.csv"""
import json
import os

import numpy as np
import pandas as pd

from common import RES, free_m1, gl, load_bars
from goldlab.sim import Costs
import strategy as S
from parta import make_cache

ZERO = Costs(commission=0.0, slip_bps=0.0, swap_long=0.0, swap_short=0.0, spread_mult=0.0)


def stats(t):
    t = gl.cut(t, "is")
    R = t.R.to_numpy()
    R = R[np.isfinite(R)]
    pf = R[R > 0].sum() / -R[R < 0].sum()
    return len(R), round(float(pf), 3), round(float(R.mean()), 4)


def main():
    trials = [json.loads(l) for l in open(os.path.join(RES, "trials.jsonl"))]
    rows = []
    # Part B (bug-fix re-runs supersede the first runs of the same config)
    pb = {}
    for tr in trials:
        c = tr["config"]
        if c.get("part") == "B":
            pb[(c["sym"], c["rule"])] = tr
    for sym in ["xauusd", "eurusd", "gbpusd", "usdjpy", "deuidxeur", "lightcmdusd"]:
        m1 = gl.load_m1(sym)
        bars = {"channel": load_bars(sym, "4h"), "rsi2": load_bars(sym, "D"), "orb": None}
        for rule in ["orb", "channel", "rsi2"]:
            tr = pb[(sym, rule)]
            p = {k: v for k, v in tr["config"].items() if k not in ("part", "sym", "rerun")}
            o = S.make_orders(m1, rule=p.pop("rule"), bars=bars[rule], **p)
            n, pf0, e0 = stats(gl.simulate(m1, o, sym=sym, costs=ZERO))
            rows.append({"part": "B", "name": f"{rule}@{sym}", "n": tr["is"]["n"], "pf_net": tr["is"]["pf"],
                         "exp_net": tr["is"]["expectancy_R"], "pf_gross": pf0, "exp_gross": e0,
                         "cost_R": round(e0 - tr["is"]["expectancy_R"], 4)})
            print(rows[-1], flush=True)
        free_m1(sym)
        del m1
    m1 = gl.load_m1("xauusd")
    cache = make_cache()
    for tr in trials:
        c = tr["config"]
        if c.get("part") != "A":
            continue
        p = {k: v for k, v in c.items() if k not in ("part", "name", "note")}
        o = S.make_orders(m1, None, cache=cache, **p)
        n, pf0, e0 = stats(gl.simulate(m1, o, costs=ZERO))
        rows.append({"part": "A", "name": c["name"], "n": tr["is"]["n"], "pf_net": tr["is"]["pf"],
                     "exp_net": tr["is"]["expectancy_R"], "pf_gross": pf0, "exp_gross": e0,
                     "cost_R": round(e0 - tr["is"]["expectancy_R"], 4)})
        print(rows[-1], flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(RES, "gross_vs_net.csv"), index=False)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
