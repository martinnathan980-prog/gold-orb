"""Point-in-time earnings-release calendar of the lab's 40 US shares, from SEC EDGAR (8-K item 2.02).

Usage
    PYTHONDONTWRITEBYTECODE=1 python3 -B earnings_edgar.py fetch    # download (cached) the EDGAR filings lists
    PYTHONDONTWRITEBYTECODE=1 python3 -B earnings_edgar.py build    # build ~/explore_data/earnings/calendar*.csv
    PYTHONDONTWRITEBYTECODE=1 python3 -B earnings_edgar.py test     # self-checks on the cache (no network)
    PYTHONDONTWRITEBYTECODE=1 python3 -B earnings_edgar.py refilter # re-apply the 2015-06..2021-12 filter to the cache
    from earnings_edgar import calendar; cal = calendar(end="2021-12-31")   # quarterly results only

What a run reads: `calendar(end, quarterly_only=True)`: one row per release with
    ticker, accepted_utc (tz-aware UTC: the time EDGAR accepted the 8-K = the safe 'known at'),
    accepted_et (same instant, New York time), reaction_session (date of the first regular 09:30-16:00 New York
    session that STARTS after accepted_utc), when (before_open / in_session / after_close, New York clock),
    quarter_flag (results / before_results / after_results / amendment), form, items, accession, filing_date,
    event_date (the 8-K's own 'date of report'), period_end, lag_days, usual_lag, note, cik.
    Rows with when == 'in_session' (Citigroup x4) and all Alibaba rows (6-K filed hours after a pre-market release)
    have a reaction_session one session LATE by construction: see sources.md section 30.

Source facts (checked 2026-11-18, see sources.md section 'Earnings releases'):
- https://data.sec.gov/submissions/CIK##########.json answers the plain client name "research-client/1.0";
  www.sec.gov (company_tickers.json, Archives) refuses it (403 'Request Rate Threshold Exceeded' page), so the CIKs
  are written here by hand and checked against the name EDGAR returns.
- In the submissions JSON, acceptanceDateTime is real UTC ("2021-10-28T20:30:23.000Z" for Apple's 8-K of 2021-10-28,
  i.e. 16:30:23 New York EDT; "2021-01-27T21:30:35.000Z" in winter = 16:30 EST). The SAME instant is printed in
  Eastern local time without a zone in the filing's own header (ACCEPTANCE-DATETIME: 20211028163023) and on the
  EDGAR web pages: never mix the two. filingDate is the Eastern business date, and an 8-K accepted after 17:30
  New York carries the NEXT business day as filingDate: use the acceptance time, never filingDate.
- Every reply is filtered before it is written: only filings dated 2015-06-01..2021-12-31 are kept in the cache.
"""
import json, os, sys, time, urllib.request, urllib.error
import pandas as pd

UA = {"User-Agent": "research-client/1.0", "Accept-Encoding": "identity"}
CACHE = os.path.expanduser("~/explore_data/earnings")
RAW = os.path.join(CACHE, "raw")
CUT = "2021-12-31"            # nothing filed after this is kept
KEEP_FROM = "2015-06-01"      # filings older than this are dropped (10-Q periods needed from mid-2016)
START = "2016-10-01"          # first release of the calendar
NY = "America/New_York"
INFO = os.path.expanduser("~/explore_data/h1/info.json")
KIT = {"xauusd", "xagusd", "us100", "us500", "us30", "ger40", "eurusd", "gbpusd", "usdjpy", "audusd", "usdcad",
       "usdchf", "nzdusd", "eurjpy", "oil"}

