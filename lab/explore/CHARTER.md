# Open search for new trading rules: charter of each run

You are one run of a continuous search that a scheduled task starts every few hours, day and night. Each run tests ONE idea,
writes its result, commits, pushes and stops. Read this whole file first; then LEDGER.md (what was already tried) and
IDEAS.md (the queue).
**Where the prompt that started your run and this charter differ, this charter wins**, in particular on how to choose
the idea: the prompt's short "take the one marked en cours" is replaced by step 2 of "What a run does" below (several
runs may work at the same time; an idea marked `en cours` usually belongs to a run that is still working).

## The goal (the user's, a French retail trader)
- He trades an FP Markets Raw account (EUR, 1:500, hedging; CFDs with the `.r` suffix: FX majors and crosses, US and
  European indices, gold, silver, oil, crypto 24/5) through a MetaTrader 5 robot that runs ten rules (listed below).
- He wants to grow 2,000-5,000 EUR to 10,000 EUR fast, then grow more calmly. Speed comes mostly from risk; what
  research can add is **new rules with a high return per unit of drawdown that do not lose at the same time as the
  ten**. That is the target: independence first, then return per unit of drawdown.
- He asked for everything (2026-11-17: "known and unknown, very different and not different, never stop"): paths
  nobody takes first (unusual data: news tone, positioning, funding, macro, volumes, on-chain, weather, flows;
  unusual clocks, horizons and combinations), but also well-known or published effects, as long as the lab has not
  tested them yet (LEDGER.md and the closed families at the end). Vary the families: do not take an idea of the same
  family as the last ledger line while another family is open.
- Markets that can be judged net of costs today (`lab/r2/fp_costs.json`): xauusd, xagusd, us100, us500, us30, ger40,
  btcusd, ethusd, eurusd, gbpusd, usdjpy, audusd, usdcad, usdchf, nzdusd, eurjpy. An idea that needs another market
  (oil, gas, other crosses ...) is marked `attend les frais FP` in IDEAS.md and left for the lead.
- "Nothing works" is an acceptable and honest result. Never dress up a weak result.

## Hard rules (break none)
1. **Data split.** In sample (IS) = start of data to 2021-12-31: all research, tuning and fitting happen here only.
   Validation (VAL) = 2022-01-01 to 2025-12-31: at most ONE look per frozen finalist, declared first (rule 5).
   Holdout = 2026: never download, read or compute anything on 2026 data. Cut every series at 2021-12-31 when you read
   it for research (cut in the read itself, before any statistic).
2. **The ten rules' trades** (`lab/results/r2/recalc/trades/*.parquet`, in git) hold validation-period rows: read them
   only with the filter `entry_time < 2022-01-01` in the read statement (see
   `lab/r2/tracks/round6/night_fade/correlation.py`, which also gives the weekly-correlation convention).
3. **Never touch** `lab/robot/`, `lab/live_ai/`, `lab/holdout_raw/`, `lab/data/holdout/`, the demo files, or any file of
   earlier rounds. Write only under `lab/explore/`.
4. **Declare before you run.** Before computing any result of an idea, write its folder
   `lab/explore/ideas/<NNN>_<slug>/declared.json` (hypothesis and mechanism, exact rule, markets, data and sources,
   main configuration, at most 11 configurations in total = the main + its neighbours, costs, the bars below), store
   its sha256 in `declared.sha256`, and commit both. Then run. Never change a declaration after a result; a new
   variant is a new idea with a new number.
5. **A VAL look** is allowed only for an idea whose main configuration passed every IS bar AND survived your own attack
   (an independent re-implementation of the signal and the trades in a separate script, from the declaration only,
   giving the same trades). Declare the look first in `val_declared.json` (frozen rule, the bars, cut 2025-12-31),
   append one line to `lab/results/val_access.log` (date, idea, what is read), run it once, record it, and never tune
   after it.
6. **No sub-agents.** Do not use the Agent or Workflow tools. Do not call other AI models (Gemini, ChatGPT ...). You
   work alone, compactly.
