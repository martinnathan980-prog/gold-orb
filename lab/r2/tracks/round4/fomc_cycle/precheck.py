"""Structure check BEFORE any simulation: timestamps and the calendar only (no price, no return is computed).

- in-sample slices: first / last bar, rows;
- NYSE days with no bar at all in the frame (holes);
- NYSE days with no bar starting exactly at 15:55 (and 15:30) New York: what the entry / exit conventions D5 / D6 do;
- calendar: FOMC gaps in NYSE days, number of week trades by label, partial weeks, expected n per configuration.
Output: results/r2/round4/fomc_cycle/precheck.json
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from goldlab.data import entry_index, exit_index, trading_day  # noqa: E402


def clock_check(frame, days, half, hhmm):
    t = C.ny_time(days, hhmm)
    ei = entry_index(frame, t)
    xi = exit_index(frame, t)
    N = len(frame)
    idx = frame.index
    exact = (ei < N) & (idx[np.minimum(ei, N - 1)] == t)
    rows = []
    for k in np.flatnonzero(~exact):
        nxt = idx[ei[k]] if ei[k] < N else None
        rows.append({"day": str(days[k].date()), "half_day": bool(half[k]),
                     "first_bar_at_or_after": str(nxt.tz_convert(C.NY)) if nxt is not None else None,
                     "exit_index_bar": str(idx[xi[k]].tz_convert(C.NY))})
    return {"clock": hhmm, "days": int(len(days)), "days_without_exact_bar": int((~exact).sum()),
            "of_which_half_days": int(sum(r["half_day"] for r in rows)), "list": rows}


def main():
    days_all, half_all = C.nyse_days()
    out = {}
    for sym, start in (("us500", "2013-01-02"), ("ger40", "2013-10-01")):
        fr = C.load_is(sym)
        sel = days_all >= pd.Timestamp(start)
        days, half = days_all[sel], half_all[sel]
        td = trading_day(fr.index)
        cnt = pd.Series(1, index=td).groupby(level=0).size()
        n_bars = cnt.reindex(days).fillna(0).astype(int)
        r = {"first_bar_utc": str(fr.index[0]), "last_bar_utc": str(fr.index[-1]), "rows": int(len(fr)),
             "nyse_days_checked": int(len(days)),
             "nyse_days_without_any_bar": [str(d.date()) for d in days[n_bars.to_numpy() == 0]],
             "nyse_days_with_fewer_than_600_bars": [str(d.date()) for d in days[(n_bars.to_numpy() > 0) & (n_bars.to_numpy() < 600)]]}
        r["clock_1555"] = clock_check(fr, days, half, "15:55")
        if sym == "us500":
            r["clock_1530"] = clock_check(fr, days, half, "15:30")
        out[sym] = r
        del fr
    # calendar structure (no price)
    pos = days_all.get_indexer(C.FOMC)
    gaps = np.diff(pos)
    out["calendar"] = {"fomc_days_in_sample": int(len(C.FOMC)), "first": str(C.FOMC[0].date()), "last": str(C.FOMC[-1].date()),
                       "all_are_nyse_days": bool((pos >= 0).all()),
                       "gap_nyse_days": {"min": int(gaps.min()), "median": float(np.median(gaps)), "max": int(gaps.max()),
                                         "counts": {int(k): int(v) for k, v in zip(*np.unique(gaps, return_counts=True))}}}
    struct = {}
    for name, s, mode, wm1 in (("main", 0, "both", 0), ("n_shift_p1", 1, "both", 0), ("n_wm1_short", 0, "both", -1),
                               ("diag_long_even", 0, "long_even", 0)):
        lab = C.day_labels(days_all, C.FOMC, s)
        b = C.blocks(lab, C.side_map(mode, wm1))
        b = b[b.first_day >= pd.Timestamp("2013-01-02")]
        inside = b[~b.truncated]
        struct[name] = {"week_trades": int(len(b)), "cut_by_end_of_sample": int(b.truncated.sum()),
                        "by_label": {w: int(v) for w, v in inside.wlabel.value_counts().sort_index().items()},
                        "partial_weeks": int((inside.n_days < 5).sum()),
                        "n_days_counts": {int(k): int(v) for k, v in inside.n_days.value_counts().sort_index().items()},
                        "long": int((inside.side > 0).sum()), "short": int((inside.side < 0).sum())}
    out["calendar"]["week_trades"] = struct
    C.jdump(out, os.path.join(C.OUT, "precheck.json"))
    for sym in ("us500", "ger40"):
        r = out[sym]
        print(sym, r["first_bar_utc"], r["last_bar_utc"], r["rows"], "holes:", r["nyse_days_without_any_bar"][:20],
              "short days:", r["nyse_days_with_fewer_than_600_bars"][:20])
        for ck in ("clock_1555", "clock_1530"):
            if ck in r:
                print("  ", ck, r[ck]["days_without_exact_bar"], "of", r[ck]["days"], "half days:", r[ck]["of_which_half_days"])
                for row in r[ck]["list"][:60]:
                    print("     ", row)
    print(out["calendar"])


if __name__ == "__main__":
    main()
