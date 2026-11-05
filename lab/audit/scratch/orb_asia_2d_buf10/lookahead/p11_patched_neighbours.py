"""P11: the finalist was selected and its IS criteria computed on the UNPATCHED data.  Re-evaluate the
finalist, its declared neighbours and the x1.5 stress on the current (patched) data, IS only (nothing logged to
results/orb).  Also a 'consistent' stress: orders REBUILT on x1.5-spread quotes (range, levels, first touch see
the wider spread) instead of reusing the normal-quote orders."""
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'audit/scratch/orb_asia_2d_buf10/lookahead')
from common import *
from goldlab.evalkit import stressed_costs
from dataclasses import replace
res = {}
for nm, unp in (("patched", False), ("unpatched", True)):
    m1 = load(unpatched=unp)
    NB = {"F3": {}, "buf0.00": {"buf_frac": 0.0}, "buf0.08": {"buf_frac": 0.08}, "buf0.12": {"buf_frac": 0.12}, "buf0.20": {"buf_frac": 0.2},
          "hold1": {"hold_days": 1}, "hold3": {"hold_days": 3}, "re06": {"range_end": "06:00"}, "re08": {"range_end": "08:00"},
          "rs23": {"range_start": "-01:00"}, "rs01": {"range_start": "01:00"}, "ee11": {"entry_end": "11:00"}, "ee13": {"entry_end": "13:00"},
          "x14": {"exit_time": "14:00"}, "x18": {"exit_time": "18:00"}, "stopmid": {"stop_mode": "mid"}}
    rows = {}
    for k, ch in NB.items():
        o = S.make_orders(m1, **{**P, **ch})
        o = o[pd.to_datetime(o.date) < '2022-01-01'].reset_index(drop=True)
        t = is_part(gl.simulate(m1, o)); ts = is_part(gl.simulate(m1, o, costs=stressed_costs()))
        rows[k] = {**summ(t), "stressPF": round(pf(ts.R), 3)}
    df = pd.DataFrame(rows).T
    nbpf = df.drop('F3').pf.astype(float)
    print(f"== {nm}\n", df.to_string(), f"\nmedian neighbour PF {nbpf.median():.3f}", flush=True)
    # consistent stress: rebuild orders on x1.5-spread quotes
    spr = (m1.ac - m1.bc).to_numpy(); half = spr * 0.25
    m2 = m1.copy()
    for c in ('bo', 'bh', 'bl', 'bc'): m2[c] = m2[c].to_numpy() - half
    for c in ('ao', 'ah', 'al', 'ac'): m2[c] = m2[c].to_numpy() + half
    o2 = S.make_orders(m2, **P); o2 = o2[pd.to_datetime(o2.date) < '2022-01-01'].reset_index(drop=True)
    c2 = replace(stressed_costs(), spread_mult=1.0)
    t2 = is_part(gl.simulate(m2, o2, costs=c2))
    print(f"   consistent stress (orders rebuilt on x1.5 quotes): {summ(t2)}", flush=True)
    del m1, m2
