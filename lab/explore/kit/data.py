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
        out[k] = {"source": "dukascopy" if src == "duka" else "binance", "symbol": sym, "point": pt,
                  "price_is": "mid" if crypto else "bid", "weekdays_only": crypto,
                  "hours": "closed Fri 23:55 - Mon 00:00 server (NY+7h)" if crypto else "bars that exist in the data"}
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


def _apply_rule(obs, values, known, name, min_lag=None):
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
    d = pd.DataFrame({"v": np.asarray(values, float), "obs": obs}, index=k)
    d = d[~np.isnan(d.v.to_numpy())].sort_index()
    d = d[~d.index.duplicated(keep="last")]
    d = d[pd.DatetimeIndex(d.index) < period_end()]
    s = pd.Series(d.v.to_numpy(), index=d.index, name=name)
    s.attrs["obs_date"] = d.obs.to_numpy()
    s.attrs["min_lag"] = None if min_lag is None else str(pd.Timedelta(min_lag))
    return cut(s)


def external(obs_dates, values, known, min_lag=None, name="external"):
    """Any custom external series (GDELT, a scraped table, ...): values observed on `obs_dates` (naive dates or
    timestamps), indexed by the time each is KNOWN (`known` rule, no default) and cut at the period end. `min_lag` (a
    Timedelta, REQUIRED) is the declared publication lag: every known_at must be at least obs_date + min_lag, else it
    raises (verifier V4: a series indexed by its observation date passes the truncation test while it leaks, because
    its own index is the lie; this check is the guard). The observation dates stay in s.attrs['obs_date']."""
    if min_lag is None:
        raise ValueError("data.external: give min_lag=<declared publication lag> (e.g. pd.Timedelta(hours=1) for a "
                         "15-minute GDELT file published at its slot's end + processing)")
    return _apply_rule(obs_dates, values, known, name, min_lag)


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


def asof_join(times, series):
    """Value of `series` (indexed by known-at time, UTC) last known at each of `times`: strictly backward-looking, a value
    known at exactly t counts as known at t. NaN where nothing is known yet."""
    s = series.sort_index()
    s = s[~s.index.duplicated(keep="last")]
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
