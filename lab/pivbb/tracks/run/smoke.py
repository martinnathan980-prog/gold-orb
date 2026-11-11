import sys, time, json
sys.path.insert(0, "/home/user/gold-orb/lab")
import numpy as np, pandas as pd
import goldlab as gl
from goldlab import r2
from pivbb.tracks.run import strategy as S
m1 = r2.load("xauusd", end="2022-01-01")
print(len(m1), m1.index[0], m1.index[-1])
t0=time.time(); c = S.context(m1); print("ctx", time.time()-t0)
D = c["D"]; print(D.tail(3)); print("days", len(D), "full", D.full.sum())
# compare levels with shared events file
ev = pd.read_parquet("results/pivbb/events_is.parquet"); ev = ev[ev.seed==-1]
T = S.level_table(c)
chk = ev.drop_duplicates(["day","level"])[["day","level","px","atr_d"]]
pos = D.index.get_indexer(pd.DatetimeIndex(chk.day))
for nm in ["D_P","D_R2","PDH","W_R1"]:
    q = chk[chk.level==nm]; mine = T[nm][D.index.get_indexer(pd.DatetimeIndex(q.day))]
    print(nm, len(q), "max abs diff", np.nanmax(np.abs(mine-q.px.to_numpy())), "atr diff", np.nanmax(np.abs(D.atr.to_numpy()[D.index.get_indexer(pd.DatetimeIndex(q.day))]-q.atr_d.to_numpy())))
for prm in [dict(), dict(entry="touch", fill="pending"), dict(entry="touch"), dict(entry="retest", fill="pending"), dict(entry="retest"), dict(trail_mid=True, target=None)]:
    t0=time.time(); o = S.make_orders(m1, **prm); print(prm, len(o), round(time.time()-t0,2)); 
print(o.head())
# touches vs events
sig,_,_ = S.signals(m1, entry="touch", levels=("D_R1",))
e = ev[ev.level=="D_R1"]
print("touch count mine", len(sig), "events", len(e))