# lab key -> list of (CIK, expected words in EDGAR's name). Several CIKs = predecessor registrants, merged.
CIKS = {
    "aapl": [(320193, "apple")], "adbe": [(796343, "adobe")], "amd": [(2488, "micro devices")],
    "amzn": [(1018724, "amazon")],
    "avgo": [(1730168, "broadcom"), (1649338, "broadcom")],          # Broadcom Inc (2018-) ; Broadcom Ltd (2016-2018)
    "ba": [(12927, "boeing")], "baba": [(1577552, "alibaba")], "bac": [(70858, "bank of america")],
    "c": [(831001, "citigroup")], "cat": [(18230, "caterpillar")], "crm": [(1108524, "salesforce")],
    "csco": [(858877, "cisco")], "cvx": [(93410, "chevron")],
    "dis": [(1744489, "disney"), (1001039, "")],                       # new Disney (2019-03-) ; old Disney (TWDC Enterprises 18)
    "fb": [(1326801, "meta")], "ge": [(40545, "general electric")], "googl": [(1652044, "alphabet")],
    "gs": [(886982, "goldman")], "hd": [(354950, "home depot")], "intc": [(50863, "intel")],
    "jnj": [(200406, "johnson")], "jpm": [(19617, "jpmorgan")], "ma": [(1141391, "mastercard")],
    "mcd": [(63908, "mcdonald")], "mrk": [(310158, "merck")], "msft": [(789019, "microsoft")],
    "mu": [(723125, "micron")], "nflx": [(1065280, "netflix")], "nke": [(320187, "nike")],
    "nvda": [(1045810, "nvidia")], "orcl": [(1341439, "oracle")], "pfe": [(78003, "pfizer")],
    "pypl": [(1633917, "paypal")], "qcom": [(804328, "qualcomm")], "tsla": [(1318605, "tesla")],
    "unh": [(731766, "unitedhealth")], "v": [(1403161, "visa")], "wfc": [(72971, "wells fargo")],
    "wmt": [(104169, "walmart")], "xom": [(34088, "exxon")],
}
COLS = ["accessionNumber", "filingDate", "reportDate", "acceptanceDateTime", "form", "items",
        "primaryDocument", "primaryDocDescription", "size"]

def tickers():
    m = json.load(open(INFO))["markets"]
    return sorted(k for k in m if k not in KIT)

# ---------------------------------------------------------------- fetch (rate-limited, cached, filtered)
_last = [0.0]; _refusals = [0]
def _get(url):
    if _refusals[0] >= 2:
        raise RuntimeError("two refusals from EDGAR: stopped")
    wait = 0.25 - (time.time() - _last[0])          # at most 4 requests a second
    if wait > 0: time.sleep(wait)
    _last[0] = time.time()
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code in (403, 429): _refusals[0] += 1
        raise

def _filter_block(block):
    """Keep only filings with KEEP_FROM <= filingDate <= CUT (in memory, before anything is written)."""
    n = len(block.get("filingDate", []))
    def ok(i):   # filed AND accepted in the window, and not an accession number of 2022 or later (re-filed records)
        return (KEEP_FROM <= block["filingDate"][i] <= CUT and block["acceptanceDateTime"][i][:10] <= CUT
                and int(block["accessionNumber"][i].split("-")[1]) <= 21)
    keep = [i for i in range(n) if ok(i)]
    return {c: [block[c][i] for i in keep] for c in COLS if c in block}

def fetch_cik(cik):
    """Cache file raw/CIK##########.json = {cik, name_check, filings (filtered)}; returns its path."""
    out = os.path.join(RAW, f"CIK{cik:010d}.json")
    if os.path.exists(out): return out
    j = _get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    name = j.get("name", "")                     # today's name: kept only to check the CIK, not used as data
    blocks = [_filter_block(j["filings"]["recent"])]
    extra = []
    for f in j["filings"].get("files", []):
        if f["filingTo"] >= KEEP_FROM and f["filingFrom"] <= CUT:
            blocks.append(_filter_block(_get("https://data.sec.gov/submissions/" + f["name"])))
            extra.append(f["name"])
    rows = {c: sum((b.get(c, []) for b in blocks), []) for c in COLS}
    os.makedirs(RAW, exist_ok=True)
    json.dump({"cik": cik, "name_check": name, "extra_files": extra, "filings": rows,
               "fetched_utc": pd.Timestamp.now("UTC").isoformat(), "kept": f"{KEEP_FROM}..{CUT}"}, open(out, "w"))
    return out

def refilter_cache():
    """Apply the current window filter to every cached reply again (in place)."""
    for t in tickers():
        for cik, _ in CIKS[t]:
            p = os.path.join(RAW, f"CIK{cik:010d}.json")
            j = json.load(open(p)); j["filings"] = _filter_block(j["filings"]); json.dump(j, open(p, "w"))

def fetch():
    fetch_baba()
    for t in tickers():
        for cik, word in CIKS[t]:
            p = fetch_cik(cik)
            nm = json.load(open(p))["name_check"]
            ok = word.lower() in nm.lower()
            print(f"{t:6s} CIK {cik:>8d} {nm[:40]:40s} {'ok' if ok else 'NAME MISMATCH'}")

