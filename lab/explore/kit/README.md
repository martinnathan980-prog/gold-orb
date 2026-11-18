# The research kit of the open search

One tested kit that every run imports, so that testing an idea is: **declare, build a signal table, one call, read
the verdict.** Plain Python 3 + numpy, pandas, pyarrow, scipy. It finds the repository from its own location
(`lab/` is two folders up), never from the current directory.

## Commands (from the repository root)

```
PYTHONDONTWRITEBYTECODE=1 python3 -B lab/explore/kit/test_kit.py            # self-tests, offline, ~50 s: must end "N/N checks passed"
PYTHONDONTWRITEBYTECODE=1 python3 -B lab/explore/kit/test_kit.py --net      # + one month of each source, decoded
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
   simulate exactly `build(data)` (adding `market` is fine): the verdict compares the two tables' hash.
4. `bk = sim.books({key: bars})`; `main = sim.simulate(sig, bk, exit=..., stop=..., target=...)`; the neighbours the
   same way; `every = sim.simulate(..., mode="every")`; `null = stats.null_test(main, bk, exit=..., stop=...,
   n_draws=2000)` (every draw simulated, as round 6); optional `checks.shift_test(...)`.
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

**`costs.py`** – FP Raw costs from `lab/r2/fp_costs.json` (unknown market -> `CostError`); conventions below.

**`sim.py`** – hourly simulator: entry at the open of the first bar opening at or after `known_at + delay_h`; exit
`("hours", N)`, `("clock", "HH:MM", tz)` or `("bdays", N)`; mandatory stop `("d20", k)` or `("bps", x)`; optional
target; stop before target in a bar; gaps fill at the open; one position per market and rule (skips counted; among
signals entering at the same bar the earliest `known_at`, then the first row, is kept, never the one that exits first;
`same_bar_skipped` counts them) or every signal; gross / net / stress from the same signals; R = net result / stop distance. 10 configurations x 16
markets x 9 years (24,000 signals each) in about 2 s; a 2,000-draw null in well under a second to a few
seconds (pure numpy: numba is not used, so its absence is harmless). `Book` refuses bars past the period lock.

**`stats.py`** – PF, t per trade, t on daily sums (entry trading day), years positive (entry year), market split,
`null_test` (same market, same side, same New York clock time, random day, same exit/stop, net costs, >= 2,000
draws, percentile of the real net mean R; every draw simulated by default as round 6's `no_overlap=False`;
`mode="one"` applies the one-position filter with colliding draws ordered at random), weekly correlation with the sum of the ten, deflated Sharpe.

**`judge.py`** – every bar of CHARTER.md with value and pass/fail (one market; basket with the small-basket
amendment) plus the guards (`truncation_test` bound to the main signals, `declared_hash`, `configs<=11`), overall
verdict, results.json, trials.jsonl, ledger line; years positive = every year from the first trade to 2021 (a year
without a trade is not positive); minimum-lot sizing reported, not judged; `val_verdict` for the single VAL look;
`ledger_total`, `ledger_add`, `ideas_read`.

**`checks.py`** – `truncation_test` (signals rebuilt on data cut at given dates and exactly at the time stamps of
sampled signals must equal the full build; a row length for every data item, else it raises; the report carries the
full build's `signals_sha`), `shift_test` (entries one bar later, reported), `declared_hash`.

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
  are not checked. The minimum-lot sizing bar is not judged (figures only, at rough fixed EUR rates).
- FRED values are the current vintage (revised); ALFRED vintages are not wired.
