"""Run the REAL code of mql5/SondeFP.mq5 (translated to C++ by to_cpp.py, linked with the working imitation of
MetaTrader in mock_mains.h + mock_sonde.h) and check what it sends to the broker and what it writes: the trade requests,
the positions and deals left at the fake broker, the alerts, and MQL5/Files/claude/releve/sonde.csv, which is then read
with the real Python reader (releve.lire_sonde / releve.commissions_mesurees).

    python3 live_ai/check/test_sonde.py                    every test (a few seconds: the script's Sleep is a virtual clock)
    python3 live_ai/check/test_sonde.py -k stop,H2         only the tests whose id or title contains "stop" or "H2"
    python3 live_ai/check/test_sonde.py --mq5 /path/Copy.mq5     test another copy of the script (e.g. a corrected one)
    python3 live_ai/check/test_sonde.py --keep             keep the temporary directories (log in Files/_mock/log.txt)

One line per test: PASS / FAIL. Each test states what the script SHOULD do. A title ending with {F3} says which finding
of the first run (2026-11-11, script 1.00) the test guards: findings F1 to F8 and F10 are corrected in 1.10, and each of
these tests fails on the 1.00 script. (A test can still be declared an EXPECTED FAILURE, marked [F3], for a defect that
is known and not corrected yet; there is none today.) Exit code 0 only if every test that should pass passes.

Inputs: as in test_mains.py, the `input` values are wrapped, in the TRANSLATED file only, in mock_input<T>() so that a
test can run the same binary with another value (env MOCK_INPUT_InpSymbols ...). The .mq5 is never modified.

WHAT THIS CANNOT PROVE about the real terminal (the imitation is hand-written from the MQL5 documentation and from the
Standard Library's Trade.mqh; it is not MetaTrader):
  * that MetaEditor compiles the file (only g++ on the translation does);
  * FP Markets' real symbols (names, minimum lots, stops level, tick value, order flags) and where the broker really
    books its cost (DEAL_COMMISSION on each deal, on the entry deal only, DEAL_FEE, or a separate daily charge);
  * that the terminal rounds a deal's commission to cents (here it does: see the note printed by test N1);
  * the timing of the real terminal: when the new position is listed, when the deals reach the history (tests H*
    take delays, the script never really waits here), how OrderSend answers (tests P1, O1 are "what if" cases
    allowed by the documentation: 'the trade server can fill in the deal or order field values ... if it is aware of
    these data when forming a response');
  * whether SymbolInfoTick fails for a moment on a market the script has just added to Market Watch (test Q2
    assumes it does; from memory, the documentation does not say);
  * StringFind with an empty substring (test E1 assumes it returns 0, as C++ does; the documentation does not say);
  * what a script may still do once it is being removed from the chart (test X1 follows Trade.mqh: CTrade sends nothing
    when IsStopped() is true).
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIVE = HERE.parent
sys.path.insert(0, str(LIVE))
import releve  # noqa: E402

MAGIC = 20261112
HEADER = ("base,name,status,volume,bid_before,ask_before,buy_price,bid_at_close,ask_at_close,sell_price,deals,commission,fee,"
          "profit,swap,tick_size,tick_value,contract_size,position")
NCOL = len(HEADER.split(","))
INPUT_RE = re.compile(r"^const\s+(string|double|int|long|bool)\s+(Inp\w+)\s*=\s*(.+?);(\s*//.*)?$", re.M)
FIRST = 50001001                      # ticket of the first position the fake broker opens
USD_EUR, JPY_EUR = 0.8621, 0.005561   # the fake broker's exchange rates (account in EUR)
# The fake broker's markets (MK_DEFAULTS in mock_mains.h), written again here so that what the script must send and
# write is recomputed independently. eur = value in EUR of a move of 1.0 in price for one lot; com / fee = EUR per lot
# charged on EVERY deal (commission) or as a fee.
B = {
    "XAUUSD.r": dict(dg=2, ts=0.01, tv=0.8621, tvl=0.8625, contract=100.0, vmin=0.01, stops=0.0, com=2.59, fee=0.0, bid=4080.10, ask=4080.23, eur=100 * USD_EUR),
    "EURUSD.r": dict(dg=5, ts=0.00001, tv=0.8621, tvl=0.8625, contract=100000.0, vmin=0.01, stops=0.0, com=2.59, fee=0.0, bid=1.16000, ask=1.16002, eur=100000 * USD_EUR),
    "USDJPY.r": dict(dg=3, ts=0.001, tv=0.5561, tvl=0.5565, contract=100000.0, vmin=0.01, stops=0.0, com=2.59, fee=0.0, bid=155.000, ask=155.004, eur=100000 * JPY_EUR),
    "NAS100": dict(dg=2, ts=0.01, tv=0.008621, tvl=0.008625, contract=1.0, vmin=0.10, stops=1.0, com=0.0, fee=0.0, bid=25000.00, ask=25001.50, eur=USD_EUR),
    "BTCUSD": dict(dg=2, ts=0.01, tv=0.008621, tvl=0.008625, contract=1.0, vmin=0.01, stops=0.0, com=0.0, fee=17.24, bid=100000.00, ask=100012.00, eur=USD_EUR),
    "ETHUSD": dict(dg=2, ts=0.01, tv=0.008621, tvl=0.008625, contract=1.0, vmin=0.10, stops=0.0, com=0.0, fee=0.60, bid=3500.00, ask=3501.20, eur=USD_EUR),
    "JPN225": dict(dg=2, ts=0.01, tv=0.005561, tvl=0.005565, contract=1.0, vmin=0.10, stops=0.0, com=0.0, fee=0.0, bid=50000.00, ask=50008.00, eur=100 * JPY_EUR),
}
# the defects of script 1.00 found on 2026-11-11 (all corrected in 1.10)
FINDINGS = {
    "F1": "status 'ok' is written although the two deals of the round trip were not read back (history late, or no order "
          "ticket in the answer): the commission is then 0 or half, and lire_sonde takes it as measured",
    "F2": "a position without a stop is not detected (stop removed by CTrade when the market does not accept one, or not "
          "kept by the broker); left open, the alert still says 'elle a un stop'",
    "F3": "a position already closed by its stop before the resale is reported as 'POSITION RESTEE OUVERTE', with the "
          "alert to close it by hand",
    "F4": "no refusal on an account that is not in hedging mode (there, the resale by market name closes the whole "
          "position of the market, whatever opened it)",
    "F5": "sonde.csv that cannot be written is not reported: the final alert still says the probe is done (and an older "
          "sonde.csv stays in place)",
    "F6": "an empty name in the list of markets (comma in excess) is resolved to the first market of the broker, IF "
          "StringFind returns 0 for an empty substring (not documented)",
    "F7": "a market that has no quote yet when the script looks (just added to Market Watch by the script itself) is "
          "skipped with 'pas de prix' instead of waiting a moment for its first quote (IF the first quote comes late: "
          "from memory, not in the documentation)",
    "F8": "with the 'Algo Trading' button on but trading not allowed for this script, the alert tells the user to press "
          "the button (which is already on)",
    "F10": "the stop is rounded to the number of digits, not to the tick size: on a market whose tick size is larger than "
           "its point the server may refuse the buy (IF servers refuse such stops: from memory)",
}


# ---------------------------------------------------------------------------------------------- build and run
def build(mq5, work):
    cpp = work / "sonde.cpp"
    subprocess.run([sys.executable, "-I", str(HERE / "to_cpp.py"), str(mq5), str(cpp)], check=True, capture_output=True)
    src = cpp.read_text()
    src, n = INPUT_RE.subn(lambda m: f'const {m[1]} {m[2]} = mock_input<{m[1]}>("{m[2]}", {m[3]});{m[4] or ""}', src)
    want = sum(1 for ln in Path(mq5).read_text(encoding="ascii").split("\n") if ln.startswith("input "))
    assert n == want, f"{n} inputs rewritten, {want} in the .mq5"
    cpp.write_text(src)
    (work / "run.cpp").write_text('#include "mock_sonde.h"\n#include "sonde.cpp"\nint main() { return sd_run(OnStart); }\n')
    extra = os.environ.get("SONDE_CXXFLAGS", "").split()                        # e.g. -fsanitize=address,undefined
    subprocess.run(["g++", "-std=c++17", "-O1", "-g", "-D_GLIBCXX_ASSERTIONS", *extra, "-I", str(HERE), "-I", str(work),
                    str(work / "run.cpp"), "-o", str(work / "sonde")], check=True)
    return work / "sonde"


REQ_RE = re.compile(r"^(open|close|sltp) (\S+) position=(\d+) .*?sl=(\S+) .*?-> retcode=(\d+)")
KEPT = []


class Run:
    """One run of the script in a fresh fake terminal. ctl = lines of _mock/control.txt (see mock_mains.h, mock_sonde.h);
    at = [(virtual ms, "key=value"), ...] changes of the fake world while the script sleeps."""

    def __init__(self, binary, symbols=None, ctl=None, at=(), balance=None, missing="", inputs=None, prepare=None):
        self.root = Path(tempfile.mkdtemp(prefix="sonde_"))
        KEPT.append(self.root)
        self.files = self.root / "Files"
        mock = self.files / "_mock"
        mock.mkdir(parents=True)
        lines = [f"{k}={v}" for k, v in (ctl or {}).items()] + [f"at.{ms}={kv}" for ms, kv in at]
        (mock / "control.txt").write_text("\n".join(lines) + "\n")
        if balance is not None:
            (mock / "state.txt").write_text(f"balance={balance:.2f}\n")
        if prepare:
            prepare(self.files)
        env = dict(os.environ, MOCK_FILES=str(self.files), MOCK_MISSING=missing)
        inputs = dict(inputs or {})
        if symbols is not None:
            inputs["InpSymbols"] = symbols
        env.update({"MOCK_INPUT_" + k: str(v) for k, v in inputs.items()})
        p = subprocess.run([str(binary)], env=env, capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, f"the script crashed: exit code {p.returncode} {p.stderr[-300:]!r}"
        self.log = [tuple(ln.split("\t", 1)) for ln in (mock / "log.txt").read_text().splitlines() if "\t" in ln]
        self.folder = self.files / "claude" / "releve"
        p = self.folder / "sonde.csv"
        self.text = p.read_text() if p.is_file() else None
        self.rows, self.trailer = {}, None
        if self.text is not None:
            ln = self.text.split("\n")
            assert ln[0] == HEADER, f"header {ln[0]!r}"
            assert self.text.endswith("\n") and "\r" not in self.text
            for x in ln[1:-1]:
                if x.startswith("#"):
                    self.trailer = x
                else:
                    f = x.split(",")
                    key = f[0]
                    while key in self.rows:                                    # the same base twice: second row under "base#"
                        key += "#"
                    self.rows[key] = f
        # the broker's own books
        self.balance, self.positions, self.deals = 1000.0, [], []
        for x in (mock / "state.txt").read_text().splitlines():
            f = x.split("|")
            if x.startswith("balance="):
                self.balance = float(x[8:])
            elif f[0] == "P":
                self.positions.append(dict(ticket=int(f[1]), symbol=f[2], volume=float(f[4]), price=float(f[5]), sl=float(f[6]),
                                           magic=int(f[9]), ident=int(f[12])))
            elif f[0] == "D":
                self.deals.append(dict(deal=int(f[1]), position=int(f[3]), symbol=f[5], type=int(f[6]), entry=int(f[7]),
                                       volume=float(f[8]), price=float(f[9]), profit=float(f[10]), swap=float(f[11]),
                                       commission=float(f[12]), fee=float(f[13]), magic=int(f[14]), reason=int(f[15])))
        # every trade request the script made, in order: (kind, symbol, position, sl, retcode)
        self.req = []
        for kind, text in self.log:
            m = REQ_RE.match(text) if kind in ("TRADE", "SONDE") else None
            if m:
                self.req.append((m[1], m[2], int(m[3]), float(m[4]), int(m[5])))

    def of(self, kind):
        return [t for k, t in self.log if k == kind]

    def kinds(self, kind, symbol=None):
        return [r for r in self.req if r[0] == kind and (symbol is None or r[1] == symbol)]

    def alerts(self):
        return " | ".join(self.of("ALERT"))

    def sonde(self):
        return releve.lire_sonde(self.folder)

    def status(self, base):
        return self.rows[base][2]

    def row(self, base):
        """the 19 fields of a complete row, by name"""
        f = self.rows[base]
        assert len(f) == NCOL, f"{base}: {len(f)} fields instead of {NCOL}: {f}"
        d = dict(zip(HEADER.split(","), f))
        for k in d:
            if k not in ("base", "name", "status"):
                d[k] = float(d[k])
        return d

    def nothing_sent(self):
        assert not self.req, f"trade requests were sent: {self.req}"
        assert not self.positions and not self.deals, "the broker has positions or deals"
        assert abs(self.balance - 1000.0) < 1e-9

    def no_naked_position(self):
        """at no moment a request that opens a position without a stop, and no position left without one"""
        for kind, sym, _, sl, rc in self.req:
            assert not (kind == "open" and sl <= 0), f"{sym}: opening request sent without a stop"
        for p in self.positions:
            assert p["sl"] > 0, f"position {p['ticket']} on {p['symbol']} is left open WITHOUT a stop"


def near(a, b, tol=1e-9):
    return abs(a - b) <= tol


def expected_sl(name, balance=1000.0, risk_pct=0.4):
    """(stop, distance) the script must compute for the minimum lot, from the balance at that moment"""
    s = B[name]
    per_price = s["vmin"] * s["tvl"] / s["ts"]
    dist = min(risk_pct / 100 * balance / per_price, 0.015 * s["bid"])
    return s["bid"] - dist, dist


def honest(r, base, name):
    """What the csv says about a market must not mislead the reader: the row is read as a measure by lire_sonde only if
    the two deals of the round trip are in it, with the commission and fee the broker really booked."""
    got = r.sonde().get(base)
    if got is None:
        return False
    s = B[name]
    booked = -sum(d["commission"] + d["fee"] for d in r.deals if d["symbol"] == name)
    assert got["transactions"] == 2, f"lire_sonde takes as measured a row with {got['transactions']} deal(s): {r.rows[base]}"
    assert near(got["commission_aller_retour"], booked, 1e-6), (got, booked)
    assert near(got["commission_en_prix"], booked / s["vmin"] / s["eur"], 1e-9), got
    return True


# ---------------------------------------------------------------------------------------------- the tests
def t_normal(b):
    """default list of markets: 5 round trips; ETHUSD absent at this broker; JP225 in close-only mode"""
    r = Run(b, missing="ETHUSD", ctl={"sym.JPN225.trade_mode": 3})
    names = {"XAUUSD": "XAUUSD.r", "EURUSD": "EURUSD.r", "USDJPY": "USDJPY.r", "US100": "NAS100", "BTCUSD": "BTCUSD"}
    assert list(r.rows) == ["XAUUSD", "EURUSD", "USDJPY", "US100", "BTCUSD", "ETHUSD", "JP225"], list(r.rows)
    assert r.rows["ETHUSD"] == ["ETHUSD", "", "INTROUVABLE"], r.rows["ETHUSD"]
    assert r.rows["JP225"] == ["JP225", "JPN225", "marche ferme ou non negociable"], r.rows["JP225"]
    # requests: one buy with a stop then one sale per market, nothing on the two others
    assert [(k, s) for k, s, *_ in r.req] == [(k, n) for n in names.values() for k in ("open", "close")], r.req
    assert all(rc == 10009 for *_, rc in r.req)
    opens = [t for t in r.of("TRADE") if t.startswith("open ")]
    assert all(f"magic={MAGIC} comment=sonde" in t and "type=0" in t for t in opens), opens
    worst, balance = 0.0, 1000.0
    for i, (base, name) in enumerate(names.items()):
        s, d = B[name], r.row(base)
        sl, dist = expected_sl(name, balance)                                    # the balance shrinks with each round trip
        sent = r.kinds("open", name)[0][3]
        assert near(sent, sl, s["ts"] * 0.51), f"{name}: stop {sent}, expected {sl}"
        assert dist >= max(8 * (s["ask"] - s["bid"]), s["stops"] + 2 * (s["ask"] - s["bid"])) - 1e-9
        risk = (s["ask"] - sent) * s["vmin"] * s["tvl"] / s["ts"]                # loss in EUR if the stop is hit
        worst = max(worst, risk / balance * 100)
        pos = FIRST + 2 * i                                                      # each round trip uses two order tickets
        assert d["name"] == name and d["status"] == "ok" and d["position"] == pos, d
        assert near(d["volume"], s["vmin"]) and d["deals"] == 2
        assert near(d["bid_before"], s["bid"]) and near(d["ask_before"], s["ask"])
        assert near(d["buy_price"], s["ask"]) and near(d["sell_price"], s["bid"])
        assert near(d["bid_at_close"], s["bid"]) and near(d["ask_at_close"], s["ask"])
        assert near(d["tick_size"], s["ts"]) and near(d["tick_value"], s["tv"]) and near(d["contract_size"], s["contract"])
        # commission, fee, profit: against the settings of the fake broker ...
        com, fee = -2 * round(s["com"] * s["vmin"], 2), -2 * round(s["fee"] * s["vmin"], 2)
        profit = round((s["bid"] - s["ask"]) / s["ts"] * s["tvl"] * s["vmin"], 2)
        assert near(d["commission"], com, 1e-6) and near(d["fee"], fee, 1e-6) and near(d["profit"], profit, 1e-6), (d, com, fee, profit)
        assert d["swap"] == 0.0
        # ... and against the broker's own books
        mine = [x for x in r.deals if x["position"] == pos]
        assert [x["entry"] for x in mine] == [0, 1] and all(x["magic"] == MAGIC and x["symbol"] == name for x in mine)
        assert near(sum(x["commission"] for x in mine), d["commission"], 1e-6) and near(sum(x["fee"] for x in mine), d["fee"], 1e-6)
        assert near(sum(x["profit"] for x in mine), d["profit"], 1e-6)
        balance = round(balance + sum(x["profit"] + x["commission"] + x["fee"] for x in mine), 2)
    assert worst <= 0.4 * 1.125 + 1e-9, f"risk at the stop {worst:.3f} % of the balance"
    assert not r.positions and len(r.deals) == 10
    assert near(r.balance, balance, 1e-6) and balance < 1000.0
    # last line and messages
    m = re.fullmatch(r"#currency=EUR,server=FPMarketsSC-Demo,server_time=(\d+)", r.trailer or "")
    assert m and abs(int(m[1]) - (time.time() + 7200)) < 30, r.trailer
    assert r.alerts() == "Sonde terminee : 5 marches sur 7. Vous pouvez le dire a Claude.", r.alerts()
    assert any("5 marches sur 7" in c for c in r.of("COMMENT"))
    # the Python reader, and the conversion of the commission into price units
    got = r.sonde()
    assert list(got) == list(names), list(got)
    for base, name in names.items():
        s, g = B[name], got[base]
        rt = 2 * (round(s["com"] * s["vmin"], 2) + round(s["fee"] * s["vmin"], 2))          # EUR for the round trip
        assert g["nom"] == name and g["transactions"] == 2 and near(g["volume"], s["vmin"])
        assert near(g["commission_aller_retour"], rt, 1e-9) and near(g["commission_par_lot"], rt / s["vmin"], 1e-6), g
        assert near(g["commission_en_prix"], rt / s["vmin"] / s["eur"], 1e-12), (g, rt / s["vmin"] / s["eur"])
        assert near(g["commission_pb"], rt / s["vmin"] / s["eur"] / s["ask"] * 1e4, 6e-4)
        assert near(g["ecart_realise"], s["ask"] - s["bid"], 1e-8) and near(g["ecart_realise_pb"], (s["ask"] - s["bid"]) / s["ask"] * 1e4, 6e-4)
    lab = releve.commissions_mesurees(r.folder)
    assert set(lab) == {"xauusd", "eurusd", "usdjpy", "us100", "btcusd"}, lab
    assert near(lab["xauusd"], 0.06 / 0.01 / 86.21, 1e-12) and lab["us100"] == 0.0
    true_rt = 2 * B["XAUUSD.r"]["com"]
    return (f"commission conversion checked. NOTE (F9): at 0.01 lot each deal's commission is rounded to 0.01 EUR; the fake "
            f"broker charges {true_rt:.2f} EUR per lot round trip, the probe reads {got['XAUUSD']['commission_par_lot']:.2f} "
            f"(resolution +-1.00 EUR per lot at 0.01 lot); risk at the stop up to {worst:.3f} % of the balance (input: 0.4)")


def t_move(b):
    """the price moves while the position is open: sale price, quote at the close and result follow"""
    r = Run(b, "XAUUSD", at=[(500, "price.XAUUSD.r=4081.10,4081.23")])
    d = r.row("XAUUSD")
    assert d["status"] == "ok" and near(d["buy_price"], 4080.23) and near(d["sell_price"], 4081.10)
    assert near(d["bid_before"], 4080.10) and near(d["bid_at_close"], 4081.10) and near(d["ask_at_close"], 4081.23)
    assert near(d["profit"], round(0.87 / 0.01 * 0.8621 * 0.01, 2), 1e-6) and near(d["commission"], -0.06, 1e-6), d
    assert near(r.sonde()["XAUUSD"]["ecart_realise"], -0.87, 1e-8)
    assert not r.positions


def t_big_balance(b):
    """a demo account of 100 000: the stop is not further than 1.5 % of the price"""
    r = Run(b, "XAUUSD,BTCUSD", balance=100000.0)
    for base, name in (("XAUUSD", "XAUUSD.r"), ("BTCUSD", "BTCUSD")):
        s = B[name]
        sent = r.kinds("open", name)[0][3]
        assert near(sent, s["bid"] * (1 - 0.015), s["ts"] * 0.51), f"{name}: stop {sent} for a price of {s['bid']}"
        assert r.status(base) == "ok" and honest(r, base, name)
    assert not r.positions


def t_lag(b):
    """the terminal lists a new position only some time after the answer to the buy (while the script waits)"""
    r = Run(b, "XAUUSD,BTCUSD", ctl={"lag": 1})
    assert r.status("XAUUSD") == "ok" and r.status("BTCUSD") == "ok" and not r.positions
    assert [k for k, *_ in r.req] == ["open", "close"] * 2 and honest(r, "XAUUSD", "XAUUSD.r") and honest(r, "BTCUSD", "BTCUSD")


def t_no_price(b):
    """a market without any price: status line, no order"""
    r = Run(b, "XAUUSD,BTCUSD", ctl={"price.XAUUSD.r": "0,0"})
    assert r.rows["XAUUSD"] == ["XAUUSD", "XAUUSD.r", "pas de prix"], r.rows["XAUUSD"]
    assert not r.kinds("open", "XAUUSD.r") and r.status("BTCUSD") == "ok"


def t_first_tick(b):
    """a market whose first quote arrives 0.8 s after the script added it to Market Watch: it is probed all the same"""
    r = Run(b, "XAUUSD,BTCUSD", ctl={"x.BTCUSD.first_tick_ms": 3000})        # the script reaches BTCUSD at 2200 ms
    assert r.status("XAUUSD") == "ok"
    assert r.rows["BTCUSD"][2] == "ok", r.rows["BTCUSD"]
    assert honest(r, "BTCUSD", "BTCUSD") and not r.positions


def t_names(b):
    """names with spaces; a market whose trading is disabled is INTROUVABLE and gets no order"""
    r = Run(b, " XAUUSD , US500,GER40 ", ctl={"sym.US500.trade_mode": 0})
    assert list(r.rows) == ["XAUUSD", "US500", "GER40"], list(r.rows)
    assert r.rows["US500"] == ["US500", "", "INTROUVABLE"] and r.row("GER40")["name"] == "DE40" and r.status("GER40") == "ok"
    assert [s for _, s, *_ in r.req] == ["XAUUSD.r", "XAUUSD.r", "DE40", "DE40"]
    assert "2 marches sur 3" in r.alerts()


def t_real(b):
    """REAL account (and contest account): nothing is sent, nothing is written, one alert"""
    for mode in (2, 1):
        r = Run(b, ctl={"account_trade_mode": mode})
        r.nothing_sent()
        assert r.text is None and not (r.files / "claude").exists(), "files were written"
        assert len(r.of("ALERT")) == 1 and "Rien n'a ete fait" in r.alerts(), r.alerts()
        assert not r.of("SLEEP") and not r.of("COMMENT")


def t_algo_off(b):
    """'Algo Trading' button off: nothing is sent, no file, the alert names the button"""
    r = Run(b, ctl={"terminal_trade_allowed": 0})
    r.nothing_sent()
    assert r.text is None and len(r.of("ALERT")) == 1 and "Algo Trading" in r.alerts(), r.alerts()


def t_algo_script(b):
    """button on, but trading not allowed for this script (box of its own window): nothing sent, and the alert says which box"""
    r = Run(b, ctl={"mql_trade_allowed": 0})
    r.nothing_sent()
    assert r.text is None and len(r.of("ALERT")) == 1
    assert "Activez le bouton Algo Trading" not in r.alerts(), f"the alert sends the user to a button that is already on: {r.alerts()}"


def t_lot_too_big(b):
    """minimum lot too large for the stop budget (1 lot of gold; then a 20 EUR account): status line, no order"""
    r = Run(b, "XAUUSD,BTCUSD", ctl={"sym.XAUUSD.r.vol_min": 1, "sym.XAUUSD.r.vol_step": 1})
    assert r.rows["XAUUSD"] == ["XAUUSD", "XAUUSD.r", "lot minimum trop gros pour un stop a 0.40 % du solde"], r.rows["XAUUSD"]
    assert not r.kinds("open", "XAUUSD.r") and r.status("BTCUSD") == "ok" and "1 marches sur 2" in r.alerts()
    assert "XAUUSD" not in r.sonde()
    r = Run(b, "XAUUSD,BTCUSD", balance=20.0)
    assert all(len(f) == 3 and f[2].startswith("lot minimum trop gros") for f in r.rows.values()), r.rows
    assert not r.req and not r.deals and near(r.balance, 20.0) and r.sonde() == {}


def t_margin(b):
    """margin too small for the minimum lot: status line, no order"""
    r = Run(b, "BTCUSD,XAUUSD", ctl={"sym.BTCUSD.leverage": 0.5})          # 0.01 BTC then needs 1724 EUR
    assert r.rows["BTCUSD"] == ["BTCUSD", "BTCUSD", "marge insuffisante"], r.rows["BTCUSD"]
    assert not r.kinds("open", "BTCUSD") and r.status("XAUUSD") == "ok"


def t_refused(b):
    """the buy refused by the server (10006), by a closed session (10018) on one market, by the account (10027)"""
    r = Run(b, "XAUUSD,BTCUSD", ctl={"retcode_open": 10006})
    assert r.rows["XAUUSD"] == ["XAUUSD", "XAUUSD.r", "achat refuse : 10006 rejected"], r.rows["XAUUSD"]
    assert r.rows["BTCUSD"][2] == "achat refuse : 10006 rejected"
    assert len(r.req) == 2 and not r.kinds("close") and not r.positions and not r.deals
    assert "0 marches sur 2" in r.alerts() and r.sonde() == {}
    r = Run(b, "XAUUSD,US100,BTCUSD", ctl={"x.NAS100.retcode_open": 10018})
    assert r.rows["US100"] == ["US100", "NAS100", "achat refuse : 10018 market closed"], r.rows["US100"]
    assert r.status("XAUUSD") == "ok" and r.status("BTCUSD") == "ok" and not r.positions and list(r.sonde()) == ["XAUUSD", "BTCUSD"]
    r = Run(b, "XAUUSD", ctl={"account_trade_expert": 0})
    assert r.rows["XAUUSD"][2] == "achat refuse : 10027 auto trading disabled by client", r.rows["XAUUSD"]
    assert not r.positions and not r.deals


def t_close_fails(b):
    """the sale refused five times: the position stays (with its stop), status line and alert, the next market is probed"""
    r = Run(b, "XAUUSD,BTCUSD", ctl={"x.XAUUSD.r.retcode_close": 10021})
    assert [(k, s, rc) for k, s, _, _, rc in r.req] == [("open", "XAUUSD.r", 10009)] + [("close", "XAUUSD.r", 10021)] * 5 + \
        [("open", "BTCUSD", 10009), ("close", "BTCUSD", 10009)], r.req
    assert len(r.positions) == 1
    p = r.positions[0]
    assert p["symbol"] == "XAUUSD.r" and p["ticket"] == FIRST and p["magic"] == MAGIC and near(p["sl"], expected_sl("XAUUSD.r")[0], 0.0051), p
    d = r.row("XAUUSD")
    assert d["status"] == "POSITION RESTEE OUVERTE (fermez-la a la main)" and d["position"] == FIRST, d
    assert d["deals"] == 1 and near(d["commission"], -0.03, 1e-6) and d["sell_price"] == 0.0 and near(d["buy_price"], 4080.23)
    assert r.status("BTCUSD") == "ok"
    assert len(r.of("ALERT")) == 1 and "n'a pas pu etre refermee" in r.alerts() and "elle a un stop" in r.alerts(), r.alerts()
    assert "Vous pouvez le dire" not in r.alerts()
    assert list(r.sonde()) == ["BTCUSD"]
    r.no_naked_position()


def t_close_retry(b):
    """the sale refused twice, accepted the third time: a normal row"""
    r = Run(b, "XAUUSD", ctl={"close_fails": 2})
    assert [rc for k, *_, rc in r.req if k == "close"] == [10021, 10021, 10009], r.req
    assert r.status("XAUUSD") == "ok" and r.row("XAUUSD")["deals"] == 2 and not r.positions
    assert honest(r, "XAUUSD", "XAUUSD.r") and "1 marches sur 1" in r.alerts()


def t_history_late(b):
    """the exit deal reaches the history 3 s after the sale: the script waits for it"""
    r = Run(b, "XAUUSD,BTCUSD", ctl={"history_delay_out_ms": 3000})
    polls = [t for t in r.of("HISTORY") if t.startswith(f"position {FIRST}:")]
    assert len(polls) >= 2 and "1 of 2" in polls[0] and "2 of 2" in polls[-1], polls
    assert r.status("XAUUSD") == "ok" and r.row("XAUUSD")["deals"] == 2 and near(r.row("XAUUSD")["commission"], -0.06, 1e-6)
    assert honest(r, "XAUUSD", "XAUUSD.r") and honest(r, "BTCUSD", "BTCUSD")


def t_history_never_out(b):
    """the exit deal is still not in the history when the script stops waiting: the row must not pass for a measure"""
    r = Run(b, "XAUUSD", ctl={"history_delay_out_ms": 600000})
    assert not r.positions and len(r.deals) == 2
    assert len([t for t in r.of("HISTORY")]) == 10
    honest(r, "XAUUSD", "XAUUSD.r")
    assert r.status("XAUUSD") != "ok", f"status ok with {r.rows['XAUUSD'][10]} deal(s) and commission {r.rows['XAUUSD'][11]}"


def t_history_never(b):
    """no deal at all in the history in time: the row must not pass for a measure (a commission of 0)"""
    r = Run(b, "XAUUSD", ctl={"history_delay_ms": 600000})
    assert not r.positions and len(r.deals) == 2
    honest(r, "XAUUSD", "XAUUSD.r")
    assert r.status("XAUUSD") != "ok", f"status ok with {r.rows['XAUUSD'][10]} deal(s) and commission {r.rows['XAUUSD'][11]}"


def t_no_ticket(b):
    """the server's answer to the buy carries no order ticket (allowed by the documentation of OrderSend)"""
    r = Run(b, "XAUUSD", ctl={"no_order_ticket": 1})
    assert not r.positions and len(r.deals) == 2, "the position was not closed"
    honest(r, "XAUUSD", "XAUUSD.r")
    assert r.status("XAUUSD") == "ok" and r.row("XAUUSD")["deals"] == 2 and r.row("XAUUSD")["position"] == FIRST, r.rows["XAUUSD"]


