"""Check the robot's start from the lines the user copied in MetaTrader's Experts tab and pasted into the chat.

    python3 -I lab/robot/demo/check_start.py FILE

FILE = what the user pasted, saved as text by the lead: one or several lines copied from the Experts tab with right-click ->
Copy, or lines of a MetaTrader log file (MQL5/Logs). Each line may carry the tab's columns before 'CR|' (the time, the source
such as 'ClaudeRobot (XAUUSD.r,M1)', tabs or spaces); the robot's line starts at 'CR|' (CR_Journal.mqh JrnAt prints every live
line, rp=1 never). Read: UTF-8, UTF-16 with or without a byte-order mark, cp1252, CRLF or CR line ends, a UTF-8 byte-order mark,
non-breaking spaces, quotes or a code fence around the lines, two robot lines glued on one line (review5b START-GLUED-PREFIX: with the
next line's Experts or log prefix between them when the copy lost its line ends: date and time, or a log file's code, severity and time,
then the source 'ClaudeRobot (XAUUSD.r,M1)'; that prefix is taken off the end of the robot line before it is read). A robot line the chat
wrapped onto the next lines is put back together when the pieces read as one robot line (said as information). After a line that already
reads on its own (review6 FV5-START-TRAILING-DIGITS, review5b START-TRAILING-WORD), the next line is its end only when it brings later fields
('|key=...'), when the line's last value is a number or a risk table visibly cut ('20000:0.' then '7'; a table the robot accepts as it stands,
its one ';' at the end included, is not: SizParseTable, review6b FV6-START-SEMICOLON-CUT), or when it mends the INIT line's last
name ('ETHUSD.' then 'r', 'ETHUSD' then '.r'): a word, a time ('10:02'), a number, a dot or a login typed after a line ('merci' after INIT,
'0' after SELFTEST, the login after PLAN or CLOCK) is never glued onto its last value, never printed, and the line is read alone. When the two
would read as one row all the same, that reading is only looked at: a SELFTEST line whose golden= reads 366 only with the next line, or a
PLAN line whose risk table is the INIT line's only with it, is a line the chat wrapped (said as information); otherwise the doubtful value is
'texte colle apres la ligne, ou ligne coupee : demander de la recopier', never printed. Text glued on the same line is caught by what the
robot itself writes: the PLAN line's risk table is the INIT line's (MainWait and MainInitLine both write g_cfg.risk_table), a risk table the
robot would refuse (demo_common.risk_table_ok, SizParseTable) is not its text, golden=366 followed by more digits is glued text, and the
CLOCK line's rule_s is 7200 or 10800 (ClkRuleOffset); such a value is never printed and the line is to be copied again. Text glued onto the
INIT line's last name with no line end (the name '.r' then more characters) is 'texte colle apres la ligne INIT : demander de la recopier',
never another market; the glued text is never printed. A MISSED line's reason is its last field (FolMissedTxt): only the robot's own words
are printed, 'refused_<rc>' only when rc is one of MetaTrader's trade server return codes (demo_common.TRADE_RETCODES, with its meaning when
known); other digits after 'refused_', and any after 'code', are glued text, never printed, the line to be copied again (review6b
FV6-START-MISSED-GLUED-DIGITS). A line cut short is said plainly ('ligne coupee : demander de la recopier'), and so is a piece of a robot line
without its start; 'CR|' in the user's own words (not followed by the stamp's digits, no robot field after it: 'Les lignes commencent par CR|')
is other text (review6b FV6-START-PROSE-CR-PIPE). The lines are read with demo_common's parser and schema (a line that fails is never printed),
every line is scanned first so that account values (login, server, holder's name, user folder) are masked, and the text of a line that is
not the robot's is never printed. A line pasted twice counts once.

The starts are grouped as check_demo groups them (check_demo.starts_of: the lines OnInit writes before INIT, a CLOCK or an ERROR,
belong to the start that follows; an INIT with deinit= is the robot's stop line, named as such). The last start decides; the
earlier ones are named with what was different in them. Robot facts from dist/ClaudeRobot.mq5: OnInit checks the inputs first
(an InpRiskTable, InpK1T or 'rule BKE' refusal, 'symbol ... not found': an ERROR line, no INIT, then the stop line deinit=8), then
takes the instance lock ('another copy of ClaudeRobot runs on this terminal', INIT_FAILED), then writes INIT (MainInitLine) and SELFTEST;
MainWait writes PLAN once connected (on a demo with InpPlanStart 0, 'PLAN src=first_deal' may precede it), MainRebuild writes
REBUILD, CBarStore::Check writes READY for each market once its history is deep enough (NOTREADY meanwhile).
A second copy dragged onto another chart while the pasted start runs (review6 FV5-START-SECOND-COPY): its OnInit finds the lock taken,
writes ERROR 'another copy of ClaudeRobot runs on this terminal' and returns INIT_FAILED (MQL5 documentation, OnInit: 'When returning
INIT_FAILED, the EA is forcibly unloaded from the chart'), then OnDeinit writes its stop line INIT deinit=8 (REASON_INITFAILED, rebuilds=0)
the same second; its daily file stays the first copy's (opened FILE_SHARE_READ), so only the Experts tab shows these two lines, after or
among the running start's lines. They are set apart (second_copies: an ERROR 'another copy' after a line of a running copy, its INIT build=
line or any other line it writes, with no stop line of that copy before it, or followed by such a line that is not a new INIT build= line;
and the deinit=8 line within 60 s): 'INFO : deuxieme copie du robot refusee ... la copie qui tourne continue : ne pas relancer le robot',
and the verdict says to tell the user so (the guide's advice after an ERROR line, remove the robot from the other chart and relaunch it, does
not apply), unless the paste ends with the stop line of the copy that ran; they never end the running start, which is checked as usual. The
same ERROR followed by an INIT build= line is a start refused then relaunched (starts_of). Alone in the paste (review6b
FV6-START-LONE-SECOND-COPY), it still means a copy runs: GrdLockTake refuses only a lock another copy refreshed less than 10 s before
(CR_GRD_LOCK_STALE_MS), so the advice is to remove nothing and to ask for the INIT line of the copy that runs (error_meaning, shared with
check_demo), never 'le robot n'a pas demarre'; exit code 1 (nothing checked).

Checks of the last start (one line each):
  INIT (check_demo.start_settings, shared with check_demo, so that the two tools never disagree): build fd6aaf01e332 or a later
    build of dist/'s git history, version 2.00, harness=0, comm_pts=6, demo=1, the risk table exactly S7 = 0:7;3000:3.5;10000:1.4;
    20000:0.7 (D2 named when the default was left), sleeves ALL, the three switches on, k1t giving 417.23813245421888 for 2026
    (DoubleToString(v,-16): 2026:4.1723813245421888e+02 or e+002; within 1e-9), the four .r names (another name: which), and,
    for this check only, vps=0, tester=0, observer=0 and entries_off=0 (the Mac's trading copy);
  SELFTEST ok=1 with golden=366 (CR_GOLDEN_N); PLAN state=ok, demo=1, risk S7; REBUILD; READY for each of the four markets.
  A line not in the paste is 'ABSENT' (SELFTEST, written with INIT: the user was asked for the INIT line only) or 'PAS ENCORE'
  (PLAN, REBUILD, READY: the paste may predate them), never an error.
  ERROR (with what it means, check_demo.error_meaning, shared: an InpRiskTable, InpK1T or 'rule BKE' refusal is a typo in one of the two
  typed values; 'symbol ... not found'; 'another copy'), CLOCK state=wrong (unless a CLOCK state=ok follows), REFUSED, TAKEOVER, and
  MISSED (late, notready, exited, notrade, observe or settle at a start are normal, said as information) are named. When the last start
  was refused (an ERROR, then the stop line deinit=8, or no stop line yet), MetaTrader has taken the robot off the chart and F7 cannot
  reach its inputs: the advice is to relaunch it (step 6 of the guide) with the two values (review5b RH5-5); F7 stays the advice for a
  running start whose settings differ.
Output: plain French on stdout, one line per check: 'OK : ...', 'DIFFERENT : <what to tell the user>', 'PAS ENCORE : ...' or
'ABSENT : ...' (and 'INFO : ...' for what is only said), then a one-line verdict. Exit code 0 only when the paste holds a start
(INIT build=) and everything in it is OK; 1 otherwise; 2 when FILE cannot be read. Nothing is written to disk.
"""
import argparse
import os
import re
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import demo_common as C  # noqa: E402
import check_demo as D  # noqa: E402

