from common import *
base = {"rule": "xlead", "leader": "ethusd", "pred": "lead", "k": 1, "sess": "all", "dirn": 1, "hold": 5, "stop": 2.0}
for z in (5, 8):
    run("btcusd", dict(base, z=z), full=True, tag="R4")
print("trials (lines, distinct):", n_trials())
