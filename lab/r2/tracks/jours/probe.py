"""Probe: order columns and timing of the ten sleeves on in-sample frames (no result printed after 2021)."""
import sys, time, importlib.util, os
import numpy as np, pandas as pd
import common as C
from goldlab import r2
spec = importlib.util.spec_from_file_location("r2_recalc", os.path.join(C.LAB, "r2", "recalc.py"))
recalc = importlib.util.module_from_spec(spec); sys.modules["r2_recalc"] = recalc; spec.loader.exec_module(recalc)
sl = [s for s in recalc.sleeves() if (s[1], s[2]) in C.SLEEVES]
sl.sort(key=lambda s: s[2])
want = sys.argv[1:]
last = None
for track, name, sym, mo, params in sl:
    if want and sym not in want: continue
    if sym != last:
        m1 = C.load_is(sym); last = sym
    t0 = time.time()
    o = mo(m1, **params)
    print(name, sym, "orders", len(o), "t=%.1fs" % (time.time() - t0), list(o.columns))
    for c in ("etype", "trail", "be", "target", "target_dist", "stop", "stop_dist", "exit_i", "expiry_i"):
        if c in o:
            v = o[c]
            print("   ", c, "nan%%=%.2f" % v.isna().mean(), "uniq" if v.nunique() < 6 else "", v.unique()[:5] if v.nunique() < 6 else v.describe()[["min", "50%", "max"]].round(2).to_dict())
    if "exit_i" in o:
        print("    sched hold (min) median", float((o.exit_i - o.entry_i).median()))
