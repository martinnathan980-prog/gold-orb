"""Self-tests of the demo tools (read_mac_files.py and check_demo.py), end to end.

    python3 -I lab/robot/demo/test_demo_tools.py [--quick] [--keep]

Not named test_*.py under check/, so the robot's suite (check/run_tests.py) never runs it. It writes small inputs in
the exact formats the MQL5 sources write them (the header lines and the INTROUVABLE line are read from ReleveFP.mq5 and
SondeFP.mq5 themselves; numbers with DoubleToString's decimals; days newest first in the m1 files; line ends both
"\\n" and "\\r\\n"), runs each tool on them and checks the outputs.

Data: in-sample bars only, the 2021 bar files already exported under lab/robot/check/out/bars/ (read-only; weeks of
June-December 2021). The fake account's server name, login, holder's name and user folder are planted in the inputs
(MetaTrader's own logs, a terminal line glued in a robot file) and must never appear in any output. Every output goes
to the session scratchpad; scratch is deleted at the end unless --keep.
The cases of the adversarial review are the tests named 'review ...': hand-made multi-day journals (a lost daily file,
a second ticket for one paper trade, a missing or refused CLOSE, the CLOSE px=0 race, MetaTrader's logs beside the
robot's files, the plan started at the go-live time), ReleveFP files (a weekend run after an early holiday close,
holiday windows for InpExtraClosures, the probe's cents, a cut fiche line, 3-digit gold) and replays (a lost file,
the coverage of 30 days of minutes, a market whose minutes start late, a day whose spread differs, a clean trading
run without a false alarm).
The cases of the second review are the tests named 'review2 ...' (N1-N10): one journal line lost (DEC, PFILL, FILL,
SEND, PEXIT) and the verdict when not every sleeve was compared; exits at the broker's stop left out of the averages;
an Experts log of one day; ReleveFP 1.10 (sp_min, the terminal's own M1 bars r1_<BASE>.csv, barres= in fini.txt) and
1.00 files; the last daily file lost; account words glued to robot lines; unreadable values and a fuzz of cut and
glued lines; the live period, a CLOCK line before INIT, a market whose minutes start late, minutes taken before the
demo, late-by-design entries; a cut gold fiche and a cut m1 file; a CLOSE without price whose minutes never reach the
stop. 'review2 control ...' checks guard against false alarms (they pass on the tools before the fix too).
The cases of the third review are the tests named 'review3 ...' (with the reviewers' ids): a reconnection (REBUILD
why=reconnect) and the money estimate's holes (files of the start lost, the 30-day purge, a lost last file, positions
closed without their opening), time fields out of range and long digit runs, lost SLMOD lines (a trailing stop), a lost
SIZE, AGG or DAY line and lines counted once, lost INIT, deinit or REBUILD lines of a restart, the headline's euros
(late entries said, closes for another reason apart, money in words), a duplicated day file, a file cut in its last line,
the gold stop estimate commission included, races and stops after the paper's exit, unreadable DAY lines and releve files,
check_demo reading fini.txt, the scrubber and the schema (numbers, French words, free text, duplicated keys); tool 1 on
r1 files measured in calendar days, empty or short r1 files, Max bars, files ReleveFP could not write, m1 files not
copied, the version as text, files re-saved by a spreadsheet, fini integers and lines ReleveFP never writes; ReleveFP.mq5
itself run against lab/robot/demo/releve_mock/ (r1 for the robot's markets only, the minutes first, a loading series, a
weekend run, a failing last call); and, with the replay, a disconnection over a paper line and a market set aside alone.
The cases of the fourth review are the tests named 'review4 ...' (with the reviewers' ids A1-A14 and RC3-...): the terminal's
bars (r1) against the robot's own depth (the replay is READY only 60 days after the first bar of US100, BTCUSD, ETHUSD: ReleveFP's
default becomes 100 days, R1_DAYS_NEEDED and the advice count it, SIZE and MISSED are compared from the replay's READY), the demo's
settings (S7, ALL, demo, .r names, switches, a plan still to come), execution costs against the lab's (x1.5), refused stop moves,
balance moves from outside the robot (a deposit, a hand trade, a payment), a bar spread of 0 or below the ticks', r1 bars not
synchronized or with days missing, an observer restarted with another risk table, the money window, times out of range, a printed
copy without INIT or from the VPS, symbol suffixes, reconnections (a line written during the outage, a sizing skip restated, the
outage said), a first start purged before a restart, a stop on the tick grid, and values that divide by zero. The hand-made journals
use S7 and a balance that follows their trades since review4 (the checks of A4 and A7 would flag the earlier D2 and flat balances).
The cases of the fourth review's second round are the tests named 'review4b ...' (the verifiers' ids R4V-1..6 and ADV5-1..14): a plan
start hours after the first start (SIZE observe with B = P_in = 0), execution costs under the timing noise of real orders (small
journals of noisy trades), a swap credit, the wording of r1 spans, READY and B(T), a printed VPS copy whose lines differ (no traceback),
printed logs file by file (an earlier run, purged days, a lost restart file, a day of other programs' prints only), ORPHAN at a
reconcile, InpK1T on a 2026 demo, fini.txt's server_time one digit too long, fini.txt absent, Max bars and stopped=1, fiches.csv absent,
a CLOSE cut at the end of its file, the money check's limit said, a releve row with a negative price, a time exit after the releve's last
bar, a login glued onto a counter; and with the replay, the Mac asleep (the process frozen, then a catch-up at the wake), built against
the self-test's own copy of the harness with MOCK_SLEEP (check/ itself is never changed).
The cases of the fifth review are the tests named 'review5 ...': START, check_start.py on the start's lines the user pastes into the chat
(the Experts tab copied with right-click -> Copy, the account planted around them): the right settings, the INIT line alone, D2 left, a comma
in the risk table, InpK1T empty or 2026:417 or with a three-digit exponent, a name without .r, a real account, an older build, the stop line
only, ERROR lines only, two starts, a cut line, a wrapped line, UTF-16, quotes and a byte-order mark, spaces around InpRiskTable, CLOCK,
SELFTEST ok=0, an observer copy, markets not READY yet, the agreement with check_demo on the same start and, with the harness, the release
file's own start lines; FV4b-1, the Mac's Experts logs cut by its local date (printed_files: Paris = server - 1 h, - 2 h in the weeks when
Paris and New York have not both changed clocks) with a lost middle day, a lost restart day, two lost days, a lost last file with and without
--bars, across the end of October and of March; FV4b-2, two logs of the same name from two folders; FV4b-3 (with the replay), a US100 row
of the releve with a negative low and the NQB differences it causes days later; FV4b-4, a hand gain just under and just over the threshold
the report prints; MAC-ZIP, trees laid out like an extracted Finder zip (with __MACOSX, with AppleDouble files beside the files, without them)
given to both tools. The review4b printed cases use printed_files too (review5: the logs cut by the Mac's local date, as MetaTrader cuts them;
before review5 they were cut by the server day of the journal files, which hid FV4b-1).
The cases of the fifth round's second pass are the tests named 'review5b ...' (the verifiers' ids), on journals of the user's November 2026 demo
built by story_journal (starts, refused starts, stops, positions adopted across a stop, refused closes, positions open at the copy): check_start.py
with one chat word after the INIT line (START-TRAILING-WORD), the start lines glued with the Experts prefix between them (START-GLUED-PREFIX), a
refused last start (RH5-5: relaunch, not F7); check_demo with a start OnInit refused then the relaunch, and alone (RH5-1, with check_start's
verdict on the same lines), a start replaced by a later one, with and without real trades (RH5-2), an observer copy during the demo
(OBSERVER-NORMAL), a restart in a lost daily file seen in the Experts logs (PRINTED-RESTART-UNCHECKED, md_journal 'restart_d2'), a close or
stop moves in a lost file (LOST-FILE-POSITIONS), closes refused with Algo Trading off (RH5-3), the copy taken while the robot runs and --copie
(RH5-4), a paper trade while MetaTrader was closed (RH5-6), a position closed while the robot was stopped and the balance difference (RH5-7), the
Mac asleep (RH5-8), a position open at the copy (RH5-9) and the Paris times on stdout (RH5-10).
The cases of the sixth round are the tests named 'review6 ...' (the final verifier's ids FV5-...): check_start.py with a time, a number, a dot or
the login typed alone on the line after a PLAN, SELFTEST or CLOCK line, or glued on that line, and an INIT line whose risk table holds the login
(FV5-START-TRAILING-DIGITS; lines the chat really wrapped inside their last value as controls), a second copy MetaTrader refused while the start
runs, its two lines after or among the start's lines (FV5-START-SECOND-COPY); check_demo on story_journal's November 2026 journals with a D2 demo
restarted with the same settings, also with the restart's daily file lost, without and with the Mac's Experts logs (FV5-RH5-2-SAME-SETTINGS-RESTART),
a lost daily file whose trades lost money (FV5-RH5-7-LOST-FILE-COST), --copie a few minutes after the server's midnight (FV5-COPIE-MIDNIGHT), and the
start numbers after refused starts and with a restart seen only in the Experts tab (FV5-START-NUMBERING).
The cases of the sixth round's second pass are the tests named 'review6b ...' (the verifier's ids FV6-...): check_start.py with the login glued
right after a MISSED line whose reason is refused_<rc> or code<k> (FV6-START-MISSED-GLUED-DIGITS), a paste holding only the lines of a second copy
MetaTrader refused, with or without lines of the copy that runs (FV6-START-LONE-SECOND-COPY), a risk table typed with the ';' the robot accepts at
its end, then a time, the login or '0' on the next chat line (FV6-START-SEMICOLON-CUT), 'CR|' in the user's own words (FV6-START-PROSE-CR-PIPE);
check_demo with a restart inside a lost daily file before the start in force, with and without the Mac's Experts logs
(FV6-DEMO-UNKNOWN-RESTART-ADVICE), and a second copy refused while the robot runs, in the Experts log of a day kept or lost
(FV6-DEMO-PRINTED-SECOND-COPY, insert_printed).
The cases of the seventh round are the tests named 'deals ...' (ReleveFP 1.11 writes the account's deals and open positions, ids RELEVE-111, TOOL1,
TOOL2): ReleveFP.mq5 1.11 itself, translated and built against releve_mock, run on story_journal accounts (story_history: the opening deposit and each
trade's deals, agreeing with the journal by construction) and on the harness's own account (harness_history: check/mock_replay.h's _mock/deals.csv
and state.txt, a deposit first, MetaTrader's magic 0 for the harness's hand trades, the deals' stops from the journal); check_demo with --deals or
deals.csv beside --bars, read_mac_files on a releve folder holding the deals (merge_deals). Faults: the broker's stops slipping 1x (no alarm), 3x and
10x the lab's (MOCK_SLIP_STOP_BPS), the gold commission twice the lab's (MOCK_COMM, and edited deals), a triple swap charged on a Wednesday night
(crypto: the lab triples on Friday; gold, the lab's own triple day: no anomaly), a trade by hand, a deposit, a robot deal the journal does not know, a CLOSE line lost whose deal
exists, a position still open at the run and the same missing from positions.csv, a deals.csv row with an extra field (the holder's name glued), a
1.11 folder without deals.csv, erreur_deals, an empty history, a 1.10 folder (both tools unchanged: controls), the account's words planted in the
deals' comments and external ids (never in any output). DAY balances are moved with the deals the tests add (shift_balances).
The cases of the deals stage's second pass are the tests named 'deals2 ...' (review8, the verifiers' ids): releve_mock now follows the documented
MetaTrader (FileWriteString adds a CR before a bare LF of a TXT or CSV file and returns the bytes written, the deal getters answer for the deals
HistorySelect listed, SymbolInfoInteger may fail with 4302, FileOpen and FileWriteString fail on demand, the account plants a server, company,
holder's name and login), checked by a C++ probe; ReleveFP 1.11 writes every row ending in CR LF and counts them (RELEVE111-CRLF), the first 1.11
rebuilt (rows ending in a bare LF, WriteRow with ==) fails as the documentation predicts and both tools then say plainly that ReleveFP could not write
the history (IMIT-CRLF, TOOL2-FINI-COUNTS-IGNORED); deals.csv or positions.csv that cannot be opened (OPEN-FAIL-UNTESTED), a failed write without its
own code after an unknown symbol (LASTERR-STALE), the planted account in no file (IMIT-LOOSE); tool 1: a withdrawal named 'retrait', trades by hand
or of another program closed before the robot's first trade INFO, a deposit on the Sunday before the first trade DIFFERENT, ReleveFP 1.11 expected
(a 1.10 folder DIFFERENT), a robot position closed by hand DIFFERENT; check_demo: positions=-1 with positions.csv's header only, deals.csv cut after
4 of 9 rows, a DUP line's ticket and a lost daily file's positions known to the journal, ReleveFP run the day before the copy (the history up to the
releve, then an estimate), 40 trades then one deal edited by 0.20 EUR (and the same on the harness account), deals.csv reversed (the period), tool 1's
wording (no 'du le', no negative zero), the execution cost line beside the broker's stops (harness, 10x), the server name's sources from 1.11 on
(control), every check's info JSON-safe (SELFTEST-JSON: the results file is written in a finally block, the scratch deleted after it, and each
replay group's own scratch folders deleted when it ends, so that a full run stays within the disk the session keeps free).
--quick: tool 1, the ReleveFP harness and the journal-only checks of tool 2 (no robot build or replay).
DEMO_TEST_SCRATCH and DEMO_TEST_RESULTS (environment) move the scratch folder and the results file (used to run this
file against a copy of earlier tools).
"""
import argparse
import calendar
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import demo_common as C  # noqa: E402

import numpy as np  # noqa: E402

MQL5 = os.path.join(C.LAB, "live_ai", "mql5")
BARS = os.path.join(C.CHECK, "out", "bars")
SCRATCH = os.environ.get("DEMO_TEST_SCRATCH") or os.path.join(os.path.dirname(C.DEFAULT_OUT), "demo_test")
RESULTS_FILE = os.environ.get("DEMO_TEST_RESULTS") or os.path.join(os.path.dirname(C.DEFAULT_OUT), "demo_test_results.json")
FAKE_SERVER = "FPMarketsSC-Demo7"
FAKE_LOGIN = "51234987"
FAKE_NAME = "Marie-Claire Fontanel"                # the account holder, as MetaTrader's own log names them
FAKE_USER = "marie-claire"                         # the Windows (Wine) user folder
ACCOUNT_WORDS = [FAKE_SERVER, FAKE_LOGIN, FAKE_NAME, "Fontanel", FAKE_USER, "Marie-Claire"]
REC = np.dtype([("t", "<i8"), ("o", "<i4"), ("h", "<i4"), ("l", "<i4"), ("c", "<i4"), ("s", "<i4")])
RESULTS = []


def jsonable(x, depth=0):
    """a check's info as the results file can hold it (review8 SELFTEST-JSON): dict keys as text (a (market, item) tuple becomes
    'market/item'), tuples and sets as lists, anything else that json cannot write as its text"""
    if depth > 20:
        return str(x)
    if isinstance(x, dict):
        return {("/".join(str(p) for p in k) if isinstance(k, tuple) else (k if isinstance(k, (str, int, float, bool)) or k is None else str(k))):
                jsonable(v, depth + 1) for k, v in x.items()}
    if isinstance(x, (list, tuple, set, frozenset)):
        return [jsonable(v, depth + 1) for v in x]
    if isinstance(x, (str, int, float, bool)) or x is None:
        return x
    if isinstance(x, np.generic):
        return x.item()
    return str(x)


def check(name, cond, info=None):
    RESULTS.append({"test": name, "pass": bool(cond), "info": jsonable(info)})
    print(("PASS " if cond else "FAIL ") + name + ("" if cond or info is None else f"  -> {str(info)[:300]}"))
    return bool(cond)


def chk(name, fn):
    """a check whose condition comes from fn() -> (cond, info); an exception is a FAIL that names it (so that a run of
    this file against earlier tools records every check instead of stopping)"""
    try:
        cond, info = fn()
    except Exception as e:                                              # noqa: BLE001 (any failure of the tool under test)
        cond, info = False, f"{e.__class__.__name__}: {e}"
    return check(name, cond, info)


# ---------------------------------------------------------------------------------------------- the MQL5 literals
R1_HEADER = "time,open,high,low,close,tick_volume,spread,real_volume"   # ReleveFP 1.10 r1_<BASE>.csv (fallback when absent)


def literal_lines():
    """header lines and the INTROUVABLE line, as the .mq5 sources write them. ReleveFP 1.10 adds sp_min at the end of the
    m1 header and the r1 header; the inputs of the tests are written in the 1.10 format either way (m1: the 1.00 header
    + ',sp_min'; r1: R1_HEADER when the .mq5 has none), and 'm1_v100' is the 1.00 header for the files of the old version"""
    rel = open(os.path.join(MQL5, "ReleveFP.mq5"), encoding="ascii").read()
    son = open(os.path.join(MQL5, "SondeFP.mq5"), encoding="ascii").read()
    fh = re.search(r'string FicheHeader\(\)\s*\{(.*?)return s;', rel, re.S).group(1)
    fiche_header = "".join(re.findall(r'"([^"]*)"', fh)).replace("\\n", "")
    introuvable = re.search(r'return base \+ "(,INTROUVABLE,*)\\n"', rel).group(1)
    tous_header = re.search(r'FileWriteString\(h, "(name,path,[^"]*)\\n"\)', rel).group(1)
    m1_header = re.search(r'FileWriteString\(h, "(time,bo[^"]*)\\n"\)', rel).group(1)
    m1_v100 = m1_header[:-len(",sp_min")] if m1_header.endswith(",sp_min") else m1_header
    r1m = re.search(r'FileWriteString\(h, "(time,open,high[^"]*)\\n"\)', rel)
    sonde_header = re.search(r'string out = "(base,name,status[^"]*)\\n"', son).group(1)
    return {"fiche": fiche_header, "introuvable": introuvable, "tous": tous_header, "m1": m1_v100 + ",sp_min", "m1_v100": m1_v100,
            "m1_mq5": m1_header, "r1": r1m.group(1) if r1m else R1_HEADER, "r1_mq5": r1m.group(1) if r1m else None,
            "sonde": sonde_header, "releve_src": rel}


def ds(x, d):
    """DoubleToString(x, d)"""
    return f"{x:.{d}f}"


def write(path, text, crlf=False):
    with open(path, "wb") as f:
        f.write((text.replace("\n", "\r\n") if crlf else text).encode("cp1252"))


# ---------------------------------------------------------------------------------------------- bars (in sample)
def read_bin(path):
    with open(path, "rb") as f:
        assert f.read(4) == b"CRB1"
        digits = int(np.frombuffer(f.read(4), "<i4")[0])
        n = int(np.frombuffer(f.read(8), "<i8")[0])
        rec = np.frombuffer(f.read(n * REC.itemsize), REC)
    assert int(rec["t"].max()) < calendar.timegm((2022, 1, 1, 0, 0, 0)) + 3 * 3600     # in sample only
    return digits, rec


def bars_2021(base, srv_from, srv_to):
    digits, rec = read_bin(os.path.join(BARS, f"{base}.r_y2021.bin"))
    sel = rec[(rec["t"] >= srv_from) & (rec["t"] < srv_to)]
    return digits, sel.copy()


def srv(s):
    return calendar.timegm(time.strptime(s, "%Y-%m-%d %H:%M"))


# ---------------------------------------------------------------------------------------------- ReleveFP files
def m1_text(rec, digits, lit, spread_style="flat", sub=0, version="1.10"):
    """m1_<BASE>.csv as Minutes()/Row() write it: days newest first, minutes in order inside a day. spread_style:
    'flat' = the bar spread at every tick (open = close = mean = max); 'open' = the bar spread at the open, two points
    more at the close, the mean between, the max above (so that only the 'open' convention matches the bar spread);
    'min_hidden' = the bar spread is the smallest spread of the minute, met between the open and the close. Version
    1.10 adds sp_min (the smallest ask - bid of the minute's ticks: the bar spread here); 1.00 has no such column."""
    sc = 10.0 ** digits
    lines = [lit["m1"] if version == "1.10" else lit["m1_v100"]]
    t = rec["t"].astype(np.int64)
    days = sorted(set((t // 86400).tolist()), reverse=True)
    for d in days:
        sel = rec[(t // 86400) == d]
        for r in sel:
            s = max(int(r["s"]) - sub, 0)
            bo, bh, bl, bc = (int(r[k]) / sc for k in "ohlc")
            if spread_style == "flat":
                so, scl, smean, smax, n = s, s, float(s), s, 3
            elif spread_style == "min_hidden":                       # the bar spread is the minimum of the ticks: hidden
                so, scl, smean, smax, n = s + 2, s + 2, s + 1.5, s + 4, 3
            else:
                so, scl, n = s, s + 2, 3
                smean, smax = s + 1.0, s + 3
            ao, ac = bo + so / sc, bc + scl / sc
            ah, al = bh + max(so, scl) / sc, bl + min(so, scl) / sc
            sps = smean / sc * n
            lines.append(f"{int(r['t'])}," + ",".join(ds(x, digits) for x in (bo, bh, bl, bc, ao, ah, al, ac))
                         + f",{n},{ds(sps / n, digits + 2)},{ds(smax / sc, digits)}"
                         + (f",{ds(s / sc, digits)}" if version == "1.10" else ""))
    return "\n".join(lines) + "\n"


def r1_text(rec, digits, lit, sub=0):
    """r1_<BASE>.csv as ReleveFP 1.10 Rates()/RateRow() write it: the terminal's M1 bars as CopyRates gives them, days
    newest first, bars in time order inside a day: time (server seconds), open, high, low, close (bid, the symbol's
    digits), tick_volume, spread (MqlRates.spread, points), real_volume"""
    sc = 10.0 ** digits
    lines = [lit["r1"]]
    t = rec["t"].astype(np.int64)
    for d in sorted(set((t // 86400).tolist()), reverse=True):
        for r in rec[(t // 86400) == d]:
            lines.append(f"{int(r['t'])}," + ",".join(ds(int(r[k]) / sc, digits) for k in "ohlc")
                         + f",{3},{max(int(r['s']) - sub, 0)},0")
    return "\n".join(lines) + "\n"


def fiche_line(base, nm, f, digits):
    return ",".join([base, nm, f.get("path", "Metals\\" + nm), f.get("desc", "Spot " + base), str(digits), ds(f["point"], 8),
                     ds(f["tick_size"], 8), ds(f["tick_value"], 8), ds(f.get("tick_value_loss", f["tick_value"]), 8),
                     ds(f["contract"], 4), ds(f["vmin"], 4), ds(f["vstep"], 4), ds(f["vmax"], 2), str(f.get("calc", 2)),
                     str(f.get("exe", 2)), "1", str(f.get("spread", 12)), str(f.get("stops", 0)), str(f.get("swap_mode", 1)),
                     ds(f["swap_long"], 4), ds(f["swap_short"], 4), str(f.get("swap3", 3)), ds(f.get("margin_initial", 0.0), 4),
                     ds(f["margin"], 2), f.get("ccy_base", base[:3]), f.get("ccy_profit", "USD"), f.get("ccy_margin", "USD"), ds(f["bid"], digits),
                     ds(f["ask"], digits), str(f.get("tick_time", 1700000000)), f["sessions"]])


SESS_GOLD = "1:60-1440|2:0-1440|2:60-1440|3:60-1440|4:60-1440|5:60-1435|"
SESS_GOLD_SHORT_FRI = "1:60-1440|2:60-1440|3:60-1440|4:60-1440|5:60-1400|"     # Friday to 23:20 server: GFP skips
SESS_IDX = "1:60-1395|2:60-1395|3:60-1395|4:60-1395|5:60-1395|"
SESS_CRY = "0:0-1440|1:0-1440|2:0-1440|3:0-1440|4:0-1440|5:0-1440|6:0-1440|"


def fake_fiches(variant="good"):
    """fiches of FP-like markets. variant 'good': what the robot assumes; 'bad': a few values that differ (crypto
    margin 1:2, Friday gold session to 23:20, US100 minimum lot 1.0, gold stops level 20)"""
    rate = 0.86                                                         # EUR per USD
    g = {"point": 0.01, "tick_size": 0.01, "tick_value": 0.01 * 100 * rate, "contract": 100.0, "vmin": 0.01, "vstep": 0.01,
         "vmax": 100.0, "swap_long": -55.1, "swap_short": 18.2, "swap3": 3, "bid": 1790.00, "ask": 1790.12,
         "sessions": SESS_GOLD, "path": "Metals\\XAUUSD.r", "calc": 2}
    g["margin"] = g["ask"] * 100 * rate / 500
    i = {"point": 0.01, "tick_size": 0.01, "tick_value": 0.01 * rate, "contract": 1.0, "vmin": 0.1, "vstep": 0.1, "vmax": 100.0,
         "swap_long": -1.6, "swap_short": 0.3, "swap3": 5, "bid": 16100.00, "ask": 16101.00, "sessions": SESS_IDX, "calc": 3,
         "path": "Indices\\US100.r", "ccy_base": "USD"}
    i["margin"] = i["ask"] * rate / 200
    b = {"point": 0.01, "tick_size": 0.01, "tick_value": 0.01 * rate, "contract": 1.0, "vmin": 0.01, "vstep": 0.01, "vmax": 100.0,
         "swap_long": -20.0, "swap_short": -2.0, "swap_mode": 5, "swap3": 5, "bid": 57000.00, "ask": 57022.50, "sessions": SESS_CRY,
         "calc": 2, "path": "Crypto\\BTCUSD.r"}
    b["margin"] = b["ask"] * rate / 50
    e = dict(b, bid=4300.00, ask=4303.00, path="Crypto\\ETHUSD.r", ccy_base="ETH")
    e["margin"] = e["ask"] * rate / 50
    j = {"point": 0.001, "tick_size": 0.001, "tick_value": 0.001 * 100000 / 114.0 * rate * 114.0 / 114.0, "contract": 100000.0,
         "vmin": 0.01, "vstep": 0.01, "vmax": 50.0, "swap_long": 3.1, "swap_short": -12.0, "swap3": 3, "bid": 114.000, "ask": 114.008,
         "sessions": "1:0-1440|2:0-1440|3:0-1440|4:0-1440|5:0-1435|", "calc": 0, "path": "Forex\\USDJPY.r", "ccy_base": "USD",
         "ccy_profit": "JPY",
         "margin": 100000 * rate / 500}
    if variant == "bad":
        b["margin"] = b["ask"] * rate / 2
        e["margin"] = e["ask"] * rate / 2
        g["sessions"] = SESS_GOLD_SHORT_FRI
        g["stops"] = 20
        i["vmin"] = 1.0
    return {"XAUUSD": (g, 2), "US100": (i, 2), "BTCUSD": (b, 2), "ETHUSD": (e, 2), "USDJPY": (j, 3)}


def make_releve(folder, lit, variant="good", m1_from="2021-10-25 00:00", m1_to="2021-12-01 00:00", sonde=True, crlf=False,
                srv_now=None, mutate=None, tweak=None, cut_fiche=None, version="1.10", cut_m1=None, r1_from=None, r1_days=None):
    """ReleveFP's and SondeFP's files. srv_now: the time ReleveFP ran (fini.txt server_time; default one hour before
    m1_to); mutate(base, rec): change the bars of the m1 files; tweak(fiches): change the fiches before writing;
    cut_fiche: a market whose fiches.csv line is cut short (a copy that stopped in the middle); version '1.10' (sp_min,
    r1_<BASE>.csv, barres= in fini.txt) or '1.00'; cut_m1: a market whose m1 file stops half way (newest days first, so
    the oldest days are lost) while fini.txt keeps the full minutes= count; r1_from: the r1 files start then (default: as
    the m1 files); r1_days: {market: days} the r1 file of that market holds the days InpRateSymbols asks for, back from
    the run day (review4). fini.txt gets ReleveFP 1.10's r1 keys (jours_r1, debut_r1, fin_r1, synchro_r1 ...)"""
    os.makedirs(folder, exist_ok=True)
    fi = fake_fiches(variant)
    if tweak:
        tweak(fi)
    lines = [lit["fiche"]]
    for base in ("BTCUSD", "ETHUSD", "US100", "XAUUSD", "USDJPY"):
        f, dg = fi[base]
        ln = fiche_line(base, base + ".r", f, dg)
        lines.append(ln[:60] if base == cut_fiche else ln)
    lines.append("JP225" + lit["introuvable"])
    write(os.path.join(folder, "fiches.csv"), "\n".join(lines) + "\n", crlf)
    tous = [lit["tous"]]
    for nm, tm in (("XAUUSD", 4), ("XAUUSD.r", 4), ("US100", 4), ("US100.r", 4), ("BTCUSD.r", 4), ("ETHUSD.r", 4), ("USDJPY.r", 4),
                   ("EURUSD.r", 4), ("GOLD", 0)):
        tous.append(f"{nm},Path\\{nm},desc {nm},2,1.0000,0.0100,0.0100,2,-1.0000,-1.0000,USD,{tm}")
    write(os.path.join(folder, "tous.csv"), "\n".join(tous) + "\n", crlf)
    srv_now = srv_now if srv_now is not None else srv(m1_to) - 3600
    fini = [f"version={version}", f"server={FAKE_SERVER}", "company=First Prudential Markets Ltd", "currency=EUR", "leverage=500",
            "demo=1", f"server_time={srv_now}", f"server_minus_gmt_sec={C.rule_offset(C.srv_to_utc(srv_now))}", "all_symbols=9"]
    for base in ("BTCUSD", "ETHUSD", "US100", "XAUUSD"):
        dg, rec = bars_2021(base, srv(m1_from), srv(m1_to))
        if mutate:
            rec = mutate(base, rec)
        style = "open" if variant == "good" else "flat"
        # the lab's gold spread holds the 6-point commission: the broker's raw spread is 6 points less
        sub = 6 if base == "XAUUSD" else 0
        text = m1_text(rec, dg, lit, style, sub, version)
        if base == cut_m1:
            ls = text.split("\n")
            text = "\n".join(ls[:len(ls) // 2]) + "\n"
        write(os.path.join(folder, f"m1_{base}.csv"), text, crlf)
        line = (f"{base}={base}.r jours=30 minutes={len(rec)} ticks={3 * len(rec)} du={time.strftime('%Y.%m.%d %H:%M', time.gmtime(int(rec['t'][0])))} "
                f"au={time.strftime('%Y.%m.%d %H:%M', time.gmtime(int(rec['t'][-1])))} derniere_erreur=0 jours_incomplets=0")
        if version == "1.10":
            day0 = srv_now - srv_now % 86400
            if r1_days and base in r1_days:
                rec_r = bars_2021(base, day0 - (r1_days[base] - 1) * 86400, srv(m1_to))[1]
            else:
                rec_r = rec if r1_from is None else bars_2021(base, srv(r1_from), srv(m1_to))[1]
            write(os.path.join(folder, f"r1_{base}.csv"), r1_text(rec_r, dg, lit, sub), crlf)
            asked = r1_days[base] if r1_days and base in r1_days else int((day0 - int(rec_r["t"][0]) // 86400 * 86400) // 86400) + 1
            line += (f" barres={len(rec_r)} jours_barres={len(set((rec_r['t'] // 86400).tolist()))} erreur_barres=0 jours_courts=0 "
                     f"erreur_r1=0 jours_r1={asked} debut_r1={int(rec_r['t'][0])} fin_r1={int(rec_r['t'][-1])} synchro_r1=1 attente_r1=2")
        fini.append(line)
    fini.append("USDJPY=USDJPY.r jours=0 minutes=0 ticks=0 du=1970.01.01 00:00 au=1970.01.01 00:00 derniere_erreur=4401 jours_incomplets=0"
                + (" barres=0 jours_barres=0 erreur_barres=0" if version == "1.10" else ""))
    fini.append("JP225=INTROUVABLE")
    fini += ["stopped=0", "seconds=412"]
    write(os.path.join(folder, "fini.txt"), "\n".join(fini) + "\n", crlf)
    if sonde:
        rate = 0.86
        s = [lit["sonde"]]
        # gold: 0.01 lot, 3 USD per side per lot in EUR, rounded to the cent per deal: -0.03 EUR per deal
        s.append("XAUUSD,XAUUSD.r,ok,0.0100,1790.00,1790.12,1790.12,1790.05,1790.17,1790.05,2,-0.0600,0.0000,-0.0602,0.0000,"
                 f"0.01000000,{ds(0.01 * 100 * rate, 8)},100.0000,70001234")
        s.append("US100,US100.r,ok,0.1000,16100.00,16101.00,16101.00,16100.50,16101.50,16100.50,2,0.0000,0.0000,-0.0430,0.0000,"
                 f"0.01000000,{ds(0.01 * rate, 8)},1.0000,70001235")
        s.append("BTCUSD,BTCUSD.r,ok,0.0100,57000.00,57022.50,57022.50,57001.00,57023.00,57001.00,2,0.0000,0.0000,-0.1849,0.0000,"
                 f"0.01000000,{ds(0.01 * rate, 8)},1.0000,70001236")
        if variant == "bad":
            s.append("ETHUSD,ETHUSD.r,POSITION RESTEE OUVERTE (fermez-la a la main),0.0100,4300.00,4303.00,4303.00,0.00,0.00,0.00,1,-0.0300,"
                     f"0.0000,0.0000,0.0000,0.01000000,{ds(0.01 * rate, 8)},1.0000,70001237")
        else:
            s.append("ETHUSD,ETHUSD.r,lot minimum trop gros pour un stop a 0.40 % du solde")
        s.append("JP225,,INTROUVABLE")
        s.append(f"#currency=EUR,server={FAKE_SERVER},server_time={srv_now + 600}")
        write(os.path.join(folder, "sonde.csv"), "\n".join(s) + "\n", crlf)


def outputs_text(out):
    txt = ""
    for root, _, files in os.walk(out):
        for f in files:
            p = os.path.join(root, f)
            if f.endswith((".json", ".txt", ".log", ".csv")) and os.path.getsize(p) < 200_000_000:
                txt += open(p, encoding="utf-8", errors="replace").read()
    return txt


def run_tool(script, args):
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, script)] + args, capture_output=True, text=True, timeout=7200)
    return r.returncode, r.stdout, r.stderr


# ---------------------------------------------------------------------------------------------- tool 1
def test_tool1(lit):
    base_dir = os.path.join(SCRATCH, "t1")
    for variant in ("good", "bad"):
        folder = os.path.join(base_dir, "in_" + variant)
        out = os.path.join(base_dir, "out_" + variant)
        make_releve(folder, lit, variant, crlf=(variant == "bad"))
        rc, so, se = run_tool("read_mac_files.py", [folder, "--out", out])
        if not check(f"tool1 {variant}: runs", rc == 0, se[-2000:]):
            continue
        s = json.load(open(os.path.join(out, "summary.json")))
        chk = {(c["market"], c["item"]): c for c in s["checks"]}
        txt = outputs_text(out) + so
        check(f"tool1 {variant}: account server never written or printed", FAKE_SERVER not in txt, None)
        check(f"tool1 {variant}: every check is OK, DIFFERENT, UNKNOWN or INFO with both values",
              all(c["status"] in ("OK", "DIFFERENT", "UNKNOWN", "INFO") and "broker" in c and "assumed" in c for c in s["checks"]))
        check(f"tool1 {variant}: summary_fr.txt written", os.path.exists(os.path.join(out, "summary_fr.txt")))
        st = lambda m, i: chk.get((m, i), {}).get("status")             # noqa: E731
        check(f"tool1 {variant}: the four robot markets have their name check",
              all(st(b, "name") == "OK" for b in C.ROBOT_BASES), [chk.get((b, "name")) for b in C.ROBOT_BASES])
        check(f"tool1 {variant}: JP225 not found is reported", st("JP225", "name") == "DIFFERENT")
        check(f"tool1 {variant}: hedging inferred from the probe", st("compte", "margin_mode") == "OK", chk.get(("compte", "margin_mode")))
        check(f"tool1 {variant}: server clock New York + 7 h from fini.txt", st("compte", "server_clock") == "OK",
              chk.get(("compte", "server_clock")))
        check(f"tool1 {variant}: server clock from the gold break (across the November switch)",
              st("compte", "server_clock_bars") == "OK" and "changement" in chk[("compte", "server_clock_bars")]["broker"],
              chk.get(("compte", "server_clock_bars")))
        check(f"tool1 {variant}: gold commission 0.06 EUR per 0.01 lot = 6.98 points, within the 1-point margin of the robot",
              st("XAUUSD", "commission") == "OK", chk.get(("XAUUSD", "commission")))
        check(f"tool1 {variant}: no commission on US100 and BTC", st("US100", "commission") == "OK" and st("BTCUSD", "commission") == "OK")
        check(f"tool1 {variant}: Thanksgiving 2021 and the Friday after are checked against the gold closures",
              st("XAUUSD", "holiday_2021-11-25") in ("OK", "DIFFERENT") and st("XAUUSD", "holiday_2021-11-26") in ("OK", "DIFFERENT"),
              [k for k in chk if k[1].startswith("holiday")])
        check(f"tool1 {variant}: crypto quotes at weekends set against the lab", st("BTCUSD", "weekend") in ("OK", "INFO"))
        check(f"tool1 {variant}: freeze level and filling are UNKNOWN (not in the files)",
              st("XAUUSD", "freeze_level") == "UNKNOWN" and st("XAUUSD", "filling") == "UNKNOWN")
        check(f"tool1 {variant}: the USDJPY failure of the tick history is reported", st("USDJPY", "releve_days") == "DIFFERENT",
              chk.get(("USDJPY", "releve_days")))
        if variant == "good":
            check("tool1 good: crypto margin 1:50 is OK", st("BTCUSD", "margin") == "OK" and st("ETHUSD", "margin") == "OK",
                  [chk.get(("BTCUSD", "margin")), chk.get(("ETHUSD", "margin"))])
            check("tool1 good: Friday gold session reaches 23:46", st("XAUUSD", "friday_session") == "OK", chk.get(("XAUUSD", "friday_session")))
            check("tool1 good: US100 minimum lot 0.1", st("US100", "vol_min") == "OK")
            check("tool1 good: gold spread with commission within 1.5 x the model", st("XAUUSD", "spread") == "OK", chk.get(("XAUUSD", "spread")))
            check("tool1 good: digits, contract sizes and volumes as assumed",
                  all(st(b, k) == "OK" for b in C.ROBOT_BASES for k in ("digits", "point", "contract_size", "vol_step", "vol_max")),
                  [(b, k, st(b, k)) for b in C.ROBOT_BASES for k in ("digits", "point", "contract_size", "vol_step", "vol_max")])
            check("tool1 good: swaps converted (gold long -55.1 points = 11.1 %/year vs 5.5 %)",
                  st("XAUUSD", "swap_long") == "DIFFERENT" and "11," in chk[("XAUUSD", "swap_long")]["broker"], chk.get(("XAUUSD", "swap_long")))
            check("tool1 good: BTC swap in annual % (-20 % = the lab's 20 %)", st("BTCUSD", "swap_long") == "OK", chk.get(("BTCUSD", "swap_long")))
        else:
            check("tool1 bad: crypto margin 1:2 reported with the T7b reading",
                  st("BTCUSD", "margin") == "DIFFERENT" and "462" in chk[("BTCUSD", "margin")]["note"], chk.get(("BTCUSD", "margin")))
            check("tool1 bad: Friday gold session to 23:20 makes GFP skip", st("XAUUSD", "friday_session") == "DIFFERENT",
                  chk.get(("XAUUSD", "friday_session")))
            check("tool1 bad: US100 minimum lot 1.0 differs", st("US100", "vol_min") == "DIFFERENT")
            check("tool1 bad: gold stops level 20 differs", st("XAUUSD", "stops_level") == "DIFFERENT")
            check("tool1 bad: the probe position left open is reported", st("compte", "probe_left_open") == "DIFFERENT")
            check("tool1 bad: CRLF line ends read", len(s["fiches"]) == 6, list(s["fiches"]))
    # an --out inside the repository is refused
    rc, so, se = run_tool("read_mac_files.py", [os.path.join(base_dir, "in_good"), "--out", os.path.join(C.ROBOT, "demo", "x_out")])
    check("tool1: --out inside the repository refused", rc != 0 and not os.path.exists(os.path.join(C.ROBOT, "demo", "x_out")), se[-300:])
    # an empty folder: still runs
    empty = os.path.join(base_dir, "in_empty")
    os.makedirs(empty, exist_ok=True)
    rc, so, se = run_tool("read_mac_files.py", [empty, "--out", os.path.join(base_dir, "out_empty")])
    check("tool1: runs on an empty folder", rc == 0, se[-500:])
    # only a sonde file: still runs, the rest UNKNOWN
    only = os.path.join(base_dir, "in_only_sonde")
    os.makedirs(only, exist_ok=True)
    shutil.copy(os.path.join(base_dir, "in_good", "sonde.csv"), only)
    rc, so, se = run_tool("read_mac_files.py", [only, "--out", os.path.join(base_dir, "out_only")])
    check("tool1: runs with sonde.csv alone", rc == 0, se[-500:])


# ---------------------------------------------------------------------------------------------- tool 2: journals by hand
def jl(utc, ev, code, *kv):
    """one journal line as JrnAt writes it: CR|utc|EVENT|code|k=v...; doubles DoubleToString(x, -16)"""
    parts = []
    for k, v in kv:
        if isinstance(v, bool):
            v = "1" if v else "0"
        elif isinstance(v, float):
            v = f"{v:.16e}"
        parts.append(f"|{k}={v}")
    return f"CR|{int(utc)}|{ev}|{code}" + "".join(parts)


S7 = "0:7;3000:3.5;10000:1.4;20000:0.7"           # the user's risk table (SPEC 1 step 3), typed on the demo
D2 = "0:10;3000:5;10000:2;20000:1"                 # the build's default (InpRiskTable not typed)


def init_line(utc, build=C.REQUIRED_BUILD, observer=0, harness=0, demo=1, vps=0, comm=6, risk=S7, sleeves="ALL", sw=("on", "on", "on"),
              syms=None, k1t=""):
    """the INIT line of a start as the demo has it (S7 typed, sleeves ALL, the three switches on, the .r names; review4 A4); k1t: the
    K1 table as the robot writes it back (Brk72K1Text, review4b ADV5-5)"""
    syms = dict({b: b + ".r" for b in C.ROBOT_BASES}, **(syms or {}))
    return jl(utc, "INIT", "-", ("build", build), ("version", "2.00"), ("demo", demo), ("vps", vps), ("tester", 0), ("observer", observer),
              ("entries_off", observer), ("harness", harness), ("comm_pts", comm), ("risk", risk),
              ("sleeves", sleeves), ("S0.75r", sw[2]), ("K1", sw[0]), ("H2", sw[1]), ("k1t", k1t), ("XAUUSD", syms["XAUUSD"]),
              ("US100", syms["US100"]), ("BTCUSD", syms["BTCUSD"]), ("ETHUSD", syms["ETHUSD"]))


def dec_ord(utc, code, oid, side, et, lv, st, x, rp=False, lv2=0.0, sd=0.0):
    """a DEC what=ord line with every field JrnOrder writes (CR_Journal.mqh), stamped at its decision time"""
    kv = [("what", "ord"), ("oid", oid), ("side", side), ("et", et), ("lv", float(lv)), ("lv2", float(lv2)), ("tf", utc),
          ("tt", utc + 3600), ("ax", 0), ("exp", utc + 3600), ("st", float(st)), ("sd", float(sd)), ("tr", 0.0), ("be", 0.0),
          ("tg", 0.0), ("td", 0.0), ("x", x), ("xg", 0), ("xh", 0), ("xr", 0.0), ("ref", 0), ("vle", 0), ("grp", 0), ("at", utc)]
    if rp:
        kv.append(("rp", 1))
    return jl(utc, "DEC", code, *kv)


HAND_DAY1, HAND_DAY2 = 10082.65, 9892.78           # the hand-made journal's DAY balances (they follow its two trades)


def handmade_journal(folder, variant):
    """two days of a trading demo copy: one gold trade closed by the EA, one gold trade stopped by the broker, the
    listed lines; variant 'bad' adds an old build, a failed self-test, an ERROR, a DUP, a COST over the model ..."""
    os.makedirs(folder, exist_ok=True)
    t0 = calendar.timegm((2021, 11, 15, 8, 0, 0))
    L = [init_line(t0, build="40dce66811c6" if variant == "bad" else C.REQUIRED_BUILD),
         jl(t0, "SELFTEST", "-", ("ok", 0 if variant == "bad" else 1), ("why", "golden" if variant == "bad" else ""), ("golden", 366)),
         jl(t0 + 60, "PLAN", "-", ("T", 1630000000), ("state", "ok"), ("demo", 1), ("B_T", 10000.0), ("risk", S7)),
         jl(t0 + 60, "REBUILD", "-", ("n", 1), ("why", "start"), ("from", t0 - 120 * 86400), ("to", t0 + 60), ("minutes", 172800), ("ms", 812))]
    for b in C.ROBOT_BASES:
        ready_at = t0 + (1500 if (variant == "bad" and b == "ETHUSD") else 62)
        if variant == "bad" and b == "ETHUSD":
            L.append(jl(t0 + 62, "NOTREADY", b, ("why", "sync"), ("bars", 1000), ("raw", 1000), ("first", t0 - 50 * 86400), ("last", t0),
                        ("masked", 0), ("holes", 0)))
        L.append(jl(ready_at, "READY", b, ("bars", 100000), ("raw", 100000), ("first", t0 - 120 * 86400), ("last", t0), ("masked", 0),
                    ("holes", 0), ("depth_days", C.DEPTH_DAYS[b])))
    L.append(dec_ord(t0 - 86400 * 3, "D4H", (t0 - 86400 * 3) * 100 + 9, 0, 3, 1800.5, 0.0, t0, rp=True, lv2=1760.0, sd=12.5))
    # trade 1: ORX long, paper fill 1800.50 at 09:00, real fill 1800.40 one bar later, EA close at 1810.07 against 1810.00
    f1 = t0 + 3600
    oid1 = f1 * 100 + 10
    k = 86.0                                                            # EUR per price unit and lot
    risk1 = (1800.40 - 1790.00 + 2 * 0.03) * k * 0.10
    L += [jl(f1, "DEC", "ORX", ("what", "ord"), ("oid", oid1), ("side", 1), ("et", 1), ("lv", 1800.5), ("lv2", 0.0), ("tf", f1), ("tt", f1),
             ("ax", 0), ("exp", f1 + 60), ("st", 1790.0), ("sd", 0.0), ("tr", 0.0), ("be", 0.0), ("tg", 0.0), ("td", 0.0), ("x", f1 + 30000),
             ("xg", 0), ("xh", 0), ("xr", 0.0), ("ref", 0), ("vle", 0), ("grp", 0), ("at", f1)),
          jl(f1, "PFILL", "ORX", ("oid", oid1), ("side", 1), ("bar", f1), ("px", 1800.5), ("stop", 1790.0), ("st0", 1790.0), ("x", f1 + 30000),
             ("s_raw", 12), ("s_paper", 0.18)),
          jl(f1, "SIZE", "ORX", ("oid", oid1), ("side", 1), ("et", 1), ("lots", 0.1), ("want", 0.1), ("skip", "none"), ("B", 10000.0),
             ("P_in", 10000.0), ("rate", 10.0), ("m", 1.0), ("f", 1.0), ("unit", 1000.0), ("w", 0.0), ("r", 10.5), ("budget", 1000.0),
             ("late", 1), ("quote", 1800.4)),
          jl(f1 + 62, "SEND", "ORX", ("oid", oid1), ("side", 1), ("lots", 0.1), ("want", 0.1), ("sl", 1790.03), ("bid", 1800.28), ("ask", 1800.4),
             ("stamp", f1), ("dev", 24), ("cut", "-"), ("result", "filled"), ("rc", 10009), ("s_raw", 12), ("s_paper", 0.18)),
          jl(f1 + 62, "FILL", "ORX", ("oid", oid1), ("ticket", 70000011), ("side", 1), ("px", 1800.4), ("lots", 0.1), ("sl", 1790.0),
             ("listed", 1), ("risk", risk1), ("budget", 1000.0), ("stamp", f1), ("s_raw", 12), ("s_paper", 0.18)),
          jl(f1 + 30060, "PEXIT", "ORX", ("oid", oid1), ("side", 1), ("bar", f1 + 30000), ("px", 1810.0), ("stop", 1790.0), ("st0", 1790.0),
             ("x", f1 + 30000), ("reason", "time"), ("s_raw", 12), ("s_paper", 0.18)),
          jl(f1 + 30002, "CLOSE", "ORX", ("ticket", 70000011), ("magic", 20261210), ("px", 1810.07), ("why", "time"), ("rc", 10009), ("ok", 1))]
    # trade 2: GFP long stopped: paper stop exit 1789.80, no CLOSE line (the broker's stop), broker stop moved to 1790.20
    f2 = t0 + 86400 + 3600
    oid2 = f2 * 100 + 8
    risk2 = (1801.00 - 1790.00 + 0.06) * k * 0.2
    L += [dec_ord(f2, "GFP", oid2, 1, 2, 1801.1, 1790.0, f2 + 12000),
          jl(f2, "PFILL", "GFP", ("oid", oid2), ("side", 1), ("bar", f2), ("px", 1801.1), ("stop", 1790.0), ("st0", 1790.0), ("x", f2 + 12000),
             ("s_raw", 10), ("s_paper", 0.16)),
          jl(f2, "SIZE", "GFP", ("oid", oid2), ("side", 1), ("et", 2), ("lots", 0.2), ("want", 0.2), ("skip", "none"), ("B", 10000.0),
             ("P_in", 10000.0), ("rate", 10.0), ("m", 1.0), ("f", 1.0), ("unit", 1000.0), ("w", 0.0), ("r", 11.1), ("budget", 1000.0),
             ("late", 1), ("quote", 1801.0)),
          jl(f2 + 62, "SEND", "GFP", ("oid", oid2), ("side", 1), ("lots", 0.2), ("want", 0.2), ("sl", 1790.03), ("bid", 1800.9), ("ask", 1801.0),
             ("stamp", f2), ("dev", 20), ("cut", "-"), ("result", "filled"), ("rc", 10009), ("s_raw", 10), ("s_paper", 0.16)),
          jl(f2 + 62, "FILL", "GFP", ("oid", oid2), ("ticket", 70000012), ("side", 1), ("px", 1801.0), ("lots", 0.2), ("sl", 1790.0),
             ("listed", 1), ("risk", risk2), ("budget", 1000.0), ("stamp", f2), ("s_raw", 10), ("s_paper", 0.16)),
          jl(f2 + 600, "SLMOD", "GFP", ("ticket", 70000012), ("from", 1790.0), ("to", 1790.2), ("rc", 10009), ("ok", 1)),
          jl(f2 + 3660, "PEXIT", "GFP", ("oid", oid2), ("side", 1), ("bar", f2 + 3600), ("px", 1789.8), ("stop", 1790.17), ("st0", 1790.0),
             ("x", f2 + 12000), ("reason", "stop"), ("s_raw", 10), ("s_paper", 0.16)),
          jl(f2 + 7200, "MISSED", "BKB", ("oid", (f2 + 7000) * 100 + 3), ("stamp", f2 + 7000), ("reason", "exited")),
          jl(t0 + 86400 + 60, "COST", "XAUUSD", ("day", C.utc_to_srv(t0) // 86400 * 86400), ("raw_bp", 0.2), ("paper_bp", 0.9 if variant == "bad" else 0.53),
             ("model_bp", 0.47), ("comm_usd_oz", 0.08 if variant == "bad" else 0.06), ("comm_n", 4)),
          jl(t0 + 86400 + 60, "AGG", "-", ("day", C.utc_to_srv(t0) // 86400 * 86400), ("XAUUSD", 1300), ("US100", 0), ("BTCUSD", 0),
             ("ETHUSD", 0), ("dec", 10), ("pev", 3)),
          # the balance books what the trades made (review4 A7): ORX +83.16 - 0.52 commission; GFP at its broker stop 1790.20 less the
          # lab's 1 bp stop slippage, -188.84 - 1.03 commission
          jl(t0 + 86400 + 60, "DAY", "-", ("day", C.utc_to_srv(t0) // 86400 * 86400), ("balance", HAND_DAY1), ("equity", HAND_DAY1),
             ("bars_fed", 5000)),
          jl(t0 + 2 * 86400 + 60, "AGG", "-", ("day", C.utc_to_srv(t0) // 86400 * 86400 + 86400), ("XAUUSD", 0), ("US100", 0), ("BTCUSD", 0),
             ("ETHUSD", 0), ("dec", 10), ("pev", 3)),
          jl(t0 + 2 * 86400 + 60, "DAY", "-", ("day", C.utc_to_srv(t0) // 86400 * 86400 + 86400), ("balance", HAND_DAY2), ("equity", HAND_DAY2),
             ("bars_fed", 9000)),
          jl(t0 + 2 * 86400 + 600, "LATEBAR", "BTCUSD", ("why", "revised value"), ("t", t0 + 2 * 86400 + 480), ("wait_s", 0))]
    if variant == "bad":
        L += [jl(t0 + 7200, "ERROR", "-", ("what", "paper refused order 1 (two pending orders)")),
              jl(t0 + 7300, "DUP", "N30", ("ticket", 70000020), ("kept", 70000019)),
              jl(t0 + 7400, "REFUSED", "N30", ("oid", 163700000001), ("why", "broker"), ("rc", 10016)),
              jl(t0 + 7500, "MISSED", "N30", ("oid", 163700000001), ("stamp", t0 + 7000), ("reason", "refused"), ("rc", 10016)),
              jl(t0 + 7600, "SLFIX", "OC4", ("ticket", 70000021), ("why", "no_expected_stop")),
              jl(t0 + 7700, "WATCH", "D4H", ("ticket", 70000022), ("due", t0 + 7000), ("open", t0)),
              "CR|1637000000|DEC|N30|what=ord|oid=12"]                 # a line cut short: unreadable since review2 N7
        L.append("CR|bad line")
    L.append(jl(t0 + 3 * 86400, "INIT", "-", ("deinit", 1), ("lines", len(L)), ("bars_fed", 9000), ("rebuilds", 1)))
    day = time.strftime("%Y%m%d", time.gmtime(C.utc_to_srv(t0)))
    write(os.path.join(folder, f"{day}.log"), "\n".join(L) + "\n", crlf=(variant == "bad"))
    return {"k": k, "oid1": oid1, "oid2": oid2, "t0": t0}


def utf16_printed(path, journal_lines, extra_other=True, drop=0, vps=False):
    """an Experts log as MetaTrader writes it (UTF-16 LE with a byte-order mark): a prefix, then the robot's line; the
    terminal's own lines name the login and the server"""
    out = []
    if extra_other:
        out.append(f"QK\t0\t09:59:58.120\tNetwork\t'{FAKE_LOGIN}': authorized on {FAKE_SERVER} through Access Point EU 2")
    for i, ln in enumerate(journal_lines):
        if drop and i % drop == 3:
            continue
        if vps and "|INIT|-|build=" in ln:
            ln = ln.replace("|vps=0|", "|vps=1|").replace("|observer=1|", "|observer=0|")
        out.append(f"GH\t0\t10:00:{i % 60:02d}.000\tClaudeRobot (XAUUSD.r,M1)\t{ln}")
    with open(path, "wb") as f:
        f.write(b"\xff\xfe" + ("\r\n".join(out) + "\r\n").encode("utf-16-le"))


def test_tool2_journal(lit):
    base_dir = os.path.join(SCRATCH, "t2j")
    for variant in ("good", "bad"):
        jdir = os.path.join(base_dir, "j_" + variant, "ClaudeRobot")
        info = handmade_journal(jdir, variant)
        out = os.path.join(base_dir, "out_" + variant)
        rc, so, se = run_tool("check_demo.py", ["--journals", os.path.dirname(jdir), "--out", out])
        if not check(f"tool2 journal {variant}: runs", rc == 0, se[-2000:]):
            continue
        r = json.load(open(os.path.join(out, "report.json")))
        a, b = r["journal"], r["fills"]
        pos = {p["ticket"]: p for p in b["positions"]}
        check(f"tool2 journal {variant}: report_fr.txt written", os.path.exists(os.path.join(out, "report_fr.txt")))
        check(f"tool2 journal {variant}: one start, its deinit reason", len(a["starts"]) == 1 and a["starts"][0]["deinit"] == 1,
              a["starts"][0] if a["starts"] else None)
        p1, p2 = pos.get(70000011), pos.get(70000012)
        ok1 = p1 is not None and abs(p1["eur_per_price_per_lot"] - info["k"]) < 1e-9 and abs(p1["entry_diff_pts"] - (-10.0)) < 1e-6 \
            and abs(p1["entry_diff_eur"] - (-0.86)) < 1e-9 and abs(p1["exit_diff_pts"] - (-7.0)) < 1e-6 and p1["exit_kind"] == "ea_close" \
            and abs(p1["entry_diff_net_pts"] - (-7.0 if variant == "good" else -6.0)) < 1e-6 \
            and abs(p1["entry_diff_bp"] - (-0.1 / 1800.5 * 1e4)) < 1e-9
        check(f"tool2 journal {variant}: EA-closed gold trade, differences in points, bp and EUR (EUR per point from the FILL risk)",
              ok1, p1)
        ok2 = p2 is not None and p2["exit_kind"] == "broker_stop_estimated" and abs(p2["exit_real"] - 1790.2) < 1e-9 \
            and abs(p2["exit_diff_pts"] - (-40.0)) < 1e-6
        check(f"tool2 journal {variant}: broker stop: no CLOSE line, exit estimated at the last broker stop", ok2, p2)
        tot = b["per_sleeve"]["TOTAL"]
        check(f"tool2 journal {variant}: share of intents that became trades", tot["intents"] == 2 and tot["real_trades"] == 2
              and abs(tot["share_intents_to_trades"] - 1.0) < 1e-12, tot)
        m = b["money_estimate"]
        check(f"tool2 journal {variant}: money estimate from the DAY lines", m is not None
              and abs(m["balance_change_eur"] - (HAND_DAY2 - HAND_DAY1)) < 1e-9, m)
        check(f"tool2 journal {variant}: commission and swap per trade said UNKNOWN", b["commission_swap_per_trade"].startswith("UNKNOWN"))
        txt = outputs_text(out) + so
        if variant == "good":
            check("tool2 journal good: nothing abnormal", r["anomalies"] == [] and "Rien d'anormal" in so, r["anomalies"])
            check("tool2 journal good: COST gold commission 0.06 used for the net differences",
                  b["commission_source"].startswith("COST") and abs(b["commission_per_side_price"]["XAUUSD"] - 0.03) < 1e-12)
            check("tool2 journal good: LATEBAR listed without being an anomaly", len(a["listed"]["LATEBAR"]) == 1)
            check("tool2 journal good: counts per sleeve (live and replayed)", a["counts"]["ORX"]["FILL"]["live"] == 1
                  and a["counts"]["D4H"]["DEC"]["replayed"] == 1 and a["counts"]["ORX"]["DEC"]["orders_live"] == 1, a["counts"]["ORX"])
            # printed lines: the same copy, UTF-16, with the terminal's own lines naming the account
            jlines = [ln for ln in open(os.path.join(jdir, os.listdir(jdir)[0])).read().splitlines() if "|rp=1" not in ln]
            pf = os.path.join(base_dir, "experts_good.log")
            utf16_printed(pf, jlines)
            out2 = os.path.join(base_dir, "out_printed")
            rc, so2, se = run_tool("check_demo.py", ["--journals", os.path.dirname(jdir), "--printed", pf, "--out", out2])
            r2 = json.load(open(os.path.join(out2, "report.json"))) if rc == 0 else {}
            check("tool2 printed: same copy, every live line printed, nothing abnormal",
                  rc == 0 and r2["printed"]["same_copy_as_files"] and r2["printed"]["ok"] and r2["anomalies"] == [], (se[-500:], r2.get("printed")))
            txt2 = outputs_text(out2) + so2
            check("tool2 printed: the login and the server of the terminal's lines never reach an output",
                  FAKE_LOGIN not in txt2 and FAKE_SERVER not in txt2)
            pf3 = os.path.join(base_dir, "experts_missing.log")
            utf16_printed(pf3, jlines, drop=5)
            out3 = os.path.join(base_dir, "out_printed_missing")
            rc, so3, se = run_tool("check_demo.py", ["--journals", os.path.dirname(jdir), "--printed", pf3, "--out", out3])
            r3 = json.load(open(os.path.join(out3, "report.json"))) if rc == 0 else {}
            check("tool2 printed: lines missing from the Experts log are reported",
                  rc == 0 and r3["printed"]["n_live_not_printed"] > 0 and r3["anomalies"], r3.get("printed", {}).get("n_live_not_printed"))
        else:
            an = " | ".join(r["anomalies"])
            for word, why in (("40dce66811c6", "old (debug) build"), ("auto-test", "failed self-test"), ("ERROR", "ERROR line"),
                              ("DUP", "DUP line"), ("REFUSED", "REFUSED line"), ("SLFIX", "SLFIX line"), ("WATCH", "WATCH line"),
                              ("MISSED", "MISSED refused"), ("1,5 fois", "COST over the model"), ("commission or", "gold commission off"),
                              ("ETHUSD pret seulement apres", "READY after 24 min"), ("illisible", "unparsable line")):
                check(f"tool2 journal bad: anomaly reported: {why}", word in an, an[:600])
            check("tool2 journal bad: 'rien d'anormal' not said", "Rien d'anormal" not in so and "rien d'anormal" not in so)
            check("tool2 journal bad: missed reasons counted", r["journal"]["missed_by_reason"].get("N30 refused") == 1,
                  r["journal"]["missed_by_reason"])
        check(f"tool2 journal {variant}: no account data in the outputs", FAKE_SERVER not in txt and FAKE_LOGIN not in txt)


# ---------------------------------------------------------------------------------------------- tool 2: the review's cases
def U(s):
    """UTC seconds of a server time 'YYYY-mm-dd HH:MM' (November 2021: server = UTC + 2 h)"""
    return C.srv_to_utc(srv(s))


def md_journal(folder, variant=(), style="live"):
    """eight server days of a trading demo (Wed 2021-11-17 to Thu 2021-11-25), one daily file per server date as JrnAt
    writes them. style 'live': MetaTrader runs at weekends, so Saturday and Sunday have their files (AGG, COST, DAY of
    the day before at 00:00:30); 'harness': the mock jumps over the weekend, so Monday's file holds the DAY lines of
    Friday, Saturday and Sunday. Five positions: ORX (A) closed by the EA, D4H short (E) open over the weekend and closed
    on Monday, BKB (C), GFP (B), N30 (D). variant: 'no_close' (A's CLOSE line gone), 'close_refused' (A's close refused,
    rc 10018, never retried), 'race' (C's CLOSE px=0 rc=0 ok=1), 'dup' (a second ticket for D's oid, no DUP line),
    'restart' (stopped Friday night, started again Monday with an ADOPT of E), 'observe_late' (a MISSED observe stamped
    after the plan start), 'plan_unset', 'glued' (a terminal line glued inside a robot file). The plan starts at the
    go-live time (SPEC 1 step 3), so the paper trade already open at the start ends MISSED observe (normal).
    Every order has its DEC line; ORX, GFP and D4H enter by stop orders (et=1, SIZE late=1: sent one bar after the
    paper's fill, by design); F (F1E) is a paper trade whose intent was skipped (SIZE skip=cap, nothing sent).
    Variants of the second review: 'late_dec' (a D4H DEC stamped Saturday 00:00 written on Monday 01:00, as the robot
    writes a Friday-close decision), 'early_dec' (a live D4H DEC stamped two days before the start, written just
    after it), 'clock_first' (a CLOCK line written in OnInit before the INIT line), 'bkb_stop' (C ends at its paper
    stop and no CLOSE line: the broker's stop).
    The DAY balances follow the trades (each close books its result less the model's gold commission; review4 A7).
    Variants of the fourth review: 'plan_future' (InpPlanStart typed a year late: PLAN state=future), 'risk_d2' (the build's
    default risk table, S7 not typed), 'sleeves_gfp', 'demo0' (a real account), 'sym_noR' (US100 not the .r name), 'k1_off'
    (a switch off on the demo), 'slip_gold' (the three gold fills 4 bp worse than their quote, the closes 4 bp worse than the
    paper), 'slmod_refused' (BKB's stop move refused six times, rc 10029, never done), 'slmod_once' (refused once, done at
    the next try), 'deposit' (500 EUR more on the balance from Saturday), 'hand_loss' (700 EUR less from Saturday), 'p_in'
    (a payment of 500 EUR: P_in of the later SIZE lines and the balance), 'reconnect_cap' (a reconnection while F1E's
    cap-skipped paper trade is open: the reconcile writes MISSED cap), 'missed_twice' (a MISSED refused written twice for one
    N30 trade), 'outage' (a reconnection: a paper trade opened and closed while offline, another still open: MISSED late),
    'n30_stop_grid' (N30 ends at its paper stop 16200.10, the broker stop on US100's 0.25 grid at 16200.00), 'orx_stopped' (with
    'no_close': the balance books ORX at its broker stop, the case where the minutes show that stop crossed).
    Variants of review4b: 'plan_late' (InpPlanStart 20 h after the start: an intent before it sized observe, B = P_in = 0),
    'orphan_reconcile' (with 'outage': an ORPHAN at the reconnection's reconcile), 'orphan_mid' (an ORPHAN far from any start or
    reconnection). Variant of review5b: 'restart_d2' ('restart' with the build's default D2 at the restart: InpRiskTable not typed)."""
    os.makedirs(folder, exist_ok=True)
    L = []                                                              # (server write time, line)

    def add(t_srv, line):
        L.append((int(t_srv), line))
    T = srv("2022-11-17 08:00") if "plan_future" in variant else (srv("2021-11-18 04:00") if "plan_late" in variant else srv("2021-11-17 08:00"))
    k_gold, k_usd = 86.0, 0.86
    risk = D2 if "risk_d2" in variant else S7
    closes = []                                                         # (server time, EUR) each close books on the balance

    def start(at):
        a = srv(at)
        if "clock_first" in variant and at == "2021-11-17 08:00":     # OnInit: the guards' clock check writes before INIT
            add(a, jl(C.srv_to_utc(a), "CLOCK", "-", ("state", "wrong"), ("measured_s", 3600), ("rule_s", 7200)))
        r_ = D2 if ("restart_d2" in variant and at != "2021-11-17 08:00") else risk    # review5b: the restart with InpRiskTable not typed
        add(a, init_line(C.srv_to_utc(a), risk=r_, sleeves="GFP" if "sleeves_gfp" in variant else "ALL", demo=0 if "demo0" in variant else 1,
                         sw=("off" if "k1_off" in variant else "on", "on", "on"), syms={"US100": "US100"} if "sym_noR" in variant else None))
        add(a, jl(C.srv_to_utc(a), "SELFTEST", "-", ("ok", 1), ("why", ""), ("golden", 366)))
        state = "unset" if "plan_unset" in variant else ("future" if ("plan_future" in variant or "plan_late" in variant) else "ok")
        add(a + 60, jl(C.srv_to_utc(a + 60), "PLAN", "-", ("T", T), ("state", state), ("demo", 0 if "demo0" in variant else 1),
                       ("B_T", 10000.0), ("risk", r_)))
        add(a + 60, jl(C.srv_to_utc(a + 60), "REBUILD", "-", ("n", 1), ("why", "start"), ("from", C.srv_to_utc(a) - 120 * 86400),
                       ("to", C.srv_to_utc(a + 60)), ("minutes", 172800), ("ms", 812)))
        for b in C.ROBOT_BASES:
            add(a + 62, jl(C.srv_to_utc(a + 62), "READY", b, ("bars", 100000), ("raw", 100000), ("first", C.srv_to_utc(a) - 120 * 86400),
                           ("last", C.srv_to_utc(a)), ("masked", 0), ("holes", 0), ("depth_days", C.DEPTH_DAYS[b])))
    start("2021-11-17 08:00")
    # the paper trade already open at the start (stamped before the plan start): MISSED observe, a normal first start
    oid0 = U("2021-11-17 07:50") * 100 + 3
    add(srv("2021-11-17 08:01"), dec_ord(U("2021-11-17 07:50"), "BKB", oid0, 1, 0, 60000.0, 59000.0, U("2021-11-17 20:00"), rp=True))
    add(srv("2021-11-17 08:01"), jl(U("2021-11-17 07:50"), "PFILL", "BKB", ("oid", oid0), ("side", 1), ("bar", U("2021-11-17 07:50")),
                                    ("px", 60000.0), ("stop", 59000.0), ("st0", 59000.0), ("x", U("2021-11-17 20:00")), ("s_raw", 2600),
                                    ("s_paper", 26.0), ("rp", 1)))
    add(srv("2021-11-17 08:02"), jl(U("2021-11-17 08:02"), "MISSED", "BKB", ("oid", oid0), ("stamp", U("2021-11-17 07:50")), ("reason", "observe")))
    add(srv("2021-11-17 20:00"), jl(U("2021-11-17 20:00"), "PEXIT", "BKB", ("oid", oid0), ("side", 1), ("bar", U("2021-11-17 20:00")),
                                    ("px", 60100.0), ("stop", 59000.0), ("st0", 59000.0), ("x", U("2021-11-17 20:00")), ("reason", "time"),
                                    ("s_raw", 2600), ("s_paper", 26.0)))
    if "plan_late" in variant:                                          # an intent before the plan start: sized observe, B = P_in = 0
        on = U("2021-11-17 12:00") * 100 + C.SLEEVE_ID["NQB"]
        a = srv("2021-11-17 12:00")
        add(a, dec_ord(C.srv_to_utc(a), "NQB", on, 1, 0, 57100.0, 56500.0, U("2021-11-17 13:00")))
        add(a, jl(C.srv_to_utc(a), "PFILL", "NQB", ("oid", on), ("side", 1), ("bar", C.srv_to_utc(a)), ("px", 57100.0), ("stop", 56500.0),
                  ("st0", 56500.0), ("x", U("2021-11-17 13:00")), ("s_raw", 2600), ("s_paper", 26.0)))
        add(a, jl(C.srv_to_utc(a), "SIZE", "NQB", ("oid", on), ("side", 1), ("et", 0), ("lots", 0.0), ("want", 0.0), ("skip", "observe"),
                  ("B", 0.0), ("P_in", 0.0), ("rate", 0.0), ("m", 0.0), ("f", 1.0), ("unit", 0.0), ("w", 0.0), ("r", 0.0), ("budget", 0.0),
                  ("late", 0), ("quote", 0.0)))
        add(a + 300, jl(C.srv_to_utc(a) + 300, "MISSED", "NQB", ("oid", on), ("stamp", C.srv_to_utc(a)), ("reason", "observe")))
        add(srv("2021-11-17 13:00"), jl(U("2021-11-17 13:00"), "PEXIT", "NQB", ("oid", on), ("side", 1), ("bar", U("2021-11-17 13:00")),
                                        ("px", 57150.0), ("stop", 56500.0), ("st0", 56500.0), ("x", U("2021-11-17 13:00")), ("reason", "time"),
                                        ("s_raw", 2600), ("s_paper", 26.0)))
    if "observe_late" in variant:
        add(srv("2021-11-18 12:02"), jl(U("2021-11-18 12:02"), "MISSED", "NQB", ("oid", U("2021-11-18 12:00") * 100 + 7),
                                        ("stamp", U("2021-11-18 12:00")), ("reason", "observe")))
    if "early_dec" in variant:                                          # stamped at its decision time, two days before
        add(srv("2021-11-17 08:01"), jl(U("2021-11-15 08:00"), "DEC", "D4H", ("what", "info"), ("side", 0), ("v1", 1.5), ("v2", 0.0),
                                        ("at", U("2021-11-17 08:01"))))
    if "late_dec" in variant:                                           # a Friday-close decision written on Monday
        add(srv("2021-11-22 01:00"), dec_ord(U("2021-11-20 00:00"), "D4H", U("2021-11-20 00:00") * 100 + 9, -1, 1, 1860.0, 1875.0,
                                             U("2021-11-24 00:00")))

    def trade(code, sym_k, h, oid_at, side, ppx, stop, x_at, fill_px, sl, lots, ticket, exit_px, close_px, reason="time",
              close=("ok",), extra_fill=None):
        oid = U(oid_at) * 100 + C.SLEEVE_ID[code]
        f0 = srv(oid_at)
        et = 1 if code in ("ORX", "GFP", "D4H") else 0                  # stop orders: sent one bar late by design
        slip = 4e-4 if ("slip_gold" in variant and code in ("ORX", "GFP", "D4H")) else 0.0
        if slip:
            close_px = exit_px * (1 - side * slip)                      # the robot's close 4 bp worse than the paper's exit
        p_in = 10500.0 if ("p_in" in variant and f0 >= srv("2021-11-21 00:00")) else 10000.0
        add(f0, dec_ord(C.srv_to_utc(f0), code, oid, side, et, ppx, stop, U(x_at)))
        add(f0, jl(C.srv_to_utc(f0), "PFILL", code, ("oid", oid), ("side", side), ("bar", C.srv_to_utc(f0)), ("px", ppx), ("stop", stop),
                   ("st0", stop), ("x", U(x_at)), ("s_raw", 12), ("s_paper", 0.18)))
        add(f0, jl(C.srv_to_utc(f0), "SIZE", code, ("oid", oid), ("side", side), ("et", et), ("lots", lots), ("want", lots), ("skip", "none"),
                   ("B", 10000.0), ("P_in", p_in), ("rate", 10.0), ("m", 1.0), ("f", 1.0), ("unit", 1000.0), ("w", 0.0), ("r", 10.0),
                   ("budget", 1000.0), ("late", et), ("quote", fill_px)))
        # the quote the request went with: the fill is that quote (slip 0) or worse by slip (the broker's own slippage)
        q = fill_px / (1 + side * slip)
        add(f0 + 60, jl(C.srv_to_utc(f0 + 60), "SEND", code, ("oid", oid), ("side", side), ("lots", lots), ("want", lots), ("sl", sl),
                        ("bid", q - (0.12 if side > 0 else 0.0)), ("ask", q + (0.0 if side > 0 else 0.12)),
                        ("stamp", C.srv_to_utc(f0)), ("dev", 24), ("cut", "-"), ("result", "filled"), ("rc", 10009), ("s_raw", 12),
                        ("s_paper", 0.18)))
        risk = (side * (fill_px - sl) + 2 * h) * sym_k * lots
        add(f0 + 60, jl(C.srv_to_utc(f0 + 60), "FILL", code, ("oid", oid), ("ticket", ticket), ("side", side), ("px", fill_px), ("lots", lots),
                        ("sl", sl), ("listed", 1), ("risk", risk), ("budget", 1000.0), ("stamp", C.srv_to_utc(f0)), ("s_raw", 12),
                        ("s_paper", 0.18)))
        if extra_fill:
            add(f0 + 120, jl(C.srv_to_utc(f0 + 120), "FILL", code, ("oid", oid), ("ticket", extra_fill), ("side", side), ("px", fill_px),
                             ("lots", lots), ("sl", sl), ("listed", 1), ("risk", risk), ("budget", 1000.0), ("stamp", C.srv_to_utc(f0)),
                             ("s_raw", 12), ("s_paper", 0.18)))
        x0 = srv(x_at)
        add(x0, jl(C.srv_to_utc(x0), "PEXIT", code, ("oid", oid), ("side", side), ("bar", C.srv_to_utc(x0)), ("px", exit_px), ("stop", stop),
                   ("st0", stop), ("x", C.srv_to_utc(x0)), ("reason", reason), ("s_raw", 12), ("s_paper", 0.18)))
        for kind in close:
            if kind == "ok":
                add(x0 + 5, jl(C.srv_to_utc(x0) + 5, "CLOSE", code, ("ticket", ticket), ("magic", 20261200 + C.SLEEVE_ID[code]),
                               ("px", close_px), ("why", reason), ("rc", 10009), ("ok", 1)))
            elif kind == "refused":
                add(x0 + 5, jl(C.srv_to_utc(x0) + 5, "CLOSE", code, ("ticket", ticket), ("magic", 20261200 + C.SLEEVE_ID[code]),
                               ("px", 0.0), ("why", reason), ("rc", 10018), ("ok", 0)))
            elif kind == "race":
                add(x0 + 5, jl(C.srv_to_utc(x0) + 5, "CLOSE", code, ("ticket", ticket), ("magic", 20261200 + C.SLEEVE_ID[code]),
                               ("px", 0.0), ("why", reason), ("rc", 0), ("ok", 1)))
        if extra_fill:
            add(x0 + 6, jl(C.srv_to_utc(x0) + 6, "CLOSE", code, ("ticket", extra_fill), ("magic", 20261200 + C.SLEEVE_ID[code]),
                           ("px", close_px), ("why", reason), ("rc", 10009), ("ok", 1)))
        # what the balance books at the close: the robot's close price, the broker's stop (the race: at the stop; a paper stop
        # exit without CLOSE: at the paper's exit, which holds the lab's stop slippage), less the model's gold commission; a
        # refused or missing close books nothing (the position may still be open)
        px_out = close_px if "ok" in close else (stop if "race" in close else (exit_px if reason in ("stop", "trail", "gap") else None))
        if "orx_stopped" in variant and code == "ORX":                  # no CLOSE line: the broker's stop closed it (lab slippage)
            px_out = stop * (1 - side * 1e-4)
        if px_out is not None:
            pl = side * (px_out - fill_px) * lots * sym_k - 2 * h * lots * sym_k
            closes.append((x0 + 5, pl))
            if extra_fill:
                closes.append((x0 + 6, pl))
        return oid
    close_a = () if "no_close" in variant else (("refused",) if "close_refused" in variant else ("ok",))
    info = {"A": trade("ORX", k_gold, 0.03, "2021-11-18 10:00", 1, 1860.50, 1850.0, "2021-11-19 16:00", 1860.40, 1850.0, 0.1, 70000101,
                       1865.0, 1865.07, close=close_a)}
    info["E"] = trade("D4H", k_gold, 0.03, "2021-11-19 18:00", -1, 1862.0, 1872.0, "2021-11-22 12:00", 1861.90, 1872.03, 0.1, 70000102,
                      1855.0, 1855.10)
    if "bkb_stop" in variant:                                           # C ends at its paper stop: the broker's stop, no line
        info["C"] = trade("BKB", k_usd, 0.0, "2021-11-23 09:00", 1, 57000.0, 56000.0, "2021-11-23 15:00", 57010.0, 56000.0, 0.05,
                          70000104, 55990.0, 0.0, reason="stop", close=())
    else:
        info["C"] = trade("BKB", k_usd, 0.0, "2021-11-23 09:00", 1, 57000.0, 56000.0, "2021-11-23 15:00", 57010.0, 56000.0, 0.05,
                          70000104, 57500.0, 57490.0, close=("race",) if "race" in variant else ("ok",))
    info["B"] = trade("GFP", k_gold, 0.03, "2021-11-23 20:30", 1, 1858.0, 1850.0, "2021-11-23 23:00", 1858.10, 1850.03, 0.2, 70000103,
                      1859.0, 1859.02)
    if "n30_stop_grid" in variant:                                      # the broker stop on US100's 0.25 grid, away from the market
        info["D"] = trade("N30", k_usd, 0.0, "2021-11-24 16:31", 1, 16300.0, 16200.10, "2021-11-24 22:00", 16301.0, 16200.0, 1.0, 70000105,
                          16200.10 * (1 - 0.5e-4), 0.0, reason="stop", close=())
    else:
        info["D"] = trade("N30", k_usd, 0.0, "2021-11-24 16:31", 1, 16300.0, 16200.0, "2021-11-24 22:00", 16301.0, 16200.0, 1.0, 70000105,
                          16350.0, 16349.0, extra_fill=70000106 if "dup" in variant else None)
    # F: a paper trade whose intent was skipped (6 robot positions at most: SIZE skip=cap), so nothing was sent
    oid_f = U("2021-11-22 14:00") * 100 + C.SLEEVE_ID["F1E"]
    f0 = srv("2021-11-22 14:00")
    add(f0, dec_ord(C.srv_to_utc(f0), "F1E", oid_f, 1, 0, 4200.0, 4150.0, U("2021-11-22 20:00")))
    add(f0, jl(C.srv_to_utc(f0), "PFILL", "F1E", ("oid", oid_f), ("side", 1), ("bar", C.srv_to_utc(f0)), ("px", 4200.0), ("stop", 4150.0),
               ("st0", 4150.0), ("x", U("2021-11-22 20:00")), ("s_raw", 300), ("s_paper", 3.0)))
    add(f0, jl(C.srv_to_utc(f0), "SIZE", "F1E", ("oid", oid_f), ("side", 1), ("et", 0), ("lots", 0.0), ("want", 0.25), ("skip", "cap"),
               ("B", 10000.0), ("P_in", 10000.0), ("rate", 10.0), ("m", 1.0), ("f", 0.750978), ("unit", 1000.0), ("w", 0.0), ("r", 50.0),
               ("budget", 750.0), ("late", 0), ("quote", 4200.0)))
    add(srv("2021-11-22 20:00"), jl(U("2021-11-22 20:00"), "PEXIT", "F1E", ("oid", oid_f), ("side", 1), ("bar", U("2021-11-22 20:00")),
                                    ("px", 4210.0), ("stop", 4150.0), ("st0", 4150.0), ("x", U("2021-11-22 20:00")), ("reason", "time"),
                                    ("s_raw", 300), ("s_paper", 3.0)))
    info["F"] = oid_f
    # review4 variants
    if "slmod_refused" in variant or "slmod_once" in variant:          # BKB's stop move refused (freeze level), retried every 10 s
        u = U("2021-11-23 10:00")
        n_ref = 6 if "slmod_refused" in variant else 1
        for k in range(n_ref):
            add(srv("2021-11-23 10:00") + 10 * k, jl(u + 10 * k, "SLMOD", "BKB", ("ticket", 70000104), ("from", 56000.0), ("to", 56200.0),
                                                     ("rc", 10029), ("ok", 0)))
        if "slmod_once" in variant:
            add(srv("2021-11-23 10:00") + 10, jl(u + 10, "SLMOD", "BKB", ("ticket", 70000104), ("from", 56000.0), ("to", 56200.0),
                                                 ("rc", 10009), ("ok", 1)))
    if "reconnect_cap" in variant:                                      # the reconcile restates the dry sizing's skip (cap)
        w = srv("2021-11-22 16:00")
        add(w, dec_ord(C.srv_to_utc(f0), "F1E", oid_f, 1, 0, 4200.0, 4150.0, U("2021-11-22 20:00"), rp=True))
        add(w, jl(C.srv_to_utc(f0), "PFILL", "F1E", ("oid", oid_f), ("side", 1), ("bar", C.srv_to_utc(f0)), ("px", 4200.0), ("stop", 4150.0),
                  ("st0", 4150.0), ("x", U("2021-11-22 20:00")), ("s_raw", 300), ("s_paper", 3.0), ("rp", 1)))
        add(w, jl(C.srv_to_utc(f0), "SIZE", "F1E", ("oid", oid_f), ("side", 1), ("et", 0), ("lots", 0.0), ("want", 0.25), ("skip", "cap"),
                  ("B", 10000.0), ("P_in", 10000.0), ("rate", 10.0), ("m", 1.0), ("f", 0.750978), ("unit", 1000.0), ("w", 0.0), ("r", 50.0),
                  ("budget", 750.0), ("late", 0), ("quote", 4200.0), ("rp", 1)))
        add(w, jl(U("2021-11-22 16:00") + 2, "REBUILD", "-", ("n", 2), ("why", "reconnect"), ("from", U("2021-11-22 16:00") - 120 * 86400),
                  ("to", U("2021-11-22 16:00")), ("minutes", 172800), ("ms", 900)))
        add(w + 60, jl(U("2021-11-22 16:01"), "MISSED", "F1E", ("oid", oid_f), ("stamp", C.srv_to_utc(f0)), ("reason", "cap")))
    if "missed_twice" in variant:                                       # one OC4 trade refused, its MISSED written twice
        o = U("2021-11-24 17:00") * 100 + C.SLEEVE_ID["OC4"]
        a = srv("2021-11-24 17:00")
        add(a, dec_ord(C.srv_to_utc(a), "OC4", o, 1, 0, 16310.0, 16250.0, U("2021-11-24 18:00")))
        add(a, jl(C.srv_to_utc(a), "PFILL", "OC4", ("oid", o), ("side", 1), ("bar", C.srv_to_utc(a)), ("px", 16310.0), ("stop", 16250.0),
                  ("st0", 16250.0), ("x", U("2021-11-24 18:00")), ("s_raw", 12), ("s_paper", 0.12)))
        add(a, jl(C.srv_to_utc(a), "SIZE", "OC4", ("oid", o), ("side", 1), ("et", 0), ("lots", 1.0), ("want", 1.0), ("skip", "none"),
                  ("B", 10000.0), ("P_in", 10000.0), ("rate", 10.0), ("m", 1.0), ("f", 1.0), ("unit", 1000.0), ("w", 0.0), ("r", 60.0),
                  ("budget", 1000.0), ("late", 0), ("quote", 16310.0)))
        for k in (5, 6):
            add(a + 60 * k, jl(C.srv_to_utc(a) + 60 * k, "MISSED", "OC4", ("oid", o), ("stamp", C.srv_to_utc(a)), ("reason", "refused"),
                               ("rc", 10016)))
        add(srv("2021-11-24 18:00"), jl(U("2021-11-24 18:00"), "PEXIT", "OC4", ("oid", o), ("side", 1), ("bar", U("2021-11-24 18:00")),
                                        ("px", 16320.0), ("stop", 16250.0), ("st0", 16250.0), ("x", U("2021-11-24 18:00")), ("reason", "time"),
                                        ("s_raw", 12), ("s_paper", 0.12)))
    if "outage" in variant:                                             # offline from after BKB's fill (09:01) to 12:00 server
        w = srv("2021-11-23 12:00")
        on, ob = U("2021-11-23 11:00") * 100 + C.SLEEVE_ID["NQB"], U("2021-11-23 11:50") * 100 + C.SLEEVE_ID["BKE"]
        add(w, dec_ord(U("2021-11-23 11:00"), "NQB", on, 1, 0, 57100.0, 56500.0, U("2021-11-23 11:30"), rp=True))
        add(w, jl(U("2021-11-23 11:00"), "PFILL", "NQB", ("oid", on), ("side", 1), ("bar", U("2021-11-23 11:00")), ("px", 57100.0),
                  ("stop", 56500.0), ("st0", 56500.0), ("x", U("2021-11-23 11:30")), ("s_raw", 2600), ("s_paper", 26.0), ("rp", 1)))
        add(w, jl(U("2021-11-23 11:00"), "SIZE", "NQB", ("oid", on), ("side", 1), ("et", 0), ("lots", 0.05), ("want", 0.05), ("skip", "none"),
                  ("B", 10000.0), ("P_in", 10000.0), ("rate", 10.0), ("m", 1.0), ("f", 1.0), ("unit", 1000.0), ("w", 0.0), ("r", 600.0),
                  ("budget", 1000.0), ("late", 0), ("quote", 57100.0), ("rp", 1)))
        add(w, jl(U("2021-11-23 11:30"), "PEXIT", "NQB", ("oid", on), ("side", 1), ("bar", U("2021-11-23 11:30")), ("px", 57150.0),
                  ("stop", 56500.0), ("st0", 56500.0), ("x", U("2021-11-23 11:30")), ("reason", "time"), ("s_raw", 2600), ("s_paper", 26.0),
                  ("rp", 1)))
        add(w, dec_ord(U("2021-11-23 11:50"), "BKE", ob, 1, 0, 4250.0, 4200.0, U("2021-11-23 13:00"), rp=True))
        add(w, jl(U("2021-11-23 11:50"), "PFILL", "BKE", ("oid", ob), ("side", 1), ("bar", U("2021-11-23 11:50")), ("px", 4250.0),
                  ("stop", 4200.0), ("st0", 4200.0), ("x", U("2021-11-23 13:00")), ("s_raw", 300), ("s_paper", 3.0), ("rp", 1)))
        add(w, jl(U("2021-11-23 11:50"), "SIZE", "BKE", ("oid", ob), ("side", 1), ("et", 0), ("lots", 0.2), ("want", 0.2), ("skip", "none"),
                  ("B", 10000.0), ("P_in", 10000.0), ("rate", 10.0), ("m", 1.0), ("f", 1.0), ("unit", 1000.0), ("w", 0.0), ("r", 50.0),
                  ("budget", 1000.0), ("late", 0), ("quote", 4250.0), ("rp", 1)))
        add(w, jl(U("2021-11-23 12:00") + 2, "REBUILD", "-", ("n", 2), ("why", "reconnect"), ("from", U("2021-11-23 12:00") - 120 * 86400),
                  ("to", U("2021-11-23 12:00")), ("minutes", 172800), ("ms", 900)))
        add(w + 60, jl(U("2021-11-23 12:01"), "MISSED", "BKE", ("oid", ob), ("stamp", U("2021-11-23 11:50")), ("reason", "late")))
        if "orphan_reconcile" in variant:                               # a position whose paper trade ended during the outage
            add(w + 61, jl(U("2021-11-23 12:01") + 1, "CLOSE", "F1B", ("ticket", 70000199), ("magic", 20261205), ("px", 57300.0),
                           ("why", "orphan"), ("rc", 10009), ("ok", 1)))
            add(w + 61, jl(U("2021-11-23 12:01") + 1, "ORPHAN", "F1B", ("ticket", 70000199), ("why", "not_the_paper_trade"),
                           ("magic", 20261205), ("at", "reconcile")))
        add(srv("2021-11-23 13:00"), jl(U("2021-11-23 13:00"), "PEXIT", "BKE", ("oid", ob), ("side", 1), ("bar", U("2021-11-23 13:00")),
                                        ("px", 4260.0), ("stop", 4200.0), ("st0", 4200.0), ("x", U("2021-11-23 13:00")), ("reason", "time"),
                                        ("s_raw", 300), ("s_paper", 3.0)))
    if "orphan_mid" in variant:                                         # an ORPHAN far from any start or reconnection: still an anomaly
        add(srv("2021-11-24 15:00"), jl(U("2021-11-24 15:00"), "CLOSE", "F1B", ("ticket", 70000198), ("magic", 20261205), ("px", 57300.0),
                                        ("why", "orphan"), ("rc", 10009), ("ok", 1)))
        add(srv("2021-11-24 15:00"), jl(U("2021-11-24 15:00"), "ORPHAN", "F1B", ("ticket", 70000198), ("why", "not_the_paper_trade"),
                                        ("magic", 20261205), ("at", "reconcile")))
    if "restart" in variant or "restart_d2" in variant:                # stopped Friday night, started again on Monday
        add(srv("2021-11-19 23:30"), jl(U("2021-11-19 23:30"), "INIT", "-", ("deinit", 1), ("lines", 100), ("bars_fed", 9000), ("rebuilds", 1)))
        start("2021-11-22 08:00")
        add(srv("2021-11-22 08:02"), jl(U("2021-11-22 08:02"), "ADOPT", "D4H", ("oid", info["E"]), ("ticket", 70000102),
                                        ("open", U("2021-11-19 18:01")), ("stamp", U("2021-11-19 18:00")), ("why", "reconcile")))
    # the daily lines of the day before, at 00:00:30 of each server day the robot runs; the balance at the end of a day books
    # every close before it, plus the variants' outside moves (a deposit, a hand trade's loss, a payment)
    def bal_at(pd):
        b = 10000.0 + sum(pl for tc, pl in closes if tc < pd + 86400)
        if "deposit" in variant and pd >= srv("2021-11-20 00:00"):
            b += 500.0
        if "hand_loss" in variant and pd >= srv("2021-11-20 00:00"):
            b -= 700.0
        if "p_in" in variant and pd >= srv("2021-11-21 00:00"):
            b += 500.0
        return round(b, 2)
    restarted = "restart" in variant or "restart_d2" in variant
    stopped = {"2021-11-20", "2021-11-21"} if restarted else set()
    for d in range(18, 26):
        day = f"2021-11-{d:02d}"
        if day in stopped or (day == "2021-11-22" and restarted):
            continue                                                    # not running: no daily lines for these days
        prev_days = [srv(f"2021-11-{d - 1:02d} 00:00")]
        if style == "harness" and d in (20, 21):
            continue
        if style == "harness" and d == 22:
            prev_days = [srv("2021-11-19 00:00"), srv("2021-11-20 00:00"), srv("2021-11-21 00:00")]
        t = srv(f"{day} 00:00") + 30
        for pd in prev_days:
            wk = C.dow(pd) in (0, 6)
            add(t, jl(C.srv_to_utc(t), "AGG", "-", ("day", pd), ("XAUUSD", 0 if wk else 1300), ("US100", 0 if wk else 800),
                      ("BTCUSD", 0 if wk else 1440), ("ETHUSD", 0 if wk else 1440), ("dec", 10), ("pev", 3)))
            if not wk:
                add(t, jl(C.srv_to_utc(t), "COST", "XAUUSD", ("day", pd), ("raw_bp", 0.2), ("paper_bp", 0.53), ("model_bp", 0.47),
                          ("comm_usd_oz", 0.06), ("comm_n", 2)))
                for b_, m_ in (("US100", 0.37), ("BTCUSD", 2.96), ("ETHUSD", 13.0)):
                    add(t, jl(C.srv_to_utc(t), "COST", b_, ("day", pd), ("raw_bp", m_), ("paper_bp", m_), ("model_bp", m_)))
            add(t, jl(C.srv_to_utc(t), "DAY", "-", ("day", pd), ("balance", bal_at(pd)), ("equity", bal_at(pd)), ("bars_fed", 5000)))
    add(srv("2021-11-25 10:00"), jl(U("2021-11-25 10:00"), "INIT", "-", ("deinit", 9), ("lines", 300), ("bars_fed", 50000), ("rebuilds", 1)))
    L.sort(key=lambda x: x[0])
    files = {}
    for t, ln in L:
        files.setdefault(time.strftime("%Y%m%d", time.gmtime(t)) + ".log", []).append(ln)
    if "glued" in variant:                                              # a terminal line inside a robot file
        files["20211118.log"].insert(3, f"KR\t0\t09:58:01.112\tNetwork\t'{FAKE_LOGIN}': authorized on {FAKE_SERVER} through Access Point EU 2")
    for name, lines in files.items():
        write(os.path.join(folder, name), "\n".join(lines) + "\n", crlf=True)
    info["files"] = sorted(files)
    return info


def terminal_log(path, robot_lines=()):
    """MetaTrader's own log (MQL5/Logs or Logs/<yyyymmdd>.log): UTF-16 LE with a byte-order mark; the terminal's lines
    name the login, the server, the account holder and the Windows user folder; ReleveFP prints fini.txt there"""
    out = [f"KR\t0\t09:58:01.112\tNetwork\t'{FAKE_LOGIN}': authorized on {FAKE_SERVER} through Access Point EU 2 (ping: 21.33 ms, build 5120)",
           f"QJ\t0\t09:58:01.300\tNetwork\t'{FAKE_LOGIN}': terminal synchronized with First Prudential Markets Pty Ltd: 0 positions, 0 orders",
           f"GP\t0\t09:58:01.301\tTerminal\tMetaTrader 5 x64 build 5120 started for First Prudential Markets ({FAKE_NAME})",
           f"DE\t0\t09:58:02.000\tTerminal\tC:\\users\\{FAKE_USER}\\AppData\\Roaming\\MetaQuotes\\Terminal\\D0E8209F77C8CF37AD8BF550E51FF075",
           f"HN\t0\t09:59:00.000\tReleveFP (XAUUSD.r,M1)\tserver={FAKE_SERVER}"]
    for i, ln in enumerate(robot_lines):
        out.append(f"CS\t0\t10:{(i // 60) % 60:02d}:{i % 60:02d}.000\tClaudeRobot (XAUUSD.r,M1)\t{ln}")
    with open(path, "wb") as f:
        f.write(b"\xff\xfe" + ("\r\n".join(out) + "\r\n").encode("utf-16-le"))


def m1_flat(path, srv_from, srv_to, bid=1860.0, dip_at=None, dip_low=None):
    """a gold m1 file as ReleveFP writes it, a quiet market around `bid`; dip_at: one minute whose bid low goes to dip_low"""
    lines = ["time,bo,bh,bl,bc,ao,ah,al,ac,n,sp_mean,sp_max"]
    t = srv_from
    while t < srv_to:
        lo = dip_low if (dip_at is not None and t == dip_at) else bid - 0.30
        b = (bid, bid + 0.30, lo, bid + 0.10)
        a = tuple(x + 0.12 for x in b)
        lines.append(f"{t}," + ",".join(f"{x:.2f}" for x in b + a) + ",4,0.1200,0.12")
        t += 60
    write(path, "\n".join(lines) + "\n", crlf=True)


def leak_free(text):
    return [w for w in ACCOUNT_WORDS if w in text]


def test_review_journal(lit):
    """the review's journal cases (B1-B4, M1, M2, m2, m3), on hand-made multi-day journals"""
    base_dir = os.path.join(SCRATCH, "rv")

    def go(name, variant=(), style="live", extra=(), prep=None):
        jdir = os.path.join(base_dir, "j_" + name, "ClaudeRobot")
        info = md_journal(jdir, variant, style)
        if prep:
            prep(jdir, info)
        out = os.path.join(base_dir, "out_" + name)
        rc, so, se = run_tool("check_demo.py", ["--journals", os.path.dirname(jdir), "--out", out] + list(extra))
        r = json.load(open(os.path.join(out, "report.json"))) if rc == 0 else {}
        txt = (outputs_text(out) if rc == 0 else "") + so + se
        return rc, so, se, r, txt, info
    # the clean demo: a normal first start (MISSED observe before the plan start), weekend files: nothing abnormal
    rc, so, se, r, txt, info = go("base")
    if check("review base: runs", rc == 0, se[-1500:]):
        check("review M2: MISSED observe stamped before the plan start is not an anomaly, nothing abnormal",
              r["anomalies"] == [] and "Rien d'anormal" in so and len(r["journal"].get("missed_before_plan", [])) == 1, r["anomalies"])
        kinds = {p["ticket"]: p["exit_kind"] for p in r["fills"]["positions"]}
        check("review base: the five positions closed by the EA", kinds == {t: "ea_close" for t in (70000101, 70000102, 70000103, 70000104,
                                                                                                    70000105)}, kinds)
        trades = next((ln for ln in so.splitlines() if ln.startswith("Trades :")), "")
        tot = r["fills"]["per_sleeve"]["TOTAL"]
        check("review M1: the summary gives the total in bp and EUR, never points averaged across markets",
              "pb" in trades and "EUR" in trades and "pts" not in trades, trades)
        check("review M1: TOTAL has no point averages; points are per sleeve and per market",
              not any(k.endswith("pts_mean") and tot.get(k) is not None for k in tot) and tot.get("entry_diff_bp_mean") is not None
              and r["fills"].get("per_symbol", {}).get("XAUUSD", {}).get("entry_diff_pts_mean") is not None,
              {k: v for k, v in tot.items() if "pts" in k})
        rtxt = open(os.path.join(base_dir, "out_base", "report_fr.txt")).read()
        tline = next((ln for ln in rtxt.splitlines() if ln.strip().startswith("TOTAL")), "")
        check("review M1: report_fr.txt's TOTAL row has no points", tline and "pts" not in tline, tline)
        check("review B2: no missing day on a clean journal with weekend files", r["journal"].get("missing_files") == []
              and r["journal"].get("day_gaps") == [], r["journal"].get("day_gaps"))
    # the harness's weekend (Friday to Sunday DAY lines all in Monday's file, no weekend file): no false alarm
    rc, so, se, r, txt, info = go("harness_weekend", style="harness")
    check("review B2: harness-style weekend (no weekend files) is not a missing day", rc == 0 and not r.get("journal", {}).get("missing_files")
          and not any("manquant" in a for a in r.get("anomalies", [])), r.get("anomalies"))
    # stopped on Friday night and started again on Monday: no DAY lines for Friday to Sunday, explained, ADOPT of the same ticket
    rc, so, se, r, txt, info = go("restart", ("restart",))
    check("review B2/B3: a stop over the weekend (no DAY line Friday to Sunday) and an ADOPT of the same ticket are not anomalies",
          rc == 0 and r["anomalies"] == [] and r["journal"]["restarts"] == 1 and r["journal"].get("day_gaps") == [], r.get("anomalies"))
    # B2: Monday's file lost: named, the position whose exit was in it is flagged, the money estimate is incomplete
    def drop_monday(jdir, info):
        os.remove(os.path.join(jdir, "20211122.log"))
    rc, so, se, r, txt, info = go("drop_day", prep=drop_monday)
    if check("review B2 drop_day: runs", rc == 0, se[-1500:]):
        an = " | ".join(r["anomalies"])
        check("review B2: the missing daily file is named as an anomaly", "20211122.log" in an and "manquant" in an
              and "Rien d'anormal" not in so, an[:500])
        pe = {p["ticket"]: p for p in r["fills"]["positions"]}.get(70000102, {})
        check("review B2: the position whose exit lines were in the missing file is flagged (not 'open at the end')",
              pe.get("exit_kind") == "missing_exit" and "sans aucune sortie" in an, (pe.get("exit_kind"), pe.get("close_why")))
        m = r["fills"]["money_estimate"]
        check("review B2: the money estimate is marked incomplete", m is not None and m.get("complete") is False and m.get("missing_days", 0) >= 1, m)
    # B3: a second real position for an existing paper trade (same oid, new ticket, no DUP line)
    rc, so, se, r, txt, info = go("dup", ("dup",))
    check("review B3: an oid with two real tickets is an anomaly", rc == 0 and any("deux positions reelles" in a for a in r["anomalies"])
          and r["fills"].get("duplicates") and r["fills"]["duplicates"][0]["tickets"] == [70000105, 70000106], r.get("anomalies"))
    # B4: the EA's CLOSE line gone while the paper exited by time: flagged, kept out of the euros
    rc, so, se, r, txt, info = go("no_close", ("no_close",))
    if check("review B4 no_close: runs", rc == 0, se[-1500:]):
        pa = {p["ticket"]: p for p in r["fills"]["positions"]}[70000101]
        check("review B4: no CLOSE after a time exit is an anomaly, exit unknown (no price invented at the stop)",
              pa["exit_kind"] == "no_close_unknown" and pa.get("exit_real") is None and pa.get("gross_eur") is None
              and any("sans ligne CLOSE" in a for a in r["anomalies"]) and "Rien d'anormal" not in so, (pa["exit_kind"], pa.get("exit_real")))
        ok_total = r["fills"]["money_estimate"]["positions"] == 4
        check("review B4: the unknown exit is left out of the money totals", ok_total, r["fills"]["money_estimate"])
    # B4 with the releve's minutes: quotes never touched the stop -> not closed by the robot; a dip through the stop ->
    # the broker's stop (estimated at the stop, no anomaly)
    mdir = os.path.join(base_dir, "m1_quiet")
    os.makedirs(mdir, exist_ok=True)
    m1_flat(os.path.join(mdir, "m1_XAUUSD.csv"), srv("2021-11-18 09:00"), srv("2021-11-19 17:00"))
    rc, so, se, r, txt, info = go("no_close_quiet", ("no_close",), extra=("--bars", mdir, "--no-replay"))
    pa = {p["ticket"]: p for p in r.get("fills", {}).get("positions", [])}.get(70000101, {})
    check("review B4: with minutes that never touch its stop, the position is 'non fermee par le robot'",
          rc == 0 and pa.get("exit_kind") == "not_closed" and any("non fermee" in a for a in r["anomalies"]), (pa.get("exit_kind"), se[-500:]))
    mdir2 = os.path.join(base_dir, "m1_dip")
    os.makedirs(mdir2, exist_ok=True)
    m1_flat(os.path.join(mdir2, "m1_XAUUSD.csv"), srv("2021-11-18 09:00"), srv("2021-11-19 17:00"), dip_at=srv("2021-11-19 03:00"),
            dip_low=1849.95)
    rc, so, se, r, txt, info = go("no_close_dip", ("no_close", "orx_stopped"), extra=("--bars", mdir2, "--no-replay"))
    pa = {p["ticket"]: p for p in r.get("fills", {}).get("positions", [])}.get(70000101, {})
    check("review B4: with minutes whose bid low crosses the stop, the broker's stop is seen (no anomaly, exit at the stop)",
          rc == 0 and pa.get("exit_kind") == "broker_stop_seen" and abs((pa.get("exit_real") or 0) - 1850.0) < 1e-9
          and r["anomalies"] == [], (pa.get("exit_kind"), r.get("anomalies")))
    # B4: a refused close (rc 10018, ok=0) never followed by a success
    rc, so, se, r, txt, info = go("close_refused", ("close_refused",))
    pa = {p["ticket"]: p for p in r.get("fills", {}).get("positions", [])}.get(70000101, {})
    check("review B4: a CLOSE refused and never retried is an anomaly naming the retcode, exit unknown",
          rc == 0 and pa.get("exit_kind") == "close_refused" and pa.get("exit_real") is None
          and any("refusee" in a and "10018" in a for a in r["anomalies"]), (pa.get("exit_kind"), r.get("anomalies")))
    # m3: CLOSE px=0 rc=0 ok=1 (the broker's stop just before the robot's request): a broker stop, not an exit at price 0
    rc, so, se, r, txt, info = go("race", ("race",))
    pc = {p["ticket"]: p for p in r.get("fills", {}).get("positions", [])}.get(70000104, {})
    check("review m3: CLOSE px=0 rc=0 ok=1 is not an EA close at 0; without minutes the broker's stop cannot be checked: exit unknown "
          "(review3 R3-12), the stop level kept apart",
          rc == 0 and pc.get("exit_kind") == "race_unchecked" and pc.get("exit_real") is None and abs((pc.get("race_level") or 0) - 56000.0) < 1e-9
          and any("sans pouvoir le verifier" in a for a in r["anomalies"]), (pc.get("exit_kind"), pc.get("exit_real"), r.get("anomalies")))
    # M2 control: an observe after the plan start is an anomaly; an unset plan is an anomaly
    rc, so, se, r, txt, info = go("observe_late", ("observe_late",))
    check("review M2: a MISSED observe stamped after the plan start is still an anomaly", rc == 0
          and any("observe" in a for a in r["anomalies"]), r.get("anomalies"))
    rc, so, se, r, txt, info = go("plan_unset", ("plan_unset",))
    check("review: a PLAN state 'unset' is an anomaly", rc == 0 and any("plan non regle" in a for a in r["anomalies"]), r.get("anomalies"))
    # B1: MetaTrader's own logs beside the robot's files (same <yyyymmdd>.log names): skipped and named, never copied
    def experts_beside(jdir, info):
        robot = open(os.path.join(jdir, "20211118.log"), encoding="cp1252").read().splitlines()[:20]
        terminal_log(os.path.join(jdir, "experts_20211126.log"), robot)
    rc, so, se, r, txt, info = go("leak_beside", prep=experts_beside)
    check("review B1: an Experts log in the journals folder is skipped, named, and no account data reaches any output",
          rc == 0 and leak_free(txt) == [] and any(s_["file"] == "experts_20211126.log" for s_ in r["inputs"].get("skipped_files", []))
          and any("experts_20211126.log" in a for a in r["anomalies"]), (leak_free(txt), r.get("inputs", {}).get("skipped_files"), se[-300:]))

    def journal_instead(jdir, info):
        terminal_log(os.path.join(jdir, "20211118.log"))
    tl = os.path.join(base_dir, "terminal_20211118.log")
    terminal_log(tl)
    rc, so, se, r, txt, info = go("leak_instead", prep=journal_instead, extra=("--printed", tl))
    check("review B1: the terminal's Journal log instead of a robot file (and as --printed): no account data in any output",
          rc == 0 and leak_free(txt) == [], (leak_free(txt), se[-300:]))
    check("review B1: that file is named 'pas un journal du robot' and its day is reported missing",
          rc == 0 and any("20211118.log" in s_["file"] and "pas un journal du robot" in s_["why"] for s_ in r["inputs"].get("skipped_files", []))
          and "20211118.log" in " ".join(r["journal"].get("missing_files", [])), (r.get("inputs", {}).get("skipped_files"),
                                                                                  r.get("journal", {}).get("missing_files")))
    check("review m2: a --printed file without any robot line is an anomaly naming it", rc == 0
          and any("terminal_20211118.log" in a and "aucune ligne du robot" in a for a in r["anomalies"]), r.get("anomalies"))
    rc, so, se, r, txt, info = go("leak_glued", ("glued",))
    check("review B1: a terminal line inside a robot file is counted by file and line only, never copied",
          rc == 0 and leak_free(txt) == [] and r["inputs"].get("foreign_lines") == 1 and "text" not in (r["inputs"].get("foreign_first") or [{"text": 1}])[0],
          (leak_free(txt), r.get("inputs", {}).get("foreign_first")))


# ---------------------------------------------------------------------------------------------- tool 1: the review's cases
def test_review_tool1(lit):
    """read_mac_files.py: M5 (a holiday session complete when ReleveFP ran after it), m4 (InpExtraClosures windows that
    ClkInit takes), m5 (the probe's cents in the gold all-in spread), m6 (a cut fiche line), m7 (gold digits)"""
    import re as _re
    base_dir = os.path.join(SCRATCH, "rv1")

    def go(name, **kw):
        folder = os.path.join(base_dir, "in_" + name)
        out = os.path.join(base_dir, "out_" + name)
        make_releve(folder, lit, "good", **kw)
        rc, so, se = run_tool("read_mac_files.py", [folder, "--out", out])
        s = json.load(open(os.path.join(out, "summary.json"))) if rc == 0 else {"checks": []}
        return rc, so, se, {(c["market"], c["item"]): c for c in s["checks"]}
    rx = _re.compile(r"'(XAU \d{4}\.\d{2}\.\d{2} \d{2}:\d{2}-\d{4}\.\d{2}\.\d{2} \d{2}:\d{2})'")

    def valid_window(note):
        """the suggested window parses as ClkInit's 'XAU yyyy.mm.dd hh:mm-yyyy.mm.dd hh:mm', ends after it starts, <= 7 days"""
        m = rx.search(note or "")
        if not m:
            return False
        a, z = m.group(1)[4:].split("-")
        try:
            ta, tz = time.strptime(a, "%Y.%m.%d %H:%M"), time.strptime(z, "%Y.%m.%d %H:%M")
        except ValueError:
            return False
        d = calendar.timegm(tz) - calendar.timegm(ta)
        return 0 < d <= 7 * 86400

    # M5: FP closes gold at 13:00 New York on the Friday after Thanksgiving; ReleveFP ran on Saturday (no later bar)
    def early_friday(base, rec):
        if base != "XAUUSD":
            return rec
        t = rec["t"]
        return rec[~((t >= srv("2021-11-26 20:00")) & (t < srv("2021-11-27 00:00")))]
    rc, so, se, chk = go("early_sat", m1_to="2021-11-27 00:00", srv_now=srv("2021-11-27 10:41"), mutate=early_friday)
    c = chk.get(("XAUUSD", "holiday_2021-11-26"), {})
    check("review M5: the Friday after Thanksgiving is judged when ReleveFP ran on Saturday (not UNKNOWN), with the exact window",
          rc == 0 and c.get("status") == "DIFFERENT" and "'XAU 2021.11.26 13:00-2021.11.26 18:00'" in c.get("note", ""), (c, se[-300:]))

    # m4: the last gold bar of the Thanksgiving session the evening before (23:00 New York); the whole session closed
    def eve(base, rec):
        if base != "XAUUSD":
            return rec
        t = rec["t"]
        return rec[~((t >= srv("2021-11-25 06:00")) & (t < srv("2021-11-26 01:00")))]
    rc, so, se, chk = go("hol_eve", mutate=eve)
    c = chk.get(("XAUUSD", "holiday_2021-11-25"), {})
    check("review m4: a session ending the evening before gets a window ClkInit takes ('XAU 2021.11.24 23:00-2021.11.25 18:00')",
          rc == 0 and c.get("status") == "DIFFERENT" and valid_window(c.get("note")) and "2021.11.24 23:00-2021.11.25 18:00" in c.get("note", ""),
          c.get("note"))

    def whole(base, rec):
        if base != "XAUUSD":
            return rec
        t = rec["t"]
        return rec[~((t >= srv("2021-11-25 01:00")) & (t < srv("2021-11-26 01:00")))]
    rc, so, se, chk = go("hol_whole", mutate=whole)
    c = chk.get(("XAUUSD", "holiday_2021-11-25"), {})
    check("review m4: a session closed all day gets the exact window, not '(et la veille)'",
          rc == 0 and c.get("status") == "DIFFERENT" and valid_window(c.get("note")) and "et la veille" not in c.get("note", "")
          and "2021.11.24 17:00-2021.11.25 18:00" in c.get("note", ""), c.get("note"))
    # m5: the probe's gold commission (0.06 EUR on 0.01 lot, cents rounded) agrees with the model: the all-in spread adds
    # the model's 0.06 USD per oz, not the rounded 6.98 points
    rc, so, se, chk = go("cents")
    c = chk.get(("XAUUSD", "spread"), {})
    check("review m5: the gold all-in spread adds the model's commission when the probe agrees within its rounding",
          rc == 0 and "du modele" in str(c.get("broker")) and chk.get(("XAUUSD", "commission"), {}).get("status") == "OK", c.get("broker"))
    # m6: the gold line of fiches.csv cut short: the probe and the minutes still give the commission and spread checks
    rc, so, se, chk = go("cut", cut_fiche="XAUUSD")
    check("review m6: a cut gold fiche line keeps the commission and spread checks (sonde.csv, m1 file)",
          rc == 0 and chk.get(("XAUUSD", "commission"), {}).get("status") == "OK" and ("XAUUSD", "spread") in chk,
          [k for k in chk if k[0] == "XAUUSD"])

    # m7: gold with 3 digits: the digits note says the paper commission would be 10 times too small
    def three_digits(fi):
        g, _ = fi["XAUUSD"]
        g = dict(g, point=0.001, tick_size=0.001, tick_value=0.001 * 100 * 0.86)
        fi["XAUUSD"] = (g, 3)
    rc, so, se, chk = go("digits3", tweak=three_digits)
    c = chk.get(("XAUUSD", "digits"), {})
    check("review m7: 3-digit gold: the digits note says the robot's paper commission would be 10 times too small",
          rc == 0 and c.get("status") == "DIFFERENT" and "commission" in c.get("note", "") and "10 fois trop petite" in c.get("note", ""),
          c.get("note"))


# ---------------------------------------------------------------------------------------------- the second review: journals
def lines_of(path):
    return open(path, "rb").read().decode("cp1252").splitlines()


def drop_line(pred, k=0):
    """a prep that removes the k-th live line (rp=1 lines aside) matching pred, in file order"""
    def prep(jdir, info):
        n = 0
        for f in sorted(os.listdir(jdir)):
            p = os.path.join(jdir, f)
            ls = lines_of(p)
            for i, ln in enumerate(ls):
                if pred(ln) and "|rp=1" not in ln:
                    if n == k:
                        del ls[i]
                        write(p, "\n".join(ls) + "\n", crlf=True)
                        return
                    n += 1
        raise AssertionError("no line to drop")
    return prep


def test_review2_journal(lit):
    """the second review's journal cases (N1, N2, N3, N5, N6, N7, N8 a b e, N10), on hand-made journals"""
    base_dir = os.path.join(SCRATCH, "rv2j")

    def go(name, variant=(), style="live", extra=(), prep=None):
        jdir = os.path.join(base_dir, "j_" + name, "ClaudeRobot")
        info = md_journal(jdir, variant, style)
        if prep:
            prep(jdir, info)
        out = os.path.join(base_dir, "out_" + name)
        rc, so, se = run_tool("check_demo.py", ["--journals", os.path.dirname(jdir), "--out", out] + list(extra))
        rp = os.path.join(out, "report.json")
        r = json.load(open(rp)) if rc == 0 and os.path.exists(rp) else {}
        rt = os.path.join(out, "report_fr.txt")
        rtxt = open(rt, encoding="utf-8").read() if rc == 0 and os.path.exists(rt) else ""
        txt = (outputs_text(out) if rc == 0 else "") + so + se
        return {"rc": rc, "so": so, "se": se, "r": r, "txt": txt, "rtxt": rtxt, "info": info, "jdir": jdir,
                "an": " | ".join(r.get("anomalies", []))}

    # N1: the journal alone shows a lost line; the verdict says what could not be compared
    g = go("base")
    chk("review2 N1: without --bars the verdict says it covers only what could be compared ('Rien d'anormal sur ce qui a pu etre "
        "compare', 10 sleeves not compared)",
        lambda: (g["rc"] == 0 and g["r"]["anomalies"] == [] and "Rien d'anormal sur ce qui a pu etre compare" in g["so"]
                 and "10 sleeves non comparees" in g["so"], (g["so"][-500:], g["se"][-300:])))
    chk("review2 control N1: a clean journal has no missing line", lambda: (g["rc"] == 0 and not g["r"]["journal"].get("breaks"),
                                                                       g["r"].get("journal", {}).get("breaks")))
    for name, pred, word in (("dec", lambda ln: "|DEC|ORX|" in ln, "DEC (ORX order)"),
                             ("pfill", lambda ln: "|PFILL|F1E|" in ln, "PFILL (a paper trade with no real position)"),
                             ("fill", lambda ln: "|FILL|N30|" in ln, "FILL"), ("send", lambda ln: "|SEND|GFP|" in ln, "SEND"),
                             ("pexit", lambda ln: "|PEXIT|ORX|" in ln, "PEXIT (position closed by the robot)")):
        g = go("n1_" + name, prep=drop_line(pred))
        chk(f"review2 N1: a lost {word} line is reported from the journal alone ('ligne(s) du journal manquante(s)'), not "
            "'Rien d'anormal'",
            lambda: (g["rc"] == 0 and "ligne(s) du journal manquante(s)" in g["an"] and "Rien d'anormal" not in g["so"],
                     (g["an"][:500], g["se"][-300:])))
        if name == "fill":
            chk("review2 N1: a lost line makes the money estimate incomplete",
                lambda: (g["r"]["fills"]["money_estimate"]["complete"] is False, g["r"]["fills"]["money_estimate"]))

    def drop_monday(jdir, info):
        os.remove(os.path.join(jdir, "20211122.log"))
    g = go("n1_in_gap", prep=drop_monday)
    chk("review2 control N1: lines lost with a missing daily file are reported once (the file), not again as missing lines",
        lambda: (g["rc"] == 0 and "20211122.log" in g["an"] and "ligne(s) du journal manquante(s)" not in g["an"], g["an"][:600]))
    g = go("n1_restart", ("restart",))
    chk("review2 control N1: a stop on Friday and a start on Monday (ADOPT of the open position) give no missing line",
        lambda: (g["rc"] == 0 and g["r"]["anomalies"] == [] and not g["r"]["journal"].get("breaks"), g["an"][:500]))

    # N2: an exit at the broker's stop has no price in the journal: out of the averages, the euros and the headline
    hj = os.path.join(base_dir, "n2_hand", "ClaudeRobot")
    hinfo = handmade_journal(hj, "good")
    out = os.path.join(base_dir, "out_n2")
    rc, so, se = run_tool("check_demo.py", ["--journals", os.path.dirname(hj), "--out", out])
    r = json.load(open(os.path.join(out, "report.json"))) if rc == 0 else {}
    rtxt = open(os.path.join(out, "report_fr.txt"), encoding="utf-8").read() if rc == 0 else ""
    pos = {p["ticket"]: p for p in r.get("fills", {}).get("positions", [])}
    p1, p2 = pos.get(70000011, {}), pos.get(70000012, {})
    tot = r.get("fills", {}).get("per_sleeve", {}).get("TOTAL", {})
    chk("review2 N2: the broker-stop exit (no journal line) is left out of the exit average and the euros",
        lambda: (rc == 0 and abs(tot["exit_diff_bp_mean"] - p1["exit_diff_bp"]) < 1e-9
                 and abs(tot["exit_diff_eur_sum"] - p1["exit_diff_eur"]) < 1e-9, {k: tot.get(k) for k in ("exit_diff_bp_mean", "exit_diff_eur_sum")}))
    chk("review2 N2: it is counted apart, estimated at stop x (1 - the lab's stop slippage, gold 1 bp) and labelled as an estimate",
        lambda: (tot.get("estimated_exits") == 1 and abs(p2["exit_est"] - 1790.2 * (1 - 1.0e-4)) < 1e-9
                 and abs(p2["exit_diff_est_pts"] - (1789.8 - 1790.2 * (1 - 1.0e-4)) / 0.01) < 1e-6 and "stop courtier" in rtxt
                 and "estim" in rtxt, (tot.get("estimated_exits"), p2.get("exit_est"), p2.get("exit_diff_est_pts"))))
    chk("review2 N2: the stdout headline's exit figure uses the known exits only",
        lambda: (f"sortie {C.frs(p1['exit_diff_bp'], 2, 'pb')}" in so, next((ln for ln in so.splitlines() if ln.startswith("Trades")), so[-300:])))

    # N3: an Experts log of one day (Monday) holding a line stamped before the weekend: compared by file order
    g = go("n3_late_dec", ("late_dec",))
    mon = [ln for ln in lines_of(os.path.join(g["jdir"], "20211122.log")) if "|rp=1" not in ln]
    pf = os.path.join(base_dir, "experts_monday.log")
    utf16_printed(pf, mon)
    g2 = go("n3_printed", ("late_dec",), extra=("--printed", pf))
    chk("review2 N3: a one-day Experts log with a line stamped before the weekend gives no false alarm (window by file order)",
        lambda: (g2["rc"] == 0 and g2["r"]["printed"]["ok"] and g2["r"]["printed"]["n_live_not_printed"] == 0 and g2["r"]["anomalies"] == [],
                 (g2["r"].get("printed", {}).get("n_live_not_printed"), g2["an"][:400])))
    pf2 = os.path.join(base_dir, "experts_monday_missing.log")
    utf16_printed(pf2, mon[:5] + mon[6:])
    g3 = go("n3_printed_missing", ("late_dec",), extra=("--printed", pf2))
    chk("review2 control N3: a line missing inside that day's Experts log is still reported",
        lambda: (g3["rc"] == 0 and g3["r"]["printed"]["n_live_not_printed"] >= 1 and g3["r"]["anomalies"] != [],
                 g3["r"].get("printed", {}).get("n_live_not_printed")))
    chk("review2 N3: that missing line is the only one reported (not the weekend's lines)",
        lambda: (g3["rc"] == 0 and g3["r"]["printed"]["n_live_not_printed"] == 1, g3["r"].get("printed", {}).get("n_live_not_printed")))

    # N5: the last daily file lost
    def drop_last(jdir, info):
        os.remove(os.path.join(jdir, "20211125.log"))
    g = go("n5_last", prep=drop_last)
    chk("review2 N5: a journal whose last line is not a stop (INIT deinit) is flagged: robot still running, or last file missing",
        lambda: (g["rc"] == 0 and "dernier fichier manquant" in g["an"] and "Rien d'anormal" not in g["so"], g["an"][:500]))
    fdir = os.path.join(base_dir, "releve_n5")
    os.makedirs(fdir, exist_ok=True)
    write(os.path.join(fdir, "fini.txt"), "\n".join(["version=1.10", f"server={FAKE_SERVER}", "currency=EUR",
                                                    f"server_time={srv('2021-11-25 12:00')}", "server_minus_gmt_sec=7200"]) + "\n", crlf=True)
    g = go("n5_last_fini", prep=drop_last, extra=("--bars", fdir, "--no-replay"))
    chk("review2 N5: with ReleveFP's fini.txt (run on 25 Nov) the missing last file is named (20211125.log)",
        lambda: (g["rc"] == 0 and "20211125.log" in g["an"] and leak_free(g["txt"]) == [], g["an"][:500]))

    def drop_deinit(jdir, info):
        p = os.path.join(jdir, "20211125.log")
        write(p, "\n".join(ln for ln in lines_of(p) if "|deinit=" not in ln) + "\n", crlf=True)
    g = go("n5_running", prep=drop_deinit, extra=("--bars", fdir, "--no-replay"))
    chk("review2 control N5: a robot still running when the files were copied (journal up to ReleveFP's day) is not an anomaly",
        lambda: (g["rc"] == 0 and g["r"]["anomalies"] == [], g["an"][:400]))
    chk("review2 N5: the report says that robot was still running (no stop line at the end, journal up to ReleveFP's day)",
        lambda: (g["rc"] == 0 and "encore en marche" in g["rtxt"], g["rtxt"][-400:]))
    g = go("n5_complete", extra=("--bars", fdir, "--no-replay"))
    chk("review2 control N5: a journal ending with its stop line gives no end-of-journal remark",
        lambda: (g["rc"] == 0 and g["r"]["anomalies"] == [], g["an"][:400]))

    # N6: account words glued to robot lines never reach an output; every line is scanned before anything is kept
    def glue(jdir, info):
        p = os.path.join(jdir, "20211118.log")
        ls = lines_of(p)
        for i, ln in enumerate(ls):
            if "|PFILL|ORX|" in ln:
                ls[i] = ln + f"'{FAKE_LOGIN}': authorized on {FAKE_SERVER} through Access Point EU 2 {FAKE_NAME}"
        ls.insert(3, f"CR|{U('2021-11-18 09:00')}|ERROR|-|what=terminal said '{FAKE_LOGIN}': authorized on {FAKE_SERVER}, "
                     f"account {FAKE_LOGIN} {FAKE_NAME}")
        write(p, "\n".join(ls) + "\n", crlf=True)
        p = os.path.join(jdir, "20211117.log")                         # the same server name in a field that parses
        write(p, "\n".join(ln.replace("|ETHUSD=ETHUSD.r", f"|ETHUSD={FAKE_SERVER}") for ln in lines_of(p)) + "\n", crlf=True)
    g = go("n6_glued", prep=glue)
    chk("review2 N6: account words glued to a PFILL and an ERROR line reach no output (report.json, report_fr.txt, stdout)",
        lambda: (g["rc"] == 0 and leak_free(g["txt"]) == [], (leak_free(g["txt"]), g["se"][-300:])))
    chk("review2 N6/N7: those two lines (and, since review3 P3, the INIT line whose symbol name was edited) are unreadable and keep no text",
        lambda: (g["r"]["inputs"]["unparsable"] == 3 and all(set(b) <= {"file", "line", "why"} for b in g["r"]["inputs"]["unparsable_first"]),
                 g["r"].get("inputs", {}).get("unparsable_first")))

    # N7: values that are not numbers, a line cut after a valid prefix, and a fuzz of cut and glued lines
    def corrupt(jdir, info):
        p = os.path.join(jdir, "20211119.log")
        d = srv("2021-11-18 00:00")
        u = U("2021-11-19 00:00") + 40
        extra = [f"CR|{u}|COST|ETHUSD|day={d}|raw_bp=1.3e+01|paper_bp=abc|model_bp=1.3e+01",
                 f"CR|{u}|COST|BTCUSD|day={d}|raw_bp=2.9e+00|paper_bp=2.9e+00xyz|model_bp=2.96e+00",
                 "CR|1637053080|PSTOP|D4H|oid=16367328"]
        write(p, "\n".join(lines_of(p) + extra) + "\n", crlf=True)
    g = go("n7_corrupt", prep=corrupt)
    chk("review2 N7: a COST line whose paper_bp is not a number gives a report, no traceback", lambda: (g["rc"] == 0 and "Traceback" not in g["se"],
                                                                                           g["se"][-600:]))
    chk("review2 N7: those lines and a line cut after a valid prefix are counted unreadable",
        lambda: (g["r"]["inputs"]["unparsable"] == 3 and "illisible" in g["an"], g["r"].get("inputs", {}).get("unparsable_first")))

    def fuzz(jdir, info):
        rnd = random.Random(20211125)
        glue_txt = [f"'{FAKE_LOGIN}': authorized on {FAKE_SERVER} through Access Point EU 2",
                    f"MetaTrader 5 x64 build 5120 started for First Prudential Markets ({FAKE_NAME})",
                    f"C:\\users\\{FAKE_USER}\\AppData\\Roaming", f"server={FAKE_SERVER}", "\t0\t09:58:01.112\tNetwork", "|", "=", "e+", "nan",
                    "1.#INF", "-", "|x=1", "|rp=1", "|oid=", "é", "\x00"]
        for f in sorted(os.listdir(jdir)):
            p = os.path.join(jdir, f)
            ls = lines_of(p)
            out_ls = []
            for ln in ls:
                out_ls.append(ln)
                if not ln.startswith("CR|") or rnd.random() > 0.5:
                    continue
                m = rnd.randrange(4)
                if m == 0:
                    bad = ln[:rnd.randrange(4, max(5, len(ln)))]
                elif m == 1:
                    bad = ln + rnd.choice(glue_txt)
                elif m == 2:
                    parts = ln.split("|")
                    k = rnd.randrange(1, len(parts))
                    parts[k] = parts[k][:rnd.randrange(0, len(parts[k]) + 1)] + rnd.choice(glue_txt)
                    bad = "|".join(parts)
                else:
                    i = rnd.randrange(len(ln))
                    bad = ln[:i] + rnd.choice(glue_txt) + ln[i:]
                out_ls.append(bad.replace("\x00", "?"))
            with open(p, "wb") as fh:
                fh.write(("\r\n".join(out_ls) + "\r\n").encode("utf-8"))
    g = go("n7_fuzz", prep=fuzz)
    chk("review2 N7: a fuzz of cut, glued and edited robot lines: a report, no traceback, no account word in any output",
        lambda: (g["rc"] == 0 and "Traceback" not in g["se"] and leak_free(g["txt"]) == [], (g["se"][-800:], leak_free(g["txt"]))))

    # N8 a: the live period starts at the first INIT or REBUILD, not at a decision stamped earlier
    g = go("n8a", ("early_dec",))
    chk("review2 N8a: the live period starts at the start (INIT 2021-11-17 06:00 UTC), not at a DEC stamped two days before",
        lambda: (g["rc"] == 0 and "Periode en direct : du 2021-11-17 06:00 UTC" in g["rtxt"],
                 next((ln for ln in g["rtxt"].splitlines() if ln.startswith("Periode")), "")))
    # N8 b: a CLOCK line written in OnInit before INIT belongs to that start
    g = go("n8b", ("clock_first",))
    chk("review2 N8b: a CLOCK line written before INIT is part of that start (one start, no 'build None')",
        lambda: (g["rc"] == 0 and len(g["r"]["journal"]["starts"]) == 1 and "build None" not in g["so"] and "horloge" in g["an"]
                 and "aucune ligne INIT" not in g["an"], (len(g["r"].get("journal", {}).get("starts", [])), g["so"][:200], g["an"][:300])))
    # N8 e: the headline's entry mean leaves out the entries late by design (stop orders sent one bar after the paper)
    g = go("n8e")
    t8 = g["r"].get("fills", {}).get("per_sleeve", {}).get("TOTAL", {})
    on_time = [(16301.0 - 16300.0) / 16300.0 * 1e4, (57010.0 - 57000.0) / 57000.0 * 1e4]
    chk("review2 N8e: the total entry mean is taken on the entries on time only; the 3 late-by-design entries are shown apart",
        lambda: (g["rc"] == 0 and abs(t8["entry_diff_bp_mean"] - sum(on_time) / 2) < 1e-9 and t8.get("entries_late") == 3
                 and "en retard par construction" in g["rtxt"] and "en retard par construction" in g["so"],
                 {k: t8.get(k) for k in ("entry_diff_bp_mean", "entries_late", "entry_diff_late_bp_mean")}))

    # N10: a CLOSE without price (rc=0) or a paper stop exit with no CLOSE, whose minutes never reach the stop
    mq = os.path.join(base_dir, "m1_btc_quiet")
    os.makedirs(mq, exist_ok=True)
    m1_flat(os.path.join(mq, "m1_BTCUSD.csv"), srv("2021-11-23 08:00"), srv("2021-11-23 16:00"), bid=57200.0)
    md = os.path.join(base_dir, "m1_btc_dip")
    os.makedirs(md, exist_ok=True)
    m1_flat(os.path.join(md, "m1_BTCUSD.csv"), srv("2021-11-23 08:00"), srv("2021-11-23 16:00"), bid=57200.0,
            dip_at=srv("2021-11-23 12:00"), dip_low=55990.0)
    for variant, what in (("race", "a CLOSE without price (rc=0, ok=1)"), ("bkb_stop", "a paper stop exit with no CLOSE line")):
        g = go("n10_" + variant, (variant,), extra=("--bars", mq, "--no-replay"))
        pc = {p["ticket"]: p for p in g["r"].get("fills", {}).get("positions", [])}.get(70000104, {})
        chk(f"review2 N10: {what} whose minutes never reach the broker stop is an anomaly, no exit invented at the stop",
            lambda: (g["rc"] == 0 and pc.get("exit_kind") == "stop_not_reached" and pc.get("exit_real") is None
                     and any("jamais" in a and "stop" in a for a in g["r"]["anomalies"]), (pc.get("exit_kind"), g["an"][:400])))
        g = go("n10_dip_" + variant, (variant,), extra=("--bars", md, "--no-replay"))
        pc = {p["ticket"]: p for p in g["r"].get("fills", {}).get("positions", [])}.get(70000104, {})
        chk(f"review2 control N10: {what} whose minutes do cross the stop is a broker stop, no anomaly",
            lambda: (g["rc"] == 0 and pc.get("exit_kind") in ("broker_stop_race", "broker_stop_estimated") and g["r"]["anomalies"] == [],
                     (pc.get("exit_kind"), g["an"][:400])))


# ---------------------------------------------------------------------------------------------- the second review: tool 1
def test_review2_tool1(lit):
    """read_mac_files.py on ReleveFP 1.10 files (r1, sp_min, barres=), on 1.00 files, and N9 (a cut gold fiche, a cut m1 file);
    the ReleveFP.mq5 source itself for the 1.10 formats"""
    base_dir = os.path.join(SCRATCH, "rv2t1")

    def go(name, **kw):
        folder = os.path.join(base_dir, "in_" + name)
        out = os.path.join(base_dir, "out_" + name)
        make_releve(folder, lit, "good", **kw)
        rc, so, se = run_tool("read_mac_files.py", [folder, "--out", out])
        s = json.load(open(os.path.join(out, "summary.json"))) if rc == 0 else {"checks": [], "problems": []}
        return rc, so, se, {(c["market"], c["item"]): c for c in s["checks"]}, s
    src = lit["releve_src"]
    hdr = lit["m1_mq5"]
    chk("review2 N4: ReleveFP.mq5 is version 1.10 or later (review7: 1.11): m1 header unchanged plus sp_min at the end, r1 file with the "
        "terminal's M1 bars (CopyRates; days per market in InpRateSymbols, gold 200 since review3 R4), barres= at the end of each market's fini line",
        lambda: (re.search(r'#property version\s+"1\.1[01]"', src) is not None and hdr == lit["m1_v100"] + ",sp_min"
                 and lit["m1_v100"] == "time,bo,bh,bl,bc,ao,ah,al,ac,n,sp_mean,sp_max" and lit["r1_mq5"] == R1_HEADER
                 and re.search(r'input\s+string\s+InpRateSymbols\s*=\s*"XAUUSD:200,', src) is not None and "CopyRates(" in src
                 and '"r1_"' in src and re.search(r'"version=1\.1[01]\\n"', src) is not None and 'info = "barres="' in src and '" jours_barres="' in src
                 and '" erreur_barres="' in src and re.search(r'info_m\[i\] \+ \(info_r\[i\] != ""', src) is not None, (hdr, lit["r1_mq5"])))
    rc, so, se, ck, s = go("v110")
    chk("review2 N4: ReleveFP 1.10's r1 files are read: bar count against fini.txt's barres= (OK) and the days covered",
        lambda: (rc == 0 and ck.get(("XAUUSD", "r1_rows"), {}).get("status") == "OK" and ck.get(("BTCUSD", "r1_rows"), {}).get("status") == "OK"
                 and "jours" in str(ck.get(("XAUUSD", "r1_rows"), {}).get("broker")), (se[-500:], ck.get(("XAUUSD", "r1_rows")))))
    chk("review2 N4: SPEC 10.3 answered from the r1 and m1 files (information only): share of minutes where MqlRates.spread equals "
        "the ticks' minimum, the open, the close, the rounded mean",
        lambda: (ck.get(("XAUUSD", "bar_spread"), {}).get("status") == "OK" and "minimum 100" in str(ck[("XAUUSD", "bar_spread")]["broker"])
                 and "ouverture 100" in str(ck[("XAUUSD", "bar_spread")]["broker"]) and "fermeture 0" in str(ck[("XAUUSD", "bar_spread")]["broker"])
                 and not any(c["status"] == "DIFFERENT" for k, c in ck.items() if k[1] == "bar_spread"), ck.get(("XAUUSD", "bar_spread"))))
    rc, so, se, ck, s = go("v100", version="1.00")
    chk("review2 N4: version 1.00 files (no sp_min, no r1, no barres=) are still read without error or reading problem",
        lambda: (rc == 0 and not s.get("problems") and ck.get(("XAUUSD", "releve_days"), {}).get("status") == "OK"
                 and ck.get(("XAUUSD", "m1_rows"), {}).get("status") == "OK", (se[-500:], s.get("problems"))))
    # N9 a: no usable gold fiche line: the Friday session check stays, UNKNOWN
    rc, so, se, ck, s = go("n9_cut_gold", cut_fiche="XAUUSD")
    chk("review2 N9: with the gold fiche line cut, the Friday gold session check is still there, UNKNOWN (not missing)",
        lambda: (rc == 0 and ck.get(("XAUUSD", "friday_session"), {}).get("status") == "UNKNOWN"
                 and ck.get(("XAUUSD", "releve_days"), {}).get("status") == "OK", [k for k in ck if k[0] == "XAUUSD"]))
    # N9 b: an m1 file cut half way (the oldest days lost) while fini.txt counts every minute
    rc, so, se, ck, s = go("n9_cut_m1", cut_m1="BTCUSD")
    chk("review2 N9: an m1 file shorter than fini.txt's minutes= is DIFFERENT (file cut, oldest days lost)",
        lambda: (rc == 0 and ck.get(("BTCUSD", "m1_rows"), {}).get("status") == "DIFFERENT"
                 and ck.get(("ETHUSD", "m1_rows"), {}).get("status") == "OK", (ck.get(("BTCUSD", "m1_rows")), ck.get(("ETHUSD", "m1_rows")))))


# ---------------------------------------------------------------------------------------------- tool 2: replay end to end
SPAN = (srv("2021-06-01 00:00"), srv("2021-12-01 00:00"))
PLAN0 = srv("2021-05-01 00:00")


LIVE_FROM = srv("2021-10-05 00:00")                                   # 126 days after SPAN's start: gold's 120-day depth is there


def raw_gold(base, rec):
    """export_frames.py --raw-h 3 for gold: the lab's spread holds the 6-point commission; the broker's raw quote is the
    lab bid + 3 points with a spread 6 points smaller, so that the robot (h = 3 points) sees the lab's quotes again"""
    if base != "XAUUSD":
        return rec
    rec = rec.copy()
    for k in "ohlc":
        rec[k] = rec[k] + 3
    rec["s"] = np.maximum(rec["s"] - 6, 0)
    return rec


def harness_live(name, span, env_extra, mutate=None, frm=LIVE_FROM, to=None, restarts=(), exe=None):
    """the 'live' robot: dist/ClaudeRobot.mq5 in the harness (demo_check_release, gold commission 6 points) on in-sample
    bars, with the user's risk table S7 (SPEC 1 step 3; env_extra may change it); its journal then gets harness=0 in its
    INIT lines, as the release file writes. to: the run's end (default the bars' end); restarts: [(stop, back, env)] a stop
    at server time stop and a start at back with these inputs changed (review4 A10); exe: another build of the release file
    (the self-test's copy of the harness with MOCK_SLEEP, review4b ADV5-2)"""
    import check_demo as D
    from build import replay
    if exe is None:
        exe, warn, cached = D.build_exe(6)
    else:
        cached = True
    work = os.path.join(SCRATCH, name)
    os.makedirs(os.path.join(work, "bars"), exist_ok=True)
    bars = {}
    for base in C.ROBOT_BASES:
        dg, rec = bars_2021(base, *span)
        rec = raw_gold(base, rec)
        if mutate:
            rec = mutate(base, rec)
        p = os.path.join(work, "bars", f"{base}.r.bin")
        D.write_bin(p, dg, rec["t"].astype(np.int64), rec["o"].astype(np.int64), rec["h"].astype(np.int64), rec["l"].astype(np.int64),
                    rec["c"].astype(np.int64), rec["s"].astype(np.int64))
        bars[f"{base}.r"] = p
    env = {"MOCK_INPUT_InpPush": "false", "MOCK_ACCOUNT": "demo", "MOCK_BALANCE": "10000", "MOCK_INPUT_InpRiskTable": S7}
    env.update(env_extra)
    files = os.path.join(work, "files")
    seg, fresh, wall = frm, True, 0.0
    for stop, back, env2 in restarts:
        so, w = replay(exe, files, bars, env=env, fresh=fresh, frm=seg, to=stop, timeout=3600)
        wall += w
        fresh, seg = False, back
        env = dict(env, **env2)
    so, w = replay(exe, files, bars, env=env, fresh=fresh, frm=seg, to=to, timeout=3600)
    wall += w
    for f in os.listdir(os.path.join(files, "ClaudeRobot")):
        p = os.path.join(files, "ClaudeRobot", f)
        t = open(p).read().replace("|harness=1|", "|harness=0|")
        open(p, "w").write(t)
    return files, wall, cached


SLEEP_ANCHOR = "   ev.erase(std::unique(ev.begin(), ev.end()), ev.end());\n"
SLEEP_PATCH = """   // review4b (the self-test's own copy of the harness, never check/'s file): MOCK_SLEEP="a-b,a-b" removes every event in
   // [a, b) (server seconds): the Mac asleep, the MetaTrader process frozen (no timer pass, no tick); the broker's stops still
   // run, booked at the next event
   if(const char *sl = getenv("MOCK_SLEEP"))
     {
      std::vector<std::pair<long, long>> w;
      std::stringstream hs(sl);
      string it;
      while(std::getline(hs, it, ','))
        {
         long a = 0, b = 0;
         if(sscanf(it.c_str(), "%ld-%ld", &a, &b) == 2) w.push_back({a, b});
        }
      std::vector<long> kept;
      for(long t : ev)
        {
         bool asleep = false;
         for(auto &x : w) if(t >= x.first && t < x.second) asleep = true;
         if(!asleep) kept.push_back(t);
        }
      ev.swap(kept);
     }
"""


def sleep_harness_exe(root):
    """the release file dist/ClaudeRobot.mq5 built against a copy of check/'s harness under root (the scratch folder; check/
    itself is never changed) that adds MOCK_SLEEP: the Mac asleep, its process frozen (review4b ADV5-2). Returns the binary"""
    import importlib.util
    chk = os.path.join(root, "robot", "check")
    os.makedirs(chk, exist_ok=True)
    for f in ("build.py", "to_cpp.py", "mql5_shim.h", "mock_faults.h"):
        shutil.copy(os.path.join(C.CHECK, f), chk)
    src = open(os.path.join(C.CHECK, "mock_replay.h")).read()
    if src.count(SLEEP_ANCHOR) != 1:
        raise RuntimeError("mock_replay.h changed: the MOCK_SLEEP patch of the self-test no longer applies")
    with open(os.path.join(chk, "mock_replay.h"), "w") as f:
        f.write(src.replace(SLEEP_ANCHOR, SLEEP_ANCHOR + SLEEP_PATCH))
    for d in ("src", "dist"):
        link = os.path.join(root, "robot", d)
        if not os.path.lexists(link):
            os.symlink(os.path.join(C.ROBOT, d), link)
    spec = importlib.util.spec_from_file_location("build_sleep_copy", os.path.join(chk, "build.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    exe, warn = mod.build(C.DIST, name="sleep_release", comm_pts=6)
    return exe


def csv_dir(name, span, lit, mutate=None, style="open", version="1.10", r1=False):
    """ReleveFP's files of the 'live' robot's bars: m1_<BASE>.csv (style and version as m1_text), and with r1 the terminal's
    own bars r1_<BASE>.csv (ReleveFP 1.10)"""
    d = os.path.join(SCRATCH, name)
    os.makedirs(d, exist_ok=True)
    for base in C.ROBOT_BASES:
        dg, rec = bars_2021(base, *span)
        rec = raw_gold(base, rec)
        if mutate:
            rec = mutate(base, rec)
        write(os.path.join(d, f"m1_{base}.csv"), m1_text(rec, dg, lit, style, 0, version))
        if r1:
            write(os.path.join(d, f"r1_{base}.csv"), r1_text(rec, dg, lit))
    return d


def test_tool2_replay(lit):
    t0 = time.time()
    obs, wall, cached = harness_live("live_observer", SPAN, {"MOCK_INPUT_InpTrade": "false"})
    check("tool2 replay: harness build demo_check_release and the 'live' observer run", os.path.isdir(obs), {"wall": wall, "cached": cached})
    full = csv_dir("csv_full", SPAN, lit)
    out = os.path.join(SCRATCH, "out_replay_full")
    rc, so, se = run_tool("check_demo.py", ["--journals", obs, "--bars", full, "--out", out])
    if not check("tool2 replay full: runs", rc == 0, se[-3000:]):
        return
    r = json.load(open(os.path.join(out, "report.json")))
    rp = r["replay"]
    check("tool2 replay full: replay done", rp.get("status") == "done", rp.get("why"))
    if rp.get("status") != "done":
        return
    cal = rp["spread"]["calibration"]
    check("tool2 replay full: spread convention measured on the paper lines = 'open' (all bars match)",
          rp["spread"]["used"] == "open" and cal["paper_lines"]["open"]["match"] == cal["paper_lines"]["open"]["n"] > 100
          and cal["paper_lines"]["close"]["match"] == 0, cal["paper_lines"])
    cm = rp["comparison"]
    eq = {ev: cm["by_event"].get(ev, {}).get("equal", 0) + cm["by_event"].get(ev, {}).get("tol", 0) for ev in ("DEC", "PFILL", "PEXIT", "SIZE")}
    check("tool2 replay full: lines compared line for line, none different",
          not cm["differences"] and eq["DEC"] > 200 and eq["PFILL"] > 50 and eq["PEXIT"] > 50 and eq["SIZE"] > 50, (eq, cm["differences"][:3]))
    check("tool2 replay full: every sleeve compared, D4H after its 120-day warm-up",
          all(v != "jamais" for v in rp["span"]["sleeves_compared_from"].values()), rp["span"]["sleeves_compared_from"])
    check("tool2 replay full: SIZE compared with the account fields and the skip (observer)",
          rp["size_mode"]["live_copy_observer"] and "B" in rp["size_mode"]["compared"] and "skip" in rp["size_mode"]["compared"], rp["size_mode"])
    sb = rp["side_by_side"]
    check("tool2 replay full: bars per day (AGG) and daily spreads (COST) identical", sb["agg_days"] > 40 and sb["agg_days_same"] == sb["agg_days"]
          and sb["cost_n"] > 120 and sb["cost_same"] == sb["cost_n"], {k: sb[k] for k in ("agg_days", "agg_days_same", "cost_n", "cost_same")})
    check("tool2 replay full: nothing abnormal", r["anomalies"] == [] and "Rien d'anormal" in so, r["anomalies"])
    check("tool2 replay full: replay files outside the repository", os.path.isdir(os.path.join(out, "replay", "files")))
    txt_full = open(os.path.join(out, "report_fr.txt"), encoding="utf-8").read()
    chk("review3 U6: report_fr.txt counts the compared lines in French ('egales'), not 'equal'",
        lambda: ("egales" in txt_full and "equal " not in txt_full, next((ln for ln in txt_full.splitlines() if "DEC " in ln), "")))
    # review2 follow-up (found on the reviewer's missing-last-day run): the robot stopped cleanly after a decision's stamp
    # but before the moment it writes that decision (D4H's DEC stamped 17:59 UTC is written after the 22:00 DAY line):
    # the replay's line comes after the stop, so it is no difference
    now_ev = {"INIT", "SELFTEST", "PLAN", "REBUILD", "READY", "NOTREADY", "SEND", "FILL", "CLOSE", "SLMOD", "SLFIX", "REFUSED", "ADOPT",
              "ORPHAN", "DUP", "MISSED", "LATEBAR", "GAP", "SETTLE", "CLOCK", "MARK", "LOCK", "TAKEOVER", "WATCH", "ERROR", "AGG", "COST", "DAY"}
    jobs = os.path.join(obs, "ClaudeRobot")
    order, now = [], None                                   # (file, line index, stamp, write time, event) in file order
    for f in sorted(os.listdir(jobs)):
        for i, ln in enumerate(open(os.path.join(jobs, f)).read().split("\n")):
            p = ln.split("|")
            if len(p) < 4 or p[0] != "CR" or "|rp=1" in ln:
                continue
            if p[2] in now_ev:
                now = int(p[1]) if now is None else max(now, int(p[1]))
            order.append((f, i, int(p[1]), max(now or 0, int(p[1])), p[2]))
    cand = None
    for k in range(len(order) - 1, len(order) // 2, -1):    # the latest one: every sleeve is past its warm-up
        f, i, t, w, ev = order[k]
        first = next(j for j in range(k, -1, -1) if j == 0 or order[j - 1][3] < w)    # the first line written at w
        if (ev == "DEC" and w - t >= 7200 and t < C.srv_to_utc(SPAN[1]) - 2 * 86400 and first > 0 and order[first - 1][3] < w - 120
                and order[first][0] == f):
            cand = (f, order[first][1], w, t)
            break
    stop_dir = os.path.join(SCRATCH, "live_stop_before_write", "ClaudeRobot")
    if cand:
        shutil.copytree(jobs, stop_dir)
        for g in sorted(os.listdir(stop_dir)):
            if g > cand[0]:
                os.remove(os.path.join(stop_dir, g))
        lines = open(os.path.join(stop_dir, cand[0])).read().split("\n")[:cand[1]]
        cr = "\r" if lines and lines[-1].endswith("\r") else ""
        lines.append(f"CR|{cand[2] - 60}|INIT|-|deinit=1|lines={len(order)}|bars_fed=100000|rebuilds=1|masked_XAUUSD=0|masked_US100=0|"
                     f"masked_BTCUSD=0|masked_ETHUSD=0" + cr)
        open(os.path.join(stop_dir, cand[0]), "w").write("\n".join(lines) + "\n")
    outs = os.path.join(SCRATCH, "out_stop_before_write")
    rc, sos, se = run_tool("check_demo.py", ["--journals", os.path.dirname(stop_dir), "--bars", full, "--out", outs]) if cand else (1, "", "")
    rs = json.load(open(os.path.join(outs, "report.json"))) if rc == 0 else {}
    ds_ = rs.get("replay", {}).get("comparison", {}).get("differences", [])
    chk("review2 follow-up: a robot stopped after a decision's stamp but before it writes that decision (the next server midnight) "
        "gives no replay difference and nothing abnormal",
        lambda: (cand is not None and rc == 0 and not ds_ and rs.get("anomalies") == [] and "Rien d'anormal" in sos,
                 (cand and (cand[0], C.utc_txt(cand[3]), C.utc_txt(cand[2])), se[-300:], [(d["kind"], d["event"], d["code"], d["when"])
                                                                                       for d in ds_][:3], rs.get("anomalies"))))
    # the VPS copy's printed lines against the Mac's files (shadow weeks, SPEC 10.12 step 3): equal
    jl_obs = []
    for f in sorted(os.listdir(os.path.join(obs, "ClaudeRobot"))):
        jl_obs += [ln for ln in open(os.path.join(obs, "ClaudeRobot", f)).read().splitlines() if ln and "|rp=1" not in ln]
    pv = os.path.join(SCRATCH, "experts_vps.log")
    utf16_printed(pv, jl_obs, vps=True)
    outv = os.path.join(SCRATCH, "out_vps")
    rc, sov, se = run_tool("check_demo.py", ["--journals", obs, "--printed", pv, "--out", outv])
    rv = json.load(open(os.path.join(outv, "report.json"))) if rc == 0 else {}
    pr = rv.get("printed", {})
    eqv = sum(v.get("equal", 0) for v in pr.get("comparison", {}).get("by_event", {}).values())
    check("tool2 VPS printed lines: another copy, SPEC 10.12 lines equal", rc == 0 and pr.get("kind", "").startswith("autre")
          and pr.get("ok") and eqv > 500, (se[-300:], pr.get("kind"), eqv, (pr.get("comparison") or {}).get("differences", [])[:2]))
    check("tool2 VPS printed lines: no account data in the outputs", FAKE_LOGIN not in outputs_text(outv) + sov)
    # an --out inside the repository is refused
    rc, _, se = run_tool("check_demo.py", ["--journals", obs, "--out", os.path.join(C.ROBOT, "demo", "x_out")])
    check("tool2: --out inside the repository refused", rc != 0 and not os.path.exists(os.path.join(C.ROBOT, "demo", "x_out")), se[-200:])
    # ETHUSD's minutes missing: its sleeves are left out, the others compared
    noeth = os.path.join(SCRATCH, "csv_no_eth")
    shutil.copytree(full, noeth)
    os.remove(os.path.join(noeth, "m1_ETHUSD.csv"))
    out6 = os.path.join(SCRATCH, "out_no_eth")
    rc, so6, se = run_tool("check_demo.py", ["--journals", obs, "--bars", noeth, "--out", out6])
    r6 = json.load(open(os.path.join(out6, "report.json"))) if rc == 0 else {}
    c6 = r6.get("replay", {}).get("comparison", {})
    check("tool2 replay without ETHUSD minutes: BKE and F1E left out, no difference elsewhere",
          rc == 0 and not c6.get("differences") and c6["excluded"].get("pas de minutes du releve pour ce marche", 0) > 0,
          (se[-300:], c6.get("excluded"), (c6.get("differences") or [])[:2]))
    # the files of the first days lost (no INIT line): said, and the replay still runs with the default inputs
    noinit = os.path.join(SCRATCH, "live_no_init", "ClaudeRobot")
    shutil.copytree(os.path.join(obs, "ClaudeRobot"), noinit)
    for f in sorted(os.listdir(noinit))[:3]:
        os.remove(os.path.join(noinit, f))
    out7 = os.path.join(SCRATCH, "out_no_init")
    rc, so7, se = run_tool("check_demo.py", ["--journals", os.path.dirname(noinit), "--bars", full, "--out", out7])
    r7 = json.load(open(os.path.join(out7, "report.json"))) if rc == 0 else {}
    c7 = r7.get("replay", {}).get("comparison", {})
    check("tool2 journal without INIT: reported, replay with the default inputs, no difference",
          rc == 0 and any("INIT" in x for x in r7.get("anomalies", [])) and not c7.get("differences")
          and sum(v.get("equal", 0) for v in c7.get("by_event", {}).values()) > 500, (se[-300:], r7.get("anomalies"), (c7.get("differences") or [])[:2]))
    # one live line changed: exactly one difference, both lines shown
    jdir = os.path.join(obs, "ClaudeRobot")
    bad = os.path.join(SCRATCH, "live_observer_edited", "ClaudeRobot")
    shutil.copytree(jdir, bad)
    files = sorted(os.listdir(bad))
    target = None
    for f in files[len(files) // 2:]:
        lines = open(os.path.join(bad, f)).read().split("\n")
        for i, ln in enumerate(lines):
            if "|PFILL|BKB|" in ln and "|rp=1" not in ln:
                lines[i] = ln.replace("|px=", "|px=9")
                target = ln
                break
        if target:
            open(os.path.join(bad, f), "w").write("\n".join(lines))
            break
    out2 = os.path.join(SCRATCH, "out_replay_edited")
    rc, so2, se = run_tool("check_demo.py", ["--journals", os.path.dirname(bad), "--bars", full, "--out", out2])
    r2 = json.load(open(os.path.join(out2, "report.json"))) if rc == 0 else {}
    d2 = r2.get("replay", {}).get("comparison", {}).get("differences", [])
    check("tool2 replay edited: the changed PFILL is the one difference, with its live and replay lines",
          len(d2) == 1 and d2[0]["event"] == "PFILL" and d2[0]["fields"] == ["px"] and d2[0]["replay"] == target, d2[:2])
    check("tool2 replay edited: 'rien d'anormal' not said", "Rien d'anormal" not in so2)
    # ReleveFP's 30 last days only: the long warm-ups are left out, the short ones compared and equal
    short = csv_dir("csv_short", (srv("2021-11-01 00:00"), SPAN[1]), lit)
    out3 = os.path.join(SCRATCH, "out_replay_short")
    rc, so3, se = run_tool("check_demo.py", ["--journals", obs, "--bars", short, "--out", out3])
    r3 = json.load(open(os.path.join(out3, "report.json"))) if rc == 0 else {}
    c3 = r3.get("replay", {}).get("comparison", {})
    eq3 = sum(v.get("equal", 0) + v.get("tol", 0) for v in c3.get("by_event", {}).values())
    check("tool2 replay 30 days: compared where the warm-up allows, no difference",
          rc == 0 and not c3.get("differences") and eq3 > 50 and c3["excluded"].get("echauffement du rejeu (pas assez d'historique avant)", 0) > 0,
          (eq3, c3.get("excluded"), (c3.get("differences") or [])[:2]))
    # M3: the coverage of each sleeve is said, in report_fr.txt and on stdout, with the InpDays to ask for
    cov3 = r3.get("replay", {}).get("coverage", {})
    txt3 = open(os.path.join(out3, "report_fr.txt")).read() if rc == 0 else ""
    check("review M3: with 30 days of minutes, each sleeve's coverage is printed ('jamais' for F1B, F1E, OC4, GFP, D4H) and "
          "ReleveFP 1.10's r1 bars are asked for (InpRateSymbols; review4: no more InpDays), on stdout too",
          rc == 0 and all(cov3.get(c, {}).get("never") for c in ("F1B", "F1E", "OC4", "GFP", "D4H"))
          and not cov3.get("BKB", {}).get("never", True) and "couverture par sleeve" in txt3 and "F1B  jamais compare" in txt3
          and "InpRateSymbols" in txt3 and "InpRateSymbols" in so3 and "jamais comparees" in so3,
          ({c: (v.get("never"), v.get("from")) for c, v in cov3.items()}, so3[-600:]))
    chk("review2 N1: with 30 days of minutes the verdict says it covers only the compared sleeves ('Rien d'anormal sur ce qui a pu "
        "etre compare (5 sleeves non comparees : OC4, F1B, F1E, GFP, D4H')",
        lambda: (rc == 0 and "Rien d'anormal sur ce qui a pu etre compare (5 sleeves non comparees : OC4, F1B, F1E, GFP, D4H" in so3
                 and "Rien d'anormal." not in so3, so3[-500:]))
    # a bar of the ReleveFP minutes differs from the broker's: differences appear
    def bump(base, rec):
        if base == "BTCUSD":
            rec = rec.copy()
            sel = (rec["t"] >= srv("2021-11-10 12:00")) & (rec["t"] < srv("2021-11-10 16:00"))
            rec["c"][sel] += 30000
            rec["h"][sel] = np.maximum(rec["h"][sel], rec["c"][sel])
        return rec
    moved = csv_dir("csv_moved", SPAN, lit, bump)
    out4 = os.path.join(SCRATCH, "out_replay_moved")
    rc, so4, se = run_tool("check_demo.py", ["--journals", obs, "--bars", moved, "--out", out4])
    r4 = json.load(open(os.path.join(out4, "report.json"))) if rc == 0 else {}
    d4 = r4.get("replay", {}).get("comparison", {}).get("differences", [])
    check("tool2 replay moved bars: differences found and listed on BTC sleeves", rc == 0 and len(d4) > 0
          and all(d["code"] in ("BKB", "F1B", "NQB") for d in d4), [(d["event"], d["code"]) for d in d4[:6]])
    # MqlRates.spread = the minimum spread of the minute, which ReleveFP 1.00 does not write (no sp_min, no r1): no column
    # matches; the replay cannot be used and says so, instead of listing hundreds of differences (review2 N4)
    hidden = csv_dir("csv_min_hidden", SPAN, lit, style="min_hidden", version="1.00")
    out8 = os.path.join(SCRATCH, "out_min_hidden")
    rc, so8, se = run_tool("check_demo.py", ["--journals", obs, "--bars", hidden, "--out", out8])
    r8 = json.load(open(os.path.join(out8, "report.json"))) if rc == 0 else {}
    cal8 = r8.get("replay", {}).get("spread", {}).get("calibration", {})
    txt8 = open(os.path.join(out8, "report_fr.txt")).read() if rc == 0 else ""
    chk("review2 N4: minimum spread hidden (ReleveFP 1.00, no r1): no column matches, the minimum is compatible, and the replay "
        "is said unusable instead of listing differences",
        lambda: (rc == 0 and max(v["match"] for v in cal8["paper_lines"].values()) == 0
                 and cal8["min_consistent"]["inside"] == cal8["min_consistent"]["n"] > 100 and "rejeu inutilisable" in so8
                 and "rejeu inutilisable" in txt8 and not any("differente(s)" in a for a in r8.get("anomalies", []))
                 and "Rien d'anormal." not in so8, (cal8.get("paper_lines"), cal8.get("min_consistent"), r8.get("anomalies"), so8[-400:])))
    chk("review3 U5: the unusable replay is said once on stdout, in plain words, and report_fr.txt names no convention for a replay not run",
        lambda: (rc == 0 and so8.count("inutilisable") == 1 and "retenu : " not in txt8 and "ReleveFP 1.11" in so8, (so8[-500:], txt8.count("retenu"))))
    # ReleveFP 1.10's sp_min column: the 'min' convention is found and the replay is exact again
    spmin = csv_dir("csv_min_spmin", SPAN, lit, style="min_hidden", version="1.10")
    out12 = os.path.join(SCRATCH, "out_min_spmin")
    rc, so12, se = run_tool("check_demo.py", ["--journals", obs, "--bars", spmin, "--out", out12])
    r12 = json.load(open(os.path.join(out12, "report.json"))) if rc == 0 else {}
    rp12 = r12.get("replay", {})
    chk("review2 N4: with ReleveFP 1.10's sp_min column the convention 'min' is found and the replay has no difference",
        lambda: (rc == 0 and rp12["spread"]["used"] == "min" and rp12["status"] == "done" and not rp12["comparison"]["differences"]
                 and r12["anomalies"] == [], (rp12.get("spread", {}).get("used"), len(rp12.get("comparison", {}).get("differences", [])),
                                              r12.get("anomalies"), se[-300:])))
    # ReleveFP 1.10's r1 files (the terminal's own M1 bars): the replay is built from them, no calibration needed
    r1d = csv_dir("csv_r1", SPAN, lit, style="min_hidden", version="1.00", r1=True)
    out13 = os.path.join(SCRATCH, "out_r1")
    rc, so13, se = run_tool("check_demo.py", ["--journals", obs, "--bars", r1d, "--out", out13])
    r13 = json.load(open(os.path.join(out13, "report.json"))) if rc == 0 else {}
    rp13 = r13.get("replay", {})
    txt13 = open(os.path.join(out13, "report_fr.txt")).read() if rc == 0 else ""
    chk("review2 N4: with r1_<BASE>.csv files the replay uses the terminal's own bars (the report says so): no difference, nothing "
        "abnormal, although the m1 files hide the bar spread",
        lambda: (rc == 0 and rp13.get("status") == "done" and set(rp13.get("bar_source", {}).values()) == {"r1"}
                 and not rp13["comparison"]["differences"] and r13["anomalies"] == [] and "r1_XAUUSD.csv" in txt13,
                 (rp13.get("bar_source"), len(rp13.get("comparison", {}).get("differences", [])), r13.get("anomalies"), se[-300:])))
    # minutes taken before the demo: the advice is to run ReleveFP after it (InpDays cannot help)
    early = csv_dir("csv_before_demo", (SPAN[0], srv("2021-10-01 00:00")), lit)
    out14 = os.path.join(SCRATCH, "out_before_demo")
    rc, so14, se = run_tool("check_demo.py", ["--journals", obs, "--bars", early, "--out", out14])
    r14 = json.load(open(os.path.join(out14, "report.json"))) if rc == 0 else {}
    chk("review2 N8d: minutes that end before the demo ask to run ReleveFP after the demo, and the verdict is not a plain "
        "'Rien d'anormal'",
        lambda: (rc == 0 and "relancer ReleveFP apres la demo" in so14 and "Rien d'anormal." not in so14
                 and "InpDays" not in r14.get("replay", {}).get("coverage_advice", ""), (r14.get("replay", {}).get("coverage_advice"), so14[-400:])))
    # B2 with the replay: a daily file lost in the middle (a Wednesday): named, and its hours are not blamed on the robot
    lost = os.path.join(SCRATCH, "live_observer_lost_day", "ClaudeRobot")
    shutil.copytree(os.path.join(obs, "ClaudeRobot"), lost)
    os.remove(os.path.join(lost, "20211117.log"))
    out9 = os.path.join(SCRATCH, "out_lost_day")
    rc, so9, se = run_tool("check_demo.py", ["--journals", os.path.dirname(lost), "--bars", full, "--out", out9])
    r9 = json.load(open(os.path.join(out9, "report.json"))) if rc == 0 else {}
    c9 = r9.get("replay", {}).get("comparison", {})
    check("review B2 with the replay: the lost file is named, its hours left out, no difference blamed on the robot",
          rc == 0 and any("20211117.log" in a for a in r9.get("anomalies", [])) and not c9.get("differences")
          and c9.get("excluded", {}).get("journal du robot manquant a ce moment (fichier du jour absent)", 0) > 0,
          (r9.get("anomalies"), c9.get("excluded"), (c9.get("differences") or [])[:2], se[-300:]))
    # M4: BTC's minutes start 25 days before the end (a short tick history at the broker), the others 6 months: BTC's
    # sleeves start their warm-up at BTC's first minute, the short file is named, nothing is blamed on the robot
    def btc_short(base, rec):
        if base == "BTCUSD":
            rec = rec[rec["t"] >= SPAN[1] - 25 * 86400]
        return rec
    sh = csv_dir("csv_btc_short", SPAN, lit, btc_short)
    out10 = os.path.join(SCRATCH, "out_btc_short")
    rc, so10, se = run_tool("check_demo.py", ["--journals", obs, "--bars", sh, "--out", out10])
    r10 = json.load(open(os.path.join(out10, "report.json"))) if rc == 0 else {}
    rp10 = r10.get("replay", {})
    check("review M4: a market whose minutes start late delays only its own sleeves: no difference, the short file named",
          rc == 0 and not rp10.get("comparison", {}).get("differences") and any("m1_BTCUSD.csv commence" in p for p in rp10.get("problems", []))
          and rp10.get("coverage", {}).get("NQB", {}).get("never") and not rp10.get("coverage", {}).get("N30", {}).get("never", True),
          ((rp10.get("comparison", {}).get("differences") or [])[:2], rp10.get("problems"), se[-300:]))
    chk("review2 N8c: the bars per day (AGG) of that market are not compared on days before its first minute: no AGG anomaly",
        lambda: (rc == 0 and not any("nombre de barres different" in a for a in r10.get("anomalies", []))
                 and rp10["side_by_side"]["agg_days"] > 40, (r10.get("anomalies"), rp10.get("side_by_side", {}).get("agg_days"))))
    # m1: the releve's spread of one gold day differs from the broker's bars: the daily COST medians differ -> anomaly
    def wide_day(base, rec):
        if base == "XAUUSD":
            rec = rec.copy()
            sel = (rec["t"] >= srv("2021-11-16 00:00")) & (rec["t"] < srv("2021-11-17 00:00"))
            rec["s"][sel] += 5
        return rec
    wd = csv_dir("csv_wide_day", SPAN, lit, wide_day)
    out11 = os.path.join(SCRATCH, "out_wide_day")
    rc, so11, se = run_tool("check_demo.py", ["--journals", obs, "--bars", wd, "--out", out11])
    r11 = json.load(open(os.path.join(out11, "report.json"))) if rc == 0 else {}
    check("review m1: a day whose median spread differs between the robot and the replay (COST) is an anomaly",
          rc == 0 and any("COST" in a and "XAUUSD" in a for a in r11.get("anomalies", [])), (r11.get("anomalies"), se[-300:]))
    # the trading copy: fills against the mock's deals (the truth), and the replay as an observer against it
    trd, wall, _ = harness_live("live_trading", SPAN, {"MOCK_INPUT_InpTrade": "true", "MOCK_INPUT_InpPlanStart": str(PLAN0)})
    out5 = os.path.join(SCRATCH, "out_trading")
    rc, so5, se = run_tool("check_demo.py", ["--journals", trd, "--bars", full, "--out", out5])
    if not check("tool2 trading: runs", rc == 0, se[-3000:]):
        return
    r5 = json.load(open(os.path.join(out5, "report.json")))
    import pandas as pd
    deals = pd.read_csv(os.path.join(trd, "_mock", "deals.csv"), keep_default_na=False, float_precision="round_trip")
    robot = deals[(deals.magic >= 20261201) & (deals.magic <= 20261289) & deals.type.isin([0, 1])]
    ins = robot[robot.entry == 0].set_index("position")
    outs = robot[robot.entry == 1].groupby("position").last()
    pos = {p["ticket"]: p for p in r5["fills"]["positions"]}
    check("tool2 trading: one position per opening deal of the mock", len(pos) == len(ins) > 20, (len(pos), len(ins)))
    ent_ok = all(abs(pos[t]["entry_real"] - ins.loc[t, "price"]) < 1e-9 for t in ins.index if t in pos)
    check("tool2 trading: real entries = the mock's opening deals", ent_ok)
    ea = [t for t in outs.index if t in pos and int(outs.loc[t, "reason"]) == 3]
    sl_ = [t for t in outs.index if t in pos and int(outs.loc[t, "reason"]) == 4]
    ea_ok = all(pos[t]["exit_kind"] == "ea_close" and abs(pos[t]["exit_real"] - outs.loc[t, "price"]) < 1e-9 for t in ea)
    sl_ok = all(pos[t]["exit_kind"] in ("broker_stop_estimated", "broker_stop_race", "broker_stop_seen") for t in sl_)
    check("tool2 trading: EA closes read from CLOSE lines, broker stops (no line) estimated", ea_ok and sl_ok and len(ea) > 5,
          {"ea": len(ea), "sl": len(sl_), "bad_ea": [t for t in ea if pos[t]["exit_kind"] != "ea_close"][:3],
           "bad_sl": [(t, pos[t]["exit_kind"]) for t in sl_ if pos[t]["exit_kind"] not in ("broker_stop_estimated", "broker_stop_race",
                                                                                          "broker_stop_seen")][:3]})
    bad_kinds = [(p["ticket"], p["exit_kind"]) for p in pos.values() if p["exit_kind"] not in
                 ("ea_close", "broker_stop_estimated", "broker_stop_race", "broker_stop_seen", "open_or_unknown")]
    check("review B4: a clean trading run has no position flagged as not closed or exit unknown (no false alarm)",
          not bad_kinds and not [a for a in r5["anomalies"] if "CLOSE" in a or "fermee" in a or "sortie" in a], (bad_kinds[:5], r5["anomalies"]))
    units = {"XAUUSD": 100 * 0.89, "US100": 0.89, "BTCUSD": 0.89, "ETHUSD": 0.89}
    k_ok = all(abs(p["eur_per_price_per_lot"] / units[p["symbol"]] - 1) < 1e-6 for p in pos.values() if p.get("eur_per_price_per_lot"))
    check("tool2 trading: EUR per point from the FILL risk = the mock's tick value (units x 0.89)", k_ok,
          [(p["symbol"], p.get("eur_per_price_per_lot")) for p in list(pos.values())[:4]])
    c5 = r5["replay"]["comparison"]
    paper_diff = [d for d in c5["differences"] if d["event"] in PAPER_EV_T]
    check("tool2 trading: the paper lines of the trading copy equal the observer replay", not paper_diff, paper_diff[:3])
    check("tool2 trading: SIZE compared on the account-free fields only", not r5["replay"]["size_mode"]["live_copy_observer"]
          and r5["replay"]["size_mode"]["compared"] == ["side", "et", "late", "f"], r5["replay"]["size_mode"])
    chk("review2 control N1: a clean trading run has no missing journal line", lambda: (not r5["journal"].get("breaks")
                                                                                     and not any("manquante" in a for a in r5["anomalies"]),
                                                                                     (r5["journal"].get("breaks"), r5["anomalies"])))
    t5 = r5["fills"]["per_sleeve"]["TOTAL"]
    ea_bp = [p["exit_diff_bp"] for p in pos.values() if p["exit_kind"] == "ea_close" and p.get("exit_diff_bp") is not None]
    est = [p for p in pos.values() if p["exit_kind"] in ("broker_stop_estimated", "broker_stop_race", "broker_stop_seen")]
    chk("review2 N2: on the trading run the exit average holds the robot's closes only; the broker stops are counted apart with "
        "their estimate",
        lambda: (abs(t5["exit_diff_bp_mean"] - sum(ea_bp) / len(ea_bp)) < 1e-9 and t5["estimated_exits"] == len(est) > 5
                 and all(p.get("exit_est") is not None for p in est), (t5.get("exit_diff_bp_mean"), t5.get("estimated_exits"), len(est))))
    chk("review2 N10: every broker stop of the clean trading run is checked and seen in the minutes (no false 'stop jamais touche')",
        lambda: (all(p.get("stop_seen_utc") for p in est) and not any(p["exit_kind"] == "stop_not_reached" for p in pos.values()),
                 [(p["ticket"], p["exit_kind"], p.get("stop_seen_utc")) for p in est if not p.get("stop_seen_utc")][:5]))
    test_review3_replay(lit, obs, full)
    print(f"   (replay tests {time.time() - t0:.0f} s)")


PAPER_EV_T = ["DEC", "PFILL", "PEXIT", "PSTOP", "PREVISE", "PVOID", "PREFUSE", "HOLD"]


# ---------------------------------------------------------------------------------------------- the third review
def edit_lines(path, fn):
    """rewrite a robot file (CRLF, cp1252) line by line: fn(lines) -> lines"""
    write(path, "\n".join(fn(lines_of(path))) + "\n", crlf=True)


def test_review3_journal(lit):
    """the third review's journal cases on hand-made journals (no replay): R3-1 (a MISSED just after a reconnection),
    R3-2, R3-3, R3-4, R3-5, R3-6, R3-7, R3-8, R3-9, R3-11, R3-12, U1, U2, U3, U6, R8, R2, R6, P2, P3, P4, P6, P7"""
    base_dir = os.path.join(SCRATCH, "rv3j")

    def go(name, variant=(), extra=(), prep=None, style="live"):
        jdir = os.path.join(base_dir, "j_" + name, "ClaudeRobot")
        info = md_journal(jdir, variant, style)
        if prep:
            prep(jdir, info)
        out = os.path.join(base_dir, "out_" + name)
        rc, so, se = run_tool("check_demo.py", ["--journals", os.path.dirname(jdir), "--out", out] + list(extra))
        rp = os.path.join(out, "report.json")
        r = json.load(open(rp)) if rc == 0 and os.path.exists(rp) else {}
        rt = os.path.join(out, "report_fr.txt")
        rtxt = open(rt, encoding="utf-8").read() if rc == 0 and os.path.exists(rt) else ""
        return {"rc": rc, "so": so, "se": se, "r": r, "rtxt": rtxt, "info": info, "jdir": jdir, "an": " | ".join(r.get("anomalies", [])),
                "txt": (outputs_text(out) if rc == 0 else "") + so + se}
    base = go("base")
    tot0 = base["r"].get("fills", {}).get("per_sleeve", {}).get("TOTAL", {})

    # R3-1: a MISSED reason=late two minutes after a REBUILD why=reconnect is a start's case, not an anomaly
    def reconnect(jdir, info):
        def f(ls):
            u = U("2021-11-23 12:00")
            blk = [jl(u - 600, "DEC", "BKE", ("what", "info"), ("side", 1), ("v1", 1.5), ("v2", 0.0), ("at", u - 600), ("rp", 1)),
                   jl(u + 2, "REBUILD", "-", ("n", 2), ("why", "reconnect"), ("from", u - 120 * 86400), ("to", u), ("minutes", 172800), ("ms", 0)),
                   jl(u + 62, "MISSED", "BKE", ("oid", (u - 240) * 100 + 4), ("stamp", u - 240), ("reason", "late"))]
            k = next(i for i, ln in enumerate(ls) if int(ln.split("|")[1]) > u + 62)
            return ls[:k] + blk + ls[k:]
        edit_lines(os.path.join(jdir, "20211123.log"), f)
    g = go("r31_reconnect", prep=reconnect)
    chk("review3 R3-1: a MISSED reason=late two minutes after a REBUILD why=reconnect counts as a start's case (no 'MISSED non envoyes')",
        lambda: (g["rc"] == 0 and "MISSED non envoyes" not in g["an"], (g["an"][:400], g["se"][-300:])))

    # R3-2: the money estimate is incomplete when the journal starts without INIT and positions it did not open close in it
    def drop_first_two(jdir, info):
        for f in ("20211117.log", "20211118.log"):
            os.remove(os.path.join(jdir, f))
    g = go("r32_first2", prep=drop_first_two)
    m = g["r"].get("fills", {}).get("money_estimate") or {}
    chk("review3 R3-2: files of the start lost: positions closed in the window without their opening (ticket 70000101) make the money "
        "estimate incomplete, named",
        lambda: (g["rc"] == 0 and m.get("complete") is False and 70000101 in (m.get("unseen_tickets") or [])
                 and any("debut du journal absent" in w for w in m.get("incomplete_why", [])), (m, g["se"][-300:])))

    def drop_last(jdir, info):
        os.remove(os.path.join(jdir, "20211125.log"))
    fdir = os.path.join(base_dir, "releve_r32")
    os.makedirs(fdir, exist_ok=True)
    write(os.path.join(fdir, "fini.txt"), "\n".join(["version=1.10", f"server={FAKE_SERVER}", "currency=EUR",
                                                    f"server_time={srv('2021-11-25 12:00')}", "server_minus_gmt_sec=7200"]) + "\n", crlf=True)
    g = go("r32_tail", prep=drop_last, extra=("--bars", fdir, "--no-replay"))
    m = g["r"].get("fills", {}).get("money_estimate") or {}
    chk("review3 R3-2: the last file lost (journal_end names it): the money estimate is incomplete",
        lambda: (g["rc"] == 0 and m.get("complete") is False and m.get("journal_end_missing") is True, m))

    def purged(jdir, info):
        drop_first_two(jdir, info)
        d = srv("2021-10-25 00:00")
        write(os.path.join(jdir, "20211026.log"), jl(C.srv_to_utc(d + 86400) + 30, "DAY", "-", ("day", d), ("balance", 10000.0),
                                                    ("equity", 10000.0), ("bars_fed", 5000)) + "\n", crlf=True)
    g = go("r32_purge", prep=purged)
    chk("review3 R3-2: no INIT and the oldest file 30 days older than the newest: the robot's own 30-day purge is named, not 'send the file'",
        lambda: (g["rc"] == 0 and "efface lui-meme" in g["an"] and "envoyer aussi le fichier du jour du demarrage" not in g["an"], g["an"][:500]))

    # R3-3: time fields out of range: a DAY with an extra digit, two glued stamps: unreadable lines, no traceback, no flood
    def bad_times(jdir, info):
        def f(ls):
            out = []
            for ln in ls:
                if "|DAY|" in ln:
                    p = ln.split("|")
                    p = [x if not x.startswith("day=") else x + "0" for x in p]
                    ln = "|".join(p)
                out.append(ln)
            return out
        edit_lines(os.path.join(jdir, "20211121.log"), f)

        def g2(ls):
            sz = next(ln for ln in ls if "|SIZE|" in ln)
            u = sz.split("|")[1]
            return ls + [sz.replace(f"CR|{u}|", f"CR|{u}{u}|", 1)]
        edit_lines(os.path.join(jdir, "20211124.log"), g2)
    g = go("r33_times", prep=bad_times)
    chk("review3 R3-3: a DAY whose day has an extra digit and a line with two glued stamps: unreadable, a report, no traceback, no flood of "
        "missing files",
        lambda: (g["rc"] == 0 and "Traceback" not in g["se"] and g["r"]["inputs"]["unparsable"] == 2
                 and len(g["r"]["journal"].get("missing_files", [])) < 30 and len(g["so"]) < 20000,
                 (g["se"][-400:], g["r"].get("inputs", {}).get("unparsable_first"), len(g["r"].get("journal", {}).get("missing_files", [])))))

    def digit_fuzz(jdir, info):
        rnd = random.Random(31)
        for f in sorted(os.listdir(jdir)):
            p = os.path.join(jdir, f)
            ls = lines_of(p)
            for i, ln in enumerate(ls):
                if ln.startswith("CR|") and rnd.random() < 0.15:
                    parts = ln.split("|")
                    k = rnd.choice([1] + [j for j, x in enumerate(parts) if x.split("=")[0] in ("bar", "stamp", "x", "tf", "to", "from", "at", "oid")])
                    parts[k] = parts[k] + "".join(rnd.choice("0123456789") for _ in range(rnd.randrange(3, 25)))
                    ls[i] = "|".join(parts)
            write(p, "\n".join(ls) + "\n", crlf=True)
    g = go("r33_fuzz", prep=digit_fuzz)
    chk("review3 R3-3: a fuzz of long digit runs glued to stamps, bars, oids and times: a report, no traceback, no account word",
        lambda: (g["rc"] == 0 and "Traceback" not in g["se"] and leak_free(g["txt"]) == [], g["se"][-600:]))

    # R3-4: a trailing broker stop whose moves (SLMOD) the journal must show: C (BKB) trails to 56600, the broker's stop closes it
    def trail(drop=None):
        def prep(jdir, info):
            oid = info["C"]
            moves = [("2021-11-23 10:00", 56000.0, 56200.0), ("2021-11-23 11:00", 56200.0, 56400.0), ("2021-11-23 12:00", 56400.0, 56600.0)]

            def f(ls):
                add = []
                for k, (at, frm, to) in enumerate(moves):
                    u = U(at)
                    add.append(jl(u, "PSTOP", "BKB", ("oid", oid), ("side", 1), ("bar", u), ("px", to + 300), ("stop", to), ("st0", 56000.0),
                                  ("x", U("2021-11-23 15:00")), ("s_raw", 12), ("s_paper", 0.18)))
                    if k != drop:
                        add.append(jl(u + 90, "SLMOD", "BKB", ("ticket", 70000104), ("from", frm), ("to", to), ("rc", 10009), ("ok", 1)))
                out = []
                for ln in ls:
                    if "|PEXIT|BKB|" in ln and f"oid={oid}" in ln:
                        ln = ln.replace("|stop=5.6000000000000000e+04|", "|stop=5.6600000000000000e+04|")
                        ln = ln.replace("|px=5.5990000000000000e+04|", "|px=5.6590000000000000e+04|")
                    out.append(ln)
                return sorted(out + add, key=lambda x: int(x.split("|")[1]))
            edit_lines(os.path.join(jdir, "20211123.log"), f)
        return prep
    g = go("r34_trail", ("bkb_stop",), prep=trail())
    chk("review3 control R3-4: a trailing stop whose every move is in the journal gives no missing line",
        lambda: (g["rc"] == 0 and not g["r"]["journal"].get("breaks"), g["r"].get("journal", {}).get("breaks")))
    for k, what in ((1, "a stop move in the middle"), (2, "the last stop move")):
        g = go(f"r34_drop{k}", ("bkb_stop",), prep=trail(drop=k))
        chk(f"review3 R3-4: {what} lost (SLMOD) is reported as a missing line and makes the money estimate incomplete",
            lambda: (g["rc"] == 0 and any(b["missing"] == "SLMOD" for b in g["r"]["journal"].get("breaks", []))
                     and "SLMOD" in g["an"] and (g["r"]["fills"]["money_estimate"] or {}).get("complete") is False,
                     (g["an"][:500], (g["r"].get("fills", {}).get("money_estimate") or {}).get("incomplete_why"))))

    # R3-5: a lost SIZE (a SEND without it), daily lines that come in sets, one lost DEC counted once
    g = go("r35_size", prep=drop_line(lambda ln: "|SIZE|N30|" in ln))
    chk("review3 R3-5: a lost SIZE line (its SEND remains) is reported from the journal alone",
        lambda: (g["rc"] == 0 and "SIZE" in g["an"] and "manquante" in g["an"], g["an"][:400]))
    g = go("r35_agg", prep=drop_line(lambda ln: "|AGG|" in ln, k=3))
    chk("review3 R3-5: a lost AGG line (its DAY remains) is reported",
        lambda: (g["rc"] == 0 and "AGG" in g["an"] and "manquante" in g["an"], g["an"][:400]))

    def drop_last_day(jdir, info):
        edit_lines(os.path.join(jdir, "20211125.log"), lambda ls: [ln for ln in ls if "|DAY|" not in ln])
    g = go("r35_lastday", prep=drop_last_day)
    chk("review3 R3-5: the last DAY line lost (no later DAY line to show it) is reported through its AGG",
        lambda: (g["rc"] == 0 and "DAY" in g["an"] and "manquante" in g["an"], g["an"][:400]))
    g = go("r35_dec", prep=drop_line(lambda ln: "|DEC|ORX|" in ln))
    chk("review3 R3-5: one lost DEC line counts as one missing line (not two)",
        lambda: (g["rc"] == 0 and "1 ligne(s) du journal manquante(s)" in g["an"] and "1 DEC (ordre)" in g["an"], g["an"][:300]))

    # R3-6: the start and stop lines of a restart
    def drop_in(fname, pred):
        def prep(jdir, info):
            edit_lines(os.path.join(jdir, fname), lambda ls: [ln for ln in ls if not pred(ln)])
        return prep
    g = go("r36_init", ("restart",), prep=drop_in("20211122.log", lambda ln: "|INIT|-|build=" in ln))
    chk("review3 R3-6: a restart whose INIT line is lost is a start of its own, reported (not merged into the previous one)",
        lambda: (g["rc"] == 0 and len(g["r"]["journal"]["starts"]) == 2 and "ligne de demarrage perdue" in g["an"], g["an"][:400]))
    g = go("r36_deinit", ("restart",), prep=drop_in("20211119.log", lambda ln: "|deinit=" in ln))
    chk("review3 R3-6: a start that ends with no stop line before the next INIT is reported (crash, Mac switched off, or line lost)",
        lambda: (g["rc"] == 0 and "sans ligne d'arret (INIT deinit) avant le demarrage suivant" in g["an"], g["an"][:400]))
    g = go("r36_rebuild", ("restart",), prep=drop_in("20211122.log", lambda ln: "|REBUILD|" in ln))
    chk("review3 R3-6: a start whose REBUILD line is lost is live from its INIT line and the lost line is reported",
        lambda: (g["rc"] == 0 and "REBUILD" in g["an"] and g["r"]["journal"]["starts"][1].get("live_from") is not None, g["an"][:400]))

    # R3-7: the headline says the late-by-design part of its euros; closes for another reason are apart
    t7 = base["r"].get("fills", {}).get("per_sleeve", {}).get("TOTAL", {})
    chk("review3 R3-7: the stdout headline's euros say how much comes from the entries late by design ('dont ... entrees en retard')",
        lambda: (base["rc"] == 0 and "entrees en retard par construction)" in next((ln for ln in base["so"].splitlines() if ln.startswith("Trades")), "")
                 and t7.get("entry_diff_late_eur_sum") is not None, next((ln for ln in base["so"].splitlines() if ln.startswith("Trades")), "")))

    def close_prev(jdir, info):
        edit_lines(os.path.join(jdir, "20211123.log"), lambda ls: [ln.replace("|why=time|", "|why=prev|") if "|CLOSE|BKB|" in ln else ln for ln in ls])
    g = go("r37_prev", prep=close_prev)
    tg = g["r"].get("fills", {}).get("per_sleeve", {}).get("TOTAL", {})
    pos = {p["ticket"]: p for p in g["r"].get("fills", {}).get("positions", [])}
    others = [pos[t]["exit_diff_bp"] for t in (70000101, 70000102, 70000103, 70000105) if pos.get(t, {}).get("exit_diff_bp") is not None]
    chk("review3 R3-7: a robot close for another reason than the paper's exit (CLOSE why=prev) is left out of the exit average and shown apart",
        lambda: (g["rc"] == 0 and tg.get("exits_apart") == 1 and abs(tg["exit_diff_bp_mean"] - sum(others) / len(others)) < 1e-9
                 and "pour une autre raison" in g["rtxt"], {k: tg.get(k) for k in ("exits_apart", "exit_diff_bp_mean")}))

    # R3-8: a second copy of a day file ('20211118 2.log', the Mac's 'Keep both')
    def dup_file(jdir, info):
        shutil.copy(os.path.join(jdir, "20211118.log"), os.path.join(jdir, "20211118 2.log"))
    g = go("r38_dup", prep=dup_file)
    t8 = g["r"].get("fills", {}).get("per_sleeve", {}).get("TOTAL", {})
    chk("review3 R3-8: a second copy of a day file is skipped and named; the trade counts stay those of the journal",
        lambda: (g["rc"] == 0 and any(s_["file"] == "20211118 2.log" for s_ in g["r"]["inputs"].get("skipped_files", []))
                 and "20211118 2.log" in g["an"] and t8.get("intents") == tot0.get("intents") and t8.get("real_trades") == tot0.get("real_trades"),
                 (g["r"].get("inputs", {}).get("skipped_files"), t8.get("intents"), tot0.get("intents"))))

    # R3-9: the last line of a file without its line end was cut while the robot wrote it
    def cut_end(jdir, info):
        p = os.path.join(jdir, "20211121.log")
        raw = open(p, "rb").read().decode("cp1252").rstrip("\r\n")
        open(p, "wb").write(raw[:-1].encode("cp1252"))
    g = go("r39_cut", prep=cut_end)
    chk("review3 R3-9: a file whose last line has no line end (cut inside its last number) counts that line unreadable",
        lambda: (g["rc"] == 0 and g["r"]["inputs"]["unparsable"] == 1 and "coupee a la fin du fichier" in g["an"], g["an"][:300]))

    # R3-12: the paper exited by time, no CLOSE; the minutes cross the stop only after the paper's exit
    md = os.path.join(base_dir, "m1_after")
    os.makedirs(md, exist_ok=True)
    m1_flat(os.path.join(md, "m1_XAUUSD.csv"), srv("2021-11-18 09:00"), srv("2021-11-19 21:00"), dip_at=srv("2021-11-19 19:00"),
            dip_low=1849.95)
    g = go("r312_after", ("no_close",), extra=("--bars", md, "--no-replay"))
    pa = {p["ticket"]: p for p in g["r"].get("fills", {}).get("positions", [])}.get(70000101, {})
    chk("review3 R3-12: a position not closed at the paper's time exit whose minutes cross its stop later is said so (stop after the paper's "
        "exit), not 'stop never touched'",
        lambda: (g["rc"] == 0 and pa.get("exit_kind") == "broker_stop_after_paper" and "ne touchent pas son stop" not in g["an"]
                 and "fermee(s) ensuite par le stop courtier" in g["an"], (pa.get("exit_kind"), g["an"][:400])))
    g = go("r312_race", ("race",))
    m = g["r"].get("fills", {}).get("money_estimate") or {}
    chk("review3 R3-12: a CLOSE without price (rc=0) that no minutes can check leaves the money estimate incomplete",
        lambda: (g["rc"] == 0 and m.get("complete") is False, m.get("incomplete_why")))

    # U1: the money in words, and the balance-based costs on stdout
    tl = next((ln for ln in base["so"].splitlines() if ln.startswith("Trades")), "")
    chk("review3 U1: the stdout headline says the euros in words ('le reel a fait X EUR de moins/plus que le papier') and gives the "
        "balance-based costs ('frais hors des prix')",
        lambda: (base["rc"] == 0 and ("de moins que le papier" in tl or "de plus que le papier" in tl) and "frais hors des prix" in base["so"],
                 base["so"][:600]))

    # U2: an unreadable DAY line is not a missing day
    def bad_day(jdir, info):
        edit_lines(os.path.join(jdir, "20211120.log"), lambda ls: [ln + "abc" if "|DAY|" in ln else ln for ln in ls])
    g = go("u2_day", prep=bad_day)
    chk("review3 U2: an unreadable DAY line is said 'ligne DAY illisible', not a missing day or a cut file",
        lambda: (g["rc"] == 0 and "aucune ligne DAY" not in g["an"] and "manquant" not in g["an"] and "ligne DAY illisible" in g["rtxt"],
                 g["an"][:400]))

    # U3, U6, R8, R2, R6: ReleveFP's files beside a journal, without the replay
    rdir = os.path.join(base_dir, "rel_u3")
    make_releve(rdir, lit, "good", m1_from="2021-11-15 00:00", m1_to="2021-11-26 00:00")
    p = os.path.join(rdir, "r1_XAUUSD.csv")
    ls = lines_of(p)
    ls[5] = "x" + ls[5]
    write(p, "\n".join(ls) + "\n")
    write(os.path.join(rdir, "m1_US100.csv"), "time;bo;bh\n1;2;3\n")
    g = go("u3_bad", extra=("--bars", rdir, "--no-replay"))
    chk("review3 U3: a bad row of an r1 file and an unreadable m1 file are anomalies naming the files (not only notes)",
        lambda: (g["rc"] == 0 and "r1_XAUUSD.csv : 1 ligne(s) illisible(s)" in g["an"] and "fichier du releve illisible : m1_US100.csv" in g["an"],
                 g["an"][:500]))
    chk("review3 U6: '--no-replay' is said in French on stdout ('non lance'), no English status",
        lambda: (g["rc"] == 0 and "non lance (--no-replay)" in g["so"] and "skipped" not in g["so"], g["so"][-400:]))
    rdir2 = os.path.join(base_dir, "rel_r8")
    make_releve(rdir2, lit, "good", m1_from="2021-11-15 00:00", m1_to="2021-11-26 00:00")
    p = os.path.join(rdir2, "r1_XAUUSD.csv")
    ls = lines_of(p)
    write(p, "\n".join(ls[:len(ls) // 2]) + "\n")                       # cut: the oldest days lost
    os.remove(os.path.join(rdir2, "r1_BTCUSD.csv"))                      # not copied
    g = go("r8_fini", extra=("--bars", rdir2, "--no-replay"))
    chk("review3 R8: check_demo reads fini.txt beside the releve: a cut r1 file asks to copy it again, an r1 file not copied asks for it",
        lambda: (g["rc"] == 0 and "recopier r1_XAUUSD.csv" in g["so"] and "copier aussi r1_BTCUSD.csv" in g["so"], g["so"][-600:]))
    rdir3 = os.path.join(base_dir, "rel_r2")
    make_releve(rdir3, lit, "good", m1_from="2021-11-15 00:00", m1_to="2021-11-26 00:00")
    p = os.path.join(rdir3, "r1_XAUUSD.csv")
    ls = lines_of(p)
    keep = [ls[0]] + [ln for ln in ls[1:] if int(ln.split(",")[0]) < srv("2021-11-24 00:00")]
    write(p, "\n".join(keep) + "\n")
    fl = lines_of(os.path.join(rdir3, "fini.txt"))
    fl = [re.sub(r"barres=\d+", f"barres={len(keep) - 1}", ln) if ln.startswith("XAUUSD=") else ln for ln in fl]
    fl = [re.sub(r"barres=\d+", "barres=-1", ln) if ln.startswith("ETHUSD=") else ln for ln in fl]
    write(os.path.join(rdir3, "fini.txt"), "\n".join(fl) + "\n")
    g = go("r2_short", extra=("--bars", rdir3, "--no-replay"))
    chk("review3 R2: terminal bars (r1) that end days before the minutes (m1) give the cause and 'relancer ReleveFP' on stdout",
        lambda: (g["rc"] == 0 and "relancer ReleveFP : les barres r1_XAUUSD s'arretent" in g["so"], g["so"][-600:]))
    chk("review3 R6: an r1 file ReleveFP could not write this time (barres=-1) is left aside (an older run's file) and the run asked again",
        lambda: (g["rc"] == 0 and "r1_ETHUSD.csv (fichier ouvert ailleurs ?)" in g["so"]
                 and any("r1_ETHUSD.csv laisse de cote" in x for x in g["r"].get("replay", {}).get("problems", [])), g["so"][-600:]))

    # R3-11: the gold broker-stop estimate given with the commission included (bp and EUR)
    hj = os.path.join(base_dir, "hand", "ClaudeRobot")
    handmade_journal(hj, "good")
    out = os.path.join(base_dir, "out_hand")
    rc, so, se = run_tool("check_demo.py", ["--journals", os.path.dirname(hj), "--out", out])
    r = json.load(open(os.path.join(out, "report.json"))) if rc == 0 else {}
    rtxt = open(os.path.join(out, "report_fr.txt"), encoding="utf-8").read() if rc == 0 else ""
    p2 = {p["ticket"]: p for p in r.get("fills", {}).get("positions", [])}.get(70000012, {})
    want = None
    if p2:
        want = (1789.8 - 1790.2 * (1 - 1.0e-4) + 0.03) * 0.2 * 86.0
    chk("review3 R3-11: the gold broker-stop estimate is given commission included, in bp and in EUR",
        lambda: (rc == 0 and abs((p2.get("exit_diff_est_net_eur") or 0) - want) < 1e-6
                 and "commission comprise : le papier de l'or met la commission dans son stop" in rtxt, (p2.get("exit_diff_est_net_eur"), want)))

    # P2, P3, P4: the scrubber and the schema
    sc = C.Scrubber()
    sc.scan_log_line(f"KR\t0\t09:58:01.112\tReseau\t'{FAKE_LOGIN}': autorise sur Vexlorn-Demo42 via Access Point EU 2")
    chk("review3 P2: a number equal to a masked value (a login read as a number) is masked in report.json",
        lambda: (sc.obj({"login": int(FAKE_LOGIN), "x": float(FAKE_LOGIN), "n": 12}) == {"login": sc.MASK, "x": sc.MASK, "n": 12},
                 sc.obj({"login": int(FAKE_LOGIN)})))
    chk("review3 P3: the French terminal line 'autorise sur <serveur>' masks the server name",
        lambda: ("Vexlorn-Demo42" not in sc.text("le serveur Vexlorn-Demo42"), sc.secrets))

    def edited(jdir, info):
        def f(ls):
            out = []
            for ln in ls:
                if "|INIT|-|build=" in ln:
                    ln = ln.replace("|ETHUSD=ETHUSD.r", "|ETHUSD=Dumont-Segur")
                if "|DAY|" in ln:
                    ln = ln + "|Vexlorn_Demo42=1"
                out.append(ln)
            out.append(f"CR|{U('2021-11-17 09:00')}|ERROR|-|what=script file missing: Dumont-Segur.csv")
            out.append(f"CR|{U('2021-11-17 09:01')}|DAY|-|day={srv('2021-11-16 00:00')}|balance=1|equity=1|bars_fed=1|Dumont=1|Dumont=2")
            return out
        edit_lines(os.path.join(jdir, "20211117.log"), f)
        edit_lines(os.path.join(jdir, "20211119.log"), lambda ls: [ln + "|Vexlorn_Demo42=1" if "|DAY|" in ln else ln for ln in ls])
    g = go("p3_edited", prep=edited)
    chk("review3 P3: an edited line that keeps the robot's format brings no free text to any output (an INIT symbol name that is not the "
        "market's, an ERROR's free part, an unknown key's name)",
        lambda: (g["rc"] == 0 and "Dumont" not in g["txt"] and "Vexlorn_Demo42" not in g["txt"], [w for w in ("Dumont", "Vexlorn") if w in g["txt"]]))
    chk("review3 P4: the reason given for a duplicated key never quotes a name that is not the robot's",
        lambda: (g["rc"] == 0 and "cle en double" in g["an"] + g["rtxt"] and "cle Dumont" not in g["txt"], g["an"][:300]))

    # P6: --fiches inside the repository is warned about like the other inputs
    g = go("p6_fiches", extra=("--fiches", os.path.join(HERE, "demo_common.py")))
    chk("review3 P6: --fiches inside the repository gets the warning", lambda: (g["rc"] == 0 and "Attention : des fichiers du Mac sont dans le depot" in g["so"],
                                                                              g["so"][:300]))
    # R1: a fiches.csv re-saved with semicolons beside the minutes: a report, never a traceback
    rdir4 = os.path.join(base_dir, "rel_semi")
    make_releve(rdir4, lit, "good", m1_from="2021-11-15 00:00", m1_to="2021-11-26 00:00")
    p = os.path.join(rdir4, "fiches.csv")
    write(p, open(p, "rb").read().decode("cp1252").replace(",", ";"))
    g = go("r1_semi", extra=("--bars", rdir4, "--no-replay"))
    chk("review3 R1 (fiches header): check_demo with a fiches.csv re-saved by a spreadsheet (semicolons) beside the minutes: a report naming "
        "it, no traceback", lambda: (g["rc"] == 0 and "Traceback" not in g["se"] and "tableur" in g["an"], (g["se"][-300:], g["an"][:300])))
    # P7: the default output folder can be moved with DEMO_OUT
    r_ = subprocess.run([sys.executable, "-I", "-c", f"import sys; sys.dont_write_bytecode = True; sys.path.insert(0, {HERE!r}); "
                         "import demo_common as C; print(C.DEFAULT_OUT)"],
                        capture_output=True, text=True, env=dict(os.environ, DEMO_OUT=os.path.join(SCRATCH, "elsewhere")))
    chk("review3 P7: the default --out comes from DEMO_OUT when it is set", lambda: (r_.stdout.strip() == os.path.join(SCRATCH, "elsewhere"),
                                                                                   (r_.stdout, r_.stderr[-200:])))


def test_review3_tool1(lit):
    """the third review's cases of read_mac_files.py: R1 (the r1 days in calendar days), R2 (an empty or short r1 file), R3 (Max bars),
    R6, R9, R10, R11, R12, R13/U7, R1 (fiches header), R2 (fini integers), P1, P5, U6"""
    base_dir = os.path.join(SCRATCH, "rv3t1")

    def go(name, prep=None, **kw):
        folder = os.path.join(base_dir, "in_" + name)
        out = os.path.join(base_dir, "out_" + name)
        make_releve(folder, lit, "good", **kw)
        if prep:
            prep(folder)
        rc, so, se = run_tool("read_mac_files.py", [folder, "--out", out])
        s = json.load(open(os.path.join(out, "summary.json"))) if rc == 0 else {"checks": [], "problems": []}
        txt = (open(os.path.join(out, "summary_fr.txt"), encoding="utf-8").read() if rc == 0 else "")
        return {"rc": rc, "so": so, "se": se, "ck": {(c["market"], c["item"]): c for c in s["checks"]}, "s": s, "txt": txt,
                "json": open(os.path.join(out, "summary.json"), encoding="utf-8").read() if rc == 0 else ""}

    def fini_edit(folder, fn):
        p = os.path.join(folder, "fini.txt")
        write(p, "\n".join(fn(lines_of(p))) + "\n")
    g = go("r1_200", r1_from="2021-06-01 00:00")
    c = g["ck"].get(("XAUUSD", "r1_rows"), {})
    chk("review3 R1 (r1 days): a gold r1 file of six months (5 trading days a week) is measured in calendar days: no 'too short for D4H' note",
        lambda: (g["rc"] == 0 and c.get("status") == "OK" and "jours du calendrier" in str(c.get("broker")) and "moins que les 150" not in c.get("note", "")
                 and "il en faut" not in c.get("note", ""), c))

    def r1_empty(folder):
        write(os.path.join(folder, "r1_XAUUSD.csv"), lit["r1"] + "\n")
        fini_edit(folder, lambda ls: [re.sub(r"barres=\d+ jours_barres=\d+", "barres=0 jours_barres=0", ln) if ln.startswith("XAUUSD=") else ln
                                      for ln in ls])
    g = go("r2_empty", prep=r1_empty)
    chk("review3 R2: a found market whose r1 file holds no bar is DIFFERENT (history not loaded), not OK",
        lambda: (g["rc"] == 0 and g["ck"].get(("XAUUSD", "r1_rows"), {}).get("status") == "DIFFERENT", g["ck"].get(("XAUUSD", "r1_rows"))))

    def r1_newest_lost(folder):
        p = os.path.join(folder, "r1_XAUUSD.csv")
        ls = lines_of(p)
        keep = [ls[0]] + [ln for ln in ls[1:] if int(ln.split(",")[0]) < srv("2021-11-26 00:00")]
        write(p, "\n".join(keep) + "\n")
        fini_edit(folder, lambda ls_: [re.sub(r"barres=\d+", f"barres={len(keep) - 1}", ln) if ln.startswith("XAUUSD=") else ln for ln in ls_])
    g = go("r2_newest", prep=r1_newest_lost)
    chk("review3 R2: r1 bars missing on days the m1 file has minutes (the newest days, fini.txt matching) is DIFFERENT 'barres manquantes'",
        lambda: (g["rc"] == 0 and g["ck"].get(("XAUUSD", "r1_rows"), {}).get("status") == "DIFFERENT"
                 and "barres manquantes" in g["ck"].get(("XAUUSD", "r1_rows"), {}).get("note", ""), g["ck"].get(("XAUUSD", "r1_rows"))))

    def maxbars(folder):
        fini_edit(folder, lambda ls: ls[:3] + ["max_barres=100000"] + ls[3:])
    g = go("r3_maxbars", prep=maxbars)
    chk("review3 R3 (erreur_barres): 'Max bars in chart' below 500000 (fini.txt max_barres=) is DIFFERENT with what to do",
        lambda: (g["rc"] == 0 and g["ck"].get(("compte", "max_bars"), {}).get("status") == "DIFFERENT"
                 and "500000" in g["ck"].get(("compte", "max_bars"), {}).get("note", ""), g["ck"].get(("compte", "max_bars"))))

    def r1_open_failed(folder):
        os.remove(os.path.join(folder, "r1_XAUUSD.csv"))
        fini_edit(folder, lambda ls: [re.sub(r"barres=\d+ jours_barres=\d+ erreur_barres=\d+", "barres=-1 jours_barres=0 erreur_barres=-1", ln)
                                      if ln.startswith("XAUUSD=") else ln for ln in ls])
    g = go("r6_open", prep=r1_open_failed)
    chk("review3 R6: ReleveFP could not write r1_XAUUSD.csv (barres=-1): DIFFERENT 'relancer', not silent",
        lambda: (g["rc"] == 0 and g["ck"].get(("XAUUSD", "r1_rows"), {}).get("status") == "DIFFERENT"
                 and "n'a pas pu ecrire" in g["ck"].get(("XAUUSD", "r1_rows"), {}).get("note", ""), g["ck"].get(("XAUUSD", "r1_rows"))))

    def no_m1(folder):
        os.remove(os.path.join(folder, "m1_XAUUSD.csv"))
    g = go("r11_nom1", prep=no_m1)
    chk("review3 R11: an m1 file not copied while fini.txt counts its minutes is DIFFERENT 'copier aussi les fichiers m1'",
        lambda: (g["rc"] == 0 and g["ck"].get(("XAUUSD", "m1_rows"), {}).get("status") == "DIFFERENT"
                 and "copier aussi" in g["ck"].get(("XAUUSD", "m1_rows"), {}).get("note", ""), g["ck"].get(("XAUUSD", "m1_rows"))))

    def m1_open_failed(folder):
        fini_edit(folder, lambda ls: [re.sub(r"=XAUUSD\.r .*? barres=", "=XAUUSD.r fichier impossible a ouvrir barres=", ln)
                                      if ln.startswith("XAUUSD=") else ln for ln in ls])
        os.remove(os.path.join(folder, "m1_XAUUSD.csv"))
    g = go("r12_m1open", prep=m1_open_failed)
    chk("review3 R12: 'fichier impossible a ouvrir' in fini.txt is said plainly (relancer ReleveFP), never Python's None",
        lambda: (g["rc"] == 0 and "None" not in g["txt"] and "m1 impossible a ouvrir" in str(g["ck"].get(("XAUUSD", "releve_days"), {}).get("broker"))
                 and g["ck"].get(("XAUUSD", "releve_days"), {}).get("status") == "DIFFERENT", g["ck"].get(("XAUUSD", "releve_days"))))
    g = go("r13_v110")
    chk("review3 R13/U7: the version of ReleveFP is kept as text ('1.10')", lambda: (g["rc"] == 0 and g["s"].get("releve_version") == "1.10",
                                                                                   g["s"].get("releve_version")))
    chk("review3 P1: the broker company of fini.txt is not copied into summary.json",
        lambda: (g["rc"] == 0 and "First Prudential Markets Ltd" not in g["json"] and "company" not in g["s"].get("account", {}), g["s"].get("account")))
    chk("review3 U6: tool 1's stdout has no English day names nor 'mock'; the crypto weekend quotes (no effect on the robot) are not "
        "among the points that differ",
        lambda: (g["rc"] == 0 and " Sat " not in g["so"] and "mock" not in g["so"] and "cotation le week-end" not in g["so"].split("Points cles")[0],
                 g["so"][:800]))
    g = go("r13_v100", version="1.00")
    chk("review3 R13: a 1.00 run (the new .mq5 not compiled) is DIFFERENT 'ReleveFP 1.11 attendu (recompiler)'",
        lambda: (g["rc"] == 0 and g["ck"].get(("compte", "releve_version"), {}).get("status") == "DIFFERENT"
                 and "F7" in g["ck"].get(("compte", "releve_version"), {}).get("note", ""), g["ck"].get(("compte", "releve_version"))))

    def bad_ints(folder):
        fini_edit(folder, lambda ls: [("server_time=abc" if ln.startswith("server_time=") else ln) for ln in ls]
                  + [f"titulaire=Helene-Gaelle {FAKE_NAME}", "email=hg.fake@exemple.fr"])
        p = os.path.join(folder, "sonde.csv")
        sl = lines_of(p)
        sl = [ln.replace("lot minimum trop gros pour un stop a 0.40 % du solde", f"refuse par le serveur : compte {FAKE_LOGIN} {FAKE_NAME}")
              for ln in sl]
        sl = [ln + ",server_time=xyz" if ln.startswith("#") else ln for ln in sl]
        write(p, "\n".join(sl) + "\n")
    g = go("r2_ints", prep=bad_ints)
    chk("review3 R2 (fini integers): a server_time in fini.txt or sonde.csv that is not an integer gives a report, no traceback",
        lambda: (g["rc"] == 0 and "Traceback" not in g["se"], g["se"][-400:]))
    chk("review3 P5: lines fini.txt and sonde.csv never write (an extra key, a status that is not SondeFP's) are not kept",
        lambda: (g["rc"] == 0 and "Helene" not in g["json"] + g["txt"] + g["so"] and "exemple.fr" not in g["json"] + g["txt"]
                 and leak_free(g["json"] + g["txt"] + g["so"]) == [], [w for w in ("Helene", "exemple.fr") if w in g["json"] + g["txt"]]))

    def sess_text(folder):
        # the privacy review's fuzz case fiches_xau_text: the gold sessions field holds "server:login" (an edited file)
        p = os.path.join(folder, "fiches.csv")
        ls = []
        for ln in lines_of(p):
            if ln.startswith("XAUUSD,"):
                f = ln.split(",")
                f[-1] = f"5:{FAKE_SERVER}:{FAKE_LOGIN}|"
                ln = ",".join(f)
            ls.append(ln)
        write(p, "\n".join(ls) + "\n")
    g = go("p5_sessions", prep=sess_text)
    chk("review3 P5 (fiches sessions): a sessions field that is not ReleveFP's 'day:from-to|' list is not copied into the outputs; "
        "a problem names it and the gold Friday check is UNKNOWN",
        lambda: (g["rc"] == 0 and leak_free(g["json"] + g["txt"] + g["so"]) == []
                 and any("seances" in p and "illisibles" in p for p in g["s"].get("problems", []))
                 and g["ck"].get(("XAUUSD", "friday_session"), {}).get("status") == "UNKNOWN",
                 (leak_free(g["json"] + g["txt"] + g["so"]), g["s"].get("problems"), g["ck"].get(("XAUUSD", "friday_session")))))

    def semis(folder):
        for f in ("fiches.csv", "tous.csv"):
            p = os.path.join(folder, f)
            write(p, open(p, "rb").read().decode("cp1252").replace(",", ";"))
    g = go("r1_semis", prep=semis)
    chk("review3 R1 (fiches header): fiches.csv and tous.csv re-saved with semicolons: a report naming them, no traceback",
        lambda: (g["rc"] == 0 and any("tableur" in p for p in g["s"].get("problems", [])), (g["se"][-300:], g["s"].get("problems"))))
    # R9, R10: the rounded mean of a half-way spread; a line cut inside its last field
    import check_demo as D
    import read_mac_files as RM
    import pandas as pd
    df = pd.DataFrame({"time": [0, 60], "bo": [1.0, 1.0], "bh": [1.0, 1.0], "bl": [1.0, 1.0], "bc": [1.0, 1.0], "ao": [1.15, 1.01],
                       "ah": [1.15, 1.01], "al": [1.15, 1.01], "ac": [1.15, 1.01], "n": [2, 2], "sp_mean": [float("0.1450"), float("1.0050")],
                       "sp_max": [0.15, 0.01]})
    conv, _, _ = D.spread_points(df, 2)
    chk("review3 R9: a half-way mean spread (0.1450, 1.0050 at 2 digits) rounds up to 15 and 101 points, not down",
        lambda: (list(conv["mean"]) == [15, 101], list(conv["mean"])))
    cut = os.path.join(base_dir, "r1_cut.csv")
    os.makedirs(base_dir, exist_ok=True)
    with open(cut, "wb") as f:
        f.write((lit["r1"] + "\r\n1637280000,1860.00,1860.10,1859.90,1860.05,37,12,0\r\n1637280060,1860.05,1860.20,1860.00,1860.10,37,1").encode())
    chk("review3 R10: an r1 copy cut inside its last line's spread field: both readers drop that line and data_rows counts complete lines only",
        lambda: (len(D.read_r1(cut)) == 1 and len(RM.read_r1(cut)) == 1 and RM.data_rows(cut) == 1 and int(D.read_r1(cut).spread[0]) == 12,
                 (len(D.read_r1(cut)), len(RM.read_r1(cut)), RM.data_rows(cut))))


def test_review3_releve(lit):
    """ReleveFP.mq5 run for real (translated by lab/live_ai/check/to_cpp.py, against the demo copy of the MT5 imitation in
    lab/robot/demo/releve_mock/): r1 only for the robot's markets (R4), every m1 file before any r1 file (R14), a series still
    loading is waited for (R2), the days after the last bar are no error (R3), a last call that fails never drops a day (R7),
    Max bars in fini.txt; and read_mac_files on what it writes (R5: a repository harness for ReleveFP 1.10)"""
    import shutil as _sh
    base_dir = os.path.join(SCRATCH, "rv3rel")
    os.makedirs(base_dir, exist_ok=True)
    if not _sh.which("g++"):
        check("review3 R5: g++ is there to build ReleveFP's harness", False, "g++ absent")
        return
    mock = os.path.join(HERE, "releve_mock")
    cpp = os.path.join(base_dir, "releve.cpp")
    r = subprocess.run([sys.executable, "-I", os.path.join(C.LAB, "live_ai", "check", "to_cpp.py"), os.path.join(MQL5, "ReleveFP.mq5"), cpp],
                       capture_output=True, text=True)
    with open(os.path.join(base_dir, "run.cpp"), "w") as f:
        f.write('#include "mock_mt5.h"\n#include "releve.cpp"\nint main() { OnStart(); return 0; }\n')
    b = subprocess.run(["g++", "-std=c++17", "-O1", "-w", "-I", mock, "-I", base_dir, os.path.join(base_dir, "run.cpp"), "-o",
                        os.path.join(base_dir, "run")], capture_output=True, text=True)
    if not check("review3 R5: ReleveFP.mq5 1.10 translates, compiles and links against the MT5 imitation (CopyRates, Bars, SeriesInfoInteger)",
                 r.returncode == 0 and b.returncode == 0, (r.stderr[-300:], b.stderr[-1500:])):
        return

    def run(name, **env):
        files = os.path.join(base_dir, "F_" + name)
        if os.path.isdir(files):
            shutil.rmtree(files)
        os.makedirs(files)
        log = os.path.join(base_dir, f"open_{name}.log")
        if os.path.exists(log):
            os.remove(log)
        e = dict(os.environ, MOCK_FILES=files, MOCK_OPEN_LOG=log, **{k: str(v) for k, v in env.items()})
        rr = subprocess.run([os.path.join(base_dir, "run")], env=e, capture_output=True, text=True, timeout=600)
        d = os.path.join(files, "claude", "releve")
        fini = {}
        if os.path.exists(os.path.join(d, "fini.txt")):
            for ln in open(os.path.join(d, "fini.txt")).read().splitlines():
                k, _, v = ln.partition("=")
                fini[k] = v
        opened = open(log).read().split() if os.path.exists(log) else []
        rows = (len(open(os.path.join(d, "r1_XAUUSD.csv")).read().splitlines()) - 1) if os.path.exists(os.path.join(d, "r1_XAUUSD.csv")) else -1
        return {"rc": rr.returncode, "fini": fini, "opened": opened, "dir": d, "rows": rows, "files": sorted(os.listdir(d)) if os.path.isdir(d) else []}

    def key(fl, k):
        m = re.search(r"(?:^| )" + k + r"=(-?\d+)", fl or "")
        return int(m.group(1)) if m else None
    p = run("plain")
    r1s = [f for f in p["files"] if f.startswith("r1_")]
    rate_src = releve_rate_default(lit["releve_src"])
    chk("review3 R4: ReleveFP writes r1 files for the robot's four markets only (InpRateSymbols), each with its own days (as its "
        "InpRateSymbols default says; gold 200)",
        lambda: (p["rc"] == 0 and r1s == ["r1_BTCUSD.csv", "r1_ETHUSD.csv", "r1_US100.csv", "r1_XAUUSD.csv"]
                 and key(p["fini"].get("XAUUSD"), "jours_r1") == 200 == rate_src.get("XAUUSD")
                 and all(key(p["fini"].get(b), "jours_r1") == rate_src.get(b) for b in C.ROBOT_BASES), (r1s, p["fini"].get("XAUUSD"), rate_src)))
    m1i = [i for i, f in enumerate(p["opened"]) if "m1_" in f]
    r1i = [i for i, f in enumerate(p["opened"]) if "r1_" in f]
    chk("review3 R14: every m1 file is written before any r1 file (a slow terminal history never delays the minutes)",
        lambda: (bool(m1i) and bool(r1i) and max(m1i) < min(r1i), p["opened"]))
    chk("review3 R3 (erreur_barres): fini.txt names Max bars in chart (max_barres=) and, per market, the series' first and last bar and "
        "its last error", lambda: ("max_barres" in p["fini"] and key(p["fini"].get("XAUUSD"), "debut_r1") and key(p["fini"].get("XAUUSD"), "fin_r1")
                                   and key(p["fini"].get("XAUUSD"), "erreur_r1") == 0, p["fini"].get("XAUUSD")))
    q = run("loading", MOCK_R1_LOAD_MS=3000)
    chk("review3 R2: a terminal whose M1 series is still loading (CopyRates gives 0 twice at once) is waited for: every bar written",
        lambda: (q["rc"] == 0 and q["rows"] == p["rows"] > 0 and key(q["fini"].get("XAUUSD"), "synchro_r1") == 1, (q["rows"], p["rows"], q["fini"].get("XAUUSD"))))
    w = run("weekend", MOCK_NOW=1794479400 + 2 * 86400, MOCK_R1_AFTER_LAST=1)
    chk("review3 R3 (erreur_barres): a Saturday run whose days after the last bar answer -1 counts no error (erreur_barres=0)",
        lambda: (w["rc"] == 0 and key(w["fini"].get("XAUUSD"), "erreur_barres") == 0 and w["rows"] > 0, w["fini"].get("XAUUSD")))
    h = run("partial", MOCK_R1_PARTIAL=1)
    chk("review3 R7: a day whose later calls fail keeps the bars of its first answer (written, counted short), never dropped silently",
        lambda: (h["rc"] == 0 and h["rows"] > 0 and (key(h["fini"].get("XAUUSD"), "jours_courts") or 0) > 0, (h["rows"], h["fini"].get("XAUUSD"))))
    src = lit["releve_src"]
    chk("review3 R16/R13: ReleveFP's header says it adds its markets to Market Watch, its description names the r1 bars",
        lambda: ("Market Watch" in src[:2500] and re.search(r'#property description "[^"]*r1', src) is not None, src[:300]))
    out = os.path.join(base_dir, "t1_out")
    rc, so, se = run_tool("read_mac_files.py", [p["dir"], "--out", out])
    s = json.load(open(os.path.join(out, "summary.json"))) if rc == 0 else {"checks": []}
    ck = {(c["market"], c["item"]): c for c in s["checks"]}
    chk("review3 R5: read_mac_files reads what ReleveFP 1.10 writes (r1 rows = barres=, version, Max bars)",
        lambda: (rc == 0 and ck.get(("XAUUSD", "r1_rows"), {}).get("status") == "OK" and ck.get(("compte", "max_bars"), {}).get("status") == "OK"
                 and ck.get(("compte", "releve_version"), {}).get("status") == "OK", (se[-300:], ck.get(("XAUUSD", "r1_rows")))))


def test_review3_replay(lit, obs, full):
    """the third review's replay cases: R3-1 (a disconnection over a live paper line: the rebuild's rp=1 lines stand for
    the live ones), R15 (each market's spread convention judged on its own lines)"""
    jobs = os.path.join(obs, "ClaudeRobot")
    t_line = None
    for f in sorted(os.listdir(jobs)):
        if f < "20211115.log":
            continue
        for ln in open(os.path.join(jobs, f)).read().splitlines():
            if "|PFILL|BKB|" in ln and "|rp=1" not in ln:
                t_line = int(ln.split("|")[1])
                break
        if t_line:
            break
    world = os.path.join(SCRATCH, "world_disconnect.txt")
    with open(world, "w") as fh:
        fh.write(f"{C.utc_to_srv(t_line) - 120} disconnect 300\n")
    disc, wall, _ = harness_live("live_disconnect", SPAN, {"MOCK_INPUT_InpTrade": "false", "MOCK_FAULTS": world})
    rb = [ln for f in sorted(os.listdir(os.path.join(disc, "ClaudeRobot"))) for ln in open(os.path.join(disc, "ClaudeRobot", f)).read().splitlines()
          if "|REBUILD|" in ln and "why=reconnect" in ln]
    out = os.path.join(SCRATCH, "out_disconnect")
    rc, so, se = run_tool("check_demo.py", ["--journals", disc, "--bars", full, "--out", out])
    r = json.load(open(os.path.join(out, "report.json"))) if rc == 0 else {}
    cm = r.get("replay", {}).get("comparison", {})
    chk("review3 R3-1: a 5-minute disconnection over a live BKB paper line (REBUILD why=reconnect): its rp=1 lines stand for the live ones, "
        "no replay difference, nothing abnormal",
        lambda: (rc == 0 and len(rb) == 1 and not cm.get("differences") and cm.get("rebuild_lines_used", 0) > 0 and r.get("anomalies") == [],
                 (len(rb), [(d["kind"], d["event"], d["code"], d["when"]) for d in cm.get("differences", [])][:4], r.get("anomalies"), se[-300:])))
    # R15: BTC's minutes hide the bar spread (ReleveFP 1.00, no sp_min), the other markets' give it at the open
    mixed = os.path.join(SCRATCH, "csv_btc_hidden")
    shutil.copytree(full, mixed)
    dg, rec = bars_2021("BTCUSD", *SPAN)
    write(os.path.join(mixed, "m1_BTCUSD.csv"), m1_text(raw_gold("BTCUSD", rec), dg, lit, "min_hidden", 0, "1.00"))
    out2 = os.path.join(SCRATCH, "out_btc_hidden")
    rc, so2, se = run_tool("check_demo.py", ["--journals", obs, "--bars", mixed, "--out", out2])
    r2 = json.load(open(os.path.join(out2, "report.json"))) if rc == 0 else {}
    rp2 = r2.get("replay", {})
    chk("review3 R15: one market whose minutes do not give the bar spread is set aside alone (BTC); the others are replayed with no difference",
        lambda: (rc == 0 and rp2.get("status") == "done" and rp2.get("unusable_markets") == ["BTCUSD"] and not rp2["comparison"]["differences"]
                 and all(rp2["coverage"][c]["never"] for c in ("BKB", "F1B", "NQB")) and not rp2["coverage"]["ORX"]["never"],
                 (rp2.get("status"), rp2.get("unusable_markets"), len(rp2.get("comparison", {}).get("differences", [])), se[-300:])))
    shutil.rmtree(mixed, ignore_errors=True)


# ---------------------------------------------------------------------------------------------- the fourth review
def releve_rate_default(src):
    """ReleveFP.mq5's default InpRateSymbols as {market: days}"""
    m = re.search(r'input\s+string\s+InpRateSymbols\s*=\s*"([^"]*)"', src)
    out = {}
    for part in (m.group(1) if m else "").split(","):
        k, _, v = part.partition(":")
        if k.strip() and v.strip().isdigit():
            out[k.strip()] = int(v)
    return out


def days_needed(b, demo_days=C.DEMO_DAYS_MAX):
    """calendar days of terminal bars a robot market needs (review4 A1), computed here from the robot's constants: the replay
    robot is READY only once its bars reach back DEPTH_DAYS (CR_Bars.mqh, CR_Registry.mqh: gold 120, the others 60), the
    rules need their warm-up, then a demo of four weeks at most and a week between the demo's end and ReleveFP's run"""
    warm = max(C.WARMUP_DAYS[c] for c, s in C.SYM_OF_CODE.items() if b in C.READS_OF_CODE[c])
    return max(warm, C.DEPTH_DAYS[b]) + demo_days + 7


def test_review4_releve(lit):
    """the fourth review's cases on ReleveFP.mq5 and demo_common (A1/RC3-R4: the r1 days against the robot's depth, A9)"""
    src = lit["releve_src"]
    rate = releve_rate_default(src)
    need = {b: days_needed(b) for b in C.ROBOT_BASES}
    chk("review4 A1/RC3-R4: demo_common.R1_DAYS_NEEDED counts the robot's depth (DEPTH_DAYS: 60 days for US100, BTCUSD, ETHUSD, 120 "
        "for gold) + a four-week demo + a week: at least 95 and 155 days",
        lambda: (all(C.R1_DAYS_NEEDED.get(b, 0) >= need[b] for b in C.ROBOT_BASES), (C.R1_DAYS_NEEDED, need)))
    chk("review4 A1/RC3-R4: ReleveFP's default InpRateSymbols gives every robot market those days "
        "(XAUUSD:200,US100:100,BTCUSD:100,ETHUSD:100) and the version is 1.10 or later (review7: 1.11)",
        lambda: (all(rate.get(b, 0) >= need[b] for b in C.ROBOT_BASES) and rate.get("XAUUSD") == 200
                 and rate.get("US100") == rate.get("BTCUSD") == rate.get("ETHUSD") == 100
                 and re.search(r'#property version\s+"1\.1[01]"', src) is not None and re.search(r'"version=1\.1[01]\\n"', src) is not None,
                 (rate, need)))
    chk("review4 A9: ReleveFP waits up to 300 s for a loading M1 series (InpRateWait default)",
        lambda: (re.search(r"input\s+int\s+InpRateWait\s*=\s*300\s*;", src) is not None,
                 (re.search(r"input\s+int\s+InpRateWait[^\n]*", src) or re.search("x", "x")).group(0)))


def test_review4_tool1(lit):
    """the fourth review's cases of read_mac_files.py: A1/RC3-R4 (r1 days against the robot's depth), RC3-inpdays (m1 days
    before r1's first day), RC3-R2 and A9 (synchro_r1=0, a newest day half loaded, weekdays without bars), RC3-tool1 (an
    unreadable r1 file), A8 (the bar spread against the ticks' smallest), A12 (times out of range)"""
    base_dir = os.path.join(SCRATCH, "rv4t1")

    def go(name, prep=None, **kw):
        folder = os.path.join(base_dir, "in_" + name)
        out = os.path.join(base_dir, "out_" + name)
        make_releve(folder, lit, "good", **kw)
        if prep:
            prep(folder)
        rc, so, se = run_tool("read_mac_files.py", [folder, "--out", out])
        s = json.load(open(os.path.join(out, "summary.json"))) if rc == 0 else {"checks": [], "problems": []}
        return {"rc": rc, "so": so, "se": se, "ck": {(c["market"], c["item"]): c for c in s["checks"]}, "s": s}

    def fini_edit(folder, fn):
        p = os.path.join(folder, "fini.txt")
        write(p, "\n".join(fn(lines_of(p))) + "\n")

    def r1_keep(folder, base, keep_fn):
        """keep the r1 rows keep_fn(time) says, and set fini.txt's barres= and jours_barres= to what is left (a run that wrote them so)"""
        p = os.path.join(folder, f"r1_{base}.csv")
        ls = lines_of(p)
        keep = [ls[0]] + [ln for ln in ls[1:] if keep_fn(int(ln.split(",")[0]))]
        write(p, "\n".join(keep) + "\n")
        nd = len({int(ln.split(",")[0]) // 86400 for ln in keep[1:]})
        fini_edit(folder, lambda ls_: [re.sub(r"jours_barres=\d+", f"jours_barres={nd}", re.sub(r"(?<![a-z_])barres=\d+", f"barres={len(keep) - 1}", ln))
                                       if ln.startswith(base + "=") else ln for ln in ls_])
    st = lambda g, b, i: g["ck"].get((b, i), {}).get("status")                    # noqa: E731
    nt = lambda g, b, i: g["ck"].get((b, i), {}).get("note", "")                  # noqa: E731
    g = go("a1_r1_75", r1_from="2021-05-15 00:00", r1_days={"US100": 75, "BTCUSD": 75, "ETHUSD": 75})
    chk("review4 A1/RC3-R4 (tool 1): r1 files of 75 calendar days for US100, BTCUSD and ETHUSD are DIFFERENT with the days needed "
        "(the robot's 60-day depth) and the InpRateSymbols to set; gold's 200 days are OK",
        lambda: (g["rc"] == 0 and all(st(g, b, "r1_days") == "DIFFERENT" for b in ("US100", "BTCUSD", "ETHUSD"))
                 and "InpRateSymbols" in nt(g, "US100", "r1_days") and "US100:100" in nt(g, "US100", "r1_days")
                 and st(g, "XAUUSD", "r1_days") == "OK", (g["ck"].get(("US100", "r1_days")), g["ck"].get(("XAUUSD", "r1_days")), g["se"][-300:])))
    g = go("inpdays_m1_150", m1_from="2021-07-04 00:00", r1_days={"XAUUSD": 200, "US100": 100, "BTCUSD": 100, "ETHUSD": 100})
    chk("review4 RC3-inpdays (tool 1): m1 minutes over 150 days and r1 bars over ReleveFP's 100 days: the m1 days before r1's first day "
        "are not 'barres manquantes', and 100 days are enough",
        lambda: (g["rc"] == 0 and all(st(g, b, "r1_rows") == "OK" and st(g, b, "r1_days") == "OK" for b in C.ROBOT_BASES),
                 [(b, st(g, b, "r1_rows"), nt(g, b, "r1_rows")[:120], st(g, b, "r1_days")) for b in C.ROBOT_BASES]))

    def synchro0(folder):
        fini_edit(folder, lambda ls: [ln.replace("synchro_r1=1", "synchro_r1=0").replace("attente_r1=2", "attente_r1=300")
                                      if ln.startswith("XAUUSD=") else ln for ln in ls])
    g = go("r2_synchro0", prep=synchro0)
    chk("review4 RC3-R2/A9 (tool 1): synchro_r1=0 in fini.txt (the M1 series still loading when ReleveFP gave up) is DIFFERENT "
        "'relancer ReleveFP'",
        lambda: (g["rc"] == 0 and st(g, "XAUUSD", "r1_rows") == "DIFFERENT" and "relancer ReleveFP" in nt(g, "XAUUSD", "r1_rows")
                 and "synchro" in nt(g, "XAUUSD", "r1_rows"), g["ck"].get(("XAUUSD", "r1_rows"))))

    def newest_half(folder):
        p = os.path.join(folder, "r1_XAUUSD.csv")
        last_day = max(int(ln.split(",")[0]) for ln in lines_of(p)[1:]) // 86400 * 86400
        r1_keep(folder, "XAUUSD", lambda t: t < last_day + 12 * 3600)
    g = go("r2_newest_half", prep=newest_half)
    chk("review4 RC3-R2 (tool 1): an r1 file whose newest day stops half way (fini.txt matching) is DIFFERENT: its last bar is hours "
        "before the last m1 minute",
        lambda: (g["rc"] == 0 and st(g, "XAUUSD", "r1_rows") == "DIFFERENT" and "relancer ReleveFP" in nt(g, "XAUUSD", "r1_rows"),
                 g["ck"].get(("XAUUSD", "r1_rows"))))
    gap = set(range(srv("2021-08-09 00:00"), srv("2021-08-21 00:00"), 86400))
    g = go("a9_gap", prep=lambda f: r1_keep(f, "XAUUSD", lambda t: t // 86400 * 86400 not in gap), r1_from="2021-06-01 00:00")
    chk("review4 A9 (tool 1): ten weekdays without any bar inside an r1 file, before the m1 minutes (fini.txt matching), are DIFFERENT "
        "'jour(s) de semaine sans barre'",
        lambda: (g["rc"] == 0 and st(g, "XAUUSD", "r1_rows") == "DIFFERENT" and "sans barre" in nt(g, "XAUUSD", "r1_rows"),
                 g["ck"].get(("XAUUSD", "r1_rows"))))

    def utf16_r1(folder):
        p = os.path.join(folder, "r1_XAUUSD.csv")
        t = open(p, "rb").read().decode("cp1252")
        open(p, "wb").write(b"\xff\xfe" + t.encode("utf-16-le"))
    g = go("r1_utf16", prep=utf16_r1)
    chk("review4 RC3-tool1: an r1 file re-saved in UTF-16 (unreadable) is DIFFERENT, not OK",
        lambda: (g["rc"] == 0 and st(g, "XAUUSD", "r1_rows") == "DIFFERENT", g["ck"].get(("XAUUSD", "r1_rows"))))

    def r1_spread(fn):
        def prep(folder):
            p = os.path.join(folder, "r1_US100.csv")
            ls = lines_of(p)
            out = [ls[0]]
            for ln in ls[1:]:
                f = ln.split(",")
                f[6] = str(fn(int(f[6])))
                out.append(",".join(f))
            write(p, "\n".join(out) + "\n")
        return prep
    g = go("a8_zero", prep=r1_spread(lambda s: 0))
    chk("review4 A8 (tool 1): bar spread 0 in the terminal's bars (r1) while the minutes' ticks have a spread (sp_min) is DIFFERENT: the "
        "robot's paper would pay no spread",
        lambda: (g["rc"] == 0 and st(g, "US100", "bar_spread") == "DIFFERENT" and "papier" in nt(g, "US100", "bar_spread"),
                 g["ck"].get(("US100", "bar_spread"))))
    g = go("a8_below", prep=r1_spread(lambda s: max(s - 3, 0)))
    chk("review4 A8 (tool 1): a bar spread below the minute's smallest tick spread on most minutes is DIFFERENT",
        lambda: (g["rc"] == 0 and st(g, "US100", "bar_spread") == "DIFFERENT", g["ck"].get(("US100", "bar_spread"))))
    g = go("a8_ctrl")
    chk("review4 control A8 (tool 1): a bar spread equal to the minute's smallest tick spread stays OK (information)",
        lambda: (g["rc"] == 0 and all(st(g, b, "bar_spread") == "OK" for b in C.ROBOT_BASES), [g["ck"].get((b, "bar_spread")) for b in C.ROBOT_BASES]))

    def big_fini(folder):
        fini_edit(folder, lambda ls: [re.sub(r"^server_time=(\d+)", r"server_time=\g<1>000000", ln) for ln in ls])
    g = go("a12_fini", prep=big_fini)
    chk("review4 A12 (tool 1): fini.txt's server_time with six more digits: a report, no traceback, the value set aside",
        lambda: (g["rc"] == 0 and "Traceback" not in g["se"], g["se"][-500:]))

    def big_m1(folder):
        p = os.path.join(folder, "m1_XAUUSD.csv")
        ls = lines_of(p)
        f = ls[2].split(",")
        f[0] += "000000"
        ls[2] = ",".join(f)
        write(p, "\n".join(ls) + "\n")
    g = go("a12_m1", prep=big_m1)
    chk("review4 A12 (tool 1): one m1 row whose time has six more digits is dropped and counted; the file is read (not 'illisible')",
        lambda: (g["rc"] == 0 and not any("m1_XAUUSD.csv illisible" in p for p in g["s"].get("problems", [])) and "XAUUSD" in g["s"].get("m1", {})
                 and "1 ligne(s) illisible(s)" in nt(g, "XAUUSD", "m1_rows"), (g["s"].get("problems"), g["ck"].get(("XAUUSD", "m1_rows")), g["se"][-300:])))


def test_review4_journal(lit):
    """the fourth review's journal cases on hand-made journals: A4 (demo settings), A5 (execution costs), A6 (refused stop moves),
    A7 (balance moves from outside), A8 (bar spread 0), A11 (money window), A12, A13, A14, the VPS note (A2), RC3-R3-1b and 1c
    (reconnections), RC3-R3-2 (purge with a restart), RC3-R3-4 (tick grid), RC3-new-crash, RC3-R2/A9 (r1 not synchronized)"""
    base_dir = os.path.join(SCRATCH, "rv4j")

    def go(name, variant=(), extra=(), prep=None, style="live"):
        jdir = os.path.join(base_dir, "j_" + name, "ClaudeRobot")
        info = md_journal(jdir, variant, style)
        if prep:
            prep(jdir, info)
        out = os.path.join(base_dir, "out_" + name)
        rc, so, se = run_tool("check_demo.py", ["--journals", os.path.dirname(jdir), "--out", out] + list(extra))
        rp = os.path.join(out, "report.json")
        r = json.load(open(rp)) if rc == 0 and os.path.exists(rp) else {}
        rt = os.path.join(out, "report_fr.txt")
        rtxt = open(rt, encoding="utf-8").read() if rc == 0 and os.path.exists(rt) else ""
        return {"rc": rc, "so": so, "se": se, "r": r, "rtxt": rtxt, "info": info, "jdir": jdir, "an": " | ".join(r.get("anomalies", [])),
                "txt": (outputs_text(out) if rc == 0 else "") + so + se}
    base = go("base")
    chk("review4 control: the clean hand-made demo (S7 typed, a balance that follows the trades) has nothing abnormal",
        lambda: (base["rc"] == 0 and base["r"]["anomalies"] == [], (base["an"][:500], base["se"][-300:])))
    # A4: the demo's settings
    for v, word, what in (("plan_future", "plan pas encore en vigueur", "a PLAN state 'future' whose start lies after the whole journal"),
                          ("risk_d2", S7, "a risk table other than S7 (here the build's default D2), shown with S7's text"),
                          ("sleeves_gfp", "sleeves GFP", "InpSleeves other than ALL"),
                          ("demo0", "compte reel", "INIT demo=0 (a real account)"),
                          ("sym_noR", "US100.r", "a symbol that is not the .r name"),
                          ("k1_off", "interrupteur K1", "a switch (K1) off on the demo account")):
        g = go("a4_" + v, (v,))
        chk(f"review4 A4: {what} is an anomaly", lambda: (g["rc"] == 0 and word in g["an"] and "Rien d'anormal" not in g["so"], g["an"][:400]))

    def no_trade(jdir, info):
        for f in os.listdir(jdir):
            edit_lines(os.path.join(jdir, f), lambda ls: [ln for ln in ls if not any(f"|{e}|" in ln for e in ("SEND", "FILL", "CLOSE", "ADOPT"))])
    g = go("a4_no_trade", prep=no_trade)
    chk("review4 A4: intents sized to send (SIZE skip=none) and no real trade while the copy is not an observer is an anomaly",
        lambda: (g["rc"] == 0 and "aucun trade reel" in g["an"], g["an"][:400]))
    # A5: execution costs against the lab's (fp_costs.json, the 1.5 x the rules were tested with)
    g = go("a5_slip", ("slip_gold",))
    chk("review4 A5: gold fills 4 bp worse than their quote and closes 4 bp worse than the paper (13 x the lab's 0.3 bp) are an anomaly "
        "naming the market and the lab's figure",
        lambda: (g["rc"] == 0 and "XAUUSD" in g["an"] and "glissement" in g["an"] and "1,5" in g["an"], g["an"][:600]))
    chk("review4 A5: stdout judges the execution costs against the lab ('frais d'execution'), in the margin on the clean demo",
        lambda: (base["rc"] == 0 and "frais d'execution" in base["so"].lower() and "glissement" not in base["an"], base["so"][:900]))
    # A6: refused stop moves
    g = go("a6_refused", ("slmod_refused",))
    chk("review4 A6: stop moves refused by the broker (SLMOD ok=0, rc 10029 freeze level) and never done are an anomaly naming the "
        "retcode, the market and the count",
        lambda: (g["rc"] == 0 and "10029" in g["an"] and "BTCUSD" in g["an"] and "gel" in g["an"] and "6" in g["an"], g["an"][:500]))
    g = go("a6_once", ("slmod_once",))
    chk("review4 control A6: a stop move refused once and done at the next try is no anomaly",
        lambda: (g["rc"] == 0 and g["r"]["anomalies"] == [], g["an"][:400]))
    # A7: balance moves from outside the robot
    for v, what in (("deposit", "a balance 500 EUR above what the trades made (a deposit, a hand trade's gain)"),
                    ("hand_loss", "a balance 700 EUR below what the trades and their costs explain (a hand trade's loss)"),
                    ("p_in", "a payment of 500 EUR (P_in of the SIZE lines changes)")):
        g = go("a7_" + v, (v,))
        m = (g["r"].get("fills") or {}).get("money_estimate") or {}
        chk(f"review4 A7: {what} is an anomaly ('le solde a bouge pour une autre raison') and the money estimate is incomplete",
            lambda: (g["rc"] == 0 and "le solde a bouge" in g["an"] and m.get("complete") is False, (g["an"][:500], m.get("incomplete_why"))))
    # A8: a bar spread of 0 in the COST lines
    def cost_zero(jdir, info):
        for f in os.listdir(jdir):
            edit_lines(os.path.join(jdir, f), lambda ls: [re.sub(r"\|raw_bp=[^|]*\|paper_bp=[^|]*", "|raw_bp=0.0000000000000000e+00|paper_bp="
                                                                 "0.0000000000000000e+00", ln) if "|COST|US100|" in ln else ln for ln in ls])
    g = go("a8_cost0", prep=cost_zero)
    chk("review4 A8 (check_demo): COST lines whose bar spread is 0 (raw_bp 0) are an anomaly: the paper pays no spread",
        lambda: (g["rc"] == 0 and "US100" in g["an"] and "nul" in g["an"] and "papier" in g["an"], g["an"][:400]))
    # A11: the money window and the result since the start
    tl = next((ln for ln in base["so"].splitlines() if ln.startswith("Solde")), "")
    chk("review4 A11: the money line says its window ('du soir du ... au soir du ...') and gives the result since the start (B(T))",
        lambda: (base["rc"] == 0 and "soir du" in tl and "depuis le debut" in tl, base["so"][:900]))
    # RC3-R3-1b: a sizing skip restated at a reconnection; one trade counted once
    g = go("r31b_cap", ("reconnect_cap",))
    chk("review4 RC3-R3-1b: a MISSED cap written at a reconnection's reconcile, repeating the SIZE skip=cap of its oid, is not an anomaly",
        lambda: (g["rc"] == 0 and "MISSED non envoyes" not in g["an"], g["an"][:400]))
    g = go("r31b_twice", ("missed_twice",))
    chk("review4 RC3-R3-1b: two MISSED lines of one trade count as one ('1 trade(s) MISSED non envoyes')",
        lambda: (g["rc"] == 0 and "1 trade(s) MISSED non envoyes" in g["an"], g["an"][:400]))
    # RC3-R3-1c: the outage said plainly
    g = go("r31c_outage", ("outage",))
    chk("review4 RC3-R3-1c: a reconnection is said on stdout without --bars: when the robot came back and how long at most it was offline",
        lambda: (g["rc"] == 0 and "hors ligne" in g["so"] and "2021-11-23 10:00 UTC" in g["so"] and "au plus" in g["so"], g["so"][:900]))
    nfl = next((ln for ln in g["so"].splitlines() if "non suivi" in ln), "")
    chk("review4 RC3-R3-1c: the paper trade opened and closed while the robot was offline (only rp=1 lines) is named 'non suivi' on stdout "
        "and in the verdict (information: the robot did what it must, the demo has one real trade less)",
        lambda: (g["rc"] == 0 and "NQB le 2021-11-23 09:00 UTC" in nfl
                 and (any(ln.startswith("Rien d'anormal") and "non suivi" in ln for ln in g["so"].splitlines()) or g["r"]["anomalies"]),
                 (nfl, g["so"][-400:])))
    chk("review4 RC3-R3-1c: the MISSED late just after the reconnection is described as a trade open during the outage, not a start's",
        lambda: (g["rc"] == 0 and "coupure" in g["rtxt"] and "BKE late" in g["rtxt"] and "deja ouverts a un demarrage" not in g["rtxt"],
                 [ln for ln in g["rtxt"].splitlines() if "late" in ln][:4]))

    # RC3-R3-2: the first start purged, a later restart kept
    def purged_restart(jdir, info):
        for f in ("20211117.log", "20211118.log"):
            os.remove(os.path.join(jdir, f))
        d = srv("2021-10-25 00:00")
        write(os.path.join(jdir, "20211026.log"), jl(C.srv_to_utc(d + 86400) + 30, "DAY", "-", ("day", d), ("balance", 10000.0),
                                                    ("equity", 10000.0), ("bars_fed", 5000)) + "\n", crlf=True)
    g = go("r32_purged_restart", ("restart",), prep=purged_restart)
    chk("review4 RC3-R3-2: a copy whose first start was purged (no INIT, files over 30 days) and that holds a later restart gets the "
        "purge note", lambda: (g["rc"] == 0 and "efface lui-meme" in g["an"], g["an"][:500]))
    chk("review4 RC3-R3-2: no Python 'None' on stdout or in report_fr.txt, and no readiness text ('jamais pret') for the start without INIT",
        lambda: (g["rc"] == 0 and "None" not in g["so"] and "None" not in g["rtxt"] and "jamais pret" not in g["rtxt"],
                 (g["so"][:300], [ln for ln in g["rtxt"].splitlines() if "None" in ln or "jamais pret" in ln][:4])))
    # RC3-R3-4: a broker stop on the tick grid (US100 0.25)
    fdir = os.path.join(base_dir, "fiches_tick")

    def tick025(fi):
        fi["US100"][0].update(tick_size=0.25, tick_value=0.25 * 0.86)
    make_releve(fdir, lit, "good", m1_from="2021-11-24 00:00", m1_to="2021-11-25 00:00", tweak=tick025)
    g = go("r34_tick", ("n30_stop_grid",), extra=("--fiches", os.path.join(fdir, "fiches.csv")))
    chk("review4 RC3-R3-4: a broker stop on US100's tick grid (0.25 in fiches.csv: the paper stop 16200.10 is 16200.00 at the broker) is "
        "not a lost SLMOD", lambda: (g["rc"] == 0 and "SLMOD" not in g["an"], g["an"][:500]))

    # RC3-new-crash: values the schema accepts that a division or a log cannot take
    def pfill_px0(jdir, info):
        edit_lines(os.path.join(jdir, "20211124.log"), lambda ls: [re.sub(r"\|px=[^|]*", "|px=0.0000000000000000e+00", ln, count=1)
                                                                   if "|PFILL|N30|" in ln else ln for ln in ls])
    g = go("crash_px0", prep=pfill_px0)
    chk("review4 RC3-new-crash: a PFILL px=0 for a filled trade: a report, no traceback", lambda: (g["rc"] == 0 and "Traceback" not in g["se"],
                                                                                              g["se"][-400:]))

    def ask_eq_bid(jdir, info):
        def f(ls):
            out = []
            for ln in ls:
                if "|SEND|N30|" in ln:
                    ln = re.sub(r"\|ask=[^|]*", "|ask=" + re.search(r"\|bid=([^|]*)", ln).group(1), ln)
                out.append(ln)
            return out
        edit_lines(os.path.join(jdir, "20211124.log"), f)
    g = go("crash_askbid", prep=ask_eq_bid)
    chk("review4 RC3-new-crash: a SEND line whose ask equals its bid (no fiches.csv): a report, no traceback",
        lambda: (g["rc"] == 0 and "Traceback" not in g["se"], g["se"][-400:]))
    # A12: a malformed --input; times out of range in the releve beside the journal
    g = go("a12_input", extra=("--input", "InpGuard"))
    chk("review4 A12: a --input without '=' is refused with a plain message before the run (no traceback)",
        lambda: (g["rc"] != 0 and "Traceback" not in g["se"] and "--input" in g["se"] + g["so"], (g["rc"], g["se"][-300:])))
    rdir = os.path.join(base_dir, "rel_bigfini")
    make_releve(rdir, lit, "good", m1_from="2021-11-15 00:00", m1_to="2021-11-26 00:00")
    p = os.path.join(rdir, "fini.txt")
    write(p, "\n".join(re.sub(r"^server_time=(\d+)", r"server_time=\g<1>000000", ln) for ln in lines_of(p)) + "\n")
    g = go("a12_fini", extra=("--bars", rdir, "--no-replay"))
    chk("review4 A12 (check_demo): fini.txt's server_time with six more digits beside the releve: a report, no traceback",
        lambda: (g["rc"] == 0 and "Traceback" not in g["se"], g["se"][-400:]))
    rdir2 = os.path.join(base_dir, "rel_bigm1")
    make_releve(rdir2, lit, "good", m1_from="2021-11-15 00:00", m1_to="2021-11-26 00:00")
    p = os.path.join(rdir2, "m1_XAUUSD.csv")
    ls = lines_of(p)
    f2 = ls[2].split(",")
    f2[0] += "000000"
    ls[2] = ",".join(f2)
    write(p, "\n".join(ls) + "\n")

    def drop_deinit(jdir, info):
        edit_lines(os.path.join(jdir, "20211125.log"), lambda ls_: [ln for ln in ls_ if "|deinit=" not in ln])
    g = go("a12_m1", prep=drop_deinit, extra=("--bars", rdir2, "--no-replay"))
    chk("review4 A12 (check_demo): one m1 row whose time has six more digits, with a journal without its stop line: a report, no traceback",
        lambda: (g["rc"] == 0 and "Traceback" not in g["se"], g["se"][-400:]))
    # A13 and the VPS note (A2): printed lines of another copy
    lines = []
    for fn in sorted(os.listdir(base["jdir"])):
        if fn < "20211119.log":
            continue
        for ln in lines_of(os.path.join(base["jdir"], fn)):
            if "|rp=1" in ln:
                continue
            lines.append(re.sub(r"\|bars_fed=\d+", "|bars_fed=7777", ln) if "|DAY|" in ln else ln)
    pf = os.path.join(base_dir, "experts_other_noinit.log")
    utf16_printed(pf, lines)
    g = go("a13_printed", extra=("--printed", pf))
    chk("review4 A13: a printed Experts log without INIT whose DAY lines differ from the files' (another copy, its own bar count) is not "
        "called the same copy", lambda: (g["rc"] == 0 and g["r"]["printed"].get("kind") != "meme copie", g["r"].get("printed", {}).get("kind")))
    allv = [ln for fn in sorted(os.listdir(base["jdir"])) for ln in lines_of(os.path.join(base["jdir"], fn)) if "|rp=1" not in ln]
    pv = os.path.join(base_dir, "experts_vps.log")
    utf16_printed(pv, allv, vps=True)
    g = go("a2_vps_note", extra=("--printed", pv))
    chk("review4 A2 (note): a printed VPS copy (INIT vps=1) is said plainly not checked yet on stdout (its own lines: the VPS phase after "
        "the demo)", lambda: (g["rc"] == 0 and "VPS" in g["so"] and "pas encore verifi" in g["so"], g["so"][-700:]))

    # A14: an INIT symbol suffix carrying a login or a user name
    def sym_leak(jdir, info):
        edit_lines(os.path.join(jdir, "20211117.log"), lambda ls_: [ln.replace("|US100=US100.r", "|US100=US100.58004127").replace(
            "|BTCUSD=BTCUSD.r", "|BTCUSD=BTCUSD.theo.qn") if "|INIT|-|build=" in ln else ln for ln in ls_])
    g = go("a14_sym", prep=sym_leak)
    chk("review4 A14: INIT symbol suffixes holding digits or a user name never reach report.json, report_fr.txt or stdout",
        lambda: (g["rc"] == 0 and "58004127" not in g["txt"] and "theo.qn" not in g["txt"], [w for w in ("58004127", "theo.qn") if w in g["txt"]]))
    # RC3-R2 / A9 in check_demo: the terminal's bars not synchronized when ReleveFP read them
    rdir3 = os.path.join(base_dir, "rel_sync0")
    make_releve(rdir3, lit, "good", m1_from="2021-11-15 00:00", m1_to="2021-11-26 00:00")
    p = os.path.join(rdir3, "fini.txt")
    write(p, "\n".join(ln.replace("synchro_r1=1", "synchro_r1=0") if ln.startswith("XAUUSD=") else ln for ln in lines_of(p)) + "\n")
    g = go("r2_sync0", extra=("--bars", rdir3, "--no-replay"))
    chk("review4 RC3-R2/A9 (check_demo): synchro_r1=0 gives 'relancer ReleveFP' on stdout and an anomaly",
        lambda: (g["rc"] == 0 and "synchro" in g["so"] and "relancer ReleveFP" in g["so"] and "synchro" in g["an"], (g["so"][-600:], g["an"][:300])))


RATE_TEST = {"XAUUSD": 200, "US100": 100, "BTCUSD": 100, "ETHUSD": 100}     # ReleveFP 1.10's InpRateSymbols (review4 A1)
HIST4 = (srv("2021-05-03 00:00"), srv("2021-11-27 00:00"))                 # the bars of the fourth review's demos (in sample)
GO4, END4, RUN4 = srv("2021-10-25 00:00"), srv("2021-11-13 00:00"), srv("2021-11-13 10:00")   # go-live, the demo's end, ReleveFP


def releve_replay(name, lit, run_srv, rate=None, m1_days=30, mutate=None, synchro=None, drop_days=None, zero_spread=()):
    """ReleveFP 1.10's files of a demo's bars as the script writes them when it runs at server time run_srv: r1_<BASE>.csv (the
    'live' robot's own bars, gold raw) over rate[base] days back from the run day, m1_<BASE>.csv over m1_days (MqlRates.spread is
    the minute's smallest tick spread: sp_min), fini.txt with ReleveFP 1.10's keys. synchro: {market: 0} synchro_r1=0; drop_days:
    {market: [server days]} missing from r1 (fini.txt counting what is left); zero_spread: markets whose r1 spread is 0 while their
    ticks (m1) keep the real spread"""
    rate = dict(RATE_TEST, **(rate or {}))
    d = os.path.join(SCRATCH, name)
    os.makedirs(d, exist_ok=True)
    day0 = run_srv - run_srv % 86400
    fini = ["version=1.10", f"server={FAKE_SERVER}", "currency=EUR", "leverage=500", "demo=1", f"server_time={run_srv}",
            f"server_minus_gmt_sec={C.rule_offset(C.srv_to_utc(run_srv))}", "all_symbols=9", "max_barres=500000"]
    for base in C.ROBOT_BASES:
        dg, rec = bars_2021(base, day0 - (rate[base] - 1) * 86400, run_srv)
        rec = raw_gold(base, rec)
        if mutate:
            rec = mutate(base, rec)
        mrec = rec[rec["t"] >= day0 - (m1_days - 1) * 86400]
        write(os.path.join(d, f"m1_{base}.csv"), m1_text(mrec, dg, lit, "min_hidden", 0, "1.10"))
        rr = rec
        if drop_days and base in drop_days:
            rr = rr[~np.isin(rr["t"] // 86400 * 86400, np.array(sorted(drop_days[base]), dtype=np.int64))]
        if base in zero_spread:
            rr = rr.copy()
            rr["s"] = 0
        write(os.path.join(d, f"r1_{base}.csv"), r1_text(rr, dg, lit))
        sy = (synchro or {}).get(base, 1)
        fini.append(f"{base}={base}.r jours={m1_days} minutes={len(mrec)} ticks={3 * len(mrec)} "
                    f"du={time.strftime('%Y.%m.%d %H:%M', time.gmtime(int(mrec['t'][0])))} au={time.strftime('%Y.%m.%d %H:%M', time.gmtime(int(mrec['t'][-1])))} "
                    f"derniere_erreur=0 jours_incomplets=0 barres={len(rr)} jours_barres={len(set((rr['t'] // 86400).tolist()))} erreur_barres=0 "
                    f"jours_courts=0 erreur_r1=0 jours_r1={rate[base]} debut_r1={int(rr['t'][0])} fin_r1={int(rr['t'][-1])} synchro_r1={sy} "
                    f"attente_r1={300 if sy == 0 else 2}")
    write(os.path.join(d, "fini.txt"), "\n".join(fini + ["stopped=0", "seconds=640"]) + "\n")
    return d


def test_review4_replay(lit):
    """the fourth review's replay cases: a demo of 1,000 EUR with S7 (as the user's), go-live 2021-10-25, ReleveFP run 2021-11-13:
    A1 (r1 of 75 days for US100, BTCUSD, ETHUSD: the replay is READY 60 days after its first bar), the default 100 days (control),
    A5 (slippage 10 x the lab's), A6 (a freeze level refusing the trailing moves), A7 (a hand position), A8 (bar spread 0), A9 (ten
    days missing in r1, not synchronized), A10 (an observer restarted with another risk table), RC3-R3-1a (outages over a written-
    later line), RC3-R3-1b (a drop while a cap-skipped paper trade is open), RC3-inpdays (the coverage advice)"""
    t0 = time.time()
    demo_env = {"MOCK_INPUT_InpTrade": "true", "MOCK_INPUT_InpPlanStart": str(GO4), "MOCK_BALANCE": "1000"}

    def check_demo(name, jfiles, bars, extra=()):
        out = os.path.join(SCRATCH, "out4_" + name)
        rc, so, se = run_tool("check_demo.py", ["--journals", jfiles, "--bars", bars, "--out", out] + list(extra))
        r = json.load(open(os.path.join(out, "report.json"))) if rc == 0 else {}
        rp = r.get("replay", {})
        dif = rp.get("comparison", {}).get("differences", [])
        return {"rc": rc, "so": so, "se": se, "r": r, "rp": rp, "dif": dif, "an": " | ".join(r.get("anomalies", [])),
                "short": [(d["kind"], d["event"], d["code"], d["when"], d.get("fields")) for d in dif[:4]]}
    rel100 = releve_replay("rel4_100", lit, RUN4)
    rel75 = releve_replay("rel4_75", lit, RUN4, rate={"US100": 75, "BTCUSD": 75, "ETHUSD": 75})
    clean, _, _ = harness_live("live4_clean", HIST4, demo_env, frm=GO4, to=END4)
    g = check_demo("clean", clean, rel100)
    chk("review4 control: a clean S7 demo of 1,000 EUR with ReleveFP 1.10's default files (r1 100 days): no difference, every sleeve "
        "compared over the whole demo, nothing abnormal",
        lambda: (g["rc"] == 0 and g["rp"].get("status") == "done" and not g["dif"] and g["r"]["anomalies"] == [] and "Rien d'anormal." in g["so"],
                 (g["short"], g["an"][:500], g["so"][-500:], g["se"][-300:])))
    g = check_demo("a1_trading", clean, rel75)
    cov = g["rp"].get("coverage", {})
    chk("review4 A1: the same demo with r1 of 75 days for US100, BTCUSD, ETHUSD (the replay READY only 60 days after their first bar): no "
        "replay difference (SIZE and MISSED compared from the replay's READY)",
        lambda: (g["rc"] == 0 and g["rp"].get("status") == "done" and not g["dif"], (g["short"], g["se"][-300:])))
    chk("review4 A1: the coverage says when the replay became READY for the sleeves it delays, and asks for longer r1 (InpRateSymbols "
        "with the depth: at least 100 days), never InpDays",
        lambda: (g["rc"] == 0 and any("pret" in (v.get("why") or "") for v in cov.values()) and "InpRateSymbols" in g["rp"].get("coverage_advice", "")
                 and "US100:100" in g["rp"].get("coverage_advice", "") and "InpDays" not in g["so"] + json.dumps(g["rp"].get("coverage_advice", "")),
                 ({c: v.get("why") for c, v in cov.items()}, g["rp"].get("coverage_advice"))))
    obs, _, _ = harness_live("live4_observer", HIST4, dict(demo_env, MOCK_INPUT_InpTrade="false"), frm=GO4, to=END4)
    g = check_demo("a1_observer", obs, rel75)
    chk("review4 A1: the observer copy with r1 of 75 days: no SIZE skip difference before the replay's READY (notrade against notready)",
        lambda: (g["rc"] == 0 and g["rp"].get("status") == "done" and not g["dif"], (g["short"], g["se"][-300:])))
    # A5: slippage ten times the lab's on every market, market orders and broker stops
    slip = dict(demo_env)
    for b in C.ROBOT_BASES:
        slip[f"MOCK_SLIP_MKT_BPS_{b}.r"] = repr(10 * C.SLIP_BPS[b][0])
        slip[f"MOCK_SLIP_STOP_BPS_{b}.r"] = repr(10 * C.SLIP_BPS[b][1])
    sl10, _, _ = harness_live("live4_slip10", HIST4, slip, frm=GO4, to=END4)
    g = check_demo("a5_slip10", sl10, rel100)
    chk("review4 A5: slippage 10 x the lab's (fp_costs.json) is an anomaly per market and the balance-based costs are judged above the "
        "lab's allowance", lambda: (g["rc"] == 0 and g["an"].count("glissement") >= 2 and "frais hors des prix" in g["an"] and "Rien d'anormal" not in g["so"],
                                    g["an"][:800]))
    # A6: a freeze level that refuses every stop move of gold
    frz, _, _ = harness_live("live4_freeze", HIST4, dict(demo_env, MOCK_BALANCE="10000", **{"MOCK_FREEZE_XAUUSD.r": "100000"}), frm=GO4, to=END4)
    g = check_demo("a6_freeze", frz, rel100)
    chk("review4 A6: a freeze level refusing gold's stop moves (SLMOD rc=10029) is an anomaly naming the retcode",
        lambda: (g["rc"] == 0 and "10029" in g["an"] and "gel" in g["an"], (g["an"][:500], g["r"].get("journal", {}).get("broker_retcodes"))))
    # A7: a position opened by hand on the account
    world = os.path.join(SCRATCH, "world4_hand.txt")
    with open(world, "w") as fh:
        fh.write(f"{srv('2021-11-03 15:00')} hand_open XAUUSD.r 1 0.5\n{srv('2021-11-05 18:00')} hand_close\n")
    hnd, _, _ = harness_live("live4_hand", HIST4, dict(demo_env, MOCK_BALANCE="10000", MOCK_FAULTS=world), frm=GO4, to=END4)
    g = check_demo("a7_hand", hnd, rel100)
    m = (g["r"].get("fills") or {}).get("money_estimate") or {}
    chk("review4 A7: a hand position (magic 777) on the account: 'le solde a bouge pour une autre raison', the estimate incomplete",
        lambda: (g["rc"] == 0 and "le solde a bouge" in g["an"] and m.get("complete") is False, (g["an"][:500], m.get("incomplete_why"))))

    # A8: bar spread 0 on US100 and BTCUSD (the robot's bars and r1), the ticks with their spread
    def zero(base, rec):
        if base in ("US100", "BTCUSD"):
            rec = rec.copy()
            rec["s"] = 0
        return rec
    zs, _, _ = harness_live("live4_zero", HIST4, demo_env, mutate=zero, frm=GO4, to=END4)
    relz = releve_replay("rel4_zero", lit, RUN4, zero_spread=("US100", "BTCUSD"))
    g = check_demo("a8_zero", zs, relz)
    chk("review4 A8 (replay): bar spread 0 in the robot's bars while the releve's ticks have a spread: an anomaly naming the markets",
        lambda: (g["rc"] == 0 and "US100" in g["an"] and "BTCUSD" in g["an"] and "papier" in g["an"], g["an"][:600]))
    # A9: ten weekdays missing in gold's r1, not synchronized
    gap = [d for d in range(srv("2021-08-09 00:00"), srv("2021-08-21 00:00"), 86400) if C.dow(d) not in (0, 6)]
    relg = releve_replay("rel4_gap", lit, RUN4, synchro={"XAUUSD": 0}, drop_days={"XAUUSD": gap})
    g = check_demo("a9_gap", clean, relg)
    chk("review4 A9 (replay): ten weekdays missing in gold's r1 (synchro_r1=0): 'relancer ReleveFP' (an anomaly) and no replay difference "
        "blamed on the robot", lambda: (g["rc"] == 0 and "relancer ReleveFP" in g["so"] and "r1_XAUUSD" in g["an"] and not g["dif"],
                                        (g["short"], g["an"][:500])))
    # A10: an observer started with D2, restarted with S7
    rk, _, _ = harness_live("live4_risk", HIST4, dict(demo_env, MOCK_INPUT_InpTrade="false", MOCK_INPUT_InpRiskTable=D2), frm=GO4, to=END4,
                            restarts=[(srv("2021-11-03 12:00"), srv("2021-11-03 12:30"), {"MOCK_INPUT_InpRiskTable": S7})])
    g = check_demo("a10_risk", rk, rel100)
    chk("review4 A10: an observer restarted with another risk table: no SIZE difference in the start whose risk table is not the replay's",
        lambda: (g["rc"] == 0 and g["rp"].get("status") == "done" and not g["dif"], (g["short"], len(g["dif"]))))
    # RC3-R3-1a: outages over lines stamped before them and written during them (10,000 EUR trading copy, 1-26 Nov)
    run_late = srv("2021-11-27 10:00")
    rel_late = releve_replay("rel4_late", lit, run_late)
    env_t = {"MOCK_INPUT_InpTrade": "true", "MOCK_INPUT_InpPlanStart": str(srv("2021-11-01 00:00")), "MOCK_BALANCE": "10000"}
    for nm, lines_w in (("night", [f"{srv('2021-11-15 00:30')} disconnect 32400"]),        # Monday 00:30-09:30 server: the reopen inside
                        ("weekend", [f"{srv('2021-11-13 12:00')} disconnect 165600"])):    # Saturday noon to Monday 10:00
        wf = os.path.join(SCRATCH, f"world4_{nm}.txt")
        with open(wf, "w") as fh:
            fh.write("\n".join(lines_w) + "\n")
        jd, _, _ = harness_live("live4_" + nm, HIST4, dict(env_t, MOCK_FAULTS=wf), frm=srv("2021-11-01 00:00"))
        g = check_demo("r31a_" + nm, jd, rel_late)
        chk(f"review4 RC3-R3-1a: an outage ({nm}) over lines stamped before it and written during it (a Friday decision written at the "
            "Sunday reopen, a revision written on Monday): no replay difference, the outage said on stdout",
            lambda: (g["rc"] == 0 and g["rp"].get("status") == "done" and not g["dif"] and "hors ligne" in g["so"], (g["short"], g["so"][-400:])))
    # RC3-R3-1b: a 5-minute drop while a cap-skipped paper trade is open (found in a first run)
    ref, _, _ = harness_live("live4_capref", HIST4, env_t, frm=srv("2021-11-01 00:00"))
    rows, _ = C.read_journal_files(C.journal_paths(ref))
    pf = {(r["code"], r.get("oid")): r for r in rows if r["ev"] == "PFILL" and r.get("rp") != 1}
    px = {(r["code"], r.get("oid")): r for r in rows if r["ev"] in ("PEXIT", "PREVISE") and r.get("rp") != 1}
    cand = None
    for r in rows:
        k = (r["code"], r.get("oid"))
        if r["ev"] == "SIZE" and r.get("rp") != 1 and r.get("skip") == "cap" and k in pf and k in px and px[k]["utc"] - pf[k]["utc"] >= 3 * 3600:
            mid = C.utc_to_srv((pf[k]["utc"] + px[k]["utc"]) // 2)
            if C.dow(mid) not in (0, 6):
                cand = (k, mid)
                break
    if cand:
        wf = os.path.join(SCRATCH, "world4_cap.txt")
        with open(wf, "w") as fh:
            fh.write(f"{cand[1] - cand[1] % 60} disconnect 300\n")
        jd, _, _ = harness_live("live4_capdisc", HIST4, dict(env_t, MOCK_FAULTS=wf), frm=srv("2021-11-01 00:00"))
        g = check_demo("r31b_cap", jd, rel_late)
    chk("review4 RC3-R3-1b (replay): a 5-minute drop while a cap-skipped paper trade is open: no 'MISSED non envoyes' anomaly",
        lambda: (cand is not None and g["rc"] == 0 and "MISSED non envoyes" not in g["an"], (cand, g["an"][:400] if cand else None)))
    print(f"   (review4 replay tests {time.time() - t0:.0f} s)")


# ---------------------------------------------------------------------------------------------- the fourth review, second round
K1T_2026 = "2026:4.1723813245421888e+02"           # INIT k1t as the robot writes back InpK1T = 2026:417.23813245421888 (SPEC 10.14)
MINI_K = {"XAUUSD": 86.0, "US100": 0.86, "BTCUSD": 0.86, "ETHUSD": 0.86}      # EUR per price unit and lot (0.86 EUR per USD)
MINI_H = {"XAUUSD": 0.03, "US100": 0.0, "BTCUSD": 0.0, "ETHUSD": 0.0}          # the gold paper's commission per side (3 points)


def mini_journal(folder, start, end, trades=(), k1t="", balance0=1000.0, extra=None):
    """a small trading journal as JrnAt writes it, one daily file per server date (review4b): a start at server time `start`
    (INIT with the K1 table k1t, SELFTEST, PLAN from the start with B(T) = balance0, REBUILD, READY), the trades, then the AGG,
    COST and DAY lines of every server day the robot ran (the balance books each close: the gross result less the model's
    gold commission, plus extra(server day) EUR) and the stop at `end`. trades: dicts with code, side, at (server seconds),
    hold (seconds), ppx (paper entry), stop, fill (the real fill), quote (the SEND quote), lots, ticket, xpx (paper exit),
    close (the robot's close)"""
    os.makedirs(folder, exist_ok=True)
    L = []

    def add(t_srv, line):
        L.append((int(t_srv), line))
    u0 = C.srv_to_utc(start)
    add(start, init_line(u0, k1t=k1t))
    add(start, jl(u0, "SELFTEST", "-", ("ok", 1), ("why", ""), ("golden", 366)))
    add(start + 60, jl(u0 + 60, "PLAN", "-", ("T", start), ("state", "ok"), ("demo", 1), ("B_T", balance0), ("risk", S7)))
    add(start + 60, jl(u0 + 60, "REBUILD", "-", ("n", 1), ("why", "start"), ("from", u0 - 120 * 86400), ("to", u0 + 60), ("minutes", 172800),
                       ("ms", 700)))
    for b in C.ROBOT_BASES:
        add(start + 62, jl(u0 + 62, "READY", b, ("bars", 100000), ("raw", 100000), ("first", u0 - 120 * 86400), ("last", u0), ("masked", 0),
                           ("holes", 0), ("depth_days", C.DEPTH_DAYS[b])))
    closes = []
    for t in trades:
        code, side, a = t["code"], t["side"], int(t["at"])
        b = C.SYM_OF_CODE[code]
        ua, ux = C.srv_to_utc(a), C.srv_to_utc(a + t["hold"])
        oid = ua * 100 + C.SLEEVE_ID[code]
        h, k = MINI_H[b], MINI_K[b]
        sp = {"XAUUSD": 0.12, "US100": 1.0, "BTCUSD": 25.0, "ETHUSD": 3.0}[b]
        add(a, dec_ord(ua, code, oid, side, 0, t["ppx"], t["stop"], ux))
        add(a, jl(ua, "PFILL", code, ("oid", oid), ("side", side), ("bar", ua), ("px", t["ppx"]), ("stop", t["stop"]), ("st0", t["stop"]),
                  ("x", ux), ("s_raw", 12), ("s_paper", 0.12)))
        add(a, jl(ua, "SIZE", code, ("oid", oid), ("side", side), ("et", 0), ("lots", t["lots"]), ("want", t["lots"]), ("skip", "none"),
                  ("B", balance0), ("P_in", balance0), ("rate", 7.0), ("m", 1.0), ("f", 1.0), ("unit", 70.0), ("w", 0.0), ("r", 10.0),
                  ("budget", 70.0), ("late", 0), ("quote", t["quote"])))
        q = t["quote"]
        add(a + 1, jl(ua + 1, "SEND", code, ("oid", oid), ("side", side), ("lots", t["lots"]), ("want", t["lots"]), ("sl", t["stop"]),
                      ("bid", q - (sp if side > 0 else 0.0)), ("ask", q + (0.0 if side > 0 else sp)), ("stamp", ua), ("dev", 24), ("cut", "-"),
                      ("result", "filled"), ("rc", 10009), ("s_raw", 12), ("s_paper", 0.12)))
        risk = (side * (t["fill"] - t["stop"]) + 2 * h) * k * t["lots"]
        add(a + 1, jl(ua + 1, "FILL", code, ("oid", oid), ("ticket", t["ticket"]), ("side", side), ("px", t["fill"]), ("lots", t["lots"]),
                      ("sl", t["stop"]), ("listed", 1), ("risk", risk), ("budget", 70.0), ("stamp", ua), ("s_raw", 12), ("s_paper", 0.12)))
        add(a + t["hold"], jl(ux, "PEXIT", code, ("oid", oid), ("side", side), ("bar", ux), ("px", t["xpx"]), ("stop", t["stop"]),
                              ("st0", t["stop"]), ("x", ux), ("reason", "time"), ("s_raw", 12), ("s_paper", 0.12)))
        add(a + t["hold"] + 2, jl(ux + 2, "CLOSE", code, ("ticket", t["ticket"]), ("magic", 20261200 + C.SLEEVE_ID[code]), ("px", t["close"]),
                                  ("why", "time"), ("rc", 10009), ("ok", 1)))
        closes.append((a + t["hold"] + 2, side * (t["close"] - t["fill"]) * t["lots"] * k - 2 * h * t["lots"] * k))
    d0 = start - start % 86400
    for pd in range(d0, end - end % 86400, 86400):
        tw = pd + 86400 + 30
        bal = round(balance0 + sum(pl for tc, pl in closes if tc < pd + 86400) + (extra(pd) if extra else 0.0), 2)
        wk = C.dow(pd) in (0, 6)
        uw = C.srv_to_utc(tw)
        add(tw, jl(uw, "AGG", "-", ("day", pd), ("XAUUSD", 0 if wk else 1300), ("US100", 0 if wk else 800), ("BTCUSD", 0 if wk else 1440),
                   ("ETHUSD", 0 if wk else 1440), ("dec", 10), ("pev", 3)))
        if not wk:
            add(tw, jl(uw, "COST", "XAUUSD", ("day", pd), ("raw_bp", 0.2), ("paper_bp", 0.53), ("model_bp", 0.47), ("comm_usd_oz", 0.06),
                       ("comm_n", 2)))
            for b_, m_ in (("US100", 0.37), ("BTCUSD", 2.96), ("ETHUSD", 13.0)):
                add(tw, jl(uw, "COST", b_, ("day", pd), ("raw_bp", m_), ("paper_bp", m_), ("model_bp", m_)))
        add(tw, jl(uw, "DAY", "-", ("day", pd), ("balance", bal), ("equity", bal), ("bars_fed", 5000)))
    add(end, jl(C.srv_to_utc(end), "INIT", "-", ("deinit", 9), ("lines", 300), ("bars_fed", 50000), ("rebuilds", 1)))
    L.sort(key=lambda x: x[0])
    files = {}
    for t, ln in L:
        files.setdefault(time.strftime("%Y%m%d", time.gmtime(t)) + ".log", []).append(ln)
    for name, lines in files.items():
        write(os.path.join(folder, name), "\n".join(lines) + "\n", crlf=True)
    return sorted(files)


A5_SD = {"XAUUSD": 0.5, "US100": 0.6, "BTCUSD": 1.5, "ETHUSD": 2.0}            # bp: the price moves in the seconds between the bar's
A5_N = {"XAUUSD": 8, "US100": 15, "BTCUSD": 17, "ETHUSD": 10}                 # open and the order (review4b R4V-2); trades per market
A5_SLEEVES = {"XAUUSD": ("GFP", "ORX", "D4H"), "US100": ("N30", "OC4"), "BTCUSD": ("BKB", "F1B", "NQB"), "ETHUSD": ("BKE", "F1E")}
A5_PX = {"XAUUSD": 1860.0, "US100": 16300.0, "BTCUSD": 57000.0, "ETHUSD": 4200.0}
A5_LOTS = {"XAUUSD": 0.05, "US100": 1.0, "BTCUSD": 0.05, "ETHUSD": 0.5}


def noisy_trades(seed, start, mult=1.0):
    """trades of a broker whose slippage is mult x the lab's (fp_costs.json), the real order a second or so after the bar's open (the
    paper's price): every entry and every close off the paper by a zero-mean drift of A5_SD bp, the fill against the request's quote at
    exactly mult x the lab's slippage (review4b R4V-2)"""
    rng = random.Random(seed)
    out, tk = [], 70001000
    for b in C.ROBOT_BASES:
        lab = C.SLIP_BPS[b][0]
        h = MINI_H[b]
        for n in range(A5_N[b]):
            code = A5_SLEEVES[b][n % len(A5_SLEEVES[b])]
            day = n // 4
            a = start + day * 86400 + 3600 * (2 + (n % 4) * 3) + 600 * C.ROBOT_BASES.index(b)
            while C.dow(a) in (0, 6):
                a += 86400
            side = 1 if (n + seed) % 3 else -1
            ppx = A5_PX[b] * (1 + 0.001 * n)
            stop = ppx * (1 - side * 0.01)
            d = rng.gauss(0.0, A5_SD[b]) + (mult - 1.0) * lab        # beyond the paper (which books the lab's slippage)
            e = rng.gauss(0.0, A5_SD[b]) + (mult - 1.0) * lab
            fill = ppx + side * (d * 1e-4 * ppx - h)                 # gold: the paper's price holds the commission h
            quote = fill / (1 + side * mult * lab * 1e-4)
            xpx = ppx * (1 + side * 0.002)
            close = xpx - side * (e * 1e-4 * xpx - h)
            out.append({"code": code, "side": side, "at": a, "hold": 3600, "ppx": ppx, "stop": stop, "fill": fill, "quote": quote,
                        "lots": A5_LOTS[b], "ticket": tk, "xpx": xpx, "close": close})
            tk += 1
    return out


def paris_wall(u):
    """the Mac's wall clock (Paris) of a UTC instant, written here apart from the tools (the fixture must not lean on the code it checks):
    European summer time from the last Sunday of March 01:00 UTC to the last Sunday of October 01:00 UTC"""
    y = time.gmtime(u).tm_year

    def last_sunday(m):
        d = calendar.timegm((y, m, 31, 0, 0, 0))                      # March and October have 31 days
        return d - ((time.gmtime(d).tm_wday + 1) % 7) * 86400
    return u + (7200 if last_sunday(3) + 3600 <= u < last_sunday(10) + 3600 else 3600)


def printed_files(folder, jdir, names=None, edit=None):
    """MetaTrader's own Experts logs (MQL5/Logs/<yyyymmdd>.log, UTF-16) of a journal folder, as the Mac writes them (review5 FV4b-1): one file
    per local date of the Mac (Paris: server - 1 h, - 2 h in the weeks when Paris and New York have not both changed clocks), not per server
    day; each live line goes to the day it was written (the clock of the stamped lines before it: a decision stamped at its bar is written
    later), after the Experts tab's prefix with that local time (review4b ADV5-4); edit(name, lines) may change a file's lines. Returns the
    paths"""
    import check_demo as D
    os.makedirs(folder, exist_ok=True)
    by_day, now = {}, None
    for fn in sorted(names or os.listdir(jdir)):
        for ln in lines_of(os.path.join(jdir, fn)):
            m = re.match(r"^CR\|(\d+)\|([A-Z]+)\|", ln)
            if not m or "|rp=1" in ln:
                continue
            u = int(m.group(1))
            if m.group(2) in D.NOW_STAMPED:
                now = u if now is None else max(now, u)
            loc = paris_wall(u if now is None else max(now, u))
            by_day.setdefault(time.strftime("%Y%m%d", time.gmtime(loc)), []).append((loc, ln))
    out = []
    for day, items in sorted(by_day.items()):
        lines = [ln for _, ln in items]
        if edit:
            lines = edit(day + ".log", lines)
        p = os.path.join(folder, day + ".log")
        rows = [f"GH\t0\t{time.strftime('%H:%M:%S', time.gmtime(loc))}.{k % 1000:03d}\tClaudeRobot (XAUUSD.r,M1)\t{ln}"
                for k, (loc, ln) in enumerate(items) if ln in lines]
        with open(p, "wb") as f:
            f.write(b"\xff\xfe" + ("\r\n".join(rows) + "\r\n").encode("utf-16-le"))
        out.append(p)
    return out


def experts_others(path):
    """an Experts log of a day the robot printed nothing: only ReleveFP's and SondeFP's own prints (review4b ADV5-7)"""
    out = ["GH\t0\t11:00:01.104\tReleveFP (EURUSD,M1)\tReleve termine : 9 marches sur 9. Vous pouvez le dire a Claude.",
           "KJ\t0\t11:00:01.105\tReleveFP (EURUSD,M1)\tReleveFP termine", f"QH\t0\t11:00:01.106\tReleveFP (EURUSD,M1)\tserver={FAKE_SERVER}",
           "LO\t0\t11:20:44.310\tSondeFP (EURUSD,M1)\tsonde terminee : 4 marches"]
    with open(path, "wb") as f:
        f.write(b"\xff\xfe" + ("\r\n".join(out) + "\r\n").encode("utf-16-le"))


def test_review4b_journal(lit):
    """the fourth review's second round, journal cases: R4V-1 (a plan start hours after the first start: SIZE observe B = P_in = 0), R4V-2
    (execution costs under timing noise), R4V-3 (a swap credit), R4V-5 (wording), ADV5-1 (a printed other copy whose lines differ), ADV5-3
    (ORPHAN at a reconnection's reconcile), ADV5-4 (printed logs of another run or of purged days), ADV5-5 (InpK1T), ADV5-6 (fini.txt's
    server_time one digit too long), ADV5-7 (an Experts log of a day without robot line), ADV5-8 (ReleveFP interrupted, Max bars), ADV5-10
    (a cut CLOSE), ADV5-11 (the threshold said), ADV5-12 (a bad r1 row), ADV5-13 (a line written after the releve's last bar), ADV5-14 (a
    login glued to a counter)"""
    base_dir = os.path.join(SCRATCH, "rv4bj")

    def go(name, variant=(), extra=(), prep=None, style="live", mini=None):
        jdir = os.path.join(base_dir, "j_" + name, "ClaudeRobot")
        info = mini_journal(jdir, **mini) if mini is not None else md_journal(jdir, variant, style)
        if prep:
            prep(jdir, info)
        out = os.path.join(base_dir, "out_" + name)
        rc, so, se = run_tool("check_demo.py", ["--journals", os.path.dirname(jdir), "--out", out] + list(extra(jdir) if callable(extra) else extra))
        rp = os.path.join(out, "report.json")
        r = json.load(open(rp)) if rc == 0 and os.path.exists(rp) else {}
        rt = os.path.join(out, "report_fr.txt")
        rtxt = open(rt, encoding="utf-8").read() if rc == 0 and os.path.exists(rt) else ""
        return {"rc": rc, "so": so, "se": se, "r": r, "rtxt": rtxt, "info": info, "jdir": jdir, "an": " | ".join(r.get("anomalies", [])),
                "txt": (outputs_text(out) if rc == 0 else "") + so + se, "out": out}
    # R4V-1: InpPlanStart 20 h after the first start (SPEC 1 step 3, accepted by A4): the intent before it is sized observe with B = P_in = 0
    g = go("r4v1_plan_late", ("plan_late",))
    m = (g["r"].get("fills") or {}).get("money_estimate") or {}
    chk("review4b R4V-1: a plan start 20 h after the first start, with an intent sized observe before it (SIZE B = P_in = 0), is no payment "
        "('versement ou retrait') and leaves the money estimate complete",
        lambda: (g["rc"] == 0 and "versement" not in g["an"] and m.get("complete") is True and not m.get("payments"), (g["an"][:500], m.get("incomplete_why"))))
    tline = next((ln for ln in g["so"].splitlines() if ln.startswith("Solde")), "")
    chk("review4b R4V-5 (d): with the plan starting later than the first start, the money line dates B(T) at the plan's start T, not at the "
        "first start", lambda: (g["rc"] == 0 and "B(T)" in tline and "2021-11-18 02:00 UTC" in tline and "2021-11-17 06:00 UTC" not in tline, tline))
    # R4V-2: timing noise around the lab's slippage (the broker slips exactly as the lab) stays in the margin; seeds chosen where the earlier
    # rule (mean > 0.5 x lab and > 2 standard errors above 0) called it beyond
    flagged = []
    for seed in (8, 11, 12, 21, 28):
        g = go(f"r4v2_noise{seed}", mini={"start": srv("2021-11-15 00:00"), "end": srv("2021-11-27 10:00"),
                                          "trades": noisy_trades(seed, srv("2021-11-15 00:00"))})
        if g["rc"] != 0 or "glissement" in g["an"] or "dans la marge" not in g["so"]:
            flagged.append((seed, g["rc"], [a for a in g["r"].get("anomalies", []) if "glissement" in a][:2], g["se"][-200:]))
    chk("review4b R4V-2: entries and closes off the paper by zero-mean timing noise (0.5 to 2 bp a trade) with the broker's slippage at "
        "the lab's: 'dans la marge' on five demos, no 'glissement ... au-dela' (judged against 1.5 x the lab, not against 0)",
        lambda: (not flagged, flagged))
    # R4V-3: a swap credited on a gold short held two weeks (the lab books gold shorts at 0)
    tr = [{"code": "D4H", "side": -1, "at": srv("2021-11-15 10:00"), "hold": 11 * 86400, "ppx": 1860.0, "stop": 1878.6, "fill": 1860.03,
           "quote": 1860.03 / (1 - 0.3e-4), "lots": 0.05, "ticket": 70002001, "xpx": 1850.0, "close": 1849.97}]
    g = go("r4v3_credit", mini={"start": srv("2021-11-15 08:00"), "end": srv("2021-11-27 10:00"), "trades": tr,
                                "extra": lambda pd: 4.0 if pd >= srv("2021-11-26 00:00") else 0.0})
    chk("review4b R4V-3: a 4 EUR swap credit on a 0.05 lot gold short held eleven days (1,000 EUR account) is not 'le solde a bouge pour une "
        "autre raison'", lambda: (g["rc"] == 0 and "le solde a bouge" not in g["an"], g["an"][:400]))
    # ADV5-1: a printed VPS copy whose SIZE and MISSED lines differ from the files' (compared on SPEC 10.12: no traceback, the VPS note)
    base = go("base")
    allv = [ln for fn in sorted(os.listdir(base["jdir"])) for ln in lines_of(os.path.join(base["jdir"], fn)) if "|rp=1" not in ln]
    vps_lines = []
    for ln in allv:
        if "|SIZE|N30|" in ln:
            ln = ln.replace("|f=1.0000000000000000e+00|", "|f=5.0000000000000000e-01|")
        vps_lines.append(ln)
    vps_lines.append(jl(U("2021-11-24 17:05"), "MISSED", "OC4", ("oid", U("2021-11-24 17:00") * 100 + 2), ("stamp", U("2021-11-24 17:00")),
                        ("reason", "observe")))
    pv = os.path.join(base_dir, "experts_vps_diff.log")
    utf16_printed(pv, vps_lines, vps=True)
    g = go("adv51_vps_diff", extra=("--printed", pv))
    chk("review4b ADV5-1: a printed VPS copy whose SIZE and MISSED lines differ from the files' gives a report (no traceback), the differences "
        "on SPEC 10.12's lines and the plain note that VPS copies are not checked yet",
        lambda: (g["rc"] == 0 and "Traceback" not in g["se"] and "VPS" in g["so"] and "pas encore verifi" in g["so"]
                 and len(((g["r"].get("printed") or {}).get("other_copy") or g["r"].get("printed") or {}).get("comparison", {}).get("differences", [])) >= 1,
                 (g["rc"], g["se"][-600:], (g["r"].get("printed") or {}).get("kind"))))
    # ADV5-1 / ADV5-4: the restart day's journal file lost, the Mac's own Experts logs kept (one per day)
    def drop_restart_file(jdir, info):
        os.remove(os.path.join(jdir, "20211122.log"))
    g0 = go("adv51_lost_restart_src", ("restart",))
    logs = printed_files(os.path.join(base_dir, "logs_restart"), g0["jdir"])
    g = go("adv51_lost_restart", ("restart",), prep=drop_restart_file, extra=[x for p in logs for x in ("--printed", p)])
    pr = g["r"].get("printed") or {}
    chk("review4b ADV5-1/ADV5-4: the restart day's journal file lost while the Mac's Experts logs keep it: a report, the logs are the same "
        "copy (not 'autre copie (VPS ?)'), no VPS note",
        lambda: (g["rc"] == 0 and "Traceback" not in g["se"] and pr.get("same_copy_as_files") is True and "VPS" not in g["so"]
                 and "autre copie" not in str(pr.get("kind")), (g["rc"], pr.get("kind"), g["se"][-400:], g["so"][-300:])))
    # ADV5-4: MQL5/Logs also holds an earlier short run of the robot on this Mac (D2, a week before the demo)
    od = os.path.join(base_dir, "logs_old")
    logs = printed_files(od, base["jdir"])
    old = os.path.join(od, "20211110.log")
    a = srv("2021-11-10 09:00")
    utf16_printed(old, [init_line(C.srv_to_utc(a), risk=D2), jl(C.srv_to_utc(a), "SELFTEST", "-", ("ok", 1), ("why", ""), ("golden", 366)),
                        jl(C.srv_to_utc(a) + 60, "REBUILD", "-", ("n", 1), ("why", "start"), ("from", C.srv_to_utc(a) - 120 * 86400),
                           ("to", C.srv_to_utc(a) + 60), ("minutes", 172800), ("ms", 650)),
                        jl(C.srv_to_utc(a) + 7200, "INIT", "-", ("deinit", 1), ("lines", 9), ("bars_fed", 100), ("rebuilds", 1))], extra_other=False)
    g = go("adv54_old_run", extra=[x for p in [old] + logs for x in ("--printed", p)])
    pr = g["r"].get("printed") or {}
    chk("review4b ADV5-4: the Experts logs of an earlier run (before the journal) beside the demo's own: the demo's logs are checked as the "
        "same copy, the earlier run is named apart, no VPS note",
        lambda: (g["rc"] == 0 and pr.get("same_copy_as_files") is True and "VPS" not in g["so"] and "20211110.log" in json.dumps(pr.get("other_period_files", [])),
                 (pr.get("kind"), pr.get("other_period_files"), g["so"][-400:])))
    # ADV5-4: the journal's first days gone (the robot's 30-day purge, or not sent), the Experts logs of every day kept
    def drop_first(jdir, info):
        for f in ("20211117.log", "20211118.log"):
            os.remove(os.path.join(jdir, f))
    logs = printed_files(os.path.join(base_dir, "logs_all"), base["jdir"])
    g = go("adv54_purged", prep=drop_first, extra=[x for p in logs for x in ("--printed", p)])
    pr = g["r"].get("printed") or {}
    chk("review4b ADV5-4: the journal's first two days missing, the Experts logs of every day kept: the logs of the journal's days are the "
        "same copy, the earlier days named apart, no VPS note",
        lambda: (g["rc"] == 0 and pr.get("same_copy_as_files") is True and "VPS" not in g["so"] and "20211117.log" in json.dumps(pr.get("other_period_files", [])),
                 (pr.get("kind"), pr.get("other_period_files"), g["so"][-400:])))
    # ADV5-7: the Experts log of the last day holds only ReleveFP's and SondeFP's prints (the robot printed nothing that day)
    logs = printed_files(os.path.join(base_dir, "logs_last"), base["jdir"])
    last = os.path.join(base_dir, "logs_last", "20211126.log")
    experts_others(last)
    g = go("adv57_last_day", extra=[x for p in logs + [last] for x in ("--printed", p)])
    chk("review4b ADV5-7: an Experts log holding only other programs' prints (ReleveFP, SondeFP) is information, not 'journal du terminal ?'",
        lambda: (g["rc"] == 0 and "20211126.log" not in g["an"] and g["r"]["anomalies"] == [] and leak_free(g["txt"]) == [],
                 (g["an"][:400], leak_free(g["txt"]))))
    # ADV5-3: ORPHAN at a reconnection's reconcile (a position whose paper trade ended during the outage) is normal; elsewhere it is not
    g = go("adv53_orphan", ("outage", "orphan_reconcile"))
    chk("review4b ADV5-3: an ORPHAN at=reconcile just after a reconnection (its paper trade ended during the outage) is no anomaly; it is said "
        "in report_fr.txt", lambda: (g["rc"] == 0 and "ORPHAN" not in g["an"] and "ORPHAN" in g["rtxt"], g["an"][:400]))
    g = go("adv53_orphan_mid", ("orphan_mid",))
    chk("review4b control ADV5-3: an ORPHAN far from any start or reconnection stays an anomaly",
        lambda: (g["rc"] == 0 and "ORPHAN" in g["an"], g["an"][:400]))
    # ADV5-5: InpK1T, one of the two values the user types, on a 2026 demo
    s26, e26 = srv("2026-11-16 08:00"), srv("2026-11-18 10:00")
    g = go("adv55_k1t_empty", mini={"start": s26, "end": e26, "k1t": ""})
    chk("review4b ADV5-5: a 2026 demo started with InpK1T empty (K1 on, no threshold for 2026) is an anomaly naming K1 and the value to type",
        lambda: (g["rc"] == 0 and "K1" in g["an"] and "2026:417.23813245421888" in g["an"], g["an"][:400]))
    g = go("adv55_k1t_wrong", mini={"start": s26, "end": e26, "k1t": "2026:4.0000000000000000e+02"})
    chk("review4b ADV5-5: a 2026 demo started with a mistyped InpK1T (2026:400) is an anomaly", lambda: (g["rc"] == 0 and "InpK1T" in g["an"], g["an"][:400]))
    g = go("adv55_k1t_ok", mini={"start": s26, "end": e26, "k1t": K1T_2026})
    chk("review4b control ADV5-5: a 2026 demo started with InpK1T = 2026:417.23813245421888 has nothing abnormal",
        lambda: (g["rc"] == 0 and g["r"]["anomalies"] == [], g["an"][:400]))
    # ADV5-6: fini.txt's server_time with one digit too many (a year in the 2400s): set aside, no flood of file names
    rdir = os.path.join(base_dir, "rel_st1")
    make_releve(rdir, lit, "good", m1_from="2021-11-15 00:00", m1_to="2021-11-26 00:00")
    p = os.path.join(rdir, "fini.txt")
    write(p, "\n".join(re.sub(r"^server_time=(\d+)", r"server_time=\g<1>0", ln) for ln in lines_of(p)) + "\n")

    def drop_deinit(jdir, info):
        edit_lines(os.path.join(jdir, "20211125.log"), lambda ls_: [ln for ln in ls_ if "|deinit=" not in ln])
    g = go("adv56_st1", prep=drop_deinit, extra=("--bars", rdir, "--no-replay"))
    size = os.path.getsize(os.path.join(g["out"], "report.json")) if g["rc"] == 0 else -1
    chk("review4b ADV5-6: fini.txt's server_time one digit too long is set aside: a small report (no list of file names up to the year 2400s)",
        lambda: (g["rc"] == 0 and 0 < size < 2_000_000 and len(g["so"]) < 20_000 and re.search(r"\b2[1-9]\d\d-\d\d-\d\d", g["so"]) is None, (size, len(g["so"]), g["an"][:300])))
    # ADV5-8: ReleveFP interrupted (no fini.txt), Max bars in chart left at 100000, stopped=1: the cause is named
    rdir = os.path.join(base_dir, "rel_nofini")
    make_releve(rdir, lit, "good", m1_from="2021-11-15 00:00", m1_to="2021-11-26 00:00")
    os.remove(os.path.join(rdir, "fini.txt"))
    g = go("adv58_nofini", extra=("--bars", rdir, "--no-replay"))
    chk("review4b ADV5-8: no fini.txt beside the releve (ReleveFP deletes it at its start and writes it last: interrupted) is an anomaly "
        "asking to run ReleveFP again to its end", lambda: (g["rc"] == 0 and "fini.txt" in g["an"] and "relancer ReleveFP" in g["an"], g["an"][:400]))
    rdir = os.path.join(base_dir, "rel_maxbars")
    make_releve(rdir, lit, "good", m1_from="2021-11-15 00:00", m1_to="2021-11-26 00:00")
    p = os.path.join(rdir, "fini.txt")
    write(p, "\n".join(lines_of(p) + ["max_barres=100000"]).replace("stopped=0", "stopped=1") + "\n")
    g = go("adv58_maxbars", extra=("--bars", rdir, "--no-replay"))
    chk("review4b ADV5-8: fini.txt's max_barres=100000 and stopped=1 are named (Max bars in chart 500000, ReleveFP stopped before its end)",
        lambda: (g["rc"] == 0 and "500000" in g["an"] and "stopped" in g["an"], g["an"][:500]))
    # ADV5-10: the last line of a file cut while the robot wrote it, here the N30 CLOSE: the exit is unknown, the robot is not blamed
    def cut_close(jdir, info):
        p = os.path.join(jdir, "20211124.log")
        raw = open(p, "rb").read()
        assert b"|CLOSE|N30|" in raw.splitlines()[-1]
        open(p, "wb").write(raw[:-37])
    g = go("adv510_cut_close", prep=cut_close)
    chk("review4b ADV5-10: a CLOSE cut at the end of its file is the unreadable line (one anomaly), not 'position non fermee par le robot'",
        lambda: (g["rc"] == 0 and "illisible" in g["an"] and "non fermee" not in g["an"] and "sans ligne CLOSE" not in g["an"], g["an"][:500]))
    # ADV5-11: the size of a balance move the money check can see is said
    chk("review4b ADV5-11: report_fr.txt says how large a move of the balance from outside the robot must be to be seen",
        lambda: (base["rc"] == 0 and "ne se voit pas" in base["rtxt"], [ln for ln in base["rtxt"].splitlines() if "solde" in ln.lower()][:3]))
    # ADV5-12: an r1 row with a negative price is not a bar
    rdir = os.path.join(base_dir, "rel_neg")
    make_releve(rdir, lit, "good", m1_from="2021-11-15 00:00", m1_to="2021-11-26 00:00")
    p = os.path.join(rdir, "r1_XAUUSD.csv")
    ls = lines_of(p)
    f = ls[5].split(",")
    f[3] = "-" + f[3]
    ls[5] = ",".join(f)
    write(p, "\n".join(ls) + "\n")
    g = go("adv512_neg", extra=("--bars", rdir, "--no-replay"))
    chk("review4b ADV5-12: an r1 row with a negative low is dropped and counted (an anomaly naming r1_XAUUSD.csv), never fed to the replay",
        lambda: (g["rc"] == 0 and "r1_XAUUSD.csv : 1 ligne(s) illisible(s)" in g["an"], g["an"][:400]))
    # ADV5-13: a time exit written after the releve's last bar (crypto at weekends) is out of the replay's span
    import check_demo as D
    t0_, t1_ = srv("2021-11-01 00:00"), srv("2021-11-27 09:00")
    w = D.Windows([], {"BKB": (t0_, t1_)}, None)
    chk("review4b ADV5-13: a PREVISE stamped at Friday's last kept bar whose time exit comes after the releve's last bar is out of the span",
        lambda: (w.why_out("BKB", t1_ - 40000, t1_ - 40000, "PREVISE", t_end=t1_ + 60) is not None
                 and w.why_out("BKB", t1_ - 40000, t1_ - 40000, "PREVISE", t_end=t1_ - 39000) is None, None))
    # ADV5-14: a login glued onto a counter (COST comm_n) makes the line unreadable: the number never reaches an output
    def glue_comm(jdir, info):
        edit_lines(os.path.join(jdir, "20211119.log"), lambda ls_: [ln.replace("|comm_n=2", "|comm_n=2" + FAKE_LOGIN, 1) if "|COST|XAUUSD|" in ln else ln
                                                                   for ln in ls_])
    g = go("adv514_glue", prep=glue_comm)
    chk("review4b ADV5-14: a login glued onto COST comm_n makes the line unreadable; the login never reaches report.json, report_fr.txt or stdout",
        lambda: (g["rc"] == 0 and FAKE_LOGIN not in g["txt"] and "illisible" in g["an"], [w_ for w_ in (FAKE_LOGIN,) if w_ in g["txt"]]))


def test_review4b_tool1(lit):
    """the fourth review's second round on read_mac_files.py: R4V-5 (c) (server_time set aside is not 'fini.txt absent'), ADV5-8 (fini.txt
    absent), ADV5-9 (fiches.csv absent), ADV5-12 (an r1 row with a negative price)"""
    base_dir = os.path.join(SCRATCH, "rv4bt1")

    def go(name, prep=None, **kw):
        folder = os.path.join(base_dir, "in_" + name)
        out = os.path.join(base_dir, "out_" + name)
        make_releve(folder, lit, "good", **kw)
        if prep:
            prep(folder)
        rc, so, se = run_tool("read_mac_files.py", [folder, "--out", out])
        s = json.load(open(os.path.join(out, "summary.json"))) if rc == 0 else {"checks": [], "problems": []}
        return {"rc": rc, "so": so, "se": se, "ck": {(c["market"], c["item"]): c for c in s["checks"]}, "s": s}

    def fini_edit(folder, fn):
        p = os.path.join(folder, "fini.txt")
        write(p, "\n".join(fn(lines_of(p))) + "\n")
    g = go("r4v5c_st", prep=lambda f: fini_edit(f, lambda ls: [re.sub(r"^server_time=(\d+)", r"server_time=\g<1>000000", ln) for ln in ls]))
    sc = g["ck"].get(("compte", "server_clock"), {})
    chk("review4b R4V-5 (c) (tool 1): fini.txt present with its server_time set aside: the server clock says the value is unreadable, not "
        "'fini.txt absent'", lambda: (g["rc"] == 0 and "fini.txt absent" not in str(sc.get("broker")) and "server_time" in str(sc.get("broker")), sc))
    g = go("adv58_nofini", prep=lambda f: os.remove(os.path.join(f, "fini.txt")))
    chk("review4b ADV5-8 (tool 1): fini.txt absent beside ReleveFP's other files is DIFFERENT (ReleveFP interrupted: run it again to its end)",
        lambda: (g["rc"] == 0 and any(c["status"] == "DIFFERENT" and "fini.txt" in str(c.get("broker")) + str(c.get("note")) for c in g["s"]["checks"]),
                 [c for c in g["s"]["checks"] if c["market"] == "compte"][:6]))
    g = go("adv59_nofiches", prep=lambda f: os.remove(os.path.join(f, "fiches.csv")))
    xau = [c for c in g["s"]["checks"] if c["market"] == "XAUUSD"]
    chk("review4b ADV5-9 (tool 1): fiches.csv absent is DIFFERENT, and the robot markets' fiche items (digits, tick size, minimum lot ...) are "
        "listed as UNKNOWN instead of dropped",
        lambda: (g["rc"] == 0 and any(c["status"] == "DIFFERENT" and "fiches.csv" in str(c.get("broker")) + str(c.get("note")) for c in g["s"]["checks"])
                 and any(c["item"] == "digits" and c["status"] == "UNKNOWN" for c in xau) and any(c["item"] == "vol_min" for c in xau),
                 [(c["item"], c["status"]) for c in xau]))

    def neg_row(folder):
        p = os.path.join(folder, "r1_XAUUSD.csv")
        ls = lines_of(p)
        f = ls[5].split(",")
        f[3] = "-" + f[3]
        ls[5] = ",".join(f)
        write(p, "\n".join(ls) + "\n")
    g = go("adv512_neg", prep=neg_row)
    chk("review4b ADV5-12 (tool 1): an r1 row with a negative low is dropped and counted (r1_rows DIFFERENT 'ligne(s) illisible(s)')",
        lambda: (g["rc"] == 0 and g["ck"].get(("XAUUSD", "r1_rows"), {}).get("status") == "DIFFERENT"
                 and "illisible" in g["ck"].get(("XAUUSD", "r1_rows"), {}).get("note", ""), g["ck"].get(("XAUUSD", "r1_rows"))))


SLEEP_NIGHT = (srv("2021-11-02 23:40"), srv("2021-11-03 07:10"))     # Tuesday night: the terminal's bars of the sleep 90 s after the wake
SLEEP_WEEKEND = (srv("2021-11-05 22:30"), srv("2021-11-08 08:15"))   # Friday night to Monday morning: the bars there at the wake


def test_review4b_replay(lit):
    """the fourth review's second round with the replay: ADV5-2 (the Mac asleep: the process frozen, then a catch-up at the wake; built
    against the self-test's own copy of the harness with MOCK_SLEEP), R4V-5 (a) and (b) on the clean demo of review4"""
    t0 = time.time()

    def check_demo(name, jfiles, bars=None, extra=()):
        out = os.path.join(SCRATCH, "out4b_" + name)
        rc, so, se = run_tool("check_demo.py", ["--journals", jfiles, "--out", out] + (["--bars", bars] if bars else []) + list(extra))
        r = json.load(open(os.path.join(out, "report.json"))) if rc == 0 else {}
        rp = r.get("replay", {})
        dif = rp.get("comparison", {}).get("differences", [])
        rt = os.path.join(out, "report_fr.txt")
        return {"rc": rc, "so": so, "se": se, "r": r, "rp": rp, "dif": dif, "an": " | ".join(r.get("anomalies", [])),
                "rtxt": open(rt, encoding="utf-8").read() if rc == 0 and os.path.exists(rt) else "",
                "short": [(d["kind"], d["event"], d["code"], d["when"], d.get("fields")) for d in dif[:4]]}
    exe, err = None, None
    try:
        exe = sleep_harness_exe(os.path.join(SCRATCH, "harness_sleep"))
    except Exception as e:                                              # noqa: BLE001
        err = f"{e.__class__.__name__}: {str(e)[-300:]}"
    check("review4b ADV5-2: the self-test's copy of the harness with MOCK_SLEEP builds (check/ itself unchanged)", exe is not None, err)
    rel = releve_replay("rel4b_sleep", lit, RUN4)
    g = gj = None
    if exe:
        env = {"MOCK_INPUT_InpTrade": "true", "MOCK_INPUT_InpPlanStart": str(GO4), "MOCK_BALANCE": "1000",
               "MOCK_SLEEP": f"{SLEEP_NIGHT[0]}-{SLEEP_NIGHT[1]},{SLEEP_WEEKEND[0]}-{SLEEP_WEEKEND[1]}"}
        for b in C.ROBOT_BASES:
            env[f"MOCK_HOLE_{b}.r"] = f"{SLEEP_NIGHT[0]}-{SLEEP_NIGHT[1]}@{SLEEP_NIGHT[1] + 90}"
        jd, _, _ = harness_live("live4b_sleep", HIST4, env, frm=GO4, to=END4, exe=exe)
        g = check_demo("sleep", jd, rel)
        gj = check_demo("sleep_nobars", jd)
    chk("review4b ADV5-2: the Mac asleep one night (the bars of the sleep after the wake: REBUILD why=latebar) and over a weekend (no "
        "rebuild): no replay difference, no 'MISSED non envoyes', no AGG or COST anomaly",
        lambda: (g is not None and g["rc"] == 0 and g["rp"].get("status") == "done" and not g["dif"] and "MISSED non envoyes" not in g["an"]
                 and "nombre de barres different" not in g["an"] and "COST" not in g["an"], (g and g["short"], g and g["an"][:600], g and g["se"][-300:])))
    chk("review4b ADV5-2: both sleeps are said plainly on stdout: the robot offline (Mac asleep or MetaTrader frozen ?) and for how long at most",
        lambda: (g is not None and g["rc"] == 0 and "hors ligne" in g["so"] and "veille" in g["so"]
                 and len([o for o in g["r"]["journal"].get("outages", []) if o.get("why") == "sleep"]) == 2,
                 (g and [ln for ln in g["so"].splitlines() if "ligne" in ln.lower()][:4], g and g["r"]["journal"].get("outages"))))
    chk("review4b ADV5-2: the early check without the releve (journal only) says the sleeps too and raises no 'MISSED non envoyes'",
        lambda: (gj is not None and gj["rc"] == 0 and "hors ligne" in gj["so"] and "MISSED non envoyes" not in gj["an"], (gj and gj["so"][-500:])))
    # R4V-5 (a), (b): the clean review4 demo with ReleveFP's default files
    clean = os.path.join(SCRATCH, "live4_clean", "files")
    rel100 = os.path.join(SCRATCH, "rel4_100")
    if not os.path.isdir(clean):
        clean, _, _ = harness_live("live4_clean", HIST4, {"MOCK_INPUT_InpTrade": "true", "MOCK_INPUT_InpPlanStart": str(GO4),
                                                          "MOCK_BALANCE": "1000"}, frm=GO4, to=END4)
    if not os.path.isdir(rel100):
        rel100 = releve_replay("rel4_100", lit, RUN4)
    g = check_demo("clean", clean, rel100)
    chk("review4b R4V-5 (a): r1 files of ReleveFP's default days (200 for gold, 100 for the others) give no note 'plus tard que les autres "
        "marches' (the shorter span is by design)", lambda: (g["rc"] == 0 and "plus tard que les autres" not in g["rtxt"],
                                                              [ln for ln in g["rtxt"].splitlines() if "plus tard" in ln][:3]))
    exc = g["rp"].get("comparison", {}).get("excluded", {})
    chk("review4b R4V-5 (b): lines from before the robot's live start are counted 'robot pas en marche', never 'rejeu pas encore pret'",
        lambda: (g["rc"] == 0 and not any("pas encore pret" in k for k in exc), exc))
    print(f"   (review4b replay tests {time.time() - t0:.0f} s)")


# ---------------------------------------------------------------------------------------------- review5: the start's paste (check_start.py)
START_U = C.srv_to_utc(srv("2026-11-15 11:02"))           # the user's start: Sunday 15 November 2026, 10:02 in Paris, 11:02 on the server


def start_lines(u=START_U, ready=C.ROBOT_BASES, **kw):
    """a start as the release robot writes it (OnInit: INIT, SELFTEST; MainWait: PLAN src=first_deal, then PLAN; MainRebuild: REBUILD;
    CBarStore::Check: READY), with the user's settings unless kw changes the INIT line (init_line's arguments)"""
    kw.setdefault("k1t", K1T_2026)
    risk = kw.get("risk", S7)
    t0 = u - 3 * 86400
    out = [init_line(u, **kw), jl(u, "SELFTEST", "-", ("ok", 1), ("why", ""), ("golden", 366)),
           jl(u + 4, "PLAN", "-", ("src", "first_deal"), ("T", C.utc_to_srv(t0))),
           jl(u + 4, "PLAN", "-", ("T", C.utc_to_srv(t0)), ("state", "ok"), ("demo", kw.get("demo", 1)), ("B_T", 10000.0), ("risk", risk)),
           jl(u + 6, "REBUILD", "-", ("n", 1), ("why", "start"), ("from", u - 200 * 86400), ("to", u + 6), ("minutes", 288000), ("ms", 4210))]
    for b in ready:
        out.append(jl(u + 40, "READY", b, ("bars", 180000), ("raw", 180000), ("first", u - 200 * 86400), ("last", u), ("masked", 0), ("holes", 0),
                      ("depth_days", C.DEPTH_DAYS[b])))
    return out


def stop_line(u, reason):
    return jl(u, "INIT", "-", ("deinit", reason), ("lines", 12), ("bars_fed", 0), ("rebuilds", 1), ("masked_XAUUSD", 0), ("masked_US100", 0),
              ("masked_BTCUSD", 0), ("masked_ETHUSD", 0))


def experts_paste(lines, style="copy", account=True):
    """lines as the Experts tab copies them (right-click -> Copy): the time and the source before 'CR|' ('copy'), a line of MetaTrader's
    own log file ('log': code, severity, time, source), or the columns turned into spaces by the chat ('spaces'); account=True plants the
    account in the paste the way a careless copy would bring it (a Journal-tab line with the login and the server, the holder's name and
    the user folder before a robot line)"""
    out = []
    if account:
        out.append(f"QK\t0\t10:01:58.120\tNetwork\t'{FAKE_LOGIN}': authorized on {FAKE_SERVER} through Access Point EU 2")
        out.append(f"MN\t0\t10:01:57.002\tTerminal\tFP Markets MT5 Terminal started for FP Markets ({FAKE_NAME})")
    for k, ln in enumerate(lines):
        t = f"10:02:{10 + k % 49:02d}.{(37 * k) % 1000:03d}"
        if style == "log":
            out.append(f"GH\t0\t{t}\tClaudeRobot (XAUUSD.r,M1)\t{ln}")
        elif style == "spaces":
            out.append(f"2026.11.15 {t}    ClaudeRobot (XAUUSD.r,M1)    {ln}")
        else:
            src = f"ClaudeRobot (XAUUSD.r,M1) C:\\users\\{FAKE_USER}\\AppData {FAKE_LOGIN}" if (account and k == 0) else "ClaudeRobot (XAUUSD.r,M1)"
            out.append(f"2026.11.15 {t}\t{src}\t{ln}")
    return "\n".join(out) + "\n"


def test_review5_start(lit):
    """review5 START: check_start.py on the lines the user pastes into the chat right after the start (the Experts tab copied with right-click
    -> Copy), built with this file's journal lines (JrnAt's format) wrapped the way the tab copies them, account values planted in the paste.
    check_start.py does not exist before review5: these tests fail there by construction"""
    del lit
    base_dir = os.path.join(SCRATCH, "rv5s")
    os.makedirs(base_dir, exist_ok=True)

    def go(name, content):
        p = os.path.join(base_dir, name + ".txt")
        with open(p, "wb") as f:
            f.write(content if isinstance(content, bytes) else content.encode("utf-8"))
        rc, so, se = run_tool("check_start.py", [p])
        ok_lines = [ln for ln in so.splitlines() if ln.startswith("OK : ")]
        diff = [ln for ln in so.splitlines() if ln.startswith("DIFFERENT : ")]
        return {"rc": rc, "so": so, "se": se, "ok": ok_lines, "diff": diff, "leak": leak_free(so + se),
                "verdict": next((ln for ln in so.splitlines() if ln.startswith("Verdict")), "")}
    g = go("right", experts_paste(start_lines()))
    chk("review5 START: the user's right settings (S7, InpK1T 2026, .r names, demo, build fd6aaf01e332) pasted from the Experts tab with "
        "a Journal line and account values around them: every check OK, exit code 0, nothing of the account printed",
        lambda: (g["rc"] == 0 and not g["diff"] and len(g["ok"]) >= 14 and "conforme" in g["verdict"] and not g["leak"]
                 and "READY ETHUSD" in g["so"] and "417.23813245421888" in g["so"] and "Traceback" not in g["se"], (g["rc"], g["so"][-1500:], g["se"][-500:], g["leak"])))
    g = go("init_only", experts_paste(start_lines()[:1], account=False))
    chk("review5 START: the INIT line alone (what the guide asks for): OK, the lines written later said 'PAS ENCORE' or 'ABSENT', exit code 0",
        lambda: (g["rc"] == 0 and not g["diff"] and "PAS ENCORE : READY XAUUSD" in g["so"] and "ABSENT : SELFTEST" in g["so"]
                 and "PAS ENCORE : PLAN" in g["so"], g["so"][-1200:]))
    g = go("d2", experts_paste(start_lines(risk=D2)))
    chk("review5 START: InpRiskTable left at the default (D2): DIFFERENT naming D2, InpRiskTable and the S7 table to type, exit code 1",
        lambda: (g["rc"] == 1 and any("D2" in x and "InpRiskTable" in x and S7 in x for x in g["diff"]), g["diff"]))
    comma = [jl(START_U, "ERROR", "-", ("what", "InpRiskTable: '3000:3,5' is not a pair from:pct of plain numbers")), stop_line(START_U, 8)]
    g = go("comma", experts_paste(comma))
    chk("review5 START: a comma typed in the risk table (the robot refuses it: ERROR, no INIT, stop line deinit=8): the ERROR named as a typo "
        "in InpRiskTable (a comma), INIT absent, the typed value never printed, exit code 1",
        lambda: (g["rc"] == 1 and any("InpRiskTable" in x and "virgule" in x for x in g["diff"]) and "ABSENT : INIT" in g["so"]
                 and "3000:3,5" not in g["so"] and "arret" in g["so"], g["so"][-1200:]))
    g = go("k1t_empty", experts_paste(start_lines(k1t="")))
    chk("review5 START: InpK1T left empty (K1 on, no threshold for 2026): DIFFERENT naming InpK1T and 2026:417.23813245421888, exit code 1",
        lambda: (g["rc"] == 1 and any("InpK1T" in x and "2026:417.23813245421888" in x for x in g["diff"]), g["diff"]))
    g = go("k1t_417", experts_paste(start_lines(k1t="2026:4.1700000000000000e+02")))
    chk("review5 START: InpK1T typed 2026:417 (the robot writes back 4.1700000000000000e+02): DIFFERENT, a typo, exit code 1",
        lambda: (g["rc"] == 1 and any("InpK1T" in x and "417" in x and "faute de frappe" in x for x in g["diff"]), g["diff"]))
    g = go("k1t_e002", experts_paste(start_lines(k1t="2026:4.1723813245421888e+002"), "log"))
    chk("review5 START control: k1t with a three-digit exponent (2026:4.1723813245421888e+002, as MetaTrader under Windows may print it) "
        "and the log file's prefix: OK, exit code 0", lambda: (g["rc"] == 0 and not g["diff"], g["so"][-800:]))
    g = go("no_r", experts_paste(start_lines(syms={"XAUUSD": "XAUUSD"}), "spaces"))
    chk("review5 START: the robot took XAUUSD instead of XAUUSD.r (columns turned into spaces by the chat): DIFFERENT naming both names, exit 1",
        lambda: (g["rc"] == 1 and any("XAUUSD.r" in x and "pris XAUUSD " in x for x in g["diff"]), g["diff"]))
    g = go("demo0", experts_paste(start_lines(demo=0, observer=1, sw=("off", "off", "off"))))
    chk("review5 START: a real account (demo=0): DIFFERENT 'compte reel' (remove the robot), exit code 1",
        lambda: (g["rc"] == 1 and any("compte reel" in x for x in g["diff"]), g["diff"]))
    old = next((b["build"] for b in C.known_builds() if b["kind"] == "release" and b["build"] != C.REQUIRED_BUILD), "1cf1d0cab64b")
    g = go("old", experts_paste(start_lines(build=old)))
    chk("review5 START: an older build of dist/'s history: DIFFERENT naming the build and the right file, exit code 1",
        lambda: (g["rc"] == 1 and any(old in x and C.REQUIRED_BUILD in x for x in g["diff"]), (old, g["diff"])))
    g = go("stop_only", experts_paste([stop_line(START_U, 1)]))
    chk("review5 START: the robot's stop line only (INIT deinit=): named as the stop line, INIT absent, no setting said OK, exit code 1",
        lambda: (g["rc"] == 1 and "ligne d'arret" in g["so"] and "ABSENT : INIT" in g["so"] and not g["ok"], g["so"][-800:]))
    errs = [jl(START_U, "ERROR", "BKE", ("what", "InpK1T refused: '2026:417,23813245421888': T must be a number of bp (e.g. 465.1178140105435)")),
            jl(START_U, "ERROR", "-", ("what", "rule BKE: Init refused its configuration"))]
    g = go("errors_only", experts_paste(errs))
    chk("review5 START: the two ERROR lines of an InpK1T typo only: one DIFFERENT saying a typo in InpK1T (the second line, same cause, as "
        "information), INIT absent, exit code 1",
        lambda: (g["rc"] == 1 and len(g["diff"]) == 1 and "InpK1T" in g["diff"][0] and "faute de frappe" in g["diff"][0]
                 and "ABSENT : INIT" in g["so"] and "417,23" not in g["so"], g["so"][-1000:]))
    two = start_lines(START_U - 900, risk=D2, ready=())[:2] + [stop_line(START_U - 60, 5)] + start_lines()
    g = go("two_starts", experts_paste(two))
    chk("review5 START: two starts in one paste (D2 first, stopped by the change of parameters, then S7): the last one decides (OK, exit 0), "
        "the first is named with its D2",
        lambda: (g["rc"] == 0 and not g["diff"] and any(ln.startswith("INFO : demarrage 1") and "D2" in ln for ln in g["so"].splitlines()),
                 g["so"][-1500:]))
    full = start_lines()
    g = go("cut", experts_paste([full[0][:170]] + full[1:2], account=False))
    chk("review5 START: an INIT line cut in the middle: 'ligne coupee : demander de la recopier', no setting checked from it, exit code 1",
        lambda: (g["rc"] == 1 and any("ligne coupee : demander de la recopier" in x and "INIT" in x for x in g["diff"])
                 and "OK : build" not in g["so"], g["so"][-800:]))
    wr = full[0]
    g = go("wrapped", f"2026.11.15 10:02:10.123\tClaudeRobot (XAUUSD.r,M1)\t{wr[:140]}\n{wr[140:250]}\n{wr[250:]}\n")
    chk("review5 START: an INIT line the chat wrapped onto three lines is put back together (said as information) and checked: OK, exit 0",
        lambda: (g["rc"] == 0 and "recollee" in g["so"] and any("seuil K1" in x for x in g["ok"]), g["so"][-800:]))
    u16 = experts_paste(full, "log").replace("\n", "\r\n")
    g = go("utf16", b"\xff\xfe" + u16.encode("utf-16-le"))
    chk("review5 START: the paste saved as UTF-16 (byte-order mark, CRLF, MetaTrader's log prefix): read, OK, exit code 0, nothing of the "
        "account printed", lambda: (g["rc"] == 0 and not g["diff"] and len(g["ok"]) >= 14 and not g["leak"], (g["so"][-800:], g["leak"])))
    g = go("quotes_bom", b"\xef\xbb\xbf" + ('```\n"' + full[0] + '"\r\n```\r\n').encode("utf-8"))
    chk("review5 START control: a UTF-8 byte-order mark, a code fence and quotes around the line: OK, exit code 0",
        lambda: (g["rc"] == 0 and not g["diff"], g["so"][-600:]))
    g = go("risk_spaces", experts_paste(start_lines(risk=" " + S7 + " ")))
    chk("review5 START: InpRiskTable typed with a space before and after (the robot trims them, MainInitLine writes them back): the line is "
        "read and the table is S7, exit code 0", lambda: (g["rc"] == 0 and not g["diff"], g["so"][-800:]))
    clock = [jl(START_U, "CLOCK", "-", ("state", "wrong"), ("measured_s", 3600), ("rule_s", 7200))] + full
    g = go("clock", experts_paste(clock))
    chk("review5 START: CLOCK state=wrong written by OnInit (no CLOCK state=ok after it): DIFFERENT with the Mac's clock to fix, exit code 1",
        lambda: (g["rc"] == 1 and any("CLOCK" in x and "heure du Mac" in x for x in g["diff"]), g["diff"]))
    g = go("clock_ok", experts_paste(clock + [jl(START_U + 300, "CLOCK", "-", ("state", "ok"), ("measured_s", 7200), ("rule_s", 7200))]))
    chk("review5 START control: CLOCK state=wrong followed by CLOCK state=ok: information only, exit code 0",
        lambda: (g["rc"] == 0 and not g["diff"] and "CLOCK" in g["so"], g["so"][-800:]))
    st0 = [full[0], jl(START_U, "SELFTEST", "-", ("ok", 0), ("why", "golden"), ("golden", 366))]
    g = go("selftest0", experts_paste(st0))
    chk("review5 START: SELFTEST ok=0: DIFFERENT (the robot will not trade), exit code 1",
        lambda: (g["rc"] == 1 and any("SELFTEST ok=0" in x for x in g["diff"]), g["diff"]))
    g = go("observer", experts_paste(start_lines(observer=1)))
    chk("review5 START: an observer copy on the demo (InpTrade false): DIFFERENT naming InpTrade, exit code 1",
        lambda: (g["rc"] == 1 and any("InpTrade" in x for x in g["diff"]), g["diff"]))
    nr = start_lines(ready=("XAUUSD", "BTCUSD")) + [jl(START_U + 40, "NOTREADY", "US100", ("why", "sync"), ("bars", 100), ("raw", 100),
                                                     ("first", START_U - 9 * 86400), ("last", START_U), ("masked", 0), ("holes", 0))]
    g = go("not_ready_yet", experts_paste(nr + [jl(START_U + 50, "MISSED", "BKB", ("oid", (START_U - 600) * 100 + 3), ("stamp", START_U - 600),
                                                  ("reason", "late"))]))
    chk("review5 START control: two markets not READY yet (one NOTREADY sync) and a MISSED late at the start: 'PAS ENCORE' and information, "
        "never an error, exit code 0",
        lambda: (g["rc"] == 0 and "PAS ENCORE : READY US100" in g["so"] and "PAS ENCORE : READY ETHUSD" in g["so"] and "MISSED" in g["so"]
                 and not g["diff"], g["so"][-1000:]))
    # check_start and check_demo agree on the same start (start_settings, shared)
    agree, seen = [], []
    for name, kw in (("right", {}), ("d2", {"risk": D2}), ("k1t_empty", {"k1t": ""}), ("k1t_417", {"k1t": "2026:4.1700000000000000e+02"}),
                     ("no_r", {"syms": {"US100": "US100"}}), ("sleeves", {"sleeves": "GFP"}), ("k1_off", {"sw": ("off", "on", "on")}),
                     ("old", {"build": old})):
        ls_ = start_lines(**kw) + [stop_line(START_U + 3600, 1)]
        jd = os.path.join(base_dir, "agree_" + name, "ClaudeRobot")
        os.makedirs(jd, exist_ok=True)
        write(os.path.join(jd, time.strftime("%Y%m%d", time.gmtime(C.utc_to_srv(START_U))) + ".log"), "\n".join(ls_) + "\n")
        out = os.path.join(base_dir, "agree_out_" + name)
        rc, so, se = run_tool("check_demo.py", ["--journals", os.path.dirname(jd), "--out", out])
        an = json.load(open(os.path.join(out, "report.json")))["anomalies"] if rc == 0 else ["(check_demo failed)"]
        gs = go("agree_" + name, experts_paste(ls_[:-1]))
        seen.append((name, bool(an), gs["rc"]))
        if bool(an) != (gs["rc"] == 1):
            agree.append((name, an[:2], gs["diff"][:2]))
    chk("review5 START: check_start and check_demo agree on the same start lines (right settings, D2, InpK1T empty or 2026:417, no .r name, "
        "InpSleeves, K1 off, an older build): both flag it or neither", lambda: (not agree and len(seen) == 8, (agree, seen)))


def apple_double():
    """an AppleDouble file as macOS writes it beside a file (magic 0x00051607, version 2, 'Mac OS X', an extended-attributes block)"""
    return (b"\x00\x05\x16\x07\x00\x02\x00\x00Mac OS X        \x00\x02\x00\x00\x00\x09\x00\x00\x00\x32\x00\x00\x0e\xb0\x00\x00\x00\x02"
            b"\x00\x00\x0e\xe2\x00\x00\x01\x1e" + b"\x00" * 32 + b"ATTR\x00\x00\x00\x00com.apple.quarantine\x000083;6553f1a2;Safari;"
            + b"\x00" * 80)


def finder_zip_tree(root, files, macosx=True, beside=False):
    """a tree laid out exactly like a Finder zip ('Compresser') extracted elsewhere: the user's files as they are, then for each of them
    an AppleDouble '._<name>' under __MACOSX/<same folders>/ (macosx), or beside it (beside: a copy made by tar or onto a FAT key), and
    the folders' own '._<folder>' entries. files: {relative path: source path}. Returns the AppleDouble paths written"""
    out = []
    for rel, src in files.items():
        dst = os.path.join(root, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy(src, dst)
        d, n = os.path.split(rel)
        for where in ([os.path.join(root, "__MACOSX", d)] if macosx else []) + ([os.path.join(root, d)] if beside else []):
            os.makedirs(where, exist_ok=True)
            p = os.path.join(where, "._" + n)
            with open(p, "wb") as f:
                f.write(apple_double())
            out.append(p)
    if macosx:
        for top in {rel.split("/")[0] for rel in files if "/" in rel}:
            with open(os.path.join(root, "__MACOSX", "._" + top), "wb") as f:
                f.write(apple_double())
    with open(os.path.join(root, ".DS_Store"), "wb") as f:
        f.write(b"\x00\x00\x00\x01Bud1" + b"\x00" * 60)
    return out


def start_go(base_dir, name, content):
    """check_start.py on one paste saved as text: rc, stdout, the OK and DIFFERENT lines, the verdict, the account words found"""
    p = os.path.join(base_dir, name + ".txt")
    with open(p, "wb") as f:
        f.write(content if isinstance(content, bytes) else content.encode("utf-8"))
    rc, so, se = run_tool("check_start.py", [p])
    return {"rc": rc, "so": so, "se": se, "ok": [ln for ln in so.splitlines() if ln.startswith("OK : ")],
            "diff": [ln for ln in so.splitlines() if ln.startswith("DIFFERENT : ")], "leak": leak_free(so + se),
            "verdict": next((ln for ln in so.splitlines() if ln.startswith("Verdict")), "")}


def test_review5b_start(lit):
    """review5b (the fifth round's second pass), check_start.py: START-TRAILING-WORD (one chat word after the INIT line was glued onto ETHUSD.r),
    START-GLUED-PREFIX (robot lines glued on one line with the Experts tab's prefix between them), RH5-5 (a refused last start: the robot left the
    chart, F7 cannot reach it: relaunch with the two values)"""
    del lit
    base_dir = os.path.join(SCRATCH, "rv5bs")
    os.makedirs(base_dir, exist_ok=True)
    full = start_lines()
    init = full[0]
    bad = []
    for word in ("merci", "OK", "9h30", "Voila"):
        for style in ("copy", "bare"):
            text = (experts_paste([init], account=False) if style == "copy" else init + "\n") + word + "\n"
            g = start_go(base_dir, f"trail_{word}_{style}", text)
            if g["rc"] != 0 or g["diff"] or "recollee" in g["so"] or "OK : marches XAUUSD.r, US100.r, BTCUSD.r, ETHUSD.r" not in g["so"]:
                bad.append((word, style, g["rc"], g["diff"][:1]))
    chk("review5b START-TRAILING-WORD: the right INIT line followed by one chat word ('merci', 'OK', '9h30', 'Voila'), with or without the "
        "Experts prefix: the word is never glued onto ETHUSD.r, every check OK, exit code 0", lambda: (not bad, bad))
    g = start_go(base_dir, "trail_after_all", experts_paste(full, account=False) + "merci\n")
    chk("review5b control START-TRAILING-WORD: a word after the whole start (READY's last field is a number): OK, exit code 0",
        lambda: (g["rc"] == 0 and not g["diff"], g["so"][-600:]))
    g = start_go(base_dir, "glued_login", experts_paste([init + FAKE_LOGIN], account=False))
    chk("review5b START-TRAILING-WORD: text glued onto the end of the INIT line (no line end, '.r' then digits): 'texte colle apres la ligne "
        "INIT : demander de la recopier', never 'ce compte n'a pas ETHUSD.r', the glued text never printed, exit code 1",
        lambda: (g["rc"] == 1 and any("texte colle" in x and "recopier" in x for x in g["diff"]) and "ce compte n'a pas" not in g["so"]
                 and not g["leak"], (g["diff"], g["leak"])))
    g = start_go(base_dir, "wrap_in_r", "2026.11.15 10:02:10.123\tClaudeRobot (XAUUSD.r,M1)\t" + init[:-2] + "\n" + init[-2:] + "\n")
    g2 = start_go(base_dir, "wrap_in_r2", "2026.11.15 10:02:10.123\tClaudeRobot (XAUUSD.r,M1)\t" + init[:-1] + "\n" + init[-1:] + "\n")
    chk("review5b control START-TRAILING-WORD: an INIT line the chat wrapped inside its last name ('ETHUSD' then '.r', or 'ETHUSD.' then "
        "'r') is put back together: OK, exit code 0", lambda: (g["rc"] == 0 and g2["rc"] == 0 and not g["diff"] and not g2["diff"]
                                                             and "recollee" in g["so"] and "recollee" in g2["so"], (g["so"][-500:], g2["so"][-500:])))
    # START-GLUED-PREFIX: the copy lost its line ends, the tab's prefix of each line sits between the robot lines
    res = {}
    for name, style, sep in (("copy", "copy", ""), ("copy_space", "copy", " "), ("log", "log", ""), ("spaces", "spaces", " ")):
        txt = experts_paste(full, style, account=False).rstrip("\n").replace("\n", sep) + "\n"
        res[name] = start_go(base_dir, "glued_" + name, txt)
    chk("review5b START-GLUED-PREFIX: the nine start lines glued on one line with the Experts tab's prefix between them (tab, log file or "
        "spaces style; nothing or a space between the lines): every line read, every check OK, exit code 0",
        lambda: (all(v["rc"] == 0 and not v["diff"] and "OK : READY ETHUSD" in v["so"] and "OK : SELFTEST ok=1" in v["so"] for v in res.values()),
                 {k: (v["rc"], v["diff"][:2]) for k, v in res.items()}))
    g = start_go(base_dir, "glued_copy_d2", experts_paste(start_lines(risk=D2), account=False).rstrip("\n").replace("\n", "") + "\n")
    chk("review5b control START-GLUED-PREFIX: the same glued copy of a start with D2: the D2 found (DIFFERENT), exit code 1",
        lambda: (g["rc"] == 1 and any("D2" in x for x in g["diff"]) and not any("ligne coupee" in x for x in g["diff"]), g["diff"][:3]))
    # RH5-5: a refused last start (ERROR, then the stop line deinit=8): the robot left the chart, F7 cannot reach its inputs
    comma = [jl(START_U, "ERROR", "-", ("what", "InpRiskTable: '3000:3,5' is not a pair from:pct of plain numbers")), stop_line(START_U, 8)]
    k1e = [jl(START_U, "ERROR", "BKE", ("what", "InpK1T refused: '2026:417,23813245421888': T must be a number of bp (e.g. 465.1178140105435)")),
           jl(START_U, "ERROR", "-", ("what", "rule BKE: Init refused its configuration")), stop_line(START_U, 8)]
    out = {}
    for name, ls_ in (("comma", comma), ("k1t", k1e)):
        out[name] = start_go(base_dir, "refused_" + name, experts_paste(ls_, account=False))

    def relaunch_ok(g, word):
        d = [x for x in g["diff"] if word in x]
        return (g["rc"] == 1 and len(d) == 1 and "relancer" in d[0] and "etape 6" in d[0] and S7 in d[0] and C.K1T_TEXT in d[0]
                and "F7" not in d[0])
    chk("review5b RH5-5: a refused last start (ERROR InpRiskTable with a comma, or the two InpK1T lines, then INIT deinit=8): the advice is to "
        "relaunch the robot (step 6 of the guide) with the two values, never F7 (the robot left the chart), exit code 1",
        lambda: (relaunch_ok(out["comma"], "InpRiskTable") and relaunch_ok(out["k1t"], "InpK1T"), (out["comma"]["diff"], out["k1t"]["diff"])))
    g = start_go(base_dir, "refused_then_right", experts_paste(comma + full, account=False))
    gd = start_go(base_dir, "running_d2", experts_paste(start_lines(risk=D2), account=False))
    chk("review5b control RH5-5: a refused start followed by the right start: information only, exit code 0; a running start with D2 keeps the "
        "F7 advice", lambda: (g["rc"] == 0 and not g["diff"] and "INFO : demarrage 1" in g["so"] and gd["rc"] == 1
                              and any("F7" in x and "D2" in x for x in gd["diff"]), (g["so"][-700:], gd["diff"][:2])))


STORY_OPENED = srv("2026-11-14 15:30")             # the user's demo account opened on Saturday 14 November 2026 (1 000 EUR)
STORY_START = srv("2026-11-14 16:00")              # the start the guide asks for: Saturday, 15:00 in Paris, every market closed
STORY_COPY = srv("2026-11-18 23:00")               # the Wednesday copy: 22:00 in Paris, the robot running
ERR_COMMA = "InpRiskTable: '3000:3,5' is not a pair from:pct of plain numbers"
ERR_K1T = ("InpK1T refused: '2026:417,23813245421888': T must be a number of bp (e.g. 465.1178140105435)",
           "rule BKE: Init refused its configuration")


def story_journal(folder, segs, trades=(), opened=STORY_OPENED, copy=STORY_COPY, balance0=1000.0):
    """a demo journal as the release robot writes it on the user's Mac in November 2026 (review5b), one daily file per server date. segs: the
    starts in time order, dicts with 'at' (server time of the INIT line), 'to' (server time of the stop line INIT deinit=, None: still running
    when the files were copied at `copy`), 'deinit' (9), 'risk' (S7), 'k1t' (K1T_2026), 'observer' (0), 'refused' (ERROR texts: OnInit refused
    the inputs, so only the ERROR lines and the stop line deinit=8 at 'at', no INIT build=; 'stop_line' False drops that stop line). Each start
    that runs writes INIT, SELFTEST, PLAN src=first_deal and PLAN (InpPlanStart 0 on a demo: the plan starts at the account's first deal,
    `opened`), REBUILD and the four READY. trades: dicts like mini_journal's (code, side, at, hold, ppx, stop, fill, quote, lots, ticket, xpx,
    close) with optional 'refused_closes' (n, rc): n CLOSE ok=0 lines a minute apart from the paper's exit, the close done after them;
    'open_at_copy' (no exit yet when the files were copied); 'booked' (server time, price): no CLOSE line, the balance books the close then
    (the broker's stop while the robot was stopped). A trade whose entry falls while no start runs is the paper's only: the next start's
    rebuild writes its lines rp=1 and its reconcile ends it MISSED late. A position still open at a stop is adopted by the next start (ADOPT).
    The AGG, COST and DAY lines of the day before come at 00:00:30 of each server day a start runs (weekends included); the balance books
    every close. Returns the file names."""
    os.makedirs(folder, exist_ok=True)
    L = []

    def add(t_srv, line):
        L.append((int(t_srv), len(L), line))

    def running(t):
        return next((k for k, s in enumerate(segs) if not s.get("refused") and s["at"] <= t and (s.get("to") is None or t < s["to"])), None)
    for k, s in enumerate(segs):
        a = s["at"]
        u = C.srv_to_utc(a)
        if s.get("refused"):
            for w in s["refused"]:
                add(a, jl(u, "ERROR", "BKE" if w.startswith("InpK1T") else "-", ("what", w)))
            if s.get("stop_line", True):
                add(a, jl(u, "INIT", "-", ("deinit", 8), ("lines", len(s["refused"])), ("bars_fed", 0), ("rebuilds", 0), ("masked_XAUUSD", 0),
                          ("masked_US100", 0), ("masked_BTCUSD", 0), ("masked_ETHUSD", 0)))
            continue
        risk = s.get("risk", S7)
        add(a, init_line(u, risk=risk, k1t=s.get("k1t", K1T_2026), observer=s.get("observer", 0)))
        add(a, jl(u, "SELFTEST", "-", ("ok", 1), ("why", ""), ("golden", 366)))
        if opened:                                                      # no deal yet on the account: T = 0, no 'src=first_deal' line
            add(a + 120, jl(u + 120, "PLAN", "-", ("src", "first_deal"), ("T", opened)))
        add(a + 120, jl(u + 120, "PLAN", "-", ("T", opened or 0), ("state", "ok"), ("demo", 1), ("B_T", 0.0 if opened else balance0),
                        ("risk", risk)))
        add(a + 120, jl(u + 120, "REBUILD", "-", ("n", 1), ("why", "start"), ("from", u - 120 * 86400), ("to", u + 120), ("minutes", 172860),
                        ("ms", 0)))
        for b in C.ROBOT_BASES:
            add(a + 180, jl(u + 180, "READY", b, ("bars", 100000), ("raw", 100000), ("first", u - 120 * 86400), ("last", u), ("masked", 0),
                            ("holes", 0), ("depth_days", C.DEPTH_DAYS[b])))
        if s.get("to") is not None:
            add(s["to"], jl(C.srv_to_utc(s["to"]), "INIT", "-", ("deinit", s.get("deinit", 9)), ("lines", 300), ("bars_fed", 5000),
                            ("rebuilds", 1), ("masked_XAUUSD", 0), ("masked_US100", 0), ("masked_BTCUSD", 0), ("masked_ETHUSD", 0)))
    closes = []                                                         # (server time, EUR) the balance books

    def put_exit(x0, pex):
        """the paper's exit line: live when a start runs then, else written rp=1 by the next start's rebuild (never live while stopped)"""
        if running(x0) is not None:
            add(x0, pex)
            return
        nxt = next((s for s in segs if not s.get("refused") and s["at"] > x0), None)
        if nxt is not None:
            add(nxt["at"] + 119, pex + "|rp=1")
    for t in trades:
        code, side, a = t["code"], t["side"], int(t["at"])
        b = C.SYM_OF_CODE[code]
        ua = C.srv_to_utc(a)
        x0 = a + t["hold"]
        ux = C.srv_to_utc(x0)
        oid = ua * 100 + C.SLEEVE_ID[code]
        h, kk = MINI_H[b], MINI_K[b]
        sp = {"XAUUSD": 0.12, "US100": 1.0, "BTCUSD": 25.0, "ETHUSD": 3.0}[b]
        k_in = running(a)
        dec = dec_ord(ua, code, oid, side, 0, t["ppx"], t["stop"], ux)
        pf = jl(ua, "PFILL", code, ("oid", oid), ("side", side), ("bar", ua), ("px", t["ppx"]), ("stop", t["stop"]), ("st0", t["stop"]),
                ("x", ux), ("s_raw", 12), ("s_paper", 0.12))
        pex = jl(ux, "PEXIT", code, ("oid", oid), ("side", side), ("bar", ux), ("px", t["xpx"]), ("stop", t["stop"]), ("st0", t["stop"]),
                 ("x", ux), ("reason", "time"), ("s_raw", 12), ("s_paper", 0.12))
        sz = [("oid", oid), ("side", side), ("et", 0), ("lots", t["lots"]), ("want", t["lots"]), ("skip", "none"), ("B", balance0), ("P_in", balance0),
              ("rate", 7.0), ("m", 1.0), ("f", 1.0), ("unit", 70.0), ("w", 0.0), ("r", 10.0), ("budget", 70.0), ("late", 0), ("quote", t["quote"])]
        if k_in is None:
            # the robot was stopped at the paper's entry: the next start's rebuild writes the paper's lines rp=1, its reconcile ends the
            # intent MISSED late (CR_Follower.mqh: sendable until stamp + 5 min)
            nxt = next(s for s in segs if not s.get("refused") and s["at"] > a)
            add(nxt["at"] + 119, dec + "|rp=1")
            add(nxt["at"] + 119, pf + "|rp=1")
            add(nxt["at"] + 119, jl(ua, "SIZE", code, *sz, ("rp", 1)))
            add(nxt["at"] + 181, jl(C.srv_to_utc(nxt["at"] + 181), "MISSED", code, ("oid", oid), ("stamp", ua), ("reason", "late")))
            put_exit(x0, pex)
            continue
        add(a, dec)
        add(a, pf)
        add(a, jl(ua, "SIZE", code, *sz))
        q = t["quote"]
        add(a + 1, jl(ua + 1, "SEND", code, ("oid", oid), ("side", side), ("lots", t["lots"]), ("want", t["lots"]), ("sl", t["stop"]),
                      ("bid", q - (sp if side > 0 else 0.0)), ("ask", q + (0.0 if side > 0 else sp)), ("stamp", ua), ("dev", 24), ("cut", "-"),
                      ("result", "filled"), ("rc", 10009), ("s_raw", 12), ("s_paper", 0.12)))
        risk_ = (side * (t["fill"] - t["stop"]) + 2 * h) * kk * t["lots"]
        add(a + 1, jl(ua + 1, "FILL", code, ("oid", oid), ("ticket", t["ticket"]), ("side", side), ("px", t["fill"]), ("lots", t["lots"]),
                      ("sl", t["stop"]), ("listed", 1), ("risk", risk_), ("budget", 70.0), ("stamp", ua), ("s_raw", 12), ("s_paper", 0.12)))
        # a stop while the position is open: the next start adopts it (ADOPT at its reconcile) when it starts before the exit
        s_in = segs[k_in]
        if s_in.get("to") is not None and s_in["to"] < x0:
            nxt = next((s for s in segs if not s.get("refused") and s["at"] >= s_in["to"]), None)
            if nxt is not None and nxt["at"] < x0:
                add(nxt["at"] + 181, jl(C.srv_to_utc(nxt["at"] + 181), "ADOPT", code, ("oid", oid), ("ticket", t["ticket"]), ("open", ua + 1),
                                        ("stamp", ua), ("why", "reconcile")))
        if t.get("open_at_copy"):
            continue
        put_exit(x0, pex)
        k_out = running(x0 + 2)
        if t.get("booked"):
            tb, pxb = t["booked"]
            closes.append((tb, side * (pxb - t["fill"]) * t["lots"] * kk - 2 * h * t["lots"] * kk))
            continue
        if k_out is None:
            continue
        tc = x0 + 2
        for j in range(t.get("refused_closes", (0, 0))[0]):
            add(tc, jl(C.srv_to_utc(tc), "CLOSE", code, ("ticket", t["ticket"]), ("magic", 20261200 + C.SLEEVE_ID[code]), ("px", 0.0),
                       ("why", "time"), ("rc", t["refused_closes"][1]), ("ok", 0)))
            tc += 60
        add(tc, jl(C.srv_to_utc(tc), "CLOSE", code, ("ticket", t["ticket"]), ("magic", 20261200 + C.SLEEVE_ID[code]), ("px", t["close"]),
                   ("why", "time"), ("rc", 10009), ("ok", 1)))
        closes.append((tc, side * (t["close"] - t["fill"]) * t["lots"] * kk - 2 * h * t["lots"] * kk))
    first = min((s["at"] for s in segs if not s.get("refused")), default=None)
    if first is not None:
        for pd in range(first - first % 86400, copy - copy % 86400, 86400):
            tw = pd + 86400 + 30
            if running(tw) is None or tw > copy:
                continue
            bal = round(balance0 + sum(pl for tc, pl in closes if tc < pd + 86400), 2)
            wk = C.dow(pd) in (0, 6)
            uw = C.srv_to_utc(tw)
            add(tw, jl(uw, "AGG", "-", ("day", pd), ("XAUUSD", 0 if wk else 1300), ("US100", 0 if wk else 800), ("BTCUSD", 0 if wk else 1440),
                       ("ETHUSD", 0 if wk else 1440), ("dec", 10), ("pev", 3)))
            if not wk:
                add(tw, jl(uw, "COST", "XAUUSD", ("day", pd), ("raw_bp", 0.2), ("paper_bp", 0.53), ("model_bp", 0.47), ("comm_usd_oz", 0.06),
                           ("comm_n", 2)))
                for b_, m_ in (("US100", 0.37), ("BTCUSD", 2.96), ("ETHUSD", 13.0)):
                    add(tw, jl(uw, "COST", b_, ("day", pd), ("raw_bp", m_), ("paper_bp", m_), ("model_bp", m_)))
            add(tw, jl(uw, "DAY", "-", ("day", pd), ("balance", bal), ("equity", bal), ("bars_fed", 5000)))
    L.sort(key=lambda x: (x[0], x[1]))
    files = {}
    for t, _, ln in L:
        if t > copy:
            continue                                                    # written after the copy: not in the files sent
        files.setdefault(time.strftime("%Y%m%d", time.gmtime(t)) + ".log", []).append(ln)
    for name, lines in files.items():
        write(os.path.join(folder, name), "\n".join(lines) + "\n", crlf=True)
    return sorted(files)


def story_trade(code, at, ticket, hold=3600, side=1, **kw):
    """one trade of story_journal at server time `at`: prices near the market's level, the fill and the close at the paper's prices
    (gold: the paper's prices hold the commission h)"""
    b = C.SYM_OF_CODE[code]
    px = A5_PX[b]
    h = MINI_H[b]
    stop = px * (1 - side * 0.01)
    xpx = px * (1 + side * 0.002)
    t = {"code": code, "side": side, "at": at, "hold": hold, "ppx": px, "stop": stop, "fill": px - side * h, "quote": px - side * h,
         "lots": A5_LOTS[b], "ticket": ticket, "xpx": xpx, "close": xpx + side * h}
    t.update(kw)
    return t


STORY_END = srv("2026-11-18 22:30")                # a stop line before the copy (the journal ends complete: no end-of-journal remark)


def story_trades():
    """the clean week of the stories: four trades closed by the robot on Monday and Tuesday 16-17 November 2026"""
    return [story_trade("ORX", srv("2026-11-16 10:00"), 70009001), story_trade("N30", srv("2026-11-16 17:00"), 70009002, side=-1),
            story_trade("BKB", srv("2026-11-17 09:00"), 70009003), story_trade("BKE", srv("2026-11-17 14:00"), 70009004, side=-1)]


def start_paste_of(jdir):
    """the start lines the user would paste from the Experts tab: the live lines of the journal up to the last READY of its last start"""
    ls_ = [ln for f in sorted(os.listdir(jdir)) for ln in lines_of(os.path.join(jdir, f)) if ln.startswith("CR|") and "|rp=1" not in ln]
    last_init = max((k for k, ln in enumerate(ls_) if "|INIT|-|build=" in ln), default=None)
    ready = [k for k, ln in enumerate(ls_) if "|READY|" in ln and (last_init is None or k > last_init)]
    end = max(ready) + 1 if ready else len(ls_)
    keep = [ln for ln in ls_[:end] if any(f"|{e}|" in ln for e in ("INIT", "SELFTEST", "PLAN", "REBUILD", "READY", "ERROR", "CLOCK"))]
    return experts_paste(keep, account=False)


def test_review5b_journal(lit):
    """review5b (the fifth round's second pass), check_demo on journals of the user's November 2026 demo (story_journal): RH5-1 (a start OnInit
    refused: ERROR then INIT deinit=8), RH5-2 (a start replaced by a later one: its settings are information, its real trades are named, the
    settings in force said), OBSERVER-NORMAL, PRINTED-RESTART-UNCHECKED (a restart whose daily file is lost, its INIT in the Experts log)"""
    del lit
    base_dir = os.path.join(SCRATCH, "rv5bj")

    def go(name, segs=None, trades=(), extra=(), prep=None, jdir=None, **kw):
        jdir = jdir or os.path.join(base_dir, "j_" + name, "ClaudeRobot")
        if not os.path.isdir(jdir) or not os.listdir(jdir):
            story_journal(jdir, segs, trades, **kw)
        if prep:
            prep(jdir)
        out = os.path.join(base_dir, "out_" + name)
        rc, so, se = run_tool("check_demo.py", ["--journals", os.path.dirname(jdir), "--out", out] + list(extra))
        rp = os.path.join(out, "report.json")
        r = json.load(open(rp)) if rc == 0 and os.path.exists(rp) else {}
        rt = os.path.join(out, "report_fr.txt")
        return {"rc": rc, "so": so, "se": se, "r": r, "an": r.get("anomalies", []), "jdir": jdir, "out": out,
                "rtxt": open(rt, encoding="utf-8").read() if rc == 0 and os.path.exists(rt) else "",
                "txt": (outputs_text(out) if rc == 0 else "") + so + se}
    S0, END = STORY_START, STORY_END
    tr = story_trades()
    # RH5-1: a start OnInit refused (the typo the guide plans for), then the relaunch with the right values
    shapes = {"b1": [{"at": S0 - 240, "refused": [ERR_COMMA]}, {"at": S0, "to": END}],
              "b2": [{"at": S0 - 240, "refused": list(ERR_K1T)}, {"at": S0, "to": END}],
              "b3": [{"at": S0 - 600, "to": S0 - 65, "deinit": 5, "risk": D2, "k1t": ""}, {"at": S0 - 60, "refused": [ERR_COMMA]},
                     {"at": S0 + 180, "to": END}],
              "b5": [{"at": S0 - 240, "refused": [ERR_COMMA], "stop_line": False}, {"at": S0, "to": END}]}
    res = {k: go("rh51_" + k, v, tr) for k, v in shapes.items()}
    bad = {k: (g["rc"], g["an"][:3], g["so"].splitlines()[0][:120]) for k, g in res.items()
           if g["rc"] != 0 or g["an"] or "build ?" in g["so"] or g["r"].get("journal", {}).get("restarts") != (1 if k == "b3" else 0)
           or not ((g["r"].get("fills") or {}).get("money_estimate") or {}).get("complete")}
    chk("review5b RH5-1: a start OnInit refused (a comma in InpRiskTable, the two InpK1T lines, a typo made with F7 after a D2 start, an ERROR "
        "with its stop line lost), then the relaunch: nothing abnormal, no 'build ?', no lost INIT or journal start, the restart count and the "
        "money estimate as without it", lambda: (not bad, bad))
    inf = [ln for ln in res["b1"]["so"].splitlines() if ln.startswith("Information") and "refuse" in ln]
    chk("review5b RH5-1: the refused start is said on stdout as information, with what the ERROR means (a comma typed in InpRiskTable) and "
        "when the robot was relaunched (Paris time)", lambda: (len(inf) == 1 and "virgule" in inf[0] and "InpRiskTable" in inf[0]
                                                              and "relance" in inf[0] and "heure de Paris" in inf[0], res["b1"]["so"][:900]))
    g = go("rh51_b4", [{"at": S0, "refused": [ERR_COMMA]}], ())
    chk("review5b RH5-1: a refused start alone (ERROR, then INIT deinit=8, nothing after): the first anomaly says the robot did not start, "
        "what the ERROR means and to relaunch it (step 6 of the guide) with the two values; never 'envoyer aussi le fichier du jour'",
        lambda: (g["rc"] == 0 and g["an"] and "n'a pas demarre" in g["an"][0] and "virgule" in g["an"][0] and "etape 6" in g["an"][0]
                 and S7 in g["an"][0] and not any("envoyer aussi le fichier" in a for a in g["an"]), g["an"][:3]))
    agree = []
    for k, gk in list(res.items()) + [("b4", g)]:
        gs = start_go(base_dir, "agree5b_" + k, start_paste_of(gk["jdir"]))
        if (gs["rc"] == 0) != (gk["an"] == []):
            agree.append((k, gs["rc"], gs["diff"][:2], gk["an"][:2]))
    chk("review5b RH5-1: check_start and check_demo agree on these journals (the start lines pasted): both conforming after a refused start "
        "and its relaunch, both flagging a refused start alone", lambda: (not agree, agree))
    # RH5-2: a start replaced by a later one
    gc = go("rh52_c", [{"at": S0 - 600, "to": S0 - 60, "deinit": 5, "risk": D2, "k1t": ""}, {"at": S0 - 55, "to": END}], tr)
    info1 = [ln for ln in gc["so"].splitlines() if ln.startswith("Information") and "demarrage 1" in ln]
    rv = next((ln for ln in gc["so"].splitlines() if ln.startswith("Reglages en vigueur")), "")
    chk("review5b RH5-2: a start with D2 and InpK1T empty replaced 9 minutes later (F7) by the right one: no anomaly about the settings of the "
        "replaced start, which is said as information (D2, remplace), and a stdout line says the settings in force are right",
        lambda: (gc["rc"] == 0 and gc["an"] == [] and len(info1) == 1 and "D2" in info1[0] and "remplace" in info1[0]
                 and "conformes" in rv and "heure de Paris" in rv, (gc["an"][:3], info1, rv)))
    gs = start_go(base_dir, "agree5b_c", start_paste_of(gc["jdir"]))
    chk("review5b RH5-2: check_start gives the same verdict as check_demo on that two-start journal (conforming)",
        lambda: (gs["rc"] == 0 and gc["an"] == [], (gs["diff"][:2], gc["an"][:2])))
    g1 = go("rh52_c_inforce", [{"at": S0 - 600, "to": S0 - 60, "deinit": 5}, {"at": S0 - 55, "to": END, "risk": D2}], tr)
    chk("review5b control RH5-2: the right start replaced by a start with D2: the start in force is flagged (D2, InpRiskTable)",
        lambda: (g1["rc"] == 0 and any("D2" in a and "demarrage 2" in a for a in g1["an"]), g1["an"][:3]))
    op = srv("2026-11-11 10:00")
    d_tr = [story_trade("BKB", srv("2026-11-11 18:30"), 70008001), story_trade("N30", srv("2026-11-12 16:40"), 70008002),
            story_trade("OC4", srv("2026-11-12 18:55"), 70008003, hold=4 * 3600, booked=(srv("2026-11-13 18:10"), A5_PX["US100"] * 0.99)),
            story_trade("ORX", srv("2026-11-12 10:00"), 70008004, hold=srv("2026-11-16 12:00") - srv("2026-11-12 10:00"))] + tr
    gd = go("rh52_d", [{"at": srv("2026-11-11 18:00"), "to": srv("2026-11-12 19:59"), "deinit": 1, "risk": D2, "k1t": ""},
                       {"at": S0, "to": END}], d_tr, opened=op)
    an_d = " | ".join(gd["an"])
    chk("review5b RH5-2: an earlier run with D2 (11-12 November, robot removed with a position open) before the S7 start: no anomaly about its "
        "settings as such, but one naming the real trades made with D2 (4, with their result) and the position the next start took over "
        "(ADOPT, ticket 70008004)", lambda: (gd["rc"] == 0 and "a taper dans InpRiskTable" not in an_d and "trade(s) reel(s)" in an_d
                                             and "D2" in an_d and "70008004" in an_d and "4 trade(s)" in an_d, gd["an"][:4]))
    chk("review5b RH5-2: the plan of the start in force begins before the earlier start (InpPlanStart 0: the account's first deal): said, the "
        "plan and the money count that earlier run", lambda: (gd["rc"] == 0 and any("plan" in ln and "demarrage 1" in ln and "compte" in ln
                                                                                   for ln in gd["so"].splitlines()), gd["so"][:1500]))
    # OBSERVER-NORMAL: an observer copy during the demo
    go_ = go("obs_demo", [{"at": S0, "to": END, "observer": 1}], ())
    chk("review5b OBSERVER-NORMAL: a demo copy on the Mac left as an observer (observer=1) in the demo's first two weeks (the plan starts at the "
        "account's first deal, just before): an anomaly naming InpTrade, never 'normal'",
        lambda: (go_["rc"] == 0 and any("observatrice" in a and "InpTrade" in a for a in go_["an"]) and "normal)" not in go_["so"], go_["an"][:3]))
    go0 = go("obs_t0", [{"at": S0, "to": END, "observer": 1}], (), opened=0)
    chk("review5b OBSERVER-NORMAL: an observer copy whose account has no deal yet (no date for the demo): no anomaly (the VPS weeks also use one), "
        "but stdout says it sent no order because InpTrade is false, never 'normal'",
        lambda: (go0["rc"] == 0 and go0["an"] == [] and "InpTrade" in go0["so"] and "normal)" not in go0["so"], (go0["an"][:2], go0["so"][:600])))
    # PRINTED-RESTART-UNCHECKED: the restart day's file lost, the restart made with D2, the Mac's Experts logs given
    jsrc = os.path.join(base_dir, "j_pr_src", "ClaudeRobot")
    md_journal(jsrc, ("restart_d2",))
    logs = printed_files(os.path.join(base_dir, "logs_pr"), jsrc)
    jl_ = os.path.join(base_dir, "j_pr_lost", "ClaudeRobot")
    md_journal(jl_, ("restart_d2",))
    os.remove(os.path.join(jl_, "20211122.log"))
    gp = go("pr_lost", jdir=jl_, extra=[x for p in logs for x in ("--printed", p)])
    ga = go("pr_lost_alone", jdir=jl_)
    infp = [ln for ln in gp["so"].splitlines() if ln.startswith("Information") and "onglet Experts" in ln]
    chk("review5b PRINTED-RESTART-UNCHECKED: a restart made with D2 whose daily file is lost, the Mac's Experts logs given: its INIT (in the "
        "Experts log only) is checked: an anomaly naming D2 and the Experts log, and an information line says the restart was seen there, in "
        "the missing file", lambda: (gp["rc"] == 0 and any("D2" in a and "onglet Experts" in a for a in gp["an"])
                                     and any("redemarrage" in ln and "20211122.log" in ln and "DIFFERENTS" in ln for ln in infp), (gp["an"][:4], infp)))
    chk("review5b control PRINTED-RESTART-UNCHECKED: without the Experts logs the restart's settings stay unknown (said with the missing file)",
        lambda: (ga["rc"] == 0 and any("20211122.log" in a and "inconnus" in a for a in ga["an"]) and not any("D2" in a for a in ga["an"]),
                 ga["an"][:3]))
    segs_r = [{"at": S0, "to": srv("2026-11-17 15:00"), "deinit": 1}, {"at": srv("2026-11-17 15:12"), "to": END, "risk": D2}]
    jr = os.path.join(base_dir, "j_pr_day_src", "ClaudeRobot")
    story_journal(jr, segs_r, tr)
    logs_r = printed_files(os.path.join(base_dir, "logs_pr_day"), jr)
    gq = go("pr_day", segs_r, tr, prep=lambda j: os.remove(os.path.join(j, "20261117.log")),
            extra=[x for p in logs_r for x in ("--printed", p)])
    infq = [ln for ln in gq["so"].splitlines() if ln.startswith("Information") and "onglet Experts" in ln]
    chk("review5b PRINTED-RESTART-UNCHECKED: a stop and a restart (with D2) inside a lost day, the Experts logs given: the restart's D2 flagged "
        "naming the Experts log, and an information line names the stop and the restart the Experts tab shows in the missing file",
        lambda: (gq["rc"] == 0 and any("D2" in a and "onglet Experts" in a for a in gq["an"])
                 and any("20261117.log" in ln and "arret" in ln and "redemarrage" in ln for ln in infq), (gq["an"][:4], infq)))
    chk("review5b: no account word in any output of these cases", lambda: (all(not leak_free(x["txt"]) for x in
                                                                              list(res.values()) + [g, gc, gd, go_, go0, gp, gq]), None))


def test_review5b_fills(lit):
    """review5b, positions and outages on journals of the user's November 2026 demo: LOST-FILE-POSITIONS (a position whose close or stop moves
    were in a lost daily file), RH5-3 (closes MetaTrader refused while Algo Trading was off), RH5-4 (the copy taken while the robot runs, --copie),
    RH5-6 (a paper trade while MetaTrader was closed), RH5-7 (a position closed while the robot was stopped, the balance difference with unknown
    exits), RH5-8 (the Mac asleep: the last line at a sure time), RH5-9 (positions still open at the copy), RH5-10 (Paris times on stdout)"""
    del lit
    base_dir = os.path.join(SCRATCH, "rv5bf")

    def go(name, segs=None, trades=(), extra=(), prep=None, jdir=None, **kw):
        jdir = jdir or os.path.join(base_dir, "j_" + name, "ClaudeRobot")
        if not os.path.isdir(jdir) or not os.listdir(jdir):
            story_journal(jdir, segs, trades, **kw)
        if prep:
            prep(jdir)
        out = os.path.join(base_dir, "out_" + name)
        rc, so, se = run_tool("check_demo.py", ["--journals", os.path.dirname(jdir), "--out", out] + list(extra))
        rp = os.path.join(out, "report.json")
        r = json.load(open(rp)) if rc == 0 and os.path.exists(rp) else {}
        rt = os.path.join(out, "report_fr.txt")
        return {"rc": rc, "so": so, "se": se, "r": r, "an": r.get("anomalies", []), "jdir": jdir,
                "rtxt": open(rt, encoding="utf-8").read() if rc == 0 and os.path.exists(rt) else "",
                "txt": (outputs_text(out) if rc == 0 else "") + so + se}
    S0, END = STORY_START, STORY_END
    tr = story_trades()
    # LOST-FILE-POSITIONS: a gold position opened on Monday night; its close (Tuesday 10:00) is in the lost file of Tuesday; a reconnection on
    # Wednesday rebuilds the history, so the paper's exit is known (rp=1)
    lp = story_trade("ORX", srv("2026-11-16 22:00"), 70009101, hold=12 * 3600)

    def lost_close(jdir):
        p = os.path.join(jdir, "20261118.log")
        ls_ = lines_of(p)
        src = os.path.join(base_dir, "lp_pexit.txt")
        pex = open(src).read().strip() if os.path.exists(src) else ""
        u = C.srv_to_utc(srv("2026-11-18 09:00"))
        k = next(i for i, ln in enumerate(ls_) if int(ln.split("|")[1]) >= u)
        ls_[k:k] = [pex + "|rp=1", jl(u + 2, "REBUILD", "-", ("n", 2), ("why", "reconnect"), ("from", u - 120 * 86400), ("to", u), ("minutes", 172800),
                                      ("ms", 900))]
        write(p, "\n".join(ls_) + "\n", crlf=True)
        os.remove(os.path.join(jdir, "20261117.log"))
    jfull = os.path.join(base_dir, "j_lp_full", "ClaudeRobot")
    story_journal(jfull, [{"at": S0, "to": END}], tr + [lp])
    lp_oid = C.srv_to_utc(lp["at"]) * 100 + C.SLEEVE_ID["ORX"]
    pex = next(ln for ln in lines_of(os.path.join(jfull, "20261117.log")) if "|PEXIT|ORX|" in ln and f"|oid={lp_oid}|" in ln)
    write(os.path.join(base_dir, "lp_pexit.txt"), pex + "\n")
    g = go("lp_close", [{"at": S0, "to": END}], tr + [lp], prep=lost_close)
    chk("review5b LOST-FILE-POSITIONS: a position whose close was in a lost daily file (its paper exit known from a later rebuild): said as an "
        "exit in that missing file (named), never 'non fermee par le robot' or 'stop du courtier touche avant'",
        lambda: (g["rc"] == 0 and g["an"] and "20261117.log" in g["an"][0] and all("20261117.log" in a for a in g["an"])
                 and not any("non fermee par le robot" in a or "touche avant" in a for a in g["an"]), g["an"][:4]))
    # the same position stopped by the broker on Wednesday: its trailing stop moves were in the lost file; the releve's minutes cross the last
    # stop, not the FILL's
    ls_t = story_trade("ORX", srv("2026-11-16 22:00"), 70009102, hold=srv("2026-11-18 05:00") - srv("2026-11-16 22:00"))

    def lost_stop(jdir):
        p = os.path.join(jdir, "20261118.log")
        out_ = []
        for ln in lines_of(p):
            if "|CLOSE|ORX|" in ln and "70009102" in ln:
                continue                                                # the broker's stop: no CLOSE line
            if "|PEXIT|ORX|" in ln and f"|oid={C.srv_to_utc(ls_t['at']) * 100 + C.SLEEVE_ID['ORX']}|" in ln:
                ln = re.sub(r"\|px=[^|]*", "|px=1.8579000000000000e+03", ln)
                ln = re.sub(r"\|stop=[^|]*", "|stop=1.8580000000000000e+03", ln).replace("|reason=time", "|reason=stop")
            out_.append(ln)
        write(p, "\n".join(out_) + "\n", crlf=True)
        os.remove(os.path.join(jdir, "20261117.log"))
    mdir = os.path.join(base_dir, "m1_lp")
    os.makedirs(mdir, exist_ok=True)
    m1_flat(os.path.join(mdir, "m1_XAUUSD.csv"), srv("2026-11-16 20:00"), srv("2026-11-18 12:00"), bid=1860.0, dip_at=srv("2026-11-18 04:58"),
            dip_low=1857.5)
    g2 = go("lp_stop", [{"at": S0, "to": END}], tr + [ls_t], prep=lost_stop, extra=("--bars", mdir, "--no-replay"))
    chk("review5b LOST-FILE-POSITIONS: a position stopped by the broker whose stop moves were in the lost file (the minutes cross the paper's "
        "last stop, not the FILL's): said with the missing file, never 'fermee autrement (a la main, stop-out ?)'",
        lambda: (g2["rc"] == 0 and any("20261117.log" in a and "70009102" in a for a in g2["an"])
                 and not any("a la main" in a for a in g2["an"]), g2["an"][:4]))
    # RH5-3: the Algo Trading button red for an hour: MetaTrader refuses the robot's closes (rc 10027), they go through 47 and 30 min late
    al = [story_trade("NQB", srv("2026-11-16 18:43"), 70009201, refused_closes=(47, 10027)),
          story_trade("N30", srv("2026-11-16 19:00"), 70009202, refused_closes=(30, 10027))]
    g = go("algo", [{"at": S0, "to": END}], tr + al)
    an = " | ".join(g["an"])
    chk("review5b RH5-3: closes refused by MetaTrader with rc=10027 (Algo Trading off), 47 and 30 times, then done: an anomaly with the code's "
        "meaning, the count, the positions, how late after the paper they closed, Paris times and the advice (the button green)",
        lambda: (g["rc"] == 0 and "10027" in an and "Algo Trading" in an and "x77" in an and "2 position(s)" in an and "47 min" in an
                 and "heure de Paris" in an and "vert" in an, g["an"][:3]))
    g0 = go("algo_once", [{"at": S0, "to": END}], tr + [story_trade("NQB", srv("2026-11-16 18:43"), 70009203, refused_closes=(1, 10004))])
    chk("review5b control RH5-3: one close refused once (requote 10004) and done a minute later: no anomaly",
        lambda: (g0["rc"] == 0 and g0["an"] == [], g0["an"][:3]))
    # RH5-6: MetaTrader quit 18:25 server and reopened at 18:40: the N30 entry of 18:30 falls inside
    seg6 = [{"at": S0, "to": srv("2026-11-17 18:25"), "deinit": 9}, {"at": srv("2026-11-17 18:40"), "to": END}]
    g6 = go("stop_window", seg6, tr + [story_trade("N30", srv("2026-11-17 18:30"), 70009301)])
    nf = [ln for ln in g6["so"].splitlines() if "non suivi" in ln]
    chk("review5b RH5-6: a paper trade whose entry falls while MetaTrader was closed (stop line, then the next start) is said on stdout as not "
        "followed during the stop, with its time in Paris, and not as a trade already open at a start",
        lambda: (g6["rc"] == 0 and nf and "N30" in nf[0] and "arret" in nf[0] and "heure de Paris" in nf[0]
                 and "deja ouverts a un demarrage" not in g6["rtxt"], (nf, g6["so"][-600:])))
    # RH5-7: the earlier run of story d (robot removed with OC4 open, closed by its broker stop on Friday while the robot was stopped)
    op = srv("2026-11-11 10:00")
    d_tr = [story_trade("BKB", srv("2026-11-11 18:30"), 70008001), story_trade("N30", srv("2026-11-12 16:40"), 70008002),
            story_trade("OC4", srv("2026-11-12 18:55"), 70008003, hold=4 * 3600, booked=(srv("2026-11-13 18:10"), A5_PX["US100"] * 0.99))] + tr
    g7 = go("stopped_exit", [{"at": srv("2026-11-11 18:00"), "to": srv("2026-11-12 19:59"), "deinit": 1}, {"at": S0, "to": END}], d_tr, opened=op)
    oc4 = [a for a in g7["an"] if "70008003" in a]
    sl = next((ln for ln in g7["so"].splitlines() if ln.startswith("Solde")), "")
    chk("review5b RH5-7: a position whose paper exit came while the robot was stopped and that the next start did not take over: 'le robot etait "
        "arrete', closed meanwhile; never 'non fermee par le robot, ou stop du courtier touche avant'",
        lambda: (g7["rc"] == 0 and oc4 and "arrete" in oc4[0] and "plus ouverte" in oc4[0] and "touche avant" not in oc4[0], oc4))
    chk("review5b RH5-7: with exits unknown, the money line says an unexplained balance difference (with the positions without an exit price), "
        "not costs", lambda: (g7["rc"] == 0 and "difference non expliquee" in sl and "sans prix de sortie" in sl and "cout de" not in sl, sl))
    # RH5-4 and RH5-9: the Wednesday copy taken while the robot runs, a position still open
    run_tr = tr + [story_trade("F1E", srv("2026-11-18 20:00"), 70009401, open_at_copy=True)]
    g4 = go("running", [{"at": S0, "to": None}], run_tr)
    g4c = go("running_copy", [{"at": S0, "to": None}], run_tr, extra=("--copie", "2026-11-18 22:00"))
    g4l = go("running_late", [{"at": S0, "to": None}], run_tr, extra=("--copie", "2026-11-19 22:00"))
    chk("review5b RH5-4: the copy taken while the robot runs, journals only: the end-of-journal remark says it is normal for the Wednesday or "
        "Saturday copy and how to settle it (--copie), and the rest of the verdict is printed",
        lambda: (g4["rc"] == 0 and len(g4["an"]) == 1 and "mercredi ou du samedi" in g4["an"][0] and "--copie" in g4["an"][0]
                 and any(ln.startswith("Pour le reste") and "rien d'anormal" in ln for ln in g4["so"].splitlines()), (g4["an"], g4["so"][-500:])))
    chk("review5b RH5-4: with --copie (the Paris time of the user's message) the journal reaching the copy's day is a robot still running: "
        "no anomaly, the verdict line printed; a copy a day after the journal's end names the missing file",
        lambda: (g4c["rc"] == 0 and g4c["an"] == [] and "Rien d'anormal" in g4c["so"] and g4l["rc"] == 0
                 and any("20261119.log" in a for a in g4l["an"]), (g4c["an"], g4l["an"][:2])))
    f1e = next((ln for ln in g4["rtxt"].splitlines() if ln.strip().startswith("F1E") and "position(s)" in ln), "")
    chk("review5b RH5-9: a position still open when the files were copied is 'encore ouverte' in its sleeve's line, not an unknown exit",
        lambda: (g4["rc"] == 0 and "encore ouverte" in f1e and "sortie(s) inconnue(s)" not in f1e, f1e))
    # RH5-8 and RH5-10: the Mac asleep Monday night (the robot's process frozen: a catch-up at the wake, a MISSED late written hours after
    # its time, the daily lines stamped at the server's midnight)
    def asleep(jdir):
        p = os.path.join(jdir, "20261117.log")
        ls_ = lines_of(p)
        u_w = C.srv_to_utc(srv("2026-11-17 08:12"))
        st = C.srv_to_utc(srv("2026-11-17 03:00"))
        oid = st * 100 + C.SLEEVE_ID["BKB"]
        k = next(i for i, ln in enumerate(ls_) if int(ln.split("|")[1]) >= u_w)
        ls_[k:k] = [dec_ord(st, "BKB", oid, 1, 0, 57000.0, 56430.0, st + 3600),
                    jl(st, "PFILL", "BKB", ("oid", oid), ("side", 1), ("bar", st), ("px", 57000.0), ("stop", 56430.0), ("st0", 56430.0),
                       ("x", st + 3600), ("s_raw", 12), ("s_paper", 0.12)),
                    jl(u_w, "MISSED", "BKB", ("oid", oid), ("stamp", st), ("reason", "late")),
                    jl(st + 3600, "PEXIT", "BKB", ("oid", oid), ("side", 1), ("bar", st + 3600), ("px", 57100.0), ("stop", 56430.0),
                       ("st0", 56430.0), ("x", st + 3600), ("reason", "time"), ("s_raw", 12), ("s_paper", 0.12))]
        write(p, "\n".join(ls_) + "\n", crlf=True)
    g8 = go("asleep", [{"at": S0, "to": END}], tr, prep=asleep)
    sl8 = [ln for ln in g8["rtxt"].splitlines() if "HORS LIGNE" in ln]
    chk("review5b RH5-8: the Mac asleep: the report gives the last line at a sure time and says the DAY, AGG and COST lines are stamped at the "
        "server's midnight (never 'aucune ligne du robot du ... au reveil')",
        lambda: (g8["rc"] == 0 and sl8 and "heure sure" in sl8[0] and "minuit serveur" in sl8[0] and "aucune ligne du robot du" not in sl8[0], sl8))
    utc_lines = [ln for x in (g6, g8, g4c) for ln in x["so"].splitlines() if " UTC" in ln and not ln.startswith("Fichiers")]
    chk("review5b RH5-10: every stdout line with a UTC time also gives the Paris time the user reads (outages, trades not followed, the first "
        "intention of the money line)", lambda: (utc_lines and all("heure de Paris" in ln for ln in utc_lines), [ln[:200] for ln in utc_lines
                                                                                                             if "heure de Paris" not in ln][:4]))
    chk("review5b: no account word in any output of these cases", lambda: (all(not leak_free(x["txt"]) for x in (g, g2, g0, g6, g7, g4, g4c, g4l, g8)),
                                                                          None))


def test_review6_start(lit):
    """review6 (the sixth round), check_start.py: FV5-START-TRAILING-DIGITS (a time, a number, a dot or the login typed alone on the line after a
    PLAN, SELFTEST or CLOCK line was glued onto its last value: a false DIFFERENT, the login printed; text glued on the same line), with lines
    the chat really wrapped inside their last value as controls; FV5-START-SECOND-COPY (a second copy MetaTrader refused while the start runs,
    its ERROR and stop line after or inside the start's lines)"""
    del lit
    base_dir = os.path.join(SCRATCH, "rv6s")
    os.makedirs(base_dir, exist_ok=True)
    full = start_lines()
    init, selftest, plan_src, plan = full[:4]
    up_plan = [init, selftest, plan_src, plan]
    clock = jl(START_U, "CLOCK", "-", ("state", "wrong"), ("measured_s", 3600), ("rule_s", 7200))
    pre = "2026.11.15 10:02:14.111\tClaudeRobot (XAUUSD.r,M1)\t"

    def ep(ls):
        return experts_paste(ls, account=False)
    # FV5-START-TRAILING-DIGITS: a line the user typed after the robot's lines
    res = {}
    for name, text in (("plan_time", ep(up_plan) + "10:02\n"), ("plan_login", ep(up_plan) + FAKE_LOGIN + "\n"), ("plan_dot", ep(up_plan) + ".\n"),
                       ("plan_1500", ep(up_plan) + "1500\n"), ("bare_plan_login", "\n".join(up_plan) + "\n" + FAKE_LOGIN + "\n"),
                       ("selftest_0", ep([init, selftest]) + "0\n")):
        res[name] = start_go(base_dir, "trail6_" + name, text)
    bad = {k: (g["rc"], g["diff"][:2], g["leak"]) for k, g in res.items()
           if g["rc"] != 0 or g["diff"] or "recollee" in g["so"] or g["leak"] or "OK : SELFTEST ok=1 (366 vecteurs)" not in g["so"]
           or (k != "selftest_0" and "OK : PLAN state=ok" not in g["so"])}
    chk("review6 FV5-START-TRAILING-DIGITS: the start lines up to PLAN (or SELFTEST), then a time ('10:02'), a number, a dot or the login typed alone "
        "on the next line, with or without the Experts prefix: never glued onto the risk table or golden=, every check OK, exit code 0, the login "
        "never printed", lambda: (not bad, bad))
    g = start_go(base_dir, "trail6_clock_login", ep(full + [clock]) + FAKE_LOGIN + "\n")
    chk("review6 FV5-START-TRAILING-DIGITS: a CLOCK state=wrong line, then the login alone on the next line: the CLOCK line read alone (its rule, "
        "7200 s), the login never printed", lambda: (g["rc"] == 1 and any("CLOCK" in x and "7200 s" in x for x in g["diff"]) and not g["leak"],
                                                     (g["diff"][:2], g["leak"])))
    glued = {"plan_space": start_go(base_dir, "glue6_plan_space", ep([init, selftest, plan_src, plan + " " + FAKE_LOGIN])),
             "plan": start_go(base_dir, "glue6_plan", ep([init, selftest, plan_src, plan + FAKE_LOGIN])),
             "clock": start_go(base_dir, "glue6_clock", ep(full + [clock + FAKE_LOGIN])),
             "selftest": start_go(base_dir, "glue6_selftest", ep([init, selftest + "12"]))}
    bad = {k: (g["rc"], g["diff"][:2], g["leak"]) for k, g in glued.items()
           if g["rc"] != 1 or g["leak"] or "36612" in g["so"] or "pas le fichier envoye" in g["so"]
           or not any(("texte colle" in x and "recopier" in x) for x in g["diff"])}
    chk("review6 FV5-START-TRAILING-DIGITS: the login glued after the PLAN line (with or without a space) or after the CLOCK line, digits glued "
        "after golden=366, on the same line: the glued text never printed, 'texte colle ... recopier' (never 'pas le fichier envoye'), exit code 1",
        lambda: (not bad, bad))
    fz = start_go(base_dir, "glue6_risk_edited", ep([init.replace("risk=0:7;3000:3.5", f"risk=0:7;3{FAKE_LOGIN}000:3.5")] + full[1:]))
    chk("review6 FV5-START-TRAILING-DIGITS: an INIT line whose risk table holds the login (an edited line: the robot refuses such a table at "
        "OnInit): never printed, the line to be copied again, exit code 1",
        lambda: (fz["rc"] == 1 and not fz["leak"] and any("recopier" in x for x in fz["diff"]), (fz["diff"][:2], fz["leak"])))
    wrapped = {"plan_cut_dot": ep([init, selftest, plan_src]) + pre + plan[:-1] + "\n" + plan[-1:] + "\n",
               "plan_cut_digit": ep([init, selftest, plan_src]) + pre + plan[:-2] + "\n" + plan[-2:] + "\n",
               "selftest_cut_digit": ep([init]) + pre + selftest[:-1] + "\n" + selftest[-1:] + "\n",
               "selftest_cut_field": ep([init]) + pre + selftest[:-len("|golden=366")] + "\n|golden=366\n"}
    gw = {k: start_go(base_dir, "wrap6_" + k, v) for k, v in wrapped.items()}
    chk("review6 control FV5-START-TRAILING-DIGITS: PLAN and SELFTEST lines the chat wrapped inside their last value ('20000:0.' then '7', "
        "'20000:0' then '.7', 'golden=36' then '6', before '|golden=366'): put back together, every check OK, exit code 0",
        lambda: (all(g["rc"] == 0 and not g["diff"] and "OK : SELFTEST ok=1 (366 vecteurs)" in g["so"] for g in gw.values()),
                 {k: (g["rc"], g["diff"][:2]) for k, g in gw.items()}))
    gi = [start_go(base_dir, "trail6_init_" + w, ep([init]) + t + "\n") for w, t in (("time", "10:02"), ("login", FAKE_LOGIN))]
    gd = start_go(base_dir, "trail6_d2_time", ep(start_lines(risk=D2)[:4]) + "10:02\n")
    chk("review6 control FV5-START-TRAILING-DIGITS: the INIT line alone then a time or the login: OK, exit code 0, nothing printed; a D2 start up "
        "to PLAN then a time: D2 flagged, exit code 1",
        lambda: (all(g["rc"] == 0 and not g["diff"] and not g["leak"] for g in gi) and gd["rc"] == 1 and any("D2" in x for x in gd["diff"]),
                 ([g["diff"][:1] for g in gi], gd["diff"][:2])))

    # FV5-START-SECOND-COPY: dragged onto another chart while the start runs, the second copy finds the lock taken (OnInit: ERROR 'another copy',
    # INIT_FAILED, then OnDeinit's stop line deinit=8, rebuilds=0); MetaTrader unloads it from its chart, the first copy goes on
    def sec(u):
        return [jl(u, "ERROR", "-", ("what", "another copy of ClaudeRobot runs on this terminal")),
                jl(u, "INIT", "-", ("deinit", 8), ("lines", 1), ("bars_fed", 0), ("rebuilds", 0), ("masked_XAUUSD", 0), ("masked_US100", 0),
                   ("masked_BTCUSD", 0), ("masked_ETHUSD", 0))]

    def with_second(ls, at, u):
        txt = ep(ls).splitlines()
        two = [f"2026.11.15 10:05:10.{k:03d}\tClaudeRobot (US100.r,M1)\t{x}" for k, x in enumerate(sec(u))]
        return "\n".join(txt[:at + 1] + two + txt[at + 1:]) + "\n"
    sc = {"after": start_go(base_dir, "second6_after", with_second(full, len(full) - 1, START_U + 180)),
          "inside": start_go(base_dir, "second6_inside", ep(full[:5] + sec(START_U + 30) + full[5:])),
          "inside_late": start_go(base_dir, "second6_inside_late", with_second(full, 4, START_U + 180))}
    bad = {k: (g["rc"], g["diff"][:2]) for k, g in sc.items()
           if g["rc"] != 0 or g["diff"] or "deuxieme copie" not in g["so"] or "ne pas relancer" not in g["so"] or "finit par l'arret" in g["so"]
           or "ABSENT : INIT" in g["so"] or "OK : READY ETHUSD" not in g["so"] or "deuxieme copie" not in g["verdict"]}
    chk("review6 FV5-START-SECOND-COPY: a second copy MetaTrader refused while the start runs (ERROR 'another copy', then its stop line deinit=8, "
        "from another chart), after the start's lines or inside them (in time order, or later lines pasted among them): the running start checked "
        "(OK, exit code 0), the refused copy said as information and in the verdict ('ne pas relancer'), never 'le collage finit par l'arret du "
        "robot' nor 'ABSENT : INIT'", lambda: (not bad, bad))
    g2 = start_go(base_dir, "second6_after_d2", with_second(start_lines(risk=D2), len(full) - 1, START_U + 180))
    chk("review6 FV5-START-SECOND-COPY: the same after a start with D2: D2 still flagged (exit code 1), the second copy information only (no "
        "DIFFERENT for it, no stop of the running start)",
        lambda: (g2["rc"] == 1 and any("D2" in x for x in g2["diff"]) and not any("another copy" in x or "arret du robot" in x for x in g2["diff"])
                 and "deuxieme copie" in g2["so"], g2["diff"][:4]))
    alone = start_go(base_dir, "second6_alone", ep(sec(START_U)))
    before = start_go(base_dir, "second6_before", ep(sec(START_U - 120) + full))
    chk("review6 control FV5-START-SECOND-COPY: the refused copy alone (no running start in the paste): the guide's advice (another chart), INIT "
        "absent, exit code 1; a start refused for another copy, then the right start (the old copy removed): information, exit code 0",
        lambda: (alone["rc"] == 1 and any("autre graphique" in x for x in alone["diff"]) and "ABSENT : INIT" in alone["so"]
                 and before["rc"] == 0 and not before["diff"] and "INFO : demarrage 1" in before["so"], (alone["diff"][:2], before["diff"][:2])))
    chk("review6: no account word in any check_start output of these cases",
        lambda: (all(not g["leak"] for g in list(res.values()) + list(glued.values()) + list(gw.values()) + list(sc.values()) + gi
                     + [g, fz, gd, g2, alone, before]), None))


def test_review6_journal(lit):
    """review6, check_demo on journals of the user's November 2026 demo (story_journal): FV5-RH5-2-SAME-SETTINGS-RESTART (a D2 demo that MetaTrader
    restarted with the same settings; the same with the restart's daily file lost, without and with the Mac's Experts logs; control: D2 replaced
    by S7), FV5-RH5-7-LOST-FILE-COST (a lost daily file whose trades lost money: the balance difference is no cost), FV5-COPIE-MIDNIGHT (--copie
    a few minutes after the server's midnight), FV5-START-NUMBERING (start numbers after refused starts; a restart seen only in the Experts tab
    counted; the Experts INIT gives the build of a start whose INIT line the files lost)"""
    del lit
    base_dir = os.path.join(SCRATCH, "rv6j")

    def go(name, segs=None, trades=(), extra=(), prep=None, jdir=None, **kw):
        jdir = jdir or os.path.join(base_dir, "j_" + name, "ClaudeRobot")
        if not os.path.isdir(jdir) or not os.listdir(jdir):
            story_journal(jdir, segs, trades, **kw)
        if prep:
            prep(jdir)
        out = os.path.join(base_dir, "out_" + name)
        rc, so, se = run_tool("check_demo.py", ["--journals", os.path.dirname(jdir), "--out", out] + list(extra))
        rp = os.path.join(out, "report.json")
        r = json.load(open(rp)) if rc == 0 and os.path.exists(rp) else {}
        rt = os.path.join(out, "report_fr.txt")
        return {"rc": rc, "so": so, "se": se, "r": r, "an": r.get("anomalies", []), "jdir": jdir,
                "rtxt": open(rt, encoding="utf-8").read() if rc == 0 and os.path.exists(rt) else "",
                "txt": (outputs_text(out) if rc == 0 else "") + so + se}

    def drop(*names):
        def prep(jdir):
            for n in names:
                if os.path.exists(os.path.join(jdir, n)):
                    os.remove(os.path.join(jdir, n))
        return prep

    def line(g, head):
        return next((ln for ln in g["so"].splitlines() if ln.startswith(head)), "")
    S0, END = STORY_START, STORY_END
    tr = story_trades()
    # FV5-RH5-2-SAME-SETTINGS-RESTART: D2 in both starts, MetaTrader quit on Monday 22:00 server and opened again on Tuesday 08:00
    d2d2 = [{"at": S0, "to": srv("2026-11-16 22:00"), "deinit": 9, "risk": D2}, {"at": srv("2026-11-17 08:00"), "to": END, "risk": D2}]
    g = go("same", d2d2, tr)
    info = [ln for ln in g["so"].splitlines() if ln.startswith("Information")]
    chk("review6 FV5-RH5-2-SAME-SETTINGS-RESTART: a D2 demo restarted with the same settings: D2 flagged once, on the start in force (with the "
        "earlier start named), no 'remplace' information, no plan note, no separate anomaly for the first start's trades",
        lambda: (g["rc"] == 0 and sum(1 for a in g["an"] if "D2" in a) == 1 and any("D2" in a and "demarrage 2" in a and "demarrage 1" in a for a in g["an"])
                 and not any("remplace" in ln or "comptent aussi" in ln for ln in info) and not any("trade(s) reel(s)" in a for a in g["an"]),
                 (g["an"][:3], info)))
    gl = go("same_lost", d2d2, tr, prep=drop("20261117.log"))
    info = [ln for ln in gl["so"].splitlines() if ln.startswith("Information")]
    chk("review6 FV5-RH5-2-SAME-SETTINGS-RESTART: the same with the restart's daily file lost (no Experts logs): the settings in force unknown, the "
        "first start's D2 is an anomaly ('reglages du redemarrage inconnus', 'a verifier'), never 'remplace'",
        lambda: (gl["rc"] == 0 and any("D2" in a and "demarrage 1" in a and "inconnus" in a and "a verifier" in a for a in gl["an"])
                 and not any("remplace" in ln for ln in info) and not any("remplace" in a for a in gl["an"]) and "inconnus" in line(gl, "Reglages en vigueur"),
                 (gl["an"][:3], info)))
    jfull = os.path.join(base_dir, "j_same_src", "ClaudeRobot")
    story_journal(jfull, d2d2, tr)
    logs = printed_files(os.path.join(base_dir, "logs_same"), jfull)
    gp = go("same_lost_p", d2d2, tr, prep=drop("20261117.log"), extra=[x for p in logs for x in ("--printed", p)])
    info = [ln for ln in gp["so"].splitlines() if ln.startswith("Information")]
    chk("review6 FV5-RH5-2-SAME-SETTINGS-RESTART: the same with the Mac's Experts logs: the restart's D2 flagged naming the Experts log, the first "
        "start's 'a verifier' settled, no 'remplace' information, no separate anomaly for the first start's trades",
        lambda: (gp["rc"] == 0 and any("D2" in a and "onglet Experts" in a for a in gp["an"]) and not any("a verifier" in a for a in gp["an"])
                 and not any("remplace" in ln for ln in info) and not any("trade(s) reel(s)" in a for a in gp["an"]), (gp["an"][:4], info)))
    gr = go("replaced", [{"at": S0, "to": srv("2026-11-16 22:00"), "deinit": 9, "risk": D2}, {"at": srv("2026-11-17 08:00"), "to": END}], tr)
    info = [ln for ln in gr["so"].splitlines() if ln.startswith("Information")]
    chk("review6 control FV5-RH5-2-SAME-SETTINGS-RESTART: a D2 start replaced by an S7 start (other settings): the 'remplace' information and "
        "the anomaly naming the first start's real trades are still there",
        lambda: (gr["rc"] == 0 and any("demarrage 1" in ln and "D2" in ln and "remplace par le demarrage 2" in ln for ln in info)
                 and any("trade(s) reel(s) faits par le demarrage 1 remplace" in a for a in gr["an"]), (gr["an"][:3], info)))
    # FV5-RH5-7-LOST-FILE-COST: Tuesday's file lost, with two trades that lost money in it
    b_px, e_px = A5_PX["BTCUSD"], A5_PX["ETHUSD"]
    lost_tr = tr[:2] + [story_trade("BKB", srv("2026-11-17 09:00"), 70009603, xpx=b_px * 0.995, close=b_px * 0.995),
                        story_trade("BKE", srv("2026-11-17 14:00"), 70009604, side=-1, xpx=e_px * 1.006, close=e_px * 1.006)]
    gm = go("lost_cost", [{"at": S0, "to": END}], lost_tr, prep=drop("20261117.log"))
    sl = line(gm, "Solde")
    chk("review6 FV5-RH5-7-LOST-FILE-COST: one daily file lost (two losing trades inside, no position without an exit price): the money line says "
        "an unexplained difference between the balance and the trades with the missing day, never costs ('frais hors des prix', 'cout de')",
        lambda: (gm["rc"] == 0 and "difference non expliquee" in sl and "journal manquant" in sl and "frais hors des prix" not in sl
                 and "cout de" not in sl and not ((gm["r"].get("fills") or {}).get("money_estimate") or {}).get("positions_exit_unknown"), sl))
    gk = go("lost_cost_all", [{"at": S0, "to": END}], lost_tr)
    chk("review6 control FV5-RH5-7-LOST-FILE-COST: the same journal with every file: a complete estimate, said as costs ('frais hors des prix')",
        lambda: (gk["rc"] == 0 and "frais hors des prix" in line(gk, "Solde") and "difference non expliquee" not in line(gk, "Solde"),
                 line(gk, "Solde")))
    # FV5-COPIE-MIDNIGHT: the Wednesday copy, the robot running; --copie given a few minutes after the server's midnight (23:00 in Paris)
    gc = go("copie_2305", [{"at": S0, "to": None}], tr, extra=("--copie", "2026-11-18 23:05"))
    chk("review6 FV5-COPIE-MIDNIGHT: --copie at 23:05 (Paris, five minutes after the server's midnight) on a journal that reaches Wednesday: no "
        "missing file, an information line saying that nothing is missing if the files were zipped before 23:00",
        lambda: (gc["rc"] == 0 and gc["an"] == [] and any(ln.startswith("Information") and "zippes avant 23:00" in ln and "20261119.log" in ln
                                                         for ln in gc["so"].splitlines()), (gc["an"][:2], gc["so"][-700:])))
    gc1 = go("copie_2230", [{"at": S0, "to": None}], tr, extra=("--copie", "2026-11-18 22:30"))
    gc2 = go("copie_0130", [{"at": S0, "to": None}], tr, extra=("--copie", "2026-11-19 01:30"))
    chk("review6 control FV5-COPIE-MIDNIGHT: --copie at 22:30 (before midnight): nothing abnormal; at 01:30 the next night (beyond the hour): "
        "20261119.log named as missing",
        lambda: (gc1["rc"] == 0 and gc1["an"] == [] and gc2["rc"] == 0 and any("20261119.log" in a for a in gc2["an"]), (gc1["an"][:2], gc2["an"][:2])))
    # FV5-START-NUMBERING: the numbers the reader sees are the starts that ran
    g1 = go("num_refused", [{"at": S0 - 240, "refused": [ERR_COMMA]}, {"at": S0, "to": END}], tr)
    g2 = go("num_refused2", [{"at": S0 - 600, "refused": [ERR_COMMA]}, {"at": S0 - 300, "refused": list(ERR_K1T)}, {"at": S0, "to": END}], tr)
    g3 = go("num_d2_refused_s7", [{"at": S0 - 600, "to": S0 - 65, "deinit": 5, "risk": D2, "k1t": ""}, {"at": S0 - 60, "refused": [ERR_COMMA]},
                                  {"at": S0 + 180, "to": END}], tr)
    chk("review6 FV5-START-NUMBERING: after refused starts the start in force is numbered among the starts that ran (1 after one or two refused "
        "starts; 2 after a D2 start, a refused one and the S7 one, which replaced 'demarrage 1'), as the headline counts them",
        lambda: (g1["rc"] == g2["rc"] == g3["rc"] == 0 and "1 demarrage(s)" in line(g1, "Journal") and "Reglages en vigueur (demarrage 1," in g1["so"]
                 and "Reglages en vigueur (demarrage 1," in g2["so"] and "2 demarrage(s)" in line(g3, "Journal")
                 and "Reglages en vigueur (demarrage 2," in g3["so"] and "remplace par le demarrage 2" in g3["so"]
                 and "Demarrages : 2 (redemarrages : 1) ; demarrage(s) refuse(s) par le robot : 1" in g3["rtxt"],
                 (line(g1, "Reglages"), line(g2, "Reglages"), line(g3, "Reglages"), line(g3, "Journal"))))
    segs_r = [{"at": S0, "to": srv("2026-11-17 15:00"), "deinit": 1}, {"at": srv("2026-11-17 15:12"), "to": END, "risk": D2}]
    jr = os.path.join(base_dir, "j_num_day_src", "ClaudeRobot")
    story_journal(jr, segs_r, tr)
    logs_r = printed_files(os.path.join(base_dir, "logs_num_day"), jr)
    gx = go("num_experts_restart", segs_r, tr, prep=drop("20261117.log"), extra=[x for p in logs_r for x in ("--printed", p)])
    chk("review6 FV5-START-NUMBERING: a restart seen only in the Experts tab (its day's file lost) counts in the headline and in report_fr.txt's "
        "restarts, with the number 'Reglages en vigueur' gives it",
        lambda: (gx["rc"] == 0 and "2 demarrage(s)" in line(gx, "Journal") and "Reglages en vigueur (demarrage 2," in gx["so"]
                 and "Demarrages : 2 (redemarrages : 1)" in gx["rtxt"], (line(gx, "Journal"), line(gx, "Reglages"),
                                                                         [ln for ln in gx["rtxt"].splitlines() if ln.startswith("Demarrages")])))
    jsrc = os.path.join(base_dir, "j_num_fill_src", "ClaudeRobot")
    md_journal(jsrc, ("restart_d2",))
    logs_f = printed_files(os.path.join(base_dir, "logs_num_fill"), jsrc)
    jf = os.path.join(base_dir, "j_num_fill", "ClaudeRobot")
    md_journal(jf, ("restart_d2",))
    os.remove(os.path.join(jf, "20211122.log"))
    gf = go("num_fill", jdir=jf, extra=[x for p in logs_f for x in ("--printed", p)])
    chk("review6 FV5-START-NUMBERING: a restart whose INIT line the files lost, given by the Experts tab: its build shown in the headline (no "
        "'build ?'), and report_fr.txt counts the restart",
        lambda: (gf["rc"] == 0 and "2 demarrage(s)" in line(gf, "Journal") and "build ?" not in line(gf, "Journal")
                 and "Demarrages : 2 (redemarrages : 1)" in gf["rtxt"], (line(gf, "Journal"),
                                                                         [ln for ln in gf["rtxt"].splitlines() if ln.startswith("Demarrages")])))
    chk("review6 control: no account word in any check_demo output of these cases (the journals plant none; a guard)",
        lambda: (all(not leak_free(x["txt"]) for x in (g, gl, gp, gr, gm, gk, gc, gc1, gc2, g1, g2, g3, gx, gf)), None))


SECOND_ERR = "another copy of ClaudeRobot runs on this terminal"     # dist/ClaudeRobot.mq5 OnInit: GrdLockTake failed, INIT_FAILED


def second_pair(u):
    """the two lines of a second copy MetaTrader refused (OnInit: ERROR 'another copy', INIT_FAILED; OnDeinit: the stop line deinit=8, rebuilds=0)"""
    return [jl(u, "ERROR", "-", ("what", SECOND_ERR)),
            jl(u, "INIT", "-", ("deinit", 8), ("lines", 1), ("bars_fed", 0), ("rebuilds", 0), ("masked_XAUUSD", 0), ("masked_US100", 0),
               ("masked_BTCUSD", 0), ("masked_ETHUSD", 0))]


def insert_printed(path, hhmmss, lines, src="ClaudeRobot (US100.r,M1)"):
    """robot lines put into one of MetaTrader's Experts logs (printed_files' UTF-16 format) at the local time hhmmss, after the source of
    another chart: what the Experts tab shows of a copy the daily file never holds (a second copy refused while the first one runs)"""
    rows = open(path, "rb").read().decode("utf-16").splitlines()
    new = [f"GH\t0\t{hhmmss}.{500 + k:03d}\t{src}\t{ln}" for k, ln in enumerate(lines)]
    at = next((k for k, r in enumerate(rows) if r.split("\t")[2] > hhmmss + ".500"), len(rows))
    rows = rows[:at] + new + rows[at:]
    with open(path, "wb") as f:
        f.write(b"\xff\xfe" + ("\r\n".join(rows) + "\r\n").encode("utf-16-le"))


def test_review6b_start(lit):
    """review6b (the sixth round's second pass), check_start.py: FV6-START-MISSED-GLUED-DIGITS (the login typed right after a MISSED line whose
    reason is 'refused_<rc>' or 'code<k>' was printed with the reason), FV6-START-LONE-SECOND-COPY (a paste holding only the second copy's lines
    told the user to remove the robot that runs and said it had not started), FV6-START-SEMICOLON-CUT (a risk table typed with the ';' the robot
    accepts at its end glued the user's next chat line onto the PLAN line), FV6-START-PROSE-CR-PIPE ('CR|' in the user's own words read as a cut
    robot line)"""
    del lit
    base_dir = os.path.join(SCRATCH, "rv6bs")
    os.makedirs(base_dir, exist_ok=True)
    full = start_lines()
    init, selftest, plan_src, plan = full[:4]

    def ep(ls):
        return experts_paste(ls, account=False)
    # FV6-START-MISSED-GLUED-DIGITS: MISSED is written by FolMissedTxt with the reason as the line's last field (refused_<rc>, FolIntentStep;
    # code<k>, SizSkipName): the login typed right after the line, without a space, lands in the reason
    mu = START_U + 600
    m_ref = jl(mu, "MISSED", "BKB", ("oid", (START_U - 3600) * 100 + C.SLEEVE_ID["BKB"]), ("stamp", START_U - 3600), ("reason", "refused_10006"))
    m_code = jl(mu, "MISSED", "ORX", ("oid", (START_U - 3600) * 100 + C.SLEEVE_ID["ORX"]), ("stamp", START_U - 3600), ("reason", "code19"))
    gm = {"refused_glued": start_go(base_dir, "missed6b_refused_glued", ep(full + [m_ref + FAKE_LOGIN])),
          "code_glued": start_go(base_dir, "missed6b_code_glued", ep(full + [m_code + FAKE_LOGIN])),
          "refused_glued_bare": start_go(base_dir, "missed6b_refused_glued_bare", "\n".join(full + [m_ref + FAKE_LOGIN]) + "\n")}
    bad = {k: (g["rc"], g["diff"][-2:], g["leak"]) for k, g in gm.items()
           if g["rc"] != 1 or g["leak"] or re.search(r"refused_10006\d|code19\d", g["so"])
           or not any("MISSED" in x and "recopier" in x for x in g["diff"])}
    chk("review6b FV6-START-MISSED-GLUED-DIGITS: the right start, then a MISSED line (reason refused_10006 or code19) with the login glued right "
        "after it: the login never printed (nor any digit glued to the reason), the MISSED line to be copied again, exit code 1",
        lambda: (not bad, bad))
    gc = {"alone": start_go(base_dir, "missed6b_refused_alone", ep(full + [m_ref])),
          "login_next": start_go(base_dir, "missed6b_refused_login_next", ep(full + [m_ref]) + FAKE_LOGIN + "\n")}
    gsp = start_go(base_dir, "missed6b_refused_login_space", ep(full + [m_ref + " " + FAKE_LOGIN]))
    chk("review6b control FV6-START-MISSED-GLUED-DIGITS: the MISSED refused_10006 line alone or with the login on the next line: 'MISSED BKB "
        "reason=refused_10006' said (a broker refusal: exit code 1); the login after a space: the line unreadable, to be copied again; the login "
        "never printed",
        lambda: (all(g["rc"] == 1 and not g["leak"] and any("MISSED BKB reason=refused_10006" in x for x in g["diff"]) for g in gc.values())
                 and gsp["rc"] == 1 and not gsp["leak"] and any("MISSED" in x and "recopier" in x for x in gsp["diff"]),
                 ({k: (g["rc"], g["diff"][-1:], g["leak"]) for k, g in gc.items()}, gsp["diff"][-1:])))

    # FV6-START-LONE-SECOND-COPY: GrdLockTake refuses only a lock another copy refreshed less than 10 s ago (CR_GRD_LOCK_STALE_MS): 'another
    # copy' means a copy runs on this terminal; OnInit returns INIT_FAILED and MetaTrader unloads the new copy (MQL5 documentation, OnInit)
    su = START_U + 900
    later = [jl(su - 60, "MISSED", "BKB", ("oid", (START_U - 3600) * 100 + C.SLEEVE_ID["BKB"]), ("stamp", START_U - 3600), ("reason", "late")),
             jl(su - 30, "NOTREADY", "XAUUSD", ("why", "holes"), ("bars", 1000), ("raw", 1000), ("first", su - 86400), ("last", su - 60), ("masked", 0),
                ("holes", 1))]
    after = [jl(su + 60, "READY", "XAUUSD", ("bars", 1000), ("raw", 1000), ("first", su - 86400), ("last", su), ("masked", 0), ("holes", 0),
                ("depth_days", C.DEPTH_DAYS["XAUUSD"]))]
    lone = {"pair": start_go(base_dir, "lone6b_pair", ep(second_pair(su))),
            "error_only": start_go(base_dir, "lone6b_error_only", ep(second_pair(su)[:1])),
            "running_lines_before": start_go(base_dir, "lone6b_running_before", ep(later + second_pair(su))),
            "running_lines_after": start_go(base_dir, "lone6b_running_after", ep(second_pair(su) + after))}

    def lone_bad(g):
        so = g["so"]
        return (g["rc"] != 1 or "n'a pas demarre" in so or "l'enlever de l'autre graphique" in so or "relance le robot" in so
                or not ("ne rien enlever" in so or "ne pas relancer" in so) or "INIT" not in g["verdict"] or "qui tourne" not in g["verdict"])
    bad = {k: (g["rc"], g["diff"][:2], g["verdict"]) for k, g in lone.items() if lone_bad(g)}
    chk("review6b FV6-START-LONE-SECOND-COPY: a paste holding only the refused second copy's lines (ERROR 'another copy' and its stop line deinit=8, "
        "or the ERROR alone, or with lines of the copy that runs before or after them but not its INIT line): never 'le robot n'a pas demarre' "
        "nor 'l'enlever de l'autre graphique'; the copy that runs is left alone ('ne rien enlever' or 'ne pas relancer') and the verdict asks for "
        "the INIT line of the copy that runs; exit code 1 (nothing checked)", lambda: (not bad, bad))
    gb = start_go(base_dir, "lone6b_before_relaunch", ep(second_pair(START_U - 120) + full))
    gs = start_go(base_dir, "lone6b_after_start", ep(full + second_pair(START_U + 300)))
    chk("review6b control FV6-START-LONE-SECOND-COPY: a copy refused for another copy, then the right start (the old copy removed, the robot "
        "relaunched): exit code 0; the right start then a second copy refused: exit code 0 with 'deuxieme copie'",
        lambda: (gb["rc"] == 0 and not gb["diff"] and gs["rc"] == 0 and "deuxieme copie" in gs["so"], (gb["diff"][:2], gs["diff"][:2])))

    # FV6-START-SEMICOLON-CUT: SizParseTable accepts one ';' at the end of InpRiskTable and MainInitLine and MainWait write the table back as typed
    s7s = S7 + ";"
    semi = start_lines(risk=s7s)
    up_plan = semi[:4]
    gsemi = {k: start_go(base_dir, "semi6b_" + k, ep(up_plan) + t + "\n") for k, t in (("time", "17:43"), ("login", FAKE_LOGIN), ("zero", "0"))}
    bad = {k: (g["rc"], g["diff"][:2], g["leak"]) for k, g in gsemi.items()
           if g["rc"] != 0 or g["diff"] or g["leak"] or "recollee" in g["so"] or "OK : PLAN state=ok" not in g["so"]}
    chk("review6b FV6-START-SEMICOLON-CUT: a start whose risk table was typed with the ';' the robot accepts at its end (INIT and PLAN write it "
        "back), up to PLAN, then a time, the login or '0' alone on the next line: never glued onto the PLAN line, every check OK, exit code 0, the "
        "login never printed", lambda: (not bad, bad))
    pre = "2026.11.15 10:02:14.111\tClaudeRobot (XAUUSD.r,M1)\t"
    cut_at = plan.index("20000:0.7")
    gw = start_go(base_dir, "semi6b_wrap_after_semicolon", ep(full[:3]) + pre + plan[:cut_at] + "\n" + plan[cut_at:] + "\n")
    gall = start_go(base_dir, "semi6b_whole_start", ep(semi) + "merci\n")
    chk("review6b control FV6-START-SEMICOLON-CUT: a PLAN line the chat wrapped right after a ';' of its table ('...10000:1.4;' then "
        "'20000:0.7'): put back together, exit code 0; the whole start with the trailing ';' then 'merci': exit code 0",
        lambda: (gw["rc"] == 0 and not gw["diff"] and "recollee" in gw["so"] and gall["rc"] == 0 and not gall["diff"],
                 (gw["diff"][:2], gall["diff"][:2])))

    # FV6-START-PROSE-CR-PIPE: the guide itself says 'Les lignes du robot commencent par CR|'
    prose = {"before": start_go(base_dir, "prose6b_before", "Voici les lignes qui commencent par CR| :\n" + ep(full)),
             "after": start_go(base_dir, "prose6b_after", ep(full) + "J'ai bien les lignes CR| et les 4 READY\n"),
             "backticks": start_go(base_dir, "prose6b_backticks", "Les lignes `CR|` :\n" + ep(full)),
             "end_of_line": start_go(base_dir, "prose6b_end_of_line", "les lignes CR|\n" + ep(full))}
    bad = {k: (g["rc"], g["diff"][:2]) for k, g in prose.items() if g["rc"] != 0 or g["diff"] or "OK : READY ETHUSD" not in g["so"]}
    chk("review6b FV6-START-PROSE-CR-PIPE: the right start with one line of the user's own words holding 'CR|' (before, after, in backticks, at "
        "the end of the line): read as other text, every check OK, exit code 0", lambda: (not bad, bad))
    gcut = start_go(base_dir, "prose6b_control_cut", ep(full) + pre + full[5][:30] + "\n")
    gsplit = start_go(base_dir, "prose6b_control_split", ep(full[:5]) + pre + "CR|\n" + full[5][3:] + "\n" + ep(full[6:]))
    gfrag = start_go(base_dir, "prose6b_control_fragment", ep(full) + pre + "CR|\n" + full[5][3:40] + "|holes=0|depth_days=120\n")
    chk("review6b control FV6-START-PROSE-CR-PIPE: a robot line cut short ('CR|<stamp>|READY|...') is still 'ligne coupee' (exit code 1); a robot "
        "line split right after 'CR|' is put back together (exit code 0); a piece of a robot line after a lone 'CR|' is still flagged (exit code 1)",
        lambda: (gcut["rc"] == 1 and any("ligne coupee" in x for x in gcut["diff"]) and gsplit["rc"] == 0 and not gsplit["diff"]
                 and gfrag["rc"] == 1 and any("recopier" in x for x in gfrag["diff"]),
                 (gcut["diff"][:1], gsplit["diff"][:1], gfrag["diff"][:1])))
    chk("review6b: no account word in any check_start output of these cases",
        lambda: (all(not g["leak"] for g in list(gm.values()) + list(gc.values()) + list(lone.values()) + list(gsemi.values())
                     + list(prose.values()) + [gsp, gb, gs, gw, gall, gcut, gsplit, gfrag]), None))


def test_review6b_journal(lit):
    """review6b, check_demo on story_journal's November 2026 journals: FV6-DEMO-UNKNOWN-RESTART-ADVICE (D2 on Saturday, a restart on Tuesday
    inside the lost daily file, S7 from Wednesday: the anomaly asked for the running robot's INIT line, which says nothing of that restart, and
    the Mac's Experts logs did not settle it), FV6-DEMO-PRINTED-SECOND-COPY (a second copy refused while the robot runs, seen in the Experts
    logs only: 'lignes imprimees differentes'; in a lost day's Experts log its stop line read as a stop of the robot)"""
    del lit
    base_dir = os.path.join(SCRATCH, "rv6bj")

    def go(name, jdir, extra=()):
        out = os.path.join(base_dir, "out_" + name)
        rc, so, se = run_tool("check_demo.py", ["--journals", os.path.dirname(jdir), "--out", out] + list(extra))
        rp = os.path.join(out, "report.json")
        r = json.load(open(rp)) if rc == 0 and os.path.exists(rp) else {}
        rt = os.path.join(out, "report_fr.txt")
        return {"rc": rc, "so": so, "se": se, "r": r, "an": r.get("anomalies", []),
                "info": [ln for ln in so.splitlines() if ln.startswith("Information")],
                "rtxt": open(rt, encoding="utf-8").read() if rc == 0 and os.path.exists(rt) else "",
                "txt": (outputs_text(out) if rc == 0 else "") + so + se}

    def journal(name, segs, lost=(), logs=False):
        """the journal folder (its lost files removed) and, with logs=True, the Mac's Experts logs written from the whole journal"""
        src = os.path.join(base_dir, "src_" + name, "ClaudeRobot")
        story_journal(src, segs, tr)
        pl = printed_files(os.path.join(base_dir, "logs_" + name), src) if logs else []
        jdir = os.path.join(base_dir, "j_" + name, "ClaudeRobot")
        shutil.copytree(src, jdir)
        for n in lost:
            os.remove(os.path.join(jdir, n))
        return jdir, pl
    tr = story_trades()
    S0, END = STORY_START, STORY_END
    MON22, TUE08, WED08 = srv("2026-11-16 22:00"), srv("2026-11-17 08:00"), srv("2026-11-18 08:00")
    # FV6-DEMO-UNKNOWN-RESTART-ADVICE: D2, a MetaTrader restart on Tuesday inside the lost 20261117.log (D2 kept), the user's F7 to S7 on Wednesday
    segs = [{"at": S0, "to": MON22, "deinit": 9, "risk": D2}, {"at": TUE08, "to": WED08 - 60, "deinit": 5, "risk": D2}, {"at": WED08, "to": END}]
    j2, logs2 = journal("lost_restart", segs, lost=("20261117.log",), logs=True)
    g = go("lost_restart", j2)
    a1 = next((a for a in g["an"] if "demarrage 1" in a and "D2" in a and "inconnus" in a), "")
    chk("review6b FV6-DEMO-UNKNOWN-RESTART-ADVICE: D2 on Saturday, a restart inside the lost Tuesday file, S7 in force from Wednesday: the anomaly "
        "on the first start's D2 asks for the Mac's Experts logs of that day (MQL5/Logs, --printed), never for the INIT line of the robot that runs "
        "(it is the S7 start, which says nothing of the lost restart); the D2 start's real trades are named",
        lambda: (g["rc"] == 0 and a1 != "" and "robot qui tourne" not in a1 and "--printed" in a1
                 and any("trade(s) reel(s)" in a and "demarrage 1" in a for a in g["an"]), (g["an"][:4])))
    gp = go("lost_restart_p", j2, [x for p in logs2 for x in ("--printed", p)])
    chk("review6b FV6-DEMO-UNKNOWN-RESTART-ADVICE: the same with the Mac's Experts logs (the restart's INIT line, D2, is in Tuesday's log): the "
        "restart's settings are known, no 'reglages du redemarrage inconnus' nor 'a verifier' left (the missing-file anomaly reads the same with "
        "and without the logs, review5); the D2 run of starts 1 and 2 is replaced by the S7 start 3 (information) and its real trades are an anomaly",
        lambda: (gp["rc"] == 0 and not any("redemarrage inconnus" in a or "a verifier" in a for a in gp["an"])
                 and any("demarrages 1 et 2" in x and "remplaces par le demarrage 3" in x for x in gp["info"])
                 and any("trade(s) reel(s)" in a and "demarrages 1 et 2" in a for a in gp["an"]), (gp["an"][:4], gp["info"])))
    segs_b = [{"at": S0, "to": MON22, "deinit": 9, "risk": D2}, {"at": TUE08, "to": WED08 - 60, "deinit": 5}, {"at": WED08, "to": END}]
    j2b, logs2b = journal("lost_restart_s7", segs_b, lost=("20261117.log",), logs=True)
    gb = go("lost_restart_s7_p", j2b, [x for p in logs2b for x in ("--printed", p)])
    chk("review6b FV6-DEMO-UNKNOWN-RESTART-ADVICE: the restart in the lost file was the S7 one (the Experts logs give its INIT line): start 1's "
        "D2 is replaced by start 2 (information), no 'reglages du redemarrage inconnus' nor 'a verifier' left, start 1's real trades named",
        lambda: (gb["rc"] == 0 and not any("redemarrage inconnus" in a or "a verifier" in a for a in gb["an"])
                 and any("demarrage 1" in x and "remplace par le demarrage 2" in x for x in gb["info"])
                 and any("trade(s) reel(s)" in a and "demarrage 1" in a for a in gb["an"]), (gb["an"][:4], gb["info"])))
    jl10, _ = journal("lost_restart_in_force", [{"at": S0, "to": MON22, "deinit": 9, "risk": D2}, {"at": TUE08, "to": END}],
                      lost=("20261117.log",))
    gf = go("lost_restart_in_force", jl10)
    chk("review6b control FV6-DEMO-UNKNOWN-RESTART-ADVICE: the restart in the lost file is the start in force (no later start): the anomaly still "
        "asks for the INIT line of the robot that runs ('a verifier')",
        lambda: (gf["rc"] == 0 and any("demarrage 1" in a and "inconnus" in a and "robot qui tourne" in a for a in gf["an"]), gf["an"][:3]))

    # FV6-DEMO-PRINTED-SECOND-COPY: the second copy's lines never reach the daily file (the first copy holds it, FILE_SHARE_READ): Experts only
    jc, logs_c = journal("second", [{"at": S0, "to": END}], logs=True)
    g0 = go("second_control", jc, [x for p in logs_c for x in ("--printed", p)])
    insert_printed(next(p for p in logs_c if p.endswith("20261116.log")), "10:00:00", second_pair(C.srv_to_utc(srv("2026-11-16 11:00"))))
    gs = go("second", jc, [x for p in logs_c for x in ("--printed", p)])
    chk("review6b FV6-DEMO-PRINTED-SECOND-COPY: a clean S7 demo whose Monday Experts log holds a second copy MetaTrader refused (ERROR 'another "
        "copy', then its stop line deinit=8, from a US100 chart): no 'lignes imprimees differentes' anomaly, the refused copy said as information "
        "on stdout and in report_fr.txt",
        lambda: (gs["rc"] == 0 and not any("lignes imprimees" in a for a in gs["an"]) and any("deuxieme copie" in x for x in gs["info"])
                 and "deuxieme copie" in gs["rtxt"], (gs["an"][:3], gs["info"])))
    jd, logs_d = journal("second_lost", [{"at": S0, "to": END}], lost=("20261117.log",), logs=True)
    insert_printed(next(p for p in logs_d if p.endswith("20261117.log")), "10:00:00", second_pair(C.srv_to_utc(srv("2026-11-17 11:00"))))
    gd = go("second_lost", jd, [x for p in logs_d for x in ("--printed", p)])
    chk("review6b FV6-DEMO-PRINTED-SECOND-COPY: the same pair in the Experts log of a lost day: never 'montre un arret' of the robot that day (its "
        "stop line is the refused copy's), the refused copy said as information",
        lambda: (gd["rc"] == 0 and not any("montre un arret" in x for x in gd["info"]) and any("deuxieme copie" in x for x in gd["info"]), gd["info"]))
    chk("review6b control FV6-DEMO-PRINTED-SECOND-COPY: the same demo and Experts logs without the refused copy: nothing abnormal in the printed "
        "lines, no 'deuxieme copie'",
        lambda: (g0["rc"] == 0 and not any("lignes imprimees" in a for a in g0["an"]) and "deuxieme copie" not in g0["so"], (g0["an"][:2])))
    chk("review6b control: no account word in any check_demo output of these cases (the journals plant none; a guard)",
        lambda: (all(not leak_free(x["txt"]) for x in (g, gp, gb, gf, g0, gs, gd)), None))


def test_review5_journal(lit):
    """review5, journal and files cases: FV4b-1 (the Mac's Experts logs cut by the Mac's local date with a lost daily file: a middle day, the
    restart day, two days, the last file with and without --bars; across the weeks when Paris and New York change clocks on different dates),
    FV4b-2 (two logs of the same name from two folders), FV4b-4 (the balance check's real thresholds), MAC-ZIP (the Finder zip's __MACOSX folder
    and AppleDouble files in every input of both tools)"""
    base_dir = os.path.join(SCRATCH, "rv5j")

    def go(name, variant=(), extra=(), prep=None, mini=None, jdir=None):
        jdir = jdir or os.path.join(base_dir, "j_" + name, "ClaudeRobot")
        info = None
        if not os.path.isdir(jdir) or not os.listdir(jdir):
            info = mini_journal(jdir, **mini) if mini is not None else md_journal(jdir, variant)
        if prep:
            prep(jdir, info)
        out = os.path.join(base_dir, "out_" + name)
        rc, so, se = run_tool("check_demo.py", ["--journals", os.path.dirname(jdir), "--out", out] + list(extra))
        rp = os.path.join(out, "report.json")
        r = json.load(open(rp)) if rc == 0 and os.path.exists(rp) else {}
        rt = os.path.join(out, "report_fr.txt")
        return {"rc": rc, "so": so, "se": se, "r": r, "rtxt": open(rt, encoding="utf-8").read() if rc == 0 and os.path.exists(rt) else "",
                "jdir": jdir, "an": r.get("anomalies", []), "pr": r.get("printed") or {}, "out": out,
                "txt": (outputs_text(out) if rc == 0 else "") + so + se}

    def drop(*names):
        def prep(jdir, info):
            for n in names:
                os.remove(os.path.join(jdir, n))
        return prep

    def printed(paths):
        return [x for p in paths for x in ("--printed", p)]

    def lost_ok(g, expect, alone=None, names=()):
        """the printed logs are the same copy, add no anomaly and no VPS note: the anomalies are the journal's own about the lost file, the
        same as without --printed (alone): the missing file first, then only what the journal says because of it (a position whose exit
        lines were in it names that file)"""
        an = g["an"]
        same_as_alone = alone is None or an == alone["an"]
        return (g["rc"] == 0 and g["pr"].get("kind") == "meme copie" and g["pr"].get("same_copy_as_files") is True and "VPS" not in g["so"]
                and an and expect in an[0] and same_as_alone and (alone is not None or len(an) == 1)
                and all(any(n in a for n in names) for a in an[1:]),
                (g["rc"], g["pr"].get("kind"), g["pr"].get("files_kind"), an[:4], (alone or {}).get("an", [])[:4], g["se"][-300:]))
    # the Mac's clock (review5): Paris and New York change clocks on different dates
    chk("review5 FV4b-1 (clocks): the Mac's local time is Paris time: server - 1 h in November 2026, server - 2 h between the US and the EU "
        "changes (20 March and 28 October 2026), the EU changes at 01:00 UTC on the last Sundays of March and October",
        lambda: (C.paris_of_utc(START_U) == C.utc_to_srv(START_U) - 3600
                 and all(C.paris_of_utc(C.srv_to_utc(srv(x))) == srv(x) - 7200 for x in ("2026-03-20 12:00", "2026-10-28 12:00"))
                 and C.paris_of_utc(calendar.timegm((2026, 3, 29, 0, 59, 0))) - calendar.timegm((2026, 3, 29, 0, 59, 0)) == 3600
                 and C.paris_of_utc(calendar.timegm((2026, 3, 29, 1, 0, 0))) - calendar.timegm((2026, 3, 29, 1, 0, 0)) == 7200
                 and C.paris_of_utc(calendar.timegm((2026, 10, 25, 0, 59, 0))) - calendar.timegm((2026, 10, 25, 0, 59, 0)) == 7200
                 and C.paris_of_utc(calendar.timegm((2026, 10, 25, 1, 0, 0))) - calendar.timegm((2026, 10, 25, 1, 0, 0)) == 3600
                 and all(C.paris_of_utc(u) == paris_wall(u) for u in range(calendar.timegm((2021, 1, 1, 0, 0, 0)),
                                                                           calendar.timegm((2027, 1, 1, 0, 0, 0)), 7 * 3600 + 17)), None))
    # FV4b-1: a daily journal file lost, the Mac's Experts logs (named by its local date) kept
    src = go("fv1_src")
    logs = printed_files(os.path.join(base_dir, "logs_fv1"), src["jdir"])
    g = go("fv1_clean", extra=printed(logs), jdir=src["jdir"])
    chk("review5 control FV4b-1: the whole journal and the Mac's Experts logs cut by its local date (a day's last hour in the next file): the "
        "same copy, nothing abnormal", lambda: (g["rc"] == 0 and g["pr"].get("kind") == "meme copie" and g["an"] == [], (g["pr"].get("files_kind"), g["an"][:3])))
    for case, names, expect in (("middle", ("20211123.log",), "fichier(s) du jour manquant(s) : 20211123.log"),
                                ("two_days", ("20211123.log", "20211124.log"), "fichier(s) du jour manquant(s) : 20211123.log, 20211124.log"),
                                ("last", ("20211125.log",), "fin du journal sans ligne d'arret")):
        g = go("fv1_" + case, prep=drop(*names), extra=printed(logs))
        ga = go("fv1_" + case + "_alone", prep=drop(*names))
        chk(f"review5 FV4b-1: the journal file(s) {', '.join(names)} lost, the Mac's Experts logs of every day given: the same copy, no VPS note, "
            "only the missing-file anomaly (the same anomalies as without --printed)", lambda: lost_ok(g, expect, ga, names))
    g0 = go("fv1_restart_src", ("restart",))
    logs_r = printed_files(os.path.join(base_dir, "logs_fv1_restart"), g0["jdir"])
    g = go("fv1_restart", ("restart",), prep=drop("20211122.log"), extra=printed(logs_r))
    ga = go("fv1_restart_alone", ("restart",), prep=drop("20211122.log"))
    chk("review5 FV4b-1: the restart day's journal file lost (its INIT in the Mac's Experts log only): the same copy, no VPS note, the same "
        "anomalies as without --printed: the missing file named (the restart was in it) and the position whose exit lines were in it",
        lambda: lost_ok(g, "fichier(s) du jour manquant(s) : 20211122.log", ga, ("20211122.log",)))
    chk("review5 FV4b-1: a lost restart day is named by the journal itself (the DAY line of that day sits in the next file, after a stop): one "
        "missing-file anomaly that says the restart was in it, no 'ligne de demarrage perdue', no 'sans fichier manquant connu'",
        lambda: (ga["rc"] == 0 and any("20211122.log" in a and "redemarrage" in a for a in ga["an"]) and not any("demarrage perdue" in a for a in ga["an"])
                 and not any("sans fichier manquant connu" in a for a in ga["an"]) and all("20211122.log" in a for a in ga["an"]), ga["an"][:4]))
    rdir = os.path.join(base_dir, "rel_fv1")
    make_releve(rdir, lit, "good", m1_from="2021-11-15 00:00", m1_to="2021-11-26 12:00",
                tweak=lambda fi: [f.__setitem__("tick_time", srv("2021-11-26 10:59")) for f, _ in fi.values()])
    g = go("fv1_last_bars", prep=drop("20211125.log"), extra=printed(logs) + ["--bars", rdir, "--no-replay"])
    chk("review5 FV4b-1: the last journal file lost, with ReleveFP's files run the day after (--bars): the same copy, no VPS note, only the "
        "missing-file anomaly naming 20211125.log", lambda: lost_ok(g, "fichier du jour manquant probable : 20211125.log", None, ("20211125.log",)))
    for name, a, z, lost in (("fv1_october", "2021-10-27 08:00", "2021-11-09 10:00", "20211102.log"),
                             ("fv1_march", "2021-03-10 08:00", "2021-03-31 10:00", "20210316.log")):
        gs = go(name + "_src", mini={"start": srv(a), "end": srv(z)})
        lg = printed_files(os.path.join(base_dir, "logs_" + name), gs["jdir"])
        gc = go(name + "_all", extra=printed(lg), jdir=gs["jdir"])
        g = go(name, prep=drop(lost), extra=printed(lg), mini={"start": srv(a), "end": srv(z)})
        chk(f"review5 FV4b-1 (clocks): {a[:10]} to {z[:10]}, across the weeks when Paris is server - 2 h: the Mac's logs are the same copy with "
            f"nothing abnormal, and with {lost} lost only the missing-file anomaly",
            lambda: (gc["rc"] == 0 and gc["an"] == [] and gc["pr"].get("kind") == "meme copie" and lost_ok(g, lost)[0],
                     (gc["an"][:3], gc["pr"].get("files_kind"), lost_ok(g, lost)[1])))
    # FV4b-2: two logs of the same name from two folders (the Mac's and a VPS's), and the terminal's Journal log named like an Experts log
    mac = printed_files(os.path.join(base_dir, "fv2", "Logs"), src["jdir"])
    day = "20211123.log"
    mine = [ln for ln in lines_of_utf16(os.path.join(base_dir, "fv2", "Logs", day))]
    vps_lines = [init_line(U("2021-11-23 01:00"), vps=1)] + [ln.replace("|f=1.0000000000000000e+00|", "|f=5.0000000000000000e-01|")
                                                             for ln in mine if "|INIT|" not in ln]
    os.makedirs(os.path.join(base_dir, "fv2", "vps"), exist_ok=True)
    utf16_printed(os.path.join(base_dir, "fv2", "vps", day), vps_lines, vps=True)
    # the terminal's Journal log under the Mac user's folder, the same name as an Experts log one level up too: named with the folders it
    # takes to tell them apart, the user folder masked
    jdir_u = os.path.join(base_dir, "fv2", "Users", FAKE_USER, "Logs")
    os.makedirs(jdir_u, exist_ok=True)
    jt = os.path.join(jdir_u, "20211124.log")
    with open(jt, "wb") as f:
        f.write(b"\xff\xfe" + ("\r\n".join([f"QK\t0\t09:59:58.120\tNetwork\t'{FAKE_LOGIN}': authorized on {FAKE_SERVER} through Access Point EU 2",
                                            "PO\t0\t10:00:00.410\tTerminal\tFP Markets MT5 Terminal x64 build 4620 started"]) + "\r\n").encode("utf-16-le"))
    g = go("fv2_two_folders", extra=printed(mac + [os.path.join(base_dir, "fv2", "vps", day), jt]), jdir=src["jdir"])
    fk = g["pr"].get("files_kind") or {}
    chk("review5 FV4b-2: the Mac's Logs/20211123.log and a VPS's vps/20211123.log are two files (named with their folder): the Mac's the same "
        "copy, the VPS's another copy", lambda: (g["rc"] == 0 and fk.get("Logs/" + day) == "same" and fk.get("vps/" + day) == "other", fk))
    chk("review5 FV4b-2: the terminal's Journal log Users/<user>/Logs/20211124.log (the same name as the Experts log of that day) is told "
        "apart by its folders in the anomaly, the user folder masked; the account in it never printed",
        lambda: (g["rc"] == 0 and any(f"{C.Scrubber.MASK}/Logs/20211124.log" in a and "aucune ligne du robot" in a for a in g["an"])
                 and fk.get("fv2/Logs/20211124.log") == "same" and leak_free(g["txt"]) == [],
                 ([a for a in g["an"] if "aucune" in a], sorted(fk)[:12], leak_free(g["txt"]))))
    # FV4b-4: the balance check's 'en plus' figure is the real threshold (the costs already seen counted)
    tr = [{"code": "GFP", "side": 1, "at": srv("2021-11-16 10:00"), "hold": 3600, "ppx": 1860.0, "stop": 1841.4, "fill": 1860.03,
           "quote": 1860.03 / (1 + 0.3e-4), "lots": 0.05, "ticket": 70005001, "xpx": 1862.0, "close": 1861.97},
          {"code": "ORX", "side": -1, "at": srv("2021-11-17 10:00"), "hold": 3600, "ppx": 1865.0, "stop": 1883.6, "fill": 1864.97,
           "quote": 1864.97 / (1 - 0.3e-4), "lots": 0.05, "ticket": 70005002, "xpx": 1863.0, "close": 1863.03},
          {"code": "N30", "side": 1, "at": srv("2021-11-18 16:00"), "hold": 3600, "ppx": 16300.0, "stop": 16200.0, "fill": 16300.3,
           "quote": 16300.3 / (1 + 0.2e-4), "lots": 0.5, "ticket": 70005003, "xpx": 16320.0, "close": 16319.7}]
    mini = {"start": srv("2021-11-15 08:00"), "end": srv("2021-11-24 10:00"), "trades": tr, "balance0": 600.0}
    g = go("fv4_base", mini=mini)
    m = re.search(r"ne se voit pas en dessous de ([0-9 ]+,\d\d) EUR en plus", g["rtxt"])
    th = float(m.group(1).replace(" ", "").replace(",", ".")) if m else None
    res = {}
    for k, eps in (("under", -0.05), ("over", 0.05)):
        gain = (th or 0.0) + eps
        res[k] = go(f"fv4_{k}", mini=dict(mini, extra=lambda pd, gain=gain: gain if pd >= srv("2021-11-20 00:00") else 0.0))
    chk("review5 FV4b-4: a hand gain 5 cents under the 'en plus' figure the report prints is not flagged, 5 cents over it is ('le solde a bouge')",
        lambda: (th is not None and th > 2.0 and "le solde a bouge" not in " | ".join(res["under"]["an"])
                 and "le solde a bouge" in " | ".join(res["over"]["an"]), (th, res["under"]["an"][:2], res["over"]["an"][:2])))
    # MAC-ZIP: the Finder zip's metadata in every input of both tools
    zfiles = {f"Files/ClaudeRobot/{n}": os.path.join(src["jdir"], n) for n in sorted(os.listdir(src["jdir"]))}
    zfiles.update({f"Logs/{os.path.basename(p)}": p for p in logs})
    zfiles.update({f"Files/claude/releve/{n}": os.path.join(rdir, n) for n in sorted(os.listdir(rdir))})
    plain = os.path.join(base_dir, "zip_plain")
    finder_zip_tree(plain, zfiles, macosx=False)
    os.remove(os.path.join(plain, ".DS_Store"))
    zroot = os.path.join(base_dir, "zip_finder")
    ad = finder_zip_tree(zroot, zfiles, macosx=True)
    beside = os.path.join(base_dir, "zip_beside")
    finder_zip_tree(beside, zfiles, macosx=False, beside=True)

    def run_tree(root, name, logs_as="files"):
        lg_dir = os.path.join(root, "Logs")
        if logs_as == "folder":
            pr = ["--printed", lg_dir]
        else:                                                           # what a find of every *.log gives, AppleDouble files included
            pr = printed(sorted(os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs if f.endswith(".log") and "Logs" in d))
        out = os.path.join(base_dir, "out_zip_" + name)
        rc, so, se = run_tool("check_demo.py", ["--journals", os.path.join(root, "Files"), "--bars", os.path.join(root, "Files", "claude", "releve"),
                                                "--no-replay", "--out", out] + pr)
        r = json.load(open(os.path.join(out, "report.json"))) if rc == 0 else {}
        return {"rc": rc, "so": so, "se": se, "an": r.get("anomalies", []), "pr": r.get("printed") or {},
                "leak": leak_free((outputs_text(out) if rc == 0 else "") + so + se)}
    p0 = run_tree(plain, "plain")
    p1 = run_tree(zroot, "finder")
    p2 = run_tree(beside, "beside")
    p3 = run_tree(zroot, "folder", logs_as="folder")
    chk("review5 control MAC-ZIP: the tree of the zip without any macOS file: no information about macOS files",
        lambda: (p0["rc"] == 0 and "macOS" not in p0["so"], (p0["rc"], p0["se"][-300:])))
    chk("review5 MAC-ZIP: the Finder zip extracted with its __MACOSX folder, every .log of it given with --printed (AppleDouble '._*.log' "
        "included): the same anomalies as without them (never 'journal du terminal ?'), one information line 'fichiers de macOS ignores'",
        lambda: (len(ad) > 10 and p1["rc"] == 0 and p1["an"] == p0["an"] and p1["so"].count("de macOS ignore") == 1
                 and "._" in p1["so"] and not any("._" in a for a in p1["an"]) and p1["leak"] == [] and p0["leak"] == [],
                 (p1["an"][:3], p0["an"][:3], p1["so"][-600:], p1["leak"])))
    chk("review5 MAC-ZIP: AppleDouble files beside the files (no __MACOSX: a copy by tar or onto a FAT key) in --journals, --bars and --printed: "
        "the same anomalies as without them, one information line", lambda: (p2["rc"] == 0 and p2["an"] == p0["an"]
                                                                            and p2["so"].count("de macOS ignore") == 1, (p2["an"][:3], p2["so"][-500:])))
    chk("review5 MAC-ZIP: --printed given the Logs folder of the extracted zip: its .log files read, the AppleDouble ones left out, the same "
        "result as the files one by one", lambda: (p3["rc"] == 0 and p3["an"] == p0["an"] and p3["pr"].get("kind") == p0["pr"].get("kind")
                                                   and p3["pr"].get("lines") == p0["pr"].get("lines"), (p3["rc"], p3["se"][-300:], p3["an"][:3])))
    t1 = {}
    for name, root in (("plain", plain), ("finder", zroot), ("beside", beside)):
        folder = os.path.join(root, "Files", "claude", "releve")
        if name == "finder":                                            # the files of the releve folder zipped by the Finder: __MACOSX beside them
            folder = os.path.join(base_dir, "zip_releve_files")
            finder_zip_tree(folder, {n: os.path.join(rdir, n) for n in sorted(os.listdir(rdir))})
        out = os.path.join(base_dir, "out_t1zip_" + name)
        rc, so, se = run_tool("read_mac_files.py", [folder, "--out", out])
        s = json.load(open(os.path.join(out, "summary.json"))) if rc == 0 else {}
        t1[name] = {"rc": rc, "so": so, "checks": [(c["market"], c["item"], c["status"]) for c in s.get("checks", [])], "problems": s.get("problems"),
                    "leak": leak_free((outputs_text(out) if rc == 0 else "") + so + se)}
    chk("review5 MAC-ZIP (tool 1): ReleveFP's folder with a __MACOSX folder inside it, or AppleDouble files beside its files: the same checks and "
        "reading problems as without them, one information line 'fichiers de macOS ignores'",
        lambda: (all(t1[k]["rc"] == 0 for k in t1) and t1["finder"]["checks"] == t1["plain"]["checks"] == t1["beside"]["checks"]
                 and t1["finder"]["problems"] == t1["plain"]["problems"] == t1["beside"]["problems"]
                 and t1["finder"]["so"].count("de macOS ignore") == 1 and t1["beside"]["so"].count("de macOS ignore") == 1
                 and "macOS" not in t1["plain"]["so"] and not any(v["leak"] for v in t1.values()),
                 {k: (v["rc"], v["so"][-300:], v["leak"]) for k, v in t1.items()}))


def lines_of_utf16(path):
    """the robot lines of a MetaTrader log (UTF-16): the text from 'CR|' on"""
    out = []
    for ln in open(path, "rb").read().decode("utf-16").splitlines():
        k = ln.find("CR|")
        if k >= 0:
            out.append(ln[k:])
    return out


def shift_lines(lines, delta):
    """robot lines moved in time by delta seconds (their own stamp only: the rest is the robot's text)"""
    return [re.sub(r"^CR\|(\d+)\|", lambda m: f"CR|{int(m.group(1)) + delta}|", ln) for ln in lines]


def test_review5_replay(lit):
    """review5 with the robot built in the harness: START on the release file's own start lines (the user's two values typed: S7 and
    InpK1T = 2026:417.23813245421888; k1t as DoubleToString(-16) writes it), moved to the user's start; FV4b-3 (a US100 row of the releve
    dropped for its price: the later differences of the sleeves reading US100 marked)"""
    t0 = time.time()
    jd, _, _ = harness_live("live5_start", HIST4, {"MOCK_INPUT_InpTrade": "true", "MOCK_INPUT_InpK1T": "2026:417.23813245421888",
                                                    "MOCK_BALANCE": "10000"}, frm=GO4, to=GO4 + 4 * 3600)
    cr = os.path.join(jd, "ClaudeRobot")
    live = [ln for fn in sorted(os.listdir(cr)) for ln in lines_of(os.path.join(cr, fn)) if ln.startswith("CR|") and "|rp=1" not in ln]
    k_init = next((k for k, ln in enumerate(live) if "|INIT|-|build=" in ln), None)
    ready = [k for k, ln in enumerate(live) if "|READY|" in ln]
    real = live[k_init:max(ready) + 1] if k_init is not None and len(ready) >= 4 else []
    delta = START_U - int(real[0].split("|")[1]) if real else 0
    p = os.path.join(SCRATCH, "rv5_real_start.txt")
    with open(p, "w", encoding="utf-8") as f:
        f.write(experts_paste(shift_lines(real, delta)))
    rc, so, se = run_tool("check_start.py", [p])
    chk("review5 START (harness): the release file's own start lines (INIT with k1t as the robot writes InpK1T = 2026:417.23813245421888, "
        "SELFTEST, PLAN, REBUILD, the four READY), moved to 15 November 2026 and pasted from the Experts tab: every check OK, exit code 0",
        lambda: (bool(real) and rc == 0 and "DIFFERENT" not in so and "OK : seuil K1 de 2026" in so and "OK : READY US100" in so
                 and leak_free(so) == [], (len(real), real[:1], so[-1500:], se[-400:])))
    # FV4b-3: a US100 row of the terminal's bars with a negative low (dropped: the replay has no bar there): every later difference of the
    # sleeves reading US100 (N30, OC4, NQB) is marked, and the replay anomaly says it
    clean = os.path.join(SCRATCH, "live4_clean", "files")
    if not os.path.isdir(clean):
        clean, _, _ = harness_live("live4_clean", HIST4, {"MOCK_INPUT_InpTrade": "true", "MOCK_INPUT_InpPlanStart": str(GO4),
                                                          "MOCK_BALANCE": "1000"}, frm=GO4, to=END4)
    rel = releve_replay("rel5_us100", lit, RUN4)
    p = os.path.join(rel, "r1_US100.csv")
    ls_ = lines_of(p)
    bad_t = srv("2021-10-27 15:31")
    k = next(i for i, ln in enumerate(ls_) if ln.startswith(f"{bad_t},"))
    f = ls_[k].split(",")
    f[3] = "-" + f[3]
    ls_[k] = ",".join(f)
    write(p, "\n".join(ls_) + "\n")
    out = os.path.join(SCRATCH, "out5_us100")
    rc, so, se = run_tool("check_demo.py", ["--journals", clean, "--bars", rel, "--out", out])
    r = json.load(open(os.path.join(out, "report.json"))) if rc == 0 else {}
    dif = (r.get("replay") or {}).get("comparison", {}).get("differences", [])
    us = [d for d in dif if "US100" in C.READS_OF_CODE.get(d["code"], []) and (d.get("t_utc") or 0) >= C.srv_to_utc(bad_t)]
    late = [d for d in us if d["code"] == "NQB" and d["t_utc"] > C.srv_to_utc(bad_t) + 2 * 3600]
    an = " | ".join(r.get("anomalies", []))
    chk("review5 FV4b-3: a US100 row with a negative low dropped from the replay: every difference of N30, OC4 and NQB from that bar on carries "
        "the hint (NQB ones hours later too) and the replay anomaly names the file",
        lambda: (rc == 0 and late and all(d.get("near_bad_bar") for d in us) and "r1_US100.csv" in an and "lisent un marche" in an,
                 (rc, len(dif), len(us), len(late), [(d["code"], d["when"], bool(d.get("near_bad_bar"))) for d in us[:6]], an[:600], se[-300:])))
    print(f"   (review5 replay tests {time.time() - t0:.0f} s)")


# ---------------------------------------------------------------------------------------------- review7: the account's deals (ReleveFP 1.11)
MOCK_DEAL_COLS = ["ticket", "order", "position", "time", "time_msc", "symbol", "type", "entry", "reason", "magic", "volume", "price", "sl", "tp",
                  "commission", "swap", "fee", "profit", "comment", "external_id"]
MOCK_POS_COLS = ["ticket", "identifier", "time", "time_msc", "symbol", "type", "magic", "volume", "price_open", "sl", "tp", "price_current",
                 "swap", "profit", "comment", "external_id"]
DEALS_SYMS_EXTRA = "XAUUSD.r:2:0.01,US100.r:2:0.1,BTCUSD.r:2:0.01,ETHUSD.r:2:0.01"   # the harness's .r names, as FP's terminal knows them
REL7 = {}
# ReleveFP 1.11's names and headers kept here too (not read from demo_common), so that this file runs against the tools as they were before
# review7 (the before/after comparison): there the deals tests fail, the controls pass
T_DEALS, T_POSITIONS = "deals.csv", "positions.csv"
T_DEALS_HEADER = "time,time_msc,ticket,order,position,symbol,type,entry,reason,magic,volume,price,sl,tp,commission,swap,fee,profit"
T_POSITIONS_HEADER = "ticket,identifier,time,time_msc,symbol,type,magic,volume,price_open,sl,tp,price_current,swap,profit"
T_DEAL_TYPES = ("DEAL_TYPE_BUY", "DEAL_TYPE_SELL", "DEAL_TYPE_BALANCE", "DEAL_TYPE_CREDIT", "DEAL_TYPE_CHARGE", "DEAL_TYPE_CORRECTION",
                "DEAL_TYPE_BONUS", "DEAL_TYPE_COMMISSION", "DEAL_TYPE_COMMISSION_DAILY", "DEAL_TYPE_COMMISSION_MONTHLY",
                "DEAL_TYPE_COMMISSION_AGENT_DAILY", "DEAL_TYPE_COMMISSION_AGENT_MONTHLY", "DEAL_TYPE_INTEREST", "DEAL_TYPE_BUY_CANCELED",
                "DEAL_TYPE_SELL_CANCELED", "DEAL_DIVIDEND", "DEAL_DIVIDEND_FRANKED", "DEAL_TAX")
T_DEAL_REASONS = ("DEAL_REASON_CLIENT", "DEAL_REASON_MOBILE", "DEAL_REASON_WEB", "DEAL_REASON_EXPERT", "DEAL_REASON_SL", "DEAL_REASON_TP",
                  "DEAL_REASON_SO", "DEAL_REASON_ROLLOVER", "DEAL_REASON_VMARGIN", "DEAL_REASON_SPLIT", "DEAL_REASON_CORPORATE_ACTION")


def t_base(sym):
    """the robot's market of a broker symbol (XAUUSD.r -> XAUUSD), None for another"""
    return next((b for b in C.ROBOT_BASES if str(sym or "").startswith(b)), None)


def t_read(path):
    """a file's text, '' when it does not exist (ReleveFP 1.10 writes no deals.csv)"""
    try:
        return open(path, errors="replace").read()
    except OSError:
        return ""


def t_rows(path):
    """deals.csv or positions.csv as dicts of strings ([] without the file): the tests read ReleveFP's files on their own"""
    import csv
    try:
        with open(path, newline="") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def guarded(fn, *args):
    """a group of tests that never stops the run: an exception (the tools before review7 lack its functions) is one FAIL with its name"""
    try:
        fn(*args)
    except Exception as e:                                              # noqa: BLE001
        check(f"deals: {fn.__name__} stopped ({e.__class__.__name__}: tools without review7?)", False, str(e)[:300])


def mock_deal(ticket, order, position, t, sym, typ, entry, reason, magic, vol, px, sl=0.0, tp=0.0, comm=0.0, swap=0.0, fee=0.0, profit=0.0,
              comment="", ext="", msc=None):
    """one deal of the MetaTrader imitation's account (releve_mock MOCK_DEALS_FILE): type, entry and reason are the positions of the
    documentation's lists (demo_common.DEAL_TYPES ...)"""
    return {"ticket": ticket, "order": order, "position": position, "time": int(t), "time_msc": int(t) * 1000 if msc is None else msc,
            "symbol": sym, "type": typ, "entry": entry, "reason": reason, "magic": magic, "volume": vol, "price": px, "sl": sl, "tp": tp,
            "commission": comm, "swap": swap, "fee": fee, "profit": profit, "comment": comment.replace(",", " "), "external_id": ext.replace(",", " ")}


def mock_csv(path, rows, cols):
    with open(path, "w") as f:
        f.write(",".join(cols) + "\n")
        for r in rows:
            f.write(",".join(repr(r[c]) if isinstance(r[c], float) else str(r[c]) for c in cols) + "\n")


def releve_binary():
    """ReleveFP.mq5 translated by lab/live_ai/check/to_cpp.py and built against the demo copy of the MT5 imitation (releve_mock), once"""
    if "exe" in REL7:
        return REL7["exe"]
    d = os.path.join(SCRATCH, "rv7_build")
    os.makedirs(d, exist_ok=True)
    cpp = os.path.join(d, "releve.cpp")
    r = subprocess.run([sys.executable, "-I", os.path.join(C.LAB, "live_ai", "check", "to_cpp.py"), os.path.join(MQL5, "ReleveFP.mq5"), cpp],
                       capture_output=True, text=True)
    with open(os.path.join(d, "run.cpp"), "w") as f:
        f.write('#include "mock_mt5.h"\n#include "releve.cpp"\nint main() { OnStart(); return 0; }\n')
    b = subprocess.run(["g++", "-std=c++17", "-O1", "-w", "-I", os.path.join(HERE, "releve_mock"), "-I", d, os.path.join(d, "run.cpp"), "-o",
                        os.path.join(d, "run")], capture_output=True, text=True)
    REL7["exe"] = os.path.join(d, "run") if (r.returncode == 0 and b.returncode == 0) else None
    REL7["err"] = (r.stderr[-300:], b.stderr[-800:])
    return REL7["exe"]


def releve_run_deals(name, deals, positions, now_srv, env=None, exe=None):
    """ReleveFP 1.11 itself run on an account whose deals and open positions are given (releve_mock MOCK_DEALS_FILE, MOCK_POSITIONS_FILE):
    the folder claude/releve it wrote (its deals.csv, positions.csv and fini.txt; its m1, r1 and fiches files are the imitation's own); exe:
    another build (review8: the first 1.11 rebuilt)"""
    exe = exe or releve_binary()
    d = os.path.join(SCRATCH, name)
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(os.path.join(d, "F"))
    mock_csv(os.path.join(d, "mk_deals.csv"), deals, MOCK_DEAL_COLS)
    mock_csv(os.path.join(d, "mk_positions.csv"), positions, MOCK_POS_COLS)
    e = dict(os.environ, MOCK_FILES=os.path.join(d, "F"), MOCK_NOW=str(now_srv), MOCK_DEALS_FILE=os.path.join(d, "mk_deals.csv"),
             MOCK_POSITIONS_FILE=os.path.join(d, "mk_positions.csv"), MOCK_SYMS_EXTRA=DEALS_SYMS_EXTRA, **{k: str(v) for k, v in (env or {}).items()})
    if exe:
        subprocess.run([exe], env=e, capture_output=True, text=True, timeout=600)
    return os.path.join(d, "F", "claude", "releve")


FINI_DEALS_KEYS = ("positions", "positions_heure", "deals", "deals_du", "deals_au", "erreur_deals")


def merge_deals(rel_dir, run_dir, out_dir):
    """a releve folder of the tests (releve_replay, make_releve) with what ReleveFP 1.11 wrote about the account (run_dir): deals.csv,
    positions.csv and fini.txt's six new keys; version=1.11 and no server line, as 1.11 writes fini.txt"""
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    shutil.copytree(rel_dir, out_dir)
    for f in (T_DEALS, T_POSITIONS):
        if os.path.exists(os.path.join(run_dir, f)):
            shutil.copy(os.path.join(run_dir, f), os.path.join(out_dir, f))
    run_fini = dict(ln.split("=", 1) for ln in open(os.path.join(run_dir, "fini.txt")).read().splitlines() if "=" in ln) \
        if os.path.exists(os.path.join(run_dir, "fini.txt")) else {}
    lines = [ln for ln in open(os.path.join(out_dir, "fini.txt")).read().splitlines() if not ln.startswith("server=")]
    lines = ["version=1.11" if ln.startswith("version=") else ln for ln in lines]
    k = next((i for i, ln in enumerate(lines) if ln.startswith("stopped=")), len(lines))
    lines[k:k] = [f"{key}={run_fini[key]}" for key in FINI_DEALS_KEYS if key in run_fini]
    write(os.path.join(out_dir, "fini.txt"), "\n".join(lines) + "\n")
    return out_dir


def harness_history(files, deposit=None, deposit_srv=None, hand_magic=777, plant=True, end_srv=None):
    """the harness's own account as MetaTrader's history holds it (check/mock_replay.h keeps it in _mock/deals.csv and state.txt): every deal
    with its time, price, commission, swap and profit; a deposit first, as a demo account's history starts (the harness starts from
    MOCK_BALANCE without one); each deal's stop (DEAL_SL: the order's stop for an opening deal, the position's stop at its close, from the
    journal's FILL and SLMOD lines); the harness's hand trades (magic 777) with MetaTrader's magic 0; the positions open at the end (state.txt,
    current price from the last bar); comments and external ids holding the account's planted server, name and login (ReleveFP must drop them)"""
    import pandas as pd
    deals = pd.read_csv(os.path.join(files, "_mock", "deals.csv"), keep_default_na=False, float_precision="round_trip")
    rows, _ = C.read_journal_files(C.journal_paths(files))
    lv = C.live(rows)
    fill_sl = {r["ticket"]: r["sl"] for r in lv if r["ev"] == "FILL" and r.get("ticket")}
    slm = {}
    for r in lv:
        if r["ev"] == "SLMOD" and r.get("ok") == 1 and r.get("ticket"):
            slm.setdefault(r["ticket"], []).append((C.utc_to_srv(r["utc"]), r["to"]))

    def stop_at(pos, t_srv):
        last = fill_sl.get(pos, 0.0)
        for u, lvl in slm.get(pos, []):
            if u <= t_srv:
                last = lvl
        return last
    out = []
    if deposit:
        out.append(mock_deal(39000001, 0, 0, deposit_srv, "", 2, 0, 0, 0, 0.0, 0.0, profit=float(deposit),
                             comment=("Depot " + FAKE_NAME) if plant else "", ext=FAKE_LOGIN if plant else ""))
    for r in deals.itertuples():
        typ, pos = int(r.type), int(r.position)
        magic = 0 if int(r.magic) == hand_magic else int(r.magic)
        sl = 0.0
        if typ in (0, 1) and pos:
            sl = fill_sl.get(pos, 0.0) if int(r.entry) == 0 else stop_at(pos, int(r.time))
        out.append(mock_deal(int(r.deal), int(r.order), pos, int(r.time), str(r.symbol), typ, int(r.entry), int(r.reason), magic, float(r.volume),
                             float(r.price), sl=sl, comm=float(r.commission), swap=float(r.swap), profit=float(r.profit),
                             comment=f"{FAKE_SERVER} {r.comment}" if plant else "", ext=f"X{FAKE_LOGIN}" if plant else ""))
    poss = []
    st = open(os.path.join(files, "_mock", "state.txt")).read().splitlines()
    bars = {}
    for ln in st:
        if not ln.startswith("pos "):
            continue
        p = ln.split()
        tk, sym, typ, vol, po, sl, tp, mg, tm = int(p[1]), p[2], int(p[3]), float(p[4]), float(p[5]), float(p[6]), float(p[7]), int(p[8]), int(p[9])
        b = t_base(sym)
        cur = po
        bf = os.path.join(os.path.dirname(files), "bars", f"{sym}.bin")
        if b and os.path.exists(bf):
            if sym not in bars:
                bars[sym] = read_bin(bf)
            dg, rec = bars[sym]
            rr = rec[rec["t"] <= (end_srv or int(rec["t"][-1]))]
            if len(rr):
                cur = (int(rr["c"][-1]) + (int(rr["s"][-1]) if typ == 1 else 0)) / 10 ** dg
        units = 100.0 if b == "XAUUSD" else 1.0
        poss.append({"ticket": tk, "identifier": tk, "time": tm, "time_msc": tm * 1000 + 1, "symbol": sym, "type": typ, "magic": 0 if mg == hand_magic else mg,
                     "volume": vol, "price_open": po, "sl": sl, "tp": tp, "price_current": cur, "swap": 0.0,
                     "profit": round((1 if typ == 0 else -1) * (cur - po) * vol * units * 0.89, 2),
                     "comment": FAKE_NAME if plant else "", "external_id": FAKE_LOGIN if plant else ""})
    return out, poss


def shift_balances(jdir, from_srv, delta):
    """a journal copy whose balance moved by delta EUR at server time from_srv (a deal added or changed in the account's history): every DAY
    line stamped after it gets delta on its balance and equity"""
    for f in sorted(os.listdir(jdir)):
        p = os.path.join(jdir, f)

        def fn(lines):
            out = []
            for ln in lines:
                if "|DAY|" in ln and C.utc_to_srv(int(ln.split("|")[1])) > from_srv:
                    ln = re.sub(r"\|balance=([-0-9.e+]+)", lambda m: f"|balance={float(m.group(1)) + delta!r}", ln)
                    ln = re.sub(r"\|equity=([-0-9.e+]+)", lambda m: f"|equity={float(m.group(1)) + delta!r}", ln)
                out.append(ln)
            return out
        edit_lines(p, fn)


def story_history(trades, balance0=1000.0, opened=STORY_OPENED, plant=True):
    """the account's history of a story_journal demo: the opening deposit, then each trade's opening deal at its FILL line (a + 1 s) and its
    closing deal at its CLOSE line (or the broker's stop of 'booked'), with the commission the story's balance books (gold: h a side) and the
    result of its prices; positions of 'open_at_copy' trades stay open (no closing deal)"""
    out = [mock_deal(1000001, 0, 0, opened, "", 2, 0, 0, 0, 0.0, 0.0, profit=balance0, comment=("Depot " + FAKE_NAME) if plant else "")]
    n = 1000002
    for t in trades:
        b = C.SYM_OF_CODE[t["code"]]
        kk, h = MINI_K[b], MINI_H[b]
        side, lots, tk = t["side"], t["lots"], t["ticket"]
        magic = 20261200 + C.SLEEVE_ID[t["code"]]
        out.append(mock_deal(n, tk, tk, t["at"] + 1, b + ".r", 0 if side > 0 else 1, 0, 3, magic, lots, t["fill"], sl=t["stop"],
                             comm=-round(h * lots * kk, 2) or 0.0, comment=f"CR {t['code']} {FAKE_LOGIN}" if plant else ""))
        n += 1
        if t.get("open_at_copy"):
            continue
        if t.get("booked"):
            tb, px = t["booked"]
            reason = 4
        else:
            tb, px = t["at"] + t["hold"] + 2 + 60 * t.get("refused_closes", (0, 0))[0], t["close"]
            reason = 3
        out.append(mock_deal(n, tk + 1, tk, tb, b + ".r", 1 if side > 0 else 0, 1, reason, magic, lots, px, sl=t["stop"],
                             comm=-round(h * lots * kk, 2) or 0.0, profit=round(side * (px - t["fill"]) * lots * kk, 2),
                             comment=f"[sl] {FAKE_SERVER}" if plant else ""))
        n += 1
    return out


def story_deals_case(name, trades=None, segs=None, copy=STORY_COPY, deals_fn=None, journal_fn=None, positions=None, extra_deals=(),
                     shifts=(), env=None, tool1=False, lit=None, args=()):
    """a story_journal demo (review5b) and its account's history written by ReleveFP 1.11 itself (releve_mock): deals_fn(deals) changes the
    history, extra_deals are added, shifts = [(server time, EUR)] move the DAY balances as those deals move the balance, journal_fn(jdir)
    edits the journal; then check_demo journal-only with --deals (and tool 1 on a releve folder holding the same deals when tool1)"""
    trades = story_trades() if trades is None else trades
    segs = [{"at": STORY_START, "to": STORY_END}] if segs is None else segs
    base = os.path.join(SCRATCH, "rv7_" + name)
    if os.path.isdir(base):
        shutil.rmtree(base)
    jdir = os.path.join(base, "j", "ClaudeRobot")
    story_journal(jdir, segs, trades, copy=copy)
    deals = story_history(trades) + list(extra_deals)
    if deals_fn:
        deals = deals_fn(deals)
    for t_srv, delta in shifts:
        shift_balances(jdir, t_srv, delta)
    if journal_fn:
        journal_fn(jdir)
    rel = releve_run_deals("rv7_rel_" + name, deals, positions or [], copy, env)
    out = os.path.join(base, "out")
    dpath = os.path.join(rel, T_DEALS)
    rc, so, se = run_tool("check_demo.py", ["--journals", os.path.dirname(jdir), "--deals", dpath, "--out", out] + list(args))
    r = json.load(open(os.path.join(out, "report.json"))) if rc == 0 and os.path.exists(os.path.join(out, "report.json")) else {}
    g = {"rc": rc, "so": so, "se": se, "r": r, "an": " | ".join(r.get("anomalies", [])), "d": (r.get("deals") or {}), "rel": rel, "out": out,
         "jdir": jdir, "txt": outputs_text(out) + so if rc == 0 else so + se,
         "pos": {p["ticket"]: p for p in (r.get("fills") or {}).get("positions", [])}, "m": (r.get("fills") or {}).get("money_estimate") or {}}
    if tool1 and lit is not None:
        g["t1"] = tool1_on_deals(base, rel, lit)
    return g


def tool1_on_deals(base, rel, lit, fini_edit_fn=None, drop=()):
    """read_mac_files on a releve folder of the tests (make_releve, ReleveFP 1.10's files) holding ReleveFP 1.11's deals.csv, positions.csv
    and fini keys from rel (merge_deals); drop: files left out"""
    src = os.path.join(base, "rel110")
    if not os.path.isdir(src):
        make_releve(src, lit, "good")
    folder = merge_deals(src, rel, os.path.join(base, "rel111"))
    for f in drop:
        if os.path.exists(os.path.join(folder, f)):
            os.remove(os.path.join(folder, f))
    if fini_edit_fn:
        lines = t_read(os.path.join(folder, "fini.txt")).splitlines()
        write(os.path.join(folder, "fini.txt"), "\n".join(fini_edit_fn(lines)) + "\n")
    out = os.path.join(base, "t1out")
    rc, so, se = run_tool("read_mac_files.py", [folder, "--out", out])
    s = json.load(open(os.path.join(out, "summary.json"))) if rc == 0 else {"checks": []}
    return {"rc": rc, "so": so, "se": se, "s": s, "ck": {(c["market"], c["item"]): c for c in s["checks"]}, "txt": (outputs_text(out) + so) if rc == 0 else se}


def test_review7_deals_quick(lit):
    """review7 (ReleveFP 1.11's deals.csv and positions.csv, the tools' reading of them) without the robot build: ReleveFP.mq5 itself through
    releve_mock on story_journal demos whose account history agrees with the journal by construction (story_history), then check_demo
    journal-only --deals and read_mac_files on the same history; faults: a trade by hand, a deposit, a robot position the journal does not
    know, a CLOSE line lost whose deal exists, a position still open at the run (and missing from positions.csv), the gold commission twice
    the lab's, a triple swap charged on a Wednesday (BTC, the lab triples Friday; gold, the lab triples Wednesday: no anomaly), a row that is not
    ReleveFP's (an extra field holding the holder's name), the account's planted words, a 1.10 folder without deals (behaviour unchanged)"""
    if not releve_binary():
        check("deals RELEVE-111: ReleveFP.mq5 1.11 translates and builds against releve_mock", False, REL7.get("err"))
        return
    src = lit["releve_src"]
    chk("deals RELEVE-111: ReleveFP.mq5 is version 1.11 (#property version, fini.txt version=1.11) and writes deals.csv and positions.csv "
        "with the documented header, never the server's name nor a comment or external id",
        lambda: (re.search(r'#property version\s+"1\.11"', src) is not None and '"version=1.11\\n"' in src and T_DEALS_HEADER in src
                 and T_POSITIONS_HEADER in src and "ACCOUNT_SERVER" not in src
                 and not any(p_ in "\n".join(ln.split("//")[0] for ln in src.splitlines()) for p_ in ("DEAL_COMMENT", "DEAL_EXTERNAL_ID",
                                                                                                         "POSITION_COMMENT", "POSITION_EXTERNAL_ID")),
                 re.search(r'#property version[^\n]*', src).group(0)))
    g = story_deals_case("clean", tool1=True, lit=lit)
    raw = t_read(os.path.join(g["rel"], T_DEALS))
    fini = dict(ln.split("=", 1) for ln in t_read(os.path.join(g["rel"], "fini.txt")).splitlines() if "=" in ln)
    chk("deals RELEVE-111: ReleveFP 1.11 (releve_mock) writes the story account's 9 deals oldest first with the 1.11 keys in fini.txt "
        "(deals=9, deals_du/deals_au, positions=0, erreur_deals=0) and no server line",
        lambda: (raw.splitlines()[:1] == [T_DEALS_HEADER] and len(raw.splitlines()) == 10 and fini.get("deals") == "9" and fini.get("positions") == "0"
                 and fini.get("erreur_deals") == "0" and fini.get("deals_du") == str(STORY_OPENED) and "server" not in fini
                 and fini.get("version") == "1.11", (raw.splitlines()[:3], fini)))
    chk("deals RELEVE-111: ReleveFP 1.11 writes the deals whose comments and external ids hold the holder's name, login and server: none of "
        "them in any file it writes", lambda: (len(raw.splitlines()) == 10 and os.path.exists(os.path.join(g["rel"], T_POSITIONS))
                                   and not any(w in open(os.path.join(g["rel"], f), errors="replace").read() for f in os.listdir(g["rel"])
                                   for w in ACCOUNT_WORDS), [f for f in os.listdir(g["rel"]) for w in ACCOUNT_WORDS
                                                             if w in open(os.path.join(g["rel"], f), errors="replace").read()]))
    chk("deals TOOL2: a clean story demo with its account history (--deals): every robot position matched, prices equal, the balance explained "
        "deal by deal ('le solde suit l'historique'), nothing abnormal",
        lambda: (g["rc"] == 0 and g["d"].get("matched") == 4 and not g["d"].get("price_disagreements") and g["m"].get("deals", {}).get("exact")
                 and g["r"].get("anomalies") == [] and "le solde suit l'historique au centime pres" in g["so"] and "Rien d'anormal" in g["so"],
                 (g["an"][:600], g["d"], g["se"][-500:])))
    t1 = g.get("t1") or {"ck": {}, "rc": 1, "txt": ""}
    st1 = lambda m_, i_: t1["ck"].get((m_, i_), {}).get("status")      # noqa: E731
    chk("deals TOOL1: read_mac_files reads deals.csv (period, robot positions per sleeve, the opening deposit as information) and the gold "
        "commission from the deals agrees with the lab's 6 points round trip; US100, BTC, ETH none",
        lambda: (t1["rc"] == 0 and st1("compte", "deals_file") == "OK" and st1("compte", "deals_robot") == "OK"
                 and "ORX 1" in str(t1["ck"].get(("compte", "deals_robot"), {}).get("broker")) and st1("compte", "deals_balance") == "INFO"
                 and st1("XAUUSD", "deals_commission") == "OK" and all(st1(b, "deals_commission") == "OK" for b in ("US100", "BTCUSD", "ETHUSD")),
                 ({k: v.get("status") for k, v in t1["ck"].items() if "deal" in k[1] or "position" in k[1]}, t1.get("se", "")[-300:])))
    # a trade by hand on BTC, a deposit during the demo, a robot position the journal does not know
    hand = [mock_deal(1000101, 9001, 9001, srv("2026-11-17 15:00"), "BTCUSD.r", 0, 0, 0, 0, 0.1, 57100.0, comment=FAKE_NAME),
            mock_deal(1000102, 9002, 9001, srv("2026-11-17 16:00"), "BTCUSD.r", 1, 1, 0, 0, 0.1, 57300.0, profit=17.2, comment=FAKE_SERVER)]
    g = story_deals_case("hand", extra_deals=hand, shifts=[(srv("2026-11-17 16:00"), 17.2)], tool1=True, lit=lit)
    chk("deals TOOL2: a trade by hand (magic 0) read from the history: an anomaly with its market, side, lots, times and result; the balance "
        "still explained (the hand trade is in the history)",
        lambda: (g["rc"] == 0 and "trade(s) a la main" in g["an"] and "BTCUSD.r achat de 0,10 lot" in g["an"] and "+17,20 EUR" in g["an"]
                 and g["m"].get("deals", {}).get("exact") and g["m"].get("deals", {}).get("hand_eur") == 17.2, (g["an"][:600], g["m"].get("deals"))))
    t1 = g["t1"]
    chk("deals TOOL1: the trade by hand is DIFFERENT with its result", lambda: (t1["ck"].get(("compte", "deals_hand"), {}).get("status") == "DIFFERENT"
                                                                              and "+17,20 EUR" in str(t1["ck"].get(("compte", "deals_hand"), {}).get("broker")),
                                                                              t1["ck"].get(("compte", "deals_hand"))))
    dep = [mock_deal(1000201, 0, 0, srv("2026-11-17 12:00"), "", 2, 0, 0, 0, 0.0, 0.0, profit=500.0, comment="Depot " + FAKE_NAME)]
    g = story_deals_case("deposit", extra_deals=dep, shifts=[(srv("2026-11-17 12:00"), 500.0)], tool1=True, lit=lit)
    chk("deals TOOL2: a deposit during the demo read from the history: an anomaly 'versement de 500,00 EUR' with its time, the balance explained",
        lambda: (g["rc"] == 0 and "versement de 500,00 EUR le 2026-11-17" in g["an"] and g["m"].get("deals", {}).get("exact")
                 and g["m"].get("deals", {}).get("payments_eur") == 500.0, (g["an"][:600], g["m"].get("deals"))))
    chk("deals TOOL1: a deposit after the robot's first trade is DIFFERENT (the opening deposit alone is information)",
        lambda: (g["t1"]["ck"].get(("compte", "deals_balance"), {}).get("status") == "DIFFERENT", g["t1"]["ck"].get(("compte", "deals_balance"))))
    unk = [mock_deal(1000301, 9101, 9101, srv("2026-11-17 11:00"), "BTCUSD.r", 0, 0, 3, 20261203, 0.05, 57000.0, sl=56430.0),
           mock_deal(1000302, 9102, 9101, srv("2026-11-17 11:30"), "BTCUSD.r", 1, 1, 3, 20261203, 0.05, 57116.28, profit=5.0)]
    g = story_deals_case("unknown", extra_deals=unk, shifts=[(srv("2026-11-17 11:30"), 5.0)])
    chk("deals TOOL2: a robot position of the history the journal does not know (no FILL or ADOPT of its ticket): named, with its sleeve and times",
        lambda: (g["rc"] == 0 and "position(s) du robot dans l'historique du compte que le journal ne connait pas" in g["an"] and "BKB" in g["an"]
                 and g["d"].get("unknown_to_journal") == 1, (g["an"][:600], g["d"].get("unknown_to_journal"))))
    # a CLOSE line lost whose deal exists
    lost = lambda jd: [edit_lines(os.path.join(jd, f), lambda ls: [ln for ln in ls if not ("|CLOSE|ORX|" in ln)]) for f in os.listdir(jd)]   # noqa: E731
    g = story_deals_case("closelost", journal_fn=lost)
    p0 = g["pos"].get(70009001, {})
    chk("deals TOOL2: a position whose CLOSE line is lost but whose deal exists: its exit is known from the history (price, the robot's close), "
        "the anomaly says what the journal lacked, and the money is explained (complete)",
        lambda: (g["rc"] == 0 and p0.get("exit_kind") == "ea_close_deal" and abs((p0.get("exit_real") or 0) - 1863.75) < 1e-6
                 and "connue par l'historique du compte" in g["an"] and "fermee par le robot le" in g["an"] and g["m"].get("complete") is True
                 and g["m"].get("deals", {}).get("exact"), (p0.get("exit_kind"), p0.get("exit_real"), g["an"][:500], g["m"].get("incomplete_why"))))
    # a position still open when ReleveFP ran: in positions.csv (normal), then missing from it (an anomaly)
    tr = story_trades() + [story_trade("N30", srv("2026-11-18 10:00"), 70009005, side=1, open_at_copy=True)]
    segs = [{"at": STORY_START, "to": None}]
    opn = {"ticket": 70009005, "identifier": 70009005, "time": srv("2026-11-18 10:00") + 1, "time_msc": (srv("2026-11-18 10:00") + 1) * 1000,
           "symbol": "US100.r", "type": 0, "magic": 20261201, "volume": 1.0, "price_open": 16300.0, "sl": 16137.0, "tp": 0.0,
           "price_current": 16310.0, "swap": 0.0, "profit": 8.6, "comment": FAKE_NAME, "external_id": FAKE_LOGIN}
    g = story_deals_case("open", trades=tr, segs=segs, positions=[opn])
    chk("deals TOOL2: a position still open when ReleveFP ran, listed in positions.csv: matched, no anomaly about it",
        lambda: (g["rc"] == 0 and g["pos"].get(70009005, {}).get("open_at_releve") and "positions.csv" not in g["an"]
                 and (g["d"].get("open_at_releve") or {}).get("journal_matched") == 1, (g["an"][:500], g["d"].get("open_at_releve"))))
    g = story_deals_case("open_missing", trades=tr, segs=segs, positions=[])
    chk("deals TOOL2: a position open at the run by the journal and the history but missing from positions.csv: an anomaly naming it",
        lambda: (g["rc"] == 0 and "absente(s) de positions.csv" in g["an"] and "N30 ticket 70009005" in g["an"], g["an"][:600]))
    # the gold commission twice the lab's (each side 0.26 EUR for 0.05 lot instead of 0.13)
    def comm2(ds):
        return [dict(d, commission=d["commission"] * 2) if d["symbol"] == "XAUUSD.r" else d for d in ds]
    t_in, t_out = srv("2026-11-16 10:00") + 1, srv("2026-11-16 11:00") + 2
    g = story_deals_case("comm2x", deals_fn=comm2, shifts=[(t_in, -0.13), (t_out, -0.13)], tool1=True, lit=lit)
    chk("deals TOOL2: a gold commission twice the lab's: an anomaly for XAUUSD (per lot and side against the model), the balance still explained",
        lambda: (g["rc"] == 0 and "commission XAUUSD au-dela du modele" in g["an"] and g["m"].get("deals", {}).get("exact"), g["an"][:600]))
    chk("deals TOOL1: the gold commission of the deals twice the lab's is DIFFERENT (12 points round trip against 6)",
        lambda: (g["t1"]["ck"].get(("XAUUSD", "deals_commission"), {}).get("status") == "DIFFERENT"
                 and "12" in str(g["t1"]["ck"].get(("XAUUSD", "deals_commission"), {}).get("broker")), g["t1"]["ck"].get(("XAUUSD", "deals_commission"))))
    # a triple swap charged on a Wednesday night: BTC (the lab triples Friday: an anomaly), gold (the lab triples Wednesday: no anomaly)
    copy2 = srv("2026-11-20 23:00")
    segs2 = [{"at": STORY_START, "to": srv("2026-11-20 22:30")}]
    tw_b = story_trade("BKB", srv("2026-11-18 20:00"), 70009006, hold=6 * 3600)
    tw_g = story_trade("ORX", srv("2026-11-18 21:00"), 70009007, hold=5 * 3600)
    day_b = 0.2 * tw_b["fill"] * tw_b["lots"] * MINI_K["BTCUSD"] / 360.0
    day_g = 0.055 * tw_g["fill"] * tw_g["lots"] * MINI_K["XAUUSD"] / 360.0

    def swap3(ds, which):
        out = []
        for d in ds:
            if d["position"] == which["ticket"] and d["entry"] == 1:
                d = dict(d, swap=-round(3 * (day_b if which is tw_b else day_g), 2))
            out.append(d)
        return out
    tc_b = tw_b["at"] + tw_b["hold"] + 2
    g = story_deals_case("swap3_btc", trades=story_trades() + [tw_b], segs=segs2, copy=copy2, deals_fn=lambda ds: swap3(ds, tw_b),
                         shifts=[(tc_b, -round(3 * day_b, 2))], tool1=True, lit=lit)
    chk("deals TOOL2: a triple swap charged on a Wednesday night on BTC (the lab triples on Friday): an anomaly 'swaps BTCUSD plus chers' naming "
        "the position and its one night at the lab's count",
        lambda: (g["rc"] == 0 and "swaps BTCUSD plus chers que 1,5 fois ceux du labo" in g["an"] and "70009006" in g["an"] and "1 nuit(s)" in g["an"],
                 (g["an"][:700], (g["d"].get("costs") or {}).get("BTCUSD"))))
    chk("deals TOOL1: the BTC swaps of the deals beyond 1.5 x the lab's are DIFFERENT",
        lambda: (g["t1"]["ck"].get(("BTCUSD", "deals_swap"), {}).get("status") == "DIFFERENT", g["t1"]["ck"].get(("BTCUSD", "deals_swap"))))
    tc_g = tw_g["at"] + tw_g["hold"] + 2
    g = story_deals_case("swap3_gold", trades=story_trades() + [tw_g], segs=segs2, copy=copy2, deals_fn=lambda ds: swap3(ds, tw_g),
                         shifts=[(tc_g, -round(3 * day_g, 2))], tool1=True, lit=lit)
    chk("deals TOOL2: a triple swap charged on a Wednesday night on gold (the lab's own triple day): no swap anomaly, 3 nights at the lab's count",
        lambda: (g["rc"] == 0 and "swaps XAUUSD" not in g["an"] and not (g["d"].get("costs") or {}).get("XAUUSD", {}).get("swap_beyond")
                 and (g["d"].get("costs") or {}).get("XAUUSD", {}).get("swap_nights") == 3, (g["an"][:400], (g["d"].get("costs") or {}).get("XAUUSD"))))
    # a row that is not ReleveFP's (an extra field holding the holder's name) and the account's words planted around: never in any output
    g = story_deals_case("tamper")
    p_ = os.path.join(g["rel"], T_DEALS)
    rows_ = t_read(p_).splitlines() or ["", "", ""]
    rows_.insert(3, rows_[2] + f",{FAKE_NAME} login: {FAKE_LOGIN}")
    write(p_, "\n".join(rows_) + "\n")
    out = os.path.join(SCRATCH, "rv7_tamper", "out2")
    rc, so, se = run_tool("check_demo.py", ["--journals", os.path.dirname(g["jdir"]), "--deals", p_, "--out", out])
    rr = json.load(open(os.path.join(out, "report.json"))) if rc == 0 else {}
    txt = (outputs_text(out) + so) if rc == 0 else se
    chk("deals TOOL2: a deals.csv row with an extra field (the holder's name and login glued) is counted and located, its text never kept",
        lambda: (rc == 0 and "1 ligne(s) illisible(s)" in " ".join(rr.get("anomalies", [])) and "lignes 4" in " ".join(rr.get("anomalies", []))
                 and not any(w in txt for w in ACCOUNT_WORDS), (rr.get("anomalies"), [w for w in ACCOUNT_WORDS if w in txt])))
    t1 = tool1_on_deals(os.path.join(SCRATCH, "rv7_tamper"), g["rel"], lit)
    chk("deals TOOL1: the same row is counted and located (DIFFERENT), no account word in tool 1's outputs",
        lambda: (t1["rc"] == 0 and t1["ck"].get(("compte", "deals_file"), {}).get("status") == "DIFFERENT"
                 and "lignes 4" in str(t1["ck"].get(("compte", "deals_file"), {}).get("broker")) and not any(w in t1["txt"] for w in ACCOUNT_WORDS),
                 (t1["ck"].get(("compte", "deals_file")), [w for w in ACCOUNT_WORDS if w in t1["txt"]])))
    # tool 1: a 1.11 folder without deals.csv, erreur_deals, an empty history; a 1.10 folder (nothing said: control)
    base = os.path.join(SCRATCH, "rv7_t1")
    os.makedirs(base, exist_ok=True)
    gc = story_deals_case("t1src")
    t1 = tool1_on_deals(base, gc["rel"], lit, drop=(T_DEALS,))
    chk("deals TOOL1: version=1.11 without deals.csv is DIFFERENT ('deals.csv absent : recopier le dossier claude/releve en entier')",
        lambda: (t1["ck"].get(("compte", "deals_file"), {}).get("status") == "DIFFERENT" and "absent" in str(t1["ck"].get(("compte", "deals_file"), {}).get("broker")),
                 t1["ck"].get(("compte", "deals_file"))))
    t1 = tool1_on_deals(base, gc["rel"], lit, fini_edit_fn=lambda ls: [("erreur_deals=4401" if ln.startswith("erreur_deals=") else ln) for ln in ls])
    chk("deals TOOL1: erreur_deals != 0 in fini.txt is DIFFERENT", lambda: (t1["ck"].get(("compte", "deals_error"), {}).get("status") == "DIFFERENT",
                                                                         t1["ck"].get(("compte", "deals_error"))))
    ge = releve_run_deals("rv7_rel_empty", [], [], STORY_COPY)
    t1 = tool1_on_deals(os.path.join(SCRATCH, "rv7_t1e"), ge, lit)
    chk("deals TOOL1: an empty history (deals=0: not even the opening deposit) is DIFFERENT, with the advice to run ReleveFP again",
        lambda: (t1["ck"].get(("compte", "deals_file"), {}).get("status") == "DIFFERENT" and "relancer ReleveFP" in str(t1["ck"].get(("compte", "deals_file"), {}).get("note")),
                 t1["ck"].get(("compte", "deals_file"))))
    f110 = os.path.join(SCRATCH, "rv7_t1_110")
    make_releve(f110, lit, "good")
    out = os.path.join(SCRATCH, "rv7_t1_110_out")
    rc, so, se = run_tool("read_mac_files.py", [f110, "--out", out])
    s110 = json.load(open(os.path.join(out, "summary.json"))) if rc == 0 else {"checks": [{"item": "?"}]}
    chk("deals control: a ReleveFP 1.10 folder (no deals.csv, no positions.csv): tool 1 says nothing about deals (behaviour unchanged)",
        lambda: (rc == 0 and not any("deal" in c["item"] or "position" in c["item"] for c in s110["checks"]) and "deals" not in s110, se[-300:]))
    # check_demo with a 1.10 releve beside --bars and no --deals: no history section, the same anomalies as with the old tools (control)
    gd = story_deals_case("noargs")
    out = os.path.join(SCRATCH, "rv7_nodeals_out")
    rc, so, se = run_tool("check_demo.py", ["--journals", os.path.dirname(gd["jdir"]), "--bars", f110, "--no-replay", "--out", out])
    rn = json.load(open(os.path.join(out, "report.json"))) if rc == 0 else {"deals": 1}
    chk("deals control: check_demo with a 1.10 releve folder (no deals.csv beside --bars): no history section, nothing about deals",
        lambda: (rc == 0 and "deals" not in rn and "deals" not in rn.get("fills", {}) and "Historique du compte" not in so
                 and "historique du compte" not in " ".join(rn.get("anomalies", [])), (so[-400:], se[-300:])))


def test_review7_deals_replay(lit):
    """review7 with the harness's own account (the robot's release file replayed as review4's 1,000 EUR S7 demo, GO4 to END4, ReleveFP at RUN4):
    ReleveFP.mq5 1.11 itself (releve_mock) writes deals.csv and positions.csv from the harness's deals and open positions (harness_history),
    so the journal's FILL and CLOSE lines and the deals agree by construction; check_demo with deals.csv beside --bars. Faults: the broker's
    stops slipping 1x (no alarm), 3x and 10x the lab's (MOCK_SLIP_STOP_BPS), the gold commission twice the lab's (MOCK_COMM), a triple swap
    charged on a Wednesday night (BTC or ETH), a trade by hand (MOCK_FAULTS hand_open, MetaTrader's magic 0), a deposit (MOCK_PAYMENTS), a
    deal the journal does not know, a CLOSE line lost whose deal exists, a position still open at the run (and missing from positions.csv), a
    1.10 folder without deals (behaviour unchanged), the account's words planted in the deals' comments and external ids"""
    t0 = time.time()
    if not releve_binary():
        check("deals RELEVE-111: ReleveFP.mq5 1.11 builds against releve_mock (harness account)", False, REL7.get("err"))
        return
    demo_env = {"MOCK_INPUT_InpTrade": "true", "MOCK_INPUT_InpPlanStart": str(GO4), "MOCK_BALANCE": "1000"}
    rel100 = releve_replay("rel7_100", lit, RUN4)
    outs = []

    def with_deals(name, files, mutate=None, positions_fn=None):
        deals, poss = harness_history(files, deposit=1000.0, deposit_srv=GO4 - 86400, end_srv=END4)
        if mutate:
            deals = mutate(deals)
        if positions_fn:
            poss = positions_fn(poss)
        run = releve_run_deals("rel7_run_" + name, deals, poss, RUN4)
        return merge_deals(rel100, run, os.path.join(SCRATCH, "rel7_" + name)), deals, poss

    def cd(name, jfiles, bars, extra=("--no-replay",)):
        out = os.path.join(SCRATCH, "out7_" + name)
        outs.append(out)
        rc, so, se = run_tool("check_demo.py", ["--journals", jfiles, "--bars", bars, "--out", out] + list(extra))
        r = json.load(open(os.path.join(out, "report.json"))) if rc == 0 else {}
        outs.append(("so", so))
        return {"rc": rc, "so": so, "se": se, "r": r, "an": " | ".join(r.get("anomalies", [])), "d": r.get("deals") or {},
                "m": (r.get("fills") or {}).get("money_estimate") or {}, "pos": {p["ticket"]: p for p in (r.get("fills") or {}).get("positions", [])}}
    clean, _, _ = harness_live("live7_clean", HIST4, demo_env, frm=GO4, to=END4)
    relc, deals_c, poss_c = with_deals("clean", clean)
    import pandas as pd
    hd = pd.read_csv(os.path.join(clean, "_mock", "deals.csv"), keep_default_na=False, float_precision="round_trip")
    got = t_rows(os.path.join(relc, T_DEALS))
    raw = t_read(os.path.join(relc, T_DEALS))

    def same_vals():
        by_t = {int(d["ticket"]): d for d in got}
        for r_ in hd.itertuples():
            d = by_t.get(int(r_.deal))
            if d is None or abs(float(d["price"]) - round(float(r_.price), 2)) > 1e-9 or abs(float(d["commission"]) - round(float(r_.commission), 2)) > 1e-9 \
                    or abs(float(d["profit"]) - round(float(r_.profit), 2)) > 1e-9 or d["type"] != T_DEAL_TYPES[int(r_.type)] \
                    or d["reason"] != T_DEAL_REASONS[int(r_.reason)]:
                return False
        return True
    chk("deals RELEVE-111 (harness): ReleveFP 1.11 writes the harness account's every deal (and the opening deposit) oldest first, prices and money "
        "rounded to the digits, types and reasons by name, volumes with the step's digits (US100 one decimal)",
        lambda: (raw.splitlines()[:1] == [T_DEALS_HEADER] and len(got) == len(hd) + 1 and same_vals()
                 and [int(d["time"]) for d in got] == sorted(int(d["time"]) for d in got) and ",US100.r,DEAL_TYPE_" in raw
                 and re.search(r",US100\.r,DEAL_TYPE_\w+,DEAL_ENTRY_\w+,DEAL_REASON_\w+,\d+,\d+\.\d,", raw) is not None,
                 (len(got), len(hd), raw.splitlines()[:3])))
    chk("deals RELEVE-111 (harness): positions.csv lists the robot positions still open at the run; the planted server, login and name "
        "(comments, external ids) are in no file ReleveFP writes",
        lambda: (len(t_read(os.path.join(relc, T_POSITIONS)).splitlines()) == len(poss_c) + 1 and len(poss_c) >= 1
                 and not any(w in open(os.path.join(relc, f), errors="replace").read() for f in os.listdir(relc) for w in ACCOUNT_WORDS),
                 (poss_c[:1], [f for f in os.listdir(relc) for w in ACCOUNT_WORDS if w in open(os.path.join(relc, f), errors="replace").read()])))
    g = cd("clean", clean, relc, extra=())
    stops = g["d"].get("stops") or {}
    est = [p for p in g["pos"].values() if p.get("exit_kind_journal") in ("broker_stop_estimated", "broker_stop_race", "broker_stop_seen")]
    hdo = hd[(hd.entry == 1) & (hd.reason == 4)].set_index("position")
    chk("deals TOOL2: the clean demo with its account history (replay included): every position matched, entries and closes equal, the "
        "broker's stops at their real price (the harness's), slipping 1x the lab's: in the margin; balance explained; 'Rien d'anormal.'",
        lambda: (g["rc"] == 0 and g["d"].get("matched") == len(g["pos"]) > 30 and not g["d"].get("price_disagreements") and len(est) > 5
                 and all(p["exit_kind"] == "broker_stop_deal" and abs(p["exit_real"] - round(float(hdo.loc[p["ticket"], "price"]), 2)) < 1e-9 for p in est)
                 and all(v.get("n_vs_paper", 0) >= 3 and not v.get("beyond") for v in stops.values()) and len(stops) == 4
                 and g["m"].get("deals", {}).get("exact") and g["r"].get("anomalies") == [] and "Rien d'anormal." in g["so"],
                 ({k: (v.get("n_vs_paper"), v.get("beyond_paper_bp_mean")) for k, v in stops.items()}, g["an"][:600], g["se"][-400:])))
    chk("deals TOOL2: the broker's stop exits now enter the euros and the headline ('stops courtier au prix reel'), their slippage given per market "
        "in points, bp and EUR against the lab's",
        lambda: (g["rc"] == 0 and "stops courtier au prix reel" in g["so"] and "glissement au niveau du stop" in g["so"]
                 and g["r"]["fills"]["per_sleeve"]["TOTAL"].get("stop_exit_diff_eur_sum") is not None
                 and "sortie(s) par stop courtier, prix inconnu" not in g["so"], g["so"][:900]))
    # review8 RELEVE111-CRLF on the harness account: every row of ReleveFP's files ends in CR LF and deals= counts them all
    chk("deals2 RELEVE111-CRLF (harness): ReleveFP 1.11's deals.csv and positions.csv of the harness account end every row in CR LF (the "
        "documented FileWriteString of releve_mock), deals= and positions= count them all",
        lambda: (crlf_rows(os.path.join(relc, T_DEALS)) == len(got) and fini_of(relc).get("deals") == str(len(got))
                 and crlf_rows(os.path.join(relc, T_POSITIONS)) == len(poss_c) and fini_of(relc).get("positions") == str(len(poss_c)),
                 (crlf_rows(os.path.join(relc, T_DEALS)), len(got), fini_of(relc).get("deals"))))
    # review8 MONEY-AU-CENTIME-CLAIM on the harness account: one closing deal of the second week edited by +0.20 EUR, the journal untouched
    tgt = next((d for d in sorted(deals_c, key=lambda d: d["time"]) if d["entry"] == 1 and d["magic"] in C.CODE_OF_MAGIC
                and d["time"] > srv("2021-11-03 00:00")), None)
    ge = cd("edit020", clean, with_deals("edit020", clean, mutate=lambda ds: [dict(d, profit=round(d["profit"] + 0.20, 2)) if d["ticket"] == tgt["ticket"]
                                                                              else d for d in ds])[0]) if tgt else {"rc": 1, "an": "", "m": {}}
    chk("deals2 MONEY-AU-CENTIME-CLAIM (harness): one closing deal of the harness account's second week edited by +0.20 EUR (about 100 deals): the "
        "balance no longer follows the history (an anomaly), while the clean run agrees line by line",
        lambda: (bool(tgt) and ge["rc"] == 0 and "ne suit pas l'historique du compte" in ge["an"] and not (ge["m"].get("deals") or {}).get("exact")
                 and g["m"].get("deals", {}).get("exact"), (ge["an"][:500], tgt and tgt["ticket"], (ge["m"].get("deals") or {}).get("tolerance_max_eur"))))
    open_t = [q["ticket"] for q in poss_c if q["magic"] in C.CODE_OF_MAGIC]
    chk("deals TOOL2: the robot position still open when ReleveFP ran is in positions.csv and matched with the journal (no anomaly)",
        lambda: (bool(open_t) and all(g["pos"].get(t_, {}).get("open_at_releve") for t_ in open_t), (open_t, g["d"].get("open_at_releve"))))
    gp = cd("open_missing", clean, with_deals("open_missing", clean, positions_fn=lambda ps: [q for q in ps if q["magic"] not in C.CODE_OF_MAGIC])[0])
    chk("deals TOOL2: the same position missing from positions.csv: an anomaly naming it",
        lambda: (gp["rc"] == 0 and "absente(s) de positions.csv" in gp["an"] and str(open_t[0]) in gp["an"], gp["an"][:500]))
    # the broker's stops slipping 3x and 10x the lab's (the market orders stay at the lab's)
    for mult in (3, 10):
        env = dict(demo_env, **{f"MOCK_SLIP_STOP_BPS_{b}.r": repr(mult * C.SLIP_BPS[b][1]) for b in C.ROBOT_BASES})
        jd, _, _ = harness_live(f"live7_stop{mult}", HIST4, env, frm=GO4, to=END4)
        gs = cd(f"stop{mult}", jd, with_deals(f"stop{mult}", jd)[0])
        st_ = gs["d"].get("stops") or {}
        chk(f"deals TOOL2: the broker's stops slipping {mult}x the lab's (MOCK_SLIP_STOP_BPS): judged beyond 1.5 x the lab's on every market with "
            f"3 stops or more ('glissement des stops courtier ... au-dela'), the real slippage about {mult} x the lab's",
            lambda: (gs["rc"] == 0 and st_ and all(v.get("beyond") for v in st_.values() if v.get("n_vs_paper", 0) >= 3)
                     and sum(1 for v in st_.values() if v.get("n_vs_paper", 0) >= 3) >= 3 and gs["an"].count("glissement des stops courtier") >= 3
                     and all(abs(v["slip_bp_mean"] / v["lab_stop_bp"] - mult) < 0.5 for v in st_.values() if v.get("slip_bp_mean")),
                     ({k: (v.get("n_vs_paper"), v.get("beyond"), v.get("slip_bp_mean")) for k, v in st_.items()}, gs["an"][:500])))
    # review8 DEALS-WORDING: the execution cost line says what it judges and gives the broker's stops' verdict beside it (gs: the 10x run)
    chk("deals2 DEALS-WORDING (harness): with the broker's stops 10x the lab's, stdout's execution cost line names what it judges ('Frais "
        "d'execution des ordres au marche') and gives the stops' verdict beside it ('stops courtier (historique du compte) : AU-DELA')",
        lambda: (gs["rc"] == 0 and "Frais d'execution des ordres au marche" in gs["so"] and "stops courtier (historique du compte) : AU-DELA" in gs["so"],
                 [ln for ln in gs["so"].splitlines() if ln.startswith("Frais")]))
    # the gold commission twice the lab's
    jd, _, _ = harness_live("live7_comm2", HIST4, dict(demo_env, **{"MOCK_COMM_XAUUSD.r": repr(2 * 3.0 * 0.89)}), frm=GO4, to=END4)
    gc = cd("comm2", jd, with_deals("comm2", jd)[0])
    chk("deals TOOL2: the gold commission twice the lab's (MOCK_COMM): 'commission XAUUSD au-dela du modele', the balance still explained",
        lambda: (gc["rc"] == 0 and "commission XAUUSD au-dela du modele du labo" in gc["an"] and gc["m"].get("deals", {}).get("exact"),
                 (gc["an"][:500], (gc["d"].get("costs") or {}).get("XAUUSD"))))
    # a triple swap charged on a Wednesday night on a crypto position (the lab triples on Friday)
    # the robot's crypto positions of the harness's history held over a Wednesday night (server days)
    wed = None
    for pid_, grp in hd[(hd.position > 0) & hd.type.isin([0, 1])].groupby("position"):
        ins, outs_ = grp[grp.entry == 0], grp[grp.entry == 1]
        if len(ins) != 1 or len(outs_) != 1 or int(ins.magic.iloc[0]) not in C.CODE_OF_MAGIC or t_base(ins.symbol.iloc[0]) not in ("BTCUSD", "ETHUSD"):
            continue
        a_, z_ = int(ins.time.iloc[0]), int(outs_.time.iloc[0])
        if any(C.dow(t_ - 86400) == 3 for t_ in range(a_ - a_ % 86400 + 86400, z_ + 1, 86400)):
            wed = {"position": int(pid_), "price_in": float(ins.price.iloc[0]), "vol_in": float(ins.volume.iloc[0]), "time_out": z_,
                   "side": 1 if int(ins.type.iloc[0]) == 0 else -1, "out_ticket": int(outs_.deal.iloc[0])}
            break
    if wed:
        k_ = 0.89
        daily = 0.2 * wed["price_in"] * wed["vol_in"] * k_ / 360.0 if wed["side"] > 0 else 0.02 * wed["price_in"] * wed["vol_in"] * k_ / 360.0
        sw = -round(3 * daily, 2)
        jcopy = os.path.join(SCRATCH, "live7_swap", "files")
        if os.path.isdir(os.path.dirname(jcopy)):
            shutil.rmtree(os.path.dirname(jcopy))
        shutil.copytree(clean, jcopy)
        shift_balances(os.path.join(jcopy, "ClaudeRobot"), wed["time_out"], sw)
        gw = cd("swap3", jcopy, with_deals("swap3", clean, mutate=lambda ds: [dict(d, swap=sw) if d["ticket"] == wed["out_ticket"] else d
                                                                            for d in ds])[0])
    chk("deals TOOL2: a triple swap charged on a Wednesday night on a crypto position (the lab triples on Friday): 'swaps ... plus chers' naming it",
        lambda: (wed is not None and gw["rc"] == 0 and f"ticket {wed['position']}" in gw["an"] and "plus chers que 1,5 fois ceux du labo" in gw["an"]
                 and gw["m"].get("deals", {}).get("exact"), (wed and wed["position"], gw["an"][:600] if wed else None)))
    # a trade by hand (MOCK_FAULTS hand_open: MetaTrader's magic 0 in the history) and a deposit (MOCK_PAYMENTS)
    world = os.path.join(SCRATCH, "world7_hand.txt")
    with open(world, "w") as fh:
        fh.write(f"{srv('2021-11-03 15:00')} hand_open XAUUSD.r 1 0.05\n{srv('2021-11-05 18:00')} hand_close\n")
    jd, _, _ = harness_live("live7_hand", HIST4, dict(demo_env, MOCK_FAULTS=world), frm=GO4, to=END4)
    gh = cd("hand", jd, with_deals("hand", jd)[0])
    chk("deals TOOL2: a trade by hand read from the history (magic 0): an anomaly with its market, side, lots, times and result; the balance "
        "explained (no 'le solde a bouge' guess)",
        lambda: (gh["rc"] == 0 and "trade(s) a la main sur le compte" in gh["an"] and "XAUUSD.r achat de 0,05 lot" in gh["an"]
                 and gh["m"].get("deals", {}).get("exact") and "le solde a bouge pour une autre raison que les trades du robot :" not in gh["an"],
                 gh["an"][:700]))
    pay = os.path.join(SCRATCH, "pay7.csv")
    with open(pay, "w") as fh:
        fh.write(f"{srv('2021-11-04 12:00')},250.0\n")
    jd, _, _ = harness_live("live7_pay", HIST4, dict(demo_env, MOCK_PAYMENTS=pay), frm=GO4, to=END4)
    gd = cd("pay", jd, with_deals("pay", jd)[0])
    chk("deals TOOL2: a deposit read from the history (DEAL_TYPE_BALANCE): 'versement de 250,00 EUR le 2021-11-04', the balance explained",
        lambda: (gd["rc"] == 0 and "versement de 250,00 EUR le 2021-11-04" in gd["an"] and gd["m"].get("deals", {}).get("exact")
                 and gd["an"].count("versement") == 1, gd["an"][:600]))
    # a robot position of the history the journal does not know (a second copy's trade?), the balance moved by it
    tx = srv("2021-11-09 10:00")
    extra = [mock_deal(41900001, 41900001, 41900001, tx, "BTCUSD.r", 0, 0, 3, 20261203, 0.01, 65000.0, sl=64000.0, comment=FAKE_NAME),
             mock_deal(41900002, 41900002, 41900001, tx + 1800, "BTCUSD.r", 1, 1, 3, 20261203, 0.01, 65100.0, profit=0.89, comment=FAKE_SERVER)]
    jcopy = os.path.join(SCRATCH, "live7_unknown", "files")
    if os.path.isdir(os.path.dirname(jcopy)):
        shutil.rmtree(os.path.dirname(jcopy))
    shutil.copytree(clean, jcopy)
    shift_balances(os.path.join(jcopy, "ClaudeRobot"), tx + 1800, 0.89)
    gu = cd("unknown", jcopy, with_deals("unknown", clean, mutate=lambda ds: ds + extra)[0])
    chk("deals TOOL2: a robot deal the journal does not know (BKB, no FILL): named with its sleeve and times, the balance still explained",
        lambda: (gu["rc"] == 0 and "que le journal ne connait pas" in gu["an"] and "BKB" in gu["an"] and gu["m"].get("deals", {}).get("exact"),
                 gu["an"][:600]))
    # a CLOSE line lost whose deal exists
    jcopy = os.path.join(SCRATCH, "live7_closelost", "files")
    if os.path.isdir(os.path.dirname(jcopy)):
        shutil.rmtree(os.path.dirname(jcopy))
    shutil.copytree(clean, jcopy)
    ea = next(p for p in sorted(g["pos"].values(), key=lambda p: p.get("exit_utc") or 0) if p["exit_kind"] == "ea_close" and not p.get("exit_apart"))
    for f in sorted(os.listdir(os.path.join(jcopy, "ClaudeRobot"))):
        edit_lines(os.path.join(jcopy, "ClaudeRobot", f), lambda ls: [ln for ln in ls if not ("|CLOSE|" in ln and f"|ticket={ea['ticket']}|" in ln)])
    gl = cd("closelost", jcopy, relc)
    pl = gl["pos"].get(ea["ticket"], {})
    chk("deals TOOL2: a position whose CLOSE line is lost but whose deal exists: the exit is the deal's (the robot's close, its price), the anomaly "
        "says the journal lacked it, the money is complete",
        lambda: (gl["rc"] == 0 and pl.get("exit_kind") == "ea_close_deal" and abs((pl.get("exit_real") or 0) - (ea.get("exit_real") or -1)) < 0.006
                 and "connue par l'historique du compte" in gl["an"] and gl["m"].get("complete") is True,
                 (pl.get("exit_kind"), pl.get("exit_real"), ea.get("exit_real"), gl["an"][:500], gl["m"].get("incomplete_why"))))
    # the Mac asleep over a night and a weekend (review4b ADV5-2's harness copy with MOCK_SLEEP): the DAY lines of the sleep are written at the
    # wake, with the deals made meanwhile in their balance
    exe_s = os.path.join(SCRATCH, "harness_sleep", "robot", "build", "sleep_release", "replay")
    if not os.path.exists(exe_s):
        try:
            exe_s = sleep_harness_exe(os.path.join(SCRATCH, "harness_sleep"))
        except Exception:                                               # noqa: BLE001
            exe_s = None
    gz = {"rc": 1, "m": {}, "r": {}, "an": ""}
    if exe_s:
        env = dict(demo_env, MOCK_SLEEP=f"{SLEEP_NIGHT[0]}-{SLEEP_NIGHT[1]},{SLEEP_WEEKEND[0]}-{SLEEP_WEEKEND[1]}")
        for b in C.ROBOT_BASES:
            env[f"MOCK_HOLE_{b}.r"] = f"{SLEEP_NIGHT[0]}-{SLEEP_NIGHT[1]}@{SLEEP_NIGHT[1] + 90}"
        jd, _, _ = harness_live("live7_sleep", HIST4, env, frm=GO4, to=END4, exe=exe_s)
        gz = cd("sleep", jd, with_deals("sleep", jd)[0])
    chk("deals TOOL2: the Mac asleep over a night and a weekend (DAY lines written at the wake, deals made meanwhile): the balance still follows "
        "the history line by line, nothing abnormal",
        lambda: (bool(exe_s) and gz["rc"] == 0 and (gz["m"].get("deals") or {}).get("exact") and (gz["m"].get("deals") or {}).get("days_checked", 0) >= 10
                 and gz["r"].get("anomalies") == [], (gz["an"][:500], gz["m"].get("deals"))))
    g0 = cd("v110", clean, rel100)
    chk("deals control: the same demo with ReleveFP 1.10's files (no deals.csv): nothing about the account's history, 'Rien d'anormal.' as before",
        lambda: (g0["rc"] == 0 and not g0["d"] and "Historique du compte" not in g0["so"] and g0["r"].get("anomalies") == []
                 and "Rien d'anormal" in g0["so"], (g0["an"][:300], g0["so"][-300:])))
    leaks = [o for o in outs if isinstance(o, str) and any(w in outputs_text(o) for w in ACCOUNT_WORDS)]
    leaks += ["stdout" for o in outs if isinstance(o, tuple) and any(w in o[1] for w in ACCOUNT_WORDS)]
    chk("deals privacy: the account's server, login and name planted in the deals' comments and external ids are in no output of check_demo "
        "(which read the deals: the clean run's history section)", lambda: (not leaks and bool(g["d"].get("used")), (leaks[:3], g["d"].get("used"))))
    print(f"   (review7 deals replay tests {time.time() - t0:.0f} s)")


# ---------------------------------------------------------------------------------------------- review8: the deals stage's second pass
PROBE7 = r'''#include "mock_mt5.h"
int main()
  {
   FolderCreate("p");
   int h = FileOpen("p\\t.txt", FILE_WRITE | FILE_TXT | FILE_ANSI);
   uint n_txt = FileWriteString(h, "ab\ncd\r\n");
   FileClose(h);
   h = FileOpen("p\\c.csv", FILE_WRITE | FILE_CSV | FILE_ANSI);
   uint n_csv = FileWriteString(h, "x\n");
   FileClose(h);
   h = FileOpen("p\\b.bin", FILE_WRITE | FILE_BIN);
   uint n_bin = FileWriteString(h, "ab\n");
   FileClose(h);
   ResetLastError();
   int ho = FileOpen("p\\no.txt", FILE_WRITE | FILE_TXT | FILE_ANSI);
   int e_open = GetLastError();
   h = FileOpen("p\\w.txt", FILE_WRITE | FILE_TXT | FILE_ANSI);
   ResetLastError();
   uint n_fail = FileWriteString(h, "abc\r\n");
   int e_fail = GetLastError();
   FileClose(h);
   HistorySelect(0, 100);
   long out_list = HistoryDealGetInteger(1000001, DEAL_TIME);
   HistorySelect(0, TimeTradeServer() + 86400);
   long in_list = HistoryDealGetInteger(1000001, DEAL_TIME);
   long dg = -1;
   ResetLastError();
   bool sel = SymbolInfoInteger("XAUUSD.r", SYMBOL_DIGITS, dg);
   int e_sel = GetLastError();
   printf("txt=%u\ncsv=%u\nbin=%u\nopen=%d\nopen_err=%d\nfail=%u\nfail_err=%d\nout_list=%ld\nin_list=%ld\nsel=%d\nsel_err=%d\nserver=%s\n"
          "company=%s\nname=%s\nlogin=%ld\ncurrency=%s\n", n_txt, n_csv, n_bin, ho, e_open, n_fail, e_fail, out_list, in_list, (int)sel, e_sel,
          AccountInfoString(ACCOUNT_SERVER).c_str(), AccountInfoString(ACCOUNT_COMPANY).c_str(), AccountInfoString(ACCOUNT_NAME).c_str(),
          AccountInfoInteger(ACCOUNT_LOGIN), AccountInfoString(ACCOUNT_CURRENCY).c_str());
   return 0;
  }
'''


def build_against_releve_mock(name, cpp_text=None, mq5_text=None):
    """a C++ program built against releve_mock: cpp_text as it is, or an .mq5 text translated by to_cpp.py (review8); the binary, None when the
    build failed (its error in REL7[name])"""
    d = os.path.join(SCRATCH, "rv8_build_" + name)
    os.makedirs(d, exist_ok=True)
    if mq5_text is not None:
        with open(os.path.join(d, "R.mq5"), "w", encoding="ascii") as f:
            f.write(mq5_text)
        r = subprocess.run([sys.executable, "-I", os.path.join(C.LAB, "live_ai", "check", "to_cpp.py"), os.path.join(d, "R.mq5"),
                            os.path.join(d, "releve.cpp")], capture_output=True, text=True)
        if r.returncode != 0:
            REL7[name] = r.stderr[-400:]
            return None
        cpp_text = '#include "mock_mt5.h"\n#include "releve.cpp"\nint main() { OnStart(); return 0; }\n'
    with open(os.path.join(d, "run.cpp"), "w") as f:
        f.write(cpp_text)
    b = subprocess.run(["g++", "-std=c++17", "-O1", "-w", "-I", os.path.join(HERE, "releve_mock"), "-I", d, os.path.join(d, "run.cpp"), "-o",
                        os.path.join(d, "run")], capture_output=True, text=True)
    if b.returncode != 0:
        REL7[name] = b.stderr[-800:]
        return None
    return os.path.join(d, "run")


def fini_of(folder):
    """fini.txt of a releve folder as a dict of strings ({} without it)"""
    return dict(ln.split("=", 1) for ln in t_read(os.path.join(folder, "fini.txt")).splitlines() if "=" in ln)


def crlf_rows(path):
    """the data rows of a file whose every line ends in CR LF (header excluded); None when a line ends otherwise or the file is absent"""
    try:
        raw = open(path, "rb").read()
    except OSError:
        return None
    parts = raw.split(b"\r\n")
    if not raw.endswith(b"\r\n") or parts[-1] != b"" or any(b"\n" in p or b"\r" in p for p in parts):
        return None
    return len(parts) - 2


def cd_deals(name, jdir, dpath, extra=()):
    """check_demo journal-only with --deals (or --bars when dpath is a folder), as story_deals_case runs it"""
    out = os.path.join(SCRATCH, "rv8_out_" + name)
    arg = ["--bars", dpath, "--no-replay"] if os.path.isdir(dpath) else ["--deals", dpath]
    rc, so, se = run_tool("check_demo.py", ["--journals", os.path.dirname(jdir)] + arg + ["--out", out] + list(extra))
    r = json.load(open(os.path.join(out, "report.json"))) if rc == 0 and os.path.exists(os.path.join(out, "report.json")) else {}
    return {"rc": rc, "so": so, "se": se, "r": r, "an": " | ".join(r.get("anomalies", [])), "d": (r.get("deals") or {}), "out": out,
            "txt": outputs_text(out) + so if rc == 0 else so + se, "rep_fr": t_read(os.path.join(out, "report_fr.txt")),
            "pos": {p["ticket"]: p for p in (r.get("fills") or {}).get("positions", [])}, "m": (r.get("fills") or {}).get("money_estimate") or {}}


def open_story():
    """the stories' clean week with an N30 position still open when the files are copied (and when ReleveFP runs): trades, starts, the open
    position as positions.csv lists it"""
    tr = story_trades() + [story_trade("N30", srv("2026-11-18 10:00"), 70009005, side=1, open_at_copy=True)]
    opn = {"ticket": 70009005, "identifier": 70009005, "time": srv("2026-11-18 10:00") + 1, "time_msc": (srv("2026-11-18 10:00") + 1) * 1000,
           "symbol": "US100.r", "type": 0, "magic": 20261201, "volume": 1.0, "price_open": 16300.0, "sl": 16137.0, "tp": 0.0,
           "price_current": 16310.0, "swap": 0.0, "profit": 8.6, "comment": FAKE_NAME, "external_id": FAKE_LOGIN}
    return tr, [{"at": STORY_START, "to": None}], opn


def test_review8_deals2_quick(lit):
    """review8, the deals stage's second pass (the verifiers' ids), without the robot build: ReleveFP 1.11 through releve_mock now as the
    documentation describes MetaTrader (FileWriteString adds a CR before a bare LF of a TXT file and returns the bytes written; the deal getters
    answer for the listed deals; a symbol may be not selected; the account plants a server, company, holder's name and login): RELEVE111-CRLF
    (every row written, ending in CR LF, counted), IMIT-CRLF (a probe of releve_mock; the first 1.11 rebuilt -- rows ending in a bare LF, WriteRow
    with == -- fails as the documentation predicts and both tools say so plainly), OPEN-FAIL-UNTESTED (deals.csv or positions.csv that cannot be
    opened), LASTERR-STALE (a failed write without a code of its own after an unknown symbol), IMIT-LOOSE (the planted account in no file);
    tool 1: TOOL1-WITHDRAWAL-WORD, TOOL1-PREDEMO-TRADES, TOOL1-DEPOSIT-BEFORE-FIRST-TRADE, TOOL1-VERSION-EXPECTS-110, TOOL1-HAND-CLOSE-UNSEEN;
    check_demo: TOOL2-FINI-COUNTS-IGNORED (positions=-1, a cut deals.csv), TOOL2-UNKNOWN-POSITIONS-WORDING (a DUP line, a lost daily file),
    TOOL2-LATECOPY-SILENT (ReleveFP run the day before the copy), MONEY-AU-CENTIME-CLAIM (one deal edited by 0.20 EUR after 40 trades);
    PERIOD-FROM-FILE-ORDER (deals.csv reversed), DEALS-WORDING (no 'du le', no negative zero), SERVER-CLAIM (control: the scrubber's sources
    from 1.11 on), SELFTEST-JSON (every info JSON-safe); the account's words in no output"""
    if not releve_binary():
        check("deals2 RELEVE111-CRLF: ReleveFP.mq5 builds against releve_mock", False, REL7.get("err"))
        return
    t0 = time.time()
    outs = []
    # RELEVE111-CRLF: every deals.csv and positions.csv row written and counted, each line ending in CR LF
    tr, segs, opn = open_story()
    deals_open = story_history(tr)
    g = story_deals_case("d2_crlf", trades=tr, segs=segs, positions=[opn], tool1=True, lit=lit)
    outs += [g["out"], ("so", g["so"])]
    fo = fini_of(g["rel"])
    chk("deals2 RELEVE111-CRLF: ReleveFP 1.11 under the documented FileWriteString (releve_mock adds the CR before a bare LF and returns the bytes "
        "written) writes every row of deals.csv and positions.csv, each line ending in CR LF, counted by fini.txt (deals=, positions=), erreur_deals=0",
        lambda: (crlf_rows(os.path.join(g["rel"], T_DEALS)) == len(deals_open) and crlf_rows(os.path.join(g["rel"], T_POSITIONS)) == 1
                 and fo.get("deals") == str(len(deals_open)) and fo.get("positions") == "1" and fo.get("erreur_deals") == "0",
                 (crlf_rows(os.path.join(g["rel"], T_DEALS)), len(deals_open), fo)))
    t1 = g.get("t1") or {"ck": {}, "rc": 1}
    chk("deals2 control RELEVE111-CRLF: both tools read the CR LF files: check_demo matches the open position and explains the balance, tool 1's history, "
        "robot and positions items are not DIFFERENT",
        lambda: (g["rc"] == 0 and (g["d"].get("open_at_releve") or {}).get("journal_matched") == 1 and g["m"].get("deals", {}).get("exact")
                 and not [a_ for a_ in g["r"].get("anomalies", []) if "deals.csv" in a_ or "positions.csv" in a_ or "historique du compte" in a_]
                 and t1["rc"] == 0 and t1["ck"].get(("compte", "deals_file"), {}).get("status") == "OK"
                 and t1["ck"].get(("compte", "deals_robot"), {}).get("status") == "OK"
                 and t1["ck"].get(("compte", "positions_file"), {}).get("status") == "INFO",
                 (g["an"][:400], {"/".join(k): v.get("status") for k, v in t1["ck"].items() if "deal" in k[1] or "position" in k[1]})))
    # IMIT-CRLF and IMIT-LOOSE: a probe of releve_mock itself
    pexe = build_against_releve_mock("probe", cpp_text=PROBE7)
    kv, pdir = {}, os.path.join(SCRATCH, "rv8_probe_files")
    if pexe:
        os.makedirs(pdir, exist_ok=True)
        dfile = os.path.join(SCRATCH, "rv8_probe_deals.csv")
        mock_csv(dfile, story_history(story_trades()), MOCK_DEAL_COLS)
        po = subprocess.run([pexe], env=dict(os.environ, MOCK_FILES=pdir, MOCK_NOW=str(STORY_COPY), MOCK_DEALS_FILE=dfile, MOCK_OPEN_FAIL="no.txt",
                                             MOCK_WRITE_FAIL="w.txt:1:0", MOCK_SYM_NOT_SELECTED="XAUUSD.r", MOCK_SYMS_EXTRA=DEALS_SYMS_EXTRA),
                            capture_output=True, text=True, timeout=60).stdout
        kv = dict(ln.split("=", 1) for ln in po.splitlines() if "=" in ln)
    pb = lambda n: open(os.path.join(pdir, "p", n), "rb").read() if os.path.exists(os.path.join(pdir, "p", n)) else None   # noqa: E731
    chk("deals2 IMIT-CRLF: releve_mock's FileWriteString follows the documentation: a TXT or CSV file gets the CR before a bare LF and the count "
        "includes it (8 bytes for 'ab\\ncd\\r\\n'), a BIN file gets the text as it is; FileOpen fails on demand (5004), FileWriteString too, without "
        "a code of its own",
        lambda: (kv.get("txt") == "8" and pb("t.txt") == b"ab\r\ncd\r\n" and kv.get("csv") == "3" and pb("c.csv") == b"x\r\n" and kv.get("bin") == "3"
                 and pb("b.bin") == b"ab\n" and kv.get("open") == "-1" and kv.get("open_err") == "5004" and kv.get("fail") == "0"
                 and kv.get("fail_err") == "0", (kv, REL7.get("probe"))))
    chk("deals2 IMIT-LOOSE: releve_mock answers the deal getters for the deals HistorySelect listed only, fails SymbolInfoInteger with 4302 for a "
        "symbol not selected in Market Watch, and its account has a planted server, company, holder's name and login",
        lambda: (kv.get("out_list") == "0" and kv.get("in_list") == str(STORY_OPENED) and kv.get("sel") == "0" and kv.get("sel_err") == "4302"
                 and kv.get("server") == "FPMarketsSC-Demo7" and kv.get("company") == "First Prudential Markets Ltd"
                 and kv.get("name") == FAKE_NAME and kv.get("login") == FAKE_LOGIN and kv.get("currency") == "EUR", kv))
    planted = [w for w in (kv.get("server"), kv.get("company"), kv.get("name"), kv.get("login")) if w]
    chk("deals2 IMIT-LOOSE: none of the imitation's planted server, company, holder's name and login in any file ReleveFP 1.11 writes (fini.txt "
        "included)", lambda: (len(planted) == 4 and not [f for f in os.listdir(g["rel"]) for w in planted
                                                      if w in open(os.path.join(g["rel"], f), errors="replace").read()],
                              [f for f in os.listdir(g["rel"]) for w in planted if w in open(os.path.join(g["rel"], f), errors="replace").read()]))
    # IMIT-CRLF: the first 1.11 rebuilt (rows ending in a bare LF, WriteRow with ==): under the documented behaviour every write of those files
    # 'fails'; both tools then say plainly that ReleveFP could not write the history (TOOL2-FINI-COUNTS-IGNORED: no 'historique d'un autre
    # compte', no 'absente(s) de positions.csv')
    src = lit["releve_src"]
    mut = src.replace('\\r\\n";', '\\n";').replace('\\r\\n"))', '\\n"))').replace("return n >= (uint)StringLen(s);", "return n == (uint)StringLen(s);")
    mexe = build_against_releve_mock("mutant", mq5_text=mut) if mut != src else None
    rel_m = releve_run_deals("rv8_rel_mutant", deals_open, [opn], STORY_COPY, exe=mexe) if mexe else None
    fm = fini_of(rel_m) if rel_m else {}
    chk("deals2 IMIT-CRLF: the first 1.11 rebuilt (bare LF, WriteRow with ==) fails under releve_mock as the documentation predicts: deals=-1, "
        "positions=-1, erreur_deals=-1, deals.csv holds its header only",
        lambda: (bool(rel_m) and fm.get("deals") == "-1" and fm.get("positions") == "-1" and fm.get("erreur_deals") == "-1"
                 and t_read(os.path.join(rel_m, T_DEALS)).splitlines() == [T_DEALS_HEADER], (fm, REL7.get("mutant"))))
    gm = cd_deals("mutant", g["jdir"], os.path.join(rel_m, T_DEALS)) if rel_m else {"rc": 1, "an": "", "r": {}, "d": {}, "txt": ""}
    outs += [gm.get("out"), ("so", gm.get("so", ""))]
    chk("deals2 TOOL2-FINI-COUNTS-IGNORED: what that ReleveFP writes (deals=-1, positions=-1, headers only) is one anomaly 'relancer ReleveFP' "
        "saying the history was not used; never 'historique d'un autre compte' nor 'absente(s) de positions.csv'",
        lambda: (gm["rc"] == 0 and len([a_ for a_ in gm["r"].get("anomalies", []) if "deals.csv" in a_ or "positions.csv" in a_
                                         or "historique du compte" in a_]) == 1
                 and "deals=-1" in gm["an"] and "relancer ReleveFP" in gm["an"]
                 and "non utilise" in gm["an"] and "positions.csv incomplet" in gm["an"] and "historique d'un autre compte" not in gm["an"]
                 and "absente(s) de positions.csv" not in gm["an"] and gm["d"].get("used") is False, gm["an"][:700]))
    t1m = tool1_on_deals(os.path.join(SCRATCH, "rv8_t1_mutant"), rel_m, lit) if rel_m else {"ck": {}, "rc": 1}
    chk("deals2 TOOL1: the same files in tool 1: erreur_deals, the history and positions.csv DIFFERENT ('deals=-1'), nothing called OK",
        lambda: (t1m["rc"] == 0 and t1m["ck"].get(("compte", "deals_error"), {}).get("status") == "DIFFERENT"
                 and t1m["ck"].get(("compte", "deals_file"), {}).get("status") == "DIFFERENT"
                 and "deals=-1" in str(t1m["ck"].get(("compte", "deals_file"), {}).get("broker"))
                 and t1m["ck"].get(("compte", "positions_file"), {}).get("status") == "DIFFERENT",
                 {"/".join(k): (v.get("status"), str(v.get("broker"))[:120]) for k, v in t1m["ck"].items() if "deal" in k[1] or "position" in k[1]}))
    # FV7-T1-POSITIONS-COUNT-WORDING (final review of the deals stage): tool 1's positions.csv line says why it is DIFFERENT and what to ask
    pf_m = t1m["ck"].get(("compte", "positions_file"), {})
    chk("deals2 FV7-T1-POSITIONS-COUNT-WORDING: fini.txt says positions=-1: tool 1's positions.csv line names it and says 'relancer ReleveFP'",
        lambda: (t1m["rc"] == 0 and pf_m.get("status") == "DIFFERENT" and "positions=-1" in str(pf_m.get("broker"))
                 and "relancer ReleveFP" in str(pf_m.get("note")), pf_m))
    t1c = tool1_on_deals(os.path.join(SCRATCH, "rv8_t1_poscut"), g["rel"], lit,
                         fini_edit_fn=lambda ls: [re.sub(r"\bpositions=\d+", "positions=2", l_) for l_ in ls])
    pf_c = t1c["ck"].get(("compte", "positions_file"), {})
    chk("deals2 FV7-T1-POSITIONS-COUNT-WORDING: positions.csv one row short of fini.txt: the line gives the count ('1 ligne(s) lue(s) pour "
        "positions=2 dans fini.txt') and asks to copy the claude/releve folder again",
        lambda: (t1c["rc"] == 0 and pf_c.get("status") == "DIFFERENT" and "1 ligne(s) lue(s) pour positions=2 dans fini.txt" in str(pf_c.get("broker"))
                 and "recopier le dossier claude/releve" in str(pf_c.get("note")), pf_c))
    # OPEN-FAIL-UNTESTED: deals.csv, then positions.csv, that ReleveFP cannot open
    rel_od = releve_run_deals("rv8_rel_openfail_d", deals_open, [opn], STORY_COPY, env={"MOCK_OPEN_FAIL": T_DEALS})
    fod = fini_of(rel_od)
    chk("deals2 OPEN-FAIL-UNTESTED: deals.csv cannot be opened (MOCK_OPEN_FAIL): deals=-1, deals_du=0, erreur_deals=5004, no deals.csv; positions.csv "
        "written (positions=1)", lambda: (fod.get("deals") == "-1" and fod.get("deals_du") == "0" and fod.get("erreur_deals") == "5004"
                                          and not os.path.exists(os.path.join(rel_od, T_DEALS)) and fod.get("positions") == "1"
                                          and crlf_rows(os.path.join(rel_od, T_POSITIONS)) == 1, fod))
    god = cd_deals("openfail_d", g["jdir"], rel_od)
    outs += [god["out"], ("so", god["so"])]
    chk("deals2 OPEN-FAIL-UNTESTED: check_demo --bars on that folder says deals.csv is missing beside ReleveFP 1.11's fini.txt (deals=-1, erreur 5004): "
        "relancer ReleveFP", lambda: (god["rc"] == 0 and "deals.csv absent de --bars" in god["an"] and "erreur_deals=5004" in god["an"]
                                      and "relancer ReleveFP" in god["an"], god["an"][:600]))
    t1od = tool1_on_deals(os.path.join(SCRATCH, "rv8_t1_openfail_d"), rel_od, lit)
    chk("deals2 OPEN-FAIL-UNTESTED: tool 1 on it: deals.csv absent and erreur_deals DIFFERENT",
        lambda: (t1od["ck"].get(("compte", "deals_file"), {}).get("status") == "DIFFERENT" and "absent" in str(t1od["ck"].get(("compte", "deals_file"), {}).get("broker"))
                 and t1od["ck"].get(("compte", "deals_error"), {}).get("status") == "DIFFERENT", t1od["ck"].get(("compte", "deals_file"))))
    rel_op = releve_run_deals("rv8_rel_openfail_p", deals_open, [opn], STORY_COPY, env={"MOCK_OPEN_FAIL": T_POSITIONS})
    fop = fini_of(rel_op)
    gop = cd_deals("openfail_p", g["jdir"], os.path.join(rel_op, T_DEALS))
    outs += [gop["out"], ("so", gop["so"])]
    chk("deals2 OPEN-FAIL-UNTESTED: positions.csv cannot be opened: positions=-1, erreur_deals=5004, deals.csv whole; check_demo keeps the history "
        "(matched, balance explained) and says positions.csv was not compared (positions=-1), never that deals.csv is short",
        lambda: (fop.get("positions") == "-1" and fop.get("erreur_deals") == "5004" and fop.get("deals") == str(len(deals_open))
                 and not os.path.exists(os.path.join(rel_op, T_POSITIONS)) and gop["rc"] == 0 and gop["d"].get("matched") == 5
                 and gop["m"].get("deals", {}).get("exact") and "positions.csv incomplet" in gop["an"] and "positions=-1" in gop["an"]
                 and "deals.csv incomplet" not in gop["an"], (fop, gop["an"][:600])))
    # LASTERR-STALE: a deal on a symbol the terminal no longer knows (SymbolInfoInteger leaves 4301), then its row's write fails without a code
    old = mock_deal(1000050, 9050, 9050, STORY_OPENED + 60, "OLD.SYM", 0, 0, 1, 0, 1.0, 1.5)
    rel_st = releve_run_deals("rv8_rel_stale", story_history(story_trades()) + [old], [], STORY_COPY, env={"MOCK_WRITE_FAIL": "deals.csv:3:0"})
    fst = fini_of(rel_st)
    chk("deals2 LASTERR-STALE: a write into deals.csv that fails without a code of its own right after an unknown symbol's 4301: erreur_deals=-1 "
        "(no code), not 4301; the rows before it kept (deals=1)",
        lambda: (fst.get("erreur_deals") == "-1" and fst.get("deals") == "1" and len(t_read(os.path.join(rel_st, T_DEALS)).splitlines()) == 2, fst))
    # TOOL1-WITHDRAWAL-WORD: a withdrawal after the robot's first trade
    wd = [mock_deal(1000202, 0, 0, srv("2026-11-17 12:00"), "", 2, 0, 0, 0, 0.0, 0.0, profit=-300.0, comment="Retrait " + FAKE_NAME)]
    g2 = story_deals_case("d2_withdraw", extra_deals=wd, shifts=[(srv("2026-11-17 12:00"), -300.0)], tool1=True, lit=lit)
    outs += [g2["out"], ("so", g2["so"])]
    b2 = str(g2["t1"]["ck"].get(("compte", "deals_balance"), {}).get("broker"))
    chk("deals2 TOOL1-WITHDRAWAL-WORD: a withdrawal of 300 EUR is a 'retrait -300,00 EUR' in tool 1 (DIFFERENT), never a 'versement'; check_demo "
        "says 'retrait de 300,00 EUR'", lambda: (g2["t1"]["ck"].get(("compte", "deals_balance"), {}).get("status") == "DIFFERENT"
                                                 and "retrait -300,00 EUR" in b2 and "versement -300" not in b2 and "retrait de 300,00 EUR" in g2["an"],
                                                 (b2[:300], g2["an"][:300])))
    # TOOL1-PREDEMO-TRADES: a trade by hand and a SondeFP round trip closed before the robot's start (and first trade)
    pre = [mock_deal(1000401, 9401, 9401, srv("2026-11-14 15:40"), "BTCUSD.r", 0, 0, 0, 0, 0.01, 57100.0, comment=FAKE_NAME),
           mock_deal(1000402, 9402, 9401, srv("2026-11-14 15:45"), "BTCUSD.r", 1, 1, 0, 0, 0.01, 57080.0, profit=-0.17),
           mock_deal(1000403, 9403, 9403, srv("2026-11-14 15:46"), "BTCUSD.r", 0, 0, 3, 20261112, 0.01, 57090.0, comment="CM sonde"),
           mock_deal(1000404, 9404, 9403, srv("2026-11-14 15:47"), "BTCUSD.r", 1, 1, 3, 20261112, 0.01, 57070.0, profit=-0.17)]
    g3 = story_deals_case("d2_prehand", extra_deals=pre, shifts=[(srv("2026-11-14 15:45"), -0.17), (srv("2026-11-14 15:47"), -0.17)], tool1=True, lit=lit)
    outs += [g3["out"], ("so", g3["so"])]
    ck3 = g3["t1"]["ck"]
    chk("deals2 TOOL1-PREDEMO-TRADES: a trade by hand and a SondeFP trade closed before the robot's first trade are INFO 'avant le premier trade du "
        "robot' in tool 1 (not DIFFERENT), as check_demo says 'avant la demo' without an anomaly",
        lambda: (ck3.get(("compte", "deals_hand_before"), {}).get("status") == "INFO" and ck3.get(("compte", "deals_other_before"), {}).get("status") == "INFO"
                 and ("compte", "deals_hand") not in ck3 and ("compte", "deals_other") not in ck3 and g3["rc"] == 0 and g3["r"].get("anomalies") == []
                 and "avant la demo" in t_read(os.path.join(g3["out"], "report_fr.txt")),
                 ({"/".join(k): v.get("status") for k, v in ck3.items() if "deal" in k[1]}, g3["an"][:300])))
    # TOOL1-DEPOSIT-BEFORE-FIRST-TRADE: 500 EUR paid in on the Sunday, after the start, before the first trade
    dep = [mock_deal(1000501, 0, 0, srv("2026-11-15 12:00"), "", 2, 0, 0, 0, 0.0, 0.0, profit=500.0, comment="Depot " + FAKE_NAME)]
    g4 = story_deals_case("d2_sundep", extra_deals=dep, shifts=[(srv("2026-11-15 12:00"), 500.0)], tool1=True, lit=lit)
    outs += [g4["out"], ("so", g4["so"])]
    c4 = g4["t1"]["ck"].get(("compte", "deals_balance"), {})
    chk("deals2 TOOL1-DEPOSIT-BEFORE-FIRST-TRADE: a deposit after the opening one but before the robot's first trade is DIFFERENT in tool 1 (with "
        "the reminder that check_demo dates it against the start), as check_demo flags it",
        lambda: (c4.get("status") == "DIFFERENT" and "versement +500,00 EUR" in str(c4.get("broker")) and "check_demo" in str(c4.get("note"))
                 and "versement de 500,00 EUR le 2026-11-15" in g4["an"], (c4, g4["an"][:300])))
    # TOOL1-VERSION-EXPECTS-110: 1.11 expected; a 1.10 folder (the old .ex5) DIFFERENT
    g0 = story_deals_case("d2_clean", tool1=True, lit=lit)
    outs += [g0["out"], ("so", g0["so"])]
    v11 = g0["t1"]["ck"].get(("compte", "releve_version"), {})
    f110 = os.path.join(SCRATCH, "rv8_v110")
    make_releve(f110, lit, "good")
    o110 = os.path.join(SCRATCH, "rv8_v110_out")
    rc110, _, _ = run_tool("read_mac_files.py", [f110, "--out", o110])
    s110 = json.load(open(os.path.join(o110, "summary.json"))) if rc110 == 0 else {"checks": []}
    v10 = next((c for c in s110["checks"] if c["market"] == "compte" and c["item"] == "releve_version"), {})
    chk("deals2 TOOL1-VERSION-EXPECTS-110: tool 1 expects ReleveFP 1.11 (OK for 1.11, '1.11' in the expected column); a 1.10 folder is DIFFERENT "
        "'ancien script : recompiler ReleveFP 1.11 (F7)'", lambda: (v11.get("status") == "OK" and str(v11.get("assumed")) == "1.11"
                                                                     and v10.get("status") == "DIFFERENT" and "ancien script" in str(v10.get("note"))
                                                                     and "1.11" in str(v10.get("note")) and "F7" in str(v10.get("note")), (v11, v10)))
    # TOOL1-HAND-CLOSE-UNSEEN: the robot's gold position closed by hand on the phone (closing deal DEAL_REASON_MOBILE, magic 0)
    hc = lambda ds: [dict(d, reason=1, magic=0) if (d["position"] == 70009001 and d["entry"] == 1) else d for d in ds]   # noqa: E731
    g5 = story_deals_case("d2_handclose", deals_fn=hc, tool1=True, lit=lit)
    outs += [g5["out"], ("so", g5["so"])]
    c5 = g5["t1"]["ck"].get(("compte", "deals_robot_hand_close"), {})
    chk("deals2 TOOL1-HAND-CLOSE-UNSEEN: a robot position closed by hand (closing deal DEAL_REASON_MOBILE, magic 0) is DIFFERENT in tool 1, named "
        "with its sleeve and 'a la main (telephone)'", lambda: (c5.get("status") == "DIFFERENT" and "ORX" in str(c5.get("broker"))
                                                                  and "a la main (telephone)" in str(c5.get("broker")), c5))
    # TOOL2-FINI-COUNTS-IGNORED: positions=-1 with positions.csv holding its header only, a journal position open at the releve
    gp = story_deals_case("d2_posfail", trades=tr, segs=segs, positions=[opn])
    write(os.path.join(gp["rel"], T_POSITIONS), T_POSITIONS_HEADER + "\n", crlf=True)
    fl = [("positions=-1" if ln.startswith("positions=") else ("erreur_deals=-1" if ln.startswith("erreur_deals=") else ln))
          for ln in t_read(os.path.join(gp["rel"], "fini.txt")).splitlines()]
    write(os.path.join(gp["rel"], "fini.txt"), "\n".join(fl) + "\n", crlf=True)
    gp2 = cd_deals("posfail", gp["jdir"], os.path.join(gp["rel"], T_DEALS))
    outs += [gp2["out"], ("so", gp2["so"])]
    chk("deals2 TOOL2-FINI-COUNTS-IGNORED: positions.csv with its header only and positions=-1 in fini.txt: 'positions.csv incomplet ... non "
        "comparees', never 'absente(s) de positions.csv' for the journal's open position",
        lambda: (gp2["rc"] == 0 and "positions.csv incomplet" in gp2["an"] and "positions=-1" in gp2["an"] and "absente(s) de positions.csv" not in gp2["an"]
                 and (gp2["d"].get("open_at_releve") or {}).get("skipped"), gp2["an"][:600]))
    # TOOL2-FINI-COUNTS-IGNORED: deals.csv cut after 4 of its 9 rows (a copy that stopped on a line end), deals=9 in fini.txt
    gc = story_deals_case("d2_cut")
    raw = open(os.path.join(gc["rel"], T_DEALS), "rb").read().split(b"\r\n")
    n_all = len(raw) - 2
    with open(os.path.join(gc["rel"], T_DEALS), "wb") as f:
        f.write(b"\r\n".join(raw[:5]) + b"\r\n")
    gc2 = cd_deals("cut", gc["jdir"], os.path.join(gc["rel"], T_DEALS))
    outs += [gc2["out"], ("so", gc2["so"])]
    chk("deals2 TOOL2-FINI-COUNTS-IGNORED: deals.csv cut after 4 of its 9 rows: one anomaly 'deals.csv incomplet (4 lignes lues pour deals=9)', "
        "the history used up to its last row: no 'sans aucune transaction', no 'historique d'un autre compte', no 'encore ouverte(s)'",
        lambda: (gc2["rc"] == 0 and n_all == 9 and "deals.csv incomplet (4 lignes lues pour deals=9 dans fini.txt)" in gc2["an"]
                 and "sans aucune transaction" not in gc2["an"] and "historique d'un autre compte" not in gc2["an"]
                 and "encore ouverte(s) dans l'historique" not in gc2["an"] and gc2["d"].get("journal_after_cut") == 2, (n_all, gc2["an"][:700],
                                                                                                                        gc2["d"].get("journal_after_cut"))))
    # TOOL2-UNKNOWN-POSITIONS-WORDING: a duplicate gold position the robot closed (DUP and CLOSE lines name its ticket) and its deals
    o_tr = story_trades()[0]
    dupd = [mock_deal(1000601, 9601, 70009101, o_tr["at"] + 1, "XAUUSD.r", 0, 0, 3, 20261210, 0.05, o_tr["fill"], sl=o_tr["stop"]),
            mock_deal(1000602, 9602, 70009101, o_tr["at"] + 70, "XAUUSD.r", 1, 1, 3, 20261210, 0.05, o_tr["fill"])]

    def add_dup(jd):
        p_ = os.path.join(jd, time.strftime("%Y%m%d", time.gmtime(o_tr["at"])) + ".log")
        u = C.srv_to_utc(o_tr["at"])
        add = [jl(u + 65, "DUP", "ORX", ("ticket", 70009101), ("kept", 70009001)),
               jl(u + 69, "CLOSE", "ORX", ("ticket", 70009101), ("magic", 20261210), ("px", o_tr["fill"]), ("why", "dup"), ("rc", 10009), ("ok", 1))]

        def ins(ls):
            k = next(i for i, ln in enumerate(ls) if "|FILL|ORX|" in ln)
            return ls[:k + 1] + add + ls[k + 1:]
        edit_lines(p_, ins)
    g6 = story_deals_case("d2_dup", extra_deals=dupd, journal_fn=add_dup)
    outs += [g6["out"], ("so", g6["so"])]
    chk("deals2 TOOL2-UNKNOWN-POSITIONS-WORDING: the duplicate the robot closed (its DUP and CLOSE lines name the ticket) is known to the journal: "
        "never 'que le journal ne connait pas'", lambda: (g6["rc"] == 0 and "que le journal ne connait pas" not in g6["an"]
                                                         and "ORX ticket 70009101" in str(g6["d"].get("known_by_other_lines")), (g6["an"][:500],
                                                                                                                                 g6["d"].get("known_by_other_lines"))))
    # TOOL2-UNKNOWN-POSITIONS-WORDING: the daily file of Tuesday 17 lost (BKB's and BKE's lines were in it)
    g7 = story_deals_case("d2_lost", journal_fn=lambda jd: os.remove(os.path.join(jd, "20261117.log")))
    outs += [g7["out"], ("so", g7["so"])]
    chk("deals2 TOOL2-UNKNOWN-POSITIONS-WORDING: the positions of a lost daily file are listed with that file ('leurs lignes etaient dedans', on "
        "stdout too), never 'que le journal ne connait pas'", lambda: (g7["rc"] == 0 and "que le journal ne connait pas" not in g7["an"]
                                                                       and g7["d"].get("in_lost_files") == {"20261117.log": 2}
                                                                       and "positions des fichiers du jour manquants connues par l'historique" in g7["so"]
                                                                       and "20261117.log" in g7["an"], (g7["an"][:500], g7["d"].get("in_lost_files"))))
    # TOOL2-LATECOPY-SILENT: ReleveFP run on Tuesday 17:30 server, the files copied on Wednesday 23:00 (one DAY line after the releve, a gold
    # trade closed after it)
    rel_t = srv("2026-11-17 17:30")
    trl = story_trades() + [story_trade("ORX", srv("2026-11-17 19:00"), 70009008)]
    bl = os.path.join(SCRATCH, "rv8_late")
    if os.path.isdir(bl):
        shutil.rmtree(bl)
    jl_dir = os.path.join(bl, "j", "ClaudeRobot")
    story_journal(jl_dir, [{"at": STORY_START, "to": STORY_END}], trl)
    rel_l = releve_run_deals("rv8_rel_late", [d for d in story_history(trl) if d["time"] <= rel_t], [], rel_t)
    g8 = cd_deals("late", jl_dir, os.path.join(rel_l, T_DEALS))
    outs += [g8["out"], ("so", g8["so"])]
    md8 = g8["m"].get("deals") or {}
    chk("deals2 TOOL2-LATECOPY-SILENT: the journal goes on after the releve: the DAY lines up to it are explained by the history ('historique du compte "
        "jusqu'au releve'), the rest estimated from the balance and said so ('apres le releve ... (estimation d'apres le solde)'), never silently",
        lambda: (g8["rc"] == 0 and md8.get("partial") and md8.get("exact") and "historique du compte jusqu'au releve" in g8["so"]
                 and "apres le releve" in g8["so"] and "(estimation d'apres le solde)" in g8["so"] and (g8["m"].get("after_history") or {}).get("positions") == 3
                 and "historique du compte jusqu'au releve" in g8["rep_fr"], (md8, g8["so"][-900:])))
    # MONEY-AU-CENTIME-CLAIM: 36 more trades on Monday (their rounded cents made the old tolerance grow past 0.20 EUR by Tuesday), then BKB's closing
    # deal on Tuesday edited by +0.20 EUR (the journal's balance keeps the true one)
    many = story_trades()
    for k in range(36):
        many.append(story_trade(["ORX", "N30", "BKB", "BKE"][k % 4], srv("2026-11-16 00:20") + 900 * k, 70009200 + k, hold=600, side=1 if k % 2 == 0 else -1))
    edit = lambda ds: [dict(d, profit=round(d["profit"] + 0.20, 2)) if (d["position"] == 70009003 and d["entry"] == 1) else d for d in ds]   # noqa: E731
    gmc = story_deals_case("d2_many", trades=many)
    gme = story_deals_case("d2_many_edit", trades=many, deals_fn=edit)
    outs += [gmc["out"], ("so", gmc["so"]), gme["out"], ("so", gme["so"])]
    chk("deals2 MONEY-AU-CENTIME-CLAIM: 40 trades agree with the history line by line (exact, the gap said as it is), and one closing deal edited "
        "by 0.20 EUR the next day breaks it on its day ('ne suit pas l'historique ... le 2026-11-17'): the tolerance no longer grows over the demo",
        lambda: (gmc["rc"] == 0 and gmc["m"].get("deals", {}).get("exact") and gmc["r"].get("anomalies") == []
                 and gme["rc"] == 0 and "ne suit pas l'historique du compte" in gme["an"] and "le 2026-11-17" in gme["an"]
                 and not gme["m"].get("deals", {}).get("exact"), (gmc["m"].get("deals", {}).get("max_gap_eur"), gme["an"][:500])))
    chk("deals2 MONEY-AU-CENTIME-CLAIM: 'au centime pres' is said only when the largest gap seen is a cent at most, else 'a X EUR pres'",
        lambda: (all(("au centime pres" in x["so"]) == ((x["m"].get("deals") or {}).get("max_gap_eur", 1) <= 0.011)
                     for x in (g0, gmc) if (x["m"].get("deals") or {}).get("exact")), [(x["m"].get("deals") or {}).get("max_gap_eur") for x in (g0, gmc)]))
    # PERIOD-FROM-FILE-ORDER: the same history with its rows reversed
    rev = os.path.join(SCRATCH, "rv8_rel_reversed")
    if os.path.isdir(rev):
        shutil.rmtree(rev)
    shutil.copytree(g0["rel"], rev)
    rr_ = open(os.path.join(rev, T_DEALS), "rb").read().split(b"\r\n")
    with open(os.path.join(rev, T_DEALS), "wb") as f:
        f.write(b"\r\n".join([rr_[0]] + list(reversed(rr_[1:-1]))) + b"\r\n")
    g9 = cd_deals("reversed", g0["jdir"], os.path.join(rev, T_DEALS))
    t19 = tool1_on_deals(os.path.join(SCRATCH, "rv8_t1_reversed"), rev, lit)
    outs += [g9["out"], ("so", g9["so"])]
    b9 = str(t19["ck"].get(("compte", "deals_file"), {}).get("broker"))
    chk("deals2 PERIOD-FROM-FILE-ORDER: a deals.csv whose rows are in reverse order: both tools give the period from the earliest to the latest deal",
        lambda: (g9["rc"] == 0 and g9["d"].get("from_srv") == STORY_OPENED and g9["d"].get("from_srv") < g9["d"].get("to_srv")
                 and "du 14/11/2026 a 14:30" in b9 and "transactions du 2026-11-14" in g9["rep_fr"], (g9["d"].get("from_srv"), b9[:200])))
    # DEALS-WORDING (tool 1): no 'du le', no negative zero
    tx0 = (g0["t1"] or {}).get("txt", "")
    chk("deals2 DEALS-WORDING: tool 1 says 'du 14/11/2026 ... au ...' (never 'du le'), and no negative zero ('-0 EUR', '-0 points') on the markets "
        "without commission", lambda: (bool(tx0) and "du le " not in tx0 and "au le " not in tx0 and "-0 EUR" not in tx0 and "-0 points" not in tx0
                                       and "0 EUR par lot et par cote = 0 points" in tx0, [ln for ln in tx0.splitlines() if "commission des trades" in ln][:2]))
    # SERVER-CLAIM (control): 1.11's fini.txt names no server; sonde.csv still does, and tool 1 masks it everywhere
    rel111 = os.path.join(SCRATCH, "rv7_d2_clean", "rel111")
    chk("deals2 control SERVER-CLAIM: a 1.11 folder (no server line in fini.txt) with SondeFP's sonde.csv naming the server: tool 1 learns it there "
        "and masks it in every output", lambda: ("server=" not in t_read(os.path.join(rel111, "fini.txt")) and FAKE_SERVER in t_read(os.path.join(rel111, "sonde.csv"))
                                                 and bool(tx0) and FAKE_SERVER not in tx0, t_read(os.path.join(rel111, "fini.txt"))[:200]))
    # SELFTEST-JSON: every info so far is JSON (the review7 check whose info was keyed by (market, item) tuples included)
    r7 = next((r for r in RESULTS if r["test"].startswith("deals TOOL1: read_mac_files reads deals.csv")), None)
    chk("deals2 SELFTEST-JSON: every check's info can be written to the results file as plain JSON (no default), the review7 check keyed by "
        "(market, item) tuples included", lambda: (bool(json.dumps(RESULTS)) and (r7 is None or all(isinstance(k, str) for k in (r7["info"] or [{}])[0])),
                                                   r7 and str(r7["info"])[:200]))
    leaks = [o for o in outs if isinstance(o, str) and os.path.isdir(o) and any(w in outputs_text(o) for w in ACCOUNT_WORDS)]
    leaks += ["stdout" for o in outs if isinstance(o, tuple) and any(w in o[1] for w in ACCOUNT_WORDS)]
    leaks += ["tool 1" for x in (g, g2, g3, g4, g0, g5) for t_ in [x.get("t1") or {}] if any(w in t_.get("txt", "") for w in ACCOUNT_WORDS)]
    leaks += ["tool 1" for t_ in (t1m, t1od, t19) if any(w in t_.get("txt", "") for w in ACCOUNT_WORDS)]
    chk("deals2 privacy: the account's server, login and name (planted in the deals' comments, external ids, the imitation's account and the "
        "sonde) are in no output of these cases", lambda: (not leaks, leaks[:3]))
    print(f"   (review8 deals2 quick tests {time.time() - t0:.0f} s)")


# the scratch folders a later group reuses (review4b and review5 take live4_clean and rel4_100 from review4, review7 the sleeping harness of
# review4b, review7's and review8's groups the ReleveFP build): kept when a replay group's own folders are deleted (pruned)
KEEP_ACROSS_GROUPS = frozenset({"live4_clean", "rel4_100", "harness_sleep", "rv7_build"})
PRUNE = {"on": True}


def prune_scratch(keep=frozenset()):
    """delete the scratch's folders and files except keep and KEEP_ACROSS_GROUPS (nothing with --keep)"""
    if not PRUNE["on"]:
        return
    for n in sorted(set(os.listdir(SCRATCH)) - set(keep) - KEEP_ACROSS_GROUPS):
        p = os.path.join(SCRATCH, n)
        if os.path.isdir(p) and not os.path.islink(p):
            shutil.rmtree(p, ignore_errors=True)
        else:
            try:
                os.remove(p)
            except OSError:
                pass


def pruned(fn, *args):
    """a replay group whose scratch folders and files are deleted when it ends (review8: the full run held about 4 GB of scratch at its end, more
    than the disk the session keeps free allows), except those a later group reuses (KEEP_ACROSS_GROUPS); --keep keeps everything"""
    before = set(os.listdir(SCRATCH))
    try:
        fn(*args)
    finally:
        prune_scratch(keep=before)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args(argv)
    PRUNE["on"] = not a.keep
    if os.path.isdir(SCRATCH):
        shutil.rmtree(SCRATCH)
    os.makedirs(SCRATCH)
    t0 = time.time()
    n_fail = 0
    try:
        lit = literal_lines()
        test_tool1(lit)
        test_review_tool1(lit)
        test_review2_tool1(lit)
        test_tool2_journal(lit)
        test_review_journal(lit)
        test_review2_journal(lit)
        test_review3_tool1(lit)
        test_review3_journal(lit)
        test_review3_releve(lit)
        test_review4_releve(lit)
        test_review4_tool1(lit)
        test_review4_journal(lit)
        test_review4b_tool1(lit)
        test_review4b_journal(lit)
        test_review5_start(lit)
        test_review5_journal(lit)
        test_review5b_start(lit)
        test_review5b_journal(lit)
        test_review5b_fills(lit)
        test_review6_start(lit)
        test_review6_journal(lit)
        test_review6b_start(lit)
        test_review6b_journal(lit)
        guarded(test_review7_deals_quick, lit)
        guarded(test_review8_deals2_quick, lit)
        if not a.quick:
            prune_scratch()                     # the quick groups' folders (about 1.2 GB): no replay group reads them
            pruned(test_tool2_replay, lit)
            pruned(test_review4_replay, lit)
            pruned(test_review4b_replay, lit)
            pruned(test_review5_replay, lit)
            pruned(guarded, test_review7_deals_replay, lit)
        n_fail = sum(1 for r in RESULTS if not r["pass"])
        groups = [(k, [r for r in RESULTS if r["test"].startswith(p)]) for k, p in
                  (("review2", "review2"), ("review3", "review3"), ("review4", "review4 "), ("review4b", "review4b "), ("review5", "review5 "),
                   ("review5b", "review5b "), ("review6", "review6 "), ("review6b", "review6b "), ("deals", "deals "), ("deals2", "deals2 "))]
        print(f"\n{len(RESULTS) - n_fail}/{len(RESULTS)} checks passed in {time.time() - t0:.0f} s ("
              + ", ".join(f"{k}: {sum(r['pass'] for r in rs)}/{len(rs)}" for k, rs in groups) + ")")
    finally:
        # review8 SELFTEST-JSON: the results file is written even when a group stopped the run, as JSON whatever the checks' infos hold (check()
        # makes them JSON-safe; default=str is a second lock), and the scratch is deleted in any case unless --keep
        try:
            with open(RESULTS_FILE, "w") as f:
                json.dump(jsonable(RESULTS), f, indent=1, default=str)
        finally:
            if not a.keep:
                shutil.rmtree(SCRATCH, ignore_errors=True)
    return 0 if n_fail == 0 and RESULTS else 1


if __name__ == "__main__":
    sys.exit(main())
