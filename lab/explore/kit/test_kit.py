"""Self-tests of the kit: synthetic data only, no network, no lab data (about 2 minutes).
    PYTHONDONTWRITEBYTECODE=1 python3 -B lab/explore/kit/test_kit.py          (all offline tests)
    PYTHONDONTWRITEBYTECODE=1 python3 -B lab/explore/kit/test_kit.py --net    (+ one month of each source, decoded)
    PYTHONDONTWRITEBYTECODE=1 python3 -B lab/explore/kit/test_kit.py --net-venues   (+ the three crypto venues only)
    PYTHONDONTWRITEBYTECODE=1 python3 -B lab/explore/kit/test_kit.py --real-bars    (+ oil and the 40 shares' prepared bars,
                                                                                   and the universe's daily bars, kit v2.2)
"""
import io
import json
import lzma
import os
import shutil
import sys
import tempfile
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats as st  # noqa: E402

from kit import checks, costs, data, judge, sim, stats, synth  # noqa: E402

TMP = tempfile.mkdtemp(prefix="kit_test_")
os.environ["EXPLORE_CACHE"] = os.path.join(TMP, "cache")
os.environ["EXPLORE_VAL_LOG"] = os.path.join(TMP, "val_access.log")
TEN_DIR = synth.ten_fixture(os.path.join(TMP, "ten"))
TEN = stats.ten_trades(TEN_DIR)
RESULTS, NUMBERS = [], {}
U = lambda s: pd.Timestamp(s, tz="UTC")  # noqa: E731


def check(name, cond, info=""):
    RESULTS.append((name, bool(cond), info))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""), flush=True)


# ------------------------------------------------------------------ fake HTTP server for the readers
REQ = []


def _fake(url, **kw):
    REQ.append(url)
    if "dukascopy" in url:
        p = url.split("/datafeed/")[1].split("/")
        y, m = int(p[1]), int(p[2]) + 1
        t0 = pd.Timestamp(year=y, month=m, day=1, tz="UTC")
        hrs = pd.date_range(t0, t0 + pd.offsets.MonthBegin(1), freq="h", inclusive="left")
        sec = ((hrs - t0).total_seconds()).astype(np.uint32)
        rec = np.zeros(len(hrs), dtype=">u4,>u4,>u4,>u4,>u4,>f4")
        px = 110000 + np.arange(len(hrs)) % 50          # EURUSD 1.10000.. in points
        rec["f0"], rec["f1"], rec["f2"], rec["f3"], rec["f4"], rec["f5"] = sec, px, px + 3, px - 5, px + 7, 1.0
        return lzma.compress(rec.tobytes(), format=lzma.FORMAT_ALONE)
    if "binance" in url and "klines" in url:
        name = url.rsplit("/", 1)[1]
        y, m = int(name.split("-")[-2]), int(name.split("-")[-1][:2])
        t0 = pd.Timestamp(year=y, month=m, day=1, tz="UTC")
        hrs = pd.date_range(t0, t0 + pd.offsets.MonthBegin(1), freq="h", inclusive="left")
        mul = 1000 if y >= 2025 else 1                   # 2025+ spot files are in microseconds
        ms = (hrs.as_unit("ns").asi8 // 1_000_000) * mul
        rows = "\n".join(f"{a},100,101,99,100.5,10,{a + 3599999 * mul},1000,5,4,400,0" for a in ms)
        return _zip(name.replace(".zip", ".csv"), rows)
    if "fundingRate" in url:
        name = url.rsplit("/", 1)[1]
        y, m = int(name.split("-")[-2]), int(name.split("-")[-1][:2])
        t0 = pd.Timestamp(year=y, month=m, day=1, tz="UTC")
        ts = pd.date_range(t0, t0 + pd.offsets.MonthBegin(1), freq="8h", inclusive="left").as_unit("ns").asi8 // 10 ** 6
        return _zip(name.replace(".zip", ".csv"), "calc_time,funding_interval_hours,last_funding_rate\n" +
                    "\n".join(f"{a},8,0.0001" for a in ts))
    if "fred" in url:                                    # a server that ignores coed: rows into 2023
        d = pd.date_range("2021-06-01", "2023-01-31", freq="B")
        return ("observation_date,X\n" + "\n".join(f"{x.date()},{i}" for i, x in enumerate(d))).encode()
    if "yahoo" in url:                                   # a server that ignores period2
        d = pd.date_range("2021-11-01 14:30", "2022-02-01 14:30", freq="B", tz="UTC")
        ts = [int(x.timestamp()) for x in d]
        q = {"open": [1.0] * len(ts), "high": [1.0] * len(ts), "low": [1.0] * len(ts), "close": list(range(len(ts))),
             "volume": [1] * len(ts)}
        return json.dumps({"chart": {"result": [{"meta": {"exchangeTimezoneName": "America/New_York"}, "timestamp": ts,
                                                 "indicators": {"quote": [q]}}]}}).encode()
    raise AssertionError(url)


def _zip(name, txt):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr(name, txt)
    return b.getvalue()


VALDECL = {"frozen_rule": "the main configuration of declared.json", "bars": "CHARTER VAL bars", "cut": "2025-12-31",
           "attack": "independent re-implementation gave the same trades"}


def test_period_lock():
    real = data.http_get
    data.http_get = _fake
    try:
        data.lock()
        REQ.clear()
        b = data.duka_h1("EURUSD", 2020)
        yrs = sorted({int(u.split("/datafeed/")[1].split("/")[1]) for u in REQ})
        check("lock: Dukascopy rows < 2022, nothing of 2022+ requested", b.index.max() < U("2022-01-01") and yrs == [2020, 2021],
              f"{len(REQ)} files, last row {b.index.max()}")
        REQ.clear()
        k = data.binance_klines("BTCUSDT", start="2021-10")
        f = data.binance_funding(start="2021-11")
        check("lock: Binance klines/funding < 2022, no 2022 file", k.index.max() < U("2022-01-01") and
              f.index.max() < U("2022-01-01") and not any("2022-" in u for u in REQ) and "taker_buy_base" in k,
              f"{len(REQ)} files")
        REQ.clear()
        fr = data.fred("X", known=data.rule_next_bday_utc(13, 1))
        check("lock: FRED asks coed=2021-12-31, cuts a server that sends more, indexed by known time",
              "coed=2021-12-31" in REQ[0] and fr.index.max() < U("2022-01-01") and fr.index.max() == U("2021-12-31 13:00"),
              f"last known {fr.index.max()}")
        try:
            data.fred("X", known=None)
            check("FRED without a known-at rule raises", False)
        except ValueError:
            check("FRED without a known-at rule raises", True)
        REQ.clear()
        y = data.yahoo_daily("^GSPC", known=data.rule_local_close("16:00"))
        check("lock: Yahoo period2 bounded, rows < 2022, known at the US close (21:00 UTC in winter)",
              "period2=1640995199" in REQ[0] and y.index.max() < U("2022-01-01") and y.index.max() == U("2021-12-31 21:00"),
              f"last {y.index.max()}")
        idea = os.path.join(TMP, "ideas", "077_x")
        os.makedirs(idea)
        try:
            data.unlock_val(idea)
            check("unlock_val refused without val_declared.json", False)
        except data.PeriodError:
            check("unlock_val refused without val_declared.json", not os.path.exists(os.environ["EXPLORE_VAL_LOG"]))
        json.dump(VALDECL, open(os.path.join(idea, "val_declared.json"), "w"))
        json.dump({"verdict": "pass"}, open(os.path.join(idea, "results.json"), "w"))
        open(os.environ["EXPLORE_VAL_LOG"], "w").write("previous line\n")
        line = data.unlock_val(idea)
        log = open(os.environ["EXPLORE_VAL_LOG"]).read().splitlines()
        j = json.loads(log[-1])
        check("unlock_val appends one JSON line (time, track explore, label look:<idea>, period val)",
              len(log) == 2 and log[0] == "previous line" and set(j) == {"time", "track", "label", "period"} and
              j["track"] == "explore" and j["label"] == "look:077_x" and j["period"] == "val" and j == line)
        REQ.clear()
        b2 = data.duka_h1("EURUSD", 2025)
        k2 = data.binance_klines("BTCUSDT", start="2025-11")
        check("unlocked: rows to 2025-12-31, nothing of 2026 requested or returned",
              b2.index.max() < U("2026-01-01") and b2.index.max() >= U("2025-12-31") and k2.index.max() < U("2026-01-01")
              and not any("/2026/" in u or "2026-" in u for u in REQ), f"{len(REQ)} files, last {b2.index.max()}")
        cached = [os.path.join(r, x) for r, _, fs in os.walk(os.environ["EXPLORE_CACHE"]) for x in fs]
        check("cache holds no 2026 file", not any("2026" in os.path.basename(p) for p in cached), f"{len(cached)} files")
        z = pd.DataFrame({"v": 1.0}, index=pd.date_range("2025-12-31 22:00", periods=5, freq="h", tz="UTC"))
        check("cut() never returns 2026 even unlocked", data.cut(z).index.max() < U("2026-01-01"))
    finally:
        data.lock()
        data.http_get = real
        shutil.rmtree(os.environ["EXPLORE_CACHE"], ignore_errors=True)


def test_asof_and_known():
    s = pd.Series([1.0, 2.0], index=[U("2020-01-02 13:00"), U("2020-01-03 13:00")])
    v = data.asof_join(pd.DatetimeIndex([U("2020-01-02 12:59"), U("2020-01-02 13:00"), U("2020-01-03 12:00"),
                                         U("2020-01-03 13:00")]), s)
    check("asof_join: backward only, a value known at exactly t counts", np.isnan(v[0]) and list(v[1:]) == [1.0, 1.0, 2.0])
    k = data.known_at(pd.DatetimeIndex(["2019-03-08", "2019-03-11", "2019-11-01", "2019-11-04"]), time="16:00")
    check("known_at US close: 21:00 UTC in winter, 20:00 UTC in summer (DST)",
          [x.hour for x in k] == [21, 20, 20, 21], str([str(x) for x in k]))
    r = data.rule_next_bday_utc(13, 1)(pd.DatetimeIndex(["2021-12-31", "2020-01-03"]))
    check("published late: D + 1 business day 13:00 UTC (Friday -> Monday)",
          list(r) == [U("2022-01-03 13:00"), U("2020-01-06 13:00")])
    obs = pd.DatetimeIndex(["2020-01-02", "2020-01-03"])
    late = pd.Series([10.0, 20.0], index=r[:0].append(data.rule_next_bday_utc(13, 1)(obs)))
    v = data.asof_join(pd.DatetimeIndex([U("2020-01-03 12:00"), U("2020-01-03 13:00"), U("2020-01-06 12:59")]), late)
    check("a value published late is not used before its publication", list(v) == [np.nan, 10.0, 10.0] or
          (np.isnan(v[0]) and list(v[1:]) == [10.0, 10.0]), str(v))


def test_daily_bars_dst():
    t = pd.date_range("2019-03-06 00:00", "2019-03-13 00:00", freq="h", tz="UTC")
    h1 = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}, index=t)
    lab = data.trading_day(pd.DatetimeIndex([U("2019-03-07 21:00"), U("2019-03-07 22:00"), U("2019-03-12 20:00"),
                                             U("2019-03-12 21:00")]))
    check("17:00 New York boundary: 22:00 UTC in winter, 21:00 UTC in summer",
          [str(x.date()) for x in lab] == ["2019-03-07", "2019-03-08", "2019-03-12", "2019-03-13"], str(list(lab)))
    d = data.daily_bars(h1)
    check("daily_bars ny17: known_at = end of the day's last bar", d.loc["2019-03-12", "known_at"] == U("2019-03-12 21:00")
          and d.loc["2019-03-07", "known_at"] == U("2019-03-07 22:00"))
    du = data.daily_bars(h1, "utc")
    check("daily_bars utc: 24 bars, known at midnight", du.loc["2019-03-07", "n_bars"] == 24 and
          du.loc["2019-03-07", "known_at"] == U("2019-03-08"))


# ------------------------------------------------------------------ costs by hand
SH = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "spread_shape.json")))["shape"]
FPC = json.load(open(os.path.join(data.LAB, "r2", "fp_costs.json")))


def _how(t):
    n = pd.Timestamp(t).tz_convert("America/New_York")
    return n.dayofweek * 24 + n.hour


def test_costs():
    # gold, long, Wednesday 10:00 NY -> Thursday 10:00 NY: one rollover (Wednesday) = 3 nights (triple Wed)
    ti, to = U("2019-06-12 14:00"), U("2019-06-13 14:00")
    g = FPC["xauusd"]
    s_in = 0.19 / 4080 * 1300 * SH["xauusd"][_how(ti)]
    s_out = 0.19 / 4080 * 1300 * SH["xauusd"][_how(to)]
    fill = (1300 + s_in / 2) * (1 + 0.3e-4)
    out = (1300 - s_out / 2) * (1 - 0.3e-4)
    sw = 0.055 / 360 * fill * 3
    r = costs.round_trip("xauusd", 1, 1300.0, 1300.0, ti, to)
    check("gold: spread bp of 4080 x shape, slip 0.3 bp/side, swap long 5.5 %/360 x 3 (Wed triple)",
          abs(r["cost"] - (fill - out + sw)) < 1e-9 and costs.swap_nights(pd.DatetimeIndex([ti]), pd.DatetimeIndex([to]),
                                                                          "Wed")[0] == 3,
          f"cost {r['cost']:.4f} $ = {r['cost_bp']:.2f} bp (swap {sw:.4f})")
    rs = costs.round_trip("xauusd", 1, 1300.0, 1300.0, ti, to, "stress")
    fill2 = (1300 + 1.5 * s_in / 2) * (1 + 1.5 * 0.3e-4)
    out2 = (1300 - 1.5 * s_out / 2) * (1 - 1.5 * 0.3e-4)
    check("stress: spread and slippage x1.5, swap unchanged (rate x fill)",
          abs(rs["cost"] - (fill2 - out2 + 0.055 / 360 * fill2 * 3)) < 1e-9 and costs.round_trip(
              "xauusd", 1, 1300.0, 1300.0, ti, to, "gross")["cost"] == 0.0)
    # index, short, stop exit, held Friday -> Monday: swap_short 0 (credits ignored, no cost)
    ti, to = U("2019-06-14 15:00"), U("2019-06-17 15:00")
    s_in = 0.4 / 7377 * 2900 * SH["us500"][_how(ti)]
    s_out = 0.4 / 7377 * 2900 * SH["us500"][_how(to)]
    want = (2900 - s_in / 2) * (1 - 0.2e-4) - (2900 + s_out / 2) * (1 + 0.5e-4)
    r = costs.round_trip("us500", -1, 2900.0, 2900.0, ti, to, exit_kind="stop")
    check("us500 short: spread bp of 7377, market in 0.2 bp, stop out 0.5 bp, no swap on the short",
          abs(r["cost"] + want) < 1e-9 and r["swap"] == 0.0, f"{r['cost_bp']:.2f} bp")
    # FX and silver: the spread in bp of the fallback reference price, applied to the trade's price (the lab's model)
    e1 = costs.base_spread("eurusd", 1.10)
    e2 = costs.base_spread("eurusd", 1.39)
    j1 = costs.base_spread("usdjpy", 100.0)
    x1 = costs.base_spread("xagusd", 18.5)
    check("FX and silver spread = bp of the reference price, applied to the trade's price (lab model)",
          abs(e1 - 7.5e-5 / 1.16 * 1.10) < 1e-15 and abs(e2 - 7.5e-5 / 1.16 * 1.39) < 1e-15 and
          abs(j1 - 0.011 / 152.0 * 100.0) < 1e-15 and abs(x1 - 0.03 / 55.5 * 18.5) < 1e-15, f"{e1:.6g} {e2:.6g} {j1:.4g} {x1:.4g}")
    ti, to = U("2019-07-10 12:00"), U("2019-07-11 12:00")
    r = costs.round_trip("eurusd", 1, 1.12, 1.12, ti, to)
    sin, sout = 7.5e-5 / 1.16 * 1.12 * SH["eurusd"][_how(ti)], 7.5e-5 / 1.16 * 1.12 * SH["eurusd"][_how(to)]
    want = (1.12 + sin / 2) * 1.00001 - (1.12 - sout / 2) * 0.99999 + 0.02 / 360 * (1.12 + sin / 2) * 1.00001 * 3
    check("eurusd long over Wednesday: spread (bp of the reference price) x shape, 0.1 bp/side, swap 2 %/360 x 3",
          abs(r["cost"] - want) < 1e-12, f"{r['cost_bp']:.2f} bp")
    # crypto, long Thursday 12:00 NY -> Monday 12:00 NY: Thu 1 + Fri 3 (triple Fri) = 4 nights at 20 %/360
    ti, to = U("2019-06-13 16:00"), U("2019-06-17 16:00")
    n = costs.swap_nights(pd.DatetimeIndex([ti]), pd.DatetimeIndex([to]), "Fri")[0]
    r = costs.round_trip("btcusd", 1, 10000.0, 10000.0, ti, to)
    s_in = 22.5 / 76000 * 10000 * SH["btcusd"][_how(ti)]
    s_out = 22.5 / 76000 * 10000 * SH["btcusd"][_how(to)]
    fill = (10000 + s_in / 2) * (1 + 0.5e-4)
    want = fill - (10000 - s_out / 2) * (1 - 0.5e-4) + 0.2 / 360 * fill * 4
    check("btcusd long Thu -> Mon: 4 nights (Fri triple), 20 %/360, spread bp of 76000, slip 0.5 bp",
          n == 4 and abs(r["cost"] - want) < 1e-9, f"{r['cost_bp']:.2f} bp")
    # rollover = 17:00 New York, DST-correct
    f = lambda a, b: int(costs.swap_nights(pd.DatetimeIndex([U(a)]), pd.DatetimeIndex([U(b)]), "Wed")[0])  # noqa: E731
    check("rollover at 17:00 NY: 21:00 UTC in July, 22:00 UTC in January",
          f("2019-07-09 20:30", "2019-07-09 21:30") == 1 and f("2019-07-09 21:30", "2019-07-09 22:30") == 0 and
          f("2019-01-08 20:30", "2019-01-08 21:30") == 0 and f("2019-01-08 21:30", "2019-01-08 22:30") == 1 and
          f("2019-01-08 10:00", "2019-01-08 22:00") == 0 and f("2019-01-08 10:00", "2019-01-08 22:01") == 1,
          "an exit exactly at 17:00 NY holds no night (exit - 1 s, as lab/goldlab/sim.py)")
    try:
        costs.spec("wtiusd")
        check("a market without a cost entry raises", False)
    except costs.CostError:
        check("a market without a cost entry raises", True)


# ------------------------------------------------------------------ simulator mechanics
def flat(key, start="2019-05-01", end="2019-07-01", price=1.10, hr=0.001):
    t = synth.calendar(synth.KIND.get(key, "fx"), start, end)
    b = pd.DataFrame({"open": price, "high": price + hr, "low": price - hr, "close": price, "volume": 1.0}, index=t)
    return data.fp_hours(key, b)


def test_sim_mechanics():
    b = flat("eurusd")
    T = U("2019-06-12 10:00")                 # a Wednesday
    i = b.index.get_loc(T)
    s0 = 7.5e-5 / 1.16 * 1.10 * SH["eurusd"][_how(T)]
    fill = (1.10 + s0) * (1 + 1e-5)
    d20 = 0.002
    stop = fill - d20
    tgt = fill + 2 * d20
    sig = pd.DataFrame({"known_at": [T], "side": [1]})
    run = lambda bb, **kw: sim.simulate(sig, bb, market="eurusd", exit=kw.pop("exit", ("hours", 5)),  # noqa: E731
                                        stop=("d20", 1.0), **kw)
    b1 = b.copy()
    b1.iloc[i + 2, b1.columns.get_loc("low")] = stop - 0.0005
    b1.iloc[i + 2, b1.columns.get_loc("high")] = tgt + 0.0005
    t1 = run(b1, target=("d20", 2.0))
    check("entry at the open of the signal bar at the ask (+ slip), D20 from 20 completed days",
          abs(t1.entry_px[0] - fill) < 1e-12 and abs(t1.d20[0] - d20) < 1e-12)
    check("stop and target in the same bar: the stop, at the stop level minus stop slippage",
          t1.reason[0] == "stop" and abs(t1.exit_px[0] - stop * (1 - 0.3e-4)) < 1e-12 and
          t1.exit_time[0] == b.index[i + 2] + pd.Timedelta(hours=1))
    b2 = b.copy()
    b2.iloc[i + 2, b2.columns.get_loc("open")] = stop - 0.001
    b2.iloc[i + 2, b2.columns.get_loc("low")] = stop - 0.002
    t2 = run(b2)
    check("a bar opening beyond the stop fills at its open with stop slippage",
          t2.reason[0] == "stop_gap" and abs(t2.exit_px[0] - (stop - 0.001) * (1 - 0.3e-4)) < 1e-12)
    b3 = b.copy()
    b3.iloc[i + 3, b3.columns.get_loc("high")] = tgt + 0.0001
    t3 = run(b3, target=("d20", 2.0))
    check("target fills at the target, no slippage", t3.reason[0] == "target" and abs(t3.exit_px[0] - tgt) < 1e-12)
    t4 = run(b)
    x = b.index[i + 5]
    s5 = 7.5e-5 / 1.16 * 1.10 * SH["eurusd"][_how(x)]
    want_R = ((1.10 - 0 * s5) * (1 - 1e-5) - fill) / d20
    check("time exit at the open of the bar N hours later, at the bid (- slip); R = net / stop distance",
          t4.reason[0] == "time" and t4.exit_time[0] == x and abs(t4.R[0] - want_R) < 1e-9 and t4.swap_bp[0] == 0,
          f"R {t4.R[0]:.4f}")
    t5 = sim.simulate(pd.DataFrame({"known_at": [T + pd.Timedelta(seconds=1)], "side": [1]}), b, market="eurusd",
                      exit=("hours", 5), stop=("d20", 1.0))
    check("a signal known 1 s after a bar opens enters at the next bar", t5.entry_time[0] == T + pd.Timedelta(hours=1))
    two = pd.DataFrame({"known_at": [T, T + pd.Timedelta(hours=1)], "side": [1, -1]})
    t6 = sim.simulate(two, b, market="eurusd", exit=("hours", 5), stop=("d20", 1.0))
    t7 = sim.simulate(two, b, market="eurusd", exit=("hours", 5), stop=("d20", 1.0), mode="every")
    check("one position per market: the overlapping signal is skipped and counted; every-signal takes both",
          len(t6) == 1 and t6.attrs["counts"]["eurusd"]["overlap_skipped"] == 1 and len(t7) == 2)
    try:
        sim.simulate(sig, b, market="eurusd", exit=("hours", 5), stop=None)
        check("the protective stop is mandatory", False)
    except ValueError:
        check("the protective stop is mandatory", True)
    # DST: clock exit 16:00 New York
    bb = flat("eurusd", "2019-02-01", "2019-04-01")
    s = pd.DataFrame({"known_at": [U("2019-03-08 10:00"), U("2019-03-11 10:00")], "side": [1, 1]})
    t8 = sim.simulate(s, bb, market="eurusd", exit=("clock", "16:00", "America/New_York"), stop=("d20", 1.0), mode="every")
    check("clock exit 16:00 NY in the DST week: 21:00 UTC on Friday 8 March, 20:00 UTC on Monday 11 March",
          list(t8.exit_time) == [U("2019-03-08 21:00"), U("2019-03-11 20:00")], str(list(t8.exit_time)))
    t9 = sim.simulate(s.iloc[:1], bb, market="eurusd", exit=("bdays", 1), stop=("d20", 1.0))
    check("business-day exit: Friday + 1 business day = Monday, same clock", t9.exit_time[0] == U("2019-03-11 10:00"))
    # crypto weekend at FP
    c = flat("btcusd", "2019-05-01", "2019-07-01", price=8000.0, hr=50.0)
    srv = data.server_time(c.index)
    check("crypto: no bar inside FP's closure (Fri 23:55 - Mon 00:00 server)", not (srv.dayofweek >= 5).any())
    s = pd.DataFrame({"known_at": [U("2019-06-15 12:00"), U("2019-06-21 14:00")], "side": [1, 1]})
    t10 = sim.simulate(s, c, market="btcusd", exit=("hours", 24), stop=("d20", 1.0), mode="every")
    check("crypto: a Saturday signal enters at the reopening (Sunday 17:00 NY = 21:00 UTC in June)",
          t10.entry_time[0] == U("2019-06-16 21:00"), str(t10.entry_time[0]))
    check("crypto: a time exit inside the closure is done at the Friday close (end of the 16:00 NY bar)",
          t10.reason[1] == "time_close" and t10.exit_time[1] == U("2019-06-21 21:00"), str(t10.exit_time[1]))


# ------------------------------------------------------------------ look-ahead traps
def test_lookahead():
    b = synth.bars("us500", seed=3)
    h = b[b.index.hour == 14]
    side = np.sign(h.close - h.open).replace(0, 1).astype(int)

    def build_bad(d):
        x = d[d.index.hour == 14]
        return pd.DataFrame({"known_at": x.index, "side": np.sign(x.close - x.open).replace(0, 1).astype(int).to_numpy()})

    def build_good(d):
        x = d[d.index.hour == 14]
        return pd.DataFrame({"known_at": x.index + pd.Timedelta(hours=1),
                             "side": np.sign(x.close - x.open).replace(0, 1).astype(int).to_numpy()})
    bk = sim.Book(b, "us500")
    bad = sim.simulate(build_bad(b), {"us500": bk}, market=None, exit=("hours", 1), stop=("d20", 2.0)) \
        if False else sim.simulate(build_bad(b).assign(market="us500"), {"us500": bk}, exit=("hours", 1), stop=("d20", 2.0))
    good = sim.simulate(build_good(b).assign(market="us500"), {"us500": bk}, exit=("hours", 1), stop=("d20", 2.0))
    cuts = [U("2016-03-02 15:00"), U("2018-07-11 15:00"), U("2020-11-04 15:00")]
    tb = checks.truncation_test(build_bad, b, cuts)
    tg = checks.truncation_test(build_good, b, cuts)
    tb0 = checks.truncation_test(build_bad, b, cuts, n_signal_cuts=0, n_random_cuts=0)   # the given cuts only
    check("trap 1, a signal stamped at its bar's open using that bar's close: the truncation test catches it",
          not tb["pass"] and tg["pass"], f"(cuts at bar ends only would miss it: {tb0['pass']}) bad PF {stats.pf(bad.R):.2f} (the trap is real), good PF {stats.pf(good.R):.2f}")
    check("trap 1, stamped at the bar's end (the kit's rule) it cannot be exploited",
          abs(stats.t_stat(good.R_gross)) < 3.5 and stats.t_stat(bad.R_gross) > 20,
          f"t gross good {stats.t_stat(good.R_gross):.2f}, bad {stats.t_stat(bad.R_gross):.1f}")
    # trap 2: an external value equal to the next 24 h move, published 25 h after its observation
    d = data.daily_bars(b, "utc")
    fut = np.sign(d.close.shift(-1) - d.close).dropna()
    obs = fut.index
    pub = pd.Series(fut.to_numpy(), index=data.known_at(obs, lag_days=1, time="01:00", tz="UTC") + pd.Timedelta(days=1))
    times = (obs + pd.Timedelta(days=1)).tz_localize("UTC")          # the signal is taken at midnight UTC after day D
    use = data.asof_join(times, pub)
    ok = np.isfinite(use)
    sg = pd.DataFrame({"known_at": times[ok], "side": use[ok].astype(int), "market": "us500"})
    ex = sim.simulate(sg, {"us500": bk}, exit=("hours", 24), stop=("d20", 3.0))
    wrong = pd.DataFrame({"known_at": times, "side": fut.to_numpy().astype(int), "market": "us500"})
    exw = sim.simulate(wrong, {"us500": bk}, exit=("hours", 24), stop=("d20", 3.0))
    check("trap 2, a value used before it is known: through known-at + asof_join there is no edge",
          abs(stats.t_stat(ex.R_gross)) < 3.5 and stats.t_stat(exw.R_gross) > 10,
          f"t gross kit {stats.t_stat(ex.R_gross):.2f}; if indexed by observation date {stats.t_stat(exw.R_gross):.1f}")
    td = checks.truncation_test(lambda dd: pd.DataFrame({"known_at": times, "side": np.nan_to_num(
        data.asof_join(times, dd)).astype(int)}), pub, [U("2017-05-05"), U("2020-02-02")], row_len=pd.Timedelta(0))
    check("trap 3, a value published late: the truncation test on the known-at series passes for the kit's join",
          td["pass"])
    d1 = pd.DataFrame({"known_at": [U("2019-06-12 10:00")], "side": [1]})
    sh = checks.shift_test(d1.assign(market="us500"), {"us500": bk}, exit=("hours", 5), stop=("d20", 1.0))
    check("shift_test reports the same signals one bar later", sh["shifted"]["n"] == 1 and "PF" in sh["base"])


# ------------------------------------------------------------------ planted edge, noise, null, DSR, correlation
def _tr_fixed(sig):
    """Truncation report of a signal table given as data (synthetic worlds: the signals ARE the data, indexed by their
    known_at, so the test is genuine and binds the report to these signals)."""
    d = pd.DataFrame({"side": sig.side.to_numpy()}, index=pd.DatetimeIndex(sig.known_at))
    return checks.truncation_test(lambda x: pd.DataFrame({"known_at": x.index, "side": x.side.to_numpy()}), d,
                                  row_len=pd.Timedelta(0))


def judge_one(bars_key, b, sig, hold=5, n_draws=2000, neighbours_h=(4, 6), write_dir=None, seed=0):
    bk = {bars_key: sim.Book(b, bars_key)}
    rule = dict(exit=("hours", hold), stop=("d20", 1.5))
    main = sim.simulate(sig, bk, **rule)
    nb = {f"h{h}": sim.simulate(sig, bk, exit=("hours", h), stop=("d20", 1.5)) for h in neighbours_h}
    ev = sim.simulate(sig, bk, mode="every", **rule)
    nl = stats.null_test(main, bk, n_draws=n_draws, seed=seed, **rule)
    return judge.verdict(write_dir or TMP, main, nb, ev, nl, corr="compute", ten=TEN, write=write_dir is not None,
                         data_desc="synthetic", truncation=_tr_fixed(sig)), main, nl


def test_planted_and_noise():
    t0 = time.time()
    b, sig = synth.signal_world("us500", seed=5, edge=0.0004)
    idea = os.path.join(TMP, "ideas", "901_planted")
    _declare(idea, {"idea": "901 planted"})
    res, main, nl = judge_one("us500", b, sig, write_dir=idea)
    NUMBERS["planted"] = {k: res["bars"][k]["value"] for k in res["bars"]}
    NUMBERS["planted"]["dsr_N_all"] = res["selection"]["dsr_N_all"]["dsr"]
    check("planted edge is found: every bar passes, deflated probability >= 0.95",
          res["verdict"] == "pass", f"{res['verdict']} {res['failed_bars']}; {res['ledger_line'][-150:]}")
    lines = open(os.path.join(idea, "trials.jsonl")).read().splitlines()
    check("judge writes results.json and appends one trials.jsonl line per configuration",
          os.path.exists(os.path.join(idea, "results.json")) and len(lines) == 3 and res["ledger_line"].startswith("| 901 |"))
    # 200 noise rules through the full judge
    rng = np.random.default_rng(11)
    keys = list(costs.SPEC)
    tn, tg, pct, verdicts = [], [], [], []
    for w in range(20):
        key = keys[w % len(keys)]
        bw = synth.bars(key, seed=100 + w)
        bk = sim.Book(bw, key)
        days = pd.bdate_range("2013-03-01", "2021-12-20", tz="UTC")
        for r in range(10):
            hr = int(rng.integers(0, 24))
            pick = days[rng.random(len(days)) < 0.15] + pd.Timedelta(hours=hr)
            sg = pd.DataFrame({"known_at": pick, "side": rng.choice([-1, 1], len(pick)), "market": key})
            hold = int(rng.choice([3, 6, 12, 24]))
            rule = dict(exit=("hours", hold), stop=("d20", 1.0))
            m = sim.simulate(sg, {key: bk}, **rule)
            nb = {"a": sim.simulate(sg, {key: bk}, exit=("hours", hold * 2), stop=("d20", 1.0)),
                  "b": sim.simulate(sg, {key: bk}, exit=("hours", hold), stop=("d20", 2.0))}
            ev = sim.simulate(sg, {key: bk}, mode="every", **rule)
            nl = stats.null_test(m, {key: bk}, n_draws=2000, seed=w * 10 + r, **rule)
            res = judge.verdict(TMP, m, nb, ev, nl, ten=TEN, write=False)
            tn.append(stats.t_stat(m.R)); tg.append(stats.t_stat(m.R_gross)); pct.append(nl["percentile"])
            core = [f for f in res["failed_bars"] if f not in GUARDS]   # the guards are not given here: judge the rest
            verdicts.append("fail" if core else "pass on every non-guard bar")
    tg, tn, pct = np.array(tg), np.array(tn), np.array(pct)
    npass = sum(v != "fail" for v in verdicts)
    NUMBERS["noise"] = {"rules": len(verdicts), "passed": npass, "t_gross_mean": float(tg.mean()), "t_gross_sd": float(tg.std()),
                        "t_net_mean": float(tn.mean()), "ks_normal_p": float(st.kstest(tg, "norm").pvalue),
                        "null_pct_ks_uniform_p": float(st.kstest(pct / 100, "uniform").pvalue),
                        "null_pct_ge_97.5": int((pct >= 97.5).sum()), "seconds": round(time.time() - t0, 1)}
    check("200 noise rules through the full judge: none passes", npass == 0, json.dumps(NUMBERS["noise"]))
    check("noise: t (gross) looks standard normal", abs(tg.mean()) < 0.25 and 0.8 < tg.std() < 1.25 and
          NUMBERS["noise"]["ks_normal_p"] > 0.001)
    check("null calibration: a noise rule's percentile is uniform (KS) and >= 97.5 in about 2.5 % of rules",
          NUMBERS["noise"]["null_pct_ks_uniform_p"] > 0.001 and (pct >= 97.5).sum() <= 12)


def test_long_drift_guard():
    """A long-only rule on a rising market: PF bars pass from drift alone, the side-keeping null does not."""
    b = synth.bars("us100", seed=21, drift_h=0.00012)
    days = pd.bdate_range("2013-03-01", "2021-12-20", tz="UTC")
    sg = pd.DataFrame({"known_at": days + pd.Timedelta(hours=15), "side": 1, "market": "us100"})
    bk = {"us100": sim.Book(b, "us100")}
    rule = dict(exit=("hours", 20), stop=("d20", 2.0))
    m = sim.simulate(sg, bk, **rule)
    nl = stats.null_test(m, bk, n_draws=2000, **rule)
    check("long-only on drift: PF high but the null (same side) is not beaten", stats.pf(m.R) > 1.12 and nl["percentile"] < 97.5,
          f"PF {stats.pf(m.R):.2f}, null percentile {nl['percentile']:.1f}")


def test_basket_and_lock_in_sim():
    b1, s1 = synth.signal_world("us500", seed=31, edge=0.0003)
    b2, s2 = synth.signal_world("ger40", seed=32, edge=0.0003)
    bk = sim.books({"us500": b1, "ger40": b2})
    sig = pd.concat([s1, s2], ignore_index=True)
    rule = dict(exit=("hours", 5), stop=("d20", 1.5))
    m = sim.simulate(sig, bk, **rule)
    idea = os.path.join(TMP, "ideas", "904_basket")
    _declare(idea, {"idea": "904 basket"})
    res = judge.verdict(idea, m, {"h4": sim.simulate(sig, bk, exit=("hours", 4), stop=("d20", 1.5))},
                        sim.simulate(sig, bk, mode="every", **rule), stats.null_test(m, bk, **rule), ten=TEN, write=False,
                        truncation=_tr_fixed(sig))
    check("basket of 2: t on daily sums, small-basket share bar 75 %, markets positive, pass",
          res["basket"] and "t_daily>=2.5" in res["bars"] and "max_market_share<=75%" in res["bars"] and
          "n>=250" not in res["bars"] and res["verdict"] == "pass", f"{res['verdict']} {res['failed_bars']}")
    late = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0},
                        index=pd.date_range("2021-12-31 20:00", periods=6, freq="h", tz="UTC"))
    try:
        sim.Book(late, "eurusd")
        check("the simulator refuses bars past the period lock", False)
    except data.PeriodError:
        check("the simulator refuses bars past the period lock", True)


def test_dsr_monte_carlo():
    rng = np.random.default_rng(7)
    res = {}
    for N in (1, 50, 500):
        hits, ratio = 0, []
        W = 300 if N < 500 else 120
        for w in range(W):
            x = np.where(rng.random((N, 300)) < 0.62, -1.0, rng.exponential(1 / 0.38 * 0.62, (N, 300)))
            x = x - (0.62 * -1 + 0.38 * 0.62 / 0.38)          # zero mean, skewed (stop-like) trade results
            srs = x.mean(1) / x.std(1, ddof=1)
            best = x[int(np.argmax(srs))]
            d = stats.deflated_sharpe(best, N)
            hits += d["dsr"] >= 0.95
            ratio.append(srs.max() / d["sr0"] if N > 1 else 0)
        res[N] = {"worlds": W, "share_dsr>=0.95": hits / W, "mean_maxSR_over_SR0": float(np.mean(ratio))}
    NUMBERS["dsr_mc"] = res
    check("deflated Sharpe vs Monte Carlo of pure-noise rules: the best of N reaches 0.95 in <= ~7 % of worlds",
          all(v["share_dsr>=0.95"] <= 0.08 for v in res.values()) and res[1]["share_dsr>=0.95"] > 0.01, json.dumps(res))


