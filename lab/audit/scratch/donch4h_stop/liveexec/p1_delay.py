"""P1: manual execution.  The trader receives the alert when the stop order would have filled and
enters AT MARKET N minutes later (open of the first M1 bar starting >= fill-bar start + N min).

Models
  A  ('re-anchored', the brief): same signals as the EA's fictive position (baseline trade list);
     stop = late fill -/+ 2 x ATR, trail 2 x ATR from the best price since the late fill, same
     time stop.  Each trade independent (alert stream follows the EA's fictive position).
       A1 always enter;  A2 skip if the theoretical trade has already exited at T+N
  B  ('EA mode 1 manages the manual position'): the EA puts the fictive position's stop on the
     real position -> identical exit (time & price) to the theoretical trade; only the entry
     is late.  R measured in units of the PLANNED risk (2 x ATR, lot sized from the alert).
     Only trades still open at T+N.
  C  ('human is flat-gated'): brackets armed only when the REAL (late) position is flat at the
     4 h close (sequential), late market entry, re-anchored stop -> different signal subset.
"""
import sys
sys.path.insert(0, "/home/user/gold-orb/lab/audit/scratch/donch4h_stop/liveexec")
import numpy as np
import pandas as pd
from common import HERE, S, PARAMS, fmt, gl, is_part, simulate2, stats, val_part, trading_day, COSTS

m1 = gl.load_m1("xauusd")
o = pd.read_pickle(f"{HERE}/orders_base.pkl")
t = pd.read_pickle(f"{HERE}/trades_base.pkl")
idx = m1.index
arrays = tuple(m1[k].to_numpy(np.float64) for k in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"))
bo, ao = arrays[0], arrays[4]
slip = COSTS["xauusd"].slip_bps * 1e-4
fi = np.searchsorted(idx.values, t.entry_time.values)          # fill bar of the theoretical trade
xi = np.searchsorted(idx.values, (t.exit_time - pd.Timedelta(minutes=1) * (t.reason != "time")).values)
od = o.loc[t.index]
frames = []
summ = []
for N in (0, 1, 5, 15, 60, 240):
    if N == 0:
        b = t.copy(); b["model"] = "base"; b["N"] = 0; frames.append(b); continue
    e = gl.entry_index(m1, idx[fi] + pd.Timedelta(minutes=N))
    alive = (t.exit_time.values > idx[np.clip(e, 0, len(idx) - 1)].values) & (e < len(idx))
    late = pd.DataFrame({"entry_i": e, "side": t.side.to_numpy(), "etype": 0,
                         "stop_dist": od.stop_dist.to_numpy(), "trail": od.trail.to_numpy(),
                         "exit_i": od.exit_i.to_numpy(), "alive": alive, "orig": t.index.to_numpy(),
                         "theoR": t.R.to_numpy()}, index=t.index)
    late = late[(late.entry_i < late.exit_i) & (late.entry_i < len(idx))]
    ta = simulate2(m1, late, no_overlap=False, trail_mode=0, arrays=arrays)
    a1 = ta.copy(); a1["model"] = "A1"; a1["N"] = N
    a2 = ta[ta.alive.astype(bool)].copy(); a2["model"] = "A2"; a2["N"] = N
    frames += [a1, a2]
    # model B: same exit as theoretical trade, late entry, R in planned-risk units
    bt = t[alive].copy()
    ee = e[alive]
    s = bt.side.to_numpy()
    ent = np.where(s > 0, ao[ee] * (1 + slip), bo[ee] * (1 - slip))
    d0 = trading_day(idx[ee]).values.astype("datetime64[D]")
    d1 = trading_day(bt.exit_time - pd.Timedelta(seconds=1)).values.astype("datetime64[D]")
    nights = np.busday_count(d0, d1) + 2 * np.busday_count(d0, d1, weekmask="Wed")
    rate = np.where(s > 0, COSTS["xauusd"].swap_long, COSTS["xauusd"].swap_short)
    pnl = s * (bt.exit.to_numpy() - ent) - ent * rate / 360 * nights - COSTS["xauusd"].commission
    bt["chaseR"] = s * (ent - bt.entry.to_numpy()) / od.loc[bt.index, "stop_dist"].to_numpy()
    bt["R"] = pnl / od.loc[bt.index, "stop_dist"].to_numpy()
    bt["model"] = "B"; bt["N"] = N
    frames.append(bt)
    # model C: flat-gated sequential on ALL armed+touched brackets
    oc = o.copy()
    ec = gl.entry_index(m1, idx[oc.trig_i.to_numpy()] + pd.Timedelta(minutes=N))
    cc = pd.DataFrame({"arm_i": oc.entry_i.to_numpy(), "entry_i": ec, "side": oc.side.to_numpy(), "etype": 0,
                       "stop_dist": oc.stop_dist.to_numpy(), "trail": oc.trail.to_numpy(),
                       "exit_i": oc.exit_i.to_numpy()})
    cc = cc[(cc.entry_i < cc.exit_i) & (cc.entry_i < len(idx))]
    tc = simulate2(m1, cc, no_overlap=True, trail_mode=0, arrays=arrays)
    tc["model"] = "C"; tc["N"] = N
    frames.append(tc)
allf = pd.concat(frames, ignore_index=True, sort=False)
isf = is_part(allf)
valf = val_part(allf, "manual-delay-N(1,5,15,60,240)-models-A1A2BC")
rows = []
for (mdl, N), g in allf.groupby(["model", "N"], sort=False):
    gi = isf[(isf.model == mdl) & (isf.N == N)]
    gv = valf[(valf.model == mdl) & (valf.N == N)]
    si, sv = stats(gi), stats(gv)
    extra = ""
    if mdl == "B":
        extra = f" chaseR_mean IS {gi.chaseR.mean():+.3f} VAL {gv.chaseR.mean():+.3f}"
    print(f"{mdl:4s} N={N:3d} | IS {fmt(si)}\n{'':11s}| VAL {fmt(sv)}{extra}")
    rows.append({"model": mdl, "N": N, **{f"is_{k}": v for k, v in si.items()}, **{f"val_{k}": v for k, v in sv.items()}})
pd.DataFrame(rows).to_csv(f"{HERE}/p1_delay.csv", index=False)
# how many theoretical trades are already closed at T+N (IS only)
for N in (1, 5, 15, 60, 240):
    e = gl.entry_index(m1, idx[fi] + pd.Timedelta(minutes=N))
    alive = (t.exit_time.values > idx[np.clip(e, 0, len(idx) - 1)].values)
    m = (t.entry_time < pd.Timestamp("2022-01-01", tz="UTC")).to_numpy()
    dead = ~alive & m
    print(f"N={N:3d}: IS theoretical trades already closed at T+N: {dead.sum()} of {m.sum()}, their theo R sum {t.R[dead].sum():+.1f}")
