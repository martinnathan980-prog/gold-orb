"""S0: an empty EA (the S0 driver against the stubs) replays 2021 on the four symbols with a parsable journal.

    python3 -I lab/robot/check/test_s0_replay.py [--no-sanitize]

The dist file (harness build) replays the 2021 bars of XAUUSD.r, US100.r, BTCUSD.r and ETHUSD.r exported by
export_frames.py (--tag y2021). Checks: every journal line parses (CR|utc|EVENT|code|k=v...); INIT, SELFTEST (ok=1),
PLAN, four READY lines and one REBUILD are there; one AGG and one DAY line per server day; every kept bar that starts
before the last barrier was fed to the driver (the bars of the last minute stay forming); no ERROR; no order sent.
The same replay under the sanitizer build (address, undefined behaviour, bounds-checked containers) must end cleanly
with the same journal.
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import compare  # noqa: E402
from build import build, replay  # noqa: E402
from test_s0_script import bars_2021  # noqa: E402


def bar_counts(paths):
    n, last = {}, {}
    for s, p in paths.items():
        with open(p, "rb") as f:
            f.read(4)
            np.frombuffer(f.read(4), "<i4")
            k = int(np.frombuffer(f.read(8), "<i8")[0])
            t = np.frombuffer(f.read(k * 28), np.dtype([("t", "<i8"), ("v", "<i4", 5)]))["t"]
        n[s], last[s] = k, int(t[-1])
    return n, last


def run(sanitize):
    bars = bars_2021()
    exe, warn = build("dist", sanitize=sanitize)
    files = os.path.join(HERE, "out", "run_s0_empty" + ("_san" if sanitize else ""))
    out, wall = replay(exe, files, bars, env={"ASAN_OPTIONS": "detect_leaks=1"} if sanitize else None)
    rows = compare.read_journal(files)
    ev = compare.check_parsable(files)["events"]
    n, last = bar_counts(bars)
    last_event = max(last.values())
    expect_fed = sum(n.values()) - sum(1 for s in last if last[s] == last_event)
    deinit = [r for r in rows if r["ev"] == "INIT" and "deinit" in r][-1]
    selftest = compare.events(rows, "SELFTEST").iloc[0]
    days = len(compare.events(rows, "DAY"))
    res = {"sanitize": sanitize, "replay": out, "wall_s": round(wall, 2), "warnings": len(warn), "events": ev,
           "bars_in_files": sum(n.values()), "bars_fed": int(deinit["bars_fed"]), "bars_expected_fed": expect_fed,
           "server_days_with_lines": days}
    ok = (len(warn) == 0 and ev.get("INIT") == 2 and int(selftest["ok"]) == 1 and ev.get("PLAN") == 1 and ev.get("READY") == 4
          and ev.get("REBUILD") == 1 and ev.get("AGG") == days and days > 300 and "ERROR" not in ev and "SEND" not in ev
          and int(deinit["bars_fed"]) == expect_fed)
    res["pass"] = bool(ok)
    return res, files


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-sanitize", action="store_true")
    a = ap.parse_args(argv)
    r1, f1 = run(False)
    out = {"plain": r1}
    ok = r1["pass"]
    if not a.no_sanitize:
        r2, f2 = run(True)
        same = subprocess.run(["diff", "-r", "-q", os.path.join(f1, "ClaudeRobot"), os.path.join(f2, "ClaudeRobot")],
                              capture_output=True, text=True)
        r2["journal_identical_to_plain_build"] = same.returncode == 0
        out["sanitizer"] = r2
        ok &= r2["pass"] and r2["journal_identical_to_plain_build"]
    out["pass"] = bool(ok)
    print(json.dumps(out, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
