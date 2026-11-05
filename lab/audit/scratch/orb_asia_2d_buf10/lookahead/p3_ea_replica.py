"""P3: independent, event-driven (EA-style) re-implementation of orb_asia_2d_buf10, written from the
rules in report.md section 3 WITHOUT calling strategy.py or goldlab.simulate.  Bar-by-bar loop:
  * collects the Asian range (bars starting 00:00-06:59 London) as the bars arrive,
  * at the first bar starting >= 07:00 London arms an OCO pair (Ask >= H+0.1W / Bid <= L-0.1W) valid until 12:00 London,
  * the FIRST touch decides the day; trade only if flat (and no exit happened in that same bar),
  * stop = opposite level (checked on Bid for longs / Ask for shorts), time exit at the open of the first bar
    starting >= 16:00 NY two business days later (numpy busday_offset, no holidays),
  * costs: 1.5bp slippage on stop entries, stop exits and time exits, commission 0.07, swap 5%/2% per 17:00 NY
    rollover with Wednesday x3.
Then compares trade by trade with the official pipeline (IS; VAL via logged cut)."""
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'audit/scratch/orb_asia_2d_buf10/lookahead')
from common import *
import datetime as dt

m1 = load()
idx = m1.index
N = len(m1)
ldn = idx.tz_convert(gl.LDN); nyt = idx.tz_convert(gl.NY)
l_date = ldn.normalize().tz_localize(None).values.astype('datetime64[D]')
l_min = (ldn.hour * 60 + ldn.minute).to_numpy()
l_dow = ldn.dayofweek.to_numpy()
ts = idx.asi8  # ms
bo, bh, bl, bc, ao, ah, al, ac = (m1[c].to_numpy().tolist() for c in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"))
l_date_np = l_date; l_date = l_date.astype('int64').tolist(); l_min = l_min.tolist(); l_dow = l_dow.tolist(); ts_np = ts; ts = ts.tolist()
SLIP = 1.5e-4; COMM = 0.07; SWL = 0.05; SWS = 0.02

def exit_ts_ms(dint):
    d2 = np.busday_offset(np.datetime64(int(dint), 'D'), 2, roll='forward')
    t = pd.Timestamp(str(d2) + ' 16:00').tz_localize(gl.NY).tz_convert('UTC')
    return t.value // 10**6

def nights(t_in, t_out):
    """17:00 NY rollovers strictly after entry and at/before exit, Mon-Fri, Wednesday x3 (naive calendar walk)."""
    a = pd.Timestamp(t_in, unit='ms', tz='UTC').tz_convert(gl.NY); b = pd.Timestamp(t_out, unit='ms', tz='UTC').tz_convert(gl.NY)
    n = 0
    for d in pd.date_range(a.tz_localize(None).normalize(), b.tz_localize(None).normalize(), freq='D'):
        r = (d + pd.Timedelta(hours=17)).tz_localize(gl.NY)
        if a < r <= b and r.dayofweek < 5:
            n += 3 if r.dayofweek == 2 else 1
    return n

trades = []
cur_day = None; rng_h = -1e300; rng_l = 1e300; rng_n = 0
armed = False; used = False; buy_lv = sell_lv = np.nan; day_x = None
pos = 0; ent_i = -1; ent_px = np.nan; stp = np.nan; x_ms = None; ent_day = None
for i in range(N):
    d = l_date[i]; mn = l_min[i]
    if d != cur_day:
        # new London calendar date: reset range collection
        cur_day = d; rng_h = -1e300; rng_l = 1e300; rng_n = 0; armed = False; used = False
    exited_this_bar = False
    # ---- manage open position (time exit at open, then stop) ----
    if pos != 0 and i > ent_i:
        if ts[i] >= x_ms:
            px = bo[i] * (1 - SLIP) if pos > 0 else ao[i] * (1 + SLIP)
            trades.append((ent_i, i, pos, ent_px, px, stp, 'time', ent_day)); pos = 0; exited_this_bar = True
        elif pos > 0 and bl[i] <= stp:
            px = min(stp, bo[i]) * (1 - SLIP)
            trades.append((ent_i, i, pos, ent_px, px, stp, 'stop', ent_day)); pos = 0; exited_this_bar = True
        elif pos < 0 and ah[i] >= stp:
            px = max(stp, ao[i]) * (1 + SLIP)
            trades.append((ent_i, i, pos, ent_px, px, stp, 'stop', ent_day)); pos = 0; exited_this_bar = True
    # ---- range collection ----
    if l_dow[i] < 5 and mn < 7 * 60:
        rng_h = max(rng_h, ah[i]); rng_l = min(rng_l, bl[i]); rng_n += 1
    # ---- arm at first bar >= 07:00 London ----
    if l_dow[i] < 5 and 7 * 60 <= mn < 12 * 60 and not armed and not used:
        armed = True
        W = rng_h - rng_l
        if rng_n >= 210 and W > 0:
            buy_lv = rng_h + 0.1 * W; sell_lv = rng_l - 0.1 * W; day_x = exit_ts_ms(d)
        else:
            used = True  # skipped day
    # ---- pending OCO ----
    if armed and not used and 7 * 60 <= mn < 12 * 60:
        up = ah[i] >= buy_lv; dn = bl[i] <= sell_lv
        if up or dn:
            used = True
            if up and dn:
                mo = 0.5 * (ao[i] + bo[i]); side = 1 if abs(buy_lv - mo) <= abs(mo - sell_lv) else -1
            else:
                side = 1 if up else -1
            if pos == 0 and not exited_this_bar:
                pos = side; ent_i = i; ent_day = d; x_ms = day_x
                if side > 0:
                    ent_px = max(buy_lv, ao[i]) * (1 + SLIP); stp = sell_lv
                else:
                    ent_px = min(sell_lv, bo[i]) * (1 - SLIP); stp = buy_lv
                # stop inside the fill bar (pessimistic, like the engine)
                if side > 0 and bl[i] <= stp:
                    trades.append((ent_i, i, pos, ent_px, stp * (1 - SLIP), stp, 'stop', ent_day)); pos = 0
                elif side < 0 and ah[i] >= stp:
                    trades.append((ent_i, i, pos, ent_px, stp * (1 + SLIP), stp, 'stop', ent_day)); pos = 0

print('loop done, trades', len(trades), flush=True)
T = pd.DataFrame(trades, columns=['ei', 'xi', 'side', 'entry', 'exit', 'stop', 'reason', 'day'])
T['entry_time'] = idx[T.ei.to_numpy()]
T['exit_ms'] = ts_np[T.xi.to_numpy()] + np.where(T.reason == 'time', 0, 60_000)
T['nights'] = [nights(ts_np[a], b) for a, b in zip(T.ei, T.exit_ms)]
T['swap'] = T.entry * np.where(T.side > 0, SWL, SWS) / 360 * T.nights
T['pnl'] = T.side * (T.exit - T.entry) - T.swap - COMM
T['R'] = T.pnl / (T.entry - T.stop).abs()
T.to_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/ea_replica_full.pkl')

off = pd.read_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/trades_base_full.pkl')
def compare(a, b, nm):
    A = a.set_index('entry_time'); B = b.set_index('entry_time')
    com = A.index.intersection(B.index)
    print(f"{nm}: official n={len(A)} replica n={len(B)} common={len(com)} only_off={len(A.index.difference(B.index))} only_rep={len(B.index.difference(A.index))}")
    dR = (A.loc[com, 'R'] - B.loc[com, 'R']).abs()
    dsw = (A.loc[com, 'swap'] - B.loc[com, 'swap']).abs()
    print(f"   max |dR| {dR.max():.2e}  n(|dR|>1e-6) {(dR > 1e-6).sum()}  max |dswap| {dsw.max():.2e}  side mismatch {(A.loc[com,'side']!=B.loc[com,'side']).sum()}")
    print("   official:", summ(a)); print("   replica :", summ(b))
    return A, B, com
A, B, com = compare(is_part(off), is_part(T), "IS")
bad = (A.loc[com, 'R'] - B.loc[com, 'R']).abs() > 1e-6
if bad.any():
    print(pd.DataFrame({'R_off': A.loc[com][bad].R, 'R_rep': B.loc[com][bad].R, 'sw_off': A.loc[com][bad].swap, 'sw_rep': B.loc[com][bad].swap}).head(20))
compare(val_part(off, "ea-replica-official"), val_part(T, "ea-replica-replica"), "VAL")
