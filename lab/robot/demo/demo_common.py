"""Shared helpers of the demo tools (read_mac_files.py, check_demo.py, test_demo_tools.py).

What lives here:
  * the output folder rule: every output goes to --out, which defaults to the session scratchpad and may never lie
    inside the repository (the Mac files can hold the account's server, login or name);
  * the scrubber: values that identify the account (server name, login) are collected while reading and masked in
    every text the tools write or print;
  * the clocks of SPEC 2.1: server = New York + 7 h, UTC from the US summer-time rule (the same rule as
    check/test_worlds.py and CR_Clock.mqh);
  * the NYSE calendar (lab/r2/tracks/idx_us/idxus_lib.py us_holidays, loaded read-only, a copy as fallback);
  * a tolerant journal reader built on check/compare.py's line format (bad lines are counted, not fatal);
  * French number formatting for the summaries the user reads.
Nothing here reads market data by itself and nothing writes inside the repository.
"""
import calendar
import datetime as dt
import glob
import importlib.util
import json
import math
import os
import re
import sys
import time

sys.dont_write_bytecode = True                  # never leave __pycache__ in check/ or demo/

HERE = os.path.dirname(os.path.abspath(__file__))
ROBOT = os.path.dirname(HERE)
LAB = os.path.dirname(ROBOT)
REPO = os.path.dirname(LAB)
CHECK = os.path.join(ROBOT, "check")
DIST = os.path.join(ROBOT, "dist", "ClaudeRobot.mq5")
FP_COSTS = os.path.join(LAB, "r2", "fp_costs.json")
DEFAULT_OUT = "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/demo_out"
REQUIRED_BUILD = "fd6aaf01e332"                 # the build the user installs (dist/ClaudeRobot.mq5, CR_BUILD)

if CHECK not in sys.path:
    sys.path.insert(0, CHECK)
import compare  # noqa: E402  (check/compare.py, read-only: the journal line format)

# the robot's four markets (CR_Registry.mqh RegInit) and the lab names (fp_costs.json keys)
ROBOT_BASES = ["XAUUSD", "US100", "BTCUSD", "ETHUSD"]
LAB_SYM = {"XAUUSD": "xauusd", "US100": "us100", "BTCUSD": "btcusd", "ETHUSD": "ethusd", "USDJPY": "usdjpy",
           "EURUSD": "eurusd", "US500": "us500", "GER40": "ger40", "US30": "us30", "XAGUSD": "xagusd", "GBPUSD": "gbpusd",
           "AUDUSD": "audusd", "USDCAD": "usdcad", "USDCHF": "usdchf", "NZDUSD": "nzdusd", "EURJPY": "eurjpy"}
# CR_Registry.mqh RegInit: family, depth days, model bp of the COST line; sleeves (id, code, symbol)
FAMILY = {"XAUUSD": "XAU", "US100": "IDX", "BTCUSD": "CRY", "ETHUSD": "CRY"}
DEPTH_DAYS = {"XAUUSD": 120, "US100": 60, "BTCUSD": 60, "ETHUSD": 60}
MODEL_BP = {"XAUUSD": 0.47, "US100": 0.37, "BTCUSD": 2.96, "ETHUSD": 13.0}
CODES = ["N30", "OC4", "BKB", "BKE", "F1B", "F1E", "NQB", "GFP", "D4H", "ORX"]
SLEEVE_ID = {c: i + 1 for i, c in enumerate(CODES)}
SYM_OF_CODE = {"N30": "US100", "OC4": "US100", "BKB": "BTCUSD", "BKE": "ETHUSD", "F1B": "BTCUSD", "F1E": "ETHUSD",
               "NQB": "BTCUSD", "GFP": "XAUUSD", "D4H": "XAUUSD", "ORX": "XAUUSD"}
READS_OF_CODE = {c: [s] for c, s in SYM_OF_CODE.items()}
READS_OF_CODE["NQB"] = ["BTCUSD", "US100"]
CODE_OF_MAGIC = {20261200 + i: c for c, i in SLEEVE_ID.items()}
# lab slippage per side, bps (fp_costs.json; CR_Registry.mqh RegSym): market, stop
SLIP_BPS = {"XAUUSD": (0.3, 1.0), "US100": (0.2, 0.5), "BTCUSD": (0.5, 1.5), "ETHUSD": (0.7, 2.0)}
XAU_COMM_PTS = 6                                 # CR_Types.mqh CR_XAU_COMM_PTS (round trip, points)


