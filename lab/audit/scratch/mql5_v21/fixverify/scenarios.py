"""Scratch (fix-verification lens, EA v2.10): quantify two control-flow scenarios with the twin's
paper engine (lab/live/ea_twin.py, exact Dukascopy bid/ask, full history).

A) Paper entry on the DECISION bar (first M1 bar of the bucket). In v2.10 CatchUp runs
   Decide -> PlacePendings (current tick = after that bar closed) and THEN ProcessBar -> PaperEnter ->
   DeletePendings (F5).  If at decision time the price is back inside the channel, the stop orders are
   placed and deleted in the same call: mode 2 gets no trade.  v2.0 kept the same-side stop alive.
   Price at decision time ~ open of the next M1 bar (ask for the buy test, bid for the sell test).

B) Mode-1 binder: a same-side paper re-entry within 6 h of the previous paper entry.  The trader opens
   after the tick alert, i.e. before the paper ENTRY is recorded at the M1 close, so BindManualPosition
   still sees the previous trade (sig, entry_utc, atr, deadline) and binds to it.
"""
import os
import sys

import numpy as np
import pandas as pd

LAB = "/home/user/gold-orb/lab"
sys.path.insert(0, LAB)
sys.path.insert(0, os.path.join(LAB, "live"))
sys.path.insert(0, os.path.join(LAB, "audit"))
import goldlab as gl  # noqa: E402
from ea_twin import four_hour_bars, wilder, deadline_utc  # noqa: E402


def run(m1, n=60, atr_n=14, k_stop=2.0, k_trail=2.0, days=5):
    t4, h4, l4, c4 = four_hour_bars(m1, False)
    atr4 = wilder(h4, l4, c4, atr_n)
    hi_roll = pd.Series(h4).rolling(n).max().to_numpy()
    lo_roll = pd.Series(l4).rolling(n).min().to_numpy()
    b4_index = {t: i for i, t in enumerate(t4)}
    idx = m1.index
    bo, bh, bl, bc = (m1[k].to_numpy() for k in ("bo", "bh", "bl", "bc"))
    ao, ah, al = (m1[k].to_numpy() for k in ("ao", "ah", "al"))
    bucket = idx.floor("4h")
    trades = []
    side = 0
    br = None
    last_bucket = None
    for i in range(len(idx)):
        t = idx[i]
        bk = bucket[i]
        if bk != last_bucket:
            last_bucket = bk
            br = None
            tc = (idx[i - 1] + pd.Timedelta(minutes=1)) if i > 0 else bk
            if side == 0:
                j = b4_index.get(bk, None)
                jprev = (j - 1) if j is not None else np.searchsorted(t4.values, bk.to_datetime64()) - 1
                if jprev >= n + atr_n and np.isfinite(atr4[jprev]):
                    br = dict(hi=hi_roll[jprev], lo=lo_roll[jprev], atr=atr4[jprev], dec=tc,
                              exp=bk + pd.Timedelta(hours=4), dec_i=i)
        if side != 0:
            if t >= dl:
                trades.append(dict(et=et, side=side, fill=fill, ex=bo[i] if side > 0 else ao[i], init=init,
                                   xt=t, why="time", **meta)); side = 0
            elif side > 0:
                if bl[i] <= stop:
                    trades.append(dict(et=et, side=side, fill=fill, ex=min(stop, bo[i]), init=init,
                                       xt=t + pd.Timedelta(minutes=1), why="stop", **meta)); side = 0
                else:
                    best = max(best, bh[i]); stop = max(stop, best - trail)
            else:
                if ah[i] >= stop:
                    trades.append(dict(et=et, side=side, fill=fill, ex=max(stop, ao[i]), init=init,
                                       xt=t + pd.Timedelta(minutes=1), why="stop", **meta)); side = 0
                else:
                    best = min(best, al[i]); stop = min(stop, best + trail)
            continue
        if br is None or t >= br["exp"]:
            continue
        hu, hd = ah[i] >= br["hi"], bl[i] <= br["lo"]
        if not (hu or hd):
            continue
        s = (-1 if bc[i] >= bo[i] else 1) if (hu and hd) else (1 if hu else -1)
        fill = max(br["hi"], ao[i]) if s > 0 else min(br["lo"], bo[i])
        side, et = s, t
        trail = k_trail * br["atr"]
        init = stop = fill - s * k_stop * br["atr"]
        best = fill
        dl = deadline_utc(br["dec"], days)
        # scenario A bookkeeping
        first_bar = (i == br["dec_i"])
        nxt = i + 1 if i + 1 < len(idx) else i
        if s > 0:
            beyond_at_decision = ao[nxt] >= br["hi"]
        else:
            beyond_at_decision = bo[nxt] <= br["lo"]
        # v2.0: same-side stop left alive for the rest of the window -> filled later?
        late_fill = False
        k = i + 1
        while k < len(idx) and idx[k] < br["exp"]:
            if (s > 0 and ah[k] >= br["hi"]) or (s < 0 and bl[k] <= br["lo"]):
                late_fill = True
                break
            k += 1
        meta = dict(first_bar=first_bar, beyond=beyond_at_decision, late_fill=late_fill, atr=br["atr"], dl=dl)
        br = None
        if s > 0:
            if bl[i] <= stop:
                trades.append(dict(et=et, side=s, fill=fill, ex=stop, init=init, xt=t + pd.Timedelta(minutes=1),
                                   why="stop", **meta)); side = 0
            else:
                best = max(best, bh[i]); stop = max(stop, best - trail)
        else:
            if ah[i] >= stop:
                trades.append(dict(et=et, side=s, fill=fill, ex=stop, init=init, xt=t + pd.Timedelta(minutes=1),
                                   why="stop", **meta)); side = 0
            else:
                best = min(best, al[i]); stop = min(stop, best + trail)
    tr = pd.DataFrame(trades)
    tr["R"] = tr.side * (tr.ex - tr.fill) / (tr.fill - tr.init).abs()
    return tr


