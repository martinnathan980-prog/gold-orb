"""P20: the CONDITIONAL status is decided by audit/cost_scenarios.json 'low_cost_ecn' (spread_mult 0.35), which
audit.py / holdout.py apply via Costs(**c) to orders PRE-BUILT on normal quotes.  For this strategy (OCO first
touch pre-resolved, entry_i = expiry_i = touch bar) that silently NOFILLs orders whose touch bar no longer reaches
the level once the Ask is lowered / Bid raised.  Compare engine convention vs a consistent rebuild (orders built
on the scenario quotes) for all three scenarios + the scenario stress (x1.5), IS and VAL (one logged cut)."""
import sys, json; sys.path.insert(0, '.'); sys.path.insert(0, 'audit/scratch/orb_asia_2d_buf10/lookahead')
from common import *
from goldlab.sim import Costs
from goldlab.evalkit import is_criteria, val_criteria
from dataclasses import replace
m1 = load()
spr = (m1.ac - m1.bc).to_numpy()
scen = json.load(open('audit/cost_scenarios.json'))
o_base = pd.read_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/orders_base.pkl')
def quotes(sm):
    half = spr * (sm - 1) / 2
    m2 = m1.copy()
    for k in ('bo', 'bh', 'bl', 'bc'): m2[k] = m2[k].to_numpy() - half
    for k in ('ao', 'ah', 'al', 'ac'): m2[k] = m2[k].to_numpy() + half
    return m2
frames = []
rows = []
for sname, c in scen.items():
    cc = Costs(**c)
    st = replace(cc, commission=cc.commission * 1.5, slip_bps=cc.slip_bps * 1.5, spread_mult=cc.spread_mult * 1.5)
    # engine convention (what audit.py / holdout.py do)
    te = gl.simulate(m1, o_base, costs=cc); tes = gl.simulate(m1, o_base, costs=st)
    # consistent: rebuild orders on the scenario quotes
    mq = quotes(cc.spread_mult); oq = S.make_orders(mq, **P)
    tc = gl.simulate(mq, oq, costs=replace(cc, spread_mult=1.0)); del mq
    mq2 = quotes(st.spread_mult); oq2 = S.make_orders(mq2, **P)
    tcs = gl.simulate(mq2, oq2, costs=replace(st, spread_mult=1.0)); del mq2
    for nm, t, ts_ in (("engine(pre-built orders)", te, tes), ("rebuilt on scenario quotes", tc, tcs)):
        ri, rsi = gl.report(is_part(t)), gl.report(is_part(ts_))
        crit = is_criteria(ri, rsi)
        rows.append({"scenario": sname, "method": nm, "nofill_orders": t.attrs['nofill'], "IS_n": ri['n'], "IS_pf": ri['pf'], "IS_t": ri['t_stat'],
                     "IS_yrs+": ri['years_pos'], "IS_stress_pf": rsi['pf'], "IS_pass": crit['pass'],
                     "IS_fail": [k for k, v in crit.items() if k != 'pass' and not v]})
        frames.append(t.assign(scenario=sname, method=nm))
        print(rows[-1], flush=True)
allv = pd.concat(frames)
v = gl.cut(allv, "val", track="review", label=vlabel("cost-scenarios engine-vs-rebuilt(low_cost_ecn,typical_retail,conservative)"))
for r in rows:
    g = v[(v.scenario == r['scenario']) & (v.method == r['method'])]
    rv = gl.report(g); r.update({"VAL_n": rv['n'], "VAL_pf": rv['pf'], "VAL_t": rv['t_stat'], "VAL_pass": val_criteria(rv)['pass']})
df = pd.DataFrame(rows)
pd.set_option('display.width', 250)
print(df.to_string())
df.to_csv('audit/scratch/orb_asia_2d_buf10/lookahead/p20_lowcost_ecn.csv', index=False)
