"""Build the single file the user installs: dist/ClaudeRobot.mq5 (and dist/ClaudeRobot_debug.mq5).

    python3 -I lab/robot/tools/amalgam.py            # from anywhere; writes lab/robot/dist/

What it does (SPEC 1, "Single file"):
  * starts from src/ClaudeRobot.mq5 and inlines every local `#include "X.mqh"` recursively, in order, once each
    (a file already inlined is skipped: its include guard would skip it anyway);
  * keeps `#include <Trade\\Trade.mqh>` (once) and every other line as it is (#property, #ifndef/#define constants,
    include guards, #ifdef CR_HARNESS blocks);
  * refuses a non-ASCII byte, a local include that cannot be found, and a file first inlined inside a conditional
    block (#if...) that is later included outside one (its text would then be missing from some builds);
  * writes dist/ClaudeRobot.mq5 with `#define CR_BUILD "<12 hex>"` on its first line, the 12 first hex digits of the
    sha256 of everything below that line, and dist/ClaudeRobot_debug.mq5 = the same text with `#define CR_DEBUG`
    (aggregate lines, bar dump) and its own CR_BUILD.
Prints the sha256, the line count and the inlined files. Exit 2 on a refusal.
"""
import argparse
import hashlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROBOT = os.path.dirname(HERE)
INC_LOCAL = re.compile(r'^\s*#include\s+"([^"]+)"\s*(//.*)?$')
INC_SYS = re.compile(r'^\s*#include\s+<([^>]+)>\s*(//.*)?$')
COND_OPEN = re.compile(r"^\s*#\s*(if|ifdef|ifndef)\b")
COND_CLOSE = re.compile(r"^\s*#\s*endif\b")


class Refused(Exception):
    pass


def check_ascii(path, raw):
    for no, line in enumerate(raw.split(b"\n"), 1):
        for col, ch in enumerate(line, 1):
            if ch > 127:
                raise Refused(f"{path}:{no}:{col}: non-ASCII byte 0x{ch:02x} (the EA must be pure ASCII)")


def inline(path, out, state, depth_cond):
    raw = open(path, "rb").read()
    check_ascii(path, raw)
    text = raw.decode("ascii").replace("\r\n", "\n")
    base = os.path.dirname(path)
    cond = 0                                    # conditional depth inside this file
    out.append(f"// ==== begin {os.path.relpath(path, ROBOT)}")
    for no, line in enumerate(text.split("\n"), 1):
        m = INC_LOCAL.match(line)
        if m:
            inc = os.path.normpath(os.path.join(base, m.group(1)))
            if not os.path.exists(inc):
                raise Refused(f"{path}:{no}: local include not found: {m.group(1)}")
            inside = (depth_cond + cond) > 0
            if inc in state["done"]:
                if state["cond_first"].get(inc) and not inside:
                    raise Refused(f"{path}:{no}: {m.group(1)} was first inlined inside a conditional block and is "
                                  f"needed outside one here")
                out.append(f"// (already inlined: {m.group(1)})")
                continue
            state["done"].add(inc)
            state["order"].append(os.path.relpath(inc, ROBOT))
            state["cond_first"][inc] = inside
            inline(inc, out, state, depth_cond + cond)
            continue
        m = INC_SYS.match(line)
        if m:
            if m.group(1) in state["sys"]:
                out.append(f"// (already included: <{m.group(1)}>)")
                continue
            state["sys"].add(m.group(1))
        if COND_OPEN.match(line):
            cond += 1
        elif COND_CLOSE.match(line):
            cond -= 1
        out.append(line)
    if cond != 0:
        raise Refused(f"{path}: unbalanced #if/#endif ({cond:+d})")
    out.append(f"// ==== end {os.path.relpath(path, ROBOT)}")


def build(src, extra_define=None):
    state = {"done": {os.path.normpath(src)}, "order": [os.path.relpath(src, ROBOT)], "sys": set(), "cond_first": {}}
    out = []
    if extra_define:
        out.append(f"#define {extra_define}")
    inline(os.path.normpath(src), out, state, 0)
    body = "\n".join(out).rstrip("\n") + "\n"
    sha = hashlib.sha256(body.encode("ascii")).hexdigest()
    text = f'#define CR_BUILD "{sha[:12]}"\n' + body
    return text, sha, state["order"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(ROBOT, "src", "ClaudeRobot.mq5"))
    ap.add_argument("--out", default=os.path.join(ROBOT, "dist"))
    a = ap.parse_args(argv)
    try:
        rel, sha, order = build(a.src)
        dbg, sha_d, _ = build(a.src, "CR_DEBUG")
    except Refused as e:
        sys.stderr.write(f"amalgam: REFUSED: {e}\n")
        return 2
    os.makedirs(a.out, exist_ok=True)
    p_rel = os.path.join(a.out, "ClaudeRobot.mq5")
    p_dbg = os.path.join(a.out, "ClaudeRobot_debug.mq5")
    with open(p_rel, "w", encoding="ascii", newline="\n") as f:
        f.write(rel)
    with open(p_dbg, "w", encoding="ascii", newline="\n") as f:
        f.write(dbg)
    print(f"amalgam: {p_rel}  CR_BUILD {sha[:12]}  sha256(body) {sha}  {rel.count(chr(10))} lines")
    print(f"amalgam: {p_dbg}  CR_BUILD {sha_d[:12]}  {dbg.count(chr(10))} lines")
    print("amalgam: inlined " + ", ".join(order))
    return 0


if __name__ == "__main__":
    sys.exit(main())
