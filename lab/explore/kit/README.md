# The research kit of the open search

One tested kit that every run imports, so that testing an idea is: **declare, build a signal table, one call, read
the verdict.** Plain Python 3 + numpy, pandas, pyarrow, scipy. It finds the repository from its own location
(`lab/` is two folders up), never from the current directory.

## Commands (from the repository root)

```
PYTHONDONTWRITEBYTECODE=1 python3 -B lab/explore/kit/test_kit.py            # self-tests, offline, ~2 min: must end "N/N checks passed"
PYTHONDONTWRITEBYTECODE=1 python3 -B lab/explore/kit/test_kit.py --net      # + one month of each source, decoded
PYTHONDONTWRITEBYTECODE=1 python3 -B lab/explore/kit/test_kit.py --net-venues   # + Bitstamp, Bitfinex, Coinbase only
PYTHONDONTWRITEBYTECODE=1 python3 -B lab/explore/kit/test_kit.py --real-bars    # + oil and the 40 shares' prepared bars (lead's machine)
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


## Kit v2.1 (2026-11-18): shares, oil, the slow track, several events at one time

**Read the section "Kit v2.1 fix" at the end first: it replaces several figures below** (share commission 0.03 USD with
the 2 USD minimum MODELLED, share spread level by year, dividends, oil's spread in USD and its contract rolls, the slow
track for ideas declared `slow` only, share bars of fewer than 5 minutes dropped).

Self-test: 138 checks (the 122 of v2, unchanged, plus 16). One existing check was made independent of the live ledger:
P3 (the planted pair) now reads its selection label on a fixed ledger fixture of 2,500 configurations; on the live
LEDGER.md (2,614 on 2026-11-18) the v2 kit itself failed it ('pass, weak against selection', t 5.2), with no change in
the kit. Every other line of the 122 is identical to the v2 kit's output (only timings differ).

### A. New markets with PROVISIONAL costs (`kit/extra_costs.json`, `kit/extra_shape.json`)
- `costs.py` reads `extra_costs.json` beside `lab/r2/fp_costs.json` (never edited) into `costs.EXTRA` (NOT into
  `costs.SPEC`, which stays the 16 FP markets: the noise and speed tests loop over it). `costs.spec(key)` finds both.
  Every entry carries `"provisional": true` and `"source"`; `costs.is_provisional(key)` (a pair with a provisional leg
  is provisional). `judge.verdict` writes `PROVISIONAL COSTS (<markets>)` in the ledger line and `provisional_costs`,
  `costs` in results.json. A pass on provisional costs is re-judged on the broker's own figures before anything else.
- Markets: `oil` (WTI; the lab's data symbol lightcmdusd, FP's XTIUSD) and 40 US shares (keys = lower-case tickers:
  aapl adbe amd amzn avgo ba baba bac c cat crm csco cvx dis fb ge googl gs hd intc jnj jpm ma mcd mrk msft mu nflx
  nke nvda orcl pfe pypl qcom tsla unh v wfc wmt xom).
- Shares, the lab's convention (`_stocks` of fp_costs.json, lab/prep_round3.py, PROTOCOL_V3 section 5): the QUOTED
  bid/ask of the data plus 0.02 USD per share per side. The kit works on BID bars plus a modelled spread, so each share
  has `spread_bps` = its in-sample median quoted spread (bp of mid, from the lab's one-minute bid/ask read with
  ts < 2022) times an hour-of-week shape (`extra_shape.json`), and `commission_per_unit` 0.02 (price units per unit
  per side) added on each side ON TOP of the half spread, inside the quotes before slippage (as the lab's frames add it
  to the quotes), x1.5 in the stress (the lab's stress widens the frame's spread, commission inside), 0 in gross.
  Shape: as `spread_shape.json` (ratio to the 17:00-NY day's median spread, mean per hour of the week) with two
  differences, both measured: the OPEN quote of the FIRST minute of each hourly bar (an order at a bar's open fills at
  that quote; for the 09 bar that is the 09:30 opening quote, 6-16 times the day's median: jpm 16.2, so entering at the
  session's open costs ~40 bp of spread on jpm), and NO clip to [0.7, 6] (the lab's share frames use raw quotes; the
  clip belongs to the forward-looking FP model). With the clip and the minute's close quote (the first pass) the kit's
  cost was 6-42 % below the lab's frames; now:

  | share | lab frame mean cost (bp) | kit mean cost (bp) | kit / lab | by year (2017 ... 2021) |
  |---|---|---|---|---|
  | aapl | 6.70 | 6.92 | 1.03 | 1.14 high in 2017, about 1.0 later |
  | msft | 10.72 | 10.49 | 0.98 | 1.19 (2017), 0.91-0.94 (2018-2019) |
  | tsla | 11.74 | 11.42 | 0.97 | 0.83-1.23 |
  | nvda | 12.57 | 11.76 | 0.94 | 0.81-1.21 |
  | ge | 63.18 | 65.46 | 1.04 | 1.81 (2017) to 0.90 |
  | jpm | 16.03 | 16.68 | 1.04 | 1.56 (2017), 0.90 (2019) |
  | xom | 21.62 | 21.84 | 1.01 | 1.54 (2017), 0.82 (2019) |
  | nflx | 12.69 | 11.89 | 0.94 | 1.29 (2017), 0.91 (2019) |

  500 random in-sample round trips per share (market in at an hourly bar's open, out at the open 24 h later, 1 bp
  slippage both sides, swap excluded), kit cost (`costs.round_trip`) against the lab's frame `lab/data/fp/<t>_m1`
  (quoted bid/ask + 0.02, split-adjusted). The constant level over-charges 2017 and under-charges 2018-2020 by 10-20 %
  (quoted spreads were tighter in 2017); over the whole sample it matches. Builder scripts:
  scratchpad `kit_v21/builder/build_extra.py`, `make_json.py`, `cost_vs_frames.py`.
- Slippage, swaps, lots of shares: the lab's own `STOCK_SPEC` (lab/r2/tracks/stocks/transfer.py): 1 bp market, 2 bp
  stop, swap 7 % long and 3 % short (annual, 360 days, credits ignored), triple swap Friday, 1 share per lot, minimum
  1; leverage 1:5 (fpmarkets.com's share page, 20 % margin, read only as a search snippet). [v2.1 fix: the minimum
  commission of 2 USD per order side is now MODELLED at the stake notional; see the end.]
- Oil: FP's spread 0.05 USD per barrel at 60 USD (8.3 bp; a third-party review gives FP 0.021 and a market average of
  0.04: 0.05 allows a Raw commission), FLAT shape (the lab's one-minute oil data has a constant 0.04 spread: no shape
  can be measured; wider spreads at the 18:00 New York reopen are not modelled), slippage 0.5 / 1.5 bp, swaps 6 % long
  and 4 % short (both a cost, guessed), triple Friday (guessed), 100 barrels per lot, 0.01 minimum, 1:100 (guessed).
- Web (2026-11-18): fpmarkets.com answered HTTP 403 to every fetch; only search-engine snippets of its pages were read
  (MT4/MT5 fees: "2 cents per share, 2 USD minimum per side" for NYSE/NASDAQ; share CFDs: 20 % margin; forex swap
  pages: triple swap on Wednesday). DailyForex (updated 2024-01-09) reads 0.03 USD per share on MT5: the x1.5 stress
  (0.03) covers it. Every figure stays PROVISIONAL until read in the user's MetaTrader (symbol specification: spread,
  commission, swap long/short and its triple day, contract size, minimum volume, margin).

### B. Local-only markets (`data.load_bars('oil' | ticker)`)
- They exist only as prepared hourly BID bars (`~/explore_data/h1`, built by the lead with
  `lead/build_h1_from_lab.py`); there is no download path. `load_bars` reads them through the same lock (rows filtered
  inside the read; after `unlock_val` the years 2022-2025 come from the sibling folder `<dir>_val`; never 2026) and
  raises `FileNotFoundError` with the folders searched when the file is absent.
- Shares have 7 hourly bars a day (09:30-16:00 New York). D20 needs `min_day_bars` bars per 17:00-NY day: 7 for shares
  (a full session; half days do not count), 10 for every other market (cost entry `min_day_bars`, read by `sim.Book`,
  `sim.books`, `sim.pair_book`; a pair takes the smaller of its legs').
- **First-bar label.** A share's first bar is labelled at the full hour (09:00) though trading starts at 09:30: its open
  is the 09:30 price, its end (10:00) is right. The kit treats the bar as opening at its label, i.e. EARLIER than it
  does, which is never optimistic: a signal known between 09:00 and 09:30 enters at the 10:00 bar; a signal known by
  09:00 enters "at the open" = the 09:30 price, with the 09:30 opening spread (expensive). Anything computed from that
  bar is known at 10:00 (`known_at` = label + 1 h, as for every bar); a value taken from its open is the 09:30 price.
  An `('hours', N)` exit counted from that bar holds 30 minutes less than the labels say; the null draws by label clock.
  The trap test shows a signal stamped at the 09:00 label using the bar's close caught by the truncation test.
- **Splits.** The prepared share bars are RAW (not split-adjusted): in sample aapl (2020-08-31, 4:1), tsla
  (2020-08-31, 5:1), nvda (2021-07-20, 4:1) and ge (2021-08-02, 1:8) jump overnight. `load_bars` back-adjusts them with
  the splits listed in the cost entry (taken from the lab's stocks_info.json, dates before 2022 only, each confirmed
  by the bars' overnight ratio; no other split-like move exists in sample), so returns, D20 and stops are continuous;
  `sim.Book` scales the per-unit commission by `data.split_factor` (one adjusted unit before a 4:1 split pays 0.005)
  and refuses raw bars. No column of the bars carries the adjustment (a build could read a coming split from it). Guards:
  an unlisted split-like overnight move (lab rule: within 4 % of a usual ratio) raises `DataGap`; reading a share past
  `splits_checked_to` (2021-12-31) raises `PeriodError`: before a validation look on shares, the lead adds the
  2022-2025 splits to `extra_costs.json`. Limits: an ABSOLUTE price level of a share in a rule depends on later splits
  (use ratios); dividends are not modelled (a CFD long is credited, a short debited, at each ex-date while the bars drop
  by the dividend: the bars understate a long by the dividend and overstate a short; 0 to about 1 % a quarter on these
  shares, which matters on the slow track).

### C. Slow track
`judge.verdict(..., max_hold_tdays=5)` by default (bar `hold<=5d`, unchanged); a run of the slow track (declared
`slow`, CHARTER 'Slow track') passes `max_hold_tdays=40`: the bar becomes `hold<=40d` ("hold <= 40 trading days (slow
track)"), results.json records `max_hold_tdays` and `slow_track`, and the ledger line says `slow track (hold<=40d)`.
[v2.1 fix: only 5 or 40, and 40 only when the idea's declared.json says `"track": "slow"`.] Everything else is unchanged
(swaps every night, null, baskets).

### D. Small fixes
- Several rows known at the same time: `data.external(..., keep='all')` keeps every row (rows known together in their
  input order; default `keep='last'` unchanged); `data.event_table(obs_dates, known=, min_lag=, market=..., ...)`
  returns an event calendar table (one row per event, labelled columns, lag enforced, cut at the period end; give it to
  a truncation test with row_len 0); `data.asof_join(times, series, agg='last' | 'first' | 'sum' | 'mean' | 'max' |
  'min' | 'count')` combines rows known at the same time (default 'last', unchanged).
- `checks.shift_test(..., max_wait_h=)` passes it to both runs and reports each run's stale count.
- The basket bar `max_market_share` reads `n/a (total profit <= 0)` (and fails) instead of inf.


## Kit v2.1 fix (2026-11-18, after the verifier's review V21-1 to V21-8)

Self-test: **148 checks** (the 122 of v2 unchanged, same output; the 16 of v2.1, seven of them amended in code to the
fixed cost model: the share round trip by hand, the simulator on share bars, the split-scaled commission (now at
10 USD, where the per-share rate binds), the pair of two shares, test B's commission figures, test C's slow-track
declaration (`"track": "slow"`, and 7 and 30 now refused) and test C's sizing figures; plus 10 new checks
`test_v21_review_fixes`, all 10 failing on the kit before the fix: `kit_v21/fix/new_tests_on_old_kit.log`). On the
16 FP markets the kit is unchanged (the verifier's p6 comparison: 31 cases identical, round trips identical value by
value, one new key `commission_out`). Scratch of the fix
(scripts and logs): `kit_v21/fix/` (build_rolls.py, spread_levels.py, fetch_divs.py, make_fix_json.py; repro_before/
and repro_after/ = the verifier's scripts on the kit before and after).

- **Oil contract rolls (V21-1).** The lab's oil series (Dukascopy LIGHT.CMD/USD) is the FRONT WTI future, rolled once a
  month by the vendor at an 18:00 New York reopen with a jump = next contract / expiring one (2020-04-19: +35 %; 2015-2016
  contango months +1 to +8 %; the lab's inventory had rated the data unfit for that reason). `extra_costs.json` oil
  `rolls` lists the 108 roll reopens of 2013-2021 (one a month) with their ratio; `data.load_bars('oil')` back-adjusts
  every price before each roll by the ratio measured on the bars (as share splits), so the series is the continuous
  rolled future: no fake gain for a long held across a roll, no breakout or stop on a roll jump. How they were found
  (`kit_v21/fix/work/build_rolls.py`): the NYMEX CL last trading day E (3 business days before the 25th); the data's
  jump sits at the reopen of trading day E-1 (2013-2015-08, 2020-2021) or E (2015-09 to 2019); a neighbouring reopen
  replaced it in 5 months where its gap was >= 30 bp and 3 x larger. After `rolls_checked_to` (the validation years)
  the rule E-1 is applied (`data.roll_times`, `data.cl_expiry`, NYSE holidays by rule): the lead checks those rolls at
  the look. (Superseded by fix 2 below: the in-sample ratios are now LISTED from outside settlements, not measured on
  the bars, and the public table `data.ROLLS_APPLIED` is gone.) `sim.Book` refuses raw oil bars. **Contango** is then in the price path
  (as for a CFD on the future rolled by price adjustment); the swaps (6 % long, 4 % short, both a cost) are a financing
  guess on top. If FP's XTIUSD is a spot CFD whose swap carries the contango, the real swap replaces the guess (read it
  in MT5). Residual: the real night move of a roll reopen (median about 6 bp) is removed with the jump; months where the
  roll was small may have been placed on the wrong night (error of the order of that night's move).
- **The 2 USD minimum commission is modelled (V21-2) and the share commission is 0.03 USD (V21-8).** Per side,
  per unit: `max(0.03 x adj, 2 USD x price / N)` with N = `costs.trade_notional(key)` = 5,000 EUR / 6 positions x
  leverage (1:5) x 1.15 USD/EUR = 4,791.67 USD, the most favourable stake the charter allows; in `costs.round_trip`,
  `costs.pair_round_trip` and `sim.Book` (at each price of the bar), x1.5 in the stress, 0 in gross. Above about
  72 USD a share the minimum binds (4.17 bp per side); a jpm round trip at 150 USD pays 8.3 bp of commission instead of
  2.7 bp with 0.02. `res["sizing"]["by_market"][share]` gives the notional, the commission in bp of a round trip as
  modelled and the extra cost on a 1,000 EUR account (about +33 bp a round trip at 1:5).
- **Oil's spread is 0.05 USD a barrel, constant (V21-3)** (`spread_abs`; x the roll adjustment of the bar): 50 bp at
  10 USD (April 2020), 8.3 bp at 60, 5 bp at 100. The lead's ruling (d) on bp-of-price spreads was about consistency
  with the lab's FP frames; there is no FP oil frame.
- **Share spread level by year (V21-4; two levels per year since fix 2, KF-5).** `spread_bps_by_year`: per New York calendar year, a level in bp such that the
  kit's mean spread (level x the whole-period hour-of-week shape) over every bar-open minute of that year (09:30 for the
  09 bar, hh:00 otherwise) EQUALS the mean quoted spread of the lab's one-minute bid/ask at those minutes (ts < 2022):
  the exact kit / data ratio is 1.000 (0.999-1.001) for every share and year (`kit_v21/fix/work/exact_final.json`;
  before: 0.60-2.11 by year with the single median level). Years not listed (2022 on) use `spread_bps` = max(2021
  level, mean of the yearly levels). The verifier's sampled check (p7_frames.py, 3,000 random trips per share) is in
  `kit_v21/fix/repro_after/p7_frames.log`; its yearly figures scatter around 1 by sampling (about 600 trips a year,
  heavy-tailed by the 09:30 trips).
- **The open of a share session (V21-5): documented, not changed.** An entry or exit at the 09 bar's open pays the
  09:30 first-minute quote (median spread at 09:30 / 09:31 / 09:35: jpm 36 / 5.7 / 4.1 bp, xom 35 / 7.8 / 4.3, msft
  12 / 3.2 / 2.5): a rule that acts at the session's open is judged on the worst minute (a jpm long from the 09 open
  costs about 27 bp net, 8 bp later in the day). The kit cannot enter at 09:31-09:35 (no such bar); an idea that needs
  it enters at the 10:00 bar or says so. On shorts the wide opening spread is also applied to the whole 09 bar's ask
  high (stops on the 09 bar are pessimistic).
- **Slow track only when declared (V21-6).** `judge.verdict(max_hold_tdays=)` accepts 5 or 40 only; 40 needs
  `"track": "slow"` in the idea's declared.json (the template has the field).
- **Short share bars dropped (V21-7).** `load_bars` drops a share bar with fewer than 5 one-minute rows
  (`min_bar_minutes`; the `volume` column counts minutes): the one-minute 13:00 bar of a half day (2 on jpm). Data
  holes (e.g. jpm 2019-03-11 starting at 12:00) stay: **a share signal should be simulated with `max_wait_h`** (e.g. 2)
  so that an entry is not silently delayed by hours or to the next day.
- **Dividends (V21-8).** Each share lists its ex-dates 2017-2021 with dividend / previous close (`dividends`, Yahoo's
  chart events read with period2 = 2021-12-31, as fractions so no later split adjustment is kept;
  `dividends_checked_to`). A SHORT open at an ex-date's first bar (entry before the 09:00-labelled bar of the ex-date,
  exit at or after it) pays the fraction x its fill (`costs.dividends`, inside `swap`, so in the simulator, the
  round trips, the pairs and the null); a long is credited `dividend_credit_long` (0 at the first fix; 0.70 since fix 2,
  KF-4). A trade past `dividends_checked_to` raises `CostError` (list the
  2022-2025 dividends before a validation look on shares, as the splits). Oil's swap guess and leverage (1:100,
  reported only; ESMA caps retail oil at 1:10) stay guesses.

## Kit v2.1 fix 2 (2026-11-18, after the verifier's second review KF-1 to KF-10)

What changed, issue by issue. Every fix has one check in `test_v21_review2_fixes` (test_kit.py) that fails on the kit
before this fix and passes after; the kit before is kept in `kit_v21/fix2/kit_before`, the run of the new checks on it
in `kit_v21/fix2/new_tests_on_old_kit.log` (1 of 9 passes there: KF-6, whose fix is in the test code itself; the old
test code fails V7 in `kit_v21/fix2/run1.log`). Scripts and outputs: `kit_v21/fix2/s/`, the verifier's scripts re-run on
the repaired kit: `kit_v21/fix2/repro_after/` (adapted copies, where a script read a removed name, in `repro_after/s/`).
Nothing changed for the 16 FP markets: the verifier's o19_same.py gives the same 22,682 trades and 96 round trips as
the v2 kit (max difference 0.0; `kit_v21/fix2/s/k_same_cmp.py`).

- **Oil rolls dated and sized from OUTSIDE settlements (KF-1, KF-7).** The first fix measured each ratio on the bars
  (first open / previous close), so a roll after a data hole or on a news night carried the real move (2013-05:
  +306 bp of real rally removed; 2014-07 and 2021-11: the true roll left in; 2015-02: a -360 bp real move removed). Now
  `extra_costs.json oil.rolls` lists, for 2013-01 to 2021-12 (108), the first bar on the new contract and the ratio
  next / front from EIA's daily NYMEX WTI settlements of contract 1 and contract 2 (RCLC1 / RCLC2, rows before 2022):
  Dukascopy's mid at 14:28-14:30 New York (the settlement window) is closer to C1 before its roll and to C2 after it,
  which dates the switch; the ratio is C2 / C1 on the last settlement before the switch, so the real move after the
  settlement and over the night STAYS in the series. 21 of the 108 roll bars moved (2013-05 to 2013-05-19 22:00,
  2014-07 to 2014-07-22 22:00 (-196 bp), 2020-05 to 2020-05-10 22:00 (+562 bp, a week early: the old table had
  -56 bp on 2020-05-17), 2021-11 to 2021-11-15 23:00 (-141 bp), ...); 2015-02 is +130 bp (was -170). Product of the
  ratios 2.492 (2.408 before). Method and every month's case: `kit_v21/fix2/s/k1_build.py` and `k1_build.json`; the
  outside data are kept in `kit/oil_outside.csv` (date, c1, c2 = the public EIA settlements, and duka_on = 1 / 2, the
  contract the vendor's 14:30 price is closer to; the vendor's price itself is not in the repository: the lead keeps it
  beside the prepared bars as `oil_mid_1430.csv`). The self-test checks every listed
  ratio against the outside C2 / C1 (max deviation 2.3 bp, bar 60 bp) and the day states (194 checked, no
  contradiction); `--real-bars` checks the lead's price file against the raw bars (the 14:30 mid lies in the raw 14:00
  bar on 100 % of 2,184 days, and gives the flag duka_on) and that the adjusted reopen move at each roll is the vendor's raw move / the ratio. Adjusted reopen
  moves on roll days (business days 0 and 1 to the expiry, verifier's o4_total.py): median |move| 11.8 and 6.9 bp
  (other days 3.8-6.3); before: 0.4 and 1.0 (the night was erased). The verifier's own hourly CL=F comparison
  (o7_implied.py) now reads: median |error| 20 bp (26 before), mean 34 (42), > 100 bp in 7 months (11); its largest
  remaining 'errors' are its method's: it reads the spread on the days after the roll, the expiry day included
  (2016-01: the expiring February contract settled 656 bp under March on its last day, 383 bp the day of the roll),
  and 2020-04 / 2020-05 where the spread moved by hundreds of bp a day.
  Validation years (after `rolls_checked_to`): the rule E-1 and the ratio measured on the bars as before (it then
  includes that night's real move: a limit), but a rule roll whose reopen comes after a hole longer than the normal
  break (2 h daily, 50 h over a weekend) raises `DataGap`: list that roll (time and C2 / C1 ratio) in
  `extra_costs.json` and move `rolls_checked_to` at the look.
- **Look-ahead through absolute levels is now caught (KF-2).** `checks.truncation_test` re-bases every cut copy of
  back-adjusted bars (attrs `market` = oil or a share with splits, as `data.load_bars` returns them) to the adjustment
  known at the cut (prices / the factor of the rolls and splits at or after the cut), and runs each cut build inside
  `data.asof(cut)` (then `data.price_factor`, `roll_times`, `split_factor` ignore later rolls and splits). On the real
  oil bars (verifier's o8_lookahead.py): the level rule 'close crosses 100' now FAILS (148 failed cuts; it passed with
  0), a rule reading `data.price_factor` fails (104), the ratio rule passes. A share level rule across aapl's 4:1 split
  fails too. `data.ROLLS_APPLIED` and `attrs['rolls_adjusted']` are gone. Limit: a series that lost the bars' attrs
  (a numpy array, a Series built anew) is not re-based: build signals from the bars passed to the test.
- **The roll adjustment no longer depends on what this process loaded (KF-3).** In sample the ratios are the listed
  ones, so `data.price_factor` and `sim.Book` give the same factor after a second load with another start year, on a
  truncated copy, in a pair, or in a fresh process (o9_state.py: raw-USD spread 0.0500 in every year in every case;
  2013 mean 5.12 bp of price). The validation-year ratios that load_bars measures are kept in a private table, merged
  across loads; a Book on bars whose rule roll was not measured in this process raises `DataGap`.
- **Longs are credited 70 % of the dividend (KF-4).** `dividend_credit_long` = 0.70 for every share (a CFD long is
  normally credited the dividend, often net of the 30 % US withholding without a treaty; 0.70 is the pessimistic end:
  read FP's figure in MetaTrader). `judge.verdict` adds `res["dividends"]` (`judge.dividend_report`): per share, the
  long and short trades across ex-dates and the credits, and the main's PF and mean R (net) at credits 0 and 1; the
  ledger line gives 'long dividend credit 0.70 (PF net at credit 0 / 1: a / b)' and says LONG RESULT NEEDS THE DIVIDEND
  CREDIT when the net PF is >= 1 only with it.
- **Two share spread levels per year (KF-5).** `spread_bps_by_year_h09` prices an order at the OPEN of the
  09:00-labelled bar (the 09:30 minute), `spread_bps_by_year` every other bar open and every bar close; each is
  calibrated on its own minutes (`kit_v21/fix2/s/k5_levels.py`). The verifier's o16_spread_all.py on all 40 shares x
  5 years: kit / data 0.99-1.00 for the 09 bar and 1.00-1.01 for the 10-15 bars (before: 0.75-2.16 and 0.51-1.62), no
  share-year off by more than 20 %. jpm 2017: 10-15 bars 1.745 against 1.744 bp (1.254 before). Years not listed:
  `spread_bps_h09` / `spread_bps` = max(2021 level, mean of the yearly levels).
- **V7 with EXPLORE_H1_DIR set (KF-6).** `test_review_v7_budget` unsets EXPLORE_H1_DIR for its prefetch part (it tests
  the download path); the self-test run as prescribed ends N/N.
- **Per-leg exit adjustment (KF-8).** `costs.pair_round_trip(..., adj=, adj_out=)` takes each leg's adjustment at entry
  and exit (a split inside the trade); both default to `data.price_factor`. `costs.round_trip`'s `adj` defaults to
  `data.price_factor` for a market with rolls or splits (1 otherwise). Consequence: a hand check of ge before its 1:8
  reverse split now pays 0.03 USD per REAL share (24 bp a side at about 12 USD), as `sim.Book` always did (the
  `--real-bars` sanity bound is 3-100 bp; it was 3-60).
- **Documentation (KF-9).** The costs.py header and the spread-level notes are corrected. The exit-side minimum
  commission is still charged at the exit price (min x P_exit / N instead of min x P_entry / N): a limit, about 0.4 bp
  on a trade whose price moved 10 % (more for a winner, less for a loser).
- **xom ex-dates (KF-10): rejected, the stored dates are kept.** The bars show the dividend drop on the stored dates:
  the overnight move of xom minus cvx (a close peer without an ex-date in those weeks; `kit_v21/fix2/s/k10_gap.py`,
  `k10_gap.txt`, sd 67 bp) is -148 bp on 2021-11-10 (dividend 133 bp) and +33 bp on 2021-11-09; -303 bp on 2020-11-10
  (dividend 236 bp) and -208 bp on 2020-11-09 (the vaccine-news day). The kit charges the dividend when the price drops.

Amended existing checks (they asserted the behaviour these fixes change): V21-1 (the synthetic vendor bars now jump
at every listed roll of their span, and the expected levels are x the listed ratios after the first bar), V21-8 (a long
is credited 0.70), 'A: oil by hand' (the oil spread is x the bar's roll factor, as `sim.Book` charges back-adjusted
bars; it passed before only because the old table was empty there), the share spread hand helper `_xsp` (the 09 open's
level) and the --real-bars cost bound.

Limits that remain: the validation-year rolls are measured on the bars (night move included) unless listed at the look;
months where C1 and C2 differ by less than 12 bp are dated by Dukascopy's usual reopen (error below 12 bp); the
truncation guard sees only bars that keep their attrs; the exit-side minimum commission at the exit price; the 0.70
dividend credit and every other PROVISIONAL figure are to be read at FP.
