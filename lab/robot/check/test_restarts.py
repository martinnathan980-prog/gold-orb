"""T6 restarts (step K): the shipped single file restarted 100 times per sleeve from SPEC 2.2's depth only, with 10
outages of 1-6 h, switches off and on: the later paper trades are unchanged, the real positions follow SPEC 4.8.

    python3 -I lab/robot/check/test_restarts.py [--per-sleeve 100] [--outages 10] [--only off|on]
                                                [--from 2013-01-01 --to 2022-01-01] [--analyse] [--keep]

The EA: dist/ClaudeRobot.mq5, harness build (as test_accept.py). It trades (InpTrade true) on a demo account in the
replay mock: 100,000 EUR, InpPlanStart before the data, F3S, the in-sample bars of the four symbols. Per switch setting
(off: InpK1 = InpH2 = InpS075 = 0; on: 1, InpK1T = the lab's in-sample folds):
  continuous  one process over the whole period: the reference.
  restarts    the same period cut into processes (MOCK_FROM / MOCK_TO): each new process starts with the mock's saved
              broker state (positions, orders, deals, balance) and nothing else; the EA rebuilds everything from the
              broker, its bars from the depth only (120 days of gold, 60 of the others). Restart points, for each of the
              ten sleeves, from the continuous run: 50 inside its open paper trades, 30 one to ten minutes before one of
              its decisions, 20 at random weekday minutes (points closer than 10 min merged); 10 of them are outages:
              the next process starts 1 to 6 hours later (the mock's broker stops keep working meanwhile).
Checks:
  1. Later paper trades unchanged: every paper trade (PFILL then PEXIT or PREVISE; PVOID dropped) that ends after the
     first restart, taken from the first process that finishes it (a later process's replay of an old trade is not a
     later trade), equals the continuous run's trade of the same oid: fill stamp, bar and price, side, initial stop, exit
     event, stamp, price and reason, bit for bit; none missing, none extra.
  2. Every process: SELFTEST ok, one REBUILD, from the depth only (at most 121 days of minutes), no ERROR.
  3. Positions (SPEC 4.8): never two positions of one sleeve at once, no DUP; every robot position open across a
     restart is adopted (ADOPT) or closed with a CLOSE or ORPHAN line in the next process; ORPHAN only after an outage
     (its paper trade ended while the EA was down), when its paper trade ended during the start-up, or when it ended
     before the restart while its close was still waiting for the market to reopen (the continuous run closes it at the
     reopening, the new process at its first reconcile); the real trades equal the continuous run's (entry and exit time and
     price, lots), except where an entry or exit falls in an outage or in a start's start-up window (from the restart to
     two minutes after its first live barrier), or where only the lots differ because the balance path changed after
     such a difference (each counted with its cause).
  4. No EA-initiated close against the paper (review F1, F5): a close the EA itself decides in a start-up window
     (CLOSE why=latest_exit or why=orphan) of a position whose paper trade (the continuous run's trade of that sleeve and
     side filled within 5 min of the position's entry) is still open at that moment fails the test. The start-up
     windows are reported apart: entries delayed by a start, exits in a start, and these EA-initiated closes.
Outputs: check/out/test_restarts/summary.json, and <setting>_data.json.gz (what the checks read; --analyse checks it
again without replaying).
"""
import argparse
import calendar
import glob
import gzip
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.dont_write_bytecode = True
os.environ.setdefault("NUMBA_CACHE_DIR", "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/numba")
HERE = os.path.dirname(os.path.abspath(__file__))
ROBOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import compare  # noqa: E402
import test_worlds as W  # noqa: E402  (step J's helpers: positions from the mock's deals, clock conversions)
from build import build  # noqa: E402

OUT = os.path.join(HERE, "out", "test_restarts")
DIST = os.path.join(ROBOT, "dist", "ClaudeRobot.mq5")
SYMS = W.SYMS
CODES = W.CODES
FOL_EV = ("ADOPT", "ORPHAN", "DUP", "MISSED", "CLOSE", "SLFIX", "REFUSED", "ERROR", "REBUILD", "SELFTEST")
PLAN_START = calendar.timegm((2012, 12, 1, 0, 0, 0))          # server time, before the data
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
F_KEYS = ("utc", "bar", "px", "st0", "side")
REL = 1e-12                             # SPEC 7: rolling values and the stops built on them
LATE_BOOKING = 4 * 86400                # an exit can be journaled after its stamp: a PREVISE (x + 30 min, after a weekend), an exit
                                        # bar whose barrier falls in the next process