def t_placed(b):
    """the buy is answered 'placed' (10008) without price: the buy price is read in the history"""
    r = Run(b, "XAUUSD", ctl={"placed": 1})
    d = r.row("XAUUSD")
    assert d["status"] == "ok" and near(d["buy_price"], 4080.23) and near(d["sell_price"], 4080.10) and d["deals"] == 2, d
    assert honest(r, "XAUUSD", "XAUUSD.r") and not r.positions


def t_reticket(b):
    """the server gives the position another ticket while it is open: it is still closed, and its deals are found"""
    r = Run(b, "XAUUSD", at=[(1000, f"do.1=reticket {FIRST}")])
    assert not r.positions and r.kinds("close")[0][2] == FIRST + 1, r.req
    d = r.row("XAUUSD")
    assert d["status"] == "ok" and d["deals"] == 2 and d["position"] == FIRST, d
    assert honest(r, "XAUUSD", "XAUUSD.r")


def t_stop_removed_by_ctrade(b):
    """a market that does not accept a stop in the order (CTrade then removes it silently): no position without a stop"""
    r = Run(b, "XAUUSD,BTCUSD", ctl={"sym.XAUUSD.r.order_mode": 127 - 16})
    r.no_naked_position()
    assert r.status("BTCUSD") == "ok"


