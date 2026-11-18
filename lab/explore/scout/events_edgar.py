"""Event calendar of the broad US universe (lead/DIRECTION3.md): every 8-K / 8-K/A of each company, 2016-2021,
with the time it became public, from SEC EDGAR. Method of earnings_edgar.py (verified on the lab's 40 shares),
extended to every 8-K and to the companies of ~/explore_data/d1/universe.csv (rows with in_universe true).

Usage
    PYTHONDONTWRITEBYTECODE=1 python3 -B events_edgar.py fetch    # filings lists (cached, filtered, resumable)
    PYTHONDONTWRITEBYTECODE=1 python3 -B events_edgar.py build    # ~/explore_data/events_d1/events_raw.csv (+ side files)
    PYTHONDONTWRITEBYTECODE=1 python3 -B events_edgar.py test     # checks + counts + price witness (no network)
    from events_edgar import calendar, news_sessions, idea_sessions
    res = calendar("2021-12-31", kind="results", drop_late=True)   # one row per fiscal quarter; event day = event_session
    oth = calendar("2021-12-31", kind="other")                     # 8-K rows without item 2.02 (candidates left out)
    ns = news_sessions()                                           # one row per share-session with any filing
    s61 = idea_sessions("061"); s62 = idea_sessions("062")         # the share-sessions of ideas 061 / 062 (one reading)

Event day (review D3-3/D3-4, 2026-11-18): `event_session` = the session s whose window [close of s-1, close of s)
holds the acceptance instant (close 16:00 New York, 13:00 on half days). It is the first close at which the 8-K is
public, so a move read at that close and a trade at the next open use nothing unknown. It equals `reaction_session`
except for rows accepted INSIDE a session (when = in_session), whose reaction_session is the next session. This is a
property of the clock, never of prices; prices may only FLAG a stamp as late (`late_suspect`), never move it earlier.

Source facts (re-checked here, see sources.md section 'Events of a broad universe of US shares'):
- https://data.sec.gov/submissions/CIK##########.json and the extra files it names answer the client name
  "research-client/1.0" (nothing personal). www.sec.gov is NOT used (it refuses this client).
- acceptanceDateTime in that JSON is real UTC (earnings_edgar.py, sources.md section 30 and its verification).
- Every reply is filtered IN MEMORY before it is written: only rows with 2015-06-01 <= filingDate <= 2021-12-31,
  acceptance (UTC) before 2022-01-01 and an accession number of year <= 21 (records re-filed later under an old
  date are dropped), and only the forms needed (8-K family, 10-Q/10-K family, 6-K/20-F/40-F to detect foreign filers).
"""
import json, os, sys, time, urllib.request, urllib.error
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import earnings_edgar as ee        # imported, never edited: UA, COLS, NYSE_HOLIDAYS, reaction_session, is_session

UNIVERSE = os.path.expanduser("~/explore_data/d1/universe.csv")
BARS = os.path.expanduser("~/explore_data/d1/bars")
OUT = os.path.expanduser("~/explore_data/events_d1")
RAW = os.path.join(OUT, "raw")
KEEP_FROM, CUT = "2015-06-01", "2021-12-31"
EV_FROM = pd.Timestamp("2016-01-01", tz="UTC")       # first 8-K of the table (acceptance, UTC)
CUT_TS = pd.Timestamp("2022-01-01", tz="UTC")        # nothing at or after this instant, anywhere
NY = "America/New_York"
FORMS_KEEP = {"8-K", "8-K/A", "8-K12B", "8-K12G3", "8-K15D5", "10-Q", "10-Q/A", "10-K", "10-K/A", "10-KT",
              "10-KT/A", "10-K405", "6-K", "6-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
EV_FORMS = {"8-K", "8-K/A"}
PERIODIC = {"10-Q", "10-K", "10-KT"}

# The earlier script's hand holiday list starts 2016-11-24; the 2016 closures before that are added here (NYSE).
ee.NYSE_HOLIDAYS.update(pd.Timestamp(x).date() for x in
                        "2016-01-01 2016-01-18 2016-02-15 2016-03-25 2016-05-30 2016-07-04 2016-09-05".split())
# NYSE early closes (13:00 New York) 2016-2021; 2017-2021 agree with the lab's hourly bars of aapl (last bar 12:00).
HALF_DAYS = {pd.Timestamp(x).date() for x in """2016-11-25 2017-07-03 2017-11-24 2018-07-03 2018-11-23 2018-12-24
2019-07-03 2019-11-29 2019-12-24 2020-11-27 2020-12-24 2021-11-26""".split()}

# Predecessor registrants: the universe's CIK is a NEW holding company or merged company created after 2016, so the
# company's 8-Ks of the earlier years sit under the old CIK. Written by hand, checked against the name data.sec.gov
# returns (today's name of the old registrant, given here). Cut-over = the day the new registrant became the listed
# company (merger or reorganisation closed; New York date): rows of the old CIK accepted before it are kept, rows of
# the new CIK accepted before it are dropped (e.g. Upjohn's own 2020 results under Viatris's CIK while Mylan was
# the listed share).
PRED = {
    "apa":  [(6769, "apache", "2021-03-01")],      # Apache Corp -> APA Corp (holding company)
    "blk":  [(1364742, "blackrock", "2030-01-01")],  # BlackRock Inc (now 'BlackRock Finance, Inc.') -> new BlackRock (2024)
    "ci":   [(701221, "cigna", "2018-12-20")],      # Cigna Corp (now 'Cigna Holding Co') -> new Cigna (Express Scripts deal)
    "lin":  [(884905, "linde", "2018-10-31")],      # Praxair Inc (now 'LINDE INC') -> Linde plc
    "skyd": [(813828, "paramount", "2030-01-01")],  # CBS Corp / ViacomCBS / Paramount Global -> Skydance Corp (2025)
    "vtrs": [(1623613, "mylan", "2020-11-16")],     # Mylan N.V. (now 'Mylan II B.V.') -> Viatris
}

# Companies whose results 8-K is filed after the close (or before the open) although the release itself went out a
# session earlier, shown by the price witness (review D3-8, verifier's v_late2.py; re-checked by `test`, which
# requires every company it finds at p < 0.001 to be here). Their results rows that are NOT accepted in session get
# late_suspect = True: the stamp may be a session late. They are flagged, never moved; a run drops them
# (calendar(drop_late=True)). Early-peak share among their results rows not accepted in session (baseline 14 %):
LATE_STAMP = {
    "schw": "12 of 24 (8-Ks at about 16:30 New York; Schwab releases before the open)",
    "ato":  "12 of 24",
    "hal":  "6 of 9",
    "vmc":  "9 of 20",
}
# Hand picks of the results row (review D3-9), chosen from the filing pattern only (no price): PPL files its release
# at about 07:30 with items 2.02, 7.01 and 9.01, then a second 2.02 / 9.01 8-K (no 7.01) later; in 2018-2021 both
# fall on the same day, in 2016 and 2017 the second came 15-16 days later and took the fiscal-Q4 pick (L4 = 47 days).
HAND_RESULTS = {
    "0000922224-16-000121": "ppl Q4 2015 release 2016-02-04 07:35 (2.02, 7.01, 9.01), not the 2016-02-19 8-K",
    "0000922224-17-000007": "ppl Q4 2016 release 2017-02-01 07:18 (2.02, 7.01, 9.01), not the 2017-02-17 8-K",
    # Baxter's Q4 2019 release was delayed by an internal review; the 8-K that carries it also carries item 4.02
    # (non-reliance on earlier statements). The 2020-01-13 8-K (lag 13 days) is the preliminary figures.
    "0001193125-20-035710": "bax Q4 2019 release 2020-02-13 16:53 (2.02, 4.02, 7.01), not the 2020-01-13 preliminary",
}
MIN_FILE_DAYS = 15    # a 10-Q/10-K reportDate fewer days than this before its own acceptance is not a period end

# ---------------------------------------------------------------- universe
def universe():
    u = pd.read_csv(UNIVERSE, dtype={"cik": int})
    return u[u.in_universe.astype(str).str.lower() == "true"].reset_index(drop=True)

# ---------------------------------------------------------------- fetch (<= 4 requests a second, cached, filtered)
_last = [0.0]; _refused = [0]
class Stop(Exception): pass

def _get(url):
    for attempt in range(3):
        if _refused[0] >= 2:
            raise Stop(f"two refusals in a row from data.sec.gov (last url {url})")
        wait = 0.25 - (time.time() - _last[0])
        if wait > 0: time.sleep(wait)
        _last[0] = time.time()
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=ee.UA), timeout=60)
            j = json.loads(r.read()); _refused[0] = 0
            return j
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                _refused[0] += 1; time.sleep(5); continue
            if e.code >= 500 and attempt < 2:
                time.sleep(5); continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt < 2: time.sleep(5); continue
            raise
    raise Stop(f"two refusals in a row from data.sec.gov (last url {url})")

def _keep(block, i):
    f = block["filingDate"][i]; a = block["acceptanceDateTime"][i]; acc = block["accessionNumber"][i]
    if not (KEEP_FROM <= f <= CUT): return False
    if pd.Timestamp(a) >= CUT_TS: return False                       # acceptance instant (UTC)
    if int(acc.split("-")[1]) > 21: return False                     # re-filed later under an old date
    return block["form"][i] in FORMS_KEEP