X_KEYS = ("utc", "ev", "px", "reason")


def log(m):
    print(m, flush=True)


def inputs(sw, k1t):
    base = {"MOCK_INPUT_InpTrade": "true", "MOCK_INPUT_InpPlanStart": str(PLAN_START), "MOCK_INPUT_InpPush": "false",
            "MOCK_BALANCE": "100000", "MOCK_QUIET": "1", "MOCK_SYMS": ",".join(SYMS), **W.F3S_PRESET}
    sws = {"off": ("0", ""), "on": ("1", k1t)}[sw]
    base.update({"MOCK_INPUT_InpK1": sws[0], "MOCK_INPUT_InpH2": sws[0], "MOCK_INPUT_InpS075": sws[0], "MOCK_INPUT_InpK1T": sws[1]})
    for s, p in W.bar_paths().items():
        base[f"MOCK_BARS_{s}"] = p
    return base


def one_process(exe, files, env, frm=None, to=None):
    e = dict(ENV, MOCK_FILES=files, **env)
    if frm is not None:
        e["MOCK_FROM"] = str(int(frm))
    if to is not None:
        e["MOCK_TO"] = str(int(to))
    r = subprocess.run([exe], env=e, capture_output=True, text=True, timeout=7200)
    if r.returncode:
        raise RuntimeError(f"replay failed ({r.returncode}) from {frm} to {to}: {r.stdout[-1500:]} {r.stderr[-1500:]}")
    return r.stdout.strip()


def drop_logs(files):
    """the EA appends to its daily logs and never reads them: removed after each process so that a thousand rebuilds do
    not fill the disk (what the checks need is kept first)"""
    for f in glob.glob(os.path.join(files, "ClaudeRobot", "*.log")):
        os.remove(f)


def trades_of(rows, lo):
    """{code: {oid: [fill fields, exit fields]}} of the trades finished in these rows whose exit is at or after lo"""
    out = {}
    for c in CODES:
        done, _ = compare.paper_chain(rows, c)
        out[c] = {str(o): [{k: f.get(k) for k in F_KEYS}, {k: x.get(k) for k in X_KEYS}] for o, (f, x) in done.items() if x["utc"] >= lo}
    return out


def fol_rows(rows):
    """the follower's lines the checks read, and the sizing skips (SIZE lines whose skip is not none)"""
    return [{k: v for k, v in r.items() if k in ("utc", "ev", "code", "ticket", "why", "reason", "rp", "from", "to", "minutes", "ok",
                                                  "what", "oid", "skip")}
            for r in rows if r["ev"] in FOL_EV or (r["ev"] == "SIZE" and r.get("skip") not in (None, "none"))]


def pos_records(files):
    p = W.positions(files)
    if not len(p):
        return []
    cols = [c for c in ("position", "code", "side", "u_in", "px_in", "vol", "u_out", "px_out", "reason_out", "t_in", "t_out") if c in p]
    recs = p[cols].to_dict("records")
    for r in recs:
        for k, v in list(r.items()):
            if isinstance(v, float) and not np.isfinite(v):
                r[k] = None
            elif isinstance(v, (np.integer,)):
                r[k] = int(v)
            elif isinstance(v, (np.floating,)):
                r[k] = float(v)
    return recs


# ------------------------------------------------------------------ the continuous run and the restart points
def continuous(exe, sw, env, frm, to):
    files = os.path.join(OUT, f"{sw}_continuous")
    if os.path.isdir(files):
        shutil.rmtree(files)
    os.makedirs(files)
    t0 = time.time()
    out = one_process(exe, files, env, frm, to)
    rows = compare.read_journal(files)
    dec = {c: sorted(int(r["utc"]) for r in rows if r["ev"] == "DEC" and r["code"] == c and r.get("what") == "ord") for c in CODES}
    data = {"trades": trades_of(rows, -1), "dec": dec, "fol": fol_rows(rows), "pos": pos_records(files),
            "wall_s": round(time.time() - t0, 1), "mock": out}
    drop_logs(files)
    return data


