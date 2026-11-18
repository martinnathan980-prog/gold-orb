"""Daily bars of the broad US universe (direction 3, lead/DIRECTION3.md), 2016-01-01..2021-12-31, from Yahoo's chart API.

    PYTHONDONTWRITEBYTECODE=1 python3 -B prices_d1.py fetch [SYM ...]  # download (cached, resumable) Yahoo replies
    PYTHONDONTWRITEBYTECODE=1 python3 -B prices_d1.py build            # write bars/, dividends.csv, splits.csv, info.json
    PYTHONDONTWRITEBYTECODE=1 python3 -B prices_d1.py test             # quality checks (no network), counts printed
    PYTHONDONTWRITEBYTECODE=1 python3 -B prices_d1.py report           # liquidity figures and lists (no network)
    PYTHONDONTWRITEBYTECODE=1 python3 -B prices_d1.py selftest         # strip() and build/test on synthetic replies

Input: ~/explore_data/d1/universe.csv (scout/universe_us.py): rows with in_universe true (role 'universe') and rows with
in_lab40 true (role 'lab40', only to check the daily bars against the lab's hourly bars), plus Alibaba (BABA, one of
the lab's 40 but not in the S&P list). All output goes to ~/explore_data/d1/ (never into the repository).

THE PERIOD LOCK. One request per share: period1 = 2016-01-01 00:00 UTC, period2 = 2022-01-01 00:00 UTC. The reply is
stripped IN MEMORY before anything is written: the 'meta' block (it carries TODAY's price and dates) is read only for
nothing at all - it is deleted unread -, 'adjclose' is deleted (its level depends on dividends paid up to today: a
leak), and every time stamp whose New York date is after 2021-12-31 is dropped, as are dividend and split events dated
after 2021-12-31. The cache file raw_yahoo/<SYM>.json holds only: timestamps, open/high/low/close/volume, the kept
events, and one small number computed in memory before adjclose is dropped (adjclose_check, see below).

WHAT YAHOO'S QUOTE PRICES ARE (verified by `test`, see check 'adjustment'):
- adjusted for EVERY split up to today, including splits after 2021: the LEVELS of 2016-2021 carry later splits
  (Amazon's 20:1 of 2022: Yahoo's 2021 prices are 1/20 of the prices traded then). Ratios (returns) are unaffected.
  Volume ('shares') is split-adjusted the same way; dollar volume (close x shares) is not affected.
- NOT adjusted for dividends: the quote close drops by the dividend on the ex-date. adjclose is (checked in memory at
  fetch time: the step of adjclose/close on each ex-date equals 1 - dividend / previous close; the median and worst
  error are kept as adjclose_check).

Bars (bars/<key>.parquet): UTC index 'time' = the session's OPEN (09:30 New York, daylight saving applied); columns
open high low close (float, Yahoo quote prices), volume = the session's length in MINUTES (390, 210 on 13:00 half days:
the kit reads 'volume' as a count of minutes), shares = Yahoo's traded volume. One row per NYSE session.

Calendar: from 2017-01-26 the sessions are the days on which the lab's 40 shares have hourly bars (~/explore_data/h1,
through the kit); half days = days on which the lab's hourly bars hold fewer than 90 minutes of quotes from 13:00 New York (median
over the shares; a full day has 180; the BID bars sometimes carry a few sparse quotes after a 13:00 close). Before 2017-01-26 (no hourly bars)
the NYSE holiday rules (kit/data.py _nyse_holidays) and the one half day of that stretch (2016-11-25) are used; the rule
calendar is compared with the hourly one on the overlap (check 'calendar').
"""
import json, os, sys, time, urllib.error, urllib.request
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))          # lab/explore -> 'from kit import data'
UNIV = os.path.expanduser("~/explore_data/d1/universe.csv")
D1 = os.path.expanduser(os.environ.get("PRICES_D1_OUT", "~/explore_data/d1"))   # selftest points it elsewhere
RAW = os.path.join(D1, "raw_yahoo")
BARS = os.path.join(D1, "bars")
LOG = os.path.join(D1, "fetch_log.json")
NY = "America/New_York"
P1 = int(pd.Timestamp("2016-01-01", tz="UTC").timestamp())
P2 = int(pd.Timestamp("2022-01-01", tz="UTC").timestamp())               # exclusive
LAST_DAY = "2021-12-31"
HOURLY_FROM = "2017-01-26"                                               # first day of the lab's hourly share bars
# Yahoo answers 429 to a full browser string sent by a script (checked 2026-11-18: the Chrome string above got 429 on
# the first request, the short one below got 200 from the same machine a minute later); nothing personal is sent.
UA = {"User-Agent": "Mozilla/5.0"}
H1_ALIAS = {"meta": "fb"}                                                # key in universe.csv -> key of the lab's bars
EXTRA_LAB = [{"key": "baba", "yahoo": "BABA", "cik": 1577552, "sector": "", "in_universe_from": "", "role": "lab40"}]
SPLIT_RATIOS = (1.5, 2, 3, 4, 5, 6, 7, 8, 10, 15, 20, 25, 50)
GAP_S, WAITS = 1.1, (5, 20)          # about one request a second; two retries with growing waits


# ---------------------------------------------------------------- shares
def shares():
    u = pd.read_csv(UNIV)
    u = u[u.in_universe | u.in_lab40].copy()
    u["role"] = np.where(u.in_lab40, "lab40", "universe")
    rows = u[["key", "yahoo", "cik", "sector", "in_universe_from", "role"]].to_dict("records")
    have = {r["key"] for r in rows}
    rows += [r for r in EXTRA_LAB if r["key"] not in have]
    out = pd.DataFrame(rows)
    if os.environ.get("PRICES_D1_ONLY") == "lab40":                       # selftest only
        out = out[out.role == "lab40"]
    return out


# ---------------------------------------------------------------- fetch (polite, cached, stripped)
def _ny_date(ts):
    return pd.to_datetime(np.asarray(ts, dtype=np.int64), unit="s", utc=True).tz_convert(NY).strftime("%Y-%m-%d")


