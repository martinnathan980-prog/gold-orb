export const meta = {
  name: 'scan-build',
  description: 'Direction 4: build the scan of price rules (indicators, shocks, mixes) on synthetic bars only, then have an independent verifier attack it; repairs in at most two rounds. No return is computed on real bars: the lead runs the scan after committing the rule list hash',
  phases: [
    { title: 'Build', detail: 'one builder writes lab/explore/scan from lead/DIRECTION4.md, with its tests' },
    { title: 'Verify', detail: 'an independent verifier attacks look-ahead, the wall, the grammar, the selection' },
    { title: 'Repair', detail: 'the builder repairs what the verifier found; the verifier checks again' },
  ],
}

// args: { selftest: "231/231 checks passed" }
const SP = '/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad'
const BW = SP + '/explore_wt'
const SCAN = BW + '/lab/explore/scan'

async function run(prompt, opts) {
  try {
    const r = await agent(prompt, Object.assign({}, opts, { model: 'opus' }))
    if (r) return r
  } catch (e) {
    log('opus refused or failed for ' + (opts.label || '') + ': retrying on the session model')
  }
  return await agent(prompt, opts)
}

const BUILD_SCHEMA = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['built', 'not_finished', 'blocked'] },
    files: { type: 'array', items: { type: 'string' } },
    rule_count: { type: 'integer' },
    cells: { type: 'integer', description: 'rule x market cells' },
    rules_sha256: { type: 'string', description: 'sha256 of the generated rule list file' },
    tests: { type: 'string', description: 'the last line of the test run and what the tests cover' },
    definitions_fixed: { type: 'array', items: { type: 'string' }, description: 'every detail of DIRECTION4.md you had to make exact (written in scan/GRAMMAR.md), one per line' },
    dead_rules: { type: 'string', description: 'rules with no signal in the counts-only pass on real bars before 2019, and what you did (a bug repaired / left as it is)' },
    timing: { type: 'string', description: 'measured time and memory of the pipeline on synthetic bars, and the estimate for the real scan with 3 processes' },
    how_to_run: { type: 'string', description: 'the exact commands the lead runs: discovery, selection, confirmation, report; and how a restart resumes' },
    notes_for_lead: { type: 'string' },
  },
  required: ['status', 'files', 'tests', 'how_to_run'],
}

const VERIFY_SCHEMA = {
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
          what: { type: 'string' },
          evidence: { type: 'string' },
          fix: { type: 'string' },
        },
        required: ['id', 'severity', 'what', 'evidence'],
      },
    },
    lookahead: { type: 'string' },
    wall: { type: 'string' },
    grammar: { type: 'string', description: 'the rule list against DIRECTION4.md: counts by family, frame, filter, exit; anything missing, extra or defined otherwise' },
    selection: { type: 'string', description: 'selection and confirmation code against sections 4 and 5, with the edge cases tried' },
    noise_worlds: { type: 'string', description: 'what the pipeline picks and confirms on synthetic worlds without any edge, and on a world with a planted edge' },
    summary: { type: 'string' },
  },
  required: ['verdict', 'findings', 'lookahead', 'wall', 'grammar', 'selection', 'summary'],
}

const COMMON = `WHERE YOU WORK
- Checkout root: ${BW} (a git working copy; run NO git command, the lead commits). The lab's research kit is ${BW}/lab/explore/kit (README.md first; data.py, sim.py, stats.py, checks.py, synth.py). The kit's self-test was run by the lead (${args && args.selftest ? args.selftest : 'all checks passed'}): do not run it.
- The specification is ${BW}/lab/explore/lead/DIRECTION4.md: a pre-registration. It is followed to the letter; it is never edited.
- SYNTHETIC BARS ONLY (kit.synth) for everything that computes a return, a trade or a statistic. Real bars (kit.data.load_bars) may be read for ONE purpose: counting signals per rule on bars before 2019-01-01 (no price move after a signal, no return, no trade). The lead runs the real scan later, after the rule list's hash is committed.
- No sub-agents, no other AI models, no download. The machine is shared (4 processors, 15 GB): at most 2 worker processes while you develop, under 4 GB of memory, no background process left behind. Use PYTHONDONTWRITEBYTECODE=1 and python3 -B with PYTHONPATH=${BW}/lab/explore (no __pycache__ in the checkout).
- Never write under the kit, CHARTER.md, IDEAS.md, LEDGER.md or lead/. Scratch files go to ~/explore_data/scan_dev/.`

