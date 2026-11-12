"""Read the robot's journal and compare it with the lab references (SPEC 2.6, 7).

    python3 -I lab/robot/check/compare.py parse  <MOCK_FILES dir | journal dir | .log>
    python3 -I lab/robot/check/compare.py orders <MOCK_FILES dir> <script csv> [--code BKB] [--from UTC] [--to UTC]
    python3 -I lab/robot/check/compare.py trades <MOCK_FILES dir> <ref trades.parquet> --code BKB [--from UTC] [--to UTC]

Journal line: CR|<utc>|<EVENT>|<code>|k=v|... (utc integer seconds; doubles DoubleToString(x, -16), an exact round trip).
Tolerances (SPEC 7): times, sides, reasons, counts and prices taken from bars are compared for equality; prices built on
rolling, Wilder or score values to 1e-12 relative (--rel); trades still open at the end of the replay are left out.
Python use: read_journal, events, check_parsable, cmp_orders, paper_trades, cmp_trades.
"""
import argparse
import glob
import json
import math
import os
import re
import sys

import numpy as np
import pandas as pd

LINE = re.compile(r"^CR\|(-?\d+)\|([A-Z0-9]+)\|([^|]*)((?:\|[A-Za-z0-9_.]+=[^|]*)*)$")
EVENTS = {"INIT", "SELFTEST", "PLAN", "READY", "NOTREADY", "DEC", "PFILL", "PEXIT", "PSTOP", "PREVISE", "PVOID", "PREFUSE", "HOLD",
          "SIZE", "SEND", "FILL", "SLMOD", "SLFIX", "CLOSE", "REFUSED", "ADOPT", "ORPHAN", "DUP", "MISSED", "LATEBAR", "GAP",
          "REBUILD", "SETTLE", "CLOCK", "STOP", "GUARD", "MARK", "LOCK", "COST", "TAKEOVER", "WATCH", "ERROR", "AGG", "DAY", "BAR"}
# DEC (what=ord) keys -> CrOrder / script columns
DEC_KEYS = {"oid": "oid", "side": "side", "et": "etype", "lv": "level", "lv2": "level2", "tf": "t_from", "tt": "t_to",
            "ax": "after_exit_of", "exp": "expiry_excl", "st": "stop", "sd": "stop_dist", "tr": "trail", "be": "be", "tg": "target",
            "td": "target_dist", "x": "x_sched", "xg": "x_gap", "xh": "xh", "xr": "xh_r", "ref": "refuse", "vle": "void_le",
            "grp": "group"}
FLOAT_COLS = {"level", "level2", "stop", "stop_dist", "trail", "be", "target", "target_dist", "xh_r"}
REASONS = ("stop", "target", "time", "trail", "eod", "nofill", "skip", "gap", "void", "refused", "rule")


def journal_files(path):
    if os.path.isfile(path):
        return [path]
    for sub in ("ClaudeRobot", ""):
        fs = sorted(glob.glob(os.path.join(path, sub, "*.log")))
        if fs:
            return fs
    return []


def num(v):
    """a journal value: int, float (NaN accepted in any spelling) or the text"""
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        low = v.lower()
        if "nan" in low:
            return math.nan
        if "inf" in low:
            return -math.inf if low.startswith("-") else math.inf
        return v


def read_journal(path):
    """every line of the journal as a dict: utc, ev, code and the k=v fields (numbers parsed); bad lines raise"""
    rows, bad = [], []
    for f in journal_files(path):
        with open(f) as h:
            for no, ln in enumerate(h, 1):
                ln = ln.rstrip("\n")
                if not ln:
                    continue
                m = LINE.match(ln)
                if not m or m.group(2) not in EVENTS:
                    bad.append(f"{os.path.basename(f)}:{no}: {ln[:200]}")
                    continue
                d = {"utc": int(m.group(1)), "ev": m.group(2), "code": m.group(3)}
                for kv in m.group(4).split("|")[1:]:
                    k, v = kv.split("=", 1)
                    d[k] = num(v)
                rows.append(d)
    if bad:
        raise ValueError(f"{len(bad)} unparsable journal line(s), first: {bad[0]}")
    return rows


def events(rows, ev, code=None, live_only=False):
    x = [r for r in rows if r["ev"] == ev and (code is None or r["code"] == code) and not (live_only and r.get("rp") == 1)]
    return pd.DataFrame(x)


def check_parsable(path):
    rows = read_journal(path)
    counts = {}
    for r in rows:
        counts[r["ev"]] = counts.get(r["ev"], 0) + 1
    return {"files": len(journal_files(path)), "lines": len(rows), "events": dict(sorted(counts.items()))}


def same_value(a, b, col, rel=0.0):
    if col in FLOAT_COLS:
        a, b = float(a), float(b)
        if math.isnan(a) and math.isnan(b):
            return True
        if a == b:
            return True
        return rel > 0 and abs(a - b) <= rel * max(abs(a), abs(b))
    return int(a) == int(b)