def test_correlation_fixture():
    rng = np.random.default_rng(2)
    e = pd.DatetimeIndex(np.sort(rng.choice(pd.date_range("2014-01-01", "2021-12-30", freq="h", tz="UTC"), 300, replace=False)))
    main = pd.DataFrame({"entry_time": e, "exit_time": e + pd.Timedelta(hours=10), "R": rng.standard_normal(300)})
    rho = stats.corr_with_ten(main, ten=stats.ten_trades(TEN_DIR))
    # independent: weeks Monday..Sunday from the Monday of the week of 2014-01-01, 418 weeks; the ten read by hand
    mon0 = pd.Timestamp("2013-12-30")

    def wk(t):
        x = t[(t.exit_time < U("2022-01-01"))]
        k = ((x.exit_time.dt.tz_convert(None) - mon0).dt.days // 7).to_numpy()
        out = np.zeros(418)
        m = (k >= 0) & (k < 418)
        np.add.at(out, k[m], x.R.to_numpy()[m])
        return out
    tot = np.zeros(418)
    n_read = 0
    for n, s in stats.TEN:
        t = pd.read_parquet(os.path.join(TEN_DIR, f"{n}__{s}.parquet"))
        t = t[t.entry_time < U("2022-01-01")]
        n_read += len(t)
        tot += wk(t)
    want = float(np.corrcoef(wk(main), tot)[0, 1])
    sun = stats.weekly(pd.DataFrame({"exit_time": [U("2014-01-05 23:00"), U("2014-01-06 00:30")], "R": [1.0, 2.0]}))
    check("weekly correlation convention (W-SUN exit weeks, 418 weeks, ten read with entry < 2022, 2022 exits dropped)",
          abs(rho - want) < 1e-12 and sun.iloc[0] == 1.0 and sun.iloc[1] == 2.0 and len(stats.WEEKS) == 418,
          f"rho {rho:.4f}")


def test_hash_ledger_speed():
    d = os.path.join(TMP, "ideas", "902_h")
    os.makedirs(d)
    open(os.path.join(d, "declared.json"), "w").write('{"a": 1}')
    import hashlib
    open(os.path.join(d, "declared.sha256"), "w").write(hashlib.sha256(b'{"a": 1}').hexdigest() + "  declared.json\n")
    ok1 = checks.declared_hash(d)
    open(os.path.join(d, "declared.json"), "w").write('{"a": 2}')
    try:
        checks.declared_hash(d)
        ok2 = False
    except AssertionError:
        ok2 = True
    check("declared_hash: matches, then detects a changed declaration", bool(ok1) and ok2)
    led = os.path.join(TMP, "LEDGER.md")
    shutil.copy(judge.LEDGER, led)
    t0, i0 = judge.ledger_total(led), judge.ideas_read(led)
    new = judge.ledger_add(11, "| 903 | 2026-11-17 | x | us500 | s | 11 | fermee | n 1 |", led)
    check("ledger helpers: read and update the running total, count ideas with a read verdict",
          new == t0 + 11 and judge.ledger_total(led) == t0 + 11 and judge.ideas_read(led) == i0 + 1, f"{t0} -> {new}")
    # speed: 10 configurations x 16 markets x 9 years
    bks = {k: sim.Book(synth.bars(k, seed=i), k) for i, k in enumerate(costs.SPEC)}
    rng = np.random.default_rng(0)
    sigs = []
    for k, bk in bks.items():
        ka = bk.index[rng.choice(len(bk.index) - 300, 1500, replace=False)]
        sigs.append(pd.DataFrame({"known_at": ka, "side": rng.choice([-1, 1], 1500), "market": k}))
    sg = pd.concat(sigs, ignore_index=True)
    t0 = time.time()
    n = 0
    for h in (2, 4, 6, 8, 12, 24, 48, 72, 96, 120):
        n += len(sim.simulate(sg, bks, exit=("hours", h), stop=("d20", 1.0), target=("d20", 2.0)))
    dt = time.time() - t0
    NUMBERS["speed_10cfg_16mk_9y_s"] = round(dt, 1)
    check("speed: 10 configurations x 16 markets x 9 years (24,000 signals each)", dt < 60, f"{dt:.1f} s, {n} trades")


def test_net():
    """One month (or year) of each source, each reported on its own: a source down does not hide the others."""
    os.environ["EXPLORE_CACHE"] = os.path.join(TMP, "netcache")
    data.lock()

    def one(name, fn):
        try:
            fn()
        except Exception as e:      # a source unreachable from here is reported, the other sources still run
            check(f"net: {name} reachable", False, repr(e))

    def _eur():
        d = data._duka_month("EURUSD", 2019, 6, "BID")
        a = data._duka_month("EURUSD", 2019, 6, "ASK")
        d = d[d.volume > 0]
        check("net: Dukascopy EURUSD 2019-06 BID decoded (hourly, prices ~1.12, ask > bid)",
              len(d) > 400 and 1.10 < d.close.median() < 1.15 and (a.reindex(d.index).close > d.close).mean() > 0.99
              and (d.high >= d[["open", "close"]].max(axis=1)).all(), f"{len(d)} bars, median {d.close.median():.5f}")

    def _xau():
        x = data.duka_h1("XAUUSD", 2019, end_year=2019)
        check("net: Dukascopy XAUUSD 2019 point size", 1200 < x.close.median() < 1600, f"median {x.close.median():.2f}")

    def _bn():
        k = data.binance_klines("BTCUSDT", "1h", start="2019-06", end="2019-06-30")
        check("net: Binance BTCUSDT 1h 2019-06 (720 bars, taker-buy columns)", len(k) >= 700 and
              (k.taker_buy_base <= k.volume + 1e-9).all() and 5000 < k.close.median() < 14000, f"{len(k)} bars")
        f = data.binance_funding("BTCUSDT", start="2020-01", end="2020-01-31")
        check("net: Binance funding 2020-01 (3 a day)", 80 <= len(f) <= 100 and f.abs().max() < 0.01, f"{len(f)} rows")

    def _fred():
        fr = data.fred("DGS10", known=data.rule_next_bday_utc(13, 1), start="2019-01-01", end="2019-12-31")
        check("net: FRED DGS10 2019 indexed by known time", 240 < len(fr) < 260 and fr.index.max() < U("2020-01-03"),
              f"{len(fr)} rows")

    def _yahoo():
        y = data.yahoo_daily("^GSPC", known=data.rule_local_close(), start="2019-06-01", end="2019-07-01")
        check("net: Yahoo ^GSPC 2019-06 known at the close", 18 <= len(y) <= 22 and 2700 < y.median() < 3100 and
              set(y.index.hour) <= {20}, f"{len(y)} rows")
    for name, fn in (("Dukascopy EURUSD", _eur), ("Dukascopy XAUUSD", _xau), ("Binance", _bn), ("FRED", _fred),
                     ("Yahoo", _yahoo)):
        one(name, fn)


# ------------------------------------------------------------------ review 1 (verifier issues V1-V9): written before the fixes
GUARDS = ("truncation_test", "declared_hash")


def _declare(folder, decl):
    import hashlib
    os.makedirs(folder, exist_ok=True)
    raw = json.dumps(decl, indent=1).encode()
    open(os.path.join(folder, "declared.json"), "wb").write(raw)
    open(os.path.join(folder, "declared.sha256"), "w").write(hashlib.sha256(raw).hexdigest() + "  declared.json\n")


def _planted_world():
    b, sig0 = synth.signal_world("us500", seed=5, edge=0.0004)
    value = pd.Series(sig0.side.to_numpy(), index=pd.DatetimeIndex(sig0.known_at))

    def build(d):
        days = pd.bdate_range("2013-02-01", "2021-12-20", tz="UTC") + pd.Timedelta(hours=14)
        x = data.asof_join(days, d["value"])
        ok = np.isfinite(x) & (x != 0)
        return pd.DataFrame({"known_at": days[ok], "side": np.sign(x[ok]).astype(int)})
    return b, value, build


def test_review_v1_same_bar():
    """V1: among signals entering at the same bar, mode 'one' must not keep the one that exits first."""
    b = synth.bars("us500", seed=41)
    bk = sim.books({"us500": b})
    rng = np.random.default_rng(41)
    days = pd.bdate_range("2013-02-01", "2021-12-24", tz="UTC") + pd.Timedelta(hours=14)
    s1 = rng.choice([-1, 1], len(days))
    pair = pd.concat([pd.DataFrame({"known_at": days, "side": s1}),
                      pd.DataFrame({"known_at": days, "side": -s1})], ignore_index=True).assign(market="us500")
    t = sim.simulate(pair, bk, exit=("hours", 29), stop=("d20", 2.0), target=("d20", 0.5))
    first = pd.Series(s1, index=days)
    kept_first = (t.side.to_numpy() == first.reindex(pd.DatetimeIndex(t.known_at)).to_numpy()).all()
    cnt = t.attrs["counts"]["us500"]
    check("V1: two opposite signals on one bar, target nearer than the stop: the first row is kept, not the winner",
          kept_first and abs(stats.t_stat(t.R_gross)) < 3.5 and cnt.get("same_bar_skipped", -1) == len(t),
          f"t gross {stats.t_stat(t.R_gross):.2f}, mean R {t.R.mean():.3f}, same_bar_skipped {cnt.get('same_bar_skipped')}")
    ts = []
    for w in range(4):
        bw = synth.bars("us500", seed=50 + w)
        r = np.random.default_rng(50 + w)
        d7 = pd.date_range("2013-02-01", "2021-12-24", freq="D", tz="UTC") + pd.Timedelta(hours=21)
        sg = pd.DataFrame({"known_at": d7, "side": r.choice([-1, 1], len(d7)), "market": "us500"})
        tt = sim.simulate(sg, sim.books({"us500": bw}), exit=("hours", 29), stop=("d20", 2.0), target=("d20", 0.5))
        ts.append(stats.t_stat(tt.R_gross))
    check("V1: a 7-day daily random signal (weekend signals share the Sunday open) has no edge in mode 'one'",
          abs(np.mean(ts)) < 1.5 and max(abs(x) for x in ts) < 3.5, f"t gross by world {np.round(ts, 2).tolist()}")


def test_review_v2_null_dense():
    """V2: the null must be calibrated for dense daily +/-1 signals whose trades overlap."""
    rng = np.random.default_rng(12)
    keys = ["us500", "eurusd", "xauusd", "us100", "gbpusd"]
    pe, po = [], []
    for w in range(10):
        key = keys[w % len(keys)]
        bk = {key: sim.Book(synth.bars(key, seed=200 + w), key)}
        days = pd.bdate_range("2013-03-01", "2021-12-20", tz="UTC")
        for r in range(10):
            sg = pd.DataFrame({"known_at": days + pd.Timedelta(hours=int(rng.integers(0, 24))),
                               "side": rng.choice([-1, 1], len(days)), "market": key})
            rule = dict(exit=("hours", int(rng.choice([29, 48]))), stop=("d20", 1.0))
            m = sim.simulate(sg, bk, **rule)
            pe.append(stats.null_test(m, bk, n_draws=1000, seed=w * 10 + r, **rule)["percentile"])
            if r < 4:
                po.append(stats.null_test(m, bk, n_draws=1000, seed=w * 10 + r, mode="one", **rule)["percentile"])
    pe, po = np.array(pe), np.array(po)
    NUMBERS["null_dense"] = {"rules": len(pe), "ge97.5_default": int((pe >= 97.5).sum()), "mean_default": float(pe.mean()),
                             "ks_p_default": float(st.kstest(pe / 100, "uniform").pvalue), "rules_one": len(po),
                             "ge97.5_one": int((po >= 97.5).sum()), "mean_one": float(po.mean()),
                             "ks_p_one": float(st.kstest(po / 100, "uniform").pvalue)}
    check("V2: null calibration with dense overlapping signals (default null): about 2.5 % reach 97.5, uniform",
          (pe >= 97.5).sum() <= 7 and NUMBERS["null_dense"]["ks_p_default"] > 0.001 and 35 < pe.mean() < 65,
          json.dumps(NUMBERS["null_dense"]))
    check("V2: the same with the one-position null (ties at random, never by exit)",
          (po >= 97.5).sum() <= 4 and NUMBERS["null_dense"]["ks_p_one"] > 0.001 and 35 < po.mean() < 65)


def test_review_v3_v9_guards_in_judge():
    """V3: the judge requires a passing truncation report bound to the main signals and a matching declaration hash.
    V9: more than 11 configurations fails; years without a trade count as not positive."""
    b, value, build = _planted_world()
    data_ = {"bars": b, "value": value}
    try:
        checks.truncation_test(build, data_, row_len={"bars": pd.Timedelta(hours=1)})
        check("V3: truncation_test refuses a data item without its row_len", False)
    except ValueError:
        check("V3: truncation_test refuses a data item without its row_len", True)
    tr = checks.truncation_test(build, data_, row_len={"bars": pd.Timedelta(hours=1), "value": pd.Timedelta(0)})
    sig = build(data_).assign(market="us500")
    bk = sim.books({"us500": b})
    rule = dict(exit=("hours", 5), stop=("d20", 1.5))
    main = sim.simulate(sig, bk, **rule)
    nb = {"h4": sim.simulate(sig, bk, exit=("hours", 4), stop=("d20", 1.5))}
    ev = sim.simulate(sig, bk, mode="every", **rule)
    nl = stats.null_test(main, bk, n_draws=2000, **rule)
    idea = os.path.join(TMP, "ideas", "905_guards")
    _declare(idea, {"idea": "905 guards"})
    kw = dict(corr="compute", ten=TEN, write=False)
    ok = judge.verdict(idea, main, nb, ev, nl, truncation=tr, **kw)
    no_tr = judge.verdict(idea, main, nb, ev, nl, **kw)
    other = checks.truncation_test(lambda d: build(d).iloc[::2].reset_index(drop=True), data_,
                                   row_len={"bars": pd.Timedelta(hours=1), "value": pd.Timedelta(0)})
    wrong_tr = judge.verdict(idea, main, nb, ev, nl, truncation=other, **kw)
    bare = os.path.join(TMP, "ideas", "906_nodecl")
    os.makedirs(bare, exist_ok=True)
    no_decl = judge.verdict(bare, main, nb, ev, nl, truncation=tr, **kw)
    check("V3: verdict 'pass' needs the truncation report of the main signals and the declaration hash",
          ok["verdict"] == "pass" and no_tr["verdict"] == "fail" and "truncation_test" in no_tr["failed_bars"] and
          wrong_tr["verdict"] == "fail" and no_decl["verdict"] == "fail" and "declared_hash" in no_decl["failed_bars"],
          f"{ok['verdict']} / {no_tr['failed_bars']} / {wrong_tr['failed_bars']} / {no_decl['failed_bars']}")
    many = judge.verdict(idea, main, nb, ev, nl, truncation=tr, n_configs=12, **kw)
    check("V9: more than 11 configurations fails the verdict", many["verdict"] == "fail" and
          any(k.startswith("configs") for k in many["failed_bars"]), str(many["failed_bars"]))
    yrs = pd.DatetimeIndex(main.entry_time).year
    gap = main[(yrs != 2015) & (yrs != 2016)].reset_index(drop=True)
    gap.attrs.update(main.attrs)
    g = judge.verdict(idea, gap, nb, ev, nl, truncation=tr, **kw)
    check("V9: 'years positive' counts every year from the first trade to 2021 (a year without a trade is not positive)",
          abs(g["bars"]["years>=60%"]["value"] - 7 / 9) < 1e-9, str(g["bars"]["years>=60%"]))
    sz = ok.get("sizing") or {}
    check("V5: the verdict reports the minimum-lot sizing figures and says the sizing bar is not judged",
          sz.get("judged") is False and sz.get("min_lot_margin_eur", 0) > 0 and sz.get("min_lot_loss_at_median_stop_eur", 0) > 0
          and "sizing" in ok["ledger_line"], json.dumps(sz))


def test_review_v4_external():
    """V4: an external series must say when each observation is published; non-daily FRED series need a lag and an
    explicit acceptance of revised (current-vintage) values."""
    real = data.http_get

    def monthly(url, **kw):
        d = pd.date_range("2015-01-01", "2023-01-01", freq="MS")
        return ("observation_date,M\n" + "\n".join(f"{x.date()},{i}" for i, x in enumerate(d))).encode()
    data.http_get = monthly
    os.environ["EXPLORE_CACHE"] = os.path.join(TMP, "cache_v4")
    try:
        data.lock()
        try:
            data.fred("MONTHLY1", known=data.rule_next_bday_utc(13, 1))
            a = False
        except ValueError:
            a = True
        try:
            data.fred("MONTHLY2", known=data.rule_next_bday_utc(13, 1), min_lag=pd.Timedelta(days=40), revised_ok=True)
            b_ = False
        except ValueError:
            b_ = True
        s = data.fred("MONTHLY3", known=lambda d: data.known_at(d, lag_days=45, time="12:30", tz=data.NY),
                      min_lag=pd.Timedelta(days=40), revised_ok=True)
        c = len(s) > 50 and s.index.max() < U("2022-01-01") and "obs_date" in s.attrs and s.attrs["obs_date"] is not None
        check("V4: a monthly FRED series with a daily known-at rule is refused; the declared lag is enforced",
              a and b_ and c, f"last known {s.index.max()}")
    finally:
        data.http_get = real
    obs = pd.bdate_range("2016-01-01", "2016-03-31")
    try:
        data.external(obs, np.arange(len(obs)), known=data.rule_next_bday_utc(13, 1))
        e1 = False
    except (ValueError, TypeError):
        e1 = True
    try:
        data.external(obs, np.arange(len(obs)), known=data.rule_next_bday_utc(13, 0), min_lag=pd.Timedelta(days=1))
        e2 = False
    except ValueError:
        e2 = True
    x = data.external(obs, np.arange(len(obs)), known=data.rule_next_bday_utc(13, 1), min_lag=pd.Timedelta(hours=12))
    check("V4: data.external needs a publication lag, enforces it and keeps the observation dates",
          e1 and e2 and len(x) == len(obs) and len(x.attrs["obs_date"]) == len(x))


def test_review_v5_val_judge():
    def tt(rows):
        t = pd.DataFrame(rows, columns=["entry_time", "R"])
        t["entry_time"] = pd.to_datetime(t.entry_time, utc=True)
        t["exit_time"] = t.entry_time + pd.Timedelta(hours=5)
        t["market"] = "us500"
        return t
    good = tt([("2022-03-01", 1.0), ("2022-04-01", -0.5), ("2023-03-01", 0.8), ("2024-05-01", 0.3), ("2024-06-01", -0.1)])
    idea = os.path.join(TMP, "ideas", "907_val")
    os.makedirs(idea, exist_ok=True)
    json.dump(VALDECL, open(os.path.join(idea, "val_declared.json"), "w"))
    try:
        r = judge.val_verdict(idea, good, good)
        bad = judge.val_verdict(idea, good[good.entry_time.dt.year != 2024], good, write=False)
        ok = (r["verdict"] == "pass" and set(r["bars"]) >= {"PF>=1.06", "exp>0", "every_signal_exp>0", "years>=3/4"} and
              os.path.exists(os.path.join(idea, "val_results.json")) and bad["verdict"] == "fail")
        try:
            judge.val_verdict(idea, tt([("2021-12-30", 1.0)]), good, write=False)
            ok = False
        except ValueError:
            pass
        check("V5: judge.val_verdict applies the 4 VAL bars (a year without a trade is not positive), writes val_results.json",
              ok, f"{r['verdict']} {r['bars'].get('years>=3/4')}; without 2024: {bad['verdict']}")
    except AttributeError as e:
        check("V5: judge.val_verdict applies the 4 VAL bars", False, repr(e))


def test_review_v6_synth_fair():
    """V6: on synthetic bars, gross R must be zero-mean for any stop or target (a wick belongs to the path: a price that
    touched a stop inside a bar does not come back for free)."""
    out = {}
    for name, stop, tgt in (("tight stop 0.3 D20", ("d20", 0.3), None), ("target 0.3 / stop 1 D20", ("d20", 1.0), ("d20", 0.3))):
        Rs = []
        for w in range(12):
            key = ["us500", "eurusd", "xauusd"][w % 3]
            bk = {key: sim.Book(synth.bars(key, seed=700 + w), key)}
            rng = np.random.default_rng(w)
            days = pd.bdate_range("2013-03-01", "2021-12-20", tz="UTC") + pd.Timedelta(hours=int(rng.integers(0, 24)))
            sg = pd.DataFrame({"known_at": days, "side": rng.choice([-1, 1], len(days)), "market": key})
            Rs.append(sim.simulate(sg, bk, exit=("hours", 23), stop=stop, target=tgt).R_gross.to_numpy())
        R = np.concatenate(Rs)
        out[name] = {"n": int(len(R)), "mean_R_gross": round(float(R.mean()), 4), "t": round(stats.t_stat(R), 2)}
    NUMBERS["synth_fair"] = out
    check("V6: synthetic bars are a fair game for stops and targets (pooled gross t of 12 worlds within +/-3.5)",
          all(abs(v["t"]) < 3.5 for v in out.values()), json.dumps(out))


def test_review_v7_budget():
    real = data.http_get
    calls = []
    h1_env = os.environ.pop("EXPLORE_H1_DIR", None)   # kit v2.1 fix 2 (KF-6): the prefetch part tests the download path
    try:
        data.set_deadline(-1)
        try:
            data.http_get("https://datafeed.dukascopy.com/x")
            a = False
        except data.BudgetExceeded:
            a = True
        data.http_get = lambda url, **kw: (calls.append(url), _fake(url))[1]
        os.environ["EXPLORE_CACHE"] = os.path.join(TMP, "cache_v7")
        data.set_deadline(None)
        rep = data.prefetch(["eurusd"], start_year=2021)
        data.set_deadline(-1)
        data.http_get = real
        rep2 = data.prefetch(["usdjpy"], start_year=2021)
        check("V7: a download deadline stops cleanly; prefetch reports each market",
              a and rep["eurusd"]["status"] == "ok" and rep["eurusd"]["files"] == 12 and
              rep2["usdjpy"]["status"].startswith("stopped") and data.HTTP_TRIES <= 4 and
              "Mozilla" not in data.user_agent("https://fred.stlouisfed.org/graph/fredgraph.csv"),
              f"{rep} {rep2}")
    except AttributeError as e:
        check("V7: a download deadline stops cleanly; prefetch reports each market", False, repr(e))
    finally:
        data.http_get = real
        if hasattr(data, "set_deadline"):
            data.set_deadline(None)
        if h1_env is not None:
            os.environ["EXPLORE_H1_DIR"] = h1_env


def test_review_v8_template():
    import importlib.util
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template", "run_template.py")
    spec = importlib.util.spec_from_file_location("run_template_t", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    folder = os.path.join(TMP, "ideas", "908_nodecl")
    os.makedirs(folder, exist_ok=True)
    try:
        mod.one_idea(folder, edge=0.0, seed=1, ten=TEN)
        ok = False
    except FileNotFoundError:
        ok = not os.path.exists(os.path.join(folder, "declared.json"))
    except Exception as e:
        ok = False
        print("   template raised", repr(e)[:200])
    check("V8: the template reads the committed declared.json and never writes it", ok)


def test_review_v9_unlock():
    idea = os.path.join(TMP, "ideas", "909_v")
    os.makedirs(idea, exist_ok=True)
    res = []
    for decl, verdict in (({}, "pass"), (dict(VALDECL, cut="2026-06-30"), "pass"), (VALDECL, "fail"),
                          (VALDECL, None)):
        json.dump(decl, open(os.path.join(idea, "val_declared.json"), "w"))
        if verdict is None:
            if os.path.exists(os.path.join(idea, "results.json")):
                os.remove(os.path.join(idea, "results.json"))
        else:
            json.dump({"verdict": verdict}, open(os.path.join(idea, "results.json"), "w"))
        try:
            data.unlock_val(idea)
            res.append(False)
        except data.PeriodError:
            res.append(True)
        finally:
            data.lock()
    check("V9: unlock_val refuses an empty val_declared.json, a cut other than 2025-12-31, a failed idea, no results.json",
          all(res), str(res))
    json.dump(VALDECL, open(os.path.join(idea, "val_declared.json"), "w"))
    json.dump({"verdict": "pass, weak against selection"}, open(os.path.join(idea, "results.json"), "w"))
    try:
        data.unlock_val(idea)
        weak_ok = data.period_end() == data.VAL_END
    except data.PeriodError:
        weak_ok = False
    finally:
        data.lock()
    check("L1: a 'pass, weak against selection' may take its validation look (charter amendment of 2026-11-18)", weak_ok)


def test_lead_v11():
    """Lead's review (2026-11-18): signed correlation bar, prepared hourly bars, hole guard, nothing past the period end
    in the FRED / Yahoo cache."""
    b, value, build = _planted_world()
    data_ = {"bars": b, "value": value}
    tr = checks.truncation_test(build, data_, row_len={"bars": pd.Timedelta(hours=1), "value": pd.Timedelta(0)})
    sig = build(data_).assign(market="us500")
    bk = sim.books({"us500": b})
    rule = dict(exit=("hours", 5), stop=("d20", 1.5))
    main = sim.simulate(sig, bk, **rule)
    nb = {"h4": sim.simulate(sig, bk, exit=("hours", 4), stop=("d20", 1.5))}
    ev = sim.simulate(sig, bk, mode="every", **rule)
    nl = stats.null_test(main, bk, n_draws=2000, **rule)
    idea = os.path.join(TMP, "ideas", "910_lead")
    _declare(idea, {"idea": "910 lead"})
    v = {c: judge.verdict(idea, main, nb, ev, nl, truncation=tr, corr=c, write=False) for c in (-0.6, 0.30, 0.31, None)}
    check("L2: the correlation bar is signed: -0.6 and 0.30 pass, 0.31 and a missing value fail",
          v[-0.6]["bars"]["corr<=0.30"]["pass"] and v[0.30]["bars"]["corr<=0.30"]["pass"] and
          not v[0.31]["bars"]["corr<=0.30"]["pass"] and not v[None]["bars"]["corr<=0.30"]["pass"])
    # prepared hourly bars: read without any request, cut by the lock, validation years only after unlock
    h1 = os.path.join(TMP, "h1")
    os.makedirs(h1, exist_ok=True)
    os.makedirs(h1 + "_val", exist_ok=True)
    idx = pd.date_range("2020-01-01", "2022-03-01", freq="h", tz="UTC", inclusive="left")
    f = pd.DataFrame({"open": 1.10, "high": 1.101, "low": 1.099, "close": 1.10, "volume": 60.0}, index=idx)
    f.index.name = "time"
    f.to_parquet(os.path.join(h1, "eurusd.parquet"))            # holds 2022 rows on purpose: they must not come out
    idv = pd.date_range("2022-01-01", "2026-02-01", freq="h", tz="UTC", inclusive="left")
    fv = pd.DataFrame({"open": 1.20, "high": 1.201, "low": 1.199, "close": 1.20, "volume": 60.0}, index=idv)
    fv.index.name = "time"
    fv.to_parquet(os.path.join(h1 + "_val", "eurusd.parquet"))  # holds 2026 rows on purpose
    real = data.http_get
    data.http_get = _fake
    os.environ["EXPLORE_H1_DIR"] = h1
    try:
        data.lock()
        REQ.clear()
        a = data.load_bars("eurusd", 2020)
        ok_locked = (not REQ and a.index.max() < U("2022-01-01") and a.index.min() == U("2020-01-01") and
                     "prepared" in a.attrs.get("source", "") and a.attrs.get("price_is") == "bid")
        videa = os.path.join(TMP, "ideas", "911_h1")
        os.makedirs(videa, exist_ok=True)
        json.dump(VALDECL, open(os.path.join(videa, "val_declared.json"), "w"))
        json.dump({"verdict": "pass"}, open(os.path.join(videa, "results.json"), "w"))
        data.unlock_val(videa)
        c = data.load_bars("eurusd", 2020)
        ok_unlocked = (not REQ and c.index.max() < U("2026-01-01") and c.index.max() >= U("2025-12-31") and
                       float(c.close[c.index < U("2022-01-01")].max()) == 1.10 and float(c.close[c.index >= U("2022-01-01")].min()) == 1.20)
        data.lock()
        check("L3: prepared hourly bars are read with no request; < 2022 while locked; 2022-2025 after unlock; never 2026",
              ok_locked and ok_unlocked, f"locked last {a.index.max()}, unlocked last {c.index.max()}, requests {len(REQ)}")
        del os.environ["EXPLORE_H1_DIR"]
        REQ.clear()
        d = data.load_bars("usdcad", 2021)
        check("L3: without a prepared file the bars come from the download as before", len(REQ) == 12 and
              d.attrs.get("source") == "dukascopy download", f"{len(REQ)} requests, source {d.attrs.get('source')}")
        # a month refused by the server and cached empty inside the history is an error
        hole = os.path.join(data.cache_dir(), "duka", "GBPUSD")
        os.makedirs(hole, exist_ok=True)
        open(os.path.join(hole, "2021_06_BID.bi5"), "wb").write(b"")
        try:
            data.duka_h1("GBPUSD", 2021)
            check("L4: a month without bars inside the history raises DataGap", False)
        except data.DataGap as e:
            check("L4: a month without bars inside the history raises DataGap", "2021" in str(e))
        # FRED and Yahoo: nothing dated at or after the period end is written to the cache
        data.fred("LEADX", known=data.rule_next_bday_utc(13, 1))
        data.yahoo_daily("LEADY", known=data.rule_local_close("16:00"))
        cf = open([os.path.join(r, x) for r, _, fs in os.walk(os.path.join(data.cache_dir(), "fred")) for x in fs if "LEADX" in x][0]).read()
        cy = json.load(open([os.path.join(r, x) for r, _, fs in os.walk(os.path.join(data.cache_dir(), "yahoo")) for x in fs if "LEADY" in x][0]))
        ty = cy["chart"]["result"][0]["timestamp"]
        check("L5: the FRED and Yahoo cache files hold no row at or after the period end and no price meta",
              "2022-" not in cf and "2023-" not in cf and "2021-12-31" in cf and max(ty) < int(U("2022-01-01").timestamp())
              and set(cy["chart"]["result"][0]["meta"]) == {"exchangeTimezoneName"}, f"{len(cf.splitlines())} FRED lines, {len(ty)} Yahoo days")
    finally:
        data.http_get = real
        os.environ.pop("EXPLORE_H1_DIR", None)
        data.lock()


# ------------------------------------------------------------------ kit v2 (2026-11-18): A pairs, B exits on a condition, C crypto venues
SHC = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "spread_shape.json")))["shape_close"]


def _sp(key, price, t, close=False):
    """Hand spread: FP spread in bp of the reference price (fp_costs.json, or the FX fallback) x price x hour-of-week
    shape at the bar's open (or close)."""
    ref = FPC[key].get("spread_ref_price") or costs.REF_FALLBACK[key]
    return FPC[key]["spread"] / ref * price * (SHC if close else SH)[key][_how(t)]


def _flat_pair(name, ka, kb, pa, pb, kind="ratio", start="2019-05-01", end="2019-07-01"):
    a, b = flat(ka, start, end, price=pa), flat(kb, start, end, price=pb)
    return a, b, sim.pair_book(name, ka, kb, a, b, kind=kind)


def test_pairs_costs():
    """P1: one pair round trip by hand (ratio and product, long and short, across the Wednesday triple-swap night; a
    scheduled exit in the Friday closure at the close-of-bar spread); the legs must share the triple weekday."""
    ti, to = U("2019-06-12 10:00"), U("2019-06-13 10:00")            # Wednesday -> Thursday: 3 nights (triple Wed)
    sl = lambda k, kind: FPC[k]["slip_mkt_bps" if kind == "mkt" else "slip_stop_bps"] * 1e-4  # noqa: E731
    rows, ok = [], True
    for name, ka, kb, pa, pb_, kind in (("eurusd/gbpusd", "eurusd", "gbpusd", 1.10, 1.30, "ratio"),
                                        ("eurusd*usdchf", "eurusd", "usdchf", 1.10, 0.95, "product")):
        a, b, pb = _flat_pair(name, ka, kb, pa, pb_, kind)
        for side in (1, -1):
            sides = (side, -side) if kind == "ratio" else (side, side)
            res = gross = sw = 0.0
            for k, p, s in zip((ka, kb), (pa, pb_), sides):
                si, so = _sp(k, p, ti), _sp(k, p, to)
                fill = (p + si) * (1 + sl(k, "mkt")) if s > 0 else p * (1 - sl(k, "mkt"))       # bid bars: ask = bid + spread
                ex = p * (1 - sl(k, "mkt")) if s > 0 else (p + so) * (1 + sl(k, "mkt"))
                res += s * (ex / fill - 1)
                gross += s * ((p + so / 2) / (p + si / 2) - 1)
                sw += (FPC[k]["swap_long"] if s > 0 else FPC[k]["swap_short"]) / 360 * 3
            res -= sw
            t = sim.simulate(pd.DataFrame({"known_at": [ti], "side": [side], "market": name}), {name: pb},
                             exit=("hours", 24), stop=("bps", 500))
            rt = costs.pair_round_trip(name, side, (pa, pb_), (pa, pb_), ti, to)
            good = (len(t) == 1 and t.reason[0] == "time" and t.exit_time[0] == to and abs(t.net_bp[0] - res * 1e4) < 1e-8
                    and abs(t.gross_bp[0] - gross * 1e4) < 1e-8 and abs(t.swap_bp[0] - sw * 1e4) < 1e-8
                    and abs(t.R[0] - res / 0.05) < 1e-9 and abs(rt["net"] - res) < 1e-12 and rt["nights"] == 3)
            ok &= good
            rows.append(f"{name} {'long' if side > 0 else 'short'}: cost {(gross - res) * 1e4:.2f} bp (swap {sw * 1e4:.2f})")
    check("P1: pair round trip by hand: each leg's spread x shape, slippage, the swap of the side held, 3 nights (Wed)",
          ok, "; ".join(rows))
    # a time exit falling in the Friday closure: both legs at the close of the last bar, close-of-bar spread shape
    a, b, pb = _flat_pair("eurusd/gbpusd", "eurusd", "gbpusd", 1.10, 1.30)
    tf = U("2019-06-14 14:00")
    t = sim.simulate(pd.DataFrame({"known_at": [tf], "side": [1], "market": "eurusd/gbpusd"}), {"eurusd/gbpusd": pb},
                     exit=("hours", 24), stop=("bps", 500))
    lastbar = U("2019-06-14 20:00")
    fa, fb = (1.10 + _sp("eurusd", 1.10, tf)) * (1 + 1e-5), 1.30 * (1 - 1e-5)
    xa, xb = 1.10 * (1 - 1e-5), (1.30 + _sp("gbpusd", 1.30, lastbar, close=True)) * (1 + 1e-5)
    want = (xa / fa - 1) - (xb / fb - 1)
    check("P1: a scheduled pair exit in the Friday closure: both legs at the last close, close-of-bar spread shape",
          t.reason[0] == "time_close" and t.exit_time[0] == U("2019-06-14 21:00") and abs(t.net_bp[0] - want * 1e4) < 1e-8
          and abs(t.exit_px_b[0] - xb) < 1e-12, f"{t.net_bp[0]:.3f} bp")
    try:
        sim.pair_book("btc/xau", "btcusd", "xauusd", flat("btcusd", price=8000.0, hr=50.0), flat("xauusd", price=1300.0, hr=1.0))
        e1 = False
    except costs.CostError:
        e1 = True
    try:
        costs.spread("eurusd/gbpusd", 0.85)
        e2 = False
    except costs.CostError:
        e2 = True
    check("P1: legs with different triple-swap days are refused; costs.spec(pair) works, a pair's spread is per leg",
          e1 and e2 and costs.spec("eurusd/gbpusd")["pair"]["legs"] == ("eurusd", "gbpusd") and "eurusd/gbpusd" not in costs.SPEC)


