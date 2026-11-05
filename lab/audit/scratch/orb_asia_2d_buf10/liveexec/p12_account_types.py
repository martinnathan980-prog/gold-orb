"""P12: account type matters more than any execution detail: baseline + EA/manual variants under the three
Amendment-1 scenarios (scenario-consistent: quotes spread-scaled before make_orders)."""
import gc, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa
SCN = json.load(open(os.path.join(LAB, "audit", "cost_scenarios.json")))
m0 = gl.load_m1("xauusd")
def scale(m, k):
    if k == 1.0:
        return m
    h = (m["ac"] - m["bc"]).to_numpy() * (k - 1) / 2
    out = m.copy()
    for c in ("bo", "bh", "bl", "bc"): out[c] = m[c].to_numpy() - h
    for c in ("ao", "ah", "al", "ac"): out[c] = m[c].to_numpy() + h
    return out
frames = []
for name, c in SCN.items():
    m1 = scale(m0, c["spread_mult"])
    cc = Costs(commission=c["commission"], slip_bps=c["slip_bps"], swap_long=c["swap_long"], swap_short=c["swap_short"])
    o = S.make_orders(m1, **PARAMS).reset_index(drop=True)
    frames.append(gl.simulate(m1, o, costs=cc).assign(variant=f"{name}_EA"))
    fi = o.entry_i.to_numpy()
    for N in (5, 60):
        ei = np.minimum(gl.entry_index(m1, m1.index[fi] + pd.Timedelta(minutes=N)), len(m1) - 1)
        oo = pd.DataFrame({"entry_i": ei, "side": o.side, "etype": 0, "stop": o.stop.to_numpy(), "exit_i": o.exit_i, "date": o.date})
        q = np.where(oo.side > 0, m1.bo.to_numpy()[ei], m1.ao.to_numpy()[ei])
        oo = oo[~np.where(oo.side > 0, q <= oo.stop, q >= oo.stop)]
        frames.append(gl.simulate(m1, oo, costs=cc).assign(variant=f"{name}_manual{N}_abs"))
    tp = m1.index[fi].tz_convert(PARIS); hp = np.asarray(tp.hour + tp.minute / 60)
    frames.append(gl.simulate(m1, o[(hp >= 8) & (hp < 9)], costs=cc).assign(variant=f"{name}_prework_only"))
    if m1 is not m0:
        del m1
    gc.collect()
allt = pd.concat(frames)
ti, tv = is_part(allt), val_part(allt, "account types (3 Amendment-1 scenarios) x EA / manual 5,60 min / pre-work only")
for k in allt.variant.unique():
    a, b = stats(ti[ti.variant == k]), stats(tv[tv.variant == k])
    print(f"{k:32s} IS n {a['n']} PF {a['pf']} t {a['t']} yrs {a['yrs_pos']} | VAL n {b['n']} PF {b['pf']} t {b['t']}")
