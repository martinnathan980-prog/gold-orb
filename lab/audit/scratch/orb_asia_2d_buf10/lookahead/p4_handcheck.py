"""P4: hand verification of a random sample of IS trades against raw M1 rows (pure pandas on the
parquet rows, no strategy.py / sim.py code).  For each trade: range extremes and the minutes that set
them, levels, the bars just before / at the first touch, fill price, stop path, exit bar, swap nights, R."""
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'audit/scratch/orb_asia_2d_buf10/lookahead')
from common import *
m1 = load()
t = is_part(pd.read_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/trades_base_full.pkl'))
rng = np.random.default_rng(20261105)
pick = list(rng.choice(len(t), 12, replace=False))
# add special cases: longest hold, a Friday entry (weekend), largest R, smallest risk
t = t.reset_index(drop=True)
pick += [int(t.hold_min.idxmax()), int(t[t.entry_time.dt.tz_convert(gl.LDN).dt.dayofweek == 4].index[3]),
         int(t.R.idxmax()), int(t.risk.idxmin())]
SLIP = 1.5e-4
ok_all = True
for k in pick:
    r = t.loc[k]
    d = pd.Timestamp(r.date)
    rs = pd.Timestamp(d.strftime('%Y-%m-%d') + ' 00:00', tz=gl.LDN).tz_convert('UTC')
    re = pd.Timestamp(d.strftime('%Y-%m-%d') + ' 07:00', tz=gl.LDN).tz_convert('UTC')
    ee = pd.Timestamp(d.strftime('%Y-%m-%d') + ' 12:00', tz=gl.LDN).tz_convert('UTC')
    xd = np.busday_offset(np.datetime64(d.strftime('%Y-%m-%d')), 2, roll='forward')
    xt = pd.Timestamp(str(xd) + ' 16:00', tz=gl.NY).tz_convert('UTC')
    R = m1[(m1.index >= rs) & (m1.index < re)]
    H, L = R.ah.max(), R.bl.min(); W = H - L
    buy, sell = H + 0.1 * W, L - 0.1 * W
    E = m1[(m1.index >= re) & (m1.index < ee)]
    touch = E[(E.ah >= buy) | (E.bl <= sell)]
    tb = touch.index[0]
    side = 1 if touch.iloc[0].ah >= buy else -1
    prev = E[E.index < tb]
    no_prev_touch = bool(((prev.ah < buy) & (prev.bl > sell)).all())
    row = m1.loc[tb]
    fill = (max(buy, row.ao) * (1 + SLIP)) if side > 0 else (min(sell, row.bo) * (1 - SLIP))
    stop = sell if side > 0 else buy
    after = m1[(m1.index > tb) & (m1.index < xt)]
    hitbar = after[after.bl <= stop] if side > 0 else after[after.ah >= stop]
    first_bar_hit = (row.bl <= stop) if side > 0 else (row.ah >= stop)
    if first_bar_hit:
        xr, xtime, xpx = 'stop', tb, stop * (1 - side * SLIP)
    elif len(hitbar):
        hb = hitbar.index[0]; hr = m1.loc[hb]
        xpx = (min(stop, hr.bo) * (1 - SLIP)) if side > 0 else (max(stop, hr.ao) * (1 + SLIP))
        xr, xtime = 'stop', hb
    else:
        xb = m1[m1.index >= xt].index[0]; xrw = m1.loc[xb]
        xpx = xrw.bo * (1 - SLIP) if side > 0 else xrw.ao * (1 + SLIP)
        xr, xtime = 'time', xb
    # swap nights: 17:00 NY rollovers between fill and exit, Mon-Fri, Wed x3
    a = tb.tz_convert(gl.NY); b = (xtime + pd.Timedelta(minutes=0 if xr == 'time' else 1)).tz_convert(gl.NY)
    nights = 0
    for dd in pd.date_range(a.normalize(), b.normalize(), freq='D'):
        roll = dd + pd.Timedelta(hours=17)
        if a < roll <= b and roll.dayofweek < 5:
            nights += 3 if roll.dayofweek == 2 else 1
    swap = fill * (0.05 if side > 0 else 0.02) / 360 * nights
    pnl = side * (xpx - fill) - swap - 0.07
    Rh = pnl / abs(fill - stop)
    match = (side == r.side and abs(fill - r.entry) < 1e-6 and abs(xpx - r.exit) < 1e-6 and abs(Rh - r.R) < 1e-6
             and tb == r.entry_time and xr == r.reason)
    ok_all &= match
    print(f"--- trade {k}: date {d.date()} ({d.day_name()[:3]}) side {side:+d}  official side {int(r.side):+d}")
    print(f"  range UTC [{rs:%Y-%m-%d %H:%M}, {re:%H:%M}) bars {len(R)}: H=max ask high {H:.3f} @ {R.ah.idxmax():%H:%M}  L=min bid low {L:.3f} @ {R.bl.idxmin():%H:%M}  W={W:.3f}")
    print(f"  levels buy {buy:.3f} (Ask)  sell {sell:.3f} (Bid); no touch before {tb:%H:%M}: {no_prev_touch}; prev bar ah/bl "
          f"{(prev.ah.iloc[-1] if len(prev) else np.nan):.3f}/{(prev.bl.iloc[-1] if len(prev) else np.nan):.3f}")
    print(f"  touch bar {tb} ao {row.ao:.3f} ah {row.ah:.3f} bo {row.bo:.3f} bl {row.bl:.3f} -> fill {fill:.3f} (official {r.entry:.3f}); stop {stop:.3f} (official {r.stop:.3f})")
    print(f"  scheduled exit {xt} ; exit {xr} @ {xtime} px {xpx:.3f} (official {r.reason} {r.exit_time} {r.exit:.3f}); nights {nights} swap {swap:.3f} (official {r.swap:.3f})")
    print(f"  R hand {Rh:.4f} official {r.R:.4f}  MATCH={match}")
print("ALL MATCH:", ok_all, "n checked", len(pick))
