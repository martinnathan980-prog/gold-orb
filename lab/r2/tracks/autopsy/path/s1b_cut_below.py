"""Part 1 (continued, description only): the anatomy rows summed cumulatively.

For each sleeve, checkpoint and threshold theta, the trades still open at the checkpoint whose state is <= theta
(theta < 0: "hard the wrong way"; theta >= 0: "not ahead by theta"): how many, and the sum and mean of the rest of
those trades (final R minus the R of closing at the next bar's open).  Minus that sum is the first-order effect of a
rule that would close them there, BEFORE the freed position slot lets new signals in (that second effect needs the
full re-simulation of part 2).  Common window 2018-02-01..2021-12-31, the earlier years separately, and by year.
Output: results/r2/autopsy/path/anatomy_cut_below.csv
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

THETAS = [-0.75, -0.5, -0.25, 0.0, 0.25, 0.5]


def main():
    ck = pd.read_parquet(os.path.join(C.RES, "anatomy_checkpoints.parquet"))
    tr = pd.read_parquet(os.path.join(C.RES, "anatomy_trades.parquet"))
    base = tr.groupby(["sleeve", "period"]).agg(n_trades=("R", "size"), total_R=("R", "sum")).reset_index()
    rows = []
    for (sl, per, cp), d in ck.groupby(["sleeve", "period", "checkpoint"], observed=True):
        b = base[(base.sleeve == sl) & (base.period == per)].iloc[0]
        for th in THETAS:
            x = d[d.u <= th]
            r = {"sleeve": sl, "period": per, "checkpoint": cp, "theta": th, "n_open": int(len(d)),
                 "n_cut": int(len(x)), "share_cut_of_trades": round(len(x) / b.n_trades, 3),
                 "rest_sum": round(float(x.rest.sum()), 2), "rest_mean": round(float(x.rest.mean()), 4) if len(x) else None,
                 "first_order_gain_R": round(float(-x.rest.sum()), 2),
                 "gain_pct_of_total_R": round(float(-x.rest.sum() / b.total_R * 100), 1) if b.total_R > 0 else None,
                 "cut_losers_share": round(float((x.R <= 0).mean()), 3) if len(x) else None}
            if per == "2018-2021":
                for y in C.YEARS:
                    xy = x[x.year == y]
                    r[f"gain_{y}"] = round(float(-xy.rest.sum()), 2)
                r["years_gain_pos"] = int(sum(r[f"gain_{y}"] > 0 for y in C.YEARS))
            rows.append(r)
    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(C.RES, "anatomy_cut_below.csv"), index=False)


if __name__ == "__main__":
    main()
