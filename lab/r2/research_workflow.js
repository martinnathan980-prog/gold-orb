export const meta = {
  name: 'r2-research',
  description: 'Round-2 research under PROTOCOL_V2: each track researches its idea on in-sample data, validates its finalists once, then every passing finalist is attacked by three independent reviewers and judged',
  phases: [
    { title: 'Research', detail: 'one agent per track: in-sample research, then single-shot validation' },
    { title: 'Verify', detail: 'three adversarial lenses per passing finalist' },
    { title: 'Judge', detail: 'GO / DISQUALIFY per finalist' },
  ],
}

const LAB = '/home/user/gold-orb/lab'

const TRACKS = {
  idx_us: `MARKETS: us100 (Nasdaq 100), us500 (S&P 500), us30 (Dow) index CFDs. Index data before 2014 is incomplete (limited quoting hours): start in 2014.
WHY THIS TRACK: index CFDs have the lowest cost relative to movement of all our markets (spread about 0.6-0.8 bp vs an hourly range of 20-40 bp), and intraday momentum in US equity indices is documented: first-half-hour -> last-half-hour momentum (Gao, Han, Li, Zhou 2018), end-of-day momentum driven by option-hedging flows (Baltussen et al. 2021), opening-range breakouts (Zarattini & Aziz 2023) and the "noise area" intraday momentum rule (Zarattini, Aziz, Barbon 2024: enter when price leaves a band around the open whose width is the average absolute move from the open to that time of day over the last ~14 sessions; trail; flat at the close). None of this has been tested in this lab.
IDEAS (pick a disciplined subset): opening-range breakout at 09:30 New York (5/15/30 min ranges; stop at the other side of the range or a fraction of ATR; exit at 15:55 NY or trailing); the noise-area breakout checked at fixed clock times; last 30-60 minutes momentum conditional on the day's move; gap continuation / fade; the same rule on the three indices as a basket. Sessions are in New York local time (DST!). Indices rose strongly in 2014-2021: long-only profits are suspect; show long vs short, and pass the random-entry null.`,

  idx_eu: `MARKET: ger40 (DAX CFD, quoted in EUR; data from late 2013 with real bid/ask) — you may also read us500 as a predictor (load, extract what you need, free it).
WHY THIS TRACK: in round 1 a single untuned opening-range breakout (08:00-09:00 London range) on the DAX was "the steadiest" of 24 market x rule cells (7/9 years positive, gross PF 1.13) but was only tested with a fixed synthetic spread. The DAX has a real cash open (09:00 Frankfurt, Xetra opening auction), a second impulse at the US open (15:30 Frankfurt) and a cash close at 17:30. Cost is low relative to movement (about 0.6 bp spread).
IDEAS: opening-range breakouts around 08:00 and 09:00 Frankfurt (15/30/60 min), stop at the other side or ATR fraction, exit at a fixed time or trailing; US-open impulse; close-to-close gap logic using the US move after 17:30 Frankfurt (is the gap continued or faded after 09:00?); morning trend continuation into the afternoon. Use "Europe/Berlin" local time. Show long vs short (the DAX rose over the sample).`,

  crypto: `MARKETS: btcusd, ethusd CFDs. First check the data: when it really starts, whether weekends are present, holes, crazy prints. In-sample is short (start of data -> 2021), validation 2022-2025.
WHY THIS TRACK: crypto moves 2-3 times more than gold per hour while the CFD spread is about 2 bp, so cost relative to movement is low; short-horizon trend persistence in bitcoin has been one of the strongest systematic effects of the last decade (though decaying); the market trades 24/7, which gives more trades. Never tested in this lab. Overnight financing on crypto CFDs is expensive (see r2.SPEC swaps): prefer holds of hours, at most 1-3 days.
IDEAS: channel breakouts on 1h/4h with ATR stop and trailing; volatility-compression breakouts; intraday time-series momentum by session (Asia / Europe / US hours); weekend vs weekday behaviour; pullback entries in a trend. BTC rose enormously in-sample: long-only profit means nothing; show long vs short and pass the random-entry null. Leave BTC->ETH lead-lag to the leadlag track.`,

  gold2: `MARKETS: xauusd (gold) and xagusd (silver) under FP costs.
CONTEXT: round 1 used conservative costs (about 0.8 USD per round trip in 2013-2021). Under FP costs the round-1 survivor (trend/donch4h_stop: 60-bar 4h channel breakout with stop entries and a 2xATR trailing stop) has IS PF 1.51, t 3.2 on the FP frame; the lead will include it as a legacy sleeve, so do NOT resubmit it. Round 1 also measured small positive GROSS edges that costs killed: London-open range breakout (08:00-08:30/09:00 London: +0.14 to +0.19 R gross), US 09:30 NY 15-minute range breakout (+0.16 R), Asian-range breakout (00:00-07:00 London, +0.11 R), first touch of a 100-dollar round number in London/NY hours (stop-entry breakout), and after large moves gold tends to continue rather than revert. Details: lab/results/{orb,pivots,trend,meanrev}/report.md and lab/results/orb/gross_vs_net_is.json.
YOUR JOB: (1) CONFIRMATORY re-tests under FP costs of those round-1 gross-positive rules with their round-1 parameters, pre-declared, no re-tuning (each counts as a trial): do any become real sleeves at today's costs? (2) NEW sleeves that ADD trades without duplicating the 4h breakout: breakouts on faster bars (1h/2h) with multi-day channels, pullback entries inside a trend, volatility-contraction breakouts, session-restricted trend (London/NY overlap only); (3) silver as an independent check: the same rule with the same parameters on xagusd (silver costs much more: see r2.SPEC).
HONESTY NOTE: validation data (2022-2025) for gold was already consulted in round 1 for other rules, and you have read those reports; say so, and treat the every-signal diagnostic and the null test as mandatory.`,

  events: `MARKETS: xauusd, us100, us500 (and btcusd if useful), around scheduled US macro releases.
CALENDAR: lab/tracks/seasonality/calendars.py already holds FOMC statement dates and NFP release dates for 2013-2025 (check them). Add CPI release dates from the BLS archive (public schedule; you may fetch it). Use only release times known in advance (NFP and CPI at 08:30 New York, FOMC statement at 14:00 New York).
WHY THIS TRACK: the user asked for attention to macro events. Round 1 (gold only, conservative costs) found no drift before or after NFP and a suggestive follow-through after FOMC (t about 2.3, 8 events a year). Not yet tested: equity indices around the same events; the pre-FOMC drift in equities (Lucca & Moench); a breakout bracket placed just before the release; momentum entered a few minutes after the release once the spread has normalised; CPI days.
IMPORTANT: real fills around news are worse than any model (spreads blow out, stops slip). Judge your event sleeves on the cost-stress run (x1.5), and treat entries in the first minute after a release as untradeable. Frequency is low (about 30-35 events a year): the protocol allows a basket across instruments with identical parameters to reach the 250-trade bar.`,

  leadlag: `MARKETS: pairs among xauusd/xagusd, btcusd/ethusd, us100/us500/us30, us500/ger40, btcusd/us100.
WHY THIS TRACK: round 1 found that gold absorbs a dollar move within the same 5-minute bar (no tradable lag). Untested: does a LESS liquid market lag its leader at the 1-15 minute horizon — silver after gold, ether after bitcoin, the Dow or S&P after the Nasdaq (and the reverse), the DAX after the S&P outside cash hours, bitcoin against the Nasdaq in US hours? The follower's cost is what matters (silver and ether are expensive, us500/us30 are cheap).
METHOD: descriptive first (in-sample): for each pair, regress the follower's next 1/5/15/30-minute return on the leader's last 1/5/15-minute move not yet matched by the follower (rolling beta from past data only); look at the tails (largest 1% / 0.1% leader moves) and compare the predicted catch-up in bp with the follower's round-trip cost. Only if an effect is larger than about twice the cost, turn it into a rule (enter the follower at the next minute, tight stop, exit after N minutes). Also test "relative-strength" intraday momentum between the three US indices (long the strongest, short the weakest from a fixed time to the close) as two-legged trades simulated per leg. Memory: load the leader, keep only the series you need, r2.free(), then load the follower. Align on bar CLOSE times; the predictor bar must be closed before the follower entry.`,

  ml: `"OUR OWN INDICATOR": a learned filter, built only from our data. MARKETS: any of the 8 (r2.SYMS), one at a time.
IDEA: take a broad, simple candidate generator with fixed exits (for example: every 1h close that makes a new 24-48h high or low -> breakout candidate in that direction, stop k x ATR, trailing, time exit; or every session-open range break), which alone is about break-even, and learn WHEN it pays. Features must be causal and cheap to compute in an MT5 Expert Advisor: time of day / day of week, volatility regime (ATR percentile vs its own past), range compression, distance from the previous day's high/low and from round numbers, multi-horizon past returns, trend strength, size of the breakout bar, spread level, recent result of the same signal. Model: SMALL and exportable — logistic regression or a shallow tree ensemble (depth <= 3, <= 60 trees) or a hand-readable scorecard — because it has to be re-coded in MQL5; save it as JSON in your track folder (pip install scikit-learn is allowed; no GPU, no deep nets).
STRICT ANTI-OVERFITTING PROCEDURE: all in-sample numbers you report for a filtered sleeve MUST come from walk-forward out-of-fold predictions (train on years < Y with a purge gap of at least the maximum holding time, predict year Y, for Y from the 4th year of data to 2021). Feature choice, model type, hyper-parameters and the score threshold each count as trials (log them). The sleeve's in-sample trades = candidates whose out-of-fold score passes the threshold. The frozen model for validation = trained on all in-sample data with the chosen settings; validation is then run ONCE on 2022-2025 through r2.validate with a make_orders that loads the frozen JSON model. Also report the unfiltered candidate generator (the baseline the filter must beat) and a permutation test (labels shuffled within year: the walk-forward gain must vanish).
A filter that only removes trades in one known regime (e.g. "skip low volatility") is a rule, not a model: if a 1-2 threshold rule does as well as the model, prefer the rule and say so.`,

  overnight: `MARKETS: us500, us100, ger40, btcusd, xauusd — session, overnight and calendar effects, held hours to a few days, with overnight financing included (r2.SPEC swaps; triple swap once a week is already in the engine).
WHY THIS TRACK: documented effects never tested here: the overnight drift of US equity indices (returns earned between the close and the next open, concentrated around the European open; Boyarchenko, Larsen, Whelan 2020; Cooper, Cliff, Gulen 2008), intraday reversal vs overnight continuation, turn-of-month and day-of-week effects in indices, weekend and hour-of-day patterns in bitcoin. Round 1 did this for gold only (effects of 1-2 bp per hour, below the old costs — re-check the gold Friday-afternoon / weekend drift under FP costs with the round-1 definition, as one pre-declared trial).
METHOD: descriptive first (in-sample mean return and t-stat per window, per year, with a count of how many windows you looked at — multiple testing!), then turn only the robust, mechanism-backed windows into timed trades (enter at time X, exit at time Y, protective stop k x ATR). Calendar rules are judged with r2.null_test(..., mode="time"): the window must beat random windows of the same length and side, otherwise it is just "the index went up". Dividend adjustments on cash-index CFDs are not modelled: say so. State clearly for each sleeve whether it is market beta held at particular hours (it will behave like a leveraged long position in a crash) or a genuinely timing-dependent effect.`,
}

