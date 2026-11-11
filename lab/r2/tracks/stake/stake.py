"""Track `stake` (PROTOCOL_V3, Addendum E): stake rules on the trades of the ten validated rules. IN SAMPLE ONLY.

Entries, stops and exits of the ten rules are untouched; only the SIZE of each trade changes. Every trades file is
cut at entry_time < 2022-01-01 right after it is read (`load_trades`); nothing here ever touches 2022+.

THE CLOCK (one clock, the same for the decision and for the accounting)
    FP Markets server time = New York local time + 7 hours (server midnight = 17:00 New York = 23:00 Paris).
    day   = server calendar day;  week = Monday 00:00 to Sunday 24:00 server time;  month = server month.
    A trade's result is booked in the day / week / month of its EXIT time.
    State seen by a trade at its entry time t:
        w  = sum of (stake x R) of the trades whose exit time is STRICTLY before t and falls in the server week of t
        d  = same for the server day of t
        pw = whole booked result of the previous server week (all of it is closed by then)
    in units of the base stake (1.0 = one base risk). Trades still open at t count for nothing (no peeking).
    A result booked in the same minute as an entry is NOT known to that entry (strict "<").

THE STAKE OF A TRADE (multiplier of the base stake), computed in this order from the configuration:
    base  = green_prev_mult if pw > 0 else 1
    boost = max(week catch-up, day catch-up), where a catch-up is
                linear : min(cap - 1, (loss - thr) / k)     once the loss of the week (day) exceeds thr
                step   : cap - 1                            once the loss of the week (day) exceeds thr
            then limited by the family cap (us100 / gold / crypto: famcap - 1) and by the "open boost" budget
            (the boosts of the trades currently open + this one <= open_budget)
    m = base x (1 + boost)
    if w >= wk_lock            : m = m x wk_lock_mult      (0 = no new trade for the rest of the week)
    if 0 < w and prot_k > 0    : m = min(m, max(prot_min, w / prot_k))   ("defend the cushion")
    if d >= dy_lock            : m = m x dy_lock_mult
    if w <= -wk_stop           : m = 0                      (weekly loss stop)
    if d <= -dy_stop           : m = 0                      (daily loss stop)
    A trade with m = 0 is not taken.

THE IDEAL ACCOUNT of the search: no compounding, every trade risks m x (base stake), results add up; all amounts
are in R (= % of the account at a 1 % base stake). Minimum lots, position caps and compounding are in `account()`.

SELECTION (Addendum E, fixed there; the details below were written BEFORE any configuration was run):
    scale     : s = (reference worst week) / (configuration worst week); every amount is multiplied by s.
    eligible  : scaled maximum drawdown <= the reference's.
    rank      : highest share of winning weeks; tie: highest scaled total.
    view      : the selection is made on the trades WITHOUT costs ("gross first"), on the COMMON PERIOD
                2018-02-01 .. 2021-12-31 (the only window where the ten rules all trade; the one Addendum E quotes).
                The three other views (with costs; whole in-sample period 2013-2021) are computed and logged for
                every configuration and the frozen profiles are reported in all four.
    "strong"  : the winner of that rule.
    "soft"    : the winner of the same rule among the configurations that keep, after scaling, at least two thirds
                of the reference's total (gross, common period).
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from numba import njit

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
if LAB not in sys.path:
    sys.path.insert(0, LAB)

OUT = os.path.join(LAB, "results", "r2", "stake")
NET_DIR = os.path.join(LAB, "results", "r2", "recalc", "trades")
GROSS_DIR = os.path.join(OUT, "trades_gross_is")
SLEEVES = [("noise30", "us100"), ("ocm4", "us100"), ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"),
           ("nq_btc_follow", "btcusd"), ("F1_brk_ridge_filter", "btcusd"), ("F1_brk_ridge_filter", "ethusd"),
           ("GOLD_FRI_PM", "xauusd"), ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd")]
FAMILY = {"us100": 0, "xauusd": 1, "btcusd": 2, "ethusd": 2}
FAM_NAMES = ("us100", "gold", "crypto")
IS_END = pd.Timestamp("2022-01-01", tz="UTC")
COMMON_START = pd.Timestamp("2018-02-01", tz="UTC")
PERIODS = ("common", "whole")
KINDS = ("gross", "net")
BIG = 1e18

DEFAULT = dict(
    wk_cap=1.0, wk_k=1.0, wk_thr=0.0, wk_form="linear",      # week catch-up
    dy_cap=1.0, dy_k=1.0, dy_thr=0.0, dy_form="linear",      # day catch-up
    famcap=(BIG, BIG, BIG),                                  # max multiplier per family (us100, gold, crypto)
    open_budget=BIG,                                         # max sum of boosts of the open trades
    wk_lock=BIG, wk_lock_mult=0.0,                           # week profit lock
    prot_k=0.0, prot_min=0.0,                                # defend the cushion when the week is green
    dy_lock=BIG, dy_lock_mult=0.0,                           # day profit lock
    wk_stop=BIG, dy_stop=BIG,                                # loss stops
    green_prev_mult=1.0,                                     # stake after a green week
)

_cache = {}


def server_time(ts):
    """UTC timestamps -> naive FP server time (New York local time + 7 h)."""
    return pd.DatetimeIndex(ts).tz_convert("America/New_York").tz_localize(None) + pd.Timedelta(hours=7)


def build_frame(per_sleeve):
    """{(name, sym): trades DataFrame (columns of results/r2/recalc/trades)} -> one frame sorted by entry time, with
    the columns the engine and the account loop use. Reads no file: the caller decides what period it passes."""
    fr = []
    for (name, sym), t in per_sleeve.items():
        fr.append(pd.DataFrame({
            "sleeve": f"{name}_{sym}", "sym": sym, "fam": FAMILY[sym],
            "t_in": t.entry_time.dt.tz_convert("UTC").astype("datetime64[ns, UTC]").to_numpy(),
            "t_out": t.exit_time.dt.tz_convert("UTC").astype("datetime64[ns, UTC]").to_numpy(),
            "entry": t.entry.to_numpy(float), "risk": t.risk.to_numpy(float), "pnl": t.pnl.to_numpy(float),
            "R": t.R.to_numpy(float)}))
    d = pd.concat(fr, ignore_index=True)
    d["t_in"] = pd.to_datetime(d.t_in, utc=True)
    d["t_out"] = pd.to_datetime(d.t_out, utc=True)
    return d.sort_values(["t_in", "sleeve"], kind="stable").reset_index(drop=True)


def load_trades(kind="net"):
    """All ten sleeves, IN SAMPLE ONLY (entry < 2022-01-01), sorted by entry time."""
    if kind in _cache:
        return _cache[kind]
    per = {}
    for name, sym in SLEEVES:
        t = pd.read_parquet(os.path.join(NET_DIR if kind == "net" else GROSS_DIR, f"{name}__{sym}.parquet"))
        per[(name, sym)] = t[t.entry_time < IS_END]        # the cut comes first, before anything else
    d = build_frame(per)
    assert (d.t_in < IS_END).all()
    _cache[kind] = d
    return d


def prepare(d):
    """Arrays for the engine (server clock)."""
    si, so = server_time(d.t_in), server_time(d.t_out)
    day0 = np.datetime64("1970-01-01")
    dy_in = ((si.values.astype("datetime64[D]") - day0).astype("int64"))
    dy_out = ((so.values.astype("datetime64[D]") - day0).astype("int64"))
    wk_in, wk_out = (dy_in + 3) // 7, (dy_out + 3) // 7       # weeks start on Monday
    d0, w0 = min(dy_in.min(), dy_out.min()), min(wk_in.min(), wk_out.min()) - 1
    a = dict(
        t_in=d.t_in.values.astype("datetime64[ns]").astype("int64"), t_out=d.t_out.values.astype("datetime64[ns]").astype("int64"),
        R=d.R.to_numpy(float).copy(), fam=d.fam.to_numpy("int64"),
        dy_in=dy_in - d0, dy_out=dy_out - d0, wk_in=wk_in - w0, wk_out=wk_out - w0,
        ndy=int(max(dy_in.max(), dy_out.max()) - d0 + 1), nwk=int(max(wk_in.max(), wk_out.max()) - w0 + 1),
        mo_out=(so.year * 12 + so.month - 1).to_numpy("int64"),
        sleeve=d.sleeve.to_numpy(), dow_out=so.dayofweek.to_numpy(),
    )
    a["mo_out"] = a["mo_out"] - a["mo_out"].min()
    a["order_out"] = np.argsort(a["t_out"], kind="stable")
    a["week_monday"] = pd.Timestamp("1970-01-01") + pd.to_timedelta((np.arange(a["nwk"]) + w0) * 7 - 3, unit="D")
    return a


def subset(kind, period):
    d = load_trades(kind)
    if period == "common":
        d = d[d.t_in >= COMMON_START].reset_index(drop=True)
    return d


def params(cfg):
    c = dict(DEFAULT)
    bad = set(cfg) - set(DEFAULT)
    assert not bad, bad
    c.update(cfg)
    p = np.array([c["wk_cap"], c["wk_k"], c["wk_thr"], 1.0 if c["wk_form"] == "step" else 0.0,
                  c["dy_cap"], c["dy_k"], c["dy_thr"], 1.0 if c["dy_form"] == "step" else 0.0,
                  c["open_budget"], c["wk_lock"], c["wk_lock_mult"], c["prot_k"], c["prot_min"],
                  c["dy_lock"], c["dy_lock_mult"], c["wk_stop"], c["dy_stop"], c["green_prev_mult"]], dtype=np.float64)
    return p, np.array(c["famcap"], dtype=np.float64)


@njit(cache=True)
def multiplier(w, d, pw, fam, open_boost, p, famcap):
    """The stake rule itself: (week state, day state, previous week, family, boosts open now) -> (m, boost)."""
    base = p[17] if pw > 0.0 else 1.0
    b = 0.0
    if p[0] > 1.0 and w < -p[2]:
        b = p[0] - 1.0 if p[3] > 0.5 else min(p[0] - 1.0, (-w - p[2]) / p[1])
    if p[4] > 1.0 and d < -p[6]:
        bd = p[4] - 1.0 if p[7] > 0.5 else min(p[4] - 1.0, (-d - p[6]) / p[5])
        if bd > b:
            b = bd
    if b > famcap[fam] - 1.0:
        b = max(0.0, famcap[fam] - 1.0)
    if b > p[8] - open_boost:
        b = max(0.0, p[8] - open_boost)
    m = base * (1.0 + b)
    if w >= p[9]:
        m *= p[10]
    if p[11] > 0.0 and w > 0.0:
        m = min(m, max(p[12], w / p[11]))
    if d >= p[13]:
        m *= p[14]
    if w <= -p[15] or d <= -p[16]:
        m = 0.0
    if m <= 0.0:
        return 0.0, 0.0
    return m, b


@njit(cache=True)
def engine(t_in, t_out, R, wk_in, dy_in, wk_out, dy_out, fam, order_out, nwk, ndy, p, famcap):
    """Replays the trades in entry order. Returns the stake multiplier of every trade (0 = not taken)."""
    n = len(R)
    m = np.zeros(n)
    bo = np.zeros(n)
    wk = np.zeros(nwk)
    dy = np.zeros(ndy)
    j = 0
    open_boost = 0.0
    for i in range(n):
        while j < n and t_out[order_out[j]] < t_in[i]:        # book what closed strictly before this entry
            k = order_out[j]
            j += 1
            if m[k] > 0.0:
                wk[wk_out[k]] += m[k] * R[k]
                dy[dy_out[k]] += m[k] * R[k]
                open_boost -= bo[k]
        m[i], bo[i] = multiplier(wk[wk_in[i]], dy[dy_in[i]], wk[wk_in[i] - 1], fam[i], open_boost, p, famcap)
        open_boost += bo[i]
    return m


def run(a, cfg, R=None):
    p, fc = params(cfg)
    return engine(a["t_in"], a["t_out"], a["R"] if R is None else R, a["wk_in"], a["dy_in"], a["wk_out"], a["dy_out"],
                  a["fam"], a["order_out"], a["nwk"], a["ndy"], p, fc)


def _longest_red(x):
    best = cur = 0
    for v in x:
        cur = cur + 1 if v < 0 else 0
        best = max(best, cur)
    return int(best)


def stats(a, m, R=None):
    """Statistics of one run, in R (= % of the account at a 1 % base stake, no compounding)."""
    R = a["R"] if R is None else R
    r = m * R
    took = m > 0
    dy = np.bincount(a["dy_out"][took], weights=r[took], minlength=a["ndy"])
    dn = np.bincount(a["dy_out"][took], minlength=a["ndy"])
    wk = np.bincount(a["wk_out"][took], weights=r[took], minlength=a["nwk"])
    wn = np.bincount(a["wk_out"][took], minlength=a["nwk"])
    mo = np.bincount(a["mo_out"][took], weights=r[took])
    mn = np.bincount(a["mo_out"][took])
    days, weeks, months = dy[dn > 0], wk[wn > 0], mo[mn > 0]
    first, last = np.nonzero(np.bincount(a["wk_out"], minlength=a["nwk"]))[0][[0, -1]]
    cal_weeks = wk[first:last + 1]                            # every calendar week of the span, traded or not
    o = a["order_out"]
    cum = np.cumsum(r[o])
    dd = float((np.maximum.accumulate(np.r_[0.0, cum]) - np.r_[0.0, cum]).max())
    # stake open at the same time (sum of multipliers of the open trades), measured at each entry
    ev_t = np.r_[a["t_in"][took], a["t_out"][took]]
    ev_v = np.r_[m[took], -m[took]]
    eo = np.lexsort((ev_v, ev_t))                             # exits before entries at the same instant
    open_stake = np.cumsum(ev_v[eo])
    g, b = days[days > 0], days[days < 0]
    return {
        "n_trades": int(took.sum()), "skipped_pct": round(float(100 * (1 - took.mean())), 1),
        "avg_stake": round(float(m[took].mean()), 3), "max_stake": round(float(m.max()), 2),
        "max_open_stake": round(float(open_stake.max()), 2),
        "days": int(len(days)), "win_days_pct": round(float(100 * (days > 0).mean()), 1),
        "weeks": int(len(weeks)), "win_weeks_pct": round(float(100 * (weeks > 0).mean()), 1),
        "weeks_no_trade": int((wn[first:last + 1] == 0).sum()),
        "months": int(len(months)), "win_months_pct": round(float(100 * (months > 0).mean()), 1),
        "total": round(float(r.sum()), 1),
        "avg_green_day": round(float(g.mean()), 3), "avg_red_day": round(float(b.mean()), 3),
        "avg_green_week": round(float(weeks[weeks > 0].mean()), 2), "avg_red_week": round(float(weeks[weeks < 0].mean()), 2),
        "worst_day": round(float(days.min()), 2), "worst_week": round(float(weeks.min()), 2),
        "best_week": round(float(weeks.max()), 2), "worst_month": round(float(months.min()), 2),
        "max_dd": round(dd, 2), "longest_red_weeks": _longest_red(cal_weeks),
    }


AMOUNTS = ("total", "avg_green_day", "avg_red_day", "avg_green_week", "avg_red_week", "worst_day", "worst_week",
           "best_week", "worst_month", "max_dd", "avg_stake", "max_stake", "max_open_stake")


def scaled(st, ref):
    """Addendum E scaling: base stake multiplied by s so that the worst week equals the reference's."""
    s = ref["worst_week"] / st["worst_week"]
    out = {"scale": round(float(s), 3)}
    for k in AMOUNTS:
        out[k] = round(float(st[k] * s), 3)
    out["dd_vs_ref"] = round(float(out["max_dd"] / ref["max_dd"]), 3)
    out["total_vs_ref"] = round(float(out["total"] / ref["total"]), 3)
    out["eligible"] = bool(out["max_dd"] <= ref["max_dd"] + 1e-9)
    return out


