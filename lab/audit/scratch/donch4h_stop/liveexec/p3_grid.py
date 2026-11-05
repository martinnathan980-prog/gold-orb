"""P3: 4 h bar grid.  The rule is defined on the UTC grid (00/04/../20 UTC).  An MT5 H4 chart on a
UTC+2/+3 server is on a different grid.  Same rule, same params, bars on:
  utc+0 (baseline), fixed utc+1h / +2h / +3h,
  ny17   = server clock NY+7h (UTC+2 winter / UTC+3 summer, US DST dates; strategy grid='ny17'),
  eet    = server clock Europe/Athens (UTC+2/+3 with EU DST dates, common for EU/Cyprus brokers).
"""
import sys
sys.path.insert(0, "/home/user/gold-orb/lab/audit/scratch/donch4h_stop/liveexec")
import numpy as np
import pandas as pd
from common import HERE, S, PARAMS, fmt, gl, is_part, stats, val_part

m1 = gl.load_m1("xauusd")
_AGG = {"bo": "first", "bh": "max", "bl": "min", "bc": "last", "ao": "first", "ah": "max", "al": "min", "ac": "last"}


def bars_clock(m1, clock):
    """4h bars whose boundaries are at multiples of 4h on a wall clock: ('fixed', h) = UTC+h, or a tz name."""
    if isinstance(clock, tuple):
        loc = m1.index.tz_localize(None) + pd.Timedelta(hours=clock[1])
    else:
        loc = m1.index.tz_convert(clock).tz_localize(None)
    x = m1.set_axis(loc)
    b = x.resample("4h", label="left", closed="left").agg(_AGG).dropna()
    last_utc = pd.Series(m1.index, index=loc).resample("4h", label="left", closed="left").last()
    b["t_close"] = last_utc.reindex(b.index) + pd.Timedelta(minutes=1)
    for c in "ohlc":
        b[c] = (b["b" + c] + b["a" + c]) / 2
    b = b.set_axis(pd.DatetimeIndex(b["t_close"])).sort_index()
    return b


p = S._p(PARAMS)
frames = []
for name, clock in (("utc+0", ("fixed", 0)), ("utc+1", ("fixed", 1)), ("utc+2", ("fixed", 2)),
                    ("utc+3", ("fixed", 3)), ("ny17", "ny17"), ("eet", "Europe/Athens")):
    if clock == "ny17":
        o = S.make_orders(m1, **{**PARAMS, "grid": "ny17"})
    else:
        b = bars_clock(m1, clock)
        a = gl.atr(b, int(p["atr_n"]))
        o = S._donchian_stop(m1, p, b, a, int(p["n"]))
    t = gl.simulate(m1, o, no_overlap=True)
    t["grid"] = name
    frames.append(t)
    print(name, "orders", len(o), "trades", len(t), flush=True)
allf = pd.concat(frames, ignore_index=True)
isf = is_part(allf)
valf = val_part(allf, "bar-grid-utc0-3-ny17-eet")
rows = []
for g in allf.grid.unique():
    si, sv = stats(isf[isf.grid == g]), stats(valf[valf.grid == g])
    print(f"{g:6s} | IS {fmt(si)}\n{'':6s} | VAL {fmt(sv)}")
    rows.append({"grid": g, **{f"is_{k}": x for k, x in si.items()}, **{f"val_{k}": x for k, x in sv.items()}})
pd.DataFrame(rows).to_csv(f"{HERE}/p3_grid.csv", index=False)
# overlap of trades between the UTC grid and ny17 (same side, entry within 4 h)
a_, b_ = allf[allf.grid == "utc+0"], allf[allf.grid == "ny17"]
a_ = a_[a_.entry_time < pd.Timestamp("2022-01-01", tz="UTC")]; b_ = b_[b_.entry_time < pd.Timestamp("2022-01-01", tz="UTC")]
bt = b_.entry_time.values
m = 0
for et, sd in zip(a_.entry_time.values, a_.side.values):
    j = np.searchsorted(bt, et)
    for k in (j - 1, j):
        if 0 <= k < len(bt) and abs(bt[k] - et) <= np.timedelta64(4, "h") and b_.side.values[k] == sd:
            m += 1; break
print(f"IS: share of UTC-grid trades with a same-side ny17-grid trade within 4 h: {m}/{len(a_)} = {m/len(a_):.0%}")
