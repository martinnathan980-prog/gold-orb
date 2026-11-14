"""Self-tests of the demo tools (read_mac_files.py and check_demo.py), end to end.

    python3 -I lab/robot/demo/test_demo_tools.py [--quick] [--keep]

Not named test_*.py under check/, so the robot's suite (check/run_tests.py) never runs it. It writes small inputs in
the exact formats the MQL5 sources write them (the header lines and the INTROUVABLE line are read from ReleveFP.mq5 and
SondeFP.mq5 themselves; numbers with DoubleToString's decimals; days newest first in the m1 files; line ends both
"\\n" and "\\r\\n"), runs each tool on them and checks the outputs.

Data: in-sample bars only, the 2021 bar files already exported under lab/robot/check/out/bars/ (read-only; weeks of
October-December 2021). The fake account's server name and login are planted in the inputs and must never appear in
any output. Every output goes to the session scratchpad; scratch is deleted at the end unless --keep.
--quick: tool 1 and the journal-only checks of tool 2 (no harness build or replay).
"""
import argparse
import calendar
import json
import os
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
SCRATCH = os.path.join(os.path.dirname(C.DEFAULT_OUT), "demo_test")
FAKE_SERVER = "FPMarketsSC-Demo7"
FAKE_LOGIN = "51234987"
FAKE_NAME = "Marie-Claire Fontanel"                # the account holder, as MetaTrader's own log names him
FAKE_USER = "marie-claire"                         # the Windows (Wine) user folder
ACCOUNT_WORDS = [FAKE_SERVER, FAKE_LOGIN, FAKE_NAME, "Fontanel", FAKE_USER, "Marie-Claire"]
REC = np.dtype([("t", "<i8"), ("o", "<i4"), ("h", "<i4"), ("l", "<i4"), ("c", "<i4"), ("s", "<i4")])
RESULTS = []


def check(name, cond, info=None):
    RESULTS.append({"test": name, "pass": bool(cond), "info": info})
    print(("PASS " if cond else "FAIL ") + name + ("" if cond or info is None else f"  -> {str(info)[:300]}"))
    return bool(cond)


# ---------------------------------------------------------------------------------------------- the MQL5 literals
def literal_lines():
    """header lines and the INTROUVABLE line, as the .mq5 sources write them"""
    rel = open(os.path.join(MQL5, "ReleveFP.mq5"), encoding="ascii").read()
    son = open(os.path.join(MQL5, "SondeFP.mq5"), encoding="ascii").read()
    fh = re.search(r'string FicheHeader\(\)\s*\{(.*?)return s;', rel, re.S).group(1)
    fiche_header = "".join(re.findall(r'"([^"]*)"', fh)).replace("\\n", "")
    introuvable = re.search(r'return base \+ "(,INTROUVABLE,*)\\n"', rel).group(1)
    tous_header = re.search(r'FileWriteString\(h, "(name,path,[^"]*)\\n"\)', rel).group(1)
    m1_header = re.search(r'FileWriteString\(h, "(time,bo[^"]*)\\n"\)', rel).group(1)
    sonde_header = re.search(r'string out = "(base,name,status[^"]*)\\n"', son).group(1)
    return {"fiche": fiche_header, "introuvable": introuvable, "tous": tous_header, "m1": m1_header, "sonde": sonde_header}


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
def m1_text(rec, digits, lit, spread_style="flat", sub=0):
    """m1_<BASE>.csv as Minutes()/Row() write it: days newest first, minutes in order inside a day. spread_style:
    'flat' = the bar spread at every tick (open = close = mean = max); 'open' = the bar spread at the open, two points
    more at the close, the mean between, the max above (so that only the 'open' convention matches the bar spread)"""
    sc = 10.0 ** digits
    lines = [lit["m1"]]
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
                         + f",{n},{ds(sps / n, digits + 2)},{ds(smax / sc, digits)}")
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
                srv_now=None, mutate=None, tweak=None, cut_fiche=None):
    """ReleveFP's and SondeFP's files. srv_now: the time ReleveFP ran (fini.txt server_time; default one hour before
    m1_to); mutate(base, rec): change the bars of the m1 files; tweak(fiches): change the fiches before writing;
    cut_fiche: a market whose fiches.csv line is cut short (a copy that stopped in the middle)"""
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
    fini = ["version=1.00", f"server={FAKE_SERVER}", "company=First Prudential Markets Ltd", "currency=EUR", "leverage=500",
            "demo=1", f"server_time={srv_now}", f"server_minus_gmt_sec={C.rule_offset(C.srv_to_utc(srv_now))}", "all_symbols=9"]
    for base in ("BTCUSD", "ETHUSD", "US100", "XAUUSD"):
        dg, rec = bars_2021(base, srv(m1_from), srv(m1_to))
        if mutate:
            rec = mutate(base, rec)
        style = "open" if variant == "good" else "flat"
        # the lab's gold spread holds the 6-point commission: the broker's raw spread is 6 points less
        write(os.path.join(folder, f"m1_{base}.csv"), m1_text(rec, dg, lit, style, 6 if base == "XAUUSD" else 0), crlf)
        fini.append(f"{base}={base}.r jours=30 minutes={len(rec)} ticks={3 * len(rec)} du={time.strftime('%Y.%m.%d %H:%M', time.gmtime(int(rec['t'][0])))} "
                    f"au={time.strftime('%Y.%m.%d %H:%M', time.gmtime(int(rec['t'][-1])))} derniere_erreur=0 jours_incomplets=0")
    fini.append("USDJPY=USDJPY.r jours=0 minutes=0 ticks=0 du=1970.01.01 00:00 au=1970.01.01 00:00 derniere_erreur=4401 jours_incomplets=0")
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
    L.append(jl(t0 - 86400 * 3, "DEC", "D4H", ("what", "ord"), ("oid", (t0 - 86400 * 3) * 100 + 9), ("side", 0), ("et", 3), ("lv", 1800.5),
                ("lv2", 1760.0), ("rp", 1)))
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
    L += [jl(f2, "PFILL", "GFP", ("oid", oid2), ("side", 1), ("bar", f2), ("px", 1801.1), ("stop", 1790.0), ("st0", 1790.0), ("x", f2 + 12000),
             ("s_raw", 10), ("s_paper", 0.16)),
          jl(f2, "SIZE", "GFP", ("oid", oid2), ("side", 1), ("et", 2), ("lots", 0.2), ("want", 0.2), ("skip", "none"), ("B", 10000.0),
             ("P_in", 10000.0), ("rate", 10.0), ("m", 1.0), ("f", 1.0), ("unit", 1000.0), ("w", 0.0), ("r", 11.1), ("budget", 1000.0),
             ("late", 1), ("quote", 1801.0)),
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
              "CR|1637000000|DEC|N30|what=ord|oid=12"]                 # a line cut short: still parses (oid only)
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


