"""Construction (c): "one small trade a day" structures with a high hit rate. IN SAMPLE ONLY (2013-2021).

Question (fixed before any run): among structures that win on >= 70 % of their days, is there one whose EXPECTATION
is not negative after FP costs, in sample, with >= 400 days and both halves of the sample positive?
At most 40 configurations, every one logged in results/r2/jours/trials.jsonl (this file is the only writer).

Common conventions
    unit   ADR = mean (high - low) of the 20 previous full trading days (known at the start of the day)
    target T x ADR, stop S x ADR from the fill, one trade a day at most, time exit the same session
    result in R = pnl / stop distance (a full loss = -1 R, a full win = +T/S R), FP costs in the frame (net) or mid (gross)
    clock per market: us100 / us500 / us30 / btcusd New York (cash open 09:30), ger40 Berlin (09:00), xauusd /
    FX London (08:00); "quiet hours" = 19:00 New York (02:00 FP server) to 03:00 New York.
Structures
    orfade   limit order at the first-hour high (sell) / low (buy), first one touched after the first hour and before
             `last` ; target back inside, stop beyond
    gapfill  at the cash open + 1 min, if a x ADR <= |open - previous cash close| <= b x ADR: trade toward the previous
             close, target = the whole gap, stop = S x gap (here T, S are in units of the GAP)
    tomean   at midday, if |price - session average since the open| >= d x ADR: trade toward the average
    quiet    at 19:00 New York, limit sell at price + x ADR and limit buy at price - x ADR (first touched before
             01:00 New York), exit 03:00 New York
    beta     always long (index drift), intraday or overnight: reported as BETA, not as an edge
    mom      at open + 30 min, in the direction of the first 30 minutes (us indices); btcusd: at 17:05 New York in the
             direction of the last 24 h, exit 16:50 New York
"""
import json
import os
import sys

import numpy as np
import pandas as pd

import common as C
import goldlab as gl
from goldlab import r2
from goldlab.sim import apply_spread_mult, simulate

CLOCK = {"us100": ("America/New_York", "09:30", "10:30", "12:00", "15:55", "15:59"),
         "us500": ("America/New_York", "09:30", "10:30", "12:00", "15:55", "15:59"),
         "us30": ("America/New_York", "09:30", "10:30", "12:00", "15:55", "15:59"),
         "btcusd": ("America/New_York", "09:30", "10:30", "12:00", "15:55", "15:59"),
         "ger40": ("Europe/Berlin", "09:00", "10:00", "12:30", "17:25", "17:29"),
         "xauusd": ("Europe/London", "08:00", "09:00", "12:00", "16:55", "16:59"),
         "eurusd": ("Europe/London", "08:00", "09:00", "12:00", "16:55", "16:59"),
         "gbpusd": ("Europe/London", "08:00", "09:00", "12:00", "16:55", "16:59")}

# ---- the configurations (first pass written before any run; second pass = neighbours, added after the first) ----
T0, S0 = 0.15, 0.60
PASS1 = (
    [("orfade", s, dict(T=T0, S=S0)) for s in ("us100", "us500", "us30", "ger40", "xauusd", "eurusd", "gbpusd", "btcusd")]
    + [("gapfill", s, dict(a=0.10, b=0.50, T=1.0, S=3.0)) for s in ("us100", "us500", "us30", "ger40")]
    + [("tomean", s, dict(d=0.25, T=T0, S=S0)) for s in ("us100", "us500", "ger40", "eurusd", "xauusd")]
    + [("quiet", s, dict(x=0.15, T=T0, S=S0)) for s in ("eurusd", "gbpusd", "usdjpy", "audusd", "xauusd")]
    + [("beta", "us500", dict(mode="intraday", T=T0, S=S0)), ("beta", "us500", dict(mode="overnight", T=T0, S=S0)),
       ("beta", "us100", dict(mode="overnight", T=T0, S=S0))]
    + [("mom", "us100", dict(T=T0, S=S0)), ("mom", "us500", dict(T=T0, S=S0)), ("mom", "btcusd", dict(T=T0, S=S0))]
)
# second pass, written after reading the first one (results/r2/jours/c_pass1.json): neighbours and transfers of the
# only structures that came out >= 70 % with a net expectation >= 0 (mom on us indices / btcusd, tomean on eurusd).
# `look` = minutes after the open at which the direction is read and the trade entered (first pass: 30).
PASS2 = [
    ("mom", "us500", dict(T=0.10, S=0.60)), ("mom", "us500", dict(T=0.10, S=0.90)), ("mom", "us500", dict(T=0.20, S=0.60)),
    ("mom", "us500", dict(T=0.15, S=0.60, look=60)),
    ("mom", "us100", dict(T=0.10, S=0.60)), ("mom", "us100", dict(T=0.10, S=0.90)), ("mom", "us100", dict(T=0.15, S=0.60, look=60)),
    ("mom", "us30", dict(T=0.15, S=0.60)), ("mom", "ger40", dict(T=0.15, S=0.60)), ("mom", "btcusd", dict(T=0.10, S=0.60)),
    ("tomean", "eurusd", dict(d=0.15, T=0.15, S=0.60)), ("tomean", "gbpusd", dict(d=0.25, T=0.15, S=0.60)),
]
assert len(PASS1) + len(PASS2) <= 40