_prep = {}


def arrays(kind, period):
    if (kind, period) not in _prep:
        _prep[(kind, period)] = prepare(subset(kind, period))
    return _prep[(kind, period)]


def evaluate(cfg):
    """One configuration in the four views (gross / net x common / whole in-sample), raw and scaled."""
    out = {}
    for kind in KINDS:
        for period in PERIODS:
            a = arrays(kind, period)
            st = stats(a, run(a, cfg))
            ref = stats(a, run(a, {}))
            out[f"{kind}_{period}"] = {"equal_stake": st, "scaled": scaled(st, ref)}
    return out


# ------------------------------------------------------------------ zero-edge control (Addendum E)
@njit(cache=True)
def _zero_stats(m, R, wk_out, dy_out, order_out, nwk, ndy):
    n = len(R)
    wk = np.zeros(nwk)
    wn = np.zeros(nwk)
    dy = np.zeros(ndy)
    dn = np.zeros(ndy)
    cum = 0.0
    peak = 0.0
    dd = 0.0
    low = 0.0
    lowc = 1.0
    eq = 1.0
    for q in range(n):
        k = order_out[q]
        if m[k] <= 0.0:
            continue
        r = m[k] * R[k]
        wk[wk_out[k]] += r
        wn[wk_out[k]] += 1
        dy[dy_out[k]] += r
        dn[dy_out[k]] += 1
        cum += r
        if cum > peak:
            peak = cum
        if peak - cum > dd:
            dd = peak - cum
        if cum < low:
            low = cum
    nw = 0
    ww = 0
    worst_w = 0.0
    for i in range(nwk):
        if wn[i] > 0:
            nw += 1
            if wk[i] > 0:
                ww += 1
            if wk[i] < worst_w:
                worst_w = wk[i]
    nd = 0
    wd = 0
    worst_d = 0.0
    for i in range(ndy):
        if dn[i] > 0:
            nd += 1
            if dy[i] > 0:
                wd += 1
            if dy[i] < worst_d:
                worst_d = dy[i]
    return 100.0 * ww / nw, 100.0 * wd / nd, worst_w, worst_d, cum, dd, low


