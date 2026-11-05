"""P13: Costs(spread_mult) is applied INSIDE simulate() to quotes that differ from the quotes make_orders() used to
pre-resolve the OCO first touch (entry_i = expiry_i = touch bar).  With spread_mult < 1 the touch bar's Ask may no
longer reach the buy level (Bid the sell level) -> the order silently NOFILLs and the day is lost; with
spread_mult > 1 fills are forced on the old touch bar.  Compare engine convention vs a consistent rebuild
(orders rebuilt on the modified quotes, simulate with spread_mult=1).  IS only."""
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'audit/scratch/orb_asia_2d_buf10/lookahead')
from common import *
from goldlab.sim import Costs
m1 = load()
spr = (m1.ac - m1.bc).to_numpy()
o = pd.read_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/orders_base.pkl')
o = o[pd.to_datetime(o.date) < '2022-01-01'].reset_index(drop=True)
rows = []
for sm in (0.5, 0.6, 0.8, 1.0, 1.5, 2.0):
    for slip in (1.5, 0.5):
        c = Costs(slip_bps=slip, spread_mult=sm)
        te = gl.simulate(m1, o, costs=c)
        nof = te.attrs['nofill']
        te = is_part(te)
        # consistent: rebuild on modified quotes
        half = spr * (sm - 1) / 2
        m2 = m1.copy()
        for k in ('bo', 'bh', 'bl', 'bc'): m2[k] = m2[k].to_numpy() - half
        for k in ('ao', 'ah', 'al', 'ac'): m2[k] = m2[k].to_numpy() + half
        o2 = S.make_orders(m2, **P); o2 = o2[pd.to_datetime(o2.date) < '2022-01-01'].reset_index(drop=True)
        tc = gl.simulate(m2, o2, costs=Costs(slip_bps=slip, spread_mult=1.0))
        tc = is_part(tc)
        se, sc = summ(te), summ(tc)
        rows.append({"spread_x": sm, "slip_bp": slip, "engine_nofill": nof, "engine_n": se["n"], "engine_pf": se["pf"], "engine_t": se["t"],
                     "rebuilt_n": sc["n"], "rebuilt_pf": sc["pf"], "rebuilt_t": sc["t"], "rebuilt_yrs+": sc["yrs+"]})
        print(rows[-1], flush=True)
        del m2
pd.DataFrame(rows).to_csv('audit/scratch/orb_asia_2d_buf10/lookahead/p13_spreadmult_bug.csv', index=False)
print(pd.DataFrame(rows).to_string())
