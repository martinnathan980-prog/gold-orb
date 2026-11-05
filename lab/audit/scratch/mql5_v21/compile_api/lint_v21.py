"""Structural lint for GoldOrb_Donchian4H.mq5 v2.10 (no MetaEditor here).
Checks: ASCII/CRLF, '//' comments ending in a backslash (line splice), bracket balance,
per-function brace depth, StringFormat/PrintFormat specifier count AND specifier/argument
type compatibility, Print/Alert argument counts (<= 64), declared identifiers vs MQL5
reserved words / builtin names, identifiers used but never declared (for manual review),
non-void functions whose last statement is not a return.
Usage: python3 -I lint_v21.py <file.mq5>
"""
import re
import sys

path = sys.argv[1]
raw = open(path, "rb").read()
print("bytes", len(raw), "non-ascii", sum(b > 127 for b in raw), "CR", raw.count(b"\r"), "TAB", raw.count(b"\t"))
src = raw.decode("ascii")
lines = src.split("\n")
for i, l in enumerate(lines, 1):
    s = l.rstrip()
    if "//" in s and s.endswith("\\"):
        print("LINE-SPLICE comment ends with backslash at line", i)


def strip(code):
    out, i, n = [], 0, len(code)
    while i < n:
        c = code[i]
        if code.startswith("//", i):
            j = code.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i)); i = j
        elif code.startswith("/*", i):
            j = code.find("*/", i + 2) + 2
            out.append("".join(ch if ch == "\n" else " " for ch in code[i:j])); i = j
        elif c in "\"'":
            j = i + 1
            while code[j] != c:
                if code[j] == "\n":
                    print("UNTERMINATED literal starting line", code.count("\n", 0, i) + 1)
                    break
                j += 2 if code[j] == "\\" else 1
            out.append(c + " " * (j - i - 1) + c); i = j + 1
        else:
            out.append(c); i += 1
    return "".join(out)


clean = strip(src)
pairs = {")": "(", "]": "[", "}": "{"}
stack, line, ok = [], 1, True
for ch in clean:
    if ch == "\n":
        line += 1
    elif ch in "([{":
        stack.append((ch, line))
    elif ch in ")]}":
        if not stack or stack[-1][0] != pairs[ch]:
            print(f"UNBALANCED {ch} at line {line}"); ok = False; break
        stack.pop()
if stack:
    print("UNCLOSED:", stack[-5:]); ok = False
print("brackets balanced" if ok else "bracket problem")

# top-level function definitions: brace depth must return to 0 at their end
TYPES = r"(?:void|int|uint|long|ulong|double|float|bool|string|datetime|char|uchar|short|ushort|color)"
funcs = {}
depth = 0
cl = clean.split("\n")
for i, l in enumerate(cl, 1):
    if depth == 0:
        m = re.match(r"\s*" + TYPES + r"\s+(\w+)\s*\(", l)
        if m:
            funcs.setdefault(m.group(1), []).append(i)
    depth += l.count("{") - l.count("}")
    if depth < 0:
        print("NEGATIVE depth at", i)
print("depth at EOF", depth)
dups = {k: v for k, v in funcs.items() if len(v) > 1}
print("functions defined/declared:", len(funcs), "multi:", dups)

# ---------- symbol table (very rough): name -> type -------------------------------------
decl_re = re.compile(r"\b(" + TYPES[3:-1] + r"|MqlTick|MqlRates|MqlDateTime|Bar4|GoState|CTrade|ENUM_\w+)\s+&?\s*(\w+)")
sym = {}
for m in decl_re.finditer(clean):
    t, name = m.group(1), m.group(2)
    sym.setdefault(name, set()).add(t)
# a, b, c in "double a, b, c;" lists
for m in re.finditer(r"\b(" + TYPES[3:-1] + r")\s+(\w+(?:\s*=\s*[^,;()]+)?(?:\s*,\s*\w+(?:\s*=\s*[^,;()]+)?)+)\s*;", clean):
    for part in m.group(2).split(","):
        nm = part.split("=")[0].strip()
        sym.setdefault(nm, set()).add(m.group(1))

RESERVED = set("""bool enum struct char float uchar class int uint color long ulong datetime short ushort double string void
const private protected public virtual extern input static break dynamic_cast return case else sizeof continue for switch
default if while delete new do operator false this template true typename interface override final namespace using
sinput group export""".split())
BUILTIN_SHORT = set("""abs fabs acos asin atan ceil cos exp floor fmax fmin fmod log log10 pow round sin sqrt tan
min max rand srand isnan""".split())
print("\n-- declared names that are reserved or builtin math aliases --")
for name, ts in sorted(sym.items()):
    if name in RESERVED or name in BUILTIN_SHORT:
        print("  ", name, ts)
for n in ("expiry", "exp", "tc", "sig", "vd", "q"):
    print("  check", n, "declared as", sym.get(n), "reserved" if n in RESERVED else "", "builtin-alias" if n in BUILTIN_SHORT else "")


