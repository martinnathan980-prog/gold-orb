export const meta = {
  name: 'explore-verify-kit21-round3',
  description: 'Third adversarial check of the research kit v2.1 (the second round of fixes: oil rolls from outside settlements, the look-ahead guard on adjusted levels, two spread levels for shares, the dividend credit), while the day\'s batch runs; repair only what is real',
  phases: [
    { title: 'Kit round 3 verify', detail: 'break the second round of fixes' },
    { title: 'Kit round 3 repair', detail: 'only if something major is found' },
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
A trading lab runs a continuous search for new trading rules for a retail FP Markets account (CFDs, MetaTrader 5). Every idea is tested with one shared research kit, ${KW}/lab/explore/kit (README.md there): data.py (period lock: in sample to 2021-12-31, one logged look at 2022-2025, never 2026), costs.py, sim.py (hourly simulator), stats.py, judge.py (verdict), checks.py (look-ahead guards). Rules of the search: ${KW}/lab/explore/CHARTER.md.
Kit v2.1 added 40 US shares and oil with PROVISIONAL costs and a slow track. It was attacked twice; each attack found real defects, and each was repaired. The SECOND repair is what nobody has checked yet: (KF-1) oil contract rolls dated and sized from outside settlements (EIA contract 1 / 2, kit/oil_outside.csv) instead of the reopen gap; (KF-2) checks.truncation_test re-bases each cut copy of back-adjusted bars and runs each cut build inside data.asof(cut), so that a rule on adjusted LEVELS fails; (KF-3) the roll factor no longer depends on what was loaded; (KF-4) a long share position is credited 70 % of a dividend and judge.dividend_report shows the result at credits 0 and 1; (KF-5) two spread levels per share and year (the 09:30 open, the other bars); (KF-8) adjustment defaults in costs.round_trip / pair_round_trip. The lead then replaced the vendor's price column of kit/oil_outside.csv by a derived flag (duka_on) and adapted two tests, and added a column late_by_construction to the earnings calendar (lab/explore/scout/earnings_edgar.py). Reports of the earlier rounds: ${SP}/kit_v21/lead/kit_report.json (build, first attack, first repair); the second attack's scripts ${SP}/kit_v21/verify2/ and the second repair's ${SP}/kit_v21/fix2/ (kit_before = the kit before that repair; PROGRESS.txt; s/ scripts; repro_after/).
THE DAY'S IDEAS ARE RUNNING RIGHT NOW on this same kit in another working copy (${SP}/explore_wt): never read-lock, edit or run anything there.
WHERE YOU WORK: ${KW} is a small working copy at the lab's current commit (lab/explore, lab/r2/fp_costs.json, lab/COSTS_FP.md, the ten rules' trades). The lab's main copy ${MAIN} is read-only for you (lab/data holds the one-minute files, which you may read ONLY with a filter ts < 2022-01-01 inside the read, and only for mechanical work on costs and alignment, never to run or tune a trading rule). Prepared hourly bars (in sample only) are in ~/explore_data/h1 (the kit finds them; 14 FP markets, 'oil', 40 US shares); the vendor's oil 14:30 mid is ~/explore_data/h1/oil_mid_1430.csv.
Run NO git command. No sub-agents. Never download from Dukascopy. Never fetch, read or compute anything dated 2022 or later (a web reply that necessarily carries later data is filtered in memory before anything is printed or written).
THE MACHINE MAY RESTART, and this task may then be started again from the beginning: look at your scratch folder first; if an interrupted run of this same task left work there, read it critically and continue from it; save your work to disk as you go.
THE MACHINE IS SHARED: 4 processors and 15 GB of memory for three agents: at most 1 worker process, memory under about 3 GB, no background process left running when you finish. The kit's full self-test takes about 4 minutes: run it at most twice.
Python: PYTHONDONTWRITEBYTECODE=1 python3 -B ... (no __pycache__ in the working copy). Self-test: PYTHONDONTWRITEBYTECODE=1 python3 -B ${KW}/lab/explore/kit/test_kit.py must end "157/157 checks passed".
Write for a reader who was not there: plain sentences, exact numbers, the script that shows each claim.`

const VERDICT_SCHEMA = { type: 'object', properties: {
  verdict: { type: 'string', enum: ['ok', 'needs_fixes'] },
  issues: { type: 'array', items: { type: 'object', properties: { id: { type: 'string' }, severity: { type: 'string', enum: ['blocking', 'major', 'minor'] }, what: { type: 'string' }, evidence: { type: 'string' }, fix: { type: 'string' }, which_ideas_to_rerun: { type: 'string', description: 'shares / oil / slow track / none: which kinds of idea results this defect could change' } }, required: ['id', 'severity', 'what', 'evidence', 'fix'] } },
  what_was_tested: { type: 'string' } }, required: ['verdict', 'issues', 'what_was_tested'] }
const FIX_SCHEMA = { type: 'object', properties: {
  per_issue: { type: 'array', items: { type: 'object', properties: { id: { type: 'string' }, status: { type: 'string', enum: ['fixed', 'partly', 'not_fixed', 'rejected'] }, change: { type: 'string' }, test: { type: 'string' } }, required: ['id', 'status', 'change', 'test'] } },
  tests: { type: 'string' }, which_ideas_to_rerun: { type: 'string' }, text_changes: { type: 'string' }, limits: { type: 'array', items: { type: 'string' } }, files: { type: 'array', items: { type: 'string' } } },
  required: ['per_issue', 'tests', 'which_ideas_to_rerun', 'limits', 'files'] }

const VERIFY = `You are the third adversarial verifier of a research kit that judges trading ideas. Two earlier verifiers each found defects that would have made verdicts wrong; the second repair has not been checked by anyone. A wrong price adjustment, a cost mistake or a broken look-ahead guard makes verdicts wrong in either direction. Your job is to BREAK the second repair; you fix nothing.

${COMMON}
Edit NOTHING in ${KW}; work in ${SP}/kit_v21/verify3/ (create it). Start by diffing ${SP}/kit_v21/fix2/kit_before against ${KW}/lab/explore/kit and reading every changed line of costs.py, data.py, checks.py, judge.py, sim.py (the test file: read the new tests only).

WHAT TO ATTACK, most important first
1. THE OIL ROLL TABLE (extra_costs.json oil.rolls and rolls_vendor_gap; data._adjust_rolls, _roll_table, price_factor, check_adjusted). Each listed roll is a bar time and a ratio (next / front settlement on the last day before the switch). The adjusted series must show, at each roll, only the real move of that night.
 - For every listed roll compute the adjusted move at the listed bar (vendor gap / ratio). Its typical size on ordinary nights is a few basis points; at the listed rolls the lead measured a median of 16 bp, 4 above 100 bp (2014-03-19 +121, 2015-02-18 -299, 2020-03-18 -126, 2020-04-19 -128) and about ten between 60 and 85 bp. For each roll whose adjusted night move is large, decide with the raw hourly bars and the outside settlements whether (a) the market really moved that night, (b) the vendor switched contracts at ANOTHER bar within about two days (then the raw series holds the true jump elsewhere, and the adjusted series now carries two fake moves of opposite sign a few hours or days apart), or (c) the ratio is wrong. Search each such month for the bar whose raw move best matches the contract spread. Say how many months are (b) or (c), the size of the fake moves, and what they would do to a rule: count how many signals of a plain 72-hour breakout rule and how many touches of a 2 % stop fall on those bars, against the totals.
 - Total check: the product of the ratios against the cumulative C2/C1 at the rolls from the outside file; the adjusted buy-and-hold by year against what a front-month roller earned.
 - The validation path (after rolls_checked_to) on a synthetic file you make yourself: measured ratio, the DataGap on a hole, the private table merged across loads, a Book on bars from an earlier load.
2. THE LOOK-AHEAD GUARD (checks._cut, _asof_prices, data.asof, known_end; KF-2). Find a FALSE PASS: a rule that uses a later roll or split and still passes (levels through a derived series that lost its attrs, a rule that calls data.load_bars or data.price_factor inside build, sim.Book inside build, D20 in price units, an absolute stop). Find a FALSE FAILURE: an honest rule (ratios, breakouts against past highs, ATR in price units compared with price moves, a threshold in percent) that now fails on oil or on a split share, or on an FP market. Check that an exception inside a cut build leaves data.asof unset afterwards; that nested use (an event build and a signal build) works; that the period lock and asof interact rightly (asof later than the period end); the cost in time of the 200 cuts.
3. SHARE SPREADS, TWO LEVELS (KF-5): for five shares and each year, recompute from the lab's one-minute bid/ask (read with ts < 2022) the mean quoted spread at the 09:30 minute and at the hh:00 minutes 10-15, and compare with what sim.Book charges at those bar opens; check which level a CLOSE of the 09 bar, an exit before a closure and a pair leg get; years not listed.
4. DIVIDEND CREDIT (KF-4): hand-check a long and a short across an ex-date at credits 0, 0.7 and 1 against sim.simulate; judge.dividend_report's arithmetic on a small set of trades you build (PF and mean R at credit 0 and 1 recomputed by hand); the 'needs the dividend credit' flag; a pair with a share leg.
5. THE JUDGE'S OUTPUT: with a planted-edge toy rule and a noise rule on (a) a basket of five shares, fast track, (b) oil, (c) a slow-track rule on shares held 30 days with "track": "slow", run the whole chain the way kit/template/run_template.py does (declared.json, truncation test, simulate, neighbours, every, null, judge.verdict): no crash, the noise fails, the planted edge passes, the ledger line and results.json carry PROVISIONAL COSTS, the slow track and the dividend figures; judge.ledger_add accepts the line (on a COPY of LEDGER.md passed as ledger=..., never the real one).
6. THE LEAD'S EDITS: kit/oil_outside.csv now holds date, c1, c2, duka_on (1 / 2 / 0 / empty); the KF-1 test and the --real-bars check were adapted (run test_kit.py --real-bars once: its last line must say all checks passed); the earnings calendar's new column: lab/explore/scout/earnings_edgar.py calendar(drop_late=True) gives 816 rows, its own test passes 30/30.
7. NOTHING ELSE CHANGED: the 16 FP markets give the same trades as the kit before v2.1 (${SP}/kit_v21/builder/ or the first reports name a copy; else compare with ${SP}/kit_v21/fix2/kit_before) on synthetic rules and three real markets.
SEVERITY: blocking = a verdict on shares or oil could be wrong in a way that matters (look-ahead, a fake gain or loss, a cost off by more than about 20 % of the round trip, a crash in the chain); major = wrong but bounded; minor = documentation, a rare case. For each issue say which kinds of idea results it could change (shares / oil / slow track / none).
RETURN: verdict 'ok' or 'needs_fixes'; the issues (id R3-n); what you tested, including what held.`

function fixPrompt(v) {
  return `You repair a research kit that judges trading ideas, after a third adversarial review. Fix what is real, reject what is not (with evidence), and prove each fix with a test that fails before and passes after.

${COMMON}
Edit only ${KW}/lab/explore/kit; your scratch: ${SP}/kit_v21/fix3/ (create it; keep a copy of the kit before your changes there). The verifier's scripts are under ${SP}/kit_v21/verify3/.

THE VERIFIER'S ISSUES
${JSON.stringify(v, null, 1).slice(0, 24000)}

RULES: reproduce each issue first; one test per fix in test_kit.py; keep every existing check passing (157 before you start); re-run the verifier's reproduction scripts on the repaired kit; update README.md; change nothing for the 16 FP markets; no vendor price series in the kit folder (the repository is public: derived flags, ratios and public settlements only; the vendor's prices stay in ~/explore_data). If a fix needs a decision that is not yours (a cost figure, a rule of the charter), take the pessimistic side and say so.
RETURN the structured result: per issue (status, change, test), the last line of the full self-test, WHICH KINDS OF IDEA RESULTS YOUR CHANGES CAN ALTER (shares / oil / slow track / none: the lead re-runs those ideas), any change needed in the text that tells a run how to use the kit, the limits that remain, the files.`
}

const v = await run(VERIFY, { label: 'kit v2.1 round 3: verify', phase: 'Kit round 3 verify', schema: VERDICT_SCHEMA })
if (!v) return { verdict: null }
log('Kit v2.1 round 3 verifier: ' + v.verdict + ', ' + v.issues.length + ' issue(s): ' + v.issues.map(i => i.id + ' ' + i.severity).join(', '))
const real = v.issues.filter(i => i.severity !== 'minor')
if (real.length === 0) return { verdict: v, fix: null }
const f = await run(fixPrompt(v), { label: 'kit v2.1 round 3: repair', phase: 'Kit round 3 repair', schema: FIX_SCHEMA })
return { verdict: v, fix: f }
