# The research kit of the open search

One tested kit that every run imports, so that testing an idea is: **declare, build a signal table, one call, read
the verdict.** Plain Python 3 + numpy, pandas, pyarrow, scipy. It finds the repository from its own location
(`lab/` is two folders up), never from the current directory.

## Commands (from the repository root)

```
PYTHONDONTWRITEBYTECODE=1 python3 -B lab/explore/kit/test_kit.py            # self-tests, offline, ~2 min: must end "N/N checks passed"
PYTHONDONTWRITEBYTECODE=1 python3 -B lab/explore/kit/test_kit.py --net      # + one month of each source, decoded
PYTHONDONTWRITEBYTECODE=1 python3 -B lab/explore/kit/test_kit.py --net-venues   # + Bitstamp, Bitfinex, Coinbase only
PYTHONDONTWRITEBYTECODE=1 python3 -B lab/explore/kit/data.py prefetch us500 eurusd --budget 1200    # bars into the cache, stops cleanly
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/kit/template/run_template.py   # the whole flow on synthetic data
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/NNN_slug/run.py          # a run's own idea
```

## The flow of a run (see `template/run_template.py`, ~60 lines)

1. Write `ideas/NNN_slug/declared.json` from `template/declared.template.json` (at most 11 configurations), its
   sha256 in `declared.sha256`, commit and push. `run.py` READS that file (never writes it) and calls
   `checks.declared_hash(folder)` first; `judge.verdict` checks the hash again (bar `declared_hash`).
2. Data: `data.load_bars(fp_key)` reads prepared hourly bars when a folder holds them (`EXPLORE_H1_DIR`,
   `~/explore_data/h1`, `lab/explore/prices/h1`: no download; `bars.attrs["source"]` says which) and downloads
   otherwise. Before a download, `data.prefetch([...], budget_s=...)` (108 Dukascopy files per market: ~2 min when the
   server is healthy, much more when it resets; it refuses connections for hours after heavy use) and
   `data.set_deadline(s)` stop cleanly (`BudgetExceeded`: write `en cours`). A month missing inside a market's
   history raises `DataGap` (never test on bars with a hole). Then `data.load_bars(fp_key)`, `data.fred(...)`,
   `data.yahoo_daily(...)`, `data.binance_klines(...)`, `data.binance_funding(...)`, `data.external(...)` for any
   other source, each value indexed by the time it is KNOWN; join with `data.asof_join(times, series)`.
3. `build(data)` returns the WHOLE signal table (filters included): columns `known_at` (UTC), `side` (+1/-1), optional
   `market`. **A value computed from a bar's close is known at that bar's end (open + 1 h), never before.**
   `tr = checks.truncation_test(build, data, cuts, row_len={item: ...})` (a row length for EVERY item) must pass;
   simulate exactly `build(data)` (adding `market` is fine): the verdict compares the two tables' hash. Keep the
   default cut counts (50 at signals' stamps, 50 just after them, 100 random bar ends: about 200 rebuilds); the
   verdict refuses a sparser report (`checks.cuts_ok`).
4. `bk = sim.books({key: bars})`; `main = sim.simulate(sig, bk, exit=..., stop=..., target=...)`; the neighbours the
   same way; `every = sim.simulate(..., mode="every")`; `null = stats.null_test(main, bk, exit=..., stop=...,
   n_draws=2000)` (every draw simulated, as round 6) with the main's OWN exit, stop and target (the verdict checks
   `null["exit_key"] == main.attrs["exit_key"]`); optional `checks.shift_test(...)`.
5. `res = judge.verdict(folder, main, neighbours, every, null, truncation=tr, n_configs=...)` writes `results.json`,
   appends `trials.jsonl`, returns `res["verdict"]` (`fail` / `pass, weak against selection` / `pass`) and
   `res["ledger_line"]`. Then `judge.ledger_add(n_configs, res["ledger_line"])` (after verdict, never before: N_all
   reads the running total). Without a passing truncation report of the main signals, or with a changed declaration,
   or with more than 11 configurations, the verdict is `fail`.
