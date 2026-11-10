from causality import *
import json
p = strategy.FINALISTS["nq_btc_follow"]["params"]
ok, n = truncation_test("btcusd", p, n_cuts=6, seed=11)
print("finalist nq_btc_follow truncation test:", ok, "orders", n)
json.dump({"finalist": "nq_btc_follow", "params": p, "n_cuts": 6, "identical": bool(ok), "n_orders_full": int(n),
           "method": "orders rebuilt on the follower frame AND the leader series both cut at 6 random times (2019-2021) equal the full-data orders whose entry and exit are before the cut"},
          open(os.path.join(RES, "causality_nq_btc.json"), "w"), indent=1)
