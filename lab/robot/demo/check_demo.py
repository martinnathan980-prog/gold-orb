"""Check two weeks of the robot on the FP demo account from the files the user sends back from the Mac.

    python3 -I lab/robot/demo/check_demo.py --journals DIR [--bars DIR] [--printed FILE ...] [--out DIR]
                                            [--fiches FILE] [--spread auto|open|close|mean|max|min2|min]
                                            [--input InpName=value ...] [--no-replay] [--rebuild]

--journals  the robot's daily files MQL5/Files/ClaudeRobot/<yyyymmdd>.log (CR_Journal.mqh JrnAt: one line
            CR|<utc>|<EVENT>|<code>|k=v|... per event, utc = the event's lab time, doubles DoubleToString(x, -16);
            lines of a rebuild's replay end with |rp=1 and are written to the file only). The line format is
            check/compare.py's (read-only); every field is checked against the robot's own (demo_common.SCHEMA: a
            number for each numeric key, a fixed vocabulary for each text key, every field the robot always writes,
            printable ASCII only): a line that fails is unreadable, counted and located, and its text is never kept.
            Every line, the robot's included, is scanned for account values first, so that they are masked everywhere.
            A .log file that is not a robot journal (MetaTrader's own logs have the same <yyyymmdd>.log names: UTF-16,
            or no line starting with 'CR|') is skipped and named. The text of a line that is not a robot line is never
            kept or written (it may hold the login, the server, the holder's name or the user folder).
            Missing daily files: the robot writes a DAY line for every server day it runs live (weekends included,
            written at the first minute of a later day into that day's file, CR_Main.mqh MainDaily); after a REBUILD
            the next DAY line is the rebuild day's (the replay writes none but leaves the day counter there); a start
            or a stop (INIT) breaks the chain until the next REBUILD. Any other jump in the DAY days means lost lines:
            the absent files are named, the positions whose exit lines were in them are flagged, the money estimate
            is marked incomplete, and their hours are left out of the replay comparison. The chain cannot see a lost
            last file: a journal whose last live line is not the robot's stop (INIT deinit) is flagged (robot still
            running, or last file missing), and with ReleveFP's run time (fini.txt server_time beside the m1 files or
            fiches.csv, fiches.csv's tick times, the end of its minutes) the days without a file up to it are named;
            a journal that reaches ReleveFP's day without a stop line is a robot still running (no anomaly).
            Lost lines without a lost file: lines the robot always writes in pairs are checked on the journal alone
            (a PFILL or SIZE without the DEC of its order, a PEXIT, PREVISE, PSTOP or HOLD without its PFILL, a filled
            SEND without its FILL and a FILL without its SEND, a CLOSE or SLMOD whose ticket has no FILL or ADOPT, a paper
            trade with no exit before the next one of its sleeve or after its time exit): each break is 'ligne(s) du
            journal manquante(s)' unless it falls in a hole already named, and it makes the money estimate incomplete.
            Lines OnInit writes before its INIT line (a CLOCK of the guards' clock check, an ERROR) belong to that start.
            Review3: every SLMOD starts from the stop the journal last showed (the FILL's sl, the previous move), and a
            position the broker's stop closed carried the stop the robot sets for the paper's last stop (paper stop + side
            x h); every SEND has its SIZE; AGG, the COST of each market that fed bars, and DAY come as one set per server
            day; every start that ran live has its PLAN and REBUILD; several breaks that point at one lost line count once,
            and a break that an unreadable line of the same event may explain is left to that line. Lines after a stop with
            no new INIT line are a start whose INIT line is lost; a start followed by another with no stop line between
            ended without OnDeinit; a start whose REBUILD line is lost is live from its INIT line + 5 minutes. A file name
            that is not <yyyymmdd>.log (a second copy the Mac made) is skipped and named; a file whose last line has no line
            end was cut while the robot wrote (that line is unreadable); time fields outside 2015-2100 make a line
            unreadable; a live line repeated word for word is a file read twice. A journal without INIT whose oldest file is
            30 days older than its newest lost its first files to the robot's own purge (CR_JRN_KEEP_DAYS).
--printed   the Experts tab's lines (copied text, or MetaTrader's own MQL5/Logs/<yyyymmdd>.log, UTF-16 accepted):
            the same CR| lines after a terminal prefix, live lines only (rp=1 is never printed, SPEC 2.6). Other lines
            are never kept; they are only scanned for an account login or server name, which is then masked.
--bars      ReleveFP's files: m1_<BASE>.csv (ReleveFP.mq5 Minutes/Row: time,bo,bh,bl,bc,ao,ah,al,ac,n,sp_mean,
            sp_max and, from ReleveFP 1.10, sp_min; time = server seconds; bid and ask O/H/L/C of the ticks of the
            minute; spreads in price units) and, from ReleveFP 1.10, r1_<BASE>.csv (Rates/RateRow: the terminal's own
            M1 bars, what the robot reads with CopyRates: time,open,high,low,close,tick_volume,spread,real_volume, bid
            prices, MqlRates.spread in points), optionally with fiches.csv and fini.txt beside them. Files of ReleveFP
            1.00 (no sp_min, no r1) are read too.

What it does:
 (a) the journal: builds and inputs of every INIT line (CR_BUILD must be fd6aaf01e332 or a later build of the git
     history of dist/; an older, unknown, debug or harness build is flagged), SELFTEST, PLAN, REBUILD, READY and
     NOTREADY with their durations after each start, restarts and their reasons, every ERROR, DUP, SLFIX, REFUSED,
     MISSED (with its reason; late, notready and exited within 15 min of a start or of a rebuild after a reconnection
     are a start's case), COST, LATEBAR, GUARD, STOP, MARK, WATCH line (and ORPHAN, CLOCK, GAP, SETTLE, TAKEOVER,
     LOCK, ADOPT), and per sleeve the counts of DEC, PFILL, PEXIT, SIZE, SEND, FILL, CLOSE (live and replayed). The live
     period runs from the first start (INIT) or rebuild, not from a decision stamped earlier (a D4H DEC is stamped at
     its bar's decision time). The checks of missing lines and of the journal's end are described above.
 (b) fills: each real position (FILL, or ADOPT after a restart) against its paper trade (PFILL, PEXIT/PREVISE of the
     same oid): entry and exit price differences in points, bp and EUR at the real lots (EUR per point from the FILL
     line's own risk: risk = (side x (fill - sl) + 2h) / tick size x tick value x lots, CR_Broker.mqh BrkRiskMoney);
     the exits: an EA close (a CLOSE line with ok=1, rc 10009 or 10010 and a price), or a broker stop, which the
     journal does not write (no line: its price and slippage are unknown). A CLOSE with ok=1 but rc 0 and px 0 is the
     race where the broker's stop closed the position just before the robot's request (CR_Broker.mqh BrkClose: CTrade
     clears its result): a broker stop too. With --bars the releve's minutes must reach the broker stop (the FILL sl,
     then each SLMOD) for every such exit (bid low for a long, ask high for a short), else it is an anomaly ('stop
     jamais touche') and the exit is unknown. Exits at the broker's stop stay out of the exit averages, the euros and
     the headline; they are counted apart with an estimate at stop x (1 -/+ the lab's stop slippage), what the paper
     books for its own stop exit, and their real slippage is in the balance difference only. A position whose paper
     trade ended otherwise (time, target, rule, eod ...) and has no successful CLOSE was either not closed by the robot
     or stopped by the broker before the paper's exit: with --bars, the releve's minutes say which; else, or when they
     did not cross, it is an anomaly. Its exit is then unknown and it is left out of the money totals; so is a CLOSE
     refused (ok=0) never followed by a success. An oid with two real tickets (FILL or ADOPT) is an anomaly; so is a
     position with no exit line whose paper exit time has passed while the journal goes on (lines missing).
     A race whose stop no minutes can check is an unknown exit; a position not closed at the paper's exit whose minutes
     cross its stop later (up to the journal's next line about it) was closed by the broker's stop after the paper's exit.
     The robot's closes for another reason than the paper's exit (orphan, prev, refused, the guards ...) or more than 10 min
     after it are shown apart, out of the exit averages. The money estimate (DAY balances against the gross results) is
     incomplete when the journal's start or end is missing, when a position closes in it without its opening, or when an
     adopted position's entry is outside it; the headline says the euros in words ('le reel a fait X EUR de moins que le
     papier', with the late-by-design part) and gives the balance-based costs.
     Points are given per sleeve and per market only (their sizes differ); totals are in bp and EUR. The total entry
     average holds the entries on time only: a stop, limit or OCO order is sent one bar after the paper's fill by
     design (SIZE late=1), and those entries are shown apart. On gold the paper's prices hold the commission (h = 3
     points a side, SPEC 2.2), so the differences are also given commission included (the measured COST rate, else
     the model); the broker's own slippage against the quote the request went with (SEND bid / ask); per sleeve and
     in total, and the share of intents (live SIZE lines) that became real trades. The journal holds no deal line
     (CR_Ledger.mqh reads DEAL_COMMISSION and DEAL_SWAP but writes neither): per-trade commission and swap are
     UNKNOWN; the gold commission of each server day comes from the COST lines (comm_usd_oz, against the robot's 0.06
     USD per oz); the DAY lines' balances give an estimate of costs not in the prices (commission + swap + stop
     slippage) against the gross result.
 (c) replay (with --bars): each market's bars become the harness's bar files (check/mock_replay.h rp_load_bars and
     check/export_frames.py: b"CRB1", int32 digits, int64 n, n x <int64 server time, int32 bid O/H/L/C in points,
     int32 spread in points>; the robot's paper ask = bid + spread x point + h on all four prices, CR_Bars.mqh
     BarsMakeAt, so the spread is the bar's MqlRates.spread). From r1_<BASE>.csv (ReleveFP 1.10) the bars are the
     terminal's own: prices converted to integer points exactly, spread = MqlRates.spread, no calibration. From
     m1_<BASE>.csv the column that gives MqlRates.spread is measured (SPEC 10.3, the moderator says the bar's
     minimum): --spread auto matches every paper line's s_raw against the open, close, rounded mean, max, min2 and,
     with ReleveFP 1.10, min (sp_min) conventions, and the COST lines; when no column gives 90 % of the bars, the
     sleeves of those markets are not compared (with no r1 file at all the replay is not run and the verdict says it
     cannot be used), instead of hundreds of differences; each market is judged on its own paper lines (review3 R15).
     The report says which file each market's bars came from. fini.txt beside the files says whether an r1 file is cut,
     not copied, older than the run (barres=-1) or read with errors; r1 bars that end before the m1 minutes ask to run
     ReleveFP again; a bad row of a releve file is dropped and counted, an unreadable file is an anomaly.
     All bars are passed (the robot masks them itself). dist/ClaudeRobot.mq5 is built with the harness
     (check/build.py, name demo_check_release, CR_XAU_COMM_PTS from the INIT line, 6 in the release; the dist file is
     read, never regenerated) and replays the span as an observer (InpTrade false, SPEC 10.2 and 10.12) with the
     inputs of the INIT line (risk table, sleeves, the three switches as resolved, the K1 table), the plan start and
     B(T) of the PLAN line (InpPlanStart, MOCK_BALANCE), and --input for what INIT does not show (InpExtraClosures
     ...). Then the live lines of SPEC 10.12 step 3 (DEC, PFILL, PEXIT, PSTOP, PREVISE, PVOID, PREFUSE, HOLD, SIZE,
     MISSED) are compared line for line, matched by key (event, sleeve, oid, bar or time), every field equal (doubles
     built on rolling or Wilder values within 1e-12 relative, SPEC 7). Every difference is listed with its first line
     on each side. Choice for SIZE (it depends on the real account): the replay is NOT given the account's deal
     history, because the journal does not hold it (no deal line, no broker stop fill, no commission or swap), so
     MOCK_DEALS could only be guessed; SIZE is compared on what does not depend on the account or on the tick of the
     request: stamp, sleeve, oid, side, entry type, late flag and stake factor; when the live copy is an observer (no
     FILL), the balance never moved for the robot, so B, P_in, rate, m, w and the week unit are compared too (the
     replay starts from the PLAN line's B(T)); the skip reason is compared when both copies observe and the replay's
     symbol was READY. lots, want, r, budget and quote are never compared (account and tick). MISSED is compared for
     reason=exited (P5, account-independent); the other reasons come from the real account and are listed apart.
     Lines are compared only where both sides can hold them: inside each sleeve's own span (from the latest first
     minute to the earliest last minute among the markets it reads, READS_OF_CODE: a market whose minutes start late
     delays only its sleeves, and the short file is named) after the sleeve's warm-up (WARMUP_DAYS below: the
     look-backs of the rule files, and about 400 bars for a Wilder ATR to meet 1e-12) and after the first moment both
     paper chains are flat together (a trade held over the replay's start would block the next one on one side only),
     every line of one paper trade in or out together (by its oid's decision time), while the live copy was running
     live (from a REBUILD to its INIT deinit) with the same paper inputs, outside the hours of a missing daily file.
     From the last live line before a REBUILD why=reconnect or why=latebar to its 'to', the robot was not live: there the
     rp=1 lines of that rebuild stand for the live lines it could not write (review3 R3-1).
     A line only the replay has is also judged by when the replay wrote it (the clock of the lines before it): a
     decision stamped before the robot's stop but written after it (D4H's DEC stamped 17:59 UTC is written at the
     next server midnight, a Friday decision on Monday) or inside a missing file's hours is not a difference.
     Each sleeve's coverage ("compare du ... au ..." or "jamais") is printed. With ReleveFP's default InpDays=30 and
     no r1 file, a two-week demo at the end of it: BKB, BKE (5-day warm-up) and ORX (3 days) are compared over most
     of the demo, N30 and NQB (25 days) over its last days only, OC4 (35), F1B, F1E, GFP (30) and D4H (120) never;
     ReleveFP 1.10's r1 files (InpRateDays=200) or InpDays=150 compare every sleeve over the whole demo, and the tool
     asks for them when a sleeve is left out; minutes that end before the demo ask to run ReleveFP after it. The AGG
     and COST lines of both sides are set side by side (bars fed per server day and symbol, each market only on the
     days its bars cover whole; median spreads), which shows whether ReleveFP's bars are the broker's; a day that
     differs is an anomaly.
 (d) --printed: the printed lines against the files' live lines: the same copy (the Mac's) must print every live line
     of its files between its first and last printed line, in the files' order (write order, not stamps: a
     Friday-close DEC stamped Saturday is written on Monday); another copy (the VPS's, INIT vps=1) is compared on
     SPEC 10.12's lines as above (shadow weeks). A --printed file with no robot line at all (the terminal's Journal
     tab, say) is named as an anomaly.
 MISSED: the reasons that come from the account (refused, prev_open, market_shut ...) are anomalies; 'exited' and
     'notrade' never are; 'late', 'notready' and 'exited' within 15 min of a start (a paper trade already open, SPEC
     4.8 d) are not; 'observe' is not when its stamp is before the PLAN line's start T (InpPlanStart set to the
     go-live time, SPEC 1 step 3) or the plan is not in force yet. A PLAN state 'unset' (no entry on a real account)
     is an anomaly.
Output in --out (default: the session scratchpad; a folder inside the repository is refused): report.json,
report_fr.txt, the converted bars and the replay's journal under replay/; a French summary on stdout. When nothing
is abnormal the verdict is "Rien d'anormal." only if the replay compared every sleeve over the whole demo; otherwise
it reads "Rien d'anormal sur ce qui a pu etre compare (N sleeves non comparees : ...)".
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
WARMUP_DAYS = C.WARMUP_DAYS
REL_TOL = 1e-12
NEAR_S = 1800                                   # a live disturbance within 30 min of a line explains it
SIZE_ACCOUNT = ["B", "P_in", "rate", "m", "unit", "w"]
SIZE_FREE = ["side", "et", "late", "f"]
SIZE_NEVER = ["lots", "want", "r", "budget", "quote"]
DEINIT_FR = {0: "arret par le programme", 1: "robot retire du graphique", 2: "recompile", 3: "symbole ou periode du graphique change",
             4: "graphique ferme", 5: "parametres changes", 6: "autre compte", 7: "modele applique", 8: "OnInit en echec",
             9: "terminal ferme"}
REC = np.dtype([("t", "<i8"), ("o", "<i4"), ("h", "<i4"), ("l", "<i4"), ("c", "<i4"), ("s", "<i4")])
SPREAD_CONV = ["open", "close", "mean", "max", "min2", "min"]      # min: ReleveFP 1.10's sp_min (absent from 1.00 files)
CONV_MATCH = 0.99                                # below this share of the paper bars, the report warns that some bars differ
CONV_USABLE = 0.9                                # below this, no column gives the bar spread: the m1 replay cannot be used
REPLAY_NAME = "demo_check_release"
JRN_KEEP_DAYS = 30                              # CR_Journal.mqh CR_JRN_KEEP_DAYS: the release robot deletes older daily files
# lines OnInit may write before its INIT line: the guards' clock check (GrdSelfTest), an input refused (ERROR), a lock taken
# over (TAKEOVER), a change on a real account (INIT change=, ChangeOn); they belong to the start that follows (review2 N8 b)
ONINIT_EV = ("CLOCK", "ERROR", "TAKEOVER")
# events stamped when they are written (Jrn: the server clock now); DEC, the paper lines and SIZE are stamped at their own
# lab time, which can be days earlier (a Friday-close decision written on Monday), and STOP or GUARD of the history too
NOW_STAMPED = {"INIT", "SELFTEST", "PLAN", "REBUILD", "READY", "NOTREADY", "SEND", "FILL", "CLOSE", "SLMOD", "SLFIX", "REFUSED",
               "ADOPT", "ORPHAN", "DUP", "MISSED", "LATEBAR", "GAP", "SETTLE", "CLOCK", "MARK", "LOCK", "TAKEOVER", "WATCH", "ERROR",
               "AGG", "COST", "DAY"}


# ---------------------------------------------------------------------------------------------- (a) the journal
def _oninit(r):
    return r["ev"] in ONINIT_EV or (r["ev"] == "INIT" and "change" in r)


LIVE_AFTER_INIT_S = 300                         # no REBUILD line in a start (lost): live from its INIT line + 5 minutes


def starts_of(rows):
    """the starts (INIT with build=), each with its stop (INIT deinit=), its REBUILD lines and its live span. Lines OnInit
    writes before the INIT line (ONINIT_EV, written within 2 minutes of it) belong to that start, not to a start of
    their own (review2 N8 b). Lines after a stop (INIT deinit) with no new INIT build= line before them are a start whose
    INIT line is lost (review3 R3-6: 'init_lost'); a start followed by another INIT build= with no stop line between
    ended without OnDeinit: terminal closed abruptly, Mac switched off, or the stop line lost ('no_deinit'). A start with
    no REBUILD line (lost) is live from its INIT line + LIVE_AFTER_INIT_S."""
    out, cur = [], None
    last_live = None
    pending = []                                                  # OnInit lines waiting for their INIT line

    def new_start(r, init):
        s = {"utc": r["utc"], "init": init, "rebuilds": [], "selftest": None, "plan": None, "last_live": None,
             "ready": {}, "notready": defaultdict(list)}
        if init is None:
            s["no_init"] = True
        return s

    def flush_pending(into_index):
        for p in pending:
            p["_si"] = into_index
        pending.clear()

    def close(s, at):
        s["end"] = s.get("deinit_utc") or s.get("last_live") or at
        if s.get("deinit") is None and s.get("init") is not None:
            s["no_deinit"] = True                                 # another start follows with no stop line between
        out.append(s)
    for r in rows:
        if r["ev"] == "INIT" and "build" in r:
            if pending and pending[0]["utc"] < r["utc"] - 120:     # older lines: a start whose INIT line is lost
                if cur is not None:
                    close(cur, pending[0]["utc"])
                cur = new_start(pending[0], None)
                flush_pending(len(out))
            if cur is not None:
                close(cur, r["utc"])
            cur = new_start(r, r)
            r["_si"] = len(out)
            flush_pending(len(out))
            continue
        if (cur is None or cur.get("deinit")) and _oninit(r) and r.get("rp") != 1:
            pending.append(r)
            continue
        if cur is not None and cur.get("deinit") and r.get("rp") != 1:
            # a line after the stop that is not an OnInit line: a new start whose INIT line is lost (review3 R3-6)
            out.append(dict(cur, end=cur.get("deinit_utc") or cur.get("last_live") or r["utc"]))
            cur = new_start(pending[0] if pending else r, None)
            cur["init_lost"] = True
        if cur is None:
            cur = new_start(pending[0] if pending else r, None)
        if pending:
            flush_pending(len(out))
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
    if pending:                                                   # OnInit lines with no INIT after them (OnInit failed)
        if cur is None:
            cur = new_start(pending[0], None)
        last_live = max(last_live or 0, pending[-1]["utc"])
        flush_pending(len(out))
    if cur is not None:
        cur["end"] = cur.get("deinit_utc") or cur.get("last_live") or last_live
        out.append(cur)
    for k, s in enumerate(out):
        s["live_from"] = int(s["rebuilds"][0]["to"]) if s["rebuilds"] else None
        if s["init"] is None and s["live_from"] is None:          # files cut after the start: live from their first line
            first = [r["utc"] for r in rows if r.get("_si") == k and r.get("rp") != 1]
            s["live_from"] = min(first) - 1 if first else None
        elif s["live_from"] is None and any(r.get("_si") == k and r.get("rp") != 1 and r["ev"] in COMPARE_EV for r in rows):
            s["live_from"] = int(s["utc"]) + LIVE_AFTER_INIT_S   # it ran live but its REBUILD line is lost (review3 R3-6)
            s["no_rebuild"] = True
    return out


def paper_inputs(init):
    """the inputs that change the paper chain (switches, K1 table, gold commission) and the sizing (risk, sleeves)"""
    if not init:
        return None
    return {"K1": init.get("K1"), "H2": init.get("H2"), "S0.75r": init.get("S0.75r"), "k1t": init.get("k1t", ""),
            "comm_pts": init.get("comm_pts")}


def day_gaps(rows, files, unreadable=None, skipped=None):
    """server days whose DAY line is missing. CR_Main.mqh MainDaily writes one DAY line per server day the robot runs live
    (weekends included), at the first minute of a later day, into that day's file; a rebuild's replay writes none but
    leaves the day counter on the rebuild's day, so after a REBUILD line at server day R the next DAY line is DAY(R). A
    start or a stop (INIT) breaks the chain until the next REBUILD. Any other jump in the DAY days means lost lines:
    DAY(x) goes to the file of day x + 1, so the absent files among those days are named; only the days between the
    first and the last file present are looked at, never an open range (review3 R3-3). A day whose DAY line is in the
    unreadable lines (a DAY line edited or cut, review3 U2) is not a missing day: it is named apart ('illegible').
    skipped = the files skipped by the reader: a missing file whose name is there was replaced by another file (a
    MetaTrader log under the robot's name). Returns (gaps, ranges): ranges = UTC intervals whose lines are missing (left
    out of the replay comparison)."""
    lv = C.live(rows)
    present = {C.day_of_file(f) for f in (files or [])} - {None}
    lo, hi = (min(present), max(present)) if present else (None, None)
    bad_day_files = {u["file"] for u in (unreadable or []) if u.get("ev") == "DAY"}
    skipped_names = {s["file"] for s in (skipped or [])}
    prev, gaps, ranges = None, [], []
    for r in lv:
        ev, u = r["ev"], int(r["utc"])
        if ev == "INIT":
            prev = None                                     # a start or a stop: the next REBUILD sets the chain again
            continue
        if ev == "REBUILD":
            s_day = C.utc_to_srv(u)
            prev = (s_day - s_day % 86400 - 86400, u)       # as if DAY(R - 1) had just been written
            continue
        if ev != "DAY" or not isinstance(r.get("day"), int):
            continue
        d = int(r["day"])
        f_day = C.day_of_file(r.get("_f") or "")
        if f_day is not None and d >= f_day:
            continue                                        # DAY(x) is written on a later day: this one cannot be the robot's
        if prev is not None and d - prev[0] > 86400:
            a, z = prev[0] + 86400, d - 86400               # the days without a DAY line
            if lo is not None:
                a, z = max(a, lo - 86400), min(z, hi - 86400)   # never beyond the files present
            days = list(range(a, z + 1, 86400)) if z >= a else []
            illegible = [x for x in days if C.file_of_day(x + 86400) in bad_day_files]
            lost = [x for x in days if x not in illegible]
            missing = [x + 86400 for x in lost if x + 86400 not in present]
            if lost:
                gaps.append({"first_day": C.ymd(lost[0]), "last_day": C.ymd(lost[-1]), "days": len(lost), "explained": False,
                             "missing_files": [C.file_of_day(x) for x in missing],
                             "replaced_files": [C.file_of_day(x) for x in missing if C.file_of_day(x) in skipped_names],
                             "illegible_days": [C.ymd(x) for x in illegible]})
                if missing:
                    for x in missing:
                        ranges.append((C.srv_to_utc(x) - 600, C.srv_to_utc(x + 86400) + 600))
                else:
                    ranges.append((prev[1], u))
            elif illegible:
                gaps.append({"first_day": C.ymd(illegible[0]), "last_day": C.ymd(illegible[-1]), "days": 0, "explained": True,
                             "missing_files": [], "replaced_files": [], "illegible_days": [C.ymd(x) for x in illegible]})
        if prev is None or d > prev[0]:
            prev = (d, u)
    return gaps, ranges


def days_txt(g):
    return f"le {g['first_day']}" if g["first_day"] == g["last_day"] else f"du {g['first_day']} au {g['last_day']}"


INF_T = 1 << 62
MARK_MAGIC = 20261290                           # the guard's mark trade (CR_Types.mqh CR_MAGIC_MARK)
# CLOSE reasons that may close a position the robot does not follow (no FILL or ADOPT for its ticket in this run):
# ORPHAN, DUP, the guard's mark, NOT_READY exits by LatestExit, a missed Friday close, the guards' closes, SLFIX of an
# unfollowed position (CR_Follower.mqh FolMapPositions, FolRecSleeve, FolNotReadyExits, FolSlfix; CR_Guards.mqh)
UNFOLLOWED_CLOSE = {"orphan", "dup", "mark", "latest_exit", "friday_missed", "stop", "guard", "lock", "friday", "clock", "slfix"}
MISSING_FR = {"DEC": "DEC (ordre)", "PFILL": "PFILL", "FILL": "FILL", "SEND": "SEND", "FILL/ADOPT": "FILL ou ADOPT", "PEXIT": "PEXIT",
              "SIZE": "SIZE", "SLMOD": "SLMOD (deplacement du stop)", "DAY": "DAY", "AGG": "AGG", "COST": "COST", "PLAN": "PLAN",
              "REBUILD": "REBUILD"}


def overlaps(a, z, ranges):
    return any(x0 <= z and a <= x1 for x0, x1 in ranges)


def fed_evidence(lv):
    """for each market, the latest bar a live paper line names and the server days whose AGG line fed bars of it: the
    journal goes on past a time when it holds such a line"""
    last_bar = defaultdict(int)
    agg_days = defaultdict(list)
    for r in lv:
        if r["ev"] in PAPER_EV and isinstance(r.get("bar"), int) and C.SYM_OF_CODE.get(r["code"]):
            b = C.SYM_OF_CODE[r["code"]]
            last_bar[b] = max(last_bar[b], r["bar"])
        elif r["ev"] == "AGG" and isinstance(r.get("day"), int):
            for b in C.ROBOT_BASES:
                if isinstance(r.get(b), int) and r[b] > 0:
                    agg_days[b].append(r["day"])

    def fed_after(b, t):
        if last_bar[b] > t:
            return True
        d = C.utc_to_srv(int(t))
        return any(x > d - d % 86400 for x in agg_days[b])
    return fed_after


def open_minutes(b, utc_a, utc_z, cap=20 * 86400):
    """minutes of [utc_a, utc_z) when the robot keeps the market's bars (its own masks, CR_Bars.mqh BarsMaskReason: the
    market is open); a span longer than cap counts as long enough"""
    if utc_z - utc_a > cap:
        return cap // 60
    if utc_z <= utc_a or b not in C.FAMILY:
        return 0
    m = np.arange(int(utc_a) - int(utc_a) % 60, int(utc_z), 60, dtype=np.int64)
    srv_m = np.array([C.utc_to_srv(int(x)) for x in m], dtype=np.int64) if len(m) < 3000 else m + (C.utc_to_srv(int(m[0])) - int(m[0]))
    return int(mask_kept(srv_m, C.FAMILY[b]).sum())


def slmod_paths(rows, points, comm_pts=6):
    """per ticket the broker stops the journal shows (review3 R3-4): the FILL's sl, then every SLMOD. Returns
    {ticket: {"code", "side", "oid", "fill_sl", "chain": [(utc, from, to, ok, row)]}} for live FILL, ADOPT and SLMOD lines,
    and h per market (the gold paper's commission per side in price: the broker stop of a gold trade is the paper stop
    + side x h, CR_Follower.mqh FolExpectedStop)"""
    lv = C.live(rows)
    h = {b: (comm_pts * 0.5 * points.get(b, 0.01) if b == "XAUUSD" else 0.0) for b in C.ROBOT_BASES}
    out = {}
    for r in lv:
        t = r.get("ticket")
        if not t:
            continue
        if r["ev"] == "FILL":
            out.setdefault(t, {"code": r["code"], "side": r.get("side"), "oid": r.get("oid"), "fill_sl": r.get("sl"), "fill_utc": r["utc"],
                               "chain": []})
        elif r["ev"] == "ADOPT" and t not in out:
            out[t] = {"code": r["code"], "side": None, "oid": r.get("oid"), "fill_sl": None, "fill_utc": r.get("open"), "chain": []}
        elif r["ev"] == "SLMOD":
            e = out.setdefault(t, {"code": r["code"], "side": None, "oid": None, "fill_sl": None, "fill_utc": None, "chain": []})
            e["chain"].append((r["utc"], r.get("from"), r.get("to"), r.get("ok"), r))
    return out, h


def journal_breaks(rows, ranges, starts=None, points=None, comm_pts=6, unreadable=None):
    """lines the robot always writes in pairs, one of which is absent (review2 N1, review3 R3-4, R3-5), read from the
    journal alone:
      - every live PFILL and SIZE has the DEC what=ord line of its order (oid; live or rp=1: a rebuild writes them again);
      - every live PEXIT, PREVISE, PSTOP and HOLD has the PFILL of its trade (live or rp=1);
      - every SEND result=filled has its FILL and every FILL its SEND (CR_Broker.mqh BrkOpen writes both in one call);
        every SEND has the SIZE of its intent (live or rp=1);
      - every CLOSE and SLMOD names a ticket of a FILL or an ADOPT (or of a DUP, ORPHAN, SLFIX, WATCH or REFUSED line),
        except a close that may target an unfollowed position (UNFOLLOWED_CLOSE) or the guard's mark;
      - every SLMOD starts from the position's stop as the journal last showed it: the FILL's sl, or the 'to' of the
        ticket's previous SLMOD (half a point of tolerance); and a position that the broker's stop closed carried, at the
        paper's stop exit, the stop the robot sets (the paper's stop + side x h, FolExpectedStop) when the paper's stop got
        there at least 15 open minutes before and nothing stopped the robot meanwhile (NOTREADY, CLOCK, STOP, LOCK, GUARD,
        a restart or a reconnection);
      - MainDaily writes AGG, the COST of each market that fed bars, and DAY together: one set per server day;
      - every start that ran live has its PLAN and its REBUILD line;
      - every paper trade ends (PEXIT, PREVISE or PVOID) before the next PFILL of its sleeve (one trade at a time per
        sleeve, CR_Paper.mqh), or once its scheduled exit (or HOLD's) has passed while the journal goes on for its market.
        A rebuild's replay (rp=1 lines) starts the chain again from scratch.
    A break whose missing line could lie in a known hole (ranges: a missing daily file, the time before the first file
    when it has no INIT line, the days after a missing last file) is not reported (that hole is, once); nor is one whose
    missing line may be an unreadable line of the same event in a file of that time (unreadable: the reader's list with
    the event of each line; that line is reported as unreadable, review3 U2). Each break names the line it points at
    ('key'): several breaks pointing at one lost line count once (review3 R3-5)."""
    lv = C.live(rows)
    points = points or {b: 0.01 for b in C.ROBOT_BASES}
    bad_files = defaultdict(set)                                  # event -> files holding an unreadable line of it
    for u in unreadable or []:
        if u.get("ev"):
            bad_files[u["ev"]].add(u["file"])
    alias = {"FILL/ADOPT": ("FILL", "ADOPT")}

    def unreadable_there(missing, r, a, z):
        evs = alias.get(missing, (missing,))
        files = {r.get("_f")}
        if z - a < 40 * 86400:
            s0, s1 = C.utc_to_srv(max(int(a), C.TIME_MIN)), C.utc_to_srv(min(int(z), C.TIME_MAX - 1))
            files |= {C.file_of_day(d) for d in range(s0 - s0 % 86400, s1 + 86400, 86400)}
        return any(bad_files[e] & files for e in evs)
    dec = {(r["code"], r.get("oid")) for r in rows if r["ev"] == "DEC" and r.get("what") == "ord"}
    pfill = {(r["code"], r.get("oid")) for r in rows if r["ev"] == "PFILL"}
    size = {(r["code"], r.get("oid")) for r in rows if r["ev"] == "SIZE"}
    fill = {(r["code"], r.get("oid")) for r in lv if r["ev"] == "FILL"}
    send_filled = {(r["code"], r.get("oid")) for r in lv if r["ev"] == "SEND" and r.get("result") == "filled"}
    tickets = {r.get("ticket") for r in lv if r["ev"] in ("FILL", "ADOPT", "DUP", "ORPHAN", "SLFIX", "WATCH", "REFUSED")
               and r.get("ticket")}
    out = []

    def add(r, missing, a, z, what, key=None):
        if overlaps(a, z, ranges) or unreadable_there(missing, r, a, z):
            return
        out.append({"missing": missing, "event": r["ev"], "code": r["code"], "oid": r.get("oid"), "ticket": r.get("ticket"),
                    "utc": r["utc"], "when": C.utc_txt(r["utc"]), "file": r.get("_f"), "line": r.get("_n"), "text_fr": what,
                    "key": key or (missing, r["code"], r.get("oid") if r.get("oid") is not None else r.get("ticket"))})

    def dec_t(r):
        o = r.get("oid")
        return int(o) // 100 if isinstance(o, int) and o > 0 else r["utc"]
    last_pfill = {}                                               # sleeve -> decision time of its latest PFILL (file order)
    send_wo_fill = defaultdict(list)                              # sleeve -> SEND rows without their FILL (a lost FILL)
    for r in rows:
        ev, code = r["ev"], r["code"]
        if ev == "PFILL":
            last_pfill[code] = dec_t(r)
        if r.get("rp") == 1:
            continue
        k = (code, r.get("oid"))
        if ev in ("PFILL", "SIZE") and k not in dec:
            add(r, "DEC", dec_t(r) - 60, r["utc"] + 600, f"{ev} {code} oid {r.get('oid')} ({C.utc_txt(r['utc'])}) sans la ligne DEC de son ordre")
        if ev in ("PEXIT", "PREVISE", "PSTOP", "HOLD") and k not in pfill:
            add(r, "PFILL", dec_t(r) - 60, r["utc"] + 600, f"{ev} {code} oid {r.get('oid')} ({C.utc_txt(r['utc'])}) sans le PFILL de son trade")
        if ev == "SEND" and k not in size:
            add(r, "SIZE", dec_t(r) - 60, r["utc"] + 60, f"SEND {code} oid {r.get('oid')} ({C.utc_txt(r['utc'])}) sans la ligne SIZE de son intention")
        if ev == "SEND" and r.get("result") == "filled" and k not in fill:
            n0 = len(out)
            add(r, "FILL", r["utc"] - 60, r["utc"] + 600, f"SEND rempli {code} oid {r.get('oid')} ({C.utc_txt(r['utc'])}) sans sa ligne FILL")
            if len(out) > n0:
                send_wo_fill[code].append(out[-1])
        if ev == "FILL" and k not in send_filled:
            add(r, "SEND", r["utc"] - 600, r["utc"] + 60, f"FILL {code} ticket {r.get('ticket')} ({C.utc_txt(r['utc'])}) sans sa ligne SEND")
        if ev in ("CLOSE", "SLMOD") and r.get("ticket") not in tickets:
            if ev == "CLOSE" and (code == "MARK" or r.get("magic") == MARK_MAGIC or r.get("why") in UNFOLLOWED_CLOSE):
                continue
            # the lost line is the ticket's FILL: when the same sleeve has a filled SEND without its FILL before, that one
            prior = [b for b in send_wo_fill.get(code, []) if b["utc"] <= r["utc"]]
            key = prior[-1]["key"] if prior else ("FILL/ADOPT", code, r.get("ticket"))
            add(r, "FILL/ADOPT", last_pfill.get(code, -INF_T) - 600, r["utc"] + 60,
                f"{ev} {code} ticket {r.get('ticket')} ({C.utc_txt(r['utc'])}) sans FILL ni ADOPT de ce ticket", key)
    # the broker stops (review3 R3-4): each SLMOD starts from the stop the journal last showed
    paths, h = slmod_paths(rows, points, comm_pts)
    for t, p in paths.items():
        b = C.SYM_OF_CODE.get(p["code"])
        tol = 0.5 * points.get(b, 0.01)
        cur, tried = p["fill_sl"], []
        for (u, frm, to, ok, r) in p["chain"]:
            if not isinstance(frm, (int, float)):
                continue
            # from = 0: the position had no stop at that time (removed by hand or by the broker): the robot puts one back;
            # that is no lost line (SLFIX and the invariant say the rest)
            if isinstance(cur, (int, float)) and cur > 0 and frm > 0 and abs(frm - cur) > tol + 1e-9 * abs(cur) \
                    and not any(abs(frm - x) <= tol + 1e-9 * abs(x) for x in tried):
                add(r, "SLMOD", (paths[t].get("fill_utc") or u) - 60, u + 60,
                    f"SLMOD {p['code']} ticket {t} ({C.utc_txt(u)}) part de {C.fr(frm, 5)} alors que le dernier stop du journal est "
                    f"{C.fr(cur, 5)} : deplacement(s) du stop absent(s) du journal (ligne perdue, ou stop change a la main)",
                    ("SLMOD", t, round(float(cur), 8), round(float(frm), 8)))
                cur = frm
            if ok == 1:
                cur, tried = to, []
            elif "why" not in r and isinstance(to, (int, float)):
                tried.append(to)                                  # a refused move: the next one may start from it
            if cur is None:
                cur = frm
    # the stop at a broker-stop exit: the stop the robot sets for the paper's last stop
    pex = {}
    for r in lv:                                                  # the live exits (a later rebuild writes them again as rp=1)
        if r["ev"] in ("PEXIT", "PREVISE"):
            pex[(r["code"], r.get("oid"))] = r
    pstops = defaultdict(list)
    for r in lv:
        if r["ev"] in ("PFILL", "PSTOP"):
            pstops[(r["code"], r.get("oid"))].append(r)
    closed_ok = {r.get("ticket") for r in lv if r["ev"] == "CLOSE" and r.get("ok") == 1}
    halts = [(r["utc"], r["code"]) for r in rows if (r.get("rp") != 1 and (r["ev"] in ("NOTREADY", "STOP", "LOCK", "GUARD", "INIT", "REBUILD")
                                                                         or (r["ev"] == "CLOCK" and r.get("state") in ("wrong", "flat"))))]
    for t, p in paths.items():
        b = C.SYM_OF_CODE.get(p["code"])
        x = pex.get((p["code"], p["oid"]))
        side = p["side"]
        if b is None or x is None or t in closed_ok or x.get("reason") not in STOP_REASONS or not side or x.get("rp") == 1:
            continue
        want = x.get("stop", 0) + side * h.get(b, 0.0)
        cur = p["fill_sl"]
        moves = [c for c in p["chain"] if c[0] <= x["utc"]]
        for (u, frm, to, ok, r) in moves:
            if ok == 1:
                cur = to
        if not isinstance(cur, (int, float)) or abs(cur - want) <= 1.01 * points.get(b, 0.01) + 1e-9 * abs(want):
            continue
        if any(isinstance(c[2], (int, float)) and abs(c[2] - want) <= 1.01 * points.get(b, 0.01) + 1e-9 * abs(want) for c in p["chain"]):
            continue                                              # the move to that stop is in the journal (refused, retried)
        t_set = None                                              # when the paper's stop got to its last level (written a bar later)
        for s in pstops.get((p["code"], p["oid"]), []):
            if s["utc"] > x["utc"]:
                break
            if abs((s.get("stop") or 0) - x.get("stop", 0)) > 1e-9 * abs(x.get("stop", 0)) + 1e-12:
                t_set = None
            elif t_set is None:
                t_set = s["utc"] + 60
        if t_set is None or open_minutes(b, t_set, x["utc"]) < 15:
            continue
        if any(t_set <= u <= x["utc"] and (cd in ("-", "MARK") or cd == b or cd == p["code"]) for u, cd in halts):
            continue
        add(x, "SLMOD", t_set - 60, x["utc"] + 60,
            f"position {p['code']} ticket {t} fermee au stop du papier ({C.fr(x.get('stop'), 5)}, {C.utc_txt(x['utc'])}) alors que le dernier "
            f"stop courtier du journal est {C.fr(cur, 5)} (le robot le met a {C.fr(want, 5)}) : deplacement(s) du stop perdu(s)",
            ("SLMOD", t, "end"))
    # the daily lines: AGG, COST of each market that fed bars, DAY (CR_Main.mqh MainDaily)
    agg = {r.get("day"): r for r in lv if r["ev"] == "AGG"}
    day = {r.get("day"): r for r in lv if r["ev"] == "DAY"}
    cost = {(r["code"], r.get("day")) for r in lv if r["ev"] == "COST"}
    for d, r in agg.items():
        if d not in day:
            add(r, "DAY", r["utc"] - 60, r["utc"] + 60, f"AGG du {C.ymd(d)} sans la ligne DAY du meme jour", ("DAY", "-", d))
        for b_ in C.ROBOT_BASES:
            if isinstance(r.get(b_), int) and r[b_] > 0 and (b_, d) not in cost:
                add(r, "COST", r["utc"] - 60, r["utc"] + 60, f"AGG du {C.ymd(d)} : {r[b_]} barre(s) de {b_} sans sa ligne COST",
                    ("COST", b_, d))
    for d, r in day.items():
        if d not in agg:
            add(r, "AGG", r["utc"] - 60, r["utc"] + 60, f"DAY du {C.ymd(d)} sans la ligne AGG du meme jour", ("AGG", "-", d))
    # every start that ran live has its PLAN and its REBUILD line
    for k, s in enumerate(starts or []):
        if s.get("init") is None:
            continue
        r0 = s["init"]
        if s.get("rebuilds") and s.get("plan") is None:
            add(r0, "PLAN", r0["utc"] - 60, s["rebuilds"][0]["utc"] + 60, f"demarrage du {C.utc_txt(r0['utc'])} sans sa ligne PLAN",
                ("PLAN", "-", k))
        if s.get("no_rebuild"):
            add(r0, "REBUILD", r0["utc"] - 60, r0["utc"] + 3600, f"demarrage du {C.utc_txt(r0['utc'])} sans sa ligne REBUILD alors qu'il a "
                "tourne en direct", ("REBUILD", "-", k))
    # every paper trade ends before the next one of its sleeve, or once its time exit has passed
    fed_after = fed_evidence(lv)
    hold_x = defaultdict(int)
    for r in rows:
        if r["ev"] == "HOLD" and isinstance(r.get("x"), int):
            hold_x[(r["code"], r.get("oid"))] = max(hold_x[(r["code"], r.get("oid"))], r["x"])
    open_, prev_rp = {}, False
    for r in rows:
        is_rp = r.get("rp") == 1
        if is_rp and not prev_rp:
            open_.clear()                                         # a rebuild's replay: the chain starts again
        prev_rp = is_rp
        ev, code = r["ev"], r["code"]
        if ev == "PFILL":
            o = open_.get(code)
            if o is not None and o.get("oid") != r.get("oid"):
                add(o, "PEXIT", o["utc"], r["utc"], f"PFILL {code} oid {o.get('oid')} ({C.utc_txt(o['utc'])}) sans sortie du papier avant le "
                                                     f"trade suivant ({C.utc_txt(r['utc'])})")
            open_[code] = r
        elif ev in ("PEXIT", "PREVISE", "PVOID"):
            o = open_.get(code)
            if o is not None and o.get("oid") == r.get("oid"):
                del open_[code]
    for code, o in open_.items():
        b = C.SYM_OF_CODE.get(code)
        x = max(o.get("x") if isinstance(o.get("x"), int) else 0, hold_x.get((code, o.get("oid")), 0))
        if b and x > 0 and fed_after(b, x + 3600):
            add(o, "PEXIT", o["utc"], x + 86400, f"PFILL {code} oid {o.get('oid')} ({C.utc_txt(o['utc'])}) sans sortie du papier alors que sa "
                                                 f"sortie prevue ({C.utc_txt(x)}) est passee et que le journal continue")
    out.sort(key=lambda b: (b["utc"], b["missing"]))
    return out


def missing_count(brk):
    """the lines missing, each counted once (several breaks may point at one lost line, review3 R3-5): {kind: n}"""
    seen, n = set(), Counter()
    for b in brk:
        k = tuple(b.get("key") or (b["missing"], b["code"], b.get("oid")))
        if k in seen:
            continue
        seen.add(k)
        n["FILL" if b["missing"] == "FILL/ADOPT" and k[0] == "FILL" else b["missing"]] += 1
    return n


def journal_end(rows, files, releve_end):
    """the end of the journal (review2 N5). The DAY chain cannot see a lost last file, so: a journal whose last live line
    is the robot's stop (INIT deinit) is complete; otherwise the robot was still running when the files were copied, or
    the last file is missing. ReleveFP's run (fini.txt server_time, fiches.csv tick times, the end of its minutes:
    releve_end, UTC) settles it when given: the robot writes a file every day it runs (weekends included), so the days
    from the newest file to the releve's day without a file are named."""
    lv = C.live(rows)
    if not lv:
        return {}
    last = lv[-1]
    days = sorted(d for d in (C.day_of_file(f) for f in files or []) if d is not None)
    res = {"last_line_utc": last["utc"], "last_line_when": C.utc_txt(last["utc"]), "stop_line_last": last["ev"] == "INIT" and "deinit" in last,
           "newest_file": C.file_of_day(days[-1]) if days else None, "releve_end_utc": releve_end,
           "releve_end_when": C.utc_txt(releve_end) if releve_end else None, "missing_files": [], "ranges": []}
    if res["stop_line_last"]:
        res["kind"] = "stopped"
        return res
    if releve_end is None or not days:
        res["kind"] = "no_stop_unknown"
        res["anomaly"] = ("fin du journal sans ligne d'arret du robot (INIT deinit) : robot encore en marche quand les fichiers ont ete "
                          "copies, ou dernier fichier manquant (donner aussi fini.txt de ReleveFP, ou --bars, pour le savoir)")
        return res
    s = C.utc_to_srv(int(releve_end)) - 3600                      # the robot's first lines of a day come at 00:00:30
    ref_day = s - s % 86400
    miss = [C.file_of_day(d) for d in range(days[-1] + 86400, ref_day + 1, 86400)]
    if miss:
        res["kind"] = "missing_tail"
        res["missing_files"] = miss
        res["ranges"] = [(C.srv_to_utc(days[-1] + 86400) - 600, INF_T)]
        more = f" (et {', '.join(miss[1:])} si le robot tournait encore ces jours-la)" if len(miss) > 1 else ""
        res["anomaly"] = (f"fin du journal le {res['last_line_when']} sans ligne d'arret alors que le releve de ReleveFP va jusqu'au "
                          f"{res['releve_end_when']} : fichier du jour manquant probable : {miss[0]}{more} (dernier fichier manquant, ou "
                          "robot arrete sans ligne d'arret : terminal ferme d'un coup, Mac eteint ; envoyer ces fichiers s'ils existent)")
    else:
        res["kind"] = "running"
        res["note"] = ("robot encore en marche quand les fichiers ont ete copies (pas de ligne d'arret a la fin ; le journal va jusqu'au "
                       "jour du releve de ReleveFP) : normal")
    return res


