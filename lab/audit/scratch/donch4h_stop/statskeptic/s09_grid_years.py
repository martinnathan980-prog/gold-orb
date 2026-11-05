"""(a) Pseudo-replications: the identical rule on 4h grids shifted by +1h, +2h, +3h from UTC
    midnight (an arbitrary design choice) and on the NY-17:00 (MT5 server) grid.  Different
    bar boundaries -> different channels, entries and chains: if the edge is real, IS and VAL
    should hold on every grid.  (strategy.bars_cached is monkey-patched IN THIS PROCESS ONLY.)
(b) Leave-one-year-out PF / t for IS and VAL; IS halves.
One logged VAL cut for (a); (b) uses s01's saved trades."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa

m1 = gl.load_m1("xauusd")
_AGG = {"bo": "first", "bh": "max", "bl": "min", "bc": "last",
        "ao": "first", "ah": "max", "al": "min", "ac": "last"}
orig_bars_cached = S.bars_cached


def bars_offset(m, rule, hours):
    off = pd.Timedelta(hours=hours)
    b = m.resample(rule, label="left", closed="left", offset=off).agg(_AGG).dropna()
    last = m.index.to_series().resample(rule, label="left", closed="left", offset=off).last().reindex(b.index)
    b["t_close"] = last + pd.Timedelta(minutes=1)
    for k in "ohlc":
        b[k] = (b["b" + k] + b["a" + k]) / 2
    return b


out = {"grids": {}}
parts = []
stress = stressed_costs("xauusd")
for name in ("utc+0", "utc+1", "utc+2", "utc+3", "ny17"):
    S._bar_cache.clear()
    if name == "ny17":
        S.bars_cached = orig_bars_cached
        o = S.make_orders(m1, **dict(PARAMS, grid="ny17"))
    else:
        h = int(name[-1])
        S.bars_cached = (lambda m, rule, h=h: bars_offset(m, rule, h))
        o = S.make_orders(m1, **PARAMS)
    S.bars_cached = orig_bars_cached
    t = gl.simulate(m1, o, no_overlap=True)
    ts = gl.simulate(m1, o, costs=stress, no_overlap=True)
    te = gl.simulate(m1, o, no_overlap=False)
    ri, rsi = rep_pair(t, ts)
    crit = is_criteria(ri, rsi)
    tei = gl.cut(te, "is")
    out["grids"][name] = {"is_n": ri["n"], "is_pf": ri["pf"], "is_t": ri["t_stat"], "is_years": ri["years_pos"],
                          "is_stress_pf": rsi["pf"], "is_pass": bool(crit["pass"]),
                          "is_long_R": ri["long_R"], "is_short_R": ri["short_R"], "is_every_pf": round(pf(tei.R), 3)}
    for v, d in (("normal", t), ("every", te)):
        x = d[d.entry_time >= VA_A - pd.Timedelta(days=10)].copy()
        x["grid"], x["variant"] = name, v
        parts.append(x)
    print(name, out["grids"][name], flush=True)
tv = gl.cut(pd.concat(parts, ignore_index=True), "val", track="review",
            label=label("grid-offset replications(utc+0..+3h, ny17)"))
for (gname, v), g in tv.groupby(["grid", "variant"]):
    if v == "normal":
        rv = gl.report(g)
        out["grids"][gname].update({"val_n": rv["n"], "val_pf": rv["pf"], "val_t": rv["t_stat"],
                                    "val_years": rv["years_pos"], "val_pass": bool(val_criteria(rv)["pass"]),
                                    "val_long_R": rv["long_R"], "val_short_R": rv["short_R"]})
    else:
        out["grids"][gname]["val_every_pf"] = round(pf(g.R), 3)
for k, v in out["grids"].items():
    print(k, v, flush=True)

# (b) leave-one-year-out
ti = pd.read_parquet(os.path.join(HERE, "cand_trades_is.parquet"))
tvv = pd.read_parquet(os.path.join(HERE, "cand_trades_val.parquet"))
for per, t in (("is", ti[ti.variant == "normal"]), ("val", tvv[tvv.variant == "normal"])):
    y = t.entry_time.dt.year
    out[f"loyo_{per}"] = {int(k): [round(pf(t.R[y != k]), 3), round(tstat(t.R[y != k]), 2)] for k in sorted(y.unique())}
t = ti[ti.variant == "normal"]
y = t.entry_time.dt.year
for nm, m in (("2013-2016", y <= 2016), ("2017-2021", y >= 2017)):
    out[f"is_half_{nm}"] = summarize(t[m])
json.dump(out, open(os.path.join(HERE, "s09_grid_years.json"), "w"), indent=1, default=str)
print(json.dumps({k: v for k, v in out.items() if k != "grids"}, indent=1, default=str))
