export const meta = {
  name: 'explore-kit-v22-daily-shares',
  description: 'Research kit v2.2 for direction 3: generic US shares on daily bars (a broad universe with provisional costs), basket bars read by groups for baskets of many markets, an exit after N sessions; build, adversarial verification (also of the last unreviewed repair), fix',
  phases: [
    { title: 'Kit v2.2 build', detail: 'generic daily shares, group bars, session exit, tests' },
    { title: 'Kit v2.2 verify', detail: 'break it; also the third repair of v2.1' },
    { title: 'Kit v2.2 fix', detail: 'fix what the verifier found' },
  ],
}

const SP = '/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad'
const KW = SP + '/kit_v2_wt'
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
A trading lab runs a continuous search for new trading rules for a retail FP Markets account (CFDs, MetaTrader 5). Every idea is tested with one shared research kit, ${KW}/lab/explore/kit (README.md there; 166 passing self-tests): data.py (period lock: in sample to 2021-12-31, one logged look at 2022-2025, never 2026), costs.py, sim.py (simulator on hourly bars), stats.py, judge.py (verdict), checks.py (look-ahead guards). Rules of the search: ${KW}/lab/explore/CHARTER.md. The lead's new plan is ${KW}/lab/explore/lead/DIRECTION3.md: READ IT FIRST (ideas 059 to 062: large moves on results days, on other news days and on days without news, tested on a broad universe of US shares on DAILY bars; the charter's amendment 'Baskets of many markets').
THE DATA OF THE NEW TEST BED (built today by other agents, outside the repository; read-only for you): ~/explore_data/d1/universe.csv (500 companies of the S&P 500 list; 382 rows with in_universe true: key, yahoo, ticker, name, cik, sector, added, in_universe_from, in_lab40); ~/explore_data/d1/bars/<key>.parquet (daily bars 2016-2021 from Yahoo: UTC index 'time' = the session's open, 09:30 New York; open high low close; volume = the session's length in minutes, 390 or 210; shares = traded volume), ~/explore_data/d1/dividends.csv, splits.csv, info.json (they are being built as you start: use what is there, and say what was missing); the scripts and their documentation: ${DW}/lab/explore/scout/prices_d1.py (its docstring says exactly what Yahoo's prices are: adjusted for EVERY split up to today, not for dividends), universe_us.py, events_edgar.py and the last section of ${DW}/lab/explore/scout/sources.md; the 8-K calendar is in ~/explore_data/events_d1.
WHERE YOU WORK: ${KW} is a small working copy at the lab's current commit (lab/explore, lab/r2/fp_costs.json, lab/COSTS_FP.md, the ten rules' trades). The lab's main copy ${MAIN} is read-only for you. Prepared hourly bars (in sample) of the 14 FP markets, oil and the lab's 40 shares are in ~/explore_data/h1. Run NO git command. No sub-agents. Never download from Dukascopy. Never fetch, read or compute anything dated 2022 or later. No price series may be written inside the working copy (the repository is public): ratios, flags, lists of companies and public facts only.
NO TRADING RULE IS RUN HERE on the real bars of the new universe: mechanical checks only (bars load, costs are sane, a random-signal rule has no edge, a planted edge on SYNTHETIC bars is found). The ideas are judged tomorrow, by other runs, on declarations written before any result.
THE MACHINE MAY RESTART, and this task may then be started again from the beginning: look at the working copy and your scratch folder first; if an interrupted run of this same task left work there, read it critically and continue from it; save your work to disk as you go. THE MACHINE IS SHARED: 4 processors and 15 GB of memory for three agents: at most 2 worker processes, memory under about 3 GB, no background process left running when you finish.
Python: PYTHONDONTWRITEBYTECODE=1 python3 -B ... (no __pycache__ in the working copy). Self-test: PYTHONDONTWRITEBYTECODE=1 python3 -B ${KW}/lab/explore/kit/test_kit.py must end "N/N checks passed" (about 5 minutes; 166 before this work); with --real-bars it adds checks on the prepared bars.
Write for a reader who was not there: plain sentences, exact numbers, the script that shows each claim.`

const BUILD_SCHEMA = { type: 'object', properties: {
  summary: { type: 'string' }, costs_table: { type: 'string' }, tests: { type: 'string' }, how_a_run_uses_it: { type: 'string' },
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

const BUILD_PROMPT = `You extend a research kit used to judge trading ideas. A bug here makes every later verdict wrong: work as carefully as the existing code does and prove each claim with a test.