6. A pass (`pass` or `pass, weak against selection`: the deflated Sharpe is a label, not a gate, CHARTER
   'Selection') is only "A VERIFIER": the charter's attack (independent re-implementation) comes next, then
   `val_declared.json` (`frozen_rule`, `bars`, `attack`, `cut: "2025-12-31"`), `data.unlock_val(folder)` (refused
   unless results.json says every in-sample bar passed), the frozen main simulated on 2022-2025 and
   `judge.val_verdict(folder, trades, every)` (the 4 VAL bars, `val_results.json`, once; it also reports the t and
   how many validation looks this search has taken). Sizing on a 1,000-5,000 EUR account is NOT judged:
   `res["sizing"]` gives the minimum-lot margin and loss at the median stop for the lead.

## What each piece guarantees

**`data.py`** – period lock: every reader returns rows strictly before 2022-01-01 00:00 UTC; nothing of 2022+ is
even requested while locked. `unlock_val(idea_dir)` needs `idea_dir/val_declared.json`, appends
`{"time","track":"explore","label":"look:<folder>","period":"val"}` to `lab/results/val_access.log` (append only;
`EXPLORE_VAL_LOG` redirects it) and moves the end to 2026-01-01 exclusive. Nothing dated 2026 or later is ever
requested, returned or cached. Cache `~/explore_data` (`EXPLORE_CACHE`; it may not survive between runs), browser
User-Agent for Dukascopy only (FRED drops connections from a browser string: other hosts get a plain client name),
>= 1 s between Dukascopy requests, 4 tries per file with waits of 2, 4, 8 s, a deadline (`set_deadline`,
`EXPLORE_DEADLINE`) that raises `BudgetExceeded` instead of waiting past it, progress lines with `EXPLORE_PROGRESS=1`,
`prefetch(keys, start_year, budget_s)` market by market (also a CLI).
- `duka_h1(symbol, start_year, side)`: Dukascopy hourly BID/ASK, 24-byte records decoded as `lab/explore/fetch.py`
  (same cache layout), zero-volume bars dropped, a magnitude check catches a wrong point size.
- `daily_bars(h1, "ny17"|"utc")`: day on the 17:00 New York boundary (DST correct; label = the date the day ends) or
  UTC; column `known_at` = end of the day's last bar.
- `binance_klines(symbol, interval, market="spot"|"um")` (taker-buy columns kept; microsecond 2025 files handled),
  `binance_funding(symbol)` (indexed by the funding time).
- `fred(series, known=..., min_lag=None, revised_ok=False)` (fredgraph.csv with cosd/coed): **current vintage,
  revisions included** (ALFRED has the as-published values; not wired). A non-daily series (weekly, monthly: most
  monthly series are dated at the START of their period and published weeks later) is refused unless `min_lag` (the
  declared publication lag, checked on every row) and `revised_ok=True` are given.
