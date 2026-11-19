# Direction 4: a scan of price rules on the round-the-clock markets (pre-registration)

Written by the lead on 2026-11-19 (evening), BEFORE any code of the scan exists and before any result. Nothing below may
change after the first run on real bars; a later scan is a new document.

## 1. Why
The user's instruction of 2026-11-19: no more shares and no more exotic data; search on the markets that trade almost
round the clock and move all the time (gold, euro-dollar, oil ...), with **sudden shocks, existing indicators, new
indicators and mixes of indicators**. Budget: about 10 % of the weekly credit a day at most.

An inventory of the lab's archives (three readers, 2026-11-19, `lead/batch_archive_map.js`) says what that ground holds:
- **Already searched, do not expect more:** gold in depth (about 500 configurations: session and Asian-range breakouts,
  channels, RSI(2), Bollinger fades, pivots, round numbers, pivot + Bollinger on 15 minutes, clock effects), the US
  indices and the DAX intraday (about 300), bitcoin and ether breakouts (about 180), four frozen trend rules and the
  clock/fix effects on 8 currency pairs. What survived became the robot's ten rules: slow breakouts on gold and
  crypto, opening momentum on the Nasdaq. Lessons: nothing under one hour survives costs; mean reversion lost at
  every scale on gold and indices; a gross edge under twice its cost does not survive.
- **Never tested (searched for and not found):** MACD, moving-average crosses, stochastics, CCI, Keltner, Ichimoku,
  SuperTrend, Parabolic SAR, ADX as a trend gate, RSI other than RSI(2), Bollinger rules outside gold, squeeze /
  inside-bar / narrow-range breakouts as rules, candle patterns in general, **any rule on a sudden large move of the
  traded market itself**, any mix of two indicators, home-made indicators; and almost nothing at all on **oil** and
  **silver**, and only generic transfers on the currencies.

So the user's ground is largely untested. It is also wide: testing it by hand, eight ideas a day, would take months
and pay an agent for every rule. A scan tests it in one pass at the price of computing time, if its statistics are
honest. This document fixes those statistics.

## 2. What is scanned
**Markets (15):** xauusd, xagusd, oil; eurusd, gbpusd, usdjpy, audusd, usdcad, usdchf, nzdusd, eurjpy; us100, us500,
us30, ger40. Hourly bars of the kit (`data.load_bars`, in sample, FP costs; oil with its provisional costs). Bitcoin
and ether are left out of this first scan (short history, five rules of the robot already, one-sided drift).

**Frames:** H1 (the bars), H4 and D1 built from them inside the scan (4-hour blocks and days that start at 17:00 New
York). A value of an H4 or D1 bar is known at the end of its last hourly bar. Every indicator is causal: its value at
a bar uses that bar and earlier bars only. A signal known at a bar's end enters at the open of the next hourly bar.

**Signals (39).** Each gives +1 (buy) or -1 (sell) at the close of a bar of its frame, on the bar where the condition
becomes true:

