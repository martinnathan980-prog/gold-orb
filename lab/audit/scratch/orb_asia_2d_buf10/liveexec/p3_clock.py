"""P3: broker server clock.  The rule uses M1 bars only (London clock for the range/entry window,
New York clock for the exit), so the bar GRID of a UTC+2/+3 server is identical to the UTC grid for
M1/H1 (whole-hour offsets) and only the clock MAPPING matters.  Variants = what an EA that
hard-codes server hours would actually trade:
  C0 baseline (correct London / NY wall clocks)
  C1 NY-close server (UTC+2/+3 switching on US dates), fixed server hours 02:00-09:00 range,
     orders until 14:00, exit 23:00 server  -> range/entry window 1 h late in US/EU DST-gap weeks
  C2 EET server (UTC+2/+3 switching on EU dates), same fixed server hours -> range exact,
     exit 21:00 London = 17:00 NY (market closed) in DST-gap weeks
  C3 EA on fixed UTC (no DST): range 00-07 UTC, orders until 12 UTC, exit 21:00 UTC
  C4 EA on fixed UTC+2 'winter' hours for the range but NY exit correct (range 1 h late all summer)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa: F401,F403

S.TZ["UTC"] = "UTC"   # runtime only (adds a zone key), file untouched
m1 = gl.load_m1("xauusd")
t = pd.read_pickle(os.path.join(HERE, "trades_base.pkl"))
P = dict(PARAMS)
V = {
    "C0_baseline": {},
    "C1_NYclose_server_fixed_hours": dict(tz="NY", range_start="-05:00", range_end="02:00", entry_end="07:00"),
    "C2_EET_server_fixed_hours": dict(exit_tz="LDN", exit_time="21:00"),
    "C3_fixed_UTC_no_DST": dict(tz="UTC", range_start="00:00", range_end="07:00", entry_end="12:00",
                                exit_tz="UTC", exit_time="21:00"),
    "C4_range_on_winter_hours": dict(tz="UTC", range_start="00:00", range_end="07:00", entry_end="12:00"),
}
frames, info = [], {}
for k, over in V.items():
    p = dict(P)
    p.update(over)
    o = S.make_orders(m1, **p)
    tt = gl.simulate(m1, o, no_overlap=True)
    tt["variant"] = k
    frames.append(tt)
    # how many trades differ from the baseline (by session date + side + entry time)?
    key = set(zip(tt.entry_time, tt.side))
    kb = set(zip(t.entry_time, t.side))
    info[k] = {"n_trades": len(tt), "same_entry_as_base": len(key & kb)}
allt = pd.concat(frames)
ti = is_part(allt)
tv = val_part(allt, "server-clock mapping variants C0-C4 (fixed server hours / UTC / DST gaps)")
rows = []
for k in V:
    sa, sb = stats(ti[ti.variant == k]), stats(tv[tv.variant == k])
    rows.append({"variant": k, **info[k], "IS_n": sa["n"], "IS_pf": sa["pf"], "IS_t": sa["t"], "IS_yrs": sa["yrs_pos"],
                 "VAL_n": sb["n"], "VAL_pf": sb["pf"], "VAL_t": sb["t"]})
r = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(r.to_string(index=False))
r.to_csv(os.path.join(HERE, "p3_clock.csv"), index=False)
# DST-gap sessions per year (London-NY offset != 5 h)
d = pd.date_range("2013-01-01", "2025-12-31", freq="B")
l = S._local_times(d, "07:00", gl.LDN)
n = l.tz_convert(gl.NY)
gap = (n.hour != 2)
print("weekday sessions per year in US/EU DST gap:", pd.Series(gap, index=d).groupby(d.year).sum().to_dict())
# exits landing on the closed market (17:00-18:00 NY) in C2 / C3
for k in ("C2_EET_server_fixed_hours", "C3_fixed_UTC_no_DST"):
    x = allt[(allt.variant == k) & (allt.reason == "time")].exit_time.dt.tz_convert(gl.NY)
    print(k, "time exits by NY clock:", x.dt.strftime("%H:%M").value_counts().head(5).to_dict())
