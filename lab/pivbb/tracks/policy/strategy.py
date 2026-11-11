"""Track 'policy' of the pivot + Bollinger study: the three-way decision WAIT / FADE / FOLLOW at a level touch.

    make_orders(m1, **params) -> orders DataFrame for goldlab.sim.simulate (works on any gold M1 bid/ask frame)
    FINALISTS = {name: params}

How a decision is made
----------------------
* Levels of trading day D (17:00 New York boundary) come from the last FULL trading day before D (>= 600 M1
  bars): "Traditional" daily pivots P, R1-R3, S1-S3, yesterday's high / low, the previous week's and the previous
  month's pivots. dATR = 14-day mean true range of full days, known at the open of D. All prices are MID prices
  (so the signals are the same on the FP frame, the cost-stress frame and the zero-cost frame).
* A TOUCH is the first M1 bar whose high / low reaches a level after a close at least 0.15 dATR away from it
  (same arming rule as the shared event builder pivbb/events.py).
* The CONTEXT of a touch uses only bars closed at the end of the touch minute (15-min / 1-h / 4-h bars closed
  before the touch minute, the M1 bars up to and including the touch bar). The order is a MARKET order at the
  open of the NEXT minute.
* The policy is either a frozen model (one model per walk-forward fold: a touch of year Y is scored by the model
  trained on years < Y; touches after the last fold year use the model trained on all in-sample data) or a
  scorecard (thresholds on context features). Nothing is ever fitted inside make_orders.

Differences from pivbb/events.py (deliberate, for causality): the shared builder skips days that turn out not to
be full (known only at the end of the day) and takes "previous week" as the previous group of full days; here a
day is traded whatever it turns out to be, and its levels come from the last full day / week / month before it.
"""
import os
import sys

import numba as nb
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
if LAB not in sys.path:
    sys.path.insert(0, LAB)
from goldlab.data import NY, trading_day  # noqa: E402

ARM = 0.15
LEVELS = ["D_S3", "D_S2", "D_S1", "D_P", "D_R1", "D_R2", "D_R3", "W_S2", "W_S1", "W_P", "W_R1", "W_R2",
          "M_S1", "M_P", "M_R1", "PDH", "PDL"]
FAM = np.array([0] * 7 + [1] * 5 + [2] * 3 + [3] * 2)
DRANK = np.array([-3, -2, -1, 0, 1, 2, 3] + [np.nan] * 10)
EOD = 16 * 60 + 50                      # forced exit, New York minute of day
MIN_ROOM = 15                           # no entry in the last 15 minutes before the forced exit

FIRST = ["s", "lvl", "nth_level", "nth_any", "stretch15", "stretch60", "bw", "squeeze", "mid_slope", "walk", "rsi",
         "mom4", "mom16", "atr15_d", "ny_hour", "dow", "from_open", "range_used", "trend20", "gap"]
EXTRA = ["fam", "outward", "n_dlev", "at_extreme", "open_vs_p", "lv_vs_p", "p_range", "p_loc", "p_body",
         "stretch240", "rsi60", "squeeze60", "pctb15", "r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8",
         "bar_rng", "bar_loc", "eff8", "m15", "m60", "pen", "tb_rng", "room_ahead", "room_behind", "dist_wm",
         "r10", "r50", "atr_pct", "atr_rel"]
RICH = FIRST + EXTRA


def pivots(h, l, c):
    p = (h + l + c) / 3.0
    return {"P": p, "R1": 2 * p - l, "S1": 2 * p - h, "R2": p + (h - l), "S2": p - (h - l),
            "R3": 2 * p + (h - 2 * l), "S3": 2 * p - (2 * h - l)}


def _rsi(c, n=14):
    d = np.diff(c, prepend=c[0])
    up = pd.Series(np.where(d > 0, d, 0.0)).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()
    dn = pd.Series(np.where(d < 0, -d, 0.0)).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()
    return 100.0 * up / np.maximum(up + dn, 1e-12)


