from common import *
A = dict(signal="ibs", thr=0.3, side=1, stop_atr=2.5, entry="close", trend=False, exit="sma5", hold=5)
B = dict(signal="ibs", thr=0.3, side=1, stop_atr=2.5, entry="1830", trend=False, exit="time", hold=1)
trial("us30", A, "A rep"); trial("ger40", A, "A rep"); trial("us30", B, "B rep")
for sym in ["us500", "us100"]:
    trial(sym, dict(A, side=-1), "A mirror short"); trial(sym, dict(B, side=-1), "B mirror short")
for nm, P in (("A", A), ("B", B)):
    for k, v in (("thr", 0.2), ("thr", 0.4), ("stop_atr", 2.0), ("stop_atr", 3.0)):
        trial("us100", dict(P, **{k: v}), f"{nm} nb {k}={v}")
r2.free()
