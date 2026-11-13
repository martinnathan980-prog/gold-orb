"""T4 acceptance (step K): the shipped single file, all ten sleeves at once, against the lab over 2013-2021, switches off
and on (T5), plain and sanitizer builds, and speed.

    python3 -I lab/robot/check/test_accept.py [--no-sanitize] [--fresh] [--clean]

The EA is dist/ClaudeRobot.mq5 as it is (check/test_release.py checks that it is tools/amalgam.py's output of src/),
translated by check/to_cpp.py: the harness build (CR_HARNESS, CR_XAU_COMM_PTS=0: the exported spread holds the gold
commission, SPEC 7) and its sanitizer build, with every real module: the rules of steps D-H, J's broker, follower and
guards, K's driver and golden vectors. It replays the 2013-2021 bars of the four symbols (export_frames.py --tag is) in
one process, InpTrade false (SPEC 8's T4/T5 setting: no order is sent), on a demo account:
  off  InpK1 = InpH2 = InpS075 = 0 (the official rules)
  on   InpK1 = InpH2 = InpS075 = 1, InpK1T = the K1 folds the lab fits on the same bars (ref_changes.py, T5)
Checks:
  1. Journal contract: every line parses; INIT 2, SELFTEST ok=1 with every golden vector, PLAN 1, READY 4, REBUILD 1;
     no ERROR, no SEND; the sanitizer build writes byte-identical journals (the full in-sample ten-sleeve run under the
     sanitizer, SPEC 8 K).
  2. Same as the rule steps: every line of each sleeve (DEC, PFILL, PEXIT, PSTOP, PREVISE, PVOID, PREFUSE, HOLD) equals,
     in order and byte for byte, that sleeve's lines in the journal the rule step's own test checked against the lab:
     check/out/test_idxus/is_test_idxus (N30, OC4: step D), test_E/off and test_E/on (BKB, BKE, F1B, F1E: E),
     test_NQB/is_plain (NQB: F), test_G/replay (GFP, ORX: G), test_D4H/is_ea (D4H: H). Those tests resolved every
     decision against the lab's orders and classified every difference, on their private trees (the S0 stubs of the
     other steps); equal lines carry their verdicts over to the shipped file, where all modules run together. A missing
     step journal is made again by running that step's own test.
  3. Against the lab directly: compare.cmp_trades (entry and exit minute, side, reason equal; prices within 1e-12
     relative) for every sleeve against ref_lab.py's trades on the frames rebuilt from the same bars (off), and against
     ref_changes.py's chains (on: BKE+K1, BKB+S0.75r, F1E+H2; the other seven sleeves against ref_lab.py again); GFP
     against the lab run on the kept bars too (test_GFP.py's reference: the rebuilt frame without the 20 gold bars of
     2012-12-31 17:00-17:58 New York that the mask drops). Lab trades still open at the frame end are left out (SPEC 7).
     Every remaining difference is classified with its cause; an unclassified one fails the test.
  4. Speed (SPEC 7): the full in-sample ten-sleeve replay under 3 min; a start's rebuild (SPEC 2.2's depth: 120 days of
     gold, 60 of the others) under 5 s, measured on a start at 2021-06-01.
Outputs: check/out/test_accept/summary.json; the plain journals in check/out/test_accept/{off,on} (--clean removes them;
the sanitizer journals are removed once compared).
"""
import argparse
import calendar
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
os.environ.setdefault("NUMBA_CACHE_DIR", "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/numba")
HERE = os.path.dirname(os.path.abspath(__file__))
ROBOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import compare  # noqa: E402
from build import build, replay  # noqa: E402

OUT = os.path.join(HERE, "out", "test_accept")
DIST = os.path.join(ROBOT, "dist", "ClaudeRobot.mq5")
SYMS = ("XAUUSD.r", "US100.r", "BTCUSD.r", "ETHUSD.r")
CODES = ["N30", "OC4", "BKB", "BKE", "F1B", "F1E", "NQB", "GFP", "D4H", "ORX"]
SYM_OF = {"N30": "us100", "OC4": "us100", "BKB": "btcusd", "BKE": "ethusd", "F1B": "btcusd", "F1E": "ethusd", "NQB": "btcusd",
          "GFP": "xauusd", "D4H": "xauusd", "ORX": "xauusd"}
