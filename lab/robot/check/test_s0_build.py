"""S0: the dist file builds; g++ and the sanitizer build compile every variant without a warning; the translator refuses
what the MQL5 subset bans.

    python3 -I lab/robot/check/test_s0_build.py

  * tools/amalgam.py writes dist/ClaudeRobot.mq5 and dist/ClaudeRobot_debug.mq5: pure ASCII, CR_BUILD = the 12 first hex
    digits of the sha256 of the body, every src file inlined once;
  * builds (g++ -std=c++17 -O2 -ffp-contract=off -Wall): dist (harness), dist debug, src (includes one by one), release
    (no CR_HARNESS: the file the user gets), dist under -fsanitize=address,undefined -D_GLIBCXX_DEBUG: 0 warnings each;
  * the dist file defines no harness constant: no '#define CR_HARNESS', no '#define CR_NO_GUARD', and CR_XAU_COMM_PTS
    only as the '#ifndef' default 6;
  * to_cpp.py refuses '->', 'new', 'template <', 'virtual', Sleep(), fmax()/fmin(), a function-like macro, an enum input
    and a string literal + a string literal (exit 2).
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROBOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from build import BuildError, build  # noqa: E402

BANNED = {"arrow": "void f() { g->x = 1; }", "new": "void f() { CFoo *p = new CFoo; }", "template": "template <typename T> T f(T x) { return x; }",
          "virtual": "class A { virtual void f() {} };", "sleep": "void f() { Sleep(10); }", "macro": "#define SQ(x) ((x) * (x))",
          "enum_input": "input ENUM_TIMEFRAMES InpTf = PERIOD_M1;", "lit_plus_lit": 'string s = "a" + "b";',
          "fmax": "double f(double a, double b) { return fmax(a, b); }"}


def main():
    res = {}
    r = subprocess.run([sys.executable, "-I", os.path.join(ROBOT, "tools", "amalgam.py")], capture_output=True, text=True)
    res["amalgam"] = r.stdout.strip().splitlines()
    ok = r.returncode == 0
    for name in ("ClaudeRobot.mq5", "ClaudeRobot_debug.mq5"):
        raw = open(os.path.join(ROBOT, "dist", name), "rb").read()
        first, body = raw.split(b"\n", 1)
        m = re.match(rb'#define CR_BUILD "([0-9a-f]{12})"', first)
        ascii_ok = all(b < 128 for b in raw)
        sha_ok = bool(m) and hashlib.sha256(body).hexdigest()[:12] == m.group(1).decode()
        res[name] = {"bytes": len(raw), "ascii": ascii_ok, "cr_build_matches_sha256": sha_ok}
        ok &= ascii_ok and sha_ok
    dist = open(os.path.join(ROBOT, "dist", "ClaudeRobot.mq5")).read()
    srcs = sorted(f for f in os.listdir(os.path.join(ROBOT, "src")) if f.endswith((".mqh", ".mq5")))
    inl = {f: dist.count(f"// ==== begin src/{f}") for f in srcs}
    res["src_files_inlined_once"] = all(v == 1 for v in inl.values())
    ok &= res["src_files_inlined_once"]
    no_harness = (re.search(r"^\s*#define\s+CR_HARNESS\b", dist, re.M) is None and re.search(r"^\s*#define\s+CR_NO_GUARD\b", dist, re.M) is None
                  and re.findall(r"^\s*#define\s+CR_XAU_COMM_PTS\s+(\S+)", dist, re.M) == ["6"])
    res["dist_defines_no_harness_constant"] = no_harness
    ok &= no_harness
    builds = {}
    for label, kw in (("dist", {}), ("dist_debug", {"debug": True}), ("src", {"entry": "src"}),
                      ("release", {"harness": False, "name": "dist_release"}), ("sanitizer", {"sanitize": True})):
        entry = kw.pop("entry", "dist")
        try:
            exe, warn = build(entry, **kw)
            builds[label] = {"ok": True, "warnings": len(warn), "first_warnings": warn[:3]}
            ok &= len(warn) == 0
        except BuildError as e:
            builds[label] = {"ok": False, "error": str(e)[-1500:]}
            ok = False
    res["builds"] = builds
    refused = {}
    with tempfile.TemporaryDirectory() as d:
        for k, code in BANNED.items():
            p = os.path.join(d, f"{k}.mq5")
            with open(p, "w") as f:
                f.write(code + "\n")
            r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "to_cpp.py"), p, os.path.join(d, f"{k}.cpp")],
                               capture_output=True, text=True)
            refused[k] = r.returncode == 2
    res["translator_refuses"] = refused
    ok &= all(refused.values())
    res["pass"] = bool(ok)
    print(json.dumps(res, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
