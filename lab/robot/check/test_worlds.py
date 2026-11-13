"""T8 worlds (step J): the execution layer (CR_Broker, CR_Follower, CR_Guards) in the replay mock, ten sleeves on
CR_Rule_Script (the lab's orders from ref_lab.py, rebuilt in-sample frames), then the scripted fault worlds.

    python3 -I lab/robot/check/test_worlds.py [--only clean_fast,dup_open,...] [--no-sanitize] [--list]

What is built (SPEC 8: J's tests compile S0, A, B, C, I files; the rule files are the S0 stubs, read with `git show HEAD`
because steps D-H edit them in parallel): build/test_worlds/tree = src/ with the HEAD rule stubs. Binaries: the harness
build (CR_XAU_COMM_PTS=0, the exported spread holds the gold commission, SPEC 7), the same with h = 3 points
(CR_XAU_COMM_PTS=6) for the gold quote world, the sanitizer build, and the release build (no CR_HARNESS, compiled only).
Every build must have 0 warnings.

Clean worlds (SPEC 7 T8 "clean ticks -> real = paper (gold one bar late), for each sleeve"), 2021-01-04 to 2022-01-01,
the in-sample bars of the four symbols (history before is there: the first rebuild replays 120 / 60 days dry):
  clean_fast   fast mode (broker stops checked at bar end with the lab rule). For every live paper trade: one real
               position, opened at the stamp + 2 s (market) or the fill bar + 62 s (stop, limit, OCO: one bar late), at
               the paper's fill price (market) or at the next bar's open quote (pending); closed at x + 2 s at the paper's
               time-exit price, or by its broker stop in the paper's stop bar at the price the lab rule gives on the grid
               stop. Every difference is listed with its cause. The live paper trades also equal the lab trades
               (compare.cmp_trades against ref_lab.py's rebuilt_is trades).
  clean_tick   tick mode (O->L->H->C ticks, stops on ticks): the same trades, the same bars; market entries and time
               exits at the same prices; stop exits fill at the triggering tick (the bar's low or high), not at the stop.
  clean_h      gold with h = 3 points (raw bid = lab bid + 3 points, raw spread = lab spread - 6 points clipped at 0):
               the broker stop = paper stop + side x h triggers in the same bar; real fill = paper fill - side x h (x
               the slippage factor).
  clean_san    the sanitizer build replays the fast world: identical journal and deals.
Fault worlds: see WORLDS below (each one says what it checks).
"""
import argparse
import calendar
import json
import os
import shutil
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROBOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import compare  # noqa: E402
from build import BuildError, build  # noqa: E402

OUT = os.path.join(HERE, "out", "test_worlds")
BUILD = os.path.join(ROBOT, "build", "test_worlds")
SYMS = ("XAUUSD.r", "US100.r", "BTCUSD.r", "ETHUSD.r")
CODES = ["N30", "OC4", "BKB", "BKE", "F1B", "F1E", "NQB", "GFP", "D4H", "ORX"]
SID = {c: i + 1 for i, c in enumerate(CODES)}
CODE_OF_MAGIC = {20261200 + i: c for c, i in SID.items()}
SYM_OF = {"N30": "US100.r", "OC4": "US100.r", "BKB": "BTCUSD.r", "BKE": "ETHUSD.r", "F1B": "BTCUSD.r", "F1E": "ETHUSD.r",
          "NQB": "BTCUSD.r", "GFP": "XAUUSD.r", "D4H": "XAUUSD.r", "ORX": "XAUUSD.r"}
SLIP = {"XAUUSD.r": (0.3, 1.0), "US100.r": (0.2, 0.5), "BTCUSD.r": (0.5, 1.5), "ETHUSD.r": (0.7, 2.0)}   # mkt, stop bps
PENDING = {"GFP", "D4H", "ORX"}
RULE_STUBS = ["CR_Rule_IdxUS.mqh", "CR_Rule_Brk72.mqh", "CR_Rule_F1.mqh", "CR_F1Model.mqh", "CR_Rule_NqBtc.mqh", "CR_Rule_GoldFri.mqh",
              "CR_Rule_Orb.mqh", "CR_Rule_Donch.mqh", "CR_Golden.mqh"]
REF = os.path.join(HERE, "out", "ref", "rebuilt_is")
IS_END = 1640995200                                             # 2022-01-01 00:00 UTC: every read below stops before it
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
           NUMBA_CACHE_DIR=os.environ.get("NUMBA_CACHE_DIR", "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/numba"))
DEAL_SL, DEAL_EXPERT = 4, 3


def srv(s):
    """'2021-01-04 00:00' on the server clock -> server seconds"""
    return calendar.timegm(time.strptime(s, "%Y-%m-%d %H:%M"))


def us_dst(utc):
    """US summer time at a UTC instant (2nd Sunday of March 07:00 UTC to 1st Sunday of November 06:00 UTC)"""
    y = time.gmtime(utc).tm_year

    def nth_sunday(m, n):
        first = calendar.timegm((y, m, 1, 0, 0, 0))
        wd = time.gmtime(first).tm_wday                    # Monday 0 ... Sunday 6
        return first + ((6 - wd) % 7) * 86400 + 7 * 86400 * (n - 1)
    return nth_sunday(3, 2) + 7 * 3600 <= utc < nth_sunday(11, 1) + 6 * 3600


def srv_to_utc(s):
    u3 = s - 3 * 3600
    return u3 if us_dst(u3) else u3 + 3600


def utc_to_srv(u):
    return u + (3 * 3600 if us_dst(u) else 2 * 3600)


# ------------------------------------------------------------------ builds
def make_tree():
    """src/ with the rule files of the S0 commit (HEAD): the rule steps edit them beside this one (SPEC 8)"""
    dst = os.path.join(BUILD, "tree")
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    os.makedirs(dst)
    for f in sorted(os.listdir(os.path.join(ROBOT, "src"))):
        if f in RULE_STUBS:
            r = subprocess.run(["git", "-C", ROBOT, "show", f"HEAD:lab/robot/src/{f}"], capture_output=True, text=True)
            if r.returncode:
                raise SystemExit(f"git show HEAD:{f} failed: {r.stderr}")
            with open(os.path.join(dst, f), "w") as h:
                h.write(r.stdout)
        else:
            shutil.copy(os.path.join(ROBOT, "src", f), os.path.join(dst, f))
    return dst


def binaries(tree, sanitize=True):
    entry = os.path.join(tree, "ClaudeRobot.mq5")
    out, warn_all = {}, {}
    plan = [("plain", dict(name="test_worlds_plain")), ("h6", dict(name="test_worlds_h6", defines=["CR_XAU_COMM_PTS=6"])),
            ("release", dict(name="test_worlds_release", harness=False))]
    if sanitize:
        plan.append(("san", dict(name="test_worlds_san", sanitize=True)))
    for k, kw in plan:
        exe, warn = build(entry, **kw)
        out[k] = exe
        warn_all[k] = warn
    return out, warn_all


# ------------------------------------------------------------------ bars
def read_bars(path):
    with open(path, "rb") as f:
        assert f.read(4) == b"CRB1"
        digits, = struct.unpack("<i", f.read(4))
        n, = struct.unpack("<q", f.read(8))
        rec = np.frombuffer(f.read(28 * n), dtype=np.dtype([("t", "<i8"), ("o", "<i4"), ("h", "<i4"), ("l", "<i4"), ("c", "<i4"),
                                                             ("s", "<i4")]))
    return digits, rec[rec["t"] < srv("2022-01-01 00:00")]      # in sample only (server time; stricter than 00:00 UTC)


def write_bars(path, digits, rec):
    with open(path, "wb") as f:
        f.write(b"CRB1")
        f.write(struct.pack("<i", digits))
        f.write(struct.pack("<q", len(rec)))
        f.write(rec.tobytes())


def bar_paths(tag="is"):
    p = {s: os.path.join(HERE, "out", "bars", f"{s}_{tag}.bin") for s in SYMS}
    missing = [s for s, v in p.items() if not os.path.exists(v)]
    if missing:
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "export_frames.py"), "--tag", tag], capture_output=True, text=True,
                           env=ENV)
        if r.returncode:
            raise SystemExit("export_frames.py failed: " + r.stderr[-2000:])
    return p