GOLDEN_N = 366                                   # CR_Main.mqh CR_GOLDEN_N: the SELFTEST golden= of this build
_GOLDEN_RX = re.compile(r"#define CR_GOLDEN_N (\d+)")
CR_AT = re.compile(r"CR\|")
_HEAD = re.compile(r"^CR\|-?\d*\|?([A-Z0-9]*)")
# a piece of a robot line without its start: '|key=' of the robot's start lines
_FRAGMENT = re.compile(r"\|(build|version|demo|vps|tester|observer|entries_off|harness|comm_pts|risk|sleeves|S0\.75r|K1|H2|k1t|XAUUSD|US100|"
                       r"BTCUSD|ETHUSD|ok|why|golden|state|B_T|src|minutes|depth_days|deinit|bars_fed|rebuilds|what)=")
_QUOTES = "\"'`\u201c\u201d\u2018\u2019\u00ab\u00bb"
_LOG_PREFIX = re.compile(r"^\S{0,4}\t\d+\t\d\d:\d\d:\d\d")                        # a MetaTrader log line (code, severity, time)
_TAB_TIME = re.compile(r"^\s*(\d{4}\.\d\d\.\d\d\s+)?\d\d:\d\d:\d\d(\.\d+)?\s")    # the Experts tab's time column
# the prefix of the next copied line, left at the end of a robot line when the copy lost its line ends (review5b START-GLUED-PREFIX): the
# Experts tab's date and time, or a log file's code, severity and time, then the source 'ClaudeRobot (XAUUSD.r,M1)'; a robot line never
# holds a tab, a time with seconds or a '(symbol,period)' group, so the prefix is told apart from the robot's own last value
_TRAIL_PREFIX = re.compile(r"\s*(?:[A-Z]{2}\t\d+\t|(?:\d{4}\.\d\d\.\d\d[ \t]+))?\d\d:\d\d:\d\d(?:\.\d+)?[ \t]+[^\t|]{0,60}?"
                           r"\([A-Za-z0-9._#+\-]{1,24},[A-Z]{1,3}\d{0,2}\)[ \t]*$")
# the last value of a robot line as pasted (after its last '='), and the ends that show a number or a risk table cut by the chat (review6
# FV5-START-TRAILING-DIGITS): '20000:0.' then '7' is one value; '20000:0.7' then '10:02' is a value then the user's own text
_LAST_VALUE = re.compile(r"=([^|=]*)$")
_NUMERIC_VALUE = re.compile(r"^[0-9.:;eE+\- ]*$")
_CUT_END = (".", ":", ";", "e", "E", "+", "-")
_LATER_FIELD = re.compile(r"\|[A-Za-z0-9_.]+=")
SECOND_COPY = "another copy of ClaudeRobot runs on this terminal"   # OnInit (dist/ClaudeRobot.mq5): GrdLockTake failed, INIT_FAILED
RULE_OFFSETS = (7200, 10800)                     # ClkRuleOffset: server - UTC by the rule (server = New York + 7 h), the CLOCK line's rule_s
MISSED_START_OK = {"late", "notready", "exited", "notrade", "observe", "settle"}
MISSED_HINT = {"algo_trading_off": "le bouton Algo Trading est rouge : cliquer dessus pour le passer au vert",
               "no_connection": "MetaTrader n'etait pas connecte (en bas a droite) au moment de l'ordre",
               "refused": "ordre refuse par le courtier", "market_shut": "marche ferme au moment de l'ordre",
               "selftest": "l'auto-test du robot est en echec (SELFTEST ok=0)", "clock": "horloge du serveur decalee (CLOCK)",
               "margin": "pas assez de marge pour l'ordre", "min_lot": "mise plus petite que le lot minimum",
               "cap": "plafond de mise atteint", "prev_open": "une position precedente de la sleeve etait encore ouverte"}
