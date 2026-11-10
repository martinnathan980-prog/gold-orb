"""Information only (PROTOCOL_V2 s.3c): the candidate under the HISTORICAL Dukascopy bid/ask (IS only)."""
from common import *
import json, gc
from goldlab.split import cut
from goldlab.metrics import report
F = {"rule": "xlead", "leader": "us100", "pred": "lead", "sess": "uscash", "dirn": 1, "k": 1, "z": 6, "hold": 60, "stop": 2.0}
r2.free(); gc.collect()
raw = gl.load_m1("btcusd", end="2022-01-01")          # raw Dukascopy quotes, in-sample only
o = strategy.make_orders(raw, **F)
t = cut(gl.simulate(raw, o, sym="btcusd", costs=r2.costs("btcusd"), no_overlap=True), "is")
rep = report(t)
by = {int(y): {"n": int(len(g)), "net_bps": round(float((g.pnl / g.entry).mean() * 1e4), 1), "R": round(float(g.R.sum()), 1),
               "median_spread_bps_at_entry": round(float(((raw.ao - raw.bo) / raw.bo * 1e4).reindex(g.entry_time).median()), 1)}
      for y, g in t.groupby(t.entry_time.dt.year)}
out = {"model": "raw Dukascopy bid/ask of the time + FP slippage, no commission", "n": rep["n"], "pf": rep["pf"], "t": rep["t_stat"],
       "expectancy_R": rep["expectancy_R"], "net_bps": round(float((t.pnl / t.entry).mean() * 1e4), 1), "by_year": by}
print(json.dumps(out, indent=1))
json.dump(out, open(os.path.join(RES, "hist_cost_nq_btc.json"), "w"), indent=1)
gl.data._cache.clear()
