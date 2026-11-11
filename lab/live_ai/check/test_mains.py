"""Run the REAL code of mql5/ClaudeMains.mq5 (translated to C++ by to_cpp.py, linked with the working imitation of
MetaTrader in mock_mains.h) and drive it ONLY through pont.py's Hands class, exactly as the brain will, plus a control
file for the fake world (server clock, prices, broker answers).  One test per promise of the EA.

    python3 live_ai/check/test_mains.py                 every test (about a minute)
    python3 live_ai/check/test_mains.py -k ttl,O7 -j 1  only the tests whose id or title contains "ttl" or "O7", one at a time
    python3 live_ai/check/test_mains.py --mq5 /path/Copy.mq5     test another copy of the EA (e.g. a corrected one)
    python3 live_ai/check/test_mains.py --lag           the same tests on a terminal that lists a new position only after
                                                        the handler that opened it has returned (worst case of the real one)

One line per test:  PASS / FAIL, or for a test tied to a known defect of the EA (finding id in brackets):
XFAIL = fails as reported (the promise is NOT kept), XPASS = passes now (the defect is gone: remove the mark).
Exit code 0 only if every test that should pass passes.

Inputs: the translation turns `input` variables into constants; here their initial values are wrapped, in the
TRANSLATED file only, in mock_input<T>("InpName", default) so that a test can start the same binary with another
value (env MOCK_INPUT_InpName).  The .mq5 itself is never modified.

WHAT THIS CANNOT PROVE about the real terminal (the imitation is hand-written from the MQL5 documentation and the
Standard Library's Trade.mqh; it is not MetaTrader):
  * that MetaEditor compiles the file (only g++ on the translation does);
  * the real values of FP Markets' symbols (names, lot sizes, stops level, tick value in EUR, sessions, filling,
    whether a stop is accepted in the order) and the real commission / fee fields;
  * the timing of the real terminal: OnTimer once a second (here every 15 ms), how long OrderSend blocks, when the
    list of positions is refreshed after a trade (the "lag" tests take the worst case allowed by the documentation);
  * the exact answers of the real trade server (which requests return false, partial fills, requotes, "placed" without
    a deal, re-quotes on gaps) and its own stop-out;
  * file sharing between MetaTrader under Wine and Python on macOS (locks, renames seen half-way, FileReadString on
    "\n"-only files - the documentation only promises "\r\n" -, FileMove into a missing folder);
  * TimeGMT() / TimeTradeServer() of the real terminal against the Mac's clock (brain timeout, Friday close, day change);
  * that global variables really survive in the user's terminal (they are saved when it closes normally).
"""
import argparse
import calendar
import concurrent.futures
import contextlib
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

HERE = Path(__file__).resolve().parent
LIVE = HERE.parent
sys.path.insert(0, str(LIVE))
from pont import Hands  # noqa: E402

MAGIC = 20261110
THU = "2026-11-12 10:30:00"            # server clock of the default fake world: a Thursday morning
HEAD = {"positions": "ticket,symbol,side,volume,price_open,sl,tp,price_current,profit,swap,time_open,ttl_deadline,comment",
        "deals": "deal,position,time,symbol,type,entry,volume,price,profit,swap,commission,fee,magic,reason,comment"}
INPUT_RE = re.compile(r"^const\s+(string|double|int|long|bool)\s+(Inp\w+)\s*=\s*(.+?);(\s*//.*)?$", re.M)


def ts(s):
    """'2026-11-12 10:30:00' on the server clock -> seconds, the way MT5 counts them"""
    return calendar.timegm(time.strptime(s, "%Y-%m-%d %H:%M:%S"))


def fp_offset(sec):
    """server clock minus UTC at server time `sec`, recomputed independently of pont.py: New York + 7 h"""
    for off in (7200, 10800):
        ny = datetime.fromtimestamp(sec - off, tz=timezone.utc).astimezone(ZoneInfo("America/New_York"))
        if ny.utcoffset().total_seconds() + 7 * 3600 == off:
            return off
    raise AssertionError(sec)


def build(mq5, work):
    cpp = work / "mains.cpp"
    subprocess.run([sys.executable, "-I", str(HERE / "to_cpp.py"), str(mq5), str(cpp)], check=True, capture_output=True)
    src = cpp.read_text()
    src, n = INPUT_RE.subn(lambda m: f'const {m[1]} {m[2]} = mock_input<{m[1]}>("{m[2]}", {m[3]});{m[4] or ""}', src)
    want = sum(1 for ln in Path(mq5).read_text(encoding="ascii").split("\n") if ln.startswith("input "))
    assert n == want, f"{n} inputs rewritten, {want} in the .mq5"
    cpp.write_text(src)
    (work / "run.cpp").write_text('#include "mock_mains.h"\n#include "mains.cpp"\n')
    extra = os.environ.get("MAINS_CXXFLAGS", "").split()                        # e.g. -fsanitize=address,undefined
    subprocess.run(["g++", "-std=c++17", "-O1", "-g", "-D_GLIBCXX_ASSERTIONS", *extra, "-I", str(HERE), "-I", str(work),
                    str(work / "run.cpp"), "-o", str(work / "mains")], check=True)
    return work / "mains"


class World:
    """One fake terminal + broker (the compiled EA) on its own temporary directory, and a Hands on its bridge folder."""

    def __init__(self, binary, server=THU, inputs=None, env=None, **ctl):
        self.binary = binary
        self.root = Path(tempfile.mkdtemp(prefix="mains_"))
        self.files = self.root / "Files"
        self.mock = self.files / "_mock"
        self.mock.mkdir(parents=True)
        self.dir = self.files / "claude"
        self.h = Hands(self.dir)
        self.inputs, self.env = dict(inputs or {}), dict(env or {})
        self.ctl = {"server_offset": ts(server) - time.time()}
        if LAG:
            self.ctl["lag"] = 1
        self.ctl.update(ctl)
        self.seq, self.ndo, self.proc = 0, 0, None
        self.start()

    # ---------------------------------------------------------------- process
    def start(self, inputs=None):
        if inputs is not None:
            self.inputs = dict(inputs)
        e = dict(os.environ, MOCK_FILES=str(self.files))
        e.update(self.env)
        e.update({"MOCK_INPUT_" + k: str(v) for k, v in self.inputs.items()})
        for name in ("stop", "ack.txt"):
            (self.mock / name).unlink(missing_ok=True)
        self._write_control()
        self.err = open(self.root / "stderr.txt", "ab")
        self.proc = subprocess.Popen([str(self.binary)], env=e, stdout=self.err, stderr=self.err)
        self._wait_ack()

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def check_alive(self):
        if self.proc is not None and self.proc.poll() is not None:
            tail = (self.root / "stderr.txt").read_text(errors="replace")[-400:]
            raise AssertionError(f"the EA process died (exit code {self.proc.returncode}) {tail!r}")

    def stop(self):
        """the terminal is closed normally (OnDeinit, global variables saved)"""
        (self.mock / "stop").touch()
        rc = self.proc.wait(10)
        self.proc = None
        assert rc == 0, f"exit code {rc} at a clean stop"

    def kill(self):
        """the terminal crashes / the computer is switched off"""
        self.proc.kill()
        self.proc.wait(10)
        self.proc = None

    def close(self, keep=False):
        if self.running():
            self.proc.kill()
            self.proc.wait(10)
        if not keep:
            shutil.rmtree(self.root, ignore_errors=True)

    # ---------------------------------------------------------------- control of the fake world
    def _write_control(self):
        self.seq += 1
        lines = [f"seq={self.seq}"] + [f"{k}={v}" for k, v in self.ctl.items() if v is not None]
        tmp = self.mock / "control.txt.tmp"
        tmp.write_text("\n".join(lines) + "\n")
        os.replace(tmp, self.mock / "control.txt")

    def _wait_ack(self):
        ack, want = self.mock / "ack.txt", f"seq={self.seq}\n"
        self.wait(lambda: ack.read_text().startswith(want), 15, "the fake terminal to take the control file")

    def set(self, d=None, **kw):
        self.ctl.update(d or {})
        self.ctl.update(kw)
        self._write_control()
        if self.running():
            self._wait_ack()

    def tick(self, n=2):
        """let the EA run n full loops (n=2: the export that follows OnTradeTransaction is done too)"""
        for _ in range(n):
            self.set()

    def wait(self, cond, timeout=10, what="a condition"):
        t0 = time.time()
        while True:
            self.check_alive()
            try:
                v = cond()
                if v:
                    return v
            except (FileNotFoundError, KeyError, ValueError, IndexError, pd.errors.ParserError, pd.errors.EmptyDataError):
                pass
            if time.time() - t0 > timeout:
                raise AssertionError(f"timeout ({timeout} s) waiting for {what}")
            time.sleep(0.02)

    def now(self):
        return int(time.time() + self.ctl["server_offset"])

    def sync(self):
        if self.running():
            self.wait(lambda: abs(self.h.account()["server_time"] - self.now()) <= 6, 10, "account.txt at the new server time")

    def at(self, when):
        self.set(server_offset=ts(when) - time.time())
        self.sync()

    def advance(self, seconds):
        self.set(server_offset=self.ctl["server_offset"] + seconds)
        self.sync()

    def price(self, sym, bid, ask):
        self.set({f"price.{sym}": f"{bid},{ask}"})
        self.tick(2)

    def outside(self, sym, side, volume, sl=0, tp=0, magic=0, comment=""):
        """a position opened without the EA: by hand (magic 0) or by another robot; returns its ticket"""
        before = {p["ticket"] for p in self.state()["positions"]}
        self.ndo += 1
        self.set({f"do.{self.ndo}": f"open {sym} {side} {volume} {sl} {tp} {magic} {comment}".strip()})
        new = [p["ticket"] for p in self.state()["positions"] if p["ticket"] not in before]
        assert len(new) == 1, new
        return new[0]

    def do(self, op):
        self.ndo += 1
        self.set({f"do.{self.ndo}": op})

    # ---------------------------------------------------------------- what the broker and the terminal recorded
    def state(self):
        st = {"balance": 1000.0, "positions": [], "deals": []}
        try:
            raw = (self.mock / "state.txt").read_text()
        except FileNotFoundError:
            return st
        for ln in raw.splitlines():
            f = ln.split("|")
            if f[0] == "P":
                st["positions"].append(dict(ticket=int(f[1]), symbol=f[2], side="buy" if f[3] == "0" else "sell", volume=float(f[4]),
                                            price_open=float(f[5]), sl=float(f[6]), tp=float(f[7]), magic=int(f[9]), time=int(f[10]),
                                            comment=f[11]))
            elif f[0] == "D":
                st["deals"].append(dict(deal=int(f[1]), position=int(f[3]), time=int(f[4]), symbol=f[5], type=int(f[6]), entry=int(f[7]),
                                        volume=float(f[8]), price=float(f[9]), profit=float(f[10]), commission=float(f[12]),
                                        fee=float(f[13]), magic=int(f[14]), reason=int(f[15]), comment=f[16]))
            elif ln.startswith("balance="):
                st["balance"] = float(ln[8:])
        return st

    def robot(self):
        return [p for p in self.state()["positions"] if p["magic"] == MAGIC]

    def pos(self, ticket):
        return next((p for p in self.state()["positions"] if p["ticket"] == ticket), None)

    def log(self, kind):
        try:
            raw = (self.mock / "log.txt").read_text(errors="replace")
        except FileNotFoundError:
            return []
        return [ln.split("\t", 1)[1] for ln in raw.splitlines() if ln.startswith(kind + "\t")]

    def trades(self, kind=None):
        """every request that reached the trade server ("open", "close" or "sltp")"""
        return [t for t in self.log("TRADE") if kind is None or t.startswith(kind + " ")]

    def untouched(self, before):
        """a position that the EA must never touch is still exactly as it was, and no request ever named it"""
        now = self.pos(before["ticket"])
        assert now == before, f"position {before['ticket']} opened outside the robot was changed: {before} -> {now}"
        assert not [t for t in self.trades() if f"position={before['ticket']} " in t], "a request was sent for a position that is not the robot's"

    # ---------------------------------------------------------------- the brain's orders (through pont.py)
    def open(self, *a, **kw):
        r = self.h.open(*a, **kw)
        self.tick(2)
        return r

    def must_open(self, *a, **kw):
        r = self.open(*a, **kw)
        assert r["ok"], f"open refused: {r.get('reason')!r}"
        return r

    def modify(self, *a, **kw):
        r = self.h.modify(*a, **kw)
        self.tick(2)
        return r

    def shut(self, *a, **kw):
        r = self.h.close(*a, **kw)
        self.tick(2)
        return r

    def close_all(self):
        r = self.h.close_all()
        self.tick(2)
        return r

    def raw(self, cid, text, wait=True, timeout=10):
        """a command file written directly (for what pont.py never writes); returns the answer as pont parses it"""
        tmp, p = self.dir / "cmd" / f"{cid}.part", self.dir / "cmd" / f"{cid}.txt"
        tmp.write_bytes(text.encode("latin-1"))
        os.replace(tmp, p)
        if not wait:
            return None
        res = self.dir / "res" / f"{cid}.txt"
        self.wait(res.exists, timeout, f"the answer to command {cid}")
        self.tick(2)
        return self.h._kv(f"res/{cid}.txt")