7. **Budget per run:** one idea, about 60 minutes of work at most. Heavy computing is fine (CPU is cheap: scan
   thousands of rows or variants in one script), but keep your own steps few. If you cannot finish, write the state in
   the ledger (`en cours`) and stop; the next run continues it or closes it.
8. **No personal data, no secrets, no market data in git** (data files go to the cache below, never committed).
   Commit only code, declarations, small result JSONs and the ledger.
9. Work on branch `lab` only; never open a pull request. Commit messages end with the attribution lines your own
   system instructions give.

## Data you can fetch (checked from this environment on 2026-11-16)
**Notice of 2026-11-18 00:35 UTC: Dukascopy (`datafeed.dukascopy.com`) resets every connection from the cloud since the
evening of 17 November (too many downloads in one day). Until this notice is removed: probe it ONCE
(`PYTHONDONTWRITEBYTECODE=1 python3 -B lab/explore/kit/data.py prefetch eurusd --budget 60`); if it answers `error`,
do not retry and do not start an idea whose traded market needs Dukascopy prices (column Prices = `duka` in
IDEAS.md). Take an idea marked `crypto` (prices from Binance, which works), or close your run with
`EN COURS : serveur de prix indisponible`. The lead runs the `duka` ideas from the lab's own bars meanwhile.**
Cache folder: `~/explore_data` (outside the repository; it may survive between runs, or not).
- **Dukascopy hourly candles (FX, metals, indices, oil, some crypto)**, works:
  `https://datafeed.dukascopy.com/datafeed/<SYMBOL>/<YYYY>/<MM>/BID_candles_hour_1.bi5` (and `ASK_...`), where
  `<MM>` is the month index from 00 (January) to 11; LZMA-compressed records of 24 bytes (big-endian: uint32 seconds
  from the month start, then open, close, low, high as uint32 in points, then float32 volume; check the decoding
  against a known price). Send a browser User-Agent, at most about one request per second, retry 429/503 with growing
  waits. Symbols as Dukascopy names them (EURUSD, XAUUSD, USA500IDXUSD, USATECHIDXUSD, DEUIDXEUR, LIGHTCMDUSD ...).
- **Binance public dumps** (crypto, spot and USD-M futures), works: `https://data.binance.vision/` (klines 1m/1h/1d
  since 2017, futures `fundingRate` monthly files since 2019-09, `premiumIndexKlines`; the `metrics` files with open
  interest start late 2021, so they have no in-sample history). The live Binance and Bybit APIs are blocked here.
- **FRED** (US macro, rates, spreads, uncertainty indices, daily or weekly), works:
  `https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES>`.
- **Yahoo chart API** (daily history of futures, indices, ETFs), works:
  `https://query1.finance.yahoo.com/v8/finance/chart/<TICKER>?period1=<unix>&period2=<unix>&interval=1d`.
- **GDELT 2.0** (world news events and tone since 2015, 15-minute files), works: `https://data.gdeltproject.org/`.
- Blocked or unreachable from here: CFTC (403), Stooq. If a source fails, say so in the ledger and move on.
- More sources, each with tested code and the time its values are known: `lab/explore/scout/sources.md`
  (CFTC positioning through Socrata, FINRA short volume, Treasury auctions, Wikipedia page views, Coinbase, Bitstamp
  and Bitfinex candles, blockchain.info, Coin Metrics, CBOE indices, NOAA and more), with the list of what is blocked.
- `lab/explore/fetch.py` is the first runs' helper; the kit's `data.py` replaces it.

## The kit (`lab/explore/kit`): use it; do not rewrite fetch, backtest or statistics
Built and attacked on 2026-11-17/19 (README.md in the folder; v2.3, after six adversarial reviews: 231 self-tests). It holds the period lock, FP
costs in the lab's conventions, an hourly simulator, hedged pairs, exits on a condition, every bar below, the
random-entry null (same-day for baskets), the correlation with the ten, the deflated Sharpe, the guards against
look-ahead and, since v2.1, US shares and oil with provisional costs and the slow track (paragraphs under "The bars").
1. Check first: `PYTHONDONTWRITEBYTECODE=1 python3 -B lab/explore/kit/test_kit.py` must end `N/N checks passed`
   (about 7 minutes). If it does not, run no idea and write the failure in the ledger.
