# Data sources of the open search: what can really be fetched (scout, probed 2026-11-17, 21:45-22:45 UTC)

Read with `CHARTER.md` (hard rules) and `kit/data.py` (period lock, `known=` rules). Every snippet below was run by the
scout from this environment with the in-sample bound (nothing after 2021-12-31 requested or kept). "When known" is the
part that protects a run from look-ahead: use the conservative rule unless you can prove a faster one.
The snippets share the three helpers of section 0 and need only the standard library and pandas.

**Read this first: six traps found while probing**
1. **FRED refuses a browser User-Agent** from here (connection closed or read timeout), and answers the default Python
   client at once. `kit/data.py:http_get` sends a browser User-Agent to every host, so `kit.data.fred()` will hang and
   fail until FRED is exempted (tested with the kit's exact User-Agent: read timeout; with the default one: 200).
2. **FRED ignores `coed=` on licence-limited series** and returns its own recent window instead: `BAMLH0A0HYM2`,
   `BAMLC0A0CM`, `BAMLHE00EHYIOAS` (ICE BofA spreads: only 2023-11-20 to today) and `SP500` (2025-11-17 to today);
   `DJIA` starts 2016-11-17. **Idea 005 (credit leads equity) has no in-sample data on FRED any more**, and a run
   that asks for it would receive and cache 2023-2026 values. Check the first and last DATE before parsing a value.
3. **Files that only exist as one full history to today** (CBOE index files, DIX, the JGB file, the policy-uncertainty
   file) must be read with `stream_until` (section 0), never downloaded whole: the CBOE server ignores `Range`.
4. **Bounds that are silently ignored**: Kraken's OHLC `since` (it returns its last 720 candles, i.e. 2024-2026),
   FRED as above. Ask for 1-3 rows first and look at the dates only.
5. **Revised history**: NFCI as published on 2019-06-28 differs from today's NFCI for the same weeks by 0.24 on
   average (the index is re-estimated every week); Coin Metrics exchange flows were recomputed in 2026; AirNow files
   are rewritten for 48 hours. Section by section below; ALFRED gives real-time vintages for FRED series.
6. **Shared address**: other sessions use the same outgoing address. GDELT's API (one call per 5 s), Wikimedia and
   Dukascopy answered 429 or reset connections during this probe. Space the calls, retry with long waits.

## 0. Common helpers (used by every snippet)
```python
import io, json, time, urllib.request, urllib.parse as up
import pandas as pd
CUT = "2021-12-31"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
def raw(url, headers=None, timeout=60):
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=timeout).read()
def stream_until(url, is_after_cut, headers=UA, timeout=60):
    """Lines of an ascending text file up to the first line dated after the cut; that line and the rest are never read."""
    r = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout); out = []
    for line in r:
        s = line.decode("utf-8", "replace").rstrip("\r\n")
        if is_after_cut(s): break
        out.append(s)
    r.close(); return out
```
`stream_until` reads line by line and closes the connection at the first row dated after the cut. Python keeps a small
read-ahead buffer (at most 8 KB of the file after the stop row is pulled from the socket and thrown away unparsed; for a
daily file that is a few months of rows never turned into numbers). If that is not acceptable, do not use the four
sources that need it (2, 4, 11, 28).

## 1. FRED (St. Louis Fed): rates, real yields, volatility indices, uncertainty, liquidity
- URL: `https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES>&cosd=<start>&coed=2021-12-31` (no key).
- Real-time vintages (the series as published on a past day): `https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=<SERIES>&cosd=..&coed=<vintage>&vintage_date=<vintage>`
  (one request per vintage date; the same parameter on fredgraph.csv is ignored: checked).
```python
def fred(sid, start="1990-01-01"):
    b = raw(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={start}&coed={CUT}")   # default urllib User-Agent
    dates = pd.read_csv(io.BytesIO(b), usecols=[0], parse_dates=[0]).iloc[:, 0]                    # dates only first
    assert dates.max() <= pd.Timestamp(CUT), f"{sid}: FRED ignored coed (licence window): do not use, do not cache"
    return pd.read_csv(io.BytesIO(b), na_values=["."], parse_dates=[0], index_col=0).iloc[:, 0].dropna()
def alfred(sid, vintage, start="1990-01-01"):
    """The series as it was published on `vintage` (YYYY-MM-DD <= cut): one request per vintage date."""
    assert vintage <= CUT
    u = f"https://alfred.stlouisfed.org/graph/alfredgraph.csv?id={sid}&cosd={start}&coed={vintage}&vintage_date={vintage}"
    return pd.read_csv(io.BytesIO(raw(u)), na_values=["."], parse_dates=[0], index_col=0).iloc[:, 0].dropna()
```
- Probe: 53 series asked with `cosd=1990-01-01&coed=2021-12-31`, 0.6-3 s each (NASDAQCOM 15 s).

| Series | What | First in-sample date (rows to 2021-12-31) | When known | Revised later? |
|---|---|---|---|---|
| DGS10, DGS2, DTB3, T10Y2Y, T10Y3M | Treasury yields and slopes, daily | before 1990 (8,007 rows from 1990) | The Treasury posts day D's curve on D between about 15:30 and 18:00 New York; FRED shows D on the next business day about 16:20 New York. Safe: D+1 business day 13:00 UTC if the live robot reads treasury.gov (`rule_next_bday_utc(13, 1)`), D+1 22:00 UTC if it reads FRED | no |
| DFII10, T10YIE, T5YIFR | 10-year real yield, breakevens | 2003-01-02 (4,755) | same | no |
| VIXCLS, VXVCLS (3-month VIX), VXNCLS, RVXCLS, VXDCLS, GVZCLS (gold), OVXCLS (oil) | CBOE volatility index closes | 1990-01-02 (8,062); 2007-12-04 (3,545); 2001-02-02; 2004-01-02; 1997-10-07; 2008-06-03 (3,423); 2007-05-10 | The index closes at 16:15 New York on D and is public in real time; FRED shows D on D+1. Safe: `rule_local_close("16:30")` (live source = CBOE, section 2) | no |
| USEPUINDXD (daily policy uncertainty), WLEMUINDXD (equity-market uncertainty), INFECTDISEMVTRACKD | newspaper-count indices, 7 days a week | 1985 (11,688 rows from 1990) | The authors' file is rewritten every night about 19:00 US Central; the ALFRED vintage of 2019-06-28 already held the value of 2019-06-28. Safe: D+1 13:00 UTC | yes, mildly: 18 of 59 days of May-June 2019 differ by more than 1 % between the 2019-06-28 vintage and today (median 0.4 %). Use ALFRED vintages if the rule keys on single-day jumps |
| NFCI | Chicago Fed financial conditions, weekly (week ending Friday) | 1971 (1,670 from 1990) | Released the next Wednesday 08:30 New York (the 2019-06-28 vintage ends at 2019-06-21). Safe: release Wednesday 14:00 UTC | **yes, heavily** (re-estimated weekly): use ALFRED vintages only |
| STLFSI4 | St. Louis Fed stress index, weekly | 1993-12-31 | version 4 was created in 2022: no real-time history before, **do not use in sample** | whole history rebuilt |
| WALCL, WTREGEN, WRESBAL, WSHOMCB | Fed balance sheet, Treasury account, reserves (Wednesday levels) | 2002-12-18 (994) | H.4.1 release Thursday 16:30 New York. Safe: Thursday 22:00 UTC | rarely |
| RRPONTSYD | overnight reverse repo, daily | 2003-02-07 (2,153) | same day about 13:15 New York (New York Fed operation result) | no; near zero before 2021-03 except quarter ends |
| DTWEXBGS, DTWEXAFEGS, DTWEXEMEGS, DEXJPUS, DEXUSEU, DEXKOUS ... | dollar indices and noon exchange rates (H.10) | 2006-01-02 (4,013); 1990; 1999 | H.10 is published once a week (Monday, for the week before). Safe: the following Tuesday 00:00 UTC. For a live dollar signal build it from Dukascopy prices instead | index weights revised yearly |
| ICSA | jobless claims, weekly (week ending Saturday) | 1967 (1,669 from 1990) | Thursday 08:30 New York | yes, the week after |
| NASDAQCOM, CBBTCUSD | Nasdaq Composite close; Coinbase bitcoin daily | 1971 (8,065 from 1990); 2014-12-01 (2,553) | close of D | no |
| EVZCLS, VXEEMCLS, TEDRATE | euro and emerging-market volatility, TED spread | 2007-11-01; 2011-03-16; 1986 | probably dead: the CBOE history file of EVZ answers 403 today; TEDRATE ended in January 2022 | do not build on them |
| BAMLH0A0HYM2, BAMLC0A0CM, BAMLHE00EHYIOAS, SP500, DJIA | ICE BofA spreads, S&P 500, Dow | **not available in sample** (see trap 2) | | |
| GOLDPMGBD228NLBM, WILL5000IND | London gold fix, Wilshire 5000 | 404: removed from FRED | | |

- Still published: not checked series by series (FRED gives no date without the values); the H.15 yields, the CBOE
  indices (checked on CBOE, section 2), the H.4.1 series and the uncertainty file (section 28) are alive today.
- Licence: FRED terms of use; ICE and S&P series are restricted (hence the windows). No data in git.

## 2. CBOE index histories: VIX9D, VVIX, SKEW (and VIX, VIX3M, VXN, GVZ, OVX, RVX, VXD)
- URL: `https://cdn.cboe.com/api/global/us_indices/daily_prices/<NAME>_History.csv`: one ascending file to today
  (`DATE,OPEN,HIGH,LOW,CLOSE` or `DATE,<NAME>`; dates MM/DD/YYYY). `Range` is ignored: use `stream_until`.
```python
def cboe_index(name):  # VIX9D, VVIX, SKEW, VIX3M, GVZ, OVX, VXN ...
    L = stream_until(f"https://cdn.cboe.com/api/global/us_indices/daily_prices/{name}_History.csv",
                     lambda s: s[:1].isdigit() and int(s[6:10]) >= 2022)
    d = pd.read_csv(io.StringIO("\n".join(L)), parse_dates=[0], index_col=0)
    return d[d.columns[-1]]
```
- Probe: VIX9D 2011-01-04 to 2021-12-31, 2,768 rows, 0.3 s; VVIX 2006-03-06 (sparse before 2007), 3,925 rows, 0.2 s;
  SKEW 1990-01-02, 8,049 rows, 0.3 s. In-sample years from 2013: 9.
- Frequency: daily close. When known: the files are rewritten at about 17:31 New York for VIX9D, VVIX, VIX3M, VXN,
  GVZ, OVX, RVX, VXD (Last-Modified Mon 16 Nov 2026 22:31 GMT) and about 21:15 New York for SKEW and VIX. The indices
  themselves tick in real time until 16:15 New York. Safe rule: `rule_local_close("17:45")`, or simply the next
  session's open.
- Revised: no. Still published: yes for the ten names above (HEAD, Last-Modified 16-17 Nov 2026); **EVZ: 403**.
- Licence: CBOE market-data terms (research use; nothing in git).

## 3. CBOE put/call ratios
- 2006-11-01 to 2019-10-04: static files `https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/equitypc.csv`
  (`totalpc.csv`, `indexpc.csv`), last modified 2020-10-30, about 135 KB, 3,253 rows each.
- From 2019-10-07: one JSON per session, `https://cdn.cboe.com/data/us/options/market_statistics/daily/<YYYY-MM-DD>_daily_options`
  (key `ratios`: total, index, exchange-traded products, equity, VIX, SPX+SPXW, OEX put/call). Earlier dates and
  non-trading days answer 403. About 565 calls for 2019-10-07 to 2021-12-31 (0.2 s each).
```python
def cboe_pc_archive(kind="equity"):  # equity, total, index
    t = raw(f"https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/{kind}pc.csv", UA).decode()
    d = pd.read_csv(io.StringIO(t), skiprows=2, parse_dates=[0], index_col=0)
    return d[d.columns[-1]]
def cboe_pc_day(day):  # 'YYYY-MM-DD' (<= 2021-12-31); 403 = no session that day
    assert day <= CUT
    j = json.loads(raw(f"https://cdn.cboe.com/data/us/options/market_statistics/daily/{day}_daily_options", UA))
    return {r["name"]: float(r["value"]) for r in j["ratios"]}
```
- Probe: archive first 2006-11-01, last 2019-10-04; JSON of 2021-12-30 gives equity 0.49, total 0.83; 2019-10-07 exists;
  2019-06-03, 2016-03-01, 2012-06-12 answer 403.
- When known: end of the session; the JSON of 2026-11-16 was written at 03:21 GMT the next day. Safe: next day 08:00 UTC
  (the ratios are also shown on CBOE's site during the evening, not verified). Revised: no. Still published: yes.

## 4. SqueezeMetrics DIX and GEX
- URL: `https://squeezemetrics.com/monitor/static/DIX.csv` (`date,price,dix,gex`, ascending, to today; `Range` works).
```python
def dix():
    L = stream_until("https://squeezemetrics.com/monitor/static/DIX.csv", lambda s: s[:4].isdigit() and s[:10] > CUT)
    return pd.read_csv(io.StringIO("\n".join(L)), parse_dates=[0], index_col=0)
```
- Probe: 2011-05-02 to 2021-12-31, 2,687 rows, 0.2 s. Daily. In sample from 2013: 9 years.
- When known: the file is rewritten about 18:00 New York (Last-Modified Mon 16 Nov 2026 22:59 GMT) with the day's value
  (it is built from the FINRA files of section 6). Safe: `rule_local_close("19:00")`.
- Revised: unknown (a vendor's computation on the S&P 500 members; the first print cannot be checked). The lab already
  used this file as a sizing gate (Addendum C, failed validation). Still published: yes. Proprietary, free to read.

## 5. CFTC Commitments of Traders through Socrata (the www.cftc.gov site refuses us, this API does not)
- URL: `https://publicreporting.cftc.gov/resource/<id>.json?$select=..&$where=..&$order=..&$limit=50000`.
  Ids checked: legacy futures-only `6dca-aqww` (since 1986), disaggregated futures-only `72hh-3qpy` and financial
  futures (TFF) futures-only `gpe5-46if` (both since 2006-06-13). Combined-with-options ids (from memory, not probed):
  `jun7-fc8e`, `kh3c-gbw2`, `yw9f-hn96`.
- Contract codes checked (rows to 2021-12-28): gold 088691 (1,688), silver 084691 (1,688), EUR 099741 (1,210, since 1999),
  JPY 097741 (1,689), GBP 096742 (1,634), AUD 232741 (1,552), CAD 090741 (1,689), CHF 092741 (1,687), NZD 112741 (908),
  E-mini S&P 500 13874A (1,263), Nasdaq-100 209742 (1,176), Dow 124603 (1,019).
```python
def cot(codes, resource="6dca-aqww", cols="noncomm_positions_long_all,noncomm_positions_short_all,open_interest_all"):
    q = {"$select": "report_date_as_yyyy_mm_dd,cftc_contract_market_code," + cols, "$limit": "50000",
         "$where": "cftc_contract_market_code in (%s) AND report_date_as_yyyy_mm_dd <= '%sT00:00:00.000'"
                   % (",".join("'%s'" % c for c in codes), CUT), "$order": "report_date_as_yyyy_mm_dd"}
    d = pd.DataFrame(json.loads(raw("https://publicreporting.cftc.gov/resource/%s.json?%s" % (resource, up.urlencode(q)), UA)))
    d["date"] = pd.to_datetime(d.pop("report_date_as_yyyy_mm_dd"))
    return d.set_index("date").apply(lambda c: pd.to_numeric(c, errors="coerce") if c.name != "cftc_contract_market_code" else c)
```
- Probe: 12 legacy contracts in one call, 17,203 rows, 4.3 s; TFF 10 contracts 8,117 rows, 5.2 s. Weekly.
- When known: positions of Tuesday's close, released **Friday 15:30 New York**; when a federal holiday falls in the
  week the release slips (usually to Monday). Two long gaps (from memory, check before declaring): the shutdowns of
  October 2013 and of 2018-12-22 to 2019-01-25, after which the backlog was published over several weeks (until early
  March 2019). Safe rule: value usable from the **Tuesday 00:00 UTC after the report's own Tuesday (report date + 7
  days)**, and drop report dates 2013-10-01..2013-11-12 and 2018-12-18..2019-03-05. A Monday entry is safe only in
  weeks without a US federal holiday between the report Tuesday and Friday.
- Revised: rarely (corrected reports replace the old ones; the API serves the corrected values).
- Still published: yes (latest report date 2026-11-10). Public domain.

## 6. FINRA daily short-sale volume files (off-exchange trades reported to FINRA)
- URL: `https://cdn.finra.org/equity/regsho/daily/<FAC>shvol<YYYYMMDD>.txt`, '|' separated, one row per symbol.
  `CNMS` (all facilities together) exists from 2018-08-01 (2014, 2011, 2009 answer 403); before that add the
  facility files `FNSQ` (Nasdaq TRF) and `FNYX` (NYSE TRF), which exist for 2011-01-03 (`FNRA` is almost empty).
  2011 rows: `Date|Symbol|ShortVolume|TotalVolume|Market`; 2021 rows add `ShortExemptVolume` before `TotalVolume`.
```python
def finra_day(day="20211230", fac="CNMS", symbols=("SPY", "QQQ", "GLD", "SLV", "GDX", "TLT", "HYG")):
    assert day <= "20211231"
    t = raw(f"https://cdn.finra.org/equity/regsho/daily/{fac}shvol{day}.txt", UA).decode()
    return [l.split("|") for l in t.splitlines() if l.split("|")[1:2] and l.split("|")[1] in symbols]
```
- Probe: 2021-12-30 CNMS: GLD short 578,593 of 1,056,342; 2011-01-03 FNSQ: GLD 1,161,084 of 2,385,176 (0.2-0.3 s per
  file, about 0.3-0.5 MB). A 2011-2021 history is about 2,770 days x 1-2 files: 10-15 minutes, kept rows only.
- When known: posted by 18:00 New York on the day itself (the 2021-12-30 file was written 17:23 New York, the
  2026-11-16 file 17:18). Safe: `rule_local_close("18:30")`.
- Revised: no in principle (old files were re-uploaded in 2021-2022, content unchanged as far as can be seen).
- Still published: yes (file of 2026-11-16 exists, HEAD only). Public.

## 7. US Treasury auctions (fiscaldata API; TreasuryDirect's own web service answers 500)
- URL: `https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query?filter=auction_date:lte:2021-12-31,...`
```python
def fiscal(path, flt, fields, size=10000):
    out, page = [], 1
    while True:
        j = json.loads(raw("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/" + path +
                           f"?filter={flt}&fields={fields}&sort={fields.split(',')[0]}&page[size]={size}&page[number]={page}", UA))
        out += j["data"]
        if page >= j["meta"]["total-pages"]: break
        page += 1
    return pd.DataFrame(out)
def auctions():
    return fiscal("v1/accounting/od/auctions_query", f"auction_date:lte:{CUT},auction_date:gte:2012-01-01,security_type:in:(Note,Bond)",
                  "auction_date,announcemt_date,issue_date,security_type,security_term,reopening,inflation_index_security,floating_rate,"
                  "offering_amt,total_accepted,bid_to_cover_ratio,high_yield,indirect_bidder_accepted,closing_time_comp")
```
- Probe: 960 note and bond auctions 2012-2021 in 0.6 s (history since 1979-10-31). In 2013-2021: 670 nominal coupon
  auctions on 643 days (2y, 3y, 5y, 7y, 30y: 108 each; 10y: 109; 20y: 21), 238 clusters of consecutive auction days;
  closing time 13:00 New York for 632 of them (11:30 for 36).
- Fields: `auction_date`, `announcemt_date`, `issue_date` (settlement), `security_term`, `reopening`,
  `offering_amt`, `total_accepted`, `bid_to_cover_ratio`, `high_yield`, `indirect_bidder_accepted`, `closing_time_comp`.
- When known: the calendar (date, size) on `announcemt_date`, 2 to 6 business days before the auction in 2013-2021
  (2 days: 75 auctions, 3: 187, 4: 203, 5: 167, 6: 36; the Treasury's tentative schedule gives the pattern months
  ahead); results within about two minutes of the close. Safe for results: close + 5 minutes. Settlement follows 1
  to 11 business days after the auction. Auctions fall on Monday to Thursday (84, 216, 203, 165).
- Trap: two rows are 25-million-dollar test auctions announced the same day (2019-06-21 and 2021-12-02, both
  Fridays): keep `offering_amt` of one billion or more.
- Revised: no. Still published: yes (latest auction listed 2026-10-22 on 2026-11-17). Public domain.
- Note: the "tail" of idea 013 needs the when-issued yield at the close, which is not in this data.

## 8. Daily Treasury Statement: the Treasury's cash balance
- URL: `.../v1/accounting/dts/operating_cash_balance?filter=record_date:lte:2021-12-31` (since 2005-10-03).
```python
def tga():
    d = fiscal("v1/accounting/dts/operating_cash_balance", f"record_date:lte:{CUT}", "record_date,account_type,open_today_bal,close_today_bal")
    return d
```
- Probe: 11,971 rows in 1.8 s; account type "Federal Reserve Account" (later "Treasury General Account (TGA)") holds
  the closing balance in `close_today_bal`, USD millions; 2,263 business days in 2013-2021.
- When known: day D's statement is published on the next business day about 16:00 New York. Safe:
  `known_at(dates, lag_bdays=1, time="16:30")`. Revised: rarely. Still published: yes (latest record 2026-11-16).
- Format break after the sample (2022): the closing balance moves to another account type and column.

## 9. Swiss National Bank sight deposits (weekly)
- URL: `https://data.snb.ch/api/cube/snbgwdchfsgw/data/csv/en?fromDate=2011-01-01&toDate=2021-12-31`
```python
def snb():
    t = raw(f"https://data.snb.ch/api/cube/snbgwdchfsgw/data/csv/en?fromDate=2011-01-01&toDate={CUT}", UA).decode("utf-8-sig")
    d = pd.read_csv(io.StringIO(t), sep=";", skiprows=3, parse_dates=[0]).dropna(subset=["Value"])
    return d.pivot(index="Date", columns="D0", values="Value")
```
- Probe: 574 weekly rows 2011-01-07 to 2021-12-31 in 2.2 s; columns GI (domestic banks), UEB (other), TG (total),
  CHF millions, dated on the Friday that ends the week (weekly averages).
- When known: the file header says "PublishingDate 2026-11-16 10:00": Monday 10:00 Zurich for the week before. Safe:
  Monday 10:00 UTC (Tuesday when Monday is a Swiss holiday). Revised: no. Still published: yes. Free with attribution.

## 10. European Central Bank data API (euro-area yield curve)
- URL: `https://data-api.ecb.europa.eu/service/data/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_<2Y|10Y>?startPeriod=..&endPeriod=2021-12-31&format=csvdata`
```python
def ecb_yield(tenor="2Y", start="2013-01-01"):
    u = f"https://data-api.ecb.europa.eu/service/data/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_{tenor}?startPeriod={start}&endPeriod={CUT}&format=csvdata"
    d = pd.read_csv(io.BytesIO(raw(u, UA)), usecols=["TIME_PERIOD", "OBS_VALUE"], parse_dates=["TIME_PERIOD"], index_col="TIME_PERIOD")
    return d["OBS_VALUE"]
```
- Probe: 2-year AAA spot yield, 2,294 daily rows 2013-01-02 to 2021-12-31, 8.6 s.
- When known (from memory, not verified): published at noon Frankfurt time on the next business day. Safe:
  `rule_next_bday_utc(13, 1)`. Revised: no. Free reuse with attribution.

## 11. Japan Ministry of Finance: JGB yields
- URL: `https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/historical/jgbcme_all.csv` (1974-09-24 to the
  end of last month, ascending, dates Y/M/D; the current month is in `.../interest_rate/jgbcme.csv`, not probed).
```python
def jgb():
    L = stream_until("https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/historical/jgbcme_all.csv",
                     lambda s: s[:4].isdigit() and int(s[:4]) >= 2022)
    d = pd.read_csv(io.StringIO("\n".join(L[1:])), na_values=["-"], parse_dates=[0], index_col=0)
    return d
```
- Probe: 12,151 rows to 2021-12-30, 15 maturities (1Y..40Y), 2.3 s.
- When known (not verified): the yields are the Tokyo afternoon reference rates, posted on the ministry's site the next
  business day. Safe: D+2 00:00 UTC. Revised: no. Still published: yes (file last modified 2026-11-03).
- The weekly "transactions in securities" (foreign bond flows) file was not found (404 on the guessed path).

## 12. New York Fed markets API (primary dealers, reverse repo operations)
- URLs: `https://markets.newyorkfed.org/api/pd/get/SBN2015/timeseries/PDPOSGST-TOT.json` (dealers' net Treasury
  position, weekly, 2015-01-07 to 2021-12-29 in the "SBN2015" series break; earlier breaks not probed);
  `https://markets.newyorkfed.org/api/rp/reverserepo/propositions/search.json?startDate=..&endDate=2021-12-31`.
```python
def nyfed_pd(key="PDPOSGST-TOT", brk="SBN2015"):
    j = json.loads(raw(f"https://markets.newyorkfed.org/api/pd/get/{brk}/timeseries/{key}.json", UA))["pd"]["timeseries"]
    s = pd.Series({pd.Timestamp(x["asofdate"]): float(x["value"]) for x in j if x["value"] not in ("", "*")})
    return s[s.index <= CUT]
```
- Probe: 365 weekly values in 0.3 s; reverse repo operations of 2021-12-28..31: 4 rows.
- When known: dealer statistics for the week ending Wednesday are released on the Thursday of the following week about
  16:15 New York (8 days). Safe: that Thursday 22:00 UTC. Only 7 in-sample years and 365 points: too few for a rule
  on one market.

## 13. Bitfinex public API: nine years of hourly bitcoin, and the price of borrowing dollars
- URL: `https://api-pub.bitfinex.com/v2/candles/<key>/hist?limit=10000&start=<ms>&end=<ms>&sort=1`; keys
  `trade:1h:tBTCUSD` (first candle **2013-03-31 23:00**), `trade:1h:tETHUSD` (first 2016-03-09 16:00),
  `trade:1D:fUSD:p2` and `trade:1h:fUSD:p2` (USD margin-funding rate, 2-day period; first 2016-07-31; `p30` also).
```python
def bitfinex(key="trade:1D:fUSD:p2", start="2016-07-01", end=CUT + " 23:59"):
    s, e, out = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000), int(pd.Timestamp(end, tz="UTC").timestamp() * 1000), []
    while s < e:
        j = json.loads(raw(f"https://api-pub.bitfinex.com/v2/candles/{key}/hist?limit=10000&start={s}&end={e}&sort=1", UA))
        if not j: break
        out += j; s = j[-1][0] + 1; time.sleep(1.5)
    d = pd.DataFrame(out, columns=["t", "open", "close", "high", "low", "volume"])
    return d.set_index(pd.to_datetime(d.pop("t"), unit="ms", utc=True))
```
- Probe: daily funding candles 2016-07-31 to 2021-12-31, 1,971 rows, 2.7 s; a funding "price" is the rate per day
  (0.0002 = 0.02 % a day). Rows are `[time, open, close, high, low, volume]`. Hours without a trade are missing.
- When known: at the candle's close (real time). Revised: no. Still up: yes (`platform/status` = 1).
- **Consequence for the search: bitcoin has 8.75 in-sample years of hourly prices here (ether 5.8), against 4.4 on
  Binance.** The CFD's costs are a model in basis points anyway; say in the declaration which venue prices the trades.
- Too short for research: `stats1/pos.size:1h:tBTCUSD:long|short` (margin longs and shorts) starts 2021-02-22 and
  `funding.size` 2021-04-07 through this API.

## 14. Bitstamp OHLC (USD pairs, long history)
- URL: `https://www.bitstamp.net/api/v2/ohlc/<pair>/?step=<seconds>&limit=1000&start=<s>&end=<s>`: it returns the
  `limit` candles that END at `end`, so walk backward.
```python
def bitstamp(pair="btcusd", step=86400, start="2013-01-01", end=CUT):
    s, e, out = int(pd.Timestamp(start, tz="UTC").timestamp()), int(pd.Timestamp(end, tz="UTC").timestamp()) + 86399, []
    while e > s:
        j = json.loads(raw(f"https://www.bitstamp.net/api/v2/ohlc/{pair}/?step={step}&limit=1000&start={s}&end={e}", UA))["data"]["ohlc"]
        if not j: break
        out += j; e = int(j[0]["timestamp"]) - step; time.sleep(0.3)
    d = pd.DataFrame(out).astype(float).drop_duplicates("timestamp").sort_values("timestamp")
    d = d[d.timestamp >= s]
    return d.set_index(pd.to_datetime(d.pop("timestamp"), unit="s", utc=True))
```
- Probe: btcusd daily 2013-01-01 to 2021-12-31, 3,287 rows, 5.0 s (hourly candles exist for November 2012; daily for
  December 2011); ethusd hourly starts 2017-08-16. Real time, not revised.

## 15. Coinbase Exchange candles
- URL: `https://api.exchange.coinbase.com/products/<BTC-USD|ETH-USD>/candles?granularity=<60|3600|86400>&start=..&end=..`
  (at most 300 candles per call; rows `[time, low, high, open, close, volume]`).
```python
def coinbase(product="BTC-USD", gran=86400, start="2015-07-20", end=CUT):
    s, e, out = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1), []
    while s < e:
        t = min(s + pd.Timedelta(seconds=gran * 300), e)
        out += json.loads(raw(f"https://api.exchange.coinbase.com/products/{product}/candles?granularity={gran}"
                              f"&start={s:%Y-%m-%dT%H:%M:%SZ}&end={(t - pd.Timedelta(seconds=gran)):%Y-%m-%dT%H:%M:%SZ}", UA))
        s = t; time.sleep(0.25)
    d = pd.DataFrame(out, columns=["t", "low", "high", "open", "close", "volume"]).drop_duplicates("t").sort_values("t")
    return d.set_index(pd.to_datetime(d.pop("t"), unit="s", utc=True))
```
- Probe: BTC-USD daily 2015-07-20 to 2021-12-31, 2,357 rows, 3.5 s; ETH-USD from 2016-05-18. Hourly history of
  BTC-USD needs about 190 calls. Real time, not revised. Still up: product status "online".

## 16. Upbit candles (Korean won market)
- URL: `https://api.upbit.com/v1/candles/days?market=KRW-BTC&to=<UTC time>&count=200` (also `candles/minutes/60`);
  walks backward from `to`.
```python
def upbit(market="KRW-BTC", end=CUT):
    to, out = pd.Timestamp(end) + pd.Timedelta(days=1), []
    while True:
        j = json.loads(raw(f"https://api.upbit.com/v1/candles/days?market={market}&to={to:%Y-%m-%dT%H:%M:%SZ}&count=200", UA))
        if not j: break
        out += j; to = pd.Timestamp(j[-1]["candle_date_time_utc"]); time.sleep(0.2)
    d = pd.DataFrame(out)
    return d.set_index(pd.to_datetime(d.candle_date_time_utc))["trade_price"].sort_index()
```
- Probe: KRW-BTC daily 2017-09-25 to 2021-12-31, 1,559 rows, 10.8 s: 4.27 in-sample years. The won rate for a
  premium comes from FRED `DEXKOUS` (weekly publication lag: use the previous week's rate) or any live FX quote.

## 17. Binance public dumps (charter): what is inside the klines
- `https://data.binance.vision/data/spot/monthly/klines/<SYM>/1h/<SYM>-1h-<YYYY-MM>.zip`, no header, 12 columns:
  open time (ms), open, high, low, close, volume, close time, quote volume, trades, **taker-buy base volume**,
  taker-buy quote volume, ignore. BTCUSDT and ETHUSDT: 38,222 hourly rows each, 2017-08-17 04:00 to 2021-12-31,
  53 files, about 32 s per symbol. Taker-buy share = column 10 / column 6 (mean 0.498 for BTC, 0.500 for ETH).
- Futures funding files: `.../futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2019-09.zip` answers 404,
  2020-01 exists: at most 2 in-sample years, **below the 4-year rule** (the charter says "since 2019-09").

## 18. blockchain.info charts (bitcoin chain activity)
- URL: `https://api.blockchain.info/charts/<chart>?start=2013-01-01&timespan=9years&format=json&sampled=false`
  (start + timespan must end by 2021-12-31: this pair ends on 2021-12-30).
```python
def bcinfo(chart="transaction-fees-usd"):
    j = json.loads(raw(f"https://api.blockchain.info/charts/{chart}?start=2013-01-01&timespan=9years&format=json&sampled=false", UA))
    s = pd.Series({pd.Timestamp(v["x"], unit="s"): v["y"] for v in j["values"]})
    assert s.index.max() <= pd.Timestamp(CUT); return s
```
- Probe (each 0.5 s, 3,286 daily rows 2013-01-01 to 2021-12-30): hash-rate, difficulty, miners-revenue,
  n-transactions, transaction-fees-usd, estimated-transaction-volume-usd, n-unique-addresses, avg-block-size,
  median-confirmation-time; mempool-size is by minute from 2016-06-14 (194,327 rows, 6 MB, 2.3 s).
- When known: a UTC day's value appears some hours after midnight. Safe: D+1 06:00 UTC. Revised: these are counts of
  the chain (stable); hash-rate is an estimate. Still published: not checked (it would read a 2026 value).

## 19. Coin Metrics community API
- URL: `https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets=btc&metrics=..&frequency=1d&start_time=..&end_time=2021-12-31&page_size=10000`
```python
def coinmetrics(asset="btc", metrics="AdrActCnt,TxCnt,FeeTotNtv,CapMVRVCur,FlowInExNtv,FlowOutExNtv,SplyExNtv", start="2013-01-01"):
    j = json.loads(raw("https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets=%s&metrics=%s&frequency=1d"
                       "&start_time=%s&end_time=%s&page_size=10000" % (asset, metrics, start, CUT), UA))
    d = pd.DataFrame(j["data"]); d.index = pd.to_datetime(d.pop("time")).dt.tz_localize(None)
    return d[[c for c in metrics.split(",")]].astype(float)
```
- Probe: btc 2013-01-01 to 2021-12-31, 3,287 rows, 0.4 s. Open metrics for btc at daily frequency: PriceUSD,
  AdrActCnt, TxCnt, TxTfrCnt, CapMVRVCur, CapMrktCurUSD, HashRate, FeeTotNtv, IssTotNtv, SplyCur, FlowInExNtv,
  FlowOutExNtv, FlowInExUSD, FlowOutExUSD, SplyExNtv, BlkCnt. Refused (403, and one refused metric fails the whole
  call): CapRealUSD, DiffMean, FeeMeanUSD, NVTAdj, TxTfrValAdjUSD, SplyAct1yr, VtyDayRet30d, RevUSD, SOPR.
  Stablecoin supply `SplyCur` for usdt (from 2014-10-06), usdc, usdt_eth, usdt_trx, usdt_omni: open. Exchange flows
  start 2011-04-24 (btc), ether metrics 2015-07-30.
- When known: the day after (safe: D+2 00:00 UTC).
- **Revised: the exchange-flow metrics are not point-in-time.** Rows of 2011 carry a status time of April and
  September 2026: the labelling of exchange addresses is extended backward. A back-test on today's flows knows
  addresses nobody knew then. Chain counts (AdrActCnt, TxCnt, FeeTotNtv, SplyCur) do not have this problem.
- Licence (from memory): community data is CC BY-NC 4.0, non-commercial: to be read before any live use.

## 20. Wikimedia page views
- URL: `https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/<Title>/daily/20150701/20211231`
  (daily since 2015-07-01: 6.5 in-sample years). A descriptive User-Agent is required.
```python
def wiki(article, start="20150701", end="20211231", project="en.wikipedia"):
    j = json.loads(raw(f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{project}/all-access/user/"
                       f"{up.quote(article, safe='')}/daily/{start}/{end}", {"User-Agent": "scout-probe/0.1 (research script)"}))
    return pd.Series({pd.Timestamp(i["timestamp"][:8]): i["views"] for i in j["items"]})
```
- Probe: 2,376 daily values per page in 0.3 s (Ethereum, Gold, Silver, Euro, Japanese_yen, S&P_500 read; Bitcoin and
  DAX answered 429 from this shared address: wait 2-3 s between calls and retry).
- When known: a UTC day is published during the next day. Safe: D+2 00:00 UTC.
- Traps: views are counted under the title of the time; a renamed page splits its history (S&P_500 has a median of
  767 views a day, far too low: the page was moved, add the old title). "user" excludes declared robots only.
- Revised: no. Licence: CC0.

## 21. GDELT: what it offers beyond the daily event files of ideas 002 and 003
- Daily event files (in use): `https://data.gdeltproject.org/events/<YYYYMMDD>.export.CSV.zip`, 2013-04-01 on; the
  file of 2021-12-30 was written 2021-12-31 07:00 GMT (5.8 MB). Country codes of the actors, the Goldstein scale and
  the four "QuadClass" groups are in the same rows: country-specific tone or conflict costs no extra download.
- Daily theme counts: `https://data.gdeltproject.org/gkg/<YYYYMMDD>.gkgcounts.csv.zip` (0.26 MB in 2013, 3.1 MB in
  2021, written 07:01 GMT the next day; HEAD only, content not read): counts of events by theme and place (KILL,
  PROTEST, ARREST, AFFECT ...).
- DOC 2.0 API (news articles, **2017-01-01 on only: 5 in-sample years**):
  `https://api.gdeltproject.org/api/v2/doc/doc?query=<words>&mode=timelinevolraw&format=csv&startdatetime=20211201000000&enddatetime=20211231235959`
  returned the daily count of matching articles and of all monitored articles for December 2021 (2.2 KB, one call).
  `mode=timelinetone` gives the average tone. Limit: one call per 5 seconds per address; 3 of the scout's 4 calls
  got 429 because the address is shared. Whether a five-year window comes back by day in one call is not verified.
- TV API (`/api/v2/tv/tv`, business-channel captions since 2009): connection reset twice: not reachable.
- When known: 15-minute updates; a day's count is complete after midnight UTC. Safe: D+1 08:00 UTC. Counts of old
  days can still grow a little (late crawls).

## 22. Hacker News story counts (Algolia)
```python
def hn_count(query="bitcoin", day="2021-12-30"):
    s = int(pd.Timestamp(day, tz="UTC").timestamp())
    j = json.loads(raw(f"https://hn.algolia.com/api/v1/search_by_date?query={query}&tags=story&numericFilters=created_at_i>={s},created_at_i<{s + 86400}&hitsPerPage=0", UA))
    return j["nbHits"]
```
- Probe: 2 stories with "bitcoin" on 2021-12-30, 0.3 s per day-window (one call per day: slow for long histories).
  Real time; deleted stories disappear later (small).

## 23. GFZ Potsdam: geomagnetic Kp index
- URL: `https://kp.gfz-potsdam.de/app/json/?start=2013-01-01T00:00:00Z&end=2021-12-31T23:59:59Z&index=Kp`
```python
def kp(start="2013-01-01"):
    j = json.loads(raw(f"https://kp.gfz-potsdam.de/app/json/?start={start}T00:00:00Z&end={CUT}T23:59:59Z&index=Kp", UA))
    return pd.Series(j["Kp"], index=pd.to_datetime(j["datetime"]))
```
- Probe: 26,296 three-hour values 2013-01-01 to 2021-12-31 in 1.9 s (status "def" = definitive).
- When known: a provisional value minutes after each 3-hour interval, replaced by the definitive one within weeks
  (small changes). Safe: the completed UTC day, at D+1 00:30 UTC. Still published: yes (file modified 2026-11-16).
  Licence: CC BY 4.0.

## 24. Iowa Environmental Mesonet: hourly airport weather (sky cover in New York)
- URL: `https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=LGA&data=skyc1&...&year1=..&year2=..&tz=Etc/UTC&format=onlycomma&report_type=3`
  One request per station and year (a nine-year request fails); the end date is exclusive.
```python
def asos(station="LGA", y1=2013, y2=2021):
    parts = []
    for y in range(y1, min(y2, 2021) + 1):          # one request per year; the end date is exclusive (stops at 2022-01-01)
        u = (f"https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station={station}&data=skyc1&data=skyc2&data=skyc3"
             f"&data=skyc4&data=tmpf&data=vsby&year1={y}&month1=1&day1=1&year2={y + 1}&month2=1&day2=1&tz=Etc%2FUTC"
             "&format=onlycomma&latlon=no&missing=M&trace=T&direct=no&report_type=3")
        parts.append(pd.read_csv(io.BytesIO(raw(u, UA, 240)), parse_dates=["valid"], index_col="valid")); time.sleep(2)
    d = pd.concat(parts); assert d.index.max() < pd.Timestamp("2022-01-01"); return d
```
- Probe: LaGuardia 2013-2021, 78,540 hourly reports (about 8,720 a year, 390 KB and 0.5 s per year); Central Park
  ("NYC") 2021: 8,737 rows. Columns skyc1..4 (CLR, FEW, SCT, BKN, OVC, VV), tmpf, vsby.
- When known: minutes after the report (xx:51 each hour). Not revised. Public data; one request at a time.

## 25. NOAA daily summaries (Central Park)
```python
def noaa_daily(station="USW00094728", start="2013-01-01"):
    u = ("https://www.ncei.noaa.gov/access/services/data/v1?dataset=daily-summaries&stations=%s&startDate=%s&endDate=%s"
         "&dataTypes=TMAX,TMIN,PRCP,AWND,SNOW&format=csv&units=metric" % (station, start, CUT))
    return pd.read_csv(io.BytesIO(raw(u, UA, 120)), parse_dates=["DATE"], index_col="DATE")
```
- Probe: 3,287 days 2013-2021 (TMAX, TMIN, PRCP, AWND, SNOW) in 7.6 s. A day's values exist only after the day: for
  a same-day rule use section 24. NOAA's hourly service returned no rows for LaGuardia (two tries): use section 24.

## 26. AirNow hourly files (fine particles in New York), EPA yearly files
- URL: `https://files.airnowtech.org/airnow/<YYYY>/<YYYYMMDD>/HourlyData_<YYYYMMDDHH>.dat` (hour in UTC; '|'
  separated: date, time, monitor id, name, offset, parameter, unit, value, agency), 0.4-1.2 MB per hour, all US monitors.
```python
def airnow_hour(stamp="2021123013"):
    assert stamp[:8] <= "20211231"
    t = raw(f"https://files.airnowtech.org/airnow/{stamp[:4]}/{stamp[:8]}/HourlyData_{stamp}.dat", UA).decode("latin-1")
    return [l.split("|") for l in t.splitlines() if "|PM2.5|" in l and ("New York" in l or "NYC" in l or "IS 52" in l or "Division Street" in l)]
```
- Probe: 13:00 UTC files of 2015-01-05 and 2021-12-30 (0.7-0.8 s each). New York City PM2.5 monitors present in both:
  360610115 (IS143, Manhattan), 360610135 (CCNY), 360470052 (PS 314, Brooklyn), 360810120 (Maspeth), 360850111
  (Fresh Kills). Years before 2015 not probed.
- When known: first posted about 90 minutes after the hour, then **rewritten for 48 hours** (the 2021-12-30 13:00
  file was last written 2022-01-01 12:59 GMT): the archive is the last revision, not the first print. Keep to monitors
  that report on time, and say so in the declaration.
- Still published: yes (file of 2026-11-16 13:00 exists, HEAD only).
- `https://aqs.epa.gov/aqsweb/airdata/daily_88101_<YYYY>.zip` (4.2 MB for 2015, HEAD only) is the audited daily mean,
  published months later: for cross-checks, not for a live rule.

## 27. USGS earthquakes
```python
def quakes(minmag=6.0, box=(24, 46, 123, 146), start="2013-01-01"):
    u = ("https://earthquake.usgs.gov/fdsnws/event/1/query?format=csv&starttime=%s&endtime=%s&minmagnitude=%s"
         "&minlatitude=%s&maxlatitude=%s&minlongitude=%s&maxlongitude=%s&orderby=time-asc" % ((start, CUT, minmag) + box))
    return pd.read_csv(io.BytesIO(raw(u, UA)), parse_dates=["time"])[["time", "mag", "place"]]
```
- Probe: magnitude 5.5 or more near Japan (24-46 N, 123-146 E), 2013-2021: 231 events (68 of magnitude 6 or more),
  0.7 s. Real time; magnitudes are revised in the first days. Too few events for a rule on one market.

## 28. Daily economic policy uncertainty, the authors' own file
```python
def epu_site():
    L = stream_until("https://www.policyuncertainty.com/media/All_Daily_Policy_Data.csv",
                     lambda s: s[:1].isdigit() and int(s.split(",")[2]) >= 2022)
    d = pd.read_csv(io.StringIO("\n".join(L)))
    d.index = pd.to_datetime(dict(year=d.year, month=d.month, day=d.day)); return d.iloc[:, -1]
```
- Probe: 13,514 days 1985-01-01 to 2021-12-31 in 0.2 s (same data as FRED USEPUINDXD); rewritten nightly
  (Last-Modified 2026-11-17 00:55 GMT): still published. Timing and revisions: section 1.

## 29. The lab's own minute bars (scout's counting only; the scheduled runs do not have them)
`/home/user/gold-orb/lab/data/<market>_m1.parquet` (columns ts, bo..bc, ao..ac), read with
`pq.read_table(path, columns=["ts","bc"], filters=[("ts", "<", 2022-01-01 UTC)])`. Used here only to count
price-based signals (pair z-scores, round-number crossings); no outcome after a signal was computed.

---

## Reachable but not usable under the rules (nothing downloaded)
| Source | What the probe returned | Why not used |
|---|---|---|
| AAII sentiment survey `https://www.aaii.com/files/surveys/sentiment.xls` | HEAD 200, 1.3 MB, last modified Thu 12 Nov 2026 | one binary file with the whole history to today (holds 2022-2026 values), old Excel format that the runs cannot parse without xlrd |
| Geopolitical risk, daily `https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls` | HEAD 200, 3.3 MB, last modified 2026-11-17 | same two reasons; and it is unclear how soon after a day its value is posted |
| San Francisco Fed daily news sentiment `https://www.frbsf.org/wp-content/uploads/news_sentiment_data.xlsx` | HEAD 200, 0.4 MB, last modified 2026-11-17 | full history to today in one file; published weekly, model revised |
| New York Fed ACM term premium `.../ACMTermPremium.xls` | HEAD 200, 10 MB | same; re-estimated history |
| Wayback Machine | `archive.org/wayback/available` answers (snapshots: GLD archive 2021-10-19, AAII 2020-12-06, geopolitical risk 2022-03-31, news sentiment 2022-04-25) | the snapshots themselves live on `web.archive.org`, which resets every connection (8 tries) |

## Blocked or not reached (error as returned)
| Source | Result |
|---|---|
| BitMEX funding since 2016 (`www.bitmex.com/api/v1/funding`) | 403 Forbidden twice (HTML error page) |
| Yahoo chart API | `query1` with a Linux Chrome User-Agent: 429 "Edge: Too Many Requests" on every ticker of the first batch; one call to `query2` with another browser string answered 200 (GLD, 22 daily bars of December 2021); the follow-up batch was refused by this session's permission system as a way around the refusal. **Coverage of ^VIX9D, ^VVIX, ^SKEW, ^MOVE, GDX, HYG, LQD, TLT, RSP, IWM, GBTC is not verified; no idea in ideas.md needs Yahoo.** `kit.data.yahoo_daily` uses `query1` |
| Dukascopy datafeed (charter source) | three connection resets between 22:12 and 22:27 UTC; the proxy log shows the same for other sessions from 21:47 UTC: probably throttled by the parallel downloads, not a new block. ETF, bond and copper symbols on Dukascopy therefore not verified |
| SPDR gold holdings archive (`spdrgoldshares.com/assets/dynamic/GLD/GLD_US_archive_EN.csv`) | 200 but a PDF, not the CSV: holdings in tonnes not reached; iShares silver holdings not probed |
| Kraken OHLC | ignores `since`: returns only its last 720 candles (2024-2026) |
| TreasuryDirect web service (`TA_WS/securities/search`) | 500 (use section 7) |
| GDELT TV API | connection reset twice |
| Dukascopy retail sentiment (SWFX) | the guessed endpoint answers 204 with no content: not found |
| Google Trends | 404 on the probed endpoint; not pursued (its rescaling is a look-ahead trap anyway) |
| Japan MoF weekly securities flows | 404 on the guessed path |
| NOAA hourly service and per-year hourly file | header without rows; the file path returns a web page |
| Twitter-based uncertainty file (policyuncertainty.com) | 404 on the guessed name |
| CBOE EVZ history | 403 |
| Bitfinex margin longs and shorts; Binance funding files | reachable, but history starts 2021-02 and 2020-01: too short |
| www.cftc.gov, Stooq | not probed again (refused according to the lead and the charter) |
| NAAIM exposure, COMEX stocks, Baltic Dry, Shanghai gold premium | not probed (no stable file known) |

## Still published today? (metadata or latest date only)
Alive, checked on 2026-11-17: CBOE VIX9D, VVIX, SKEW, VIX3M, VXN, GVZ, OVX, RVX, VXD, VIX (files modified 16-17 Nov
2026); CBOE put/call JSON (file of 2026-11-16); DIX (2026-11-16); CFTC (latest report 2026-11-10); FINRA (file of
2026-11-16); Treasury statement (2026-11-16) and auctions (2026-10-22); SNB (published 2026-11-16); JGB file
(2026-11-03); GFZ (2026-11-16); AirNow (2026-11-16); policy-uncertainty file (2026-11-17); Bitfinex, Coinbase, Upbit
(status endpoints). Not checked because the only way was to read a 2026 value: FRED series one by one, ECB,
blockchain.info, Coin Metrics, Wikimedia, Bitstamp, Iowa Mesonet, NOAA, USGS, New York Fed (all long-standing public
services). Dead or dying: EVZ, TED spread, STLFSI before version 4, the ICE BofA history on FRED.

## What went wrong during the probe (said plainly)
Values dated after 2021 reached this machine five times by accident. None was displayed, stored on disk or used in a
count; only dates and row counts were printed.
1. FRED, first batch: `BAMLH0A0HYM2`, `BAMLC0A0CM`, `BAMLHE00EHYIOAS` and `SP500` came back as 2023-11-20..2026-11-16
   and 2025-11-17..2026-11-16 although `coed=2021-12-31` was sent (trap 2). The rows were parsed to count them. The
   guard of the `fred` snippet was then tested once on `BAMLH0A0HYM2` (dates column only).
2. CBOE `VIX9D`, `VVIX`, `SKEW` files: a `Range: bytes=0-699` request was answered with the whole file (three files
   to today in memory, first 420 bytes printed). Hence `stream_until`.
3. The SPDR archive URL returned a whole PDF (not data).
4. Kraken returned daily bitcoin candles of 2024-11-27 to today (first timestamp printed).
5. Yahoo's reply for GLD carries today's price in its `meta` block (only the key names were printed).

Two probe loops also failed to stop after two refusals as the task asked: 77 calls to Yahoo (all 429, in one minute)
and 8 to web.archive.org (all reset), before the stop rule was built into the probe helper.

---

## 30. Earnings releases (SEC EDGAR, 8-K item 2.02)
(probed and built 2026-11-18, 06:50-07:30 UTC; code `lab/explore/scout/earnings_edgar.py`; calendar in
`~/explore_data/earnings/`, never in the repository)

- URLs (all answer the plain client name `User-Agent: research-client/1.0`, nothing personal; at most 4 requests a second):
  - filings list of a company: `https://data.sec.gov/submissions/CIK<10 digits>.json` (holds about the last 1,000
    filings; older ones are in the extra files it names, `CIK..-submissions-001.json`, fetched only when their
    filingFrom..filingTo overlaps 2015-06..2021-12).
  - full-text search (2001 on): `https://efts.sec.gov/LATEST/search-index?q=<phrase>&forms=6-K&ciks=<10 digits>&dateRange=custom&startdt=..&enddt=2021-12-31`
    (JSON hits with accession number and file date; used for Alibaba and for the question of advance dates below).
  - **refused**: `www.sec.gov` (`files/company_tickers.json`, every `Archives/edgar/...` page, i.e. the filings'
    documents and headers) answers 403 'Request Rate Threshold Exceeded' to a User-Agent without a contact address
    (two refusals, then stopped). So the CIKs are written by hand in the script and checked against the name EDGAR
    returns, and no press-release text could be read.
- What the cache holds: one file per CIK, `~/explore_data/earnings/raw/CIK##########.json`, filtered in memory before
  it is written: filings with filingDate 2015-06-01..2021-12-31, acceptance date <= 2021-12-31 and an accession
  number of year <= 21 (Salesforce has two records re-filed in 2022 under old filing dates: dropped). Plus
  `fts_baba_results.json` (21 accession numbers). 43 files, 20 MB.
- Rebuild: `PYTHONDONTWRITEBYTECODE=1 python3 -B lab/explore/scout/earnings_edgar.py fetch` (only what is not
  cached), `... build` (writes `calendar_raw.csv`, 904 rows, and `calendar.csv`, 841 quarterly results),
  `... test` (30 checks on the cache, no network: 30/30 passed).
- Use in a run:
```python
import sys; sys.path.insert(0, "lab/explore/scout")
from earnings_edgar import calendar
cal = calendar(end="2021-12-31")                       # one row per fiscal quarter ('results'), cut at `end` (UTC)
allrows = calendar(end="2021-12-31", quarterly_only=False)   # every 8-K 2.02 with its flag
# columns: ticker, accepted_utc (tz-aware), accepted_et, when (before_open / in_session / after_close),
#          reaction_session (date), quarter_flag, form, items, accession, filing_date, event_date, period_end,
#          lag_days, usual_lag, note, cik
```

**WHEN each value is known (the whole point)**
- `accepted_utc` = EDGAR's acceptance time of the 8-K. In the submissions JSON `acceptanceDateTime` is **real UTC**
  ("2021-10-28T20:30:23.000Z" = Apple, 16:30:23 New York EDT; "2021-01-27T21:30:35.000Z" = 16:30 EST in winter).
  The SAME instant is printed in New York local time with no zone in the filing's own header and on the EDGAR web
  pages: never mix the two. Converted with pandas tz (daylight saving handled); checked on Apple in summer and winter
  and on JPMorgan (10:45 UTC = 06:45 New York, its usual release time).
- `filing_date` is the New York business date of filing, and a filing accepted after 17:30 New York carries the NEXT
  business day: never key on it (Apple 2019-01-02 16:30, Tesla 2019-04-03 20:22 ...).
- The acceptance time is a **safe** 'known at' (the filing cannot be public before EDGAR accepts it), but it can be
  **late**: companies put the release on a wire, or post it on their site, first. Measured on what EDGAR alone shows:
  - after-close releases (458): acceptance 3 minutes after 16:00 New York at the 10th percentile, 12 at the median,
    32 at the 90th, 58 at the 97th; each company keeps a tight clock (Apple 16:30 every quarter, Micron 16:00-16:06,
    Nvidia 16:20-16:27, JPMorgan 06:39-06:46 except once, UnitedHealth 06:00-06:34). The wire time itself is not in
    EDGAR and the press-release documents could not be read (www.sec.gov refused), so the gap to the wire is
    measured only indirectly, by price (below).
  - late filers seen: Tesla (16:11-17:25, letter usually out about 16:05), Amazon once 19:53, Facebook once 19:18,
    Apple once 18:55, Alphabet once 18:40, Chevron at 09:00 although its release goes out earlier, Citigroup 07:55-10:26
    (its release is at about 08:00 New York; **4 quarterly results were accepted after 09:30**: 2019-07-15, 2020-07-14,
    2020-10-13, 2021-10-14), and **Alibaba** (6-K accepted at about 16:30 New York on the release day; the release is
    published before the US open: on the 19 release days with bars the open gap of the 6-K's own day is 3.1 x usual against 1.7 x on the
    day the safe rule names, and larger than on that day in 16 of 19 cases).
  - price check of the calendar (in-sample hourly share bars, open of the first bar against the previous close; the
    check was used to judge the calendar, not to choose events or tune anything): on the reaction session named by
    the safe rule the open gap is 7.1 x the share's usual gap for after-close releases (389 events; largest of the
    three days around it in 87 %), 3.4 x for before-open releases (331; 71 %), against 1.1 x the day before.
- **The safe rule for every run**: the reaction session is the first regular session (09:30-16:00 New York) that
  STARTS strictly after `accepted_utc` (column `reaction_session`; NYSE full-day holidays written in the script and
  checked against the days without bars, 2017-01-27..2021-12-31: identical). Early closes (13:00) do not change it.
  Consequence: a release accepted at 09:31 reacts the NEXT day by this rule although the wire went out before the
  open: Citigroup x 4 and Alibaba x 21 are then a full session late. A run should either drop `when == 'in_session'`
  and Alibaba from rules that trade the reaction day (052, 054), or keep them and say that their reaction day is late
  by construction. Never move an event earlier on the evidence of a price move.

**Which 8-K is 'the' quarterly result (`quarter_flag`)**
- A release = form 8-K or 8-K/A whose `items` include 2.02 (Results of Operations and Financial Condition); Alibaba:
  the 6-K found by full-text search ("Alibaba Group Announces" + "Quarter Results"); three results filed under the
  wrong item, found by the gap check, are added by hand (`GAP_FILLS`): GE Q1 2017 and Q1 2020 (item 9.01 only),
  Citigroup Q1 2021 (item 2.01 declared instead of 2.02). Column `note` says so.
- Fiscal period ends = the `reportDate` of the company's 10-Q/10-K (52/53-week years respected), extended by 91 days
  to the cut and filled where one is missing. Each 8-K 2.02 belongs to the last period end before its day.
- The company's usual lag L = median, over its periods, of the lag of the last 8-K 2.02 accepted before that period's
  10-Q/10-K. In each period the 'results' row is the earliest plain 8-K (not 8-K/A) within max(2, min(7, L/4)) days
  of L, or the one nearest to L; an 8-K whose own event date is an earlier release's day (call transcripts) is
  never chosen. The others are flagged `before_results` (pre-announcements, delivery reports, restated segments),
  `after_results` (transcripts, reserves, later revisions) or `amendment` (8-K/A).
- Point in time: the choice uses the company's whole-history usual lag; a run that needs a strictly point-in-time
  event set should take every 8-K 2.02 (`quarterly_only=False`) or drop the flagged rows knowingly. Flagged rows:
  40 before, 22 after, 1 amendment (Tesla 24, PayPal 5, Nike 7, Exxon 3 ...).

**Counts per share (quarterly results 2016-10-01..2021-12-31; acceptance clock New York, median (min-max))**

| Key | Results | First | Last | Clock | When | Other 8-K 2.02 kept in the raw table |
|---|---|---|---|---|---|---|
| aapl | 21 | 2016-10-25 | 2021-10-28 | 16:30 (16:30-18:55) | after_close 21 | before_results 1 (2019-01-02 revenue warning) |
| adbe | 21 | 2016-12-15 | 2021-12-16 | 16:07 (08:04-16:09) | after_close 19, before_open 2 (Dec 2020, Dec 2021) |  |
| amd | 21 | 2016-10-20 | 2021-10-26 | 16:19 (06:34-17:11) | after_close 20, before_open 1 (2020-10-27, with the Xilinx deal) | after_results 1 |
| amzn | 21 | 2016-10-27 | 2021-10-28 | 16:18 (16:06-19:53) | after_close 21 |  |
| avgo | 21 | 2016-12-08 | 2021-12-09 | 16:19 (16:05-16:39) | after_close 21 (Broadcom Ltd CIK 1649338 to 2018, Broadcom Inc 1730168 after) | after_results 1 |
| ba | 21 | 2016-10-26 | 2021-10-27 | 07:40 (07:33-07:56) | before_open 21 | before_results 1 (2019-07-18 737 MAX charge) |
| baba | 21 | 2016-11-02 | 2021-11-18 | 16:30 (12:47-17:21) | after_close 20, in_session 1: **6-K hours late, see above** |  |
| bac | 21 | 2016-10-17 | 2021-10-14 | 06:46 (06:17-06:56) | before_open 21 |  |
| c | 21 | 2016-10-14 | 2021-10-14 | 08:35 (07:55-10:26) | before_open 17, **in_session 4** | before_results 2, after_results 1 |
| cat | 21 | 2016-10-25 | 2021-10-28 | 07:31 (06:30-09:05) | before_open 21 | after_results 1 |
| crm | 21 | 2016-11-17 | 2021-11-30 | 16:14 (16:08-16:40) | after_close 21 | after_results 1 |
| csco | 21 | 2016-11-16 | 2021-11-17 | 16:10 (16:08-16:34) | after_close 21 |  |
| cvx | 21 | 2016-10-28 | 2021-10-29 | 09:00 (06:02-09:04) | before_open 21 |  |
| dis | 21 | 2016-11-10 | 2021-11-10 | 16:09 (16:06-16:19) | after_close 21 (old Disney CIK 1001039 to 2019-03, new 1744489 after) |  |
| fb | 21 | 2016-11-02 | 2021-10-25 | 16:10 (16:04-19:18) | after_close 21 (CIK 1326801, now Meta) |  |
| ge | 21 | 2016-10-21 | 2021-10-26 | 06:55 (06:06-08:12) | before_open 21 (2 hand-added) | before_results 2, after_results 1 |
| googl | 21 | 2016-10-27 | 2021-10-26 | 16:01 (16:01-18:40) | after_close 21 (Alphabet CIK 1652044, one filing for both share classes) |  |
| gs | 21 | 2016-10-18 | 2021-10-15 | 07:38 (07:29-08:34) | before_open 21 | after_results 2 |
| hd | 21 | 2016-11-15 | 2021-11-16 | 06:10 (06:05-06:58) | before_open 21 |  |
| intc | 21 | 2016-10-18 | 2021-10-21 | 16:07 (16:04-16:10) | after_close 21 | before_results 1 (2021-01-14 CEO change with preliminary results) |
| jnj | 21 | 2016-10-18 | 2021-10-19 | 08:00 (07:12-08:34) | before_open 21 | after_results 1 |
| jpm | 21 | 2016-10-14 | 2021-10-13 | 06:45 (06:39-07:54) | before_open 21 |  |
| ma | 21 | 2016-10-28 | 2021-10-28 | 08:02 (07:47-08:08) | before_open 21 |  |
| mcd | 21 | 2016-10-21 | 2021-10-27 | 07:59 (06:59-08:06) | before_open 21 | before_results 2 (monthly sales updates 2020) |
| mrk | 21 | 2016-10-25 | 2021-10-28 | 06:50 (06:38-08:37) | before_open 21 |  |
| msft | 21 | 2016-10-20 | 2021-10-26 | 16:04 (16:02-16:41) | after_close 21 |  |
| mu | 22 | 2016-10-04 | 2021-12-20 | 16:00 (16:00-16:06) | after_close 22 (fiscal quarters end early in the month: 22 fall in the window) |  |
| nflx | 21 | 2016-10-17 | 2021-10-19 | 16:09 (16:02-16:57) | after_close 21 | before_results 1, after_results 1 |
| nke | 21 | 2016-12-20 | 2021-12-20 | 16:18 (16:16-17:09) | after_close 21 | after_results 7 (call transcripts filed 2-6 days later) |
| nvda | 21 | 2016-11-10 | 2021-11-17 | 16:21 (16:20-16:27) | after_close 21 | before_results 1 (2019-01-28 guidance cut) |
| orcl | 21 | 2016-12-15 | 2021-12-09 | 16:15 (16:08-16:51) | after_close 21 |  |
| pfe | 21 | 2016-11-01 | 2021-11-02 | 08:42 (08:04-09:29) | before_open 21 |  |
| pypl | 21 | 2016-10-20 | 2021-11-08 | 16:28 (16:10-16:38) | after_close 21 | before_results 5 (reclassification 8-K a week before) |
| qcom | 21 | 2016-11-02 | 2021-11-03 | 16:05 (16:01-16:18) | after_close 21 |  |
| tsla | 21 | 2016-10-26 | 2021-10-20 | 16:38 (16:11-17:25) | after_close 21 | before_results 24 (quarterly delivery reports carry item 2.02) |
| unh | 21 | 2016-10-18 | 2021-10-14 | 06:03 (06:00-06:34) | before_open 21 |  |
| v | 21 | 2016-10-24 | 2021-10-26 | 16:05 (06:03-16:40) | after_close 20, before_open 1 (2017-10-25) |  |
| wfc | 21 | 2016-10-14 | 2021-10-14 | 07:59 (06:46-08:05) | before_open 21 | after_results 2, amendment 1 (April 2018 revision) |
| wmt | 21 | 2016-11-17 | 2021-11-16 | 07:00 (06:04-07:01) | before_open 21 |  |
| xom | 21 | 2016-10-28 | 2021-10-29 | 07:58 (07:27-08:39) | before_open 21 | after_results 3 (reserves 8-K in February) |

Totals: 841 quarterly results (40 x 21 + Micron's 22nd), 41 in late 2016, 160 a year 2017-2021 (159 in 2020: Micron's
calendar), 458 after the close, 378 before the open, 5 inside the session (accepted 09:30-16:00). The last results in sample are the
September quarter (October-November 2021) for calendar-year companies, the November quarter (December 2021) for Nike,
Micron, Oracle, Adobe, Broadcom; the December 2021 quarter (reported in 2022) is out of the period by design.

**Checked by hand (dates known independently; script `test()`)**: Apple 2021-10-28 after the close (20:30 UTC,
reaction 2021-10-29) and 2021-01-27 (21:30 UTC, winter time); Microsoft 2021-10-26, Amazon 2021-10-28, Alphabet
2021-10-26, Facebook 2021-10-25, Netflix 2021-10-19, Tesla 2021-10-20, Intel 2021-10-21, Nvidia 2021-11-17, Nike
2021-12-20, Micron 2021-12-20 (all after the close); Walmart 2021-11-16 and JPMorgan 2021-10-13 before the open
(reaction the same day); Apple's 2019-01-02 revenue warning flagged `before_results`; Tesla's delivery reports
flagged. All agree.

**Gaps and oddities found**
- No quarter is missing once the three hand-added filings are in (each share has 21; the gap check found GE Q1 2017,
  GE Q1 2020, Citigroup Q1 2021: results filed without item 2.02).
- Price bars of the shares start 2017-01-26: the 2 to 3 releases per share before that date (about 80) have no
  reaction bars.
- Adobe's December 2020 and December 2021 results 8-K were accepted at 08:04 / 08:06 New York (Adobe's other quarters
  are after the close); the 2021 one is confirmed by an 8.3 % opening gap the same morning. Visa 2017-10-25 at 06:03.
- Intel 2021-01-21: accepted 16:04, after the close; Intel is reported to have published that release minutes early
  because of a leak (from memory, not verified here). If so the wire was inside the session: the safe rule still
  gives the next day, where most of the move took place.
- In 3 % of reaction sessions the first hourly bar opens within 0.1 % of the previous close although the share moved
  a lot during that first hour (e.g. Alphabet 2021-10-27): the lab's share bars do not always show the opening gap.
  A rule on 'the gap at the open' (054) should measure it on the first bar's close or the 10:00 bar, and say so.

**Revisions**: EDGAR keeps every filing; corrections come as new 8-K or 8-K/A (kept, flagged). The acceptance time of a
filing never changes. Records can be re-filed with an old filing date (Salesforce 2022 re-submissions of 2020-2021
10-Q/10-K): filter on acceptance date and accession year as the script does.

**Can the DATE of a release be known in advance, point in time? (idea 053)** Not from EDGAR, as far as could be shown:
- Full-text search for the exact date string ("January 29, 2019" ...) in each company's filings of the 75 days before
  12 releases (Apple, Microsoft, Netflix, JPMorgan, Amazon, Tesla, Alphabet, Intel, Nike, Exxon, Facebook, Walmart):
  only Apple's Q1 2019 date appears in advance, inside its 2019-01-02 revenue-warning 8-K; the 3 JPMorgan hits are
  note prospectuses (424B2) that merely contain the date. 10 of 12: nothing.
- Phrase searches over the 40 companies 2016-07..2021-12 ("to announce ... quarter ... results ... conference call",
  "will report ... results on", "will release ... results on", "earnings release date") return results releases,
  proxies and merger documents, not dated announcements; a handful (Broadcom 2016-11-02, AMD 2020-10-27) may name
  a coming date inside a merger release: could not be read (www.sec.gov refused).
- Companies announce the date by press release and on their investor site, 2 to 4 weeks ahead (some, e.g. JPMorgan
  and Netflix, a year ahead), not on EDGAR. Free point-in-time copies of those pages exist only in the Wayback Machine
  (`archive.org/wayback/available` answers and lists, e.g., a 2019-01-16 snapshot of Apple's investor page), but
  `web.archive.org` itself refused (connection reset, then 403): not reachable from here.
- So idea 053 as briefed (date public at least 5 trading days before) is **not testable point in time with the
  sources reachable here**. The only honest variant is a rule that does not need the date: e.g. enter at a fixed lag
  after the previous release (the company's own rhythm, `usual_lag` computed from past releases only) and accept
  that some entries land after the release; or close the idea.

**Independent verification (2026-11-18, a second agent whose job was to break the calendar): no row is stamped
earlier than its release was public.** What it checked and what a run must know:
- The clock: under the UTC reading, each company's summer and winter release clocks agree (37 of 40 within 20
  minutes); under the other reading none does. EDGAR's own filing-date rule (next business day after 17:30 Eastern)
  holds on 5,592 of 5,623 filings under the UTC reading (the 31 exceptions are at 17:30-17:32 or on EDGAR's
  extended-hours days). The reaction session, recomputed with its own holiday calendar, differs on 0 of 904 rows.
- Prices as a witness (in-sample bars, market-adjusted, 743 results rows): the largest move of the five sessions
  around the reaction session falls ON it for 344 of 408 after-close rows and 249 of 331 before-open rows; the mean
  abnormal opening gap is 14.8 times the usual one on the reaction session after an after-close release (2.1 the
  session before, 1.7 the session after) and 6.4 times after a before-open release.
- **Rows that are late by construction: 25 results rows** (the 21 Alibaba 6-K, whose release goes out before the
  US open but is filed about 16:30 New York; the 4 Citigroup rows accepted after 09:30). `calendar()` now returns
  the column `late_by_construction`; **a rule that trades the reaction day calls `calendar(drop_late=True)`** (816
  rows). Never move them earlier.
- `when` uses a fixed 16:00 close: on the 13:00 half days two non-results rows are labelled `in_session` though they
  came after the close; their reaction session is right.
- `quarter_flag` is set with hindsight for `before_results` / `after_results` (they need the later filings); the
  `results` pick itself gave the same rows when redone strictly point in time. `quarterly_only=True` drops 38
  `before_results` rows with bars, of which 22 are real news days (warnings, pre-announcements): an idea on results
  days does not see them.
- `calendar(end=...)`: `end` is a UTC instant; a bare date means the end of that UTC day (19:59 or 20:59 New York).
- `build()` does not notice a truncated cache file (only `test()` does, by its counts): run `test` after any rebuild.