def cmd(**kw):
    return "".join(f"{k}={v}\r\n" for k, v in kw.items())


XAU = dict(symbol="XAUUSD", side="buy", volume="0.0500", sl="4075.23")       # a plain valid order (ask 4080.23)

# the known defects of the EA that the XFAIL tests demonstrate (ClaudeMains.mq5 as of 2026-11-11)
FINDINGS = {
    "H1": "the ttl deadline is deleted in the very pass that opened the position if the terminal does not list it yet",
    "H2": "locks, starting capital and ttl deadlines live in terminal global variables that are only written to disk when "
          "MetaTrader closes normally: a crash forgets them (GlobalVariablesFlush is never called)",
    "H3": "with a lot step that is not 0.01 / 0.1 / 1 (e.g. 0.5) the volume is rounded UP, beyond the risk cap",
    "H4": "'nan' in sl / tp / volume passes every check of the hands (only the broker can still refuse)",
    "H5": "on a symbol that does not take a stop inside the order, CTrade silently removes it: position without a stop",
    "H6": "close_all answers ok=1 even when positions could not be closed",
    "H7": "a comma in the tag shifts the columns of positions.csv / deals.csv (pont raises or reads wrong columns)",
    "H8": "if the order file cannot be moved to done/, the same order is executed again on every pass",
    "H9": "InpResetLocks does not lift the daily lock: it comes back at once",
    "H10": "a modify that changes nothing is reported as a refusal (10025 no changes)",
    "H11": "if the server clock steps back, account.txt and the forced closes stop until the clock has caught up",
    "H13": "(unverified premise) if balance / equity read 0 before the terminal is connected: false permanent stop, or "
           "kill switch and daily limit switched off",
    "H14": "ttl closes share one 10 s throttle: positions due together are closed 10 s apart, and one that cannot be "
           "closed (market closed) keeps the others from being closed at all",
}
TESTS = []
LAG = False                            # --lag: every test runs with the terminal's list of positions refreshed late


def test(tid, title, xfail=None):
    def deco(fn):
        TESTS.append((tid, title, xfail, fn))
        return fn
    return deco


# ====================================================================== 1. exports
@test("E1", "account.txt: every key pont.account() converts, refreshed at least every 5 s")
def e_account(W):
    with W() as w:
        a = w.h.account()
        assert (a["balance"], a["equity"], a["margin"], a["margin_free"]) == (1000.0, 1000.0, 0.0, 1000.0), a
        assert (a["currency"], a["leverage"], a["demo"], a["hedging"], a["trade_allowed"]) == ("EUR", 500, 1, 1, 1), a
        assert (a["start_balance"], a["day_start_balance"]) == (1000.0, 1000.0), a
        assert (a["max_risk_pct"], a["max_positions"], a["max_per_symbol"], a["daily_loss_pct"], a["kill_pct"]) == (1.0, 6, 2, 6.0, 50.0), a
        assert a["magic"] == str(MAGIC) and a["ea_version"] == "1.00" and a["server"] == "FPMarketsSC-Demo", a
        assert abs(a["ea_time_gmt"] - time.time()) <= 3 and abs(a["server_time"] - w.now()) <= 3, a
        assert abs(a["server_minus_gmt_sec"] - w.ctl["server_offset"]) <= 1, a
        assert a["blocked"] == "cerveau muet", a                               # the brain has not spoken yet
        w.h.alive()
        w.wait(lambda: w.h.account()["blocked"] == "", 8, "blocked to clear once the brain is alive")
        t1 = w.h.account()["ea_time_gmt"]
        w.wait(lambda: w.h.account()["ea_time_gmt"] > t1, 7, "account.txt to be rewritten within 5 s")
        r = w.must_open("XAUUSD", "buy", 0.02, sl=4075.23)
        a = w.h.account()
        assert a["balance"] == 999.95 and abs(a["equity"] - (999.95 - 0.22)) < 0.011, a      # commission, then the spread
        assert abs(a["margin"] - 0.02 * 100 * 4080.23 * 0.8621 / 500) < 0.011 and abs(a["margin_free"] - (a["equity"] - a["margin"])) < 0.011, a
        assert r["ticket"] == w.robot()[0]["ticket"]


@test("E2", "symbols.csv: six markets, broker names found, the missing market gives an empty row")
def e_symbols(W):
    with W(env={"MOCK_MISSING": "ETHUSD"}) as w:
        s = w.h.symbols()
        assert list(s.index) == ["XAUUSD", "US100", "BTCUSD", "ETHUSD", "EURUSD", "USDJPY"], list(s.index)
        assert (s.loc["XAUUSD", "name"], s.loc["US100", "name"], s.loc["EURUSD", "name"], s.loc["BTCUSD", "name"]) == ("XAUUSD.r", "NAS100", "EURUSD.r", "BTCUSD")
        assert pd.isna(s.loc["ETHUSD", "name"]) and s.loc["ETHUSD"].isna().all(), s.loc["ETHUSD"]
        x = s.loc["XAUUSD"]
        assert (x.digits, x.point, x.tick_size, x.tick_value, x.tick_value_loss, x.contract_size) == (2, 0.01, 0.01, 0.8621, 0.8625, 100.0), x
        assert (x.vol_min, x.vol_step, x.vol_max, x.stops_level, x.spread_points, x.bid, x.ask, x.trade_mode) == (0.01, 0.01, 100.0, 0, 13, 4080.10, 4080.23, 4), x
        assert abs(x.margin_1lot - 100 * 4080.23 * 0.8621 / 500) < 0.011 and x.ccy_profit == "USD" and abs(x.tick_time - w.now()) <= 70, x
        e = s.loc["EURUSD"]
        assert (e.digits, e.point, e.contract_size, e.bid, e.ask) == (5, 0.00001, 100000.0, 1.16, 1.16002), e
        assert s.loc["US100", "vol_min"] == 0.1 and s.loc["US100", "stops_level"] == 100
        assert "ClaudeMains: ETHUSD -> INTROUVABLE" in w.log("PRINT")
        names = (w.dir / "all_symbols.txt").read_text().split()
        assert "XAUUSD.r" in names and "ETHUSD" not in names, names
        w.h.alive()
        r = w.open("ETHUSD", "buy", 0.1, sl=3400.0)
        assert not r["ok"] and r["reason"] == "marche inconnu", r
        w.set({"price.XAUUSD.r": "4081.00,4081.13"})
        w.advance(61)                                                           # symbols.csv follows once a minute
        w.wait(lambda: w.h.symbols().loc["XAUUSD", "bid"] == 4081.00, 5, "symbols.csv to follow the price at the next minute")


@test("E3", "positions.csv: the robot's positions only, every column, profit follows the price")
def e_positions(W):
    with W() as w:
        assert w.h.positions().empty and ",".join(w.h.positions().columns) == HEAD["positions"]
        w.h.alive()
        hand = w.outside("USDJPY.r", "buy", 0.01)
        r = w.must_open("XAUUSD", "buy", 0.50, sl=4075.23, tp=4100.0, tag="e3")
        p = w.h.positions()
        assert len(p) == 1 and ",".join(p.columns) == HEAD["positions"], p
        q = p.iloc[0]
        assert (q.ticket, q.symbol, q.side, q.volume, q.price_open, q.sl, q.tp) == (r["ticket"], "XAUUSD.r", "buy", 0.02, 4080.23, 4075.23, 4100.0), q
        assert (q.price_current, q.profit, q.swap, q.ttl_deadline, q.comment) == (4080.10, -0.22, 0.0, 0, "CM e3"), q
        assert abs(q.time_open - w.now()) <= 5 and hand not in set(p.ticket)
        w.set({"price.XAUUSD.r": "4082.23,4082.36"})
        w.advance(6)
        w.wait(lambda: w.h.positions().iloc[0].profit == round(200 * 0.8621 * 0.02, 2), 5, "the profit to follow the price within 5 s")