def _refiled(block, i):
    """Counted only (no date stored): a record with an in-window filing date but accepted / numbered 2022 or later."""
    f = block["filingDate"][i]
    return KEEP_FROM <= f <= CUT and (pd.Timestamp(block["acceptanceDateTime"][i]) >= CUT_TS
                                      or int(block["accessionNumber"][i].split("-")[1]) > 21)

def _filter(block):
    n = len(block.get("filingDate", []))
    keep = [i for i in range(n) if _keep(block, i)]
    return {c: [block[c][i] for i in keep] for c in ee.COLS if c in block}, sum(_refiled(block, i) for i in range(n))

def fetch_cik(cik):
    out = os.path.join(RAW, f"CIK{cik:010d}.json")
    if os.path.exists(out): return out, False
    j = _get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    name = j.get("name", "")                         # today's name: only to check the CIK
    b, nref = _filter(j["filings"]["recent"]); blocks = [b]; extra = []
    for f in j["filings"].get("files", []):
        if f["filingTo"] >= KEEP_FROM and f["filingFrom"] <= CUT:
            b, n2 = _filter(_get("https://data.sec.gov/submissions/" + f["name"]))
            blocks.append(b); extra.append(f["name"]); nref += n2
    rows = {c: sum((b.get(c, []) for b in blocks), []) for c in ee.COLS}
    del j
    os.makedirs(RAW, exist_ok=True)
    tmp = out + ".tmp"
    json.dump({"cik": cik, "name_check": name, "extra_files": extra, "filings": rows, "refiled_dropped": nref,
               "kept": f"filingDate {KEEP_FROM}..{CUT}, accepted < 2022-01-01 UTC, accession year <= 21",
               "fetched_utc": pd.Timestamp.now("UTC").strftime("%Y-%m-%d")}, open(tmp, "w"))
    os.replace(tmp, out)                             # never a half-written cache file
    return out, True

def fetch():
    u = universe(); log = []
    for k, (key, cik, name) in enumerate(zip(u.key, u.cik, u.name)):
        try:
            p, new = fetch_cik(int(cik))
        except Stop as e:
            print(f"STOPPED at {key} (CIK {cik}), company {k + 1} of {len(u)}: {e}"); break
        except Exception as e:
            print(f"{key} CIK {cik}: ERROR {e!r}"); log.append((key, repr(e))); continue
        j = json.load(open(p))
        if new or k % 50 == 0:
            print(f"{k + 1:3d} {key:6s} CIK {cik:>8d} {j['name_check'][:38]:38s} rows {len(j['filings']['form']):5d}"
                  f" extra {len(j['extra_files'])} {'new' if new else 'cached'}", flush=True)
    for key, lst in PRED.items():
        for cik, word, _ in lst:
            try:
                p, new = fetch_cik(cik)
            except Stop as e:
                print(f"STOPPED at predecessor of {key}: {e}"); return
            nm = json.load(open(p))["name_check"]
            print(f"predecessor of {key}: CIK {cik} {nm} {'ok' if word in nm.lower() else 'NAME MISMATCH'}")
    n = sum(os.path.exists(os.path.join(RAW, f"CIK{int(c):010d}.json")) for c in u.cik)
    print(f"cache holds {n} of {len(u)} companies; errors {len(log)}")

# ---------------------------------------------------------------- clock helpers
def when_class(et):
    """before_open / in_session / after_close on the New York clock (13:00 close on NYSE half days); closed_day for
    an acceptance on a weekend or an NYSE holiday (no session that day, whatever the clock)."""
    if not ee.is_session(et.date()): return "closed_day"
    m = et.hour * 60 + et.minute + et.second / 60
    close = 780 if et.date() in HALF_DAYS else 960
    return "before_open" if m < 570 else ("in_session" if m < close else "after_close")

def reaction_session(ts):
    return ee.reaction_session(ts)                    # first session STARTING strictly after the acceptance time

def event_session(ts):
    """The session s with close(s-1) <= acceptance < close(s): the first session CLOSING after the acceptance. An
    8-K accepted at 16:00:00 exactly goes to the next session (the safe side of the closing print)."""
    et = ts.tz_convert(NY); d = et.date()
    while not ee.is_session(d): d = d + timedelta(days=1)
    close = pd.Timestamp(datetime(d.year, d.month, d.day, 13 if d in HALF_DAYS else 16, 0), tz=NY)
    if et >= close:
        d = d + timedelta(days=1)
        while not ee.is_session(d): d = d + timedelta(days=1)
    return d

# ---------------------------------------------------------------- build
def _filings_one(cik, raw=None):
    j = json.load(open(os.path.join(raw or RAW, f"CIK{cik:010d}.json")))
    d = pd.DataFrame(j["filings"], columns=ee.COLS); d["cik"] = cik
    return d

def _filings(cik, key=None):
    """Filings of the universe CIK, preceded by those of its predecessor registrants (PRED) accepted before it."""
    d = _filings_one(cik)
    for pc, _, cut in PRED.get(key, []):
        o = _filings_one(pc)
        t = pd.Timestamp(cut, tz=NY).tz_convert("UTC")
        d = pd.concat([o[pd.to_datetime(o.acceptanceDateTime, utc=True) < t],
                       d[pd.to_datetime(d.acceptanceDateTime, utc=True) >= t]], ignore_index=True)
    if d.empty: return d
    d = d.drop_duplicates("accessionNumber")
    d["accepted_utc"] = pd.to_datetime(d.acceptanceDateTime, utc=True, format="ISO8601")
    d = d[(d.accepted_utc < CUT_TS) & (d.filingDate <= CUT)]
    d["accepted_et"] = d.accepted_utc.dt.tz_convert(NY)
    d["items"] = d["items"].fillna("")
    return d.sort_values("accepted_utc").reset_index(drop=True)

def _flag_quarters(f, ev):
    """The earlier script's rule (earnings_edgar.build), per company. ev = the company's 8-K/8-K/A with item 2.02.
    Returns (ev with period_end, lag_days, quarter_flag; usual lag L; note)."""
    periodic = f[f.form.isin(PERIODIC)].copy()
    periodic["reportDate"] = periodic.reportDate.fillna("")
    # review D3-9: EDGAR sometimes gives the filing date as reportDate (HSIC 2016-2018, RJF 2017-08-08): a 'period
    # end' fewer than MIN_FILE_DAYS before its own acceptance is not one; the gap filling below replaces it
    ok_rd = periodic.reportDate != ""
    rdt = pd.to_datetime(periodic.reportDate.where(ok_rd, None))
    acc_d = periodic.accepted_et.dt.tz_localize(None).dt.normalize()
    bad_rd = ok_rd & ((acc_d - rdt).dt.days < MIN_FILE_DAYS)
    periodic.loc[bad_rd, "reportDate"] = ""
    rd = periodic.reportDate
    pe = sorted(set(pd.to_datetime(rd[rd != ""])))
    fy_ends = sorted(set(pd.to_datetime(periodic[periodic.form.isin({"10-K", "10-KT"}) & (rd != "")].reportDate)))
    ev = ev.copy(); ev["period_end"] = pd.NaT; ev["lag_days"] = np.nan; ev["quarter_flag"] = ""
    ev["fiscal_q4"] = False
    if not pe or ev.empty:
        return ev, np.nan, "no 10-Q/10-K period ends" if not pe else "no item 2.02"
    filled = [pe[0]]
    for x in pe[1:]:
        while (x - filled[-1]).days > 120:
            filled.append(filled[-1] + pd.Timedelta(days=91))
        filled.append(x)
    pe = filled
    while pe[-1] < pd.Timestamp(CUT) - pd.Timedelta(days=1):
        pe.append(pe[-1] + pd.Timedelta(days=91))
    pe = pd.DatetimeIndex(pe)
    acc_day = ev.accepted_et.dt.tz_localize(None).dt.normalize()
    pos = pe.searchsorted(acc_day, side="left") - 1
    ev["period_end"] = pd.to_datetime([pe[i] if i >= 0 else pd.NaT for i in pos]).values
    ev["lag_days"] = (acc_day - ev.period_end).dt.days
    def is_fy(p):        # fiscal year end: within 10 days (day of year, either side of New Year) of a 10-K period end
        for q in fy_ends:
            dd = (p.dayofyear - q.dayofyear) % 365
            if min(dd, 365 - dd) <= 10:
                return True
        return False
    lags, lags4 = [], []
    for _, r in periodic.iterrows():
        if not r.reportDate: continue
        c = ev[(ev.form != "8-K/A") & (ev.period_end == pd.Timestamp(r.reportDate)) & (ev.accepted_utc <= r.accepted_utc)]
        if len(c):
            (lags4 if r.form in ("10-K", "10-KT") else lags).append(c.lag_days.iloc[-1])
    ok = ev.period_end.notna()
    allg = lags + lags4
    L = float(pd.Series(allg).median()) if allg else (float(ev[ok].groupby("period_end").lag_days.min().median())
                                                      if ok.any() else np.nan)
    # review D3-9: the fiscal fourth quarter (10-K quarter) is released 45-60 days after year end at many companies,
    # later than the 10-Q quarters, so the pooled L picked a pre-announcement for it. Its own usual lag L4 = median,
    # over the company's fiscal fourth quarters, of the lag of the EARLIEST plain 8-K with item 2.02 accepted more
    # than 15 days after the year end (preliminary figures at January conferences come earlier; the last 2.02 before
    # the 10-K, used for L, is often a later investor update). Needs 2 such quarters, else L. The 10-Q quarters keep
    # the pooled L, unchanged; usual_lag reports L.
    fy = {p: is_fy(p) for p in ev[ok].period_end.unique()}
    ev.loc[ok, "fiscal_q4"] = ev.loc[ok, "period_end"].map(fy).astype(bool)
    q4l = []
    for p, g in ev[ok & ev.fiscal_q4].groupby("period_end"):
        c = g[(g.form == "8-K") & (g.lag_days > 15)]
        if len(c): q4l.append(c.lag_days.iloc[0])
    L4 = float(pd.Series(q4l).median()) if len(q4l) >= 2 else L
    Lq = L
    for p, g in ev[ok].groupby("period_end"):
        cand = g[g.form != "8-K/A"]
        if cand.empty:
            ev.loc[g.index, "quarter_flag"] = "amendment"; continue
        acc_d = cand.accepted_et.dt.strftime("%Y-%m-%d")
        follow = (cand.event_date < acc_d) & cand.event_date.isin(set(acc_d))
        pool = cand[~follow] if (~follow).any() else cand
        near = pool[(pool.lag_days - L).abs() <= max(2.0, min(7.0, 0.25 * L))]
        best = near.index[0] if len(near) else (pool.lag_days - L).abs().idxmin()      # the rule of section 30
        if fy[p] and L4 != L:
            # fiscal fourth quarter: the earliest row near L4, those carrying 9.01 (a press release) first; if no
            # row is near L4 the pick of the pooled rule stands
            n4 = pool[(pool.lag_days - L4).abs() <= max(2.0, min(7.0, 0.25 * L4))]
            if len(n4):
                w9 = n4[n4["items"].str.contains(r"\b9\.01\b")]
                best = (w9 if len(w9) else n4).index[0]
        hand = [i for i in g.index if g.at[i, "accessionNumber"] in HAND_RESULTS] if "accessionNumber" in g else []
        if hand:
            best = hand[0]
        for i in g.index:
            if i == best: ev.at[i, "quarter_flag"] = "results"
            elif ev.at[i, "form"] == "8-K/A": ev.at[i, "quarter_flag"] = "amendment"
            elif ev.at[i, "accepted_utc"] < ev.at[best, "accepted_utc"]: ev.at[i, "quarter_flag"] = "before_results"
            else: ev.at[i, "quarter_flag"] = "after_results"
    ev.loc[~ok, "quarter_flag"] = "no_period"
    return ev, L, ""

