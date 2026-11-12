"""Translate an .mq5 file (and every local .mqh it includes) into C++ that compiles against mql5_shim.h.

Extension of lab/robot/spike/check/to_cpp_spike.py (itself an extension of lab/live_ai/check/to_cpp.py). Same principle:
only MQL5-only syntax is rewritten, every statement is kept byte for byte, line numbers are preserved (one output line
per input line), so a compiler message points at the MQL5 line.

    python3 -I check/to_cpp.py <entry.mq5|.mqh> <out.cpp> [--subst NAME=PATH ...] [--symbol=X]

  * `#include "X.mqh"` is translated too, into <out_dir>/X.mqh.cpp, and the include is pointed at it; --subst
    CR_Clock.mqh=check/dbl/CR_Clock_dbl.mqh translates another file in place of an include of that name (the wave-1
    tests use the table-driven clock double, SPEC 8);
  * `#include <Trade\\Trade.mqh>` becomes `#include "mql5_shim.h"`; `#property` lines become comments;
  * `input` / `sinput` constants of a plain type (bool, int, long, double, string, datetime, uint, ulong) become
    `const T Name = mock_input<T>("Name", default);` so a replay can override them (env MOCK_INPUT_<Name>);
  * dynamic arrays: declarations `T a[];` and parameters `T &a[]` become MqlArray<T>; an unsized array with an
    initializer `T a[] = {...};` (a constant table, possibly over several lines) becomes `MqlArray<T> a = {{...}};` so
    that it can be passed to an array parameter as in MQL5; fixed-size arrays `T a[N]` stay C arrays (so the robot
    never passes a fixed-size array to an array parameter);
  * no _Symbol/_Point/_Digits unless --symbol is given (a multi-symbol EA must not use them).

Refuses (exit 2, with the line) what this translation cannot carry faithfully or what the MQL5 subset of SPEC 1 bans:
'->', 'new', 'delete', 'this.', '#import', 'virtual', 'template <', function-like macros, Sleep(), fmax()/fmin() (NaN rules
differ between C++ and MQL5), an input of another
type (enum inputs), and a string literal directly followed by '+' and another string literal (pointer arithmetic in
C++, concatenation in MQL5).
"""
import os
import re
import sys

PLAIN = "string|double|int|long|bool|ulong|uint|datetime"
INPUT_RE = re.compile(r"^(?:input|sinput)\s+(" + PLAIN + r")\s+(Inp\w+)\s*=\s*(.+?);(\s*//.*)?$")
INPUT_ANY = re.compile(r"^\s*(?:input|sinput)\s+(?!group\b)")
BAD = [(re.compile(r"->"), "'->' is not MQL5 (pointers use '.'); not translatable"),
       (re.compile(r"\bnew\s+\w+"), "object pointers (new) are not supported by the translation"),
       (re.compile(r"^\s*delete\s"), "object pointers (delete) are not supported by the translation"),
       (re.compile(r"^\s*#import\b"), "#import (DLL) is forbidden on the MetaQuotes VPS"),
       (re.compile(r"\bthis\s*\."), "'this.' (MQL5) cannot be translated without knowing it is a pointer"),
       (re.compile(r"\bvirtual\b"), "virtual functions are outside the MQL5 subset (SPEC 1)"),
       (re.compile(r"\btemplate\s*<"), "templates are outside the MQL5 subset (SPEC 1)"),
       (re.compile(r"^\s*#define\s+\w+\("), "function-like macros are outside the MQL5 subset (SPEC 1)"),
       (re.compile(r"\bSleep\s*\("), "Sleep() is outside the MQL5 subset (SPEC 1)"),
       (re.compile(r"\bf(max|min)\s*\("), "fmax/fmin: C++ takes std::fmax (NaN ignored), MQL5 its own; write the comparison out")]
LIT_PLUS_LIT = re.compile(r'"(?:\\.|[^"\\])*"\s*\+\s*"')
TABLE_RE = re.compile(r"^(\s*)((?:static\s+|const\s+)*)(\w+)\s+(\w+)\s*\[\s*\]\s*=\s*\{(.*)$")


def strip_comment(s):
    """the code part of a line (a '//' inside a string literal is kept)"""
    out, q = [], False
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == '"' and (i == 0 or s[i - 1] != "\\"):
            q = not q
        if not q and s[i:i + 2] == "//":
            break
        out.append(ch)
        i += 1
    return "".join(out)


def parse_subst(args):
    sub = {}
    for a in args:
        k, v = a.split("=", 1)
        sub[k] = os.path.abspath(v)
    return sub


