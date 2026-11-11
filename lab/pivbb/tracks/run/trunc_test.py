"""Causality: orders built on data cut at random times == orders built on the full data, up to those times.
Orders sent in the last 20 minutes of the cut frame are left out: the rule needs 15 minutes before its forced exit, and
at the very end of a frame the forced exit is capped at the last bar (an end-of-file effect, not information from the future)."""
import sys, json
sys.path.insert(0, "/home/user/gold-orb/lab")
import numpy as np, pandas as pd
from goldlab import r2
from pivbb.tracks.run import strategy as S
m1 = r2.load("xauusd", end="2022-01-01")
rng = np.random.default_rng(7)
cuts = sorted(rng.integers(len(m1) // 3, len(m1) - 5000, 5))
CONFIGS = json.loads(sys.argv[1]) if len(sys.argv) > 1 else [
    dict(), dict(entry="touch", fill="pending"), dict(entry="touch"), dict(entry="retest", fill="pending"), dict(entry="retest"),
    dict(trail_mid=True, target=None, stop="mid", stop_atr=0.05), dict(levels=("W_P", "W_R1", "W_S1"), hold_days=1, trail_mid=True),
    dict(sq_max=0.7, bbout=True, hours=(2, 12), nth="first", away=1)]
res = []
for prm in CONFIGS:
    full = S.make_orders(m1, **prm)
    for n in cuts:
        part = S.make_orders(m1.iloc[:n], **prm)
        a = full[full.entry_i < n - 20].reset_index(drop=True)
        b = part[part.entry_i < n - 20].reset_index(drop=True)
        same_n = len(a) == len(b)
        ok = same_n
        if same_n and len(a):
            for col in ("entry_i", "side", "etype"):
                ok &= bool((a[col].to_numpy() == b[col].to_numpy()).all())
            for col in ("level", "stop", "target"):
                ok &= bool(np.allclose(a[col].to_numpy(), b[col].to_numpy(), equal_nan=True, rtol=0, atol=1e-9))
            closed = a.exit_i.to_numpy() < n - 2          # exits that happen before the cut must be identical
            ok &= bool((a.exit_i.to_numpy()[closed] == b.exit_i.to_numpy()[closed]).all())
            ok &= bool((b.exit_i.to_numpy()[~closed] >= n - 2).all()) if (~closed).any() else True
        res.append({"params": prm, "cut": str(m1.index[n]), "orders_before_cut": int(len(a)), "identical": bool(ok)})
        print(prm, m1.index[n], len(a), len(b), "OK" if ok else "MISMATCH", flush=True)
json.dump(res, open("/home/user/gold-orb/lab/results/pivbb/run/" + ("truncation_test_finalists.json" if len(sys.argv) > 1 else "truncation_test_all_modes.json"), "w"), indent=1, default=str)
print("all identical:", all(r["identical"] for r in res))