REFUSED_HINT = {"algo_trading_off": "le bouton Algo Trading est rouge : cliquer dessus pour le passer au vert",
                "not_hedging": "le compte n'est pas en mode couverture (hedging) : il faut un compte demo Raw en hedging",
                "no_connection": "MetaTrader n'etait pas connecte au moment de l'ordre", "market_closed": "marche ferme au moment de l'ordre"}


def golden_n():
    """CR_GOLDEN_N of dist/ClaudeRobot.mq5 (the SELFTEST line's golden=), GOLDEN_N when the file cannot be read"""
    try:
        m = _GOLDEN_RX.search(open(C.DIST, encoding="ascii", errors="replace").read())
        return int(m.group(1)) if m else GOLDEN_N
    except OSError:
        return GOLDEN_N


def decode(raw):
    """the pasted text: UTF-16 (byte-order mark, or every other byte zero), UTF-8 (with or without its mark), else cp1252"""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    if len(raw) >= 4 and raw[1:2] == b"\x00" and raw[3:4] == b"\x00":
        return raw.decode("utf-16-le", errors="replace")
    if len(raw) >= 4 and raw[0:1] == b"\x00" and raw[2:3] == b"\x00":
        return raw.decode("utf-16-be", errors="replace")
    if raw[:3] == b"\xef\xbb\xbf":
        raw = raw[3:]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def parse_piece(seg):
    """a robot line as pasted (from 'CR|' on): demo_common.parse_robot_line on it, then without a closing quote or backtick the copy
    may have kept (an ERROR text may itself end with a quote, so the line is first read as it is)"""
    s = seg.strip()
    row, why = C.parse_robot_line(s)
    if row is None:
        s2 = s.rstrip(_QUOTES + " \t")
        if s2 != s:
            row2, why2 = C.parse_robot_line(s2)
            if row2 is not None:
                return row2, None
    return row, why


_ROBOT_START = re.compile(r"^CR\|-?\d")                 # a robot line starts with its stamp: CR|<utc>|<EVENT>|... (JrnAt)


def robot_like(seg):
    """a pasted piece from 'CR|' on that may be a robot line: 'CR|' then the stamp's digits, or one of the robot's fields ('|build=', '|risk=' ...);
    anything else ('CR|' in the user's words, 'CR|`', 'CR| :') is other text (review6b FV6-START-PROSE-CR-PIPE)"""
    s = seg.strip()
    return bool(_ROBOT_START.match(s) or _FRAGMENT.search(s))


def continuation(ln):
    """a pasted line that may be the rest of a robot line the chat wrapped: no 'CR|', not empty, not a MetaTrader log line or a
    line with the Experts tab's time column"""
    return bool(ln.strip()) and "CR|" not in ln and not _LOG_PREFIX.match(ln) and not _TAB_TIME.match(ln) and not ln.strip().startswith("```")


def odd_names(row):
    """how many INIT symbol names of a row show an unusual suffix (demo_common.sym_shown: '<autre suffixe ...>')"""
    return sum(1 for b in C.ROBOT_BASES if "<autre" in str(row.get(b, ""))) if row and row.get("ev") == "INIT" else 0


def join_kind(old, new, txt, cont):
    """how the next pasted line continues a robot line that already reads on its own (review6 FV5-START-TRAILING-DIGITS; review5b
    START-TRAILING-WORD for the INIT line): 'field' when it brings later fields ('|key=...'), 'cut' when the line's last value is a number or
    a risk table visibly cut ('20000:0.' then '7': it ends with '.', ':', ';', 'e', '+' or '-'), 'mend' when it mends the INIT line's last
    name ('ETHUSD.' then 'r', 'ETHUSD' then '.r'); None otherwise: a word, a time, a number or a login typed after the line is never glued
    onto its last value (the line is read alone; read_paste keeps the glued reading apart, never printed). new = the two read as one row"""
    if new is None:
        return None
    if cont.startswith("|") or (_LATER_FIELD.search(cont) and new["_raw"].count("|") > old["_raw"].count("|")):
        return "field"
    m = _LAST_VALUE.search(str(txt).strip().rstrip(_QUOTES + " \t"))
    last = m.group(1) if m else ""
    k = re.search(r"\|([A-Za-z0-9_.]+)=[^|=]*$", str(txt).strip().rstrip(_QUOTES + " \t"))
    if k and k.group(1) == "risk" and C.risk_table_ok(old.get("risk")):
        # a risk table the robot accepts as it stands, its ';' at the end included (SizParseTable: one ';' may end the list; MainInitLine and
        # MainWait write it back as typed): not visibly cut, so the next line is never glued onto it (review6b FV6-START-SEMICOLON-CUT); a
        # table the chat wrapped after a ';' ('...10000:1.4;' then '20000:0.7') is told by check() from the reading kept apart (_tail_alt)
        return None
    if last and _NUMERIC_VALUE.match(last) and last.endswith(_CUT_END):
        return "cut"
    if old.get("ev") == "INIT" and "build" in old:
        if odd_names(new) < odd_names(old):
            return "mend"
        k = re.search(r"\|([A-Z0-9]+)=[^|]*$", str(txt).strip())
        b = k.group(1) if k else None
        if b in C.ROBOT_BASES and new.get(b) == b + ".r" and old.get(b) != b + ".r":
            return "mend"
    return None


def refused_stop(x):
    """the stop line of a copy OnInit refused: INIT deinit=8 (REASON_INITFAILED) with rebuilds=0 (OnDeinit right after a failed OnInit)"""
    return x["ev"] == "INIT" and x.get("deinit") == 8 and x.get("rebuilds", 0) == 0


def live_line(x):
    """a line only a copy past OnInit's instance lock writes: its INIT build= line and every line but OnInit's (ERROR, CLOCK, TAKEOVER, INIT
    change=) and the stop lines (review6b FV6-START-LONE-SECOND-COPY: a running copy's lines without its INIT line still show it runs)"""
    return not D._oninit(x) and not (x["ev"] == "INIT" and "deinit" in x)


