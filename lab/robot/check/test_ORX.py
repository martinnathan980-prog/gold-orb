"""T4 gold clock ORX (step G): orb_asia_2d_buf10, every decision and every trade of 2013-2021 against the lab.

    python3 -I lab/robot/check/test_ORX.py [--no-sanitize] [--fresh]

The EA, its private tree and the in-sample replay are test_GFP.py's (imported; the replay is cached and shared). The lab:
ref_lab.one("ORX") on the rebuilt and the official frames, and the lab's make_orders and r2.run on the rebuilt frame
and on the kept frame (the rebuilt frame without the 20 gold bars the EA's mask drops), each in a fresh process (P8),
plus the lab's own per-day range table (_local_times, _range_stats on every London weekday) and sessions().
Checks:
  1. Decisions. Every lab order (the first touch of a London weekday's 07:00-12:00 window) has the EA order of the same
     bar (oid = bar start x 100 + 10): same side, stop entry at the same level and absolute stop at the other level (bit
     for bit: the range, the buffer and the levels use the lab's own expressions on the same bars), window and expiry =
     that bar, exit = the first bar at or after 16:00 New York on BusinessDays(London date, 2) (checked against pandas
     BDay and zoneinfo too), no gap rule. No EA order without a lab order. The orders decided by the tie rule (both
     levels in one bar) are counted. Every DEC info line (a range that is not valid) matches the lab's range table
     (fewer than 210 bars, with the same count, or no width), and every invalid lab range with a window bar has one.
  2. Trades: the journal's paper trades against r2.run's: entry and exit minute, side, reason and the three prices
     equal (every ORX price comes from bars); compare.cmp_trades (rel 1e-12) as well; trades open at the frame end left
     out. Against the kept and the rebuilt frames (the mask of 2012-12-31 does not reach ORX).
  3. The lab on the rebuilt frame against the official trades: each difference listed with its cause.
  4. Unit worlds (test_GFP.py's generated C++ program): OrxExitTime on every London weekday of 2012-2035 against pandas
     BDay(2) and zoneinfo, LatestExit, and synthetic bar worlds against the lab's make_orders: 209 and 210 range bars, a
     flat range, both levels in one bar (nearer the top, nearer the bottom, an exact tie), a touch on the 07:00 bar,
     Thursday and Friday exits, the US/UK summer-time gap weeks, weekend dates.
  5. The sanitizer build writes a byte-identical journal (test_GFP's replay), the unit program gives the same answers.
  6. The holes world (test_GFP.hole_cuts: short London ranges, empty entry windows, cut touch bars, holes after a fill
     and around a 16:00 exit, random holes): checks 1 and 2 against the lab's code on the same holed bars; DEC info
     lines must appear for the short ranges, exits must move past 16:00, stops must be hit through a gap.
Outputs: check/out/test_G/test_ORX.json.
"""
import argparse
import json
import os
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import compare  # noqa: E402
import test_GFP as G  # noqa: E402

LDN, NY = G.LDN, G.NY
CODE = "ORX"
EXPECT = {"et": 1, "xg": 0, "ref": 0, "vle": 0, "xh": 0, "ax": 0, "sd": 0.0, "tr": 0.0, "be": 0.0, "tg": 0.0, "td": 0.0, "lv2": 0.0}


def ldn_date(t):
    return str(G.utc(t).tz_convert(LDN).date())