const COMMON = (key) => `You are one of 8 parallel quant researchers in ROUND 2 of a research programme. Your track: **${key}**.

THE USER'S GOAL. A fully automated MetaTrader 5 robot on an FP Markets Standard account (spread only, no commission), leverage 1:500, capital 1,000 EUR that he is ready to lose, hard stop when 500 EUR is left. He wants several trades a day, losses cut quickly, many small gains that add up, and the fastest growth we can honestly find. Round 1 (gold only, conservative costs, one rule at a time, 321 configurations) found one surviving rule (a 10-day channel breakout on 4h bars, about 1 trade a week): real but too slow for him. Round 2 looks where round 1 did not: new markets, a PORTFOLIO of small rules ("sleeves"), and the real costs of his account.
An honest "nothing survives on this track" is a valuable answer. Do not torture the data: every extra configuration lowers the value of your best one.

READ FIRST (all short): ${LAB}/PROTOCOL_V2.md (frozen criteria), ${LAB}/r2/README.md (toolkit, pitfalls, account constraints), ${LAB}/goldlab/r2.py, and the fill-rule docstring at the top of ${LAB}/goldlab/sim.py. Round-1 context when relevant: ${LAB}/results/<orb|pivots|seasonality|trend|meanrev|crossasset>/report.md.

HARD RULES
1. Research and tuning ONLY on the in-sample period (entries before 2022-01-01). Budget: at most 120 evaluated configurations, EVERY one logged with r2.log_trial("${key}", sym, params, ev). Use r2.evaluate(..., full=False) while exploring and full=True for the shortlist.
2. Choose at most 2 finalists. A finalist = one rule with ONE fixed parameter set, applied to 1-3 instruments; each instrument is a "sleeve" (a basket evaluation is allowed as PROTOCOL_V2 says). For each finalist: in-sample criteria via r2.is_criteria (includes cost stress and the every-signal run), neighbour robustness (each tuned parameter at about +/-20% or the adjacent grid values; report the median PF), the random-entry null r2.null_test (mode "day" for signal rules, "time" for calendar rules; needs >= 97.5th percentile), long vs short split, gross edge per trade in the first vs second half of the in-sample period (is it eroding?), median stop distance in 2024-2025 and its money value on the minimum lot. Decide the finalists BEFORE any validation access and write that decision to ${LAB}/results/r2/${key}/finalists_preval.json.
3. Then, once per finalist sleeve: r2.validate(sym, make_orders, params, "${key}", name). No re-tuning afterwards, whatever the result. Report it as it is, even if it fails.
4. Causality and fill realism: the pitfalls in r2/README.md are all real. Prove causality with a truncation test (orders built on data cut at a few random times must equal the orders built on the full data up to those times).
5. Do NOT edit ${LAB}/goldlab/ or other tracks' folders (if you suspect an engine bug: minimal repro in your output, workaround in your own code). Do NOT git commit. Do NOT download market data. NEVER load 2026 data (no include_holdout=True). You may web-search literature and public calendars.
6. Resources are shared with up to 7 other agents on 4 CPUs / 15 GB RAM: single process, no multiprocessing, one symbol loaded at a time (r2.free()), stay under about 2.5 GB.

DELIVERABLES
- ${LAB}/r2/tracks/${key}/strategy.py exposing make_orders(m1, **params) (it must work on ANY M1 frame of that market: it will be re-run on the 2026 holdout, and its logic ported to an MT5 Expert Advisor — keep the rule simple enough to code in MQL5) and FINALISTS = {name: {"syms": [...], "params": {...}}}.
- ${LAB}/results/r2/${key}/: trials.jsonl (written by log_trial), finalists_preval.json, candidates.json and any supporting .json/.csv/.txt.
- Your structured output. You cannot write .md files, so put the full report in report_md: what you tested and why, trial count, the finalists with every number the schema asks for, rejected ideas with one line each, engine or data concerns.

YOUR TRACK — ${key}
${TRACKS[key]}`

