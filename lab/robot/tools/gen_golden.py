"""Write src/CR_Golden.mqh: the self-test vectors of SPEC 7 T10, each one computed by the lab's own code.

    python3 -I lab/robot/tools/gen_golden.py            # writes src/CR_Golden.mqh
    python3 -I lab/robot/tools/gen_golden.py --check    # exit 1 if the file on disk is not what this would write

What the EA checks at OnInit (GoldenCheck, called by CR_Main; a mismatch blocks trading, SPEC 7 T10):
  clock    60 UTC instants, most of them one second around a summer-time switch of 2012-2035: server, New York and
           London wall clocks (zoneinfo), the server clock back to UTC (pont.server_to_utc), both summer-time flags
  nyse     40 New York dates: full closure, 13:00 half day or open, by idxus_lib.us_holidays (the rules only: the
           EA's ClkHolKind, so a typed InpExtraClosures entry cannot fail the self-test)
  atd      20 AddTradingDays(t, n) against trend.add_trading_days (tracks/trend/strategy.py:107-111)
  bday     20 BusinessDays(date, n) against pandas BDay
  orx      10 ORX time exits (16:00 New York on BusinessDays(London date, 2)) against pandas and zoneinfo
  f1       30 F1 scores: 24 candidates of the lab's ml/strategy.py candidates() on the in-sample BTC and ETH frames
           (12 each, spread over the score range, the 6 nearest the threshold included) and 6 made-up vectors for the
           clip and dummy edges; the expected score is the model's sum taken term by term in the EA's order (Python
           floats: IEEE doubles, the EA's operations), within 1e-12 of the lab's score_model (numpy), checked here
  riskbp   10 K1 risks 1e4 x stop_dist / P of the lab's brk72 ETH orders (make_orders through recalc.sleeves(), the
           in-sample frame), P = the mid close of the last bar starting before the decision (s1_run.py:85-108)
  risk     the five plans F3S, F2S, F1S, D2 (the default) and S7 (SPEC 1): SizParseTable, then the rate at 15 keys, against
           growth._pct on growth.SCHEDULES["F3"], ["F2"], ["F1"], ["D2"], ["S7"]
  wilder   a 48-value series (NaN first, one more NaN inside) through CrWilder(14), against pandas
           ewm(alpha=1/14, adjust=False).mean()
  sma      the same series through CrRollSum(14, 9).Mean(), against pandas rolling(14, min_periods=9).mean()
Times are compared exactly; doubles within 1e-12 relative (SPEC 7: rolling, Wilder and score values), the rates of the
risk tables exactly. In-sample data only: every frame is read with the row filter ts < 2022-01-01 inside the read call,
the lab calls run in fresh processes (P8). NUMBA_CACHE_DIR under /tmp, no bytecode.
"""
import argparse
import datetime as dt
import json
import math
import os
import subprocess
import sys
from zoneinfo import ZoneInfo

sys.dont_write_bytecode = True
os.environ.setdefault("NUMBA_CACHE_DIR", "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/numba")
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from pandas.tseries.offsets import BDay  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROBOT = os.path.dirname(HERE)
LAB = os.path.dirname(ROBOT)
OUT = os.path.join(ROBOT, "src", "CR_Golden.mqh")
CUT = "2022-01-01"
NY, LDN, UTC = ZoneInfo("America/New_York"), ZoneInfo("Europe/London"), dt.timezone.utc
for sub in (("live_ai",), ("r2", "tracks", "idx_us"), ("r2", "tracks", "stake")):
    sys.path.insert(0, os.path.join(LAB, *sub))
sys.path.insert(0, LAB)
REL = 1e-12
PLANS = [("F3S", "0:3;3000:2;6000:1;12000:0.5", "F3"), ("F2S", "0:2;6000:1;12000:0.5", "F2"), ("F1S", "0:1;12000:0.5", "F1"),
         ("D2", "0:10;3000:5;10000:2;20000:1", "D2"), ("S7", "0:7;3000:3.5;10000:1.4;20000:0.7", "S7")]
RISK_KEYS = [0.0, 999.99, 2999.99, 3000.0, 3000.01, 5999.99, 6000.0, 9999.99, 10000.0, 11999.99, 12000.0, 19999.99, 20000.0,
             50000.0, 10000000.0]


def secs(t):
    return int(t.timestamp())


