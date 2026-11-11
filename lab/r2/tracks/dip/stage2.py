from common import *
BASE = dict(signal="ibs", thr=0.3, side=1, stop_atr=2.5, entry="close", trend=False)
CFG = [("X1 ibs<.3 exit up", dict(exit="up", hold=5)), ("X2 ibs<.3 exit sma5", dict(exit="sma5", hold=5)),
       ("X3 ibs<.3 next close", dict(exit="time", hold=1)), ("X4 ibs<.3 3 days", dict(exit="time", hold=3)),
       ("X5 ibs<.3 swap-free 18:30->16:00", dict(exit="time", hold=1, entry="1830"))]
for sym in ["us500", "us100"]:
    for lab, p in CFG:
        trial(sym, dict(BASE, **p), lab)
r2.free()