def live_period(rows):
    """the live period: from the first start (INIT) or rebuild (REBUILD) to the last live line (review2 N8 a); a journal
    with neither starts at its first line stamped when written (NOW_STAMPED), never at a decision stamped earlier"""
    lv = C.live(rows)
    if not lv:
        return None, None
    first = next((r["utc"] for r in lv if (r["ev"] == "INIT" and "build" in r) or r["ev"] == "REBUILD"), None)
    if first is None:
        first = next((r["utc"] for r in lv if r["ev"] in NOW_STAMPED), min(r["utc"] for r in lv))
    return first, max(r["utc"] for r in lv)


def analyse_journal(rows, builds, files=None, releve_end=None, info=None, points=None):
    lv = C.live(rows)
    info = info or {}
    starts = starts_of(rows)
    res = {"lines": len(rows), "live_lines": len(lv), "replayed_lines": len(rows) - len(lv)}
    if rows:
        res["first_utc"], res["last_utc"] = live_period(rows)
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
             "no_init_line": bool(s.get("no_init")), "init_lost": bool(s.get("init_lost")), "no_deinit": bool(s.get("no_deinit")),
             "no_rebuild": bool(s.get("no_rebuild"))}
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
        if s.get("init_lost"):
            anomalies.append(f"demarrage {k + 1} ({e['when']}) : des lignes du robot suivent son arret (INIT deinit) sans nouvelle ligne INIT : "
                             "ligne de demarrage perdue (fichier coupe ou modifie ?) ; build et reglages de ce demarrage inconnus")
        if s.get("no_deinit"):
            anomalies.append(f"demarrage {k + 1} ({e['when']}) : fini sans ligne d'arret (INIT deinit) avant le demarrage suivant : terminal "
                             "ferme d'un coup, Mac eteint, ou ligne perdue")
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
        days_ = sorted(d for d in (C.day_of_file(f) for f in files or []) if d is not None)
        if days_ and days_[-1] - days_[0] >= (JRN_KEEP_DAYS - 1) * 86400:
            res["purged"] = True                                    # CR_Journal.mqh JrnPurge (review3 R3-2)
            anomalies.append(f"aucune ligne INIT dans les fichiers : le plus ancien ({C.file_of_day(days_[0])}) a {(days_[-1] - days_[0]) // 86400} "
                             f"jours de moins que le plus recent : le robot efface lui-meme ses fichiers de plus de {JRN_KEEP_DAYS} jours, ceux "
                             "du demarrage n'existent plus (build, reglages et positions ouvertes avant sont inconnus) ; la prochaine fois, "
                             "copier les journaux avant 30 jours")
        else:
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
        """within 15 min after a start's first live minute, or after a rebuild that a reconnection or a late bar
        caused (the robot was not live while the paper went on, review3 R3-1)"""
        k = r.get("_si")
        if k is None or k >= len(starts) or starts[k].get("live_from") is None:
            return False
        if r["utc"] - starts[k]["live_from"] <= 900:
            return True
        return any(0 <= r["utc"] - int(b["to"]) <= 900 for b in starts[k]["rebuilds"][1:] if isinstance(b.get("to"), int))

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
        isnum = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)   # noqa: E731
        # every field was type-checked when read; a value that is still not a finite number never raises (review2 N7)
        e["over_model"] = bool(isnum(e["paper_bp"]) and isnum(e["model_bp"]) and e["model_bp"] > 0 and e["paper_bp"] > 1.5 * e["model_bp"])
        e["comm_off"] = bool(isnum(e["comm_usd_oz"]) and isinstance(e["comm_n"], int) and e["comm_n"] > 0 and abs(e["comm_usd_oz"] - 0.06) > 0.01)
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
    gaps, ranges = day_gaps(rows, files, info.get("unparsable_all"), info.get("skipped_files"))
    res["day_gaps"] = gaps
    res["missing_ranges_utc"] = ranges
    res["missing_files"] = sorted({f for g in gaps if not g["explained"] for f in g["missing_files"]})
    for g in gaps:
        if g.get("illegible_days"):
            res.setdefault("illegible_day_lines", []).extend(g["illegible_days"])
        if g["explained"]:
            continue
        rep_ = [f for f in g["missing_files"] if f in g.get("replaced_files", [])]
        lost = [f for f in g["missing_files"] if f not in rep_]
        if lost:
            anomalies.append(f"fichier(s) du jour manquant(s) : {', '.join(lost)} (aucune ligne DAY {days_txt(g)} sans arret "
                             "ni redemarrage du robot) : les lignes de ces jours manquent (positions, montants, comparaison)")
        if rep_:
            anomalies.append(f"fichier(s) du robot remplace(s) par un journal de MetaTrader du meme nom : {', '.join(rep_)} (aucune ligne DAY "
                             f"{days_txt(g)}) : envoyer le fichier MQL5/Files/ClaudeRobot/ de ce jour, pas celui de MQL5/Logs")
        if not g["missing_files"]:
            anomalies.append(f"lignes du robot manquantes : aucune ligne DAY {days_txt(g)} alors que les fichiers de ces jours sont la "
                             "(fichier coupe ?)")
    # the end of the journal (review2 N5): a stop line, a robot still running, or a lost last file
    end = journal_end(rows, files, releve_end)
    res["end"] = {k: v for k, v in end.items() if k != "ranges"}
    if end.get("anomaly"):
        anomalies.append(end["anomaly"])
    res["missing_files"] = sorted(set(res["missing_files"]) | set(end.get("missing_files", [])))
    # lines whose partner is absent (review2 N1), outside the holes already named
    holes = list(ranges) + list(end.get("ranges", []))
    if starts and starts[0].get("no_init") and lv:
        holes.append((-INF_T, (res.get("first_utc") or lv[0]["utc"]) + 600))      # before the first file: unknown
    res["holes_utc"] = holes
    comm = next((s["init"].get("comm_pts") for s in starts if s["init"] and s["init"].get("comm_pts") is not None), 6)
    brk = journal_breaks(rows, holes, starts, points, comm, info.get("unparsable_all"))
    res["breaks"] = brk
    if brk:
        n = missing_count(brk)
        res["missing_lines"] = dict(n)
        anomalies.append(f"{sum(n.values())} ligne(s) du journal manquante(s) (sans fichier manquant connu a ce moment : fichier coupe ou modifie ?) : "
                         + ", ".join(f"{v} {MISSING_FR.get(k, k)}" for k, v in sorted(n.items())) + f" ; par ex. {brk[0]['text_fr']}")
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
KNOWN_EXITS = ("ea_close", "broker_stop_estimated", "broker_stop_race", "broker_stop_seen", "broker_stop_after_paper")
# the robot's closes that follow the paper's own exit (CR_Follower.mqh CR_FW_NAME: time, rule, paper, revise, void, prefuse,
# latest_exit, crossed); the others (orphan, dup, slfix, prev, refused*, mark, the guards' stop, guard, lock, friday, clock,
# friday_missed) close for another reason and are not slippage against the paper's exit (review3 R3-7)
PAPER_CLOSE_WHY = ("time", "rule", "paper", "revise", "void", "prefuse", "latest_exit", "crossed")
CLOSE_LATE_S = 600                              # a close more than 10 min after the paper's exit is not compared with it
# exits at the broker's stop: the journal holds no line of them, so their price is unknown (review2 N2): they stay out of
# the exit averages, the euros and the headline, and are shown apart with an estimate at stop x (1 -/+ the lab's stop
# slippage), which is what the paper books for its own stop exit (so the estimate shows no difference by construction)
ESTIMATED_EXITS = ("broker_stop_estimated", "broker_stop_race", "broker_stop_seen", "broker_stop_after_paper")
REASON_FR = {"time": "par le temps", "target": "a l'objectif", "rule": "par sa regle", "eod": "en fin de seance",
             "void": "annule (void)", "refused": "refuse", "nofill": "sans remplissage", "skip": "saute"}