# ------------------------------------------------------------------ clock
def us_switches(y):
    """US summer time on and off, UTC (2nd Sunday of March 07:00, 1st Sunday of November 06:00)"""
    def nth_sun(m, n):
        d = dt.date(y, m, 1)
        d += dt.timedelta(days=(6 - d.weekday()) % 7 + 7 * (n - 1))
        return d
    on = dt.datetime.combine(nth_sun(3, 2), dt.time(7), UTC)
    off = dt.datetime.combine(nth_sun(11, 1), dt.time(6), UTC)
    return on, off


def uk_switches(y):
    def last_sun(m):
        d = dt.date(y, m, 31)
        return d - dt.timedelta(days=(d.weekday() + 1) % 7)
    return dt.datetime.combine(last_sun(3), dt.time(1), UTC), dt.datetime.combine(last_sun(10), dt.time(1), UTC)


def wall(u, tz):
    """the wall clock of tz at UTC second u, as seconds read as if UTC (MQL5's convention)"""
    w = dt.datetime.fromtimestamp(u, UTC).astimezone(tz).replace(tzinfo=None)
    return int((w - dt.datetime(1970, 1, 1)).total_seconds())


def clock_vectors():
    import pont
    inst = []
    for y in (2012, 2016, 2020, 2024, 2035):
        on, off = us_switches(y)
        for t in (on, off):
            inst += [secs(t) - 1, secs(t)]
        k_on, k_off = uk_switches(y)
        for t in (k_on, k_off):
            inst += [secs(t) - 1, secs(t)]
    for y in (2013, 2019, 2026):                              # the gap weeks: US switched, UK not yet, and back
        on, off = us_switches(y)
        inst += [secs(on) + 3 * 86400 + 12 * 3600, secs(off) - 3 * 86400 + 9 * 3600]
    base = [dt.datetime(2013, 1, 1, 0, 0, tzinfo=UTC), dt.datetime(2017, 12, 31, 21, 59, 59, tzinfo=UTC),
            dt.datetime(2018, 6, 15, 13, 30, tzinfo=UTC), dt.datetime(2020, 2, 29, 23, 0, tzinfo=UTC),
            dt.datetime(2021, 12, 31, 23, 59, tzinfo=UTC), dt.datetime(2022, 7, 1, 20, 0, tzinfo=UTC),
            dt.datetime(2024, 2, 29, 12, 0, tzinfo=UTC), dt.datetime(2025, 11, 2, 5, 30, tzinfo=UTC),
            dt.datetime(2026, 3, 8, 6, 59, 59, tzinfo=UTC), dt.datetime(2026, 3, 8, 7, 0, 0, tzinfo=UTC),
            dt.datetime(2026, 11, 1, 5, 59, 59, tzinfo=UTC), dt.datetime(2026, 11, 13, 9, 0, tzinfo=UTC),
            dt.datetime(2030, 1, 4, 22, 0, tzinfo=UTC), dt.datetime(2035, 12, 31, 23, 0, tzinfo=UTC)]
    inst += [secs(t) for t in base]
    inst = sorted(set(inst))
    assert len(inst) == 60, len(inst)
    srv = [wall(u, NY) + 7 * 3600 for u in inst]
    back = [int(v) for v in pont.server_to_utc(np.array(srv, np.int64)).as_unit("s").asi8]
    rows = []
    for u, s, b in zip(inst, srv, back):
        us = int(dt.datetime.fromtimestamp(u, UTC).astimezone(NY).dst() != dt.timedelta(0))
        uk = int(dt.datetime.fromtimestamp(u, UTC).astimezone(LDN).dst() != dt.timedelta(0))
        rows.append([u, s, wall(u, NY), wall(u, LDN), b, us, uk])
    return rows