@nb.njit(cache=True)
def _find_touches(h, l, c, first, last, Lm, arm):
    """All touches. Lm[day, level] (nan = no level), arm[day] (nan = day not tradable).
    Returns arrays: bar index, side (+1 price came up to the level), level code, nth touch of that level today, day."""
    nd, nl = Lm.shape
    cap = 1 << 16
    oi = np.empty(cap, np.int64)
    os_ = np.empty(cap, np.int64)
    oc = np.empty(cap, np.int64)
    oq = np.empty(cap, np.int64)
    od = np.empty(cap, np.int64)
    n = 0
    for d in range(nd):
        if not (arm[d] > 0):
            continue
        for j in range(nl):
            lv = Lm[d, j]
            if not np.isfinite(lv):
                continue
            side = 0
            q = 0
            for i in range(first[d], last[d]):
                hit = 0
                if side == 1 and h[i] >= lv:
                    hit = 1
                elif side == -1 and l[i] <= lv:
                    hit = -1
                if hit != 0:
                    if q < 64:
                        if n == cap:
                            cap *= 2
                            oi2 = np.empty(cap, np.int64); oi2[:n] = oi[:n]; oi = oi2
                            os2 = np.empty(cap, np.int64); os2[:n] = os_[:n]; os_ = os2
                            oc2 = np.empty(cap, np.int64); oc2[:n] = oc[:n]; oc = oc2
                            oq2 = np.empty(cap, np.int64); oq2[:n] = oq[:n]; oq = oq2
                            od2 = np.empty(cap, np.int64); od2[:n] = od[:n]; od = od2
                        oi[n] = i; os_[n] = hit; oc[n] = j; oq[n] = q; od[n] = d
                        n += 1
                        q += 1
                    side = 0
                else:
                    if c[i] <= lv - arm[d]:
                        side = 1
                    elif c[i] >= lv + arm[d]:
                        side = -1
    return oi[:n], os_[:n], oc[:n], oq[:n], od[:n]


@nb.njit(cache=True)
def _running(h, l, first, last):
    rh = np.empty(len(h))
    rl = np.empty(len(h))
    for d in range(len(first)):
        mh, ml = -np.inf, np.inf
        for i in range(first[d], last[d]):
            if h[i] > mh:
                mh = h[i]
            if l[i] < ml:
                ml = l[i]
            rh[i] = mh
            rl[i] = ml
    return rh, rl


