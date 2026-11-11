"""How much cost can each validated sleeve bear?  In-sample only (2013-2021), frozen rules, nothing re-tuned.

For a multiplier m of the modelled spread (the Raw commission is inside the spread where there is one):
  base    spread x m, slippage x 1        -> the in-sample bar is PF >= 1.12 and t >= 2.5
  stress  spread x 1.5 m, slippage x 1.5  -> the in-sample bar is PF >= 1.04
m = 1 is the model of r2/fp_costs.json. Used with live_ai/releve.py: when the measured cost at a sleeve's signal
minutes is r times the model, the row m >= r tells at once whether the sleeve still passes its in-sample bars.

    python3 r2/cost_grid.py [sym ...]      -> results/live/cost_grid_<sym>.json   (one file per market)
    python3 r2/cost_grid.py merge          -> results/live/cost_grid.json
"""
import glob
import json
import os
import sys
import time

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LAB)
sys.path.insert(0, os.path.join(LAB, "r2"))
from goldlab import r2  # noqa: E402
from goldlab.metrics import report  # noqa: E402
from goldlab.sim import apply_spread_mult, simulate  # noqa: E402
from goldlab.split import cut  # noqa: E402
import recalc  # noqa: E402

OUT = os.path.join(LAB, "results", "live")
GRID = (1.0, 1.5, 2.0, 3.0, 4.0)
KEEP = ("n", "pf", "t_stat", "expectancy_R", "total_R", "years_pos")


def one(sym, mk, params, m1, spread_mult, slip_mult):
    f = apply_spread_mult(m1, spread_mult) if spread_mult != 1.0 else m1
    t = cut(simulate(f, mk(f, **params), sym=sym, costs=r2.costs(sym, slip_mult), no_overlap=True), "is")
    r = report(t)
    out = {k: r.get(k) for k in KEEP}
    out["bps_net"] = round(float((t["pnl"] / t["entry"]).mean() * 1e4), 2) if len(t) else 0.0
    return out


def run(syms):
    os.makedirs(OUT, exist_ok=True)
    for sym in syms:
        res = {}
        m1 = r2.load(sym)
        for track, name, s, mk, params in recalc.sleeves():
            if s != sym:
                continue
            rows = []
            for m in GRID:
                t0 = time.time()
                b = one(sym, mk, params, m1, m, 1.0)
                st = one(sym, mk, params, m1, 1.5 * m, 1.5)
                ok = bool(b["pf"] >= 1.12 and b["t_stat"] >= 2.5 and st["pf"] >= 1.04)
                rows.append({"m": m, "base": b, "stress": st, "passes_is_bars": ok})
                print(f"{name:22s} {sym:7s} m {m:3.1f} | PF {b['pf']:5.2f} t {b['t_stat']:5.2f} R/trade {b['expectancy_R']:+.3f} "
                      f"bps {b['bps_net']:+6.2f} | stress PF {st['pf']:5.2f} | {'ok' if ok else 'NO'} [{time.time() - t0:.0f}s]", flush=True)
            res[f"{name}:{sym}"] = rows
            json.dump(res, open(os.path.join(OUT, f"cost_grid_{sym}.json"), "w"), indent=1)
        r2.free()


def merge():
    out = {}
    for p in sorted(glob.glob(os.path.join(OUT, "cost_grid_*.json"))):
        out.update(json.load(open(p)))
    for k, rows in out.items():
        last_ok = max([r["m"] for r in rows if r["passes_is_bars"]], default=None)
        print(f"{k:30s} passes up to m = {last_ok} | " + " ".join(f"{r['m']:g}:{r['base']['pf']:.2f}/{r['stress']['pf']:.2f}" for r in rows))
    json.dump(out, open(os.path.join(OUT, "cost_grid.json"), "w"), indent=1)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "merge":
        merge()
    else:
        run(a or ["xauusd", "us100", "btcusd", "ethusd"])