# ------------------------------------------------------------------ calendar
def nyse_vectors():
    import idxus_lib as cm
    D = dt.date
    days = [D(2013, 3, 29), D(2013, 7, 3), D(2013, 12, 24), D(2014, 1, 20), D(2015, 4, 3), D(2015, 11, 27), D(2016, 2, 15),
            D(2016, 12, 26), D(2017, 1, 2), D(2018, 12, 6), D(2018, 5, 28), D(2018, 7, 3), D(2018, 12, 5), D(2018, 12, 24),
            D(2019, 7, 4), D(2019, 9, 2), D(2019, 11, 28), D(2019, 11, 29), D(2020, 7, 3), D(2021, 6, 18), D(2021, 12, 24),
            D(2021, 12, 31), D(2022, 6, 20), D(2023, 1, 2), D(2023, 6, 19), D(2024, 1, 15), D(2024, 7, 3), D(2025, 1, 9),
            D(2025, 2, 17), D(2025, 12, 24), D(2026, 4, 3), D(2026, 7, 3), D(2026, 12, 24), D(2027, 6, 18), D(2027, 9, 6),
            D(2027, 12, 24), D(2028, 4, 14), D(2020, 11, 25), D(2022, 12, 23), D(2026, 11, 14)]
    assert len(days) == 40 and len(set(days)) == 40
    rows = []
    for d in days:
        full, half = cm.us_holidays(d.year)
        kind = 1 if d in full else (2 if d in half else 0)
        rows.append([int((dt.datetime.combine(d, dt.time()) - dt.datetime(1970, 1, 1)).total_seconds()), kind])
    kinds = [r[1] for r in rows]
    assert kinds.count(1) >= 15 and kinds.count(2) >= 8 and kinds.count(0) >= 5, kinds
    return rows


def atd_vectors():
    from tracks.trend import strategy as trend
    pts = [("2013-01-04 21:00", 5), ("2016-03-11 21:00", 1), ("2016-03-12 10:00", 1), ("2016-03-13 08:00", 2),
           ("2016-11-04 20:00", 1), ("2018-12-31 22:00", 5), ("2019-04-18 16:00", 3), ("2019-12-24 20:00", 5),
           ("2020-02-28 21:59", 1), ("2020-10-30 03:00", 5), ("2021-03-12 21:00", 5), ("2021-07-02 13:00", 10),
           ("2021-11-05 19:00", -1), ("2022-01-01 12:00", 0), ("2024-02-29 22:00", 2), ("2025-11-02 04:00", 1),
           ("2026-03-06 20:00", 5), ("2026-11-13 21:00", 5), ("2030-12-27 23:00", 3), ("2035-06-29 20:00", 5)]
    rows = []
    for t, n in pts:
        ts = pd.DatetimeIndex([pd.Timestamp(t, tz="UTC")])
        want = trend.add_trading_days(ts, n)
        assert not pd.isna(want[0]), t
        rows.append([secs(ts[0]), n, secs(want[0])])
    return rows


