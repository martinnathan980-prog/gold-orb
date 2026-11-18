"""Broad universe of US shares for direction 3 (lead/DIRECTION3.md): one row per company of today's S&P 500 list.

    PYTHONDONTWRITEBYTECODE=1 python3 -B universe_us.py fetch   # download (cached) the lists + Yahoo volumes of 2021
    PYTHONDONTWRITEBYTECODE=1 python3 -B universe_us.py build   # write ~/explore_data/d1/universe.csv (+ side files)
    PYTHONDONTWRITEBYTECODE=1 python3 -B universe_us.py test    # checks on universe.csv (no network)
    PYTHONDONTWRITEBYTECODE=1 python3 -B universe_us.py report  # the numbers of the hand-back (no network)

Sources (all cached in ~/explore_data/d1/raw_universe/, read on 2026-11-18):
- constituents.csv   github datasets/s-and-p-500-companies (today's list: ticker, name, GICS, date added, CIK).
                     THE source of universe.csv.
- wikipedia_sp500.html  Wikipedia REST page html of "List of S&P 500 companies": cross-check of the list only.
                     On 2026-11-18 that page holds the constituents table but NO table of changes.
- fja_*.csv          github fja05680/sp500: point-in-time lists of the index's tickers (one row per change date,
                     1996..2026-08-18), the changes since 2019 and each ticker's first/last date. Used to (a) check
                     'added' and (b) count the companies that were in the index in 2017-2021 and are not in today's
                     list (survivors only). Index membership dates only: no price, nothing else.
- yahoo_<SYM>_2021.json  Yahoo chart API daily bars 2021-01-01..2021-12-31 of the dual-class shares only, to compare
                     their volumes. The reply's 'meta' block (today's price) is deleted before the reply is written
                     and never printed; bars of 2022 or later are dropped in memory.
                     2026-11-18: Yahoo answered 429 (Too Many Requests) to the first request and again to one retry:
                     host dropped after two refusals, no Yahoo file cached, so FOXA/FOX and NWSA/NWS fell to the
                     'first listed' rule (FOXA and NWSA kept). A later 'fetch' tries again (stops at two refusals).
Side files: universe_dropped_classes.csv (the share classes dropped), universe_left_2017_2021.csv (tickers in the
index at some time in 2017-2021 whose company is not in today's list; last_in_lists = last point-in-time list that
holds the ticker, the removal is at the next list).

Rules (see build()):
- key = lower-case ticker, letters and digits only ('brkb'); yahoo = ticker with '.' -> '-'.
- one row per CIK: a class that is one of the lab's 40 is kept; else the class with the larger 2021 volume on Yahoo;
  else the first listed. Dropped classes go to universe_dropped_classes.csv.
- in_universe_from = later of 2017-01-01 and 'added' (constituents.csv), as the plan says.
  fja_from = first point-in-time list of 2017-01-03..2021-12-31 that holds the ticker (or its former ticker):
  a check of 'added', NOT used in in_universe_from; disagreements are flagged in 'added_note'.
- in_universe = not in_lab40 and added < 2022-01-01 and kept class (always true after the per-CIK step).
"""
import json, os, re, sys, time, urllib.request, urllib.error
import pandas as pd

D1 = os.path.expanduser("~/explore_data/d1")
RAW = os.path.join(D1, "raw_universe")
OUT = os.path.join(D1, "universe.csv")
INFO = os.path.expanduser("~/explore_data/h1/info.json")
READ_ON = "2026-11-18"              # date the lists were read (the cache files' date)
START, CUT = "2017-01-01", "2022-01-01"
KIT = {"xauusd", "xagusd", "us100", "us500", "us30", "ger40", "eurusd", "gbpusd", "usdjpy", "audusd", "usdcad",
       "usdchf", "nzdusd", "eurjpy", "oil"}