- `external(obs_dates, values, known=..., min_lag=...)`: any other source (GDELT, idea 002's news tone, ...), with
  the same check; the observation dates stay in `s.attrs["obs_date"]`. A series indexed by its observation date passes
  the truncation test while leaking (its own index is the lie): the declared lag is the only guard.
- `yahoo_daily(ticker, known=...)` (period2 bounded):
  **no default known-at rule**: give `data.rule_next_bday_utc(13, 1)` (observation + 1 business day 13:00 UTC),
  `data.rule_local_close("16:00")` (US close: 21:00 or 20:00 UTC by DST) or your own function of the dates.
- `asof_join(times, series)`: the last value known at or before each time (equality counts), NaN before.
- `fp_markets()`: FP key -> data symbol (Dukascopy XAUUSD, XAGUSD, USATECHIDXUSD, USA500IDXUSD, USA30IDXUSD,
  DEUIDXEUR, the 8 pairs; Binance BTCUSDT, ETHUSDT), `price_is` ('bid' or 'mid'), hours rule; `fp_hours` removes
  the crypto bars inside FP's closure (Friday 23:55 to Monday 00:00 server = New York + 7 h).
- `crypto_h1(venue, symbol)` and `load_bars(key, venue=...)`: bitcoin and ether from Bitstamp, Bitfinex, Coinbase
  (section 'Crypto venues').

**`costs.py`** – FP Raw costs from `lab/r2/fp_costs.json` (unknown market -> `CostError`); conventions below.

**`sim.py`** – hourly simulator: entry at the open of the first bar opening at or after `known_at + delay_h`; exit
`("hours", N)`, `("clock", "HH:MM", tz)` or `("bdays", N)` or on a condition `("event", events, max_hold)` (section 'Exit on a condition'); mandatory stop `("d20", k)` or `("bps", x)`; optional
target; stop before target in a bar; gaps fill at the open; one position per market and rule (skips counted; among
signals entering at the same bar the earliest `known_at`, then the first row, is kept, never the one that exits first;
`same_bar_skipped` counts them) or every signal; gross / net / stress from the same signals; R = net result / stop distance. 10 configurations x 16
markets x 9 years (24,000 signals each) in about 2 s; a 2,000-draw null in well under a second to a few
seconds (pure numpy: numba is not used, so its absence is harmless). `Book` refuses bars past the period lock. `pair_book` makes a hedged pair one market (section 'Pairs').

**`stats.py`** – PF, t per trade, t on daily sums (entry trading day), years positive (entry year), market split,
`null_test` (same market, same side, same New York clock time, random day, same exit/stop, net costs, >= 2,000
draws, percentile of the real net mean R; every draw simulated by default as round 6's `no_overlap=False`;
`mode="one"` applies the one-position filter with colliding draws ordered at random; the result carries `exit_key`,
the hash of the exit, stop, target and event times it ran), weekly correlation with the sum of the ten, deflated Sharpe.

**`judge.py`** – every bar of CHARTER.md with value and pass/fail (one market; basket with the small-basket
amendment) plus the guards (`truncation_test` bound to the main signals with dense cuts, `declared_hash`, `configs<=11`, and for an event-exit rule `event_truncation_test` bound to the events each market used; the null bar requires the null's `exit_key` to equal the main's), overall
verdict, results.json, trials.jsonl, ledger line; years positive = every year from the first trade to 2021 (a year
without a trade is not positive); minimum-lot sizing reported, not judged; `val_verdict` for the single VAL look;
`ledger_total`, `ledger_add`, `ideas_read`.

**`checks.py`** – `truncation_test` (signals rebuilt on data cut at given dates, exactly at the time stamps of 50
sampled signals, 1-24 bar ends after 50 of them and at 100 random bar ends must equal the full build; a row length
for every data item, else it raises; the report carries the full build's `signals_sha`, on an event build
`events_sha` and `events_by_key`, and its cut counts), `cuts_ok` (the density the verdict requires), `shift_test`
(entries one bar later, reported), `declared_hash`.

## Conventions (and the lab file each one copies)

| Convention | Kit | Lab source |
|---|---|---|
| Spread | FP spread (Raw commission folded) in bp of `spread_ref_price`, applied to the price, x Dukascopy's hour-of-week shape (`spread_shape.json`, 168 numbers per market at the bar's open and at its close, in-sample means of the clipped [0.7, 6] ratio to the trading day's median) | `lab/build_fp_frames.py`, `lab/prep_round3.py`, `lab/COSTS_FP.md` |
| Spread without a reference price (FX, silver) | bp of an approximate late-2025 price (`costs.REF_FALLBACK`), applied to the price: the same forward-looking model as every other market | the lab used bp of the mean price of its data's last 60 days (late 2025); lead's ruling of 2026-11-18 (the kit's first version charged max(absolute, bp): silver 2.3x and the yen pairs 1.2-1.3x the lab's frames) |
| Fills | long buys the ask, sells the bid; market fills `slip_mkt_bps`, stop fills `slip_stop_bps`, targets none | `lab/goldlab/sim.py`, `lab/goldlab/r2.py` |
| Swap | one night per 17:00 New York rollover between the trading days of entry and exit - 1 s (business days), `swap_triple` counts 3; annual rate / 360 x entry price; credits ignored | `lab/goldlab/sim.py` |
| Stress | spread x 1.5 and slippage x 1.5, swaps unchanged; gross = mid, no cost | `lab/COSTS_FP.md`, `lab/goldlab/r2.py` |
| Crypto hours | no fill on bars in FP's closure; a time exit in the closure at the Friday close | `lab/build_fp_frames.py`, `lab/r2/recalc.py`, `lab/goldlab/data.py exit_index` |
| Exit in a closure (any market) | close of the last bar before it | `lab/goldlab/data.py exit_index` |
| Daily sums / years | entry trading day / entry calendar year | `round6 common.py daily_sums`, `goldlab/metrics.py` |
| Correlation | weekly R by exit week (W-SUN, UTC), 418 weeks 2014-2021, zeros kept, Pearson; the ten read with `entry_time < 2022-01-01` in the read, 2022 exits dropped; the bar is signed (<= 0.30: a negative correlation passes) | `lab/r2/tracks/round6/night_fade/correlation.py` |
| Null | same market, side, clock time, random day, same exit; every draw taken | `round6 null.py` (no_overlap=False), PROTOCOL_V3 section 4 |
| DSR | Bailey and Lopez de Prado 2014; V = max(1/(T-1), the configurations' SR variance: a very different neighbour can push the DSR to 0, `dsr_N_all_V_noise` shows the DSR with V = 1/(T-1)); N_all (the label 'pass' / 'pass, weak against selection') and N_main (reported); per-trade R (one market) or daily sums (basket) | CHARTER.md 'Selection' |

**A long-only rule on a rising market passes the PF bars from drift alone** (test_kit: PF 2.1 on a drifting
synthetic market). The guard is the null, which keeps each trade's side and clock: the same drift is in the null
draws, so the rule must beat its own market's drift to pass (that test's percentile: about 30).

## Pairs (kit v2, 2026-11-18)

Lead's ruling: a hedged pair (two legs of equal notional at entry) is ONE market; several pairs form a basket of
pairs, whose basket bars are read across pairs, never across the legs of one hedge.

```
pb = sim.pair_book("eurusd/gbpusd", "eurusd", "gbpusd", bars_eu, bars_gu, kind="ratio")    # P = mid_a / mid_b
px = sim.pair_book("eurusd*usdchf", "eurusd", "usdchf", bars_eu, bars_uc, kind="product")  # P = mid_a x mid_b (EURCHF)
bk = {"eurusd/gbpusd": pb, "eurusd*usdchf": px}        # a basket of 2 pairs; signals carry market = the pair's name
main = sim.simulate(sig, bk, exit=..., stop=("d20", 1.5))   # then null_test, verdict, checks exactly as for any market
```
- **Sides.** `ratio`: long the pair = long a, short b. `product` (a cross from two dollar pairs quoted opposite ways):
  long the pair = long a, long b. The name is registered in `costs` (`costs.spec(name)` works; `costs.SPEC` still
  lists the FP markets only).
- **Bars.** The hours where both legs have a bar (an hour missing in one leg is no pair bar). The pair's path inside
  an hour is unknown, so it is OBSERVED at each bar's open and close only: open = P of the legs' opens, close = P of the
  legs' closes, high/low = max/min of the two. D20 = the pair's own daily range on the 17:00 New York day from those
  observed prices (20 completed days, as for any market).
- **Stops and targets.** Distances in P units (`("d20", k)` of the pair, or `("bps", x)` of P), turned into a
  fraction of the entry bar's mid P. A robot computes the pair's result from both legs and closes both at market when
  it SEES the level crossed, so a level crossed at an observation is filled at that observation (the bar's open if it
  opens beyond, else its close), never at the level: R can be worse than -1 and a target is never a limit fill. Stop:
  both legs' stop slippage (`stop_gap` at an open, `stop` at a close); target: both legs' market slippage. A leg's own
  wick never triggers anything.
- **Costs** (each leg with its own lab convention, added): each leg filled at its own quote (FP spread in bp of its
  reference price x its hour-of-week shape; the close-of-bar shape for exits at a close) with its own slippage; relative
  spread of the pair = spread_a/price_a + spread_b/price_b; swap per night = the rate of the side held on each leg (the
  long leg pays swap_long, the short leg swap_short); the legs must share the triple-swap weekday (else `CostError`).
  `costs.pair_round_trip(...)` gives one trade by hand.
- **Result: the EXACT two-leg result**, per unit of ONE leg's notional: sum over legs of side_leg x (exit_leg /
  fill_leg - 1) - swaps. R = result / (stop distance / mid P). Chosen over the synthetic price's result
  P_exit/P_entry - 1 because it is what two real positions of equal notional earn and lets each leg carry its own
  costs exactly; for a ratio the synthetic result is (r_a - r_b)/(1 + r_b), off by (r_a - r_b) r_b/(1 + r_b): test P3
  measures 0.004 R on average (max 0.06 R) on the planted pair. Each leg's return is taken in its own quote currency
  (as every single-market result in the kit): for legs quoted in different currencies (ger40/us500, a product with
  USDCHF) the conversion of one leg's P&L is a further second-order term, not modelled.
