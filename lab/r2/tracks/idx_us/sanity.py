"""Independent recomputation (plain pandas, no shared helper code) of the signals behind a few IS trades."""
import sys; sys.path.insert(0, "/home/user/gold-orb/lab")
import numpy as np, pandas as pd
from goldlab import r2
m1 = r2.load("us100", end="2022-01-01")
mid = (m1.bc + m1.ac) / 2
ny = m1.index.tz_convert("America/New_York")
s = pd.DataFrame({"mid_c": mid.values, "mid_o": ((m1.bo + m1.ao) / 2).values, "bl": m1.bl.values, "ah": m1.ah.values}, index=ny)
def px_at(day, hhmm):
    """mid known at day hh:mm = close of the last bar starting before that time"""
    t = pd.Timestamp(f"{day} {hhmm}", tz="America/New_York")
    x = s.loc[:t - pd.Timedelta(seconds=1)]
    return float(x.mid_c.iloc[-1]), x.index[-1]
def open_at(day):
    t = pd.Timestamp(f"{day} 09:30", tz="America/New_York")
    x = s.loc[t:t + pd.Timedelta(minutes=1, seconds=59)]
    return float(x.mid_o.iloc[0])
tr = pd.read_csv("/home/user/gold-orb/lab/results/r2/idx_us/trades_is_noise30_us100.csv", parse_dates=["entry_time", "exit_time"])
tr["ny"] = tr.entry_time.dt.tz_convert("America/New_York")
days = sorted(set(d.date() for d in s.index))
import datetime as dt
print("--- noise30: recompute band at the entry check for 4 trades")
for k in (100, 700, 1200, 1600):
    r = tr.iloc[k]
    day = r.ny.date(); hhmm = r.ny.strftime("%H:%M")
    # previous 14 regular sessions (weekday sessions present in data, excluding the listed holidays/half-days by hand is skipped: use strategy grid dates)
    sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/idx_us")
    import idxus_lib as cm
    g = cm.grid(m1)
    dl = list(g["dates"]); i = dl.index(day)
    prev = dl[i - 14:i]
    am = []
    for d in prev:
        try:
            p, _ = px_at(d, hhmm); o = open_at(d); am.append(abs(p / o - 1))
        except Exception as e:
            am.append(np.nan)
    sigma = np.nanmean(am)
    o = open_at(day); pc, tpc = px_at(dl[i - 1], "16:00")
    p, tp = px_at(day, hhmm)
    ub = max(o, pc) * (1 + sigma); lb = min(o, pc) * (1 - sigma)
    print(f"  {day} {hhmm} side={r.side:+d} open={o:.2f} prevclose={pc:.2f} sigma={sigma*1e4:.1f}bp UB={ub:.2f} LB={lb:.2f} price@check={p:.2f} (bar {tp.strftime('%H:%M')}) "
          f"-> {'LONG' if p > ub else 'SHORT' if p < lb else 'none'} | trade entry={r.entry:.2f} stop={r.stop:.2f} (centre {max(o, pc) if r.side > 0 else min(o, pc):.2f}) exit {r.exit_time.tz_convert('America/New_York').strftime('%H:%M')} reason={r.reason} R={r.R:.2f}")
tr = pd.read_csv("/home/user/gold-orb/lab/results/r2/idx_us/trades_is_ocm4_us100.csv", parse_dates=["entry_time", "exit_time"])
tr["ny"] = tr.entry_time.dt.tz_convert("America/New_York")
print("--- ocm4: recompute candle, size filter and ATR stop for 4 trades")
# daily ATR14 (simple mean of TR over 14 complete NY-17:00 trading days with >= 600 bars)
td = (ny + pd.Timedelta(hours=7)).tz_localize(None).normalize()
dm = pd.DataFrame({"h": ((m1.bh + m1.ah) / 2).values, "l": ((m1.bl + m1.al) / 2).values, "c": mid.values}).groupby(td.values).agg(h=("h", "max"), l=("l", "min"), c=("c", "last"), n=("c", "size"))
dm = dm[dm.n >= 600]
pcx = dm.c.shift(1)
trng = np.maximum(dm.h - dm.l, np.maximum((dm.h - pcx).abs(), (dm.l - pcx).abs()))
atr = trng.rolling(14).mean()
for k in (50, 400, 700, 950):
    r = tr.iloc[k]
    day = r.ny.date()
    o = open_at(day); c, tc = px_at(day, "09:34")
    mv = c / o - 1
    i = dl.index(day)
    prevm = []
    for d in dl[i - 20:i]:
        try:
            prevm.append(abs(px_at(d, "09:34")[0] / open_at(d) - 1))
        except Exception:
            prevm.append(np.nan)
    med = np.nanmedian(prevm)
    a = float(atr[atr.index < pd.Timestamp(day)].iloc[-1])
    print(f"  {day} entry {r.ny.strftime('%H:%M')} side={r.side:+d} open={o:.2f} close@09:34={c:.2f} move={mv*1e4:+.1f}bp median20={med*1e4:.1f}bp -> {'signal' if abs(mv) >= med else 'NO'} {'LONG' if mv > 0 else 'SHORT'} | "
          f"ATR14={a:.1f} 0.3ATR={0.3*a:.2f} trade risk={r.risk:.2f} entry={r.entry:.2f} exit {r.exit_time.tz_convert('America/New_York').strftime('%H:%M')} reason={r.reason} R={r.R:.2f}")
