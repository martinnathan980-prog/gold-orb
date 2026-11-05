"""ONE-TIME validation of the two pre-chosen finalists (chosen on IS only) + interpretation diagnostics.
Run once.  Every VAL access goes through gl.cut(..., track, label) and is logged."""
import json
import os

import numpy as np
import pandas as pd

from common import RES, Px, gl, local_times, summarize, tstat
from goldlab.evalkit import evaluate_is, is_criteria, val_criteria
from goldlab.sim import simulate
import strategy

m1 = gl.load_m1("xauusd")  # full 2013-2025
nb = json.load(open(os.path.join(RES, "neighbors.json")))
cands = []


def fill_rate(o, rep):
    et = m1.index[np.minimum(o.entry_i.to_numpy(), len(m1) - 1)]
    n_is = int(((et >= pd.Timestamp('2013-01-01', tz='UTC')) & (et < pd.Timestamp('2022-01-01', tz='UTC'))).sum())
    return round(rep['n'] / max(1, n_is), 3)


for name, params in strategy.FINALISTS.items():
    o = strategy.make_orders(m1, **params)
    t, rep, rep_s = evaluate_is(m1, o)
    crit = is_criteria(rep, rep_s)
    crit["neighbor_median_pf>=1.10"] = nb[name]["median_neighbor_pf"] >= 1.10
    crit["pass"] = all(v for k, v in crit.items() if k != "pass")
    tv = gl.cut(t, "val", track="seasonality", label=name)          # <-- the single VAL look
    rv = gl.report(tv)
    vc = val_criteria(rv)
    gl.show(rep, f"{name} IS")
    gl.show(rep_s, f"{name} IS stress x1.5")
    gl.show(rv, f"{name} VAL")
    print("IS criteria:", crit, "\nVAL criteria:", vc, "\n")
    cands.append({"name": name, "params": params, "is": rep, "is_stress": {k: rep_s.get(k) for k in ("pf", "expectancy_R", "t_stat", "years_pos")},
                  "neighbor_median_pf": nb[name]["median_neighbor_pf"], "is_criteria": crit,
                  "val": rv, "val_criteria": vc, "fill_rate_is": fill_rate(o, rep)})

# ---------------- interpretation diagnostics (after the finalist look; nothing is re-tuned)
print("=== diagnostics (VAL 2022-2025, interpretation only)")
plc = {**strategy.FINALISTS["FRI_PM_LIM"], "weekdays": (0, 1, 2, 3)}
tp = simulate(m1, strategy.make_orders(m1, **plc))
rp = gl.report(gl.cut(tp, "val", track="seasonality", label="diagnostic-placebo-MonThu-13:30-16:45"))
print(f"placebo Mon-Thu same window (limit entry): n={rp['n']} PF={rp['pf']} exp={rp['expectancy_R']} t={rp['t_stat']} yrs={rp['years_pos']}")
px = Px(m1)
d1 = gl.bars(m1, "D")
days = pd.DatetimeIndex(d1.index[(d1.index >= "2022-01-01") & (d1.index < "2026-01-01")])
fr, oth = days[days.dayofweek == 4], days[days.dayofweek < 4]
def w(dd0, t0, dd1, t1):
    return np.log(px.at(local_times(dd1, t1, gl.NY), 5) / px.at(local_times(dd0, t0, gl.NY), 5)) * 1e4
diag = {}
for lab, r, yy in (("Fri 13:30->16:45 mid", w(fr, "13:30", fr, "16:45"), fr.year),
                   ("Mon-Thu 13:30->16:45 mid", w(oth, "13:30", oth, "16:45"), oth.year),
                   ("Fri 13:30->Sun 22:00 mid", w(fr, "13:30", fr + pd.Timedelta(days=2), "22:00"), fr.year),
                   ("Fri 16:45->Sun 19:00 (weekend gap+1h) mid", w(fr, "16:45", fr + pd.Timedelta(days=2), "19:00"), fr.year)):
    s = summarize(r, yy, lab)
    diag[lab] = s
    print(f"{lab:42s} n={s['n']} mean={s['mean_bp']:+.2f} bp t={s['t']:+.2f} sd={s['sd_bp']} yrs={s['yrs_same_sign']} {s['by_year']}")
p0, p1 = px.at([pd.Timestamp("2022-01-03 00:00", tz="UTC")], 60)[0], px.before([pd.Timestamp("2025-12-31 21:00", tz="UTC")], 600)[0]
hrs = ((m1.index >= "2022-01-01") & (m1.index < "2026-01-01")).sum() / 60
drift_h = np.log(p1 / p0) * 1e4 / hrs
print(f"VAL buy&hold {p0:.0f}->{p1:.0f} ({(p1 / p0 - 1) * 100:.0f}%), unconditional drift {drift_h:.2f} bp per trading hour "
      f"-> beta share of a 3.25h Friday hold ~{3.25 * drift_h:.1f} bp, of the 7.5h+weekend hold ~{7.5 * drift_h:.1f} bp (+ weekend gap drift)")
diag["val_drift_bp_per_trading_hour"] = round(drift_h, 3)
diag["placebo_MonThu_FRI_PM_LIM_val"] = {k: rp.get(k) for k in ("n", "pf", "expectancy_R", "t_stat", "years_pos")}
with open(os.path.join(RES, "candidates.json"), "w") as f:
    json.dump({"track": "seasonality", "configs_tested": sum(1 for _ in open(os.path.join(RES, "trials.jsonl"))),
               "finalists": cands, "val_diagnostics": diag}, f, indent=1, default=str)
print("saved candidates.json")