LAB_ALIAS = {"fb": "meta"}          # lab key -> key in today's list (Facebook renamed Meta Platforms, same CIK)
BROWSER = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/120.0 Safari/537.36", "Accept-Encoding": "identity"}
SOURCES = {
    "constituents.csv": "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv",
    "wikipedia_sp500.html": "https://en.wikipedia.org/api/rest_v1/page/html/List_of_S%26P_500_companies",
    "fja_README.md": "https://raw.githubusercontent.com/fja05680/sp500/master/README.md",
    "fja_historical_components.csv": "https://raw.githubusercontent.com/fja05680/sp500/master/"
                                     "S%26P%20500%20Historical%20Components%20%26%20Changes%20(Updated).csv",
    "fja_changes_since_2019.csv": "https://raw.githubusercontent.com/fja05680/sp500/master/sp500_changes_since_2019.csv",
    "fja_ticker_start_end.csv": "https://raw.githubusercontent.com/fja05680/sp500/master/sp500_ticker_start_end.csv",
}
# Former ticker (in the point-in-time lists of 2017-2021) -> today's ticker of the SAME company, written by hand and
# checked against today's list (the successor must be in it). Same SEC registrant unless marked '(successor)'.
RENAMED = {
    "FB": "META", "ABC": "COR", "ANTM": "ELV", "BLL": "BALL", "FLT": "CPAY", "HCP": "DOC", "PEAK": "DOC",
    "PKI": "RVTY", "RE": "EG", "WLTW": "WTW", "SYMC": "GEN", "NLOK": "GEN", "JEC": "J", "TMK": "GL",
    "ARNC": "HWM",      # Arconic Inc. renamed Howmet Aerospace in 2020 (same CIK 4281)
    "BHGE": "BKR", "DWDP": "DD", "UTX": "RTX", "BBT": "TFC", "HRS": "LHX", "BK": "BNY", "MMC": "MRSH",
    "MYL": "VTRS",      # (successor) Mylan merged into Viatris (new CIK 1792044) in 2020; the index kept the slot
    "PX": "LIN",        # (successor) Praxair merged into Linde plc (new CIK 1707925) in 2018; the index kept the slot
    "CBS": "SKYD", "VIAC": "SKYD",   # (successor) CBS -> ViacomCBS -> Paramount -> Skydance (new CIK 2041610)
    "EQR": "VMRK",      # Equity Residential took AvalonBay in 2026 and became Vivmark Residential (same CIK 906107)
}
# Ticker reused by a different company: fja's point-in-time match is not this company; 'added' is right.
REUSED = {"DD": "DD was old E. I. du Pont (CIK 30554) until 2017-08; today's DuPont (CIK 1666700) is DowDuPont renamed",
          "DOW": "DOW was Dow Chemical until 2017-08; today's Dow Inc. (CIK 1751788) was spun off on 2019-04-01",
          "FOXA": "FOXA was Twenty-First Century Fox until 2019-03; today's Fox Corp. (CIK 1754301) from 2019-03-19",
          "IR": "IR was Ingersoll-Rand plc (now TT) until 2020-03; today's Ingersoll Rand Inc. joined 2020-03-03",
          "TT": "Trane Technologies traded as IR (Ingersoll-Rand plc) until 2020-03-02: in the index all along",
          "BKR": "fja writes Baker Hughes Inc. (BHI, CIK 808362) under the later ticker; today's Baker Hughes "
                 "(CIK 1701605) formed on 2017-07-03"}
# The list's 'added' is later than the share's real first day in the index (no look-ahead: the universe starts it late).
LATE_DATE = {"SRE": "Sempra was in the index before 2017; the list says 2017-03-17 (2.5 months lost, harmless)",
             "TROW": "T. Rowe Price was in the index before 2017; the list says 2019-07-29 (fja: on 2017-01-03): "
                     "2.5 years lost, harmless but notable"}
# CIK numbers from about 1687000 were given out in 2017 or later (EDGAR assigns them in sequence).
NEW_CIK = 1687000
NEW_CIK_OK = {"MRNA", "BKR", "EVRG", "AMCR", "DOW", "FOXA", "STE", "OTIS", "CARR", "IR"}   # formed before 'added'
PREDECESSOR = {   # from memory, NOT checked against EDGAR: the events job must confirm them by name
    "CI": "old Cigna Corp CIK 701221, until the Express Scripts deal of 2018-12",
    "LIN": "Praxair CIK 884905, until 2018-10",
    "VTRS": "Mylan N.V. CIK 1623613, until 2020-11",
    "APA": "Apache Corp CIK 6769, until 2021-03",
    "BLK": "old BlackRock CIK 1364742, until 2024-10",
    "SKYD": "CBS / ViacomCBS / Paramount Global CIK 813828, until 2025-08",
}

