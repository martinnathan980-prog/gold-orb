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
    for name, fn in (("gfp_holiday", w_gfp_holiday), ("us100_half", w_us100_half)):
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