- **Trades** get `entry_px_a/b`, `exit_px_a/b` (net scenario) and `stop_frac`; `entry_px`/`exit_px` are P at the legs'
  fills. `judge.verdict` reports the minimum-lot sizing of BOTH legs (`res["sizing"]["by_market"][pair]["legs"]`:
  lots for equal notional, rounded up to the lot step, margins, loss at the median stop). Correlation, null and
  deflated Sharpe are unchanged (the pair is one market).
- Tests P1-P4: one round trip by hand (both kinds, long and short, across the Wednesday triple night; a Friday
  closure exit at the close spread), stops at the observed close and gap, a target past its level, a missing leg bar,
  D20 by hand, a planted mean-reverting pair found, a basket of two pairs judged across pairs, 96 pure-noise pair rules
  (none passes, gross t ~ N(0,1), null uniform).

## Exit on a condition (kit v2)

```
def build_events(d):                       # a function of the data, like build(d) for the signals
    z = ...                                 # e.g. the pair's z-score at the 20:00 UTC bar's close
    return pd.DataFrame({"known_at": z.index[z.abs() <= 0.5] + pd.Timedelta(hours=1)})   # [, "market": ...]
tre = checks.truncation_test(build_events, data, row_len={...})      # must pass, like the signals' report
ev = build_events(data)
rule = dict(exit=sim.event_exit(ev, ("bdays", 5)), stop=("d20", 1.5))  # = ("event", ev, ("bdays", 5))
main = sim.simulate(sig, bk, **rule); null = stats.null_test(main, bk, n_draws=2000, **rule)
res = judge.verdict(folder, main, neigh, every, null, truncation=tr, event_truncation=tre, n_configs=...)
```
- `known_at` of an event = the time the exit condition is KNOWN to be true (a value from a bar's close: the bar's
  end). Events may be a table (known_at [, market]), a DatetimeIndex, or `{market: DatetimeIndex}`; a market without
  events raises (give an empty index).