2. Write `ideas/NNN_slug/declared.json` from `kit/template/declared.template.json` (at most 11 configurations, the
   publication lag of every external series), its sha256 in `declared.sha256`, commit and push. Copy
   `kit/template/run_template.py` to the idea's `run.py`: it READS the declaration and never writes it. Run it with
   `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/NNN_slug/run.py`.
3. Data only through `kit.data`: `load_bars(fp_key)` (prepared hourly bars if a folder holds them, else a download),
   `fred`, `yahoo_daily`, `binance_klines`, `binance_funding`, and `external(obs, values, known=..., min_lag=...)` for
   any other source; join with `asof_join`. **`lab/explore/scout/sources.md` gives, for 29 other sources, tested fetch
   code and WHEN each value is known (and what is blocked): read your source's section before declaring.**
4. `build(data)` returns the WHOLE signal table (`known_at` UTC, `side`, optional `market`); a value computed from a
   bar's close is known at the bar's END. Pass `truncation_test` the bars of `data.load_bars` (or `data.daily_bars` of
   them) and compute EVERY feature (returns, ranges, averages, ranks) INSIDE `build`: for shares and oil the test
   refuses an input that carries the market's mark but is not at its price level, and a feature handed over as a bare
   array is not seen by the guard at all. `checks.truncation_test(build, data, cuts, row_len={every item: ...})` must
   pass; simulate exactly `build(data)`; then the neighbours, `mode="every"`, `stats.null_test(..., n_draws=2000)`,
   `judge.verdict(folder, main, neighbours, every, null, truncation=tr, n_configs=N)` (writes results.json and
   trials.jsonl) and only then `judge.ledger_add(N, res["ledger_line"])`.
5. `pass` and `pass, weak against selection` both mean A VERIFIER: your attack (rule 5), then `val_declared.json`
   (frozen_rule, bars, attack, cut "2025-12-31"), `data.unlock_val(folder)`, the frozen main on 2022-2025 and
   `judge.val_verdict(folder, trades, every)`, once.
6. Sizing is reported, not judged (`res["sizing"]`, for the lead). Never edit the kit inside an idea run. If the kit
   cannot express your rule (limit orders, trailing stops), take another idea, or write the missing piece in the
   idea folder on top of `kit.costs` and `kit.data` and say so in the ledger; a kit bug goes in the ledger for the
   lead.
7. **Hedged pairs:** `bk = {name: sim.pair_book(name, key_a, key_b, bars_a, bars_b, kind='ratio'|'product')}`
   (ratio: P = a/b, long = long a and short b; product: P = a x b, long = long both, for a cross built from two dollar
   pairs quoted opposite ways). Equal notional per leg; the pair is ONE market in simulate, null_test and judge, and a
   basket of pairs is a dict of several pair books. The pair is observed at bar opens and closes only: a stop or
   target is filled at the observation that crosses it, never at the level, so R can be worse than -1. Each leg pays
   its own FP costs; the legs must share the triple-swap weekday.
8. **Exit on a condition:** write `build_events(data)` like `build(data)`: a table with `known_at` = when the
   condition is KNOWN (a value from a bar's close is known at the bar's end), optional `market`. Then
   `tre = checks.truncation_test(build_events, data, row_len={...})`, `rule = dict(exit=sim.event_exit(ev, ('bdays',
   N)), stop=...)`, simulate and null with `**rule`, and `judge.verdict(..., truncation=tr, event_truncation=tre)`.
   A trade leaves at the open after the first event strictly after its entry bar's open, or at max_hold. A weekly
   "exit on Friday 20:00" is an event exit whose events are the Fridays 20:00.
9. **Keep the default cut counts of both truncation tests** (about 200 rebuilds: make `build` fast): the verdict
   refuses sparser reports. It also fails the null bar unless the null ran the main's own exit, stop, target and
   events (pass the same `**rule` to `simulate` and `null_test`). For a basket whose legs are decided at the same
   time the null is the same-day null, automatically.
