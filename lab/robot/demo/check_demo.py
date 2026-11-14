"""Check two weeks of the robot on the FP demo account from the files the user sends back from the Mac.

    python3 -I lab/robot/demo/check_demo.py --journals DIR [--bars DIR] [--printed FILE ...] [--out DIR]
                                            [--fiches FILE] [--spread auto|open|close|mean|max|min2]
                                            [--input InpName=value ...] [--no-replay] [--rebuild]

--journals  the robot's daily files MQL5/Files/ClaudeRobot/<yyyymmdd>.log (CR_Journal.mqh JrnAt: one line
            CR|<utc>|<EVENT>|<code>|k=v|... per event, utc = the event's lab time, doubles DoubleToString(x, -16);
            lines of a rebuild's replay end with |rp=1 and are written to the file only). The line format and the
            number parser are check/compare.py's (read-only); a line that does not parse is counted, not fatal.
            A .log file that is not a robot journal (MetaTrader's own logs have the same <yyyymmdd>.log names: UTF-16,
            or no line starting with 'CR|') is skipped and named. The text of a line that is not a robot line is never
            kept or written (it may hold the login, the server, the holder's name or the user folder): only its file
            and line number; it is scanned so that any account value it holds is masked everywhere.
            Missing daily files: the robot writes a DAY line for every server day it runs (weekends included, written
            at the first minute of the next day, CR_Main.mqh MainDaily); a gap in the DAY days with no start, stop or
            rebuild (INIT, REBUILD) between the two lines means lines are missing: the absent files are named, and
            their hours are left out of the replay comparison.
--printed   the Experts tab's lines (copied text, or MetaTrader's own MQL5/Logs/<yyyymmdd>.log, UTF-16 accepted):
            the same CR| lines after a terminal prefix, live lines only (rp=1 is never printed, SPEC 2.6). Other lines
            are never kept; they are only scanned for an account login or server name, which is then masked.
--bars      ReleveFP's m1_<BASE>.csv files (ReleveFP.mq5 Minutes/Row: time,bo,bh,bl,bc,ao,ah,al,ac,n,sp_mean,sp_max;
            time = server seconds; bid and ask O/H/L/C of the ticks of the minute; sp_mean, sp_max in price units),
            optionally with fiches.csv beside them (digits, contract sizes, minimum lots for the mock).

What it does:
 (a) the journal: builds and inputs of every INIT line (CR_BUILD must be fd6aaf01e332 or a later build of the git
     history of dist/; an older, unknown, debug or harness build is flagged), SELFTEST, PLAN, REBUILD, READY and
     NOTREADY with their durations after each start, restarts and their reasons, every ERROR, DUP, SLFIX, REFUSED,
     MISSED (with its reason), COST, LATEBAR, GUARD, STOP, MARK, WATCH line (and ORPHAN, CLOCK, GAP, SETTLE, TAKEOVER,
     LOCK, ADOPT), and per sleeve the counts of DEC, PFILL, PEXIT, SIZE, SEND, FILL, CLOSE (live and replayed).
 (b) fills: each real position (FILL, or ADOPT after a restart) against its paper trade (PFILL, PEXIT/PREVISE of the
     same oid): entry and exit price differences in points, bp and EUR at the real lots (EUR per point from the FILL
     line's own risk: risk = (side x (fill - sl) + 2h) / tick size x tick value x lots, CR_Broker.mqh BrkRiskMoney);
     the exits: an EA close (a CLOSE line with ok=1, rc 10009 or 10010 and a price), or a broker stop, which the
     journal does not write (no line: its price is estimated at the broker stop, FILL sl or the last SLMOD). A CLOSE
     with ok=1 but rc 0 and px 0 is the race where the broker's stop closed the position just before the robot's
     request (CR_Broker.mqh BrkClose: CTrade clears its result): a broker stop too. A position whose paper trade
     ended otherwise (time, target, rule, eod ...: not stop, trail or gap) and has no successful CLOSE was either not
     closed by the robot or stopped by the broker before the paper's exit: with --bars, the releve's minutes say
     whether the real quotes crossed its broker stop in between (bid low for a long, ask high for a short); else, or
     when they did not, it is an anomaly. Its exit is then unknown and it is left out of the money totals; so is a
     CLOSE refused (ok=0) never followed by a success. An oid with two real tickets (FILL or ADOPT) is an anomaly;
     so is a position with no exit line whose paper exit time has passed while the journal goes on (lines missing).
     Points are given per sleeve and per market only (their sizes differ); totals are in bp and EUR. On gold the
     paper's prices hold the commission (h = 3
     points a side, SPEC 2.2), so the differences are also given commission included (the measured COST rate, else
     the model); the broker's own slippage against the quote the request went with (SEND bid / ask); per sleeve and
     in total, and the share of intents
     (live SIZE lines) that became real trades. The journal holds no deal line (CR_Ledger.mqh reads DEAL_COMMISSION
     and DEAL_SWAP but writes neither): per-trade commission and swap are UNKNOWN; the gold commission of each server
     day comes from the COST lines (comm_usd_oz, against the robot's 0.06 USD per oz); the DAY lines' balances give an
     estimate of costs not in the prices (commission + swap + stop slippage) against the gross result.
 (c) replay (with --bars): ReleveFP's minutes become the harness's bar files (check/mock_replay.h rp_load_bars and
     check/export_frames.py: b"CRB1", int32 digits, int64 n, n x <int64 server time, int32 bid O/H/L/C in points,
     int32 spread in points>; the robot's paper ask = bid + spread x point + h on all four prices, CR_Bars.mqh
     BarsMakeAt, so the spread is the bar's MqlRates.spread). Which ReleveFP column gives MqlRates.spread is an open
     Mac item (SPEC 10.3: the moderator says the bar's minimum): --spread auto measures it on the live journal (every
     paper line carries its bar's s_raw) and on the COST lines, and picks the convention that matches. All bars are
     passed (the robot masks them itself). dist/ClaudeRobot.mq5 is built with the harness (check/build.py, name
     demo_check_release, CR_XAU_COMM_PTS from the INIT line, 6 in the release; the dist file is read, never
     regenerated) and replays the span as an observer (InpTrade false, SPEC 10.2 and 10.12) with the inputs of the
     INIT line (risk table, sleeves, the three switches as resolved, the K1 table), the plan start and B(T) of the
     PLAN line (InpPlanStart, MOCK_BALANCE), and --input for what INIT does not show (InpExtraClosures ...). Then the
     live lines of SPEC 10.12 step 3 (DEC, PFILL, PEXIT, PSTOP, PREVISE, PVOID, PREFUSE, HOLD, SIZE, MISSED) are
     compared line for line, matched by key (event, sleeve, oid, bar or time), every field equal (doubles built on
     rolling or Wilder values within 1e-12 relative, SPEC 7). Every difference is listed with its first line on each
     side. Choice for SIZE (it depends on the real account): the replay is NOT given the account's deal history,
     because the journal does not hold it (no deal line, no broker stop fill, no commission or swap), so MOCK_DEALS
     could only be guessed; SIZE is compared on what does not depend on the account or on the tick of the request:
     stamp, sleeve, oid, side, entry type, late flag and stake factor; when the live copy is an observer (no FILL),
     the balance never moved for the robot, so B, P_in, rate, m, w and the week unit are compared too (the replay
     starts from the PLAN line's B(T)); the skip reason is compared when both copies observe and the replay's symbol
     was READY. lots, want, r, budget and quote are never compared (account and tick). MISSED is compared for
     reason=exited (P5, account-independent); the other reasons come from the real account and are listed apart.
     Lines are compared only where both sides can hold them: inside each sleeve's own span (from the latest first
     minute to the earliest last minute among the markets it reads, READS_OF_CODE: a market whose minutes start late
     delays only its sleeves, and the short file is named) after the sleeve's warm-up (WARMUP_DAYS below: the
     look-backs of the rule files, and about 400 bars for a Wilder ATR to meet 1e-12) and after the first moment both
     paper chains are flat together (a trade held over the replay's start would block the next one on one side only),
     every line of one paper trade in or out together (by its oid's decision time), while the live copy was running
     live (from a REBUILD to its INIT deinit) with the same paper inputs, outside the hours of a missing daily file.
     Each sleeve's coverage ("compare du ... au ..." or "jamais") is printed. With ReleveFP's default InpDays=30 and
     a two-week demo at the end of it: BKB, BKE (5-day warm-up) and ORX (3 days) are compared over most of the demo,
     N30 and NQB (25 days) over its last days only, OC4 (35), F1B, F1E, GFP (30) and D4H (120) never; InpDays=150
     compares every sleeve over the whole demo, and the tool asks for it when a sleeve is left out. The AGG and COST
     lines of both sides are set side by side (bars fed per server day and symbol; median spreads), which shows
     whether ReleveFP's minutes are the broker's bars; a day that differs is an anomaly.
 (d) --printed: the printed lines against the files' live lines: the same copy (the Mac's) must print every live line
     of its files; another copy (the VPS's, INIT vps=1) is compared on SPEC 10.12's lines as above (shadow weeks).
     A --printed file with no robot line at all (the terminal's Journal tab, say) is named as an anomaly.
 MISSED: the reasons that come from the account (refused, prev_open, market_shut ...) are anomalies; 'exited' and
     'notrade' never are; 'late', 'notready' and 'exited' within 15 min of a start (a paper trade already open, SPEC
     4.8 d) are not; 'observe' is not when its stamp is before the PLAN line's start T (InpPlanStart set to the
     go-live time, SPEC 1 step 3) or the plan is not in force yet. A PLAN state 'unset' (no entry on a real account)
     is an anomaly.
Output in --out (default: the session scratchpad; a folder inside the repository is refused): report.json,
report_fr.txt, the converted bars and the replay's journal under replay/; a French summary on stdout that says
"rien d'anormal" only when nothing is.
"""
import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import time
from collections import Counter, defaultdict

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import demo_common as C  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

COMPARE_EV = ["DEC", "PFILL", "PEXIT", "PSTOP", "PREVISE", "PVOID", "PREFUSE", "HOLD", "SIZE", "MISSED"]
PAPER_EV = ["PFILL", "PEXIT", "PSTOP", "PREVISE", "PVOID", "PREFUSE", "HOLD"]
LISTED = ["ERROR", "DUP", "SLFIX", "REFUSED", "MISSED", "COST", "LATEBAR", "GUARD", "STOP", "MARK", "WATCH", "ORPHAN", "CLOCK",
          "GAP", "SETTLE", "TAKEOVER", "LOCK", "ADOPT"]
COUNT_EV = ["DEC", "PFILL", "PEXIT", "PSTOP", "PREVISE", "PVOID", "PREFUSE", "HOLD", "SIZE", "SEND", "FILL", "CLOSE", "MISSED",
            "REFUSED", "SLMOD", "ADOPT", "DUP", "ORPHAN", "SLFIX", "WATCH"]
# days of bars the replay needs before a sleeve's lines can equal the live robot's (SPEC 3 look-backs; a Wilder ATR
# with alpha 1/14 needs about 400 bars to forget its seed to 1e-13: gold hour bars ~18 trading days, 4h bars ~68)
# (CR_Rule_*.mqh constants: N30 14 rows, OC4 20 rows and a 14-day ATR, BKB/BKE 72 + 24 hour bars, F1 280 session bars of
# 14 a day, NQB 28,800 minutes, GFP Wilder on hour bars, D4H 60 4h bars and Wilder on them, ORX the day's London range)
WARMUP_DAYS = {"N30": 25, "OC4": 35, "BKB": 5, "BKE": 5, "F1B": 30, "F1E": 30, "NQB": 25, "GFP": 30, "D4H": 120, "ORX": 3}
REL_TOL = 1e-12
NEAR_S = 1800                                   # a live disturbance within 30 min of a line explains it
SIZE_ACCOUNT = ["B", "P_in", "rate", "m", "unit", "w"]
SIZE_FREE = ["side", "et", "late", "f"]
SIZE_NEVER = ["lots", "want", "r", "budget", "quote"]
DEINIT_FR = {0: "arret par le programme", 1: "robot retire du graphique", 2: "recompile", 3: "symbole ou periode du graphique change",
             4: "graphique ferme", 5: "parametres changes", 6: "autre compte", 7: "modele applique", 8: "OnInit en echec",
             9: "terminal ferme"}
REC = np.dtype([("t", "<i8"), ("o", "<i4"), ("h", "<i4"), ("l", "<i4"), ("c", "<i4"), ("s", "<i4")])
SPREAD_CONV = ["open", "close", "mean", "max", "min2"]
REPLAY_NAME = "demo_check_release"


# ---------------------------------------------------------------------------------------------- (a) the journal
def starts_of(rows):
    """the starts (INIT with build=), each with its stop (INIT deinit=), its REBUILD lines and its live span"""
    out, cur = [], None
    last_live = None
    for r in rows:
        if r["ev"] == "INIT" and "build" in r:
            if cur is not None:
                cur["end"] = cur.get("deinit_utc") or cur.get("last_live") or r["utc"]
                out.append(cur)
            cur = {"utc": r["utc"], "init": r, "rebuilds": [], "selftest": None, "plan": None, "last_live": None,
                   "ready": {}, "notready": defaultdict(list)}
            r["_si"] = len(out)
            continue
        if cur is None:
            cur = {"utc": r["utc"], "init": None, "rebuilds": [], "selftest": None, "plan": None, "last_live": None,
                   "ready": {}, "notready": defaultdict(list), "no_init": True}
        r["_si"] = len(out)
        ev = r["ev"]
        if ev == "INIT" and "deinit" in r:
            cur["deinit"] = r
            cur["deinit_utc"] = r["utc"]
        elif ev == "SELFTEST" and cur["selftest"] is None:
            cur["selftest"] = r
        elif ev == "PLAN" and "state" in r and cur["plan"] is None:
            cur["plan"] = r
        elif ev == "REBUILD":
            cur["rebuilds"].append(r)
        elif ev == "READY" and r["code"] not in cur["ready"]:
            cur["ready"][r["code"]] = r
        elif ev == "NOTREADY":
            cur["notready"][r["code"]].append(r)
        if r.get("rp") != 1:
            cur["last_live"] = max(cur["last_live"] or r["utc"], r["utc"]) if ev not in ("INIT",) else cur["last_live"]
            last_live = r["utc"]
    if cur is not None:
        cur["end"] = cur.get("deinit_utc") or cur.get("last_live") or last_live
        out.append(cur)
    for k, s in enumerate(out):
        s["live_from"] = int(s["rebuilds"][0]["to"]) if s["rebuilds"] else None
        if s["init"] is None and s["live_from"] is None:          # files cut after the start: live from their first line
            first = [r["utc"] for r in rows if r.get("_si") == k and r.get("rp") != 1]
            s["live_from"] = min(first) - 1 if first else None
    return out


