"""T1 clock: src/CR_Clock.mqh (step A) against the lab's own references, in sample (SPEC 7 T1, SPEC 8 step A).

    python3 -I lab/robot/check/test_clock.py

The public signatures of src/CR_Clock.mqh must stay those S0 fixed (S0's own API list and reader, test_s0_dbl.py).
check/test_clock.cpp is built three times with the spec's flags (g++ -std=c++17 -O2 -ffp-contract=off): on src/CR_Clock.mqh,
the same under -fsanitize=address,undefined -D_GLIBCXX_DEBUG, and on the table double check/dbl/CR_Clock_dbl.mqh
(-DCLK_DBL). Every query goes through the plain and the sanitizer builds, which must answer byte for byte the same.
  1. conversions: every hour of 2012-2035 and every minute within 3 h of each US and UK switch: UTC -> server, New York,
     London; back again; the summer-time flags; the server day (goldlab trading_day) and week; the date, weekday, minute
     and year of the time's own clock; the rule offset; ClkStr. Then every wall-clock minute within 3 h of each switch
     (the spring gap and the repeated hour included): server -> UTC against pont.server_to_utc, New York and London ->
     UTC against pandas tz_localize(ambiguous = summer time, nonexistent = +1 h). References: zoneinfo through pandas.
  2. NYSE: every date of 2000-2040 against idxus_lib.us_holidays.
  3. BusinessDays: every date of 2000-2040, n = -10..10, at 00:00 and 13:37, against pandas BDay.
  4. AddTradingDays: every in-sample gold 4h close (gl.bars(m1, "4h").t_close, the frame read with the 2022 filter),
     n = 5, and every 30 min of 2012-2035 for n in -5, -1, 0, 1, 2, 3, 5, 10, against trend.add_trading_days.
  5. server days and weeks of the official in-sample trades of the ten sleeves (read with the 2022 filter) against
     stake.prepare.
  6. known closures of the three families: every 5 min of 2012-2035, every closure edge +-1 s and +-60 s, 200,000
     instants in a random order (the cache), against an independent Python reading of SPEC 2.1 built on
     idxus_lib.us_holidays; the same with typed windows; the gold holiday closures against the in-sample gold bars of
     every NYSE holiday and half day of 2013-2021, each difference listed; every in-sample closure edge against the bars
     of its market (does the bar at c0 - 1 min exist).
  7. typed closures: good and bad strings, their effect on ClkNyse.
  8. RealExitMinute: every 5 min of 2012-2035 (three families, with and without the gap rule) and Fridays with broker
     session ends, against the rule written in src/CR_Clock.mqh; then the lab's exit bar of every in-sample order of the
     gap-rule sleeves (check/out/ref/official, ref_lab.py) and of their trades.
  9. the real clock against the double on the same queries: they must agree wherever both are defined.
It compiles only src/CR_Clock.mqh with S0's files (CR_Types.mqh, the mock, the shim, the double), as SPEC 8 asks of a
wave-1 step: the other src files may be another step's work in progress.
Outputs: lab/robot/check/out/clock/ (summary.json, xau_holiday_scan.csv, lab_exits.csv, closure_edges.json).
Exit 0 when everything holds.
"""
import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
os.environ.setdefault("NUMBA_CACHE_DIR", "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/numba")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from pandas.tseries.offsets import BDay  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROBOT = os.path.dirname(HERE)
LAB = os.path.dirname(ROBOT)
sys.path.insert(0, HERE)
sys.path.insert(0, LAB)
for sub in (("r2", "tracks", "idx_us"), ("r2", "tracks", "stake"), ("live_ai",)):
    sys.path.insert(0, os.path.join(LAB, *sub))
from build import build  # noqa: E402
import idxus_lib as cm  # noqa: E402
import pont  # noqa: E402
import goldlab as gl  # noqa: E402
from tracks.trend import strategy as trend  # noqa: E402
import stake as S  # noqa: E402

CUT = pd.Timestamp("2022-01-01", tz="UTC")
NY, LDN = "America/New_York", "Europe/London"
XAU, IDX, CRY = 0, 1, 2
FAMS = {"XAU": XAU, "IDX": IDX, "CRY": CRY}
OUT = os.path.join(HERE, "out", "clock")
CPP = os.path.join(HERE, "test_clock.cpp")
SRC = os.path.join(ROBOT, "src", "CR_Clock.mqh")
DBL = os.path.join(HERE, "dbl", "CR_Clock_dbl.mqh")
H, M, DAY = 3600, 60, 86400
LONG, SHORT, H1345, GNONE = 1, 2, 3, 0
GOLD_NAME = {LONG: "long", SHORT: "short", H1345: "13:45", GNONE: "none"}


def epoch(*a):
    return int(dt.datetime(*a, tzinfo=dt.timezone.utc).timestamp())


T0, T1 = epoch(2012, 1, 1), epoch(2036, 1, 1)


def secs(x):
    """UTC seconds of a datetime-like array / column"""
    return pd.DatetimeIndex(x).as_unit("s").asi8.astype(np.int64)


def wall(u, tz):
    """wall-clock seconds of tz for UTC seconds u (zoneinfo through pandas)"""
    return pd.to_datetime(np.asarray(u, np.int64), unit="s", utc=True).tz_convert(tz).tz_localize(None).as_unit("s").asi8


def from_wall(w, tz):
    """UTC seconds of wall-clock seconds w of tz: an ambiguous time takes the summer-time instant, a time in the spring
    gap moves forward by the gap (the rule of pont.server_to_utc)"""
    w = np.asarray(w, np.int64)
    idx = pd.to_datetime(w, unit="s").tz_localize(tz, ambiguous=np.ones(len(w), bool), nonexistent=pd.Timedelta(hours=1))
    return idx.tz_convert("UTC").as_unit("s").asi8


def from_wall_strict(w, tz):
    """the same for times that must be neither ambiguous nor in a gap (pandas raises otherwise)"""
    idx = pd.to_datetime(np.asarray(w, np.int64), unit="s").tz_localize(tz, ambiguous="raise", nonexistent="raise")
    return idx.tz_convert("UTC").as_unit("s").asi8


def day_secs(d):
    return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp())


def hhmm(ny_secs):
    return pd.to_datetime(ny_secs, unit="s").strftime("%H:%M") if ny_secs is not None else "-"


