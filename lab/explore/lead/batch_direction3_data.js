export const meta = {
  name: 'explore-direction3-data',
  description: 'Direction 3 of the open strategy search, data: a broad universe of US shares (S&P 500 list minus the lab\'s 40) with daily bars from Yahoo, and every 8-K of each company from SEC EDGAR with its acceptance time; an adversarial check of both',
  phases: [
    { title: 'Universe', detail: 'the list of companies with SEC numbers, sectors and dates added' },
    { title: 'Prices', detail: 'daily bars 2016-2021 from Yahoo, dividends, splits' },
    { title: 'Events', detail: 'every 8-K with items and acceptance time from EDGAR' },
    { title: 'Data verify', detail: 'break the universe, the prices and the calendar' },
    { title: 'Data repair', detail: 'only if something major is found' },
  ],
}

const SP = '/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad'
const DW = SP + '/d3_wt'
const MAIN = '/home/user/gold-orb'

async function run(prompt, opts) {
  try {
    const r = await agent(prompt, Object.assign({}, opts, { model: 'opus' }))
    if (r) return r
  } catch (e) {
    log('opus refused or failed for ' + (opts.label || '') + ': retrying on the session model')
  }
  return await agent(prompt, opts)
}

const COMMON = `CONTEXT
A trading lab runs a continuous search for new trading rules for a retail FP Markets account (CFDs, MetaTrader 5). Rules of the search: ${DW}/lab/explore/CHARTER.md. The lead's new plan is ${DW}/lab/explore/lead/DIRECTION3.md: READ IT FIRST. In short: on the lab's 40 large US shares the drift after results was nil for small reactions and strong after reactions of 8 % or more, but 80 events prove nothing; the honest test is the same rule on OTHER shares. That needs a broad universe of US shares with daily bars and an event calendar (every 8-K of each company with the time it became public). You build or check that data. Nobody runs a trading rule here: no return after an event is computed except to check the calendar's timing, and never to choose anything.
THE PERIOD: in sample only, to 2021-12-31. Never fetch, read, print or store anything dated 2022 or later. Two traps: (1) Yahoo's chart API puts a 'meta' block in every reply that carries TODAY's price and dates: never parse it beyond what is needed to detect an error, never print it, and strip it before anything is written to disk; (2) EDGAR's filings lists hold recent filings: filter in memory to acceptance times before 2022-01-01 before writing (the earlier script ${DW}/lab/explore/scout/earnings_edgar.py shows how, including records re-filed later under old dates).
SOURCES THAT ANSWER FROM THIS MACHINE (checked today): https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv (the current S&P 500 list: Symbol, Security, GICS Sector, GICS Sub-Industry, Headquarters Location, Date added, CIK, Founded); https://raw.githubusercontent.com/fja05680/sp500/master/ (history of the index's components and changes, CSV files; list the repository's files through the raw URLs named in its README if you need them); https://en.wikipedia.org/api/rest_v1/page/html/List_of_S%26P_500_companies (the same table plus a table of changes; the ordinary Wikipedia API answers 429); Yahoo https://query1.finance.yahoo.com/v8/finance/chart/<SYMBOL>?period1=<unix>&period2=<unix>&interval=1d&events=div%2Csplits (send a browser User-Agent); EDGAR https://data.sec.gov/submissions/CIK<10 digits>.json and the extra files it names (User-Agent "research-client/1.0", nothing personal, at most 5 requests a second; www.sec.gov refuses this client: do not use it). Be polite everywhere: a pause between requests (Yahoo: about one request a second), cache what you fetch, stop using a host after two refusals in a row and say so. Send nothing personal and nothing about this project in any request.
WHERE YOU WORK: ${DW} is a small working copy of the repository (lab/explore only). Write code only under ${DW}/lab/explore/scout/ and data only under ~/explore_data/ (never in the repository: it is public, and no price series may enter it). The lab's main copy ${MAIN} is read-only. The existing earnings calendar of the 40 shares is in ~/explore_data/earnings (read-only) and its documentation is the last section of ${DW}/lab/explore/scout/sources.md. Prepared hourly bars of the 40 shares are in ~/explore_data/h1 (read-only; keys = lower-case tickers; ~/explore_data/h1/info.json lists them).
Run NO git command. No sub-agents. THE MACHINE MAY RESTART, and this task may then be started again from the beginning: look at your output folders first; if an interrupted run of this same task left work there, read it critically and continue from it (reuse the cache); save your work to disk as you go. THE MACHINE IS SHARED: 4 processors and 15 GB of memory for three agents: at most 2 worker processes, memory under about 3 GB, no background process left running when you finish.
Python: PYTHONDONTWRITEBYTECODE=1 python3 -B ... (no __pycache__ in the working copy).
Write for a reader who was not there: plain sentences, exact numbers, the script that shows each claim.`