${COMMON}
Edit only ${KW}/lab/explore/kit. Your scratch: ${SP}/kit_v22/builder/ (create it; keep a copy of the kit before your changes there).

WHAT TO ADD (kit v2.2), each with tests in test_kit.py and a README section, WITHOUT changing any result of the 166 existing checks nor anything for the markets the kit already has (the 16 FP markets, oil, the 40 hourly shares)

A. GENERIC US SHARES ON DAILY BARS. The 382 shares of the universe (and any share later added to it) become markets of the kit, keyed by the universe file's 'key', through ONE class of costs, not 382 hand entries.
 - The list of companies is public information: copy what the kit needs (key, sector, in_universe_from) into a small file inside the kit (for example kit/universe_us.csv); no price in it. data.load_bars(key) reads the share's daily bars from the prepared folder (~/explore_data/d1/bars, found the way the hourly folder is found: an environment variable, the cache, then the repository if the lead ever puts bars there), through the period lock like every reader (the validation years come from a sibling folder after unlock_val; a missing file raises a clear error), and never returns a row before the share's in_universe_from (no look-ahead at inclusion: the bars before it may be used only as history for averages if you can make that safe and explicit; if in doubt, cut them and say so).
 - Costs: one entry for the class in kit/extra_costs.json, "provisional": true with its source, heavier than the measured costs of the lab's 40 shares on purpose: spread 12 bp of the price for an order at a bar's close, 25 bp for an order at the session's open (the bar's open); commission max(0.03 USD a share, 2 USD an order) at the charter's stake, exactly as for the 40 shares; slippage 1 bp on a market order, 2 bp on a stop; swaps 7 % long and 3 % short a year, triple on Friday; dividends from ~/explore_data/d1/dividends.csv as fractions of the previous close (a short open at the ex-date's open pays, a long is credited 70 %: the existing code path). The dividend FRACTIONS are public facts and ratios: they may live in a kit file; decide and say. Stress x1.5 as for every market. Flat hour-of-week shape. costs.is_provisional is true for every share of the class; judge's ledger line must not print 382 names (print the class and the count).
 - Yahoo's prices are adjusted for every split up to the day they were downloaded, also splits after 2021: the kit must not adjust them again; absolute LEVELS carry later splits and the look-ahead guard cannot see that (no split list): say it loudly in the README and in the error text of anything that could tempt a run to use levels; the dividend fractions and the commission per share (0.03 USD on a price that may be a fraction or a multiple of the price traded then) need a decision: the per-share commission is wrong on split-adjusted prices; the minimum per order (2 USD at the stake's notional) does not depend on the share count. Decide the pessimistic, simple treatment (for example charge max(minimum, 0.03 USD x the stake's notional / the unadjusted price when splits.csv allows it, else the minimum) and prove it on a share with a known split inside 2016-2021.
 - DAILY BARS IN AN HOURLY SIMULATOR. sim.py assumes one-hour bars in places (BAR_NS, the exit time of a close exit, the 59-minute gap rule, D20's days of at least 10 bars, the truncation test's default row length, the dividend clock at 09:00, the null's clock). Read all of sim.py, stats.py, costs.py, checks.py and judge.py for every such assumption, list them, and make each right for a market whose bars are one session long (a per-market bar length in the cost entry): a daily bar opens at 09:30 New York and its close is known at 16:00 (13:00 on half days: the 'volume' column says 210); a signal from a daily close enters at the NEXT session's open; an exit at a close pays the close spread; a stop is checked on the day's high and low (both stop and target touched in one bar: the stop); swaps count the nights between entry and exit; D20 = the mean daily range of the 20 sessions before the entry bar.
 - An exit after N SESSIONS of the market's own bars: ("sessions", N) = the open of the bar N sessions after the entry bar (for hourly share markets: the same clock time N sessions later, by the market's own trading days), usable in simulate, in the null (same exit key) and in the judge's hold bar. ('bdays', N) ignores exchange holidays: an earlier run lost one session in 36 of 355 trades to that.
B. BASKET BARS BY GROUPS (CHARTER.md 'Baskets of many markets'): judge.verdict(..., groups={market: group}) for a basket of MORE THAN 40 markets: the bars 'markets positive >= 65 %' and 'max market share <= 25 %' are read on the groups (at least 8 groups, else it raises); a basket of more than 40 markets WITHOUT groups raises with a message naming the charter amendment; a basket of 40 markets or fewer ignores groups and behaves as before. results.json records the groups' figures. The declaration must name the groups before any result: judge reads them from the idea's declared.json when it has a "groups" entry ("sector" for the universe file's sectors) and refuses groups that differ from the declaration.
C. Small things the last batch asked for, if cheap and safe: results.json main['max_market_share_of_profit'] written as a JSON-valid value (not inf); a public helper for the exchange calendar of the shares (sessions and the 13:00 half days) built from the bars or from rules, so that runs stop hard-coding holiday lists.

RULES: read costs.py, sim.py, data.py, judge.py, checks.py, stats.py and test_kit.py fully first; follow their style; do not weaken any check; every new cost path gets a hand-computed test (a daily-bar round trip: entry at the open with the 25 bp level, exit at an open N sessions later and at a close, across a Friday, across an ex-dividend date long and short, a stop hit inside a day, a stop gapped through at the open); a trap test for look-ahead on daily bars (a signal stamped at the session's open but computed from its close must be caught by the truncation test with the right row length; say what row length a run must pass); a planted edge on SYNTHETIC daily bars is found and a noise rule is not (the whole chain: declared.json with groups, truncation test, simulate, neighbours, every-signal, null, verdict with groups, ledger_add on a COPY of LEDGER.md). On the REAL bars of the universe: mechanical checks only under --real-bars (every share of the universe file loads or is listed as missing; first bar not before in_universe_from; D20 exists; a daily round trip costs between 20 and 120 bp; no row after 2021).
RETURN the structured result: summary; the cost table of the class with sources; the last line of the full self-test and of --real-bars; a text ready for CHARTER.md telling a run how to use the generic shares, the session exit and the groups (what to load, what row length to pass, what to stamp, what to declare); the limits; the files.`

function verifyPrompt(b) {
  return `You are the adversarial verifier of an extension to a research kit that judges trading ideas, and of the last repair made to it, which nobody has checked. Tomorrow three ideas on a broad universe of US shares will be judged with it. A cost mistake, a look-ahead, a wrong bar convention or a broken bar makes their verdicts wrong, in either direction. Your job is to BREAK it; you fix nothing.

${COMMON}
Edit NOTHING in ${KW}; work in ${SP}/kit_v22/verify/ (create it). The kit before this extension is ${MAIN}/lab/explore/kit (v2.1 after its third repair, 166 checks): diff every file. The kit before that third repair is ${SP}/kit_v21/fix3/kit_before; the third repair's report is in ${SP}/kit_v21/fix3/PROGRESS.txt and its scripts in ${SP}/kit_v21/fix3/s/.

WHAT WAS ADDED (the builder's report; test it, do not trust it)
${JSON.stringify(b, null, 1).slice(0, 14000)}

WHAT TO ATTACK, most important first
1. Full self-test in place and from a fresh copy of the tree; --real-bars once. Read every diff.
2. DAILY BARS IN THE SIMULATOR. With your own hand computations on real daily bars of five shares of the universe (mechanics only, no rule): an entry at a session's open from a signal stamped at the previous close; exits at an open N sessions later, at a close, by a stop inside a day, by a stop gapped through at the open; net, stress and gross; across a Friday, a holiday, a half day, an ex-dividend date (long and short). Compare with sim.simulate to the last decimal. Then every place the hourly assumption could survive: exit times, hold in trading days (the judge's hold bar: a 5-session hold must read 5, a 40-session hold 40), swap nights, D20 (20 sessions, the entry day excluded), the null's random entries (same clock, same exit), the truncation test (a signal that uses its own bar's close but is stamped at that bar's open MUST fail; say with which row length; with the default one-hour row length is a daily-bar look-ahead caught or missed? If missed, that is blocking: a run that forgets the row length would pass a look-ahead), the shift test, the same-day null for baskets (382 shares, many signals on one day), correlation with the ten.
3. LOOK-AHEAD AT INCLUSION AND IN THE DATA: load_bars never returns a bar before in_universe_from (or only in a way a build cannot misuse); nothing of 2022 or later through the lock even if a prepared file held such rows (make a synthetic file to prove it); the split adjustment up to today in Yahoo's levels: can a ratio-based rule be affected (the dividend fraction, the per-share commission, D20 in price units against a price move)? Show that a rule on LEVELS is not caught for this class and judge whether the README says so plainly enough.
4. COSTS OF THE CLASS: hand-check the round trip on shares at about 10, 30, 80, 300 and 3000 USD; the commission treatment on a split-adjusted price (pick a share with a split inside 2016-2021 and one with a large split after 2021 if splits.csv lets you know it without later data); is each provisional figure pessimistic enough against what the lab measured on its 40 shares (compare the class with the measured costs of the 40 on daily round trips: the class must not be cheaper for any of them); dividends long and short.
5. GROUP BARS: more than 40 markets without groups raises; with fewer than 8 groups raises; groups that differ from declared.json are refused; the two bars are computed on groups exactly (hand-check on a small set of trades); 40 markets or fewer behave exactly as before (same results.json as the old kit on a synthetic basket); a market missing from the groups mapping.
6. THE SESSION EXIT: ('sessions', N) against a hand count on real bars around holidays, for a daily share and for an hourly share; in the null; in the hold bar; exit_key differs from ('bdays', N).
7. THE THIRD REPAIR OF v2.1 (unreviewed): the exact power-of-two re-basing of the look-ahead guard (can an honest rule on oil still fail? can a rule on adjusted levels still pass? differences of logs); the refusal of inputs that carry an adjusted market's mark but are not at its price level (does it refuse honest runs: a frame of bars with an extra float column such as a moving average, a D20 column, a daily table built by data.daily_bars with added columns? the batch's prompt tells runs to precompute daily tables for speed); the share close-spread levels (three per year) on five shares against the lab's one-minute quotes (ts < 2022); the re-dated March 2014 oil roll; an empty main through the whole chain.
8. NOTHING ELSE CHANGED: the 16 FP markets, oil and the 40 hourly shares give the same trades and verdicts as the kit before this extension, on synthetic rules and on real bars with random signals; re-run two earlier ideas of the lab (${MAIN}/lab/explore/ideas/030_weekly_reversal_dollar_pairs and one idea folder of your choice that uses the hourly shares or oil, copied to your scratch) with the new kit and compare their main figures with their stored results.json (a difference must be explained by a documented change).
SEVERITY: blocking = a verdict could be wrong in a way that matters (look-ahead, a fake gain or loss, a cost off by more than about 20 % of the round trip, a crash of the chain on a normal run); major = wrong but bounded; minor = documentation, a rare case.
RETURN: verdict 'ok' or 'needs_fixes'; the issues (id V22-n, severity, what, evidence with numbers and the script that shows it, the fix you propose); what you tested, including what held.`
}

function fixPrompt(b, v) {
  return `You fix an extension to a research kit that judges trading ideas, after an adversarial review. Fix what is real, reject what is not (with evidence), and prove each fix with a test that fails before and passes after.

${COMMON}
Edit only ${KW}/lab/explore/kit; your scratch: ${SP}/kit_v22/fix/ (create it; keep a copy of the kit before your fixes there). The verifier's scripts are under ${SP}/kit_v22/verify/.

THE BUILDER'S REPORT
${JSON.stringify(b, null, 1).slice(0, 8000)}

THE VERIFIER'S ISSUES
${JSON.stringify(v, null, 1).slice(0, 20000)}

RULES: reproduce each issue first; one test per fix; keep every existing check passing; re-run the verifier's reproduction scripts on the fixed kit; update the README; change nothing for the 16 FP markets; no price series inside the kit folder. If a fix needs a decision that is not yours (a cost figure, a rule of the charter), take the pessimistic side and say so.
RETURN the structured result: per issue (status, change, test), the last line of the full self-test and of --real-bars, the final text for CHARTER.md (generic daily shares, the session exit, groups: what a run loads, passes, stamps and declares), the limits that remain, the files.`
}

const b = await run(BUILD_PROMPT, { label: 'kit v2.2: build', phase: 'Kit v2.2 build', schema: BUILD_SCHEMA })
if (!b) return { build: null }
const v = await run(verifyPrompt(b), { label: 'kit v2.2: verify', phase: 'Kit v2.2 verify', schema: VERDICT_SCHEMA })
if (!v) return { build: b, verdict: null }
log('Kit v2.2 verifier: ' + v.verdict + ', ' + v.issues.length + ' issue(s): ' + v.issues.map(i => i.id + ' ' + i.severity).join(', '))
if (v.verdict === 'ok' && v.issues.filter(i => i.severity !== 'minor').length === 0) return { build: b, verdict: v, fix: null }
const f = await run(fixPrompt(b, v), { label: 'kit v2.2: fix', phase: 'Kit v2.2 fix', schema: FIX_SCHEMA })
return { build: b, verdict: v, fix: f }