const NUM = { type: ['number', 'null'] }
const SLEEVE = {
  type: 'object',
  properties: {
    sym: { type: 'string' },
    is_n: NUM, is_trades_per_year: NUM, is_win_rate: NUM, is_pf: NUM, is_t: NUM, is_exp_R: NUM, is_bps_per_trade: NUM,
    is_years_pos: { type: ['string', 'null'] }, is_long_R: NUM, is_short_R: NUM, is_avg_hold_h: NUM, is_max_dd_R: NUM,
    stress_pf: NUM, gross_pf: NUM, gross_bps_per_trade: NUM, every_signal_exp_R: NUM, neighbor_median_pf: NUM, null_percentile: NUM,
    is_pass: { type: 'boolean' },
    val_n: NUM, val_pf: NUM, val_exp_R: NUM, val_t: NUM, val_years_pos: { type: ['string', 'null'] },
    val_long_R: NUM, val_short_R: NUM, val_every_signal_exp_R: NUM,
    val_pass: { type: 'boolean' },
    median_stop_2024_25: NUM, min_lot_stop_money: NUM,
  },
  required: ['sym', 'is_n', 'is_pf', 'is_t', 'is_exp_R', 'is_pass', 'val_pass'],
}
const FINALIST = {
  type: 'object',
  properties: {
    name: { type: 'string' },
    rule: { type: 'string', description: 'the exact rule in plain language, precise enough to code an Expert Advisor from it' },
    params_json: { type: 'string' },
    sleeves: { type: 'array', items: SLEEVE },
    basket: { type: ['string', 'null'], description: 'if judged as a basket: its IS and VAL numbers and pass/fail, else null' },
    passes: { type: 'boolean', description: 'true if at least one sleeve (or the basket) passes BOTH the in-sample and the validation criteria' },
    notes: { type: 'string' },
  },
  required: ['name', 'rule', 'params_json', 'sleeves', 'passes', 'notes'],
}
const RESEARCH = {
  type: 'object',
  properties: {
    track: { type: 'string' },
    n_trials: { type: 'integer' },
    verdict: { type: 'string' },
    finalists: { type: 'array', items: FINALIST },
    rejected: { type: 'array', items: { type: 'object', properties: { idea: { type: 'string' }, result: { type: 'string' } }, required: ['idea', 'result'] } },
    engine_concerns: { type: 'string' },
    report_md: { type: 'string' },
  },
  required: ['track', 'n_trials', 'verdict', 'finalists', 'rejected', 'engine_concerns', 'report_md'],
}

