"""Data access of the open search, behind the PERIOD LOCK.

Guarantees (tested in test_kit.py):
- Every reader returns rows strictly before 2022-01-01 00:00 UTC (in sample), unless unlock_val(idea_dir) was called,
  which needs idea_dir/val_declared.json (frozen_rule, bars, attack, cut 2025-12-31) and a results.json whose verdict
  says every in-sample bar passed, appends one line to lab/results/val_access.log and moves the end to
  2026-01-01 00:00 UTC (exclusive). Nothing dated 2026-01-01 or later is ever requested, returned or cached; while locked,
  nothing of 2022 or later is requested either (a month/year is only requested when it starts before the period end).
- External series (fred, yahoo_daily, external) are indexed by the time the value is KNOWN, from a rule the caller
  must give; asof_join only looks backward (a value known at exactly t counts as known at t). external() and non-daily
  FRED series also need a declared publication lag, checked on every row (a series indexed by its observation date
  would pass the truncation test while leaking).
- Prepared hourly bars: load_bars(key) first looks for <fp key>.parquet in EXPLORE_H1_DIR, <cache>/h1 and
  lab/explore/prices/h1 (hourly BID bars the lead built once from the lab's own minute data, in sample only; the
  validation years live in a sibling folder '<dir>_val' and are read only after unlock_val). No download then.
- LOCAL-ONLY markets (kit v2.1, kit/extra_costs.json 'local'): 'oil' (WTI, the lab's lightcmdusd) and 40 US shares
  (keys = lower-case tickers) exist ONLY as prepared bars: load_bars reads them through the same lock and raises
  FileNotFoundError when the file is absent (no download path). Shares: 7 hourly bars a day (09:30-16:00 New York); the
  FIRST BAR IS LABELLED AT THE FULL HOUR (09:00) THOUGH TRADING STARTS AT 09:30: its open is the 09:30 price, its end
  (label + 1 h = 10:00) is right. The kit treats that bar as opening at its label, i.e. EARLIER than it really does: a
  signal known between 09:00 and 09:30 enters at the 10:00 bar (late, never early), and an entry 'at the open' of the
  session is the 09:30 price, filled at that bar's open with the 09:30 spread shape. Nothing can be known from the bar
  before its end (10:00); a value computed from its open is the 09:30 price. A 'hours' exit counted from that bar holds
  30 minutes less than its label says. The share bars are NOT split-adjusted in the files: load_bars back-adjusts them
  (splits of the cost entry, checked against the bars); sim.Book recomputes the adjustment (split_factor) to scale the
  per-unit commission and refuses raw bars. No column of the bars carries the split adjustment (a build could read a
  future split from it); an ABSOLUTE share (or oil) price level still depends on later splits (rolls): use ratios.
  checks.truncation_test catches a rule on levels (kit v2.1 fix 2, KF-2: cut copies re-based, cut builds in asof).
- Cache: ~/explore_data (EXPLORE_CACHE overrides), outside the repository. Polite HTTP: browser User-Agent, at least
  1 s between Dukascopy requests (0.3 s for other hosts), growing waits on 429/503/network errors, 404 = no data.
"""
import datetime as _dt
import io
import json
import lzma
import os
import ssl
import time
import urllib.error
import urllib.request
import zipfile

import numpy as np
import pandas as pd

KIT = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(KIT, "..", ".."))          # lab/explore/kit -> lab
NY = "America/New_York"
IS_END = pd.Timestamp("2022-01-01", tz="UTC")                  # exclusive
VAL_END = pd.Timestamp("2026-01-01", tz="UTC")                 # exclusive; the holdout starts here: never touched
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
UA_PLAIN = "explore-kit/1.0 (python-urllib)"
HTTP_TRIES = 4                      # per file; waits 2, 4, 8 s between tries (a run's budget is 60 minutes)
_STATE = {"end": IS_END, "unlocked_by": None, "deadline": None}


class BudgetExceeded(RuntimeError):
    """The download deadline (set_deadline / EXPLORE_DEADLINE) has passed: stop, write 'en cours' in the ledger."""


def set_deadline(seconds_from_now):
    """Stop downloading after this many seconds (None: no deadline). http_get raises BudgetExceeded once it has
    passed, before any new request; files already cached are still read. EXPLORE_DEADLINE (a unix time) sets it for a
    whole process."""
    _STATE["deadline"] = None if seconds_from_now is None else time.time() + float(seconds_from_now)


def _deadline():
    d = _STATE["deadline"]
    env = os.environ.get("EXPLORE_DEADLINE")
    if env:
        d = float(env) if d is None else min(d, float(env))
    return d


def user_agent(url):
    """Dukascopy wants a browser User-Agent (CHARTER); FRED drops connections from one (checked 2026-11-17: the
    browser string timed out where a plain one got HTTP 200), so every other host gets a plain client name."""
    return UA if "dukascopy" in url.split("/")[2] else UA_PLAIN
_LAST = {}


class PeriodError(RuntimeError):
    pass


class DataGap(RuntimeError):
    """Bars with a hole (a month without data inside a market's history)."""


def cache_dir():
    return os.path.expanduser(os.environ.get("EXPLORE_CACHE", "~/explore_data"))


def val_log_path():
    return os.environ.get("EXPLORE_VAL_LOG", os.path.join(LAB, "results", "val_access.log"))


def period_end():
    """Exclusive end of what readers may return: 2022-01-01 UTC (locked) or 2026-01-01 UTC (after unlock_val)."""
    return _STATE["end"]


VAL_KEYS = ("frozen_rule", "bars", "cut", "attack")
VAL_OK_VERDICTS = ("pass", "pass, weak against selection")


def check_val_declared(idea_dir):
    """The conditions of charter rule 5 that a file can show: idea_dir/val_declared.json holds a non-empty frozen_rule,
    bars and attack (what the independent re-implementation found) and cut = "2025-12-31"; idea_dir/results.json says
    verdict "pass" or "pass, weak against selection" (every in-sample bar passed; CHARTER 'Selection', amended
    2026-11-18: the deflated Sharpe is a label carried to the ledger, not a gate). Raises PeriodError otherwise."""
    p = os.path.join(idea_dir, "val_declared.json")
    if not os.path.isfile(p):
        raise PeriodError(f"no val_declared.json in {idea_dir}: the validation period stays locked")
    try:
        v = json.load(open(p))
    except ValueError as e:
        raise PeriodError(f"val_declared.json is not JSON: {e}")
    miss = [k for k in VAL_KEYS if not (isinstance(v, dict) and v.get(k))]
    if miss or str(v.get("cut")) != "2025-12-31":
        raise PeriodError(f"val_declared.json needs non-empty {list(VAL_KEYS)} with cut '2025-12-31' (missing: {miss})")
    r = os.path.join(idea_dir, "results.json")
    verdict = json.load(open(r)).get("verdict") if os.path.isfile(r) else None
    if verdict not in VAL_OK_VERDICTS:
        raise PeriodError(f"results.json verdict is {verdict!r}: only an idea that passed every in-sample bar may look "
                          "at the validation period")
    return v


def unlock_val(idea_dir):
    """Open 2022-2025 for this process. Allowed only if check_val_declared(idea_dir) passes (charter rule 5). Appends
    one JSON line to the val access log without reading it."""
    idea_dir = os.path.abspath(idea_dir)
    check_val_declared(idea_dir)
    line = {"time": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "track": "explore",
            "label": "look:" + os.path.basename(idea_dir.rstrip("/")), "period": "val"}
    p = val_log_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(line) + "\n")
    _STATE["end"], _STATE["unlocked_by"] = VAL_END, idea_dir
    return line


def lock():
    """Back to in sample only (used by the tests)."""
    _STATE["end"], _STATE["unlocked_by"] = IS_END, None


def _assert_before(ts_index, what):
    if len(ts_index) and pd.DatetimeIndex(ts_index).max() >= period_end():
        raise PeriodError(f"{what}: a row at or after {period_end()} would be returned")


def cut(df):
    """Rows of a UTC-indexed frame/series strictly before the period end (applied by every reader)."""
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is None:
        raise ValueError("index must be tz-aware UTC")
    out = df[idx < period_end()]
    _assert_before(out.index, "cut")
    return out


def _allowed(year, month=1):
    """A file covering (year, month) may be requested only if it starts before the period end (never 2026+)."""
    start = pd.Timestamp(year=year, month=month, day=1, tz="UTC")
    return start < period_end() and start < VAL_END


# ---------------------------------------------------------------- HTTP
def _ctx():
    ca = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    return ssl.create_default_context(cafile=ca) if ca and os.path.exists(ca) else None


