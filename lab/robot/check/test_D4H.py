"""T4 gold trend D4H (step H): donch4h_stop, every decision and every trade of 2013-2021 against the lab.

    python3 -I lab/robot/check/test_D4H.py [--world all|is|holes|restarts|unit] [--no-sanitize] [--fresh] [--verbose]

SPEC 7 T4/T5 for src/CR_Rule_Donch.mqh (CRuleDonch), and SPEC 8's "Wilder ATR within 1e-12 after warm-up".
The EA is built from a private tree under build/test_D4H/ (SPEC 8: the S0, A, B, C and I files as they are in src/,
this step's CR_Rule_Donch.mqh, and the S0 stubs of the files of the steps running beside H (D, E, F, G, J) and of K's
generated file, read from commit STUB_COMMIT with git show). It is compiled as check/build.py compiles a harness EA
(to_cpp.py, the same g++ flags, CR_HARNESS, CR_XAU_COMM_PTS=0), against a private copy of the mock whose
mock_faults.h is S0's neutral stub (J owns that file). It replays the exported bars of the four symbols through the S0
driver with InpTrade false (no order is sent), with the real clock (A), bars (B), paper (C) and account (I).
The lab: check/ref_lab.py's references on the frame rebuilt from the same gold bars (make_orders, every signal, and
r2.run, the official call, each in a fresh process), and the lab's own functions for the per-bar quantities (gl.bars,
gl.atr, pandas rolling max and min, gl.entry_index, and trend/strategy.py's add_trading_days, exit_index and
_first_touch), which give ref_lab.py's orders back exactly (checked).
Worlds:
  is        the in-sample bars of 2013-2021 (T4/T5); also replayed under the sanitizer build.
  holes     the same gold frame with windows of bars removed (hole_cuts): time exits that fall in a hole (the paper's
            late revision, PREVISE) or end exactly at x + 30 min, holes at the start of the activation bucket and over
            a whole bucket, the touch bar taken out, holes right after a fill, two 6-trading-day holes that trigger the
            lab's own validity test (HOLE_RULE: the lab drops an order whose exit bar does not follow its fill bar,
            strategy.py:277), and 200 random holes. The references: ref_lab.py on the frame with the same holes.
  restarts  the in-sample bars replayed in one process per segment (MOCK_FROM / MOCK_TO): restarts inside open trades,
            inside an armed OCO window, and at random minutes. Each start rebuilds the rule from the depth of SPEC 2.2
            (120 days of gold), so the ATR is warmed up from there. Compared on the lines the live passes wrote.
  unit      a generated C++ program with the tree's rule file: LatestExit against the lab's exit of every in-sample
            trade (with the comment: equal; without it: the largest lab exit of every decision consistent with the
            open), hand cases, and three bar worlds for the first bucket after Init (starting on a boundary, cut by the
            load, opened after a known closure) against the lab's functions on the same bars.
Checks in each replay world:
  1. Decisions: one DEC line per 4h bar whose channel and ATR are finite and that has a next bar (the lab's set before
     its touch test, strategy.py:266-267), none else. Each has up, dn, x and the activation bar equal to the lab's, 2 ATR
     within 1e-12 relative (counted bit for bit too), and an expiry at the end of the activation bar's bucket (its last
     bar is the lab's i1).
  2. Every DEC whose OCO is touched in its window and whose exit bar follows the touch bar is a lab order (entry bar,
     side, level, stop_dist, trail, exit bar, touch bar, decision equal); the others are "no touch" or HOLE_RULE
     (classified, never silent). Every PFILL is on the lab's touch bar, on the lab's side.
  3. Paper trades: the journal's (compare.paper_trades) against r2.run's on the same frame (compare.cmp_trades: entry
     and exit minute, side, reason equal; prices within 1e-12 relative, also counted bit for bit); trades open at the
     frame end are left out. In the holes world the trades near a HOLE_RULE case are listed apart, up to the first
     trade from which both chains agree again.
  4. The journal parses, has no ERROR and no SEND line; the builds have no warning; the sanitizer journal is
     byte-identical (world is).
Also (lab side only): the 4h bars of the rebuilt frame equal those of the kept bars (the frame without the 20 gold bars
the EA's mask drops on 2012-12-31), the Wilder ATR of the lab warmed up on 120 days only against its full-history value
at every decision of 2013-2021 (the replay depth of SPEC 2.2), and the lab on the rebuilt frame against the official
trades (results/r2/recalc/trades), each difference listed with its cause.
Outputs: check/out/test_D4H/ (journals, D4H_<world>_result.json, holes_world.json). In sample only: every frame and
trade file is read with the 2022-01-01 cut inside the read call.
"""
import argparse
import hashlib
import importlib.util
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
from build import CXX, SAN, BuildError, replay, translate  # noqa: E402

OUT = os.path.join(HERE, "out", "test_D4H")
WORK = os.path.join(ROBOT, "build", "test_D4H")
CUT = pd.Timestamp("2022-01-01", tz="UTC")
NY = "America/New_York"
STUB_COMMIT = "7b87227"                 # the end of part 1: the files of D-H, J and K are still S0's stubs there
SYMS = ("XAUUSD.r", "US100.r", "BTCUSD.r", "ETHUSD.r")
# SPEC 8: the files H's tests may include as they are (S0, A, B, C, I, H) ...
FINISHED = ("ClaudeRobot.mq5", "CR_Types.mqh", "CR_Registry.mqh", "CR_Journal.mqh", "CR_Main.mqh", "CR_Rule_Script.mqh",
            "CR_Clock.mqh", "CR_Math.mqh", "CR_Bars.mqh", "CR_Paper.mqh", "CR_Ledger.mqh", "CR_Sizing.mqh",
            "CR_Rule_Donch.mqh")
# ... and the S0 stubs of everything else (steps D, E, F, G, J running beside H, and K's generated file)
STUBS = ("CR_Rule_IdxUS.mqh", "CR_Rule_Brk72.mqh", "CR_Rule_F1.mqh", "CR_F1Model.mqh", "CR_Rule_NqBtc.mqh",
         "CR_Rule_GoldFri.mqh", "CR_Rule_Orb.mqh", "CR_Broker.mqh", "CR_Follower.mqh", "CR_Guards.mqh", "CR_Golden.mqh")
CODE, SID = "D4H", 9
REL = 1e-12                             # SPEC 7: Wilder values and the stops built on them
TF = 14400                              # the 4h UTC grid
N_CH, ATR_N, K_STOP = 60, 14, 2.0       # strategy.py:427-429
HOLES_TAG = "d4hholes"
SEED = 20261113
DEPTH_DAYS = 120                        # SPEC 2.2: the gold history a rebuild replays


def log(msg):
    print(msg, flush=True)


def secs(ts):
    return pd.DatetimeIndex(ts).tz_convert("UTC").as_unit("s").asi8.astype(np.int64)


def utc(t):
    return pd.Timestamp(int(t), unit="s", tz="UTC")


def ny_str(t):
    return str(utc(t).tz_convert(NY))[:16]


def write(name, res):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w") as f:
        json.dump(res, f, indent=1, default=str)


# ======================================================================================== the EA
def git_stub(path):
    """a file as it was at STUB_COMMIT (S0's stub), read with git show (read only)"""
    r = subprocess.run(["git", "-C", ROBOT, "show", f"{STUB_COMMIT}:./{path}"], capture_output=True)
    if r.returncode:
        raise RuntimeError(f"git show {STUB_COMMIT}:{path} failed: {r.stderr.decode()[-500:]}")
    if b"S0 STUB" not in r.stdout:
        raise RuntimeError(f"{path} at {STUB_COMMIT} is not an S0 stub")
    return r.stdout


def make_tree():
    """the private source tree of the build (under build/, git-ignored); returns its src directory"""
    d = os.path.join(WORK, "tree", "src")
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(d)
    src = os.path.join(ROBOT, "src")
    names = sorted(n for n in os.listdir(src) if n.endswith((".mqh", ".mq5")))
    missing = set(FINISHED + STUBS) - set(names)
    extra = set(names) - set(FINISHED + STUBS)
    if missing or extra:
        raise RuntimeError(f"src/ lacks {sorted(missing)} or has unknown files {sorted(extra)}")
    for n in names:
        if n in STUBS:
            with open(os.path.join(d, n), "wb") as f:
                f.write(git_stub(f"src/{n}"))
        else:
            shutil.copy(os.path.join(src, n), os.path.join(d, n))
    return d


def harness_dir():
    """a private copy of the mock and the shim, with S0's neutral mock_faults.h"""
    h = os.path.join(WORK, "harness")
    os.makedirs(h, exist_ok=True)
    for n in ("mock_replay.h", "mql5_shim.h"):
        shutil.copy(os.path.join(HERE, n), os.path.join(h, n))
    with open(os.path.join(h, "mock_faults.h"), "wb") as f:
        f.write(git_stub("check/mock_faults.h"))
    return h


def tree_stamp(tree, extra=b""):
    h = hashlib.sha256(extra)
    for n in sorted(os.listdir(tree)):
        h.update(n.encode())
        h.update(open(os.path.join(tree, n), "rb").read())
    for n in ("to_cpp.py", "mql5_shim.h", "mock_replay.h", "build.py"):
        h.update(open(os.path.join(HERE, n), "rb").read())
    return h.hexdigest()


_TREE = {}


def tree():
    if not _TREE:
        _TREE["src"] = make_tree()
        _TREE["harness"] = harness_dir()
    return _TREE


def compile_cpp(run_cpp, exe, sanitize, incdirs, defines):
    cmd = CXX + (SAN if sanitize else []) + [f"-D{d}" for d in defines]
    for i in incdirs:
        cmd += ["-I", i]
    cmd += [run_cpp, "-o", exe]
    r = subprocess.run(cmd, capture_output=True, text=True)
    warn = [ln for ln in r.stderr.splitlines() if "warning:" in ln]
    if r.returncode:
        raise BuildError(f"compile failed ({exe}):\n" + r.stderr[-20000:])
    return warn, " ".join(cmd)