def test_pairs_stops():
    """P2: stops and targets of a pair are seen at observed prices only (each bar's open and close), never at the level,
    never on one leg's wick; a pair bar needs both legs."""
    a0, b0, _ = _flat_pair("eurusd/gbpusd", "eurusd", "gbpusd", 1.10, 1.30)
    T = U("2019-06-12 10:00")
    i = a0.index.get_loc(T)
    sig = pd.DataFrame({"known_at": [T], "side": [1], "market": "eurusd/gbpusd"})
    fa, fb = (1.10 + _sp("eurusd", 1.10, T)) * (1 + 1e-5), 1.30 * (1 - 1e-5)

    def run(a, b, **kw):
        pb = sim.pair_book("eurusd/gbpusd", "eurusd", "gbpusd", a, b)
        return sim.simulate(sig, {"eurusd/gbpusd": pb}, exit=("hours", 8), **kw), pb
    a = a0.copy()
    a.iloc[i + 1, a.columns.get_loc("low")] = 1.078                     # a wick 2 % down: not an observed pair price
    a.iloc[i + 2, a.columns.get_loc("close")] = 1.10 * 0.992             # the bar closes 0.8 % down: beyond a 0.5 % stop
    t, _ = run(a, b0, stop=("bps", 50))
    xa = 1.10 * 0.992 * (1 - 0.3e-4)
    xb = (1.30 + _sp("gbpusd", 1.30, a0.index[i + 2], close=True)) * (1 + 0.3e-4)
    want = (xa / fa - 1) - (xb / fb - 1)
    check("P2: a pair stop is filled at the observed close beyond the level (both legs, stop slippage, close spread): R < -1",
          t.reason[0] == "stop" and t.exit_time[0] == a0.index[i + 2] + pd.Timedelta(hours=1) and
          abs(t.R[0] - want / 0.005) < 1e-9 and t.R[0] < -1.4, f"R {t.R[0]:.3f} (a fill at the level would give about -1)")
    a = a0.copy()
    a.iloc[i + 2, a.columns.get_loc("open")] = 1.10 * 0.99
    a.iloc[i + 2, a.columns.get_loc("close")] = 1.10 * 0.99
    t, _ = run(a, b0, stop=("bps", 50))
    xa = 1.10 * 0.99 * (1 - 0.3e-4)
    xb = (1.30 + _sp("gbpusd", 1.30, a0.index[i + 2])) * (1 + 0.3e-4)
    check("P2: a pair bar opening beyond the stop fills at that open ('stop_gap', open spread shape)",
          t.reason[0] == "stop_gap" and t.exit_time[0] == a0.index[i + 2] and
          abs(t.R[0] - ((xa / fa - 1) - (xb / fb - 1)) / 0.005) < 1e-9, f"R {t.R[0]:.3f}")
    a = a0.copy()
    a.iloc[i + 1, a.columns.get_loc("high")] = 1.13                      # a leg's wick far beyond the target: ignored
    a.iloc[i + 3, a.columns.get_loc("close")] = 1.10 * 1.006
    t, _ = run(a, b0, stop=("bps", 50), target=("bps", 30))
    xa = 1.10 * 1.006 * (1 - 1e-5)
    xb = (1.30 + _sp("gbpusd", 1.30, a0.index[i + 3], close=True)) * (1 + 1e-5)
    want = (xa / fa - 1) - (xb / fb - 1)
    check("P2: a pair target is a market exit at the observed close that crossed it (market slippage), not at the level; "
          "a leg's wick does not trigger it", t.reason[0] == "target" and t.exit_time[0] == a0.index[i + 3] + pd.Timedelta(hours=1)
          and abs(t.net_bp[0] - want * 1e4) < 1e-8 and t.net_bp[0] > 30 + 1, f"{t.net_bp[0]:.2f} bp against a 30 bp target")
    a = a0.copy()
    a.iloc[i + 2, a.columns.get_loc("close")] = 1.10 * 0.992
    b = b0.drop(b0.index[i + 2])                                         # leg b has no bar at i + 2
    t, pb = run(a, b, stop=("bps", 50))
    check("P2: a pair bar needs both legs: an hour missing in one leg is no pair bar (the other leg's price there is never used)",
          a0.index[i + 2] not in pb.index and len(pb.t) == len(a0) - 1 and t.reason[0] == "time", str(t.reason[0]))
    # D20 of the pair from its observed opens and closes, by hand
    bw = synth.bars("eurusd", seed=61), synth.bars("gbpusd", seed=62)
    pb = sim.pair_book("eurusd/gbpusd", "eurusd", "gbpusd", *bw)
    bka, bkb = sim.Book(bw[0], "eurusd"), sim.Book(bw[1], "gbpusd")
    common = bka.index.intersection(bkb.index)
    ia, ib = bka.index.get_indexer(common), bkb.index.get_indexer(common)
    po, pc = bka.mid["o"][ia] / bkb.mid["o"][ib], bka.mid["c"][ia] / bkb.mid["c"][ib]
    df = pd.DataFrame({"h": np.maximum(po, pc), "l": np.minimum(po, pc)}, index=common)
    g = df.groupby(data.trading_day(common))
    rng_ = (g.h.max() - g.l.min())[g.h.size() >= 10]
    tq = U("2018-03-14 15:00")
    days = rng_[rng_.index < pd.Timestamp("2018-03-14")]                 # trading days ended before 15:00 UTC on the 14th
    check("P2: pair D20 = mean of the last 20 completed 17:00-NY days' range of the observed pair price (by hand)",
          abs(pb.d20(np.array([tq.value]))[0] - days.iloc[-20:].mean()) < 1e-12)


def _ou_legs(ka, kb, seed, kind="ratio", theta=0.02, sig=0.0012, vol=0.0005):
    """Two synthetic legs whose ratio (or product) carries a planted mean-reverting part S (AR(1), half-life ~35 h)."""
    from scipy.signal import lfilter
    t = synth.calendar("fx")
    eps = np.random.default_rng(seed + 77).standard_normal(len(t))
    dS = pd.Series(np.diff(np.r_[0.0, lfilter([sig], [1, -(1 - theta)], eps)]), index=t)
    sb = -0.5 if kind == "ratio" else 0.5
    a = synth.bars(ka, seed=seed, vol_h=vol, edge=lambda i: 0.5 * dS.reindex(i).to_numpy())
    b = synth.bars(kb, seed=seed + 1, vol_h=vol, edge=lambda i: sb * dS.reindex(i).to_numpy())
    return a, b


PAIRS_W = {"audusd/nzdusd": ("audusd", "nzdusd", "ratio"), "eurusd*usdchf": ("eurusd", "usdchf", "product")}


def _pair_z(d, name):
    ka, kb, kind = PAIRS_W[name]
    a, b = d[ka].close, d[kb].close
    c = a.index.intersection(b.index)
    x = np.log(a[c] / b[c]) if kind == "ratio" else np.log(a[c] * b[c])
    x = x[x.index.hour == 20]                                            # the 20:00 UTC bar's close, known at 21:00
    return ((x - x.rolling(20).mean().shift(1)) / x.rolling(20).std().shift(1)).dropna()


def _pair_build(names, thr=1.0):
    def build(d):
        out = []
        for nm in names:
            z = _pair_z(d, nm)
            z = z[z.abs() >= thr]
            out.append(pd.DataFrame({"known_at": z.index + pd.Timedelta(hours=1), "side": -np.sign(z.to_numpy()).astype(int),
                                     "market": nm}))
        return pd.concat(out, ignore_index=True)
    return build


def _pair_events(names, back=0.5):
    def build(d):
        out = []
        for nm in names:
            z = _pair_z(d, nm)
            z = z[z.abs() <= back]
            out.append(pd.DataFrame({"known_at": z.index + pd.Timedelta(hours=1), "market": nm}))
        return pd.concat(out, ignore_index=True)
    return build


# kit v2.1: P3 reads its selection label on a FIXED ledger (running total 2,500, the charter's 'about 2,500 before this
# search'): with the live LEDGER.md, whose total grows with every idea run (2,614 on 2026-11-18), the planted pair (t 5.2)
# slid from 'pass' to 'pass, weak against selection' although nothing in the kit changed (the original v2 kit fails it
# too on today's ledger). The check itself is unchanged.
LEDGER_FIXED = os.path.join(TMP, "LEDGER_fixed.md")
open(LEDGER_FIXED, "w").write("# fixture\nRunning total of configurations (before this search + this search): **2500**\n")


def test_pairs_planted_and_basket():
    """P3: a planted mean-reverting pair (fade a 20-day z-score, exit when z is back inside 0.5) is found through the full
    judge with both truncation reports; a basket of two pairs (a ratio and a product) is judged with the basket bars
    across PAIRS (market = pair name), and the sizing reports both legs."""
    d = {}
    for nm, (ka, kb, kind) in PAIRS_W.items():
        d[ka], d[kb] = _ou_legs(ka, kb, {"audusd/nzdusd": 3, "eurusd*usdchf": 13}[nm], kind)
    rl = {k: pd.Timedelta(hours=1) for k in d}
    bk = {nm: sim.pair_book(nm, ka, kb, d[ka], d[kb], kind=kind) for nm, (ka, kb, kind) in PAIRS_W.items()}
    out = {}
    for label, names in (("one", ["audusd/nzdusd"]), ("basket", list(PAIRS_W))):
        bs, be = _pair_build(names), _pair_events(names)
        sub = {k: v for k, v in d.items() if any(k in PAIRS_W[n][:2] for n in names)}
        trs = checks.truncation_test(bs, sub, row_len={k: rl[k] for k in sub})
        tre = checks.truncation_test(be, sub, row_len={k: rl[k] for k in sub})
        sig, ev = bs(sub), be(sub)
        books_ = {n: bk[n] for n in names}
        rule = dict(exit=sim.event_exit(ev, ("bdays", 5)), stop=("d20", 1.5))
        main = sim.simulate(sig, books_, **rule)
        nb = {"mh3": sim.simulate(sig, books_, exit=sim.event_exit(ev, ("bdays", 3)), stop=("d20", 1.5)),
              "s2": sim.simulate(sig, books_, exit=sim.event_exit(ev, ("bdays", 5)), stop=("d20", 2.0))}
        evr = sim.simulate(sig, books_, mode="every", **rule)
        nl = stats.null_test(main, books_, n_draws=2000, **rule)
        idea = os.path.join(TMP, "ideas", f"92{len(names)}_pairs")
        _declare(idea, {"idea": f"pairs {label}"})
        res = judge.verdict(idea, main, nb, evr, nl, ten=TEN, write=False, truncation=trs, event_truncation=tre,
                            ledger=LEDGER_FIXED)
        out[label] = (res, main, trs, tre)
    r1, m1, trs, tre = out["one"]
    NUMBERS["pair_planted"] = {k: v["value"] for k, v in r1["bars"].items()}
    check("P3: a planted mean-reverting pair (event exit when z is back) passes every bar, guards included",
          trs["pass"] and tre["pass"] and r1["verdict"] == "pass" and r1["main"]["markets"] == ["audusd/nzdusd"]
          and not r1["basket"] and "event_truncation_test" in r1["bars"],
          f"{r1['verdict']} {r1['failed_bars']}; n {r1['main']['n']}, t {r1['main']['t_trade']:.2f}, null {r1['null']['percentile']:.1f}")
    rb = out["basket"][0]
    bym = rb["main"]["by_market"]
    check("P3: a basket of 2 pairs is judged across pairs (t on daily sums, markets = pairs, small-basket share 75 %)",
          rb["basket"] and set(bym) == set(PAIRS_W) and "t_daily>=2.5" in rb["bars"] and
          "max_market_share<=75%" in rb["bars"] and rb["verdict"] == "pass", f"{rb['verdict']} {rb['failed_bars']} "
          f"{ {k: round(v['sum_R'], 1) for k, v in bym.items()} }")
    sz = rb["sizing"]["by_market"]
    pz = sz.get("eurusd*usdchf", {})
    check("P3: the minimum-lot sizing of a pair reports both legs (lots for equal notional, margins, loss at median stop)",
          set(pz.get("legs", {})) == {"eurusd", "usdchf"} and pz.get("margin_eur", 0) > 0 and
          pz.get("loss_at_median_stop_eur", 0) > 0 and all(v["lots_rounded_up"] >= 0.01 for v in pz["legs"].values()),
          json.dumps({k: round(v, 3) if isinstance(v, float) else v for k, v in pz.items() if k != "legs"}))
    # exact two-leg result vs the synthetic price's result P_exit / P_entry - 1: second order, measured
    ra = m1.exit_px_a / m1.entry_px_a - 1
    rb_ = m1.exit_px_b / m1.entry_px_b - 1
    exact = ra - rb_
    synth_r = (m1.exit_px_a / m1.exit_px_b) / (m1.entry_px_a / m1.entry_px_b) - 1
    diff_R = (exact - synth_r) * m1.side / m1.stop_frac
    NUMBERS["pair_exact_vs_synthetic"] = {"mean_abs_diff_R": float(diff_R.abs().mean()), "max_abs_diff_R": float(diff_R.abs().max()),
                                         "mean_diff_R": float(diff_R.mean()), "mean_abs_R": float(m1.R.abs().mean())}
    check("P3: the synthetic price's result differs from the exact two-leg result by (r_a - r_b) r_b / (1 + r_b) only "
          "(the kit uses the exact one)", np.allclose(exact - synth_r, exact * rb_ / (1 + rb_), atol=1e-13) and
          float(diff_R.abs().mean()) < 0.05, json.dumps(NUMBERS["pair_exact_vs_synthetic"]))


def test_pairs_noise():
    """P4: pure-noise pairs (independent legs, random signals) through the full judge: gross t about N(0, 1), none passes,
    the null percentile is uniform; with exits on random events too."""
    t0 = time.time()
    rng = np.random.default_rng(91)
    combos = [("eurusd", "gbpusd", "ratio"), ("audusd", "nzdusd", "ratio"), ("eurusd", "usdchf", "product"),
              ("audusd", "usdcad", "product"), ("xauusd", "xagusd", "ratio"), ("us100", "us30", "ratio"),
              ("us500", "ger40", "ratio"), ("gbpusd", "usdjpy", "product")]
    tg, pct, npass, pct_ev, tg_ev = [], [], 0, [], []
    days = pd.bdate_range("2013-03-01", "2021-12-20", tz="UTC")
    for w in range(16):
        ka, kb, kind = combos[w % len(combos)]
        nm = f"n{w}:{ka}{'/' if kind == 'ratio' else '*'}{kb}"
        pb = sim.pair_book(nm, ka, kb, synth.bars(ka, seed=300 + w), synth.bars(kb, seed=400 + w), kind=kind)
        bk = {nm: pb}
        for r in range(6):
            pick = days[rng.random(len(days)) < 0.15] + pd.Timedelta(hours=int(rng.integers(0, 24)))
            sg = pd.DataFrame({"known_at": pick, "side": rng.choice([-1, 1], len(pick)), "market": nm})
            if r < 4:
                hold = int(rng.choice([3, 6, 12, 24]))
                rule = dict(exit=("hours", hold), stop=("d20", 1.0))
                nb = {"a": sim.simulate(sg, bk, exit=("hours", hold * 2), stop=("d20", 1.0)),
                      "b": sim.simulate(sg, bk, exit=("hours", hold), stop=("d20", 2.0))}
            else:                                                    # exits on random events (known times, no edge)
                evt = pb.index[rng.random(len(pb.index)) < 0.03] + pd.Timedelta(hours=1)
                rule = dict(exit=("event", evt, ("bdays", 3)), stop=("d20", 1.5))
                nb = {"a": sim.simulate(sg, bk, exit=("event", evt, ("bdays", 2)), stop=("d20", 1.5))}
            m = sim.simulate(sg, bk, **rule)
            ev = sim.simulate(sg, bk, mode="every", **rule)
            nl = stats.null_test(m, bk, n_draws=2000, seed=w * 10 + r, **rule)
            res = judge.verdict(TMP, m, nb, ev, nl, ten=TEN, write=False)
            core = [f for f in res["failed_bars"] if f not in GUARDS + ("event_truncation_test",)]
            npass += not core
            (tg if r < 4 else tg_ev).append(stats.t_stat(m.R_gross))
            (pct if r < 4 else pct_ev).append(nl["percentile"])
    tg, pct, allp = np.array(tg), np.array(pct), np.array(pct + pct_ev)
    tall = np.r_[tg, tg_ev]
    NUMBERS["pair_noise"] = {"rules": len(allp), "passed": int(npass), "t_gross_mean": float(tall.mean()),
                             "t_gross_sd": float(tall.std()), "ks_normal_p": float(st.kstest(tall, "norm").pvalue),
                             "null_pct_ks_uniform_p": float(st.kstest(allp / 100, "uniform").pvalue),
                             "null_pct_ge_97.5": int((allp >= 97.5).sum()), "event_rules": len(pct_ev),
                             "event_null_mean": float(np.mean(pct_ev)), "seconds": round(time.time() - t0, 1)}
    nn = NUMBERS["pair_noise"]
    check("P4: 96 pure-noise pair rules (32 with event exits) through the full judge: none passes", npass == 0, json.dumps(nn))
    check("P4: noise pairs: gross t looks standard normal (observed fills keep the game fair)",
          abs(nn["t_gross_mean"]) < 0.3 and 0.75 < nn["t_gross_sd"] < 1.3 and nn["ks_normal_p"] > 0.001)
    check("P4: the null is calibrated on pairs (percentile uniform, >= 97.5 in about 2.5 % of rules), event exits included",
          nn["null_pct_ks_uniform_p"] > 0.001 and nn["null_pct_ge_97.5"] <= 8 and 30 < nn["event_null_mean"] < 70)


def test_event_mechanics():
    """E1: exit on a condition: an event before, at and inside the entry bar; max_hold; an event in a closure; per-market
    events; the causality invariant on random events."""
    b = flat("eurusd")
    T = U("2019-06-12 10:00")
    sig = pd.DataFrame({"known_at": [T], "side": [1]})
    H = pd.Timedelta(hours=1)
    run = lambda ev, mh=("hours", 5), s=sig, bb=b: sim.simulate(s, bb, market="eurusd", exit=("event", pd.DatetimeIndex(ev), mh),  # noqa: E731
                                                              stop=("d20", 1.0))
    r1 = run([T - H, T, T + pd.Timedelta(minutes=30)])
    r2 = run([T - H, T])
    r3 = run([T + 2 * H])
    r4 = run([T + 2 * H + pd.Timedelta(seconds=1)])
    r5 = run([], ("bdays", 1))
    check("E1: an event before or AT the entry bar's open is ignored; one inside the entry bar exits at the next open; "
          "an event at a bar's open exits at that open; 1 s later at the next one; none: max_hold",
          (r1.reason[0], r1.exit_time[0]) == ("event", T + H) and (r2.reason[0], r2.exit_time[0]) == ("time", T + 5 * H) and
          (r3.reason[0], r3.exit_time[0]) == ("event", T + 2 * H) and r4.exit_time[0] == T + 3 * H and
          (r5.reason[0], r5.exit_time[0]) == ("time", T + pd.Timedelta(days=1)),
          f"{r1.exit_time[0]} {r2.exit_time[0]} {r3.exit_time[0]} {r4.exit_time[0]} {r5.exit_time[0]}")
    s = 7.5e-5 / 1.16 * 1.10
    fill = (1.10 + s * SH["eurusd"][_how(T)]) * (1 + 1e-5)
    check("E1: an event exit is a market exit at the bar's open (bid, market slippage)",
          abs(r3.exit_px[0] - 1.10 * (1 - 1e-5)) < 1e-12 and abs(r3.entry_px[0] - fill) < 1e-12)
    fr = U("2019-06-14 14:00")
    sat = U("2019-06-15 12:00")
    sf = pd.DataFrame({"known_at": [fr], "side": [1]})
    r6 = run([sat], ("bdays", 3), sf)
    r7 = run([sat], ("hours", 24), sf)
    check("E1: an event in the weekend closure exits at the reopening bar's open, never at the Friday close before it "
          "(that close happens before the event is known); a max_hold falling in the closure still exits at the close",
          (r6.reason[0], r6.exit_time[0]) == ("event", U("2019-06-16 21:00")) and
          (r7.reason[0], r7.exit_time[0]) == ("time_close", U("2019-06-14 21:00")), f"{r6.exit_time[0]} / {r7.exit_time[0]}")
    two = pd.concat([sig.assign(market="eurusd"), pd.DataFrame({"known_at": [T], "side": [1], "market": "gbpusd"})])
    bk = sim.books({"eurusd": b, "gbpusd": flat("gbpusd", price=1.30)})
    r8 = sim.simulate(two, bk, exit=("event", {"eurusd": pd.DatetimeIndex([T + 2 * H]), "gbpusd": pd.DatetimeIndex([T + 3 * H])},
                                     ("hours", 5)), stop=("d20", 1.0))
    try:
        sim.simulate(two, bk, exit=("event", {"eurusd": pd.DatetimeIndex([T + 2 * H])}, ("hours", 5)), stop=("d20", 1.0))
        e1 = False
    except ValueError:
        e1 = True
    try:
        run(pd.DatetimeIndex(["2019-06-12 12:00"]))
        e2 = False
    except ValueError:
        e2 = True
    check("E1: events per market; a market without events and tz-naive event times are refused",
          dict(zip(r8.market, r8.exit_time)) == {"eurusd": T + 2 * H, "gbpusd": T + 3 * H} and e1 and e2)
    # causality invariant on random events and synthetic bars (single market and a pair)
    bw = synth.bars("us500", seed=71)
    rng = np.random.default_rng(71)
    pbk = sim.pair_book("us100/us30", "us100", "us30", synth.bars("us100", seed=72), synth.bars("us30", seed=73))
    bad = 0
    for mk, bkk in (("us500", sim.Book(bw, "us500")), ("us100/us30", pbk)):
        evt = U("2013-01-01") + pd.to_timedelta(np.sort(rng.choice(4_730_000, 4000, replace=False)), unit="min")
        days = pd.bdate_range("2013-03-01", "2021-12-20", tz="UTC") + pd.Timedelta(hours=15)
        tr = sim.simulate(pd.DataFrame({"known_at": days, "side": rng.choice([-1, 1], len(days)), "market": mk}),
                          {mk: bkk}, exit=("event", evt, ("bdays", 4)), stop=("d20", 3.0), mode="every")
        en = tr.entry_time.astype("int64").to_numpy()
        xt = tr.exit_time.astype("int64").to_numpy()
        e_ns = evt.as_unit("ns").asi8
        k = np.searchsorted(e_ns, en, side="right")
        first = np.where(k < len(e_ns), e_ns[np.clip(k, 0, len(e_ns) - 1)], np.iinfo(np.int64).max)
        nxt = bkk.t[np.clip(np.searchsorted(bkk.t, first, side="left"), 0, len(bkk.t) - 1)]
        ise = (tr.reason == "event").to_numpy()
        bad += int((ise & ((xt < first) | (xt != nxt))).sum())                   # an event exit before its event, or late
        bad += int((~ise & (tr.reason.isin(["time", "time_close"])).to_numpy() & (nxt < xt) & (first < np.iinfo(np.int64).max)).sum())
    check("E1: causality on random events: every event exit is at the first bar open at or after the first event after "
          "entry, never before it; no time exit outlives an event", bad == 0, f"{bad} violations")


def test_event_lookahead():
    """E2: a look-ahead trap in an exit condition (an exit event stamped at its bar's open but computed from that bar's
    close) gives a large fake edge; the truncation test on the event build catches it, and judge.verdict refuses a pass
    without the passing event report bound to THOSE events."""
    b = synth.bars("us500", seed=81)
    bk = {"us500": sim.Book(b, "us500")}
    days = pd.bdate_range("2013-03-01", "2021-12-20", tz="UTC") + pd.Timedelta(hours=14)
    longs = pd.DataFrame({"known_at": days, "side": 1, "market": "us500"})

    def ev_bad(d):                                     # 'the bar fell', stamped at the bar's OPEN: uses its own close
        x = d[d.close < d.open]
        return pd.DataFrame({"known_at": x.index})

    def ev_good(d):                                    # the same condition, known at the bar's end
        x = d[d.close < d.open]
        return pd.DataFrame({"known_at": x.index + pd.Timedelta(hours=1)})
    rule = lambda ev: dict(exit=("event", ev, ("hours", 48)), stop=("d20", 3.0))  # noqa: E731
    tb = sim.simulate(longs, bk, **rule(ev_bad(b)))
    tg = sim.simulate(longs, bk, **rule(ev_good(b)))
    rb, rg = checks.truncation_test(ev_bad, b, [U("2016-03-02 15:00")]), checks.truncation_test(ev_good, b, [U("2016-03-02 15:00")])
    check("E2: trap: an exit event stamped before it could be known gives a large fake edge; the truncation test on the "
          "event build catches it; stamped at the bar's end there is no edge",
          stats.t_stat(tb.R_gross) > 10 and abs(stats.t_stat(tg.R_gross)) < 3.5 and not rb["pass"] and rg["pass"] and
          rb.get("events_sha") and rb.get("signals_sha") is None,
          f"t gross bad {stats.t_stat(tb.R_gross):.1f}, good {stats.t_stat(tg.R_gross):.2f}")
    # the judge: planted signal world, exit when the 18:00 bar has closed (known 19:00): a pass needs THOSE events' report
    bp, sig0 = synth.signal_world("us500", seed=5, edge=0.0004)
    bkp = {"us500": sim.Book(bp, "us500")}

    def ev_clock(d):
        x = d[d.index.hour == 18]
        return pd.DataFrame({"known_at": x.index + pd.Timedelta(hours=1)})
    trs = _tr_fixed(sig0)
    tre = checks.truncation_test(ev_clock, bp, row_len=pd.Timedelta(hours=1))
    other = checks.truncation_test(lambda d: ev_clock(d).iloc[::2].reset_index(drop=True), bp, row_len=pd.Timedelta(hours=1))
    failed = checks.truncation_test(lambda d: pd.DataFrame({"known_at": d[d.index.hour == 18].index}), bp,
                                    row_len=pd.Timedelta(hours=1))
    ev = ev_clock(bp)
    rl = dict(exit=("event", ev, ("hours", 24)), stop=("d20", 1.5))
    main = sim.simulate(sig0, bkp, **rl)
    nb = {"s2": sim.simulate(sig0, bkp, exit=("event", ev, ("hours", 24)), stop=("d20", 2.0))}
    evr = sim.simulate(sig0, bkp, mode="every", **rl)
    nl = stats.null_test(main, bkp, n_draws=2000, **rl)
    idea = os.path.join(TMP, "ideas", "930_event")
    _declare(idea, {"idea": "930 event"})
    v = {k: judge.verdict(idea, main, nb, evr, nl, ten=TEN, write=False, truncation=trs, event_truncation=x)
         for k, x in (("good", tre), ("none", None), ("other", other), ("failed", failed))}
    plain = judge.verdict(idea, sim.simulate(sig0, bkp, exit=("hours", 5), stop=("d20", 1.5)), None, None, None,
                          ten=TEN, write=False, truncation=trs)
    check("E2: judge: an event-exit rule passes only with the passing truncation report of THOSE events (missing, other "
          "events or a failed report: fail); a rule without event exits has no such bar",
          v["good"]["verdict"] == "pass" and all(v[k]["verdict"] == "fail" and v[k]["failed_bars"] == ["event_truncation_test"]
                                                 for k in ("none", "other", "failed"))
          and failed["pass"] is False and "event_truncation_test" not in plain["bars"] and
          (main.reason == "event").mean() > 0.9,
          f"good {v['good']['verdict']} {v['good']['failed_bars']}; none {v['none']['failed_bars']}; "
          f"other {v['other']['bars']['event_truncation_test']['value']}; failed {v['failed']['bars']['event_truncation_test']['value']}")


def test_event_null_noise():
    """E3: the null with event exits re-enters at random days and leaves on the same events: calibrated on noise
    (single markets, dense signals whose trades overlap, default and one-position nulls)."""
    rng = np.random.default_rng(97)
    pe, po, tg = [], [], []
    keys = ["us500", "eurusd", "xauusd", "btcusd", "gbpusd"]
    days = pd.bdate_range("2013-03-01", "2021-12-20", tz="UTC")
    for w in range(10):
        key = keys[w % len(keys)]
        bw = synth.bars(key, seed=500 + w)
        bk = {key: sim.Book(bw, key)}
        for r in range(6):
            sg = pd.DataFrame({"known_at": days[rng.random(len(days)) < 0.5] + pd.Timedelta(hours=int(rng.integers(0, 24))),
                               "market": key})
            sg["side"] = rng.choice([-1, 1], len(sg))
            evt = bw.index[rng.random(len(bw)) < float(rng.choice([0.01, 0.05]))] + pd.Timedelta(hours=1)
            rule = dict(exit=("event", evt, ("bdays", int(rng.choice([2, 5])))), stop=("d20", 1.5))
            m = sim.simulate(sg, bk, **rule)
            tg.append(stats.t_stat(m.R_gross))
            pe.append(stats.null_test(m, bk, n_draws=1000, seed=w * 10 + r, **rule)["percentile"])
            if r < 2:
                po.append(stats.null_test(m, bk, n_draws=1000, seed=w * 10 + r, mode="one", **rule)["percentile"])
    pe, po, tg = np.array(pe), np.array(po), np.array(tg)
    NUMBERS["event_null"] = {"rules": len(pe), "ge97.5": int((pe >= 97.5).sum()), "mean": float(pe.mean()),
                             "ks_p": float(st.kstest(pe / 100, "uniform").pvalue), "rules_one": len(po),
                             "mean_one": float(po.mean()), "ge97.5_one": int((po >= 97.5).sum()),
                             "t_gross_mean": float(tg.mean()), "t_gross_sd": float(tg.std())}
    n = NUMBERS["event_null"]
    check("E3: the null with event exits is calibrated on noise (uniform, about 2.5 % at 97.5; gross t about N(0,1))",
          n["ks_p"] > 0.001 and n["ge97.5"] <= 5 and 35 < n["mean"] < 65 and n["ge97.5_one"] <= 3 and
          abs(n["t_gross_mean"]) < 0.4 and n["t_gross_sd"] < 1.4, json.dumps(n))


VREQ = []
VBAD = {"on": False}


