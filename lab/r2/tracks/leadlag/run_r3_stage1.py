from common import *
ALL = ["us100", "us500", "us30"]
for disp in (0.0, 1.0, 1.5):
    for sym in ALL:
        peers = [s for s in ALL if s != sym]
        run(sym, {"rule": "relstr", "peers": peers, "T": 600, "ref": "open", "disp": disp, "xmin": 959, "stop": 3.0}, full=False, tag="R3s1")
print("trials (lines, distinct):", n_trials())