# Tickers of the same departed company (counted once): later ticker -> earlier ticker.
SAME_LEFT = {"DISCK": "DISCA", "UA": "UAA", "CTRA": "COG", "BBWI": "LB", "CPRI": "KORS",
             "LUMN": "CTL"}
# Hand labels of departed companies (for the list of the best known; names from general knowledge, not fetched).
LEFT_NAMES = {
    "CELG": "Celgene (bought by Bristol-Myers Squibb 2019)", "AGN": "Allergan (bought by AbbVie 2020)",
    "TWX": "Time Warner (bought by AT&T 2018)", "ESRX": "Express Scripts (bought by Cigna 2018)",
    "AET": "Aetna (bought by CVS 2018)", "MON": "Monsanto (bought by Bayer 2018)",
    "RHT": "Red Hat (bought by IBM 2019)", "XLNX": "Xilinx (bought by AMD 2022)",
    "ATVI": "Activision Blizzard (bought by Microsoft 2023)", "TWTR": "Twitter (taken private 2022)",
    "CERN": "Cerner (bought by Oracle 2022)", "CTXS": "Citrix (taken private 2022)",
    "WBA": "Walgreens Boots Alliance (taken private 2025)", "DISCA": "Discovery / Warner Bros. Discovery",
    "CBS": "CBS / ViacomCBS / Paramount", "VIAB": "Viacom (merged into CBS 2019)",
    "SIVB": "SVB Financial (failed 2023)", "FRC": "First Republic Bank (failed 2023)",
    "RTN": "Raytheon (merged into United Technologies 2020)", "COL": "Rockwell Collins (bought by UTC 2018)",
    "PXD": "Pioneer Natural Resources (bought by ExxonMobil 2024)", "HES": "Hess (bought by Chevron 2025)",
    "MRO": "Marathon Oil (bought by ConocoPhillips 2024)", "ANSS": "Ansys (bought by Synopsys 2025)",
    "JNPR": "Juniper Networks (bought by HPE 2025)", "DFS": "Discover Financial (bought by Capital One 2025)",
    "EA": "Electronic Arts", "K": "Kellogg / Kellanova", "INFO": "IHS Markit (merged into S&P Global 2022)",
    "MXIM": "Maxim Integrated (bought by Analog Devices 2021)", "ALXN": "Alexion (bought by AstraZeneca 2021)",
    "KSU": "Kansas City Southern (bought by Canadian Pacific 2023)", "WFM": "Whole Foods (bought by Amazon 2017)",
    "CA": "CA Technologies (bought by Broadcom 2018)", "LLTC": "Linear Technology (bought by Analog Devices 2017)",
    "STJ": "St. Jude Medical (bought by Abbott 2017)", "RAI": "Reynolds American (bought by BAT 2017)",
    "GPS": "Gap", "M": "Macy's", "KSS": "Kohl's", "MAT": "Mattel", "HOG": "Harley-Davidson", "XRX": "Xerox",
    "CTL": "CenturyLink / Lumen", "DISH": "Dish Network", "TIF": "Tiffany (bought by LVMH 2021)",
}
# 30 of the best known departed companies (chosen by hand for size and fame, not measured: no price data is used).
TOP30 = ["CELG", "AGN", "TWX", "ESRX", "AET", "MON", "RHT", "XLNX", "ATVI", "TWTR", "CERN", "WBA", "DISCA", "VIAB",
         "RTN", "COL", "PXD", "HES", "MRO", "ANSS", "JNPR", "DFS", "EA", "K", "INFO", "MXIM", "ALXN", "KSU", "SIVB",
         "CTXS"]