def _vpx(ts):
    """Deterministic candle of hour ts (unix s): open, high, low, close distinct so a column swap is seen."""
    base = 100.0 + (ts // 3600) % 50
    return base, base + 3.0, base - 2.0, base + 1.0


def _fake_venues(url, **kw):
    """Fake Bitstamp / Bitfinex / Coinbase: honours the bounds but serves at most 200 / 300 / 300 candles per call (so the
    kit must page), Bitfinex omits every 97th hour (no trade); with VBAD['on'] every reply also carries a candle of
    2022-06 and one of 2026-02 (a server that ignores the bounds)."""
    from urllib.parse import parse_qs, urlparse
    VREQ.append(url)
    q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    late = [int(U("2022-06-01").timestamp()), int(U("2026-02-01").timestamp())] if VBAD["on"] else []
    if "bitstamp" in url:
        end, start, lim = int(q["end"]), int(q["start"]), min(int(q["limit"]), 200)
        ts = list(range(max(start, end - (lim - 1) * 3600), end + 1, 3600)) + late
        rows = [{"timestamp": str(t), "open": f"{_vpx(t)[0]:.2f}", "high": f"{_vpx(t)[1]:.2f}", "low": f"{_vpx(t)[2]:.2f}",
                 "close": f"{_vpx(t)[3]:.2f}", "volume": "1.5"} for t in ts]
        return json.dumps({"data": {"pair": "BTC/USD", "ohlc": rows}}).encode()
    if "bitfinex" in url:
        s, e, lim = int(q["start"]) // 1000, int(q["end"]) // 1000, min(int(q["limit"]), 300)
        ts = [t for t in range(-(-s // 3600) * 3600, e + 1, 3600) if (t // 3600) % 97][:lim] + late
        return json.dumps([[t * 1000, _vpx(t)[0], _vpx(t)[3], _vpx(t)[1], _vpx(t)[2], 2.0] for t in ts]).encode()
    if "coinbase" in url:
        s, e = int(pd.Timestamp(q["start"]).timestamp()), int(pd.Timestamp(q["end"]).timestamp())
        if (e - s) // 3600 + 1 > 300:
            return json.dumps({"message": "granularity too small for the requested time range"}).encode()
        ts = list(range(s, e + 1, 3600)) + late
        return json.dumps([[t, _vpx(t)[2], _vpx(t)[1], _vpx(t)[0], _vpx(t)[3], 3.0] for t in ts][::-1]).encode()
    return _fake(url, **kw)


def _times_in(url):
    """Every time named by a venue request, as UTC timestamps."""
    from urllib.parse import parse_qs, urlparse
    q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    out = []
    for k in ("start", "end"):
        if k in q:
            v = q[k]
            out.append(U(v.replace("Z", "")) if "T" in v else pd.Timestamp(int(v) // (1000 if "bitfinex" in url else 1),
                                                                             unit="s", tz="UTC"))
    return out


def test_crypto_venues():
    """C1-C4: data.crypto_h1 for bitstamp, bitfinex, coinbase behind the period lock (fake server): paging, complete
    hours, nothing of 2022+ requested while locked, never 2026, a server ignoring the bounds cannot put a later row in
    the cache, columns decoded in the right order, DataGap on a hole; load_bars(..., venue=) gives FP-ready bars."""
    real = data.http_get
    data.http_get = _fake_venues
    os.environ["EXPLORE_CACHE"] = os.path.join(TMP, "cache_venues")
    try:
        data.lock()
        res = {}
        for v in ("bitstamp", "bitfinex", "coinbase"):
            VREQ.clear()
            d = data.crypto_h1(v, "btcusd", start="2021-10")
            req_t = [x for u in VREQ for x in _times_in(u)]
            hrs = pd.date_range("2021-10-01", "2022-01-01", freq="h", tz="UTC", inclusive="left")
            want = hrs[(hrs.as_unit("s").asi8 // 3600) % 97 != 0] if v == "bitfinex" else hrs
            o, h, l, c = _vpx(int(d.index[5].timestamp()))
            res[v] = {"n": len(d), "calls": len(VREQ), "complete": d.index.equals(want),
                      "max_req": max(req_t), "cols": (d.open.iloc[5], d.high.iloc[5], d.low.iloc[5], d.close.iloc[5]) == (o, h, l, c),
                      "attrs": d.attrs.get("venue") == v}
        check("C1: crypto venues page through each month (calls > months) and return every hour once, in the right columns",
              all(r["complete"] and r["cols"] and r["attrs"] and r["calls"] > 3 for r in res.values()),
              json.dumps({k: {kk: str(vv) for kk, vv in r.items()} for k, r in res.items()}))
        check("C1: locked: no venue request names a time at or after 2022-01-01",
              all(r["max_req"] < U("2022-01-01") for r in res.values()), str({k: str(r["max_req"]) for k, r in res.items()}))
        shutil.rmtree(os.environ["EXPLORE_CACHE"], ignore_errors=True)
        VBAD["on"] = True
        out = {v: data.crypto_h1(v, "ethusd", start="2021-11") for v in ("bitstamp", "bitfinex", "coinbase")}
        cached = [os.path.join(r, x) for r, _, fs in os.walk(os.path.join(data.cache_dir(), "crypto")) for x in fs]
        mx = max(int(pd.read_csv(p).t.max()) for p in cached if os.path.getsize(p))
        check("C2: a server that ignores the bounds (rows of 2022 and 2026 in every reply): nothing past 2021 is returned "
              "or cached", all(x.index.max() < U("2022-01-01") and len(x) for x in out.values()) and
              mx < int(U("2022-01-01").timestamp()) and not any("2022" in os.path.basename(p) or "2026" in p for p in cached),
              f"{len(cached)} cache files, last cached hour {pd.Timestamp(mx, unit='s')}")
        VBAD["on"] = False
        idea = os.path.join(TMP, "ideas", "940_crypto")
        os.makedirs(idea, exist_ok=True)
        json.dump(VALDECL, open(os.path.join(idea, "val_declared.json"), "w"))
        json.dump({"verdict": "pass"}, open(os.path.join(idea, "results.json"), "w"))
        data.unlock_val(idea)
        VREQ.clear()
        late = {v: data.crypto_h1(v, "btcusd", start="2025-11") for v in ("bitstamp", "bitfinex", "coinbase")}
        req_t = [x for u in VREQ for x in _times_in(u)]
        data.lock()
        cached = [os.path.join(r, x) for r, _, fs in os.walk(os.path.join(data.cache_dir(), "crypto")) for x in fs]
        check("C3: unlocked: venue rows to 2025-12-31, no request names 2026, no 2026 month cached",
              all(x.index.max() < U("2026-01-01") and x.index.max() >= U("2025-12-31") for x in late.values()) and
              max(req_t) < U("2026-01-01") and not any("2026-" in os.path.basename(p) for p in cached),
              f"last request time {max(req_t)}")
        hole = os.path.join(data.cache_dir(), "crypto", "bitstamp", "btcusd", "1h", "2021-08.csv")
        open(hole, "w").write("")
        try:
            data.crypto_h1("bitstamp", "btcusd", start="2021-06")
            check("C4: a month without candles inside a venue's history raises DataGap", False)
        except data.DataGap:
            check("C4: a month without candles inside a venue's history raises DataGap", True)
        os.remove(hole)
        VREQ.clear()
        lb = data.load_bars("btcusd", 2021, venue="bitstamp")
        dflt = data.load_bars("btcusd", 2021)
        srv = data.server_time(lb.index)
        try:
            data.load_bars("eurusd", 2021, venue="bitstamp")
            e1 = False
        except ValueError:
            e1 = True
        check("C4: load_bars('btcusd', venue='bitstamp'): FP-ready (price 'mid', FP weekend closure removed, venue in attrs); "
              "the default is still Binance; venue= on a non-crypto key is refused",
              lb.attrs.get("price_is") == "mid" and lb.attrs.get("venue") == "bitstamp" and not (srv.dayofweek >= 5).any()
              and lb.index.min() >= U("2021-01-01") and lb.index.max() < U("2022-01-01") and
              any("bitstamp" in u for u in VREQ) and any("binance" in u for u in VREQ) and
              dflt.attrs.get("source") == "binance download" and "venue" not in dflt.attrs and e1,
              f"{len(lb)} bitstamp bars, {len(dflt)} binance bars")
    finally:
        VBAD["on"] = False
        data.http_get = real
        data.lock()


def test_net_venues():
    """--net: one in-sample month of each venue decoded and compared with Binance's BTCUSDT for the same month."""
    os.environ["EXPLORE_CACHE"] = os.path.join(TMP, "netcache")
    data.lock()
    try:
        bn = data.binance_klines("BTCUSDT", "1h", start="2019-06", end="2019-06-30")
    except Exception as e:
        check("net: Binance BTCUSDT 2019-06 for the venue comparison", False, repr(e))
        return
    for v in ("bitstamp", "bitfinex", "coinbase"):
        try:
            x = data.crypto_h1(v, "btcusd", start="2019-06", end="2019-06-30")
            j = x.close.reindex(bn.index).dropna()
            rel = float((j / bn.close.reindex(j.index) - 1).abs().median())
            check(f"net: {v} BTC/USD 2019-06 decoded (hourly, columns in order) and within 1 % of Binance BTCUSDT",
                  len(x) >= 650 and rel < 0.01 and (x.high >= x[["open", "close"]].max(axis=1)).all() and
                  x.index.max() < U("2019-07-01"), f"{len(x)} bars, median |venue / Binance - 1| = {rel:.4%}")
        except Exception as e:
            check(f"net: {v} reachable", False, repr(e))


# ------------------------------------------------------------------ fixes after the extension's review (2026-11-18)
def _supp_world():
    """Two independent noise legs (eurusd, gbpusd) and the verifier's z-score of their ratio (scratchpad
    kit_v2/verify/suppress_*.py): the pair has no edge."""
    H = pd.Timedelta(hours=1)
    a, b = synth.bars("eurusd", seed=71), synth.bars("gbpusd", seed=72)

    def pc(d):
        i = d["a"].index.intersection(d["b"].index)
        return d["a"].close.reindex(i) / d["b"].close.reindex(i)

    def z_(d):
        lp = np.log(pc(d))
        return (lp - lp.rolling(120).mean()) / lp.rolling(120).std()

    def ev_build(d, k=6):            # exits back inside 1.5 (+ 6-hourly 'still inside'); k > 0: DROPPED when |z| will
        z = z_(d)                    # fall further in k bars, written so that a NaN at the end of a cut KEEPS it
        e = ((z.abs() < 1.5) & (z.shift(1).abs() >= 1.5)) | ((z.abs() < 1.5) & (np.arange(len(z)) % 6 == 0))
        if k:
            e = e & ~(z.abs().shift(-k) < z.abs() - 0.3)
        return pd.DataFrame({"known_at": z.index[e.values] + H})

    def sig_build(d, k=6):           # fade |z| > 1.5; k > 0: a signal DROPPED when the next k bars go against it
        z, lp = z_(d), np.log(pc(d))
        up = (z < -1.5) & (z.shift(1) >= -1.5)
        dn = (z > 1.5) & (z.shift(1) <= 1.5)
        if k:
            fut = lp.shift(-k - 1) - lp.shift(-1)
            up, dn = up & ~(fut < 0), dn & ~(fut > 0)
        return pd.DataFrame({"known_at": z.index[(up | dn).values] + H,
                             "side": np.where(up[up | dn], 1, -1)}).reset_index(drop=True)
    return {"a": a, "b": b}, {"a": H, "b": H}, ev_build, sig_build


def test_fix_v1_suppression():
    """FIX V1 (blocking): a build that DROPS an exit event (or a signal) when the future is favourable, with a NaN at the
    end of a cut keeping it, passed the event guard with its 8 cuts at kept events' stamps (9 seeds of 10) and the
    full judge on pure noise. The guard now cuts densely by default (50 stamp cuts, 50 cuts 1-24 bars after stamps,
    100 random bar-end cuts) and the judge refuses a report with fewer (checks.cuts_ok)."""
    D, RL, ev_build, sig_build = _supp_world()
    seeds = range(4)
    ev_bad = [checks.truncation_test(ev_build, D, row_len=RL, seed=s) for s in seeds]
    sg_bad = [checks.truncation_test(sig_build, D, row_len=RL, seed=s) for s in seeds]
    ev_ok = checks.truncation_test(lambda d: ev_build(d, 0), D, row_len=RL)
    sg_ok = checks.truncation_test(lambda d: sig_build(d, 0), D, row_len=RL)
    pb = {"eurusd/gbpusd": sim.pair_book("eurusd/gbpusd", "eurusd", "gbpusd", D["a"], D["b"])}
    sgx = sig_build(D, 0).assign(market="eurusd/gbpusd")
    t_bad = stats.t_stat(sim.simulate(sgx, pb, exit=("event", ev_build(D), ("bdays", 5)), stop=("d20", 1.5)).R_gross)
    t_hon = stats.t_stat(sim.simulate(sgx, pb, exit=("event", ev_build(D, 0), ("bdays", 5)), stop=("d20", 1.5)).R_gross)
    check("FIX V1: the suppression trap is real on a noise pair (dropping exit events that the future would improve "
          "gives a fake gross t; honest events give none)", t_bad > 3 and abs(t_hon) < 3,
          f"gross t suppressed {t_bad:.2f}, honest {t_hon:.2f}")
    check("FIX V1: the default truncation test now catches the NaN-polarity suppression in an EVENT build (every seed)",
          all(not r["pass"] for r in ev_bad) and ev_ok["pass"] and ev_ok.get("density_ok"),
          f"failed cuts per seed {[sum(not c['equal'] for c in r['cuts']) for r in ev_bad]}; honest {ev_ok['pass']}, "
          f"{len(ev_ok['cuts'])} cuts")
    check("FIX V1: ... and in a SIGNAL build (the older guard had the same blind spot)",
          all(not r["pass"] for r in sg_bad) and sg_ok["pass"] and sg_ok.get("density_ok"),
          f"failed cuts per seed {[sum(not c['equal'] for c in r['cuts']) for r in sg_bad]}")
    sparse = checks.truncation_test(ev_build, D, row_len=RL, n_signal_cuts=8, n_random_cuts=0, n_after_cuts=0)
    ok_d, why_d = checks.cuts_ok(sparse)
    check("FIX V1: a report with the old density (8 stamp cuts, no after- or random cuts) is refused by checks.cuts_ok "
          "(whether or not its few cuts happened to see the trap)", not ok_d and "too few" in why_d,
          f"{why_d}; the sparse report itself {'passed' if sparse['pass'] else 'failed'}")


def test_fix_v2_v4_judge_binding():
    """FIX V2: the event report is compared with the events each simulated market USED ('*' resolved), so the same
    times given as a table or as {market: times} are the same events. FIX V4: the null carries exit_key and the judge
    fails the null bar when the null ran another exit, stop, target or other events than the main. FIX V1 in the
    judge: a sparse report fails the truncation bars."""
    bp, sig0 = synth.signal_world("us500", seed=5, edge=0.0004)
    bkp = {"us500": sim.Book(bp, "us500")}

    def ev_clock(d):
        x = d[d.index.hour == 18]
        return pd.DataFrame({"known_at": x.index + pd.Timedelta(hours=1)})
    trs = _tr_fixed(sig0)
    tre = checks.truncation_test(ev_clock, bp, row_len=pd.Timedelta(hours=1))
    ev = ev_clock(bp)
    as_dict = {"us500": pd.DatetimeIndex(ev.known_at)}
    rl = dict(exit=("event", ev, ("hours", 24)), stop=("d20", 1.5))
    rd = dict(exit=("event", as_dict, ("hours", 24)), stop=("d20", 1.5))
    main, maind = sim.simulate(sig0, bkp, **rl), sim.simulate(sig0, bkp, **rd)
    nb = {"s2": sim.simulate(sig0, bkp, exit=("event", ev, ("hours", 24)), stop=("d20", 2.0))}
    evr = sim.simulate(sig0, bkp, mode="every", **rl)
    nl = stats.null_test(main, bkp, n_draws=2000, **rl)
    idea = os.path.join(TMP, "ideas", "950_fixes")
    _declare(idea, {"idea": "950 fixes"})
    kw = dict(ten=TEN, write=False)
    vd = judge.verdict(idea, maind, nb, evr, stats.null_test(maind, bkp, n_draws=2000, **rd), truncation=trs,
                       event_truncation=tre, **kw)
    cols = ["entry_time", "exit_time", "R"]
    check("FIX V2: events given as {market: times} with the table's times: same trades, and the table's event report "
          "binds them (verdict pass)", maind[cols].equals(main[cols]) and vd["verdict"] == "pass",
          f"{vd['verdict']} {vd['failed_bars']}")
    shifted = {"us500": pd.DatetimeIndex(ev.known_at) + pd.Timedelta(hours=1)}
    m_sh = sim.simulate(sig0, bkp, exit=("event", shifted, ("hours", 24)), stop=("d20", 1.5))
    v_sh = judge.verdict(idea, m_sh, nb, evr, stats.null_test(m_sh, bkp, n_draws=2000, exit=("event", shifted, ("hours", 24)),
                                                             stop=("d20", 1.5)), truncation=trs, event_truncation=tre, **kw)
    check("FIX V2: ... but other times per market are still refused", v_sh["failed_bars"] == ["event_truncation_test"],
          str(v_sh["failed_bars"]))
    good = judge.verdict(idea, main, nb, evr, nl, truncation=trs, event_truncation=tre, **kw)
    n_time = stats.null_test(main, bkp, n_draws=2000, exit=("hours", 24), stop=("d20", 1.5))
    n_oth = stats.null_test(main, bkp, n_draws=2000, exit=("event", ev.iloc[::2], ("hours", 24)), stop=("d20", 1.5))
    n_stop = stats.null_test(main, bkp, n_draws=2000, exit=("event", ev, ("hours", 24)), stop=("d20", 3.0))
    n_int = stats.null_test(main, bkp, n_draws=2000, exit=("event", as_dict, ("hours", 24.0)), stop=("d20", 1.5))
    vs = {k: judge.verdict(idea, main, nb, evr, x, truncation=trs, event_truncation=tre, **kw)
          for k, x in (("time", n_time), ("other_events", n_oth), ("stop", n_stop), ("same_as_dict", n_int))}
    check("FIX V4: the null must be run with the main's own exit: a null with the max_hold time exit, other events or "
          "another stop fails the null bar; the same rule written differently (dict events, 24.0 h) is accepted",
          good["verdict"] == "pass" and all(vs[k]["failed_bars"] == ["null>=97.5"] for k in ("time", "other_events", "stop"))
          and vs["same_as_dict"]["verdict"] == "pass" and nl.get("exit_key") == main.attrs.get("exit_key"),
          f"good {good['verdict']}; time {vs['time']['bars']['null>=97.5']['value']}; "
          f"other {vs['other_events']['failed_bars']}; stop {vs['stop']['failed_bars']}; dict {vs['same_as_dict']['verdict']}")
    sp_e = checks.truncation_test(ev_clock, bp, row_len=pd.Timedelta(hours=1), n_signal_cuts=8, n_random_cuts=0)
    d_sp = pd.DataFrame({"side": sig0.side.to_numpy()}, index=pd.DatetimeIndex(sig0.known_at))
    sp_s = checks.truncation_test(lambda x: pd.DataFrame({"known_at": x.index, "side": x.side.to_numpy()}), d_sp,
                                  row_len=pd.Timedelta(0), n_signal_cuts=8, n_random_cuts=0)
    v1 = judge.verdict(idea, main, nb, evr, nl, truncation=sp_s, event_truncation=sp_e, **kw)
    check("FIX V1: the judge refuses passing truncation reports cut too sparsely (signal and event bars fail)",
          sp_e["pass"] and sp_s["pass"] and sorted(v1["failed_bars"]) == ["event_truncation_test", "truncation_test"]
          and "too few" in str(v1["bars"]["event_truncation_test"]["value"]),
          f"{v1['failed_bars']}: {v1['bars']['event_truncation_test']['value']}")


def test_fix_v3_venue_holes():
    """FIX V3: a transient empty venue reply is asked again (the month comes back whole); a hole that persists raises
    DataGap and nothing is cached; allow_holes=True accepts it, records it beside the month and in attrs; a later read
    without allow_holes raises again. Also: a Bitfinex server that sends rows past the bounds no longer stops the
    paging after one page (it returned 300 of 720 hours before)."""
    real = data.http_get
    os.environ["EXPLORE_CACHE"] = os.path.join(TMP, "cache_holes")
    st_ = {"n": 0, "mode": "once"}

    def flaky(url, **kw):
        if "coinbase" in url:
            st_["n"] += 1
            if st_["n"] == 2 or (st_["mode"] == "always" and "start=2019-07-13T12" in url):
                return b"[]"
        return _fake_venues(url, **kw)
    data.http_get = flaky
    try:
        data.lock()
        d1 = data.crypto_h1("coinbase", "btcusd", start="2019-06", end="2019-06-30")
        d1b = data.crypto_h1("coinbase", "btcusd", start="2019-06", end="2019-06-30")
        check("FIX V3: one transient empty Coinbase window is asked again: 720 of 720 hours, also when re-read from the cache",
              len(d1) == 720 and len(d1b) == 720, f"{len(d1)} / {len(d1b)} hours, {st_['n']} calls")
        st_.update(n=10, mode="always")
        mpath = os.path.join(data.cache_dir(), "crypto", "coinbase", "BTC-USD", "1h", "2019-07.csv")
        try:
            data.crypto_h1("coinbase", "btcusd", start="2019-07", end="2019-07-31")
            raised = False
        except data.DataGap:
            raised = not os.path.exists(mpath)            # and nothing was cached
        st_["n"] = 10
        okh = data.crypto_h1("coinbase", "btcusd", start="2019-07", end="2019-07-31", allow_holes=True)
        try:
            data.crypto_h1("coinbase", "btcusd", start="2019-07", end="2019-07-31")
            again = False
        except data.DataGap:
            again = True
        check("FIX V3: a window that stays empty raises DataGap and caches nothing; allow_holes=True accepts the hole, "
              "records it (attrs['holes'], YYYY-MM.holes.json); a later read without allow_holes raises again",
              raised and len(okh) < 744 and okh.attrs.get("holes") and os.path.exists(mpath[:-4] + ".holes.json") and again,
              f"raised {raised}; {len(okh)} hours with allow_holes, holes {okh.attrs.get('holes')}; again {again}")
        data.http_get = _fake_venues
        VBAD["on"] = True
        shutil.rmtree(os.environ["EXPLORE_CACHE"], ignore_errors=True)
        out = {v: data.crypto_h1(v, "ethusd", start="2021-11") for v in ("bitstamp", "bitfinex", "coinbase")}
        hrs = pd.date_range("2021-11-01", "2022-01-01", freq="h", tz="UTC", inclusive="left")
        want = {v: (hrs[(hrs.as_unit("s").asi8 // 3600) % 97 != 0] if v == "bitfinex" else hrs) for v in out}
        check("FIX V3: servers that send rows past the bounds still give every hour of the month (Bitfinex stopped "
              "paging after one page)", all(out[v].index.equals(want[v]) for v in out),
              str({v: len(x) for v, x in out.items()}))
    finally:
        VBAD["on"] = False
        data.http_get = real
        data.lock()


def test_lead_joint_null():
    """Lead (2026-11-18): a basket whose legs are decided at the same time is one bet per day. Four identical legs
    (the extreme case) on pure noise: the plain null, which draws each leg on its own day, passes far too often; the
    same-day null is calibrated. A re-run of the judge does not duplicate trials.jsonl."""
    rng = np.random.default_rng(31)
    keys = ["us500", "us100", "us30", "ger40"]
    pj, pp = [], []
    for w in range(6):
        b = synth.bars("us500", seed=400 + w)
        bk = {k: sim.Book(b, k) for k in keys}                       # the same path under four names
        days = pd.bdate_range("2013-03-01", "2021-12-20", tz="UTC") + pd.Timedelta(hours=15)
        for r in range(10):
            pick = np.sort(rng.choice(len(days), 400, replace=False))
            side = rng.choice([-1, 1], len(pick))
            sg = pd.concat([pd.DataFrame({"known_at": days[pick], "side": side, "market": k}) for k in keys], ignore_index=True)
            rule = dict(exit=("hours", 5), stop=("d20", 2.0))
            m = sim.simulate(sg, bk, **rule)
            nj = stats.null_test(m, bk, n_draws=600, seed=w * 10 + r, **rule)
            pj.append(nj["percentile"])
            pp.append(stats.null_test(m, bk, n_draws=600, seed=w * 10 + r, joint=False, **rule)["percentile"])
    pj, pp = np.array(pj), np.array(pp)
    NUMBERS["null_joint"] = {"rules": len(pj), "ge97.5_joint": int((pj >= 97.5).sum()), "ge97.5_plain": int((pp >= 97.5).sum()),
                             "ks_p_joint": float(st.kstest(pj / 100, "uniform").pvalue),
                             "ks_p_plain": float(st.kstest(pp / 100, "uniform").pvalue), "joint_groups": int(nj["joint_groups"])}
    check("L6: the plain null is too easy for a basket of legs decided together (four identical legs on noise)",
          (pp >= 97.5).sum() >= 5 and NUMBERS["null_joint"]["ks_p_plain"] < 0.01, json.dumps(NUMBERS["null_joint"]))
    check("L6: the same-day null (default for such baskets) is calibrated: about 2.5 % reach 97.5, uniform",
          (pj >= 97.5).sum() <= 5 and NUMBERS["null_joint"]["ks_p_joint"] > 0.001 and 35 < pj.mean() < 65 and
          nj["joint_groups"] > 300 and nj["joint_no_common_day"] == 0)
    one = sim.simulate(sg[sg.market == "us500"], bk, **rule)
    a = stats.null_test(one, bk, n_draws=300, seed=1, **rule)
    b2 = stats.null_test(one, bk, n_draws=300, seed=1, joint=False, **rule)
    check("L6: a table without legs decided together takes the plain path unchanged",
          a["joint_groups"] == 0 and a["percentile"] == b2["percentile"] and a["null_mean"] == b2["null_mean"])
    idea = os.path.join(TMP, "ideas", "912_rerun")
    _declare(idea, {"idea": "912 rerun"})
    for _ in range(2):
        judge.verdict(idea, one, {"n": one}, one, a, corr=0.0, truncation=None, write=True)
    rows = [x for x in open(os.path.join(idea, "trials.jsonl")) if x.strip()]
    check("L7: running the judge twice leaves one set of rows in trials.jsonl", len(rows) == 2, f"{len(rows)} rows")


# ------------------------------------------------------------------ kit v2.1 (2026-11-18): A extra markets, B local-only bars,
# C slow track, D small fixes
XC = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "extra_costs.json")))
XS = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "extra_shape.json")))


def share_cal(start="2019-03-01", end="2019-08-01"):
    """Hourly bar labels of a US share CFD: 09:00 to 15:00 New York (the 09 bar really starts at 09:30), Mon-Fri."""
    t = pd.date_range(start, end, freq="h", tz="UTC", inclusive="left")
    ny = t.tz_convert("America/New_York")
    return t[(ny.dayofweek < 5) & (ny.hour >= 9) & (ny.hour <= 15)]


def flat_share(price=150.0, start="2019-03-01", end="2019-08-01", hr=0.5, idx=None):
    t = share_cal(start, end) if idx is None else idx
    return pd.DataFrame({"open": price, "high": price + hr, "low": price - hr, "close": price, "volume": 60.0}, index=t)


def _xsp(key, price, t, close=False):
    """Hand spread of a kit v2.1 market: the level of the bar's New York year (spread_bps_by_year, else spread_bps;
    oil: spread_abs USD) x price x extra_shape.json (kit v2.1 fix: V21-3, V21-4)."""
    e = XC[key]
    if "spread_abs" in e:
        return e["spread_abs"] * XS["shape_close" if close else "shape"][key][_how(t)]
    tn = pd.Timestamp(t).tz_convert("America/New_York")
    yr = str(tn.year)
    bp = e.get("spread_bps_by_year", {}).get(yr, e["spread_bps"]) * 1e-4
    if tn.hour == 9 and not close and "spread_bps_by_year_h09" in e:     # kit v2.1 fix 2 (KF-5): the 09:30 open's level
        bp = e["spread_bps_by_year_h09"].get(yr, e.get("spread_bps_h09", e["spread_bps"])) * 1e-4
    if close and "spread_bps_by_year_c15" in e:                           # kit v2.1 fix 3 (R3-5): the close levels
        g = "c09" if tn.hour == 9 else "c15" if tn.hour == 15 else "c10_14"
        bp = e[f"spread_bps_by_year_{g}"].get(yr, e.get(f"spread_bps_{g}", e["spread_bps"])) * 1e-4
    return bp * price * XS["shape_close" if close else "shape"][key][_how(t)]


def _xcm(key, mid, adj=1.0):
    """Hand commission per unit per side of a share (kit v2.1 fix, V21-2 and V21-8): max(0.03 x adj, 2 USD x mid /
    stake notional), notional = 5,000 EUR / 6 positions x leverage x 1.15 USD per EUR."""
    e = XC[key]
    st = XC["_stake"]
    n = st["account_eur"] / st["positions"] * e["leverage"] * st["usd_per_eur"]
    return max(e["commission_per_unit"] * adj, e["min_commission_per_side"] * mid / n)


def test_v21_costs_by_hand():
    """A: the new markets' costs by hand: a share round trip with the per-unit commission across the Friday triple-swap
    night (long and short; net, stress, gross; costs.round_trip and the simulator), the split-adjusted commission, oil
    (long over a weekday night, short over the weekend), D20 with 7-bar share days, nothing changed for the 16."""
    check("A: extra_costs.json adds oil and the 40 shares, every entry provisional with its source; fp_costs.json's 16 "
          "markets are untouched and not provisional; a pair with a share leg is provisional",
          sorted(costs.SPEC) == sorted(k for k in FPC if not k.startswith("_")) and len(costs.EXTRA) == 41 and
          "oil" in costs.EXTRA and all(costs.is_provisional(k) and costs.EXTRA[k]["source"] for k in costs.EXTRA) and
          not any(costs.is_provisional(k) for k in costs.SPEC) and not set(costs.SPEC) & set(costs.EXTRA) and
          costs.is_provisional(costs.register_pair("jpm/xom", "jpm", "xom")["pair"]["legs"][0]) and
          costs.spec("jpm/xom").get("provisional") is True and costs.spec("jpm/xom")["min_day_bars"] == 7,
          f"{len(costs.EXTRA)} extra markets")
    key, P = "jpm", 150.0
    ti, to = U("2019-06-13 14:00"), U("2019-06-17 14:00")      # Thursday 10:00 NY -> Monday 10:00 NY
    e = XC[key]
    sm = e["slip_mkt_bps"] * 1e-4
    nights = int(costs.swap_nights(pd.DatetimeIndex([ti]), pd.DatetimeIndex([to]), "Fri")[0])
    # costs.round_trip at mids: spread in bp of the mid x shape, + 0.02 per side, slippage after, swap rate x fill x 4
    rows, ok = [], nights == 4
    for side in (1, -1):
        for sc, k in (("net", 1.0), ("stress", 1.5), ("gross", 0.0)):
            si, so = _xsp(key, P, ti) * k, _xsp(key, P, to) * k
            c = _xcm(key, P) * k
            sl = sm * (k if sc != "gross" else 0.0)
            if side > 0:
                fill, out = (P + si / 2 + c) * (1 + sl), (P - so / 2 - c) * (1 - sl)
                sw = e["swap_long"] / 360 * fill * 4
            else:
                fill, out = (P - si / 2 - c) * (1 - sl), (P + so / 2 + c) * (1 + sl)
                sw = e["swap_short"] / 360 * fill * 4
            sw = 0.0 if sc == "gross" else sw
            want = side * (P - P) - (side * (out - fill) - sw)
            r = costs.round_trip(key, side, P, P, ti, to, scenario=sc)
            ok &= abs(r["cost"] - want) < 1e-10 and abs(r["commission_per_side"] - c) < 1e-15
            rows.append(f"{'long' if side > 0 else 'short'} {sc} {r['cost_bp']:.2f} bp")
    check("A: share round trip by hand (costs.round_trip): quoted spread bp of the year x shape, + max(0.03 USD per share, "
          "2 USD per order at the stake notional) per side on top of the half spread (x1.5 stress, 0 gross), 1 bp "
          "slippage, swap 7 % long / 3 % short x 4 nights (Fri triple)",
          ok, "; ".join(rows))
    # the simulator on flat BID share bars: ask = bid + spread + commission; exit 2 business days later (Thu -> Mon)
    b = flat_share(P)
    out_ok, info = True, []
    for side in (1, -1):
        t = sim.simulate(pd.DataFrame({"known_at": [ti], "side": [side]}), b, market=key, exit=("bdays", 2), stop=("bps", 500))
        si, so = _xsp(key, P, ti), _xsp(key, P, to)
        mi, mo = P + si / 2, P + so / 2
        ci, co = _xcm(key, mi), _xcm(key, mo)
        if side > 0:
            fill, ex = (P + si + ci) * (1 + sm), (P - co) * (1 - sm)
            sw = e["swap_long"] / 360 * fill * 4
        else:
            fill, ex = (P - ci) * (1 - sm), (P + so + co) * (1 + sm)
            sw = e["swap_short"] / 360 * fill * 4
        pnl = side * (ex - fill) - sw
        out_ok &= (len(t) == 1 and t.exit_time[0] == to and t.reason[0] == "time" and abs(t.entry_px[0] - fill) < 1e-10
                   and abs(t.exit_px[0] - ex) < 1e-10 and abs(t.net_bp[0] - pnl / fill * 1e4) < 1e-8
                   and abs(t.swap_bp[0] - sw / fill * 1e4) < 1e-8 and abs(t.gross_bp[0] - side * (mo - mi) / mi * 1e4) < 1e-8
                   and abs(t.R[0] - pnl / (0.05 * mi)) < 1e-9 and t.hold_tdays[0] == 2)
        fs = (mi + 1.5 * si / 2 + 1.5 * ci) * (1 + 1.5 * sm) if side > 0 else (mi - 1.5 * si / 2 - 1.5 * ci) * (1 - 1.5 * sm)
        xs = (mo - 1.5 * so / 2 - 1.5 * co) * (1 - 1.5 * sm) if side > 0 else (mo + 1.5 * so / 2 + 1.5 * co) * (1 + 1.5 * sm)
        sws = (e["swap_long"] if side > 0 else e["swap_short"]) / 360 * fs * 4
        out_ok &= abs(t.stress_bp[0] - (side * (xs - fs) - sws) / fs * 1e4) < 1e-8
        info.append(f"{'long' if side > 0 else 'short'} net {t.net_bp[0]:.2f} bp, stress {t.stress_bp[0]:.2f} bp")
    check("A: the simulator charges the same on BID share bars (ask = bid + spread + commission, bid side - commission, "
          "the commission at each side's mid; stress commission and spread x1.5); hold 2 trading days, 4 swap nights",
          out_ok, "; ".join(info))
    # split-adjusted commission: aapl bars back-adjusted for the 2020-08-31 4:1 split (price 10: the per-share rate binds)
    ab = flat_share(10.0, "2020-06-01", "2020-10-01")
    t1 = U("2020-08-20 14:00")
    t2 = U("2020-09-10 14:00")
    tr = sim.simulate(pd.DataFrame({"known_at": [t1, t2], "side": [1, 1]}), ab, market="aapl", exit=("hours", 2),
                      stop=("bps", 500), mode="every")
    sm_a = XC["aapl"]["slip_mkt_bps"] * 1e-4
    want = [(10 + _xsp("aapl", 10, t1) + _xcm("aapl", 10 + _xsp("aapl", 10, t1) / 2, 0.25)) * (1 + sm_a),
            (10 + _xsp("aapl", 10, t2) + _xcm("aapl", 10 + _xsp("aapl", 10, t2) / 2, 1.0)) * (1 + sm_a)]
    raw = ab.copy()
    raw.loc[raw.index < pd.Timestamp("2020-08-31", tz="America/New_York"), ["open", "high", "low", "close"]] *= 4
    try:
        sim.Book(raw, "aapl")
        refused = False
    except ValueError:
        refused = True
    check("A: before a 4:1 split one adjusted unit pays a quarter of the per-share commission (0.0075, then 0.03 after "
          "it, where the per-share rate binds); raw share bars that still jump by the split ratio are refused",
          abs(tr.entry_px[0] - want[0]) < 1e-10 and abs(tr.entry_px[1] - want[1]) < 1e-10 and refused,
          f"fills {tr.entry_px[0]:.5f} / {tr.entry_px[1]:.5f}")
    # oil: FP spread in bp of the reference price, flat shape, 0.5 bp slippage, swaps 6 % long / 4 % short, triple Fri
    ob = data.fp_hours("oil", pd.DataFrame({"open": 60.0, "high": 60.3, "low": 59.7, "close": 60.0, "volume": 60.0},
                                           index=synth.calendar("index", "2019-03-01", "2019-08-01")))
    o = XC["oil"]
    ta, tb = U("2019-06-12 14:00"), U("2019-06-14 14:00")       # Wednesday 10:00 NY, Friday 10:00 NY
    # kit v2.1 fix 2 (KF-3, KF-8; amended): oil bars given to sim.Book are back-adjusted bars, so the 0.05 USD spread
    # is x the bar's roll adjustment (the listed ratios after it; the same for ta and tb, no roll between them), and
    # costs.round_trip's adj defaults to it. The check passed before only because the old roll table was empty here.
    s0 = o["spread"] / o["spread_ref_price"] * 60.0 * float(data.price_factor("oil", pd.DatetimeIndex([ta]))[0])
    so_ = o["slip_mkt_bps"] * 1e-4
    tt = sim.simulate(pd.DataFrame({"known_at": [ta, tb], "side": [1, -1]}), ob, market="oil", exit=("bdays", 1),
                      stop=("bps", 500), mode="every")
    fl = (60 + s0) * (1 + so_); xl = 60 * (1 - so_); swl = o["swap_long"] / 360 * fl * 1
    fs = 60 * (1 - so_); xs = (60 + s0) * (1 + so_); sws = o["swap_short"] / 360 * fs * 3
    r_oil = costs.round_trip("oil", 1, 60.0, 60.0, ta, ta + pd.Timedelta(days=1))
    check("A: oil by hand: 0.05 USD at 60 (bp of the reference price, flat shape), 0.5 bp slippage; long Wed -> Thu 1 "
          "night at 6 %, short Fri -> Mon 3 nights (Fri triple) at 4 %",
          abs(tt.net_bp[0] - (xl - fl - swl) / fl * 1e4) < 1e-8 and abs(tt.net_bp[1] - (fs - xs - sws) / fs * 1e4) < 1e-8
          and abs(r_oil["cost"] - ((60 + s0 / 2) * (1 + so_) - (60 - s0 / 2) * (1 - so_) + 0.06 / 360 * (60 + s0 / 2) * (1 + so_)))
          < 1e-10 and not costs.is_provisional("xauusd"), f"long {tt.net_bp[0]:.2f} bp, short {tt.net_bp[1]:.2f} bp")
    # a hedged pair of two shares: each leg pays its own spread, commission and slippage, swaps of the side held
    pa, pb_ = 150.0, 80.0
    pbk = sim.pair_book("jpm/xom", "jpm", "xom", flat_share(pa), flat_share(pb_))
    tp = sim.simulate(pd.DataFrame({"known_at": [ti], "side": [1], "market": "jpm/xom"}), {"jpm/xom": pbk},
                      exit=("bdays", 2), stop=("bps", 500))
    res = 0.0
    for k_, p_, s_ in (("jpm", pa, 1), ("xom", pb_, -1)):
        sl_ = XC[k_]["slip_mkt_bps"] * 1e-4
        si, so = _xsp(k_, p_, ti), _xsp(k_, p_, to)
        ci, co = _xcm(k_, p_ + si / 2), _xcm(k_, p_ + so / 2)
        fill = (p_ + si + ci) * (1 + sl_) if s_ > 0 else (p_ - ci) * (1 - sl_)
        ex = (p_ - co) * (1 - sl_) if s_ > 0 else (p_ + so + co) * (1 + sl_)
        res += s_ * (ex / fill - 1) - (XC[k_]["swap_long"] if s_ > 0 else XC[k_]["swap_short"]) / 360 * 4
    rtp = costs.pair_round_trip("jpm/xom", 1, (pa, pb_), (pa, pb_), ti, to)
    check("A: a pair of two shares by hand: each leg's spread, commission per side (at each side's mid) and slippage, swaps of the side "
          "held over 4 nights; simulator and costs.pair_round_trip agree; D20 of the pair on 7-bar days",
          len(tp) == 1 and abs(tp.net_bp[0] - res * 1e4) < 1e-8 and abs(rtp["net"] - res) < 1e-12 and rtp["nights"] == 4,
          f"{tp.net_bp[0]:.2f} bp" if len(tp) else "no trade")
    bk7 = sim.Book(b, key)
    bk10 = sim.Book(b, key, min_day_bars=10)
    q = bk7.d20(np.array([U("2019-07-15 14:00").value]))[0]
    check("A: D20 of a share uses 7-bar days (its cost entry's min_day_bars); with the default 10 it would never exist; "
          "the 16 markets keep 10", costs.min_day_bars("jpm") == 7 and costs.min_day_bars("xauusd") == 10 and
          abs(q - 1.0) < 1e-12 and bk10.d20(np.array([U("2019-07-15 14:00").value]))[0] != bk10.d20(np.array([U("2019-07-15 14:00").value]))[0]
          and bk7.day_ranges.n.max() == 7, f"D20 {q}")


def test_v21_local_markets():
    """B: local-only markets: read from prepared files only (no request), cut by the lock, validation years from
    '<dir>_val' after unlock, clear errors when a file is absent; shares back-adjusted for splits (no adjustment column
    handed to a build), an unlisted split-like jump refused, a read past the checked splits refused."""
    h1 = os.path.join(TMP, "h1_v21")
    os.makedirs(h1, exist_ok=True)
    os.makedirs(h1 + "_val", exist_ok=True)
    jp = XC["jpm"]["ref_price"]
    f = flat_share(jp, "2019-01-01", "2022-03-01")              # holds 2022 rows on purpose
    f.index.name = "time"
    f.to_parquet(os.path.join(h1, "jpm.parquet"))
    fv = flat_share(jp * 1.1, "2022-01-01", "2026-02-01")       # holds 2026 rows on purpose
    fv.index.name = "time"
    fv.to_parquet(os.path.join(h1 + "_val", "jpm.parquet"))
    a = flat_share(130.0, "2020-06-01", "2020-12-01")
    a.loc[a.index < pd.Timestamp("2020-08-31", tz="America/New_York"), ["open", "high", "low", "close"]] *= 4
    a.index.name = "time"
    a.to_parquet(os.path.join(h1, "aapl.parquet"))              # raw: the 4:1 split shows as an overnight jump
    x = flat_share(XC["xom"]["ref_price"], "2020-06-01", "2020-12-01")
    x.loc[x.index < pd.Timestamp("2020-10-05", tz="America/New_York"), ["open", "high", "low", "close"]] *= 2
    x.index.name = "time"
    x.to_parquet(os.path.join(h1, "xom.parquet"))               # a 2:1 jump that no split explains
    oi = synth.calendar("index", "2019-01-01", "2022-03-01")
    ofr = pd.DataFrame({"open": 57.0, "high": 57.2, "low": 56.8, "close": 57.0, "volume": 60.0}, index=oi)
    ofr.index.name = "time"
    ofr.to_parquet(os.path.join(h1, "oil.parquet"))
    real = data.http_get

    def no_net(url, **kw):
        raise AssertionError("a local-only market made a request: " + url)
    data.http_get = no_net
    os.environ["EXPLORE_H1_DIR"] = h1
    try:
        data.lock()
        j = data.load_bars("jpm", 2019)
        o = data.load_bars("oil", 2019)
        ad = data.load_bars("aapl", 2020)
        r = data.overnight_ratios(ad)
        bk = sim.Book(ad, "aapl")
        check("B: local-only markets load from the prepared file with no request, < 2022 while locked, price_is 'bid'; a "
              "share is back-adjusted for its split (no overnight jump left, OHLCV columns only, commission scaled in Book)",
              j.index.max() < U("2022-01-01") and o.index.max() < U("2022-01-01") and j.attrs["price_is"] == "bid" and
              list(ad.columns) == ["open", "high", "low", "close", "volume"] and float(r.max()) < 1.001 and
              float(r.min()) > 0.999 and ad.attrs.get("splits_applied") == {"2020-08-31": 4.0} and
              abs(float(ad.close.iloc[0]) - 130.0) < 1e-9 and abs(bk.comm[0] - _xcm("aapl", bk.mid["o"][0], 0.25)) < 1e-15 and
              abs(bk.comm[-1] - _xcm("aapl", bk.mid["o"][-1], 1.0)) < 1e-15 and
              data.fp_markets()["jpm"]["source"] == "local", f"{len(j)} jpm bars, {len(o)} oil bars")
        errs = []
        for k, exc in (("msft", FileNotFoundError), ("xom", data.DataGap)):
            try:
                data.load_bars(k, 2019)
                errs.append(f"{k}: no error")
            except exc as ex_:
                errs.append("ok" if (k != "msft" or "no download path" in str(ex_)) else str(ex_))
        try:
            data.load_bars("oil", venue="bitstamp")
            errs.append("venue accepted")
        except ValueError:
            errs.append("ok")
        check("B: an absent prepared file raises FileNotFoundError with a clear message (no download path); an unlisted "
              "split-like jump raises DataGap; venue= is refused", errs == ["ok"] * 3, str(errs))
        idea = os.path.join(TMP, "ideas", "960_local")
        os.makedirs(idea, exist_ok=True)
        json.dump(VALDECL, open(os.path.join(idea, "val_declared.json"), "w"))
        json.dump({"verdict": "pass"}, open(os.path.join(idea, "results.json"), "w"))
        data.unlock_val(idea)
        try:
            data.load_bars("oil", 2019)
            e_oil = False
        except FileNotFoundError as ex_:
            e_oil = "_val" in str(ex_)
        ofv = ofr[ofr.index >= U("2022-01-01")].copy()
        ofv = pd.concat([ofv, pd.DataFrame({"open": 57.0, "high": 57.2, "low": 56.8, "close": 57.0, "volume": 60.0},
                                           index=pd.date_range("2022-03-01", "2026-02-01", freq="h", tz="UTC"))])
        ofv.index.name = "time"
        ofv.to_parquet(os.path.join(h1 + "_val", "oil.parquet"))
        ou = data.load_bars("oil", 2019)
        try:
            data.load_bars("jpm", 2019)
            e_split = False
        except data.PeriodError:
            e_split = True
        data.lock()
        check("B: after unlock_val the validation years come from '<dir>_val' (absent: FileNotFoundError naming it), never "
              "2026; a share is refused past its checked splits (2021-12-31) until the later splits are listed",
              e_oil and ou.index.max() < U("2026-01-01") and ou.index.max() >= U("2025-12-31") and e_split,
              f"oil unlocked last {ou.index.max()}")
    finally:
        data.http_get = real
        os.environ.pop("EXPLORE_H1_DIR", None)
        data.lock()


def test_v21_share_traps():
    """B traps: on the share calendar (first bar labelled 09:00, opens 09:30), a signal stamped at the 09 bar's label
    but computed from its close is caught by the truncation test; stamped at the bar's end it has no edge."""
    rw = synth.bars("eurusd", seed=17, vol_h=0.004)
    ny = rw.index.tz_convert("America/New_York")
    b = rw[(ny.dayofweek < 5) & (ny.hour >= 9) & (ny.hour <= 15)].copy()
    b[["open", "high", "low", "close"]] *= XC["jpm"]["ref_price"] / 1.15
    bk = {"jpm": sim.Book(b, "jpm")}

    def first_bar(d):
        n = d.index.tz_convert("America/New_York")
        return d[n.hour == 9]

    def bad(d):
        x = first_bar(d)
        return pd.DataFrame({"known_at": x.index, "side": np.sign(x.close - x.open).replace(0, 1).astype(int).to_numpy()})

    def good(d):
        x = first_bar(d)
        return pd.DataFrame({"known_at": x.index + pd.Timedelta(hours=1),
                             "side": np.sign(x.close - x.open).replace(0, 1).astype(int).to_numpy()})
    tb, tg = checks.truncation_test(bad, b), checks.truncation_test(good, b)
    rb = sim.simulate(bad(b).assign(market="jpm"), bk, exit=("hours", 1), stop=("d20", 2.0))
    rg = sim.simulate(good(b).assign(market="jpm"), bk, exit=("hours", 1), stop=("d20", 2.0))
    check("B trap: a share signal stamped at the first bar's label (09:00, really 09:30) using that bar's close is caught "
          "by the truncation test; stamped at the bar's end (10:00) it passes and has no edge",
          not tb["pass"] and tg["pass"] and stats.t_stat(rb.R_gross) > 10 and abs(stats.t_stat(rg.R_gross)) < 3.5,
          f"t gross bad {stats.t_stat(rb.R_gross):.1f}, good {stats.t_stat(rg.R_gross):.2f}; entries of the good signals "
          f"at {sorted(set(pd.DatetimeIndex(rg.entry_time).tz_convert('America/New_York').hour))} NY")


def test_v21_slow_track_and_provisional():
    """C: max_hold_tdays (5 by default, 40 on the slow track, above 40 raises): bar name and text follow it, results.json
    records it, the ledger line says 'slow track'; a market with provisional costs puts PROVISIONAL COSTS in the ledger
    line and results.json; the sizing reports the share minimum commission."""
    b, sig = synth.signal_world("us500", seed=5, edge=0.0004)
    bk = {"us500": sim.Book(b, "us500")}
    rule = dict(exit=("bdays", 12), stop=("d20", 4.0))
    main = sim.simulate(sig, bk, **rule)
    idea = os.path.join(TMP, "ideas", "970_slow")
    _declare(idea, {"idea": "970 slow", "track": "slow"})
    nl = stats.null_test(main, bk, n_draws=300, **rule)
    kw = dict(corr=0.0, truncation=_tr_fixed(sig), ledger=LEDGER_FIXED)
    v5 = judge.verdict(idea, main, {"a": main}, main, nl, write=False, **kw)
    v40 = judge.verdict(idea, main, {"a": main}, main, nl, write=True, max_hold_tdays=40, **kw)
    rj = json.load(open(os.path.join(idea, "results.json")))
    bad = []
    for x in (41, 0, 4.5, True, "40", 7, 30):
        try:
            judge.verdict(idea, main, {"a": main}, main, nl, write=False, max_hold_tdays=x, **kw)
            bad.append(x)
        except ValueError:
            pass
    check("C: slow track: a 12-day hold fails 'hold<=5d' by default and passes 'hold<=40d' with max_hold_tdays=40; the "
          "ledger line says 'slow track'; results.json records 40; 41, 0, 4.5, True, '40', 7 and 30 raise",
          "hold<=5d" in v5["failed_bars"] and "hold<=40d" in v40["bars"] and v40["bars"]["hold<=40d"]["pass"] and
          "hold<=5d" not in v40["bars"] and "slow track (hold<=40d)" in v40["ledger_line"] and
          "slow track" not in v5["ledger_line"] and rj["max_hold_tdays"] == 40 and rj["slow_track"] is True and
          v5["max_hold_tdays"] == 5 and not bad, f"max hold {v40['main']['hold_tdays_max']} days; refused all but {bad}")
    # provisional: a share basket on flat-ish synthetic share bars
    rw = synth.bars("eurusd", seed=23)
    ny = rw.index.tz_convert("America/New_York")
    sb = rw[(ny.dayofweek < 5) & (ny.hour >= 9) & (ny.hour <= 15)].copy()
    sb[["open", "high", "low", "close"]] *= 100.0
    bks = {"jpm": sim.Book(sb, "jpm")}
    days = pd.bdate_range("2013-03-01", "2021-12-20", tz="UTC") + pd.Timedelta(hours=15)
    sg = pd.DataFrame({"known_at": days, "side": 1, "market": "jpm"})
    ms = sim.simulate(sg, bks, exit=("hours", 3), stop=("d20", 1.0))
    vp = judge.verdict(idea, ms, None, None, None, corr=0.0, write=False, ledger=LEDGER_FIXED)
    vu = judge.verdict(idea, main, None, None, None, corr=0.0, write=False, ledger=LEDGER_FIXED)
    szj = vp["sizing"]["by_market"]["jpm"]
    n_st = 5000.0 / 6 * 5 * 1.15
    pxm = float(ms.entry_px.median())
    check("C: PROVISIONAL COSTS in the ledger line and results.json for a share; absent for us500; the sizing reports the "
          "2 USD minimum commission per side as MODELLED at the stake notional (4,791.67 USD) and the extra cost at a "
          "1,000 EUR account",
          "PROVISIONAL COSTS (jpm)" in vp["ledger_line"] and vp["provisional_costs"] is True and
          vp["costs"].startswith("PROVISIONAL COSTS") and "PROVISIONAL" not in vu["ledger_line"] and
          vu["provisional_costs"] is False and szj["min_commission_per_side"] == 2.0 and szj["min_commission_modelled"]
          and abs(szj["trade_notional_usd"] - n_st) < 1e-9 and
          abs(szj["commission_bp_round_trip_modelled"] - 2 * max(2.0, 0.03 * n_st / pxm) / n_st * 1e4) < 1e-9 and
          abs(szj["extra_cost_bp_round_trip_at_1000_eur_account"] - (2 * max(2.0, 0.03 * n_st / 5 / pxm) / (n_st / 5)
                                                                      - 2 * max(2.0, 0.03 * n_st / pxm) / n_st) * 1e4) < 1e-9,
          f"{vp['ledger_line'][:160]} ... sizing {json.dumps({k: (round(v, 2) if isinstance(v, float) else v) for k, v in szj.items() if k != 'note'})}")


def test_v21_small_fixes():
    """D: several rows known at the same time (external keep='all', event_table, asof_join agg); shift_test passes
    max_wait_h through; max_market_share reads 'n/a (total profit <= 0)' instead of inf."""
    obs = pd.DatetimeIndex(["2020-01-02", "2020-01-02", "2020-01-02", "2020-01-03"])
    vals = np.array([1.0, 2.0, 3.0, 4.0])
    rule = data.rule_next_bday_utc(13, 1)
    d1 = data.external(obs, vals, known=rule, min_lag=pd.Timedelta(hours=12))
    da = data.external(obs, vals, known=rule, min_lag=pd.Timedelta(hours=12), keep="all")
    t = pd.DatetimeIndex([U("2020-01-03 13:00"), U("2020-01-06 13:00")])
    ok1 = (list(d1.to_numpy()) == [3.0, 4.0] and list(da.to_numpy()) == [1.0, 2.0, 3.0, 4.0] and
           list(data.asof_join(t, da)) == [3.0, 4.0] and list(data.asof_join(t, da, agg="sum")) == [6.0, 4.0] and
           list(data.asof_join(t, da, agg="count")) == [3.0, 1.0] and list(data.asof_join(t, d1)) == [3.0, 4.0])
    ev = data.event_table(obs, known=rule, min_lag=pd.Timedelta(hours=12), market=["aapl", "msft", "jpm", "aapl"],
                          surprise=vals)
    try:
        data.event_table(obs, known=lambda d: data.known_at(d, time="09:00", tz="UTC"), min_lag=pd.Timedelta(hours=12),
                         market=["a"] * 4)
        leak = False
    except ValueError:
        leak = True
    late = data.event_table(pd.DatetimeIndex(["2021-12-30", "2021-12-31"]), known=rule, min_lag=pd.Timedelta(hours=12),
                            market=["a", "b"])
    rep = checks.truncation_test(lambda dd: pd.DataFrame({"known_at": dd.index, "market": dd.market.to_numpy()}), ev,
                                 row_len=pd.Timedelta(0))
    check("D: several rows known at the same time: external keep='all' keeps them in order (the default still keeps the "
          "last); asof_join combines them (agg); event_table keeps labelled events, enforces the lag, cuts at the period end",
          ok1 and list(ev.market) == ["aapl", "msft", "jpm", "aapl"] and ev.index[0] == ev.index[2] and
          list(ev.surprise) == [1.0, 2.0, 3.0, 4.0] and leak and len(late) == 1 and rep["pass"],
          f"{len(ev)} events, {ev.index.nunique()} known-at times")
    b = flat("eurusd")
    sg = pd.DataFrame({"known_at": [U("2019-06-15 12:00"), U("2019-06-12 10:00")], "side": [1, 1], "market": "eurusd"})
    sh = checks.shift_test(sg, {"eurusd": sim.Book(b, "eurusd")}, max_wait_h=2, exit=("hours", 3), stop=("d20", 1.0))
    sh0 = checks.shift_test(sg, {"eurusd": sim.Book(b, "eurusd")}, exit=("hours", 3), stop=("d20", 1.0))
    check("D: shift_test passes max_wait_h to both runs (a Saturday signal is stale in both; without it both take it)",
          sh["base"]["stale"] == 1 and sh["shifted"]["stale"] == 1 and sh["base"]["n"] == 1 and sh["shifted"]["n"] == 1
          and sh0["base"]["n"] == 2 and sh0["shifted"]["n"] == 2 and sh["max_wait_h"] == 2, json.dumps(sh))
    b1, s1 = synth.signal_world("us500", seed=31, edge=0.0)
    b2, s2 = synth.signal_world("ger40", seed=32, edge=0.0)
    bkb = sim.books({"us500": b1, "ger40": b2})
    m = sim.simulate(pd.concat([s1, s2], ignore_index=True), bkb, exit=("hours", 5), stop=("d20", 1.5))
    neg = m.copy()
    neg["R"] = -neg.R.abs()
    neg.attrs.update(m.attrs)
    vb = judge.verdict(TMP, neg, None, None, None, corr=0.0, write=False, ledger=LEDGER_FIXED)
    bar = [v for k_, v in vb["bars"].items() if k_.startswith("max_market_share")][0]
    check("D: the basket's max_market_share bar reads 'n/a (total profit <= 0)' (not inf) and fails",
          bar["value"] == "n/a (total profit <= 0)" and bar["pass"] is False, str(bar))


def _try(name, fn):
    """Run one review-fix check; an exception (an API the kit lacks before the fix) is a FAIL, not a crash."""
    try:
        ok, info = fn()
    except Exception as e:      # noqa: BLE001
        ok, info = False, f"raised {e!r}"[:300]
    check(name, ok, info)


def _hourly_ix(start, end):
    return pd.date_range(start, end, freq="h", tz="UTC", inclusive="left")


def test_v21_review_fixes():
    """Kit v2.1 fix (2026-11-18): one check (or more) per verifier issue V21-1..V21-8; each fails on the kit before
    the fix (scratch kit_v21/fix/kit_before)."""
    h1 = os.path.join(TMP, "h1_fix")
    os.makedirs(h1, exist_ok=True)
    os.makedirs(h1 + "_val", exist_ok=True)
    real = data.http_get

    def no_net(url, **kw):
        raise AssertionError("a local-only market made a request: " + url)
    data.http_get = no_net
    os.environ["EXPLORE_H1_DIR"] = h1
    try:
        data.lock()
        # ---------------- V21-1: oil contract rolls
        rolls = XC["oil"].get("rolls", {})
        r19 = sorted(k for k in rolls if k.startswith("2019-06"))
        rt = pd.Timestamp(r19[0]) if r19 else U("2019-06-16 22:00")
        q = float(rolls.get(r19[0], 1.06)) if r19 else 1.06
        ix = _hourly_ix("2019-01-01", "2019-12-01")
        ix = ix[ix.tz_convert("America/New_York").dayofweek < 5]
        # kit v2.1 fix 2 (KF-1): the listed ratios are applied (not measured on the bars), so the synthetic vendor bars
        # jump at EVERY listed roll of their span (amended: they jumped at the 2019-06 roll only)
        span19 = {pd.Timestamp(k): float(v) for k, v in rolls.items() if ix[0] <= pd.Timestamp(k) < ix[-1]} or {rt: q}
        ix = ix.union(pd.DatetimeIndex([r_ for r_ in span19 if r_ not in ix]))
        raw = pd.DataFrame({"open": 57.0, "high": 57.2, "low": 56.8, "close": 57.0, "volume": 60.0}, index=ix)
        for r_, q_ in span19.items():
            raw.loc[raw.index >= r_, ["open", "high", "low", "close"]] *= q_      # the vendor's roll jumps
        raw.index.name = "time"
        raw.to_parquet(os.path.join(h1, "oil.parquet"))
        P_after = float(np.prod([float(v) for k, v in rolls.items() if pd.Timestamp(k) > ix[0]])) if rolls else q

        def v1a():
            o = data.load_bars("oil", 2019)
            i = int(o.index.searchsorted(rt))
            jump = float(o.open.iloc[i] / o.close.iloc[i - 1])
            others = max(abs(float(o.open.iloc[int(o.index.searchsorted(r_))] / o.close.iloc[int(o.index.searchsorted(r_)) - 1]) - 1)
                         for r_ in span19)
            before = float(o.close.iloc[0])
            return (abs(jump - 1) < 1e-12 and others < 1e-12 and abs(before - 57.0 * P_after) < 1e-9 and
                    abs(float(o.close.iloc[-1]) - 57.0 * P_after) < 1e-9 and len(rolls) == 108 and
                    XC["oil"].get("rolls_checked_to") == "2021-12-31",
                    f"listed rolls {len(rolls)}; jump at {rt} {jump:.6f} (raw {q}); first close {before:.4f}")
        _try("V21-1: oil's contract-roll jumps are back-adjusted by load_bars (108 listed rolls 2013-2021, one a month): "
             "no jump left at the roll reopen, earlier prices x the roll ratio", v1a)

        def v1b():
            o = data.load_bars("oil", 2019)
            bko = sim.Book(o, "oil")
            sg = pd.DataFrame({"known_at": [rt - pd.Timedelta(hours=30)], "side": [1], "market": "oil"})
            ta = sim.simulate(sg, {"oil": bko}, exit=("bdays", 3), stop=("bps", 2000))
            try:
                sim.Book(raw, "oil")
                refused = False
            except ValueError:
                refused = True
            g = float(ta.gross_bp.iloc[0]) if len(ta) else float("nan")
            return (refused and abs(g) < 0.5 and abs(float(bko.s[0]) - 0.05 * P_after) < 1e-12,
                    f"long held across the roll: gross {g:.4f} bp (raw bars would book {1e4 * (q - 1):.1f} bp); raw bars "
                    f"refused {refused}; spread before the roll {float(bko.s[0]):.5f} = 0.05 USD x ratio")
        _try("V21-1: a long held across a roll books no fake gain on the adjusted bars; raw oil bars that still jump by "
             "a listed roll are refused by sim.Book; the absolute spread follows the adjustment", v1b)

        def v1c():
            idea = os.path.join(TMP, "ideas", "980_fix_val")
            os.makedirs(idea, exist_ok=True)
            json.dump(VALDECL, open(os.path.join(idea, "val_declared.json"), "w"))
            json.dump({"verdict": "pass"}, open(os.path.join(idea, "results.json"), "w"))
            e = data.cl_expiry(2023, 3)
            x = e - pd.Timedelta(days=1)
            while x.weekday() >= 5:
                x -= pd.Timedelta(days=1)
            tr = (x - pd.Timedelta(days=1) + pd.Timedelta(hours=18)).tz_localize("America/New_York").tz_convert("UTC")
            iv = _hourly_ix("2022-01-01", "2026-02-01")
            iv = iv[iv.tz_convert("America/New_York").dayofweek < 5]
            v = pd.DataFrame({"open": 60.0, "high": 60.2, "low": 59.8, "close": 60.0, "volume": 60.0}, index=iv)
            v.loc[v.index >= tr, ["open", "high", "low", "close"]] *= 1.04
            v.index.name = "time"
            v.to_parquet(os.path.join(h1 + "_val", "oil.parquet"))
            data.unlock_val(idea)
            try:
                o = data.load_bars("oil", 2019)
            finally:
                data.lock()
            i = int(o.index.searchsorted(tr))
            jump = float(o.open.iloc[i] / o.close.iloc[i - 1])
            return (abs(jump - 1) < 1e-12 and o.index.max() < U("2026-01-01") and str(e.date()) == "2023-03-21",
                    f"CL expiry 2023-03 {e.date()}, rule reopen {tr}, jump left {jump:.6f}")
        _try("V21-1: after the listed years (validation) the roll is found by the CL expiry rule (reopen of the trading day "
             "one business day before the last trading day) and removed the same way", v1c)

        # ---------------- V21-7: half-day one-minute bar dropped
        d = flat_share(XC["jpm"]["ref_price"], "2019-11-01", "2019-12-10")
        nyd = d.index.tz_convert("America/New_York")
        hd = (nyd.normalize().tz_localize(None) == pd.Timestamp("2019-11-29"))
        d = d[~hd | (nyd.hour <= 13)]
        d = pd.concat([d, pd.DataFrame({"open": d.open.iloc[0], "high": d.high.iloc[0], "low": d.low.iloc[0],
                                        "close": d.close.iloc[0], "volume": 1.0},
                                       index=pd.DatetimeIndex([pd.Timestamp("2019-11-29 13:00", tz="America/New_York")
                                                               .tz_convert("UTC")]))]).sort_index()
        d = d[~d.index.duplicated(keep="last")]
        d.loc[d.index == pd.Timestamp("2019-11-29 13:00", tz="America/New_York").tz_convert("UTC"), "volume"] = 1.0
        d.index.name = "time"
        d.to_parquet(os.path.join(h1, "jpm.parquet"))

        def v7():
            j = data.load_bars("jpm", 2019)
            t13 = pd.Timestamp("2019-11-29 13:00", tz="America/New_York").tz_convert("UTC")
            sg = pd.DataFrame({"known_at": [pd.Timestamp("2019-11-29 12:30", tz="America/New_York").tz_convert("UTC")],
                               "side": [1], "market": "jpm"})
            tr_ = sim.simulate(sg, {"jpm": sim.Book(j, "jpm")}, exit=("hours", 1), stop=("bps", 500))
            ent = pd.Timestamp(tr_.entry_time.iloc[0]).tz_convert("America/New_York") if len(tr_) else None
            return (t13 not in j.index and ent is not None and str(ent) == "2019-12-02 09:00:00-05:00" and
                    j.attrs.get("short_bars_dropped") == 1, f"entry {ent}; dropped {j.attrs.get('short_bars_dropped')}")
        _try("V21-7: a share bar of fewer than 5 minutes (the one-minute 13:00 bar of a half day) is dropped by load_bars: "
             "a signal known at 12:30 enters at the next session's first bar, not at the closing minute", v7)
    finally:
        data.http_get = real
        os.environ.pop("EXPLORE_H1_DIR", None)
        data.lock()

    # ---------------- V21-2 and V21-8: commission 0.03 and the 2 USD minimum modelled at the stake notional
    def v2():
        ti, to = U("2019-06-13 14:00"), U("2019-06-13 18:00")
        n = 5000.0 / 6 * 5 * 1.15
        out = []
        for P in (150.0, 30.0):
            r = costs.round_trip("jpm", 1, P, P, ti, to, scenario="net")
            c_want = max(0.03, 2.0 * P / n)
            sl = XC["jpm"]["slip_mkt_bps"] * 1e-4
            si, so = _xsp("jpm", P, ti), _xsp("jpm", P, to)
            fill, ex = (P + si / 2 + c_want) * (1 + sl), (P - so / 2 - c_want) * (1 - sl)
            out.append((abs(r["commission_per_side"] - c_want) < 1e-12 and abs(r["cost"] - (fill - ex)) < 1e-10,
                        f"P {P}: commission {r['commission_per_side']:.4f} per share per side (round trip {r['cost_bp']:.2f} bp)"))
        rs = costs.round_trip("jpm", 1, 30.0, 30.0, ti, to, scenario="stress")
        return (all(o for o, _ in out) and abs(rs["commission_per_side"] - 0.045) < 1e-12 and
                abs(costs.trade_notional("jpm") - n) < 1e-9, "; ".join(i for _, i in out) + f"; stress at 30: "
                f"{rs['commission_per_side']:.4f}")
    _try("V21-2 / V21-8: share commission per side = max(0.03 USD x shares, 2 USD) at the stake notional (5,000 EUR / 6 x "
         "1:5 = 4,791.67 USD): 0.0626 per share at 150 USD, 0.03 at 30 USD; stress x1.5 (0.045)", v2)

    def v8():
        exd = [k for k in XC["jpm"].get("dividends", {}) if k.startswith("2019-07")]
        if not exd:
            return False, "no jpm dividend listed in 2019-07"
        f = XC["jpm"]["dividends"][exd[0]]
        ex9 = pd.Timestamp(exd[0] + " 09:00", tz="America/New_York").tz_convert("UTC")
        ti, to = ex9 - pd.Timedelta(days=1), ex9 + pd.Timedelta(days=1)
        P = 110.0
        rs = costs.round_trip("jpm", -1, P, P, ti, to)
        rl = costs.round_trip("jpm", 1, P, P, ti, to)
        nights = int(costs.swap_nights(pd.DatetimeIndex([ti]), pd.DatetimeIndex([to]), "Fri")[0])
        cl = float(XC["jpm"].get("dividend_credit_long", 0.0))   # kit v2.1 fix 2 (KF-4): 0.70 (amended: was 0)
        ok = (abs(rs["swap"] - (XC["jpm"]["swap_short"] / 360 * rs["fill"] * nights + f * rs["fill"])) < 1e-10 and
              abs(rl["swap"] - (XC["jpm"]["swap_long"] / 360 * rl["fill"] * nights - cl * f * rl["fill"])) < 1e-10)
        d_at = costs.dividends("jpm", [-1, -1, -1], [P] * 3, pd.DatetimeIndex([ex9, ti, ti]),
                               pd.DatetimeIndex([to, ex9, ex9 - pd.Timedelta(hours=1)]))
        ok &= abs(d_at[0]) < 1e-15 and abs(d_at[1] - f * P) < 1e-12 and abs(d_at[2]) < 1e-15
        b = flat_share(P, "2019-05-01", "2019-08-15")
        t = sim.simulate(pd.DataFrame({"known_at": [ti], "side": [-1]}), b, market="jpm", exit=("bdays", 2),
                         stop=("bps", 500))
        sw_hand = XC["jpm"]["swap_short"] / 360 * t.entry_px.iloc[0] * int(costs.swap_nights(
            pd.DatetimeIndex([t.entry_time.iloc[0]]), pd.DatetimeIndex([t.exit_time.iloc[0]]), "Fri")[0]) + f * t.entry_px.iloc[0]
        ok &= abs(t.swap_bp.iloc[0] - sw_hand / t.entry_px.iloc[0] * 1e4) < 1e-8
        try:
            costs.round_trip("jpm", -1, P, P, U("2021-12-28 15:00"), U("2022-01-04 15:00"))
            late = False
        except costs.CostError:
            late = True
        cm = all(XC[k]["commission_per_unit"] == 0.03 for k in costs.EXTRA if k != "oil")
        return (ok and late and cm and len(XC["xom"]["dividends"]) == 20 and XC["amzn"]["dividends"] == {},
                f"ex-date {exd[0]} frac {f}: short pays {f * 1e4:.1f} bp, long 0; at/after the ex-open entry 0; "
                f"simulator swap {t.swap_bp.iloc[0]:.2f} bp; past the listed dividends raises {late}")
    _try("V21-8: dividends: a short open at an ex-date's 09:30 open pays dividend / previous close x its fill (simulator and "
         "costs.round_trip), a long is not credited, a trade past the listed dividends (2021) raises; share commission "
         "0.03 in net", v8)

    # ---------------- V21-3: oil spread in USD, not bp
    def v3():
        t0 = pd.DatetimeIndex([U("2020-04-21 15:00")])
        a = float(costs.spread("oil", 10.0, t0)[0])
        b = float(costs.spread("oil", 100.0, t0)[0])
        return abs(a - 0.05) < 1e-12 and abs(b - 0.05) < 1e-12, f"spread at 10 USD {a}, at 100 USD {b}"
    _try("V21-3: oil's spread is a constant 0.05 USD a barrel (50 bp at 10 USD, 5 bp at 100 USD), not 8.3 bp of price", v3)

    # ---------------- V21-4: share spread level by year
    def v4():
        t20, t23 = pd.DatetimeIndex([U("2020-06-10 15:00")]), pd.DatetimeIndex([U("2023-06-14 15:00")])
        e = XC["tsla"]
        s20 = float(costs.spread("tsla", 100.0, t20)[0]) / 100.0 * 1e4 / XS["shape"]["tsla"][_how(t20[0])]
        s23 = float(costs.spread("tsla", 100.0, t23)[0]) / 100.0 * 1e4 / XS["shape"]["tsla"][_how(t23[0])]
        by = e.get("spread_bps_by_year", {})
        full = all(set(XC[k].get("spread_bps_by_year", {})) >= {"2018", "2019", "2020", "2021"} for k in costs.EXTRA
                   if k != "oil")
        return (abs(s20 - by.get("2020", -1)) < 1e-9 and abs(s23 - e["spread_bps"]) < 1e-9 and
                e["spread_bps"] >= by.get("2021", 1e9) - 1e-12 and full,
                f"tsla level 2020 {s20:.3f} bp (whole-sample median of minutes was 5.46), 2023 (not listed) {s23:.3f} bp")
    _try("V21-4: a share's spread level is that of the bar's New York year (calibrated so that the kit's mean spread at "
         "the year's bar opens equals the data's quoted spread there), and for years not listed max(2021, mean of the years)",
         v4)

    # ---------------- V21-5: the open costs the first-minute 09:30 quote (documented; the figure the docs give)
    def v5():
        sh = np.asarray(XS["shape"]["jpm"])
        mon9, mon10 = sh[0 * 24 + 9], sh[0 * 24 + 10]
        rd = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "README.md")).read()
        return (mon9 > 5 * mon10 and "09:31" in rd and "max_wait_h" in rd and "first-minute" in rd,
                f"jpm Monday 09 bar shape {mon9:.2f} vs 10 bar {mon10:.2f}")
    _try("V21-5: entries at a share's 09 bar pay the 09:30 first-minute quote (jpm shape > 5 x the 10:00 bar's); the "
         "README says so, with the 09:31 figures and the advice to set max_wait_h", v5)

    # ---------------- V21-6: the slow track only for an idea declared slow, and only 5 or 40
    def v6():
        b, sig = synth.signal_world("us500", seed=5, edge=0.0004)
        bk = {"us500": sim.Book(b, "us500")}
        rule = dict(exit=("bdays", 12), stop=("d20", 4.0))
        main = sim.simulate(sig, bk, **rule)
        kw = dict(corr=0.0, truncation=_tr_fixed(sig), ledger=LEDGER_FIXED, write=False)
        fast = os.path.join(TMP, "ideas", "981_fast")
        slow = os.path.join(TMP, "ideas", "982_slow")
        _declare(fast, {"idea": "981 fast", "track": "fast"})
        _declare(slow, {"idea": "982 slow", "track": "slow"})
        res = {}
        for name, folder, mh in (("7", slow, 7), ("30", slow, 30), ("40_fast", fast, 40), ("40_none", TMP, 40)):
            try:
                judge.verdict(folder, main, None, None, None, max_hold_tdays=mh, **kw)
                res[name] = "accepted"
            except ValueError:
                res[name] = "refused"
        v40 = judge.verdict(slow, main, None, None, None, max_hold_tdays=40, **kw)
        return (all(v == "refused" for v in res.values()) and v40["bars"]["hold<=40d"]["pass"], json.dumps(res))
    _try("V21-6: max_hold_tdays accepts only 5 and 40; 40 needs the idea's declared.json to say track 'slow' (7, 30, "
         "40 for an idea declared fast or not declared are refused)", v6)


def _oil_world(h1, start, end, jumps, base=60.0, seed=11, vol=0.0):
    """Raw synthetic oil bars (NY weekdays, every hour) written to h1/oil.parquet: flat (or a random walk of hourly
    sd `vol`) at `base`, the vendor's raw jump at each roll time of `jumps` {UTC time: raw ratio} (prices from it on x
    the ratio)."""
    ix = _hourly_ix(start, end)
    ix = ix[ix.tz_convert("America/New_York").dayofweek < 5]
    for r in jumps:
        if r not in ix:
            ix = ix.union(pd.DatetimeIndex([r]))
    rng = np.random.default_rng(seed)
    p = base * np.exp(np.cumsum(rng.normal(0, vol, len(ix)))) if vol else np.full(len(ix), base)
    m = np.ones(len(ix))
    for r, q in jumps.items():
        m[ix >= r] *= q
    p = p * m
    raw = pd.DataFrame({"open": p, "high": p * 1.001, "low": p * 0.999, "close": p, "volume": 60.0}, index=ix)
    raw.index.name = "time"
    raw.to_parquet(os.path.join(h1, "oil.parquet"))
    return raw


def test_v21_review2_fixes():
    """Kit v2.1 fix 2 (2026-11-18): one check per verifier issue KF-1..KF-9 of the second review; each fails on the
    kit before this fix (scratch kit_v21/fix2/kit_before). KF-10 is rejected with evidence (README)."""
    h1 = os.path.join(TMP, "h1_fix2")
    os.makedirs(h1, exist_ok=True)
    os.makedirs(h1 + "_val", exist_ok=True)
    real = data.http_get

    def no_net(url, **kw):
        raise AssertionError("a local-only market made a request: " + url)
    data.http_get = no_net
    os.environ["EXPLORE_H1_DIR"] = h1
    rolls = {pd.Timestamp(k): float(v) for k, v in XC["oil"].get("rolls", {}).items()}
    try:
        data.lock()

        # ---------------- KF-1: rolls dated and sized from outside settlements; the real night move is kept
        def kf1():
            r14 = U("2014-07-22 22:00")
            span = {r: q for r, q in rolls.items() if U("2014-05-01") <= r < U("2014-10-01")}
            night = 1.01                                         # a real +100 bp move at the roll reopen
            jumps = {r: q * (night if r == r14 else 1.0) for r, q in span.items()}
            _oil_world(h1, "2014-05-01", "2014-10-01", jumps)
            o = data.load_bars("oil", 2014)
            i = int(o.index.searchsorted(r14))
            kept = float(o.open.iloc[i] / o.close.iloc[i - 1])
            others = [float(o.open.iloc[int(o.index.searchsorted(r))] / o.close.iloc[int(o.index.searchsorted(r)) - 1])
                      for r in span if r != r14]
            # the listed ratios against the outside settlements kept in kit/oil_outside.csv (EIA contract 1 / 2) and
            # Dukascopy's 14:30 mid: ratio = C2 / C1 of the last settlement before the roll (|dev| <= 60 bp); the last
            # informative day before the roll on C1, the first one after it (to the expiry) on C2
            ox = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "oil_outside.csv"), index_col=0,
                             parse_dates=True)
            ox = ox[(ox.c1 > 0) & (ox.c2 > 0)]
            s14 = pd.DatetimeIndex([d + pd.Timedelta(hours=14, minutes=30) for d in ox.index]).tz_localize(
                "America/New_York").tz_convert("UTC")
            # duka_on: 1 / 2 = the contract Dukascopy's 14:30 mid is closer to (0 = a tie, empty = no price that day);
            # the vendor's price itself is NOT in the repository (it sits beside the prepared bars, oil_mid_1430.csv)
            on = ox.duka_on.to_numpy(float)
            flick = {pd.Timestamp(d) for d in XC["oil"].get("rolls_vendor_flicker", {})}   # fix 3 (R3-4)
            on = np.where(np.isin(ox.index, list(flick)), np.nan, on) if flick else on
            g = np.log(ox.c2 / ox.c1).to_numpy() * 1e4
            dev, contra, checked = [], [], 0
            for r, q in rolls.items():
                k = int(s14.searchsorted(r)) - 1
                dev.append(abs(np.log(q) * 1e4 - g[k]))
                rn = r.tz_convert("America/New_York")
                mm = rn + pd.Timedelta(days=10) if rn.day >= 26 else rn
                E = data.cl_expiry(mm.year, mm.month)
                inf = np.isfinite(on) & (np.abs(g) >= 12)
                bef = [j for j in range(k, -1, -1) if inf[j] and s14[j] >= r - pd.Timedelta(days=12)][:1]
                aft = [j for j in range(k + 1, len(ox)) if inf[j] and ox.index[j] <= E][:1]
                for j in bef:
                    checked += 1
                    if on[j] == 2:
                        contra.append(f"{r} before")
                for j in aft:
                    checked += 1
                    if on[j] == 1:
                        contra.append(f"{r} after")
            dev = np.asarray(dev)
            spot = (rolls.get(U("2014-07-22 22:00"), 1) < 0.985 and U("2014-07-22 00:00") not in rolls and
                    rolls.get(U("2015-02-19 00:00"), 0) > 1.01 and U("2021-11-15 23:00") in rolls and
                    U("2021-11-17 23:00") not in rolls and all(q < 1.01 for r, q in rolls.items() if r.strftime("%Y-%m") == "2013-05"))
            return (abs(kept - night) < 1e-9 and all(abs(x - 1) < 1e-9 for x in others) and len(rolls) == 108 and
                    float(dev.max()) <= 60 and not contra and checked > 100 and spot,
                    f"roll 2014-07-22 22:00: reopen move left {kept:.6f} (real night move {night}); listed vs outside "
                    f"C2/C1: max |dev| {dev.max():.1f} bp; day states checked {checked}, contradictions {contra[:3]}")
        _try("KF-1: oil rolls are dated and sized from outside settlements (EIA WTI contract 1 / 2 against Dukascopy's "
             "14:30 price, kit/oil_outside.csv): the listed ratio is applied, so a real move on the roll night stays in "
             "the series; every listed ratio is within 60 bp of the outside C2/C1 and the day states agree", kf1)

        def kf1b():
            idea = os.path.join(TMP, "ideas", "983_fix2_val")
            os.makedirs(idea, exist_ok=True)
            json.dump(VALDECL, open(os.path.join(idea, "val_declared.json"), "w"))
            json.dump({"verdict": "pass"}, open(os.path.join(idea, "results.json"), "w"))
            hol = data._nyse_holidays(2023, 2023)
            e = data.cl_expiry(2023, 6, hol)                     # 2023-06-20: the rule reopen is a Thursday evening
            x = e - pd.Timedelta(days=1)
            while x.weekday() >= 5 or x in hol:
                x -= pd.Timedelta(days=1)
            tr = (x - pd.Timedelta(days=1) + pd.Timedelta(hours=18)).tz_localize("America/New_York").tz_convert("UTC")
            _oil_world(h1, "2021-06-01", "2021-12-31", {r: q for r, q in rolls.items() if r >= U("2021-06-01")})
            iv = _hourly_ix("2022-01-01", "2026-01-01")
            iv = iv[iv.tz_convert("America/New_York").dayofweek < 5]
            iv = iv[(iv < tr - pd.Timedelta(hours=14)) | (iv >= tr)]             # a 14-hour hole before the reopen
            v = pd.DataFrame({"open": 60.0, "high": 60.2, "low": 59.8, "close": 60.0, "volume": 60.0}, index=iv)
            v.loc[v.index >= tr, ["open", "high", "low", "close"]] *= 1.04
            v.index.name = "time"
            v.to_parquet(os.path.join(h1 + "_val", "oil.parquet"))
            data.unlock_val(idea)
            try:
                try:
                    data.load_bars("oil", 2021)
                    raised = False
                except data.DataGap:
                    raised = True
            finally:
                data.lock()
            return raised and tr.tz_convert("America/New_York").dayofweek == 3, \
                f"rule roll {tr} after a 14-hour hole: DataGap raised {raised}"
        _try("KF-1: in the validation years a rule roll whose reopen comes after a data hole longer than the normal break "
             "raises DataGap (its ratio would include the real move)", kf1b)

        # ---------------- KF-2: the truncation test sees absolute levels of back-adjusted bars
        def kf2():
            span = {r: q for r, q in rolls.items() if U("2016-01-01") <= r < U("2018-01-01")}
            _oil_world(h1, "2016-01-01", "2018-01-01", span, base=60.0, vol=0.004, seed=3)
            o = data.load_bars("oil", 2016)
            lvl = float(o.close.median())

            def level_rule(d):
                c = d["oil"].close
                x = c[(c > lvl) & (c.shift(1) <= lvl)]
                return pd.DataFrame({"known_at": x.index + pd.Timedelta(hours=1), "side": 1, "market": "oil"})

            def ratio_rule(d):
                c = d["oil"].close
                r_ = c / c.shift(120) - 1
                x = r_[(r_ > 0.03) & (r_.shift(1) <= 0.03)]
                return pd.DataFrame({"known_at": x.index + pd.Timedelta(hours=1), "side": 1, "market": "oil"})

            pf_mid = float(np.median(data.price_factor("oil", o.index)))

            def factor_rule(d):                                  # reads the size of the later rolls via price_factor
                c = d["oil"].close
                pf = pd.Series(data.price_factor("oil", c.index), index=c.index)
                x = c[(pf > pf_mid) & (c.index.hour == 15)]
                return pd.DataFrame({"known_at": x.index + pd.Timedelta(hours=1), "side": 1, "market": "oil"})
            rl = checks.truncation_test(level_rule, {"oil": o}, n_signal_cuts=30, n_random_cuts=30)
            rr = checks.truncation_test(ratio_rule, {"oil": o}, n_signal_cuts=30, n_random_cuts=30)
            rf = checks.truncation_test(factor_rule, {"oil": o}, n_signal_cuts=30, n_random_cuts=30)
            # a share with a split: a level rule on aapl's adjusted bars (4:1 on 2020-08-31)
            sh = flat_share(400.0, "2020-06-01", "2020-10-01")
            sh.loc[sh.index >= pd.Timestamp("2020-08-31", tz="America/New_York"), ["open", "high", "low", "close"]] /= 4
            wig = 1 + 0.03 * np.sin(np.arange(len(sh)) / 9.0)
            for col in ("open", "high", "low", "close"):
                sh[col] = sh[col] * wig
            sh.index.name = "time"
            sh.to_parquet(os.path.join(h1, "aapl.parquet"))
            a = data.load_bars("aapl", 2020)
            lv2 = float(a.close.median())

            def share_level(d):
                c = d["aapl"].close
                x = c[(c > lv2) & (c.shift(1) <= lv2)]
                return pd.DataFrame({"known_at": x.index + pd.Timedelta(hours=1), "side": 1, "market": "aapl"})
            ra = checks.truncation_test(share_level, {"aapl": a}, n_signal_cuts=30, n_random_cuts=30)
            ok = (not rl["pass"] and rr["pass"] and not rf["pass"] and not ra["pass"] and rl["n_signals"] > 5
                  and rr["n_signals"] > 5 and "ROLLS_APPLIED" not in dir(data) and "rolls_adjusted" not in o.attrs)
            return ok, (f"oil level rule: pass {rl['pass']} ({rl['n_failed_cuts']} failed cuts, {rl['n_signals']} "
                        f"signals); ratio rule: pass {rr['pass']} ({rr['n_signals']}); price_factor rule: pass {rf['pass']}; "
                        f"aapl level rule across its split: pass {ra['pass']}")
        _try("KF-2: checks.truncation_test re-bases each cut copy of back-adjusted bars (oil rolls, share splits) to the "
             "adjustment known at the cut and runs the cut build inside data.asof: a rule on absolute adjusted levels, or "
             "one that reads data.price_factor, fails; a ratio rule passes; no roll table or count is public", kf2)

        # ---------------- KF-3: the oil adjustment does not depend on load order or on this process's loads
        def kf3():
            span = {r: q for r, q in rolls.items() if U("2017-01-01") <= r < U("2020-01-01")}
            _oil_world(h1, "2017-01-01", "2020-01-01", span)
            o = data.load_bars("oil", 2017)
            data.load_bars("oil", 2019)                            # a second load with another start year
            b1 = sim.Book(o, "oil")
            want = 0.05 * float(np.prod([q for r, q in rolls.items() if r > o.index[0]]))
            saved = dict(getattr(data, "_ROLLS_MEASURED", {}))
            if hasattr(data, "_ROLLS_MEASURED"):
                data._ROLLS_MEASURED.clear()                       # as in a fresh process (bars read from a file)
            try:
                b2 = sim.Book(o, "oil")
            finally:
                if hasattr(data, "_ROLLS_MEASURED"):
                    data._ROLLS_MEASURED.update(saved)
            return (abs(float(b1.s[0]) - want) < 1e-12 and abs(float(b2.s[0]) - want) < 1e-12,
                    f"spread of the first bar after a second load {float(b1.s[0]):.6f}, with an empty process table "
                    f"{float(b2.s[0]):.6f}, expected 0.05 x the later listed ratios = {want:.6f}")
        _try("KF-3: the oil spread (and the roll adjustment) of a Book does not depend on a second load_bars with another "
             "start year nor on what this process loaded (listed ratios in sample)", kf3)
    finally:
        data.http_get = real
        os.environ.pop("EXPLORE_H1_DIR", None)
        data.lock()

    # ---------------- KF-4: a long across an ex-date is credited 70 % of the dividend; judge reports credits 0 and 1
    def kf4():
        exd = [k for k in XC["xom"].get("dividends", {}) if k.startswith("2019-08")][0]
        f = XC["xom"]["dividends"][exd]
        ex9 = pd.Timestamp(exd + " 09:00", tz="America/New_York").tz_convert("UTC")
        ti, to = ex9 - pd.Timedelta(days=3, hours=-1), ex9 + pd.Timedelta(days=1)    # Friday 10:00 -> Tuesday 09:00
        P = 80.0
        rl = costs.round_trip("xom", 1, P, P, ti, to)
        nights = int(costs.swap_nights(pd.DatetimeIndex([ti]), pd.DatetimeIndex([to]), "Fri")[0])
        hand = XC["xom"]["swap_long"] / 360 * rl["fill"] * nights - 0.7 * f * rl["fill"]
        b = flat_share(P, "2019-06-01", "2019-09-15")
        t = sim.simulate(pd.DataFrame({"known_at": [ti], "side": [1]}), b, market="xom", exit=("bdays", 2),
                         stop=("bps", 500))
        rep = judge.dividend_report(t)
        m = rep["by_market"]["xom"]
        return (abs(rl["swap"] - hand) < 1e-10 and XC["xom"]["dividend_credit_long"] == 0.7 and
                m["long_trades_across_ex_dates"] == 1 and rep["mean_R_net_credit_0"] < rep["mean_R_net"] < rep["mean_R_net_credit_1"],
                f"xom {exd}: long credited {0.7 * f * 1e4:.1f} bp of the fill; report {json.dumps(m)}; mean R at 0 / 0.7 / 1: "
                f"{rep['mean_R_net_credit_0']:.4f} / {rep['mean_R_net']:.4f} / {rep['mean_R_net_credit_1']:.4f}")
    _try("KF-4: a share long open at an ex-date's first bar is credited dividend_credit_long = 0.70 x dividend / previous "
         "close x its fill; judge.dividend_report gives the long result at credits 0 and 1", kf4)

    # ---------------- KF-5: two spread levels per share and year (09 bar open, 10-15 bars)
    def kf5():
        e = XC["jpm"]
        t9 = pd.DatetimeIndex([pd.Timestamp("2017-06-14 09:00", tz="America/New_York").tz_convert("UTC")])
        t10 = pd.DatetimeIndex([pd.Timestamp("2017-06-14 10:00", tz="America/New_York").tz_convert("UTC")])
        s9 = float(costs.spread("jpm", 100.0, t9)[0]) / 100 * 1e4 / XS["shape"]["jpm"][_how(t9[0])]
        s10 = float(costs.spread("jpm", 100.0, t10)[0]) / 100 * 1e4 / XS["shape"]["jpm"][_how(t10[0])]
        c9 = float(costs.spread("jpm", 100.0, t9, at="close")[0]) / 100 * 1e4 / XS["shape_close"]["jpm"][_how(t9[0])]
        full = all(set(XC[k].get("spread_bps_by_year_h09", {})) == set(XC[k]["spread_bps_by_year"]) and "spread_bps_h09" in XC[k]
                   for k in costs.EXTRA if k != "oil")
        c9_want = e.get("spread_bps_by_year_c09", e["spread_bps_by_year"])["2017"]   # fix 3 (R3-5): its own close level
        return (abs(s9 - e["spread_bps_by_year_h09"]["2017"]) < 1e-9 and abs(s10 - e["spread_bps_by_year"]["2017"]) < 1e-9
                and abs(c9 - c9_want) < 1e-9 and abs(s9 - s10) > 0.3 and full,
                f"jpm 2017 level at the 09 open {s9:.3f} bp, at 10:00 {s10:.3f} bp, at the 09 bar's close {c9:.3f} bp")
    _try("KF-5: a share has two spread levels per year, each calibrated on its own minutes: the 09 bar's open (09:30) and "
         "the 10-15 bars' opens (and every close)", kf5)

    # ---------------- KF-6: V7 passes when the self-test runs with EXPLORE_H1_DIR set (as prescribed)
    def kf6():
        d = os.path.join(TMP, "h1_kf6")
        os.makedirs(d, exist_ok=True)
        fe = flat("eurusd", "2021-01-01", "2021-03-01")
        fe.index.name = "time"
        fe.to_parquet(os.path.join(d, "eurusd.parquet"))
        n0 = len(RESULTS)
        os.environ["EXPLORE_H1_DIR"] = d
        try:
            test_review_v7_budget()
        finally:
            os.environ.pop("EXPLORE_H1_DIR", None)
        new = RESULTS[n0:]
        del RESULTS[n0:]
        return bool(new) and all(r[1] for r in new), f"V7 with EXPLORE_H1_DIR set: {[r[1] for r in new]}"
    _try("KF-6: the V7 download-budget check passes with EXPLORE_H1_DIR set (its prefetch part ignores the prepared bars)",
         kf6)

    # ---------------- KF-8: per-leg exit adjustment in pair_round_trip; round_trip's adj defaults to price_factor
    def kf8():
        ti, to = U("2020-08-27 15:00"), U("2020-09-02 15:00")           # across aapl's 4:1 split of 2020-08-31
        a_in = float(data.price_factor("aapl", pd.DatetimeIndex([ti]))[0])
        a_out = float(data.price_factor("aapl", pd.DatetimeIndex([to]))[0])
        costs.register_pair("aapl/msft", "aapl", "msft")
        r1 = costs.pair_round_trip("aapl/msft", 1, (120.0, 210.0), (125.0, 215.0), ti, to, adj=(a_in, 1.0),
                                   adj_out=(a_out, 1.0))
        r0 = costs.pair_round_trip("aapl/msft", 1, (120.0, 210.0), (125.0, 215.0), ti, to)
        rt0 = costs.round_trip("oil", 1, 60.0, 60.0, U("2016-01-05 15:00"), U("2016-01-06 15:00"))
        f0 = float(data.price_factor("oil", pd.DatetimeIndex([U("2016-01-05 15:00")]))[0])
        rt1 = costs.round_trip("oil", 1, 60.0, 60.0, U("2016-01-05 15:00"), U("2016-01-06 15:00"), adj=f0)
        return (abs(r1["cost_bp"] - r0["cost_bp"]) < 1e-9 and abs(rt0["cost_bp"] - rt1["cost_bp"]) < 1e-12 and
                abs(rt0["spread_in"] / costs.shape("oil", pd.DatetimeIndex([U("2016-01-05 15:00")]))[0] - 0.05 * f0) < 1e-12
                and a_in == 0.25 and a_out == 1.0,
                f"pair across the split: explicit per-leg adj {r1['cost_bp']:.4f} bp = default {r0['cost_bp']:.4f}; oil "
                f"round trip default adj {rt0['cost_bp']:.4f} bp = with price_factor {rt1['cost_bp']:.4f}")
    _try("KF-8: pair_round_trip takes each leg's exit adjustment (a split inside the trade) and defaults both to "
         "data.price_factor; costs.round_trip's adj defaults to data.price_factor for oil (rolls) and split shares", kf8)

    # ---------------- KF-9: documentation
    def kf9():
        doc = costs.__doc__
        src = XC["jpm"]["source"]["spread_bps_by_year"]
        return ("modelled since the fix" in doc.lower() or "MODELLED since the fix" in doc) and \
            "mean of the daily median quoted spread, the" not in doc and "calibrated" in src.lower(), \
            "costs.py header and extra_costs.json source notes"
    _try("KF-9: the costs.py header no longer says the 2 USD minimum is reported only, and the spread-level note says "
         "'calibrated to the bar-open minutes' as extra_costs.json does", kf9)