CHANGE_OF = {"BKE": "K1", "BKB": "S0.75r", "F1E": "H2"}
PAPER_EV = {"DEC", "PFILL", "PEXIT", "PSTOP", "PREVISE", "PVOID", "PREFUSE", "HOLD"}
CUT = pd.Timestamp("2022-01-01", tz="UTC")
REF = os.path.join(HERE, "out", "ref", "rebuilt_is")
REF_E = os.path.join(HERE, "out", "test_E", "ref", "rebuilt_is", "changes")
REF_G_KEPT = os.path.join(HERE, "out", "test_G", "ref", "lab_kept")
# the journal each rule step's own test checked against the lab, and the test that makes it again
STEP = {"N30": ("test_idxus/is_test_idxus", ["test_N30.py", "--world", "is", "--no-sanitize"]),
        "OC4": ("test_idxus/is_test_idxus", ["test_N30.py", "--world", "is", "--no-sanitize"]),
        "BKB": ("test_E/{sw}", ["test_BK.py", "--no-sanitize"]), "BKE": ("test_E/{sw}", ["test_BK.py", "--no-sanitize"]),
        "F1B": ("test_E/{sw}", ["test_BK.py", "--no-sanitize"]), "F1E": ("test_E/{sw}", ["test_BK.py", "--no-sanitize"]),
        "NQB": ("test_NQB/is_plain", ["test_NQB.py", "--world", "is", "--no-sanitize"]),
        "GFP": ("test_G/replay", ["test_GFP.py", "--no-sanitize"]), "ORX": ("test_G/replay", ["test_GFP.py", "--no-sanitize"]),
        "D4H": ("test_D4H/is_ea", ["test_D4H.py", "--world", "is", "--no-sanitize"])}
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
K1T_FALLBACK = "2019:505.84441393264945;2020:496.6915507295559;2021:465.14468666253265"


def log(m):
    print(m, flush=True)


def bars():
    p = {s: os.path.join(HERE, "out", "bars", f"{s}_is.bin") for s in SYMS}
    if not all(os.path.exists(v) for v in p.values()):
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "export_frames.py"), "--tag", "is"], capture_output=True,
                           text=True, env=ENV)
        if r.returncode:
            raise SystemExit("export_frames.py failed: " + r.stderr[-2000:])
    return p


def refs():
    """ref_lab.py's references on the rebuilt frames (the ten sleeves), and the three changes' (ref_changes.py)"""
    if not all(os.path.exists(os.path.join(REF, c, "trades.parquet")) for c in CODES):
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "ref_lab.py"), "--frame", "rebuilt", "--tag", "is", "--no-changes"],
                           capture_output=True, text=True, env=ENV)
        if r.returncode:
            raise SystemExit("ref_lab.py failed: " + (r.stdout + r.stderr)[-3000:])
    k1t = None
    if not all(os.path.exists(os.path.join(REF_E, ch, "trades.parquet")) for ch in CHANGE_OF.values()):
        for ch in CHANGE_OF.values():
            r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "ref_lab.py"), "--change", ch, "--frame", "rebuilt", "--tag", "is"],
                               capture_output=True, text=True, env=ENV)
            if r.returncode:
                raise SystemExit(f"ref_lab.py --change {ch} failed: " + r.stderr[-3000:])
            if ch == "K1":
                k1t = json.loads(r.stdout.strip().splitlines()[-1]).get("inpk1t")
        ref_e = os.path.join(REF, "changes")
    else:
        ref_e = REF_E
        p = os.path.join(HERE, "out", "test_E", "test_changes.json")
        if os.path.exists(p):
            k1t = json.load(open(p)).get("k1_folds", {}).get("inpk1t_rebuilt")
    return ref_e, k1t or K1T_FALLBACK


def read_trades(p):
    return pd.read_parquet(p, filters=[("entry_time", "<", CUT)])


