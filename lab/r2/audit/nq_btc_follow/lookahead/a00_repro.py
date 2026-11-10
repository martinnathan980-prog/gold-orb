"""Reproduce the finalist's reported IS numbers with the lab toolkit; store orders + IS trades for later comparison.
Also basic data facts for the two frames (span, gaps, bars per weekday)."""
from common import *

t0 = time.time()
m1 = r2.load("btcusd")
print("btcusd frame:", len(m1), m1.index[0], "->", m1.index[-1], "| mem MB", round(m1.memory_usage(deep=True).sum() / 1e6), flush=True)
assert m1.index[-1] < pd.Timestamp("2026-01-01", tz="UTC")
orders = strategy.make_orders(m1, **P)
print("orders:", len(orders), "| build", round(time.time() - t0, 1), "s", flush=True)
t = r2.run("btcusd", strategy.make_orders, P, "fp", True, m1)
ti = gl.cut(t, "is")
rep = report(ti)
print("IS report:", json.dumps({k: v for k, v in rep.items() if k not in ("exit_reasons",)}), flush=True)
print("exits:", rep["exit_reasons"], "| attrs", t.attrs, flush=True)
print("IS bps/trade:", r2._bps(ti))

# store IS-only orders (entry before 2022) and IS trades
et = m1.index[orders.entry_i.to_numpy()]
o_is = orders[et < IS_END].copy()
o_is["entry_time"] = et[et < IS_END]
o_is["exit_time_planned"] = m1.index[o_is.exit_i.to_numpy()]
o_is.to_parquet(os.path.join(OUT, "orders_is.parquet"))
ti.to_parquet(os.path.join(OUT, "trades_is_engine.parquet"))
print("stored", len(o_is), "IS orders and", len(ti), "IS trades")

# hold-time anomalies and exit reasons (IS)
print("hold_min distribution of time exits (IS):", ti[ti.reason == "time"].hold_min.value_counts().sort_index().to_dict())
print("planned exit - entry (minutes) for IS orders:",
      ((o_is.exit_time_planned - o_is.entry_time).dt.total_seconds() / 60).value_counts().sort_index().to_dict())
dump({"is_report": rep, "is_bps": r2._bps(ti), "n_orders_total": int(len(orders)), "n_orders_is": int(len(o_is))}, "a00_repro.json")
print("done", round(time.time() - t0, 1), "s")