def _tick_oil(h1, start, end, jumps, seed=5, base=60.0):
    """Raw synthetic oil bars quoted in CENTS (as the vendor's): a random walk of whole cents, each bar's open within a
    cent of the previous close, the vendor's raw jump at each roll of `jumps` (prices from it on x the ratio, rounded to
    the cent again). Written to h1/oil.parquet."""
    ix = _hourly_ix(start, end)
    ix = ix[ix.tz_convert("America/New_York").dayofweek < 5]
    rng = np.random.default_rng(seed)
    n = len(ix)
    c = np.round(base * 100 + np.cumsum(rng.integers(-4, 5, n))).astype(float)
    o = np.r_[c[0], c[:-1]] + rng.integers(-1, 2, n)
    m = np.ones(n)
    for r, q in jumps.items():
        m[ix >= r] *= q
    o, c = np.round(o * m) / 100, np.round(c * m) / 100
    raw = pd.DataFrame({"open": o, "high": np.maximum(o, c) + 0.01, "low": np.minimum(o, c) - 0.01, "close": c,
                        "volume": 60.0}, index=ix)
    raw.index.name = "time"
    raw.to_parquet(os.path.join(h1, "oil.parquet"))
    return raw


def test_v21_review3_fixes():
    """Kit v2.1 fix 3 (2026-11-18): one check per verifier issue R3-1..R3-9 of the third review; each fails on the kit
    before this fix (scratch kit_v21/fix3/kit_before)."""
    h1 = os.path.join(TMP, "h1_fix3")
    os.makedirs(h1, exist_ok=True)
    real = data.http_get

    def no_net(url, **kw):
        raise AssertionError("a local-only market made a request: " + url)
    data.http_get = no_net
    os.environ["EXPLORE_H1_DIR"] = h1
    rolls = {pd.Timestamp(k): float(v) for k, v in XC["oil"].get("rolls", {}).items()}
    H = pd.Timedelta(hours=1)
    S_ = lambda x, mk="oil": pd.DataFrame({"known_at": x.index + H, "side": 1, "market": mk})  # noqa: E731
    try:
        data.lock()
        span = {r: q for r, q in rolls.items() if U("2016-01-01") <= r < U("2018-01-01")}
        _tick_oil(h1, "2016-01-01", "2018-01-01", span)
        o = data.load_bars("oil", 2016)
        lvl = float(o.close.median())

        # ---------------- R3-1: exact re-basing (a power of two): tie-prone honest rules pass, level rules still fail
        def r31():
            def tie(d):                                          # close-open > open-previous close (price differences)
                b = d["oil"]
                return S_(b[(b.close - b.open) > (b.open - b.close.shift())])

            def rng2(d):                                         # range > the two previous ranges summed
                b = d["oil"]
                r_ = b.high - b.low
                return S_(b[r_ > r_.shift() + r_.shift(2)])

            def level(d):
                c = d["oil"].close
                return S_(c[(c > lvl) & (c.shift() <= lvl)])
            a = checks.truncation_test(tie, {"oil": o})
            b = checks.truncation_test(rng2, {"oil": o})
            c = checks.truncation_test(level, {"oil": o}, n_signal_cuts=30, n_random_cuts=30)
            with data.asof(U("2016-06-01")):
                q = data._asof_q("oil") if hasattr(data, "_asof_q") else None
            return (a["pass"] and b["pass"] and not c["pass"] and a["n_signals"] > 1000 and q in (0.25, 0.5, 2.0, 4.0),
                    f"close-open > open-prevclose: pass {a['pass']} ({a['n_failed_cuts']}/{len(a['cuts'])} failed, "
                    f"{a['n_signals']} signals); range rule: pass {b['pass']} ({b['n_failed_cuts']} failed); level rule: "
                    f"pass {c['pass']} ({c['n_failed_cuts']} failed); re-basing factor at 2016-06-01: {q}")
        _try("R3-1: the truncation test re-bases back-adjusted bars by an exact power of two (data._asof_q), so an honest "
             "rule comparing price differences on cent-quoted oil cannot flip on a floating-point tie (passes) while a "
             "rule on adjusted levels still fails", r31)

        # ---------------- R3-2: derived inputs are re-based (daily_bars keeps attrs, any Series name, wide frames)
        def r32():
            dd = data.daily_bars(o)
            dd = dd.set_index(pd.DatetimeIndex(dd.known_at))
            ld = float(dd.close.median())

            def daily_level(d):
                x = d["od"]
                m = (x.close > ld) & (x.close.shift() <= ld)
                return pd.DataFrame({"known_at": x.index[m], "side": 1, "market": "oil"})
            px = o.close.rename("px")

            def renamed(d):
                c = d["p"]
                return S_(c[(c > lvl) & (c.shift() <= lvl)])
            wide = pd.DataFrame({"oil": o.close})

            def wide_level(d):
                c = d["w"]["oil"]
                return S_(c[(c > lvl) & (c.shift() <= lvl)])

            def daily_ret(d):                                    # honest: computed inside build
                x = d["od"]
                r_ = x.close / x.close.shift() - 1
                return pd.DataFrame({"known_at": x.index[r_ > 0.004], "side": 1, "market": "oil"})
            kw = dict(n_signal_cuts=30, n_random_cuts=30)
            a = checks.truncation_test(daily_level, {"od": dd}, row_len=pd.Timedelta(0), **kw)
            b = checks.truncation_test(renamed, {"p": px}, **kw)
            c = checks.truncation_test(wide_level, {"w": wide}, **kw)
            e = checks.truncation_test(daily_ret, {"od": dd}, row_len=pd.Timedelta(0), **kw)
            return (dd.attrs.get("market") == "oil" and not a["pass"] and not b["pass"] and not c["pass"] and e["pass"]
                    and min(a["n_signals"], b["n_signals"], c["n_signals"]) > 3,
                    f"level rule on daily_bars: pass {a['pass']} (attrs market {dd.attrs.get('market')}); on a close "
                    f"renamed 'px': pass {b['pass']}; on a wide frame column 'oil': pass {c['pass']}; honest daily return "
                    f"rule on daily_bars: pass {e['pass']}")
        _try("R3-2: data.daily_bars keeps attrs['market'], and the truncation test re-bases any input carrying an adjusted "
             "market's attrs whatever its name, and wide-frame columns named after an adjusted market: a level rule on "
             "each fails", r32)

        # ---------------- R3-3: precomputed returns with the market's attrs are refused, not falsely failed
        th = float(o.close.pct_change().quantile(0.98))           # a fixed threshold (2 % of hourly returns exceed it)

        def r33():
            def thr(d, k="r"):
                x = d[k]
                return S_(x[x > th])
            out = []
            for name, item in (("pct_change", o.close.pct_change()),
                               ("log-return frame", np.log(o[["open", "high", "low", "close"]]).diff())):
                try:
                    checks.truncation_test(lambda d: thr({"r": d["r"] if isinstance(d["r"], pd.Series) else d["r"].close}),
                                           {"r": item}, n_signal_cuts=5, n_random_cuts=5)
                    out.append(f"{name}: not refused")
                except ValueError as ex:
                    out.append("refused" if "INSIDE build" in str(ex) else f"{name}: other error {ex}")

            def inside(d):
                r_ = d["oil"].close.pct_change()
                return S_(r_[r_ > th])
            ok_in = checks.truncation_test(inside, {"oil": o}, n_signal_cuts=30, n_random_cuts=30)
            return (out == ["refused", "refused"] and ok_in["pass"] and ok_in["n_signals"] > 10,
                    f"precomputed: {out}; the same return rule computed inside build: pass {ok_in['pass']} "
                    f"({ok_in['n_signals']} signals)")
        _try("R3-3: a return series or frame computed outside build that keeps an adjusted market's attrs is REFUSED by "
             "the truncation test (ValueError: compute features inside build) instead of being re-based into a false "
             "failure; the same rule computed inside build passes", r33)

        # ---------------- R3-9: bars of an earlier load whose measured roll ratios changed are refused by sim.Book
        def r39():
            sp = costs.EXTRA["oil"]
            saved = {k: sp[k] for k in ("rolls", "rolls_vendor_gap", "rolls_checked_to")}
            meas = {k: dict(v) for k, v in data._ROLLS_MEASURED.items()}
            try:
                sp["rolls"] = {k: v for k, v in saved["rolls"].items() if pd.Timestamp(k) < U("2021-01-01")}
                sp["rolls_vendor_gap"] = {k: v for k, v in saved["rolls_vendor_gap"].items() if pd.Timestamp(k) < U("2021-01-01")}
                sp["rolls_checked_to"] = "2020-12-31"                # 2021 plays the validation years (in memory)
                rule = [r for r in data.roll_times("oil") if r >= U("2021-01-01")]
                jl = {pd.Timestamp(k): v for k, v in sp["rolls"].items() if pd.Timestamp(k) >= U("2020-06-01")}
                p1 = {r: 1.0 + 0.003 * (i % 4) - 0.004 for i, r in enumerate(rule)}
                _oil_world(h1, "2020-06-01", "2022-01-01", {**jl, **p1}, vol=0.001)
                b_old = data.load_bars("oil", 2020)
                sim.Book(b_old, "oil")
                _oil_world(h1, "2020-06-01", "2022-01-01", {**jl, **{r: q * 1.003 for r, q in p1.items()}}, vol=0.001)
                b_new = data.load_bars("oil", 2020)
                try:
                    sim.Book(b_old, "oil")
                    stale = False
                except data.DataGap:
                    stale = True
                sim.Book(b_new, "oil")
                sim.Book(b_new[b_new.index >= U("2021-03-01")], "oil")   # a slice of the new load is fine
                return stale and len(rule) == 12, f"Book on bars of the earlier load after a reload: DataGap {stale}"
            finally:
                sp.update(saved)
                data._ROLLS_MEASURED.clear()
                data._ROLLS_MEASURED.update(meas)
        _try("R3-9: sim.Book refuses (DataGap) bars of an earlier load_bars whose measured roll ratios (validation years) "
             "differ from this process's current ones (attrs carry a digest, not the ratios)", r39)
    finally:
        data.http_get = real
        os.environ.pop("EXPLORE_H1_DIR", None)
        data.lock()

    # ---------------- R3-4: the March 2014 oil roll at the vendor's switch (2014-03-18 22:00)
    def r34():
        ox = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "oil_outside.csv"), index_col=0)
        want = float(ox.loc["2014-03-18", "c2"] / ox.loc["2014-03-18", "c1"])
        q = rolls.get(U("2014-03-18 22:00"))
        return (q is not None and abs(q / want - 1) < 1e-9 and U("2014-03-19 22:00") not in rolls and len(rolls) == 108
                and "2014-03-19" in XC["oil"].get("rolls_vendor_flicker", {}),
                f"roll 2014-03-18 22:00 ratio {q} (C2/C1 settled 2014-03-18: {want:.12f}); 2014-03-19 22:00 listed: "
                f"{U('2014-03-19 22:00') in rolls}")
    _try("R3-4: the March 2014 oil roll is listed where the vendor switched (2014-03-18 22:00, raw gap -111 bp) with C2/C1 "
         "settled 2014-03-18 (-82.6 bp), not at 2014-03-19 22:00 (raw gap +1 bp); the 03-19/03-20 flicker is recorded", r34)

    # ---------------- R3-5: share spread at a bar's close, three calibrated levels per year
    def r35():
        e = XC["tsla"]
        out = {}
        for g, hh in (("c09", 9), ("c10_14", 12), ("c15", 15)):
            t = pd.DatetimeIndex([pd.Timestamp(f"2017-06-14 {hh:02d}:00", tz="America/New_York").tz_convert("UTC")])
            out[g] = float(costs.spread("tsla", 100.0, t, at="close")[0]) / 100 * 1e4 / XS["shape_close"]["tsla"][_how(t[0])]
        good = all(abs(out[g] - e[f"spread_bps_by_year_{g}"]["2017"]) < 1e-9 for g in out)
        full = all(set(XC[k].get(f"spread_bps_by_year_{g}", {})) == set(XC[k]["spread_bps_by_year"]) and f"spread_bps_{g}" in XC[k]
                   for k in costs.EXTRA if k != "oil" for g in ("c09", "c10_14", "c15"))
        t15 = pd.DatetimeIndex([pd.Timestamp("2017-06-14 15:00", tz="America/New_York").tz_convert("UTC")])
        op = float(costs.spread("tsla", 100.0, t15, at="open")[0]) / 100 * 1e4 / XS["shape"]["tsla"][_how(t15[0])]
        return (good and full and out["c15"] < 0.6 * e["spread_bps_by_year"]["2017"] and abs(op - e["spread_bps_by_year"]["2017"]) < 1e-9,
                f"tsla 2017 close levels {json.dumps({k: round(v, 3) for k, v in out.items()})} bp; 10-15 open level "
                f"{e['spread_bps_by_year']['2017']} bp")
    _try("R3-5: a share's spread at a bar's CLOSE uses its own calibrated level per year (09 bar, 10-14 bars, 15 bar "
         "before the closure: kit_v21/fix3/s/k5c_levels.py), for every share and year listed", r35)

    # ---------------- R3-6: dividend_report covers a hedged pair's share legs
    def r36():
        exd = [k for k in XC["xom"]["dividends"] if "2019-03-05" <= k < "2019-09-01"]
        bx, bj = flat_share(80.0, "2019-03-01", "2019-09-15"), flat_share(110.0, "2019-03-01", "2019-09-15")
        costs.register_pair("xom/jpm", "xom", "jpm")
        pb = sim.pair_book("xom/jpm", "xom", "jpm", bx, bj)
        kas = [pd.Timestamp(d + " 09:00", tz="America/New_York").tz_convert("UTC") - pd.Timedelta(hours=20) for d in exd]
        sig = pd.DataFrame({"known_at": pd.DatetimeIndex(kas), "side": 1, "market": "xom/jpm"})
        res, keep = {}, costs.EXTRA["xom"]["dividend_credit_long"]
        try:
            for cr in (0.0, 1.0, keep):
                costs.EXTRA["xom"]["dividend_credit_long"] = cr
                res[cr] = sim.simulate(sig, {"xom/jpm": pb}, exit=("bdays", 3), stop=("bps", 300))
        finally:
            costs.EXTRA["xom"]["dividend_credit_long"] = keep
        rep = judge.dividend_report(res[keep])
        m = rep["by_market"].get("xom/jpm", {})
        return (m.get("long_trades_across_ex_dates", 0) >= 1 and "xom" in m.get("legs", {}) and
                abs(rep["mean_R_net_credit_0"] - float(res[0.0].R.mean())) < 1e-9 and
                abs(rep["mean_R_net_credit_1"] - float(res[1.0].R.mean())) < 1e-9 and
                rep["mean_R_net_credit_0"] < rep["mean_R_net"] < rep["mean_R_net_credit_1"],
                f"pair xom/jpm long across {len(exd)} xom ex-dates ({len(res[keep])} trades; report {json.dumps(m)}): "
                f"report mean R at 0 / 0.7 / 1 "
                f"{rep.get('mean_R_net_credit_0', float('nan')):.5f} / {rep.get('mean_R_net', float('nan')):.5f} / "
                f"{rep.get('mean_R_net_credit_1', float('nan')):.5f}; re-simulated at 0 / 1 {float(res[0.0].R.mean()):.5f} / "
                f"{float(res[1.0].R.mean()):.5f}")
    _try("R3-6: judge.dividend_report covers a hedged pair's share legs: its credit-0 / credit-1 figures equal the pair "
         "re-simulated with the long credit at 0 and 1", r36)

    # ---------------- R3-7: an empty main is judged 'fail' (no crash), results.json and the ledger line are written
    def r37():
        idea = os.path.join(TMP, "ideas", "984_fix3_empty")
        os.makedirs(idea, exist_ok=True)
        led = os.path.join(TMP, "LEDGER_fix3.md")
        shutil.copy(judge.LEDGER, led)
        main = sim.simulate(pd.DataFrame({"known_at": pd.DatetimeIndex([], tz="UTC"), "side": pd.Series([], dtype=int)}),
                            flat("eurusd"), market="eurusd", exit=("hours", 5), stop=("d20", 1.5))
        r = judge.verdict(idea, main, corr="compute", ten=TEN, ledger=led)
        n0 = judge.ledger_total(led)
        judge.ledger_add(1, r["ledger_line"], path=led)
        return (len(main) == 0 and r["verdict"] == "fail" and os.path.isfile(os.path.join(idea, "results.json")) and
                judge.ledger_total(led) == n0 + 1, f"verdict {r['verdict']}; ledger total {n0} -> {judge.ledger_total(led)}")
    _try("R3-7: judge.verdict with corr='compute' on a main with no trades returns 'fail' (stats.corr_with_ten gives None) "
         "and writes results.json and a ledger line", r37)

    # ---------------- R3-8: data.asof nests (an inner, later cut never widens what the outer one hides)
    def r38():
        with data.asof(U("2016-01-01")):
            with data.asof(U("2018-01-01")):
                inner = data.known_end()
            outer = data.known_end()
        return inner == U("2016-01-01") and outer == U("2016-01-01") and data._ASOF[0] is None, \
            f"inner known_end {inner}, after the inner exits {outer}"
    _try("R3-8: an inner data.asof(t2) with t2 after the outer cut keeps the outer cut", r38)


