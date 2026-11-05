"""P10: prep_data._drop_flat removes minutes whose BID is flat (O=H=L=C=previous close) -- even on trading days.
In such a minute the ASK may still move (spread change).  Does any dropped minute carry an ask extreme that
(a) would raise the Asian-range high, (b) would trigger the buy stop earlier than the official touch, or
(c) would hit a short's stop (ask) during the hold?  Raw Dukascopy CSVs, IS years (2013-2021) only."""
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'audit/scratch/orb_asia_2d_buf10/lookahead')
from common import *
import glob
m1 = load(); idx = m1.index
s = pd.read_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/sessions.pkl')
o = pd.read_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/orders_base.pkl')
t = is_part(pd.read_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/trades_base_full.pkl'))
o['d'] = pd.to_datetime(o.date); s['d'] = pd.to_datetime(s.date)
RAW = '/home/user/gold-orb/download'
tot = {"dropped_weekday": 0, "dropped_in_range": 0, "range_high_raised": 0, "dropped_in_entry_window": 0,
       "earlier_buy_trigger": 0, "dropped_in_short_holds": 0, "short_stop_hit_by_dropped": 0}
detail = []
for y in ([2014] if "--quick" in sys.argv else range(2013, 2022)):
    b = pd.read_csv(glob.glob(f'{RAW}/xauusd-m1-bid-{y}-*.csv.gz')[0]); a = pd.read_csv(glob.glob(f'{RAW}/xauusd-m1-ask-{y}-*.csv.gz')[0])
    for d in (a, b):
        d['ts'] = pd.to_datetime(d.timestamp, unit='ms', utc=True); d.set_index('ts', inplace=True)
    df = b.add_prefix('b_').join(a.add_prefix('a_'), how='inner')
    flat = (df.b_open == df.b_high) & (df.b_high == df.b_low) & (df.b_low == df.b_close)
    same = df.b_close == df.b_close.shift(1)
    ny = df.index.tz_convert(gl.NY); tday = (ny + pd.Timedelta(hours=7)).dayofweek
    drop = df[flat & same & (tday < 5)]
    drop = drop[~drop.index.isin(idx)]  # really absent from the parquet
    tot["dropped_weekday"] += len(drop)
    ldn = drop.index.tz_convert(gl.LDN); mins = ldn.hour * 60 + ldn.minute
    dd = pd.DatetimeIndex(ldn.normalize().tz_localize(None))
    sy = s[s.d.dt.year == y].set_index('d')
    # (a) range minutes
    inr = (mins < 420) & dd.isin(sy.index)
    r = drop[inr]; rd = dd[inr]
    tot["dropped_in_range"] += len(r)
    hi = sy.loc[rd, 'hi'].to_numpy()
    raised = r.a_high.to_numpy() > hi + 1e-9
    tot["range_high_raised"] += int(raised.sum())
    for ts_, ah_, h_ in zip(r.index[raised], r.a_high[raised], hi[raised]):
        detail.append(("range_high", ts_, round(ah_ - h_, 3)))
    # (b) entry window minutes before the official touch
    oy = o[o.d.dt.year == y].set_index('d')
    ine = (mins >= 420) & (mins < 720) & dd.isin(oy.index)
    e = drop[ine]; ed = dd[ine]
    tot["dropped_in_entry_window"] += len(e)
    buy = np.where(oy.loc[ed, 'side'] > 0, oy.loc[ed, 'level'], oy.loc[ed, 'stop'])
    touch_ts = idx[oy.loc[ed, 'entry_i'].to_numpy()]
    early = (e.a_high.to_numpy() >= buy) & (e.index < touch_ts)
    tot["earlier_buy_trigger"] += int(early.sum())
    for ts_ in e.index[early]:
        detail.append(("earlier_buy_trigger", ts_, None))
    # (c) short holds
    ty = t[(t.entry_time.dt.year == y) & (t.side < 0)]
    for _, rr in ty.iterrows():
        x = drop[(drop.index > rr.entry_time) & (drop.index < rr.exit_time)]
        tot["dropped_in_short_holds"] += len(x)
        hit = x[x.a_high >= rr.stop]
        if len(hit) and hit.index[0] < rr.exit_time - pd.Timedelta(minutes=1):
            tot["short_stop_hit_by_dropped"] += 1
            detail.append(("short_stop_hit", hit.index[0], round(rr.R, 2)))
    del a, b, df
    print(y, dict(tot), flush=True)
print("TOTAL", tot)
for d in [x for x in detail if x[0] != "range_high"] + detail[:3]:
    print(d)
