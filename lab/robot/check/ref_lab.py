"""Lab references of the robot (SPEC 7, "References"): the ten sleeves' orders and trades from the lab's own code.

    python3 -I lab/robot/check/ref_lab.py [--frame official|rebuilt] [--tag y2021] [--sleeves N30,OC4,...] [--jobs 3]
                                          [--no-changes]

For each sleeve, in a FRESH PROCESS (P8: the rule modules cache bar frames on id(frame)), it calls recalc.sleeves()
once and then, on the in-sample frame (read with the row filter ts < 2022-01-01 inside the read call):
  * make_orders(m1, **params)                         every signal (the brk72 wrapper included, recalc.py:43-53)
  * r2.run(sym, make_orders, params, "fp", True, m1)  the official call of recalc.py:98, m1 given
NQB: strategy.set_leader("us100", <the US100 frame of the same kind>) before each call, clear_leaders() after,
asserting "us100" in _LEADERS so that the default loader (leadlag/strategy.py:89-94) never runs (P2).
Frames: "official" = lab/data/fp/<sym>_m1.parquet; "rebuilt" = check/out/frames/<sym>_<tag>.parquet (export_frames.py).
On the official frames the trades are compared with results/r2/recalc/trades/<name>__<sym>.parquet, read with the
row filter entry_time < 2022-01-01: every official trade that also EXITS before 2022 must be identical (entry and
exit times, side, reason, prices, pnl, R, bitwise); a trade whose official exit falls in 2022 may differ.
Writes under lab/robot/check/out/ref/<frame>[_<tag>]/:
  <CODE>/orders.parquet      the lab's orders with their activation and exit bar times
  <CODE>/trades.parquet      the lab's trades (r2.run)
  script/<CODE>.csv          the orders as CrOrder rows for src/CR_Rule_Script.mqh (emit = activation bar start)
  changes/<id>/...           the three kept changes, through check/ref_changes.py (step E's file)
  summary.json               one entry per sleeve and per change
"""
import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

os.environ.setdefault("NUMBA_CACHE_DIR", "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/numba")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROBOT = os.path.dirname(HERE)
LAB = os.path.dirname(ROBOT)
OUT = os.path.join(HERE, "out", "ref")
CUT = pd.Timestamp("2022-01-01", tz="UTC")
OFFICIAL = os.path.join(LAB, "results", "r2", "recalc", "trades")
# code, sleeve id, lab rule name, symbol (SPEC 2.3; the order of src/CR_Registry.mqh)
SLEEVES = [("N30", 1, "noise30", "us100"), ("OC4", 2, "ocm4", "us100"), ("BKB", 3, "brk72_24h_wd", "btcusd"),
           ("BKE", 4, "brk72_24h_wd", "ethusd"), ("F1B", 5, "F1_brk_ridge_filter", "btcusd"),
           ("F1E", 6, "F1_brk_ridge_filter", "ethusd"), ("NQB", 7, "nq_btc_follow", "btcusd"), ("GFP", 8, "GOLD_FRI_PM", "xauusd"),
           ("D4H", 9, "donch4h_stop", "xauusd"), ("ORX", 10, "orb_asia_2d_buf10", "xauusd")]
BY_CODE = {s[0]: s for s in SLEEVES}
SCRIPT_COLS = ["emit", "oid", "side", "etype", "level", "level2", "t_from", "t_to", "after_exit_of", "expiry_excl", "stop",
               "stop_dist", "trail", "be", "target", "target_dist", "x_sched", "x_gap", "xh", "xh_r", "refuse", "void_le", "dec",
               "group"]
CMP_COLS = ["exit_time", "entry", "exit", "stop", "reason", "pnl", "R", "risk", "swap"]


def out_dir(kind, tag):
    return os.path.join(OUT, kind + (f"_{tag}" if tag else ""))


def frame(sym, kind="official", tag=None):
    """An in-sample M1 frame, cut inside the read call."""
    if kind == "official":
        p = os.path.join(LAB, "data", "fp", f"{sym}_m1.parquet")
    elif kind == "rebuilt":
        p = os.path.join(HERE, "out", "frames", f"{sym}_{tag}.parquet")
    else:
        raise ValueError(kind)
    m1 = pd.read_parquet(p, filters=[("ts", "<", CUT)])
    assert len(m1) and m1.index.max() < CUT and m1.index.is_monotonic_increasing and m1.index.is_unique
    return m1


def secs(ts):
    return pd.DatetimeIndex(ts).tz_convert("UTC").as_unit("s").asi8.astype(np.int64)


def _f(v):
    """a double for the script file: 17 significant digits, NaN -> 0 (CrOrder's 'none')"""
    v = float(v)
    return "0" if not np.isfinite(v) else repr(v) if abs(v) < 1e300 else "%.17g" % v


