"""Self-tests of the kit: synthetic data only, no network, no lab data (about 2 minutes).
    PYTHONDONTWRITEBYTECODE=1 python3 -B lab/explore/kit/test_kit.py          (all offline tests)
    PYTHONDONTWRITEBYTECODE=1 python3 -B lab/explore/kit/test_kit.py --net    (+ one month of each source, decoded)
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
    tb0 = checks.truncation_test(build_bad, b, cuts, n_signal_cuts=0)
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

if __name__ == "__main__":
    T0 = time.time()
    tests = [test_period_lock, test_asof_and_known, test_daily_bars_dst, test_costs, test_sim_mechanics, test_lookahead,
             test_correlation_fixture, test_basket_and_lock_in_sim, test_dsr_monte_carlo, test_long_drift_guard, test_hash_ledger_speed,
             test_planted_and_noise, test_review_v1_same_bar, test_review_v2_null_dense, test_review_v3_v9_guards_in_judge,
             test_review_v4_external, test_review_v5_val_judge, test_review_v6_synth_fair, test_review_v7_budget,
             test_review_v8_template, test_review_v9_unlock, test_lead_v11]
    if "--review" in sys.argv:
        tests = [t for t in tests if t.__name__.startswith("test_review")]
    if "--only" in sys.argv:                 # --only <substring of a test name>
        tests = [t for t in tests if sys.argv[sys.argv.index("--only") + 1] in t.__name__]
    if "--net" in sys.argv:
        tests.append(test_net)
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