- A trade leaves at the open of the first bar opening at or after the first event STRICTLY after its entry bar's open
  (reason `event`, market slippage), or by `max_hold` (`("hours", N)`, `("bdays", N)`) if that comes first. An event
  at or before the entry bar's open is ignored; an event inside the entry bar exits at the next open. An event in a
  closure (weekend, crypto weekend) exits at the reopening bar's open, never at the close before it (that close
  happens before the event is known); a max_hold in a closure keeps the usual close-before rule.
- It works in `sim.outcomes`, so the null re-enters at random days and leaves on the same events.
- **Guard.** `checks.truncation_test` on the event build (a table without `side`) reports `events_sha` and
  `events_by_key` (per market, `*` for a table without market); `trades.attrs["events_used"]` holds, per simulated
  market, the hash of the event times that market's exits used (its own set, else `*`); `judge.verdict` adds the bar
  `event_truncation_test` to every event-exit rule and fails it unless `event_truncation` is a passing, densely cut
  report whose events equal THOSE per market (so a table and `{market: times}` with the same times are the same
  events). Rules without event exits are judged exactly as before.
- **Why the cuts are dense (review V1, 2026-11-18).** A build that DROPS an event (or a signal) when the future is
  favourable, written so that a NaN at the end of a cut keeps it (`e & ~(|z|.shift(-k) < |z| - 0.3)`), leaves every
  kept row unchanged at its own stamp; only a cut within k bars AFTER a dropped row shows it (the row reappears in
  the cut build). The old 8 stamp cuts let such a noise pair rule pass the whole judge (t 5.5, null 100). The
  default cuts (50 stamps, 50 just after, 100 random bar ends) catch it in every seed tried; the judge refuses fewer.
