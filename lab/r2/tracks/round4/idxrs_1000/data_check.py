"""Data availability of the three in-sample frames on NYSE full sessions (no rule result is computed here).
Writes results/r2/round4/idxrs_1000/data_check.json."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402


def main():
    fr = C.load_frames()
    out = {"frames": {}}
    for s, df in fr.items():
        sec = (df.index.as_unit("ns").asi8 % C.MIN_NS)
        out["frames"][s] = {"rows_is": int(len(df)), "first": str(df.index[0]), "last": str(df.index[-1]),
                            "max_ts_lt_2022": bool(df.index.max() < C.CUT), "non_whole_minute_stamps": int((sec != 0).sum())}
    days = C.sessions()
    G = C.build_grid(fr, days)
    P = C.prepare(G)
    yrs = days.year.to_numpy()
    cols = {"09:30": 0, "09:59": 29, "10:00": 30, "15:55": 385, "15:59": 389}
    by = {}
    for y in np.unique(yrs):
        m = yrs == y
        row = {"sessions": int(m.sum())}
        for i, s in enumerate(C.SYMS):
            have = np.isfinite(P["mo"][i][m])
            row[s] = {k: int(have[:, c].sum()) for k, c in cols.items()}
            row[s]["missing_bars_0930_1559_total"] = int((~have[:, :390]).sum())
            row[s]["days_with_any_missing_bar_0930_1559"] = int((~have[:, :390]).any(axis=1).sum())
            sp = (P["ao"][i][m] - P["bo"][i][m]) / P["mo"][i][m] * 1e4
            row[s]["median_spread_bp_10:00"] = round(float(np.nanmedian(sp[:, 30])), 3)
            row[s]["median_spread_bp_15:55"] = round(float(np.nanmedian(sp[:, 385])), 3)
        allthree = np.isfinite(P["mo"][:, m, 0]).all(axis=0) & np.isfinite(P["mc"][:, m, 29]).all(axis=0)
        row["days_ranked_all_three"] = int(allthree.sum())
        by[int(y)] = row
    out["by_year"] = by
    out["sessions_total"] = int(len(days))
    out["first_session"], out["last_session"] = str(days[0].date()), str(days[-1].date())
    C.jdump(out, os.path.join(C.OUT, "data_check.json"))
    for y, r in by.items():
        print(y, r["sessions"], "ranked", r["days_ranked_all_three"],
              {s: (r[s]["10:00"], r[s]["15:55"], r[s]["days_with_any_missing_bar_0930_1559"], r[s]["median_spread_bp_10:00"])
               for s in C.SYMS})
    print(out["frames"])


if __name__ == "__main__":
    main()