const U_SCHEMA = { type: 'object', properties: {
  summary: { type: 'string' }, n_companies: { type: 'integer' }, n_in_universe: { type: 'integer' },
  by_sector: { type: 'string' }, added_dates: { type: 'string', description: 'how many entered before 2017, in each year 2017-2021, after 2021 (those are out)' },
  oddities: { type: 'array', items: { type: 'string' } }, files: { type: 'array', items: { type: 'string' } } },
  required: ['summary', 'n_companies', 'n_in_universe', 'files'] }
const P_SCHEMA = { type: 'object', properties: {
  summary: { type: 'string' }, n_shares_with_bars: { type: 'integer' }, failures: { type: 'array', items: { type: 'string' } },
  coverage: { type: 'string' }, quality_checks: { type: 'string' }, how_a_run_uses_it: { type: 'string' },
  traps: { type: 'array', items: { type: 'string' } }, files: { type: 'array', items: { type: 'string' } }, what_went_wrong: { type: 'string' } },
  required: ['summary', 'n_shares_with_bars', 'failures', 'how_a_run_uses_it', 'traps', 'files'] }
const E_SCHEMA = { type: 'object', properties: {
  summary: { type: 'string' }, n_companies: { type: 'integer' }, n_8k: { type: 'integer' }, n_results: { type: 'integer' },
  counts: { type: 'string', description: 'results rows per company and year (distribution), other 8-K by item, rows flagged late' },
  how_a_run_uses_it: { type: 'string' }, traps: { type: 'array', items: { type: 'string' } },
  files: { type: 'array', items: { type: 'string' } }, what_went_wrong: { type: 'string' } },
  required: ['summary', 'n_companies', 'n_8k', 'n_results', 'how_a_run_uses_it', 'traps', 'files'] }
const VERDICT_SCHEMA = { type: 'object', properties: {
  verdict: { type: 'string', enum: ['ok', 'needs_fixes'] },
  issues: { type: 'array', items: { type: 'object', properties: { id: { type: 'string' }, severity: { type: 'string', enum: ['blocking', 'major', 'minor'] }, what: { type: 'string' }, evidence: { type: 'string' }, fix: { type: 'string' } }, required: ['id', 'severity', 'what', 'evidence', 'fix'] } },
  what_was_tested: { type: 'string' } }, required: ['verdict', 'issues', 'what_was_tested'] }
const FIX_SCHEMA = { type: 'object', properties: {
  per_issue: { type: 'array', items: { type: 'object', properties: { id: { type: 'string' }, status: { type: 'string', enum: ['fixed', 'partly', 'not_fixed', 'rejected'] }, change: { type: 'string' }, test: { type: 'string' } }, required: ['id', 'status', 'change', 'test'] } },
  tests: { type: 'string' }, how_a_run_uses_it: { type: 'string' }, limits: { type: 'array', items: { type: 'string' } }, files: { type: 'array', items: { type: 'string' } } },
  required: ['per_issue', 'tests', 'limits', 'files'] }

const U_PROMPT = `You build the list of companies for a broad test bed of US shares. Small job, done carefully: every later step reads this file.

${COMMON}

THE JOB
- Write ${DW}/lab/explore/scout/universe_us.py (fetch, cache in ~/explore_data/d1/raw_universe/, build) and the table ~/explore_data/d1/universe.csv with one row per COMPANY: key (lower-case ticker, letters and digits only: 'brkb' for BRK.B), yahoo (Yahoo's symbol: 'BRK-B'), ticker (as listed), name, cik (integer), sector, sub_industry, added (the date the share joined the index, ISO; empty if the source gives none), in_universe_from (the later of 2017-01-01 and 'added'), in_lab40 (true for the lab's 40 shares: ~/explore_data/h1/info.json; 'fb' is Meta), in_universe (true when not in_lab40, added before 2022-01-01, and not a second share class of a company already kept).
- Source: the constituents.csv above. Cross-check it against the Wikipedia table (count, tickers, dates added: say what differs) and say on which date the list was read.
- Share classes: one row per company (per CIK): keep the class with the larger trading volume if you can tell, else the first listed; name the dropped ones.
- A date 'added' in the future of the test (2022 or later) puts the share OUT of the universe (it was not in the index in sample). Dates missing or implausible: list them; treat a missing date as 'before 2017' only if the change tables show no addition of that ticker since 2017, and say which rule you applied to each.
- SURVIVORS ONLY: companies that left the index before today are missing. Using the change history (fja05680 repository or Wikipedia's change table), count how many companies were in the index at some time in 2017-2021 and are not in today's list, and name the 30 largest or best known. Do not add them (their histories and SEC numbers are another job); the count goes in the report.
- Checks in the script (a 'test' command): unique keys, unique CIK among in_universe rows, no in_lab40 row in the universe, every in_universe row has a CIK and a sector, 11 sectors, counts by sector and by year of 'in_universe_from'.
RETURN the structured result: a summary, the counts, by sector, by date added, the oddities, the files.`