def _mid(m1, a, b):
    return (m1[a].to_numpy(float) + m1[b].to_numpy(float)) / 2


def day_table(m1, sym):
    """One row per local weekday: M1 indices of the session marks, ADR known that day."""
    tz, t_open, t_or, t_mid, t_exit, t_close = CLOCK.get(sym, CLOCK["eurusd"])
    loc = gl.local(m1.index, tz)
    dates = pd.DatetimeIndex(np.unique(loc.tz_localize(None).normalize()))
    dates = dates[dates.dayofweek < 5]
    d = pd.DataFrame({"date": dates})
    idx = m1.index

    def mark(hhmm, shift_days=0):
        t = (dates + pd.Timedelta(days=shift_days) + pd.Timedelta(hours=int(hhmm[:2]), minutes=int(hhmm[3:]))).tz_localize(
            tz, ambiguous=True, nonexistent="shift_forward").tz_convert("UTC")
        i = gl.entry_index(m1, t)
        ok = (i < len(idx)) & ((idx[np.clip(i, 0, len(idx) - 1)] - t) <= pd.Timedelta(minutes=5))
        return np.where(ok, i, -1), t
    for k, v in (("i_open", t_open), ("i_or", t_or), ("i_mid", t_mid), ("i_exit", t_exit), ("i_close", t_close)):
        d[k], _ = mark(v)
    fd = gl.full_days(m1)
    adr = (fd["h"] - fd["l"]).rolling(20).mean().shift(1)
    td = gl.trading_day(pd.DatetimeIndex(dates).tz_localize(tz).tz_convert("UTC") + pd.Timedelta(hours=12))
    d["adr"] = adr.reindex(td).to_numpy()
    return d


def _orders(rows):
    cols = ["entry_i", "side", "etype", "level", "expiry_i", "stop_dist", "target_dist", "exit_i"]
    if not rows:
        return pd.DataFrame(columns=cols)
    o = pd.DataFrame(rows, columns=cols)
    for c in ("entry_i", "side", "etype", "expiry_i", "exit_i"):
        o[c] = o[c].astype(np.int64)
    return o


def _first_touch(bh, al, i0, i1, hi, lo):
    """First bar in [i0, i1) where a sell limit at hi or a buy limit at lo would fill. (bar, side) or None."""
    if i1 <= i0:
        return None
    up = np.flatnonzero(bh[i0:i1] >= hi)
    dn = np.flatnonzero(al[i0:i1] <= lo)
    a = up[0] if len(up) else 10 ** 9
    b = dn[0] if len(dn) else 10 ** 9
    if a == b:
        return None                      # none touched, or both in the same minute: no trade
    return (i0 + a, -1) if a < b else (i0 + b, 1)