def _company_events(f):
    """Every 8-K / 8-K/A of one company from EV_FROM, with has_202 and the quarter flags of its 2.02 rows."""
    f = f.copy(); f["event_date"] = f.reportDate.fillna("")
    e8 = f[f.form.isin(EV_FORMS)].copy()
    e8["has_202"] = e8["items"].str.contains(r"\b2\.02\b")
    ev202, L, note = _flag_quarters(f, e8[e8.has_202])
    e8["period_end"] = pd.NaT; e8["lag_days"] = np.nan; e8["quarter_flag"] = ""; e8["fiscal_q4"] = False
    for c in ("period_end", "lag_days", "quarter_flag", "fiscal_q4"):
        e8.loc[ev202.index, c] = ev202[c]
    return e8[e8.accepted_utc >= EV_FROM].copy(), L, note

def crosscheck_lab40():
    """This file's code run on the earlier cache of the lab's 40 shares (~/explore_data/earnings/raw, read-only),
    compared with the verified calendar ~/explore_data/earnings/calendar.csv (Alibaba's 6-K and the 3 hand-added
    filings left out: this code has no such rules)."""
    old = pd.read_csv(os.path.join(ee.CACHE, "calendar.csv"), dtype=str)
    old = old[(old.form != "6-K") & ~old.accession.isin(ee.GAP_FILLS)]
    mine = []
    for t, lst in ee.CIKS.items():
        if t == "baba": continue
        fr = []
        for cik, _ in lst:
            d = _filings_one(cik, ee.RAW); fr.append(d)
        f = pd.concat(fr, ignore_index=True).drop_duplicates("accessionNumber")
        f["accepted_utc"] = pd.to_datetime(f.acceptanceDateTime, utc=True, format="ISO8601")
        f = f[(f.accepted_utc < CUT_TS) & (f.filingDate <= CUT)]
        f["accepted_et"] = f.accepted_utc.dt.tz_convert(NY); f["items"] = f["items"].fillna("")
        f = f.sort_values("accepted_utc").reset_index(drop=True)
        e8, L, _ = _company_events(f)
        e8 = e8[(e8.quarter_flag == "results") & (e8.accepted_et.dt.strftime("%Y-%m-%d") >= ee.START)]
        mine += list(e8.accessionNumber)
    a, b = set(old.accession), set(mine)
    # rows that only differ because the earlier calendar's hand-added filing (GAP_FILLS) took their quarter
    rawc = pd.read_csv(os.path.join(ee.CACHE, "calendar_raw.csv"), dtype=str)
    gp = set(zip(rawc[rawc.accession.isin(ee.GAP_FILLS)].ticker, rawc[rawc.accession.isin(ee.GAP_FILLS)].period_end))
    explained = set(rawc[[(t, q) in gp for t, q in zip(rawc.ticker, rawc.period_end)]].accession)
    return len(a), len(b), len(a & b), sorted(a - b), sorted(b - a), explained

def build(verbose=True):
    u = universe(); rows = []; per_rows = []; info = []
    for key, cik, name in zip(u.key, u.cik, u.name):
        p = os.path.join(RAW, f"CIK{int(cik):010d}.json")
        if not os.path.exists(p):
            info.append(dict(key=key, cik=cik, status="not fetched")); continue
        f = _filings(int(cik), key)
        forms = f.form.value_counts().to_dict() if len(f) else {}
        n8 = sum(v for k2, v in forms.items() if k2.startswith("8-K"))
        n6 = forms.get("6-K", 0) + forms.get("20-F", 0) + forms.get("40-F", 0)
        status = "foreign (6-K/20-F/40-F, no 8-K)" if (n6 and not n8) else ("ok" if n8 else "no 8-K in cache")
        if f.empty or not n8:
            info.append(dict(key=key, cik=cik, status=status, name_check=json.load(open(p))["name_check"])); continue
        per = f[f.form.isin(PERIODIC | {"10-Q/A", "10-K/A", "10-KT/A"})].copy(); per["key"] = key
        per_rows.append(per)
        e8, L, note = _company_events(f)
        e8["usual_lag"] = L; e8["key"] = key        # cik = the registrant that filed (predecessor or universe CIK)
        rows.append(e8)
        info.append(dict(key=key, cik=cik, status=status, name_check=json.load(open(p))["name_check"],
                         n_8k=len(e8), n_202=int(e8.has_202.sum()), n_results=int((e8.quarter_flag == "results").sum()),
                         usual_lag=L, first_8k=str(e8.accepted_et.min())[:10] if len(e8) else "",
                         first_filing_in_cache=str(f.filingDate.min()),
                         n_6k=n6, note=note, predecessor=";".join(f"{c} until {x}" for c, _, x in PRED.get(key, []))))
    ev = pd.concat(rows, ignore_index=True)
    ev["when"] = ev.accepted_et.map(when_class)
    ev["reaction_session"] = [reaction_session(x) for x in ev.accepted_utc]
    ev["event_session"] = [event_session(x) for x in ev.accepted_utc]
    ev["late_by_construction"] = ev["when"] == "in_session"        # reaction_session is one session after event_session
    ev = ev.rename(columns={"accessionNumber": "accession", "filingDate": "filing_date"})
    # results rows of the companies of LATE_STAMP not accepted in session: stamp possibly a session late (flag only)
    ev["late_suspect"] = ev.key.isin(set(LATE_STAMP)) & (ev.quarter_flag == "results") & (ev["when"] != "in_session")
    # EDGAR gives a filing date earlier than the New York acceptance date on a few rows (data error; kept, flagged)
    ev["filing_before_acceptance"] = ev.filing_date < ev.accepted_et.dt.strftime("%Y-%m-%d")
    per = pd.concat(per_rows, ignore_index=True).rename(columns={"accessionNumber": "accession",
                                                                  "filingDate": "filing_date", "reportDate": "period_end"})
    per["period_end"] = per.period_end.fillna("")
    pe_t = pd.to_datetime(per.period_end.where(per.period_end != "", None))
    per["period_end_ok"] = (per.period_end != "") & ((per.accepted_et.dt.tz_localize(None).dt.normalize() - pe_t).dt.days
                                                     >= MIN_FILE_DAYS)
    per["event_session"] = [event_session(x) for x in per.accepted_utc]
    # quarters without a results row: a non-2.02 8-K at the usual lag is a results CANDIDATE (review D3-10): it keeps
    # its own row, gets quarter_flag 'results_candidate', and is left out of kind='other' (it is results news)
    comp = pd.DataFrame(info)
    miss = _missing_quarters(ev, per, comp)
    cand = set(a for x in miss.candidate_8k for a in str(x).split(";") if a) if len(miss) else set()
    ev.loc[ev.accession.isin(cand) & ~ev.has_202, "quarter_flag"] = "results_candidate"
    cols = ["key", "cik", "accession", "accepted_utc", "accepted_et", "filing_date", "form", "items", "when",
            "event_session", "reaction_session", "has_202", "quarter_flag", "period_end", "fiscal_q4", "lag_days",
            "usual_lag", "late_by_construction", "late_suspect", "filing_before_acceptance", "event_date",
            "primaryDocument"]
    ev = ev[cols].sort_values(["key", "accepted_utc"]).reset_index(drop=True)
    assert ev.accepted_utc.max() < CUT_TS and ev.filing_date.max() <= CUT and ev.accepted_utc.min() >= EV_FROM
    assert (pd.to_datetime(ev.event_session) <= pd.Timestamp("2022-01-03")).all()
    os.makedirs(OUT, exist_ok=True)
    w = ev.copy()
    w["accepted_utc"] = w.accepted_utc.dt.strftime("%Y-%m-%d %H:%M:%S+00:00")
    w["accepted_et"] = w.accepted_et.dt.strftime("%Y-%m-%d %H:%M:%S%z")
    w["period_end"] = pd.to_datetime(w.period_end).dt.strftime("%Y-%m-%d")
    w.to_csv(os.path.join(OUT, "events_raw.csv"), index=False)
    per["accepted_utc"] = per.accepted_utc.dt.strftime("%Y-%m-%d %H:%M:%S+00:00")
    per[["key", "cik", "form", "accession", "period_end", "period_end_ok", "accepted_utc", "filing_date",
         "event_session"]].to_csv(os.path.join(OUT, "periodic.csv"), index=False)
    comp.to_csv(os.path.join(OUT, "companies.csv"), index=False)
    miss.to_csv(os.path.join(OUT, "results_missing_quarters.csv"), index=False)
    ns = _news_sessions(ev, per)
    ns.to_csv(os.path.join(OUT, "news_sessions.csv"), index=False)
    if verbose:
        print(f"events_raw.csv: {len(ev)} 8-K rows, {ev.key.nunique()} companies, item 2.02 {int(ev.has_202.sum())}, "
              f"results {int((ev.quarter_flag == 'results').sum())}, candidates {int((ev.quarter_flag == 'results_candidate').sum())}; "
              f"periodic.csv {len(per)} rows; news_sessions.csv {len(ns)} share-sessions; companies.csv")
        print(comp.status.value_counts().to_string())
    return ev