const P_PROMPT = `You build daily price bars for a broad test bed of US shares. A split left in the bars, a wrong date or a price from after the period would make every later test wrong.

${COMMON}

THE JOB
- Input: ~/explore_data/d1/universe.csv (built just before you: rows with in_universe true; columns key, yahoo, cik, sector, in_universe_from). ALSO fetch the lab's 40 shares (in_lab40 true), marked as such: they let the daily bars be checked against the lab's own hourly bars (~/explore_data/h1/<key>.parquet through the kit: sys.path ${DW}/lab/explore, 'from kit import data', data.load_bars(key) gives split-adjusted hourly bars to 2021).
- Write ${DW}/lab/explore/scout/prices_d1.py (fetch, cache, build, test). For each share: Yahoo daily bars from 2016-01-01 to 2021-12-31 (period2 = 2022-01-01 00:00 UTC; drop any row dated after 2021-12-31), with events=div,splits. From each reply take ONLY the timestamps, the quote arrays (open, high, low, close, volume), and the dividend and split events dated 2021-12-31 or earlier. The 'meta' block carries today's price: do not print it, do not store it; the cache on disk holds the stripped reply. Say whether Yahoo's quote prices are adjusted for splits (they are, for every split up to today, including those after 2021: the LEVELS then carry later splits; ratios do not) and for dividends (the quote close is not; adjclose is): verify both on shares with a known split and a known large dividend inside 2016-2021.
- Output, outside the repository: ~/explore_data/d1/bars/<key>.parquet with a UTC index named 'time' = the session's OPEN (09:30 New York that day, converted to UTC with daylight saving), columns open, high, low, close (float), volume (the session's length in minutes: 390, or 210 on the 13:00 half days: the kit reads 'volume' as a count of minutes), shares (Yahoo's traded volume). One row per session. ~/explore_data/d1/dividends.csv (key, ex_date, amount, fraction = amount / previous close) and ~/explore_data/d1/splits.csv (key, date, ratio), both to 2021-12-31 only. ~/explore_data/d1/info.json (per key: first and last bar, rows, median price, median daily range in bp, median dollar volume).
- Quality, each as a check in the script's 'test' command, with counts in the report: sessions match the NYSE calendar (the 40 shares' hourly bars show which days traded: use them as the calendar); no duplicate or missing session inside a share's life; high >= max(open, close) and low <= min(open, close); no zero or negative price; no overnight move that looks like an unadjusted split (within 3 % of a usual ratio) unless explained; rows with zero volume; shares whose history starts after 2017-01-01 (list with the first date) or that Yahoo does not have (list); for the lab's 40 shares, the daily close against the last hourly close of the same day and the daily open against the first hourly bar's open (median and worst differences in bp: BID bars against Yahoo's trade prices, so a few bp are normal; a split or a date shift is not).
- Liquidity figures for the cost model (no trading rule): per share and year the median price, the median daily range in bp and the median dollar volume; the share of universe shares with a median price under 30 USD (the commission per share bites there).
- Polite fetching: about one request a second, at most 2 worker processes, retry twice with growing waits, stop after two refusals in a row from the host and report where you stopped (the job can be resumed from the cache).
RETURN the structured result: summary, the number of shares with bars, the failures, coverage, the quality checks with their numbers, how a run uses the bars (a text ready for the documentation), the traps, the files, what went wrong.`