def http_get(url, min_interval=None, tries=None):
    """GET with user_agent(url) and a per-host throttle; 404 -> None; 429/503/5xx/network -> waits of 2, 4, 8 s
    (HTTP_TRIES tries). Raises BudgetExceeded once the deadline has passed (never sleeps past it)."""
    host = url.split("/")[2]
    gap = min_interval if min_interval is not None else (1.0 if "dukascopy" in host else 0.3)
    tries = HTTP_TRIES if tries is None else tries
    for k in range(tries):
        dl = _deadline()
        if dl is not None and time.time() >= dl:
            raise BudgetExceeded(f"download deadline passed before {url}")
        wait = _LAST.get(host, 0) + gap - time.time()
        if wait > 0:
            time.sleep(wait)
        _LAST[host] = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": user_agent(url), "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=60, context=_ctx()) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code not in (429, 500, 502, 503, 504) or k == tries - 1:
                raise
            _pause(2 * 2 ** k)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            if k == tries - 1:
                raise
            _pause(2 * 2 ** k)
    raise RuntimeError("failed " + url)


def _pause(sec):
    dl = _deadline()
    if dl is not None and time.time() + sec >= dl:
        raise BudgetExceeded("download deadline reached while waiting to retry")
    time.sleep(sec)


def _fred_keep(raw):
    """Drop the rows dated at or after the period end BEFORE anything is cached (FRED ignores coed on licence-limited
    series and may send recent years: scout, 2026-11-17)."""
    lines = raw.decode("utf-8", "replace").splitlines()
    lim = period_end().strftime("%Y-%m-%d")
    return ("\n".join(lines[:1] + [x for x in lines[1:] if x[:10] < lim]) + "\n").encode()


def _yahoo_keep(raw):
    """Keep only the time zone, the time stamps before the period end and their values (Yahoo's meta block carries
    today's price, and a server may ignore period2): nothing later is cached."""
    r = json.loads(raw)["chart"]["result"][0]
    ts = r.get("timestamp") or []
    lim = int(period_end().timestamp())
    k = [i for i, t in enumerate(ts) if t < lim]
    ind = {name: [{f: [v[i] for i in k] for f, v in blk.items() if isinstance(v, list) and len(v) == len(ts)}
                  for blk in blks] for name, blks in (r.get("indicators") or {}).items()}
    out = {"meta": {"exchangeTimezoneName": (r.get("meta") or {}).get("exchangeTimezoneName", NY)},
           "timestamp": [ts[i] for i in k], "indicators": ind}
    return json.dumps({"chart": {"result": [out]}}).encode()


def _cached(path, url, keep=None, **kw):
    """Bytes of url, cached at path. b'' is cached for a 404 (no data). `keep`: a function applied to the bytes before
    they are cached or returned (drops what lies past the period end)."""
    if os.path.exists(path):
        return open(path, "rb").read()
    raw = http_get(url, **kw)
    if raw and keep is not None:
        raw = keep(raw)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(raw or b"")
    os.replace(tmp, path)
    return raw or b""


# ---------------------------------------------------------------- FP universe
# FP cost key -> data source. point = Dukascopy price unit of the integer records; ref = rough typical in-sample price,
# used only for a magnitude check of the decoding (a wrong point size is off by x10 or more).
FP = {
    "xauusd": ("duka", "XAUUSD", 1e3, 1300), "xagusd": ("duka", "XAGUSD", 1e3, 18),
    "us100": ("duka", "USATECHIDXUSD", 1e3, 7000), "us500": ("duka", "USA500IDXUSD", 1e3, 2600),
    "us30": ("duka", "USA30IDXUSD", 1e3, 23000), "ger40": ("duka", "DEUIDXEUR", 1e3, 12000),
    "eurusd": ("duka", "EURUSD", 1e5, 1.15), "gbpusd": ("duka", "GBPUSD", 1e5, 1.35),
    "usdjpy": ("duka", "USDJPY", 1e3, 110), "audusd": ("duka", "AUDUSD", 1e5, 0.75),
    "usdcad": ("duka", "USDCAD", 1e5, 1.28), "usdchf": ("duka", "USDCHF", 1e5, 0.95),
    "nzdusd": ("duka", "NZDUSD", 1e5, 0.7), "eurjpy": ("duka", "EURJPY", 1e3, 125),
    "btcusd": ("binance", "BTCUSDT", None, 10000), "ethusd": ("binance", "ETHUSDT", None, 500),
}
from . import costs as _C  # noqa: E402  (costs imports nothing of the kit)
for _k, _v in _C.EXTRA.items():          # kit v2.1 local-only markets: prepared bars only, no download path
    if _v.get("local"):
        FP[_k] = ("local", _v.get("data_symbol", _k.upper()), None, float(_v["ref_price"]))
POINT = {v[1]: v[2] for v in FP.values() if v[0] == "duka"}
REF = {v[1]: v[3] for v in FP.values()}


def fp_markets():
    """{fp_key: {source, symbol, point, price_is, weekdays_only, hours}}. price_is: 'bid' (Dukascopy BID candles: ask =
    bid + FP spread) or 'mid' (Binance trade prices: bid = mid - spread/2, ask = mid + spread/2).
    Hours (lab/COSTS_FP.md, lab/build_fp_frames.py): crypto is shut at FP from Friday 23:55 to Monday 00:00 server time
    (server = New York + 7 h): no fill on a bar that opens inside; a time exit that falls in the closure is done at the
    Friday close (kit: close of the last bar before the closure). Other markets: fills only on bars that exist."""
    out = {}
    for k, (src, sym, pt, _) in FP.items():
        crypto = src == "binance"
        out[k] = {"source": {"duka": "dukascopy", "binance": "binance", "local": "local"}[src], "symbol": sym, "point": pt,
                  "price_is": "mid" if crypto else "bid", "weekdays_only": crypto,
                  "hours": "closed Fri 23:55 - Mon 00:00 server (NY+7h)" if crypto else "bars that exist in the data"}
        if src == "local":
            out[k]["hours"] = "bars that exist in the prepared file (shares: 09:30-16:00 New York, 7 bars a day)"
    return out


def server_time(ts):
    """FP server wall clock (New York + 7 h, so it follows US daylight saving), tz-naive."""
    return pd.DatetimeIndex(ts).tz_convert(NY).tz_localize(None) + pd.Timedelta(hours=7)


def fp_closed(ts):
    """True where a timestamp lies in FP's crypto closure (Fri 23:55 to Mon 00:00 server)."""
    s = server_time(ts)
    return np.asarray((s.dayofweek >= 5) | ((s.dayofweek == 4) & ((s.hour * 60 + s.minute) >= 23 * 60 + 55)))


def fp_hours(key, bars):
    """Bars FP can fill on: crypto bars whose open lies in the closure are removed (lab/build_fp_frames.py)."""
    if fp_markets()[key]["weekdays_only"]:
        return bars[~fp_closed(bars.index)]
    return bars


# ---------------------------------------------------------------- Dukascopy
def _duka_month(sym, y, m, side):
    """One month of hourly candles (m = 1..12). Same cache layout and decoding as lab/explore/fetch.py: 24-byte big-endian
    records: uint32 seconds from the month start, open, close, low, high (uint32 points), float32 volume."""
    if not _allowed(y, m):
        return None
    path = os.path.join(cache_dir(), "duka", sym, f"{y}_{m:02d}_{side}.bi5")
    raw = _cached(path, f"https://datafeed.dukascopy.com/datafeed/{sym}/{y}/{m - 1:02d}/{side}_candles_hour_1.bi5")
    if not raw:
        return None
    rec = np.frombuffer(lzma.decompress(raw), dtype=">u4,>u4,>u4,>u4,>u4,>f4")
    p = POINT[sym]
    t0 = pd.Timestamp(year=y, month=m, day=1, tz="UTC")
    return pd.DataFrame({"open": rec["f1"] / p, "high": rec["f4"] / p, "low": rec["f3"] / p, "close": rec["f2"] / p,
                         "volume": rec["f5"].astype(float)},
                        index=t0 + pd.to_timedelta(rec["f0"].astype(np.int64), unit="s"))