def zero_edge(cfg, kind="net", period="common", n=1000, seed=20261111, base_pct=(1.0,), block=False, shuffle=False):
    """The same stake rule on the same trades, each trade's result replaced by a draw WITHOUT edge: the trade's own
    R minus its sleeve's mean, with a random sign (Addendum E, literal). `block=True` is a harsher variant: one sign
    per family and server day of entry (the trades of one family entered the same day keep their link).
    `shuffle=True` is a second reading of "no edge": no sign flip (a flipped +8 R winner becomes a -8 R loss that the
    stops never allow), instead every trade receives the result, minus the sleeve's mean, of another trade of the
    same sleeve drawn at random with replacement: the shape of the results is kept (losses stopped near -1 R, long
    winners), their mean is zero and their order in time is destroyed.
    P(lose half) = share of the draws whose cumulated result (no compounding) falls to -50 % of the starting
    account at any time of the period, for a base stake of `base_pct` % (a tuple: one probability per value)."""
    a = arrays(kind, period)
    R0 = a["R"].copy()
    for s in np.unique(a["sleeve"]):
        k = a["sleeve"] == s
        R0[k] -= R0[k].mean()
    rng = np.random.default_rng(seed)
    grp = None
    if block:
        key = a["fam"] * 100000 + a["dy_in"]
        _, grp = np.unique(key, return_inverse=True)
    sl_idx = [np.nonzero(a["sleeve"] == s)[0] for s in np.unique(a["sleeve"])]
    res = np.zeros((n, 7))
    for q in range(n):
        if shuffle:
            Rz = R0.copy()
            for k in sl_idx:
                Rz[k] = R0[k][rng.integers(0, len(k), len(k))]
        elif block:
            Rz = R0 * rng.choice(np.array([-1.0, 1.0]), size=grp.max() + 1)[grp]
        else:
            Rz = R0 * rng.choice(np.array([-1.0, 1.0]), size=len(R0))
        m = run(a, cfg, Rz)
        res[q] = _zero_stats(m, Rz, a["wk_out"], a["dy_out"], a["order_out"], a["nwk"], a["ndy"])
    f = lambda x: round(float(x), 2)
    out = {"draws": n, "kind": kind, "period": period, "draw": "shuffle within sleeve" if shuffle else ("one random sign per family and day" if block else "random sign per trade"),
           "win_weeks_pct": {"mean": f(res[:, 0].mean()), "p05": f(np.percentile(res[:, 0], 5)), "p95": f(np.percentile(res[:, 0], 95))},
           "win_days_pct": {"mean": f(res[:, 1].mean()), "p05": f(np.percentile(res[:, 1], 5)), "p95": f(np.percentile(res[:, 1], 95))},
           "worst_week": {"median": f(np.median(res[:, 2])), "p05": f(np.percentile(res[:, 2], 5)), "min": f(res[:, 2].min())},
           "worst_day": {"median": f(np.median(res[:, 3])), "p05": f(np.percentile(res[:, 3], 5)), "min": f(res[:, 3].min())},
           "total": {"mean": f(res[:, 4].mean()), "median": f(np.median(res[:, 4])), "p05": f(np.percentile(res[:, 4], 5)),
                     "p95": f(np.percentile(res[:, 4], 95))},
           "max_dd": {"median": f(np.median(res[:, 5])), "p95": f(np.percentile(res[:, 5], 95)), "max": f(res[:, 5].max())},
           "p_lose_half_pct": {f"{b:g}": f(100 * (res[:, 6] * b <= -50.0).mean()) for b in base_pct}}
    return out