const E_PROMPT = `You build the event calendar for a broad test bed of US shares: every 8-K of each company with the time it became public, from the US SEC's EDGAR. A time that is too early is a look-ahead in every later test; a time a session late tests the wrong day.

${COMMON}

THE JOB
- Input: ~/explore_data/d1/universe.csv (rows with in_universe true: key, ticker, cik). The method exists and was verified on 40 shares: ${DW}/lab/explore/scout/earnings_edgar.py (read it fully, and the last section of ${DW}/lab/explore/scout/sources.md, including the independent verification at its end). Do NOT edit that script. Write a new one, ${DW}/lab/explore/scout/events_edgar.py, that imports what it can from it and works from the universe file. Cache: ~/explore_data/events_d1/raw/ (filtered replies only: nothing accepted on or after 2022-01-01, nothing re-filed later under an old date).
- For each company: its filings list (and the extra files it names) -> every 8-K and 8-K/A accepted from 2016-01-01 to 2021-12-31 with accession, acceptance time (UTC; the earlier work proved the field is real UTC), filing date, items, and the 10-Q / 10-K rows needed to date the fiscal quarters. Foreign filers of the list (6-K instead of 8-K), if any: list them and leave them out of the events (they have no items).
- Table ~/explore_data/events_d1/events_raw.csv, one row per 8-K: key, cik, accession, accepted_utc, accepted_et, form, items, when (before_open / in_session / after_close with the 13:00 half days handled), reaction_session (the first regular session, 09:30-16:00 New York, that STARTS strictly after the acceptance time; NYSE holidays as in the earlier script), has_202 (item 2.02), quarter_flag for the 2.02 rows (results / before_results / after_results / amendment, by the earlier script's rule: the usual lag from the fiscal period's end, computed per company; say how many companies needed a hand rule), late_by_construction (true when accepted during the session; the earlier work found such rows are a session late).
- A loader calendar(end, kind): kind='results' = one row per fiscal quarter (the results 8-K); kind='other' = 8-K rows WITHOUT item 2.02; kind='all'; drop_late as in the earlier script; cut at 'end' (a UTC instant; a bare date = the end of that UTC day; never after 2021-12-31).
- Checks in a 'test' command, with numbers in the report: about four results rows a year per company (list companies with fewer than 3 or more than 5 in a year, and why: fiscal calendars, late filers, results filed without item 2.02 as GE and Citigroup did); consecutive results 60 to 120 days apart; each company's summer and winter release clocks agree under the UTC reading (the earlier verifier's test); no acceptance after 2021-12-31 anywhere in the cache or the tables; the reaction session recomputed by a second, independent piece of code agrees on every row.
- Prices as a witness, if the daily bars are there (~/explore_data/d1/bars/<key>.parquet, built in parallel by another agent: use what exists when you reach this step, say how many shares you could check): for results rows, the absolute close-to-close move of sessions -2..+2 around the reaction session in units of the share's usual daily move, by 'when' class: it must peak at 0. This judges the calendar only; never choose or drop events by their later return.
- Counts for the lead's ideas (no return): results rows by year; 8-K rows without item 2.02 by item (1.01, 5.02, 7.01, 8.01 ...) and by year; how many sessions per share-year have no 8-K within two sessions.
- A new section at the END of ${DW}/lab/explore/scout/sources.md, in the style of the earnings section: 'Events of a broad universe of US shares (SEC EDGAR, every 8-K)': URLs, tested code, WHEN each value is known, flags, traps, counts.
- Fetching: at most 5 requests a second, cache every filtered reply, resume from the cache, stop after two refusals in a row and report where you stopped.
RETURN the structured result: summary, counts, how a run uses the calendar (a text ready for the charter or a brief), the traps, the files, what went wrong.`