def last_bar(sym):
    """the start of the last in-sample bar of a symbol's rebuilt frame (UTC seconds)"""
    t = pd.read_parquet(os.path.join(HERE, "out", "frames", f"{sym}_is.parquet"), columns=["bo"], filters=[("ts", "<", CUT)]).index
    return int(t.max().value // 10 ** 9)


# ------------------------------------------------------------------ replays
def run(exe, name, inputs, fresh, sanitize=False):
    files = os.path.join(OUT, name)
    key = {"exe": hashlib.sha256(open(exe, "rb").read()).hexdigest(), "inputs": inputs,
           "bars": {s: os.path.getsize(p) for s, p in bars().items()}}
    kp = os.path.join(files, "_key.json")
    if not fresh and os.path.exists(kp) and json.load(open(kp)) == key:
        return json.load(open(os.path.join(files, "_run.json")))
    env = {f"MOCK_INPUT_{k}": v for k, v in inputs.items()}
    if sanitize:
        env["ASAN_OPTIONS"] = "detect_leaks=1"
    out, wall = replay(exe, files, bars(), env=env, timeout=7200)
    res = {"stdout": out, "wall_s": round(wall, 1)}
    with open(os.path.join(files, "_run.json"), "w") as f:
        json.dump(res, f)
    with open(kp, "w") as f:
        json.dump(key, f)
    return res


def journal_files(d):
    return sorted(glob.glob(os.path.join(d, "ClaudeRobot", "*.log")))


def sleeve_lines(d, code):
    out = []
    for f in journal_files(d):
        with open(f) as h:
            for ln in h:
                p = ln.split("|", 4)
                if len(p) > 3 and p[2] in PAPER_EV and p[3] == code:
                    out.append(ln.rstrip("\n"))
    return out


def same_journals(a, b):
    fa, fb = journal_files(a), journal_files(b)
    if [os.path.basename(x) for x in fa] != [os.path.basename(x) for x in fb]:
        return False
    return all(open(x, "rb").read() == open(y, "rb").read() for x, y in zip(fa, fb))


def contract(rows):
    ev = {}
    for r in rows:
        ev[r["ev"]] = ev.get(r["ev"], 0) + 1
    st = [r for r in rows if r["ev"] == "SELFTEST"]
    ok = (ev.get("INIT") == 2 and len(st) == 1 and st[0].get("ok") == 1 and st[0].get("golden") == 322 and ev.get("PLAN") == 1
          and ev.get("READY") == 4 and ev.get("REBUILD") == 1 and "ERROR" not in ev and "SEND" not in ev)
    return {"events": dict(sorted(ev.items())), "selftest": st[0] if st else None, "pass": bool(ok)}


# ------------------------------------------------------------------ 2. the rule steps' journals
def step_journal(code, sw, fresh_steps):
    rel, cmd = STEP[code]
    d = os.path.join(HERE, "out", rel.format(sw=sw))
    if not journal_files(d) or fresh_steps:
        log(f"  making {code}'s step journal again: {' '.join(cmd)}")
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, cmd[0])] + cmd[1:], capture_output=True, text=True, env=ENV,
                           cwd=ROBOT, timeout=7200)
        if not journal_files(d):
            return None, f"{cmd[0]} exit {r.returncode}: {(r.stdout + r.stderr)[-600:]}"
    return d, None


def cmp_lines(a, b):
    if a == b:
        return {"lines": len(a), "identical": True}
    n = min(len(a), len(b))
    k = next((i for i in range(n) if a[i] != b[i]), n)
    return {"lines_dist": len(a), "lines_step": len(b), "identical": False, "first_difference": k,
            "dist": a[k] if k < len(a) else None, "step": b[k] if k < len(b) else None}


# ------------------------------------------------------------------ 3. against the lab
def trades_vs_lab(rows, code, lab, t_to, cause_fn=None):
    r = compare.cmp_trades(rows, lab, code, t_to=t_to, rel=1e-12)
    ea = compare.paper_trades(rows, code)
    lab_in = lab[lab.exit_time <= pd.Timestamp(t_to, unit="s", tz="UTC")]
    m = lab_in.merge(ea, on=["entry_time", "side"], how="outer", suffixes=("_lab", "_ea"), indicator=True)
    both = m[m._merge == "both"]
    same = both[(both.exit_time_lab == both.exit_time_ea) & (both.reason_lab == both.reason_ea)]
    bits = {c: int((same[f"{c}_lab"].astype(float) == same[f"{c}_ea"].astype(float)).sum()) for c in ("entry", "stop", "exit")}
    rel = {c: float(((same[f"{c}_lab"].astype(float) - same[f"{c}_ea"].astype(float)).abs()
                     / same[f"{c}_lab"].astype(float).abs()).max()) if len(same) else 0.0 for c in ("entry", "stop", "exit")}
    diffs = []
    for _, x in m[m._merge != "both"].iterrows():
        diffs.append({"entry_time": str(x.entry_time), "side": int(x.side), "in": "lab only" if x._merge == "left_only" else "EA only"})
    for _, x in both[(both.exit_time_lab != both.exit_time_ea) | (both.reason_lab != both.reason_ea)].iterrows():
        diffs.append({"entry_time": str(x.entry_time), "side": int(x.side), "in": "both, exit differs",
                      "lab": [str(x.exit_time_lab), x.reason_lab], "ea": [str(x.exit_time_ea), x.reason_ea]})
    tol = 1e-12
    for c in ("entry", "stop", "exit"):
        a, b = same[f"{c}_lab"].astype(float), same[f"{c}_ea"].astype(float)
        bad = same[((a - b).abs() > tol * a.abs())]
        for _, x in bad.iterrows():
            diffs.append({"entry_time": str(x.entry_time), "side": int(x.side), "in": f"both, {c} beyond 1e-12",
                          "lab": float(x[f"{c}_lab"]), "ea": float(x[f"{c}_ea"])})
    for d in diffs:
        d["cause"] = cause_fn(d) if cause_fn else None
    unexplained = [d for d in diffs if not d["cause"]]
    out = {k: r.get(k) for k in ("lab_trades", "ea_trades", "same_entry", "only_lab", "only_ea", "same_exit_and_reason",
                                 "voided_in_journal", "pass")}
    out.update({"bit_equal": bits, "max_rel_diff": rel, "differences": diffs, "unexplained": len(unexplained),
                "lab_open_at_frame_end_left_out": int((lab.exit_time > pd.Timestamp(t_to, unit="s", tz="UTC")).sum())})
    out["ok"] = len(unexplained) == 0
    return out