def main():
    m1 = gl.load_m1("xauusd", start="2013-01-01", end="2026-12-31")
    tr = run(m1)
    tr = tr[tr.et < m1.index[-1] - pd.Timedelta(days=8)].reset_index(drop=True)
    print(f"trades {len(tr)}  sumR {tr.R.sum():+.1f}")
    fb = tr[tr.first_bar]
    miss = fb[~fb.beyond]
    print(f"A) entries on the decision bar: {len(fb)} ({len(fb)/len(tr):.1%}), sumR {fb.R.sum():+.2f}")
    print(f"   of which price back inside at decision time (v2.10: stops placed then deleted -> no real trade): "
          f"{len(miss)}, sumR {miss.R.sum():+.2f}")
    print(f"   of those, v2.0 same-side stop would have filled later in the window: {int(miss.late_fill.sum())}")
    print(miss[["et", "side", "R", "why", "late_fill"]].to_string())
    # B) same-side re-entry within 6 h of the previous entry
    prev = tr.shift(1)
    gap = (tr.et - prev.et)
    b = tr[(tr.side == prev.side) & (gap <= pd.Timedelta(hours=6))].copy()
    b["gap_h"] = gap[b.index].dt.total_seconds() / 3600
    b["prev_dl"] = prev.dl[b.index]
    b["dl_early_h"] = (b.dl - b.prev_dl).dt.total_seconds() / 3600
    b["atr_ratio"] = b.atr / prev.atr[b.index]
    print(f"B) same-side re-entries within 6 h of the previous paper entry: {len(b)} of {len(tr)}")
    print(b[["et", "side", "gap_h", "dl_early_h", "atr_ratio", "R"]].to_string())
    # How long are paper trades? (the binder may bind after the paper exit)
    hold = (tr.xt - tr.et).dt.total_seconds() / 3600
    print(f"paper trades shorter than 6 h: {(hold < 6).sum()}")


if __name__ == "__main__":
    main()
