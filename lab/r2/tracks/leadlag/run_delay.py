from common import *
r1 = {"rule": "xlead", "leader": "us100", "pred": "lead", "sess": "uscash", "dirn": 1, "k": 1, "z": 6, "stop": 2.0}
r4 = {"rule": "xlead", "leader": "ethusd", "pred": "lead", "k": 1, "sess": "all", "dirn": 1, "hold": 5, "stop": 2.0, "z": 5}
run("btcusd", dict(r4, delay=1), full=False, tag="R4-delay")
run("btcusd", dict(r4, delay=2), full=False, tag="R4-delay")
run("btcusd", dict(r1, hold=15, delay=2), full=False, tag="R1-delay")
run("btcusd", dict(r1, hold=15, delay=5), full=False, tag="R1-delay")
run("btcusd", dict(r1, hold=60, delay=5), full=False, tag="R1-delay")
print("trials (lines, distinct):", n_trials())