def stop_crossed(tables, b, side, segs, t_from, t_to, partial=False):
    """did the real quotes cross a position's broker stop between its fill and the paper's exit? ReleveFP's minutes
    hold the extremes of the ticks: a long position's stop is hit by the bid low (bl), a short's by the ask high (ah).
    segs = [(from_utc, level)] in time order (the FILL's sl, then each successful SLMOD). Returns (True, utc of the
    first minute that crossed), (False, None), or (None, None) when the minutes do not cover that time. With only the
    terminal's bars (r1, ah_exact False) the ask high is the bar's high + its spread, which may be the minute's smallest:
    a short's stop not crossed by it is unknown, not 'never crossed'. partial=True: minutes that cover only part of the
    time are read on that part; a crossing there is True, no crossing is None (unknown), never False."""
    tb = (tables or {}).get(b)
    segs = [(u, lv) for u, lv in segs if u is not None and isinstance(lv, (int, float)) and lv > 0]
    if tb is None or not segs or not side or t_from is None or t_to is None:
        return None, None
    t = tb["t"]
    a, z = C.utc_to_srv(int(t_from)), C.utc_to_srv(int(t_to))
    if not len(t) or int(t[0]) > a or (int(t[-1]) < z - 60 and not partial):
        return None, None
    covered = int(t[-1]) >= z - 60
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
    if (side < 0 and not tb.get("ah_exact", True)) or not covered:
        return None, None
    return False, None