COLS = ["key", "yahoo", "ticker", "name", "cik", "sector", "sub_industry", "added", "in_universe_from",
        "in_lab40", "in_universe", "fja_from", "added_note"]

def key_of(t):  return re.sub(r"[^a-z0-9]", "", t.lower())
def yahoo_of(t): return t.replace(".", "-")

# ---------------------------------------------------------------- fetch (polite, cached)
_last = {}; _refused = {}
def _get(url, host, pause):
    if _refused.get(host, 0) >= 2:
        raise RuntimeError(f"two refusals in a row from {host}: stopped using it")
    wait = pause - (time.time() - _last.get(host, 0.0))
    if wait > 0: time.sleep(wait)
    _last[host] = time.time()
    try:
        b = urllib.request.urlopen(urllib.request.Request(url, headers=BROWSER), timeout=60).read()
        _refused[host] = 0
        return b
    except urllib.error.HTTPError as e:
        if e.code in (403, 429): _refused[host] = _refused.get(host, 0) + 1
        raise

def fetch_lists():
    os.makedirs(RAW, exist_ok=True)
    for name, url in SOURCES.items():
        p = os.path.join(RAW, name)
        if os.path.exists(p): continue
        open(p, "wb").write(_get(url, url.split("/")[2], 1.5))
        print("fetched", name)

def _unix(d): return int(pd.Timestamp(d, tz="UTC").timestamp())

def fetch_yahoo_2021(sym):
    """Daily bars 2021 of one symbol; the 'meta' block is removed before writing; bars >= 2022 dropped."""
    p = os.path.join(RAW, f"yahoo_{sym}_2021.json")
    if os.path.exists(p): return p
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={_unix('2021-01-01')}"
           f"&period2={_unix(CUT)}&interval=1d&events=div%2Csplits")
    j = json.loads(_get(url, "query1.finance.yahoo.com", 1.2))
    ch = j.get("chart", {})
    if ch.get("error") or not ch.get("result"):
        raise RuntimeError(f"Yahoo error for {sym}: {str(ch.get('error'))[:200]}")
    r = ch["result"][0]
    r.pop("meta", None)                                   # today's price and dates: never kept
    r.pop("events", None)
    ts = r.get("timestamp", [])
    keep = [i for i, t in enumerate(ts) if t < _unix(CUT)]
    q = r["indicators"]["quote"][0]
    out = {"symbol": sym, "timestamp": [ts[i] for i in keep],
           "volume": [q["volume"][i] for i in keep], "close": [q["close"][i] for i in keep]}
    json.dump(out, open(p, "w"))
    return p

def fetch():
    fetch_lists()
    c = pd.read_csv(os.path.join(RAW, "constituents.csv"))
    dup = c[c.CIK.duplicated(keep=False)]
    for t in dup.Symbol:
        if key_of(t) in set(lab40()) or key_of(t) == "goog":
            continue                                       # Alphabet: the lab's class (GOOGL) is kept anyway
        try:
            fetch_yahoo_2021(yahoo_of(t))
            print("yahoo 2021 volumes cached:", t)
        except Exception as e:                             # 2026-11-18: Yahoo answered 429 twice -> host dropped
            print(f"yahoo {t}: {str(e)[:120]} -> volume unknown, rule 'first listed' applies")
            if _refused.get("query1.finance.yahoo.com", 0) >= 2:
                print("two refusals in a row from Yahoo: no further Yahoo request"); break

# ---------------------------------------------------------------- build
def lab40():
    m = json.load(open(INFO))["markets"]
    return sorted(LAB_ALIAS.get(k, k) for k in m if k not in KIT)

def pit_lists():
    """Point-in-time lists (fja05680): DataFrame date, set of tickers."""
    h = pd.read_csv(os.path.join(RAW, "fja_historical_components.csv"))
    h["date"] = pd.to_datetime(h.date)
    h["set"] = h.tickers.str.split(",").apply(set)
    return h[["date", "set"]]

def vol2021(t):
    p = os.path.join(RAW, f"yahoo_{yahoo_of(t)}_2021.json")
    if not os.path.exists(p): return None
    v = json.load(open(p))["volume"]
    return float(sum(x for x in v if x)) / max(1, sum(1 for x in v if x))

