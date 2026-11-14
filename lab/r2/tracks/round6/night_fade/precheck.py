"""Pre-check of night_fade (PROTOCOL_V3 Addendum L) BEFORE the run, in sample only: counts and costs, NO return (L31).

- frames: rows, first and last bar, max(ts) < 2022-01-01 (asserted), minutes dropped by the build (data/r6/frames_info.json);
- evenings: the 1,753 calendar evenings (asserted), skipped Monday-Thursday dates by reason, per year;
- warm-up per cross: first tradable evening (480 completed H1 bars at 17:15 New York), tradable evenings per year;
- coverage per cross: share of the 1,753 evenings with an M1 bar starting in [17:15, 21:00) New York (the 90 % rule;
  a cross below 90 % is dropped and listed in 'crosses_kept'), and share of the decision buckets with a bar;
- signals and drops per configuration and cross (decision-table counts, base frame and costs x1.5 rebuilt frame),
  in the order: no signal bar, band not usable, no band crossing, cost filter, late entry, open already at the target,
  stop distance <= 0, exit bar not after the entry bar; orders; one_per_night's later orders;
- spreads (Dukascopy, merged frame) and all-in costs (base frame: spread + commission), close spread of every M1 bar at
  17:15-21:00 and 16:55-17:30 New York on the calendar evenings, median and 90th percentile, pips and bp, by cross and year;
  commission per cross in pips at the median price;
- the clock: decision, entry and exit times in UTC in both daylight-saving regimes and around the switches.
The moving_mid exit, stops, targets and every exit are NOT computed here (no exit of a real trade before the run).
Output: results/r2/round6/night_fade/precheck.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

import time  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

WINDOWS = {"17:15-21:00": (17 * 60 + 15, 21 * 60), "16:55-17:30": (16 * 60 + 55, 17 * 60 + 30)}
CLOCK_EVENINGS = ["2013-02-05", "2013-07-09", "2016-01-12", "2016-06-14", "2019-03-07", "2019-03-11", "2019-10-31",
                  "2019-11-04", "2021-12-22"]


def fmt(ns):
    t = pd.Timestamp(int(ns), unit="ns", tz="UTC")
    return {"utc": t.strftime("%Y-%m-%d %H:%M"), "new_york": t.tz_convert(C.NY).strftime("%Y-%m-%d %H:%M %Z")}


def q(x, p):
    return round(float(np.percentile(x, p)), 4) if len(x) else None


def spreads(merged, base, ev_set):
    """Close spreads of the M1 bars in each window on the calendar evenings, by year: median and p90 in pips and bp."""
    ny = merged.index.tz_convert(C.NY)
    mod = (ny.hour * 60 + ny.minute).to_numpy()
    d = ny.tz_localize(None).normalize()
    on_ev = np.asarray(d.isin(ev_set))
    yr = ny.year.to_numpy()
    mid = ((merged.bc + merged.ac) / 2).to_numpy()
    sp = (merged.ac - merged.bc).to_numpy()
    allin = (base.ac - base.bc).to_numpy()
    out = {}
    for w, (a, b) in WINDOWS.items():
        m = on_ev & (mod >= a) & (mod < b)
        res = {}
        for y in C.YEARS:
            k = m & (yr == y)
            res[int(y)] = {"minutes": int(k.sum()),
                           "spread_pips_median": q(sp[k] / C.PIP, 50), "spread_pips_p90": q(sp[k] / C.PIP, 90),
                           "spread_bp_median": q(sp[k] / mid[k] * 1e4, 50), "spread_bp_p90": q(sp[k] / mid[k] * 1e4, 90),
                           "all_in_pips_median": q(allin[k] / C.PIP, 50), "all_in_pips_p90": q(allin[k] / C.PIP, 90),
                           "all_in_bp_median": q(allin[k] / mid[k] * 1e4, 50), "all_in_bp_p90": q(allin[k] / mid[k] * 1e4, 90)}
        res["all_years"] = {"minutes": int(m.sum()),
                            "spread_pips_median": q(sp[m] / C.PIP, 50), "spread_pips_p90": q(sp[m] / C.PIP, 90),
                            "spread_bp_median": q(sp[m] / mid[m] * 1e4, 50), "spread_bp_p90": q(sp[m] / mid[m] * 1e4, 90),
                            "all_in_pips_median": q(allin[m] / C.PIP, 50), "all_in_pips_p90": q(allin[m] / C.PIP, 90),
                            "all_in_bp_median": q(allin[m] / mid[m] * 1e4, 50), "all_in_bp_p90": q(allin[m] / mid[m] * 1e4, 90)}
        out[w] = res
    return out


def coverage(merged, E):
    """Share of the calendar evenings with at least one M1 bar starting in [17:15, 21:00) New York (timestamps only)."""
    ns = merged.index.as_unit("ns").asi8
    a, b = C.ny_utc_ns(E, "17:15"), C.ny_utc_ns(E, "21:00")
    n_in = np.searchsorted(ns, b, side="left") - np.searchsorted(ns, a, side="left")
    has = n_in > 0
    return has, n_in


def status_counts(tb):
    s = pd.Series(tb.status).value_counts()
    out = {C.STATUS[k]: int(s.get(k, 0)) for k in sorted(C.STATUS)}
    out["decisions"] = int(len(tb))
    out["signals_buy"] = int(((tb.side > 0) & tb.usable).sum())
    out["signals_sell"] = int(((tb.side < 0) & tb.usable).sum())
    out["decision_buckets_with_a_bar_share"] = round(float(tb.has_bar.mean()), 4) if len(tb) else None
    out["orders_by_year"] = {int(y): int(v) for y, v in
                             pd.Series(pd.DatetimeIndex(tb.evening[tb.status == C.ST_ORDER]).year).value_counts().sort_index().items()}
    return out


def clock_rows(bk):
    rows = []
    for d in CLOCK_EVENINGS:
        E = pd.DatetimeIndex([pd.Timestamp(d)])
        t1715, t1955, t2100 = (int(C.ny_utc_ns(E, h)[0]) for h in ("17:15", "19:55", "21:00"))
        ei = int(np.searchsorted(bk.ns, t1715))
        xi = int(bk.exit_at(E, "21:00", 30)[0])
        b17 = int(np.searchsorted(bk.ns, int(C.ny_utc_ns(E, "17:00")[0])))
        rows.append({"evening": d, "weekday": pd.Timestamp(d).day_name(), "summer_time": bool(C.ny_summer([pd.Timestamp(t1715, unit="ns", tz="UTC")])[0]),
                     "decision_17_15": fmt(t1715), "decision_19_55": fmt(t1955), "time_exit_21_00": fmt(t2100),
                     "first_bar_at_or_after_17_00": fmt(bk.ns[b17]) if b17 < len(bk.ns) else None,
                     "first_bar_at_or_after_17_15": fmt(bk.ns[ei]) if ei < len(bk.ns) else None,
                     "exit_index_bar_21_00": fmt(bk.ns[xi]), "in_calendar": bool(pd.Timestamp(d) in C.evenings())})
    return rows


def main(crosses=None):
    t0 = time.time()
    crosses = C.CROSSES if crosses is None else crosses
    val0 = C.sha256(C.VAL_LOG)
    info = json.load(open(os.path.join(C.R6, "frames_info.json")))
    cal = C.calendar()
    E = C.evenings()
    ev_set = set(E)
    out = {"what": "night_fade pre-check (PROTOCOL_V3 Addendum L): counts and costs only, no return computed",
           "calendar": {"candidates_mon_thu_2013_01_01_to_2021_12_30": int(len(cal)),
                        "by_status": {k: int(v) for k, v in cal.status.value_counts().items()},
                        "evenings": int(len(E)), "first": str(E[0].date()), "last": str(E[-1].date()),
                        "per_year": {int(y): int(v) for y, v in pd.Series(E.year).value_counts().sort_index().items()},
                        "skipped_dates": {r: [str(x.date()) for x in cal.evening[cal.status == r]] for r in C.CAL_REASONS}},
           "frames": {}, "warm_up": {}, "coverage": {}, "signals_and_drops": {}, "spreads": {}, "commission": {}, "clock": None}
    assert out["calendar"]["evenings"] == 1753
    for c in crosses:
        merged = C.load_merged(c)
        base = C.assert_is(C.fold_commission(merged, c))
        bk = C.Book(base, c)
        bk15 = C.Book(C.stressed(base, 1.5), c)
        out["frames"][c] = {"rows": int(len(merged)), "first_bar": fmt(merged.index.as_unit("ns").asi8[0]),
                            "last_bar": fmt(merged.index.as_unit("ns").asi8[-1]),
                            "max_ts_before_2022": bool(merged.index.max() < C.CUT), "build": info.get(c)}
        Et = bk.tradable(480)
        out["warm_up"][c] = {"first_tradable_evening": str(Et[0].date()), "tradable_evenings": int(len(Et)),
                             "not_tradable_warm_up": int(len(E) - len(Et)),
                             "tradable_per_year": {int(y): int(v) for y, v in pd.Series(Et.year).value_counts().sort_index().items()}}
        has, n_in = coverage(merged, E)
        out["coverage"][c] = {"evenings_with_a_bar_17_15_21_00": int(has.sum()), "share": round(float(has.mean()), 5),
                              "kept": bool(has.mean() >= 0.90),
                              "evenings_without_a_bar": [str(x.date()) for x in E[~has]][:60],
                              "median_bars_17_15_21_00": float(np.median(n_in))}
        sd = {}
        for cfg in C.CONFIGS:
            p = cfg["params"]
            sd[cfg["name"]] = {"base": status_counts(C.decision_table(bk, p)),
                               "stress_a_rebuilt": status_counts(C.decision_table(bk15, p))}
        out["signals_and_drops"][c] = sd
        out["spreads"][c] = spreads(merged, base, ev_set)
        med = float(((merged.bc + merged.ac) / 2).median())
        out["commission"][c] = {"c_bp_round_trip": C.COMM_BP[c], "median_mid_price": round(med, 5),
                                "c_pips_round_trip_at_median_price": round(C.COMM_BP[c] * 1e-4 * med / C.PIP, 4)}
        if c == crosses[0]:
            out["clock"] = {"cross": c, "rows": clock_rows(bk)}
        print(c, "rows", len(merged), "coverage", out["coverage"][c]["share"], "first tradable",
              out["warm_up"][c]["first_tradable_evening"], "main orders", sd["main"]["base"]["order"],
              "stress-a orders", sd["main"]["stress_a_rebuilt"]["order"], round(time.time() - t0, 1), "s", flush=True)
        del merged, base, bk, bk15
    kept = [c for c in crosses if out["coverage"][c]["kept"]]
    out["crosses_kept"] = kept
    out["crosses_dropped_by_coverage"] = [c for c in crosses if c not in kept]
    out["cross_bars_on_kept"] = {"crosses_positive_needed": (65 * len(kept) + 99) // 100, "of": len(kept)}
    tot = {}
    for cfg in C.CONFIGS:
        tot[cfg["name"]] = {k: {s: int(sum(out["signals_and_drops"][c][cfg["name"]][k][s] for c in crosses))
                                for s in list(C.STATUS.values()) + ["decisions", "signals_buy", "signals_sell"]}
                            for k in ("base", "stress_a_rebuilt")}
    out["signals_and_drops_pooled"] = tot
    out["frames_summary"] = {c: {k: out["frames"][c][k] for k in ("rows", "max_ts_before_2022")} for c in crosses}
    val1 = C.sha256(C.VAL_LOG)
    assert val0 == val1
    out["val_access_log_sha256"] = val1
    out["seconds"] = round(time.time() - t0, 1)
    out["code_sha256"] = C.code_hashes()
    C.jdump(out, os.path.join(C.OUT, "precheck.json"))
    print("kept", kept, "dropped", out["crosses_dropped_by_coverage"])
    print("pooled orders", {k: v["base"]["order"] for k, v in tot.items()})
    return out


if __name__ == "__main__":
    main()