def paper_inputs(init):
    """the inputs that change the paper chain (switches, K1 table, gold commission) and the sizing (risk, sleeves)"""
    if not init:
        return None
    return {"K1": init.get("K1"), "H2": init.get("H2"), "S0.75r": init.get("S0.75r"), "k1t": init.get("k1t", ""),
            "comm_pts": init.get("comm_pts")}


def day_gaps(rows, files):
    """the server days with no DAY line between two DAY lines (CR_Main.mqh MainDaily writes one per server day the
    robot runs, weekends included, at the first minute of a later day; a rebuild's replay writes none). A gap with an
    INIT or REBUILD line between the two DAY lines is explained (the robot was stopped, or replayed the history after a
    long disconnection); any other gap means lost lines: DAY(x) goes to the file of day x + 1, so the files of days
    first_missing + 1 ... last_missing + 1 that are absent are named. Returns (gaps, ranges): ranges = UTC intervals
    whose lines are missing (left out of the replay comparison)."""
    lv = C.live(rows)
    marks = sorted(r["utc"] for r in lv if r["ev"] in ("INIT", "REBUILD"))
    present = {C.day_of_file(f) for f in (files or [])} - {None}
    seen, prev, gaps, ranges = set(), None, [], []
    for r in lv:
        if r["ev"] != "DAY" or not isinstance(r.get("day"), int):
            continue
        d, u = int(r["day"]), int(r["utc"])
        if d in seen:
            continue
        seen.add(d)
        if prev is not None and d - prev[0] > 86400:
            explained = any(prev[1] < m <= u for m in marks)
            cand = list(range(prev[0] + 2 * 86400, d + 1, 86400))
            missing = [x for x in cand if x not in present]
            g = {"first_day": C.ymd(prev[0] + 86400), "last_day": C.ymd(d - 86400), "days": (d - prev[0]) // 86400 - 1,
                 "explained": explained, "missing_files": [C.file_of_day(x) for x in missing]}
            gaps.append(g)
            if not explained:
                if missing:
                    for x in missing:
                        ranges.append((C.srv_to_utc(x) - 600, C.srv_to_utc(x + 86400) + 600))
                else:
                    ranges.append((prev[1], u))
        if prev is None or d > prev[0]:
            prev = (d, u)
    return gaps, ranges


def analyse_journal(rows, builds, files=None):
    lv = C.live(rows)
    starts = starts_of(rows)
    res = {"lines": len(rows), "live_lines": len(lv), "replayed_lines": len(rows) - len(lv)}
    if rows:
        res["first_utc"], res["last_utc"] = min(r["utc"] for r in lv) if lv else None, max(r["utc"] for r in lv) if lv else None
    st_out, anomalies = [], []
    for k, s in enumerate(starts):
        i = s["init"] or {}
        bs = C.build_status(i.get("build"), builds) if i else "UNKNOWN"
        e = {"n": k + 1, "utc": s["utc"], "when": C.utc_txt(s["utc"]), "build": i.get("build"), "build_status": bs,
             "version": i.get("version"), "demo": i.get("demo"), "vps": i.get("vps"), "tester": i.get("tester"),
             "observer": i.get("observer"), "entries_off": i.get("entries_off"), "harness": i.get("harness"),
             "comm_pts": i.get("comm_pts"), "risk": i.get("risk"), "sleeves": i.get("sleeves"),
             "switches": {x: i.get(x) for x in ("K1", "H2", "S0.75r")}, "k1t": i.get("k1t"),
             "symbols": {b: i.get(b) for b in C.ROBOT_BASES}, "end": s.get("end"), "live_from": s.get("live_from"),
             "deinit": s.get("deinit", {}).get("deinit"), "deinit_fr": DEINIT_FR.get(s.get("deinit", {}).get("deinit"), None),
             "rebuilds": [{"utc": r["utc"], "why": r.get("why"), "minutes": r.get("minutes"), "ms": r.get("ms")} for r in s["rebuilds"]],
             "selftest": {k2: s["selftest"].get(k2) for k2 in ("ok", "why", "golden")} if s["selftest"] else None,
             "plan": {k2: s["plan"].get(k2) for k2 in ("T", "state", "demo", "B_T", "risk")} if s["plan"] else None,
             "no_init_line": bool(s.get("no_init"))}
        if s["plan"] and isinstance(s["plan"].get("T"), int) and s["plan"]["T"] > 0:
            e["plan"]["T_text"] = C.ymdhm(s["plan"]["T"]) + " serveur"
        ready = {}
        for b in C.ROBOT_BASES:
            r = s["ready"].get(b)
            nr = s["notready"].get(b, [])
            ready[b] = {"ready_after_s": (r["utc"] - s["utc"]) if r else None,
                        "notready_reasons": sorted({x.get("why") for x in nr if x.get("why")}),
                        "notready_s": (r["utc"] - nr[0]["utc"]) if (r and nr) else ((s["end"] - nr[0]["utc"]) if nr and s.get("end") else None),
                        "holes": r.get("holes") if r else None}
        e["ready"] = ready
        st_out.append(e)
        if i:
            if bs != "OK":
                anomalies.append(f"demarrage {k + 1} ({e['when']}) : build {i.get('build')} ({bs}) au lieu de {C.REQUIRED_BUILD} ou plus recent")
            if i.get("harness") == 1:
                anomalies.append(f"demarrage {k + 1} : build du banc d'essai (harness=1), pas le fichier dist/ClaudeRobot.mq5")
            if i.get("comm_pts") not in (6, None):
                anomalies.append(f"demarrage {k + 1} : commission or {i.get('comm_pts')} points au lieu de 6")
            if str(i.get("version")) not in ("2.00", "2.0", "2"):
                anomalies.append(f"demarrage {k + 1} : version {i.get('version')} au lieu de 2.00")
        if s["plan"] and s["plan"].get("state") == "unset":
            anomalies.append(f"demarrage {k + 1} : plan non regle (InpPlanStart = 0 sur un compte reel) : aucune nouvelle entree")
        if s["selftest"] and s["selftest"].get("ok") != 1:
            anomalies.append(f"demarrage {k + 1} : auto-test en echec ({s['selftest'].get('why')}) : aucune entree")
        if not s["selftest"] and i:
            anomalies.append(f"demarrage {k + 1} : pas de ligne SELFTEST")
        for b, x in (ready.items() if s["init"] else []):
            if x["ready_after_s"] is None and s.get("end") and s["end"] - s["utc"] > 900:
                anomalies.append(f"demarrage {k + 1} : {b} jamais pret ({', '.join(x['notready_reasons']) or 'aucune ligne READY'})")
            elif x["ready_after_s"] is not None and x["ready_after_s"] > 900:
                anomalies.append(f"demarrage {k + 1} : {b} pret seulement apres {x['ready_after_s'] // 60} min "
                                 f"({', '.join(x['notready_reasons'])})")
    if starts and all(s["init"] is None for s in starts):
        anomalies.append("aucune ligne INIT dans les fichiers : build et reglages inconnus (envoyer aussi le fichier du jour du demarrage)")
    res["starts"] = st_out
    res["restarts"] = max(len([s for s in starts if s["init"]]) - 1, 0)
    # the listed lines (live ones; COST, LATEBAR ... are live only anyway)
    listed = {}
    for ev in LISTED:
        rs = [r for r in lv if r["ev"] == ev]
        listed[ev] = [{"utc": r["utc"], "when": C.utc_txt(r["utc"]), "code": r["code"],
                       "fields": {k: v for k, v in r.items() if not k.startswith("_") and k not in ("utc", "ev", "code")},
                       "line": r["_raw"]} for r in rs]
    res["listed"] = listed
    missed_by_reason = Counter((r["code"], r.get("reason")) for r in lv if r["ev"] == "MISSED")
    res["missed_by_reason"] = {f"{c} {why}": n for (c, why), n in sorted(missed_by_reason.items())}
    for ev, why in (("ERROR", "erreur"), ("DUP", "position en double fermee"), ("SLFIX", "position sans stop fermee"),
                    ("REFUSED", "ordre refuse"), ("GUARD", "garde -50 % declenchee"), ("STOP", "arret du plan"), ("MARK", "marque de la garde"),
                    ("WATCH", "position plus vieille que sa sortie (copie VPS ?)"), ("ORPHAN", "position sans trade papier fermee"),
                    ("TAKEOVER", "verrou repris a une autre copie"), ("LOCK", "verrou journalier")):
        if listed[ev]:
            anomalies.append(f"{len(listed[ev])} ligne(s) {ev} ({why}), la premiere le {listed[ev][0]['when']} ({listed[ev][0]['code']})")
    def observing(r):
        k = r.get("_si")
        i = (starts[k]["init"] or {}) if k is not None and k < len(starts) else {}
        return i.get("observer") == 1

    def near_start(r):
        k = r.get("_si")
        if k is None or k >= len(starts) or starts[k].get("live_from") is None:
            return False
        return r["utc"] - starts[k]["live_from"] <= 900

    def at_start(r):
        return near_start(r) and r.get("reason") in ("late", "notready", "exited")

    def before_plan(r):
        """MISSED reason=observe whose intent came before the plan was in force: InpPlanStart set to the go-live time
        (SPEC 1 step 3) makes the paper trades already open at the first start 'observe' (CR_Sizing.mqh: the stamp is
        before T); a plan still to come ('future') or unset observes by design (the unset state is flagged apart)"""
        if r.get("reason") != "observe":
            return False
        k = r.get("_si")
        plan = starts[k]["plan"] if k is not None and k < len(starts) else None
        if plan is None:
            return near_start(r)
        if plan.get("state") in ("unset", "future"):
            return True
        T, st = plan.get("T"), r.get("stamp")
        if isinstance(T, int) and T > 0 and isinstance(st, int):
            return st < C.srv_to_utc(T)
        return near_start(r)
    start_missed = [r for r in lv if r["ev"] == "MISSED" and not observing(r) and at_start(r)]
    res["missed_at_start"] = [{"when": C.utc_txt(r["utc"]), "code": r["code"], "oid": r.get("oid"), "reason": r.get("reason")}
                              for r in start_missed]
    plan_missed = [r for r in lv if r["ev"] == "MISSED" and not observing(r) and before_plan(r)]
    res["missed_before_plan"] = [{"when": C.utc_txt(r["utc"]), "code": r["code"], "oid": r.get("oid"),
                                  "stamp": C.utc_txt(r["stamp"]) if isinstance(r.get("stamp"), int) else None} for r in plan_missed]
    bad_missed = [r for r in lv if r["ev"] == "MISSED" and r.get("reason") not in ("exited", "notrade") and not observing(r)
                  and not at_start(r) and not before_plan(r)]
    if bad_missed:
        anomalies.append(f"{len(bad_missed)} trade(s) MISSED non envoyes (raisons : "
                         f"{', '.join(sorted({str(r.get('reason')) for r in bad_missed}))})")
    clock_bad = [r for r in lv if r["ev"] == "CLOCK" and r.get("state") in ("wrong", "flat")]
    if clock_bad:
        anomalies.append(f"horloge du serveur decalee {len(clock_bad)} fois (CLOCK), la premiere le {C.utc_txt(clock_bad[0]['utc'])}")
    holes = {(r["code"], r.get("from"), r.get("to")) for r in lv if r["ev"] == "GAP" and r.get("accepted") == 0}
    accepted = {(r["code"], r.get("from"), r.get("to")) for r in lv if r["ev"] == "GAP" and r.get("accepted") == 1}
    live_gaps = [r for r in lv if r["ev"] == "GAP" and r.get("live") == 1]
    if holes - accepted:
        anomalies.append(f"{len(holes - accepted)} trou(s) dans l'historique jamais accepte(s) (GAP) : le marche est reste pas pret")
    if live_gaps:
        anomalies.append(f"{len(live_gaps)} minute(s) cotee(s) dont la barre n'est pas venue (GAP live=1)")
    hedging_off = [r for r in lv if r.get("why") == "not_hedging" or r.get("reason") == "not_hedging"]
    res["hedging"] = ("DIFFERENT" if hedging_off else ("OK" if any(r["ev"] == "FILL" for r in lv) else "UNKNOWN"))
    if hedging_off:
        anomalies.append("le compte n'est pas en mode hedging (le robot refuse d'ouvrir)")
    rc_seen = Counter((r["ev"], r.get("rc")) for r in lv if r["ev"] in ("SEND", "SLMOD", "CLOSE") and r.get("rc") not in (None, 0, 10009, 10008, 10010, 10025))
    res["broker_retcodes"] = {f"{ev} rc={rc}": n for (ev, rc), n in sorted(rc_seen.items(), key=lambda x: str(x))}
    res["freeze_level_refusals"] = sum(n for (ev, rc), n in rc_seen.items() if rc == 10029)
    res["filling_refusals"] = sum(n for (ev, rc), n in rc_seen.items() if rc == 10030)
    # COST: daily spreads against the model, gold commission against 0.06 USD per oz (SPEC 2.6)
    cost = []
    for r in [x for x in lv if x["ev"] == "COST"]:
        e = {"day": C.ymd(r.get("day", 0)), "symbol": r["code"], "raw_bp": r.get("raw_bp"), "paper_bp": r.get("paper_bp"),
             "model_bp": r.get("model_bp"), "comm_usd_oz": r.get("comm_usd_oz"), "comm_n": r.get("comm_n")}
        e["over_model"] = bool(e["paper_bp"] and e["model_bp"] and e["paper_bp"] > 1.5 * e["model_bp"])
        e["comm_off"] = bool(e["comm_usd_oz"] is not None and e["comm_n"] and abs(e["comm_usd_oz"] - 0.06) > 0.01)
        cost.append(e)
    res["cost"] = cost
    over = [c for c in cost if c["over_model"]]
    if over:
        anomalies.append(f"ecart achat-vente au-dessus de 1,5 fois le modele {len(over)} jour(s) (COST), par ex. {over[0]['symbol']} le "
                         f"{over[0]['day']} : {C.fr(over[0]['paper_bp'], 3)} pb pour {C.fr(over[0]['model_bp'], 2)}")
    coff = [c for c in cost if c["comm_off"]]
    if coff:
        anomalies.append(f"commission or eloignee de 0,06 USD/once {len(coff)} jour(s) (COST), par ex. {C.fr(coff[0]['comm_usd_oz'], 4)} le {coff[0]['day']}")
    # counts per sleeve
    counts = {}
    for c in C.CODES:
        counts[c] = {ev: {"live": sum(1 for r in lv if r["ev"] == ev and r["code"] == c),
                          "replayed": sum(1 for r in rows if r["ev"] == ev and r["code"] == c and r.get("rp") == 1)} for ev in COUNT_EV}
        counts[c]["DEC"]["orders_live"] = sum(1 for r in lv if r["ev"] == "DEC" and r["code"] == c and r.get("what") == "ord")
        counts[c]["DEC"]["skips_live"] = sum(1 for r in lv if r["ev"] == "DEC" and r["code"] == c and r.get("what") == "skip")
    res["counts"] = counts
    res["day_lines"] = [{"day": C.ymd(r.get("day", 0)), "utc": r["utc"], "balance": r.get("balance"), "equity": r.get("equity")}
                        for r in lv if r["ev"] == "DAY"]
    res["agg"] = [{"day": r.get("day"), **{b: r.get(b) for b in C.ROBOT_BASES}} for r in lv if r["ev"] == "AGG"]
    # missing daily files (B2): a gap in the DAY days that no stop, start or rebuild explains
    gaps, ranges = day_gaps(rows, files)
    res["day_gaps"] = gaps
    res["missing_ranges_utc"] = ranges
    res["missing_files"] = sorted({f for g in gaps if not g["explained"] for f in g["missing_files"]})
    for g in gaps:
        if g["explained"]:
            continue
        if g["missing_files"]:
            anomalies.append(f"fichier(s) du jour manquant(s) : {', '.join(g['missing_files'])} (aucune ligne DAY du {g['first_day']} au "
                             f"{g['last_day']} sans arret ni redemarrage du robot entre les deux) : les lignes de ces jours manquent "
                             "(positions, montants, comparaison)")
        else:
            anomalies.append(f"lignes du robot manquantes : aucune ligne DAY du {g['first_day']} au {g['last_day']} alors que les "
                             "fichiers de ces jours sont la (fichier coupe ?)")
    return res, anomalies, starts