| id | family | definition |
|---|---|---|
| T01-T03 | trend | EMA(fast) crosses EMA(slow): 10/30, 20/50, 50/200 |
| T04, T05 | trend | MACD(12,26,9): line crosses its signal line; line crosses zero |
| T06, T07 | trend | close above the highest high (below the lowest low) of the previous 20; 55 bars |
| T08 | trend | SuperTrend(ATR 10, x3) flips |
| T09 | trend | Ichimoku(9,26,52): close leaves the cloud upward / downward |
| T10 | trend | close outside the Keltner channel EMA20 +/- 2 ATR20: follow |
| T11 | trend | close outside Bollinger(20, 2): follow |
| T12 | trend | +DI(14) crosses -DI(14) while ADX(14) >= 25 |
| T13 | trend | Parabolic SAR(0.02, 0.2) flips |
| R01-R03 | reversal | RSI(2) < 10 / > 90; RSI(7) < 20 / > 80; RSI(14) < 30 / > 70: buy / sell |
| R04 | reversal | Stochastic(14,3,3): %K crosses above %D under 20 (buy); below %D over 80 (sell) |
| R05 | reversal | close outside Bollinger(20, 2): fade |
| R06 | reversal | CCI(20) comes back above -100 (buy) / back below +100 (sell) |
| R07 | reversal | three closes down in a row (buy) / up in a row (sell) |
| R08 | reversal | internal bar strength (close - low) / (high - low) < 0.2 (buy) / > 0.8 (sell); H4 and D1 only |
| K01, K02 | shock | bar return beyond k standard deviations of the previous 500 bar returns, k = 3; 4: follow it |
| K03, K04 | shock | the same, k = 3; 4: fade it |
| K05, K06 | shock | bar range above 2.5 x ATR(20): follow the bar's direction (close - open); fade it |
| K07 | shock | after a shock bar (k = 3): the first of the next 6 bars that retraces at least 38.2 % of the shock bar and closes back beyond that level: enter in the shock's direction |
| C01 | compression | Bollinger(20, 2) width was the lowest of 120 bars at one of the previous 6 bars, and the close is outside the band: follow |
| C02 | compression | the previous bar had the narrowest range of 7; close beyond that bar's high / low: follow |
| C03 | compression | the previous bar is inside its predecessor; close beyond the predecessor's high / low: follow |
| P01 | candle | engulfing bar after a 10-bar low (buy) / high (sell) |
| P02 | candle | pin bar (wick at least twice the body and 60 % of the range) at a 10-bar low (buy) / high (sell) |
| L01 | level | close crosses a round level that no close crossed in the previous 120 bars: follow (grid: 0.01 for dollar pairs, 1.00 for yen pairs, 10 for gold, 0.50 for silver, 100 for us100 and ger40, 50 for us500, 500 for us30; not on oil, whose bars are roll-adjusted) |
| H01 | home-made | efficiency ratio ER(24) = abs(close - close[24]) / sum of abs(bar changes) rises above 0.5: follow the 24-bar move |
| H02 | home-made | ER(24) < 0.15 and the close is the highest (lowest) of 24 bars: fade |
| H03 | home-made | at least 85 % of the last 20 closes above EMA20 (buy) / at most 15 % (sell), first bar where it holds |
| H04 | home-made | internal bar strength > 0.8 on three bars in a row (buy) / < 0.2 (sell) |
| H05 | home-made | (close - close[24]) / (sd of bar returns x sqrt(24)) rises above +3 (buy) / falls below -3 (sell) |

**Filters (the mixes).** F0 none; F1 with the trend (the side agrees with close against EMA200 of the H4 frame); F2
against that trend; F3 strong trend (ADX(14) of the signal's frame >= 25); F4 weak trend (ADX(14) < 20); and, for H1
signals only, the session of the signal bar: F5 Asia (18:00-02:59 New York), F6 Europe (03:00-07:59), F7 US
(08:00-16:59).

**Exits.** Time exit and one stop: H1 signals 6 h and 24 h; H4 signals 24 h and 72 h; D1 signals 48 h and 120 h; stop
2 x D20; one position per rule and market (`sim.simulate`, mode `one`), FP costs of the kit, net and at costs x1.5.

**A rule** = signal x frame x filter x exit: about 1,390 rules, about 20,800 rule-market cells. The exact list is
generated by `lab/explore/scan/grammar.py`; where a definition above is not exact enough the builder fixes the detail
in `scan/GRAMMAR.md` BEFORE any run on real bars, and the list's sha256 is committed before the first run.

## 3. Three stages, so that a mirage has to be lucky three times
1. **Discovery: bars before 2019-01-01 only.** The scan's reader cuts every bar at that date: no figure of 2019 or
   later exists while rules are ranked.
2. **Frozen candidates, then confirmation on 2019-2021.** The selection of section 4 is mechanical; its list is
   written with its sha256 before the confirmation code runs, and confirmation computes nothing for any other rule.
3. **The lab's ordinary protocol for each survivor:** an idea number, a declaration (main = the rule on its unit,
   neighbours = its siblings), the judge on the whole in-sample period, the attack by an independent
   re-implementation, then ONE declared look at 2022-2025 (with the extra bar if one-sided). The in-sample bars of a
   survivor pass partly by construction (it was chosen on 2013-2018): the confirmation years and the validation look
   are the evidence. 2026 is never read.

