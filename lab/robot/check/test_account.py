"""T7a account: CR_Ledger and CR_Sizing (step I; SPEC 5, 6, 7 T7a) against the lab's growth.run_one.

    python3 -I lab/robot/check/test_account.py [--quick] [--no-sanitize] [--san-all]

1. Rows: the symbol and sleeve rows of check/test_account.cpp equal src/CR_Registry.mqh (RegSym, RegSleeve, the two
   frozen stake factors) and lab/r2/fp_costs.json (units per lot, minimum lot, lot step, leverage, slippage).
2. Unit worlds of check/test_account.cpp (risk tables and bad strings, m, lots with stake factors, minimum lot, caps,
   margin, stamps, plan start unset / to come / past, B(T), P_in, ref on deposits and withdrawals, the STOP, GUARD (b, c)
   and LOCK history latches, settle) in four builds: plain and sanitizer (address, undefined behaviour, checked
   containers), each with the guard on and with CR_NO_GUARD.
3. T7a: the official trades of the ten sleeves (results/r2/recalc/trades, read with the row filter entry_time <
   2022-01-01 inside the read call), entries 2018-02-01 .. 2021-12-31, 1,000 EUR at the start and on the first entry of
   each following server month (growth.py real_order:421-436), plans F3S, F2S and F1S, built with CR_NO_GUARD.
   growth.run_one on growth.arrays(d, price_level="is") (P8) is the reference. Equal: taken count, skips by reason
   (minimum lot, caps, margin; none by the stake rule), stop week, money paid in each week; weekly balances within
   0.01 EUR. Per trade (diagnosis, from the EA's SIZE lines): lots, m, w, unit, B, P_in, rate against a copy of
   growth.engine that records them; the copy must give run_one's figures bit for bit. The same at the lab's edges x0
   and x-0.5 (growth.with_edge), where the plan stop fires.
4. R16 inside T7a: F3S at edge x1 with each deposit's deal 45 s before the balance shows it. The sizing requests of
   that minute meet SETTLE and are asked again every 2 s inside their 5-minute window; the result must not change.
--quick: T7a at edge x1 only. Sanitizer: the unit worlds and T7a F3S at x1 and x-0.5 (--san-all: every T7a run).
Outputs under lab/robot/check/out/test_account/ (summary.json, inputs, the EA's trades.csv / weeks.csv, journals).
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True
os.environ.setdefault("NUMBA_CACHE_DIR", "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/numba")
HERE = os.path.dirname(os.path.abspath(__file__))
ROBOT = os.path.dirname(HERE)
LAB = os.path.dirname(ROBOT)
OUT = os.path.join(HERE, "out", "test_account")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(LAB, "r2", "tracks", "stake"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import compare  # noqa: E402
from build import BuildError, build  # noqa: E402
import stake as S  # noqa: E402
import account as A  # noqa: E402
import growth as G  # noqa: E402

CUT = pd.Timestamp("2022-01-01", tz="UTC")
PLANS = {"F3S": "0:3;3000:2;6000:1;12000:0.5", "F2S": "0:2;6000:1;12000:0.5", "F1S": "0:1;12000:0.5"}
EDGES = (1.0, 0.0, -0.5)
CODE = {"noise30_us100": "N30", "ocm4_us100": "OC4", "brk72_24h_wd_btcusd": "BKB", "brk72_24h_wd_ethusd": "BKE",
        "F1_brk_ridge_filter_btcusd": "F1B", "F1_brk_ridge_filter_ethusd": "F1E", "nq_btc_follow_btcusd": "NQB",
        "GOLD_FRI_PM_xauusd": "GFP", "donch4h_stop_xauusd": "D4H", "orb_asia_2d_buf10_xauusd": "ORX"}
SK = {"none": 0, "stopped": 1, "min_lot": 10, "cap": 11, "margin": 12}
SKEW = -45                                  # R16 run: a deposit's deal 45 s before the balance shows it
SAN_EDGES = (1.0, -0.5)                     # F3S runs repeated under the sanitizer: no stop, and a stop in week 49
ENTRY = "src/CR_Sizing.mqh"
SUBST = ["CR_Clock.mqh=" + os.path.join(ROBOT, "check", "dbl", "CR_Clock_dbl.mqh")]


# ------------------------------------------------------------------ 1. rows
def defines():
    out = {}
    for f in ("CR_Types.mqh", "CR_Registry.mqh"):
        for m in re.finditer(r"^\s*#define\s+(CR_\w+)\s+(-?[\d.]+)\b", open(os.path.join(ROBOT, "src", f)).read(), re.M):
            out[m.group(1)] = float(m.group(2))
    out["CR_XAU_COMM_PTS"] = 0.0          # harness builds (build.py: CR_XAU_COMM_PTS=0, SPEC 7)
    return out


def check_rows(exe):
    rows = subprocess.run([exe, "rows"], capture_output=True, text=True, check=True).stdout.split("\n")
    sym = [r.split() for r in rows if r.startswith("sym ")]
    sl = [r.split() for r in rows if r.startswith("sleeve ")]
    d = defines()
    val = lambda tok: d[tok] if tok in d else float(tok)
    src = open(os.path.join(ROBOT, "src", "CR_Registry.mqh")).read()
    reg_sym = re.findall(r"RegSym\((CR_\w+),\s*\"(\w+)\",\s*\"(\w+)\",\s*(CR_FAM_\w+),\s*(\w+),\s*([\d.]+),\s*([\d.]+),\s*(\d+),\s*([\d.]+)\)", src)
    reg_sl = re.findall(r"RegSleeve\((\d+),\s*\"(\w+)\",\s*\"(\w+)\",\s*(CR_K_\w+),\s*(\d+),\s*(CR_\w+),\s*(-?\w+),\s*(CR_CH_\w+),\s*"
                        r"([\w.]+),\s*(CR_REF_\w+)\)", src)
    cost = json.load(open(os.path.join(LAB, "r2", "fp_costs.json")))
    bad = []
    if len(reg_sym) != 4 or len(sym) != 4 or len(reg_sl) != 10 or len(sl) != 10:
        bad.append(f"row counts: registry {len(reg_sym)}/{len(reg_sl)}, test {len(sym)}/{len(sl)}")
    for r, t in zip(reg_sym, sym):
        want = [val(r[0]), r[1], r[2], val(r[3]), val(r[4]), float(r[5]), float(r[6]), float(r[7]), float(r[8])]
        got = [float(t[1]), t[2], t[3], float(t[4]), float(t[5]), float(t[6]), float(t[7]), float(t[8]), float(t[9])]
        if want != got:
            bad.append(f"symbol {r[1]}: registry {want} test {got}")
        c = cost[t[3]]
        spec = [c["units_per_lot"], c["min_lot"], c["lot_step"], c["leverage"], c["slip_mkt_bps"], c["slip_stop_bps"]]
        mine = [float(t[10]), float(t[11]), float(t[12]), float(t[13]), float(t[6]), float(t[7])]
        if spec != mine:
            bad.append(f"symbol {t[2]}: fp_costs.json {spec} test {mine}")
    for r, t in zip(reg_sl, sl):
        want = [int(r[0]), r[1], r[2], val(r[3]), int(r[4]), val(r[5]), val(r[6]), val(r[7]), val(r[8]), val(r[9]),
                20261200 + int(r[0])]
        got = [int(t[1]), t[2], t[3], float(t[4]), int(t[5]), float(t[6]), float(t[7]), float(t[8]), float(t[9]), float(t[10]), int(t[11])]
        if want != got:
            bad.append(f"sleeve {r[1]}: registry {want} test {got}")
    return {"pass": not bad, "differences": bad, "symbols": len(sym), "sleeves": len(sl)}


# ------------------------------------------------------------------ 2. builds and unit worlds
def make(name, sanitize, no_guard):
    exe, warn = build(os.path.join(ROBOT, ENTRY), name=name, main=os.path.join(HERE, "test_account.cpp"), subst=SUBST,
                      defines=["CR_NO_GUARD"] if no_guard else [], sanitize=sanitize)
    return exe, warn


def run_units(exe, tag, sanitize):
    d = os.path.join(OUT, "unit_" + tag)
    env = dict(os.environ, ASAN_OPTIONS="detect_leaks=1") if sanitize else None
    t0 = time.time()
    r = subprocess.run([exe, d], capture_output=True, text=True, env=env, cwd=ROBOT, timeout=3600)
    line = (r.stdout.strip().splitlines() or [""])[-1]
    m = re.search(r"(\d+) checks, (\d+) failed", line)
    parsed = compare.check_parsable(d)
    return {"exit": r.returncode, "summary": line, "checks": int(m.group(1)) if m else 0, "failed": int(m.group(2)) if m else -1,
            "stderr": r.stderr[-3000:], "journal": parsed["events"], "sec": round(time.time() - t0, 2),
            "pass": r.returncode == 0 and m is not None and int(m.group(2)) == 0}


# ------------------------------------------------------------------ 3. T7a inputs and the lab's reference
def lab_frame():
    """The official trades, cut at the read, entries in 2018-02-01 .. 2021-12-31, with the reason and side columns
    that S.build_frame drops (same concatenation and the same stable sort, checked)."""
    per, extra = {}, []
    for name, sym in S.SLEEVES:
        t = pd.read_parquet(os.path.join(S.NET_DIR, f"{name}__{sym}.parquet"), filters=[("entry_time", "<", CUT)])
        assert len(t) and (t.entry_time < CUT).all()
        t = t[(t.entry_time >= S.COMMON_START) & (t.entry_time < CUT)]
        per[(name, sym)] = t
        extra.append(pd.DataFrame({"sleeve": f"{name}_{sym}", "t_in": t.entry_time.dt.tz_convert("UTC").to_numpy(),
                                   "reason": t.reason.to_numpy(), "side": t.side.to_numpy(np.int64)}))
    d = S.build_frame(per)
    e = pd.concat(extra, ignore_index=True)
    e["t_in"] = pd.to_datetime(e.t_in, utc=True)
    e = e.sort_values(["t_in", "sleeve"], kind="stable").reset_index(drop=True)
    assert (e.sleeve.to_numpy() == d.sleeve.to_numpy()).all() and (e.t_in.to_numpy() == d.t_in.to_numpy()).all()
    return d, e


def payments(x):
    """growth.py real_order:421-436: 1,000 EUR on the first entry at or after each server month start (after the first)"""
    first = x["t_in_server"].min().normalize().replace(day=1)
    last = x["t_in_server"].max()
    months = pd.date_range(first, last, freq="MS")[1:]
    dep_srv = months.values.astype("datetime64[ns]").astype("int64")
    order = np.argsort(x["t_in"], kind="stable")
    srv = x["t_in_server"].values.astype("datetime64[ns]").astype("int64")[order]
    pos = np.searchsorted(srv, dep_srv, side="left")
    keep = pos < len(order)
    dep_t = x["t_in"][order][pos[keep]]
    dep_wk = x["wk_in"][order][pos[keep]]
    dep_amt = np.full(int(keep.sum()), 1000.0)
    return dep_t, dep_wk, dep_amt


def mirror(x, pnl, plan, dep_t, dep_wk, dep_amt, start=1000.0):
    """growth.engine (growth.py:150-319) written again for the STOPPED plans (key 1, the cushion_only stake rule, no
    payment steps, no second profile), recording each entry's sizing. Checked against run_one bit for bit."""
    base, kill_dd, kill_arm = G.STOPPED[plan]
    thr, pct = (np.array(v, dtype=np.float64) for v in G.SCHEDULES[base])
    key, rp = 1, np.zeros(5)
    p, famcap = S.params(G.CFG)
    pk = G.pack(x)
    t_in, t_out, order_out, wk_in, dy_in, wk_out, dy_out, fam, symid = pk["head"]
    risk, entry, upl, minlot, step, lev = pk["tail"]
    nwk = pk["nwk"]
    max_pos, max_per_sym, usd_eur = A.LIMITS["max_positions"], A.LIMITS["max_per_sym"], A.USD_EUR
    n, nd = len(t_in), len(dep_t)
    eq_wk, paid_wk, cnt = np.zeros(nwk), np.zeros(nwk), np.zeros(8)
    cnt[5] = -1.0
    eq = paid = ref = start
    o_idx = np.full(max_pos, -1, np.int64)
    o_lots, o_margin, o_boost = np.zeros(max_pos), np.zeros(max_pos), np.zeros(max_pos)
    cur_wk, cur_dy = -1, -1
    wk_paid, hwm, wk_hwm = start, 0.0, 0.0
    wk_bal, dy_bal, wk_base, dy_base = start, start, start, start
    prev_wk, prev_res = -2, 0.0
    rec, j, q, i, stopped = 0, 0, 0, 0, False
    big = np.int64(9223372036854775807)
    out = [None] * n
    risk_of = lambda e, pd_, h: G._risk(e, pd_, thr, pct, key, rp, h)
    while True:
        t_entry = t_in[i] if i < n else big
        t_close = t_out[order_out[j]] if j < n else big
        t_dep = dep_t[q] if q < nd else big
        if i >= n and j >= n and q >= nd:
            break
        if t_dep <= t_entry and t_dep <= t_close and q < nd:
            w_ev = dep_wk[q]
            while rec < w_ev and rec < nwk:
                eq_wk[rec], paid_wk[rec] = eq, paid
                rec += 1
            if not stopped:
                amt = dep_amt[q]
                if amt > 0.0:
                    eq += amt
                    paid += amt
                    wk_base += amt
                    dy_base += amt
                    if eq == amt:
                        wk_base, dy_base = eq, eq
                    ref = max(ref + amt, eq)
            q += 1
            continue
        if t_close < t_entry and j < n:
            k = order_out[j]
            j += 1
            slot = -1
            for s in range(max_pos):
                if o_idx[s] == k:
                    slot = s
            if slot < 0:
                continue
            w_ev = wk_out[k]
            while rec < w_ev and rec < nwk:
                eq_wk[rec], paid_wk[rec] = eq, paid
                rec += 1
            if w_ev != cur_wk:
                if cur_wk >= 0:
                    prev_wk, prev_res = cur_wk, (eq - wk_base) / max(risk_of(wk_bal, wk_paid, wk_hwm) / 100.0 * wk_bal, 1e-9)
                cur_wk, wk_bal, wk_base, wk_paid, wk_hwm = w_ev, eq, eq, paid, hwm
            if dy_out[k] != cur_dy:
                cur_dy, dy_bal, dy_base = dy_out[k], eq, eq
            eq += pnl[k] * o_lots[slot] * upl[k] * usd_eur
            if eq - paid > hwm:
                hwm = eq - paid
            o_idx[slot] = -1
            if eq <= 0.0:
                eq = 0.0
                cnt[6] += 1.0
                o_idx[:] = -1
            if eq <= ref * (1.0 - kill_dd) and cnt[5] < 0 and paid >= kill_arm:
                cnt[5] = float(w_ev)
                stopped = True
                cnt[7] = 1.0
                if i >= n:
                    o_idx[:] = -1
            continue
        if i >= n:
            break
        w_ev = wk_in[i]
        while rec < w_ev and rec < nwk:
            eq_wk[rec], paid_wk[rec] = eq, paid
            rec += 1
        if stopped:
            o_idx[:] = -1
            out[i] = {"skip": "stopped"}
            i += 1
            continue
        if w_ev != cur_wk:
            if cur_wk >= 0:
                prev_wk, prev_res = cur_wk, (eq - wk_base) / max(risk_of(wk_bal, wk_paid, wk_hwm) / 100.0 * wk_bal, 1e-9)
            cur_wk, wk_bal, wk_base, wk_paid, wk_hwm = w_ev, eq, eq, paid, hwm
        if dy_in[i] != cur_dy:
            cur_dy, dy_bal, dy_base = dy_in[i], eq, eq
        unit = max(risk_of(wk_bal, wk_paid, wk_hwm) / 100.0 * wk_bal, 1e-9)
        w = (eq - wk_base) / unit
        d = (eq - dy_base) / unit
        pw = prev_res if prev_wk == w_ev - 1 else 0.0
        open_boost, n_open, n_sym, used = 0.0, 0, 0, 0.0
        for s in range(max_pos):
            if o_idx[s] >= 0:
                n_open += 1
                open_boost += o_boost[s]
                used += o_margin[s]
                if symid[o_idx[s]] == symid[i]:
                    n_sym += 1
        m, b = S.multiplier(w, d, pw, fam[i], open_boost, p, famcap)
        rate = risk_of(eq, paid, hwm)
        rec_i = {"skip": None, "lots": 0.0, "m": float(m), "w": float(w), "unit": float(unit), "B": float(eq), "P_in": float(paid),
                 "rate": float(rate)}
        out[i] = rec_i
        if m <= 0.0 or eq <= 0.0:
            cnt[1] += 1.0
            rec_i["skip"] = "rule"
            i += 1
            continue
        per_lot = risk[i] * upl[i] * usd_eur
        lots = np.floor(eq * rate * m * 1.0 / 100.0 / per_lot / step[i] + 1e-9) * step[i]
        rec_i["want"] = float(lots)
        if lots < minlot[i]:
            cnt[2] += 1.0
            rec_i["skip"] = "min_lot"
            i += 1
            continue
        if n_open >= max_pos or n_sym >= max_per_sym:
            cnt[3] += 1.0
            rec_i["skip"] = "cap"
            i += 1
            continue
        margin = lots * upl[i] * entry[i] * usd_eur / lev[i]
        if used + margin > eq:
            cnt[4] += 1.0
            rec_i["skip"] = "margin"
            i += 1
            continue
        for s in range(max_pos):
            if o_idx[s] < 0:
                o_idx[s], o_lots[s], o_margin[s], o_boost[s] = i, lots, margin, b
                break
        cnt[0] += 1.0
        rec_i["skip"] = "none"
        rec_i["lots"] = float(lots)
        i += 1
    while rec < nwk:
        eq_wk[rec], paid_wk[rec] = eq, paid
        rec += 1
    return eq_wk, paid_wk, cnt, out