def ea_exe(sanitize=False):
    """the replay binary of the tree (rebuilt when the sources or flags change): (exe, warnings, stamp)"""
    t = tree()
    defines = ["CR_HARNESS", "CR_XAU_COMM_PTS=0"]
    stamp = tree_stamp(t["src"], repr((defines, sanitize)).encode() + git_stub("check/mock_faults.h"))
    work = os.path.join(WORK, "ea_san" if sanitize else "ea")
    sp = os.path.join(work, "stamp.json")
    if os.path.exists(sp):
        old = json.load(open(sp))
        if old.get("stamp") == stamp and os.path.exists(old.get("exe", "")):
            return old["exe"], old["warnings"], stamp
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)
    ea = os.path.join(work, "ea.cpp")
    translate(os.path.join(t["src"], "ClaudeRobot.mq5"), ea)
    run = os.path.join(work, "run.cpp")
    with open(run, "w") as f:
        f.write(f'#include "{os.path.join(t["harness"], "mock_replay.h")}"\n#include "{ea}"\n')
    exe = os.path.join(work, "replay")
    warn, cmd = compile_cpp(run, exe, sanitize, [t["harness"], work, t["src"]], defines)
    with open(sp, "w") as f:
        json.dump({"stamp": stamp, "exe": exe, "warnings": warn, "cmd": cmd}, f)
    return exe, warn, stamp


def bar_stamp(bars):
    h = hashlib.sha256()
    for s in sorted(bars):
        st = os.stat(bars[s])
        h.update(f"{s}:{st.st_size}:{int(st.st_mtime)}".encode())
    return h.hexdigest()


def run_ea(world, sanitize=False, fresh=False):
    """replay the world's bars (one process, or one per segment when the world has restarts): {files, replay, wall_s,
    warnings, cached, processes}"""
    exe, warn, est = ea_exe(sanitize)
    bars = world["bars"]
    files = os.path.join(OUT, f"{world['name']}_ea" + ("_san" if sanitize else ""))
    stamp = hashlib.sha256((est + bar_stamp(bars) + repr(world.get("restarts_srv", []))).encode()).hexdigest()
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
           "wall_s": round(wall, 1), "warnings": warn, "sanitize": sanitize, "world": world["name"], "processes": len(outs),
           "cached": False}
    with open(sp, "w") as f:
        json.dump(res, f, indent=1)
    return res


# ======================================================================================== inputs and the lab
def tool(args):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", NUMBA_CACHE_DIR=_NB)
    r = subprocess.run([sys.executable, "-I"] + args, env=env, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"{os.path.basename(args[0])} failed ({r.returncode}): {(r.stdout + r.stderr)[-3000:]}")
    return r.stdout


def ref_dir(tag):
    return os.path.join(HERE, "out", "ref", f"rebuilt_{tag}")


def refs_ready(tag):
    return all(os.path.exists(os.path.join(ref_dir(tag), CODE, f)) for f in ("orders.parquet", "trades.parquet"))


def world_is():
    """the in-sample world: the bar exports of tag 'is' (S0's export_frames.py), the rebuilt gold frame and ref_lab.py's
    D4H references on it (made when missing)"""
    bars = {s: os.path.join(HERE, "out", "bars", f"{s}_is.bin") for s in SYMS}
    man = os.path.join(HERE, "out", "manifest_is.json")
    if not all(os.path.exists(p) for p in bars.values()) or not os.path.exists(man):
        tool([os.path.join(HERE, "export_frames.py"), "--tag", "is"])
    if not refs_ready("is"):
        tool([os.path.join(HERE, "ref_lab.py"), "--frame", "rebuilt", "--tag", "is", "--sleeves", CODE, "--no-changes"])
    return {"name": "is", "tag": "is", "bars": bars, "ref": ref_dir("is"),
            "frame": os.path.join(HERE, "out", "frames", "xauusd_is.parquet")}


def read_frame(path):
    m1 = pd.read_parquet(path, filters=[("ts", "<", CUT)])
    assert len(m1) and m1.index.max() < CUT and m1.index.is_monotonic_increasing and m1.index.is_unique
    return m1


def lab_refs(world):
    o = pd.read_parquet(os.path.join(world["ref"], CODE, "orders.parquet"))
    t = pd.read_parquet(os.path.join(world["ref"], CODE, "trades.parquet"), filters=[("entry_time", "<", CUT)])
    return o.reset_index(drop=True), t[t.entry_time < CUT].reset_index(drop=True)


_LAB = {}


def lab():
    """goldlab and the trend strategy module (loaded under the name recalc.py gives it: the numba cache keys on it)"""
    if not _LAB:
        if LAB not in sys.path:
            sys.path.insert(0, LAB)
        import goldlab as gl
        spec = importlib.util.spec_from_file_location("strategy_trend", os.path.join(LAB, "tracks", "trend", "strategy.py"))
        T = importlib.util.module_from_spec(spec)
        sys.modules["strategy_trend"] = T
        spec.loader.exec_module(T)
        _LAB["gl"], _LAB["T"] = gl, T
    return _LAB["gl"], _LAB["T"]


def lab_grid(m1):
    """every 4h bar of the frame with the lab's own quantities (strategy.py:257-288, re-derived with its functions):
    channel, ATR, t_close, the window [i0, i1], the first touch, the time exit and its exit bar; keep0 = the lab's
    decision set before its touch test, keep = its orders, hole_rule = touched orders the lab drops (xi <= hit_i)"""
    gl, T = lab()
    b = gl.bars(m1, "4h")
    a = gl.atr(b, ATR_N).to_numpy()
    up = b["h"].rolling(N_CH).max().to_numpy()
    dn = b["l"].rolling(N_CH).min().to_numpy()
    tc = pd.DatetimeIndex(b["t_close"])
    n = len(m1)
    i0 = gl.entry_index(m1, tc)
    i1 = np.r_[gl.entry_index(m1, tc[1:]), n] - 1
    keep0 = np.isfinite(up) & np.isfinite(dn) & np.isfinite(a) & (i0 < n) & (i1 >= i0)
    i0c = np.clip(i0, 0, n - 1).astype(np.int64)
    hit_i, hit_s = T._first_touch(m1["ah"].to_numpy(), m1["bl"].to_numpy(), m1["bo"].to_numpy(), m1["bc"].to_numpy(), i0c,
                                  i1.astype(np.int64), np.nan_to_num(up, nan=np.inf), np.nan_to_num(dn, nan=-np.inf))
    xt = T.add_trading_days(tc, 5) - pd.Timedelta(minutes=5)
    xi = T.exit_index(m1, xt)
    touched = keep0 & (hit_i >= 0)
    return {"b": b, "a": a, "up": up, "dn": dn, "tc": secs(tc), "i0": i0c, "i1": i1.astype(np.int64), "keep0": keep0,
            "hit_i": hit_i, "hit_s": hit_s, "xt": secs(xt), "xi": xi, "keep": touched & (xi > hit_i),
            "hole_rule": touched & ~(xi > hit_i), "idx": secs(m1.index), "n": n, "h": b["h"].to_numpy(), "l": b["l"].to_numpy(),
            "c": b["c"].to_numpy(), "key": secs(b.index)}


def grid_vs_ref(g, lab_o):
    """the grid's orders against ref_lab.py's (the lab's make_orders): field by field, bit for bit"""
    k = np.where(g["keep"])[0]
    side = g["hit_s"][k]
    mine = pd.DataFrame({"entry_i": g["i0"][k], "side": side, "level": np.where(side > 0, g["up"][k], g["dn"][k]),
                         "expiry_i": g["i1"][k], "stop_dist": g["a"][k] * K_STOP, "exit_i": g["xi"][k], "trail": g["a"][k] * K_STOP,
                         "trig_i": g["hit_i"][k], "dec": g["tc"][k]})
    ref = lab_o.copy()
    ref["dec"] = secs(ref.dec_time)
    ok = len(mine) == len(ref)
    bad = {}
    if ok:
        for c in ("entry_i", "side", "level", "expiry_i", "stop_dist", "exit_i", "trail", "trig_i", "dec"):
            bad[c] = int((mine[c].to_numpy() != ref[c].to_numpy()).sum())
        ok = all(v == 0 for v in bad.values())
    return {"grid_orders": int(len(mine)), "ref_lab_orders": int(len(ref)), "fields_differing": bad, "pass": bool(ok)}


# ======================================================================================== decisions
OWN = {"et": 3, "side": 0, "xg": 1, "vle": 0, "ref": 0, "ax": 0, "grp": 0, "xh": 0}
ZERO = ("st", "be", "tg", "td", "xr")


def dec_frame(rows):
    d = [r for r in rows if r["ev"] == "DEC" and r["code"] == CODE and r.get("what") == "ord"]
    df = pd.DataFrame(d)
    if len(df):
        df["dec"] = df["utc"].astype(np.int64)
    return df


