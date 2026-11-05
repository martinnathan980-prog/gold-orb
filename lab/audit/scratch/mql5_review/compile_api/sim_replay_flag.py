"""Model the EA's CatchUp() replay flag (GoldOrb_Donchian4H.mq5 line 662) on real M1 bar times.

Live EA: CatchUp runs on every tick/timer; it only does work when a NEW M1 bar has formed
(cur = iTime(M1,0)).  It then processes the closed bars in (last_m1, cur-60] and sets
    g_replay = (cur - g.last_m1 > 5*60)
In steady state each new bar j processes bar j-1, with last_m1 = t[j-2].
We count, per year:
  * replay batches  -> each sends Notify("rattrapage ... termine")   (lines 685-690)
  * 4h decisions taken while g_replay is true -> no LEVELS push, no OffsetOK, no PlacePendings
    (lines 503, 524-533)
and compare with the proposed fix g_replay = (n > 5).
Usage: python3 lab/audit/scratch/mql5_review/compile_api/sim_replay_flag.py
"""
import os
import sys

import numpy as np
import pandas as pd

LAB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, LAB)
import goldlab as gl  # noqa: E402

m1 = gl.load_m1("xauusd", start="2024-01-01", end="2026-01-01")
t = ((m1.index - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(seconds=1)).to_numpy().astype(np.int64)  # s UTC
bucket = (t // 14400) * 14400

rows = []
last_m1 = t[0]
last_bucket = bucket[0]
for j in range(1, len(t)):
    cur = t[j]                                  # first tick of the new bar j
    todo = [k for k in (j - 1,) if t[k] > last_m1]
    if not todo:
        continue
    n = len(todo)
    replay_ea = (cur - last_m1) > 300
    replay_fix = n > 5
    k = todo[0]
    decided = bucket[k] != last_bucket
    if decided:
        last_bucket = bucket[k]
    rows.append((t[k], replay_ea, replay_fix, decided))
    last_m1 = t[k]

df = pd.DataFrame(rows, columns=["bar", "replay_ea", "replay_fix", "decision"])
df["year"] = pd.to_datetime(df.bar, unit="s", utc=True).dt.year
ny = pd.to_datetime(df.bar, unit="s", utc=True).dt.tz_convert("America/New_York")
df["ny_hm"] = ny.dt.strftime("%a %H:%M")
out = df.groupby("year").agg(
    batches=("bar", "size"),
    replay_batches_EA=("replay_ea", "sum"),
    replay_batches_fix=("replay_fix", "sum"),
    decisions=("decision", "sum"),
)
out["decisions_in_replay_EA"] = df[df.decision & df.replay_ea].groupby("year").size()
out["decisions_in_replay_fix"] = df[df.decision & df.replay_fix].groupby("year").size()
print(out.fillna(0).astype(int).to_string())
print("\nNY wall-clock of the bars processed in replay (EA rule), most common:")
print(df[df.replay_ea].ny_hm.value_counts().head(8).to_string())
print("\nNY wall-clock of the 4h decisions taken in replay (EA rule), most common:")
print(df[df.replay_ea & df.decision].ny_hm.value_counts().head(5).to_string())

# --- which twin trades have their ENTRY / EXIT bar processed in replay (silent: Print only) ---
sys.path.insert(0, os.path.join(LAB, "live"))
sys.path.insert(0, os.path.join(LAB, "audit"))
import ea_twin  # noqa: E402

m1w = gl.load_m1("xauusd", start="2023-08-01", end="2026-01-01")
tw = ea_twin.run(m1w, mt5like=True)
tw = tw[tw.entry_time >= pd.Timestamp("2024-01-01", tz="UTC")]
rep = set(df.bar[df.replay_ea].tolist())
sec = lambda s: ((s - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(seconds=1)).astype(np.int64)
ent_bar = sec(tw.entry_time)
ex_bar = sec(tw.exit_time) - np.where(tw.reason == "time", 0, 60)
tw = tw.assign(silent_entry=ent_bar.isin(rep).to_numpy(), silent_exit=pd.Series(ex_bar).isin(rep).to_numpy())
print(f"\ntwin trades 2024-2025: {len(tw)} | ENTRY bar processed in replay (no push): {int(tw.silent_entry.sum())}"
      f" | EXIT bar processed in replay (no push): {int(tw.silent_exit.sum())}")
print(tw[tw.silent_entry | tw.silent_exit][["entry_time", "side", "exit_time", "reason", "R"]].head(12).to_string())

# trades whose 4h window was armed by a decision taken in replay -> mode 2 never placed real orders
dec_rep = set(((df.bar[df.decision & df.replay_ea] // 14400) * 14400).tolist())
ent_bucket = (ent_bar // 14400) * 14400
tw = tw.assign(window_armed_in_replay=ent_bucket.isin(dec_rep).to_numpy())
k = tw.window_armed_in_replay
print(f"twin trades whose window's Decide ran in replay (no PlacePendings in mode 2, no LEVELS push): "
      f"{int(k.sum())} / {len(tw)}  | their sum R {tw.R[k].sum():+.2f} (all trades {tw.R.sum():+.2f})")

# trades entered on the FIRST M1 bar of their 4h window: Decide/PlacePendings only run when that bar
# has closed (next bar's first tick), so real stop orders / LEVELS push arrive after the paper entry
first_bar = []
for eb in ent_bar:
    b = (eb // 14400) * 14400
    i = np.searchsorted(t, b)            # first bar of the bucket in the data
    first_bar.append(i < len(t) and t[i] == eb)
first_bar = np.array(first_bar)
print(f"twin trades entered on the window's first M1 bar (before Decide ran in the EA): "
      f"{int(first_bar.sum())} / {len(tw)} | their sum R {tw.R[first_bar].sum():+.2f}")