def second_copies(rows):
    """a second copy of the robot MetaTrader refused while the pasted start runs (review6 FV5-START-SECOND-COPY): dragged onto another chart,
    its OnInit finds the instance lock taken, writes ERROR 'another copy of ClaudeRobot runs on this terminal', returns INIT_FAILED (the EA
    is then forcibly unloaded from its chart, MQL5 documentation of OnInit) and OnDeinit writes its stop line INIT deinit=8 (REASON_INITFAILED,
    rebuilds=0) the same second. Its two lines may sit after or inside the running start's lines; they never end the running start. Such a
    copy is an ERROR after a line of a running copy (its INIT build= line or any other line it writes, review6b FV6-START-LONE-SECOND-COPY: the
    paste may hold the running copy's later lines without its INIT line) with no stop line of that copy between, or an ERROR followed, past
    OnInit lines and refused stops, by a running copy's line that is not a new INIT build= line (the user copied from the red ERROR line down).
    An ERROR followed by an INIT build= line is a start refused then relaunched (starts_of's case); one alone is the lone refused copy check()
    names (a copy runs elsewhere, not in the paste). Returns (the other rows, [(ERROR row, stop row or None)])"""
    drop, pairs = set(), []
    running = False

    def runs_after(k):
        """the first line after rows[k] that is neither an OnInit line nor a refused copy's stop line is a running copy's line, not a new start"""
        for x in rows[k + 1:]:
            if id(x) in drop or D._oninit(x) or refused_stop(x):
                continue
            return live_line(x) and not (x["ev"] == "INIT" and "build" in x)
        return False
    for k, r in enumerate(rows):
        if id(r) in drop:
            continue
        if r["ev"] == "INIT" and "deinit" in r:
            running = False                                             # the running copy's own stop line (or a refused start's)
            continue
        if live_line(r):
            running = True
            continue
        if not (r["ev"] == "ERROR" and str(r.get("what") or "") == SECOND_COPY and (running or runs_after(k))):
            continue
        cand = [x for x in rows if refused_stop(x) and id(x) not in drop and abs(int(x["utc"]) - int(r["utc"])) <= 60]
        after = [x for x in cand if rows.index(x) > k]
        stop = after[0] if after else (cand[-1] if cand else None)
        drop.add(id(r))
        if stop is not None:
            drop.add(id(stop))
        pairs.append((r, stop))
    return [r for r in rows if id(r) not in drop], pairs


def glued_after(row, txt):
    """the INIT line's last name when text was glued onto it (review5b START-TRAILING-WORD): the last field is a robot market whose name
    shows an unusual suffix that starts with '.r' (the right name, then the glued text) or is the cut '.'; the glued text is only looked
    at here, never kept or printed. Returns the market or None"""
    if not row or row.get("ev") != "INIT" or "build" not in row:
        return None
    m = re.search(r"\|([A-Z0-9]+)=([^|]*)$", str(txt).strip().rstrip(_QUOTES + " \t"))
    if not m or m.group(1) not in C.ROBOT_BASES or "<autre" not in str(row.get(m.group(1), "")):
        return None
    b, v = m.group(1), m.group(2)
    for a in sorted([b] + C.SYM_ALIASES.get(b, []), key=len, reverse=True):
        if v.startswith(a):
            suf = v[len(a):]
            return b if (suf.startswith(".r") or suf == ".") else None
    return None


def strip_trail_prefix(seg):
    """a robot line glued to the next copied line: without the next line's Experts or log prefix at its end (review5b START-GLUED-PREFIX)"""
    return _TRAIL_PREFIX.sub("", seg)


def read_paste(text, scrub):
    """the robot lines of the paste: (rows, notes) where notes = {"cut": [...], "joined": [...], "fragments": [...], "other": n,
    "dup": n}; every line is scanned for account values first"""
    text = text.replace("\ufeff", "").replace("\u00a0", " ").replace("\u202f", " ")
    lines = text.splitlines()
    for ln in lines:
        scrub.scan_log_line(ln)
    rows, cut, joined, fragments, used, seen = [], [], [], [], set(), set()
    other = dup = 0
    prev = None                                                         # [row index, its text, its last line number] of the last robot line

    def try_join(head, conts):
        """head + the first m continuation lines read as one robot line (with nothing, then a space, between the pieces): (row, text, m)"""
        for m in range(1, len(conts) + 1):
            for sep in ("", " "):
                txt = head.rstrip() + sep + sep.join(conts[:m])
                r2, _ = parse_piece(txt)
                if r2 is not None:
                    return r2, txt, m
        return None, None, 0

    def keep(row, txt, no, last_no):
        nonlocal dup, prev
        if row["_raw"] in seen:                                         # the robot stamps every line to the second: a repeat is a double paste
            dup += 1
            return
        seen.add(row["_raw"])
        row["_n"], row["_f"], row["_seq"] = no, "collage", len(rows)
        if row["ev"] == "ERROR":
            row["_pasted"] = txt                                        # never printed (error_meaning only looks for a comma)
        g = glued_after(row, txt)
        if g:
            row["_glued_after"] = g                                     # text glued onto the INIT line's last name (review5b)
        rows.append(row)
        prev = [len(rows) - 1, txt, last_no]
    for no, ln in enumerate(lines, 1):
        if no in used:
            continue
        starts = [m.start() for m in CR_AT.finditer(ln)]
        if not starts:
            if prev is not None and prev[2] == no - 1 and continuation(ln):
                # the end of the line above, wrapped where the line above already read as a robot line: kept only when it brings later
                # fields, when the line's last value is visibly cut, or when it mends the INIT line's last name (join_kind); a word, a time,
                # a number or a login typed after the line is never glued onto it (review5b START-TRAILING-WORD, review6
                # FV5-START-TRAILING-DIGITS). When the two would read as one row all the same, that reading is kept apart (_tail_alt):
                # check() looks at it only to tell a wrapped SELFTEST or PLAN line, and never prints it
                r2, txt, _ = try_join(prev[1], [ln.strip()])
                old = rows[prev[0]]
                if r2 is not None and join_kind(old, r2, prev[1], ln.strip()) is None:
                    old["_tail_alt"], old["_tail_no"] = r2, no
                    r2 = None
                if r2 is not None:
                    seen.discard(old["_raw"])
                    r2["_n"], r2["_f"], r2["_seq"] = old["_n"], "collage", old["_seq"]
                    if r2["ev"] == "ERROR":
                        r2["_pasted"] = txt
                    g = glued_after(r2, txt)
                    if g:
                        r2["_glued_after"] = g
                    rows[prev[0]] = r2
                    seen.add(r2["_raw"])
                    joined.append((old["_n"], no - old["_n"] + 1, r2["ev"]))
                    prev = [prev[0], txt, no]
                    continue
            if _FRAGMENT.search(ln):
                fragments.append(no)
            elif ln.strip() and not ln.strip().startswith("```"):
                other += 1
            continue
        pieces = [ln[a:b] for a, b in zip(starts, starts[1:] + [len(ln)])]
        for j, seg in enumerate(pieces):
            if j < len(pieces) - 1:
                seg = strip_trail_prefix(seg)                           # the next line's prefix, when the copy lost its line ends
            row, why = parse_piece(seg)
            txt, last_no = seg, no
            if row is None and j == len(pieces) - 1:
                # a line the chat wrapped: the next lines (no 'CR|') may be its end; kept only when the whole reads as one robot line
                conts = []
                for k in range(no + 1, min(no + 6, len(lines) + 1)):
                    if not continuation(lines[k - 1]):
                        break
                    conts.append(lines[k - 1].strip())
                row, txt2, m = try_join(seg, conts)
                if row is not None:
                    txt, last_no = txt2, no + m
                    used.update(range(no + 1, no + 1 + m))
                    joined.append((no, m + 1, row["ev"]))
                elif robot_like(seg):
                    used.update(range(no + 1, no + 1 + len(conts)))      # the rest of the cut line: not a second problem
            if row is None and not robot_like(seg):
                # 'CR|' in the user's own words (the guide says 'Les lignes du robot commencent par CR|'): not a robot line, other text, never
                # printed (review6b FV6-START-PROSE-CR-PIPE); the lines after it are read on their own (a piece of a robot line is still flagged)
                other += 1
                prev = None
                continue
            if row is None:
                hm = _HEAD.match(seg.strip())
                ev = hm.group(1) if hm and hm.group(1) in C.SCHEMA else None
                cut.append({"line": no, "ev": ev, "why": why})
                prev = None
                continue
            keep(row, txt, no, last_no if j == len(pieces) - 1 else -1)
    # the Experts tab lists the oldest line first; a paste in the other order is put back in write order
    if len(rows) > 1 and rows[0]["utc"] > rows[-1]["utc"]:
        rows.reverse()
    return rows, {"cut": cut, "joined": joined, "fragments": fragments, "other": other, "dup": dup}


