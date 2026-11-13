"""T2 data: CR_Bars and CR_Math (SPEC 8 step B) against pandas and the lab code on in-sample data, plain and sanitizer builds.

    python3 -I lab/robot/check/test_bars.py [--quick] [--no-sanitize]

Builds check/test_bars.cpp (the translated src/CR_Bars.mqh and src/CR_Math.mqh with the S0 clock double) and checks:
  1. primitives: CrRollSum (sum, mean, valid count), CrRollMax/Min, CrRollMedian, CrWilder, CrMedian and CrRing on random
     series (NaN gaps, repeated values, one sign, mixed magnitudes, ties) and in-sample series (gold hour true ranges, BTC
     minute squared returns over 28,800 minutes, US100 daily moves, BTC hour closes) against pandas: within 1e-12 relative
     (the counts of exact equality are reported);
  2. store: the 2013-2021 bars of the four symbols replayed through the store minute by minute as CR_Main does: every fed
     bar equals the rebuilt lab frame (check/out/frames/<sym>_is.parquet) bit for bit, in (time, symbol id) order, at the
     first barrier after its start, and the bars kept are exactly those an independent pandas copy of SPEC 2.2's mask
     keeps (per reason counts equal);
  3. h = 3 points: synthetic raw gold bars (raw bid = lab bid + 3 points, raw spread = lab spread - 6 points, clipped at 0)
     through a build with CR_XAU_COMM_PTS=6: the paper quotes equal the lab frame wherever the lab spread is >= 6 points
     (and are bid + 6 points where the raw spread was clipped);
  4. aggregates: CrAgg's UTC hour, 4-hour and trading-day buckets of the kept bars equal goldlab.data.bars (1h, 4h, D),
     goldlab.data.full_days, crypto/strategy.py h1_bars and ml/strategy.py _h1_bid;
  5. the daily cost statistics (BarsCost) equal the pandas medians per server day;
  6. the mock worlds of test_bars.cpp (barrier, missing minute, LATEBAR at most one per 5 min, READY: SERIES_SYNCHRONIZED
     false, a hole that fills, a hole that stays, short and no history, stability; mask on a NYSE and a typed half day);
  7. the sanitizer build (address, undefined behaviour, checked containers): the worlds, the primitives (outputs equal to
     the plain build's, byte for byte) and the 2021 store;
  8. the symbol rows of the test equal CR_Registry.mqh's RegSym rows;
  9. the mask in sample: the kept bars are the rebuilt frames, except gold bars of 17:00-17:59 New York (the xau rule; in
     sample: 20 bars, all on 2012-12-31, the gold frame's first day). Any other dropped bar fails the test. The robot has
     no flat-bar rule (lead decision after step B's finding 1: MT5 makes a bar only when a tick came; on the 2-digit FP
     bid the lab's flat rule dropped 5,969 real in-sample bars), so bid-flat bars are kept.
Outputs: check/out/test_bars/ (result.json; the large streams are never written to disk). In-sample only: frames are
read with ts < 2022-01-01 inside the read call.
"""
import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import time

os.environ.setdefault("NUMBA_CACHE_DIR", "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/numba")
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROBOT = os.path.dirname(HERE)
LAB = os.path.dirname(ROBOT)
OUT = os.path.join(HERE, "out", "test_bars")
CUT = pd.Timestamp("2022-01-01", tz="UTC")
sys.path.insert(0, HERE)
sys.path.insert(0, LAB)
sys.path.insert(0, os.path.join(LAB, "r2", "tracks", "idx_us"))
from build import build  # noqa: E402
from test_s0_script import bars_2021  # noqa: E402

SYMS = [("xauusd", "XAUUSD.r", 0, "XAU"), ("us100", "US100.r", 1, "IDX"), ("btcusd", "BTCUSD.r", 2, "CRY"), ("ethusd", "ETHUSD.r", 3, "CRY")]
REC = np.dtype([("t", "<i8"), ("o", "<i4"), ("h", "<i4"), ("l", "<i4"), ("c", "<i4"), ("s", "<i4")])
FED = np.dtype([("t", "<i8"), ("sym", "<i4"), ("s", "<i4"), ("bo", "<f8"), ("bh", "<f8"), ("bl", "<f8"), ("bc", "<f8"),
                ("ao", "<f8"), ("ah", "<f8"), ("al", "<f8"), ("ac", "<f8")])
