export const meta = {
  name: 'explore-prep-direction2',
  description: 'Prepare direction 2 of the open strategy search: extend the research kit to new markets with provisional costs (US share CFDs, oil) and to the slow track, with an adversarial verification; build a point-in-time earnings calendar from SEC EDGAR',
  phases: [
    { title: 'Kit: more markets, slow track', detail: 'provisional costs for shares and oil, local-only markets, slow-track bar, tests' },
    { title: 'Kit verify', detail: 'adversarial check' },
    { title: 'Kit fix', detail: 'fix what the verifier found' },
    { title: 'Earnings calendar', detail: 'SEC EDGAR 8-K item 2.02 acceptance times for the lab\'s shares' },
  ],
}

const SP = '/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad'
const KW = SP + '/kit_v2_wt'
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
A trading lab runs a continuous search for new trading rules for a retail FP Markets account (CFDs, MetaTrader 5). Every idea is tested with one shared research kit, ${KW}/lab/explore/kit (README.md there; 122 passing self-tests): data.py (period lock: in sample to 2021-12-31, one logged look at 2022-2025, never 2026), costs.py (FP costs from lab/r2/fp_costs.json), sim.py (hourly simulator, hedged pairs, exits on a condition), stats.py (bars, same-day null), judge.py (verdict), checks.py (look-ahead guards). Rules of the search: ${KW}/lab/explore/CHARTER.md. The lead has just changed the direction of the search (${KW}/lab/explore/lead/DIRECTION2.md: read it): company earnings on US share CFDs, a slow track (holds up to 40 trading days), and oil.
WHERE YOU WORK: ${KW} is a small working copy (lab/explore, lab/r2/fp_costs.json, lab/COSTS_FP.md, the ten rules' trades). The lab's main copy ${MAIN} is read-only for you (lab/COSTS_FP.md, lab/r2/fp_costs.json and its '_stocks' note, lab/prep_round3.py, lab/build_fp_frames.py, lab/goldlab/*.py hold the lab's conventions; lab/data holds the one-minute files, which you may read ONLY with a filter ts < 2022-01-01 inside the read, and only for mechanical work on costs and alignment, never to run or tune a trading rule). Prepared hourly bars (in sample only) are in ~/explore_data/h1: the 14 markets of the kit, plus 'oil' and 40 US shares (keys = lower-case tickers; ~/explore_data/h1/info.json lists them; shares have 7 hourly bars a day, 09:30-16:00 New York, the first bar labelled at the full hour though trading starts at half past). Run NO git command. No sub-agents. Never download from Dukascopy. Never fetch, read or compute anything dated 2022 or later.
THE MACHINE MAY RESTART, and this task may then be started again from the beginning: before anything else look at the working copy (compare with ${MAIN}/lab/explore) and at your scratch folder; if an interrupted run of this same task left work there, read it critically and continue from it; save your work to disk as you go.
THE MACHINE IS SHARED: 4 processors and 15 GB of memory for three agents: at most 3 worker processes, memory under about 3 GB, no background process left running when you finish.
Python: PYTHONDONTWRITEBYTECODE=1 python3 -B ... (no __pycache__ in the working copy). Self-test: PYTHONDONTWRITEBYTECODE=1 python3 -B ${KW}/lab/explore/kit/test_kit.py must end "N/N checks passed" (about 2 minutes).`

const BUILD_SCHEMA = { type: 'object', properties: {
  summary: { type: 'string' },
  costs_table: { type: 'string', description: 'for oil and a few shares: every provisional figure, its value and where it comes from' },
  tests: { type: 'string' }, how_a_run_uses_it: { type: 'string' },
  limits: { type: 'array', items: { type: 'string' } }, files: { type: 'array', items: { type: 'string' } } },
  required: ['summary', 'costs_table', 'tests', 'how_a_run_uses_it', 'limits', 'files'] }
const VERDICT_SCHEMA = { type: 'object', properties: {
  verdict: { type: 'string', enum: ['ok', 'needs_fixes'] },
  issues: { type: 'array', items: { type: 'object', properties: { id: { type: 'string' }, severity: { type: 'string', enum: ['blocking', 'major', 'minor'] }, what: { type: 'string' }, evidence: { type: 'string' }, fix: { type: 'string' } }, required: ['id', 'severity', 'what', 'evidence', 'fix'] } },
  what_was_tested: { type: 'string' } }, required: ['verdict', 'issues', 'what_was_tested'] }
const FIX_SCHEMA = { type: 'object', properties: {
  per_issue: { type: 'array', items: { type: 'object', properties: { id: { type: 'string' }, status: { type: 'string', enum: ['fixed', 'partly', 'not_fixed', 'rejected'] }, change: { type: 'string' }, test: { type: 'string' } }, required: ['id', 'status', 'change', 'test'] } },
  tests: { type: 'string' }, how_a_run_uses_it: { type: 'string' }, limits: { type: 'array', items: { type: 'string' } }, files: { type: 'array', items: { type: 'string' } } },
  required: ['per_issue', 'tests', 'how_a_run_uses_it', 'limits', 'files'] }
const EARN_SCHEMA = { type: 'object', properties: {
  summary: { type: 'string' },
  per_ticker: { type: 'array', items: { type: 'object', properties: { ticker: { type: 'string' }, events: { type: 'integer' }, first: { type: 'string' }, last: { type: 'string' }, note: { type: 'string' } }, required: ['ticker', 'events'] } },
  how_a_run_uses_it: { type: 'string' }, traps: { type: 'array', items: { type: 'string' } },
  files: { type: 'array', items: { type: 'string' } }, what_went_wrong: { type: 'string' } },
  required: ['summary', 'per_ticker', 'how_a_run_uses_it', 'traps', 'files'] }

const BUILD_PROMPT = `You extend a research kit used to judge trading ideas. A bug here makes every later verdict wrong: work as carefully as the existing code does and prove each claim with a test.

${COMMON}
Edit only ${KW}/lab/explore/kit. Your scratch: ${SP}/kit_v21/builder/ (create it; keep a copy of the kit before your changes there).

WHAT TO ADD (kit v2.1), each with tests in test_kit.py and a README section, without changing any result of the 122 existing checks nor anything for the 16 existing markets

A. NEW MARKETS WITH PROVISIONAL COSTS. A file kit/extra_costs.json, read by costs.py beside lab/r2/fp_costs.json (which you never edit), with entries in the same shape plus "provisional": true and "source": where each figure comes from.
- Markets: 'oil' (WTI crude oil CFD; the lab's data symbol is lightcmdusd; FP's symbol is XTIUSD) and the 40 US shares that have prepared bars.
- Shares: follow the lab's own convention for share CFDs (the '_stocks' note of lab/r2/fp_costs.json, lab/COSTS_FP.md, lab/prep_round3.py): the quoted bid/ask spread of the data plus 0.02 USD per share per side. The kit works on BID bars plus a modelled spread, so give each share its in-sample median quoted spread (in basis points of price, from the lab's one-minute bid/ask read with ts < 2022) with its hour-of-week shape computed the way kit/spread_shape.json was (its header says how; the first builder's script is ${SP}/explore_kit/build/shape.py), and add support for a per-unit commission ("commission_per_unit": price units per unit per side, 0.02 for shares) charged on each side on top of the half spread, in the net and stress scenarios. Report, do not model, the minimum commission per order.
- Swaps, leverage, lot sizes and the triple-swap weekday of shares and oil, and oil's spread: take them from FP Markets' published product specifications if you can reach them (web search or fetch; say exactly what you read and where), else set careful, slightly pessimistic values and say so. Every such figure is PROVISIONAL until the broker's own numbers are read in the user's MetaTrader.
- costs.is_provisional(key); judge.verdict writes "PROVISIONAL COSTS" in the ledger line and in results.json when any market of the main is provisional.
- Compare the kit's modelled cost with the lab's own cost frames for a few shares (lab/data/fp/<ticker>_m1.parquet hold bid/ask with the lab's costs folded in; read with ts < 2022): about 500 random in-sample round trips per share, kit cost against frame cost; report the ratio (the first builder found 0.97 to 1.04 on the lab's markets).

B. LOCAL-ONLY MARKETS in data.py: 'oil' and the shares exist only as prepared bars (no download path). data.load_bars(key) must read them, cut by the period lock like every reader (the validation years come from the sibling folder '<dir>_val' after unlock_val), and fail with a clear message when the prepared file is absent. Trading days of shares have 7 hourly bars: D20 needs fewer bars per day than the default 10 (a per-market 'min_day_bars' in the cost entry, read by sim.Book and sim.books). Document the first-bar label (a bar labelled HH:00 that really starts at HH:30) and what it means for a signal's known_at and an entry 'at the open'.

C. SLOW TRACK (CHARTER.md 'Slow track'): judge.verdict(..., max_hold_tdays=5) by default; a run of the slow track passes 40; above 40 raises. The bar's name and text follow the number ('hold<=40d'), results.json records it, and the ledger line says 'slow track' when it is not 5.

D. Small fixes the first batches asked for: data.external (and the kit's known-at helper) silently keep ONE row per known-at time: add a way to keep several rows that are known at the same time (an event calendar where several events are announced together), without changing the default; checks.shift_test passes max_wait_h through; the judge's 'max_market_share' bar prints 'n/a (total profit <= 0)' instead of inf.

RULES: read costs.py, sim.py, data.py, judge.py and test_kit.py fully first; follow their style; do not weaken any check; every new cost path gets a hand-computed test (a share round trip with the per-unit commission, across a triple-swap night; oil); a trap test for anything that could look ahead. Mechanical checks on the real prepared bars are welcome (bars load, D20 exists, costs are sane), never a trading rule.
RETURN the structured result: summary; the table of provisional costs with their sources; the last line of the full self-test with the new checks; a text ready for CHARTER.md telling a run how to use shares, oil, the slow track and several events at one time; the limits; the files.`

function verifyPrompt(b) {
  return `You are the adversarial verifier of an extension to a research kit that judges trading ideas. If it has a cost mistake, a look-ahead or a broken bar, every later verdict on shares, oil and slow rules is wrong. Your job is to BREAK it; you fix nothing.

${COMMON}
Edit NOTHING in ${KW}; work in ${SP}/kit_v21/verify/. The kit before this extension is ${MAIN}/lab/explore/kit (diff every file).

WHAT WAS ADDED (the builder's report; test it, do not trust it)
${JSON.stringify(b, null, 1).slice(0, 12000)}

WHAT TO DO
1. Full self-test in place and from a fresh copy of the tree. Read every diff.
2. Costs: hand-compute share and oil round trips (long and short, intraday, overnight, across the triple-swap night, a stop exit) from kit/extra_costs.json and compare with the kit to the last decimal; check the per-unit commission is charged once per side in net and 1.5 times nowhere it should not be (read how the stress scenario is defined); compare the kit's cost with the lab's cost frames for shares on real in-sample bars (ratio near 1?). Judge each provisional figure: is it plausible for FP Markets, is it pessimistic enough, is its source real?
3. Shares on real prepared bars (mechanics only, no rule): D20 exists with 7-bar days; an overnight gap through a stop fills at the open with stop slippage; the first-bar label cannot let a signal known after the open enter at that open; holidays and half days.
4. Slow track: the hold bar at 5, 40 and 41; a 30-day trade passes only with max_hold_tdays=40; swaps over a long hold match a hand count including triple nights.
5. Period lock for local-only markets: nothing of 2022+ comes out while locked even if the prepared file holds such rows; the unlock path reads only the '_val' sibling; never 2026.
6. Nothing changed for the 16 existing markets: same trades and verdicts as the main copy's kit on a few synthetic rules; the 122 earlier checks print the same lines.
7. The small fixes (several rows known at one time, shift_test, the share bar's text): do they do what is said and nothing else?
RETURN: verdict 'ok' or 'needs_fixes', the issues (id, severity, what, evidence with numbers and the script that shows it, the fix you propose), what you tested.`
}

function fixPrompt(b, v) {
  return `You fix an extension to a research kit that judges trading ideas, after an adversarial review. Fix what is real, reject what is not (with evidence), and prove each fix with a test that fails before and passes after.

${COMMON}
Edit only ${KW}/lab/explore/kit; your scratch: ${SP}/kit_v21/fix/ (keep a copy of the kit before your fixes there). The verifier's scripts are under ${SP}/kit_v21/verify/.

THE BUILDER'S REPORT
${JSON.stringify(b, null, 1).slice(0, 8000)}

THE VERIFIER'S ISSUES
${JSON.stringify(v, null, 1).slice(0, 16000)}

RULES: reproduce each issue first; add a test per fix; keep every existing check passing unchanged; re-run the verifier's reproduction scripts on the fixed kit; update the README.
RETURN the structured result: per issue (status, change, test), the last line of the full self-test, the final text for CHARTER.md (shares, oil, slow track, several events at one time), the limits that remain, the files.`
}

const EARN_PROMPT = `You build a point-in-time calendar of company earnings releases for a trading lab, from the US SEC's EDGAR system. A wrong time here is a look-ahead in every earnings idea, so the time each release became public is the whole job.

${COMMON}
Write only under ${KW}/lab/explore/scout/ (a script earnings_edgar.py and a new section appended to sources.md) and in your cache ~/explore_data/earnings/ (downloads and the calendar itself: never in the repository). Your scratch: ${SP}/kit_v21/earnings/.

THE JOB
- Shares: the 40 tickers of ~/explore_data/h1/info.json (every key except the 14 kit markets and 'oil'). Period: releases from 2016-10-01 to 2021-12-31 only; keep nothing later in the cache (filter each reply before writing it).
- Source: EDGAR. Each company's filings list is https://data.sec.gov/submissions/CIK<10 digits>.json (older filings are in the extra files it names); it answers a plain client name: send the User-Agent "research-client/1.0" and nothing personal, at most 5 requests a second, cache every reply, stop after two refusals. Find each ticker's CIK (EDGAR's company_tickers file, or search); mind tickers that changed (the lab's key 'fb' is Meta), share classes (GOOGL), and companies that file late.
- An earnings release is a form 8-K whose items include 2.02 (Results of Operations and Financial Condition). The time it became public is the filing's acceptance time (acceptanceDateTime; say in which time zone EDGAR gives it and convert to UTC correctly, with daylight saving). One release per fiscal quarter: where a quarter has several 8-K with item 2.02 (a pre-announcement, an amendment 8-K/A, a correction), keep them all in the raw table with a flag and mark the one that is the quarterly results (say how you decide: the one nearest to the 10-Q or 10-K, the usual weekday pattern of the company, the one whose press release has the results).
- Many companies publish the press release on a wire a few minutes BEFORE the 8-K is accepted (sometimes an hour). So the acceptance time is a safe 'known at' (never early), but it can be late: say so, measure it on a sample if you can (compare with the time printed in a few press releases), and give the safe rule a run should use: the reaction session is the first regular session (09:30-16:00 New York) that STARTS after the acceptance time.
- Check the table: every company should have about 4 releases a year; list the gaps and the oddities; check a dozen well-known dates by hand against what you know (for example Apple reported after the close on 2021-10-28) and say which you checked.
- Deliver: (1) lab/explore/scout/earnings_edgar.py: fetch, cache, build; a function that returns the calendar (ticker, acceptance time UTC, quarter flag, form, items, accession number) cut at a given end date, tested on the cache; (2) the calendar itself in ~/explore_data/earnings/ (parquet or CSV), with the script that rebuilds it; (3) a section 'Earnings releases (SEC EDGAR, 8-K item 2.02)' appended to lab/explore/scout/sources.md in the style of the other sections: URLs, tested code, WHEN each value is known, revisions, traps, counts per ticker; (4) for the idea 'buy before the results' (DIRECTION2.md, idea 053): can the DATE of a release be known in advance from EDGAR or any free source, point in time (for example an 8-K or press release announcing the date)? Say what you found; do not guess.
RETURN the structured result: summary, events per ticker with first and last dates and notes, how a run uses it (text ready for CHARTER.md or a brief), the traps, the files, what went wrong.`

const kitRun = (async () => {
  const b = await run(BUILD_PROMPT, { label: 'kit v2.1: build', phase: 'Kit: more markets, slow track', schema: BUILD_SCHEMA })
  if (!b) return { build: null }
  const v = await run(verifyPrompt(b), { label: 'kit v2.1: verify', phase: 'Kit verify', schema: VERDICT_SCHEMA })
  if (!v) return { build: b, verdict: null }
  log('Kit v2.1 verifier: ' + v.verdict + ', ' + v.issues.length + ' issue(s)')
  if (v.verdict === 'ok' && v.issues.length === 0) return { build: b, verdict: v, fix: null }
  const f = await run(fixPrompt(b, v), { label: 'kit v2.1: fix', phase: 'Kit fix', schema: FIX_SCHEMA })
  return { build: b, verdict: v, fix: f }
})()
const earnRun = run(EARN_PROMPT, { label: 'earnings calendar', phase: 'Earnings calendar', schema: EARN_SCHEMA })
const [kit, earnings] = await Promise.all([kitRun, earnRun])
return { kit: kit, earnings: earnings }