def strip(raw):
    """Stripped reply (dict) or ('nodata', message). Only timestamps, quote arrays and events dated <= 2021-12-31 are
    kept; 'meta' is deleted without being read; adjclose is used once, in memory, for adjclose_check, then dropped."""
    j = json.loads(raw)
    ch = j.get("chart") or {}
    if ch.get("error") or not ch.get("result"):
        e = ch.get("error") or {}
        return ("nodata", f"{e.get('code', '')}: {str(e.get('description', ''))[:120]}")
    r = ch["result"][0]
    r.pop("meta", None)                                  # today's price and dates: never read, printed or stored
    ts = r.get("timestamp") or []
    if not ts:
        return ("nodata", "no time stamps in 2016-2021")
    d = _ny_date(ts)
    k = [i for i, t in enumerate(ts) if t < P2 and d[i] <= LAST_DAY]
    q = r["indicators"]["quote"][0]
    quote = {f: [q.get(f, [None] * len(ts))[i] for i in k] for f in ("open", "high", "low", "close", "volume")}
    ev = r.get("events") or {}
    divs = [{"date": v["date"], "amount": v["amount"]} for v in (ev.get("dividends") or {}).values()
            if v["date"] < P2 and _ny_date([v["date"]])[0] <= LAST_DAY]
    spl = [{"date": v["date"], "numerator": v.get("numerator"), "denominator": v.get("denominator"),
            "splitRatio": v.get("splitRatio")} for v in (ev.get("splits") or {}).values()
           if v["date"] < P2 and _ny_date([v["date"]])[0] <= LAST_DAY]
    chk = None
    adj = ((r["indicators"].get("adjclose") or [{}])[0]).get("adjclose")
    if adj and divs:                                     # in memory only: adjclose is not kept
        close = np.array([np.nan if x is None else x for x in q["close"]], float)
        a = np.array([np.nan if x is None else x for x in adj], float)
        rat = a / close
        pos = {t: i for i, t in enumerate(ts)}
        errs = []
        for dv in divs:
            i = pos.get(dv["date"])
            if i is None or i == 0 or not np.isfinite(rat[i]) or not np.isfinite(rat[i - 1]) or not close[i - 1]:
                continue
            step = rat[i - 1] / rat[i]                   # adjclose divides the earlier prices by (1 - div/prev close)
            errs.append(abs(step - (1 - dv["amount"] / close[i - 1])) * 1e4)
        if errs:
            chk = {"n_ex_dates": len(errs), "median_err_bp": float(np.median(errs)), "max_err_bp": float(np.max(errs))}
    return {"timestamp": [ts[i] for i in k], "quote": quote, "dividends": divs, "splits": spl,
            "adjclose_check": chk, "kept": "NY dates 2016-01-01..2021-12-31; meta and adjclose deleted"}


CACHE_KEYS = {"timestamp", "quote", "dividends", "splits", "adjclose_check", "kept"}


def cache_check(rec):
    """Problems of one stripped record (list of strings, empty = clean): only the stripped KEYS are allowed (no 'meta',
    no 'adjclose' series, no other indicator), and no time stamp or event at or after 2022-01-01. Keys are tested,
    never the text: the 'kept' note itself names what was deleted (review D3-2)."""
    bad = []
    if set(rec) - CACHE_KEYS:
        bad.append(f"extra keys {sorted(set(rec) - CACHE_KEYS)}")
    if set(rec.get("quote", {})) - {"open", "high", "low", "close", "volume"}:
        bad.append(f"extra quote fields {sorted(set(rec['quote']) - {'open', 'high', 'low', 'close', 'volume'})}")
    n = sum(t >= P2 for t in rec.get("timestamp", [])) + sum(d["date"] >= P2 for d in rec.get("dividends", []) +
                                                              rec.get("splits", []))
    if n:
        bad.append(f"{n} time stamps or events at or after 2022-01-01")
    return bad


def listing_cut(shares_traded):
    """Index label of the last row of a leading pre-listing block, or None: the latest zero-volume row such that more
    than half the rows up to it have zero volume (AMCR: Yahoo carries 669 zero-volume rows before the NYSE listing of
    June 2019; review D3-11). Isolated zero-volume days inside a share's life are not cut."""
    z = (pd.Series(shares_traded).fillna(0) <= 0).to_numpy()
    if not z.any():
        return None
    share = np.cumsum(z) / np.arange(1, len(z) + 1)
    ok = np.where(z & (share > 0.5))[0]
    return int(ok.max()) if len(ok) else None


class Refused(RuntimeError):
    pass


_state = {"last": 0.0, "refusals": 0}


def _request(url):
    """GET with a pause of GAP_S, two retries with growing waits on 429/5xx/network errors. A 429 or 403 counts as a
    refusal; two refusals in a row raise Refused (the caller stops using the host). 404 -> None."""
    for k in range(len(WAITS) + 1):
        wait = GAP_S - (time.time() - _state["last"])
        if wait > 0:
            time.sleep(wait)
        _state["last"] = time.time()
        try:
            b = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
            _state["refusals"] = 0
            return b
        except urllib.error.HTTPError as e:
            if e.code == 404:
                _state["refusals"] = 0
                try:
                    return e.read()                      # Yahoo sends a JSON error body with 404 (no data)
                except Exception:
                    return None
            if e.code in (403, 429):
                _state["refusals"] += 1
                if _state["refusals"] >= 2:
                    raise Refused(f"HTTP {e.code} twice in a row")
            elif e.code not in (500, 502, 503, 504):
                raise
            err = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            err = type(e).__name__
        if k < len(WAITS):
            time.sleep(WAITS[k])
    raise RuntimeError(f"failed after retries ({err})")


def _log():
    return json.load(open(LOG)) if os.path.exists(LOG) else {"nodata": {}, "errors": {}, "stopped": None}


def fetch(only=None):
    os.makedirs(RAW, exist_ok=True)
    lg = _log()
    lg["stopped"] = None
    syms = list(shares().yahoo) if not only else only
    todo = [s for s in syms if not os.path.exists(os.path.join(RAW, f"{s}.json")) and s not in lg["nodata"]]
    print(f"{len(syms)} symbols, {len(syms) - len(todo)} already cached or known absent, {len(todo)} to fetch")
    for n, s in enumerate(todo):
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?period1={P1}&period2={P2}"
               f"&interval=1d&events=div%2Csplits")
        try:
            raw = _request(url)
        except Refused as e:
            lg["stopped"] = f"{pd.Timestamp.now('UTC'):%Y-%m-%d %H:%M} UTC at {s} ({n} of {len(todo)} done): {e}"
            print("STOPPED, Yahoo refused twice in a row:", lg["stopped"])
            break
        except Exception as e:
            lg["errors"][s] = str(e)[:200]
            print(s, "error", str(e)[:120])
            continue
        out = strip(raw) if raw else ("nodata", "404 without body")
        if isinstance(out, tuple):
            lg["nodata"][s] = out[1]
            print(s, "no data:", out[1])
        else:
            lg["errors"].pop(s, None)
            tmp = os.path.join(RAW, f"{s}.json.part")
            json.dump(out, open(tmp, "w"))
            os.replace(tmp, os.path.join(RAW, f"{s}.json"))
            if n % 25 == 0:
                print(f"{n + 1}/{len(todo)} {s}: {len(out['timestamp'])} rows")
        json.dump(lg, open(LOG, "w"), indent=1)
    json.dump(lg, open(LOG, "w"), indent=1)