AGG = np.dtype([("sym", "<i4"), ("kind", "<i4"), ("key", "<i8"), ("t_first", "<i8"), ("t_last", "<i8"), ("n", "<i4"), ("pad", "<i4"),
                ("bo", "<f8"), ("bh", "<f8"), ("bl", "<f8"), ("bc", "<f8"), ("ao", "<f8"), ("ah", "<f8"), ("al", "<f8"), ("ac", "<f8"),
                ("mh", "<f8"), ("ml", "<f8")])
COST = np.dtype([("sym", "<i4"), ("pad", "<i4"), ("day", "<i8"), ("raw", "<f8"), ("pap", "<f8")])
PRICES = ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac")
REASONS = ("kept", "m_weekend", "m_crypto", "m_idx", "m_xau", "m_half")      # CR_MASK_NAME, in CR_MASK_* order
KEPT, WEEKEND, CRYPTO, IDX, XAU, HALF = range(len(REASONS))                   # CR_MASK_KEPT .. CR_MASK_HALF
TOL = 1e-12


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_test(name, sanitize=False, comm=None):
    defines = [f"CR_XAU_COMM_PTS={comm}"] if comm is not None else []
    exe, warn = build(os.path.join(ROBOT, "src", "CR_Bars.mqh"), name=name, main=os.path.join(HERE, "test_bars.cpp"),
                      subst=["CR_Clock.mqh=" + os.path.join(HERE, "dbl", "CR_Clock_dbl.mqh")], defines=defines, sanitize=sanitize)
    return exe, warn


def read_bin(path):
    with open(path, "rb") as f:
        assert f.read(4) == b"CRB1"
        np.frombuffer(f.read(4), "<i4")
        n = int(np.frombuffer(f.read(8), "<i8")[0])
        return np.frombuffer(f.read(n * REC.itemsize), REC).copy()


def write_bin(path, rec):
    with open(path, "wb") as f:
        f.write(b"CRB1")
        f.write(np.int32(2).tobytes())
        f.write(np.int64(len(rec)).tobytes())
        f.write(rec.tobytes())


def frame(sym, tag):
    m1 = pd.read_parquet(os.path.join(HERE, "out", "frames", f"{sym}_{tag}.parquet"), filters=[("ts", "<", CUT)])
    assert len(m1) and m1.index.max() < CUT and m1.index.is_monotonic_increasing and m1.index.is_unique
    return m1


def secs(idx):
    return pd.DatetimeIndex(idx).tz_convert("UTC").as_unit("s").asi8.astype(np.int64)


def half_days():
    import idxus_lib
    out = set()
    for y in range(2011, 2024):
        out |= set(idxus_lib.us_holidays(y)[1])
    return out


def mask_reasons(rec, fam, halves):
    """SPEC 2.2's mask, written again with pandas (independent of the EA): the first reason of each broker bar (KEPT ..
    HALF, the CR_MASK_* codes), from the bar's server time only (no flat-bar rule)"""
    t = rec["t"]
    n = len(rec)
    srv = pd.DatetimeIndex(pd.to_datetime(t, unit="s"))
    dow = srv.dayofweek.to_numpy()                         # Monday 0 .. Sunday 6
    hm = srv.hour.to_numpy() * 60 + srv.minute.to_numpy()
    ny = srv - pd.Timedelta(hours=7)                       # New York wall clock = server - 7 h
    nym = ny.hour.to_numpy() * 60 + ny.minute.to_numpy()
    r = np.full(n, KEPT, np.int8)
    if fam == "IDX":
        dates = ny.normalize()
        is_half = np.isin(dates.values.astype("datetime64[D]"), np.array(sorted(halves), dtype="datetime64[D]"))
        r[is_half & (nym >= 13 * 60 + 16) & (nym < 18 * 60)] = HALF
        r[(nym >= 16 * 60 + 15) & (nym < 18 * 60)] = IDX
    if fam == "XAU":
        r[(nym >= 17 * 60) & (nym < 18 * 60)] = XAU
    if fam == "CRY":
        r[(dow >= 5) | ((dow == 4) & (hm >= 23 * 60 + 55))] = CRYPTO
    else:
        r[dow >= 5] = WEEKEND
    return r


def run_store(exe, name, files, extra=()):
    d = os.path.join(OUT, name)
    os.makedirs(d, exist_ok=True)
    args = [exe, "store", d] + [f"{k}={v}" for k, v in files.items()] + list(extra)
    t0 = time.time()
    r = subprocess.run(args, capture_output=True, cwd=ROBOT)
    if r.returncode:
        raise RuntimeError(f"store {name} failed ({r.returncode}): {r.stderr.decode()[-3000:]}")
    fed = np.frombuffer(r.stdout, FED)
    with open(os.path.join(d, "summary.json")) as f:
        summ = json.load(f)
    agg = np.fromfile(os.path.join(d, "agg.bin"), AGG)
    cost = np.fromfile(os.path.join(d, "costs.bin"), COST)
    summ["wall_s"] = round(time.time() - t0, 2)
    return fed, summ, agg, cost