def t_stop_removed_left_open(b):
    """same market, and the sale fails: a position must not be left open without a stop behind an alert saying it has one"""
    r = Run(b, "XAUUSD", ctl={"sym.XAUUSD.r.order_mode": 127 - 16, "x.XAUUSD.r.retcode_close": 10021})
    naked = [p for p in r.positions if p["sl"] <= 0]
    assert not (naked and "elle a un stop" in r.alerts()), f"position {naked[0]['ticket']} left open with sl=0; alert: {r.alerts()}"
    r.no_naked_position()


def t_stop_dropped_by_broker(b):
    """the broker opens the position without keeping the stop, and the sale fails: the stop is put back (or the alert says
    the position has NO stop)"""
    r = Run(b, "XAUUSD", ctl={"drop_sl": 1, "x.XAUUSD.r.retcode_close": 10021})
    assert len(r.positions) == 1 and r.status("XAUUSD").startswith("POSITION RESTEE OUVERTE")
    naked = r.positions[0]["sl"] <= 0
    assert not (naked and "elle a un stop" in r.alerts()), f"position left open with sl=0; alert: {r.alerts()}"
    assert not naked or "SANS STOP" in r.status("XAUUSD")
    # and when the stop cannot be put back either, the status and the alert say so
    r = Run(b, "XAUUSD", ctl={"drop_sl": 1, "x.XAUUSD.r.retcode_close": 10021, "retcode_sltp": 10016})
    assert len(r.positions) == 1 and r.positions[0]["sl"] <= 0
    assert "SANS STOP" in r.status("XAUUSD") and "PAS de stop" in r.alerts() and "elle a un stop" not in r.alerts(), (r.status("XAUUSD"), r.alerts())