# ---------------------------------------------------------------- calendar (lab's hourly bars + rules before them)
def lab_h1():
    from kit import data
    out = {}
    for k in sorted(shares().query("role == 'lab40'").key):
        hk = H1_ALIAS.get(k, k)
        try:
            out[k] = data.load_bars(hk)
        except Exception as e:                           # noqa: BLE001
            print("hourly bars missing for", k, str(e)[:80])
    return out


def calendar(h1=None):
    """DataFrame indexed by NY date (str): minutes (390/210), source ('hourly'/'rules'), n_lab (shares with bars)."""
    from kit.data import _nyse_holidays
    h1 = lab_h1() if h1 is None else h1
    cnt, last = {}, {}
    for b in h1.values():
        ny = b.index.tz_convert(NY)
        late_min = pd.Series(np.where(ny.hour >= 13, b.volume.to_numpy(), 0.0), index=ny.strftime("%Y-%m-%d"))
        g = late_min.groupby(level=0).sum()            # minutes of quotes from 13:00 New York (180 on a full day)
        for day, hmax in g.items():
            cnt[day] = cnt.get(day, 0) + 1
            last.setdefault(day, []).append(hmax)
    nlab = len(h1)
    rows = {}
    for day in sorted(cnt):
        if day < HOURLY_FROM or day > LAST_DAY:
            continue
        if cnt[day] >= nlab / 2:
            rows[day] = {"minutes": 210 if np.median(last[day]) < 90 else 390, "source": "hourly", "n_lab": cnt[day]}
    hol = _nyse_holidays(2016, 2021)
    rule = {}
    for day in pd.bdate_range("2016-01-01", LAST_DAY):
        if day in hol or day == pd.Timestamp("2018-12-05"):          # 2018-12-05: national day of mourning
            continue
        rule[day.strftime("%Y-%m-%d")] = 390
    for h in ("2016-11-25", "2017-07-03", "2017-11-24", "2018-07-03", "2018-11-23", "2018-12-24", "2019-07-03",
              "2019-11-29", "2019-12-24", "2020-11-27", "2020-12-24", "2021-11-26"):
        rule[h] = 210
    for day, m in rule.items():
        if day < HOURLY_FROM:
            rows[day] = {"minutes": m, "source": "rules", "n_lab": 0}
    cal = pd.DataFrame.from_dict(rows, orient="index").sort_index()
    cal.attrs["rule"] = rule
    return cal


def session_open_utc(days):
    return pd.DatetimeIndex(pd.to_datetime(pd.Index(days)) + pd.Timedelta(hours=9, minutes=30)).tz_localize(NY) \
        .tz_convert("UTC")


# ---------------------------------------------------------------- build
def load_raw(sym):
    p = os.path.join(RAW, f"{sym}.json")
    return json.load(open(p)) if os.path.exists(p) else None


def frame(raw):
    """Daily frame indexed by NY date (str) with open high low close shares; rows with a missing price dropped."""
    q = raw["quote"]
    df = pd.DataFrame({"open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"],
                       "shares": q["volume"]}, index=_ny_date(raw["timestamp"]), dtype=float)
    df.index.name = "day"
    return df


