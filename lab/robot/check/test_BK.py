"""T4 crypto brk72 (step E): BKB and BKE, switches off, against the lab on the whole in-sample period.

    python3 -I lab/robot/check/test_BK.py [--no-sanitize]

What runs (SPEC 7 T4/T5, SPEC 8 row E):
  * the EA: a private copy of src/ under build/test_E/tree, with the finished files of S0, A, B, C and I, step E's own
    files, and the S0 stubs (git, commit 7b87227) of the steps running beside E (D, F, G, H, J, K): SPEC 8 lets a
    step compile only those. The copy goes through tools/amalgam.py (one file, as the user gets it), check/to_cpp.py
    and g++ (-std=c++17 -O2 -ffp-contract=off -Wall, 0 warnings), against S0's mock and shim and J's mock_faults.h
    stub. It replays the 2013-2021 bars of the four symbols (export_frames.py --tag is) through the S0 driver, with
    InpTrade false and InpK1 = InpH2 = InpS075 = 0.
  * the lab: ref_lab.py's one() for BKB and BKE in a fresh process each (P8), on the frames rebuilt from the same bars,
    written under check/out/test_E/ref/ (make_orders with the recalc wrapper, r2.run).
Checks, per sleeve:
  * orders: every lab order has the EA's DEC line with its oid, same side, stop_dist within 1e-12 relative, its
    activation window [D, D + 5 min] resolving to the lab's entry bar and its exit (D + 24 h, gap rule) to the lab's
    exit bar; every other EA order has no kept bar in its window, or is void (its exit bar does not follow its entry
    bar, which the wrapper drops); no K1 line, no refusal;
  * trades: compare.cmp_trades (entry and exit minute, side, reason equal; prices within 1e-12 relative), every lab
    trade that ends before the frame's last bar; the counts of bit-identical prices are reported;
  * the lab trades on the rebuilt frames against the official trades (results/r2/recalc, entries before 2022): the
    differences are listed with their cause (the export rounds the bid to 2 digits, SPEC 7);
  * the sanitizer build (-fsanitize=address,undefined -D_GLIBCXX_DEBUG) replays the same bars with a journal byte for
    byte identical; the release file (no CR_HARNESS) and the debug file (CR_DEBUG) of the private tree compile with 0
    warnings; the journal keeps S0's replay contract (2 INIT, SELFTEST ok, 1 PLAN, 4 READY, 1 REBUILD, no ERROR, no SEND).
Also holds the harness the other tests of step E import (test_F1.py, test_changes.py). Outputs: check/out/test_E/.
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
HERE = os.path.dirname(os.path.abspath(__file__))
ROBOT = os.path.dirname(HERE)
LAB = os.path.dirname(ROBOT)
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import build as B  # noqa: E402
import compare  # noqa: E402

OUT = os.path.join(HERE, "out", "test_E")
TREE = os.path.join(ROBOT, "build", "test_E")
REF = os.path.join(OUT, "ref")
CUT = pd.Timestamp("2022-01-01", tz="UTC")
STUB_COMMIT = "7b87227"                       # part 1 done: the files of D, F, G, H, J and K are S0's stubs there
OWN = ("CR_Rule_Brk72.mqh", "CR_Rule_F1.mqh", "CR_F1Model.mqh")
FINISHED = ("ClaudeRobot.mq5", "CR_Types.mqh", "CR_Registry.mqh", "CR_Journal.mqh", "CR_Main.mqh", "CR_Rule_Script.mqh",
            "CR_Clock.mqh", "CR_Math.mqh", "CR_Bars.mqh", "CR_Paper.mqh", "CR_Ledger.mqh", "CR_Sizing.mqh")
PARALLEL = ("CR_Rule_IdxUS.mqh", "CR_Rule_NqBtc.mqh", "CR_Rule_GoldFri.mqh", "CR_Rule_Orb.mqh", "CR_Rule_Donch.mqh",
            "CR_Broker.mqh", "CR_Follower.mqh", "CR_Guards.mqh", "CR_Golden.mqh")
SYMS = ("XAUUSD.r", "US100.r", "BTCUSD.r", "ETHUSD.r")
LAB_SYM = {"BKB": "btcusd", "BKE": "ethusd", "F1B": "btcusd", "F1E": "ethusd"}
BROKER = {"btcusd": "BTCUSD.r", "ethusd": "ETHUSD.r"}
RULE = {"BKB": "brk72_24h_wd", "BKE": "brk72_24h_wd", "F1B": "F1_brk_ridge_filter", "F1E": "F1_brk_ridge_filter"}
SID = {"BKB": 3, "BKE": 4, "F1B": 5, "F1E": 6}
SWITCHES_OFF = {"InpTrade": "false", "InpK1": "0", "InpH2": "0", "InpS075": "0", "InpK1T": ""}
REL = 1e-12                                   # SPEC 7: values built on rolling means, and the stops built on them
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
           NUMBA_CACHE_DIR=os.environ.get("NUMBA_CACHE_DIR",
                                          "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/numba"))


# ======================================================================================== the private tree and builds
def stub_text(rel):
    """the S0 stub of a file of a step running beside E: git (read only), else the current file while it is still one"""
    r = subprocess.run(["git", "-C", ROBOT, "show", f"{STUB_COMMIT}:./{rel}"], capture_output=True)
    if r.returncode == 0 and b"S0 STUB" in r.stdout:
        return r.stdout, f"git {STUB_COMMIT}"
    cur = open(os.path.join(ROBOT, rel), "rb").read()
    if b"S0 STUB" in cur:
        return cur, "current file (still the S0 stub)"
    raise RuntimeError(f"{rel}: no S0 stub available (git show failed and the file is no longer a stub)")


def make_tree():
    """build/test_E/tree: src (finished files, E's files, the S0 stubs of the parallel steps), harness, dist"""
    root = os.path.join(TREE, "tree")
    src, har, dist = (os.path.join(root, d) for d in ("src", "harness", "dist"))
    if os.path.isdir(root):
        shutil.rmtree(root)
    for d in (src, har, dist):
        os.makedirs(d)
    known = set(OWN) | set(FINISHED) | set(PARALLEL)
    found = sorted(n for n in os.listdir(os.path.join(ROBOT, "src")) if n.endswith((".mqh", ".mq5")))
    unknown = sorted(set(found) - known)
    missing = sorted(known - set(found))
    if unknown or missing:
        raise RuntimeError(f"src/ has unknown files {unknown} or misses {missing}: the test's file lists need an update")
    origin = {}
    for n in OWN + FINISHED:
        shutil.copy(os.path.join(ROBOT, "src", n), os.path.join(src, n))
        origin[n] = "current"
    for n in PARALLEL:
        txt, how = stub_text(f"src/{n}")
        open(os.path.join(src, n), "wb").write(txt)
        origin[n] = how
    for n in ("mock_replay.h", "mql5_shim.h"):                  # S0's
        shutil.copy(os.path.join(HERE, n), os.path.join(har, n))
    txt, how = stub_text("check/mock_faults.h")                 # J's: its stub
    open(os.path.join(har, "mock_faults.h"), "wb").write(txt)
    origin["mock_faults.h"] = how
    r = subprocess.run([sys.executable, "-I", os.path.join(ROBOT, "tools", "amalgam.py"), "--src", os.path.join(src, "ClaudeRobot.mq5"),
                        "--out", dist], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("amalgam refused the tree:\n" + r.stderr)
    return {"root": root, "src": src, "harness": har, "dist": os.path.join(dist, "ClaudeRobot.mq5"), "origin": origin}


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


def compile_cpp(run_cpp, exe, sanitize, extra_defines=()):
    t = tree()
    cmd = B.CXX + (B.SAN if sanitize else []) + ["-DCR_HARNESS", "-DCR_XAU_COMM_PTS=0"] + [f"-D{d}" for d in extra_defines] + \
        ["-I", t["harness"], "-I", os.path.dirname(run_cpp), run_cpp, "-o", exe]
    r = subprocess.run(cmd, capture_output=True, text=True)
    warn = [ln for ln in r.stderr.splitlines() if "warning:" in ln]
    if r.returncode:
        raise B.BuildError(f"compile failed ({exe}):\n" + r.stderr[-20000:])
    return warn


def build_ea(sanitize):
    """the replay binary of the private tree's single file; reused while the file and the harness are unchanged"""
    t = tree()
    name = "ea_san" if sanitize else "ea"
    work = os.path.join(TREE, name)
    key = sha_files([t["dist"]] + [os.path.join(t["harness"], n) for n in ("mock_replay.h", "mql5_shim.h", "mock_faults.h")]) + \
        (" san" if sanitize else "") + " " + " ".join(B.CXX + (B.SAN if sanitize else []))
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
    warn = compile_cpp(run, exe, sanitize)
    json.dump(warn, open(os.path.join(work, "warnings.json"), "w"))
    open(stamp, "w").write(key)
    return exe, warn


def build_unit(name, entry, main_cpp, sanitize=False):
    """a generated C++ program (written under build/test_E/): the mock without its main, one module of the private tree
    translated with what it includes (entry, e.g. "CR_Rule_F1.mqh"), then main_cpp (as SPEC 8's module tests)"""
    t = tree()
    work = os.path.join(TREE, name)
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)
    B.translate(os.path.join(t["src"], entry), os.path.join(work, "ea.cpp"))
    run = os.path.join(work, "run.cpp")
    with open(run, "w") as f:
        f.write("#define MOCK_REPLAY_NO_MAIN\n")
        f.write(f'#include "{os.path.join(t["harness"], "mock_replay.h")}"\n#include "{os.path.join(work, "ea.cpp")}"\n')
        f.write(main_cpp)
    exe = os.path.join(work, "unit")
    warn = compile_cpp(run, exe, sanitize)
    return exe, warn


# ======================================================================================== data, references, replay
def bars():
    """the 2013-2021 broker bars of the four symbols (S0's export_frames.py --tag is), exported when missing"""
    p = {s: os.path.join(HERE, "out", "bars", f"{s}_is.bin") for s in SYMS}
    if not all(os.path.exists(v) for v in p.values()):
        subprocess.run([sys.executable, "-I", os.path.join(HERE, "export_frames.py"), "--tag", "is"], check=True, env=ENV,
                       capture_output=True)
    return p


def manifest_last():
    """last bar start of each broker symbol (UTC seconds), from the export's manifest"""
    m = json.load(open(os.path.join(HERE, "out", "manifest_is.json")))
    return {r["broker"]: int(pd.Timestamp(r["last"]).value // 10**9) for r in m}


def spawn(code):
    r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, env=ENV, cwd=ROBOT)
    if r.returncode:
        raise RuntimeError("reference process failed:\n" + r.stderr[-4000:])
    return json.loads(r.stdout.strip().splitlines()[-1])


def lab_ref(code, kind="rebuilt"):
    """ref_lab.one(code) in a fresh process (P8), its outputs under check/out/test_E/ref/<kind>[_is]/"""
    tag = "is" if kind == "rebuilt" else None
    src = (f"import sys, json; sys.dont_write_bytecode = True; sys.path.insert(0, {HERE!r}); import ref_lab; "
           f"ref_lab.OUT = {REF!r}; print(json.dumps(ref_lab.one({code!r}, {kind!r}, {tag!r}), default=str))")
    res = spawn(src)
    d = os.path.join(REF, kind + ("_is" if tag else ""), code)
    return res, pd.read_parquet(os.path.join(d, "orders.parquet")), pd.read_parquet(os.path.join(d, "trades.parquet"))


def change_ref(cid, kind="rebuilt"):
    """ref_changes.run_change(cid) in a fresh process, its outputs under check/out/test_E/ref/<kind>[_is]/changes/<cid>/"""
    tag = "is" if kind == "rebuilt" else None
    out = os.path.join(REF, kind + ("_is" if tag else ""))
    src = (f"import sys, json; sys.dont_write_bytecode = True; sys.path.insert(0, {HERE!r}); import ref_changes; "
           f"print(json.dumps(ref_changes.run_change({cid!r}, {kind!r}, {tag!r}, {out!r}), default=str))")
    res = spawn(src)
    d = os.path.join(out, "changes", cid)
    files = {n[:-8]: pd.read_parquet(os.path.join(d, n)) for n in os.listdir(d) if n.endswith(".parquet")}
    return res, files


def official_trades(code):
    p = os.path.join(LAB, "results", "r2", "recalc", "trades", f"{RULE[code]}__{LAB_SYM[code]}.parquet")
    return pd.read_parquet(p, filters=[("entry_time", "<", CUT)])


_FRAMES = {}


def frame(sym):
    """the rebuilt in-sample frame of a lab symbol (= the EA's kept bars, T2), read with the 2022 filter"""
    if sym not in _FRAMES:
        m1 = pd.read_parquet(os.path.join(HERE, "out", "frames", f"{sym}_is.parquet"), filters=[("ts", "<", CUT)])
        assert len(m1) and m1.index.max() < CUT
        _FRAMES[sym] = m1
    return _FRAMES[sym]


def frame_secs(sym):
    return pd.DatetimeIndex(frame(sym).index).as_unit("s").asi8.astype(np.int64)


def replay(exe, name, inputs, env_extra=None):
    """the EA over the in-sample bars; returns (journal rows, stdout, seconds, MOCK_FILES dir). A replay of the same
    binary (sha256), inputs and bar files already in OUT/<name> is read again instead of run again (test_BK and test_F1
    share the switches-off replays; the sanitizer one takes about 4 minutes)"""
    files = os.path.join(OUT, name)
    env = {f"MOCK_INPUT_{k}": v for k, v in inputs.items()}
    env.update(env_extra or {})
    bp = bars()
    key = json.dumps({"exe": sha_files([exe]), "env": env, "bars": {s: [os.path.getsize(p), os.path.getmtime(p)] for s, p in bp.items()}},
                     sort_keys=True)
    stamp = os.path.join(files, "_replay_key.json")
    done = os.path.join(files, "_replay_out.json")
    if os.path.exists(stamp) and os.path.exists(done) and open(stamp).read() == key:
        d = json.load(open(done))
        return compare.read_journal(files), d["out"], d["wall"], files
    out, wall = B.replay(exe, files, bp, env=env, fresh=True)
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


# ======================================================================================== comparisons
def secs(ts):
    return pd.DatetimeIndex(ts).tz_convert("UTC").as_unit("s").asi8.astype(np.int64)


def exit_bar(idx, x, gap):
    """gl.exit_index on the frame's bar starts (seconds): first bar at or after x; with the gap rule, the bar before
    when the next one starts more than 30 min after x (or there is none)"""
    x = np.asarray(x, np.int64)
    xi = np.searchsorted(idx, x, side="left").astype(np.int64)
    if not gap:
        return xi
    nxt = idx[np.clip(xi, 0, len(idx) - 1)]
    g = (xi >= len(idx)) | (nxt - x > 1800)
    return np.where(g & (xi > 0), xi - 1, xi).astype(np.int64)


def act_bar(idx, tf, tt):
    """the activation bar of [tf, tt] (first bar starting inside), -1 when none"""
    ai = np.searchsorted(idx, np.asarray(tf, np.int64), side="left").astype(np.int64)
    ok = (ai < len(idx)) & (idx[np.clip(ai, 0, len(idx) - 1)] <= np.asarray(tt, np.int64))
    return np.where(ok, ai, -1)


def what_of(r):
    """the DEC kind; compare.num reads any text holding "inf" or "nan" as a number, so "info" comes back as inf"""
    w = r.get("what")
    if isinstance(w, float) and w == float("inf"):
        return "info"
    return w


def dec_rows(rows, code, what):
    d = pd.DataFrame([r for r in rows if r["ev"] == "DEC" and r["code"] == code and what_of(r) == what])
    return d


def rel_diff(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    den = np.maximum(np.abs(a), np.abs(b))
    return np.where(a == b, 0.0, np.abs(a - b) / np.where(den > 0, den, 1.0))


def cmp_orders(rows, code, lab, sym, expect, x_col="x"):
    """the EA's orders (DEC what=ord) against the lab's orders of the same frame (see the module docstring)"""
    idx = frame_secs(sym)
    ea = dec_rows(rows, code, "ord")
    res = {"code": code, "lab_orders": int(len(lab)), "ea_orders": int(len(ea))}
    if not len(ea):
        res["pass"] = len(lab) == 0
        return res, ea
    dup = int(ea.oid.duplicated().sum())
    ea = ea.drop_duplicates("oid", keep="last").set_index("oid")
    ea["ai"] = act_bar(idx, ea.tf.to_numpy(np.int64), ea.tt.to_numpy(np.int64))
    ea["xi"] = exit_bar(idx, ea[x_col].to_numpy(np.int64), True)
    bad_fields = {}
    for k, v in expect.items():
        n_bad = int((ea[k] != v).sum())
        if n_bad:
            bad_fields[k] = n_bad
    lab = lab.reset_index(drop=True).copy()
    lab["oid"] = lab["ea_oid"] if "ea_oid" in lab else (secs(lab["dec_time"]) if "dec_time" in lab
                                                        else lab["cid"].to_numpy(np.int64) // 10**9) * 100 + SID[code]
    lab = lab.set_index("oid")
    both = lab.index.intersection(ea.index)
    only_lab = sorted(int(x) for x in lab.index.difference(ea.index))
    only_ea = ea.loc[ea.index.difference(lab.index)]
    L, E = lab.loc[both], ea.loc[both]
    same_side = (L.side.to_numpy() == E.side.to_numpy())
    same_entry = (L.entry_i.to_numpy() == E.ai.to_numpy())
    same_exit = (L.exit_i.to_numpy() == E.xi.to_numpy())
    rd = rel_diff(L.stop_dist.to_numpy(), E.sd.to_numpy())
    wrong = [{"oid": int(o), "side": [int(a), int(b)], "entry_bar": [int(c), int(d)], "exit_bar": [int(e), int(f)],
              "stop_dist": [float(g), float(h)]}
             for o, a, b, c, d, e, f, g, h, ok in zip(both, L.side, E.side, L.entry_i, E.ai, L.exit_i, E.xi, L.stop_dist, E.sd,
                                                      same_side & same_entry & same_exit & (rd <= REL)) if not ok]
    # EA orders the lab does not have: no kept bar in their window, or void (the wrapper's exit_i > entry_i)
    no_bar = only_ea[only_ea.ai < 0]
    void = only_ea[(only_ea.ai >= 0) & (only_ea.xi <= only_ea.ai)]
    other = only_ea[(only_ea.ai >= 0) & (only_ea.xi > only_ea.ai)]
    res.update({"matched": int(len(both)), "duplicates": dup, "only_lab": len(only_lab), "only_lab_first": only_lab[:10],
                "only_ea_no_bar_in_window": int(len(no_bar)), "only_ea_void": int(len(void)),
                "only_ea_unexplained": int(len(other)), "only_ea_unexplained_first": [int(x) for x in other.index[:10]],
                "wrong": len(wrong), "wrong_first": wrong[:10], "stop_dist_bit_equal": int((rd == 0).sum()),
                "stop_dist_max_rel_diff": float(rd.max()) if len(rd) else 0.0, "fields_not_as_expected": bad_fields})
    res["pass"] = (dup == 0 and not only_lab and len(other) == 0 and not wrong and not bad_fields)
    return res, ea


def cmp_trades(rows, code, lab_trades, t_from, t_to):
    """compare.cmp_trades, plus the counts of bit-identical prices and the largest relative differences"""
    r = compare.cmp_trades(rows, lab_trades, code, t_from=t_from, t_to=t_to, rel=REL)
    ea = compare.paper_trades(rows, code)
    lab = lab_trades[(lab_trades.entry_time >= pd.Timestamp(t_from, unit="s", tz="UTC"))
                     & (lab_trades.exit_time <= pd.Timestamp(t_to, unit="s", tz="UTC"))]
    if len(ea) and len(lab):
        m = lab.merge(ea, on=["entry_time", "side"], suffixes=("_lab", "_ea"))
        for c in ("entry", "stop", "exit"):
            d = rel_diff(m[f"{c}_lab"], m[f"{c}_ea"])
            r[f"{c}_max_rel_diff"] = float(d.max()) if len(d) else 0.0
    good = (r.get("lab_trades", 0) > 0 and r["pass"] and r.get("only_lab") == 0 and r.get("only_ea") == 0
            and r.get("same_exit_and_reason") == r.get("same_entry") == r.get("lab_trades"))
    r["pass"] = bool(good)
    return r


def official_diff(code, reb_trades, off_orders=None, reb_orders=None):
    """the lab's trades on the rebuilt frame against the official trades (entries before 2022): what differs, and why"""
    off = official_trades(code)
    a = off.reset_index(drop=True)
    b = reb_trades.reset_index(drop=True)
    m = a.merge(b, on=["entry_time", "side"], how="outer", suffixes=("_off", "_reb"), indicator=True)
    both = m[m._merge == "both"]
    same_xr = (both.exit_time_off == both.exit_time_reb) & (both.reason_off == both.reason_reb)
    res = {"code": code, "official": int(len(a)), "rebuilt": int(len(b)), "same_entry_side": int(len(both)),
           "same_exit_and_reason": int(same_xr.sum()), "only_official": int((m._merge == "left_only").sum()),
           "only_rebuilt": int((m._merge == "right_only").sum())}
    for c in ("entry", "exit", "R"):
        d = (both[f"{c}_off"] - both[f"{c}_reb"]).abs()
        res[f"max_abs_{c}_diff"] = float(d.max()) if len(d) else 0.0
    rows = []
    lim = pd.Timestamp("2022-01-01", tz="UTC")
    for _, r in m[(m._merge != "both") | ~((m.exit_time_off == m.exit_time_reb) & (m.reason_off == m.reason_reb))].iterrows():
        row = {"entry_time": str(r.entry_time), "side": int(r.side), "in": {"left_only": "official only", "right_only": "rebuilt only",
                                                                            "both": "both"}[r._merge],
               "official_exit": str(r.get("exit_time_off")), "official_reason": str(r.get("reason_off")),
               "rebuilt_exit": str(r.get("exit_time_reb")), "rebuilt_reason": str(r.get("reason_reb"))}
        if r._merge == "left_only" and pd.notna(r.exit_time_off) and r.exit_time_off >= lim:
            row["cause"] = "the official exit falls in 2022 (beyond the in-sample frame)"
        rows.append(row)
    res["differences"] = rows
    if off_orders is not None and reb_orders is not None:
        ko = set(int(x) for x in off_orders.oid_ea) if "oid_ea" in off_orders else None
        kr = set(int(x) for x in reb_orders.oid_ea) if "oid_ea" in reb_orders else None
        if ko is not None and kr is not None:
            res["orders_only_official"] = sorted(ko - kr)[:20]
            res["orders_only_rebuilt"] = sorted(kr - ko)[:20]
            res["n_orders_only_official"] = len(ko - kr)
            res["n_orders_only_rebuilt"] = len(kr - ko)
    return res


DETAIL_SRC = """
import sys, os, json
sys.dont_write_bytecode = True
import numpy as np, pandas as pd
LAB, CHECK, CODE, SYM, TIMES = {lab!r}, {check!r}, {code!r}, {sym!r}, {times!r}
sys.path.insert(0, LAB); sys.path.insert(0, os.path.join(LAB, "r2"))
import recalc
reg = {{(s[1], s[2]): s for s in recalc.sleeves()}}
CUT = pd.Timestamp("2022-01-01", tz="UTC")
out = {{}}
for kind, p in (("official", os.path.join(LAB, "data", "fp", SYM + "_m1.parquet")),
                ("rebuilt", os.path.join(CHECK, "out", "frames", SYM + "_is.parquet"))):
    m1 = pd.read_parquet(p, filters=[("ts", "<", CUT)])
    d = {{}}
    if CODE in ("BKB", "BKE"):
        M = sys.modules["r2_crypto_strategy"]
        b = M.h1_bars(m1)
        c = b["c"]
        hi, lo = c.rolling(72).max().shift(1), c.rolling(72).min().shift(1)
        dec = (b["start"] + 3600000) // 1000
        for t in TIMES:
            k = np.flatnonzero(dec.to_numpy() == t)
            if len(k):
                i = k[0]
                d[str(t)] = {{"close": float(c.iat[i]), "hi72": float(hi.iat[i]), "lo72": float(lo.iat[i]),
                             "side": int(1 if c.iat[i] > hi.iat[i] else (-1 if c.iat[i] < lo.iat[i] else 0))}}
            else:
                d[str(t)] = None
    else:
        M = sys.modules["r2_ml_strategy"]
        params = reg[("F1_brk_ridge_filter", SYM)][4]
        M._cache.clear()
        b = M.session_bars(m1, 2, 16)
        hh, ll = b["h"].shift(1).rolling(14).max(), b["l"].shift(1).rolling(14).min()
        f = M.candidates(m1, **{{**params, "max_wait_min": 10**9}})
        spec = M.load_model(params["model"])["frozen"]
        sc = dict(zip(pd.DatetimeIndex(f["t_dec"]).as_unit("s").asi8.tolist(), M.score_model(f, spec).tolist()))
        dec = pd.DatetimeIndex(b.index + pd.Timedelta(hours=1)).as_unit("s").asi8
        for t in TIMES:
            k = np.flatnonzero(dec == t)
            if len(k):
                i = k[0]
                d[str(t)] = {{"close": float(b["c"].iat[i]), "hh14": float(hh.iat[i]), "ll14": float(ll.iat[i]),
                             "side": int(1 if b["c"].iat[i] > hh.iat[i] else (-1 if b["c"].iat[i] < ll.iat[i] else 0)),
                             "score": sc.get(int(t))}}
            else:
                d[str(t)] = None
    out[kind] = d
print(json.dumps(out))
"""


def decision_detail(code, times):
    """the decision inputs at each time (UTC s) on the official and the rebuilt frame, from the lab's own functions (a
    fresh process): brk72 the hour close and the 72-close channel; F1 the session close, the 14-bar channel, the score"""
    if not times:
        return {}
    return spawn(DETAIL_SRC.format(lab=LAB, check=HERE, code=code, sym=LAB_SYM[code], times=sorted(int(t) for t in times)))


def explain(code, od):
    """why the rebuilt-frame trades differ from the official ones: the decisions of the differing trades and of the
    orders present on one frame only, read on both frames"""
    tms = set()
    for r in od["differences"]:
        tms.add(int(pd.Timestamp(r["entry_time"]).floor("h").value // 10**9))
    for k in ("orders_only_official", "orders_only_rebuilt"):
        tms.update(int(x) // 100 for x in od.get(k, []))
    det = decision_detail(code, tms)
    thr = json.load(open(os.path.join(LAB, "r2", "tracks", "ml", "models", "B1_ridge_full.json")))["frozen"]["thr"]["0.5"]
    rows = []
    for t in sorted(tms):
        o, r = det["official"].get(str(t)), det["rebuilt"].get(str(t))
        if code in ("BKB", "BKE"):
            why = (f"official side {o and o['side']} (close {o and o['close']}, channel {o and o['lo72']}..{o and o['hi72']}), "
                   f"rebuilt side {r and r['side']} (close {r and r['close']}, channel {r and r['lo72']}..{r and r['hi72']})")
        else:
            why = (f"official side {o and o['side']} score {o and o.get('score')} (close {o and o['close']}, channel "
                   f"{o and o['ll14']}..{o and o['hh14']}); rebuilt side {r and r['side']} score {r and r.get('score')} (close "
                   f"{r and r['close']}, channel {r and r['ll14']}..{r and r['hh14']}); threshold {thr}")
        rows.append({"decision": str(pd.Timestamp(t, unit="s", tz="UTC")), "official": o, "rebuilt": r,
                     "cause": "the export rounds the bid to 2 digits (SPEC 7): " + why})
    return rows


def with_ea_oid(orders, code):
    o = orders.copy()
    d = secs(o["dec_time"]) if "dec_time" in o else o["cid"].to_numpy(np.int64) // 10**9
    o["oid_ea"] = d * 100 + SID[code]
    return o


def counts(rows, code):
    c = {}
    for r in rows:
        if r["code"] == code:
            k = r["ev"] + (":" + str(what_of(r)) if r["ev"] == "DEC" else "")
            c[k] = c.get(k, 0) + 1
    return dict(sorted(c.items()))


def errors(rows):
    return [r for r in rows if r["ev"] == "ERROR"]


def write(name, res):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w") as f:
        json.dump(res, f, indent=1, default=str)


def build_variants():
    """the private tree's single file as the user gets it (no CR_HARNESS, CR_XAU_COMM_PTS 6) and its debug twin
    (dist/ClaudeRobot_debug.mq5, CR_DEBUG), compiled only: every warning is reported"""
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
        cmd = B.CXX + (["-DCR_HARNESS", "-DCR_XAU_COMM_PTS=0"] if harness else []) + ["-I", t["harness"], "-I", work, run, "-o",
                                                                                      os.path.join(work, "replay")]
        r = subprocess.run(cmd, capture_output=True, text=True)
        out[name] = {"exit": r.returncode, "warnings": [ln for ln in r.stderr.splitlines() if "warning:" in ln][:10],
                     "error": r.stderr[-2000:] if r.returncode else ""}
    out["pass"] = all(v["exit"] == 0 and not v["warnings"] for v in out.values() if isinstance(v, dict))
    return out


def s0_contract(rows):
    """S0's replay contract (test_s0_replay.py) on this journal: two INIT lines, SELFTEST ok, one PLAN, four READY, one
    REBUILD, no ERROR, no SEND: the rules add only their own lines"""
    ev = {}
    for r in rows:
        ev[r["ev"]] = ev.get(r["ev"], 0) + 1
    st = [r for r in rows if r["ev"] == "SELFTEST"]
    res = {"INIT": ev.get("INIT", 0), "SELFTEST_ok": int(st[0]["ok"]) if st else None, "PLAN": ev.get("PLAN", 0),
           "READY": ev.get("READY", 0), "REBUILD": ev.get("REBUILD", 0), "ERROR": ev.get("ERROR", 0), "SEND": ev.get("SEND", 0)}
    res["pass"] = (res["INIT"] == 2 and res["SELFTEST_ok"] == 1 and res["PLAN"] == 1 and res["READY"] == 4 and res["REBUILD"] == 1
                   and res["ERROR"] == 0 and res["SEND"] == 0)
    return res


# ======================================================================================== the brk72 test
EXPECT_OFF = {"et": 0, "xg": 1, "vle": 1, "ref": 0, "xh": 0}


def check_window(ea, hold_s):
    """the order's own times: [D, D + 5 min], x = D + hold"""
    if not len(ea):
        return 0
    d = ea.reset_index()
    D = d.oid.to_numpy(np.int64) // 100
    return int(((d.tf.to_numpy() != D) | (d.tt.to_numpy() != D + 300) | (d.x.to_numpy() != D + hold_s)).sum())


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-sanitize", action="store_true")
    a = ap.parse_args(argv)
    t0 = time.time()
    res = {"test": "T4 brk72 BKB BKE, switches off", "per_sleeve": {}}
    refs = {c: lab_ref(c) for c in ("BKB", "BKE")}
    offs = {c: lab_ref(c, "official") for c in ("BKB", "BKE")}
    exe, warn = build_ea(False)
    res["tree"] = tree()["origin"]
    res["build_warnings"] = warn
    rows, out, wall, files = replay(exe, "off", SWITCHES_OFF)
    res["replay"] = {"stdout": out, "wall_s": round(wall, 1), "errors": errors(rows)[:5]}
    fm, last = first_minute(rows), manifest_last()
    res["s0_contract"] = s0_contract(rows)
    res["builds"] = build_variants()
    ok = not warn and not res["replay"]["errors"] and res["s0_contract"]["pass"] and res["builds"]["pass"]
    print(f"builds: harness {len(warn)} warnings, release exit {res['builds']['release']['exit']} warnings "
          f"{len(res['builds']['release']['warnings'])}, debug exit {res['builds']['debug']['exit']} warnings "
          f"{len(res['builds']['debug']['warnings'])} | S0 journal contract {res['s0_contract']} ", flush=True)
    for code in ("BKB", "BKE"):
        info, lab_o, lab_t = refs[code]
        sym = LAB_SYM[code]
        ro, ea = cmp_orders(rows, code, lab_o, sym, EXPECT_OFF)
        ro["window_or_exit_not_D_plus"] = check_window(ea, 86400)
        rt = cmp_trades(rows, code, lab_t, fm, last[BROKER[sym]] - 1)
        c = counts(rows, code)
        extra_lines = {k: v for k, v in c.items() if k in ("DEC:skip", "DEC:info", "PREFUSE", "HOLD")}
        od = official_diff(code, lab_t, with_ea_oid(offs[code][1], code), with_ea_oid(lab_o, code))
        od["causes"] = explain(code, od)
        good = ro["pass"] and ro["window_or_exit_not_D_plus"] == 0 and rt["pass"] and not extra_lines
        res["per_sleeve"][code] = {"orders": ro, "trades": rt, "journal_counts": c, "unexpected_lines": extra_lines,
                                   "lab_rebuilt": {k: info[k] for k in ("orders", "trades", "R_sum", "reasons")},
                                   "lab_official": {k: offs[code][0][k] for k in ("orders", "trades", "R_sum")},
                                   "rebuilt_vs_official": od, "pass": bool(good)}
        ok &= good
        print(f"{code}: orders lab {ro['lab_orders']} EA {ro['ea_orders']} matched {ro.get('matched')} wrong {ro.get('wrong')} "
              f"only_lab {ro.get('only_lab')} | EA extra: no bar {ro.get('only_ea_no_bar_in_window')} void {ro.get('only_ea_void')} "
              f"unexplained {ro.get('only_ea_unexplained')} | stop_dist bit-equal {ro.get('stop_dist_bit_equal')} "
              f"max rel {ro.get('stop_dist_max_rel_diff'):.3g} | trades lab {rt.get('lab_trades')} EA {rt.get('ea_trades')} "
              f"same {rt.get('same_exit_and_reason')} entry/stop/exit bit-equal {rt.get('entry_equal')}/{rt.get('stop_equal')}/"
              f"{rt.get('exit_equal')} voided {rt.get('voided_in_journal')} | {'PASS' if good else 'FAIL'}", flush=True)
        print(f"     rebuilt vs official: official {od['official']} rebuilt {od['rebuilt']} same exit+reason "
              f"{od['same_exit_and_reason']} only official {od['only_official']} only rebuilt {od['only_rebuilt']} "
              f"max |R| diff {od['max_abs_R_diff']:.3g}", flush=True)
    if not a.no_sanitize:
        exe_s, warn_s = build_ea(True)
        rows_s, out_s, wall_s, files_s = replay(exe_s, "off_san", SWITCHES_OFF)
        same = journals_identical(files, files_s)
        res["sanitizer"] = {"build_warnings": warn_s, "stdout": out_s, "wall_s": round(wall_s, 1), "journal_identical": same}
        ok &= same and not warn_s
        print(f"sanitizer: warnings {len(warn_s)} journal identical {same} ({wall_s:.0f} s)", flush=True)
    res["pass"] = bool(ok)
    res["sec"] = round(time.time() - t0, 1)
    write("test_BK.json", res)
    print(f"test_BK: {'PASS' if ok else 'FAIL'} ({res['sec']} s) -> {os.path.relpath(os.path.join(OUT, 'test_BK.json'), ROBOT)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
