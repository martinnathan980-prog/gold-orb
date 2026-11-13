"""T10 release: the two files the user gets (dist/ClaudeRobot.mq5, dist/ClaudeRobot_debug.mq5) and the self-test's guard.

    python3 -I lab/robot/check/test_release.py [--keep]

Checks (SPEC 1 "Single file", SPEC 7 T10; step K):
  1. Released: tools/amalgam.py run again into build/test_release/amalgam gives the dist files byte for byte (dist is
     the current src/); CR_BUILD is the first 12 hex digits of the sha256 of the text below it; the debug file is the
     same text with `#define CR_DEBUG` first; every src file is inlined exactly once; only <Trade\\Trade.mqh> is left as
     an include; pure ASCII.
  2. No harness constant: the dist files define none of CR_HARNESS, CR_NO_GUARD, CR_DEBUG (the release file),
     CR_IDX_TRACE (step D's diagnostic) or any MOCK_ name; CR_XAU_COMM_PTS is defined once, under #ifndef, as 6, and
     CR_BRK_NOTIONAL_X (the 20 x balance cap, raised only by T7b's harness build) once, under #ifndef, as 20.0; the
     harness-only inputs (InpScript, InpScriptDir) and the script rule sit inside #ifdef CR_HARNESS blocks.
  3. The 15 inputs of SPEC 1, in order, with their types and defaults (D2: InpRiskTable 0:10;3000:5;10000:2;20000:1, no
     plan stop, InpGuard false); no other input outside #ifdef CR_HARNESS.
  4. MQL5 subset (SPEC 1): no fmax/fmin, no '->', 'new', '#import', 'virtual', 'template', function-like macro, Sleep
     (to_cpp.py refuses them; it translates the file below), no `#property strict`.
  5. Builds, 0 warnings each: the harness build (CR_HARNESS, CR_XAU_COMM_PTS=0), its sanitizer build, the release
     build (no CR_HARNESS: what MetaEditor compiles), the debug file as a release build, and the release build with
     -DCR_NO_GUARD and with -DCR_XAU_COMM_PTS=0 (the two forbidden constants); the CR_NO_GUARD build no longer warns
     about `settled` (request 1 of step K, fixed).
  6. The guard works through the whole EA in the replay mock (one week of 2021, InpTrade true, a demo account):
       release build             SELFTEST ok=1 with every golden vector (CR_GOLDEN_N of src/CR_Golden.mqh), INIT
                                 harness=0 comm_pts=6 and the default plan D2, orders sent; the journal (review F9):
                                 Print (the mock's log) carries no rp=1 line while the file does, and the file is
                                 flushed at most once per timer pass;
       release + CR_NO_GUARD     SELFTEST ok=0 why=CR_NO_GUARD..., no SEND, the intents skipped as selftest;
       release + comm 0          SELFTEST ok=0 why=CR_XAU_COMM_PTS..., no SEND;
       release + notional 1000   SELFTEST ok=0 why=CR_BRK_NOTIONAL_X..., no SEND (the 20 x balance cap is fixed);
       harness, one golden F1 score changed in a copy of the dist file   SELFTEST ok=0 why=golden f1_score ..., no SEND;
       debug file                its BAR lines (the bar dump of CR_DEBUG) are there.
Outputs: check/out/test_release/summary.json; builds under build/test_release/ (removed unless --keep).
"""
import argparse
import calendar
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROBOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import compare  # noqa: E402
from build import BuildError, build, replay  # noqa: E402

OUT = os.path.join(HERE, "out", "test_release")
WORK = os.path.join(ROBOT, "build", "test_release")
DIST = os.path.join(ROBOT, "dist", "ClaudeRobot.mq5")
DIST_DBG = os.path.join(ROBOT, "dist", "ClaudeRobot_debug.mq5")
SYMS = ("XAUUSD.r", "US100.r", "BTCUSD.r", "ETHUSD.r")
INPUTS = [("bool", "InpTrade", "true"), ("datetime", "InpPlanStart", "0"), ("string", "InpRiskTable", '"0:10;3000:5;10000:2;20000:1"'),
          ("double", "InpStopFallPct", "0.0"), ("double", "InpStopArmPaid", "12000.0"), ("bool", "InpGuard", "false"),
          ("string", "InpSleeves", '"ALL"'), ("int", "InpK1", "-1"), ("int", "InpH2", "-1"), ("int", "InpS075", "-1"),
          ("string", "InpK1T", '""'), ("double", "InpDailyLockStakes", "0.0"), ("int", "InpFridayCloseHHMM", "0"),
          ("string", "InpExtraClosures", '""'), ("bool", "InpPush", "true")]