def build(verbose=True):
    sh = shares()
    cal = calendar()
    os.makedirs(BARS, exist_ok=True)
    info, divs, spls = {}, [], []
    for r in sh.itertuples():
        raw = load_raw(r.yahoo)
        if raw is None:
            continue
        df = frame(raw)
        df = df[~df.index.duplicated(keep="first")]
        df = df.dropna(subset=["open", "high", "low", "close"])
        df = df[df.index.isin(cal.index)]                  # rows on non-sessions are counted by test(), not kept
        cut = listing_cut(df.shares.to_numpy())
        if cut is not None:                                # pre-listing rows (zero traded volume): not kept
            df = df.iloc[cut + 1:]
        out = df.copy()
        out["volume"] = cal.loc[out.index, "minutes"].astype(float).to_numpy()
        out.index = session_open_utc(out.index)
        out.index.name = "time"
        out = out[["open", "high", "low", "close", "volume", "shares"]].astype(float)
        assert out.index.max() < pd.Timestamp("2022-01-01", tz="UTC")
        out.to_parquet(os.path.join(BARS, f"{r.key}.parquet"))
        close_by_day = df.close
        for dv in raw["dividends"]:
            day = _ny_date([dv["date"]])[0]
            prev = close_by_day[close_by_day.index < day]
            pc = float(prev.iloc[-1]) if len(prev) else np.nan
            divs.append({"key": r.key, "ex_date": day, "amount": dv["amount"], "fraction": dv["amount"] / pc})
        for s in raw["splits"]:
            num, den = s.get("numerator"), s.get("denominator")
            ratio = (num / den) if num and den else np.nan
            # Yahoo lists spin-offs and other capital changes as 'splits' with ratios such as 1319:1000 (DHR 2019,
            # Envista); a usual split ratio (2:1, 3:2, 1:8 ...) is a split, anything else an adjustment (review D3-7)
            kind = "split" if np.isfinite(ratio) and near_split(ratio) and abs(near_split(ratio) / ratio - 1) < 1e-6 \
                else "spin_off_or_other_adjustment"
            spls.append({"key": r.key, "date": _ny_date([s["date"]])[0], "ratio": ratio, "kind": kind,
                         "yahoo_text": s.get("splitRatio")})
        rng = (df.high - df.low) / df.close * 1e4
        info[r.key] = {"yahoo": r.yahoo, "role": r.role, "first": df.index.min(), "last": df.index.max(),
                       "rows": int(len(df)), "median_price": round(float(df.close.median()), 4),
                       "median_range_bp": round(float(rng.median()), 1),
                       "median_dollar_volume": round(float((df.close * df.shares).median()), 0),
                       "adjclose_check": raw.get("adjclose_check")}
    pd.DataFrame(divs, columns=["key", "ex_date", "amount", "fraction"]).sort_values(["key", "ex_date"]) \
        .to_csv(os.path.join(D1, "dividends.csv"), index=False)
    pd.DataFrame(spls, columns=["key", "date", "ratio", "kind", "yahoo_text"]).sort_values(["key", "date"]) \
        .to_csv(os.path.join(D1, "splits.csv"), index=False)
    lg = _log()
    meta = {"made_by": "lab/explore/scout/prices_d1.py build", "source": "Yahoo chart API v8, interval 1d, read "
            f"{pd.Timestamp.now('UTC'):%Y-%m-%d}", "period": "NY dates 2016-01-01..2021-12-31",
            "index": "UTC session open (09:30 New York)", "volume": "minutes of the session (390 / 210)",
            "shares": "Yahoo traded volume (split-adjusted to today)",
            "prices": "Yahoo quote prices: split-adjusted for every split up to TODAY (levels carry splits after "
                      "2021), NOT dividend-adjusted", "not_on_yahoo": lg["nodata"],
            "levels_warning": "LEVELS are not the prices traded in 2016-2021: Yahoo divides every earlier price by "
                      "each later split and spin-off ratio, those after 2021 included (lab40 against the lab's hourly "
                      "bars: AMZN and GOOGL 0.05, NVDA, AVGO, NFLX 0.1, TSLA and WMT 0.333, GE 0.623, MRK 0.954, PFE "
                      "0.949; universe shares have no reference). Returns (ratios) are right. Anything per share is "
                      "not: a commission per share, a price filter in USD, a dividend in USD. A run expresses such "
                      "costs as a fraction of the price (see sources.md section 31, daily bars).",
            "dividends": "dividends.csv 'amount' is in Yahoo's scaled USD (divided by the same later ratios as the "
                      "prices: MMM 2019-02-14 shows 1.204 for the 1.44 paid); use 'fraction' (amount / previous "
                      "close, both scaled alike) only",
            "splits": "splits.csv kind = split (usual ratio) or spin_off_or_other_adjustment (Yahoo's price "
                      "adjustment for a spin-off, e.g. DHR 1319:1000, DD 1487:1000, GE 104:100, MRK 1048:1000)",
            "pre_listing": "rows before a leading block of zero-volume rows ends are dropped (listing_cut: AMCR before "
                      "2019-06-11)", "fetch_errors": lg["errors"],
            "fetch_stopped": lg["stopped"], "n_shares": len(info)}
    json.dump({"meta": meta, "shares": info}, open(os.path.join(D1, "info.json"), "w"), indent=1)
    liq = []
    for r in sh.itertuples():
        raw = load_raw(r.yahoo)
        if raw is None:
            continue
        df = frame(raw).dropna(subset=["close"])
        df = df[df.index.isin(cal.index)]
        cut = listing_cut(df.shares.to_numpy())
        if cut is not None:
            df = df.iloc[cut + 1:].copy()
        df["year"] = df.index.str[:4]
        df["rng"] = (df.high - df.low) / df.close * 1e4
        df["dv"] = df.close * df.shares
        g = df.groupby("year")
        y = pd.DataFrame({"sessions": g.size(), "median_price": g.close.median(), "median_range_bp": g.rng.median(),
                          "median_dollar_volume": g.dv.median()}).reset_index()
        y.insert(0, "role", r.role)
        y.insert(0, "key", r.key)
        liq.append(y)
    pd.concat(liq).round(4).to_csv(os.path.join(D1, "liquidity_by_year.csv"), index=False)
    if verbose:
        print(f"built {len(info)} shares; dividends {len(divs)}, splits {len(spls)}")


# ---------------------------------------------------------------- test
def near_split(x):
    """Usual ratio r if x (a price ratio, previous close / today) is within 3 % of r or 1/r, else None."""
    for r in SPLIT_RATIOS:
        for t in (r, 1 / r):
            if abs(x / t - 1) < 0.03:
                return t
    return None