def t_stop_hit(b):
    """the stop is hit while the position is open: nothing is left open, so no 'left open' status and no alert to close by hand"""
    r = Run(b, "XAUUSD,BTCUSD", at=[(500, "price.XAUUSD.r=4070.00,4070.13")])
    assert not r.positions
    mine = [d for d in r.deals if d["symbol"] == "XAUUSD.r"]
    assert [d["reason"] for d in mine] == [3, 4] and near(mine[1]["price"], 4070.00), mine      # closed by the broker: reason 4 = stop
    assert not r.status("XAUUSD").startswith("POSITION RESTEE OUVERTE"), r.status("XAUUSD")
    assert "n'a pas pu etre refermee" not in r.alerts(), r.alerts()
    assert r.status("XAUUSD") != "ok" and r.status("BTCUSD") == "ok" and list(r.sonde()) == ["BTCUSD"]


def t_removed(b):
    """the script is removed from the chart while the position is open (CTrade then sends nothing): status line and alert"""
    r = Run(b, "XAUUSD,BTCUSD", at=[(1000, "stopped=1")])
    assert len(r.positions) == 1 and r.positions[0]["sl"] > 0 and not r.kinds("close")
    assert r.status("XAUUSD").startswith("POSITION RESTEE OUVERTE") and "BTCUSD" not in r.rows
    assert "n'a pas pu etre refermee" in r.alerts() and r.sonde() == {}
    assert r.trailer is not None


