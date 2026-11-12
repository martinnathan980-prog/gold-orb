"""S0: CR_Rule_Script replays the lab's orders (ref_lab.py) as DEC lines equal to them, field by field.

    python3 -I lab/robot/check/test_s0_script.py [--codes N30,OC4,...] [--sanitize]

The dist file (harness build) replays 2021 on the four symbols with the ten sleeves switched to the script rule
(harness input InpScript); every order of check/out/ref/official/script/<CODE>.csv whose emit minute lies inside the
replayed minutes must come out exactly once as a DEC line with the same 24 fields (doubles compared bit for bit).
Prepares what it needs: the 2021 bar export (export_frames.py --tag y2021) and the official references (ref_lab.py).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROBOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import compare  # noqa: E402
from build import build, replay  # noqa: E402

CODES = "N30,OC4,BKB,BKE,F1B,F1E,NQB,GFP,D4H,ORX"
SYMS = ("XAUUSD.r", "US100.r", "BTCUSD.r", "ETHUSD.r")
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
           NUMBA_CACHE_DIR=os.environ.get("NUMBA_CACHE_DIR", "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/numba"))


def bars_2021(tag="y2021"):
    """the exported bars of a tag: y2021 (2021) or is (the whole in-sample period); exported when missing"""
    p = {s: os.path.join(HERE, "out", "bars", f"{s}_{tag}.bin") for s in SYMS}
    if not all(os.path.exists(v) for v in p.values()):
        win = ["--from", "2021-01-01", "--to", "2022-01-01"] if tag == "y2021" else []
        subprocess.run([sys.executable, "-I", os.path.join(HERE, "export_frames.py")] + win + ["--tag", tag], check=True, env=ENV,
                       capture_output=True)
    return p


def refs():
    d = os.path.join(HERE, "out", "ref", "official", "script")
    if not all(os.path.exists(os.path.join(d, f"{c}.csv")) for c in CODES.split(",")):
        subprocess.run([sys.executable, "-I", os.path.join(HERE, "ref_lab.py"), "--no-changes"], check=True, env=ENV, capture_output=True)
    return d


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", default=CODES)
    ap.add_argument("--sanitize", action="store_true")
    ap.add_argument("--tag", default="y2021", help="y2021 (default) or is (2013-2021)")
    a = ap.parse_args(argv)
    bars, sdir = bars_2021(a.tag), refs()
    exe, warn = build("dist", sanitize=a.sanitize)
    files = os.path.join(HERE, "out", "run_s0_script_" + a.tag + ("_san" if a.sanitize else ""))
    if os.path.isdir(files):
        shutil.rmtree(files)
    os.makedirs(os.path.join(files, "ClaudeRobot", "script"))
    for c in a.codes.split(","):
        shutil.copy(os.path.join(sdir, f"{c}.csv"), os.path.join(files, "ClaudeRobot", "script", f"{c}.csv"))
    out, wall = replay(exe, files, bars, env={"MOCK_INPUT_InpScript": a.codes}, fresh=False)
    rows = compare.read_journal(files)
    reb = compare.events(rows, "REBUILD")
    # the first barrier the driver processes: after the first stored bar, or after the rebuild barrier when the store
    # was empty at the first rebuild (the replay starts at the first event)
    r0 = reb.iloc[0]
    first_minute = int(r0["from"]) + 60 if int(r0["from"]) > 0 else int(r0["to"]) + 60
    last_bar = max(int(compare.events(rows, "INIT").iloc[-1]["utc"]) - 2, 0)          # the OnDeinit line: last event + 2 s
    res = {"replay": out, "wall_s": round(wall, 2), "warnings": len(warn), "first_minute": first_minute, "last_minute": last_bar,
           "errors": [r for r in rows if r["ev"] == "ERROR"][:5], "per_sleeve": {}}
    ok = len(warn) == 0 and not res["errors"]
    for c in a.codes.split(","):
        r = compare.cmp_orders(rows, os.path.join(sdir, f"{c}.csv"), c, first_minute, last_bar)
        res["per_sleeve"][c] = {k: r[k] for k in ("ref_orders", "dec_lines", "equal", "n_missing", "n_wrong", "n_extra", "duplicates", "pass")}
        ok &= r["pass"] and r["ref_orders"] > 0
    res["pass"] = bool(ok)
    print(json.dumps(res, indent=1, default=str))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
