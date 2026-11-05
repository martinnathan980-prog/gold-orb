"""Python twin of the MQL5 EA v2 paper engine (GoldOrb_Donchian4H.mq5), line-for-line logic:
bar-by-bar processing of CLOSED M1 bars, decision at the first bar of each new 4h UTC bucket
when flat, channel/ATR from completed 4h mid bars, first-touch rule, fills at the worse of
level/open, stop then trailing after the bar, time exit at the bar open, DeadlineUTC rule.

Purpose: prove that the EA's algorithm reproduces the lab backtest (lab/tracks/trend,
donch4h_stop) before anyone runs the MQL5 code, and measure the effect of MT5-style data
approximations (bid bars + one spread value per bar, 4h mid bars from M5 bid + spread/2).

Usage:  python3 lab/live/ea_twin.py [--mt5like] [--start 2013-01-01] [--end 2026-12-31]
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

LAB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, LAB)
sys.path.insert(0, os.path.join(LAB, "audit"))
import goldlab as gl  # noqa: E402
from goldlab.sim import Costs  # noqa: E402
from audit import load_strategy  # noqa: E402

NY = "America/New_York"


def deadline_utc(decision_utc, days=5):
    """EA DeadlineUTC: NY wall clock + 7h, + N weekdays, - 7h, - 5 min; weekend / 17-18h NY
    break -> 16:59 NY (Friday for the weekend)."""
    ny = decision_utc.tz_convert(NY).tz_localize(None)
    td = ny + pd.Timedelta(hours=7)
    added = 0
    while added < days:
        td += pd.Timedelta(days=1)
        if td.dayofweek <= 4:
            added += 1
    ny = td - pd.Timedelta(hours=7) - pd.Timedelta(minutes=5)
    mins = ny.hour * 60 + ny.minute
    weekend = ny.dayofweek == 5 or (ny.dayofweek == 6 and mins < 18 * 60) or (ny.dayofweek == 4 and mins >= 17 * 60)
    brk = 17 * 60 <= mins < 18 * 60
    if weekend:
        while ny.dayofweek != 4:
            ny -= pd.Timedelta(days=1)
    if weekend or brk:
        ny = ny.normalize() + pd.Timedelta(hours=16, minutes=59)
    return ny.tz_localize(NY, nonexistent="shift_forward", ambiguous=False).tz_convert("UTC")


def four_hour_bars(m1, mt5like):
    if not mt5like:
        b = gl.bars(m1, "4h")
        return b.index, b.h.to_numpy(), b.l.to_numpy(), b.c.to_numpy()
    # MT5-like: M5 bid bars, mid = bid + spread/2 with ONE spread value per M5 bar (at its open)
    m5 = m1.resample("5min", label="left", closed="left").agg(
        {"bo": "first", "bh": "max", "bl": "min", "bc": "last", "ao": "first"}).dropna()
    hs = (m5.ao - m5.bo) / 2
    mid = pd.DataFrame({"h": m5.bh + hs, "l": m5.bl + hs, "c": m5.bc + hs}, index=m5.index)
    b = mid.resample("4h", label="left", closed="left").agg({"h": "max", "l": "min", "c": "last"}).dropna()
    return b.index, b.h.to_numpy(), b.l.to_numpy(), b.c.to_numpy()


def wilder(h, l, c, n=14):
    pc = np.r_[np.nan, c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    out = np.full(len(tr), np.nan)
    a = np.nan
    for i in range(1, len(tr)):
        a = tr[i] if i == 1 else a + (tr[i] - a) / n
        out[i] = a
    return out


def run(m1, mt5like=False, n=60, atr_n=14, k_stop=2.0, k_trail=2.0, days=5):
    t4, h4, l4, c4 = four_hour_bars(m1, mt5like)
    atr4 = wilder(h4, l4, c4, atr_n)
    hi_roll = pd.Series(h4).rolling(n).max().to_numpy()
    lo_roll = pd.Series(l4).rolling(n).min().to_numpy()
    b4_index = {t: i for i, t in enumerate(t4)}
    idx = m1.index
    bo, bh, bl, bc = (m1[k].to_numpy() for k in ("bo", "bh", "bl", "bc"))
    if mt5like:     # one spread per M1 bar, measured at the open (MT5 MqlRates.spread)
        spr = (m1.ao - m1.bo).to_numpy()
        ao, ah, al = bo + spr, bh + spr, bl + spr
    else:
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
            tc = (idx[i - 1] + pd.Timedelta(minutes=1)) if i > 0 else bk   # = lab t_close of the completed 4h bar
            if side == 0:
                j = b4_index.get(bk, None)
                jprev = (j - 1) if j is not None else np.searchsorted(t4.values, bk.to_datetime64()) - 1
                if jprev >= n + atr_n and np.isfinite(atr4[jprev]):
                    br = dict(hi=hi_roll[jprev], lo=lo_roll[jprev], atr=atr4[jprev], dec=tc, exp=bk + pd.Timedelta(hours=4))
        if side != 0:
            first = i == fill_i
            if not first and t >= dl:
                ex = bo[i] if side > 0 else ao[i]
                trades.append((et, side, fill, ex, init, t, "time"))
                side = 0
            elif side > 0:
                if bl[i] <= stop:
                    ex = stop if first else min(stop, bo[i])
                    trades.append((et, side, fill, ex, init, t + pd.Timedelta(minutes=1), "trail" if stop > init else "stop"))
                    side = 0
                else:
                    best = max(best, bh[i])
                    stop = max(stop, best - trail)
            else:
                if ah[i] >= stop:
                    ex = stop if first else max(stop, ao[i])
                    trades.append((et, side, fill, ex, init, t + pd.Timedelta(minutes=1), "trail" if stop < init else "stop"))
                    side = 0
                else:
                    best = min(best, al[i])
                    stop = min(stop, best + trail)
            continue
        if br is None or t >= br["exp"]:
            continue
        hu, hd = ah[i] >= br["hi"], bl[i] <= br["lo"]
        if not (hu or hd):
            continue
        s = (-1 if bc[i] >= bo[i] else 1) if (hu and hd) else (1 if hu else -1)
        fill = max(br["hi"], ao[i]) if s > 0 else min(br["lo"], bo[i])
        side, fill_i, et = s, i, t
        trail = k_trail * br["atr"]
        init = stop = fill - s * k_stop * br["atr"]
        best = fill
        dl = deadline_utc(br["dec"], days)
        br = None
        # same-bar stop check, then trailing from the fill bar's extremes
        if s > 0:
            if bl[i] <= stop:
                trades.append((et, s, fill, stop, init, t + pd.Timedelta(minutes=1), "stop"))
                side = 0
            else:
                best = max(best, bh[i]); stop = max(stop, best - trail)
        else:
            if ah[i] >= stop:
                trades.append((et, s, fill, stop, init, t + pd.Timedelta(minutes=1), "stop"))
                side = 0
            else:
                best = min(best, al[i]); stop = min(stop, best + trail)
    tr = pd.DataFrame(trades, columns=["entry_time", "side", "entry", "exit", "init_stop", "exit_time", "reason"])
    tr["R"] = tr.side * (tr.exit - tr.entry) / (tr.entry - tr.init_stop).abs()
    return tr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mt5like", action="store_true")
    ap.add_argument("--start", default="2013-01-01")
    ap.add_argument("--end", default="2026-12-31")
    a = ap.parse_args()
    m1 = gl.load_m1("xauusd", start=a.start, end=a.end)
    twin = run(m1, mt5like=a.mt5like)
    mod = load_strategy("trend")
    lab = gl.simulate(m1, mod.make_orders(m1, **mod.FINALISTS["donch4h_stop"]),
                      costs=Costs(commission=0, slip_bps=0, swap_long=0, swap_short=0))
    lab = lab[lab.entry_time < m1.index[-1] - pd.Timedelta(days=8)]
    twin = twin[twin.entry_time < m1.index[-1] - pd.Timedelta(days=8)]
    k = ["entry_time", "side"]
    j = lab.merge(twin, on=k, how="outer", suffixes=("_lab", "_twin"), indicator=True)
    both = j[j._merge == "both"]
    print(f"lab trades {len(lab)} | twin trades {len(twin)} | identical entry (time+side) {len(both)} "
          f"({len(both)/len(lab):.1%})")
    if len(both):
        d = (both.R_lab - both.R_twin).abs()
        same_exit = (both.exit_time_lab == both.exit_time_twin).mean()
        print(f"matched: same exit time {same_exit:.1%} | mean |dR| {d.mean():.4f} | max |dR| {d.max():.3f}")
    print(f"sum R  lab {lab.R.sum():+.1f} | twin {twin.R.sum():+.1f}")
    g = lambda r: r[r > 0].sum() / -r[r < 0].sum()
    print(f"PF (zero costs)  lab {g(lab.R):.3f} | twin {g(twin.R):.3f}")
    only = j[j._merge != "both"]
    if len(only):
        print("unmatched (first 12):")
        print(only[["entry_time", "side", "_merge", "R_lab", "R_twin", "reason_lab", "reason_twin"]].head(12).to_string())


if __name__ == "__main__":
    main()