const REVIEW_CTX = (key, f) => `CONTEXT. Round 2 of a pre-registered research programme (repo /home/user/gold-orb, branch lab). The user wants a fully automated MT5 robot on an FP Markets Standard account, 1:500 leverage, 1,000 EUR he can lose, hard stop at 500 EUR, several trades a day. Read ${LAB}/PROTOCOL_V2.md and ${LAB}/r2/README.md first. Research was done on in-sample data (before 2022), validated once on 2022-2025; a single-look 2026 holdout comes later (2026 data must NOT be loaded: never use include_holdout=True; do not download data).

FINALIST UNDER REVIEW: track "${key}", name "${f.name}". It claims to pass the in-sample and validation criteria.
Rule: ${f.rule}
Parameters: ${f.params_json}
Reported numbers: ${JSON.stringify(f.sleeves)}${f.basket ? '\nBasket: ' + f.basket : ''}
Researcher's notes: ${f.notes}

Where things are: strategy code ${LAB}/r2/tracks/${key}/strategy.py (make_orders, FINALISTS); toolkit ${LAB}/goldlab/r2.py (r2.load / evaluate / validate / null_test / costs / SPEC), engine ${LAB}/goldlab/sim.py; track outputs ${LAB}/results/r2/${key}/ (trials.jsonl, finalists_preval.json, candidates.json).
RULES: run Python from ${LAB} (sys.path.insert(0, '${LAB}')), single process, under ~2.5 GB, one symbol at a time. Do NOT modify lab/goldlab, lab/r2/tracks or lab/results/r2/${key}. Scratch only under ${LAB}/r2/audit/${f.name}/<your-lens>/. Any validation-period access must go through gl.cut(trades, "val", track="review", label="<lens>:${f.name}:<what>") (logged). Do not git commit. Be adversarial: your job is to find what is wrong or fragile, and to quantify it with runs. Return only the structured output.`