class Ctx:
    """Arrays built from one M1 bid/ask frame (mid prices). Everything a day uses is known at its open."""

    def __init__(self, m1):
        idx = m1.index
        self.index = idx
        self.tmin = (idx.as_unit("ms").asi8 // 60_000).astype(np.int64)
        self.o = ((m1["bo"] + m1["ao"]) / 2).to_numpy(np.float64)
        self.h = ((m1["bh"] + m1["ah"]) / 2).to_numpy(np.float64)
        self.l = ((m1["bl"] + m1["al"]) / 2).to_numpy(np.float64)
        self.c = ((m1["bc"] + m1["ac"]) / 2).to_numpy(np.float64)
        ny = idx.tz_convert(NY)
        self.ny_min = (ny.hour * 60 + ny.minute).to_numpy()
        td = trading_day(idx)
        day = td.asi8
        self.first = np.r_[0, np.flatnonzero(np.diff(day)) + 1].astype(np.int64)
        self.last = np.r_[self.first[1:], len(day)].astype(np.int64)
        self.dates = pd.DatetimeIndex(td[self.first])
        D = pd.DataFrame({"o": self.o[self.first], "h": np.maximum.reduceat(self.h, self.first),
                          "l": np.minimum.reduceat(self.l, self.first), "c": self.c[self.last - 1],
                          "n": self.last - self.first}, index=self.dates)
        F = D[D.n >= 600]
        pc = F.c.shift(1)
        tr = np.maximum(F.h - F.l, np.maximum((F.h - pc).abs(), (F.l - pc).abs()))
        atr = tr.rolling(14).mean()
        st = pd.DataFrame({"ph": F.h, "pl": F.l, "pc": F.c, "po": F.o, "atr": atr, "c20": F.c.shift(19),
                           "atr60": atr.rolling(60, min_periods=20).median()})
        # the last full day strictly before each day
        pos = np.searchsorted(F.index.values, D.index.values, side="left") - 1
        pv = st.iloc[np.clip(pos, 0, None)].to_numpy().copy()
        pv[pos < 0] = np.nan
        for j, k in enumerate(st.columns):
            D[k] = pv[:, j]
        # the last week / month (of full days) strictly before each day's week / month
        for tag, freq in (("w", "W-FRI"), ("m", "M")):
            g = F.groupby(F.index.to_period(freq)).agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))
            gk = g.index.asi8
            p = np.searchsorted(gk, D.index.to_period(freq).asi8, side="left") - 1
            gv = g.to_numpy()[np.clip(p, 0, None)].copy() if len(g) else np.full((len(D), 3), np.nan)
            gv[p < 0] = np.nan
            for j, col in enumerate("hlc"):
                D[tag + col] = gv[:, j]
        self.D = D
        self.b15, self.b60, self.b240 = self._bars(15), self._bars(60), self._bars(240)
        # forced-exit bar of each day: first bar at / after 16:50 New York, else the day's last bar
        cand = np.flatnonzero((self.ny_min >= EOD) & (self.ny_min < 17 * 60))
        p = np.searchsorted(cand, self.first, side="left")
        x = np.where(p < len(cand), cand[np.clip(p, 0, max(len(cand) - 1, 0))] if len(cand) else -1, -1)
        self.eod_i = np.where((x >= self.first) & (x < self.last), x, self.last - 1).astype(np.int64)

    def _bars(self, width):
        key = self.tmin // width
        first = np.r_[0, np.flatnonzero(np.diff(key)) + 1]
        last = np.r_[first[1:], len(key)] - 1
        b = pd.DataFrame({"start": key[first] * width, "o": self.o[first], "h": np.maximum.reduceat(self.h, first),
                          "l": np.minimum.reduceat(self.l, first), "c": self.c[last]})
        b["end"] = b.start + width
        b["mid"] = b.c.rolling(20).mean()
        b["sd"] = b.c.rolling(20).std(ddof=0)
        pc = b.c.shift(1)
        b["atr"] = np.maximum(b.h - b.l, np.maximum((b.h - pc).abs(), (b.l - pc).abs())).rolling(14).mean()
        b["rsi"] = _rsi(b.c.to_numpy())
        b["bw_med"] = (4 * b.sd).rolling(96).median()
        b["out_up"] = (b.c > b.mid + 2 * b.sd).rolling(8).sum()
        b["out_dn"] = (b.c < b.mid - 2 * b.sd).rolling(8).sum()
        return b

    def level_matrix(self, seed=None):
        """(days x 17) level prices. seed = None: real levels; otherwise each family (daily, weekly, monthly,
        yesterday's high/low) is shifted by +/- U(0.2, 0.4) x dATR, drawn per day from (seed, family, date)
        so that the placebo does not depend on the length of the frame."""
        D = self.D
        d = pivots(D.ph, D.pl, D.pc)
        w = pivots(D.wh, D.wl, D.wc)
        m = pivots(D.mh, D.ml, D.mc)
        cols = [d[k] for k in ("S3", "S2", "S1", "P", "R1", "R2", "R3")] + [w[k] for k in ("S2", "S1", "P", "R1", "R2")] + \
               [m[k] for k in ("S1", "P", "R1")] + [D.ph, D.pl]
        Lm = np.column_stack([np.asarray(x, np.float64) for x in cols])
        if seed is not None:
            ordn = (D.index.values.astype("datetime64[D]").astype(np.int64))
            atr = D.atr.to_numpy()
            for f in range(4):
                sh = np.empty(len(D))
                for i, od in enumerate(ordn):
                    r = np.random.default_rng([int(seed), f, int(od)])
                    sh[i] = r.uniform(0.2, 0.4) * (1.0 if r.random() < 0.5 else -1.0)
                Lm[:, FAM == f] += (sh * atr)[:, None]
        return Lm


