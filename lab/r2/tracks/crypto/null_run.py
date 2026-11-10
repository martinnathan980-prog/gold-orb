"""Random-entry null (r2.null_test, mode 'day', 200 seeds) for the shortlisted sleeves. IS only."""
import sys, json, time
sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/crypto")
from helpers import *  # noqa

from final_cfg import FINAL as CFG

if __name__ == "__main__":
    path = os.path.join(OUT, "null_tests.json")
    out = json.load(open(path)) if os.path.exists(path) else {}
    for sym in ("btcusd", "ethusd"):
        for name, p in CFG.items():
            for mode in ("day", "time"):
                key = f"{name}:{sym}:{mode}"
                if key in out:
                    continue
                t0 = time.time()
                out[key] = r2.null_test(sym, S.make_orders, p, n_seeds=200, mode=mode)
                print(key, out[key], f"[{time.time() - t0:.0f}s]", flush=True)
                json.dump(out, open(path, "w"), indent=1)
        r2.free()
