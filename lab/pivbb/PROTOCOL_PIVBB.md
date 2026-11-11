# Pivot points + Bollinger bands on gold — study protocol

Pre-registered on 2026-11-11, before any look at data from 2022 on for this study.

## The claim under test (the user's own reading of the market)
On gold, 15-minute chart, with daily "Traditional" pivots (P, R1–R3, S1–S3; also weekly and monthly) and
Bollinger bands (20, 2): price keeps going to the pivots, either to bounce or to break through and run to
the next one; the Bollinger bands show the intensity; with the context (patterns, volatility, time of
day, …) one can tell when to **wait**, when to **go against the move** (bounce) and when to **follow the
acceleration** to the next pivot.

## Data and split
- Gold M1, FP Markets Raw costs: `r2.load("xauusd")`, costs `r2.costs("xauusd")`.
- **In-sample (IS)**: decisions before 2022-01-01. All research, tuning and model fitting happen here.
- **Validation (VAL)**: 2022–2025. Nobody but the lead touches it, once, for the finalists that survive
  verification. 2026 is never loaded.

## What the first pass already found (IS, `pivbb/scout.py`, `pivbb/scout2.py`)
1. No magnet effect: a pivot is touched as often as its mirror image around the day's open
   (P: 70.4 % of days vs 67.6 %; every other level within 1.6 standard errors).
2. At a touch (±0.25 daily ATR, until the end of the trading day) the bounce rate is 47.1 % on real levels
   and 48.1 % on placebo levels: a pivot is not a better place to bounce than a random line. Yesterday's
   high / low and R2 / S2 break through more often than random lines.
3. Bollinger "intensity" does not announce a bounce: level beyond the band with RSI ≥ 70 → bounce 43.9 %
   (placebo 46.0 %). No Bollinger state reaches 50 %.
4. After a touch the next pivot is reached before the previous one about 4 points more often than a
   driftless walk predicts, and just as much on placebo levels: generic intraday momentum.
5. Gradient boosting on the whole context, walk-forward 2017–2021: AUC 0.526 on real levels, 0.507–0.518 on
   placebo levels. Its most confident "break" tenth nets +0.10 R per trade when followed (+0.10, +0.05,
   +0.24, 0.00, −0.02 by year); its most confident "bounce" tenth loses when faded (−0.07 R).

## Shared tools
- `pivbb/events.py`: `Gold()` (M1 mid arrays, trading days, level sets, 15-minute and 1-hour Bollinger /
  RSI / ATR) and `build(g, seed=None)` → one row per touch with context and outcomes; `seed=k` gives
  placebo levels (every set shifted by ±U(0.2, 0.4) × daily ATR).
- `results/pivbb/events_is.parquet`: the IS touches, real (`seed == -1`) and ten placebo seeds.
- Trading rules are judged with the lab engine: `make_orders(m1, **params)` + `r2.evaluate` (FP costs, cost
  stress ×1.5, gross run, every-signal run), `r2.is_criteria`, `r2.null_test`, `r2.log_trial`.

## Criteria for a finalist (all on IS)
PROTOCOL_V2 section 4 unchanged: n ≥ 250, PF ≥ 1.12, t ≥ 2.5, ≥ 60 % of years positive, PF ≥ 1.04 with
costs ×1.5, neighbours' median PF ≥ 1.06, every-signal expectancy > 0, hold ≤ 5 trading days, random-entry
null ≥ 97.5th percentile. For a model-based rule every IS number comes from walk-forward out-of-fold
predictions (train on years < Y, predict Y).
In addition, for this study:
- **Level placebo**: the same rule on ≥ 10 shifted level sets. Report the real PF against the placebo
  distribution. A rule that does as well on placebo levels may still be a finalist, but it is labelled
  "not specific to pivots".
- **Novelty**: correlation of daily results with the two gold rules already in the portfolio
  (`tracks/trend` donch4h_stop, `tracks/orb` orb_asia_2d_buf10). Above 0.5 it is the same trade.
- **Erosion**: gross edge per trade in 2013–2017 vs 2018–2021.
- At most 80 evaluated configurations per track, every one logged; at most 2 finalists per track.

## After the research
Each finalist is attacked by an independent reviewer (look-ahead, statistics and multiple testing,
execution realism). A judge decides which frozen finalists get the single VAL look, run by the lead:
VAL PF ≥ 1.06, expectancy > 0, every-signal expectancy > 0, and the result must not rest on one year
(positive in at least 3 of the 4 years). "Nothing survives" is a valid outcome.