def when_txt(u):
    """a start time as the user sees it on the Mac (Paris), with the server's time"""
    return C.paris_when(u)


def error_meaning(r, raw_text="", relaunch=False):
    """what an ERROR line means for the user: check_demo.error_meaning (shared, so that the two tools say the same)"""
    return D.error_meaning(r, raw_text, relaunch)


def check(rows, notes, builds):
    """the lines to print and the verdict: (lines, exit code)"""
    out, bad, later, absent = [], [], [], []

    def say(tag, txt):
        out.append(f"{tag} : {txt}")
        if tag == "DIFFERENT":
            bad.append(txt)
        elif tag == "PAS ENCORE":
            later.append(txt)
        elif tag == "ABSENT":
            absent.append(txt)
    evs = {}
    for r in rows:
        e = "INIT (arret)" if r["ev"] == "INIT" and "deinit" in r else r["ev"]
        evs[e] = evs.get(e, 0) + 1
    out.append("Demarrage du robot : verification du collage de l'onglet Experts.")
    out.append(f"Lignes du robot lues : {len(rows)}" + (f" ({', '.join(f'{e} x{n}' if n > 1 else e for e, n in evs.items())})" if rows else "")
               + f" ; autres lignes : {notes['other']} (jamais recopiees)" + (f" ; {notes['dup']} ligne(s) collee(s) deux fois" if notes["dup"] else "") + ".")
    for c in notes["cut"]:
        say("DIFFERENT", f"ligne {c['ev'] or 'du robot'} (ligne {c['line']} du collage) : ligne coupee : demander de la recopier (clic droit sur "
                         "la ligne dans l'onglet Experts, Copier, puis tout coller)" + (f" [{c['why']}]" if c.get("why") else ""))
    for no in notes["fragments"]:
        say("DIFFERENT", f"ligne {no} du collage : morceau de ligne du robot sans son debut (CR|...) : ligne coupee : demander de la recopier")
    for no, n, ev in notes["joined"]:
        out.append(f"INFO : ligne {ev} coupee sur {n} lignes par le collage (ligne {no}), recollee pour la verifier")
    # a second copy MetaTrader refused while the pasted start runs (review6 FV5-START-SECOND-COPY): set apart, it never ends the running start
    rows, copies = second_copies(rows)
    starts = D.starts_of(rows) if rows else []
    # the earlier starts: named, the last one decides
    for k, s in enumerate(starts[:-1]):
        out.append("INFO : " + start_story(s, rows, k + 1, builds) + " ; remplace par le demarrage suivant")
    last = starts[-1] if starts else None
    i = (last or {}).get("init")
    mine = [r for r in rows if last is not None and r.get("_si") == len(starts) - 1]
    errors = [r for r in mine if r["ev"] == "ERROR"]
    # the running copy stopped after the second copy was refused (its stop line comes later in the paste): the refused copy's lines are then
    # no reason to leave the robot as it is (the guide's 'relance le robot' applies again)
    stopped = bool(copies) and last is not None and bool(last.get("deinit")) and last["deinit"].get("deinit") != 8 \
        and int(last["deinit"]["utc"]) >= max(int(e["utc"]) for e, _ in copies)
    if i is None:
        # the lone refused copy (review6b FV6-START-LONE-SECOND-COPY): only its ERROR 'another copy' (and its stop line) in the paste. GrdLockTake
        # refuses only a lock another copy refreshed less than 10 s before (CR_GRD_LOCK_STALE_MS): a copy runs on another chart of this terminal,
        # and MetaTrader unloaded the new one (INIT_FAILED): remove nothing; the INIT line of the copy that runs is what is checked
        lone = bool(errors) and all(str(e.get("what") or "") == SECOND_COPY for e in errors)
        if last is not None and last.get("deinit"):
            dn = last["deinit"].get("deinit")
            out.append("INFO : ligne d'arret " + ("de la nouvelle copie, refusee" if lone else "du robot")
                       + f" (INIT deinit={dn} : {D.DEINIT_FR.get(dn, 'raison inconnue')}) : ce n'est pas la ligne de demarrage")
        # a refused start (ERROR, then the stop line deinit=8, or no stop line yet): MetaTrader took the robot off the chart, so F7 cannot reach
        # its inputs: relaunch it with the two values (review5b RH5-5)
        refused = bool(errors) and (bool(last.get("refused")) or not last.get("deinit") or last["deinit"].get("deinit") == 8)
        name_errors(errors, say, out, relaunch=refused)
        out += copies_info(copies, stopped)
        say("ABSENT", "INIT : pas de ligne de demarrage (INIT avec build=) dans le collage"
            + (" : demander celle de la copie qui tourne (voir la ligne ERROR)" if lone else
               (" : le robot n'a pas demarre (voir la ligne ERROR)" if errors else " : demander a l'utilisateur de copier la ligne INIT qui "
                "contient build= (clic droit, Copier)")))
        return finish(out, bad, later, absent, started=False, copies=copies if not stopped else (), lone=lone)
    out.append(f"Demarrage verifie : {when_txt(last['utc'])}.")
    year = time.gmtime(int(last["utc"])).tm_year
    items = D.start_settings(i, len(starts), C.utc_txt(last["utc"]), {year}, builds)
    by_group = {}
    for it in items:
        by_group.setdefault(it["group"], []).append(it)
    ga = i.get("_glued_after")
    for it in items:
        if ga and it["key"] == f"sym:{ga}" and not it["ok"]:
            # text glued onto the INIT line's last name (review5b START-TRAILING-WORD): the name cannot be read, it is not another market
            it["say"] = (f"texte colle apres la ligne INIT (apres {ga}.r, sans retour a la ligne) : demander de la recopier (clic droit sur la ligne "
                         "dans l'onglet Experts, Copier, puis la coller seule)")
    for g in ("build", "demo", "where", "risk", "sleeves", "switch", "k1t", "sym"):
        its = by_group.get(g, [])
        if g in ("sym", "switch") and its and all(it["ok"] for it in its):
            say("OK", {"sym": "marches " + ", ".join(it["label"] for it in its),
                       "switch": "interrupteurs " + ", ".join(it["key"].split(":")[1] for it in its) + " en marche (InpK1, InpH2, InpS075 a -1)"}[g])
            continue
        for it in its:
            if it["ok"]:
                say("OK", it["label"])
            else:
                say("DIFFERENT", it["say"])
    if i.get("K1") == "on" and not by_group.get("k1t"):
        out.append(f"INFO : pas de seuil K1 du labo pour {year} : InpK1T non verifie")
    # SELFTEST, PLAN, REBUILD, READY
    st = last.get("selftest")
    gn = golden_n()
    if st is None:
        say("ABSENT", "SELFTEST (ecrite avec INIT : pas dans le collage ; regarder la capture)")
    elif st.get("ok") != 1:
        say("DIFFERENT", f"SELFTEST ok=0 ({st.get('why') or 'raison vide'}) : le robot se bloque lui-meme, il ne tradera pas ; envoyer une "
                         "capture de l'onglet Experts, laisser le robot en place")
    elif st.get("golden") not in (None, gn):
        alt = st.get("_tail_alt") or {}
        if alt.get("ok") == 1 and alt.get("golden") == gn:
            # golden=36 then '6' on the next line: the line wrapped by the chat (review6 FV5-START-TRAILING-DIGITS)
            out.append(f"INFO : ligne SELFTEST coupee sur 2 lignes par le collage (ligne {st['_n']}), recollee pour la verifier")
            say("OK", f"SELFTEST ok=1 ({gn} vecteurs)")
        elif alt or str(st.get("golden")).startswith(str(gn)):
            # text glued after golden=366 (on the line, or a number on the next line that may end it): its value is not the robot's alone,
            # never printed (review6 FV5-START-TRAILING-DIGITS)
            say("DIFFERENT", f"ligne SELFTEST (ligne {st['_n']} du collage) : texte colle apres la ligne, ou ligne coupee : demander de la recopier "
                             "(clic droit sur la ligne dans l'onglet Experts, Copier, puis la coller seule)")
        else:
            say("DIFFERENT", f"SELFTEST golden={st.get('golden')} au lieu de {gn} : pas le fichier envoye ; refaire les etapes 1 et 2 du guide")
    else:
        say("OK", f"SELFTEST ok=1 ({st.get('golden', '?')} vecteurs)")
    plan = last.get("plan")
    src = [r for r in mine if r["ev"] == "PLAN" and r.get("src") == "first_deal"]
    if plan is None:
        say("PAS ENCORE", "PLAN (ecrite quand MetaTrader est connecte ; le collage a pu etre fait avant)")
    else:
        pb = []
        if plan.get("state") == "unset":
            pb.append("plan non regle (state=unset : compte reel sans InpPlanStart) : aucune entree")
        elif plan.get("state") == "future":
            T = plan.get("T")
            pb.append(f"plan pas encore en vigueur (state=future, InpPlanStart = {C.ymdhm(T) if isinstance(T, int) else '?'} serveur) : aucune "
                      f"entree avant ; {D.GUIDE_F7}, InpPlanStart = 0 (1970.01.01 00:00), OK")
        if plan.get("demo") != 1:
            pb.append("PLAN demo=0 : compte reel")
        # the PLAN line ends with the risk table, the same text as the INIT line's (MainWait and MainInitLine both write g_cfg.risk_table): a
        # value that differs is text glued after the line or a line cut, never printed; the next line glued on (_tail_alt) is taken only
        # when it gives the INIT line's table, a line the chat wrapped (review6 FV5-START-TRAILING-DIGITS)
        same_risk = lambda a: a is not None and i.get("risk") is not None and str(a).strip() == str(i.get("risk")).strip()  # noqa: E731
        if not C.risk_table_ok(i.get("risk")):
            # the INIT line itself is to be copied again (start_settings): the PLAN line's table is judged on its own
            if C.risk_preset(plan.get("risk")) != C.RISK_EXPECTED:      # its value is not printed: nothing vouches for it here
                pb.append(f"ligne PLAN (ligne {plan['_n']} du collage) : mise qui n'est pas S7, ou illisible : demander de la recopier avec la "
                          "ligne INIT")
        elif not same_risk(plan.get("risk")) and same_risk((plan.get("_tail_alt") or {}).get("risk")):
            out.append(f"INFO : ligne PLAN coupee sur 2 lignes par le collage (ligne {plan['_n']}), recollee pour la verifier")
        elif not same_risk(plan.get("risk")):
            pb.append(f"ligne PLAN (ligne {plan['_n']} du collage) : sa mise n'est pas celle de la ligne INIT : texte colle apres la ligne, ou "
                      "ligne coupee : demander de la recopier (clic droit sur la ligne dans l'onglet Experts, Copier, puis la coller seule)")
        if (same_risk(plan.get("risk")) or same_risk((plan.get("_tail_alt") or {}).get("risk"))) and C.risk_preset(i.get("risk")) != C.RISK_EXPECTED:
            pb.append(f"PLAN : mise {C.risk_shown(i.get('risk'))} au lieu de S7 (meme cause que la ligne INIT)")
        for x in pb:
            say("DIFFERENT", x)
        if not pb:
            say("OK", "PLAN state=ok, compte demo, mise S7" + (" ; PLAN src=first_deal avant : le plan part de la premiere transaction du "
                                                               "compte, normal sur la demo" if src else ""))
    if last.get("rebuilds"):
        say("OK", "REBUILD (historique relu)")
    else:
        say("PAS ENCORE", "REBUILD (juste apres PLAN)")
    for b in C.ROBOT_BASES:
        if b in last.get("ready", {}):
            say("OK", f"READY {b}")
        else:
            nr = last.get("notready", {}).get(b) or []
            say("PAS ENCORE", f"READY {b}" + (f" (NOTREADY {nr[-1].get('why')} : MetaTrader charge l'historique, jusqu'a 15 min la premiere fois)"
                                             if nr else " (le collage a pu etre fait avant ; regarder la capture)"))
    # the lines that need a look
    name_errors(errors, say, out, relaunch=bool(last.get("refused")) or (bool(errors) and (last.get("deinit") or {}).get("deinit") == 8))
    out += copies_info(copies, stopped)
    clocks = [r for r in mine if r["ev"] == "CLOCK"]
    for k, r in enumerate(clocks):
        if r.get("state") in ("wrong", "flat"):
            fixed = any(x.get("state") == "ok" for x in clocks[k + 1:])
            # rule_s, the line's last value, is 7200 or 10800 (ClkRuleOffset): any other value is text glued after the line, never printed
            # (review6 FV5-START-TRAILING-DIGITS)
            txt = (f"CLOCK state={r.get('state')} (serveur - GMT mesure {r.get('measured_s')} s au lieu de {r.get('rule_s')} s)"
                   if r.get("rule_s") in RULE_OFFSETS else
                   f"CLOCK state={r.get('state')} (ligne {r['_n']} du collage : texte colle apres la ligne ? demander de la recopier)")
            if fixed:
                out.append(f"INFO : {txt}, puis CLOCK state=ok : rien a faire")
            else:
                say("DIFFERENT", f"{txt} : le robot n'entre pas tant que l'horloge est fausse ; si aucune ligne CLOCK state=ok ne suit dans les "
                                 "minutes, l'heure du Mac est fausse : activer 'Regler la date et l'heure automatiquement', puis redemarrer "
                                 "MetaTrader")
    for r in [x for x in mine if x["ev"] == "REFUSED"]:
        say("DIFFERENT", f"REFUSED {r['code']} why={r.get('why')} : " + REFUSED_HINT.get(r.get("why"), "ordre refuse : capture de l'onglet Experts"))
    for r in [x for x in mine if x["ev"] == "TAKEOVER"]:
        say("DIFFERENT", "TAKEOVER : une autre copie du robot tournait sur ce compte et ne repondait plus : un seul graphique doit porter le robot")
    for r in [x for x in mine if x["ev"] == "MISSED"]:
        reason = str(r.get("reason"))
        if reason in MISSED_START_OK:
            out.append(f"INFO : MISSED {r['code']} reason={reason} : normal au demarrage (trade papier deja ouvert ou fini)")
        else:
            say("DIFFERENT", missed_txt(r))
    if last.get("deinit"):
        dn = last["deinit"].get("deinit")
        say("DIFFERENT", f"le collage finit par l'arret du robot (INIT deinit={dn} : {D.DEINIT_FR.get(dn, 'raison inconnue')}) : demander la "
                         "ligne INIT du redemarrage (ou relancer le robot, etape 6 du guide)")
    return finish(out, bad, later, absent, started=True, copies=copies if not stopped else ())