def duka_h1(symbol, start_year=2013, side="BID", end_year=None):
    """Dukascopy hourly candles (BID or ASK) of a Dukascopy symbol, UTC bar-open index, volume kept, bars with zero
    volume dropped (no trading: weekends, breaks). Cut at the period end."""
    if symbol not in POINT:
        raise KeyError(f"no point size for {symbol}: add it to data.FP after checking the decoding")
    last = period_end().year - 1 if end_year is None else min(end_year, period_end().year - 1)
    months = [(y, m) for y in range(start_year, last + 1) for m in range(1, 13)]
    parts, t0 = [], time.time()
    for q, (y, m) in enumerate(months):
        parts.append(_duka_month(symbol, y, m, side))
        if os.environ.get("EXPLORE_PROGRESS") and (q % 12 == 11 or q == len(months) - 1):
            print(f"  {symbol} {side}: {q + 1}/{len(months)} months ({time.time() - t0:.0f} s)", flush=True)
    have = [ym for ym, p in zip(months, parts) if p is not None and len(p)]
    if have:
        hole = [ym for ym, p in zip(months, parts) if have[0] < ym < have[-1] and (p is None or not len(p))]
        if hole:
            raise DataGap(f"{symbol}: no bars for {len(hole)} month(s) inside its history, first {hole[:4]}: a refused or "
                          f"empty download was cached under {os.path.join(cache_dir(), 'duka', symbol)}; delete those "
                          "files and fetch again (never test on bars with a hole)")
    parts = [p for p in parts if p is not None and len(p)]
    if not parts:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated(keep="last") & (df.volume > 0)]
    df.index.name = "time"
    med = float(df.close.median())
    if not (REF[symbol] / 4 < med < REF[symbol] * 4):
        raise ValueError(f"{symbol}: median price {med} far from the expected {REF[symbol]}: point size wrong?")
    return cut(df)


# ---------------------------------------------------------------- Binance
_KL = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades",
       "taker_buy_base", "taker_buy_quote", "ignore"]


