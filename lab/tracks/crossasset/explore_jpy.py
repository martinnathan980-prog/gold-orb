"""Descriptive IS-only: is the USDJPY -> gold lead concentrated in tails / years / sessions?
Signal (past only): z = USDJPY L-bar log return / rolling sd of L-bar returns (20 trading days,
shifted).  Gold forward return over k bars after the decision bar close, in bp; sign-adjusted
so that positive = gold moved OPPOSITE to USDJPY (i.e. with the yen).  Also the same for the USD
basket and the DAX (risk-on/off) for comparison."""
import warnings

import numpy as np
import pandas as pd

from common import gl, load_bars

warnings.filterwarnings("ignore")


def run(rule, L, k, per_day, zs=(1.5, 2.0, 2.5, 3.0)):
    g = load_bars("xauusd", rule)
    g = g[g.index < pd.Timestamp("2022-01-01", tz="UTC")]
    lg = np.log(g["c"])
    out = {}
    for s in ["usdjpy", "eurusd", "deuidxeur"]:
        b = load_bars(s, rule)
        lp = np.log(b["c"]).reindex(g.index)
        r = (lp - lp.shift(L)) * 1e4
        sd = r.rolling(per_day * 20, min_periods=per_day * 5).std().shift(1)
        z = r / sd
        fut = (lg.shift(-k) - lg) * 1e4
        sign = -1 if s in ("usdjpy",) else 1   # gold expected to follow yen / follow EUR / ? DAX
        rows = []
        for zz in zs:
            for side, m in (("x_up", z > zz), ("x_dn", z < -zz)):
                f = fut[m]
                # thin overlapping signals: keep first bar of each cluster (>= k bars apart)
                idx = np.flatnonzero(m.to_numpy())
                keep, last = [], -10 ** 9
                for i in idx:
                    if i - last >= k:
                        keep.append(i)
                        last = i
                f2 = fut.iloc[keep].dropna()
                rows.append({"z": zz, "side": side, "n_raw": int(m.sum()), "n_thin": len(f2),
                             "mean_fut_bp": round(f2.mean(), 1), "med": round(f2.median(), 1),
                             "t": round(f2.mean() / (f2.std() / np.sqrt(len(f2))), 2) if len(f2) > 2 else np.nan,
                             "yrs_with_sign": "".join("+" if v > 0 else "-" for v in
                                                      (f2.groupby(f2.index.year).mean() * (sign if side == "x_up" else -sign)))})
        print(f"\n== {rule} L={L} k={k} predictor={s} (sign convention: gold expected {'opposite' if sign < 0 else 'same'} to predictor)")
        print(pd.DataFrame(rows).to_string(index=False))
        # session split for the strongest z
        lt = gl.local(g.index, gl.LDN).hour
        m = (z.abs() > 2.0)
        sess = pd.cut(lt, [-1, 6, 12, 16, 23], labels=["asia(0-6)", "ldn(7-12)", "ldn/ny(13-16)", "ny(17-23)"])
        f = fut * np.sign(z) * sign
        tab = f[m].groupby(sess[m.to_numpy()]).agg(["count", "mean"]).round(1)
        print("   |z|>2 sign-adjusted fut (raw, overlapping) by London hour:", tab.to_dict())


if __name__ == "__main__":
    run("15min", 4, 8, 96)
    run("1h", 1, 8, 24)
    run("1h", 4, 8, 24)
    run("1h", 4, 24, 24)