def gfp_hole_days():
    """GFP hole days (SPEC 7: classified): Fridays whose gold data has no bar in [16:45, 16:50] New York, though bars run
    to 13:30: the lab's 16:45 test reads that future hole and skips the Friday; the EA cannot see it"""
    m1 = pd.read_parquet(os.path.join(HERE, "out", "frames", "xauusd_is.parquet"), columns=["bo"], filters=[("ts", "<", CUT)])
    ny = m1.index.tz_convert("America/New_York")
    df = pd.DataFrame({"d": ny.normalize().tz_localize(None), "m": ny.hour * 60 + ny.minute, "dow": ny.dayofweek})
    fri = df[df.dow == 4]
    days = set()
    for d, g in fri.groupby("d"):
        if (g.m < 13 * 60 + 30).any() and not ((g.m >= 16 * 60 + 45) & (g.m <= 16 * 60 + 50)).any():
            days.add(str(d.date()))
    return days


# ------------------------------------------------------------------ 4. speed of a start
def start_speed(exe):
    frm = calendar.timegm((2021, 6, 1, 0, 0, 0))
    files = os.path.join(OUT, "start_speed")
    out, wall = replay(exe, files, bars(), env={"MOCK_INPUT_InpTrade": "false"}, frm=frm, to=frm + 600)
    rows = compare.read_journal(files)
    reb = [r for r in rows if r["ev"] == "REBUILD"]
    rep = float(out.split("replay ")[1].split(" s")[0]) if "replay " in out else None
    shutil.rmtree(files, ignore_errors=True)
    return {"process_wall_s": round(wall, 2), "mock_replay_s": rep, "rebuild_minutes": reb[0]["minutes"] if reb else None,
            "rebuild_from": reb[0]["from"] if reb else None, "pass": rep is not None and rep < 5.0}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-sanitize", action="store_true")
    ap.add_argument("--fresh", action="store_true", help="replay again even when a cached replay of the same binary exists")
    ap.add_argument("--fresh-steps", action="store_true", help="make the rule steps' journals again")
    ap.add_argument("--clean", action="store_true", help="remove the plain journals at the end")
    a = ap.parse_args(argv)
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    res = {"dist_cr_build": open(DIST).readline().strip()}
    exe, w = build(DIST, name="test_accept")
    warn = {"harness": len(w)}
    exe_san = None
    if not a.no_sanitize:
        exe_san, w2 = build(DIST, name="test_accept_san", sanitize=True)
        warn["sanitizer"] = len(w2)
    res["warnings"] = warn
    ref_e, k1t = refs()
    res["k1t"] = k1t
    sw_inputs = {"off": {"InpTrade": "false", "InpK1": "0", "InpH2": "0", "InpS075": "0", "InpK1T": ""},
                 "on": {"InpTrade": "false", "InpK1": "1", "InpH2": "1", "InpS075": "1", "InpK1T": k1t}}
    last = {s: last_bar(s) for s in set(SYM_OF.values())}
    holes = gfp_hole_days()
    ok = all(v == 0 for v in warn.values())
    for sw, inp in sw_inputs.items():
        log(f"replay {sw} ...")
        r = run(exe, sw, inp, a.fresh)
        d = os.path.join(OUT, sw)
        rows = compare.read_journal(d)
        R = {"wall_s": r["wall_s"], "mock": r["stdout"], "contract": contract(rows)}
        ok &= R["contract"]["pass"]
        if exe_san:
            log(f"replay {sw} under the sanitizer ...")
            rs = run(exe_san, sw + "_san", inp, True, sanitize=True)
            R["sanitizer"] = {"wall_s": rs["wall_s"], "identical_journal": same_journals(d, os.path.join(OUT, sw + "_san"))}
            ok &= R["sanitizer"]["identical_journal"]
            shutil.rmtree(os.path.join(OUT, sw + "_san"), ignore_errors=True)
        R["same_as_rule_steps"], R["lab"] = {}, {}
        for code in CODES:
            sd, err = step_journal(code, sw, a.fresh_steps and sw == "off")
            if sd is None:
                R["same_as_rule_steps"][code] = {"identical": False, "error": err}
                ok = False
            else:
                c = cmp_lines(sleeve_lines(d, code), sleeve_lines(sd, code))
                c["step_journal"] = os.path.relpath(sd, ROBOT)
                R["same_as_rule_steps"][code] = c
                ok &= c["identical"]
            sym = SYM_OF[code]
            t_to = last[sym] - 1
            changed = sw == "on" and code in CHANGE_OF
            lab = read_trades(os.path.join(ref_e, CHANGE_OF[code], "trades.parquet") if changed else os.path.join(REF, code, "trades.parquet"))
            if code == "GFP":
                kept = read_trades(os.path.join(REF_G_KEPT, "GFP", "trades.parquet")) if os.path.exists(REF_G_KEPT) else None

                def cause(dd):
                    day = dd["entry_time"][:10]
                    if dd["in"] == "EA only" and day in holes:
                        return "GFP hole day: the gold data stops before 16:45 New York; the lab's 16:45 test reads that future hole"
                    if dd["in"].startswith("both, stop") and dd["entry_time"] < "2013-02-01":
                        return ("rebuilt frame only: the 20 gold bars of 2012-12-31 17:00-17:58 New York that the mask drops seed "
                                "the lab's hour ATR; equal on the kept bars")
                    return None
                R["lab"][code] = trades_vs_lab(rows, code, lab, t_to, cause)
                if kept is not None:
                    R["lab"][code + "_kept_bars"] = trades_vs_lab(rows, code, kept, t_to, cause)
                    ok &= R["lab"][code + "_kept_bars"]["ok"] and R["lab"][code + "_kept_bars"]["unexplained"] == 0
            else:
                R["lab"][code + ("+" + CHANGE_OF[code] if changed else "")] = trades_vs_lab(rows, code, lab, t_to)
            ok &= all(v["ok"] for k, v in R["lab"].items() if k.startswith(code))
        res[sw] = R
        log(f"  {sw}: replay {r['wall_s']} s, contract {R['contract']['pass']}, same as the rule steps "
            f"{sum(v.get('identical', False) for v in R['same_as_rule_steps'].values())}/10")
    res["start_speed"] = start_speed(exe)
    res["full_replay_under_3_min"] = all(res[sw]["wall_s"] < 180 for sw in sw_inputs)
    ok &= res["start_speed"]["pass"] and res["full_replay_under_3_min"]
    res["sec"] = round(time.time() - t0, 1)
    res["pass"] = bool(ok)
    with open(os.path.join(OUT, "summary.json"), "w") as f:
        json.dump(res, f, indent=1, default=str)
    for sw in sw_inputs:
        log(f"== switches {sw} (replay {res[sw]['wall_s']} s; sanitizer identical: {res[sw].get('sanitizer', {}).get('identical_journal')})")
        for code in CODES:
            s = res[sw]["same_as_rule_steps"][code]
            for k, v in res[sw]["lab"].items():
                if k.split("+")[0].split("_")[0] != code:
                    continue
                log(f"  {k:12s} lines = step: {s.get('identical')} ({s.get('lines', s.get('lines_dist'))}) | lab {v['lab_trades']} "
                    f"EA {v['ea_trades']} same {v['same_exit_and_reason']} bit-equal {v['bit_equal']} max rel {max(v['max_rel_diff'].values()):.2g} "
                    f"diffs {len(v['differences'])} unexplained {v['unexplained']} left out (open at end) {v['lab_open_at_frame_end_left_out']}")
    log(f"start: rebuild of {res['start_speed']['rebuild_minutes']} minutes, mock replay {res['start_speed']['mock_replay_s']} s")
    log(f"test_accept: {'PASS' if ok else 'FAIL'} ({res['sec']} s)")
    if a.clean:
        for sw in sw_inputs:
            shutil.rmtree(os.path.join(OUT, sw), ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