def events(ctx, seed=None):
    """One row per touch with its causal context (see module docstring)."""
    D, b15, b60, b240 = ctx.D, ctx.b15, ctx.b60, ctx.b240
    Lm = ctx.level_matrix(seed)
    atr_day = D.atr.to_numpy()
    ti, ts, tc, tq, td = _find_touches(ctx.h, ctx.l, ctx.c, ctx.first, ctx.last, Lm, ARM * atr_day)
    order = np.lexsort((tc, ts, ti))                       # time, then side, then level
    ti, ts, tc, tq, td = ti[order], ts[order], tc[order], tq[order], td[order]
    if len(ti) == 0:
        return pd.DataFrame(columns=["i", "di", "t", "level", "px", "s", "atr_d", "year"] + RICH)
    # rank among today's touches, and distinct daily levels already touched today
    new_day = np.r_[True, td[1:] != td[:-1]]
    grp_start = np.maximum.accumulate(np.where(new_day, np.arange(len(td)), 0))
    nth_any = np.arange(len(td)) - grp_start
    fd = ((FAM[tc] == 0) & (tq == 0)).astype(np.int64)
    cs = np.cumsum(fd)
    n_dlev = cs - fd - (cs - fd)[grp_start]
    s = ts.astype(np.float64)
    lv = Lm[td, tc]
    atr = atr_day[td]
    a = ctx.first[td]
    e15, e60, e240 = b15.end.to_numpy(), b60.end.to_numpy(), b240.end.to_numpy()
    k = np.searchsorted(e15, ctx.tmin[ti], side="right") - 1
    k6 = np.searchsorted(e60, ctx.tmin[ti], side="right") - 1
    k24 = np.searchsorted(e240, ctx.tmin[ti], side="right") - 1
    A = {q: b15[q].to_numpy() for q in ("c", "h", "l", "mid", "sd", "atr", "rsi", "bw_med", "out_up", "out_dn")}
    B = {q: b60[q].to_numpy() for q in ("mid", "sd", "rsi", "bw_med")}
    C = {q: b240[q].to_numpy() for q in ("mid", "sd")}
    kk = np.clip(k, 16, None)
    k6c, k24c = np.clip(k6, 0, None), np.clip(k24, 0, None)
    with np.errstate(divide="ignore", invalid="ignore"):
        ok = (k >= 120) & np.isfinite(A["bw_med"][kk]) & (A["sd"][kk] > 0) & (A["atr"][kk] > 0)
        rh, rl = _running(ctx.h, ctx.l, ctx.first, ctx.last)
        rhp, rlp = rh[ti - 1], rl[ti - 1]
        a15 = A["atr"][kk]
        f = {}
        f["s"] = s
        f["lvl"] = tc.astype(np.float64)
        f["nth_level"] = tq.astype(np.float64)
        f["nth_any"] = nth_any.astype(np.float64)
        f["stretch15"] = s * (lv - A["mid"][kk]) / (2 * A["sd"][kk])
        f["stretch60"] = np.where(B["sd"][k6c] > 0, s * (lv - B["mid"][k6c]) / (2 * B["sd"][k6c]), np.nan)
        f["bw"] = 4 * A["sd"][kk] / atr
        f["squeeze"] = 4 * A["sd"][kk] / A["bw_med"][kk]
        f["mid_slope"] = s * (A["mid"][kk] - A["mid"][kk - 4]) / a15
        f["walk"] = np.where(ts == 1, A["out_up"][kk], A["out_dn"][kk])
        f["rsi"] = np.where(ts == 1, A["rsi"][kk], 100 - A["rsi"][kk])
        f["mom4"] = s * (A["c"][kk] - A["c"][kk - 4]) / a15
        f["mom16"] = s * (A["c"][kk] - A["c"][kk - 16]) / a15
        f["atr15_d"] = a15 / atr
        f["ny_hour"] = ctx.ny_min[ti] / 60.0
        f["dow"] = D.index.dayofweek.to_numpy()[td].astype(np.float64)
        f["from_open"] = s * (lv - ctx.o[a]) / atr
        f["range_used"] = (rhp - rlp) / atr
        c20 = D.c20.to_numpy()[td]
        f["trend20"] = s * (ctx.o[a] - c20) / (atr * np.sqrt(20))
        f["gap"] = s * (ctx.o[a] - D.pc.to_numpy()[td]) / atr
        # --- richer context
        f["fam"] = FAM[tc].astype(np.float64)
        f["outward"] = s * DRANK[tc]
        f["n_dlev"] = n_dlev.astype(np.float64)
        f["at_extreme"] = np.where(ts == 1, lv >= rhp, lv <= rlp).astype(np.float64)
        P = Lm[td, 3]
        f["open_vs_p"] = s * (ctx.o[a] - P) / atr
        f["lv_vs_p"] = s * (lv - P) / atr
        ph, pl, pc, po = (D[q].to_numpy()[td] for q in ("ph", "pl", "pc", "po"))
        f["p_range"] = (ph - pl) / atr
        f["p_loc"] = s * (2 * (pc - pl) / (ph - pl) - 1)
        f["p_body"] = s * (pc - po) / atr
        f["stretch240"] = np.where(C["sd"][k24c] > 0, s * (lv - C["mid"][k24c]) / (2 * C["sd"][k24c]), np.nan)
        f["rsi60"] = np.where(ts == 1, B["rsi"][k6c], 100 - B["rsi"][k6c])
        f["squeeze60"] = 4 * B["sd"][k6c] / B["bw_med"][k6c]
        f["pctb15"] = s * (A["c"][kk] - A["mid"][kk]) / (2 * A["sd"][kk])
        tot = np.zeros(len(ti))
        for j in range(8):
            dj = A["c"][kk - j] - A["c"][kk - j - 1]
            f[f"r{j + 1}"] = s * dj / a15
            tot += np.abs(dj)
        f["bar_rng"] = (A["h"][kk] - A["l"][kk]) / a15
        f["bar_loc"] = s * (2 * (A["c"][kk] - A["l"][kk]) / (A["h"][kk] - A["l"][kk]) - 1)
        f["eff8"] = s * (A["c"][kk] - A["c"][kk - 8]) / tot
        f["m15"] = s * (ctx.c[ti] - ctx.c[np.clip(ti - 15, 0, None)]) / atr
        f["m60"] = s * (ctx.c[ti] - ctx.c[np.clip(ti - 60, 0, None)]) / atr
        f["pen"] = s * (ctx.c[ti] - lv) / atr
        f["tb_rng"] = (ctx.h[ti] - ctx.l[ti]) / atr
        diff = s[:, None] * (Lm[td] - lv[:, None]) / atr[:, None]
        f["room_ahead"] = np.minimum(np.nanmin(np.where(diff > 1e-9, diff, np.inf), axis=1), 3.0)
        f["room_behind"] = np.minimum(np.nanmin(np.where(diff < -1e-9, -diff, np.inf), axis=1), 3.0)
        wm = np.abs(diff[:, 7:15]).copy()
        own = (tc >= 7) & (tc < 15)
        wm[np.flatnonzero(own), tc[own] - 7] = np.nan
        wm = np.where(np.isfinite(wm), wm, np.inf)
        f["dist_wm"] = np.minimum(wm.min(axis=1), 3.0)
        f["r10"] = np.abs(lv - np.round(lv / 10.0) * 10.0) / atr
        f["r50"] = np.abs(lv - np.round(lv / 50.0) * 50.0) / atr
        f["atr_pct"] = 100.0 * atr / lv
        f["atr_rel"] = atr / D.atr60.to_numpy()[td]
    ev = pd.DataFrame(f)
    ev.insert(0, "atr_d", atr)
    ev.insert(0, "px", lv)
    ev.insert(0, "level", np.array(LEVELS)[tc])
    ev.insert(0, "t", ctx.index[ti])
    ev.insert(0, "di", td)
    ev.insert(0, "i", ti)
    ev["year"] = ctx.index[ti].year.to_numpy()
    ev["eod_i"] = ctx.eod_i[td]
    ev = ev[ok].replace([np.inf, -np.inf], np.nan).reset_index(drop=True)
    return ev