## 4. Selection on the discovery years (fixed now)
Units: ALL15; FX8; IDX4 (the four indices); COM3 (gold, silver, oil); and each of the 15 markets alone.
For every rule and unit, on trades entered in the discovery years: n, PF net, t on daily sums, PF at costs x1.5,
positive years among 2013-2018 (a year without a trade is not positive), share of the unit's markets with a positive
total, largest market share of the profit.
- **Eligible:** n >= 200 (a basket) or 150 (one market); PF >= 1.10; PF at costs x1.5 >= 1.02; at least 4 positive
  years of 6; for a basket at least 65 % of its markets positive (COM3: 2 of 3) and no market above 50 % of the
  profit (35 % for ALL15 and FX8); and one sibling (the same signal, frame and filter with the other exit, or the
  neighbouring parameter of the same family with the same frame, filter and exit) with t >= 1.0 on the same unit.
- **Picked:** eligible rule-units ranked by t. First the baskets: at most 12 with t >= 2.5. Then single markets: at
  most 12 with t >= 3.0. A candidate whose daily result correlates above 0.6 with one already picked is skipped.
  There may be fewer picks, or none: then the scan says "nothing" and stops.
Why these numbers: with about 5,500 basket hypotheses and 21,000 single-market ones (strongly correlated), chance alone
gives a handful above these thresholds; a rule as good as the robot's best (t about 3.5 over nine years) is expected
at 2.9 on six years. Lower thresholds would flood the confirmation; higher ones would miss real rules.

## 5. Confirmation on 2019-2021 (fixed now)
A frozen candidate (same rule, same unit, nothing changed) is **confirmed** if, on trades entered in 2019-2021: t on
daily sums >= 1.65; PF >= 1.08; PF at costs x1.5 >= 1.00; at least 2 positive years of 3; for a basket at least 60 %
of its markets positive; and the kit's random-entry null on those trades (2,000 draws) at or above the 90th
percentile (the same-year null is reported). If nothing is real, about one candidate of 24 is expected to be confirmed
by chance; the validation look is there for it.

## 6. What is recorded
- In git: the code and its tests (`lab/explore/scan/`), `GRAMMAR.md`, the rule list's hash, the discovery summary
  (counts by family, the eligible table, how the whole grammar is distributed: share of rules with t > 2 by family,
  gross against net), `frozen_candidates.json`, `confirmation.json`, and one ledger line. No bar, no trade table.
- The ledger's running total grows by the number of rule-unit cells evaluated (about 26,000): every later
  deflated-Sharpe label will say "weak against selection", which is true.
- Out of git (`~/explore_data/scan/`): per-cell daily results, resumable after a machine restart.

## 7. Safeguards the builder and the verifier must show
- No look-ahead: for every signal family and frame, a truncation test (signals computed on bars cut at random times
  equal the full run's signals up to the cut), and each indicator against an independent plain implementation.
- The wall: the discovery code cannot read a bar of 2019 or later; the confirmation code refuses a candidate list whose
  hash is not the frozen one.
- The same simulator and costs as the judge (`kit.sim.simulate`), so a survivor's idea run reproduces its trades.
- Determinism: two runs give the same tables; a restart resumes without changing them.

## 8. What the scan cannot say
It covers one- to five-day holds on hourly bars with fixed, textbook parameters: a failure here does not close faster
rules (the lab's own lesson: nothing under one hour pays its costs) nor finer tuning (which this design refuses on
purpose). Three stages reduce selection, they do not remove it. Oil is judged with provisional costs: a survivor on
oil needs FP's real figures before anything else.
