"""(1) Clocks() prints the UTC date + Paris TIME only: how often is the Paris calendar day of a
deadline different from the printed UTC date?  (2) How often does the deadline fall inside a
market closure (next bar > 30 min later): the EA (paper + RealTimeExit) then exits at the
first tick AFTER the reopen, the lab (exit_index) on the last bar BEFORE the closure."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, LAB); sys.path.insert(0, os.path.join(LAB, "live")); sys.path.insert(0, os.path.join(LAB, "audit"))
import numpy as np, pandas as pd
import goldlab as gl
import ea_twin

m1 = gl.load_m1("xauusd", start="2013-01-01", end="2026-12-31")
tr = ea_twin.run(m1, mt5like=False)
tr = tr[tr.entry_time < m1.index[-1] - pd.Timedelta(days=8)].reset_index(drop=True)
dec = tr.entry_time.dt.floor("4h")
dl = pd.DatetimeIndex([ea_twin.deadline_utc(d, 5) for d in dec])
paris = dl.tz_convert("Europe/Paris")
diff_day = (paris.date != dl.date)
print(f"trades {len(tr)} | deadline Paris date != printed UTC date: {diff_day.sum()} ({diff_day.mean():.1%})")
print("examples (as Clocks() prints them -> real Paris time):")
for u, p in list(zip(dl[diff_day], paris[diff_day]))[:3]:
    print(f"   '{u:%Y.%m.%d %H:%M} UTC / {p:%H:%M} Paris'  -> really {p:%a %d.%m %H:%M} Paris")
idx = m1.index.values
xi = np.searchsorted(idx, dl.values)
nxt = idx[np.clip(xi, 0, len(idx) - 1)]
inside = (nxt - dl.values) > np.timedelta64(30, "m")
held = (nxt - dl.values)[inside].astype("timedelta64[m]").astype(int)
print(f"deadline inside a closure (EA holds through the reopen gap): {inside.sum()} trades; "
      f"of which still open at the deadline (reason=time): {(inside & (tr.reason == 'time').to_numpy()).sum()}; "
      f"extra holding (min) {sorted(held.tolist())[:10]}")
print(pd.DataFrame({"deadline_utc": dl[inside], "reopen_utc": pd.DatetimeIndex(nxt[inside]).tz_localize('UTC'),
                    "reason": tr.reason[inside].to_numpy()}).head(8).to_string())
