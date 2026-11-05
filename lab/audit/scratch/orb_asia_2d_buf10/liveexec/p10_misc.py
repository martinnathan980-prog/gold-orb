"""P10: weekend-gap tail exposure, London-open fill clustering, spread at fill (all on the baseline path)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa: F401,F403

m1 = gl.load_m1("xauusd")
t = pd.read_pickle(os.path.join(HERE, "trades_base.pkl"))
idx = m1.index
ivals = idx.values
# weekend gaps seen by open positions: Sunday reopen vs Friday last quote, in R (side-signed, + = favourable)
gap_bars = np.where(np.diff(ivals).astype("timedelta64[m]").astype(np.int64) > 24 * 60)[0] + 1   # first bar after >24h gap
gt = idx[gap_bars]
rows = []
for k, r in t.iterrows():
    a = np.searchsorted(gt.values, r.entry_time.to_datetime64(), side="right")
    b = np.searchsorted(gt.values, r.exit_time.to_datetime64(), side="left")
    for j in range(a, b):
        gi = gap_bars[j]
        if r.side > 0:
            g = (m1.bo.iat[gi] - m1.bc.iat[gi - 1])
            to_stop = m1.bc.iat[gi - 1] - r.stop
        else:
            g = -(m1.ao.iat[gi] - m1.ac.iat[gi - 1])
            to_stop = r.stop - m1.ac.iat[gi - 1]
        rows.append({"entry": r.entry_time, "gap_R": g / r.risk, "room_R": to_stop / r.risk, "yr": r.entry_time.year})
g = pd.DataFrame(rows)
print("positions open across a >24h market gap:", len(g), "| gap in R (side-signed): p1 %.2f p5 %.2f median %.2f min %.2f max %.2f"
      % (g.gap_R.quantile(.01), g.gap_R.quantile(.05), g.gap_R.median(), g.gap_R.min(), g.gap_R.max()))
print("   cases where the adverse gap exceeded the remaining room to the stop:", int((-g.gap_R > g.room_R).sum()),
      "| min remaining room before gap (R):", round(float(g.room_R.min()), 2),
      "| cases with remaining room < 0.25R:", int((g.room_R < 0.25).sum()))
# London-open clustering of fills and spread at fill
tl = t.entry_time.dt.tz_convert(gl.LDN)
m = tl.dt.hour * 60 + tl.dt.minute - 7 * 60
fi = gl.entry_index(m1, t.entry_time)
spr_fill = (m1.ac - m1.bc).to_numpy()[fi]
med_spr_day = pd.Series((m1.ac - m1.bc).to_numpy()).groupby(np.asarray(trading_day(idx))).median()
rel = spr_fill / med_spr_day.reindex(np.asarray(trading_day(t.entry_time))).to_numpy()
print("fills in minute 0 / 0-4 / 0-14 after 07:00 London:", int((m == 0).sum()), int((m < 5).sum()), int((m < 15).sum()), "of", len(t))
print("spread at fill / that day's median spread: median %.2f  p90 %.2f  p99 %.2f | fills in 07:00-07:04 London: median %.2f p90 %.2f"
      % (np.median(rel), np.percentile(rel, 90), np.percentile(rel, 99), np.median(rel[m < 5]), np.percentile(rel[m < 5], 90)))
# VAL accesses logged by this lens
n = sum(1 for line in open(os.path.join(LAB, "results", "val_access.log")) if f"liveexec:{NAME}" in line)
print("VAL accesses logged by this lens so far:", n)