# ------------------------------------------------------------------ configurations (append-only: the trial log)
def _c(**kw):
    return kw


CONFIGS = [
    # --- the seven of the first scout (re-run and logged first)
    ("01_reference", _c()),
    ("02_day_catch_cap2", _c(dy_cap=2.0)),
    ("03_day_catch_cap3", _c(dy_cap=3.0)),
    ("04_day_catch_cap5", _c(dy_cap=5.0)),
    ("05_day_catch_cap3_daylock0.5", _c(dy_cap=3.0, dy_lock=0.5)),
    ("06_week_catch_cap3", _c(wk_cap=3.0)),
    ("07_week_catch_cap3_weeklock2", _c(wk_cap=3.0, wk_lock=2.0)),
    # --- batch 2: the catch-up formula within the week, a weekly loss stop, a lock alone, the cushion alone
    ("08_week_step_cap2", _c(wk_cap=2.0, wk_form="step")),
    ("09_week_step_cap3", _c(wk_cap=3.0, wk_form="step")),
    ("10_week_lin_cap3_k3", _c(wk_cap=3.0, wk_k=3.0)),
    ("11_week_lin_cap5_k1", _c(wk_cap=5.0)),
    ("12_week_lin_cap2_k1", _c(wk_cap=2.0)),
    ("13_week_cap3_stop8", _c(wk_cap=3.0, wk_stop=8.0)),
    ("14_week_cap3_stop12", _c(wk_cap=3.0, wk_stop=12.0)),
    ("15_weeklock3_alone", _c(wk_lock=3.0)),
    ("16_cushion_k2_min0.25_alone", _c(prot_k=2.0, prot_min=0.25)),
    # --- batch 3: catch-up + cushion, families (crypto correlation), open-boost budget, stake after a green week
    ("17_week_cap3_cushion_k2_min0.25", _c(wk_cap=3.0, prot_k=2.0, prot_min=0.25)),
    ("18_week_cap3_cushion_k4_min0.25", _c(wk_cap=3.0, prot_k=4.0, prot_min=0.25)),
    ("19_week_cap3_cushion_k2_min0.1", _c(wk_cap=3.0, prot_k=2.0, prot_min=0.1)),
    ("20_week_cap2_cushion_k2_min0.25", _c(wk_cap=2.0, prot_k=2.0, prot_min=0.25)),
    ("21_week_cap3_cushion_k2_green0.5", _c(wk_cap=3.0, prot_k=2.0, prot_min=0.25, green_prev_mult=0.5)),
    ("22_week_cap3_not_on_crypto", _c(wk_cap=3.0, famcap=(BIG, BIG, 1.0))),
    ("23_week_cap3_crypto_only", _c(wk_cap=3.0, famcap=(1.0, 1.0, BIG))),
    ("24_week_cap3_open_budget2", _c(wk_cap=3.0, open_budget=2.0)),
    # --- batch 4: stake after a green week alone, wider cushion, cap 5, families + cushion, day rules on top
    ("25_green_prev0.5_alone", _c(green_prev_mult=0.5)),
    ("26_week_cap3_cushion_k6_min0.25", _c(wk_cap=3.0, prot_k=6.0, prot_min=0.25)),
    ("27_week_cap5_cushion_k4_min0.25", _c(wk_cap=5.0, prot_k=4.0, prot_min=0.25)),
    ("28_week_cap3_crypto_only_cushion_k4", _c(wk_cap=3.0, famcap=(1.0, 1.0, BIG), prot_k=4.0, prot_min=0.25)),
    ("29_week_cap3_not_on_gold_cushion_k4", _c(wk_cap=3.0, famcap=(BIG, 1.0, BIG), prot_k=4.0, prot_min=0.25)),
    ("30_week_cap3_crypto_cap2_others_cushion_k4", _c(wk_cap=3.0, famcap=(2.0, 2.0, 3.0), prot_k=4.0, prot_min=0.25)),
    ("31_week_cap3_cushion_k4_day_catch_cap3", _c(wk_cap=3.0, prot_k=4.0, prot_min=0.25, dy_cap=3.0)),
    ("32_day_step_cap5_daylock0.01", _c(dy_cap=5.0, dy_form="step", dy_lock=0.01)),
    # --- batch 5: the cushion alone (stake never above the base), crypto-only caps, cap 5 without gold
    ("33_cushion_k4_min0.25_alone", _c(prot_k=4.0, prot_min=0.25)),
    ("34_week_cap5_crypto_only_cushion_k4", _c(wk_cap=5.0, famcap=(1.0, 1.0, BIG), prot_k=4.0, prot_min=0.25)),
    ("35_week_cap2_crypto_only_cushion_k4", _c(wk_cap=2.0, famcap=(1.0, 1.0, BIG), prot_k=4.0, prot_min=0.25)),
    ("36_week_crypto_cap5_us100_cap3_cushion_k4", _c(wk_cap=5.0, famcap=(3.0, 1.0, 5.0), prot_k=4.0, prot_min=0.25)),
    ("37_week_cap5_not_on_gold_cushion_k4", _c(wk_cap=5.0, famcap=(BIG, 1.0, BIG), prot_k=4.0, prot_min=0.25)),
    # --- batch 6: between "crypto only" and "not on gold"; a cushion that never goes below half the base stake
    ("38_week_crypto_cap3_us100_cap2_cushion_k4", _c(wk_cap=3.0, famcap=(2.0, 1.0, 3.0), prot_k=4.0, prot_min=0.25)),
    ("39_week_cap3_crypto_only_cushion_k4_min0.5", _c(wk_cap=3.0, famcap=(1.0, 1.0, BIG), prot_k=4.0, prot_min=0.5)),
]

