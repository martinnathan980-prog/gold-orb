export const meta = {
  name: 'explore-daily-batch',
  description: 'Open strategy search, the lead\'s daily batch: test each idea in sample with the research kit v2.1 on local price bars (one agent per idea, no validation look, an independent attack on any pass)',
  phases: [
    { title: 'Ideas', detail: 'one agent per idea: declare, test in sample with the kit, attack a pass' },
  ],
}

// args: { ideas: [ { num, slug, row: "lead/DIRECTION2.md" | "IDEAS.md" } | { num, slug, scout: k } | { num, slug, custom: "<full brief>" }, optional note ], selftest: "148/148 checks passed" }
const SP = '/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad'
const BW = SP + '/explore_wt'
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
          n: { type: 'number' }, pf_net: { type: 'number' }, pf_gross: { type: 'number' }, t: { type: 'number' }, pf_stress: { type: 'number' },
          years_positive: { type: 'string' }, null_pct: { type: 'number' }, corr: { type: 'number' }, dsr_n_all: { type: 'number' },
          declared_sha256: { type: 'string' },
          what_changed_vs_brief: { type: 'string' },
          attack_done: { type: 'boolean' },
          attack_same_trades: { type: 'string', description: 'yes / no / not applicable, with the count of trades compared and the largest difference' },
          plain_reading: { type: 'string', description: 'three or four plain sentences: what the test shows, with the numbers that matter (gross and net, long and short, by market or by year where it matters), and what you would look at next' },
          plain_fr: { type: 'string', description: 'ONE sentence in plain French for a non-specialist (no jargon, no English word, no acronym): what was tested and why it does or does not earn money' },
          notes_for_lead: { type: 'string' },
        },
        required: ['number', 'title', 'folder', 'status', 'n_configs', 'ledger_line', 'plain_reading', 'plain_fr'],
      },
    },
    kit_issues: { type: 'array', items: { type: 'string' }, description: 'bugs, missing features or traps met in the kit or in the earnings calendar, with evidence' },
    what_went_wrong: { type: 'string' },
  },
  required: ['ideas'],
}

