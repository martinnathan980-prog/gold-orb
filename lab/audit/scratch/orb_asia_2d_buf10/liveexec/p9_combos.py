"""P9: (a) cost margin of the CONDITIONAL status: IS/VAL PF and t when the all-in round-trip cost is
lower/higher than the pre-registered model by x $/oz (post-hoc on the baseline path; the path itself is
unchanged, so this is first-order only).
(b) combined live scenarios (20 feed-noise seeds each, sigma 0.5 bp on H and L independently):
  A  EA, native pending orders, retail swap 8%/2%, rollover spread x2 (16-17 & 18-19 NY), +$0.10/oz
  B  A + manual market entry 5 min after the touch (same absolute stop, signal dropped if beyond it)
  C  A + manual entry 15 min after (same distance convention)
  D  A + salaried trader: 08-09 & 12-13 Paris signals at touch+1 min, 09-12 signals at 12:00 Paris,
       time exit moved to next business day 08:00 Paris
"""
import gc
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa: F401,F403

m1 = gl.load_m1("xauusd")
t = pd.read_pickle(os.path.join(HERE, "trades_base.pkl"))
idx = m1.index
# (a) cost margin
fr = []
for x in (-0.30, -0.20, -0.15, -0.10, -0.05, 0.0, 0.10, 0.25, 0.50, 0.75):
    tt = t.copy()
    tt["R"] = (tt.pnl - x) / tt.risk
    fr.append(tt.assign(variant=f"cost{x:+.2f}"))
# (b) combos
s, p = finalist_sessions(m1)
H, L = s.hi.to_numpy(), s.lo.to_numpy()
px = 0.5 * (H + L)
ny = idx.tz_convert(gl.NY)
mm = np.asarray(ny.hour * 60 + ny.minute)
W2 = ((mm >= 960) & (mm < 1020)) | ((mm >= 1080) & (mm < 1140))
h = np.where(W2, (m1.ac - m1.bc).to_numpy() * 0.5, 0.0)
mr = m1.copy()
for c in ("bo", "bh", "bl", "bc"):
    mr[c] = mr[c].to_numpy() - h
for c in ("ao", "ah", "al", "ac"):
    mr[c] = mr[c].to_numpy() + h
del h
gc.collect()
ao, bo = m1.ao.to_numpy(), m1.bo.to_numpy()
retail = Costs(swap_long=0.08, swap_short=0.02)
EXTRA = 0.10


def delayed(o, N, conv):
    fi = o.entry_i.to_numpy()
    ei = np.minimum(gl.entry_index(m1, idx[fi] + pd.Timedelta(minutes=N)), len(m1) - 1)
    oo = pd.DataFrame({"entry_i": ei, "side": o.side.to_numpy(), "etype": 0, "exit_i": o.exit_i.to_numpy(),
                       "date": o.date.to_numpy()})
    if conv == "dist":
        oo["stop"], oo["stop_dist"] = np.nan, (o.level - o.stop).abs().to_numpy()
    else:
        oo["stop"] = o.stop.to_numpy()
        q = np.where(oo.side > 0, bo[ei], ao[ei])
        oo = oo[~np.where(oo.side > 0, q <= oo.stop, q >= oo.stop)]
    return oo[oo.exit_i > oo.entry_i]


def salaried(o):
    fi = o.entry_i.to_numpy()
    tp = idx[fi].tz_convert(PARIS)
    hp = np.asarray(tp.hour + tp.minute / 60)
    a = ((hp >= 8) & (hp < 9)) | ((hp >= 12) & (hp < 13))
    b = (hp >= 9) & (hp < 12)
    ei1 = np.minimum(gl.entry_index(m1, idx[fi] + pd.Timedelta(minutes=1)), len(m1) - 1)
    noon = S._local_times(pd.DatetimeIndex(tp.tz_localize(None).normalize()), "12:00", PARIS)
    ei12 = np.minimum(gl.entry_index(m1, noon), len(m1) - 1)
    xd = pd.DatetimeIndex(o.date) + pd.offsets.BDay(int(PARAMS["hold_days"]) + 1)
    x08 = gl.entry_index(m1, S._local_times(xd, "08:00", PARIS))
    ei = np.where(a, ei1, ei12)
    sel = a | b
    oo = pd.DataFrame({"entry_i": ei[sel], "side": o.side.to_numpy()[sel], "etype": 0, "stop": np.nan,
                       "stop_dist": (o.level - o.stop).abs().to_numpy()[sel], "exit_i": x08[sel],
                       "date": o.date.to_numpy()[sel]}).sort_values("entry_i")
    return oo[oo.exit_i > oo.entry_i]


rng = np.random.default_rng(11)
for seed in range(21):
    if seed == 0:
        e1 = e2 = 0.0
    else:
        e1, e2 = rng.normal(0, 0.5e-4, len(s)) * px, rng.normal(0, 0.5e-4, len(s)) * px
    hh, ll = H + e1, L + e2
    w = hh - ll
    o = orders_from_levels(m1, s, hh + 0.1 * w, ll - 0.1 * w)
    for combo, oo in (("A_EA", o), ("B_manual5_abs", delayed(o, 5, "abs")), ("C_manual15_dist", delayed(o, 15, "dist")),
                      ("D_salaried", salaried(o))):
        tt = gl.simulate(mr, oo, no_overlap=True)
        tt = post_costs(tt, retail)
        tt["R"] = (tt.pnl - EXTRA) / tt.risk
        fr.append(tt.assign(variant=f"{combo}_s{seed}"))
allt = pd.concat(fr)
ti = is_part(allt)
tv = val_part(allt, "cost margin -0.30..+0.75 $/oz and combined live scenarios A-D x 21 feed seeds")
rows = []
for k in allt.variant.unique():
    a, b = stats(ti[ti.variant == k]), stats(tv[tv.variant == k])
    rows.append({"variant": k, "IS_n": a["n"], "IS_pf": a["pf"], "IS_t": a["t"], "IS_yrs": a["yrs_pos"],
                 "VAL_n": b["n"], "VAL_pf": b["pf"], "VAL_t": b["t"]})
r = pd.DataFrame(rows)
r.to_csv(os.path.join(HERE, "p9_combos.csv"), index=False)
pd.set_option("display.width", 250)
print(r[r.variant.str.startswith("cost")].to_string(index=False))
for combo in ("A_EA", "B_manual5_abs", "C_manual15_dist", "D_salaried"):
    q = r[r.variant.str.startswith(combo)]
    q0 = q[q.variant == f"{combo}_s0"].iloc[0]
    qn = q[q.variant != f"{combo}_s0"]
    print(f"{combo}: no-noise IS {q0.IS_pf} (t {q0.IS_t}) VAL {q0.VAL_pf} (t {q0.VAL_t}) | 20 noise seeds: IS PF p5/p50/p95 "
          f"{np.percentile(qn.IS_pf, 5):.3f}/{np.median(qn.IS_pf):.3f}/{np.percentile(qn.IS_pf, 95):.3f}  VAL PF "
          f"{np.percentile(qn.VAL_pf, 5):.3f}/{np.median(qn.VAL_pf):.3f}/{np.percentile(qn.VAL_pf, 95):.3f}  "
          f"share VAL>=1.10 {np.mean(qn.VAL_pf >= 1.10):.2f}  share VAL>1.0 {np.mean(qn.VAL_pf > 1.0):.2f}")