# ------------------------------------------------------------------ kit v2.2: generic US shares on daily bars
D1C = XC["_classes"]["us_shares_d1"]
NYZ = "America/New_York"


def _d1_folder(name):
    d = os.path.join(TMP, name)
    os.makedirs(d, exist_ok=True)
    os.makedirs(d + "_val", exist_ok=True)
    return d


def _write_d1(folder, key, df):
    f = df.copy()
    f.index.name = "time"
    f.to_parquet(os.path.join(folder, f"{key}.parquet"))


def _flat_d1(price=40.0, start="2016-01-01", end="2021-12-31", rng_=1.0):
    """Flat daily session bars on the rule calendar (data.us_sessions): open = close = price, high - low = rng_."""
    cal = data.us_sessions(start, end)
    return pd.DataFrame({"open": price, "high": price + rng_ / 2, "low": price - rng_ / 2, "close": price,
                         "volume": cal.minutes.to_numpy(float), "shares": 1e6}, index=pd.DatetimeIndex(cal.open_utc))


def _d1cm(mid, adj=1.0):
    """Hand commission per adjusted unit per side of the class: max(0.03 x adj, 2 USD x mid / stake notional)."""
    st = XC["_stake"]
    n = st["account_eur"] / st["positions"] * D1C["leverage"] * st["usd_per_eur"]
    return max(D1C["commission_per_unit"] * adj, D1C["min_commission_per_side"] * mid / n)


def _ny_open(day):
    return pd.Timestamp(day + " 09:30").tz_localize(NYZ).tz_convert("UTC")


def _ny_at(day, hm):
    return pd.Timestamp(f"{day} {hm}").tz_localize(NYZ).tz_convert("UTC")


