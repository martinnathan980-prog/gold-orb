"""T3 paper: CR_Paper (SPEC 2.5, step C) against the lab's own code on in-sample data, plain and sanitizer builds.

    python3 -I lab/robot/check/test_paper.py [--quick] [--no-sanitize] [--orders N] [--seed S] [--markets a,b] [--keep]
                                             [--exe BINARY] [--no-e2e] [--e2e-tag is|y2021] [--mutants]

The paper engine (src/CR_Paper.mqh, translated by check/to_cpp.py) runs inside check/test_paper.cpp, which feeds it
minute by minute as CR_Main does: for every minute M, the bars starting before M with their OnBar outputs, then the
OnMinute(M) outputs, then PapOnBarrier(M). Checks:
  1. Random orders (T3). For each market (xauusd, us100, btcusd, ethusd): the in-sample frame lab/data/fp/<sym>_m1.parquet,
     read with ts < 2022-01-01 inside the read call, with random holes cut into it (most of them around scheduled exits,
     so that the gap rule moves those exits, some exactly at the rule's 30-minute edge), and at least 10,000 random orders
     on 15 sleeves: market, stop, limit and OCO entries; absolute, distance, tiny and wrong-side stops; targets, trails and
     break-evens; time exits with and without the gap rule; hold extensions (some with xh at or before x); both refusals;
     void_le on market and pending entries; rule exits followed by an after_exit_of order; orders emitted from OnBar;
     overlapping market windows; targeted shapes (a stop hit on the last bar before a hole, a hold whose barrier and
     revision tests disagree, a hold ahead on its fill bar, a hold granted after a stop on the last bar before a hole).
     The lab reference of each sleeve is built only with the lab's functions: goldlab.data.exit_index (gap rule),
     tracks/trend/strategy.py _first_touch (OCO side), lab/r2/recalc.py _crypto_fp_hours (void_le), autopsy/payoff
     variants.hold_decision and H (hold), payoff common.fills with variants.refuse (refusal 1, d0 as
     validation_hi/vhi_sleeves.stop_distance_at_fill), synthesis_B common simulate_filtered (refusal 2),
     goldlab.sim.simulate (one position per sleeve, r2.costs). Every trade must be identical: entry and exit times, side,
     reason, entry, initial stop and exit prices bit for bit. Trades still open at the frame end are excluded. Also: every
     PREFUSE is in the lab's refused set, the HOLD status of every taken trade with an extension (its last HOLD a grant)
     equals variants.hold_decision's, and in the full run every coverage counter (result.json "coverage_total") is above 0.
  2. The same replay with PapOnBarrier called once every 61 minutes only: PapOnBar's own barrier must give the same events
     (a HOLD's barrier time aside) and the same trades open at the end.
  3. The hand-built scenarios of the simulator map (results/live/brain_maps_2026-11-11.json, map 'simulateur', section
     6: A to I2; the swap cases K and the no_overlap=False table H' do not apply to the paper) on xauusd 2021: lab and
     paper identical, and the map's hand formulas hold.
  4. The unit worlds of test_paper.cpp (59 checks).
  5. The sanitizer build (address, undefined behaviour, checked containers): the unit worlds and the same replays, with
     events byte for byte equal to the plain build's.
  6. End to end through the S0 driver: src/ as S0 left it (commit 399837f, read with git show) with this CR_Paper.mqh and
     the clock double, the ten sleeves switched to CR_Rule_Script and fed with the lab's own orders on the frames rebuilt
     from the bar exports (ref_lab.py --frame rebuilt), 2013-2021 (2021 with --quick): every paper trade of the journal
     equals the lab's trade, prices bit for bit; the sanitizer build writes the same journal.
--exe tests another binary built from test_paper.cpp; --mutants builds nine broken engines (MUTANTS) and requires the quick
test to fail on each (outputs in check/out/test_paper_mutant/, mutants.json).
Outputs: check/out/test_paper/ (result.json and per-market events; the bar files are deleted unless --keep).
In sample only: every frame is read with ts < 2022-01-01 inside the read call.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

_NB = os.environ.get("NUMBA_CACHE_DIR", "")
if not _NB.startswith("/tmp/"):
    _NB = "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/numba"
# a cache of its own: the lab's numba kernels are imported here under private module names, and a cache entry written
# under another module name cannot be loaded back
os.environ["NUMBA_CACHE_DIR"] = os.path.join(_NB, "t3_paper")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROBOT = os.path.dirname(HERE)
LAB = os.path.dirname(ROBOT)
OUT = os.path.join(HERE, "out", "test_paper")
CUT = pd.Timestamp("2022-01-01", tz="UTC")
sys.path.insert(0, HERE)
sys.path.insert(0, LAB)
sys.path.insert(0, os.path.join(LAB, "r2", "tracks", "validation_hi"))
from build import build  # noqa: E402
import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
from goldlab.sim import _DEFAULTS as SIM_DEFAULTS, simulate  # noqa: E402
import vhi_lens as L  # noqa: E402   (only its load_file: the lens modules under private names)

PC = L.load_file(os.path.join(L.AUTOPSY, "payoff", "common.py"), "t3_payoff_common")
PV = L.load_file(os.path.join(L.AUTOPSY, "payoff", "variants.py"), "t3_payoff_variants", {"common": PC})
SB = L.load_file(os.path.join(L.AUTOPSY, "synthesis_B", "common.py"), "t3_sB_common")
REC = L.load_file(os.path.join(LAB, "r2", "recalc.py"), "t3_recalc")
TRD = L.load_file(os.path.join(LAB, "tracks", "trend", "strategy.py"), "t3_strategy_trend")

MARKETS = {"xauusd": 0, "us100": 1, "btcusd": 2, "ethusd": 3}
VOL = {"xauusd": 0.0012, "us100": 0.0018, "btcusd": 0.006, "ethusd": 0.008}       # a typical hour's move, fraction of price
# slippage rows of src/CR_Registry.mqh RegSym (checked against the file below) = lab/r2/fp_costs.json
SLIP = {"xauusd": (0.3, 1.0), "us100": (0.2, 0.5), "btcusd": (0.5, 1.5), "ethusd": (0.7, 2.0)}
BAR = np.dtype([("t", "<i8"), ("sym", "<i4"), ("s", "<i4"), ("bo", "<f8"), ("bh", "<f8"), ("bl", "<f8"), ("bc", "<f8"),
                ("ao", "<f8"), ("ah", "<f8"), ("al", "<f8"), ("ac", "<f8")])
ROWF = [("kind", "<i8"), ("emit_kind", "<i8"), ("emit_t", "<i8"), ("sleeve", "<i8"), ("oid", "<i8"), ("side", "<i8"), ("etype", "<i8"),
        ("level", "<f8"), ("level2", "<f8"), ("t_from", "<i8"), ("t_to", "<i8"), ("after_exit_of", "<i8"), ("expiry_excl", "<i8"),
        ("stop", "<f8"), ("stop_dist", "<f8"), ("trail", "<f8"), ("be", "<f8"), ("target", "<f8"), ("target_dist", "<f8"),
        ("x_sched", "<i8"), ("x_gap", "<i8"), ("xh", "<i8"), ("xh_r", "<f8"), ("refuse", "<i8"), ("void_le", "<i8"), ("dec", "<i8"),
        ("group", "<i8")]
ROW = np.dtype(ROWF)
REASON = {0: "stop", 1: "target", 2: "time", 3: "trail", 7: "gap"}
SPARSE = 61                                    # the sparse replay calls PapOnBarrier once every 61 minutes
CHAINS = ["market", "market_gap", "stop_entry", "limit_entry", "oco", "hold_r1", "hold_mixed", "void_le_r2", "void_le",
          "refuse1", "refuse2", "exit_reversal", "onbar_stop", "limit_window", "overlap_market"]
REFUSE = {"hold_r1": 1, "void_le_r2": 2, "refuse1": 1, "refuse2": 2}
SPACING_MIN = {"market": 300, "market_gap": 600, "stop_entry": 600, "limit_entry": 600, "oco": 480, "hold_r1": 900,
               "hold_mixed": 900, "void_le_r2": 300, "void_le": 300, "refuse1": 400, "refuse2": 400, "exit_reversal": 600,
               "onbar_stop": 1440, "limit_window": 2880, "overlap_market": 1440}


def secs(ix):
    return pd.DatetimeIndex(ix).tz_convert("UTC").as_unit("s").asi8.astype(np.int64)


def frame(sym, start=None):
    """the in-sample M1 frame (FP costs), cut inside the read call"""
    filt = [("ts", "<", CUT)] + ([("ts", ">=", pd.Timestamp(start, tz="UTC"))] if start else [])
    m1 = pd.read_parquet(os.path.join(LAB, "data", "fp", f"{sym}_m1.parquet"), filters=filt)
    assert len(m1) and m1.index.max() < CUT and m1.index.is_monotonic_increasing and m1.index.is_unique
    return m1


def registry_rows_ok():
    """the slippage of the test equals CR_Registry.mqh's RegSym rows"""
    txt = open(os.path.join(ROBOT, "src", "CR_Registry.mqh")).read()
    ok = True
    for sym, (mkt, stp) in SLIP.items():
        lab = f'"{sym}"'
        line = [ln for ln in txt.splitlines() if "RegSym(" in ln and lab in ln]
        ok &= len(line) == 1 and f", {mkt}, {stp}," in line[0]
    return ok


