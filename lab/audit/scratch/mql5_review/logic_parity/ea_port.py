"""A more literal Python port of the EA v2 control flow (CatchUp -> Decide -> ProcessBar) than
lab/live/ea_twin.py, to test the items the twin does not model:

  * first-run initialisation (g.last_m1 = cur-60, g.last_bucket_utc = current bucket -> the
    current 4h window is skipped, and the EA starts FLAT whatever the lab position is),
  * deadline reference: EA = bucket start (g.br_decision_utc) vs lab = t_close of the 4h bar
    just completed (= last M1 bar of the previous bucket + 1 min),
  * time-exit rule: EA = first bar >= DeadlineUTC (16:59 NY rule only for weekend/break) vs
    lab exit_index (last bar before any closure > 30 min, else first bar >= xt).

Indicators (4h mid bars, channel, Wilder ATR) are taken from the twin (full history), so this
isolates control-flow effects.  Times are int64 ns (UTC).
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, LAB)
sys.path.insert(0, os.path.join(LAB, "live"))
sys.path.insert(0, os.path.join(LAB, "audit"))
import goldlab as gl  # noqa: E402
from goldlab.sim import Costs  # noqa: E402
from audit import load_strategy  # noqa: E402
from ea_twin import four_hour_bars, wilder  # noqa: E402
from mql5_time import DeadlineUTC  # noqa: E402

NS = 1_000_000_000
MIN = 60 * NS
H4 = 4 * 3600 * NS


def _ts(x):
    t = pd.Timestamp(x)
    return t.tz_localize("UTC") if t.tzinfo is None else t


def run(m1, start, end, mt5like=False, first_run="ea", deadline_ref="bucket", exit_rule="ea",
        n=60, atr_n=14, k_stop=2.0, k_trail=2.0, days=5, warm_days=21, bars4=None, m1like=None):
    t4, h4, l4, c4 = bars4 if bars4 is not None else four_hour_bars(m1, mt5like)
    if m1like is not None:
        mt5like = m1like
    atr4 = wilder(h4, l4, c4, atr_n)
    hi_roll = pd.Series(h4).rolling(n).max().to_numpy()
    lo_roll = pd.Series(l4).rolling(n).min().to_numpy()
    t4v = t4.values.astype("datetime64[ns]").astype(np.int64)
    tv = m1.index.values.astype("datetime64[ns]").astype(np.int64)
    bo, bh, bl, bc = (m1[k].to_numpy() for k in ("bo", "bh", "bl", "bc"))
    if mt5like:
        spr = (m1.ao - m1.bo).to_numpy()
        ao, ah, al = bo + spr, bh + spr, bl + spr
    else:
        ao, ah, al = (m1[k].to_numpy() for k in ("ao", "ah", "al"))
    s0 = int(np.searchsorted(tv, _ts(start).value))
    s1 = min(len(tv), int(np.searchsorted(tv, _ts(end).value + 12 * 86400 * NS)))   # let open trades finish
    if first_run == "warm":           # replay `warm_days` of history flat before the start
        s_beg = int(np.searchsorted(tv, _ts(start).value - warm_days * 86400 * NS))
        last_bucket = None
    else:                             # EA lines 656: skip the bucket of the first bar
        s_beg = s0
        last_bucket = (tv[s0] // H4) * H4
    trades = []
    side = 0
    br = None
    dl = None
    for i in range(s_beg, s1):
        t = tv[i]
        bk = (t // H4) * H4
        if bk != last_bucket:
            last_bucket = bk
            br = None
            if side == 0:
                j = int(np.searchsorted(t4v, bk)) - 1          # last 4h bar strictly before the bucket
                if j >= n + atr_n and np.isfinite(atr4[j]):
                    tc = tv[i - 1] + MIN if i > 0 else bk     # lab t_close of the bar just completed
                    dec = bk if deadline_ref == "bucket" else tc
                    br = dict(hi=hi_roll[j], lo=lo_roll[j], atr=atr4[j], dec=dec, exp=bk + H4)
        if side != 0:
            first = i == fill_i
            if exit_rule == "ea":
                tx = (not first) and t >= dl
            else:                     # lab exit_index: last bar before a closure > 30 min after xt
                t_next = tv[i + 1] if i + 1 < len(tv) else np.iinfo(np.int64).max
                tx = (not first) and (t >= dl or t_next - dl > 30 * MIN)
            if tx:
                trades.append((et, side, fill, bo[i] if side > 0 else ao[i], init, t, "time"))
                side = 0
            elif side > 0:
                if bl[i] <= stop:
                    trades.append((et, side, fill, stop if first else min(stop, bo[i]), init, t + MIN,
                                   "trail" if stop > init else "stop"))
                    side = 0
                else:
                    best = max(best, bh[i]); stop = max(stop, best - trail)
            else:
                if ah[i] >= stop:
                    trades.append((et, side, fill, stop if first else max(stop, ao[i]), init, t + MIN,
                                   "trail" if stop < init else "stop"))
                    side = 0
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
        side, fill_i, et = s, i, t
        trail = k_trail * br["atr"]
        init = stop = fill - s * k_stop * br["atr"]
        best = fill
        if exit_rule == "ea":
            dl = DeadlineUTC(br["dec"] // NS) * NS                         # EA DeadlineUTC (16:59 rules)
        else:                                                              # lab: add_trading_days - 5 min, raw
            dl = _lab_xt(br["dec"])
        br = None
        if s > 0:
            if bl[i] <= stop:
                trades.append((et, s, fill, stop, init, t + MIN, "stop")); side = 0
            else:
                best = max(best, bh[i]); stop = max(stop, best - trail)
        else:
            if ah[i] >= stop:
                trades.append((et, s, fill, stop, init, t + MIN, "stop")); side = 0
            else:
                best = min(best, al[i]); stop = min(stop, best + trail)
    tr = pd.DataFrame(trades, columns=["entry_time", "side", "entry", "exit", "init_stop", "exit_time", "reason"])
    for c in ("entry_time", "exit_time"):
        tr[c] = pd.to_datetime(tr[c], utc=True)
    tr["R"] = tr.side * (tr.exit - tr.entry) / (tr.entry - tr.init_stop).abs()
    return tr[(tr.entry_time >= _ts(start)) & (tr.entry_time < _ts(end))].reset_index(drop=True)


_S = None


def _lab_xt(dec_ns):
    global _S
    if _S is None:
        _S = load_strategy("trend")
    t = pd.DatetimeIndex([pd.Timestamp(dec_ns, tz="UTC")])
    return (_S.add_trading_days(t, 5) - pd.Timedelta(minutes=5))[0].value


def lab_trades(m1, start, end, flat_from=None):
    S = load_strategy("trend")
    o = S.make_orders(m1, **S.FINALISTS["donch4h_stop"])
    if flat_from is not None:      # lab started flat at the EA's first decision (tester-like)
        o = o[m1.index[np.clip(o.entry_i, 0, len(m1) - 1)] >= _ts(flat_from)].reset_index(drop=True)
    t = gl.simulate(m1, o, costs=Costs(commission=0, slip_bps=0, swap_long=0, swap_short=0))
    return t[(t.entry_time >= _ts(start)) & (t.entry_time < _ts(end))].reset_index(drop=True)


def compare(lab, ea, label):
    j = lab.merge(ea, on=["entry_time", "side"], how="outer", suffixes=("_lab", "_ea"), indicator=True)
    both = j[j._merge == "both"]
    same_exit = (both.exit_time_lab == both.exit_time_ea).mean() if len(both) else float("nan")
    print(f"{label:58s} lab {len(lab):4d} ea {len(ea):4d} same entry {len(both):4d} "
          f"({len(both)/max(len(lab),1):6.1%}) same exit {same_exit:6.1%} | sumR lab {lab.R.sum():+6.1f} ea {ea.R.sum():+6.1f}")
    return j[j._merge != "both"]