def test(verbose=True):
    sh = shares()
    h1 = lab_h1()
    cal = calendar(h1)
    res = {}
    fails = []

    def ok(name, cond, msg):
        res[name] = msg
        print(("PASS " if cond else "FLAG ") + name + ": " + msg)
        if not cond:
            fails.append(name)

    # calendar: rules vs hourly on the overlap
    rule = cal.attrs["rule"]
    hdays = cal[cal.source == "hourly"]
    ov = {d for d in rule if d >= HOURLY_FROM}
    only_rule, only_h1 = sorted(ov - set(hdays.index)), sorted(set(hdays.index) - ov)
    half_dis = sorted(d for d in set(hdays.index) & ov if rule[d] != hdays.loc[d, "minutes"])
    ok("calendar", not only_rule and not only_h1 and not half_dis,
       f"{len(cal)} sessions 2016-2021 ({(cal.source == 'rules').sum()} from rules before {HOURLY_FROM}, "
       f"{len(hdays)} from the lab's hourly bars), {int((cal.minutes == 210).sum())} half days; on the overlap the "
       f"rule calendar and the hourly one differ on {len(only_rule)} + {len(only_h1)} days {only_rule[:5]} "
       f"{only_h1[:5]}, half-day disagreements {half_dis[:5]}")
    partial = hdays[hdays.n_lab < len(h1)]
    res["calendar_partial_days"] = {d: int(n) for d, n in partial.n_lab.items()}

    nodata = _log()["nodata"]
    present, missing_yahoo = [], []
    for r in sh.itertuples():
        (present if load_raw(r.yahoo) is not None else missing_yahoo).append(r)
    ok("coverage", len(missing_yahoo) == 0,
       f"{len(present)} of {len(sh)} shares have a cached reply ({sum(r.role == 'universe' for r in present)} "
       f"universe, {sum(r.role == 'lab40' for r in present)} lab40); missing: "
       f"{[(r.yahoo, nodata.get(r.yahoo, 'not fetched')) for r in missing_yahoo]}")

    tot = {"rows": 0, "dup": 0, "nonsession": 0, "missing": 0, "nullprice": 0, "hl": 0, "nonpos": 0, "zerovol": 0,
           "split_like": 0}
    late, split_rows, miss_rows, hl_rows, zv, prelist = [], [], [], [], [], []
    spl = pd.read_csv(os.path.join(D1, "splits.csv")) if os.path.exists(os.path.join(D1, "splits.csv")) else None
    caldays = cal.index.to_numpy()
    for r in present:
        raw = load_raw(r.yahoo)
        df = frame(raw)
        tot["dup"] += int(df.index.duplicated().sum())
        nn = df[df[["open", "high", "low", "close"]].isna().any(axis=1)]
        tot["nullprice"] += len(nn)
        df = df[~df.index.duplicated()].dropna(subset=["open", "high", "low", "close"])
        ns = df[~df.index.isin(cal.index)]
        tot["nonsession"] += len(ns)
        df = df[df.index.isin(cal.index)]
        tot["rows"] += len(df)
        life = caldays[(caldays >= df.index.min()) & (caldays <= df.index.max())]
        mi = sorted(set(life) - set(df.index))
        tot["missing"] += len(mi)
        if mi:
            miss_rows.append((r.key, len(mi), mi[:3]))
        bad = df[(df.high < df[["open", "close"]].max(axis=1) - 1e-9) | (df.low > df[["open", "close"]].min(axis=1) + 1e-9)]
        tot["hl"] += len(bad)
        if len(bad):
            hl_rows.append((r.key, len(bad)))
        tot["nonpos"] += int((df[["open", "high", "low", "close"]] <= 0).any(axis=1).sum())
        cut = listing_cut(df.shares.to_numpy())
        if cut is not None:                                  # pre-listing block: build drops it
            prelist.append((r.key, cut + 1, df.index[cut + 1] if cut + 1 < len(df) else None))
            df = df.iloc[cut + 1:]
        zm = (df.shares.fillna(0) <= 0).to_numpy()
        z = int(zm.sum())
        tot["zerovol"] += z
        if z:
            runs = np.diff(np.flatnonzero(np.diff(np.r_[0, zm.astype(int), 0])))[::2]
            zv.append((r.key, z, int(runs.max()), str(df.index[zm][0]), str(df.index[zm][-1])))
        if df.index.min() > "2017-01-01":
            late.append((r.key, df.index.min()))
        prev = df.close.shift(1)
        vol_x = df.shares / df.shares.shift(1).rolling(20, min_periods=10).median()   # traded shares / prior 20 median
        after = df.shares.shift(-5).rolling(20, min_periods=10).median().shift(-15) / \
            df.shares.shift(1).rolling(20, min_periods=10).median()                # 20 sessions from s+5, against before
        for col in ("open", "close"):
            x = (prev / df[col]).dropna()
            for day, v in x.items():
                t = near_split(v)
                if t is None:
                    continue
                listed = spl is not None and ((spl.key == r.key) & (spl.date == day)).any()
                split_rows.append({"key": r.key, "day": day, "col": col, "prev_close_over": round(v, 4),
                                   "near": round(t, 4), "listed_split_that_day": bool(listed),
                                   "volume_x_day": round(float(vol_x.get(day, np.nan)), 2),
                                   "volume_x_after": round(float(after.get(day, np.nan)), 2)})
    tot["split_like"] = len({(x["key"], x["day"]) for x in split_rows})
    ok("duplicates", tot["dup"] == 0, f"{tot['dup']} duplicate dates in {len(present)} replies")
    ok("sessions", tot["nonsession"] == 0 and tot["missing"] == 0,
       f"{tot['rows']} rows on sessions; {tot['nonsession']} rows on days that are not NYSE sessions (dropped); "
       f"{tot['missing']} sessions missing inside a share's life in {len(miss_rows)} shares {miss_rows[:8]}")
    ok("null_prices", tot["nullprice"] == 0, f"{tot['nullprice']} rows with a missing price (dropped)")
    ok("high_low", tot["hl"] == 0, f"{tot['hl']} rows with high < max(open, close) or low > min(open, close) "
       f"in {len(hl_rows)} shares {hl_rows[:8]}")
    ok("positive", tot["nonpos"] == 0, f"{tot['nonpos']} rows with a zero or negative price")
    long_runs = [x for x in zv if x[2] >= 3 and x[4] >= "2017-01-01"]
    print(f"INFO pre_listing: leading zero-volume blocks dropped by build: {prelist}")
    res["pre_listing"] = prelist
    ok("zero_volume", not long_runs,
       f"after the pre-listing blocks, {tot['zerovol']} rows with zero traded volume in {len(zv)} shares "
       f"(key, rows, longest run, first, last) {zv}; runs of 3+ sessions from 2017: {long_runs} (prices are present on "
       "these rows; volume is not used by the event rules)")
    res["late_start"] = late
    print(f"INFO late_start: {len(late)} shares start after 2017-01-01: {late}")
    res["split_like_moves"] = split_rows
    unexpl = [x for x in split_rows if not _split_like_explained(x)]
    ok("split_like", not unexpl,
       f"{tot['split_like']} share-days with an overnight or close-to-close move within 3 % of a usual split ratio, "
       f"{sum(1 for x in split_rows if x['key'] in EXPLAINED.get(x['day'], ()))} rows explained by hand (EXPLAINED), "
       f"the rest by their volume (a real move: traded shares >= 3 x the prior 20-session median that day; an "
       f"unadjusted split only rescales them by its ratio; volume_x_after = later volume / earlier, for reading); "
       f"unexplained: {unexpl}")

    # bars written vs raw
    nb = len([f for f in os.listdir(BARS) if f.endswith(".parquet")]) if os.path.isdir(BARS) else 0
    if nb == 0 or not os.path.exists(os.path.join(D1, "splits.csv")):
        ok("bars_written", False, f"NO BARS: {nb} bar files, splits.csv "
           f"{'present' if os.path.exists(os.path.join(D1, 'splits.csv')) else 'missing'} in {D1}: run `build` first; "
           "the adjustment checks and the comparison with the lab's hourly bars cannot run")
        json.dump(res, open(os.path.join(D1, "test_result.json"), "w"), indent=1, default=str)
        print("flags:", fails)
        return res
    late_ts = 0
    for f in os.listdir(BARS) if nb else []:
        b = pd.read_parquet(os.path.join(BARS, f), columns=["close"])
        late_ts += int((b.index >= pd.Timestamp("2022-01-01", tz="UTC")).sum())
    ok("bars_written", nb == len(present) and late_ts == 0, f"{nb} bar files, {late_ts} rows dated 2022 or later")
    raw_late = 0
    for r in present:
        raw = load_raw(r.yahoo)
        bad = cache_check(raw)
        if bad:
            raw_late += 1
            print("   cache problem", r.yahoo, bad)
    ok("cache_clean", raw_late == 0, f"cache: {raw_late} of {len(present)} cached files with a problem (keys other "
       "than the stripped ones, e.g. 'meta' or an adjclose series, or a time stamp / event at or after 2022-01-01)")

    res.update(adjustment_checks(h1, present, cal))
    res.update(lab_compare(h1, present, ok))
    json.dump(res, open(os.path.join(D1, "test_result.json"), "w"), indent=1, default=str)
    print("flags:", fails if fails else "none")
    return res


