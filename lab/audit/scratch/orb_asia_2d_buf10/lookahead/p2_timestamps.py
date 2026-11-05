"""P2: timestamp convention + time-zone checks.
 (a) gaps between consecutive M1 bars: where do they sit in NY time (daily break 17:00-18:00 NY, weekend)?
 (b) bar labelling: rebuild M1 bars from the 2025 tick files and compare with the parquet (start-labelled?)
 (c) session windows in UTC across DST (London) and the US/UK DST-mismatch weeks."""
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'audit/scratch/orb_asia_2d_buf10/lookahead')
from common import *
m1 = load()
RUN_AB = False
idx = m1.index
if RUN_AB:
  pass
gap = np.diff(idx.asi8) // 60_000  # minutes
ny = idx[1:].tz_convert(gl.NY)
g = pd.DataFrame({"gap": gap, "ny_h": ny.hour, "ny_m": ny.minute, "dow": ny.dayofweek, "t": idx[1:]})
big = g[g.gap > 1]
print("bars", len(idx), "gaps>1min", len(big))
print("gap size distribution (min):", big.gap.describe().round(1).to_dict())
# classify: weekend reopen (Sunday ~18:00 NY), daily reopen (18:00 NY), other
wk = big[(big.gap > 24 * 60)]
dly = big[(big.gap <= 24 * 60) & (big.ny_h == 18) & (big.ny_m <= 5)]
oth = big.drop(wk.index).drop(dly.index)
print("weekend/holiday reopen gaps", len(wk), "| daily 18:00 NY reopen", len(dly), "| other", len(oth))
print("reopen hour (NY) of >24h gaps:", wk.ny_h.value_counts().head(5).to_dict())
print("other gaps by size:", pd.cut(oth.gap, [1, 2, 5, 15, 60, 240, 1440]).value_counts().sort_index().to_dict())
# what NY clock time do the daily breaks START at?  (last bar before an 18:00 NY reopen)
prev = idx[:-1][big.index[(big.gap <= 24*60) & (big.ny_h == 18)]].tz_convert(gl.NY)
print("last bar before daily break (NY hh:mm):", pd.Series(prev.strftime('%H:%M')).value_counts().head(5).to_dict())

# (b) tick -> M1 reconstruction on a few days
import glob
fs = sorted(glob.glob('/home/user/gold-orb/download/xauusd-tick-2025-*.csv.gz'))[:1]
tk = pd.read_csv(fs[0], nrows=3_000_000)
tk['ts'] = pd.to_datetime(tk.timestamp, unit='ms', utc=True)
tk = tk[(tk.ts >= '2025-06-02') & (tk.ts < '2025-06-05')]
for lab_, flo in (("start-label", tk.ts.dt.floor('1min')), ("end-label", tk.ts.dt.floor('1min') + pd.Timedelta(minutes=1))):
    gb = tk.groupby(flo)
    rb = pd.DataFrame({"bo": gb.bidPrice.first(), "bh": gb.bidPrice.max(), "bl": gb.bidPrice.min(), "bc": gb.bidPrice.last(),
                       "ao": gb.askPrice.first(), "ah": gb.askPrice.max(), "al": gb.askPrice.min(), "ac": gb.askPrice.last()})
    j = rb.join(m1, rsuffix='_m1', how='inner')
    err = {c: float((j[c] - j[c + '_m1']).abs().median()) for c in ("bo", "bh", "bl", "bc", "ah", "al")}
    exact = {c: float(((j[c] - j[c + '_m1']).abs() < 1e-6).mean()) for c in ("bo", "bh", "bl", "bc", "ah", "al")}
    print(lab_, "matched bars", len(j), "median abs err", err, "share exact", {k: round(v, 3) for k, v in exact.items()})

# (c) session windows in UTC
PP = dict(S.DEFAULTS); PP.update(P)
s = S.sessions(m1, PP)
s['rs_utc'] = s.t_rs.dt.strftime('%H:%M'); s['re_utc'] = s.t_re.dt.strftime('%H:%M'); s['x_utc'] = pd.DatetimeIndex(s.t_x).strftime('%H:%M')
s['month'] = s.date.dt.month
print("range start UTC by month:\n", s.groupby('month').rs_utc.agg(lambda x: x.value_counts().to_dict()).to_string())
print("exit 16:00 NY in UTC by month:\n", s.groupby('month').x_utc.agg(lambda x: x.value_counts().to_dict()).to_string())
# DST mismatch weeks 2019: US DST starts 2019-03-10, UK 2019-03-31; UK ends 2019-10-27, US 2019-11-03
for d in ("2019-03-11", "2019-03-29", "2019-04-01", "2019-10-28", "2019-11-01", "2019-11-04"):
    r = s[s.date == d]
    if len(r):
        r = r.iloc[0]
        print(d, "range", r.t_rs, "->", r.t_re, "entry until", r.t_ee, "exit", r.t_x)