def first_diffs(a, b, idx, k=3):
    bad = np.flatnonzero(~idx)[:k]
    return [{"i": int(i), "got": repr(a[i]), "want": repr(b[i])} for i in bad]


def expected(tag, last_utc, halves, only=None):
    """per symbol: the broker bars, the rebuilt frame, the mask reasons; and the expected fed stream"""
    bins = bars_2021(tag)
    sym_data, parts = {}, []
    for name, broker, sid, fam in SYMS:
        if only is not None and broker not in only:
            continue
        rec = read_bin(bins[broker])
        fr = frame(name, tag)
        assert len(fr) == len(rec) and (np.rint(fr["bo"].to_numpy() * 100).astype(np.int64) == rec["o"]).all(), f"{name}: frame and bars differ"
        r = mask_reasons(rec, fam, halves)
        tu = secs(fr.index)
        sym_data[broker] = {"rec": rec, "fr": fr, "r": r, "tu": tu, "sid": sid, "name": name, "fam": fam}
        keep = (r == 0) & (tu < last_utc)
        p = {"t": tu[keep], "sym": np.full(int(keep.sum()), sid, np.int32), "s": rec["s"][keep]}
        for k in PRICES:
            p[k] = fr[k].to_numpy()[keep]
        parts.append(p)
    exp = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    order = np.lexsort((exp["sym"], exp["t"]))
    return sym_data, {k: v[order] for k, v in exp.items()}


def cmp_stream(fed, exp):
    res = {"fed": int(len(fed)), "expected": int(len(exp["t"]))}
    if len(fed) != len(exp["t"]):
        res["pass"] = False
        return res
    bad = {}
    for k in ("t", "sym", "s") + PRICES:
        eq = fed[k] == exp[k]
        if not eq.all():
            bad[k] = {"n": int((~eq).sum()), "first": first_diffs(fed[k], exp[k], eq)}
    res["fields_differing"] = bad
    res["pass"] = not bad
    return res


def check_store(fed, summ, sym_data, exp):
    res = cmp_stream(fed, exp)
    res.update({k: summ[k] for k in ("loads", "latebars", "waits", "order_ok", "contract_ok", "sec", "wall_s")})
    masked = {}
    ok_mask = True
    last_srv = summ["last_event_srv"]
    for broker, sd in sym_data.items():
        taken = sd["rec"]["t"] < last_srv
        cnt = {REASONS[k]: int(((sd["r"] == k) & taken).sum()) for k in range(len(REASONS))}
        base = {"XAUUSD.r": "XAUUSD", "US100.r": "US100", "BTCUSD.r": "BTCUSD", "ETHUSD.r": "ETHUSD"}[broker]
        ea = {k: summ["masked"][base][k] for k in REASONS}
        masked[base] = {"ea": ea, "pandas": cnt, "equal": ea == cnt}
        ok_mask &= ea == cnt
    res["mask"] = masked
    res["pass"] = bool(res["pass"] and ok_mask and summ["order_ok"] == 1 and summ["contract_ok"] == 1 and summ["loads"] == 1
                       and summ["latebars"] == 0 and summ["waits"] == 0)
    return res


def check_costs(cost, sym_data, last_utc, last_srv):
    rows, worst, exact, total, missing = [], 0.0, 0, 0, 0
    last_day = last_srv // 86400 * 86400                               # the run's last server day is never closed
    for broker, sd in sym_data.items():
        rec, fr, r, tu = sd["rec"], sd["fr"], sd["r"], sd["tu"]
        keep = (r == 0) & (tu < last_utc)
        bo, ao = fr["bo"].to_numpy()[keep], fr["ao"].to_numpy()[keep]
        mid = (bo + ao) / 2
        raw = rec["s"][keep] * 0.01 / mid * 1e4
        pap = (ao - bo) / mid * 1e4
        day = rec["t"][keep] // 86400 * 86400
        g = pd.DataFrame({"day": day, "raw": raw, "pap": pap}).groupby("day").median()
        got = cost[cost["sym"] == sd["sid"]]
        gd = pd.DataFrame({"raw": got["raw"], "pap": got["pap"]}, index=got["day"])
        common = g.index.intersection(gd.index)
        missing += int(len(set(g.index.tolist()) - set(gd.index.tolist()) - {last_day}))
        for k in ("raw", "pap"):
            a, b = gd.loc[common, k].to_numpy(), g.loc[common, k].to_numpy()
            exact += int((a == b).sum())
            total += len(a)
            if len(a):
                worst = max(worst, float((np.abs(a - b) / np.abs(b)).max()))
        rows.append({"sym": broker, "days_ea": int(len(gd)), "days_pandas": int(len(g)), "common": int(len(common))})
    return {"per_symbol": rows, "values": total, "exact": exact, "max_rel_diff": worst, "days_missing_besides_last": missing,
            "pass": bool(worst <= TOL and missing == 0 and total > 0)}


