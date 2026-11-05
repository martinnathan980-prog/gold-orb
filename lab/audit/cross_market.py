"""Generalisation check: run a gold finalist with its exact, untuned parameters on the other
markets (bid-only data + fixed synthetic spreads -> indicative only)."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import goldlab as gl
from audit import load_strategy

track, name = sys.argv[1], sys.argv[2]
mod = load_strategy(track)
p = mod.FINALISTS[name]
out = {}
for sym in ("xauusd", "eurusd", "gbpusd", "usdjpy", "deuidxeur", "lightcmdusd"):
    m1 = gl.load_m1(sym)
    t = gl.simulate(m1, mod.make_orders(m1, **p), sym=sym)
    row = {}
    for per in ("is", "val"):
        r = gl.report(gl.cut(t, per, track="audit", label=f"crossmkt:{track}:{name}:{sym}") if per == "val" else gl.cut(t, per))
        row[per] = {k: r.get(k) for k in ("n", "pf", "t_stat", "expectancy_R", "years_pos", "long_R", "short_R")}
    out[sym] = row
    print(sym, "IS", row["is"], "\n      VAL", row["val"], flush=True)
    gl.data._cache.pop(sym, None)
os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results", "audit"), exist_ok=True)
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results", "audit", f"crossmarket__{track}__{name}.json"), "w"), indent=1)