10. **Crypto before 2017-08:** `data.load_bars('btcusd'|'ethusd', start_year, venue='bitstamp'|'bitfinex'|
   'coinbase')`; declare the venue. A venue month with more than 48 h without a candle raises `DataGap` (fetch
   again later; `allow_holes=True` only for a checked real outage, named in the idea's notes).

## Costs (always on, always FP Markets Raw)
`lab/r2/fp_costs.json` (spread in price units at a reference price, Raw commission folded in, slippage per side for
market and stop orders, swaps as annual % of notional with the triple day; crypto is 24/5 at FP) and
`lab/COSTS_FP.md`. Report the gross result, the net result and the net result with costs x1.5. A rule that cannot
be sized on a 1,000-5,000 EUR account (minimum lot, margin at 1:500, at most 6 open positions for the whole robot)
does not pass.

## The bars (PROTOCOL_V3 section 4; read on the main configuration only)
- One market: n >= 250 trades, PF >= 1.12, t >= 2.5, >= 60 % of years positive, PF >= 1.04 with costs x1.5,
  neighbours' median PF >= 1.06, every-signal expectancy > 0, hold <= 5 trading days, random-entry null >= 97.5th
  percentile. A slower rule with fewer trades may pool several markets as a **basket** (one rule, same parameters):
  t on daily sums of R >= 2.5, pooled PF >= 1.12 and >= 1.04 at costs x1.5, >= 60 % of years positive, >= 65 % of
  markets positive, no market above 25 % of the profit, null on pooled trades.
  **Small baskets** (amendment of 2026-11-17, written before any result of this search, for ideas declared after it):
  with 2 to 4 markets the 25 % bar cannot be met by construction, so it becomes: no market above 50 % of the profit
  (4 markets), 60 % (3 markets), 75 % (2 markets); every other basket bar is unchanged.
- **Power first:** before declaring, count the signals of the main configuration from the signal data alone (no
  price, no return): if n >= 250 on one market, or the basket bars, cannot be reached in sample, close the idea as
  `donnees insuffisantes` without running it.
- **Independence:** weekly correlation of the main configuration's R with the sum of the ten <= 0.30 (2014-2021);
  the bar is signed: a negative correlation passes (a rule that wins when the ten lose is what the user needs).
- **Selection:** the search tests many ideas, so luck finds winners. Log every configuration in the idea's
  `trials.jsonl`, keep the running total in LEDGER.md, and report the deflated Sharpe ratio (Bailey and Lopez de
  Prado) of the main configuration given the total number of configurations ever tested (about 2,500 before this
  search, plus every configuration of this search). A pass with a deflated probability below 0.95 is labelled
  "pass, weak against selection".
  **Amendment of 2026-11-18 (written by the lead before any idea of this search passed in sample; one idea had been
  judged, 005, failed on t 0.82): the label is carried to the ledger and to the final message, but it is not a gate.
  A weak pass gets its attack and its single VAL look like a pass.** Reason: measured in sample on the ten rules the
  robot trades, nine of the ten have a deflated probability below 0.95 under the lab's 2,500 configurations (their t
  is 2.7 to 3.9; only one reaches 4.8), so as a gate it would refuse every edge of the size this lab has ever found.
  What controls luck instead: the main configuration is declared and hashed before any result; the in-sample bars
  (t >= 2.5 and the null >= 97.5th percentile: none of 200 pure-noise rules passes them with costs, about 1 in 400
  without, in the kit's tests); the independent attack; the single look at four untouched years; the lead's own
  verification, with the number of VAL looks this search has taken in view; the 2026 holdout, which stays closed.
- VAL (rule 5): PF >= 1.06, expectancy > 0, every-signal expectancy > 0, positive in at least 3 of the 4 years.
- **Slow track (amendment of 2026-11-18, written before any slow idea was run):** an idea whose declared.json says
  `"track": "slow"` (set at declaration, before any result) may hold up to 40 trading days instead of 5:
  `judge.verdict(..., max_hold_tdays=40)`. The kit accepts only 5 or 40, and refuses 40 for an idea not declared slow.
  Every other bar is unchanged; swaps are charged every night, share dividends are charged, and the null and the
  basket bars apply. Reason: the twelve ideas run so far, all held a few days, show no gross edge, and the best
  documented premium this lab never tested (trend following over weeks) lives at slower holds. The user asked on
  2026-11-18 for a change of direction if the ideas were poor.
- **New markets and provisional costs (2026-11-18, kit v2.1):** US share CFDs and oil are judged with the costs of
  `kit/extra_costs.json`, marked PROVISIONAL (the broker's own figures are not read yet; the ledger line and
  results.json say so). A pass on provisional costs is reported as such and re-judged on the real costs, read in the
  user's MetaTrader, before anything else.
- **US share CFDs (kit v2.1):** `data.load_bars(<ticker in lower case>)` for the 40 shares of `kit/extra_costs.json`.
  - Data: prepared hourly bars only (2017-2021), 7 bars a day from 09:30 to 16:00 New York. The first bar is labelled
    09:00 but opens at 09:30: its open is the 09:30 price, and anything taken from it is known at 10:00. The kit
    split-adjusts the bars and drops bars of fewer than 5 minutes (the closing minute of a half day).
  - Prices: use ratios of prices, never absolute levels (the levels are adjusted for later splits). The truncation
    test catches a rule on levels only when the signals are built from the bars passed to it (their attrs kept).
  - Costs, PROVISIONAL: the data's quoted spread, calibrated by year (one level for an order at the 09:30 open, one
    for the other opens, three for exits at a bar's close: the 15:59 close is wider), times its hour-of-week shape; a commission of max(0.03 USD a share, 2 USD an order) at a
    stake of 5,000 EUR / 6 positions at 1:5 (above about 72 USD a share the minimum binds: 4.2 bp a side; a 1,000 EUR
    account pays about 33 bp more a round trip, reported in `res["sizing"]`); swaps 7 % long and 3 % short a year.
  - Dividends, PROVISIONAL: a short open at an ex-date's 09:30 open pays the dividend; a long is credited 70 % of it
    (the pessimistic end of what brokers credit; the bars drop by the whole dividend). `results.json["dividends"]`
    gives the result at credits 0 and 1; a verdict marked `LONG RESULT NEEDS THE DIVIDEND CREDIT` stays doubtful
    until FP's figure is read.
  - The session's open is expensive: an order at the 09 bar's open pays the 09:30 first-minute quote, 10 to 16 times
    the day's median spread. A rule that acts at the session's open is judged on that cost; a rule that can wait
    enters at the bar labelled 10:00.
  - Simulate share signals with `max_wait_h` (for example 2), so that a hole in the data cannot delay an entry by
    hours or to the next day.
  - A validation look on shares needs the lead to list the 2022-2025 splits and dividends first; the kit refuses to
    read past the ones it holds.
- **Oil (kit v2.1):** `data.load_bars('oil')` is the front WTI future (the lab's Dukascopy LIGHT.CMD/USD series).
  - The kit back-adjusts it for its monthly contract roll: 108 rolls for 2013-2021, each dated where the series
    switches from the front contract's settlement to the next one's and sized as next / front on the last settlement
    before the switch (public EIA settlements, `kit/oil_outside.csv`), so a trade never books a roll jump, the real
    move of the roll night stays, and the futures carry (contango) is in the adjusted price. A run never adjusts oil
    by hand. Use ratios, never absolute levels. In the validation years the expiry rule dates the rolls; a roll that
    reopens after a hole in the data raises `DataGap` and the lead lists it before the look.
  - Costs, PROVISIONAL: spread 0.05 USD a barrel (constant in USD); swaps 6 % long and 4 % short a year, both a cost,
    guessed. FP's own oil contract (XTIUSD) is a spot contract: a pass is also re-checked on the broker's prices.
- **Several events at one time:** an event calendar where several rows are known at the same time (several companies
  reporting the same evening, several releases at 08:30 New York) is built with `data.event_table(obs_dates,
  known=..., min_lag=..., market=..., <columns>)` or `data.external(..., keep='all')`: one row per event, the
  publication lag enforced on every row, cut at the period end. Rows known together are combined with
  `data.asof_join(times, series, agg='sum' | 'mean' | 'count' | ...)`. The table goes to the truncation test with
  `row_len=0`. Never let the default (`keep='last'`, one row per known-at time) silently drop events.
- **Company earnings (2026-11-18):** the calendar of `scout/earnings_edgar.py` (documented in the last section of
  `scout/sources.md`; 841 quarterly results of the 40 shares, 2016-10 to 2021-12, from SEC EDGAR; an independent
  verifier found no row stamped earlier than its release). A release is known at the time EDGAR accepted the filing
  (safe: never early, sometimes late); the reaction session is the first regular session (09:30-16:00 New York) that
  STARTS after that time. A value taken from the reaction is known at the end of the bar that carries it. A rule
  that trades the reaction day loads `calendar(drop_late=True)` (it drops the 25 rows known to be a session late:
  Alibaba, and Citigroup's filings made during the session); never move an event earlier because of a price move.
- **US shares on daily bars (kit v2.2; direction 3, ideas 059 to 062):**
  - Load: `data.load_bars(key)` for the keys of `kit/universe_us.csv` (382 shares with sector and in_universe_from;
    the lab's 40 are not in it). One bar a session: the index is the session's open (09:30 New York); the column
    `known_at` is its close (16:00, 13:00 on a half day). No bar before in_universe_from (so no D20 in a share's
    first 20 sessions) and none after 2021. For the whole universe at once: `data.long_bars({key: bars})`. Sessions
    and half days come from `data.us_sessions()`; never hard-code a holiday list. Never pass these bars to
    `data.daily_bars` (it refuses them).
  - Prices: Yahoo's levels carry every split up to today and are not adjusted for dividends. Use ratios only
    (returns, range / close, dollar volume). A rule on a price level, on levels compared ACROSS shares (a price rank,
    the cheapest decile) or on a raw share count fails the truncation test. Measure moves with
    `data.session_moves(bars)`: `ret_total` adds the ex-date's dividend back; a session flagged `action` (an ex-date
    of 2 % or more, a split or spin-off record) is a corporate action, not news (no signal on it unless the
    declaration says otherwise).
  - Stamp: a value computed from a session's close is known at that bar's `known_at` (or later), never at its index.
    The 8-K events (`scout/events_edgar.py`, `scout/sources.md` section 31: `event_session` is the first session that
    closes after the filing was accepted) go through `data.event_table(..., min_lag=...)` and take row_len 0.
  - Truncation test: compute every feature INSIDE build from the bars passed to it; give the bars
    `row_len='known_at'` (a shorter row length is refused). `cols` holds only known_at, side and integer or label
    columns. On the whole universe the test takes a few minutes.
  - Simulate: entry is the next session's open; pass `max_wait_h=96`. Exit with `('session_close', N)` (a close) or
    `('sessions', N)` (the open N sessions later, holidays skipped; not `('bdays', N)`); `('hours', N)` and clock
    exits are refused. Stop `('d20', k)`: D20 is the mean high - low of the 20 sessions completed before the entry.
  - Costs, PROVISIONAL and heavy on purpose: spread 56 bp of the price for an order at the session's open (the
    first-minute cost measured on the lab's 40 shares, at its 75th percentile), 12 bp at a close; commission
    max(0.03 USD a share, 2 USD an order) at 4,791.67 USD a trade, computed on Yahoo's price levels (pessimistic for
    shares that split after 2021: run `checks.min_commission_test` and pass it to `judge.verdict(min_commission=...)`;
    reported, not judged); slippage 1 bp (2 on a stop); swaps 7 % long and 3 % short a year; dividends (a short
    pays, a long is credited 70 %). One night, open to open, costs about 70 bp.
  - Declare `"groups": "sector"` in declared.json for a basket of more than 40 markets (next paragraph);
    `judge.verdict(..., groups=...)` raises without it. Survivors only (today's index list: 183 companies that left
    the index since 2017 are missing): said with every result, long and short sides reported apart.
  - A validation look on these shares needs the lead to prepare the 2022-2025 bars, splits, dividends and filings
    first; the kit refuses to read past what it holds.
- **Rules on one side, signals bunched in time (kit v2.3, amendment of 2026-11-19, after idea 063, written before
  any validation look of this search):** the judged null draws its random days in the whole sample, so a rule that
  trades one side only and whose signals fall mostly in a few years is credited with the drift of those years (idea
  063, long bitcoin: 91st percentile of the judged null, 43rd against days of the same years; idea 042, the same rule
  short: 2nd and 58th). Every run now also computes the same-year null, `stats.null_test(..., within="year")`, and
  gives it to the judge as `null_year=`: INFORMATION, never a bar, written in the ledger line. Its limit: it removes
  the drift of whole years only; drift and signals bunched inside a part of a year still read as timing, so a high
  value is not proof of timing (count the signals by quarter).
  **The validation look of a one-sided rule carries one bar more, whatever its in-sample nulls say.** One-sided = at
  least 80 % of the main's trades on one side. Its `val_declared.json` holds `"extra_null_bar": 90`, and
  `judge.val_verdict(..., null_year=...)` judges it: the same-year null of the validation trades (2,000 draws, the
  frozen rule) at or above the 90th percentile. The kit enforces it: `data.unlock_val` keeps the period locked for
  a one-sided main without that key, and a value that does not bind is an error. A long rule on a market that rose in 2022-2025 can meet the four
  validation bars on that rise alone; this bar asks that its days beat other days of the same years. A pass in
  sample stays a pass: this only says what the validation must show. The lead may declare the same bar for any
  other rule (it is written in the idea's row of IDEAS.md before the run).
- **Baskets of many markets (amendment of 2026-11-18, written before any run on such a basket):** for a basket of
  MORE THAN 40 markets (several hundred shares with a few trades each) the two basket bars are read on GROUPS of
  markets fixed in the declaration before any result (at least 8 groups, for example sectors): at least 65 % of the
  groups positive, no group above 25 % of the profit. A market with two trades is positive or negative by chance, so
  the bars say nothing market by market. Every other bar is unchanged (`lab/explore/lead/DIRECTION3.md`).
- **Rulings of the lead (2026-11-18):** (a) a hedged pair (two legs of equal notional) is ONE synthetic market, and
  several pairs form a basket of pairs: the basket bars are read across pairs, never across the two legs of a hedge
  (the scout's ideas 1, 3 and 4 are run as ONE basket of seven pairs, idea 015; not both ways);
  (b) crypto signals and in-sample trade prices may come from the dollar venues Bitstamp, Bitfinex or Coinbase before
  Binance's 2017-08 start (scout/sources.md): the declaration names the venue that prices the trades, costs stay FP's;
  (c) a source that exists only as one file of its whole history may be read with a streamed download stopped at the
  first row past 2021 (a read-ahead of a few kilobytes, discarded unparsed, is accepted); (d) costs of the FX pairs
  and silver follow the lab's forward-looking model (today's cost in basis points of price), as for every market.

## What a run does
1. The repository is checked out on branch `lab`; `git pull --ff-only`, then check you can push
   (`git push --dry-run origin HEAD:lab`): if not, stop at once and say so. Read this file, LEDGER.md, IDEAS.md.
   Push your declaration as soon as it is committed, so that nothing is lost if the run stops.
2. Choose the idea: one marked `en cours` whose run stopped (its claim time, or, if none is written, the last
   commit under its folder, `git log -1 --format=%cI -- lab/explore/ideas/<NNN>_*`, is more than 3 hours old), else
   the first `ouverte` one in IDEAS.md that is not of the last ledger line's family, or a better new idea of your own
   (add it to IDEAS.md first, with its mechanism and why it is worth a run). Check in LEDGER.md and the closed
   families below that it was not tried. Never take an idea marked `reservee (lead)`: the lead runs it. **Claim it at once:** set its status to `en cours (AAAA-MM-JJ HH:MM UTC)`
   in IDEAS.md, commit and push; if the push is refused, `git pull --rebase origin lab` and check that no other run
   claimed it meanwhile (else choose another). Two runs may overlap: never work on an idea another run holds.
3. Check that its data exists and covers enough in-sample history (at least 4 years; say how many). If not, close it
   as `donnees insuffisantes` and take the next one (at most two such skips per run).
4. Declare (rule 4), fetch, build, run the IS test, the neighbours, costs x1.5, the null, the correlation, the
   deflated Sharpe, all with the kit (section "The kit"). Keep code in the idea folder (`run.py` and helpers) so the
   result can be re-run.
5. If it passes: attack it (rule 5), then, if it survives, the single VAL look.
6. Write `results.json` in the idea folder and one line in LEDGER.md (number, date, idea, markets, data, configurations,
   verdict, the key figures: n, PF net, t, PF at x1.5, years positive, null percentile, correlation, deflated
   probability). Mark the idea in IDEAS.md (`fermee`, `en cours` or `trouvee`).
7. Commit and push (`git pull --rebase origin lab` first if the push is refused; retry a few times).
8. Final message, in French, first line exactly one of:
   - `RIEN DE NOTABLE : idee NNN (<titre>) echoue : <la raison en une phrase>`
   - `EN COURS : idee NNN (<titre>) : <ou on en est>`
   - `TROUVE : idee NNN (<titre>) passe en echantillon et a la validation : <chiffres>`
   - `A VERIFIER : idee NNN (<titre>) passe en echantillon, validation a faire : <chiffres>`
   (a weak pass is also `A VERIFIER` or `TROUVE`, with the words `faible face a la selection` in the next line)
   Then at most three short lines. No jargon in the first line.

## Direction 3 (2026-11-18, evening)
The batch of 18 November (ideas 051 to 058) found nothing, but showed for the first time a gross edge: the drift
after LARGE results-day moves on the 40 shares (a reading made after the verdict: a hypothesis). It is tested on
other shares: a broad universe of US shares on daily bars, with every 8-K as an event calendar. Plan, universe, costs
and the briefs of ideas 059 to 062: `lab/explore/lead/DIRECTION3.md`.

## Direction 2 (2026-11-18)
After 17 ideas without a find, the lead changed the direction of the search: company earnings on US share CFDs, slow
rules (the slow track above), and the families that work on new markets. The plan and the full brief of each new
idea are in `lab/explore/lead/DIRECTION2.md`. The daily batch of 8 ideas is run by the lead
(`lab/explore/LEAD_ROUTINE.md`); the scheduled runs are paused meanwhile.

## The ten rules of the robot (do not redo, and be independent of them)
noise30 and ocm4 (us100 opening momentum); brk72_24h_wd and F1_brk_ridge_filter (BTC and ETH channel breakouts);
nq_btc_follow (BTC following the Nasdaq); GOLD_FRI_PM (gold Friday afternoon); donch4h_stop (gold 4-hour channel);
orb_asia_2d_buf10 (gold Asian-range breakout).

## Families the lab already closed (do not redo; details in LEDGER.md and lab/PROTOCOL*.md)
Gold intraday (twice), US indices intraday and opening rules, DAX, crypto short horizon (118 configurations), macro
event days, lead-lag between markets, night and calendar windows, a learned filter (ML), pivots and Bollinger bands,
micro-scale prediction, a language model as discretionary trader, US single shares with the opening rules, FX majors
(round 3), daily dip-buying on indices, profit targets and partial exits, stakes by conviction or clock, pyramiding,
selling volatility insurance, month-end FX fix with the S&P sign, Tokyo fixing days, "green weeks", index relative
strength intraday, FX weekend overreaction fade, DAX noise30 on the Xetra clock, FOMC even/odd weeks, leveraged-ETF
close pair, gold reopen drift (round 5), night mean reversion on FX crosses (round 6: gross edge real but costs twice
the edge). Lesson of every round: short-horizon edges usually die on costs; slower and better-informed signals are
the open ground.