def _missing_quarters(ev, per, comp):
    """Fiscal quarters (a 10-Q/10-K with a valid period end) whose release is expected after the company's first 8-K
    of the table and that have no 'results' row; a non-2.02 8-K within the usual-lag tolerance is listed as candidate."""
    miss = []
    res = ev[ev.quarter_flag == "results"]
    lag = comp.set_index("key").usual_lag if "usual_lag" in comp else pd.Series(dtype=float)
    perq = per[per.form.isin(["10-Q", "10-K", "10-KT"]) & per.period_end_ok]
    for k, g in perq.groupby("key"):
        L = lag.get(k)
        if L is None or pd.isna(L): continue
        rk = res[res.key == k]; ek = ev[ev.key == k]
        if ek.empty: continue
        f8 = ek.accepted_utc.min()
        have_pe = set(pd.to_datetime(rk.period_end).dt.date)
        o = ek[~ek.has_202]
        olag = (o.accepted_et.dt.tz_localize(None).dt.normalize() - pd.Timestamp(0)).dt.days
        for pe_s, gg in g.groupby("period_end"):
            pe_d = pd.Timestamp(pe_s)
            expect = pd.Timestamp(pe_d.date() + timedelta(days=int(L)), tz="UTC")
            if expect < f8 or expect < EV_FROM or pe_d.date() in have_pe: continue
            lg = olag - (pe_d - pd.Timestamp(0)).days
            tol = max(2.0, min(7.0, 0.25 * L))
            c = o[(lg - L).abs() <= tol]
            miss.append(dict(key=k, period_end=pe_s, periodic_form=gg.form.iloc[0],
                             periodic_accepted_utc=gg.accepted_utc.min().strftime("%Y-%m-%d %H:%M"),
                             periodic_event_session=str(gg.event_session.min()),
                             usual_lag=L, candidate_8k=";".join(c.accession), candidate_items=";".join(c["items"]),
                             candidate_accepted_et=";".join(c.accepted_et.dt.strftime("%Y-%m-%d %H:%M"))))
    cols = ["key", "period_end", "periodic_form", "periodic_accepted_utc", "periodic_event_session", "usual_lag",
            "candidate_8k", "candidate_items", "candidate_accepted_et"]
    return pd.DataFrame(miss, columns=cols)

def _news_sessions(ev, per):
    """One row per (key, session) on which anything was filed, by event_session (and the reaction_session of results
    rows accepted in session). Columns count or flag what fell on that session; see sources.md section 31."""
    ev = ev.copy(); ev["s"] = pd.to_datetime(ev.event_session)
    is_res = ev.quarter_flag == "results"
    oth = ~ev.has_202 & (ev.quarter_flag != "results_candidate")
    parts = {
        "n_8k_other": ev[oth & (ev.form == "8-K")].groupby(["key", "s"]).size(),
        "n_8ka_other": ev[oth & (ev.form == "8-K/A")].groupby(["key", "s"]).size(),
        "n_8k_202": ev[ev.has_202].groupby(["key", "s"]).size(),
        "n_8k_all": ev.groupby(["key", "s"]).size(),
        "results_event": ev[is_res].groupby(["key", "s"]).size(),
        "results_late_suspect": ev[is_res & ev.late_suspect].groupby(["key", "s"]).size(),
        "results_candidate": ev[ev.quarter_flag == "results_candidate"].groupby(["key", "s"]).size(),
    }
    rr = ev[is_res].assign(s=pd.to_datetime(ev[is_res].reaction_session))
    parts["results_reaction"] = rr.groupby(["key", "s"]).size()
    p = per.copy(); p["s"] = pd.to_datetime(p.event_session)
    parts["periodic"] = p.groupby(["key", "s"]).size()
    t = pd.concat(parts, axis=1).fillna(0).astype(int)
    for c in ("results_event", "results_late_suspect", "results_candidate", "results_reaction", "periodic"):
        t[c] = t[c] > 0
    t.index.names = ["key", "session"]
    t = t.reset_index()
    t["session"] = t.session.dt.strftime("%Y-%m-%d")
    return t[(t.session >= "2016-01-01")].sort_values(["key", "session"]).reset_index(drop=True)

# ---------------------------------------------------------------- the function a run uses
def calendar(end=CUT, kind="results", drop_late=False, drop_in_session=False, path=None):
    """8-K events accepted on or before `end` (a UTC instant; a bare date = the end of that UTC day; never after
    2021-12-31 23:59:59 UTC).
    kind='results': one row per fiscal quarter (the 8-K with item 2.02 flagged 'results');
    kind='other'  : 8-K / 8-K/A rows WITHOUT item 2.02, minus the 'results_candidate' rows (results news filed
                    without item 2.02, review D3-10);   kind='all': every row.
    The event day of every row is `event_session` (first session CLOSING after the acceptance; see the module text).
    drop_late=True drops the rows whose stamp may be a session late and cannot be shown safe (late_suspect: the
    companies of LATE_STAMP). drop_in_session=True also drops the rows accepted inside a session (the earlier
    drop_late; a sensitivity check only: their event_session is the right day). No row is ever moved earlier."""
    path = path or os.path.join(OUT, "events_raw.csv")
    d = pd.read_csv(path, dtype={"items": str, "event_date": str, "accession": str})
    d["items"] = d["items"].fillna("")
    d["accepted_utc"] = pd.to_datetime(d.accepted_utc, utc=True)
    d["accepted_et"] = d.accepted_utc.dt.tz_convert(NY)
    for c in ("event_session", "reaction_session", "period_end", "filing_date"):
        d[c] = pd.to_datetime(d[c])
    e = pd.Timestamp(end)
    e = e.tz_localize("UTC") if e.tzinfo is None else e.tz_convert("UTC")
    if len(str(end)) <= 10: e = e + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    e = min(e, pd.Timestamp(CUT + " 23:59:59", tz="UTC"))
    d = d[d.accepted_utc <= e]
    if kind == "results": d = d[d.quarter_flag == "results"]
    elif kind == "other": d = d[~d.has_202 & (d.quarter_flag != "results_candidate")]
    elif kind != "all": raise ValueError(kind)
    if drop_late: d = d[~d.late_suspect]
    if drop_in_session: d = d[~d.late_by_construction]
    return d.reset_index(drop=True)

