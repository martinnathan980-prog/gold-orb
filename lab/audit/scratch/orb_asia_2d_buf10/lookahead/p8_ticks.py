"""P8: tick-level fidelity of the finalist's fills (Jun-Dec 2025 = VAL period, logged).
Re-simulates the official orders tick by tick (audit/tick_sim.py semantics: stop entry at the first tick with
Ask>=level / Bid<=level filled at THAT tick's quote; stop exit at the triggering tick's quote; time exit at the
first tick >= 16:00 NY).  Same costs added to both (1.5bp/side slippage, commission, swap) -> R difference.
Ticks are loaded month by month and filtered to the trade windows to keep memory modest."""
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'audit/scratch/orb_asia_2d_buf10/lookahead'); sys.path.insert(0, 'audit')
from common import *
import glob
from tick_sim import covered_span, tick_simulate
m1 = load(); idx = m1.index; ns = idx.as_unit('ns').asi8
o = pd.read_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/orders_base.pkl')
T = pd.read_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/trades_base_full.pkl')
v = val_part(T, "tick-fidelity-Jun-Dec2025(R terms, entry/exit jumps)")
w = v[v.entry_time >= pd.Timestamp('2025-06-01', tz='UTC')].copy()
act = ns[o.loc[w.index, 'entry_i'].to_numpy()]
end = pd.DatetimeIndex(w.exit_time).as_unit('ns').asi8 + 3600 * 10**9
parts = []
for f in sorted(glob.glob('/home/user/gold-orb/download/xauusd-tick-2025-*.csv.gz')):
    d = pd.read_csv(f, dtype={'timestamp': 'int64', 'askPrice': 'float64', 'bidPrice': 'float64'})
    tsn = d.timestamp.to_numpy() * 1_000_000
    keep = np.zeros(len(d), bool)
    for a, b in zip(act - 60 * 10**9, end):
        i0, i1 = np.searchsorted(tsn, a), np.searchsorted(tsn, b)
        keep[i0:i1] = True
    # keep file boundaries so covered_span sees the month-end holes
    keep[0] = keep[-1] = True
    parts.append(d[keep])
    del d
tk = pd.concat(parts).drop_duplicates('timestamp').sort_values('timestamp')
ticks = (tk.timestamp.to_numpy(np.int64) * 1_000_000, tk.bidPrice.to_numpy(np.float64), tk.askPrice.to_numpy(np.float64))
del tk, parts
cov = covered_span(act, end, ticks[0])
# extra guard: require that the filtered tick stream has no >60 h hole inside each window (filtering creates holes only between windows)
w = w[cov]
print("Jun-Dec 2025 trades:", len(cov), "covered by tick data:", int(cov.sum()))
oo = o.loc[w.index]
tk_ = tick_simulate(m1, oo, ticks)
both = w.join(tk_, rsuffix='_tick')
both = both[np.isfinite(both.pnl_tick)]
slip = 1.5e-4
# add the same costs to the tick result: slippage on entry and exit, commission, swap (same nights as official)
tick_entry = both.fill * (1 + slip * both.side)
tick_exit = both.exit_tick * (1 - slip * both.side)
both['pnl_tick_net'] = both.side * (tick_exit - tick_entry) - both.swap - both.commission
both['R_tick'] = both.pnl_tick_net / (tick_entry - both.stop).abs()
lv = oo.loc[both.index, 'level']
both['entry_jump_usd'] = both.side * (both.fill - lv)                     # tick fill beyond the level (adverse > 0)
m1_exit_raw = np.where(both.reason == 'time', both.exit / (1 - slip * both.side), both.exit / (1 - slip * both.side))
both['exit_jump_usd'] = -both.side * (both.exit_tick - m1_exit_raw)        # tick exit worse than M1 raw exit (>0 adverse)
same_reason = (both.reason == both.reason_tick).mean()
same_fill_min = (pd.DatetimeIndex(both.t_fill).floor('1min') == pd.DatetimeIndex(both.entry_time)).mean()
print(f"n={len(both)} same exit reason {same_reason:.3f}  tick fill in the same minute as the M1 fill {same_fill_min:.3f}")
print(f"entry jump (tick fill - level, adverse USD): mean {both.entry_jump_usd.mean():.3f} median {both.entry_jump_usd.median():.3f} p90 {both.entry_jump_usd.quantile(.9):.3f} max {both.entry_jump_usd.max():.3f}")
print(f"exit jump  (adverse USD): mean {both.exit_jump_usd.mean():.3f} median {both.exit_jump_usd.median():.3f} p90 {both.exit_jump_usd.quantile(.9):.3f}")
print(f"slippage budget per trade (2 x 1.5bp): {(both.entry * 2 * slip).mean():.3f} USD")
print(f"R per trade: M1 {both.R.mean():.4f}  tick(+same costs) {both.R_tick.mean():.4f}  diff {(both.R - both.R_tick).mean():.4f} R/trade")
print(f"PF: M1 {pf(both.R):.3f} tick {pf(both.R_tick):.3f}   (tiny sample, VAL period, 2025 prices)")
print(f"mean risk USD {both.risk.mean():.2f}; jump as share of risk: {(both.entry_jump_usd / both.risk).mean():.4f} R")
