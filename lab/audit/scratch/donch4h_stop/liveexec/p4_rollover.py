"""P4: wider spreads around the daily break (gold trades 18:00 -> 17:00 New York; Dukascopy data
have no bars 17:00-17:59 NY).  Bid/ask widened symmetrically around the mid (mid unchanged, so the
channel levels and ATR are unchanged; touches, fills and stops see the wider quotes).  Orders are
rebuilt on the widened frame.
  R1 x2   16:30-17:00 + 18:00-18:30 NY (1 h of trading time around the break)
  R2 x2   16:00-17:00 + 18:00-19:00 NY (2 h)
  R3 x3   2 h window
  R4 x5   16:50-17:00 + 18:00-18:20 NY, x2 on the rest of the 2 h window (typical retail reopen spike)
"""
import gc
import sys
sys.path.insert(0, "/home/user/gold-orb/lab/audit/scratch/donch4h_stop/liveexec")
import numpy as np
import pandas as pd
from common import HERE, S, PARAMS, fmt, gl, is_part, stats, val_part

m1 = gl.load_m1("xauusd")
ny = gl.local(m1.index, gl.NY)
hm = ny.hour.to_numpy() * 60 + ny.minute.to_numpy()
spr = (m1["ac"] - m1["bc"]).to_numpy()


def win(a, b):
    return (hm >= a) & (hm < b)


W1h = win(16 * 60 + 30, 17 * 60) | win(18 * 60, 18 * 60 + 30)
W2h = win(16 * 60, 17 * 60) | win(18 * 60, 19 * 60)
Wsp = win(16 * 60 + 50, 17 * 60) | win(18 * 60, 18 * 60 + 20)
SCEN = {"R1_x2_1h": np.where(W1h, 2.0, 1.0), "R2_x2_2h": np.where(W2h, 2.0, 1.0),
        "R3_x3_2h": np.where(W2h, 3.0, 1.0), "R4_x5spike_x2_2h": np.where(Wsp, 5.0, np.where(W2h, 2.0, 1.0))}
frames = []
o0 = pd.read_pickle(f"{HERE}/orders_base.pkl")
t0 = pd.read_pickle(f"{HERE}/trades_base.pkl")
t0 = t0.copy(); t0["scen"] = "base"; frames.append(t0)
# exposure of the baseline (IS): trades whose fill or exit bar lies in the windows
fi = np.searchsorted(m1.index.values, t0.entry_time.values)
xi = np.searchsorted(m1.index.values, (t0.exit_time - pd.Timedelta(minutes=1) * (t0.reason != "time")).values)
xi = np.clip(xi, 0, len(m1) - 1)
isb = (t0.entry_time < pd.Timestamp("2022-01-01", tz="UTC")).to_numpy()
for nm, w in (("1h", W1h), ("2h", W2h)):
    print(f"IS trades with fill in the {nm} window: {int((w[fi] & isb).sum())}, exit in it: {int((w[xi] & isb).sum())} of {isb.sum()}")
for name, mult in SCEN.items():
    x = m1.copy()
    half = spr * (mult - 1) / 2
    for c in ("bo", "bh", "bl", "bc"):
        x[c] = x[c].to_numpy() - half
    for c in ("ao", "ah", "al", "ac"):
        x[c] = x[c].to_numpy() + half
    o = S.make_orders(x, **PARAMS)
    t = gl.simulate(x, o, no_overlap=True)
    t["scen"] = name
    frames.append(t)
    print(name, "orders", len(o), "trades", len(t), "(base orders", len(o0), ")", flush=True)
    del x, o
    S._bar_cache.clear()
    gc.collect()
allf = pd.concat(frames, ignore_index=True)
isf = is_part(allf)
valf = val_part(allf, "rollover-spread-x2-x3-x5")
rows = []
for s in allf.scen.unique():
    si, sv = stats(isf[isf.scen == s]), stats(valf[valf.scen == s])
    print(f"{s:18s} | IS {fmt(si)}\n{'':18s} | VAL {fmt(sv)}")
    rows.append({"scen": s, **{f"is_{k}": v for k, v in si.items()}, **{f"val_{k}": v for k, v in sv.items()}})
pd.DataFrame(rows).to_csv(f"{HERE}/p4_rollover.csv", index=False)
