from common import *
import json
F = {"rule": "xlead", "leader": "us100", "pred": "lead", "sess": "uscash", "dirn": 1, "k": 1, "z": 6, "hold": 60, "stop": 2.0}
out = {}
ev = run("btcusd", F, full=True, tag="R1-final")
out["final"] = ev
nb = {"z5": dict(F, z=5), "z7": dict(F, z=7), "hold48": dict(F, hold=48), "hold72": dict(F, hold=72),
      "stop1.6": dict(F, stop=1.6), "stop2.4": dict(F, stop=2.4), "k2": dict(F, k=2), "k5": dict(F, k=5)}
pfs = {}
for name, p in nb.items():
    e = run("btcusd", p, full=False, tag="R1-nb-" + name)
    pfs[name] = e["is"]["pf"]
print("neighbour PFs:", pfs, "median", float(np.median(list(pfs.values()))))
json.dump({"center": F, "neighbors": {k: {"params": nb[k], "pf": pfs[k]} for k in nb}, "median_pf": float(np.median(list(pfs.values())))},
          open(os.path.join(RES, "neighbors_nq_btc.json"), "w"), indent=1)
print("trials (lines, distinct):", n_trials())