@test("E4", "deals.csv: fee column, rewritten right after each transaction and once a minute, balance operations left out")
def e_deals(W):
    with W() as w:
        assert w.h.deals().empty and ",".join(w.h.deals().columns[:-1]) == HEAD["deals"]
        w.h.alive()
        r = w.h.open("XAUUSD", "buy", 0.02, sl=4075.23, tag="e4")
        assert r["ok"], r
        w.wait(lambda: len(w.h.deals()) == 1, 2, "the entry deal in deals.csv right after the order")
        d = w.h.deals().iloc[0]
        assert (d.position, d.symbol, d.type, d.entry, d.volume, d.price, d.profit) == (r["ticket"], "XAUUSD.r", "buy", 0, 0.02, 4080.23, 0.0), d
        assert (d.swap, d.commission, d.fee, d.magic, d.reason, d.comment) == (0.0, -0.05, 0.0, MAGIC, 3, "CM e4"), d
        assert d.time_utc == pd.Timestamp(d.time - fp_offset(d.time), unit="s", tz="UTC"), d
        b = w.must_open("BTCUSD", "buy", 0.02, sl=99512.0)
        w.wait(lambda: len(w.h.deals()) == 2, 2, "the second entry deal")
        assert w.h.deals().iloc[1].fee == -0.34 and w.h.deals().iloc[1].position == b["ticket"], w.h.deals().iloc[1]      # the broker's "fee"
        w.do("balance 50")                                                      # a deposit: not a trade
        w.tick(2)
        assert len(w.h.deals()) == 2 and w.h.account()["balance"] == round(1000 - 0.05 - 0.34 + 50, 2)
        w.set({"price.XAUUSD.r": "4075.00,4075.13"})                            # through the stop: the BROKER closes
        w.wait(lambda: len(w.h.deals()) == 3, 3, "the stop's exit deal in deals.csv")
        x = w.h.deals().iloc[2]
        assert (x.position, x.type, x.entry, x.reason, x.price, x.comment) == (r["ticket"], "sell", 1, 4, 4075.00, "[sl 4075.23]"), x
        assert x.profit == round(-523 * 0.8625 * 0.02, 2), x
        minute, m1 = w.now() // 60, (w.dir / "deals.csv").stat().st_mtime_ns
        w.tick(3)
        assert (w.dir / "deals.csv").stat().st_mtime_ns == m1 or w.now() // 60 != minute      # nothing happened: not rewritten...
        w.advance(61)
        w.wait(lambda: (w.dir / "deals.csv").stat().st_mtime_ns != m1, 3, "deals.csv to be rewritten at the next minute")


def bars_ok(w, base, name, tf, sec, count, bid0, digits, point, spread):
    now = w.now()
    b = w.h.bars(base, tf)
    if w.now() // 60 != now // 60:
        return False                                                            # a minute just changed: look again
    last = now // sec * sec - sec                                               # last COMPLETED bar, server clock
    assert len(b) == count and list(b.columns) == ["open", "high", "low", "close", "tick_volume", "spread"], (base, tf, len(b))
    assert str(b.index.tz) == "UTC" and b.index.is_monotonic_increasing and b.index.is_unique
    if sec <= 300:                                                              # (H1 / D1 go back across a change of the US clock)
        assert (b.index[1:] - b.index[:-1] == pd.Timedelta(seconds=sec)).all()
    if b.index[-1] != pd.Timestamp(last - fp_offset(last), unit="s", tz="UTC"):
        return False                                                            # the export of this minute is not there yet
    k = last // sec
    o, c = bid0 * (1 + ((k * 37) % 201 - 100) * 1e-5), bid0 * (1 + (((k + 1) * 37) % 201 - 100) * 1e-5)
    x = b.iloc[-1]
    tol = 0.51 * point
    assert abs(x.open - o) < tol and abs(x.close - c) < tol and abs(x.high - (max(o, c) + 3 * point)) < tol and abs(x.low - (min(o, c) - 2 * point)) < tol, (base, tf, x)
    assert x.tick_volume == 50 + k % 17 and x.spread == spread, x
    return True


@test("E5", "bars M1/M5/H1/D1: completed bars only, right count, index converted to UTC (winter +2 h and summer +3 h)")
def e_bars(W):
    for server in (THU, "2026-07-15 12:00:20"):
        with W(server=server) as w:
            for base, name, bid0, dg, pt, sp in (("XAUUSD", "XAUUSD.r", 4080.10, 2, 0.01, 13), ("US100", "NAS100", 25000.0, 2, 0.01, 150),
                                                 ("EURUSD", "EURUSD.r", 1.16, 5, 0.00001, 2)):
                for tf, sec, count in (("M1", 60, 240), ("M5", 300, 300), ("H1", 3600, 300), ("D1", 86400, 300)):
                    w.wait(lambda: bars_ok(w, base, name, tf, sec, count, bid0, dg, pt, sp), 5, f"bars {base} {tf}")
            w.advance(60)                                                       # a new minute: a new last bar
            w.wait(lambda: bars_ok(w, "XAUUSD", "XAUUSD.r", "M1", 60, 240, 4080.10, 2, 0.01, 13), 5, "the next M1 bar")
    assert fp_offset(ts(THU)) == 7200 and fp_offset(ts("2026-07-15 12:00:20")) == 10800


@test("E6", "ea_alive() and ping(): true while the EA runs, false once it is stopped; pont removes the unanswered order")
def e_alive(W):
    with W() as w:
        assert w.h.ea_alive() and w.h.ping()
        w.stop()
        time.sleep(2.2)
        assert not w.h.ea_alive(max_age=2)
        r = w.h.send("ping", timeout=1.0)
        assert not r["ok"] and r["reason"] == "pas de réponse des mains" and not list((w.dir / "cmd").glob("*.txt")), r
        w.start()
        assert w.h.ea_alive() and w.h.ping()


# ====================================================================== 2. open
@test("O1", "open without a stop (0, absent, negative): refused, nothing is sent to the broker")
def o_nostop(W):
    with W() as w:
        w.h.alive()
        r = w.open("XAUUSD", "buy", 0.05, sl=0)
        assert not r["ok"] and r["reason"] == "stop obligatoire", r
        r = w.open("XAUUSD", "sell", 0.05, sl=-4085.0)
        assert not r["ok"] and r["reason"] == "stop obligatoire", r
        r = w.raw("a1", cmd(action="open", symbol="XAUUSD", side="buy", volume="0.05"))
        assert r["ok"] == "0" and r["reason"] == "stop obligatoire", r
        assert not w.trades() and not w.state()["positions"]


@test("O2", "open with the stop on the wrong side (buy above / sell below the price): refused; the right side is placed at the broker")
def o_wrongside(W):
    with W() as w:
        w.h.alive()
        for side, sl in (("buy", 4090.0), ("buy", 4080.10), ("sell", 4070.0), ("sell", 4080.23)):
            r = w.open("XAUUSD", side, 0.05, sl=sl)
            assert not r["ok"] and r["reason"] == "stop du mauvais cote ou trop pres", (side, sl, r)
        assert not w.trades()
        r = w.must_open("XAUUSD", "sell", 0.05, sl=4085.10)
        p = w.pos(r["ticket"])
        assert (p["side"], p["sl"], p["price_open"], p["magic"]) == ("sell", 4085.10, 4080.10, MAGIC) and r["sl"] == 4085.10 and r["price"] == 4080.10, (p, r)


@test("O3", "open with the stop inside the broker's stops level: refused")
def o_stopslevel(W):
    with W() as w:
        w.h.alive()
        for sl in (24999.50, 24999.00):                                         # NAS100: level 100 points = 1.00 under the bid 25000.00
            r = w.open("US100", "buy", 1.0, sl=sl)
            assert not r["ok"] and r["reason"] == "stop du mauvais cote ou trop pres", (sl, r)
        assert not w.trades()
        r = w.must_open("US100", "buy", 1.0, sl=24970.00)
        assert r["volume"] == 0.3, r
        w.set({"sym.XAUUSD.r.stops_level": 50})
        r = w.open("XAUUSD", "buy", 0.05, sl=4079.80)                           # 0.30 under the bid, level 0.50
        assert not r["ok"] and r["reason"] == "stop du mauvais cote ou trop pres", r
        w.set({"sym.XAUUSD.r.stops_level": 0})
        assert w.must_open("XAUUSD", "buy", 0.05, sl=4079.80)["volume"] == 0.05   # the same order passes when the level is 0


@test("O4", "open on an unknown market: refused; the broker's own name is accepted")
def o_unknown(W):
    with W() as w:
        w.h.alive()
        for sym in ("DOGEUSD", "", "xauusd", "XAUUSD.x", "JPN225"):             # JPN225 exists at the broker but was not requested
            r = w.open(sym, "buy", 0.05, sl=4075.23)
            assert not r["ok"] and r["reason"] == "marche inconnu", (sym, r)
        assert not w.trades()
        assert w.must_open("XAUUSD.r", "buy", 0.05, sl=4075.23)["volume"] == 0.02


@test("O5", "open with an invalid side: refused")
def o_side(W):
    with W() as w:
        w.h.alive()
        for side in ("long", "BUY", "", "0"):
            r = w.open("XAUUSD", side, 0.05, sl=4075.23)
            assert not r["ok"] and r["reason"] == "side doit etre buy ou sell", (side, r)
        r = w.raw("a1", cmd(action="open", symbol="XAUUSD", volume="0.05", sl="4075.23"))
        assert r["ok"] == "0" and r["reason"] == "side doit etre buy ou sell", r
        assert not w.trades()


@test("O6", "open that has expired (expire < server time): refused; a still valid one is executed")
def o_expired(W):
    with W() as w:
        w.h.alive()
        r = w.open("XAUUSD", "buy", 0.05, sl=4075.23, valid_sec=-8)
        assert not r["ok"] and r["reason"] == "ordre perime", r
        r = w.raw("a1", cmd(action="open", expire=w.now() - 1, **XAU))
        assert r["ok"] == "0" and r["reason"] == "ordre perime", r
        assert not w.trades()
        r = w.raw("a2", cmd(action="open", expire=w.now() + 30, **XAU))
        assert r["ok"] == "1", r


