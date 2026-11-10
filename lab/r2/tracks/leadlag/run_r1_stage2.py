from common import *
base = {"rule": "xlead", "leader": "us100", "pred": "lead", "sess": "uscash", "dirn": 1}
cfgs = [
    dict(base, k=1, z=6, hold=15, stop=1.0),
    dict(base, k=1, z=6, hold=15, stop=3.0),
    dict(base, k=1, z=6, hold=60, stop=2.0),
    dict(base, k=1, z=7, hold=15, stop=2.0),
    dict(base, k=5, z=6, hold=15, stop=1.0),
    dict(base, k=5, z=6, hold=15, stop=3.0),
]
for p in cfgs:
    run("btcusd", p, full=False, tag="R1s2")
print("trials (lines, distinct):", n_trials())
