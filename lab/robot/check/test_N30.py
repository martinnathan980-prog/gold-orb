"""T4 N30 noise30 (step D): every decision and every trade of N30 over the whole in-sample period, against the lab.

    python3 -I lab/robot/check/test_N30.py [--world all|is|holes|restarts] [--tag is|y2021] [--no-sanitize]
                                           [--sanitize-holes] [--full-tree] [--trace] [--fresh] [--verbose]

SPEC 7 T4/T5 for src/CR_Rule_IdxUS.mqh (CRuleN30; CRuleOC4 is checked by test_OC4.py, which imports this file).
The EA is built from a tree under build/test_idxus_tree/src/ (SPEC 8: the finished files of S0, A, B, C and I as they
are in src/, this step's CR_Rule_IdxUS.mqh, and the S0 stubs of the files of the steps running beside it, E, F, G, H, J
and K, read from commit STUB_COMMIT with git show; --full-tree takes every file from src/ instead). It is compiled as
check/build.py compiles a harness EA (to_cpp.py, the same g++ flags, CR_HARNESS, CR_XAU_COMM_PTS=0), against a private
copy of the mock whose mock_faults.h is S0's neutral stub (J owns that file). The EA replays the bars of the four symbols
exported by check/export_frames.py through the S0 driver (CR_Main's minute contract), InpTrade false (SPEC 8: no order
is sent), with the real clock (A), bars (B), paper (C) and account (I). The lab references are check/ref_lab.py's, on the
frame rebuilt from the same US100 bars: make_orders (every signal) and r2.run (the official call). Three worlds:
  is        the in-sample bars (--tag is: 2013-2021; y2021: 2021 only), the references ref_lab.py --frame rebuilt
            --tag is (made when missing); also replayed under the sanitizer build.
  holes     the same US100 frame with 349 windows of bars removed (hole_cuts: aimed at the paths in-sample data barely
            reaches, chosen from the lab's own orders: a hole right after an entry bar (HOLE_RULE), an empty decision
            window, a stale price, reversals whose next bar comes late, never comes before 15:55, or is the last bar
            before a hole, an exit falling back before a hole (PREVISE), a missing or late 09:30 bar, a short OC4
            candle, an empty 09:34 window, a hole after 09:34, a day without session, a trading day under 600 bars, a
            missing 16:00 price, and 200 random holes). Its bar file and frame use the tag idxholes; the references are
            ref_lab.py --frame rebuilt --tag idxholes, i.e. the lab's code on the frame with the same holes.
  restarts  the in-sample bars replayed in 26 processes (MOCK_FROM / MOCK_TO): 25 restarts inside open trades, 4
            minutes before a check or 09:34, between a reversal's exit bar and its entry bar, in a gap question, at
            random; each start rebuilds the rules from the depth of SPEC 2.2 (60 days of US100). Compared on the lines
            the live passes wrote (live_rows).
Checks, in each world:
  1. Decisions. Every DEC line of the sleeve (orders and rule exits) is resolved on the frame with the paper's own
     reading of a CrOrder (SPEC 2.4, 2.5), written here independently of the EA: activation = the first kept bar in
     [t_from, t_to], or for an after_exit_of order the first kept bar after the bar where that CrExit resolved; exit =
     the bar where a later CrExit of the order resolved, else goldlab.data.exit_index of x_sched (the lab's gap rule);
     void when no bar activates it, and (void_le) when its exit bar does not follow its activation bar. The resolved
     orders must equal the lab's make_orders orders one for one: entry bar, side, exit bar equal; the stop equal (N30's
     stop is built from bar prices: exact) or, for OC4's ATR distance, within 1e-12 relative (SPEC 7).
  2. Every order the EA emitted that the paper voids is classified with the lab's own grid: a window without a kept
     bar (the lab's EI = -1), a reversal with no kept bar after the exit's before 15:55 (the lab's ei + 1 >= xi), or
     void_le (the lab's HOLE_RULE ei >= xi: the check's bar is the last bar before a data hole through 15:55). An
     unclassified void fails the test. In the holes world each targeted path must be reached (coverage > 0); in the
     restarts world some restarts must fall inside open trades and some decisions just after a restart.
  3. Paper trades. The journal's paper trades (compare.paper_trades: PFILL + PEXIT or PREVISE, PVOID dropped) equal
     r2.run's trades on the same frame: entry and exit minute, side, reason equal, prices within 1e-12 relative
     (compare.cmp_trades); trades still open at the frame end are excluded.
  4. Razors: the lab's decisions within 1e-9 of a threshold are counted and listed (SPEC 7).
  5. The journal parses, holds no ERROR and no SEND line; the build has no warning.
  6. The sanitizer build (address, undefined behaviour, checked containers) writes a byte-identical journal (world is;
     --sanitize-holes adds the holes world).
--trace builds with -DCR_IDX_TRACE (DEC info lines with the rule's statistics) for diagnosis; --fresh ignores cached
replays. Builds and replays are cached (stamps of the sources, flags and bars), so test_OC4.py reuses this file's runs.
Outputs: check/out/test_idxus/ (journals, <CODE>_<world>_result.json, holes_world.json). In sample only: every frame and
trade file is read with the 2022-01-01 cut inside the read call.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
_NB = os.environ.get("NUMBA_CACHE_DIR", "")
if not _NB.startswith("/tmp/"):
    _NB = "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/numba"
os.environ["NUMBA_CACHE_DIR"] = _NB

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROBOT = os.path.dirname(HERE)
LAB = os.path.dirname(ROBOT)
sys.path.insert(0, HERE)
import compare  # noqa: E402
from build import replay  # noqa: E402

OUT = os.path.join(HERE, "out", "test_idxus")
CUT = pd.Timestamp("2022-01-01", tz="UTC")
NY = "America/New_York"
STUB_COMMIT = "7b87227"                 # the end of part 1: E-H, J and K files are still S0's stubs there
SYMS = ("XAUUSD.r", "US100.r", "BTCUSD.r", "ETHUSD.r")
# SPEC 8: the files D's tests may include as they are (S0, A, B, C, I, D) ...
FINISHED = ("ClaudeRobot.mq5", "CR_Types.mqh", "CR_Registry.mqh", "CR_Journal.mqh", "CR_Main.mqh", "CR_Rule_Script.mqh",
            "CR_Clock.mqh", "CR_Math.mqh", "CR_Bars.mqh", "CR_Paper.mqh", "CR_Ledger.mqh", "CR_Sizing.mqh",
            "CR_Rule_IdxUS.mqh")
# ... and the S0 stubs of everything else (steps E, F, G, H, J running beside D, and K's generated file)
STUBS = ("CR_Rule_Brk72.mqh", "CR_Rule_F1.mqh", "CR_F1Model.mqh", "CR_Rule_NqBtc.mqh", "CR_Rule_GoldFri.mqh",
         "CR_Rule_Orb.mqh", "CR_Rule_Donch.mqh", "CR_Broker.mqh", "CR_Follower.mqh", "CR_Guards.mqh", "CR_Golden.mqh")
CODE_ID = {"N30": 1, "OC4": 2}
REL = 1e-12                             # SPEC 7: rolling values and the stops built on them
RAZOR = 1e-9                            # SPEC 7: decisions this close to a threshold are listed


def log(msg):
    print(msg, flush=True)


# ======================================================================================== the EA
def make_tree(full=False):
    """the source tree of the build (under build/, git-ignored); returns its directory"""
    d = os.path.join(ROBOT, "build", "test_idxus_tree", "src")
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(d)
    src = os.path.join(ROBOT, "src")
    names = sorted(n for n in os.listdir(src) if n.endswith((".mqh", ".mq5")))
    missing = set(FINISHED + STUBS) - set(names)
    if missing:
        raise RuntimeError(f"src/ lacks {sorted(missing)}")
    for n in names:
        if full or n not in STUBS:
            shutil.copy(os.path.join(src, n), os.path.join(d, n))
            continue
        with open(os.path.join(d, n), "wb") as f:
            f.write(git_stub(f"src/{n}"))
    return d


def tool(args):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", NUMBA_CACHE_DIR=_NB)
    r = subprocess.run([sys.executable, "-I"] + args, env=env, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"{os.path.basename(args[0])} failed ({r.returncode}): {(r.stdout + r.stderr)[-3000:]}")


def inputs(tag):
    """the bar exports of a tag and the lab references of N30 and OC4 on the frames rebuilt from them (S0's tools)"""
    bars = {s: os.path.join(HERE, "out", "bars", f"{s}_{tag}.bin") for s in SYMS}
    man = os.path.join(HERE, "out", f"manifest_{tag}.json")
    if not all(os.path.exists(p) for p in bars.values()) or not os.path.exists(man):
        win = ["--from", "2021-01-01", "--to", "2022-01-01"] if tag == "y2021" else []
        tool([os.path.join(HERE, "export_frames.py")] + win + ["--tag", tag])
    ref = os.path.join(HERE, "out", "ref", f"rebuilt_{tag}")
    if not all(os.path.exists(os.path.join(ref, c, f)) for c in CODE_ID for f in ("orders.parquet", "trades.parquet")):
        tool([os.path.join(HERE, "ref_lab.py"), "--frame", "rebuilt", "--tag", tag, "--sleeves", ",".join(CODE_ID), "--no-changes"])
    last = {m["broker"]: int(pd.Timestamp(m["last"]).value // 10**9) for m in json.load(open(man))}
    return bars, ref, last


def stamp_of(tree, defines, sanitize, bars):
    h = hashlib.sha256()
    for n in sorted(os.listdir(tree)):
        h.update(n.encode())
        h.update(open(os.path.join(tree, n), "rb").read())
    for n in ("to_cpp.py", "mql5_shim.h", "mock_replay.h", "build.py"):
        h.update(open(os.path.join(HERE, n), "rb").read())
    h.update(repr((sorted(defines), sanitize)).encode())
    for s in sorted(bars):
        st = os.stat(bars[s])
        h.update(f"{s}:{st.st_size}:{int(st.st_mtime)}".encode())
    return h.hexdigest()


def world_is(tag="is"):
    """the in-sample world of a tag: the bar exports, the rebuilt US100 frame and the references on it"""
    bars, ref, last = inputs(tag)
    return {"name": tag, "tag": tag, "bars": bars, "ref": ref, "frame": os.path.join(HERE, "out", "frames", f"us100_{tag}.parquet"),
            "last_us100": last["US100.r"]}


def git_stub(path):
    """a file as it was at STUB_COMMIT (S0's stub), read with git show"""
    r = subprocess.run(["git", "-C", ROBOT, "show", f"{STUB_COMMIT}:./{path}"], capture_output=True)
    if r.returncode:
        raise RuntimeError(f"git show {STUB_COMMIT}:{path} failed: {r.stderr.decode()[-500:]}")
    if b"S0 STUB" not in r.stdout:
        raise RuntimeError(f"{path} at {STUB_COMMIT} is not an S0 stub")
    return r.stdout


def ea_exe(sanitize=False, trace=False, full=False):
    """the replay binary of the tree (rebuilt only when the sources or flags changed); returns (exe, warnings, stamp, name).
    It is built as check/build.py builds a harness EA (its translator, flags and defines), except that the mock is compiled
    from a private copy whose mock_faults.h is S0's neutral stub (step J owns that file and runs beside D)"""
    from build import CXX, SAN, BuildError, translate
    tree = make_tree(full)
    defines = ["CR_HARNESS", "CR_XAU_COMM_PTS=0"] + (["CR_IDX_TRACE"] if trace else [])
    name = "test_idxus" + ("_trace" if trace else "") + ("_full" if full else "") + ("_san" if sanitize else "")
    faults = open(os.path.join(HERE, "mock_faults.h"), "rb").read() if full else git_stub("check/mock_faults.h")
    h = hashlib.sha256(stamp_of(tree, defines, sanitize, {}).encode() + faults)
    stamp = h.hexdigest()
    work = os.path.join(ROBOT, "build", name)
    sp = os.path.join(work, "stamp.json")
    if os.path.exists(sp):
        old = json.load(open(sp))
        if old.get("stamp") == stamp and os.path.exists(old.get("exe", "")):
            return old["exe"], old["warnings"], stamp, name
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)
    for n in ("mock_replay.h", "mql5_shim.h"):
        shutil.copy(os.path.join(HERE, n), os.path.join(work, n))
    with open(os.path.join(work, "mock_faults.h"), "wb") as f:
        f.write(faults)
    ea = os.path.join(work, "ea.cpp")
    translate(os.path.join(tree, "ClaudeRobot.mq5"), ea)
    run = os.path.join(work, "run.cpp")
    with open(run, "w") as f:
        f.write('#include "mock_replay.h"\n')
        f.write(f'#include "{ea}"\n')
    exe = os.path.join(work, "replay")
    cmd = CXX + (SAN if sanitize else []) + [f"-D{d}" for d in defines] + ["-I", work, "-I", tree, run, "-o", exe]
    r = subprocess.run(cmd, capture_output=True, text=True)
    warn = [ln for ln in r.stderr.splitlines() if "warning:" in ln]
    if r.returncode:
        raise BuildError(f"compile failed ({name}):\n" + r.stderr[-20000:])
    with open(sp, "w") as f:
        json.dump({"stamp": stamp, "exe": exe, "warnings": warn, "cmd": " ".join(cmd)}, f)
    return exe, warn, stamp, name


def run_ea(world, sanitize=False, trace=False, full=False, fresh=False):
    """replay the world's bars (one process, or one per segment when the world has restarts); returns {files, stamp,
    replay, wall_s, warnings, cached}"""
    bars = world["bars"]
    exe, warn, est, name = ea_exe(sanitize, trace, full)
    files = os.path.join(OUT, f"{world['name']}_{name}")
    h = hashlib.sha256((est + repr(world.get("restarts_srv", []))).encode())
    for sy in sorted(bars):
        st = os.stat(bars[sy])
        h.update(f"{sy}:{st.st_size}:{int(st.st_mtime)}".encode())
    stamp = h.hexdigest()
    sp = os.path.join(files, "stamp.json")
    if not fresh and os.path.exists(sp):
        old = json.load(open(sp))
        if old.get("stamp") == stamp and os.path.isdir(os.path.join(files, "ClaudeRobot")):
            old["cached"] = True
            return old
    env = {"MOCK_INPUT_InpTrade": "false"}
    if sanitize:
        env["ASAN_OPTIONS"] = "detect_leaks=1"
    cuts = list(world.get("restarts_srv", []))
    outs, wall = [], 0.0
    for k in range(len(cuts) + 1):
        frm = cuts[k - 1] if k > 0 else None
        to = cuts[k] if k < len(cuts) else None
        out, w = replay(exe, files, bars, env=env, fresh=(k == 0), frm=frm, to=to, timeout=7200)
        outs.append(out)
        wall += w
    res = {"stamp": stamp, "files": files, "replay": outs[0] if len(outs) == 1 else f"{len(outs)} processes; last: {outs[-1]}",
           "wall_s": round(wall, 1), "warnings": warn, "sanitize": sanitize, "trace": trace, "full_tree": full,
           "world": world["name"], "processes": len(outs), "cached": False}
    with open(sp, "w") as f:
        json.dump(res, f, indent=1)
    return res


# ======================================================================================== the lab side
def frame(world):
    m1 = pd.read_parquet(world["frame"], filters=[("ts", "<", CUT)])
    assert len(m1) and m1.index.max() < CUT and m1.index.is_monotonic_increasing and m1.index.is_unique
    return m1


def secs(idx):
    return pd.DatetimeIndex(idx).tz_convert("UTC").as_unit("s").asi8.astype(np.int64)


def lab_refs(code, world):
    o = pd.read_parquet(os.path.join(world["ref"], code, "orders.parquet"))
    t = pd.read_parquet(os.path.join(world["ref"], code, "trades.parquet"), filters=[("entry_time", "<", CUT)])
    t = t[t.entry_time < CUT].reset_index(drop=True)
    return o, t


def lab_lib():
    for p in (LAB, os.path.join(LAB, "r2", "tracks", "idx_us")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import goldlab as gl
    import idxus_lib as cm
    return gl, cm


def lab_grid(m1):
    """the lab's own grid and the per-check quantities of noise30 and ocm4 (strategy.py:127-168, 216-257), re-derived from
    idxus_lib with the lab's formulas, for the classification of the voids and the razors"""
    gl, cm = lab_lib()
    g = cm.grid(m1)
    P, EI, O, POS = g["P"], g["EI"], g["O"], g["POS"]
    D = len(g["dates"])
    min_date = pd.Timestamp("2014-01-01").date()
    sok = (~g["half"]) & np.array([d >= min_date for d in g["dates"]], bool)
    xi = gl.exit_index(m1, pd.DatetimeIndex(g["t0"] + (955 - 570) * np.timedelta64(60, "s").astype("timedelta64[ns]"), tz="UTC"))
    checks = np.arange(30, 361, 30)
    absmove = np.abs(P[:, checks] / O[:, None] - 1)
    sig = pd.DataFrame(absmove).rolling(14, min_periods=9).mean().shift(1).to_numpy()
    cl = P[:, 390]
    pc = np.r_[np.nan, cl[:-1]]
    hi = np.where(np.isfinite(pc), np.fmax(O, pc), O)
    lo = np.where(np.isfinite(pc), np.fmin(O, pc), O)
    C = P[:, 4]
    move = C / O - 1
    amove = np.abs(move)
    med = pd.Series(amove).rolling(20, min_periods=10).median().shift(1).to_numpy()
    atr = cm.atr_at(m1, g["t0"] + 4 * np.timedelta64(60, "s").astype("timedelta64[ns]"), 14)
    cnt = POS[:, 4] - POS[:, 0]
    return {"g": g, "D": D, "sok": sok, "xi": xi, "checks": checks, "sig": sig, "hi": hi, "lo": lo, "C": C, "move": move,
            "amove": amove, "med": med, "atr": atr, "cnt": cnt, "idx": secs(m1.index)}


def t_of(lg, d, m):
    """UTC seconds of the grid's minute m (from 09:30 New York) on row d"""
    return int(lg["g"]["t0"][d].astype("datetime64[s]").astype(np.int64)) + 60 * int(m)


def ny_str(t):
    return str(pd.Timestamp(int(t), unit="s", tz="UTC").tz_convert(NY))[:16]


# ======================================================================================== decisions
def dec_lines(rows, code):
    ords = [r for r in rows if r["ev"] == "DEC" and r["code"] == code and r.get("what") == "ord"]
    exs = [r for r in rows if r["ev"] == "DEC" and r["code"] == code and r.get("what") == "exit"]
    return ords, exs


def resolve(rows, code, m1):
    """the EA's DEC lines read as the paper reads a CrOrder (SPEC 2.4, 2.5), on the frame: one row per order"""
    gl, _ = lab_lib()
    ts = secs(m1.index)
    n = len(ts)

    def first_in(a, b):
        k = int(np.searchsorted(ts, a, "left"))
        return int(ts[k]) if k < n and ts[k] <= b else None

    def next_after(t, b):
        k = int(np.searchsorted(ts, t, "right"))
        return int(ts[k]) if k < n and ts[k] <= b else None

    ords, exs = dec_lines(rows, code)
    ex_by = {}
    for e in exs:
        ex_by.setdefault(int(e["oid"]), []).append((int(e["at"]), first_in(int(e["tf"]), int(e["tt"]))))
    xs = sorted({int(o["x"]) for o in ords if int(o["x"]) > 0})
    xbar = {}
    if xs:
        xi = gl.exit_index(m1, pd.DatetimeIndex(pd.to_datetime(xs, unit="s", utc=True)))
        xbar = {x: (int(ts[i]) if 0 <= i < n else None) for x, i in zip(xs, xi)}
    out = []
    for o in ords:
        oid, tf, tt, ax = int(o["oid"]), int(o["tf"]), int(o["tt"]), int(o["ax"])
        r = {"oid": oid, "dec": int(o["utc"]), "at": int(o["at"]), "side": int(o["side"]), "et": int(o["et"]), "stop": float(o["st"]),
             "stop_dist": float(o["sd"]), "x": int(o["x"]), "xg": int(o["xg"]), "vle": int(o["vle"]), "ax": ax, "act": None,
             "exit": None, "exit_by": None, "status": "ok"}
        if ax:
            eb = [b for at, b in ex_by.get(ax, []) if at == r["at"]]
            r["after_bar"] = eb[-1] if eb else None
            act = next_after(eb[-1], tt) if eb and eb[-1] is not None else None
        else:
            act = first_in(tf, tt)
        r["act"] = act
        if act is None:
            r["status"] = "void_window" if not ax else ("void_exit" if r["after_bar"] is None else "void_no_next_bar")
            out.append(r)
            continue
        xb = None
        for at, b in sorted(ex_by.get(oid, [])):
            if b is not None and b > act:
                xb, r["exit_by"] = b, "rule_exit"
                break
        if xb is None:
            xb = xbar.get(r["x"]) if r["xg"] else first_in(r["x"], 2**62)
            r["exit_by"] = "x_sched"
        r["exit"] = xb
        if r["vle"] and (xb is None or xb <= act):
            r["status"] = "void_le"
        out.append(r)
    return out, len(ords), len(exs)


def cmp_decisions(code, res_orders, lab_orders):
    """resolved EA orders (status ok) against the lab's make_orders orders"""
    ok = [r for r in res_orders if r["status"] == "ok"]
    ea = pd.DataFrame(ok)
    lab = lab_orders.copy()
    lab["entry_s"] = secs(lab.entry_t)
    lab["exit_s"] = secs(lab.exit_t)
    col = "stop" if code == "N30" else "stop_dist"
    if not len(ea):
        return {"lab_orders": int(len(lab)), "ea_orders": 0, "pass": len(lab) == 0}
    m = lab.merge(ea, left_on=["entry_s", "side"], right_on=["act", "side"], how="outer", suffixes=("_lab", "_ea"), indicator=True)
    both = m[m._merge == "both"]
    a, b = both[f"{col}_lab"].astype(float).to_numpy(), both[f"{col}_ea"].astype(float).to_numpy()
    d = np.abs(a - b)
    same_exit = both.exit_s.to_numpy() == both.exit.to_numpy().astype(np.int64)
    eq = d == 0
    within = d <= REL * np.abs(a)
    bad = both[~(same_exit & within)]
    res = {"lab_orders": int(len(lab)), "ea_orders_ok": int(len(ea)), "matched": int(len(both)),
           "only_lab": int((m._merge == "left_only").sum()), "only_ea": int((m._merge == "right_only").sum()),
           "same_exit_bar": int(same_exit.sum()), f"{col}_equal": int(eq.sum()), f"{col}_within_1e-12": int(within.sum()),
           f"{col}_max_rel_diff": float(np.max(d / np.abs(a))) if len(a) else 0.0,
           "exit_by": {k: int(v) for k, v in pd.Series([r["exit_by"] for r in ok]).value_counts().items()},
           "examples_only_lab": [ny_str(t) for t in m[m._merge == "left_only"].entry_s.head(10)],
           "examples_only_ea": [ny_str(t) for t in m[m._merge == "right_only"].act.head(10)],
           "examples_bad": [{"entry": ny_str(r.entry_s), "exit_lab": ny_str(r.exit_s), "exit_ea": ny_str(r.exit),
                             "lab": float(getattr(r, f"{col}_lab")), "ea": float(getattr(r, f"{col}_ea"))} for r in bad.head(10).itertuples()]}
    res["pass"] = res["only_lab"] == 0 and res["only_ea"] == 0 and len(bad) == 0 and res["matched"] == res["lab_orders"]
    return res


def classify_voids_n30(res_orders, lg):
    """every N30 order the paper voids, with the lab grid's reason for not having it"""
    g, xi, idx = lg["g"], lg["xi"], lg["idx"]
    EI = g["EI"]
    by_t = {}
    for d in range(lg["D"]):
        for j, m in enumerate(lg["checks"]):
            by_t[t_of(lg, d, m)] = (d, j, m)
    rows, bad = [], 0
    for r in res_orders:
        if r["status"] == "ok":
            continue
        d, j, m = by_t.get(r["dec"], (None, None, None))
        why = "unclassified"
        if d is not None:
            ei = EI[d, m]
            if r["status"] == "void_window" and ei < 0:
                why = "lab EI = -1: no kept bar in [T, T + 5 min]"
            elif r["status"] == "void_le" and ei >= 0 and ei >= xi[d]:
                why = "lab HOLE_RULE ei >= xi: the check's bar is the last before a hole through 15:55 (check skipped)"
            elif r["status"] == "void_le" and r["ax"] and ei >= 0 and ei + 1 >= xi[d]:
                why = "lab ei + 1 >= xi: the bar after the exit's is the last before a hole through 15:55 (no entry)"
            elif r["status"] == "void_no_next_bar" and ei >= 0 and (ei + 1 >= len(idx) or ei + 1 >= xi[d]):
                why = "lab ei + 1 >= xi: no kept bar after the exit's before 15:55 (no entry)"
            elif r["status"] == "void_exit" and ei < 0:
                why = "lab EI = -1: the exit's window has no kept bar"
        bad += why == "unclassified"
        rows.append({"dec": ny_str(r["dec"]), "status": r["status"], "side": r["side"], "why": why})
    return {"n": len(rows), "unclassified": bad, "list": rows}


def classify_voids_oc4(res_orders, lg):
    g, xi = lg["g"], lg["xi"]
    EI = g["EI"]
    by_t = {t_of(lg, d, 4): d for d in range(lg["D"])}
    rows, bad = [], 0
    for r in res_orders:
        if r["status"] == "ok":
            continue
        d = by_t.get(r["dec"])
        why = "unclassified"
        if d is not None:
            if r["status"] == "void_window" and EI[d, 4] < 0:
                why = "lab EI = -1: no kept bar in [09:34, 09:39]"
            elif r["status"] == "void_le" and EI[d, 4] >= 0 and xi[d] <= EI[d, 4]:
                why = "lab xi <= EI: the order's bar is the last before a hole through 15:55"
        bad += why == "unclassified"
        rows.append({"dec": ny_str(r["dec"]), "status": r["status"], "side": r["side"], "why": why})
    return {"n": len(rows), "unclassified": bad, "list": rows}


def lab_holes_n30(lg):
    """the lab's own HOLE_RULE and window-void checks (where the lab skipped an evaluable check)"""
    g, xi, sig = lg["g"], lg["xi"], lg["sig"]
    P, EI, O = g["P"], g["EI"], g["O"]
    ok = lg["sok"] & np.isfinite(O)
    hole, nobar = [], []
    for j, m in enumerate(lg["checks"]):
        p, s, ei = P[:, m], sig[:, j], EI[:, m]
        ev = ok & np.isfinite(p) & np.isfinite(s)
        hole += [ny_str(t_of(lg, d, m)) for d in np.flatnonzero(ev & (ei >= 0) & (ei >= xi))]
        nobar += [ny_str(t_of(lg, d, m)) for d in np.flatnonzero(ev & (ei < 0))]
    return {"hole_rule_checks": sorted(hole), "no_bar_checks": sorted(nobar)}


def razors_n30(lg):
    g, sig, hi, lo = lg["g"], lg["sig"], lg["hi"], lg["lo"]
    P, O = g["P"], g["O"]
    ok = lg["sok"] & np.isfinite(O)
    out = []
    for j, m in enumerate(lg["checks"]):
        p, s = P[:, m], sig[:, j]
        ev = ok & np.isfinite(p) & np.isfinite(s)
        ub, lb = hi * (1 + 1.0 * s), lo * (1 - 1.0 * s)
        for d in np.flatnonzero(ev):
            for name, thr in (("ub", ub[d]), ("lb", lb[d])):
                rel = abs(p[d] - thr) / abs(thr)
                if rel <= RAZOR:
                    out.append({"check": ny_str(t_of(lg, d, m)), "band": name, "rel": float(rel)})
    return out


def razors_oc4(lg):
    g = lg["g"]
    O, C, med, amove = g["O"], lg["C"], lg["med"], lg["amove"]
    ev = lg["sok"] & np.isfinite(O) & np.isfinite(C) & (lg["cnt"] >= 3) & (np.sign(lg["move"]) != 0) & np.isfinite(lg["atr"]) \
        & np.isfinite(med)
    out = []
    for d in np.flatnonzero(ev):
        rel = abs(amove[d] - med[d]) / abs(med[d]) if med[d] != 0 else abs(amove[d])
        if rel <= RAZOR:
            out.append({"day": str(g["dates"][d]), "rel": float(rel)})
    return out


# ======================================================================================== the holes world
HOLES_TAG = "idxholes"
HOLES_SEED = 20261113


def ny_sec(day, minute):
    """UTC seconds of a New York wall-clock time: a date and a minute of that day (may pass midnight backwards)"""
    t = pd.Timestamp(day) + pd.Timedelta(minutes=int(minute))
    return int(t.tz_localize(NY).tz_convert("UTC").value // 10**9)


def hole_cuts(m1, n30, oc4, seed=HOLES_SEED):
    """windows [a, b) (UTC seconds) whose bars are removed: targeted at the paths that in-sample data barely reaches,
    chosen from the lab's own orders on the in-sample frame (distinct days per kind), plus random holes"""
    rng = np.random.default_rng(seed)
    used = set()
    cuts = []

    def nyd(t):
        return pd.Timestamp(int(t), unit="s", tz="UTC").tz_convert(NY).tz_localize(None).normalize()

    def nymin(t):
        x = pd.Timestamp(int(t), unit="s", tz="UTC").tz_convert(NY)
        return x.hour * 60 + x.minute

    def check_of(t):
        """the N30 check whose window [T, T + 5 min] holds bar t (None when none does)"""
        k = nymin(t) - 600
        if k < 0 or k % 30 > 5 or k // 30 > 11:
            return None
        return ny_sec(nyd(t), 600 + 30 * (k // 30))

    def pick(cands, n, kind, make):
        cands = [c for c in cands if c[0] not in used]
        if not cands:
            return
        for i in rng.permutation(len(cands))[:n]:
            day = cands[i][0]
            used.add(day)
            for a, b in make(*cands[i]):
                cuts.append((int(a), int(b), kind))

    o = n30.reset_index(drop=True)
    es, xs = secs(o.entry_t), secs(o.exit_t)
    plain, rev, at_xi = [], [], []
    for k in range(len(o)):
        day = nyd(es[k])
        if k > 0 and o.entry_i[k] == o.exit_i[k - 1] + 1 and nyd(xs[k - 1]) == day and check_of(xs[k - 1]) is not None:
            rev.append((day, es[k], int(xs[k - 1]), check_of(xs[k - 1])))
        elif check_of(es[k]) is not None:
            plain.append((day, es[k], check_of(es[k])))
        if nymin(xs[k]) == 955 and nymin(es[k]) < 900:
            at_xi.append((day, es[k]))
    # reversals (an exit and the opposite entry at one check) are rare: 4 in sample, one for each reversal kind
    pick(rev, 1, "C_reversal_late_next_bar", lambda d, e, x, T: [(x + 60, x + 540)])
    pick(rev, 1, "D_reversal_no_bar_to_1555", lambda d, e, x, T: [(x + 60, ny_sec(d, 955))])
    pick(rev, 1, "E_reversal_bar_then_hole", lambda d, e, x, T: [(e + 60, ny_sec(d, 991))])
    pick(rev, 1, "B2_window_void_reversal", lambda d, e, x, T: [(T, T + 360)])
    pick(plain, 15, "A_hole_after_entry", lambda d, e, T: [(e + 60, ny_sec(d, 991))])
    pick(plain, 15, "B_window_void", lambda d, e, T: [(T, T + 360)])
    pick(plain, 15, "F_stale_price", lambda d, e, T: [(T - 720, T)])
    pick(at_xi, 10, "N_gap_exit_revised", lambda d, e: [(ny_sec(d, 931), ny_sec(d, 991))])
    days4 = sorted({nyd(t) for t in secs(oc4.entry_t)})
    c4 = [(d,) for d in days4]
    pick(c4, 15, "G_open_at_0931", lambda d: [(ny_sec(d, 570), ny_sec(d, 571))])
    pick(c4, 10, "G2_no_open", lambda d: [(ny_sec(d, 570), ny_sec(d, 572))])
    pick(c4, 10, "H_candle_short", lambda d: [(ny_sec(d, 571), ny_sec(d, 574))])
    pick(c4, 10, "I_window_void_0934", lambda d: [(ny_sec(d, 574), ny_sec(d, 580))])
    pick(c4, 10, "J_hole_after_0934", lambda d: [(ny_sec(d, 575), ny_sec(d, 991))])
    pick(c4, 10, "K_no_session", lambda d: [(ny_sec(d, 540), ny_sec(d, 975))])
    pick(c4, 10, "L_short_atr_day", lambda d: [(ny_sec(d, -360), ny_sec(d, 540))])
    pick(c4, 15, "M_no_1600_price", lambda d: [(ny_sec(d, 948), ny_sec(d, 960))])
    ts = secs(m1.index)
    rows = sorted({nyd(t) for t in ts[ts >= ny_sec(pd.Timestamp("2014-01-02"), 0)][::997]})
    for i in range(200):
        d = rows[int(rng.integers(len(rows)))]
        a = ny_sec(d, int(rng.integers(560, 966)))
        cuts.append((a, a + 60 * int(rng.integers(1, 61)), "R_random"))
    return sorted(cuts)


def holes_world(fresh=False):
    """the in-sample frame with hole_cuts removed: a US100 bar file for the EA (the other symbols keep their in-sample
    bars) and the lab's references on the same frame (ref_lab.py --frame rebuilt --tag idxholes)"""
    base = world_is("is")
    import export_frames as ef
    fpath = os.path.join(HERE, "out", "frames", f"us100_{HOLES_TAG}.parquet")
    bpath = os.path.join(HERE, "out", "bars", f"US100.r_{HOLES_TAG}.bin")
    ref = os.path.join(HERE, "out", "ref", f"rebuilt_{HOLES_TAG}")
    spec = os.path.join(OUT, "holes_world.json")
    m1 = frame(base)
    n30, _ = lab_refs("N30", base)
    oc4, _ = lab_refs("OC4", base)
    cuts = hole_cuts(m1, n30, oc4)
    key = hashlib.sha256((repr(cuts) + repr((len(m1), int(m1.index[0].value), int(m1.index[-1].value)))).encode()).hexdigest()
    done = os.path.exists(spec) and json.load(open(spec)).get("key") == key and os.path.exists(fpath) and os.path.exists(bpath) \
        and all(os.path.exists(os.path.join(ref, c, f)) for c in CODE_ID for f in ("orders.parquet", "trades.parquet"))
    if fresh or not done:
        ts = secs(m1.index)
        drop = np.zeros(len(ts), bool)
        kinds = {}
        for a, b, kind in cuts:
            i, j = np.searchsorted(ts, a, "left"), np.searchsorted(ts, b, "left")
            kinds[kind] = kinds.get(kind, 0) + int((~drop[i:j]).sum())
            drop[i:j] = True
        mh = m1[~drop]
        t = ef.server_secs(mh.index)
        pts, spread = ef.to_points(mh)
        os.makedirs(os.path.dirname(bpath), exist_ok=True)
        ef.write_bin(bpath, t, pts, spread)
        _, rec = ef.read_bin(bpath)
        fr = ef.rebuild(rec)
        assert (fr.index == mh.index.as_unit(fr.index.unit)).all(), "server -> UTC round trip"
        for c in mh.columns:
            assert (fr[c].to_numpy() == mh[c].to_numpy()).all(), f"bar file does not give the frame back ({c})"
        mh.to_parquet(fpath)
        tool([os.path.join(HERE, "ref_lab.py"), "--frame", "rebuilt", "--tag", HOLES_TAG, "--sleeves", ",".join(CODE_ID), "--no-changes"])
        os.makedirs(OUT, exist_ok=True)
        with open(spec, "w") as f:
            json.dump({"key": key, "seed": HOLES_SEED, "bars_in": int(len(m1)), "bars_removed": int(drop.sum()),
                       "removed_by_kind": kinds, "cuts": [[a, b, k, ny_str(a), ny_str(b)] for a, b, k in cuts]}, f, indent=1)
    info = json.load(open(spec))
    bars = dict(base["bars"])
    bars["US100.r"] = bpath
    mh = pd.read_parquet(fpath, filters=[("ts", "<", CUT)])
    return {"name": "holes", "tag": HOLES_TAG, "bars": bars, "ref": ref, "frame": fpath,
            "last_us100": int(secs(mh.index[-1:])[0]), "cuts": len(cuts), "bars_removed": info["bars_removed"],
            "removed_by_kind": info["removed_by_kind"]}


def coverage(code, rows, resolved):
    """the paths the holes world must reach (a count of 0 fails it: the world would have lost its purpose)"""
    st = pd.Series([r["status"] for r in resolved]).value_counts().to_dict()
    pv = sum(1 for r in rows if r["ev"] == "PVOID" and r["code"] == code)
    prv = sum(1 for r in rows if r["ev"] == "PREVISE" and r["code"] == code)
    if code == "N30":
        late = sum(1 for r in resolved if r["ax"] and r["act"] is not None and r.get("after_bar") is not None and r["act"] - r["after_bar"] > 60)
        cov = {"void_le_entry": sum(1 for r in resolved if r["status"] == "void_le" and not r["ax"]),
               "void_le_reversal": sum(1 for r in resolved if r["status"] == "void_le" and r["ax"]),
               "void_window": st.get("void_window", 0), "void_exit_window": st.get("void_exit", 0),
               "void_no_next_bar": st.get("void_no_next_bar", 0), "reversal_next_bar_late": late, "PVOID": pv, "PREVISE": prv}
    else:
        cov = {"void_le": st.get("void_le", 0), "void_window": st.get("void_window", 0), "PVOID": pv}
    return cov


# ======================================================================================== the restarts world
def restart_points(m1, n30, oc4, seed=HOLES_SEED):
    """restart times (UTC seconds) for the in-sample bars: inside open N30 and OC4 trades, 4 minutes before an N30 check
    that exits or enters and before OC4's 09:34 decision (a start needs two settle reads 2 s apart and a replay, so in the
    mock the first live barrier is about 2 minutes after the restart), in the 30-minute gap question of a revised exit,
    between a reversal's exit bar and its entry bar, and at random minutes. The mid-trade and random ones avoid the 3
    minutes around a decision minute and around a lab trade's entry or exit, so that every decision and every fill or
    exit is journaled by a live pass (the minutes just before a live start are replayed with rp=1)."""
    rng = np.random.default_rng(seed + 1)
    busy = set()
    for t in np.r_[secs(n30.entry_t), secs(n30.exit_t), secs(oc4.entry_t), secs(oc4.exit_t)]:
        for k in range(-3, 4):
            busy.add(int(t) // 60 + k)

    def nymin(t):
        x = pd.Timestamp(int(t), unit="s", tz="UTC").tz_convert(NY)
        return x.hour * 60 + x.minute

    def free(t):
        mod = nymin(t)
        if (mod - 600) % 30 in (0, 1, 2, 27, 28, 29) or abs(mod - 574) <= 3 or abs(mod - 960) <= 3:
            return False
        return int(t) // 60 not in busy and pd.Timestamp(int(t), unit="s", tz="UTC").tz_convert(NY).dayofweek < 5

    def first_free(t, tries=200):
        for k in range(tries):
            if free(t + 60 * k):
                return int(t + 60 * k)
        return None

    def check_at_or_before(t):
        k = nymin(t) - 600
        return int(t) - 60 * (k % 30) if 0 <= k <= 335 and k % 30 <= 5 else None

    pts = []
    o = n30.reset_index(drop=True)
    es, xs = secs(o.entry_t), secs(o.exit_t)
    for k in rng.permutation(len(o))[:6]:                                # inside open trades
        pts.append(first_free(es[k] + (xs[k] - es[k]) // 2 // 60 * 60))
    for k in rng.permutation(len(o))[:3]:                                # 4 min before the check that exits a trade
        T = check_at_or_before(xs[k])
        if T is not None:
            pts.append(T - 240)
    for k in rng.permutation(len(o))[:3]:                                # 4 min before the check that enters one
        T = check_at_or_before(es[k])
        if T is not None:
            pts.append(T - 240)
    revs = [k for k in range(1, len(o)) if o.entry_i[k] == o.exit_i[k - 1] + 1]
    for k in revs[:2]:                                                   # between a reversal's exit bar and its entry bar
        if int(es[k]) - int(xs[k - 1]) >= 60:
            pts.append(int(xs[k - 1]) + 60)
    q = oc4.reset_index(drop=True)
    e4, x4 = secs(q.entry_t), secs(q.exit_t)
    for k in rng.permutation(len(q))[:3]:
        d = pd.Timestamp(int(e4[k]), unit="s", tz="UTC").tz_convert(NY).tz_localize(None).normalize()
        pts.append(ny_sec(d, 570))                                       # 09:30: OC4 decides live 4 minutes later
        pts.append(first_free(e4[k] + (x4[k] - e4[k]) // 2 // 60 * 60))  # inside its trade
    for d in ("2015-11-02", "2018-02-02"):                               # gap questions open (data ends before 15:55)
        pts.append(ny_sec(pd.Timestamp(d), 965))
    ts = secs(m1.index)
    for _ in range(4):
        pts.append(first_free(int(ts[int(rng.integers(len(ts) // 10, len(ts)))]) // 60 * 60))
    return sorted({int(p) for p in pts if p is not None and ts[0] < p < ts[-1]})


def restarts_world():
    base = world_is("is")
    m1 = frame(base)
    n30, _ = lab_refs("N30", base)
    oc4, _ = lab_refs("OC4", base)
    pts = restart_points(m1, n30, oc4)
    srv = [int(pd.Timestamp(p, unit="s", tz="UTC").tz_convert(NY).tz_localize(None).value // 10**9) + 7 * 3600 for p in pts]
    w = dict(base)
    w["name"] = "restarts"
    w["restarts_utc"] = pts
    w["restarts_srv"] = srv
    return w


def live_rows(rows):
    """the journal of a run with restarts, as live passes wrote it: DEC and paper lines with rp=1 (a restart's replay of
    the history) are dropped, except, for a trade filled during a restart's replay and exited live, its PFILL: the
    latest replayed one before that live exit, put back in front of it"""
    out, last_rp_fill, live_fill = [], {}, set()
    for r in rows:
        key = (r["code"], r.get("oid"))
        if r.get("rp") == 1:
            if r["ev"] == "PFILL":
                last_rp_fill[key] = r
            continue
        if r["ev"] == "PFILL":
            live_fill.add(key)
        elif r["ev"] in ("PEXIT", "PREVISE", "PVOID") and key not in live_fill and key in last_rp_fill:
            out.append(last_rp_fill.pop(key))
            live_fill.add(key)
        out.append(r)
    return out


# ======================================================================================== one sleeve
def check_sleeve(code, world, sanitize=True, trace=False, full=False, fresh=False):
    t0 = time.time()
    plain = run_ea(world, False, trace, full, fresh)
    all_rows = compare.read_journal(plain["files"])
    evc = compare.check_parsable(plain["files"])["events"]
    rows = live_rows(all_rows) if world["name"] == "restarts" else all_rows
    m1 = frame(world)
    lab_o, lab_t = lab_refs(code, world)
    reb = compare.events(rows, "REBUILD").iloc[0]
    first_minute = int(reb["from"]) + 60 if int(reb["from"]) > 0 else int(reb["to"]) + 60
    res = {"code": code, "world": world["name"], "tree": "src/ (every file)" if full else f"finished files from src/, stubs from {STUB_COMMIT}",
           "replay": plain["replay"], "wall_s": plain["wall_s"], "cached_replay": plain.get("cached", False),
           "build_warnings": plain["warnings"], "events": evc, "first_minute_utc": first_minute,
           "errors": [r for r in all_rows if r["ev"] == "ERROR"][:5]}
    if world["name"] == "restarts":
        res["restarts"] = {"processes": plain.get("processes"), "rebuild_lines": int(evc.get("REBUILD", 0)),
                           "at_ny": [ny_str(t) for t in world["restarts_utc"]]}
    if world["name"] == "holes":
        res["holes"] = {"cuts": world["cuts"], "bars_removed": world["bars_removed"], "removed_by_kind": world["removed_by_kind"]}
    ok = not plain["warnings"] and not res["errors"] and "SEND" not in evc
    if world["name"] == "restarts":
        ok &= res["restarts"]["rebuild_lines"] == len(world["restarts_utc"]) + 1
    # 1-2. decisions
    resolved, n_ord, n_ex = resolve(rows, code, m1)
    lab_o = lab_o[secs(lab_o.entry_t) >= first_minute]
    res["dec_lines"] = {"orders": n_ord, "rule_exits": n_ex,
                        "status": {k: int(v) for k, v in pd.Series([r["status"] for r in resolved]).value_counts().items()}}
    res["decisions"] = cmp_decisions(code, resolved, lab_o)
    ok &= res["decisions"]["pass"]
    lg = lab_grid(m1)
    if code == "N30":
        res["voids"] = classify_voids_n30(resolved, lg)
        res["lab_skipped_checks"] = lab_holes_n30(lg)
        res["razors"] = razors_n30(lg)
    else:
        res["voids"] = classify_voids_oc4(resolved, lg)
        res["razors"] = razors_oc4(lg)
    ok &= res["voids"]["unclassified"] == 0
    if world["name"] == "holes":
        res["coverage"] = coverage(code, rows, resolved)
        ok &= all(v > 0 for v in res["coverage"].values())
    if world["name"] == "restarts":
        ea_t = compare.paper_trades(rows, code)
        es, xs = secs(ea_t.entry_time), secs(ea_t.exit_time)
        pts = world["restarts_utc"]
        decs = np.array(sorted(r["dec"] for r in resolved), np.int64)
        res["coverage"] = {"restarts_inside_an_open_trade": sum(1 for p in pts if ((es < p) & (xs > p)).any()),
                           "decisions_within_5_min_after_a_restart": sum(1 for p in pts if ((decs > p) & (decs <= p + 300)).any())}
        ok &= all(v > 0 for v in res["coverage"].values())
    # 3. paper trades
    tr = compare.cmp_trades(rows, lab_t, code, t_from=first_minute, t_to=world["last_us100"] - 1, rel=REL)
    ea_t = compare.paper_trades(rows, code)
    tr["ea_trades_total"] = int(len(ea_t))
    tr["lab_trades_total"] = int(len(lab_t))
    if len(ea_t):
        tr["reasons_ea"] = {k: int(v) for k, v in ea_t.reason.value_counts().items()}
        tr["revised_ea"] = int(ea_t.revised.sum())
    tr["reasons_lab"] = {k: int(v) for k, v in lab_t.reason.value_counts().items()}
    full_eq = tr.get("entry_equal") == tr.get("stop_equal") == tr.get("exit_equal") == tr.get("lab_trades")
    tr["prices_bit_for_bit"] = bool(full_eq)
    res["trades"] = tr
    ok &= bool(tr["pass"]) and tr.get("lab_trades", 0) > 0 and tr.get("same_exit_and_reason") == tr.get("lab_trades")
    # 6. sanitizer
    if sanitize:
        san = run_ea(world, True, trace, full, fresh)
        same = subprocess.run(["diff", "-r", "-q", os.path.join(plain["files"], "ClaudeRobot"), os.path.join(san["files"], "ClaudeRobot")],
                              capture_output=True, text=True)
        res["sanitizer"] = {"replay": san["replay"], "wall_s": san["wall_s"], "cached_replay": san.get("cached", False),
                            "build_warnings": san["warnings"], "journal_identical_to_plain_build": same.returncode == 0}
        ok &= same.returncode == 0 and not san["warnings"]
    res["pass"] = bool(ok)
    res["sec"] = round(time.time() - t0, 1)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, f"{code}_{world['name']}_result.json"), "w") as f:
        json.dump(res, f, indent=1, default=str)
    return res


def report(res, verbose=False):
    d, t = res["decisions"], res["trades"]
    col = "stop" if res["code"] == "N30" else "stop_dist"
    log(f"{res['code']} world {res['world']}: replay {res['wall_s']} s{' (cached)' if res['cached_replay'] else ''}, "
        f"DEC orders {res['dec_lines']['orders']}, rule exits {res['dec_lines']['rule_exits']}, status {res['dec_lines']['status']}")
    if "holes" in res:
        log(f"  holes: {res['holes']['cuts']} cuts, {res['holes']['bars_removed']} bars removed")
    if "restarts" in res:
        r = res["restarts"]
        log(f"  restarts: {len(r['at_ny'])} ({r['processes']} processes, {r['rebuild_lines']} REBUILD lines) at {r['at_ny']}")
    log(f"  decisions: lab {d['lab_orders']}, EA {d.get('ea_orders_ok')}, matched {d.get('matched')}, only lab {d.get('only_lab')}, "
        f"only EA {d.get('only_ea')}, same exit bar {d.get('same_exit_bar')}, {col} equal {d.get(col + '_equal')} "
        f"(within 1e-12 {d.get(col + '_within_1e-12')}, max rel {d.get(col + '_max_rel_diff')}); exits by {d.get('exit_by')}")
    if not d.get("pass"):
        log(f"  decision differences: only lab {d.get('examples_only_lab')} only EA {d.get('examples_only_ea')} bad {d.get('examples_bad')}")
    whys = pd.Series([v["status"] + ": " + v["why"] for v in res["voids"]["list"]]).value_counts().to_dict()
    log(f"  voids: {res['voids']['n']} ({res['voids']['unclassified']} unclassified) {whys}")
    if verbose or res["voids"]["unclassified"]:
        for v in res["voids"]["list"]:
            log(f"    {v['dec']} {v['status']:16s} side {v['side']:+d}  {v['why']}")
    if "lab_skipped_checks" in res:
        h = res["lab_skipped_checks"]
        log(f"  lab: HOLE_RULE checks {len(h['hole_rule_checks'])} {h['hole_rule_checks'][:8]}")
        log(f"  lab: checks without a bar in [T, T+5] {len(h['no_bar_checks'])} {h['no_bar_checks'][:8]}")
    if "coverage" in res:
        log(f"  coverage: {res['coverage']}")
    log(f"  razors (lab decisions within 1e-9 of a threshold): {len(res['razors'])} {res['razors'][:5]}")
    log(f"  trades: lab {t.get('lab_trades')}, EA {t.get('ea_trades')}, same entry {t.get('same_entry')}, same exit+reason "
        f"{t.get('same_exit_and_reason')}, entry/stop/exit equal {t.get('entry_equal')}/{t.get('stop_equal')}/{t.get('exit_equal')}, "
        f"within 1e-12 {t.get('entry_within_rel')}/{t.get('stop_within_rel')}/{t.get('exit_within_rel')}, voided {t.get('voided_in_journal')}")
    log(f"  reasons EA {t.get('reasons_ea')} lab {t.get('reasons_lab')}, PREVISE exits {t.get('revised_ea')}")
    if "sanitizer" in res:
        s = res["sanitizer"]
        log(f"  sanitizer: replay {s['wall_s']} s{' (cached)' if s['cached_replay'] else ''}, warnings {len(s['build_warnings'])}, "
            f"journal identical {s['journal_identical_to_plain_build']}")
    if res["errors"] or res["build_warnings"]:
        log(f"  errors {res['errors']} warnings {res['build_warnings'][:5]}")
    log(f"{res['code']} world {res['world']}: {'PASS' if res['pass'] else 'FAIL'} ({res['sec']} s) -> "
        f"{os.path.relpath(OUT, ROBOT)}/{res['code']}_{res['world']}_result.json")


def main(code, argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", default="all", choices=["all", "is", "holes", "restarts"],
                    help="is = in sample (T4/T5); holes = with targeted holes; restarts = in sample with restarts")
    ap.add_argument("--tag", default="is", choices=["is", "y2021"], help="period of the in-sample world")
    ap.add_argument("--no-sanitize", action="store_true", help="skip the sanitizer replay of the in-sample world")
    ap.add_argument("--sanitize-holes", action="store_true", help="also replay the holes world under the sanitizer")
    ap.add_argument("--full-tree", action="store_true")
    ap.add_argument("--trace", action="store_true")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(argv)
    ok = True
    if a.world in ("all", "is"):
        res = check_sleeve(code, world_is(a.tag), not a.no_sanitize, a.trace, a.full_tree, a.fresh)
        report(res, a.verbose)
        ok &= res["pass"]
    if a.world in ("all", "holes"):
        res = check_sleeve(code, holes_world(a.fresh), a.sanitize_holes, a.trace, a.full_tree, a.fresh)
        report(res, a.verbose)
        ok &= res["pass"]
    if a.world in ("all", "restarts"):
        res = check_sleeve(code, restarts_world(), False, a.trace, a.full_tree, a.fresh)
        report(res, a.verbose)
        ok &= res["pass"]
    log(f"{code}: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main("N30"))
