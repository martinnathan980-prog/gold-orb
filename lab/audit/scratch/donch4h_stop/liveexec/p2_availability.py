"""P2: human availability (Paris time).

Windows   W1 = 07:00-23:00 Paris, any market day      W2 = Mon-Fri 08:00-20:00 Paris
Variants
  S0   subset of the baseline trades whose trigger (fill) falls inside the window, instant fill
  S5   same subset, market entry 5 min after the trigger (re-anchored stop, model A1 of P1)
  D    signals outside the window -> entered at market at the next window open if the
       theoretical trade is still open then (re-anchored stop, EA-style exits)
  G0/G5 flat-gated: night triggers ignored, sequential one-position rule on the REAL position,
       entries at the trigger (G0) or 5 min later (G5)
  M3   'no EA, phone only': G5 entries, server-side initial stop, trailing stop moved only at the
       4 h closes that fall inside the window, time exit at the last in-window minute before the
       deadline
  M4   MT5 terminal built-in trailing (activates only once open profit >= 2 ATR), entries at the
       trigger (pending orders at the broker) [M4_0] or 5 min after it [M4_5]; terminal on 24/5
  P    pending OCO orders refreshed only at in-window 4 h closes (left GTC overnight, levels and
       ATR stale), exits EA-managed (P_ea) or as in M3 (P_m3)
"""
import sys
sys.path.insert(0, "/home/user/gold-orb/lab/audit/scratch/donch4h_stop/liveexec")
import numpy as np
import pandas as pd
from common import HERE, PARIS, S, PARAMS, fmt, gl, is_part, simulate2, stats, val_part

