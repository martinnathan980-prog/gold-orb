from common import *
base = {"rule": "xlead", "leader": "us500", "pred": "resid", "dirn": 1, "hold": 30, "stop": 2.0}
run("ger40", dict(base, sess="eu_am", k=5, z=3), full=True, tag="R2s2-full")
run("ger40", dict(base, sess="eurex_pm", k=15, z=2, hold=60), full=False, tag="R2s2")
run("ger40", dict(base, sess="eu_am", k=5, z=3, stop=3.0), full=False, tag="R2s2")
run("us500", {"rule": "xlead", "leader": "ger40", "pred": "resid", "dirn": 1, "hold": 30, "stop": 2.0, "sess": "xetra", "k": 5, "z": 4}, full=False, tag="R2mirror")
print("trials (lines, distinct):", n_trials())
