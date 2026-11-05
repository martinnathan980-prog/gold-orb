"""Lookahead audit (orders only, no P&L): orders generated on an M1 frame truncated at a cut date
must be identical to those generated on a longer frame, for every order whose decision happens
before the cut (exits are clipped at the frame end, so only entries/levels/stops are compared)."""
import sys
import numpy as np
import pandas as pd
from run import gl
from strategy import make_orders

def check(cfg, cuts, end_long="2022-01-10"):
    full = gl.load_m1("xauusd", end=end_long)
    o_full = make_orders(full, **cfg)
    o_full["t_entry"] = full.index[o_full.entry_i.values]
    res = []
    for cut in cuts:
        part = full[full.index < pd.Timestamp(cut, tz="UTC")]
        o = make_orders(part, **cfg)
        o["t_entry"] = part.index[o.entry_i.values]
        # compare orders entering at least 8 days before the cut (exit decisions fully inside)
        lim = pd.Timestamp(cut, tz="UTC") - pd.Timedelta(days=8)
        a = o[o.t_entry < lim].reset_index(drop=True)
        b = o_full[o_full.t_entry < lim].reset_index(drop=True)
        cols = ["t_entry", "side", "stop", "stop_dist", "target", "exit_i"]
        same = len(a) == len(b) and all(
            np.allclose(a[c].astype(float).fillna(-1), b[c].astype(float).fillna(-1)) if c not in ("t_entry",) else (a[c] == b[c]).all()
            for c in cols)
        res.append((cut, len(a), len(b), same))
    return res

if __name__ == "__main__":
    cfgs = [dict(family="soup", tf="D", n=5, min_age=1, mode="close_inside", stop_buf=1.0, max_bars=3),
            dict(family="rsi", tf="D", rsi_n=2, lo=10, hi=90, trend_n=200, exit_ma=5, max_bars=5, stop_atr=3.0),
            dict(family="sess", ref="ldn", check="11:00", k=0.75, target_frac=0.5, stop_mode="extreme", stop_buf=0.25, exit_at="16:30"),
            dict(family="soup", tf="1h", n=120, min_age=12, mode="close_inside", stop_buf=0.25, max_bars=72)]
    for c in cfgs:
        print(c["family"], c.get("tf", ""), check(c, ["2015-06-17 13:37", "2018-03-02 09:00", "2021-11-23 20:15"]))