def check_decisions(rows, g, lab_o, t_first, t_last, allow_dup=False):
    """checks 1 and 2: the DEC lines against the lab grid, then the resolved orders against ref_lab.py's orders. With
    allow_dup (restarts: a decision journaled live and again by the next start's replay) every line is checked and the
    lines of one oid must agree field by field"""
    idx = g["idx"]
    ea = dec_frame(rows)
    res = {"dec_lines": int(len(ea))}
    if not len(ea):
        res["pass"] = False
        return res, None
    dupm = ea.oid.duplicated(keep=False)
    res["duplicate_oids"] = int(ea.oid.duplicated().sum())
    cols = ["lv", "lv2", "sd", "tr", "x", "tf", "tt", "exp", "side", "et", "xg", "dec"]
    res["duplicates_that_disagree"] = int(ea[dupm].groupby("oid")[cols].nunique().gt(1).any(axis=1).sum()) if dupm.any() else 0
    ea = ea.drop_duplicates("oid", keep="last").reset_index(drop=True)    # (duplicates agree: checking one is enough)
    pos = pd.Series(np.arange(len(g["tc"])), index=g["tc"])
    k_all = np.where(g["keep0"])[0]
    act_all = idx[g["i0"][k_all]]
    in_win = (act_all >= t_first) & (act_all <= t_last)
    want = set(g["tc"][k_all[in_win]].tolist())
    got = set(ea.dec.tolist())
    res["lab_decisions"] = len(want)
    res["n_missing"] = len(want - got)
    res["missing"] = [ny_str(t) for t in sorted(want - got)[:10]]
    res["n_extra"] = len(got - want)                           # not a lab decision (or outside the compared minutes)
    res["extra"] = [ny_str(t) for t in sorted(got - want)[:10]]
    known = ea.dec.isin(pos.index)
    res["n_unknown_decision_time"] = int((~known).sum())
    ea = ea[known].copy()
    k = pos.loc[ea.dec.to_numpy()].to_numpy()
    ea["k"] = k
    ea["status"] = np.where(g["keep"][k], "order", np.where(g["hole_rule"][k], "hole_rule", "no_touch"))
    a2 = g["a"][k] * K_STOP
    sd = ea.sd.to_numpy(np.float64)
    rel = np.abs(sd - a2) / np.abs(a2)
    exp = ea.tf.to_numpy(np.int64) - ea.tf.to_numpy(np.int64) % TF + TF
    last_in_window = idx[np.searchsorted(idx, exp, "left") - 1]
    checks = {
        "oid = t_close x 100 + 9": int((ea.oid != ea.dec * 100 + SID).sum()),
        "level = up (bit for bit)": int((ea.lv.to_numpy(np.float64) != g["up"][k]).sum()),
        "level2 = dn (bit for bit)": int((ea.lv2.to_numpy(np.float64) != g["dn"][k]).sum()),
        "x = AddTradingDays(t_close, 5) - 5 min": int((ea.x.to_numpy(np.int64) != g["xt"][k]).sum()),
        "activation bar = the first bar at or after t_close": int((ea.tf.to_numpy(np.int64) != idx[g["i0"][k]]).sum()),
        "window = one bar (t_from = t_to = at)": int(((ea["tf"] != ea["tt"]) | (ea["at"] != ea["tf"])).sum()),
        "expiry = end of the activation bar's 4h bucket": int((ea.exp.to_numpy(np.int64) != exp).sum()),
        "last bar before expiry = the lab's i1": int((last_in_window != idx[g["i1"][k]]).sum()),
        "trail = stop_dist": int((ea.tr.to_numpy(np.float64) != sd).sum()),
        "stop_dist within 1e-12 of 2 ATR": int((rel > REL).sum()),
    }
    for c, v in OWN.items():
        checks[f"{c} = {v}"] = int((ea[c] != v).sum())
    for c in ZERO:
        checks[f"{c} = 0"] = int((ea[c].astype(float) != 0.0).sum())
    res["field_checks_failed"] = {c: v for c, v in checks.items() if v}
    res["field_checks"] = len(checks)
    res["atr"] = {"decisions": int(len(ea)), "bit_for_bit": int((sd == a2).sum()), "max_rel_diff": float(rel.max()) if len(rel) else 0.0,
                  "over_1e-12": int((rel > REL).sum())}
    res["status"] = {s: int(v) for s, v in ea.status.value_counts().items()}
    # 2. the resolved orders against ref_lab.py's orders
    lo = lab_o.copy()
    lo["dec"] = secs(lo.dec_time)
    lo["act"] = secs(lo.entry_t)
    lo = lo[(lo.act >= t_first) & (lo.act <= t_last)]
    eo = ea[ea.status == "order"]
    m = lo.merge(eo, on="dec", how="outer", suffixes=("_lab", "_ea"), indicator=True)
    both = m[m._merge == "both"]
    lvl = np.where(both.side_lab.to_numpy() > 0, both.lv.to_numpy(np.float64), both.lv2.to_numpy(np.float64))
    xbar = idx[g["xi"][both.k.to_numpy(np.int64)]]
    ocheck = {"entry bar": int((both.act.to_numpy() != both.tf.to_numpy(np.int64)).sum()),
              "side (the lab's first touch)": int((both.side_lab.to_numpy() != g["hit_s"][both.k.to_numpy(np.int64)]).sum()),
              "level": int((both.level.to_numpy(np.float64) != lvl).sum()),
              "stop_dist (bit for bit)": int((both.stop_dist.to_numpy(np.float64) != both.sd.to_numpy(np.float64)).sum()),
              "trail (bit for bit)": int((both.trail.to_numpy(np.float64) != both.tr.to_numpy(np.float64)).sum()),
              "exit bar": int((secs(both.exit_t) != xbar).sum()),
              "touch bar": int((both.trig_i.to_numpy() != g["hit_i"][both.k.to_numpy(np.int64)]).sum()),
              "expiry bar": int((both.expiry_i.to_numpy() != g["i1"][both.k.to_numpy(np.int64)]).sum())}
    res["orders"] = {"lab_orders": int(len(lo)), "ea_orders": int(len(eo)), "matched": int(len(both)),
                     "only_lab": int((m._merge == "left_only").sum()), "only_ea": int((m._merge == "right_only").sum()),
                     "field_checks_failed": {c: v for c, v in ocheck.items() if v},
                     "examples_only_lab": [ny_str(t) for t in m[m._merge == "left_only"].dec.head(8)],
                     "examples_only_ea": [ny_str(t) for t in m[m._merge == "right_only"].dec.head(8)]}
    hr = ea[ea.status == "hole_rule"]
    res["hole_rule"] = [{"decision": ny_str(r.dec), "activation": ny_str(r.tf), "touch": ny_str(idx[g["hit_i"][r.k]]),
                         "x": ny_str(r.x), "lab_exit_bar": ny_str(idx[g["xi"][r.k]]) if g["xi"][r.k] >= 0 else None,
                         "why": "the lab's exit bar (gap rule) does not follow its touch bar (strategy.py:277): the lab drops the order"}
                        for r in hr.itertuples()]
    # every PFILL on the lab's touch bar and side
    pf = [r for r in rows if r["ev"] == "PFILL" and r["code"] == CODE]
    bad_fill = 0
    status_of = dict(zip(ea.oid.tolist(), ea.status.tolist()))
    k_of = dict(zip(ea.oid.tolist(), ea.k.tolist()))
    for r in pf:
        kk = k_of.get(r["oid"])
        if kk is None or status_of.get(r["oid"]) == "no_touch" or r["bar"] != idx[g["hit_i"][kk]] or r["side"] != g["hit_s"][kk]:
            bad_fill += 1
    res["pfill"] = {"lines": len(pf), "not_on_the_lab_touch_bar_or_side": bad_fill}
    ok = ((allow_dup or res["duplicate_oids"] == 0) and res["duplicates_that_disagree"] == 0 and res["n_missing"] == 0
          and res["n_extra"] == 0 and res["n_unknown_decision_time"] == 0 and not res["field_checks_failed"]
          and res["orders"]["only_lab"] == 0 and res["orders"]["only_ea"] == 0 and not res["orders"]["field_checks_failed"]
          and bad_fill == 0)
    res["pass"] = bool(ok)
    return res, ea


# ======================================================================================== trades
def drop_oids(rows, oids):
    oids = set(oids)
    return [r for r in rows if not (r["code"] == CODE and r["ev"] in ("PFILL", "PEXIT", "PREVISE", "PVOID") and r.get("oid") in oids)]


