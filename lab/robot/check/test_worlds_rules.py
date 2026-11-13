"""T8 again with the real rules (step K): the shipped single file in tick and fast worlds, switches off and on, and the
three worlds that need the rules (SPEC 7 T8), which step J's script sleeves could not run.

    python3 -I lab/robot/check/test_worlds_rules.py [--only clean_fast,clean_on,...] [--no-sanitize]

The EA: dist/ClaudeRobot.mq5 translated by check/to_cpp.py (harness build; for the gold quote world also CR_XAU_COMM_PTS=6),
all ten real rules (InpScript empty), J's follower, broker and guards. The worlds reuse step J's harness
(check/test_worlds.py: run, positions, real_vs_paper, lab_check, judge_clean), so a world is judged exactly as J's
script-sleeve worlds were, now with the rules deciding:
  clean_fast   2021, fast mode, switches off: every live paper trade has its real position (gold pending orders one bar
               late) at the expected times and prices, or a sizing skip; the live paper trades equal the lab's
               (ref_lab.py, rebuilt frames)
  clean_on     the same with InpK1 = InpH2 = InpS075 = 1 (InpK1T = the lab's in-sample folds): BKE+K1, BKB+S0.75r and
               F1E+H2 against ref_changes.py's chains, the seven others against ref_lab.py
  clean_tick   tick mode (ticks O, L, H, C): the same trades; stop exits fill at the triggering tick (counted)
  clean_h      gold with h = 3 points (CR_XAU_COMM_PTS=6; raw bid = lab bid + 3 points, raw spread = lab spread - 6
               points): the broker stop = paper stop + side x h triggers in the same bar
  clean_san    the sanitizer build replays clean_fast: identical journal and deals
  gfp_holiday  R8: Good Friday 2021-04-02 with gold quoted all day (the bars of Friday 2021-03-26 copied one week on):
               GFP writes its skip line at 13:30 New York and makes no order, no paper trade, no position that day
  us100_half   P6: the NYSE half day 2021-11-26 with US100 quoted after 13:15 (the 13:16-16:14 bars of 2021-11-19 copied
               one week on): the mask drops exactly the added bars (the deinit line's masked count) and N30, OC4 and NQB
               write the same lines as without them
  orx_spike    9.5: a raw spread spike (+300 points) on one gold bar inside a London range [00:00, 07:00) that has an ORX
               order: the order's level and stop are the range's H' + 0.1 W' and L - 0.1 W' with the spiked ask high
               (computed here from the bars), wider than without the spike, and the real trade follows the paper
The worlds of the review's fixes (each fails on the shipped file of CR_BUILD 1ca53085c0c1, the one reviewed):
  h2_restart   F1: switches on, one restart during an F1E trade held by H2 (2018-03-16 08:29 UTC, the review's case):
               the restarted run adopts the position and closes it at the paper's held exit like the continuous run;
               no CLOSE why=latest_exit (the old LatestExit, 15:55 New York of the decision, closed it 11 h early)
  notready_gate F1: a restart during an ORX trade whose exit falls in the gold holiday closure of 2020-02-17 (its
               LatestExit, with the gap rule, is before the closure; the paper exits at the reopening), gold not
               synchronized for 5 min after the start: nothing is closed before the sleeve is READY, the position is
               adopted and closes with the paper; then gold not synchronized for 30 min: the LatestExit close waits for
               10 min of NOT_READY after the first READY check (SPEC 4.8)
  crypto_weekend F2: BTC and ETH quoted all weekend 2021-07-31/08-01 (Friday's bars copied one and two days on; the
               mask drops them): no SIZE or SEND of a crypto sleeve in the masked weekend although BKB has an order
               there ([D, D+5] = Saturday 00:00-00:05 server), and every sleeve's paper lines and real positions equal
               the run without the weekend bars
  shadow       F6: one week of 2021 run by an observer (off the VPS, demo, InpTrade false) and by the VPS copy with
               InpTrade false: the same SIZE, MISSED and paper lines (SPEC 10.2, 10.12 compare the two journals)
  gfp_session  F7: FP's Friday gold session ending at 16:50 New York (23:50 server) is accepted (GFP trades as without
               session information); one ending at 16:40 skips the Friday with a DEC skip line (reason 4) and a push
Outputs: check/out/test_worlds_rules/summary.json (and the worlds' journals, removed at the end unless --keep).
"""
import argparse
import calendar
import json
import os
import shutil
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
import test_worlds as W  # noqa: E402  (step J's harness)
from build import build  # noqa: E402

OUT = os.path.join(HERE, "out", "test_worlds_rules")
DIST = os.path.join(ROBOT, "dist", "ClaudeRobot.mq5")
CODES = W.CODES
CHANGE_OF = {"BKE": "K1", "BKB": "S0.75r", "F1E": "H2"}
REF_E = os.path.join(HERE, "out", "test_E", "ref", "rebuilt_is", "changes")
PAPER_EV = {"DEC", "PFILL", "PEXIT", "PSTOP", "PREVISE", "PVOID", "PREFUSE", "HOLD"}
NY = "America/New_York"