def fja_from(h, ticker):
    """First point-in-time list of 2017-01-03..2021-12-31 holding the ticker or a former ticker of it."""
    names = {ticker} | {o for o, n in RENAMED.items() if n == ticker}
    w = h[(h.date >= START) & (h.date < CUT)]
    hit = w[w["set"].apply(lambda s: bool(s & names))]
    return "" if hit.empty else hit.date.iloc[0].date().isoformat()

def founded_year(s):
    m = re.search(r"\d{4}", str(s)); return int(m.group()) if m else None

def build(verbose=True):
    c = pd.read_csv(os.path.join(RAW, "constituents.csv"), dtype={"CIK": "Int64"})
    h = pit_lists()
    labs = set(lab40())
    rows, dropped = [], []
    for cik, g in c.groupby("CIK", sort=False):
        g = g.copy()
        g["k"] = g.Symbol.map(key_of)
        if len(g) > 1:
            inlab = g[g.k.isin(labs)]
            vols = {t: vol2021(t) for t in g.Symbol}
            if len(inlab):
                keep, why = inlab.Symbol.iloc[0], "class in the lab's 40"
            elif all(v is not None for v in vols.values()):
                keep, why = max(vols, key=vols.get), "larger mean daily volume on Yahoo in 2021"
            else:
                keep, why = g.Symbol.iloc[0], "first listed (no volume)"
            for t in g.Symbol:
                if t != keep:
                    dropped.append({"ticker_dropped": t, "ticker_kept": keep, "cik": int(cik), "reason": why,
                                    "mean_volume_2021_dropped": vols.get(t), "mean_volume_2021_kept": vols.get(keep)})
            g = g[g.Symbol == keep]
        r = g.iloc[0]
        rows.append(r)
    u = pd.DataFrame(rows)
    out = pd.DataFrame({
        "key": u.Symbol.map(key_of), "yahoo": u.Symbol.map(yahoo_of), "ticker": u.Symbol, "name": u.Security,
        "cik": u.CIK.astype("Int64"), "sector": u["GICS Sector"], "sub_industry": u["GICS Sub-Industry"],
        "added": pd.to_datetime(u["Date added"], errors="coerce").dt.date.astype(str).replace("NaT", ""),
    })
    out["in_universe_from"] = out.added.apply(lambda a: max(START, a) if a else START)
    out["in_lab40"] = out.key.isin(labs)
    out["in_universe"] = (~out.in_lab40) & out.added.apply(lambda a: (a < CUT) if a else True)
    out["fja_from"] = out.ticker.apply(lambda t: fja_from(h, t))
    notes = []
    for _, r in out.iterrows():
        n = []
        if not r.added: n.append("no date added: treated as before 2017 only if fja shows the ticker on 2017-01-03")
        elif r.added >= CUT:
            n.append("added 2022 or later: out" + (f" (fja: in the index under this ticker from {r.fja_from}; left "
                     "and came back, or ticker reused)" if r.fja_from else ""))
        elif r.added < "1957-03-04": n.append("added before the index's 500-share start (1957-03-04)")
        if r.ticker in REUSED:
            n.append("fja date ignored: " + REUSED[r.ticker])
        elif r.added and r.added < CUT:
            if not r.fja_from:
                n.append("fja: never in the index in 2017-2021")
            elif r.added < START and r.fja_from > "2017-01-03":
                n.append(f"fja: not in the index on 2017-01-03, first in 2017-2021 on {r.fja_from}")
            elif r.added >= START and abs((pd.Timestamp(r.fja_from) - pd.Timestamp(r.added)).days) > 7:
                n.append(f"fja: first in 2017-2021 on {r.fja_from}, not {r.added}")
        if r.ticker in LATE_DATE:
            n.append(LATE_DATE[r.ticker])
        if r.in_universe and r.cik >= NEW_CIK and r.ticker not in NEW_CIK_OK:
            n.append(f"CIK {r.cik} registered after 2016 while the share counts from {r.in_universe_from}: 8-Ks "
                     f"before its formation are under a predecessor CIK ({PREDECESSOR.get(r.ticker, 'unknown')})")
        notes.append("; ".join(n))
    out["added_note"] = notes
    out = out[COLS].sort_values("key").reset_index(drop=True)
    os.makedirs(D1, exist_ok=True)
    out.to_csv(OUT, index=False)
    pd.DataFrame(dropped).to_csv(os.path.join(D1, "universe_dropped_classes.csv"), index=False)
    left = survivors_check(h, set(c.Symbol))
    left.to_csv(os.path.join(D1, "universe_left_2017_2021.csv"), index=False)
    if verbose:
        print(f"{len(out)} companies, {int(out.in_universe.sum())} in the universe -> {OUT}")
    return out

