"""Quick check of the user's claim "a trade that starts hard the wrong way has no chance: cut it at once" (PROTOCOL_V3,
Addendum H, cross-check of the path lens's anatomy). IN SAMPLE ONLY: trades entered before 2022-01-01, price frames read
with a filter that stops at 2021-12-31 (no 2022+ row is ever loaded).

For every in-sample trade of the ten sleeves and every checkpoint t minutes after the fill (trades still open at t):
  open R at t   = the result if the trade were closed at the close of the last bar finished by t, on the quote that closes
                  it (bid for a long, ask for a short), minus the lab's market slippage for an exit;
  rest of trade = official net R of the trade (costs and swaps included) - open R at t.
A positive mean rest in a bucket means that holding the trades of that bucket earned more than cutting them at t; a
negative one means cutting them at t would have paid. One position per sleeve is ignored here (an earlier exit could
free the sleeve for its next signal): the path lens simulates that.

    python3 r2/tracks/autopsy/quick_check/rest_of_trade.py     (from lab/)
"""
import json
import os

import numpy as np
import pandas as pd

LAB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
TRADES = os.path.join(LAB, "results", "r2", "recalc", "trades")
OUT = os.path.join(LAB, "results", "r2", "autopsy", "quick_check")
IS_END = pd.Timestamp("2022-01-01", tz="UTC")
SLEEVES = [("noise30", "us100"), ("ocm4", "us100"), ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd"),
           ("GOLD_FRI_PM", "xauusd"), ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"), ("F1_brk_ridge_filter", "btcusd"),
           ("F1_brk_ridge_filter", "ethusd"), ("nq_btc_follow", "btcusd")]
SLIP_MKT_BP = {"xauusd": 0.3, "us100": 0.2, "btcusd": 0.5, "ethusd": 0.7}      # lab market slippage (brain map simulateur)
CHECKS = (5, 15, 30, 60, 120, 240, 480)
EDGES = (-np.inf, -0.75, -0.5, -0.25, 0.0, 0.25, 0.5, np.inf)
LABELS = ("< -0.75", "-0.75..-0.5", "-0.5..-0.25", "-0.25..0", "0..0.25", "0.25..0.5", "> 0.5")


def frame(sym):
    """In-sample closes only: the filter is applied while reading, so no 2022+ row is loaded."""
    f = pd.read_parquet(os.path.join(LAB, "data", "fp", f"{sym}_m1.parquet"), columns=["bc", "ac"], filters=[("ts", "<", IS_END)])
    assert f.index.max() < IS_END
    return f


def trades(name, sym):
    t = pd.read_parquet(os.path.join(TRADES, f"{name}__{sym}.parquet"))
    t = t[t.entry_time < IS_END].reset_index(drop=True)                     # the cut comes first
    assert (t.entry_time < IS_END).all() and len(t) > 0
    return t


def main():
    rows = []
    for sym in ("us100", "xauusd", "btcusd", "ethusd"):
        f = frame(sym)
        ts = f.index.values.astype("datetime64[ns]").astype("int64")
        bc, ac = f.bc.to_numpy(), f.ac.to_numpy()
        slip = SLIP_MKT_BP[sym] * 1e-4
        for name, s in SLEEVES:
            if s != sym:
                continue
            t = trades(name, sym)
            ent = t.entry_time.values.astype("datetime64[ns]").astype("int64")
            ext = t.exit_time.values.astype("datetime64[ns]").astype("int64")
            # exits after 2021-12-31 would need 2022 bars: such trades are dropped for the checkpoints they cannot reach
            last_ts = ts[-1]
            for c in CHECKS:
                at = ent + c * 60 * 10**9
                k = np.searchsorted(ts, at, side="left") - 1                  # last bar that started before entry + t: closed by t
                open_ = (ext > at) & (k >= 0) & (at <= last_ts)
                side = t.side.to_numpy()
                px = np.where(side > 0, bc[np.clip(k, 0, None)] * (1 - slip), ac[np.clip(k, 0, None)] * (1 + slip))
                r_cut = side * (px - t.entry.to_numpy()) / t.risk.to_numpy()
                for i in np.flatnonzero(open_):
                    rows.append((f"{name}_{sym}", sym, c, float(r_cut[i]), float(t.R.iat[i]), int(pd.Timestamp(ent[i]).year)))
        del f
    d = pd.DataFrame(rows, columns=["sleeve", "sym", "check_min", "r_open", "r_final", "year"])
    d["rest"] = d.r_final - d.r_open
    d["bucket"] = pd.cut(d.r_open, EDGES, labels=LABELS)
    d.to_parquet(os.path.join(OUT, "checkpoints.parquet"))
    out = {"what": __doc__.strip().splitlines()[0], "checkpoints_min": list(CHECKS), "buckets_R": list(LABELS), "pooled": {}, "by_sleeve": {}, "cut_rules": {}}
    for c in CHECKS:
        g = d[d.check_min == c].groupby("bucket", observed=False)
        out["pooled"][str(c)] = {str(b): {"n": int(len(x)), "mean_rest_R": round(float(x.rest.mean()), 3) if len(x) else None,
                                          "share_ending_in_gain": round(float((x.r_final > 0).mean()), 3) if len(x) else None,
                                          "years_with_positive_rest": int((x.groupby("year").rest.mean() > 0).sum()) if len(x) else 0,
                                          "years": int(x.year.nunique())} for b, x in g}
    for sl, x in d.groupby("sleeve"):
        out["by_sleeve"][sl] = {}
        for c in CHECKS:
            y = x[x.check_min == c]
            out["by_sleeve"][sl][str(c)] = {str(b): [int(len(z)), round(float(z.rest.mean()), 3) if len(z) else None] for b, z in y.groupby("bucket", observed=False)}
    # the user's rule, as a first look: cut at t every trade whose open result is at or below -x R (gain = what cutting saves)
    for c in (5, 15, 30, 60, 120):
        for x in (0.25, 0.5, 0.75):
            sel = d[(d.check_min == c) & (d.r_open <= -x)]
            per_sleeve = {sl: round(float(-(z.rest).sum()), 1) for sl, z in sel.groupby("sleeve")}
            out["cut_rules"][f"t{c}_x{x}"] = {"trades_cut": int(len(sel)), "R_saved_total": round(float(-sel.rest.sum()), 1),
                                             "R_saved_per_trade_cut": round(float(-sel.rest.mean()), 3) if len(sel) else None,
                                             "winners_killed": int((sel.r_final > 0).sum()), "per_sleeve": per_sleeve}
    json.dump(out, open(os.path.join(OUT, "summary.json"), "w"), indent=1)
    n_tr = d[d.check_min == CHECKS[0]].shape[0]
    print("trades at the first checkpoint:", n_tr)
    for c in CHECKS:
        p = out["pooled"][str(c)]
        print(f"t={c:3d} min | " + " | ".join(f"{b}: n {v['n']:4d} rest {v['mean_rest_R'] if v['mean_rest_R'] is not None else float('nan'):+.3f} R, "
                                              f"end in gain {v['share_ending_in_gain'] if v['share_ending_in_gain'] is not None else float('nan'):.2f}, yrs+ {v['years_with_positive_rest']}/{v['years']}"
                                              for b, v in p.items()))
    print()
    for k, v in out["cut_rules"].items():
        print(f"{k:10s}: cut {v['trades_cut']:5d} trades, R saved {v['R_saved_total']:+8.1f} ({v['R_saved_per_trade_cut']}), winners killed {v['winners_killed']:4d} | {v['per_sleeve']}")


if __name__ == "__main__":
    main()
