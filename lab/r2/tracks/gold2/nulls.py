"""Random-entry null (PROTOCOL_V2 section 4) for the shortlisted rules, in-sample, mode 'day'."""
import json, os, sys, time
from research import RES, r2, S, use
import stageB, stageA

CANDS = {"SQ": ("xauusd", stageB.B["B5_sq1h_n24_07"]), "TR": ("xauusd", stageB.B["B3_d1h_n48_tr240_k2"])}
if __name__ == "__main__":
    pth = os.path.join(RES, "null_tests.json")
    res = json.load(open(pth)) if os.path.exists(pth) else {}
    for k, (sym, p) in CANDS.items():
        for mode in ("day", "time"):
            key = f"{k}:{sym}:{mode}"
            if key in res:
                print(key, res[key]); continue
            use(sym)
            t0 = time.time()
            r = r2.null_test(sym, S.make_orders, S.resolve(p), n_seeds=200, mode=mode)
            r["secs"] = round(time.time() - t0, 1)
            res[key] = r
            print(key, json.dumps(r), flush=True)
            json.dump(res, open(pth, "w"), indent=1)