# ------------------------------------------------------------------ the three builds
class Exe:
    def __init__(self, path, tag):
        self.path, self.tag = path, tag

    def run(self, *args):
        r = subprocess.run([self.path] + [str(a) for a in args], capture_output=True, text=True,
                           env=dict(os.environ, ASAN_OPTIONS="detect_leaks=1"))
        if r.returncode:
            raise RuntimeError(f"{self.tag} {args[:1]} exit {r.returncode}: {r.stdout[-2000:]} {r.stderr[-2000:]}")
        return r.stdout

    def _io(self, name):
        return os.path.join(OUT, "io", f"{self.tag}_{name}")

    def pairs(self, Q, typed=None):
        fi, fo = self._io("pairs_in.bin"), self._io("pairs_out.bin")
        np.ascontiguousarray(np.asarray(Q, np.int64).reshape(-1, 5)).tofile(fi)
        self.run("pairs", fi, fo, *([typed] if typed else []))
        return np.fromfile(fo, np.int64).reshape(-1, 3)

    def hours(self, U, typed=None):
        fi, fo = self._io("hours_in.bin"), self._io("hours_out.bin")
        np.ascontiguousarray(np.asarray(U, np.int64)).tofile(fi)
        self.run("hours", fi, fo, *([typed] if typed else []))
        return np.fromfile(fo, np.int64).reshape(-1, 16)

    def grid(self, op, a, b, t0, t1, step, typed=None):
        fo = self._io(f"grid_{op}.bin")
        self.run("grid", op, a, b, t0, t1, step, fo, *([typed] if typed else []))
        return np.fromfile(fo, np.int64).reshape(-1, 4)

    def parse(self, lines):
        fi, fo = self._io("parse_in.txt"), self._io("parse_out.txt")
        with open(fi, "w") as f:
            f.write("\n".join(lines) + "\n")
        self.run("parse", fi, fo)
        out = []
        for ln in open(fo).read().split("\n")[:len(lines)]:
            ok, _, err = ln.partition("\t")
            out.append((ok == "1", err))
        return out

    def strs(self, U):
        fi, fo = self._io("str_in.bin"), self._io("str_out.txt")
        np.ascontiguousarray(np.asarray(U, np.int64)).tofile(fi)
        self.run("str", fi, fo)
        return open(fo).read().split("\n")[:len(U)]


class Clocks:
    """the plain build answers; the sanitizer build is asked the same and must answer the same"""

    def __init__(self, plain, san, dbl):
        self.p, self.s, self.d = plain, san, dbl
        self.san_diff = []

    def ask(self, kind, *args, **kw):
        a = getattr(self.p, kind)(*args, **kw)
        b = getattr(self.s, kind)(*args, **kw)
        same = (a == b) if isinstance(a, list) else np.array_equal(a, b)
        if not same:
            self.san_diff.append(kind)
        return a

    def dbl(self, kind, *args, **kw):
        return getattr(self.d, kind)(*args, **kw)


def build_all():
    res = {}
    exes = {}
    for tag, entry, kw in (("plain", SRC, {}), ("san", SRC, {"sanitize": True}), ("dbl", DBL, {"defines": ["CLK_DBL"]})):
        t0 = time.time()
        exe, warn = build(entry, name=f"test_clock_{tag}", main=CPP, **kw)
        res[tag] = {"warnings": len(warn), "first": warn[:3], "sec": round(time.time() - t0, 1)}
        exes[tag] = Exe(exe, tag)
    return exes, res


def rle(t, R):
    t = np.asarray(t, np.int64)
    R = np.asarray(R, np.int64).reshape(len(t), -1)
    if R.shape[1] < 3:
        R = np.column_stack([R, np.zeros((len(t), 3 - R.shape[1]), np.int64)])
    keep = np.ones(len(t), bool)
    keep[1:] = (R[1:] != R[:-1]).any(axis=1)
    return np.column_stack([t[keep], R[keep]])


def same_rle(a, b):
    if a.shape == b.shape and np.array_equal(a, b):
        return {"rows": int(len(a)), "equal": True}
    n = min(len(a), len(b))
    bad = np.flatnonzero((a[:n] != b[:n]).any(axis=1))
    k = int(bad[0]) if len(bad) else n
    return {"rows_clock": int(len(a)), "rows_ref": int(len(b)), "equal": False,
            "first_difference": {"clock": a[k].tolist() if k < len(a) else None, "ref": b[k].tolist() if k < len(b) else None}}


# ------------------------------------------------------------------ 1. conversions
def switches(tz, y0=2012, y1=2035):
    u = np.arange(epoch(y0, 1, 1), epoch(y1 + 1, 1, 1), H, dtype=np.int64)
    off = wall(u, tz) - u
    return u[1:][off[1:] != off[:-1]]


