"""Step 1 (rule 2): reproduce the official in-sample trades of the ten sleeves from the in-sample slice.

For each sleeve: base orders of the frozen rule on the in-sample frame (FP costs, one position per sleeve), then a
trade-by-trade comparison with the rows of results/r2/recalc/trades/<name>__<sym>.parquet whose entry is before
2022-01-01 (filter applied while reading).  Trades still open at the end of the in-sample frame are identified from
OUR simulation (censored) and left out of both sides: their result needs 2022 prices.
Output: results/r2/autopsy/payoff/reproduce.json
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

BY_SYM = {"us100": ["noise30", "ocm4"], "btcusd": ["brk72_24h_wd", "F1_brk_ridge_filter", "nq_btc_follow"],
          "ethusd": ["brk72_24h_wd", "F1_brk_ridge_filter"], "xauusd": ["GOLD_FRI_PM", "donch4h_stop", "orb_asia_2d_buf10"]}


def compare(name, sym, m1):
    t0 = time.time()
    o = C.build_orders(name, sym, m1)
    t = C.sim(m1, o, sym, stress=False)
    cens = C.censored(m1, t, sym)
    off = C.load_official(name, sym)
    mine = t[~cens]
    cen_t = t[cens]
    key = lambda d: list(zip(d.entry_time.dt.as_unit("ns").astype("int64"), d.side))
    k_c = set(key(cen_t))
    off_k = key(off)
    keep_off = np.array([k not in k_c for k in off_k])
    off_kept = off[keep_off]
    a = mine.assign(k=key(mine)).set_index("k")
    b = off_kept.assign(k=key(off_kept)).set_index("k")
    common = a.index.intersection(b.index)
    diff = {}
    for c in ("entry", "exit", "stop", "pnl", "R"):
        diff[c] = float(np.nanmax(np.abs(a.loc[common, c].to_numpy() - b.loc[common, c].to_numpy()))) if len(common) else None
    same_exit_time = bool((a.loc[common, "exit_time"].values == b.loc[common, "exit_time"].values).all())
    same_reason = bool((a.loc[common, "reason"].values == b.loc[common, "reason"].values).all())
    win = C.window(mine, "common")
    win_off = C.window(off_kept, "common")
    res = {
        "official_rows_before_2022": int(len(off)),
        "censored_in_sample": int(cens.sum()),
        "censored_entry_times": [str(x) for x in cen_t.entry_time],
        "official_rows_compared": int(len(off_kept)), "ours": int(len(mine)),
        "matched": int(len(common)), "only_official": int(len(b.index.difference(a.index))),
        "only_ours": int(len(a.index.difference(b.index))),
        "max_abs_diff": diff, "same_exit_time": same_exit_time, "same_reason": same_reason,
        "total_R_official_compared": round(float(off_kept.R.sum()), 4), "total_R_ours": round(float(mine.R.sum()), 4),
        "common_window": {"official_n": int(len(win_off)), "ours_n": int(len(win)),
                          "official_total_R": round(float(win_off.R.sum()), 4), "ours_total_R": round(float(win.R.sum()), 4)},
        "first_entry": str(mine.entry_time.min()), "frame_start": str(m1.index[0]), "frame_end": str(m1.index[-1]),
        "orders": int(len(o)), "skipped": int(t.attrs.get("skipped", -1)), "nofill": int(t.attrs.get("nofill", -1)),
        "seconds": round(time.time() - t0, 1),
    }
    res["reproduced"] = bool(res["matched"] == res["official_rows_compared"] == res["ours"]
                             and abs(res["total_R_official_compared"] - res["total_R_ours"]) < 1e-6
                             and same_exit_time and same_reason)
    return res


def main():
    out = {}
    lead = None
    for sym in ("us100", "btcusd", "ethusd", "xauusd"):
        m1 = C.load_is(sym)
        if sym == "us100":
            lead = ((m1["bc"] + m1["ac"]) / 2).rename("mid")
        if sym == "btcusd":
            C.set_leader_is(lead)
        for name in BY_SYM[sym]:
            r = compare(name, sym, m1)
            out[f"{name}:{sym}"] = r
            print(f"{name:22s} {sym}: official {r['official_rows_before_2022']} censored {r['censored_in_sample']} "
                  f"ours {r['ours']} matched {r['matched']} totR off {r['total_R_official_compared']:.4f} "
                  f"ours {r['total_R_ours']:.4f} maxdiff R {r['max_abs_diff']['R']} -> {r['reproduced']} "
                  f"[{r['seconds']}s]", flush=True)
        del m1
    json.dump(out, open(os.path.join(C.OUT, "reproduce.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