def log(m):
    print(m, flush=True)


def k1t():
    p = os.path.join(HERE, "out", "test_E", "test_changes.json")
    v = json.load(open(p)).get("k1_folds", {}).get("inpk1t_rebuilt") if os.path.exists(p) else None
    return v or "2019:505.84441393264945;2020:496.6915507295559;2021:465.14468666253265"


SW_ON = {"MOCK_INPUT_InpK1": "1", "MOCK_INPUT_InpH2": "1", "MOCK_INPUT_InpS075": "1"}


def ny_srv(day, hh, mm=0):
    """server seconds of a New York wall-clock time (server = New York + 7 h)"""
    t = pd.Timestamp(day) + pd.Timedelta(hours=hh, minutes=mm) + pd.Timedelta(hours=7)
    return int(t.value // 10 ** 9)


def change_check(rows, code, g):
    """the live paper trades of a changed sleeve against ref_changes.py's chain"""
    ref = pd.read_parquet(os.path.join(REF_E, CHANGE_OF[code], "trades.parquet"),
                          filters=[("entry_time", "<", pd.Timestamp(W.IS_END, unit="s", tz="UTC"))])
    ref = ref[ref.entry_time >= pd.Timestamp(g, unit="s", tz="UTC")]
    live = [r for r in rows if r.get("rp") != 1]
    t = compare.paper_trades(live, code)
    if len(t):
        ref = ref[ref.exit_time <= t.exit_time.max()]
    r = compare.cmp_trades(live, ref, code, t_from=g)
    return {k: r.get(k) for k in ("lab_trades", "ea_trades", "same_entry", "only_lab", "only_ea", "same_exit_and_reason", "entry_equal",
                                  "stop_equal", "exit_equal", "pass")}


def clean(name, exe, bars, env=None, h_pts=0, mode="fast", codes=CODES, on=False):
    """J's clean world (test_worlds.clean) with the real rules: InpScript empty, every sleeve judged"""
    files = os.path.join(OUT, name)
    t0 = time.time()
    e = dict(env or {})
    if on:
        e.update(SW_ON, MOCK_INPUT_InpK1T=k1t())
    _, out = W.run(exe, files, bars, W.FROM, W.TO, env=e, codes=[])
    rows = W.journal(files)
    g = W.go_live(rows)
    B = {s: W.Bars(p) for s, p in bars.items()}
    per, diffs, lab = {}, {}, {}
    for c in codes:
        r, d = W.real_vs_paper(rows, files, B, c, mode, h_pts=h_pts if W.SYM_OF[c] == "XAUUSD.r" else 0, go_live=g)
        per[c] = r
        diffs[c] = d
        if h_pts == 0:
            lab[c] = change_check(rows, c, g) if (on and c in CHANGE_OF) else W.lab_check(rows, c, g)
    errors = W.ev(rows, "ERROR")
    res = {"files": files, "replay": out.strip().splitlines()[-1] if out.strip() else "", "sec": round(time.time() - t0, 1), "go_live": g,
           "events": W.counts(rows), "per_sleeve": per, "diffs": diffs, "lab": lab, "errors": errors[:5]}
    res["pass"] = W.judge_clean(res, mode)
    return res, rows


def sleeve_lines(files, codes):
    out = {c: [] for c in codes}
    for f in sorted(x for x in os.listdir(os.path.join(files, "ClaudeRobot")) if x.endswith(".log")):
        for ln in open(os.path.join(files, "ClaudeRobot", f)):
            p = ln.split("|", 4)
            if len(p) > 3 and p[2] in PAPER_EV and p[3] in out:
                out[p[3]].append(ln.rstrip("\n"))
    return out


def deinit(rows):
    d = [r for r in rows if r["ev"] == "INIT" and "deinit" in r]
    return d[-1] if d else {}


def world(name, exe, bars, frm, to, env=None):
    files = os.path.join(OUT, name)
    W.run(exe, files, bars, frm, to, env=env or {}, codes=[])
    return files, W.journal(files)


PLAN0 = calendar.timegm((2012, 12, 1, 0, 0, 0))                 # server time: a plan start before the data
TRADE = {"MOCK_INPUT_InpTrade": "true", "MOCK_INPUT_InpPlanStart": str(PLAN0), "MOCK_INPUT_InpPush": "true",
         "MOCK_TIMER_CALLS": "58"}


def cut_runs(name, exe, bars, frm, t1, to, env, env2=None):
    """the same period once in one process and once cut at t1 (server): the second process starts from the mock's saved
    broker state only (as in T6); env2 is added to the second process (e.g. a symbol not synchronized after the start)"""
    fc, fr = os.path.join(OUT, name + "_continuous"), os.path.join(OUT, name + "_restarted")
    W.run(exe, fc, bars, frm, to, env=env, codes=[])
    W.run(exe, fr, bars, frm, t1, env=env, codes=[])
    W.run(exe, fr, bars, t1, to, env=dict(env, **(env2 or {})), codes=[], fresh=False)
    return fc, fr


def first_check_utc(rows, base, after):
    """the first READY or NOTREADY line of a symbol at or after `after` (UTC): the first READY check of that start"""
    r = [x["utc"] for x in rows if x["ev"] in ("READY", "NOTREADY") and x["code"] == base and x["utc"] >= after]
    return min(r) if r else None


# ------------------------------------------------------------------ the worlds of the review's fixes
def w_h2_restart(exe, bars):
    """F1: an F1E trade held by H2, one restart during the hold: adopted, closed with the paper, never at 15:55"""
    frm, t1, to = W.utc_to_srv(calendar.timegm((2018, 3, 10, 0, 0, 0))), W.utc_to_srv(calendar.timegm((2018, 3, 16, 8, 29, 0))), \
        W.utc_to_srv(calendar.timegm((2018, 3, 17, 0, 0, 0)))
    env = dict(TRADE, **SW_ON, MOCK_INPUT_InpK1T=k1t())
    fc, fr = cut_runs("h2_restart", exe, bars, frm, t1, to, env)
    rc, rr = W.journal(fc), W.journal(fr)
    u1 = W.srv_to_utc(t1)
    held = []                                                    # the continuous run's F1E trades held by H2 and open at t1
    done, _ = compare.paper_chain(rc, "F1E")
    holds = {int(r["oid"]) for r in rc if r["ev"] == "HOLD" and r["code"] == "F1E"}
    for o, (f, x) in done.items():
        if int(o) in holds and int(f["bar"]) < u1 < int(x["utc"]):
            held.append((int(o), int(f["bar"]), int(x["utc"]), int(f["side"])))
    pc, pr = W.wpos(fc, "F1E"), W.wpos(fr, "F1E")
    out = []
    for o, fb, xu, side in held:
        a = pc[(pc.side == side) & ((pc.u_in - fb).abs() <= 300)] if len(pc) else pc
        b = pr[(pr.side == side) & ((pr.u_in - fb).abs() <= 300)] if len(pr) else pr
        out.append({"oid": o, "paper_exit_utc": xu, "continuous_u_out": int(a.iloc[0].u_out) if len(a) else None,
                    "restarted_u_out": int(b.iloc[0].u_out) if len(b) and not pd.isna(b.iloc[0].get("u_out")) else None,
                    "ticket": int(b.iloc[0].position) if len(b) else None})
    seg2 = [r for r in rr if r["utc"] >= u1 and r.get("rp") != 1]
    late = [r for r in seg2 if r["ev"] == "CLOSE" and r.get("why") == "latest_exit"]
    adopt = [r for r in seg2 if r["ev"] == "ADOPT" and r["code"] == "F1E"]
    res = {"held_open_at_restart": out, "latest_exit_closes": [(r["utc"], r.get("ticket")) for r in late],
           "adopt_lines": [(r["utc"], r.get("why"), r.get("ticket")) for r in adopt], "errors": W.ev(rr, "ERROR")[:3]}
    ok = bool(out) and all(x["continuous_u_out"] is not None and x["restarted_u_out"] == x["continuous_u_out"] for x in out)
    ok = ok and not late and all(any(int(a.get("ticket", -1)) == x["ticket"] for a in adopt) for x in out) and not res["errors"]
    res["pass"] = bool(ok)
    return res


def w_notready_gate(exe, bars):
    """F1: positions of a NOT_READY sleeve close at LatestExit only after the first READY check of the start and 10 min of
    NOT_READY; an ORX trade whose exit falls in the gold holiday closure of Presidents' Day 2020"""
    frm = W.utc_to_srv(calendar.timegm((2020, 2, 10, 0, 0, 0)))
    t1 = W.utc_to_srv(calendar.timegm((2020, 2, 17, 19, 55, 0)))   # 14:55 New York, inside the closure [13:00, 18:00)
    to = W.utc_to_srv(calendar.timegm((2020, 2, 19, 0, 0, 0)))
    u1 = W.srv_to_utc(t1)
    res = {}
    fc, fr = cut_runs("gate_short", exe, bars, frm, t1, to, TRADE, {"MOCK_UNSYNC_XAUUSD.r": f"{t1}-{t1 + 300}"})
    rc, rr = W.journal(fc), W.journal(fr)
    done, _ = compare.paper_chain(rc, "ORX")
    tr = [(int(o), int(f["bar"]), int(x["utc"]), int(f["side"])) for o, (f, x) in done.items() if int(f["bar"]) < u1 < int(x["utc"])]
    pc, pr = W.wpos(fc, "ORX"), W.wpos(fr, "ORX")
    rows = []
    for o, fb, xu, side in tr:
        a = pc[(pc.side == side) & ((pc.u_in - fb).abs() <= 300)] if len(pc) else pc
        b = pr[(pr.side == side) & ((pr.u_in - fb).abs() <= 300)] if len(pr) else pr
        rows.append({"oid": o, "paper_exit_utc": xu, "continuous_u_out": int(a.iloc[0].u_out) if len(a) else None,
                     "restarted_u_out": int(b.iloc[0].u_out) if len(b) and not pd.isna(b.iloc[0].get("u_out")) else None})
    seg2 = [r for r in rr if r["utc"] >= u1 and r.get("rp") != 1]
    late = [r for r in seg2 if r["ev"] == "CLOSE" and r.get("why") == "latest_exit"]
    fc_xau = first_check_utc(rr, "XAUUSD", u1)
    ready = [r["utc"] for r in seg2 if r["ev"] == "READY" and r["code"] == "XAUUSD"]
    adopt = [r for r in seg2 if r["ev"] == "ADOPT" and r["code"] == "ORX"]
    res["short"] = {"open_at_restart": rows, "first_check_utc": fc_xau, "ready_utc": ready[:1],
                    "adopted": [(r["utc"], r.get("why")) for r in adopt], "latest_exit_closes": [r["utc"] for r in late]}
    ok_a = bool(rows) and not late and bool(adopt) and bool(ready) and all(adopt[0]["utc"] >= ready[0] for _ in [0]) and \
        all(x["continuous_u_out"] is not None and x["restarted_u_out"] == x["continuous_u_out"] for x in rows)
    # gold not synchronized for 30 min: NOT_READY lasts; LatestExit (12:59 New York, passed) closes it, 10 min after the first check
    _, fr2 = cut_runs("gate_long", exe, bars, frm, t1, to, TRADE, {"MOCK_UNSYNC_XAUUSD.r": f"{t1}-{t1 + 1800}"})
    rr2 = W.journal(fr2)
    seg2b = [r for r in rr2 if r["utc"] >= u1 and r.get("rp") != 1]
    late2 = [r["utc"] for r in seg2b if r["ev"] == "CLOSE" and r.get("why") == "latest_exit" and r.get("code") == "ORX"]
    fc2 = first_check_utc(rr2, "XAUUSD", u1)
    res["long"] = {"first_check_utc": fc2, "latest_exit_closes": late2, "wait_s": (late2[0] - fc2) if late2 and fc2 else None}
    ok_b = bool(late2) and fc2 is not None and 600 <= late2[0] - fc2 <= 660
    res["errors"] = (W.ev(rr, "ERROR") + W.ev(rr2, "ERROR"))[:3]
    res["pass"] = bool(ok_a and ok_b and not res["errors"])
    return res


def w_crypto_weekend(exe, bars):
    """F2: BTC and ETH quoted all weekend (the mask drops the bars): no crypto order in the masked weekend"""
    fri = calendar.timegm((2021, 7, 30, 0, 0, 0))                   # server clock: Friday 2021-07-30
    paths, added = {}, {}
    for s_ in ("BTCUSD.r", "ETHUSD.r"):
        d, rec = W.read_bars(bars[s_])
        src = rec[(rec["t"] >= fri) & (rec["t"] < fri + 86400)]
        sat, sun = src.copy(), src.copy()
        sat["t"] += 86400
        sun["t"] += 2 * 86400
        had = int(((rec["t"] >= fri + 86400) & (rec["t"] < fri + 3 * 86400)).sum())
        new = np.sort(np.concatenate([rec, sat, sun]), order="t")
        assert had == 0 and (np.diff(new["t"]) > 0).all()
        p_ = os.path.join(OUT, "bars", f"{s_}_weekend.bin")
        os.makedirs(os.path.dirname(p_), exist_ok=True)
        W.write_bars(p_, d, new)
        paths[s_], added[s_] = p_, int(len(sat) + len(sun))
    frm, to = calendar.timegm((2021, 7, 26, 0, 0, 0)), calendar.timegm((2021, 8, 3, 0, 0, 0))
    env = dict(TRADE, MOCK_INPUT_InpPush="false")
    f0, r0 = world("weekend_ref", exe, bars, frm, to, env)
    f1, r1 = world("weekend", exe, dict(bars, **paths), frm, to, env)
    lo, hi = W.srv_to_utc(fri + 23 * 3600 + 55 * 60), W.srv_to_utc(fri + 3 * 86400)    # Friday 23:55 server to Monday 00:00
    crypto = ("BKB", "BKE", "F1B", "F1E", "NQB")
    sent = [r for r in r1 if r["ev"] in ("SIZE", "SEND", "FILL") and r["code"] in crypto and lo <= r["utc"] < hi and r.get("rp") != 1]
    ords = [r for r in r1 if r["ev"] == "DEC" and r.get("what") == "ord" and r["code"] in ("BKB", "BKE") and lo <= int(r["tf"]) < hi]
    m0, m1 = deinit(r0), deinit(r1)
    l0, l1 = sleeve_lines(f0, CODES), sleeve_lines(f1, CODES)
    p0, p1 = W.wpos(f0), W.wpos(f1)
    key = lambda p: sorted((r.code, r.side, int(r.u_in), int(r.u_out) if not pd.isna(r.u_out) else -1, float(r.vol)) for r in p.itertuples()) if len(p) else []
    res = {"bars_added": added, "masked_added": {s_[:6]: m1.get(f"masked_{s_[:6]}", -1) - m0.get(f"masked_{s_[:6]}", -1) for s_ in paths},
           "orders_in_the_masked_weekend": [(r["code"], r["oid"], r["tf"], r["tt"]) for r in ords],
           "crypto_size_send_fill_in_the_masked_weekend": [(r["ev"], r["code"], r["utc"]) for r in sent][:5],
           "same_paper_lines": {c: l0[c] == l1[c] for c in CODES}, "same_positions": key(p0) == key(p1), "positions": int(len(p1)),
           "errors": W.ev(r1, "ERROR")[:3]}
    res["pass"] = bool(all(res["masked_added"][s_[:6]] == added[s_] for s_ in paths) and ords and not sent and all(res["same_paper_lines"].values())
                       and res["same_positions"] and not res["errors"])
    return res


def w_shadow(exe, bars):
    """F6: the observer (off the VPS, demo, InpTrade false) and the VPS copy with InpTrade false write the same intents"""
    frm, to = calendar.timegm((2021, 3, 1, 0, 0, 0)), calendar.timegm((2021, 3, 8, 0, 0, 0))
    base = {"MOCK_INPUT_InpTrade": "false", "MOCK_INPUT_InpPlanStart": str(PLAN0), "MOCK_INPUT_InpPush": "false"}
    fo, ro = world("shadow_observer", exe, bars, frm, to, dict(base, MOCK_VPS="0"))
    fv, rv = world("shadow_vps", exe, bars, frm, to, dict(base, MOCK_VPS="1"))
    keep = ("SIZE", "MISSED", "DEC", "PFILL", "PEXIT", "PSTOP", "PREVISE", "PVOID", "PREFUSE", "HOLD")

    def lines(files):
        out = []
        for f in sorted(x for x in os.listdir(os.path.join(files, "ClaudeRobot")) if x.endswith(".log")):
            for ln in open(os.path.join(files, "ClaudeRobot", f)):
                p_ = ln.split("|", 4)
                if len(p_) > 3 and p_[2] in keep:
                    out.append(ln.rstrip("\n"))
        return out
    lo, lv = lines(fo), lines(fv)
    io = [r for r in ro if r["ev"] == "INIT" and "observer" in r]
    iv = [r for r in rv if r["ev"] == "INIT" and "observer" in r]
    size_live = [r for r in ro if r["ev"] == "SIZE" and r.get("rp") != 1]
    res = {"observer_flags": [io[0].get("observer"), iv[0].get("observer")] if io and iv else None, "lines": [len(lo), len(lv)],
           "identical": lo == lv, "first_difference": next(([a, b] for a, b in zip(lo, lv) if a != b), None),
           "live_size_lines": len(size_live), "skips": sorted({str(r.get("skip")) for r in size_live}),
           "missed_exited_market": sum(1 for r in ro if r["ev"] == "MISSED" and r.get("reason") == "exited" and r.get("rp") != 1),
           "sends": sum(1 for r in ro + rv if r["ev"] == "SEND")}
    res["pass"] = bool(res["observer_flags"] == [1, 0] and res["identical"] and len(size_live) > 0 and res["skips"] == ["notrade"]
                       and res["sends"] == 0)
    return res


def w_gfp_session(exe, bars):
    """F7: FP's Friday gold session ending at 16:50 New York is accepted; one ending at 16:40 skips the Friday, pushed"""
    frm, to = calendar.timegm((2021, 3, 8, 0, 0, 0)), calendar.timegm((2021, 3, 13, 0, 0, 0))
    fri_1330 = int(pd.Timestamp("2021-03-12 13:30", tz=NY).tz_convert("UTC").value // 10 ** 9)
    env = dict(TRADE, MOCK_INPUT_InpPush="true")
    out = {}
    for tag, end in (("none", None), ("1650", "2350"), ("1640", "2340")):
        files = os.path.join(OUT, "gfp_session_" + tag)
        faults = None if end is None else [f"0 session XAUUSD.r 5 0100 {end}"]
        W.run(exe, files, bars, frm, to, env=env, codes=[], faults=faults)
        rows = W.journal(files)
        dec = [r for r in rows if r["ev"] == "DEC" and r["code"] == "GFP" and r["utc"] == fri_1330 and r.get("rp") != 1]
        pu = [q for q in W.pushes(files) if "GFP" in q and "seance" in q]
        out[tag] = {"orders": sum(1 for r in dec if r.get("what") == "ord"),
                    "skips": [(r.get("v1"), r.get("v2")) for r in dec if r.get("what") == "info" and int(r.get("side", 9)) == 0],
                    "session_pushes": pu[:2], "faults": W.fault_counts(files)}
    res = {"runs": out}
    res["pass"] = bool(out["none"]["orders"] == 1 and out["1650"]["orders"] == 1 and not out["1650"]["skips"] and not out["1650"]["session_pushes"]
                       and out["1640"]["orders"] == 0 and len(out["1640"]["skips"]) == 1 and int(out["1640"]["skips"][0][0]) == 4
                       and len(out["1640"]["session_pushes"]) == 1)
    return res


# ------------------------------------------------------------------ the three rule worlds
def w_gfp_holiday(exe, bars):
    """R8: GFP skips Good Friday 2021-04-02 although gold is quoted (bars of 2021-03-26 copied one week on)"""
    d, rec = W.read_bars(bars["XAUUSD.r"])
    a, b = calendar.timegm((2021, 3, 26, 0, 0, 0)), calendar.timegm((2021, 3, 27, 0, 0, 0))
    src = rec[(rec["t"] >= a) & (rec["t"] < b)].copy()
    src["t"] += 7 * 86400
    had = int(((rec["t"] >= a + 7 * 86400) & (rec["t"] < b + 7 * 86400)).sum())
    new = np.sort(np.concatenate([rec, src]), order="t")
    p = os.path.join(OUT, "bars", "XAUUSD.r_goodfriday.bin")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    W.write_bars(p, d, new)
    bb = dict(bars, **{"XAUUSD.r": p})
    files, rows = world("gfp_holiday", exe, bb, calendar.timegm((2021, 3, 29, 0, 0, 0)), calendar.timegm((2021, 4, 6, 0, 0, 0)))
    day0 = pd.Timestamp("2021-04-02 00:00", tz=NY)
    lo, hi = int(day0.tz_convert("UTC").value // 10 ** 9), int((day0 + pd.Timedelta(days=1)).tz_convert("UTC").value // 10 ** 9)
    dec = [r for r in rows if r["ev"] == "DEC" and r["code"] == "GFP" and lo <= r["utc"] < hi]
    skip = [r for r in dec if r.get("what") == "info" and int(r.get("side", 9)) == 0]
    ords = [r for r in dec if r.get("what") == "ord"]
    fills = [r for r in rows if r["ev"] == "PFILL" and r["code"] == "GFP" and lo <= r["utc"] < hi]
    pos = W.wpos(files, "GFP")
    pos_day = pos[(pos.u_in >= lo) & (pos.u_in < hi)] if len(pos) else pos
    t1330 = int(pd.Timestamp("2021-04-02 13:30", tz=NY).tz_convert("UTC").value // 10 ** 9)
    res = {"bars_added": int(len(src)), "bars_there_before": had, "gfp_dec_lines": len(dec),
           "skip_lines": [{"utc": r["utc"], "v1": r.get("v1"), "v2": r.get("v2")} for r in skip], "orders": len(ords),
           "paper_fills": len(fills), "positions": int(len(pos_day)), "errors": W.ev(rows, "ERROR")[:3]}
    res["pass"] = bool(had == 0 and len(src) > 600 and len(skip) == 1 and skip[0]["utc"] == t1330 and not ords and not fills
                       and len(pos_day) == 0 and not res["errors"])
    return res


def w_us100_half(exe, bars):
    """P6: US100 quoted after 13:15 on the NYSE half day 2021-11-26: masked, and N30, OC4, NQB unchanged"""
    d, rec = W.read_bars(bars["US100.r"])
    a, b = ny_srv("2021-11-19", 13, 16), ny_srv("2021-11-19", 16, 15)
    src = rec[(rec["t"] >= a) & (rec["t"] < b)].copy()
    src["t"] += 7 * 86400
    had = int(((rec["t"] >= a + 7 * 86400) & (rec["t"] < b + 7 * 86400)).sum())
    new = np.sort(np.concatenate([rec, src]), order="t")
    p = os.path.join(OUT, "bars", "US100.r_halfday.bin")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    W.write_bars(p, d, new)
    frm, to = calendar.timegm((2021, 11, 24, 0, 0, 0)), calendar.timegm((2021, 11, 30, 12, 0, 0))
    f0, r0 = world("us100_half_ref", exe, bars, frm, to)
    f1, r1 = world("us100_half", exe, dict(bars, **{"US100.r": p}), frm, to)
    l0, l1 = sleeve_lines(f0, ["N30", "OC4", "NQB"]), sleeve_lines(f1, ["N30", "OC4", "NQB"])
    m0, m1 = deinit(r0).get("masked_US100", -1), deinit(r1).get("masked_US100", -1)
    res = {"bars_added": int(len(src)), "bars_there_before": had, "masked_US100_without": m0, "masked_US100_with": m1,
           "same_lines": {c: l0[c] == l1[c] for c in l0}, "lines": {c: len(l0[c]) for c in l0},
           "errors": W.ev(r1, "ERROR")[:3]}
    res["pass"] = bool(had == 0 and len(src) > 100 and m1 - m0 == len(src) and all(res["same_lines"].values()) and not res["errors"])
    return res


def w_orx_spike(exe, bars, clean_rows):
    """9.5: a raw spread spike inside an ORX London range widens its levels and stop; the real trade follows the paper"""
    ords = [r for r in clean_rows if r["ev"] == "DEC" and r["code"] == "ORX" and r.get("what") == "ord" and r["utc"] >= W.FROM + 60 * 86400]
    o = ords[0]
    day = pd.Timestamp(o["utc"], unit="s", tz="UTC").tz_convert("Europe/London").normalize()
    r0 = int(day.tz_convert("UTC").value // 10 ** 9)                      # London 00:00 of the order's day, UTC
    d, rec = W.read_bars(bars["XAUUSD.r"])
    # the range bar whose ask high makes H: its raw spread gets a spike, so that H moves by the spike itself
    rng_m = (rec["t"] >= W.utc_to_srv(r0)) & (rec["t"] < W.utc_to_srv(r0 + 7 * 3600))
    ix = np.flatnonzero(rng_m)
    k = int(ix[np.argmax(rec["h"][ix] + rec["s"][ix])])
    t3 = W.srv_to_utc(int(rec["t"][k]))
    rec2 = rec.copy()
    spike = 50                                                            # points: 0.50 USD on a raw spread of 10-20 points
    rec2["s"][k] += spike
    p = os.path.join(OUT, "bars", "XAUUSD.r_spike.bin")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    W.write_bars(p, d, rec2)

    def levels(rr):
        """the range as the rule reads it: paper ask high = (bid high + spread) / 100, bid low / 100 (h = 0 here)"""
        m = (rr["t"] >= W.utc_to_srv(r0)) & (rr["t"] < W.utc_to_srv(r0 + 7 * 3600))
        H = float(np.max((rr["h"][m] + rr["s"][m]) / 100.0))
        L = float(np.min(rr["l"][m] / 100.0))
        buf = 0.1 * (H - L) + 0.0
        return H, L, H + buf, L - buf
    H0, L0, buy0, sell0 = levels(rec)
    H, L, buy, sell = levels(rec2)
    # the first bar of [07:00, 12:00) London that touches a level (both: the nearer to the mid open, a tie long)
    m = (rec2["t"] >= W.utc_to_srv(r0 + 7 * 3600)) & (rec2["t"] < W.utc_to_srv(r0 + 12 * 3600))
    touch = None
    for x in rec2[m]:
        ah, bl = (x["h"] + x["s"]) / 100.0, x["l"] / 100.0
        up, dn = ah >= buy, bl <= sell
        if up or dn:
            side = 1 if up else -1
            if up and dn:
                mo = 0.5 * ((x["o"] + x["s"]) / 100.0 + x["o"] / 100.0)
                side = 1 if abs(buy - mo) <= abs(mo - sell) else -1
            touch = (W.srv_to_utc(int(x["t"])), side)
            break
    files, rows = world("orx_spike", exe, dict(bars, **{"XAUUSD.r": p}), W.utc_to_srv(r0) - 6 * 3600, W.utc_to_srv(r0 + 3 * 86400))
    o2 = [r for r in rows if r["ev"] == "DEC" and r["code"] == "ORX" and r.get("what") == "ord" and r0 <= r["utc"] < r0 + 86400]
    B = {s: W.Bars(q) for s, q in dict(bars, **{"XAUUSD.r": p}).items()}
    rvp, diffs = W.real_vs_paper(rows, files, B, "ORX", "fast", go_live=W.go_live(rows))
    res = {"day": str(day.date()), "spiked_bar_utc": t3, "spike_points": spike, "range_without": [H0, L0], "range_with": [H, L],
           "clean_order": {"side": o["side"], "lv": o["lv"], "st": o["st"]},
           "spiked_orders": [{"side": r["side"], "lv": r["lv"], "st": r["st"], "utc": r["utc"]} for r in o2],
           "expected": {"buy": buy, "sell": sell, "touch": touch}, "real_vs_paper": rvp, "diffs": diffs[:5],
           "errors": W.ev(rows, "ERROR")[:3]}
    clean_ok = o["lv"] == (buy0 if o["side"] > 0 else sell0) and o["st"] == (sell0 if o["side"] > 0 else buy0)
    if touch is None:
        same = len(o2) == 0
    else:
        q = o2[0] if o2 else None
        want_lv, want_st = (buy, sell) if touch[1] > 0 else (sell, buy)
        same = q is not None and len(o2) == 1 and q["utc"] == touch[0] and q["side"] == touch[1] and q["lv"] == want_lv and q["st"] == want_st
    res["clean_order_as_computed"] = bool(clean_ok)
    res["spiked_order_as_computed"] = bool(same)
    res["wider"] = bool(H > H0 and (buy - sell) > (buy0 - sell0))
    res["pass"] = bool(clean_ok and same and res["wider"] and rvp["n_diffs"] == 0 and not res["errors"])
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--no-sanitize", action="store_true")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args(argv)
    want = set(a.only.split(",")) if a.only else None
    sel = lambda n: want is None or n in want
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    exes, warn = {}, {}
    exes["plain"], w = build(DIST, name="test_wr_plain")
    warn["plain"] = len(w)
    exes["h6"], w = build(DIST, name="test_wr_h6", defines=["CR_XAU_COMM_PTS=6"])
    warn["h6"] = len(w)
    if not a.no_sanitize and sel("clean_san"):
        exes["san"], w = build(DIST, name="test_wr_san", sanitize=True)
        warn["san"] = len(w)
    bars = W.bar_paths()
    summary = {"dist_cr_build": open(DIST).readline().strip(), "warnings": warn, "worlds": {}}
    ok = all(v == 0 for v in warn.values())
    clean_rows = None
    if sel("clean_fast") or sel("orx_spike") or sel("clean_san"):
        r, clean_rows = clean("clean_fast", exes["plain"], bars)
        summary["worlds"]["clean_fast"] = {k: v for k, v in r.items() if k not in ("diffs", "files")}
        summary["worlds"]["clean_fast"]["unexplained"] = r.get("unexplained")
        ok &= r["pass"]
        log(f"{'PASS' if r['pass'] else 'FAIL'} clean_fast {r['sec']} s")
    if sel("clean_on"):
        r, _ = clean("clean_on", exes["plain"], bars, on=True)
        summary["worlds"]["clean_on"] = {k: v for k, v in r.items() if k not in ("diffs", "files")}
        ok &= r["pass"]
        log(f"{'PASS' if r['pass'] else 'FAIL'} clean_on {r['sec']} s")
    if sel("clean_tick"):
        r, _ = clean("clean_tick", exes["plain"], bars, env={"MOCK_TICK": "1"}, mode="tick")
        summary["worlds"]["clean_tick"] = {k: v for k, v in r.items() if k not in ("diffs", "files", "lab")}
        ok &= r["pass"]
        log(f"{'PASS' if r['pass'] else 'FAIL'} clean_tick {r['sec']} s")
        shutil.rmtree(os.path.join(OUT, "clean_tick"), ignore_errors=True)
    if sel("clean_h"):
        hb = dict(bars, **{"XAUUSD.r": W.h_bars(bars["XAUUSD.r"])})
        r, _ = clean("clean_h", exes["h6"], hb, h_pts=3, codes=["GFP", "D4H", "ORX"])
        summary["worlds"]["clean_h"] = {k: v for k, v in r.items() if k not in ("diffs", "files", "lab")}
        ok &= r["pass"]
        log(f"{'PASS' if r['pass'] else 'FAIL'} clean_h {r['sec']} s")
        shutil.rmtree(os.path.join(OUT, "clean_h"), ignore_errors=True)
    if "san" in exes:
        t1 = time.time()
        W.run(exes["san"], os.path.join(OUT, "clean_san"), bars, W.FROM, W.TO, env={"ASAN_OPTIONS": "detect_leaks=1"}, codes=[])
        same = W.same_dirs(os.path.join(OUT, "clean_fast", "ClaudeRobot"), os.path.join(OUT, "clean_san", "ClaudeRobot")) if hasattr(W, "same_dirs") else False
        d0, d1 = W.deals(os.path.join(OUT, "clean_fast")), W.deals(os.path.join(OUT, "clean_san"))
        same_deals = d0.equals(d1)
        summary["worlds"]["clean_san"] = {"identical_journal": bool(same), "identical_deals": bool(same_deals), "sec": round(time.time() - t1, 1),
                                          "pass": bool(same and same_deals)}
        ok &= same and same_deals
        log(f"{'PASS' if same and same_deals else 'FAIL'} clean_san {summary['worlds']['clean_san']['sec']} s")
        shutil.rmtree(os.path.join(OUT, "clean_san"), ignore_errors=True)
    for name, fn in (("gfp_holiday", w_gfp_holiday), ("us100_half", w_us100_half), ("h2_restart", w_h2_restart),
                     ("notready_gate", w_notready_gate), ("crypto_weekend", w_crypto_weekend), ("shadow", w_shadow),
                     ("gfp_session", w_gfp_session)):
        if sel(name):
            t1 = time.time()
            r = fn(exes["plain"], bars)
            r["sec"] = round(time.time() - t1, 1)
            summary["worlds"][name] = r
            ok &= r["pass"]
            log(f"{'PASS' if r['pass'] else 'FAIL'} {name} {r['sec']} s")
    if sel("orx_spike") and clean_rows is not None:
        t1 = time.time()
        r = w_orx_spike(exes["plain"], bars, clean_rows)
        r["sec"] = round(time.time() - t1, 1)
        summary["worlds"]["orx_spike"] = r
        ok &= r["pass"]
        log(f"{'PASS' if r['pass'] else 'FAIL'} orx_spike {r['sec']} s")
    summary["pass"] = bool(ok)
    summary["sec"] = round(time.time() - t0, 1)
    with open(os.path.join(OUT, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1, default=str)
    n = len(summary["worlds"])
    log(f"test_worlds_rules: {sum(1 for v in summary['worlds'].values() if v.get('pass'))}/{n} worlds passed, warnings {warn}, "
        f"{summary['sec']} s")
    if not a.keep:
        for d in os.listdir(OUT):
            if os.path.isdir(os.path.join(OUT, d)):
                shutil.rmtree(os.path.join(OUT, d), ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
