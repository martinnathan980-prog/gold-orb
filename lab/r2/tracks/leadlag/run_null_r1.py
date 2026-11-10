from common import *
import json, time
F = {"rule": "xlead", "leader": "us100", "pred": "lead", "sess": "uscash", "dirn": 1, "k": 1, "z": 6, "hold": 60, "stop": 2.0}
use("btcusd")
t = time.time()
nul = r2.null_test("btcusd", strategy.make_orders, F, n_seeds=200, mode="day")
print("null (mode day):", nul, f"{time.time()-t:.0f}s")
t = time.time()
nul2 = r2.null_test("btcusd", strategy.make_orders, F, n_seeds=200, mode="time", seed=1)
print("null (mode time):", nul2, f"{time.time()-t:.0f}s")
json.dump({"params": F, "day": nul, "time": nul2}, open(os.path.join(RES, "null_nq_btc.json"), "w"), indent=1)
