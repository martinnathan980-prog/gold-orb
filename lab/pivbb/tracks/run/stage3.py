import sys, json
sys.path.insert(0, "/home/user/gold-orb/lab")
import numpy as np
from pivbb.tracks.run.harness import trial, OUT
O2 = ["D_R2", "D_S2"]; O4 = ["D_R2", "D_S2", "D_R3", "D_S3"]
A = dict(levels=O2, entry="touch")
Bc = dict(levels=O4, hours=[2, 12], target=None)
NA = [("nA stop 0.15", dict(A, stop_atr=0.15)), ("nA stop 0.40", dict(A, stop_atr=0.40)), ("nA no target", dict(A, target=None)),
      ("nA stop-order at level", dict(A, fill="pending")), ("nA hours 02-16", dict(A, hours=[2, 16])), ("nA first touch", dict(A, nth="first")),
      ("nA + R3/S3", dict(A, levels=O4))]
NB = [("nB stop 0.15", dict(Bc, stop_atr=0.15)), ("nB stop 0.40", dict(Bc, stop_atr=0.40)), ("nB hours 02-14", dict(Bc, hours=[2, 14])),
      ("nB all hours", dict(Bc, hours=[0, 24])), ("nB R2/S2 only", dict(Bc, levels=O2)), ("nB trail mid", dict(Bc, trail_mid=True)),
      ("nB exit 15:00", dict(Bc, eod=900)), ("nB touch market", dict(Bc, entry="touch"))]
res = {}
for name, lst in (("A", NA), ("B", NB)):
    pfs = []
    for tag, prm in lst:
        ev, row = trial(tag, prm, kind="neighbour")
        pfs.append(row["pf"])
    res[name] = pfs
json.dump(res, open(OUT + "/neighbours_raw.json", "w"))
print(res, {k: float(np.median(v)) for k, v in res.items()})