def cap_case(w, base, side, req, dist):
    """one order; returns (answer, expected volume, risk of 1 lot, cap), recomputed here from symbols.csv and account.txt"""
    s = w.h.symbols().loc[base]
    price = s.ask if side == "buy" else s.bid
    sl = round(price - dist if side == "buy" else price + dist, int(s.digits))
    w.tick(2)
    cap = w.h.account()["balance"] * 0.01
    r1 = abs(price - sl) / s.tick_size * s.tick_value_loss                      # EUR lost by 1 lot at the stop
    exp = math.floor(min(req, cap / r1, s.vol_max) / s.vol_step + 1e-9) * s.vol_step
    r = w.must_open(base, side, req, sl=sl)
    p = w.pos(r["ticket"])
    assert abs(r["volume"] - exp) < 1e-9 and abs(p["volume"] - exp) < 1e-9, (base, r, exp)
    assert p["sl"] == sl and r["sl"] == sl and r["price"] == price, (base, r, p)
    assert r["risk_money"] <= cap + 0.005 and abs(r["risk_money"] - r1 * exp) < 0.0051, (base, r, r1 * exp, cap)
    return r, exp, r1, cap


@test("O7", "volume reduced to the risk cap (1 % of the balance, tick value in EUR), on five markets; the real loss at the stop stays under the cap")
def o_riskcap(W):
    with W() as w:
        w.h.alive()
        for base, side, req, dist, want in (("XAUUSD", "buy", 0.50, 5.00, 0.02), ("EURUSD", "sell", 1.0, 0.00200, 0.05),
                                            ("USDJPY", "buy", 1.0, 0.350, 0.05), ("US100", "buy", 5.0, 50.0, 0.2),
                                            ("BTCUSD", "sell", 1.0, 500.0, 0.02), ("XAUUSD", "buy", 0.01, 5.00, 0.01)):
            r, exp, r1, cap = cap_case(w, base, side, req, dist)
            assert abs(exp - want) < 1e-9, (base, exp, want)                    # the figures worked out by hand
            assert w.shut(r["ticket"])["ok"]
        r, exp, r1, cap = cap_case(w, "XAUUSD", "buy", 0.50, 5.00)
        w.set({"price.XAUUSD.r": f"{r['sl']},{r['sl'] + 0.13}"})                # the price comes down exactly to the stop
        w.wait(lambda: not w.robot(), 3, "the broker to execute the stop")
        out = [d for d in w.state()["deals"] if d["position"] == r["ticket"] and d["entry"] == 1][0]
        assert out["reason"] == 4 and abs(-out["profit"] - r["risk_money"]) < 0.011 and -out["profit"] <= cap + 0.005, (out, r, cap)


@test("O8", "open refused when even the minimum lot would risk more than the cap")
def o_minlot(W):
    with W() as w:
        w.h.alive()
        r = w.open("XAUUSD", "buy", 0.50, sl=4060.23)                           # 20.00 away: 0.01 lot = 17.25 EUR > 10 EUR
        assert not r["ok"] and r["reason"] == "limite de risque : le lot minimum (0.01) risquerait 17.25, limite 10.00", r
        r = w.open("US100", "sell", 5.0, sl=27000.0)
        assert not r["ok"] and r["reason"].startswith("limite de risque : le lot minimum (0.10)"), r
        assert not w.trades()


def six(w):
    out = []
    for base, side, sl in (("XAUUSD", "buy", 4075.23), ("XAUUSD", "sell", 4085.10), ("EURUSD", "sell", 1.162), ("EURUSD", "buy", 1.158),
                           ("USDJPY", "buy", 154.654), ("USDJPY", "sell", 155.35)):
        out.append(w.must_open(base, side, 1.0, sl=sl)["ticket"])
    return out


@test("O9", "at most 6 positions in total (positions opened by hand do not count)")
def o_maxtotal(W):
    with W() as w:
        w.h.alive()
        w.outside("BTCUSD", "buy", 0.01)
        t = six(w)
        for base, sl in (("US100", 24950.0), ("BTCUSD", 99512.0)):
            r = w.open(base, "buy", 1.0, sl=sl)
            assert not r["ok"] and r["reason"] == "trop de positions ouvertes", r
        assert len(w.robot()) == 6 and len(w.trades("open")) == 6
        assert w.shut(t[0])["ok"]
        assert w.must_open("US100", "buy", 1.0, sl=24950.0)["volume"] == 0.2


@test("O10", "at most 2 positions per market (whatever name is used for it)")
def o_maxsym(W):
    with W() as w:
        w.h.alive()
        w.outside("XAUUSD.r", "buy", 0.01)
        a = w.must_open("XAUUSD", "buy", 0.5, sl=4075.23)
        w.must_open("XAUUSD.r", "sell", 0.5, sl=4085.10)
        for sym in ("XAUUSD", "XAUUSD.r"):
            r = w.open(sym, "buy", 0.5, sl=4075.23)
            assert not r["ok"] and r["reason"] == "trop de positions sur ce marche", r
        assert len(w.robot()) == 2
        w.must_open("EURUSD", "buy", 1.0, sl=1.158)                             # another market is still open to the brain
        assert w.shut(a["ticket"])["ok"]
        w.must_open("XAUUSD", "buy", 0.5, sl=4075.23)


@test("O11", "open refused when the free margin is not enough")
def o_margin(W):
    with W() as w:
        w.h.alive()
        r = w.open("BTCUSD", "buy", 1.0, sl=99962.0)                            # 50.00 away: 0.23 lot allowed by the risk, margin 1983 EUR
        assert not r["ok"] and r["reason"] == "marge insuffisante", r
        assert not w.trades()


@test("O12", "open refused when the market is not fully tradable, has no price, or the server says it is closed")
def o_closed(W):
    with W() as w:
        w.h.alive()
        for mode in (3, 0, 1):                                                  # close only, disabled, long only
            w.set({"sym.XAUUSD.r.trade_mode": mode})
            r = w.open("XAUUSD", "buy", 0.05, sl=4075.23)
            assert not r["ok"] and r["reason"] == "marche ferme ou non negociable", (mode, r)
        w.set({"sym.XAUUSD.r.trade_mode": None, "price.XAUUSD.r": "0,0"})
        r = w.open("XAUUSD", "buy", 0.05, sl=4075.23)
        assert not r["ok"] and r["reason"] == "pas de prix", r
        assert not w.trades()
        w.set({"price.XAUUSD.r": None, "retcode_open": 10018})                  # outside the trading session
        r = w.open("XAUUSD", "buy", 0.05, sl=4075.23)
        assert not r["ok"] and r["reason"] == "refuse par le serveur : 10018 market closed", r
        assert not w.state()["positions"]


@test("O13", "a refusal of the trade server is reported with its code, and nothing is recorded as open")
def o_server(W):
    with W() as w:
        w.h.alive()
        for extra in ({}, {"ordersend_true": 1}):                               # whether OrderSend itself answers false or true
            for code, text in ((10006, "rejected"), (10004, "requote (4080.10/4080.23)"), (10019, "not enough money"), (10031, "no connection")):
                w.set(dict(extra, retcode_open=code))
                r = w.open("XAUUSD", "buy", 0.05, sl=4075.23, ttl_min=30)
                assert not r["ok"] and r["reason"] == f"refuse par le serveur : {code} {text}", (extra, code, r)
                assert "ticket" not in r
            w.set({"ordersend_true": None, "retcode_open": None})
        assert not w.state()["positions"] and w.h.positions().empty and len(w.trades("open")) == 8
        assert w.must_open("XAUUSD", "buy", 0.05, sl=4075.23)["volume"] == 0.02


@test("O14", "ttl: the deadline is stored (positions.csv) and the position is closed at the deadline")
def o_ttl(W):
    with W() as w:
        w.h.alive()
        a = w.must_open("XAUUSD", "buy", 0.02, sl=4075.23, ttl_min=30)
        b = w.must_open("EURUSD", "buy", 0.05, sl=1.158)
        p = w.h.positions().set_index("ticket")
        assert abs(p.loc[a["ticket"], "ttl_deadline"] - (p.loc[a["ticket"], "time_open"] + 1800)) <= 2 and p.loc[b["ticket"], "ttl_deadline"] == 0, p
        w.advance(29 * 60)
        w.tick(3)
        assert len(w.robot()) == 2 and not w.trades("close")
        w.advance(70)
        w.wait(lambda: [q["ticket"] for q in w.robot()] == [b["ticket"]], 3, "the position to be closed at its deadline")
        out = [d for d in w.state()["deals"] if d["position"] == a["ticket"] and d["entry"] == 1][0]
        assert out["reason"] == 3 and abs(out["time"] - (p.loc[a["ticket"], "ttl_deadline"] + 10)) <= 12, out
        assert f"Robot Claude : Duree max atteinte : position {a['ticket']} fermee." in w.log("NOTIFY")
        w.wait(lambda: len(w.h.positions()) == 1, 3, "positions.csv")


@test("O14b", "ttl: still enforced after the terminal has been closed and reopened, with the brain stopped")
def o_ttl_restart(W):
    with W() as w:
        w.h.alive()
        a = w.must_open("XAUUSD", "buy", 0.02, sl=4075.23, ttl_min=30)
        w.stop()
        (w.dir / "brain_alive.txt").unlink()                                    # the brain is gone
        w.set(server_offset=w.ctl["server_offset"] + 10 * 60)
        w.start()
        w.tick(3)
        assert [q["ticket"] for q in w.robot()] == [a["ticket"]] and w.h.account()["blocked"] == "cerveau muet"
        assert w.h.positions().iloc[0].ttl_deadline > 0
        w.advance(21 * 60)
        w.wait(lambda: not w.robot(), 3, "the position to be closed at its deadline after the restart")


@test("O14c", "ttl: still enforced after a CRASH of the terminal (global variables are only saved when it closes)", xfail="H2")
def o_ttl_crash(W):
    with W() as w:
        w.h.alive()
        w.must_open("XAUUSD", "buy", 0.02, sl=4075.23, ttl_min=30)
        w.kill()
        w.start()
        w.tick(3)
        assert w.h.positions().iloc[0].ttl_deadline > 0, "after the crash the position has lost its deadline (ttl_deadline=0): it will never be closed by the hands"
        w.advance(31 * 60)
        w.wait(lambda: not w.robot(), 3, "the position to be closed at its deadline after the crash")


