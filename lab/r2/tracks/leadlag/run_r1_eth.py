from common import *
F = {"rule": "xlead", "leader": "us100", "pred": "lead", "sess": "uscash", "dirn": 1, "k": 1, "z": 6, "hold": 60, "stop": 2.0}
ev = run("ethusd", F, full=True, tag="R1-eth")
print(r2.is_criteria(ev))
print("trials (lines, distinct):", n_trials())