# ---------------------------------------------------------------- build
def _filings(ticker):
    """All cached filings of a lab key (predecessor CIKs merged, co-registrant duplicates dropped)."""
    frames = []
    for cik, _ in CIKS[ticker]:
        p = os.path.join(RAW, f"CIK{cik:010d}.json")
        d = pd.DataFrame(json.load(open(p))["filings"]); d["cik"] = cik; frames.append(d)
    d = pd.concat(frames, ignore_index=True).drop_duplicates("accessionNumber")
    d = d[(d.filingDate <= CUT) & (d.acceptanceDateTime.str.slice(0, 10) <= CUT)]
    # acceptanceDateTime in the submissions JSON is UTC (checked: Apple 2021-10-28 20:30Z = 16:30 New York)
    d["accepted_utc"] = pd.to_datetime(d.acceptanceDateTime, utc=True, format="ISO8601")
    d["accepted_et"] = d.accepted_utc.dt.tz_convert(NY)
    return d.sort_values("accepted_utc").reset_index(drop=True)

# Alibaba files 6-K (foreign issuer: no 8-K, no items). Its results 6-K are found with EDGAR full-text search
# (efts.sec.gov answers the plain client name), phrase "Alibaba Group Announces" + "Quarter Results", 6-K only.
FTS_BABA = ("https://efts.sec.gov/LATEST/search-index?q=%22Alibaba%20Group%20Announces%22%20Quarter%20Results"
            "&forms=6-K&ciks=0001577552&dateRange=custom&startdt=2016-10-01&enddt=2021-12-31")

def fetch_baba():
    out = os.path.join(RAW, "fts_baba_results.json")
    if os.path.exists(out): return out
    j = _get(FTS_BABA)
    acc = sorted({h["_id"].split(":")[0] for h in j["hits"]["hits"] if h["_source"]["file_date"] <= CUT})
    json.dump({"query": FTS_BABA, "accessions": acc, "total": j["hits"]["total"]["value"]}, open(out, "w"))
    return out

# Results releases filed under the wrong item (no 2.02 in EDGAR's index): found by the gap check, added by hand.
GAP_FILLS = {
    "0000040545-17-000020": "ge Q1 2017: 8-K ge8k1q17.htm filed with item 9.01 only",
    "0000040545-20-000019": "ge Q1 2020: 8-K ge1q20208-k.htm filed with item 9.01 only",
    "0001104659-21-050513": "c Q1 2021: 8-K declared item 2.01 instead of 2.02",
}

# NYSE full-day closures 2016-10..2022-01 (the lab's share bars confirm 2017-01-26..2021-12-31: see test())
NYSE_HOLIDAYS = {pd.Timestamp(x).date() for x in """
2016-11-24 2016-12-26 2017-01-02 2017-01-16 2017-02-20 2017-04-14 2017-05-29 2017-07-04 2017-09-04 2017-11-23
2017-12-25 2018-01-01 2018-01-15 2018-02-19 2018-03-30 2018-05-28 2018-07-04 2018-09-03 2018-11-22 2018-12-05
2018-12-25 2019-01-01 2019-01-21 2019-02-18 2019-04-19 2019-05-27 2019-07-04 2019-09-02 2019-11-28 2019-12-25
2020-01-01 2020-01-20 2020-02-17 2020-04-10 2020-05-25 2020-07-03 2020-09-07 2020-11-26 2020-12-25 2021-01-01
2021-01-18 2021-02-15 2021-04-02 2021-05-31 2021-07-05 2021-09-06 2021-11-25 2021-12-24 2022-01-17""".split()}

def is_session(d):
    return pd.Timestamp(d).weekday() < 5 and d not in NYSE_HOLIDAYS

def reaction_session(accepted_utc):
    """First regular session (09:30-16:00 New York) that STARTS strictly after the acceptance time."""
    et = accepted_utc.tz_convert(NY)
    d = et.date()
    if (et.hour, et.minute, et.second) >= (9, 30, 0):
        d = d + pd.Timedelta(days=1)
    while not is_session(d):
        d = d + pd.Timedelta(days=1)
    return d

def _when(et):
    m = et.hour * 60 + et.minute
    return "before_open" if m < 570 else ("in_session" if m < 960 else "after_close")