def csv_dir(name, span, lit, mutate=None, style="open"):
    d = os.path.join(SCRATCH, name)
    os.makedirs(d, exist_ok=True)
    for base in C.ROBOT_BASES:
        dg, rec = bars_2021(base, *span)
        rec = raw_gold(base, rec)
        if mutate:
            rec = mutate(base, rec)
        write(os.path.join(d, f"m1_{base}.csv"), m1_text(rec, dg, lit, style, 0))
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
    # MqlRates.spread = the minimum spread of the minute, which ReleveFP does not write: said, and the differences explained
    hidden = csv_dir("csv_min_hidden", SPAN, lit, style="min_hidden")
    out8 = os.path.join(SCRATCH, "out_min_hidden")
    rc, so8, se = run_tool("check_demo.py", ["--journals", obs, "--bars", hidden, "--out", out8])
    r8 = json.load(open(os.path.join(out8, "report.json"))) if rc == 0 else {}
    cal8 = r8.get("replay", {}).get("spread", {}).get("calibration", {})
    d8 = r8.get("replay", {}).get("comparison", {}).get("differences", [])
    txt8 = open(os.path.join(out8, "report_fr.txt")).read() if rc == 0 else ""
    check("tool2 hidden minimum spread: no column matches, the minimum is compatible, the differences are explained",
          rc == 0 and max(v["match"] for v in cal8["paper_lines"].values()) == 0
          and cal8["min_consistent"]["inside"] == cal8["min_consistent"]["n"] > 100 and "attention" in txt8
          and d8 and any("MqlRates.spread" in (d.get("hint") or "") for d in d8),
          (cal8.get("paper_lines"), cal8.get("min_consistent"), len(d8)))
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
    sl_ok = all(pos[t]["exit_kind"] in ("broker_stop_estimated", "closed_without_line") for t in sl_)
    check("tool2 trading: EA closes read from CLOSE lines, broker stops (no line) estimated", ea_ok and sl_ok and len(ea) > 5,
          {"ea": len(ea), "sl": len(sl_), "bad_ea": [t for t in ea if pos[t]["exit_kind"] != "ea_close"][:3]})
    units = {"XAUUSD": 100 * 0.89, "US100": 0.89, "BTCUSD": 0.89, "ETHUSD": 0.89}
    k_ok = all(abs(p["eur_per_price_per_lot"] / units[p["symbol"]] - 1) < 1e-6 for p in pos.values() if p.get("eur_per_price_per_lot"))
    check("tool2 trading: EUR per point from the FILL risk = the mock's tick value (units x 0.89)", k_ok,
          [(p["symbol"], p.get("eur_per_price_per_lot")) for p in list(pos.values())[:4]])
    c5 = r5["replay"]["comparison"]
    paper_diff = [d for d in c5["differences"] if d["event"] in PAPER_EV_T]
    check("tool2 trading: the paper lines of the trading copy equal the observer replay", not paper_diff, paper_diff[:3])
    check("tool2 trading: SIZE compared on the account-free fields only", not r5["replay"]["size_mode"]["live_copy_observer"]
          and r5["replay"]["size_mode"]["compared"] == ["side", "et", "late", "f"], r5["replay"]["size_mode"])
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
    test_tool2_journal(lit)
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
