"""Random-entry null (PROTOCOL_V2): same trades (side, stop, duration) at random days / same NY time."""
from harness import *     # noqa
import sys
todo = {
    "noise_us100": ("us100", dict(rule="noise")),
    "ocm_atr0.3_us100": ("us100", dict(rule="ocm", stop="atr", k=0.3)),
}
out = {}
p = os.path.join(RES, "null_tests.json")
if os.path.exists(p):
    out = json.load(open(p))
for name, (sym, params) in todo.items():
    if name in out:
        print(name, out[name]); continue
    t0 = time.time()
    nul = r2.null_test(sym, S.make_orders, S.resolve(params), n_seeds=200, mode="day")
    nul["secs"] = round(time.time() - t0, 1)
    nul["params"] = S.resolve(params); nul["sym"] = sym
    out[name] = nul
    print(name, nul, flush=True)
    json.dump(out, open(p, "w"), indent=1, default=str)
