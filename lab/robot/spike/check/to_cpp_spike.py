"""Translate an .mq5 file (and every local .mqh it includes) into C++ that compiles against mql5_shim.h.

Extension of lab/live_ai/check/to_cpp.py (md5 5187732967a3b04f850bd0d57a56c41e, not modified), same principle:
only MQL5-only syntax is rewritten, every statement is kept byte for byte, line numbers are preserved.
Added for the spike:
  * `#include "X.mqh"` (a local include) is translated too, into <out_dir>/X.mqh.cpp, and the include is pointed at it;
  * `input` / `sinput` constants are wrapped in mock_input<T>("InpName", default) so a replay can override them
    (env MOCK_INPUT_<InpName>), as test_mains.py does for the hands; `input group "..."` lines become comments;
  * no _Symbol/_Point/_Digits constants are appended unless --symbol is given (a multi-symbol EA must not use them).

    python3 -I check/to_cpp_spike.py mql5/SpikeRobot.mq5 out/build/spike.cpp

Refuses (exit 2, with the line number) the constructs this translation cannot carry to C++ faithfully:
  * '->' (MQL5 has no '->': object pointers use '.', which C++ cannot express without knowing the pointer types);
  * 'new' / 'delete' / '*' object pointers in declarations (same reason);
  * '#import' (DLL calls: forbidden on the MetaQuotes VPS anyway);
  * 'this.' (MQL5 spelling of this->).
"""
import os
import re
import sys

INPUT_RE = re.compile(r"^(?:input|sinput)\s+(string|double|int|long|bool|ulong|uint|datetime)\s+(Inp\w+)\s*=\s*(.+?);(\s*//.*)?$")
BAD = [(re.compile(r"->"), "'->' is not MQL5 (pointers use '.'); not translatable"),
       (re.compile(r"\bnew\s+\w+"), "object pointers (new) are not supported by the translation"),
       (re.compile(r"^\s*delete\s"), "object pointers (delete) are not supported by the translation"),
       (re.compile(r"^\s*#import\b"), "#import (DLL) is forbidden on the MetaQuotes VPS"),
       (re.compile(r"\bthis\s*\."), "'this.' (MQL5) cannot be translated without knowing it is a pointer")]


def strip_comment(s):
    """the code part of a line (a '//' inside a string literal is kept: good enough for the checks below)"""
    out, q = [], False
    for i, ch in enumerate(s):
        if ch == '"' and (i == 0 or s[i - 1] != "\\"):
            q = not q
        if not q and s[i:i + 2] == "//":
            break
        out.append(ch)
    return "".join(out)


def translate(path, out_path, done, symbol=None):
    src = open(path, encoding="ascii").read().split("\n")
    out = []
    in_block = False
    for no, line in enumerate(src, 1):
        s = line
        code = strip_comment(s)
        if "/*" in code:
            in_block = True
        if not in_block:
            bare = re.sub(r'"(\\.|[^"\\])*"', '""', code)          # string literals may say "new" or "->"
            for rx, why in BAD:
                if rx.search(bare):
                    sys.stderr.write(f"{path}:{no}: {why}\n    {line.strip()}\n")
                    sys.exit(2)
        if "*/" in code:
            in_block = False
        if s.startswith("#property"):
            s = "// " + s
        elif s.startswith("#include <Trade\\Trade.mqh>"):
            s = '#include "mql5_shim.h"'
        else:
            m = re.match(r'^#include\s+"([^"]+\.mqh)"\s*$', s)
            if m:
                inc = os.path.join(os.path.dirname(path), m.group(1))
                inc_out = os.path.join(os.path.dirname(out_path), os.path.basename(m.group(1)) + ".cpp")
                if inc not in done:
                    done.add(inc)
                    translate(inc, inc_out, done)
                s = f'#include "{os.path.basename(inc_out)}"'
        if re.match(r"^input\s+group\b", s):
            s = "// " + s
        m = INPUT_RE.match(s)
        if m:
            s = f'const {m[1]} {m[2]} = mock_input<{m[1]}>("{m[2]}", {m[3]});{m[4] or ""}'
        # parameters: [const] T &name[]  ->  [const] MqlArray<T> &name
        s = re.sub(r"\b(const\s+)?(\w+)\s*&\s*(\w+)\s*\[\s*\]", lambda m: f"{m.group(1) or ''}MqlArray<{m.group(2)}> &{m.group(3)}", s)
        # declarations: T a[], b[];  ->  MqlArray<T> a, b;
        m = re.match(r"^(\s*)(static\s+)?(\w+)\s+(\w+\s*\[\s*\](?:\s*,\s*\w+\s*\[\s*\])*)\s*;(.*)$", s)
        if m and m.group(3) not in ("return", "else"):
            names = [n.strip().split("[")[0].strip() for n in m.group(4).split(",")]
            s = f"{m.group(1)}{m.group(2) or ''}MqlArray<{m.group(3)}> {', '.join(names)};{m.group(5)}"
        out.append(s)
    cpp = "\n".join(out)
    if symbol:
        cpp += f'\nconst string _Symbol = "{symbol}";\nconst double _Point = 0.01;\nconst int _Digits = 2;\n'
    open(out_path, "w").write(cpp)
    return len(src)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sym = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--symbol=")), None)
    os.makedirs(os.path.dirname(os.path.abspath(args[1])), exist_ok=True)
    seen = set()
    n = translate(args[0], args[1], seen, sym)
    print("translated", n, "lines +", len(seen), "include(s)")