@test("O14d", "ttl: kept when the terminal shows the new position a moment after OrderSend has returned", xfail="H1")
def o_ttl_lag(W):
    with W(lag=1) as w:
        w.h.alive()
        a = w.must_open("XAUUSD", "buy", 0.02, sl=4075.23, ttl_min=30)
        w.wait(lambda: len(w.h.positions()) == 1, 3, "positions.csv")
        assert w.h.positions().iloc[0].ttl_deadline > 0, "the deadline was deleted in the same pass (the position was not listed yet): ttl_deadline=0, never closed"
        w.advance(31 * 60)
        w.wait(lambda: not w.robot(), 3, "the position to be closed at its deadline")
        assert a["ticket"]


@test("O14e", "ttl: three positions due together are all closed, even when one of them cannot be (its market is closed)", xfail="H14")
def o_ttl_starved(W):
    with W() as w:
        w.h.alive()
        a = w.must_open("EURUSD", "buy", 0.05, sl=1.158, ttl_min=30)["ticket"]
        b = w.must_open("USDJPY", "buy", 0.05, sl=154.654, ttl_min=30)["ticket"]
        c = w.must_open("XAUUSD", "buy", 0.02, sl=4075.23, ttl_min=30)["ticket"]
        w.set({"sym.XAUUSD.r.trade_mode": 0})                                   # gold cannot be traded for now (daily break)
        w.advance(30 * 60 + 5)
        for _ in range(3):
            w.tick(3)
            w.advance(11)
        left = sorted(p["ticket"] for p in w.robot())
        assert left == [c], (f"{len(left)} positions still open 38 s after their deadline (tickets {left}; {a} and {b} are on open markets): "
                             f"only gold was tried, {len(w.trades('close'))} times")


@test("O15", "target on the wrong side: refused; a valid target is placed and executed by the broker")
def o_tp(W):
    with W() as w:
        w.h.alive()
        for side, sl, tp in (("buy", 4075.23, 4080.00), ("sell", 4085.10, 4080.20)):
            r = w.open("XAUUSD", side, 0.02, sl=sl, tp=tp)
            assert not r["ok"] and r["reason"] == "objectif du mauvais cote ou trop pres", r
        assert not w.trades()
        r = w.must_open("XAUUSD", "buy", 0.02, sl=4075.23, tp=4090.0)
        assert w.pos(r["ticket"])["tp"] == 4090.0
        w.set({"price.XAUUSD.r": "4090.50,4090.63"})
        w.wait(lambda: not w.robot(), 3, "the broker to execute the target")
        out = w.state()["deals"][-1]
        assert out["reason"] == 5 and out["profit"] > 0, out


@test("O16", "Algo Trading button off: account.txt says so, opens are refused without reaching the broker")
def o_algo(W):
    with W() as w:
        w.h.alive()
        a = w.must_open("XAUUSD", "buy", 0.02, sl=4075.23)
        n = len(w.trades())
        w.set(terminal_trade_allowed=0)
        w.wait(lambda: w.h.account()["trade_allowed"] == 0 and w.h.account()["blocked"] == "trading automatique desactive dans MT5", 8, "account.txt")
        r = w.open("EURUSD", "buy", 0.05, sl=1.158)
        assert not r["ok"] and r["reason"] == "trading automatique desactive dans MT5" and len(w.trades()) == n, r
        r = w.shut(a["ticket"])                                                  # nothing can be closed either: MetaTrader refuses
        assert not r["ok"] and r["reason"] == "refuse par le serveur : 10027 auto trading disabled by client", r
        w.set(terminal_trade_allowed=None)
        assert w.shut(a["ticket"])["ok"] and w.must_open("EURUSD", "buy", 0.05, sl=1.158)


@test("O17", "risk cap on a market whose lot step is 0.5: the volume is rounded DOWN to the step", xfail="H3")
def o_step(W):
    with W(**{"sym.NAS100.vol_step": 0.5, "sym.NAS100.vol_min": 0.5}) as w:
        w.h.alive()
        r = w.open("US100", "buy", 5.0, sl=24986.50)                            # 15.00 away: 12.94 EUR per lot, cap 10 EUR -> 0.77 -> 0.5 lot
        assert r["ok"], r
        assert r["volume"] == 0.5 and r["risk_money"] <= 10.0, f"0.5 lot allowed (6.47 EUR), {r['volume']} lot opened: risk {r['risk_money']} EUR for a cap of 10.00"


@test("O18", "sl=nan / volume=nan in an order: refused by the hands themselves", xfail="H4")
def o_nan(W):
    with W() as w:
        w.h.alive()
        r = w.raw("a1", cmd(action="open", symbol="XAUUSD", side="buy", volume="0.05", sl="nan"))
        sent = w.trades("open")
        assert r["ok"] == "0" and not sent, f"the hands sent the order to the broker with the full requested volume and no usable stop: {sent[0][:95] if sent else r}"
        r = w.raw("a2", cmd(action="open", symbol="XAUUSD", side="buy", volume="nan", sl="4075.23"))
        assert r["ok"] == "0", f"volume=nan opened {r.get('volume')} lot"
        t = w.must_open("EURUSD", "buy", 0.05, sl=1.158)["ticket"]
        r = w.raw("a3", cmd(action="modify", ticket=t, sl="nan"))
        assert r["ok"] == "0" and not w.trades("sltp") and w.pos(t)["sl"] == 1.158, f"modify sl=nan was sent to the broker: {w.trades('sltp')[-1][:80]}"


@test("O19", "a market where the broker does not take a stop inside the order: no position is opened without a stop", xfail="H5")
def o_ordermode(W):
    with W(**{"sym.XAUUSD.r.order_mode": 127 - 16}) as w:                       # SYMBOL_ORDER_MODE without SYMBOL_ORDER_SL
        w.h.alive()
        r = w.open("XAUUSD", "buy", 0.02, sl=4075.23)
        p = w.robot()
        assert not r["ok"] and not p, f"answer ok={r['ok']} sl={r.get('sl')} but at the broker the position has sl={p[0]['sl'] if p else None}: CTrade removed the stop"


# ====================================================================== 3. modify
@test("M1", "modify: the stop only moves toward the price (buy and sell), the target is free")
def m_direction(W):
    with W() as w:
        w.h.alive()
        t = w.must_open("XAUUSD", "buy", 0.02, sl=4075.23)["ticket"]
        for sl in (4070.0, 4075.22):
            r = w.modify(t, sl=sl)
            assert not r["ok"] and r["reason"] == "le stop ne peut que se rapprocher du prix" and w.pos(t)["sl"] == 4075.23, r
        r = w.modify(t, sl=4078.0)
        assert r["ok"] and r["sl"] == 4078.0 and r["tp"] == 0.0 and w.pos(t)["sl"] == 4078.0, r
        r = w.modify(t, sl=4077.99)
        assert not r["ok"] and r["reason"] == "le stop ne peut que se rapprocher du prix" and w.pos(t)["sl"] == 4078.0, r
        for sl in (4080.10, 4081.0):                                            # at / beyond the price
            r = w.modify(t, sl=sl)
            assert not r["ok"] and r["reason"] == "stop trop pres du prix" and w.pos(t)["sl"] == 4078.0, r
        w.price("XAUUSD.r", 4090.00, 4090.13)
        assert w.modify(t, sl=4082.0)["ok"] and w.pos(t)["sl"] == 4082.0        # above the entry price: allowed (toward the price)
        for tp in (4100.0, 4095.0, 4120.0, 0.0):                                # set, nearer, farther, removed
            r = w.modify(t, tp=tp)
            assert r["ok"] and r["tp"] == tp and r["sl"] == 4082.0 and (w.pos(t)["tp"], w.pos(t)["sl"]) == (tp, 4082.0), (tp, r)
        s = w.must_open("EURUSD", "sell", 0.05, sl=1.162)["ticket"]
        r = w.modify(s, sl=1.163)
        assert not r["ok"] and r["reason"] == "le stop ne peut que se rapprocher du prix" and w.pos(s)["sl"] == 1.162, r
        assert w.modify(s, sl=1.161, tp=1.15)["ok"] and (w.pos(s)["sl"], w.pos(s)["tp"]) == (1.161, 1.15)
        assert not w.modify(s, sl=1.1615)["ok"] and w.pos(s)["sl"] == 1.161


@test("M2", "modify: unknown ticket refused; a stop can never be removed")
def m_unknown(W):
    with W() as w:
        w.h.alive()
        t = w.must_open("XAUUSD", "buy", 0.02, sl=4075.23)["ticket"]
        for ticket in (424242, 0):
            r = w.modify(ticket, sl=4078.0)
            assert not r["ok"] and r["reason"] == "position introuvable", r
        r = w.raw("a1", cmd(action="modify", ticket="abc", sl="4078.0"))
        assert r["ok"] == "0" and r["reason"] == "position introuvable", r
        for sl in ("0", "-1", "abc", ""):
            r = w.raw("b" + str(len(sl)) + sl[:1].replace("-", "m"), cmd(action="modify", ticket=t, sl=sl))
            assert r["ok"] == "0" and r["reason"] == "stop obligatoire" and w.pos(t)["sl"] == 4075.23, (sl, r)
        assert not w.trades("sltp")


@test("M3", "modify / close: a position with another magic number (opened by hand or by another robot) is refused and left alone")
def m_magic(W):
    with W() as w:
        w.h.alive()
        hand = w.pos(w.outside("XAUUSD.r", "buy", 0.01, sl=4000.0))
        other = w.pos(w.outside("EURUSD.r", "sell", 0.01, sl=1.2, magic=777, comment="other robot"))
        for p in (hand, other):
            r = w.modify(p["ticket"], sl=4050.0 if p is hand else 1.19, tp=1.0)
            assert not r["ok"] and r["reason"] == "position introuvable", r
            for vol in (0.0, 0.01):
                r = w.shut(p["ticket"], vol)
                assert not r["ok"] and r["reason"] == "position introuvable", r
            w.untouched(p)
        assert w.h.positions().empty and not w.trades()


@test("M4", "modify with exactly the values already in place is answered ok", xfail="H10")
def m_same(W):
    with W() as w:
        w.h.alive()
        t = w.must_open("XAUUSD", "buy", 0.02, sl=4075.23, tp=4100.0)["ticket"]
        r = w.modify(t, sl=4075.23, tp=4100.0)
        assert r["ok"], f"ok=False, reason={r['reason']!r} (the server answers 10025 'no changes' and OrderSend returns false)"