def t_empty_name(b):
    """a comma in excess in the list of markets: no order on a market that was not asked for"""
    r = Run(b, "XAUUSD,,BTCUSD,")
    assert sorted({s for _, s, *_ in r.req}) == ["BTCUSD", "XAUUSD.r"], f"orders sent on {sorted({s for _, s, *_ in r.req})}"
    assert not r.positions


def t_file(b):
    """sonde.csv cannot be written: the user is told, instead of 'Vous pouvez le dire a Claude'"""
    r = Run(b, "XAUUSD", prepare=lambda files: (files / "claude").write_text("not a folder"))
    assert r.text is None and len(r.deals) == 2 and not r.positions
    assert "sonde.csv" in r.alerts() and "Vous pouvez le dire" not in r.alerts(), r.alerts()
    # an older result does not survive a run that stops half-way
    def old(files):
        (files / "claude" / "releve").mkdir(parents=True)
        (files / "claude" / "releve" / "sonde.csv").write_text(HEADER + "\nXAUUSD,XAUUSD.r,ok,0.0100,1,1,1,1,1,1,2,-0.5000,0,0,0,0.01,0.8621,100,1\n")
    r = Run(b, "XAUUSD", prepare=old, at=[(1000, "stopped=1")])
    assert "XAUUSD" not in r.sonde()
    r = Run(b, "XAUUSD", prepare=old, ctl={"account_trade_mode": 2})         # a refusal changes nothing
    assert near(r.sonde()["XAUUSD"]["commission_aller_retour"], 0.5)