_CACHE = {}


def get_events(m1, seed=None):
    """Events of a frame, cached by (length, first / last time, sum of mid closes rounded, seed). The signals use
    mid prices only, so the FP, cost-stress and zero-cost frames of one evaluation share one table."""
    key = (len(m1), m1.index[0], m1.index[-1], round(float(m1["bc"].iloc[-1] + m1["ac"].iloc[-1]), 6), seed)
    if key not in _CACHE:
        if len(_CACHE) > 14:
            _CACHE.clear()
        _CACHE[key] = events(Ctx(m1), seed)
    return _CACHE[key]


def trade_orders(ev, side, stop=0.25, target=None, hold=None):
    """Market orders at the open of the minute after the touch. side: array of +1 / -1 (already follow = s, fade = -s).
    stop / target in dATR from the fill; hold in minutes (None = until the forced exit at 16:50 New York)."""
    entry = ev.i.to_numpy() + 1
    eod = ev.eod_i.to_numpy()
    x = eod if hold is None else np.minimum(entry + int(hold), eod)
    o = pd.DataFrame({"entry_i": entry, "side": np.asarray(side, np.int64), "etype": 0,
                      "stop_dist": stop * ev.atr_d.to_numpy(),
                      "target_dist": np.nan if target is None else target * ev.atr_d.to_numpy(),
                      "exit_i": x})
    return o


def tradable(ev):
    return (ev.i.to_numpy() + 1 + MIN_ROOM <= ev.eod_i.to_numpy())


_MODELS = {}


def load_model(name):
    if name not in _MODELS:
        import joblib
        _MODELS[name] = joblib.load(os.path.join(HERE, name))
    return _MODELS[name]


