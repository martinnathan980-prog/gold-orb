"""Step 1: reproduce the reported in-sample numbers with the lab engine, save the IS trades, and take a first look
at the M1 frame conventions (index, duplicates, open-vs-previous-close, hour completeness)."""
import time

from common import *  # noqa

out = {}
for sym in SYMS:
    t0 = time.time()
    m1 = r2.load(sym)
    idx = m1.index
    d = {"rows": int(len(m1)), "first": str(idx[0]), "last": str(idx[-1]), "tz": str(idx.tz),
         "monotonic_strict": bool(idx.is_monotonic_increasing and idx.is_unique),
         "second_or_ms_offsets": int((idx.second != 0).sum() + (idx.microsecond != 0).sum())}
    # ---- engine reproduction (IS only)
    orders = S.make_orders(m1, **PARAMS)
    t = gl.simulate(m1, orders, sym=sym, costs=r2.costs(sym), no_overlap=True)
    ti = gl.cut(t, "is")
    rep = report(ti)
    d["engine_is"] = {k: rep[k] for k in ("n", "pf", "t_stat", "expectancy_R", "years_pos", "long_R", "short_R", "avg_hold_h",
                                            "max_hold_h", "max_dd_R", "win_rate", "by_year_R", "exit_reasons")}
    d["engine_is_bps"] = round(float((ti.pnl / ti.entry).mean() * 1e4), 2)
    d["orders_total"] = int(len(orders))
    d["orders_is"] = int((orders.dec_time < IS_END).sum())
    ti.to_pickle(os.path.join(HERE, f"engine_is_trades_{sym}.pkl"))
    orders[orders.dec_time < IS_END].to_pickle(os.path.join(HERE, f"engine_is_orders_{sym}.pkl"))
    # ---- M1 conventions (IS rows only for the descriptive part)
    mi = m1[m1.index < IS_END]
    ts = S.ts_ms(mi)
    dt = np.diff(ts) // 60000
    consec = dt == 1
    mo = ((mi.bo + mi.ao) / 2).to_numpy()
    mc = ((mi.bc + mi.ac) / 2).to_numpy()
    eq_open_prev_close = (mo[1:] == mc[:-1])[consec]
    d["is_rows"] = int(len(mi))
    d["consecutive_minute_pairs"] = int(consec.sum())
    d["share_open_equals_prev_close(mid)"] = round(float(eq_open_prev_close.mean()), 4)
    d["median_abs_open_minus_prev_close_bp"] = round(float(np.median(np.abs(mo[1:] / mc[:-1] - 1)[consec]) * 1e4), 3)
    # hour completeness by year
    hs = ts // 3_600_000
    first = np.r_[0, np.flatnonzero(np.diff(hs)) + 1]
    last = np.r_[first[1:] - 1, len(ts) - 1]
    cnt = last - first + 1
    hstart = pd.to_datetime(hs[first] * 3_600_000, unit="ms", utc=True)
    first_min = (ts[first] // 60000) % 60
    last_min = (ts[last] // 60000) % 60
    hb = pd.DataFrame({"y": hstart.year, "cnt": cnt, "first_min": first_min, "last_min": last_min,
                       "gap_prev_h": np.r_[1, np.diff(hs[first])]})
    d["h1_by_year"] = {int(y): {"bars": int(len(g)), "full60": round(float((g.cnt == 60).mean()), 3),
                                "cnt_lt_30": int((g.cnt < 30).sum()), "cnt_lt_10": int((g.cnt < 10).sum()),
                                "first_row_not_min0": round(float((g.first_min != 0).mean()), 4),
                                "last_row_not_min59": round(float((g.last_min != 59).mean()), 4),
                                "bars_after_gap(>1h)": int((g.gap_prev_h > 1).sum()),
                                "hours_in_year_missing": int((g.gap_prev_h - 1).sum())} for y, g in hb.groupby("y")}
    # spread of the FP frame at IS and in bp (context)
    spr = ((mi.ac - mi.bc) / ((mi.ac + mi.bc) / 2) * 1e4)
    d["fp_spread_bp_by_year_median"] = {int(y): round(float(v), 2) for y, v in spr.groupby(mi.index.year).median().items()}
    out[sym] = d
    print(sym, json.dumps(d, indent=1), f"[{time.time() - t0:.0f}s]", flush=True)
    del m1, mi, t, ti, orders
    r2.free()
dump(out, "s01_reproduce.json")