m1 = gl.load_m1("xauusd")
o = pd.read_pickle(f"{HERE}/orders_base.pkl")
t = pd.read_pickle(f"{HERE}/trades_base.pkl")
idx = m1.index
arrays = tuple(m1[k].to_numpy(np.float64) for k in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"))
N1 = len(idx)
par = gl.local(idx, PARIS)
ph = par.hour.to_numpy() + par.minute.to_numpy() / 60
dow = par.dayofweek.to_numpy()
WIN = {"W1": (ph >= 7) & (ph < 23), "W2": (ph >= 8) & (ph < 20) & (dow <= 4)}


def win_at(times, w):
    p = gl.local(pd.DatetimeIndex(times), PARIS)
    h = p.hour.to_numpy() + p.minute.to_numpy() / 60
    if w == "W1":
        return (h >= 7) & (h < 23)
    return (h >= 8) & (h < 20) & (p.dayofweek.to_numpy() <= 4)


def next_in(mask):
    """next_in[i] = smallest j >= i with mask[j] (N1 if none)."""
    j = np.where(mask, np.arange(N1), N1)
    return np.minimum.accumulate(j[::-1])[::-1]


def last_in(mask):
    j = np.where(mask, np.arange(N1), -1)
    return np.maximum.accumulate(j)


bucket = idx.floor("4h")
last_of_bucket = np.r_[bucket[1:] != bucket[:-1], True]
bound_time = bucket + pd.Timedelta(hours=4)

frames = []
def add(tr, name):
    x = tr.copy(); x["variant"] = name; frames.append(x)

add(t, "base")
fi = np.searchsorted(idx.values, t.entry_time.values)
od = o.loc[t.index]
for w in ("W1", "W2"):
    inw = win_at(t.entry_time, w)
    add(t[inw], f"S0_{w}")
    # S5: subset, 5-min-late market entry (re-anchored)
    e = gl.entry_index(m1, idx[fi] + pd.Timedelta(minutes=5))
    late = pd.DataFrame({"entry_i": e, "side": t.side.to_numpy(), "etype": 0, "stop_dist": od.stop_dist.to_numpy(),
                         "trail": od.trail.to_numpy(), "exit_i": od.exit_i.to_numpy()}, index=t.index)[inw]
    late = late[late.entry_i < late.exit_i]
    add(simulate2(m1, late, no_overlap=False, arrays=arrays), f"S5_{w}")
    # D: night signals deferred to the next window open (at market) if the theoretical trade still open
    nx = next_in(WIN[w])
    e2 = np.where(inw, gl.entry_index(m1, idx[fi] + pd.Timedelta(minutes=5)), nx[np.clip(fi, 0, N1 - 1)])
    alive = (e2 < N1) & (t.exit_time.values > idx[np.clip(e2, 0, N1 - 1)].values)
    dd = pd.DataFrame({"entry_i": e2, "side": t.side.to_numpy(), "etype": 0, "stop_dist": od.stop_dist.to_numpy(),
                       "trail": od.trail.to_numpy(), "exit_i": od.exit_i.to_numpy(), "inw": inw}, index=t.index)
    dd = dd[(inw | alive) & (dd.entry_i < dd.exit_i)]
    td = simulate2(m1, dd, no_overlap=False, arrays=arrays)
    add(td, f"D_{w}")
    add(td[~td.inw.astype(bool)], f"Donly_{w}")
    # G0 / G5 / M3: flat-gated on all armed+touched brackets, night triggers ignored
    trig_ok = WIN[w][o.trig_i.to_numpy()]
    og = o[trig_ok].copy()
    g0 = og[["entry_i", "side", "etype", "level", "expiry_i", "stop_dist", "exit_i", "trail"]].copy()
    add(simulate2(m1, g0, no_overlap=True, arrays=arrays), f"G0_{w}")
    e5 = gl.entry_index(m1, idx[og.trig_i.to_numpy()] + pd.Timedelta(minutes=5))
    g5 = pd.DataFrame({"arm_i": og.entry_i.to_numpy(), "entry_i": e5, "side": og.side.to_numpy(), "etype": 0,
                       "stop_dist": og.stop_dist.to_numpy(), "trail": og.trail.to_numpy(), "exit_i": og.exit_i.to_numpy()})
    g5 = g5[g5.entry_i < g5.exit_i]
    add(simulate2(m1, g5, no_overlap=True, arrays=arrays), f"G5_{w}")
    upd = last_of_bucket & win_at(bound_time, w)
    li = last_in(WIN[w])
    m3 = g5.copy()
    m3["exit_i"] = np.where(WIN[w][m3.exit_i.to_numpy()], m3.exit_i.to_numpy(), li[m3.exit_i.to_numpy()])
    m3 = m3[m3.entry_i < m3.exit_i]
    add(simulate2(m1, m3, no_overlap=True, trail_mode=1, upd=upd, arrays=arrays), f"M3_{w}")
    # P: pending orders refreshed only at in-window 4h closes, GTC overnight (stale levels / ATR)
    b = S.bars_cached(m1, "4h")
    up = b["h"].rolling(60).max().to_numpy(); dn = b["l"].rolling(60).min().to_numpy()
    av = gl.atr(b, 14).to_numpy()
    tc = pd.DatetimeIndex(b["t_close"])
    i0 = gl.entry_index(m1, tc)
    dec_ok = win_at(tc, w) & np.isfinite(up) & np.isfinite(dn) & np.isfinite(av) & (i0 < N1)
    k_ok = np.flatnonzero(dec_ok)
    i1 = np.full(len(tc), -1, np.int64)
    nxt = np.r_[i0[k_ok][1:], N1] - 1
    i1[k_ok] = nxt
    keep = dec_ok & (i1 >= i0)
    i0c = np.clip(i0, 0, N1 - 1).astype(np.int64)
    hit_i, hit_s = S._first_touch(m1["ah"].to_numpy(), m1["bl"].to_numpy(), m1["bo"].to_numpy(), m1["bc"].to_numpy(),
                                  i0c, i1.astype(np.int64), np.nan_to_num(up, nan=np.inf), np.nan_to_num(dn, nan=-np.inf))
    xt = S.add_trading_days(tc, 5) - pd.Timedelta(minutes=5)
    xi = S.exit_index(m1, xt)
    keep &= (hit_i >= 0) & (xi > hit_i)
    side = hit_s[keep]
    po = pd.DataFrame({"entry_i": i0c[keep], "side": side, "etype": 1, "level": np.where(side > 0, up[keep], dn[keep]),
                       "expiry_i": i1[keep], "stop_dist": 2 * av[keep], "exit_i": xi[keep], "trail": 2 * av[keep]})
    add(simulate2(m1, po, no_overlap=True, arrays=arrays), f"P_ea_{w}")
    pm = po.copy()
    pm["exit_i"] = np.where(WIN[w][pm.exit_i.to_numpy()], pm.exit_i.to_numpy(), li[pm.exit_i.to_numpy()])
    pm = pm[pm.entry_i < pm.exit_i]
    add(simulate2(m1, pm, no_overlap=True, trail_mode=1, upd=upd, arrays=arrays), f"P_m3_{w}")
# M4: MT5 built-in trailing (activation at profit >= trail distance)
base_o = o[["entry_i", "side", "etype", "level", "expiry_i", "stop_dist", "exit_i", "trail"]].copy()
add(simulate2(m1, base_o, no_overlap=True, trail_mode=2, arrays=arrays), "M4_0")
e5 = gl.entry_index(m1, idx[o.trig_i.to_numpy()] + pd.Timedelta(minutes=5))
m4 = pd.DataFrame({"arm_i": o.entry_i.to_numpy(), "entry_i": e5, "side": o.side.to_numpy(), "etype": 0,
                   "stop_dist": o.stop_dist.to_numpy(), "trail": o.trail.to_numpy(), "exit_i": o.exit_i.to_numpy()})
m4 = m4[m4.entry_i < m4.exit_i]
add(simulate2(m1, m4, no_overlap=True, trail_mode=2, arrays=arrays), "M4_5")

allf = pd.concat(frames, ignore_index=True, sort=False)
isf = is_part(allf)
valf = val_part(allf, "availability-W1W2-S0S5-D-G0G5-M3-M4-Pending")
rows = []
for v in allf.variant.unique():
    si, sv = stats(isf[isf.variant == v]), stats(valf[valf.variant == v])
    print(f"{v:10s} | IS {fmt(si)}\n{'':10s} | VAL {fmt(sv)}")
    rows.append({"variant": v, **{f"is_{k}": x for k, x in si.items()}, **{f"val_{k}": x for k, x in sv.items()}})
pd.DataFrame(rows).to_csv(f"{HERE}/p2_availability.csv", index=False)
# where do the alerts fall (IS only)?
ti = is_part(t)
p = gl.local(pd.DatetimeIndex(ti.entry_time), PARIS)
print("IS alerts by Paris hour:", pd.Series(p.hour).value_counts().sort_index().to_dict())
print("IS share in W1 %.0f%%, in W2 %.0f%%" % (100 * win_at(ti.entry_time, "W1").mean(), 100 * win_at(ti.entry_time, "W2").mean()))
for w in ("W1", "W2"):
    inw = win_at(ti.entry_time, w)
    print(f"IS {w}: in-window R {ti.R[inw].sum():+.1f} (n {inw.sum()}), out-of-window R {ti.R[~inw].sum():+.1f} (n {(~inw).sum()})")
mm = isf[isf.variant == "base"]
print("IS trail moves per trade (engine, every M1): median/p90",
      np.percentile(simulate2(m1, base_o, no_overlap=True, arrays=arrays).pipe(is_part).nmod, [50, 90]))