# The two frozen profiles (selection: see the module docstring; made by run.py `select`, on trials 1-39).
# base_scale = the base stake as a multiple of the reference's base stake: the SMALLEST of the four Addendum-E
# scales (gross / net x common / whole in-sample period), rounded down to 0.01, so that the in-sample worst week
# is no larger than the reference's in any of the four views.
FROZEN = {
    "soft": {"trial": 28, "name": "28_week_cap3_crypto_only_cushion_k4", "base_scale": 0.58,
             "config": _c(wk_cap=3.0, famcap=(1.0, 1.0, BIG), prot_k=4.0, prot_min=0.25)},
    "strong": {"trial": 36, "name": "36_week_crypto_cap5_us100_cap3_cushion_k4", "base_scale": 0.39,
               "config": _c(wk_cap=5.0, famcap=(3.0, 1.0, 5.0), prot_k=4.0, prot_min=0.25)},
}
# Not frozen, kept for the report: the cushion alone (trial 33), the only rule whose stake never exceeds the base.
INFO_ONLY = {"cushion_only": {"trial": 33, "name": "33_cushion_k4_min0.25_alone", "base_scale": 1.0,
                              "config": _c(prot_k=4.0, prot_min=0.25)}}


def log_trials(path=None, only=None):
    """Evaluates every configuration of CONFIGS in order and rewrites the trial log."""
    path = path or os.path.join(OUT, "trials.jsonl")
    rows = []
    for i, (name, cfg) in enumerate(CONFIGS, 1):
        rows.append({"trial": i, "name": name, "config": cfg, "is": evaluate(cfg)})
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return rows
