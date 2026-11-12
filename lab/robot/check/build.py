"""Translate-and-compile helper (SPEC 1, 7): the robot (dist or src) or a test entry, against mql5_shim.h and the
replay mock, with the spec's flags: g++ -std=c++17 -O2 -ffp-contract=off (+ -fsanitize=address,undefined
-D_GLIBCXX_DEBUG for the sanitizer build). Harness builds always define CR_HARNESS and, unless told otherwise,
CR_XAU_COMM_PTS=0 (the exported spread already holds the gold commission, SPEC 7).

    python3 -I lab/robot/check/build.py dist [--sanitize] [--debug] [--define NAME[=V]] [--name X]
    python3 -I lab/robot/check/build.py src  [...]                 # the src tree, includes translated one by one
    python3 -I lab/robot/check/build.py <entry.mq5|.mqh|.cpp> [--main test.cpp] [--subst CR_Clock.mqh=<path>] [...]

dist: tools/amalgam.py first, then dist/ClaudeRobot.mq5 (--debug: dist/ClaudeRobot_debug.mq5) through to_cpp.py.
An .mqh entry with --main: the test's own main() (the .cpp includes "entry.cpp"; MOCK_REPLAY_NO_MAIN is defined).
Output: lab/robot/build/<name>/<exe>; prints the warnings; exit 1 on a compile error or (with --werror) a warning.
Python use: from build import build, replay.
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROBOT = os.path.dirname(HERE)
BUILD = os.path.join(ROBOT, "build")
CXX = ["g++", "-std=c++17", "-O2", "-ffp-contract=off", "-Wall", "-Wno-unused-function"]
SAN = ["-fsanitize=address,undefined", "-fno-sanitize-recover=undefined", "-D_GLIBCXX_DEBUG"]


class BuildError(RuntimeError):
    pass


def amalgam():
    r = subprocess.run([sys.executable, "-I", os.path.join(ROBOT, "tools", "amalgam.py")], capture_output=True, text=True)
    if r.returncode:
        raise BuildError("amalgam failed:\n" + r.stderr)
    return r.stdout


def translate(entry, out_cpp, subst=()):
    cmd = [sys.executable, "-I", os.path.join(HERE, "to_cpp.py"), entry, out_cpp]
    for s in subst:
        cmd += ["--subst", s]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise BuildError("to_cpp refused:\n" + r.stderr)
    return r.stdout.strip()


def build(entry="dist", name=None, defines=(), subst=(), sanitize=False, debug=False, main=None, harness=True,
          comm_pts=0, werror=False, quiet=True):
    """Returns (exe path, list of warning lines)."""
    if entry in ("dist", "src"):
        name = name or (entry + ("_debug" if debug else "") + ("_san" if sanitize else ""))
    else:
        name = name or os.path.splitext(os.path.basename(main or entry))[0] + ("_san" if sanitize else "")
    work = os.path.join(BUILD, name)
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)
    if entry == "dist":
        amalgam()
        src = os.path.join(ROBOT, "dist", "ClaudeRobot_debug.mq5" if debug else "ClaudeRobot.mq5")
    elif entry == "src":
        src = os.path.join(ROBOT, "src", "ClaudeRobot.mq5")
    else:
        src = os.path.abspath(entry)
    defs = list(defines)
    if harness:
        defs.append("CR_HARNESS")
        if not any(d.startswith("CR_XAU_COMM_PTS") for d in defs):
            defs.append(f"CR_XAU_COMM_PTS={comm_pts}")
    if src.endswith(".cpp"):
        ea = src
    else:
        ea = os.path.join(work, "ea.cpp")
        translate(src, ea, subst)
    run = os.path.join(work, "run.cpp")
    with open(run, "w") as f:
        if main:
            f.write("#define MOCK_REPLAY_NO_MAIN\n")
            f.write(f'#include "{os.path.abspath(main)}"\n')
        else:
            f.write('#include "mock_replay.h"\n')
            f.write(f'#include "{ea}"\n')
    exe = os.path.join(work, "replay")
    cmd = CXX + (SAN if sanitize else []) + [f"-D{d}" for d in defs] + ["-I", HERE, "-I", work, "-I", os.path.join(ROBOT, "src"),
                                                                       run, "-o", exe]
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True)
    warn = [ln for ln in r.stderr.splitlines() if "warning:" in ln]
    if r.returncode:
        raise BuildError(f"compile failed ({name}):\n" + r.stderr[-20000:])
    if not quiet:
        print(f"build: {exe}  {time.time() - t0:.1f} s  warnings {len(warn)}")
    if warn and werror:
        raise BuildError("warnings:\n" + "\n".join(warn))
    return exe, warn


def replay(exe, files, syms, env=None, fresh=True, frm=None, to=None, timeout=3600):
    """Run a replay binary. syms: {broker name: bar file}. Returns (stdout, seconds)."""
    if fresh and os.path.isdir(files):
        shutil.rmtree(files)
    os.makedirs(files, exist_ok=True)
    e = dict(os.environ, MOCK_FILES=str(files), MOCK_SYMS=",".join(syms), MOCK_QUIET="1")
    for k, v in syms.items():
        e[f"MOCK_BARS_{k}"] = str(v)
    if frm is not None:
        e["MOCK_FROM"] = str(int(frm))
    if to is not None:
        e["MOCK_TO"] = str(int(to))
    e.update({k: str(v) for k, v in (env or {}).items()})
    t0 = time.perf_counter()
    r = subprocess.run([exe], env=e, capture_output=True, text=True, timeout=timeout)
    wall = time.perf_counter() - t0
    if r.returncode:
        raise BuildError(f"replay failed ({r.returncode}): {r.stdout}\n{r.stderr[-5000:]}")
    return r.stdout.strip(), wall


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("entry")
    ap.add_argument("--name")
    ap.add_argument("--define", action="append", default=[])
    ap.add_argument("--subst", action="append", default=[])
    ap.add_argument("--sanitize", action="store_true")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--main")
    ap.add_argument("--release", action="store_true", help="no CR_HARNESS (the build the user gets)")
    ap.add_argument("--werror", action="store_true")
    a = ap.parse_args(argv)
    try:
        exe, warn = build(a.entry, a.name, a.define, a.subst, a.sanitize, a.debug, a.main, harness=not a.release,
                          werror=a.werror, quiet=False)
    except BuildError as e:
        sys.stderr.write(str(e) + "\n")
        return 1
    for w in warn:
        print(w)
    print(exe)
    return 0


if __name__ == "__main__":
    sys.exit(main())