# ---------------------------------------------------------------------------------------------- output folder
def safe_out(path):
    """the --out folder, created; refused (SystemExit) when it lies inside the repository"""
    p = os.path.realpath(os.path.abspath(path or DEFAULT_OUT))
    repo = os.path.realpath(REPO)
    if p == repo or p.startswith(repo + os.sep):
        raise SystemExit(f"--out refuse : {p} est dans le depot {repo}. Les fichiers du Mac peuvent contenir le serveur "
                         f"ou le numero du compte : choisissez un dossier hors du depot (par defaut {DEFAULT_OUT}).")
    os.makedirs(p, exist_ok=True)
    return p


def inside_repo(path):
    p = os.path.realpath(os.path.abspath(path))
    repo = os.path.realpath(REPO)
    return p == repo or p.startswith(repo + os.sep)


def warn_if_in_repo(paths):
    """the Mac files may name the account: a warning when they sit inside the repository (never to be added to git)"""
    if any(p and inside_repo(p) for p in paths):
        print("Attention : des fichiers du Mac sont dans le depot ; ne les ajoutez jamais a git (ils peuvent contenir le serveur "
              "ou le numero du compte). Mieux : les garder hors du depot.")


# ---------------------------------------------------------------------------------------------- scrubbing
class Scrubber:
    """values that identify the account, masked in every output text"""
    MASK = "<masque>"

    def __init__(self):
        self.secrets = set()

    def add(self, value):
        v = (value or "").strip()
        if len(v) >= 3:
            self.secrets.add(v)

    def text(self, s):
        if not isinstance(s, str):
            return s
        for v in sorted(self.secrets, key=len, reverse=True):
            s = s.replace(v, self.MASK)
        return s

    def obj(self, o):
        """a JSON-able object with every string scrubbed (keys included)"""
        if isinstance(o, dict):
            return {self.text(str(k)): self.obj(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [self.obj(v) for v in o]
        if isinstance(o, str):
            return self.text(o)
        return o

    # what a MetaTrader log line (terminal Journal, Experts tab, the scripts' own prints) may hold about the account:
    # the login in quotes at the start of a message ("'12345678': authorized on ..."), the server ("authorized on X",
    # "server=X" printed by ReleveFP and SondeFP), a login after the word login, the holder's name in brackets after
    # "started for <company>", and the Windows (or Wine) and Mac user folders
    ACCOUNT_PATTERNS = [
        (re.compile(r"'(\d{4,})'\s*:"), 1),
        (re.compile(r"authoriz\w*\s+on\s+([^\s,;]+)", re.I), 1),
        (re.compile(r"\bserver\s*=\s*([^\s,;|]+)", re.I), 1),
        (re.compile(r"\blogin\s*[:=]?\s*'?(\d{4,})", re.I), 1),
        (re.compile(r"\baccount\s*[:=#]?\s*'?(\d{4,})", re.I), 1),
        (re.compile(r"started for [^(\r\n]*\(([^)\r\n]+)\)", re.I), 1),
        (re.compile(r"[A-Za-z]:\\+users\\+([^\\/\r\n]+)", re.I), 1),
        (re.compile(r"/users/([^/\r\n]+)/", re.I), 1),
    ]

    def scan_log_line(self, line):
        """a line that is not a robot line may name the account (login, server, holder's name, user folder): every
        such value is collected so that it can never reach an output. The tools never write the text of these lines
        anyway; this is the second lock."""
        for rx, g in self.ACCOUNT_PATTERNS:
            for m in rx.finditer(line):
                v = m.group(g).strip().strip("'\"")
                self.add(v)
                if " " in v:                                     # a name: its parts too ("Jean-Baptiste Delacroix")
                    for part in v.split():
                        if len(part) >= 4:
                            self.add(part)
                if "-" in v and not v.isdigit():                 # a user folder like "jean-baptiste"
                    self.add(v.lower())


def write_json(path, obj, scrub):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(scrub.obj(obj), f, indent=1, ensure_ascii=False, default=_json_default)


def write_text(path, lines, scrub):
    with open(path, "w", encoding="utf-8") as f:
        f.write(scrub.text("\n".join(lines)) + "\n")


def _json_default(o):
    if hasattr(o, "item"):
        return o.item()
    if isinstance(o, float) and not math.isfinite(o):
        return str(o)
    return str(o)


def clean_json(o):
    """NaN and infinity as text (strict JSON readers refuse them)"""
    if isinstance(o, dict):
        return {k: clean_json(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean_json(v) for v in o]
    if isinstance(o, float) and not math.isfinite(o):
        return None
    if hasattr(o, "item") and not isinstance(o, (str, bytes)):
        try:
            return clean_json(o.item())
        except (ValueError, AttributeError):
            return str(o)
    return o


# ---------------------------------------------------------------------------------------------- reading files
def read_text(path):
    """a file the terminal wrote: UTF-16 with a byte-order mark (MetaTrader's own logs) or single-byte ANSI text
    (FILE_ANSI: the Windows code page; cp1252 under Wine on a Mac)"""
    raw = open(path, "rb").read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    if len(raw) >= 4 and raw[1:2] == b"\x00" and raw[3:4] == b"\x00":
        return raw.decode("utf-16-le", errors="replace")
    if raw[:3] == b"\xef\xbb\xbf":
        return raw[3:].decode("utf-8", errors="replace")
    return raw.decode("cp1252", errors="replace")


def fnum(s):
    """a number written by DoubleToString / IntegerToString, None when empty or not a number"""
    if s is None:
        return None
    s = str(s).strip()
    if s == "":
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return None


# ---------------------------------------------------------------------------------------------- clocks (SPEC 2.1)
def us_dst(utc):
    """US summer time at a UTC instant: 2nd Sunday of March 07:00 UTC to 1st Sunday of November 06:00 UTC"""
    y = time.gmtime(utc).tm_year

    def nth_sunday(m, n):
        first = calendar.timegm((y, m, 1, 0, 0, 0))
        wd = time.gmtime(first).tm_wday
        return first + ((6 - wd) % 7) * 86400 + 7 * 86400 * (n - 1)
    return nth_sunday(3, 2) + 7 * 3600 <= utc < nth_sunday(11, 1) + 6 * 3600


def srv_to_utc(s):
    u3 = int(s) - 3 * 3600
    return u3 if us_dst(u3) else u3 + 3600


def utc_to_srv(u):
    u = int(u)
    return u + (3 * 3600 if us_dst(u) else 2 * 3600)


def rule_offset(utc):
    """server - UTC by the rule, seconds (CR_Clock ClkRuleOffset)"""
    return 3 * 3600 if us_dst(int(utc)) else 2 * 3600


def srv_to_ny(s):
    return int(s) - 7 * 3600


def dow(t):
    """0 = Sunday ... 6 = Saturday, on the time's own clock"""
    return int(((int(t) // 86400) + 4) % 7)


def hm(t):
    """hh:mm of a time on its own clock"""
    m = (int(t) % 86400) // 60
    return f"{m // 60:02d}:{m % 60:02d}"


def ymd(t):
    return time.strftime("%Y-%m-%d", time.gmtime(int(t)))


def ymdhm(t):
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(int(t)))


def utc_txt(u):
    return ymdhm(u) + " UTC"


DOW_FR = ["dimanche", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"]
DOW_EN3 = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


# ---------------------------------------------------------------------------------------------- NYSE calendar
def _load_us_holidays():
    p = os.path.join(LAB, "r2", "tracks", "idx_us", "idxus_lib.py")
    try:
        spec = importlib.util.spec_from_file_location("demo_idxus_lib", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.us_holidays
    except Exception:                                            # a copy of idxus_lib.py:53-83 (same rules)
        def _easter(y):
            a, b, c = y % 19, y // 100, y % 100
            d, e = b // 4, b % 4
            f = (b + 8) // 25
            g = (b - f + 1) // 3
            h = (19 * a + b - d - g + 15) % 30
            i, k = c // 4, c % 4
            l_ = (32 + 2 * e + 2 * i - h - k) % 7
            m = (a + 11 * h + 22 * l_) // 451
            return dt.date(y, (h + l_ - 7 * m + 114) // 31, (h + l_ - 7 * m + 114) % 31 + 1)

        def _nth(y, mo, wd, n):
            if n > 0:
                d = dt.date(y, mo, 1)
                return d + dt.timedelta(days=(wd - d.weekday()) % 7 + 7 * (n - 1))
            d = dt.date(y + (mo == 12), mo % 12 + 1, 1) - dt.timedelta(days=1)
            return d - dt.timedelta(days=(d.weekday() - wd) % 7)

        def _obs(d):
            return d - dt.timedelta(days=1) if d.weekday() == 5 else (d + dt.timedelta(days=1) if d.weekday() == 6 else d)

        special = {dt.date(2018, 12, 5), dt.date(2025, 1, 9)}

        def us_holidays(y):
            full = set()
            ny = dt.date(y, 1, 1)
            if ny.weekday() == 6:
                full.add(dt.date(y, 1, 2))
            elif ny.weekday() < 5:
                full.add(ny)
            full |= {_nth(y, 1, 0, 3), _nth(y, 2, 0, 3), _easter(y) - dt.timedelta(days=2), _nth(y, 5, 0, -1)}
            if y >= 2022:
                full.add(_obs(dt.date(y, 6, 19)))
            full |= {_obs(dt.date(y, 7, 4)), _nth(y, 9, 0, 1)}
            tg = _nth(y, 11, 3, 4)
            full |= {tg, _obs(dt.date(y, 12, 25))}
            full |= {d for d in special if d.year == y}
            half = {tg + dt.timedelta(days=1)}
            j3, j4 = dt.date(y, 7, 3), dt.date(y, 7, 4)
            if j4.weekday() in (1, 2, 3, 4) and j3.weekday() < 5:
                half.add(j3)
            x = dt.date(y, 12, 24)
            if x.weekday() < 4:
                half.add(x)
            return full, half - full
        return us_holidays


us_holidays = _load_us_holidays()
_HOL_CACHE = {}


def nyse_kind(d):
    """'full', 'half' or None for a datetime.date (New York date)"""
    if d.year not in _HOL_CACHE:
        _HOL_CACHE[d.year] = us_holidays(d.year)
    full, half = _HOL_CACHE[d.year]
    return "full" if d in full else ("half" if d in half else None)


def gold_holiday_closure(d):
    """the robot's built-in gold closure of an NYSE date (SPEC 2.1), New York wall clock in minutes of that date:
    (start_min, end_min) or None. Observed Good Friday, Christmas, New Year: from 17:00 the day before; other full
    holidays 13:00-18:00; the Friday after Thanksgiving and a Christmas Eve half day 13:45-18:00."""
    k = nyse_kind(d)
    if k is None:
        return None
    if k == "full":
        if d in (dt.date(2018, 12, 5), dt.date(2025, 1, 9)):
            return None                                      # days of mourning: normal gold days
        # New Year (observed Jan 1 or 2), Christmas (the only December full holiday besides 2018-12-05), Good Friday (the
        # only full holiday of March or April): closed from 17:00 the day before
        if (d.month == 1 and d.day <= 2) or d.month == 12 or d.month in (3, 4):
            return (-7 * 60, 18 * 60)
        return (13 * 60, 18 * 60)
    if d.month == 11 or (d.month == 12 and d.day == 24):     # the Friday after Thanksgiving, a Christmas Eve half day
        return (13 * 60 + 45, 18 * 60)
    return None                                              # July 3 half days: normal gold days


# ---------------------------------------------------------------------------------------------- journal reading
CR_IN_LINE = re.compile(r"CR\|-?\d+\|[A-Z0-9]+\|")


def parse_cr(text):
    """one robot journal line (CR|utc|EVENT|code|k=v...) as a dict, None when it does not parse (compare.py rules)"""
    m = compare.LINE.match(text)
    if not m or m.group(2) not in compare.EVENTS:
        return None
    d = {"utc": int(m.group(1)), "ev": m.group(2), "code": m.group(3)}
    for kv in m.group(4).split("|")[1:]:
        k, v = kv.split("=", 1)
        d[k] = v if k in compare.TEXT_KEYS else compare.num(v)
    if d["ev"] in ("FILL", "REFUSED") and isinstance(d.get("risk"), str):
        d["risk"] = compare.num(d["risk"])            # money at risk here, the risk table in INIT and PLAN (compare.py: text)
    return d


def journal_paths(path):
    """the robot's daily files: a folder holding them (or MQL5/Files, or MQL5/Files/ClaudeRobot), or one file"""
    if os.path.isfile(path):
        return [path]
    out = []
    for sub in ("ClaudeRobot", ""):
        out = sorted(glob.glob(os.path.join(path, sub, "*.log")))
        if out:
            break
    return out


def is_utf16(path):
    """MetaTrader's own logs (MQL5/Logs, Logs) are UTF-16; the robot's daily files are single-byte text (FILE_ANSI)"""
    with open(path, "rb") as f:
        raw = f.read(4)
    return raw[:2] in (b"\xff\xfe", b"\xfe\xff") or (len(raw) >= 4 and raw[1:2] == b"\x00" and raw[3:4] == b"\x00")


DAY_FILE = re.compile(r"^(\d{4})(\d{2})(\d{2})\.log$")


def day_of_file(name):
    """server date (00:00, seconds) of a daily file name <yyyymmdd>.log, None for another name"""
    m = DAY_FILE.match(os.path.basename(name))
    if not m:
        return None
    try:
        return calendar.timegm((int(m.group(1)), int(m.group(2)), int(m.group(3)), 0, 0, 0))
    except (ValueError, OverflowError):
        return None


def file_of_day(srv_day):
    return time.strftime("%Y%m%d", time.gmtime(int(srv_day))) + ".log"


def read_journal_files(paths, scrub=None, printed=False):
    """rows of the robot lines of these files, in file order (files sorted by name = server date). Returns (rows, info).

    The text of a line that is not a robot line is NEVER kept or written anywhere (MetaTrader's own logs carry the
    login, the server, the holder's name and the user folder): such a line is only counted, located by file and line
    number, and scanned so that the scrubber masks whatever account value it holds.
    printed=False (--journals, the robot's daily files): a robot line starts with 'CR|'. A file in UTF-16 (a MetaTrader
    log) or with no line starting with 'CR|' is not a robot journal: it is skipped and named in info['skipped_files'].
    printed=True (--printed, the Experts tab): the robot's line follows a terminal prefix; MetaTrader's UTF-16 logs are
    accepted; a file with no robot line is named in info['files_without_robot_lines']."""
    rows, bad, foreign, skipped, no_robot, per_file = [], [], [], [], [], {}
    other = 0
    for p in paths:
        name = os.path.basename(p)
        try:
            text = read_text(p)
        except OSError as e:
            skipped.append({"file": name, "why": f"illisible ({e.__class__.__name__})"})
            continue
        lines = text.splitlines()
        if not printed:
            n_cr = sum(1 for ln in lines if ln.startswith("CR|"))
            if is_utf16(p) or n_cr == 0:
                for ln in lines:
                    if ln.strip() and scrub is not None:
                        scrub.scan_log_line(ln)
                if not any(ln.strip() for ln in lines):
                    why = "fichier vide"
                elif is_utf16(p):
                    why = ("pas un journal du robot : c'est un journal de MetaTrader (UTF-16) ; s'il vient de l'onglet Experts, "
                           "le donner avec --printed")
                else:
                    why = "pas un journal du robot (aucune ligne CR|)"
                skipped.append({"file": name, "why": why})
                continue
        kept = 0
        for no, ln in enumerate(lines, 1):
            ln = ln.rstrip("\r\n")
            if not ln.strip():
                continue
            k = ln.find("CR|") if printed else (0 if ln.startswith("CR|") else -1)
            if k < 0:
                if scrub is not None:
                    scrub.scan_log_line(ln)
                if printed:
                    other += 1
                else:
                    foreign.append({"file": name, "line": no})
                continue
            body = ln[k:]
            d = parse_cr(body)
            if d is None:
                if scrub is not None:
                    scrub.scan_log_line(ln)
                # the text starts with 'CR|' (the robot's own); cut at the first tab (a robot line has none, a terminal
                # line glued to it does) and scrubbed when written
                bad.append({"file": name, "line": no, "text": body.split("\t")[0][:160]})
                continue
            if printed and scrub is not None and k > 0:
                scrub.scan_log_line(ln[:k])
            d["_f"] = name
            d["_n"] = no
            d["_raw"] = body
            rows.append(d)
            kept += 1
        per_file[name] = kept
        if printed and kept == 0:
            no_robot.append(name)
    used = [os.path.basename(p) for p in paths if os.path.basename(p) not in {s["file"] for s in skipped}]
    return rows, {"files": used, "lines": len(rows), "unparsable": len(bad), "unparsable_first": bad[:10],
                  "other_lines_ignored": other, "foreign_lines": len(foreign), "foreign_first": foreign[:10],
                  "skipped_files": skipped, "files_without_robot_lines": no_robot, "robot_lines_per_file": per_file}


def live(rows):
    return [r for r in rows if r.get("rp") != 1]


# ---------------------------------------------------------------------------------------------- formatting (French)
def fr(x, nd=2, unit=""):
    """a number for the French summary: decimal comma, spaces between thousands; '?' when unknown"""
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "?"
    s = f"{x:,.{nd}f}".replace(",", " ").replace(".", ",")
    return s + (" " + unit if unit else "")


def frs(x, nd=2, unit=""):
    """the same with an explicit sign"""
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "?"
    return ("+" if x > 0 else "") + fr(x, nd, unit)


def median(xs):
    xs = sorted(x for x in xs if x is not None and math.isfinite(x))
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def mean(xs):
    xs = [x for x in xs if x is not None and math.isfinite(x)]
    return sum(xs) / len(xs) if xs else None


def load_fp_costs():
    try:
        return json.load(open(FP_COSTS))
    except Exception:
        return {}


def known_builds():
    """CR_BUILD of every committed version of dist/ClaudeRobot.mq5 (and the debug file), oldest first, from the git
    history (read-only git commands), plus the files on disk; [] when git is not available"""
    import subprocess
    out = []
    for rel in ("lab/robot/dist/ClaudeRobot.mq5", "lab/robot/dist/ClaudeRobot_debug.mq5"):
        try:
            r = subprocess.run(["git", "-C", REPO, "log", "--reverse", "--format=%H %ct", "--", rel], capture_output=True,
                               text=True, timeout=30)
            for ln in r.stdout.split("\n"):
                if not ln.strip():
                    continue
                h, ct = ln.split()
                s = subprocess.run(["git", "-C", REPO, "show", f"{h}:{rel}"], capture_output=True, text=True, timeout=30)
                first = s.stdout.split("\n", 1)[0]
                m = re.match(r'#define CR_BUILD "([0-9a-f]+)"', first)
                if m:
                    out.append((int(ct), m.group(1), "debug" if "debug" in rel else "release"))
        except Exception:
            pass
    for rel in ("ClaudeRobot.mq5", "ClaudeRobot_debug.mq5"):
        p = os.path.join(ROBOT, "dist", rel)
        try:
            m = re.match(r'#define CR_BUILD "([0-9a-f]+)"', open(p).readline())
            if m:
                out.append((int(os.path.getmtime(p)), m.group(1), "debug" if "debug" in rel else "release"))
        except OSError:
            pass
    out.sort()
    seen, res = set(), []
    for ct, b, kind in out:
        if b not in seen:
            seen.add(b)
            res.append({"build": b, "time": ct, "kind": kind})
    return res


def build_status(build, builds):
    """'OK' (the required build or a later one), 'OLDER', 'UNKNOWN' (not in the history), 'DEBUG' (the debug file)"""
    if build == REQUIRED_BUILD:
        return "OK"
    order = [b["build"] for b in builds]
    kinds = {b["build"]: b["kind"] for b in builds}
    if build not in order:
        return "UNKNOWN"
    if kinds.get(build) == "debug":
        return "DEBUG"
    if REQUIRED_BUILD in order and order.index(build) > order.index(REQUIRED_BUILD):
        return "OK"
    return "OLDER"
