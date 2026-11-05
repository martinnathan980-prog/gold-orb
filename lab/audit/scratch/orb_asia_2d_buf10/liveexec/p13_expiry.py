"""P13: pending-order expiry misuse.  ORDER_TIME_DAY expires at the server day end (00:00 server = 17:00 NY),
not at 12:00 London -> entry window silently extended to ~16:59 NY.  Primary model and low_cost_ecn."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa
m0 = gl.load_m1("xauusd")
c = json.load(open(os.path.join(LAB, "audit", "cost_scenarios.json")))["low_cost_ecn"]
h = (m0["ac"] - m0["bc"]).to_numpy() * (c["spread_mult"] - 1) / 2
mlc = m0.copy()
for k in ("bo", "bh", "bl", "bc"): mlc[k] = m0[k].to_numpy() - h
for k in ("ao", "ah", "al", "ac"): mlc[k] = m0[k].to_numpy() + h
LC = Costs(commission=c["commission"], slip_bps=c["slip_bps"], swap_long=c["swap_long"], swap_short=c["swap_short"])
fr = []
for nm, m, cc in (("primary", m0, None), ("low_cost_ecn", mlc, LC)):
    for ee in ("12:00", "13:00", "16:00", "22:00"):
        o = S.make_orders(m, **{**PARAMS, "entry_end": ee})
        tt = gl.simulate(m, o, costs=cc)
        tl = tt.entry_time.dt.tz_convert(gl.LDN)
        fr.append(tt.assign(variant=f"{nm}_entry_end_{ee}LDN", late=(tl.dt.hour >= 12).to_numpy()))
allt = pd.concat(fr)
ti, tv = is_part(allt), val_part(allt, "pending expiry misuse: entry_end 12/13/16/22 London (ORDER_TIME_DAY), primary & low_cost")
for k in allt.variant.unique():
    a, b = stats(ti[ti.variant == k]), stats(tv[tv.variant == k])
    print(f"{k:34s} IS n {a['n']} PF {a['pf']} t {a['t']} | VAL n {b['n']} PF {b['pf']} t {b['t']} | fills after 12:00 LDN: {int(allt[allt.variant == k].late.sum())}")