const LENSES = [
  { key: 'lookahead', prompt: `LENS: LOOK-AHEAD AND SIMULATION FIDELITY. Read the code path used by this finalist line by line, and the engine. Hunt for any use of information not available at decision time and any fill better than reality: bar labelling vs t_close, rolling windows that include the unfinished bar, session clocks and DST, how bracket / pending orders are resolved, stops or ATR computed after the decision, time exits over closures, levels on mid vs triggers on bid/ask, data holes, whole-sample statistics, (for learned filters) any training on data that overlaps the predicted period. Write an INDEPENDENT bar-by-bar re-implementation from the plain-language rule and compare trade by trade with the engine result on the in-sample period (match rate, max R difference). Run truncation probes (orders rebuilt on data cut just after random decision times) and timing probes (decision delayed by 1, 5, 30 bars: results should degrade smoothly, not collapse or improve). Hand-check at least 10 random trades against raw M1 rows. Report every issue with severity and its estimated effect on PF.` },
  { key: 'stats', prompt: `LENS: STATISTICAL SKEPTIC. How likely is the edge real rather than selected? Round 1 logged 321 configurations and round 2 several hundred more (count ${LAB}/results/r2/*/trials.jsonl); this finalist is one of few survivors. Use and extend the nulls: r2.null_test (both modes), random side at the rule's own entry times, block bootstrap by week of the in-sample and validation R, family-wise chance that the best of this track's logged trials reaches this t-stat under a zero-edge null (use the track's trials.jsonl; estimate the effective number of independent trials), deflated Sharpe. Check concentration (top trades, top weeks, single years), stability by year and by side, dependence on the market's direction (is it leveraged beta?), agreement between the one-position run and the every-signal run, gross edge erosion over time. Conclude with: your probability that the after-cost edge is positive going forward (with reasoning), the size you would expect if real, the distribution of the 2026 holdout result under "no edge" and under "edge as measured", and which holdout outcomes would be informative.` },
  { key: 'live', prompt: `LENS: LIVE EXECUTION AS AN AUTOMATED EXPERT ADVISOR on FP Markets Standard (MT5, 1:500), 1,000 EUR account. Quantify with the lab engine (write variants in your scratch folder reusing the strategy functions): (1) execution delay: orders sent 1 s to 1 min late, i.e. market entry at the next M1 bar instead of the modelled fill, and stops triggered one bar late; (2) costs: spread x2, stop slippage x2 and x3, a spread spike (x5) in the first minutes of each session and around the daily break; where does the edge die? (3) sizing on this account: with r2.SPEC (lot size, minimum lot, lot step) and stop distances of 2024-2025, what risk per trade in EUR does the minimum lot impose, what fraction of signals can be sized at 1%, 2%, 5% risk on 1,000 EUR, margin needed at the instrument's leverage; (4) operations: trading hours and daily breaks on a retail broker vs the Dukascopy data used (which trades fall in hours where FP Markets may not quote?), weekend gaps, swaps on multi-day holds, MT5 order types needed (no native OCO), stop level / freeze level, what the EA must persist across restarts. List the MQL5 implementation pitfalls for this exact rule and give a concrete EA specification (inputs, bar construction and clocks, order logic, exits, sizing, journal fields).` },
]

