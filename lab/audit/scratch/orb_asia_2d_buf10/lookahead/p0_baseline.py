"""P0: reproduce the finalist on current (patched) and unpatched data; IS only (no VAL access here)."""
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'audit/scratch/orb_asia_2d_buf10/lookahead')
from common import *

for nm, unp in (("patched(current)", False), ("unpatched", True)):
    with Timer("load " + nm):
        m1 = load(unpatched=unp)
    print(nm, "rows", len(m1), "index dtype", m1.index.dtype, m1.index[0], m1.index[-1])
    with Timer("make_orders"):
        o = S.make_orders(m1, **P)
    with Timer("simulate"):
        t = gl.simulate(m1, o, no_overlap=True)
    # research-harness style: orders cut to IS dates before simulating
    oi = o[pd.to_datetime(o.date) < pd.Timestamp("2022-01-01")].reset_index(drop=True)
    ti = gl.simulate(m1, oi, no_overlap=True)
    print(nm, "orders", len(o), "IS (full-sim cut):", summ(is_part(t)))
    print(nm, "IS (harness: orders cut first):", summ(is_part(ti)))
    rep = gl.report(is_part(t)); print("   by_year", rep["by_year_R"], rep["exit_reasons"], "max_hold_h", rep["max_hold_h"])
    if not unp:
        o.to_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/orders_base.pkl')
        t.to_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/trades_base_full.pkl')  # full frame kept on disk only
    else:
        o.to_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/orders_unpatched.pkl')
        t.to_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/trades_unpatched_full.pkl')
    del m1
