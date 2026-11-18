export const meta = {
  name: 'explore-verify-kit21-fix',
  description: 'Second adversarial check before the kit is used: the fixes made to the research kit v2.1 (oil contract rolls, share commission minimum, yearly spreads, dividends) and the earnings calendar built from SEC EDGAR; fix what is real',
  phases: [
    { title: 'Kit fix verify', detail: 'break the roll adjustment, the commission, the dividends, the yearly spread' },
    { title: 'Kit fix repair', detail: 'only if the verifier finds something real' },
    { title: 'Earnings verify', detail: 'independent check of release times and reaction sessions' },
    { title: 'Earnings repair', detail: 'only if the verifier finds something real' },
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
A trading lab runs a continuous search for new trading rules for a retail FP Markets account (CFDs, MetaTrader 5). Every idea is tested with one shared research kit, ${KW}/lab/explore/kit (README.md there): data.py (period lock: in sample to 2021-12-31, one logged look at 2022-2025, never 2026), costs.py, sim.py (hourly simulator), stats.py, judge.py (verdict), checks.py (look-ahead guards). Rules of the search: ${KW}/lab/explore/CHARTER.md; the new direction: ${KW}/lab/explore/lead/DIRECTION2.md (company earnings on US share CFDs, a slow track, oil).
The kit was just extended (v2.1: 40 US shares and oil with PROVISIONAL costs, a slow track), reviewed once, and FIXED after that review. Nobody has checked the fixes yet. Today's ideas (earnings drift on shares, oil breakouts) will be judged with them.
WHERE YOU WORK: ${KW} is a small working copy (lab/explore, lab/r2/fp_costs.json, lab/COSTS_FP.md, the ten rules' trades). The kit BEFORE v2.1 (v2, 122 checks) is ${MAIN}/lab/explore/kit; the kit after the v2.1 build but before the fixes is ${SP}/kit_v21/fix/kit_before. The lab's main copy ${MAIN} is read-only for you (lab/data holds the one-minute files, which you may read ONLY with a filter ts < 2022-01-01 inside the read, and only for mechanical work on costs and alignment, never to run or tune a trading rule). Prepared hourly bars (in sample only) are in ~/explore_data/h1 (set EXPLORE_H1_DIR=$HOME/explore_data/h1): the 14 markets of the kit, plus 'oil' and 40 US shares (keys = lower-case tickers; 7 hourly bars a day, 09:30-16:00 New York, the first bar labelled 09:00 though trading starts at 09:30). The full reports of the earlier agents are in ${SP}/kit_v21/lead/kit_report.json (build, verdict, fix) and ${SP}/kit_v21/lead/earnings_report.json; earlier scripts are under ${SP}/kit_v21/ (builder, verify, fix, earnings).
Run NO git command. No sub-agents. Never download from Dukascopy. Never fetch, read or compute anything dated 2022 or later (a web reply that necessarily carries later data is filtered in memory before anything is printed or written).
THE MACHINE MAY RESTART, and this task may then be started again from the beginning: look at your scratch folder first; if an interrupted run of this same task left work there, read it critically and continue from it; save your work to disk as you go.
THE MACHINE IS SHARED: 4 processors and 15 GB of memory for two agents: at most 2 worker processes each, memory under about 4 GB, no background process left running when you finish.
Python: PYTHONDONTWRITEBYTECODE=1 python3 -B ... (no __pycache__ in the working copy). Self-test: EXPLORE_H1_DIR=$HOME/explore_data/h1 PYTHONDONTWRITEBYTECODE=1 python3 -B ${KW}/lab/explore/kit/test_kit.py must end "N/N checks passed" (about 3 to 4 minutes; 148 expected).
Write for a reader who was not there: plain sentences, exact numbers, the script that shows each claim.`

const VERDICT_SCHEMA = { type: 'object', properties: {
  verdict: { type: 'string', enum: ['ok', 'needs_fixes'] },
  issues: { type: 'array', items: { type: 'object', properties: { id: { type: 'string' }, severity: { type: 'string', enum: ['blocking', 'major', 'minor'] }, what: { type: 'string' }, evidence: { type: 'string' }, fix: { type: 'string' } }, required: ['id', 'severity', 'what', 'evidence', 'fix'] } },
  what_was_tested: { type: 'string' } }, required: ['verdict', 'issues', 'what_was_tested'] }
const FIX_SCHEMA = { type: 'object', properties: {
  per_issue: { type: 'array', items: { type: 'object', properties: { id: { type: 'string' }, status: { type: 'string', enum: ['fixed', 'partly', 'not_fixed', 'rejected'] }, change: { type: 'string' }, test: { type: 'string' } }, required: ['id', 'status', 'change', 'test'] } },
  tests: { type: 'string' }, text_changes: { type: 'string', description: 'any change needed in the text that tells a run how to use the kit or the calendar' }, limits: { type: 'array', items: { type: 'string' } }, files: { type: 'array', items: { type: 'string' } } },
  required: ['per_issue', 'tests', 'limits', 'files'] }

const KIT_VERIFY = `You are the adversarial verifier of FIXES made to a research kit that judges trading ideas. A cost mistake, a look-ahead or a wrong price adjustment here makes every later verdict on shares and oil wrong, in either direction (a false pass costs real money later; a false fail buries a good rule). Your job is to BREAK the fixes; you fix nothing.

${COMMON}
Edit NOTHING in ${KW}; work in ${SP}/kit_v21/verify2/ (create it). Read ${SP}/kit_v21/lead/kit_report.json first (the 'fix' part says what was changed and how it was tested: test it, do not trust it), then diff ${SP}/kit_v21/fix/kit_before against ${KW}/lab/explore/kit and read every changed line.

WHAT TO ATTACK
1. Self-test in place and on a fresh copy of the tree (148 checks).
2. OIL CONTRACT ROLLS (data._adjust_rolls, roll_times, cl_expiry, price_factor, check_adjusted; extra_costs.json 'rolls'). The raw prepared bars are ~/explore_data/h1/oil.parquet.
 - With your own method (not the fixer's), find the monthly roll reopens in the raw bars and compare with the 108 listed times: wrong nights, missed rolls, months adjusted twice, a real news gap removed as a roll. After the adjustment, is any calendar pattern left in the reopen gaps (by day of month, by days to the CL expiry)?
 - Compare with outside knowledge where you can: the adjusted series is a continuously rolled front WTI future; over 2013-2021 a long held throughout should lose roughly what a front-month rolled position lost (think of the well-known decay of rolled oil funds). Give the adjusted total return and say whether it is plausible; give the worst single adjusted ratios and say whether each is a plausible roll spread for its date (for example the spring of 2020).
 - Hand-compute five trades that cross a roll (long and short; gross, net, stress; one with a stop) from the raw bars, the ratio and extra_costs.json, and compare with sim.simulate to the last decimal. The spread must stay 0.05 USD of RAW price whatever the adjustment.
 - Look-ahead: the adjusted LEVELS before a roll depend on later rolls. Show that a rule built on ratios gives the same signals on bars cut early and on the full bars (checks.truncation_test), and that a rule on absolute levels is caught. Can a signal build read a later roll from anything the kit hands it (columns, attrs, module tables such as data.ROLLS_APPLIED)?
 - State hazards: ROLLS_APPLIED is a module table of the last load. Load oil twice with different start years, build Books in either order, a pair with oil as a leg, a truncated copy of the bars: is any spread, factor or check wrong?
 - The validation path (rule E-1 after rolls_checked_to) on a synthetic file with rows dated 2022-2025 that you make yourself (never real data): planted rolls at the rule's reopens are removed; holidays; nothing happens in sample.
3. SHARE COMMISSION WITH THE MINIMUM (costs.commission, trade_notional, sim.Book comm_q, pairs): hand-compute round trips at prices near 30, 72, 150 and 3000 USD, long and short, net / stress / gross, intraday and across a split (aapl 2020-08-31, ge 2021-08-02 reverse), and compare with the simulator and costs.round_trip to the last decimal. Is the minimum charged per ORDER SIDE as stated, never twice, never in gross, x1.5 in stress only? Is the adjusted-unit arithmetic right before a split (the same USD commission for the same USD notional)?
4. YEARLY SPREAD LEVELS (spread_bps_by_year, costs._year_bps): recompute for three shares, from the lab's one-minute bid/ask (read with ts < 2022), the mean quoted spread at the bar-open minutes per year, and compare with the kit's mean modelled spread over the same bars; check the New York year boundary and the level used for years not listed.
5. DIVIDENDS (costs.dividends inside costs.swap; extra_costs.json 'dividends'): check ten ex-dates and amounts you know (for example JPMorgan, Exxon, Apple, Microsoft in 2019-2021) against the stored fractions; test the timing semantics on real bars (a short opened the day before and closed after the ex-date open pays; entered at the ex-date's first bar does not; a long is not credited; an intraday trade never pays); the null test and pairs carry it; a trade past dividends_checked_to raises. Is anything charged twice (a dividend AND the price drop are both real for a short: the drop is a gain, the dividend a cost; check the sign).
6. DROPPED SHORT BARS (min_bar_minutes): which bars are dropped for five shares; does dropping change D20, a 'clock' exit, the last bar of a half day, a stop on the dropped minute; could a signal known at 12:30 on a half day now wait until the next day, and is that the documented behaviour?
7. SLOW TRACK GATE: only 5 or 40; 40 only when declared.json says "track": "slow" (the template's own text must not pass by accident).
8. NOTHING ELSE CHANGED: the 16 FP markets give the same trades and verdicts as the kit before v2.1 (${MAIN}/lab/explore/kit) on synthetic rules and on three real markets with random signals.
9. Anything else you find wrong, optimistic or untested in the changed code.
SEVERITY: blocking = a verdict on shares or oil could be wrong in a way that matters (look-ahead, a fake gain or loss, a cost off by more than about 20 % of the round trip); major = wrong but bounded; minor = documentation, a rare case.
RETURN: verdict 'ok' or 'needs_fixes'; the issues (id KF-n, severity, what, evidence with numbers and the script that shows it, the fix you propose); what you tested, including what held.`

function kitFixPrompt(v) {
  return `You repair a research kit that judges trading ideas, after a second adversarial review of its latest fixes. Fix what is real, reject what is not (with evidence), and prove each fix with a test that fails before and passes after.

${COMMON}
Edit only ${KW}/lab/explore/kit; your scratch: ${SP}/kit_v21/fix2/ (create it; keep a copy of the kit before your changes there). The verifier's scripts are under ${SP}/kit_v21/verify2/.

THE VERIFIER'S ISSUES
${JSON.stringify(v, null, 1).slice(0, 24000)}

RULES: reproduce each issue first; one test per fix in test_kit.py; keep every existing check passing unchanged (148 before you start); re-run the verifier's reproduction scripts on the repaired kit; update README.md; do not change anything for the 16 FP markets. If a fix needs a decision that is not yours (a cost figure, a rule of the charter), take the pessimistic side and say so.
RETURN the structured result: per issue (status, change, test), the last line of the full self-test, any change needed in the text that tells a run how to use the kit, the limits that remain, the files.`
}

const EARN_VERIFY = `You are the adversarial verifier of an earnings-release calendar that a trading lab is about to use for three trading ideas. If a release is stamped earlier than it was public, every result is a look-ahead; if it is stamped a session late, the idea is tested on the wrong day and a real effect is missed. Your job is to BREAK the calendar; you fix nothing.

${COMMON}
Edit NOTHING in ${KW} or in ~/explore_data/earnings; work in ${SP}/kit_v21/earnings_verify/ (create it). The calendar: ~/explore_data/earnings/calendar.csv (one row per fiscal quarter) and calendar_raw.csv (every 8-K with item 2.02, flagged), built by ${KW}/lab/explore/scout/earnings_edgar.py (read it fully) from the cached EDGAR replies in ~/explore_data/earnings/raw/; the documentation is the last section of ${KW}/lab/explore/scout/sources.md. The builder's report: ${SP}/kit_v21/lead/earnings_report.json. EDGAR's data.sec.gov answers the plain User-Agent "research-client/1.0" (send nothing personal; at most 5 requests a second; stop after two refusals); prefer the cache.

WHAT TO ATTACK
1. Run the script's own tests. Then, with YOUR OWN code, rebuild from the cached replies the list of 8-K filings with item 2.02 for eight tickers (include aapl, jpm, c, tsla, nke, baba and two of your choice) and compare with calendar_raw.csv row by row: missing rows, extra rows, times.
2. THE CLOCK. Is acceptanceDateTime really UTC? Prove it independently of the builder's argument: for companies with a fixed, well-known release clock (for example Apple 16:30 New York, JPMorgan before 07:00 New York), the UTC reading must give that clock in both summer and winter time across all years; the other reading must not. Check the daylight-saving weeks (March and November, where New York and UTC shift) event by event.
3. THE REACTION SESSION. Recompute it yourself for every row (first regular session, 09:30-16:00 New York, that STARTS strictly after the acceptance time; your own holiday list) and compare with the column. Edge cases: accepted at 09:30:00 exactly, during the session, after 16:00 on a Friday, the day before a holiday, a half day, accepted on a holiday or weekend.
4. PRICES AS A WITNESS (in-sample hourly share bars only, through the kit: data.load_bars(ticker); judge the calendar only, never a trading rule and never choose events by their later return). For each event measure the absolute move of sessions -2..+2 around the calendar's reaction session (open gap and open-to-close, in units of the share's usual session move), by 'when' class and by ticker. The move should peak at offset 0. List every event whose largest move is clearly at offset -1 (the calendar is LATE: the idea would trade a day after the news) or at offset +1, and say for each ticker how many. A late stamp is safe but must be known; an EARLY stamp (reaction clearly before... no: the stamp before the news was public) is a look-ahead: can any row be early? Think of the three rows added by hand (GE twice, Citigroup once), the 21 Alibaba rows found by full-text search, amendments, and the rule that picks the 'results' row among several 8-K of one quarter (does that choice use anything not known at the time? what would a strictly point-in-time user get from quarterly_only=False?).
5. COMPLETENESS AND FLAGS: about four results a year for each share, 80 to 100 days apart; list every gap and every pair of 'results' rows closer than 60 days; check twenty well-known release dates you remember (several companies, several years) and say which you checked and which you could not.
6. HYGIENE: calendar(end=...) really cuts (nothing after the end, nothing after 2021-12-31 whatever the argument); no row or cache file holds anything dated 2022 or later; the User-Agent carries nothing personal; the script fails loudly when the cache is absent rather than silently returning less.
SEVERITY: blocking = some rows are early (look-ahead) or the reaction session is wrong for a whole class of events; major = many rows a session late without a flag, or results rows mis-picked for a company; minor = isolated rows, documentation.
RETURN: verdict 'ok' or 'needs_fixes'; the issues (id EV-n, severity, what, evidence with numbers and the script that shows it, the fix you propose); what you tested, including what held, and the table of offsets (how many events peak at -1, 0, +1) by 'when' class.`

function earnFixPrompt(v) {
  return `You repair an earnings-release calendar built from SEC EDGAR for a trading lab, after an adversarial review. Fix what is real, reject what is not (with evidence), and prove each fix with a test in the script's own test list.

${COMMON}
Edit only ${KW}/lab/explore/scout/earnings_edgar.py, the last section of ${KW}/lab/explore/scout/sources.md, and the calendar files in ~/explore_data/earnings/ (rebuild them with the script). Your scratch: ${SP}/kit_v21/earnings_fix/ (create it; keep copies of the script and of both calendar files before your changes there). The verifier's scripts are under ${SP}/kit_v21/earnings_verify/. EDGAR's data.sec.gov answers the plain User-Agent "research-client/1.0" (nothing personal; at most 5 requests a second; stop after two refusals); prefer the cache.

THE VERIFIER'S ISSUES
${JSON.stringify(v, null, 1).slice(0, 24000)}

RULES: never move an event EARLIER because of a price move (prices may only show that a stamp is late, and a late stamp is then flagged, not moved); a row whose time cannot be shown safe is flagged so that a run can drop it; keep the raw table complete; the script's tests must all pass after your changes; say in sources.md what a run must do with each flag.
RETURN the structured result: per issue (status, change, test), the last line of the script's tests, the text changes a run needs (how to load the calendar, which rows to drop), the limits that remain, the files.`
}

const kitRun = (async () => {
  const v = await run(KIT_VERIFY, { label: 'kit v2.1 fixes: verify', phase: 'Kit fix verify', schema: VERDICT_SCHEMA })
  if (!v) return { verdict: null }
  log('Kit v2.1 fix verifier: ' + v.verdict + ', ' + v.issues.length + ' issue(s): ' + v.issues.map(i => i.id + ' ' + i.severity).join(', '))
  const real = v.issues.filter(i => i.severity !== 'minor')
  if (v.verdict === 'ok' && real.length === 0) return { verdict: v, fix: null }
  const f = await run(kitFixPrompt(v), { label: 'kit v2.1 fixes: repair', phase: 'Kit fix repair', schema: FIX_SCHEMA })
  return { verdict: v, fix: f }
})()
const earnRun = (async () => {
  const v = await run(EARN_VERIFY, { label: 'earnings calendar: verify', phase: 'Earnings verify', schema: VERDICT_SCHEMA })
  if (!v) return { verdict: null }
  log('Earnings calendar verifier: ' + v.verdict + ', ' + v.issues.length + ' issue(s): ' + v.issues.map(i => i.id + ' ' + i.severity).join(', '))
  const real = v.issues.filter(i => i.severity !== 'minor')
  if (v.verdict === 'ok' && real.length === 0) return { verdict: v, fix: null }
  const f = await run(earnFixPrompt(v), { label: 'earnings calendar: repair', phase: 'Earnings repair', schema: FIX_SCHEMA })
  return { verdict: v, fix: f }
})()
const [kit, earnings] = await Promise.all([kitRun, earnRun])
return { kit: kit, earnings: earnings }