def h_bars(src):
    """gold bars for h = 3 points: raw bid = lab bid + 3 points, raw spread = lab spread - 6 points clipped at 0 (SPEC 7)"""
    dst = os.path.join(OUT, "bars", "XAUUSD.r_is_h6.bin")
    if not os.path.exists(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        d, rec = read_bars(src)
        r = rec.copy()
        for k in ("o", "h", "l", "c"):
            r[k] = rec[k] + 3
        r["s"] = np.maximum(rec["s"] - 6, 0)
        write_bars(dst, d, r)
    return dst


class Bars:
    """the bars of one symbol, by server time (for the expected real prices)"""

    def __init__(self, path):
        self.digits, self.rec = read_bars(path)
        self.sc = 10.0 ** self.digits
        self.t = self.rec["t"]

    def at(self, t_srv):
        i = int(np.searchsorted(self.t, t_srv))
        if i < len(self.t) and self.t[i] == t_srv:
            return self.rec[i]
        return None

    def forming(self, t_srv):
        """the bar forming at server time t_srv (the last bar starting at or before it)"""
        i = int(np.searchsorted(self.t, t_srv, side="right")) - 1
        return self.rec[i] if i >= 0 else None


# ------------------------------------------------------------------ worlds
def read_orders(path, **kw):
    """ref_lab.py's script orders, in sample only: rows emitted before 2022-01-01 00:00 UTC"""
    df = pd.read_csv(path, **kw)
    return df[df["emit"].astype(np.int64) < IS_END].reset_index(drop=True)


def script_dir(files, codes, src=None, extra=None, override=None):
    d = os.path.join(files, "ClaudeRobot", "script")
    os.makedirs(d, exist_ok=True)
    for c in codes:
        p = os.path.join(src or os.path.join(REF, "script"), f"{c}.csv")
        df = read_orders(p, dtype=str) if not (override and c in override) else override[c].astype(str)
        if extra and c in extra:
            df = pd.concat([df, extra[c].astype(str)], ignore_index=True)
            df = df.sort_values("emit", key=lambda s: s.astype(np.int64), kind="stable")
        df.to_csv(os.path.join(d, f"{c}.csv"), index=False)


def run(exe, files, bars, frm, to, env=None, codes=CODES, fresh=True, faults=None, payments=None, extra_orders=None, timeout=1800,
        expect_fail=False, override=None):
    """one replay process; returns (exit code, stdout)"""
    if fresh and os.path.isdir(files):
        shutil.rmtree(files)
    os.makedirs(os.path.join(files, "_mock"), exist_ok=True)
    if fresh:
        script_dir(files, codes, extra=extra_orders, override=override)
    e = dict(ENV, MOCK_FILES=files, MOCK_SYMS=",".join(SYMS), MOCK_QUIET="1", MOCK_FROM=str(frm), MOCK_TO=str(to), MOCK_BALANCE="100000",
             MOCK_INPUT_InpScript=",".join(codes), MOCK_INPUT_InpK1="0", MOCK_INPUT_InpH2="0", MOCK_INPUT_InpS075="0",
             MOCK_INPUT_InpPlanStart=str(srv("2020-06-01 00:00")))
    for s, p in bars.items():
        e[f"MOCK_BARS_{s}"] = p
    if faults is not None:
        fp = os.path.join(files, "_mock", "faults_in.txt")
        with open(fp, "w") as f:
            f.write("\n".join(faults) + "\n")
        e["MOCK_FAULTS"] = fp
    if payments is not None:
        pp = os.path.join(files, "_mock", "payments.csv")
        with open(pp, "w") as f:
            f.write("\n".join(f"{t},{a}" for t, a in payments) + "\n")
        e["MOCK_PAYMENTS"] = pp
    e.update({k: str(v) for k, v in (env or {}).items()})
    r = subprocess.run([exe], env=e, capture_output=True, text=True, timeout=timeout)
    if r.returncode and not expect_fail:
        raise RuntimeError(f"replay failed ({r.returncode}): {r.stdout[-2000:]} {r.stderr[-3000:]}")
    return r.returncode, r.stdout + r.stderr


def deals(files):
    p = os.path.join(files, "_mock", "deals.csv")
    if not os.path.exists(p):
        return pd.DataFrame(columns=["deal", "order", "position", "time", "symbol", "type", "entry", "volume", "price", "reason", "magic",
                                     "commission", "swap", "profit", "comment"])
    return pd.read_csv(p, keep_default_na=False, float_precision="round_trip")      # (the default parser is not exact)


def positions(files):
    """one row per robot position of the deal history: magic, side, open and close (server and UTC), prices, reasons"""
    d = deals(files)
    d = d[d.type.isin([0, 1])]
    rows = []
    for pid, g in d.groupby("position"):
        i, o = g[g.entry == 0], g[g.entry == 1]
        if not len(i):
            continue
        r = {"position": int(pid), "magic": int(i.magic.iloc[0]), "code": CODE_OF_MAGIC.get(int(i.magic.iloc[0]), "-"),
             "side": 1 if int(i.type.iloc[0]) == 0 else -1, "t_in": int(i.time.iloc[0]), "px_in": float(i.price.iloc[0]),
             "vol": float(i.volume.iloc[0]), "comment": str(i.comment.iloc[0])}
        r["u_in"] = srv_to_utc(r["t_in"])
        if len(o):
            r.update(t_out=int(o.time.iloc[-1]), px_out=float(o.price.iloc[-1]), reason_out=int(o.reason.iloc[-1]),
                     magic_out=int(o.magic.iloc[-1]))
            r["u_out"] = srv_to_utc(r["t_out"])
        rows.append(r)
    return pd.DataFrame(rows)


def journal(files):
    return compare.read_journal(files)


def ev(rows, name, code=None, live=None):
    return [r for r in rows if r["ev"] == name and (code is None or r["code"] == code) and (live is None or (r.get("rp") != 1) == live)]


def counts(rows):
    c = {}
    for r in rows:
        c[r["ev"]] = c.get(r["ev"], 0) + 1
    return dict(sorted(c.items()))


def fault_counts(files):
    p = os.path.join(files, "_mock", "faults.txt")
    out = {}
    if os.path.exists(p):
        for ln in open(p):
            k, _, v = ln.rstrip().rpartition(" ")
            out[k] = int(v)
    return out


def pushes(files):
    p = os.path.join(files, "_mock", "log.txt")
    return [ln.rstrip().split(" ", 2)[2] for ln in open(p) if ln.startswith("PUSH ")] if os.path.exists(p) else []


# ------------------------------------------------------------------ real against paper
def grid(x, side, digits):
    """BrkGridOf on a tick of one point: the largest grid price <= x (long), the smallest >= x (short)"""
    sc = 10 ** digits
    k = np.floor(x * sc)
    g = round(k / sc, digits)
    if side > 0:
        while g > x:
            k -= 1
            g = round(k / sc, digits)
        while round((k + 1) / sc, digits) <= x:
            k += 1
            g = round(k / sc, digits)
        return g
    while g < x:
        k += 1
        g = round(k / sc, digits)
    while round((k - 1) / sc, digits) >= x:
        k -= 1
        g = round(k / sc, digits)
    return g


def real_vs_paper(rows, files, bars, code, mode, h_pts=0, go_live=0):
    """every live paper trade of a sleeve against the real positions (see the module docstring); returns a summary and the
    list of differences, each with its kind"""
    sym = SYM_OF[code]
    B = bars[sym]
    sc = B.sc
    sm, ss = SLIP[sym][0] * 1e-4, SLIP[sym][1] * 1e-4
    h = h_pts / sc
    done, voided = compare.paper_chain(rows, code, live_only=True)
    size = {r["oid"]: r for r in ev(rows, "SIZE", code, live=True)}
    missed = {r["oid"]: r for r in ev(rows, "MISSED", code, live=True)}
    pos = positions(files)
    pos = pos[pos.code == code].sort_values("u_in").reset_index(drop=True) if len(pos) else pos
    crossed = {int(r["ticket"]) for r in ev(rows, "CLOSE", code) if r.get("why") == "crossed"}
    used = set()
    res = {"code": code, "paper_trades": len(done), "voided": len(voided), "real_positions": int(len(pos)), "matched": 0, "skipped": 0,
           "missed": 0, "entry_time_ok": 0, "entry_px_ok": 0, "exit_time_ok": 0, "exit_px_ok": 0, "exit_px_within_tick": 0}
    diffs = []
    for oid, (f, x) in sorted(done.items(), key=lambda kv: kv[1][0]["utc"]):
        stamp = f["utc"]
        if stamp < go_live:
            continue
        pend = code in PENDING
        cand = [k for k in range(len(pos)) if k not in used and pos.side[k] == f["side"] and stamp <= pos.u_in[k] <= stamp + 300]
        if not cand:
            s = size.get(oid)
            if s is not None and s.get("skip") not in (None, "none"):
                res["skipped"] += 1
                continue
            if oid in missed:
                res["missed"] += 1
                diffs.append({"oid": oid, "kind": "missed", "reason": missed[oid].get("reason")})
                continue
            diffs.append({"oid": oid, "kind": "no_real_position", "stamp": stamp})
            continue
        k = cand[0]
        used.add(k)
        p = pos.iloc[k]
        res["matched"] += 1
        want_in = stamp + (62 if pend else 2)
        if p.u_in == want_in:
            res["entry_time_ok"] += 1
        else:
            diffs.append({"oid": oid, "kind": "entry_time", "real": int(p.u_in), "want": want_in})
        # the entry price: the market fill at the quote of the send (the bar forming then)
        bar = B.forming(p.t_in)
        ask = round((bar["o"] + bar["s"]) / sc, B.digits)
        bid = round(bar["o"] / sc, B.digits)
        if mode == "tick":
            pass                                                # the first tick of the bar is its open, as in fast mode
        want_px = ask * (1 + sm) if f["side"] > 0 else bid * (1 - sm)
        if p.px_in == want_px:
            res["entry_px_ok"] += 1
        else:
            diffs.append({"oid": oid, "kind": "entry_px", "real": p.px_in, "want": want_px})
        if not pend and h_pts == 0 and p.px_in != f["px"]:
            diffs.append({"oid": oid, "kind": "entry_px_vs_paper", "real": p.px_in, "paper": f["px"]})
        if "t_out" not in p or pd.isna(p.get("t_out")):
            diffs.append({"oid": oid, "kind": "still_open"})
            continue
        reason = x.get("reason")
        if reason == "time":
            want_out = x["utc"] + 2
            ok_t = p.u_out == want_out
            if ok_t:
                res["exit_time_ok"] += 1
            else:
                diffs.append({"oid": oid, "kind": "exit_time", "reason": reason, "real": int(p.u_out), "want": want_out,
                              "real_reason": int(p.reason_out)})
            xb = B.forming(p.t_out)
            xbid = round(xb["o"] / sc, B.digits) if ok_t else round(xb["c"] / sc, B.digits)
            xask = round((xb["o" if ok_t else "c"] + xb["s"]) / sc, B.digits)
            want_x = xbid * (1 - sm) if f["side"] > 0 else xask * (1 + sm)
            if p.px_out == want_x:
                res["exit_px_ok"] += 1
            else:
                diffs.append({"oid": oid, "kind": "exit_px", "reason": reason, "real": p.px_out, "want": want_x, "paper": x["px"]})
        else:
            bar_t = x["bar"]
            want_out = bar_t + 59 if mode == "fast" else None
            if p.reason_out == DEAL_EXPERT and p.position in crossed and p.u_out == bar_t + 2:
                # the paper's new stop (trail) was already beyond the open of the next bar: the follower cannot place it and
                # closes at that open at once (SPEC 4.4); the paper books its stop at the same open, with the stop slippage
                xb = B.at(utc_to_srv(bar_t))
                if f["side"] > 0:
                    want_x = round(xb["o"] / sc, B.digits) * (1 - sm)
                else:
                    want_x = round((xb["o"] + xb["s"]) / sc, B.digits) * (1 + sm)
                res["crossed_at_open"] = res.get("crossed_at_open", 0) + 1
                res["exit_time_ok"] += 1
                if p.px_out == want_x:
                    res["exit_px_ok"] += 1
                else:
                    diffs.append({"oid": oid, "kind": "exit_px_crossed", "real": p.px_out, "want": want_x, "paper": x["px"]})
                continue
            if p.reason_out == DEAL_SL and (mode != "fast" or p.u_out == want_out) and bar_t <= p.u_out < bar_t + 60:
                res["exit_time_ok"] += 1
            else:
                diffs.append({"oid": oid, "kind": "exit_time", "reason": reason, "real": int(p.u_out), "want": want_out,
                              "real_reason": int(p.reason_out)})
            if mode == "fast" and p.reason_out == DEAL_SL:
                st = x["stop"]
                gs = grid(st + f["side"] * h, f["side"], B.digits)
                xb = B.at(utc_to_srv(bar_t))
                first = (p.u_in >= bar_t)
                if f["side"] > 0:
                    o = round((xb["o"]) / sc, B.digits)
                    want_x = (gs if first else min(gs, o)) * (1 - ss)
                else:
                    o = round((xb["o"] + xb["s"]) / sc, B.digits)
                    want_x = (gs if first else max(gs, o)) * (1 + ss)
                if p.px_out == want_x:
                    res["exit_px_ok"] += 1
                if abs(p.px_out - x["px"]) <= 1.0 / sc * (1 + ss) + 1e-9 and h_pts == 0:
                    res["exit_px_within_tick"] += 1
                if p.px_out != want_x:
                    diffs.append({"oid": oid, "kind": "exit_px", "reason": reason, "real": p.px_out, "want": want_x, "paper": x["px"]})
    open_fills = [r for r in ev(rows, "PFILL", code, live=True) if r["oid"] not in done and r["oid"] not in voided]
    for f in open_fills:                                        # a paper trade still open at the end (SPEC 7: excluded)
        for k in range(len(pos)):
            if k not in used and pos.side[k] == f["side"] and f["utc"] <= pos.u_in[k] <= f["utc"] + 300:
                used.add(k)
                res["open_at_end"] = res.get("open_at_end", 0) + 1
                break
    extra = [int(pos.position[k]) for k in range(len(pos)) if k not in used and pos.u_in[k] >= go_live]
    if extra:
        diffs.append({"kind": "real_without_paper", "positions": extra[:10], "n": len(extra)})
    res["n_diffs"] = len(diffs)
    return res, diffs


def lab_check(rows, code, go_live):
    """the live paper trades against the lab's trades (ref_lab.py, rebuilt_is): the script chain equals the lab"""
    ref = pd.read_parquet(os.path.join(REF, code, "trades.parquet"), filters=[("entry_time", "<", pd.Timestamp(IS_END, unit="s", tz="UTC"))])
    ref = ref[(ref.entry_time >= pd.Timestamp(go_live, unit="s", tz="UTC"))]
    live = [r for r in rows if r.get("rp") != 1]
    t = compare.paper_trades(live, code)
    if len(t):
        last = t.exit_time.max()
        ref = ref[ref.exit_time <= last]
    r = compare.cmp_trades(live, ref, code, t_from=go_live)
    return {k: r.get(k) for k in ("lab_trades", "ea_trades", "same_entry", "only_lab", "only_ea", "same_exit_and_reason", "entry_equal",
                                  "stop_equal", "exit_equal", "pass")}


# ------------------------------------------------------------------ the clean worlds
FROM = srv("2021-01-04 00:00")
TO = srv("2022-01-01 00:00")


def go_live(rows):
    reb = [r for r in rows if r["ev"] == "REBUILD"]
    return int(reb[0]["to"]) + 60 if reb else 0


def clean(ctx, name, exe, bars, env=None, h_pts=0, mode="fast", codes=CODES):
    files = os.path.join(OUT, name)
    t0 = time.time()
    _, out = run(exe, files, bars, FROM, TO, env=env, codes=codes)
    rows = journal(files)
    g = go_live(rows)
    B = {s: Bars(p) for s, p in bars.items()}
    per, diffs, lab = {}, {}, {}
    for c in codes:
        r, d = real_vs_paper(rows, files, B, c, mode, h_pts=h_pts if SYM_OF[c] == "XAUUSD.r" else 0, go_live=g)
        per[c] = r
        diffs[c] = d
        if h_pts == 0:
            lab[c] = lab_check(rows, c, g)
    errors = ev(rows, "ERROR")
    return {"files": files, "replay": out.strip().splitlines()[-1] if out.strip() else "", "sec": round(time.time() - t0, 1),
            "go_live": g, "events": counts(rows), "per_sleeve": per, "diffs": diffs, "lab": lab, "errors": errors[:5]}, rows


def judge_clean(res, mode):
    """the clean world passes when every live paper trade has its real position (or a SIZE skip), at the expected times
    and prices; tick mode allows stop exits at the triggering tick (counted, listed)"""
    ok = not res["errors"]
    bad = {}
    for c, d in res["diffs"].items():
        keep = []
        for x in d:
            if mode == "tick" and x["kind"] == "exit_px" and x.get("reason") in ("stop", "trail"):
                res["per_sleeve"][c]["tick_stop_px"] = res["per_sleeve"][c].get("tick_stop_px", 0) + 1
                continue
            keep.append(x)
        if keep:
            bad[c] = keep
    for c, l in res.get("lab", {}).items():
        if not l.get("pass"):
            bad.setdefault(c, []).append({"kind": "paper_vs_lab", **l})
    res["unexplained"] = {c: v[:8] for c, v in bad.items()}
    res["n_unexplained"] = sum(len(v) for v in bad.values())
    return ok and not bad


# ------------------------------------------------------------------ fault worlds
class Ctx:
    """what the worlds share: binaries, bars, the clean fast run (to choose their trades)"""

    def __init__(self, exes, bars):
        self.exe = exes
        self.bars = bars
        self.files = os.path.join(OUT, "clean_fast")
        self.rows = journal(self.files)
        self.pos = positions(self.files)
        self.trades = {c: compare.paper_chain(self.rows, c, live_only=True)[0] for c in CODES}

    def pick(self, code, after, cond=None):
        """the first live paper trade of a sleeve entered at or after `after` (UTC) that has a real position in the clean run;
        returns (fill row, exit row, real position)"""
        for oid, (f, x) in sorted(self.trades[code].items(), key=lambda kv: kv[1][0]["utc"]):
            if f["utc"] < after:
                continue
            p = self.pos[(self.pos.code == code) & (self.pos.u_in >= f["utc"]) & (self.pos.u_in <= f["utc"] + 300)]
            if not len(p):
                continue
            if cond is None or cond(f, x, p.iloc[0]):
                return f, x, p.iloc[0]
        raise RuntimeError(f"no {code} trade after {after}")


def day_srv(u, back_h=6):
    """a world start: the whole minute `back_h` hours before UTC instant u, on the server clock"""
    s = utc_to_srv(u) - back_h * 3600
    return s - s % 60


def wpos(files, code=None):
    p = positions(files)
    if code is not None and len(p):
        p = p[p.code == code]
    return p.reset_index(drop=True) if len(p) else p


def overlap_max(p):
    """the most robot positions of one sleeve open at the same time"""
    if not len(p):
        return 0
    evs = []
    for r in p.itertuples():
        evs.append((r.t_in, 1))
        evs.append((r.t_out if not pd.isna(getattr(r, "t_out", np.nan)) else 1 << 62, -1))
    n = m = 0
    for _, d in sorted(evs, key=lambda e: (e[0], e[1])):
        n += d
        m = max(m, n)
    return m


def chk(res, name, cond, info=None):
    res.setdefault("checks", {})[name] = bool(cond)
    if info is not None:
        res.setdefault("info", {})[name] = info
    return bool(cond)


def finish(res):
    res["pass"] = all(res.get("checks", {}).values()) and not res.get("errors")
    return res


def wrun(ctx, name, frm, to, faults=None, env=None, codes=CODES, exe="plain", fresh=True, payments=None, extra=None, expect_fail=False,
         override=None, bars=None):
    files = os.path.join(OUT, name)
    e = {"MOCK_TIMER_CALLS": "58"}
    e.update(env or {})
    rc, out = run(ctx.exe[exe], files, bars or ctx.bars, frm, to, env=e, codes=codes, fresh=fresh, faults=faults, payments=payments,
                  extra_orders=extra, expect_fail=expect_fail, override=override)
    return files, rc, out


def script_rows(code):
    return read_orders(os.path.join(REF, "script", f"{code}.csv"))


def order_row(code, emit, side, etype=0, level=0.0, stop=0.0, stop_dist=0.0, trail=0.0, x=0, x_gap=0, expiry=0, void_le=0, dec=None):
    """one CrOrder row for CR_Rule_Script (activation window = the one bar at `emit`, UTC)"""
    d = emit if dec is None else dec
    return {"emit": emit, "oid": d * 100 + SID[code], "side": side, "etype": etype, "level": repr(float(level)), "level2": "0",
            "t_from": emit, "t_to": emit, "after_exit_of": 0, "expiry_excl": expiry, "stop": repr(float(stop)),
            "stop_dist": repr(float(stop_dist)), "trail": repr(float(trail)), "be": "0", "target": "0", "target_dist": "0", "x_sched": x,
            "x_gap": x_gap, "xh": 0, "xh_r": "0", "refuse": 0, "void_le": void_le, "dec": d, "group": 0}


def w_refused_sltp(ctx):
    """a refused stop move (10016) three times: the old stop stays, the move is tried again every 10 s and placed; an open
    refused for its stop (10016): nothing opened, MISSED (the trade is the paper's alone)"""
    f, x, p = ctx.pick("D4H", FROM + 30 * 86400, lambda f, x, p: sum(1 for r in ctx.rows if r["ev"] == "PSTOP" and r["oid"] == f["oid"]) >= 3)
    frm, to = day_srv(f["utc"]), day_srv(x["utc"], -6)
    m = 20261209
    first_pstop = min(r["utc"] for r in ctx.rows if r["ev"] == "PSTOP" and r["oid"] == f["oid"])
    g = ctx.pick("ORX", x["utc"] + 3600)
    to = max(to, day_srv(g[1]["utc"], -6))
    faults = [f"{utc_to_srv(first_pstop) - 30} refuse_sltp 10016 3 {m}", f"{utc_to_srv(g[0]['utc'])} refuse_open 10016 1 20261210"]
    files, rc, out = wrun(ctx, "refused_sltp", frm, to, faults)
    rows = journal(files)
    res = {"trade": int(f["oid"]), "fault_counts": fault_counts(files), "errors": ev(rows, "ERROR")}
    sm = [r for r in ev(rows, "SLMOD", "D4H") if r.get("why") is None]
    bad = [r for r in sm if r.get("ok") == 0]
    good_after = [r for r in sm if r.get("ok") == 1 and bad and r["utc"] > bad[-1]["utc"]]
    gaps = [bad[i + 1]["utc"] - bad[i]["utc"] for i in range(len(bad) - 1)]
    chk(res, "three_refusals_journaled", len(bad) == 3, [(r["utc"], r.get("rc")) for r in bad])
    chk(res, "retried_10s_apart", all(gp >= 10 for gp in gaps), gaps)
    chk(res, "placed_after", len(good_after) >= 1)
    pd4 = wpos(files, "D4H")
    tr = pd4[(pd4.u_in >= f["utc"]) & (pd4.u_in <= f["utc"] + 300)]
    chk(res, "d4h_exit_as_clean_run", len(tr) == 1 and int(tr.iloc[0].t_out) == int(p.t_out) and float(tr.iloc[0].px_out) == float(p.px_out),
        tr[["t_out", "px_out"]].to_dict("records") if len(tr) else None)
    orx = wpos(files, "ORX")
    no_orx = orx[(orx.u_in >= g[0]["utc"]) & (orx.u_in <= g[0]["utc"] + 300)]
    miss = [r for r in ev(rows, "MISSED", "ORX") if r["oid"] == g[0]["oid"]]
    chk(res, "refused_open_not_opened", len(no_orx) == 0 and len(miss) == 1 and len(ev(rows, "REFUSED", "ORX")) >= 1,
        [r.get("reason") for r in miss])
    return finish(res)


def w_freeze(ctx):
    """a stop move inside FREEZE_LEVEL: the broker refuses (10029), the old stop stays and the move is tried every 10 s; the
    paper's exit still closes the position"""
    f, x, p = ctx.pick("D4H", FROM + 60 * 86400, lambda f, x, p: sum(1 for r in ctx.rows if r["ev"] == "PSTOP" and r["oid"] == f["oid"]) >= 3)
    frm, to = day_srv(f["utc"]), day_srv(x["utc"], -6)
    faults = [f"{utc_to_srv(f['utc']) + 120} freeze XAUUSD.r 100000000", f"{utc_to_srv(x['utc']) - 600} freeze XAUUSD.r 0"]
    files, rc, out = wrun(ctx, "freeze", frm, to, faults)
    rows = journal(files)
    res = {"trade": int(f["oid"]), "errors": ev(rows, "ERROR")}
    sm = [r for r in ev(rows, "SLMOD", "D4H") if r.get("why") is None and r["utc"] < x["utc"] - 600]
    frozen = [r for r in sm if r.get("ok") == 0 and r.get("rc") == 10029]
    gaps = [frozen[i + 1]["utc"] - frozen[i]["utc"] for i in range(len(frozen) - 1)]
    chk(res, "frozen_refusals", len(frozen) >= 1, len(frozen))
    chk(res, "retried_10s_apart", all(gp >= 10 for gp in gaps), gaps[:10])
    pd4 = wpos(files, "D4H")
    tr = pd4[(pd4.u_in >= f["utc"]) & (pd4.u_in <= f["utc"] + 300)]
    closed = len(tr) == 1 and not pd.isna(tr.iloc[0].get("t_out"))
    chk(res, "closed_with_the_paper", closed and abs(int(tr.iloc[0].u_out) - int(x["utc"])) <= 120,
        {"real_out": int(tr.iloc[0].u_out) if closed else None, "paper_exit": int(x["utc"]), "reason": x.get("reason")})
    return finish(res)


def w_requote_timeout(ctx):
    """a requote (retried, filled once); a timeout whose order was made (found by the one-intent-one-trade search: adopted,
    nothing sent again); a timeout whose order was not made (sent again once the reads are stable): one position each"""
    a = ctx.pick("BKB", FROM + 20 * 86400)
    b = ctx.pick("BKB", a[1]["utc"] + 3600)
    c = ctx.pick("BKB", b[1]["utc"] + 3600)
    frm, to = day_srv(a[0]["utc"]), day_srv(c[1]["utc"], -6)
    m = 20261203
    faults = [f"{utc_to_srv(a[0]['utc'])} refuse_open 10004 1 {m}", f"{utc_to_srv(b[0]['utc'])} timeout_open_done 1 {m}",
              f"{utc_to_srv(c[0]['utc'])} timeout_open_none 1 {m}"]
    files, rc, out = wrun(ctx, "requote_timeout", frm, to, faults)
    rows = journal(files)
    res = {"fault_counts": fault_counts(files), "errors": ev(rows, "ERROR")}
    pb = wpos(files, "BKB")
    for k, (fx, xx, px) in (("requote", a), ("timeout_done", b), ("timeout_none", c)):
        tr = pb[(pb.u_in >= fx["utc"]) & (pb.u_in <= fx["utc"] + 300)]
        chk(res, k + "_one_position", len(tr) == 1, tr[["position", "t_in", "px_in"]].to_dict("records"))
        if len(tr):
            chk(res, k + "_exit_as_clean", int(tr.iloc[0].t_out) == int(px.t_out))
    chk(res, "never_two_at_once", overlap_max(pb) == 1, overlap_max(pb))
    chk(res, "adopted_after_timeout", any(r.get("why") in ("order", "deal_in", "position") for r in ev(rows, "ADOPT", "BKB")),
        [r.get("why") for r in ev(rows, "ADOPT", "BKB")])
    return finish(res)


def w_slow_reply(ctx):
    """a slow reply: the answer says timeout and the order, deal and position appear 3 s later: nothing is sent again, the
    position is adopted, one position"""
    a = ctx.pick("F1B", FROM + 40 * 86400)
    frm, to = day_srv(a[0]["utc"]), day_srv(a[1]["utc"], -6)
    faults = [f"{utc_to_srv(a[0]['utc'])} slow_open 3 1 20261205"]
    files, rc, out = wrun(ctx, "slow_reply", frm, to, faults)
    rows = journal(files)
    res = {"fault_counts": fault_counts(files), "errors": ev(rows, "ERROR")}
    pf = wpos(files, "F1B")
    tr = pf[(pf.u_in >= a[0]["utc"]) & (pf.u_in <= a[0]["utc"] + 300)]
    sends = [r for r in ev(rows, "SEND", "F1B") if r["oid"] == a[0]["oid"]]
    chk(res, "one_position", len(tr) == 1, tr[["position", "t_in"]].to_dict("records"))
    chk(res, "sent_once", len(sends) == 1, [(r["utc"], r.get("result")) for r in sends])
    chk(res, "adopted", any(r["oid"] == a[0]["oid"] for r in ev(rows, "ADOPT", "F1B")))
    if len(tr):
        chk(res, "exit_as_clean", int(tr.iloc[0].t_out) == int(a[2].t_out))
    return finish(res)


def w_dup(ctx):
    """the broker makes an open twice: the newer position is closed at the next pass (DUP), the older one follows the paper"""
    a = ctx.pick("NQB", FROM + 50 * 86400)
    frm, to = day_srv(a[0]["utc"]), day_srv(a[1]["utc"], -6)
    files, rc, out = wrun(ctx, "broker_dup", frm, to, [f"{utc_to_srv(a[0]['utc'])} dup_open 1 20261207"])
    rows = journal(files)
    res = {"fault_counts": fault_counts(files), "errors": ev(rows, "ERROR")}
    pn = wpos(files, "NQB")
    tr = pn[(pn.u_in >= a[0]["utc"]) & (pn.u_in <= a[0]["utc"] + 300)].sort_values("position")
    chk(res, "two_made", len(tr) == 2, len(tr))
    if len(tr) == 2:
        old, new = tr.iloc[0], tr.iloc[1]
        chk(res, "newer_closed_dup", any(int(r["ticket"]) == int(new.position) for r in ev(rows, "DUP", "NQB")) and int(new.t_out) - int(new.t_in) <= 60)
        chk(res, "older_follows_paper", int(old.t_out) == int(a[2].t_out) and float(old.px_out) == float(a[2].px_out))
    return finish(res)


def w_n30_reversal(ctx):
    """an N30 reversal (the lab exits at bar e, the opposite entry fills at e + 1 min) whose close is refused for a minute:
    the close is retried into the new stamp's minute, the new entry waits for it (one intent, one trade: the old trade's OUT
    deal at or after the new stamp does not block it), never two positions"""
    # the lab has no N30 reversal in sample (an exit at a check followed by the opposite entry one minute later): the pair is
    # built from a real N30 trade that exits by time (order A, the lab's own row) and an opposite market order B activating on
    # the bar after A's exit bar, held one hour
    res = {"errors": []}
    fa, xa, pa = ctx.pick("N30", FROM + 10 * 86400, lambda f, x, p: x.get("reason") == "time")
    e = xa["utc"]
    rows_a = script_rows("N30")
    ra = rows_a[rows_a.oid == fa["oid"]]
    rb = pd.DataFrame([order_row("N30", e + 60, -fa["side"], stop_dist=abs(fa["px"] - fa["st0"]), x=e + 60 + 3600)])
    pairs = pd.concat([ra.astype(str), rb.astype(str)], ignore_index=True)
    frm, to = day_srv(fa["utc"]), day_srv(e, -10)
    clean_files = os.path.join(OUT, "n30_reversal_ref")
    wrun(ctx, "n30_reversal_ref", frm, to, None, codes=["N30"], override={"N30": pairs})
    pbr = wpos(clean_files, "N30")
    pbr = pbr[(pbr.u_in >= e + 60) & (pbr.u_in <= e + 360)].iloc[0]
    files, rc, out = wrun(ctx, "n30_reversal", frm, to, [f"{utc_to_srv(e)} refuse_close 10006 6 20261201"], codes=["N30"],
                          override={"N30": pairs})
    rows = journal(files)
    res.update({"fault_counts": fault_counts(files), "errors": ev(rows, "ERROR"), "exit_bar": e, "new_stamp": e + 60})
    pn = wpos(files, "N30")
    a = pn[(pn.u_in >= fa["utc"]) & (pn.u_in <= fa["utc"] + 300)]
    b = pn[(pn.u_in >= e + 60) & (pn.u_in <= e + 360)]
    chk(res, "old_closed_in_new_minute", len(a) == 1 and e + 60 <= int(a.iloc[0].u_out) < e + 120, a[["u_out"]].to_dict("records"))
    chk(res, "new_sent_in_its_minute", len(b) == 1 and e + 60 <= int(b.iloc[0].u_in) < e + 120, b[["u_in"]].to_dict("records"))
    chk(res, "never_two_at_once", overlap_max(pn) == 1, overlap_max(pn))
    chk(res, "new_exit_as_clean", len(b) == 1 and int(b.iloc[0].t_out) == int(pbr.t_out))
    chk(res, "six_refusals", fault_counts(files).get("refuse_close 10006", 0) == 6)
    return finish(res)


def w_deal_future(ctx):
    """a timeout whose order was made, its order and deal stamped 5 s after the terminal's clock and its position listed 10 s
    later: HistorySelect(0, TimeTradeServer() + 86400) still finds them (R5 e): nothing is sent again, one position"""
    a = ctx.pick("BKE", FROM + 70 * 86400)
    frm, to = day_srv(a[0]["utc"]), day_srv(a[1]["utc"], -6)
    files, rc, out = wrun(ctx, "deal_future", frm, to, [f"{utc_to_srv(a[0]['utc'])} timeout_open_done 1 20261204 5 10"])
    rows = journal(files)
    res = {"fault_counts": fault_counts(files), "errors": ev(rows, "ERROR")}
    pe = wpos(files, "BKE")
    tr = pe[(pe.u_in >= a[0]["utc"]) & (pe.u_in <= a[0]["utc"] + 300)]
    sends = [r for r in ev(rows, "SEND", "BKE") if r["oid"] == a[0]["oid"]]
    chk(res, "one_position", len(tr) == 1, tr[["position", "t_in"]].to_dict("records"))
    chk(res, "sent_once", len(sends) == 1, [(r["utc"], r.get("result")) for r in sends])
    chk(res, "deal_after_clock", len(tr) == 1 and int(tr.iloc[0].t_in) == utc_to_srv(a[0]["utc"]) + 2 + 5)
    chk(res, "exit_as_clean", len(tr) == 1 and int(tr.iloc[0].t_out) == int(a[2].t_out))
    return finish(res)


def w_stops(ctx):
    """R4: a position listed 3 s after its fill whose stop the broker dropped gets its stop back (5 s after its open); a stop
    removed by hand is put back; a stop removed by hand whose move is refused -> the position is closed (SLFIX)"""
    a = ctx.pick("BKB", FROM + 90 * 86400)
    b = ctx.pick("BKB", a[1]["utc"] + 3600, lambda f, x, p: x["utc"] - f["utc"] > 4 * 3600)
    c = ctx.pick("BKB", b[1]["utc"] + 3600, lambda f, x, p: x["utc"] - f["utc"] > 4 * 3600)
    frm, to = day_srv(a[0]["utc"]), day_srv(c[1]["utc"], -6)
    m = 20261203
    tb, tc = utc_to_srv(b[0]["utc"]) + 1800, utc_to_srv(c[0]["utc"]) + 1800
    faults = [f"{utc_to_srv(a[0]['utc'])} drop_sl 3 1 {m}", f"{tb} sl_remove {m}", f"{tc} refuse_sltp 10016 5 {m}", f"{tc} sl_remove {m}"]
    files, rc, out = wrun(ctx, "stops", frm, to, faults)
    rows = journal(files)
    res = {"fault_counts": fault_counts(files), "errors": ev(rows, "ERROR")}
    pb = wpos(files, "BKB")
    ta = pb[(pb.u_in >= a[0]["utc"]) & (pb.u_in <= a[0]["utc"] + 300)]
    sm = ev(rows, "SLMOD", "BKB")
    put_a = [r for r in sm if len(ta) and r.get("ticket") == int(ta.iloc[0].position) and r.get("from") == 0 and r.get("ok") == 1]
    chk(res, "dropped_stop_put_back", len(put_a) == 1 and srv_to_utc(int(ta.iloc[0].t_in)) + 5 <= put_a[0]["utc"] <= srv_to_utc(int(ta.iloc[0].t_in)) + 10,
        [(r["utc"], r.get("to")) for r in put_a])
    tbp = pb[(pb.u_in >= b[0]["utc"]) & (pb.u_in <= b[0]["utc"] + 300)]
    put_b = [r for r in sm if len(tbp) and r.get("ticket") == int(tbp.iloc[0].position) and r.get("from") == 0 and r.get("ok") == 1]
    chk(res, "removed_stop_put_back", len(put_b) == 1 and srv_to_utc(tb) <= put_b[0]["utc"] <= srv_to_utc(tb) + 3, [(r["utc"]) for r in put_b])
    chk(res, "b_exit_as_clean", len(tbp) == 1 and int(tbp.iloc[0].t_out) == int(b[2].t_out))
    tcp = pb[(pb.u_in >= c[0]["utc"]) & (pb.u_in <= c[0]["utc"] + 300)]
    fix = ev(rows, "SLFIX", "BKB")
    chk(res, "slfix_closed", len(tcp) == 1 and len(fix) == 1 and int(tcp.iloc[0].t_out) <= tc + 5,
        {"slfix": [(r["utc"], r.get("why")) for r in fix], "t_out": int(tcp.iloc[0].t_out) if len(tcp) else None, "removed": tc})
    chk(res, "slfix_pushed", any("SLFIX" in p for p in pushes(files)))
    return finish(res)


def w_listed_late(ctx):
    """a restart while a D4H position is open, the terminal listing the positions 30 s late: reconcile waits for the
    position the history holds open, adopts it; nothing is sent again, one position, the exit as in the clean run"""
    f, x, p = ctx.pick("D4H", FROM + 120 * 86400, lambda f, x, p: x["utc"] - f["utc"] > 12 * 3600)
    frm, t1, to = day_srv(f["utc"]), utc_to_srv(f["utc"]) + 6 * 3600, day_srv(x["utc"], -6)
    t1 -= t1 % 60
    wrun(ctx, "listed_late", frm, t1, None)
    files, rc, out = wrun(ctx, "listed_late", t1, to, [f"{t1} hide_positions 30"], fresh=False)
    rows = journal(files)
    res = {"fault_counts": fault_counts(files), "errors": ev(rows, "ERROR")}
    pd4 = wpos(files, "D4H")
    tr = pd4[(pd4.u_in >= f["utc"]) & (pd4.u_in <= f["utc"] + 300)]
    adopt = [r for r in ev(rows, "ADOPT", "D4H") if r["oid"] == f["oid"]]
    rec = [r for r in rows if r["ev"] == "REBUILD"]
    chk(res, "one_position", len(tr) == 1, len(tr))
    chk(res, "adopted_after_listing", len(adopt) == 1 and adopt[0]["utc"] >= srv_to_utc(t1) + 30, [(r["utc"], r.get("why")) for r in adopt])
    chk(res, "sent_once", len([r for r in ev(rows, "SEND", "D4H") if r["oid"] == f["oid"]]) == 1)
    chk(res, "exit_as_clean", len(tr) == 1 and int(tr.iloc[0].t_out) == int(p.t_out) and float(tr.iloc[0].px_out) == float(p.px_out))
    chk(res, "two_rebuilds", len(rec) == 2)
    return finish(res)


def w_restart(ctx):
    """a restart mid-week, with positions open: every position of the clean run in the window is there again, the same
    (entries, exits, prices, lots), none twice"""
    frm, t1, to = srv("2021-06-07 00:00"), srv("2021-06-09 12:00"), srv("2021-06-14 00:00")
    wrun(ctx, "restart", frm, t1, None, env={"MOCK_TIMER_CALLS": "1"})
    files, rc, out = wrun(ctx, "restart", t1, to, None, fresh=False, env={"MOCK_TIMER_CALLS": "1"})
    rows = journal(files)
    res = {"errors": ev(rows, "ERROR")}
    ref_files = os.path.join(OUT, "restart_ref")
    wrun(ctx, "restart_ref", frm, to, None, env={"MOCK_TIMER_CALLS": "1"})
    a, b = wpos(files), wpos(ref_files)
    key = ["code", "t_in", "side"]
    m = b.merge(a, on=key, how="outer", suffixes=("_ref", "_rst"), indicator=True)
    both = m[m._merge == "both"]
    same = both[(both.t_out_ref == both.t_out_rst) & (both.px_in_ref == both.px_in_rst) & (both.px_out_ref == both.px_out_rst)]
    open_at_restart = int(((b.t_in < t1) & ((b.t_out > t1) | b.t_out.isna())).sum()) if len(b) else 0
    chk(res, "same_positions", len(m) == len(both) and len(same) == len(both),
        {"ref": len(b), "restart": len(a), "only_ref": int((m._merge == "left_only").sum()), "only_restart": int((m._merge == "right_only").sum()),
         "same_exits": len(same), "open_at_restart": open_at_restart})
    lots_diff = int((both.vol_ref != both.vol_rst).sum())
    chk(res, "same_lots", lots_diff == 0, lots_diff)
    chk(res, "positions_adopted", len(ev(rows, "ADOPT")) == open_at_restart, len(ev(rows, "ADOPT")))
    chk(res, "never_two_per_sleeve", all(overlap_max(a[a.code == c]) <= 1 for c in CODES))
    return finish(res)


def w_latebar(ctx):
    """a late revision of a gold bar while D4H and ORX positions are open: LATEBAR, a rebuild, the open positions adopted,
    no duplicate, no orphan"""
    f, x, p = ctx.pick("D4H", FROM + 150 * 86400, lambda f, x, p: x["utc"] - f["utc"] > 12 * 3600)
    frm, to = day_srv(f["utc"]), day_srv(x["utc"], -6)
    t = utc_to_srv(f["utc"]) + 3 * 3600
    t -= t % 60
    B = Bars(ctx.bars["XAUUSD.r"])
    while B.at(t) is None:
        t += 60
    files, rc, out = wrun(ctx, "latebar", frm, to, None, env={"MOCK_REVISE_XAUUSD.r": f"{t}@{t + 100}:0.05"})
    rows = journal(files)
    res = {"errors": ev(rows, "ERROR")}
    late = [r for r in rows if r["ev"] == "LATEBAR"]
    reb = [r for r in rows if r["ev"] == "REBUILD"]
    chk(res, "latebar_and_rebuild", len(late) >= 1 and len(reb) == 2, {"latebar": len(late), "rebuilds": len(reb)})
    adopt = [r for r in ev(rows, "ADOPT") if r["utc"] >= srv_to_utc(t + 100)]
    chk(res, "d4h_adopted", any(r["oid"] == f["oid"] for r in adopt), [(r["code"], r.get("why")) for r in adopt])
    pa = wpos(files)
    chk(res, "no_orphan_no_dup", not ev(rows, "ORPHAN") and not ev(rows, "DUP"))
    chk(res, "never_two_per_sleeve", all(overlap_max(pa[pa.code == c]) <= 1 for c in CODES))
    return finish(res)


def w_hole(ctx):
    """a hole of 2 hours inside the BTC session that stays (R13): BTC NOT_READY, GAP, accepted after 3 re-reads, READY;
    a BTC sleeve's intent meanwhile is skipped as NOTREADY; the next ones are taken"""
    f, x, p = ctx.pick("BKB", FROM + 100 * 86400)
    frm = utc_to_srv(f["utc"]) - 120
    to = day_srv(f["utc"], -36)
    a = frm - 20 * 86400
    a -= a % 86400
    while time.gmtime(a).tm_wday != 2:                          # a Wednesday, 10:00-12:00 server: inside the BTC session
        a -= 86400
    a += 10 * 3600
    files, rc, out = wrun(ctx, "hole", frm, to, None, env={"MOCK_HOLE_BTCUSD.r": f"{a}-{a + 7200}@0"})
    rows = journal(files)
    res = {"errors": ev(rows, "ERROR")}
    gaps = [r for r in rows if r["ev"] == "GAP" and r["code"] == "BTCUSD"]
    ready = [r for r in rows if r["ev"] == "READY" and r["code"] == "BTCUSD"]
    chk(res, "gap_then_accepted", any(r.get("accepted") == 1 for r in gaps), [(r["utc"], r.get("accepted")) for r in gaps][:4])
    chk(res, "ready_after", len(ready) == 1 and ready[0]["utc"] > srv_to_utc(frm) + 120, [r["utc"] for r in ready])
    sz = [r for r in ev(rows, "SIZE", live=True) if r["code"] in ("BKB", "F1B", "NQB")]
    first = sz[0] if sz else None
    chk(res, "first_btc_intent_notready", first is not None and first.get("skip") == "notready" and first["oid"] == f["oid"],
        (first or {}).get("skip"))
    later = [r for r in sz if ready and r["utc"] > ready[0]["utc"]]
    chk(res, "later_taken", any(r.get("skip") == "none" for r in later), len(later))
    return finish(res)


def w_notready_comment(ctx):
    """a restart while a BKB position is open, BTC never synchronized (NOT_READY for good) and the position's comment
    rewritten by the broker (P9): no BTC entry, the position keeps its stop and closes at LatestExit(POSITION_TIME)"""
    f, x, p = ctx.pick("BKB", FROM + 110 * 86400, lambda f, x, p: x.get("reason") == "time")
    frm, t1, to = day_srv(f["utc"]), utc_to_srv(f["utc"]) + 4 * 3600, day_srv(x["utc"], -6)
    t1 -= t1 % 60
    wrun(ctx, "notready_comment", frm, t1, None)
    files, rc, out = wrun(ctx, "notready_comment", t1, to, [f"{t1} comment 20261203 hello"], fresh=False,
                          env={"MOCK_UNSYNC_BTCUSD.r": f"{t1}-{to + 86400}"})
    rows = journal(files)
    res = {"fault_counts": fault_counts(files), "errors": ev(rows, "ERROR")}
    pb = wpos(files, "BKB")
    tr = pb[(pb.u_in >= f["utc"]) & (pb.u_in <= f["utc"] + 300)]
    cl = [r for r in ev(rows, "CLOSE", "BKB") if len(tr) and int(r["ticket"]) == int(tr.iloc[0].position)]
    chk(res, "closed_at_latest_exit", len(tr) == 1 and len(cl) >= 1 and cl[-1].get("why") == "latest_exit"
        and int(tr.iloc[0].u_out) == int(x["utc"]) + 2, {"u_out": int(tr.iloc[0].u_out) if len(tr) else None, "x": int(x["utc"]),
                                                          "why": [r.get("why") for r in cl]})
    sz = [r for r in ev(rows, "SIZE", live=True) if r["code"] in ("BKB", "F1B", "NQB") and r["utc"] >= srv_to_utc(t1)]
    chk(res, "no_btc_entry", all(r.get("skip") == "notready" for r in sz), sorted({r.get("skip") for r in sz}))
    nr = [r for r in rows if r["ev"] == "NOTREADY" and r["code"] == "BTCUSD" and r["utc"] >= srv_to_utc(t1)]
    chk(res, "btc_notready", len(nr) >= 1)
    return finish(res)


def w_magic0(ctx):
    """broker stop deals carrying magic 0: the closes are still the robot's (deals attach by position id): the positions,
    the ledger's balance at every sizing and the lots equal the run without the fault; no orphan"""
    f, x, p = ctx.pick("ORX", FROM + 130 * 86400, lambda f, x, p: x.get("reason") == "stop")
    frm, to = day_srv(f["utc"]), day_srv(x["utc"], -48)
    files, rc, out = wrun(ctx, "magic0", frm, to, None, env={"MOCK_STOP_MAGIC0": "1"})
    ref_files, _, _ = wrun(ctx, "magic0_ref", frm, to, None)
    rows, rr = journal(files), journal(ref_files)
    res = {"errors": ev(rows, "ERROR")}
    d = deals(files)
    sl0 = d[(d.reason == DEAL_SL) & (d.magic == 0)]
    chk(res, "stop_deals_magic0", len(sl0) >= 1, len(sl0))
    a, b = wpos(files), wpos(ref_files)
    cols = ["t_in", "t_out", "px_out", "vol"]
    chk(res, "same_positions", len(a) == len(b) and a[cols].fillna(-1).equals(b[cols].fillna(-1)), {"world": len(a), "ref": len(b)})
    s1 = [(r["oid"], r.get("B"), r.get("lots")) for r in ev(rows, "SIZE", live=True)]
    s2 = [(r["oid"], r.get("B"), r.get("lots")) for r in ev(rr, "SIZE", live=True)]
    chk(res, "same_sizing", s1 == s2 and len(s1) > 0, len(s1))
    chk(res, "no_orphan", not ev(rows, "ORPHAN"))
    return finish(res)


def open_at(pos, t_srv):
    """robot positions of a run open at server time t"""
    if not len(pos):
        return pos
    return pos[(pos.t_in < t_srv) & ((pos.t_out > t_srv) | pos.t_out.isna())]


def w_clock(ctx):
    """the computer clock 1 h off during the US/EU summer-time gap week (R7): CLOCK (no entries) at the next check, the robot
    positions closed after 10 min, flat until the offset matches again, then entries again"""
    frm, t_bad, t_ok, to = srv("2021-03-16 00:00"), srv("2021-03-16 10:00"), srv("2021-03-16 13:00"), srv("2021-03-18 00:00")
    files, rc, out = wrun(ctx, "clock", frm, to, [f"{t_bad} gmt_shift 3600", f"{t_ok} gmt_shift 0"])
    rows = journal(files)
    res = {"errors": ev(rows, "ERROR")}
    ck = [r for r in rows if r["ev"] == "CLOCK"]
    st = [(r["utc"], r.get("state")) for r in ck]
    wrong = [u for u, s in st if s == "wrong"]
    flat = [u for u, s in st if s == "flat"]
    okk = [u for u, s in st if s == "ok"]
    chk(res, "wrong_within_10_min", len(wrong) == 1 and srv_to_utc(t_bad) <= wrong[0] <= srv_to_utc(t_bad) + 660, st)
    chk(res, "flat_10_min_later", len(flat) == 1 and wrong and 600 <= flat[0] - wrong[0] <= 660)
    chk(res, "ok_after", len(okk) == 1 and srv_to_utc(t_ok) <= okk[0] <= srv_to_utc(t_ok) + 120)
    sz = [r for r in ev(rows, "SIZE", live=True) if wrong and okk and wrong[0] <= r["utc"] < okk[0]]
    chk(res, "entries_blocked", all(r.get("skip") in ("clock",) for r in sz), sorted({r.get("skip") for r in sz}))
    cl = [r for r in ev(rows, "CLOSE") if r.get("why") == "clock"]
    pa = wpos(files)
    still = open_at(pa, utc_to_srv(flat[0]) + 30) if flat else pa
    chk(res, "flat_closes", len(cl) >= 1 and len(still) == 0, {"closes": len(cl), "open_after_flat": len(still)})
    later = [r for r in ev(rows, "SIZE", live=True) if okk and r["utc"] > okk[0]]
    chk(res, "entries_again", any(r.get("skip") == "none" for r in later), len(later))
    return finish(res)


def w_payments(ctx):
    """a deposit and a withdrawal mid-week: B moves by them, w (the week's robot close money in units) does not; w at each
    sizing equals the robot close money of the week before the stamp over the week unit, from the deal history"""
    frm, to = srv("2021-05-03 00:00"), srv("2021-05-08 00:00")
    pays = [(srv("2021-05-05 12:00"), 50000), (srv("2021-05-06 12:00"), -30000)]
    files, rc, out = wrun(ctx, "payments", frm, to, None, payments=pays, env={"MOCK_TIMER_CALLS": "1"})
    rows = journal(files)
    res = {"errors": ev(rows, "ERROR")}
    d = deals(files)
    rob = d[d.type.isin([0, 1]) & d.magic.between(20261201, 20261289)]
    pos_money = {}
    for pid, g in d[d.type.isin([0, 1])].groupby("position"):
        if not g.magic.between(20261201, 20261289).any():
            continue
        o = g[g.entry == 1]
        if len(o):
            t = srv_to_utc(int(o.time.iloc[-1]))
            stamp = t - t % 60 + (60 if int(o.reason.iloc[-1]) in (4, 5, 6) else 0)
            pos_money[pid] = (stamp, float((g.profit + g.commission + g.swap).sum()))
    wk0 = srv_to_utc(srv("2021-05-03 00:00"))
    bad = []
    sz = ev(rows, "SIZE", live=True)
    for r in sz:
        if r.get("unit", 0) <= 0 or r.get("skip") == "settle":
            continue
        S = r["utc"]
        money = sum(m for st, m in pos_money.values() if wk0 <= st < S)
        want = money / r["unit"]
        if abs(want - r["w"]) > 1e-9 * max(1, abs(want)):
            bad.append((S, r["w"], want))
    chk(res, "w_is_close_money_only", not bad and len(sz) > 0, {"sizings": len(sz), "bad": bad[:5]})
    bs = [(r["utc"], r["B"]) for r in sz]
    after_dep = [b for u, b in bs if u >= srv_to_utc(pays[0][0])]
    chk(res, "B_moves_with_the_deposit", bool(after_dep) and after_dep[0] > 140000, after_dep[:1])
    chk(res, "robot_trades", len(rob) > 0, len(rob))
    return finish(res)


def w_settle(ctx):
    """balance and history out of step (R16): a deposit whose balance shows 30 s after its deal: an intent meanwhile waits
    (SETTLE, no SIZE line) and is sized and sent inside its window; 90 s: B(T) accepted after 60 s and pushed"""
    f, x, p = ctx.pick("BKB", FROM + 160 * 86400)
    res = {"errors": []}
    for skew in (30, 90):
        t_dep = utc_to_srv(f["utc"]) - 10
        frm, to = day_srv(f["utc"]), day_srv(f["utc"], -6)
        name = f"settle_{skew}"
        files, rc, out = wrun(ctx, name, frm, to, None, payments=[(t_dep, 20000)], env={"MOCK_PAY_SKEW": str(-skew)})
        rows = journal(files)
        res["errors"] += ev(rows, "ERROR")
        sz = [r for r in ev(rows, "SIZE", "BKB", live=True) if r["oid"] == f["oid"]]
        se = [r for r in ev(rows, "SEND", "BKB") if r["oid"] == f["oid"]]
        stl = [(r["utc"], r.get("state")) for r in rows if r["ev"] == "SETTLE"]
        dep_u = srv_to_utc(t_dep)
        if skew == 30:
            chk(res, "30s_sized_once_after", len(sz) == 1 and sz[0]["utc"] == f["utc"], [(r["utc"], r.get("skip")) for r in sz])
            chk(res, "30s_sent_after_settle", len(se) == 1 and dep_u + 30 <= se[0]["utc"] <= f["utc"] + 300, [r["utc"] for r in se])
            chk(res, "30s_moving_then_ok", ("moving" in [s for _, s in stl]) and ("ok" in [s for _, s in stl]), stl[:6])
        else:
            acc = [u for u, s in stl if s == "accepted"]
            mov = [u for u, s in stl if s == "moving"]                # (the deposit is booked at the next bar event)
            chk(res, "90s_accepted_after_60s", len(acc) >= 1 and mov and 60 <= acc[0] - mov[0] <= 62, stl[:8])
            chk(res, "90s_pushed", any("desaccord" in q for q in pushes(files)))
            chk(res, "90s_sent_inside_window", len(se) == 1 and se[0]["utc"] <= f["utc"] + 300, [r["utc"] for r in se])
    return finish(res)


def w_plan(ctx):
    """plan start (R3): unset on a real account on the VPS -> OBSERVE (no entry, daily push), exits still run; 0 on demo ->
    the first deal; still to come -> OBSERVE until it, then entries; set after earlier manual losses -> B(T) leaves them out"""
    frm, to = srv("2021-07-05 00:00"), srv("2021-07-08 00:00")
    res = {"errors": []}
    files, _, _ = wrun(ctx, "plan_real_unset", frm, to, None, env={"MOCK_ACCOUNT": "real", "MOCK_VPS": "1", "MOCK_INPUT_InpPlanStart": "0",
                                                                   "MOCK_TIMER_CALLS": "1"})
    rows = journal(files)
    res["errors"] += ev(rows, "ERROR")
    sz = ev(rows, "SIZE", live=True)
    chk(res, "real_unset_observe", len(sz) > 0 and all(r.get("skip") == "observe" for r in sz) and len(deals(files)) == 0,
        sorted({r.get("skip") for r in sz}))
    chk(res, "real_unset_daily_push", sum("InpPlanStart" in q for q in pushes(files)) >= 2)
    files, _, _ = wrun(ctx, "plan_demo_zero", frm, to, None, env={"MOCK_INPUT_InpPlanStart": "0", "MOCK_TIMER_CALLS": "1"})
    rows = journal(files)
    pl = [r for r in rows if r["ev"] == "PLAN" and r.get("src") == "first_deal"]
    d = deals(files)
    chk(res, "demo_zero_first_deal", len(pl) == 1 and len(d) > 0 and int(pl[0]["T"]) == int(d.time.min()), [r.get("T") for r in pl])
    t_plan = srv("2021-07-06 12:00")
    files, _, _ = wrun(ctx, "plan_future", frm, to, None, env={"MOCK_INPUT_InpPlanStart": str(t_plan), "MOCK_TIMER_CALLS": "1"})
    rows = journal(files)
    sz = ev(rows, "SIZE", live=True)
    before = [r for r in sz if r["utc"] < srv_to_utc(t_plan)]
    after = [r for r in sz if r["utc"] >= srv_to_utc(t_plan)]
    chk(res, "future_observe_then_trade", before and all(r.get("skip") == "observe" for r in before) and any(r.get("skip") == "none" for r in after),
        {"before": sorted({r.get("skip") for r in before}), "after": sorted({r.get("skip") for r in after})})
    dl = os.path.join(OUT, "plan_losses_deals.csv")
    os.makedirs(OUT, exist_ok=True)
    with open(dl, "w") as h:
        h.write(f"{frm + 3600},{frm + 7200},XAUUSD.r,1,1.0,1800.0,1600.0,777,-20000.0,0,0,3\n")
    t_plan2 = frm + 3 * 3600
    files, _, _ = wrun(ctx, "plan_losses", frm, to, None, env={"MOCK_INPUT_InpPlanStart": str(t_plan2), "MOCK_DEALS": dl, "MOCK_TIMER_CALLS": "1"})
    rows = journal(files)
    sz = [r for r in ev(rows, "SIZE", live=True) if r["utc"] >= srv_to_utc(t_plan2)]
    chk(res, "losses_before_plan_left_out", bool(sz) and abs(sz[0]["P_in"] - 80000.0) < 0.01 and abs(sz[0]["B"] - 80000.0) < 2000,
        {"P_in": sz[0]["P_in"] if sz else None, "B": sz[0]["B"] if sz else None})
    return finish(res)


def w_plan_stop(ctx):
    """the plan stop (SPEC 6.1) armed from the start (InpStopArmPaid 0) with a 0.3 % fall: at the first booked close that
    leaves B under 99.7 % of ref -> STOP, every robot position closed, no entry after (stopped), also after a restart"""
    frm, t1, to = srv("2021-08-02 00:00"), srv("2021-08-04 00:00"), srv("2021-08-06 00:00")
    env = {"MOCK_INPUT_InpStopArmPaid": "0", "MOCK_INPUT_InpStopFallPct": "0.3", "MOCK_TIMER_CALLS": "1"}
    wrun(ctx, "plan_stop", frm, t1, None, env=env)
    files, _, _ = wrun(ctx, "plan_stop", t1, to, None, env=env, fresh=False)
    rows = journal(files)
    res = {"errors": ev(rows, "ERROR")}
    st = [r for r in rows if r["ev"] == "STOP"]
    chk(res, "stop_latched", len(st) >= 1, [(r["utc"], r.get("src")) for r in st])
    if st:
        t_stop = min(r["utc"] for r in st)
        after = [r for r in ev(rows, "SIZE", live=True) if r["utc"] > t_stop + 60]
        chk(res, "no_entry_after", all(r.get("skip") == "stopped" for r in after) and not [r for r in ev(rows, "SEND") if r["utc"] > t_stop + 60],
            sorted({r.get("skip") for r in after}))
        pa = wpos(files)
        chk(res, "flat_after", len(open_at(pa, utc_to_srv(t_stop) + 120)) == 0)
        chk(res, "pushed", any("STOP du plan" in q for q in pushes(files)))
        chk(res, "latched_after_restart", any(r["utc"] >= srv_to_utc(t1) for r in st))
    return finish(res)


def deals_file(name, lines):
    p = os.path.join(OUT, name + "_deals.csv")
    os.makedirs(OUT, exist_ok=True)
    with open(p, "w") as h:
        h.write("\n".join(lines) + "\n")
    return p


def w_guard(ctx):
    """the disaster guard (SPEC 6.2, P3, R2): (b) a manual loss leaves B at 40 % of ref while robot positions are open: GUARD,
    every robot position closed with requests of magic 20261290 (so the history holds the guard's mark), no entry, and after a
    restart still latched; (b) with no robot position open: the minimum-lot mark trade, refused while the market is closed
    (10018) and tried again every 60 s until its deal exists; (c) alone: a mark deal in the history keeps GUARD latched with
    the equity well above 50 % of ref; (a) the live equity: a hand position's floating loss takes the equity under 50 %"""
    res = {"errors": []}
    # (b) with positions open, then a restart
    frm, t1, to = srv("2021-09-06 00:00"), srv("2021-09-08 00:00"), srv("2021-09-09 00:00")
    pa = open_at(ctx.pos, srv("2021-09-07 10:00"))
    t_loss = srv("2021-09-07 10:00")
    dl = deals_file("guard_b", [f"{t_loss - 60},{t_loss},XAUUSD.r,1,1.0,1800.0,1200.0,777,-60000.0,0,0,3"])
    env = {"MOCK_DEALS": dl, "MOCK_TIMER_CALLS": "1"}
    wrun(ctx, "guard_b", frm, t1, None, env=env)
    files, _, _ = wrun(ctx, "guard_b", t1, to, None, env=env, fresh=False)
    rows = journal(files)
    res["errors"] += ev(rows, "ERROR")
    g = [r for r in rows if r["ev"] == "GUARD"]
    chk(res, "b_latched", any(r["utc"] < srv_to_utc(t1) for r in g), [(r["utc"], r.get("src")) for r in g][:6])
    cl = [r for r in ev(rows, "CLOSE") if r.get("why") == "guard"]
    chk(res, "b_closed_with_mark_magic", len(pa) > 0 and len(cl) >= 1 and all(int(r["magic"]) == 20261290 for r in cl),
        {"open_then": len(pa), "closes": [(r["code"], r["magic"]) for r in cl]})
    d = deals(files)
    chk(res, "b_mark_deals_in_history", int((d.magic == 20261290).sum()) >= 1)
    after = [r for r in ev(rows, "SIZE", live=True) if r["utc"] > srv_to_utc(t_loss) + 60]
    # (the plan stop, armed from the start since P_in = B(T) >= 12,000, latches too at the next robot close: STOPPED comes
    # first in the lab's order of the checks)
    chk(res, "b_no_entry_after", all(r.get("skip") in ("guard", "stopped") for r in after)
        and not [r for r in ev(rows, "SEND") if r["utc"] > srv_to_utc(t_loss) + 60], sorted({r.get("skip") for r in after}))
    chk(res, "b_latched_after_restart", any(r["utc"] >= srv_to_utc(t1) for r in g))
    # (b) with no robot position open: the mark trade, refused while the market is closed
    frm2, to2 = srv("2021-09-13 00:00"), srv("2021-09-14 00:00")
    t_loss2 = srv("2021-09-13 01:30")
    dl2 = deals_file("guard_mark", [f"{t_loss2 - 60},{t_loss2},XAUUSD.r,1,1.0,1800.0,1200.0,777,-60000.0,0,0,3"])
    # (each pass tries the four markets in turn: 12 refusals = 3 passes)
    files, _, _ = wrun(ctx, "guard_mark", frm2, to2, [f"{t_loss2} refuse_open 10018 12 20261290"], codes=["N30"],
                       env={"MOCK_DEALS": dl2})
    rows = journal(files)
    res["errors"] += ev(rows, "ERROR")
    mk = [r for r in rows if r["ev"] == "MARK"]
    failed = [r["utc"] for r in mk if r.get("state") == "failed"]
    done = [r for r in mk if r.get("open") == 1 and r.get("closed") == 1]
    gaps = [failed[i + 1] - failed[i] for i in range(len(failed) - 1)]
    chk(res, "mark_refused_three_times_60s_apart", len(failed) == 3 and all(60 <= x <= 61 for x in gaps), gaps)
    chk(res, "mark_done_after", len(done) == 1 and failed and done[0]["utc"] >= failed[-1] + 60)
    d = deals(files)
    chk(res, "mark_deals", int((d.magic == 20261290).sum()) == 2, int((d.magic == 20261290).sum()))
    chk(res, "mark_pushed_once", sum("marque" in q for q in pushes(files)) == 1)
    # (c) alone: a mark deal of an earlier run, equity at 100 % of ref
    t_m = srv("2021-09-13 02:00")
    dl3 = deals_file("guard_c", [f"{t_m},{t_m + 1},XAUUSD.r,1,0.01,1800.0,1800.0,20261290,0.0,0,0,3"])
    files, _, _ = wrun(ctx, "guard_c", srv("2021-09-14 00:00"), srv("2021-09-15 00:00"), None, env={"MOCK_DEALS": dl3, "MOCK_TIMER_CALLS": "1"})
    rows = journal(files)
    g = [r for r in rows if r["ev"] == "GUARD"]
    sz = ev(rows, "SIZE", live=True)
    chk(res, "c_latched_from_mark", any(r.get("src") == "history_c" for r in g) and sz and all(r.get("skip") == "guard" for r in sz),
        {"guard": [r.get("src") for r in g], "skips": sorted({r.get("skip") for r in sz})})
    # (a) the live equity: 3 lots of gold bought by hand on 6 August 2021, the 9 August fall
    files, _, _ = wrun(ctx, "guard_a", srv("2021-08-05 00:00"), srv("2021-08-10 00:00"), [f"{srv('2021-08-06 10:00')} hand_open XAUUSD.r 1 3"],
                       env={"MOCK_BALANCE": "10000", "MOCK_TIMER_CALLS": "1"})
    rows = journal(files)
    res["errors"] += ev(rows, "ERROR")
    g = [r for r in rows if r["ev"] == "GUARD"]
    chk(res, "a_latched_on_equity", any(r.get("src") == "equity" and r["equity"] <= 0.5 * r["ref"] for r in g),
        [(r["utc"], r.get("src"), r.get("equity"), r.get("ref")) for r in g][:3])
    d = deals(files)
    hand = d[d.magic == 777]
    chk(res, "a_hand_position_untouched", len(hand) == 1 and int(hand.entry.iloc[0]) == 0, len(hand))
    return finish(res)


def w_lock(ctx):
    """the daily lock (SPEC 6.3) at one stake: the day's booked robot money reaches -1 x rate x the day's first balance ->
    LOCK, the robot positions closed, no entry until the next server day, entries again then"""
    d = deals(ctx.files)
    rob = d[d.type.isin([0, 1]) & d.magic.between(20261201, 20261289) & (d.entry == 1)].copy()
    rob["day"] = rob.time // 86400
    money = rob.groupby("day").profit.sum()
    days = [int(k) for k, v in money.items() if v < -700 and k * 86400 > FROM + 30 * 86400 and time.gmtime(int(k) * 86400).tm_wday <= 3]
    res = {"errors": []}
    if not days:
        return finish(dict(res, checks={"losing_day_found": False}))
    day = days[0] * 86400
    files, _, _ = wrun(ctx, "lock", day - 86400, day + 2 * 86400, None, env={"MOCK_INPUT_InpDailyLockStakes": "1", "MOCK_TIMER_CALLS": "1"})
    rows = journal(files)
    res["errors"] += ev(rows, "ERROR")
    lk = [r for r in rows if r["ev"] == "LOCK"]
    chk(res, "locked_that_day", any(day <= utc_to_srv(r["utc"]) < day + 86400 for r in lk), [r["utc"] for r in lk])
    blocked, flat, again = [], [], []
    for r in lk:                                                # each LOCK holds until the end of its own server day
        t_l = r["utc"]
        d0 = utc_to_srv(t_l) - utc_to_srv(t_l) % 86400
        end = srv_to_utc(d0 + 86400)
        blocked += [q.get("skip") for q in ev(rows, "SIZE", live=True) if t_l < q["utc"] < end]
        flat.append(len(open_at(wpos(files), utc_to_srv(t_l) + 30)))
        again += [q.get("skip") for q in ev(rows, "SIZE", live=True) if end <= q["utc"] < end + 86400]
    chk(res, "no_entry_rest_of_day", lk and all(k == "lock" for k in blocked), sorted(set(blocked)))
    chk(res, "flat_after_lock", lk and all(n == 0 for n in flat), flat)
    chk(res, "entries_next_day", "none" in again, sorted(set(again)))
    return finish(res)


def w_friday(ctx):
    """the Friday close at 22:00 server (SPEC 6.4): every robot position closed then, no entry until Monday 00:00; and a close
    missed while the terminal was off: a position opened before it is closed at the first pass of the next week"""
    frm, to = srv("2021-10-04 00:00"), srv("2021-10-12 00:00")
    env = {"MOCK_INPUT_InpFridayCloseHHMM": "2200", "MOCK_TIMER_CALLS": "1"}
    files, _, _ = wrun(ctx, "friday", frm, to, None, env=env)
    rows = journal(files)
    res = {"errors": ev(rows, "ERROR")}
    fc = srv("2021-10-08 22:00")
    pa = wpos(files)
    cl = [r for r in ev(rows, "CLOSE") if r.get("why") == "friday"]
    chk(res, "closed_at_friday_close", len(open_at(pa, fc + 60)) == 0 and len(cl) >= 1 and all(fc <= utc_to_srv(r["utc"]) <= fc + 120 for r in cl),
        {"closes": len(cl), "open_after": len(open_at(pa, fc + 60))})
    wk = [r for r in ev(rows, "SIZE", live=True) if srv_to_utc(fc) <= r["utc"] < srv_to_utc(srv("2021-10-11 00:00"))]
    chk(res, "no_entry_weekend", all(r.get("skip") == "friday" for r in wk), sorted({r.get("skip") for r in wk}))
    mon = [r for r in ev(rows, "SIZE", live=True) if r["utc"] >= srv_to_utc(srv("2021-10-11 00:00"))]
    chk(res, "entries_monday", any(r.get("skip") == "none" for r in mon), len(mon))
    # missed: the first part ends Friday 21:00 with positions open, the second starts Monday 00:30
    t_off, t_on = srv("2021-10-08 21:00"), srv("2021-10-11 00:30")
    wrun(ctx, "friday_missed", frm, t_off, None, env=env)
    open_before = open_at(wpos(os.path.join(OUT, "friday_missed")), t_off)
    files, _, _ = wrun(ctx, "friday_missed", t_on, to, None, env=env, fresh=False)
    rows = journal(files)
    cl = [r for r in ev(rows, "CLOSE") if r.get("why") == "friday_missed"]
    pm = wpos(files)
    gone = [int(pm[pm.position == r.position].iloc[0].t_out) for r in open_before.itertuples() if len(pm[pm.position == r.position])]
    # (the broker's own stops still work while the terminal is off: a position may be closed by its stop meanwhile)
    chk(res, "missed_close_done_monday", len(open_before) >= 1 and len(cl) >= 1 and len(gone) == len(open_before)
        and all(t < t_on or t_on <= t < t_on + 600 for t in gone),
        {"open_friday": len(open_before), "friday_missed": [(r["code"], r["utc"]) for r in cl], "closed_at": gone})
    return finish(res)


def w_vps_tradefalse(ctx):
    """InpTrade false on the VPS copy (R14), restarted with D4H and ORX positions open: no new entry (notrade), the exits and
    the stop upkeep still run: the positions close as in the clean run"""
    f, x, p = ctx.pick("D4H", FROM + 200 * 86400, lambda f, x, p: x["utc"] - f["utc"] > 12 * 3600)
    t1 = utc_to_srv(f["utc"]) + 3600
    t1 -= t1 % 60
    frm, to = day_srv(f["utc"], 30), day_srv(x["utc"], -12)
    wrun(ctx, "vps_tradefalse", frm, t1, None, env={"MOCK_VPS": "1", "MOCK_TIMER_CALLS": "1"})
    p1 = wpos(os.path.join(OUT, "vps_tradefalse"))
    open_then = open_at(p1, t1) if len(p1) else p1
    for r in open_then.itertuples():                            # the second part runs past their exits in the clean run
        rr = ctx.pos[(ctx.pos.code == r.code) & (ctx.pos.t_in == r.t_in)]
        if len(rr) and not pd.isna(rr.iloc[0].get("t_out")):
            to = max(to, int(rr.iloc[0].t_out) + 3600)
    files, _, _ = wrun(ctx, "vps_tradefalse", t1, to, None, env={"MOCK_VPS": "1", "MOCK_INPUT_InpTrade": "false", "MOCK_TIMER_CALLS": "1"},
                       fresh=False)
    rows = journal(files)
    res = {"errors": ev(rows, "ERROR")}
    sz = [r for r in ev(rows, "SIZE", live=True) if r["utc"] >= srv_to_utc(t1)]
    chk(res, "no_new_entry", sz and all(r.get("skip") == "notrade" for r in sz) and not [r for r in ev(rows, "SEND") if r["utc"] >= srv_to_utc(t1)],
        sorted({r.get("skip") for r in sz}))
    pa = wpos(files)
    ref = ctx.pos
    same = 0
    for r in open_then.itertuples():
        q = pa[pa.position == r.position]
        rr = ref[(ref.code == r.code) & (ref.t_in == r.t_in)]
        if len(q) and len(rr) and q.iloc[0].get("t_out") == rr.iloc[0].get("t_out") and not pd.isna(q.iloc[0].get("t_out")):
            same += 1
    chk(res, "exits_still_done", len(open_then) >= 1 and same == len(open_then), {"open_at_restart": len(open_then), "same_exit": same})
    return finish(res)


def w_observer(ctx):
    """a real account off the VPS (SPEC 4.9) is an observer: it sends nothing at all (no SEND, CLOSE, SLMOD, MARK), keeps its
    journal, and pushes WATCH when a robot position outlives its paper exit by more than 5 min (the VPS copy may be dead)"""
    f, x, p = ctx.pick("BKB", FROM + 190 * 86400, lambda f, x, p: x.get("reason") == "time")
    t1 = utc_to_srv(f["utc"]) + 3600
    t1 -= t1 % 60
    frm, to = day_srv(f["utc"]), day_srv(x["utc"], -6)
    wrun(ctx, "observer", frm, t1, None)
    files, _, _ = wrun(ctx, "observer", t1, to, None, env={"MOCK_ACCOUNT": "real", "MOCK_VPS": "0"}, fresh=False)
    rows = journal(files)
    res = {"errors": ev(rows, "ERROR")}
    seg2 = [r for r in rows if r["utc"] >= srv_to_utc(t1)]
    chk(res, "no_request", not [r for r in seg2 if r["ev"] in ("SEND", "CLOSE", "SLMOD", "MARK")], counts(seg2))
    init = [r for r in rows if r["ev"] == "INIT" and r.get("observer") == 1]
    chk(res, "observer_flag", len(init) >= 1)
    w = [r for r in ev(rows, "WATCH", "BKB")]
    chk(res, "watch_after_paper_exit", len(w) >= 1 and x["utc"] + 300 < w[0]["utc"] <= x["utc"] + 300 + 120, [(r["utc"], r.get("due")) for r in w])
    chk(res, "watch_pushed", any("WATCH" in q for q in pushes(files)))
    return finish(res)


def w_instances(ctx):
    """the instance lock (SPEC 4.9, R10): a second copy while one runs is refused at OnInit (ERROR, the EA unloads); a lock
    whose heartbeat is 15 s old (a crashed copy) is taken over (TAKEOVER, push) and the copy trades"""
    frm, to = srv("2021-11-01 00:00"), srv("2021-11-02 00:00")
    res = {"errors": []}
    files, rc, out = wrun(ctx, "instance_second", frm, to, ["0 lock_hold 0", "0 lock_beat 999999"], expect_fail=True)
    rows = journal(files)
    chk(res, "second_copy_refused", rc == 3 and any("another copy" in str(r.get("what", "")) for r in ev(rows, "ERROR")), {"exit": rc})
    files, rc, out = wrun(ctx, "instance_crashed", frm, to, ["0 lock_hold 15"], env={"MOCK_TIMER_CALLS": "1"})
    rows = journal(files)
    res["errors"] += ev(rows, "ERROR")
    chk(res, "crashed_taken_over", len([r for r in rows if r["ev"] == "TAKEOVER"]) == 1 and any("relais" in q for q in pushes(files)))
    chk(res, "then_trades", len(ev(rows, "SEND")) >= 1, len(ev(rows, "SEND")))
    return finish(res)


def gold_bar(ctx, t_srv):
    B = Bars(ctx.bars["XAUUSD.r"])
    b = B.at(t_srv)
    return B, b


def w_p5(ctx):
    """P5: a stop entry whose paper trade is stopped on its own fill bar: the late intent is not sent (MISSED reason=exited),
    nothing is opened"""
    t = srv("2021-06-16 21:00")                                 # (14:00 New York; the bar must have a range)
    B, b = gold_bar(ctx, t)
    while b is None or (b["h"] - b["l"]) < 60 or b["o"] - b["l"] < 20:
        t += 60
        b = B.at(t)
    sc = B.sc
    lv = (b["o"] + 5) / sc                                      # touched: the bar's high is above
    st = (b["l"] + 3) / sc                                      # under the fill, above the bar's low: stopped on the fill bar
    u = srv_to_utc(t)
    o = pd.DataFrame([order_row("ORX", u, 1, etype=1, level=lv, stop=st, x=u + 3600, expiry=u + 60)])
    files, _, _ = wrun(ctx, "p5_exited", t - 6 * 3600, t + 6 * 3600, None, codes=["ORX"], override={"ORX": o})
    rows = journal(files)
    res = {"errors": ev(rows, "ERROR"), "bar": int(t)}
    oid = int(o.oid.iloc[0])
    fill = [r for r in ev(rows, "PFILL", "ORX") if r["oid"] == oid]
    ex = [r for r in ev(rows, "PEXIT", "ORX") if r["oid"] == oid]
    chk(res, "paper_filled_and_stopped_on_its_bar", len(fill) == 1 and len(ex) == 1 and ex[0]["bar"] == fill[0]["bar"] == u
        and ex[0].get("reason") == "stop", [(r["ev"], r["bar"], r.get("reason")) for r in fill + ex])
    ms = [r for r in ev(rows, "MISSED", "ORX") if r["oid"] == oid]
    chk(res, "missed_exited", len(ms) == 1 and ms[0].get("reason") == "exited")
    chk(res, "nothing_sent", not ev(rows, "SEND", "ORX") and len(wpos(files, "ORX")) == 0)
    return finish(res)


def w_p4(ctx):
    """P4: a gap-rule exit inside the gold closure (17:15 New York) and the bar of 16:59 (c0 - 1) missing: the real position
    closes at the barrier of 16:59 at the last quote (RealExitMinute); the paper books its exit at the last kept bar before
    the closure (16:58) once x + 30 min has passed (PREVISE)"""
    day = srv("2021-06-15 00:00")
    t_open = day + 20 * 3600                                    # 13:00 New York
    c0m1 = day + 23 * 3600 + 59 * 60                            # 16:59 New York (server 23:59)
    B = Bars(ctx.bars["XAUUSD.r"])
    keep = B.rec[B.rec["t"] != c0m1]
    path = os.path.join(OUT, "bars", "XAUUSD.r_is_no_c0m1.bin")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_bars(path, B.digits, keep)
    bars = dict(ctx.bars, **{"XAUUSD.r": path})
    u = srv_to_utc(t_open)
    x = srv_to_utc(day + 86400 + 15 * 60)                       # 17:15 New York
    o = pd.DataFrame([order_row("D4H", u, 1, stop_dist=40.0, x=x, x_gap=1)])
    files, _, _ = wrun(ctx, "p4_closure", t_open - 6 * 3600, day + 86400 + 4 * 3600, None, codes=["D4H"], override={"D4H": o}, bars=bars)
    rows = journal(files)
    res = {"errors": ev(rows, "ERROR")}
    p = wpos(files, "D4H")
    cl = ev(rows, "CLOSE", "D4H")
    want_t = srv_to_utc(c0m1) + 2
    b58 = B.at(c0m1 - 60)
    sm = SLIP["XAUUSD.r"][0] * 1e-4
    chk(res, "real_closed_at_c0_minus_1", len(p) == 1 and int(p.iloc[0].u_out) == want_t and cl and cl[0].get("why") == "time",
        {"u_out": int(p.iloc[0].u_out) if len(p) else None, "want": want_t})
    chk(res, "real_price_last_quote", len(p) == 1 and float(p.iloc[0].px_out) == round(b58["c"] / B.sc, 2) * (1 - sm))
    rv = [r for r in rows if r["ev"] == "PREVISE" and r["code"] == "D4H"]
    chk(res, "paper_revised_to_16_58", len(rv) == 1 and rv[0]["bar"] == srv_to_utc(c0m1 - 60) and rv[0]["px"] == round(b58["o"] / B.sc, 2) * (1 - sm),
        [(r["bar"], r["px"]) for r in rv])
    return finish(res)


def w_good_friday(ctx):
    """R8: a gap-rule exit on Good Friday (2 April 2021, 12:00 New York): gold is closed from Thursday 17:00; the real
    position closes at the barrier of Thursday 16:59 (RealExitMinute), at the price the paper books (its last kept bar
    before x: Thursday 16:59, PREVISE once x + 30 min has passed)"""
    t_open = srv("2021-04-01 17:00")                            # Thursday 10:00 New York
    x = srv_to_utc(srv("2021-04-02 19:00"))                     # Friday 12:00 New York
    u = srv_to_utc(t_open)
    o = pd.DataFrame([order_row("D4H", u, 1, stop_dist=40.0, x=x, x_gap=1)])
    files, _, _ = wrun(ctx, "good_friday", t_open - 6 * 3600, srv("2021-04-05 06:00"), None, codes=["D4H"], override={"D4H": o})
    rows = journal(files)
    res = {"errors": ev(rows, "ERROR")}
    p = wpos(files, "D4H")
    c0m1 = srv("2021-04-01 23:59")                              # Thursday 16:59 New York
    rv = [r for r in rows if r["ev"] == "PREVISE" and r["code"] == "D4H"]
    chk(res, "real_closed_thursday_16_59", len(p) == 1 and int(p.iloc[0].u_out) == srv_to_utc(c0m1) + 2,
        {"u_out": int(p.iloc[0].u_out) if len(p) else None, "want": srv_to_utc(c0m1) + 2})
    chk(res, "paper_revised_to_thursday_16_59", len(rv) == 1 and rv[0]["bar"] == srv_to_utc(c0m1), [(r["bar"], r["px"]) for r in rv])
    chk(res, "same_price", len(p) == 1 and len(rv) == 1 and float(p.iloc[0].px_out) == rv[0]["px"])
    return finish(res)


def w_switches(ctx):
    """the change switches (SPEC 3.9): on a demo account with S0.75r, H2 and K1 on, the sizing carries the frozen
    equal-swing factors (BKB 0.771793, F1E 0.750978, the others 1); on a real account (VPS) with S0.75r on: journaled and
    pushed"""
    frm, to = srv("2021-11-08 00:00"), srv("2021-11-13 00:00")
    files, _, _ = wrun(ctx, "switches_demo", frm, to, None, env={"MOCK_INPUT_InpS075": "1", "MOCK_INPUT_InpH2": "1", "MOCK_INPUT_InpK1": "1",
                                                                 "MOCK_TIMER_CALLS": "1"})
    rows = journal(files)
    res = {"errors": ev(rows, "ERROR")}
    f = {}
    for r in ev(rows, "SIZE", live=True):
        f.setdefault(r["code"], set()).add(r["f"])
    chk(res, "factors", f.get("BKB") == {0.771793} and f.get("F1E") == {0.750978} and all(v == {1.0} for k, v in f.items() if k not in ("BKB", "F1E")),
        {k: sorted(v) for k, v in f.items()})
    files, _, _ = wrun(ctx, "switches_real", frm, frm + 86400, None, env={"MOCK_ACCOUNT": "real", "MOCK_VPS": "1", "MOCK_INPUT_InpS075": "1",
                                                                          "MOCK_TIMER_CALLS": "1"})
    rows = journal(files)
    on_real = [r for r in rows if r["ev"] == "INIT" and r.get("on_real") == 1]
    chk(res, "real_journaled_and_pushed", len(on_real) == 1 and any("REEL" in q for q in pushes(files)))
    return finish(res)


def w_tester(ctx):
    """the tester mode (R12): TimeGMT() = TimeTradeServer(), no clock check (no CLOCK line), the same real trades as the
    plain run of the same days"""
    frm, to = srv("2021-12-06 00:00"), srv("2021-12-11 00:00")
    files, _, _ = wrun(ctx, "tester", frm, to, None, env={"MOCK_TESTER": "1", "MOCK_TIMER_CALLS": "1"})
    ref, _, _ = wrun(ctx, "tester_ref", frm, to, None, env={"MOCK_TIMER_CALLS": "1"})
    rows = journal(files)
    res = {"errors": ev(rows, "ERROR")}
    chk(res, "no_clock_line", not [r for r in rows if r["ev"] == "CLOCK"])
    a, b = wpos(files), wpos(ref)
    cols = ["code", "t_in", "px_in", "t_out", "px_out", "vol"]
    chk(res, "same_trades", len(a) > 0 and len(a) == len(b) and a[cols].fillna(-1).equals(b[cols].fillna(-1)), {"tester": len(a), "plain": len(b)})
    tst = [r for r in rows if r["ev"] == "INIT" and r.get("tester") == 1]
    chk(res, "tester_flag", len(tst) >= 1)
    return finish(res)


def same_dirs(a, b):
    r = subprocess.run(["diff", "-r", "-q", a, b], capture_output=True, text=True)
    return r.returncode == 0, r.stdout[-600:]


def w_sanitizer(ctx):
    """the sanitizer build (address, undefined behaviour, bounds-checked containers) replays three months of the ten script
    sleeves and two fault worlds with journals and deals identical to the plain build's"""
    res = {"errors": []}
    if "san" not in ctx.exe:
        return finish(dict(res, checks={"sanitizer_build": False}))
    frm, to = FROM, srv("2021-04-01 00:00")
    env = {"MOCK_TIMER_CALLS": "1", "ASAN_OPTIONS": "detect_leaks=1"}
    fp, _, _ = wrun(ctx, "san_plain", frm, to, None, env=env)
    fs, _, _ = wrun(ctx, "san_san", frm, to, None, env=env, exe="san")
    ok_j, d_j = same_dirs(os.path.join(fp, "ClaudeRobot"), os.path.join(fs, "ClaudeRobot"))
    ok_d = deals(fp).equals(deals(fs))
    chk(res, "clean_q1_identical", ok_j and ok_d and len(deals(fp)) > 0, {"journal": d_j, "deals": len(deals(fp))})
    for name in ("requote_timeout", "slow_reply"):
        src = os.path.join(OUT, name, "_mock", "faults_in.txt")
        if not os.path.exists(src):
            chk(res, name + "_identical", False, "the plain world did not run")
            continue
        faults = [ln.rstrip("\n") for ln in open(src) if ln.strip()]
        rows_p = journal(os.path.join(OUT, name))
        init = [r for r in rows_p if r["ev"] == "INIT"][0]
        start = utc_to_srv(init["utc"]) - 2
        last = [r for r in rows_p if r["ev"] == "INIT" and "deinit" in r][-1]
        stop = utc_to_srv(last["utc"]) - 2 + 60
        fa, _, _ = wrun(ctx, name + "_p2", start, stop, faults)
        fb, _, _ = wrun(ctx, name + "_san", start, stop, faults, exe="san")
        ok_j, d_j = same_dirs(os.path.join(fa, "ClaudeRobot"), os.path.join(fb, "ClaudeRobot"))
        chk(res, name + "_identical", ok_j and deals(fa).equals(deals(fb)), d_j)
    return finish(res)


WORLDS = [w_refused_sltp, w_freeze, w_requote_timeout, w_slow_reply, w_dup, w_n30_reversal, w_deal_future, w_stops, w_listed_late,
          w_restart, w_latebar, w_hole, w_notready_comment, w_magic0, w_clock, w_payments, w_settle, w_plan, w_plan_stop, w_guard,
          w_lock, w_friday, w_vps_tradefalse, w_observer, w_instances, w_p5, w_p4, w_good_friday, w_switches, w_tester, w_sanitizer]
NOT_HERE = {
    "a GFP Friday that is a NYSE holiday with gold quoted after 13:30 (R8)": "the skip is GFP's rule (step G); the script sleeves "
    "replay the lab's orders, so K's T8 with the real rules covers it; the exit side of R8 is w_good_friday",
    "a US100 half day quoted after 13:15 (P6)": "the mask (step B, T2) and N30/OC4's grid (step D); nothing of the execution layer",
    "a spread spike inside ORX's London range (9.5)": "ORX's levels and stop (step G); the follower sends what the paper fills",
}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--no-sanitize", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args(argv)
    names = ["clean_fast", "clean_tick", "clean_h"] + [w.__name__[2:] for w in WORLDS]
    if a.list:
        print("\n".join(names))
        return 0
    want = set(a.only.split(",")) if a.only else None
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    summary = {"what": "T8 worlds of step J (script sleeves)", "worlds": {}}
    ok = True
    tree = make_tree()
    try:
        exes, warns = binaries(tree, sanitize=not a.no_sanitize)
    except BuildError as e:
        print(str(e)[-4000:])
        return 1
    summary["builds"] = {k: {"warnings": len(v), "first": v[:3]} for k, v in warns.items()}
    ok &= all(len(v) == 0 for v in warns.values())
    bars = bar_paths()
    if want is None or "clean_fast" in want or any(n not in ("clean_tick", "clean_h") for n in want):
        res, _ = clean(None, "clean_fast", exes["plain"], bars)
        res["pass"] = judge_clean(res, "fast")
        summary["worlds"]["clean_fast"] = {k: v for k, v in res.items() if k not in ("diffs", "files")}
        ok &= res["pass"]
        print(f"{'PASS' if res['pass'] else 'FAIL'} clean_fast {res['sec']} s")
    if want is None or "clean_tick" in want:
        res, _ = clean(None, "clean_tick", exes["plain"], bars, env={"MOCK_TICK": "1"}, mode="tick")
        res["pass"] = judge_clean(res, "tick")
        summary["worlds"]["clean_tick"] = {k: v for k, v in res.items() if k not in ("diffs", "files", "lab")}
        ok &= res["pass"]
        print(f"{'PASS' if res['pass'] else 'FAIL'} clean_tick {res['sec']} s")
    if want is None or "clean_h" in want:
        hb = dict(bars, **{"XAUUSD.r": h_bars(bars["XAUUSD.r"])})
        res, _ = clean(None, "clean_h", exes["h6"], hb, h_pts=3, codes=["GFP", "D4H", "ORX"])
        res["pass"] = judge_clean(res, "fast")
        summary["worlds"]["clean_h"] = {k: v for k, v in res.items() if k not in ("diffs", "files", "lab")}
        ok &= res["pass"]
        print(f"{'PASS' if res['pass'] else 'FAIL'} clean_h {res['sec']} s")
    ctx = Ctx(exes, bars)
    for w in WORLDS:
        name = w.__name__[2:]
        if want is not None and name not in want:
            continue
        t1 = time.time()
        try:
            r = w(ctx)
        except Exception as e:                                  # a world that cannot run fails, with its reason
            import traceback
            r = {"pass": False, "exception": repr(e), "trace": traceback.format_exc()[-1500:]}
        r["sec"] = round(time.time() - t1, 1)
        r["doc"] = (w.__doc__ or "").strip().split("\n")[0]
        summary["worlds"][name] = r
        ok &= bool(r.get("pass"))
        print(f"{'PASS' if r.get('pass') else 'FAIL'} {name} {r['sec']} s" + ("" if r.get("pass") else "  " + json.dumps(r.get("checks", r.get("exception")), default=str)[:400]))
    summary["not_in_this_test"] = NOT_HERE
    summary["pass"] = bool(ok)
    summary["sec"] = round(time.time() - t0, 1)
    with open(os.path.join(OUT, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1, default=str)
    n = len(summary["worlds"])
    n_ok = sum(1 for v in summary["worlds"].values() if v.get("pass"))
    print(f"test_worlds: {n_ok}/{n} worlds passed, builds {'0 warnings' if all(len(v) == 0 for v in warns.values()) else 'WITH WARNINGS'}, "
          f"{summary['sec']} s -> {os.path.relpath(os.path.join(OUT, 'summary.json'), ROBOT)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
