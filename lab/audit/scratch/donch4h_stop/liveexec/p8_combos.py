"""P8: combined 'operating modes' for the French retail trader, with plausible retail frictions
(slippage 3 bp/side on market/stop fills, swaps 8 %/3 % per year), plus the no-OCO double-fill risk
of manually placed overnight pending orders, and max hold under the EA's deadline rule.

  E_auto      EA on a VPS, pending OCO stops at every 4 h close, EA trailing every M1 (= baseline orders)
  P_ea_W1     human places both pending stops at the 4 h closes inside 07-23 Paris (GTC overnight),
              EA (mode 1, VPS) trails every M1
  P_m3_W1     same entries, no EA: SL moved by hand at the in-window 4 h closes only
  M3_W1       human enters at market 5 min after the alert (07-23 Paris only), SL moved at in-window 4 h closes
"""
import sys
from dataclasses import replace
sys.path.insert(0, "/home/user/gold-orb/lab/audit/scratch/donch4h_stop/liveexec")
import numpy as np
import pandas as pd
from common import COSTS, HERE, PARIS, S, PARAMS, fmt, gl, is_part, simulate2, stats, val_part

m1 = gl.load_m1("xauusd")
idx = m1.index; N1 = len(idx)
o = pd.read_pickle(f"{HERE}/orders_base.pkl")
arrays = tuple(m1[k].to_numpy(np.float64) for k in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"))
par = gl.local(idx, PARIS); ph = par.hour.to_numpy() + par.minute.to_numpy() / 60
W1 = (ph >= 7) & (ph < 23)
def win_at(times):
    p = gl.local(pd.DatetimeIndex(times), PARIS); h = p.hour.to_numpy() + p.minute.to_numpy() / 60
    return (h >= 7) & (h < 23)
li = np.maximum.accumulate(np.where(W1, np.arange(N1), -1))
bucket = idx.floor("4h")
last_of_bucket = np.r_[bucket[1:] != bucket[:-1], True]
upd = last_of_bucket & win_at(bucket + pd.Timedelta(hours=4))
retail = replace(COSTS["xauusd"], slip_bps=3.0, swap_long=0.08, swap_short=0.03)

# pending-order brackets refreshed only at in-window decisions
b = S.bars_cached(m1, "4h")
up = b["h"].rolling(60).max().to_numpy(); dn = b["l"].rolling(60).min().to_numpy(); av = gl.atr(b, 14).to_numpy()
tc = pd.DatetimeIndex(b["t_close"]); i0 = gl.entry_index(m1, tc)
dec_ok = win_at(tc) & np.isfinite(up) & np.isfinite(dn) & np.isfinite(av) & (i0 < N1)
k_ok = np.flatnonzero(dec_ok); i1 = np.full(len(tc), -1, np.int64); i1[k_ok] = np.r_[i0[k_ok][1:], N1] - 1
keep = dec_ok & (i1 >= i0); i0c = np.clip(i0, 0, N1 - 1).astype(np.int64)
hit_i, hit_s = S._first_touch(m1["ah"].to_numpy(), m1["bl"].to_numpy(), m1["bo"].to_numpy(), m1["bc"].to_numpy(),
                              i0c, i1.astype(np.int64), np.nan_to_num(up, nan=np.inf), np.nan_to_num(dn, nan=-np.inf))
xi = S.exit_index(m1, S.add_trading_days(tc, 5) - pd.Timedelta(minutes=5))
keep &= (hit_i >= 0) & (xi > hit_i)
side = hit_s[keep]
po = pd.DataFrame({"entry_i": i0c[keep], "side": side, "etype": 1, "level": np.where(side > 0, up[keep], dn[keep]),
                   "expiry_i": i1[keep], "stop_dist": 2 * av[keep], "exit_i": xi[keep], "trail": 2 * av[keep],
                   "opp": np.where(side > 0, dn[keep], up[keep]), "exp2": i1[keep]})
pm = po.copy(); pm["exit_i"] = np.where(W1[pm.exit_i.to_numpy()], pm.exit_i.to_numpy(), li[pm.exit_i.to_numpy()])
pm = pm[pm.entry_i < pm.exit_i]
og = o[W1[o.trig_i.to_numpy()]]
e5 = gl.entry_index(m1, idx[og.trig_i.to_numpy()] + pd.Timedelta(minutes=5))
m3 = pd.DataFrame({"arm_i": og.entry_i.to_numpy(), "entry_i": e5, "side": og.side.to_numpy(), "etype": 0,
                   "stop_dist": og.stop_dist.to_numpy(), "trail": og.trail.to_numpy(), "exit_i": og.exit_i.to_numpy()})
m3["exit_i"] = np.where(W1[m3.exit_i.to_numpy()], m3.exit_i.to_numpy(), li[m3.exit_i.to_numpy()])
m3 = m3[m3.entry_i < m3.exit_i]
frames = []
for cname, cc in (("lab", None), ("retail", retail)):
    for v, oo, tm in (("E_auto", o, 0), ("P_ea_W1", po, 0), ("P_m3_W1", pm, 1), ("M3_W1", m3, 1)):
        tt = simulate2(m1, oo, no_overlap=True, trail_mode=tm, upd=upd, costs=cc, arrays=arrays)
        tt["v"] = f"{v}|{cname}"; frames.append(tt)
allf = pd.concat(frames, ignore_index=True, sort=False)
isf = is_part(allf); valf = val_part(allf, "operating-modes-x-retail-frictions")
for v in allf.v.unique():
    print(f"{v:18s} | IS {fmt(stats(isf[isf.v == v]))}\n{'':18s} | VAL {fmt(stats(valf[valf.v == v]))}")
# no-OCO risk: opposite pending touched between the fill and the next in-window decision (IS only)
tp = isf[isf.v == "P_ea_W1|lab"]
ah, bl = m1["ah"].to_numpy(), m1["bl"].to_numpy()
dbl = 0
for fi_, sd, ex, op, xi_ in zip(tp.fill_i.to_numpy(), tp.side.to_numpy(), tp.exp2.to_numpy(), tp.opp.to_numpy(), tp.x_i.to_numpy()):
    seg = slice(int(fi_), int(ex) + 1)
    if sd > 0 and bl[seg].min() <= op: dbl += 1
    if sd < 0 and ah[seg].max() >= op: dbl += 1
print(f"IS P_ea_W1: trades where the opposite (non-OCO) pending would also be touched before the next in-window check: {dbl} of {len(tp)}")
