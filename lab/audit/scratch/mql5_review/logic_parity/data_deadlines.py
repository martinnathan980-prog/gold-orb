"""On the real lab data (Dukascopy M1 2013-2026): where does the EA's deadline reference
(bucket start of the window) differ from the lab's (t_close of the decision bar), and where does
the EA's time-exit rule (first bar >= deadline, 16:59 NY special cases only) differ from the
lab's exit_index (last bar before any closure > 30 min)?

Counts on ALL decision bars (orders) and on the actual lab trades (zero costs)."""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, LAB)
sys.path.insert(0, os.path.join(LAB, "audit"))
import goldlab as gl  # noqa: E402
from goldlab.sim import Costs  # noqa: E402
from mql5_time import DeadlineUTC  # noqa: E402
from audit import load_strategy  # noqa: E402
S = load_strategy("trend")
add_trading_days, exit_index = S.add_trading_days, S.exit_index

NY = "America/New_York"
m1 = gl.load_m1("xauusd", start="2013-01-01", end="2026-12-31")
idx = m1.index
iv = idx.values
print("M1 bars", len(m1), idx[0], idx[-1])

# ---- 1. Friday last bar (NY clock) distribution
ny = idx.tz_convert(NY)
s = pd.Series(ny, index=idx)
tday = gl.trading_day(idx)
last_of_week = pd.Series(ny).groupby(pd.Series(ny).dt.to_period("W-SAT")).max()
fri_last = last_of_week.dt.strftime("%a %H:%M")
print("\nlast M1 bar of each week (NY clock), top values:\n", fri_last.value_counts().head(8).to_string())

# ---- 2. all 4h decisions (lab orders before no_overlap, both sides) : lab tc vs EA bucket start
b = gl.bars(m1, "4h")
tc = pd.DatetimeIndex(b["t_close"])
i0 = gl.entry_index(m1, tc)
ok = i0 < len(m1)
tc, i0 = tc[ok], i0[ok]
ea_bucket = idx[i0].floor("4h")                      # EA: decision = start of the bucket of the 1st bar it trades in
lab_xt = add_trading_days(tc, 5) - pd.Timedelta(minutes=5)
lab_xi = exit_index(m1, lab_xt)
ea_dl = pd.to_datetime([DeadlineUTC(int(t.timestamp())) for t in ea_bucket], unit="s", utc=True)
ea_xi = np.searchsorted(iv, ea_dl.values, side="left")          # EA: first bar with t >= deadline
ref_diff = tc != ea_bucket
print(f"\n4h decisions: {len(tc)} | lab tc != EA bucket start: {ref_diff.sum()}")
cat = pd.Series(np.where(ref_diff, "other", "same"))
dow = pd.DatetimeIndex(tc).tz_convert(NY)
gap_h = (idx[i0] - tc).total_seconds() / 3600
cat[ref_diff & (gap_h > 24)] = "post-weekend/holiday (>24h closed)"
cat[ref_diff & (gap_h <= 24) & (gap_h > 0.6)] = "post-closure 0.6-24h"
cat[ref_diff & (gap_h <= 0.6)] = "data hole / short closure at bucket end"
print(cat.value_counts().to_string())
xi_diff = lab_xi != ea_xi
print(f"exit bar differs (lab exit_index vs EA first-bar>=DeadlineUTC): {xi_diff.sum()} of {len(tc)}")
d = pd.DataFrame({"tc": tc, "ea_bucket": ea_bucket, "lab_xt": lab_xt, "ea_dl": ea_dl,
                  "lab_exit_bar": idx[np.clip(lab_xi, 0, len(idx) - 1)],
                  "ea_exit_bar": idx[np.clip(ea_xi, 0, len(idx) - 1)], "cat": cat.values})
d["why"] = np.where(d.tc != d.ea_bucket, "ref time", np.where(d.lab_xt != d.ea_dl, "deadline", "closure rule"))
dd = d[xi_diff]
print("  by cause:", dd.why.value_counts().to_dict())
dd2 = dd[dd.why != "ref time"]
if len(dd2):
    print("  exit-bar differences NOT explained by the reference time (closure rule / holidays):")
    print(dd2[["tc", "lab_xt", "lab_exit_bar", "ea_exit_bar"]].assign(
        lab_xt=lambda x: x.lab_xt.dt.tz_convert(NY), lab_exit_bar=lambda x: x.lab_exit_bar.dt.tz_convert(NY),
        ea_exit_bar=lambda x: x.ea_exit_bar.dt.tz_convert(NY)).head(30).to_string())

# ---- 3. actual lab trades (zero cost)
mod = S
orders = mod.make_orders(m1, **mod.FINALISTS["donch4h_stop"])
lab = gl.simulate(m1, orders, costs=Costs(commission=0, slip_bps=0, swap_long=0, swap_short=0))
lab = lab.reset_index(drop=True)
print(f"\nlab trades {len(lab)}; reasons: {lab.reason.value_counts().to_dict()}")
dec = pd.DatetimeIndex(lab.dec_time)
ent_bucket = lab.entry_time.dt.floor("4h")
lab_xt_t = add_trading_days(dec, 5) - pd.Timedelta(minutes=5)
lab_xi_t = exit_index(m1, lab_xt_t)
lab_dl_bar = idx[np.clip(lab_xi_t, 0, len(idx) - 1)]
ea_dl_t = pd.to_datetime([DeadlineUTC(int(t.timestamp())) for t in ent_bucket], unit="s", utc=True)
ea_dl_bar = idx[np.clip(np.searchsorted(iv, ea_dl_t.values, side="left"), 0, len(idx) - 1)]
lab["lab_tx_bar"] = lab_dl_bar
lab["ea_tx_bar"] = ea_dl_bar
lab["ref_diff"] = dec != ent_bucket
aff = lab[lab.lab_tx_bar != lab.ea_tx_bar].copy()
# a trade changes only if it is still open at the earlier of the two time exits
first_tx = np.minimum(aff.lab_tx_bar.values, aff.ea_tx_bar.values)
aff["open_at_earlier_tx"] = aff.exit_time.values >= first_tx
print(f"trades whose time-exit bar differs (EA vs lab): {len(aff)}; still open at the earlier one "
      f"(=> different exit): {int(aff.open_at_earlier_tx.sum())}")
show = aff[aff.open_at_earlier_tx]
if len(show):
    print(show[["entry_time", "side", "dec_time", "reason", "exit_time", "R", "lab_tx_bar", "ea_tx_bar"]].assign(
        lab_tx_bar=lambda x: x.lab_tx_bar.dt.tz_convert(NY).dt.strftime("%a %m-%d %H:%M NY"),
        ea_tx_bar=lambda x: x.ea_tx_bar.dt.tz_convert(NY).dt.strftime("%a %m-%d %H:%M NY")).to_string())
sun = lab[lab.ref_diff]
print(f"\ntrades entered in a window whose lab decision time != EA bucket start: {len(sun)}"
      f" (reasons {sun.reason.value_counts().to_dict()}, hold max {((sun.exit_time - sun.entry_time).dt.total_seconds()/86400).max():.2f} d)")
pd.to_pickle(lab, os.path.join(HERE, "lab_trades_zero.pkl"))
