"""Synthetic tests of night_fade (PROTOCOL_V3 Addendum L) with KNOWN answers. No market data is read.

World A (scenario frame): one cross, minutes from Sunday 2018-10-28 17:00 to Friday 2019-04-26 17:00 New York
(weekday rule), mid 1.5 everywhere, spread 2u, minute half-range 40u, u = 2**-14 (every price, sum and band below is
exactly representable). Scenarios are planted on single evenings (New York times), each with its expected decision
statuses and trades derived by hand (fills, exits and R from the engine's stated rules):
  bands and the span rule, strict band crossing (sigma = 0 and an exact equality close == lower band), D, C and the
  cost filter (D == 2C kept, D < 2C dropped), entry timing (5 minutes late kept, 6 dropped), the refused target (buy and
  sell), a dropped order not blocking later signals, target on a later bar and on the entry bar, stop first when stop
  and target are in one bar, gap opens through the stop and through the target, time exit at 21:00 with a 30-minute and
  a 31-minute gap, one position per cross (an order on the exit bar skipped; later signals on either side), moving_mid
  (non-strict >= on its own middle band; capped at 21:00), m15 decisions, one_per_night, first_hour, stop_3.0, width_2.5,
  DST evenings in both regimes, NYSE holidays, 24 Dec - 1 Jan, the special closure 2018-12-05 (a normal day), warm-up,
  costs x1.5 readings (a) and (b) (a cost-filter drop in a, a fill past the target in b), the gross reading, the swap
  and time-window assertions, and an independent band / H1 reference for every decision of the frame.
World B: the frame builder on synthetic raw csv.gz files (filter < 2022 in the read, flat, zero-volume, crossed and
weekday rules) and the commission fold.
World C: twelve noisy synthetic crosses through run.run_all (91 trials lines, refuses to run twice, subset invariants),
null.null_all / replay_orders (mechanics, reproducibility, 20-draw drops), correlation.correlate and verdict.verdict_all.
World D: every bar judged on the unrounded figure (exact figures on one side of a threshold, display values on the other).
World E: moving_mid on noisy frames with planted quote holes (the exit is the first M1 bar at or after the trigger end).
Review fixes proven here: R6-1 (moving_mid exit without a gap rule: world A 2019-02-06, worlds C and E), R6-2 (bars on
unrounded figures: world D, world C verdict), R6-3 (reading a's gross and cost bp from its own orders: worlds A and C),
R6-4 (declared L18: mid closes equal, H1 ranges recomputed on the x1.5 frame: world A), R6-5 (write order of the run:
world C), R6-6 (exits by kind, moving_mid exits apart from 21:00 exits: worlds A and C).
Output: results/r2/round6/night_fade/synthetic.json

    python3 -I test_synthetic.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

import gzip  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

U = 2.0 ** -14
M = 1.5
A = 40 * U
S0 = 2 * U
NS_H = 3_600 * 10**9
NS_5 = 300 * 10**9
SCR = "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/round6_build/synthetic"
SL_M = 0.1 * 1e-4                     # the engine's market slippage factor at base costs (sim.py: slip_mkt_bps * 1e-4)
SL_S = 0.3 * 1e-4
SL_M15 = (0.1 * 1.5) * 1e-4
SL_S15 = (0.3 * 1.5) * 1e-4
CHECKS = {}


def check(name, cond, detail=None):
    CHECKS[name] = {"pass": bool(cond)} if detail is None else {"pass": bool(cond), "detail": detail}
    print(("PASS " if cond else "FAIL ") + name + ("" if cond or detail is None else f"   {detail}"), flush=True)


def ny_ns(day, hhmm):
    return int(C.ny_utc_ns(pd.DatetimeIndex([pd.Timestamp(day)]), hhmm)[0])


def ny_ts(day, hhmm):
    return pd.Timestamp(ny_ns(day, hhmm), unit="ns", tz="UTC")


# ============================================================================================ world A
class Syn:
    """Minute frame with planted mid open / close / high / low and spread."""

    def __init__(self, start="2018-10-28 21:00", end="2019-04-26 21:00"):
        utc = pd.date_range(start, end, freq="min", tz="UTC", inclusive="left").as_unit("ns")
        ny = utc.tz_convert(C.NY)
        self.idx = utc[(ny + pd.Timedelta(hours=7)).dayofweek < 5]
        n = len(self.idx)
        self.o, self.c = np.full(n, M), np.full(n, M)
        self.h, self.l = np.full(n, M + A), np.full(n, M - A)
        self.s = np.full(n, S0)
        self.keep = np.ones(n, bool)
        self.pos = {int(t): i for i, t in enumerate(self.idx.asi8)}

    def i(self, day, hhmm):
        return self.pos[ny_ns(day, hhmm)]

    def bar(self, day, hhmm, o, c, h=None, l=None, s=None, amp=U):
        i = self.i(day, hhmm)
        self.o[i], self.c[i] = o, c
        self.h[i] = max(o, c) + amp if h is None else h
        self.l[i] = min(o, c) - amp if l is None else l
        if s is not None:
            self.s[i] = s

    def level(self, day, h0, h1, lv, amp=U):
        a, b = self.i(day, h0), self.i(day, h1)
        self.o[a:b] = lv
        self.c[a:b] = lv
        self.h[a:b] = lv + amp
        self.l[a:b] = lv - amp

    def hole(self, day, h0, h1):
        self.keep[self.i(day, h0):self.i(day, h1)] = False

    def frame(self):
        half = self.s / 2
        df = pd.DataFrame({"bo": self.o - half, "bh": self.h - half, "bl": self.l - half, "bc": self.c - half,
                           "ao": self.o + half, "ah": self.h + half, "al": self.l + half, "ac": self.c + half},
                          index=self.idx)[self.keep]
        df.index.name = "ts"
        return df[C.COLS]


def spike_buy(sy, d, plateau=M - 10 * U, until="21:05", s=None):
    """Buy signal at 17:15: bucket [17:10,17:15) closes at M - 20u (mu = M - u, D = 19u); entry bar 17:15 opens at
    M - 20u (ask open M - 19u < mu) and closes at the plateau, kept from 17:16 to `until`."""
    sy.bar(d, "17:14", M, M - 20 * U, s=s)
    sy.bar(d, "17:15", M - 20 * U, plateau)
    sy.level(d, "17:16", until, plateau)


def build_world_a():
    sy = Syn()
    P10 = M - 10 * U
    # SA: target on a later bar (17:30)
    spike_buy(sy, "2018-11-27")
    sy.bar("2018-11-27", "17:30", P10, P10, h=M + U)
    # SB: target on the entry bar
    sy.bar("2018-11-28", "17:14", M, M - 20 * U)
    sy.bar("2018-11-28", "17:15", M - 20 * U, P10, h=M + U, l=M - 21 * U)
    sy.level("2018-11-28", "17:16", "21:05", P10)
    # SC: stop and target in one bar (17:40): stop first
    spike_buy(sy, "2018-11-29")
    sy.bar("2018-11-29", "17:40", P10, P10, h=M + U, l=M - 400 * U)
    # SD: gap open through the stop (18:00)
    spike_buy(sy, "2018-12-03")
    sy.bar("2018-12-03", "18:00", M - 400 * U, P10)
    # SE: gap open through the target (18:10); E+1 = 2018-12-05, the special closure, is a normal day
    spike_buy(sy, "2018-12-04")
    sy.bar("2018-12-04", "18:10", M + 30 * U, P10)
    # SF: time exit at 21:00 (on the special closure day itself)
    spike_buy(sy, "2018-12-05")
    # SG: no bar in [21:00, 21:30): exit at 21:30
    spike_buy(sy, "2018-12-06", until="21:35")
    sy.hole("2018-12-06", "21:00", "21:30")
    # SH: no bar in [21:00, 21:31): exit at the last bar before (20:59)
    spike_buy(sy, "2018-12-10")
    sy.hole("2018-12-10", "21:00", "21:31")
    # SI: one position per cross, later signals on either side
    d = "2018-12-11"
    P40 = M - 40 * U
    sy.bar(d, "17:14", M, M - 20 * U)
    sy.bar(d, "17:15", M - 20 * U, P40)
    sy.level(d, "17:16", "18:54", P40)
    sy.bar(d, "18:54", P40, M - 25 * U)
    sy.bar(d, "18:55", M - 25 * U, P40)
    sy.level(d, "18:56", "19:44", P40)
    sy.bar(d, "19:20", P40, P40, h=M + U)
    sy.bar(d, "19:44", P40, M - 20 * U)
    sy.bar(d, "19:45", M - 20 * U, M - 20 * U)
    sy.level(d, "19:46", "21:05", M - 20 * U)
    sy.bar(d, "20:30", M - 20 * U, M - 20 * U, l=M - 40 * U)
    # SJ: an order whose entry bar is the open trade's exit bar is skipped; the next one trades
    d = "2018-12-12"
    sy.bar(d, "17:14", M, M - 20 * U)
    sy.bar(d, "17:15", M - 20 * U, P40)
    sy.level(d, "17:16", "21:05", P40)
    sy.bar(d, "17:20", P40, P40, h=M + U)
    # SK: entry exactly 5 minutes late (kept)
    d = "2018-12-13"
    sy.bar(d, "17:14", M, M - 20 * U)
    sy.hole(d, "17:15", "17:20")
    sy.bar(d, "17:20", M - 20 * U, P10)
    sy.level(d, "17:21", "21:05", P10)
    # SL: entry 6 minutes late (dropped); a later signal trades
    d = "2018-12-17"
    P15 = M - 15 * U
    sy.bar(d, "17:14", M, M - 20 * U)
    sy.hole(d, "17:15", "17:21")
    sy.bar(d, "17:34", M, M - 30 * U)
    sy.bar(d, "17:35", M - 30 * U, P15)
    sy.level(d, "17:36", "21:05", P15)
    # SM: buy refused (ask open >= mu); a later signal trades
    d = "2018-12-18"
    sy.bar(d, "17:14", M, M - 20 * U)
    sy.bar(d, "17:15", M, M)
    sy.bar(d, "17:39", M, M - 30 * U)
    sy.bar(d, "17:40", M - 30 * U, P15)
    sy.level(d, "17:41", "21:05", P15)
    # SN: sell refused (bid open <= mu)
    d = "2018-12-19"
    sy.bar(d, "17:14", M, M + 20 * U)
    sy.bar(d, "17:15", M, M)
    # SO: D == 2C exactly (kept); SP: D < 2C (dropped)
    spike_buy(sy, "2018-12-20", s=9.5 * U)
    spike_buy(sy, "2019-01-02", s=9.5 * U + 2.0 ** -20)
    # SQ: 4 empty buckets in the window (span 120: usable); SR: 5 (span 125: not usable until the hole leaves)
    spike_buy(sy, "2019-01-03")
    sy.hole("2019-01-03", "16:00", "16:20")
    d = "2019-01-07"
    sy.bar(d, "17:14", M, M - 20 * U)
    sy.hole(d, "16:00", "16:25")
    # SS: close exactly on the lower band (no signal); ST: one unit below (buy)
    for d, last, s in (("2019-01-08", M - 8 * U, None), ("2019-01-09", M - 9 * U, 0.5 * U)):
        sy.level(d, "15:35", "15:50", M - 8 * U)
        sy.level(d, "15:50", "17:10", M - 7 * U)
        sy.level(d, "17:10", "17:14", M - 8 * U)
        sy.bar(d, "17:14", M - 8 * U, last, s=s)
        if d == "2019-01-08":
            sy.level(d, "17:15", "21:05", M - 7 * U)
        else:
            sy.bar(d, "17:15", M - 9 * U, M - 9 * U)
            sy.level(d, "17:16", "21:05", M - 9 * U)
    # SW25: a crossing between 2.0 and 2.5 sigma (3 closes at -20u, 16 at -10u, signal -22u: z = 2.35)
    d = "2019-01-22"
    sy.level(d, "15:35", "15:50", M - 20 * U)
    sy.level(d, "15:50", "17:10", M - 10 * U)
    sy.level(d, "17:10", "17:14", M - 20 * U)
    sy.bar(d, "17:14", M - 20 * U, M - 22 * U)
    sy.bar(d, "17:15", M - 22 * U, M - 22 * U)
    sy.level(d, "17:16", "21:05", M - 22 * U)
    # m15 (also main) evening
    spike_buy(sy, "2019-01-10")
    # SMM: moving_mid exit at 17:45 (main: target at 17:44)
    d = "2019-01-14"
    sy.bar(d, "17:14", M, M - 20 * U)
    sy.bar(d, "17:15", M - 20 * U, P10)
    sy.level(d, "17:16", "17:44", P10)
    sy.bar(d, "17:44", P10, M, h=M + U, l=M - 11 * U)
    # SGAP (review R6-1): buy at 17:15; the bucket [18:00,18:05) closes at M, above its own middle band M - 5.5u, and
    # no quote follows until 18:40 (35 minutes). moving_mid exits at the 18:40 open (the first M1 bar at or after
    # 18:05), never at the 18:04 open (which the 30-minute gap rule would pick, before the trigger close exists). The
    # main's resting target is hit at the 18:04 open (gap through it: M + 29u).
    d = "2019-02-06"
    spike_buy(sy, d)
    sy.bar(d, "18:04", M + 30 * U, M)
    sy.hole(d, "18:05", "18:40")
    # SV: a falling drift: moving_mid never triggers, capped at 21:00
    d = "2019-01-15"
    sy.bar(d, "17:14", M, M - 20 * U)
    sy.bar(d, "17:15", M - 20 * U, P10)
    for b in range(0, 47):
        t0 = (pd.Timestamp("2000-01-01 17:15") + pd.Timedelta(minutes=5 * b)).strftime("%H:%M")
        t1 = (pd.Timestamp("2000-01-01 17:15") + pd.Timedelta(minutes=5 * b + 5)).strftime("%H:%M")
        if b == 0:
            sy.level(d, "17:16", t1, P10)
        else:
            sy.level(d, t0, t1, M - (10 + b) * U)
    # SY: base D/C = 2.53 (kept); costs x1.5 rebuilt: 1.69 (dropped)
    spike_buy(sy, "2019-01-16", s=7.5 * U)
    # SZ: x1.5 widened ask open reaches the target: refused in a, fill past the target in b
    d = "2019-01-17"
    sy.bar(d, "17:14", M, M - 20 * U)
    sy.bar(d, "17:15", M - 3.5 * U, P10, s=4 * U)
    sy.level(d, "17:16", "21:05", P10)
    # DST: winter (EST) and summer (EDT) evenings
    spike_buy(sy, "2019-03-07")
    spike_buy(sy, "2019-03-11")
    # planted on evenings that must not trade: warm-up, Christmas-New Year, MLK, Presidents' day, E+1 = Good Friday
    for d in ("2018-11-20", "2018-12-26", "2019-01-01", "2019-01-21", "2019-02-18", "2019-04-18"):
        spike_buy(sy, d)
    return sy


def ref_buckets(df):
    """Independent M5 buckets: id -> (mid close of the last minute, ask close - bid close of it)."""
    ns = df.index.as_unit("ns").asi8
    b = ns // NS_5
    last = np.r_[b[1:] != b[:-1], True]
    ids = b[last]
    mid = ((df.bc.to_numpy() + df.ac.to_numpy()) / 2)[last]
    cc = (df.ac.to_numpy() - df.bc.to_numpy())[last]
    return ids, mid, cc


def ref_band(ids, mid, cc, t, k=2.0, span=120, minutes=5):
    """Independent band at decision t (ns): plain loops over the 20 existing buckets ending at the signal bucket."""
    if minutes != 5:
        raise ValueError
    bid = (t - NS_5) // NS_5
    j = int(np.searchsorted(ids, bid))
    if j >= len(ids) or ids[j] != bid:
        return {"has_bar": False}
    if j < 19 or ids[j - 19] * NS_5 < (bid * NS_5 + NS_5) - span * 60 * 10**9:
        return {"has_bar": True, "usable": False}
    xs = [float(x) for x in mid[j - 19:j + 1]]
    s = 0.0
    for x in xs:
        s += x
    mu = s / 20
    v = 0.0
    for x in xs:
        v += (x - mu) * (x - mu)
    sd = float(np.sqrt(v / 20))
    close = xs[-1]
    side = 1 if close < mu - k * sd else (-1 if close > mu + k * sd else 0)
    return {"has_bar": True, "usable": True, "mu": mu, "sigma": sd, "close": close, "C": float(cc[j]), "side": side,
            "D": abs(close - mu)}


def ref_stop_dist(df, t, mult=2.0, n=480):
    """Independent mean H1 range: UTC hours by integer division, mid high/low, hours ended by t, last n, plain mean."""
    ns = df.index.as_unit("ns").asi8
    hr = ns // NS_H
    g = pd.DataFrame({"hr": hr, "bh": df.bh.to_numpy(), "ah": df.ah.to_numpy(), "bl": df.bl.to_numpy(),
                      "al": df.al.to_numpy()}).groupby("hr")
    rng = ((g.bh.max() + g.ah.max()) / 2) - ((g.bl.min() + g.al.min()) / 2)
    rng = rng[(rng.index.to_numpy() + 1) * NS_H <= t]
    w = rng.to_numpy()[-n:]
    assert len(w) == n
    s = 0.0
    for x in w:
        s += float(x)
    return mult * (s / n)


def trade_on(t, d):
    return t[pd.DatetimeIndex(t.evening) == pd.Timestamp(d)].sort_values("entry_time").reset_index(drop=True)


def world_a():
    sy = build_world_a()
    df = sy.frame()
    C.assert_is(df)
    bk = C.Book(df, "eurcad")
    P = {c["name"]: c["params"] for c in C.CONFIGS}
    cal = C.calendar().set_index("evening").status
    check("A calendar: 2018-12-26 Christmas-New Year, 2019-01-21 holiday on E, 2019-04-18 holiday on E+1 (Good Friday), "
          "2018-12-04 and 2018-12-05 normal (special closure removed)",
          cal[pd.Timestamp("2018-12-26")] == "christmas_new_year" and cal[pd.Timestamp("2019-01-01")] == "christmas_new_year"
          and cal[pd.Timestamp("2019-01-21")] == "holiday_on_E" and cal[pd.Timestamp("2019-02-18")] == "holiday_on_E"
          and cal[pd.Timestamp("2019-04-18")] == "holiday_on_E_plus_1" and cal[pd.Timestamp("2018-12-04")] == "ok"
          and cal[pd.Timestamp("2018-12-05")] == "ok" and cal[pd.Timestamp("2018-11-21")] == "holiday_on_E_plus_1")
    Et = bk.tradable(480)
    in_frame = Et[(Et >= pd.Timestamp("2018-10-28")) & (Et <= pd.Timestamp("2019-04-26"))]
    check("A warm-up: first tradable evening 2018-11-26 (504 completed H1 bars; 2018-11-20 has 408)",
          str(in_frame[0].date()) == "2018-11-26" and pd.Timestamp("2018-11-20") not in Et)
    check("A skipped evenings absent from the tradable list",
          all(pd.Timestamp(d) not in Et for d in ("2018-11-20", "2018-12-26", "2019-01-01", "2019-01-21", "2019-02-18",
                                                  "2019-04-18", "2018-11-22", "2018-11-21")))
    tb = C.decision_table(bk, P["main"])
    tb = tb[(tb.evening >= pd.Timestamp("2018-11-26")) & (tb.evening <= pd.Timestamp("2019-04-25"))].reset_index(drop=True)
    row = lambda d, k: tb[(tb.evening == pd.Timestamp(d)) & (tb.k == k)].iloc[0]  # noqa: E731
    st = lambda d, k: C.STATUS[int(row(d, k).status)]  # noqa: E731
    # ---------- independent reference for every decision
    ids, mid, cc = ref_buckets(df)
    bad = []
    for r in tb.itertuples():
        ref = ref_band(ids, mid, cc, int(r.dec_ns))
        if not ref["has_bar"]:
            ok = not r.has_bar
        elif not ref["usable"]:
            ok = r.has_bar and not r.usable
        else:
            ok = (r.usable and r.mu == ref["mu"] and r.sigma == ref["sigma"] and r.close == ref["close"] and r.C == ref["C"]
                  and r.side == ref["side"] and r.D == ref["D"])
        if not ok:
            bad.append((str(r.evening.date()), int(r.k)))
    check(f"A bands, signals, D and C equal an independent reference on all {len(tb)} decisions (exact)", not bad, bad[:5])
    # ---------- statuses
    q = tb[tb.evening == pd.Timestamp("2018-11-26")]
    check("A sigma = 0 (all closes equal): no signal on any of the 33 decisions (strict crossing)",
          len(q) == 33 and (q.status == C.ST_INSIDE).all() and (q.sigma == 0).all())
    r = row("2018-11-27", 0)
    check("A SA decision 17:15: mu = M - u, D = 19u, C = 2u exactly, buy, order",
          r.mu == M - U and r.D == 19 * U and r.C == 2 * U and r.side == 1 and r.status == C.ST_ORDER)
    r = row("2019-01-08", 0)
    exact = r.close == r.mu - 2.0 * r.sigma
    check("A SS close exactly on the lower band (construction exact) -> no signal (strict)",
          exact and r.status == C.ST_INSIDE, {"close": r.close, "lower": r.mu - 2 * r.sigma})
    r = row("2019-01-09", 0)
    check("A ST one unit below the lower band -> buy, D = 1.75u, C = 0.5u, order",
          r.side == 1 and r.D == 1.75 * U and r.C == 0.5 * U and r.status == C.ST_ORDER)
    r = row("2018-12-20", 0)
    check("A SO D == 2C exactly -> kept", r.D == 2 * r.C and r.D == 19 * U and r.status == C.ST_ORDER)
    r = row("2019-01-02", 0)
    check("A SP D < 2C -> dropped by the cost filter", r.D < 2 * r.C and r.status == C.ST_COST)
    check("A SQ span exactly 120 min (4 empty buckets) -> usable, order", st("2019-01-03", 0) == "order")
    check("A SR span 125 min (5 empty buckets) -> band not usable at 17:15-18:00, usable from 18:05",
          all(st("2019-01-07", k) == "band_not_usable" for k in range(10)) and st("2019-01-07", 10) == "no_band_crossing"
          and row("2019-01-07", 0).has_bar)
    r = row("2018-12-13", 0)
    check("A SK entry exactly 5 minutes late -> kept (entry bar 17:20)",
          r.status == C.ST_ORDER and r.entry_delay_min == 5.0 and st("2018-12-13", 1) == "no_signal_bar")
    check("A SL entry 6 minutes late -> dropped; the 17:35 signal still becomes an order",
          st("2018-12-17", 0) == "entry_late_over_5min" and row("2018-12-17", 0).side == 1 and st("2018-12-17", 4) == "order")
    check("A SM buy refused (ask open >= mu); the 17:40 signal still becomes an order",
          st("2018-12-18", 0) == "open_already_at_target" and st("2018-12-18", 5) == "order")
    check("A SN sell refused (bid open <= mu)", st("2018-12-19", 0) == "open_already_at_target" and row("2018-12-19", 0).side == -1)
    # ---------- stop distance = independent mean H1 range
    worst = 0.0
    for r in tb[tb.status == C.ST_ORDER].itertuples():
        worst = max(worst, abs(r.stop_dist - ref_stop_dist(df, int(r.dec_ns))))
    check("A stop distance = 2 x independent mean range of the 480 completed H1 bars at the decision (exact)", worst == 0.0, worst)
    # ---------- trades of the main
    o, _ = C.make_orders(bk, P["main"])
    t = C.run_orders(bk, o, C.costs(P["main"]))
    stop_of = lambda d, k: ref_stop_dist(df, ny_ns(d, "17:15") + k * NS_5)  # noqa: E731
    exp = []
    fill = (M - 19 * U) * (1 + SL_M)

    def add(d, k, side, entry_hm, fill_, reason, exit_hm, xpx, mult=2.0):
        sd_ = mult / 2.0 * stop_of(d, k)
        stop = fill_ - side * sd_
        exp.append({"evening": d, "side": side, "entry": ny_ts(d, entry_hm), "fill": fill_, "stop": stop, "reason": reason,
                    "exit": ny_ts(d, exit_hm), "xpx": xpx, "R": side * (xpx - fill_) / abs(fill_ - stop)})
    add("2018-11-27", 0, 1, "17:15", fill, "target", "17:31", M - U)
    add("2018-11-28", 0, 1, "17:15", fill, "target", "17:16", M - U)
    sc_stop = fill - stop_of("2018-11-29", 0)
    add("2018-11-29", 0, 1, "17:15", fill, "stop", "17:41", sc_stop * (1 - SL_S))
    add("2018-12-03", 0, 1, "17:15", fill, "stop", "18:01", (M - 401 * U) * (1 - SL_S))
    add("2018-12-04", 0, 1, "17:15", fill, "target", "18:11", M + 29 * U)
    add("2018-12-05", 0, 1, "17:15", fill, "time", "21:00", (M - 11 * U) * (1 - SL_M))
    add("2018-12-06", 0, 1, "17:15", fill, "time", "21:30", (M - 11 * U) * (1 - SL_M))
    add("2018-12-10", 0, 1, "17:15", fill, "time", "20:59", (M - 11 * U) * (1 - SL_M))
    add("2018-12-11", 0, 1, "17:15", fill, "target", "19:21", M - U)
    add("2018-12-11", 26, -1, "19:45", (M - 21 * U) * (1 - SL_M), "target", "20:31", M - 38.25 * U)
    add("2018-12-12", 0, 1, "17:15", fill, "target", "17:21", M - U)
    add("2018-12-12", 2, 1, "17:25", (M - 39 * U) * (1 + SL_M), "time", "21:00", (M - 41 * U) * (1 - SL_M))
    add("2018-12-13", 0, 1, "17:20", fill, "time", "21:00", (M - 11 * U) * (1 - SL_M))
    add("2018-12-17", 4, 1, "17:35", (M - 29 * U) * (1 + SL_M), "time", "21:00", (M - 16 * U) * (1 - SL_M))
    add("2018-12-18", 5, 1, "17:40", (M - 29 * U) * (1 + SL_M), "time", "21:00", (M - 16 * U) * (1 - SL_M))
    add("2018-12-20", 0, 1, "17:15", fill, "time", "21:00", (M - 11 * U) * (1 - SL_M))
    add("2019-01-03", 0, 1, "17:15", fill, "time", "21:00", (M - 11 * U) * (1 - SL_M))
    add("2019-01-09", 0, 1, "17:15", (M - 8 * U) * (1 + SL_M), "time", "21:00", (M - 10 * U) * (1 - SL_M))
    add("2019-01-10", 0, 1, "17:15", fill, "time", "21:00", (M - 11 * U) * (1 - SL_M))
    add("2019-01-14", 0, 1, "17:15", fill, "target", "17:45", M - U)
    add("2019-01-15", 0, 1, "17:15", fill, "time", "21:00", (M - 56 * U) * (1 - SL_M))
    add("2019-01-16", 0, 1, "17:15", fill, "time", "21:00", (M - 11 * U) * (1 - SL_M))
    add("2019-01-17", 0, 1, "17:15", (M - 1.5 * U) * (1 + SL_M), "time", "21:00", (M - 11 * U) * (1 - SL_M))
    add("2019-01-22", 0, 1, "17:15", (M - 21 * U) * (1 + SL_M), "time", "21:00", (M - 23 * U) * (1 - SL_M))
    add("2019-02-06", 0, 1, "17:15", fill, "target", "18:05", M + 29 * U)
    add("2019-03-07", 0, 1, "17:15", fill, "time", "21:00", (M - 11 * U) * (1 - SL_M))
    add("2019-03-11", 0, 1, "17:15", fill, "time", "21:00", (M - 11 * U) * (1 - SL_M))
    E = pd.DataFrame(exp).sort_values("entry").reset_index(drop=True)
    tt = t[(t.evening >= pd.Timestamp("2018-11-26")) & (t.evening <= pd.Timestamp("2019-04-25"))].reset_index(drop=True)
    same_n = len(tt) == len(E)
    diffs = []
    if same_n:
        for a, b in zip(tt.itertuples(), E.itertuples()):
            ok = (a.entry_time == b.entry and a.side == b.side and abs(a.entry - b.fill) <= 1e-15
                  and abs(a.stop - b.stop) <= 1e-15 and a.reason == b.reason and a.exit_time == b.exit
                  and abs(a.exit - b.xpx) <= 1e-15 and abs(a.R - b.R) <= 1e-12)
            if not ok:
                diffs.append({"evening": b.evening, "engine": [str(a.entry_time), a.side, a.entry, a.stop, a.reason,
                                                              str(a.exit_time), a.exit, a.R],
                              "expected": [str(b.entry), b.side, b.fill, b.stop, b.reason, str(b.exit), b.xpx, b.R]})
    check(f"A main: {len(E)} trades exactly as derived by hand (entry, fill, stop, exit reason, time, price, R)",
          same_n and not diffs, {"n_engine": len(tt), "n_expected": len(E), "diffs": diffs[:4]})
    check("A one position: SI sell order at 18:55 exists and is skipped while the buy is open; SJ order on the exit bar "
          "(17:20) skipped", st("2018-12-11", 20) == "order" and row("2018-12-11", 20).side == -1
          and st("2018-12-12", 1) == "order" and len(trade_on(tt, "2018-12-11")) == 2 and len(trade_on(tt, "2018-12-12")) == 2)
    check("A DST: EST evening 2019-03-07 enters 22:15 UTC, exits 02:00 UTC; EDT evening 2019-03-11 enters 21:15 UTC, exits "
          "01:00 UTC", trade_on(tt, "2019-03-07").entry_time[0] == pd.Timestamp("2019-03-07 22:15", tz="UTC")
          and trade_on(tt, "2019-03-07").exit_time[0] == pd.Timestamp("2019-03-08 02:00", tz="UTC")
          and trade_on(tt, "2019-03-11").entry_time[0] == pd.Timestamp("2019-03-11 21:15", tz="UTC")
          and trade_on(tt, "2019-03-11").exit_time[0] == pd.Timestamp("2019-03-12 01:00", tz="UTC")
          and not bool(trade_on(tt, "2019-03-07").ny_summer_time[0]) and bool(trade_on(tt, "2019-03-11").ny_summer_time[0]))
    check("A swap 0 and no trade crosses 17:00 New York (asserted by check_trades)", float(t.swap.abs().sum()) == 0.0)
    ev_e = C.run_orders(bk, o, C.costs(P["main"]), no_overlap=False)
    check("A every-signal run: one trade per order (overlaps allowed), more than the main",
          len(ev_e) == len(o) and len(ev_e) > len(t))
    # ---------- neighbours
    o7, tb7 = C.make_orders(bk, P["one_per_night"])
    t7 = C.run_orders(bk, o7, C.costs(P["one_per_night"]))
    firsts = o.groupby("evening").head(1)
    check("A one_per_night: exactly the first order of each evening; SI and SJ keep one trade",
          len(o7) == len(firsts) and (o7.entry_i.to_numpy() == firsts.entry_i.to_numpy()).all()
          and len(trade_on(t7, "2018-12-11")) == 1 and len(trade_on(t7, "2018-12-12")) == 1
          and (pd.Series(tb7.status).eq(C.ST_NOT_FIRST).sum() == len(o) - len(o7)))
    o2, tb2 = C.make_orders(bk, P["first_hour"])
    check("A first_hour: 9 decisions a night (17:15-17:55), its orders = the main's orders with k <= 8",
          (tb2.groupby("evening").size() == 9).all() and len(o2) == int((o.k_dec <= 8).sum())
          and (o2.entry_i.to_numpy() == o[o.k_dec <= 8].entry_i.to_numpy()).all())
    o6, _ = C.make_orders(bk, P["stop_3.0"])
    check("A stop_3.0: same orders, stop distance x 1.5 of the main's",
          len(o6) == len(o) and np.allclose(o6.stop_dist.to_numpy(), 1.5 * o.stop_dist.to_numpy(), rtol=0, atol=0))
    o4, tb4 = C.make_orders(bk, P["width_2.5"])
    r4 = tb4[(tb4.evening == pd.Timestamp("2019-01-22")) & (tb4.k == 0)].iloc[0]
    r2_ = row("2019-01-22", 0)
    z = r2_.D / r2_.sigma
    check("A width_2.5: a close 2.35 sigma below mu signals at 2.0 sigma (main order) but not at 2.5; no width_2.5 "
          "order that evening", 2.0 < z < 2.5 and r2_.side == 1 and r2_.status == C.ST_ORDER and r4.side == 0
          and r4.status == C.ST_INSIDE and not (o4.evening == pd.Timestamp("2019-01-22")).any() and len(o4) < len(o),
          {"z": z})
    o5, tb5 = C.make_orders(bk, P["m15"])
    d15 = tb5[tb5.evening == pd.Timestamp("2019-01-10")]
    r5 = d15[d15.k == 0].iloc[0]
    check("A m15: 11 decisions 17:15-19:45 every 15 min; 17:15 uses the [17:00,17:15) bucket: buy, mu = M - u, D = 19u",
          len(d15) == 11 and (np.diff(d15.dec_ns.to_numpy()) == 15 * 60 * 10**9).all()
          and int(d15.dec_ns.iloc[-1]) == ny_ns("2019-01-10", "19:45") and r5.side == 1 and r5.mu == M - U and r5.D == 19 * U
          and r5.status == C.ST_ORDER)
    o3, _ = C.make_orders(bk, P["moving_mid"])
    t3 = C.run_orders(bk, o3, C.costs(P["moving_mid"]))
    a3 = trade_on(t3, "2019-01-14")
    b3 = trade_on(t3, "2018-12-05")
    v3 = trade_on(t3, "2019-01-15")
    check("A moving_mid: no target; exit at the 17:45 open after the [17:40,17:45) close returns to its own middle band",
          o3.target.isna().all() and len(a3) == 1 and a3.reason[0] == "time" and a3.exit_time[0] == ny_ts("2019-01-14", "17:45")
          and abs(a3.exit[0] - (M - U) * (1 - SL_M)) <= 1e-15)
    check("A moving_mid: close == its own middle band counts (>=): SF exits at 18:45 (window all at the plateau)",
          len(b3) == 1 and b3.exit_time[0] == ny_ts("2018-12-05", "18:45") and abs(b3.exit[0] - (M - 11 * U) * (1 - SL_M)) <= 1e-15)
    check("A moving_mid: a falling drift never returns to the band: capped at the 21:00 exit",
          len(v3) == 1 and v3.exit_time[0] == ny_ts("2019-01-15", "21:00"))
    # ---------- review R6-1: no gap rule on the moving exit (the reviewer's case, expected exit 18:40)
    dg = "2019-02-06"
    sb5 = bk.bars(5, 20, 120)
    jg = int(np.searchsorted(sb5["start"], ny_ns(dg, "18:00")))
    trig_ok = (sb5["start"][jg] == ny_ns(dg, "18:00") and bool(sb5["usable"][jg]) and sb5["close"][jg] == M
               and sb5["mu"][jg] == M - 5.5 * U and bk.ns[int(np.searchsorted(bk.ns, ny_ns(dg, "18:05")))] == ny_ns(dg, "18:40"))
    g3 = trade_on(t3, dg)
    g1 = trade_on(tt, dg)
    old_rule = int(C.exit_index(bk.m1, pd.DatetimeIndex([ny_ts(dg, "18:05")]), max_gap_min=30)[0])
    check("A moving_mid (review R6-1): the trigger bar [18:00,18:05) closes at M >= its own middle band M - 5.5u and no "
          "quote follows until 18:40: exit at the 18:40 open (the first M1 bar at or after 18:05, R = exit at M - 11u), "
          "not at the 18:04 open that the 30-minute gap rule would give (before the trigger close exists); main: target "
          "at the 18:04 open",
          trig_ok and len(g3) == 1 and g3.reason[0] == "time" and g3.exit_time[0] == ny_ts(dg, "18:40")
          and abs(g3.exit[0] - (M - 11 * U) * (1 - SL_M)) <= 1e-15 and int(g3.mm_trigger_end_ns[0]) == ny_ns(dg, "18:05")
          and bk.ns[old_rule] == ny_ns(dg, "18:04") and len(g1) == 1 and g1.reason[0] == "target",
          {"exit": str(g3.exit_time[0]) if len(g3) else None, "trigger_ok": trig_ok})
    mm_bad = []
    for r in t3.itertuples():
        trig = int(r.mm_trigger_end_ns)
        xb = int(np.searchsorted(bk.ns, pd.Timestamp(r.exit_time).value, side="left"))
        if r.reason == "time" and xb < int(r.exit21_i):
            if not (trig > pd.Timestamp(r.entry_time).value and xb == int(np.searchsorted(bk.ns, trig, side="left"))):
                mm_bad.append(str(r.evening))
    check("A moving_mid (review R6-1): every exit before the 21:00 exit bar is at the first M1 bar at or after its trigger "
          "bar's end (which is after the entry bar's start)", not mm_bad and len(t3) > 0, mm_bad)
    # ---------- review R6-6: exits by kind ('time' split into the 21:00 exit and moving_mid exits)
    kinds = {d: (trade_on(t3, d).exit_kind[0] if len(trade_on(t3, d)) else None)
             for d in ("2019-01-14", "2018-12-05", "2019-02-06", "2019-01-15", "2018-12-10")}
    n21 = {}
    for r in t3.itertuples():
        x21 = int(bk.exit_at(pd.DatetimeIndex([r.evening]), "21:00", 30)[0])
        n21[(str(r.evening), str(r.entry_time))] = r.reason == "time" and pd.Timestamp(r.exit_time).value < bk.ns[x21]
    n_mm = int(sum(n21.values()))
    s3 = C.stats(t3.assign(cross="eurcad"), crosses=["eurcad"])
    s1 = C.stats(tt.assign(cross="eurcad"), crosses=["eurcad"])
    check("A exits by kind (review R6-6): moving_mid's market exits at its own middle band are 'moving_mid', its 21:00 "
          "exits 'time_21_00' (SV capped at 21:00, SH's band exit at 18:45 before its 20:59 exit bar); the main has no "
          "'moving_mid' exit; the stats count them apart and the kinds add up to the engine's reasons",
          kinds == {"2019-01-14": "moving_mid", "2018-12-05": "moving_mid", "2019-02-06": "moving_mid",
                    "2019-01-15": "time_21_00", "2018-12-10": "moving_mid"}
          and s3["exits_by_kind"].get("moving_mid", 0) == n_mm > 0
          and s3["exits_by_kind"].get("moving_mid", 0) + s3["exits_by_kind"].get("time_21_00", 0) == s3["exits"]["time"]
          and "moving_mid" not in s1["exits_by_kind"] and s1["exits_by_kind"].get("time_21_00", 0) == s1["exits"]["time"]
          and s1["exits_by_kind"].get("target", 0) == s1["exits"]["target"],
          {"kinds": kinds, "stats": s3.get("exits_by_kind"), "independent_moving_count": n_mm})
    # ---------- costs x1.5 and gross
    m15 = C.stressed(df, 1.5)
    bk15 = C.Book(m15, "eurcad")
    oa, tba = C.make_orders(bk15, P["main"])
    ra = tba[(tba.evening == pd.Timestamp("2019-01-16")) & (tba.k == 0)].iloc[0]
    rz = tba[(tba.evening == pd.Timestamp("2019-01-17")) & (tba.k == 0)].iloc[0]
    check("A x1.5 reading a: the filter sees 1.5 C (SY: C 7.5u -> 11.25u, dropped); SZ refused on the widened ask open",
          ra.C == 11.25 * U and ra.status == C.ST_COST and rz.status == C.ST_TARGET
          and row("2019-01-16", 0).status == C.ST_ORDER and row("2019-01-17", 0).status == C.ST_ORDER)
    tb_ = C.run_orders(bk, o, C.costs(P["main"], 1.5), frame=m15)
    z = trade_on(tb_, "2019-01-17")
    zf = (M - 0.5 * U) * (1 + SL_M15)
    check("A x1.5 reading b: the base order replayed, its fill past the target (M - 0.5u x (1 + 0.15 bp) >= M - u)",
          len(z) == 1 and abs(z.entry[0] - zf) <= 1e-15 and z.entry[0] >= M - U)
    sa = trade_on(tb_, "2018-11-27")
    check("A x1.5 reading b: SA fill = widened ask open x (1 + 0.15 bp), target still at mu",
          len(sa) == 1 and abs(sa.entry[0] - (M - 18.5 * U) * (1 + SL_M15)) <= 1e-15 and sa.reason[0] == "target"
          and sa.exit[0] == M - U)
    oa_keys = set(zip(oa.evening, oa.k_dec))
    check("A x1.5 reading a: rebuilt orders are a subset of the base orders", oa_keys <= set(zip(o.evening, o.k_dec)))
    mg = C.stressed(df, 0.0)
    tg = C.run_orders(bk, o, C.GROSS, frame=mg)
    g = trade_on(tg, "2018-11-27")
    check("A gross: base orders on mid quotes, no slippage (SA: fill M - 20u, exit M - u)",
          len(g) == 1 and g.entry[0] == M - 20 * U and g.exit[0] == M - U)
    # ---------- review R6-3: reading a's gross and cost bp come from its own rebuilt orders, not from the base orders
    ta = C.run_orders(bk15, oa, C.costs(P["main"], 1.5))
    ga = C.run_orders(bk, oa, C.GROSS, frame=mg)
    sa_ = C.stats(ta.assign(cross="eurcad"), gross=ga, crosses=["eurcad"])
    sb_ = C.stats(tb_.assign(cross="eurcad"), gross=tg, crosses=["eurcad"])
    ev_a = set(pd.DatetimeIndex(ga.evening))
    check("A x1.5 reading a (review R6-3): its gross bp is the mean over ITS OWN orders replayed on the gross frame (SY and "
          "SZ, dropped in a, are absent), its cost bp = that gross bp - its net bp; reading b keeps the base orders' gross",
          sa_["n_gross"] == len(ga) == len(ta) and set(zip(ta.evening, ta.entry_time)) == set(zip(ga.evening, ga.entry_time))
          and sa_["bp_gross_per_trade"] == round(float((ga.pnl / ga.entry).mean() * 1e4), 4)
          and sa_["bp_cost_per_trade"] == round(float((ga.pnl / ga.entry).mean() * 1e4)
                                                - float((ta.pnl / ta.entry).mean() * 1e4), 4)
          and pd.Timestamp("2019-01-16") not in ev_a and pd.Timestamp("2019-01-17") not in ev_a
          and len(ga) < len(tg) and sb_["n_gross"] == len(tg),
          {"n_a": len(ta), "n_gross_a": len(ga), "n_gross_base": len(tg)})
    # ---------- review R6-4: what declared L18 says of reading a's frame (mid closes equal; H1 ranges recomputed)
    idx2 = pd.DatetimeIndex(["2019-02-06 23:00", "2019-02-06 23:01"], tz="UTC").as_unit("ns")
    m2 = pd.DataFrame({"bo": [1.5000, 1.4990], "bh": [1.5010, 1.4995], "bl": [1.4995, 1.4985], "bc": [1.5005, 1.4990],
                       "ao": [1.50002, 1.5050], "ah": [1.50102, 1.5055], "al": [1.49952, 1.5045], "ac": [1.50052, 1.5050]},
                      index=idx2)[C.COLS]
    m2s = C.stressed(m2, 1.5)
    rb, rs = float(C.Book(m2, "eurcad").h1(1)["rng"][0]), float(C.Book(m2s, "eurcad").h1(1)["rng"][0])
    mid_same = float(np.abs(((m2.bc + m2.ac) / 2 - (m2s.bc + m2s.ac) / 2).to_numpy()).max()) <= 1e-15
    c5 = float(C.Book(m2, "eurcad").bars(5, 1, 120)["close"][0]) - float(C.Book(m2s, "eurcad").bars(5, 1, 120)["close"][0])
    check("A x1.5 frame (review R6-4, declared L18): the M5 mid closes equal the base frame's up to the last bits, but an H1 "
          "range is recomputed on the widened quotes and differs when the spread varies inside the hour (two minutes, "
          "spreads 0.2 and 6 pips: 42.4 pips on the base frame, 57.35 on the x1.5 frame)",
          mid_same and abs(c5) <= 1e-15 and abs(rb / 1e-4 - 42.4) < 1e-9 and abs(rs / 1e-4 - 57.35) < 1e-9,
          {"h1_base_pips": rb / 1e-4, "h1_x1.5_pips": rs / 1e-4})
    # ---------- assertions
    bad_t = tt.iloc[:1].copy()
    bad_t["exit_time"] = bad_t.entry_time + pd.Timedelta(hours=21)
    try:
        C.check_trades(bad_t)
        raised = False
    except AssertionError:
        raised = True
    late_t = tt.iloc[:1].copy()
    late_t["exit_time"] = ny_ts(str(pd.Timestamp(late_t.evening.iloc[0]).date()), "21:31")
    try:
        C.check_trades(late_t)
        raised2 = False
    except AssertionError:
        raised2 = True
    check("A swap / clock assertion raises on a trade crossing 17:00 New York and on an exit after 21:30", raised and raised2)
    return {"df": df, "bk": bk, "main_trades": tt, "orders": o, "n_decisions": int(len(tb))}


# ============================================================================================ world B
def world_b():
    import frames as F
    d = os.path.join(SCR, "raw_b")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    out = os.path.join(SCR, "r6_b")
    shutil.rmtree(out, ignore_errors=True)
    ms = lambda s: int(pd.Timestamp(s, tz="UTC").value // 10**6)  # noqa: E731
    rows_b, rows_a = {y: [] for y in range(2013, 2022)}, {y: [] for y in range(2013, 2022)}

    def put(ts, b, a, vb=1.0, va=1.0, year=None):
        y = year or int(ts[:4])
        rows_b[y].append((ms(ts), *b, vb))
        rows_a[y].append((ms(ts), *a, va))
    put("2015-03-03 10:00", (1.1, 1.2, 1.0, 1.15), (1.11, 1.21, 1.01, 1.16))       # kept
    put("2015-03-03 10:01", (1.15, 1.15, 1.15, 1.15), (1.16, 1.16, 1.16, 1.16))    # flat at the previous bid close: dropped
    put("2015-03-03 10:02", (1.2, 1.3, 1.1, 1.25), (1.21, 1.31, 1.11, 1.26), 0.0, 0.0)  # zero volume both: dropped
    put("2015-03-03 10:03", (1.2, 1.3, 1.1, 1.25), (1.21, 1.31, 1.11, 1.24))       # crossed (ask close < bid close)
    put("2015-03-07 12:00", (1.2, 1.3, 1.1, 1.25), (1.21, 1.31, 1.11, 1.26))       # Saturday: weekday rule
    put("2016-01-04 10:00", (1.3, 1.4, 1.2, 1.35), (1.31, 1.41, 1.21, 1.36))       # kept
    put("2016-01-04 10:00", (9.0, 9.0, 9.0, 9.0), (9.1, 9.1, 9.1, 9.1), year=2017)  # duplicate in a later file: first kept
    put("2021-12-31 21:59", (1.4, 1.5, 1.3, 1.45), (1.41, 1.51, 1.31, 1.46))       # kept (last minute of 2021)
    put("2022-01-01 00:00", (1.4, 1.5, 1.3, 1.45), (1.41, 1.51, 1.31, 1.46), year=2021)  # >= 2022 in the 2021 file: filtered
    for y in range(2013, 2022):
        for side, rows in (("bid", rows_b[y]), ("ask", rows_a[y])):
            with gzip.open(os.path.join(d, f"zzzaaa-m1-{side}-{y}.csv.gz"), "wt") as f:
                f.write("timestamp,open,high,low,close,volume\n")
                for r in rows:
                    f.write(",".join(str(x) for x in r) + "\n")
    old = (F.RAW6, F.R6)
    F.RAW6, F.R6 = d, out
    try:
        info = F.build("zzzaaa")
        fr = pd.read_parquet(os.path.join(out, "zzzaaa_m1.parquet"), filters=[("ts", "<", C.CUT)])
    finally:
        F.RAW6, F.R6 = old
    exp_idx = pd.DatetimeIndex(["2015-03-03 10:00", "2016-01-04 10:00", "2021-12-31 21:59"], tz="UTC")
    check("B frames: filter < 2022 in the read, flat and zero-volume minutes, crossed minute, Saturday minute dropped; "
          "duplicate keeps the first file's row",
          list(fr.index) == list(exp_idx) and info["dropped_crossed"] == 1 and info["dropped_flat_or_zero_volume"] == 2
          and info["dropped_weekday_rule"] == 1 and float(fr.bo.iloc[1]) == 1.3 and fr.index.max() < C.CUT, info)
    m = pd.DataFrame({"bo": [1.0], "bh": [1.1], "bl": [0.9], "bc": [1.05], "ao": [1.01], "ah": [1.11], "al": [0.91],
                      "ac": [1.06]}, index=pd.DatetimeIndex(["2015-03-03 10:00"], tz="UTC").as_unit("ns"))
    f2 = C.fold_commission(m, "nzdcad")
    h = 0.5 * 1.0 * 1e-4 * ((1.05 + 1.06) / 2)
    check("B commission fold: bid - h, ask + h on all four prices, h = 0.5 x c x 1e-4 x mid close (NZDCAD c = 1.0 bp)",
          all(f2[k].iloc[0] == m[k].iloc[0] - h for k in ("bo", "bh", "bl", "bc"))
          and all(f2[k].iloc[0] == m[k].iloc[0] + h for k in ("ao", "ah", "al", "ac"))
          and abs((f2.ac.iloc[0] - f2.bc.iloc[0]) - (0.01 + 1.0e-4 * 1.055)) < 1e-15)
    shutil.rmtree(d, ignore_errors=True)
    shutil.rmtree(out, ignore_errors=True)


# ============================================================================================ world C
def noisy_frame(seed, start="2018-10-28 21:00", end="2019-04-26 21:00", level=1.5):
    """A random-walk minute frame with a mean-reverting night and a wider rollover spread (synthetic, seeded)."""
    rng = np.random.default_rng(seed)
    utc = pd.date_range(start, end, freq="min", tz="UTC", inclusive="left").as_unit("ns")
    ny = utc.tz_convert(C.NY)
    utc = utc[(ny + pd.Timedelta(hours=7)).dayofweek < 5]
    ny = utc.tz_convert(C.NY)
    n = len(utc)
    keep = rng.random(n) > 0.03                                      # random missing minutes
    hm = (ny.hour * 60 + ny.minute).to_numpy()
    vol = np.where((hm >= 17 * 60) & (hm < 21 * 60), 0.6e-4, 1.2e-4)
    x = np.zeros(n)
    eps = rng.standard_normal(n) * vol
    for i in range(1, n):
        x[i] = 0.995 * x[i - 1] + eps[i]
    mid_c = level * np.exp(x + np.cumsum(rng.standard_normal(n) * 0.2e-4))
    mid_o = np.r_[mid_c[0], mid_c[:-1]]
    amp = np.abs(rng.standard_normal(n)) * 0.4e-4 * level
    sp = np.where((hm >= 16 * 60 + 55) & (hm < 17 * 60 + 10), 6e-4, 0.8e-4) * level * (1 + 0.3 * rng.random(n))
    df = pd.DataFrame({"bo": mid_o - sp / 2, "bh": np.maximum(mid_o, mid_c) + amp - sp / 2, "bl": np.minimum(mid_o, mid_c) - amp - sp / 2,
                       "bc": mid_c - sp / 2, "ao": mid_o + sp / 2, "ah": np.maximum(mid_o, mid_c) + amp + sp / 2,
                       "al": np.minimum(mid_o, mid_c) - amp + sp / 2, "ac": mid_c + sp / 2}, index=utc)[keep]
    df.index.name = "ts"
    return df[C.COLS]


def world_c(a):
    out = os.path.join(SCR, "pipeline")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    levels = {"eurcad": 1.5, "gbpcad": 1.7, "euraud": 1.6, "audcad": 0.95, "eurgbp": 0.88, "eurchf": 1.1, "gbpchf": 1.25,
              "audnzd": 1.07, "nzdcad": 0.9, "cadchf": 0.72, "gbpaud": 1.8, "eurnzd": 1.7}
    cache = {}

    def load(c):
        if c not in cache:
            cache[c] = C.assert_is(C.fold_commission(noisy_frame(C.CROSSES.index(c) + 11, level=levels[c]), c))
        return cache[c]
    val_fake = os.path.join(out, "val_access.log")
    open(val_fake, "w").write("synthetic\n")
    import run as RUN
    res = RUN.run_all(C.CONFIGS, C.CROSSES, load, out, decl_sha="synthetic", decl_utc="synthetic", val_log=val_fake)
    lines = [json.loads(x) for x in open(os.path.join(out, "trials.jsonl"))]
    check("C run_all: 91 trials lines (7 configurations x (12 crosses + pooled)), every reading present",
          len(lines) == 91 and sum(1 for x in lines if x["cross"] == "pooled") == 7
          and all(all(k in x for k in ("base", "stress_a", "stress_b", "gross", "every_signal")) for x in lines))
    try:
        RUN.run_all(C.CONFIGS, C.CROSSES, load, out, val_log=val_fake)
        refused = False
    except AssertionError as e:
        refused = "trials.jsonl exists" in str(e)
    check("C the run refuses to run twice (trials.jsonl exists)", refused and sum(1 for _ in open(os.path.join(out, "trials.jsonl"))) == 91)
    tr = lambda i, name, k: pd.read_parquet(os.path.join(out, f"trades_{i:02d}_{name}_{k}.parquet"))  # noqa: E731
    mb, me, ma, mbb, mg = (tr(1, "main", k) for k in ("base", "every", "stress_a", "stress_b", "gross"))
    n_main = len(mb)
    check("C main has trades on every cross; every-signal >= main", n_main > 50 and mb.cross.nunique() == 12 and len(me) >= n_main,
          {"main": n_main, "every": len(me)})
    Rchk = np.allclose(mb.R, mb.side * (mb.exit - mb.entry) / (mb.entry - mb.stop).abs(), rtol=0, atol=1e-12)
    check("C R = side x (exit fill - entry fill) / |entry fill - stop| on every main trade", Rchk)
    k_main = set(zip(mb.cross, mb.entry_time))
    o7 = tr(7, "one_per_night", "base")
    f1 = tr(2, "first_hour", "base")
    check("C one_per_night trades are main orders, at most one per cross and evening",
          set(zip(o7.cross, o7.entry_time)) <= set(zip(me.cross, me.entry_time))
          and o7.groupby(["cross", "evening"]).size().max() == 1)
    e_ny = pd.DatetimeIndex(f1.entry_time).tz_convert(C.NY)
    check("C first_hour entries between 17:15 and 18:00 New York", ((e_ny.hour * 60 + e_ny.minute) <= 18 * 60).all()
          and ((e_ny.hour * 60 + e_ny.minute) >= 17 * 60 + 15).all())
    m15t = tr(5, "m15", "base")
    dn = pd.DatetimeIndex(m15t.dec_utc).tz_localize("UTC").tz_convert(C.NY)
    check("C m15 decisions on the 15-minute grid 17:15-19:45", (dn.minute % 15 == 0).all() and
          ((dn.hour * 60 + dn.minute) <= 19 * 60 + 45).all())
    check("C stress a orders subset of base orders; stress b and gross replay the base orders (entries among them)",
          set(zip(ma.cross, ma.entry_time)) <= set(zip(me.cross, me.entry_time))
          and set(zip(mbb.cross, mbb.entry_time)) <= set(zip(me.cross, me.entry_time))
          and set(zip(mg.cross, mg.entry_time)) <= set(zip(me.cross, me.entry_time)))
    mm = tr(3, "moving_mid", "base")
    check("C moving_mid: no target exits", not (mm.reason == "target").any() and len(mm) > 0)
    rj = json.load(open(os.path.join(out, "run.json")))
    pooled = {c["name"]: c["results"]["pooled"] for c in rj["configs"]}
    check("C run.json: pooled n equals the trade files; val log unchanged", pooled["main"]["base"]["n"] == n_main
          and rj["val_access_log_sha256_before"] == rj["val_access_log_sha256_after"])
    # ---------- review R6-1 in the pipeline: every moving_mid band exit at the first M1 bar at or after its trigger end
    badw, n_mmx = [], 0
    for c in C.CROSSES:
        ns_c = load(c).index.as_unit("ns").asi8
        for r in mm[(mm.cross == c) & (mm.exit_kind == "moving_mid")].itertuples():
            n_mmx += 1
            trig = int(r.mm_trigger_end_ns)
            first = int(np.searchsorted(ns_c, trig, side="left"))
            if not (trig > pd.Timestamp(r.entry_time).value and ns_c[first] == pd.Timestamp(r.exit_time).value):
                badw.append((c, str(r.entry_time)))
    check("C moving_mid (review R6-1): every band exit is at the first M1 bar at or after its trigger bar's end (12 crosses)",
          n_mmx > 50 and not badw, {"n": n_mmx, "bad": badw[:5]})
    # ---------- review R6-3: each reading's gross and cost bp come from the gross replay of its own orders
    g0, ga_ = tr(1, "main", "gross"), tr(1, "main", "gross_a")
    pm = pooled["main"]
    bp_of = lambda x: round(float((x.pnl / x.entry).mean() * 1e4), 4)  # noqa: E731
    check("C gross and cost bp (review R6-3): base and stress_b from the base orders' gross replay, stress_a from its own "
          "rebuilt orders' gross replay (gross_a: other orders, so another count); gross_a in every trials line",
          pm["stress_a"]["n_gross"] == len(ga_) and pm["stress_a"]["bp_gross_per_trade"] == bp_of(ga_)
          and pm["base"]["n_gross"] == len(g0) == pm["stress_b"]["n_gross"] and pm["base"]["bp_gross_per_trade"] == bp_of(g0)
          and pm["stress_b"]["bp_gross_per_trade"] == bp_of(g0) and len(ga_) < len(g0)
          and set(zip(ga_.cross, ga_.entry_time)) <= set(zip(me.cross, me.entry_time))
          and all("gross_a" in x and "n_gross" in x["stress_a"] for x in lines),
          {"n_gross_a": len(ga_), "n_gross": len(g0)})
    # ---------- review R6-6: exits by kind in run.json
    mmb, mnb = pooled["moving_mid"]["base"], pooled["main"]["base"]
    check("C exits by kind (review R6-6): moving_mid's 'time' exits split into 'moving_mid' and 'time_21_00' in run.json and "
          "in its trials lines; the main has no 'moving_mid' exit",
          mmb["exits_by_kind"].get("moving_mid", 0) == int((mm.exit_kind == "moving_mid").sum()) > 0
          and mmb["exits_by_kind"].get("moving_mid", 0) + mmb["exits_by_kind"].get("time_21_00", 0) == mmb["exits"]["time"]
          and "moving_mid" not in mnb["exits_by_kind"]
          and all("exits_by_kind" in x["base"] for x in lines if x["config"] == "moving_mid" and x["base"]["n"] > 0),
          {"moving_mid": mmb.get("exits_by_kind"), "main": mnb.get("exits_by_kind")})
    # ---------- review R6-2: unrounded figures stored next to the display figures
    check("C raw figures (review R6-2): every judged figure stored unrounded next to its display value",
          all(k in mnb for k in ("pf_raw", "t_daily_raw", "expectancy_R_raw", "total_R_raw", "max_cross_share_raw",
                                 "max_hold_h_raw"))
          and abs(mnb["pf_raw"] - C.pf(mb.R)) == 0 and mnb["total_R_raw"] == float(mb.R.to_numpy().sum())
          and round(mnb["pf_raw"], 4) == mnb["pf"] and pm["every"]["expectancy_R_raw"] == float(me.R.to_numpy().mean()))
    # ---------- review R6-5: run.json records the trials file it wrote
    check("C bookkeeping (review R6-5): run.json records the sha256 and the line count of trials.jsonl; no temporary file left",
          rj["trials_sha256"] == C.sha256(os.path.join(out, "trials.jsonl")) and rj["trials_logged"] == 91
          and not any(".tmp" in f for f in os.listdir(out)))
    # ---------- the null
    import null as NULL
    p = C.CONFIG["main"]["params"]
    n1, m1_ = NULL.null_all(mb, C.CROSSES, load, p, n_replays=6, seed=0)
    n2, m2_ = NULL.null_all(mb, C.CROSSES, load, p, n_replays=6, seed=0)
    check("C null: reproducible with default_rng(0); percentile = share of replay means strictly below the main's",
          np.array_equal(m1_, m2_) and n1["percentile"] == round(float((m1_ < float(mb.R.mean())).mean() * 100), 2)
          and abs(n1["main_mean_R"] - float(mb.R.mean())) < 1e-6)
    # replay mechanics on world A's frame
    bk = a["bk"]
    tA = a["main_trades"]
    E_t = bk.tradable(480)
    E_t = E_t[(E_t >= pd.Timestamp("2018-11-26")) & (E_t <= pd.Timestamp("2019-04-25"))]
    mid0 = C.ny_utc_ns(E_t, "00:00")
    x21 = bk.exit_at(E_t, "21:00", 30)
    tr0 = tA.sort_values("entry_time").reset_index(drop=True)
    ev_late = list(E_t).index(pd.Timestamp("2018-12-13"))            # SK: no bar 17:15-17:19, 17:20 bar exists
    ev_ok = list(E_t).index(pd.Timestamp("2019-02-05"))              # a quiet evening
    ev_hole = list(E_t).index(pd.Timestamp("2018-12-17"))            # SL: no bar 17:15-17:20 (first bar 17:21)
    cand = np.full((len(tr0), 20), ev_hole, np.int32)
    cand[0, 5] = ev_ok                                               # trade 0 (17:15): first valid candidate is #5
    cand[1, :] = ev_hole                                             # trade 1 (17:15): never valid within 5 min -> dropped
    cand[2, 0] = ev_late                                             # trade 2 (17:15): SK's 17:20 bar, exactly 5 min late: kept
    ro, nl, nx = NULL.replay_orders(bk, tr0, cand, E_t, mid0, x21, p)
    first = ro.iloc[0]
    m_o = (bk.m1.bo.to_numpy()[first.entry_i] + bk.m1.ao.to_numpy()[first.entry_i]) / 2
    check("C null replay: same clock time on the drawn evening (first valid of 20 candidates), stop and target distances "
          "scaled by the replay bar's mid open, 21:00 exit of that evening, same side",
          bk.ns[first.entry_i] == ny_ns("2019-02-05", "17:15") and first.exit_i == x21[ev_ok] and first.side == tr0.side[0]
          and abs(first.stop_dist - tr0.risk[0] / tr0.entry[0] * m_o) <= 1e-15
          and abs(first.target_dist - (tr0.target_px[0] - tr0.entry[0]) * tr0.side[0] / tr0.entry[0] * m_o) <= 1e-15)
    check("C null replay: a trade with no candidate within 5 minutes in 20 draws is dropped and counted; 5 minutes late kept",
          nl >= 1 and (bk.ns[ro.entry_i.to_numpy()] == ny_ns("2018-12-13", "17:20")).any(), {"dropped_late": nl})
    tn = C.run_orders(bk, ro, C.costs(p), no_overlap=False, check=False)
    C.check_trades(tn, last_entry_ny="20:05")
    check("C null replay trades all simulated (no_overlap=False) and pass the clock assertions", len(tn) == len(ro))
    # ---------- correlation (synthetic ten)
    import correlation as COR
    rng = np.random.default_rng(5)
    wk = pd.date_range("2014-01-06", "2021-12-27", freq="7D", tz="UTC")
    ten = {f"{n}:{s}": pd.DataFrame({"entry_time": wk, "exit_time": wk + pd.Timedelta(hours=30),
                                      "R": rng.standard_normal(len(wk))}) for n, s in COR.TEN}
    mt = pd.DataFrame({"entry_time": wk + pd.Timedelta(hours=2), "exit_time": wk + pd.Timedelta(hours=31),
                       "R": sum(v.R for v in ten.values()).to_numpy() * 0.5 + rng.standard_normal(len(wk))})
    cr = COR.correlate(mt, ten)
    exp_rho = float(np.corrcoef(mt.R, sum(v.R for v in ten.values()))[0, 1])
    check("C correlation: 418 W-SUN weeks, Pearson with the sum of the ten (known series)",
          cr["n_weeks"] == 418 and abs(cr["main"]["corr_with_sum_of_ten"] - exp_rho) < 1e-3, {"rho": cr["main"]["corr_with_sum_of_ten"],
                                                                                         "expected": exp_rho})
    # ---------- verdict on the synthetic outputs
    import verdict as V
    C.jdump(dict(n1, declared_sha256="synthetic"), os.path.join(out, "null.json"))
    C.jdump(dict(cr, declared_sha256="synthetic"), os.path.join(out, "correlation.json"))
    vr = V.verdict_all(out, load, {"crosses_kept": C.CROSSES, "_written_utc": "synthetic"}, "synthetic")
    crit = vr["criteria"]
    b = pooled["main"]["base"]
    check("C verdict: twelve bars computed from the run (n, PF, t daily, years, both x1.5 readings, crosses, share, "
          "neighbours' median, every signal, hold, null, correlation)",
          len(crit) == 12 and crit["n>=250"]["value"] == b["n"] and crit["pf>=1.12"]["value"] == b["pf"]
          and crit["null>=97.5pct"]["value"] == n1["percentile"] and isinstance(vr["main_pass"], bool)
          and "account_check" in vr["reported_main"] and "break_even_extra_cost_per_round_trip" in vr["reported_main"])
    check("C verdict (review R6-2): the bars read the unrounded figures of run.json, null.json and correlation.json",
          crit["pf>=1.12"]["value_raw"] == b["pf_raw"] and crit["pf>=1.12"]["pass"] == (b["pf_raw"] >= 1.12)
          and crit["t_daily>=2.5"]["value_raw"] == b["t_daily_raw"]
          and crit["null>=97.5pct"]["value_raw"] == n1["percentile_raw"]
          and crit["abs_weekly_corr_with_ten<=0.30"]["value_raw"] == cr["main"]["corr_with_sum_of_ten_raw"]
          and crit["every_signal_exp>0"]["value_raw"] == pooled["main"]["every"]["expectancy_R_raw"]
          and crit["neighbours_median_pf>=1.06"]["value_raw"] == float(np.median(
              [pooled[k]["base"]["pf_raw"] for k in V.NEIGHBOURS])))
    shutil.rmtree(out, ignore_errors=True)
    # ---------- review R6-5: write order of the declared run (two crosses, the main only)
    two, cfg1 = C.CROSSES[:2], [C.CONFIG["main"]]
    out2 = os.path.join(SCR, "pipeline_val")
    shutil.rmtree(out2, ignore_errors=True)
    os.makedirs(out2)
    val2 = os.path.join(out2, "val_access.log")
    open(val2, "w").write("synthetic\n")
    seen = []

    def load_touch(c):
        seen.append(c)
        if len(seen) == 2:                                            # someone touches the val log during the run
            open(val2, "a").write("touched during the run\n")
        return load(c)
    try:
        RUN.run_all(cfg1, two, load_touch, out2, decl_sha="synthetic", decl_utc="synthetic", val_log=val2)
        msg = None
    except AssertionError as e:
        msg = str(e)
    rj_p, tri_p = os.path.join(out2, "run.json"), os.path.join(out2, "trials.jsonl")
    rj2 = json.load(open(rj_p)) if os.path.exists(rj_p) else {}
    check("C bookkeeping (review R6-5): when the val log changes during the run, run.json and trials.jsonl are both "
          "written, complete (run.json holds both val hashes and the trials file's sha256), before the assertion fires",
          msg == "results/val_access.log changed" and os.path.exists(tri_p) and bool(rj2)
          and rj2["val_access_log_sha256_before"] != rj2["val_access_log_sha256_after"]
          and rj2["trials_sha256"] == C.sha256(tri_p) and rj2["trials_logged"] == 3 == sum(1 for _ in open(tri_p))
          and not any(".tmp" in f for f in os.listdir(out2)), {"assertion": msg, "files": sorted(os.listdir(out2))})
    out3 = os.path.join(SCR, "pipeline_fail")
    shutil.rmtree(out3, ignore_errors=True)
    os.makedirs(out3)
    val3 = os.path.join(out3, "val_access.log")
    open(val3, "w").write("synthetic\n")

    def load_fail(c):
        if c == two[1]:
            raise RuntimeError("synthetic failure during the computation")
        return load(c)
    try:
        RUN.run_all(cfg1, two, load_fail, out3, decl_sha="synthetic", decl_utc="synthetic", val_log=val3)
        failed = False
    except RuntimeError:
        failed = True
    nothing = not os.path.exists(os.path.join(out3, "run.json")) and not os.path.exists(os.path.join(out3, "trials.jsonl"))
    RUN.run_all(cfg1, two, load, out3, decl_sha="synthetic", decl_utc="synthetic", val_log=val3)
    rj3 = json.load(open(os.path.join(out3, "run.json")))
    check("C bookkeeping (review R6-5): a failure during the computation leaves neither run.json nor trials.jsonl, so the "
          "declared run can be started again and then completes",
          failed and nothing and rj3["trials_sha256"] == C.sha256(os.path.join(out3, "trials.jsonl"))
          and rj3["val_access_log_sha256_before"] == rj3["val_access_log_sha256_after"])
    shutil.rmtree(out2, ignore_errors=True)
    shutil.rmtree(out3, ignore_errors=True)
    return {"pipeline_main_trades": n_main, "null_percentile_synthetic": n1["percentile"]}


# ============================================================================================ world D (review R6-2)
def world_d():
    """Every bar is judged on the unrounded figure (review R6-2): synthetic trade frames and weekly series whose exact
    figure lies on one side of a threshold while its rounded display value lies on the other."""
    import correlation as COR
    import verdict as V

    def trades(R, crosses=("eurcad",), hold=30.0, start="2015-03-03 22:20"):
        """One trade a day (crosses in turn), the columns common.stats reads."""
        R = np.asarray(R, float)
        et = pd.date_range(start, periods=len(R), freq="D", tz="UTC")
        cr = [crosses[i % len(crosses)] for i in range(len(R))]
        return pd.DataFrame({"R": R, "entry_time": et, "exit_time": et + pd.Timedelta(minutes=30), "side": 1,
                             "reason": "time", "hold_min": hold, "entry": 1.5, "risk": 0.003, "pnl": R * 0.003,
                             "target_px": 1.5005, "cross": cr})
    st = lambda R, **kw: C.stats(trades(R, **kw), crosses=list(kw.get("crosses", ("eurcad",))))  # noqa: E731
    good = st([2.0, -1.0] * 200)

    def run_dict(base=good, sa=good, sb=good, every=good, nbr=None):
        cfgs = [{"name": "main", "results": {"pooled": {"base": base, "stress_a": sa, "stress_b": sb, "every": every}}}]
        for i, k in enumerate(V.NEIGHBOURS):
            cfgs.append({"name": k, "results": {"pooled": {"base": good if nbr is None else nbr[i]}}})
        return {"configs": cfgs}
    nul = {"percentile": 99.0, "percentile_raw": 99.0}
    cor = {"main": {"corr_with_sum_of_ten": 0.1, "corr_with_sum_of_ten_raw": 0.1}}
    crit = lambda rd, n=1, co=cor: V.criteria(rd, nul, co, n)[0]  # noqa: E731
    # PF: exact 1.119951 shown as 1.12
    b = st([1.119951, -1.0] * 200)
    check("D PF 1.119951 (shown 1.12) fails 'PF >= 1.12' (review R6-2)",
          b["pf"] == 1.12 and b["pf_raw"] < 1.12 and not crit(run_dict(base=b))["pf>=1.12"]["pass"]
          and crit(run_dict())["pf>=1.12"]["pass"], {"pf_raw": b["pf_raw"]})
    # stress: exact 1.039951 shown as 1.04 in reading a, and in reading b
    s = st([1.039951, -1.0] * 200)
    check("D x1.5 PF 1.039951 (shown 1.04) fails the stress bar in reading a and in reading b",
          s["pf"] == 1.04 and not crit(run_dict(sa=s))["stress_pf>=1.04_both_readings"]["pass"]
          and not crit(run_dict(sb=s))["stress_pf>=1.04_both_readings"]["pass"])
    # t on daily sums: exact t just below 2.5, shown as 2.5
    lo, hi = 1.0, 3.0
    for _ in range(200):                                          # bisection on a: t of [a, -1] x 50 days = 2.4997
        a = (lo + hi) / 2
        tt_ = C.t_stat(np.array([a, -1.0] * 50))
        lo, hi = (a, hi) if tt_ < 2.4997 else (lo, a)
    bt = st([lo, -1.0] * 50)
    check("D t on daily sums 2.4997 (shown 2.5) fails 't >= 2.5'",
          bt["t_daily"] == 2.5 and bt["t_daily_raw"] < 2.5 and not crit(run_dict(base=bt))["t_daily>=2.5"]["pass"],
          {"t_raw": bt["t_daily_raw"]})
    # largest cross share 0.25004 (shown 0.25); pooled total 0.0004 (shown 0.0) with shares of 0.2
    four = ("eurcad", "gbpcad", "euraud", "audcad")
    bs = st([0.25004, 0.25, 0.25, 0.24996], crosses=four)
    five = ("eurcad", "gbpcad", "euraud", "audcad", "eurgbp")
    bz = st([0.00008] * 5, crosses=five)
    check("D cross share 0.25004 (shown 0.25) fails 'no cross above 25 %'; a pooled total of +0.0004 R (shown 0.0) with "
          "shares of 20 % passes it",
          bs["max_cross_share"] == 0.25 and bs["max_cross_share_raw"] > 0.25
          and not crit(run_dict(base=bs), 4)["max_cross_share<=25%"]["pass"]
          and bz["total_R"] == 0.0 and bz["total_R_raw"] > 0 and crit(run_dict(base=bz), 5)["max_cross_share<=25%"]["pass"],
          {"share_raw": bs["max_cross_share_raw"], "total_raw": bz["total_R_raw"]})
    # neighbours' median of exact PFs 1.059955 (each shown 1.06)
    nbr = [st([x, -1.0] * 200) for x in (1.0, 1.0, 1.059955, 1.059955, 2.0, 2.0)]
    cm = crit(run_dict(nbr=nbr))["neighbours_median_pf>=1.06"]
    check("D neighbours' median of the exact PFs (1.059955, each shown 1.06) fails 'median >= 1.06'",
          float(np.median([x["pf"] for x in nbr])) == 1.06 and not cm["pass"] and cm["value_raw"] < 1.06, cm)
    # every-signal expectancy +2e-6 (shown 0.0)
    ev = st([1.000004, -1.0] * 200)
    check("D every-signal expectancy +2e-6 R (shown 0.0) passes '> 0'",
          ev["expectancy_R"] == 0.0 and ev["expectancy_R_raw"] > 0 and crit(run_dict(every=ev))["every_signal_exp>0"]["pass"])
    # max hold 192.0004 h (shown 192.0)
    bh = st([2.0, -1.0] * 200, hold=192.0004 * 60)
    check("D max hold 192.0004 h (shown 192.0) fails 'max hold <= 5 trading days (192 h)'",
          bh["max_hold_h"] == 192.0 and not crit(run_dict(base=bh))["max_hold<=5_trading_days"]["pass"])
    # weekly correlation 0.30004 exactly constructed (shown 0.3)
    rng = np.random.default_rng(1)
    W = COR.WEEKS
    x = rng.standard_normal(len(W))
    x = (x - x.mean()) / x.std()
    z = rng.standard_normal(len(W))
    z = z - z.mean()
    z -= (z @ x) / (x @ x) * x
    z /= z.std()
    y = 0.30004 * x + np.sqrt(1 - 0.30004 ** 2) * z
    wed = W.to_timestamp(how="start").tz_localize("UTC") + pd.Timedelta(days=2)
    ten = {f"{n}:{s_}": pd.DataFrame({"entry_time": wed - pd.Timedelta(hours=1), "exit_time": wed, "R": x / len(COR.TEN)})
           for n, s_ in COR.TEN}
    co = COR.correlate(pd.DataFrame({"entry_time": wed - pd.Timedelta(hours=1), "exit_time": wed, "R": y}), ten)
    check("D weekly correlation 0.30004 (shown 0.3) fails '|rho| <= 0.30' in correlation.py and in the verdict",
          co["main"]["corr_with_sum_of_ten"] == 0.3 and co["main"]["corr_with_sum_of_ten_raw"] > 0.30 and not co["pass"]
          and not crit(run_dict(), co={"main": co["main"]})["abs_weekly_corr_with_ten<=0.30"]["pass"],
          {"rho_raw": co["main"]["corr_with_sum_of_ten_raw"]})


# ============================================================================================ world E (review R6-1)
def with_holes(df, seed, frac=0.4, lo=6, hi=46):
    """Remove one block of lo .. hi-1 minutes starting between 15:00 and 21:30 New York on about `frac` of the days."""
    rng = np.random.default_rng(seed)
    ns = df.index.as_unit("ns").asi8
    days = pd.DatetimeIndex(sorted(set(df.index.tz_convert(C.NY).tz_localize(None).normalize())))
    keep = np.ones(len(df), bool)
    for d in days:
        if rng.random() < frac:
            s = int(C.ny_utc_ns(pd.DatetimeIndex([d]), "15:00")[0]) + int(rng.integers(0, 390)) * C.NS_MIN
            L = int(rng.integers(lo, hi)) * C.NS_MIN
            keep &= ~((ns >= s) & (ns < s + L))
    return df[keep]


def world_e():
    """moving_mid on noisy frames with planted quote holes (review R6-1): every exit before the 21:00 exit bar is at the
    FIRST M1 bar at or after its trigger bar's end (never a bar before it), including cases where that bar is more than
    30 minutes after the end (where the 30-minute gap rule would have moved the exit before the trigger close); every
    21:00 exit has no trigger before its 21:00 exit bar."""
    p = C.CONFIG["moving_mid"]["params"]
    n_mm = n_gap = n_21 = 0
    bad = []
    for seed in (21, 22, 23):
        bk = C.Book(C.fold_commission(with_holes(noisy_frame(seed), seed), "eurcad"), "eurcad")
        o, _ = C.make_orders(bk, p)
        t = C.run_orders(bk, o, C.costs(p))
        for r in t.itertuples():
            trig = int(r.mm_trigger_end_ns)
            xb = int(np.searchsorted(bk.ns, pd.Timestamp(r.exit_time).value, side="left"))
            first = int(np.searchsorted(bk.ns, trig, side="left")) if trig > 0 else None
            if r.exit_kind == "moving_mid":
                n_mm += 1
                ok = trig > pd.Timestamp(r.entry_time).value and xb == first and bk.ns[xb] >= trig
                if ok and bk.ns[first] - trig > 30 * C.NS_MIN:
                    n_gap += 1
                    old = int(C.exit_index(bk.m1, pd.DatetimeIndex([pd.Timestamp(trig, unit="ns", tz="UTC")]), 30)[0])
                    ok = ok and bk.ns[old] < trig                     # where the old rule would have exited
            elif r.exit_kind == "time_21_00":
                n_21 += 1
                ok = first is None or first >= int(r.exit21_i)
            else:
                ok = r.exit_kind in ("stop", "gap")
            if not ok:
                bad.append((seed, str(r.entry_time), r.exit_kind))
    check("E moving_mid with planted quote holes (review R6-1): every band exit at the first M1 bar at or after its trigger "
          "end, including exits more than 30 minutes after it (the old gap rule exited before the trigger close there); "
          "every 21:00 exit has no earlier trigger", not bad and n_mm > 100 and n_gap >= 1 and n_21 > 0,
          {"band_exits": n_mm, "band_exits_after_a_gap_over_30_min": n_gap, "exits_21_00": n_21, "bad": bad[:5]})
    return {"world_e_band_exits": n_mm, "world_e_gap_cases": n_gap}


def main():
    t0 = time.time()
    os.makedirs(SCR, exist_ok=True)
    info = {}
    try:
        a = world_a()
        info["world_a_decisions_checked"] = a["n_decisions"]
        info["world_a_main_trades"] = int(len(a["main_trades"]))
        world_b()
        info.update(world_c(a))
        world_d()
        info.update(world_e())
    except Exception:
        traceback.print_exc()
        check("no exception", False, traceback.format_exc()[-1500:])
    n_fail = sum(1 for v in CHECKS.values() if not v["pass"])
    out = {"what": "synthetic tests of night_fade (Addendum L) with known answers; no market data read",
           "n_checks": len(CHECKS), "n_failed": n_fail, "all_pass": n_fail == 0, "checks": CHECKS, "info": info,
           "code_sha256": C.code_hashes(), "seconds": round(time.time() - t0, 1)}
    C.jdump(out, os.path.join(C.OUT, "synthetic.json"))
    print(f"{len(CHECKS) - n_fail}/{len(CHECKS)} checks pass")
    assert n_fail == 0, "synthetic checks failed"


if __name__ == "__main__":
    main()