def _bn_csv(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        txt = z.read(z.namelist()[0]).decode()
    first = txt.split("\n", 1)[0]
    return pd.read_csv(io.StringIO(txt), header=0 if first[:1].isalpha() else None)


def _bn_time(x):
    x = np.asarray(x, dtype=np.int64)
    unit = np.where(x > 10 ** 14, 1000, 1)            # 2025+ spot files are in microseconds
    return pd.to_datetime(x // unit, unit="ms", utc=True)


def _last_month(end):
    e = period_end() - pd.Timedelta(days=1)
    if end is not None:
        e = min(e, pd.Timestamp(end, tz="UTC"))
    return e.strftime("%Y-%m")


def binance_klines(symbol="BTCUSDT", interval="1h", market="spot", start="2017-08", end=None):
    """Monthly klines from data.binance.vision (spot from 2017-08; market='um' for USD-M futures). Columns open, high,
    low, close, volume, quote_volume, trades, taker_buy_base, taker_buy_quote; UTC bar-open index; cut at period end."""
    base = "spot" if market == "spot" else "futures/um"
    parts = []
    for p in pd.period_range(start, _last_month(end), freq="M"):
        if not _allowed(p.year, p.month):
            continue
        name = f"{symbol}-{interval}-{p.year}-{p.month:02d}.zip"
        path = os.path.join(cache_dir(), "binance", base.replace("/", "_"), "klines", symbol, interval, name)
        raw = _cached(path, f"https://data.binance.vision/data/{base}/monthly/klines/{symbol}/{interval}/{name}")
        if not raw:
            continue
        d = _bn_csv(raw)
        d = d.iloc[:, :12]
        d.columns = _KL
        d.index = _bn_time(d.open_time)
        parts.append(d[["open", "high", "low", "close", "volume", "quote_volume", "trades", "taker_buy_base",
                        "taker_buy_quote"]].astype(float))
    if not parts:
        return pd.DataFrame()
    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df.index.name = "time"
    return cut(df)


def binance_funding(symbol="BTCUSDT", start="2019-09", end=None):
    """USD-M futures funding rate (monthly files, from 2019-09), indexed by the funding time (when it is known/settled)."""
    parts = []
    for p in pd.period_range(start, _last_month(end), freq="M"):
        if not _allowed(p.year, p.month):
            continue
        name = f"{symbol}-fundingRate-{p.year}-{p.month:02d}.zip"
        path = os.path.join(cache_dir(), "binance", "futures_um", "fundingRate", symbol, name)
        raw = _cached(path, f"https://data.binance.vision/data/futures/um/monthly/fundingRate/{symbol}/{name}")
        if not raw:
            continue
        d = _bn_csv(raw)
        if not isinstance(d.columns[0], str):
            d.columns = ["calc_time", "funding_interval_hours", "last_funding_rate"][:d.shape[1]]
        s = pd.Series(d["last_funding_rate"].astype(float).to_numpy(), index=_bn_time(d["calc_time"]), name=symbol)
        parts.append(s)
    if not parts:
        return pd.Series(dtype=float)
    s = pd.concat(parts).sort_index()
    return cut(s[~s.index.duplicated(keep="last")])


# ---------------------------------------------------------------- crypto dollar venues (lead's ruling of 2026-11-18 (b))
# scout/sources.md sections 13 (Bitfinex), 14 (Bitstamp), 15 (Coinbase): URLs, paging, limits and first dates (probed
# 2026-11-17; re-probed 2026-11-18 with the kit's plain client name: all three answer 200 and honour in-sample bounds,
# end inclusive). FP key -> (venue symbol, first month with hourly candles).
VENUES = {
    "bitstamp": {"btcusd": ("btcusd", "2012-11"), "ethusd": ("ethusd", "2017-08")},
    "bitfinex": {"btcusd": ("tBTCUSD", "2013-03"), "ethusd": ("tETHUSD", "2016-03")},
    "coinbase": {"btcusd": ("BTC-USD", "2015-07"), "ethusd": ("ETH-USD", "2016-05")},
}
VENUE_LIMIT = {"bitstamp": 1000, "bitfinex": 10000, "coinbase": 300}     # candles per call (the venues' maxima)
VENUE_GAP_S = {"bitstamp": 0.3, "bitfinex": 2.0, "coinbase": 0.35}       # seconds between calls (Bitfinex: 30 a minute)
_H = 3600
# Longest run of hours without a candle a venue month may have before it is treated as incomplete (verifier V3: one
# transient empty reply silently dropped 300 hours of a Coinbase month, cached as complete). Bitcoin and ether trade
# every hour on these venues from their first month on; a real venue outage longer than this (for example Bitfinex in
# August 2016) is accepted only with crypto_h1(..., allow_holes=True), which records it next to the cached month.
VENUE_MAX_HOLE_H = 48


def _venue_json(url, gap, empty):
    """GET and decode a venue reply; an EMPTY reply is asked once more before it is believed (a transient empty page
    or window must not end the paging or leave a hole: verifier V3). `empty(j)` says whether a decoded reply is empty."""
    j = None
    for k in range(2):
        raw = http_get(url, min_interval=gap)
        j = json.loads(raw) if raw else None
        if j is not None and not empty(j):
            return j
        if k == 0:
            _pause(gap)
    return j


def _venue_pages(venue, sym, s, e):
    """Hourly candles with open time in [s, e) (unix seconds; e <= period end) from one venue, paged as
    scout/sources.md describes. No request names a time at or after e. Returns a list of (t, o, h, l, c, v)."""
    lim, gap, rows = VENUE_LIMIT[venue], VENUE_GAP_S[venue], []
    last = e - _H                                                    # open time of the last wanted candle (inclusive)
    if venue == "bitstamp":                                          # the `limit` candles ENDING at `end`: walk back
        end, pages = last, 0
        while end >= s:
            r = _venue_json(f"https://www.bitstamp.net/api/v2/ohlc/{sym}/?step=3600&limit={lim}&start={s}&end={end}",
                            gap, lambda x: not (x.get("data") or {}).get("ohlc"))
            j = (r.get("data") or {}).get("ohlc") or [] if r else []
            if not j:
                break
            ts = [int(x["timestamp"]) for x in j]
            rows += [(int(x["timestamp"]), float(x["open"]), float(x["high"]), float(x["low"]), float(x["close"]),
                      float(x["volume"])) for x in j]
            nxt = min(ts) - _H
            if nxt >= end:
                raise RuntimeError(f"bitstamp {sym}: paging did not move back from {end} (end bound ignored?)")
            end, pages = nxt, pages + 1
            if pages > 60:
                raise RuntimeError(f"bitstamp {sym}: more than 60 pages for one month")
    elif venue == "bitfinex":                                        # ascending from `start`, sort=1
        start, pages = s * 1000, 0
        while start <= last * 1000:
            j = _venue_json(f"https://api-pub.bitfinex.com/v2/candles/trade:1h:{sym}/hist?limit={lim}&start={start}"
                            f"&end={last * 1000}&sort=1", gap, lambda x: len(x) == 0) or []
            if j and not isinstance(j[0], list):
                raise RuntimeError(f"bitfinex {sym}: unexpected reply {str(j)[:120]}")
            if not j:
                break
            rows += [(int(x[0]) // 1000, float(x[1]), float(x[3]), float(x[4]), float(x[2]), float(x[5])) for x in j]
            inside = [int(x[0]) for x in j if start <= int(x[0]) <= last * 1000]   # a row past the bounds must not
            if not inside:                                                        # end the paging (it did: a server
                break                                                             # ignoring end gave 300 h of 720)
            mx = max(inside)
            if mx >= last * 1000:                    # never stop on a short page: a capped reply would drop hours
                break
            if mx + 1 <= start:
                raise RuntimeError(f"bitfinex {sym}: paging did not move forward")
            start, pages = mx + 1, pages + 1
            if pages > 60:
                raise RuntimeError(f"bitfinex {sym}: more than 60 pages for one month")
    elif venue == "coinbase":                                        # windows of at most `lim` candles, end inclusive
        a = s
        while a <= last:
            b = min(a + (lim - 1) * _H, last)
            fmt = lambda x: pd.Timestamp(x, unit="s", tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
            j = _venue_json(f"https://api.exchange.coinbase.com/products/{sym}/candles?granularity=3600&start={fmt(a)}"
                            f"&end={fmt(b)}", gap, lambda x: isinstance(x, list) and len(x) == 0) or []
            if isinstance(j, dict):
                raise RuntimeError(f"coinbase {sym}: {str(j)[:120]}")
            rows += [(int(x[0]), float(x[3]), float(x[2]), float(x[1]), float(x[4]), float(x[5])) for x in j]
            a = b + _H
    else:
        raise ValueError(f"unknown venue {venue}: one of {sorted(VENUES)}")
    return rows


def _venue_holes(ts, s, e, first_month):
    """Runs of more than VENUE_MAX_HOLE_H hours without a candle in [s, e) (unix s, ts sorted unique open times): between
    candles, before the first one (except in the venue's first month, which starts when the venue does) and after the
    last one. [(from, to)] as UTC strings."""
    if not len(ts):
        return [] if first_month else [(str(pd.Timestamp(s, unit="s", tz="UTC")), str(pd.Timestamp(e, unit="s", tz="UTC")))]
    edges = ([] if first_month else [s - _H]) + list(ts) + [e]
    out = []
    for a, b in zip(edges[:-1], edges[1:]):
        if (b - a) // _H - 1 > VENUE_MAX_HOLE_H:
            out.append((str(pd.Timestamp(a + _H, unit="s", tz="UTC")), str(pd.Timestamp(b, unit="s", tz="UTC"))))
    return out


def _venue_month(venue, sym, y, m, first_month=False, allow_holes=False):
    """One month of hourly candles of a venue, cached at <cache>/crypto/<venue>/<sym>/1h/YYYY-MM.csv. The rows outside
    [month start, min(month end, period end)) are dropped BEFORE anything is cached or returned (a server that ignores
    a bound cannot put a later row in the cache). None if the venue has no candle that month.
    Completeness (verifier V3): an empty reply is asked once more (_venue_json); a month with a run of more than
    VENUE_MAX_HOLE_H hours without a candle is NOT cached and raises DataGap, unless allow_holes=True (a real venue
    outage): it is then cached with its holes in YYYY-MM.holes.json, and a later read without allow_holes raises again."""
    if not _allowed(y, m):
        return None
    s0 = pd.Timestamp(year=y, month=m, day=1, tz="UTC")
    e0 = min(s0 + pd.offsets.MonthBegin(1), period_end(), VAL_END)
    path = os.path.join(cache_dir(), "crypto", venue, sym, "1h", f"{y}-{m:02d}.csv")
    hpath = path[:-4] + ".holes.json"
    if os.path.exists(path) and os.path.exists(hpath) and not allow_holes:
        raise DataGap(f"{venue} {sym} {y}-{m:02d}: cached with holes {json.load(open(hpath))['holes'][:3]} (accepted "
                      "earlier with allow_holes=True); pass allow_holes=True to read it")
    if not os.path.exists(path):
        s, e = int(s0.timestamp()), int(e0.timestamp())
        rows = [r for r in _venue_pages(venue, sym, s, e) if s <= r[0] < e]
        holes = _venue_holes(sorted({r[0] for r in rows}), s, e, first_month)
        if holes and not allow_holes:
            raise DataGap(f"{venue} {sym} {y}-{m:02d}: {len(holes)} run(s) of more than {VENUE_MAX_HOLE_H} h without a "
                          f"candle after a second request, first {holes[:3]}; nothing cached. Fetch again later; if it is "
                          "a real venue outage, pass allow_holes=True (the holes are recorded beside the cached month)")
        if holes:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            json.dump({"holes": holes, "max_hole_h": VENUE_MAX_HOLE_H}, open(hpath, "w"))
        txt = "t,open,high,low,close,volume\n" + "".join(f"{r[0]},{r[1]!r},{r[2]!r},{r[3]!r},{r[4]!r},{r[5]!r}\n"
                                                           for r in sorted(set(rows)))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".part", "w") as f:
            f.write(txt if rows else "")
        os.replace(path + ".part", path)
    if os.path.getsize(path) == 0:
        return None
    d = pd.read_csv(path)
    d.index = pd.to_datetime(d.pop("t").to_numpy(np.int64), unit="s", utc=True)
    d = d[d.index < e0]
    return d.astype(float)


def crypto_h1(venue, symbol, start=None, end=None, allow_holes=False):
    """Hourly candles of bitcoin or ether in dollars from a venue before (and after) Binance's 2017-08 start: venue
    'bitstamp' | 'bitfinex' | 'coinbase', symbol an FP key ('btcusd', 'ethusd') or the venue's own symbol. Trade
    prices (treated as mid), UTC bar-open index, columns open high low close volume; behind the period lock like every
    reader (months requested only if they start before the period end, never 2026; each request ends before the
    period end; the 'keep' filter of _venue_month runs before the cache). Bitfinex and Coinbase omit hours without a
    trade, Bitstamp sends them flat with volume 0 (kept, as Binance's klines). A month without candles inside the
    venue's history raises DataGap, and so does a month with a run of more than VENUE_MAX_HOLE_H (48) hours without a
    candle after a second request (nothing is cached; allow_holes=True accepts a real venue outage and records it in
    YYYY-MM.holes.json and attrs['holes']). attrs: venue, symbol, source."""
    if venue not in VENUES:
        raise ValueError(f"unknown venue {venue}: one of {sorted(VENUES)}")
    tab = VENUES[venue]
    key = symbol if symbol in tab else next((k for k, v in tab.items() if v[0] == symbol), None)
    if key is None:
        raise ValueError(f"{venue}: no symbol {symbol} (FP keys {sorted(tab)})")
    sym, first = tab[key]
    p0 = max(pd.Period(first, "M"), pd.Period(start, "M")) if start else pd.Period(first, "M")
    months = [p for p in pd.period_range(p0, _last_month(end), freq="M") if _allowed(p.year, p.month)]
    parts, t0 = [], time.time()
    for q, p in enumerate(months):
        parts.append(_venue_month(venue, sym, p.year, p.month, first_month=(p == pd.Period(first, "M")),
                                  allow_holes=allow_holes))
        if os.environ.get("EXPLORE_PROGRESS") and (q % 12 == 11 or q == len(months) - 1):
            print(f"  {venue} {sym}: {q + 1}/{len(months)} months ({time.time() - t0:.0f} s)", flush=True)
    have = [p for p, d in zip(months, parts) if d is not None and len(d)]
    if have:
        hole = [str(p) for p, d in zip(months, parts) if have[0] < p < have[-1] and (d is None or not len(d))]
        if hole:
            raise DataGap(f"{venue} {sym}: no candles for {len(hole)} month(s) inside its history, first {hole[:4]}: "
                          f"delete those files under {os.path.join(cache_dir(), 'crypto', venue, sym)} and fetch again")
    parts = [d for d in parts if d is not None and len(d)]
    if not parts:
        df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"], dtype=float)
        df.index = pd.DatetimeIndex([], tz="UTC")
    else:
        df = pd.concat(parts).sort_index()
        df = df[~df.index.duplicated(keep="last")]
        bad = ~((df.high >= df[["open", "close"]].max(axis=1) - 1e-9) & (df.low <= df[["open", "close"]].min(axis=1) + 1e-9)
                & (df.low > 0))
        if bad.mean() > 0.001:
            raise ValueError(f"{venue} {sym}: {int(bad.sum())} candles with high/low inconsistent with open/close: "
                             "columns decoded in the wrong order?")
    df.index.name = "time"
    df = cut(df[["open", "high", "low", "close", "volume"]])
    df.attrs.update(venue=venue, symbol=sym, source=f"{venue} download")
    hl = []
    for p in months:
        hp = os.path.join(cache_dir(), "crypto", venue, sym, "1h", f"{p.year}-{p.month:02d}.holes.json")
        if os.path.exists(hp):
            hl += [tuple(h) for h in json.load(open(hp))["holes"]]
    if hl:
        df.attrs["holes"] = hl
    return df


# ---------------------------------------------------------------- known-at rules and external series
def known_at(obs_dates, lag_bdays=0, time="16:00", tz=NY, lag_days=0):
    """UTC time at which a value observed on each (naive) date is known: date + lag_bdays business days + lag_days
    calendar days, at the local wall time `time` in `tz` (daylight saving handled by tz)."""
    d = pd.DatetimeIndex(pd.to_datetime(obs_dates)).normalize()
    if d.tz is not None:
        d = d.tz_localize(None)
    if lag_bdays:
        d = d + pd.offsets.BDay(lag_bdays)
    if lag_days:
        d = d + pd.Timedelta(days=lag_days)
    hh, mm = (int(x) for x in time.split(":"))
    loc = (d + pd.Timedelta(hours=hh, minutes=mm)).tz_localize(tz, ambiguous=False, nonexistent="shift_forward")
    return loc.tz_convert("UTC")


def rule_next_bday_utc(hour_utc=13, lag_bdays=1):
    """Known-at rule: observation date + lag_bdays business days at hour_utc UTC (e.g. FRED daily: D+1 13:00 UTC)."""
    return lambda dates: known_at(dates, lag_bdays=lag_bdays, time=f"{int(hour_utc):02d}:00", tz="UTC")


def rule_local_close(time="16:00", tz=NY, lag_bdays=0):
    """Known-at rule: local close of the observation day (US close 16:00 New York = 21:00 or 20:00 UTC by DST)."""
    return lambda dates: known_at(dates, lag_bdays=lag_bdays, time=time, tz=tz)


def _apply_rule(obs, values, known, name, min_lag=None, keep="last"):
    if known is None or not callable(known):
        raise ValueError("give known=<rule>: a function from observation dates to the UTC time each value is known "
                         "(e.g. data.rule_next_bday_utc(13, 1)); there is no default, on purpose")
    obs = pd.DatetimeIndex(pd.to_datetime(obs))
    obs = obs.tz_localize(None) if obs.tz is not None else obs
    k = pd.DatetimeIndex(known(obs))
    if len(k) != len(obs):
        raise ValueError("known-at rule must return one time per observation")
    k = k.tz_convert("UTC") if k.tz is not None else k.tz_localize("UTC")
    lag = k - obs.tz_localize("UTC")
    if (lag < pd.Timedelta(0)).any():
        raise ValueError("known-at rule returns a time before the observation date itself")
    if min_lag is not None and (lag < pd.Timedelta(min_lag)).any():
        bad = int((lag < pd.Timedelta(min_lag)).sum())
        raise ValueError(f"{name}: the known-at rule makes {bad} values known less than the declared publication lag "
                         f"{pd.Timedelta(min_lag)} after their observation date: the rule leaks")
    if keep not in ("last", "all"):
        raise ValueError("keep is 'last' (one row per known-at time, the default) or 'all' (every row)")
    d = pd.DataFrame({"v": np.asarray(values, float), "obs": obs}, index=k)
    d = d[~np.isnan(d.v.to_numpy())].sort_index(kind="mergesort")      # stable: rows known together keep their order
    if keep == "last":
        d = d[~d.index.duplicated(keep="last")]
    d = d[pd.DatetimeIndex(d.index) < period_end()]
    s = pd.Series(d.v.to_numpy(), index=d.index, name=name)
    s.attrs["obs_date"] = d.obs.to_numpy()
    s.attrs["min_lag"] = None if min_lag is None else str(pd.Timedelta(min_lag))
    return cut(s)


def external(obs_dates, values, known, min_lag=None, name="external", keep="last"):
    """Any custom external series (GDELT, a scraped table, ...): values observed on `obs_dates` (naive dates or
    timestamps), indexed by the time each is KNOWN (`known` rule, no default) and cut at the period end. `min_lag` (a
    Timedelta, REQUIRED) is the declared publication lag: every known_at must be at least obs_date + min_lag, else it
    raises (verifier V4: a series indexed by its observation date passes the truncation test while it leaks, because
    its own index is the lie; this check is the guard). The observation dates stay in s.attrs['obs_date'].
    keep='last' (default): one row per known-at time, the last given. keep='all': every row is kept, rows known at the
    same time in their input order (an event calendar where several events are announced together); for events that
    carry labels (tickers, kinds) use event_table."""
    if min_lag is None:
        raise ValueError("data.external: give min_lag=<declared publication lag> (e.g. pd.Timedelta(hours=1) for a "
                         "15-minute GDELT file published at its slot's end + processing)")
    return _apply_rule(obs_dates, values, known, name, min_lag, keep)


def event_table(obs_dates, known, min_lag, name="events", **columns):
    """An event calendar as a table: one row per event (NONE dropped, several may share a known-at time), indexed by
    the time each event is KNOWN (`known` rule from the observation dates, no default) and cut at the period end, with
    column obs_date and the given columns (e.g. market=tickers, kind=..., value=...). min_lag (REQUIRED) is the declared
    publication lag, enforced on every row as in external(). Rows known together keep their input order. Use it as an
    item of a truncation test's data with row_len 0, and asof_join(..., agg=) to combine rows known together."""
    if min_lag is None:
        raise ValueError("data.event_table: give min_lag=<declared publication lag>")
    obs = pd.DatetimeIndex(pd.to_datetime(obs_dates))
    obs = obs.tz_localize(None) if obs.tz is not None else obs
    for c, v in columns.items():
        if len(v) != len(obs):
            raise ValueError(f"event_table: column {c} has {len(v)} rows for {len(obs)} observation dates")
    vals = np.arange(len(obs), dtype=float)                          # row numbers through the same checked path
    s = _apply_rule(obs, vals, known, name, min_lag, keep="all")
    pos = s.to_numpy().astype(np.int64)
    t = pd.DataFrame({"obs_date": obs[pos]}, index=s.index)
    for c, v in columns.items():
        t[c] = np.asarray(v, dtype=object if not np.issubdtype(np.asarray(v).dtype, np.number) else None)[pos]
    t.index.name = "known_at"
    t.attrs["min_lag"] = s.attrs["min_lag"]
    return cut(t)


def fred(series, known, start="1990-01-01", end=None, min_lag=None, revised_ok=False):
    """A FRED series through fredgraph.csv with cosd=start and coed = the last day of the open period, indexed by the
    time each value is KNOWN (rule given by the caller). Missing values ('.') dropped.
    VINTAGES: fredgraph.csv returns TODAY's values, revisions included, not what was known at the time. Market series
    (rates, spreads, VIX, dollar index: daily, never revised) are fine. Weekly / monthly / quarterly series (dated at
    the START of their period for most monthly series and published weeks later, then revised) are refused unless the
    caller gives min_lag (declared publication lag from the observation date, checked on every row: e.g. 40 days for a
    monthly series dated the 1st and released mid-next-month) AND revised_ok=True (the declaration states that
    revised values are used, or the rule only uses series that are not revised). For the as-first-published values,
    ALFRED (alfred.stlouisfed.org, vintage dates) is the source; it is not wired in the kit."""
    last = period_end() - pd.Timedelta(days=1)
    end = (min(last, pd.Timestamp(end, tz="UTC")) if end is not None else last).strftime("%Y-%m-%d")
    path = os.path.join(cache_dir(), "fred", f"{series}_{start}_{end}.csv")
    raw = _cached(path, f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd={start}&coed={end}",
                  keep=_fred_keep)
    if not raw:
        raise RuntimeError(f"FRED {series}: no data")
    d = pd.read_csv(io.BytesIO(raw), na_values=["."])
    obs = pd.to_datetime(d.iloc[:, 0])
    keep = obs < period_end().tz_localize(None)
    gap = float(np.median(np.diff(obs[keep].to_numpy()).astype("timedelta64[h]").astype(float) / 24)) if keep.sum() > 2 else 1.0
    if gap > 4 and (min_lag is None or not revised_ok):
        raise ValueError(f"FRED {series}: observations every ~{gap:.0f} days (not daily): give min_lag=<publication lag "
                         "from the observation date> and revised_ok=True (fredgraph.csv serves revised values)")
    s = _apply_rule(obs[keep], d.iloc[:, 1][keep], known, series, min_lag)
    s.attrs["vintage"] = "current (revised values) from fredgraph.csv"
    s.attrs["obs_every_days"] = gap
    return s


def yahoo_daily(ticker, known, field="close", start="1990-01-01", end=None):
    """Daily bars from Yahoo's chart API with period2 bounded by the period end; one field (open/high/low/close/
    adjclose/volume) indexed by the time it is KNOWN (rule from the exchange-local date, given by the caller)."""
    p1 = int(pd.Timestamp(start, tz="UTC").timestamp())
    p2 = int(period_end().timestamp()) - 1
    if end is not None:
        p2 = min(p2, int(pd.Timestamp(end, tz="UTC").timestamp()))
    path = os.path.join(cache_dir(), "yahoo", f"{ticker.replace('^', '_').replace('=', '_')}_{p1}_{p2}.json")
    raw = _cached(path, f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1={p1}&period2={p2}"
                        f"&interval=1d&events=div%2Csplit", keep=_yahoo_keep)
    j = json.loads(raw)["chart"]["result"][0]
    tz = j["meta"].get("exchangeTimezoneName", NY)
    t = pd.to_datetime(np.asarray(j["timestamp"], dtype=np.int64), unit="s", utc=True)
    q = j["indicators"]["quote"][0]
    vals = j["indicators"]["adjclose"][0]["adjclose"] if field == "adjclose" else q[field]
    vals = np.array([np.nan if v is None else v for v in vals], float)
    obs = t.tz_convert(tz).tz_localize(None).normalize()
    keep = np.asarray(t < period_end())
    return _apply_rule(obs[keep], vals[keep], known, ticker)


AGG = ("last", "first", "sum", "mean", "max", "min", "count")


def asof_join(times, series, agg="last"):
    """Value of `series` (indexed by known-at time, UTC) last known at each of `times`: strictly backward-looking, a value
    known at exactly t counts as known at t. NaN where nothing is known yet. Several rows known at the SAME time (a
    series from external(..., keep='all')) are combined first by `agg`: 'last' (the default: the last row given, as
    before), 'first', 'sum', 'mean', 'max', 'min' or 'count'."""
    if agg not in AGG:
        raise ValueError(f"agg is one of {AGG}")
    s = series.sort_index(kind="mergesort")
    if agg == "last":
        s = s[~s.index.duplicated(keep="last")]
    elif s.index.has_duplicates:
        s = s.groupby(level=0, sort=True).agg(agg).astype(float)
    kn = pd.DatetimeIndex(s.index).tz_convert("UTC").as_unit("ns").asi8
    tt = pd.DatetimeIndex(times)
    tt = (tt.tz_convert("UTC") if tt.tz is not None else tt.tz_localize("UTC")).as_unit("ns").asi8
    i = np.searchsorted(kn, tt, side="right") - 1
    v = s.to_numpy(float)
    out = np.where(i >= 0, v[np.clip(i, 0, None)], np.nan) if len(v) else np.full(len(tt), np.nan)
    return out


# ---------------------------------------------------------------- bars
def trading_day(ts):
    """FX trading day: a new day starts at 17:00 New York (lab/goldlab/data.py trading_day). Naive dates."""
    ny = pd.DatetimeIndex(ts).tz_convert(NY)
    return (ny + pd.Timedelta(hours=7)).tz_localize(None).normalize()


def daily_bars(h1, boundary="ny17", bar=pd.Timedelta(hours=1)):
    """Daily bars from hourly bars. boundary 'ny17': day = 17:00 New York to 17:00 New York (FX convention, DST
    correct, label = the date the day ends); 'utc': UTC calendar day. Columns open high low close volume n_bars
    known_at (end of the day's last bar: use it, never the label, to time a signal)."""
    lab = trading_day(h1.index) if boundary == "ny17" else pd.DatetimeIndex(h1.index).tz_convert("UTC").tz_localize(None).normalize()
    g = h1.groupby(lab)
    d = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                      "close": g["close"].last(), "n_bars": g["open"].size()})
    if "volume" in h1:
        d["volume"] = g["volume"].sum()
    d["known_at"] = pd.Series(h1.index, index=lab).groupby(level=0).max() + bar
    d.index.name = "day"
    return d


def prefetch(keys, start_year=2013, budget_s=None):
    """Download (or find in the cache) the hourly bars of FP keys, market by market, with progress, and stop cleanly
    at the budget. Returns {key: {'status': 'ok' | 'stopped (budget)' | 'error: ...', 'files', 'seconds'}}; a run that
    gets 'stopped' writes 'en cours' in the ledger and leaves the rest to the next run (the cache keeps what came).
    CLI: python3 -B lab/explore/kit/data.py prefetch us500 eurusd --budget 1200 [--start 2013]"""
    if budget_s is not None:
        set_deadline(budget_s)
    out = {}
    try:
        for k in keys:
            t0 = time.time()
            m = fp_markets()[k]
            sub = os.path.join(cache_dir(), "duka", m["symbol"]) if m["source"] == "dukascopy" else \
                os.path.join(cache_dir(), "binance", "spot", "klines", m["symbol"], "1h")
            try:
                b = load_bars(k, start_year)
                st = "ok" if len(b) else "error: no bars"
            except BudgetExceeded:
                st = "stopped (budget)"
            except Exception as e:      # one market failing does not stop the others
                st = f"error: {type(e).__name__}: {str(e)[:120]}"
            nf = sum(len(f) for _, _, f in os.walk(sub)) if os.path.isdir(sub) else 0
            out[k] = {"status": st, "files": nf, "seconds": round(time.time() - t0, 1)}
            print(f"prefetch {k}: {out[k]}", flush=True)
            if st.startswith("stopped"):
                for r in keys[keys.index(k) + 1:]:
                    out[r] = {"status": "stopped (budget)", "files": 0, "seconds": 0.0}
                break
    finally:
        if budget_s is not None:
            set_deadline(None)
    return out


def h1_dirs():
    """Folders searched, in order, for prepared hourly bars <fp key>.parquet: EXPLORE_H1_DIR, <cache>/h1, and
    lab/explore/prices/h1 in the repository (present only if the lead committed it)."""
    d = [os.environ.get("EXPLORE_H1_DIR"), os.path.join(cache_dir(), "h1"), os.path.join(KIT, "..", "prices", "h1")]
    return [os.path.abspath(x) for x in d if x]


def local_h1(key, start_year=2013):
    """Prepared hourly BID bars of an FP key (UTC bar-open index 'time'; open high low close; volume = number of
    one-minute bars in the hour, NOT traded volume), or None if no folder of h1_dirs() holds <key>.parquet. Rows are
    filtered inside the read: before 2022 while locked; after unlock_val the sibling folder '<dir>_val' (2022-2025) is
    added if it exists, else None is returned so that the caller falls back to the download. Never a row of 2026."""
    for d in h1_dirs():
        p = os.path.join(d, f"{key}.parquet")
        if not os.path.isfile(p):
            continue
        lim = min(period_end(), VAL_END)
        parts = [pd.read_parquet(p, filters=[("time", "<", min(lim, IS_END))])]
        if lim > IS_END:
            pv = os.path.join(d.rstrip("/") + "_val", f"{key}.parquet")
            if not os.path.isfile(pv):
                return None
            parts.append(pd.read_parquet(pv, filters=[("time", ">=", IS_END), ("time", "<", lim)]))
        b = pd.concat(parts).sort_index()
        idx = pd.DatetimeIndex(b.index)
        b.index = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
        b.index.name = "time"
        b = b[~b.index.duplicated(keep="last")]
        b = b[b.index >= pd.Timestamp(year=start_year, month=1, day=1, tz="UTC")]
        sym = FP[key][1]
        med = float(b.close.median()) if len(b) else float("nan")
        if len(b) and not (REF[sym] / 4 < med < REF[sym] * 4):
            raise ValueError(f"{key}: median price {med} of {p} far from the expected {REF[sym]}")
        b = cut(b[["open", "high", "low", "close", "volume"]].astype(float))
        b.attrs["source"] = f"prepared hourly bars ({d})"
        return b
    return None


def load_bars(key, start_year=2013, venue=None, allow_holes=False):
    """FP-ready hourly bars of an FP cost key: prepared hourly BID bars if a folder of h1_dirs() has them (no
    download), else Dukascopy BID (price_is 'bid') or Binance 1h (price_is 'mid'), with the FP crypto closure removed.
    Cut at the period end. b.attrs['source'] says where the bars came from.
    venue (btcusd / ethusd only): 'bitstamp' | 'bitfinex' | 'coinbase' reads crypto_h1 from start_year (or the venue's
    first month) instead of Binance (lead's ruling of 2026-11-18 (b): the declaration names the venue that prices the
    trades; costs stay FP's); price_is 'mid', FP's weekend closure removed, attrs['venue'] says which. None or
    'binance': the default, unchanged. allow_holes: passed to crypto_h1 (a venue month with a run of more than 48 h
    without a candle raises DataGap unless allowed)."""
    m = fp_markets()[key]
    if m["source"] == "local":
        if venue not in (None, "binance"):
            raise ValueError(f"venue= is for the crypto keys (btcusd, ethusd), not {key}")
        b = local_h1(key, start_year)
        if b is None:
            raise FileNotFoundError(
                f"{key}: a local-only market (prepared hourly bars, no download path): no {key}.parquet in "
                f"{h1_dirs()}" + ("" if period_end() <= IS_END else " or no validation file in their sibling '<dir>_val' "
                                  "folders") + ". The lead builds it with lab/explore/lead/build_h1_from_lab.py.")
        src = b.attrs["source"]
        mbm = int(_C.spec(key).get("min_bar_minutes", 0))
        nshort = 0
        if mbm and len(b):                     # kit v2.1 fix (V21-7): a share 'hour' of fewer minutes is not a bar
            keep = b.volume.to_numpy() >= mbm
            nshort = int((~keep).sum())
            b = b[keep]
        b = _adjust_splits(key, b)
        b = _adjust_rolls(key, b)
        b.attrs.update(price_is="bid", market=key, source=src)
        if mbm:
            b.attrs["short_bars_dropped"] = nshort
        return b
    if venue not in (None, "binance"):
        if m["source"] != "binance":
            raise ValueError(f"venue= is for the crypto keys (btcusd, ethusd), not {key}")
        b = crypto_h1(venue, key, start=f"{start_year}-01", allow_holes=allow_holes)
        src = b.attrs["source"]
        b = fp_hours(key, b)
        b.attrs.update(price_is="mid", market=key, source=src, venue=venue)
        return b
    b = local_h1(key, start_year) if m["source"] == "dukascopy" else None
    if b is not None:
        pass
    elif m["source"] == "dukascopy":
        b = duka_h1(m["symbol"], start_year)
        b.attrs["source"] = "dukascopy download"
    else:
        b = binance_klines(m["symbol"], "1h", start=f"{max(start_year, 2017)}-{'08' if start_year <= 2017 else '01'}")
    src = b.attrs.get("source", "binance download")
    b = fp_hours(key, b)
    b.attrs["price_is"], b.attrs["market"], b.attrs["source"] = m["price_is"], key, src
    return b


SPLIT_RATIOS = (1.5, 2, 3, 4, 5, 6, 7, 8, 10, 15, 20, 25, 50)    # lab/prep_round3.py RATIOS


def overnight_ratios(bars):
    """Previous 17:00-NY day's last close / this day's first open, per day (the move a split makes)."""
    td = trading_day(bars.index)
    g = bars.groupby(td)
    d = pd.DataFrame({"o": g["open"].first(), "c": g["close"].last()})
    return (d.c.shift(1) / d.o).dropna()


def _listed_splits(key):
    """{ex-date (naive Timestamp): ratio} of a share's splits before the period end; raises PeriodError when the period
    end is past the entry's splits_checked_to (the later splits are not in the kit)."""
    sp = _C.spec(key)
    end = period_end()
    chk = pd.Timestamp(sp.get("splits_checked_to", "1900-01-01")).tz_localize(NY) + pd.Timedelta(days=1)
    if end > chk.tz_convert("UTC"):
        raise PeriodError(f"{key}: its splits are checked to {sp.get('splits_checked_to')} only; reading to {end} needs "
                          "the later splits in kit/extra_costs.json first (splits, splits_checked_to)")
    kend = known_end()
    return {pd.Timestamp(d): float(q) for d, q in sp.get("splits", {}).items() if pd.Timestamp(d).tz_localize(NY) < kend}


def _nyse_holidays(y0, y1):
    """NYSE full-day holidays (rules; special closures not included), as naive dates: the business-day calendar of the
    NYMEX CL expiry rule (the lab's oil data rolls with the front WTI future)."""
    from pandas.tseries.holiday import (AbstractHolidayCalendar, GoodFriday, Holiday, USLaborDay, USMartinLutherKingJr,
                                        USMemorialDay, USPresidentsDay, USThanksgivingDay, nearest_workday,
                                        sunday_to_monday)

    class _NYSE(AbstractHolidayCalendar):
        rules = [Holiday("NewYear", month=1, day=1, observance=sunday_to_monday), USMartinLutherKingJr, USPresidentsDay,
                 GoodFriday, USMemorialDay, Holiday("Juneteenth", month=6, day=19, start_date="2022-01-01",
                                                    observance=nearest_workday),
                 Holiday("July4", month=7, day=4, observance=nearest_workday), USLaborDay, USThanksgivingDay,
                 Holiday("Christmas", month=12, day=25, observance=nearest_workday)]
    return set(_NYSE().holidays(f"{y0}-01-01", f"{y1}-12-31"))


def cl_expiry(year, month, hol=None):
    """NYMEX WTI (CL) last trading day of the contract expiring in that month: 3 business days before the 25th (the
    business day before the 25th first when the 25th is not one). Naive date."""
    hol = _nyse_holidays(year, year) if hol is None else hol
    isbd = lambda x: x.weekday() < 5 and x not in hol      # noqa: E731
    x = pd.Timestamp(year, month, 25)
    while not isbd(x):
        x -= pd.Timedelta(days=1)
    k = 0
    while k < 3:
        x -= pd.Timedelta(days=1)
        k += isbd(x)
    return x


_ASOF = [None]      # kit v2.1 fix 2 (KF-2): the cut of checks.truncation_test while a cut build runs, else None


class asof:
    """Context: rolls and splits as they were known at time t (checks.truncation_test runs each cut build inside it):
    roll_times, price_factor, split_factor and the cut copies of the bars then ignore every roll / split at or after
    t, so a build that reads an absolute adjusted level, or data.price_factor, sees what it would have seen at t."""

    def __init__(self, t):
        self.t = None if t is None else pd.Timestamp(t)

    def __enter__(self):
        self.prev = _ASOF[0]
        _ASOF[0] = self.t
        return self

    def __exit__(self, *a):
        _ASOF[0] = self.prev
        return False


def known_end():
    """End of what is known: the period end, or the cut of a truncation test's cut build (asof) if earlier."""
    a = _ASOF[0]
    return period_end() if a is None else min(period_end(), a)


def roll_times(key):
    """Contract-roll times (UTC: the first bar on the new contract) of a futures-based local market (cost entry
    'rolls' {time: ratio}, listed to 'rolls_checked_to') before known_end(); after rolls_checked_to (validation years)
    the rule of the listed years' end: the 18:00 New York reopen that starts the trading day one business day before
    the CL expiry (cl_expiry). [] for every other market."""
    sp = _C.spec(key)
    if "rolls" not in sp:
        return []
    end = known_end()
    out = [pd.Timestamp(t) for t in sp["rolls"] if pd.Timestamp(t) < end]
    chk = pd.Timestamp(sp.get("rolls_checked_to", "1900-01-01"))
    m = (chk + pd.Timedelta(days=1)).to_period("M")
    hol = _nyse_holidays(m.year, end.year + 1)
    while True:
        e = cl_expiry(m.year, m.month, hol)
        x = e - pd.Timedelta(days=1)
        while x.weekday() >= 5 or x in hol:
            x -= pd.Timedelta(days=1)
        t = (x - pd.Timedelta(days=1) + pd.Timedelta(hours=18)).tz_localize(NY).tz_convert("UTC")
        if t >= end:
            break
        if e > chk:
            out.append(t)
        m += 1
    return sorted(out)


_ROLLS_MEASURED = {}  # key -> {rule roll time: ratio measured by load_bars} (validation years only); merged, never replaced


def _normal_break(t0, t1):
    """True if the bars t0 -> t1 (consecutive bar open times) span no more than the market's normal break: the daily
    17:00-18:00 New York pause (2 h between bar opens) or a weekend (Friday -> Sunday/Monday, at most 50 h)."""
    h = (t1 - t0) / pd.Timedelta(hours=1)
    if h <= 2:
        return True
    a, b = t0.tz_convert(NY), t1.tz_convert(NY)
    return a.dayofweek == 4 and b.dayofweek in (6, 0) and h <= 50


def _roll_table(key, since=None):
    """{roll time: ratio new / old} of the rolls before known_end() (and after `since`, if given): the LISTED rolls of
    extra_costs.json (in sample: dated and sized from outside settlements, kit v2.1 fix 2, KF-1) and, after
    rolls_checked_to, the rule rolls with the ratio load_bars measured in this process (_ROLLS_MEASURED). A rule roll
    that is needed but was not measured raises DataGap (sim.Book then refuses the bars: load_bars them first)."""
    sp = _C.spec(key)
    if "rolls" not in sp:
        return {}
    listed = {pd.Timestamp(t): float(q) for t, q in sp["rolls"].items()}
    meas = _ROLLS_MEASURED.get(key, {})
    out = {}
    for r in roll_times(key):
        if since is not None and r <= since:
            continue
        if r in listed:
            out[r] = listed[r]
        elif r in meas:
            out[r] = meas[r]
        else:
            raise DataGap(f"{key}: the roll at {r} (validation years, rule) has no ratio in this process: build the bars "
                          f"with data.load_bars('{key}') (which measures it) before using them")
    return out


def _adjust_rolls(key, b):
    """Back-adjust a futures-based local market (oil) for its contract rolls (kit v2.1 fix 2, KF-1/KF-3/KF-7): every
    price of the bars before a roll is multiplied by its ratio (as a share split), so the series is the continuous rolled
    future. In sample the ratio is the LISTED one (extra_costs.json oil.rolls: the roll dated where Dukascopy's price
    switches from the outside front-month settlement to the next one, and sized as next / front settled on the last day
    before the switch, EIA NYMEX WTI contract 1 / 2), so the real move of the roll night stays in the series. After
    rolls_checked_to (validation years) the ratio is measured on the bars at the rule's reopen (first open / previous
    close; it then includes that night's real move, README limits) and kept in a private table (merged across loads);
    a reopen that comes after a hole longer than the normal break raises DataGap (list that roll first). Nothing about
    the rolls is put in the bars or their attrs (a build could read a later roll from them)."""
    sp = _C.spec(key)
    if "rolls" not in sp or not len(b):
        return b
    t = b.index
    o, c = b.open.to_numpy(float), b.close.to_numpy(float)
    listed = {pd.Timestamp(x) for x in sp["rolls"]}
    meas = _ROLLS_MEASURED.setdefault(key, {})
    for r in roll_times(key):
        if r in listed:
            continue
        i = int(t.searchsorted(r))
        if 0 < i < len(t):
            if not _normal_break(t[i - 1], t[i]):
                raise DataGap(f"{key}: the rule roll at {r} reopens at {t[i]} after a hole from {t[i - 1]}: its ratio "
                              "cannot be measured across the hole (it would include the real move): list this roll's "
                              "time and ratio (next / front contract settled before the switch, e.g. EIA RCLC2 / RCLC1) "
                              "in kit/extra_costs.json oil.rolls and move rolls_checked_to")
            meas[r] = float(o[i] / c[i - 1])
    tab = _roll_table(key, since=t[0])
    out = b.copy()
    if tab:
        adj = _roll_adj(t, tab)
        for col in ("open", "high", "low", "close"):
            out[col] = out[col].to_numpy() * adj
    out.attrs.update(b.attrs)
    return out


def _roll_adj(index, applied):
    idx = pd.DatetimeIndex(index)
    adj = np.ones(len(idx))
    for x, q in applied.items():
        adj[np.asarray(idx < pd.Timestamp(x))] *= q
    return adj


def price_factor(key, index):
    """Adjusted / raw price of each bar time: split_factor (shares) x the roll adjustment of a futures-based market (the
    listed ratios in sample, the ratios load_bars measured in the validation years; DataGap if one is needed and was not
    measured in this process). As known at known_end() (checks.truncation_test: at its cut). sim.Book scales the
    per-unit commission and an absolute spread (oil's spread_abs) by it."""
    idx = pd.DatetimeIndex(index)
    f = split_factor(key, idx)
    if "rolls" in _C.spec(key) and len(idx):
        tab = _roll_table(key, since=idx.min())
        if tab:
            f = f * _roll_adj(idx, tab)
    return f


def has_adjustment(key):
    """True for a market whose loaded bars are back-adjusted (share splits, oil rolls)."""
    sp = _C.spec(key)
    return "splits" in sp or "rolls" in sp


def split_factor(key, index):
    """Adjusted / raw price of each bar time of a share with splits (1.0 for every other market): the product of 1 / ratio
    over the splits whose ex-date (New York midnight) is after the bar and before the period end. sim.Book scales the
    per-unit commission by it (one adjusted unit before a 4:1 split is a quarter of a real share)."""
    idx = pd.DatetimeIndex(index)
    adj = np.ones(len(idx))
    if "splits" not in _C.spec(key):
        return adj
    for d, q in _listed_splits(key).items():
        adj[np.asarray(idx < d.tz_localize(NY))] /= q
    return adj


def check_adjusted(key, bars):
    """Raise ValueError if a share's bars still show a listed split as an overnight jump, or oil's bars are raw at a
    listed contract roll (ratio beyond 0.2 %): the bars' reopen move there equals the vendor's raw move recorded in
    extra_costs.json oil.rolls_vendor_gap, or equals the roll ratio itself (raw bars: give the bars of data.load_bars,
    which back-adjusts them)."""
    sp = _C.spec(key)
    if "rolls" in sp and len(bars):
        t = bars.index
        o, c = bars.open.to_numpy(float), bars.close.to_numpy(float)
        vg = {pd.Timestamp(x): float(v) for x, v in sp.get("rolls_vendor_gap", {}).items()}
        for r, q in sp["rolls"].items():
            r = pd.Timestamp(r)
            i = int(t.searchsorted(r))
            if 0 < i < len(t) and t[i] == r and abs(q - 1) > 0.002:
                g = o[i] / c[i - 1]
                if abs(g / q - 1) < 1e-4 or (r in vg and abs(g / vg[r] - 1) < 1e-9 and abs(vg[r] / q - 1) > 1e-4):
                    raise ValueError(f"{key}: the bars jump at the listed contract roll {r} as the raw data do: they "
                                     "are not roll-adjusted (use data.load_bars)")
    if "splits" not in sp or not len(bars):
        return
    r = overnight_ratios(bars)
    for d, q in _listed_splits(key).items():
        if d in r.index and abs(r[d] / q - 1) < 0.04:
            raise ValueError(f"{key}: the bars jump by the split ratio {q} on {d.date()}: they are not split-adjusted "
                             "(use data.load_bars)")


def _adjust_splits(key, b):
    """Back-adjust a local share's raw bars for its splits (cost entry 'splits' {ex-date: ratio}, 'splits_checked_to'):
    prices of the bars before the ex-date (New York midnight) are divided by the ratio, so the series is continuous in
    the units of the period end (lab/prep_round3.py, which also scales its frames' commission: sim.Book does it with
    split_factor). Only splits before the period end are applied. Guards: a read past splits_checked_to raises PeriodError (the split list must be completed first: the
    validation years' splits are not in the kit); a listed split whose day does not show its ratio, or a day whose
    overnight move looks like an unlisted split (lab/prep_round3.py rule: within 4 % of a usual ratio, unless the entry
    lists the day in 'not_splits'), raises DataGap."""
    sp = _C.spec(key)
    if "splits" not in sp:
        return b
    listed = _listed_splits(key)
    if not len(b):
        return b
    r = overnight_ratios(b)
    for d, q in listed.items():
        if d in r.index and not abs(r[d] / q - 1) < 0.04:
            raise DataGap(f"{key}: listed split {d.date()} ({q}) but the bars' overnight ratio that day is {r[d]:.4f}")
    skip = {pd.Timestamp(x) for x in sp.get("not_splits", [])} | {pd.Timestamp(x) for x in sp.get("splits", {})}
    for d, x in r.items():
        if d in listed or d in skip:
            continue
        if any(abs(x / q - 1) < 0.04 or abs(x * q - 1) < 0.04 for q in SPLIT_RATIOS):
            raise DataGap(f"{key}: the overnight move of {d.date()} (ratio {x:.4f}) looks like an unlisted split: check it "
                          "and add it to 'splits' (or to 'not_splits') in kit/extra_costs.json")
    adj = split_factor(key, b.index)
    out = b.copy()
    for c in ("open", "high", "low", "close"):
        out[c] = out[c].to_numpy() * adj
    out.attrs.update(b.attrs)
    out.attrs["splits_applied"] = {str(d.date()): q for d, q in listed.items()}
    return out


if __name__ == "__main__":
    import sys
    a = sys.argv[1:]
    if not a or a[0] != "prefetch":
        sys.exit("usage: python3 -B lab/explore/kit/data.py prefetch <fp key> ... [--budget SECONDS] [--start YEAR]")
    opt = lambda f, d: type(d)(a[a.index(f) + 1]) if f in a else d  # noqa: E731
    ks = [x for i, x in enumerate(a[1:], 1) if not x.startswith("--") and a[i - 1] not in ("--budget", "--start")]
    os.environ.setdefault("EXPLORE_PROGRESS", "1")
    r = prefetch(ks, opt("--start", 2013), opt("--budget", 0.0) or None)
    print(json.dumps(r, indent=1))