def paper_stop_path(rows, code, oid, side, h, entry_utc):
    """the broker stop the robot keeps for a paper trade (FolExpectedStop: the paper's stop + side x h), from its PFILL and
    PSTOP lines: [(from UTC, level)]; used when the journal's own stop moves (SLMOD) are known to be incomplete"""
    out = []
    for r in rows:
        if r["code"] == code and r.get("oid") == oid and r["ev"] in ("PFILL", "PSTOP") and r.get("rp") != 1 and isinstance(r.get("stop"), (int, float)):
            out.append((max(int(r["utc"]) + 60, int(entry_utc or 0)), r["stop"] + side * h))
    return out


def fills_report(rows, res_a, starts, points, fiches, tables=None):
    """each real position against its paper trade; tables = the releve's minutes (--bars: m1, else the terminal's bars
    r1, per market) or None"""
    lv = C.live(rows)
    # tickets whose stop moves are known to be incomplete (a lost SLMOD line, review3 R3-4): their broker stop is taken
    # from the paper's stops (the robot keeps the broker stop at the paper's stop + side x h)
    slmod_broken = {b.get("key")[1] for b in res_a.get("breaks", []) if b["missing"] == "SLMOD" and b.get("key")}
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
    # entries late by design (review2 N8 e): a stop, limit or OCO order is sent one bar after the paper's fill (SIZE late=1,
    # CR_Sizing.mqh SizRisk); else the order's type (DEC et != 0)
    late_of = {(r["code"], r.get("oid")): r.get("late") == 1 for r in lv if r["ev"] == "SIZE"}
    et_of = {(r["code"], r.get("oid")): r.get("et") for r in rows if r["ev"] == "DEC" and r.get("what") == "ord"}
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
        if t in slmod_broken and side:                              # stop moves lost: the paper's stops say where it was
            ps = paper_stop_path(rows, p["code"], p["oid"], side, h[b], p.get("entry_utc"))
            if ps:
                segs = ps
                e["stop_from_paper"] = True
        last_sl = segs[-1][1] if segs else None
        voided_row = void_at.get((p["code"], p["oid"])) if e["paper_voided"] else None
        t_end = x["utc"] if x is not None else (voided_row["utc"] if voided_row else None)
        reason = x.get("reason") if x is not None else ("void" if voided_row else None)
        # the journal's next line about this ticket after a time: how long the position may have stayed open
        later = sorted(r["utc"] for r in lv if r.get("ticket") == t and r["ev"] in ("CLOSE", "SLMOD", "WATCH", "ORPHAN", "DUP", "SLFIX", "MARK",
                                                                                   "ADOPT"))
        if good:
            e.update(exit_real=good[0]["px"], exit_utc=good[0]["utc"], exit_kind="ea_close", close_why=good[0].get("why"))
        elif race or (x is not None and reason in STOP_REASONS):
            # the broker's stop (no line), or the race where it closed the position just before the robot's request: with
            # the releve's minutes the stop must have been reached (review2 N10)
            t_chk = (race[0]["utc"] + 60) if race else x["utc"]
            seen, when = stop_crossed(tables, b, side, segs, p.get("entry_utc"), t_chk)
            if seen is False and t in slmod_broken:
                e.update(exit_real=None, exit_utc=None, exit_kind="stop_lines_missing",
                         close_why="deplacements du stop perdus (lignes SLMOD manquantes) : stop courtier inconnu, sortie inconnue")
            elif seen is False:
                e.update(exit_real=None, exit_utc=None, exit_kind="stop_not_reached",
                         close_why=("CLOSE sans prix (rc=0) comme si le stop courtier venait de fermer la position" if race else
                                    f"le papier est sorti par son stop le {C.utc_txt(x['utc'])} sans ligne CLOSE")
                                   + ", mais les minutes du releve ne touchent jamais son stop : position fermee autrement (a la main, "
                                     "stop-out ?)")
            elif race and seen is None:
                # the race claims the broker's stop closed it just before the robot's request: without minutes that cover it
                # the claim cannot be checked, and the paper did not exit at its stop: exit unknown (review3 R3-12)
                e.update(exit_real=None, exit_utc=race[0]["utc"], exit_kind="race_unchecked", race_level=last_sl,
                         close_why=("CLOSE sans prix (rc=0) : stop courtier juste avant la fermeture du robot, non verifie (pas de minutes du "
                                    "releve sur ce moment, --bars) : sortie inconnue"))
            elif race:
                e.update(exit_real=last_sl, exit_utc=race[0]["utc"], exit_kind="broker_stop_race", stop_seen_utc=when,
                         close_why="stop courtier juste avant la fermeture du robot (CLOSE sans prix, rc=0) : prix inconnu")
            else:
                e.update(exit_real=last_sl, exit_utc=x["utc"], exit_kind="broker_stop_estimated", stop_seen_utc=when,
                         close_why="stop courtier (aucune ligne : prix inconnu)"
                                   + (" ; niveau pris au stop du papier (lignes SLMOD manquantes)" if e.get("stop_from_paper") else ""))
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
            seen2, when2 = (None, None)
            if seen is False:
                # not stopped before the paper's exit: maybe after it, while the robot did not close it (stopped, asleep,
                # disconnected), up to the journal's next line about this ticket (review3 R3-12)
                t_next = next((u for u in later if u > t_end), None) or (lv[-1]["utc"] if lv else t_end)
                if t_next > t_end + 60:
                    seen2, when2 = stop_crossed(tables, b, side, segs, p.get("entry_utc"), t_next, partial=True)
            if seen:
                e.update(exit_real=last_sl, exit_utc=when, exit_kind="broker_stop_seen", stop_seen_utc=when,
                         close_why="stop courtier touche avant la sortie du papier (vu dans les minutes du releve) : prix inconnu")
            elif seen2:
                e.update(exit_real=last_sl, exit_utc=when2, exit_kind="broker_stop_after_paper", stop_seen_utc=when2,
                         close_why=f"pas fermee par le robot a la sortie du papier ({rfr} le {C.utc_txt(t_end)} : robot arrete ou deconnecte ?), "
                                   f"puis fermee par le stop courtier le {C.utc_txt(when2)} (vu dans les minutes du releve) : prix inconnu")
            elif seen is False and t in slmod_broken:
                e.update(exit_real=None, exit_utc=None, exit_kind="stop_lines_missing",
                         close_why="deplacements du stop perdus (lignes SLMOD manquantes) : stop courtier inconnu, sortie inconnue")
            elif seen is False and seen2 is False:
                e.update(exit_real=None, exit_utc=None, exit_kind="not_closed",
                         close_why=f"position non fermee par le robot : pas de ligne CLOSE alors que le papier est sorti {rfr} le "
                                   f"{C.utc_txt(t_end)}, et les minutes du releve ne touchent pas son stop")
            elif seen is False:
                e.update(exit_real=None, exit_utc=None, exit_kind="not_closed",
                         close_why=f"position non fermee par le robot : pas de ligne CLOSE alors que le papier est sorti {rfr} le "
                                   f"{C.utc_txt(t_end)} ; les minutes du releve ne touchent pas son stop jusque-la (apres : minutes "
                                   "absentes)")
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
        if e["exit_kind"] == "ea_close":
            # a close for another reason than the paper's exit, or long after it, is no slippage against it (review3 R3-7)
            cw = str(e.get("close_why") or "")
            if cw not in PAPER_CLOSE_WHY:
                e["exit_apart"] = f"fermeture {cw}, pas la sortie du papier"
            elif e.get("paper_exit_utc") is None:
                e["exit_apart"] = "pas de sortie du papier"
            elif (e.get("exit_utc") or 0) - e["paper_exit_utc"] > CLOSE_LATE_S:
                e["exit_apart"] = f"fermee {((e.get('exit_utc') or 0) - e['paper_exit_utc']) // 60} min apres la sortie du papier"
        if e["exit_kind"] in ESTIMATED_EXITS and side and last_sl:
            # exit_real is the stop's level, not a price; the estimate adds the lab's stop slippage (fp_costs.json)
            e["exit_estimated"] = True
            e["exit_est"] = last_sl * (1 - side * C.SLIP_BPS[b][1] / 1e4)
            e["exit_est_slip_bp"] = C.SLIP_BPS[b][1]
            if e.get("paper_exit") is not None:
                d = side * (e["paper_exit"] - e["exit_est"])
                e["exit_diff_est_pts"] = d / pt
                e["exit_diff_est_bp"] = d / e["paper_exit"] * 1e4
                e["exit_diff_est_net_bp"] = (d + comm_side[b]) / e["paper_exit"] * 1e4    # gold: the paper's prices hold h
                e["exit_diff_est_eur"] = d * e["lots"] * k if (k and e.get("lots")) else None
                # gold: the paper's stop exit holds h and the broker stop is the paper's stop + side x h, so the raw estimate
                # is about -h by construction: the commission-included figure is the one shown (review3 R3-11)
                e["exit_diff_est_net_eur"] = (d + comm_side[b]) * e["lots"] * k if (k and e.get("lots")) else None
        if side and e.get("exit_real") is not None and e.get("entry_real") is not None and e.get("lots") and k:
            e["gross_eur"] = side * (e["exit_real"] - e["entry_real"]) * e["lots"] * k
            e["model_commission_eur"] = 2 * h[b] * e["lots"] * k
        key = (p["code"], p["oid"])
        e["late_by_design"] = bool(late_of[key]) if key in late_of else (et_of.get(key) not in (None, 0))
        out.append(e)
    out.sort(key=lambda e: (e.get("entry_utc") or 0))
    for kind, label in (("close_refused", "fermeture(s) refusee(s) et jamais reussie(s) dans le journal"),
                        ("not_closed", "position(s) non fermee(s) par le robot (sortie du papier passee, stop jamais touche)"),
                        ("stop_not_reached", "position(s) donnee(s) fermee(s) par le stop courtier dont les minutes du releve ne "
                                             "touchent jamais le stop"),
                        ("no_close_unknown", "position(s) sans ligne CLOSE alors que le papier est sorti sans stop (non fermee par "
                                             "le robot, ou stop courtier avant : a verifier)"),
                        ("missing_exit", "position(s) sans aucune sortie au milieu du journal (lignes manquantes ?)"),
                        ("race_unchecked", "fermeture(s) sans prix (CLOSE rc=0) donnee(s) au stop courtier sans pouvoir le verifier"),
                        ("stop_lines_missing", "position(s) dont les deplacements du stop manquent (lignes SLMOD)"),
                        ("broker_stop_after_paper", "position(s) pas fermee(s) par le robot a la sortie du papier, fermee(s) ensuite par "
                                                    "le stop courtier")):
        xs = [e for e in out if e["exit_kind"] == kind]
        if xs:
            e0 = xs[0]
            tail = (" ; prix de sortie inconnu (estime au stop)" if kind in KNOWN_EXITS else " ; sortie inconnue, laissee hors des totaux en euros")
            anomalies.append(f"{len(xs)} {label}, par ex. {e0['code']} ticket {e0['ticket']} : {e0['close_why']}{tail}")
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
        # exits: the robot's closes only (a broker stop has no price in the journal, review2 N2); entries: in TOTAL the ones
        # on time only, the entries late by design apart (review2 N8 e); per sleeve and per market all (each is one kind)
        known = [e for e in ps if e["exit_kind"] == "ea_close" and not e.get("exit_apart")]
        apart = [e for e in ps if e["exit_kind"] == "ea_close" and e.get("exit_apart")]
        est = [e for e in ps if e["exit_kind"] in ESTIMATED_EXITS]
        late = [e for e in ps if e.get("late_by_design")]
        src = {"entry": ps if key_ is not None else [e for e in ps if not e.get("late_by_design")], "exit": known, "fill": ps}
        keys = [("entry_diff_bp", "entry"), ("exit_diff_bp", "exit"), ("fill_vs_quote_bp", "fill"), ("entry_diff_net_bp", "entry"),
                ("exit_diff_net_bp", "exit")]
        if key_ is not None:
            keys += [("entry_diff_pts", "entry"), ("entry_diff_net_pts", "entry"), ("exit_diff_pts", "exit"), ("exit_diff_net_pts", "exit"),
                     ("fill_vs_quote_pts", "fill")]
        for kk, which in keys:
            v = [e[kk] for e in src[which] if e.get(kk) is not None]
            q[kk + "_mean"] = C.mean(v)
            q[kk + "_median"] = C.median(v)
        for kk, which in (("entry_diff_eur", ps), ("exit_diff_eur", known), ("gross_eur", ps), ("model_commission_eur", ps)):
            v = [e[kk] for e in which if e.get(kk) is not None]
            q[kk + "_sum"] = sum(v) if v else None
        lv_ = [e["entry_diff_bp"] for e in late if e.get("entry_diff_bp") is not None]
        q["entries_late"] = len(lv_)
        q["entry_diff_late_bp_mean"] = C.mean(lv_)
        le = [e["entry_diff_eur"] for e in late if e.get("entry_diff_eur") is not None]
        q["entry_diff_late_eur_sum"] = sum(le) if le else None
        q["estimated_exits"] = len(est)
        q["exit_diff_est_bp_mean"] = C.mean([e["exit_diff_est_bp"] for e in est if e.get("exit_diff_est_bp") is not None])
        q["exit_diff_est_net_bp_mean"] = C.mean([e["exit_diff_est_net_bp"] for e in est if e.get("exit_diff_est_net_bp") is not None])
        if key_ is not None:
            q["exit_diff_est_pts_mean"] = C.mean([e["exit_diff_est_pts"] for e in est if e.get("exit_diff_est_pts") is not None])
        ee = [e["exit_diff_est_eur"] for e in est if e.get("exit_diff_est_eur") is not None]
        q["exit_diff_est_eur_sum"] = sum(ee) if ee else None
        en = [e["exit_diff_est_net_eur"] for e in est if e.get("exit_diff_est_net_eur") is not None]
        q["exit_diff_est_net_eur_sum"] = sum(en) if en else None
        # the robot's closes for another reason than the paper's exit, or long after it, apart (review3 R3-7)
        q["exits_apart"] = len(apart)
        q["exits_apart_why"] = dict(Counter(e["exit_apart"].split(",")[0] for e in apart))
        ea = [e["exit_diff_eur"] for e in apart if e.get("exit_diff_eur") is not None]
        q["exit_apart_eur_sum"] = sum(ea) if ea else None
        q["exit_apart_bp_mean"] = C.mean([e["exit_diff_bp"] for e in apart if e.get("exit_diff_bp") is not None])
        q["exits"] = dict(Counter(e["exit_kind"] for e in ps))
        q["stop_exits_paper"] = sum(1 for e in ps if e.get("paper_reason") in STOP_REASONS)
        q["broker_stops_estimated"] = sum(1 for e in ps if e["exit_kind"] in ESTIMATED_EXITS)
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
        brk = res_a.get("breaks") or []
        isnum = lambda x: isinstance(x, (int, float)) and math.isfinite(x)   # noqa: E731
        db = (days[-1]["balance"] if isnum(days[-1]["balance"]) else 0) - (days[0]["balance"] if isnum(days[0]["balance"]) else 0)
        gross = sum(e["gross_eur"] for e in closed)
        # positions the balance holds but the gross cannot (review3 R3-2): closed in the window but opened before the
        # first file (no FILL or ADOPT for the ticket), or adopted with an entry outside the journal
        followed = {e["ticket"] for e in out}
        unseen = sorted({r.get("ticket") for r in lv if r["ev"] == "CLOSE" and r.get("ok") == 1 and t0 <= r["utc"] < t1
                         and r.get("ticket") not in followed})
        no_entry = sorted(e["ticket"] for e in out if e.get("exit_utc") and t0 <= e["exit_utc"] < t1 and e.get("gross_eur") is None
                          and e["exit_kind"] in KNOWN_EXITS)
        st0 = (res_a.get("starts") or [{}])[0]
        no_init = bool(st0.get("no_init_line") and not st0.get("init_lost"))
        tail = (res_a.get("end") or {}).get("kind") == "missing_tail"
        why = []
        if unknown:
            why.append(f"{len(unknown)} position(s) sans prix de sortie connu")
        if holes:
            why.append(f"{sum(g['days'] for g in holes)} jour(s) de journal manquant(s)")
        if brk:
            why.append(f"{sum(missing_count(brk).values())} ligne(s) manquante(s)")
        if no_init:
            why.append("debut du journal absent (pas de ligne INIT : positions ouvertes avant inconnues)")
        if tail:
            why.append("fin du journal absente (dernier fichier manquant)")
        if unseen:
            why.append(f"position(s) fermee(s) dans la periode sans leur ouverture dans le journal : tickets {', '.join(str(x) for x in unseen[:6])}")
        if no_entry:
            why.append(f"position(s) reprise(s) (ADOPT) dont l'entree est hors du journal : tickets {', '.join(str(x) for x in no_entry[:6])}")
        money = {"from": days[0]["day"], "to": days[-1]["day"], "balance_change_eur": db, "gross_from_prices_eur": gross,
                 "costs_not_in_prices_eur": db - gross, "model_commission_eur": sum(e.get("model_commission_eur") or 0 for e in closed),
                 "positions": len(closed), "with_estimated_stop_prices": sum(1 for e in closed if e["exit_kind"] != "ea_close"),
                 "positions_exit_unknown": len(unknown), "missing_days": sum(g["days"] for g in holes), "journal_breaks": len(brk),
                 "unseen_tickets": unseen, "tickets_without_entry": no_entry, "journal_start_missing": no_init, "journal_end_missing": tail,
                 "complete": not why, "incomplete_why": why,
                 "note": ("estimation : commission + swap + glissement des stops courtier (leur sortie est comptee au niveau du stop, "
                          "sans glissement) + autres operations du compte")}
    return {"positions": out, "per_sleeve": per, "per_symbol": per_sym, "money_estimate": money, "points": points, "h_price": h,
            "commission_per_side_price": comm_side, "commission_source": comm_src, "duplicates": doubles, "anomalies": anomalies,
            "minutes_used_for_stops": bool(tables),
            "commission_swap_per_trade": "UNKNOWN : le journal n'a pas de ligne par transaction (deal)"}


