"""T4 gold clock GFP (step G): GOLD_FRI_PM, every decision and every trade of 2013-2021 against the lab.

    python3 -I lab/robot/check/test_GFP.py [--no-sanitize] [--fresh]

What runs (SPEC 7 T4/T5, SPEC 8 row G):
  * The EA: a private copy of src/ under build/test_G/tree/ with the finished files of S0, A, B, C and I as they are
    now, step G's two rule files, and the S0 stubs (git, commit 7b87227) of the steps running beside G (D, E, F, H, J,
    K): SPEC 8 lets a step compile only those. tools/amalgam.py makes the single file; check/to_cpp.py and g++
    (-std=c++17 -O2 -ffp-contract=off -Wall, 0 warnings) build it against S0's mock and shim and J's mock_faults.h
    stub. It replays the 2013-2021 bars of the four symbols (export_frames.py --tag is) through the S0 driver with
    InpTrade false and the three switches off.
  * The lab, each call in a fresh process (P8), every frame read with the 2022-01-01 cut inside the read call:
      rebuilt   ref_lab.one("GFP") on the frame rebuilt from the same bars (make_orders, r2.run: S0's references);
      kept      the same lab calls on the rebuilt frame without the bars the EA's mask drops (SPEC 2.2, the XAU rule;
                test_bars.mask_reasons, step B's copy of the mask): the EA's own input, so "EA = lab code on the
                broker's bars" is checked with no exception. Since SPEC v2.1 (change X1) export_frames.py drops the
                gold bars of 17:00-17:59 New York itself (in sample the 20 bars of 2012-12-31 17:00-17:58, which
                seeded the lab's hour ATR, so three January 2013 stops differed on the rebuilt frame): the mask must
                then drop nothing, the kept frame IS the rebuilt frame, and a dropped bar fails the test;
      official  ref_lab.one on lab/data/fp (the rebuilt frame rounds the bid to 2 digits, SPEC 7).
    The per-Friday quantities of the lab's make_orders (the 13:30 bar, the 16:45 test, the hour ATR) come from the
    lab's own helpers (_open_at, _atr, _local_ns), to classify the days the lab skips.
Checks:
  1. Decisions. Every lab order has the EA order of its New York date: buy limit at the same level (bit for bit), its
     window [13:30, 13:35] resolving to the lab's entry bar, its expiry (bars before 14:30) to the lab's expiry bar,
     its exit (16:45, no gap rule) to the lab's exit bar, stop_dist within 1e-12 relative (Wilder ATR). Every other
     EA order is classified: no kept bar in its window (the lab's _open_at fails: it never activates), or a GFP hole
     day (the lab's 16:45 test reads a future hole; SPEC 7: classified, never silent). Every Friday of the replay has
     an EA order or a DEC info line (never silent).
  2. Skip set (SPEC 8 G: the lab's in sample). The Fridays the EA's calendar skips (NYSE full or half day, XAU closure,
     broker session) are exactly the lab's skipped Fridays minus the hole days; the lab skips none the calendar keeps
     except the hole days.
  3. Trades: the journal's paper trades (compare.paper_trades) against r2.run's: entry and exit minute, side, reason,
     entry and exit price equal, initial stop within 1e-12 relative (compare.cmp_trades with rel 1e-12 gives its own
     verdict too); trades open at the frame end left out. Against the kept frame: no difference but the hole days.
     Against the rebuilt frame: every difference must have a cause, checked: a hole day, or the mask of 2012-12-31
     (the difference vanishes against the kept frame; since X1 none can remain, as the kept and rebuilt frames must be
     the same bars).
  4. The lab on the rebuilt frame against the official trades: each difference listed with its cause.
  5. Unit worlds (a generated C++ program on the private tree's rule file, with a test copy of the mock's session hook):
     the calendar on every Friday of 2012-2035 against idxus_lib.us_holidays, typed closures, broker sessions,
     LatestExit, and synthetic bar worlds (warm-up, missing bars, empty hours) against the lab's make_orders.
  6. The journal parses and keeps S0's replay contract (2 INIT, SELFTEST ok, 1 PLAN, 4 READY, 1 REBUILD, no ERROR, no
     SEND); the release file (no CR_HARNESS) and the debug file compile with 0 warnings; the sanitizer build
     (-fsanitize=address,undefined -D_GLIBCXX_DEBUG) writes a byte-identical journal.
  7. The holes world: the same replay with 216 windows of gold bars cut (hole_cuts: aimed at paths in-sample data barely
     reaches, chosen from the lab's own orders, plus 120 random holes), against the lab's code on the same holed bars:
     checks 1-3 again, and each aimed path must be reached (orders that never activate, hole days, a late activation
     bar, a level and an ATR hour from earlier bars, exits after 16:45). Its sanitizer replay is byte-identical too.
  8. Depth (SPEC 2.2: every start replays 120 days of gold; T6 is step K's): the lab's hour ATR read at each Friday's
     13:30 from the last 120 days of bars only must equal the whole frame's within 1e-12.
This file also holds the harness test_ORX.py imports (the replays are shared and cached). Outputs: check/out/test_G/.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROBOT = os.path.dirname(HERE)
LAB = os.path.dirname(ROBOT)
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import build as B  # noqa: E402
import compare  # noqa: E402

OUT = os.path.join(HERE, "out", "test_G")
TREE = os.path.join(ROBOT, "build", "test_G")
REF = os.path.join(OUT, "ref")
CUT = pd.Timestamp("2022-01-01", tz="UTC")
NY, LDN = "America/New_York", "Europe/London"
STUB_COMMIT = "7b87227"                       # part 1 done: the files of D, E, F, H, J and K are S0's stubs there
OWN = ("CR_Rule_GoldFri.mqh", "CR_Rule_Orb.mqh")
FINISHED = ("ClaudeRobot.mq5", "CR_Types.mqh", "CR_Registry.mqh", "CR_Journal.mqh", "CR_Main.mqh", "CR_Rule_Script.mqh",
            "CR_Clock.mqh", "CR_Math.mqh", "CR_Bars.mqh", "CR_Paper.mqh", "CR_Ledger.mqh", "CR_Sizing.mqh")
PARALLEL = ("CR_Rule_IdxUS.mqh", "CR_Rule_Brk72.mqh", "CR_Rule_F1.mqh", "CR_F1Model.mqh", "CR_Rule_NqBtc.mqh",
            "CR_Rule_Donch.mqh", "CR_Broker.mqh", "CR_Follower.mqh", "CR_Guards.mqh", "CR_Golden.mqh")
SYMS = ("XAUUSD.r", "US100.r", "BTCUSD.r", "ETHUSD.r")
SID = {"GFP": 8, "ORX": 10}
RULE = {"GFP": "GOLD_FRI_PM", "ORX": "orb_asia_2d_buf10"}
INPUTS = {"InpTrade": "false", "InpK1": "0", "InpH2": "0", "InpS075": "0", "InpK1T": ""}
REL = 1e-12                                   # SPEC 7: Wilder values and the stops built on them
NB = os.environ.get("NUMBA_CACHE_DIR", "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/numba")
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", NUMBA_CACHE_DIR=NB)


def log(msg):
    print(msg, flush=True)


def write(name, res):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w") as f:
        json.dump(res, f, indent=1, default=str)


# ======================================================================================== the private tree and builds
def git_stub(rel):
    """a file of a step running beside G, as S0 left it (git show, read only); without that commit, the current file
    while it is still the stub"""
    r = subprocess.run(["git", "-C", ROBOT, "show", f"{STUB_COMMIT}:./{rel}"], capture_output=True)
    if r.returncode == 0 and b"S0 STUB" in r.stdout:
        return r.stdout, f"S0 stub (git {STUB_COMMIT})"
    cur = open(os.path.join(ROBOT, rel), "rb").read()
    if b"S0 STUB" in cur:
        return cur, "S0 stub (the current file is still the stub)"
    raise RuntimeError(f"{rel}: no S0 stub (git show {STUB_COMMIT} failed or is not a stub, and the file is no longer one)")


def make_tree():
    """build/test_G/tree: src (finished files, G's files, the S0 stubs of the parallel steps), harness, dist"""
    root = os.path.join(TREE, "tree")
    src, har, dist = (os.path.join(root, d) for d in ("src", "harness", "dist"))
    if os.path.isdir(root):
        shutil.rmtree(root)
    for d in (src, har, dist):
        os.makedirs(d)
    found = sorted(n for n in os.listdir(os.path.join(ROBOT, "src")) if n.endswith((".mqh", ".mq5")))
    known = set(OWN) | set(FINISHED) | set(PARALLEL)
    if set(found) != known:
        raise RuntimeError(f"src/ holds {sorted(set(found) - known)} unknown and misses {sorted(known - set(found))}: "
                           "update the file lists of test_GFP.py")
    origin = {}
    for n in OWN + FINISHED:
        shutil.copy(os.path.join(ROBOT, "src", n), os.path.join(src, n))
        origin[n] = "current"
    for n in PARALLEL:
        txt, how = git_stub(f"src/{n}")
        open(os.path.join(src, n), "wb").write(txt)
        origin[n] = how
    for n in ("mock_replay.h", "mql5_shim.h"):
        shutil.copy(os.path.join(HERE, n), os.path.join(har, n))
    txt, how = git_stub("check/mock_faults.h")
    open(os.path.join(har, "mock_faults.h"), "wb").write(txt)
    origin["mock_faults.h"] = how
    r = subprocess.run([sys.executable, "-I", os.path.join(ROBOT, "tools", "amalgam.py"), "--src", os.path.join(src, "ClaudeRobot.mq5"),
                        "--out", dist], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("amalgam refused the tree:\n" + r.stderr)
    return {"root": root, "src": src, "harness": har, "dist": os.path.join(dist, "ClaudeRobot.mq5"), "origin": origin,
            "amalgam": r.stdout.strip().splitlines()[0]}


_TREE = {}


def tree():
    if "t" not in _TREE:
        _TREE["t"] = make_tree()
    return _TREE["t"]


def sha_files(paths):
    h = hashlib.sha256()
    for p in paths:
        h.update(open(p, "rb").read())
    return h.hexdigest()


def compile_cpp(run_cpp, exe, sanitize, incdirs, defines):
    cmd = B.CXX + (B.SAN if sanitize else []) + [f"-D{d}" for d in defines]
    for d in incdirs:
        cmd += ["-I", d]
    cmd += [run_cpp, "-o", exe]
    r = subprocess.run(cmd, capture_output=True, text=True)
    warn = [ln for ln in r.stderr.splitlines() if "warning:" in ln]
    if r.returncode:
        raise B.BuildError(f"compile failed ({exe}):\n" + r.stderr[-20000:])
    return warn


def build_ea(sanitize):
    """the replay binary of the private tree's single file (harness build); reused while the sources are unchanged"""
    t = tree()
    name = "ea_san" if sanitize else "ea"
    work = os.path.join(TREE, name)
    srcs = [t["dist"]] + [os.path.join(t["harness"], n) for n in ("mock_replay.h", "mql5_shim.h", "mock_faults.h")] + \
        [os.path.join(HERE, "to_cpp.py")]
    key = sha_files(srcs) + (" san " if sanitize else " ") + " ".join(B.CXX + (B.SAN if sanitize else []))
    exe = os.path.join(work, "replay")
    stamp = os.path.join(work, "stamp.txt")
    if os.path.exists(exe) and os.path.exists(stamp) and open(stamp).read() == key:
        return exe, json.load(open(os.path.join(work, "warnings.json")))
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)
    B.translate(t["dist"], os.path.join(work, "ea.cpp"))
    run = os.path.join(work, "run.cpp")
    with open(run, "w") as f:
        f.write(f'#include "{os.path.join(t["harness"], "mock_replay.h")}"\n#include "{os.path.join(work, "ea.cpp")}"\n')
    warn = compile_cpp(run, exe, sanitize, [t["harness"], work], ["CR_HARNESS", "CR_XAU_COMM_PTS=0"])
    json.dump(warn, open(os.path.join(work, "warnings.json"), "w"))
    open(stamp, "w").write(key)
    return exe, warn


def build_variants():
    """the private tree's single file as the user gets it (no CR_HARNESS, CR_XAU_COMM_PTS 6) and its debug twin
    (CR_DEBUG, harness defines), compiled only: every warning is reported"""
    t = tree()
    out = {}
    for name, src, harness in (("release", t["dist"], False), ("debug", t["dist"].replace("ClaudeRobot.mq5", "ClaudeRobot_debug.mq5"), True)):
        work = os.path.join(TREE, "variant_" + name)
        if os.path.isdir(work):
            shutil.rmtree(work)
        os.makedirs(work)
        B.translate(src, os.path.join(work, "ea.cpp"))
        run = os.path.join(work, "run.cpp")
        with open(run, "w") as f:
            f.write(f'#include "{os.path.join(t["harness"], "mock_replay.h")}"\n#include "{os.path.join(work, "ea.cpp")}"\n')
        try:
            warn = compile_cpp(run, os.path.join(work, "replay"), False, [t["harness"], work],
                               ["CR_HARNESS", "CR_XAU_COMM_PTS=0"] if harness else [])
            out[name] = {"exit": 0, "warnings": warn[:10]}
        except B.BuildError as e:
            out[name] = {"exit": 1, "warnings": [], "error": str(e)[-2000:]}
    out["pass"] = all(v["exit"] == 0 and not v["warnings"] for v in out.values())
    return out


# ======================================================================================== bars, replay, journal
def bars():
    """the 2013-2021 broker bars of the four symbols (S0's export_frames.py --tag is), exported when missing"""
    p = {s: os.path.join(HERE, "out", "bars", f"{s}_is.bin") for s in SYMS}
    man = os.path.join(HERE, "out", "manifest_is.json")
    fr = os.path.join(HERE, "out", "frames", "xauusd_is.parquet")
    if not all(os.path.exists(v) for v in p.values()) or not os.path.exists(man) or not os.path.exists(fr):
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "export_frames.py"), "--tag", "is"], env=ENV,
                           capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError("export_frames.py failed:\n" + r.stderr[-3000:])
    return p


