"""P4b: decompose the retail-style rollover spike (x5 spread) effect: pre-close only / reopen only,
entries vs exits (custom sim with separate quote arrays for the entry scan and for the exit path),
and a 'rollover guard' diagnostic (no pending orders and no stop checks on spiked quotes) - IS + VAL.
"""
import gc
import sys
sys.path.insert(0, "/home/user/gold-orb/lab/audit/scratch/donch4h_stop/liveexec")
import numba as nb
import numpy as np
import pandas as pd
from common import COSTS, HERE, S, PARAMS, fmt, gl, is_part, simulate2, stats, val_part

m1 = gl.load_m1("xauusd")
ny = gl.local(m1.index, gl.NY)
hm = ny.hour.to_numpy() * 60 + ny.minute.to_numpy()
spr = (m1["ac"] - m1["bc"]).to_numpy()
win = lambda a, b: (hm >= a) & (hm < b)
PRE = win(16 * 60 + 50, 17 * 60)
REO = win(18 * 60, 18 * 60 + 20)
@nb.njit(cache=True)
def _exit_path(bo, bh, bl, ao, ah, al, fi, fp, side, st, trail, xe, slip, x_i, x_px, moved_out):
    N = len(bo)
    for k in range(len(fi)):
        s = side[k]; cur = st[k]; best = fp[k]; moved = False; i = fi[k]; done = False
        while i < N:
            if xe[k] >= 0 and i >= xe[k] and i > fi[k]:
                x_i[k] = i; x_px[k] = bo[i] * (1 - slip) if s > 0 else ao[i] * (1 + slip); moved_out[k] = 2; done = True; break
            first = i == fi[k]
            if s > 0:
                if bl[i] <= cur:
                    px = cur if first else min(cur, bo[i]); x_i[k] = i; x_px[k] = px * (1 - slip); moved_out[k] = 1 if moved else 0; done = True; break
                if bh[i] > best: best = bh[i]
                if best - trail[k] > cur: cur = best - trail[k]; moved = True
            else:
                if ah[i] >= cur:
                    px = cur if first else max(cur, ao[i]); x_i[k] = i; x_px[k] = px * (1 + slip); moved_out[k] = 1 if moved else 0; done = True; break
                if al[i] < best: best = al[i]
                if best + trail[k] < cur: cur = best + trail[k]; moved = True
            i += 1
        if not done:
            x_i[k] = N - 1; x_px[k] = bo[N - 1]


def exit_only(tb, arr):
    bo, bh, bl, bc, ao, ah, al, ac = arr
    o = pd.read_pickle(f"{HERE}/orders_base.pkl").loc[tb.index]
    fi = np.searchsorted(m1.index.values, tb.entry_time.values).astype(np.int64)
    n = len(tb)
    x_i = np.full(n, -1, np.int64); x_px = np.full(n, np.nan); mv = np.zeros(n, np.int64)
    _exit_path(bo, bh, bl, ao, ah, al, fi, tb.entry.to_numpy(), tb.side.to_numpy().astype(np.int64), tb.stop.to_numpy(),
               o.trail.to_numpy(), o.exit_i.to_numpy().astype(np.int64), COSTS["xauusd"].slip_bps * 1e-4, x_i, x_px, mv)
    out = tb.copy()
    out["exit"] = x_px
    out["R"] = (out.side * (out.exit - out.entry) - out.swap - out.commission) / out.risk   # swap kept as base (approx.)
    return out


base_arr = tuple(m1[k].to_numpy(np.float64) for k in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"))


def widened(mult):
    half = spr * (mult - 1) / 2
    bo, bh, bl, bc, ao, ah, al, ac = base_arr
    return (bo - half, bh - half, bl - half, bc - half, ao + half, ah + half, al + half, ac + half)


frames = []
t0 = pd.read_pickle(f"{HERE}/trades_base.pkl").copy(); t0["scen"] = "base"; frames.append(t0)
for name, w in (("x5_preclose_only", PRE), ("x5_reopen_only", REO), ("x5_both", PRE | REO)):
    mult = np.where(w, 5.0, 1.0)
    arr = widened(mult)
    x = m1.copy()
    for c, a in zip(("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"), arr):
        x[c] = a
    o = S.make_orders(x, **PARAMS)
    t = simulate2(x, o, no_overlap=True, arrays=arr)       # entries + exits on spiked quotes
    t["scen"] = name; frames.append(t)
    # exits only: the SAME base trades (fill bar, fill price, initial stop), exit path on spiked quotes
    te = exit_only(t0, arr)
    te["scen"] = name + "|exits-only"; frames.append(te)
    del x, o
    S._bar_cache.clear(); gc.collect()
allf = pd.concat(frames, ignore_index=True, sort=False)
isf = is_part(allf)
valf = val_part(allf, "rollover-x5-spike-decomposition")
for s in allf.scen.unique():
    si, sv = stats(isf[isf.scen == s]), stats(valf[valf.scen == s])
    print(f"{s:34s} | IS {fmt(si)}\n{'':34s} | VAL {fmt(sv)}")
# fills / exits inside the spike windows (IS)
W = PRE | REO
for s in ("base", "x5_both", "x5_preclose_only|exits-only"):
    tb = isf[isf.scen == s]
    fi = np.clip(np.searchsorted(m1.index.values, tb.entry_time.values), 0, len(m1) - 1)
    xi = np.clip(np.searchsorted(m1.index.values, (tb.exit_time - pd.Timedelta(minutes=1)).values), 0, len(m1) - 1)
    print(f"IS {s:28s}: fills in spike windows n={W[fi].sum():3d} R={tb.R.to_numpy()[W[fi]].sum():+6.1f} | "
          f"exits in spike windows n={W[xi].sum():3d} R={tb.R.to_numpy()[W[xi]].sum():+6.1f}")
b0 = isf[isf.scen == "base"].sort_index(); e0 = isf[isf.scen == "x5_preclose_only|exits-only"].sort_index()
d = (e0.R.to_numpy() - b0.R.to_numpy())
print(f"IS exits-only pre-close x5: trades changed {int((np.abs(d) > 1e-9).sum())}, sum dR {d.sum():+.1f}, "
      f"mean dR of changed {d[np.abs(d) > 1e-9].mean():+.2f}")
