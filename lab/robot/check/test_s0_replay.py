"""S0: an empty EA (the S0 driver against the stubs) replays 2021 on the four symbols with a parsable journal.

    python3 -I lab/robot/check/test_s0_replay.py [--no-sanitize]

The dist file (harness build) replays the 2021 bars of XAUUSD.r, US100.r, BTCUSD.r and ETHUSD.r exported by
export_frames.py (--tag y2021). Checks: every journal line parses (CR|utc|EVENT|code|k=v...); INIT, SELFTEST (ok=1),
PLAN, four READY lines and one REBUILD are there; one AGG and one DAY line per server day; every kept bar that starts
before the last barrier was fed to the driver (the bars of the last minute stay forming); no ERROR; no order sent.
Since step K every module of the dist file is real (rules, follower, broker), so the replay runs with InpTrade
false: the EA observes and sends nothing (SPEC 4.9), which is the contract the rule steps' T4/T5 replays keep; the
trading paths are T7b's and T8's (check/test_t7b.py, test_worlds.py, test_worlds_rules.py).
The kept bars are derived, not hard-coded: SPEC 2.2's mask is applied to the bar files by test_bars.mask_reasons (the
pandas copy of the mask, independent of the EA; no flat-bar rule since the lead's decision after step B's finding 1).
The same replay under the sanitizer build (address, undefined behaviour, bounds-checked containers) must end cleanly
with the same journal. Also checks compare.py's paper trades on a small written journal (PVOID, PREVISE, a rebuild).
"""
import argparse
import json
import os
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import compare  # noqa: E402
from build import build, replay  # noqa: E402
from test_bars import KEPT, REASONS, half_days, mask_reasons, read_bin  # noqa: E402
from test_s0_script import bars_2021  # noqa: E402

FAMILY = {"XAUUSD.r": "XAU", "US100.r": "IDX", "BTCUSD.r": "CRY", "ETHUSD.r": "CRY"}


def bar_counts(paths):
    """per symbol: the bars of the file and the bars SPEC 2.2's mask drops, by reason; and the bars the driver must be
    fed: every kept bar that starts before the replay's last bar time (the bars of that minute never close)"""
    recs = {s: read_bin(p) for s, p in paths.items()}
    last_event = max(int(r["t"][-1]) for r in recs.values())
    halves = half_days()
    n, masked, fed = {}, {}, 0
    for s, r in recs.items():
        why = mask_reasons(r, FAMILY[s], halves)
        n[s] = int(len(r))
        masked[s] = {REASONS[k]: int((why == k).sum()) for k in range(len(REASONS)) if k != KEPT and (why == k).any()}
        fed += int(((why == KEPT) & (r["t"] < last_event)).sum())
    return n, masked, fed


def run(sanitize):
    bars = bars_2021()
    exe, warn = build("dist", sanitize=sanitize)
    files = os.path.join(HERE, "out", "run_s0_empty" + ("_san" if sanitize else ""))
    env = {"MOCK_INPUT_InpTrade": "false"}                 # observe only (step K: every module is real now, see the docstring)
    if sanitize:
        env["ASAN_OPTIONS"] = "detect_leaks=1"
    out, wall = replay(exe, files, bars, env=env)
    rows = compare.read_journal(files)
    ev = compare.check_parsable(files)["events"]
    n, masked, expect_fed = bar_counts(bars)
    deinit = [r for r in rows if r["ev"] == "INIT" and "deinit" in r][-1]
    selftest = compare.events(rows, "SELFTEST").iloc[0]
    days = len(compare.events(rows, "DAY"))
    res = {"sanitize": sanitize, "replay": out, "wall_s": round(wall, 2), "warnings": len(warn), "events": ev,
           "bars_in_files": sum(n.values()), "bars_masked": masked, "bars_fed": int(deinit["bars_fed"]), "bars_expected_fed": expect_fed,
           "server_days_with_lines": days}
    ok = (len(warn) == 0 and ev.get("INIT") == 2 and int(selftest["ok"]) == 1 and ev.get("PLAN") == 1 and ev.get("READY") == 4
          and ev.get("REBUILD") == 1 and ev.get("AGG") == days and days > 300 and "ERROR" not in ev and "SEND" not in ev
          and int(deinit["bars_fed"]) == expect_fed)
    res["pass"] = bool(ok)
    return res, files


def paper_chain_check():
    """compare.py's paper trades on a small written journal (read back through read_journal): a PVOID after the fill
    drops the trade (void_le), a PREVISE replaces the exit, a rebuild's later PFILL starts the trade again, an order
    voided before any fill and an open trade give no row, another sleeve's lines are ignored"""
    d = os.path.join(HERE, "out", "run_s0_paper_chain", "ClaudeRobot")
    os.makedirs(d, exist_ok=True)

    def ln(t, ev, oid, px, reason=None, rp=False, code="BKB"):                 # a line as JrnPaper writes it
        kv = f"oid={oid}|side=1|bar={t - t % 60}|px={px}|stop=9.5|st0=9.5|x=90000" + (f"|reason={reason}" if reason else "")
        return f"CR|{t}|{ev}|{code}|{kv}|s_raw=3|s_paper=0.03" + ("|rp=1" if rp else "")
    lines = [ln(60000, "PFILL", 1, 10.5), ln(60060, "PEXIT", 1, 9.5, "stop"), ln(60000, "PVOID", 1, 10.5, "void"),       # voided
             ln(61000, "PFILL", 2, 11.0), ln(61060, "PEXIT", 2, 9.5, "stop"), ln(61020, "PREVISE", 2, 10.75, "time"),  # revised
             ln(62000, "PFILL", 3, 12.0), ln(62600, "PEXIT", 3, 12.25, "time"),                                          # plain
             ln(63000, "PVOID", 4, 0, "void"),                                                                            # no fill
             ln(64000, "PFILL", 5, 13.0), ln(64060, "PEXIT", 5, 9.5, "stop"), ln(64000, "PVOID", 5, 13.0, "void"),
             ln(64000, "PFILL", 5, 13.0, rp=True), ln(64600, "PEXIT", 5, 13.5, "time", rp=True),                         # rebuilt
             ln(65000, "PFILL", 6, 14.0),                                                                                 # open
             ln(66000, "PFILL", 7, 15.0, code="BKE"), ln(66600, "PEXIT", 7, 15.5, "time", code="BKE")]
    with open(os.path.join(d, "20210101.log"), "w") as f:
        f.write("\n".join(lines) + "\n")
    rows = compare.read_journal(os.path.dirname(d))
    t = compare.paper_trades(rows, "BKB")
    _, void = compare.paper_chain(rows, "BKB")
    t_live = compare.paper_trades(rows, "BKB", live_only=True)
    _, void_live = compare.paper_chain(rows, "BKB", live_only=True)
    got = [(int(r.oid), float(r.exit), r.reason, bool(r.revised)) for r in t.itertuples()]
    want = [(2, 10.75, "time", True), (3, 12.25, "time", False), (5, 13.5, "time", False)]
    ok = got == want and void == [1] and t_live.oid.tolist() == [2, 3] and void_live == [1, 5]
    return {"trades": got, "voided": void, "live_only_trades": t_live.oid.tolist(), "live_only_voided": void_live, "pass": bool(ok)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-sanitize", action="store_true")
    a = ap.parse_args(argv)
    pc = paper_chain_check()
    r1, f1 = run(False)
    out = {"paper_chain": pc, "plain": r1}
    ok = pc["pass"] and r1["pass"]
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
