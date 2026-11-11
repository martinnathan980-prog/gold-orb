"""Truncation test: orders built on data cut at random times (half of the cuts forced inside the US cash
session / Xetra session) must equal the orders built on the full frame up to the cut (entry bar, side, stop
distance; exit bar whenever the full-frame exit lies before the cut). IS frame only."""
import json
import numpy as np, pandas as pd
from common import *
A = dict(signal="ibs", thr=0.3, side=1, stop_atr=2.5, entry="close", trend=False, exit="sma5", hold=5)
B = dict(signal="ibs", thr=0.3, side=1, stop_atr=2.5, entry="1830", trend=False, exit="time", hold=1)
CONFIGS = {"A us100": ("us100", A), "B us100": ("us100", B), "A ger40": ("ger40", A),
           "A-hi rsi2 trend us500": ("us500", dict(A, signal="rsi2", thr=10, trend=True, exit="hi"))}


def check(sym, params, n_cuts=12, seed=11):
    use(sym)
    m1 = r2.load(sym, end="2022-01-01")
    p = dict(params, sess=SESS[sym])
    full = S.make_orders(m1, **p)
    te, tx = m1.index[full.entry_i.to_numpy()], m1.index[full.exit_i.to_numpy()]
    rng = np.random.default_rng(seed)
    tz, o, c = S.SESS[SESS[sym]]
    loc = gl.local(m1.index, tz); mod = (loc.hour * 60 + loc.minute).to_numpy()
    inside = np.flatnonzero((mod >= c - 6) & (mod <= c + 3) | (mod >= o) & (mod < o + 60))
    inside = inside[inside > len(m1) * 0.3]
    cuts = list(rng.integers(int(len(m1) * 0.3), len(m1) - 10, n_cuts // 2)) + list(rng.choice(inside, n_cuts - n_cuts // 2))
    res = []
    for cut in sorted(cuts):
        T = m1.index[cut]
        part = S.make_orders(m1.iloc[:cut], **p)
        ref = full[te < T].reset_index(drop=True)
        done = np.asarray(tx[te < T] < T)
        k = min(len(part), len(ref))
        a, b = part.iloc[:k], ref.iloc[:k]
        r = {"cut": str(T.tz_convert(tz)), "n_cut": len(part), "n_full_before": len(ref), "same_n": len(part) == len(ref),
             "same_entry": bool((a.entry_i.to_numpy() == b.entry_i.to_numpy()).all()),
             "same_side": bool((a.side.to_numpy() == b.side.to_numpy()).all()),
             "same_stop": bool(np.allclose(a.stop_dist.to_numpy(), b.stop_dist.to_numpy(), rtol=1e-12, atol=0)),
             "same_exit_when_done": bool((a.exit_i.to_numpy()[done[:k]] == b.exit_i.to_numpy()[done[:k]]).all()),
             "open_at_cut": int((~done).sum())}
        res.append(r)
    ok = all(r["same_n"] and r["same_entry"] and r["same_side"] and r["same_stop"] and r["same_exit_when_done"] for r in res)
    return ok, res


out = {}
for nm, (sym, params) in CONFIGS.items():
    ok, res = check(sym, params)
    out[nm] = {"sym": sym, "params": params, "pass": ok, "cuts": res}
    print(f"{nm:<24} {'PASS' if ok else 'FAIL'} " + " ".join(f"[{r['cut'][:16]} {r['n_cut']}/{r['n_full_before']} open={r['open_at_cut']}]" for r in res), flush=True)
    if not ok:
        print(json.dumps([r for r in res if not all(v for kk, v in r.items() if kk.startswith('same'))], indent=1))
r2.free()
json.dump(out, open(f"{RES}/causality.json", "w"), indent=1, default=str)
