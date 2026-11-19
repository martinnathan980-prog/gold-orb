export const meta = {
  name: 'lab-archive-map',
  description: 'Read-only inventory of every price-based rule family the lab already tested on gold, silver, oil, currencies, indices and crypto in its earlier rounds, so that the new direction (shocks, indicators, mixes of indicators on always-open markets) does not pay for the same tests twice',
  phases: [
    { title: 'Read', detail: 'three readers over the archives of rounds 1 to 6 and the open search', model: 'sonnet' },
  ],
}

const LAB = '/home/user/gold-orb/lab'

const SCHEMA = {
  type: 'object',
  properties: {
    families: {
      type: 'array',
      description: 'one entry per rule family tested (group close variants together)',
      items: {
        type: 'object',
        properties: {
          family: { type: 'string', description: 'short name, e.g. "RSI mean reversion", "moving-average trend", "opening range breakout"' },
          rule: { type: 'string', description: 'the rule in one or two plain sentences: signal, entry, exit, stop' },
          markets: { type: 'string', description: 'markets it was tested on (gold, silver, oil, eurusd, us100 ...)' },
          bar_size_and_hold: { type: 'string', description: 'bar size used (1 min, 5 min, 1 h, 4 h, daily) and typical holding time' },
          n_configs: { type: 'string', description: 'how many configurations were tried, if the files say' },
          result: { type: 'string', description: 'the outcome with the numbers the files give (profit factor gross and net, t, trades, years) and the verdict: kept in the robot / passed in sample then failed validation / failed in sample' },
          why: { type: 'string', description: 'why it failed or passed, in one sentence (no edge before costs, edge eaten by costs, one period only, market drift ...)' },
          sources: { type: 'string', description: 'the files that say so (paths relative to the lab folder)' },
        },
        required: ['family', 'rule', 'markets', 'result', 'sources'],
      },
    },
    never_tested_seen: { type: 'array', items: { type: 'string' }, description: 'price-based families you looked for in your files and found NO trace of (say which: e.g. "sudden large hourly moves (shocks) on any market", "RSI on oil", "MACD anywhere", "Ichimoku", "volatility squeeze", "ADX filter", "multi-timeframe filter + oscillator"). Only what you actually searched for.' },
    lessons: { type: 'array', items: { type: 'string' }, description: 'lessons the files state themselves (costs per market, horizons that died on costs, what kind of rule survived)' },
    not_read: { type: 'string', description: 'what you could not read or left out, if anything' },
  },
  required: ['families', 'never_tested_seen', 'lessons'],
}

const COMMON = `You are a careful reader making an inventory for a trading research lab. READ ONLY: you change nothing, run no research, write no file. The lab (${LAB}) searched for trading rules in several rounds; the lead now wants to search price-based rules (sudden shocks, classic indicators such as RSI, MACD, moving averages, Bollinger, ADX, stochastics, Ichimoku, new home-made indicators, and mixes of indicators) on markets that trade almost round the clock (gold, silver, oil, euro-dollar and the other major currencies, the US and German indices, bitcoin and ether). He must not pay twice for tests already done. Your job: list every rule family ALREADY TESTED in the files assigned to you, with what was tested exactly, on which markets, with which bar size, how many configurations, and the result with its numbers.

RULES
- Read only text and small result files: .md, .json, .py, small .csv. Use Grep and Glob to find things, Read to read them, and short shell commands (ls, wc, head, python3 -c to print the keys or a few fields of a JSON) when a file is large. NEVER open a .parquet file, never open anything whose path contains "holdout", never run any research script.
- Be exact: quote the numbers the files give (profit factor, t, number of trades, years, costs) and name the file. Do not guess a result: if a family's code exists but you find no result, say so.
- Group close variants in one family, but keep different markets or different bar sizes visible.
- For the field never_tested_seen: actively search your files (grep -ril) for these words before saying a family was never tested: rsi, macd, stochastic, bollinger, keltner, squeeze, adx, ichimoku, supertrend, atr, moving average / sma / ema, donchian, channel, breakout, shock, spike, jump, gap, range expansion, engulfing, inside bar, nr7, pivot, round number, vwap, momentum, mean reversion, z-score, oil / wti / brent / lightcmd, silver / xag.
- Keep each text field short (one to three sentences). Return the structured result only.`

const A = COMMON + `

YOUR FILES (round 1 and the side tracks): ${LAB}/PROTOCOL.md, ${LAB}/PROTOCOL_V2.md, ${LAB}/README.md, ${LAB}/COSTS.md, ${LAB}/COSTS_FP.md, the code in ${LAB}/tracks/ (crossasset, meanrev, orb, pivots, seasonality, trend) and their results in ${LAB}/results/ (crossasset, meanrev, orb, pivots, seasonality, trend, review, report_data_donch4h.json, costs_research.json), ${LAB}/pivbb and ${LAB}/results/pivbb and ${LAB}/results/pivots, ${LAB}/micro and ${LAB}/results/micro, ${LAB}/hybrid, ${LAB}/panel and ${LAB}/results/panel, ${LAB}/report, ${LAB}/results/audit. Say for each family which indicator and which parameters were tried.`

const B = COMMON + `

YOUR FILES (rounds 2 and 3): ${LAB}/PROTOCOL_V3.md from its start to Addendum G (sections 1 to 6 and addenda A to G: read the parts about rules and tracks, skip the long parts about stakes and growth paths), ${LAB}/results/r2/round3_summary.json, the code in ${LAB}/r2/tracks/ and the results in ${LAB}/results/r2/ for these tracks: fx, gold2, idx_eu, idx_us, crypto, carry, dip, events, jours, leadlag, overnight, shape, vol, ml, pivbb_bounce, pivbb_run, pyramid, micro. Also ${LAB}/results/r2/mql5_survey.json if it lists rule ideas. For the tracks fx, gold2, idx_us, idx_eu and crypto be especially complete: every rule family, its markets and its numbers.`

const C = COMMON + `

YOUR FILES (rounds 4 to 6, the autopsy and the open search): ${LAB}/PROTOCOL_V3.md from Addendum H to the end (addenda H, I, J, K, L and their outcomes), ${LAB}/results/r2/round4_ideas.json, the code in ${LAB}/r2/tracks/ and the results in ${LAB}/results/r2/ for: round4, round5, round6, autopsy (especially autopsy/breadth: the ten rules carried to other markets: which rule on which market passed or failed, with numbers), stocks, shape, sizing; then the open search: ${LAB}/explore/CHARTER.md (section 'Families the lab already closed'), ${LAB}/explore/LEDGER.md (every line: idea, markets, verdict, key figures) and ${LAB}/explore/IDEAS.md (statuses). Also read ${LAB}/robot/SPEC.md section 3 and list the ten rules of the robot exactly (signal, market, bar size, exit, stop) as families with result 'kept in the robot'.`

phase('Read')
const parts = await parallel([
  () => agent(A, { label: 'read:round1', phase: 'Read', schema: SCHEMA, model: 'sonnet' }),
  () => agent(B, { label: 'read:rounds2-3', phase: 'Read', schema: SCHEMA, model: 'sonnet' }),
  () => agent(C, { label: 'read:rounds4-6+open', phase: 'Read', schema: SCHEMA, model: 'sonnet' }),
])
const names = ['round1', 'rounds2_3', 'rounds4_6_open']
const out = {}
parts.forEach((p, i) => { out[names[i]] = p })
const missing = names.filter((n, i) => !parts[i])
if (missing.length) log('readers without a result: ' + missing.join(', '))
return out