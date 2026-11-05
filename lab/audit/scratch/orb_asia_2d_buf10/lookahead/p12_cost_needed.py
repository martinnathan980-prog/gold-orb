"""P12: on the patched data, how much cheaper than the primary model must the broker be for the finalist to clear
IS PF>=1.20 and t>=2.0 (the CONDITIONAL premise)?  Engine convention (orders on normal quotes).  IS only."""
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'audit/scratch/orb_asia_2d_buf10/lookahead')
from common import *
from goldlab.sim import Costs
m1 = load()
o = pd.read_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/orders_base.pkl')
o = o[pd.to_datetime(o.date) < '2022-01-01'].reset_index(drop=True)
rows = []
for comm in (0.07, 0.035, 0.0):
    for slip in (1.5, 1.0, 0.5, 0.0):
        for sm in (1.0, 0.8, 0.6):
            t = is_part(gl.simulate(m1, o, costs=Costs(commission=comm, slip_bps=slip, spread_mult=sm)))
            s_ = summ(t)
            rows.append({"comm": comm, "slip_bp": slip, "spread_x": sm, "pf": s_["pf"], "t": s_["t"], "yrs+": s_["yrs+"],
                         "pass_pf_t": bool(s_["pf"] >= 1.2 and s_["t"] >= 2.0)})
df = pd.DataFrame(rows); print(df.to_string())
