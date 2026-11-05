"""P1b: fine delay sweep N = 1..30, 45, 90, 120, 180 min (both stop conventions) to separate a
systematic decay from execution jitter (which trades flip / get skipped)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa: F401,F403

m1 = gl.load_m1("xauusd")
o = pd.read_pickle(os.path.join(HERE, "orders_base.pkl"))
idx = m1.index
ao, bo = m1.ao.to_numpy(), m1.bo.to_numpy()
fi = o.entry_i.to_numpy()
t_fill = idx[fi]
dist = (o.level - o.stop).abs().to_numpy()

frames = []
Ns = list(range(1, 31)) + [45, 90, 120, 180]
for N in Ns:
    ei = np.minimum(gl.entry_index(m1, t_fill + pd.Timedelta(minutes=N)), len(m1) - 1)
    for conv in ("dist", "abs"):
        oo = pd.DataFrame({"entry_i": ei, "side": o.side, "etype": 0, "exit_i": o.exit_i, "date": o.date})
        if conv == "dist":
            oo["stop"], oo["stop_dist"] = np.nan, dist
        else:
            oo["stop"] = o.stop.to_numpy()
            px = np.where(o.side > 0, bo[ei], ao[ei])
            oo = oo[~np.where(o.side > 0, px <= o.stop, px >= o.stop)]
        oo = oo[oo.exit_i > oo.entry_i]
        tt = gl.simulate(m1, oo, no_overlap=True)
        tt["N"], tt["conv"] = N, conv
        frames.append(tt)
allt = pd.concat(frames)
ti = is_part(allt)
tv = val_part(allt, "manual-delay fine sweep N=1..30,45,90,120,180 (dist/abs)")
rows = []
for (N, conv), a in ti.groupby(["N", "conv"]):
    b = tv[(tv.N == N) & (tv.conv == conv)]
    sa, sb = stats(a), stats(b)
    rows.append({"N": N, "conv": conv, "IS_n": sa["n"], "IS_pf": sa["pf"], "IS_t": sa["t"],
                 "VAL_n": sb["n"], "VAL_pf": sb["pf"], "VAL_t": sb["t"]})
r = pd.DataFrame(rows)
pv = r.pivot(index="N", columns="conv", values=["IS_pf", "VAL_pf"])
print(pv.to_string())
r.to_csv(os.path.join(HERE, "p1b_delay_sweep.csv"), index=False)
for conv in ("dist", "abs"):
    q = r[(r.conv == conv) & (r.N <= 15)]
    q2 = r[(r.conv == conv) & (r.N >= 16) & (r.N <= 30)]
    print(f"{conv}: N=1..15  IS pf min/med/max {q.IS_pf.min():.3f}/{q.IS_pf.median():.3f}/{q.IS_pf.max():.3f}"
          f"  VAL pf min/med/max {q.VAL_pf.min():.3f}/{q.VAL_pf.median():.3f}/{q.VAL_pf.max():.3f}"
          f"  | share IS>=1.20: {(q.IS_pf >= 1.2).mean():.2f}  share VAL>=1.10: {(q.VAL_pf >= 1.1).mean():.2f}")
    print(f"{conv}: N=16..30 IS pf min/med/max {q2.IS_pf.min():.3f}/{q2.IS_pf.median():.3f}/{q2.IS_pf.max():.3f}"
          f"  VAL pf min/med/max {q2.VAL_pf.min():.3f}/{q2.VAL_pf.median():.3f}/{q2.VAL_pf.max():.3f}")
