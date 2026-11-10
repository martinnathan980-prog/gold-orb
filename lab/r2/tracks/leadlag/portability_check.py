"""Checks without any P&L: (1) the set_leader() hook gives the same orders as the default research loader;
(2) on a SHORT frame (as the 2026 holdout will be) orders equal the full-frame orders once the 20-day
warm-up is over (so the holdout frame must come with >= ~25 days of history before the first trade date)."""
from common import *
import gc, json
p = strategy.FINALISTS["nq_btc_follow"]["params"]
use("btcusd")
m1 = r2.load("btcusd")
strategy.clear_leaders()
full = strategy.make_orders(m1, **p)
ft = m1.index[full.entry_i.to_numpy()]
# (1) hook: leader given as an M1 frame
L = pd.read_parquet(os.path.join(LAB, "data", "fp", "us100_m1.parquet"))
L = L[L.index < pd.Timestamp("2026-01-01", tz="UTC")]
strategy.clear_leaders(); strategy.set_leader("us100", L)
o2 = strategy.make_orders(m1, **p)
same1 = len(o2) == len(full) and bool((o2.values == full.values).all())
# (2) short frame starting 2025-06-01 (follower and leader both cut)
a = pd.Timestamp("2025-06-01", tz="UTC")
ms = m1[m1.index >= a]
strategy.clear_leaders(); strategy.set_leader("us100", L[L.index >= a])
o3 = strategy.make_orders(ms, **p)
t3 = ms.index[o3.entry_i.to_numpy()]
b = pd.Timestamp("2025-07-01", tz="UTC")
A = pd.DataFrame({"t": ft[ft >= b], "side": full.side.to_numpy()[ft >= b], "sd": full.stop_dist.to_numpy()[ft >= b]}).reset_index(drop=True)
B = pd.DataFrame({"t": t3[t3 >= b], "side": o3.side.to_numpy()[t3 >= b], "sd": o3.stop_dist.to_numpy()[t3 >= b]}).reset_index(drop=True)
same2 = len(A) == len(B) and bool((A.t.values == B.t.values).all()) and bool((A.side.values == B.side.values).all()) and bool(np.allclose(A.sd.values, B.sd.values, rtol=1e-9))
first_short = str(t3.min()) if len(t3) else None
res = {"set_leader_hook_identical": bool(same1), "n_orders_full_frame": int(len(full)),
       "short_frame_from": str(a), "first_order_on_short_frame": first_short,
       "orders_from_2025-07-01_identical_to_full_frame": bool(same2), "n_compared": int(len(A))}
print(res)
json.dump(res, open(os.path.join(RES, "portability_nq_btc.json"), "w"), indent=1)
strategy.clear_leaders(); del L; gc.collect()