# ---------- calls ------------------------------------------------------------------------
def calls(name, text=src):
    for m in re.finditer(r"(?<![\w.])" + name + r"\s*\(", text):
        if clean[m.start()] == " ":   # inside a comment/string in the cleaned copy
            continue
        i = m.end(); d = 1; j = i; in_s = False
        while d:
            ch = text[j]
            if in_s:
                if ch == "\\": j += 1
                elif ch == '"': in_s = False
            elif ch == '"': in_s = True
            elif ch in "([{": d += 1
            elif ch in ")]}": d -= 1
            j += 1
        yield text.count("\n", 0, m.start()) + 1, text[i:j - 1]


def split_top(s):
    parts, d, cur, in_s, k = [], 0, "", False, 0
    while k < len(s):
        ch = s[k]
        if in_s:
            cur += ch
            if ch == "\\": cur += s[k + 1]; k += 1
            elif ch == '"': in_s = False
        elif ch == '"': in_s = True; cur += ch
        elif ch in "([{": d += 1; cur += ch
        elif ch in ")]}": d -= 1; cur += ch
        elif ch == "," and d == 0: parts.append(cur); cur = ""
        else: cur += ch
        k += 1
    parts.append(cur)
    return [p.strip() for p in parts]


STR_FUNCS = ("DoubleToString", "TimeToString", "IntegerToString", "Clocks", "ResultRetcodeDescription", "EnumToString", "StringFormat")
INT_FIELDS = {"g.n_trades": "int", "g.week_n": "int", "n": "int", "g.side": "int"}
DBL_HINT = ("MathAbs", "InpStopATR", "g.trail", "g.real_D", "/ 3600.0", "R", "g.cum_R", "g.week_R", "vmin", "pct", "lots",
            "InpRiskPct", "vol")


def guess(a):
    a = a.strip()
    if a.startswith('"') or "?" in a and '"' in a:
        return "string"
    if any(a.startswith(f) or ("." + f) in a.split("(")[0] for f in STR_FUNCS) or a in ("_Symbol", "why", "m", "txt"):
        return "string"
    if a in INT_FIELDS:
        return INT_FIELDS[a]
    if a in ("t", "g.real_ticket"):
        return "ulong"
    if a in sym:
        return "/".join(sorted(sym[a]))
    if any(h in a for h in DBL_HINT):
        return "double"
    return "?"


spec = re.compile(r"%(?:%|[-+ 0#]*\d*(?:\.\d+)?(?:hh|h|ll|l|I32|I64)?[diouxXeEfgGcsS])")
print("\n-- StringFormat / PrintFormat --")
for name in ("StringFormat", "PrintFormat"):
    for ln, body in calls(name):
        args = split_top(body)
        fmt = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', args[0]))
        specs = [x for x in spec.findall(fmt) if x != "%%"]
        status = "OK" if len(specs) == len(args) - 1 else "COUNT-MISMATCH"
        print(f"{name} line {ln}: specifiers {len(specs)} args {len(args) - 1} {status}")
        for s, a in zip(specs, args[1:]):
            g = guess(a)
            conv = s[-1]
            bad = (conv == "s" and g not in ("string", "?")) or (conv in "fFeEgG" and g in ("string", "int", "ulong")) \
                or (conv in "diouxX" and g in ("string", "double")) or ("I64" in s and g not in ("ulong", "long", "?"))
            print(f"     {s:8s} <- {a[:70]:70s} [{g}]{'  <-- TYPE?' if bad else ''}")
print("\n-- Print / Alert arg counts --")
for name in ("Print", "Alert", "Comment"):
    for ln, body in calls(name):
        n = len(split_top(body))
        if n > 1:
            print(f"{name} line {ln}: {n} args{'  <-- >64' if n > 64 else ''}")

# ---------- identifiers used but never declared in the file -----------------------------------
words = set(re.findall(r"\b[A-Za-z_]\w*\b", clean))
declared = set(sym) | set(funcs) | {"GoState", "Bar4", "ENUM_GO_MODE", "ENUM_GO_TZ", "GO_ALERTS", "GO_MANAGE_MANUAL", "GO_AUTO",
                                    "GO_TZ_US", "GO_TZ_EU", "GO_TZ_FIXED"}
# struct fields
for m in re.finditer(r"\.\s*(\w+)", clean):
    declared.add(m.group(1))
for m in re.finditer(r"input\s+\w+\s+(\w+)", clean):
    declared.add(m.group(1))
undeclared = sorted(w for w in words - declared - RESERVED if not w[0].isdigit())
print("\n-- identifiers not declared in this file (must be MQL5/Trade.mqh builtins) --")
print(" ".join(undeclared))

# ---------- non-void functions: last statement before closing brace ------------------------------
print("\n-- non-void functions: final statement --")
for name, lns in funcs.items():
    ln = lns[-1]
    hdr = cl[ln - 1]
    if re.match(r"\s*void\b", hdr):
        continue
    # find body end
    d, started = 0, False
    for k in range(ln - 1, len(cl)):
        d += cl[k].count("{") - cl[k].count("}")
        if "{" in cl[k]:
            started = True
        if started and d == 0:
            body = "\n".join(cl[ln - 1:k + 1])
            stmts = [s.strip() for s in re.split(r";", body.rsplit("}", 1)[0]) if s.strip()]
            last = stmts[-1].split("\n")[-1].strip() if stmts else ""
            flag = "" if "return" in last else "  <-- no final return?"
            print(f"  {name:22s} line {ln:4d}-{k + 1:4d}: last stmt: {last[:60]}{flag}")
            break