# ---------------------------------------------------------------------------------------------- (c) replay
M1_COLS = ["time", "bo", "bh", "bl", "bc", "ao", "ah", "al", "ac", "n", "sp_mean", "sp_max"]   # ReleveFP 1.00; 1.10 adds sp_min
R1_COLS = ["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]   # r1_<BASE>.csv (ReleveFP 1.10)


def read_m1(path, info=None):
    """ReleveFP's m1 file (columns read by name; sp_min when the file has it, ReleveFP 1.10). Bad rows and a last line
    cut while copying are dropped and counted in info (demo_common.read_releve_csv, review3 U3, R10)"""
    df, inf = C.read_releve_csv(path, M1_COLS, optional=("sp_min",))
    if info is not None:
        info.update(inf)
    df["time"] = df["time"].astype(np.int64)
    return df.drop_duplicates("time").sort_values("time").reset_index(drop=True)


def read_r1(path, info=None):
    """ReleveFP 1.10's r1 file: the terminal's own M1 bars (MqlRates, the bars the robot reads with CopyRates): time
    (server seconds), bid open/high/low/close with the symbol's digits, tick_volume, spread (points), real_volume;
    days newest first (sorted here). All eight columns are needed on a row (review3 R10)"""
    df, inf = C.read_releve_csv(path, R1_COLS)
    if info is not None:
        info.update(inf)
    df["time"] = df["time"].astype(np.int64)
    df["spread"] = df["spread"].astype(np.int64)
    return df.drop_duplicates("time").sort_values("time").reset_index(drop=True)


def m1_digits(path):
    """decimals of the first price of a ReleveFP file (prices are written with the symbol's digits)"""
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
    conv = {"open": o, "close": c, "mean": np.floor(mean_ + 0.5 + 1e-7), "max": mx, "min2": np.minimum(o, c)}   # half-way up (R9)
    if "sp_min" in df.columns:                                     # ReleveFP 1.10: the smallest spread of the minute's ticks
        conv["min"] = np.rint(df.sp_min.to_numpy() * sc)
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
    bar's s_raw; (2) every COST line carries the day's median raw spread in bp of the mid over the kept bars. 'min' (the
    sp_min column) exists only in ReleveFP 1.10 files. usable is False when the paper lines show that no column gives the
    bar spread (best share below CONV_USABLE): the replay of those markets cannot be used (review2 N4); a convention that
    gives most bars but not all (a few days whose minutes differ from the broker's bars) keeps the replay, whose
    differences and COST lines then show those days"""
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
            if k in tb["conv"]:
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
            if k not in tb["conv"]:
                continue
            s = tb["conv"][k][sel] * tb["point"]
            mid = tb["bid_o"][sel] + s / 2
            med = float(np.median(s / mid * 1e4))
            cost[k].append(abs(med - r["raw_bp"]) / max(r["raw_bp"], 1e-12))
    out = {"paper_lines": per, "min_consistent": min_ok,
           "cost_days": {k: {"days": len(v), "mean_rel_err": (sum(v) / len(v)) if v else None} for k, v in cost.items()}}
    choice, why, usable, share = "open", "defaut (export_frames.py prend l'ecart de l'ouverture)", True, None
    n = per["open"]["n"]
    if n >= 10:
        best = max((k for k in SPREAD_CONV if per[k]["n"]), key=lambda k: (per[k]["match"] / per[k]["n"], k == "open"))
        share = per[best]["match"] / per[best]["n"]
        choice, why = best, f"{per[best]['match']} barres sur {per[best]['n']} egales a s_raw des lignes du papier"
        usable = share >= CONV_USABLE
    elif any(v for v in cost.values()):
        best = min((k for k in SPREAD_CONV if cost[k]), key=lambda k: sum(cost[k]) / len(cost[k]))
        choice, why = best, f"ecart median du jour le plus proche des lignes COST ({len(cost[best])} jours)"
    out["choice"], out["why"], out["usable"], out["share"] = choice, why, usable, share
    out["conventions"] = [k for k in SPREAD_CONV if per[k]["n"] or cost[k]]
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
OUT_UNUSABLE = "ecart des barres inconnu pour ce marche (aucune colonne du releve ne redonne MqlRates.spread)"
OUT_WRITTEN = "ligne que le robot aurait ecrite apres son arret (decision datee avant, ecrite plus tard)"


def write_times(rows):
    """when each line was written: a journal is in write order and the NOW_STAMPED events carry the clock, so a line was
    written at the latest of its own stamp and the clock of the lines before it (a decision stamped at its bar can be
    written hours later, at the server's midnight: D4H's DEC stamped 17:59 UTC lies after the 22:00 DAY line)"""
    out, now = {}, None
    for r in rows:
        if r["ev"] in NOW_STAMPED and r.get("rp") != 1:
            now = r["utc"] if now is None else max(now, r["utc"])
        out[id(r)] = r["utc"] if now is None else max(now, r["utc"])
    return out


class Windows:
    """where a live line can be compared: inside its sleeve's own span (the markets it reads all have minutes) after
    the sleeve's warm-up and once both paper chains have been flat together, while the live copy ran live with the
    same paper inputs, outside the hours of a missing daily file; never for a sleeve reading a market whose bar spread
    is unknown (unusable: an m1 file where no column gives MqlRates.spread, review2 N4)"""

    def __init__(self, starts, spans, inputs, flat=None, no_bars=(), gaps=(), unusable=()):
        self.flat = flat or {}
        self.no_bars = set(no_bars)
        self.unusable = set(unusable)
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
        if code in self.unusable:
            return OUT_UNUSABLE
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

    def not_live_at(self, w):
        """why a line the replay wrote at w (its write time, not its stamp) cannot be in the live journal: inside a missing
        daily file's hours, or while no live copy ran (after a stop, or after the last line of files copied while the robot
        ran); None when the live copy was running then"""
        if w is None:
            return None
        if any(a <= w <= b for a, b in self.gaps):
            return OUT_GAP
        if self.no_init or any(a < w <= b for a, b, _ in self.cover):
            return None
        return OUT_WRITTEN


def rebuild_windows(rows):
    """the times a running robot was not live (review3 R3-1): a REBUILD why=reconnect (MetaTrader lost the server for more
    than 60 s: Wi-Fi drop, Mac asleep) or why=latebar (a revised bar) writes the minutes from the last live line before it
    to its 'to' only as its replay's rp=1 lines (CR_Main.mqh MainLive returns while disconnected, then MainRebuild). Returns
    [(from, to, REBUILD row, rp=1 rows of that rebuild)], from = the write time of the last live line before the rebuild"""
    wt = write_times(rows)
    out = []
    for i, r in enumerate(rows):
        if r["ev"] != "REBUILD" or r.get("why") not in ("reconnect", "latebar") or r.get("rp") == 1 or not isinstance(r.get("to"), int):
            continue
        j, block = i - 1, []
        while j >= 0 and rows[j].get("rp") == 1:
            block.append(rows[j])
            j -= 1
        if j < 0:
            continue
        out.append((wt[id(rows[j])], int(r["to"]), r, block[::-1]))
    return out


def rebuild_substitutes(rows):
    """the rp=1 lines a reconnection's rebuild wrote for the minutes the robot was not live: inside (from, to] of each
    rebuild_windows entry they stand for the live lines the robot could not write (review3 R3-1)"""
    subs = []
    for a, z, _, block in rebuild_windows(rows):
        for r in block:
            if r["ev"] in COMPARE_EV and a < key_time(r) <= z:
                subs.append(r)
    return subs


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


def compare_lines(live_rows, rep_rows, win, mode, dist, replay_ready, subs=()):
    lv = keyed([r for r in live_rows if r["ev"] in COMPARE_EV and r.get("rp") != 1])
    n_sub = 0
    for k, r in keyed(list(subs)).items():                   # a reconnection's rp=1 lines where no live line exists (R3-1)
        if k not in lv:
            lv[k] = r
            n_sub += 1
    rp = keyed([r for r in rep_rows if r["ev"] in COMPARE_EV and r.get("rp") != 1])
    rep_written = write_times(rep_rows)
    stats = {ev: Counter() for ev in COMPARE_EV}
    diffs, account, excluded = [], [], Counter()
    compared = Counter()                                     # lines compared per sleeve (coverage)
    span_seen = {}                                           # first and last compared time per sleeve
    for k in sorted(set(lv) | set(rp), key=lambda k: (key_time(lv.get(k) or rp.get(k)), str(k))):
        a, b = lv.get(k), rp.get(k)
        r = a or b
        ev, code = r["ev"], r["code"]
        why = win.why_out(code, key_time(r), dec_time(r))
        if not why and a is None:
            # a line only the replay has: the live robot could not write it if it would have come after its stop or in a
            # missing file's hours, although its stamp is earlier (a decision written at the next server midnight)
            why = win.not_live_at(rep_written.get(id(b)))
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
            # a rebuild's rp=1 line standing for a live one (R3-1): its SIZE was sized dry, without the live gates (observer,
            # stopped, guard ...), so its skip reason is not comparable
            st, bad = compare_fields(a, b, dict(mode, skip=False) if (a.get("rp") == 1 and ev == "SIZE") else mode)
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
            "compared_per_sleeve": dict(compared), "compared_span_per_sleeve": span_seen, "rebuild_lines_used": n_sub}


def side_by_side(live_rows, rep_rows, first_day_srv=None, cover=None):
    """AGG (kept bars fed per server day and symbol) and COST (median spreads) of both sides; the replay's first server
    day is left out of AGG (CR_Main.mqh MainDaily starts its counters at the first barrier of a run). cover = {market:
    (first, last minute of its bars, server)}: a market's count is compared only on the days its bars cover whole, after
    its own first day (a market whose minutes start late, review2 N8 c)"""
    agg_l = {r.get("day"): r for r in live_rows if r["ev"] == "AGG"}
    agg_r = {r.get("day"): r for r in rep_rows if r["ev"] == "AGG"}
    agg = []
    for d in sorted(set(agg_l) & set(agg_r)):
        if first_day_srv is not None and d <= first_day_srv:
            continue
        e = {"day": C.ymd(d)}
        bs = [b for b in C.ROBOT_BASES if cover is None or (b in cover and cover[b][0] - cover[b][0] % 86400 < d
                                                             and d + 86400 <= cover[b][1] + 2 * 3600)]
        if not bs:
            continue
        for b in bs:
            e[b] = (agg_l[d].get(b), agg_r[d].get(b))
        e["markets"] = bs
        e["same"] = all(e[b][0] == e[b][1] for b in bs)
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


def load_minutes(bars_dir, fiches, fini=None):
    """ReleveFP's files of --bars as tables: m1_<BASE>.csv (the minutes built from ticks) and, from ReleveFP 1.10,
    r1_<BASE>.csv (the terminal's own M1 bars, what the robot reads). fini = fini.txt beside them (read_mac_files.read_fini)
    or None: its counts say whether an r1 file is cut (rows < barres=), not copied (barres > 0 and no file), stale (barres=-1:
    ReleveFP could not write it, an older file is left), or read with errors (erreur_barres > 0) (review3 R8, R6). Returns
    {"m1": {market: table}, "r1": {...}, "stop": the tables of the broker-stop checks (m1, else r1), "files": {market:
    [names]}, "problems": [...], "advice": [...] (what to do, printed on stdout), "unreadable": {market: [names]} (files that
    could not be read at all), "bad_rows": {name: n}}."""
    m1t, r1t, files, problems, advice = {}, {}, defaultdict(list), [], []
    unreadable, bad_rows = defaultdict(list), {}
    fm = (fini or {}).get("markets", {}) if fini else {}
    for b in C.ROBOT_BASES:
        dg_f = (fiches.get(b) or {}).get("digits") if fiches and (fiches.get(b) or {}).get("found") else None
        p = os.path.join(bars_dir, f"m1_{b}.csv")
        if os.path.exists(p):
            try:
                inf = {}
                df = read_m1(p, inf)
                if inf.get("bad_rows") or inf.get("cut_last"):
                    bad_rows[f"m1_{b}.csv"] = inf.get("bad_rows", 0) + int(bool(inf.get("cut_last")))
                if not len(df):
                    problems.append(f"m1_{b}.csv vide")
                else:
                    dg = int(dg_f) if dg_f is not None else m1_digits(p)
                    conv, lo, hi = spread_points(df, dg)
                    t = df.time.to_numpy()
                    m1t[b] = {"src": "m1", "df": df, "digits": dg, "point": 10.0 ** -dg, "conv": conv, "lo": lo, "hi": hi, "t": t,
                              "index": {int(x): i for i, x in enumerate(t)}, "bid_o": df.bo.to_numpy(), "kept": mask_kept(t, C.FAMILY[b]),
                              "bl": df.bl.to_numpy().astype(float), "ah": df.ah.to_numpy().astype(float), "ah_exact": True}
                    files[b].append(os.path.basename(p))
            except Exception as e:                               # noqa: BLE001 (any unreadable file is reported, never fatal)
                problems.append(f"m1_{b}.csv illisible ({e.__class__.__name__} : texte jamais recopie)")
                unreadable[b].append(f"m1_{b}.csv")
        p = os.path.join(bars_dir, f"r1_{b}.csv")
        fb = fm.get(b) or {}
        bars_f = fb.get("barres") if isinstance(fb.get("barres"), int) else None
        if os.path.exists(p) and bars_f is not None and bars_f < 0:
            problems.append(f"r1_{b}.csv laisse de cote : ReleveFP n'a pas pu l'ecrire cette fois (barres=-1 dans fini.txt), le fichier "
                            "est d'un releve plus ancien")
            advice.append(f"relancer ReleveFP : il n'a pas pu ecrire r1_{b}.csv (fichier ouvert ailleurs ?)")
        elif os.path.exists(p):
            try:
                inf = {}
                df = read_r1(p, inf)
                if inf.get("bad_rows") or inf.get("cut_last"):
                    bad_rows[f"r1_{b}.csv"] = inf.get("bad_rows", 0) + int(bool(inf.get("cut_last")))
                if bars_f is not None and inf.get("rows", 0) + inf.get("bad_rows", 0) + int(bool(inf.get("cut_last"))) < bars_f:
                    problems.append(f"r1_{b}.csv coupe : {bars_f - inf.get('rows', 0)} barre(s) de moins que fini.txt (barres={bars_f}) ; "
                                    "ReleveFP ecrit le jour le plus recent d'abord, ce sont les plus anciens qui manquent")
                    advice.append(f"recopier r1_{b}.csv en entier")
                if isinstance(fb.get("erreur_barres"), int) and fb["erreur_barres"] > 0:
                    advice.append(f"relancer ReleveFP : {fb['erreur_barres']} jour(s) de barres r1_{b} illisibles (erreur_barres)")
                if not len(df):
                    problems.append(f"r1_{b}.csv vide")
                    if bars_f is None or bars_f > 0:
                        advice.append(f"relancer ReleveFP : r1_{b}.csv est vide (barres du terminal pas encore chargees ?)")
                else:
                    dg = int(dg_f) if dg_f is not None else m1_digits(p)
                    sc, pt = 10.0 ** dg, 10.0 ** -dg
                    t = df.time.to_numpy()
                    o, h, l_, c = (np.rint(df[k].to_numpy() * sc).astype(np.int64) for k in ("open", "high", "low", "close"))
                    sp = df.spread.to_numpy().astype(np.int64)
                    r1t[b] = {"src": "r1", "digits": dg, "point": pt, "t": t, "o": o, "h": h, "l": l_, "c": c, "s": sp,
                              "bl": df.low.to_numpy().astype(float), "ah": df.high.to_numpy().astype(float) + sp * pt, "ah_exact": False}
                    files[b].append(os.path.basename(p))
            except Exception as e:                               # noqa: BLE001
                problems.append(f"r1_{b}.csv illisible ({e.__class__.__name__} : texte jamais recopie)")
                unreadable[b].append(f"r1_{b}.csv")
        elif bars_f is not None and bars_f > 0:
            advice.append(f"copier aussi r1_{b}.csv (fini.txt dit barres={bars_f})")
        elif bars_f is not None and bars_f < 0:
            advice.append(f"relancer ReleveFP : il n'a pas pu ecrire r1_{b}.csv (fichier ouvert ailleurs ?)")
        # the terminal's bars end before the minutes: the M1 series was still loading when ReleveFP read it (review3 R2)
        if b in r1t and b in m1t and int(r1t[b]["t"][-1]) // 86400 < int(m1t[b]["t"][-1]) // 86400:
            problems.append(f"r1_{b}.csv finit le {C.ymd(int(r1t[b]['t'][-1]))}, avant m1_{b}.csv ({C.ymd(int(m1t[b]['t'][-1]))}) : "
                            "barres du terminal pas encore chargees quand ReleveFP les a lues")
            advice.append(f"relancer ReleveFP : les barres r1_{b} s'arretent le {C.ymd(int(r1t[b]['t'][-1]))}, les minutes m1 le "
                          f"{C.ymd(int(m1t[b]['t'][-1]))}")
        if b not in m1t and b not in r1t:
            problems.append(f"ni m1_{b}.csv ni r1_{b}.csv lisible : les regles de {b} ne sont pas rejouees")
    stop = {b: (m1t.get(b) or r1t.get(b)) for b in C.ROBOT_BASES if b in m1t or b in r1t}
    return {"m1": m1t, "r1": r1t, "stop": stop, "files": dict(files), "problems": problems, "advice": advice,
            "unreadable": dict(unreadable), "bad_rows": bad_rows}


NO_MINUTES = {"m1": {}, "r1": {}, "stop": {}, "files": {}, "problems": [], "advice": [], "unreadable": {}, "bad_rows": {}}


def inp_days_needed(live0, last_minute):
    """ReleveFP's InpDays that lets every sleeve be compared from the start of the live journal: the longest warm-up
    (D4H, 120 days) and 5 days for the paper chains to align, before the first live day"""
    need = int(math.ceil((last_minute - live0) / 86400.0)) + max(WARMUP_DAYS.values()) + 6
    return max(150, need)


def replay_check(rows, starts, minutes, out, fiches, spread_opt, inputs_extra, rebuild, scrub, gaps=()):
    lv = C.live(rows)
    rep = {"status": "not run"}
    problems = list(minutes["problems"])
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
    # the bars of each market: the terminal's own (r1_<BASE>.csv, ReleveFP 1.10: MqlRates as the robot reads them, exact)
    # when present, else the minutes built from ticks (m1_<BASE>.csv) with the spread convention measured on the journal
    m1t, r1t = minutes["m1"], minutes["r1"]
    src = {b: ("r1" if b in r1t else "m1") for b in C.ROBOT_BASES if b in r1t or b in m1t}
    rep["bar_source"] = src
    if not src:
        rep.update(status="impossible", why="aucun fichier m1_<marche>.csv ni r1_<marche>.csv lisible dans --bars", problems=problems)
        return rep
    m1_used = {b: m1t[b] for b in src if src[b] == "m1"}
    cal = calibrate(lv, m1_used) if m1_used else None
    conv = (cal["choice"] if spread_opt == "auto" else spread_opt) if cal else None
    # each market judged on its own paper lines (review3 R15): one market whose minutes do not give the bar spread is set
    # aside, the others are replayed; a market with too few paper lines takes the choice of all markets together
    per_mkt, conv_of, unusable = {}, {}, []
    for b in sorted(m1_used):
        cb = calibrate(lv, {b: m1_used[b]})
        n_b = cb["paper_lines"]["open"]["n"]
        own = n_b >= 10
        per_mkt[b] = {"choice": cb["choice"] if own else conv, "share": cb["share"], "paper_lines": n_b,
                      "usable": cb["usable"] if own else (cal["usable"] if cal else True), "why": cb["why"] if own else "trop peu de lignes "
                      "du papier : choix de tous les marches"}
        conv_of[b] = (per_mkt[b]["choice"] if spread_opt == "auto" else spread_opt)
        if spread_opt == "auto" and not per_mkt[b]["usable"]:
            unusable.append(b)
    rep["spread"] = {"calibration": cal, "used": conv, "asked": spread_opt, "markets_from_m1": sorted(m1_used), "per_market": per_mkt,
                     "used_per_market": conv_of}
    # no column gives the bar spread (review2 N4): the sleeves of those markets cannot be compared; with no r1 file at
    # all the replay cannot be used, and is not run (hundreds of differences would hide any real one)
    rep["unusable_markets"] = unusable
    if unusable and len(unusable) == len(src):
        best = max((cal["paper_lines"][k]["match"] for k in SPREAD_CONV), default=0)
        rep.update(status="unusable", problems=problems,
                   why=("les minutes de ReleveFP (fichiers m1) ne permettent pas de refaire les calculs du robot : lancer ReleveFP 1.10 et "
                        "renvoyer aussi ses fichiers r1_<marche>.csv"),
                   detail=(f"aucune colonne des fichiers m1 ne redonne l'ecart des barres du robot (MqlRates.spread) : au mieux {best} barres "
                           f"sur {cal['paper_lines']['open']['n']} ; minimum compatible {cal['min_consistent']['inside']}/"
                           f"{cal['min_consistent']['n']} (SPEC 10.3 : MT5 garde sans doute l'ecart minimum de la minute)"))
        return rep
    work = os.path.join(out, "replay")
    bars_out = os.path.join(work, "bars")
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(bars_out)
    syms = {}
    first, last, cover_srv = {}, {}, {}
    for b in C.ROBOT_BASES:
        path = os.path.join(bars_out, f"{names[b]}.bin")
        if src.get(b) == "r1":
            tb = r1t[b]
            write_bin(path, tb["digits"], tb["t"], tb["o"], tb["h"], tb["l"], tb["c"], tb["s"])
        elif src.get(b) == "m1":
            tb = m1t[b]
            sc = 10.0 ** tb["digits"]
            o, h, l_, c = (np.rint(tb["df"][k].to_numpy() * sc).astype(np.int64) for k in ("bo", "bh", "bl", "bc"))
            cv = conv_of.get(b, conv)
            if cv not in tb["conv"]:
                problems.append(f"m1_{b}.csv n'a pas la colonne de la convention {cv} (sp_min : ReleveFP 1.10) : ecart de l'ouverture pris")
            write_bin(path, tb["digits"], tb["t"], o, h, l_, c, tb["conv"].get(cv, tb["conv"]["open"]))
        else:
            dg = int((fiches.get(b) or {}).get("digits") or 2) if fiches else 2
            write_bin(path, dg, np.zeros(0, np.int64), *(np.zeros(0, np.int64) for _ in range(5)))
        if b in src:
            first[b], last[b] = C.srv_to_utc(int(tb["t"][0])), C.srv_to_utc(int(tb["t"][-1]))
            cover_srv[b] = (int(tb["t"][0]), int(tb["t"][-1]))
        syms[names[b]] = path
    span = [min(first.values()), max(last.values())]
    # each sleeve's own span: the markets it reads must all have bars (M4: a market whose history at the broker is
    # short delays its own sleeves only, and is named)
    spans = {}
    for c in C.CODES:
        rd = C.READS_OF_CODE[c]
        if all(b in src for b in rd):
            spans[c] = (max(first[b] for b in rd), min(last[b] for b in rd) - 3600)
    for b in sorted(src):
        codes = ", ".join(c for c in C.CODES if b in C.READS_OF_CODE[c])
        fname = f"{src[b]}_{b}.csv"
        if first[b] > span[0] + 86400:
            problems.append(f"{fname} commence le {C.utc_txt(first[b])}, plus tard que les autres marches ({C.utc_txt(span[0])}) : "
                            f"historique du courtier plus court ; {codes} compare(s) a partir de cette date et de leur echauffement")
        if last[b] < span[1] - 86400:
            problems.append(f"{fname} finit le {C.utc_txt(last[b])}, plus tot que les autres ({C.utc_txt(span[1])}) : {codes} "
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
    unusable_codes = [c for c in C.CODES if any(b in unusable for b in C.READS_OF_CODE[c])]
    win = Windows(starts, spans, paper_inputs(init), flat, no_bars, gaps, unusable_codes)
    rep["span"] = {"from": C.utc_txt(span[0]), "to": C.utc_txt(span[1]), "compared_to": C.utc_txt(span_to),
                   "warmup_days": WARMUP_DAYS,
                   "per_sleeve": {c: [C.utc_txt(a), C.utc_txt(z)] for c, (a, z) in spans.items()},
                   "sleeves_compared_from": {c: (C.utc_txt(flat[c]) if flat[c] < INF else "jamais") for c in C.CODES}}
    rw = rebuild_windows(rows)
    rep["not_live_windows"] = [{"from": C.utc_txt(a), "to": C.utc_txt(z), "why": r.get("why")} for a, z, r, _ in rw]
    rep["comparison"] = compare_lines(rows, rrows, win, mode, disturbances(lv), replay_ready, rebuild_substitutes(rows))
    # coverage (M3): what was really compared per sleeve, against the live journal's time
    cover = [(s["live_from"], s["end"]) for s in starts if s.get("live_from") is not None and s.get("end")]
    live0 = min(a for a, _ in cover) if cover else span[0]
    live1 = max(z for _, z in cover) if cover else span[1]
    cmpd = rep["comparison"]["compared_per_sleeve"]
    cov, short, late_start = {}, [], False
    for c in C.CODES:
        if c in unusable_codes:
            cov[c] = {"from": None, "to": None, "lines": 0, "never": True, "partial": True,
                      "why": "ecart des barres inconnu pour " + ", ".join(b for b in C.READS_OF_CODE[c] if b in unusable)}
            continue
        if c not in spans:
            miss_b = [b for b in C.READS_OF_CODE[c] if b not in src]
            bad_f = [f for b in miss_b for f in minutes.get("unreadable", {}).get(b, [])]
            cov[c] = {"from": None, "to": None, "lines": 0, "never": True, "partial": True,
                      "why": (f"fichier illisible : {', '.join(bad_f)}" if bad_f else "pas de minutes du releve pour " + ", ".join(miss_b))}
            continue
        lo = max(spans[c][0] + WARMUP_DAYS[c] * 86400, flat[c])
        a, z = max(lo, live0), min(spans[c][1], live1)
        if a >= z:
            why = (f"echauffement de {WARMUP_DAYS[c]} jours : minutes du releve depuis le {C.utc_txt(spans[c][0])}, comparable a partir "
                   f"du {C.utc_txt(lo) if lo < INF else '?'}" if spans[c][1] > live0 else
                   f"minutes du releve finies le {C.utc_txt(spans[c][1])}, avant la demo")
            cov[c] = {"from": None, "to": None, "lines": cmpd.get(c, 0), "never": True, "partial": True, "why": why}
            short.append(c)
            late_start |= spans[c][1] > live0
        else:
            part = a > live0 + 86400 or z < live1 - 86400
            cov[c] = {"from": C.utc_txt(a), "to": C.utc_txt(z), "lines": cmpd.get(c, 0), "never": False, "partial": part,
                      "why": ("debut de la demo hors des minutes du releve (echauffement)" if a > live0 + 86400 else "")}
            if part:
                short.append(c)
                late_start |= a > live0 + 86400
    rep["coverage"] = cov
    rep["coverage_short"] = short
    advice = []
    if span[1] < live1 - 86400:                                    # minutes taken before the end of the demo (review2 N8 d)
        advice.append(f"relancer ReleveFP apres la demo : ses minutes finissent le {C.utc_txt(span[1])}, le journal le {C.utc_txt(live1)}")
    if late_start:
        days = inp_days_needed(live0, max(span[1], live1))
        demo_d = int(math.ceil((max(span[1], live1) - live0) / 86400.0))
        gold_d = max(200, demo_d + max(WARMUP_DAYS.values()) + 6)
        other_d = max(75, demo_d + max(v for c, v in WARMUP_DAYS.items() if C.SYM_OF_CODE[c] != "XAUUSD") + 6)
        advice.append(f"pour comparer toutes les sleeves sur toute la demo, relancer ReleveFP 1.10 (barres r1 : InpRateSymbols = "
                      f"XAUUSD:{gold_d},US100:{other_d},BTCUSD:{other_d},ETHUSD:{other_d}) ou avec InpDays={days} (les echauffements vont "
                      f"jusqu'a {max(WARMUP_DAYS.values())} jours)")
    advice += [a for a in minutes.get("advice", []) if a not in advice]
    if advice:
        rep["coverage_advice"] = " ; ".join(advice)
    first_srv = min(v[0] for v in cover_srv.values())
    rep["side_by_side"] = side_by_side(lv, rlive, first_srv - first_srv % 86400, cover_srv)
    rep["names"] = names
    rep["files"] = minutes["files"]
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
        # the window is bounded by write order, not by stamps (review2 N3): some lines are written days after their stamp
        # (a Friday-close DEC on Monday), so the lines required are the files' live lines between the first and the last
        # printed one, in file order
        seq = [r["_raw"] for r in rows if r.get("rp") != 1]
        pos = defaultdict(list)
        for i, x in enumerate(seq):
            pos[x].append(i)
        idx = [i for x in p_raw for i in pos.get(x, [])]
        span_live = seq[min(idx):max(idx) + 1] if idx else []
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
def releve_end_utc(dirs, fiches, minutes, scrub):
    """when ReleveFP ran, UTC (review2 N5): fini.txt's server_time (beside the m1 files or fiches.csv), the latest tick
    time of fiches.csv, the end of its minutes or bars; None when none is there. fini.txt names the account's server:
    it is masked at once and nothing else of the file is kept"""
    cands = []
    for d in dirs:
        p = os.path.join(d, "fini.txt") if d else None
        if not p or not os.path.exists(p):
            continue
        try:
            for ln in C.read_text(p).splitlines():
                k, _, v = ln.partition("=")
                if k.strip() == "server":
                    scrub.add(v.strip())
                elif k.strip() == "server_time" and C.fnum(v) and isinstance(C.fnum(v), int):
                    cands.append(C.srv_to_utc(C.fnum(v)))
        except OSError:
            continue
    for f in (fiches or {}).values():
        if f.get("found") and isinstance(f.get("tick_time"), int) and f["tick_time"] > 0:
            cands.append(C.srv_to_utc(f["tick_time"]))
    for tb in list(minutes["m1"].values()) + list(minutes["r1"].values()):
        if len(tb["t"]):
            cands.append(C.srv_to_utc(int(tb["t"][-1])) + 60)
    return max(cands) if cands else None


def read_fiches_near(paths, scrub=None, problems=None):
    """fiches.csv (--fiches, or beside the m1 files of --bars): {} when absent or unreadable; a file without ReleveFP's
    header (re-saved by a spreadsheet with semicolons, say) is named in problems, never a traceback (review3 R1)"""
    for p in paths:
        if p and os.path.exists(p):
            sys.path.insert(0, HERE)
            import read_mac_files as R
            try:
                f, pr = R.read_fiches(p, scrub)
            except Exception as e:                                # noqa: BLE001 (one bad file never stops the others)
                f, pr = {}, [f"{os.path.basename(p)} illisible ({e.__class__.__name__} : texte jamais recopie)"]
            if problems is not None:
                problems += [x for x in pr if "illisible" in x or "en-tete" in x or "vide" in x]
            return f
    return {}


def read_fini_near(d, scrub):
    """fini.txt beside the files of --bars (read_mac_files.read_fini; the server name is masked at once), None when absent"""
    p = os.path.join(d, "fini.txt") if d else None
    if not p or not os.path.exists(p):
        return None
    sys.path.insert(0, HERE)
    import read_mac_files as R
    try:
        return R.read_fini(p, scrub)
    except Exception:                                             # noqa: BLE001
        return None


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
    for u in rep["inputs"].get("unparsable_first", [])[:10]:
        L.append(f"  ligne illisible : {u['file']} ligne {u['line']} ({u.get('why')}) : texte jamais recopie")
    for g in a.get("day_gaps", []):
        if g.get("explained") and g.get("illegible_days"):
            L.append(f"  ligne DAY illisible (modifiee ?) le {', '.join(g['illegible_days'])} : pas un jour manquant")
            continue
        L.append(f"  JOURS MANQUANTS ({days_txt(g)}) : "
                 + (f"fichier(s) absent(s) {', '.join(g['missing_files'])}" if g["missing_files"] else "lignes DAY absentes (fichier coupe ?)")
                 + (f" ; ligne DAY illisible (modifiee ?) le {', '.join(g['illegible_days'])}" if g.get("illegible_days") else ""))
    end = a.get("end") or {}
    if end.get("kind") == "missing_tail":
        L.append(f"  FIN DU JOURNAL : fichier(s) probablement manquant(s) {', '.join(end['missing_files'])} (releve jusqu'au "
                 f"{end.get('releve_end_when')})")
    elif end.get("kind") == "no_stop_unknown":
        L.append("  fin du journal : pas de ligne d'arret (robot encore en marche, ou dernier fichier manquant)")
    elif end.get("kind") == "running":
        L.append(f"  fin du journal : {end.get('note')}")
    for k in a.get("breaks", [])[:10]:
        L.append(f"  LIGNE MANQUANTE ({MISSING_FR.get(k['missing'], k['missing'])}) : {k['text_fr']} ({k['file']} ligne {k['line']})")
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
        if s.get("init_lost"):
            L.append("    LIGNE INIT PERDUE : des lignes suivent l'arret precedent sans nouvelle ligne de demarrage")
        if s.get("no_deinit"):
            L.append("    FIN SANS LIGNE D'ARRET (terminal ferme d'un coup, Mac eteint, ou ligne perdue)")
        if s.get("no_rebuild"):
            L.append("    LIGNE REBUILD PERDUE : en direct compte a partir de la ligne INIT + 5 min")
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
    L.append("Positions reelles contre le papier (ecart positif = cout : le reel a fait moins bien que le papier ; meme sens pour les euros) :")
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
        ent = (f"{C.frs(q.get('entry_diff_pts_mean'), 2, 'pts')} ({C.frs(q['entry_diff_bp_mean'], 2, 'pb')}) en moyenne" if pts
               else f"{C.frs(q['entry_diff_bp_mean'], 2, 'pb')} en moyenne")
        if pts and q.get("entries_late"):
            ent += f" (dont {q['entries_late']} en retard d'une barre par construction)"
        elif not pts and q.get("entries_late"):
            ent = ((f"{C.frs(q['entry_diff_bp_mean'], 2, 'pb')} en moyenne pour les entrees a l'heure" if q["entry_diff_bp_mean"] is not None
                    else "aucune a l'heure")
                   + f" ; {q['entries_late']} entree(s) en retard par construction (ordres stop envoyes une barre apres le papier) : "
                   f"{C.frs(q.get('entry_diff_late_bp_mean'), 2, 'pb')}")
        sor = (f"{C.frs(q.get('exit_diff_pts_mean'), 2, 'pts')} ({C.frs(q['exit_diff_bp_mean'], 2, 'pb')})" if pts
               else C.frs(q["exit_diff_bp_mean"], 2, "pb"))
        fil = (f"{C.frs(q.get('fill_vs_quote_pts_mean'), 2, 'pts')} ({C.frs(q['fill_vs_quote_bp_mean'], 2, 'pb')})" if pts
               else C.frs(q["fill_vs_quote_bp_mean"], 2, "pb"))
        unk = f", {q['exit_unknown']} sortie(s) inconnue(s) (hors des euros)" if q.get("exit_unknown") else ""
        est = ""
        if q.get("estimated_exits"):
            # gold: the raw estimate is about -h by construction (the paper's stop holds h): shown commission included only
            # (review3 R3-11)
            if net:
                fig = (f"{C.frs(q.get('exit_diff_est_net_bp_mean'), 2, 'pb')}, {C.frs(q.get('exit_diff_est_net_eur_sum'), 2, 'EUR')} "
                       "(commission comprise : le papier de l'or met la commission dans son stop)")
            else:
                fig = f"{C.frs(q.get('exit_diff_est_bp_mean'), 2, 'pb')}, {C.frs(q.get('exit_diff_est_eur_sum'), 2, 'EUR')}"
            est = (f" ; {q['estimated_exits']} sortie(s) par stop courtier : prix et glissement inconnus (aucune ligne), hors des moyennes et "
                   f"des euros, seulement dans la difference du solde ; estimation au stop x (1 - glissement du labo) : {fig}")
        apart = ""
        if q.get("exits_apart"):
            apart = (f" ; {q['exits_apart']} fermeture(s) du robot pour une autre raison que la sortie du papier, ou bien apres "
                     f"({', '.join(f'{k} {v}' for k, v in q.get('exits_apart_why', {}).items())}), a part : "
                     f"{C.frs(q.get('exit_apart_bp_mean'), 2, 'pb')}, {C.frs(q.get('exit_apart_eur_sum'), 2, 'EUR')}")
        return (f"  {name:6s} {q['positions']} position(s) : entree {ent}, sortie {sor} (fermetures du robot a la sortie du papier), soit "
                f"{C.frs((q['entry_diff_eur_sum'] or 0) + (q['exit_diff_eur_sum'] or 0), 2, 'EUR')} ; stops : {q['stop_exits_paper']} au papier, "
                f"{q['broker_stops_estimated']} chez le courtier{unk} ; remplissage contre le prix de l'envoi {fil}" + est + apart + net)
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
        kinds_fr = {"ea_close": "fermees par le robot", "broker_stop_estimated": "stop courtier (prix inconnu)",
                    "broker_stop_race": "stop courtier juste avant la fermeture du robot", "broker_stop_seen":
                    "stop courtier vu dans les minutes du releve", "close_refused": "FERMETURE REFUSEE", "not_closed": "NON FERMEES",
                    "stop_not_reached": "STOP JAMAIS TOUCHE DANS LES MINUTES",
                    "no_close_unknown": "SANS LIGNE CLOSE (a verifier)", "missing_exit": "SANS SORTIE (lignes manquantes ?)",
                    "open_or_unknown": "encore ouvertes a la fin du journal", "race_unchecked": "CLOSE SANS PRIX NON VERIFIE",
                    "stop_lines_missing": "STOP INCONNU (SLMOD manquants)",
                    "broker_stop_after_paper": "PAS FERMEES A LA SORTIE DU PAPIER, puis stop courtier"}
        L.append("  sorties : " + ", ".join(f"{kinds_fr.get(k, k)} {n}" for k, n in ex.most_common()))
        for e in [e for e in b["positions"] if e["exit_kind"] not in KNOWN_EXITS and e["exit_kind"] != "open_or_unknown"][:10]:
            L.append(f"    {e['code']} ticket {e['ticket']} ouverte le {C.utc_txt(e['entry_utc']) if e.get('entry_utc') else '?'} : {e['close_why']}")
    L.append(f"  commission et swap par trade : inconnus (le journal n'a pas de ligne par transaction) ; commission or retenue : "
             f"{b['commission_source']}.")
    if b.get("money_estimate") and b["money_estimate"]["positions"]:
        m = b["money_estimate"]
        L.append(f"  solde du {m['from']} au {m['to']} : {C.frs(m['balance_change_eur'], 2, 'EUR')} ; resultat brut des prix "
                 f"{C.frs(m['gross_from_prices_eur'], 2, 'EUR')} ; frais hors des prix (commission + swap + glissement des stops, estimation) : "
                 f"{cost_words(m['costs_not_in_prices_eur'])} ; commission du modele {C.fr(m['model_commission_eur'], 2, 'EUR')}")
        if not m.get("complete", True):
            L.append(f"  attention : estimation incomplete ({' ; '.join(m.get('incomplete_why') or [])}) : la difference n'est pas que des frais")
    L.append("")
    if r is None:
        L.append("Rejeu : non demande (--bars absent).")
    elif r.get("status") == "unusable":
        L.append(f"Rejeu inutilisable : {r.get('why')}")
        L.append(f"  detail : {r.get('detail')}")
    elif r.get("status") != "done":
        why = " / ".join(x.strip() for x in str(r.get("why", "")).splitlines() if x.strip())[:300]
        L.append(f"Rejeu : {STATUS_FR.get(r.get('status'), r.get('status'))}" + (f" (detail technique : {why})" if why else ""))
        for a_ in r.get("advice", []) or []:
            L.append(f"  a faire : {a_}")
    else:
        L.append(f"Rejeu des barres du releve ({r['span']['from']} - {r['span']['to']}) avec le banc d'essai (observateur) :")
        L.append("  barres : " + ", ".join(f"{b} {'r1_' + b + '.csv (barres du terminal, exactes)' if v == 'r1' else 'm1_' + b + '.csv (minutes des ticks)'}"
                                           for b, v in r.get("bar_source", {}).items()))
        L += spread_lines(r)
        sb = r["side_by_side"]
        L.append(f"  barres par jour identiques (AGG) : {sb['agg_days_same']}/{sb['agg_days']} jours ; ecart du jour identique (COST) : "
                 f"{sb['cost_same']}/{sb['cost_n']}")
        cmpr = r["comparison"]
        sm = r["size_mode"]
        L.append(f"  SIZE compare sur : {', '.join(sm['compared'])} (jamais : {', '.join(sm['never'])}, qui suivent le compte reel "
                 f"ou le tick de l'envoi ; le journal n'a pas l'historique des transactions pour les rejouer)")
        word = {"equal": "egales", "tol": "egales a 1e-12 pres", "diff": "differentes", "only_live": "seulement en direct",
                "only_replay": "seulement au rejeu", "account": "selon le compte reel", "skip_replay_not_ready": "marche pas pret au rejeu"}
        for ev in COMPARE_EV:
            st = cmpr["by_event"].get(ev, {})
            if st:
                L.append(f"  {ev:7s} : " + ", ".join(f"{word.get(k, k)} {v}" for k, v in sorted(st.items())))
        if cmpr.get("rebuild_lines_used"):
            L.append(f"  robot hors ligne (reconnexion) : {cmpr['rebuild_lines_used']} ligne(s) comparee(s) a celles que le robot a ecrites "
                     "en se reconstruisant (rp=1) : " + ", ".join(f"du {w['from']} au {w['to']}" for w in r.get("not_live_windows", [])))
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
            for x in p.get("printed_not_in_files", [])[:10]:
                L.append(f"  imprimee mais absente des fichiers : {x}")
            for x in p.get("live_not_printed", [])[:10]:
                L.append(f"  dans les fichiers mais pas imprimee : {x}")
        else:
            cm = p.get("comparison", {})
            L.append(f"Lignes imprimees : {p.get('kind')} ; {len(cm.get('differences', []))} difference(s) sur les lignes de SPEC 10.12.")
    L.append("")
    if rep["anomalies"]:
        L.append("A REGARDER :")
        L += [f"  - {x}" for x in rep["anomalies"]]
    else:
        L.append("Verdict : " + verdict(rep)[0].lower() + verdict(rep)[1:])
    return L


def spread_lines(r):
    """the French lines about the bar spread convention (m1 files only; r1 files hold MqlRates.spread itself)"""
    cal = (r.get("spread") or {}).get("calibration")
    if not cal:
        return ["  ecart de la barre : MqlRates.spread lu dans les fichiers r1 (aucune calibration)"]
    pl = cal["paper_lines"]
    ks = [k for k in SPREAD_CONV if pl[k]["n"]]
    out = [f"  ecart de la barre (MqlRates.spread) sur {', '.join(r['spread'].get('markets_from_m1', []))} : "
           + ", ".join(f"{k} {pl[k]['match']}/{pl[k]['n']}" for k in ks)
           + f" ; minimum compatible {cal['min_consistent']['inside']}/{cal['min_consistent']['n']} ; retenu : {r['spread']['used']} ({cal['why']})"]
    best = max((pl[k]["match"] for k in ks), default=0)
    if pl["open"]["n"] and best < CONV_MATCH * pl["open"]["n"]:
        out.append(f"  attention : aucune colonne du releve ne redonne l'ecart de toutes les barres ({best}/{pl['open']['n']} au mieux) ; "
                   f"si le minimum est compatible ({cal['min_consistent']['inside']}/{cal['min_consistent']['n']}), MT5 garde l'ecart minimum de "
                   "la minute : ReleveFP 1.10 l'ecrit (sp_min) et donne les barres du terminal (r1)")
    if r.get("unusable_markets") and r.get("status") == "done":
        out.append(f"  rejeu inutilisable pour {', '.join(r['unusable_markets'])} (ecart des barres inconnu) : leurs sleeves ne sont pas comparees")
    return out


def verdict(rep):
    """the last line when nothing is abnormal: plain only when the replay compared every sleeve over the whole demo,
    else it says what could not be compared (review2 N1)"""
    r = rep.get("replay")
    if r is None:
        return f"Rien d'anormal sur ce qui a pu etre compare ({len(C.CODES)} sleeves non comparees : pas de rejeu sans --bars)."
    if r.get("status") == "unusable":
        return f"Rien d'anormal sur ce qui a pu etre compare ({len(C.CODES)} sleeves non comparees : rejeu inutilisable, ecart des barres inconnu)."
    if r.get("status") != "done":
        return (f"Rien d'anormal sur ce qui a pu etre compare ({len(C.CODES)} sleeves non comparees : rejeu "
                f"{STATUS_FR.get(r.get('status'), r.get('status'))}).")
    cov = r.get("coverage", {})
    never = [c for c in C.CODES if cov.get(c, {}).get("never")]
    part = [c for c in C.CODES if cov.get(c, {}).get("partial") and not cov.get(c, {}).get("never")]
    if not never and not part:
        return "Rien d'anormal."
    txt = []
    if never:
        txt.append(f"{len(never)} sleeve{'s' if len(never) > 1 else ''} non comparee{'s' if len(never) > 1 else ''} : {', '.join(never)}")
    if part:
        txt.append(f"en partie seulement : {', '.join(part)}")
    return "Rien d'anormal sur ce qui a pu etre compare (" + " ; ".join(txt) + ")."


STATUS_FR = {"not run": "pas lance", "impossible": "impossible", "build failed": "construction du robot en echec",
             "replay failed": "rejeu en echec (le robot du banc d'essai s'est arrete)", "skipped": "non lance (--no-replay)",
             "unusable": "inutilisable", "done": "fait"}


def money_words(x, what="le reel a fait"):
    """an amount in words with its direction (review3 U1): 'le reel a fait 48,84 EUR de moins que le papier'"""
    if x is None:
        return f"{what} ? EUR"
    if abs(x) < 0.005:
        return f"{what} autant que le papier"
    return f"{what} {C.fr(abs(x), 2, 'EUR')} de {'moins' if x > 0 else 'plus'} que le papier"


def cost_words(x):
    """the balance's costs not in the prices (balance change - gross result): negative = a cost"""
    if x is None:
        return "?"
    return f"cout de {C.fr(-x, 2, 'EUR')}" if x <= 0 else f"gain de {C.fr(x, 2, 'EUR')} (inattendu)"


def headline_eur(tot):
    """the euros of the headline (review3 R3-7): every entry (the late-by-design ones too, said apart) and the robot's closes
    at the paper's exit; positive = the real trades did worse than the paper"""
    total = (tot.get("entry_diff_eur_sum") or 0) + (tot.get("exit_diff_eur_sum") or 0)
    return total, tot.get("entry_diff_late_eur_sum")


def short_summary(rep):
    a, b, r = rep["journal"], rep["fills"], rep.get("replay")
    S = [f"Journal : {a['live_lines']} lignes en direct, {len(a['starts'])} demarrage(s), build "
         f"{', '.join(sorted({str(s['build']) for s in a['starts']})) or '?'}."]
    tot = b["per_sleeve"]["TOTAL"]
    if tot["positions"]:
        # the headline holds known prices only: entries on time (the late-by-design ones apart, review2 N8 e) and the robot's
        # own closes at the paper's exit (a broker stop has no price in the journal, review2 N2; a close for another reason is
        # no slippage, review3 R3-7); the euros in words with their direction (review3 U1)
        if tot["entry_diff_bp_mean"] is not None or not tot.get("entries_late"):
            ent = C.frs(tot["entry_diff_bp_mean"], 2, "pb")
            if tot.get("entries_late"):
                ent += (f" (hors {tot['entries_late']} entree(s) en retard par construction : "
                        f"{C.frs(tot.get('entry_diff_late_bp_mean'), 2, 'pb')})")
        else:
            ent = f"{C.frs(tot.get('entry_diff_late_bp_mean'), 2, 'pb')} (les {tot['entries_late']} en retard par construction)"
        sor = C.frs(tot["exit_diff_bp_mean"], 2, "pb")
        hors = []
        if tot.get("estimated_exits"):
            hors.append(f"{tot['estimated_exits']} sortie(s) par stop courtier, prix inconnu")
        if tot.get("exits_apart"):
            hors.append(f"{tot['exits_apart']} fermeture(s) pour une autre raison que la sortie du papier")
        if hors:
            sor += f" (hors {' ; '.join(hors)})"
        total, late_eur = headline_eur(tot)
        dont = (f" (dont {C.fr(abs(late_eur), 2, 'EUR')} de {'moins' if late_eur > 0 else 'plus'} sur les entrees en retard par "
                "construction)") if late_eur else ""
        S.append(f"Trades : {tot['intents']} intentions, {tot['real_trades']} trades reels, {tot['positions']} positions suivies ; "
                 f"ecart moyen avec le papier (positif = cout) : entree {ent}, sortie {sor} ; en tout {money_words(total)} sur les prix "
                 f"connus{dont} (points par marche dans report_fr.txt).")
        m = b.get("money_estimate")
        if m and m.get("positions"):
            S.append(f"Solde du {m['from']} au {m['to']} : {C.frs(m['balance_change_eur'], 2, 'EUR')} ; frais hors des prix estimes d'apres le "
                     f"solde (commission, swap, glissement des stops) : {cost_words(m['costs_not_in_prices_eur'])} (commission du modele "
                     f"{C.fr(m['model_commission_eur'], 2, 'EUR')})" + ("" if m.get("complete", True) else " ; estimation incomplete (report_fr.txt)")
                     + ".")
    else:
        S.append(f"Trades : {tot['intents']} intentions, aucun trade reel"
                 + (" (copie observatrice : normal)." if a["starts"] and all(s["observer"] == 1 for s in a["starts"]) else "."))
    if r is not None and r.get("status") == "done":
        n = len(r["comparison"]["differences"])
        ncmp = sum(r["comparison"].get("compared_per_sleeve", {}).values())
        srcs = sorted(set(r.get("bar_source", {}).values()))
        how = ("barres du terminal (r1)" if srcs == ["r1"] else
               (f"minutes des ticks (m1), ecart de barre retenu : {r['spread']['used']}" if srcs == ["m1"] else
                f"barres r1 et minutes m1 (ecart de barre retenu : {r['spread']['used']})"))
        S.append(f"Rejeu : {n} difference(s) sur {ncmp} lignes comparees ; {how}.")
        if r.get("unusable_markets"):
            S.append(f"  rejeu inutilisable pour {', '.join(r['unusable_markets'])} : les minutes du releve ne redonnent pas l'ecart des barres "
                     "du robot ; lancer ReleveFP 1.10 et renvoyer ses fichiers r1_<marche>.csv")
        cov = r.get("coverage", {})
        never = [c for c, v in cov.items() if v["never"]]
        part = [c for c, v in cov.items() if v["partial"] and not v["never"]]
        if never or part or r.get("coverage_advice"):
            S.append("  couverture : " + (f"jamais comparees : {', '.join(never)}" if never else "")
                     + (" ; " if never and part else "") + (f"en partie seulement : {', '.join(part)}" if part else "")
                     + (" ; " if (never or part) and r.get("coverage_advice") else "") + (r.get("coverage_advice") or ""))
    elif r is not None and r.get("status") == "unusable":
        pass                                                    # said once, in the list below (review3 U5)
    elif r is not None:
        S.append(f"Rejeu : {STATUS_FR.get(r.get('status'), r.get('status'))}."
                 + (f" A faire : {' ; '.join(r['advice'])}." if r.get("advice") else ""))
    if rep["anomalies"]:
        S.append(f"A regarder ({len(rep['anomalies'])}) :")
        S += [f"  - {x}" for x in rep["anomalies"][:20]]
        if len(rep["anomalies"]) > 20:
            S.append(f"  ... et {len(rep['anomalies']) - 20} autres (report_fr.txt)")
    else:
        S.append(verdict(rep))
    return S


def run(args):
    scrub = C.Scrubber()
    out = C.safe_out(args.out)
    paths = C.journal_paths(args.journals)
    if not paths:
        raise SystemExit("aucun fichier .log du robot dans le dossier --journals")
    rows, info = C.read_journal_files(paths, scrub, any_name=os.path.isfile(args.journals))
    if not rows:
        why = "; ".join(f"{s_['file']} : {s_['why']}" for s_ in info["skipped_files"][:5])
        raise SystemExit(scrub.text(f"aucune ligne du robot dans --journals ({why}) : il faut les fichiers "
                                    "MQL5/Files/ClaudeRobot/<aaaammjj>.log du robot"))
    fiche_problems = []
    fiches = read_fiches_near([args.fiches, os.path.join(args.bars, "fiches.csv") if args.bars else None], scrub, fiche_problems)
    builds = C.known_builds()
    fini = read_fini_near(args.bars, scrub) if args.bars else None
    minutes = load_minutes(args.bars, fiches, fini) if args.bars else NO_MINUTES
    rel_end = releve_end_utc([args.bars, os.path.dirname(os.path.abspath(args.fiches)) if args.fiches else None], fiches, minutes, scrub)
    points, how = point_sizes(rows, fiches)
    res_a, anomalies, starts = analyse_journal(rows, builds, info["files"], rel_end, info, points)
    res_b = fills_report(rows, res_a, starts, points, fiches, minutes["stop"])
    res_b["points_source"] = how
    rep = {"tool": "check_demo", "version": 2,
           "inputs": {"journal_files": info["files"], "unparsable": info["unparsable"], "unparsable_first": info["unparsable_first"],
                      "skipped_files": info["skipped_files"], "foreign_lines": info["foreign_lines"],
                      "foreign_first": info["foreign_first"], "repeated_lines": info.get("repeated_lines", 0),
                      "repeated_first": info.get("repeated_first", []), "unknown_keys_dropped": info.get("unknown_keys_dropped", 0),
                      "fiches_problems": fiche_problems},
           "required_build": C.REQUIRED_BUILD, "known_builds": builds, "journal": res_a, "fills": res_b, "anomalies": anomalies}
    if info["skipped_files"]:
        anomalies.append(f"{len(info['skipped_files'])} fichier(s) ignore(s) dans --journals : "
                         + "; ".join(f"{s_['file']} ({s_['why']})" for s_ in info["skipped_files"][:4]))
    if info["unparsable"]:
        u0 = info["unparsable_first"][0]
        anomalies.append(f"{info['unparsable']} ligne(s) illisible(s) dans le journal (fichier coupe ou modifie ? texte jamais recopie), "
                         f"la premiere : {u0['file']} ligne {u0['line']} ({u0['why']})")
    if info["foreign_lines"]:
        anomalies.append(f"{info['foreign_lines']} ligne(s) qui ne sont pas du robot dans ses fichiers (premiere : "
                         f"{info['foreign_first'][0]['file']} ligne {info['foreign_first'][0]['line']})")
    if info.get("repeated_lines"):                                # a file read twice (review3 R3-8)
        r0 = info["repeated_first"][0]
        anomalies.append(f"{info['repeated_lines']} ligne(s) du robot en double mot pour mot (le robot date chaque ligne a la seconde : un "
                         f"fichier copie deux fois ?), la premiere : {r0['file']} ligne {r0['line']}")
    for fp in fiche_problems:
        anomalies.append(f"fiches.csv : {fp} (renvoyer le fichier d'origine de ReleveFP)")
    for b, names in (minutes.get("unreadable") or {}).items():
        anomalies.append(f"fichier du releve illisible : {', '.join(names)} (le recopier depuis le Mac)")
    for nm, n in (minutes.get("bad_rows") or {}).items():
        anomalies.append(f"{nm} : {n} ligne(s) illisible(s) laissee(s) de cote (fichier modifie ou coupe ? le recopier depuis le Mac)")
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
                                 f"le {bad[0]['day']} : {C.fr(bad[0]['raw_bp'][0], 8)} pb en direct, {C.fr(bad[0]['raw_bp'][1], 8)} au rejeu "
                                 "(l'ecart des minutes du releve n'est pas exactement celui des barres du courtier)")
        elif r.get("status") == "unusable":
            anomalies.append(f"rejeu inutilisable : {r.get('why')}")
        else:
            anomalies.append(f"rejeu impossible : {STATUS_FR.get(r.get('status'), r.get('status'))} (details dans report_fr.txt)")
    elif args.bars:
        rep["replay"] = {"status": "skipped", "problems": minutes["problems"], "advice": minutes.get("advice", [])}
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
            anomalies.append("lignes imprimees (onglet Experts) differentes des fichiers du robot (les lignes dans report_fr.txt)")
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
    C.warn_if_in_repo([a.journals, a.bars, a.fiches] + list(a.printed or []))
    run(a)
    out = C.safe_out(a.out)
    print(f"Fichiers ecrits : {os.path.join(out, 'report.json')} et {os.path.join(out, 'report_fr.txt')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