D2 = "0:10;3000:5;10000:2;20000:1"
HARNESS_DEFINES = ("CR_HARNESS", "CR_NO_GUARD", "CR_IDX_TRACE", "CR_DEBUG")
FROM = calendar.timegm((2021, 3, 1, 0, 0, 0))                 # server time; in sample
TO = calendar.timegm((2021, 3, 6, 0, 0, 0))


def text(p):
    return open(p, "rb").read()


def golden_n():
    """CR_GOLDEN_N of the generated src/CR_Golden.mqh (the SELFTEST line's golden=)"""
    m = re.search(r"^#define CR_GOLDEN_N (\d+)", open(os.path.join(ROBOT, "src", "CR_Golden.mqh")).read(), re.M)
    return int(m.group(1)) if m else -1


def check_released(res):
    """1. dist = amalgam(src) now; CR_BUILD; debug = release + CR_DEBUG; each src file once; ASCII"""
    d = os.path.join(WORK, "amalgam")
    os.makedirs(d, exist_ok=True)
    r = subprocess.run([sys.executable, "-I", os.path.join(ROBOT, "tools", "amalgam.py"), "--out", d], capture_output=True, text=True)
    same = r.returncode == 0 and text(os.path.join(d, "ClaudeRobot.mq5")) == text(DIST) and \
        text(os.path.join(d, "ClaudeRobot_debug.mq5")) == text(DIST_DBG)
    rel, dbg = text(DIST), text(DIST_DBG)
    out = {"amalgam_exit": r.returncode, "dist_is_current_src": same}
    try:
        rel.decode("ascii")
        dbg.decode("ascii")
        out["ascii"] = True
    except UnicodeDecodeError:
        out["ascii"] = False
    first, body = rel.split(b"\n", 1)
    m = re.match(rb'#define CR_BUILD "([0-9a-f]{12})"$', first)
    out["cr_build"] = m.group(1).decode() if m else None
    out["cr_build_is_sha_of_body"] = bool(m) and hashlib.sha256(body).hexdigest()[:12] == m.group(1).decode()
    d_first, d_body = dbg.split(b"\n", 1)
    md = re.match(rb'#define CR_BUILD "([0-9a-f]{12})"$', d_first)
    out["debug_is_release_plus_cr_debug"] = bool(md) and d_body == b"#define CR_DEBUG\n" + body and \
        hashlib.sha256(d_body).hexdigest()[:12] == md.group(1).decode()
    src = sorted(f for f in os.listdir(os.path.join(ROBOT, "src")) if f.endswith((".mqh", ".mq5")))
    begins = re.findall(rb"^// ==== begin src/(\S+)$", rel, re.M)
    out["src_files"] = len(src)
    out["inlined_once"] = sorted(b.decode() for b in begins) == src and len(begins) == len(set(begins))
    incs = re.findall(rb'^\s*#include\s+(\S+)', rel, re.M)
    out["includes_left"] = sorted(set(i.decode() for i in incs))
    ok = same and out["ascii"] and out["cr_build_is_sha_of_body"] and out["debug_is_release_plus_cr_debug"] and out["inlined_once"] \
        and out["includes_left"] == ["<Trade\\Trade.mqh>"]
    res["released"] = dict(out, pass_=ok)
    return ok


def blocks(lines):
    """for each line, the stack of the #if conditions it sits in (as written)"""
    stack, out = [], []
    for ln in lines:
        s = ln.strip()
        if re.match(r"#\s*(if|ifdef|ifndef)\b", s):
            stack.append(s)
            out.append(list(stack))
            continue
        if re.match(r"#\s*endif\b", s):
            out.append(list(stack))
            if stack:
                stack.pop()
            continue
        if re.match(r"#\s*else\b", s) and stack:
            stack[-1] = stack[-1] + " #else"
        out.append(list(stack))
    return out


