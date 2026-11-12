"""Part 1 addendum (description, computed after stage A): are the portfolio-level clock gaps quoted by the autopsy
(fills after 12:00 New York earn less; Friday fills earn less) a within-sleeve effect or a mix effect (sleeves with a
lower mean trading more at those times)? For each year: raw gap = mean R(cell) - mean R(rest) over all ten chains (FP,
stake 1); within-sleeve gap = trade-weighted mean over sleeves of (mean R of the sleeve's trades in the cell - mean R
of its other trades that year), sleeves with >= 5 trades on both sides; and the count of sleeve-years with a negative
gap. Description only, no stake, no trial.

    NUMBA_CACHE_DIR=/tmp/numba_clock PYTHONDONTWRITEBYTECODE=1 python3 s2b_decompose.py
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common as C  # noqa: E402
import engine as E  # noqa: E402


def main():
    d = pd.concat([E.chain(k, "fp").assign(sleeve=k) for k in C.KEYS], ignore_index=True)
    d["year"] = d.entry_time.dt.year
    d["after12"] = C.local_hours(d.entry_time, C.NY) >= 12.0
    d["fri"] = C.server_weekday(d.entry_time) == 4
    out = {}
    for cut in ("after12", "fri"):
        rows = {}
        for y, g in d[d.year >= 2014].groupby("year"):
            raw = float(g.R[g[cut]].mean() - g.R[~g[cut]].mean())
            gaps, w, neg, tot = [], [], 0, 0
            per = {}
            for k, s in g.groupby("sleeve"):
                if k in C.NO_WEEKDAY and cut == "fri":
                    continue
                a, b = s.R[s[cut]], s.R[~s[cut]]
                if len(a) >= 5 and len(b) >= 5:
                    gp = float(a.mean() - b.mean())
                    gaps.append(gp)
                    w.append(len(a))
                    neg += int(gp < 0)
                    tot += 1
                    per[k] = {"n_cell": int(len(a)), "gap": round(gp, 4)}
            rows[int(y)] = {"raw_gap": round(raw, 4), "n_cell": int(g[cut].sum()), "n_rest": int((~g[cut]).sum()),
                            "within_gap_weighted": round(float(np.average(gaps, weights=w)), 4) if gaps else None,
                            "sleeve_years_negative": f"{neg}/{tot}", "per_sleeve": per}
        out[cut] = rows
        print(cut)
        for y, r in rows.items():
            print(f"  {y}: raw {r['raw_gap']:+.3f} (n {r['n_cell']}/{r['n_rest']}) within-sleeve {r['within_gap_weighted']:+.3f} "
                  f"negative sleeves {r['sleeve_years_negative']}")
        oof = [r for y, r in rows.items() if y in C.OOF]
        neg = sum(int(x.split('/')[0]) for x in [r["sleeve_years_negative"] for r in oof])
        tot = sum(int(x.split('/')[1]) for x in [r["sleeve_years_negative"] for r in oof])
        print(f"  2019-2021 sleeve-years with a negative gap: {neg}/{tot}")
        out[cut + "_2019_2021_negative_sleeve_years"] = f"{neg}/{tot}"
    C.jdump(out, os.path.join(C.OUT, "part1_decomposition.json"))


if __name__ == "__main__":
    main()
