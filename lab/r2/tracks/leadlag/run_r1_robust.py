from common import *
F = {"rule": "xlead", "leader": "us100", "pred": "lead", "sess": "uscash", "dirn": 1, "k": 1, "z": 6, "hold": 60, "stop": 2.0}
run("btcusd", dict(F, delay=1), full=False, tag="R1-60-delay1")
run("btcusd", dict(F, delay=2), full=False, tag="R1-60-delay2")
run("btcusd", dict(F, leader="us500"), full=False, tag="R1-60-leader-us500")
print("trials (lines, distinct):", n_trials())
