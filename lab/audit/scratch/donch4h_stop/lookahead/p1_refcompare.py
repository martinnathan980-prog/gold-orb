"""P1: independent EA re-implementation vs engine, trade by trade (IS; VAL through logged gl.cut)."""
import sys
import time

sys.path.insert(0, ".")
sys.path.insert(0, "tracks/trend")
sys.path.insert(0, "audit/scratch/donch4h_stop/lookahead")
import numpy as np
import pandas as pd

import goldlab as gl
import refimpl as RI
import strategy as S

t0 = time.time()
m1 = gl.load_m1("xauusd")
t, c = RI.load_raw()
assert len(t) == len(m1)
o = S.make_orders(m1, **S.FINALISTS["donch4h_stop"])
eng = gl.simulate(m1, o, no_overlap=True)
eng_is = gl.cut(eng, "is")
eng_val = gl.cut(eng, "val", track="review", label="lookahead:donch4h_stop:refimpl-compare")


def compare(ref, e, tag):
    ref = ref.set_index("entry_time")
    e = e.set_index("entry_time")
    common = ref.index.intersection(e.index)
    only_ref = ref.index.difference(e.index)
    only_eng = e.index.difference(ref.index)
    a, b = ref.loc[common], e.loc[common]
    same_side = (a.side.to_numpy() == b.side.to_numpy())
    d_entry = np.abs(a.entry.to_numpy() - b.entry.to_numpy())
    d_exit = np.abs(a.exit.to_numpy() - b.exit.to_numpy())
    same_xt = (a.exit_time.to_numpy() == b.exit_time.to_numpy())
    d_R = np.abs(a.R.to_numpy() - b.R.to_numpy())
    print(f"[{tag}] ref n={len(ref)} eng n={len(e)} common={len(common)} only_ref={len(only_ref)} "
          f"only_eng={len(only_eng)} same_side={same_side.mean():.4f} max|d_entry|={d_entry.max():.2e} "
          f"max|d_exit|={d_exit.max():.2e} same_exit_time={same_xt.mean():.4f} max|dR|={d_R.max():.2e}")
    bad = np.nonzero((~same_side) | (d_entry > 1e-6) | (d_exit > 1e-6) | (~same_xt) | (d_R > 1e-6))[0]
    if len(bad):
        print(" mismatches:")
        cols = ["side", "entry", "exit", "exit_time", "R"]
        print(pd.concat([a.iloc[bad][cols].add_prefix("ref_"), b.iloc[bad][cols + ["swap"]].add_prefix("eng_"),
                         a.iloc[bad][["swap"]].add_prefix("ref_")], axis=1).head(20).to_string())
    for x in only_ref[:10]:
        print("  only_ref", x, ref.loc[[x], ["side", "entry", "exit", "exit_time", "R"]].to_dict("records"))
    for x in only_eng[:10]:
        print("  only_eng", x, e.loc[[x], ["side", "entry", "exit", "exit_time", "R"]].to_dict("records"))
    return a, b


for dec in ("engine", "boundary"):
    ref = RI.run(t, c, dec=dec)
    r_is = ref[(ref.entry_time >= "2013-01-01") & (ref.entry_time < "2022-01-01")]
    r_val = ref[(ref.entry_time >= "2022-01-01") & (ref.entry_time < "2026-01-01")]
    print(f"== dec={dec}: ties (both levels in one M1 bar) among taken trades: {int(ref.tie.sum())}")
    print(f"   ref IS  n={len(r_is)} PF={RI.pf(r_is.R):.4f} t={RI.tstat(r_is.R):.3f}  | engine IS PF={RI.pf(eng_is.R):.4f}")
    print(f"   ref VAL n={len(r_val)} PF={RI.pf(r_val.R):.4f} t={RI.tstat(r_val.R):.3f} | engine VAL PF={RI.pf(eng_val.R):.4f}")
    compare(r_is, eng_is, f"{dec}/IS")
    compare(r_val, eng_val, f"{dec}/VAL")
# ties among ALL resolved orders of the engine (taken or skipped)
print("engine orders: all resolved OCO windows", len(o))
print(f"time {time.time()-t0:.1f}s")
