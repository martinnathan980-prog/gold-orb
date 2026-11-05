"""Emulate the EA's CatchUp() replay flag on continuous live operation (NO downtime):
bar j is processed at the first tick of bar j+1 with g.last_m1 = open of bar j-1, so
g_replay = (idx[j+1] - idx[j-1] > 300 s).  While g_replay is true the EA suppresses the
LEVELS / ENTRY / EXIT pushes and Decide() skips PlacePendings() (mode 2: no broker orders).
Cross with the twin's trades (exact data) to count what a live user would miss."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, LAB); sys.path.insert(0, os.path.join(LAB, "live")); sys.path.insert(0, os.path.join(LAB, "audit"))
import numpy as np, pandas as pd
import goldlab as gl
import ea_twin

start, end = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("2019-01-01", "2026-12-31")
m1 = gl.load_m1("xauusd", start=start, end=end)
idx = m1.index
v = idx.values.astype("datetime64[s]").astype(np.int64)
rep = np.zeros(len(v), bool)
rep[1:-1] = (v[2:] - v[:-2]) > 300           # flag of bar j (processed when bar j+1 opens)
rep_s = pd.Series(rep, index=idx)
print(f"bars {len(v)} | bars processed with g_replay=1 in continuous operation: {rep.sum()} "
      f"| 'rattrapage termine' pushes ~{np.sum(np.diff(np.r_[0, rep.astype(int)]) == 1)}")

tr = ea_twin.run(m1, mt5like=False)
tr = tr[tr.entry_time < idx[-1] - pd.Timedelta(days=8)].reset_index(drop=True)
dec = tr.entry_time.dt.floor("4h")
first_bar = idx[np.searchsorted(idx.values, dec.values)]          # bar where Decide() runs
dec_rep = rep_s.reindex(first_bar).to_numpy()
ent_rep = rep_s.reindex(tr.entry_time).to_numpy()
xbar = np.where(tr.reason == "time", tr.exit_time, tr.exit_time - pd.Timedelta(minutes=1))
ext_rep = rep_s.reindex(pd.DatetimeIndex(xbar)).to_numpy()
ny = dec.dt.tz_convert("America/New_York")
sunday = (ny.dt.dayofweek == 6).to_numpy()
print(f"trades {len(tr)} | sum R {tr.R.sum():+.1f}")
print(f"decision bar processed in replay (mode 2 places NO order, no LEVELS push): {dec_rep.sum()} trades, "
      f"R {tr.R[dec_rep].sum():+.1f}  (of which Sunday-open window: {(dec_rep & sunday).sum()})")
print(f"entry bar in replay (ENTRY push suppressed): {ent_rep.sum()} | exit bar in replay (EXIT push suppressed): {ext_rep.sum()}")
print(f"  exits suppressed by reason: {tr.reason[ext_rep].value_counts().to_dict()}")
print(f"trades whose window is the Sunday-open bucket: {sunday.sum()}, R {tr.R[sunday].sum():+.1f}")
print(tr[dec_rep].head(8).to_string())

# where do the suppressed ENTRY / EXIT bars sit relative to the closure?
gap_before = pd.Series(np.r_[False, (v[1:] - v[:-1]) > 300], index=idx)   # bar is FIRST after a gap
gap_after = pd.Series(np.r_[(v[1:] - v[:-1]) > 300, False], index=idx)    # bar is LAST before a gap
for name, bars_ in (("ENTRY", pd.DatetimeIndex(tr.entry_time[ent_rep])), ("EXIT", pd.DatetimeIndex(xbar[ext_rep]))):
    fb = gap_before.reindex(bars_).to_numpy(); lb = gap_after.reindex(bars_).to_numpy()
    nyb = bars_.tz_convert("America/New_York")
    print(f"{name}: first bar after closure {fb.sum()} | last bar before closure {lb.sum()} | "
          f"Sunday-open bar {int(((nyb.dayofweek == 6) & fb).sum())}")
