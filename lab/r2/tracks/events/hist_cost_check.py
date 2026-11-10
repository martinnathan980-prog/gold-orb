"""Information only (IS): the finalist rule under the HISTORICAL Dukascopy bid/ask (real spread of the time,
PROTOCOL_V2 section 3c) instead of the forward-looking FP frame.  Same slippage / swap as the FP model."""
import json, sys
import numpy as np, pandas as pd
from runner import RES, gl, r2, S
P = S.resolve(dict(rule="long", kinds="fomc+nfp+cpi", lead=5, exit="hold", hold=15, stop_atr=1.0, atr_n=14))
out = {}
for sym in ("us500", "us100"):
    r2.free(); S._cache.clear(); gl.data._cache.clear()
    m1 = gl.load_m1(sym, end="2022-01-01")          # raw Dukascopy quotes, in-sample only
    t = gl.cut(gl.simulate(m1, S.make_orders(m1, **P), sym=sym, costs=r2.costs(sym)), "is")
    rep = gl.report(t)
    spr = ((m1.ac - m1.bc) / ((m1.ac + m1.bc) / 2) * 1e4)
    e = t.entry_time
    sp_entry = spr.reindex(e).to_numpy()
    out[sym] = {"n": rep["n"], "pf": rep["pf"], "t": rep["t_stat"], "expR": rep["expectancy_R"], "years_pos": rep["years_pos"],
                "bps": round(float((t.pnl / t.entry).mean() * 1e4), 2), "median_spread_bp_at_entry": round(float(np.nanmedian(sp_entry)), 2),
                "by_year_R": rep["by_year_R"],
                "median_spread_bp_by_year_at_entry": {int(k): round(float(v), 2) for k, v in pd.Series(sp_entry, index=e.dt.year.to_numpy()).groupby(level=0).median().items()}}
    print(sym, out[sym], flush=True)
    gl.data._cache.clear()
json.dump(out, open(f"{RES}/hist_cost_check_is.json", "w"), indent=1, default=str)