def script_rows(code, sid, rule, orders, m1):
    """The lab's orders as CrOrder rows (src/CR_Rule_Script.mqh): activation = exactly the lab's entry bar, exit = the
    lab's exit bar (its gap rule already resolved: no gap flag), pending orders fill up to the lab's expiry bar."""
    idx_s = secs(m1.index)
    n = len(m1)
    o = orders.reset_index(drop=True)
    col = lambda c, d=np.nan: o[c].to_numpy() if c in o else np.full(len(o), d)
    ei, xi = o["entry_i"].to_numpy(np.int64), col("exit_i", -1).astype(np.int64)
    et = col("etype", 0).astype(np.int64)
    exp = col("expiry_i", -1).astype(np.int64)
    if "dec_time" in o:
        dec = secs(o["dec_time"])
    elif "cid" in o:
        dec = (o["cid"].to_numpy(np.int64) // 1_000_000_000).astype(np.int64)
    else:
        dec = np.where(ei < n, idx_s[np.clip(ei, 0, n - 1)], 0)
    rows, skipped = [], 0
    for k in range(len(o)):
        if ei[k] < 0 or ei[k] >= n:
            skipped += 1
            continue
        t = int(idx_s[ei[k]])
        x = int(idx_s[xi[k]]) if 0 <= xi[k] < n else 0
        pend = et[k] > 0
        expiry = int(idx_s[min(exp[k], n - 1)]) + 60 if pend else 0
        d = int(dec[k]) if dec[k] > 0 else t
        rows.append([t, d * 100 + sid, int(o["side"].iat[k]), int(et[k]), _f(col("level")[k]) if pend else "0", "0", t, t, 0, expiry,
                     _f(col("stop")[k]), _f(col("stop_dist")[k]), _f(col("trail")[k]), _f(col("be")[k]), _f(col("target")[k]),
                     _f(col("target_dist")[k]), x, 0, 0, "0", 0, 1 if rule == "brk72_24h_wd" else 0, d, 0])
    df = pd.DataFrame(rows, columns=SCRIPT_COLS)
    assert df.oid.is_unique, f"{code}: two lab orders share an oid"
    assert (np.diff(df.emit.to_numpy()) >= 0).all(), f"{code}: orders not in activation order"
    return df, skipped


def compare_official(name, sym, t):
    """the lab trades of this run against results/r2/recalc/trades (entries before 2022)"""
    off = pd.read_parquet(os.path.join(OFFICIAL, f"{name}__{sym}.parquet"), filters=[("entry_time", "<", CUT)])
    a = off.reset_index(drop=True)
    b = t.reset_index(drop=True)
    m = a.merge(b, on=["entry_time", "side"], how="outer", suffixes=("_off", "_lab"), indicator=True)
    both = (m._merge == "both").to_numpy()
    same = both.copy()
    for c in CMP_COLS:
        x, y = m[f"{c}_off"].to_numpy(), m[f"{c}_lab"].to_numpy()
        if m[f"{c}_off"].dtype.kind == "f":
            eq = (x == y) | (np.isnan(x.astype(float)) & np.isnan(y.astype(float)))
        else:
            eq = x == y
        same &= np.asarray(eq, bool)
    exit_2022 = (m["exit_time_off"] >= CUT).to_numpy()
    diff_rows = m[~same]
    bad = []
    allowed = []
    for _, r in diff_rows.iterrows():
        row = {"entry_time": str(r.entry_time), "side": int(r.side), "in": str(r._merge),
               "official_exit": str(r.get("exit_time_off")), "lab_exit": str(r.get("exit_time_lab")),
               "official_reason": str(r.get("reason_off")), "lab_reason": str(r.get("reason_lab"))}
        late = (r._merge != "right_only" and pd.notna(r.exit_time_off) and r.exit_time_off >= CUT) or \
               (r._merge == "right_only" and r.entry_time >= t.entry_time.max() - pd.Timedelta(days=10))
        (allowed if late else bad).append(row)
    return {"official_trades_before_2022": int(len(a)), "official_exit_in_2022": int(exit_2022.sum()),
            "lab_trades": int(len(b)), "identical": int(same.sum()), "differ_allowed_exit_in_2022_or_frame_end": allowed,
            "differ_not_allowed": bad, "pass": len(bad) == 0}


def one(code, kind, tag):
    """the work of one sleeve, in this (fresh) process"""
    t0 = time.time()
    _, sid, rule, sym = BY_CODE[code]
    sys.path.insert(0, LAB)
    sys.path.insert(0, os.path.join(LAB, "r2"))
    import recalc
    from goldlab import r2
    reg = {(s[1], s[2]): s for s in recalc.sleeves()}          # once in this process
    track, name, sym_, mo, params = reg[(rule, sym)]
    m1 = frame(sym, kind, tag)
    S = sys.modules.get("r2_leadlag_strategy")
    lead = frame("us100", kind, tag) if code == "NQB" else None

    def with_leader(fn):
        if lead is None:
            return fn()
        S.clear_leaders()
        S.set_leader("us100", lead)
        assert "us100" in S._LEADERS
        try:
            return fn()
        finally:
            assert "us100" in S._LEADERS, "the leader was replaced by the default loader"
            S.clear_leaders()

    orders = with_leader(lambda: mo(m1, **params)).reset_index(drop=True)
    trades = with_leader(lambda: r2.run(sym, mo, params, "fp", True, m1))
    d = out_dir(kind, tag)
    os.makedirs(os.path.join(d, code), exist_ok=True)
    os.makedirs(os.path.join(d, "script"), exist_ok=True)
    o = orders.copy()
    n = len(m1)
    o["entry_t"] = pd.DatetimeIndex(m1.index[np.clip(o.entry_i.to_numpy(), 0, n - 1)]).where(o.entry_i.to_numpy() < n)
    if "exit_i" in o:
        xi = o.exit_i.to_numpy()
        o["exit_t"] = pd.DatetimeIndex(m1.index[np.clip(xi, 0, n - 1)]).where((xi >= 0) & (xi < n))
    for c in o.columns:
        if o[c].dtype == object:
            o[c] = o[c].astype(str)
    o.to_parquet(os.path.join(d, code, "orders.parquet"))
    trades.to_parquet(os.path.join(d, code, "trades.parquet"))
    sc, skipped = script_rows(code, sid, rule, orders, m1)
    sc.to_csv(os.path.join(d, "script", f"{code}.csv"), index=False)
    res = {"code": code, "sleeve": f"{rule}_{sym}", "frame": kind, "tag": tag, "bars": int(n), "first_bar": str(m1.index[0]),
           "last_bar": str(m1.index[-1]), "orders": int(len(orders)), "trades": int(len(trades)),
           "script_rows": int(len(sc)), "orders_beyond_frame": int(skipped),
           "reasons": trades.reason.value_counts().to_dict(), "R_sum": float(trades.R.sum())}
    if code == "NQB":
        res["leader"] = "set_leader('us100', the us100 frame of the same kind); default loader never ran"
    if kind == "official":
        res["official"] = compare_official(rule, sym, trades)
    res["sec"] = round(time.time() - t0, 1)
    return res


def spawn(args):
    """run one sleeve (or one change) in a fresh process; returns its JSON result"""
    r = subprocess.run([sys.executable, "-I", os.path.abspath(__file__)] + args, capture_output=True, text=True,
                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    if r.returncode:
        return {"args": args, "error": r.stderr[-4000:]}
    return json.loads(r.stdout.strip().splitlines()[-1])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", default="official", choices=["official", "rebuilt"])
    ap.add_argument("--tag")
    ap.add_argument("--sleeves", default=",".join(s[0] for s in SLEEVES))
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--no-changes", action="store_true")
    ap.add_argument("--changes", default="K1,S0.75r,H2")
    ap.add_argument("--one")
    ap.add_argument("--change")
    a = ap.parse_args(argv)
    if a.frame == "rebuilt" and not a.tag:
        raise SystemExit("--frame rebuilt needs --tag (the export_frames.py tag)")
    if a.one:
        print(json.dumps(one(a.one, a.frame, a.tag), default=str))
        return 0
    if a.change:
        sys.path.insert(0, HERE)
        import ref_changes
        print(json.dumps(ref_changes.run_change(a.change, a.frame, a.tag, out_dir(a.frame, a.tag)), default=str))
        return 0
    t0 = time.time()
    base = ["--frame", a.frame] + (["--tag", a.tag] if a.tag else [])
    jobs = [["--one", c] + base for c in a.sleeves.split(",") if c]
    if not a.no_changes:
        jobs += [["--change", c] + base for c in a.changes.split(",") if c]
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        res = list(ex.map(spawn, jobs))
    d = out_dir(a.frame, a.tag)
    os.makedirs(d, exist_ok=True)
    summary = {"frame": a.frame, "tag": a.tag, "cut": str(CUT), "sec": round(time.time() - t0, 1), "results": res}
    with open(os.path.join(d, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1, default=str)
    ok = True
    for r in res:
        if "error" in r:
            ok = False
            print("ERROR", r["args"], r["error"][-1500:])
            continue
        if "change" not in r:
            o = r.get("official", {})
            line = (f"{r['code']:4s} {r['sleeve']:28s} orders {r['orders']:5d} trades {r['trades']:5d} R {r['R_sum']:9.3f}")
            if o:
                line += (f" | official<2022 {o['official_trades_before_2022']:5d} identical {o['identical']:5d}"
                         f" allowed {len(o['differ_allowed_exit_in_2022_or_frame_end'])} NOT {len(o['differ_not_allowed'])}")
                ok &= o["pass"]
            print(line + f" [{r['sec']} s]")
        else:
            print(f"{r['change']:7s} {r['key']:34s} trades {r['trades']:5d} R {r['R_sum']:9.3f} | " + r.get("note", "") + f" [{r['sec']} s]")
    print(f"ref_lab: {'PASS' if ok else 'FAIL'}  ({summary['sec']} s)  -> {os.path.relpath(d, ROBOT)}/summary.json")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