# Split-like moves read one by one (see test_result.json, 'split_like_moves'): day -> keys whose move is a real
# price move (checked against news, the hourly bars of the lab, or the shape of the bars around it). Filled after
# the first test run.
EXPLAINED = {
    # read one by one on 2026-11-18 (review D3-11): real moves, each with a one-day volume spike and no lasting
    # change of the traded shares; the volume rule (_split_like_explained) covers them too, the list documents them
    "2016-02-08": ("wmb",),            # Williams: ETE merger doubts, -35 % on 5 x volume
    "2016-04-22": ("amd",),            # AMD: Q1 results and the China joint venture, +52 % on 10 x volume
    "2017-09-28": ("dxcm",),           # DexCom: FDA approval of Abbott's Libre, -33 % on 35 x volume
    "2018-05-11": ("gen",),            # Symantec (now Gen Digital): audit committee inquiry, -33 % on 15 x volume
    "2020-03-09": ("apa", "dvn", "eog"),  # oil price war, COVID crash
    "2020-03-12": ("rcl",), "2020-03-16": ("apa", "mgm"), "2020-04-01": ("ccl",),   # COVID crash
}


def _split_like_explained(x):
    if x["key"] in EXPLAINED.get(x["day"], ()):
        return True
    # a news day trades many times the usual volume; an unadjusted split only rescales the traded shares by its ratio
    return not x["listed_split_that_day"] and np.isfinite(x["volume_x_day"]) and x["volume_x_day"] >= 3


def adjustment_checks(h1, present, cal):
    """Split adjustment: no split-sized jump on the ex-date of each split Yahoo lists (to 2021); the levels against
    the lab's hourly bars (the factor = later splits). Dividends: on the ex-dates of the largest dividends the quote
    close drops by about the dividend; the adjclose step (kept from fetch time) matches the dividend."""
    out = {}
    spl = pd.read_csv(os.path.join(D1, "splits.csv"))
    rows = []
    byk = {r.key: r.yahoo for r in present}
    for s in spl.itertuples():
        df = frame(load_raw(byk[s.key])).dropna(subset=["close"])
        if s.date not in df.index:
            continue
        i = df.index.get_loc(s.date)
        if i == 0:
            continue
        rows.append({"key": s.key, "date": s.date, "ratio": s.ratio,
                     "prev_close_over_open": round(df.close.iloc[i - 1] / df.open.iloc[i], 4)})
    unadj = [x for x in rows if near_split(x["prev_close_over_open"]) and abs(x["prev_close_over_open"] - 1) > 0.25]
    print(f"{'PASS' if not unadj else 'FLAG'} adjustment_splits: {len(rows)} splits listed by Yahoo in 2016-2021 "
          f"with bars on both sides; previous close / open of the ex-date: median "
          f"{np.median([x['prev_close_over_open'] for x in rows]) if rows else float('nan'):.4f}, "
          f"{len(unadj)} look unadjusted {unadj[:5]}")
    for k in ("aapl", "tsla", "nvda", "ge"):
        out[f"split_{k}"] = [x for x in rows if x["key"] == k]
        print("   ", k, out[f"split_{k}"])
    out["adjustment_splits"] = rows
    dv = pd.read_csv(os.path.join(D1, "dividends.csv"))
    big = dv.dropna().sort_values("fraction", ascending=False).head(10)
    drops = []
    for d in big.itertuples():
        df = frame(load_raw(byk[d.key])).dropna(subset=["close"])
        i = df.index.get_loc(d.ex_date) if d.ex_date in df.index else None
        if not i:
            continue
        drops.append({"key": d.key, "ex_date": d.ex_date, "fraction": round(d.fraction, 4),
                      "open_over_prev_close_minus_1": round(df.open.iloc[i] / df.close.iloc[i - 1] - 1, 4)})
    print("INFO adjustment_dividends: the 10 largest dividends (fraction of the previous close) and the opening gap "
          "of the ex-date (unadjusted close: the gap is about -fraction):")
    for x in drops:
        print("   ", x)
    out["adjustment_dividends"] = drops
    chk = [load_raw(r.yahoo).get("adjclose_check") for r in present]
    chk = [c for c in chk if c]
    if chk:
        msg = (f"{len(chk)} shares with dividends: adjclose step on the ex-date vs 1 - dividend / previous close: "
               f"median of medians {np.median([c['median_err_bp'] for c in chk]):.2f} bp, worst "
               f"{max(c['max_err_bp'] for c in chk):.1f} bp ({sum(c['n_ex_dates'] for c in chk)} ex-dates)")
        print("INFO adjclose_check:", msg)
        out["adjclose_check"] = msg
    return out


def lab_compare(h1, present, ok):
    """Daily close vs last hourly close of the same NY day, daily open vs first hourly bar's open, for the lab's 40.
    The level factor (Yahoo / hourly, median) is reported: a factor of r means a split of r:1 after 2021."""
    out = {}
    rows = []
    byk = {r.key: r for r in present}
    allc, allo = [], []
    for k, b in sorted(h1.items()):
        if k not in byk:
            continue
        df = frame(load_raw(byk[k].yahoo)).dropna(subset=["close"])
        ny = b.index.tz_convert(NY)
        day = ny.strftime("%Y-%m-%d")
        g = b.groupby(day)
        hd = pd.DataFrame({"o": g.open.first(), "c": g.close.last()})
        j = df.join(hd, how="inner")
        fac = float(np.median(j.close / j.c))
        dc = (j.close / fac / j.c - 1) * 1e4
        do = (j.open / fac / j.o - 1) * 1e4
        # date shift test: is the daily close closer to the hourly close of the same day than of the day before/after?
        sh = {}
        for lag in (-1, 0, 1):
            sh[lag] = float(np.nanmedian(np.abs(j.close / fac / hd.c.shift(lag).reindex(j.index) - 1)) * 1e4)
        allc.append(dc)
        allo.append(do)
        rows.append({"key": k, "days": len(j), "level_factor": round(fac, 4),
                     "close_med_abs_bp": round(float(dc.abs().median()), 1), "close_worst_bp": round(float(dc.abs().max()), 1),
                     "close_worst_day": dc.abs().idxmax(), "close_days_over_100bp": int((dc.abs() > 100).sum()),
                     "open_med_abs_bp": round(float(do.abs().median()), 1), "open_worst_bp": round(float(do.abs().max()), 1),
                     "open_worst_day": do.abs().idxmax(), "open_days_over_100bp": int((do.abs() > 100).sum()),
                     "lag_med_abs_bp": {str(a): round(v, 1) for a, v in sh.items()},
                     "daily_minus_hourly_days": len(df) - len(j)})
    t = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print(t.drop(columns=["lag_med_abs_bp"]).to_string(index=False))
    c, o = pd.concat(allc).abs(), pd.concat(allo).abs()
    best_lag0 = all(min(r["lag_med_abs_bp"], key=r["lag_med_abs_bp"].get) == "0" for r in rows)
    ok("lab40_close", c.median() < 10 and best_lag0,
       f"{len(rows)} shares, {len(c)} days: |daily close / last hourly close - 1| median {c.median():.1f} bp, "
       f"95th pct {c.quantile(.95):.1f} bp, worst {c.max():.0f} bp, {int((c > 100).sum())} days over 100 bp; the same-day "
       f"match beats the day before and after for {'every' if best_lag0 else 'NOT every'} share")
    ok("lab40_open", o.median() < 25,
       f"|daily open / first hourly open - 1| median {o.median():.1f} bp, 95th pct {o.quantile(.95):.1f} bp, worst "
       f"{o.max():.0f} bp, {int((o > 100).sum())} days over 100 bp")
    nonunit = t[(t.level_factor - 1).abs() > 0.01][["key", "level_factor"]].to_dict("records")
    print("INFO level factors other than 1 (Yahoo level / lab level = 1 / later split ratio):", nonunit)
    out["lab40_compare"] = rows
    out["level_factors"] = nonunit
    return out