# ====================================================================== 4. close
@test("C1", "close: the position is closed at the market, the answer gives the price; closing twice is refused")
def c_close(W):
    with W() as w:
        w.h.alive()
        t = w.must_open("XAUUSD", "buy", 0.02, sl=4075.23)["ticket"]
        r = w.shut(t)
        assert r["ok"] and r["price"] == 4080.10 and not w.robot() and w.h.positions().empty, r
        d = w.h.deals().iloc[-1]
        assert (d.position, d.type, d.entry, d.volume, d.price, d.profit, d.commission, d.reason) == (t, "sell", 1, 0.02, 4080.10, -0.22, -0.05, 3), d
        for ticket in (t, 424242):
            r = w.shut(ticket)
            assert not r["ok"] and r["reason"] == "position introuvable", r
        assert len(w.trades("close")) == 1


@test("C2", "partial close: same ticket, stop and ttl kept; an impossible volume is refused by the server; too much = everything")
def c_partial(W):
    with W() as w:
        w.h.alive()
        t = w.must_open("EURUSD", "buy", 1.0, sl=1.158, ttl_min=30)["ticket"]
        before = w.h.positions().iloc[0]
        r = w.shut(t, 0.02)
        assert r["ok"] and r["price"] == 1.16, r
        p = w.h.positions().iloc[0]
        assert (p.ticket, p.volume, p.sl, p.ttl_deadline) == (t, 0.03, 1.158, before.ttl_deadline) and w.pos(t)["volume"] == 0.03, p
        r = w.shut(t, 0.005)
        assert not r["ok"] and r["reason"] == "refuse par le serveur : 10014 invalid volume" and w.pos(t)["volume"] == 0.03, r
        r = w.shut(t, 5.0)
        assert r["ok"] and not w.robot(), r
        assert [d["volume"] for d in w.state()["deals"] if d["entry"] == 1] == [0.02, 0.03]


@test("C3", "close_all: every position of the robot, on every market; positions opened by hand or by another robot are never touched")
def c_closeall(W):
    with W() as w:
        w.h.alive()
        hand = w.pos(w.outside("XAUUSD.r", "buy", 0.01))
        other = w.pos(w.outside("BTCUSD", "sell", 0.01, sl=101000.0, magic=777))
        six(w)
        r = w.close_all()
        assert r["ok"] and not w.robot() and w.h.positions().empty and len(w.trades("close")) == 6, r
        w.untouched(hand)
        w.untouched(other)
        assert w.close_all()["ok"]                                              # nothing to close: still ok


@test("C4", "close_all answers ok=False when a position could not be closed", xfail="H6")
def c_closeall_fail(W):
    with W() as w:
        w.h.alive()
        w.must_open("XAUUSD", "buy", 0.02, sl=4075.23)
        w.set(retcode_close=10018)                                              # market closed
        r = w.close_all()
        assert len(w.robot()) == 1
        assert not r["ok"], f"the position is still open at the broker but the answer is ok={r['ok']}, reason={r['reason']!r}"


# ====================================================================== 5. silent brain
@test("S1", "silent brain: opens refused, stops left in place (and still executed by the broker), ttl enforced; resumes when the brain is back")
def s_silent(W):
    with W(inputs={"InpBrainTimeoutSec": 4}) as w:
        w.h.alive()
        a = w.must_open("XAUUSD", "buy", 0.02, sl=4075.23, ttl_min=30)["ticket"]
        b = w.must_open("EURUSD", "buy", 0.05, sl=1.158)["ticket"]
        n = len(w.trades())
        time.sleep(5.2)                                                         # the brain says nothing for more than 4 s
        w.wait(lambda: w.h.account()["blocked"] == "cerveau muet", 8, "blocked=cerveau muet")
        r = w.open("USDJPY", "buy", 0.05, sl=154.654)
        assert not r["ok"] and r["reason"] == "cerveau muet", r
        assert "Cerveau : MUET" in (w.mock / "comment.txt").read_text()
        assert (w.pos(a)["sl"], w.pos(b)["sl"]) == (4075.23, 1.158) and len(w.trades()) == n      # nothing touched
        w.set({"price.EURUSD.r": "1.15790,1.15792"})                            # the broker executes the stop on its own
        w.wait(lambda: [p["ticket"] for p in w.robot()] == [a], 3, "the broker to execute the stop")
        w.advance(31 * 60)                                                      # and the hands still enforce the deadline
        w.wait(lambda: not w.robot(), 3, "the ttl close while the brain is silent")
        assert w.h.account()["blocked"] == "cerveau muet"
        w.h.alive()
        assert w.must_open("USDJPY", "buy", 0.05, sl=154.654)["ok"]
        assert "Cerveau : connecte" in (w.mock / "comment.txt").read_text()


@test("S2", "brain never started, or brain_alive.txt unreadable: opens refused")
def s_never(W):
    with W() as w:
        r = w.open("XAUUSD", "buy", 0.02, sl=4075.23)
        assert not r["ok"] and r["reason"] == "cerveau muet", r
        for text in ("", "garbage\r\n", "time_gmt=abc\r\n", f"time_gmt={int(time.time()) - 181}\r\n"):
            (w.dir / "brain_alive.txt").write_bytes(text.encode())
            r = w.open("XAUUSD", "buy", 0.02, sl=4075.23)
            assert not r["ok"] and r["reason"] == "cerveau muet", (text, r)
        assert not w.trades()
        w.h.alive()
        assert w.must_open("XAUUSD", "buy", 0.02, sl=4075.23)["ok"]


# ====================================================================== 6. daily loss
def lose(w, bid):
    """a position by hand, two of the robot, then gold gaps down through its stop to `bid`"""
    w.h.alive()
    hand = w.pos(w.outside("USDJPY.r", "buy", 0.01))
    a = w.must_open("XAUUSD", "buy", 0.02, sl=4075.23)["ticket"]
    b = w.must_open("EURUSD", "buy", 0.05, sl=1.158)["ticket"]
    assert w.h.account()["blocked"] == ""
    w.set({"price.XAUUSD.r": f"{bid},{bid + 0.13}"})
    return hand, a, b


@test("D1", "daily loss limit: everything of the robot closed, opens blocked until the next server day, also after a restart; the hand position is not touched")
def d_daily(W):
    with W() as w:
        hand, a, b = lose(w, 4040.00)                                           # -69.40 EUR on gold: more than 6 % of 1000
        w.wait(lambda: w.h.account()["blocked"] == "perte max du jour atteinte", 3, "the daily lock")
        w.wait(lambda: not w.robot(), 3, "the robot's positions to be closed")
        w.tick(2)
        why = {d["position"]: d["reason"] for d in w.state()["deals"] if d["entry"] == 1}
        assert why == {a: 4, b: 3}, why                                         # gold by its stop (broker), the euro by the hands
        w.untouched(hand)
        assert w.h.positions().empty and w.log("NOTIFY") == ["Robot Claude : Perte max du jour atteinte : tout est ferme, reprise demain."]
        r = w.open("XAUUSD", "buy", 0.01, sl=4035.13)
        assert not r["ok"] and r["reason"] == "perte max du jour atteinte", r
        w.stop()
        w.start()                                                               # same day, terminal reopened
        w.h.alive()
        w.tick(3)
        a2 = w.h.account()
        assert a2["blocked"] == "perte max du jour atteinte" and a2["day_start_balance"] == 1000.0, a2
        assert not w.open("XAUUSD", "buy", 0.01, sl=4035.13)["ok"]
        w.at("2026-11-12 23:59:50")
        assert w.h.account()["blocked"] == "perte max du jour atteinte"
        w.at("2026-11-13 00:00:05")                                             # the next server day
        w.h.alive()
        w.wait(lambda: w.h.account()["blocked"] == "", 8, "the lock to clear on the next server day")
        a3 = w.h.account()
        assert a3["day_start_balance"] == a3["balance"] == w.state()["balance"] and a3["balance"] < 940, a3
        assert w.must_open("XAUUSD", "buy", 0.01, sl=4035.13)["volume"] == 0.01
        w.untouched(hand)


@test("D2", "daily loss limit: still locked after a CRASH of the terminal", xfail="H2")
def d_crash(W):
    with W() as w:
        lose(w, 4040.00)
        w.wait(lambda: w.h.account()["blocked"] == "perte max du jour atteinte", 3, "the daily lock")
        w.kill()
        w.start()
        w.h.alive()
        w.tick(3)
        a = w.h.account()
        assert a["blocked"] == "perte max du jour atteinte", f"after the crash blocked={a['blocked']!r}, day_start_balance={a['day_start_balance']}: a new daily allowance"


@test("D3", "InpResetLocks=true lifts the daily lock (as its description says)", xfail="H9")
def d_reset(W):
    with W() as w:
        lose(w, 4040.00)
        w.wait(lambda: w.h.account()["blocked"] == "perte max du jour atteinte", 3, "the daily lock")
        w.stop()
        w.start(inputs={"InpResetLocks": "true"})
        w.h.alive()
        w.tick(3)
        a = w.h.account()
        assert a["blocked"] == "", f"blocked={a['blocked']!r} right after the reset: the lock comes back at once (day_start_balance is still {a['day_start_balance']})"


# ====================================================================== 7. kill switch
@test("K1", "kill switch at -50 % of the starting capital: everything closed, permanent across days and restarts; InpResetLocks clears it")
def k_kill(W):
    with W() as w:
        hand, a, b = lose(w, 3780.00)                                           # -517.90 EUR on gold
        w.wait(lambda: w.h.account()["blocked"] == "arret definitif (-50 %)", 3, "the kill switch")
        w.wait(lambda: not w.robot(), 3, "the robot's positions to be closed")
        w.tick(2)
        w.untouched(hand)
        n = w.log("NOTIFY")
        assert len(n) == 2 and n[0].startswith("Robot Claude : ARRET DEFINITIF : fonds ") and n[0].endswith("capital de depart 1000.00. Tout est ferme."), n
        bal = w.state()["balance"]
        assert 470 < bal < 490 and w.h.account()["start_balance"] == 1000.0, bal
        r = w.open("XAUUSD", "buy", 0.01, sl=3775.13)
        assert not r["ok"] and r["reason"] == "arret definitif (-50 %)", r
        w.at("2026-11-13 00:00:05")                                             # next day: the daily lock goes, not the kill
        w.h.alive()
        w.tick(3)
        assert w.h.account()["blocked"] == "arret definitif (-50 %)"
        w.stop()
        w.start()                                                               # terminal reopened
        w.h.alive()
        w.tick(3)
        assert w.h.account()["blocked"] == "arret definitif (-50 %)" and not w.open("XAUUSD", "buy", 0.01, sl=3775.13)["ok"]
        w.stop()
        w.start(inputs={"InpResetLocks": "true"})
        w.h.alive()
        w.wait(lambda: w.h.account()["blocked"] == "", 8, "InpResetLocks to clear the kill switch")
        assert w.h.account()["start_balance"] == bal                            # the new starting capital is what is left
        assert w.must_open("XAUUSD", "buy", 0.5, sl=3775.13)["volume"] == 0.01   # cap = 1 % of 481 EUR
        w.stop()
        w.start(inputs={})                                                      # InpResetLocks back to false
        w.h.alive()
        w.tick(3)
        assert w.h.account()["blocked"] == "" and w.h.account()["start_balance"] == bal
        assert len(w.trades()) == 4 and w.log("NOTIFY") == n                    # 2 opens, 1 forced close, 1 open after the reset


