"""Tiny structural lint for an .mq5 file (no compiler available here):
1) strips comments / string / char literals, checks (), [], {} balance with line numbers;
2) for every StringFormat/PrintFormat call, counts % specifiers vs arguments.
Usage: python3 -I lint_mq5.py <file.mq5>
"""
import re
import sys

src = open(sys.argv[1], encoding="ascii").read()


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
                j += 2 if code[j] == "\\" else 1
            out.append(c + " " * (j - i - 1) + c); i = j + 1
        else:
            out.append(c); i += 1
    return "".join(out)


clean = strip(src)
pairs = {")": "(", "]": "[", "}": "{"}
stack, line = [], 1
ok = True
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


# StringFormat / PrintFormat argument counts (split top-level commas of the call)
def calls(name):
    for m in re.finditer(r"\b" + name + r"\s*\(", src):
        i = m.end(); depth = 1; j = i; in_s = False
        while depth:
            ch = src[j]
            if in_s:
                if ch == "\\": j += 1
                elif ch == '"': in_s = False
            elif ch == '"': in_s = True
            elif ch in "([{": depth += 1
            elif ch in ")]}": depth -= 1
            j += 1
        yield src.count("\n", 0, m.start()) + 1, src[i:j - 1]


def split_top(s):
    parts, depth, cur, in_s, k = [], 0, "", False, 0
    while k < len(s):
        ch = s[k]
        if in_s:
            cur += ch
            if ch == "\\": cur += s[k + 1]; k += 1
            elif ch == '"': in_s = False
        elif ch == '"': in_s = True; cur += ch
        elif ch in "([{": depth += 1; cur += ch
        elif ch in ")]}": depth -= 1; cur += ch
        elif ch == "," and depth == 0: parts.append(cur); cur = ""
        else: cur += ch
        k += 1
    parts.append(cur)
    return [p.strip() for p in parts]


spec = re.compile(r"%(?:%|[-+ 0#]*\d*(?:\.\d+)?(?:hh|h|ll|l|I32|I64)?[diouxXeEfgGcsS])")
for name in ("StringFormat", "PrintFormat"):
    for ln, body in calls(name):
        args = split_top(body)
        fmt = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', args[0]))
        n_spec = len([x for x in spec.findall(fmt) if x != "%%"])
        status = "OK" if n_spec == len(args) - 1 else "MISMATCH"
        print(f"{name} line {ln}: specifiers {n_spec} args {len(args) - 1} {status}")