function verifyPrompt(u, p, e) {
  return `You are the adversarial verifier of the data of a new test bed: a broad universe of US shares with daily bars and an event calendar. Three trading ideas will be judged on it tomorrow. A look-ahead in the universe, a split left in the prices, an event stamped early or a day late would make their verdicts wrong. Your job is to BREAK the data; you fix nothing.

${COMMON}
Edit NOTHING under ${DW} or ~/explore_data/d1 or ~/explore_data/events_d1; work in ${SP}/d3/verify/ (create it). The builders' reports (test them, do not trust them):
UNIVERSE: ${JSON.stringify(u, null, 1).slice(0, 3500)}
PRICES: ${JSON.stringify(p, null, 1).slice(0, 6000)}
EVENTS: ${JSON.stringify(e, null, 1).slice(0, 6000)}

WHAT TO ATTACK
1. THE UNIVERSE (~/explore_data/d1/universe.csv, scout/universe_us.py): look-ahead at inclusion (a share used before it joined the index; dates added that are wrong: check twenty against what you know); duplicates and share classes; the lab's 40 shares must be out; how many companies of 2017-2021 are missing because they left the index (survivors only) and what that does to a long-short event rule held five sessions (argue it; the builders must have said it plainly).
2. THE PRICES (~/explore_data/d1/bars, scout/prices_d1.py): run the script's tests. With your own code: any row after 2021-12-31, any 'meta' or current price in a cache file; splits (compare with splits.csv: no jump left on a split date; an unlisted jump that looks like a split); the session index (09:30 New York in UTC across daylight saving; holidays; half days); for the lab's 40 shares compare daily bars with the lab's hourly bars day by day (close, open, high, low) and list the worst mismatches; dividends (ten known ex-dates and amounts); bad ticks (a high far above both neighbours); shares with holes.
3. THE CALENDAR (~/explore_data/events_d1, scout/events_edgar.py): run its tests. With your own code, rebuild the 8-K list of ten companies from the cached replies and compare row by row; recompute the reaction session of every row; the release clocks in summer and winter; the results pick (about four a year: list every company-year that is off and judge the reason); prices as a witness on every share that has bars: the move must peak on the reaction session, by 'when' class; list companies whose results rows peak a session early or late more than a quarter of the time. Can any row be EARLY (stamped before the news was public)? Think of amendments, of results filed without item 2.02, of the hand rules.
4. THE THREE EVENT KINDS the lead will use (DIRECTION3.md ideas 059, 061, 062): results days; 8-K days without item 2.02; sessions with no 8-K nearby. Are the definitions computable from the tables without ambiguity (an 8-K accepted after the close belongs to the NEXT session; an 8-K/A; several 8-K on one day)? Give the counts of each kind with a daily move of 8 % or more, per year (a count of events and of absolute moves on the event day itself: no later return).
5. HYGIENE: nothing dated 2022 or later in any file under ~/explore_data/d1 and ~/explore_data/events_d1; nothing personal in any request (read the scripts' headers); no price series written inside ${DW}.
SEVERITY: blocking = look-ahead, wrong days for a whole class of events, splits left in; major = wrong but bounded (a few percent of rows); minor = documentation, isolated rows.
RETURN: verdict 'ok' or 'needs_fixes'; the issues (id D3-n, severity, what, evidence with numbers and the script that shows it, the fix you propose); what you tested, including what held and the counts of item 4.`
}

function fixPrompt(v) {
  return `You repair the data of a test bed (a broad universe of US shares: list, daily bars, event calendar) after an adversarial review. Fix what is real, reject what is not (with evidence), and prove each fix with a check in the scripts' own tests.

${COMMON}
Edit only the scripts under ${DW}/lab/explore/scout/ (universe_us.py, prices_d1.py, events_edgar.py), the new section of sources.md, and the data under ~/explore_data/d1 and ~/explore_data/events_d1 (rebuilt with the scripts). Your scratch: ${SP}/d3/fix/ (keep copies of what you change). The verifier's scripts are under ${SP}/d3/verify/.

THE VERIFIER'S ISSUES
${JSON.stringify(v, null, 1).slice(0, 24000)}

RULES: never move an event EARLIER because of a price move (prices may only show that a stamp is late; a late stamp is flagged, not moved); a row whose time cannot be shown safe is flagged so that a run can drop it; the scripts' tests must all pass after your changes; say in sources.md what a run must do with each flag.
RETURN the structured result: per issue (status, change, test), the last lines of the scripts' tests, the text a run needs, the limits that remain, the files.`
}

phase('Universe')
const u = await run(U_PROMPT, { label: 'universe', phase: 'Universe', schema: U_SCHEMA })
if (!u) return { universe: null }
log('Universe: ' + u.n_in_universe + ' shares of ' + u.n_companies + ' companies')
const [p, e] = await Promise.all([
  run(P_PROMPT, { label: 'daily prices', phase: 'Prices', schema: P_SCHEMA }),
  run(E_PROMPT, { label: '8-K calendar', phase: 'Events', schema: E_SCHEMA }),
])
if (!p || !e) return { universe: u, prices: p, events: e, verdict: null }
const v = await run(verifyPrompt(u, p, e), { label: 'data: verify', phase: 'Data verify', schema: VERDICT_SCHEMA })
if (!v) return { universe: u, prices: p, events: e, verdict: null }
log('Data verifier: ' + v.verdict + ', ' + v.issues.length + ' issue(s): ' + v.issues.map(i => i.id + ' ' + i.severity).join(', '))
const real = v.issues.filter(i => i.severity !== 'minor')
if (real.length === 0) return { universe: u, prices: p, events: e, verdict: v, fix: null }
const f = await run(fixPrompt(v), { label: 'data: repair', phase: 'Data repair', schema: FIX_SCHEMA })
return { universe: u, prices: p, events: e, verdict: v, fix: f }
