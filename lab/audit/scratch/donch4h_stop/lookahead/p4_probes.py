"""P4/P5: timing-shift, look-ahead-sensitivity, level-source, grid, perturbation and fill-model probes.
All variants run through refimpl2 (identical to the engine at default settings, checked first).
VAL numbers: one logged gl.cut per probe family (variants concatenated, column 'variant')."""
import json
import sys
import time

sys.path.insert(0, ".")
sys.path.insert(0, "audit/scratch/donch4h_stop/lookahead")
import numpy as np
import pandas as pd

import goldlab as gl
import refimpl as RI
import refimpl2 as R2

T0 = time.time()
t, c = RI.load_raw()
idx = pd.DatetimeIndex(pd.to_datetime(t, utc=True))
ny = idx.tz_convert("America/New_York")
ny_min = (ny.hour * 60 + ny.minute).to_numpy()
ny_dow = ny.dayofweek.to_numpy()
OUT = {}


def family(name, variants):
    """variants: dict label -> kwargs. Returns IS and VAL stats per variant."""
    frames = []
    for lab, kw in variants.items():
        tr = R2.run(t, c, **kw)
        tr["variant"] = lab
        frames.append(tr)
    allf = pd.concat(frames, ignore_index=True)
    is_ = allf[(allf.entry_time >= pd.Timestamp("2013-01-01", tz="UTC")) & (allf.entry_time < pd.Timestamp("2022-01-01", tz="UTC"))]
    val = gl.cut(allf, "val", track="review", label=f"lookahead:donch4h_stop:{name}")
    res = {}
    for lab in variants:
        res[lab] = {"is": R2.stats(is_[is_.variant == lab]), "val": R2.stats(val[val.variant == lab])}
    OUT[name] = res
    print(f"\n== {name}  ({time.time()-T0:.0f}s)")
    for lab, r in res.items():
        print(f"  {lab:28s} IS {r['is']}\n  {'':28s} VAL {r['val']}")
    return res


# 0) baseline must reproduce the engine
base = family("base", {"base": {}})
assert base["base"]["is"]["n"] == 499 and abs(base["base"]["is"]["pf"] - 1.35) < 1e-3, base

# 1) activation delay (M1 bars after the 4h close) and deliberate early activation (look-ahead)
family("delay", {f"delay{d:+d}": {"delay": d} for d in (-5, -2, -1, 1, 2, 3, 5, 10, 15, 30, 60, 120, 240)})

# 2) stale levels / channel excluding the current bin / grid offsets
family("levels_timing", {"lag1": {"lag": 1}, "lag2": {"lag": 2}, "excl_current": {"excl_current": True},
                         "grid+1h": {"offset_ns": 1 * 3600 * 10**9}, "grid+2h": {"offset_ns": 2 * 3600 * 10**9},
                         "grid+3h": {"offset_ns": 3 * 3600 * 10**9}})

# 3) level source: how an MT5 bid-chart EA would compute the channel
family("level_source", {"bid": {"src": "bid"}, "ask": {"src": "ask"}, "minmid": {"src": "minmid"},
                        "bid_atr_mid": {"src": "bid", "atr_src": "mid"}})

# 4) path fragility: tiny perturbations (20 seeds each)
fam = {}
for s in range(20):
    fam[f"noise0.05_s{s}"] = {"level_noise": 0.05, "seed": s}
    fam[f"noise0.50_s{s}"] = {"level_noise": 0.50, "seed": s}
    fam[f"rdelay2_s{s}"] = {"delay_rand": 2, "seed": s}
    fam[f"trail1pct_s{s}"] = {"trail_noise": 0.01, "seed": s}
pert = family("perturb", fam)
summ = {}
for kind in ("noise0.05", "noise0.50", "rdelay2", "trail1pct"):
    for per in ("is", "val"):
        v = np.array([pert[f"{kind}_s{s}"][per]["pf"] for s in range(20)])
        summ[f"{kind}/{per}"] = {"min": round(float(v.min()), 3), "p10": round(float(np.percentile(v, 10)), 3),
                                 "median": round(float(np.median(v)), 3), "p90": round(float(np.percentile(v, 90)), 3),
                                 "max": round(float(v.max()), 3)}
OUT["perturb_summary"] = summ
print("\nperturbation PF summary:")
for k_, v in summ.items():
    print(f"  {k_:16s} {v}")

# 5) fast-market fill model: a fraction of the fill bar's range beyond the trigger is paid
family("fill_model", {f"ffrac{f}": {"ffrac": f} for f in (0.1, 0.25, 0.5)})

# 6) no fills allowed in the daily rollover window / Sunday open (spread-spike minutes)
roll = (ny_min >= 16 * 60 + 55) & (ny_min < 18 * 60 + 15)   # last 5 min before + first 15 min after the daily break
sunday_open = (ny_dow == 6) & (ny_min >= 17 * 60) & (ny_min < 18 * 60 + 30)
family("blocked_windows", {"no_rollover_fills": {"nofill": roll}, "no_sunday_open_fills": {"nofill": sunday_open},
                           "no_both": {"nofill": roll | sunday_open}})

json.dump(OUT, open("audit/scratch/donch4h_stop/lookahead/p4_probes.json", "w"), indent=1)
print(f"total {time.time()-T0:.0f}s")