def write_inputs(d_dir, x, e, pnl, dep_t):
    os.makedirs(d_dir, exist_ok=True)
    tin, tout = x["t_in"] // 10 ** 9, x["t_out"] // 10 ** 9
    assert (x["t_in"] % 10 ** 9 == 0).all() and (x["t_out"] % 10 ** 9 == 0).all()
    tr = pd.DataFrame({"i": np.arange(len(tin)), "t_in": tin, "t_out": tout, "time_exit": (e.reason.to_numpy() == "time").astype(int),
                       "code": [CODE[s] for s in x["sleeve"]], "side": e.side.to_numpy(), "entry": x["entry"], "risk": x["risk"], "pnl": pnl})
    with open(os.path.join(d_dir, "trades.csv"), "w") as f:
        f.write("i,t_in,t_out,time_exit,code,side,entry,risk,pnl\n")
        for r in tr.itertuples(index=False):
            f.write(f"{r.i},{r.t_in},{r.t_out},{r.time_exit},{r.code},{r.side},{r.entry!r},{r.risk!r},{r.pnl!r}\n")
    with open(os.path.join(d_dir, "payments.csv"), "w") as f:
        f.write("t,amount\n")
        for t in dep_t:
            f.write(f"{int(t) // 10 ** 9},1000.0\n")
    mon = x["week_monday"].values.astype("datetime64[s]").astype(np.int64)
    mon = np.r_[mon, mon[-1] + 7 * 86400]
    with open(os.path.join(d_dir, "weeks.csv"), "w") as f:
        f.write("w,monday_srv\n")
        for k, v in enumerate(mon):
            f.write(f"{k},{int(v)}\n")
    return mon