def bday_vectors():
    pts = [("2013-01-05", 1), ("2013-01-05", -1), ("2013-01-05", 0), ("2013-01-06", 0), ("2016-02-29", 2), ("2017-12-29", 2),
           ("2018-06-01", -3), ("2019-11-27", 2), ("2020-03-06", 5), ("2020-12-31", 1), ("2021-04-02", 2), ("2021-12-31", -10),
           ("2022-01-01", 2), ("2024-07-04", 2), ("2025-01-03", 10), ("2026-11-13", 2), ("2026-11-14", -2), ("2027-02-26", 3),
           ("2031-08-30", 1), ("2035-12-28", 4)]
    rows = []
    for d, n in pts:
        t = pd.Timestamp(d)
        rows.append([int(t.value // 10 ** 9), n, int((t + BDay(n)).value // 10 ** 9)])
    return rows


def orx_vectors():
    days = ["2013-01-02", "2014-03-28", "2015-10-29", "2016-03-24", "2018-11-01", "2019-12-27", "2020-02-27", "2021-03-26",
            "2021-10-28", "2026-11-12"]
    rows = []
    for d in days:
        t = pd.Timestamp(d)
        ex = (t + BDay(2)).to_pydatetime().replace(hour=16, tzinfo=NY)
        rows.append([int(t.value // 10 ** 9), int(ex.astimezone(UTC).timestamp())])
    return rows


# ------------------------------------------------------------------ the lab's ML candidates and brk72 orders (fresh processes)
def spawn(src):
    r = subprocess.run([sys.executable, "-I", "-c", src], capture_output=True, text=True,
                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    if r.returncode:
        raise SystemExit("lab process failed:\n" + r.stderr[-4000:])
    return json.loads(r.stdout.strip().splitlines()[-1])


PRELUDE = f"""
import sys, os, json
sys.dont_write_bytecode = True
import numpy as np, pandas as pd
LAB = {LAB!r}
sys.path.insert(0, LAB); sys.path.insert(0, os.path.join(LAB, "r2"))
import recalc
reg = {{(s[1], s[2]): s for s in recalc.sleeves()}}
CUT = pd.Timestamp({CUT!r}, tz="UTC")
def frame(sym):
    m1 = pd.read_parquet(os.path.join(LAB, "data", "fp", sym + "_m1.parquet"), filters=[("ts", "<", CUT)])
    assert len(m1) and m1.index.max() < CUT
    return m1
"""


def f1_candidates(sym):
    src = PRELUDE + f"""
M = sys.modules["r2_ml_strategy"]
params = reg[("F1_brk_ridge_filter", {sym!r})][4]
spec = M.load_model(params["model"])["frozen"]
f = M.candidates(frame({sym!r}), **params)
s = M.score_model(f, spec)
X = f[M.FEATURES].to_numpy(float)
print(json.dumps({{"x": X.tolist(), "score": [float(v) for v in s], "thr": float(M._thr(spec, params["q"])),
                  "spec": spec}}))
"""
    return spawn(src)


def bke_risks():
    src = PRELUDE + """
track, name, sym, mo, params = reg[("brk72_24h_wd", "ethusd")]
m1 = frame("ethusd")
o = mo(m1, **params).reset_index(drop=True)
mid = ((m1["bc"] + m1["ac"]) / 2.0).to_numpy()
idx = m1.index
out = []
for k in np.linspace(0, len(o) - 1, 10).astype(int):
    D = pd.Timestamp(o["dec_time"].iat[k])
    i = int(idx.searchsorted(D, side="left")) - 1           # the last bar starting before D
    sd, P = float(o["stop_dist"].iat[k]), float(mid[i])
    out.append([sd, P, 1e4 * sd / P, int(D.value // 10**9)])       # s1_run.py:105 riskbp = 1e4 * stop_dist / P
print(json.dumps({"rows": out}))
"""
    return spawn(src)["rows"]


def f1_vectors():
    picked, spec, thr = [], None, None
    for sym in ("btcusd", "ethusd"):
        c = f1_candidates(sym)
        spec, thr = c["spec"], c["thr"]
        x, s = np.array(c["x"]), np.array(c["score"])
        ok = np.isfinite(x).all(axis=1)
        x, s = x[ok], s[ok]
        near = np.argsort(np.abs(s - thr))[:3]                # the three nearest the threshold
        spread = np.argsort(s)[np.linspace(0, len(s) - 1, 9).astype(int)]
        for i in list(near) + [j for j in spread if j not in near][:9]:
            picked.append(x[i].tolist())
    assert len(picked) == 24
    # made-up edges: clip on both sides, the dummies' boundaries (hour 8/10/11/12/13/15, dow 0/4), off-range dummies
    base = picked[0]
    edges = []
    for hour, dow, scale in ((8.0, 0.0, 9.0), (10.0, 4.0, -9.0), (11.0, 1.0, 0.0), (12.0, 4.0, 3.9), (13.0, 2.0, -4.1),
                             (15.0, 5.0, 100.0)):
        v = [base[k] + scale * (k + 1) for k in range(13)] + [hour, dow]
        edges.append(v)
    vecs = picked + edges
    num, mean, std = spec["num"], spec["mean"], spec["std"]
    clip = spec.get("clip", 4.0)
    feats = ["brk", "bar", "body", "ret4", "ret14", "ret70", "chan", "vol", "pos", "seq", "opp", "pdd", "dret", "hour", "dow"]
    pos = {f: i for i, f in enumerate(feats)}
    rows = []
    for v in vecs:
        s = 0.0
        for name, mu, sd, cf in zip(num, mean, std, spec["coef"]):
            z = (v[pos[name]] - mu) / sd
            if z < -clip:
                z = -clip
            if z > clip:
                z = clip
            s = s + z * cf
        for j, (name, lo, hi) in enumerate(spec["dummies"]):
            d = 1.0 if (v[pos[name]] >= lo and v[pos[name]] <= hi) else 0.0
            s = s + d * spec["coef"][len(num) + j]
        seq = spec["intercept"] + s
        rows.append(v + [seq])
    lab = lab_scores(vecs)                                    # the lab's score_model (numpy), fresh process
    for r, ls in zip(rows, lab):
        assert abs(ls - r[-1]) <= REL * max(abs(r[-1]), 1e-3), (ls, r[-1])
    return rows, thr


def lab_scores(vecs):
    src = PRELUDE + f"""
M = sys.modules["r2_ml_strategy"]
params = reg[("F1_brk_ridge_filter", "btcusd")][4]
spec = M.load_model(params["model"])["frozen"]
X = np.array({vecs!r}, dtype=float)
f = pd.DataFrame(X, columns=M.FEATURES)
print(json.dumps({{"score": [float(v) for v in M.score_model(f, spec)]}}))
"""
    return spawn(src)["score"]


# ------------------------------------------------------------------ account and primitives
def risk_vectors():
    import growth as G
    out = []
    for name, text, sched in PLANS:
        thr, pct = G.SCHEDULES[sched]
        pairs = [tuple(map(float, p.split(":"))) for p in text.split(";")]
        assert [p[0] for p in pairs[1:]] == list(thr) and [p[1] for p in pairs] == list(pct), name
        th, pc = np.array(thr, np.float64), np.array(pct, np.float64)
        out.append((name, text, len(pairs), [float(G._pct.py_func(k, th, pc)) for k in RISK_KEYS]))
    return out


def series():
    rng = np.random.default_rng(20261113)
    x = np.round(rng.gamma(2.0, 1.1, 48) + 0.05, 2)
    x[0] = np.nan
    x[17] = np.nan
    for k in (30, 31, 33, 34, 35, 36):                       # a stretch that drops under min_periods 9
        x[k] = np.nan
    s = pd.Series(x)
    wil = s.ewm(alpha=1.0 / 14, adjust=False).mean().to_numpy()
    sma = s.rolling(14, min_periods=9).mean().to_numpy()
    return x, wil, sma


# ------------------------------------------------------------------ the file
def lit(v):
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    v = float(v)
    if not math.isfinite(v):
        return "0.0"
    s = "%.17g" % v
    return s if any(c in s for c in ".en") else s + ".0"


def table(ctype, name, vals, per=8):
    body = []
    for i in range(0, len(vals), per):
        body.append("   " + ", ".join(lit(v) for v in vals[i:i + per]))
    return f"{ctype} {name}[] = {{\n" + ",\n".join(body) + "};\n"


def render(v):
    clk, nyse, atd, bday, orx, (f1, thr), risk, rbp, (x, wil, sma) = v
    n_risk = sum(len(r[3]) + 1 for r in risk)
    total = len(clk) + len(nyse) + len(atd) + len(bday) + len(orx) + len(f1) + len(rbp) + n_risk + 2 * len(x)
    flat = lambda rows: [c for r in rows for c in r]
    nan_w = [0 if math.isfinite(w) else 1 for w in wil]
    nan_s = [0 if math.isfinite(s) else 1 for s in sma]
    nan_x = [0 if math.isfinite(a) else 1 for a in x]
    h = []
    h.append("""//+------------------------------------------------------------------+
//| CR_Golden.mqh - GENERATED by tools/gen_golden.py (step K): the    |
//| self-test vectors of SPEC 7 T10, each computed by the lab's own  |
//| code (zoneinfo, pont, us_holidays, trend.add_trading_days,       |
//| pandas BDay, ml/strategy.py, the brk72 orders, growth._pct,      |
//| pandas ewm and rolling). Do not edit by hand: run the generator. |
//|                                                                  |
//| GoldenCheck(why), called by CR_Main at OnInit after the build    |
//| constants check: false (and why) on the first vector the EA does |
//| not reproduce, which blocks trading (SELFTEST ok=0). Times are   |
//| compared exactly; doubles within 1e-12 relative (SPEC 7); the    |
//| rates of the risk tables exactly. The NYSE dates use the rules   |
//| (ClkHolKind), so a typed InpExtraClosures entry cannot fail it.  |
//| The risk tables go through SizParseTable and LedRate; the live   |
//| table (InpRiskTable) is put back afterwards.                     |
//+------------------------------------------------------------------+
#ifndef CR_GOLDEN_MQH
#define CR_GOLDEN_MQH
#include "CR_Types.mqh"
#include "CR_Clock.mqh"
#include "CR_Journal.mqh"
#include "CR_Math.mqh"
#include "CR_Ledger.mqh"
#include "CR_Sizing.mqh"
#include "CR_Rule_Brk72.mqh"
#include "CR_Rule_F1.mqh"
#include "CR_Rule_Orb.mqh"
""")
    h.append(f"#define CR_GOLDEN_N {total}                // vectors checked (SELFTEST golden=)\n")
    h.append("#define CR_GOLD_REL 1e-12               // doubles: relative tolerance (SPEC 7)\n")
    h.append(f"#define CR_GOLD_NCLK {len(clk)}\n#define CR_GOLD_NNYSE {len(nyse)}\n#define CR_GOLD_NATD {len(atd)}\n"
             f"#define CR_GOLD_NBDAY {len(bday)}\n#define CR_GOLD_NORX {len(orx)}\n#define CR_GOLD_NF1 {len(f1)}\n"
             f"#define CR_GOLD_NRBP {len(rbp)}\n#define CR_GOLD_NRISK {len(risk)}\n#define CR_GOLD_NKEY {len(RISK_KEYS)}\n"
             f"#define CR_GOLD_NSER {len(x)}\n\n")
    h.append("// clock: utc, server, New York, London, server -> utc (pont), US summer time, UK summer time (7 per row)\n")
    h.append(table("long", "CR_GOLD_CLK", flat(clk), 7))
    h.append("// NYSE: New York date 00:00, kind (0 open, 1 full closure, 2 13:00 half day)\n")
    h.append(table("long", "CR_GOLD_NYSE", flat(nyse), 8))
    h.append("// AddTradingDays: utc, n, result utc\n")
    h.append(table("long", "CR_GOLD_ATD", flat(atd), 6))
    h.append("// BusinessDays: date 00:00, n, result\n")
    h.append(table("long", "CR_GOLD_BDAY", flat(bday), 6))
    h.append("// ORX time exit: London date 00:00, 16:00 New York on BusinessDays(date, 2) as utc\n")
    h.append(table("long", "CR_GOLD_ORX", flat(orx), 6))
    h.append(f"// F1: the 15 features (FEATURES order), then the score (16 per row); the threshold is {lit(thr)}\n")
    h.append(table("double", "CR_GOLD_F1", flat(f1), 4))
    h.append("// K1 riskbp: stop_dist, P (mid close of the last bar before the decision), the lab's 1e4 x stop_dist / P\n")
    h.append(table("double", "CR_GOLD_RBP", flat([[a, b, c] for a, b, c, _ in rbp]), 3))
    h.append("// ... and the decision of each (utc), for the message\n")
    h.append(table("long", "CR_GOLD_RBP_T", [t for _, _, _, t in rbp], 5))
    h.append("// risk tables: the keys, then per plan the number of pairs and the rate at each key\n")
    h.append(table("double", "CR_GOLD_KEYS", RISK_KEYS, 6))
    h.append(table("int", "CR_GOLD_RISK_NP", [r[2] for r in risk], 3))
    h.append(table("double", "CR_GOLD_RISK", flat([r[3] for r in risk]), 11))
    h.append("string CR_GOLD_RISK_TXT[] = {" + ", ".join(f'"{r[1]}"' for r in risk) + "};\n")
    h.append("string CR_GOLD_RISK_NAME[] = {" + ", ".join(f'"{r[0]}"' for r in risk) + "};\n")
    h.append("// the series (1 = NaN in the _NAN tables), pandas ewm(alpha=1/14, adjust=False).mean() and rolling(14, 9).mean()\n")
    h.append(table("double", "CR_GOLD_X", x, 8))
    h.append(table("int", "CR_GOLD_X_NAN", nan_x, 24))
    h.append(table("double", "CR_GOLD_WIL", wil, 4))
    h.append(table("int", "CR_GOLD_WIL_NAN", nan_w, 24))
    h.append(table("double", "CR_GOLD_SMA", sma, 4))
    h.append(table("int", "CR_GOLD_SMA_NAN", nan_s, 24))
    h.append("""
CRuleF1   g_gold_f1;                   // scratch objects of the self-test (never the sleeves' own)
CrWilder  g_gold_w;
CrRollSum g_gold_s;

bool GoldNear(const double a, const double b)
  {
   if(!MathIsValidNumber(a) || !MathIsValidNumber(b)) return false;
   double m = MathAbs(b);
   if(m < 1.0) m = 1.0;
   return MathAbs(a - b) <= CR_GOLD_REL * m;
  }

string GoldMsg(const string what, const int k, const string got, const string want)
  {
   return "golden " + what + " " + IntegerToString(k) + ": got " + got + ", want " + want;
  }

bool GoldClock(string &why)
  {
   for(int k = 0; k < CR_GOLD_NCLK; k++)
     {
      int b = 7 * k;
      datetime u = (datetime)CR_GOLD_CLK[b];
      long srv = (long)ClkUtcToServer(u), ny = (long)ClkUtcToNy(u), ldn = (long)ClkUtcToLdn(u);
      long back = (long)ClkServerToUtc((datetime)CR_GOLD_CLK[b + 1]);
      long us = ClkUsDst(u) ? 1 : 0, uk = ClkUkDst(u) ? 1 : 0;
      if(srv != CR_GOLD_CLK[b + 1] || ny != CR_GOLD_CLK[b + 2] || ldn != CR_GOLD_CLK[b + 3] || back != CR_GOLD_CLK[b + 4]
         || us != CR_GOLD_CLK[b + 5] || uk != CR_GOLD_CLK[b + 6])
        {
         why = GoldMsg("clock", k, JI(srv) + "/" + JI(ny) + "/" + JI(ldn) + "/" + JI(back) + "/" + JI(us) + JI(uk),
                       JI(CR_GOLD_CLK[b + 1]) + "/" + JI(CR_GOLD_CLK[b + 2]) + "/" + JI(CR_GOLD_CLK[b + 3]) + "/"
                       + JI(CR_GOLD_CLK[b + 4]) + "/" + JI(CR_GOLD_CLK[b + 5]) + JI(CR_GOLD_CLK[b + 6]));
         return false;
        }
     }
   return true;
  }

bool GoldCalendar(string &why)
  {
   for(int k = 0; k < CR_GOLD_NNYSE; k++)
     {
      int gold = 0;
      long kind = ClkHolKind(ClkDayNo((datetime)CR_GOLD_NYSE[2 * k]), gold);
      if(kind != CR_GOLD_NYSE[2 * k + 1])
        {
         why = GoldMsg("nyse", k, JI(kind), JI(CR_GOLD_NYSE[2 * k + 1]));
         return false;
        }
     }
   for(int k = 0; k < CR_GOLD_NATD; k++)
     {
      long got = (long)ClkAddTradingDays((datetime)CR_GOLD_ATD[3 * k], (int)CR_GOLD_ATD[3 * k + 1]);
      if(got != CR_GOLD_ATD[3 * k + 2])
        {
         why = GoldMsg("add_trading_days", k, JI(got), JI(CR_GOLD_ATD[3 * k + 2]));
         return false;
        }
     }
   for(int k = 0; k < CR_GOLD_NBDAY; k++)
     {
      long got = (long)ClkBusinessDays((datetime)CR_GOLD_BDAY[3 * k], (int)CR_GOLD_BDAY[3 * k + 1]);
      if(got != CR_GOLD_BDAY[3 * k + 2])
        {
         why = GoldMsg("business_days", k, JI(got), JI(CR_GOLD_BDAY[3 * k + 2]));
         return false;
        }
     }
   for(int k = 0; k < CR_GOLD_NORX; k++)
     {
      long got = (long)OrxExitTime((datetime)CR_GOLD_ORX[2 * k]);
      if(got != CR_GOLD_ORX[2 * k + 1])
        {
         why = GoldMsg("orx_exit", k, JI(got), JI(CR_GOLD_ORX[2 * k + 1]));
         return false;
        }
     }
   return true;
  }

bool GoldScores(string &why)
  {
   ArrayResize(g_gold_f1.m_x, CR_F1_NFEAT);
   for(int k = 0; k < CR_GOLD_NF1; k++)
     {
      int b = (CR_F1_NFEAT + 1) * k;
      for(int j = 0; j < CR_F1_NFEAT; j++) g_gold_f1.m_x[j] = CR_GOLD_F1[b + j];
      double s = g_gold_f1.Score();
      if(!GoldNear(s, CR_GOLD_F1[b + CR_F1_NFEAT]))
        {
         why = GoldMsg("f1_score", k, JD(s), JD(CR_GOLD_F1[b + CR_F1_NFEAT]));
         return false;
        }
     }
   for(int k = 0; k < CR_GOLD_NRBP; k++)
     {
      double r = Brk72RiskBp(CR_GOLD_RBP[3 * k], CR_GOLD_RBP[3 * k + 1]);
      if(!GoldNear(r, CR_GOLD_RBP[3 * k + 2]))
        {
         why = GoldMsg("riskbp", k, JD(r), JD(CR_GOLD_RBP[3 * k + 2]) + " (decision " + JI(CR_GOLD_RBP_T[k]) + ")");
         return false;
        }
     }
   return true;
  }

bool GoldRisk(string &why)
  {
   bool ok = true;
   for(int t = 0; t < CR_GOLD_NRISK && ok; t++)
     {
      double fr[], pc[];
      int n = 0;
      string err = "";
      if(!SizParseTable(CR_GOLD_RISK_TXT[t], fr, pc, n, err) || n != CR_GOLD_RISK_NP[t])
        {
         why = GoldMsg("risk_table", t, CR_GOLD_RISK_NAME[t] + " parsed into " + IntegerToString(n) + " pairs " + err,
                       IntegerToString(CR_GOLD_RISK_NP[t]) + " pairs");
         ok = false;
         break;
        }
      LedSetRates(fr, pc, n);
      for(int k = 0; k < CR_GOLD_NKEY; k++)
        {
         double got = LedRate(CR_GOLD_KEYS[k]);
         double want = CR_GOLD_RISK[t * CR_GOLD_NKEY + k];
         if(got != want)
           {
            why = GoldMsg("risk_table", t, CR_GOLD_RISK_NAME[t] + " at " + JD(CR_GOLD_KEYS[k]) + ": " + JD(got), JD(want));
            ok = false;
            break;
           }
        }
     }
   LedSetRates(g_siz_from, g_siz_pct, g_siz_n);        // the live table (InpRiskTable) again
   return ok;
  }

bool GoldSeries(string &why)
  {
   g_gold_w.Init(14);
   g_gold_s.Init(14, 9);
   for(int k = 0; k < CR_GOLD_NSER; k++)
     {
      double x = (CR_GOLD_X_NAN[k] != 0) ? CrNaN() : CR_GOLD_X[k];
      double w = g_gold_w.Push(x);
      g_gold_s.Push(x);
      double m = g_gold_s.Mean();
      bool wn = !MathIsValidNumber(w), mn = !MathIsValidNumber(m);
      if(wn != (CR_GOLD_WIL_NAN[k] != 0) || (!wn && !GoldNear(w, CR_GOLD_WIL[k])))
        {
         why = GoldMsg("wilder", k, JD(w), (CR_GOLD_WIL_NAN[k] != 0) ? "nan" : JD(CR_GOLD_WIL[k]));
         return false;
        }
      if(mn != (CR_GOLD_SMA_NAN[k] != 0) || (!mn && !GoldNear(m, CR_GOLD_SMA[k])))
        {
         why = GoldMsg("sma", k, JD(m), (CR_GOLD_SMA_NAN[k] != 0) ? "nan" : JD(CR_GOLD_SMA[k]));
         return false;
        }
     }
   return true;
  }

bool GoldenCheck(string &why)
  {
   why = "";
   if(!GoldClock(why)) return false;
   if(!GoldCalendar(why)) return false;
   if(!GoldScores(why)) return false;
   if(!GoldRisk(why)) return false;
   if(!GoldSeries(why)) return false;
   return true;
  }
#endif
""")
    return "".join(h)


def vectors():
    clk = clock_vectors()
    nyse = nyse_vectors()
    atd = atd_vectors()
    bday = bday_vectors()
    orx = orx_vectors()
    f1 = f1_vectors()
    risk = risk_vectors()
    rbp = bke_risks()
    ser = series()
    return clk, nyse, atd, bday, orx, f1, risk, rbp, ser


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="compare with the file on disk; write nothing")
    a = ap.parse_args(argv)
    text = render(vectors())
    text.encode("ascii")
    if a.check:
        cur = open(OUT).read() if os.path.exists(OUT) else ""
        same = cur == text
        print(f"gen_golden: {'up to date' if same else 'DIFFERENT from what the generator writes'}: {OUT}")
        return 0 if same else 1
    with open(OUT, "w", encoding="ascii", newline="\n") as f:
        f.write(text)
    n = text.count("\n")
    print(f"gen_golden: wrote {OUT} ({n} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
