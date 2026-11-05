"""Diagnostic on already-logged configs (IS only): why do A4b / A5a change so much with overlap?
For the overlap-allowed simulation: max concurrent positions, weekly-aggregated t-stat (accounts
for correlation of overlapping trades within a week), share of total R from the best 5 weeks,
and mean R of the signals the one-position engine takes vs the ones it skips."""
import json
import os

import numpy as np
import pandas as pd

from common import RES, gl
import strategy as S
from parta import CONFIGS, make_cache

NAMES = ["A4a_channel_usd_confirm", "A4b_channel_usd_contra", "A5a_resmom_n24_h3", "A5b_rawmom_n24_h3_control"]


def conc(t):
    ev = pd.concat([pd.Series(1, index=t.entry_time), pd.Series(-1, index=t.exit_time)]).sort_index()
    return int(ev.cumsum().max())


def main():
    m1 = gl.load_m1("xauusd")
    cache = make_cache()
    rows = []
    for nm in NAMES:
        p = {k: v for k, v in CONFIGS[nm].items() if k != "note"}
        o = S.make_orders(m1, None, cache=cache, **p)
        tov = gl.cut(gl.simulate(m1, o, no_overlap=False), "is")
        tno = gl.cut(gl.simulate(m1, o, no_overlap=True), "is")
        taken = tov.index.isin(tno.index)        # same order rows -> taken by the one-position engine
        wk = gl.weekly_R(tov)
        allw = pd.period_range(wk.index.min(), wk.index.max(), freq="W")
        wk = wk.reindex(allw, fill_value=0.0)
        top5 = wk.sort_values(ascending=False).head(5).sum()
        by_y = tov.groupby(tov.entry_time.dt.year).R.sum().round(1).to_dict()
        rows.append({"name": nm, "n_ov": len(tov), "max_conc": conc(tov),
                     "pf_ov": round(tov.R[tov.R > 0].sum() / -tov.R[tov.R < 0].sum(), 3),
                     "t_trades": round(tov.R.mean() / tov.R.std() * np.sqrt(len(tov)), 2),
                     "t_weekly": round(wk.mean() / wk.std() * np.sqrt(len(wk)), 2),
                     "totalR": round(tov.R.sum(), 1), "top5wk_R": round(top5, 1),
                     "meanR_taken": round(tov.R[taken].mean(), 3), "n_taken": int(taken.sum()),
                     "meanR_skipped": round(tov.R[~taken].mean(), 3), "n_skipped": int((~taken).sum()),
                     "by_year": by_y})
        print(json.dumps(rows[-1], default=str), flush=True)
    pd.DataFrame(rows).to_csv(os.path.join(RES, "overlap_deep.csv"), index=False)


if __name__ == "__main__":
    main()