- Tests FIX V1, V2, V4 (`test_fix_*`): the suppression trap on a noise pair (gross t 11) in an event build and in a
  signal build fails the default guard in every seed; a sparse report is refused by the judge; `{market: times}`
  events are bound by the table's report, other times are not; a null run with the max_hold exit, other events or
  another stop fails the null bar, the same rule written differently does not.
- Tests E1-E3: event before / at / inside the entry bar, at a bar open and 1 s later, max_hold, an event in the
  weekend closure, per-market events, a causality invariant on random events (single market and pair); a look-ahead
  trap (an exit event stamped at its bar's open but computed from its close gives t 22 of fake edge; the event
  truncation test catches it); the judge refuses a pass with no, other or failed event reports; the null with event
  exits is calibrated on noise.

## Crypto venues (kit v2)

Lead's ruling (b): bitcoin and ether signals and in-sample trade prices may come from the dollar venues before
Binance's 2017-08 start; the declaration names the venue that prices the trades; costs stay FP's.

```
b = data.load_bars("btcusd", 2013, venue="bitstamp")   # FP-ready: price_is 'mid', FP weekend removed, attrs['venue']
x = data.crypto_h1("bitfinex", "ethusd", start="2016-03")   # raw hourly candles of a venue
```
| venue | symbols | first hourly month | paging (scout/sources.md) |
|---|---|---|---|
| bitstamp | btcusd, ethusd | 2012-11, 2017-08 | `ohlc/<pair>/?step=3600&limit=1000&start=&end=`: the candles ending at `end`, walked back |
| bitfinex | tBTCUSD, tETHUSD | 2013-03, 2016-03 | `candles/trade:1h:<sym>/hist?limit=10000&start=&end=&sort=1`, forward, 2 s between calls |
| coinbase | BTC-USD, ETH-USD | 2015-07, 2016-05 | `products/<id>/candles?granularity=3600&start=&end=`, windows of 300 candles |
- One month per cache file `<cache>/crypto/<venue>/<sym>/1h/YYYY-MM.csv`; a month is requested only if it starts
  before the period end (never 2026), no request names a time at or after it, and rows outside the month and past the
  period end are dropped BEFORE the cache (a server ignoring its bounds cannot put a later row on disk), and never end
  the paging (a Bitfinex reply carrying a later row stopped it after one page). A month
  without candles inside a venue's history raises `DataGap`. An empty reply is asked a second time; a month that still
  has a run of more than 48 h without a candle (`data.VENUE_MAX_HOLE_H`) is NOT cached and raises `DataGap` (review
  V3: one transient empty Coinbase window had cached 420 of 720 hours as complete). A real venue outage (Bitfinex
  2016-08-02 19:00 to 08-10 15:00 UTC after its hack, seen live) is accepted only with `allow_holes=True`
  (`crypto_h1` and `load_bars(..., venue=, allow_holes=True)`): it is cached with `YYYY-MM.holes.json` and listed in
  `attrs["holes"]`; reading that month again without `allow_holes` raises again. Bitfinex and Coinbase omit hours without a trade;
  Bitstamp sends them flat with volume 0 (kept, like Binance's klines). The default (`venue=None`, Binance) is unchanged.
- Tests C1-C4 (fake server: paging, complete hours, column order, lock, a server that ignores bounds, unlock to 2025,
  DataGap, load_bars), FIX V3 (a transient empty window, a persistent one, `allow_holes`, servers past the bounds)
  and `--net-venues` (June 2019 of each venue decoded, median gap to Binance BTCUSDT 0.31-0.34 %).

**`synth.py`** (tests and template only) – hourly bars whose high and low are drawn from the exact law of a Brownian
path's max and min given the bar's move, so stops and targets are a fair game on noise (an earlier version drew
wicks independently of the path: tight stops lost and near targets won on pure noise).

## Limits
- Hourly resolution: stops and targets inside an hour are judged on the bar's high and low with the bar's open
  spread; a crypto bar opening at Friday 23:00 server includes 5 minutes FP cannot trade.
- Swap rates are today's (forward-looking), as in the lab; credits are ignored.
- Binance prices are trade prices (treated as mid), Dukascopy are BID: the kit models FP's spread, not the source's.
- The deflated Sharpe at N_all ~ 2,500 asks for a t near 5 on one market (nine of the ten rules the robot trades
  would read 'weak'): it is a label carried to the ledger, not a gate; a weak pass still gets its attack and its
  single validation look (CHARTER 'Selection', amended 2026-11-18).
- Prepared hourly bars are aggregated from the lab's one-minute BID bars (first, max, min, last per UTC hour); their
  `volume` column is the number of one-minute bars in the hour, not traded volume (an idea that needs Dukascopy's
  volume must download). They equal Dukascopy's hourly candles on complete hours (FX and metals 100 %; index CFDs
  differ on a few percent of hours where the lab's minute file has gaps).
- N_MAIN_BEFORE = 160 is an estimate (range 100-210), see `judge.py`.
- The truncation report is bound to the main configuration's signals only; neighbours built from other signal tables
  are not checked. The truncation test is SAMPLED: a row dropped by a look-ahead of h bars is seen only by a cut in
  the h bar ends after it. With the default ~200 cuts, synthetic suppression traps of 100-1,250 signals and horizons
  of 1-12 bars were caught in 88 of 90 runs (the misses: 335 signals dropped on a 1-bar look-ahead, 2 seeds of 10);
  a build that drops very few rows, with a very short horizon, can still slip through. More cuts
  (`n_random_cuts=`, `n_after_cuts=`, `cuts=`) only add safety. Reports made before 2026-11-18 (8 cuts) are refused. The minimum-lot sizing bar is not judged (figures only, at rough fixed EUR rates).
- FRED values are the current vintage (revised); ALFRED vintages are not wired.
- Pairs: observed only at bar opens and closes (a real robot watching ticks would stop earlier and nearer the level:
  the kit is the conservative side for stops, and gives up target fills inside the hour); legs quoted in different
  currencies: each leg's return in its own quote currency (FX conversion of P&L not modelled); equal notional at the
  minimum lot is only approximate (lots rounded up, reported). The neighbours' events are not checked separately (as
  the neighbours' signals); the null's are (its `exit_key`).
- Event exits: an event at exactly the entry bar's open is ignored (the condition was already true at entry); an
  event in a closure waits for the reopening (a gap risk the max_hold rule does not have).
- Crypto venues: trade prices of the venue (treated as mid), not FP's quotes; venues differ by about 0.3 % from
  Binance in 2019 and more in the early years (Bitfinex traded at a premium in 2017); splicing a venue before 2017-08
  with Binance after it is the run's choice and must be declared. Coinbase and Bitfinex cannot tell a capped reply
  or a lost reply from hours without a trade below 48 h (the --net check counts 718-720 hours of 720 in June 2019);
  a hole longer than 48 h is refused unless allowed. The 48 h floor is a judgement: an honest month of an early,
  thin venue with no trade for two days would raise too (none seen; then check it and pass `allow_holes=True`).

## Lead's additions of 2026-11-18 (after the first batch of ideas)
- **Same-day null for baskets.** When trades of several markets were decided at the same time (same `known_at`),
  `stats.null_test` re-enters the legs of each such group together on ONE random day (`joint="auto"`, mode
  `every`). A basket whose legs move together is one bet per day; drawing each leg on its own day made the null
  too narrow (four identical legs on noise reached the 97.5th percentile about one time in five; with the same-day
  null, 1 time in 60). The result reports `joint_groups`. A table without such groups is judged exactly as before.
- **`judge.verdict` run twice** replaces this declaration's rows in `trials.jsonl` instead of adding them again.