# ---------------------------------------------------------------------------------------------- (b) fills
def point_sizes(rows, fiches):
    """point per symbol: fiches.csv when given, else from the SEND lines ((ask - bid) / s_raw), else 0.01"""
    out, how = {}, {}
    for b in C.ROBOT_BASES:
        f = fiches.get(b) if fiches else None
        if f and f.get("point"):
            out[b], how[b] = float(f["point"]), "fiches.csv"
            continue
        est = []
        for r in rows:
            if r["ev"] == "SEND" and C.SYM_OF_CODE.get(r["code"]) == b and r.get("s_raw") and r.get("ask") and r.get("bid"):
                est.append((r["ask"] - r["bid"]) / r["s_raw"])
        if est:
            p = C.median(est)
            out[b], how[b] = 10.0 ** round(math.log10(p)), "lignes SEND"
        else:
            out[b], how[b] = 0.01, "defaut 0,01 (le banc d'essai)"
    return out, how


EA_CLOSE_RC = (10009, 10010)                    # TRADE_RETCODE_DONE, TRADE_RETCODE_DONE_PARTIAL
STOP_REASONS = ("stop", "trail", "gap")         # paper exits that the broker's own stop makes (no CLOSE line)
KNOWN_EXITS = ("ea_close", "broker_stop_estimated", "broker_stop_race", "broker_stop_seen")
REASON_FR = {"time": "par le temps", "target": "a l'objectif", "rule": "par sa regle", "eod": "en fin de seance",
             "void": "annule (void)", "refused": "refuse", "nofill": "sans remplissage", "skip": "saute"}