const buildPrompt = `You build one tool for a trading research lab: a scan that tests about 1,390 price rules (classic indicators, sudden shocks, home-made indicators, and mixes of a signal with a filter) on 15 markets, in three stages that keep false discoveries rare. Real money follows the lab's verdicts later, so a silent look-ahead or a leak between the stages would be the worst outcome; a slow or plain tool is fine.

${COMMON}

WHAT TO BUILD, in ${SCAN}/ (a Python package next to kit/, imported as 'scan'):
- frames.py: H4 and D1 bars from the kit's hourly bars (blocks and days that start at 17:00 New York), each with the time its values are KNOWN (the end of its last hourly bar).
- indicators.py: EMA, SMA, RSI (Wilder), MACD, ATR (Wilder), ADX and +DI/-DI, Bollinger, Keltner, Stochastic, CCI, SuperTrend, Ichimoku, Parabolic SAR, efficiency ratio, internal bar strength, rolling standard deviation. Plain numpy/pandas, causal: the value at a bar uses that bar and earlier bars only.
- grammar.py: the exact rule list of DIRECTION4.md section 2 (signal x frame x filter x exit), with stable ids such as 'T04|H4|F1|72h'; writes scan/rules.csv and prints its sha256. GRAMMAR.md: every definition made exact (crossing conventions, warm-up bars, ties, what 'first bar where it holds' means, the session clock, the round-level grids, siblings of each rule for section 4).
- signals.py: for one market, the signal table (known_at, side) of every rule, computed once per signal-frame and reused across filters and exits.
- engine.py: trades through kit.sim.simulate (mode 'one', exit ('hours', N), stop ('d20', 2.0), the kit's costs, max_wait_h such that a signal known when the market is shut is entered at the reopening only if that is within 2 hours, otherwise dropped: say what you chose in GRAMMAR.md), then per rule and market: daily sums of net R, of R at costs x1.5 and of gross R, the number of trades, by year.
- discover.py: stage 1 on bars BEFORE 2019-01-01 only (the reader cuts the bars and asserts it); resumable (one small file per market or chunk under ~/explore_data/scan/, a restart skips what is done and gives the same tables); a --counts-only mode that writes signal counts and computes no return; a --synthetic mode for the tests.
- select.py: section 4 exactly (units, eligibility, ranking, the correlation rule, at most 12 baskets then 12 single markets); writes frozen_candidates.json and prints its sha256.
- confirm.py: section 5 exactly, for the frozen list only (it refuses a list whose sha256 is not the one given on the command line), with the kit's random-entry null (2,000 draws) and the same-year null as information.
- report.py: discovery_summary.json (counts; for each family and frame the share of rules with t > 2 and t < -2 on each unit, mean gross and net R; the eligible table), confirmation.json, and a short plain-text summary.
- run_all.sh: discovery (3 processes), selection, confirmation, report, in that order, logging to ~/explore_data/scan/run.log; safe to start again after a restart.
- test_scan.py: (1) each indicator against a second, plain implementation written in the test; (2) NO LOOK-AHEAD: for every signal id and frame, signals computed on bars cut at 40 random times equal the full run's signals up to each cut, and an H4 or D1 value is never used before its last hourly bar has closed; (3) the wall: discovery refuses or cuts any bar of 2019 or later; confirm refuses a wrong hash; (4) a planted world: synthetic bars in which one rule's signals are followed by a drift: the pipeline picks and confirms it; (5) a world without any edge, reduced grammar: how many picks, how many confirmed (report the numbers); (6) determinism and resume; (7) the rule count and the list's hash.

HOW TO WORK
- Read DIRECTION4.md, then the kit's README sections on load_bars, sim.simulate, costs, synth, checks.truncation_test. Keep your own steps few; heavy computing is fine.
- Speed target: the real discovery (about 20,800 rule-market cells on about 37,000 hourly bars per market) in under two hours with 3 processes. Compute each signal-frame once per market; do not call sim.simulate more often than needed.
- Never tune anything on a result. A definition is fixed from the text of DIRECTION4.md and the usual textbook meaning, then written in GRAMMAR.md.
- At the end run the counts-only pass on real bars before 2019 and report rules without signals.

RETURN the structured result (files, rule count, the list's sha256, the tests' last line, every definition you fixed, the dead rules, timing, the exact commands for the lead).`

