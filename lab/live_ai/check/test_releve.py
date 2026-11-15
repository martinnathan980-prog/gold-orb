"""Run ReleveFP.mq5 for real (translated to C++, against the working imitation of MT5 in mock_mt5.h) and check
what it writes: the per-minute bid/ask rows against an independent recomputation of the same fake ticks, the
specification files, and that the Python reader (releve.lire_m1) parses them. ReleveFP 1.10 (check_110): the smallest
spread of each minute (sp_min) against the recomputation, the terminal's M1 bars of the robot's four markets (r1_<BASE>.csv)
against the imitation's bars and fini.txt's barres=, their days newest first, fini.txt's 1.10 keys, and the r1 days of
InpRateSymbols against what the robot's replay needs (its depth of 120 / 60 days, a demo of four weeks, a week). ReleveFP 1.11
(check_111): deals.csv and positions.csv against the imitation's deals and open positions (MOCK_DEALS_FILE, MOCK_POSITIONS_FILE: the order,
the enumerations' names, the digits of prices, volumes and money), a balance deal with an empty symbol, a symbol the terminal does not know,
a type outside the enumeration, a deal after the run's day left out, the planted comments, external ids, holder's name, login and server in
no file, fini.txt's new keys and no server line, an empty history (header only, deals=0), a history that cannot be read, a failed write and
the account currency's digits. Review8 (the deals stage's second pass): imitation_doc checks that mock_mt5.h follows the documented behaviour
the script relies on (FileWriteString adds a CR before a bare LF of a TXT or CSV file and returns the bytes written; FileOpen and FileWriteString
fail on demand; the deal getters answer for the listed deals only; 4302 for a symbol not in Market Watch; a planted server, company, holder's name
and login); check_111 adds the CR LF line ends and counts, the planted account in no file, deals.csv or positions.csv that cannot be opened, a
failed write without its own code after an unknown symbol or a closed position (-1, never that earlier code), a symbol not selected (8 decimals);
mutant_lf rebuilds the first 1.11 (rows ending in a bare LF, WriteRow with ==) and shows the imitation now catches it. The demo
tools' own harness (lab/robot/demo/test_demo_tools.py, review3/review4 groups) runs ReleveFP's scenarios (a loading series,
a weekend run, a failing last call) against lab/robot/demo/releve_mock.

    python3 live_ai/check/test_releve.py
"""
import os
import subprocess
import sys
import tempfile
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
NOW = 1794479400
START = NOW - 10 * 86400