def survivors_check(h, current):
    """Tickers in the index at some time in 2017-2021 (fja point-in-time lists) whose company is not in today's list."""
    w = h[(h.date >= START) & (h.date < CUT)]
    seen = {}
    for d, s in zip(w.date, w["set"]):
        for t in s:
            seen.setdefault(t, [d, d]); seen[t][1] = d
    end_is = w["set"].iloc[-1]                          # the last list of 2021 (2021-12-20)
    rows = []
    for t, (a, b) in sorted(seen.items()):
        if t in current: continue
        succ = RENAMED.get(t)
        if succ:
            assert succ in current, (t, succ)
            continue
        # last list holding the ticker (fja runs to 2026-08-18; constituents.csv is later and is 'today')
        hold = h[h["set"].apply(lambda s: t in s)]
        # review D3-12: no date after 2021 is written; a departure after 2021 reads 'after 2021' and the part of the
        # label that tells what happened later (e.g. '(bought by ... 2025)') is cut
        last = hold.date.max().date().isoformat()
        lab = LEFT_NAMES.get(t, "")
        if re.search(r"20[2-9]\d", lab) and re.search(r"(202[2-9]|20[3-9]\d)", lab):
            lab = re.sub(r"\s*\([^)]*\)", "", lab).strip()
        rows.append({"ticker": t, "same_company_as": SAME_LEFT.get(t, ""), "first_2017_2021": a.date().isoformat(),
                     "last_in_lists": last if last < CUT else "after 2021",
                     "left_in_sample": t not in end_is, "label": lab})
    return pd.DataFrame(rows)

# ---------------------------------------------------------------- cross-check with Wikipedia
def wiki_check():
    w = pd.read_html(os.path.join(RAW, "wikipedia_sp500.html"))[0]
    c = pd.read_csv(os.path.join(RAW, "constituents.csv"))
    res = {"rows_constituents": len(c), "rows_wikipedia": len(w),
           "only_constituents": sorted(set(c.Symbol) - set(w.Symbol)),
           "only_wikipedia": sorted(set(w.Symbol) - set(c.Symbol))}
    m = c.merge(w, on="Symbol", suffixes=("_c", "_w"))
    diff = {}
    for col in ["Security", "GICS Sector", "GICS Sub-Industry", "Date added", "CIK"]:
        a, b = m[col + "_c"].astype(str).str.strip(), m[col + "_w"].astype(str).str.strip()
        if col == "CIK": a, b = a.str.lstrip("0"), b.str.lstrip("0")
        bad = m[a != b]
        diff[col] = [(r.Symbol, r[col + "_c"], r[col + "_w"]) for _, r in bad.iterrows()]
    res["differences"] = diff
    return res

