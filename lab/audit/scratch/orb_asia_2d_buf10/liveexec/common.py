"""Live-execution lens (orb_asia_2d_buf10): shared helpers.  Run from /home/user/gold-orb/lab.

Nothing here modifies goldlab / tracks / results/<track>.  Numba cache and bytecode are redirected
so nothing is written under lab/tracks.  VAL access only via val_part() -> gl.cut(..., "val",
track="review", label="liveexec:orb_asia_2d_buf10:<what>").
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("NUMBA_CACHE_DIR", os.path.join(HERE, "numba_cache"))
sys.dont_write_bytecode = True

import importlib.util  # noqa: E402
import math  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

LAB = "/home/user/gold-orb/lab"
if LAB not in sys.path:
    sys.path.insert(0, LAB)
import goldlab as gl  # noqa: E402
from goldlab.data import trading_day  # noqa: E402
from goldlab.sim import COSTS, Costs  # noqa: E402

PARIS = "Europe/Paris"
NAME = "orb_asia_2d_buf10"


def load_strategy():
    d = os.path.join(LAB, "tracks", "orb")
    spec = importlib.util.spec_from_file_location("strategy_orb_liveexec", os.path.join(d, "strategy.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod      # lets numba's on-disk cache (in NUMBA_CACHE_DIR) find the module
    spec.loader.exec_module(mod)
    return mod


S = load_strategy()
PARAMS = dict(S.FINALISTS[NAME])


def baseline(m1=None):
    m1 = gl.load_m1("xauusd") if m1 is None else m1
    o = S.make_orders(m1, **PARAMS).reset_index(drop=True)
    t = gl.simulate(m1, o, no_overlap=True)
    return m1, o, t


def _pf(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    g, l = x[x > 0].sum(), -x[x < 0].sum()
    return round(float(g / l), 3) if l > 0 else None


def stats(t, col="R"):
    if len(t) == 0:
        return {"n": 0}
    R = t[col].to_numpy(float)
    ok = np.isfinite(R)
    R = R[ok]
    yrs = t.entry_time.dt.year.to_numpy()[ok]
    by = pd.Series(R).groupby(yrs).sum()
    lo = t.side.to_numpy()[ok] > 0
    return {"n": int(len(R)), "pf": _pf(R), "exp": round(float(R.mean()), 4),
            "t": round(float(R.mean() / (R.std(ddof=1) / math.sqrt(len(R)))), 2) if len(R) > 2 else None,
            "totR": round(float(R.sum()), 1), "yrs_pos": f"{int((by > 0).sum())}/{len(by)}",
            "pf_long": _pf(R[lo]), "pf_short": _pf(R[~lo]),
            "R_long": round(float(R[lo].sum()), 1), "R_short": round(float(R[~lo].sum()), 1)}


def is_part(t):
    return gl.cut(t, "is")


def val_part(t, what):
    return gl.cut(t, "val", track="review", label=f"liveexec:{NAME}:{what}")


def post_costs(t, costs=None):
    """Recompute swap / commission / pnl / R for a trades frame (same formulas as goldlab.sim)."""
    c = costs or COSTS["xauusd"]
    t = t.copy()
    gross = t.side * (t.exit - t.entry)
    d0 = trading_day(t.entry_time).values.astype("datetime64[D]")
    d1 = trading_day(t.exit_time - pd.Timedelta(seconds=1)).values.astype("datetime64[D]")
    nights = np.busday_count(d0, d1) + 2 * np.busday_count(d0, d1, weekmask="Wed")
    rate = np.where(t.side > 0, c.swap_long, c.swap_short)
    t["nights"] = nights
    t["swap"] = t.entry * rate / 360.0 * nights
    t["commission"] = c.commission
    t["pnl"] = gross - t["swap"] - t["commission"]
    t["risk"] = (t.entry - t.stop).abs()
    t["R"] = t.pnl / t.risk.where(t.risk > 0)
    return t


def fmt(d):
    return " ".join(f"{k}={v}" for k, v in d.items())


def orders_from_levels(m1, s, buy_lv, sell_lv, allow_l=None, allow_s=None):
    """Re-implementation of the tail of S.make_orders for the finalist (entry='stop', stop='opp',
    no target/trail/be, no filters) from a sessions frame `s` and arbitrary level arrays.
    Used for level-perturbation experiments; checked to reproduce make_orders exactly."""
    n = len(s)
    allow_l = np.ones(n, bool) if allow_l is None else allow_l
    allow_s = np.ones(n, bool) if allow_s is None else allow_s
    ah, bl, ao, bo = (m1[k].to_numpy(np.float64) for k in ("ah", "bl", "ao", "bo"))
    fi, side = S._first_touch(ah, bl, ao, bo, s.i1.to_numpy(np.int64), s.ie.to_numpy(np.int64),
                              np.asarray(buy_lv, float), np.asarray(sell_lv, float), allow_l, allow_s)
    ok = fi >= 0
    level = np.where(side > 0, buy_lv, sell_lv)
    stop = np.where(side > 0, sell_lv, buy_lv)
    o = pd.DataFrame({"entry_i": fi[ok], "side": side[ok], "etype": 1, "level": level[ok],
                      "expiry_i": fi[ok], "stop": stop[ok], "target": np.nan,
                      "exit_i": s.ix.to_numpy(np.int64)[ok], "be": np.nan, "trail": np.nan,
                      "date": s.date.values[ok], "w_atr": s.w_atr.values[ok], "width": s.width.values[ok]})
    risk = np.abs(o.level - o.stop)
    o = o[(o.exit_i > o.entry_i) & np.isfinite(o.stop) & (risk > 0)]
    return o.reset_index(drop=True)


def finalist_sessions(m1, **over):
    p = dict(S.DEFAULTS)
    p.update(PARAMS)
    p.update(over)
    s = S.sessions(m1, p)
    s = s[s.width > 0].reset_index(drop=True)
    return s, p