def make_orders(m1, sym=None, kind=None, **p):
    d = day_table(m1, sym)
    bh, al = m1["bh"].to_numpy(float), m1["al"].to_numpy(float)
    mo, mh, ml, mc = _mid(m1, "bo", "ao"), _mid(m1, "bh", "ah"), _mid(m1, "bl", "al"), _mid(m1, "bc", "ac")
    idx = m1.index
    rows = []
    if kind == "orfade":
        for r in d.itertuples():
            if min(r.i_open, r.i_or, r.i_exit) < 0 or not np.isfinite(r.adr) or r.i_or - r.i_open < 30:
                continue
            hi, lo = mh[r.i_open:r.i_or].max(), ml[r.i_open:r.i_or].min()
            ft = _first_touch(bh, al, r.i_or, r.i_exit - 60, hi, lo)
            if ft is None:
                continue
            i, side = ft
            rows.append((r.i_or, side, 2, hi if side < 0 else lo, i, p["S"] * r.adr, p["T"] * r.adr, r.i_exit))
    elif kind == "gapfill":
        prev_close = np.nan
        for r in d.itertuples():
            if r.i_open >= 0 and r.i_exit >= 0 and np.isfinite(prev_close) and np.isfinite(r.adr):
                i = r.i_open + 1
                gap = mo[i] - prev_close
                if p["a"] * r.adr <= abs(gap) <= p["b"] * r.adr and i < r.i_exit:
                    rows.append((i, -int(np.sign(gap)), 0, np.nan, -1, p["S"] * abs(gap), p["T"] * abs(gap), r.i_exit))
            prev_close = mc[r.i_close] if r.i_close >= 0 else np.nan
    elif kind == "tomean":
        for r in d.itertuples():
            if min(r.i_open, r.i_mid, r.i_exit) < 0 or not np.isfinite(r.adr) or r.i_mid - r.i_open < 60:
                continue
            dev = mc[r.i_mid - 1] - mc[r.i_open:r.i_mid].mean()
            if abs(dev) >= p["d"] * r.adr:
                rows.append((r.i_mid, -int(np.sign(dev)), 0, np.nan, -1, p["S"] * r.adr, p["T"] * r.adr, r.i_exit))
    elif kind == "quiet":
        ny = "America/New_York"
        loc = gl.local(idx, ny)
        dates = pd.DatetimeIndex(np.unique(loc.tz_localize(None).normalize()))
        dates = dates[dates.dayofweek < 4]                                  # Monday..Thursday evenings (New York)
        def at(h, plus=0):
            t = (dates + pd.Timedelta(days=plus, hours=h)).tz_localize(ny, ambiguous=True, nonexistent="shift_forward").tz_convert("UTC")
            i = gl.entry_index(m1, t)
            ok = (i < len(idx)) & ((idx[np.clip(i, 0, len(idx) - 1)] - t) <= pd.Timedelta(minutes=5))
            return np.where(ok, i, -1), t
        i0, t0 = at(19)
        i1, _ = at(1, 1)
        ix, _ = at(3, 1)
        fd = gl.full_days(m1)
        adr = (fd["h"] - fd["l"]).rolling(20).mean().shift(1).reindex(gl.trading_day(t0)).to_numpy()
        for a, b, x, u in zip(i0, i1, ix, adr):
            if min(a, b, x) < 0 or not np.isfinite(u):
                continue
            ref = mo[a]
            ft = _first_touch(bh, al, a, b, ref + p["x"] * u, ref - p["x"] * u)
            if ft is None:
                continue
            i, side = ft
            rows.append((a, side, 2, ref + p["x"] * u if side < 0 else ref - p["x"] * u, i, p["S"] * u, p["T"] * u, x))
    elif kind == "beta":
        dd = d.reset_index(drop=True)
        for k, r in enumerate(dd.itertuples()):
            if not np.isfinite(r.adr):
                continue
            if p["mode"] == "intraday":
                if r.i_open >= 0 and r.i_exit >= 0:
                    rows.append((r.i_open + 5, 1, 0, np.nan, -1, p["S"] * r.adr, p["T"] * r.adr, r.i_exit))
            elif k + 1 < len(dd) and r.i_exit >= 0 and dd.i_open[k + 1] >= 0 and (dd.date[k + 1] - r.date).days <= 3:
                rows.append((r.i_exit, 1, 0, np.nan, -1, p["S"] * r.adr, p["T"] * r.adr, int(dd.i_open[k + 1]) + 5))
    elif kind == "mom":
        if sym == "btcusd":
            ny = "America/New_York"
            dates = pd.DatetimeIndex(np.unique(gl.local(idx, ny).tz_localize(None).normalize()))
            dates = dates[dates.dayofweek.isin([6, 0, 1, 2, 3])]             # Sunday..Thursday 17:05 = server Mon..Fri
            t = (dates + pd.Timedelta(hours=17, minutes=5)).tz_localize(ny, ambiguous=True, nonexistent="shift_forward").tz_convert("UTC")
            i0 = gl.entry_index(m1, t)
            ix = gl.exit_index(m1, t + pd.Timedelta(hours=23, minutes=45))
            ip = np.searchsorted(idx.values, (t - pd.Timedelta(hours=24)).tz_localize(None).values.astype(idx.values.dtype), side="right") - 1
            fd = gl.full_days(m1)
            adr = (fd["h"] - fd["l"]).rolling(20).mean().shift(1).reindex(gl.trading_day(t)).to_numpy()
            for a, x, q, u, tt in zip(i0, ix, ip, adr, t):
                if a >= len(idx) or q < 0 or not np.isfinite(u) or x <= a or (idx[a] - tt) > pd.Timedelta(minutes=5):
                    continue
                mv = mc[a - 1] - mc[q]
                if mv != 0:
                    rows.append((a, int(np.sign(mv)), 0, np.nan, -1, p["S"] * u, p["T"] * u, x))
        else:
            for r in d.itertuples():
                if min(r.i_open, r.i_exit) < 0 or not np.isfinite(r.adr):
                    continue
                a = r.i_open + int(p.get("look", 30))
                mv = mc[a - 1] - mo[r.i_open]
                if mv != 0 and a < r.i_exit:
                    rows.append((a, int(np.sign(mv)), 0, np.nan, -1, p["S"] * r.adr, p["T"] * r.adr, r.i_exit))
    else:
        raise ValueError(kind)
    return _orders(rows)