def part_conversions(C):
    us, uk = switches(NY), switches(LDN)
    near = [np.arange(s - 3 * H, s + 3 * H + 1, M, dtype=np.int64) for s in np.r_[us, uk]]
    U = np.unique(np.r_[np.arange(T0, T1, H, dtype=np.int64), np.concatenate(near)])
    R = C.ask("hours", U)
    srv = wall(U, NY) + 7 * H
    nyw, ldw = wall(U, NY), wall(U, LDN)
    sday = gl.trading_day(pd.to_datetime(U, unit="s", utc=True)).as_unit("s").asi8
    dyn = sday // DAY
    ts = pd.to_datetime(U, unit="s")
    want = {
        "server": srv, "new_york": nyw, "london": ldw,
        "server_back": pont.server_to_utc(srv).as_unit("s").asi8, "new_york_back": from_wall(nyw, NY),
        "london_back": from_wall(ldw, LDN),
        "us_summer": (nyw - U == -4 * H).astype(np.int64), "uk_summer": (ldw - U == H).astype(np.int64),
        "server_day": sday, "server_week": ((dyn + 3) // 7 * 7 - 3) * DAY,          # stake.prepare: weeks start on Monday
        "day": U - U % DAY, "dow": ((ts.dayofweek.to_numpy() + 1) % 7).astype(np.int64),
        "minute_of_day": (ts.hour.to_numpy() * 60 + ts.minute.to_numpy()).astype(np.int64),
        "year": ts.year.to_numpy().astype(np.int64), "rule_offset": srv - U}
    res = {"utc_instants": int(len(U)), "us_switches": int(len(us)), "uk_switches": int(len(uk)), "mismatches": {}}
    for k, (name, w) in enumerate(want.items(), start=1):
        res["mismatches"][name] = int((R[:, k] != w).sum())
    # ClkStr on the hours
    hrs = np.arange(T0, T1, 7 * H + 13 * M, dtype=np.int64)
    got = C.ask("strs", hrs)
    exp = list(pd.to_datetime(hrs, unit="s").strftime("%Y.%m.%d %H:%M"))
    res["clkstr_checked"] = len(hrs)
    res["mismatches"]["clkstr"] = int(sum(a != b for a, b in zip(got, exp)))
    # wall-clock minutes within 3 h of each switch, as the input
    srv_s = np.concatenate([np.arange(w - 3 * H, w + 3 * H + 1, M) for w in wall(us, NY) + 7 * H])
    ny_s = np.concatenate([np.arange(w - 3 * H, w + 3 * H + 1, M) for w in wall(us, NY)])
    ld_s = np.concatenate([np.arange(w - 3 * H, w + 3 * H + 1, M) for w in wall(uk, LDN)])
    for name, op, w, ref in (("server_to_utc", 4, srv_s, pont.server_to_utc(srv_s).as_unit("s").asi8),
                             ("ny_to_utc", 5, ny_s, from_wall(ny_s, NY)), ("ldn_to_utc", 6, ld_s, from_wall(ld_s, LDN))):
        Q = np.column_stack([np.full(len(w), op), w, np.zeros((len(w), 3), np.int64)])
        got = C.ask("pairs", Q)[:, 0]
        res["mismatches"][name + "_near_switches"] = int((got != ref).sum())
        res[name + "_wall_minutes"] = int(len(w))
    res["pass"] = all(v == 0 for v in res["mismatches"].values())
    return res, U, R


# ------------------------------------------------------------------ 2-3. NYSE and business days
def ref_nyse_kind(days):
    cal = {}
    out = np.zeros(len(days), np.int64)
    for i, d in enumerate(days):
        if d.year not in cal:
            cal[d.year] = cm.us_holidays(d.year)
        f, h = cal[d.year]
        out[i] = 1 if d in f else (2 if d in h else 0)
    return out


def part_dates(C):
    days = [dt.date(2000, 1, 1) + dt.timedelta(days=k) for k in range((dt.date(2041, 1, 1) - dt.date(2000, 1, 1)).days)]
    D = np.array([day_secs(d) for d in days], np.int64)
    z = np.zeros(len(D), np.int64)
    got = C.ask("pairs", np.column_stack([np.full(len(D), 18), D, z, z, z]))[:, 0]
    res = {"dates": len(D), "nyse_mismatches": int((got != ref_nyse_kind(days)).sum()),
           "nyse_full_days": int((got == 1).sum()), "nyse_half_days": int((got == 2).sum())}
    Q, want = [], []
    for tod in (0, 13 * H + 37 * M):
        base = pd.to_datetime(D + tod, unit="s")
        for n in range(-10, 11):
            if tod and n not in (-3, 0, 3):
                continue
            Q.append(np.column_stack([np.full(len(D), 17), D + tod, np.full(len(D), n), z, z]))
            want.append((base + BDay(n)).as_unit("s").asi8)
    Q, want = np.concatenate(Q), np.concatenate(want)
    got = C.ask("pairs", Q)[:, 0]
    res["business_days_queries"] = int(len(Q))
    res["business_days_mismatches"] = int((got != want).sum())
    res["pass"] = res["nyse_mismatches"] == 0 and res["business_days_mismatches"] == 0
    return res, Q, got


# ------------------------------------------------------------------ 4. AddTradingDays
def read_frame(sym, columns=None):
    m1 = pd.read_parquet(os.path.join(LAB, "data", "fp", f"{sym}_m1.parquet"), columns=columns, filters=[("ts", "<", CUT)])
    assert len(m1) and m1.index.max() < CUT and m1.index.is_monotonic_increasing
    return m1


def part_atd(C, gold):
    res = {}
    b = gl.bars(gold, "4h")
    tc = pd.DatetimeIndex(b["t_close"])
    want = trend.add_trading_days(tc, 5)
    ok = ~pd.isna(want)
    t = secs(tc)
    z = np.zeros(len(t), np.int64)
    got = C.ask("pairs", np.column_stack([np.full(len(t), 16), t, np.full(len(t), 5), z, z]))[:, 0]
    w = pd.DatetimeIndex(want[ok]).as_unit("s").asi8
    res["gold_4h_closes"] = {"checked": int(ok.sum()), "nat_in_lab": int((~ok).sum()), "first": str(tc[0]), "last": str(tc[-1]),
                             "mismatches": int((got[ok] != w).sum())}
    grid = np.arange(T0, T1, 1800, dtype=np.int64)
    gidx = pd.to_datetime(grid, unit="s", utc=True)
    res["grid_30min"] = {}
    for n in (-5, -1, 0, 1, 2, 3, 5, 10):
        wv = trend.add_trading_days(gidx, n)
        nat = int(pd.isna(wv).sum())
        ref = rle(grid, pd.DatetimeIndex(wv).as_unit("s").asi8 - grid)
        r = same_rle(C.ask("grid", "atd", n, 0, T0, T1, 1800), ref)
        r["nat_in_lab"] = nat
        res["grid_30min"][str(n)] = r
    res["grid_points"] = int(len(grid))
    res["pass"] = res["gold_4h_closes"]["mismatches"] == 0 and res["gold_4h_closes"]["nat_in_lab"] == 0 and \
        all(v["equal"] and v["nat_in_lab"] == 0 for v in res["grid_30min"].values())
    return res


# ------------------------------------------------------------------ 5. stake.prepare
def official_trades():
    per = {}
    for name, sym in S.SLEEVES:
        p = os.path.join(S.NET_DIR, f"{name}__{sym}.parquet")
        per[(name, sym)] = pd.read_parquet(p, filters=[("entry_time", "<", CUT)])
    return per


def part_weeks(C):
    d = S.build_frame(official_trades())
    a = S.prepare(d)
    t_in, t_out = secs(d.t_in), secs(d.t_out)
    z = np.zeros(len(t_in), np.int64)
    wk_in = C.ask("pairs", np.column_stack([np.full(len(z), 10), t_in, z, z, z]))[:, 0]
    wk_out = C.ask("pairs", np.column_stack([np.full(len(z), 10), t_out, z, z, z]))[:, 0]
    dy_in = C.ask("pairs", np.column_stack([np.full(len(z), 9), t_in, z, z, z]))[:, 0] // DAY
    dy_out = C.ask("pairs", np.column_stack([np.full(len(z), 9), t_out, z, z, z]))[:, 0] // DAY
    monday = pd.DatetimeIndex(a["week_monday"]).as_unit("s").asi8
    off_in, off_out = dy_in - a["dy_in"], dy_out - a["dy_out"]
    res = {"trades": int(len(d)), "first_entry": str(d.t_in.min()), "last_entry": str(d.t_in.max()),
           "week_in_mismatches": int((wk_in != monday[a["wk_in"]]).sum()),
           "week_out_mismatches": int((wk_out != monday[a["wk_out"]]).sum()),
           "day_offsets": sorted(set(off_in.tolist()) | set(off_out.tolist()))}
    res["pass"] = res["week_in_mismatches"] == 0 and res["week_out_mismatches"] == 0 and len(res["day_offsets"]) == 1
    return res


# ------------------------------------------------------------------ 6. closures: an independent reading of SPEC 2.1
def gold_kinds(y):
    full, half = cm.us_holidays(y)
    gf = cm._easter(y) - dt.timedelta(days=2)
    xmas = cm._observed(dt.date(y, 12, 25))
    j1 = dt.date(y, 1, 1)
    nyo = j1 + dt.timedelta(days=1) if j1.weekday() == 6 else (j1 if j1.weekday() < 5 else None)
    out = {}
    for d in full:
        out[d] = LONG if d in (gf, xmas, nyo) else (GNONE if d in cm.SPECIAL_CLOSURES else SHORT)
    tg = cm._nth(y, 11, 3, 4)
    for d in half:
        out[d] = H1345 if (d == tg + dt.timedelta(days=1) or (d.month == 12 and d.day == 24)) else GNONE
    return out


def parse_typed(s):
    """the windows of a known-good InpExtraClosures string: [(family, ny0, ny1)] and {date: 'NYSE' | 'HALF'}"""
    win, days = [], {}
    for p in s.split(";"):
        p = " ".join(p.split())
        if not p:
            continue
        k = p[:4]
        if k in ("NYSE", "HALF"):
            days[dt.datetime.strptime(p[5:], "%Y.%m.%d").date()] = k
            continue
        a, b = p[4:].split("-")
        t0 = int(dt.datetime.strptime(a.strip(), "%Y.%m.%d %H:%M").replace(tzinfo=dt.timezone.utc).timestamp())
        t1 = int(dt.datetime.strptime(b.strip(), "%Y.%m.%d %H:%M").replace(tzinfo=dt.timezone.utc).timestamp())
        win.append((FAMS[p[:3]], t0, t1))
    return win, days


KINDS = {}


def ref_closures(fam, typed=""):
    """merged closures [st, en) of a family, UTC seconds, New York dates 1999-12-20 .. 2041-01-10 (SPEC 2.1)"""
    if not KINDS:
        for y in range(1999, 2043):
            KINDS.update(gold_kinds(y))
    a, b = [], []
    d, d1 = dt.date(1999, 12, 20), dt.date(2041, 1, 10)
    while d <= d1:
        s = day_secs(d)
        w = (d.weekday() + 1) % 7                     # 0 = Sunday
        if fam == XAU:
            if 1 <= w <= 4:
                a.append(s + 17 * H); b.append(s + 18 * H)
            if w == 5:
                a.append(s + 17 * H); b.append(s + 2 * DAY + 18 * H)
            k = KINDS.get(d, GNONE)
            if k == LONG:
                a.append(s - DAY + 17 * H); b.append(s + 18 * H)
            elif k == SHORT:
                a.append(s + 13 * H); b.append(s + 18 * H)
            elif k == H1345:
                a.append(s + 13 * H + 45 * M); b.append(s + 18 * H)
        elif fam == IDX:
            if 1 <= w <= 4:
                a.append(s + 16 * H + 15 * M); b.append(s + 18 * H)
            if w == 5:
                a.append(s + 16 * H + 15 * M); b.append(s + 2 * DAY + 18 * H)
        elif fam == CRY and w == 5:
            a.append(s + 16 * H + 55 * M); b.append(s + 2 * DAY + 17 * H)
        d += dt.timedelta(days=1)
    ua, ub = from_wall_strict(a, NY), from_wall_strict(b, NY)
    win, _ = parse_typed(typed)
    tw = [(t0, t1) for f, t0, t1 in win if f == fam]
    if tw:
        ua = np.r_[ua, from_wall([x[0] for x in tw], NY)]
        ub = np.r_[ub, from_wall([x[1] for x in tw], NY)]
    o = np.argsort(ua, kind="stable")
    st, en = [], []
    for x, y in zip(ua[o], ub[o]):
        if st and x <= en[-1]:
            en[-1] = max(en[-1], y)
        else:
            st.append(x)
            en.append(y)
    return np.array(st, np.int64), np.array(en, np.int64)


def ref_in(st, en, t):
    t = np.asarray(t, np.int64)
    i = np.searchsorted(st, t, side="right") - 1
    ic = np.maximum(i, 0)
    inside = (i >= 0) & (t < en[ic])
    return np.column_stack([inside.astype(np.int64), np.where(inside, st[ic], 0), np.where(inside, en[ic], 0)])


def ref_next(st, en, t):
    t = np.asarray(t, np.int64)
    i = np.searchsorted(st, t, side="right") - 1
    ic = np.maximum(i, 0)
    inside = (i >= 0) & (t < en[ic])
    j = np.where(inside, i, i + 1)
    ok = j < len(st)
    jc = np.minimum(j, len(st) - 1)
    return np.column_stack([ok.astype(np.int64), np.where(ok, st[jc], 0), np.where(ok, en[jc], 0)])


def ref_rex(st, en, x, fam, gap, fe):
    """the rule of ClkRealExitMinute (SPEC 2.1 with the broker's session end), on the reference closures"""
    x = np.asarray(x, np.int64)
    fe = np.broadcast_to(np.asarray(fe, np.int64), x.shape)
    nx = ref_next(st, en, x)
    c0, c1 = nx[:, 1], nx[:, 2]
    e0 = np.where((fe > 0) & (fe < c0) & (c0 - fe <= 12 * H), fe, c0)
    r = x.copy()
    if gap:
        r = np.where((x >= e0) & (x < c1 - 30 * M), e0 - 60, r)
    if fam == CRY:
        r = np.where((fe > 0) & (r >= e0 - 60) & (r < c1), e0 - 60, r)
    return np.where(nx[:, 0] == 1, r, x)


TYPED = ("XAU 2026.12.24 13:45-2026.12.26 18:00;IDX 2026.07.03 13:15-2026.07.05 18:00;CRY 2026.12.31 16:55-2027.01.02 17:00;"
         "XAU 2026.03.04 09:00-2026.03.04 11:00;XAU 2026.03.10 16:00-2026.03.11 19:00;CRY 2026.06.10 10:00-2026.06.10 12:30;"
         "NYSE 2026.01.09;HALF 2026.12.31")


def part_closures(C, REF):
    res = {"grid_5min": {}, "edges": {}, "random": {}, "typed": {}}
    grid = np.arange(T0, T1, 300, dtype=np.int64)
    rng = np.random.default_rng(20261112)
    for name, f in FAMS.items():
        st, en = REF[f]
        r1 = same_rle(C.ask("grid", "inc", f, 0, T0, T1, 300), rle(grid, ref_in(st, en, grid)))
        r2 = same_rle(C.ask("grid", "nxt", f, 0, T0, T1, 300), rle(grid, ref_next(st, en, grid)))
        res["grid_5min"][name] = {"in_closure": r1, "next_closure": r2}
        sel = (st >= T0) & (en < T1)
        e = np.unique(np.concatenate([np.r_[st[sel], en[sel]] + k for k in (-60, -1, 0, 1, 60)]))
        rt = np.sort(rng.integers(T0, T1, 200000))
        rng.shuffle(rt)
        for label, t in (("edges", e), ("random", rt)):
            z = np.zeros(len(t), np.int64)
            gi = C.ask("pairs", np.column_stack([np.full(len(t), 19), t, np.full(len(t), f), z, z]))
            gn = C.ask("pairs", np.column_stack([np.full(len(t), 20), t, np.full(len(t), f), z, z]))
            res[label][name] = {"queries": int(len(t)), "in_mismatches": int((gi != ref_in(st, en, t)).any(axis=1).sum()),
                                "next_mismatches": int((gn != ref_next(st, en, t)).any(axis=1).sum())}
        res["grid_5min"][name]["closures_2012_2035"] = int(sel.sum())
    # typed windows, 2025-06 .. 2027-06, every minute
    a0, a1 = epoch(2025, 6, 1), epoch(2027, 6, 1)
    g1 = np.arange(a0, a1, 60, dtype=np.int64)
    for name, f in FAMS.items():
        st, en = ref_closures(f, TYPED)
        r1 = same_rle(C.ask("grid", "inc", f, 0, a0, a1, 60, typed=TYPED), rle(g1, ref_in(st, en, g1)))
        r2 = same_rle(C.ask("grid", "nxt", f, 0, a0, a1, 60, typed=TYPED), rle(g1, ref_next(st, en, g1)))
        sel = (st >= a0) & (en < a1)
        e = np.unique(np.concatenate([np.r_[st[sel], en[sel]] + k for k in (-60, -1, 0, 1, 60)]))
        z = np.zeros(len(e), np.int64)
        gi = C.ask("pairs", np.column_stack([np.full(len(e), 19), e, np.full(len(e), f), z, z]), typed=TYPED)
        b0, b1 = REF[f]
        bsel = (b0 >= a0) & (b1 < a1)
        changed = set(zip(st[sel].tolist(), en[sel].tolist())) - set(zip(b0[bsel].tolist(), b1[bsel].tolist()))
        res["typed"][name] = {"in_closure": r1, "next_closure": r2, "edge_queries": int(len(e)),
                              "edge_mismatches": int((gi != ref_in(st, en, e)).any(axis=1).sum()),
                              "closures_changed_by_the_typed_windows": int(len(changed))}
    # typed NYSE and HALF dates
    _, days = parse_typed(TYPED)
    probe = [dt.date(2026, 1, 9), dt.date(2026, 12, 31), dt.date(2026, 1, 8), dt.date(2026, 12, 25), dt.date(2026, 12, 24)]
    want = [1 if days.get(d) == "NYSE" else 2 if days.get(d) == "HALF" else int(ref_nyse_kind([d])[0]) for d in probe]
    P = np.array([[18, day_secs(d), 0, 0, 0] for d in probe], np.int64)
    got = C.ask("pairs", P, typed=TYPED)[:, 0].tolist()
    res["typed"]["nyse"] = {"dates": [str(d) for d in probe], "got": got, "want": want}
    ok = all(v["in_closure"]["equal"] and v["next_closure"]["equal"] for v in res["grid_5min"].values() if isinstance(v, dict))
    ok &= all(v["in_mismatches"] == 0 and v["next_mismatches"] == 0 for k in ("edges", "random") for v in res[k].values())
    ok &= all(res["typed"][n]["in_closure"]["equal"] and res["typed"][n]["next_closure"]["equal"] and res["typed"][n]["edge_mismatches"] == 0
              for n in FAMS)
    ok &= got == want
    res["pass"] = bool(ok)
    return res


def part_holiday_scan(REF, gold_t):
    """every NYSE full or half day of 2013-2021: the gold bars inside its built-in closure, each difference listed"""
    st, en = REF[XAU]
    rows, diffs = [], []
    gt = np.asarray(gold_t, np.int64)
    gny = wall(gt, NY)
    for y in range(2013, 2022):
        full, half = cm.us_holidays(y)
        kinds = gold_kinds(y)
        for d in sorted(full | half):
            k = kinds.get(d, GNONE)
            s = day_secs(d)
            win = {LONG: (s - DAY + 17 * H, s + 18 * H), SHORT: (s + 13 * H, s + 18 * H), H1345: (s + 13 * H + 45 * M, s + 18 * H)}.get(k)
            day_bars = gny[(gny >= s) & (gny < s + 17 * H)]
            last = int(day_bars[-1]) if len(day_bars) else None
            row = {"date": str(d), "weekday": d.strftime("%a"), "nyse": "full" if d in full else "half", "gold_closure": GOLD_NAME[k],
                   "last_bar_before_17_ny": hhmm(last), "bars_on_date": int(len(day_bars))}
            if win is None:
                row.update(window_ny="-", merged_closure_ny="-", bars_inside=0, bar_times_ny="", bars_on_holiday_date_inside=0,
                           cls="normal gold day")
            else:
                u0, u1 = from_wall_strict(list(win), NY)
                inside = gny[(gt >= u0) & (gt < u1)]
                i = np.searchsorted(st, u0, side="right") - 1
                m0, m1 = wall([st[i], en[i]], NY)
                row["window_ny"] = f"{pd.to_datetime(win[0], unit='s'):%m-%d %H:%M} - {pd.to_datetime(win[1], unit='s'):%m-%d %H:%M}"
                row["merged_closure_ny"] = f"{pd.to_datetime(m0, unit='s'):%a %m-%d %H:%M} - {pd.to_datetime(m1, unit='s'):%a %m-%d %H:%M}"
                row["bars_inside"] = int(len(inside))
                row["bar_times_ny"] = ";".join(pd.to_datetime(inside[:30], unit="s").strftime("%m-%d %H:%M"))
                on_date = inside[inside >= s]
                row["bars_on_holiday_date_inside"] = int(len(on_date))
                if k == LONG:
                    row["cls"] = "no bar on the date" + (f"; {len(inside) - len(on_date)} bar(s) the evening before" if len(inside) > len(on_date) else "")
                    if len(on_date):
                        row["cls"] = f"{len(on_date)} bar(s) on the date"
                elif len(inside) == 0:
                    row["cls"] = "no bar inside"
                elif len(inside) == 1 and inside[0] == win[0]:
                    row["cls"] = f"one bar starting at {hhmm(win[0])}"
                else:
                    row["cls"] = f"{len(inside)} bars inside, to {hhmm(int(inside[-1]))}"
                if len(inside):
                    diffs.append(f"{d} {GOLD_NAME[k]}: {row['bar_times_ny']}")
            rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "xau_holiday_scan.csv"), index=False)
    lg, sh, hh, nn = (df[df.gold_closure == x] for x in ("long", "short", "13:45", "none"))
    mins = lambda s: [int(v[:2]) * 60 + int(v[3:]) for v in s if v != "-"]  # noqa: E731
    sh_wo = sh[sh.date != "2019-07-04"]
    res = {"days": int(len(df)), "by_closure": df.gold_closure.value_counts().to_dict(),
           "long_bars_on_the_date": int(lg.bars_on_holiday_date_inside.sum()),
           "long_days_with_evening_bars": lg[lg.bars_inside > 0][["date", "bar_times_ny"]].values.tolist(),
           "short_last_bar_range_ny": [hhmm(min(mins(sh_wo.last_bar_before_17_ny)) * 60), hhmm(max(mins(sh_wo.last_bar_before_17_ny)) * 60)],
           "short_2019_07_04_last_bar": sh[sh.date == "2019-07-04"].last_bar_before_17_ny.tolist(),
           "short_classes": sh.cls.value_counts().to_dict(),
           "h1345_last_bar_range_ny": [hhmm(min(mins(hh.last_bar_before_17_ny)) * 60), hhmm(max(mins(hh.last_bar_before_17_ny)) * 60)],
           "h1345_classes": hh.cls.value_counts().to_dict(),
           "normal_days": nn[["date", "nyse", "last_bar_before_17_ny"]].values.tolist(),
           "differences": diffs}
    expect = sum(len(f | h) for f, h in (cm.us_holidays(y) for y in range(2013, 2022)))
    sh_ok = all(m <= 14 * 60 + 16 for m in mins(sh_wo.last_bar_before_17_ny))
    hh_ok = all(13 * 60 + 29 <= m <= 14 * 60 + 5 for m in mins(hh.last_bar_before_17_ny))
    nn_ok = all(m >= 16 * 60 + 58 for m in mins(nn.last_bar_before_17_ny)) and len(mins(nn.last_bar_before_17_ny)) == len(nn)
    res["checks"] = {"every_holiday_listed": len(df) == expect, "no_gold_bar_on_a_long_closure_date": res["long_bars_on_the_date"] == 0,
                     "short_days_end_by_14_16_but_2019_07_04": sh_ok, "h1345_days_end_13_29_to_14_05": hh_ok,
                     "july3_and_2018_12_05_normal": nn_ok}
    res["pass"] = all(res["checks"].values())
    return res


