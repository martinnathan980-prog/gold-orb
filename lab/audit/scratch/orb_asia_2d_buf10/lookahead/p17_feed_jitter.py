"""P17: execution/feed-noise band.  A live feed differs from Dukascopy by cents.  Add iid per-minute noise
(same shift to all 8 OHLC fields of a bar, sd $0.03 / $0.10) -> rebuild orders -> simulate; distribution of
IS PF over seeds.  If the band is as wide as the 1.177-vs-1.20 gap, the PASS/CONDITIONAL/FAIL call at the
threshold is decided by noise, not by the strategy.  IS only."""
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'audit/scratch/orb_asia_2d_buf10/lookahead')
from common import *
m1 = load(); N = len(m1)
cols = ('bo', 'bh', 'bl', 'bc', 'ao', 'ah', 'al', 'ac')
base = {c: m1[c].to_numpy().copy() for c in cols}
out = []
for sd in (0.03, 0.10):
    for seed in range(12):
        rng = np.random.default_rng(1000 + seed)
        z = rng.normal(0, sd, N)
        m2 = pd.DataFrame({c: base[c] + z for c in cols}, index=m1.index)
        o = S.make_orders(m2, **P); o = o[pd.to_datetime(o.date) < '2022-01-01'].reset_index(drop=True)
        t = is_part(gl.simulate(m2, o))
        s_ = summ(t); out.append({"sd": sd, "seed": seed, **s_}); print(out[-1], flush=True)
        del m2
df = pd.DataFrame(out)
df.to_csv('audit/scratch/orb_asia_2d_buf10/lookahead/p17_feed_jitter.csv', index=False)
for sd, g in df.groupby('sd'):
    print(f"sd ${sd}: PF min {g.pf.min():.3f} median {g.pf.median():.3f} max {g.pf.max():.3f} | t min {g.t.min():.2f} max {g.t.max():.2f} | "
          f"n {g.n.min()}-{g.n.max()} | share PF>=1.20 & t>=2: {((g.pf >= 1.2) & (g.t >= 2)).mean():.2f}")