def t_netting(b):
    """an account that is not in hedging mode: the script refuses (as ClaudeMains does)"""
    r = Run(b, "XAUUSD", ctl={"margin_mode": 0})
    r.nothing_sent()
    assert r.text is None and len(r.of("ALERT")) == 1


def t_rerun(b):
    """a second run after a position was left open: the old one is not touched, the file is replaced"""
    r = Run(b, "XAUUSD", ctl={"x.XAUUSD.r.retcode_close": 10021})
    assert len(r.positions) == 1
    (r.files / "_mock" / "control.txt").write_text("\n")
    (r.files / "_mock" / "log.txt").unlink()
    env = dict(os.environ, MOCK_FILES=str(r.files), MOCK_INPUT_InpSymbols="XAUUSD")
    subprocess.run([str(b)], env=env, check=True, timeout=60)
    text = (r.folder / "sonde.csv").read_text().split("\n")
    assert text[1].split(",")[2] == "ok" and text[1].split(",")[18] == str(FIRST + 1), text[1]
    assert len(text) == 4 and text[2].startswith("#currency=") and text[3] == ""
    state = (r.files / "_mock" / "state.txt").read_text()
    assert state.count("\nP|") == 1 and f"P|{FIRST}|" in state, "the position left by the first run was closed by the second"


