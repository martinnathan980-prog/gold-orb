"""Port check (no performance evaluation): the gold2 re-implementations of the round-1 rules must build
the same orders as the round-1 code on the in-sample FP frame."""
import importlib.util
import json
import os
import sys
import tempfile
import time

# the round-1 modules are imported read-only: keep numba's compiled cache out of their folders
os.environ.setdefault("NUMBA_CACHE_DIR", tempfile.mkdtemp(prefix="gold2_nbcache_"))

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, LAB)
sys.path.insert(0, HERE)
import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
import strategy as S  # noqa: E402


def r1(name):
    spec = importlib.util.spec_from_file_location("r1_" + name, os.path.join(LAB, "tracks", name, "strategy.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["r1_" + name] = mod          # numba's on-disk cache re-imports the module by name
    spec.loader.exec_module(mod)
    return mod


def cmp(a, b, cols, name):
    a = a.sort_values(["entry_i", "side"]).reset_index(drop=True)
    b = b.sort_values(["entry_i", "side"]).reset_index(drop=True)
    out = {"name": name, "n_r1": int(len(a)), "n_gold2": int(len(b))}
    if len(a) == len(b):
        for col in cols:
            x, y = a[col].to_numpy(float), b[col].to_numpy(float)
            same = np.isclose(x, y, rtol=0, atol=1e-9) | (np.isnan(x) & np.isnan(y))
            out["diff_" + col] = int((~same).sum())
            if col == "exit_i" and (~same).any():
                out["exit_diff_examples"] = [(int(p), int(q)) for p, q in zip(x[~same][:5], y[~same][:5])]
    else:
        ka = set(zip(a.entry_i, a.side))
        kb = set(zip(b.entry_i, b.side))
        out["only_r1"] = len(ka - kb)
        out["only_gold2"] = len(kb - ka)
    print(json.dumps(out), flush=True)
    return out


m1 = r2.load("xauusd", end="2022-01-01")
res = []
t0 = time.time()
orb = r1("orb")
BASE = dict(entry="stop", stop_mode="opp", target_R=None, exit_time="16:00", exit_tz="NY")
R1 = {
    "S1_asia": (dict(tz="LDN", range_start="00:00", range_end="07:00", entry_end="12:00"),
                dict(family="orb", tz="LDN", range_start=0, range_end=420, entry_end=720)),
    "S2_ldn30": (dict(tz="LDN", range_start="08:00", range_end="08:30", entry_end="12:00"),
                 dict(family="orb", tz="LDN", range_start=480, range_end=510, entry_end=720)),
    "S3_ldn60": (dict(tz="LDN", range_start="08:00", range_end="09:00", entry_end="12:00"),
                 dict(family="orb", tz="LDN", range_start=480, range_end=540, entry_end=720)),
    "S6_us15": (dict(tz="NY", range_start="09:30", range_end="09:45", entry_end="12:00"),
                dict(family="orb", tz="NY", range_start=570, range_end=585, entry_end=720)),
    "F3_asia2d": (dict(tz="LDN", range_start="00:00", range_end="07:00", entry_end="12:00", buf_frac=0.1, hold_days=2),
                  dict(family="orb", tz="LDN", range_start=0, range_end=420, entry_end=720, buf_frac=0.1, hold_days=2)),
}
for k, (p1, p2) in R1.items():
    a = orb.make_orders(m1, **{**BASE, **p1})
    b = S.make_orders(m1, **p2)
    res.append(cmp(a, b, ["entry_i", "side", "level", "stop", "exit_i"], "orb/" + k))
print("orb", round(time.time() - t0, 1), "s", flush=True)

piv = r1("pivots")
a = piv.make_orders(m1, **piv.FINALISTS["rn100_break_fresh"])
b = S.make_orders(m1, family="rn")
res.append(cmp(a, b, ["entry_i", "side", "level", "expiry_i", "stop", "target", "exit_i"], "pivots/rn100_break_fresh"))

tr = r1("trend")
a = tr.make_orders(m1, **tr.FINALISTS["donch4h_stop"])
b = S.make_orders(m1, family="donch", tf=240, n=60, stop_atr=2.0, trail_atr=2.0, max_days=5, atr_n=14)
res.append(cmp(a, b, ["entry_i", "side", "level", "expiry_i", "stop_dist", "trail", "exit_i"], "trend/donch4h_stop"))
a = tr.make_orders(m1, **{**tr.FINALISTS["donch4h_stop"], "tf": "1h", "n": 240, "stop_atr": 4.0, "trail_atr": 4.0})
b = S.make_orders(m1, family="donch", tf=60, n=240, stop_atr=4.0, trail_atr=4.0, max_days=5, atr_n=14)
res.append(cmp(a, b, ["entry_i", "side", "level", "expiry_i", "stop_dist", "trail", "exit_i"], "trend/donch1h_240"))
json.dump(res, open(os.path.join(LAB, "results", "r2", "gold2", "port_check.json"), "w"), indent=1)
print("done", round(time.time() - t0, 1), "s")
