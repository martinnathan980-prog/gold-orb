"""How often does the EA's tick alert (TickTrigger: live ask >= br_hi / bid <= br_lo) fire in a
window where the M1 paper engine (MT5-like: ask-high = bid-high + ONE spread per bar) never
opens a position?  Exact Dukascopy ask-high stands in for the live ticks.  Same loop as
lab/live/ea_twin.run(mt5like=True), plus window bookkeeping."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, LAB); sys.path.insert(0, os.path.join(LAB, "live")); sys.path.insert(0, os.path.join(LAB, "audit"))
import numpy as np, pandas as pd
import goldlab as gl
import ea_twin

start, end = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("2019-01-01", "2026-12-31")
m1 = gl.load_m1("xauusd", start=start, end=end)
n, atr_n, k_stop, k_trail, days = 60, 14, 2.0, 2.0, 5
t4, h4, l4, c4 = ea_twin.four_hour_bars(m1, True)
atr4 = ea_twin.wilder(h4, l4, c4, atr_n)
hi_roll = pd.Series(h4).rolling(n).max().to_numpy(); lo_roll = pd.Series(l4).rolling(n).min().to_numpy()
b4 = {t: i for i, t in enumerate(t4)}
idx = m1.index
bo, bh, bl, bc = (m1[k].to_numpy() for k in ("bo", "bh", "bl", "bc"))
ah_true = m1.ah.to_numpy()
spr = (m1.ao - m1.bo).to_numpy(); ao, ah, al = bo + spr, bh + spr, bl + spr
bucket = idx.floor("4h")
side = 0; br = None; last = None
win = []          # one row per armed window: alert fired? paper filled?
for i in range(len(idx)):
    t = idx[i]; bk = bucket[i]
    if bk != last:
        if br is not None: win.append(br)
        last = bk; br = None
        if side == 0:
            j = b4.get(bk, None)
            jp = (j - 1) if j is not None else np.searchsorted(t4.values, bk.to_datetime64()) - 1
            if jp >= n + atr_n and np.isfinite(atr4[jp]):
                br = dict(dec=bk, hi=hi_roll[jp], lo=lo_roll[jp], atr=atr4[jp], exp=bk + pd.Timedelta(hours=4),
                          alert=0, alert_t=None, paper=0)
    if side != 0:
        first = i == fill_i
        if not first and t >= dl: side = 0
        elif side > 0:
            if bl[i] <= stop: side = 0
            else: best = max(best, bh[i]); stop = max(stop, best - trail)
        else:
            if ah[i] >= stop: side = 0
            else: best = min(best, al[i]); stop = min(stop, best + trail)
        continue
    if br is None or t >= br["exp"] or br["paper"]:
        continue
    if br["alert"] == 0 and (ah_true[i] >= br["hi"] or bl[i] <= br["lo"]):     # TickTrigger (live ticks)
        br["alert"] = 1 if ah_true[i] >= br["hi"] else -1; br["alert_t"] = t
    hu, hd = ah[i] >= br["hi"], bl[i] <= br["lo"]                              # paper engine at M1 close
    if not (hu or hd): continue
    s = (-1 if bc[i] >= bo[i] else 1) if (hu and hd) else (1 if hu else -1)
    fill = max(br["hi"], ao[i]) if s > 0 else min(br["lo"], bo[i])
    side, fill_i = s, i; trail = k_trail * br["atr"]; stop = fill - s * k_stop * br["atr"]; best = fill
    dl = ea_twin.deadline_utc(br["dec"], days); br["paper"] = s
    if s > 0:
        if bl[i] <= stop: side = 0
        else: best = max(best, bh[i]); stop = max(stop, best - trail)
    else:
        if ah[i] >= stop: side = 0
        else: best = min(best, al[i]); stop = min(stop, best + trail)
w = pd.DataFrame(win)
alerts = w[w.alert != 0]
phantom = alerts[alerts.paper == 0]
wrong = alerts[(alerts.paper != 0) & (alerts.paper != alerts.alert)]
print(f"{start}..{end}: armed windows {len(w)} | tick alerts {len(alerts)} | paper entries {(w.paper != 0).sum()}")
print(f"alerts with NO paper position in that window: {len(phantom)} ({len(phantom)/max(len(alerts),1):.1%}) "
      f"| buy-side {int((phantom.alert > 0).sum())} sell-side {int((phantom.alert < 0).sum())}")
print(f"alerts whose side differs from the paper side: {len(wrong)}")
print(phantom[["dec", "alert_t", "alert", "hi", "lo"]].head(10).to_string())
