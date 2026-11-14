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
--quick: tool 1 and the journal-only checks of tool 2 (no harness build or replay).
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


def check(name, cond, info=None):
    RESULTS.append({"test": name, "pass": bool(cond), "info": info})
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
                srv_now=None, mutate=None, tweak=None, cut_fiche=None, version="1.10", cut_m1=None):
    """ReleveFP's and SondeFP's files. srv_now: the time ReleveFP ran (fini.txt server_time; default one hour before
    m1_to); mutate(base, rec): change the bars of the m1 files; tweak(fiches): change the fiches before writing;
    cut_fiche: a market whose fiches.csv line is cut short (a copy that stopped in the middle); version '1.10' (sp_min,
    r1_<BASE>.csv, barres= in fini.txt) or '1.00'; cut_m1: a market whose m1 file stops half way (newest days first, so
    the oldest days are lost) while fini.txt keeps the full minutes= count"""
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
            write(os.path.join(folder, f"r1_{base}.csv"), r1_text(rec, dg, lit, sub), crlf)
            line += f" barres={len(rec)} jours_barres={len(set((rec['t'] // 86400).tolist()))} erreur_barres=0"
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
        check(f"tool1 {variant}: every check is OK, DIFFERENT or UNKNOWN with both values",
              all(c["status"] in ("OK", "DIFFERENT", "UNKNOWN") and "broker" in c and "assumed" in c for c in s["checks"]))
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
        check(f"tool1 {variant}: crypto quotes at weekends set against the lab", st("BTCUSD", "weekend") in ("OK", "DIFFERENT"))
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


def init_line(utc, build=C.REQUIRED_BUILD, observer=0, harness=0, demo=1, vps=0, comm=6):
    return jl(utc, "INIT", "-", ("build", build), ("version", "2.00"), ("demo", demo), ("vps", vps), ("tester", 0), ("observer", observer),
              ("entries_off", observer), ("harness", harness), ("comm_pts", comm), ("risk", "0:10;3000:5;10000:2;20000:1"),
              ("sleeves", "ALL"), ("S0.75r", "on"), ("K1", "on"), ("H2", "on"), ("k1t", ""), ("XAUUSD", "XAUUSD.r"),
              ("US100", "US100.r"), ("BTCUSD", "BTCUSD.r"), ("ETHUSD", "ETHUSD.r"))


def dec_ord(utc, code, oid, side, et, lv, st, x, rp=False, lv2=0.0, sd=0.0):
    """a DEC what=ord line with every field JrnOrder writes (CR_Journal.mqh), stamped at its decision time"""
    kv = [("what", "ord"), ("oid", oid), ("side", side), ("et", et), ("lv", float(lv)), ("lv2", float(lv2)), ("tf", utc),
          ("tt", utc + 3600), ("ax", 0), ("exp", utc + 3600), ("st", float(st)), ("sd", float(sd)), ("tr", 0.0), ("be", 0.0),
          ("tg", 0.0), ("td", 0.0), ("x", x), ("xg", 0), ("xh", 0), ("xr", 0.0), ("ref", 0), ("vle", 0), ("grp", 0), ("at", utc)]
    if rp:
        kv.append(("rp", 1))
    return jl(utc, "DEC", code, *kv)


