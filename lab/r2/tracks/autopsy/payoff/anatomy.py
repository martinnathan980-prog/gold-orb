"""Anatomy of the reference trades (what the losses are), common window 2018-02..2021, FP costs.  IN SAMPLE ONLY.

Reads reference_<name>__<sym>.parquet (written by run.py: the official trades re-simulated, with excursions) and
writes anatomy_sleeves.csv, anatomy_mae_winners.csv, anatomy_mfe_losers.csv, anatomy_loss_buckets.csv.
Excursions come from the simulator (mfe / mae in price, from the fill, on the exit side: bid for a long, ask for a
short; the exit bar of a stopped trade is not included), divided by the trade's risk |fill - stop| to give R.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


def one(key):
    name, sym = key.split(":")
    rt = pd.read_parquet(os.path.join(C.OUT, f"reference_{name}__{sym}.parquet"))
    t = C.window(rt[rt["mode"] == "fp"], "common").copy()
    R = t["R"].to_numpy()
    t["mfe_R"] = t["mfe"] / t["risk"]
    t["mae_R"] = -t["mae"] / t["risk"]
    win, los = t[R > 0], t[R < 0]
    stopped = los["reason"].isin(["stop", "gap", "trail"])
    big = los["R"] <= -0.9
    gl_ = -los["R"].sum()
    srt = np.sort(los["R"].to_numpy())
    k10 = max(1, int(round(0.1 * len(srt))))
    row = {"sleeve": key, "n": len(t), "win_rate": round(float((R > 0).mean()), 4),
           "avg_win_R": round(float(win["R"].mean()), 3), "avg_loss_R": round(float(los["R"].mean()), 3),
           "exp_R": round(float(R.mean()), 4), "total_R": round(float(R.sum()), 2),
           "gross_loss_R": round(float(gl_), 2), "gross_win_R": round(float(win["R"].sum()), 2),
           "losers": len(los), "losers_at_stop": int(stopped.sum()),
           "losers_at_stop_sum_R": round(float(los.loc[stopped, "R"].sum()), 2),
           "losers_at_stop_share_of_gross_loss": round(float(-los.loc[stopped, "R"].sum() / gl_), 3) if gl_ else 0,
           "losers_other_exit": int((~stopped).sum()),
           "losers_other_mean_R": round(float(los.loc[~stopped, "R"].mean()), 3) if (~stopped).any() else 0.0,
           "losers_le_minus_0.9R": int(big.sum()), "share_of_losers_le_minus_0.9R": round(float(big.mean()), 3),
           "worst10pct_losers_share_of_gross_loss": round(float(-srt[:k10].sum() / gl_), 3) if gl_ else 0,
           "worst_R": round(float(R.min()), 3),
           "losers_mean_hold_h": round(float(los["hold_min"].mean() / 60), 2),
           "winners_mean_hold_h": round(float(win["hold_min"].mean() / 60), 2),
           "stopped_median_hold_min": round(float(los.loc[stopped, "hold_min"].median()), 1) if stopped.any() else None}
    for k in (0.25, 0.5, 0.75):
        row[f"winners_mae_ge_{k}R"] = round(float((win["mae_R"] >= k).mean()), 3)
    for k in (0.5, 1.0, 1.5):
        row[f"losers_mfe_ge_{k}R"] = round(float((los["mfe_R"] >= k).mean()), 3)
        row[f"all_mfe_ge_{k}R"] = round(float((t["mfe_R"] >= k).mean()), 3)
    row["winners_median_giveback_R"] = round(float((win["mfe_R"] - win["R"]).median()), 3)
    row["winners_median_mfe_R"] = round(float(win["mfe_R"].median()), 3)
    if t["clock"].any():
        ck = t[t["clock"] & (t["reason"] == "time")]
        row["clock_exits"] = len(ck)
        row["clock_exits_ahead_ge_1R"] = int(t["ahead_at_clock"].sum())
        row["clock_exits_ahead_mean_R"] = round(float(t.loc[t["ahead_at_clock"], "R"].mean()), 3) if t["ahead_at_clock"].any() else None
    # distributions for the CSV tables
    mae_w = {"sleeve": key, **{f"p{q}": round(float(np.percentile(win["mae_R"], q)), 3) for q in (25, 50, 75, 90, 95)},
             **{f"share_ge_{k}": round(float((win["mae_R"] >= k).mean()), 3) for k in (0.1, 0.25, 0.5, 0.75, 0.9)}}
    mfe_l = {"sleeve": key, **{f"p{q}": round(float(np.percentile(los["mfe_R"], q)), 3) for q in (25, 50, 75, 90, 95)},
             **{f"share_ge_{k}": round(float((los["mfe_R"] >= k).mean()), 3) for k in (0.25, 0.5, 1.0, 1.5, 2.0)}}
    edges = [-np.inf, -1.5, -1.0, -0.9, -0.5, -0.25, 0.0]
    lab = ["<-1.5", "-1.5..-1.0", "-1.0..-0.9", "-0.9..-0.5", "-0.5..-0.25", "-0.25..0"]
    cnt = pd.cut(los["R"], edges, labels=lab, right=True)
    bk = []
    for b in lab:
        sel = cnt == b
        bk.append({"sleeve": key, "bucket_R": b, "n": int(sel.sum()), "sum_R": round(float(los.loc[sel, "R"].sum()), 2),
                   "share_of_gross_loss": round(float(-los.loc[sel, "R"].sum() / gl_), 3) if gl_ else 0})
    return row, mae_w, mfe_l, bk


def main():
    rows, mw, ml, bks = [], [], [], []
    for name, sym in C.TEN:
        r, a, b, c = one(f"{name}:{sym}")
        rows.append(r)
        mw.append(a)
        ml.append(b)
        bks += c
    pd.DataFrame(rows).to_csv(os.path.join(C.OUT, "anatomy_sleeves.csv"), index=False)
    pd.DataFrame(mw).to_csv(os.path.join(C.OUT, "anatomy_mae_winners.csv"), index=False)
    pd.DataFrame(ml).to_csv(os.path.join(C.OUT, "anatomy_mfe_losers.csv"), index=False)
    pd.DataFrame(bks).to_csv(os.path.join(C.OUT, "anatomy_loss_buckets.csv"), index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 60)
    print(pd.DataFrame(rows).T.to_string())
    print(pd.DataFrame(mw).to_string(index=False))
    print(pd.DataFrame(ml).to_string(index=False))


if __name__ == "__main__":
    main()