def t_tick_size(b):
    """index quoted in steps of 0.25 with two digits: a stop rounded to the digits only (24953.62) is refused by the fake
    broker (ASSUMPTION of mock_mains.h: stops must be multiples of the tick size); the script must send 24953.50"""
    r = Run(b, symbols="US100", ctl={"sym.NAS100.tick_size": 0.25, "sym.NAS100.tick_value": 0.008621 * 25,
                                     "sym.NAS100.tick_value_loss": 0.008625 * 25})
    sl, dist = expected_sl("NAS100")
    assert near(dist, 46.3768, 1e-3) and near(round(sl / 0.25) * 0.25, 24953.50)
    assert r.status("US100") == "ok", r.rows["US100"]
    sent = r.kinds("open", "NAS100")
    assert len(sent) == 1 and near(sent[0][3], 24953.50) and sent[0][4] == 10009, sent
    assert near(r.row("US100")["tick_size"], 0.25) and not r.positions and len(r.deals) == 2


TESTS = [
    ("N1", "normal run on the default markets: requests, stops, csv, lire_sonde, commission conversion", t_normal, None),
    ("N2", "price moving while the position is open", t_move, None),
    ("N3", "names with spaces, alternative names, disabled market", t_names, None),
    ("N4", "terminal listing the new position late", t_lag, None),
    ("D1", "large demo balance: stop capped at 1.5 % of the price", t_big_balance, None),
    ("Q1", "market without any price", t_no_price, None),
    ("Q2", "first quote of a market arriving a moment late {F7}", t_first_tick, None),
    ("R1", "REAL / contest account: refusal, nothing sent", t_real, None),
    ("A1", "Algo Trading button off", t_algo_off, None),
    ("A2", "trading not allowed for this script only {F8}", t_algo_script, None),
    ("L1", "minimum lot too large for the stop budget", t_lot_too_big, None),
    ("M1", "margin too small", t_margin, None),
    ("B1", "buy refused by the server / closed session / account", t_refused, None),
    ("C1", "sale failing five times: position left open, status line and alert", t_close_fails, None),
    ("C2", "sale failing twice then accepted", t_close_retry, None),
    ("H1", "exit deal 3 s late in the history", t_history_late, None),
    ("H2", "exit deal later than the script waits {F1}", t_history_never_out, None),
    ("H3", "no deal in the history in time {F1}", t_history_never, None),
    ("O1", "buy answered without the order ticket {F1}", t_no_ticket, None),
    ("P1", "buy answered 'placed' without price", t_placed, None),
    ("K1", "position ticket changed by the server", t_reticket, None),
    ("S1", "stop silently removed by CTrade (market without stop orders) {F2}", t_stop_removed_by_ctrade, None),
    ("S2", "stop removed by CTrade and sale failing: naked position behind 'elle a un stop' {F2}", t_stop_removed_left_open, None),
    ("S3", "stop not kept by the broker and sale failing {F2}", t_stop_dropped_by_broker, None),
    ("T1", "stop hit before the resale {F3}", t_stop_hit, None),
    ("X1", "script removed while the position is open", t_removed, None),
    ("E1", "empty name in the list of markets {F6}", t_empty_name, None),
    ("W1", "sonde.csv cannot be written; older file {F5}", t_file, None),
    ("G1", "account not in hedging mode {F4}", t_netting, None),
    ("V1", "second run after a position was left open", t_rerun, None),
    ("Z1", "market whose tick size is larger than its point: the stop is a multiple of the tick size {F10}", t_tick_size, None),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mq5", default=str(LIVE / "mql5" / "SondeFP.mq5"))
    ap.add_argument("-k", default="", help="only the tests whose id or title contains this text (several: a,b)")
    ap.add_argument("--keep", action="store_true", help="keep the temporary directories")
    a = ap.parse_args()
    releve.OUT = tempfile.mkdtemp(prefix="sonde_out_")
    work = Path(tempfile.mkdtemp(prefix="sonde_build_"))
    binary = build(Path(a.mq5), work)
    print(f"built {Path(a.mq5).name} with mock_mains.h + mock_sonde.h")
    count = {"PASS": 0, "FAIL": 0, "XFAIL": 0, "XPASS": 0}
    seen = set()
    for tid, title, fn, xfail in TESTS:
        if not any(part.strip().lower() in (tid + " " + title).lower() for part in a.k.split(",")):
            continue
        del KEPT[:]
        note = ""
        try:
            note = fn(binary) or ""
            status, detail = "PASS", ""
        except AssertionError as e:
            tb = traceback.extract_tb(e.__traceback__)
            status, detail = "FAIL", f"{str(e)[:400] or tb[-1].line} (line {tb[-1].lineno})"
        except Exception as e:  # noqa: BLE001
            status, detail = "FAIL", f"{type(e).__name__}: {str(e)[:300]}"
        if xfail:
            status = {"FAIL": "XFAIL", "PASS": "XPASS"}[status]
            seen.add(xfail)
        count[status] += 1
        where = f"\n        [kept: {', '.join(str(k) for k in KEPT)}]" if a.keep else ""
        if not a.keep:
            for k in KEPT:
                shutil.rmtree(k, ignore_errors=True)
        mark = f" [{xfail}]" if xfail else ""
        print(f"{status:5s} {tid:3s}{mark} {title}" + (f"\n        -> {detail}" if detail else "") + (f"\n        {note}" if note else "") + where)
    if not a.keep:
        shutil.rmtree(work, ignore_errors=True)
    shutil.rmtree(releve.OUT, ignore_errors=True)
    n = sum(count.values())
    print(f"\n{n} tests: {count['PASS']} pass, {count['FAIL']} FAIL, {count['XFAIL']} expected failures (known defects of the script, "
          f"see the finding ids), {count['XPASS']} expected failures that now pass")
    for fid in sorted(seen, key=lambda x: int(x[1:])):
        print(f"  {fid}: {FINDINGS[fid]}")
    print("SondeFP : " + ("every test that should pass passes" if count["FAIL"] == 0 else "FAILURES"))
    return 1 if count["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