def handmade_journal(folder, variant):
    """two days of a trading demo copy: one gold trade closed by the EA, one gold trade stopped by the broker, the
    listed lines; variant 'bad' adds an old build, a failed self-test, an ERROR, a DUP, a COST over the model ..."""
    os.makedirs(folder, exist_ok=True)
    t0 = calendar.timegm((2021, 11, 15, 8, 0, 0))
    L = [init_line(t0, build="40dce66811c6" if variant == "bad" else C.REQUIRED_BUILD),
         jl(t0, "SELFTEST", "-", ("ok", 0 if variant == "bad" else 1), ("why", "golden" if variant == "bad" else ""), ("golden", 366)),
         jl(t0 + 60, "PLAN", "-", ("T", 1630000000), ("state", "ok"), ("demo", 1), ("B_T", 10000.0), ("risk", "0:10;3000:5;10000:2;20000:1")),
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
          jl(t0 + 86400 + 60, "DAY", "-", ("day", C.utc_to_srv(t0) // 86400 * 86400), ("balance", 10000.0), ("equity", 10000.0), ("bars_fed", 5000)),
          jl(t0 + 2 * 86400 + 60, "DAY", "-", ("day", C.utc_to_srv(t0) // 86400 * 86400 + 86400), ("balance", 10000.0 + 85.5), ("equity", 10085.5),
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
        check(f"tool2 journal {variant}: money estimate from the DAY lines", m is not None and abs(m["balance_change_eur"] - 85.5) < 1e-9, m)
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
    stop and no CLOSE line: the broker's stop)."""
    os.makedirs(folder, exist_ok=True)
    L = []                                                              # (server write time, line)

    def add(t_srv, line):
        L.append((int(t_srv), line))
    T = srv("2021-11-17 08:00")
    k_gold, k_usd = 86.0, 0.86

    def start(at):
        a = srv(at)
        if "clock_first" in variant and at == "2021-11-17 08:00":     # OnInit: the guards' clock check writes before INIT
            add(a, jl(C.srv_to_utc(a), "CLOCK", "-", ("state", "wrong"), ("measured_s", 3600), ("rule_s", 7200)))
        add(a, init_line(C.srv_to_utc(a)))
        add(a, jl(C.srv_to_utc(a), "SELFTEST", "-", ("ok", 1), ("why", ""), ("golden", 366)))
        add(a + 60, jl(C.srv_to_utc(a + 60), "PLAN", "-", ("T", T), ("state", "unset" if "plan_unset" in variant else "ok"), ("demo", 1),
                       ("B_T", 10000.0), ("risk", "0:10;3000:5;10000:2;20000:1")))
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
        add(f0, dec_ord(C.srv_to_utc(f0), code, oid, side, et, ppx, stop, U(x_at)))
        add(f0, jl(C.srv_to_utc(f0), "PFILL", code, ("oid", oid), ("side", side), ("bar", C.srv_to_utc(f0)), ("px", ppx), ("stop", stop),
                   ("st0", stop), ("x", U(x_at)), ("s_raw", 12), ("s_paper", 0.18)))
        add(f0, jl(C.srv_to_utc(f0), "SIZE", code, ("oid", oid), ("side", side), ("et", et), ("lots", lots), ("want", lots), ("skip", "none"),
                   ("B", 10000.0), ("P_in", 10000.0), ("rate", 10.0), ("m", 1.0), ("f", 1.0), ("unit", 1000.0), ("w", 0.0), ("r", 10.0),
                   ("budget", 1000.0), ("late", et), ("quote", fill_px)))
        add(f0 + 60, jl(C.srv_to_utc(f0 + 60), "SEND", code, ("oid", oid), ("side", side), ("lots", lots), ("want", lots), ("sl", sl),
                        ("bid", fill_px - (0.12 if side > 0 else 0.0)), ("ask", fill_px + (0.0 if side > 0 else 0.12)),
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
    if "restart" in variant:                                            # stopped Friday night, started again on Monday
        add(srv("2021-11-19 23:30"), jl(U("2021-11-19 23:30"), "INIT", "-", ("deinit", 1), ("lines", 100), ("bars_fed", 9000), ("rebuilds", 1)))
        start("2021-11-22 08:00")
        add(srv("2021-11-22 08:02"), jl(U("2021-11-22 08:02"), "ADOPT", "D4H", ("oid", info["E"]), ("ticket", 70000102),
                                        ("open", U("2021-11-19 18:01")), ("stamp", U("2021-11-19 18:00")), ("why", "open")))
    # the daily lines of the day before, at 00:00:30 of each server day the robot runs
    bal = 10000.0
    stopped = {"2021-11-20", "2021-11-21"} if "restart" in variant else set()
    for d in range(18, 26):
        day = f"2021-11-{d:02d}"
        if day in stopped or (day == "2021-11-22" and "restart" in variant):
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
            add(t, jl(C.srv_to_utc(t), "DAY", "-", ("day", pd), ("balance", bal), ("equity", bal), ("bars_fed", 5000)))
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
    rc, so, se, r, txt, info = go("no_close_dip", ("no_close",), extra=("--bars", mdir2, "--no-replay"))
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
    check("review m3: CLOSE px=0 rc=0 ok=1 is a broker stop estimated at the stop, not an EA close at 0",
          rc == 0 and pc.get("exit_kind") == "broker_stop_race" and abs((pc.get("exit_real") or 0) - 56000.0) < 1e-9
          and r["anomalies"] == [], (pc.get("exit_kind"), pc.get("exit_real"), r.get("anomalies")))
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
    chk("review2 control N1: a clean journal has no missing line", lambda: (g["rc"] == 0 and g["r"]["journal"].get("breaks") == [],
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
        lambda: (g["rc"] == 0 and g["r"]["anomalies"] == [] and g["r"]["journal"].get("breaks") == [], g["an"][:500]))

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
        lambda: (g3["rc"] == 0 and g3["r"]["printed"]["n_live_not_printed"] == 1 and g3["r"]["anomalies"] != [],
                 g3["r"].get("printed", {}).get("n_live_not_printed")))

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
        lambda: (g["rc"] == 0 and g["r"]["anomalies"] == [] and "encore en marche" in g["rtxt"], (g["an"][:400], g["rtxt"][-300:])))
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
    chk("review2 N6/N7: those two lines are unreadable and keep no text",
        lambda: (g["r"]["inputs"]["unparsable"] == 2 and all(set(b) <= {"file", "line", "why"} for b in g["r"]["inputs"]["unparsable_first"]),
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
    chk("review2 N4: ReleveFP.mq5 is version 1.10: m1 header unchanged plus sp_min at the end, r1 file with the terminal's M1 bars "
        "(CopyRates, InpRateDays 200), barres= at the end of each market's fini line",
        lambda: (re.search(r'#property version\s+"1\.10"', src) is not None and hdr == lit["m1_v100"] + ",sp_min"
                 and lit["m1_v100"] == "time,bo,bh,bl,bc,ao,ah,al,ac,n,sp_mean,sp_max" and lit["r1_mq5"] == R1_HEADER
                 and re.search(r"input\s+int\s+InpRateDays\s*=\s*200\s*;", src) is not None and "CopyRates(" in src
                 and '"r1_"' in src and "version=1.10" in src and '" barres="' in src and '" jours_barres="' in src
                 and '" erreur_barres="' in src, (hdr, lit["r1_mq5"])))
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


def harness_live(name, span, env_extra, mutate=None, frm=LIVE_FROM):
    """the 'live' robot: dist/ClaudeRobot.mq5 in the harness (demo_check_release, gold commission 6 points) on in-sample
    bars; its journal then gets harness=0 in its INIT lines, as the release file writes"""
    import check_demo as D
    from build import replay
    exe, warn, cached = D.build_exe(6)
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
    env = {"MOCK_INPUT_InpPush": "false", "MOCK_ACCOUNT": "demo", "MOCK_BALANCE": "10000"}
    env.update(env_extra)
    files = os.path.join(work, "files")
    so, wall = replay(exe, files, bars, env=env, frm=frm, timeout=3600)
    for f in os.listdir(os.path.join(files, "ClaudeRobot")):
        p = os.path.join(files, "ClaudeRobot", f)
        t = open(p).read().replace("|harness=1|", "|harness=0|")
        open(p, "w").write(t)
    return files, wall, cached


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
          "InpDays is asked for, on stdout too",
          rc == 0 and all(cov3.get(c, {}).get("never") for c in ("F1B", "F1E", "OC4", "GFP", "D4H"))
          and not cov3.get("BKB", {}).get("never", True) and "couverture par sleeve" in txt3 and "F1B  jamais compare" in txt3
          and "InpDays=" in txt3 and "InpDays=" in so3 and "jamais comparees" in so3,
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
    chk("review2 control N1: a clean trading run has no missing journal line", lambda: (r5["journal"].get("breaks") == []
                                                                                     and not any("manquante" in a for a in r5["anomalies"]),
                                                                                     (r5["journal"].get("breaks"), r5["anomalies"])))
    t5 = r5["fills"]["per_sleeve"]["TOTAL"]
    ea_bp = [p["exit_diff_bp"] for p in pos.values() if p["exit_kind"] == "ea_close" and p.get("exit_diff_bp") is not None]
    est = [p for p in pos.values() if p["exit_kind"] in ("broker_stop_estimated", "broker_stop_race", "broker_stop_seen")]
    chk("review2 N2: on the trading run the exit average holds the robot's closes only; the broker stops are counted apart with "
        "their estimate",
        lambda: (abs(t5["exit_diff_bp_mean"] - sum(ea_bp) / len(ea_bp)) < 1e-9 and t5["estimated_exits"] == len(est) > 5
                 and all(p.get("exit_est") is not None for p in est), (t5.get("exit_diff_bp_mean"), t5.get("estimated_exits"), len(est))))
    chk("review2 control N10: every broker stop of the trading run is seen in the minutes (no 'stop jamais touche')",
        lambda: (all(p.get("stop_seen_utc") for p in est) and not any(p["exit_kind"] == "stop_not_reached" for p in pos.values()),
                 [(p["ticket"], p["exit_kind"], p.get("stop_seen_utc")) for p in est if not p.get("stop_seen_utc")][:5]))
    print(f"   (replay tests {time.time() - t0:.0f} s)")


PAPER_EV_T = ["DEC", "PFILL", "PEXIT", "PSTOP", "PREVISE", "PVOID", "PREFUSE", "HOLD"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args(argv)
    if os.path.isdir(SCRATCH):
        shutil.rmtree(SCRATCH)
    os.makedirs(SCRATCH)
    lit = literal_lines()
    t0 = time.time()
    test_tool1(lit)
    test_review_tool1(lit)
    test_tool2_journal(lit)
    test_review_journal(lit)
    if not a.quick:
        test_tool2_replay(lit)
    n_fail = sum(1 for r in RESULTS if not r["pass"])
    print(f"\n{len(RESULTS) - n_fail}/{len(RESULTS)} checks passed in {time.time() - t0:.0f} s")
    with open(os.path.join(os.path.dirname(SCRATCH), "demo_test_results.json"), "w") as f:
        json.dump(RESULTS, f, indent=1, default=str)
    if not a.keep:
        shutil.rmtree(SCRATCH, ignore_errors=True)
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
