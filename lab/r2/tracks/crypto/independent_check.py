"""Independent, slow, bar-by-bar re-implementation of the two finalist rules (pandas + python loops, no code
shared with strategy.py or the engine) on a slice of the IN-SAMPLE period, compared trade by trade with the
engine. Writes results/r2/crypto/independent_check.json."""
import json, sys
import numpy as np, pandas as pd
sys.path.insert(0, "/home/user/gold-orb/lab"); sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/crypto")
import goldlab as gl
from goldlab import r2
import strategy as S
from final_cfg import FINAL

OUT = "/home/user/gold-orb/lab/results/r2/crypto"


def hourly(m1):
    mid = pd.DataFrame({"o": (m1.bo + m1.ao) / 2, "h": (m1.bh + m1.ah) / 2, "l": (m1.bl + m1.al) / 2, "c": (m1.bc + m1.ac) / 2})
    h = mid.resample("1h").agg({"o": "first", "h": "max", "l": "min", "c": "last"}).dropna()
    return h


def signals_brk(h, n=72, atr_n=24):
    out = []
    c = h.c.to_numpy(); hi = h.h.to_numpy(); lo = h.l.to_numpy()
    for i in range(max(n, atr_n), len(h)):
        prev = c[i - n:i]
        side = 1 if c[i] > prev.max() else (-1 if c[i] < prev.min() else 0)
        if side == 0:
            continue
        tr = [max(hi[j] - lo[j], abs(hi[j] - c[j - 1]), abs(lo[j] - c[j - 1])) for j in range(i - atr_n + 1, i + 1)]
        out.append((h.index[i] + pd.Timedelta(hours=1), side, float(np.mean(tr))))
    return out


def signals_sess(h, dec_h=8, look_h=8, atr_n=24):
    out = []
    c = h.c; hi = h.h.to_numpy(); lo = h.l.to_numpy(); cc = c.to_numpy()
    pos = {t: k for k, t in enumerate(h.index)}
    for day in pd.date_range(h.index[0].normalize(), h.index[-1].normalize(), freq="D"):
        dec = day + pd.Timedelta(hours=dec_h)
        b1 = dec - pd.Timedelta(hours=1)               # bar that ends at the decision
        b0 = b1 - pd.Timedelta(hours=look_h)           # bar that ended look_h hours earlier
        if b1 not in pos or b0 not in pos or pos[b1] < atr_n:
            continue
        i = pos[b1]
        mv = cc[i] - cc[pos[b0]]
        if mv == 0:
            continue
        tr = [max(hi[j] - lo[j], abs(hi[j] - cc[j - 1]), abs(lo[j] - cc[j - 1])) for j in range(i - atr_n + 1, i + 1)]
        out.append((dec, 1 if mv > 0 else -1, float(np.mean(tr))))
    return out


def trade_sim(m1, sigs, stop_k, hold_h, c, weekday_only=True, max_delay=5):
    idx = m1.index
    bo, bl, ao, ah = (m1[k].to_numpy() for k in ("bo", "bl", "ao", "ah"))
    trades = []
    last_exit_i = -1
    for dec, side, atr in sigs:
        if weekday_only and dec.dayofweek >= 5:
            continue
        i0 = idx.searchsorted(dec)
        if i0 >= len(idx) or (idx[i0] - dec) > pd.Timedelta(minutes=max_delay):
            continue
        if i0 <= last_exit_i:                           # one position at a time
            continue
        xi = idx.searchsorted(dec + pd.Timedelta(hours=hold_h))
        entry = ao[i0] * (1 + c.slip_mkt_bps * 1e-4) if side > 0 else bo[i0] * (1 - c.slip_mkt_bps * 1e-4)
        stop = entry - side * stop_k * atr
        i = i0
        while True:
            if i >= len(idx):
                ex_i, ex_px, why = len(idx) - 1, np.nan, "eod"
                break
            if i >= xi and i > i0:
                ex_px = bo[i] * (1 - c.slip_mkt_bps * 1e-4) if side > 0 else ao[i] * (1 + c.slip_mkt_bps * 1e-4)
                ex_i, why = i, "time"
                break
            if side > 0 and bl[i] <= stop:
                px = stop if i == i0 else min(stop, bo[i])
                ex_i, ex_px, why = i, px * (1 - c.slip_bps * 1e-4), "stop"
                break
            if side < 0 and ah[i] >= stop:
                px = stop if i == i0 else max(stop, ao[i])
                ex_i, ex_px, why = i, px * (1 + c.slip_bps * 1e-4), "stop"
                break
            i += 1
        last_exit_i = ex_i
        trades.append({"entry_time": idx[i0], "side": side, "entry": entry, "exit": ex_px, "reason": why,
                       "exit_i": ex_i, "gross_R": side * (ex_px - entry) / abs(entry - stop)})
    return pd.DataFrame(trades)


if __name__ == "__main__":
    res = {}
    for sym, (a, b) in (("btcusd", ("2020-09-01", "2021-07-01")), ("ethusd", ("2018-01-01", "2018-11-01"))):
        m1 = r2.load(sym, start=a, end=b)
        c = r2.costs(sym)
        h = hourly(m1)
        # drop the last hourly bar if the slice stops before its end
        if h.index[-1] + pd.Timedelta(hours=1) > m1.index[-1] + pd.Timedelta(minutes=1):
            h = h.iloc[:-1]
        for name, p in FINAL.items():
            sigs = signals_brk(h, p["n"]) if p["family"] == "brk" else signals_sess(h, p["dec_h"], p["look_h"])
            mine = trade_sim(m1, sigs, p["stop_atr"], p["hold_h"], c)
            eng = gl.simulate(m1, S.make_orders(m1, **p), sym=sym, costs=c, no_overlap=True)
            eng = eng[eng.reason != "eod"]
            mine = mine[mine.reason != "eod"]
            m = mine.merge(eng[["entry_time", "side", "entry", "exit", "reason", "swap", "risk"]], on="entry_time", how="outer",
                           suffixes=("_mine", "_eng"), indicator=True)
            both = m[m._merge == "both"]
            r = {"slice": f"{a}..{b}", "n_mine": int(len(mine)), "n_engine": int(len(eng)), "matched": int(len(both)),
                 "only_mine": int((m._merge == "left_only").sum()), "only_engine": int((m._merge == "right_only").sum()),
                 "side_equal": bool((both.side_mine == both.side_eng).all()),
                 "max_abs_entry_diff": float((both.entry_mine - both.entry_eng).abs().max()),
                 "max_abs_exit_diff": float((both.exit_mine - both.exit_eng).abs().max()),
                 "reason_equal": bool((both.reason_mine == both.reason_eng).all()),
                 "max_abs_gross_R_diff": float((both.gross_R - both.side_eng * (both.exit_eng - both.entry_eng) / both.risk).abs().max())}
            res[f"{name}:{sym}"] = r
            print(name, sym, r, flush=True)
        r2.free()
    json.dump(res, open(f"{OUT}/independent_check.json", "w"), indent=1)