RECOPY_ALONE = "demander de la recopier (clic droit sur la ligne dans l'onglet Experts, Copier, puis la coller seule)"


def missed_txt(r):
    """a MISSED line as check_start says it (review6b FV6-START-MISSED-GLUED-DIGITS). Its reason is the line's last field (FolMissedTxt writes
    KV("reason", ...) last on a live line), so text typed right after the line lands in it, and the schema takes any digits after 'refused_'
    (FolIntentStep: 'refused_' + the broker's retcode) or 'code' (SizSkipName: 'code' + k for a reason outside its list). Only the robot's own
    words are printed: a word of its lists, 'refused_<rc>' when rc is one of MetaTrader's trade server return codes (demo_common.TRADE_RETCODES,
    MQL5 documentation), with its meaning when check_demo knows it. Other digits after 'refused_', and any after 'code' (this build's reasons
    are all in SizSkipName's list), are never printed: the line is to be copied again"""
    reason, code = str(r.get("reason")), r["code"]
    m = re.match(r"^refused_(\d+)$", reason)
    if m:
        rc = int(m.group(1))
        if rc in C.TRADE_RETCODES:
            mean = D.CLOSE_RC_FR.get(rc)
            return f"MISSED {code} reason={reason} : ordre refuse par le courtier ({rc}" + (f" : {mean})" if mean else ")")
        return (f"MISSED {code} reason=refused_<...> (ligne {r['_n']} du collage) : ordre refuse par le courtier, mais le nombre qui suit n'est pas "
                f"un code de MetaTrader : texte colle apres la ligne ? {RECOPY_ALONE}")
    if re.match(r"^code-?\d+$", reason):
        return (f"MISSED {code} reason=code<...> (ligne {r['_n']} du collage) : raison hors de la liste du robot : texte colle apres la ligne ? "
                f"{RECOPY_ALONE} ; si elle revient pareille : capture de l'onglet Experts")
    return f"MISSED {code} reason={reason} : " + MISSED_HINT.get(reason, "trade non envoye : capture de l'onglet Experts")