def manifest_last():
    """last bar start of each broker symbol (UTC seconds), from the export's manifest"""
    m = json.load(open(os.path.join(HERE, "out", "manifest_is.json")))
    return {r["broker"]: int(pd.Timestamp(r["last"]).value // 10**9) for r in m}


def bar_stamp(bp):
    return {s: [os.path.getsize(p), int(os.path.getmtime(p))] for s, p in sorted(bp.items())}


def replay(exe, name, inputs=None, env_extra=None, fresh=False, bars_map=None):
    """the EA over the in-sample bars (or bars_map); returns (journal rows, stdout, seconds, MOCK_FILES dir). A replay of the
    same binary (sha256), inputs and bar files already in OUT/<name> is read again instead of run again (test_ORX reuses
    test_GFP's)"""
    files = os.path.join(OUT, name)
    env = {f"MOCK_INPUT_{k}": v for k, v in (inputs or INPUTS).items()}
    env.update(env_extra or {})
    bp = bars_map or bars()
    key = json.dumps({"exe": sha_files([exe]), "env": env, "bars": bar_stamp(bp)}, sort_keys=True)
    stamp = os.path.join(files, "_replay_key.json")
    done = os.path.join(files, "_replay_out.json")
    if not fresh and os.path.exists(stamp) and os.path.exists(done) and open(stamp).read() == key:
        d = json.load(open(done))
        return compare.read_journal(files), d["out"], d["wall"], files
    out, wall = B.replay(exe, files, bp, env=env, fresh=True, timeout=7200)
    if bar_stamp(bp) != json.loads(key)["bars"]:
        raise RuntimeError("a bar file changed during the replay (another step re-exported it): run again")
    json.dump({"out": out, "wall": wall}, open(done, "w"))
    open(stamp, "w").write(key)
    return compare.read_journal(files), out, wall, files


def first_minute(rows):
    reb = compare.events(rows, "REBUILD").iloc[0]
    return int(reb["from"]) + 60 if int(reb["from"]) > 0 else int(reb["to"]) + 60


def journals_identical(a, b):
    r = subprocess.run(["diff", "-r", "-q", os.path.join(a, "ClaudeRobot"), os.path.join(b, "ClaudeRobot")], capture_output=True,
                       text=True)
    return r.returncode == 0


def s0_contract(rows):
    """S0's replay contract (test_s0_replay.py) on this journal: the rules add only their own lines"""
    ev = {}
    for r in rows:
        ev[r["ev"]] = ev.get(r["ev"], 0) + 1
    st = [r for r in rows if r["ev"] == "SELFTEST"]
    res = {"INIT": ev.get("INIT", 0), "SELFTEST_ok": int(st[0]["ok"]) if st else None, "PLAN": ev.get("PLAN", 0),
           "READY": ev.get("READY", 0), "REBUILD": ev.get("REBUILD", 0), "ERROR": ev.get("ERROR", 0), "SEND": ev.get("SEND", 0)}
    res["pass"] = (res["INIT"] == 2 and res["SELFTEST_ok"] == 1 and res["PLAN"] == 1 and res["READY"] == 4 and res["REBUILD"] == 1
                   and res["ERROR"] == 0 and res["SEND"] == 0)
    return res


def what_of(r):
    """the DEC kind; compare.num reads any text holding "inf" or "nan" as a number, so "info" comes back as inf"""
    w = r.get("what")
    if isinstance(w, float) and w == float("inf"):
        return "info"
    return w


def dec_rows(rows, code, what):
    return pd.DataFrame([r for r in rows if r["ev"] == "DEC" and r["code"] == code and what_of(r) == what])


def counts(rows, code):
    c = {}
    for r in rows:
        if r["code"] == code:
            k = r["ev"] + (":" + str(what_of(r)) if r["ev"] == "DEC" else "")
            c[k] = c.get(k, 0) + 1
    return dict(sorted(c.items()))


_EA = {}


def ea_run(sanitize=True, fresh=False):
    """build and replay (plain, then sanitizer); shared by test_GFP and test_ORX"""
    if "plain" not in _EA:
        exe, warn = build_ea(False)
        rows, out, wall, files = replay(exe, "replay", fresh=fresh)
        _EA["plain"] = {"rows": rows, "out": out, "wall": round(wall, 1), "files": files, "warnings": warn}
    res = dict(_EA["plain"])
    if sanitize and "san" not in _EA:
        exe_s, warn_s = build_ea(True)
        rows_s, out_s, wall_s, files_s = replay(exe_s, "replay_san", env_extra={"ASAN_OPTIONS": "detect_leaks=1"}, fresh=fresh)
        _EA["san"] = {"warnings": warn_s, "out": out_s, "wall": round(wall_s, 1), "identical": journals_identical(res["files"], files_s)}
    if sanitize:
        res["san"] = _EA["san"]
    return res


# ======================================================================================== the lab side
def spawn(src):
    r = subprocess.run([sys.executable, "-I", "-c", src], capture_output=True, text=True, env=ENV, cwd=ROBOT)
    if r.returncode:
        raise RuntimeError("reference process failed:\n" + r.stderr[-4000:])
    return json.loads(r.stdout.strip().splitlines()[-1])


def ref_lab_one(code, kind):
    """S0's ref_lab.one(code) in a fresh process (P8), outputs under check/out/test_G/ref/<kind>[_is]/<code>/"""
    tag = "is" if kind == "rebuilt" else None
    src = (f"import sys, json; sys.dont_write_bytecode = True; sys.path.insert(0, {HERE!r}); import ref_lab; "
           f"ref_lab.OUT = {REF!r}; print(json.dumps(ref_lab.one({code!r}, {kind!r}, {tag!r}), default=str))")
    res = spawn(src)
    d = os.path.join(REF, kind + ("_is" if tag else ""), code)
    return res, pd.read_parquet(os.path.join(d, "orders.parquet")), pd.read_parquet(os.path.join(d, "trades.parquet"))


def frame_path(kind):
    if kind == "official":
        return os.path.join(LAB, "data", "fp", "xauusd_m1.parquet")
    if kind == "rebuilt":
        return os.path.join(HERE, "out", "frames", "xauusd_is.parquet")
    if kind == "kept":
        return kept_frame()
    if kind == "holes_kept":
        return os.path.join(HOLES, "xauusd_holes_kept.parquet")
    raise ValueError(kind)


def read_frame(path):
    m1 = pd.read_parquet(path, filters=[("ts", "<", CUT)])
    assert len(m1) and m1.index.max() < CUT and m1.index.is_monotonic_increasing and m1.index.is_unique
    return m1


def kept_frame():
    """the rebuilt gold frame without the bars the EA's mask drops (step B's mask_reasons on the broker bars): the EA's
    kept bars, as a lab frame"""
    p = os.path.join(OUT, "frames", "xauusd_kept.parquet")
    src = os.path.join(HERE, "out", "frames", "xauusd_is.parquet")
    binp = bars()["XAUUSD.r"]
    key = json.dumps({"frame": [os.path.getsize(src), int(os.path.getmtime(src))], "bin": [os.path.getsize(binp), int(os.path.getmtime(binp))]})
    kp = p + ".key"
    if os.path.exists(p) and os.path.exists(kp) and open(kp).read() == key:
        return p
    import export_frames
    import test_bars
    _, rec = export_frames.read_bin(binp)
    m1 = read_frame(src)
    assert len(rec) == len(m1)
    reason = test_bars.mask_reasons(rec, "XAU", set())
    kept = m1[reason == test_bars.KEPT]
    os.makedirs(os.path.dirname(p), exist_ok=True)
    kept.to_parquet(p)
    dropped = m1.index[reason != test_bars.KEPT]
    json.dump({"dropped": int(len(dropped)), "first": str(dropped.min()) if len(dropped) else None,
               "last": str(dropped.max()) if len(dropped) else None,
               "by_reason": {int(k): int(v) for k, v in zip(*np.unique(reason[reason != test_bars.KEPT], return_counts=True))}},
              open(os.path.join(OUT, "frames", "kept_dropped.json"), "w"), indent=1)
    open(kp, "w").write(key)
    return p


LAB_RUN_SRC = r"""
import sys, os, json
sys.dont_write_bytecode = True
import numpy as np, pandas as pd
LAB, CODE, FRAME, OUTD = {lab!r}, {code!r}, {frame!r}, {outd!r}
sys.path.insert(0, LAB); sys.path.insert(0, os.path.join(LAB, "r2"))
import recalc
from goldlab import r2
reg = {{(s[1], s[2]): s for s in recalc.sleeves()}}
RULE = {{"GFP": "GOLD_FRI_PM", "ORX": "orb_asia_2d_buf10"}}[CODE]
track, name, sym, mo, params = reg[(RULE, "xauusd")]
CUT = pd.Timestamp("2022-01-01", tz="UTC")
m1 = pd.read_parquet(FRAME, filters=[("ts", "<", CUT)])
assert len(m1) and m1.index.max() < CUT and m1.index.is_monotonic_increasing
os.makedirs(OUTD, exist_ok=True)
orders = mo(m1, **params).reset_index(drop=True)
trades = r2.run(sym, mo, params, "fp", True, m1)
n = len(m1)
idx = m1.index
ns = idx.values.astype("datetime64[ns]").astype(np.int64)
sec = ns // 1000000000
def tsec(i):
    i = np.asarray(i, np.int64)
    return np.where((i >= 0) & (i < n), sec[np.clip(i, 0, n - 1)], -1)
o = orders.copy()
for c in ("entry_i", "exit_i", "expiry_i"):
    if c in o:
        o[c.replace("_i", "_t")] = tsec(o[c].to_numpy())
for c in o.columns:
    if o[c].dtype == object:
        o[c] = o[c].astype(str)
o.to_parquet(os.path.join(OUTD, "orders.parquet"))
trades.to_parquet(os.path.join(OUTD, "trades.parquet"))
res = {{"code": CODE, "frame": FRAME, "bars": int(n), "first_bar": str(idx[0]), "orders": int(len(orders)), "trades": int(len(trades)),
        "reasons": trades.reason.value_counts().to_dict(), "R_sum": float(trades.R.sum())}}
if CODE == "GFP":
    S = sys.modules["r2_overnight_strategy"]
    MIN = S.MIN
    d0 = idx[0].tz_convert("America/New_York").tz_localize(None).normalize()
    d1 = idx[-1].tz_convert("America/New_York").tz_localize(None).normalize()
    dates = pd.date_range(d0, d1, freq="D")
    t0 = S._local_ns(dates, S._mins(params["entry"]), "NY")
    ei, ok = S._open_at(ns, t0, 5, int(params["min_prev"]))
    t1 = S._local_ns(dates, S._mins(params["exit"]), "NY")
    xi = np.searchsorted(ns, t1, side="left")
    known = xi < n
    shut = np.zeros(len(dates), bool)
    shut[known] = (ns[xi[known]] - t1[known]) > 10 * MIN
    done, atr = S._atr(m1, ns, params["atr_tf"], int(params["atr_n"]))
    j = np.searchsorted(done, t0, side="right") - 1
    a = np.where(j >= 0, atr[np.maximum(j, 0)], np.nan)
    bc = m1["bc"].to_numpy()
    fri = np.flatnonzero(dates.dayofweek.to_numpy() == 4)
    f = pd.DataFrame({{"date": [str(dates[k].date()) for k in fri], "t0": t0[fri] // 1000000000, "open_ok": ok[fri],
                      "act_t": tsec(np.where(ei[fri] < n, ei[fri], -1)), "shut": shut[fri], "known": known[fri],
                      "next_1645_t": tsec(np.where(xi[fri] < n, xi[fri], -1)), "last_before_1645_t": tsec(xi[fri] - 1),
                      "atr": a[fri], "hour_rows": j[fri] + 1, "level": np.where(ei[fri] > 0, bc[np.clip(ei[fri] - 1, 0, n - 1)], np.nan),
                      "level_bar_t": tsec(np.where(ei[fri] > 0, ei[fri] - 1, -1)),
                      "atr_hour_t": np.where(j[fri] >= 0, done[np.maximum(j[fri], 0)] // 1000000000 - 3600, -1)}})
    f.to_parquet(os.path.join(OUTD, "fridays.parquet"))
    res["fridays"] = int(len(f))
    # depth (SPEC 2.2: 120 days of gold at every start; T6): the ATR read at each Friday's 13:30 when the bars start 120
    # days earlier, against the whole frame's
    rel = []
    for k in fri:
        if not np.isfinite(a[k]) or a[k] <= 0:
            continue
        lo_i = int(np.searchsorted(ns, t0[k] - 120 * 86400 * 1000000000, side="left"))
        if lo_i == 0:
            continue
        sub = m1.iloc[lo_i:]
        nss = ns[lo_i:]
        dn, at = S._atr(sub, nss, params["atr_tf"], int(params["atr_n"]))
        jj = int(np.searchsorted(dn, t0[k], side="right") - 1)
        v = at[jj] if jj >= 0 else np.nan
        rel.append(0.0 if v == a[k] else abs(v - a[k]) / abs(a[k]))
    rel = np.asarray(rel)
    res["depth_120d"] = {{"fridays": int(len(rel)), "bit_equal": int((rel == 0).sum()), "max_rel_diff": float(rel.max()) if len(rel) else 0.0}}
if CODE == "ORX":
    M = sys.modules["strategy_orb"]
    p = dict(M.DEFAULTS); p.update(params)
    tz = M.TZ[p["tz"]]
    loc = idx[[0, -1]].tz_convert(tz)
    dates = pd.date_range(loc[0].tz_localize(None).normalize(), loc[1].tz_localize(None).normalize(), freq="D")
    dates = dates[dates.dayofweek < 5]
    rs = M._local_times(dates, p["range_start"], tz)
    re_ = M._local_times(dates, p["range_end"], tz)
    ee = M._local_times(dates, p["entry_end"], tz)
    v = idx.values
    i0 = np.searchsorted(v, rs.values); i1 = np.searchsorted(v, re_.values); ie = np.searchsorted(v, ee.values)
    ah, bl, ac, bc = (m1[k].to_numpy(np.float64) for k in ("ah", "bl", "ac", "bc"))
    hi, lo, spr = M._range_stats(ah, bl, ac, bc, i0, i1)
    nb = i1 - i0
    width = hi - lo
    valid = (nb >= p["min_bars_frac"] * 420) & (i1 < n) & (ie > i1) & (width > 0)
    d = pd.DataFrame({{"date": [str(x.date()) for x in dates], "nbars": nb, "hi": hi, "lo": lo, "width": width,
                      "window_bar_t": tsec(np.where(ie > i1, i1, -1)), "valid": valid}})
    d.to_parquet(os.path.join(OUTD, "days.parquet"))
    s = M.sessions(m1, p)
    s = s[s.width > 0]
    res["days"] = int(len(d))
    res["valid_days"] = int(valid.sum())
    res["sessions_equal_valid_days"] = sorted(str(x.date()) for x in s.date) == sorted(d.date[valid])
    # the touch bar of each order: were both levels reached in it (the mid-open tie rule decided the side)?
    fi = orders.entry_i.to_numpy()
    lv, st = orders.level.to_numpy(), orders.stop.to_numpy()
    buy, sell = np.maximum(lv, st), np.minimum(lv, st)
    ao, bo = m1["ao"].to_numpy(), m1["bo"].to_numpy()
    mo = 0.5 * (ao[fi] + bo[fi])
    t = pd.DataFrame({{"entry_t": sec[fi], "both": (ah[fi] >= buy) & (bl[fi] <= sell), "d_up": np.abs(buy - mo), "d_dn": np.abs(mo - sell),
                      "side": orders.side.to_numpy()}})
    t.to_parquet(os.path.join(OUTD, "touch.parquet"))
    res["both_touched"] = int(t.both.sum())
    # razors (SPEC 7): a window bar, up to and including the touch, whose ask high or bid low lies within 1e-9 (relative)
    # of a level, on a valid day
    buf = p["buf_frac"] * width + p["buf_abs"]
    up_lv, dn_lv = hi + buf, lo - buf
    razors = []
    for k in np.flatnonzero(valid):
        sa, sb = ah[i1[k]:ie[k]], bl[i1[k]:ie[k]]
        hit = np.flatnonzero((sa >= up_lv[k]) | (sb <= dn_lv[k]))
        end = hit[0] + 1 if len(hit) else len(sa)
        rz = (np.abs(sa[:end] - up_lv[k]) <= 1e-9 * abs(up_lv[k])) | (np.abs(sb[:end] - dn_lv[k]) <= 1e-9 * abs(dn_lv[k]))
        if rz.any():
            j = int(np.flatnonzero(rz)[0])
            razors.append({{"date": str(dates[k].date()), "bar": str(idx[i1[k] + j]), "ask_high": float(sa[j]), "upper": float(up_lv[k]),
                            "bid_low": float(sb[j]), "lower": float(dn_lv[k]), "touch": bool(j == end - 1 and len(hit) > 0)}})
    res["razors"] = razors
print(json.dumps(res, default=str))
"""


_LAB = {}


def lab_run(code, kind):
    """the lab's make_orders and r2.run on one frame (fresh process), plus the rule's per-day quantities; outputs under
    check/out/test_G/ref/lab_<kind>/<code>/ (once per process)"""
    if (code, kind) in _LAB:
        return _LAB[(code, kind)]
    outd = os.path.join(REF, f"lab_{kind}", code)
    res = spawn(LAB_RUN_SRC.format(lab=LAB, code=code, frame=frame_path(kind), outd=outd))
    files = {n[:-8]: pd.read_parquet(os.path.join(outd, n)) for n in os.listdir(outd) if n.endswith(".parquet")}
    _LAB[(code, kind)] = (res, files)
    return res, files


def official_trades(code):
    p = os.path.join(LAB, "results", "r2", "recalc", "trades", f"{RULE[code]}__xauusd.parquet")
    return pd.read_parquet(p, filters=[("entry_time", "<", CUT)])


# ======================================================================================== the holes world
HOLES = os.path.join(OUT, "holes")
HOLES_SEED = 20261113
HOLES_PER_KIND = 8


def ny_win(day, a, b):
    """[a, b) New York wall clock on a date, UTC seconds"""
    return ny_utc(day, a), ny_utc(day, b)


def ldn_win(day, a, b):
    return (int(pd.Timestamp(f"{day} {a}").tz_localize(LDN).tz_convert("UTC").value // 10**9),
            int(pd.Timestamp(f"{day} {b}").tz_localize(LDN).tz_convert("UTC").value // 10**9))


def hole_cuts(gfp_fri, gfp_o, orx_days, orx_o, orx_t, t_lo, t_hi):
    """[(a, b, kind)] windows of UTC seconds to cut from the in-sample gold bars, aimed at the paths in-sample data barely
    reaches (chosen from the lab's own orders on the kept frame), plus random ones. GFP, on Fridays the lab trades:
      gfp_window  13:30-13:35 New York empty: the order never activates (the lab's _open_at fails)
      gfp_open    13:30-13:32 empty: the activation bar is 13:33, inside the 5 minutes
      gfp_1329    the 13:29 bar missing: the level is an earlier bar's bid close
      gfp_noon    the 12:00 New York hour empty: the ATR is an earlier hour's
      gfp_fill    13:36-14:29 empty: only the 13:30-13:35 bars may fill the limit
      gfp_exit7   16:45-16:51 empty: the exit bar is 16:52 (within the lab's 10 minutes)
      gfp_1645    16:40-16:59 empty: no quote by 16:55, a GFP hole day (the lab skips, the EA cannot know)
    ORX:
      orx_range   212 minutes of a valid London range cut: fewer than 210 bars, a DEC info line (the lab: no session)
      orx_window  the whole 07:00-12:00 London window empty: no order
      orx_touch   the lab's touch bar cut: the next touching bar, or none, decides
      orx_after   30 minutes cut just after a fill bar: the trade lives through a hole (stop at the worse of stop and open)
      orx_exit    16:00 New York -10 / +12 min cut on a time exit's date: the exit moves to 16:12, no gap rule
    random: 120 windows of 1 to 180 minutes anywhere."""
    rng = np.random.default_rng(HOLES_SEED)
    cuts = []
    pick = lambda arr, k: list(rng.choice(np.asarray(arr, dtype=object), size=min(k, len(arr)), replace=False))
    traded = sorted(set(str(utc(t).tz_convert(NY).date()) for t in tsecs(gfp_o.entry_t)))
    days = pick(traded, 7 * HOLES_PER_KIND)
    for k, (kind, a, b) in enumerate((("gfp_window", "13:30", "13:36"), ("gfp_open", "13:30", "13:33"), ("gfp_1329", "13:29", "13:30"),
                                      ("gfp_noon", "12:00", "13:00"), ("gfp_fill", "13:36", "14:30"), ("gfp_exit7", "16:45", "16:52"),
                                      ("gfp_1645", "16:40", "17:00"))):
        for d in days[k * HOLES_PER_KIND:(k + 1) * HOLES_PER_KIND]:
            cuts.append((*ny_win(d, a, b), kind))
    valid = [d for d, v, w in zip(orx_days.date, orx_days.valid, orx_days.window_bar_t) if v and w > 0]
    used = set()
    for d in pick(valid, HOLES_PER_KIND):
        cuts.append((*ldn_win(d, "00:30", "04:02"), "orx_range"))
        used.add(d)
    for d in pick([d for d in valid if d not in used], HOLES_PER_KIND):
        cuts.append((*ldn_win(d, "07:00", "12:00"), "orx_window"))
    e = tsecs(orx_o.entry_t)
    for t in pick(list(e[:-2]), HOLES_PER_KIND):
        cuts.append((int(t), int(t) + 60, "orx_touch"))
    ft = secs(orx_t.entry_time)
    for t in pick(list(ft[:-2]), HOLES_PER_KIND):
        cuts.append((int(t) + 60, int(t) + 31 * 60, "orx_after"))
    tx = secs(orx_t[orx_t.reason == "time"].exit_time)
    for t in pick(list(tx[:-2]), HOLES_PER_KIND):
        cuts.append((int(t) - 600, int(t) + 720, "orx_exit"))
    for _ in range(120):
        a = int(rng.integers(t_lo, t_hi - 3600)) // 60 * 60
        cuts.append((a, a + 60 * int(rng.integers(1, 181)), "random"))
    return sorted(cuts)


def holes_world():
    """the in-sample gold bars minus hole_cuts (the other symbols keep their in-sample bars): the EA's bar file, the frame
    rebuilt from it and that frame without the masked bars (the EA's kept bars), all under check/out/test_G/holes/"""
    import export_frames as ef
    import test_bars
    bin_p = os.path.join(HOLES, "XAUUSD.r_holes.bin")
    fr_p = os.path.join(HOLES, "xauusd_holes.parquet")
    kept_p = frame_path("holes_kept")
    spec_p = os.path.join(HOLES, "holes_world.json")
    kres, kf = lab_run("GFP", "kept")
    ores, of = lab_run("ORX", "kept")
    m1 = read_frame(frame_path("rebuilt"))
    ts = secs(m1.index)
    cuts = hole_cuts(kf["fridays"], kf["orders"], of["days"], of["orders"], of["trades"], int(ts[0]), int(ts[-1]))
    key = hashlib.sha256((repr(cuts) + repr((len(m1), int(ts[0]), int(ts[-1])))).encode()).hexdigest()
    if not (os.path.exists(spec_p) and json.load(open(spec_p)).get("key") == key and all(os.path.exists(p) for p in (bin_p, fr_p, kept_p))):
        os.makedirs(HOLES, exist_ok=True)
        drop = np.zeros(len(ts), bool)
        kinds = {}
        for a, b, kind in cuts:
            i, j = np.searchsorted(ts, a, "left"), np.searchsorted(ts, b, "left")
            kinds[kind] = kinds.get(kind, 0) + int((~drop[i:j]).sum())
            drop[i:j] = True
        mh = m1[~drop]
        t = ef.server_secs(mh.index)
        pts, spread = ef.to_points(mh)
        ef.write_bin(bin_p, t, pts, spread)
        _, rec = ef.read_bin(bin_p)
        fr = ef.rebuild(rec)
        assert (fr.index == mh.index.as_unit(fr.index.unit)).all(), "server -> UTC round trip"
        for c in mh.columns:
            assert (fr[c].to_numpy() == mh[c].to_numpy()).all(), f"the bar file does not give the frame back ({c})"
        mh.to_parquet(fr_p)
        reason = test_bars.mask_reasons(rec, "XAU", set())
        mh[reason == test_bars.KEPT].to_parquet(kept_p)
        json.dump({"key": key, "seed": HOLES_SEED, "bars_in": int(len(m1)), "bars_removed": int(drop.sum()),
                   "removed_by_kind": kinds, "masked_after": int((reason != test_bars.KEPT).sum()),
                   "cuts": [[a, b, k, ny_str(a), ny_str(b)] for a, b, k in cuts]}, open(spec_p, "w"), indent=1)
    info = json.load(open(spec_p))
    bp = dict(bars())
    bp["XAUUSD.r"] = bin_p
    return {"bars": bp, "cuts": len(cuts), "bars_removed": info["bars_removed"], "removed_by_kind": info["removed_by_kind"],
            "spec": spec_p}


_HW = {}


def holes_run(sanitize=False, fresh=False):
    """the EA over the holes world (plain, and the sanitizer build when asked); cached like the in-sample replay"""
    if "w" not in _HW:
        _HW["w"] = holes_world()
    w = _HW["w"]
    key = "san" if sanitize else "plain"
    if key not in _HW:
        exe, warn = build_ea(sanitize)
        rows, out, wall, files = replay(exe, "replay_holes" + ("_san" if sanitize else ""), bars_map=w["bars"],
                                        env_extra={"ASAN_OPTIONS": "detect_leaks=1"} if sanitize else None, fresh=fresh)
        _HW[key] = {"rows": rows, "out": out, "wall": round(wall, 1), "files": files, "warnings": warn}
    res = dict(_HW[key])
    res["world"] = w
    if sanitize:
        res["identical"] = journals_identical(_HW["plain"]["files"], res["files"]) if "plain" in _HW else None
    return res


# ======================================================================================== comparisons
def secs(ts):
    return pd.DatetimeIndex(ts).tz_convert("UTC").as_unit("s").asi8.astype(np.int64)


def tsecs(col):
    """bar times of a lab order column as UTC seconds: ref_lab.py writes timestamps (NaT for an exit beyond the frame),
    lab_run integer seconds (-1 there); both give -1 for "no bar\""""
    v = col.to_numpy() if hasattr(col, "to_numpy") else np.asarray(col)
    if v.dtype.kind in "iu":
        return v.astype(np.int64)
    s = secs(col)
    return np.where(pd.isna(pd.DatetimeIndex(col)), -1, s).astype(np.int64)


def utc(t):
    return pd.Timestamp(int(t), unit="s", tz="UTC")


def ny_str(t):
    return str(utc(t).tz_convert(NY))[:16] if t is not None and int(t) > 0 else "-"


def rel_diff(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    den = np.maximum(np.abs(a), np.abs(b))
    return np.where(a == b, 0.0, np.abs(a - b) / np.where(den > 0, den, 1.0))


def act_bar(idx, tf, tt):
    """the first bar starting in [tf, tt] (its start, seconds), -1 when none"""
    ai = np.searchsorted(idx, np.asarray(tf, np.int64), side="left")
    ok = (ai < len(idx)) & (idx[np.clip(ai, 0, len(idx) - 1)] <= np.asarray(tt, np.int64))
    return np.where(ok, idx[np.clip(ai, 0, len(idx) - 1)], -1)


def first_at_or_after(idx, x):
    i = np.searchsorted(idx, np.asarray(x, np.int64), side="left")
    return np.where(i < len(idx), idx[np.clip(i, 0, len(idx) - 1)], -1)


def last_before(idx, x):
    i = np.searchsorted(idx, np.asarray(x, np.int64), side="left") - 1
    return np.where(i >= 0, idx[np.clip(i, 0, len(idx) - 1)], -1)


def trade_rows(ea, lab, price_exact=("entry", "exit"), price_rel=("stop",)):
    """one row per trade of either side (merged on entry minute and side): what differs. Prices taken from bars must be
    equal; values built on Wilder or rolling values within REL"""
    m = lab.merge(ea, on=["entry_time", "side"], how="outer", suffixes=("_lab", "_ea"), indicator=True)
    out = []
    for _, r in m.iterrows():
        row = {"entry_time": str(r.entry_time), "side": int(r.side), "in": {"both": "both", "left_only": "lab only",
                                                                            "right_only": "EA only"}[r._merge]}
        bad = []
        if r._merge == "both":
            if r.exit_time_lab != r.exit_time_ea:
                bad.append("exit_time")
            if r.reason_lab != r.reason_ea:
                bad.append("reason")
            for c in price_exact:
                if not float(r[f"{c}_lab"]) == float(r[f"{c}_ea"]):
                    bad.append(c)
            for c in price_rel:
                d = float(rel_diff([r[f"{c}_lab"]], [r[f"{c}_ea"]])[0])
                row[f"{c}_rel_diff"] = d
                if d > REL:
                    bad.append(c)
            row.update({"exit_lab": str(r.exit_time_lab), "exit_ea": str(r.exit_time_ea), "reason": [r.reason_lab, r.reason_ea],
                        "stop": [float(r.stop_lab), float(r.stop_ea)]})
        else:
            row.update({"exit": str(r.exit_time_lab if r._merge == "left_only" else r.exit_time_ea),
                        "reason": r.reason_lab if r._merge == "left_only" else r.reason_ea})
            bad.append("missing")
        row["bad"] = bad
        out.append(row)
    return out


def trade_stats(ea, lab):
    m = lab.merge(ea, on=["entry_time", "side"], suffixes=("_lab", "_ea"))
    res = {"matched": int(len(m))}
    for c in ("entry", "stop", "exit"):
        d = rel_diff(m[f"{c}_lab"], m[f"{c}_ea"]) if len(m) else np.zeros(0)
        res[f"{c}_bit_equal"] = int((d == 0).sum())
        res[f"{c}_max_rel_diff"] = float(d.max()) if len(d) else 0.0
    return res


def window(trades, t_from, t_to):
    if not len(trades):
        return trades
    return trades[(trades.entry_time >= utc(t_from)) & (trades.exit_time <= utc(t_to))]


def official_diff(code, reb_trades):
    """the lab's trades on the rebuilt frame against the official trades (entries before 2022): what differs"""
    off = official_trades(code).reset_index(drop=True)
    b = reb_trades.reset_index(drop=True)
    m = off.merge(b, on=["entry_time", "side"], how="outer", suffixes=("_off", "_reb"), indicator=True)
    both = m[m._merge == "both"]
    same = (both.exit_time_off == both.exit_time_reb) & (both.reason_off == both.reason_reb)
    res = {"code": code, "official": int(len(off)), "rebuilt": int(len(b)), "same_entry_side": int(len(both)),
           "same_exit_and_reason": int(same.sum()), "only_official": int((m._merge == "left_only").sum()),
           "only_rebuilt": int((m._merge == "right_only").sum())}
    for c in ("entry", "exit", "R"):
        d = (both[f"{c}_off"] - both[f"{c}_reb"]).abs()
        res[f"max_abs_{c}_diff"] = float(d.max()) if len(d) else 0.0
    rows = []
    for _, r in m[(m._merge != "both") | ~((m.exit_time_off == m.exit_time_reb) & (m.reason_off == m.reason_reb))].iterrows():
        row = {"entry_time": str(r.entry_time), "side": int(r.side),
               "in": {"left_only": "official only", "right_only": "rebuilt only", "both": "both"}[r._merge],
               "official_exit": str(r.get("exit_time_off")), "official_reason": str(r.get("reason_off")),
               "rebuilt_exit": str(r.get("exit_time_reb")), "rebuilt_reason": str(r.get("reason_reb"))}
        if r._merge == "left_only" and pd.notna(r.exit_time_off) and r.exit_time_off >= CUT:
            row["cause"] = "the official exit falls in 2022 (beyond the in-sample frame)"
        rows.append(row)
    res["differences"] = rows
    return res


# ======================================================================================== unit worlds (generated C++)
UNIT_FAULTS = r"""// mock_faults.h of step G's unit program (generated by check/test_GFP.py; J's neutral hooks, except mf_session, which
// serves the Friday trade sessions the test sets in g_gs_*). Not J's file: a copy for this program only.
#pragma once
int  g_gs_n = -1;                      // -1: no information (as J's stub); else the number of Friday sessions listed
long g_gs_from[8], g_gs_to[8];
static void mf_init() {}
static bool mf_copyrates_fail(const string &) { return false; }
static int  mf_request(MqlTradeRequest &, MqlTradeResult &) { return 0; }
static void mf_after(const MqlTradeRequest &, MqlTradeResult &) {}
static void mf_event(long) {}
static bool mf_connected() { return true; }
static int  mf_session(const string &, int dow, uint idx, datetime &from, datetime &to)
  {
   if(g_gs_n < 0) return -1;
   if(dow != 5 || (int)idx >= g_gs_n) return 0;
   from = (datetime)g_gs_from[idx];
   to = (datetime)g_gs_to[idx];
   return 1;
  }
"""

UNIT_MAIN = r"""
#include <fstream>
#include <iostream>
#include <sstream>
#include <vector>
static void unit_tables()
  {
   g_cfg.harness = true;
   g_jrn_print = false;
   g_jrn_file = false;
   g_nsl = 2;
   g_sl[0].id = 8;  g_sl[0].code = "GFP"; g_sl[0].sym = CR_XAU; g_sl[0].sym2 = -1; g_sl[0].kind = CR_K_GFP; g_sl[0].magic = 20261208;
   g_sl[1].id = 10; g_sl[1].code = "ORX"; g_sl[1].sym = CR_XAU; g_sl[1].sym2 = -1; g_sl[1].kind = CR_K_ORX; g_sl[1].magic = 20261210;
   g_sym[CR_XAU].base = "XAUUSD";
   g_sym[CR_XAU].name = "XAUUSD.r";
  }
static void put_out(const string &w, const CrOut &o)
  {
   for(int i = 0; i < o.n_ord; i++)
      printf("W %s ORD %lld %d %d %.17g %lld %lld %lld %.17g %.17g %lld %d %lld\n", w.c_str(), (long long)o.ord[i].oid, o.ord[i].side,
             o.ord[i].etype, o.ord[i].level, (long long)o.ord[i].t_from, (long long)o.ord[i].t_to, (long long)o.ord[i].expiry_excl,
             o.ord[i].stop, o.ord[i].stop_dist, (long long)o.ord[i].x_sched, (int)o.ord[i].x_gap, (long long)o.ord[i].dec);
   for(int i = 0; i < o.n_dec; i++)
      printf("W %s INFO %lld %d %.17g %.17g\n", w.c_str(), (long long)o.dec[i].dec, o.dec[i].side, o.dec[i].v1, o.dec[i].v2);
  }
// bar worlds: lines "world t bo bh bl bc ao ah al ac" in time order per world; the driver's minute contract (SPEC 2.4):
// for every minute M, the bars starting before M (OnBar), then OnMinute(M)
static int run_worlds(const string &rule, const char *path)
  {
   std::ifstream f(path);
   std::string line;
   std::vector<std::string> wn;
   std::vector<CrBar> bars;
   while(std::getline(f, line))
     {
      std::istringstream s(line);
      std::string w;
      CrBar b;
      ZeroMemory(b);
      long long t;
      s >> w >> t >> b.bo >> b.bh >> b.bl >> b.bc >> b.ao >> b.ah >> b.al >> b.ac;
      if(!s) continue;
      b.t = (datetime)t;
      b.sym = CR_XAU;
      wn.push_back(w);
      bars.push_back(b);
     }
   size_t i = 0;
   while(i < bars.size())
     {
      std::string w = wn[i];
      size_t j = i;
      while(j < bars.size() && wn[j] == w) j++;
      CRuleGfp g;
      CRuleOrx x;
      bool ok = (rule == "gfp") ? g.Init(0) : x.Init(1);
      if(!ok) { printf("W %s INITFAIL\n", w.c_str()); i = j; continue; }
      datetime M0 = bars[i].t - bars[i].t % 60 + 60, M1 = bars[j - 1].t + 120;
      size_t k = i;
      for(datetime M = M0; M <= M1; M += 60)
        {
         CrOut out;
         while(k < j && bars[k].t < M)
           {
            CrOutClear(out);
            if(rule == "gfp") g.OnBar(CR_XAU, bars[k], out); else x.OnBar(CR_XAU, bars[k], out);
            put_out(w, out);
            k++;
           }
         CrOutClear(out);
         if(rule == "gfp") g.OnMinute(M, out); else x.OnMinute(M, out);
         put_out(w, out);
        }
      i = j;
     }
   return 0;
  }
int main(int argc, char **argv)
  {
   unit_tables();
   if(argc < 2) return 2;
   string cmd = argv[1];
   string err = "";
   if(cmd == "worlds" && argc >= 4) return run_worlds(argv[2], argv[3]);
   if(cmd == "cal" && argc >= 5)                      // cal <closures> <from t0> <to t0>: every Friday 13:30 New York
     {
      if(!ClkInit(argv[2], err)) { printf("CLKERR %s\n", err.c_str()); return 3; }
      for(long t = atol(argv[3]); t <= atol(argv[4]); t += 86400)
        {
         datetime ny = ClkUtcToNy((datetime)t);
         datetime t0 = ClkNyToUtc(ClkDay(ny) + 810 * 60);
         if(ClkDow(ny) != 5 || !GfpIsDecision(t0)) continue;
         double v2 = 0.0;
         int c = GfpCalendarSkip(t0, "XAUUSD.r", v2);
         printf("CAL %lld %d %.17g %lld\n", (long long)t0, c, v2, (long long)GfpExitTime(ClkDay(ny)));
        }
      return 0;
     }
   if(cmd == "sess" && argc >= 3)                     // sess <t0> then lines "n f0 t0 f1 t1 ..." on stdin
     {
      ClkInit("", err);
      datetime t0 = (datetime)atol(argv[2]);
      datetime t1 = ClkNyToUtc(ClkDay(ClkUtcToNy(t0)) + CR_GFP_OPEN_MIN * 60);   // the rule's own limit (16:46, SPEC 3 v2.1)
      std::string line;
      while(std::getline(std::cin, line))
        {
         std::istringstream s(line);
         int n;
         if(!(s >> n)) continue;
         g_gs_n = n;
         for(int k = 0; k < n && k < 8; k++) s >> g_gs_from[k] >> g_gs_to[k];
         long e = 0;
         bool sk = GfpSessionShort("XAUUSD.r", t0, t1, e);
         double v2 = 0.0;
         int c = GfpCalendarSkip(t0, "XAUUSD.r", v2);
         printf("SESS %d %ld %d %.17g\n", (int)sk, e, c, v2);
        }
      g_gs_n = -1;
      return 0;
     }
   if(cmd == "latest" && argc >= 3)                   // latest <gfp|orx> then lines "open_time comment_dec" on stdin
     {
      ClkInit("", err);
      CRuleGfp g;
      CRuleOrx x;
      g.Init(0);
      x.Init(1);
      string rule = argv[2];
      long long o, c;
      while(std::cin >> o >> c)
         printf("LATEST %lld %lld %lld\n", o, c, (long long)(rule == "gfp" ? g.LatestExit((datetime)o, (datetime)c) : x.LatestExit((datetime)o, (datetime)c)));
      return 0;
     }
   if(cmd == "init")                                  // the retired ids and the symbol guard
     {
      int ids[6] = {10, 11, 12, 19, 20, 8};
      for(int k = 0; k < 6; k++)
        {
         g_sl[1].id = ids[k];
         CRuleOrx x;
         printf("INIT ORX %d %d\n", ids[k], (int)x.Init(1));
        }
      g_sl[1].id = 10;
      g_sl[1].sym = CR_BTC;
      CRuleOrx x2;
      printf("INIT ORXBTC 10 %d\n", (int)x2.Init(1));
      g_sl[0].sym = CR_ETH;
      CRuleGfp g2;
      printf("INIT GFPETH 8 %d\n", (int)g2.Init(0));
      return 0;
     }
   if(cmd == "orxexit" && argc >= 4)                  // orxexit <from> <to>: every London weekday
     {
      ClkInit("", err);
      for(long t = atol(argv[2]); t <= atol(argv[3]); t += 86400)
        {
         datetime ld = ClkDay(ClkUtcToLdn((datetime)t));
         int dw = ClkDow(ld);
         if(dw < 1 || dw > 5) continue;
         printf("OX %lld %lld\n", (long long)ld, (long long)OrxExitTime(ld));
        }
      return 0;
     }
   return 2;
  }
"""


_UNIT = {}


def unit_exe(sanitize=False):
    """the unit program: the private tree's two rule files (and what they include), the mock without its main and a test
    copy of the session hook, then UNIT_MAIN"""
    key = "san" if sanitize else "plain"
    if key in _UNIT:
        return _UNIT[key]
    t = tree()
    work = os.path.join(TREE, "unit" + ("_san" if sanitize else ""))
    if os.path.isdir(work):
        shutil.rmtree(work)
    har = os.path.join(work, "harness")
    os.makedirs(har)
    for n in ("mock_replay.h", "mql5_shim.h"):
        shutil.copy(os.path.join(t["harness"], n), os.path.join(har, n))
    open(os.path.join(har, "mock_faults.h"), "w").write(UNIT_FAULTS)
    entry = os.path.join(t["src"], "_unit_G.mqh")
    open(entry, "w").write('#include "CR_Rule_GoldFri.mqh"\n#include "CR_Rule_Orb.mqh"\n')
    B.translate(entry, os.path.join(work, "ea.cpp"))
    run = os.path.join(work, "run.cpp")
    with open(run, "w") as f:
        f.write("#define MOCK_REPLAY_NO_MAIN\n")
        f.write(f'#include "{os.path.join(har, "mock_replay.h")}"\n#include "{os.path.join(work, "ea.cpp")}"\n')
        f.write(UNIT_MAIN)
    exe = os.path.join(work, "unit")
    warn = compile_cpp(run, exe, sanitize, [har, work], ["CR_HARNESS", "CR_XAU_COMM_PTS=0"])
    _UNIT[key] = (exe, warn)
    return exe, warn


def unit(args, stdin=None, sanitize=False):
    exe, _ = unit_exe(sanitize)
    r = subprocess.run([exe] + [str(a) for a in args], input=stdin, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"unit {args[0]} failed ({r.returncode}): {r.stdout[-1000:]} {r.stderr[-3000:]}")
    return r.stdout


def parse_world_out(text):
    """W lines of the unit program -> {world: {"ord": [...], "info": [...]}}"""
    out = {}
    for ln in text.splitlines():
        p = ln.split()
        if not p or p[0] != "W":
            continue
        w = out.setdefault(p[1], {"ord": [], "info": [], "initfail": False})
        if p[2] == "ORD":
            out[p[1]]["ord"].append({"oid": int(p[3]), "side": int(p[4]), "et": int(p[5]), "lv": float(p[6]), "tf": int(p[7]),
                                     "tt": int(p[8]), "exp": int(p[9]), "st": float(p[10]), "sd": float(p[11]), "x": int(p[12]),
                                     "xg": int(p[13]), "dec": int(p[14])})
        elif p[2] == "INFO":
            w["info"].append({"dec": int(p[3]), "side": int(p[4]), "v1": float(p[5]), "v2": float(p[6])})
        elif p[2] == "INITFAIL":
            w["initfail"] = True
    return out


def write_worlds(worlds, path):
    """{name: frame} -> the unit program's bar file (frame order, UTC seconds; repr: an exact round trip)"""
    cols = ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac")
    with open(path, "w") as f:
        for name, m1 in worlds.items():
            t = secs(m1.index)
            v = [m1[c].to_numpy(np.float64).tolist() for c in cols]
            for i in range(len(m1)):
                f.write(f"{name} {t[i]} " + " ".join(repr(v[k][i]) for k in range(8)) + "\n")


def synth_frame(start, end, seed, base=1650.0, spread=0.19, drop=None):
    """a gold-like M1 frame (random walk on the 2-digit grid, spread fixed), bars every minute in [start, end) UTC, minus
    the [a, b) windows of drop"""
    rng = np.random.default_rng(seed)
    t = pd.date_range(pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC"), freq="min", inclusive="left")
    keep = np.ones(len(t), bool)
    for a, b in (drop or []):
        keep &= ~((t >= pd.Timestamp(a, tz="UTC")) & (t < pd.Timestamp(b, tz="UTC")))
    t = t[keep]
    n = len(t)
    step = np.round(rng.normal(0, 0.25, n), 2)
    c = np.round(base + np.cumsum(step), 2)
    o = np.round(np.r_[base, c[:-1]], 2)
    hi = np.round(np.maximum(o, c) + np.round(np.abs(rng.normal(0, 0.15, n)), 2), 2)
    lo = np.round(np.minimum(o, c) - np.round(np.abs(rng.normal(0, 0.15, n)), 2), 2)
    df = pd.DataFrame({"bo": o, "bh": hi, "bl": lo, "bc": c}, index=pd.DatetimeIndex(t, name="ts"))
    for k in "ohlc":
        df["a" + k] = np.round(df["b" + k] + spread, 2)
    return df[["bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"]]


LAB_SYNTH_SRC = r"""
import sys, os, json
sys.dont_write_bytecode = True
import numpy as np, pandas as pd
LAB, CODE, FRAMES = {lab!r}, {code!r}, {frames!r}
sys.path.insert(0, LAB); sys.path.insert(0, os.path.join(LAB, "r2"))
import recalc
reg = {{(s[1], s[2]): s for s in recalc.sleeves()}}
RULE = {{"GFP": "GOLD_FRI_PM", "ORX": "orb_asia_2d_buf10"}}[CODE]
track, name, sym, mo, params = reg[(RULE, "xauusd")]
out = {{}}
for w, p in FRAMES.items():
    m1 = pd.read_parquet(p)
    o = mo(m1, **params).reset_index(drop=True)
    sec = m1.index.values.astype("datetime64[ns]").astype(np.int64) // 1000000000
    n = len(m1)
    rows = []
    for k in range(len(o)):
        r = o.iloc[k]
        g = lambda c: (float(r[c]) if c in o and pd.notna(r[c]) else None)
        rows.append({{"entry_t": int(sec[int(r.entry_i)]), "side": int(r.side), "etype": int(r.etype), "level": g("level"),
                     "stop": g("stop"), "stop_dist": g("stop_dist"),
                     "exit_t": int(sec[int(r.exit_i)]) if 0 <= int(r.exit_i) < n else -1,
                     "expiry_t": int(sec[int(r.expiry_i)]) if 0 <= int(r.expiry_i) < n else -1}})
    out[w] = rows
    if CODE == "GFP":
        S = sys.modules["r2_overnight_strategy"]
        ns = m1.index.values.astype("datetime64[ns]").astype(np.int64)
        done, atr = S._atr(m1, ns, "1h", 14)
        out[w + ":atr"] = [[int(d // 1000000000), (None if not np.isfinite(a) else float(a))] for d, a in zip(done, atr)]
print(json.dumps(out))
"""


def lab_synth(code, worlds):
    d = os.path.join(OUT, "unit", code)
    os.makedirs(d, exist_ok=True)
    paths = {}
    for w, m1 in worlds.items():
        paths[w] = os.path.join(d, f"{w}.parquet")
        m1.to_parquet(paths[w])
    return spawn(LAB_SYNTH_SRC.format(lab=LAB, code=code, frames=paths))


def ny_utc(day, hhmm):
    """UTC seconds of a New York wall-clock time on a calendar date"""
    return int(pd.Timestamp(f"{day} {hhmm}").tz_localize(NY).tz_convert("UTC").value // 10**9)


def gfp_unit():
    """the unit worlds of GFP: calendar, sessions, LatestExit, retired-id guard, bar worlds against the lab"""
    sys.path.insert(0, os.path.join(LAB, "r2", "tracks", "idx_us"))
    import idxus_lib
    res = {}
    exe, warn = unit_exe()
    res["build_warnings"] = warn
    # 1. the calendar on every Friday of 2012-2035 (no typed closure): codes 1 / 2 exactly us_holidays' full / half Fridays
    full, half = set(), set()
    for y in range(2011, 2037):
        f, h = idxus_lib.us_holidays(y)
        full |= f
        half |= h
    t_a, t_b = ny_utc("2012-01-06", "13:30"), ny_utc("2035-12-28", "13:30")
    got = [ln.split() for ln in unit(["cal", "", t_a - 86400, t_b + 86400]).splitlines() if ln.startswith("CAL")]
    bad, n_code = [], {}
    for p in got:
        t0, code, x = int(p[1]), int(p[2]), int(p[4])
        d = utc(t0).tz_convert(NY)
        want = 1 if d.date() in full else (2 if d.date() in half else 0)
        n_code[code] = n_code.get(code, 0) + 1
        want_t0 = ny_utc(str(d.date()), "13:30")
        if code != want or t0 != want_t0 or x != ny_utc(str(d.date()), "16:45") or d.dayofweek != 4:
            bad.append({"date": str(d.date()), "code": code, "want": want})
    fridays = pd.date_range("2012-01-06", "2035-12-28", freq="W-FRI")
    res["calendar_2012_2035"] = {"fridays": len(got), "expected_fridays": int(len(fridays)), "codes": n_code, "wrong": bad[:10],
                                 "pass": not bad and len(got) == len(fridays)}
    # 2. typed closures (InpExtraClosures): a window holding 13:30, one starting 16:45 (skip) and 16:46 (no skip: the 16:45
    #    exit bar can trade, SPEC 3 GFP v2.1, review F7), typed NYSE / HALF
    typed = ("XAU 2027.03.12 15:00-2027.03.12 16:00;NYSE 2027.03.19;HALF 2027.04.02;XAU 2027.04.09 16:46-2027.04.09 17:30;"
             "XAU 2027.04.16 16:45-2027.04.16 17:30;XAU 2027.04.23 09:00-2027.04.23 13:31;XAU 2027.04.30 13:31-2027.04.30 13:40")
    want = {"2027-03-12": (3, ny_utc("2027-03-12", "15:00")), "2027-03-19": (1, 0), "2027-04-02": (2, 0), "2027-04-09": (0, 0),
            "2027-04-16": (3, ny_utc("2027-04-16", "16:45")), "2027-04-23": (3, ny_utc("2027-04-23", "09:00")),
            "2027-04-30": (3, ny_utc("2027-04-30", "13:31")), "2027-03-05": (0, 0), "2027-05-07": (0, 0)}
    got = {str(utc(int(p[1])).tz_convert(NY).date()): (int(p[2]), int(float(p[3])))
           for p in (ln.split() for ln in unit(["cal", typed, ny_utc("2027-03-01", "13:30"), ny_utc("2027-05-10", "13:30")]).splitlines()
                     if ln.startswith("CAL"))}
    wrong = {d: {"got": got.get(d), "want": w} for d, w in want.items() if got.get(d) != w}
    res["typed_closures"] = {"checked": len(want), "wrong": wrong, "pass": not wrong}
    # 3. broker Friday sessions (seconds of the server day; 13:30 New York = 20:30 server = 73800, 16:46 = 23:46 = 85560: a
    #    session must reach 16:46 New York, SPEC 3 GFP v2.1, review F7; 16:55 skipped a session ending at 23:54)
    t0 = ny_utc("2019-03-08", "13:30")
    cases = [("no information", "-1", (0, -1, 0, 0.0)), ("none listed", "0", (0, -1, 0, 0.0)),
             ("00:00-23:59", "1 0 86340", (0, 86340, 0, 0.0)), ("ends 23:46 exactly", "1 0 85560", (0, 85560, 0, 0.0)),
             ("ends 23:54 (skipped before v2.1)", "1 0 86040", (0, 86040, 0, 0.0)),
             ("ends 23:45", "1 0 85500", (1, 85500, 4, 85500.0)), ("two, the second to midnight (0)", "2 3600 72000 73800 0", (0, 86400, 0, 0.0)),
             ("one that misses 20:30", "1 3600 72000", (1, -1, 4, -1.0)), ("ends at 20:30, next from 20:33", "2 3600 73800 74000 86400", (1, -1, 4, -1.0)),
             ("to = 86400 (1970.01.02)", "1 3600 86400", (0, 86400, 0, 0.0)),
             ("two holding 20:30, the longer to 23:58", "2 60000 80000 70000 86280", (0, 86280, 0, 0.0))]
    lines = unit(["sess", t0], stdin="\n".join(c[1] for c in cases) + "\n").splitlines()
    sres = []
    for (name, _, w), ln in zip(cases, [x for x in lines if x.startswith("SESS")]):
        p = ln.split()
        g = (int(p[1]), int(p[2]), int(p[3]), float(p[4]))
        sres.append({"case": name, "got": g, "want": w, "ok": g == w})
    res["sessions"] = {"cases": sres, "pass": len(sres) == len(cases) and all(s["ok"] for s in sres)}
    # 4. LatestExit: 16:45 New York of the open's New York date, the comment only cross-checks
    fr = [d for d in pd.date_range("2013-01-04", "2021-12-31", freq="W-FRI")][::7]
    qs, want = [], []
    for d in fr:
        ds = str(d.date())
        x = ny_utc(ds, "16:45")
        for o, c in ((ny_utc(ds, "13:31"), ny_utc(ds, "13:30")), (ny_utc(ds, "14:36"), 0), (ny_utc(ds, "14:20"), ny_utc(ds, "09:00")),
                     (ny_utc(ds, "13:45"), ny_utc(ds, "13:30") - 7 * 86400)):
            qs.append(f"{o} {c}")
            want.append(x)
    got = [int(ln.split()[3]) for ln in unit(["latest", "gfp"], stdin="\n".join(qs) + "\n").splitlines() if ln.startswith("LATEST")]
    res["latest_exit"] = {"queries": len(qs), "wrong": int(sum(g != w for g, w in zip(got, want))), "pass": got == want}
    # 5. Init guards (gold only; ORX refuses the retired ids 11-19)
    ini = [ln.split() for ln in unit(["init"]).splitlines() if ln.startswith("INIT")]
    want_ini = {("ORX", "10"): "1", ("ORX", "11"): "0", ("ORX", "12"): "0", ("ORX", "19"): "0", ("ORX", "20"): "1", ("ORX", "8"): "1",
                ("ORXBTC", "10"): "0", ("GFPETH", "8"): "0"}
    got_ini = {(p[1], p[2]): p[3] for p in ini}
    res["init_guards"] = {"got": {f"{k[0]} {k[1]}": v for k, v in got_ini.items()}, "pass": got_ini == want_ini}
    # 6. bar worlds against the lab's make_orders (>= 3000 bars each, the lab's minimum) and its _atr
    worlds = {
        "normal": synth_frame("2013-01-02 00:00", "2013-01-05 00:00", 1),
        # the 13:29 bar missing: the level is the 13:28 bar's bid close
        "no1329": synth_frame("2013-01-02 00:00", "2013-01-05 00:00", 2, drop=[("2013-01-04 18:29", "2013-01-04 18:30")]),
        # no bar in [13:30, 13:35]: the EA emits, the order never activates (the lab: no order)
        "nowindow": synth_frame("2013-01-02 00:00", "2013-01-05 00:00", 3, drop=[("2013-01-04 18:30", "2013-01-04 18:36")]),
        # the 12:00 New York hour empty: the ATR is the 11:00 hour's
        "no12h": synth_frame("2013-01-02 00:00", "2013-01-05 00:00", 4, drop=[("2013-01-04 17:00", "2013-01-04 18:00")]),
        # warm-up: 14 hour rows complete at 13:30 (NaN, skip) and 15 rows (valid)
        "warm14": synth_frame("2013-01-04 04:00", "2013-01-07 00:00", 5),
        "warm15": synth_frame("2013-01-04 03:00", "2013-01-07 00:00", 6),
        # summer time (13:30 EDT = 17:30 UTC), holes in the morning, a data hole over 16:45 (a hole day: the lab skips)
        "summer": synth_frame("2013-07-08 00:00", "2013-07-13 00:00", 7, drop=[("2013-07-12 13:00", "2013-07-12 14:30")]),
        "hole1645": synth_frame("2013-07-08 00:00", "2013-07-13 00:00", 8, drop=[("2013-07-12 20:40", "2013-07-12 21:00")]),
        # a NYSE holiday Friday with bars all day (Good Friday 2014-04-18): the calendar skips, the lab would trade
        "goodfri": synth_frame("2014-04-15 00:00", "2014-04-19 00:00", 9),
    }
    wpath = os.path.join(OUT, "unit", "gfp_worlds.txt")
    os.makedirs(os.path.dirname(wpath), exist_ok=True)
    write_worlds(worlds, wpath)
    ea = parse_world_out(unit(["worlds", "gfp", wpath]))
    lab = lab_synth("GFP", worlds)
    # what each world must show: "equal" = one EA order, equal to the lab's field by field (the same doubles in, so bit
    # for bit); otherwise (EA orders, EA skip codes, lab orders)
    expect = {"normal": "equal", "no1329": "equal", "no12h": "equal", "warm15": "equal", "summer": "equal",
              "warm14": (0, [5.0], 0), "nowindow": (1, [], 0), "hole1645": (1, [], 0), "goodfri": (0, [1.0], 1)}
    wres = {}
    for w, m1 in worlds.items():
        e = ea.get(w, {"ord": [], "info": []})
        lo = lab[w]
        atr = {d: a for d, a in lab[w + ":atr"]}
        idx = secs(m1.index)
        rows = []
        for o in e["ord"]:
            # the ATR the lab reads at 13:30: the last hour row whose nominal end is <= 13:30
            done = sorted(d for d in atr if d <= o["tf"])
            lab_atr = atr[done[-1]] if done else None
            rows.append({"day": str(utc(o["tf"]).tz_convert(NY).date()), "level": o["lv"], "sd": o["sd"],
                         "lab_atr_x3": None if lab_atr is None else 3.0 * lab_atr, "act_bar": int(act_bar(idx, [o["tf"]], [o["tt"]])[0]),
                         "exit_bar": int(first_at_or_after(idx, [o["x"]])[0]), "expiry_bar": int(last_before(idx, [o["exp"]])[0])})
        if expect[w] == "equal":
            ok = len(e["ord"]) == 1 and len(lo) == 1 and not e["info"]
            if ok:
                o, r, q = e["ord"][0], lo[0], rows[0]
                ok = (o["side"] == r["side"] == 1 and o["et"] == r["etype"] == 2 and o["lv"] == r["level"]
                      and q["act_bar"] == r["entry_t"] and q["exit_bar"] == r["exit_t"] and q["expiry_bar"] == r["expiry_t"]
                      and o["sd"] == r["stop_dist"] and o["sd"] == q["lab_atr_x3"] and o["xg"] == 0)
        else:
            n_ord, codes, n_lab = expect[w]
            ok = len(e["ord"]) == n_ord and [i["v1"] for i in e["info"]] == codes and len(lo) == n_lab
            if w == "warm14":
                ok &= bool(e["info"]) and e["info"][0]["v2"] == 14.0
            if w == "nowindow":
                ok &= bool(rows) and rows[0]["act_bar"] == -1
        wres[w] = {"expect": expect[w] if expect[w] == "equal" else {"ea_orders": expect[w][0], "ea_skip_codes": expect[w][1],
                                                                      "lab_orders": expect[w][2]},
                   "ea_orders": rows, "ea_info": e["info"], "lab_orders": lo, "pass": bool(ok)}
    res["bar_worlds"] = wres
    res["pass"] = (not warn and res["calendar_2012_2035"]["pass"] and res["typed_closures"]["pass"] and res["sessions"]["pass"]
                   and res["latest_exit"]["pass"] and res["init_guards"]["pass"] and all(v["pass"] for v in wres.values()))
    return res


# ======================================================================================== the GFP test
EXPECT = {"side": 1, "et": 2, "xg": 0, "ref": 0, "vle": 0, "xh": 0, "ax": 0, "st": 0.0, "tr": 0.0, "be": 0.0, "tg": 0.0, "td": 0.0}


def gfp_decisions(rows, lab_o, fri, idx, t_first, label):
    """the EA's GFP orders and skip lines against the lab's orders of one frame (idx: that frame's bar starts, seconds)"""
    ea = dec_rows(rows, "GFP", "ord")
    info = dec_rows(rows, "GFP", "info")
    res = {"frame": label, "lab_orders": int(len(lab_o)), "ea_orders": int(len(ea)), "ea_skip_lines": int(len(info))}
    dup = int(ea.oid.duplicated().sum()) if len(ea) else 0
    ea = ea.drop_duplicates("oid", keep="last").copy()
    ea["day"] = [str(utc(t).tz_convert(NY).date()) for t in ea.tf]
    ea["act"] = act_bar(idx, ea.tf.to_numpy(np.int64), ea.tt.to_numpy(np.int64))
    ea["xbar"] = first_at_or_after(idx, ea.x.to_numpy(np.int64))
    ea["expbar"] = last_before(idx, ea.exp.to_numpy(np.int64))
    own = {"window_13:30_13:35": int(((ea.tt - ea.tf) != 300).sum() + (ea.tf != np.array([ny_utc(d, "13:30") for d in ea.day])).sum()),
           "expiry_14:30": int((ea.exp - ea.tf != 3600).sum()),
           "exit_16:45": int((ea.x != np.array([ny_utc(d, "16:45") for d in ea.day])).sum()),
           "oid": int((ea.oid != ea.tf * 100 + SID["GFP"]).sum()), "dec": int((ea.utc != ea.tf).sum())}
    fields = {k: int((ea[k] != v).sum()) for k, v in EXPECT.items()}
    lab = lab_o.reset_index(drop=True).copy()
    lab["entry_s"] = tsecs(lab.entry_t)
    lab["exit_s"] = tsecs(lab.exit_t)
    lab["day"] = [str(utc(t).tz_convert(NY).date()) for t in lab.entry_s]
    lab["expiry_t"] = tsecs(lab.expiry_t) if "expiry_t" in lab else idx[lab.expiry_i.to_numpy()]
    L = lab.set_index("day")
    E = ea.set_index("day")
    both = L.index.intersection(E.index)
    only_lab = sorted(L.index.difference(E.index))
    only_ea = sorted(E.index.difference(L.index))
    Lb, Eb = L.loc[both], E.loc[both]
    rd = rel_diff(Lb.stop_dist.to_numpy(), Eb.sd.to_numpy())
    eq = {"level": (Lb.level.to_numpy() == Eb.lv.to_numpy()), "entry_bar": (Lb.entry_s.to_numpy() == Eb.act.to_numpy()),
          "expiry_bar": (Lb.expiry_t.to_numpy() == Eb.expbar.to_numpy()), "exit_bar": (Lb.exit_s.to_numpy() == Eb.xbar.to_numpy()),
          "side": (Lb.side.to_numpy() == Eb.side.to_numpy())}
    wrong = []
    for k, d in enumerate(both):
        bad = [n for n, v in eq.items() if not v[k]] + (["stop_dist"] if rd[k] > REL else [])
        if bad:
            wrong.append({"day": d, "fields": bad, "stop_dist": [float(Lb.stop_dist.iloc[k]), float(Eb.sd.iloc[k])],
                          "stop_dist_rel_diff": float(rd[k]), "level": [float(Lb.level.iloc[k]), float(Eb.lv.iloc[k])]})
    F = fri.set_index("date")
    cls = []
    for d in only_ea:
        f = F.loc[d] if d in F.index else None
        e = E.loc[d]
        if f is None:
            why = "unexplained (no such Friday in the lab's table)"
        elif e.act < 0 and not bool(f.open_ok):
            why = "no kept bar in [13:30, 13:35]: never activates (the lab's _open_at fails)"
        elif bool(f.shut) and bool(f.open_ok):
            why = "GFP hole day"
        else:
            why = "unexplained"
        cls.append({"day": d, "class": why, "act_bar": ny_str(e.act), "lab_next_bar_after_16:45": ny_str(f.next_1645_t) if f is not None else "-",
                    "lab_last_bar_before_16:45": ny_str(f.last_before_1645_t) if f is not None else "-"})
    # skip lines
    skips = []
    for _, r in info.iterrows():
        d = str(utc(int(r.utc)).tz_convert(NY).date())
        skips.append({"day": d, "code": int(r.v1), "v2": float(r.v2), "lab_order": d in L.index})
    sk_codes = {}
    for s in skips:
        sk_codes[s["code"]] = sk_codes.get(s["code"], 0) + 1
    skip_with_lab_order = [s for s in skips if s["lab_order"]]
    # every Friday of the replay: an order or a skip line
    fr_days = [d for d, t in zip(fri.date, fri.t0) if t >= t_first]
    seen = set(ea.day) | set(s["day"] for s in skips)
    silent = sorted(set(fr_days) - seen)
    res.update({"matched": int(len(both)), "duplicates": dup, "own_fields_wrong": own, "fields_not_as_expected": {k: v for k, v in fields.items() if v},
                "wrong": wrong, "n_wrong": len(wrong), "stop_dist_bit_equal": int((rd == 0).sum()),
                "stop_dist_max_rel_diff": float(rd.max()) if len(rd) else 0.0, "only_lab": only_lab, "only_ea": cls,
                "skip_lines_by_code": sk_codes, "skip_lines": skips, "skip_line_but_lab_order": skip_with_lab_order,
                "fridays_in_replay": len(fr_days), "silent_fridays": silent})
    return res


def skip_set(dec, fri, t_first):
    """SPEC 8 G: the EA's calendar skips against the lab's skipped Fridays"""
    lab_skip = set(d for d, t, ok in zip(fri.date, fri.t0, fri.lab_order) if t >= t_first and not ok)
    cal = set(s["day"] for s in dec["skip_lines"] if s["code"] in (1, 2, 3, 4))
    holes = set(c["day"] for c in dec["only_ea"] if c["class"] == "GFP hole day")
    nowin = set(c["day"] for c in dec["only_ea"] if c["class"].startswith("no kept bar"))
    res = {"lab_skipped_fridays": len(lab_skip), "ea_calendar_skips": len(cal), "hole_days": sorted(holes),
           "no_bar_in_window": sorted(nowin),
           "calendar_skip_but_lab_trades": sorted(cal - lab_skip), "lab_skip_not_explained": sorted(lab_skip - cal - holes - nowin),
           "calendar_equals_lab_minus_hole_days": cal == (lab_skip - holes - nowin)}
    res["pass"] = not res["calendar_skip_but_lab_trades"] and not res["lab_skip_not_explained"] and res["calendar_equals_lab_minus_hole_days"]
    return res


def gfp_trades(rows, lab_t, t_first, t_last, hole_days, label, cause_ok=None):
    """the journal's GFP paper trades against r2.run's (one frame): per-trade rows, causes, and compare.cmp_trades"""
    ea = compare.paper_trades(rows, "GFP")
    lab = window(lab_t, t_first, t_last)
    ea_w = ea[ea.entry_time >= utc(t_first)] if len(ea) else ea
    tr = trade_rows(ea_w, lab)
    diffs = [r for r in tr if r["bad"]]
    for r in diffs:
        day = str(pd.Timestamp(r["entry_time"]).tz_convert(NY).date())
        if day in hole_days and r["in"] == "EA only":
            r["cause"] = "GFP hole day: the lab skipped the Friday (its 16:45 test reads a future data hole)"
        elif cause_ok is not None and cause_ok(r):
            r["cause"] = cause_ok(r)
    unexplained = [r for r in diffs if "cause" not in r]
    cmp = compare.cmp_trades(rows, lab_t, "GFP", t_from=t_first, t_to=t_last, rel=REL)
    res = {"frame": label, "lab_trades": int(len(lab)), "ea_trades": int(len(ea_w)), "differences": diffs,
           "unexplained": len(unexplained), "compare_cmp_trades": cmp, "all_rows": tr}
    res.update(trade_stats(ea_w, lab))
    res["pass"] = not unexplained and res["matched"] > 0
    return res


def gfp_holes(sanitize, fresh):
    """the holes world: the EA on the gold bars with hole_cuts removed against the lab on the same bars (kept frame)"""
    hw = holes_run(False, fresh)
    rows = hw["rows"]
    res = {"world": {k: hw["world"][k] for k in ("cuts", "bars_removed", "removed_by_kind")}, "replay": hw["out"], "wall_s": hw["wall"],
           "s0_contract": s0_contract(rows)}
    info, lf = lab_run("GFP", "holes_kept")
    fri, lo, lt = lf["fridays"].copy(), lf["orders"], lf["trades"]
    lo_days = set(str(utc(t).tz_convert(NY).date()) for t in tsecs(lo.entry_t))
    fri["lab_order"] = [d in lo_days for d in fri.date]
    idx = secs(read_frame(frame_path("holes_kept")).index)
    t_first, t_last = first_minute(rows), int(idx[-1]) - 1
    dec = gfp_decisions(rows, lo, fri, idx, t_first, "holes")
    ss = skip_set(dec, fri, t_first)
    trd = gfp_trades(rows, lt, t_first, t_last, set(ss["hole_days"]), "holes")
    trd.pop("all_rows", None)
    tr = fri[fri.lab_order]
    xt = lt[lt.reason == "time"]
    cov = {"orders_never_activated": len(ss["no_bar_in_window"]), "hole_days": len(ss["hole_days"]),
           "activation_after_13:30": int((tr.act_t > tr.t0).sum()),
           "level_not_from_13:29": int(sum(ny_str(t)[-5:] != "13:29" for t in tr.level_bar_t)),
           "atr_not_from_12:00": int(sum(ny_str(t)[-5:] != "12:00" for t in tr.atr_hour_t)),
           "time_exit_not_16:45": int(sum(str(pd.Timestamp(t).tz_convert(NY))[11:16] != "16:45" for t in xt.exit_time))}
    dec_ok = (dec["n_wrong"] == 0 and not dec["only_lab"] and dec["duplicates"] == 0
              and not [c for c in dec["only_ea"] if c["class"].startswith("unexplained")]
              and not any(dec["own_fields_wrong"].values()) and not dec["fields_not_as_expected"]
              and not dec["skip_line_but_lab_order"] and not dec["silent_fridays"])
    res.update({"lab": {k: info[k] for k in ("bars", "orders", "trades", "R_sum")}, "dec": dec, "skip_set": ss, "trades": trd,
                "coverage": cov})
    res["pass"] = bool(dec_ok and ss["pass"] and trd["pass"] and all(v > 0 for v in cov.values()) and res["s0_contract"]["pass"])
    log(f"[holes] {res['world']['cuts']} cuts, {res['world']['bars_removed']} bars removed | orders lab {dec['lab_orders']} EA "
        f"{dec['ea_orders']} matched {dec['matched']} wrong {dec['n_wrong']} only lab {len(dec['only_lab'])} only EA "
        f"{len(dec['only_ea'])} ({len(ss['no_bar_in_window'])} never active, {len(ss['hole_days'])} hole days) | trades lab "
        f"{trd['lab_trades']} EA {trd['ea_trades']} matched {trd['matched']} differences {len(trd['differences'])} unexplained "
        f"{trd['unexplained']} | coverage {cov} | {'PASS' if res['pass'] else 'FAIL'}")
    if sanitize:
        hs = holes_run(True, fresh)
        res["sanitizer"] = {"build_warnings": hs["warnings"], "wall_s": hs["wall"], "journal_identical": hs["identical"]}
        res["pass"] = bool(res["pass"] and hs["identical"] and not hs["warnings"])
        log(f"[holes] sanitizer: journal identical {hs['identical']} ({hs['wall']} s)")
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-sanitize", action="store_true")
    ap.add_argument("--fresh", action="store_true", help="replay again even when a cached replay matches")
    a = ap.parse_args(argv)
    t0 = time.time()
    res = {"test": "T4/T5 GFP GOLD_FRI_PM (step G)"}
    ok = True
    # the lab
    reb_info, reb_o, reb_t = ref_lab_one("GFP", "rebuilt")
    off_info, off_o, off_t = ref_lab_one("GFP", "official")
    lab = {k: lab_run("GFP", k) for k in ("rebuilt", "kept")}
    same_ref = (len(lab["rebuilt"][1]["trades"]) == len(reb_t) and (lab["rebuilt"][1]["trades"].reset_index(drop=True)
                                                                     .equals(reb_t.reset_index(drop=True))))
    res["lab"] = {"ref_lab_rebuilt": {k: reb_info[k] for k in ("orders", "trades", "R_sum", "reasons")},
                  "ref_lab_official": {k: off_info[k] for k in ("orders", "trades", "R_sum")},
                  "kept_frame": {k: lab["kept"][0][k] for k in ("bars", "first_bar", "orders", "trades", "R_sum")},
                  "kept_dropped": json.load(open(os.path.join(OUT, "frames", "kept_dropped.json"))),
                  "lab_run_rebuilt_equals_ref_lab": bool(same_ref),
                  "depth_120d_atr": lab["kept"][0]["depth_120d"]}
    ok &= same_ref and lab["kept"][0]["depth_120d"]["max_rel_diff"] <= REL
    # SPEC v2.1 change X1: export_frames.py drops the gold bars the EA's mask drops, so the rebuilt frame is the kept frame;
    # before, 20 bars of 2012-12-31 17:00-17:58 New York seeded the lab's hour ATR and three January 2013 stops differed
    res["lab"]["rebuilt_frame_is_kept_frame"] = bool(res["lab"]["kept_dropped"]["dropped"] == 0
                                                     and lab["kept"][0]["bars"] == len(read_frame(frame_path("rebuilt"))))
    ok &= res["lab"]["rebuilt_frame_is_kept_frame"]
    log(f"depth: the hour ATR at 13:30 from the last 120 days only vs the whole frame (lab code, kept frame): "
        f"{lab['kept'][0]['depth_120d']}")
    log(f"rebuilt frame = kept frame (the mask drops no bar of the export, SPEC v2.1 X1): {res['lab']['rebuilt_frame_is_kept_frame']}")
    log(f"lab: rebuilt {reb_info['orders']} orders {reb_info['trades']} trades | kept frame {lab['kept'][0]['orders']} orders "
        f"{lab['kept'][0]['trades']} trades ({res['lab']['kept_dropped']['dropped']} bars dropped) | official {off_info['trades']} "
        f"trades | lab_run = ref_lab on the rebuilt frame: {same_ref}")
    # the EA
    ea = ea_run(sanitize=not a.no_sanitize, fresh=a.fresh)
    rows = ea["rows"]
    res["tree"] = tree()["origin"]
    res["amalgam"] = tree()["amalgam"]
    res["replay"] = {"stdout": ea["out"], "wall_s": ea["wall"], "build_warnings": ea["warnings"]}
    res["s0_contract"] = s0_contract(rows)
    res["builds"] = build_variants()
    ok &= not ea["warnings"] and res["s0_contract"]["pass"] and res["builds"]["pass"]
    log(f"EA: replay {ea['wall']} s, warnings {len(ea['warnings'])} | release/debug {res['builds']['pass']} | "
        f"S0 contract {res['s0_contract']}")
    t_first, last = first_minute(rows), manifest_last()["XAUUSD.r"]
    t_last = last - 1
    kept_idx = secs(read_frame(frame_path("kept")).index)
    reb_idx = secs(read_frame(frame_path("rebuilt")).index)
    out = {}
    for kind, idx, lo, lt in (("kept", kept_idx, lab["kept"][1]["orders"], lab["kept"][1]["trades"]),
                              ("rebuilt", reb_idx, reb_o, reb_t)):
        fri = lab[kind][1]["fridays"].copy()
        lo_days = set(str(utc(t).tz_convert(NY).date()) for t in tsecs(lo.entry_t))
        fri["lab_order"] = [d in lo_days for d in fri.date]
        dec = gfp_decisions(rows, lo, fri, idx, t_first, kind)
        ss = skip_set(dec, fri, t_first)
        holes = set(ss["hole_days"])
        cause = None
        if kind == "rebuilt":
            kept_tr = out["kept"]["trades"]["all_rows"]

            def cause(r, kept_tr=kept_tr):
                k = [x for x in kept_tr if x["entry_time"] == r["entry_time"] and x["side"] == r["side"]]
                if k and not k[0]["bad"]:
                    return ("the EA's mask drops 20 gold bars of 2012-12-31 17:00-17:58 New York (SPEC 2.2, XAU rule): the "
                            "Wilder ATR seed differs, so the stop differs; against the kept frame this trade is equal")
                return None
            dec_wrong_cause = []
            for w in dec["wrong"]:
                k = [x for x in out["kept"]["dec"]["wrong"] if x["day"] == w["day"]]
                if not k and w["fields"] == ["stop_dist"]:
                    w["cause"] = "the mask of 2012-12-31 (Wilder seed): equal against the kept frame"
                else:
                    dec_wrong_cause.append(w)
        trd = gfp_trades(rows, lt, t_first, t_last, holes, kind, cause)
        if kind == "kept":
            dec_ok = (dec["n_wrong"] == 0 and not dec["only_lab"] and dec["duplicates"] == 0
                      and not [c for c in dec["only_ea"] if c["class"].startswith("unexplained")]
                      and not any(dec["own_fields_wrong"].values()) and not dec["fields_not_as_expected"]
                      and not dec["skip_line_but_lab_order"] and not dec["silent_fridays"])
        else:
            dec_ok = (not dec_wrong_cause and not dec["only_lab"] and dec["duplicates"] == 0
                      and not [c for c in dec["only_ea"] if c["class"].startswith("unexplained")]
                      and not dec["skip_line_but_lab_order"] and not dec["silent_fridays"])
        out[kind] = {"dec": dec, "skip_set": ss, "trades": trd, "pass": bool(dec_ok and ss["pass"] and trd["pass"])}
        ok &= out[kind]["pass"]
        log(f"[{kind}] orders lab {dec['lab_orders']} EA {dec['ea_orders']} matched {dec['matched']} wrong {dec['n_wrong']} "
            f"only lab {len(dec['only_lab'])} only EA {[(c['day'], c['class'][:22]) for c in dec['only_ea']]} | stop_dist bit-equal "
            f"{dec['stop_dist_bit_equal']} max rel {dec['stop_dist_max_rel_diff']:.3g} | skip lines {dec['skip_lines_by_code']} | "
            f"Fridays {dec['fridays_in_replay']} silent {len(dec['silent_fridays'])}")
        log(f"[{kind}] skip set: lab skipped {ss['lab_skipped_fridays']} EA calendar {ss['ea_calendar_skips']} hole days "
            f"{ss['hole_days']} no bar in window {ss['no_bar_in_window']} | equal minus holes {ss['calendar_equals_lab_minus_hole_days']}")
        log(f"[{kind}] trades lab {trd['lab_trades']} EA {trd['ea_trades']} matched {trd['matched']} entry/stop/exit bit-equal "
            f"{trd['entry_bit_equal']}/{trd['stop_bit_equal']}/{trd['exit_bit_equal']} max rel stop {trd['stop_max_rel_diff']:.3g} | "
            f"differences {len(trd['differences'])} unexplained {trd['unexplained']} | cmp_trades pass {trd['compare_cmp_trades']['pass']} "
            f"| {'PASS' if out[kind]['pass'] else 'FAIL'}")
        for d in trd["differences"]:
            log(f"      {d['entry_time']} {d['in']} {d['bad']} -> {d.get('cause', 'NO CAUSE')[:90]}")
        for w in dec["wrong"]:
            log(f"      order {w['day']} {w['fields']} rel {w['stop_dist_rel_diff']:.3g} -> {w.get('cause', 'NO CAUSE')[:80]}")
    for k in out:
        out[k]["trades"].pop("all_rows", None)
    res["kept"] = out["kept"]
    res["rebuilt"] = out["rebuilt"]
    od = official_diff("GFP", reb_t)
    lv_off = {str(utc(t).tz_convert(NY).date()): float(v) for t, v in zip(tsecs(off_o.entry_t), off_o.level)}
    lv_reb = {str(utc(t).tz_convert(NY).date()): float(v) for t, v in zip(tsecs(reb_o.entry_t), reb_o.level)}
    for r in od["differences"]:
        day = str(pd.Timestamp(r["entry_time"]).tz_convert(NY).date())
        r.setdefault("cause", f"the export rounds the bid to 2 digits (SPEC 7): the buy limit level (the last bid before 13:30) is "
                              f"{lv_off.get(day)} on the official frame and {lv_reb.get(day)} on the rebuilt one, so the fill bar moves")
    res["rebuilt_vs_official"] = od
    log(f"rebuilt vs official: official {od['official']} rebuilt {od['rebuilt']} same exit+reason {od['same_exit_and_reason']} "
        f"only official {od['only_official']} only rebuilt {od['only_rebuilt']} max |R| diff {od['max_abs_R_diff']:.3g}")
    res["holes"] = gfp_holes(not a.no_sanitize, a.fresh)
    ok &= res["holes"]["pass"]
    res["unit"] = gfp_unit()
    ok &= res["unit"]["pass"]
    u = res["unit"]
    log(f"unit: calendar {u['calendar_2012_2035']['fridays']} Fridays {u['calendar_2012_2035']['codes']} pass "
        f"{u['calendar_2012_2035']['pass']} | typed {u['typed_closures']['pass']} | sessions {u['sessions']['pass']} | "
        f"LatestExit {u['latest_exit']['queries']} pass {u['latest_exit']['pass']} | init guards {u['init_guards']['pass']} | "
        f"bar worlds {[(k, v['pass']) for k, v in u['bar_worlds'].items()]}")
    if not a.no_sanitize:
        s = ea["san"]
        res["sanitizer"] = {"build_warnings": s["warnings"], "stdout": s["out"], "wall_s": s["wall"], "journal_identical": s["identical"]}
        ue, uw = unit_exe(True)
        same_unit = unit(["cal", "", ny_utc("2012-01-06", "13:30"), ny_utc("2035-12-28", "13:30")], sanitize=True) == \
            unit(["cal", "", ny_utc("2012-01-06", "13:30"), ny_utc("2035-12-28", "13:30")])
        res["sanitizer"]["unit_build_warnings"] = uw
        res["sanitizer"]["unit_calendar_identical"] = same_unit
        ok &= s["identical"] and not s["warnings"] and not uw and same_unit
        log(f"sanitizer: warnings {len(s['warnings'])} journal identical {s['identical']} ({s['wall']} s) | unit build warnings "
            f"{len(uw)} calendar identical {same_unit}")
    res["journal_counts"] = counts(rows, "GFP")
    res["pass"] = bool(ok)
    res["sec"] = round(time.time() - t0, 1)
    write("test_GFP.json", res)
    log(f"test_GFP: {'PASS' if ok else 'FAIL'} ({res['sec']} s) -> {os.path.relpath(os.path.join(OUT, 'test_GFP.json'), ROBOT)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