def check_constants(res):
    """2-4. harness constants, the 14 inputs, the MQL5 subset"""
    lines = text(DIST).decode("ascii").split("\n")
    ctx = blocks(lines)
    bad_def, comm, inputs, stray, subset, notional = [], [], [], [], [], []
    for no, (ln, st) in enumerate(zip(lines, ctx), 1):
        code = ln.split("//", 1)[0]
        m = re.match(r"\s*#\s*define\s+(\w+)\b(.*)$", code)
        if m:
            name = m.group(1)
            if name in HARNESS_DEFINES or name.startswith("MOCK_"):
                bad_def.append((no, ln.strip()))
            if name == "CR_XAU_COMM_PTS":
                comm.append((no, m.group(2).strip(), st[-1] if st else ""))
            if name == "CR_BRK_NOTIONAL_X":
                notional.append((no, m.group(2).strip(), st[-1] if st else ""))
        m = re.match(r'\s*input\s+(\w+)\s+(Inp\w+)\s*=\s*("(?:\\.|[^"\\])*"|[^;"]+?)\s*;', code)
        if m:
            in_harness = any("CR_HARNESS" in s and "#ifdef" in s and "#else" not in s for s in st)
            (stray if in_harness else inputs).append((m.group(1), m.group(2), m.group(3).strip()))
        bare = re.sub(r'"(\\.|[^"\\])*"', '""', code)
        for rx, why in ((r"\bf(max|min)\s*\(", "fmax/fmin"), (r"->", "->"), (r"\bnew\s+\w+", "new"), (r"^\s*#import\b", "#import"),
                        (r"\bvirtual\b", "virtual"), (r"\btemplate\s*<", "template"), (r"^\s*#define\s+\w+\(", "function-like macro"),
                        (r"\bSleep\s*\(", "Sleep"), (r"#property\s+strict", "#property strict")):
            if re.search(rx, bare):
                subset.append((no, why, ln.strip()[:120]))
    want = [(t, n, d) for t, n, d in INPUTS]
    script_in_harness = all(any("CR_HARNESS" in s for s in ctx[i]) for i, ln in enumerate(lines)
                            if re.match(r"\s*class\s+CRuleScript\b", ln))
    out = {"harness_defines_found": bad_def, "cr_xau_comm_pts": comm, "cr_brk_notional_x": notional, "inputs": inputs, "inputs_expected": want,
           "harness_only_inputs": stray, "subset_violations": subset, "script_rule_inside_cr_harness": script_in_harness}
    ok = (not bad_def and len(comm) == 1 and comm[0][1] == "6" and comm[0][2].startswith("#ifndef CR_XAU_COMM_PTS")
          and len(notional) == 1 and notional[0][1].split()[0] == "20.0" and notional[0][2].startswith("#ifndef CR_BRK_NOTIONAL_X")
          and inputs == want and sorted(n for _, n, _ in stray) == ["InpScript", "InpScriptDir"] and not subset and script_in_harness)
    res["constants"] = dict(out, pass_=ok)
    return ok


def builds(res):
    """5. the builds, 0 warnings each"""
    plan = {
        "harness": dict(entry=DIST, name="test_release_h"),
        "harness_san": dict(entry=DIST, name="test_release_h_san", sanitize=True),
        "release": dict(entry=DIST, name="test_release_rel", harness=False),
        "debug_release": dict(entry=DIST_DBG, name="test_release_dbg", harness=False),
        "release_no_guard": dict(entry=DIST, name="test_release_ng", harness=False, defines=["CR_NO_GUARD"]),
        "release_comm0": dict(entry=DIST, name="test_release_c0", harness=False, defines=["CR_XAU_COMM_PTS=0"]),
        "release_notional": dict(entry=DIST, name="test_release_nx", harness=False, defines=["CR_BRK_NOTIONAL_X=1000.0"]),
    }
    exe, warn = {}, {}
    for k, kw in plan.items():
        e, w = build(kw.pop("entry"), **kw)
        exe[k], warn[k] = e, len(w)
    res["builds"] = {"warnings": warn, "pass_": all(v == 0 for v in warn.values())}
    return exe