const verifyPrompt = (build) => `You are an independent, adversarial verifier. Another agent has just built a scan of trading rules for a research lab; real money follows the lab's verdicts later. Your job is to BREAK it: default to reporting a defect when a check leaves a real doubt.

${COMMON}
- You write ONLY in ${SP}/scan_review/ (your scripts and outputs). You change nothing under ${SCAN}/.

THE BUILDER'S REPORT: ${JSON.stringify(build).slice(0, 6000)}

ATTACK (report numbers and script paths)
1. LOOK-AHEAD. Your own harness, not the builder's test: for every signal id of DIRECTION4.md and each frame, compute the signals on synthetic bars, then on the same bars cut at random times, and compare; change a bar AFTER a signal's known time and check the signal does not move. Check the H4 and D1 frames: when is a block's value first used, around the daily break of the indices, at week ends, at daylight-saving changes? Check each indicator against your own plain implementation (RSI and ATR in Wilder's form, MACD, ADX, Ichimoku's shifted spans in particular: the cloud that is 'ahead' must not be read from the future).
2. THE WALL. Can any code path of discovery or selection read a bar, a trade or a statistic of 2019 or later? Can confirmation be run on a list other than the frozen one, or twice with different lists? What does a restart in the middle do?
3. THE GRAMMAR. The generated rule list against DIRECTION4.md section 2: every signal, frame, filter and exit present once; nothing extra; R08 not on H1, L01 not on oil, F5-F7 on H1 only; the definitions of GRAMMAR.md against the text (say where the builder's choice changes the meaning).
4. THE ENGINE. For ten random rule-market cells on synthetic bars, rebuild the trades with your own direct call to kit.sim.simulate from the signal table and compare trade by trade; check the one-position rule, the stop, the exits in hours over a week end, the costs (net, x1.5, gross) and the daily sums.
5. SELECTION AND CONFIRMATION against sections 4 and 5: units, eligibility numbers, the sibling rule, ranking, the correlation rule, the caps, ties, an empty result; the null calls. Feed hand-made tables with known answers.
6. NOISE AND A PLANTED EDGE. On synthetic worlds without any edge (a reduced grammar and three or four markets if the full one is too slow): how many rule-units pass the discovery thresholds, how many are picked, how many confirmed, over at least ten worlds; does the t of the whole grammar look like noise? With one planted rule: is it found and confirmed?
7. PRACTICAL. Time and memory of a discovery run on synthetic bars of the real size; the estimate for the real run; what a restart does.

RETURN the structured result. blocking = a look-ahead, a leak across the wall, or a selection that does not do what DIRECTION4.md says; major = wrong figures that would mislead the lead; minor / note otherwise.`

phase('Build')
let build = await run(buildPrompt, { label: 'build:scan', phase: 'Build', schema: BUILD_SCHEMA })
if (!build || build.status !== 'built') return { build: build, rounds: [] }

const rounds = []
for (let i = 0; i < 2; i++) {
  phase('Verify')
  const v = await run(verifyPrompt(build), { label: 'verify:scan:' + (i + 1), phase: 'Verify', schema: VERIFY_SCHEMA })
  rounds.push({ verify: v })
  const bad = v && v.findings ? v.findings.filter(f => f.severity === 'blocking' || f.severity === 'major') : []
  if (!v || bad.length === 0) break
  phase('Repair')
  const fix = await run(`You built the scan in ${SCAN}/ for a trading research lab (specification: ${BW}/lab/explore/lead/DIRECTION4.md, followed to the letter). An independent verifier found defects. Repair every blocking and major one, and the minor ones that are cheap; add a test for each repair; run test_scan.py; change nothing else and never tune on a result.

${COMMON}

THE FINDINGS: ${JSON.stringify(v.findings).slice(0, 12000)}
The verifier's scripts are in ${SP}/scan_review/ (read-only for you).

RETURN the same structured result as a build (files, rule count, the rule list's sha256 if it changed and why, the tests' last line, definitions fixed, the commands for the lead), and in notes_for_lead what you did for each finding id.`, { label: 'repair:scan:' + (i + 1), phase: 'Repair', schema: BUILD_SCHEMA })
  rounds[rounds.length - 1].repair = fix
  if (fix && fix.status === 'built') build = fix
  else break
}
return { build: build, rounds: rounds }
