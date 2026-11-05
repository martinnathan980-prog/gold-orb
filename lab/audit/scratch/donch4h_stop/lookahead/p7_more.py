"""P7: (1) tick-trailing point estimate with a heuristic intrabar path, (2) alerts-first execution
where night OCOs are left unchanged from the evening decision until 08:00 UTC, (3) cost stress x1.5
with the OCO side RE-RESOLVED under the stressed spreads (engine keeps the base-spread side),
(4) engine trades: data holes inside trades, stops hit on the fill bar, time exits moved by holes."""
import json
import sys
import time

sys.path.insert(0, ".")
sys.path.insert(0, "tracks/trend")
sys.path.insert(0, "audit/scratch/donch4h_stop/lookahead")
import numpy as np
import pandas as pd

import goldlab as gl
import refimpl as RI
import refimpl2 as R2
import strategy as S
from goldlab.evalkit import stressed_costs

T0 = time.time()
t, c = RI.load_raw()
OUT = {}
DAY = 86400 * 10**9


def hours_utc(d):
    return pd.to_datetime(d, utc=True).hour.to_numpy()


def evening_until_08(tt, dec_ns):
    """decisions at/after 20:00 UTC: OCO stays valid until the next weekday 08:00 UTC."""
    d = pd.to_datetime(dec_ns, utc=True)
    nxt = (d.normalize() + pd.Timedelta(days=1) + pd.Timedelta(hours=8))
    wd = nxt.dayofweek.to_numpy()
    nxt = nxt + pd.to_timedelta(np.where(wd == 5, 2, np.where(wd == 6, 1, 0)), unit="D")
    ex = np.searchsorted(tt, nxt.as_unit("ns").asi8, side="left") - 1
    return np.where(d.hour.to_numpy() >= 20, ex, -1)


def night_skip(d):
    return ~np.isin(hours_utc(d), [0, 4])


variants = {
    "base": {},
    "trail_heuristic_path": {"trail_mode": 3},
    "alerts_evening_oco_until_08utc": {"dec_filter": night_skip, "exp_fn": evening_until_08},
    "alerts_evening_oco_until_08utc+mt5trail": {"dec_filter": night_skip, "exp_fn": evening_until_08,
                                                 "trail_mode": 2},
    "stress_x1.5_reresolved": {"spread_mult": 1.5, "slip_bps": 2.25, "comm": 0.105},
}
frames = []
for lab, kw in variants.items():
    tr = R2.run(t, c, **kw)
    tr["variant"] = lab
    frames.append(tr)
allf = pd.concat(frames, ignore_index=True)
is_ = allf[(allf.entry_time >= pd.Timestamp("2013-01-01", tz="UTC")) & (allf.entry_time < pd.Timestamp("2022-01-01", tz="UTC"))]
val = gl.cut(allf, "val", track="review", label="lookahead:donch4h_stop:trailing-alerts-stress")
for lab in variants:
    r = {"is": R2.stats(is_[is_.variant == lab]), "val": R2.stats(val[val.variant == lab])}
    OUT[lab] = r
    print(f"  {lab:40s} IS {r['is']}\n  {'':40s} VAL {r['val']}")

# engine stress for comparison (side pre-resolved with base spreads)
m1 = gl.load_m1("xauusd")
orders = S.make_orders(m1, **S.FINALISTS["donch4h_stop"])
es = gl.simulate(m1, orders, costs=stressed_costs("xauusd"))
es_is, es_val = gl.cut(es, "is"), gl.cut(es, "val", track="review", label="lookahead:donch4h_stop:engine-stress")
print(f"  engine stress x1.5 (side not re-resolved): IS {R2.stats(es_is)}\n{'':44s}VAL {R2.stats(es_val)}")
OUT["engine_stress"] = {"is": R2.stats(es_is), "val": R2.stats(es_val)}

# ---- (4) engine trades: data holes, fill-bar stops, time exits moved by holes
eng = gl.simulate(m1, orders)
e_is = gl.cut(eng, "is")
e_val = gl.cut(eng, "val", track="review", label="lookahead:donch4h_stop:engine-holes")
idx = m1.index
gaps = np.diff(idx.as_unit("ns").asi8) / 60e9                      # minutes to next bar
ny = gl.local(idx[:-1], gl.NY)
nym = ny.hour * 60 + ny.minute
sched = ((nym >= 16 * 60 + 50) & (nym <= 18 * 60 + 5)) | (gaps > 36 * 60)   # daily break / weekend
for name, tt in (("IS", e_is), ("VAL", e_val)):
    fi = idx.get_indexer(tt.entry_time)
    xi = idx.get_indexer(tt.exit_time - pd.Timedelta(minutes=1) * (tt.reason != "time"))
    worst, n_hole, R_hole = [], 0, 0.0
    for a, b, R in zip(fi, xi, tt.R.to_numpy()):
        g = gaps[a:b]
        s_ = sched[a:b]
        un = g[(~s_) & (g > 15)]
        if len(un):
            n_hole += 1
            R_hole += R
            worst.append(un.max())
    fbar_stop = int(((tt.reason == "stop") & (tt.entry_time.dt.floor("min") == (tt.exit_time - pd.Timedelta(minutes=1)))).sum())
    print(f"  {name}: trades spanning an unscheduled data hole >15 min: {n_hole} (R {R_hole:+.1f}; longest "
          f"{max(worst) if worst else 0:.0f} min); stops hit on the fill bar: {fbar_stop}; time exits: {(tt.reason == 'time').sum()}")
    OUT[f"holes_{name}"] = {"n": n_hole, "R": round(R_hole, 1), "longest_min": float(max(worst)) if worst else 0.0,
                            "fill_bar_stops": fbar_stop}
# time exits moved before a closure / hole among taken trades
for name, tt in (("IS", e_is), ("VAL", e_val)):
    te = tt[tt.reason == "time"]
    xt = S.add_trading_days(pd.DatetimeIndex(te.dec_time), 5) - pd.Timedelta(minutes=5)
    early = (pd.Series(xt, index=te.index) - te.exit_time).dt.total_seconds() / 60
    print(f"  {name} time exits: minutes before schedule {list(np.round(early.to_numpy(), 1))}")
json.dump(OUT, open("audit/scratch/donch4h_stop/lookahead/p7_more.json", "w"), indent=1)
print(f"time {time.time()-T0:.0f}s")