# ---------------------------------------------------------------- report
def report():
    inf = json.load(open(os.path.join(D1, "info.json")))
    s = pd.DataFrame(inf["shares"]).T
    u = s[s.role == "universe"]
    print(f"shares with bars: {len(s)} ({len(u)} universe, {len(s) - len(u)} lab40)")
    for col in ("median_price", "median_range_bp", "median_dollar_volume"):
        v = u[col].astype(float)
        print(f"universe {col}: 10 % {v.quantile(.1):,.1f}  median {v.median():,.1f}  90 % {v.quantile(.9):,.1f}")
    print(f"universe shares with a median price (2016-2021, Yahoo levels) under 30 USD: {(u.median_price.astype(float) < 30).sum()}"
          f" of {len(u)} ({(u.median_price.astype(float) < 30).mean():.1%}); Yahoo levels are divided by every later "
          "split and spin-off (info.json meta.levels_warning), so this count is an upper bound for the prices traded")
    ly = pd.read_csv(os.path.join(D1, "liquidity_by_year.csv"))
    lu = ly[ly.role == "universe"]
    g = lu.groupby("year")
    print(pd.DataFrame({"shares": g.size(), "median_price": g.median_price.median(),
                        "share_under_30": g.median_price.apply(lambda x: (x < 30).mean()).round(3),
                        "median_range_bp": g.median_range_bp.median(),
                        "median_dollar_volume_musd": (g.median_dollar_volume.median() / 1e6).round(1),
                        "dv_10pct_musd": (g.median_dollar_volume.quantile(.1) / 1e6).round(1)}).to_string())
    print("not on Yahoo:", inf["meta"]["not_on_yahoo"], "errors:", inf["meta"]["fetch_errors"],
          "stopped:", inf["meta"]["fetch_stopped"])


