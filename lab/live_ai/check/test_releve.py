"""Run ReleveFP.mq5 for real (translated to C++, against the working imitation of MT5 in mock_mt5.h) and check
what it writes: the per-minute bid/ask rows against an independent recomputation of the same fake ticks, the
specification files, and that the Python reader (releve.lire_m1) parses them. ReleveFP 1.10 (check_110): the smallest
spread of each minute (sp_min) against the recomputation, the terminal's M1 bars of the robot's four markets (r1_<BASE>.csv)
against the imitation's bars and fini.txt's barres=, their days newest first, fini.txt's 1.10 keys, and the r1 days of
InpRateSymbols against what the robot's replay needs (its depth of 120 / 60 days, a demo of four weeks, a week). The demo
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
    the imitation's bars and fini.txt's barres=, the days newest first, the r1 days the robot's replay needs, fini.txt's keys"""
    assert fini.get("version") == "1.10", fini.get("version")
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
    sonde()
    print("ReleveFP : tous les tests passent")


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
