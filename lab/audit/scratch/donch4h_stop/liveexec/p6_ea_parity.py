"""P6: parity of lab/live/mql5/GoldOrb_Donchian4H.mq5 with the backtest, on the points that can be
emulated with the lab data.
  a  time-stop deadline: EA DeadlineUTC(bucket start, 5) vs backtest add_trading_days(t_close, 5)-5min
  b  auto mode: PlacePendings() skips a side when ask >= hi - StopsLevel (bid <= lo + StopsLevel) at the
     first tick of the bracket (gap / too close) -> trade missed (backtest fills it at the open)
  c  EA level construction: mid = M5 bid + MqlRates.spread/2 (one spread value per M5 bar) vs the
     backtest mid-high = (max bid-high + max ask-high)/2 of the 4 h bar
  d  weekend exposure / gaps through stops
"""
import sys
sys.path.insert(0, "/home/user/gold-orb/lab/audit/scratch/donch4h_stop/liveexec")
import numpy as np
import pandas as pd
from common import HERE, S, PARAMS, fmt, gl, is_part, simulate2, stats, val_part

m1 = gl.load_m1("xauusd")
idx = m1.index
N1 = len(idx)
o = pd.read_pickle(f"{HERE}/orders_base.pkl")
t = pd.read_pickle(f"{HERE}/trades_base.pkl")
arrays = tuple(m1[k].to_numpy(np.float64) for k in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"))
frames = []
tb = t.copy(); tb["v"] = "base"; frames.append(tb)

# ---------------------------------------------------------------- a: EA deadline
def ea_deadline(dec_utc):
    ny = dec_utc.tz_convert("America/New_York").tz_localize(None)
    added = 0
    while added < 5:
        ny += pd.Timedelta(days=1)
        if ny.weekday() <= 4:
            added += 1
    ny -= pd.Timedelta(minutes=5)
    mins = ny.hour * 60 + ny.minute
    wd = ny.weekday()      # Mon=0 .. Sun=6
    closed = wd == 5 or (wd == 6 and mins < 18 * 60) or (wd == 4 and mins >= 17 * 60)
    if closed:
        while ny.weekday() != 4:
            ny -= pd.Timedelta(days=1)
        ny = ny.normalize() + pd.Timedelta(hours=16, minutes=55)
    return pd.Timestamp(ny).tz_localize("America/New_York", nonexistent="shift_forward", ambiguous=True).tz_convert("UTC")


bucket = idx[o.entry_i.to_numpy()].floor("4h")            # EA decision = start of the UTC 4h bucket of the 1st tick
ea_dl = pd.DatetimeIndex([ea_deadline(b) for b in bucket])
ea_xi = np.searchsorted(idx.values, ea_dl.values, side="left").astype(np.int64)
ea_xi = np.minimum(ea_xi, N1 - 1)
bt_dl_bar = o.exit_i.to_numpy()
diff = ea_xi != bt_dl_bar
dmin = (idx[ea_xi] - idx[bt_dl_bar]).total_seconds() / 3600
print(f"a) brackets whose EA time-stop bar differs from the backtest: {diff.sum()} of {len(o)}; "
      f"hours EA-minus-backtest: {pd.Series(np.round(dmin[diff])).value_counts().head(8).to_dict()}")
oa = o.copy(); oa["exit_i"] = ea_xi
oa = oa[oa.exit_i > oa.trig_i]
ta = gl.simulate(m1, oa, no_overlap=True); ta["v"] = "a_EA_deadline"; frames.append(ta)

# ---------------------------------------------------------------- b: auto-mode placement
b4 = S.bars_cached(m1, "4h")
up = b4["h"].rolling(60).max().to_numpy(); dn = b4["l"].rolling(60).min().to_numpy()
av = gl.atr(b4, 14).to_numpy()
tc = pd.DatetimeIndex(b4["t_close"])
i0 = gl.entry_index(m1, tc)
i1 = np.r_[gl.entry_index(m1, tc[1:]), N1] - 1
ok = np.isfinite(up) & np.isfinite(dn) & np.isfinite(av) & (i0 < N1) & (i1 >= i0)
i0c = np.clip(i0, 0, N1 - 1).astype(np.int64)
ao_, bo_ = m1["ao"].to_numpy(), m1["bo"].to_numpy()
xt = S.add_trading_days(tc, 5) - pd.Timedelta(minutes=5)
xi = S.exit_index(m1, xt)
for lvl in (0.0, 0.5, 1.0, 2.0):
    upx = np.where(ao_[i0c] < up - lvl, up, np.inf)       # buy stop placeable only if hi > ask + lvl
    dnx = np.where(bo_[i0c] > dn + lvl, dn, -np.inf)
    hit_i, hit_s = S._first_touch(m1["ah"].to_numpy(), m1["bl"].to_numpy(), bo_, m1["bc"].to_numpy(), i0c,
                                  i1.astype(np.int64), np.nan_to_num(upx, nan=np.inf), np.nan_to_num(dnx, nan=-np.inf))
    keep = ok & (hit_i >= 0) & (xi > hit_i)
    side = hit_s[keep]
    ob = pd.DataFrame({"entry_i": i0c[keep], "side": side, "etype": 1,
                       "level": np.where(side > 0, up[keep], dn[keep]), "expiry_i": i1[keep],
                       "stop_dist": 2 * av[keep], "exit_i": xi[keep], "trail": 2 * av[keep]})
    tt = gl.simulate(m1, ob, no_overlap=True); tt["v"] = f"b_auto_stopslevel_{lvl:.1f}"; frames.append(tt)
    nb_ = int(((ao_[i0c] >= up - lvl) & ok).sum() + ((bo_[i0c] <= dn + lvl) & ok).sum())
    print(f"b) StopsLevel ${lvl:.1f}: bracket sides not placeable at the first tick: {nb_}")
fi = np.searchsorted(idx.values, t.entry_time.values)
gapfill = (fi == o.loc[t.index, "entry_i"].to_numpy())
print(f"b) baseline trades filled on the first M1 bar of their bracket: {gapfill.sum()} (IS {gapfill[(t.entry_time < pd.Timestamp('2022-01-01', tz='UTC')).to_numpy()].sum()}), "
      f"their R sum (all years) {t.R[gapfill].sum():+.1f}")

# ---------------------------------------------------------------- c: EA-style mid levels
g5 = m1.resample("5min", label="left", closed="left")
m5 = pd.DataFrame({"bh": g5["bh"].max(), "bl": g5["bl"].min(), "bo": g5["bo"].first(), "bc": g5["bc"].last(),
                   "spr_close": (m1["ac"] - m1["bc"]).resample("5min", label="left", closed="left").last(),
                   "spr_min": np.minimum(m1["ac"] - m1["bc"], m1["ao"] - m1["bo"]).resample("5min", label="left", closed="left").min()}).dropna()
last_utc = m1.index.to_series().resample("5min", label="left", closed="left").last().reindex(m5.index)
p = S._p(PARAMS)
for sp in ("spr_close", "spr_min"):
    hs = m5[sp] / 2
    mm = pd.DataFrame({"h": m5.bh + hs, "l": m5.bl + hs, "o": m5.bo + hs, "c": m5.bc + hs, "last": last_utc})
    g4 = mm.resample("4h", label="left", closed="left")
    b = pd.DataFrame({"o": g4["o"].first(), "h": g4["h"].max(), "l": g4["l"].min(), "c": g4["c"].last(),
                      "t_close": g4["last"].last() + pd.Timedelta(minutes=1)}).dropna()
    a = gl.atr(b, 14)
    # level differences vs the backtest bars (aligned on 4h start)
    bb = b4.reindex(b.index)
    uh = b["h"].rolling(60).max() - bb["h"].rolling(60).max()
    ul = b["l"].rolling(60).min() - bb["l"].rolling(60).min()
    print(f"c) {sp}: channel-high EA-minus-backtest $ median {np.nanmedian(uh):+.3f} p5 {np.nanpercentile(uh,5):+.3f} "
          f"p95 {np.nanpercentile(uh,95):+.3f}; channel-low median {np.nanmedian(ul):+.3f} p5 {np.nanpercentile(ul,5):+.3f} p95 {np.nanpercentile(ul,95):+.3f}")
    oc = S._donchian_stop(m1, p, b, a, 60)
    tt = gl.simulate(m1, oc, no_overlap=True); tt["v"] = f"c_EA_levels_{sp}"; frames.append(tt)

allf = pd.concat(frames, ignore_index=True, sort=False)
isf = is_part(allf)
valf = val_part(allf, "EA-parity-deadline-autoplacement-levels")
for v in allf.v.unique():
    print(f"{v:26s} | IS {fmt(stats(isf[isf.v == v]))}\n{'':26s} | VAL {fmt(stats(valf[valf.v == v]))}")

# ---------------------------------------------------------------- d: weekends / gaps (IS)
ti = is_part(t)
wd0 = ti.entry_time.dt.tz_convert("America/New_York")
wk = (ti.exit_time - ti.entry_time) > pd.Timedelta(0)
crosses = (gl.trading_day(ti.exit_time - pd.Timedelta(seconds=1)).isocalendar().week.to_numpy() !=
           gl.trading_day(ti.entry_time).isocalendar().week.to_numpy())
xi_ = np.searchsorted(idx.values, (ti.exit_time - pd.Timedelta(minutes=1)).values)
prev_gap = np.r_[np.inf, (np.diff(idx.values) / np.timedelta64(1, "m"))][np.clip(xi_, 0, N1 - 1)]
gap_exit = (prev_gap > 24 * 60) & (ti.reason != "time").to_numpy()
print(f"d) IS trades held over a weekend: {crosses.sum()} of {len(ti)}; exits on the first bar after a >24h closure: "
      f"{gap_exit.sum()}, their R: {np.round(ti.R.to_numpy()[gap_exit], 2).tolist()}; worst IS R {ti.R.min():.2f}; "
      f"R < -1.1: {(ti.R < -1.1).sum()}")
