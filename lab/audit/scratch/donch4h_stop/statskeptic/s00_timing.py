import sys, time, os
sys.path.insert(0, '.')
sys.path.insert(0, 'tracks/trend')
import numpy as np, pandas as pd
import goldlab as gl
import strategy as S
t0=time.time()
m1 = gl.load_m1("xauusd")
print("load", round(time.time()-t0,1), m1.shape, m1.dtypes.unique(), m1.memory_usage(deep=True).sum()/1e6, "MB", m1.index[0], m1.index[-1])
t0=time.time()
o = S.make_orders(m1, **S.FINALISTS["donch4h_stop"])
print("orders", round(time.time()-t0,1), len(o))
t0=time.time()
t = gl.simulate(m1, o, no_overlap=True)
print("sim", round(time.time()-t0,1), len(t))
t0=time.time()
t = gl.simulate(m1, o, no_overlap=True)
print("sim2", round(time.time()-t0,1), len(t))
ti = gl.cut(t, "is")
r = gl.report(ti); print({k: r[k] for k in ("n","pf","t_stat","expectancy_R","years_pos","long_n","long_R","short_n","short_R")})
print(o.head())
print(o.columns.tolist())
