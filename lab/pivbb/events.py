"""Pivot points + Bollinger bands on gold, the user's own reading of the market, as an event study.

An EVENT is the price reaching a level (a "touch"). For each touch we store what was known just before
(the context: Bollinger state, momentum, clock, ...) and what happened next (bounce, break, run to the
next pivot). Real levels are compared with PLACEBO levels: the same sets shifted by a random offset.
Whatever shows up equally on placebo levels is a property of price, not of pivots.

Set-up reproduced from the user's charts (TradingView, Gold, 15 minutes):
  * "Traditional" pivots from the previous trading day (17:00 New York close): P, R1-R3, S1-S3
    (R4/R5/S4/S5 are almost never reached), plus weekly and monthly pivots and yesterday's high / low;
  * Bollinger bands (20, 2) on 15-minute closes, and on 1-hour closes.
Everything a touch "knows" comes from bars closed before the touch minute.

    python3 pivbb/events.py            -> results/pivbb/events.parquet (real levels + placebo seeds)
"""
import os
import sys

import numba as nb
import numpy as np
import pandas as pd

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LAB)
from goldlab import r2  # noqa: E402
from goldlab.data import NY, trading_day  # noqa: E402

OUT = os.path.join(LAB, "results", "pivbb")
ARM = 0.15            # a level is "armed" once price has been at least ARM x dATR away from it
BARRIERS = (0.15, 0.25, 0.50)     # bounce / break distance, in dATR
N_PLACEBO = 10
D_LEVELS = ["S3", "S2", "S1", "P", "R1", "R2", "R3"]


def pivots(h, l, c):
    """TradingView 'Traditional' pivots from a period's high, low, close."""
    p = (h + l + c) / 3.0
    return {"P": p, "R1": 2 * p - l, "S1": 2 * p - h, "R2": p + (h - l), "S2": p - (h - l),
            "R3": 2 * p + (h - 2 * l), "S3": 2 * p - (2 * h - l)}


@nb.njit(cache=True)
def _touches(h, l, c, a, b, level, arm):
    """Touches of `level` on M1 bars [a, b). side = +1 when price came up to the level, -1 when it came down.
    The level is armed from a side once a close is at least `arm` away on that side; a touch disarms it."""
    out_i = np.empty(64, np.int64)
    out_s = np.empty(64, np.int64)
    n = 0
    side = 0
    for i in range(a, b):
        if side == 1 and h[i] >= level:
            if n < 64:
                out_i[n] = i
                out_s[n] = 1
                n += 1
            side = 0
        elif side == -1 and l[i] <= level:
            if n < 64:
                out_i[n] = i
                out_s[n] = -1
                n += 1
            side = 0
        else:
            if c[i] <= level - arm:
                side = 1
            elif c[i] >= level + arm:
                side = -1
    return out_i[:n], out_s[:n]


@nb.njit(cache=True)
def _first_passage(h, l, c, i, e, level, s, x):
    """After a touch on bar i: does price first move x back (bounce, 1) or x through the level (break, 0)?
    -1 = neither before bar e; 2 = both inside one bar (ambiguous). Also returns the number of bars taken."""
    up, dn = level + x, level - x
    brk, bnc = (up, dn) if s == 1 else (dn, up)
    # touch bar: the break side can be reached within it; a bounce only if the bar closes beyond the bounce barrier
    if (s == 1 and h[i] >= brk) or (s == -1 and l[i] <= brk):
        return 0, 0
    if (s == 1 and c[i] <= bnc) or (s == -1 and c[i] >= bnc):
        return 1, 0
    for j in range(i + 1, e):
        hit_up, hit_dn = h[j] >= up, l[j] <= dn
        if hit_up and hit_dn:
            return 2, j - i
        if hit_up:
            return (0 if s == 1 else 1), j - i
        if hit_dn:
            return (1 if s == 1 else 0), j - i
    return -1, e - i


@nb.njit(cache=True)
def _race(h, l, i, e, ahead, behind, s):
    """After a touch on bar i: does price reach the next level `ahead` (1) before the level `behind` (0)? -1 neither, 2 both."""
    for j in range(i + 1, e):
        a_hit = (h[j] >= ahead) if s == 1 else (l[j] <= ahead)
        b_hit = (l[j] <= behind) if s == 1 else (h[j] >= behind)
        if a_hit and b_hit:
            return 2
        if a_hit:
            return 1
        if b_hit:
            return 0
    return -1


def _rsi(c, n=14):
    d = np.diff(c, prepend=c[0])
    up = pd.Series(np.where(d > 0, d, 0.0)).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()
    dn = pd.Series(np.where(d < 0, -d, 0.0)).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()
    return 100.0 * up / np.maximum(up + dn, 1e-12)


