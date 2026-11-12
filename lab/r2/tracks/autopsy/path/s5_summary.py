"""Builds results/r2/autopsy/path/summary.json: every table reported by the path lens, the per-sleeve verdict on
the user's claim, the variants with their criteria, the candidates and the truncation tests.  Also writes
results/r2/autopsy/path/anatomy_loss_composition.csv and verdicts.csv.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

EARLY = ["5m", "15m", "30m", "60m", "10%", "25%"]


def records(df):
    return json.loads(df.to_json(orient="records"))


def loss_composition(tr):
    def f(d):
        L, W = d[d.R <= 0], d[d.R > 0]
        stop = L.reason.isin(["stop", "trail", "gap"])
        top = W.R.sort_values(ascending=False).head(max(1, int(len(W) * 0.1)))
        return pd.Series({
            "n": len(d), "n_losers": len(L), "sum_loss_R": round(L.R.sum(), 2), "sum_win_R": round(W.R.sum(), 2),
            "share_of_loss_from_stop_exits": round(L.R[stop].sum() / L.R.sum(), 3) if L.R.sum() < 0 else None,
            "n_stop_losers": int(stop.sum()), "avg_stop_loss_R": round(L.R[stop].mean(), 3) if stop.any() else None,
            "avg_time_exit_loss_R": round(L.R[~stop].mean(), 3) if (~stop).any() else None,
            "share_losers_at_or_below_-0.9R": round((L.R <= -0.9).mean(), 3),
            "top_10pct_winners_share_of_gross_win": round(top.sum() / W.R.sum(), 3),
            "payoff_ratio": round(W.R.mean() / -L.R.mean(), 3)})
    rows = []
    for per, dp in tr.groupby("period"):
        for sl, d in dp.groupby("sleeve"):
            rows.append({"sleeve": sl, "period": per, **f(d).to_dict()})
        rows.append({"sleeve": "ALL_TEN", "period": per, **f(dp).to_dict()})
    return pd.DataFrame(rows)


FIRST = ["5m", "15m", "30m", "60m", "120m"]


def first_in(d, mask):
    """Each trade once: the first of the checkpoints 5, 15, 30, 60, 120 min (in time order) at which it is still
    open and its state satisfies the mask; the rest is measured from that checkpoint."""
    x = d[mask].copy()
    x["k"] = x.checkpoint.astype(str).map({c: i for i, c in enumerate(FIRST)})
    return x.sort_values("k").drop_duplicates("entry_time", keep="first")


def verdicts(ck):
    """The user's claim, per sleeve: does the rest of a trade that is 'hard the wrong way' early lose (cutting pays)
    or earn (cutting destroys value)?  Each trade counted once per state class (first checkpoint where it is in it)."""
    out = []
    for (sl, per), d in ck[ck.checkpoint.isin(FIRST)].groupby(["sleeve", "period"], observed=True):
        deep = first_in(d, d.u <= -0.5)
        mild = first_in(d, (d.u > -0.5) & (d.u <= -0.25))
        flat = first_in(d, (d.u > -0.25) & (d.u <= 0.25))
        row = {"sleeve": sl, "period": per}
        for lab, x in (("deep_le_-0.5", deep), ("mild_-0.5_-0.25", mild), ("flat_-0.25_0.25", flat)):
            row[f"{lab}_cases"] = int(len(x))
            row[f"{lab}_rest_mean"] = round(float(x.rest.mean()), 4) if len(x) else None
            row[f"{lab}_rest_t"] = round(float(x.rest.mean() / (x.rest.std(ddof=1) / np.sqrt(len(x)))), 2) if len(x) > 2 else None
        out.append(row)
    v = pd.DataFrame(out)

    def say(r):
        def word(m, t):
            if m is None or t is None or not np.isfinite(t):
                return "too few cases"
            if m < 0 and t <= -2:
                return "cutting would have paid"
            if m > 0 and t >= 2:
                return "cutting would have destroyed value"
            return "no clear effect"
        return (f"{r.sleeve} ({r.period}), each trade once, at the first of the checkpoints 5/15/30/60/120 min where "
                f"it is in the class: state <= -0.5 R: {r['deep_le_-0.5_cases']} trades, rest {r['deep_le_-0.5_rest_mean']:+.3f} R "
                f"(t {r['deep_le_-0.5_rest_t']}) -> {word(r['deep_le_-0.5_rest_mean'], r['deep_le_-0.5_rest_t'])}; "
                f"-0.5..-0.25 R: {r['mild_-0.5_-0.25_cases']} trades, rest {r['mild_-0.5_-0.25_rest_mean']:+.3f} R "
                f"(t {r['mild_-0.5_-0.25_rest_t']}) -> {word(r['mild_-0.5_-0.25_rest_mean'], r['mild_-0.5_-0.25_rest_t'])}; "
                f"-0.25..+0.25 R: {r['flat_-0.25_0.25_cases']} trades, rest {r['flat_-0.25_0.25_rest_mean']:+.3f} R "
                f"(t {r['flat_-0.25_0.25_rest_t']}) -> {word(r['flat_-0.25_0.25_rest_mean'], r['flat_-0.25_0.25_rest_t'])}")
    v["statement"] = [say(r) if r["deep_le_-0.5_cases"] > 0 else f"{r.sleeve} ({r.period}): no trade at or below -0.5 R"
                      for _, r in v.iterrows()]
    return v


def main():
    R = C.RES
    base = json.load(open(os.path.join(R, "baseline.json")))
    dec = json.load(open(os.path.join(R, "declared.json")))
    tr = pd.read_parquet(os.path.join(R, "anatomy_trades.parquet"))
    ck = pd.read_parquet(os.path.join(R, "anatomy_checkpoints.parquet"))
    lc = loss_composition(tr)
    lc.to_csv(os.path.join(R, "anatomy_loss_composition.csv"), index=False)
    vd = verdicts(ck)
    vd.to_csv(os.path.join(R, "verdicts.csv"), index=False)
    crit = pd.read_csv(os.path.join(R, "criteria.csv"))
    trunc = json.load(open(os.path.join(R, "truncation.json"))) if os.path.exists(os.path.join(R, "truncation.json")) else {}
    vb = json.load(open(os.path.join(R, "variants_baseline.json")))
    t1 = trunc.get("test1", {})
    t1_tot = sum(c["orders_tested"] for s in t1.values() for c in s.values())
    t1_mis = sum(c["mismatches"] for s in t1.values() for c in s.values())
    cands = crit[crit.pass_a_to_e].copy()
    cand_list = []
    for sl, g in cands.groupby("sleeve"):
        g = g.sort_values(["total_change", "stress_total_change"], ascending=False)
        for rank, (_, r) in enumerate(g.iterrows(), 1):
            t2 = trunc.get("test2", {}).get(r.id, {})
            cand_list.append({"id": r.id, "sleeve": sl, "rank_for_its_sleeve": rank,
                              "f_truncation_test1_all_decisions_identical": t1_mis == 0,
                              "f_truncation_test2": {k: t2.get(k) for k in ("trades_tested", "identical", "fired_tested",
                                                                             "not_fired_tested")},
                              **{k: (r[k] if not isinstance(r[k], (np.integer, np.floating, np.bool_)) else r[k].item())
                                 for k in crit.columns}})
    out = {
        "lens": "path -- what a trade shows after its entry (PROTOCOL_V3, Addendum H), in sample only",
        "in_sample_guard": "price frames read with a pyarrow filter ts < 2022-01-01 (no later row materialised); official "
                           "trades read with entry_time < 2022-01-01 in the same statement; every rule run on that slice "
                           "(us100 leader of nq_btc_follow registered from its own in-sample slice); nothing 2026, no "
                           "holdout file opened",
        "windows": {"common": "entries 2018-02-01 .. 2021-12-31 (criteria)", "pre": "earlier in-sample entries, reported apart"},
        "costs": "FP (r2.costs, frame as stored); x1.5 = spread x1.5 around the mid + slippages x1.5, orders rebuilt",
        "baseline_reproduction": base,
        "anatomy": {
            "excursions": records(pd.read_csv(os.path.join(R, "anatomy_excursions.csv"))),
            "loss_composition": records(lc),
            "rest_of_trade": records(pd.read_csv(os.path.join(R, "anatomy_rest.csv"))),
            "rest_of_trade_state_le_-0.5": records(pd.read_csv(os.path.join(R, "anatomy_rest_deep.csv"))),
            "rest_of_trade_state_le_-0.5_by_year": records(pd.read_csv(os.path.join(R, "anatomy_rest_deep_by_year.csv"))),
            "rest_of_trade_by_year": records(pd.read_csv(os.path.join(R, "anatomy_rest_by_year.csv"))),
            "first_order_cut_below": records(pd.read_csv(os.path.join(R, "anatomy_cut_below.csv"))),
            "closed_before_checkpoint": records(pd.read_csv(os.path.join(R, "anatomy_closed_before_checkpoint.csv"))),
            "verdicts": records(vd),
            "definitions": {
                "state": "open result in R at the close of the last bar closed at the checkpoint, on the quote that "
                         "would close the trade (bid long / ask short), before exit slippage and swap",
                "rest": "final net R minus the net R of closing at the open of the next bar (lab engine, same order, "
                        "exit_i = that bar, FP costs and swap): > 0 holding was worth more than cutting",
                "mae_mfe": "deepest adverse / best favourable open result over the bars held from open to close, the "
                           "exit price being the last point; times in minutes from the fill",
                "planned_life": "scheduled time exit - fill time (noise30: 15:55 New York)"}},
        "rules": {"declared": dec, "n_trials": int(len(crit)), "baseline_for_variants": vb,
                  "variants": records(crit), "candidates_pass_a_to_e": cand_list,
                  "truncation": {"test1_orders_x_checkpoints_tested": t1_tot, "test1_mismatches": t1_mis,
                                 "test1_per_sleeve": t1, "test2": trunc.get("test2", {})}},
    }
    C.jdump(out, os.path.join(R, "summary.json"))
    print("summary.json written; candidates:", [c["id"] for c in cand_list], "| truncation test1", t1_tot, "mismatches", t1_mis)


if __name__ == "__main__":
    main()