def build(verbose=True):
    raw_rows = []
    baba_acc = set(json.load(open(os.path.join(RAW, "fts_baba_results.json")))["accessions"])
    for t in tickers():
        f = _filings(t)
        f["items"] = f["items"].fillna("")
        periodic = f[f.form.isin(["10-Q", "10-K", "10-KT"])].copy()
        is_rel = (f.form.isin(["8-K", "8-K/A"]) & f["items"].str.contains(r"\b2\.02\b")) | \
                 f.accessionNumber.isin(GAP_FILLS) | (f.form.eq("6-K") & f.accessionNumber.isin(baba_acc))
        ev = f[is_rel].copy()
        ev["event_date"] = ev.reportDate.fillna("")
        ev["note"] = ev.accessionNumber.map(GAP_FILLS).fillna("")
        ev.loc[ev.form == "6-K", "note"] = "6-K results (full-text search); filed hours after the release: see traps"
        # fiscal period ends: reportDate of the 10-Q/10-K, extended by 91-day steps to the cut
        pe = sorted(set(pd.to_datetime(periodic.reportDate[periodic.reportDate.fillna("") != ""])))
        if t == "baba":       # 20-F filer, quarters end on calendar quarter ends
            pe = list(pd.date_range("2015-03-31", CUT, freq="QE"))
        filled = [pe[0]]                 # a missing 10-Q/10-K (e.g. a record re-filed in 2022 and dropped): fill
        for x in pe[1:]:
            while (x - filled[-1]).days > 120:
                filled.append(filled[-1] + pd.Timedelta(days=91))
            filled.append(x)
        pe = filled
        while pe[-1] < pd.Timestamp(CUT) - pd.Timedelta(days=1):
            pe.append(pe[-1] + pd.Timedelta(days=91))
        pe = pd.DatetimeIndex(pe)
        acc_day = ev.accepted_et.dt.tz_localize(None).dt.normalize()
        pos = pe.searchsorted(acc_day, side="left") - 1       # last period end strictly before the release day
        ev["period_end"] = pd.to_datetime([pe[i] if i >= 0 else pd.NaT for i in pos]).values
        ev["lag_days"] = (acc_day - ev.period_end).dt.days
        # the company's usual lag L: per period, the last plain 8-K 2.02 before that period's 10-Q/10-K
        lags = []
        for _, r in periodic.iterrows():
            if not r.reportDate: continue
            c = ev[(ev.form != "8-K/A") & (ev.period_end == pd.Timestamp(r.reportDate)) & (ev.accepted_utc <= r.accepted_utc)]
            if len(c): lags.append(c.lag_days.iloc[-1])
        L = float(pd.Series(lags).median()) if lags else float(ev.groupby("period_end").lag_days.min().median())
        ev = ev[ev.accepted_et.dt.strftime("%Y-%m-%d") >= START].copy()
        ev["quarter_flag"] = ""
        for p, g in ev.groupby("period_end"):
            cand = g[g.form != "8-K/A"]
            if cand.empty:
                ev.loc[g.index, "quarter_flag"] = "amendment"; continue
            # a follow-up 8-K (call transcript, extra tables) carries the event date of an earlier release
            acc_d = cand.accepted_et.dt.strftime("%Y-%m-%d")
            follow = (cand.event_date < acc_d) & cand.event_date.isin(set(acc_d))
            pool = cand[~follow] if (~follow).any() else cand
            near = pool[(pool.lag_days - L).abs() <= max(2.0, min(7.0, 0.25 * L))]
            best = near.index[0] if len(near) else (pool.lag_days - L).abs().idxmin()
            for i in g.index:
                if i == best: ev.at[i, "quarter_flag"] = "results"
                elif ev.at[i, "form"] == "8-K/A": ev.at[i, "quarter_flag"] = "amendment"
                elif ev.at[i, "accepted_utc"] < ev.at[best, "accepted_utc"]: ev.at[i, "quarter_flag"] = "before_results"
                else: ev.at[i, "quarter_flag"] = "after_results"
        ev["ticker"] = t
        ev["usual_lag"] = L
        ev["when"] = ev.accepted_et.map(_when)
        ev["reaction_session"] = [reaction_session(x) for x in ev.accepted_utc]
        raw_rows.append(ev)
    raw = pd.concat(raw_rows, ignore_index=True)
    raw = raw.rename(columns={"accessionNumber": "accession", "filingDate": "filing_date"})
    out = raw[["ticker", "accepted_utc", "accepted_et", "when", "reaction_session", "quarter_flag", "form", "items",
               "accession", "filing_date", "event_date", "period_end", "lag_days", "usual_lag", "note",
               "primaryDocument", "cik"]].sort_values(["ticker", "accepted_utc"]).reset_index(drop=True)
    assert out.filing_date.max() <= CUT and out.accepted_utc.max() < pd.Timestamp("2022-01-01", tz="UTC")
    os.makedirs(CACHE, exist_ok=True)
    w = out.copy()
    w["accepted_utc"] = w.accepted_utc.dt.strftime("%Y-%m-%d %H:%M:%S+00:00")
    w["accepted_et"] = w.accepted_et.dt.strftime("%Y-%m-%d %H:%M:%S%z")
    w["period_end"] = w.period_end.dt.strftime("%Y-%m-%d")
    w.to_csv(os.path.join(CACHE, "calendar_raw.csv"), index=False)
    w[w.quarter_flag == "results"].drop(columns=["primaryDocument"]).to_csv(os.path.join(CACHE, "calendar.csv"), index=False)
    if verbose:
        print(f"raw rows {len(out)}, results {int((out.quarter_flag == 'results').sum())} -> {CACHE}/calendar*.csv")
    return out

