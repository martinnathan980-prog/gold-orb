"""Independent, deliberately naive re-implementation of the squeeze-breakout rule from its plain-language
description (pandas group-by + explicit Python loops, no code shared with strategy.py), compared order by
order with strategy.make_orders on an in-sample slice.  Orders only, no P&L."""
import json, os, sys
import numpy as np, pandas as pd
from research import RES, r2, S, gl
from pandas.tseries.offsets import BDay

P = dict(family="donch", tf=60, n=24, atr_n=14, stop_atr=2.0, trail_atr=2.0, max_days=5, squeeze=0.7, squeeze_ref=480)


def naive_orders(m1, n=24, atr_n=14, k_stop=2.0, k_trail=2.0, squeeze=0.7, ref_n=480, max_days=5):
    hour = m1.index.floor("h")
    g = m1.groupby(hour)
    bars = pd.DataFrame({
        "h": (g["bh"].max() + g["ah"].max()) / 2, "l": (g["bl"].min() + g["al"].min()) / 2,
        "c": (g["bc"].last() + g["ac"].last()) / 2,
        "first_pos": g["bo"].apply(lambda s: m1.index.get_loc(s.index[0])),
        "last_pos": g["bo"].apply(lambda s: m1.index.get_loc(s.index[-1])),
    })
    H, L, C = bars.h.to_numpy(), bars.l.to_numpy(), bars.c.to_numpy()
    first, last = bars.first_pos.to_numpy(), bars.last_pos.to_numpy()
    nb = len(bars)
    atr = np.full(nb, np.nan)
    for i in range(1, nb):
        tr = max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1]))
        atr[i] = tr if i == 1 else atr[i - 1] + (tr - atr[i - 1]) / atr_n
    width = np.full(nb, np.nan)
    hi = np.full(nb, np.nan)
    lo = np.full(nb, np.nan)
    for i in range(n - 1, nb):
        hi[i] = H[i - n + 1:i + 1].max()
        lo[i] = L[i - n + 1:i + 1].min()
        width[i] = hi[i] - lo[i]
    ah, bl, bo, bc = (m1[c].to_numpy() for c in ("ah", "bl", "bo", "bc"))
    rows = []
    for i in range(n - 1, nb - 1):
        past = width[max(0, i - ref_n):i]
        past = past[~np.isnan(past)]
        if len(past) < ref_n // 2 or np.isnan(atr[i]):
            continue
        if not width[i] <= squeeze * np.median(past):
            continue
        a, b = first[i + 1], last[i + 1]            # the bracket lives during the next bar
        hit = None
        for j in range(a, b + 1):
            up, dn = ah[j] >= hi[i], bl[j] <= lo[i]
            if up and dn:
                hit = (j, -1 if bc[j] >= bo[j] else 1)
            elif up:
                hit = (j, 1)
            elif dn:
                hit = (j, -1)
            if hit:
                break
        if hit is None:
            continue
        # time stop: decision time + 5 NY trading days - 5 minutes (last bar before a closure)
        dec = m1.index[last[i]] + pd.Timedelta(minutes=1)
        ny = dec.tz_convert(gl.NY).tz_localize(None)
        x = ((ny + pd.Timedelta(hours=7)) + BDay(max_days) - pd.Timedelta(hours=7)).tz_localize(gl.NY).tz_convert("UTC") - pd.Timedelta(minutes=5)
        xi = int(gl.exit_index(m1, pd.DatetimeIndex([x]))[0])
        if xi <= hit[0]:
            continue
        rows.append({"entry_i": int(a), "side": hit[1], "level": hi[i] if hit[1] > 0 else lo[i], "expiry_i": int(b),
                     "stop_dist": k_stop * atr[i], "trail": k_trail * atr[i], "exit_i": xi, "trig_i": hit[0]})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    out = {}
    for a, b in (("2015-01-01", "2016-04-01"), ("2019-10-01", "2021-01-01")):
        m1 = r2.load("xauusd", start=a, end=b)
        o1 = naive_orders(m1)
        o2 = S.make_orders(m1, **P)
        res = {"slice": f"{a}..{b}", "n_naive": int(len(o1)), "n_strategy": int(len(o2))}
        if len(o1) == len(o2):
            for col in ("entry_i", "side", "level", "expiry_i", "stop_dist", "trail", "exit_i", "trig_i"):
                x, y = o1[col].to_numpy(float), o2[col].to_numpy(float)
                res["max_abs_diff_" + col] = float(np.max(np.abs(x - y))) if len(x) else 0.0
        out[res["slice"]] = res
        print(json.dumps(res), flush=True)
    json.dump(out, open(os.path.join(RES, "independent_check.json"), "w"), indent=1)