@test("K2", "kill switch: still on after a CRASH of the terminal", xfail="H2")
def k_crash(W):
    with W() as w:
        lose(w, 3780.00)
        w.wait(lambda: w.h.account()["blocked"] == "arret definitif (-50 %)", 3, "the kill switch")
        w.kill()
        w.start()
        w.h.alive()
        w.tick(3)
        a = w.h.account()
        assert a["blocked"].startswith("arret definitif"), f"after the crash blocked={a['blocked']!r} and start_balance={a['start_balance']}: the stop is forgotten and -50 % now counts from what is left"


@test("K3", "InpStartBalance set by hand (1000): what InpResetLocks does to the kill switch")
def k_startbalance(W):
    with W(inputs={"InpStartBalance": 1000}) as w:
        lose(w, 3780.00)
        w.wait(lambda: w.h.account()["blocked"] == "arret definitif (-50 %)", 3, "the kill switch")
        w.at("2026-11-13 00:00:05")
        w.stop()
        w.start(inputs={"InpStartBalance": 1000, "InpResetLocks": "true"})
        w.h.alive()
        w.tick(3)
        a = w.h.account()
        assert a["blocked"] in ("", "arret definitif (-50 %)"), a
        return (f"after the reset blocked={a['blocked']!r}, start_balance={a['start_balance']}: with InpStartBalance > 0 the stop comes back at once "
                "as long as the funds are under half of InpStartBalance (InpStartBalance must be lowered too)")


@test("K4", "terminal restarted before it is connected (IF the account then reads 0, not verified on a real terminal): no false kill, no false daily lock", xfail="H13")
def k_notconnected(W):
    with W() as w:
        w.h.alive()
        w.stop()                                                                # a first normal session: starting capital 1000 saved
        w.set(connected=0)
        w.start()
        w.tick(3)
        w.set(connected=None)
        w.h.alive()
        w.tick(3)
        w.wait(lambda: w.h.account()["balance"] == 1000.0, 8, "the account to be back")
        a = w.h.account()
        assert a["blocked"] == "", f"blocked={a['blocked']!r} with the account intact (balance {a['balance']}): {w.log('NOTIFY')}"
    with W(connected=0) as w:                                                   # the very first launch, not connected yet
        w.tick(2)
        w.set(connected=None)
        w.tick(3)
        w.wait(lambda: w.h.account()["balance"] == 1000.0, 8, "the account to be back")
        a = w.h.account()
        assert a["start_balance"] == 1000.0 and a["day_start_balance"] == 1000.0, f"start_balance={a['start_balance']}, day_start_balance={a['day_start_balance']}: the kill switch and the daily limit are switched off"


# ====================================================================== 8. Friday
@test("F1", "Friday 23:50 server time: everything of the robot closed, opens blocked all week-end, back on Monday 00:00; hand position not touched")
def f_friday(W):
    with W(server="2026-11-13 23:48:00") as w:
        w.h.alive()
        hand = w.pos(w.outside("USDJPY.r", "buy", 0.01))
        six(w)
        assert w.h.account()["blocked"] == "" and len(w.robot()) == 6
        w.at("2026-11-13 23:49:57")
        w.tick(3)
        assert len(w.robot()) == 6
        w.wait(lambda: not w.robot(), 6, "everything to be closed at 23:50")
        assert w.now() >= ts("2026-11-13 23:50:00") and len(w.trades("close")) == 6
        w.untouched(hand)
        for when in ("2026-11-13 23:50:10", "2026-11-14 12:00:00", "2026-11-15 23:59:40"):
            w.at(when)
            w.h.alive()
            assert w.h.account()["blocked"] == "fermeture du week-end", when
            r = w.open("BTCUSD", "buy", 0.01, sl=99512.0)
            assert not r["ok"] and r["reason"] == "fermeture du week-end", (when, r)
        w.at("2026-11-16 00:00:05")
        w.h.alive()
        w.wait(lambda: w.h.account()["blocked"] == "", 8, "the week-end block to end on Monday")
        assert w.must_open("XAUUSD", "buy", 0.02, sl=4075.23)["ok"]
        w.untouched(hand)
    with W(server="2026-11-13 23:55:00", inputs={"InpFridayClose": 0}) as w:   # 0 = disabled
        w.h.alive()
        assert w.must_open("XAUUSD", "buy", 0.02, sl=4075.23)["ok"]
        w.at("2026-11-14 12:00:00")
        w.tick(3)
        assert len(w.robot()) == 1 and w.h.account()["blocked"] == ""


@test("F2", "Friday close when a market is already closed: the hands insist every 10 s and close as soon as the broker accepts")
def f_retry(W):
    with W(server="2026-11-13 23:48:00") as w:
        w.h.alive()
        w.must_open("XAUUSD", "buy", 0.02, sl=4075.23)
        w.set(retcode_close=10018)
        w.at("2026-11-13 23:50:01")
        w.wait(lambda: len(w.trades("close")) == 1, 3, "the first attempt")
        w.tick(5)
        assert len(w.trades("close")) == 1 and len(w.robot()) == 1             # not hammering the server
        assert any("fermeture refusee (blocage)" in p and "10018 market closed" in p for p in w.log("PRINT")), w.log("PRINT")[-1]
        w.advance(11)
        w.wait(lambda: len(w.trades("close")) == 2, 3, "the second attempt 10 s later")
        w.set(retcode_close=None)
        w.advance(11)
        w.wait(lambda: not w.robot(), 3, "the close once the broker accepts")


# ====================================================================== 9. robustness
@test("R1", "empty command file, command without action, unknown action: answered ok=0, the hands go on")
def r_empty(W):
    with W() as w:
        for cid, text in (("a1", ""), ("a2", "\r\n\r\n"), ("a3", cmd(symbol="XAUUSD", side="buy", volume="0.05", sl="4075.23")),
                          ("a4", cmd(action="buy", **XAU)), ("a5", "action\r\n=open\r\n"), ("a6", "\xff\xfe\x00garbage\x00")):
            r = w.raw(cid, text)
            assert r["ok"] == "0" and r["reason"] == "action inconnue" and r["id"] == cid, (cid, r)
            assert (w.dir / "done" / f"{cid}.txt").exists() and not (w.dir / "cmd" / f"{cid}.txt").exists()
        assert not w.trades() and w.h.ping()


@test("R2", "half-written command file: never more than the risk cap, never without a stop")
def r_half(W):
    with W() as w:
        w.h.alive()
        full = cmd(action="open", symbol="XAUUSD", side="buy", volume="0.5000", sl="4075.23", tp="0.0", ttl_min=30, tag="half", expire=w.now() + 60)
        notes = []
        for i, cut in enumerate(("action=op", "action=open\r\nsymbol=XAUUSD\r\nside=buy\r\nvolume=0.50", "sl=40", "sl=4075.2", "sl=4075.23\r\n", "ttl_min=3")):
            r = w.raw(f"h{i}", full[:full.index(cut) + len(cut)])
            for p in w.robot():
                assert p["sl"] > 0 and (p["price_open"] - p["sl"]) * 100 * 0.8625 * p["volume"] <= 10.0, p
                if w.h.positions().iloc[0].ttl_deadline != p["time"] + 1800:
                    notes.append(f"cut after {cut!r}: executed, ttl {int(w.h.positions().iloc[0].ttl_deadline - p['time']) // 60 if w.h.positions().iloc[0].ttl_deadline else 'none'} instead of 30 min")
                assert w.shut(p["ticket"])["ok"]
            assert r["ok"] in ("0", "1")
        return "; ".join(notes) + " (pont.py writes its orders in one go, so the hands never see such a file from it)"


@test("R3", "duplicate id: what the hands do with an order whose id was already executed")
def r_dup(W):
    with W() as w:
        w.h.alive()
        text = cmd(action="open", expire=w.now() + 60, **XAU)
        r1 = w.raw("dup", text)
        (w.dir / "res" / "dup.txt").unlink()
        r2 = w.raw("dup", text)
        assert r1["ok"] == "1" and r2["ok"] in ("0", "1") and w.h.ping()
        return (f"the same id sent twice was executed {len(w.robot())} time(s) (tickets {r1.get('ticket')}, {r2.get('ticket')}); "
                "pont.py never reuses an id (milliseconds + counter)")


@test("R4", "orders left in cmd/ while the terminal was closed: 'expire' is honoured, the others are executed late, in the order of their ids")
def r_stale(W):
    with W() as w:
        w.h.alive()
        w.stop()
        now = w.now()
        for cid, text in (("s1", cmd(action="open", expire=now - 1, **XAU)), ("s2", cmd(action="open", expire=now + 90, **XAU)),
                          ("s3", cmd(action="open", symbol="EURUSD", side="buy", volume="0.05", sl="1.158")), ("s4", cmd(action="ping"))):
            (w.dir / "cmd" / f"{cid}.txt").write_bytes(text.encode())
        r = w.h.send("ping", timeout=1.0)                                       # pont gives up and removes ITS order
        assert r["reason"] == "pas de réponse des mains" and len(list((w.dir / "cmd").glob("*.txt"))) == 4
        time.sleep(2.0)
        w.h.alive()
        w.start()
        w.wait(lambda: all((w.dir / "res" / f"s{i}.txt").exists() for i in (1, 2, 3, 4)), 5, "the answers")
        w.tick(2)
        r = {i: w.h._kv(f"res/s{i}.txt") for i in (1, 2, 3, 4)}
        assert r[1]["ok"] == "0" and r[1]["reason"] == "ordre perime", r[1]
        assert r[2]["ok"] == "1" and r[3]["ok"] == "1" and r[4]["pong"] == "1", r
        assert int(r[2]["ticket"]) < int(r[3]["ticket"]) and len(w.robot()) == 2
        return ("an 'open' without 'expire' left in cmd/ is executed when the hands come back, however late (pont.open always "
                "sets expire = +20 s; close / modify / close_all carry no expiry and are executed late too)")