const REVIEW = {
  type: 'object',
  properties: {
    lens: { type: 'string' },
    finalist: { type: 'string' },
    verdict: { type: 'string' },
    issues: { type: 'array', items: { type: 'object', properties: {
      severity: { type: 'string', enum: ['critical', 'major', 'minor', 'info'] },
      description: { type: 'string' }, evidence: { type: 'string' }, effect_on_results: { type: 'string' } },
      required: ['severity', 'description', 'evidence', 'effect_on_results'] } },
    measurements: { type: 'array', items: { type: 'object', properties: {
      name: { type: 'string' }, is_value: { type: 'string' }, val_value: { type: 'string' }, note: { type: 'string' } },
      required: ['name', 'is_value', 'val_value', 'note'] } },
    recommendations: { type: 'array', items: { type: 'string' } },
  },
  required: ['lens', 'finalist', 'verdict', 'issues', 'measurements', 'recommendations'],
}
const JUDGE = {
  type: 'object',
  properties: {
    finalist: { type: 'string' },
    decision: { type: 'string', enum: ['GO_TO_PORTFOLIO', 'DISQUALIFY'] },
    reasons: { type: 'array', items: { type: 'string' } },
    corrected_numbers: { type: 'string', description: 'if the reviewers measured different IS / VAL numbers than reported, the corrected ones; else "none"' },
    p_edge_real: { type: 'string' },
    expected_live_expectancy_R: { type: 'string' },
    sleeves_to_keep: { type: 'array', items: { type: 'string' } },
    ea_spec: { type: 'array', items: { type: 'string' } },
    open_risks: { type: 'array', items: { type: 'string' } },
  },
  required: ['finalist', 'decision', 'reasons', 'corrected_numbers', 'p_edge_real', 'expected_live_expectancy_R', 'sleeves_to_keep', 'ea_spec', 'open_risks'],
}