def orx_exit_utc(ldn_day):
    """16:00 New York on (London date + BDay(2)), the lab's own way (pandas offsets, zoneinfo), UTC seconds"""
    xd = pd.Timestamp(ldn_day) + pd.offsets.BDay(2)
    return int((xd + pd.Timedelta(hours=16)).tz_localize(NY).tz_convert("UTC").value // 10**9)


def orx_decisions(rows, lab_o, days, touch, idx, label):
    ea = G.dec_rows(rows, CODE, "ord")
    info = G.dec_rows(rows, CODE, "info")
    res = {"frame": label, "lab_orders": int(len(lab_o)), "ea_orders": int(len(ea)), "ea_info_lines": int(len(info))}
    dup = int(ea.oid.duplicated().sum()) if len(ea) else 0
    ea = ea.drop_duplicates("oid", keep="last").copy()
    ea["xbar"] = G.first_at_or_after(idx, ea.x.to_numpy(np.int64))
    ea["act"] = G.act_bar(idx, ea.tf.to_numpy(np.int64), ea.tt.to_numpy(np.int64))
    ea["expbar"] = G.last_before(idx, ea.exp.to_numpy(np.int64))
    ea["ldn"] = [ldn_date(t) for t in ea.tf]
    own = {"window_one_bar": int((ea.tf != ea.tt).sum()), "expiry_bar_plus_60": int((ea.exp != ea.tf + 60).sum()),
           "oid": int((ea.oid != ea.tf * 100 + G.SID[CODE]).sum()), "dec": int((ea.utc != ea.tf).sum()),
           "exit_16:00_bday2_pandas": int((ea.x != np.array([orx_exit_utc(d) for d in ea.ldn])).sum()),
           "in_window_weekday": int(sum(not (pd.Timestamp(G.utc(t)).tz_convert(LDN).dayofweek < 5
                                             and 420 <= pd.Timestamp(G.utc(t)).tz_convert(LDN).hour * 60
                                             + pd.Timestamp(G.utc(t)).tz_convert(LDN).minute < 720) for t in ea.tf))}
    fields = {k: int((ea[k] != v).sum()) for k, v in EXPECT.items()}
    lab = lab_o.reset_index(drop=True).copy()
    lab["entry_s"] = G.tsecs(lab.entry_t)
    lab["exit_s"] = G.tsecs(lab.exit_t)
    lab["oid"] = lab.entry_s * 100 + G.SID[CODE]
    L, E = lab.set_index("oid"), ea.set_index("oid")
    both = L.index.intersection(E.index)
    only_lab = sorted(int(x) for x in L.index.difference(E.index))
    only_ea = sorted(int(x) for x in E.index.difference(L.index))
    Lb, Eb = L.loc[both], E.loc[both]
    eq = {"side": Lb.side.to_numpy() == Eb.side.to_numpy(), "level": Lb.level.to_numpy() == Eb.lv.to_numpy(),
          "stop": Lb.stop.to_numpy() == Eb.st.to_numpy(), "entry_bar": Lb.entry_s.to_numpy() == Eb.act.to_numpy(),
          "expiry_bar": Lb.entry_s.to_numpy() == Eb.expbar.to_numpy(), "exit_bar": Lb.exit_s.to_numpy() == Eb.xbar.to_numpy()}
    wrong = []
    for k, o in enumerate(both):
        bad = [n for n, v in eq.items() if not v[k]]
        if bad:
            wrong.append({"oid": int(o), "bar": G.ny_str(int(o) // 100), "fields": bad,
                          "level": [float(Lb.level.iloc[k]), float(Eb.lv.iloc[k])], "stop": [float(Lb.stop.iloc[k]), float(Eb.st.iloc[k])]})
    # the tie rule (both levels reached in the touch bar)
    tb = touch.set_index("entry_t")
    tie = tb[tb.both]
    tie_ok = int(sum(int(E.loc[t * 100 + G.SID[CODE]].side) == int(r.side) for t, r in tie.iterrows() if t * 100 + G.SID[CODE] in E.index))
    # the range verdicts: DEC info lines against the lab's per-day table
    D = days.set_index("date")
    inf_rows = []
    for _, r in info.iterrows():
        d = ldn_date(int(r.utc))
        lr = D.loc[d] if d in D.index else None
        code, v2 = int(r.v1), float(r.v2)
        if lr is None:
            ok = False
        elif code == 1:
            ok = int(lr.nbars) < 210 and v2 == float(lr.nbars) and int(lr.window_bar_t) == int(r.utc)
        elif code == 2:
            ok = int(lr.nbars) >= 210 and not (float(lr.width) > 0) and int(lr.window_bar_t) == int(r.utc)
        else:
            ok = False
        inf_rows.append({"date": d, "code": code, "v2": v2, "lab_nbars": None if lr is None else int(lr.nbars), "ok": bool(ok)})
    info_days = set(x["date"] for x in inf_rows)
    lab_invalid_with_bar = [d for d, r in D.iterrows() if not bool(r.valid) and int(r.window_bar_t) > 0 and int(r.window_bar_t) >= int(idx[0])]
    missing_info = sorted(set(lab_invalid_with_bar) - info_days)
    ea_days_not_valid = sorted(set(ea.ldn) - set(D.index[D.valid]))
    res.update({"matched": int(len(both)), "duplicates": dup, "own_fields_wrong": own,
                "fields_not_as_expected": {k: v for k, v in fields.items() if v}, "wrong": wrong[:20], "n_wrong": len(wrong),
                "level_bit_equal": int(eq["level"].sum()), "stop_bit_equal": int(eq["stop"].sum()),
                "only_lab": only_lab[:20], "n_only_lab": len(only_lab), "only_ea": only_ea[:20], "n_only_ea": len(only_ea),
                "tie_rule_orders": int(len(tie)), "tie_rule_same_side": tie_ok,
                "lab_days": int(len(D)), "lab_valid_days": int(D.valid.sum()), "info_lines": inf_rows,
                "invalid_lab_days_with_window_bar": len(lab_invalid_with_bar), "invalid_days_without_info_line": missing_info,
                "ea_order_on_invalid_day": ea_days_not_valid})
    res["pass"] = (dup == 0 and not any(own.values()) and not res["fields_not_as_expected"] and not wrong and not only_lab
                   and not only_ea and tie_ok == len(tie) and all(x["ok"] for x in inf_rows) and not missing_info
                   and not ea_days_not_valid and len(both) > 0)
    return res


def orx_trades(rows, lab_t, t_first, t_last, label):
    ea = compare.paper_trades(rows, CODE)
    lab = G.window(lab_t, t_first, t_last)
    ea_w = ea[ea.entry_time >= G.utc(t_first)] if len(ea) else ea
    tr = G.trade_rows(ea_w, lab, price_exact=("entry", "stop", "exit"), price_rel=())
    diffs = [r for r in tr if r["bad"]]
    cmp = compare.cmp_trades(rows, lab_t, CODE, t_from=t_first, t_to=t_last, rel=G.REL)
    fills = set(r["oid"] for r in rows if r["code"] == CODE and r["ev"] == "PFILL")
    done, void = compare.paper_chain(rows, CODE)
    res = {"frame": label, "lab_trades": int(len(lab)), "ea_trades": int(len(ea_w)), "differences": diffs, "compare_cmp_trades": cmp,
           "reasons_lab": lab.reason.value_counts().to_dict(), "open_at_end_ea": len(fills - set(done) - set(void)),
           "lab_trades_left_out_open_at_end": int(len(lab_t) - len(lab))}
    res.update(G.trade_stats(ea_w, lab))
    res["pass"] = not diffs and cmp["pass"] and res["matched"] == len(lab) > 0
    return res


# ======================================================================================== unit worlds
def orx_day(day, n_range=420, hi=1652.0, lo=1648.0, window=(), spread=0.2, flat=False, all_window=False, seed=0):
    """one London weekday: n_range range bars from 00:00 London (max ask high = hi, min bid low = lo, or a flat range
    bid = ask = lo), then the window bars given as (London minute, bo, bh, bl, bc) with ask = bid + spread, or (all_window)
    a quiet walk over 07:00-11:59 that touches nothing unless window bars replace minutes of it"""
    rng = np.random.default_rng(seed)
    rows = []
    d0 = pd.Timestamp(day).tz_localize(LDN)
    mid = (hi + lo - spread) / 2
    for k in range(n_range):
        t = d0 + pd.Timedelta(minutes=k)
        if flat:
            rows.append((t, lo, lo, lo, lo, 0.0))
            continue
        b = round(mid + float(rng.uniform(-0.5, 0.5)), 2)
        bh, bl = b + 0.05, b - 0.05
        if k == 0:
            bl = lo
        if k == 1:
            bh = round(hi - spread, 2)
        rows.append((t, b, round(bh, 2), round(bl, 2), b, spread))
    win = {m: (bo, bh, bl, bc) for m, bo, bh, bl, bc in window}
    mins = range(420, 720) if all_window else sorted(win)
    for m in mins:
        t = d0 + pd.Timedelta(minutes=m)
        if m in win:
            bo, bh, bl, bc = win[m]
        else:
            b = round(mid + float(rng.uniform(-0.3, 0.3)), 2)
            bo, bh, bl, bc = b, round(b + 0.05, 2), round(b - 0.05, 2), b
        rows.append((t, bo, bh, bl, bc, spread))
    idx = pd.DatetimeIndex([r[0] for r in rows]).tz_convert("UTC")
    df = pd.DataFrame({"bo": [r[1] for r in rows], "bh": [r[2] for r in rows], "bl": [r[3] for r in rows], "bc": [r[4] for r in rows]},
                      index=idx.rename("ts"))
    sp = np.array([r[5] for r in rows])
    for k in "ohlc":
        df["a" + k] = np.round(df["b" + k].to_numpy() + sp, 2)
    return df[["bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"]]


def tail_bars(start, end):
    """a quiet gold tail (one bar a minute) so that the exits two business days later find bars"""
    t = pd.date_range(pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC"), freq="min", inclusive="left")
    b = 1650.0 + 0.0 * np.arange(len(t))
    df = pd.DataFrame({"bo": b, "bh": b + 0.05, "bl": b - 0.05, "bc": b}, index=pd.DatetimeIndex(t, name="ts"))
    for k in "ohlc":
        df["a" + k] = np.round(df["b" + k] + 0.2, 2)
    return df[["bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"]]


def world(days, tail_to):
    parts = list(days)
    last = max(p.index.max() for p in parts) + pd.Timedelta(minutes=1)
    parts.append(tail_bars(str(last.tz_convert("UTC").tz_localize(None)), tail_to))
    m1 = pd.concat(parts).sort_index()
    assert m1.index.is_unique
    return m1


def orx_unit():
    res = {}
    exe, warn = G.unit_exe()
    res["build_warnings"] = warn
    # 1. OrxExitTime on every London weekday of 2012-2035
    a, b = G.ny_utc("2012-01-02", "09:00"), G.ny_utc("2035-12-31", "09:00")
    got = [ln.split() for ln in G.unit(["orxexit", a, b]).splitlines() if ln.startswith("OX")]
    bad = []
    for p in got:
        d = str(pd.Timestamp(int(p[1]), unit="s").date())
        if int(p[2]) != orx_exit_utc(d):
            bad.append({"date": d, "got": int(p[2]), "want": orx_exit_utc(d)})
    n_wd = int(sum(1 for d in pd.date_range("2012-01-02", "2035-12-31") if d.dayofweek < 5))
    res["exit_2012_2035"] = {"weekdays": len(got), "expected": n_wd, "wrong": bad[:10], "pass": not bad and len(got) == n_wd}
    # 2. LatestExit: the London date of the open; the comment only cross-checks
    qs, want = [], []
    for d in pd.date_range("2013-01-07", "2021-12-31", freq="B")[::5]:
        ds = str(d.date())
        x = orx_exit_utc(ds)
        t7 = int(pd.Timestamp(f"{ds} 07:00").tz_localize(LDN).tz_convert("UTC").value // 10**9)
        for o, c in ((t7 + 60, t7), (t7 + 4 * 3600 + 59 * 60 + 60, 0), (t7 + 2 * 3600, t7 - 86400), (t7 + 600, t7 + 3600)):
            qs.append(f"{o} {c}")
            want.append(x)
    gl = [int(ln.split()[3]) for ln in G.unit(["latest", "orx"], stdin="\n".join(qs) + "\n").splitlines() if ln.startswith("LATEST")]
    res["latest_exit"] = {"queries": len(qs), "wrong": int(sum(g != w for g, w in zip(gl, want))), "pass": gl == want}
    # 3. synthetic bar worlds against the lab's make_orders (levels: H 1652, L 1648, W 4, buffer 0.4 -> 1652.4 / 1647.6;
    #    bid + 0.2 = ask, so a bid high of 1652.2 reaches the upper level)
    up = (1650.0, 1652.25, 1649.9, 1652.1)                   # ask high 1652.45 >= 1652.4
    dn = (1648.1, 1648.2, 1647.55, 1647.7)                    # bid low 1647.55 <= 1647.6
    worlds = {
        "normal": world([orx_day("2013-01-07", window=[(430, *up)], all_window=True, seed=1),
                         orx_day("2013-01-08", window=[(501, *dn)], all_window=True, seed=2),
                         orx_day("2013-01-09", all_window=True, seed=3)], "2013-01-12 00:00"),
        "bars209": world([orx_day("2013-01-07", n_range=209, window=[(420, 1650.0, 1650.1, 1649.9, 1650.0), (450, *up)]),
                          orx_day("2013-01-08", n_range=210, window=[(450, *up)])], "2013-01-11 00:00"),
        "flat": world([orx_day("2013-01-07", flat=True, window=[(425, *up)])], "2013-01-10 00:00"),
        "both": world([orx_day("2013-01-07", window=[(440, 1651.9, 1652.3, 1647.5, 1651.0)]),     # mid open 1652.0: nearer the top
                       orx_day("2013-01-08", window=[(440, 1647.9, 1652.3, 1647.5, 1650.0)]),     # mid open 1648.0: nearer the bottom
                       orx_day("2013-01-09", window=[(440, 1649.9, 1652.3, 1647.5, 1650.0)])],    # mid open 1650.0: a tie, long
                      "2013-01-12 00:00"),
        "first07": world([orx_day("2013-01-07", window=[(420, *up), (421, *dn)])], "2013-01-10 00:00"),
        "thufri": world([orx_day("2013-01-10", window=[(600, *up)]), orx_day("2013-01-11", window=[(700, *dn)])], "2013-01-16 00:00"),
        "dst": world([orx_day("2013-03-11", window=[(450, *up)]), orx_day("2013-03-29", window=[(450, *dn)]),
                      orx_day("2013-10-28", window=[(450, *up)]), orx_day("2013-10-31", window=[(450, *dn)])], "2013-11-06 00:00"),
        "weekend": world([orx_day("2013-01-05", window=[(450, *up)]), orx_day("2013-01-06", window=[(450, *dn)]),
                          orx_day("2013-01-07", window=[(719, *up)])], "2013-01-10 00:00"),
        "late": world([orx_day("2013-01-07", window=[(720, *up)]), orx_day("2013-01-08", window=[(719, *dn), (720, *up)])],
                      "2013-01-11 00:00"),
    }
    wpath = os.path.join(G.OUT, "unit", "orx_worlds.txt")
    os.makedirs(os.path.dirname(wpath), exist_ok=True)
    G.write_worlds(worlds, wpath)
    ea = G.parse_world_out(G.unit(["worlds", "orx", wpath]))
    lab = G.lab_synth(CODE, worlds)
    expect_info = {"bars209": [(1.0, 209.0)], "flat": [(2.0, 0.0)]}
    expect_n = {"normal": 2, "bars209": 1, "flat": 0, "both": 3, "first07": 1, "thufri": 2, "dst": 4, "weekend": 1, "late": 1}
    wres = {}
    for w, m1 in worlds.items():
        e = ea.get(w, {"ord": [], "info": []})
        idx = G.secs(m1.index)
        lo = {r["entry_t"]: r for r in lab[w]}
        rows, ok = [], True
        for o in e["ord"]:
            r = lo.pop(o["tf"], None)
            xb = int(G.first_at_or_after(idx, [o["x"]])[0])
            row = {"bar": G.ny_str(o["tf"]), "ldn_bar": str(G.utc(o["tf"]).tz_convert(LDN))[:16], "side": o["side"], "level": o["lv"],
                   "stop": o["st"], "exit": G.ny_str(o["x"])}
            if r is None:
                row["lab"] = "no order"
                row["ok"] = False
            else:
                row["ok"] = (o["side"] == r["side"] and o["et"] == r["etype"] == 1 and o["lv"] == r["level"] and o["st"] == r["stop"]
                             and o["tf"] == o["tt"] == r["entry_t"] and o["exp"] == o["tf"] + 60 and r["expiry_t"] == r["entry_t"]
                             and xb == r["exit_t"] and o["xg"] == 0 and o["x"] == orx_exit_utc(ldn_date(o["tf"])))
            ok &= row["ok"]
            rows.append(row)
        inf = [(i["v1"], i["v2"]) for i in e["info"]]
        ok &= not lo and inf == expect_info.get(w, []) and len(e["ord"]) == expect_n[w]
        wres[w] = {"ea_orders": rows, "ea_info": e["info"], "lab_orders": len(lab[w]), "lab_only": sorted(lo), "pass": bool(ok)}
    sides = [r["side"] for r in wres["both"]["ea_orders"]]
    wres["both"]["pass"] &= sides == [1, -1, 1]
    res["bar_worlds"] = wres
    res["pass"] = not warn and res["exit_2012_2035"]["pass"] and res["latest_exit"]["pass"] and all(v["pass"] for v in wres.values())
    return res


def orx_holes(sanitize, fresh):
    """the holes world (test_GFP.hole_cuts): the EA on the gold bars with holes cut against the lab on the same bars"""
    hw = G.holes_run(False, fresh)
    rows = hw["rows"]
    info, lf = G.lab_run(CODE, "holes_kept")
    idx = G.secs(G.read_frame(G.frame_path("holes_kept")).index)
    t_first, t_last = G.first_minute(rows), int(idx[-1]) - 1
    dec = orx_decisions(rows, lf["orders"], lf["days"], lf["touch"], idx, "holes")
    trd = orx_trades(rows, lf["trades"], t_first, t_last, "holes")
    lt = G.window(lf["trades"], t_first, t_last)
    xt = lt[lt.reason == "time"]
    ss = 1.0e-4                                                    # fp_costs.json slip_stop_bps 1.0 for gold
    st = lt[lt.reason == "stop"]
    through = ((st.side > 0) & (st.exit < st.stop * (1 - ss) - 1e-9)) | ((st.side < 0) & (st.exit > st.stop * (1 + ss) + 1e-9))
    cov = {"range_info_lines": sum(1 for x in dec["info_lines"] if x["code"] == 1),
           "time_exit_not_16:00": int(sum(str(pd.Timestamp(t).tz_convert(NY))[11:16] != "16:00" for t in xt.exit_time)),
           "stop_through_a_gap": int(through.sum())}
    res = {"world": {k: hw["world"][k] for k in ("cuts", "bars_removed", "removed_by_kind")}, "replay": hw["out"], "wall_s": hw["wall"],
           "s0_contract": G.s0_contract(rows), "lab": {k: info[k] for k in ("bars", "orders", "trades", "R_sum", "valid_days")},
           "decisions": dec, "trades": trd, "coverage": cov}
    res["pass"] = bool(dec["pass"] and trd["pass"] and all(v > 0 for v in cov.values()) and res["s0_contract"]["pass"])
    G.log(f"[holes] orders lab {dec['lab_orders']} EA {dec['ea_orders']} matched {dec['matched']} wrong {dec['n_wrong']} only lab "
          f"{dec['n_only_lab']} only EA {dec['n_only_ea']} | info lines {len(dec['info_lines'])} (all match the lab's range table: "
          f"{all(x['ok'] for x in dec['info_lines'])}), missing {len(dec['invalid_days_without_info_line'])} | trades lab "
          f"{trd['lab_trades']} EA {trd['ea_trades']} matched {trd['matched']} differences {len(trd['differences'])} | coverage {cov} | "
          f"{'PASS' if res['pass'] else 'FAIL'}")
    if sanitize:
        hs = G.holes_run(True, fresh)
        res["sanitizer"] = {"build_warnings": hs["warnings"], "wall_s": hs["wall"], "journal_identical": hs["identical"]}
        res["pass"] = bool(res["pass"] and hs["identical"] and not hs["warnings"])
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-sanitize", action="store_true")
    ap.add_argument("--fresh", action="store_true")
    a = ap.parse_args(argv)
    t0 = time.time()
    res = {"test": "T4/T5 ORX orb_asia_2d_buf10 (step G)"}
    ok = True
    reb_info, reb_o, reb_t = G.ref_lab_one(CODE, "rebuilt")
    off_info, off_o, off_t = G.ref_lab_one(CODE, "official")
    lab = {k: G.lab_run(CODE, k) for k in ("rebuilt", "kept")}
    same_ref = lab["rebuilt"][1]["trades"].reset_index(drop=True).equals(reb_t.reset_index(drop=True))
    res["lab"] = {"ref_lab_rebuilt": {k: reb_info[k] for k in ("orders", "trades", "R_sum", "reasons")},
                  "ref_lab_official": {k: off_info[k] for k in ("orders", "trades", "R_sum")},
                  "kept_frame": {k: lab["kept"][0][k] for k in ("bars", "orders", "trades", "R_sum", "days", "valid_days", "both_touched")},
                  "sessions_equal_valid_days": [lab[k][0]["sessions_equal_valid_days"] for k in ("rebuilt", "kept")],
                  "razors_kept_frame": lab["kept"][0]["razors"],
                  "lab_run_rebuilt_equals_ref_lab": bool(same_ref)}
    ok &= same_ref and all(res["lab"]["sessions_equal_valid_days"])
    G.log(f"lab: rebuilt {reb_info['orders']} orders {reb_info['trades']} trades | kept {lab['kept'][0]['orders']} orders "
          f"{lab['kept'][0]['trades']} trades, {lab['kept'][0]['days']} London weekdays, {lab['kept'][0]['valid_days']} valid ranges, "
          f"{lab['kept'][0]['both_touched']} tie-rule orders, {len(lab['kept'][0]['razors'])} razor days (a window bar within 1e-9 "
          f"of a level; the EA computes the levels with the lab's own expressions, so they are decided alike) | official "
          f"{off_info['trades']} trades | lab_run = ref_lab: {same_ref} | "
          f"range table = sessions(): {res['lab']['sessions_equal_valid_days']}")
    ea = G.ea_run(sanitize=not a.no_sanitize, fresh=a.fresh)
    rows = ea["rows"]
    res["replay"] = {"stdout": ea["out"], "wall_s": ea["wall"], "build_warnings": ea["warnings"]}
    res["s0_contract"] = G.s0_contract(rows)
    ok &= not ea["warnings"] and res["s0_contract"]["pass"]
    t_first, t_last = G.first_minute(rows), G.manifest_last()["XAUUSD.r"] - 1
    idx = {"kept": G.secs(G.read_frame(G.frame_path("kept")).index), "rebuilt": G.secs(G.read_frame(G.frame_path("rebuilt")).index)}
    for kind, lo, lt in (("kept", lab["kept"][1]["orders"], lab["kept"][1]["trades"]), ("rebuilt", reb_o, reb_t)):
        dec = orx_decisions(rows, lo, lab[kind][1]["days"], lab[kind][1]["touch"], idx[kind], kind)
        trd = orx_trades(rows, lt, t_first, t_last, kind)
        res[kind] = {"decisions": dec, "trades": trd, "pass": bool(dec["pass"] and trd["pass"])}
        ok &= res[kind]["pass"]
        G.log(f"[{kind}] orders lab {dec['lab_orders']} EA {dec['ea_orders']} matched {dec['matched']} wrong {dec['n_wrong']} only lab "
              f"{dec['n_only_lab']} only EA {dec['n_only_ea']} | level/stop bit-equal {dec['level_bit_equal']}/{dec['stop_bit_equal']} | "
              f"tie rule {dec['tie_rule_same_side']}/{dec['tie_rule_orders']} | info lines {len(dec['info_lines'])}, invalid lab ranges with "
              f"a window bar {dec['invalid_lab_days_with_window_bar']}, missing info {len(dec['invalid_days_without_info_line'])} | "
              f"own fields {dec['own_fields_wrong']}")
        G.log(f"[{kind}] trades lab {trd['lab_trades']} EA {trd['ea_trades']} (open at the end {trd['open_at_end_ea']}) matched "
              f"{trd['matched']} entry/stop/exit bit-equal {trd['entry_bit_equal']}/{trd['stop_bit_equal']}/{trd['exit_bit_equal']} | "
              f"differences {len(trd['differences'])} | cmp_trades pass {trd['compare_cmp_trades']['pass']} | "
              f"{'PASS' if res[kind]['pass'] else 'FAIL'}")
    od = G.official_diff(CODE, reb_t)

    def by_date(o):
        return {str(pd.Timestamp(d).date()): {"touch_bar": str(G.utc(t))[:16], "side": int(sd), "level": float(lv), "stop": float(st)}
                for d, t, sd, lv, st in zip(o.date, G.tsecs(o.entry_t), o.side, o.level, o.stop)}
    off_d, reb_d = by_date(off_o), by_date(reb_o)
    for r in od["differences"]:
        if "cause" in r:
            continue
        d = str(pd.Timestamp(r["entry_time"]).tz_convert(LDN).date())
        r["cause"] = (f"the export rounds the bid to 2 digits (SPEC 7): the London range and its levels move, so the touch bar, "
                      f"the fill or the stop-out differ (London date {d}: official order {off_d.get(d)}, rebuilt order {reb_d.get(d)})")
    res["rebuilt_vs_official"] = od
    G.log(f"rebuilt vs official: official {od['official']} rebuilt {od['rebuilt']} same exit+reason {od['same_exit_and_reason']} "
          f"only official {od['only_official']} only rebuilt {od['only_rebuilt']} max |R| diff {od['max_abs_R_diff']:.3g}")
    res["holes"] = orx_holes(not a.no_sanitize, a.fresh)
    ok &= res["holes"]["pass"]
    res["unit"] = orx_unit()
    ok &= res["unit"]["pass"]
    u = res["unit"]
    G.log(f"unit: exit times {u['exit_2012_2035']['weekdays']} weekdays pass {u['exit_2012_2035']['pass']} | LatestExit "
          f"{u['latest_exit']['queries']} pass {u['latest_exit']['pass']} | bar worlds {[(k, v['pass']) for k, v in u['bar_worlds'].items()]}")
    if not a.no_sanitize:
        s = ea["san"]
        ue, uw = G.unit_exe(True)
        args = ["orxexit", G.ny_utc("2012-01-02", "09:00"), G.ny_utc("2035-12-31", "09:00")]
        same_unit = G.unit(args, sanitize=True) == G.unit(args)
        wpath = os.path.join(G.OUT, "unit", "orx_worlds.txt")
        same_w = G.unit(["worlds", "orx", wpath], sanitize=True) == G.unit(["worlds", "orx", wpath])
        res["sanitizer"] = {"build_warnings": s["warnings"], "stdout": s["out"], "wall_s": s["wall"], "journal_identical": s["identical"],
                            "unit_build_warnings": uw, "unit_identical": bool(same_unit and same_w)}
        ok &= s["identical"] and not s["warnings"] and not uw and same_unit and same_w
        G.log(f"sanitizer: warnings {len(s['warnings'])} journal identical {s['identical']} ({s['wall']} s) | unit identical "
              f"{same_unit and same_w}")
    res["journal_counts"] = G.counts(rows, CODE)
    res["pass"] = bool(ok)
    res["sec"] = round(time.time() - t0, 1)
    G.write("test_ORX.json", res)
    G.log(f"test_ORX: {'PASS' if ok else 'FAIL'} ({res['sec']} s) -> check/out/test_G/test_ORX.json")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