# ---------------------------------------------------------------- checks
def test():
    u = pd.read_csv(OUT, dtype={"added": str, "fja_from": str, "added_note": str}, keep_default_na=False)
    fails = []
    def ok(cond, msg):
        print(("ok   " if cond else "FAIL ") + msg)
        if not cond: fails.append(msg)
    iu = u[u.in_universe.astype(str) == "True"]
    lab = u[u.in_lab40.astype(str) == "True"]
    ok(u.key.is_unique, f"unique keys ({len(u)} rows)")
    ok(u.key.str.fullmatch(r"[a-z0-9]+").all(), "keys are lower-case letters and digits")
    ok(u.cik.astype(str).is_unique, "one row per CIK (whole table)")
    ok(iu.cik.astype(str).is_unique, f"unique CIK among the {len(iu)} in_universe rows")
    ok(len(lab) == 39 and set(lab40()) - set(u.key) == {"baba"},
       f"39 of the lab's 40 in the list, Alibaba (a foreign ADR, never in the index) absent ({len(lab)}): "
       f"missing {sorted(set(lab40()) - set(u.key))}")
    ok(not (u.in_lab40.astype(str).eq("True") & u.in_universe.astype(str).eq("True")).any(),
       "no in_lab40 row in the universe")
    ok((iu.cik.astype(str).str.fullmatch(r"\d+")).all() and (iu.sector != "").all(),
       "every in_universe row has a CIK and a sector")
    ok(u.sector.nunique() == 11 and iu.sector.nunique() == 11, f"11 sectors ({u.sector.nunique()}, universe {iu.sector.nunique()})")
    ok((iu.added < CUT).all() and (iu.in_universe_from >= START).all() and (iu.in_universe_from < CUT).all(),
       "universe rows added before 2022, in_universe_from in 2017-2021")
    ok(((u.added >= CUT) <= (u.in_universe.astype(str) == "False")).all(), "every share added 2022+ is out")
    ok((u.yahoo == u.ticker.str.replace(".", "-", regex=False)).all(), "yahoo symbol = ticker with '-'")
    ok(set(lab.key) == set(lab40()) - {"baba"}, "lab keys = info.json shares (fb as meta) minus baba")
    lf = open(os.path.join(D1, "universe_left_2017_2021.csv")).read()
    late = re.findall(r"(?:202[2-9]|20[3-9]\d)", lf)
    ok(not late, f"universe_left_2017_2021.csv holds no year after 2021 ({len(late)} found)")
    dc = pd.read_csv(os.path.join(D1, "universe_dropped_classes.csv"))
    ok(not set(dc.ticker_dropped) & set(u.ticker), f"dropped classes not in the table: {list(dc.ticker_dropped)}")
    print("\nby sector (in_universe):"); print(iu.sector.value_counts().to_string())
    print("\nby year of in_universe_from:"); print(iu.in_universe_from.str[:4].value_counts().sort_index().to_string())
    print("\nFAILED: " + "; ".join(fails) if fails else "\nall checks passed")
    return not fails

def report():
    u = pd.read_csv(OUT, dtype={"added": str}, keep_default_na=False)
    iu = u[u.in_universe.astype(str) == "True"]
    a = u.added
    print("added: before 2017", int((a < START).sum()), {y: int((a.str[:4] == y).sum()) for y in map(str, range(2017, 2022))},
          "2022+", int((a >= CUT).sum()), "empty", int((a == "").sum()))
    print("out because added 2022+:", " ".join(u[a >= CUT].ticker))
    print("\nnotes:"); print(u[u.added_note != ""][["ticker", "added", "fja_from", "in_universe", "added_note"]].to_string())
    print("\nwikipedia cross-check:", json.dumps(wiki_check(), default=str, indent=1))
    left = pd.read_csv(os.path.join(D1, "universe_left_2017_2021.csv"), keep_default_na=False)
    left["company"] = left.same_company_as.where(left.same_company_as != "", left.ticker)
    comp = left.groupby("company").left_in_sample.apply(lambda x: x.astype(str).eq("True").all())
    print(f"\nleft: {len(left)} tickers, {len(comp)} companies in the index at some time in 2017-2021 and not in "
          f"today's list; of them {int(comp.sum())} left before the end of 2021 (not in fja's list of 2021-12-20) and "
          f"{int((~comp).sum())} were still in the index at the end of 2021 and left later")
    assert set(TOP30) <= set(left.ticker), set(TOP30) - set(left.ticker)
    print("\n30 best known:"); print(left.set_index("ticker").loc[TOP30, ["first_2017_2021", "last_in_lists", "label"]].to_string())
    print(left.to_string())

if __name__ == "__main__":
    {"fetch": fetch, "build": build, "test": test, "report": report}[sys.argv[1]]()