def translate(path, out_path, done, subst, symbol=None):
    src = open(path, encoding="ascii").read().split("\n")
    out = []
    in_block = False
    table_open = False                          # inside a multi-line `T a[] = {` initializer
    for no, line in enumerate(src, 1):
        s = line
        if table_open:
            if "};" in s:
                s = s.replace("};", "}};", 1)
                table_open = False
            out.append(s)
            continue
        mt = TABLE_RE.match(s)
        if mt and not s.lstrip().startswith("//"):
            head = f"{mt.group(1)}{mt.group(2) or ''}MqlArray<{mt.group(3)}> {mt.group(4)} = {{{{"
            rest = mt.group(5)
            if "};" in rest:
                out.append(head + rest.replace("};", "}};", 1))
            else:
                out.append(head + rest)
                table_open = True
            continue
        code = strip_comment(s)
        if "/*" in code and "*/" not in code:
            in_block = True
        if not in_block:
            if LIT_PLUS_LIT.search(code):
                sys.stderr.write(f"{path}:{no}: a string literal + a string literal is pointer arithmetic in C++\n    {line.strip()}\n")
                sys.exit(2)
            bare = re.sub(r'"(\\.|[^"\\])*"', '""', code)          # string literals may say "new" or "->"
            for rx, why in BAD:
                if rx.search(bare):
                    sys.stderr.write(f"{path}:{no}: {why}\n    {line.strip()}\n")
                    sys.exit(2)
            if INPUT_ANY.match(code) and not INPUT_RE.match(s.strip()):
                sys.stderr.write(f"{path}:{no}: only plain-typed inputs ({PLAIN.replace('|', ', ')}) are allowed\n    {line.strip()}\n")
                sys.exit(2)
        elif "*/" in code:
            in_block = False
        if s.startswith("#property"):
            s = "// " + s
        elif re.match(r"^\s*#include\s+<Trade\\Trade\.mqh>", s):
            s = '#include "mql5_shim.h"'
        else:
            m = re.match(r'^\s*#include\s+"([^"]+\.mqh)"\s*(//.*)?$', s)
            if m:
                name = os.path.basename(m.group(1))
                inc = subst.get(name, os.path.join(os.path.dirname(path), m.group(1)))
                inc_out = os.path.join(os.path.dirname(out_path), name + ".cpp")
                if name not in done:
                    done.add(name)
                    translate(inc, inc_out, done, subst)
                s = f'#include "{name}.cpp"'
        if re.match(r"^\s*input\s+group\b", s):
            s = "// " + s
        m = INPUT_RE.match(s.strip())
        if m:
            s = f'const {m[1]} {m[2]} = mock_input<{m[1]}>("{m[2]}", {m[3]});{m[4] or ""}'
        # parameters: [const] T &name[]  ->  [const] MqlArray<T> &name
        s = re.sub(r"\b(const\s+)?(\w+)\s*&\s*(\w+)\s*\[\s*\]", lambda q: f"{q.group(1) or ''}MqlArray<{q.group(2)}> &{q.group(3)}", s)
        # declarations: T a[], b[];  ->  MqlArray<T> a, b;
        m = re.match(r"^(\s*)(static\s+)?(\w+)\s+(\w+\s*\[\s*\](?:\s*,\s*\w+\s*\[\s*\])*)\s*;(.*)$", s)
        if m and m.group(3) not in ("return", "else"):
            names = [n.strip().split("[")[0].strip() for n in m.group(4).split(",")]
            s = f"{m.group(1)}{m.group(2) or ''}MqlArray<{m.group(3)}> {', '.join(names)};{m.group(5)}"
        out.append(s)
    cpp = "\n".join(out)
    if symbol:
        cpp += f'\nconst string _Symbol = "{symbol}";\nconst double _Point = 0.01;\nconst int _Digits = 2;\n'
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(cpp)
    return len(src)


def main(argv):
    pos = [a for a in argv if not a.startswith("--")]
    sym = next((a.split("=", 1)[1] for a in argv if a.startswith("--symbol=")), None)
    subst = parse_subst([argv[i + 1] for i, a in enumerate(argv) if a == "--subst"])
    pos = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] != "--subst")]
    if len(pos) != 2:
        sys.stderr.write(__doc__)
        return 2
    seen = set()
    n = translate(pos[0], pos[1], seen, subst, sym)
    print(f"to_cpp: {n} lines + {len(seen)} include(s) -> {pos[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
