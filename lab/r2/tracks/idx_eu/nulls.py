"""Random-entry null (r2.null_test, mode 'day', 200 seeds) for shortlisted configurations (IS only)."""
import json, os, sys, time
from research import r2, S, OUT

def run(name, params, mode="day", n_seeds=200):
    t0 = time.time()
    res = r2.null_test("ger40", S.make_orders, params, n_seeds=n_seeds, mode=mode)
    res["name"] = name; res["params"] = {k: (list(v) if isinstance(v, tuple) else v) for k, v in params.items()}
    print(name, json.dumps({k: v for k, v in res.items() if k != "params"}), f"{time.time()-t0:.0f}s", flush=True)
    with open(os.path.join(OUT, "null_tests.jsonl"), "a") as f:
        f.write(json.dumps(res) + "\n")
    return res

if __name__ == "__main__":
    from stage1 import CONFIGS as C1
    from stage2 import CONFIGS as C2
    cfg = dict(C1); cfg.update(dict(C2))
    for name in sys.argv[1:]:
        run(name, cfg[name])