def ticks():
    s = np.arange(START - START % 86400, NOW + 1, dtype=np.int64)
    dow = ((s // 86400) + 4) % 7
    k = (s % 7 == 3) & (dow != 0) & (dow != 6) & (s >= START) & (s <= NOW)
    s = s[k]
    bid = 100.0 + ((s * 2654435761) % 1000) / 100.0
    ask = bid + 0.10 + ((s // 60) % 5) * 0.01 + np.where(s % 13 == 0, 0.20, 0.0)
    ok = s % 997 != 0
    return pd.DataFrame({"m": (s // 60 * 60)[ok], "bid": bid[ok], "ask": ask[ok]})


def expected():
    t = ticks()
    t["sp"] = t.ask - t.bid
    g = t.groupby("m")
    return pd.DataFrame({"bo": g.bid.first(), "bh": g.bid.max(), "bl": g.bid.min(), "bc": g.bid.last(),
                         "ao": g.ask.first(), "ah": g.ask.max(), "al": g.ask.min(), "ac": g.ask.last(),
                         "n": g.bid.size(), "sp_mean": g.sp.mean(), "sp_max": g.sp.max(), "sp_min": g.sp.min()})


# ReleveFP 1.10's terminal bars (r1_<BASE>.csv), as mock_mt5.h serves them: one bar every weekday minute from R1_START to the
# last whole minute before the run, prices of the minute (the same formulas as mock_bar)
R1_START = (NOW - 40 * 86400) - (NOW - 40 * 86400) % 86400


def r1_expected():
    last = NOW - NOW % 60 - 60
    while ((last // 86400) + 4) % 7 in (0, 6):
        last -= 60
    m = np.arange(R1_START, last + 1, 60, dtype=np.int64)
    m = m[~np.isin(((m // 86400) + 4) % 7, (0, 6))]
    op = 100.0 + ((m // 60) % 97) / 100.0
    return pd.DataFrame({"time": m, "open": op, "high": op + 0.05, "low": op - 0.04, "close": op + 0.01, "tick_volume": 3 + (m // 60) % 7,
                         "spread": 10 + (m // 60) % 3, "real_volume": 0})


# the days of terminal bars the robot's replay needs (CR_Registry.mqh depth: gold 120 days, the others 60, before the robot is
# READY; then a demo of four weeks at most and a week before ReleveFP runs): what InpRateSymbols must ask at least
R1_NEED = {"XAUUSD": 120 + 28 + 7, "US100": 60 + 28 + 7, "BTCUSD": 60 + 28 + 7, "ETHUSD": 60 + 28 + 7}


def key(line, k):
    for part in line.split():
        if part.startswith(k + "="):
            return int(part.split("=", 1)[1])
    return None


def check_110(d, fini, src):
    """ReleveFP 1.10 (review4 RC3-R5): sp_min against the independent recomputation, the r1 files of the robot's markets against
    the imitation's bars and fini.txt's barres=, the days newest first, the r1 days the robot's replay needs, fini.txt's keys (still
    written by 1.11)"""
    assert tuple(int(x) for x in fini.get("version", "0.0").split(".")) >= (1, 10), fini.get("version")
    assert fini.get("max_barres") == "500000", fini.get("max_barres")
    exp = expected()
    got = pd.read_csv(d / "m1_BTCUSD.csv").set_index("time").sort_index()
    assert list(pd.read_csv(d / "m1_BTCUSD.csv", nrows=0).columns)[-1] == "sp_min"
    assert np.abs(got.sp_min - exp.sp_min).max() < 0.0051, np.abs(got.sp_min - exp.sp_min).max()
    assert (got.sp_min <= got.sp_mean + 1e-9).all() and (got.sp_min <= got.sp_max + 1e-9).all()
    import re
    rate = dict((k, int(v)) for k, v in re.findall(r"(\w+):(\d+)", re.search(r'InpRateSymbols\s*=\s*"([^"]*)"', src).group(1)))
    assert all(rate.get(b, 0) >= n for b, n in R1_NEED.items()), (rate, R1_NEED)
    r1 = sorted(p.name for p in d.iterdir() if p.name.startswith("r1_"))
    assert r1 == ["r1_BTCUSD.csv", "r1_ETHUSD.csv", "r1_US100.csv", "r1_XAUUSD.csv"], r1       # the robot's markets only
    want = r1_expected()
    for b in ("XAUUSD", "US100", "BTCUSD", "ETHUSD"):
        f = d / f"r1_{b}.csv"
        raw = f.read_text().splitlines()
        assert raw[0] == "time,open,high,low,close,tick_volume,spread,real_volume", raw[0]
        df = pd.read_csv(f)
        line = fini[b]
        assert key(line, "barres") == len(df) == len(want), (b, key(line, "barres"), len(df), len(want))
        assert key(line, "jours_r1") == rate[b] and key(line, "synchro_r1") == 1, line
        assert key(line, "erreur_barres") == 0 and key(line, "jours_courts") == 0, line
        assert key(line, "debut_r1") == R1_START and key(line, "jours_barres") == len(set((want.time // 86400).tolist())), line
        days = (df.time // 86400).to_numpy()
        assert (np.diff(days) <= 0).all(), b                                        # days newest first
        for dday in set(days.tolist()):
            assert (np.diff(df.time[days == dday].to_numpy()) > 0).all(), (b, dday)  # minutes in order inside a day
        s = df.sort_values("time").reset_index(drop=True)
        assert (s.time.to_numpy() == want.time.to_numpy()).all(), b
        for c in ("open", "high", "low", "close"):
            assert np.abs(s[c].to_numpy() - want[c].to_numpy()).max() < 0.0051, (b, c)
        assert (s.spread.to_numpy() == want.spread.to_numpy()).all() and (s.tick_volume.to_numpy() == want.tick_volume.to_numpy()).all(), b
    print(f"ReleveFP 1.10: sp_min equal to the recomputation; r1 files of the four robot markets = the terminal's bars ({len(want)} each, "
          f"newest day first, = barres= of fini.txt); InpRateSymbols {rate} reaches the robot's depth + a demo + a week")


def main():
    tmp = Path(tempfile.mkdtemp())
    cpp = tmp / "releve.cpp"
    subprocess.run([sys.executable, "-I", str(HERE / "to_cpp.py"), str(HERE.parent / "mql5" / "ReleveFP.mq5"), str(cpp)],
                   check=True, capture_output=True)
    (tmp / "run.cpp").write_text('#include "mock_mt5.h"\n#include "releve.cpp"\n'
                                 'int main() { OnStart(); printf("%d\\n", g_copy_calls); return 0; }\n')
    subprocess.run(["g++", "-std=c++17", "-O1", "-I", str(HERE), "-I", str(tmp), str(tmp / "run.cpp"), "-o", str(tmp / "run")], check=True)
    files = tmp / "Files"
    files.mkdir()
    out = subprocess.run([str(tmp / "run")], env=dict(os.environ, MOCK_FILES=str(files)), check=True, capture_output=True, text=True)
    calls = int(out.stdout.strip().splitlines()[-1])
    d = files / "claude" / "releve"
    names = sorted(p.name for p in d.iterdir())
    print("files:", names)
    fini = dict(ln.split("=", 1) for ln in (d / "fini.txt").read_text().splitlines() if "=" in ln)
    # symbol search: ".r" suffix, other known names, missing symbol
    assert fini["XAUUSD"].startswith("XAUUSD.r "), fini["XAUUSD"]
    assert fini["US100"].startswith("NAS100 "), fini["US100"]
    assert fini["JP225"].startswith("JPN225 "), fini["JP225"]
    assert fini["GER40"].startswith("DE40 "), fini["GER40"]
    assert fini["BTCUSD"].startswith("BTCUSD "), fini["BTCUSD"]
    fiches = pd.read_csv(d / "fiches.csv")
    assert len(fiches) == 9 and fiches.shape[1] == 31, fiches.shape
    assert fiches.sessions.iloc[0] == "1:1-1435|2:1-1435|3:1-1435|4:1-1435|5:1-1435|", fiches.sessions.iloc[0]
    assert "," not in fiches.description.iloc[0]
    tous = pd.read_csv(d / "tous.csv")
    assert len(tous) == 10 and tous.shape[1] == 12, tous.shape
    # minute rows against the independent recomputation
    exp = expected()
    got = pd.read_csv(d / "m1_BTCUSD.csv").set_index("time").sort_index()
    assert len(got) == len(exp), (len(got), len(exp))
    assert (got.index == exp.index).all()
    for c in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"):
        assert np.abs(got[c] - exp[c]).max() < 0.0051, c
    assert (got.n == exp.n).all()
    assert np.abs(got.sp_mean - exp.sp_mean).max() < 0.00006 and np.abs(got.sp_max - exp.sp_max).max() < 0.0051
    # a day that comes back incomplete (error 4403) is requested again: recovered for ETHUSD, counted for US500
    eth = pd.read_csv(d / "m1_ETHUSD.csv")
    us500 = pd.read_csv(d / "m1_US500.csv")
    assert len(eth) == len(exp) and "jours_incomplets=0" in fini["ETHUSD"], fini["ETHUSD"]
    assert len(us500) == len(exp) - 720 and "jours_incomplets=1" in fini["US500"], (len(us500), fini["US500"])
    assert "jours_incomplets=0" in fini["BTCUSD"]
    # the loop stops after 6 empty days in a row: 9 symbols x (11 days with history + weekends + 6 empty) calls at most
    assert calls <= 9 * 20, calls
    # the Python reader
    import releve
    df = releve.lire_m1(d, "BTCUSD")
    assert len(df) == len(exp) and str(df.index.tz) == "UTC"
    assert df.index[-1] == pd.Timestamp(int(exp.index[-1]) - 7200, unit="s", tz="UTC")     # November: server = UTC+2
    print(f"minute rows: {len(got)} identical to the recomputation; {calls} tick requests; reader ok "
          f"({df.index[0]} -> {df.index[-1]})")
    check_110(d, fini, (HERE.parent / "mql5" / "ReleveFP.mq5").read_text(encoding="ascii"))
    imitation_doc(tmp)
    check_111(tmp)
    mutant_lf(tmp)
    sonde()
    print("ReleveFP : tous les tests passent")


# ---------------------------------------------------------------------------------------------- ReleveFP 1.11: deals and positions
DEAL_TYPES = ["DEAL_TYPE_BUY", "DEAL_TYPE_SELL", "DEAL_TYPE_BALANCE", "DEAL_TYPE_CREDIT", "DEAL_TYPE_CHARGE", "DEAL_TYPE_CORRECTION",
              "DEAL_TYPE_BONUS", "DEAL_TYPE_COMMISSION", "DEAL_TYPE_COMMISSION_DAILY", "DEAL_TYPE_COMMISSION_MONTHLY",
              "DEAL_TYPE_COMMISSION_AGENT_DAILY", "DEAL_TYPE_COMMISSION_AGENT_MONTHLY", "DEAL_TYPE_INTEREST", "DEAL_TYPE_BUY_CANCELED",
              "DEAL_TYPE_SELL_CANCELED", "DEAL_DIVIDEND", "DEAL_DIVIDEND_FRANKED", "DEAL_TAX"]           # docs: ENUM_DEAL_TYPE, in order
DEAL_ENTRIES = ["DEAL_ENTRY_IN", "DEAL_ENTRY_OUT", "DEAL_ENTRY_INOUT", "DEAL_ENTRY_OUT_BY"]
DEAL_REASONS = ["DEAL_REASON_CLIENT", "DEAL_REASON_MOBILE", "DEAL_REASON_WEB", "DEAL_REASON_EXPERT", "DEAL_REASON_SL", "DEAL_REASON_TP",
                "DEAL_REASON_SO", "DEAL_REASON_ROLLOVER", "DEAL_REASON_VMARGIN", "DEAL_REASON_SPLIT", "DEAL_REASON_CORPORATE_ACTION"]
DEALS_HEADER = "time,time_msc,ticket,order,position,symbol,type,entry,reason,magic,volume,price,sl,tp,commission,swap,fee,profit"
POSITIONS_HEADER = "ticket,identifier,time,time_msc,symbol,type,magic,volume,price_open,sl,tp,price_current,swap,profit"
# what the imitation's deals and positions carry that ReleveFP must never write (a holder's name, a login, a server, external ids)
PLANTED = ["Marie-Claire Fontanel", "51234987", "FPMarketsSC-Demo7", "EXT-ID-7f3a", "commentaire-du-courtier"]
# the imitation's symbols: digits (2 for the known ones), volume step (mock_mt5.h mk11_vstep); an unknown symbol gets 8 and 8
VSTEP = {"XAUUSD.r": 0.01, "BTCUSD": 0.01, "ETHUSD": 0.01, "NAS100": 0.1, "EURUSD.r": 0.01}


def _deal(ticket, order, position, t, msc, sym, typ, entry, reason, magic, vol, px, sl, tp, comm, swap, fee, profit, comment="",
          ext=""):
    return dict(ticket=ticket, order=order, position=position, time=t, time_msc=msc, symbol=sym, type=typ, entry=entry, reason=reason,
                magic=magic, volume=vol, price=px, sl=sl, tp=tp, commission=comm, swap=swap, fee=fee, profit=profit, comment=comment,
                external_id=ext)


def imitation_account():
    """the imitation's account: a deposit (empty symbol), the robot's gold trade closed by its stop (a planted comment and external id),
    a hand trade on BTCUSD, two deals at the same millisecond (ticket order), a deal on a symbol the terminal no longer knows (8
    decimals), a deal type outside the enumeration, a deal after the run's day (outside HistorySelect's range); two open positions
    and a third the terminal lists but no longer finds (closed meanwhile)"""
    t0 = NOW - 9 * 86400
    deals = [
        _deal(4001, 0, 0, t0, t0 * 1000 + 5, "", 2, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1000.0,
              "Depot " + PLANTED[0], PLANTED[3]),
        _deal(4002, 5002, 5002, t0 + 3600, (t0 + 3600) * 1000 + 120, "XAUUSD.r", 0, 0, 3, 20261210, 0.05, 4080.23, 4070.11, 0.0, -0.14, 0.0,
              0.0, 0.0, "CR ORX " + PLANTED[1], PLANTED[3]),
        _deal(4003, 5003, 5002, t0 + 7200, (t0 + 7200) * 1000 + 999, "XAUUSD.r", 1, 1, 4, 20261210, 0.05, 4070.07, 4070.11, 0.0, -0.14,
              -0.37, -0.01, -43.68, "[sl 4070.11] " + PLANTED[2], ""),
        _deal(4005, 5005, 5005, t0 + 86400, (t0 + 86400) * 1000, "BTCUSD", 1, 0, 0, 0, 0.02, 100000.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
              PLANTED[4], ""),
        _deal(4004, 5004, 5005, t0 + 86400, (t0 + 86400) * 1000, "BTCUSD", 0, 1, 0, 0, 0.02, 99880.5, 0.0, 0.0, 0.0, 0.0, 0.0, 2.06),
        _deal(4006, 5006, 5006, t0 + 2 * 86400, (t0 + 2 * 86400) * 1000 + 7, "OLD.SYM", 0, 0, 1, 0, 1.5, 1.234567, 0.0, 0.0, 0.0, 0.0, 0.0,
              0.0),
        _deal(4007, 0, 0, t0 + 3 * 86400, (t0 + 3 * 86400) * 1000, "", 99, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -1.5, PLANTED[2]),
        _deal(4008, 0, 0, NOW + 3 * 86400, (NOW + 3 * 86400) * 1000, "", 2, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 5.0),
    ]
    positions = [
        dict(ticket=5101, identifier=5101, time=NOW - 7200, time_msc=(NOW - 7200) * 1000 + 3, symbol="XAUUSD.r", type=1, magic=20261209,
             volume=0.03, price_open=4085.5, sl=4095.25, tp=0.0, price_current=4081.17, swap=-0.21, profit=11.27, comment=PLANTED[0],
             external_id=PLANTED[3]),
        dict(ticket=5100, identifier=5100, time=NOW - 9000, time_msc=(NOW - 9000) * 1000, symbol="NAS100", type=0, magic=0, volume=0.3,
             price_open=25010.5, sl=0.0, tp=0.0, price_current=25000.0, swap=0.0, profit=-2.72, comment=PLANTED[1], external_id=""),
        dict(ticket=5102, identifier=5102, time=NOW - 600, time_msc=(NOW - 600) * 1000, symbol="BTCUSD", type=0, magic=20261205,
             volume=0.01, price_open=100010.0, sl=99000.0, tp=0.0, price_current=100000.0, swap=0.0, profit=-0.09, comment="",
             external_id=""),
    ]
    return deals, positions


def write_imitation(path, rows, cols):
    """the imitation's input files, rows shuffled (HistorySelect promises no order: the script must sort)"""
    order = [rows[i] for i in (3, 0, 6, 2, 7, 1, 5, 4)[:len(rows)]] if len(rows) == 8 else list(reversed(rows))
    with open(path, "w") as f:
        f.write(",".join(cols) + "\n")
        for r in order:
            f.write(",".join(str(r[c]) for c in cols) + "\n")


def expected_deals(deals, ccy_digits=2):
    """deals.csv as ReleveFP 1.11 writes it: the deals of HistorySelect(0, server time + a day), oldest first (time in milliseconds,
    then ticket), types by name, prices with the symbol's digits, volumes with its volume step's, money with the account currency's"""
    out = [DEALS_HEADER]
    sel = sorted((d for d in deals if 0 <= d["time"] <= NOW + 86400), key=lambda d: (d["time_msc"] if d["time_msc"] > 0 else d["time"] * 1000,
                                                                                       d["ticket"]))
    md = max(2, ccy_digits)
    for d in sel:
        known = d["symbol"] in VSTEP
        pd = 2 if known else 8
        vd = len(f"{VSTEP[d['symbol']]:.8f}".rstrip("0").split(".")[1]) if known else 8
        typ = DEAL_TYPES[d["type"]] if 0 <= d["type"] < len(DEAL_TYPES) else f"ENUM_DEAL_TYPE::{d['type']}"
        out.append(",".join([str(d["time"]), str(d["time_msc"]), str(d["ticket"]), str(d["order"]), str(d["position"]), d["symbol"], typ,
                             DEAL_ENTRIES[d["entry"]], DEAL_REASONS[d["reason"]], str(d["magic"]), f"{d['volume']:.{vd}f}",
                             f"{d['price']:.{pd}f}", f"{d['sl']:.{pd}f}", f"{d['tp']:.{pd}f}", f"{d['commission']:.{md}f}",
                             f"{d['swap']:.{md}f}", f"{d['fee']:.{md}f}", f"{d['profit']:.{md}f}"]))
    return out, sel


def expected_positions(positions, gone=None):
    out = [POSITIONS_HEADER]
    for q in sorted((q for q in positions if q["ticket"] != gone), key=lambda q: (q["time_msc"], q["ticket"])):
        vd = len(f"{VSTEP[q['symbol']]:.8f}".rstrip("0").split(".")[1])
        out.append(",".join([str(q["ticket"]), str(q["identifier"]), str(q["time"]), str(q["time_msc"]), q["symbol"],
                             ["POSITION_TYPE_BUY", "POSITION_TYPE_SELL"][q["type"]], str(q["magic"]), f"{q['volume']:.{vd}f}",
                             f"{q['price_open']:.2f}", f"{q['sl']:.2f}", f"{q['tp']:.2f}", f"{q['price_current']:.2f}", f"{q['swap']:.2f}",
                             f"{q['profit']:.2f}"]))
    return out


def run_releve(tmp, name, env):
    files = tmp / ("F111_" + name)
    files.mkdir()
    subprocess.run([str(tmp / "run")], env=dict(os.environ, MOCK_FILES=str(files), **env), check=True, capture_output=True, text=True)
    d = files / "claude" / "releve"
    fini = dict(ln.split("=", 1) for ln in (d / "fini.txt").read_text().splitlines() if "=" in ln)
    return d, fini


def check_111(tmp):
    """ReleveFP 1.11: deals.csv and positions.csv equal the imitation's deals and positions (values and formats: the order, the names
    of the enumerations, the digits), a balance deal with an empty symbol, a symbol the terminal does not know (8 decimals), a type outside
    the enumeration, a deal after the run's day left out; the planted comments, external ids, name, login and server never in any file;
    fini.txt's new keys and no server name; an empty history (header only, deals=0), a history that cannot be read (deals=-1 and its
    error, -1 without a code), a write that fails (erreur_deals=5026), a position closed between the list and its line"""
    src = (HERE.parent / "mql5" / "ReleveFP.mq5").read_text(encoding="ascii")
    import re
    assert re.search(r'#property version\s+"1\.11"', src) and "version=1.11" in src
    code = "\n".join(ln.split("//")[0] for ln in src.splitlines())               # the statements, without the comments
    for prop in ("DEAL_COMMENT", "DEAL_EXTERNAL_ID", "POSITION_COMMENT", "POSITION_EXTERNAL_ID", "ACCOUNT_SERVER", "ACCOUNT_LOGIN",
                 "ACCOUNT_NAME", "ORDER_COMMENT"):
        assert prop not in code, f"ReleveFP reads {prop}"
    deals, positions = imitation_account()
    dcols = ["ticket", "order", "position", "time", "time_msc", "symbol", "type", "entry", "reason", "magic", "volume", "price", "sl", "tp",
             "commission", "swap", "fee", "profit", "comment", "external_id"]
    pcols = ["ticket", "identifier", "time", "time_msc", "symbol", "type", "magic", "volume", "price_open", "sl", "tp", "price_current", "swap",
             "profit", "comment", "external_id"]
    write_imitation(tmp / "mk_deals.csv", deals, dcols)
    write_imitation(tmp / "mk_positions.csv", positions, pcols)
    env = {"MOCK_DEALS_FILE": str(tmp / "mk_deals.csv"), "MOCK_POSITIONS_FILE": str(tmp / "mk_positions.csv"), "MOCK_POSITION_GONE": "5102"}
    d, fini = run_releve(tmp, "full", env)
    want, sel = expected_deals(deals)
    got = (d / "deals.csv").read_text().splitlines()
    assert got == want, "\n".join(f"{a!r} | {b!r}" for a, b in zip(got, want) if a != b) or (len(got), len(want))
    assert got[1].split(",")[5] == "" and got[1].split(",")[6] == "DEAL_TYPE_BALANCE", got[1]               # the deposit: no symbol
    assert any(",OLD.SYM,DEAL_TYPE_BUY,DEAL_ENTRY_IN,DEAL_REASON_MOBILE,0,1.50000000,1.23456700," in ln for ln in got), got
    assert any(",ENUM_DEAL_TYPE::99," in ln for ln in got) and not any(",4008," in ln for ln in got)
    i3, i4 = next(i for i, ln in enumerate(got) if ",4003," in ln), next(i for i, ln in enumerate(got) if ",4004,5004," in ln)
    i5 = next(i for i, ln in enumerate(got) if ",4005,5005," in ln)
    assert i3 < i4 < i5, (i3, i4, i5)                                                        # same millisecond: ticket order
    gotp = (d / "positions.csv").read_text().splitlines()
    wantp = expected_positions(positions, gone=5102)
    assert gotp == wantp, (gotp, wantp)
    assert ",NAS100,POSITION_TYPE_BUY,0,0.3,25010.50," in gotp[1], gotp                                # volume step 0.1: one decimal
    # fini.txt: the new keys, no server name
    assert fini.get("version") == "1.11", fini.get("version")
    assert "server" not in fini, "server name written"
    assert fini.get("deals") == str(len(sel)) and fini.get("deals_du") == str(sel[0]["time"]) and fini.get("deals_au") == str(sel[-1]["time"]), fini
    assert fini.get("positions") == "2" and fini.get("positions_heure") == str(NOW) and fini.get("erreur_deals") == "0", fini
    keys = list(fini)
    assert keys.index("positions") < keys.index("deals") < keys.index("erreur_deals") < keys.index("stopped"), keys
    # privacy: nothing planted in the imitation reaches any file
    for p in d.iterdir():
        txt = p.read_text(errors="replace")
        for w in PLANTED + ["Depot", "[sl"]:
            assert w not in txt, (p.name, w)
    # an empty history: the header only, deals=0
    d0, f0 = run_releve(tmp, "empty", {})
    assert (d0 / "deals.csv").read_text().splitlines() == [DEALS_HEADER] and f0.get("deals") == "0" and f0.get("deals_du") == "0" \
        and f0.get("deals_au") == "0" and f0.get("erreur_deals") == "0", f0
    assert (d0 / "positions.csv").read_text().splitlines() == [POSITIONS_HEADER] and f0.get("positions") == "0", f0
    # the history cannot be read: deals=-1 and the error (-1 when MetaTrader gives no code)
    d1, f1 = run_releve(tmp, "histfail", dict(env, MOCK_HISTORY_FAIL="4401"))
    assert f1.get("deals") == "-1" and f1.get("erreur_deals") == "4401" and (d1 / "deals.csv").read_text().splitlines() == [DEALS_HEADER], f1
    d2, f2 = run_releve(tmp, "histfail0", dict(env, MOCK_HISTORY_FAIL="0"))
    assert f2.get("deals") == "-1" and f2.get("erreur_deals") == "-1", f2
    # a write that fails (the third write into deals.csv): the rows before it, erreur_deals=5026
    d3, f3 = run_releve(tmp, "writefail", dict(env, MOCK_WRITE_FAIL="deals.csv:3"))
    assert f3.get("deals") == "1" and f3.get("erreur_deals") == "5026" and len((d3 / "deals.csv").read_text().splitlines()) == 2, f3
    # money with the account currency's digits when it has more than 2
    d4, f4 = run_releve(tmp, "ccy4", dict(env, MOCK_CCY_DIGITS="4"))
    want4, _ = expected_deals(deals, 4)
    assert (d4 / "deals.csv").read_text().splitlines() == want4
    # review8 RELEVE111-CRLF: FileWriteString adds a CR before a bare LF of a TXT file and returns the bytes written (docs), so every header
    # and row of deals.csv and positions.csv ends in "\r\n" written by the script itself, and deals=/positions= count every row
    for name, n in (("deals.csv", len(sel)), ("positions.csv", 2)):
        raw = (d / name).read_bytes()
        parts = raw.split(b"\r\n")
        assert raw.endswith(b"\r\n") and parts[-1] == b"" and all(b"\n" not in p and b"\r" not in p for p in parts), (name, raw[:160])
        assert len(parts) - 2 == n, (name, len(parts) - 2, n)
    # review8 IMIT-LOOSE (c): the imitation's account plants its server, company, holder's name and login (imitation_doc checks it does):
    # none of them in any file, fini.txt included
    for p in d.iterdir():
        txt = p.read_text(errors="replace")
        for w in ACCOUNT_PLANTED:
            assert w not in txt, (p.name, w)
    # review8 OPEN-FAIL-UNTESTED: deals.csv or positions.csv cannot be opened (MOCK_OPEN_FAIL): -1, the error, the other file written
    d5, f5 = run_releve(tmp, "openfail_deals", dict(env, MOCK_OPEN_FAIL="deals.csv"))
    assert f5.get("deals") == "-1" and f5.get("deals_du") == "0" and f5.get("deals_au") == "0" and f5.get("erreur_deals") == "5004", f5
    assert not (d5 / "deals.csv").exists() and f5.get("positions") == "2" and (d5 / "positions.csv").read_text().splitlines() == wantp, f5
    d6, f6 = run_releve(tmp, "openfail_positions", dict(env, MOCK_OPEN_FAIL="positions.csv"))
    assert f6.get("positions") == "-1" and f6.get("erreur_deals") == "5004" and f6.get("deals") == str(len(sel)), f6
    assert not (d6 / "positions.csv").exists() and (d6 / "deals.csv").read_text().splitlines() == want, f6
    # review8 LASTERR-STALE: a write that fails without an error code of its own (MOCK_WRITE_FAIL "file:N:0") right after calls that leave
    # one set (the unknown symbol OLD.SYM: SymbolInfoInteger 4301; a position closed meanwhile: PositionSelectByTicket 4753) is -1, not
    # that earlier code
    d7, f7 = run_releve(tmp, "stale_deals", dict(env, MOCK_WRITE_FAIL="deals.csv:7:0"))
    assert f7.get("deals") == "5" and f7.get("erreur_deals") == "-1" and len((d7 / "deals.csv").read_text().splitlines()) == 6, f7
    d8, f8 = run_releve(tmp, "stale_positions", dict(env, MOCK_POSITION_GONE="5100", MOCK_WRITE_FAIL="positions.csv:2:0"))
    assert f8.get("positions") == "0" and f8.get("erreur_deals") == "-1" and f8.get("deals") == str(len(sel)), f8
    # review8 IMIT-LOOSE (b): a symbol of the deals not selected in Market Watch (SymbolInfoInteger / SymbolInfoDouble fail with 4302): its
    # prices and volumes keep 8 decimals (nothing rounded away), no error reported
    d9, f9 = run_releve(tmp, "notselected", dict(env, MOCK_SYM_NOT_SELECTED="XAUUSD.r"))
    got9 = (d9 / "deals.csv").read_text().splitlines()
    assert any(",XAUUSD.r,DEAL_TYPE_BUY,DEAL_ENTRY_IN,DEAL_REASON_EXPERT,20261210,0.05000000,4080.23000000,4070.11000000," in ln
               for ln in got9) and f9.get("erreur_deals") == "0" and f9.get("deals") == str(len(sel)), (got9[:4], f9)
    print(f"ReleveFP 1.11: deals.csv = the imitation's {len(sel)} deals (oldest first, names, digits), positions.csv = its open positions; "
          "no comment, external id, name, login or server in any file; empty history, unreadable history, failed write handled; rows end in "
          "CR LF (counts = rows); deals.csv or positions.csv that cannot be opened; a failed write without its own code is -1; a symbol not "
          "in Market Watch keeps 8 decimals")


# what the imitation's account itself holds (mock_mt5.h AccountInfoString / AccountInfoInteger, review8 IMIT-LOOSE c): its server, company,
# holder's name and login, never to be written by ReleveFP
ACCOUNT_PLANTED = ["FPMarketsSC-Demo7", "First Prudential Markets Ltd", "Marie-Claire Fontanel", "51234987"]
PROBE = r'''#include "mock_mt5.h"
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
   long out_list = HistoryDealGetInteger(4002, DEAL_TIME);
   double out_list_px = HistoryDealGetDouble(4002, DEAL_PRICE);
   string out_list_sym = HistoryDealGetString(4002, DEAL_SYMBOL);
   HistorySelect(0, TimeTradeServer() + 86400);
   long in_list = HistoryDealGetInteger(4002, DEAL_TIME);
   long dg = -1;
   ResetLastError();
   bool sel = SymbolInfoInteger("XAUUSD.r", SYMBOL_DIGITS, dg);
   int e_sel = GetLastError();
   printf("txt=%u\ncsv=%u\nbin=%u\nopen=%d\nopen_err=%d\nfail=%u\nfail_err=%d\nout_list=%ld\nout_list_px=%g\nout_list_sym=[%s]\nin_list=%ld\n"
          "sel=%d\nsel_err=%d\nserver=%s\ncompany=%s\nname=%s\nlogin=%ld\ncurrency=%s\n", n_txt, n_csv, n_bin, ho, e_open, n_fail, e_fail,
          out_list, out_list_px, out_list_sym.c_str(), in_list, (int)sel, e_sel, AccountInfoString(ACCOUNT_SERVER).c_str(),
          AccountInfoString(ACCOUNT_COMPANY).c_str(), AccountInfoString(ACCOUNT_NAME).c_str(), AccountInfoInteger(ACCOUNT_LOGIN),
          AccountInfoString(ACCOUNT_CURRENCY).c_str());
   return 0;
  }
'''


def imitation_doc(tmp):
    """review8 IMIT-CRLF and IMIT-LOOSE: the imitation (mock_mt5.h) follows the documented behaviour the script relies on.
    FileWriteString (docs.mql5.com/en/docs/files/filewritestring): 'When writing to a CSV or TXT file: if there is a symbol in the string
    '\\n' (LF) without previous character '\\r' (CR), then before '\\n' the missing '\\r' is added'; 'If successful the function returns the
    number of bytes written'; a BIN file gets the text as it is. FileOpen of a file named in MOCK_OPEN_FAIL fails (5004); MOCK_WRITE_FAIL
    'file:N:0' fails without a code. HistoryDealGet*: only the deals of the list HistorySelect made (HistoryDealSelect 'clears ... the list
    of deals available for reference'); SymbolInfoInteger with a result variable fails with 4302 (ERR_MARKET_NOT_SELECTED) for a symbol of
    MOCK_SYM_NOT_SELECTED; the account has a server, a company, a holder's name and a login (planted, never to be written)"""
    deals, _ = imitation_account()
    dcols = ["ticket", "order", "position", "time", "time_msc", "symbol", "type", "entry", "reason", "magic", "volume", "price", "sl", "tp",
             "commission", "swap", "fee", "profit", "comment", "external_id"]
    write_imitation(tmp / "probe_deals.csv", deals, dcols)
    (tmp / "probe.cpp").write_text(PROBE)
    subprocess.run(["g++", "-std=c++17", "-O1", "-I", str(HERE), str(tmp / "probe.cpp"), "-o", str(tmp / "probe")], check=True)
    files = tmp / "F_probe"
    files.mkdir()
    out = subprocess.run([str(tmp / "probe")], env=dict(os.environ, MOCK_FILES=str(files), MOCK_DEALS_FILE=str(tmp / "probe_deals.csv"),
                                                        MOCK_OPEN_FAIL="no.txt", MOCK_WRITE_FAIL="w.txt:1:0", MOCK_SYM_NOT_SELECTED="XAUUSD.r"),
                         check=True, capture_output=True, text=True).stdout
    kv = dict(ln.split("=", 1) for ln in out.splitlines() if "=" in ln)
    p = files / "p"
    assert kv["txt"] == "8" and (p / "t.txt").read_bytes() == b"ab\r\ncd\r\n", (kv["txt"], (p / "t.txt").read_bytes())
    assert kv["csv"] == "3" and (p / "c.csv").read_bytes() == b"x\r\n", kv["csv"]
    assert kv["bin"] == "3" and (p / "b.bin").read_bytes() == b"ab\n", kv["bin"]
    assert kv["open"] == "-1" and kv["open_err"] == "5004" and not (p / "no.txt").exists(), kv
    assert kv["fail"] == "0" and kv["fail_err"] == "0" and (p / "w.txt").read_bytes() == b"", kv
    assert kv["out_list"] == "0" and kv["out_list_px"] == "0" and kv["out_list_sym"] == "[]" and kv["in_list"] == str(NOW - 9 * 86400 + 3600), kv
    assert kv["sel"] == "0" and kv["sel_err"] == "4302", kv
    assert [kv["server"], kv["company"], kv["name"], kv["login"]] == ACCOUNT_PLANTED and kv["currency"] == "EUR", kv
    print("imitation: FileWriteString adds the CR before a bare LF of a TXT or CSV file and returns the bytes written (not for BIN); FileOpen "
          "and FileWriteString fail on demand; HistoryDealGet* only for the listed deals; 4302 for a symbol not in Market Watch; the account's "
          "server, company, name and login planted")


def mutant_lf(tmp):
    """review8 IMIT-CRLF: the imitation catches what the first 1.11 did. A copy of ReleveFP.mq5 whose deals.csv and positions.csv rows end in
    a bare LF and whose WriteRow accepts a write only when FileWriteString returns exactly StringLen: under the documented TXT behaviour
    (a CR added, the bytes written returned) every write of those files 'fails' -> positions=-1, deals=-1, erreur_deals=-1, header only"""
    src = (HERE.parent / "mql5" / "ReleveFP.mq5").read_text(encoding="ascii")
    mut = src.replace('\\r\\n";', '\\n";').replace('\\r\\n"))', '\\n"))')
    assert src.count('\\r\\n";') == 2 and src.count('\\r\\n"))') == 2, (src.count('\\r\\n";'), src.count('\\r\\n"))'))
    assert mut.count("return n >= (uint)StringLen(s);") == 1, "WriteRow"
    mut = mut.replace("return n >= (uint)StringLen(s);", "return n == (uint)StringLen(s);")
    m = tmp / "mutant"
    m.mkdir()
    (m / "ReleveFP_mutant.mq5").write_text(mut, encoding="ascii")
    subprocess.run([sys.executable, "-I", str(HERE / "to_cpp.py"), str(m / "ReleveFP_mutant.mq5"), str(m / "releve.cpp")], check=True,
                   capture_output=True)
    (m / "run.cpp").write_text('#include "mock_mt5.h"\n#include "releve.cpp"\nint main() { OnStart(); return 0; }\n')
    subprocess.run(["g++", "-std=c++17", "-O1", "-I", str(HERE), "-I", str(m), str(m / "run.cpp"), "-o", str(m / "run")], check=True)
    files = m / "Files"
    files.mkdir()
    subprocess.run([str(m / "run")], env=dict(os.environ, MOCK_FILES=str(files), MOCK_DEALS_FILE=str(tmp / "mk_deals.csv"),
                                              MOCK_POSITIONS_FILE=str(tmp / "mk_positions.csv")), check=True, capture_output=True)
    d = files / "claude" / "releve"
    fini = dict(ln.split("=", 1) for ln in (d / "fini.txt").read_text().splitlines() if "=" in ln)
    assert fini.get("deals") == "-1" and fini.get("positions") == "-1" and fini.get("erreur_deals") == "-1", fini
    assert (d / "deals.csv").read_text().splitlines() == [DEALS_HEADER], (d / "deals.csv").read_text()[:200]
    print("mutant (rows ending in a bare LF, WriteRow with ==): the imitation shows the failure the documentation predicts (deals=-1, "
          "positions=-1, erreur_deals=-1, header only)")


def sonde():
    """The demo probe against fake hands that publish a position's deals late (as ClaudeMains did before it exported
    them after each transaction) and charge part of the cost as a fee."""
    import time
    import releve
    import test_pont as TP
    from pont import Hands

    class LateDeals(TP.FakeHands):
        rows, pending = "", []

        def export(self):
            super().export()
            now = time.time()
            for at, row in list(self.pending):
                if at <= now:
                    self.rows += row
                    self.pending.remove((at, row))
            self.put("deals.csv", "deal,position,time,symbol,type,entry,volume,price,profit,swap,commission,fee,magic,reason,comment\n" + self.rows)

        def handle(self, f):
            kv = dict(ln.split("=", 1) for ln in f.read_bytes().decode("latin-1").splitlines() if "=" in ln)
            before = set(self.pos)
            super().handle(f)
            now = int(time.time()) + 7200
            if kv.get("action") == "open":
                for t in set(self.pos) - before:
                    p = self.pos[t]
                    self.pending.append((time.time(), f"{t + 5000},{t},{now},XAUUSD.r,buy,0,{p['volume']:.4f},{p['price']:.2f},0.00,0.00,-0.02,-0.01,20261110,3,CM sonde\n"))
            if kv.get("action") == "close" and int(kv["ticket"]) in before:
                t = int(kv["ticket"])
                self.pending.append((time.time() + 1.2, f"{t + 6000},{t},{now},XAUUSD.r,sell,1,0.0100,{self.bid:.2f},-0.12,0.00,-0.02,-0.01,20261110,3,\n"))

        def run(self):
            while not self.stop:
                for f in sorted((self.d / "cmd").glob("*.txt")):
                    self.handle(f)
                self.export()
                time.sleep(0.05)

    d = tempfile.mkdtemp()
    fake = LateDeals(d)
    fake.start()
    releve.OUT = tempfile.mkdtemp()
    out = releve.sonde(("XAUUSD", "ETHUSD"), h=Hands(d), pause=0.2)
    fake.stop = True
    m = out["marches"]["XAUUSD"]
    assert m["transactions"] == 2 and abs(m["commission_aller_retour"] - 0.06) < 1e-9, m       # both deals, commission + fee
    assert abs(m["commission_par_lot"] - 6.0) < 1e-9 and abs(m["commission_en_prix"] - 6.0 / 0.89 * 0.01) < 1e-6, m
    assert "erreur" in out["marches"]["ETHUSD"]
    assert abs(releve.commissions_mesurees()["xauusd"] - m["commission_en_prix"]) < 1e-12
    print("sonde: both deals seen although the exit deal was published late; commission + fee =", m["commission_par_lot"], "per lot")


if __name__ == "__main__":
    main()