def sessions(y0=2015, y1=2022):
    """NYSE sessions (dates) from the hand holiday list of earnings_edgar (checked against the rules by `test`)."""
    return [d.date() for d in pd.bdate_range(f"{y0}-12-01" if y0 == 2015 else f"{y0}-01-01", f"{y1}-01-31")
            if ee.is_session(d.date())]

def news_sessions(path=None):
    """news_sessions.csv: one row per (key, session) with any filing; session = event_session (results rows accepted
    in session also mark their reaction_session, column results_reaction)."""
    t = pd.read_csv(path or os.path.join(OUT, "news_sessions.csv"))
    t["session"] = pd.to_datetime(t.session).dt.date
    return t

def idea_sessions(idea, include_amend=False, results_ahead=2, window=True, path=None):
    """The share-sessions of the lead's ideas, read one way and written down here so that every run reads them the
    same way (review D3-4). One row per (key, session). 'results-like' sessions X of a share = sessions with a results
    row (event_session or reaction_session), any other 8-K with item 2.02 (pre-announcements, updates, amendments),
    a results candidate (results without 2.02) or a 10-Q / 10-K acceptance (event_session).
      '059': results rows, session = event_session, late_suspect rows dropped (columns: accession, when).
      '061': sessions s with a plain 8-K without 2.02 (also an 8-K/A if include_amend), and neither s nor s-1 in X.
      '062': sessions s with no 8-K / 8-K/A of any kind and no 10-Q / 10-K whose event_session is s-2, s-1 or s
             (accepted at or after the close of s-3 and before the close of s), and no X session in s-2..s+k with
             k = results_ahead (the lead's text: 2; NOTE: k > 0 looks at results sessions AFTER s, known at s only
             when the company announced the date: a run should say so or set results_ahead=0).
    window=True keeps sessions from the share's in_universe_from to 2021-12-31 (and from 2017-01-01)."""
    ns = news_sessions(path and os.path.join(os.path.dirname(path), "news_sessions.csv"))
    u = universe(); frm = dict(zip(u.key, pd.to_datetime(u.in_universe_from).dt.date))
    S = sessions(); idx = {d: i for i, d in enumerate(S)}
    xmask = ns.results_event | ns.results_reaction | (ns.n_8k_202 > 0) | ns.results_candidate | ns.periodic
    X = {}
    for k, s in zip(ns.key[xmask], ns.session[xmask]): X.setdefault(k, set()).add(idx[s])
    lo, hi = date(2017, 1, 1), date(2021, 12, 31)
    def inwin(k, s): return (not window) or (max(frm.get(k, hi), lo) <= s <= hi)
    if idea == "059":
        r = calendar(kind="results", drop_late=True, path=path)
        r["session"] = r.event_session.dt.date
        r = r[[inwin(k, s) for k, s in zip(r.key, r.session)]]
        return r[["key", "session", "accession", "when", "accepted_et"]].reset_index(drop=True)
    if idea == "061":
        n = ns.n_8k_other + (ns.n_8ka_other if include_amend else 0)
        c = ns[n > 0]
        keep = [(k, s) for k, s in zip(c.key, c.session)
                if inwin(k, s) and idx[s] not in X.get(k, ()) and idx[s] - 1 not in X.get(k, ())]
        return pd.DataFrame(keep, columns=["key", "session"])
    if idea == "062":
        anyf = {}
        m = (ns.n_8k_all > 0) | ns.periodic
        for k, s in zip(ns.key[m], ns.session[m]): anyf.setdefault(k, set()).add(idx[s])
        out = []
        for k in u.key:
            a, x = anyf.get(k, set()), X.get(k, set())
            for s in S:
                if not inwin(k, s): continue
                i = idx[s]
                if a & {i - 2, i - 1, i}: continue
                if x & set(range(i - 2, i + results_ahead + 1)): continue
                out.append((k, s))
        return pd.DataFrame(out, columns=["key", "session"])
    raise ValueError(idea)

# ---------------------------------------------------------------- independent session calendar (for the test)
def _nth_weekday(y, m, wd, n):
    d = date(y, m, 1); d += timedelta(days=(wd - d.weekday()) % 7); return d + timedelta(weeks=n - 1)
def _last_weekday(y, m, wd):
    d = date(y, m + 1, 1) - timedelta(days=1); return d - timedelta(days=(d.weekday() - wd) % 7)
def _easter(y):
    a = y % 19; b, c = divmod(y, 100); d, e = divmod(b, 4); g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30; j, k = divmod(c, 4); m = (a + 11 * h) // 319
    r = (2 * e + 2 * j - k - h + m + 32) % 7; n = (h - m + r + 90) // 25; p = (h - m + r + n + 19) % 32
    return date(y, n, p)
def _observed(d, newyear=False):
    if d.weekday() == 5: return None if newyear else d - timedelta(days=1)   # NYSE: no Friday close for Sat 1 Jan
    if d.weekday() == 6: return d + timedelta(days=1)
    return d
def rule_holidays(y0=2015, y1=2022):
    """NYSE closures from the exchange's rules (not from the hand list), plus the one special closure of the period."""
    h = set()
    for y in range(y0, y1 + 1):
        for d in (_observed(date(y, 1, 1), True), _nth_weekday(y, 1, 0, 3), _nth_weekday(y, 2, 0, 3),
                  _easter(y) - timedelta(days=2), _last_weekday(y, 5, 0), _observed(date(y, 7, 4)),
                  _nth_weekday(y, 9, 0, 1), _nth_weekday(y, 11, 3, 4), _observed(date(y, 12, 25))):
            if d: h.add(d)
    h.add(date(2018, 12, 5))      # national day of mourning (President G.H.W. Bush)
    return h

def rule_sessions(y0=2015, y1=2022):
    hol = rule_holidays(y0, y1); out = []
    d = date(y0, 1, 1)
    while d <= date(y1, 1, 31):
        if d.weekday() < 5 and d not in hol: out.append(d)
        d += timedelta(days=1)
    return out

def reaction_session_independent(accepted_utc_strings):
    """Second piece of code: session opens as epoch seconds via zoneinfo, then first open > acceptance."""
    ny = ZoneInfo(NY)
    sess = rule_sessions()
    opens = np.array([datetime(d.year, d.month, d.day, 9, 30, tzinfo=ny).timestamp() for d in sess])
    acc = np.array([datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
                    for s in accepted_utc_strings])
    i = np.searchsorted(opens, acc, side="right")
    return [sess[k] for k in i]

def event_session_independent(accepted_utc_strings):
    """Second piece of code for event_session: session closes (16:00, 13:00 on half days) as epoch seconds via
    zoneinfo from the rule-based calendar, then the first close strictly after the acceptance."""
    ny = ZoneInfo(NY)
    sess = rule_sessions()
    closes = np.array([datetime(d.year, d.month, d.day, 13 if d in HALF_DAYS else 16, 0, tzinfo=ny).timestamp()
                       for d in sess])
    acc = np.array([datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
                    for s in accepted_utc_strings])
    i = np.searchsorted(closes, acc, side="right")
    return [sess[k] for k in i]

def _q4_preannouncement_picks(allr, per):
    """The verifier's v_q4pick test: fiscal fourth quarters (period end in the company's usual 10-K month) whose
    'results' row is 14+ days before a later plain 8-K 2.02 row of the same quarter at a 40-80 day lag, the pick's own
    lag being under 40 days."""
    tenk = per[per.form.str.startswith("10-K") & (per.period_end.fillna("") != "")].copy()
    tenk["m"] = tenk.period_end.str[5:7]
    km = tenk.groupby("key").m.agg(lambda s: s.mode().iloc[0]).to_dict()
    r = allr[allr.quarter_flag == "results"]
    a = allr[(allr.quarter_flag == "after_results") & (allr.form == "8-K")]
    m = a.merge(r, on=["key", "period_end"], suffixes=("", "_pick"))
    if m.empty: return m
    m["gap"] = (m.accepted_utc - m.accepted_utc_pick).dt.total_seconds() / 86400
    m["q4"] = [p.strftime("%m") == km.get(k) for k, p in zip(m.key, m.period_end)]
    s = m[m.q4 & (m.gap >= 14) & m.lag_days.between(40, 80) & (m.lag_days_pick < 40)]
    return s.sort_values("accepted_utc").drop_duplicates(["key", "period_end"])