def part_edges(REF, frames):
    """does a kept bar start at c0 - 1 min before each in-sample known closure (the minute RealExitMinute closes in)?"""
    out = {}
    for name, f, t in frames:
        st, en = REF[f]
        t = np.asarray(t, np.int64)
        sel = (st > t[0]) & (en < t[-1])
        c0, c1 = st[sel], en[sel]
        j = np.searchsorted(t, c0, side="left") - 1             # last bar starting before c0
        lead = (c0 - t[np.maximum(j, 0)]) // 60
        k = np.searchsorted(t, c0, side="left")
        inside = np.searchsorted(t, c1, side="left") - k        # bars starting inside [c0, c1)
        buckets = {"1 (the c0 - 1 bar exists)": int((lead == 1).sum()), "2-5": int(((lead >= 2) & (lead <= 5)).sum()),
                   "6-30": int(((lead >= 6) & (lead <= 30)).sum()), "31-120": int(((lead >= 31) & (lead <= 120)).sum()),
                   "over 120": int((lead > 120).sum())}
        out[name] = {"closures": int(sel.sum()), "minutes_from_last_bar_to_c0": buckets,
                     "closures_with_bars_inside": int((inside > 0).sum()), "bars_inside": int(inside.sum())}
    with open(os.path.join(OUT, "closure_edges.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    return out


# ------------------------------------------------------------------ 7. typed closures: the parser
GOOD = ["", "NYSE 2026.01.09", "HALF 2026.12.24; NYSE 2026.01.09", "XAU 2026.12.24 13:45-2026.12.26 18:00",
        "CRY 2026.12.31 16:55-2027.01.02 17:00;IDX 2026.07.03 13:15-2026.07.05 18:00", "  NYSE   2026.01.09 ;; HALF\t2026.11.27 ;",
        "XAU 2026.12.24 13:45 - 2026.12.26 18:00", "XAU 2026.03.04 09:00-2026.03.11 09:00", "NYSE 2000.01.03", "HALF 2100.12.24",
        "NYSE 2030.06.03;XAU 2030.06.05 09:00-2030.06.05 11:00", TYPED, ";".join(["NYSE 2026.01.09"] * 64)]
BAD = ["NYSE 2026-01-09", "XAU 2026.12.24 13:45", "FOO 2026.12.24", "XAU 2026.12.26 18:00-2026.12.24 13:45", "HALF 2026.02.30",
       "NYSE 2026.13.01", "NYSE 2026.01.10", "XAU 2026.03.04 09:00-2026.03.11 09:01", "nyse 2026.01.09",
       "XAU 2026.12.24 24:00-2026.12.26 18:00", "XAU 2026.12.24 13:45-2026.12.24 13:45", "NYSE 1999.12.31", "NYSE 2026.01.09 extra",
       "XAUUSD 2026.12.24 13:45-2026.12.26 18:00", "NYSE 2026.1.9", "IDX 2026.07.03 13:15-2026.07.05", "XAU 2026.12.24 13:4x-2026.12.26 18:00",
       "NYSE 2026.01.09;FOO", "HALF 2101.01.03", "CRY 2026.12.31 16:55-2027.01.07 17:00", ";".join(["NYSE 2026.01.09"] * 65)]


def part_parser(C):
    got = C.ask("parse", GOOD + BAD)
    dbl = C.dbl("parse", GOOD + BAD)
    exp = [True] * len(GOOD) + [False] * len(BAD)
    wrong = [(s[:60], g[1]) for s, g, e in zip(GOOD + BAD, got, exp) if g[0] != e]
    differ = [(s[:60], "clock " + ("accepts" if g[0] else "refuses"), "double " + ("accepts" if d[0] else "refuses"))
              for s, g, d in zip(GOOD + BAD, got, dbl) if g[0] != d[0]]
    msgs = {s[:60]: g[1] for s, g in zip(BAD, got[len(GOOD):])}
    return {"good": len(GOOD), "bad": len(BAD), "wrong": wrong, "refusal_messages": msgs,
            "differences_with_the_double": differ, "pass": not wrong}


# ------------------------------------------------------------------ 8. RealExitMinute
def part_rex(C, REF):
    res = {"grid_5min": {}, "fridays": {}}
    grid = np.arange(T0, T1, 300, dtype=np.int64)
    for name, f in FAMS.items():
        st, en = REF[f]
        for gap in (0, 1):
            r = ref_rex(st, en, grid, f, gap, 0)
            ref = rle(grid, np.column_stack([(r != grid).astype(np.int64), np.where(r != grid, r, 0)]))
            got = C.ask("grid", "rex", f, gap, T0, T1, 300)
            res["grid_5min"][f"{name}_gap{gap}"] = same_rle(got, ref)
            res["grid_5min"][f"{name}_gap{gap}"]["moved_points"] = int((r != grid).sum())
    # Fridays 2016-2027 with broker session ends: x every 30 min, Friday 12:00 server to Monday 06:00 server
    fridays = pd.date_range("2016-01-01", "2027-12-31", freq="W-FRI")
    srv_fri = np.array([day_secs(d.date()) for d in fridays], np.int64)          # 00:00 of the Friday, server clock
    xs_srv = (srv_fri[:, None] + 12 * H + np.arange(0, 66 * H + 1, 1800)[None, :]).ravel()
    xs = pont.server_to_utc(xs_srv).as_unit("s").asi8
    fri_of = np.repeat(srv_fri, xs.size // len(srv_fri))
    s2u = lambda srv: pont.server_to_utc(srv).as_unit("s").asi8  # noqa: E731
    ends = {"XAU": {"none": 0, "16:55 NY": s2u(fri_of + 23 * H + 55 * M), "16:00 NY": s2u(fri_of + 23 * H),
                    "17:00 NY (= c0)": s2u(fri_of + 24 * H), "17:05 NY (later)": s2u(fri_of + 24 * H + 5 * M),
                    "04:00 NY (13 h before 17:00)": s2u(fri_of + 11 * H)},
            "IDX": {"none": 0, "16:00 NY": s2u(fri_of + 23 * H), "16:15 NY (= c0)": s2u(fri_of + 23 * H + 15 * M)},
            "CRY": {"none": 0, "23:55 server (= c0)": s2u(fri_of + 23 * H + 55 * M), "23:00 server": s2u(fri_of + 23 * H),
                    "23:58 server (later)": s2u(fri_of + 23 * H + 58 * M), "a week early (stale)": s2u(fri_of - 7 * DAY + 23 * H)}}
    for name, f in FAMS.items():
        st, en = REF[f]
        for label, fe in ends[name].items():
            fe = np.broadcast_to(np.asarray(fe, np.int64), xs.shape)
            for gap in ((0, 1) if f == CRY else (1,)):
                Q = np.column_stack([np.full(len(xs), 21), xs, np.full(len(xs), f), np.full(len(xs), gap), fe])
                got = C.ask("pairs", Q)[:, 0]
                ref = ref_rex(st, en, xs, f, gap, fe)
                res["fridays"][f"{name} gap{gap} end {label}"] = {"queries": int(len(xs)), "mismatches": int((got != ref).sum()),
                                                                   "moved": int((ref != xs).sum())}
    res["pass"] = all(v["equal"] for v in res["grid_5min"].values()) and all(v["mismatches"] == 0 for v in res["fridays"].values())
    return res


def lab_orders():
    ref = os.path.join(HERE, "out", "ref", "official")
    need = ["D4H", "BKB", "BKE", "F1B", "F1E", "NQB", "N30", "OC4"]
    if not all(os.path.exists(os.path.join(ref, c, "orders.parquet")) for c in need):
        subprocess.run([sys.executable, "-I", os.path.join(HERE, "ref_lab.py"), "--frame", "official", "--no-changes"], check=True,
                       capture_output=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    return ref


def x_of(code, o):
    """the lab's scheduled time exit x of every order (UTC seconds)"""
    if code == "D4H":                               # trend/strategy.py:275
        return secs(trend.add_trading_days(pd.DatetimeIndex(o.dec_time), 5) - pd.Timedelta(minutes=5))
    if code in ("BKB", "BKE"):                      # crypto/strategy.py: sched_exit = D + 24 h (Friday 23:54 server cap)
        return secs(o.sched_exit)
    if code in ("F1B", "F1E"):                      # ml/strategy.py:179-184
        tdec = pd.DatetimeIndex(pd.to_datetime(o.cid.to_numpy(), utc=True))
        cap = (tdec.tz_convert(NY).normalize() + pd.Timedelta(hours=15, minutes=55)).tz_convert("UTC")
        xt = tdec + pd.Timedelta(hours=13)
        return secs(xt.where(xt <= cap, cap))
    if code == "NQB":                               # leadlag/strategy.py:229
        return secs(pd.DatetimeIndex(o.entry_t) + pd.Timedelta(minutes=60))
    ny = pd.DatetimeIndex(o.entry_t).tz_convert(NY)   # N30, OC4: 15:55 New York of the session date
    return secs((ny.normalize() + pd.Timedelta(hours=15, minutes=55)).tz_convert("UTC"))


P4_ATTACK = {"BKB": {"before_c0_minus_1": 8, "hole": 5}, "BKE": {"before_c0_minus_1": 5}}   # design_review.json, finding P4


def part_lab_exits(C, last_bar):
    ref = lab_orders()
    fam = {"D4H": XAU, "BKB": CRY, "BKE": CRY, "F1B": CRY, "F1E": CRY, "NQB": CRY, "N30": IDX, "OC4": IDX}
    sym = {"D4H": "XAU", "BKB": "BTC", "BKE": "ETH", "F1B": "BTC", "F1E": "ETH", "NQB": "BTC", "N30": "IDX", "OC4": "IDX"}
    rows, res = [], {}
    for code, f in fam.items():
        o = pd.read_parquet(os.path.join(ref, code, "orders.parquet"))
        tr = pd.read_parquet(os.path.join(ref, code, "trades.parquet"))
        x, ext, ent = x_of(code, o), secs(o.exit_t), secs(o.entry_t)
        z = np.zeros(len(x), np.int64)
        real = C.ask("pairs", np.column_stack([np.full(len(x), 21), x, np.full(len(x), f), np.ones(len(x), np.int64), z]))[:, 0]
        inc = C.ask("pairs", np.column_stack([np.full(len(x), 19), x, np.full(len(x), f), z, z]))
        moved = (inc[:, 0] == 1) & (x < inc[:, 2] - 30 * M)
        before = ("open: lab exit before x (the rule's own exit at a check, or a hole)" if code == "N30" else
                  "open: lab exit before x (a hole in the data, SPEC 9.2)")
        cls = np.where(moved, np.where(ext == real, "closure: lab exit bar = c0 - 1 min",
                                       np.where(ext < real, "closure: lab exit bar before c0 - 1 min (that bar is missing)",
                                                "closure: lab exit bar inside the known closure")),
                       np.where(inc[:, 0] == 1, "closure end: within 30 min of the reopening, real = x",
                                np.where(ext >= x, "open: lab exit at or after x, real = x", before)))
        cls = np.where(x > last_bar[sym[code]], "frame end: x after the last in-sample bar (excluded, SPEC 7)", cls)
        if code == "D4H":
            key_o, key_t = secs(o.dec_time), secs(tr.dec_time)
        else:
            key_o, key_t = ent, secs(tr.entry_time)
        pos = {k: i for i, k in enumerate(key_o)}
        ti = np.array([pos.get(k, -1) for k in key_t])
        is_time = (tr.reason == "time").to_numpy()
        tcls = pd.Series(cls[ti[(ti >= 0) & is_time]]).value_counts().to_dict()
        res[code] = {"orders": int(len(o)), "classes": pd.Series(cls).value_counts().to_dict(), "trades": int(len(tr)),
                     "trades_unmatched": int((ti < 0).sum()), "time_exit_trades": int(is_time.sum()), "time_exit_trade_classes": tcls}
        time_rows = set(ti[(ti >= 0) & is_time].tolist())
        for i in np.flatnonzero(moved | (ext < x)):
            rows.append({"code": code, "x_utc": str(pd.to_datetime(x[i], unit="s")), "x_server": str(pd.to_datetime(x[i], unit="s", utc=True)
                         .tz_convert(NY).tz_localize(None) + pd.Timedelta(hours=7)), "lab_exit_bar_utc": str(pd.to_datetime(ext[i], unit="s")),
                         "real_exit_minute_utc": str(pd.to_datetime(real[i], unit="s")), "class": cls[i],
                         "is_time_exit_trade": bool(i in time_rows)})
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "lab_exits.csv"), index=False)
    ok = all(sum(v["classes"].values()) == v["orders"] and v["trades_unmatched"] == 0 for v in res.values())
    tc = {c: res[c]["time_exit_trade_classes"] for c in ("BKB", "BKE")}
    p4 = {"BKB": {"before_c0_minus_1": tc["BKB"].get("closure: lab exit bar before c0 - 1 min (that bar is missing)", 0),
                  "hole": tc["BKB"].get("open: lab exit before x (a hole in the data, SPEC 9.2)", 0)},
          "BKE": {"before_c0_minus_1": tc["BKE"].get("closure: lab exit bar before c0 - 1 min (that bar is missing)", 0)}}
    p4_ok = p4 == P4_ATTACK
    return {"sleeves": res, "rows_listed": len(rows), "p4_brk72_time_exits": p4, "p4_attack_says": P4_ATTACK,
            "p4_equal": p4_ok, "pass": bool(ok and p4_ok)}


# ------------------------------------------------------------------ 9. the double
def part_double(C, U, Rh, Qd, got_d):
    res = {}
    Rd = C.dbl("hours", U)
    res["hours"] = {"instants": int(len(U)), "rows_differing": int((Rd != Rh).any(axis=1).sum())}
    keep = Qd[:, 2] >= 0                             # the double has no negative business days
    gd = C.dbl("pairs", Qd[keep])[:, 0]
    res["business_days"] = {"queries": int(keep.sum()), "differing": int((gd != got_d[keep]).sum())}
    days = [dt.date(2000, 1, 1) + dt.timedelta(days=k) for k in range((dt.date(2041, 1, 1) - dt.date(2000, 1, 1)).days)]
    D = np.array([day_secs(d) for d in days], np.int64)
    z = np.zeros(len(D), np.int64)
    Qn = np.column_stack([np.full(len(D), 18), D, z, z, z])
    res["nyse"] = {"dates": int(len(D)), "differing": int((C.dbl("pairs", Qn) != C.p.pairs(Qn)).any(axis=1).sum())}
    rng = np.random.default_rng(7)
    t = rng.integers(epoch(2000, 1, 10), epoch(2040, 12, 20), 300000)
    for name, f in FAMS.items():
        z = np.zeros(len(t), np.int64)
        Qi = np.column_stack([np.full(len(t), 19), t, np.full(len(t), f), z, z])
        Qr = np.column_stack([np.full(len(t), 21), t, np.full(len(t), f), np.ones(len(t), np.int64), z])
        res[f"closures_{name}"] = {"queries": int(len(t)), "differing": int((C.dbl("pairs", Qi) != C.p.pairs(Qi)).any(axis=1).sum()),
                                   "real_exit_differing": int((C.dbl("pairs", Qr) != C.p.pairs(Qr)).any(axis=1).sum())}
    grid = np.arange(epoch(2000, 1, 10), epoch(2040, 12, 20), 1800, dtype=np.int64)
    zz = np.zeros(len(grid), np.int64)
    for n in (0, 1, 5):
        Q = np.column_stack([np.full(len(grid), 16), grid, np.full(len(grid), n), zz, zz])
        res[f"add_trading_days_{n}"] = {"queries": int(len(grid)), "differing": int((C.dbl("pairs", Q) != C.p.pairs(Q)).any(axis=1).sum())}
    res["pass"] = all(v.get("rows_differing", 0) == 0 and v.get("differing", 0) == 0 and v.get("real_exit_differing", 0) == 0
                      for v in res.values() if isinstance(v, dict))
    return res


# ------------------------------------------------------------------ 0. the API S0 fixed
def part_api():
    import test_s0_dbl as t0                       # S0's own list and reader (read only: nothing is regenerated)
    a_src, a_dbl = t0.api_of(SRC), t0.api_of(DBL)
    diff = [(a_src.get(n), a_dbl.get(n)) for n in t0.API if a_src.get(n) != a_dbl.get(n)]
    extra = sorted(n for n in a_src if n not in t0.API and n not in ("ClkNextClosure",) and not n.startswith("Clk"))
    return {"names": len(t0.API), "differences": diff, "added_public": ["ClkNextClosure"], "unexpected": extra, "pass": not diff}


def main(argv=None):
    argparse.ArgumentParser(description="T1 clock").parse_args(argv)
    t_start = time.time()
    os.makedirs(os.path.join(OUT, "io"), exist_ok=True)
    out = {}
    exes, out["builds"] = build_all()
    C = Clocks(exes["plain"], exes["san"], exes["dbl"])
    out["0_api"] = part_api()
    out["self_checks"] = {k: json.loads(exes[k].run().strip().splitlines()[-1]) for k in ("plain", "san")}
    out["bench_ns"] = json.loads(exes["plain"].run("bench").strip().splitlines()[-1])
    timer = {}

    def step(name, fn, *args):
        t0 = time.time()
        r = fn(*args)
        timer[name] = round(time.time() - t0, 1)
        return r

    out["1_conversions"], U, Rh = step("1", part_conversions, C)
    out["2_3_dates"], Qd, got_d = step("2_3", part_dates, C)
    gold = read_frame("xauusd")
    out["4_add_trading_days"] = step("4", part_atd, C, gold)
    out["5_weeks"] = step("5", part_weeks, C)
    REF = {f: ref_closures(f) for f in (XAU, IDX, CRY)}
    out["6_closures"] = step("6", part_closures, C, REF)
    out["6_xau_holiday_scan"] = step("6s", part_holiday_scan, REF, secs(gold.index))
    frames = [("XAU", XAU, secs(gold.index))]
    del gold
    for name, sym, f in (("IDX", "us100", IDX), ("BTC", "btcusd", CRY), ("ETH", "ethusd", CRY)):
        frames.append((name, f, secs(read_frame(sym, ["bo"]).index)))
    out["6_closure_edges_in_sample"] = step("6e", part_edges, REF, frames)
    last_bar = {name: int(t[-1]) for name, f, t in frames}
    del frames
    out["7_parser"] = step("7", part_parser, C)
    out["8_real_exit"] = step("8", part_rex, C, REF)
    out["8_lab_exits"] = step("8l", part_lab_exits, C, last_bar)
    out["9_double"] = step("9", part_double, C, U, Rh, Qd, got_d)
    out["sanitizer_same_answers"] = {"differing_query_kinds": sorted(set(C.san_diff)), "pass": not C.san_diff}
    out["seconds"] = timer
    out["seconds_total"] = round(time.time() - t_start, 1)
    keys = [k for k in out if isinstance(out[k], dict) and "pass" in out[k]]
    out["pass"] = (all(out[k]["pass"] for k in keys) and all(v["warnings"] == 0 for v in out["builds"].values())
                   and all(v["pass"] for v in out["self_checks"].values()))
    out["parts_failed"] = [k for k in keys if not out[k]["pass"]]
    shutil.rmtree(os.path.join(OUT, "io"), ignore_errors=True)
    with open(os.path.join(OUT, "summary.json"), "w") as fh:
        json.dump(out, fh, indent=1, default=str)
    print(json.dumps(out, indent=1, default=str))
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
