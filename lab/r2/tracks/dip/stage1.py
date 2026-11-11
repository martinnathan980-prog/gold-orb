from common import *
BASE = dict(side=1, exit="hi", hold=5, stop_atr=2.5, entry="close", trend=False)
CFG = [("S1 ibs<0.2", dict(signal="ibs", thr=0.2)), ("S2 ibs<0.3", dict(signal="ibs", thr=0.3)),
       ("S3 rsi2<10", dict(signal="rsi2", thr=10)), ("S4 rsi2<10 trend", dict(signal="rsi2", thr=10, trend=True)),
       ("S5 down3", dict(signal="down3", thr=3)), ("S6 bb20,2", dict(signal="bb", thr=0))]
for sym in ["us500", "us100"]:
    for lab, p in CFG:
        trial(sym, dict(BASE, **p), lab)
r2.free()