def test_v22_universe_and_costs():
    """Kit v2.2 A: the share universe is one cost class (no hand entries), its kit files hold no price, and every new
    cost path by hand on flat daily bars of a real universe key (afl) read through data.load_bars: entry at the next
    session's open with the 56 bp level, exit at an open N sessions later (56 bp) and at a close (12 bp), the per-share
    commission at the price unadjusted for the 2018 2:1 split, the Friday triple swap and a holiday, the ex-dividend
    date long and short, a stop hit inside a day, a stop gapped through at the open, stop and target in one bar."""
    u = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "universe_us.csv"), dtype=str)
    dv = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "universe_us_dividends.csv"), dtype=str)
    spl = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "universe_us_splits.csv"), dtype=str)
    keys = sorted(costs.UNIVERSE)
    check("v2.2 A: the 382 shares of the universe file are markets of ONE cost class (us_shares_d1), keyed by the file's "
          "key, none a key of fp_costs.json or extra_costs.json; SPEC (16) and EXTRA (41) unchanged; every share "
          "provisional; the kit files hold public facts only (no price column, nothing dated 2022+)",
          len(keys) == 382 and list(u.columns) == ["key", "ticker", "sector", "in_universe_from"] and
          sorted(u.key) == keys and u.sector.nunique() == 11 and not set(keys) & (set(costs.SPEC) | set(costs.EXTRA))
          and len(costs.SPEC) == 16 and len(costs.EXTRA) == 41 and
          all(costs.market_class(k) == "us_shares_d1" and costs.is_provisional(k) for k in keys) and
          costs.market_class("jpm") is None and costs.bar_kind("afl") == "session" and costs.bar_kind("jpm") == "hour"
          and list(dv.columns) == ["key", "ex_date", "fraction"] and dv.ex_date.max() < "2022-01-01" and
          list(spl.columns) == ["key", "date", "ratio"] and spl.date.max() < "2022-01-01" and
          u.in_universe_from.max() < "2022-01-01" and costs.spec("afl")["sector"] == "Financials" and
          costs.spec("afl")["commission_splits"] == {"2018-03-19": 2.0} and costs.min_day_bars("afl") == 1,
          f"{len(keys)} shares, {u.sector.nunique()} sectors, {len(dv)} dividends, {len(spl)} splits")
    d1 = _d1_folder("d1_costs")
    b = _flat_d1(40.0, "2017-01-01", "2019-12-31")
    b.loc[b.index < U("2018-05-01"), ["open", "high", "low", "close"]] -= 20.0       # 20 USD (Yahoo level) before May 2018
    _write_d1(d1, "afl", b)
    os.environ["EXPLORE_D1_DIR"] = d1
    out = {}
    try:
        data.lock()
        ab = data.load_bars("afl")
        bk = sim.Book(ab, "afl")
        sm, ss = 1e-4, 2e-4
        so, sc = D1C["spread_bps_open"] * 1e-4, D1C["spread_bps_close"] * 1e-4    # spread at an open (the session's:
        # 56 bp since kit v2.2 fix V22-1, was 25) and at a close (12 bp)
        f_div = float(dv[(dv.key == "afl") & (dv.ex_date == "2019-05-21")].fraction.iloc[0])
        P = 40.0
        c = _d1cm(P)                                            # 2019: after the split, 0.03 USD a share binds
        # (1) long and short, signal at Friday 2019-05-17's close, in at Monday's open, out 2 sessions later (Wednesday
        # open), across the ex-date Tuesday 2019-05-21: 2 nights
        sig = pd.DataFrame({"known_at": [_ny_at("2019-05-17", "16:00")] * 2, "side": [1, -1]})
        t = sim.simulate(sig, bk, market="afl", exit=("sessions", 2), stop=("bps", 900), mode="every")
        fl = (P + so * P / 2 + c) * (1 + sm); xl = (P - so * P / 2 - c) * (1 - sm)
        swl = D1C["swap_long"] / 360 * fl * 2 - 0.7 * f_div * fl
        fs = (P - so * P / 2 - c) * (1 - sm); xs = (P + so * P / 2 + c) * (1 + sm)
        sws = D1C["swap_short"] / 360 * fs * 2 + f_div * fs
        want = {1: (fl, xl, (xl - fl - swl) / fl * 1e4, swl / fl * 1e4), -1: (fs, xs, (fs - xs - sws) / fs * 1e4, sws / fs * 1e4)}
        ok1 = len(t) == 2 and all(
            abs(r.entry_px - want[r.side][0]) < 1e-10 and abs(r.exit_px - want[r.side][1]) < 1e-10 and
            abs(r.net_bp - want[r.side][2]) < 1e-8 and abs(r.swap_bp - want[r.side][3]) < 1e-8 and r.reason == "time" and
            r.entry_time == _ny_open("2019-05-20") and r.exit_time == _ny_open("2019-05-22") and r.hold_tdays == 2
            for r in t.itertuples())
        rt = costs.round_trip("afl", 1, P, P, _ny_open("2019-05-20"), _ny_open("2019-05-22"))
        ok1 &= abs(rt["cost"] - (fl - xl + swl)) < 1e-10 and abs(rt["commission_per_side"] - c) < 1e-15
        out["(1)"] = f"long {t.net_bp[0]:.2f} bp, short {t.net_bp[1]:.2f} bp (dividend {f_div * 1e4:.1f} bp)"
        check("v2.2 A1: a signal at a session's close enters at the NEXT session's open: spread 56 bp (half each side), "
              "commission max(0.03 USD a share, 2 USD an order) on top, 1 bp slippage; out at the open 2 sessions later "
              "(56 bp); swaps 7 % long / 3 % short x 2 nights; across the ex-date a short pays the dividend fraction x "
              "its fill, a long is credited 70 % of it; costs.round_trip gives the same", ok1, out["(1)"])
        # (2) across a Friday and a holiday (Memorial Day 2019-05-27): in Thursday 05-23, ('sessions', 2) out Tuesday
        # 05-28 open: 5 nights (Thu 1, Fri 3, Mon 1), 2 sessions held; ('bdays', 2) = Monday 09:30, a holiday: done at
        # Friday's close (12 bp) one session early, 1 night
        sg = pd.DataFrame({"known_at": [_ny_at("2019-05-22", "16:00")], "side": [1]})
        t2 = sim.simulate(sg, bk, market="afl", exit=("sessions", 2), stop=("bps", 900))
        t3 = sim.simulate(sg, bk, market="afl", exit=("bdays", 2), stop=("bps", 900))
        x3 = (P - sc * P / 2 - c) * (1 - sm)
        ok2 = (t2.exit_time[0] == _ny_open("2019-05-28") and t2.hold_tdays[0] == 2 and
               abs(t2.net_bp[0] - (xl - fl - D1C["swap_long"] / 360 * fl * 5) / fl * 1e4) < 1e-8 and
               int(costs.swap_nights(pd.DatetimeIndex([t2.entry_time[0]]), pd.DatetimeIndex([t2.exit_time[0]]), "Fri")[0]) == 5
               and t3.reason[0] == "time_close" and t3.exit_time[0] == _ny_at("2019-05-24", "16:00") and
               abs(t3.exit_px[0] - x3) < 1e-10 and t3.hold_tdays[0] == 1 and
               abs(t3.net_bp[0] - (x3 - fl - D1C["swap_long"] / 360 * fl * 1) / fl * 1e4) < 1e-8)
        check("v2.2 A2: across Friday and a holiday: ('sessions', 2) leaves at the open 2 SESSIONS later (Tuesday after "
              "Memorial Day), 5 swap nights (Friday triple), hold 2 sessions; ('bdays', 2) falls on the holiday and is "
              "done at the close before (one session early, the 12 bp close spread, 1 night)", ok2,
              f"sessions: out {t2.exit_time[0]}, {t2.net_bp[0]:.2f} bp; bdays: out {t3.exit_time[0]} {t3.reason[0]}, "
              f"{t3.net_bp[0]:.2f} bp")
        # (3) exit at a close: ('session_close', 0) the entry session's own close, ('session_close', 1) the next one
        t4 = sim.simulate(pd.concat([sg, sg]).assign(side=[1, -1]), bk, market="afl", exit=("session_close", 0),
                          stop=("bps", 900), mode="every")
        t5 = sim.simulate(sg, bk, market="afl", exit=("session_close", 1), stop=("bps", 900))
        xc_s = (P + sc * P / 2 + c) * (1 + sm)
        ok3 = (list(t4.reason) == ["session_close"] * 2 and all(t4.exit_time == _ny_at("2019-05-23", "16:00")) and
               abs(t4.net_bp[0] - (x3 - fl) / fl * 1e4) < 1e-8 and abs(t4.net_bp[1] - (fs - xc_s) / fs * 1e4) < 1e-8 and
               (t4.hold_tdays == 0).all() and t5.exit_time[0] == _ny_at("2019-05-24", "16:00") and t5.hold_tdays[0] == 1
               and abs(t5.net_bp[0] - (x3 - fl - D1C["swap_long"] / 360 * fl * 1) / fl * 1e4) < 1e-8)
        check("v2.2 A3: an exit at a close (('session_close', N): the close of the session N sessions after the entry's) "
              "pays the 12 bp close spread, no night for the same session, 1 night for the next", ok3,
              f"same-day long {t4.net_bp[0]:.2f} bp, short {t4.net_bp[1]:.2f} bp; next day {t5.net_bp[0]:.2f} bp")
        # (4) stops: entry Monday 2019-06-10 (signal Friday 06-07's close), D20 = 1.0 (flat ranges), stop 1.5 x D20
        bb = b.copy()
        d_in, d_hit = _ny_open("2019-06-11"), _ny_open("2019-06-18")
        bb.loc[d_in, "low"] = 37.0                               # Tuesday: touched inside the day
        bb.loc[d_hit, ["open", "high", "low", "close"]] = [37.0, 37.5, 36.5, 37.2]   # Tuesday 06-18: opens beyond the stop
        bb.loc[_ny_open("2019-06-25"), ["high", "low"]] = [45.0, 35.0]                # stop and target in one bar
        _write_d1(d1, "afl", bb)
        bk2 = sim.Book(data.load_bars("afl"), "afl")
        sa = pd.DataFrame({"known_at": [_ny_at("2019-06-07", "16:00")], "side": [1]})
        t6 = sim.simulate(sa, bk2, market="afl", exit=("sessions", 5), stop=("d20", 1.5))
        st6 = fl - 1.5
        b_wed = (37.0 - so * 37.0 / 2 - _d1cm(37.0)) * (1 - ss)
        t7 = sim.simulate(pd.DataFrame({"known_at": [_ny_at("2019-06-11", "08:00")], "side": [1]}), bk2, market="afl",
                          exit=("sessions", 5), stop=("d20", 1.0))    # known before the open: in at Tuesday's open
        t8 = sim.simulate(pd.DataFrame({"known_at": [_ny_at("2019-06-21", "16:00")], "side": [1]}), bk2, market="afl",
                          exit=("sessions", 5), stop=("d20", 1.5), target=("d20", 2.0))
        ok4 = (t6.reason[0] == "stop" and abs(t6.d20[0] - 1.0) < 1e-12 and abs(t6.exit_px[0] - st6 * (1 - ss)) < 1e-10
               and t6.exit_time[0] == _ny_at("2019-06-11", "16:00") and t6.hold_tdays[0] == 1 and
               t7.reason[0] == "stop" and t7.exit_time[0] == _ny_at("2019-06-11", "16:00") and
               abs(t7.exit_px[0] - (fl - 1.0) * (1 - ss)) < 1e-10)
        t9 = sim.simulate(pd.DataFrame({"known_at": [_ny_at("2019-06-14", "16:00")], "side": [1]}), bk2, market="afl",
                          exit=("sessions", 5), stop=("d20", 1.5))
        ok4 &= (t9.reason[0] == "stop_gap" and abs(t9.exit_px[0] - b_wed) < 1e-10 and
                t9.exit_time[0] == _ny_at("2019-06-18", "16:00") and abs(t9.d20[0] - (19 * 1.0 + 3.5) / 20) < 1e-12)
        ok4 &= t8.reason[0] == "stop" and t8.exit_time[0] == _ny_at("2019-06-25", "16:00")
        check("v2.2 A4: a stop is checked on the day's high and low (from the entry session on): touched inside a day it "
              "fills at the stop level minus 2 bp, at the session's close time; a session opening beyond it fills at its "
              "(bid) open minus 2 bp ('stop_gap'); stop and target touched in one bar: the stop", ok4,
              f"inside {t6.exit_px[0]:.4f} (stop {st6:.4f}); gap {t9.exit_px[0]:.4f}; both {t8.reason[0]}")
        # (5) the per-share commission on split-adjusted prices: afl's 2:1 split of 2018-03-19; Yahoo's 20 USD of
        # February 2018 was 40 USD traded then, so a real share is 2 adjusted units: 0.015 USD per adjusted unit; after
        # the split 0.03; at 100 USD (Yahoo) the 2 USD minimum binds whatever the share count
        _write_d1(d1, "afl", b)
        bk3 = sim.Book(data.load_bars("afl"), "afl")
        s5 = pd.DataFrame({"known_at": [_ny_at("2018-02-14", "16:00"), _ny_at("2018-04-10", "16:00")], "side": [1, 1]})
        t10 = sim.simulate(s5, bk3, market="afl", exit=("sessions", 1), stop=("bps", 900), mode="every")
        f_a = (20 + so * 20 / 2 + 0.015) * (1 + sm)
        f_b = (20 + so * 20 / 2 + 0.03) * (1 + sm)
        hi = costs.commission("afl", float(data.price_factor("afl", pd.DatetimeIndex([U("2018-02-15 14:30")]))[0]), 100.0)
        ok5 = (abs(t10.entry_px[0] - f_a) < 1e-10 and abs(t10.entry_px[1] - f_b) < 1e-10 and
               abs(_d1cm(20.0, 0.5) - 0.015) < 1e-15 and abs(float(hi) - 2 * 100 / costs.trade_notional("afl")) < 1e-15 and
               abs(float(data.price_factor("afl", pd.DatetimeIndex([U("2018-03-16 14:30")]))[0]) - 0.5) < 1e-15 and
               float(data.price_factor("afl", pd.DatetimeIndex([U("2018-03-19 13:30")]))[0]) == 1.0)
        check("v2.2 A5: the per-share commission at the price traded then: before afl's 2:1 split (2018-03-19) a Yahoo "
              "price of 20 USD is 40 USD a real share, so 0.03 USD per real share = 0.015 per adjusted unit; 0.03 after it; "
              "the 2 USD minimum (at 100 USD: 4.17 bp a side) does not depend on the share count", ok5,
              f"fills {t10.entry_px[0]:.5f} / {t10.entry_px[1]:.5f}; minimum at 100 USD {float(hi):.5f}")
        # (6) stress and gross of one trade: spread, commission and slippage x1.5, swaps and dividends unchanged; gross 0
        r_s = costs.round_trip("afl", 1, P, P, _ny_open("2019-05-20"), _ny_open("2019-05-22"), scenario="stress")
        fl15 = (P + 1.5 * so * P / 2 + 1.5 * c) * (1 + 1.5 * sm); xl15 = (P - 1.5 * so * P / 2 - 1.5 * c) * (1 - 1.5 * sm)
        sw15 = D1C["swap_long"] / 360 * fl15 * 2 - 0.7 * f_div * fl15
        check("v2.2 A6: stress x1.5 (spread, commission, slippage; swaps and dividends as net) and gross 0 for the class",
              abs(r_s["cost"] - (fl15 - xl15 + sw15)) < 1e-10 and abs(t.stress_bp[0] - (xl15 - fl15 - sw15) / fl15 * 1e4) < 1e-8
              and t.gross_bp[0] == 0.0 and costs.round_trip("afl", 1, P, P, _ny_open("2019-05-20"), _ny_open("2019-05-22"),
                                                           scenario="gross")["cost"] == 0.0,
              f"stress {t.stress_bp[0]:.2f} bp")
        rt_bp = costs.round_trip("afl", 1, P, P, _ny_open("2019-07-09"), _ny_open("2019-07-10"))["cost_bp"]
        NUMBERS["d1_round_trip_bp_afl_40usd_1night"] = round(rt_bp, 2)
    finally:
        os.environ.pop("EXPLORE_D1_DIR", None)
        data.lock()


def test_v22_daily_data_and_sessions():
    """Kit v2.2 A: data.load_bars of a universe share (prepared daily file, period lock, no row before in_universe_from,
    known_at = the session's close, 13:00 on a half day, validation years refused until the splits are listed, a clear
    error for a missing file); D20 of 20 sessions; the exchange calendar by rule; ('sessions', N) on the hourly share
    bars (same clock N sessions later, holidays skipped); hours and clock exits refused on daily bars."""
    d1 = _d1_folder("d1_data")
    f = _flat_d1(30.0, "2016-01-01", "2021-12-31")
    extra = pd.DataFrame({"open": 30.0, "high": 30.5, "low": 29.5, "close": 30.0, "volume": 390.0, "shares": 1e6},
                         index=pd.DatetimeIndex([_ny_open("2022-01-03"), _ny_open("2022-01-04")]))
    _write_d1(d1, "amcr", pd.concat([f, extra]))                 # holds 2022 rows on purpose
    fv = pd.concat([extra, pd.DataFrame({"open": 30.0, "high": 30.5, "low": 29.5, "close": 30.0, "volume": 390.0,
                                         "shares": 1e6}, index=pd.DatetimeIndex([_ny_open("2026-01-05")]))])
    _write_d1(d1 + "_val", "amcr", fv)
    os.environ["EXPLORE_D1_DIR"] = d1
    real = data.http_get

    def no_net(url, **kw):
        raise AssertionError("a daily share made a request: " + url)
    data.http_get = no_net
    try:
        data.lock()
        a = data.load_bars("amcr")
        ny = a.index.tz_convert(NYZ)
        half = a[a.volume == 210]
        ok = (a.index.min() == _ny_open("2019-06-07") and a.index.max() < U("2022-01-01") and
              (ny.hour * 60 + ny.minute == 570).all() and a.attrs["bar"] == "session" and a.attrs["price_is"] == "mid" and
              a.attrs["in_universe_from"] == "2019-06-07" and "known_at" in a and
              (pd.DatetimeIndex(a.known_at).tz_convert(NYZ).hour[a.volume == 390] == 16).all() and
              (pd.DatetimeIndex(half.known_at).tz_convert(NYZ).hour == 13).all() and len(half) > 0 and
              _ny_at("2019-11-29", "13:00") in set(pd.DatetimeIndex(half.known_at)))
        check("v2.2 A7: data.load_bars(universe key) reads the prepared daily file with no request, < 2022 while locked, "
              "no bar before the share's in_universe_from (amcr: 2019-06-07; the 2016-2019 rows are cut, not returned "
              "as history); index = 09:30 New York, known_at = 16:00 (13:00 on a half day: 2019-11-29)", ok,
              f"{len(a)} bars from {a.index.min()}, {len(half)} half days")
        bk = sim.Book(a, "amcr")
        s20 = pd.DataFrame({"known_at": pd.DatetimeIndex(a.known_at.iloc[[18, 19, 20]]), "side": [1, 1, 1]})
        tt = sim.simulate(s20, bk, market="amcr", exit=("sessions", 1), stop=("d20", 1.0), mode="every")
        cnt = tt.attrs["counts"]["amcr"]
        check("v2.2 A8: D20 = the mean daily range of the 20 sessions before the entry bar: none for the first 20 "
              "sessions after inclusion (the signal is dropped and counted as no_d20), 1.0 on flat bars after",
              cnt["no_d20"] == 1 and len(tt) == 2 and abs(tt.d20.iloc[0] - 1.0) < 1e-12 and
              tt.entry_time.iloc[0] == a.index[20], json.dumps(cnt))
        errs = []
        try:
            data.load_bars("aes")
            errs.append("no error")
        except FileNotFoundError as e:
            errs.append("ok" if "universe" in str(e) and "aes.parquet" in str(e) else str(e)[:80])
        bad = f.copy()
        bad.index = bad.index + pd.Timedelta(minutes=30)
        _write_d1(d1, "aee", bad)
        try:
            data.load_bars("aee")
            errs.append("no error")
        except data.DataGap:
            errs.append("ok")
        try:
            sim.simulate(s20, bk, market="amcr", exit=("hours", 6), stop=("d20", 1.0))
            errs.append("hours accepted")
        except ValueError as e:
            errs.append("ok" if "sessions" in str(e) else str(e)[:80])
        try:
            sim.simulate(s20, bk, market="amcr", exit=sim.event_exit(pd.DatetimeIndex([], tz="UTC"), ("hours", 30)),
                         stop=("d20", 1.0))
            errs.append("event hours accepted")
        except ValueError:
            errs.append("ok")
        idea = os.path.join(TMP, "ideas", "980_d1val")
        os.makedirs(idea, exist_ok=True)
        json.dump(VALDECL, open(os.path.join(idea, "val_declared.json"), "w"))
        json.dump({"verdict": "pass"}, open(os.path.join(idea, "results.json"), "w"))
        data.unlock_val(idea)
        try:
            data.load_bars("amcr")
            errs.append("validation read accepted")
        except data.PeriodError:
            errs.append("ok")
        data.lock()
        check("v2.2 A9: a missing daily file raises FileNotFoundError naming it; a bar not at 09:30 New York raises "
              "DataGap; ('hours', N) and an event max_hold in hours are refused on daily bars; after unlock_val a daily "
              "share is refused (PeriodError) until the 2022-2025 splits and dividends are listed", errs == ["ok"] * 5,
              str(errs))
        cal = data.us_sessions("2016-01-01", "2023-06-30")
        hd = [str(x.date()) for x in cal.index[cal.half_day]]
        want_hd = ["2016-11-25", "2017-07-03", "2017-11-24", "2018-07-03", "2018-11-23", "2018-12-24", "2019-07-03",
                   "2019-11-29", "2019-12-24", "2020-11-27", "2020-12-24", "2021-11-26"]
        dts = set(cal.index)
        check("v2.2 C: data.us_sessions, the exchange calendar by rule: 1,511 sessions in 2016-2021 (as the daily bars), "
              "the 12 half days at 13:00, Good Friday, the 2018-12-05 closure and observed holidays out, nothing at or "
              "after the period end while locked",
              len(cal) == 1511 and hd == want_hd and cal.index.max() <= pd.Timestamp("2021-12-31") and
              pd.Timestamp("2018-12-05") not in dts and pd.Timestamp("2019-04-19") not in dts and
              pd.Timestamp("2021-12-24") not in dts and pd.Timestamp("2021-12-31") in dts and
              pd.Timestamp("2017-01-02") not in dts and pd.Timestamp("2020-07-03") not in dts and
              (cal.close_utc - cal.open_utc).max() == pd.Timedelta(minutes=390),
              f"{len(cal)} sessions, half days {hd}")
    finally:
        data.http_get = real
        os.environ.pop("EXPLORE_D1_DIR", None)
        data.lock()
    # ('sessions', N) on the hourly share bars of the lab's 40: same clock N sessions later, by the market's own days
    jb = flat_share(150.0, "2019-05-01", "2019-08-01")
    jb = jb[jb.index.tz_convert(NYZ).normalize().tz_localize(None) != pd.Timestamp("2019-07-04")]
    jb = jb[~((jb.index.tz_convert(NYZ).normalize().tz_localize(None) == pd.Timestamp("2019-07-03")) &
              (jb.index.tz_convert(NYZ).hour >= 13))]                                   # the 13:00 half day
    bkj = sim.Book(jb, "jpm")
    sj = pd.DataFrame({"known_at": [_ny_at("2019-07-02", "10:00"), _ny_at("2019-07-02", "14:00")], "side": [1, 1]})
    ts = sim.simulate(sj, bkj, market="jpm", exit=("sessions", 2), stop=("bps", 500), mode="every")
    tb = sim.simulate(sj, bkj, market="jpm", exit=("bdays", 2), stop=("bps", 500), mode="every")
    t1 = sim.simulate(sj, bkj, market="jpm", exit=("sessions", 1), stop=("bps", 500), mode="every")
    check("v2.2 A10: ('sessions', N) on hourly share bars: the same clock time N of the market's own sessions later "
          "(Tuesday 10:00 + 2 sessions = Friday 10:00 over the 4 July holiday; 14:00 + 1 session on the 13:00 half day "
          "falls to the close of its last bar, 13:00), hold = sessions; ('bdays', 2) unchanged (the holiday: the close "
          "before, hold in business days)",
          list(ts.exit_time) == [_ny_at("2019-07-05", "10:00"), _ny_at("2019-07-05", "14:00")] and
          list(ts.hold_tdays) == [2, 2] and list(t1.exit_time) == [_ny_at("2019-07-03", "10:00"),
                                                                   _ny_at("2019-07-03", "13:00")] and
          list(t1.reason) == ["time", "time_close"] and
          list(tb.exit_time) == [_ny_at("2019-07-03", "13:00"), _ny_at("2019-07-03", "13:00")] and
          list(tb.reason) == ["time_close", "time_close"] and ts.attrs["hold_count"] == "sessions" and
          tb.attrs["hold_count"] == "bdays",
          f"sessions {[str(x) for x in ts.exit_time]}; bdays {[str(x) for x in tb.exit_time]}")


def test_v22_daily_traps():
    """Kit v2.2 A traps: on daily bars a signal stamped at the session's OPEN but computed from its close is caught by
    the truncation test given row_len='known_at' (the row length a run must pass); a shorter row length is refused;
    a rule on Yahoo's price level or on the raw share count fails (the levels carry later splits), a rule on ratios or
    on the dollar volume passes, also on a long frame of several shares."""
    d1 = _d1_folder("d1_traps")
    keys = ["aes", "aee", "aep"]
    for i, k in enumerate(keys):
        _write_d1(d1, k, synth.d1_bars("2016-01-01", "2021-12-31", seed=300 + i, price=40.0 + 10 * i))
    os.environ["EXPLORE_D1_DIR"] = d1
    try:
        data.lock()
        bs = {k: data.load_bars(k) for k in keys}
        b = bs["aes"]
        bk = sim.Book(b, "aes")
        KA = "known_at"

        def bad(d):
            x = d["aes"]
            return pd.DataFrame({"known_at": x.index, "side": np.sign(x.close - x.open).replace(0, 1).astype(int).to_numpy()})

        def good(d):
            x = d["aes"]
            return pd.DataFrame({"known_at": pd.DatetimeIndex(x[KA]),
                                 "side": np.sign(x.close - x.open).replace(0, 1).astype(int).to_numpy()})
        tb = checks.truncation_test(bad, {"aes": b}, row_len={"aes": "known_at"})
        tg = checks.truncation_test(good, {"aes": b}, row_len={"aes": "known_at"})
        rb = sim.simulate(bad({"aes": b}).assign(market="aes"), {"aes": bk}, exit=("sessions", 1), stop=("d20", 2.0))
        rg = sim.simulate(good({"aes": b}).assign(market="aes"), {"aes": bk}, exit=("sessions", 1), stop=("d20", 2.0))
        refused = []
        for rl in (pd.Timedelta(hours=1), pd.Timedelta(0), pd.Timedelta(hours=6)):
            try:
                checks.truncation_test(good, {"aes": b}, row_len={"aes": rl})
                refused.append(False)
            except ValueError:
                refused.append(True)
        long_ok = checks.truncation_test(good, {"aes": b}, row_len={"aes": pd.Timedelta(hours=6, minutes=30)})["pass"]
        check("v2.2 A trap: a daily signal stamped at the session's open (09:30) but computed from its close is caught by "
              "the truncation test with row_len='known_at'; stamped at the close (known_at) it passes and has no edge; "
              "a row_len of 1 h, 0 or 6 h is refused for daily bars (6.5 h is accepted)",
              not tb["pass"] and tg["pass"] and stats.t_stat(rb.R_gross) > 10 and abs(stats.t_stat(rg.R_gross)) < 3.5 and
              all(refused) and long_ok,
              f"t gross bad {stats.t_stat(rb.R_gross):.1f}, good {stats.t_stat(rg.R_gross):.2f}; failed cuts bad "
              f"{tb['n_failed_cuts']}/{len(tb['cuts'])}")
        lv = float(b.close.median())
        sh = float(b.shares.median())
        dv = float((b.close * b.shares).median())

        def mk(rule):
            def f_(d):
                x = d["aes"]
                m = rule(x).to_numpy()
                return pd.DataFrame({"known_at": pd.DatetimeIndex(x[KA])[m], "side": 1})
            return f_
        rlev = checks.truncation_test(mk(lambda x: (x.close > lv) & (x.close.shift() <= lv)), {"aes": b},
                                      row_len={"aes": "known_at"}, n_signal_cuts=30, n_random_cuts=30)
        rsh = checks.truncation_test(mk(lambda x: x.shares > sh), {"aes": b}, row_len={"aes": "known_at"},
                                     n_signal_cuts=30, n_random_cuts=30)
        rdv = checks.truncation_test(mk(lambda x: x.close * x.shares > dv), {"aes": b}, row_len={"aes": "known_at"})
        rrt = checks.truncation_test(mk(lambda x: (x.close / x.close.shift() - 1).abs() > 0.02), {"aes": b},
                                     row_len={"aes": "known_at"})
        lb = data.long_bars(bs)

        def lgood(d):
            x = d["all"]
            r = x.groupby("market").close.pct_change()
            m = (r.abs() > 0.02).to_numpy()
            return pd.DataFrame({"known_at": pd.DatetimeIndex(x[KA])[m], "side": 1, "market": x.market.to_numpy()[m]})

        def llev(d):
            x = d["all"]
            m = (x.close > 45.0).to_numpy()
            return pd.DataFrame({"known_at": pd.DatetimeIndex(x[KA])[m], "side": 1, "market": x.market.to_numpy()[m]})
        rl1 = checks.truncation_test(lgood, {"all": lb}, row_len={"all": "known_at"})
        rl2 = checks.truncation_test(llev, {"all": lb}, row_len={"all": "known_at"}, n_signal_cuts=30, n_random_cuts=30)
        try:
            checks.truncation_test(lgood, {"all": lb}, row_len={"all": pd.Timedelta(hours=1)})
            lref = False
        except ValueError:
            lref = True
        check("v2.2 A trap: Yahoo's levels carry later splits, so the truncation test re-bases every cut copy of daily "
              "share bars (prices x 2, shares / 2): a rule on the price level or on the raw share count fails; a rule "
              "on ratios and one on the dollar volume (close x shares) pass; the same on a long frame of 3 shares "
              "(data.long_bars), whose row_len must also be 'known_at'",
              not rlev["pass"] and not rsh["pass"] and rdv["pass"] and rrt["pass"] and rl1["pass"] and not rl2["pass"]
              and lref and rrt["n_signals"] > 50 and rl1["n_signals"] > 150,
              f"level {rlev['n_failed_cuts']} failed cuts, shares {rsh['n_failed_cuts']}, dollar volume "
              f"{rdv['n_failed_cuts']}, ratio {rrt['n_failed_cuts']}; long frame ratio {rl1['n_failed_cuts']}, level "
              f"{rl2['n_failed_cuts']}")
    finally:
        os.environ.pop("EXPLORE_D1_DIR", None)
        data.lock()


def _d1_world(folder, edge, seed, per_sector=4, p_event=0.06, hold=5):
    """Synthetic daily world of 4 shares per sector (44 > 40 markets, 11 groups): each share gets random event days
    (known at that session's close, value +1/-1: a calendar like the 8-K one) and, when edge > 0, a planted drift of
    edge x value per session on the next `hold` sessions. Files written to `folder` (data.load_bars reads them)."""
    u = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "universe_us.csv"), dtype=str)
    keys = sorted(u.groupby("sector").key.apply(lambda s: list(s[:per_sector])).sum())
    rng = np.random.default_rng(seed)
    cal = data.us_sessions("2016-01-01", "2021-12-31")
    days = cal.index
    ev_d, ev_k, ev_v = [], [], []
    for i, k in enumerate(keys):
        t0 = pd.Timestamp(costs.spec(k)["in_universe_from"])
        on = (rng.random(len(days)) < p_event) & (days >= t0) & (np.arange(len(days)) < len(days) - hold - 1)
        v = rng.choice([-1, 1], len(days))
        drift = np.zeros(len(days))
        for p in np.flatnonzero(on):
            drift[p + 1:p + 1 + hold] += edge * v[p]
        _write_d1(folder, k, synth.d1_bars("2016-01-01", "2021-12-31", seed=seed * 1000 + i, price=30.0 + i,
                                           drift_d=drift))
        ev_d += list(days[on]); ev_k += [k] * int(on.sum()); ev_v += list(v[on])
    ev = data.event_table(pd.DatetimeIndex(ev_d), known=data.rule_local_close("16:00"), min_lag=pd.Timedelta(hours=16),
                          market=ev_k, value=np.asarray(ev_v, float))
    return keys, ev


def _d1_build(d):
    """The whole signal table of the planted world: an event of a share, confirmed by its session's close-to-close move
    in the event's direction (a ratio of the bars), known at the event's known_at (the session's close)."""
    x, ev = d["bars"], d["events"]
    r = x.groupby("market").close.pct_change()
    day = pd.DatetimeIndex(x.index).tz_convert(NYZ).normalize().tz_localize(None)
    bt = pd.DataFrame({"market": x.market.to_numpy(), "day": day, "r": r.to_numpy()})
    e = pd.DataFrame({"market": ev.market.to_numpy(), "day": pd.DatetimeIndex(ev.obs_date), "known_at": ev.index,
                      "v": ev.value.to_numpy()})
    m = e.merge(bt, on=["market", "day"], how="inner")
    m = m[np.sign(m.r.to_numpy()) == m.v.to_numpy()]
    return pd.DataFrame({"known_at": pd.DatetimeIndex(m.known_at), "side": m.v.astype(int).to_numpy(),
                         "market": m.market.to_numpy()}).sort_values(["known_at", "market"]).reset_index(drop=True)


def _d1_chain(idea, folder, edge, seed, decl, ledger):
    keys, ev = _d1_world(folder, edge, seed)
    os.environ["EXPLORE_D1_DIR"] = folder
    bs = {k: data.load_bars(k) for k in keys}
    d = {"bars": data.long_bars(bs), "events": ev}
    tr = checks.truncation_test(_d1_build, d, row_len={"bars": "known_at", "events": pd.Timedelta(0)})
    sig = _d1_build(d)
    bk = sim.books(bs)
    rule = dict(exit=("sessions", 5), stop=("d20", 2.0))
    main = sim.simulate(sig, bk, **rule)
    nb = {"s3": sim.simulate(sig, bk, exit=("sessions", 3), stop=("d20", 2.0)),
          "s4": sim.simulate(sig, bk, exit=("sessions", 4), stop=("d20", 2.0)),
          "k15": sim.simulate(sig, bk, exit=("sessions", 5), stop=("d20", 1.5)),
          "k3": sim.simulate(sig, bk, exit=("sessions", 5), stop=("d20", 3.0))}
    every = sim.simulate(sig, bk, mode="every", **rule)
    nl = stats.null_test(main, bk, n_draws=2000, **rule)
    _declare(idea, decl)
    res = judge.verdict(idea, main, nb, every, nl, truncation=tr, corr="compute", ten=TEN, n_configs=5,
                        data_desc="synthetic daily shares 2017-2021", ledger=ledger, groups="sector")
    return res, main, nb, every, nl, tr, keys


def test_v22_daily_noise():
    """Kit v2.2: random-signal rules on synthetic daily share bars have no edge and the null stays calibrated (40
    rules: random sessions and sides, exits of 1-5 sessions or at a close, stops 1-2 x D20; 1,000 draws each)."""
    d1 = _d1_folder("d1_noise_null")
    keys = ["aes", "aee", "aep", "awk"]
    for i, k in enumerate(keys):
        _write_d1(d1, k, synth.d1_bars("2016-01-01", "2021-12-31", seed=500 + i, price=35.0 + 5 * i))
    os.environ["EXPLORE_D1_DIR"] = d1
    tg, pct = [], []
    try:
        data.lock()
        rng = np.random.default_rng(21)
        for k in keys:
            b = data.load_bars(k)
            bk = {k: sim.Book(b, k)}
            for r in range(10):
                pick = rng.random(len(b)) < 0.25
                sg = pd.DataFrame({"known_at": pd.DatetimeIndex(b.known_at)[pick], "side": rng.choice([-1, 1], int(pick.sum())),
                                   "market": k})
                ex = [("sessions", 1), ("sessions", 3), ("sessions", 5), ("session_close", 1)][r % 4]
                rule = dict(exit=ex, stop=("d20", [1.0, 2.0][r % 2]))
                m = sim.simulate(sg, bk, **rule)
                tg.append(stats.t_stat(m.R_gross))
                pct.append(stats.null_test(m, bk, n_draws=1000, seed=r, **rule)["percentile"])
    finally:
        os.environ.pop("EXPLORE_D1_DIR", None)
        data.lock()
    tg, pct = np.array(tg), np.array(pct)
    NUMBERS["d1_noise"] = {"rules": len(tg), "t_gross_mean": float(tg.mean()), "t_gross_sd": float(tg.std()),
                           "null_ge_97.5": int((pct >= 97.5).sum()), "null_mean": float(pct.mean()),
                           "null_ks_p": float(st.kstest(pct / 100, "uniform").pvalue)}
    check("v2.2 noise: 40 random-signal rules on synthetic daily share bars: gross t looks standard normal, the null's "
          "percentile is uniform (KS) and reaches 97.5 in about 2.5 % of them",
          abs(tg.mean()) < 0.5 and 0.6 < tg.std() < 1.5 and (pct >= 97.5).sum() <= 4 and
          NUMBERS["d1_noise"]["null_ks_p"] > 0.001, json.dumps(NUMBERS["d1_noise"]))


def test_v22_planted_chain_and_groups():
    """Kit v2.2 A + B: the whole chain on SYNTHETIC daily bars of 44 universe shares in 11 sectors (declared.json with
    groups 'sector', truncation test on the long bar frame and the event calendar, simulate ('sessions', 5), 4
    neighbours, every-signal, the same-day null, verdict with groups, ledger_add on a COPY of LEDGER.md): a planted edge
    is found, pure noise is not; the group bars replace the market bars above 40 markets; no declared groups, other
    groups or fewer than 8 groups raise; 40 markets or fewer ignore groups; results.json is valid JSON."""
    t0 = time.time()
    led = os.path.join(TMP, "LEDGER_copy_v22.md")
    shutil.copy(judge.LEDGER, led)
    tot0 = judge.ledger_total(led)
    decl = {"idea": "990 planted daily drift (synthetic)", "groups": "sector", "markets": "44 universe shares",
            "configurations": 5}
    try:
        data.lock()
        idea = os.path.join(TMP, "ideas", "990_d1_planted")
        res, main, nb, every, nl, tr, keys = _d1_chain(idea, _d1_folder("d1_planted"), 0.003, 7, decl, led)
        rj_txt = open(os.path.join(idea, "results.json")).read()

        def _no_const(c):
            raise ValueError(f"not JSON: {c}")
        rj = json.loads(rj_txt, parse_constant=_no_const)
        new = judge.ledger_add(5, res["ledger_line"], led)
        tail = open(led).read().rstrip("\n").splitlines()[-1]
        NUMBERS["d1_planted"] = {k: res["bars"][k]["value"] for k in res["bars"]}
        NUMBERS["d1_planted"].update(n=len(main), seconds=round(time.time() - t0, 1),
                                     groups=res["groups"]["n_groups"] if res.get("groups") else None)
        check("v2.2 chain: a planted drift on synthetic daily bars of 44 shares (11 sectors) is found: every bar passes "
              "with the group bars (groups_positive>=65%, max_group_share<=25%) instead of the market bars; the hold "
              "bar counts 5 sessions; results.json (valid JSON) records the 11 groups; the ledger line names the class "
              "and its count, not 44 tickers; ledger_add on a copy of LEDGER.md adds the 5 configurations",
              res["verdict"] != "fail" and "groups_positive>=65%" in res["bars"] and "max_group_share<=25%" in res["bars"]
              and not any(k.startswith("markets_positive") or k.startswith("max_market_share") for k in res["bars"]) and
              res["bars"]["hold<=5d"]["value"] == 5 and rj["groups"]["n_groups"] == 11 and
              rj["hold_count"] == "sessions" and "us_shares_d1 class (44 shares)" in res["ledger_line"] and
              "PROVISIONAL COSTS (us_shares_d1 class (44 shares))" in res["ledger_line"] and
              not any(f" {k}," in res["ledger_line"] for k in keys[:5]) and new == tot0 + 5 and tail == res["ledger_line"]
              and tr["pass"] and tr["density_ok"] and nl["joint_groups"] > 0,
              f"{res['verdict']} {res['failed_bars']}; {res['ledger_line'][:260]}")
        check("V22-1/V22-2 (ledger): the line of a class basket gives the class's spreads (56 bp at the open, 12 bp at "
              "a close) and says the per-share commission on Yahoo prices is pessimistic for shares split after 2021; "
              "results.json says the minimum-commission sensitivity was not run",
              "us_shares_d1: spread 56 bp at the open, 12 bp at a close" in res["ledger_line"] and
              "pessimistic for shares split after 2021" in res["ledger_line"] and
              str(rj.get("commission_min_only", "")).startswith("not run"), res["ledger_line"][-330:])
        # B: the groups' guards (write=False: judged again on the same trades)
        kw = dict(truncation=tr, corr=0.0, write=False, ledger=led, n_configs=5)
        errs = []
        bare = os.path.join(TMP, "ideas", "991_nogroups")
        _declare(bare, {"idea": "991 no groups"})
        for gname, gdir, gval in (("no declared groups", bare, None), ("groups= alone", bare, "sector"),
                                  ("other groups", idea, {k: ("X" if i == 0 else costs.spec(k)["sector"])
                                                          for i, k in enumerate(keys)})):
            try:
                judge.verdict(gdir, main, nb, every, nl, groups=gval, **kw)
                errs.append(f"{gname}: accepted")
            except ValueError as e:
                want_txt = "differ" if gname == "other groups" else "Baskets of many markets"
                errs.append("ok" if want_txt in str(e) else str(e)[:90])
        seven = os.path.join(TMP, "ideas", "992_seven")
        _declare(seven, {"idea": "992 seven groups", "groups": {k: f"g{i % 7}" for i, k in enumerate(keys)}})
        try:
            judge.verdict(seven, main, nb, every, nl, **kw)
            errs.append("7 groups accepted")
        except ValueError as e:
            errs.append("ok" if "at least 8" in str(e) else str(e)[:90])
        sub = main[main.market.isin(keys[:40])].reset_index(drop=True)
        sub.attrs.update(main.attrs)
        r40 = judge.verdict(idea, sub, nb, every, nl, groups="sector", **kw)
        r_decl = judge.verdict(idea, main, nb, every, nl, **kw)          # groups read from declared.json alone
        check("v2.2 B: a basket of more than 40 markets without declared groups raises (naming the charter amendment), "
              "also with groups= alone; groups= that differ from declared.json raise; fewer than 8 groups raise; the "
              "declaration alone is enough; a basket of 40 markets ignores groups and keeps the market bars",
              errs == ["ok"] * 4 and "markets_positive>=65%" in r40["bars"] and "groups_positive>=65%" not in r40["bars"]
              and "ignored" in (r40.get("groups") or {}) and r_decl["bars"]["groups_positive>=65%"] ==
              res["bars"]["groups_positive>=65%"], str(errs))
        # the noise world through the same chain: it fails
        nidea = os.path.join(TMP, "ideas", "993_d1_noise")
        rn, mn, *_ = _d1_chain(nidea, _d1_folder("d1_noise"), 0.0, 8, dict(decl, idea="993 noise"), led)
        neg = mn.copy()
        neg["R"] = -neg.R.abs()
        neg.attrs.update(mn.attrs)
        judge.verdict(nidea, neg, None, None, None, corr=0.0, ledger=led)
        rjn = json.loads(open(os.path.join(nidea, "results.json")).read(), parse_constant=_no_const)
        check("v2.2 chain: pure noise on the same synthetic universe through the same chain fails; a basket whose "
              "profit is <= 0 writes max_market_share_of_profit as null (valid JSON, C) and its group share bar fails",
              rn["verdict"] == "fail" and rjn["main"]["max_market_share_of_profit"] is None and
              rjn["bars"]["max_group_share<=25%"]["pass"] is False,
              f"noise: {rn['failed_bars']}; n {len(mn)}, PF {stats.pf(mn.R):.2f}, null {rn['null']['percentile']:.1f}")
    finally:
        os.environ.pop("EXPLORE_D1_DIR", None)
        data.lock()


