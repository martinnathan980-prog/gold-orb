from common import *
base = {"rule": "xlead", "leader": "us500", "pred": "resid", "dirn": 1, "hold": 30, "stop": 2.0}
for sess, zs in (("eu_am", (3, 4)), ("eurex_pm", (2, 3))):
    for k in (5, 15):
        for z in zs:
            run("ger40", dict(base, sess=sess, k=k, z=z), full=False, tag="R2s1")
print("trials (lines, distinct):", n_trials())