class Gold:
    """Arrays shared by every analysis: M1 mid prices, trading days, levels, 15-minute and 1-hour indicators."""

    def __init__(self, sym="xauusd"):
        m1 = r2.load(sym)
        self.index = m1.index
        self.tmin = (m1.index.as_unit("ms").asi8 // 60_000).astype(np.int64)
        self.o = ((m1["bo"] + m1["ao"]) / 2).to_numpy(np.float64)
        self.h = ((m1["bh"] + m1["ah"]) / 2).to_numpy(np.float64)
        self.l = ((m1["bl"] + m1["al"]) / 2).to_numpy(np.float64)
        self.c = ((m1["bc"] + m1["ac"]) / 2).to_numpy(np.float64)
        self.spr = (m1["ac"] - m1["bc"]).to_numpy(np.float64)
        r2.free(sym)
        td = trading_day(self.index)
        day = td.asi8
        self.first = np.r_[0, np.flatnonzero(np.diff(day)) + 1]
        self.last = np.r_[self.first[1:], len(day)]                      # exclusive
        cnt = self.last - self.first
        self.dates = pd.DatetimeIndex(td[self.first])
        D = pd.DataFrame({"o": self.o[self.first], "h": np.maximum.reduceat(self.h, self.first),
                          "l": np.minimum.reduceat(self.l, self.first), "c": self.c[self.last - 1], "n": cnt}, index=self.dates)
        D["full"] = D.n >= 600
        F = D[D.full]
        tr = np.maximum(F.h - F.l, np.maximum((F.h - F.c.shift(1)).abs(), (F.l - F.c.shift(1)).abs()))
        # what a day knows at its open: the previous FULL day's high / low / close, the ATR up to that day, the 20-day close
        prev = pd.DataFrame({"ph": F.h, "pl": F.l, "pc": F.c, "atr": tr.rolling(14).mean(), "c20": F.c.shift(19)}).shift(1)
        D = D.join(prev.reindex(D.index, method=None))
        D[["ph", "pl", "pc", "atr", "c20"]] = D[["ph", "pl", "pc", "atr", "c20"]].where(D.full)
        # weekly / monthly sets: previous week's (month's) high, low, close over full days
        for tag, key in (("w", F.index.to_period("W-FRI")), ("m", F.index.to_period("M"))):
            g = F.groupby(key).agg(h=("h", "max"), l=("l", "min"), c=("c", "last")).shift(1)
            k = D.index.to_period("W-FRI" if tag == "w" else "M")
            for col in "hlc":
                D[tag + col] = g[col].reindex(k).to_numpy()
        self.D = D
        # 15-minute and 1-hour bars on the clock grid, with the indicators of the user's chart
        self.b15 = self._bars(15)
        self.b60 = self._bars(60)

    def _bars(self, width):
        key = self.tmin // width
        first = np.r_[0, np.flatnonzero(np.diff(key)) + 1]
        last = np.r_[first[1:], len(key)] - 1
        b = pd.DataFrame({"start": key[first] * width, "o": self.o[first], "h": np.maximum.reduceat(self.h, first),
                          "l": np.minimum.reduceat(self.l, first), "c": self.c[last]})
        b["end"] = b.start + width                                      # the bar is known from this minute on
        b["mid"] = b.c.rolling(20).mean()
        b["sd"] = b.c.rolling(20).std(ddof=0)
        pc = b.c.shift(1)
        b["atr"] = np.maximum(b.h - b.l, np.maximum((b.h - pc).abs(), (b.l - pc).abs())).rolling(14).mean()
        b["rsi"] = _rsi(b.c.to_numpy())
        b["bw_med"] = (4 * b.sd).rolling(96).median()
        b["out_up"] = (b.c > b.mid + 2 * b.sd).rolling(8).sum()
        b["out_dn"] = (b.c < b.mid - 2 * b.sd).rolling(8).sum()
        return b

    def level_sets(self, seed=None):
        """Per trading day: {name: price} for daily, weekly, monthly pivots and yesterday's high / low.
        seed = None: the real levels. Otherwise every set is shifted by +/- U(0.2, 0.4) x dATR (placebo)."""
        D = self.D
        rng = np.random.default_rng(seed) if seed is not None else None
        sh = lambda: 0.0 if rng is None else rng.uniform(0.2, 0.4, len(D)) * rng.choice([-1.0, 1.0], len(D)) * D.atr.to_numpy()
        out = {}
        d = pivots(D.ph, D.pl, D.pc)
        s = sh()
        for k in D_LEVELS:
            out["D_" + k] = d[k].to_numpy() + s
        w, s = pivots(D.wh, D.wl, D.wc), sh()
        for k in ("S2", "S1", "P", "R1", "R2"):
            out["W_" + k] = w[k].to_numpy() + s
        m, s = pivots(D.mh, D.ml, D.mc), sh()
        for k in ("S1", "P", "R1"):
            out["M_" + k] = m[k].to_numpy() + s
        s = sh()
        out["PDH"], out["PDL"] = D.ph.to_numpy() + s, D.pl.to_numpy() + s
        return out


def build(g, seed=None):
    """One row per touch, with context and outcomes."""
    D, b15, b60 = g.D, g.b15, g.b60
    L = g.level_sets(seed)
    names = list(L)
    ny = g.index.tz_convert(NY)
    ny_min = (ny.hour * 60 + ny.minute).to_numpy()
    e15, e60 = b15.end.to_numpy(), b60.end.to_numpy()
    A15 = {k: b15[k].to_numpy() for k in ("c", "mid", "sd", "atr", "rsi", "bw_med", "out_up", "out_dn")}
    A60 = {k: b60[k].to_numpy() for k in ("mid", "sd")}
    rows = []
    for di in range(len(D)):
        atr = D.atr.iloc[di]
        if not (D.full.iloc[di] and np.isfinite(atr) and atr > 0):
            continue
        a, b = int(g.first[di]), int(g.last[di])
        day_levels = np.sort(np.array([L["D_" + k][di] for k in D_LEVELS]))
        n_any = 0
        ev = []
        for nm in names:
            lv = L[nm][di]
            if not np.isfinite(lv):
                continue
            ti, ts = _touches(g.h, g.l, g.c, a, b, lv, ARM * atr)
            for q in range(len(ti)):
                ev.append((int(ti[q]), int(ts[q]), nm, float(lv), q))
        ev.sort()
        for i, s, nm, lv, q in ev:
            k = int(np.searchsorted(e15, g.tmin[i], side="right")) - 1          # last 15-min bar closed before the touch
            k6 = int(np.searchsorted(e60, g.tmin[i], side="right")) - 1
            if k < 120 or not np.isfinite(A15["bw_med"][k]) or A15["sd"][k] <= 0 or A15["atr"][k] <= 0:
                n_any += 1
                continue
            r = {"day": D.index[di], "t": g.index[i], "i": i, "level": nm, "fam": nm.split("_")[0] if "_" in nm else "PD",
                 "px": lv, "s": s, "atr_d": atr, "nth_level": q, "nth_any": n_any,
                 # Bollinger (15 min): where the level sits against the band on the side price arrives from (1 = on the band)
                 "stretch15": s * (lv - A15["mid"][k]) / (2 * A15["sd"][k]),
                 "stretch60": s * (lv - A60["mid"][k6]) / (2 * A60["sd"][k6]) if A60["sd"][k6] > 0 else np.nan,
                 "bw": 4 * A15["sd"][k] / atr, "squeeze": 4 * A15["sd"][k] / A15["bw_med"][k],
                 "mid_slope": s * (A15["mid"][k] - A15["mid"][k - 4]) / A15["atr"][k],
                 "walk": A15["out_up"][k] if s == 1 else A15["out_dn"][k],
                 "rsi": A15["rsi"][k] if s == 1 else 100 - A15["rsi"][k],
                 "mom4": s * (A15["c"][k] - A15["c"][k - 4]) / A15["atr"][k],
                 "mom16": s * (A15["c"][k] - A15["c"][k - 16]) / A15["atr"][k],
                 "atr15_d": A15["atr"][k] / atr,
                 "ny_hour": ny_min[i] / 60.0, "dow": int(D.index[di].dayofweek),
                 "from_open": s * (lv - g.o[a]) / atr, "range_used": (g.h[a:i].max() - g.l[a:i].min()) / atr if i > a else 0.0,
                 "trend20": s * (g.o[a] - D.c20.iloc[di]) / (atr * np.sqrt(20)) if np.isfinite(D.c20.iloc[di]) else np.nan,
                 "gap": s * (g.o[a] - D.pc.iloc[di]) / atr,
                 "spread": g.spr[i - 1]}
            for x in BARRIERS:
                y, n = _first_passage(g.h, g.l, g.c, i, b, lv, s, x * atr)
                r[f"y{int(x * 100)}"], r[f"n{int(x * 100)}"] = y, n
            # run to the next daily pivot: the level ahead and the level behind in today's daily set
            ahead = day_levels[day_levels > lv + 1e-9] if s == 1 else day_levels[day_levels < lv - 1e-9][::-1]
            behind = day_levels[day_levels < lv - 1e-9][::-1] if s == 1 else day_levels[day_levels > lv + 1e-9]
            if len(ahead) and len(behind):
                r["race"] = _race(g.h, g.l, i, b, ahead[0], behind[0], s)
                r["race_odds"] = abs(lv - behind[0]) / (abs(ahead[0] - lv) + abs(lv - behind[0]))   # chance of a driftless walk
            else:
                r["race"], r["race_odds"] = -1, np.nan
            rows.append(r)
            n_any += 1
    ev = pd.DataFrame(rows)
    ev["seed"] = -1 if seed is None else seed
    return ev


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    g = Gold()
    parts = [build(g)]
    print("real levels:", len(parts[0]), "touches", flush=True)
    for sd in range(N_PLACEBO):
        parts.append(build(g, seed=sd))
        print("placebo", sd, len(parts[-1]), flush=True)
    ev = pd.concat(parts, ignore_index=True)
    ev.to_parquet(os.path.join(OUT, "events.parquet"))
    print("saved", len(ev), "rows")