# ======================================================================================== random orders and holes
class Gen:
    """random orders of one market: pass 1 times and holes on the base frame, pass 3 prices on the frame with holes"""

    def __init__(self, sym, m1, rng, n_per_chain):
        self.sym, self.rng, self.n = sym, rng, n_per_chain
        self.t = secs(m1.index)
        self.a = {c: m1[c].to_numpy() for c in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac")}
        self.p = self.a["bo"]
        self.sm = SLIP[sym][0] * 1e-4
        self.orders, self.exits, self.holes = [], [], []
        self.oid = 10_000_000
        self.seq = 0
        self.targeted = {"hold_flip": 0, "stop_on_L": 0, "hold_fill_bar": 0, "hold_stop_on_L": 0, "hole_edge": 0}

    def next_bar_time(self, t):
        i = int(np.searchsorted(self.t, t))
        return int(self.t[min(i, len(self.t) - 1)])

    def price(self, t):
        i = int(np.searchsorted(self.t, t))
        return float(self.p[min(i, len(self.p) - 1)])

    def u(self, t):
        return self.price(t) * VOL[self.sym]

    def new(self, sl, side, etype, t_from, t_to, **kw):
        self.oid += 1
        self.seq += 1
        o = dict(kind=0, emit_kind=0, emit_t=t_from, sleeve=sl, oid=self.oid, side=side, etype=etype, level=0.0, level2=0.0,
                 t_from=t_from, t_to=t_to, after_exit_of=0, expiry_excl=0, stop=0.0, stop_dist=0.0, trail=0.0, be=0.0, target=0.0,
                 target_dist=0.0, x_sched=0, x_gap=0, xh=0, xh_r=0.0, refuse=REFUSE.get(CHAINS[sl], 0), void_le=0, dec=t_from,
                 group=0, seq=self.seq)
        o.update(kw)
        self.orders.append(o)
        return o

    def plan(self, o, stops=("dist", "abs"), wrong=0.0, tiny=0.0, target=0.3, trail=0.25, be=0.15):
        """price multipliers of an order (units of a typical hour's move), applied in pass 3"""
        r = self.rng
        x = r.random()
        if o["etype"] == 3:
            stops = ("dist",)
        if x < wrong and o["etype"] != 3:
            o["_stop"] = ("wrong", r.uniform(0.0, 2.0))
        elif x < wrong + tiny:
            o["_stop"] = (stops[r.integers(len(stops))], r.uniform(0.005, 0.25))
        else:
            o["_stop"] = (stops[r.integers(len(stops))], r.uniform(0.3, 6.0))
        if o["etype"] in (1, 2):
            o["_level"] = r.uniform(-0.5, 3.0)
        if o["etype"] == 3:                                    # a fifth of the brackets so tight that one bar touches both
            w = 0.08 if r.random() < 0.2 else 2.0
            o["_level"] = (r.uniform(0.0, w), r.uniform(0.0, w))
        if r.random() < target:
            o["_target"] = ("dist" if o["etype"] == 3 else ("dist", "abs")[r.integers(2)], r.uniform(0.5, 10.0))
        if r.random() < trail:
            o["_trail"] = r.uniform(0.3, 5.0)
        if r.random() < be:
            o["_be"] = r.uniform(0.3, 5.0)

    def bare(self, o):
        """no stop plan, target, trail or break-even (the targeted orders set their own stop)"""
        for k in ("_stop", "_target", "_trail", "_be"):
            o.pop(k, None)

    # ---------------------------------------------------------------------------------- holes
    def hole_after(self, x, a=None):
        """no bar in [x, x + 30 min]: the gap rule moves the exit to the last bar before x"""
        if a is None:
            a = 0 if self.rng.random() < 0.4 else int(self.rng.integers(1, 121)) * 60
        self.holes.append((x - a, x + 1800 + int(self.rng.integers(1, 361)) * 60))

    def hole_short(self, x):
        """bars from x to x + c (c < 30 min) removed: the next bar is still inside the 30-minute window"""
        a = int(self.rng.integers(0, 61)) * 60
        c = int(self.rng.integers(1, 30)) * 60
        self.holes.append((x - a, x + c))

    def hole_edge(self, x):
        """the exact edge of gl.exit_index: no bar in [x - a, x + 30 min) (the next bar, if the data has it, starts at x + 30
        min: still the exit bar) or in [x - a, x + 31 min) (the next bar starts after x + 30 min: the gap rule applies)"""
        a = int(self.rng.integers(0, 61)) * 60
        self.holes.append((x - a, x + 1800 + (60 if self.rng.random() < 0.5 else 0)))
        self.targeted["hole_edge"] += 1

    def hole_fill(self, t_from, x):
        """no bar from just after the activation bar to x + 30 min: the gap rule lands on the activation (fill) bar"""
        act = self.next_bar_time(t_from)
        if act < x:
            self.holes.append((act + 60, x + 1800 + int(self.rng.integers(1, 241)) * 60))

    def gap_holes(self, o, p_after=0.25, p_short=0.1, p_fill=0.05, p_edge=0.08):
        x, r = o["x_sched"], self.rng.random()
        if r < p_after:
            self.hole_after(x)
        elif r < p_after + p_short:
            self.hole_short(x)
        elif r < p_after + p_short + p_fill:
            self.hole_fill(o["t_from"], x)
        elif r < p_after + p_short + p_fill + p_edge:
            self.hole_edge(x)

    # ---------------------------------------------------------------------------------- targeted orders
    def fill_px(self, i, side):
        return self.a["ao"][i] * (1 + self.sm) if side > 0 else self.a["bo"][i] * (1 - self.sm)

    def hold_flip(self, o):
        """a hold order whose 1 R test differs between the last two bars before a hole starting at x0: the barrier's
        decision (on the last bar) and the gap revision's (on the bar before it) disagree, in either direction"""
        r, A = self.rng, self.a
        t, side = o["t_from"], o["side"]
        ia = int(np.searchsorted(self.t, t))
        x0 = t + int(r.integers(30, 721)) * 60
        iL = int(np.searchsorted(self.t, x0)) - 1
        if ia >= len(self.t) or iL - ia < 2 or self.t[ia] > o["t_to"]:
            return False
        fp = self.fill_px(ia, side)
        mk = A["bc"] if side > 0 else A["ac"]
        g1, g0 = side * (mk[iL] - fp), side * (mk[iL - 1] - fp)
        lo, hi = min(g0, g1), max(g0, g1)
        if lo <= 0 or hi - lo <= 1e-9 * abs(fp):
            return False
        rk = 0.5 * (lo + hi)
        if (side > 0 and A["bl"][ia:iL + 1].min() <= fp - rk) or (side < 0 and A["ah"][ia:iL + 1].max() >= fp + rk):
            return False                                       # the stop would end the trade before L
        self.bare(o)
        o.update(stop=0.0, stop_dist=float(rk), x_sched=x0, x_gap=1, xh=x0 + int(r.integers(5, 1441)) * 60, xh_r=1.0)
        self.holes.append((x0, x0 + 1800 + int(r.integers(1, 241)) * 60))
        self.targeted["hold_flip"] += 1
        return True

    def hold_fill_bar(self, o):
        """a hold order ahead by 1 R at the close of its fill bar, with no bar from just after the fill bar to x0 + 30 min:
        the barrier grants the hold on the fill bar, the gap revision withdraws it (the exit bar is the fill bar, which
        the lab's hold_decision never counts), and the time exit waits for the first bar after the hole. The order is
        moved to the first bar of the next 240 that qualifies."""
        r, A = self.rng, self.a
        side = o["side"]
        i0 = int(np.searchsorted(self.t, o["t_from"]))
        for ia in range(i0, min(i0 + 240, len(self.t) - 2)):
            fp = self.fill_px(ia, side)
            g = side * ((A["bc"] if side > 0 else A["ac"])[ia] - fp)
            rk = 0.5 * g
            if rk <= 1e-9 * fp or (side > 0 and A["bl"][ia] <= fp - rk) or (side < 0 and A["ah"][ia] >= fp + rk):
                continue
            ta = int(self.t[ia])
            x0 = ta + int(r.integers(2, 121)) * 60
            hole_end = x0 + 1800 + int(r.integers(1, 241)) * 60
            self.bare(o)
            o.update(t_from=ta, t_to=ta, emit_t=ta, dec=ta, stop=0.0, stop_dist=float(rk), x_sched=x0, x_gap=1,
                     xh=x0 + int(r.integers(5, 1441)) * 60, xh_r=1.0, _end=hole_end)
            self.holes.append((ta + 60, hole_end))
            self.targeted["hold_fill_bar"] += 1
            return True
        return False

    def hold_stop_on_L(self, o):
        """a hold order stopped on L, the last bar before a hole at x0, while ahead by 1 R at the close of the bar before
        L: the barrier finds the trade exited, the revision's re-test (on the bar before L) grants the hold; with xh after
        the hole the stop exit stands, with xh inside the same hole the time exit at L's open replaces it (PREVISE)"""
        r, A = self.rng, self.a
        side = o["side"]
        ia = int(np.searchsorted(self.t, o["t_from"]))
        if ia >= len(self.t) - 3 or self.t[ia] > o["t_to"]:
            return False
        fp = self.fill_px(ia, side)
        for iL in range(ia + 2, min(ia + 600, len(self.t) - 1)):
            if side > 0:
                room = fp - A["bl"][ia:iL].min()                 # the stop must stay below every low before L
                dn = fp - A["bl"][iL]                            # and be hit on L
                up = A["bc"][iL - 1] - fp                         # ahead by >= 1 R at the close of the bar before L
            else:
                room = A["ah"][ia:iL].max() - fp
                dn = A["ah"][iL] - fp
                up = fp - A["ac"][iL - 1]
            hi = min(dn, up)
            if room > 0 and hi - room > 1e-7 * fp:
                rk = 0.5 * (room + hi)
                tl = int(self.t[iL])
                x0 = tl + int(r.integers(1, 61)) * 60
                hole_end = x0 + 1800 + int(r.integers(60, 241)) * 60
                if r.random() < 0.5:
                    xh = hole_end + int(r.integers(5, 601)) * 60      # after the hole: the stop exit on L stands
                else:
                    xh = x0 + int(r.integers(1, (hole_end - 1800 - x0) // 60)) * 60   # same hole: exit_index(xh) = L
                self.bare(o)
                o.update(stop=0.0, stop_dist=float(rk), x_sched=x0, x_gap=1, xh=xh, xh_r=1.0, _end=hole_end)
                self.holes.append((tl + 60, hole_end))
                self.targeted["hold_stop_on_L"] += 1
                return True
        return False

    def stop_on_L(self, o):
        """a gap-rule order whose absolute stop is first hit on the last bar before a hole around x: the stop exit
        booked on that bar is then replaced by the time exit at its open (PREVISE)"""
        r, A = self.rng, self.a
        t, side = o["t_from"], o["side"]
        ia = int(np.searchsorted(self.t, t))
        x = t + int(r.integers(30, 1441)) * 60
        ix = int(np.searchsorted(self.t, x)) - 1
        if ia >= len(self.t) or ix - ia < 3 or self.t[ia] > o["t_to"]:
            return False
        ext = A["bl"][ia + 1:ix + 1] if side > 0 else -A["ah"][ia + 1:ix + 1]
        iL = ia + 1 + int(np.argmin(ext))                     # its first lowest low (long) / highest high (short)
        fp = self.fill_px(ia, side)
        if side > 0:
            prev, lo = A["bl"][ia:iL].min(), A["bl"][iL]
            st = 0.5 * (lo + prev)
            if not (lo < prev and st < fp):
                return False
        else:
            prev, hi = A["ah"][ia:iL].max(), A["ah"][iL]
            st = 0.5 * (hi + prev)
            if not (hi > prev and st > fp):
                return False
        self.bare(o)
        o.update(stop=float(st), stop_dist=0.0, x_sched=x, x_gap=1)
        self.holes.append((int(self.t[iL]) + 60, x + 1800 + int(r.integers(1, 241)) * 60))
        self.targeted["stop_on_L"] += 1
        return True

    # ---------------------------------------------------------------------------------- chains (pass 1)
    def chain(self, sl):
        name = CHAINS[sl]
        r = self.rng
        span0, span1 = int(self.t[0]) + 86400, int(self.t[-1]) - 86400
        mean = SPACING_MIN[name] * 60
        need = self.n * mean * 2
        start = int(r.integers(span0, max(span0 + 1, span1 - need)))
        t = self.next_bar_time(start)
        k = 0
        while k < self.n and t < span1:
            t = t - t % 60
            side = 1 if r.random() < 0.5 else -1
            end = t
            if name in ("market", "market_gap", "refuse1", "refuse2", "hold_mixed"):
                et = 0
                if name in ("refuse1", "refuse2", "hold_mixed"):
                    et = int(r.choice([0, 0, 1, 2]))
                w = int(r.choice([0, 0, 60, 300]))
                o = self.new(sl, side, et, t, t + w)
                end = t + w
                if et:
                    o["expiry_excl"] = t + int(r.integers(5, 481)) * 60
                    end = o["expiry_excl"] - 1
                self.plan(o, wrong=0.1 if name == "refuse2" else 0.03, tiny=0.35 if name.startswith("refuse") else 0.02,
                          trail=0.3 if name == "market_gap" else 0.25)
                if name == "market":
                    if r.random() < 0.95:
                        o["x_sched"] = t + int(r.integers(2, 1441)) * 60
                    else:
                        o["_stop"] = ("dist", r.uniform(0.3, 2.0))
                elif name == "market_gap":
                    if not (r.random() < 0.35 and self.stop_on_L(o)):
                        o["x_sched"], o["x_gap"] = t + int(r.integers(5, 1441)) * 60, 1
                        self.gap_holes(o, 0.3, 0.12, 0.12)
                elif name in ("refuse1", "refuse2"):
                    o["x_sched"], o["x_gap"] = t + int(r.integers(5, 1441)) * 60, int(r.random() < 0.5)
                    if o["x_gap"]:
                        self.gap_holes(o)
                else:                                                   # hold_mixed
                    rr = r.random()
                    if not (et == 0 and ((rr < 0.3 and self.hold_flip(o)) or (0.3 <= rr < 0.5 and self.hold_fill_bar(o))
                                         or (0.5 <= rr < 0.7 and self.hold_stop_on_L(o)))):
                        self.hold(o)
                    end = max(end, o["t_to"], o.get("_end", end))
            elif name in ("stop_entry", "limit_entry"):
                et = 1 if name == "stop_entry" else 2
                w = int(r.choice([0, 60, 300]))
                o = self.new(sl, side, et, t, t + w, expiry_excl=t + int(r.integers(5, 481)) * 60)
                end = max(o["expiry_excl"] - 1, t + w)
                self.plan(o, wrong=0.03, target=0.4)
                o["x_sched"] = t + int(r.integers(30, 1441)) * 60
                if r.random() < 0.6:
                    o["x_gap"] = 1
                    self.gap_holes(o, 0.2, 0.1, 0.0)
            elif name == "oco":
                o = self.new(sl, 0, 3, t, t, expiry_excl=t + int(r.integers(30, 481)) * 60)
                end = o["expiry_excl"] - 1
                self.plan(o, target=0.15, trail=0.5, be=0.1)
                o["x_sched"], o["x_gap"] = t + int(r.integers(60, 2881)) * 60, 1
                self.gap_holes(o, 0.25, 0.1, 0.0)
            elif name == "hold_r1":
                o = self.new(sl, side, 0, t, t + 300)
                end = t + 300
                self.plan(o, stops=("dist",), tiny=0.1, target=0.1, trail=0.1, be=0.05)
                if not (r.random() < 0.3 and self.hold_flip(o)):
                    self.hold(o)
            elif name in ("void_le_r2", "void_le"):
                et = 0 if (name == "void_le_r2" or r.random() < 0.7) else int(r.choice([1, 2]))
                o = self.new(sl, side, et, t, t + 300, void_le=1, x_gap=1)
                end = t + 300
                if et:                                                  # armed void_le: the wrapper's entry_i is the activation bar
                    o["expiry_excl"] = t + int(r.integers(5, 2881)) * 60
                    end = o["expiry_excl"] - 1
                self.plan(o, stops=("dist",), wrong=0.0, tiny=0.15 if name == "void_le_r2" else 0.0, target=0.0, trail=0.0, be=0.0)
                o["x_sched"] = t + int(r.integers(-60, 721)) * 60
                if o["x_sched"] > t + 300:
                    rr = r.random()
                    if rr < 0.3:
                        self.hole_fill(t, o["x_sched"])
                    elif rr < 0.5:
                        self.hole_after(o["x_sched"])
                    elif rr < 0.6:
                        self.hole_short(o["x_sched"])
            elif name == "exit_reversal":
                end = self.reversal(sl, side, t)
            elif name == "onbar_stop":
                o = self.new(sl, side, 1, t, t, emit_kind=1)            # the emission bar is chosen in pass 3
                o["_onbar"] = True
                o["x_sched"] = t + int(r.integers(120, 2881)) * 60
                end = t + 3600
            elif name == "limit_window":
                o = self.new(sl, side, 2, t, t + 300, expiry_excl=t + 3600)
                end = t + 3599
                self.plan(o, stops=("dist",), target=0.2, trail=0.1, be=0.1)
                o["_level"] = r.uniform(-0.3, 1.0)
                o["x_sched"] = t + int(r.integers(120, 241)) * 60
            elif name == "overlap_market":
                kmax = int(r.integers(2, 5))
                for j in range(kmax):
                    m = t + 60 * j
                    o = self.new(sl, 1 if r.random() < 0.5 else -1, 0, m, m + 60)
                    self.plan(o, stops=("dist",), target=0.1, trail=0.1, be=0.0)
                    o["x_sched"], o["x_gap"] = m + 3600, 1
                    if r.random() < 0.15:
                        self.hole_after(o["x_sched"])
                    k += 1
                end = t + 60 * kmax
                k -= 1
            k += 1
            gap = int(r.exponential(mean)) + 120
            t = self.next_bar_time(max(end + 60, t + 60) + gap)

    def hold(self, o):
        r = self.rng
        t = o["t_from"]
        x0 = t + int(r.integers(30, 721)) * 60
        o["x_sched"], o["x_gap"] = x0, int(r.random() < 0.8)
        o["xh"], o["xh_r"] = x0 + int(r.integers(5, 1441)) * 60, 1.0
        if r.random() < 0.1:
            o["xh"] = x0 - int(r.integers(0, 241)) * 60          # xh <= x0: a pass leaves x at x0 (variants.H: max)
        if o["x_gap"]:
            rr = r.random()
            if rr < 0.35:
                self.hole_after(x0)
            elif rr < 0.45:
                self.hole_short(x0)
            elif rr < 0.5:
                self.hole_fill(t, x0)
            elif rr < 0.58:
                self.hole_edge(x0)
            if r.random() < 0.25 and o["xh"] > x0:
                self.hole_after(o["xh"])

    def reversal(self, sl, side, t):
        """N30's shape: a market order with an absolute stop; maybe later a rule exit [T, T+5] and the reverse order
        after it (after_exit_of)"""
        r = self.rng
        x = t + int(r.integers(60, 361)) * 60
        a = self.new(sl, side, 0, t, t + int(r.choice([0, 300])), x_sched=x)
        self.plan(a, stops=("abs",), target=0.0, trail=0.1, be=0.0)
        if r.random() < 0.6:
            lo, hi = t + 600, x - 600
            if r.random() < 0.15:
                lo = hi = t                                    # the rule exit resolves on the order's own fill bar
            if hi >= lo:
                T = int(r.integers(lo // 60, hi // 60 + 1)) * 60
                b = self.new(sl, -side, 0, T, T + 1500, after_exit_of=a["oid"], x_sched=x)
                self.plan(b, stops=("abs",), target=0.0, trail=0.1, be=0.0)
                self.seq += 1
                self.exits.append(dict(kind=1, emit_kind=0, emit_t=T, sleeve=sl, oid=a["oid"], t_from=T, t_to=T + 300, dec=T,
                                       seq=self.seq))
                if r.random() < 0.15:
                    self.holes.append((T, T + 360))
        return x

    # ---------------------------------------------------------------------------------- prices (pass 3, frame with holes)
    def prices(self, m1h):
        th = secs(m1h.index)
        cols = {c: m1h[c].to_numpy() for c in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac")}
        last_end = {}
        keep = []
        for o in self.orders:
            if o.get("_onbar"):
                i = int(np.searchsorted(th, o["t_from"]))
                if i >= len(th) - 1 or th[i] <= last_end.get(o["sleeve"], -1):
                    continue
                bt = int(th[i])
                o.update(t_from=bt, t_to=bt, emit_t=bt, dec=bt, expiry_excl=bt + 60, x_sched=bt + (o["x_sched"] - o["t_from"]))
                last_end[o["sleeve"]] = bt + 3600
                side = o["side"]
                if side > 0:
                    lv = cols["ao"][i] + (cols["ah"][i] - cols["ao"][i]) * self.rng.uniform(-0.2, 1.3)
                else:
                    lv = cols["bo"][i] - (cols["bo"][i] - cols["bl"][i]) * self.rng.uniform(-0.2, 1.3)
                o["level"] = float(lv)
                o["stop"] = float(lv - side * self.u(bt) * self.rng.uniform(0.5, 4.0))
                keep.append(o)
                continue
            p, u = self.price(o["t_from"]), self.u(o["t_from"])
            side, et = o["side"], o["etype"]
            ref = p
            if et == 1:
                o["level"] = ref = p + side * u * o["_level"]
            elif et == 2:
                o["level"] = ref = p - side * u * o["_level"]
            elif et == 3:
                o["level"], o["level2"] = p + u * o["_level"][0], p - u * o["_level"][1]
            if o.get("_stop"):
                kind, m = o["_stop"]
                if kind == "dist":
                    o["stop_dist"] = u * m
                elif kind == "abs":
                    o["stop"] = ref - side * u * m
                else:
                    o["stop"] = ref + side * u * m
            if "_target" in o:
                kind, m = o["_target"]
                if kind == "dist":
                    o["target_dist"] = u * m
                else:
                    o["target"] = ref + side * u * m
            if "_trail" in o:
                o["trail"] = u * o["_trail"]
            if "_be" in o:
                o["be"] = u * o["_be"]
            keep.append(o)
        self.orders = keep


def cut_holes(m1, holes):
    t = secs(m1.index)
    drop = np.zeros(len(t), bool)
    if holes:
        h = np.array(sorted(holes), np.int64)
        a = np.searchsorted(t, h[:, 0], "left")
        b = np.searchsorted(t, h[:, 1], "left")
        d = np.zeros(len(t) + 1, np.int64)
        np.add.at(d, a, 1)
        np.add.at(d, b, -1)
        drop = np.cumsum(d)[:-1] > 0
    return m1[~drop]


# ======================================================================================== the lab reference
def lab_chain(m1h, sym, orders, exits, refuse):
    """the lab's trades of one sleeve (DataFrame with oid), its refused oids and its 'ahead' oids"""
    idx = secs(m1h.index)
    N = len(idx)
    ah, bl, bo, bc = (m1h[c].to_numpy(np.float64) for c in ("ah", "bl", "bo", "bc"))

    def first_in(a, b):
        i = int(np.searchsorted(idx, a, "left"))
        return i if i < N and idx[i] <= b else -1

    ex_bar = {}
    for e in sorted(exits, key=lambda e: e["seq"]):
        ex_bar[e["oid"]] = first_in(e["t_from"], e["t_to"])
    n_void_exits = sum(1 for v in ex_bar.values() if v < 0)
    ts = lambda v: pd.to_datetime(np.asarray(v, np.int64), unit="s", utc=True)
    rows = []
    for o in sorted(orders, key=lambda o: (o["emit_t"], o["seq"])):
        if o["emit_kind"] == 1:
            ei = int(np.searchsorted(idx, o["t_from"]))
            assert ei < N and idx[ei] == o["t_from"]
        elif o["after_exit_of"]:
            e = ex_bar.get(o["after_exit_of"], -1)
            if e < 0:
                continue
            ei = first_in(max(o["t_from"], int(idx[e]) + 1), o["t_to"])
        else:
            ei = first_in(o["t_from"], o["t_to"])
        if ei < 0:
            continue
        crx = ex_bar.get(o["oid"], -1)
        hold = o["xh"] > 0 and o["x_sched"] > 0 and crx < 0
        if crx >= 0:
            xi = crx
        elif o["x_sched"] == 0:
            xi = -1
        elif o["x_gap"]:
            xi = int(gl.exit_index(m1h, ts([o["x_sched"]]))[0])
        else:
            xi = int(np.searchsorted(idx, o["x_sched"]))
        ext = -1
        if hold:
            ext = int(gl.exit_index(m1h, ts([o["xh"]]))[0]) if o["x_gap"] else int(np.searchsorted(idx, o["xh"]))
        nz = lambda v: np.nan if v == 0 else v
        rows.append(dict(entry_i=ei, side=o["side"], etype=o["etype"], level=nz(o["level"]) if o["etype"] else np.nan,
                         level2=o["level2"], expiry_i=(int(np.searchsorted(idx, o["expiry_excl"])) - 1) if o["etype"] else -1,
                         stop=nz(o["stop"]), stop_dist=nz(o["stop_dist"]), target=nz(o["target"]), target_dist=nz(o["target_dist"]),
                         exit_i=xi, trail=nz(o["trail"]), be=nz(o["be"]), oid=o["oid"], void_le=o["void_le"],
                         sched_exit=ts([o["x_sched"]])[0], hold=hold, ext_raw=ext))
    if not rows:
        return pd.DataFrame(), set(), set(), {}
    O = pd.DataFrame(rows)
    # OCO: the lab's own resolution of the side (trend/strategy.py _first_touch), then a stop entry of that side
    oco = (O.etype == 3).to_numpy()
    info = {"oco_both": set(), "rule_exits_void": n_void_exits}
    if oco.any():
        i0 = O.entry_i.to_numpy(np.int64)[oco]
        i1 = O.expiry_i.to_numpy(np.int64)[oco]
        up, dn = O.level.to_numpy(np.float64)[oco], O.level2.to_numpy(np.float64)[oco]
        hi, hs = TRD._first_touch(m1h["ah"].to_numpy(np.float64), bl, bo, bc, i0, i1, up, dn)
        keep = np.ones(len(O), bool)
        pos = np.flatnonzero(oco)
        keep[pos[hi < 0]] = False
        side = O.side.to_numpy().copy()
        lev = O.level.to_numpy().copy()
        et = O.etype.to_numpy().copy()
        side[pos] = np.where(hi >= 0, hs, 0)
        lev[pos] = np.where(hs > 0, up, dn)
        et[pos] = 1
        both = (hi >= 0) & (ah[np.clip(hi, 0, N - 1)] >= up) & (bl[np.clip(hi, 0, N - 1)] <= dn)
        info["oco_both"] = set(O.oid.to_numpy()[pos[both]].tolist())
        O = O.assign(side=side, level=lev, etype=et)[keep].reset_index(drop=True)
    # void_le: recalc.py's own wrapper (exit_i = gl.exit_index(sched_exit), kept only when exit_i > entry_i)
    vle = O.void_le.to_numpy() == 1
    if vle.any():
        sub = O[vle].reset_index(drop=True)
        kept = REC._crypto_fp_hours(lambda m1, **p: sub)(m1h)
        info["voided"] = set(sub.oid.tolist()) - set(kept.oid.tolist())
        O = pd.concat([O[~vle], kept]).sort_values("oid", kind="stable").reset_index(drop=True)
    O = O.sort_values("oid", kind="stable").reset_index(drop=True)          # oid grows with the emission order
    # hold extension: payoff variants.hold_decision (the trade alone, ahead by 1 R at the close before its clock exit bar)
    # and H (exit_i = max(ext, exit_i) where ahead)
    ahead_oids = set()
    clock = O.hold.to_numpy(bool)
    if clock.any():
        xi0 = O.exit_i.to_numpy(np.int64)
        ext = np.where(clock, np.maximum(O.ext_raw.to_numpy(np.int64), xi0), xi0)
        I = pd.DataFrame({"clock": clock, "ext1": ext, "ext2": ext, "r0": np.zeros(len(O))}, index=O.index)   # H returns r0
        ahead = PV.hold_decision(m1h, O, I, sym, False)
        ahead_oids = set(O.oid.to_numpy()[ahead].tolist())
        O, _ = PV.H(O, I, "t3", 1, ahead)
    costs = r2.costs(sym)
    refused = set()
    sim_cols = ["entry_i", "side", "etype", "level", "expiry_i", "stop", "stop_dist", "target", "target_dist", "exit_i", "trail", "be",
                "oid"]
    S = O[sim_cols].copy()
    if refuse == 1:
        fb, fp = PC.fills(m1h, S, sym, False)
        ao_, bo_ = m1h["ao"].to_numpy(), m1h["bo"].to_numpy()
        j = np.clip(fb, 0, N - 1)
        spread = np.where(fb >= 0, ao_[j] - bo_[j], np.nan)
        st, sd = S.stop.to_numpy(float), S.stop_dist.to_numpy(float)
        d0 = np.where(np.isfinite(st), np.abs(fp - st), sd)                 # vhi_sleeves.stop_distance_at_fill
        bad = np.asarray(PV.refuse(d0, spread), bool)
        refused = set(S.oid.to_numpy()[bad].tolist())
        t = simulate(m1h, S[~bad], sym=sym, costs=costs, no_overlap=True)
    elif refuse == 2:
        t = SB.simulate_filtered(m1h, S, sym, costs)
        refused = set(int(i) for i in t.attrs.get("refused_oids", []))
    else:
        t = simulate(m1h, S, sym=sym, costs=costs, no_overlap=True)
    return t, refused, ahead_oids, info


# ======================================================================================== the paper run and its trades
def write_inputs(d, m1h, sid, orders, exits, nsl):
    os.makedirs(d, exist_ok=True)
    rec = np.zeros(len(m1h), BAR)
    rec["t"] = secs(m1h.index)
    rec["sym"] = sid
    for c in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"):
        rec[c] = m1h[c].to_numpy(np.float64)
    rec["s"] = np.rint((rec["ao"] - rec["bo"]) * 100).astype(np.int32)
    rec.tofile(os.path.join(d, "bars.bin"))
    allr = sorted(orders + exits, key=lambda o: (o["emit_kind"], o["emit_t"], o["sleeve"], o["kind"], o["seq"]))
    rows = np.zeros(len(allr), ROW)
    for k, o in enumerate(allr):
        for name, _ in ROWF:
            rows[name][k] = o.get(name, 0)
    rows.tofile(os.path.join(d, "script.bin"))
    with open(os.path.join(d, "sleeves.txt"), "w") as f:
        f.write("\n".join([str(sid)] * nsl) + "\n")


def run_exe(exe, d, timeout=7200, sparse=1):
    t0 = time.time()
    r = subprocess.run([exe, "replay", d] + ([str(sparse)] if sparse > 1 else []), capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        raise RuntimeError(f"{exe} replay failed ({r.returncode}): {r.stdout[-2000:]} {r.stderr[-4000:]}")
    return time.time() - t0, json.load(open(os.path.join(d, "summary" + ("_sparse" if sparse > 1 else "") + ".json")))


def event_lines(path, what="events"):
    """the sorted lines of an events file (HOLD's barrier time blanked: it is the barrier that tested), or the trade rows
    of an open file without x_pending (which reads the last barrier)"""
    out = []
    with open(path) as f:
        for ln in f:
            p = ln.rstrip("\n").split(",")
            if what == "events":
                if p[0] == "HOLD":
                    p[4] = "*"
                out.append(",".join(p))
            elif p[0] == "trade":
                out.append(",".join(p[:-1]))
    return sorted(out)


def paper_read(d):
    """per sleeve: closed trades {oid: {...}}, refused oids, voided oids (with and without a fill), hold events, fails"""
    S = {}
    fails = []

    def sl(k):
        return S.setdefault(k, {"tr": {}, "refused": set(), "void_act": set(), "void_late": set(), "hold": {}, "revise": 0,
                                "revise_over_exit": 0, "pstop": 0, "seq": [], "last_hold": {}, "void_x": {}, "void_t": {}})

    with open(os.path.join(d, "events.csv")) as f:
        for ln in f:
            p = ln.rstrip("\n").split(",")
            if p[0] == "SUBMITFAIL":
                fails.append((int(p[1]), int(p[2]), int(p[3])))
                continue
            ev, s, oid, side, t, bar = p[0], int(p[1]), int(p[2]), int(p[3]), int(p[4]), int(p[5])
            px, stop, st0, reason, x = float(p[6]), float(p[7]), float(p[8]), int(p[9]), int(p[10])
            z = sl(s)
            if ev == "PFILL":
                z["tr"][oid] = {"side": side, "entry_time": t, "entry": px, "stop": st0, "x": x, "exit_time": None}
            elif ev in ("PEXIT", "PREVISE"):
                tr = z["tr"][oid]
                if ev == "PREVISE":
                    z["revise"] += 1
                    z["revise_over_exit"] += tr["exit_time"] is not None
                tr.update(exit_time=t, exit=px, reason=REASON.get(reason, str(reason)), revised=ev == "PREVISE")
            elif ev == "PVOID":
                z["void_x"][oid], z["void_t"][oid] = x, t
                if oid in z["tr"]:
                    z["tr"].pop(oid)
                    z["void_late"].add(oid)
                else:
                    z["void_act"].add(oid)
            elif ev == "PREFUSE":
                z["refused"].add(oid)
            elif ev == "HOLD":
                z["hold"].setdefault(oid, []).append((x, px, t))
                z["last_hold"][oid] = len(z["seq"])
            elif ev == "PSTOP":
                z["pstop"] += 1
            if ev != "PSTOP":
                z["seq"].append((ev, oid))
    opened = {}
    o = pd.read_csv(os.path.join(d, "open.csv"))
    for _, q in o[o.what == "trade"].iterrows():
        opened[int(q.sleeve)] = int(q.oid)
    return S, opened, fails


def compare_chain(lab_t, m1h, pap, open_oid, ahead, refused, hold_oids):
    """lab trades (one sleeve) against the paper's; returns counts and the first mismatches"""
    N = len(m1h)
    last_t = int(secs(m1h.index[-1:])[0])
    tr = pap["tr"]
    res = {"lab": int(len(lab_t)), "paper_closed": 0, "matched": 0, "censored": 0, "mismatch": [], "reasons": {}, "_matched": []}
    seen = set()
    for _, q in lab_t.iterrows():
        oid = int(q.oid)
        seen.add(oid)
        et, xt = int(q.entry_time.value // 10**9), int(q.exit_time.value // 10**9)
        p = tr.get(oid)
        lab_exit_bar = xt - (0 if q.reason == "time" else 60)
        censor = q.reason == "eod" or lab_exit_bar >= last_t
        if p is None or p["exit_time"] is None:
            if censor and (open_oid == oid or (p is not None and p["exit_time"] is None)):
                res["censored"] += 1
            else:
                res["mismatch"].append({"oid": oid, "why": "lab only" if p is None else "paper still open", "lab_reason": q.reason,
                                        "lab_entry": et, "lab_exit": xt})
            continue
        same = (p["entry_time"] == et and p["side"] == int(q.side) and p["entry"] == float(q.entry) and p["stop"] == float(q.stop)
                and p["exit_time"] == xt and p["exit"] == float(q.exit) and p["reason"] == q.reason)
        if same:
            res["matched"] += 1
            res["_matched"].append(oid)
            res["reasons"][q.reason] = res["reasons"].get(q.reason, 0) + 1
        elif censor:
            res["censored"] += 1
        else:
            res["mismatch"].append({"oid": oid, "why": "differs", "lab": [et, int(q.side), float(q.entry), float(q.stop), xt, float(q.exit), q.reason],
                                    "paper": [p["entry_time"], p["side"], p["entry"], p["stop"], p["exit_time"], p["exit"], p["reason"]]})
    for oid, p in tr.items():
        if p["exit_time"] is not None:
            res["paper_closed"] += 1
            if oid not in seen:
                res["mismatch"].append({"oid": oid, "why": "paper only", "paper": [p["entry_time"], p["side"], p["entry"], p["exit_time"],
                                                                                  p["reason"]]})
    res["refused_paper"] = len(pap["refused"])
    res["refused_not_in_lab_set"] = sorted(pap["refused"] - refused)[:10]
    # the hold status of every taken trade with an extension
    bad_hold = []
    held = 0
    for _, q in lab_t.iterrows():
        oid = int(q.oid)
        if oid not in hold_oids or oid not in tr or tr[oid]["exit_time"] is None:
            continue
        h = pap["hold"].get(oid, [])
        p_held = bool(h) and h[-1][1] != 0.0                 # last HOLD: a grant (px = the mark) or a withdrawal (px = 0)
        held += p_held
        if p_held != (oid in ahead):
            bad_hold.append(oid)
    res["held"] = held
    res["hold_status_differs"] = bad_hold[:10]
    res["n_hold_status_differs"] = len(bad_hold)
    res["mismatches"] = len(res["mismatch"])
    res["mismatch"] = res["mismatch"][:8]
    return res


def run_market(sym, exe, exe_san, args, rng):
    t0 = time.time()
    sid = MARKETS[sym]
    m1 = frame(sym)
    g = Gen(sym, m1, rng, args.orders // len(CHAINS) + 1)
    for sl in range(len(CHAINS)):
        g.chain(sl)
    g.holes += [(int(s), int(s) + int(rng.integers(31, 721)) * 60) for s in rng.choice(g.t[1000:-1000], 150)]
    m1h = cut_holes(m1, g.holes)
    g.prices(m1h)
    d = os.path.join(OUT, sym)
    if os.path.isdir(d):
        shutil.rmtree(d)
    write_inputs(d, m1h, sid, g.orders, g.exits, len(CHAINS))
    t_gen = time.time() - t0
    sec, summ = run_exe(exe, d)
    S, opened, fails = paper_read(d)
    res = {"bars": int(len(m1)), "bars_after_holes": int(len(m1h)), "holes": len(g.holes), "orders": len(g.orders),
           "rule_exits": len(g.exits), "submit_fail": len(fails), "paper_sec": round(sec, 1), "paper_ms": summ["ms"],
           "events": summ["events"], "chains": {}}
    t1 = time.time()
    tot = {"lab": 0, "matched": 0, "censored": 0, "mismatches": 0, "held": 0, "hold_status_differs": 0}
    cover = {"oco_both_touched": 0, "void_at_activation": 0, "void_late": 0, "revise": 0, "revise_over_stop_exit": 0,
             "hold_granted": 0, "hold_withdrawn": 0, "refused": 0, "after_exit_of_fills": 0, "pstop": 0,
             "gap_exit_moved_before_x": 0, "gap_exit_after_fill_bar_wait": 0, "rule_exits_void": 0,
             "held_then_gap_revision_of_xh": 0, "hold_withdrawn_fill_bar_wait": 0, "hold_pass_x_unchanged": 0,
             "hold_granted_at_revision": 0, "hold_granted_after_stop_on_L": 0, "void_late_armed": 0,
             "matched_market": 0, "matched_stop": 0, "matched_limit": 0, "matched_oco": 0,
             "exit_stop": 0, "exit_target": 0, "exit_time": 0, "exit_trail": 0, "exit_gap": 0,
             "targeted_hold_flip": g.targeted["hold_flip"], "targeted_stop_on_L": g.targeted["stop_on_L"],
             "targeted_hold_fill_bar": g.targeted["hold_fill_bar"], "targeted_hold_stop_on_L": g.targeted["hold_stop_on_L"],
             "targeted_hole_edge": g.targeted["hole_edge"], "gap_exit_at_x_plus_30": 0}
    for sl, name in enumerate(CHAINS):
        orders = [o for o in g.orders if o["sleeve"] == sl]
        exits = [e for e in g.exits if e["sleeve"] == sl]
        lab_t, refused, ahead, info = lab_chain(m1h, sym, orders, exits, REFUSE.get(name, 0))
        pap = S.get(sl, {"tr": {}, "refused": set(), "void_act": set(), "void_late": set(), "hold": {}, "revise": 0, "revise_over_exit": 0,
                         "pstop": 0, "seq": [], "last_hold": {}, "void_x": {}, "void_t": {}})
        hold_oids = {o["oid"] for o in orders if o["xh"] > 0}
        c = compare_chain(lab_t, m1h, pap, opened.get(sl), ahead, refused | info.get("voided", set()), hold_oids)
        c.update(orders=len(orders), refuse=REFUSE.get(name, 0))
        etype = {o["oid"]: o["etype"] for o in orders}
        for oid in c.pop("_matched"):
            cover["matched_" + ("market", "stop", "limit", "oco")[etype[oid]]] += 1
        for rs, nrs in c["reasons"].items():
            cover["exit_" + rs] += nrs
        x0 = {o["oid"]: o["x_sched"] for o in orders}
        for oid, h in pap["hold"].items():
            seq = [e for e, q in pap["seq"] if q == oid]
            for (hx, hpx, ht) in h:
                if hpx == 0:
                    continue
                cover["hold_pass_x_unchanged"] += hx == x0[oid]
                cover["hold_granted_at_revision"] += ht > x0[oid] + 1800
            if h[-1][1] != 0 and "PEXIT" in seq and seq.index("PEXIT") < seq.index("HOLD") and "PREVISE" not in seq:
                cover["hold_granted_after_stop_on_L"] += 1
        cover["void_late_armed"] += sum(1 for oid in pap["void_act"] if pap["void_x"].get(oid, 0) > pap["void_t"].get(oid, 0))
        res["chains"][name] = c
        for k in tot:
            tot[k] += c[k] if k != "hold_status_differs" else c["n_hold_status_differs"]
        aeo = {o["oid"] for o in orders if o["after_exit_of"]}
        cover["oco_both_touched"] += len(info.get("oco_both", set()) & set(pap["tr"]))
        cover["void_at_activation"] += len(pap["void_act"])
        cover["void_late"] += len(pap["void_late"])
        cover["revise"] += pap["revise"]
        cover["revise_over_stop_exit"] += pap["revise_over_exit"]
        cover["hold_granted"] += sum(1 for h in pap["hold"].values() for x, px, _ in h if px != 0)
        cover["hold_withdrawn"] += sum(1 for h in pap["hold"].values() for x, px, _ in h if px == 0)
        cover["refused"] += len(pap["refused"])
        cover["after_exit_of_fills"] += len(aeo & set(pap["tr"]))
        cover["pstop"] += pap["pstop"]
        xs = {o["oid"]: o["x_sched"] for o in orders if o["x_gap"] and o["x_sched"] > 0}
        if len(lab_t):
            for oid, rs, xt in zip(lab_t.oid.to_numpy(), lab_t.reason.to_numpy(), lab_t.exit_time.to_numpy()):
                x = xs.get(int(oid))
                if x is None or rs != "time":
                    continue
                xt = int(pd.Timestamp(xt).value // 10**9)
                cover["gap_exit_moved_before_x"] += xt < x
                cover["gap_exit_after_fill_bar_wait"] += xt > x + 1800
                cover["gap_exit_at_x_plus_30"] += xt == x + 1800
        cover["rule_exits_void"] += info.get("rule_exits_void", 0)
        for oid, h in pap["hold"].items():
            after = [e for e, q in pap["seq"][pap["last_hold"][oid]:] if q == oid]
            if h[-1][1] != 0 and "PREVISE" in after:
                cover["held_then_gap_revision_of_xh"] += 1
            if h[-1][1] == 0 and "PREVISE" not in after:
                cover["hold_withdrawn_fill_bar_wait"] += 1
    res["total"] = tot
    res["coverage"] = cover
    res["lab_sec"] = round(time.time() - t1, 1)
    res["gen_sec"] = round(t_gen, 1)
    res["pass"] = (tot["mismatches"] == 0 and tot["hold_status_differs"] == 0 and len(fails) == 0 and len(g.orders) >= args.orders
                   and all(not c["refused_not_in_lab_set"] for c in res["chains"].values()))
    # the same replay with PapOnBarrier called once every SPARSE minutes only: PapOnBar's own barrier must give the same
    # events (HOLD's barrier time aside) and the same trades open at the end
    sec_sp, _ = run_exe(exe, d, sparse=SPARSE)
    sp_ev = event_lines(os.path.join(d, "events.csv")) == event_lines(os.path.join(d, "events_sparse.csv"))
    sp_open = event_lines(os.path.join(d, "open.csv"), "open") == event_lines(os.path.join(d, "open_sparse.csv"), "open")
    res["sparse_barriers"] = {"barrier_every_min": SPARSE, "sec": round(sec_sp, 1), "events_identical": sp_ev,
                              "open_trades_identical": sp_open}
    res["pass"] &= sp_ev and sp_open
    if exe_san:
        ev_plain = open(os.path.join(d, "events.csv"), "rb").read()
        open_plain = open(os.path.join(d, "open.csv"), "rb").read()
        sec_s, _ = run_exe(exe_san, d)
        same = ev_plain == open(os.path.join(d, "events.csv"), "rb").read() and open_plain == open(os.path.join(d, "open.csv"), "rb").read()
        res["sanitizer"] = {"sec": round(sec_s, 1), "events_identical": same}
        res["pass"] &= same
    if not args.keep:
        os.remove(os.path.join(d, "bars.bin"))
    print(f"{sym:7s} orders {len(g.orders):6d} bars {len(m1h):8d} (holes {len(g.holes)}) lab trades {tot['lab']:6d} matched "
          f"{tot['matched']:6d} censored {tot['censored']:3d} mismatches {tot['mismatches']} held {tot['held']} | paper {sec:.1f} s"
          + f", sparse barriers identical={sp_ev and sp_open}"
          + (f", sanitizer {res['sanitizer']['sec']} s identical={res['sanitizer']['events_identical']}" if exe_san else "")
          + f" | {'PASS' if res['pass'] else 'FAIL'}", flush=True)
    return res


# ======================================================================================== the map's hand scenarios
def scenarios(exe, exe_san):
    """results/live/brain_maps_2026-11-11.json, map 'simulateur', section 6 (ported from its verify.py): lab = paper, and
    the hand formulas of the map"""
    m1 = frame("xauusd", "2021-01-01")
    c = r2.costs("xauusd")
    SL, SM = c.slip_bps * 1e-4, c.slip_mkt_bps * 1e-4
    idx = m1.index
    ts_ = secs(idx)
    bo, bh, bl, bc, ao, ah, al, ac = (m1[k].to_numpy() for k in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"))
    N = len(m1)
    I = lambda s: int(idx.searchsorted(pd.Timestamp(s, tz="UTC")))
    sc = {}                                     # name -> list of lab orders (dicts of simulate columns)
    hand = {}                                   # name -> [(what, oid position, field, value)]
    # A
    for i0 in range(I("2021-03-02 08:00"), I("2021-03-02 08:00") + 5000, 37):
        d = 2.0
        fp = ao[i0] * (1 + SM)
        st = fp - d
        j = i0
        while j < N and bl[j] > st:
            j += 1
        if i0 + 3 < j < i0 + 600 and bo[j] > st:
            break
    sc["A"] = [dict(entry_i=i0, side=1, stop_dist=2.0, exit_i=i0 + 5000)]
    hand["A"] = [("entry", ao[i0] * (1 + SM)), ("stop", ao[i0] * (1 + SM) - 2.0), ("exit", (ao[i0] * (1 + SM) - 2.0) * (1 - SL)),
                 ("exit_time", ts_[j] + 60), ("reason", "stop")]
    # B
    for i0 in range(I("2021-04-06 08:00"), I("2021-04-06 08:00") + 5000, 37):
        d = 2.0
        fp = bo[i0] * (1 - SM)
        st = fp + d
        j = i0
        while j < N and ah[j] < st:
            j += 1
        if i0 + 3 < j < i0 + 600 and ao[j] < st:
            break
    sc["B"] = [dict(entry_i=i0, side=-1, stop_dist=2.0, exit_i=i0 + 5000)]
    hand["B"] = [("entry", bo[i0] * (1 - SM)), ("exit", (bo[i0] * (1 - SM) + 2.0) * (1 + SL))]
    # C (long and short apart: the paper is always one position per sleeve)
    i0 = I("2021-05-11 09:00")
    x = i0 + 90
    sc["C_long"] = [dict(entry_i=i0, side=1, stop_dist=200.0, exit_i=x)]
    sc["C_short"] = [dict(entry_i=i0, side=-1, stop_dist=200.0, exit_i=x)]
    hand["C_long"] = [("exit", bo[x] * (1 - SM)), ("exit_time", ts_[x]), ("reason", "time")]
    hand["C_short"] = [("exit", ao[x] * (1 + SM)), ("exit_time", ts_[x])]
    # D: stop on the entry bar
    for i0 in range(I("2021-06-01 00:00"), I("2021-07-01 00:00")):
        if ao[i0] * (1 + SM) - bl[i0] > 3.0 and bo[i0] - bl[i0] > 2.5:
            break
    sc["D"] = [dict(entry_i=i0, side=1, stop_dist=1.5, exit_i=i0 + 500)]
    hand["D"] = [("exit", (ao[i0] * (1 + SM) - 1.5) * (1 - SL)), ("exit_time", ts_[i0] + 60)]
    # D2: stop inside the spread
    i0 = I("2021-05-11 09:00")
    d = (ao[i0] - bo[i0]) * 0.3
    sc["D2"] = [dict(entry_i=i0, side=1, stop_dist=d, exit_i=i0 + 500)]
    hand["D2"] = [("exit", (ao[i0] * (1 + SM) - d) * (1 - SL))]
    # E, E2: weekend gap through a long's stop; E3: a short's
    dgap = np.diff(idx.values).astype("timedelta64[m]").astype(int)
    for g_ in np.where(dgap > 2000)[0]:
        if bc[g_] - bo[g_ + 1] > 0.8:
            i0 = g_ - 3
            fp = ao[i0] * (1 + SM)
            st = bo[g_ + 1] + 0.5 * (bl[i0:g_ + 1].min() - bo[g_ + 1])
            if bl[i0:g_ + 1].min() > st > bo[g_ + 1] and st < fp:
                break
    sc["E"] = [dict(entry_i=i0, side=1, stop=st, exit_i=g_ + 3000)]
    sc["E2"] = [dict(entry_i=i0, side=1, stop=st, exit_i=g_ + 1)]
    hand["E"] = [("exit", bo[g_ + 1] * (1 - SL)), ("reason", "stop")]
    hand["E2"] = [("exit", bo[g_ + 1] * (1 - SM)), ("reason", "time")]
    for g2 in np.where(dgap > 2000)[0]:
        if ao[g2 + 1] - ac[g2] > 0.8:
            i3 = g2 - 3
            fp = bo[i3] * (1 - SM)
            st3 = ao[g2 + 1] - 0.5 * (ao[g2 + 1] - ah[i3:g2 + 1].max())
            if ah[i3:g2 + 1].max() < st3 < ao[g2 + 1] and st3 > fp:
                sc["E3"] = [dict(entry_i=i3, side=-1, stop=st3, exit_i=g2 + 3000)]
                hand["E3"] = [("exit", ao[g2 + 1] * (1 + SL))]
                break
    # F: stops on the wrong side
    i0 = I("2021-05-11 09:00")
    sc["F_long"] = [dict(entry_i=i0, side=1, stop=ao[i0] + 1.0, exit_i=i0 + 100)]
    sc["F_short"] = [dict(entry_i=i0, side=-1, stop=bo[i0] - 1.0, exit_i=i0 + 100)]
    hand["F_long"] = [("exit", bo[i0] * (1 - SL)), ("reason", "gap")]
    hand["F_short"] = [("exit", ao[i0] * (1 + SL)), ("reason", "gap")]
    # G: stop and target in one later bar -> stop
    found = None
    for d in (0.6, 0.8, 1.0, 1.5):
        for i0 in range(I("2021-06-01 00:00"), I("2021-09-01 00:00")):
            fp = ao[i0] * (1 + SM)
            if bl[i0] > fp - d and bh[i0] < fp + d and bl[i0 + 1] <= fp - d and bh[i0 + 1] >= fp + d and bo[i0 + 1] > fp - d:
                found = (i0, d)
                break
        if found:
            break
    i0, d = found
    sc["G"] = [dict(entry_i=i0, side=1, stop_dist=d, target_dist=d, exit_i=i0 + 100)]
    hand["G"] = [("reason", "stop")]
    # G2: target on the entry bar of a market order; G3: target gapped over a weekend
    for i0 in range(I("2021-06-01 00:00"), I("2021-09-01 00:00")):
        fp = ao[i0] * (1 + SM)
        if bh[i0] >= fp + 1.0 and bl[i0] > fp - 3.0:
            break
    sc["G2"] = [dict(entry_i=i0, side=1, stop_dist=3.0, target_dist=1.0, exit_i=i0 + 100)]
    hand["G2"] = [("exit", ao[i0] * (1 + SM) + 1.0), ("reason", "target")]
    gg = [q for q in np.where(dgap > 2000)[0] if bo[q + 1] - bc[q] > 0.8]
    if gg:
        q = gg[0]
        i0 = q - 3
        fp = ao[i0] * (1 + SM)
        tg = 0.5 * (max(bh[i0:q + 1].max(), fp) + bo[q + 1])
        if bh[i0:q + 1].max() < tg < bo[q + 1]:
            sc["G3"] = [dict(entry_i=i0, side=1, stop_dist=50.0, target=tg, exit_i=q + 3000)]
            hand["G3"] = [("exit", max(tg, bo[q + 1]))]
    # H: one position (five market orders); H2: a stop entry whose window starts while a trade is open; H2': after its exit
    i0 = I("2021-05-11 09:00")
    sc["H"] = [dict(entry_i=e, side=s, stop_dist=200.0, exit_i=x) for e, s, x in
               zip([i0, i0 + 10, i0 + 30, i0 + 31, i0 + 31], [1, -1, -1, 1, -1], [i0 + 30, i0 + 50, i0 + 60, i0 + 60, i0 + 60])]
    hand["H"] = [("count", 2)]
    lv = ah[i0 + 40:i0 + 200].max() - 0.01
    k = i0 + 40 + int(np.argmax(ah[i0 + 40:i0 + 200] >= lv))
    if ah[i0 + 20:i0 + 40].max() < lv:
        sc["H2"] = [dict(entry_i=i0, side=1, stop_dist=200.0, exit_i=i0 + 30),
                    dict(entry_i=i0 + 20, side=1, etype=1, level=lv, expiry_i=i0 + 200, stop_dist=200.0, exit_i=i0 + 400)]
        hand["H2"] = [("count", 1)]
        sc["H2b"] = [dict(entry_i=i0, side=1, stop_dist=200.0, exit_i=i0 + 30),
                     dict(entry_i=i0 + 31, side=1, etype=1, level=lv, expiry_i=i0 + 200, stop_dist=200.0, exit_i=i0 + 400)]
        hand["H2b"] = [("count", 2), ("entry_last", max(lv, ao[k]) * (1 + SL))]
    # I: exit_i <= entry_i; I2: no exit_i (the lab closes at the frame end 'eod'; the paper keeps it open)
    sc["I"] = [dict(entry_i=i0, side=1, stop_dist=200.0, exit_i=i0 - 5)]
    hand["I"] = [("exit", bo[i0 + 1] * (1 - SM)), ("exit_time", ts_[i0 + 1])]
    sc["I2"] = [dict(entry_i=i0, side=1, stop_dist=200.0)]
    hand["I2"] = [("open_at_end", 1)]
    names = list(sc)
    out = {"names": names, "submit_fail": 0, "scenarios": {}, "sanitizer_events_identical": True}
    ok = True
    for batch in range(0, len(names), 12):                       # at most CR_MAX_SL sleeves per replay
        bnames = names[batch:batch + 12]
        orders = []
        seq = 0
        for sl, name in enumerate(bnames):
            for o in sc[name]:
                seq += 1
                e = int(ts_[o["entry_i"]])
                xi = o.get("exit_i", -1)
                x = 0 if xi < 0 else (int(ts_[xi]) if xi < N else int(ts_[-1]) + 60 * (xi - N + 1))
                et = o.get("etype", 0)
                orders.append(dict(kind=0, emit_kind=0, emit_t=e, sleeve=sl, oid=1_000 + seq, side=o["side"], etype=et,
                                   level=o.get("level", 0.0), level2=0.0, t_from=e, t_to=e, after_exit_of=0,
                                   expiry_excl=int(ts_[o["expiry_i"]]) + 60 if et else 0, stop=o.get("stop", 0.0),
                                   stop_dist=o.get("stop_dist", 0.0), trail=0.0, be=0.0, target=o.get("target", 0.0),
                                   target_dist=o.get("target_dist", 0.0), x_sched=x, x_gap=0, xh=0, xh_r=0.0, refuse=0, void_le=0,
                                   dec=e, group=0, seq=seq))
        d = os.path.join(OUT, f"scenarios_{batch // 12}")
        if os.path.isdir(d):
            shutil.rmtree(d)
        write_inputs(d, m1, MARKETS["xauusd"], orders, [], len(bnames))
        run_exe(exe, d)
        S, opened, fails = paper_read(d)
        out["submit_fail"] += len(fails)
        ok &= not fails
        for sl, name in enumerate(bnames):
            lab_o = pd.DataFrame([{**SIM_DEFAULTS, **o} for o in sc[name]])         # sim.py:214-215 defaults on every row
            lab_o["oid"] = [o["oid"] for o in orders if o["sleeve"] == sl]
            t = simulate(m1, lab_o, sym="xauusd", costs=c, no_overlap=True)
            pap = S.get(sl, {"tr": {}, "refused": set(), "void_act": set(), "void_late": set(), "hold": {}, "revise": 0,
                             "revise_over_exit": 0, "pstop": 0, "seq": [], "last_hold": {}, "void_x": {}, "void_t": {}})
            cmp_ = compare_chain(t, m1, pap, opened.get(sl), set(), set(), set())
            closed = sorted([p for p in pap["tr"].values() if p["exit_time"] is not None], key=lambda p: p["entry_time"])
            checks = []
            for what, val in hand.get(name, []):
                if what == "count":
                    got = len(closed)
                elif what == "open_at_end":
                    got = int(opened.get(sl) is not None)
                elif what == "entry_last":
                    got = closed[-1]["entry"] if closed else None
                else:
                    got = closed[0][what] if closed else None
                good = (got == val) if isinstance(val, str) or what in ("count", "open_at_end", "exit_time") else \
                    (got is not None and abs(got - val) <= 1e-9 * max(1.0, abs(val)))
                checks.append({"what": what, "hand": val if isinstance(val, (str, int)) else float(val), "paper": got,
                               "ok": bool(good)})
            good = cmp_["mismatches"] == 0 and all(x["ok"] for x in checks)
            if name == "I2":
                good = good and cmp_["censored"] == 1
            ok &= good
            out["scenarios"][name] = {"lab_trades": int(len(t)), "matched": cmp_["matched"], "censored": cmp_["censored"],
                                      "mismatches": cmp_["mismatch"], "hand": checks, "pass": bool(good)}
        if exe_san:
            ev_plain = open(os.path.join(d, "events.csv"), "rb").read()
            run_exe(exe_san, d)
            same = ev_plain == open(os.path.join(d, "events.csv"), "rb").read()
            out["sanitizer_events_identical"] &= same
            ok &= same
        os.remove(os.path.join(d, "bars.bin"))
    out["pass"] = bool(ok)
    print(f"map scenarios: {sum(v['pass'] for v in out['scenarios'].values())}/{len(names)} pass "
          f"({', '.join(n for n in names if not out['scenarios'][n]['pass']) or 'all'})", flush=True)
    return out


# ======================================================================================== the S0 driver end to end
S0_COMMIT = "399837f"                         # the S0 state of src/ (SPEC 8: C's tests compile S0 files and its own)
E2E_CODES = "N30,OC4,BKB,BKE,F1B,F1E,NQB,GFP,D4H,ORX"
E2E_SYM = {"N30": "US100.r", "OC4": "US100.r", "BKB": "BTCUSD.r", "BKE": "ETHUSD.r", "F1B": "BTCUSD.r", "F1E": "ETHUSD.r",
           "NQB": "BTCUSD.r", "GFP": "XAUUSD.r", "D4H": "XAUUSD.r", "ORX": "XAUUSD.r"}
E2E_SYMS = ("XAUUSD.r", "US100.r", "BTCUSD.r", "ETHUSD.r")


def s0_tree():
    """src/ as S0 left it (git show, read only), with this step's CR_Paper.mqh; under build/ (git-ignored)"""
    d = os.path.join(ROBOT, "build", "test_paper_s0tree", "src")
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(d)
    ls = subprocess.run(["git", "-C", ROBOT, "ls-tree", "--name-only", S0_COMMIT, "--", "src/"], capture_output=True, text=True)
    names = [os.path.basename(x) for x in ls.stdout.split()]
    if ls.returncode or "CR_Main.mqh" not in names:
        return None
    for n in names:
        r = subprocess.run(["git", "-C", ROBOT, "show", f"{S0_COMMIT}:./src/{n}"], capture_output=True)
        if r.returncode:
            return None
        open(os.path.join(d, n), "wb").write(r.stdout)
    shutil.copy(os.path.join(ROBOT, "src", "CR_Paper.mqh"), os.path.join(d, "CR_Paper.mqh"))
    return d


def e2e_inputs(tag):
    """the bar exports of a tag (y2021: 2021; is: 2013-2021) and the lab's references on the frames rebuilt from them, made
    when missing by export_frames.py and ref_lab.py (S0's tools)"""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", NUMBA_CACHE_DIR=_NB)        # the tools' own (shared, warm) cache

    def tool(args):
        r = subprocess.run([sys.executable, "-I"] + args, env=env, capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(f"{os.path.basename(args[0])} failed ({r.returncode}): {(r.stdout + r.stderr)[-3000:]}")

    bars = {sy: os.path.join(HERE, "out", "bars", f"{sy}_{tag}.bin") for sy in E2E_SYMS}
    if not all(os.path.exists(v) for v in bars.values()):
        win = ["--from", "2021-01-01", "--to", "2022-01-01"] if tag == "y2021" else []
        tool([os.path.join(HERE, "export_frames.py")] + win + ["--tag", tag])
    ref = os.path.join(HERE, "out", "ref", f"rebuilt_{tag}")
    if not all(os.path.exists(os.path.join(ref, "script", f"{c}.csv")) and os.path.exists(os.path.join(ref, c, "trades.parquet"))
               for c in E2E_CODES.split(",")):
        tool([os.path.join(HERE, "ref_lab.py"), "--frame", "rebuilt", "--tag", tag, "--no-changes"])
    last = {m["broker"]: int(pd.Timestamp(m["last"]).value // 10**9)
            for m in json.load(open(os.path.join(HERE, "out", f"manifest_{tag}.json")))}
    return bars, ref, last


def e2e(sanitize, tag="y2021"):
    """the S0 driver (CR_Main minute contract, CR_Rule_Script, the S0 stubs, the clock double) with this CR_Paper.mqh replays
    2021 on the four symbols, the ten sleeves fed with the lab's own orders on the rebuilt 2021 frames: every paper trade
    of the journal (PFILL + PEXIT or PREVISE, PVOID dropped) must equal the lab's trade on the same frame, prices bit for
    bit (trades entered before the first barrier or exiting at the frame end excluded)"""
    import compare
    from build import replay as run_replay
    tree = s0_tree()
    if tree is None:
        return {"skipped": "git history of the S0 commit not available", "pass": True}
    bars, ref, last = e2e_inputs(tag)
    exe, warn = build(os.path.join(tree, "ClaudeRobot.mq5"), name="test_paper_e2e" + ("_san" if sanitize else ""), sanitize=sanitize,
                      subst=["CR_Clock.mqh=" + os.path.join(HERE, "dbl", "CR_Clock_dbl.mqh")])
    files = os.path.join(OUT, f"e2e_{tag}" + ("_san" if sanitize else ""))
    if os.path.isdir(files):
        shutil.rmtree(files)
    os.makedirs(os.path.join(files, "ClaudeRobot", "script"))
    for c in E2E_CODES.split(","):
        shutil.copy(os.path.join(ref, "script", f"{c}.csv"), os.path.join(files, "ClaudeRobot", "script", f"{c}.csv"))
    out, wall = run_replay(exe, files, bars, env={"MOCK_INPUT_InpScript": E2E_CODES}, fresh=False)
    rows = compare.read_journal(files)
    reb = compare.events(rows, "REBUILD").iloc[0]
    first_minute = int(reb["from"]) + 60 if int(reb["from"]) > 0 else int(reb["to"]) + 60
    void = {(r["code"], r["oid"]) for r in rows if r["ev"] == "PVOID"}
    kept = [r for r in rows if not (r["ev"] in ("PFILL", "PEXIT", "PREVISE") and (r["code"], r.get("oid")) in void)]
    ev = {}
    for r in rows:
        ev[r["ev"]] = ev.get(r["ev"], 0) + 1
    res = {"tag": tag, "build_warnings": warn, "replay": out, "wall_s": round(wall, 1), "first_minute": first_minute, "events": ev,
           "errors": [r for r in rows if r["ev"] == "ERROR"][:5], "per_sleeve": {}}
    ok = not warn and not res["errors"] and "SEND" not in ev
    for c in E2E_CODES.split(","):
        lab = pd.read_parquet(os.path.join(ref, c, "trades.parquet"))
        r = compare.cmp_trades(kept, lab, c, t_from=first_minute, t_to=last[E2E_SYM[c]] - 1)
        good = (r.get("lab_trades", 0) > 0 and r["pass"] and r.get("only_lab") == 0 and r.get("only_ea") == 0
                and r.get("same_exit_and_reason") == r.get("same_entry") == r.get("lab_trades")
                and r.get("entry_equal") == r.get("stop_equal") == r.get("exit_equal") == r.get("lab_trades"))
        r["voided"] = sum(1 for (cc, _) in void if cc == c)
        r["pass"] = bool(good)
        res["per_sleeve"][c] = r
        ok &= good
    res["pass"] = bool(ok)
    res["files"] = files
    return res


def e2e_both(with_sanitizer, tag="y2021"):
    t0 = time.time()
    out = {"plain": e2e(False, tag)}
    ok = out["plain"]["pass"]
    if with_sanitizer and "skipped" not in out["plain"]:
        out["sanitizer"] = e2e(True, tag)
        same = subprocess.run(["diff", "-r", "-q", os.path.join(out["plain"]["files"], "ClaudeRobot"),
                               os.path.join(out["sanitizer"]["files"], "ClaudeRobot")], capture_output=True, text=True)
        out["sanitizer"]["journal_identical_to_plain_build"] = same.returncode == 0
        ok &= out["sanitizer"]["pass"] and same.returncode == 0
    out["pass"] = bool(ok)
    out["sec"] = round(time.time() - t0, 1)
    p = out["plain"]
    if "skipped" in p:
        print(f"S0 driver end to end: skipped ({p['skipped']})", flush=True)
    else:
        n = sum(v.get("lab_trades", 0) for v in p["per_sleeve"].values())
        eq = sum(v.get("exit_equal", 0) for v in p["per_sleeve"].values())
        print(f"S0 driver end to end ({tag}, ten sleeves, lab orders through CR_Rule_Script): lab trades {n}, paper trades equal {eq}"
              + (f", sanitizer journal identical={out['sanitizer']['journal_identical_to_plain_build']}" if "sanitizer" in out else "")
              + f" | {'PASS' if ok else 'FAIL'} ({out['sec']} s)", flush=True)
    return out


# ======================================================================================== mutation checks (--mutants)
# each mutant breaks one rule of the engine; the quick test on gold and bitcoin must FAIL on every one of them
MUTANTS = {
    "no_barrier_in_PapOnBar": ("   PapSleeveBarrier(sl, b.t);                                   // (a no-op after PapOnBarrier(b.t))\n", ""),
    "no_hold_retest_at_revision": ("      if(!lfill && PapHoldPass(tr, tr.b_prev))", "      if(tr.held)"),
    "gap_edge_off_by_one": ("M <= g_pap_t[sl].q + CR_PAP_GAP", "M < g_pap_t[sl].q + CR_PAP_GAP"),
    "no_skip_on_exit_bar": ("bool busy = (g_pap_t[sl].st == CR_PT_OPEN) || (g_pap_lx[sl] != 0 && g_pap_lx[sl] == b.t);",
                            "bool busy = (g_pap_t[sl].st == CR_PT_OPEN);"),
    "refuse1_signed_distance": ("double d0 = PapOn(o.stop) ? MathAbs(fp - o.stop) : o.stop_dist;",
                                "double d0 = PapOn(o.stop) ? side * (fp - o.stop) : o.stop_dist;"),
    "oco_tie_side_flipped": ("if(hu && hd) side = (b.bc >= b.bo) ? -1 : 1;", "if(hu && hd) side = (b.bc >= b.bo) ? 1 : -1;"),
    "time_exit_on_fill_bar": ("   if(!first)\n     {\n      tr.b_prev = tr.b_last;", "   if(true)\n     {\n      tr.b_prev = tr.b_last;"),
    "no_late_void": ("   if(x0q && tr.o.void_le && tr.b_last.t == tr.act)", "   if(false)"),
    "armed_void_after_expiry": ("&& PapMinAfter(g_pap_q[i].o.x_sched + CR_PAP_GAP) < PapMinFrom(g_pap_q[i].o.expiry_excl))",
                                "&& g_pap_q[i].o.expiry_excl > M)"),
}


def mutants(argv_common):
    src = open(os.path.join(ROBOT, "src", "CR_Paper.mqh")).read()
    root = os.path.join(ROBOT, "build", "test_paper_mutants")
    res, ok = {}, True
    for name, (a, b) in MUTANTS.items():
        if src.count(a) != 1:
            res[name] = {"error": "the line to mutate is not in CR_Paper.mqh exactly once"}
            ok = False
            continue
        d = os.path.join(root, name)
        os.makedirs(d, exist_ok=True)
        shutil.copy(os.path.join(ROBOT, "src", "CR_Types.mqh"), d)
        with open(os.path.join(d, "CR_Paper.mqh"), "w") as f:
            f.write(src.replace(a, b, 1))
        exe, _ = build(os.path.join(d, "CR_Paper.mqh"), name="test_paper_mut_" + name, main=os.path.join(HERE, "test_paper.cpp"))
        r = subprocess.run([sys.executable, "-I", os.path.abspath(__file__), "--quick", "--no-sanitize", "--no-e2e",
                            "--markets", "xauusd,btcusd", "--exe", exe] + argv_common, capture_output=True, text=True, cwd=ROBOT)
        tail = [ln for ln in (r.stdout + r.stderr).splitlines() if ln.startswith(("worlds", "map", "xauusd", "btcusd", "test_paper"))]
        res[name] = {"exit": r.returncode, "caught": r.returncode != 0, "out": tail}
        ok &= r.returncode != 0
        print(f"mutant {name:28s} {'caught' if r.returncode else 'NOT CAUGHT'}", flush=True)
    with open(os.path.join(HERE, "out", "test_paper_mutant", "mutants.json"), "w") as f:
        json.dump({"pass": ok, "mutants": res}, f, indent=1)
    print(f"test_paper --mutants: {'PASS' if ok else 'FAIL'} ({sum(v.get('caught', False) for v in res.values())} of {len(res)} caught)")
    return 0 if ok else 1


# ======================================================================================== main
def build_exe(name, sanitize):
    exe, warn = build(os.path.join(ROBOT, "src", "CR_Paper.mqh"), name=name, main=os.path.join(HERE, "test_paper.cpp"),
                      sanitize=sanitize)
    return exe, warn


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="2,000 orders per market, no sanitizer replay of the markets")
    ap.add_argument("--no-sanitize", action="store_true")
    ap.add_argument("--orders", type=int, default=12000)
    ap.add_argument("--seed", type=int, default=20261112)
    ap.add_argument("--markets", default=",".join(MARKETS))
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--exe", help="test this replay binary instead of building src/CR_Paper.mqh (mutation checks)")
    ap.add_argument("--no-e2e", action="store_true", help="skip the S0 driver end-to-end replay")
    ap.add_argument("--mutants", action="store_true", help="mutation checks: the quick test must fail on each broken engine")
    ap.add_argument("--e2e-tag", choices=["y2021", "is"], help="its period: is = 2013-2021 (default), y2021 = 2021 (--quick)")
    a = ap.parse_args(argv)
    global OUT
    if a.exe or a.mutants:
        OUT = os.path.join(HERE, "out", "test_paper_mutant")              # never over the real result
    if a.mutants:
        os.makedirs(OUT, exist_ok=True)
        return mutants(["--seed", str(a.seed)])
    if a.quick:
        a.orders = 2000
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    res = {"seed": a.seed, "orders_per_market_asked": a.orders, "registry_slippage_rows": registry_rows_ok()}
    if a.exe:
        exe, warn = os.path.abspath(a.exe), []
        res["exe"] = exe
    else:
        exe, warn = build_exe("test_paper_plain", False)
    res["build_plain_warnings"] = warn
    exe_san = None
    if not a.no_sanitize:
        exe_san, warn_s = build_exe("test_paper_san", True)
        res["build_sanitizer_warnings"] = warn_s
    worlds = {}
    for label, e in (("plain", exe), ("sanitizer", exe_san)):
        if e:
            r = subprocess.run([e], capture_output=True, text=True)
            worlds[label] = {"exit": r.returncode, "out": r.stdout.strip().splitlines()[-3:]}
    res["worlds"] = worlds
    print("worlds:", {k: v["out"][-1] for k, v in worlds.items()}, flush=True)
    res["scenarios"] = scenarios(exe, exe_san)
    if not (a.no_e2e or a.exe):
        res["e2e"] = e2e_both(not a.no_sanitize and not a.quick, a.e2e_tag or ("y2021" if a.quick else "is"))
    rng = np.random.default_rng(a.seed)
    res["markets"] = {}
    for sym in a.markets.split(","):
        res["markets"][sym] = run_market(sym, exe, None if a.quick else exe_san, a, rng)
    cov = {}
    for m in res["markets"].values():
        for k, v in m["coverage"].items():
            cov[k] = cov.get(k, 0) + int(v)
    res["coverage_total"] = cov
    res["coverage_zero"] = sorted(k for k, v in cov.items() if v == 0)
    res["coverage_required"] = a.orders >= 10000 and len(res["markets"]) == len(MARKETS)
    ok = (res["registry_slippage_rows"] and not res["build_plain_warnings"] and not res.get("build_sanitizer_warnings")
          and all(w["exit"] == 0 for w in worlds.values()) and res["scenarios"]["pass"]
          and all(m["pass"] for m in res["markets"].values())
          and res.get("e2e", {"pass": True})["pass"]
          and not (res["coverage_required"] and res["coverage_zero"]))
    res["pass"] = bool(ok)
    res["sec"] = round(time.time() - t0, 1)
    with open(os.path.join(OUT, "result.json"), "w") as f:
        json.dump(res, f, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    tot = {k: sum(m["total"][k] for m in res["markets"].values()) for k in ("lab", "matched", "censored", "mismatches")}
    print(f"test_paper: {'PASS' if ok else 'FAIL'}  orders {sum(m['orders'] for m in res['markets'].values())} lab trades {tot['lab']} "
          f"matched {tot['matched']} censored {tot['censored']} mismatches {tot['mismatches']}"
          f"{'  zero coverage: ' + ','.join(res['coverage_zero']) if res['coverage_zero'] else ''}  ({res['sec']} s)"
          f" -> {os.path.relpath(os.path.join(OUT, 'result.json'), ROBOT)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
