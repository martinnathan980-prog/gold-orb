export const meta = {
  name: 'explore-batch-2-pairs',
  description: 'Open strategy search, lead batch 2: test four hedged-pair ideas in sample with the research kit v2 on local price bars (one agent per idea, no validation look, an independent attack on any pass)',
  phases: [
    { title: 'Ideas', detail: 'one agent per idea: declare, test in sample with the kit, attack a pass' },
  ],
}

const SP = '/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad'
const BW = SP + '/explore_wt'
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

const IDEA_SCHEMA = {
  type: 'object',
  properties: {
    ideas: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          number: { type: 'string' },
          title: { type: 'string' },
          folder: { type: 'string' },
          status: { type: 'string', enum: ['fail', 'pass', 'pass_weak', 'insufficient_data', 'not_finished', 'blocked'] },
          n_configs: { type: 'integer' },
          ledger_line: { type: 'string', description: 'res["ledger_line"] of judge.verdict, or a line in the same table format written by hand when no verdict was reached' },
          failed_bars: { type: 'array', items: { type: 'string' } },
          n: { type: 'number' }, pf_net: { type: 'number' }, t: { type: 'number' }, pf_stress: { type: 'number' },
          years_positive: { type: 'string' }, null_pct: { type: 'number' }, corr: { type: 'number' }, dsr_n_all: { type: 'number' },
          declared_sha256: { type: 'string' },
          what_changed_vs_scout: { type: 'string' },
          attack_done: { type: 'boolean' },
          attack_same_trades: { type: 'string', description: 'yes / no / not applicable, with the count of trades compared and the largest difference' },
          plain_reading: { type: 'string', description: 'three or four plain sentences: what the test shows, with the numbers that matter, and what you would look at next' },
          notes_for_lead: { type: 'string' },
        },
        required: ['number', 'title', 'folder', 'status', 'n_configs', 'ledger_line', 'plain_reading'],
      },
    },
    kit_issues: { type: 'array', items: { type: 'string' }, description: 'bugs, missing features or traps met in the kit, with evidence' },
    what_went_wrong: { type: 'string' },
  },
  required: ['ideas'],
}

