"""Translate GoldOrb_Donchian4H.mq5 into C++ for a g++ -fsyntax-only check against mql5_shim.h.
Only MQL5-only syntax is rewritten (dynamic arrays 'T a[]', 'input', '#property', the Trade include);
every statement, call and expression is left byte-for-byte as written, and line numbers are preserved.
Usage: python3 -I to_cpp.py <in.mq5> <out.cpp>
"""
import re
import sys

src = open(sys.argv[1], encoding="ascii").read().split("\n")
out = []
for line in src:
    s = line
    if s.startswith("#property"):
        s = "// " + s
    elif s.startswith("#include <Trade\\Trade.mqh>"):
        s = '#include "mql5_shim.h"'
    s = re.sub(r"^input\s", "const ", s)
    # parameters: [const] T &name[]  ->  [const] MqlArray<T> &name
    s = re.sub(r"\b(const\s+)?(\w+)\s*&\s*(\w+)\s*\[\s*\]", lambda m: f"{m.group(1) or ''}MqlArray<{m.group(2)}> &{m.group(3)}", s)
    # declarations: T a[], b[];  ->  MqlArray<T> a, b;
    m = re.match(r"^(\s*)(static\s+)?(\w+)\s+(\w+\s*\[\s*\](?:\s*,\s*\w+\s*\[\s*\])*)\s*;(.*)$", s)
    if m and m.group(3) not in ("return", "else"):
        names = [n.strip().split("[")[0].strip() for n in m.group(4).split(",")]
        s = f"{m.group(1)}{m.group(2) or ''}MqlArray<{m.group(3)}> {', '.join(names)};{m.group(5)}"
    out.append(s)
cpp = "\n".join(out)
cpp += "\nconst string _Symbol = \"XAUUSD\";\nconst double _Point = 0.01;\nconst int _Digits = 2;\n"
open(sys.argv[2], "w").write(cpp)
print("translated", len(src), "lines")