# ---------------------------------------------------------------- the function a run uses
def calendar(end=CUT, quarterly_only=True, path=None, drop_late=False):
    """Earnings releases accepted on or before `end` (date or timestamp, read as UTC; never after 2021-12-31).
    quarterly_only=True keeps the one release per fiscal quarter marked 'results'; False returns every 8-K with
    item 2.02 (and Alibaba's results 6-K) with its flag.
    Column late_by_construction (verifier EV-1, 2026-11-18): True where the stamp is known to be a session LATE, so
    the reaction_session named here is the session AFTER the real reaction: Alibaba's 6-K (filed hours after a release
    made before the US open) and the rows accepted during the session (Citigroup). A rule that trades the reaction
    day drops them (drop_late=True); never move them earlier."""
    path = path or os.path.join(CACHE, "calendar_raw.csv")
    d = pd.read_csv(path, dtype={"items": str})
    d["accepted_utc"] = pd.to_datetime(d.accepted_utc, utc=True)
    d["accepted_et"] = d.accepted_utc.dt.tz_convert(NY)
    for c in ("reaction_session", "period_end", "filing_date"):
        d[c] = pd.to_datetime(d[c])
    e = pd.Timestamp(end)
    e = e.tz_localize("UTC") if e.tzinfo is None else e.tz_convert("UTC")
    if len(str(end)) <= 10: e = e + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)   # a date = the whole day
    e = min(e, pd.Timestamp(CUT + " 23:59:59", tz="UTC"))
    d = d[d.accepted_utc <= e]
    if quarterly_only: d = d[d.quarter_flag == "results"]
    d = d.assign(late_by_construction=(d.form == "6-K") | (d.when == "in_session"))
    if drop_late: d = d[~d.late_by_construction]
    return d.reset_index(drop=True)