def score(ev, model):
    """Predicted net R of following and of fading each touch, and the thresholds of the model that scores it.
    A touch of year Y is scored by the fold model trained on years < Y; years after the last fold use 'final';
    years before the first fold are not scored (nan)."""
    M = load_model(model) if isinstance(model, str) else model
    n = len(ev)
    pf, pd_ = np.full(n, np.nan), np.full(n, np.nan)
    thr = {a: {q: np.full(n, np.nan) for q in ("q70", "q80", "q90")} for a in ("follow", "fade")}
    yr = ev.year.to_numpy()
    folds = sorted(M["folds"])
    for key in folds + ["final"]:
        m = M["folds"][key] if key != "final" else M["final"]
        sel = (yr == key) if key != "final" else (yr > folds[-1])
        if not sel.any():
            continue
        X = ev.loc[sel, M["feats"]]
        pf[sel] = m["follow"].predict(X)
        pd_[sel] = m["fade"].predict(X)
        for a in ("follow", "fade"):
            for q in thr[a]:
                thr[a][q][sel] = m["thr"][a][q]
    return pf, pd_, thr


def decide(ev, policy="model", model=None, q="q90", arm="both", rule=None, levels=None, hours=None, min_pred=None):
    """The three-way decision: +1 follow, -1 fade, 0 wait, for each touch."""
    n = len(ev)
    act = np.zeros(n, np.int64)
    if policy == "model":
        pf, pd_, thr = score(ev, model)
        with np.errstate(invalid="ignore"):
            fo = (pf >= thr["follow"][q]) & (pf >= pd_)
            fa = (pd_ >= thr["fade"][q]) & (pd_ > pf)
            if min_pred is not None:
                fo &= pf >= min_pred
                fa &= pd_ >= min_pred
        if arm in ("both", "follow"):
            act[fo] = 1
        if arm in ("both", "fade"):
            act[fa] = -1
    elif policy == "rule":
        # rule = {"follow": {feature: [lo, hi], ...}, "fade": {...}}; a touch matching both is left alone
        m = {}
        for a in ("follow", "fade"):
            cond = (rule or {}).get(a)
            if cond is None:
                m[a] = np.zeros(n, bool)
                continue
            ok = np.ones(n, bool)
            for feat, (lo, hi) in cond.items():
                v = ev[feat].to_numpy()
                with np.errstate(invalid="ignore"):
                    ok &= (v >= lo) & (v < hi)
            m[a] = ok
        act[m["follow"] & ~m["fade"]] = 1
        act[m["fade"] & ~m["follow"]] = -1
    elif policy == "all_follow":
        act[:] = 1
    elif policy == "all_fade":
        act[:] = -1
    else:
        raise ValueError(policy)
    if levels is not None:
        act[~ev.level.isin(list(levels)).to_numpy()] = 0
    if hours is not None:
        h = ev.ny_hour.to_numpy()
        lo, hi = hours
        inside = (h >= lo) & (h < hi) if lo <= hi else (h >= lo) | (h < hi)
        act[~inside] = 0
    act[~tradable(ev)] = 0
    return act


def make_orders(m1, policy="model", model=None, q="q90", arm="both", rule=None, levels=None, hours=None,
                min_pred=None, stop=0.25, target=None, hold=None, stop_fade=None, target_fade=None, hold_fade=None,
                seed=None, tag=None):
    """Orders of the three-way policy. stop / target (dATR) and hold (minutes) describe the trade of the follow
    arm; the fade arm uses the same unless stop_fade / target_fade / hold_fade are given. seed = placebo levels."""
    ev = get_events(m1, seed)
    act = decide(ev, policy, model, q, arm, rule, levels, hours, min_pred)
    parts = []
    for a, (st, tg, hd) in ((1, (stop, target, hold)),
                            (-1, (stop if stop_fade is None else stop_fade, target if target_fade is None else target_fade,
                                  hold if hold_fade is None else hold_fade))):
        e = ev[act == a]
        if len(e):
            o = trade_orders(e, a * e.s.to_numpy().astype(np.int64), st, tg, hd)
            o["action"] = a
            o["lvl_code"] = e.lvl.to_numpy()
            parts.append(o)
    if not parts:
        return pd.DataFrame({"entry_i": np.array([], np.int64), "side": np.array([], np.int64), "etype": np.array([], np.int64),
                             "stop_dist": [], "target_dist": [], "exit_i": np.array([], np.int64)})
    return pd.concat(parts).sort_values("entry_i", kind="stable").reset_index(drop=True)


FINALISTS = {}