def report(t):
    """Per-day report of a one-trade-a-day structure (t = IS trades, R per trade)."""
    if len(t) == 0:
        return {"days": 0}
    day = C.daily(t.exit_time, t.R)
    day = day[day != 0]
    h = len(day) // 2
    g, r = day[day > 0], day[day < 0]
    com = day[day.index >= pd.Timestamp("2018-02-01")]
    wk = day.groupby(day.index.to_period("W-SUN")).sum()
    return {"days": int(len(day)), "hit_pct": round(float((day > 0).mean() * 100), 1),
            "exp_R": round(float(day.mean()), 4), "t": round(float(day.mean() / day.std(ddof=1) * np.sqrt(len(day))), 2),
            "exp_bps": round(float((t.pnl / t.entry).mean() * 1e4), 2),
            "avg_green_R": round(float(g.mean()), 3) if len(g) else 0.0, "avg_red_R": round(float(-r.mean()), 3) if len(r) else 0.0,
            "total_R": round(float(day.sum()), 1), "half1_R": round(float(day.iloc[:h].sum()), 1),
            "half2_R": round(float(day.iloc[h:].sum()), 1), "worst_day_R": round(float(day.min()), 2),
            "green_weeks_pct": round(float((wk > 0).mean() * 100), 1),
            "long_R": round(float(t.R[t.side > 0].sum()), 1), "short_R": round(float(t.R[t.side < 0].sum()), 1),
            "common_days": int(len(com)), "common_hit_pct": round(float((com > 0).mean() * 100), 1) if len(com) else None,
            "common_total_R": round(float(com.sum()), 1), "reasons": t.reason.value_counts().to_dict(),
            "stop_bps_median": round(float((t.risk / t.entry).median() * 1e4), 1)}


def run_config(kind, sym, p, m1, mk, save=None):
    params = dict(sym=sym, kind=kind, **p)
    tn = simulate(m1, make_orders(m1, **params), sym=sym, costs=r2.costs(sym), no_overlap=True)
    tg = simulate(mk, make_orders(mk, **params), sym=sym, costs=r2.GROSS, no_overlap=True)
    tn, tg = tn[tn.entry_time < C.IS_END], tg[tg.entry_time < C.IS_END]
    rec = {"construction": "c_daily", "kind": kind, "sym": sym, "params": p, "net": report(tn), "gross": report(tg)}
    n = rec["net"]
    rec["passes"] = bool(n.get("days", 0) >= 400 and n["hit_pct"] >= 70 and n["exp_R"] >= 0 and n["half1_R"] > 0 and n["half2_R"] > 0)
    if save:
        os.makedirs(os.path.join(C.OUT, "c_trades"), exist_ok=True)
        keep = ["side", "entry_time", "exit_time", "entry", "exit", "stop", "reason", "pnl", "risk", "R"]
        tn[keep].to_parquet(os.path.join(C.OUT, "c_trades", f"{save}__net.parquet"))
        tg[keep].to_parquet(os.path.join(C.OUT, "c_trades", f"{save}__gross.parquet"))
    return rec


def run(configs, tag):
    by_sym = {}
    for k, (kind, sym, p) in enumerate(configs):
        by_sym.setdefault(sym, []).append((k, kind, p))
    recs = {}
    for sym, lst in by_sym.items():
        m1 = C.load_is(sym)
        mk = apply_spread_mult(m1, 0.0)
        for k, kind, p in lst:
            name = f"{tag}{k:02d}_{kind}_{sym}"
            rec = run_config(kind, sym, p, m1, mk, save=name)
            rec["name"] = name
            C.log_trial(rec, "trials.jsonl")
            recs[k] = rec
            n, g = rec["net"], rec["gross"]
            print(name, p, "| days", n.get("days"), "hit", n.get("hit_pct"), "net exp R", n.get("exp_R"), "t", n.get("t"),
                  "bps", n.get("exp_bps"), "halves", n.get("half1_R"), n.get("half2_R"), "| gross exp R", g.get("exp_R"),
                  "t", g.get("t"), "bps", g.get("exp_bps"), "| L/S net", n.get("long_R"), n.get("short_R"), "PASS" if rec["passes"] else "",
                  flush=True)
        del m1, mk
    return [recs[k] for k in sorted(recs)]


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "pass1"
    if which == "pass1":
        out = run(PASS1, "p1_")
        json.dump(out, open(os.path.join(C.OUT, "c_pass1.json"), "w"), indent=1)
    elif which == "pass2":
        out = run(PASS2, "p2_")
        json.dump(out, open(os.path.join(C.OUT, "c_pass2.json"), "w"), indent=1)