def copies_info(copies, stopped=False):
    """one INFO line per second copy MetaTrader refused while the pasted start ran (review6 FV5-START-SECOND-COPY): nothing to correct; the
    guide's 'relance le robot' after an ERROR does not apply to it (the copy that runs carries on). stopped: the paste ends with the stop line
    of the copy that ran (review6b: it was stopped after the refusal, so the line says no more than the refusal)"""
    return [f"INFO : deuxieme copie du robot refusee {when_txt(e['utc'])} (ERROR {SECOND_COPY}" + (", puis sa ligne d'arret deinit=8" if stop else "")
            + ") : MetaTrader l'a retiree de son graphique"
            + (" ; la copie qui tournait a ete arretee ensuite (voir sa ligne d'arret)" if stopped else
               " ; la copie qui tourne continue : ne pas relancer le robot") for e, stop in copies]


def error_cause(r):
    """the cause of an ERROR line: InpK1T refused and 'rule BKE: Init refused its configuration' are one typo in InpK1T"""
    w = str(r.get("what") or "")
    return "InpK1T" if w.startswith(("InpK1T refused", "rule BKE:")) else ("InpRiskTable" if w.startswith("InpRiskTable") else w)


def name_errors(errors, say, out, relaunch=False):
    """each ERROR line with what it means; a second line with the same cause (InpK1T refused, then 'rule BKE: Init refused its
    configuration') is said as information. relaunch: the start was refused, the robot left the chart (review5b RH5-5)"""
    said = set()
    for r in errors:
        c = error_cause(r)
        if c in said:
            out.append(f"INFO : ERROR {r['what']} : meme cause que la ligne ERROR precedente")
            continue
        said.add(c)
        say("DIFFERENT", f"ERROR {r['what']} : {error_meaning(r, raw_of(r), relaunch)}")


