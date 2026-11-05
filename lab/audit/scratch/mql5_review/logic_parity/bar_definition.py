"""Effect of the 4h mid-bar DEFINITION on trades (2013-03 .. 2026-10, warm start, vs lab):
   lab   : h = (max bid-high + max ask-high)/2, l = (min bid-low + min ask-low)/2, c = (bc+ac)/2
   EA    : h = max over M5 of (bid-high + spread/2)  (Build4H lines 318-331)
with exact M1 quotes, and with MT5-like quotes (one spread value per bar, at its open)."""
import os, sys
import numpy as np
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ea_port import compare, lab_trades, run  # noqa: E402
import goldlab as gl  # noqa: E402

m1 = gl.load_m1("xauusd", start="2012-12-01", end="2026-12-31")
lab = lab_trades(m1, "2013-03-01", "2026-10-20")


def b4(df):
    return df.index, df.h.to_numpy(), df.l.to_numpy(), df.c.to_numpy()


R4 = dict(label="left", closed="left")
# exact quotes, EA definition (max of per-M5-bar mids, M5 mid = exact M1 mids aggregated)
mid = pd.DataFrame({"h": (m1.bh + m1.ah) / 2, "l": (m1.bl + m1.al) / 2, "c": (m1.bc + m1.ac) / 2})
ea_def_exact = mid.resample("4h", **R4).agg({"h": "max", "l": "min", "c": "last"}).dropna()
# MT5-like M5: bid OHLC + one spread (at the M5 open)
m5 = m1.resample("5min", **R4).agg({"bo": "first", "bh": "max", "bl": "min", "bc": "last", "ao": "first"}).dropna()
sp = m5.ao - m5.bo
ea_def_mt5 = pd.DataFrame({"h": m5.bh + sp / 2, "l": m5.bl + sp / 2, "c": m5.bc + sp / 2}).resample("4h", **R4).agg(
    {"h": "max", "l": "min", "c": "last"}).dropna()
x = pd.DataFrame({"bh": m5.bh, "ah": m5.bh + sp, "bl": m5.bl, "al": m5.bl + sp, "bc": m5.bc, "ac": m5.bc + sp}).resample(
    "4h", **R4).agg({"bh": "max", "ah": "max", "bl": "min", "al": "min", "bc": "last", "ac": "last"}).dropna()
lab_def_mt5 = pd.DataFrame({"h": (x.bh + x.ah) / 2, "l": (x.bl + x.al) / 2, "c": (x.bc + x.ac) / 2})
labb = gl.bars(m1, "4h")
for name, bars, m1mode in (("exact M1, lab 4h def", b4(labb), False),
                           ("exact M1, EA 4h def (max of mids)", b4(ea_def_exact), False),
                           ("MT5-like M1, lab 4h def on exact quotes", b4(labb), True),
                           ("MT5-like M1 + EA 4h def (= twin --mt5like)", b4(ea_def_mt5), True),
                           ("MT5-like M1 + lab-style 4h def (proposed Build4H)", b4(lab_def_mt5), True)):
    ea = run(m1, "2013-03-01", "2026-10-20", first_run="warm", bars4=bars, m1like=m1mode)
    compare(lab, ea, name)
# proposed fix: exact ask extremes per M1 bar (ticks) but 4h bars still from M5 bid + spread/2
ea = run(m1, "2013-03-01", "2026-10-20", first_run="warm", bars4=b4(ea_def_mt5), m1like=False)
compare(lab, ea, "tick-exact M1 ask + EA 4h def from MT5-like M5 (fix #ticks)")
