# Round 2 — toolkit and rules for research tracks

Read `lab/PROTOCOL_V2.md` first (frozen). Round-1 API basics are in `lab/README.md`; the fill rules are in
the docstring of `lab/goldlab/sim.py`.

## Data (research period only: everything stops on 2025-12-31; 2026 is the holdout)

```python
import sys; sys.path.insert(0, "/home/user/gold-orb/lab")
import goldlab as gl
from goldlab import r2

m1 = r2.load("us100")        # FP-cost frame: bid/ask already carry today's FP Markets Standard spread
# symbols: xauusd xagusd us100 us500 us30 ger40 btcusd ethusd      (UTC, M1, cols bo bh bl bc ao ah al ac)
r2.SPEC["us100"]             # spread, slippage, swaps, lot size, min lot, leverage (r2/fp_costs.json)
r2.free()                    # frames are ~330 MB each: load ONE symbol at a time, free when you switch
```
- Indices: ~23 h/day, daily break around 16:15–18:00 New York, closed weekends. Crypto: 24/7 if the data
  has it (check). Session clocks: `gl.local(idx, gl.NY)`, `gl.local(idx, "Europe/Berlin")`, `gl.LDN`.
- `gl.bars(m1, "5min"|"15min"|"1h"|"4h"|"D")` — bars are labelled by START; a bar is known at `t_close`.
  `gl.full_days(m1)` = daily bars without holiday stubs. `gl.atr(bars, n)`.
- `gl.entry_index(m1, t)` = first tradable M1 bar at/after a decision time.
  `gl.exit_index(m1, t)` = bar for a time exit; if `t` is inside a closure it exits on the last bar BEFORE it.

## Strategy contract
`make_orders(m1, **params) -> DataFrame` (columns: see `sim.py`), built ONLY from the frame it receives
(the stress test re-runs it on wider quotes) and strictly causal. Every order needs a stop and a time exit
(`exit_i`, hold <= 5 trading days).

## Evaluation
```python
ev = r2.evaluate(sym, make_orders, params, full=False)   # quick: IS under FP costs
ev = r2.evaluate(sym, make_orders, params)               # full: + cost stress x1.5, gross, every-signal
r2.log_trial(track, sym, params, ev)                     # EVERY configuration you evaluate, no exception
crit = r2.is_criteria(ev, neighbor_median_pf=...)        # PROTOCOL_V2 section 4
nul = r2.null_test(sym, make_orders, params, mode="day") # must be >= 97.5th percentile ("time" for calendar rules)
val = r2.validate(sym, make_orders, params, track, name) # FINALISTS ONLY, once, logged
```
Reports: `ev["is"]` etc. are dicts (n, trades_per_year, win_rate, pf, t_stat, expectancy_R, years_pos,
max_dd_R, long_R, short_R, avg_hold_h, by_year_R ...). `ev["is_bps_per_trade"]` = net result per trade in
basis points of price; `ev["is_gross_bps_per_trade"]` = before any cost.

## Pitfalls learnt in round 1 (all real)
1. **No OCO in the engine.** Two pending orders active together are processed in row order. If your rule
   brackets the price (buy-stop + sell-stop), find the first touch yourself on M1 and emit only that order
   (see `_first_touch` in `lab/tracks/trend/strategy.py`; both touched in the same minute -> assume the
   adverse side).
2. `no_overlap=True` (one position per sleeve) skips an order whose ACTIVATION bar is inside an open trade.
   Path dependence is real: always look at the every-signal run too (it is a criterion).
3. Daily-bar signals: the day closes at 17:00 New York; the reopen minute has a very wide spread. Do not
   enter on the reopen bar; wait (e.g. 30–120 min) or use session times.
4. Indicators must use past data only: no centred windows, no whole-sample quantiles / z-scores.
5. Fills: stop entries fill at the worse of level / open, plus slippage; a stop-loss inside the fill bar is
   assumed hit; target and stop in the same bar -> stop. Limit entries fill on touch with no slippage
   (slightly optimistic: do not build an edge that only exists with limit fills at the exact extreme).
6. `weeks_pos_pct` counts weeks without trades as flat. PF is computed on R (fixed-fraction sizing).
7. Costs change conclusions: report gross and net; an edge smaller than ~2x its cost is fragile.
8. A long-only profit on a market that rose (indices, bitcoin, gold) is not an edge: show long and short
   separately and pass the random-entry null.

## Account constraints (1,000 EUR, FP Markets Standard, 1:500)
Position size is rounded down to the lot step; the minimum lot sets the smallest possible risk.
Report, for each finalist, the median stop distance in price units in 2024–2025 and the money it
represents on the minimum lot (`r2.SPEC[sym]`): above ~30 EUR it cannot be sized properly on this account.

## Housekeeping
Single process, no multiprocessing; keep memory under ~2.5 GB (free frames; resample early). Do not edit
`lab/goldlab/` nor other tracks' folders; do not `git commit`; do not download market data; never load
2026. You may web-search literature. Subagents cannot write `.md` files: return your report in the
structured output; write code, `.json`, `.csv`, `.txt` freely under your own folders.