@test("R5", "very long tag: cut to MetaTrader's comment size, the csv files still parse")
def r_longtag(W):
    with W() as w:
        w.h.alive()
        r = w.raw("a1", cmd(action="open", tag="x" * 300 + " end", expire=w.now() + 60, **XAU))
        assert r["ok"] == "1", r
        p = w.h.positions().iloc[0]
        assert p.comment == "CM " + "x" * 24 and w.robot()[0]["comment"] == p.comment and len(p.comment) == 27, p.comment
        assert w.h.deals().iloc[0].comment == p.comment
        r = w.must_open("EURUSD", "buy", 0.05, sl=1.158, tag="t" * 50)          # pont cuts at 20
        assert w.pos(r["ticket"])["comment"] == "CM " + "t" * 20


@test("R6", "a tag containing a comma does not break positions.csv / deals.csv for the brain", xfail="H7")
def r_comma(W):
    with W() as w:
        w.h.alive()
        r = w.must_open("XAUUSD", "buy", 0.02, sl=4075.23, tag="pivot,v2")
        try:
            p, d = w.h.positions(), w.h.deals()
            ok = len(p) == 1 and p.ticket.iloc[0] == r["ticket"] and len(d) == 1 and d.position.iloc[0] == r["ticket"]
            what = f"columns shifted: positions().ticket = {p.ticket.iloc[0] if len(p) else None!r}, deals().position = {d.position.iloc[0] if len(d) else None!r}"
        except Exception as e:
            ok, what = False, f"{type(e).__name__}: {str(e).strip()[:90]}"
        assert ok, what


@test("R7", "LF instead of CRLF in a command file")
def r_lf(W):
    out = []
    for env in ({}, {"MOCK_CRLF_ONLY": "1"}):
        with W(env=env) as w:
            w.h.alive()
            assert w.h.ping()                                                   # pont's own CRLF files work in both cases
            r = w.raw("a1", cmd(action="open", expire=w.now() + 60, **XAU).replace("\r\n", "\n"))
            if not env:
                assert r["ok"] == "1" and len(w.robot()) == 1, r
            else:
                assert r["ok"] == "0" and not w.robot(), r
            out.append(f"ok={r['ok']}" + (f" ({r['reason']})" if r["reason"] else ""))
    return (f"if FileReadString ends lines at LF too: {out[0]}; if it only ends them at CRLF, as the documentation says: {out[1]}. "
            "pont.py writes CRLF, which works either way")


@test("R8", "garbage in sl / volume: refused without anything sent to the broker; an absurdly large volume is cut to the cap")
def r_garbage(W):
    with W() as w:
        w.h.alive()
        for i, sl in enumerate(("abc", "", "-5", "1e999", "0x10", "--4075")):
            r = w.raw(f"s{i}", cmd(action="open", symbol="XAUUSD", side="buy", volume="0.05", sl=sl))
            assert r["ok"] == "0" and r["reason"], (sl, r)
        msgs = set()
        for i, vol in enumerate(("abc", "", "-1", "0", "0.004", "-1e999")):
            r = w.raw(f"v{i}", cmd(action="open", symbol="XAUUSD", side="buy", volume=vol, sl="4075.23"))
            assert r["ok"] == "0", (vol, r)
            msgs.add(r["reason"])
        assert not w.trades() and not w.robot(), w.trades()
        for i, vol in enumerate(("123456789", "0.029999")):
            r = w.raw(f"b{i}", cmd(action="open", symbol="XAUUSD", side="buy", volume=vol, sl="4075.23"))
            assert r["ok"] == "1" and float(r["volume"]) == 0.02, (vol, r)
            assert w.shut(int(r["ticket"]))["ok"]
        return f"a volume of 0 / below the minimum lot / unreadable is refused with: {sorted(msgs)}"


@test("R9", "the answer files: every key pont.py reads, for open / modify / close / close_all / ping / a refusal")
def r_res(W):
    with W() as w:
        w.h.alive()
        r = w.must_open("XAUUSD", "buy", 0.5, sl=4075.23, tp=4100.0, ttl_min=5, tag="r9")
        assert set(r) == {"id", "action", "ok", "reason", "ticket", "price", "volume", "sl", "risk_money", "server_time"}, sorted(r)
        assert r["ok"] is True and r["reason"] == "" and r["action"] == "open" and isinstance(r["ticket"], int), r
        assert (r["price"], r["volume"], r["sl"], r["risk_money"]) == (4080.23, 0.02, 4075.23, 8.62) and abs(int(r["server_time"]) - w.now()) <= 3, r
        assert re.fullmatch(r"\d{13}_\d{4}", r["id"]) and (w.dir / "done" / f"{r['id']}.txt").exists()
        m = w.modify(r["ticket"], sl=4076.0, tp=4099.0)
        assert set(m) == {"id", "action", "ok", "reason", "sl", "tp", "server_time"} and (m["ok"], m["sl"], m["tp"], m["action"]) == (True, 4076.0, 4099.0, "modify"), m
        c = w.shut(r["ticket"])
        assert set(c) == {"id", "action", "ok", "reason", "price", "server_time"} and (c["ok"], c["price"], c["action"]) == (True, 4080.10, "close"), c
        a = w.close_all()
        assert set(a) == {"id", "action", "ok", "reason", "server_time"} and a["ok"] is True and a["action"] == "close_all", a
        p = w.h.send("ping")
        assert p["ok"] is True and p["pong"] == "1", p
        f = w.shut(r["ticket"])
        assert set(f) == {"id", "action", "ok", "reason", "server_time"} and f["ok"] is False and f["reason"] == "position introuvable", f
        assert not list((w.dir / "cmd").glob("*")) and len(list((w.dir / "res").glob("*.txt"))) == 6 == len(list((w.dir / "done").glob("*.txt")))


@test("R10", "an order is executed once even if its file cannot be moved to done/ (folder removed)", xfail="H8")
def r_done(W):
    with W() as w:
        w.h.alive()
        shutil.rmtree(w.dir / "done")
        r = w.h.open("XAUUSD", "buy", 0.02, sl=4075.23)
        time.sleep(1.0)
        n, left = len(w.robot()), len(list((w.dir / "cmd").glob("*.txt")))
        assert r["ok"] and n == 1 and left == 0, f"one order sent, {n} positions opened; the order file is still in cmd/ ({left}) and is run again on every pass"


@test("R11", "150 orders at once: all answered (100 per pass), in the order of their ids")
def r_flood(W):
    with W() as w:
        w.set(hold=1)
        for i in range(150):
            w.raw(f"p{i:03d}", cmd(action="ping"), wait=False)
        w.set(hold=None)
        w.wait(lambda: len(list((w.dir / "res").glob("p*.txt"))) == 150, 5, "150 answers")
        assert not list((w.dir / "cmd").glob("*.txt")) and w.h.ping()


@test("R12", "the server clock steps back one hour (winter time, clock correction): account.txt is still refreshed", xfail="H11")
def r_back(W):
    with W() as w:
        w.h.alive()
        w.tick(2)
        w.set(server_offset=w.ctl["server_offset"] - 3600)
        time.sleep(8.0)
        age = time.time() - w.h.account()["ea_time_gmt"]
        assert age <= 6.5, f"account.txt is {age:.0f} s old and will not be rewritten for an hour: pont.ea_alive() turns false after 30 s, forced closes are not retried"


# ====================================================================== runner
def run_one(binary, keep, item):
    tid, title, xfail, fn = item
    worlds = []

    @contextlib.contextmanager
    def W(**kw):
        w = World(binary, **kw)
        worlds.append(w)
        try:
            yield w
        finally:
            w.close(keep=keep)

    t0 = time.time()
    try:
        note = fn(W)
        status, detail = "PASS", note or ""
    except AssertionError as e:
        tb = traceback.extract_tb(e.__traceback__)
        line = next((f.lineno for f in reversed(tb) if f.filename == __file__), 0)
        status, detail = "FAIL", f"line {line}: {str(e).strip() or tb[-1].line}"
    except Exception as e:                                                      # noqa: BLE001
        status, detail = "FAIL", f"{type(e).__name__}: {e}"
    finally:
        for w in worlds:
            w.close(keep=keep)
    if xfail:
        status = {"FAIL": "XFAIL", "PASS": "XPASS"}[status]
    where = f"  [kept: {', '.join(str(w.root) for w in worlds)}]" if keep else ""
    return tid, title, xfail, status, detail, time.time() - t0, where


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mq5", default=str(LIVE / "mql5" / "ClaudeMains.mq5"))
    ap.add_argument("-k", default="", help="only the tests whose id or title contains this text (several: a,b)")
    ap.add_argument("-j", type=int, default=6, help="tests run at the same time")
    ap.add_argument("--keep", action="store_true", help="keep the temporary directories")
    ap.add_argument("--lag", action="store_true", help="every fake terminal shows its positions late (see mock_mains.h: lag=1)")
    a = ap.parse_args()
    global LAG
    LAG = a.lag
    work = Path(tempfile.mkdtemp(prefix="mains_build_"))
    t0 = time.time()
    binary = build(Path(a.mq5), work)
    print(f"built {Path(a.mq5).name} with mock_mains.h in {time.time() - t0:.0f} s")
    todo = [t for t in TESTS if any(part.strip().lower() in (t[0] + " " + t[1]).lower() for part in a.k.split(","))]
    with concurrent.futures.ThreadPoolExecutor(max(1, a.j)) as ex:
        results = list(ex.map(lambda it: run_one(binary, a.keep, it), todo))
    count = {"PASS": 0, "FAIL": 0, "XFAIL": 0, "XPASS": 0}
    for tid, title, xfail, status, detail, sec, where in results:
        count[status] += 1
        mark = f" [{xfail}]" if xfail else ""
        print(f"{status:5s} {tid:5s}{mark} {title}  ({sec:.1f} s)" + (f"\n        -> {detail}" if detail else "") + where)
    if not a.keep:
        shutil.rmtree(work, ignore_errors=True)
    print(f"\n{len(results)} tests: {count['PASS']} pass, {count['FAIL']} FAIL, {count['XFAIL']} expected failures (known defects of the EA, "
          f"see the finding ids), {count['XPASS']} expected failures that now pass")
    for fid in sorted({r[2] for r in results if r[2]}, key=lambda x: int(x[1:])):
        print(f"  {fid}: {FINDINGS[fid]}")
    print("ClaudeMains : " + ("every test that should pass passes" if count["FAIL"] == 0 else "FAILURES"))
    return 1 if count["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