def stop_crossed(tables, b, side, segs, t_from, t_to):
    """did the real quotes cross a position's broker stop between its fill and the paper's exit? ReleveFP's minutes
    hold the extremes of the ticks: a long position's stop is hit by the bid low (bl), a short's by the ask high (ah).
    segs = [(from_utc, level)] in time order (the FILL's sl, then each successful SLMOD). Returns (True, utc of the
    first minute that crossed), (False, None), or (None, None) when the minutes do not cover that time."""
    tb = (tables or {}).get(b)
    segs = [(u, lv) for u, lv in segs if u is not None and isinstance(lv, (int, float)) and lv > 0]
    if tb is None or not segs or not side or t_from is None or t_to is None:
        return None, None
    t = tb["t"]
    a, z = C.utc_to_srv(int(t_from)), C.utc_to_srv(int(t_to))
    if not len(t) or int(t[0]) > a or int(t[-1]) < z - 60:
        return None, None
    lo = a - a % 60 + 60                                            # the minutes after the fill's own minute
    for k, (s0, level) in enumerate(segs):
        sa = max(lo, C.utc_to_srv(int(s0)) - C.utc_to_srv(int(s0)) % 60) if k else lo
        sz = (C.utc_to_srv(int(segs[k + 1][0])) // 60 * 60) if k + 1 < len(segs) else z     # before the exit minute
        i0, i1 = int(np.searchsorted(t, sa, "left")), int(np.searchsorted(t, sz, "left"))
        if i1 <= i0:
            continue
        eps = 1e-9 * abs(level)
        hit = (tb["bl"][i0:i1] <= level + eps) if side > 0 else (tb["ah"][i0:i1] >= level - eps)
        if hit.any():
            return True, C.srv_to_utc(int(t[i0 + int(np.argmax(hit))]))
    return False, None


def fills_report(rows, res_a, starts, points, fiches, tables=None):
    """each real position against its paper trade; tables = the releve's minutes (--bars) or None"""
    lv = C.live(rows)
    comm_pts = next((s["init"].get("comm_pts") for s in starts if s["init"] and s["init"].get("comm_pts") is not None), 6)
    h = {b: (comm_pts * 0.5 * points[b] if b == "XAUUSD" else 0.0) for b in C.ROBOT_BASES}
    # measured gold commission per side in price units (COST comm_usd_oz is the round trip per oz)
    cm = [c["comm_usd_oz"] for c in res_a["cost"] if c["symbol"] == "XAUUSD" and c["comm_usd_oz"] is not None and c["comm_n"]]
    comm_side = {"XAUUSD": (C.median(cm) / 2 if cm else h["XAUUSD"]), "US100": 0.0, "BTCUSD": 0.0, "ETHUSD": 0.0}
    comm_src = "COST comm_usd_oz (mesuree)" if cm else "modele (6 points aller-retour)"
    chains = {}
    for c in C.CODES:
        done, voided = C.compare.paper_chain(rows, c)
        opened = {}
        for r in rows:                                                 # open paper trades (a PFILL without exit)
            if r["code"] == c and r["ev"] == "PFILL":
                opened[r["oid"]] = r
        chains[c] = (done, set(voided), opened)
    void_at = {(r["code"], r.get("oid")): r for r in rows if r["ev"] == "PVOID"}
    hold_x = defaultdict(int)                                          # the scheduled exit a HOLD moved (H2 ...)
    for r in rows:
        if r["ev"] == "HOLD" and isinstance(r.get("x"), int):
            hold_x[(r["code"], r.get("oid"))] = max(hold_x[(r["code"], r.get("oid"))], r["x"])
    # evidence that the live journal goes on past a time for a market: a live paper line of a later bar, or a later
    # server day whose AGG line fed bars of it
    last_bar = defaultdict(int)
    for r in lv:
        if r["ev"] in PAPER_EV and isinstance(r.get("bar"), int) and C.SYM_OF_CODE.get(r["code"]):
            last_bar[C.SYM_OF_CODE[r["code"]]] = max(last_bar[C.SYM_OF_CODE[r["code"]]], r["bar"])
    agg_days = defaultdict(list)
    for r in lv:
        if r["ev"] == "AGG" and isinstance(r.get("day"), int):
            for b in C.ROBOT_BASES:
                if isinstance(r.get(b), int) and r[b] > 0:
                    agg_days[b].append(r["day"])

    def fed_after(b, t):
        if last_bar[b] > t:
            return True
        d = C.utc_to_srv(int(t))
        return any(x > d - d % 86400 for x in agg_days[b])
    send = {(r["code"], r["oid"]): r for r in lv if r["ev"] == "SEND" and r.get("result") == "filled"}
    closes = defaultdict(list)
    for r in lv:
        if r["ev"] == "CLOSE":
            closes[r.get("ticket")].append(r)
    slm = defaultdict(list)
    for r in lv:
        if r["ev"] == "SLMOD" and r.get("ok") == 1:
            slm[r.get("ticket")].append(r)
    refused = {r.get("ticket"): r for r in lv if r["ev"] == "REFUSED" and r.get("ticket")}
    pos = {}
    for r in lv:
        if r["ev"] == "FILL":
            pos[r.get("ticket")] = {"ticket": r.get("ticket"), "code": r["code"], "oid": r.get("oid"), "side": r.get("side"), "lots": r.get("lots"),
                                    "entry_real": r.get("px"), "entry_utc": r["utc"], "sl": r.get("sl"), "risk": r.get("risk"),
                                    "stamp": r.get("stamp"), "src": "FILL", "budget": r.get("budget")}
        elif r["ev"] == "ADOPT" and r.get("ticket") not in pos:
            pos[r.get("ticket")] = {"ticket": r.get("ticket"), "code": r["code"], "oid": r.get("oid"), "side": None, "lots": None,
                                    "entry_real": None, "entry_utc": r.get("open"), "sl": None, "risk": None, "stamp": r.get("stamp"),
                                    "src": "ADOPT (entree hors du journal)"}
    anomalies = []
    # one paper trade, one real position (SPEC 4.3): an oid with two tickets is a second real trade (B3)
    tickets_of = defaultdict(list)
    for r in lv:
        if r["ev"] in ("FILL", "ADOPT") and r.get("ticket") and r.get("oid") is not None:
            if r["ticket"] not in tickets_of[(r["code"], r["oid"])]:
                tickets_of[(r["code"], r["oid"])].append(r["ticket"])
    dup_closed = {r.get("ticket") for r in lv if r["ev"] == "DUP"}
    doubles = [{"code": c, "oid": o, "tickets": ts, "dup_line": [t for t in ts[1:] if t in dup_closed]}
               for (c, o), ts in tickets_of.items() if len(ts) > 1]
    if doubles:
        x0 = doubles[0]
        anomalies.append(f"{len(doubles)} trade(s) papier avec deux positions reelles ou plus (un oid, plusieurs tickets), par ex. {x0['code']} "
                         f"oid {x0['oid']} : tickets {', '.join(str(t) for t in x0['tickets'])}"
                         + (" (le robot a ferme le double : ligne DUP)" if x0["dup_line"] else " sans ligne DUP"))
    out = []
    for t, p in pos.items():
        b = C.SYM_OF_CODE.get(p["code"])
        if b is None:
            continue
        pt = points[b]
        done, voided, opened = chains[p["code"]]
        f, x = done.get(p["oid"], (opened.get(p["oid"]), None))
        side = p["side"] or (f.get("side") if f else None)
        e = dict(p, symbol=b, paper_entry=f.get("px") if f else None, paper_entry_utc=f.get("utc") if f else None,
                 paper_exit=x.get("px") if x else None, paper_exit_utc=x.get("utc") if x else None,
                 paper_reason=x.get("reason") if x else None, paper_revised=bool(x and x["ev"] == "PREVISE"),
                 paper_voided=p["oid"] in voided, side=side)
        # EUR per price unit and lot: from the FILL line's own risk (BrkRiskMoney), else fiches.csv
        k = None
        if p.get("risk") and p.get("lots") and p.get("sl") and p.get("entry_real") and side:
            den = (side * (p["entry_real"] - p["sl"]) + 2 * h[b]) * p["lots"]
            if den > 0 and p["risk"] > 0:
                k = p["risk"] / den
        if k is None and fiches and fiches.get(b, {}).get("tick_value") and fiches[b].get("tick_size"):
            k = fiches[b]["tick_value"] / fiches[b]["tick_size"]
        e["eur_per_price_per_lot"] = k
        # the exit (B4, m3): an EA close needs ok=1, a done retcode and a price; ok=1 without them is the race where
        # the broker's stop closed the position just before the request (BrkClose: CTrade clears its result)
        cl_all = closes.get(t, [])
        good = [r for r in cl_all if r.get("ok") == 1 and r.get("rc") in EA_CLOSE_RC and isinstance(r.get("px"), (int, float)) and r["px"] > 0]
        race = [r for r in cl_all if r.get("ok") == 1 and r not in good]
        failed = [r for r in cl_all if r.get("ok") != 1]
        e["close_lines"] = len(cl_all)
        if failed:
            e["close_refused_rc"] = sorted({str(r.get("rc")) for r in failed})
        segs = ([(p.get("entry_utc"), p.get("sl"))] if p.get("sl") else
                ([(p.get("entry_utc"), slm[t][0].get("from"))] if slm.get(t) else []))
        segs += [(r["utc"], r.get("to")) for r in slm.get(t, [])]
        last_sl = segs[-1][1] if segs else None
        voided_row = void_at.get((p["code"], p["oid"])) if e["paper_voided"] else None
        t_end = x["utc"] if x is not None else (voided_row["utc"] if voided_row else None)
        reason = x.get("reason") if x is not None else ("void" if voided_row else None)
        if good:
            e.update(exit_real=good[0]["px"], exit_utc=good[0]["utc"], exit_kind="ea_close", close_why=good[0].get("why"))
        elif race:
            e.update(exit_real=last_sl, exit_utc=race[0]["utc"], exit_kind="broker_stop_race",
                     close_why="stop courtier juste avant la fermeture du robot (CLOSE sans prix, rc=0) : prix estime au stop")
        elif x is not None and reason in STOP_REASONS:
            e.update(exit_real=last_sl, exit_utc=x["utc"], exit_kind="broker_stop_estimated", close_why="stop courtier (prix estime au stop)")
        elif failed:
            e.update(exit_real=None, exit_utc=None, exit_kind="close_refused",
                     close_why=f"fermeture refusee (rc={','.join(e['close_refused_rc'])}) et jamais reussie dans le journal")
        elif t_end is None:
            xs = max((f.get("x") or 0) if f else 0, hold_x.get((p["code"], p["oid"]), 0))
            if xs > 0 and fed_after(b, xs + 60):
                e.update(exit_real=None, exit_utc=None, exit_kind="missing_exit",
                         close_why=f"aucune sortie dans le journal alors que sa sortie prevue ({C.utc_txt(xs)}) est passee : lignes manquantes ?")
            else:
                e.update(exit_real=None, exit_utc=None, exit_kind="open_or_unknown", close_why="encore ouverte a la fin du journal ?")
        else:
            seen, when = stop_crossed(tables, b, side, segs, p.get("entry_utc"), t_end)
            rfr = REASON_FR.get(reason, reason)
            if seen:
                e.update(exit_real=last_sl, exit_utc=when, exit_kind="broker_stop_seen",
                         close_why="stop courtier touche avant la sortie du papier (vu dans les minutes du releve) : prix estime au stop")
            elif seen is False:
                e.update(exit_real=None, exit_utc=None, exit_kind="not_closed",
                         close_why=f"position non fermee par le robot : pas de ligne CLOSE alors que le papier est sorti {rfr} le "
                                   f"{C.utc_txt(t_end)}, et les minutes du releve ne touchent pas son stop")
            else:
                e.update(exit_real=None, exit_utc=None, exit_kind="no_close_unknown",
                         close_why=f"pas de ligne CLOSE alors que le papier est sorti {rfr} le {C.utc_txt(t_end)} : position non fermee "
                                   "par le robot, ou stop du courtier touche avant (les minutes du releve, --bars, le diraient ; sinon "
                                   "l'historique du compte)")
        if t in refused:
            e["refused"] = refused[t].get("why")
        # the broker's own slippage: the fill against the quote the request went with (SEND bid / ask)
        sd = send.get((p["code"], p["oid"]))
        if sd and side and e.get("entry_real") is not None:
            q = sd.get("ask") if side > 0 else sd.get("bid")
            if q:
                e["send_quote"] = q
                e["fill_vs_quote_pts"] = side * (e["entry_real"] - q) / pt
                e["fill_vs_quote_bp"] = side * (e["entry_real"] - q) / q * 1e4
        # differences, positive = the real trade did worse than the paper
        if side and e.get("entry_real") is not None and e.get("paper_entry") is not None:
            d = side * (e["entry_real"] - e["paper_entry"])
            e["entry_diff_pts"] = d / pt
            e["entry_diff_bp"] = d / e["paper_entry"] * 1e4
            e["entry_diff_net_pts"] = (d + comm_side[b]) / pt
            e["entry_diff_net_bp"] = (d + comm_side[b]) / e["paper_entry"] * 1e4
            e["entry_diff_eur"] = d * e["lots"] * k if (k and e.get("lots")) else None
        if side and e.get("exit_real") is not None and e.get("paper_exit") is not None:
            d = side * (e["paper_exit"] - e["exit_real"])
            e["exit_diff_pts"] = d / pt
            e["exit_diff_bp"] = d / e["paper_exit"] * 1e4
            e["exit_diff_net_pts"] = (d + comm_side[b]) / pt
            e["exit_diff_net_bp"] = (d + comm_side[b]) / e["paper_exit"] * 1e4
            e["exit_diff_eur"] = d * e["lots"] * k if (k and e.get("lots")) else None
        if side and e.get("exit_real") is not None and e.get("entry_real") is not None and e.get("lots") and k:
            e["gross_eur"] = side * (e["exit_real"] - e["entry_real"]) * e["lots"] * k
            e["model_commission_eur"] = 2 * h[b] * e["lots"] * k
        e["late_by_design"] = p["code"] in ("GFP", "D4H", "ORX")
        out.append(e)
    out.sort(key=lambda e: (e.get("entry_utc") or 0))
    for kind, label in (("close_refused", "fermeture(s) refusee(s) et jamais reussie(s) dans le journal"),
                        ("not_closed", "position(s) non fermee(s) par le robot (sortie du papier passee, stop jamais touche)"),
                        ("no_close_unknown", "position(s) sans ligne CLOSE alors que le papier est sorti sans stop (non fermee par "
                                             "le robot, ou stop courtier avant : a verifier)"),
                        ("missing_exit", "position(s) sans aucune sortie au milieu du journal (lignes manquantes ?)")):
        xs = [e for e in out if e["exit_kind"] == kind]
        if xs:
            e0 = xs[0]
            anomalies.append(f"{len(xs)} {label}, par ex. {e0['code']} ticket {e0['ticket']} : {e0['close_why']} ; sortie inconnue, "
                             "laissee hors des totaux en euros")
    # per sleeve, per market and in total; points only within one market (their sizes differ), totals in bp and EUR
    per, per_sym = {}, {}
    groups = [(c, "code", c) for c in C.CODES] + [(b, "symbol", b) for b in C.ROBOT_BASES] + [("TOTAL", None, None)]
    for g, key_, val in groups:
        ps = [e for e in out if key_ is None or e[key_] == val]
        sel = (lambda r: True) if key_ is None else ((lambda r, v=val: r["code"] == v) if key_ == "code"
                                                     else (lambda r, v=val: C.SYM_OF_CODE.get(r["code"]) == v))
        size_live = [r for r in lv if r["ev"] == "SIZE" and sel(r)]
        fills_n = sum(1 for r in lv if r["ev"] == "FILL" and sel(r))
        pfill_live = sum(1 for r in lv if r["ev"] == "PFILL" and sel(r))
        skips = Counter(r.get("skip") for r in size_live)
        missed = Counter(r.get("reason") for r in lv if r["ev"] == "MISSED" and sel(r))
        q = {"paper_trades_live": pfill_live, "intents": len(size_live), "sized_to_send": skips.get("none", 0), "real_trades": fills_n,
             "share_intents_to_trades": (fills_n / len(size_live)) if size_live else None, "size_skips": dict(skips),
             "missed": dict(missed), "positions": len(ps)}
        keys = ["entry_diff_bp", "exit_diff_bp", "fill_vs_quote_bp", "entry_diff_net_bp", "exit_diff_net_bp"]
        if key_ is not None:
            keys += ["entry_diff_pts", "entry_diff_net_pts", "exit_diff_pts", "exit_diff_net_pts", "fill_vs_quote_pts"]
        for kk in keys:
            v = [e[kk] for e in ps if e.get(kk) is not None]
            q[kk + "_mean"] = C.mean(v)
            q[kk + "_median"] = C.median(v)
        for kk in ("entry_diff_eur", "exit_diff_eur", "gross_eur", "model_commission_eur"):
            v = [e[kk] for e in ps if e.get(kk) is not None]
            q[kk + "_sum"] = sum(v) if v else None
        q["exits"] = dict(Counter(e["exit_kind"] for e in ps))
        q["stop_exits_paper"] = sum(1 for e in ps if e.get("paper_reason") in STOP_REASONS)
        q["broker_stops_estimated"] = sum(1 for e in ps if e["exit_kind"] in ("broker_stop_estimated", "broker_stop_race", "broker_stop_seen"))
        q["exit_unknown"] = sum(1 for e in ps if e["exit_kind"] not in KNOWN_EXITS)
        (per_sym if key_ == "symbol" else per)[g] = q
    # money: DAY balances against the gross results of the positions closed between the first and the last DAY line;
    # incomplete when a position of that time has no known exit or a daily file is missing
    days = res_a["day_lines"]
    money = None
    if len(days) >= 2:
        t0, t1 = days[0]["utc"], days[-1]["utc"]
        closed = [e for e in out if e.get("exit_utc") and t0 <= e["exit_utc"] < t1 and e.get("gross_eur") is not None]
        unknown = [e for e in out if e["exit_kind"] not in KNOWN_EXITS and e["exit_kind"] != "open_or_unknown"
                   and (e.get("entry_utc") or 0) < t1]
        holes = [g for g in res_a.get("day_gaps", []) if not g["explained"]]
        db = (days[-1]["balance"] or 0) - (days[0]["balance"] or 0)
        gross = sum(e["gross_eur"] for e in closed)
        money = {"from": days[0]["day"], "to": days[-1]["day"], "balance_change_eur": db, "gross_from_prices_eur": gross,
                 "costs_not_in_prices_eur": db - gross, "model_commission_eur": sum(e.get("model_commission_eur") or 0 for e in closed),
                 "positions": len(closed), "with_estimated_stop_prices": sum(1 for e in closed if e["exit_kind"] != "ea_close"),
                 "positions_exit_unknown": len(unknown), "missing_days": sum(g["days"] for g in holes),
                 "complete": not unknown and not holes,
                 "note": "estimation : commission + swap + glissement des stops courtier + autres operations du compte"}
    return {"positions": out, "per_sleeve": per, "per_symbol": per_sym, "money_estimate": money, "points": points, "h_price": h,
            "commission_per_side_price": comm_side, "commission_source": comm_src, "duplicates": doubles, "anomalies": anomalies,
            "minutes_used_for_stops": bool(tables),
            "commission_swap_per_trade": "UNKNOWN : le journal n'a pas de ligne par transaction (deal)"}


# ---------------------------------------------------------------------------------------------- (c) replay
def read_m1(path):
    df = pd.read_csv(path, encoding="cp1252")
    need = ["time", "bo", "bh", "bl", "bc", "ao", "ah", "al", "ac", "n", "sp_mean", "sp_max"]
    miss = [c for c in need if c not in df.columns]
    if miss:
        raise ValueError(f"{os.path.basename(path)} : colonnes absentes {miss}")
    df = df[need].dropna()
    df["time"] = df["time"].astype(np.int64)
    return df.drop_duplicates("time").sort_values("time").reset_index(drop=True)


def m1_digits(path):
    with open(path, "rb") as h:
        h.readline()
        first = h.readline().decode("cp1252", errors="replace").strip()
    bo = first.split(",")[1] if first else ""
    return len(bo.split(".")[1]) if "." in bo else 0


def spread_points(df, digits):
    """each convention of MqlRates.spread, in points, from ReleveFP's columns; and the bounds of the bar's minimum
    spread (min over ticks of ask - bid): at most min(open, close, mean), at least n x mean - (n - 1) x max"""
    sc = 10.0 ** digits
    o = np.rint(df.ao.to_numpy() * sc) - np.rint(df.bo.to_numpy() * sc)
    c = np.rint(df.ac.to_numpy() * sc) - np.rint(df.bc.to_numpy() * sc)
    mean_ = df.sp_mean.to_numpy() * sc
    mx = np.rint(df.sp_max.to_numpy() * sc)
    n = df.n.to_numpy().astype(float)
    conv = {"open": o, "close": c, "mean": np.floor(mean_ + 0.5), "max": mx, "min2": np.minimum(o, c)}
    lo = np.maximum(0.0, n * mean_ - (n - 1) * mx) - 0.5
    hi = np.minimum(np.minimum(o, c), mean_ + 0.5)
    return {k: v.astype(np.int64) for k, v in conv.items()}, lo, hi


def mask_kept(t_srv, fam):
    """CR_Bars.mqh BarsMaskReason: True for a kept bar (server seconds); NYSE half days from the calendar"""
    dw = ((t_srv // 86400) + 4) % 7
    smin = (t_srv % 86400) // 60
    ny = t_srv - 7 * 3600
    nmin = (ny % 86400) // 60
    keep = np.ones(len(t_srv), bool)
    if fam != "CRY":
        keep &= ~((dw == 0) | (dw == 6))
    else:
        keep &= ~((dw == 0) | (dw == 6) | ((dw == 5) & (smin >= 23 * 60 + 55)))
    if fam == "IDX":
        keep &= ~((nmin >= 16 * 60 + 15) & (nmin < 18 * 60))
        import datetime as dt
        half = np.array([C.nyse_kind(dt.date(1970, 1, 1) + dt.timedelta(days=int(d))) == "half" for d in (ny // 86400)], bool)
        keep &= ~((nmin >= 13 * 60 + 16) & (nmin < 18 * 60) & half)
    if fam == "XAU":
        keep &= ~((nmin >= 17 * 60) & (nmin < 18 * 60))
    return keep


def calibrate(live_rows, tables):
    """which ReleveFP column gives the bar spread the robot saw: (1) every live paper line carries its bar (UTC) and that
    bar's s_raw; (2) every COST line carries the day's median raw spread in bp of the mid over the kept bars"""
    per = {k: {"n": 0, "match": 0} for k in SPREAD_CONV}
    min_ok = {"n": 0, "inside": 0}
    for r in live_rows:
        if r["ev"] not in PAPER_EV or r.get("s_raw") is None or r.get("bar") is None:
            continue
        b = C.SYM_OF_CODE.get(r["code"])
        if b not in tables:
            continue
        tb = tables[b]
        i = tb["index"].get(C.utc_to_srv(int(r["bar"])))
        if i is None:
            continue
        for k in SPREAD_CONV:
            per[k]["n"] += 1
            per[k]["match"] += int(tb["conv"][k][i] == r["s_raw"])
        min_ok["n"] += 1
        min_ok["inside"] += int(tb["lo"][i] <= r["s_raw"] <= tb["hi"][i])
    cost = {k: [] for k in SPREAD_CONV}
    for r in live_rows:
        if r["ev"] != "COST" or r.get("raw_bp") is None or r["code"] not in tables:
            continue
        tb = tables[r["code"]]
        day = int(r.get("day", 0))
        sel = (tb["t"] >= day) & (tb["t"] < day + 86400) & tb["kept"]
        if sel.sum() < 10:
            continue
        for k in SPREAD_CONV:
            s = tb["conv"][k][sel] * tb["point"]
            mid = tb["bid_o"][sel] + s / 2
            med = float(np.median(s / mid * 1e4))
            cost[k].append(abs(med - r["raw_bp"]) / max(r["raw_bp"], 1e-12))
    out = {"paper_lines": per, "min_consistent": min_ok,
           "cost_days": {k: {"days": len(v), "mean_rel_err": (sum(v) / len(v)) if v else None} for k, v in cost.items()}}
    choice, why = "open", "defaut (export_frames.py prend l'ecart de l'ouverture)"
    n = per["open"]["n"]
    if n >= 10:
        best = max(SPREAD_CONV, key=lambda k: (per[k]["match"], k == "open"))
        choice, why = best, f"{per[best]['match']} barres sur {n} egales a s_raw des lignes du papier"
    elif any(v for v in cost.values()):
        best = min((k for k in SPREAD_CONV if cost[k]), key=lambda k: sum(cost[k]) / len(cost[k]))
        choice, why = best, f"ecart median du jour le plus proche des lignes COST ({len(cost[best])} jours)"
    out["choice"], out["why"] = choice, why
    return out


def write_bin(path, digits, t, o, h, l_, c, s):
    rec = np.empty(len(t), REC)
    rec["t"], rec["o"], rec["h"], rec["l"], rec["c"], rec["s"] = t, o, h, l_, c, np.maximum(s, 0)
    with open(path, "wb") as f:
        f.write(b"CRB1")
        f.write(np.int32(digits).tobytes())
        f.write(np.int64(len(t)).tobytes())
        f.write(rec.tobytes())


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def build_exe(comm_pts, rebuild=False):
    """dist/ClaudeRobot.mq5 through check/build.py with the harness (CR_HARNESS), cached by the sha256 of every input"""
    from build import BUILD, build
    work = os.path.join(BUILD, REPLAY_NAME)
    exe = os.path.join(work, "replay")
    stamp = os.path.join(work, "demo_stamp.json")
    want = {"dist": sha(C.DIST), "comm_pts": int(comm_pts)}
    for f in ("mock_replay.h", "mql5_shim.h", "mock_faults.h", "to_cpp.py", "build.py"):
        want[f] = sha(os.path.join(C.CHECK, f))
    if not rebuild and os.path.exists(exe) and os.path.exists(stamp):
        try:
            if json.load(open(stamp)) == want:
                return exe, [], True
        except ValueError:
            pass
    exe, warn = build(C.DIST, name=REPLAY_NAME, comm_pts=int(comm_pts))
    with open(stamp, "w") as f:
        json.dump(want, f)
    return exe, warn, False


def line_key(r):
    ev = r["ev"]
    if ev == "DEC":
        return (ev, r["code"], r.get("what"), r["utc"], r.get("oid", 0), r.get("tf", 0))
    if ev in PAPER_EV:
        return (ev, r["code"], r.get("oid"), r.get("bar"))
    if ev == "SIZE":
        return (ev, r["code"], r.get("oid"), r["utc"])
    if ev == "MISSED":
        return (ev, r["code"], r.get("oid"), r.get("stamp"))
    return (ev, r["code"], r["utc"])


def key_time(r):
    return int(r.get("stamp") if r["ev"] == "MISSED" and r.get("stamp") is not None else r["utc"])


def dec_time(r):
    """the decision time of the order a line belongs to (oid = decision x 100 + sleeve id, SPEC 2.4)"""
    oid = r.get("oid")
    return int(oid) // 100 if isinstance(oid, int) and oid > 0 else None


def keyed(rows):
    out, seen = {}, Counter()
    for r in rows:
        k = line_key(r)
        seen[k] += 1
        out[k + (seen[k],)] = r
    return out


def same(a, b):
    if isinstance(a, float) or isinstance(b, float):
        try:
            x, y = float(a), float(b)
        except (TypeError, ValueError):
            return "diff"
        if math.isnan(x) and math.isnan(y):
            return "equal"
        if x == y:
            return "equal"
        if abs(x - y) <= REL_TOL * max(abs(x), abs(y)):
            return "tol"
        return "diff"
    return "equal" if a == b else "diff"


def compare_fields(a, b, mode):
    """(status, differing fields) of two lines with the same key; status equal / tol / diff"""
    ev = a["ev"]
    if ev == "SIZE":
        fields = list(SIZE_FREE) + (SIZE_ACCOUNT if mode.get("account_fields") else [])
        if mode.get("skip"):
            fields.append("skip")
    elif ev == "MISSED":
        fields = ["reason"]
    else:
        fields = sorted((set(a) | set(b)) - {"ev", "code", "rp"} - {k for k in set(a) | set(b) if k.startswith("_")})
    st, bad = "equal", []
    for f in fields:
        s = same(a.get(f), b.get(f))
        if s == "diff":
            bad.append(f)
        elif s == "tol" and st == "equal":
            st = "tol"
    return ("diff" if bad else st), bad


INF = 1 << 62


def chain_intervals(rows, code):
    """[fill, exit) of every paper trade of a sleeve in these rows (live and replayed lines, the last PFILL of an oid
    wins as in compare.paper_chain); a trade with no exit stays open to the end"""
    done, voided = C.compare.paper_chain(rows, code)
    iv = [(int(f["utc"]), int(x["utc"])) for f, x in done.values()]
    opened = {}
    for r in rows:
        if r["code"] == code and r["ev"] == "PFILL":
            opened[r["oid"]] = r
    for oid, f in opened.items():
        if oid not in done and oid not in voided:
            iv.append((int(f["utc"]), INF))
    return iv


def first_flat(t_min, iv_a, iv_b):
    """the first time at or after t_min when neither chain holds an open paper trade: from then on both chains take
    the same trades (the one-position rule carries no older state)"""
    cands = sorted({t_min} | {e for (_, e) in iv_a + iv_b if t_min <= e < INF})
    for t in cands:
        if not any(a <= t < b for a, b in iv_a) and not any(a <= t < b for a, b in iv_b):
            return t
    return INF


OUT_WARMUP = "echauffement du rejeu (pas assez d'historique avant)"
OUT_SPAN = "hors de la periode des minutes du releve"
OUT_GAP = "journal du robot manquant a ce moment (fichier du jour absent)"


class Windows:
    """where a live line can be compared: inside its sleeve's own span (the markets it reads all have minutes) after
    the sleeve's warm-up and once both paper chains have been flat together, while the live copy ran live with the
    same paper inputs, outside the hours of a missing daily file"""

    def __init__(self, starts, spans, inputs, flat=None, no_bars=(), gaps=()):
        self.flat = flat or {}
        self.no_bars = set(no_bars)
        self.spans = spans                          # {code: (first UTC, last UTC compared)}
        self.gaps = list(gaps)
        self.cover = []
        for s in starts:
            if s.get("live_from") is None or not s.get("end"):
                continue
            same_in = paper_inputs(s["init"]) == inputs if s["init"] else True
            self.cover.append((s["live_from"], s["end"], same_in))
        self.no_init = not self.cover

    def why_out(self, code, t, t_dec=None):
        """t = the line's own time, t_dec = its order's decision (oid // 100), so that every line of one paper trade is
        in or out together"""
        td = t if t_dec is None else min(t, t_dec)
        if code in self.no_bars or code not in self.spans:
            return "pas de minutes du releve pour ce marche"
        r0, r1 = self.spans[code]
        if td < r0 or t > r1:
            return OUT_SPAN
        if code in WARMUP_DAYS and td < r0 + WARMUP_DAYS[code] * 86400:
            return OUT_WARMUP
        if td < self.flat.get(code, 0):
            return "chaines papier pas encore alignees (un trade ouvert d'un seul cote au debut du rejeu)"
        if any(a <= t <= b or a <= td <= b for a, b in self.gaps):
            return OUT_GAP
        if self.no_init:
            return None
        for a, b, same_in in self.cover:
            if a < t <= b:
                return None if same_in else "autres reglages du robot a ce moment"
        return "robot pas en marche (en direct) a ce moment"


def disturbances(live_rows):
    """live events that change what the live robot saw: LATEBAR, GAP, REBUILD, INIT, NOTREADY, SETTLE (per symbol or all)"""
    out = []
    for r in live_rows:
        if r["ev"] in ("LATEBAR", "GAP", "NOTREADY") and r["code"] in C.ROBOT_BASES:
            out.append((r["utc"], r["code"], r["ev"]))
        elif r["ev"] in ("REBUILD", "INIT", "SETTLE", "CLOCK"):
            out.append((r["utc"], "*", r["ev"]))
    return out


def near(dist, code, t):
    syms = C.READS_OF_CODE.get(code, [])
    hits = [ev for (u, s, ev) in dist if abs(u - t) <= NEAR_S and (s == "*" or s in syms)]
    return sorted(set(hits))


def compare_lines(live_rows, rep_rows, win, mode, dist, replay_ready):
    lv = keyed([r for r in live_rows if r["ev"] in COMPARE_EV and r.get("rp") != 1])
    rp = keyed([r for r in rep_rows if r["ev"] in COMPARE_EV and r.get("rp") != 1])
    stats = {ev: Counter() for ev in COMPARE_EV}
    diffs, account, excluded = [], [], Counter()
    compared = Counter()                                     # lines compared per sleeve (coverage)
    span_seen = {}                                           # first and last compared time per sleeve
    for k in sorted(set(lv) | set(rp), key=lambda k: (key_time(lv.get(k) or rp.get(k)), str(k))):
        a, b = lv.get(k), rp.get(k)
        r = a or b
        ev, code = r["ev"], r["code"]
        why = win.why_out(code, key_time(r), dec_time(r))
        if why:
            excluded[why] += 1
            continue
        compared[code] += 1
        t_ = key_time(r)
        f_, l_ = span_seen.get(code, (t_, t_))
        span_seen[code] = (min(f_, t_), max(l_, t_))
        # a MISSED line of the live copy alone: every reason but 'exited' comes from the real account; on a trading copy
        # 'exited' can too (an intent waiting to be sent, P5, or a stop the price crossed before the request)
        if ev == "MISSED" and a and not b and (mode.get("trading") or a.get("reason") != "exited"):
            account.append({"kind": "missed_account", "live": a["_raw"]})
            stats[ev]["account"] += 1
            continue
        if a and b:
            st, bad = compare_fields(a, b, mode)
            if ev == "SIZE" and mode.get("skip") and bad == ["skip"] and b.get("skip") == "notready" and not replay_ready.get(C.SYM_OF_CODE.get(code), True):
                st, bad = "equal", []
                stats[ev]["skip_replay_not_ready"] += 1
            stats[ev][st] += 1
            if st == "diff":
                diffs.append({"kind": "different", "event": ev, "code": code, "fields": bad, "when": C.utc_txt(key_time(r)), "_t": key_time(r),
                              "near_live_events": near(dist, code, key_time(r)), "live": a["_raw"], "replay": b["_raw"]})
        elif a:
            stats[ev]["only_live"] += 1
            diffs.append({"kind": "only_live", "event": ev, "code": code, "when": C.utc_txt(key_time(r)), "_t": key_time(r),
                          "near_live_events": near(dist, code, key_time(r)), "live": a["_raw"], "replay": None})
        else:
            stats[ev]["only_replay"] += 1
            diffs.append({"kind": "only_replay", "event": ev, "code": code, "when": C.utc_txt(key_time(r)), "_t": key_time(r),
                          "near_live_events": near(dist, code, key_time(r)), "live": None, "replay": b["_raw"]})
    session_skips = {r["utc"] for r in live_rows if r["ev"] == "DEC" and r["code"] == "GFP" and r.get("what") == "info"
                     and r.get("v1") == 4.0 and r.get("rp") != 1}
    for d in diffs:
        t = d.get("_t")
        if d["code"] == "GFP" and any(abs(t - u) <= 4 * 3600 for u in session_skips):
            d["hint"] = ("vendredi saute en direct pour la seance or de FP (DEC info v1=4) : le courtier du banc d'essai ne liste "
                         "aucune seance (mock_replay.h SymbolInfoSessionTrade), le rejeu ne saute pas")
    for d in diffs:
        if d.get("fields") and ("s_raw" in d["fields"] or "s_paper" in d["fields"]) and not d.get("hint"):
            d["hint"] = ("l'ecart de la barre (MqlRates.spread) n'est pas celui que le releve donne pour cette minute : prix acheteur "
                         "du papier differents (SPEC 10.3)")
        d.pop("_t", None)
    per_sleeve = defaultdict(Counter)
    for d in diffs:
        per_sleeve[d["code"]][d["kind"]] += 1
    return {"by_event": {ev: dict(c) for ev, c in stats.items()}, "differences": diffs, "account_dependent": account,
            "excluded": dict(excluded), "per_sleeve_differences": {c: dict(v) for c, v in per_sleeve.items()},
            "compared_per_sleeve": dict(compared), "compared_span_per_sleeve": span_seen}


def side_by_side(live_rows, rep_rows, first_day_srv=None):
    """AGG (kept bars fed per server day and symbol) and COST (median spreads) of both sides; the replay's first server
    day is left out of AGG (CR_Main.mqh MainDaily starts its counters at the first barrier of a run)"""
    agg_l = {r.get("day"): r for r in live_rows if r["ev"] == "AGG"}
    agg_r = {r.get("day"): r for r in rep_rows if r["ev"] == "AGG"}
    agg = []
    for d in sorted(set(agg_l) & set(agg_r)):
        if first_day_srv is not None and d <= first_day_srv:
            continue
        e = {"day": C.ymd(d)}
        for b in C.ROBOT_BASES:
            e[b] = (agg_l[d].get(b), agg_r[d].get(b))
        e["same"] = all(x[0] == x[1] for x in (e[b] for b in C.ROBOT_BASES))
        agg.append(e)
    cost_l = {(r["code"], r.get("day")): r for r in live_rows if r["ev"] == "COST"}
    cost_r = {(r["code"], r.get("day")): r for r in rep_rows if r["ev"] == "COST"}
    cost = []
    for k in sorted(set(cost_l) & set(cost_r), key=str):
        a, b = cost_l[k], cost_r[k]
        cost.append({"symbol": k[0], "day": C.ymd(k[1]), "raw_bp": (a.get("raw_bp"), b.get("raw_bp")),
                     "paper_bp": (a.get("paper_bp"), b.get("paper_bp")),
                     "same": same(a.get("raw_bp"), b.get("raw_bp")) != "diff"})
    return {"agg": agg, "agg_days_same": sum(1 for e in agg if e["same"]), "agg_days": len(agg), "cost": cost,
            "cost_same": sum(1 for e in cost if e["same"]), "cost_n": len(cost)}


def load_minutes(bars_dir, fiches):
    """ReleveFP's m1_<BASE>.csv files of --bars as tables (the replay's bars and the broker-stop check of the fills).
    Returns (tables, files used, problems)."""
    tables, files_used, problems = {}, {}, []
    for b in C.ROBOT_BASES:
        p = os.path.join(bars_dir, f"m1_{b}.csv")
        if not os.path.exists(p):
            problems.append(f"m1_{b}.csv absent : les regles de {b} ne sont pas rejouees")
            continue
        try:
            df = read_m1(p)
        except Exception as e:
            problems.append(f"m1_{b}.csv illisible : {str(e)[:100]}")
            continue
        if not len(df):
            problems.append(f"m1_{b}.csv vide")
            continue
        dg = (fiches.get(b) or {}).get("digits") if fiches and (fiches.get(b) or {}).get("found") else None
        dg = int(dg) if dg is not None else m1_digits(p)
        conv, lo, hi = spread_points(df, dg)
        t = df.time.to_numpy()
        tables[b] = {"df": df, "digits": dg, "point": 10.0 ** -dg, "conv": conv, "lo": lo, "hi": hi, "t": t,
                     "index": {int(x): i for i, x in enumerate(t)}, "bid_o": df.bo.to_numpy(), "kept": mask_kept(t, C.FAMILY[b]),
                     "bl": df.bl.to_numpy().astype(float), "ah": df.ah.to_numpy().astype(float)}
        files_used[b] = os.path.basename(p)
    return tables, files_used, problems


def inp_days_needed(live0, last_minute):
    """ReleveFP's InpDays that lets every sleeve be compared from the start of the live journal: the longest warm-up
    (D4H, 120 days) and 5 days for the paper chains to align, before the first live day"""
    need = int(math.ceil((last_minute - live0) / 86400.0)) + max(WARMUP_DAYS.values()) + 6
    return max(150, need)


def replay_check(rows, starts, minutes, out, fiches, spread_opt, inputs_extra, rebuild, scrub, gaps=()):
    lv = C.live(rows)
    rep = {"status": "not run"}
    tables, files_used, problems = minutes
    problems = list(problems)
    # the inputs: the start with the longest live time
    best = None
    for s in starts:
        if s["init"] is None:
            continue
        dur = (s.get("end") or s["utc"]) - (s.get("live_from") or s["utc"])
        if best is None or dur > best[0]:
            best = (dur, s)
    init = best[1]["init"] if best else {}
    plan = best[1]["plan"] if best else None
    names = {b: (init.get(b) if init and init.get(b) else ((fiches.get(b) or {}).get("name") or b + ".r")) for b in C.ROBOT_BASES}
    if not tables:
        rep.update(status="impossible", why="aucun fichier m1_<marche>.csv lisible dans --bars", problems=problems)
        return rep
    cal = calibrate(lv, tables)
    conv = cal["choice"] if spread_opt == "auto" else spread_opt
    rep["spread"] = {"calibration": cal, "used": conv, "asked": spread_opt}
    work = os.path.join(out, "replay")
    bars_out = os.path.join(work, "bars")
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(bars_out)
    syms = {}
    first, last = {}, {}
    for b in C.ROBOT_BASES:
        path = os.path.join(bars_out, f"{names[b]}.bin")
        if b in tables:
            tb = tables[b]
            sc = 10.0 ** tb["digits"]
            o, h, l_, c = (np.rint(tb["df"][k].to_numpy() * sc).astype(np.int64) for k in ("bo", "bh", "bl", "bc"))
            write_bin(path, tb["digits"], tb["t"], o, h, l_, c, tb["conv"][conv])
            first[b], last[b] = C.srv_to_utc(int(tb["t"][0])), C.srv_to_utc(int(tb["t"][-1]))
        else:
            dg = int((fiches.get(b) or {}).get("digits") or 2) if fiches else 2
            write_bin(path, dg, np.zeros(0, np.int64), *(np.zeros(0, np.int64) for _ in range(5)))
        syms[names[b]] = path
    span = [min(first.values()), max(last.values())]
    # each sleeve's own span: the markets it reads must all have minutes (M4: a market whose history at the broker is
    # short delays its own sleeves only, and is named)
    spans = {}
    for c in C.CODES:
        rd = C.READS_OF_CODE[c]
        if all(b in tables for b in rd):
            spans[c] = (max(first[b] for b in rd), min(last[b] for b in rd) - 3600)
    for b in sorted(tables):
        codes = ", ".join(c for c in C.CODES if b in C.READS_OF_CODE[c])
        if first[b] > span[0] + 86400:
            problems.append(f"m1_{b}.csv commence le {C.utc_txt(first[b])}, plus tard que les autres marches ({C.utc_txt(span[0])}) : "
                            f"historique du courtier plus court ; {codes} compare(s) a partir de cette date et de leur echauffement")
        if last[b] < span[1] - 86400:
            problems.append(f"m1_{b}.csv finit le {C.utc_txt(last[b])}, plus tot que les autres ({C.utc_txt(span[1])}) : {codes} "
                            "compare(s) jusqu'a cette date")
    # the replay's inputs (INIT and PLAN lines, --input), observer
    env = {"MOCK_QUIET": "1", "MOCK_INPUT_InpTrade": "false", "MOCK_INPUT_InpPush": "false",
           "MOCK_ACCOUNT": "demo" if (init or {}).get("demo", 1) == 1 else "real"}
    if init:
        env["MOCK_INPUT_InpRiskTable"] = str(init.get("risk"))
        env["MOCK_INPUT_InpSleeves"] = str(init.get("sleeves"))
        for sw, inp in (("K1", "InpK1"), ("H2", "InpH2"), ("S0.75r", "InpS075")):
            if init.get(sw) in ("on", "off"):
                env[f"MOCK_INPUT_{inp}"] = "1" if init[sw] == "on" else "0"
        env["MOCK_INPUT_InpK1T"] = str(init.get("k1t") or "")
    if plan:
        if isinstance(plan.get("T"), int):
            env["MOCK_INPUT_InpPlanStart"] = str(plan["T"])
        if isinstance(plan.get("B_T"), (int, float)) and plan["B_T"] > 0:
            env["MOCK_BALANCE"] = repr(float(plan["B_T"]))
    for b in C.ROBOT_BASES:
        f = (fiches or {}).get(b)
        if f and f.get("found"):
            for k, mk in (("contract_size", "UNITS"), ("vol_min", "VMIN"), ("vol_step", "VSTEP"), ("vol_max", "VMAX")):
                if f.get(k):
                    env[f"MOCK_{mk}_{names[b]}"] = repr(float(f[k]))
    for kv in inputs_extra or []:
        k, v = kv.split("=", 1)
        env[f"MOCK_INPUT_{k.strip()}"] = v
    comm = (init or {}).get("comm_pts", 6)
    comm = 6 if comm is None else comm
    t0 = time.time()
    try:
        exe, warn, cached = build_exe(comm, rebuild)
    except Exception as e:
        rep.update(status="build failed", why=str(e)[-2000:], problems=problems)
        return rep
    rep["build"] = {"name": REPLAY_NAME, "cached": cached, "warnings": len(warn), "seconds": round(time.time() - t0, 1),
                    "comm_pts": comm}
    from build import replay
    files = os.path.join(work, "files")
    t1 = time.time()
    try:
        so, wall = replay(exe, files, syms, env=env, timeout=7200)
    except Exception as e:
        rep.update(status="replay failed", why=str(e)[-2000:], problems=problems)
        return rep
    rep["run"] = {"stdout": so.splitlines()[-1] if so else "", "seconds": round(time.time() - t1, 1), "replay_wall_s": round(wall, 1),
                  "inputs": {k: v for k, v in env.items() if k.startswith("MOCK_INPUT_") or k in ("MOCK_ACCOUNT", "MOCK_BALANCE")}}
    rrows, rinfo = C.read_journal_files(C.journal_paths(files))
    rep["replay_journal"] = {"lines": rinfo["lines"], "unparsable": rinfo["unparsable"], "files": len(rinfo["files"])}
    rlive = C.live(rrows)
    rep["replay_errors"] = [r["_raw"] for r in rlive if r["ev"] == "ERROR"][:20]
    ready_r = {r["code"]: True for r in rlive if r["ev"] == "READY"}
    replay_ready = {b: ready_r.get(b, False) for b in C.ROBOT_BASES}
    rep["replay_ready"] = replay_ready
    observer = all((s["init"] or {}).get("observer") == 1 or (s["init"] or {}).get("entries_off") == 1 for s in starts if s["init"]) \
        and not any(r["ev"] == "FILL" for r in lv)
    mode = {"account_fields": observer and bool(plan), "skip": observer, "trading": not observer}
    rep["size_mode"] = {"live_copy_observer": observer, "compared": SIZE_FREE + (SIZE_ACCOUNT if mode["account_fields"] else [])
                        + (["skip"] if mode["skip"] else []), "never": SIZE_NEVER,
                        "why": ("the replay is not given the account's deal history: the journal holds no deal line (no broker "
                                "stop fill, commission or swap), so MOCK_DEALS could only be guessed and every later lot would "
                                "differ anyway; SIZE is compared on the fields that do not depend on the account or on the tick of "
                                "the request; with an observer copy the robot never moved the balance, so B, P_in, rate, m, w and "
                                "the week unit are compared from the PLAN line's B(T)")}
    span_to = span[1] - 3600
    flat = {c: (first_flat(spans[c][0] + WARMUP_DAYS[c] * 86400, chain_intervals(rows, c), chain_intervals(rrows, c))
                if c in spans else INF) for c in C.CODES}
    no_bars = [c for c in C.CODES if c not in spans]
    win = Windows(starts, spans, paper_inputs(init), flat, no_bars, gaps)
    rep["span"] = {"from": C.utc_txt(span[0]), "to": C.utc_txt(span[1]), "compared_to": C.utc_txt(span_to),
                   "warmup_days": WARMUP_DAYS,
                   "per_sleeve": {c: [C.utc_txt(a), C.utc_txt(z)] for c, (a, z) in spans.items()},
                   "sleeves_compared_from": {c: (C.utc_txt(flat[c]) if flat[c] < INF else "jamais") for c in C.CODES}}
    rep["comparison"] = compare_lines(rows, rrows, win, mode, disturbances(lv), replay_ready)
    # coverage (M3): what was really compared per sleeve, against the live journal's time
    cover = [(s["live_from"], s["end"]) for s in starts if s.get("live_from") is not None and s.get("end")]
    live0 = min(a for a, _ in cover) if cover else span[0]
    live1 = max(z for _, z in cover) if cover else span[1]
    cmpd = rep["comparison"]["compared_per_sleeve"]
    cov, short = {}, []
    for c in C.CODES:
        if c not in spans:
            cov[c] = {"from": None, "to": None, "lines": 0, "never": True, "partial": True,
                      "why": "pas de minutes du releve pour " + ", ".join(b for b in C.READS_OF_CODE[c] if b not in tables)}
            continue
        lo = max(spans[c][0] + WARMUP_DAYS[c] * 86400, flat[c])
        a, z = max(lo, live0), min(spans[c][1], live1)
        if a >= z:
            why = (f"echauffement de {WARMUP_DAYS[c]} jours : minutes du releve depuis le {C.utc_txt(spans[c][0])}, comparable a partir "
                   f"du {C.utc_txt(lo) if lo < INF else '?'}")
            cov[c] = {"from": None, "to": None, "lines": cmpd.get(c, 0), "never": True, "partial": True, "why": why}
            short.append(c)
        else:
            part = a > live0 + 86400 or z < live1 - 86400
            cov[c] = {"from": C.utc_txt(a), "to": C.utc_txt(z), "lines": cmpd.get(c, 0), "never": False, "partial": part,
                      "why": ("debut de la demo hors des minutes du releve (echauffement)" if a > live0 + 86400 else "")}
            if part:
                short.append(c)
    rep["coverage"] = cov
    rep["coverage_short"] = short
    if short:
        rep["coverage_advice"] = (f"pour comparer toutes les sleeves sur toute la demo, relancer ReleveFP avec InpDays="
                                  f"{inp_days_needed(live0, span[1])} (les echauffements vont jusqu'a {max(WARMUP_DAYS.values())} jours)")
    first_srv = min(int(tb["t"][0]) for tb in tables.values())
    rep["side_by_side"] = side_by_side(lv, rlive, first_srv - first_srv % 86400)
    rep["names"] = names
    rep["files"] = files_used
    rep["problems"] = problems
    rep["status"] = "done"
    return rep


# ---------------------------------------------------------------------------------------------- (d) printed lines
def printed_check(rows, prows, starts, scrub):
    lv_raw = Counter(r["_raw"] for r in rows if r.get("rp") != 1)
    p_init = [r for r in prows if r["ev"] == "INIT" and "build" in r]
    same_copy = bool(p_init) and all(lv_raw.get(r["_raw"], 0) > 0 for r in p_init)
    res = {"lines": len(prows), "inits": len(p_init), "same_copy_as_files": same_copy,
           "printed_vps": any(r.get("vps") == 1 for r in p_init)}
    if prows:
        t0, t1 = min(r["utc"] for r in prows), max(r["utc"] for r in prows)
        res["from"], res["to"] = C.utc_txt(t0), C.utc_txt(t1)
    else:                                       # no robot line at all (the terminal's Journal tab, say): nothing checked
        res.update(kind="aucune ligne du robot", ok=False)
        return res
    if same_copy or not p_init:
        p_raw = Counter(r["_raw"] for r in prows)
        missing_in_files = [x for x in p_raw if lv_raw.get(x, 0) == 0]
        if prows:
            t0, t1 = min(r["utc"] for r in prows), max(r["utc"] for r in prows)
            span_live = [r["_raw"] for r in rows if r.get("rp") != 1 and t0 <= r["utc"] <= t1]
        else:
            span_live = []
        not_printed = [x for x in span_live if p_raw.get(x, 0) == 0]
        res.update(kind="meme copie", printed_not_in_files=missing_in_files[:50], n_printed_not_in_files=len(missing_in_files),
                   live_not_printed=not_printed[:50], n_live_not_printed=len(not_printed),
                   replayed_lines_printed=sum(1 for r in prows if r.get("rp") == 1))
        res["ok"] = not missing_in_files and not not_printed and res["replayed_lines_printed"] == 0
        return res
    # another copy (the VPS's): SPEC 10.12 step 3 on the common live time of both copies
    pst = starts_of(prows)
    fst = starts
    cover_p = [(s.get("live_from"), s.get("end")) for s in pst if s.get("live_from") and s.get("end")]
    cover_f = [(s.get("live_from"), s.get("end")) for s in fst if s.get("live_from") and s.get("end")]

    class W2:
        def why_out(self, code, t, t_dec=None):
            del t_dec
            inp = any(a < t <= b for a, b in cover_p) or not cover_p
            inf = any(a < t <= b for a, b in cover_f) or not cover_f
            return None if (inp and inf) else "une des deux copies n'etait pas en marche"
    mode = {"account_fields": True, "skip": True, "trading": False}
    res.update(kind="autre copie (VPS ?)", comparison=compare_lines(rows, prows, W2(), mode, disturbances(C.live(rows)), {}))
    res["ok"] = not res["comparison"]["differences"]
    return res


# ---------------------------------------------------------------------------------------------- report
def read_fiches_near(paths):
    for p in paths:
        if p and os.path.exists(p):
            sys.path.insert(0, HERE)
            import read_mac_files as R
            f, _ = R.read_fiches(p)
            return f
    return {}


def french_report(rep):
    a, b, r = rep["journal"], rep["fills"], rep.get("replay")
    L = []
    L.append(f"Journal du robot : {len(rep['inputs']['journal_files'])} fichier(s), {a['lines']} lignes "
             f"({a['live_lines']} en direct, {a['replayed_lines']} rejouees au demarrage), {rep['inputs']['unparsable']} illisible(s).")
    for sk in rep["inputs"].get("skipped_files", []):
        L.append(f"  fichier ignore : {sk['file']} : {sk['why']}")
    if rep["inputs"].get("foreign_lines"):
        L.append(f"  {rep['inputs']['foreign_lines']} ligne(s) etrangere(s) au robot dans ses fichiers (texte jamais recopie ; "
                 "fichier et numero de ligne dans report.json)")
    for g in a.get("day_gaps", []):
        if g["explained"]:
            L.append(f"  pas de ligne DAY du {g['first_day']} au {g['last_day']} : robot arrete ou historique rejoue entre les deux (normal)")
        else:
            L.append(f"  JOURS MANQUANTS du {g['first_day']} au {g['last_day']} : "
                     + (f"fichier(s) absent(s) {', '.join(g['missing_files'])}" if g["missing_files"] else "lignes DAY absentes (fichier coupe ?)"))
    if a.get("first_utc"):
        L.append(f"Periode en direct : du {C.utc_txt(a['first_utc'])} au {C.utc_txt(a['last_utc'])}.")
    L.append(f"Demarrages : {len(a['starts'])} (redemarrages : {a['restarts']}).")
    for s in a["starts"]:
        sw = ", ".join(f"{k} {v}" for k, v in s["switches"].items() if v)
        L.append(f"  - {s['when']} : build {s['build']} ({s['build_status']}), demo={s['demo']} vps={s['vps']} observateur={s['observer']} "
                 f"entrees coupees={s['entries_off']} commission or {s['comm_pts']} pts, plan {s['risk']}, sleeves {s['sleeves']}"
                 + (f", {sw}" if sw else "") + (f", K1T {s['k1t']}" if s.get("k1t") else ""))
        if s["selftest"]:
            L.append(f"    auto-test : {'ok' if s['selftest']['ok'] == 1 else 'ECHEC ' + str(s['selftest']['why'])}, {s['selftest'].get('golden')} vecteurs")
        if s["plan"]:
            deb = s["plan"].get("T_text") or ("le debut de l'historique du compte" if s["plan"]["T"] == 0 else s["plan"]["T"])
            L.append(f"    plan : etat {s['plan']['state']}, debut {deb}, B(T) {C.fr(s['plan']['B_T'], 2, 'EUR')}"
                     + {"future": " (plan pas encore en vigueur : aucune entree avant son debut)",
                        "unset": " (plan non regle : aucune entree)"}.get(s["plan"].get("state"), ""))
        rd = ", ".join(f"{k} {('pret apres ' + C.fr(v['ready_after_s'] / 60, 1, 'min')) if v['ready_after_s'] is not None else 'jamais pret'}"
                       for k, v in s["ready"].items())
        L.append(f"    marches : {rd}")
        if s.get("deinit") is not None:
            L.append(f"    arret : {s['deinit_fr'] or s['deinit']} (code {s['deinit']})")
    L.append("")
    L.append("Lignes a regarder (en direct) :")
    any_l = False
    for ev in LISTED:
        xs = a["listed"].get(ev, [])
        if not xs:
            continue
        any_l = True
        if ev == "COST":
            L.append(f"  COST : {len(xs)} lignes (une par jour et par marche)")
            for sym in C.ROBOT_BASES:
                cs = [c for c in a["cost"] if c["symbol"] == sym]
                if not cs:
                    continue
                cm = [c["comm_usd_oz"] for c in cs if c.get("comm_usd_oz") is not None and c.get("comm_n")]
                L.append(f"    {sym} : ecart brut median {C.fr(C.median([c['raw_bp'] for c in cs]), 3)} pb, papier "
                         f"{C.fr(C.median([c['paper_bp'] for c in cs]), 3)} pb, modele {C.fr(cs[0]['model_bp'], 2)} pb"
                         + (f", commission or mediane {C.fr(C.median(cm), 4)} USD/once (modele 0,06)" if cm else "")
                         + (f" ; {sum(c['over_model'] for c in cs)} jour(s) au-dessus de 1,5 x le modele" if any(c["over_model"] for c in cs) else ""))
            continue
        L.append(f"  {ev} : {len(xs)}")
        for x in xs[:12]:
            f = x["fields"]
            brief = ", ".join(f"{k}={v}" for k, v in f.items() if k in ("why", "reason", "what", "state", "src", "ticket", "oid", "raw_bp",
                                                                          "paper_bp", "comm_usd_oz", "accepted", "rc", "kept"))
            L.append(f"    {x['when']} {x['code']} {brief}")
        if len(xs) > 12:
            L.append(f"    ... {len(xs) - 12} de plus (voir report.json)")
    if not any_l:
        L.append("  aucune")
    if a.get("missed_at_start"):
        L.append(f"  trades papier deja ouverts a un demarrage, non rejoints (SPEC 4.8 d, 9.9 : seulement dans les 5 min de leur "
                 f"heure) : {len(a['missed_at_start'])} (" + ", ".join(f"{m['code']} {m['reason']}" for m in a["missed_at_start"][:8]) + ")")
    if a.get("missed_before_plan"):
        L.append(f"  trades papier d'avant le debut du plan (InpPlanStart), non envoyes (MISSED observe, normal) : "
                 f"{len(a['missed_before_plan'])} (" + ", ".join(m["code"] for m in a["missed_before_plan"][:10]) + ")")
    if a.get("broker_retcodes"):
        L.append("  codes du courtier : " + ", ".join(f"{k} x{v}" for k, v in a["broker_retcodes"].items())
                 + f" (niveau de gel 10029 : {a['freeze_level_refusals']}, remplissage 10030 : {a['filling_refusals']})")
    L.append("  mode hedging : " + {"OK": "OK (le robot a ouvert des positions ; il refuse tout autre mode)",
                                    "DIFFERENT": "DIFFERENT (le robot a refuse d'ouvrir : compte pas en hedging)",
                                    "UNKNOWN": "INCONNU (aucune position ouverte dans le journal)"}[a["hedging"]])
    L.append("")
    L.append("Lignes par sleeve (en direct ; rejouees entre parentheses) :")
    L.append("  sleeve  DEC(ordres)  PFILL  PEXIT  SIZE  SEND  FILL  CLOSE  MISSED")
    for c, q in a["counts"].items():
        L.append(f"  {c:6s}  {q['DEC']['live']:4d} ({q['DEC']['orders_live']:3d})  {q['PFILL']['live']:5d}  {q['PEXIT']['live']:5d}  "
                 f"{q['SIZE']['live']:4d}  {q['SEND']['live']:4d}  {q['FILL']['live']:4d}  {q['CLOSE']['live']:5d}  {q['MISSED']['live']:6d}"
                 f"   (DEC {q['DEC']['replayed']}, PFILL {q['PFILL']['replayed']}, SIZE {q['SIZE']['replayed']})")
    L.append("")
    L.append("Positions reelles contre le papier (ecart positif = le reel a fait moins bien) :")
    tot = b["per_sleeve"]["TOTAL"]
    L.append(f"  intentions (lignes SIZE en direct) : {tot['intents']}, envoyees : {tot['sized_to_send']}, trades reels : {tot['real_trades']}"
             + (f" ({C.fr(100 * tot['share_intents_to_trades'], 1)} %)" if tot["share_intents_to_trades"] is not None else ""))
    skips = {k: v for k, v in tot["size_skips"].items() if k != "none"}
    if skips:
        L.append("  raisons des intentions non envoyees : " + ", ".join(f"{k} {v}" for k, v in skips.items()))
    if a["starts"] and all(s["observer"] == 1 for s in a["starts"]):
        L.append("  copie observatrice (InpTrade false hors VPS) : elle n'envoie aucun ordre, c'est normal (SPEC 4.9)")
    if not tot["positions"]:
        L.append("  aucune position reelle dans le journal")
    def pos_line(name, q, pts):
        net = ""
        if name in ("GFP", "D4H", "ORX", "XAUUSD"):
            net = (f" [commission comprise : entree {C.frs(q.get('entry_diff_net_pts_mean'), 2, 'pts')}, sortie "
                   f"{C.frs(q.get('exit_diff_net_pts_mean'), 2, 'pts')} ; le papier de l'or met la commission dans ses prix]")
        ent = (f"{C.frs(q.get('entry_diff_pts_mean'), 2, 'pts')} ({C.frs(q['entry_diff_bp_mean'], 2, 'pb')})" if pts
               else C.frs(q["entry_diff_bp_mean"], 2, "pb"))
        sor = (f"{C.frs(q.get('exit_diff_pts_mean'), 2, 'pts')} ({C.frs(q['exit_diff_bp_mean'], 2, 'pb')})" if pts
               else C.frs(q["exit_diff_bp_mean"], 2, "pb"))
        fil = (f"{C.frs(q.get('fill_vs_quote_pts_mean'), 2, 'pts')} ({C.frs(q['fill_vs_quote_bp_mean'], 2, 'pb')})" if pts
               else C.frs(q["fill_vs_quote_bp_mean"], 2, "pb"))
        unk = f", {q['exit_unknown']} sortie(s) inconnue(s) (hors des euros)" if q.get("exit_unknown") else ""
        return (f"  {name:6s} {q['positions']} position(s) : entree {ent} en moyenne, sortie {sor}, soit "
                f"{C.frs((q['entry_diff_eur_sum'] or 0) + (q['exit_diff_eur_sum'] or 0), 2, 'EUR')} ; stops : {q['stop_exits_paper']} au papier, "
                f"{q['broker_stops_estimated']} chez le courtier (prix estime){unk} ; remplissage contre le prix de l'envoi {fil}" + net)
    for c in C.CODES:
        if b["per_sleeve"][c]["positions"]:
            L.append(pos_line(c, b["per_sleeve"][c], True))
    if tot["positions"]:
        L.append("  par marche (les points d'un marche ne se comparent pas a ceux d'un autre) :")
        for sym in C.ROBOT_BASES:
            q = b["per_symbol"].get(sym)
            if q and q["positions"]:
                L.append("  " + pos_line(sym, q, True))
        L.append(pos_line("TOTAL", tot, False) + " (en pb et en euros seulement)")
        ex = Counter()
        for e in b["positions"]:
            ex[e["exit_kind"]] += 1
        kinds_fr = {"ea_close": "fermees par le robot", "broker_stop_estimated": "stop courtier (prix estime)",
                    "broker_stop_race": "stop courtier juste avant la fermeture du robot", "broker_stop_seen":
                    "stop courtier vu dans les minutes du releve", "close_refused": "FERMETURE REFUSEE", "not_closed": "NON FERMEES",
                    "no_close_unknown": "SANS LIGNE CLOSE (a verifier)", "missing_exit": "SANS SORTIE (lignes manquantes ?)",
                    "open_or_unknown": "encore ouvertes a la fin du journal"}
        L.append("  sorties : " + ", ".join(f"{kinds_fr.get(k, k)} {n}" for k, n in ex.most_common()))
        for e in [e for e in b["positions"] if e["exit_kind"] not in KNOWN_EXITS and e["exit_kind"] != "open_or_unknown"][:10]:
            L.append(f"    {e['code']} ticket {e['ticket']} ouverte le {C.utc_txt(e['entry_utc']) if e.get('entry_utc') else '?'} : {e['close_why']}")
    L.append(f"  commission et swap par trade : inconnus (le journal n'a pas de ligne par transaction) ; commission or retenue : "
             f"{b['commission_source']}.")
    if b.get("money_estimate") and b["money_estimate"]["positions"]:
        m = b["money_estimate"]
        L.append(f"  solde du {m['from']} au {m['to']} : {C.frs(m['balance_change_eur'], 2, 'EUR')} ; resultat brut des prix "
                 f"{C.frs(m['gross_from_prices_eur'], 2, 'EUR')} ; difference {C.frs(m['costs_not_in_prices_eur'], 2, 'EUR')} "
                 f"(commission + swap + glissement des stops, estimation ; commission du modele {C.fr(m['model_commission_eur'], 2, 'EUR')})")
        if not m.get("complete", True):
            L.append(f"  attention : estimation incomplete ({m['positions_exit_unknown']} position(s) sans prix de sortie connu, "
                     f"{m['missing_days']} jour(s) de journal manquant(s)) : la difference n'est pas que des frais")
    L.append("")
    if r is None:
        L.append("Rejeu : non demande (--bars absent).")
    elif r.get("status") != "done":
        L.append(f"Rejeu : {r.get('status')} ({str(r.get('why', ''))[:300]})")
    else:
        cal = r["spread"]["calibration"]
        L.append(f"Rejeu des minutes du releve ({r['span']['from']} - {r['span']['to']}) avec le banc d'essai (observateur) :")
        pl = cal["paper_lines"]
        L.append("  ecart de la barre (MqlRates.spread) : " + ", ".join(f"{k} {pl[k]['match']}/{pl[k]['n']}" for k in SPREAD_CONV)
                 + f" ; minimum compatible {cal['min_consistent']['inside']}/{cal['min_consistent']['n']} ; retenu : {r['spread']['used']} ({cal['why']})")
        best = max(pl[k]["match"] for k in SPREAD_CONV)
        if pl["open"]["n"] and best < 0.99 * pl["open"]["n"]:
            L.append(f"  attention : aucune colonne du releve ne redonne l'ecart de toutes les barres ({best}/{pl['open']['n']} au mieux) ; "
                     f"si le minimum est compatible ({cal['min_consistent']['inside']}/{cal['min_consistent']['n']}), MT5 garde l'ecart minimum de "
                     f"la minute, que ReleveFP n'ecrit pas : les differences de s_raw et des prix acheteur en viennent")
        sb = r["side_by_side"]
        L.append(f"  barres par jour identiques (AGG) : {sb['agg_days_same']}/{sb['agg_days']} jours ; ecart du jour identique (COST) : "
                 f"{sb['cost_same']}/{sb['cost_n']}")
        cmpr = r["comparison"]
        sm = r["size_mode"]
        L.append(f"  SIZE compare sur : {', '.join(sm['compared'])} (jamais : {', '.join(sm['never'])}, qui suivent le compte reel "
                 f"ou le tick de l'envoi ; le journal n'a pas l'historique des transactions pour les rejouer)")
        for ev in COMPARE_EV:
            st = cmpr["by_event"].get(ev, {})
            if st:
                L.append(f"  {ev:7s} : " + ", ".join(f"{k} {v}" for k, v in sorted(st.items())))
        L.append("  couverture par sleeve (lignes comparees) :")
        for c, cv in r.get("coverage", {}).items():
            if cv["never"]:
                L.append(f"    {c:4s} jamais compare ({cv['why']})")
            else:
                L.append(f"    {c:4s} compare du {cv['from']} au {cv['to']} ({cv['lines']} lignes)" + (f" ; {cv['why']}" if cv.get("why") else ""))
        if r.get("coverage_advice"):
            L.append(f"  {r['coverage_advice']}")
        if cmpr["excluded"]:
            L.append("  non compare : " + ", ".join(f"{k} ({v})" for k, v in cmpr["excluded"].items()))
        if cmpr["account_dependent"]:
            L.append(f"  lignes qui dependent du compte reel (non comparees) : {len(cmpr['account_dependent'])}")
        if cmpr["differences"]:
            L.append(f"  DIFFERENCES : {len(cmpr['differences'])}, par sleeve : "
                     + ", ".join(f"{c} {sum(v.values())}" for c, v in cmpr["per_sleeve_differences"].items()) + " (premieres lignes de chaque cote) :")
            for d in cmpr["differences"][:15]:
                L.append(f"    [{d['kind']}] {d['event']} {d['code']} {d['when']}" + (f" champs {','.join(d['fields'])}" if d.get("fields") else "")
                         + (f" (pres de {','.join(d['near_live_events'])})" if d.get("near_live_events") else ""))
                if d.get("hint"):
                    L.append(f"      explication probable : {d['hint']}")
                L.append(f"      direct : {d['live'] or '-'}")
                L.append(f"      rejeu  : {d['replay'] or '-'}")
            if len(cmpr["differences"]) > 15:
                L.append(f"    ... {len(cmpr['differences']) - 15} de plus (voir report.json)")
        else:
            L.append("  aucune difference sur les lignes comparees")
        if r.get("replay_errors"):
            L.append(f"  erreurs du rejeu : {len(r['replay_errors'])}")
        for p in r.get("problems", []):
            L.append(f"  note : {p}")
    p = rep.get("printed")
    if p is not None:
        L.append("")
        for nm in p.get("files_without_robot_lines", []):
            L.append(f"Lignes imprimees : {nm} ne contient aucune ligne du robot (journal du terminal ? il faut l'onglet Experts)")
        if p.get("kind") == "aucune ligne du robot":
            L.append("Lignes imprimees : aucune ligne du robot dans les fichiers --printed : rien n'a pu etre compare.")
        elif p.get("kind") == "meme copie":
            L.append(f"Lignes imprimees (onglet Experts) : meme copie que les fichiers ; {p['n_printed_not_in_files']} absente(s) des fichiers, "
                     f"{p['n_live_not_printed']} ligne(s) des fichiers non imprimee(s), {p['replayed_lines_printed']} ligne(s) rp=1 imprimee(s).")
        else:
            cm = p.get("comparison", {})
            L.append(f"Lignes imprimees : {p.get('kind')} ; {len(cm.get('differences', []))} difference(s) sur les lignes de SPEC 10.12.")
    L.append("")
    if rep["anomalies"]:
        L.append("A REGARDER :")
        L += [f"  - {x}" for x in rep["anomalies"]]
    else:
        L.append("Verdict : rien d'anormal.")
    return L


def short_summary(rep):
    a, b, r = rep["journal"], rep["fills"], rep.get("replay")
    S = [f"Journal : {a['live_lines']} lignes en direct, {len(a['starts'])} demarrage(s), build "
         f"{', '.join(sorted({str(s['build']) for s in a['starts']})) or '?'}."]
    tot = b["per_sleeve"]["TOTAL"]
    if tot["positions"]:
        S.append(f"Trades : {tot['intents']} intentions, {tot['real_trades']} trades reels, {tot['positions']} positions suivies ; "
                 f"ecart moyen avec le papier : entree {C.frs(tot['entry_diff_bp_mean'], 2, 'pb')}, sortie "
                 f"{C.frs(tot['exit_diff_bp_mean'], 2, 'pb')}, en tout {C.frs((tot['entry_diff_eur_sum'] or 0) + (tot['exit_diff_eur_sum'] or 0), 2, 'EUR')}"
                 f" (points par marche dans report_fr.txt).")
    else:
        S.append(f"Trades : {tot['intents']} intentions, aucun trade reel"
                 + (" (copie observatrice : normal)." if a["starts"] and all(s["observer"] == 1 for s in a["starts"]) else "."))
    if r is not None and r.get("status") == "done":
        n = len(r["comparison"]["differences"])
        ncmp = sum(r["comparison"].get("compared_per_sleeve", {}).values())
        S.append(f"Rejeu : {n} difference(s) sur {ncmp} lignes comparees ; ecart de barre retenu : {r['spread']['used']}.")
        cov = r.get("coverage", {})
        never = [c for c, v in cov.items() if v["never"]]
        part = [c for c, v in cov.items() if v["partial"] and not v["never"]]
        if never or part:
            S.append("  couverture : " + (f"jamais comparees : {', '.join(never)}" if never else "")
                     + (" ; " if never and part else "") + (f"en partie seulement : {', '.join(part)}" if part else "")
                     + (f" ; {r['coverage_advice']}" if r.get("coverage_advice") else ""))
    elif r is not None:
        S.append(f"Rejeu : {r.get('status')}.")
    if rep["anomalies"]:
        S.append(f"A regarder ({len(rep['anomalies'])}) :")
        S += [f"  - {x}" for x in rep["anomalies"][:20]]
        if len(rep["anomalies"]) > 20:
            S.append(f"  ... et {len(rep['anomalies']) - 20} autres (report_fr.txt)")
    else:
        S.append("Rien d'anormal.")
    return S


def run(args):
    scrub = C.Scrubber()
    out = C.safe_out(args.out)
    paths = C.journal_paths(args.journals)
    if not paths:
        raise SystemExit("aucun fichier .log du robot dans le dossier --journals")
    rows, info = C.read_journal_files(paths, scrub)
    if not rows:
        why = "; ".join(f"{s_['file']} : {s_['why']}" for s_ in info["skipped_files"][:5])
        raise SystemExit(scrub.text(f"aucune ligne du robot dans --journals ({why}) : il faut les fichiers "
                                    "MQL5/Files/ClaudeRobot/<aaaammjj>.log du robot"))
    fiches = read_fiches_near([args.fiches, os.path.join(args.bars, "fiches.csv") if args.bars else None])
    builds = C.known_builds()
    res_a, anomalies, starts = analyse_journal(rows, builds, info["files"])
    minutes = load_minutes(args.bars, fiches) if args.bars else ({}, {}, [])
    points, how = point_sizes(rows, fiches)
    res_b = fills_report(rows, res_a, starts, points, fiches, minutes[0])
    res_b["points_source"] = how
    rep = {"tool": "check_demo", "version": 2,
           "inputs": {"journal_files": info["files"], "unparsable": info["unparsable"], "unparsable_first": info["unparsable_first"],
                      "skipped_files": info["skipped_files"], "foreign_lines": info["foreign_lines"],
                      "foreign_first": info["foreign_first"]},
           "required_build": C.REQUIRED_BUILD, "known_builds": builds, "journal": res_a, "fills": res_b, "anomalies": anomalies}
    if info["skipped_files"]:
        anomalies.append(f"{len(info['skipped_files'])} fichier(s) ignore(s) dans --journals : "
                         + "; ".join(f"{s_['file']} ({s_['why']})" for s_ in info["skipped_files"][:4]))
    if info["unparsable"]:
        anomalies.append(f"{info['unparsable']} ligne(s) illisible(s) dans le journal (fichier coupe ?)")
    if info["foreign_lines"]:
        anomalies.append(f"{info['foreign_lines']} ligne(s) qui ne sont pas du robot dans ses fichiers (premiere : "
                         f"{info['foreign_first'][0]['file']} ligne {info['foreign_first'][0]['line']})")
    unmatched = [e for e in res_b["positions"] if e.get("paper_entry") is None]
    if unmatched:
        anomalies.append(f"{len(unmatched)} position(s) reelle(s) sans trade papier connu dans le journal")
    anomalies += res_b["anomalies"]
    if args.bars and not args.no_replay:
        r = replay_check(rows, starts, minutes, out, fiches, args.spread, args.input, args.rebuild, scrub,
                         res_a.get("missing_ranges_utc", []))
        rep["replay"] = r
        if r.get("status") == "done":
            d = r["comparison"]["differences"]
            if d:
                anomalies.append(f"rejeu : {len(d)} ligne(s) differente(s) entre le robot et le banc d'essai "
                                 f"(par sleeve : {', '.join(f'{c} {sum(v.values())}' for c, v in r['comparison']['per_sleeve_differences'].items())})")
            if r.get("replay_errors"):
                anomalies.append(f"rejeu : {len(r['replay_errors'])} ligne(s) ERROR dans le journal du banc d'essai")
            sb = r["side_by_side"]
            if sb["agg_days"] and sb["agg_days_same"] < sb["agg_days"]:
                anomalies.append(f"rejeu : nombre de barres different {sb['agg_days'] - sb['agg_days_same']} jour(s) sur {sb['agg_days']} "
                                 "(les minutes du releve ne sont pas exactement les barres du courtier)")
            if sb["cost_n"] and sb["cost_same"] < sb["cost_n"]:
                bad = [e for e in sb["cost"] if not e["same"]]
                anomalies.append(f"rejeu : ecart median du jour (COST) different {len(bad)} fois sur {sb['cost_n']}, par ex. {bad[0]['symbol']} "
                                 f"le {bad[0]['day']} : {C.fr(bad[0]['raw_bp'][0], 4)} pb en direct, {C.fr(bad[0]['raw_bp'][1], 4)} au rejeu "
                                 "(l'ecart des minutes du releve n'est pas exactement celui des barres du courtier)")
        else:
            anomalies.append(f"rejeu impossible : {r.get('status')} ({str(r.get('why', ''))[:200]})")
    elif args.bars:
        rep["replay"] = {"status": "skipped (--no-replay)", "problems": minutes[2]}
    if args.printed:
        prows, pinfo = C.read_journal_files(args.printed, scrub, printed=True)
        p = printed_check(rows, prows, starts, scrub)
        p["unparsable"] = pinfo["unparsable"]
        p["other_lines_ignored"] = pinfo["other_lines_ignored"]
        p["files_without_robot_lines"] = pinfo["files_without_robot_lines"]
        p["robot_lines_per_file"] = pinfo["robot_lines_per_file"]
        rep["printed"] = p
        for nm in pinfo["files_without_robot_lines"]:
            anomalies.append(f"fichier --printed {nm} : aucune ligne du robot (journal du terminal ? il faut l'onglet Experts)")
        if not p.get("ok") and p.get("kind") != "aucune ligne du robot":
            anomalies.append("lignes imprimees (onglet Experts) differentes des fichiers du robot (voir report_fr.txt)")
    lines = french_report(rep)
    C.write_json(os.path.join(out, "report.json"), C.clean_json(rep), scrub)
    C.write_text(os.path.join(out, "report_fr.txt"), lines, scrub)
    print(scrub.text("\n".join(short_summary(rep))))
    return rep, out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--journals", required=True)
    ap.add_argument("--bars")
    ap.add_argument("--printed", action="append")
    ap.add_argument("--out", default=C.DEFAULT_OUT)
    ap.add_argument("--fiches")
    ap.add_argument("--spread", default="auto", choices=["auto"] + SPREAD_CONV)
    ap.add_argument("--input", action="append", help="InpName=value for an input the INIT line does not show")
    ap.add_argument("--no-replay", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args(argv)
    C.warn_if_in_repo([a.journals, a.bars] + list(a.printed or []))
    run(a)
    out = C.safe_out(a.out)
    print(f"Fichiers ecrits : {os.path.join(out, 'report.json')} et {os.path.join(out, 'report_fr.txt')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