function ideaPrompt(i) {
  const second = i.also ? `
SECOND IDEA IN THE SAME RUN (same data): after idea ${i.num} is completely finished (results.json written), do idea ${i.also.num} = the scout's idea ${i.also.scout} in its own folder ${BW}/lab/explore/ideas/${i.also.num}_${i.also.slug}/, with its own declaration written before any return of that idea is computed. Its parameters are the scout's, unchanged: you will have seen idea ${i.num}'s result, so write in its declaration "declared after the result of idea ${i.num} was seen; parameters are the scout's, unchanged", and change nothing in the light of that result. Return both ideas.` : ''
  const what = i.special === 'finish'
    ? `YOUR IDEA: 002, "World news tone shock (GDELT)", ALREADY DECLARED by an earlier run that could not get prices. Its folder ${BW}/lab/explore/ideas/002_news_tone/ holds declared.json, declared.sha256 (hash 20a87637...), fetch_gdelt.py (builds the daily tone from GDELT 1.0 daily event files into ~/explore_data/gdelt, about 10 minutes with 8 processes; the GDELT host works) and a run.py written before the kit existed (it downloads prices: do not run it as it is). Read LEDGER.md's line 002 for the state. An interrupted run of this task (the machine restarted) left run_kit.py in that folder and 2,612 of the 3,193 daily tone files in ~/explore_data/idea_002/gdelt (one small JSON per day; fetch the missing days only, with at most 3 processes). Your job: keep declared.json and declared.sha256 byte for byte (the hash must still match; the judge checks it), rebuild the tone series, and run the declared test with the kit: write run_kit.py (prices from kit.data.load_bars, the tone through kit.data.external with the publication lag the declaration implies, signals exactly as declared, truncation test, simulation, neighbours, null, judge.verdict). Where the declaration and the kit differ (for example a stop or exit the kit cannot express), follow the declaration by writing the missing piece on top of kit.costs and kit.data, or, if that is not possible in the time, use the kit's nearest rule and say exactly what differs. The declared basket has four legs (long xauusd, short usdjpy, short us500, short ger40).`
    : i.custom ? `YOUR IDEA: number ${i.num}: ${i.custom} Folder to create: ${BW}/lab/explore/ideas/${i.num}_${i.slug}/.`
    : `YOUR IDEA: number ${i.num} = the scout's idea ${i.scout} (the row of ${BW}/lab/explore/scout/ideas.md that starts with "| ${i.scout}. "). Folder to create: ${BW}/lab/explore/ideas/${i.num}_${i.slug}/.${i.note ? ' ' + i.note : ''}`
  return `You are one run of a trading lab's open search for new trading rules, started by the lead (not by the scheduler). You test ONE idea in sample, honestly, and report. "Nothing works" is a normal and acceptable result; a dressed-up result is the only failure.

WHERE YOU WORK
- Checkout root: ${BW} (a git working copy; run NO git command at all, the lead commits).
- Write only inside your idea folder(s) under ${BW}/lab/explore/ideas/ and in your own cache folder ~/explore_data/idea_${i.num}/ (downloads, intermediate files). Never write anywhere else; never edit the kit, CHARTER.md, IDEAS.md, LEDGER.md or lab/results/val_access.log. The folder ${MAIN} is the lab's main copy: read-only for you.
- No sub-agents, no other AI models. About 60 minutes of work: heavy computing is fine, keep your own steps few.

READ FIRST, IN THIS ORDER
1. ${BW}/lab/explore/CHARTER.md (the rules; skip its steps about pull, push, claiming, IDEAS.md and LEDGER.md: the lead does them).
2. ${BW}/lab/explore/kit/README.md, then kit/template/run_template.py and kit/template/declared.template.json. Use the kit for data, costs, simulation, statistics and the verdict; do not rewrite them. Read the kit's source where the README is not enough (sim.py and judge.py are short).
3. Your idea's row in ${BW}/lab/explore/scout/ideas.md and the sections of ${BW}/lab/explore/scout/sources.md it names: they give tested fetch code and, above all, WHEN each value is known, and what is blocked.

${what}${second}

THE MACHINE MAY RESTART, and this task may then be started again from the beginning. So, before anything else, look at your idea folder and your cache folder. If declared.json and declared.sha256 are already there, an interrupted run of this same task wrote them: keep them byte for byte and continue from where it stopped (read its scripts critically before reusing them; reuse the cached downloads). If results.json is already there, the test is finished: read it and report it, do not run it again. Write files as you go (the declaration first, then run.py, then the results) so that nothing is lost.
THE MACHINE IS SHARED: 4 processors and 15 GB of memory for three agents. Use at most 3 worker processes for downloads or parsing, keep your memory under about 3 GB, never load the lab's one-minute files, and never leave a background process running when you finish.

HOW THIS RUN DIFFERS FROM A SCHEDULED RUN
a. Prices: kit.data.load_bars(fp_key) reads prepared hourly BID bars (in sample only, 2013 to 2021) from ~/explore_data/h1 for xauusd, xagusd, us100, us500, us30, ger40, eurusd, gbpusd, usdjpy, audusd, usdcad, usdchf, nzdusd, eurjpy. NEVER download prices from Dukascopy (it refuses connections); the column 'volume' of these bars is a count of minutes, not traded volume. Crypto bars come from Binance through the kit (that download works). Signal data from other sources: fetch it politely (one host at a time, a pause between requests, cache what you fetch, stop after two refusals from a host), cut at 2021-12-31 in the read, and never fetch, read or compute anything dated 2022 or later.
b. The kit's self-test was run by the lead (122/122): do not run it again. This is kit v2: hedged pairs (sim.pair_book: a pair is ONE market, a basket of pairs is a dict of pair books), exits on a condition (sim.event_exit with its own truncation test), a same-day null for baskets (automatic). Read the README's sections on them and CHARTER.md's kit points 7 to 9. Keep the default cut counts of both truncation tests (about 200 rebuilds each: make build and build_events fast, for example by computing the daily table once outside and only cutting inside) and pass the same rule (exit, stop, target) to simulate and to null_test: the verdict checks both.
c. Do not call judge.ledger_add. Call judge.verdict as the README says (it reads the ledger's running total and writes results.json and trials.jsonl in your idea folder): return its res["ledger_line"].
d. NO validation look, whatever the result: never write val_declared.json, never call unlock_val. If the main configuration passes every in-sample bar (verdict 'pass' or 'pass, weak against selection'), do the attack of charter rule 5: a separate script attack.py written from declared.json only, that does not import your run script nor kit.sim (kit.data and kit.costs are allowed), re-builds the signals and the trades with its own loop, and compares them with the kit's trades (entry times, sides, exits, R); write attack.json with the comparison. Then stop: the lead does the validation look.

THE ORDER OF WORK (charter rule 4: declare before you run)
1. Power first: count the main configuration's signals from the signal data alone (no price move after a signal, no return). If the bars cannot be reached (n >= 250 on one market, or the basket bars), close the idea as insufficient_data without running it.
2. Write declared.json from the template: hypothesis and mechanism, the exact rule, markets, data sources with the time each value is known and its publication lag, the main configuration and its neighbours (at most 11 configurations in all; neighbours are small changes of the main's parameters, fixed now), costs, the bars. The scout's rule is the main configuration; where it cannot be computed as written with hourly bars and the kit (for example an entry at 09:30 New York on hourly bars), declare the nearest computable rule and write what changed and why. Then write declared.sha256 (sha256 of the file, as the template says). Only then compute returns. Never change the declaration after a result; never tune.
3. Run: build(data) returns the whole signal table; checks.truncation_test must pass on the main build; simulate the main, the neighbours and the every-signal variant; stats.null_test with at least 2,000 draws; judge.verdict(...). Keep the code in the idea folder (run.py) so the lead can run it again with:
   PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=${BW}/lab/explore python3 -B ${BW}/lab/explore/ideas/<folder>/run.py
   (always use PYTHONDONTWRITEBYTECODE=1 and python3 -B: no __pycache__ folders in the checkout).
4. Read the verdict honestly. Also report the gross figures (before costs), the long and short sides apart, and each market of a basket: they tell the lead where a failed idea died (no edge at all, or an edge eaten by costs).

TRAPS THE LAB HAS FALLEN INTO BEFORE
- A value used before it is published (the release day and hour matter more than the observation date); a daily series indexed by its date instead of the time it is known; time zones and daylight saving; revised series.
- A signal computed from a bar's close and entered at that same bar's open (a bar's close is known at the bar's END).
- Thresholds or z-scores computed on the whole sample instead of the past only.
- Changing the rule after seeing the result. If you catch yourself wanting to, write the temptation in notes_for_lead instead.

RETURN the structured result: for each idea its number, title, folder, status (fail / pass / pass_weak = 'pass, weak against selection' / insufficient_data / not_finished / blocked), n_configs, the ledger line, the failed bars, the key figures, what you changed against the scout's rule, the attack result if any, a plain reading in three or four sentences, notes for the lead; then the kit issues you met (with evidence) and what went wrong.`
}

const IDEAS = args.ideas

phase('Ideas')
log('Pairs batch: ' + IDEAS.length + ' ideas')
const ideaRuns = parallel(IDEAS.map(i => () =>
  run(ideaPrompt(i), { label: 'idea:' + i.num + (i.also ? '+' + i.also.num : ''), phase: 'Ideas', schema: IDEA_SCHEMA })))

const ideas = await ideaRuns
return { ideas: ideas }
