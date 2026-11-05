"""P3: causality probes by truncation, using the strategy's OWN code (make_orders) on truncated M1.

For random taken IS trades (decision k, fill bar f):
  (a) truncate at the decision (data < t_close): the channel / ATR that make_orders' internals
      compute for bin k must equal the full-data values (no future bar enters the levels);
  (b) truncate just AFTER the fill bar (data[: f+1]): the order for decision k must exist with the
      same side, level, stop_dist, trail, trig_i  -> nothing after the fill decides the order;
  (c) truncate just BEFORE the fill bar (data[: f]): no order may exist for decision k yet
      (the side is not decided before the touch).
Also: orders whose time exit cannot be localized (ambiguous NY hour) are silently dropped -> count.
"""
import sys
import time

sys.path.insert(0, ".")
sys.path.insert(0, "tracks/trend")
import numpy as np
import pandas as pd

import goldlab as gl
import strategy as S

t0 = time.time()
m1 = gl.load_m1("xauusd")
P = S.FINALISTS["donch4h_stop"]
full = S.make_orders(m1, **P)
tr = pd.read_pickle("audit/scratch/donch4h_stop/lookahead/trades_is_base.pkl")
taken = full.loc[tr.index]
rng = np.random.default_rng(7)
pick = taken.iloc[np.sort(rng.choice(len(taken), 40, replace=False))]


def internals(m):
    b = S.bars_cached(m, "4h")
    a = gl.atr(b, 14)
    up = b["h"].rolling(60).max()
    dn = b["l"].rolling(60).min()
    return pd.DataFrame({"t_close": b["t_close"], "up": up, "dn": dn, "atr": a})


ref_int = internals(m1).set_index("t_close")
res = {"a_ok": 0, "b_ok": 0, "c_ok": 0, "n": 0}
fails = []
for _, od in pick.iterrows():
    S._bar_cache.clear()
    dec = od.dec_time
    i0 = int(od.entry_i)
    f = int(od.trig_i)
    # (a) truncate at the decision (exclusive of the first tradable bar)
    sub = m1.iloc[:i0]
    it = internals(sub).set_index("t_close")
    va, vf = it.loc[dec], ref_int.loc[dec]
    a_ok = all(abs(va[k] - vf[k]) < 1e-9 for k in ("up", "dn", "atr"))
    # (b) truncate just after the fill bar
    S._bar_cache.clear()
    ob = S.make_orders(m1.iloc[:f + 1], **P)
    ob = ob[ob.dec_time == dec]
    b_ok = (len(ob) == 1 and int(ob.side.iloc[0]) == int(od.side) and abs(ob.level.iloc[0] - od.level) < 1e-9
            and abs(ob.stop_dist.iloc[0] - od.stop_dist) < 1e-9 and abs(ob.trail.iloc[0] - od.trail) < 1e-9
            and int(ob.trig_i.iloc[0]) == f)
    # (c) truncate just before the fill bar
    S._bar_cache.clear()
    oc = S.make_orders(m1.iloc[:f], **P)
    c_ok = int((oc.dec_time == dec).sum()) == 0
    res["n"] += 1
    res["a_ok"] += a_ok
    res["b_ok"] += b_ok
    res["c_ok"] += c_ok
    if not (a_ok and b_ok and c_ok):
        fails.append((str(dec), a_ok, b_ok, c_ok, len(ob)))
print(res, "fails:", fails[:10])

# exit-time localisation: how many decision bars get NaT (ambiguous) and are therefore dropped
S._bar_cache.clear()
b = S.bars_cached(m1, "4h")
xt = S.add_trading_days(pd.DatetimeIndex(b["t_close"]), 5) - pd.Timedelta(minutes=5)
print("decision bars:", len(b), " NaT time-exit (dropped):", int(pd.isna(xt).sum()))
# exit NY wall clock == decision NY wall clock - 5 min, and 5 trading days later, for TIME exits
xi = S.exit_index(m1, xt)
ny_dec = gl.local(pd.DatetimeIndex(b["t_close"]), gl.NY)
ny_x = gl.local(m1.index[np.clip(xi, 0, len(m1) - 1)], gl.NY)
same_clock = ((ny_dec - pd.Timedelta(minutes=5)).strftime("%H:%M") == ny_x.strftime("%H:%M"))
print("time-exit bar has the decision's NY wall clock - 5 min:", f"{same_clock.mean():.4f}",
      " (others = exit moved before a closure or data hole)")
moved = ~same_clock
gap_h = ((xt[moved] - m1.index[np.clip(xi[moved], 0, len(m1) - 1)]).total_seconds() / 3600)
print("  moved earlier: n", int(moved.sum()), " by hours: median", float(np.nanmedian(gap_h)),
      "max", float(np.nanmax(gap_h)), " any exit AFTER scheduled time:",
      int(((m1.index[np.clip(xi, 0, len(m1) - 1)] - xt).total_seconds() > 30 * 60).sum()))
hold_h = (m1.index[np.clip(xi, 0, len(m1) - 1)] - pd.DatetimeIndex(b["t_close"])).total_seconds() / 3600
print("max scheduled hold from decision (h):", float(np.nanmax(hold_h)))
print(f"time {time.time()-t0:.1f}s")