# ---------------------------------------------------------------- checks, counts, witness
def test():
    out_lines = []
    def say(s=""):
        print(s); out_lines.append(s)
    n = [0]
    def ok(cond, msg):
        assert cond, msg; n[0] += 1; say(f"ok  {msg}")
    u = universe()
    comp = pd.read_csv(os.path.join(OUT, "companies.csv"))
    raw_csv = pd.read_csv(os.path.join(OUT, "events_raw.csv"), dtype=str)
    allr = calendar(kind="all"); res = calendar(kind="results")
    say(f"universe {len(u)} companies; companies.csv status: {comp.status.value_counts().to_dict()}")

    # 1. nothing at or after 2022-01-01 anywhere (cache + tables)
    bad = 0; nfiles = 0; nrows = 0
    for fn in os.listdir(RAW):
        if not fn.endswith(".json"): continue
        j = json.load(open(os.path.join(RAW, fn))); fl = j["filings"]; nfiles += 1
        for a, fd, acc in zip(fl["acceptanceDateTime"], fl["filingDate"], fl["accessionNumber"]):
            nrows += 1
            bad += (pd.Timestamp(a) >= CUT_TS) or fd > CUT or int(acc.split("-")[1]) > 21
    ok(bad == 0, f"cache: {nfiles} files, {nrows} rows, none accepted/filed/numbered 2022 or later")
    per = pd.read_csv(os.path.join(OUT, "periodic.csv"), dtype=str)
    ok((pd.to_datetime(allr.accepted_utc) < CUT_TS).all() and (allr.filing_date <= CUT).all()
       and (pd.to_datetime(per.accepted_utc, utc=True) < CUT_TS).all() and (per.filing_date <= CUT).all(),
       "tables: no acceptance or filing date after 2021-12-31")
    ok(allr.accession.is_unique, f"one row per 8-K ({len(allr)} rows)")
    ok(not res.groupby(["key", "period_end"]).size().gt(1).any(), "one 'results' per company and fiscal quarter")
    # cut
    c2 = calendar("2019-06-30", kind="all")
    ok(c2.accepted_utc.max() <= pd.Timestamp("2019-06-30 23:59:59", tz="UTC") and len(c2) < len(allr), "cut at end")
    c3 = calendar("2030-01-01", kind="all"); ok(len(c3) == len(allr), "end after 2021 is capped at 2021-12-31")

    na, nb, nab, only_old, only_new, expl = crosscheck_lab40()
    say(f"    same code on the lab's 40 (earlier cache): verified calendar {na} results rows (6-K and hand-added left "
        f"out), this code {nb}, common {nab}; only in the verified one {only_old}; only here {only_new} "
        f"(in a quarter the verified calendar filled by hand: {set(only_new) <= expl})")
    ok(nab == na and not only_old and set(only_new) <= expl,
       "this code reproduces the verified results calendar of the lab's 40 shares")
    # 2. reaction session: second, independent code (rule-based holidays, zoneinfo, epoch search)
    rs2 = reaction_session_independent(raw_csv.accepted_utc.tolist())
    diff = sum(str(a) != b for a, b in zip(rs2, raw_csv.reaction_session))
    ok(diff == 0, f"reaction session recomputed independently: {diff} of {len(raw_csv)} rows differ")
    # review D3-3/D3-4: event_session recomputed by the second calendar (first close strictly after acceptance)
    es2 = event_session_independent(raw_csv.accepted_utc.tolist())
    diff = sum(str(a) != b for a, b in zip(es2, raw_csv.event_session))
    ok(diff == 0, f"event session recomputed independently: {diff} of {len(raw_csv)} rows differ")
    ndiff = int((allr.event_session != allr.reaction_session).sum())
    ok(((allr.event_session != allr.reaction_session) == (allr["when"] == "in_session")).all(),
       f"event_session differs from reaction_session exactly on the {ndiff} rows accepted inside a session")
    ok((allr.event_session <= allr.reaction_session).all() and
       (pd.to_datetime(allr.event_session.astype(str) + " 16:00").dt.tz_localize(NY) >= allr.accepted_et).all(),
       "event_session closes at or after the acceptance, never after the reaction session")
    # review D3-11: 'when' only on session days
    cd = allr[allr["when"] == "closed_day"]
    ok(cd.accepted_et.dt.date.map(ee.is_session).eq(False).all() and
       allr[allr["when"] != "closed_day"].accepted_et.dt.date.map(ee.is_session).all(),
       f"when = closed_day exactly on the {len(cd)} rows accepted on a weekend or holiday; no in_session on them")
    fba = allr[allr.filing_before_acceptance]
    say(f"    rows whose filing date is before the New York acceptance date (EDGAR data error, flagged): {len(fba)}: "
        + ", ".join(f"{r.key} {r.accepted_et:%Y-%m-%d} {r.form} filed {r.filing_date:%Y-%m-%d}" for r in fba.itertuples()))
    # review D3-9: fiscal fourth quarters and the period-end clean-up
    r2 = res.set_index("accession")
    ok(all(a in r2.index for a in HAND_RESULTS), f"the {len(HAND_RESULTS)} hand picks (HAND_RESULTS) are results rows")
    bad_pick = allr[allr.accession.isin(["0000720005-17-000070", "0001193125-18-262474"])]  # RJF 2017-09-01, HSIC 2018-08-30
    hs = res[res.key == "hsic"]
    ok(len(bad_pick) == 2 and (bad_pick.quarter_flag != "results").all() and
       ((hs.lag_days >= 20) & (hs.lag_days <= 60)).all(),
       "review D3-9: RJF 2017-09-01 and HSIC 2018-08-30 are not results; every HSIC results lag is 20-60 days "
       f"(range {hs.lag_days.min():.0f}-{hs.lag_days.max():.0f})")
    q4 = _q4_preannouncement_picks(allr, per)
    say(f"    fiscal fourth quarters whose results pick precedes by 14+ days a later plain 2.02 8-K at a 40-80 day lag "
        f"(verifier's v_q4pick test; 37 before the fix): {len(q4)}: " +
        ", ".join(f"{r.key} {r.period_end:%Y-%m}" for r in q4.itertuples()))
    ok(len(q4) <= 16, "fiscal-Q4 pre-announcement picks down from 37 to at most 16 (read one by one in sources.md)")
    nb = int(((per.period_end_ok == "False") & (per.period_end.fillna("") != "")).sum())
    say(f"    10-Q/10-K rows whose reportDate is fewer than {MIN_FILE_DAYS} days before their acceptance (not a period "
        f"end, replaced by the 91-day filling): {nb}")
    hand = {d for d in ee.NYSE_HOLIDAYS if date(2016, 1, 1) <= d <= date(2021, 12, 31)}
    rule = {d for d in rule_holidays() if date(2016, 1, 1) <= d <= date(2021, 12, 31)}
    ok(hand == rule, f"hand holiday list = rule-based list 2016-2021 ({len(rule)} closures)")
    rs = pd.to_datetime(allr.reaction_session.astype(str) + " 09:30").dt.tz_localize(NY)
    ok((rs > allr.accepted_et).all() and ((rs - allr.accepted_et) < pd.Timedelta(days=6)).all(),
       "reaction session opens after acceptance, within 6 days")
    # half days
    hd = allr[allr.accepted_et.dt.date.isin(HALF_DAYS)]
    hm = hd.accepted_et.dt.hour * 60 + hd.accepted_et.dt.minute
    say(f"    rows accepted on 13:00 half days: {len(hd)}; of those 13:00-16:00 New York: {int(((hm >= 780) & (hm < 960)).sum())}"
        f" (all labelled after_close: {bool((hd[(hm >= 780) & (hm < 960)].when == 'after_close').all())})")

    # 3. summer / winter release clocks (the earlier verifier's test)
    r = res.copy()
    r["dst"] = r.accepted_et.map(lambda x: bool(x.dst()))
    r["ny_min"] = r.accepted_et.dt.hour * 60 + r.accepted_et.dt.minute
    r["alt_min"] = r.accepted_utc.dt.hour * 60 + r.accepted_utc.dt.minute   # other reading: the Z time as New York time
    agree_utc = agree_alt = tot = 0
    for k, g in r.groupby("key"):
        for side in ("before", "after"):
            gg = g[(g.when == "before_open") if side == "before" else (g.when == "after_close")]
            s, w = gg[gg.dst], gg[~gg.dst]
            if len(s) >= 3 and len(w) >= 3:
                tot += 1
                agree_utc += abs(s.ny_min.median() - w.ny_min.median()) <= 20
                agree_alt += abs(s.alt_min.median() - w.alt_min.median()) <= 20
    say(f"    summer/winter clocks (company x side with >= 3 releases in each season): {tot}; agree within 20 min: "
        f"UTC reading {agree_utc}, other reading {agree_alt}")
    ok(agree_utc >= 0.8 * tot and agree_alt <= 0.2 * tot, "release clocks agree across seasons only under UTC")
    # filing-date rule: accepted after 17:30 New York -> filing_date is a later business day
    a = allr.copy(); m = a.accepted_et.dt.hour * 60 + a.accepted_et.dt.minute
    late = a[m >= 17 * 60 + 31]; same = a[m < 17 * 60 + 25]
    f_late = (late.filing_date.dt.date > late.accepted_et.dt.date).mean()
    f_same = (same.filing_date.dt.date == same.accepted_et.dt.date).mean()
    say(f"    filing-date rule: after 17:31 NY filing date later than acceptance date {f_late:.4f} of {len(late)}; "
        f"before 17:25 same day {f_same:.4f} of {len(same)}")
    exc = late[late.filing_date.dt.date <= late.accepted_et.dt.date]
    say(f"    exceptions (accepted after 17:31 NY, same filing date; EDGAR extended-hours days): {len(exc)}, "
        f"on {exc.accepted_et.dt.date.nunique()} days")
    # the other reading (the Z clock taken as New York time) would put most 'late' rows before 17:30
    alt = a.accepted_utc.dt.hour * 60 + a.accepted_utc.dt.minute
    say(f"    under the other reading, rows whose filing date is a later day but whose clock is before 17:25: "
        f"{int(((alt < 17 * 60 + 25) & (a.filing_date.dt.date > a.accepted_et.dt.date)).sum())}; under UTC: "
        f"{int(((m < 17 * 60 + 25) & (a.filing_date.dt.date > a.accepted_et.dt.date)).sum())}")
    ok(f_late > 0.9 and f_same > 0.98, "EDGAR filing-date rule holds under the UTC reading")

    # 4. results per company and year; spacing
    res["year"] = res.accepted_et.dt.year
    cy = res.groupby(["key", "year"]).size().unstack(fill_value=0)
    say("\nresults rows per company and year: distribution (companies with that count)")
    for y in cy.columns:
        say(f"    {y}: " + ", ".join(f"{c}:{v}" for c, v in cy[y].value_counts().sort_index().items()))
    odd = []
    uu = u.set_index("key")
    for k, row in cy.iterrows():
        f8 = allr[allr.key == k].accepted_et.min()
        for y, v in row.items():
            if 3 <= v <= 5: continue
            odd.append(dict(key=k, year=y, n=v, first_8k_in_cache=str(f8)[:10]))
    odd = pd.DataFrame(odd)
    odd.to_csv(os.path.join(OUT, "check_results_per_year.csv"), index=False)
    say(f"company-years with fewer than 3 or more than 5 results rows: {len(odd)} "
        f"(of {cy.size}); list in check_results_per_year.csv")
    res = res.sort_values(["key", "accepted_utc"])
    gap = res.groupby("key").accepted_utc.diff().dt.days
    gg = gap.dropna()
    say(f"consecutive results 60-120 days apart: {int(gg.between(60, 120).sum())} of {len(gg)} ({gg.between(60, 120).mean():.3f});"
        f" < 60: {int((gg < 60).sum())}, > 120: {int((gg > 120).sum())}")
    res.assign(gap_days=gap)[~gap.between(60, 120) & gap.notna()][["key", "accepted_et", "gap_days", "lag_days",
        "usual_lag", "items", "accession"]].to_csv(os.path.join(OUT, "check_results_gaps.csv"), index=False)
    # fiscal quarters without a results row (results filed with the 10-Q only, or without item 2.02): built by
    # `build` (_missing_quarters); their non-2.02 8-Ks at the usual lag carry quarter_flag 'results_candidate'
    miss = pd.read_csv(os.path.join(OUT, "results_missing_quarters.csv"), dtype=str, keep_default_na=False)
    say(f"fiscal quarters (10-Q/10-K with a valid period end, release expected after the company's first 8-K) with no "
        f"results row: {len(miss)} at {miss.key.nunique() if len(miss) else 0} companies; with a non-2.02 8-K at the usual "
        f"lag (results_candidate): {int((miss.candidate_8k != '').sum()) if len(miss) else 0}; list in results_missing_quarters.csv")
    if len(miss):
        say("    by company: " + str(miss.key.value_counts().to_dict()))
    cand = set(x for c in miss.candidate_8k for x in c.split(";") if x)
    ok(set(allr[allr.quarter_flag == "results_candidate"].accession) == cand and not (allr[allr.accession.isin(cand)].has_202).any()
       and not calendar(kind="other").accession.isin(cand).any(),
       f"the {len(cand)} results candidates carry quarter_flag results_candidate and are out of kind='other'")
    ffc = comp.set_index("key").first_filing_in_cache.astype(str)
    def reason(r):
        ff = ffc.get(r.key, "")
        if r.n > 5: return "more than 5: fiscal calendar (52/53-week year or quarter ends early in the month)"
        if ff[:4] > str(r.year): return "registrant had not yet filed (spin-off / new company)"
        # the cache starts with filings of 2015-06-01: a first filing after 2015-07-15 is a new registrant
        if ff[:4] == str(r.year) and ff > KEEP_FROM[:4] + "-07-15": return "registrant's first year"
        if r.first_8k_in_cache[:4] > str(r.year): return "registrant had not yet filed an 8-K (new registrant)"
        if len(miss) and ((miss.key == r.key) & (pd.to_datetime(miss.period_end).dt.year.isin([r.year, r.year - 1]))).any():
            return "quarters without a results 8-K (see results_missing_quarters.csv)"
        return "other: see check_results_gaps.csv"
    if len(odd):
        odd["reason"] = odd.apply(reason, axis=1)
        odd.to_csv(os.path.join(OUT, "check_results_per_year.csv"), index=False)
        say("    company-years outside 3-5, by reason: " + str(odd.reason.value_counts().to_dict()))
        fy = odd[odd.key.isin(["algn", "lly"]) & (odd.year == 2016)]
        ok(len(fy) == 0 or (fy.reason != "registrant's first year").all(),
           "review D3-10: ALGN and LLY 2016 are not called the registrant's first year "
           f"({fy[['key', 'reason']].values.tolist()})")
    # without item 2.02 at all / L
    c_ok = comp[comp.status == "ok"]
    say(f"companies with no item-2.02 8-K at all: {int((c_ok.n_202 == 0).sum())}: {c_ok[c_ok.n_202 == 0].key.tolist()}")

    # 5. flags
    raw202 = allr[allr.has_202]
    say(f"\nitem-2.02 rows {len(raw202)}: " + str(raw202.quarter_flag.value_counts().to_dict()))
    say(f"results rows by when: {res['when'].value_counts().to_dict()}; late_by_construction (in_session): "
        f"{int(res.late_by_construction.sum())} results rows, {int(allr.late_by_construction.sum())} rows in all")
    ins = res[res.late_by_construction].groupby("key").size().sort_values(ascending=False)
    say(f"companies with results accepted inside the session: {len(ins)}; with 4 or more: "
        f"{ins[ins >= 4].to_dict()}")
    dev = (res.lag_days - res.usual_lag).abs()
    say(f"results rows more than 21 days from the company's usual lag: {int((dev > 21).sum())} (fiscal fourth quarters "
        f"among them: {int((res.fiscal_q4 & (dev > 21)).sum())})")
    say(f"rows by when: {allr['when'].value_counts().to_dict()}")
    ls = res[res.late_suspect]
    say(f"late_suspect (results rows of {sorted(LATE_STAMP)} not accepted in session, a run drops them): {len(ls)} "
        f"{ls.key.value_counts().to_dict()}; calendar(kind='results', drop_late=True) keeps "
        f"{len(calendar(kind='results', drop_late=True))} of {len(res)}")
    ok(set(ls.key) <= set(LATE_STAMP) and (ls["when"] != "in_session").all(), "late_suspect only on LATE_STAMP companies")

    # 6. counts for the lead's ideas (no return)
    say("\nresults rows by year: " + str(res.year.value_counts().sort_index().to_dict()))
    oth = allr[~allr.has_202].copy(); oth["year"] = oth.accepted_et.dt.year
    say(f"8-K rows without item 2.02: {len(oth)}; by year: {oth.year.value_counts().sort_index().to_dict()}")
    it = oth.assign(item=oth["items"].str.split(",")).explode("item")
    it["item"] = it["item"].str.strip(); it = it[it.item != ""]
    tab = it.groupby(["item", "year"]).size().unstack(fill_value=0)
    tab["total"] = tab.sum(axis=1); tab = tab.sort_values("total", ascending=False)
    tab.to_csv(os.path.join(OUT, "counts_other_by_item_year.csv"))
    say("8-K rows without 2.02, by item (a row with several items counts once per item):")
    say(tab.head(16).to_string())
    ed = pd.to_datetime(oth.event_date, errors="coerce")
    dl = (oth.accepted_et.dt.tz_localize(None).dt.normalize() - ed).dt.days
    bd = pd.Series([np.busday_count(a.date(), b.date()) if pd.notna(a) else np.nan
                    for a, b in zip(ed, oth.accepted_et.dt.tz_localize(None))], index=oth.index)
    say(f"    non-2.02 rows: the 8-K's own event date ('date of report') is the acceptance day (New York) for "
        f"{(dl == 0).mean():.3f}, 1-4 business days earlier for {bd.between(1, 4).mean():.3f}, more for {(bd > 4).mean():.3f} "
        f"(missing {int(ed.isna().sum())}); median {dl.median():.0f} calendar days")
    for itm in ("1.01", "5.02", "7.01", "8.01", "2.03", "5.07"):
        sel = oth["items"].str.contains(rf"\b{itm}\b")
        say(f"      item {itm}: same day {(dl[sel] == 0).mean():.3f}, 1-4 business days late {bd[sel].between(1, 4).mean():.3f}")
    only901 = int((oth["items"].str.strip() == "9.01").sum()); none = int((oth["items"].str.strip() == "").sum())
    say(f"    rows whose only item is 9.01: {only901}; rows with no item: {none}")
    # the share-sessions of ideas 059 / 061 / 062 as idea_sessions() reads them (review D3-4), by year, 2017-2021
    s59 = idea_sessions("059"); s61 = idea_sessions("061"); s61a = idea_sessions("061", include_amend=True)
    s62 = idea_sessions("062"); s62n = idea_sessions("062", results_ahead=0)
    ok(not s59.duplicated(["key", "session"]).any() and not s61.duplicated().any() and not s62.duplicated().any(),
       "idea_sessions: one row per share-session for 059, 061 and 062")
    ok(not set(zip(s61.key, s61.session)) & set(zip(s62.key, s62.session)), "no share-session is both a 061 and a 062 session")
    def by_year(t): return t.session.map(lambda d: d.year).value_counts().sort_index().to_dict()
    say(f"\nshare-sessions of the ideas (idea_sessions, 2017-2021 from in_universe_from):")
    say(f"    059 results events (late_suspect dropped): {len(s59)} {by_year(s59)}")
    say(f"    061 other-8-K sessions, plain 8-K only: {len(s61)} {by_year(s61)}; with 8-K/A: {len(s61a)}")
    say(f"    062 sessions without filing, results exclusion s-2..s+2: {len(s62)} {by_year(s62)}; s-2..s only: {len(s62n)}")
    ns_t = news_sessions()
    say(f"    news_sessions.csv: {len(ns_t)} share-sessions with a filing; with more than one 8-K: "
        f"{int((ns_t.n_8k_all > 1).sum())}; only an 8-K/A among the non-2.02 rows: "
        f"{int(((ns_t.n_8ka_other > 0) & (ns_t.n_8k_other == 0)).sum())}")
    fr = pd.DataFrame({"key": s62.key, "year": s62.session.map(lambda d: d.year)}).groupby(["key", "year"]).size()
    fr.rename("no_filing_no_results").reset_index().to_csv(os.path.join(OUT, "counts_sessions_without_8k.csv"), index=False)

    # 7. prices as a witness (only to judge the calendar; nothing is chosen by it)
    have = sorted(f[:-8] for f in os.listdir(BARS) if f.endswith(".parquet")) if os.path.isdir(BARS) else []
    keys = [k for k in have if k in set(res.key)]
    say(f"\nprice witness: daily bars present for {len(have)} shares, {len(keys)} with results rows")
    if keys:
        recs = []; recs_r = []; byco = []; miss_dates = 0; nonsess = 0; R1 = {}
        for k in keys:
            b = pd.read_parquet(os.path.join(BARS, k + ".parquet"))
            b = _bars_close(b)
            b = b[b.index <= pd.Timestamp(CUT)]
            nonsess += sum(1 for d in b.index if not ee.is_session(d.date()))
            ret = b.pct_change(); r1 = ret.abs(); R1[k] = ret
            usual = r1.shift(3).rolling(60, min_periods=40).median()     # ends at s-3: before the event window
            pos = {d.date(): i for i, d in enumerate(b.index)}
            for _, e in res[res.key == k].iterrows():
                i = pos.get(e.event_session.date()); j = pos.get(e.reaction_session.date())
                if i is None or j is None:
                    miss_dates += 1; continue
                if i < 2 or j + 2 >= len(b) or not usual.iloc[i] > 0: continue
                for o in range(-2, 3):
                    recs.append((e["when"], o, r1.iloc[i + o] / usual.iloc[i]))
                    recs_r.append((e["when"], o, r1.iloc[j + o] / usual.iloc[i]))
                byco.append((k, e["when"], r1.iloc[i - 1] > r1.iloc[i] and r1.iloc[i - 1] > r1.iloc[i + 1],
                             r1.iloc[i + 1] > r1.iloc[i] and r1.iloc[i + 1] > r1.iloc[i - 1]))
        say(f"    event sessions not found in the bars: {miss_dates}; bar dates that are not NYSE sessions: {nonsess}")
        for lab, rr in (("event_session (the event day a run uses)", recs), ("reaction_session (before the fix)", recs_r)):
            w = pd.DataFrame(rr, columns=["when", "off", "x"])
            t = w.groupby(["when", "off"]).x.mean().unstack()
            cnt = w[w.off == 0].groupby("when").size()
            say(f"    mean |close-to-close move| / usual daily move, sessions -2..+2 around the {lab}:")
            say(t.round(2).assign(events=cnt).to_string())
            if lab.startswith("event"):
                pk = t.idxmax(axis=1)
                for wc in ("before_open", "after_close", "in_session", "closed_day"):
                    if wc in pk: ok(pk[wc] == 0, f"witness peaks at the event session for {wc} ({int(cnt.get(wc, 0))} rows)")
                t.round(3).assign(events=cnt).to_csv(os.path.join(OUT, "check_witness.csv"))
            else:
                pk = t.idxmax(axis=1)
                say(f"    (with reaction_session, in_session rows peak at offset {pk.get('in_session')}: one session early)")
        bc = pd.DataFrame(byco, columns=["key", "when", "early", "late"])
        g = bc.groupby("key").agg(n=("when", "size"), early=("early", "mean"), late=("late", "mean"),
                                  when=("when", lambda x: x.value_counts().idxmax()))
        g.to_csv(os.path.join(OUT, "check_witness_by_company.csv"))
        # late stamps not by construction: results rows NOT accepted in session whose largest move of s-1, s, s+1 is
        # on s-1; per company against the overall share (binomial upper tail)
        nb = bc[bc["when"] != "in_session"]
        base = nb.early.mean()
        from math import comb
        def tail(kk, nn): return sum(comb(nn, x) * base ** x * (1 - base) ** (nn - x) for x in range(kk, nn + 1))
        gk = nb.groupby("key").early.agg(["size", "sum"])
        gk["p"] = [tail(int(kk), int(nn)) for nn, kk in zip(gk["size"], gk["sum"])]
        hot = gk[gk.p < 0.001].sort_values("p")
        say(f"    results rows not accepted in session: {len(nb)}; share whose largest move is on the session BEFORE the "
            f"event session: {base:.3f}; companies far above it (binomial p < 0.001): "
            + ", ".join(f"{k} {int(r['sum'])}/{int(r['size'])}" for k, r in hot.iterrows()))
        ok(set(hot.index) <= set(LATE_STAMP), f"every such company is in LATE_STAMP (flagged late_suspect): {sorted(LATE_STAMP)}")
        # largest move AFTER the event session: a stamp cannot be early (the 8-K is public at acceptance), so this
        # is noise or drift; listed with the same binomial test, not asserted
        base_l = bc.late.mean()
        gl = bc.groupby("key").late.agg(["size", "sum"])
        gl["p"] = [sum(comb(int(nn), x) * base_l ** x * (1 - base_l) ** (int(nn) - x) for x in range(int(kk), int(nn) + 1))
                   for nn, kk in zip(gl["size"], gl["sum"])]
        say(f"    share of results rows whose largest move is on the session AFTER the event session: {base_l:.3f}; "
            f"companies far above it (p < 0.001; a stamp cannot be early, so drift or noise): "
            + (", ".join(f"{k} {int(r['sum'])}/{int(r['size'])}" for k, r in gl[gl.p < 0.001].iterrows()) or "none"))
        # counts of signal sessions (|move| of the event session itself >= 8 %), by year; no later return is read
        U = pd.DataFrame(R1)
        mkt = U.median(axis=1)                                           # equal-weight median move of the universe
        def mv(t, net=False):
            out = []
            for k, d in zip(t.key, t.session):
                x = R1.get(k)
                v = x.get(pd.Timestamp(d), np.nan) if x is not None else np.nan
                out.append(abs(v - mkt.get(pd.Timestamp(d), np.nan)) if net else abs(v))
            return np.array(out)
        say("    signal sessions with |move| >= 8 % on the session itself (counts only), by year 2017..2021 | all | "
            "without 2020 | moves net of the universe's median move that session:")
        for nm, t in (("059", s59), ("061", s61), ("061 with 8-K/A", s61a), ("062", s62)):
            m = mv(t); mn = mv(t, True); yr = t.session.map(lambda d: d.year).to_numpy()
            big = pd.Series(yr[m >= 0.08]).value_counts().reindex(range(2017, 2022), fill_value=0)
            bign = pd.Series(yr[mn >= 0.08]).value_counts().reindex(range(2017, 2022), fill_value=0)
            say(f"      {nm:15s} {[int(x) for x in big.values]} | {int(big.sum())} | {int(big.sum() - big[2020])} | net: "
                f"{[int(x) for x in bign.values]} | {int(bign.sum())} | without 2020 {int(bign.sum() - bign[2020])}")
    say(f"\n{n[0]}/{n[0]} checks passed")
    open(os.path.join(OUT, "test_output.txt"), "w").write("\n".join(out_lines) + "\n")

def _bars_close(b):
    """Daily close series indexed by session date, whatever the bar file's layout."""
    if "date" in b.columns: b = b.set_index("date")
    idx = pd.to_datetime(b.index)
    if getattr(idx, "tz", None) is not None: idx = idx.tz_convert(NY).tz_localize(None)
    c = [x for x in b.columns if x.lower() in ("close", "adjclose", "adj_close")]
    s = pd.Series(b[c[0]].to_numpy(float), index=idx.normalize()).dropna()
    return s[~s.index.duplicated()].sort_index()

if __name__ == "__main__":
    {"fetch": fetch, "build": build, "test": test}[sys.argv[1]]()
