"""Run ReleveFP.mq5 for real (translated to C++, against the working imitation of MT5 in mock_mt5.h) and check
what it writes: the per-minute bid/ask rows against an independent recomputation of the same fake ticks, the
specification files, and that the Python reader (releve.lire_m1) parses them.

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
                         "n": g.bid.size(), "sp_mean": g.sp.mean(), "sp_max": g.sp.max()})


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
    # the loop stops after 6 empty days in a row: 9 symbols x (11 days with history + weekends + 6 empty) calls at most
    assert calls <= 9 * 20, calls
    # the Python reader
    import releve
    df = releve.lire_m1(d, "BTCUSD")
    assert len(df) == len(exp) and str(df.index.tz) == "UTC"
    assert df.index[-1] == pd.Timestamp(int(exp.index[-1]) - 7200, unit="s", tz="UTC")     # November: server = UTC+2
    print(f"minute rows: {len(got)} identical to the recomputation; {calls} tick requests; reader ok "
          f"({df.index[0]} -> {df.index[-1]})")
    print("ReleveFP : tous les tests passent")


if __name__ == "__main__":
    main()
