export const meta = {
  name: 'kit-v23-adversarial-review',
  description: 'Adversarial review of the research kit v2.3 changes (same-year null as information, event calendars with a market column): one independent verifier tries to break them and reports defects with evidence',
  phases: [
    { title: 'Review', detail: 'one verifier: regression of the judged null, calibration and mechanics of the same-year null, the judge, the event-table exemption, the documentation' },
  ],
}

const SP = '/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad'
const NEW = SP + '/kit_v2_wt'
const OLD = '/home/user/gold-orb'
const OUT = SP + '/kit_review/v23'

const SCHEMA = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['sound', 'defects_found', 'not_finished'] },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          severity: { type: 'string', enum: ['blocking', 'major', 'minor', 'note'] },
          what: { type: 'string', description: 'the defect, in one or two plain sentences' },
          evidence: { type: 'string', description: 'the script you ran (path) and the numbers it printed, or the file and line' },
          fix: { type: 'string', description: 'the smallest change that repairs it' },
        },
        required: ['id', 'severity', 'what', 'evidence'],
      },
    },
    regression: { type: 'string', description: 'the judged null (within=None) and judge.verdict without null_year against the kit before the change: which cases you compared, and whether every number is identical' },
    calibration: { type: 'string', description: 'your own measurement of the same-year null on rules without timing (percentile distribution) and with a planted timing edge' },
    event_table: { type: 'string', description: 'what you tried to slip past the new exemption and what happened' },
    docs: { type: 'string', description: 'README v2.3 section, the template, the CHARTER paragraph: anything wrong, unclear or missing' },
    summary: { type: 'string' },
  },
  required: ['verdict', 'findings', 'regression', 'calibration', 'event_table', 'summary'],
}