def test_v22_review_fixes():
    """Kit v2.2 review (verifier's issues V22-1 to V22-10): one check per fix, each failing on the kit before the fixes
    (scratch kit_v22/fix/kit_before) and passing after; an API the old kit lacks is a FAIL (_try), not a crash.
    Synthetic daily bars of universe keys only (no real price)."""
    NYc = "America/New_York"
    KA = "known_at"
    names = {
        1: "V22-1: the class's spread for an order at the session's open is at least the 75th percentile of the lab's 40 "
           "shares' modelled 09:30 first-minute spread (per-share medians 2017-2021) and their worst year's median, and "
           "its stress (x1.5) covers the costliest of the 40 (the universe's shares are smaller than the 40)",
        2: "V22-2: checks.min_commission_test re-simulates the same signals with the 2 USD minimum commission alone (the "
           "optimistic bound for shares split after 2021): a share Yahoo prices near 10 USD gains, one near 300 USD is "
           "unchanged; the report lists the shares whose median bar pays the per-share rate",
        3: "V22-3: a daily input without a known_at column (a close Series of data.load_bars, its frame with known_at "
           "dropped, a wide frame of closes named by ticker) is refused with row_len 0 (the open-stamped trap passed "
           "before); the same wide frame re-indexed to the closes takes row_len 0, or 6.5 h at its opens",
        4: "V22-4: data.daily_bars refuses the daily share bars (it stamped each close at 10:30 New York instead of "
           "16:00), also once their attrs are lost (known_at more than 1 h after the open)",
        5: "V22-5: a rule on price LEVELS compared across shares (long the shares below the day's median price, on "
           "data.long_bars) fails the truncation test, and so does a level rule on a wide frame of closes named by "
           "ticker; a cross-sectional rule on returns and dollar volumes passes; a wide frame of returns is refused "
           "(compute it inside build)",
        6: "V22-6: checks.shift_test on daily bars shifts by one session by default (24 h: the shifted run differs) and "
           "refuses a shift of 1 h (it moved no entry, so the test was silently a no-op)",
        7: "V22-7: on hourly share bars with bars after a half day's 13:00 close (the lab's 2019-07-03), ('sessions', 1) "
           "and ('session_close', 1) leave at 13:00, not at a later stray bar; a normal day keeps the same hour",
        8: "V22-8: data.session_moves gives each session's move with the ex-date's dividend added back and flags "
           "corporate actions: gen's 42 % special dividend of 2020-02-03 is a -42 % close-to-close move but a 0 total "
           "move, flagged; dd's 2019-06-03 spin-off record is flagged; other sessions are not",
        9: "V22-9: a prepared daily file whose times are a column (it loaded as 0 bars) or a tz-naive index (a raw "
           "ArrowInvalid) raises data.DataGap naming the file",
        10: "V22-10: the truncation test's re-basing plan of a long frame of daily shares holds one int32 code per row "
            "(4 bytes a row), not a boolean row mask per share (about 1 GB for 382 shares at full size)"}

    def c1():   # spread levels of the 40 are bp of price by year: no bar is read
        cal = data.us_sessions("2017-01-01", "2021-12-31")
        t9 = pd.DatetimeIndex([pd.Timestamp(f"{d.date()} 09:00").tz_localize(NYc) for d in cal.index]).tz_convert("UTC")
        yr = t9.tz_convert(NYc).year.to_numpy()
        per, by_year = {}, {}
        for k in sorted(k for k in costs.EXTRA if "splits" in costs.spec(k)):
            bp = costs.spread(k, np.full(len(t9), 100.0), t9) / 100.0 * 1e4
            per[k] = float(np.median(bp))
            for y in range(2017, 2022):
                by_year.setdefault(y, []).append(float(np.median(bp[yr == y])))
        p75 = float(np.percentile(list(per.values()), 75))
        worst = max(float(np.median(v)) for v in by_year.values())
        so = float(D1C["spread_bps_open"])
        NUMBERS["v22_open_spread_40"] = {"class": so, "p75": round(p75, 1), "worst_year": round(worst, 1),
                                         "max": round(max(per.values()), 1)}
        return (len(per) == 40 and so >= p75 and so >= worst and 1.5 * so >= max(per.values()),
                f"open spread {so:g} bp; the 40: P75 {p75:.1f}, worst year median {worst:.1f}, max "
                f"{max(per.values()):.1f} ({max(per, key=per.get)}), median {float(np.median(list(per.values()))):.1f}")
    _try(names[1], c1)
    d1 = _d1_folder("d1_review")
    keys = ["afl", "low", "key", "f", "nvr"]
    for i, k in enumerate(keys):
        _write_d1(d1, k, synth.d1_bars("2016-01-01", "2021-12-31", seed=500 + i, price=[40, 150, 15, 10, 300][i],
                                       vol_d=0.02))
    os.environ["EXPLORE_D1_DIR"] = d1
    try:
        data.lock()
        bs = {k: data.load_bars(k) for k in keys}
        b = bs["afl"]
        bk = sim.books(bs)
        rng = np.random.default_rng(11)
        sg = []
        for k in ("f", "nvr"):
            pick = np.sort(rng.choice(np.arange(30, len(bk[k].t) - 10), 150, replace=False))
            sg.append(pd.DataFrame({"known_at": pd.DatetimeIndex(bk[k].t_end[pick].astype("datetime64[ns]")).tz_localize("UTC"),
                                    "side": rng.choice([-1, 1], len(pick)), "market": k}))
        sg = pd.concat(sg).sort_values(["known_at", "market"]).reset_index(drop=True)
        rule = dict(exit=("sessions", 3), stop=("d20", 1.5))

        def c2():
            mc = checks.min_commission_test(sg, {k: bk[k] for k in ("f", "nvr")}, max_wait_h=96, **rule)
            mf = checks.min_commission_test(sg[sg.market == "f"], {"f": bk["f"]}, max_wait_h=96, **rule)
            mn = checks.min_commission_test(sg[sg.market == "nvr"], {"nvr": bk["nvr"]}, max_wait_h=96, **rule)
            return (mc["shares_paying_per_share_rate"] == ["f"] and mf["min_commission"]["mean_R"] > mf["base"]["mean_R"]
                    and mn["min_commission"] == mn["base"] and mc["base"]["n"] > 100 and mc["n_class_markets"] == 2,
                    f"f: mean R {mf['base']['mean_R']:.4f} -> {mf['min_commission']['mean_R']:.4f}; nvr equal "
                    f"{mn['min_commission'] == mn['base']}; per-share rate {mc['shares_paying_per_share_rate']}; "
                    f"{mc['base']['n']} trades")
        _try(names[2], c2)

        def trap_ser(x):          # close-to-close move stamped at its own bar's OPEN (index): a look-ahead
            r = x / x.shift(1) - 1
            s = r[r.abs() > 0.015]
            return pd.DataFrame({"known_at": pd.DatetimeIndex(s.index), "side": np.sign(s.to_numpy()).astype(int)})

        def trap_wide(x):
            st_ = (x / x.shift(1) - 1).stack()
            st_ = st_[st_.abs() > 0.015]
            return pd.DataFrame({"known_at": pd.DatetimeIndex(st_.index.get_level_values(0)),
                                 "market": st_.index.get_level_values(1), "side": np.sign(st_.to_numpy()).astype(int)}) \
                .sort_values(["known_at", "market"]).reset_index(drop=True)
        wide = pd.concat({k: bs[k]["close"] for k in keys}, axis=1)

        def c3():
            outs = []
            for nm, fn, x in (("series", trap_ser, b["close"]), ("no known_at", lambda d: trap_ser(d["close"]),
                                                                  b.drop(columns=[KA])), ("wide", trap_wide, wide)):
                try:
                    r = checks.truncation_test(fn, x, row_len=pd.Timedelta(0))
                    outs.append(f"{nm}: pass={r['pass']}")
                except ValueError as e:
                    outs.append(f"{nm}: refused" if "row_len" in str(e) else f"{nm}: {str(e)[:60]}")
            wk = wide.copy()
            wk.index = pd.DatetimeIndex(b[KA])                # values re-indexed to the time they are known
            r_hk = checks.truncation_test(trap_wide, wk, row_len=pd.Timedelta(0))
            r_h65 = checks.truncation_test(
                lambda x: trap_wide(x).assign(known_at=lambda t: t.known_at + pd.Timedelta(hours=6, minutes=30)),
                wide, row_len=pd.Timedelta(hours=6, minutes=30))
            return (outs == ["series: refused", "no known_at: refused", "wide: refused"] and r_hk["pass"] and
                    r_h65["pass"], f"{outs}; re-indexed honest {r_hk['pass']}, 6.5 h {r_h65['pass']}")
        _try(names[3], c3)

        def c4():
            e4 = []
            bare = b.copy()
            bare.attrs = {}
            for x in (b, bare):
                try:
                    data.daily_bars(x)
                    e4.append("accepted")
                except ValueError as e:
                    e4.append("refused" if "already one bar a SESSION" in str(e) else str(e)[:60])
            return e4 == ["refused", "refused"], str(e4)
        _try(names[4], c4)

        def c5():
            lb = data.long_bars(bs)

            def xs_level(x):
                med = x.groupby(level=0)["close"].transform("median")
                m = ((x["close"] < med) & ((x["close"] / x["open"] - 1).abs() > 0.005)).to_numpy()
                return pd.DataFrame({"known_at": pd.DatetimeIndex(x[KA])[m], "market": x["market"].to_numpy()[m],
                                     "side": 1}).sort_values(["known_at", "market"]).reset_index(drop=True)

            def xs_ratio(x):
                r = x.groupby("market").close.pct_change()
                med = r.groupby(level=0).transform("median")
                dv = x.close * x.shares
                m = ((r > med) & (dv > dv.groupby(level=0).transform("median")) & (r.abs() > 0.01)).to_numpy()
                return pd.DataFrame({"known_at": pd.DatetimeIndex(x[KA])[m], "market": x["market"].to_numpy()[m],
                                     "side": 1}).sort_values(["known_at", "market"]).reset_index(drop=True)

            def wide_level(x):
                lv = x.stack()
                lv = lv[lv > 40.0]
                return pd.DataFrame({"known_at": pd.DatetimeIndex(lv.index.get_level_values(0)) + pd.Timedelta(hours=7),
                                     "market": lv.index.get_level_values(1), "side": 1}) \
                    .sort_values(["known_at", "market"]).reset_index(drop=True)
            r5a = checks.truncation_test(xs_level, lb, row_len="known_at", n_signal_cuts=30, n_random_cuts=30)
            r5b = checks.truncation_test(wide_level, wide, row_len=pd.Timedelta(hours=7), n_signal_cuts=30,
                                         n_random_cuts=30)
            r5c = checks.truncation_test(xs_ratio, lb, row_len="known_at")
            try:
                checks.truncation_test(trap_ser, wide / wide.shift(1), row_len=pd.Timedelta(hours=7))
                r5d = "accepted"
            except ValueError as e:
                r5d = "refused" if "price level" in str(e) else str(e)[:60]
            return (not r5a["pass"] and not r5b["pass"] and r5c["pass"] and r5c["n_signals"] > 300 and r5d == "refused",
                    f"xs level {r5a['n_failed_cuts']}/{len(r5a['cuts'])} failed, wide level {r5b['n_failed_cuts']}, xs "
                    f"ratio {r5c['n_failed_cuts']} ({r5c['n_signals']} signals); returns frame {r5d}")
        _try(names[5], c5)

        def c6():
            sf = sg[sg.market == "f"].reset_index(drop=True)
            sh = checks.shift_test(sf, {"f": bk["f"]}, max_wait_h=96, **rule)
            try:
                checks.shift_test(sf, {"f": bk["f"]}, delay_extra_h=1.0, max_wait_h=96, **rule)
                s1 = "accepted"
            except ValueError:
                s1 = "refused"
            return (sh["delay_extra_h"] == 24.0 and sh["shifted"] != sh["base"] and s1 == "refused",
                    f"delay {sh['delay_extra_h']} h: base {sh['base']['n']} trades PF {sh['base']['PF']:.3f}, shifted "
                    f"{sh['shifted']['n']} PF {sh['shifted']['PF']:.3f}; 1 h {s1}")
        _try(names[6], c6)

        def c8():
            d8 = _d1_folder("d1_review_moves")
            for k, ex in (("gen", "2020-02-03"), ("dd", "2019-06-03")):
                g = _flat_d1(30.0, "2019-01-01", "2021-12-31")
                fr = costs.spec(k)["dividends"].get(ex, 0.0)
                g.loc[g.index >= _ny_open(ex), ["open", "high", "low", "close"]] *= (1 - fr)
                _write_d1(d8, k, g)
            os.environ["EXPLORE_D1_DIR"] = d8
            try:
                gm = data.session_moves(data.load_bars("gen"))
                dm = data.session_moves(data.long_bars({"dd": data.load_bars("dd"), "gen": data.load_bars("gen")}))
            finally:
                os.environ["EXPLORE_D1_DIR"] = d1
            ge = gm.loc[_ny_open("2020-02-03")]
            dd_ = dm[(dm.market == "dd") & (dm.index == _ny_open("2019-06-03"))].iloc[0]
            return (ge.ret < -0.4 and abs(ge.ret_total) < 1e-12 and bool(ge.action) and bool(dd_.action) and
                    dd_.split_ratio == 0.4725 and int(gm.action.sum()) <= 3 and
                    abs(gm.ret_total.drop(_ny_open("2020-02-03")).dropna()).max() < 0.02,
                    f"gen ret {ge.ret:.4f}, total {ge.ret_total:.2e}, flagged {int(gm.action.sum())} session(s); dd "
                    f"{dd_.split_ratio}")
        _try(names[8], c8)

        def c9():
            d9 = _d1_folder("d1_review_badfiles")
            g9 = synth.d1_bars("2016-01-01", "2021-12-31", seed=9, price=40.0)
            g9.reset_index().to_parquet(os.path.join(d9, "afl.parquet"))
            g9n = g9.copy()
            g9n.index = g9n.index.tz_localize(None)
            g9n.to_parquet(os.path.join(d9, "low.parquet"))
            os.environ["EXPLORE_D1_DIR"] = d9
            e9 = []
            try:
                for k in ("afl", "low"):
                    try:
                        x = data.load_bars(k)
                        e9.append(f"{len(x)} rows")
                    except data.DataGap:
                        e9.append("DataGap")
                    except Exception as e:      # noqa: BLE001
                        e9.append(type(e).__name__)
            finally:
                os.environ["EXPLORE_D1_DIR"] = d1
            return e9 == ["DataGap", "DataGap"], str(e9)
        _try(names[9], c9)

        def c10():
            lb = data.long_bars(bs)
            plan = checks._scale_plan(lb)[None]
            arrs = {}
            for p in plan:
                for v in ([p[2]["codes"]] if isinstance(p[2], dict) else [p[2]] if p[2] is not None else []):
                    arrs[id(v)] = v.nbytes
            return (len(plan) >= 5 and len(arrs) == 1 and sum(arrs.values()) <= 4 * len(lb),
                    f"{len(plan)} plan items, {len(arrs)} distinct row array(s), {sum(arrs.values())} bytes for "
                    f"{len(lb)} rows of {len(bs)} shares")
        _try(names[10], c10)
    finally:
        os.environ.pop("EXPLORE_D1_DIR", None)
        data.lock()

    def c7():   # synthetic hourly bars of the lab share jpm, with the lab's stray bars of 2019-07-03
        rows = []
        for d, r in data.us_sessions("2019-06-01", "2019-07-31").iterrows():
            extra = (13, 14, 15) if str(d.date()) == "2019-07-03" else ()
            for h in list(range(9, 13 if r.half_day else 16)) + list(extra):
                rows.append(pd.Timestamp(f"{d.date()} {h:02d}:00").tz_localize(NYc).tz_convert("UTC"))
        hb = pd.DataFrame({"open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0, "volume": 60.0},
                          index=pd.DatetimeIndex(rows))
        hb.attrs.update(market="jpm", price_is="bid")
        hk = sim.Book(hb, "jpm")
        s7 = pd.DataFrame({"known_at": [pd.Timestamp("2019-07-02 14:00", tz=NYc).tz_convert("UTC"),
                                        pd.Timestamp("2019-07-01 14:00", tz=NYc).tz_convert("UTC")], "side": [1, 1]})
        r7 = {ex: sim.simulate(s7, hk, market="jpm", exit=ex, stop=("bps", 2000), mode="every")
              .sort_values("entry_time", ascending=False).reset_index(drop=True)
              for ex in (("sessions", 1), ("session_close", 1))}
        ex1, ex2 = r7[("sessions", 1)], r7[("session_close", 1)]
        t13 = pd.Timestamp("2019-07-03 13:00", tz=NYc)
        return (ex1.exit_time[0] == t13 and ex1.reason[0] == "time_close" and ex2.exit_time[0] == t13 and
                ex1.exit_time[1] == pd.Timestamp("2019-07-02 14:00", tz=NYc) and ex1.reason[1] == "time",
                f"sessions: {ex1.exit_time[0].tz_convert(NYc)} {ex1.reason[0]}; session_close: "
                f"{ex2.exit_time[0].tz_convert(NYc)}; normal day {ex1.exit_time[1].tz_convert(NYc)} {ex1.reason[1]}")
    _try(names[7], c7)


def test_v21_real_bars():
    """--real-bars: mechanical checks on the prepared hourly bars of ~/explore_data/h1 (no trading rule): every new
    market loads (< 2022), D20 exists, share days have 7 bars, the modelled cost of a round trip is sane."""
    os.environ["EXPLORE_H1_DIR"] = os.path.expanduser("~/explore_data/h1")
    data.lock()
    out, bad = {}, []
    try:
        for k in sorted(costs.EXTRA):
            try:
                b = data.load_bars(k)
                bk = sim.Book(b, k)
                d20 = bk.d20(bk.t)
                med = float(b.close.median())
                tq = b.index[len(b) // 2]
                c = costs.round_trip(k, 1, med, med, tq + pd.Timedelta(hours=1), tq + pd.Timedelta(days=1, hours=1))["cost_bp"]
                npd = float(pd.Series(1, index=b.index).groupby(data.trading_day(b.index)).size().median())
                out[k] = {"bars": len(b), "first": str(b.index[0].date()), "d20_share": round(float(np.isfinite(d20).mean()), 3),
                          "bars_per_day": npd, "cost_bp": round(c, 1)}
                ok = (b.index.max() < U("2022-01-01") and out[k]["d20_share"] > 0.9 and
                      (npd == 7 if k != "oil" else npd >= 20) and (3 < c < 100))   # fix 2 (KF-8, amended from 60):
                # round_trip's adj now defaults to price_factor, so ge before its 1:8 reverse split (about 12 USD a real
                # share in 2019) pays 0.03 USD a real share, 24 bp a side: 80.7 bp, as sim.Book always charged
                if not ok:
                    bad.append(k)
            except Exception as e:      # noqa: BLE001
                bad.append(f"{k}: {e!r}"[:120])
        NUMBERS["real_bars"] = out
        check("real bars: oil and the 40 shares load (< 2022, split-adjusted), D20 on > 90 % of bars, 7-bar share days, "
              "round-trip cost 3-100 bp", not bad and len(out) == 41, f"bad {bad}; " + json.dumps({k: out[k] for k in list(out)[:3]}))
        # kit v2.1 fix 2 (KF-1): the outside file and the roll records match the RAW vendor bars: Dukascopy's 14:30 mid
        # of kit/oil_outside.csv lies inside the raw 14:00 New York bar (BID +- 0.10 USD); the recorded vendor gaps are the
        # raw bars' reopen moves at the listed rolls; every listed roll is a raw bar time; the adjusted bars keep the
        # real roll-night move (adjusted reopen move = vendor gap / ratio)
        raw = data.local_h1("oil")
        # the vendor's 14:30 mid is kept OUTSIDE the repository, beside the prepared bars (oil_mid_1430.csv: date,
        # duka_mid_1430); kit/oil_outside.csv holds the public settlements and the derived flag duka_on only
        vp = [os.path.join(d, "oil_mid_1430.csv") for d in data.h1_dirs()]
        vp = [x for x in vp if os.path.isfile(x)]
        ny = raw.index.tz_convert("America/New_York")
        h14 = raw[ny.hour == 14]
        h14.index = ny[ny.hour == 14].normalize().tz_localize(None)
        if vp:
            ox = pd.read_csv(vp[0], index_col=0, parse_dates=True).dropna()
            j = ox.join(h14[["low", "high"]], how="inner")
            inside = float(((j.duka_mid_1430 >= j.low - 0.10) & (j.duka_mid_1430 <= j.high + 0.10)).mean())
            oo = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "oil_outside.csv"), index_col=0,
                             parse_dates=True)
            jj = ox.join(oo, how="inner")
            jj = jj[(jj.c1 > 0) & (jj.c2 > 0)]
            fa, fb = np.abs(np.log(jj.duka_mid_1430 / jj.c1)), np.abs(np.log(jj.duka_mid_1430 / jj.c2))
            flag_ok = bool((np.where(fa > fb, 2, np.where(fb > fa, 1, 0)) == jj.duka_on.to_numpy(float)).all()) and \
                len(jj) == int(oo.duka_on.notna().sum())
        else:
            j, inside, flag_ok = h14.iloc[:0], float("nan"), False
        vg = {pd.Timestamp(k): float(v) for k, v in XC["oil"]["rolls_vendor_gap"].items()}
        gaps_ok = all(r in raw.index and abs(float(raw.open[r] / raw.close.iloc[raw.index.get_loc(r) - 1]) / v - 1) < 1e-9
                      for r, v in vg.items())
        adj = data.load_bars("oil")
        kept = max(abs(float(adj.open[r] / adj.close.iloc[adj.index.get_loc(r) - 1]) - vg[r] / float(q))
                   for r, q in ((pd.Timestamp(k), v) for k, v in XC["oil"]["rolls"].items()))
        check("real bars (KF-1): the vendor's 14:30 mid (oil_mid_1430.csv beside the prepared bars) lies in the raw 14:00 "
              "New York bar on >= 99 % of days and gives the flag duka_on of kit/oil_outside.csv; the recorded vendor gaps "
              "are the raw reopen moves at the 108 listed rolls; the adjusted reopen move there is vendor gap / listed "
              "ratio (the real night move kept)",
              inside >= 0.99 and len(j) > 2000 and flag_ok and gaps_ok and len(vg) == 108 and kept < 1e-9,
              f"days {len(j)}, inside {inside:.4f}, flag matches {flag_ok}; vendor gaps match {gaps_ok}; "
              f"max |adjusted move - gap / ratio| {kept:.2e}")
        # kit v2.1 fix 3 (R3-4): no listed roll of |ratio| >= 60 bp sits where the raw reopen gap misses the ratio by more
        # than 50 % while another bar within 48 h has a raw gap within 50 % of it (the 2014-03 roll was such a case)
        rg = np.log(raw.open / raw.close.shift()).to_numpy() * 1e4
        sus, n60 = [], 0
        for k_, q_ in XC["oil"]["rolls"].items():
            r_, lq = pd.Timestamp(k_), float(np.log(q_) * 1e4)
            if abs(lq) < 60:
                continue
            n60 += 1
            gl = rg[int(raw.index.searchsorted(r_))]
            w = np.where((raw.index >= r_ - pd.Timedelta(hours=48)) & (raw.index <= r_ + pd.Timedelta(hours=48)))[0]
            if abs(gl - lq) > 0.5 * abs(lq) and (np.abs(rg[w] - lq) <= 0.5 * abs(lq)).any():
                sus.append(k_)
        check("real bars (R3-4): every listed oil roll of |ratio| >= 60 bp is at the vendor's switch (its raw reopen gap "
              "within 50 % of the ratio, or no bar within 48 h with a raw gap within 50 % of it)", not sus and n60 > 30,
              f"{n60} rolls checked; misdated: {sus}")
        # kit v2.1 fix 3 (R3-1): on the real oil bars an honest rule comparing price differences passes the default
        # truncation test (power-of-two re-basing, no floating-point tie flips) and a rule on adjusted levels fails
        o13 = data.load_bars("oil", 2013)
        lv = float(o13.close.median())
        H_ = pd.Timedelta(hours=1)
        tie = checks.truncation_test(lambda d: pd.DataFrame({"known_at": d["oil"].index[((d["oil"].close - d["oil"].open) > (
            d["oil"].open - d["oil"].close.shift())).to_numpy()] + H_, "side": 1, "market": "oil"}), {"oil": o13})
        lvr = checks.truncation_test(lambda d: pd.DataFrame({"known_at": d["oil"].index[((d["oil"].close > lv) & (
            d["oil"].close.shift() <= lv)).to_numpy()] + H_, "side": 1, "market": "oil"}), {"oil": o13},
            n_signal_cuts=30, n_random_cuts=30)
        check("real bars (R3-1): on the real oil bars 2013-2021 'close-open > open-previous close' passes the default "
              "truncation test (200 cuts) and a rule on the adjusted level fails",
              tie["pass"] and tie["n_signals"] > 10000 and not lvr["pass"],
              f"tie rule: pass {tie['pass']}, {tie['n_failed_cuts']}/{len(tie['cuts'])} failed, {tie['n_signals']} signals; "
              f"level rule: pass {lvr['pass']} ({lvr['n_failed_cuts']} failed)")
    finally:
        os.environ.pop("EXPLORE_H1_DIR", None)


def test_v22_real_bars_d1():
    """--real-bars (kit v2.2): mechanical checks on the prepared daily bars of the universe (~/explore_data/d1/bars; no
    trading rule): every share of kit/universe_us.csv loads or is listed as missing; no bar before its
    in_universe_from, none after 2021; sessions of 390 / 210 minutes on the rule calendar; D20 exists; a daily round
    trip (in at an open, out at the next open, one night) costs 20-120 bp; random signals have no edge (gross)."""
    os.environ["EXPLORE_D1_DIR"] = os.path.expanduser("~/explore_data/d1/bars")
    data.lock()
    cal = data.us_sessions("2016-01-01", "2021-12-31")
    cal_open = set(pd.DatetimeIndex(cal.open_utc).as_unit("ns").asi8)
    out, bad, missing, books_, short = {}, [], [], {}, []
    try:
        for k in sorted(costs.UNIVERSE):
            try:
                b = data.load_bars(k)
            except FileNotFoundError:
                missing.append(k)
                continue
            try:
                bk = sim.Book(b, k)
                t0 = pd.Timestamp(costs.spec(k)["in_universe_from"]).tz_localize(NYZ)
                d20 = bk.d20(bk.t)
                med = float(b.close.median())
                i = len(b) // 2
                c = costs.round_trip(k, 1, med, med, b.index[i], b.index[i + 1])["cost_bp"]
                on_cal = bool(np.isin(b.index.as_unit("ns").asi8, list(cal_open)).all())
                pk = pd.DatetimeIndex(b.known_at).as_unit("ns").asi8
                calk = cal.set_index(pd.DatetimeIndex(cal.open_utc)).close_utc.reindex(b.index)
                rec = {"bars": len(b), "first": str(b.index[0].date()),
                       "d20_share": round(float(np.isfinite(d20[20:]).mean()), 3) if len(b) > 20 else None,
                       "cost_bp": round(c, 1)}
                if rec["d20_share"] is None:
                    short.append(k)                  # entered the universe less than 21 sessions before 2022
                ok = (b.index.min() >= t0 and b.index.max() < U("2022-01-01") and pk.max() < U("2022-01-01").value and
                      on_cal and (pd.DatetimeIndex(calk) == pd.DatetimeIndex(b.known_at)).all() and
                      (rec["d20_share"] is None or rec["d20_share"] > 0.99) and 20 < c < 160 and (b.low <= b[["open", "close"]].min(axis=1)).all())
                out[k] = rec
                books_[k] = bk
                if not ok:
                    bad.append(f"{k}: {rec}")
            except Exception as e:      # noqa: BLE001
                bad.append(f"{k}: {e!r}"[:160])
        cs = np.array([v["cost_bp"] for v in out.values()])
        NUMBERS["real_bars_d1"] = {"shares": len(out), "missing": missing, "bad": bad[:10], "no_d20_yet": short,
                                   "cost_bp_min_median_max": [float(cs.min()), float(np.median(cs)), float(cs.max())]
                                   if len(cs) else None}
        check("real bars (v2.2): every share of the universe file loads (missing ones listed), no bar before its "
              "in_universe_from or after 2021, bars on the rule calendar with the session's close as known_at, D20 on "
              "> 99 % of bars after the first 20 sessions, a daily round trip (open to next open, 1 night) costs 20-160 bp",
              not bad and len(out) + len(missing) == 382 and len(out) > 0,
              f"{len(out)} loaded, missing {missing}, bad {bad[:3]}, fewer than 21 sessions (no D20 yet) {short}; cost bp min/median/max "
              f"{NUMBERS['real_bars_d1']['cost_bp_min_median_max']}")
        dsrc = os.path.expanduser("~/explore_data/d1/dividends.csv")
        if os.path.isfile(dsrc):              # V22-9: the kit's dividend facts = the data's final file (2016-2021,
            dv0 = pd.read_csv(dsrc, dtype={"key": str, "ex_date": str})    # the builder's filters)
            dv0 = dv0[(dv0.ex_date < "2022-01-01") & (dv0.ex_date >= "2016-01-01") & dv0.key.isin(set(costs.UNIVERSE))]
            dv0 = dv0.dropna(subset=["fraction"])
            dvk = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "universe_us_dividends.csv"),
                              dtype={"key": str, "ex_date": str})
            a_ = set(zip(dv0.key, dv0.ex_date)) - {("dhr", "2016-07-05")}
            b_ = set(zip(dvk.key, dvk.ex_date))
            mg = dvk.merge(dv0, on=["key", "ex_date"], suffixes=("_kit", "_data"))
            check("real bars (V22-9): the kit's dividend file holds exactly the data's final dividends of the universe "
                  "2016-2021 (but dhr's spin-off record), with the same fractions",
                  a_ == b_ and float((mg.fraction_kit - mg.fraction_data).abs().max()) < 1e-9,
                  f"kit {len(b_)} rows, data {len(a_)}; only in kit {sorted(b_ - a_)[:5]}, only in data {sorted(a_ - b_)[:5]}")
        rng = np.random.default_rng(5)
        sigs = []
        for k, bk in books_.items():
            if len(bk.t) < 80:
                continue
            pick = np.sort(rng.choice(np.arange(25, len(bk.t) - 10), min(40, len(bk.t) - 40), replace=False))
            sigs.append(pd.DataFrame({"known_at": pd.DatetimeIndex(bk.t_end[pick].astype("datetime64[ns]")).tz_localize("UTC"),
                                      "side": rng.choice([-1, 1], len(pick)), "market": k}))
        sg = pd.concat(sigs, ignore_index=True)
        tr_ = sim.simulate(sg, books_, exit=("sessions", 5), stop=("d20", 2.0))
        tg_, tn_ = stats.t_stat(tr_.R_gross), stats.t_stat(tr_.R)
        check("real bars (v2.2): random sides on random sessions of every share (5 sessions, stop 2 x D20) have no gross "
              "edge (|t| < 3.5) and lose their costs net", abs(tg_) < 3.5 and tr_.R.mean() < tr_.R_gross.mean(),
              f"{len(tr_)} trades, t gross {tg_:.2f}, t net {tn_:.2f}, mean net bp {tr_.net_bp.mean():.1f}, mean gross bp "
              f"{tr_.gross_bp.mean():.1f}")
    finally:
        os.environ.pop("EXPLORE_D1_DIR", None)


if __name__ == "__main__":
    T0 = time.time()
    tests = [test_period_lock, test_asof_and_known, test_daily_bars_dst, test_costs, test_sim_mechanics, test_lookahead,
             test_correlation_fixture, test_basket_and_lock_in_sim, test_dsr_monte_carlo, test_long_drift_guard, test_hash_ledger_speed,
             test_planted_and_noise, test_review_v1_same_bar, test_review_v2_null_dense, test_review_v3_v9_guards_in_judge,
             test_review_v4_external, test_review_v5_val_judge, test_review_v6_synth_fair, test_review_v7_budget,
             test_review_v8_template, test_review_v9_unlock, test_lead_v11,
             test_pairs_costs, test_pairs_stops, test_pairs_planted_and_basket, test_pairs_noise, test_event_mechanics,
             test_event_lookahead, test_event_null_noise, test_crypto_venues,
             test_fix_v1_suppression, test_fix_v2_v4_judge_binding, test_fix_v3_venue_holes, test_lead_joint_null,
             test_v21_costs_by_hand, test_v21_local_markets, test_v21_share_traps, test_v21_slow_track_and_provisional,
             test_v21_small_fixes, test_v21_review_fixes, test_v21_review2_fixes, test_v21_review3_fixes,
             test_v22_universe_and_costs, test_v22_daily_data_and_sessions, test_v22_daily_traps,
             test_v22_daily_noise, test_v22_planted_chain_and_groups, test_v22_review_fixes]
    if "--review" in sys.argv:
        tests = [t for t in tests if t.__name__.startswith("test_review")]
    if "--only" in sys.argv:                 # --only <substring of a test name>
        tests = [t for t in tests if sys.argv[sys.argv.index("--only") + 1] in t.__name__]
    if "--net" in sys.argv:
        tests += [test_net, test_net_venues]
    elif "--net-venues" in sys.argv:         # the crypto venues only (no Dukascopy request)
        tests.append(test_net_venues)
    if "--real-bars" in sys.argv:            # + mechanical checks on the prepared bars of ~/explore_data/h1 (kit v2.1)
        tests += [test_v21_real_bars, test_v22_real_bars_d1]
    for t in tests:
        try:
            t()
        except Exception as e:  # a crash is a failure, reported
            import traceback
            traceback.print_exc()
            check(t.__name__ + " crashed", False, repr(e))
    shutil.rmtree(TMP, ignore_errors=True)
    bad = [r for r in RESULTS if not r[1]]
    print(json.dumps(NUMBERS, default=str))
    print(f"{len(RESULTS) - len(bad)}/{len(RESULTS)} checks passed in {time.time() - T0:.0f} s")
    sys.exit(1 if bad else 0)