def check_aggregates(agg, sym_data):
    import goldlab.data as gd
    crypto = load_module("crypto_strategy", os.path.join(LAB, "r2", "tracks", "crypto", "strategy.py"))
    ml = load_module("ml_strategy", os.path.join(LAB, "r2", "tracks", "ml", "strategy.py"))
    out, ok = {}, True
    for broker, sd in sym_data.items():
        kf = sd["fr"][sd["r"] == 0]
        res = {}
        for kind, rule in ((0, "1h"), (1, "4h"), (2, "D")):
            a = agg[(agg["sym"] == sd["sid"]) & (agg["kind"] == kind)]
            lab = gd.bars(kf, rule)
            if rule == "D":
                keys = lab.index.values.astype("datetime64[s]").astype(np.int64)
            else:
                keys = secs(lab.index)
            pos = pd.Index(keys).get_indexer(a["key"])
            found = pos >= 0
            bad = int((~found).sum())
            p = pos[found]
            aa = a[found]
            diff = {}
            for k in PRICES:
                eq = aa[k] == lab[k].to_numpy()[p]
                if not eq.all():
                    diff[k] = int((~eq).sum())
            tc = secs(lab["t_close"])[p]
            eq_tc = (aa["t_last"] + 60) == tc
            if not eq_tc.all():
                diff["t_close"] = int((~eq_tc).sum())
            emitted = set(a["key"].tolist())
            missing = len(set(keys.tolist()) - emitted - {int(keys[-1])})   # only the last bucket may stay open at the end
            r = {"ea": int(len(a)), "lab": int(len(keys)), "not_in_lab": bad, "missing_besides_last": missing, "fields_differing": diff}
            if rule == "D":
                fd = gd.full_days(kf, 600)
                fkeys = set(fd.index.values.astype("datetime64[s]").astype(np.int64).tolist())
                ea_full = set(a["key"][a["n"] >= 600].tolist())
                r["full_days"] = len(fkeys)
                r["full_days_equal"] = (ea_full == (fkeys & emitted))
                ok &= r["full_days_equal"]
            ok &= bad == 0 and missing == 0 and not diff
            res[rule] = r
        # crypto h1_bars (per-bar mid extremes) and ml _h1_bid (bid bars) on the same kept frame
        a = agg[(agg["sym"] == sd["sid"]) & (agg["kind"] == 0)]
        hb = crypto.h1_bars(kf)
        pos = pd.Index(hb["start"].to_numpy() // 1000).get_indexer(a["key"])
        found = pos >= 0
        p, aa = pos[found], a[found]
        d2 = {}
        for k, v in (("o", (aa["bo"] + aa["ao"]) / 2), ("h", aa["mh"]), ("l", aa["ml"]), ("c", (aa["bc"] + aa["ac"]) / 2), ("cnt", aa["n"])):
            eq = v == hb[k].to_numpy()[p]
            if not eq.all():
                d2[k] = int((~eq).sum())
        r = {"ea": int(len(a)), "lab": int(len(hb)), "not_in_lab": int((~found).sum()), "fields_differing": d2}
        ok &= not d2 and int((~found).sum()) <= 1                       # h1_bars drops the frame's last (incomplete) hour
        res["crypto_h1_bars"] = r
        hbid = ml._h1_bid(kf)
        pos = pd.Index(secs(hbid.index)).get_indexer(a["key"])
        found = pos >= 0
        p, aa = pos[found], a[found]
        d3 = {}
        for k, v in (("o", aa["bo"]), ("h", aa["bh"]), ("l", aa["bl"]), ("c", aa["bc"]), ("nbar", aa["n"])):
            eq = v == hbid[k].to_numpy()[p]
            if not eq.all():
                d3[k] = int((~eq).sum())
        r = {"ea": int(len(a)), "lab": int(len(hbid)), "not_in_lab": int((~found).sum()), "fields_differing": d3}
        ok &= not d3 and int((~found).sum()) == 0
        res["ml_h1_bid"] = r
        out[broker] = res
    out["pass"] = bool(ok)
    return out


# ---------------------------------------------------------------------------------------------------------- primitives
def math_inputs(sym_data_is):
    rng = np.random.default_rng(20261112)
    series, names = [], []

    def add(name, x):
        names.append(name)
        series.append(np.asarray(x, np.float64))

    L = 6000
    x = rng.normal(0, 1, L) * (10.0 ** rng.integers(-3, 6, L))
    x[rng.random(L) < 0.15] = np.nan
    x[1000:1200] = 0.0
    x[2500:2600] = 3.25
    x[4000:4050] = np.nan
    add("random_mixed", x)
    add("random_positive", np.abs(x))
    add("random_negative", -np.abs(x))
    ties = rng.integers(0, 5, L).astype(float)
    ties[rng.random(L) < 0.1] = np.nan
    add("random_ties", ties)
    r = rng.normal(0, 1e-3, 60000)
    v = rng.random(60000) > 0.3
    add("leadlag_sq", np.where(v, r * r, 0.0))
    add("leadlag_cnt", v.astype(float))
    if sym_data_is is not None:
        import goldlab.data as gd
        g = sym_data_is["XAUUSD.r"]
        b = gd.bars(g["fr"][g["r"] == 0], "1h")
        pc = b["c"].shift(1)
        tr = np.maximum(b["h"] - b["l"], np.maximum((b["h"] - pc).abs(), (b["l"] - pc).abs())).to_numpy()
        add("xau_h1_tr", tr)
        btc = sym_data_is["BTCUSD.r"]
        m = btc["fr"][(btc["r"] == 0)]
        m = m[m.index >= pd.Timestamp("2021-01-01", tz="UTC")]
        tmin = secs(m.index) // 60
        grid = np.full(int(tmin[-1] - tmin[0] + 1), np.nan)
        grid[tmin - tmin[0]] = ((m["bc"] + m["ac"]) / 2).to_numpy()
        lr = np.full(len(grid), np.nan)
        lr[1:] = np.log(grid[1:] / grid[:-1])
        ok = np.isfinite(lr)
        add("btc_2021_sq", np.where(ok, lr * lr, 0.0))
        add("btc_2021_ok", ok.astype(float))
        idx = sym_data_is["US100.r"]
        dd = gd.bars(idx["fr"][idx["r"] == 0], "D")
        add("us100_daily_absmove", (dd["c"] / dd["o"] - 1).abs().to_numpy())
        bb = gd.bars(m, "1h")
        add("btc_h1_close", bb["c"].to_numpy())
    return names, series


def math_ops(names, series):
    ops = []
    for sid, (nm, x) in enumerate(zip(names, series)):
        if nm.startswith("random"):
            for n in (1, 2, 3, 14, 20, 24, 72, 280):
                for mp in sorted({0, 1, max(n // 2, 1), max(int(0.7 * n), 1), n}):
                    ops += [(sid, 1, n, mp), (sid, 2, n, mp), (sid, 5, n, mp), (sid, 10, n, mp), (sid, 11, n, mp), (sid, 12, n, mp)]
                ops += [(sid, 3, n, n), (sid, 4, n, n), (sid, 9, n, 1), (sid, 7, n, min(2, n - 1)), (sid, 8, n, min(1, n - 1))]
                if n != 2:
                    ops.append((sid, 6, n, 0))
            ops.append((sid, 6, 2, 0))                                   # com = 1: reported apart (pandas oddity)
        elif nm.startswith("leadlag") or nm.startswith("btc_2021"):
            ops += [(sid, 1, 28800, 1), (sid, 1, 5760, 1), (sid, 2, 28800, 4800)]
        elif nm == "xau_h1_tr":
            ops += [(sid, 2, 14, 14), (sid, 2, 24, 24), (sid, 6, 14, 0), (sid, 6, 24, 0), (sid, 1, 24, 24)]
        elif nm == "us100_daily_absmove":
            ops += [(sid, 2, 14, 9), (sid, 5, 20, 10), (sid, 9, 20, 1)]
        elif nm == "btc_h1_close":
            ops += [(sid, 3, 72, 72), (sid, 4, 72, 72), (sid, 2, 70, 70), (sid, 2, 280, 280), (sid, 3, 280, 280), (sid, 4, 280, 280),
                    (sid, 1, 14, 14)]
    return ops


def pandas_ref(x, code, n, mp):
    s = pd.Series(x)
    if code == 1:
        return s.rolling(n, min_periods=mp).sum().to_numpy()
    if code == 2:
        return s.rolling(n, min_periods=mp).mean().to_numpy()
    if code == 3:
        return s.rolling(n).max().to_numpy()
    if code == 4:
        return s.rolling(n).min().to_numpy()
    if code == 5:
        return s.rolling(n, min_periods=mp).median().to_numpy()
    if code == 6:
        return s.ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()
    if code == 9:
        return s.rolling(n, min_periods=1).median().to_numpy()
    if code == 10:
        return s.rolling(n, min_periods=mp).max().to_numpy()
    if code == 11:
        return s.rolling(n, min_periods=mp).min().to_numpy()
    if code == 12:
        return s.notna().astype(float).rolling(n, min_periods=0).sum().to_numpy()
    i = np.arange(len(x))
    cnt = np.minimum(i + 1, n)
    out = np.full(len(x), np.nan)
    ok = mp < cnt
    if code == 7:                                                      # Last(k): x[i - k]
        out[ok] = x[(i - mp)[ok]]
    elif code == 8:                                                    # Get(k): x[oldest + k]
        out[ok] = x[(i - cnt + 1 + mp)[ok]]
    return out


def run_math(exe, names, series, ops, path_in, path_out):
    with open(path_in, "wb") as f:
        f.write(np.int64(len(series)).tobytes())
        for x in series:
            f.write(np.int64(len(x)).tobytes())
            f.write(np.ascontiguousarray(x, np.float64).tobytes())
        f.write(np.int64(len(ops)).tobytes())
        for op in ops:
            f.write(np.array(op, np.int64).tobytes())
    r = subprocess.run([exe, "math", path_in, path_out], capture_output=True, text=True, cwd=ROBOT)
    if r.returncode:
        raise RuntimeError("math mode failed: " + r.stderr[-2000:])
    raw = np.fromfile(path_out, np.float64)
    outs, k = [], 0
    for op in ops:
        L = len(series[op[0]])
        outs.append(raw[k:k + L])
        k += L
    return outs, raw


CODE_NAME = {1: "sum", 2: "mean", 3: "max", 4: "min", 5: "median", 6: "wilder", 7: "ring_last", 8: "ring_get", 9: "crmedian",
             10: "max_minp", 11: "min_minp", 12: "valid"}


def check_math(names, series, ops, outs):
    agg, worst_all, odd = {}, 0.0, None
    ok = True
    for op, got in zip(ops, outs):
        sid, code, n, mp = op
        ref = pandas_ref(series[sid], code, n, mp)
        ng, nr = np.isnan(got), np.isnan(ref)
        nan_ok = bool((ng == nr).all())
        m = ~ng & ~nr
        exact = int((got[m] == ref[m]).sum())
        tot = int(m.sum())
        rel = float((np.abs(got[m] - ref[m]) / np.maximum(np.abs(ref[m]), 1e-300)).max()) if tot else 0.0
        key = CODE_NAME[code]
        if code == 6 and n == 2:
            odd = {"series": names[sid], "values": tot, "exact": exact, "nan_pattern_equal": nan_ok, "max_rel_diff": rel}
            continue
        a = agg.setdefault(key, {"ops": 0, "values": 0, "exact": 0, "max_rel_diff": 0.0, "nan_pattern_differs": 0})
        a["ops"] += 1
        a["values"] += tot
        a["exact"] += exact
        a["max_rel_diff"] = max(a["max_rel_diff"], rel)
        a["nan_pattern_differs"] += 0 if nan_ok else 1
        worst_all = max(worst_all, rel)
        if not nan_ok or rel > TOL:
            ok = False
            a.setdefault("failing", []).append({"series": names[sid], "n": n, "min_periods": mp, "nan_ok": nan_ok, "max_rel_diff": rel})
    return {"per_primitive": agg, "max_rel_diff": worst_all, "series": names, "ops": len(ops),
            "wilder_n2_pandas_oddity": odd, "pass": bool(ok)}


def check_registry():
    reg = open(os.path.join(ROBOT, "src", "CR_Registry.mqh")).read()
    tst = open(os.path.join(HERE, "test_bars.cpp")).read()
    rows_r = re.findall(r"RegSym\((CR_\w+),\s*\"(\w+)\",\s*\"(\w+)\",\s*(CR_FAM_\w+),\s*(\w+),\s*([\d.]+),\s*([\d.]+),\s*(\d+),\s*([\d.]+)\);", reg)
    rows_t = re.findall(r"ea_sym\((CR_\w+),\s*\"(\w+)\",\s*\"(\w+)\",\s*(CR_FAM_\w+),\s*(\w+),\s*([\d.]+),\s*([\d.]+),\s*(\w+),\s*([\d.]+)\);", tst)
    same = len(rows_r) == 4 and len(rows_t) == 4 and all(a[:7] + a[8:] == b[:7] + b[8:] for a, b in zip(rows_r, rows_t))
    depth_r = [int(r[7]) for r in rows_r]
    store_depth = re.search(r"ea_setup\(closures,\s*(\d+),\s*(\d+)\)", tst)
    depth_ok = bool(store_depth) and depth_r == [int(store_depth.group(1))] + [int(store_depth.group(2))] * 3
    return {"rows_equal": bool(same), "depth_equal": depth_ok, "depth_days": depth_r, "pass": bool(same and depth_ok)}


def run_worlds(exe):
    t0 = time.time()
    r = subprocess.run([exe], capture_output=True, text=True, cwd=ROBOT)
    lines = r.stdout.strip().splitlines()
    try:
        j = json.loads(lines[-1])
    except (IndexError, ValueError):
        j = {"failed": -1}
    return {"exit": r.returncode, "checks": j.get("worlds_checks"), "failed": j.get("failed"), "failures": [ln for ln in lines if ln.startswith("FAIL")][:20],
            "wall_s": round(time.time() - t0, 2), "pass": r.returncode == 0 and j.get("failed") == 0}


def check_h3(exe, sym_data, tag):
    """raw gold = lab + 3 points, raw spread = lab spread - 6 (clipped at 0), EA built with CR_XAU_COMM_PTS=6"""
    sd = sym_data["XAUUSD.r"]
    rec = sd["rec"].copy()
    for k in "ohlc":
        rec[k] = rec[k] + 3
    rec["s"] = np.maximum(sd["rec"]["s"] - 6, 0)
    path = os.path.join(HERE, "out", "bars", f"XAUUSD.r_rawh3_{tag}.bin")
    write_bin(path, rec)
    try:
        fed, summ, _, _ = run_store(exe, f"store_h3_{tag}", {"XAUUSD.r": path})
    finally:
        os.remove(path)
    last_utc = summ["last_event_utc"]
    keep = (sd["r"] == 0) & (sd["tu"] < last_utc)
    fr = sd["fr"]
    lab_s = sd["rec"]["s"][keep]
    clipped = lab_s < 6
    res = {"fed": int(len(fed)), "expected": int(keep.sum()), "h_xau": summ["h_xau"], "comm_pts": summ["comm_pts"],
           "bars_with_lab_spread_ge_6": int((~clipped).sum()), "bars_clipped": int(clipped.sum())}
    ok = len(fed) == int(keep.sum()) and summ["comm_pts"] == 6 and (fed["t"] == sd["tu"][keep]).all()
    bad = {}
    if ok:
        for k in PRICES:
            want = fr[k].to_numpy()[keep]
            if k.startswith("a"):
                pts = sd["rec"][k.replace("a", "", 1)][keep].astype(np.int64)
                want = np.where(clipped, (pts + 6) / 100.0, want)          # raw spread 0: ask = raw bid + 3 points = bid + 6 points
            eq = fed[k] == want
            if not eq.all():
                bad[k] = int((~eq).sum())
        eq_lab = np.ones(int((~clipped).sum()), bool)
        for k in PRICES:
            eq_lab &= fed[k][~clipped] == fr[k].to_numpy()[keep][~clipped]
        res["equal_to_lab_where_spread_ge_6"] = bool(eq_lab.all())
        res["raw_spread_journaled"] = bool((fed["s"] == np.maximum(lab_s - 6, 0)).all())
        ok = ok and not bad and res["equal_to_lab_where_spread_ge_6"] and res["raw_spread_journaled"]
    res["fields_differing"] = bad
    res["pass"] = bool(ok)
    return res


def mask_in_sample(sym_data):
    """SPEC 2.2's mask (the pandas copy) on the in-sample broker bars: what it drops, by reason, year and New York date.
    The kept bars must be the rebuilt frames except gold bars of 17:00-17:59 New York (the xau rule): any other dropped
    bar fails (there is no flat-bar rule any more, so nothing else may go)"""
    out, ok = {}, True
    for broker, sd in sym_data.items():
        r, tu = sd["r"], sd["tu"]
        drop = r != KEPT
        years = pd.DatetimeIndex(pd.to_datetime(tu[drop], unit="s")).year
        by = {REASONS[k]: int((r == k).sum()) for k in range(1, len(REASONS)) if (r == k).any()}
        xau_ny = pd.DatetimeIndex(pd.to_datetime(tu[r == XAU], unit="s", utc=True)).tz_convert("America/New_York")
        other = int((drop & (r != XAU)).sum())
        out[broker] = {"frame_bars": int(len(r)), "kept": int((~drop).sum()), "dropped": int(drop.sum()), "by_reason": by,
                       "by_year": {int(y): int(c) for y, c in pd.Series(years).value_counts().sort_index().items()},
                       "xau_dropped_ny_dates": sorted({str(d) for d in xau_ny.date}),
                       "xau_dropped_ny_first_last": [str(xau_ny.min()), str(xau_ny.max())] if len(xau_ny) else [],
                       "dropped_other_than_xau": other}
        ok &= other == 0
    out["pass"] = bool(ok)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="the 2021 bars only (no whole in-sample store)")
    ap.add_argument("--no-sanitize", action="store_true")
    a = ap.parse_args(argv)
    os.makedirs(OUT, exist_ok=True)
    t_start = time.time()
    res = {"registry": check_registry()}
    exe, warn = build_test("test_bars")
    res["build_plain_warnings"] = len(warn)
    exe_h3, warn_h3 = build_test("test_bars_h3", comm=6)
    res["build_h3_warnings"] = len(warn_h3)
    halves = half_days()
    tag = "y2021" if a.quick else "is"
    res["tag"] = tag
    bins = bars_2021(tag)
    fed, summ, agg, cost = run_store(exe, f"store_{tag}", bins)
    sym_data, exp = expected(tag, summ["last_event_utc"], halves)
    res["store"] = check_store(fed, summ, sym_data, exp)
    del fed, exp
    res["costs"] = check_costs(cost, sym_data, summ["last_event_utc"], summ["last_event_srv"])
    res["aggregates"] = check_aggregates(agg, sym_data)
    res["h3"] = check_h3(exe_h3, sym_data, tag)
    res["mask_in_sample"] = mask_in_sample(sym_data)
    names, series = math_inputs(sym_data)
    ops = math_ops(names, series)
    outs, raw_plain = run_math(exe, names, series, ops, os.path.join(OUT, "math_in.bin"), os.path.join(OUT, "math_out.bin"))
    res["primitives"] = check_math(names, series, ops, outs)
    res["worlds"] = run_worlds(exe)
    ok = (res["registry"]["pass"] and res["build_plain_warnings"] == 0 and res["build_h3_warnings"] == 0 and res["store"]["pass"]
          and res["costs"]["pass"] and res["aggregates"]["pass"] and res["h3"]["pass"] and res["primitives"]["pass"] and res["worlds"]["pass"]
          and res["mask_in_sample"]["pass"])
    if not a.no_sanitize:
        exe_s, warn_s = build_test("test_bars_san", sanitize=True)
        san = {"warnings": len(warn_s), "worlds": run_worlds(exe_s)}
        _, raw_san = run_math(exe_s, names, series, ops, os.path.join(OUT, "math_in.bin"), os.path.join(OUT, "math_out_san.bin"))
        san["primitives_identical_to_plain"] = bool(raw_san.tobytes() == raw_plain.tobytes())
        bins21 = bars_2021("y2021")
        fed21, summ21, agg21, cost21 = run_store(exe_s, "store_y2021_san", bins21)
        sd21, exp21 = expected("y2021", summ21["last_event_utc"], halves)
        san["store_2021"] = check_store(fed21, summ21, sd21, exp21)
        san["pass"] = bool(san["warnings"] == 0 and san["worlds"]["pass"] and san["primitives_identical_to_plain"] and san["store_2021"]["pass"])
        res["sanitizer"] = san
        ok &= san["pass"]
    for p in ("math_in.bin", "math_out.bin", "math_out_san.bin"):
        if os.path.exists(os.path.join(OUT, p)):
            os.remove(os.path.join(OUT, p))
    res["wall_s"] = round(time.time() - t_start, 1)
    res["pass"] = bool(ok)
    with open(os.path.join(OUT, "result.json"), "w") as f:
        json.dump(res, f, indent=1, default=str)
    print(json.dumps(res, indent=1, default=str))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