def points(cont, per, n_out, seed):
    rng = np.random.default_rng(seed)
    fills = [f["utc"] for c in CODES for f, _ in cont["trades"][c].values()]
    reb = [r for r in cont["fol"] if r["ev"] == "REBUILD"]
    live0 = int(reb[0]["to"]) + 60 if reb else min(fills)          # the continuous run's first live barrier
    first_utc, last_utc = max(min(fills), live0), max(fills)
    per_sleeve, pts = {}, []
    n_in, n_dec = per // 2, per * 3 // 10
    n_rand = per - n_in - n_dec
    for c in CODES:
        tr = sorted((int(f["utc"]), int(x["utc"])) for f, x in cont["trades"][c].values())
        long_ = [(a, b) for a, b in tr if b - a >= 360 and a > first_utc + 3 * 86400]
        mine = []
        for k in rng.choice(len(long_), size=min(n_in, len(long_)), replace=False):
            a, b = long_[k]
            mine.append((int(rng.integers(a + 120, b - 120)) // 60 * 60, "in_trade"))
        ds = [t for t in cont["dec"][c] if t > first_utc + 3 * 86400]
        for k in rng.choice(len(ds), size=min(n_dec, len(ds)), replace=False):
            mine.append((ds[k] - 60 * int(rng.integers(1, 11)), "before_decision"))
        while sum(1 for _, w in mine if w == "random") < n_rand:
            t = int(rng.integers(first_utc + 3 * 86400, last_utc - 86400)) // 60 * 60
            if pd.Timestamp(t, unit="s", tz="UTC").dayofweek < 5:
                mine.append((t, "random"))
        per_sleeve[c] = mine
        pts += [(t, w, c) for t, w in mine]
    pts.sort()
    kept = []
    for t, w, c in pts:
        if kept and t - kept[-1][0] < 600:
            continue
        kept.append((t, w, c))
    idx = np.linspace(len(kept) // 20, len(kept) - 1 - len(kept) // 20, n_out).astype(int) if n_out else []
    outage = {int(i): 60 * int(rng.integers(60, 361)) for i in idx}
    segs, last_end = [], None
    for k, (t, w, c) in enumerate(kept):
        if last_end is not None and t < last_end + 600:
            continue
        L = outage.get(k, 0)
        segs.append({"stop": int(t), "next_start": int(t + L), "kind": w, "for": c, "outage_s": int(L)})
        last_end = t + L
    return {c: len(v) for c, v in per_sleeve.items()}, segs


# ------------------------------------------------------------------ the restarted run
def restarted(exe, sw, env, segs, frm, to):
    files = os.path.join(OUT, f"{sw}_restarts")
    if os.path.isdir(files):
        shutil.rmtree(files)
    os.makedirs(os.path.join(files, "_mock"))
    starts = [frm] + [W.utc_to_srv(s["next_start"]) for s in segs]
    stops = [W.utc_to_srv(s["stop"]) for s in segs] + [to]
    procs = []
    t0 = time.time()
    for k, (a, b) in enumerate(zip(starts, stops)):
        one_process(exe, files, env, a, b)
        rows = compare.read_journal(files)
        drop_logs(files)
        lo = segs[k - 1]["stop"] - LATE_BOOKING if k > 0 else -1
        reb = [r for r in rows if r["ev"] == "REBUILD"]
        st = [r for r in rows if r["ev"] == "SELFTEST"]
        procs.append({"k": k, "trades": trades_of(rows, lo), "fol": fol_rows(rows), "rebuilds": len(reb),
                      "rebuild_to": reb[0]["to"] if reb else None, "rebuild_minutes": reb[0]["minutes"] if reb else None,
                      "selftest_ok": bool(st and st[0].get("ok") == 1),
                      "errors": [str(r.get("what")) for r in rows if r["ev"] == "ERROR"][:3]})
        if k % 100 == 0:
            log(f"  {sw}: process {k + 1}/{len(starts)} ({time.time() - t0:.0f} s)")
    return procs, pos_records(files), round(time.time() - t0, 1)


# ------------------------------------------------------------------ checks
def cmp_paper(cont, procs, segs, code):
    e0 = segs[0]["stop"] if segs else 1 << 62           # the trades that end after the first restart are the later ones
    later = {}
    for p in procs:
        for o, v in p["trades"][code].items():
            if o not in later:
                later[o] = v + [p["k"]]
    want = {o: v for o, v in cont["trades"][code].items() if v[1]["utc"] >= e0}
    got = {o: v for o, v in later.items() if v[1]["utc"] >= e0}
    same, near, diff, missing = 0, [], [], []
    for o, (f, x) in want.items():
        g = got.get(o)
        if g is None:
            missing.append(int(o))
            continue
        exact = [k for k in ("utc", "bar", "side") if f.get(k) != g[0].get(k)] + ["x_" + k for k in ("utc", "ev", "reason")
                                                                                  if x.get(k) != g[1].get(k)]
        prices = [("px", f.get("px"), g[0].get("px")), ("st0", f.get("st0"), g[0].get("st0")), ("x_px", x.get("px"), g[1].get("px"))]
        off = [k for k, a, b in prices if a != b]
        far = [k for k, a, b in prices if a != b and not (a is not None and b is not None and abs(a - b) <= REL * abs(a))]
        if exact or far:
            diff.append({"oid": int(o), "fields": exact + far, "process": g[2], "continuous": [f, x], "restarted": g[:2]})
        elif off:
            near.append({"oid": int(o), "fields": off, "max_rel": max(abs(a - b) / abs(a) for k, a, b in prices if a != b),
                         "process": g[2]})
        else:
            same += 1
    extra = sorted(int(o) for o in got if o not in want)
    return {"checked": len(want), "identical": same, "within_1e-12": len(near), "within_1e-12_first": near[:5],
            "max_rel_within": max([q["max_rel"] for q in near], default=0.0), "different": diff[:10], "n_different": len(diff),
            "missing": missing[:10], "n_missing": len(missing), "extra": extra[:10], "n_extra": len(extra),
            "pass": len(diff) == 0 and len(missing) == 0 and len(extra) == 0}


def windows(segs, procs):
    """[a, b) UTC spans where the restarted EA was down or starting: outages, and each restart's start-up (to two
    minutes after its first live barrier)"""
    w = []
    for k, s in enumerate(segs):
        if s["outage_s"]:
            w.append((s["stop"], s["next_start"], "outage"))
        w.append((s["next_start"], startup_end(procs[k + 1], s), "start-up"))
    return w


def startup_end(p, s):
    """the end of a start's start-up: two minutes after its first live barrier, or after the last reconcile of the
    process (a sleeve whose symbol is NOT_READY is reconciled once it is READY), whichever is later"""
    to = int(p["rebuild_to"] or s["next_start"]) + 60
    # reconciles within an hour of the first live barrier (a restart inside a weekend or holiday goes live, and reconciles,
    # only when the market reopens, which can be days after the restart)
    rec = [int(r["utc"]) for r in p["fol"] if r["ev"] == "ADOPT" and r.get("why") == "reconcile" and r["utc"] < to + 3600]
    return max([to] + rec) + 120


def in_window(t, wins):
    if t is None:
        return None
    for a, b, kind in wins:
        if a <= t < b:
            return kind
    return None


def first_window_difference(pc, pr, wins):
    """the entry time of the first real trade (any sleeve) that differs because of an outage or a start-up: from then
    on the account's balance path may differ, so lots may differ by a step"""
    ka = {(r["code"], r["side"], r["u_in"]): r for r in pc}
    kb = {(r["code"], r["side"], r["u_in"]): r for r in pr}
    first = None
    for key in sorted(set(ka) | set(kb), key=lambda q: q[2]):
        x, y = ka.get(key), kb.get(key)
        if x is not None and y is not None and x["px_in"] == y["px_in"] and x.get("u_out") == y.get("u_out") and \
                x.get("px_out") == y.get("px_out") and x["vol"] == y["vol"]:
            continue
        t = key[2]
        if any(in_window(t - d, wins) for d in (0, 60, 120, 180, 240, 300)) or \
                (x is not None and in_window(x.get("u_out"), wins)) or (y is not None and in_window(y.get("u_out"), wins)):
            first = t
            break
    return first


def skips_of(fol_lists):
    """{(code, oid): reason} of the live sizing skips (SIZE skip, MISSED with a sizing reason)"""
    out = {}
    for fol in fol_lists:
        for r in fol:
            if r.get("rp") == 1:
                continue
            if r["ev"] == "SIZE" and r.get("skip") not in (None, "none"):
                out[(r["code"], int(r["oid"]))] = str(r["skip"])
            elif r["ev"] == "MISSED" and str(r.get("reason")) in ("cap", "min_lot", "margin"):
                out[(r["code"], int(r["oid"]))] = str(r["reason"])
    return out


def cmp_positions(pc, pr, wins, cont=None, procs=None):
    """the real trades of the restarted run against the continuous run's, per sleeve, keyed by side and entry time"""
    out = {}
    t_first = first_window_difference(pc, pr, wins)
    sk_c = skips_of([cont["fol"]]) if cont else {}
    sk_r = skips_of([p["fol"] for p in procs]) if procs else {}
    for c in CODES:
        fills = sorted((f["utc"], int(o)) for o, (f, _) in (cont["trades"].get(c, {}).items() if cont else []))
        fill_t = [a for a, _ in fills]

        def oid_at(u_in):
            import bisect
            j = bisect.bisect_right(fill_t, u_in) - 1
            return fills[j][1] if j >= 0 and u_in - fill_t[j] <= 300 else None
        ka = {(r["side"], r["u_in"]): r for r in pc if r["code"] == c}
        kb = {(r["side"], r["u_in"]): r for r in pr if r["code"] == c}
        same, cls, unexplained = 0, {}, []
        for key in sorted(set(ka) | set(kb), key=lambda q: q[1]):
            x, y = ka.get(key), kb.get(key)
            if x is not None and y is not None:
                eq = x["px_in"] == y["px_in"] and x.get("u_out") == y.get("u_out") and x.get("px_out") == y.get("px_out")
                if eq and x["vol"] == y["vol"]:
                    same += 1
                    continue
                if eq:
                    why = ("lots only: the balance path changed after an earlier restart difference"
                           if t_first is not None and key[1] > t_first else None)
                else:
                    w = in_window(y.get("u_out"), wins) or in_window(x.get("u_out"), wins)
                    why = f"exit in a {w} window" if w else None
            else:
                w = None
                for d in (0, 60, 120, 180, 240, 300):                    # the intent's 5-minute window touches one
                    w = w or in_window(key[1] - d, wins)
                why = f"entry in a {w} window" if w else None
                if why is None and t_first is not None and key[1] > t_first:
                    o = oid_at(key[1])
                    other = sk_c if x is None else sk_r                  # the run that has no position skipped it?
                    if o is not None and (c, o) in other:
                        why = (f"sizing skip ({other[(c, o)]}) in the {'continuous' if x is None else 'restarted'} run: the open "
                               "positions or the balance differed after an earlier restart difference")
            if why is None:
                unexplained.append({"side": key[0], "u_in": key[1], "continuous": x, "restarted": y})
            else:
                cls[why] = cls.get(why, 0) + 1
        out[c] = {"continuous": len(ka), "restarted": len(kb), "identical": same, "classified": cls,
                  "unexplained": unexplained[:5], "n_unexplained": len(unexplained), "max_open_at_once": overlap(kb.values())}
    return out


def ea_closes(procs, segs, cont, pos):
    """check 4 (review F1, F5): the closes the EA itself decides (CLOSE why=latest_exit or why=orphan, live lines) inside a
    start-up window, each matched to its position (ticket) and to the continuous run's paper trade that position follows
    (same sleeve and side, paper fill bar within 5 min of the real entry); one whose paper trade is still open at the close
    is an EA decision against the paper: a failure"""
    by_ticket = {int(r["position"]): r for r in pos}
    out = {"in_start_up": 0, "by_why": {}, "paper_trade_ended": 0, "no_paper_trade": 0, "against_open_paper": [],
           "n_against_open_paper": 0, "by_sleeve": {}}
    for k, s in enumerate(segs):
        p = procs[k + 1]
        a, b = s["next_start"], startup_end(p, s)
        for r in p["fol"]:
            if r["ev"] != "CLOSE" or r.get("rp") == 1 or str(r.get("why")) not in ("latest_exit", "orphan"):
                continue
            t = int(r["utc"])
            if not (a <= t < b):
                continue
            out["in_start_up"] += 1
            w = str(r.get("why"))
            out["by_why"][w] = out["by_why"].get(w, 0) + 1
            q = by_ticket.get(int(r["ticket"])) if r.get("ticket") is not None else None
            if q is None:
                out["no_paper_trade"] += 1
                continue
            c, side, u_in = q["code"], int(q["side"]), int(q["u_in"])
            hit = None
            for o, (f, x) in cont["trades"].get(c, {}).items():
                if int(f["side"]) == side and abs(int(f["bar"]) - u_in) <= 300:
                    hit = (o, f, x)
                    break
            if hit is None:
                out["no_paper_trade"] += 1
                continue
            o, f, x = hit
            if int(f["bar"]) <= t < int(x["utc"]):
                out["n_against_open_paper"] += 1
                out["by_sleeve"][c] = out["by_sleeve"].get(c, 0) + 1
                if len(out["against_open_paper"]) < 10:
                    out["against_open_paper"].append({"process": k + 1, "code": c, "why": w, "close_utc": t, "ticket": int(r["ticket"]),
                                                      "oid": int(o), "paper_exit_utc": int(x["utc"]),
                                                      "paper_left_h": round((int(x["utc"]) - t) / 3600, 2)})
            else:
                out["paper_trade_ended"] += 1
    return out


def start_up_split(pos_res):
    """the start-up and outage classes of check 3, apart: entries delayed by a start, exits in a start, outages"""
    out = {}
    for c, v in pos_res.items():
        cl = v["classified"]
        out[c] = {"entries_delayed_by_a_start": cl.get("entry in a start-up window", 0), "exits_in_a_start": cl.get("exit in a start-up window", 0),
                  "entries_in_an_outage": cl.get("entry in a outage window", 0), "exits_in_an_outage": cl.get("exit in a outage window", 0)}
    return out


def overlap(recs):
    ev = []
    for r in recs:
        ev.append((r["u_in"], 1))
        ev.append((r["u_out"] if r.get("u_out") is not None else 1 << 62, -1))
    n = m = 0
    for _, d in sorted(ev):
        n += d
        m = max(m, n)
    return m


def ended_before_restart(r, t, cont, pos):
    """an ORPHAN line r of a process that started at t: the restarted run's position (by ticket), opened before t, follows a
    continuous-run paper trade (same sleeve and side, paper fill bar within 5 min of the real entry) that had already
    ended before t. Its close was still waiting at the restart (the market was shut, e.g. a crypto holiday and weekend), so
    the new process finds no paper trade for it and ORPHAN is its right decision. Returns the details, or None."""
    q = pos.get(int(r["ticket"])) if r.get("ticket") is not None else None
    if q is None or q["code"] != r.get("code") or int(q["u_in"]) >= t:
        return None
    c, side, u_in = q["code"], int(q["side"]), int(q["u_in"])
    for o, (f, x) in cont["trades"].get(c, {}).items():
        if int(f["side"]) == side and abs(int(f["bar"]) - u_in) <= 300:
            if int(x["utc"]) >= t:
                return None
            cc = [int(z["u_out"]) for z in cont["pos"] if z["code"] == c and int(z["side"]) == side and int(z["u_in"]) == u_in
                  and z.get("u_out") is not None]
            return {"code": c, "oid": int(o), "paper_exit_utc": int(x["utc"]), "restart_utc": int(t), "orphan_utc": int(r["utc"]),
                    "continuous_close_utc": cc[0] if cc else None}
    return None


def follower(procs, segs, cont, pos=()):
    ev = {"ADOPT": 0, "ORPHAN": 0, "DUP": 0, "SLFIX": 0, "REFUSED": 0, "MISSED": {}}
    after_outage = {k + 1 for k, s in enumerate(segs) if s["outage_s"]}
    by_ticket = {int(q["position"]): q for q in pos}
    orphan_other = []
    before = []
    n_after = n_start = 0
    for p in procs:
        for r in p["fol"]:
            if r.get("rp") == 1 or r["ev"] == "SIZE":
                continue
            e = r["ev"]
            if e == "MISSED":
                ev["MISSED"][str(r.get("reason"))] = ev["MISSED"].get(str(r.get("reason")), 0) + 1
            elif e in ev:
                ev[e] += 1
            if e != "ORPHAN":
                continue
            if p["k"] in after_outage:
                n_after += 1
                continue
            s = segs[p["k"] - 1]
            end = startup_end(p, s)
            c = r.get("code")
            if any(s["stop"] - 120 <= x["utc"] <= end for _, x in cont["trades"].get(c, {}).values()):
                n_start += 1                          # its paper trade ended while the EA was starting
                continue
            eb = ended_before_restart(r, s["stop"], cont, by_ticket)
            if eb is not None:
                eb["process"] = p["k"]
                before.append(eb)                     # its paper trade ended before the restart, its close still waiting
            else:
                orphan_other.append({"process": p["k"], "code": c, "why": r.get("why")})
    ev["orphan_after_outage"] = n_after
    ev["orphan_paper_ended_during_start_up"] = n_start
    ev["orphan_paper_ended_before_restart"] = len(before)
    ev["orphan_paper_ended_before_restart_first"] = before[:10]
    ev["orphan_other"] = orphan_other[:10]
    return ev


def adopted(pr, procs, segs):
    """every robot position open across a restart has, in the next process, an ADOPT line or a CLOSE / ORPHAN line"""
    n, miss, by_stop = 0, [], 0
    for k, s in enumerate(segs):
        nxt = procs[k + 1]
        tk = {int(r["ticket"]) for r in nxt["fol"] if r["ev"] in ("ADOPT", "CLOSE", "ORPHAN") and r.get("ticket") is not None}
        end = startup_end(nxt, s)
        for r in pr:
            u_out = r.get("u_out")
            if r["u_in"] < s["stop"] and (u_out is None or u_out >= s["next_start"]):
                n += 1
                if int(r["position"]) in tk:
                    continue
                if u_out is not None and u_out < end and r.get("reason_out") in (4, 6):
                    by_stop += 1                      # its broker stop closed it while its sleeve waited to be reconciled
                    continue
                miss.append({"process": k + 1, "code": r["code"], "position": int(r["position"]), "u_in": r["u_in"], "u_out": u_out,
                             "reason_out": r.get("reason_out")})
    return {"open_across_restarts": n, "closed_by_their_stop_before_reconcile": by_stop, "n_not_adopted": len(miss),
            "not_adopted": miss[:10]}


def cover(cont, segs):
    out = {}
    stops = [s["stop"] for s in segs]
    for c in CODES:
        tr = [(f["utc"], x["utc"]) for f, x in cont["trades"][c].values()]
        d = np.array(cont["dec"][c], np.int64)
        out[c] = {"restarts": len(segs), "inside_its_open_trades": int(sum(1 for t in stops if any(a < t < b for a, b in tr))),
                  "within_10_min_before_its_decisions": int(sum(1 for t in stops if len(d) and ((d > t) & (d <= t + 600)).any())),
                  "outages_over_its_trades": int(sum(1 for s in segs if s["outage_s"] and any(a < s["next_start"] and b > s["stop"] for a, b in tr)))}
    return out


def analyse(D):
    cont, procs, segs = D["continuous"], D["procs"], D["segs"]
    paper = {c: cmp_paper(cont, procs, segs, c) for c in CODES}
    wins = windows(segs, procs)
    pos = cmp_positions(cont["pos"], D["pos"], wins, cont, procs)
    fol = follower(procs, segs, cont, D["pos"])
    ad = adopted(D["pos"], procs, segs)
    eac = ea_closes(procs, segs, cont, D["pos"])
    proc_ok = all(p["rebuilds"] == 1 and p["selftest_ok"] and not p["errors"] for p in procs)
    mins = [p["rebuild_minutes"] for p in procs[1:] if p["rebuild_minutes"] is not None]
    depth_ok = len(mins) == len(procs) - 1 and all(m <= 121 * 1440 for m in mins)
    res = {"switches": D["switches"], "continuous_wall_s": cont["wall_s"], "restarted_wall_s": D["wall_s"], "processes": len(procs),
           "restarts": len(segs), "outages": [{"stop": s["stop"], "hours": round(s["outage_s"] / 3600, 2)} for s in segs if s["outage_s"]],
           "points_per_sleeve": D["points_per_sleeve"], "cover": cover(cont, segs), "processes_ok": proc_ok,
           "rebuilds_from_depth_only": depth_ok, "rebuild_minutes": [int(min(mins)), int(max(mins))] if mins else None,
           "process_errors": [p["errors"] for p in procs if p["errors"]][:5], "paper": paper, "positions": pos, "follower": fol,
           "adopt": ad, "ea_closes_in_start_up": eac, "start_up_split": start_up_split(pos)}
    res["pass"] = bool(proc_ok and depth_ok and all(v["pass"] for v in paper.values())
                       and all(v["n_unexplained"] == 0 and v["max_open_at_once"] <= 1 for v in pos.values())
                       and fol["DUP"] == 0 and not fol["orphan_other"] and ad["n_not_adopted"] == 0
                       and eac["n_against_open_paper"] == 0)
    return res


def one_setting(exe, sw, k1t, per, n_out, frm, to):
    env = inputs(sw, k1t)
    log(f"{sw}: continuous run ...")
    cont = continuous(exe, sw, env, frm, to)
    pp, segs = points(cont, per, n_out, 20261113 + (sw == "on"))
    log(f"{sw}: {len(segs)} restarts ({sum(1 for s in segs if s['outage_s'])} outages), {len(segs) + 1} processes "
        f"(continuous run {cont['wall_s']} s) ...")
    procs, pos, wall = restarted(exe, sw, env, segs, frm, to)
    D = {"switches": sw, "continuous": cont, "segs": segs, "procs": procs, "pos": pos, "wall_s": wall, "points_per_sleeve": pp}
    with gzip.open(os.path.join(OUT, f"{sw}_data.json.gz"), "wt") as f:
        json.dump(D, f, default=str)
    return analyse(D)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-sleeve", type=int, default=100)
    ap.add_argument("--outages", type=int, default=10)
    ap.add_argument("--only", choices=["off", "on"])
    ap.add_argument("--from", dest="frm", help="UTC date: a shorter period (a check of the test itself)")
    ap.add_argument("--to")
    ap.add_argument("--analyse", action="store_true", help="check the saved data again, no replay")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args(argv)
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    sws = [a.only] if a.only else ["off", "on"]
    k1t = None
    p = os.path.join(HERE, "out", "test_E", "test_changes.json")
    if os.path.exists(p):
        k1t = json.load(open(p)).get("k1_folds", {}).get("inpk1t_rebuilt")
    k1t = k1t or "2019:505.84441393264945;2020:496.6915507295559;2021:465.14468666253265"
    frm = W.utc_to_srv(calendar.timegm(time.strptime(a.frm, "%Y-%m-%d"))) if a.frm else None
    to = W.utc_to_srv(calendar.timegm(time.strptime(a.to, "%Y-%m-%d"))) if a.to else None
    warn = 0
    if a.analyse:
        res = {}
        for sw in sws:
            with gzip.open(os.path.join(OUT, f"{sw}_data.json.gz"), "rt") as f:
                res[sw] = analyse(json.load(f))
    else:
        exe, w = build(DIST, name="test_restarts")
        warn = len(w)
        with ThreadPoolExecutor(max_workers=len(sws)) as ex:
            res = dict(zip(sws, ex.map(lambda s: one_setting(exe, s, k1t, a.per_sleeve, a.outages, frm, to), sws)))
    summary = {"dist_cr_build": open(DIST).readline().strip(), "warnings": warn, "per_sleeve": a.per_sleeve, "k1t": k1t,
               "period": [a.frm, a.to], "settings": res, "sec": round(time.time() - t0, 1)}
    summary["pass"] = bool(warn == 0 and all(r["pass"] for r in res.values()))
    with open(os.path.join(OUT, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1, default=str)
    for sw, r in res.items():
        log(f"== switches {sw}: {r['restarts']} restarts ({len(r['outages'])} outages), {r['processes']} processes "
            f"({r['restarted_wall_s']} s); processes ok {r['processes_ok']}, rebuilds from the depth only {r['rebuilds_from_depth_only']} "
            f"(minutes {r['rebuild_minutes']})")
        for c in CODES:
            pp, po, cv = r["paper"][c], r["positions"][c], r["cover"][c]
            log(f"  {c}: paper {pp['identical']}/{pp['checked']} bit-identical, {pp['within_1e-12']} within 1e-12 (different {pp['n_different']}, missing {pp['n_missing']}, "
                f"extra {pp['n_extra']}) | restarts in its trades {cv['inside_its_open_trades']}, before its decisions "
                f"{cv['within_10_min_before_its_decisions']}, outages over its trades {cv['outages_over_its_trades']} | real "
                f"{po['identical']}/{po['continuous']} identical, classified {po['classified']}, unexplained {po['n_unexplained']}, "
                f"max open {po['max_open_at_once']}")
        log(f"  follower: {r['follower']} | {r['adopt']['open_across_restarts']} positions open across restarts, closed by their stop "
            f"before reconcile {r['adopt']['closed_by_their_stop_before_reconcile']}, not adopted {r['adopt']['n_not_adopted']}")
        e = r["ea_closes_in_start_up"]
        log(f"  EA-initiated closes in start-up windows (latest_exit, orphan): {e['in_start_up']} {e['by_why']}, paper trade ended "
            f"{e['paper_trade_ended']}, no paper trade {e['no_paper_trade']}, AGAINST AN OPEN PAPER TRADE {e['n_against_open_paper']} "
            f"{e['by_sleeve']} {e['against_open_paper'][:3]}")
    log(f"test_restarts: {'PASS' if summary['pass'] else 'FAIL'} ({summary['sec']} s)")
    if not a.keep and not a.analyse:
        for sw in sws:
            for suffix in ("_continuous", "_restarts"):
                shutil.rmtree(os.path.join(OUT, sw + suffix), ignore_errors=True)
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