def week_of_utc(t_utc, mon):
    """index of the lab week (server Monday) holding a UTC instant"""
    srv = S.server_time(pd.DatetimeIndex([pd.Timestamp(int(t_utc), unit="s", tz="UTC")]))
    s = int(srv.values.astype("datetime64[s]").astype(np.int64)[0])
    return int(np.searchsorted(mon, s, side="right") - 1)


def run_t7a(exe, plan, edge, x, e, dep, ref, rec, sanitize, skew=0):
    tag = f"{plan}_x{edge:g}" + ("_san" if sanitize else "") + (f"_skew{skew}" if skew else "")
    d_in = os.path.join(OUT, "t7a_in_x" + f"{edge:g}")
    d_out = os.path.join(OUT, "t7a_" + tag)
    mon = write_inputs(d_in, x, e, G.with_edge(x, edge), dep[0])
    if os.path.isdir(d_out):
        subprocess.run(["rm", "-rf", d_out], check=True)
    os.makedirs(d_out)
    env = dict(os.environ, ASAN_OPTIONS="detect_leaks=1") if sanitize else None
    t0 = time.time()
    r = subprocess.run([exe, "t7a", os.path.join(d_in, "trades.csv"), os.path.join(d_in, "payments.csv"), os.path.join(d_in, "weeks.csv"),
                        PLANS[plan], d_out, str(int(skew))], capture_output=True, text=True, env=env, cwd=ROBOT, timeout=7200)
    sec = round(time.time() - t0, 2)
    res = {"plan": plan, "edge": edge, "sanitize": sanitize, "skew": skew, "exit": r.returncode, "stdout": r.stdout.strip(), "sec": sec}
    if r.returncode != 0:
        res["stderr"] = r.stderr[-3000:]
        res["pass"] = False
        return res
    ea = pd.read_csv(os.path.join(d_out, "trades.csv"), float_precision="round_trip")
    wk = pd.read_csv(os.path.join(d_out, "weeks.csv"), float_precision="round_trip")
    summ = dict(ln.split() for ln in open(os.path.join(d_out, "summary.txt")) if ln.strip())
    eq_wk, paid_wk, cnt = ref
    n = len(ea)
    counts_ea = {k: int((ea.skip == v).sum()) for k, v in SK.items()}
    counts_ea["other"] = int(n - sum(counts_ea.values()))
    counts_lab = {"none": int(cnt[0]), "min_lot": int(cnt[2]), "cap": int(cnt[3]), "margin": int(cnt[4]), "rule": int(cnt[1]),
                  "stopped": int(n - cnt[0] - cnt[1] - cnt[2] - cnt[3] - cnt[4]), "zero": int(cnt[6])}
    stop_utc = int(summ["stop_utc"])
    stop_wk_ea = week_of_utc(stop_utc, mon) if stop_utc > 0 else -1
    dB = np.abs(wk.B.to_numpy() - eq_wk)
    dP = np.abs(wk.P_in.to_numpy() - paid_wk)
    # per trade, against the recording copy of the engine (entries before the stop)
    diff = {"skip": 0, "lots": 0, "m": 0, "w": 0, "unit": 0, "B": 0, "P_in": 0, "rate": 0}
    first = {}
    maxd = {"lots": 0.0, "m": 0.0, "w": 0.0, "unit": 0.0, "B": 0.0}
    compared = 0
    for row in ea.itertuples(index=False):
        lr = rec[row.i]
        if lr["skip"] == "stopped":
            if row.skip != SK["stopped"]:
                diff["skip"] += 1
                first.setdefault("skip", int(row.i))
            continue
        compared += 1
        if SK.get(lr["skip"], -1) != row.skip:
            diff["skip"] += 1
            first.setdefault("skip", int(row.i))
        for k in ("lots", "m", "w", "unit", "B", "P_in", "rate"):
            a, b = float(getattr(row, k)), float(lr[k])
            if a != b:
                diff[k] += 1
                first.setdefault(k, int(row.i))
                if k in maxd:
                    maxd[k] = max(maxd[k], abs(a - b))
    res.update({"trades": n, "counts_ea": counts_ea, "counts_lab": counts_lab, "stop_week_ea": stop_wk_ea, "stop_week_lab": int(cnt[5]),
                "stop_utc": stop_utc, "weeks": len(wk), "max_abs_diff_weekly_balance_eur": float(dB.max()),
                "max_abs_diff_weekly_paid_eur": float(dP.max()), "final_balance_ea": float(wk.B.iloc[-1]), "final_balance_lab": float(eq_wk[-1]),
                "paid_ea": float(wk.P_in.iloc[-1]), "paid_lab": float(paid_wk[-1]), "per_trade_compared": compared,
                "per_trade_differences": diff, "per_trade_first_difference": first, "per_trade_max_abs_diff": maxd,
                "dropped_at_stop": int(summ["dropped"]), "payments_skipped_after_stop": int(summ["payments_skipped"]),
                "late_stop": int(summ["late_stop"]), "ledger_reads": int(summ["reads"]), "deals": int(summ["deals"]),
                "settle_waits": int(summ["settle_waits"]), "settle_wait_trades": int(summ["settle_wait_trades"]),
                "settle_past_window": int(summ["settle_past_window"])})
    ok = (counts_ea["none"] == counts_lab["none"] and counts_ea["min_lot"] == counts_lab["min_lot"] and counts_ea["cap"] == counts_lab["cap"]
          and counts_ea["margin"] == counts_lab["margin"] and counts_ea["stopped"] == counts_lab["stopped"] and counts_ea["other"] == 0
          and counts_lab["rule"] == 0 and counts_lab["zero"] == 0 and stop_wk_ea == int(cnt[5]) and len(wk) == len(eq_wk)
          and float(dB.max()) <= 0.01 and float(dP.max()) <= 0.01 and int(summ["late_stop"]) == 0 and int(summ["fails"]) == 0
          and int(summ["settle_past_window"]) == 0 and (int(summ["settle_waits"]) > 0) == (skew != 0))
    # the SIZE lines carry the same lots and m (every entry: one line)
    rows = compare.read_journal(d_out)
    size = [q for q in rows if q["ev"] == "SIZE"]
    by_oid = {int(q["oid"]): q for q in size}
    jbad = sum(1 for row in ea.itertuples(index=False)
               if int(row.i) not in by_oid or float(by_oid[int(row.i)]["lots"]) != float(row.lots) or float(by_oid[int(row.i)]["m"]) != float(row.m))
    res["size_lines"] = len(size)
    res["size_lines_differing_from_trades_csv"] = jbad
    ok = ok and len(size) == n and jbad == 0
    res["pass"] = bool(ok)
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--no-sanitize", action="store_true")
    ap.add_argument("--san-all", action="store_true")
    a = ap.parse_args(argv)
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    res = {"pass": False}
    builds = {}
    try:
        builds["plain"] = make("test_account_i", False, False)
        builds["plain_ng"] = make("test_account_i_ng", False, True)
        if not a.no_sanitize:
            builds["san"] = make("test_account_i_san", True, False)
            builds["san_ng"] = make("test_account_i_san_ng", True, True)
    except BuildError as err:
        res["build_error"] = str(err)[-4000:]
        print(json.dumps(res, indent=1))
        return 1
    res["warnings"] = {k: len(v[1]) for k, v in builds.items()}
    res["rows"] = check_rows(builds["plain"][0])
    res["units"] = {k: run_units(v[0], k, k.startswith("san")) for k, v in builds.items()}
    d, e = lab_frame()
    x = G.arrays(d, price_level="is")
    dep = payments(x)
    res["data"] = {"trades": int(len(d)), "first_entry": str(d.t_in.min()), "last_entry": str(d.t_in.max()),
                   "last_exit": str(d.t_out.max()), "weeks": int(x["nwk"]), "payments": int(len(dep[0])),
                   "per_sleeve": {CODE[s]: int(c) for s, c in d.sleeve.value_counts().sort_index().items()}}
    res["t7a"] = []
    pk = G.pack(x)
    for edge in (EDGES[:1] if a.quick else EDGES):
        pnl = G.with_edge(x, edge)
        for plan in PLANS:
            eq_wk, paid_wk, cnt = G.run_one(pk, pnl, plan, *dep)
            m_eq, m_paid, m_cnt, rec = mirror(x, pnl, plan, *dep)
            same = bool(np.array_equal(m_eq, eq_wk) and np.array_equal(m_paid, paid_wk) and np.array_equal(m_cnt, cnt))
            san = a.san_all or (plan == "F3S" and edge in SAN_EDGES)
            for kind in ("plain_ng",) + (("san_ng",) if "san_ng" in builds and san else ()):
                r = run_t7a(builds[kind][0], plan, edge, x, e, dep, (eq_wk, paid_wk, cnt), rec, kind.startswith("san"))
                r["engine_copy_equals_run_one"] = same
                r["pass"] = bool(r["pass"] and same)
                res["t7a"].append(r)
                print(f"T7a {plan} edge x{edge:g}{' sanitizer' if r['sanitize'] else ''}: "
                      f"{'PASS' if r['pass'] else 'FAIL'} taken {r.get('counts_ea', {}).get('none')} / {int(cnt[0])}, "
                      f"stop week {r.get('stop_week_ea')} / {int(cnt[5])}, weekly B max diff {r.get('max_abs_diff_weekly_balance_eur')}, "
                      f"{r['sec']} s", flush=True)
    # R16 inside T7a: each deposit's deal is in the history 45 s before the balance shows it; the sizing waits, same result
    pnl = G.with_edge(x, 1.0)
    eq_wk, paid_wk, cnt = G.run_one(pk, pnl, "F3S", *dep)
    m_eq, m_paid, m_cnt, rec = mirror(x, pnl, "F3S", *dep)
    same = bool(np.array_equal(m_eq, eq_wk) and np.array_equal(m_paid, paid_wk) and np.array_equal(m_cnt, cnt))
    r = run_t7a(builds["plain_ng"][0], "F3S", 1.0, x, e, dep, (eq_wk, paid_wk, cnt), rec, False, skew=SKEW)
    r["engine_copy_equals_run_one"] = same
    r["pass"] = bool(r["pass"] and same)
    res["t7a"].append(r)
    print(f"T7a F3S edge x1 deal {-SKEW} s before the balance: {'PASS' if r['pass'] else 'FAIL'} taken "
          f"{r.get('counts_ea', {}).get('none')} / {int(cnt[0])}, weekly B max diff {r.get('max_abs_diff_weekly_balance_eur')}, "
          f"sizing waits {r.get('settle_waits')} ({r.get('settle_wait_trades')} trades), {r['sec']} s", flush=True)
    res["sec"] = round(time.time() - t0, 1)
    res["pass"] = bool(res["rows"]["pass"] and all(u["pass"] for u in res["units"].values()) and all(r["pass"] for r in res["t7a"])
                       and all(v == 0 for v in res["warnings"].values()))
    with open(os.path.join(OUT, "summary.json"), "w") as f:
        json.dump(res, f, indent=1)
    short = {k: v for k, v in res.items() if k != "t7a"}
    short["t7a"] = [{k: r.get(k) for k in ("plan", "edge", "sanitize", "skew", "pass", "counts_ea", "counts_lab", "stop_week_ea",
                                           "stop_week_lab", "max_abs_diff_weekly_balance_eur", "max_abs_diff_weekly_paid_eur",
                                           "per_trade_differences", "settle_waits", "sec")}
                    for r in res["t7a"]]
    print(json.dumps(short, indent=1))
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