def bars():
    p = {s: os.path.join(HERE, "out", "bars", f"{s}_is.bin") for s in SYMS}
    if not all(os.path.exists(v) for v in p.values()):
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "export_frames.py"), "--tag", "is"], capture_output=True, text=True)
        if r.returncode:
            raise SystemExit("export_frames.py failed: " + r.stderr[-2000:])
    return p


def run_week(exe, name):
    files = os.path.join(OUT, name)
    env = {"MOCK_INPUT_InpTrade": "true", "MOCK_INPUT_InpPlanStart": str(calendar.timegm((2020, 6, 1, 0, 0, 0))),
           "MOCK_BALANCE": "100000", "MOCK_INPUT_InpPush": "false"}
    out, wall = replay(exe, files, bars(), env=env, frm=FROM, to=TO, timeout=1800)
    rows = compare.read_journal(files)
    ev = {}
    for r in rows:
        ev[r["ev"]] = ev.get(r["ev"], 0) + 1
    st = [r for r in rows if r["ev"] == "SELFTEST"]
    init = [r for r in rows if r["ev"] == "INIT" and "build" in r]
    plan = [r for r in rows if r["ev"] == "PLAN"]
    sizes = [r for r in rows if r["ev"] == "SIZE" and r.get("rp") != 1]
    # the journal's two outputs (review F9): Print goes to the mock's log, the file to MQL5/Files/ClaudeRobot
    printed = [ln for ln in open(os.path.join(files, "_mock", "log.txt")) if ln.startswith("CR|")]
    m = re.search(r"timer calls (\d+).*flushes (\d+)", out)
    return {"wall_s": round(wall, 2), "events": ev, "selftest": st[0] if st else None, "init": init[0] if init else None,
            "plan": plan[0] if plan else None, "live_size_skips": sorted({str(r.get("skip")) for r in sizes}), "sends": ev.get("SEND", 0),
            "bar_lines": ev.get("BAR", 0), "file_lines": len(rows), "file_rp_lines": sum(1 for r in rows if r.get("rp") == 1),
            "printed_lines": len(printed), "printed_rp_lines": sum(1 for ln in printed if ln.rstrip("\n").endswith("|rp=1")),
            "timer_calls": int(m.group(1)) if m else -1, "flushes": int(m.group(2)) if m else -1}