def cmp_orders(rows, script_csv, code, t_from=None, t_to=None, rel=0.0):
    """DEC lines (what=ord) of one sleeve against the CrOrder rows ref_lab.py wrote (equal field by field)"""
    ref = pd.read_csv(script_csv, dtype=str)
    for c in ref.columns:
        ref[c] = ref[c].map(num)
    if t_from is not None:
        ref = ref[ref.emit >= t_from]
    if t_to is not None:
        ref = ref[ref.emit <= t_to]
    dec = [r for r in rows if r["ev"] == "DEC" and r["code"] == code and r.get("what") == "ord"]
    by_oid = {}
    dup = 0
    for r in dec:
        dup += r["oid"] in by_oid
        by_oid[r["oid"]] = r
    missing, wrong, ok = [], [], 0
    for _, q in ref.iterrows():
        r = by_oid.pop(int(q.oid), None)
        if r is None:
            missing.append(int(q.oid))
            continue
        bad = [c for k, c in DEC_KEYS.items() if not same_value(r[k], q[c], c, rel)]
        if r["utc"] != int(q.dec):
            bad.append("dec")
        if r["at"] != int(q.emit):
            bad.append("emit")
        if bad:
            wrong.append({"oid": int(q.oid), "fields": bad})
        else:
            ok += 1
    extra = sorted(by_oid)
    return {"code": code, "ref_orders": int(len(ref)), "dec_lines": len(dec), "equal": ok, "missing": missing[:20],
            "n_missing": len(missing), "wrong": wrong[:20], "n_wrong": len(wrong), "extra": extra[:20], "n_extra": len(extra),
            "duplicates": dup, "pass": len(missing) == 0 and len(wrong) == 0 and len(extra) == 0 and dup == 0}


def paper_trades(rows, code, live_only=False):
    """PFILL + PEXIT (and PREVISE, which replaces the exit) of one sleeve joined by oid: one row per paper trade"""
    fills = {r["oid"]: r for r in rows if r["ev"] == "PFILL" and r["code"] == code and not (live_only and r.get("rp") == 1)}
    out = []
    for r in rows:
        if r["code"] != code or r["ev"] not in ("PEXIT", "PREVISE") or r["oid"] not in fills or (live_only and r.get("rp") == 1):
            continue
        f = fills[r["oid"]]
        out.append({"oid": r["oid"], "side": f["side"], "entry_time": pd.Timestamp(f["utc"], unit="s", tz="UTC"),
                    "entry": f["px"], "stop": f["st0"], "exit_time": pd.Timestamp(r["utc"], unit="s", tz="UTC"), "exit": r["px"],
                    "reason": r.get("reason"), "revised": r["ev"] == "PREVISE"})
    t = pd.DataFrame(out)
    if len(t):
        t = t.sort_values(["entry_time", "revised"]).drop_duplicates("oid", keep="last").reset_index(drop=True)
    return t


def cmp_trades(rows, ref, code, t_from=None, t_to=None, rel=1e-12):
    """paper trades of the journal against lab trades: entry/exit minute, side and reason equal; prices equal or within
    rel (stops built on rolling values)"""
    ea = paper_trades(rows, code)
    lab = ref.copy()
    if t_from is not None:
        lab = lab[lab.entry_time >= pd.Timestamp(t_from, unit="s", tz="UTC")]
        ea = ea[ea.entry_time >= pd.Timestamp(t_from, unit="s", tz="UTC")] if len(ea) else ea
    if t_to is not None:
        lab = lab[lab.exit_time <= pd.Timestamp(t_to, unit="s", tz="UTC")]
    if not len(ea):
        return {"code": code, "lab_trades": int(len(lab)), "ea_trades": 0, "pass": len(lab) == 0}
    m = lab.merge(ea, on=["entry_time", "side"], how="outer", suffixes=("_lab", "_ea"), indicator=True)
    both = m[m._merge == "both"]
    same_exit = (both.exit_time_lab == both.exit_time_ea) & (both.reason_lab == both.reason_ea)
    res = {"code": code, "lab_trades": int(len(lab)), "ea_trades": int(len(ea)), "same_entry": int(len(both)),
           "only_lab": int((m._merge == "left_only").sum()), "only_ea": int((m._merge == "right_only").sum()),
           "same_exit_and_reason": int(same_exit.sum())}
    s = both[same_exit]
    for c in ("entry", "stop", "exit"):
        d = (s[f"{c}_lab"] - s[f"{c}_ea"]).abs()
        tol = rel * s[f"{c}_lab"].abs()
        res[f"{c}_equal"] = int((d == 0).sum())
        res[f"{c}_within_rel"] = int((d <= tol).sum())
    res["pass"] = res["only_lab"] == 0 and res["only_ea"] == 0 and res["same_exit_and_reason"] == len(both) and \
        res["entry_within_rel"] == len(s) and res["exit_within_rel"] == len(s)
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["parse", "orders", "trades"])
    ap.add_argument("journal")
    ap.add_argument("ref", nargs="?")
    ap.add_argument("--code")
    ap.add_argument("--from", dest="t_from", type=int)
    ap.add_argument("--to", dest="t_to", type=int)
    ap.add_argument("--rel", type=float, default=0.0)
    a = ap.parse_args(argv)
    if a.what == "parse":
        r = check_parsable(a.journal)
    elif a.what == "orders":
        code = a.code or os.path.splitext(os.path.basename(a.ref))[0]
        r = cmp_orders(read_journal(a.journal), a.ref, code, a.t_from, a.t_to, a.rel)
    else:
        r = cmp_trades(read_journal(a.journal), pd.read_parquet(a.ref), a.code, a.t_from, a.t_to, a.rel or 1e-12)
    print(json.dumps(r, indent=1, default=str))
    return 0 if r.get("pass", True) else 1


if __name__ == "__main__":
    sys.exit(main())
