from common import *
base = {"rule": "xlead", "leader": "us100", "pred": "lead", "sess": "uscash", "dirn": 1}
for k in (1, 5):
    for z in (4, 5, 6):
        for hold in (15, 30):
            p = dict(base, k=k, z=z, hold=hold, stop=2.0)
            run("btcusd", p, full=False, tag="R1s1")
print("trials (lines, distinct):", n_trials())