const keys = Array.isArray(args) ? args : [args]

const results = await pipeline(
  keys,
  (key) => agent(COMMON(key), { label: `research:${key}`, phase: 'Research', schema: RESEARCH }),
  (res, key) => {
    if (!res) return { track: key, research: null, reviews: [] }
    const passing = (res.finalists || []).filter(f => f.passes)
    if (!passing.length) return { track: key, research: res, reviews: [] }
    return parallel(passing.map(f => () =>
      parallel(LENSES.map(l => () =>
        agent(`${REVIEW_CTX(key, f)}\n\n${l.prompt}`, { label: `${l.key}:${f.name}`, phase: 'Verify', schema: REVIEW })))
        .then(rv => {
          const ok = rv.filter(Boolean)
          return agent(`You are the judge for finalist "${f.name}" of track "${key}" (round 2, PROTOCOL_V2 in ${LAB}/PROTOCOL_V2.md). Three independent adversarial reviewers (look-ahead / fidelity, statistics, live execution) reported below.
Decide GO_TO_PORTFOLIO or DISQUALIFY. DISQUALIFY if the backtest is invalid (look-ahead, a simulation error that materially flatters results, an implementation impossibility on MT5 / this account), or if after the reviewers' corrections the finalist no longer meets the pre-registered in-sample or validation criteria. Statistical doubt alone is not grounds (the 2026 holdout and the demo are the arbiters) but must be stated as a probability. Say which sleeves (instruments) to keep, give corrected numbers if any, your probability that the edge is real, the expectancy per trade you would plan for live (in R), and a concrete Expert Advisor specification. Be concise and specific.

Rule: ${f.rule}
Parameters: ${f.params_json}
Reported: ${JSON.stringify(f.sleeves)}

REVIEWS:
${JSON.stringify(ok)}`, { label: `judge:${f.name}`, phase: 'Judge', schema: JUDGE })
            .then(j => ({ finalist: f.name, reviews: ok, judge: j }))
        })))
      .then(reviews => ({ track: key, research: res, reviews: reviews.filter(Boolean) }))
  },
)
return results.filter(Boolean)