def raw_of(r):
    """an ERROR line as pasted (kept apart, never printed: its echo of the input may hold anything), only to see whether a comma was
    typed in InpRiskTable"""
    return r.get("_pasted") or ""


def start_story(s, rows, n, builds):
    """one earlier start in a few words: when, what was different, how it ended"""
    i = s.get("init")
    if i is None:
        er = [r for r in rows if r.get("_si") == n - 1 and r["ev"] == "ERROR"]
        txt = f"demarrage {n} " + (f"en echec ({error_meaning(er[0], raw_of(er[0])).split(' :')[0]})" if er else "sans ligne INIT")
    else:
        year = time.gmtime(int(s["utc"])).tm_year
        diff = [it["say"].split(" ;")[0].split(" :")[0] for it in D.start_settings(i, n, C.utc_txt(s["utc"]), {year}, builds) if not it["ok"]]
        txt = f"demarrage {n} {when_txt(s['utc'])}" + (f" (different : {' ; '.join(diff[:4])})" if diff else " (reglages bons)")
    if s.get("deinit"):
        dn = s["deinit"].get("deinit")
        txt += f", arrete (deinit={dn} : {D.DEINIT_FR.get(dn, 'raison inconnue')})"
    return txt


def finish(out, bad, later, absent, started, copies=(), lone=False):
    """the verdict line and the exit code; copies = second copies MetaTrader refused while the start ran (review6 FV5-START-SECOND-COPY): the
    verdict says what to tell the user, since the guide's advice after an ERROR line (remove the robot from the other chart, relaunch it) does
    not apply to them. lone = the paste holds only a copy refused because another copy runs (review6b FV6-START-LONE-SECOND-COPY): nothing
    was checked (exit code 1), and the verdict asks for the INIT line of the copy that runs, removing nothing"""
    sec = (" ; deuxieme copie refusee par MetaTrader (retiree de son graphique) : dire a l'utilisateur de ne pas relancer le robot ni de "
           "l'enlever du graphique ou il tourne") if copies else ""
    if lone and len(bad) == 1:
        out.append("Verdict : rien a verifier : une copie du robot tourne deja sur un autre graphique de ce MetaTrader et MetaTrader a refuse la "
                   "nouvelle : dire a l'utilisateur de ne rien enlever ni relancer, et lui demander la ligne INIT (avec build=) de la copie qui "
                   "tourne, pour verifier ses reglages")
        return out, 1
    if bad:
        out.append(f"Verdict : a corriger ({len(bad)} point(s)) : {bad[0]}" + (" ; et les autres points DIFFERENT ci-dessus" if len(bad) > 1 else "")
                   + sec)
        return out, 1
    if not started:
        out.append("Verdict : rien a verifier : il faut la ligne INIT " + ("(avec build=) de la copie qui tourne" if copies else "du demarrage (avec build=)")
                   + sec)
        return out, 1
    txt = "Verdict : demarrage conforme : tout ce que montre le collage est bon"
    if absent or later:
        txt += " ; pas dans le collage : " + ", ".join(x.split(" (")[0] for x in absent + later) + " (regarder la capture)"
    out.append(txt + sec + ".")
    return out, 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("file", help="le texte colle par l'utilisateur, enregistre tel quel")
    a = ap.parse_args(argv)
    scrub = C.Scrubber()
    try:
        raw = open(a.file, "rb").read()
    except OSError as e:
        print(f"fichier illisible ({e.__class__.__name__})")
        return 2
    C.warn_if_in_repo([a.file])
    rows, notes = read_paste(decode(raw), scrub)
    lines, rc = check(rows, notes, C.known_builds())
    print(scrub.text("\n".join(lines)))
    return rc


if __name__ == "__main__":
    sys.exit(main())
