"""P7: broker feed / range-definition realism (the EA will not see Dukascopy's quotes).
  F1 range on BID bars (MT5 M1 bars are Bid): H = max Bid high, L = min Bid low
  F2 F1 + spread at 07:00 London added to H (EA approximation of the Ask high)
  F3 broker Asian-session spread x2 while the range forms (H = max Ask, L = min Bid on wider quotes)
  F4 systematic level shifts: H+d, L-d (d>0 wider) for d in bps of price
  F5 random per-session feed noise on H and L, sigma in bps of price, 40 seeds each
Trading quotes (fills, stops, exits) stay Dukascopy's.
"""
import gc
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa: F401,F403

m1 = gl.load_m1("xauusd")
t = pd.read_pickle(os.path.join(HERE, "trades_base.pkl"))
s, p = finalist_sessions(m1)
i0, i1 = s.i0.to_numpy(np.int64), s.i1.to_numpy(np.int64)
H, L = s.hi.to_numpy(), s.lo.to_numpy()
px = 0.5 * (H + L)


def lv(h, l):
    w = h - l
    return h + 0.1 * w, l - 0.1 * w


def run(h, l, tag):
    b, se = lv(h, l)
    o = orders_from_levels(m1, s, b, se)
    tt = gl.simulate(m1, o, no_overlap=True)
    tt["variant"] = tag
    return tt


frames = [t.assign(variant="baseline")]
bh, bl_ = m1.bh.to_numpy(np.float64), m1.bl.to_numpy(np.float64)
ac, bc = m1.ac.to_numpy(np.float64), m1.bc.to_numpy(np.float64)
hb, lb, _ = S._range_stats(bh, bl_, ac, bc, i0, i1)
frames.append(run(hb, lb, "F1_bid_bars_range"))
spr07 = (m1.ao - m1.bo).to_numpy()[i1]
frames.append(run(hb + spr07, lb, "F2_bid_high+spread07"))
# F3: spread x2 during the range window only
ldn = m1.index.tz_convert(gl.LDN)
inrange = np.asarray(ldn.hour < 7)
spr = (m1.ac - m1.bc).to_numpy()
h2 = np.where(inrange, spr * 0.5, 0.0)
ah2 = m1.ah.to_numpy() + h2
bl2 = m1.bl.to_numpy() - h2
H3, L3, _ = S._range_stats(ah2, bl2, ac, bc, i0, i1)
del ah2, bl2, h2
gc.collect()
frames.append(run(H3, L3, "F3_asian_spread_x2"))
print("F3: mean H shift $", round(float(np.mean(H3 - H)), 3), "mean L shift $", round(float(np.mean(L - L3)), 3),
      "| F1: mean H shift $", round(float(np.mean(H - hb)), 3))
for d in (-1.0, -0.5, 0.5, 1.0):
    dd = d * 1e-4 * px
    frames.append(run(H + dd, L - dd, f"F4_shift_{d:+.1f}bp"))
rng = np.random.default_rng(7)
for sig in (0.25, 0.5, 1.0):
    for k in range(40):
        e1, e2 = rng.normal(0, sig * 1e-4, len(s)) * px, rng.normal(0, sig * 1e-4, len(s)) * px
        frames.append(run(H + e1, L + e2, f"F5_noise_{sig}bp_s{k}"))
allt = pd.concat(frames)
ti = is_part(allt)
tv = val_part(allt, "feed realism: bid-bar range, Asian spread x2, level shifts, random feed noise (40 seeds x 3 sigma)")
rows = []
for k in allt.variant.unique():
    a, b = stats(ti[ti.variant == k]), stats(tv[tv.variant == k])
    rows.append({"variant": k, "IS_n": a["n"], "IS_pf": a["pf"], "IS_t": a["t"], "VAL_n": b["n"], "VAL_pf": b["pf"], "VAL_t": b["t"]})
r = pd.DataFrame(rows)
r.to_csv(os.path.join(HERE, "p7_feed.csv"), index=False)
pd.set_option("display.width", 250)
print(r[~r.variant.str.startswith("F5")].to_string(index=False))
for sig in (0.25, 0.5, 1.0):
    q = r[r.variant.str.startswith(f"F5_noise_{sig}bp")]
    f = lambda x: f"p5 {np.percentile(x, 5):.3f} p50 {np.median(x):.3f} p95 {np.percentile(x, 95):.3f} min {x.min():.3f} max {x.max():.3f}"
    print(f"F5 sigma {sig} bp (~${sig * 1e-4 * 1300:.2f} at $1300, ${sig * 1e-4 * 3400:.2f} at $3400): IS PF {f(q.IS_pf)} | "
          f"share IS>=1.20 {np.mean(q.IS_pf >= 1.2):.2f} | VAL PF {f(q.VAL_pf)} | share VAL>=1.10 {np.mean(q.VAL_pf >= 1.1):.2f}")