const prompt = `You are an independent, adversarial verifier of a small change to a trading lab's research kit. The kit judges trading ideas with real money at stake later; a silent error in its statistics would let a false strategy through or kill a true one. Your job is to BREAK the change if you can, with evidence (a script and its output). Finding nothing after honest attempts is an acceptable result; an unverified "looks fine" is not.

WHERE THINGS ARE
- The kit AFTER the change: ${NEW}/lab/explore/kit (stats.py, judge.py, checks.py, test_kit.py, README.md, template/run_template.py) and ${NEW}/lab/explore/CHARTER.md. See exactly what changed with: git -C ${NEW} diff (read-only git commands only: diff, status, log, show; nothing that writes).
- The kit BEFORE the change: ${OLD}/lab/explore/kit (the lab's main copy at the previous commit; read-only for you).
- Write ONLY in ${OUT}/ (create it; your scripts and outputs). Never edit the kit, the charter or anything else. No sub-agents, no other AI models. The machine is shared: at most 2 worker processes, under 4 GB of memory, no background process left behind. A full self-test of the new kit is already running elsewhere: do not run the whole test_kit.py; you may run single tests with: PYTHONDONTWRITEBYTECODE=1 python3 -B ${NEW}/lab/explore/kit/test_kit.py --only <substring>.
- Import the new kit with PYTHONPATH=${NEW}/lab/explore and the old one with PYTHONPATH=${OLD}/lab/explore (separate processes), always with PYTHONDONTWRITEBYTECODE=1 and python3 -B. Use the kit's synthetic bars (kit.synth) for your experiments; no market data is needed and none may be downloaded.

WHAT CHANGED (kit v2.3)
1. stats.null_test(..., within=None | 'year') and stats._null_joint(..., within=): within=None is the JUDGED random-entry null, meant to be unchanged bit for bit; within='year' draws each trade's random day in the trade's own calendar year (New York date of its entry; for a group of legs decided together, the year of the group's first leg). The result carries 'within'.
2. judge.verdict(..., null_year=None): records the same-year null in results.json ('null_same_year', with 'usable') and in the ledger line; INFORMATION only: it must change no bar and no verdict. A null run with within='year' passed as the judged 'null' must fail the null bar.
3. checks._is_event_table / checks._check_row_len: a table made by data.event_table (index named known_at, column obs_date, attrs min_lag, no open/high/low/close column) is exempt from the daily-bars row-length guard (V22-3), so an event calendar with a 'market' column of universe shares, stamped at the events' own times, takes row_len 0.
4. Documentation: README.md section 'Kit v2.3', template/run_template.py (null_year), CHARTER.md paragraph 'Rules on one side, signals bunched in time'.
5. Tests: test_v23_same_year_null and test_v23_event_table_row_len in test_kit.py.

ATTACK IT (do all; report numbers)
A. REGRESSION of the judged null. In separate processes, run the OLD and the NEW kit on the same synthetic cases and seeds and compare the full result dicts (percentile, null_mean, null_sd, the first 20 draw means): mode 'every' and mode 'one'; one market and several markets; a basket whose legs share a known_at (the joint path) and joint=False; long-only, short-only and mixed sides; an exit with a stop and a target; an event exit (sim.event_exit, see README) if you can build one quickly; a hedged pair (sim.pair_book) if quick. Every number must be identical. Also judge.verdict without null_year: identical results.json content apart from time stamps and the new key.
B. THE SAME-YEAR NULL, mechanics. For trades of one market: is every random day really of the trade's own New York calendar year (instrument it: wrap or re-implement the pool selection, or check through a market whose return identifies the year)? Entries near midnight UTC on 31 December or 1 January (New York date against UTC date), a crypto market (24/7 with the weekend closure removed), clocks that exist only part of the year (daylight saving: a 00:00 UTC entry is 19:00 or 20:00 New York), a year with very few candidate days, a trade in the last weeks of the sample (candidates without a complete trade), mode 'one', the joint path (a group whose legs have different years? a group with no common day in its year?), a pair. Does anything crash, silently fall back to the whole sample, or draw from the wrong year?
C. THE SAME-YEAR NULL, statistics. On rules WITHOUT timing (random days, one side, signals bunched in drifting years; also evenly spread; also two-sided) is its percentile uniform (at least 60 worlds, a KS test, the share at or above 97.5)? Is it biased when a year holds very few trades or when almost every candidate day of a year is a signal day (drawing with replacement from a small pool: does the null's spread become too narrow or too wide)? With a planted timing edge spread over the years, does it keep the power of the judged null? Say plainly if you find a case where it would mislead the lead (too generous or too harsh), since it is used as information before a validation look.
D. THE JUDGE. Try to make null_year change a verdict, a bar or the DSR; pass malformed dicts (missing keys, percentile None or NaN, n_draws as a string, within='YEAR'); pass the same dict as null and null_year; check results.json stays valid JSON and that 'means' never lands in it; check the ledger line still parses as one table row (no '|' or newline added).
E. THE EVENT-TABLE EXEMPTION. The guard it relaxes exists so that a cut of the truncation test never keeps a daily session before its close is known. Try to launder a look-ahead through the exemption: daily share bars (kit.synth.d1_bars, universe keys from kit/universe_us.csv) turned into an 'event table' stamped at the session OPEN with min_lag 0 and a numeric column holding the day's close-to-close return or the close under another name ('value', 'c', 'px'); a build that then reads that column at the open. Does the truncation test still catch the leak by other means (its own cut logic, the price-level guard), or does it now pass a leaking build that the kit before the change refused? Compare OLD and NEW on the same case. Also: does an honest calendar (events stamped at their acceptance times, any minute, with a 'market' column) now pass where the old kit refused, and is the result of the truncation test the same as when the column is named 'ticker'? Tables that should stay refused (bars, hand-made table with a 'market' column of shares, an event table with a close column, one whose attrs were lost by a merge or concat): are they?
F. THE DOCUMENTATION. Read the README section, the template and the charter paragraph against the code: any statement that is false, an example that does not run (run the template's own test: --only template), a number that does not match the tests (the README says 210 checks, 212 with --real-bars: count the check(...) calls that run by default if you can do it cheaply, otherwise say you did not).

RETURN the structured result: verdict ('sound' only if A to E hold), every finding with its severity (blocking = the judged statistics changed or a look-ahead now passes; major = the same-year null misleads; minor / note otherwise), evidence and the smallest fix.`

phase('Review')
const r = await agent(prompt, { label: 'review:kit-v2.3', phase: 'Review', schema: SCHEMA })
return r