# ---------------------------------------------------------------- selftest (no network; synthetic replies)
def selftest():
    """(1) strip() on a crafted reply: meta, adjclose and everything dated 2022 must go, adjclose_check must be right.
    (2) Synthetic stripped replies made from the lab's hourly bars (daily OHLC per New York day) for the lab's 40,
    written to ~/explore_data/d1_selftest (deleted at the end), with defects planted: a missing session, a duplicate
    date, a high below the close, an unadjusted 2:1 jump, a level factor 1/20 (a later split), a zero volume, a
    date shifted by one day; then build and test run there and must flag each one."""
    import shutil, subprocess
    day = lambda d: int(session_open_utc([d])[0].timestamp())        # noqa: E731
    ts = [day("2021-12-29"), day("2021-12-30"), day("2021-12-31"), day("2022-01-03")]
    rep = {"chart": {"error": None, "result": [{
        "meta": {"regularMarketPrice": 999.0, "currentTradingPeriod": "today"}, "timestamp": ts,
        "events": {"dividends": {str(ts[1]): {"amount": 1.0, "date": ts[1]}, str(ts[3]): {"amount": 1.0, "date": ts[3]}},
                   "splits": {str(ts[3]): {"date": ts[3], "numerator": 2, "denominator": 1, "splitRatio": "2:1"}}},
        "indicators": {"quote": [{"open": [100, 101, 100, 50], "high": [101, 102, 101, 51], "low": [99, 100, 99, 49],
                                  "close": [100, 100, 99, 50], "volume": [10, 11, 12, 13]}],
                       "adjclose": [{"adjclose": [99.0, 100, 99, 50]}]}}]}}
    st = strip(json.dumps(rep).encode())
    txt = json.dumps(st)
    assert "meta" not in st and "999" not in txt and "today" not in txt, "meta kept"
    assert "adjclose\"" not in txt and '"adjclose":' not in txt.replace('"adjclose_check":', ""), "adjclose kept"
    assert st["timestamp"] == ts[:3] and len(st["quote"]["close"]) == 3, "2022 row kept"
    assert len(st["dividends"]) == 1 and not st["splits"], "2022 event kept"
    assert st["adjclose_check"]["max_err_bp"] < 1e-6, st["adjclose_check"]        # 99/100 step = 1 - 1/100
    assert strip(json.dumps({"chart": {"result": None, "error": {"code": "Not Found", "description": "x"}}}).encode())[0] == "nodata"
    # review D3-2: the stripped record must pass the same cache check `test` applies to the real cache (its 'kept'
    # note names 'meta' and 'adjclose'), and the check must catch a record that still holds them
    assert cache_check(st) == [], cache_check(st)
    assert "meta" in st["kept"] and "adjclose" in st["kept"]
    leak = dict(st, meta={"regularMarketPrice": 1.0})
    assert any("meta" in b for b in cache_check(leak)), "meta not caught"
    leak = dict(st, quote=dict(st["quote"], adjclose=[1.0, 1.0, 1.0]))
    assert any("adjclose" in b for b in cache_check(leak)), "adjclose not caught"
    leak = dict(st, timestamp=st["timestamp"] + [P2])
    assert any("2022" in b for b in cache_check(leak)), "2022 stamp not caught"
    assert listing_cut([0, 0, 0, 5, 0, 7, 8, 9, 10, 11, 0, 12]) == 4 and listing_cut([5, 0, 6, 7]) is None
    print("PASS strip: meta, adjclose, 2022 rows and 2022 events removed; adjclose_check exact; error reply = no data;"
          " cache_check passes the stripped record and catches meta, adjclose and a 2022 stamp; listing_cut")

    out = os.path.expanduser("~/explore_data/d1_selftest")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(os.path.join(out, "raw_yahoo"))
    sh = shares().query("role == 'lab40'")
    h1 = lab_h1()
    plant = {"aapl": "missing 2019-03-05", "msft": "duplicate 2018-06-01", "jpm": "high below close 2020-02-03",
             "intc": "unadjusted 2:1 before 2019-07-01", "amzn": "level x 1/20", "ko": "", "xom": "zero volume 2017-05-02",
             "nke": "dates shifted one day", "pfe": "zero volume on the first 100 sessions (pre-listing)"}
    for r in sh.itertuples():
        if r.key not in h1:
            continue
        b = h1[r.key]
        ny = b.index.tz_convert(NY).strftime("%Y-%m-%d")
        g = b.groupby(ny)
        d = pd.DataFrame({"open": g.open.first(), "high": g.high.max(), "low": g.low.min(), "close": g.close.last(),
                          "volume": g.volume.sum() * 1000.0})
        if r.key == "amzn":
            d[["open", "high", "low", "close"]] /= 20
        if r.key == "aapl":
            d = d.drop("2019-03-05")
        if r.key == "msft":
            d = pd.concat([d, d.loc[["2018-06-01"]]]).sort_index(kind="mergesort")
        if r.key == "jpm":
            d.loc["2020-02-03", "high"] = d.loc["2020-02-03", "close"] * 0.99
        if r.key == "intc":
            d.loc[d.index < "2019-07-01", ["open", "high", "low", "close"]] *= 2
        if r.key == "xom":
            d.loc["2017-05-02", "volume"] = 0
        if r.key == "pfe":
            d.iloc[:100, d.columns.get_loc("volume")] = 0.0
        idx = list(d.index)
        if r.key == "nke":
            idx = idx[1:] + [idx[-1]]
            d = d.iloc[:-1]
            idx = idx[:-1]
        stamps = [int(t.timestamp()) for t in session_open_utc(idx)]
        divs = [{"date": stamps[500], "amount": float(d.close.iloc[499] * 0.02)}] if r.key == "xom" else []
        rec = {"timestamp": stamps, "quote": {f: [None if pd.isna(v) else float(v) for v in d[f]]
                                              for f in ("open", "high", "low", "close", "volume")},
               "dividends": divs, "splits": [], "adjclose_check": None, "kept": "SYNTHETIC selftest reply"}
        json.dump(rec, open(os.path.join(out, "raw_yahoo", f"{r.yahoo}.json"), "w"))
    env = dict(os.environ, PRICES_D1_OUT=out, PRICES_D1_ONLY="lab40", PYTHONDONTWRITEBYTECODE="1")
    me = os.path.abspath(__file__)
    no_bars = None
    for cmd in ("test", "build", "test"):          # review D3-2: `test` before any bar exists must report, not crash
        p = subprocess.run([sys.executable, "-B", me, cmd], env=env, capture_output=True, text=True)
        if p.returncode:
            print(p.stdout[-3000:], p.stderr[-3000:])
            raise SystemExit(f"selftest: {cmd} failed")
        if no_bars is None:
            no_bars = json.load(open(os.path.join(out, "test_result.json"))).get("bars_written", "")
    res = json.load(open(os.path.join(out, "test_result.json")))
    got = {
        "missing session (aapl)": "aapl" in res["sessions"],
        "duplicate (msft)": res["duplicates"].startswith("1 duplicate"),
        "high below close (jpm)": "('jpm', 1)" in res["high_low"],
        "unadjusted split (intc), not explained": any(x["key"] == "intc" and x["day"] == "2019-07-01"
                                                      and not _split_like_explained(x) for x in res["split_like_moves"]),
        "test before build reports NO BARS without crashing": no_bars.startswith("NO BARS"),
        "level factor 1/20 (amzn)": any(x["key"] == "amzn" and abs(x["level_factor"] - 0.05) < 1e-3 for x in res["level_factors"]),
        "zero volume (xom)": "('xom', 1, 1, '2017-05-02', '2017-05-02')" in res["zero_volume"],
        "pre-listing block dropped (pfe)": [x for x in res["pre_listing"] if x[0] == "pfe"][0][1] == 100
                                           and len(pd.read_parquet(os.path.join(out, "bars", "pfe.parquet")))
                                           == len(json.load(open(os.path.join(out, "raw_yahoo", "PFE.json")))["timestamp"]) - 100,
        "date shift (nke)": [x for x in res["lab40_compare"] if x["key"] == "nke"][0]["lag_med_abs_bp"]["0"]
                            > min([x for x in res["lab40_compare"] if x["key"] == "nke"][0]["lag_med_abs_bp"].values()),
        "dividend fraction (xom)": abs(pd.read_csv(os.path.join(out, "dividends.csv")).fraction.iloc[0] - 0.02) < 1e-9,
    }
    clean = [x for x in res["lab40_compare"] if x["key"] not in plant]
    got["clean shares match exactly"] = all(x["close_worst_bp"] < 1e-6 and x["open_worst_bp"] < 1e-6 for x in clean)
    b = pd.read_parquet(os.path.join(out, "bars", "cvx.parquet"))
    t0 = b.index[b.index.tz_convert(NY).strftime("%Y-%m-%d") == "2019-07-03"]
    got["index = 09:30 NY in UTC, half day 210 min"] = (str(t0[0]) == "2019-07-03 13:30:00+00:00"
                                                        and b.loc[t0[0], "volume"] == 210)
    t1 = b.index[b.index.tz_convert(NY).strftime("%Y-%m-%d") == "2019-01-03"]
    got["winter open 14:30 UTC, 390 min"] = str(t1[0]) == "2019-01-03 14:30:00+00:00" and b.loc[t1[0], "volume"] == 390
    for k, v in got.items():
        print(("PASS " if v else "FAIL ") + "selftest " + k)
    if not all(got.values()):
        raise SystemExit(f"selftest failed (files kept in {out})")
    if not os.environ.get("PRICES_D1_KEEP"):
        shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "fetch":
        fetch(sys.argv[2:] or None)
    else:
        {"build": build, "test": test, "report": report, "selftest": selftest}[cmd]()