function ideaPrompt(i) {
  const what = i.custom
    ? `YOUR IDEA: number ${i.num}. THE BRIEF (the lead's; it is the idea you test, not a suggestion): ${i.custom} Folder to create: ${BW}/lab/explore/ideas/${i.num}_${i.slug}/.${i.note ? ' ' + i.note : ''}`
    : i.row
    ? `YOUR IDEA: number ${i.num} = the row of ${BW}/lab/explore/${i.row} that starts with "| ${i.num} |". That row is the lead's full brief (family, data, the rule, why it may hold, power): it is the idea you test, not a suggestion. Read also the notes under that table. Folder to create: ${BW}/lab/explore/ideas/${i.num}_${i.slug}/.${i.note ? ' ' + i.note : ''}`
    : `YOUR IDEA: number ${i.num} = the scout's idea ${i.scout} (the row of ${BW}/lab/explore/scout/ideas.md that starts with "| ${i.scout}. "). Folder to create: ${BW}/lab/explore/ideas/${i.num}_${i.slug}/.${i.note ? ' ' + i.note : ''}`
  return `You are one run of a trading lab's open search for new trading rules, started by the lead (not by the scheduler). You test ONE idea in sample, honestly, and report. "Nothing works" is a normal and acceptable result; a dressed-up result is the only failure.

WHERE YOU WORK
- Checkout root: ${BW} (a git working copy; run NO git command at all, the lead commits).
- Write only inside your idea folder under ${BW}/lab/explore/ideas/ and in your own cache folder ~/explore_data/idea_${i.num}/ (downloads, intermediate files). Never write anywhere else; never edit the kit, CHARTER.md, IDEAS.md, LEDGER.md, the scout's files, ~/explore_data/h1, ~/explore_data/earnings or lab/results/val_access.log. The folder ${MAIN} is the lab's main copy: read-only for you (the code of the lab's earlier rules is there: lab/robot/SPEC.md section 3, lab/tracks/, lab/r2/tracks/).
- No sub-agents, no other AI models. About 60 minutes of work: heavy computing is fine, keep your own steps few.

READ FIRST, IN THIS ORDER
1. ${BW}/lab/explore/CHARTER.md (the rules; skip its steps about pull, push, claiming, IDEAS.md and LEDGER.md: the lead does them). Its paragraphs on the slow track, US share CFDs, oil, several events at one time and provisional costs are new: read the ones your idea needs.
2. ${BW}/lab/explore/kit/README.md, then kit/template/run_template.py and kit/template/declared.template.json. Use the kit for data, costs, simulation, statistics and the verdict; do not rewrite them. Read the kit's source where the README is not enough (sim.py and judge.py are short).
3. For a scout idea: its row in ${BW}/lab/explore/scout/ideas.md. For any outside data: the section of ${BW}/lab/explore/scout/sources.md about it (tested fetch code and, above all, WHEN each value is known, and what is blocked). For an idea on company earnings: the LAST section of sources.md (earnings releases from SEC EDGAR) and ${BW}/lab/explore/scout/earnings_edgar.py: the calendar is already built in ~/explore_data/earnings (load it with the script's calendar(end=...) function; do not rebuild or re-download it), and that section says what a run must do with each flag and which rows to drop.

${what}

THE MACHINE MAY RESTART, and this task may then be started again from the beginning. So, before anything else, look at your idea folder and your cache folder. If declared.json and declared.sha256 are already there, an interrupted run of this same task wrote them: keep them byte for byte and continue from where it stopped (read its scripts critically before reusing them; reuse the cached downloads). If results.json is already there, the test is finished: read it and report it, do not run it again. Write files as you go (the declaration first, then run.py, then the results) so that nothing is lost.
THE MACHINE IS SHARED: 4 processors and 15 GB of memory for two agents. Use at most 2 worker processes, keep your memory under about 4 GB, never load the lab's one-minute files, and never leave a background process running when you finish.

HOW THIS RUN DIFFERS FROM A SCHEDULED RUN
a. Prices: kit.data.load_bars(key) reads prepared hourly BID bars, in sample only, from ~/explore_data/h1: 2013 to 2021 for xauusd, xagusd, us100, us500, us30, ger40, eurusd, gbpusd, usdjpy, audusd, usdcad, usdchf, nzdusd, eurjpy and for 'oil' (kit v2.1, roll-adjusted by the kit); 2017 to 2021 for 40 US shares (kit v2.1; keys = lower-case tickers, listed in kit/extra_costs.json; split-adjusted by the kit). NEVER download prices from Dukascopy (it refuses connections); the column 'volume' of these bars is a count of minutes, not traded volume. Crypto bars come from Binance (or the earlier venues) through the kit: that download works. Signal data from other sources: fetch it politely (one host at a time, a pause between requests, cache what you fetch, stop after two refusals from a host, a generic User-Agent with nothing personal), cut at 2021-12-31 in the read, and never fetch, read or compute anything dated 2022 or later.
b. The kit's self-test was run by the lead (${args.selftest || 'all checks passed'}): do not run it again. This is kit v2.1: hedged pairs, exits on a condition (sim.event_exit with its own truncation test), a same-day null for baskets (automatic), local-only markets with PROVISIONAL costs (shares, oil), a slow track. Keep the default cut counts of both truncation tests (about 200 rebuilds each: make build and build_events fast, for example by computing the daily table once outside and only cutting inside) and pass the same rule (exit, stop, target) to simulate and to null_test: the verdict checks both.
   SLOW TRACK: only if the brief says so. Then declared.json holds "track": "slow" (exactly that word) and you call judge.verdict(..., max_hold_tdays=40); otherwise leave the default.
   SHARES: simulate share signals with max_wait_h=2; the first bar of a session is labelled 09:00 but opens at 09:30 and an order at its open pays the opening spread (10 to 16 times the usual one): a brief that enters 'at 10:00' means the bar labelled 10:00. Use price ratios, never absolute price levels (shares and oil are back-adjusted).
c. Do not call judge.ledger_add. Call judge.verdict as the README says (it reads the ledger's running total and writes results.json and trials.jsonl in your idea folder): return its res["ledger_line"].
d. NO validation look, whatever the result: never write val_declared.json, never call unlock_val. If the main configuration passes every in-sample bar (verdict 'pass' or 'pass, weak against selection'), do the attack of charter rule 5: a separate script attack.py written from declared.json only, that does not import your run script nor kit.sim (kit.data and kit.costs are allowed), re-builds the signals and the trades with its own loop, and compares them with the kit's trades (entry times, sides, exits, R); write attack.json with the comparison. Then stop: the lead does the validation look.

THE ORDER OF WORK (charter rule 4: declare before you run)
1. Power first: count the main configuration's signals from the signal data alone (no price move after a signal, no return). If the bars cannot be reached (n >= 250 on one market, or the basket bars), close the idea as insufficient_data without running it.
2. Write declared.json from the template: hypothesis and mechanism, the exact rule, markets, data sources with the time each value is known and its publication lag, the main configuration and its neighbours (at most 11 configurations in all; neighbours are small changes of the main's parameters, fixed now), costs, the bars. The brief's rule is the main configuration; where it cannot be computed as written with hourly bars and the kit, declare the nearest computable rule and write what changed and why. Then write declared.sha256 (sha256 of the file, as the template says). Only then compute returns. Never change the declaration after a result; never tune.
3. Run: build(data) returns the whole signal table; checks.truncation_test must pass on the main build; simulate the main, the neighbours and the every-signal variant; stats.null_test with at least 2,000 draws; judge.verdict(...). Keep the code in the idea folder (run.py) so the lead can run it again with:
   PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=${BW}/lab/explore python3 -B ${BW}/lab/explore/ideas/<folder>/run.py
   (always use PYTHONDONTWRITEBYTECODE=1 and python3 -B: no __pycache__ folders in the checkout).
4. Read the verdict honestly. Also report the gross figures (before costs), the long and short sides apart, and each market of a basket (or groups of markets when there are forty): they tell the lead where a failed idea died (no edge at all, or an edge eaten by costs).

TRAPS THE LAB HAS FALLEN INTO BEFORE
- A value used before it is published (the release day and hour matter more than the observation date); a daily series indexed by its date instead of the time it is known; time zones and daylight saving; revised series.
- A signal computed from a bar's close and entered at that same bar's open (a bar's close is known at the bar's END).
- Thresholds or z-scores computed on the whole sample instead of the past only.
- Changing the rule after seeing the result. If you catch yourself wanting to, write the temptation in notes_for_lead instead.

RETURN the structured result: the idea's number, title, folder, status (fail / pass / pass_weak = 'pass, weak against selection' / insufficient_data / not_finished / blocked), n_configs, the ledger line, the failed bars, the key figures (net and gross), what you changed against the brief, the attack result if any, a plain reading in three or four sentences, ONE plain French sentence for the user's sheet, notes for the lead; then the issues you met in the kit or the calendar (with evidence) and what went wrong.`
}

const IDEAS = args.ideas

phase('Ideas')
log('Daily batch: ' + IDEAS.length + ' ideas: ' + IDEAS.map(i => i.num).join(', '))
const ideas = await parallel(IDEAS.map(i => () =>
  run(ideaPrompt(i), { label: 'idea:' + i.num, phase: 'Ideas', schema: IDEA_SCHEMA })))
return { ideas: ideas }
