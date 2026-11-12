"""Run the robot's tests (SPEC 8): every check/test_*.py and check/test_*.cpp, found by name; no step edits this file.

    python3 -I lab/robot/check/run_tests.py                 # everything
    python3 -I lab/robot/check/run_tests.py --only T1,T3    # by the tag of their first line (T1..T10, S0)
    python3 -I lab/robot/check/run_tests.py --list

A test's tag is the first word of its first line: the first word of a .py module docstring (T3 for a docstring that
starts "T3 paper: ..."; S0 for "S0: ..."), the first word of a .cpp's first comment ("// T3 paper: ..."). A test passes
when it exits with 0.
A .cpp test is built by check/build.py with its own main(); its first ten lines name what it compiles:
    // build: entry=src/CR_Paper.mqh [subst=CR_Clock.mqh=check/dbl/CR_Clock_dbl.mqh] [define=NAME=V] [sanitize]
(the entry is translated to ea.cpp, which the test includes after "mock_replay.h"). Each test's last 30 lines of
output and the summary go to check/out/tests/.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROBOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "out", "tests")
sys.path.insert(0, HERE)
TAG = re.compile(r"^\s*(?:\"\"\"|'''|//+|#)\s*([A-Z][A-Z0-9]*[0-9a-z]*)\b")


def tag_of(path):
    with open(path) as f:
        first = f.readline()
    m = TAG.match(first)
    return m.group(1) if m else "?"


def build_line(path):
    with open(path) as f:
        head = [next(f, "") for _ in range(10)]
    for ln in head:
        m = re.match(r"^\s*//\s*build:\s*(.*)$", ln)
        if m:
            opts = {"entry": None, "subst": [], "define": [], "sanitize": False}
            for tok in m.group(1).split():
                if tok == "sanitize":
                    opts["sanitize"] = True
                elif "=" in tok:
                    k, v = tok.split("=", 1)
                    if k in ("subst", "define"):
                        opts[k].append(v)
                    else:
                        opts[k] = v
            return opts
    return None


def run_one(path, timeout):
    t0 = time.time()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
               NUMBA_CACHE_DIR=os.environ.get("NUMBA_CACHE_DIR", "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/numba"))
    if path.endswith(".py"):
        cmd = [sys.executable, "-I", path]
    else:
        from build import BuildError, build
        b = build_line(path)
        if not b or not b["entry"]:
            return {"exit": 2, "out": "no '// build: entry=...' line in the first ten lines", "sec": 0.0}
        try:
            exe, warn = build(os.path.join(ROBOT, b["entry"]), name=os.path.splitext(os.path.basename(path))[0], main=path,
                              subst=[s if os.path.isabs(s.split("=", 1)[1]) else s.split("=", 1)[0] + "=" + os.path.join(ROBOT, s.split("=", 1)[1])
                                     for s in b["subst"]], defines=b["define"], sanitize=b["sanitize"])
        except BuildError as e:
            return {"exit": 3, "out": str(e)[-3000:], "sec": round(time.time() - t0, 1)}
        if warn:
            return {"exit": 4, "out": "warnings:\n" + "\n".join(warn[:20]), "sec": round(time.time() - t0, 1)}
        cmd = [exe]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, cwd=ROBOT)
        out, code = (r.stdout + r.stderr), r.returncode
    except subprocess.TimeoutExpired:
        out, code = f"timeout after {timeout} s", 124
    return {"exit": code, "out": "\n".join(out.splitlines()[-30:]), "sec": round(time.time() - t0, 1)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--timeout", type=int, default=3600)
    a = ap.parse_args(argv)
    tests = sorted(glob.glob(os.path.join(HERE, "test_*.py")) + glob.glob(os.path.join(HERE, "test_*.cpp")))
    want = set(a.only.split(",")) if a.only else None
    sel = [(p, tag_of(p)) for p in tests]
    sel = [(p, t) for p, t in sel if want is None or t in want]
    if a.list:
        for p, t in sel:
            print(f"{t:5s} {os.path.relpath(p, ROBOT)}")
        return 0
    os.makedirs(OUT, exist_ok=True)
    rows, ok = [], True
    for p, t in sel:
        r = run_one(p, a.timeout)
        name = os.path.basename(p)
        with open(os.path.join(OUT, name + ".log"), "w") as f:
            f.write(r["out"])
        passed = r["exit"] == 0
        ok &= passed
        rows.append({"test": name, "tag": t, "pass": passed, "exit": r["exit"], "sec": r["sec"]})
        print(f"{'PASS' if passed else 'FAIL'} {t:5s} {name:28s} {r['sec']:7.1f} s" + ("" if passed else f"  (exit {r['exit']})"))
        if not passed:
            print("   " + "\n   ".join(r["out"].splitlines()[-12:]))
    with open(os.path.join(OUT, "summary.json"), "w") as f:
        json.dump({"pass": ok, "tests": rows}, f, indent=1)
    print(f"run_tests: {sum(x['pass'] for x in rows)}/{len(rows)} passed")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
