from common import *
import json
F = {"rule": "xlead", "leader": "us100", "pred": "lead", "sess": "uscash", "dirn": 1, "k": 1, "z": 6, "hold": 60, "stop": 2.0}
pf = {}
for d in (16, 24):
    e = run("btcusd", dict(F, sig_days=d), full=False, tag=f"R1-nb-sigdays{d}")
    pf[f"sig_days{d}"] = e["is"]["pf"]
nbp = os.path.join(RES, "neighbors_nq_btc.json")
nb = json.load(open(nbp))
for k, v in pf.items():
    nb["neighbors"][k] = {"params": dict(F, sig_days=int(k.replace("sig_days", ""))), "pf": v}
allpf = [v["pf"] for v in nb["neighbors"].values()]
nb["median_pf"] = float(np.median(allpf)); nb["min_pf"] = float(min(allpf)); nb["n_neighbors"] = len(allpf)
json.dump(nb, open(nbp, "w"), indent=1)
print("neighbour PFs:", {k: v["pf"] for k, v in nb["neighbors"].items()}, "median", nb["median_pf"])
print("trials (lines, distinct):", n_trials())
