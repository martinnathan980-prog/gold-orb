"""Part 1 -- anatomy of the in-sample trades of the ten sleeves (description, no selection).

Every in-sample trade (the official set, rebuilt in s0) is followed minute by minute from its fill to its exit, on
the quote that would close it (bid for a long, ask for a short), in R of its initial risk:
  * MAE / MFE (deepest adverse / best favourable open result) and when they occur;
  * losers never ahead by 0.25 R, what the losers gave back, how far against them the winners went;
  * the expectancy of the REST of the trade given its state at a checkpoint (5, 15, 30, 60, 120 minutes after the
    fill and 10 %, 25 %, 50 % of its planned life).  State = open result at the close of the last bar closed at the
    checkpoint, in 7 buckets.  Rest = final net R of the trade minus the net R it would have made if closed at the
    open of the next bar (computed by the lab engine itself: same order, exit_i = that bar, FP costs, swap).
    rest > 0: holding was worth more than cutting; rest < 0: cutting would have paid.

Periods: common window 2018-02-01 .. 2021-12-31 (main) and, separately, the earlier in-sample years where a frame
has them.  FP costs.  Output in results/r2/autopsy/path/.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


def q(x, p):
    return round(float(np.quantile(x, p)), 3) if len(x) else None


def exc_stats(d):
    """Excursion statistics of a group of trades (one sleeve, one period, winners or losers or all)."""
    if len(d) == 0:
        return {"n": 0}
    o = {"n": int(len(d)), "mean_R": round(float(d.R.mean()), 4),
         "mae_mean": round(float(d.mae.mean()), 3), "mae_median": q(d.mae, .5), "mae_p25": q(d.mae, .25),
         "mae_p10": q(d.mae, .10),
         "mfe_mean": round(float(d.mfe.mean()), 3), "mfe_median": q(d.mfe, .5), "mfe_p75": q(d.mfe, .75),
         "mfe_p90": q(d.mfe, .90),
         "t_mae_min_median": q(d.t_mae, .5), "t_mfe_min_median": q(d.t_mfe, .5),
         "t_mae_share_of_life_median": q(d.t_mae / d.life.clip(lower=1), .5),
         "t_mfe_share_of_life_median": q(d.t_mfe / d.life.clip(lower=1), .5),
         "life_min_median": q(d.life, .5), "planned_min_median": q(d.planned, .5),
         "share_mfe_lt_0.25": round(float((d.mfe < 0.25).mean()), 3),
         "share_mfe_ge_0.5": round(float((d.mfe >= 0.5).mean()), 3),
         "share_mfe_ge_1.0": round(float((d.mfe >= 1.0).mean()), 3),
         "share_mae_le_-0.25": round(float((d.mae <= -0.25).mean()), 3),
         "share_mae_le_-0.5": round(float((d.mae <= -0.5).mean()), 3),
         "share_mae_le_-0.75": round(float((d.mae <= -0.75).mean()), 3),
         "giveback_mean": round(float((d.mfe - d.R).mean()), 3), "giveback_median": q(d.mfe - d.R, .5),
         "share_stop_exit": round(float(d.reason.isin(["stop", "trail", "gap"]).mean()), 3)}
    return o


def rest_cells(df, keys):
    """Aggregate the checkpoint rows into cells."""
    g = df.groupby(keys, observed=True)
    out = g.agg(n=("rest", "size"), state_mean=("u", "mean"), final_R_mean=("R", "mean"),
                cut_R_mean=("Rcut", "mean"), rest_mean=("rest", "mean"), rest_sd=("rest", "std"),
                rest_sum=("rest", "sum"), share_final_win=("win", "mean")).reset_index()
    out["rest_t"] = out.rest_mean / (out.rest_sd / np.sqrt(out.n))
    for c in ("state_mean", "final_R_mean", "cut_R_mean", "rest_mean", "rest_sd", "rest_t", "share_final_win"):
        out[c] = out[c].round(4)
    out["rest_sum"] = out["rest_sum"].round(2)
    return out


def main():
    t_start = time.time()
    per_trade, ck_rows, closed_rows = [], [], []
    cur = None
    m1 = leader = None
    for name, sym in C.ORDER:
        t0 = time.time()
        if sym != cur:
            m1 = None
            m1 = C.load_is(sym)
            leader = C.load_is("us100", cols=["bo", "ao", "bc", "ac"]) if sym == "btcusd" else None
            cur = sym
            A = C.arrays(m1)
            ns = C.ns_index(m1)
        o = C.build_orders(name, sym, m1, leader)
        tb = C.sim(m1, o, sym, no_overlap=True)
        # the trade rows are indexed by their order row: the order rows of the official set, in the trades' order,
        # then both renumbered 0..n-1 (simulate() renumbers the orders it is given)
        bo_ = o.loc[tb.index].reset_index(drop=True)
        tb = tb.reset_index(drop=True)
        fi, xi = C.fill_exit_bars(m1, tb)
        mae, mfe, imae, imfe = C.path_stats(A, fi, xi, tb)
        fill_ns = ns[fi]
        plan_ns = C.planned_end_ns(name, m1, bo_, fill_ns)
        side = tb.side.to_numpy(np.int64)
        entry, risk = tb.entry.to_numpy(float), tb.risk.to_numpy(float)
        R = tb.R.to_numpy(float)
        period = np.where(tb.entry_time >= C.COMMON_START, "2018-2021", "pre-2018")
        pt = pd.DataFrame({
            "sleeve": f"{name}:{sym}", "entry_time": tb.entry_time.to_numpy(), "year": tb.entry_time.dt.year.to_numpy(),
            "period": period, "side": side, "R": R, "win": R > 0, "reason": tb.reason.to_numpy(),
            "mae": mae, "mfe": mfe,
            "t_mae": (ns[imae] - fill_ns) / C.MIN_NS, "t_mfe": (ns[imfe] - fill_ns) / C.MIN_NS,
            "life": tb.hold_min.to_numpy(float), "planned": (plan_ns - fill_ns) / C.MIN_NS})
        per_trade.append(pt)
        # ---- checkpoints
        N = len(ns)
        for lab, mins, frac in C.CHECKPOINTS:
            d, tc = C.checkpoint_bars(ns, fill_ns, plan_ns, minutes=mins, frac=frac)
            is_open = (d >= fi) & (d < xi) & (d + 1 < N)
            dd = np.clip(d, 0, N - 1)
            u = C.open_result(A, dd, side, entry, risk)
            oc = bo_.copy()
            ex = oc["exit_i"].to_numpy(np.int64)
            new = np.where(ex >= 0, np.minimum(ex, dd + 1), dd + 1)
            oc["exit_i"] = np.where(is_open, new, ex)
            tcut = C.sim(m1, oc, sym, no_overlap=False).sort_index()
            assert len(tcut) == len(tb) and (tcut.index == tb.index).all()
            assert (tcut.entry_time.to_numpy() == tb.entry_time.to_numpy()).all()
            Rcut = tcut.R.to_numpy(float)
            # trades closed before the checkpoint keep their own result (Rcut == R)
            assert np.allclose(Rcut[~is_open], R[~is_open], rtol=0, atol=1e-12)
            rows = pd.DataFrame({"sleeve": f"{name}:{sym}", "period": period, "year": pt.year.to_numpy(),
                                 "entry_time": pt.entry_time.to_numpy(),
                                 "checkpoint": lab, "u": u, "R": R, "Rcut": Rcut, "rest": R - Rcut,
                                 "win": R > 0, "open": is_open})
            closed_rows.append(rows[~rows.open])
            rows = rows[rows.open].copy()
            rows["bucket"] = pd.Categorical(np.array(C.BUCKETS)[np.digitize(rows.u.to_numpy(), C.BUCKET_EDGES, right=True)],
                                            categories=C.BUCKETS, ordered=True)
            ck_rows.append(rows)
        print(f"{name:20s} {sym:7s} trades {len(tb):5d} [{time.time() - t0:.1f}s]", flush=True)
    pt = pd.concat(per_trade, ignore_index=True)
    ck = pd.concat(ck_rows, ignore_index=True)
    cl = pd.concat(closed_rows, ignore_index=True)
    ck["checkpoint"] = pd.Categorical(ck.checkpoint, categories=[c[0] for c in C.CHECKPOINTS], ordered=True)
    cl["checkpoint"] = pd.Categorical(cl.checkpoint, categories=[c[0] for c in C.CHECKPOINTS], ordered=True)
    pt.to_parquet(os.path.join(C.RES, "anatomy_trades.parquet"))
    ck.to_parquet(os.path.join(C.RES, "anatomy_checkpoints.parquet"))

    # ---- excursion tables
    ex_rows = []
    for (sl, per), d in pt.groupby(["sleeve", "period"], sort=False):
        for grp, dd in (("all", d), ("winners", d[d.win]), ("losers", d[~d.win])):
            ex_rows.append({"sleeve": sl, "period": per, "group": grp, **exc_stats(dd)})
    for per, d in pt.groupby("period"):
        for grp, dd in (("all", d), ("winners", d[d.win]), ("losers", d[~d.win])):
            ex_rows.append({"sleeve": "ALL_TEN", "period": per, "group": grp, **exc_stats(dd)})
    ex = pd.DataFrame(ex_rows)
    ex.to_csv(os.path.join(C.RES, "anatomy_excursions.csv"), index=False)

    # ---- rest-of-trade tables
    rest = rest_cells(ck, ["sleeve", "period", "checkpoint", "bucket"])
    ck_all = ck.copy()
    ck_all["sleeve"] = "ALL_TEN"
    rest_all = rest_cells(ck_all, ["sleeve", "period", "checkpoint", "bucket"])
    rest = pd.concat([rest, rest_all], ignore_index=True)
    rest.to_csv(os.path.join(C.RES, "anatomy_rest.csv"), index=False)
    # the two lowest buckets together ("hard the wrong way": at or below -0.5 R)
    deep = ck[ck.u <= -0.5].copy()
    deep["bucket"] = "<=-0.5"
    deep_all = deep.copy()
    deep_all["sleeve"] = "ALL_TEN"
    rest_deep = pd.concat([rest_cells(deep, ["sleeve", "period", "checkpoint", "bucket"]),
                           rest_cells(deep_all, ["sleeve", "period", "checkpoint", "bucket"])], ignore_index=True)
    rest_deep.to_csv(os.path.join(C.RES, "anatomy_rest_deep.csv"), index=False)
    # by year, common window
    rest_y = rest_cells(ck[ck.period == "2018-2021"], ["sleeve", "checkpoint", "bucket", "year"])
    rest_y.to_csv(os.path.join(C.RES, "anatomy_rest_by_year.csv"), index=False)
    deep_y = rest_cells(deep[deep.period == "2018-2021"], ["sleeve", "checkpoint", "bucket", "year"])
    deep_y.to_csv(os.path.join(C.RES, "anatomy_rest_deep_by_year.csv"), index=False)
    # closed before the checkpoint
    clo = cl.groupby(["sleeve", "period", "checkpoint"], observed=True).agg(
        n_closed=("R", "size"), closed_mean_R=("R", "mean"), closed_share_win=("win", "mean")).reset_index()
    clo.to_csv(os.path.join(C.RES, "anatomy_closed_before_checkpoint.csv"), index=False)
    print(f"done [{time.time() - t_start:.0f}s]")


if __name__ == "__main__":
    main()