def disturbance_windows(rows, lab_t, ea_dec, g):
    """around each HOLE_RULE case that the paper traded: [its activation bar, R), R = the entry of the first trade (after
    the paper's exit of that trade) from which both chains have the same trades to the end of a 30-day look"""
    ea_t = compare.paper_trades(rows, CODE)
    if not len(ea_t) or ea_dec is None:
        return []
    key = lambda t: (int(t.entry_time.value // 10**9), int(t.side), int(t.exit_time.value // 10**9), str(t.reason))
    lab_set = {key(t) for t in lab_t.itertuples()}
    ea_set = {key(t) for t in ea_t.itertuples()}
    wins = []
    for r in ea_dec[ea_dec.status == "hole_rule"].itertuples():
        tr = ea_t[ea_t.oid == r.oid]
        if not len(tr):
            continue                                            # the paper was busy: no trade, nothing disturbed
        w0, x_end = int(r.tf), int(tr.exit_time.iloc[0].value // 10**9)
        later = sorted(k for k in lab_set | ea_set if k[0] >= x_end)
        R = None
        for j, kk in enumerate(later):
            span = [z for z in later[j:] if z[0] < kk[0] + 30 * 86400]
            if all(z in lab_set and z in ea_set for z in span):
                R = kk[0]
                break
        wins.append((w0, R if R is not None else 2**62))
    return wins


def check_trades(rows, lab_t, t_from, t_to, windows=()):
    """check 3 with compare.cmp_trades; trades whose entry lies in a disturbance window are listed apart"""
    apart = {"lab": [], "ea": []}
    if windows:
        ea_t = compare.paper_trades(rows, CODE)
        inw = lambda t: any(a <= t < b for a, b in windows)
        drop = [int(o) for o, t in zip(ea_t.oid, secs(ea_t.entry_time)) if inw(int(t))]
        apart["ea"] = [{"entry": str(t.entry_time), "side": int(t.side), "exit": str(t.exit_time), "reason": t.reason}
                       for t in ea_t.itertuples() if inw(int(t.entry_time.value // 10**9))]
        keep_lab = np.array([not inw(int(t)) for t in secs(lab_t.entry_time)], bool)
        apart["lab"] = [{"entry": str(t.entry_time), "side": int(t.side), "exit": str(t.exit_time), "reason": t.reason}
                        for t in lab_t[~keep_lab].itertuples()]
        rows = drop_oids(rows, drop)
        lab_t = lab_t[keep_lab]
    tr = compare.cmp_trades(rows, lab_t, CODE, t_from=t_from, t_to=t_to, rel=REL)
    ea_t = compare.paper_trades(rows, CODE)
    tr["ea_trades_total"] = int(len(ea_t))
    tr["lab_trades_total"] = int(len(lab_t))
    if len(ea_t):
        tr["reasons_ea"] = {k: int(v) for k, v in ea_t.reason.value_counts().items()}
        tr["revised_ea"] = int(ea_t.revised.sum())
    tr["reasons_lab"] = {k: int(v) for k, v in lab_t.reason.value_counts().items()}
    open_end = lab_t[lab_t.exit_time > utc(t_to)] if t_to is not None else lab_t.iloc[:0]
    tr["lab_trades_open_at_the_frame_end"] = [{"entry": str(t.entry_time), "lab_exit": str(t.exit_time), "reason": t.reason,
                                               "why": "its x lies after the frame end: exit_index puts the lab's exit on the "
                                                      "frame's last bar; the paper has no end-of-data exit (SPEC 2.5, 7)"}
                                              for t in open_end.itertuples()]
    tr["prices_bit_for_bit"] = bool(tr.get("entry_equal") == tr.get("stop_equal") == tr.get("exit_equal") == tr.get("lab_trades"))
    tr["listed_apart_near_hole_rule"] = apart
    tr["pass"] = bool(tr["pass"] and tr.get("lab_trades", 0) > 0 and tr.get("same_exit_and_reason") == tr.get("lab_trades"))
    return tr


# ======================================================================================== the holes world
def hole_cuts(m1, g, lab_o, lab_t, seed=SEED):
    """windows [a, b) (UTC seconds) of gold bars to remove, aimed at the paths the in-sample data barely reaches"""
    rng = np.random.default_rng(seed)
    idx = g["idx"]
    pos = pd.Series(np.arange(len(g["tc"])), index=g["tc"])
    cuts = []
    last = int(idx[-1])
    o = lab_o.copy()
    o["dec"] = secs(o.dec_time)
    o["k"] = pos.loc[o.dec.to_numpy()].to_numpy()
    t = lab_t.copy()
    t["dec"] = secs(t.dec_time)
    t["k"] = pos.loc[t.dec.to_numpy()].to_numpy()
    t["fill"] = secs(t.entry_time)
    # the lab's time exits (away from the frame end): no bar in [x, x + 30 min] -> exit on the last bar before x
    # (PREVISE); the bar at x + 30 min kept -> it takes the exit (the edge of the gap rule); a hole from 15 min before x
    tx = t[(t.reason == "time") & (secs(t.exit_time) < last - 86400)]
    for j, r in enumerate(tx.itertuples()):
        x = int(g["xt"][r.k])
        v = j % 4
        cuts.append((x, x + 31 * 60, "time_exit_in_hole") if v < 2 else
                    (x, x + 30 * 60, "time_exit_at_x+30") if v == 2 else (x - 15 * 60, x + 40 * 60, "time_exit_hole_before_x"))
    special = []
    # HOLE_RULE (b): a lab trade's fill bar, then no bar until after x + 30 min: its exit bar is its fill bar
    cand = t[(t.fill > int(pd.Timestamp("2016-03-01", tz="UTC").value // 10**9)) & (t.reason != "time")]
    r = cand.iloc[0]
    a, b = int(r.fill) + 60, int(g["xt"][r.k]) + 2 * 3600
    cuts.append((a, b, "hole_rule_after_fill"))
    special.append((a, b))
    # HOLE_RULE (a): no bar from a t_close to after its x + 30 min, and one of the first bars after the hole touching a
    # level of that decision; no lab trade open at t_close (so the paper is flat when the order activates)
    es, xs = secs(t.entry_time), secs(t.exit_time)
    ah, bl = m1["ah"].to_numpy(), m1["bl"].to_numpy()
    lo_t = int(pd.Timestamp("2018-06-01", tz="UTC").value // 10**9)
    for kk in np.where(g["keep0"])[0]:
        tc = int(g["tc"][kk])
        if tc < lo_t or ((es <= tc) & (xs > tc)).any():
            continue
        x = int(g["xt"][kk])
        j = int(np.searchsorted(idx, x + 2 * 3600, "left"))
        if j >= g["n"]:
            break
        jj = min(j + 30, g["n"])
        if (ah[j:jj] >= g["up"][kk]).any() or (bl[j:jj] <= g["dn"][kk]).any():
            cuts.append((tc, x + 2 * 3600, "hole_rule_after_t_close"))
            special.append((tc, x + 2 * 3600))
            break
    near_special = lambda s: any(a - 15 * 86400 <= s < b + 15 * 86400 for a, b in special)
    # the activation bucket starts later: its first 20 minutes cut
    for r in o.sample(n=14, random_state=seed).itertuples():
        a = int(secs([r.entry_t])[0])
        if not near_special(a):
            cuts.append((a, a + 20 * 60, "activation_bucket_start"))
    # the whole activation bucket removed: the window moves to the next bucket
    for r in o.sample(n=8, random_state=seed + 1).itertuples():
        a = int(secs([r.entry_t])[0])
        if not near_special(a):
            cuts.append((a - a % TF, a - a % TF + TF, "activation_bucket_removed"))
    # the touch bar removed
    for r in o.sample(n=14, random_state=seed + 2).itertuples():
        a = int(idx[r.trig_i])
        if not near_special(a):
            cuts.append((a, a + 60, "touch_bar_removed"))
    # a 45-minute hole right after a fill: the next bar may gap through the stop
    for r in t.sample(n=14, random_state=seed + 3).itertuples():
        a = int(r.fill) + 60
        if not near_special(a):
            cuts.append((a, a + 45 * 60, "hole_after_fill"))
    targeted = list(cuts)
    for _ in range(200):
        s = int(idx[int(rng.integers(len(idx) // 50, len(idx) - 1))])
        if near_special(s) or any(a - 86400 <= s < b + 86400 for a, b, _k in targeted):
            continue
        cuts.append((s, s + 60 * int(rng.integers(5, 241)), "random"))
    return sorted(cuts)


def holes_world(fresh=False):
    """the in-sample gold frame with hole_cuts removed: a gold bar file for the EA (the other symbols keep their bars)
    and ref_lab.py's references on the same frame (tag d4hholes)"""
    base = world_is()
    import export_frames as ef
    fpath = os.path.join(HERE, "out", "frames", f"xauusd_{HOLES_TAG}.parquet")
    bpath = os.path.join(HERE, "out", "bars", f"XAUUSD.r_{HOLES_TAG}.bin")
    spec = os.path.join(OUT, "holes_world.json")
    m1 = read_frame(base["frame"])
    g = lab_grid(m1)
    lab_o, lab_t = lab_refs(base)
    cuts = hole_cuts(m1, g, lab_o, lab_t)
    key = hashlib.sha256((repr(cuts) + repr((len(m1), int(m1.index[0].value), int(m1.index[-1].value)))).encode()).hexdigest()
    done = (os.path.exists(spec) and json.load(open(spec)).get("key") == key and os.path.exists(fpath) and os.path.exists(bpath)
            and refs_ready(HOLES_TAG))
    if fresh or not done:
        ts = g["idx"]
        drop = np.zeros(len(ts), bool)
        kinds = {}
        for a, b, kind in cuts:
            i, j = np.searchsorted(ts, a, "left"), np.searchsorted(ts, b, "left")
            kinds[kind] = kinds.get(kind, 0) + int((~drop[i:j]).sum())
            drop[i:j] = True
        mh = m1[~drop]
        tsec = ef.server_secs(mh.index)
        pts, spread = ef.to_points(mh)
        os.makedirs(os.path.dirname(bpath), exist_ok=True)
        ef.write_bin(bpath, tsec, pts, spread)
        _, rec = ef.read_bin(bpath)
        fr = ef.rebuild(rec)
        assert (fr.index == mh.index.as_unit(fr.index.unit)).all(), "server -> UTC round trip"
        for c in mh.columns:
            assert (fr[c].to_numpy() == mh[c].to_numpy()).all(), f"the bar file does not give the frame back ({c})"
        mh.to_parquet(fpath)
        tool([os.path.join(HERE, "ref_lab.py"), "--frame", "rebuilt", "--tag", HOLES_TAG, "--sleeves", CODE, "--no-changes"])
        os.makedirs(OUT, exist_ok=True)
        with open(spec, "w") as f:
            json.dump({"key": key, "seed": SEED, "bars_in": int(len(m1)), "bars_removed": int(drop.sum()), "removed_by_kind": kinds,
                       "cuts": [[a, b, k, ny_str(a), ny_str(b)] for a, b, k in cuts]}, f, indent=1)
    info = json.load(open(spec))
    bars = dict(base["bars"])
    bars["XAUUSD.r"] = bpath
    kinds = {}
    for _a, _b, k in cuts:
        kinds[k] = kinds.get(k, 0) + 1
    return {"name": "holes", "tag": HOLES_TAG, "bars": bars, "ref": ref_dir(HOLES_TAG), "frame": fpath, "cuts": len(cuts),
            "cuts_by_kind": kinds, "bars_removed": info["bars_removed"], "removed_by_kind": info["removed_by_kind"]}


def holes_coverage(rows, ea_dec, g, lab_t):
    """the paths the holes world must reach (a count of 0 fails it)"""
    idx = g["idx"]
    prv = sum(1 for r in rows if r["ev"] == "PREVISE" and r["code"] == CODE)
    st = ea_dec.status.value_counts().to_dict() if ea_dec is not None else {}
    lt = lab_t[lab_t.reason == "time"]
    pos = pd.Series(np.arange(len(g["tc"])), index=g["tc"])
    kx = pos.loc[secs(lt.dec_time)].to_numpy()
    at30 = int((secs(lt.exit_time) - g["xt"][kx] == 1800).sum())
    before_x = int((secs(lt.exit_time) < g["xt"][kx]).sum())
    gap_stop = 0
    for r in lab_t[lab_t.reason.isin(["stop", "trail"])].itertuples():
        i = int(np.searchsorted(idx, int(r.exit_time.value // 10**9) - 60, "left"))
        if i > 0 and idx[i] - idx[i - 1] > 1800:
            gap_stop += 1
    late_act = int((ea_dec.tf.to_numpy(np.int64) - ea_dec.dec.to_numpy(np.int64) > TF).sum()) if ea_dec is not None else 0
    return {"PREVISE": prv, "lab_time_exits_before_x": before_x, "lab_time_exits_at_x+30": at30,
            "hole_rule_decisions": int(st.get("hole_rule", 0)), "stop_or_trail_exits_after_a_30_min_hole": gap_stop,
            "activations_more_than_4h_after_t_close": late_act}


# ======================================================================================== the restarts world
def restart_points(g, lab_o, lab_t, seed=SEED):
    """restart times (UTC seconds): inside open lab trades, inside an armed OCO window before its touch, and at random
    minutes. None lies within 6 minutes before or 3 after an activation, touch, fill or exit bar, so every one of those
    is journaled by a live pass (a start replays the minutes just before its first live barrier with rp=1)."""
    rng = np.random.default_rng(seed + 7)
    idx = g["idx"]
    ev = np.r_[idx[g["i0"][g["keep0"]]], idx[lab_o.trig_i.to_numpy()], secs(lab_t.entry_time), secs(lab_t.exit_time),
               secs(lab_t.exit_time) - 60]
    busy = set()
    for t in ev:
        m = int(t) // 60
        for d in range(-3, 7):
            busy.add(m + d)

    def free(t):
        return int(t) // 60 not in busy

    def first_free(t, tries=600):
        t = int(t) - int(t) % 60
        for k in range(tries):
            if free(t + 60 * k):
                return t + 60 * k
        return None

    pts = []
    t = lab_t.reset_index(drop=True)
    es, xs = secs(t.entry_time), secs(t.exit_time)
    for k in rng.permutation(len(t))[:9]:                       # inside open trades
        p = first_free(es[k] + (xs[k] - es[k]) // 2)
        if p is not None and p < xs[k] - 600:
            pts.append(p)
    o = lab_o.reset_index(drop=True)
    act, trig = secs(o.entry_t), idx[o.trig_i.to_numpy()]
    long_wait = np.where(trig - act >= 3600)[0]
    for k in rng.permutation(long_wait)[:5]:                    # an armed OCO window, before its touch
        p = first_free(act[k] + (trig[k] - act[k]) // 2)
        if p is not None and p < trig[k] - 600:
            pts.append(p)
    lo = int(idx[0]) + 130 * 86400
    for _ in range(6):                                          # random minutes
        p = first_free(int(idx[int(rng.integers(np.searchsorted(idx, lo), len(idx) - 1))]))
        if p is not None:
            pts.append(p)
    return sorted({int(p) for p in pts if idx[0] + DEPTH_DAYS * 86400 < p < idx[-1] - 86400})


def to_server(t):
    return int((utc(t).tz_convert(NY).tz_localize(None) + pd.Timedelta(hours=7)).value // 10**9)


def restarts_world():
    base = world_is()
    m1 = read_frame(base["frame"])
    g = lab_grid(m1)
    lab_o, lab_t = lab_refs(base)
    pts = restart_points(g, lab_o, lab_t)
    w = dict(base)
    w["name"] = "restarts"
    w["restarts_utc"] = pts
    w["restarts_srv"] = [to_server(p) for p in pts]
    return w


def live_rows(rows, restarts_utc=()):
    """the journal of a run with restarts as the live passes wrote it. Lines with rp=1 (a start's replay of the history)
    are dropped, except:
      - the replay lines of the first start (no live pass fed those bars), and the replay lines a later start wrote for
        bars of the last day before its restart time: the previous process stops at its last event, so the bars after it
        (at a weekend, the reopening bar too) are first fed by the next start's replay. They duplicate live lines when a
        live pass had fed the bar; duplicates must agree (check_decisions), and compare.paper_chain keeps the last;
      - for a trade filled during a replay and exited live, the latest replayed PFILL before that exit.
    A start's replay lines come after the REBUILD lines of the starts before it."""
    out, last_rp_fill, live_fill = [], {}, set()
    k = 0
    for r in rows:
        if r["ev"] == "REBUILD":
            k += 1
        key = (r["code"], r.get("oid"))
        if r.get("rp") == 1:
            t = r.get("at") if r["ev"] == "DEC" else r.get("bar")
            near = k == 0 or (k <= len(restarts_utc) and t is not None and t >= restarts_utc[k - 1] - 86400)
            if not near:
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


def restart_atr(ea_dec, g, pts):
    """the ATR of the first decisions after each start (warmed up on the 120 days the start replayed)"""
    rel_all, first = [], []
    for p in pts:
        d = ea_dec[ea_dec.tf > p].sort_values("tf").head(6)
        if not len(d):
            continue
        a2 = g["a"][d.k.to_numpy(np.int64)] * K_STOP
        r = np.abs(d.sd.to_numpy(np.float64) - a2) / a2
        rel_all.extend(r.tolist())
        first.append(float(r[0]))
    return {"starts": len(first), "decisions_checked": len(rel_all), "max_rel_diff": max(rel_all) if rel_all else None,
            "bit_for_bit": int(sum(1 for x in rel_all if x == 0.0)), "first_decision_rel_diff_max": max(first) if first else None}


# ======================================================================================== lab-side checks
def kept_frame_bars(m1):
    """the EA's kept bars are the rebuilt frame without the 20 gold bars of 2012-12-31 17:00-17:58 NY (SPEC 2.2, B1): the
    lab's 4h bars of both frames"""
    gl, _ = lab()
    ny = m1.index.tz_convert(NY)
    mask = ny.hour == 17
    b1, b2 = gl.bars(m1, "4h"), gl.bars(m1[~mask], "4h")
    same = len(b1) == len(b2) and (b1.index == b2.index).all()
    if same:
        for c in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac", "h", "l", "c", "t_close"):
            same &= bool((b1[c] == b2[c]).all())
    return {"masked_bars": int(mask.sum()), "first": str(m1.index[mask][0]) if mask.any() else None,
            "last": str(m1.index[mask][-1]) if mask.any() else None, "four_hour_bars": int(len(b1)),
            "four_hour_bars_identical": bool(same)}


def lab_warmup(m1, g, step_days=15):
    """the lab's own Wilder ATR (gl.atr on gl.bars) warmed up on the last 120 days only, at every 4h bar of the first 10
    days after each start (one start every step_days days), against its value on the whole frame (relative)"""
    gl, _ = lab()
    idx = g["idx"]
    full = pd.Series(g["a"], index=g["tc"])
    t0 = int(idx[0]) + DEPTH_DAYS * 86400
    rels, starts = [], 0
    for s in range(t0, int(idx[-1]) - 11 * 86400, step_days * 86400):
        cut = m1[m1.index >= utc(s - DEPTH_DAYS * 86400)]
        b = gl.bars(cut, "4h")
        a = gl.atr(b, ATR_N)
        tc = secs(b.t_close)
        sel = (tc > s) & (tc <= s + 10 * 86400)
        if not sel.any():
            continue
        ref = full.loc[tc[sel]].to_numpy()
        rels.extend((np.abs(a.to_numpy()[sel] - ref) / ref).tolist())
        starts += 1
    r = np.array(rels)
    return {"starts": starts, "values": int(len(r)), "max_rel_diff": float(r.max()), "bit_for_bit": int((r == 0).sum()),
            "over_1e-12": int((r > REL).sum())}


def razors(m1, lab_o, lab_t, rel=1e-9):
    """SPEC 7 razors: the lab's stop and trail comparisons that come within 1e-9 (relative) of flipping. Every bar of every
    lab trade from its fill bar to its exit bar, as sim.py:136-204 walks it: the bar's bid low (long) or ask high (short)
    against the stop in force, then best and the trail move for the next bar. The touch of the OCO compares bar prices
    with extremes of bar prices (no computed value), so it has no razor."""
    idx = secs(m1.index)
    bl, bh, al, ah = (m1[c].to_numpy() for c in ("bl", "bh", "al", "ah"))
    trail_of = dict(zip(secs(lab_o.dec_time).tolist(), lab_o.trail.to_numpy().tolist()))
    out, n, dmin = [], 0, np.inf
    for t in lab_t.itertuples():
        e = int(t.entry_time.value // 10**9)
        x = int(t.exit_time.value // 10**9) - (0 if t.reason == "time" else 60)
        fi, xe = int(np.searchsorted(idx, e)), int(np.searchsorted(idx, x))
        cur, best, tr, s = float(t.stop), float(t.entry), trail_of[int(t.dec_time.value // 10**9)], int(t.side)
        for i in range(fi, xe if t.reason == "time" else xe + 1):
            d = (bl[i] - cur) / cur if s > 0 else (cur - ah[i]) / cur
            n += 1
            if abs(d) < dmin:
                dmin = abs(d)
            if abs(d) <= rel:
                out.append({"trade": str(t.entry_time), "bar": str(m1.index[i]), "rel_distance": float(d)})
            if s > 0:
                if bl[i] <= cur:
                    break
                best = max(best, bh[i])
                if best - tr > cur:
                    cur = best - tr
            else:
                if ah[i] >= cur:
                    break
                best = min(best, al[i])
                if best + tr < cur:
                    cur = best + tr
    return {"trades": int(len(lab_t)), "bars_checked": n, "razors_within_1e-9": len(out), "list": out[:20],
            "smallest_rel_distance": float(dmin)}


def official_diff(lab_t):
    """the lab on the rebuilt frame (the broker export: bid on 2 digits, spread in whole points) against the official
    trades (results/r2/recalc/trades, entries before 2022), which the lab's code gives on the unrounded official frame
    (S0's ref_lab.py check, read back from check/out/ref/official/summary.json when it is there). Lab against lab: the
    EA is compared with the rebuilt frame only."""
    off = pd.read_parquet(os.path.join(LAB, "results", "r2", "recalc", "trades", "donch4h_stop__xauusd.parquet"),
                          filters=[("entry_time", "<", CUT)])
    m = off.merge(lab_t, on=["entry_time", "side"], how="outer", suffixes=("_off", "_reb"), indicator="src")
    both = m[m["src"] == "both"]
    same_t = (both.exit_time_off == both.exit_time_reb) & (both.reason_off == both.reason_reb)
    same_p = same_t.copy()
    for c in ("entry", "exit", "stop"):
        same_p &= both[f"{c}_off"] == both[f"{c}_reb"]
    dp = {c: float((both[same_t][f"{c}_off"] - both[same_t][f"{c}_reb"]).abs().max()) for c in ("entry", "exit", "stop")}
    rows = []
    for r in m[m["src"] != "both"].itertuples():
        rows.append({"entry": str(r.entry_time), "side": int(r.side), "in": "official only" if r.src == "left_only" else "rebuilt only",
                     "why": "the 2-digit export moves the channel or the touch by a few cents, so the lab fills another minute"})
    for r in both[~same_t].itertuples():
        why = ("its official exit is in 2022, outside the in-sample frame; on the frame the lab exits at the frame end"
               if r.exit_time_off >= CUT else "the 2-digit export moves the stop or the touch")
        rows.append({"entry": str(r.entry_time), "official_exit": str(r.exit_time_off), "rebuilt_exit": str(r.exit_time_reb),
                     "official_reason": r.reason_off, "rebuilt_reason": r.reason_reb, "why": why})
    s0 = None
    sp = os.path.join(HERE, "out", "ref", "official", "summary.json")
    if os.path.exists(sp):
        for r in json.load(open(sp)).get("results", []):
            if r.get("code") == CODE and "official" in r:
                s0 = {k: (len(v) if isinstance(v, list) else v) for k, v in r["official"].items()}
    return {"official_trades_before_2022": int(len(off)), "rebuilt_lab_trades": int(len(lab_t)),
            "same_times_side_reason": int(same_t.sum()), "same_prices_too": int(same_p.sum()),
            "max_abs_price_diff_usd_on_same_times": dp, "structural_differences": rows,
            "lab_on_the_official_frame_vs_official (S0 ref_lab.py)": s0}


# ======================================================================================== the unit program (generated C++)
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
   g_sl[0].id = 9; g_sl[0].code = "D4H"; g_sl[0].lab = "donch4h_stop_xauusd"; g_sl[0].sym = CR_XAU; g_sl[0].sym2 = -1;
   g_sl[0].kind = CR_K_D4H; g_sl[0].magic = 20261209;
   g_sl[1].id = 9; g_sl[1].code = "D4X"; g_sl[1].lab = "-"; g_sl[1].sym = CR_BTC; g_sl[1].sym2 = -1; g_sl[1].kind = CR_K_D4H;
   g_sl[1].magic = 20261209;
   g_sym[CR_XAU].base = "XAUUSD";
   g_sym[CR_XAU].name = "XAUUSD.r";
  }
static void put_out(const std::string &w, const CrOut &o)
  {
   for(int i = 0; i < o.n_ord; i++)
      printf("W %s ORD %lld %d %d %.17g %.17g %lld %lld %lld %.17g %.17g %lld %d %lld\n", w.c_str(), (long long)o.ord[i].oid,
             o.ord[i].side, o.ord[i].etype, o.ord[i].level, o.ord[i].level2, (long long)o.ord[i].t_from, (long long)o.ord[i].t_to,
             (long long)o.ord[i].expiry_excl, o.ord[i].stop_dist, o.ord[i].trail, (long long)o.ord[i].x_sched, (int)o.ord[i].x_gap,
             (long long)o.ord[i].dec);
  }
// bar worlds: lines "world t bo bh bl bc ao ah al ac", time order per world; each world gets a fresh rule (Init) and the
// driver's minute contract: for every minute M the bars starting before M (OnBar), then OnMinute(M)
static int run_worlds(const char *path)
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
      CRuleDonch r;
      if(!r.Init(0)) { printf("W %s INITFAIL\n", w.c_str()); i = j; continue; }
      datetime M0 = bars[i].t - bars[i].t % 60 + 60, M1 = bars[j - 1].t + 120;
      size_t k = i;
      for(datetime M = M0; M <= M1; M += 60)
        {
         CrOut out;
         while(k < j && bars[k].t < M)
           {
            CrOutClear(out);
            r.OnBar(CR_XAU, bars[k], out);
            put_out(w, out);
            k++;
           }
         CrOutClear(out);
         r.OnMinute(M, out);
         put_out(w, out);
        }
      i = j;
     }
   return 0;
  }
int main(int argc, char **argv)
  {
   unit_tables();
   string err = "";
   if(!ClkInit("", err)) { printf("CLKERR %s\n", err.c_str()); return 3; }
   if(argc < 2) return 2;
   std::string cmd = argv[1];
   if(cmd == "worlds" && argc >= 3) return run_worlds(argv[2]);
   if(cmd == "latest")                                // lines "open_time comment_dec" on stdin
     {
      CRuleDonch r;
      r.Init(0);
      long long o, c;
      while(std::cin >> o >> c) printf("LATEST %lld %lld %lld\n", o, c, (long long)r.LatestExit((datetime)o, (datetime)c));
      return 0;
     }
   if(cmd == "exit")                                  // lines "t_close" on stdin: DonchExitTime
     {
      long long t;
      while(std::cin >> t) printf("EXIT %lld %lld\n", t, (long long)DonchExitTime((datetime)t));
      return 0;
     }
   if(cmd == "whole")                                 // lines "t key" on stdin: DonchWhole
     {
      long long t, k;
      while(std::cin >> t >> k) printf("WHOLE %lld %lld %d\n", t, k, (int)DonchWhole((datetime)t, (datetime)k));
      return 0;
     }
   if(cmd == "init")                                  // the symbol guard
     {
      CRuleDonch a, b;
      printf("INIT XAU %d\nINIT BTC %d\n", (int)a.Init(0), (int)b.Init(1));
      return 0;
     }
   return 2;
  }
"""

_UNIT = {}


def unit_exe(sanitize=False):
    """the unit program: the tree's rule file (and what it includes), the mock without its main, then UNIT_MAIN"""
    key = "san" if sanitize else "plain"
    if key in _UNIT:
        return _UNIT[key]
    t = tree()
    work = os.path.join(WORK, "unit" + ("_san" if sanitize else ""))
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)
    shutil.copytree(t["src"], os.path.join(work, "src"))
    entry = os.path.join(work, "src", "_unit_H.mqh")
    with open(entry, "w") as f:
        f.write('#include "CR_Rule_Donch.mqh"\n')
    translate(entry, os.path.join(work, "ea.cpp"))
    run = os.path.join(work, "run.cpp")
    with open(run, "w") as f:
        f.write("#define MOCK_REPLAY_NO_MAIN\n")
        f.write(f'#include "{os.path.join(t["harness"], "mock_replay.h")}"\n#include "{os.path.join(work, "ea.cpp")}"\n')
        f.write(UNIT_MAIN)
    exe = os.path.join(work, "unit")
    warn, _ = compile_cpp(run, exe, sanitize, [t["harness"], work], ["CR_HARNESS", "CR_XAU_COMM_PTS=0"])
    _UNIT[key] = (exe, warn)
    return exe, warn


def unit(args, stdin=None, sanitize=False):
    exe, _ = unit_exe(sanitize)
    r = subprocess.run([exe] + [str(a) for a in args], input=stdin, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"unit {args[0]} failed ({r.returncode}): {r.stdout[-1000:]} {r.stderr[-3000:]}")
    return r.stdout


def lab_exit(ts):
    """the lab's time exit of decisions at UTC seconds ts: trend.add_trading_days(t, 5) - 5 min"""
    _, T = lab()
    return secs(T.add_trading_days(pd.to_datetime(np.asarray(ts, np.int64), unit="s", utc=True), 5) - pd.Timedelta(minutes=5))


def max_consistent_exit(o_list):
    """for each open time o: the largest lab exit over every whole-minute decision in [B - 4 days, B], B = o floored to the
    4h UTC grid (the decisions consistent with a D4H position opened at o)"""
    out = []
    for o in o_list:
        B = int(o) - int(o) % TF
        c = np.arange(B - 4 * 86400, B + 60, 60, dtype=np.int64)
        out.append(int(lab_exit(c).max()))
    return np.array(out, np.int64)


def unit_latest(g, lab_t, rng):
    """LatestExit: with the comment, the lab's exit of every in-sample trade; without it, the largest consistent exit
    (never earlier than the lab's); hand cases"""
    pos = pd.Series(np.arange(len(g["tc"])), index=g["tc"])
    dec = secs(lab_t.dec_time)
    k = pos.loc[dec].to_numpy()
    xt = g["xt"][k]
    fill = secs(lab_t.entry_time)
    cases = []
    for lag in (60, 300):
        for o, d, x in zip(fill + lag, dec, xt):
            cases.append(("comment", int(o), int(d), int(x)))
            cases.append(("no_comment", int(o), 0, int(x)))
    # hand cases (2019 summer, 2020 winter): a Sunday-evening open (B on a server Sunday), comments out of the window
    sun_s = int(pd.Timestamp("2019-07-14 22:31", tz="UTC").value // 10**9)
    sun_w = int(pd.Timestamp("2020-01-12 23:12", tz="UTC").value // 10**9)
    mon = int(pd.Timestamp("2019-07-15 09:17", tz="UTC").value // 10**9)
    hand = []
    for o in (sun_s, sun_w, mon):
        B = o - o % TF
        hand += [("hand_no_comment", o, 0), ("hand_comment_not_a_minute", o, B - 3600 + 30), ("hand_comment_after_B", o, B + 60),
                 ("hand_comment_4_days_before_B", o, B - 4 * 86400), ("hand_comment_4_days_1_min_before_B", o, B - 4 * 86400 - 60),
                 ("hand_comment_valid", o, B - 2 * 3600)]
    text = "".join(f"{o} {c}\n" for _, o, c, _ in cases) + "".join(f"{o} {c}\n" for _, o, c in hand)
    got = [int(ln.split()[3]) for ln in unit(["latest"], text).splitlines() if ln.startswith("LATEST")]
    gc, gh = got[:len(cases)], got[len(cases):]
    nc = [i for i, c in enumerate(cases) if c[0] == "no_comment"]
    sample = sorted(rng.choice(nc, size=min(240, len(nc)), replace=False).tolist())
    mx = max_consistent_exit([cases[i][1] for i in sample])
    res = {"trades": int(len(lab_t)), "lags_s": [60, 300],
           "comment_equals_lab_exit": int(sum(1 for c, v in zip(cases, gc) if c[0] == "comment" and v == c[3])),
           "comment_cases": int(sum(1 for c in cases if c[0] == "comment")),
           "no_comment_never_before_lab_exit": int(sum(1 for c, v in zip(cases, gc) if c[0] == "no_comment" and v >= c[3])),
           "no_comment_cases": len(nc),
           "no_comment_lateness_h_max": round(max((v - c[3]) / 3600 for c, v in zip(cases, gc) if c[0] == "no_comment"), 2),
           "no_comment_equals_max_consistent_exit": int(sum(1 for i, m in zip(sample, mx) if gc[i] == m)),
           "no_comment_max_checked": len(sample)}
    hres, hbad = [], 0
    for (name, o, c), v in zip(hand, gh):
        B = o - o % TF
        valid = c > 0 and c % 60 == 0 and c <= B and B - c <= 4 * 86400
        want = int(lab_exit([c])[0]) if valid else int(max_consistent_exit([o])[0])
        hbad += v != want
        hres.append({"case": name, "open": ny_str(o), "comment": ny_str(c) if c else 0, "got": ny_str(v), "want": ny_str(want),
                     "ok": v == want})
    res["hand"] = hres
    res["pass"] = (res["comment_equals_lab_exit"] == res["comment_cases"] and res["no_comment_never_before_lab_exit"] == len(nc)
                   and res["no_comment_equals_max_consistent_exit"] == len(sample) and hbad == 0)
    return res


def lab_decisions(m1):
    """the lab's decision set of a frame (keep0) as DEC fields, from lab_grid"""
    g = lab_grid(m1)
    k = np.where(g["keep0"])[0]
    tf = g["idx"][g["i0"][k]]
    return pd.DataFrame({"bucket": k, "dec": g["tc"][k], "lv": g["up"][k], "lv2": g["dn"][k], "sd": g["a"][k] * K_STOP,
                         "x": g["xt"][k], "tf": tf, "exp": tf - tf % TF + TF})


def unit_worlds(m1, sanitize=False):
    """three bar worlds for the first bucket after Init (DonchWhole), each a 25-day slice of the in-sample gold frame:
    starting on a 4h boundary, cut by the load inside an open bucket, and opened inside a bucket after the weekend
    closure; the rule's orders against the lab's functions on the same slice"""
    specs = {"boundary": ("2015-03-02 00:00", "whole"), "cut": ("2015-03-02 01:37", "cut"), "after_closure": ("2015-03-01 00:00", "whole")}
    worlds = {}
    for name, (start, _) in specs.items():
        s = pd.Timestamp(start, tz="UTC")
        worlds[name] = m1[(m1.index >= s) & (m1.index < s + pd.Timedelta(days=25))]
    path = os.path.join(WORK, "unit_worlds.txt")
    cols = ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac")
    with open(path, "w") as f:
        for name, w in worlds.items():
            t = secs(w.index)
            v = [w[c].to_numpy(np.float64).tolist() for c in cols]
            for i in range(len(w)):
                f.write(f"{name} {t[i]} " + " ".join(repr(v[j][i]) for j in range(8)) + "\n")
    text = unit(["worlds", path], sanitize=sanitize)
    got = {n: [] for n in worlds}
    for ln in text.splitlines():
        p = ln.split()
        if len(p) > 2 and p[0] == "W" and p[2] == "ORD":
            got[p[1]].append({"oid": int(p[3]), "side": int(p[4]), "et": int(p[5]), "lv": float(p[6]), "lv2": float(p[7]), "tf": int(p[8]),
                              "tt": int(p[9]), "exp": int(p[10]), "sd": float(p[11]), "tr": float(p[12]), "x": int(p[13]),
                              "xg": int(p[14]), "dec": int(p[15])})
    res, ok = {}, True
    for name, w in worlds.items():
        lab_d = lab_decisions(w)
        ea = pd.DataFrame(got[name])
        first_ok = specs[name][1] == "whole"
        want = lab_d if first_ok else lab_d[lab_d.bucket >= N_CH]   # the cut bucket 0 is left out: the channel needs 60 more
        m = want.merge(ea, on="dec", how="outer", suffixes=("_lab", "_ea"), indicator=True)
        both = m[m._merge == "both"]
        eq = {c: int((both[f"{c}_lab"] != both[f"{c}_ea"]).sum()) for c in ("lv", "lv2", "sd", "x", "tf", "exp")}
        r = {"first_bar": str(w.index[0]), "first_bucket": specs[name][1], "lab_decisions": int(len(lab_d)),
             "expected": int(len(want)), "ea_orders": int(len(ea)), "matched": int(len(both)),
             "only_lab": int((m._merge == "left_only").sum()), "only_ea": int((m._merge == "right_only").sum()),
             "fields_differing": {c: v for c, v in eq.items() if v}}
        if not first_ok:
            r["lab_decision_left_out"] = [ny_str(t) for t in lab_d[lab_d.bucket < N_CH].dec]
        r["pass"] = r["only_lab"] == 0 and r["only_ea"] == 0 and not r["fields_differing"] and r["matched"] > 20
        ok &= r["pass"]
        res[name] = r
    res["pass"] = bool(ok)
    return res


def unit_whole():
    """DonchWhole hand cases: on the boundary, inside an open bucket, a Sunday reopening (weekend closure), a first bar 7
    minutes after the reopening (open minutes without a bar before it: it may be cut, so it is left out), after the daily
    closure inside the bucket (open time before the closure: it may be cut), a reopening after Good Friday"""
    T = lambda s: int(pd.Timestamp(s, tz="UTC").value // 10**9)
    cases = [("boundary", T("2015-03-02 04:00"), 1), ("inside_open_bucket", T("2015-03-02 05:13"), 0),
             ("sunday_reopen_winter", T("2015-03-01 23:00"), 1), ("sunday_reopen_summer", T("2019-07-14 22:00"), 1),
             ("sunday_first_bar_7_min_after_the_reopening", T("2019-07-14 22:07"), 0),
             ("after_daily_closure", T("2019-07-15 22:00"), 0), ("good_friday_reopen", T("2019-04-21 22:00"), 1)]
    text = "".join(f"{t} {t - t % TF}\n" for _, t, _ in cases)
    got = [int(ln.split()[3]) for ln in unit(["whole"], text).splitlines() if ln.startswith("WHOLE")]
    rows = [{"case": n, "t": ny_str(t), "got": v, "want": w, "ok": v == w} for (n, t, w), v in zip(cases, got)]
    return {"cases": rows, "pass": all(r["ok"] for r in rows) and len(rows) == len(cases)}


def check_unit(fresh=False):
    t0 = time.time()
    base = world_is()
    m1 = read_frame(base["frame"])
    g = lab_grid(m1)
    _, lab_t = lab_refs(base)
    rng = np.random.default_rng(SEED + 3)
    exe, warn = unit_exe(False)
    exe_s, warn_s = unit_exe(True)
    res = {"world": "unit", "build_warnings": warn, "build_warnings_sanitizer": warn_s}
    init = unit(["init"])
    res["init"] = {"gold": "INIT XAU 1" in init, "btc_refused": "INIT BTC 0" in init}
    res["latest_exit"] = unit_latest(g, lab_t, rng)
    res["whole"] = unit_whole()
    res["worlds"] = unit_worlds(m1)
    san = unit_worlds(m1, sanitize=True)
    res["worlds_sanitizer_same"] = san == res["worlds"]
    res["pass"] = bool(not warn and not warn_s and res["init"]["gold"] and res["init"]["btc_refused"] and res["latest_exit"]["pass"]
                       and res["whole"]["pass"] and res["worlds"]["pass"] and res["worlds_sanitizer_same"])
    res["sec"] = round(time.time() - t0, 1)
    write("D4H_unit_result.json", res)
    return res


# ======================================================================================== one replay world
def check_world(world, sanitize=True, fresh=False):
    t0 = time.time()
    plain = run_ea(world, False, fresh)
    all_rows = compare.read_journal(plain["files"])
    evc = compare.check_parsable(plain["files"])["events"]
    rows = live_rows(all_rows, world["restarts_utc"]) if world["name"] == "restarts" else all_rows
    m1 = read_frame(world["frame"])
    g = lab_grid(m1)
    lab_o, lab_t = lab_refs(world)
    reb = compare.events(all_rows, "REBUILD").iloc[0]
    t_first = int(reb["from"]) + 60 if int(reb["from"]) > 0 else int(reb["to"]) + 60
    t_last = int(g["idx"][-1])
    res = {"code": CODE, "world": world["name"], "tree": f"finished files from src/, stubs from {STUB_COMMIT}",
           "replay": plain["replay"], "wall_s": plain["wall_s"], "cached_replay": plain.get("cached", False),
           "build_warnings": plain["warnings"], "events": evc, "first_minute_utc": t_first,
           "errors": [r for r in all_rows if r["ev"] == "ERROR"][:5], "gold_bars": int(g["n"]), "four_hour_bars": int(len(g["tc"]))}
    ok = not plain["warnings"] and not res["errors"] and "SEND" not in evc
    res["grid_vs_ref_lab"] = grid_vs_ref(g, lab_o)
    ok &= res["grid_vs_ref_lab"]["pass"]
    if world["name"] == "restarts":
        res["restarts"] = {"processes": plain.get("processes"), "rebuild_lines": int(evc.get("REBUILD", 0)),
                           "at_ny": [ny_str(t) for t in world["restarts_utc"]]}
        ok &= res["restarts"]["rebuild_lines"] == len(world["restarts_utc"]) + 1
    if world["name"] == "holes":
        res["holes"] = {k: world[k] for k in ("cuts", "cuts_by_kind", "bars_removed", "removed_by_kind")}
    # 1-2. decisions
    dres, ea_dec = check_decisions(rows, g, lab_o, t_first, t_last, allow_dup=world["name"] == "restarts")
    res["decisions"] = dres
    ok &= dres["pass"]
    # 3. trades
    wins = disturbance_windows(rows, lab_t, ea_dec, g) if world["name"] == "holes" else []
    res["hole_rule_windows"] = [[ny_str(a), ny_str(b) if b < 2**61 else "end"] for a, b in wins]
    tr = check_trades(rows, lab_t, t_first, t_last - 1, wins)
    res["trades"] = tr
    ok &= tr["pass"]
    if world["name"] == "holes":
        res["coverage"] = holes_coverage(rows, ea_dec, g, lab_t)
        res["coverage"]["hole_rule_trades_taken_by_the_paper"] = len(wins)
        ok &= all(v > 0 for v in res["coverage"].values())
    if world["name"] == "restarts":
        ea_t = compare.paper_trades(rows, CODE)
        es, xs = secs(ea_t.entry_time), secs(ea_t.exit_time)
        pts = world["restarts_utc"]
        acts = ea_dec.tf.to_numpy(np.int64) if ea_dec is not None else np.zeros(0, np.int64)
        lo = lab_o.copy()
        la, lt = secs(lo.entry_t), g["idx"][lo.trig_i.to_numpy()]
        res["coverage"] = {"restarts_inside_an_open_trade": sum(1 for p in pts if ((es < p) & (xs > p)).any()),
                           "restarts_inside_an_armed_oco_window": sum(1 for p in pts if ((la < p) & (lt > p)).any()),
                           "decisions_within_4h_after_a_restart": sum(1 for p in pts if ((acts > p) & (acts <= p + TF)).any())}
        ok &= all(v > 0 for v in res["coverage"].values())
        res["atr_after_restart"] = restart_atr(ea_dec, g, pts)
        ok &= res["atr_after_restart"]["max_rel_diff"] is not None and res["atr_after_restart"]["max_rel_diff"] <= REL
    if world["name"] == "is":
        res["kept_frame"] = kept_frame_bars(m1)
        ok &= res["kept_frame"]["four_hour_bars_identical"]
        res["lab_atr_warmed_up_on_120_days"] = lab_warmup(m1, g)
        ok &= res["lab_atr_warmed_up_on_120_days"]["over_1e-12"] == 0
        res["razors"] = razors(m1, lab_o, lab_t)
        res["rebuilt_vs_official"] = official_diff(lab_t)
    # 4. sanitizer
    if sanitize:
        san = run_ea(world, True, fresh)
        same = subprocess.run(["diff", "-r", "-q", os.path.join(plain["files"], "ClaudeRobot"), os.path.join(san["files"], "ClaudeRobot")],
                              capture_output=True, text=True)
        res["sanitizer"] = {"replay": san["replay"], "wall_s": san["wall_s"], "cached_replay": san.get("cached", False),
                            "build_warnings": san["warnings"], "journal_identical_to_plain_build": same.returncode == 0}
        ok &= same.returncode == 0 and not san["warnings"]
    res["pass"] = bool(ok)
    res["sec"] = round(time.time() - t0, 1)
    write(f"{CODE}_{world['name']}_result.json", res)
    return res


def report(res, verbose=False):
    if res["world"] == "unit":
        le = res["latest_exit"]
        log(f"D4H world unit: builds {len(res['build_warnings'])}/{len(res['build_warnings_sanitizer'])} warnings, Init {res['init']}")
        log(f"  LatestExit with the comment = lab exit {le['comment_equals_lab_exit']}/{le['comment_cases']}; without: never before "
            f"the lab exit {le['no_comment_never_before_lab_exit']}/{le['no_comment_cases']} (at most {le['no_comment_lateness_h_max']} h "
            f"later), = the largest consistent exit {le['no_comment_equals_max_consistent_exit']}/{le['no_comment_max_checked']}; "
            f"hand cases {sum(h['ok'] for h in le['hand'])}/{len(le['hand'])}")
        log(f"  DonchWhole hand cases {sum(c['ok'] for c in res['whole']['cases'])}/{len(res['whole']['cases'])}")
        for n, w in res["worlds"].items():
            if n != "pass":
                log(f"  world {n:13s} first bar {w['first_bar']} ({w['first_bucket']}): lab {w['lab_decisions']}, expected "
                    f"{w['expected']}, EA {w['ea_orders']}, matched {w['matched']}, only lab {w['only_lab']}, only EA {w['only_ea']}, "
                    f"fields differing {w['fields_differing']}" + (f", left out {w['lab_decision_left_out']}" if "lab_decision_left_out" in w else ""))
        log(f"  sanitizer worlds identical {res['worlds_sanitizer_same']}")
        log(f"D4H world unit: {'PASS' if res['pass'] else 'FAIL'} ({res['sec']} s)")
        return
    d, t = res["decisions"], res["trades"]
    log(f"D4H world {res['world']}: replay {res['wall_s']} s{' (cached)' if res['cached_replay'] else ''}, gold bars {res['gold_bars']}, "
        f"4h bars {res['four_hour_bars']}, events {dict((k, v) for k, v in res['events'].items() if k in ('DEC', 'PFILL', 'PEXIT', 'PREVISE', 'PSTOP', 'ERROR', 'REBUILD'))}")
    if "holes" in res:
        log(f"  holes: {res['holes']['cuts']} cuts {res['holes']['cuts_by_kind']}, {res['holes']['bars_removed']} bars removed")
    if "restarts" in res:
        r = res["restarts"]
        log(f"  restarts: {len(r['at_ny'])} ({r['processes']} processes, {r['rebuild_lines']} REBUILD lines)")
        if verbose:
            log(f"    at {r['at_ny']}")
    gv = res["grid_vs_ref_lab"]
    log(f"  lab grid = ref_lab.py orders: {gv['pass']} ({gv['grid_orders']} / {gv['ref_lab_orders']})")
    log(f"  DEC lines {d['dec_lines']} for {d.get('lab_decisions')} lab decisions: missing {d.get('n_missing')}, not a lab "
        f"decision {d.get('n_extra')}, unknown time {d.get('n_unknown_decision_time')}, duplicate lines {d.get('duplicate_oids')} "
        f"(disagreeing {d.get('duplicates_that_disagree')}), {d.get('field_checks')} field checks, failed {d.get('field_checks_failed')}")
    a = d.get("atr", {})
    log(f"  ATR (2 ATR = stop_dist) at {a.get('decisions')} decisions: bit for bit {a.get('bit_for_bit')}, max rel diff "
        f"{a.get('max_rel_diff')}, over 1e-12 {a.get('over_1e-12')}")
    o = d.get("orders", {})
    log(f"  status {d.get('status')}; orders: lab {o.get('lab_orders')}, EA {o.get('ea_orders')}, matched {o.get('matched')}, only lab "
        f"{o.get('only_lab')}, only EA {o.get('only_ea')}, failed {o.get('field_checks_failed')}; PFILL {d.get('pfill')}")
    if d.get("hole_rule"):
        for h in d["hole_rule"]:
            log(f"    HOLE_RULE {h}")
    if not d.get("pass"):
        log(f"  decision differences: missing {d.get('missing')} only lab {o.get('examples_only_lab')} only EA {o.get('examples_only_ea')}")
    log(f"  trades: lab {t.get('lab_trades')}, EA {t.get('ea_trades')}, same entry {t.get('same_entry')}, same exit+reason "
        f"{t.get('same_exit_and_reason')}, entry/stop/exit equal {t.get('entry_equal')}/{t.get('stop_equal')}/{t.get('exit_equal')}, "
        f"within 1e-12 {t.get('entry_within_rel')}/{t.get('stop_within_rel')}/{t.get('exit_within_rel')}, only lab {t.get('only_lab')}, "
        f"only EA {t.get('only_ea')}")
    log(f"  reasons EA {t.get('reasons_ea')} lab {t.get('reasons_lab')}, PREVISE exits {t.get('revised_ea')}")
    for x in t.get("lab_trades_open_at_the_frame_end", []):
        log(f"    left out (open at the frame end): {x}")
    ap = t.get("listed_apart_near_hole_rule", {})
    if ap.get("lab") or ap.get("ea"):
        log(f"  near HOLE_RULE (windows {res['hole_rule_windows']}): lab {ap['lab']} EA {ap['ea']}")
    if "coverage" in res:
        log(f"  coverage: {res['coverage']}")
    if "atr_after_restart" in res:
        log(f"  ATR after a restart (120 days of depth): {res['atr_after_restart']}")
    if "kept_frame" in res:
        log(f"  kept frame: {res['kept_frame']}")
        log(f"  lab ATR warmed up on 120 days: {res['lab_atr_warmed_up_on_120_days']}")
        rz = res["razors"]
        log(f"  razors (the lab's stop and trail comparisons within 1e-9 of flipping): {rz['razors_within_1e-9']} on "
            f"{rz['bars_checked']} bars of {rz['trades']} trades (smallest relative distance {rz['smallest_rel_distance']:.3g}) {rz['list']}")
        ro = res["rebuilt_vs_official"]
        log(f"  lab on the rebuilt frame vs official trades (lab against lab): {ro['same_times_side_reason']} of "
            f"{ro['official_trades_before_2022']} with the same times, side and reason ({ro['same_prices_too']} with the same prices; "
            f"max price diff {ro['max_abs_price_diff_usd_on_same_times']} USD); S0's lab on the official frame: "
            f"{ro['lab_on_the_official_frame_vs_official (S0 ref_lab.py)']}")
        for x in ro["structural_differences"]:
            log(f"    {x}")
    if "sanitizer" in res:
        s = res["sanitizer"]
        log(f"  sanitizer: replay {s['wall_s']} s{' (cached)' if s['cached_replay'] else ''}, warnings {len(s['build_warnings'])}, "
            f"journal identical {s['journal_identical_to_plain_build']}")
    if res["errors"] or res["build_warnings"]:
        log(f"  errors {res['errors']} warnings {res['build_warnings'][:5]}")
    log(f"D4H world {res['world']}: {'PASS' if res['pass'] else 'FAIL'} ({res['sec']} s) -> {os.path.relpath(OUT, ROBOT)}/D4H_{res['world']}_result.json")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", default="all", choices=["all", "is", "holes", "restarts", "unit"])
    ap.add_argument("--no-sanitize", action="store_true", help="skip the sanitizer replays (by default every replay world)")
    ap.add_argument("--fresh", action="store_true", help="ignore cached replays and remake the holes world")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(argv)
    ok = True
    if a.world in ("all", "is"):
        res = check_world(world_is(), not a.no_sanitize, a.fresh)
        report(res, a.verbose)
        ok &= res["pass"]
    if a.world in ("all", "holes"):
        res = check_world(holes_world(a.fresh), not a.no_sanitize, a.fresh)
        report(res, a.verbose)
        ok &= res["pass"]
    if a.world in ("all", "restarts"):
        res = check_world(restarts_world(), not a.no_sanitize, a.fresh)
        report(res, a.verbose)
        ok &= res["pass"]
    if a.world in ("all", "unit"):
        res = check_unit(a.fresh)
        report(res, a.verbose)
        ok &= res["pass"]
    log(f"D4H: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