# ---------------------------------------------------------------- self-checks on the cache
def test():
    n = 0
    def ok(cond, msg):
        nonlocal n
        assert cond, msg; n += 1
    cal = calendar()
    raw = calendar(quarterly_only=False)
    ok(cal.accepted_utc.max() <= pd.Timestamp("2021-12-31 23:59:59", tz="UTC"), "nothing after the cut")
    ok(set(cal.ticker) == set(tickers()), f"all 40 shares present: missing {set(tickers()) - set(cal.ticker)}")
    ok(cal.accession.is_unique, "one row per filing")
    ok(not cal.groupby(["ticker", "period_end"]).size().gt(1).any(), "one 'results' per fiscal quarter")
    # time zone: Apple's Q4 FY2021 8-K accepted 2021-10-28 16:30:39 New York = 20:30:39 UTC (EDT, UTC-4)
    a = cal[(cal.ticker == "aapl") & (cal.accepted_et.dt.strftime("%Y-%m-%d") == "2021-10-28")]
    ok(len(a) == 1 and a.accepted_utc.iloc[0].strftime("%H:%M") == "20:30", "Apple 2021-10-28 at 20:30 UTC")
    ok(str(a.reaction_session.iloc[0].date()) == "2021-10-29", "Apple reaction session = next day")
    # winter (EST, UTC-5): Apple 2021-01-27 after the close -> 21:3x UTC
    a = cal[(cal.ticker == "aapl") & (cal.accepted_et.dt.strftime("%Y-%m-%d") == "2021-01-27")]
    ok(len(a) == 1 and a.accepted_utc.iloc[0].hour == 21, "Apple 2021-01-27 in winter time")
    # JPMorgan reports before the open: reaction session = the same day
    j = cal[(cal.ticker == "jpm") & (cal.accepted_et.dt.strftime("%Y-%m-%d") == "2021-10-13")]
    ok(len(j) == 1 and j.accepted_et.iloc[0].hour < 9 and str(j.reaction_session.iloc[0].date()) == "2021-10-13",
       "JPM 2021-10-13 before the open, reacts the same day")
    # a dozen well-known release dates (New York date of acceptance, after the close 'ac' / before the open 'bo')
    known = [("aapl", "2021-10-28", "after_close"), ("msft", "2021-10-26", "after_close"),
             ("amzn", "2021-10-28", "after_close"), ("googl", "2021-10-26", "after_close"),
             ("fb", "2021-10-25", "after_close"), ("nflx", "2021-10-19", "after_close"),
             ("tsla", "2021-10-20", "after_close"), ("intc", "2021-10-21", "after_close"),
             ("nvda", "2021-11-17", "after_close"), ("wmt", "2021-11-16", "before_open"),
             ("nke", "2021-12-20", "after_close"), ("mu", "2021-12-20", "after_close"),
             ("jpm", "2021-10-13", "before_open")]
    day = cal.accepted_et.dt.strftime("%Y-%m-%d")
    for t, dte, w in known:
        r = cal[(cal.ticker == t) & (day == dte)]
        ok(len(r) == 1 and r.when.iloc[0] == w, f"known date {t} {dte} {w}")
    # Apple's revenue warning of 2019-01-02 and Tesla's delivery reports carry item 2.02 but are not the results
    ok(raw[(raw.ticker == "aapl") & (raw.accepted_et.dt.strftime("%Y-%m-%d") == "2019-01-02")].quarter_flag.iloc[0]
       == "before_results", "Apple 2019-01-02 warning flagged before_results")
    ok((raw[(raw.ticker == "tsla") & (raw.lag_days <= 7)].quarter_flag == "before_results").all(), "Tesla deliveries")
    # every share: 21 quarterly results in 2016-10..2021-12 (Micron 22: its fiscal quarters end early in the month)
    cnt = cal.groupby("ticker").size()
    ok(((cnt == 21) | ((cnt.index == "mu") & (cnt == 22))).all(), f"counts {cnt[cnt != 21].to_dict()}")
    ok(set(GAP_FILLS) <= set(cal.accession), "hand-added results (wrong item in EDGAR) are in the calendar")
    ok((cal[cal.ticker == "baba"].form == "6-K").all(), "Alibaba from 6-K")
    # the holiday list agrees with the lab's share bars (2017-01-27..2021-12-31)
    idx = pd.read_parquet(os.path.expanduser("~/explore_data/h1/aapl.parquet"), columns=["close"]).index
    have = set(idx.tz_convert(NY).date)
    wk = [d.date() for d in pd.bdate_range("2017-01-27", "2021-12-31")]
    ok(all((d in have) == is_session(d) for d in wk), "NYSE holiday list = days without bars")
    # the cut is honoured
    c2 = calendar(end="2019-06-30")
    ok(c2.accepted_utc.max() <= pd.Timestamp("2019-06-30 23:59:59", tz="UTC") and len(c2) < len(cal), "cut at end")
    # reaction session always starts after the acceptance time
    rs = pd.to_datetime(raw.reaction_session.astype(str) + " 09:30").dt.tz_localize(NY)
    ok((rs > raw.accepted_et).all(), "reaction session opens after acceptance")
    ok(((rs - raw.accepted_et) < pd.Timedelta(days=6)).all(), "reaction session within 6 days")
    print(f"{n}/{n} checks passed")

if __name__ == "__main__":
    {"fetch": fetch, "build": build, "test": test, "refilter": refilter_cache}[sys.argv[1]]()
