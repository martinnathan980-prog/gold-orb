"""DeadlineUTC (ported EA) vs lab add_trading_days(bucket,5)-5min for EVERY 4h bucket start
2013-2030 at which the market is open (Sun 18:00 NY .. Fri 17:00 NY, excluding the daily break)."""
import os, sys
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, HERE); sys.path.insert(0, LAB); sys.path.insert(0, os.path.join(LAB, "audit"))
from mql5_time import DeadlineUTC  # noqa: E402
from audit import load_strategy  # noqa: E402
S = load_strategy("trend")
b = pd.date_range("2013-01-01", "2030-12-31", freq="4h", tz="UTC")
ny = b.tz_convert("America/New_York")
open_ = ~((ny.dayofweek == 5) | ((ny.dayofweek == 6) & (ny.hour < 18)) | ((ny.dayofweek == 4) & (ny.hour >= 17)) | (ny.hour == 17))
b = b[open_]
lab = S.add_trading_days(b, 5) - pd.Timedelta(minutes=5)
ea = pd.to_datetime([DeadlineUTC(int(t.timestamp())) for t in b], unit="s", utc=True)
d = lab != ea
print(f"bucket starts checked: {len(b)} | EA != lab: {int(d.sum())} | lab NaT: {int(pd.isna(lab).sum())}")
dl_ny = ea.tz_convert("America/New_York")
inclos = ((dl_ny.dayofweek == 5) | ((dl_ny.dayofweek == 6) & (dl_ny.hour < 18)) | ((dl_ny.dayofweek == 4) & (dl_ny.hour >= 17)) | (dl_ny.hour == 17))
print(f"EA deadlines falling in weekend/daily break (16:59 rule needed): {int(inclos.sum())}")
print("deadline NY clock values:", sorted(set(dl_ny.strftime('%H:%M'))))