def corrupted_dist():
    """a copy of the dist file with one golden F1 score changed (its 1st digit after the point)"""
    d = os.path.join(WORK, "corrupt")
    os.makedirs(d, exist_ok=True)
    t = text(DIST).decode("ascii")
    m = re.search(r"^double CR_GOLD_F1\[\] = \{\n(.*?)\};", t, re.M | re.S)
    nums = re.findall(r"-?\d+\.\d+(?:e[-+]\d+)?", m.group(1))
    target = nums[15]                                           # the first vector's score (16 values per row)
    i = m.start(1) + m.group(1).index(target)
    j = i + target.index(".") + 1
    nd = "1" if t[j] != "1" else "2"
    t2 = t[:j] + nd + t[j + 1:]
    p = os.path.join(d, "ClaudeRobot.mq5")
    with open(p, "w", encoding="ascii", newline="\n") as f:
        f.write(t2)
    return p, target, t2[i:i + len(target)]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args(argv)
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(WORK, exist_ok=True)
    res = {}
    ok = check_released(res)
    ok &= check_constants(res)
    try:
        exe = builds(res)
        cp, was, now = corrupted_dist()
        exe["harness_golden_changed"], w = build(cp, name="test_release_bad")
        res["builds"]["warnings"]["harness_golden_changed"] = len(w)
    except BuildError as e:
        res["build_error"] = str(e)[-4000:]
        print(json.dumps(res, indent=1, default=str))
        return 1
    ok &= res["builds"]["pass_"] and len(w) == 0
    runs = {}
    runs["release"] = run_week(exe["release"], "release")
    runs["release_no_guard"] = run_week(exe["release_no_guard"], "release_no_guard")
    runs["release_comm0"] = run_week(exe["release_comm0"], "release_comm0")
    runs["release_notional"] = run_week(exe["release_notional"], "release_notional")
    runs["harness_golden_changed"] = run_week(exe["harness_golden_changed"], "harness_golden_changed")
    runs["debug_release"] = run_week(exe["debug_release"], "debug_release")
    runs["harness_golden_changed"]["changed"] = {"was": was, "now": now}
    g = lambda k, f: (runs[k]["selftest"] or {}).get(f)
    rel_init = runs["release"]["init"] or {}
    rel = runs["release"]
    checks = {
        "release_selftest_ok": g("release", "ok") == 1 and g("release", "golden") == golden_n() and golden_n() > 0
        and g("release", "why") in ("", None),
        "release_init_harness0_comm6": rel_init.get("harness") == 0 and rel_init.get("comm_pts") == 6,
        "release_default_plan_d2": rel_init.get("risk") == D2 and (rel["plan"] or {}).get("risk") == D2,
        "journal_print_no_rp_lines": rel["printed_lines"] > 0 and rel["printed_rp_lines"] == 0 and rel["file_rp_lines"] > 1000
        and rel["printed_lines"] == rel["file_lines"] - rel["file_rp_lines"],
        "journal_flush_once_per_pass": 0 < rel["flushes"] <= rel["timer_calls"] + 2 and rel["flushes"] < rel["file_lines"],
        "release_sends_orders": runs["release"]["sends"] > 0,
        "no_guard_blocked": g("release_no_guard", "ok") == 0 and "CR_NO_GUARD" in str(g("release_no_guard", "why"))
        and runs["release_no_guard"]["sends"] == 0 and "selftest" in runs["release_no_guard"]["live_size_skips"],
        "comm0_blocked": g("release_comm0", "ok") == 0 and "CR_XAU_COMM_PTS" in str(g("release_comm0", "why"))
        and runs["release_comm0"]["sends"] == 0,
        "notional_cap_changed_blocked": g("release_notional", "ok") == 0 and "CR_BRK_NOTIONAL_X" in str(g("release_notional", "why"))
        and runs["release_notional"]["sends"] == 0,
        "golden_changed_blocked": g("harness_golden_changed", "ok") == 0 and str(g("harness_golden_changed", "why")).startswith("golden f1_score 0:")
        and runs["harness_golden_changed"]["sends"] == 0,
        "debug_bar_dump": runs["debug_release"]["bar_lines"] > 1000 and g("debug_release", "ok") == 1,
    }
    res["runs"] = runs
    res["guard_checks"] = checks
    ok &= all(checks.values())
    res["sec"] = round(time.time() - t0, 1)
    res["pass"] = bool(ok)
    with open(os.path.join(OUT, "summary.json"), "w") as f:
        json.dump(res, f, indent=1, default=str)
    if not a.keep:
        shutil.rmtree(WORK, ignore_errors=True)
        for k in runs:
            shutil.rmtree(os.path.join(OUT, k), ignore_errors=True)
    print(f"released: {res['released']['pass_']} (CR_BUILD {res['released']['cr_build']}, dist = amalgam(src): "
          f"{res['released']['dist_is_current_src']}, {res['released']['src_files']} src files inlined once)")
    print(f"constants and inputs: {res['constants']['pass_']} ({len(res['constants']['inputs'])} inputs, "
          f"CR_XAU_COMM_PTS {res['constants']['cr_xau_comm_pts']}, subset violations {len(res['constants']['subset_violations'])})")
    print(f"builds: {res['builds']['warnings']}")
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'} {k}")
    for k, r in runs.items():
        s = r["selftest"] or {}
        print(f"  run {k}: SELFTEST ok={s.get('ok')} why={str(s.get('why'))[:90]!r} golden={s.get('golden')} SEND {r['sends']} "
              f"live skips {r['live_size_skips']} BAR {r['bar_lines']} ({r['wall_s']} s)")
    print(f"test_release: {'PASS' if ok else 'FAIL'} ({res['sec']} s)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
