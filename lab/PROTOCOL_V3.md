# Protocol n°3 — "a little every day" (pre-registered on 2026-11-11, before any test of this round)

## 1. The question
The user asks for a robot that "wins a little every day". No real edge wins every day; what can be
engineered honestly is the **share of winning days, weeks and months** of the whole portfolio, at equal
risk per trade, **without paying for it in expectancy**.

Baseline (the ten validated rules of round 2, 2022–2025, risk units R, equal risk per trade):
5,400 trades, +428.6 R, **45.0 % of days, 56.0 % of weeks and 72.9 % of months are winning**.
Already tested on 2026-11-11 and rejected: closing the day once it is ahead (lock at +0.5 / +1.0 / +1.5 R,
with or without a daily stop at −3 R) leaves the share of winning days at 44.5–44.9 % and costs 4–9 % of
the profit.

Two levers remain: **breadth** (more small independent bets every day) and **payoff shape** (more frequent,
smaller wins from the same edges). Rounds 1–2 already covered: gold (twice), US indices intraday, DAX,
crypto, macro events, lead-lag, night and calendar windows, a learned filter, pivots and Bollinger bands,
micro-scale prediction, and two blind tests of a language model as discretionary trader. Do not redo them
(`results/r2/_paused_state.json`, `results/r2/*/`, `results/pivbb/`, `results/micro/`).

## 2. Tracks of this round
| Track | Idea | Markets | Budget |
|---|---|---|---|
| `stocks` | The two us100 opening rules that passed validation (`ocm4`, `noise30`), **frozen**, applied to single US shares: tens of small trades a day. Then free research on the same family. | 40 US share CFDs, list fixed in `dl_round3.py` before any test | 2 frozen transfers + ≤ 60 configurations |
| `fx` | Currencies were never researched here. | eurusd gbpusd usdjpy audusd usdcad usdchf nzdusd eurjpy | ≤ 60 |
| `dip` | Daily-scale mean reversion on index CFDs (buy weakness, sell the bounce), swaps included. | us500 us100 us30 ger40 | ≤ 60 |
| `shape` | Profit targets / partial exits on the validated sleeves: more winning days for how much profit? | the validated sleeves | ≤ 50 |
| `news` | A language model reads timestamped headlines. Only testable after the model's knowledge cut-off (2026-07-01 →). Its own pre-registration is written when the data source is known. | gold, us100, eurusd, btc | separate |

## 3. Data split (unchanged)
- **IS**: start of data → 2021-12-31. All research, tuning and model fitting. US shares start in March 2017.
- **VAL**: 2022–2025. **The lead only, once per frozen finalist**, logged in `results/val_access.log`.
  Research agents never read a validation-period result.
- **HOLDOUT**: 2026, one look at the frozen portfolio. Not touched by this round.

## 4. Criteria
PROTOCOL_V2 section 4, unchanged, for a sleeve on one market: n ≥ 250, PF ≥ 1.12, t ≥ 2.5, ≥ 60 % of
years positive, PF ≥ 1.04 with costs ×1.5, neighbours' median PF ≥ 1.06, every-signal expectancy > 0, hold
≤ 5 trading days, random-entry null ≥ 97.5th percentile. Model-based rules: walk-forward out-of-fold only.

**Baskets** (one rule, identical parameters, many instruments — `stocks`, `fx`), because trades taken the
same day on correlated instruments are not independent:
- the t-statistic is computed on **daily sums of R** (days with at least one trade), t ≥ 2.5;
- pooled PF ≥ 1.12, pooled PF ≥ 1.04 with costs ×1.5, ≥ 60 % of years positive;
- at least **65 % of the instruments** have a positive expectancy, and no single instrument makes more than
  25 % of the profit;
- the null test is run on the pooled trades (same clock time, random day, same instrument).
For share CFDs the long and short sides are reported separately, and the result is also reported on days
when the us100 rule itself did not trade (is it more than the index trade repeated forty times?).

**`shape`**: for each sleeve the variant is chosen in-sample by one pre-declared rule — the highest share of
winning trades among the variants that keep at least 85 % of the sleeve's in-sample expectancy per trade
and still pass PF ≥ 1.12. The portfolio-level reading (share of winning days) is then made once on VAL by
the lead.

**VAL** (lead): PF ≥ 1.06, expectancy > 0, every-signal expectancy > 0, positive in at least 3 of the 4
years; baskets: t on daily sums reported. No re-tuning after VAL.

## 5. Costs
- `fx`: FP Markets Raw, spread plus the 6 USD per lot commission folded into the quotes
  (`r2/fp_costs.json`), Dukascopy's real intraday spread shape.
- `stocks`: Dukascopy's own quoted bid/ask for the share CFD, plus FP Markets' commission per share added
  to the quotes. Until FP Markets' figures are verified the provisional model is 0.02 USD per share per
  side on top of the quoted spread; finalists are recomputed with the verified figures before any VAL look.
  Splits are not adjusted in the data: a rule may not hold a share overnight, and any reference to an
  earlier session's prices must be corrected for the split ratio.
- Stress ×1.5 and the gross result are reported for every finalist, as before.

## 6. After the research
Each finalist is attacked by an independent reviewer (look-ahead, selection, execution on a 1,000 EUR
account: minimum size, margin, number of simultaneous positions). The lead then runs the single VAL look.
The portfolio's share of winning days / weeks / months with the new sleeves is reported against the
baseline of section 1, on VAL, without any weight optimisation. "Nothing survives" is a valid outcome.

Trials so far: round 1 = 321, round 2 = about 560, pivots + Bollinger = 76, micro = 8, language-model
tests = 2 pre-registered primary tests. Every configuration of this round is logged
(`results/r2/<track>/trials.jsonl`).

## Addendum A (2026-11-11, written before any look at the data): track `vol`, "selling insurance"
**Idea.** Futures on the VIX usually trade above where the VIX ends up (contango) and slide down as they
approach expiry; whoever is short the front contract is paid a little on most days and loses violently when
volatility spikes (February 2018, March 2020, August 2024, April 2025). It is the one liquid retail CFD whose
payoff is by construction "a little most days". It is a **risk premium** (being paid to carry crash risk), not
a forecasting skill, and it is labelled as such in every report.

**Data.** Daily open / high / low / settlement of every monthly VX contract from the exchange's public history
(`lab/data/vx/`), cut at 2025-12-31. IS = 2013–2021, VAL = 2022–2025 (lead only, once).

**Rule family (at most 24 configurations, every one logged in `results/r2/vol/trials.jsonl`).**
Short the front contract, rolled 5 business days before expiry, only when a causal filter says "calm":
contango (second / front − 1 ≥ c), and / or front future below its n-day average; out otherwise; protective
exit when the future closes more than s above the entry. Baseline to beat: always short.
Decision and execution at the daily settlement. Cost: 0.16 index point per round trip (spread 0.10 +
slippage) for every entry, exit and roll; stress ×1.5. P&L in R, with 1 R = the stop distance s × entry price.

**Criteria (IS).** t of the daily P&L ≥ 2.5 (flat days count as zero); ≥ 60 % of years positive; t ≥ 2.0 with
costs ×1.5; the pick's neighbours keep at least 70 % of its Sharpe ratio; the filter must beat "always short";
worst day, worst week, worst drawdown (R) and the share of winning days / weeks / months are reported.
PROTOCOL_V2's "hold ≤ 5 trading days" and the random-entry null do not apply to a carry position held for
weeks: this deviation is declared here.
**VAL.** Total > 0, Sharpe ≥ 0.5, at least 3 of the 4 years positive.

**Before any real use.** FP Markets' own instrument (symbol, contract size, minimum lot, spread, how the
monthly roll is charged, swap, trading hours) is unknown and must be read in the user's MT5; the vendor's CFD
on the same future (VOL.IDX/USD, history from October 2022) will be compared with the futures-based result.

## Addendum B (2026-11-11, written before this rule is run in the lab engine and before any 2022+ result): `fx`, month-end fix with the S&P 500 sign
**Origin.** Idea panel of 2026-11-11 (`results/panel/panel_2026-11-11.json`, rank 2; a designer and an independent
reviewer measured it in sample only, scripts in `lab/panel/monthend_*.py`). **Mechanism.** Funds that hedge the
currency risk of their US shares must re-set their dollar hedge at the month-end 16:00 London benchmark: after a
month in which US shares rose they sell dollars into the fix, after a falling month they buy; once the forced order
is done the price comes back. The lab's earlier month-end rule (`B1_fix_me_rev`, sign = against the previous hour's
move) is a different sign rule; this is configuration n°16 of the track, the neighbours below n°17–22.

**Frozen rule `B5_fix_me_spx`.** Pairs: eurusd, gbpusd, audusd, nzdusd, usdcad, usdchf (the yen stays out).
Date: the last weekday of the calendar month that is neither an England bank holiday nor a New York Stock Exchange
holiday (python `holidays` 0.108: `country_holidays("GB", subdiv="ENG")`, `financial_holidays("NYSE")`).
Sign: official S&P 500 daily closes (public file, column `price` of https://squeezemetrics.com/monitor/static/DIX.csv):
if the close of the previous New York session is above the last close of the previous calendar month, **buy dollars**
against the six currencies; if below, **sell dollars**; no trade if equal. Entry: market, at the open of the first
M1 bar at or after 16:02 London (dropped if more than 5 minutes late). Stop: 1.5 × ATR(24) of complete hourly mid
bars, from the fill. Exit: market at the open of the first M1 bar at or after 16:30 London. Equal risk per pair.
No filter. Costs: FP Markets Raw frames (`r2/fp_costs.json`).

**Statistic.** "Basket net bp of a date" = mean over the pairs traded that date of 10,000 × P&L / entry price, from
the lab engine (spread, commission, slippage and stops included).

**In sample (2013–2021, 108 dates).** PROTOCOL_V3 section 4 basket criteria: n ≥ 250, t on daily sums of R ≥ 2.5,
pooled PF ≥ 1.12, PF ≥ 1.04 with costs ×1.5, ≥ 60 % of years positive, ≥ 4 of 6 pairs positive, no pair above 25 %
of the profit; neighbours (entry 16:00 / 16:01 / 16:03 / 16:04 with exit 16:30; entry 16:02 with exit 16:20 /
16:45): median pooled PF ≥ 1.06; null: the same dates replaced by random weekdays on which both centres are open
(same clock, same side for the six pairs, 1,000 draws): the rule's mean basket bp ≥ 97.5th percentile. The engine must
also roughly reproduce the panel's figure (about +3.9 bp net per date); a result below +2.5 bp is investigated
before anything else. The sign from the lab's us500 frame (16:00 New York) is compared with the official one
(diagnostic).

**Validation (lead, one logged look, 48 dates of 2022–2025).** Pass = all of: basket net ≥ +1.5 bp per date;
t on the 48 dates ≥ 2.0; ≥ 60 % of dates positive; ≥ 5 of 6 pairs with a positive mean; ≥ 3 of 4 years positive;
basket net still > 0 with spread and slippage doubled; and the round's own rule (pooled PF ≥ 1.06, expectancy in
R > 0, ≥ 3 of 4 years positive in R). Reported, not part of the pass: up months and down months separately; after
a pass the "sell dollars after a down month" half is traded only if its own validation mean is above zero.
**A fail is final**: no other window, sign, pair list or filter is tried on 2022–2025.

**Before any money.** Log FP Markets' bid and ask on the six pairs every second from 15:55 to 16:35 London on
30 November and 31 December 2026; live only if the median all-in cost at 16:02–16:03 is at most twice the frame's.
Live size 0.01 lot per pair; stop after 24 month-ends with a negative sum.

## Addendum C (2026-11-11, written before any 2022+ result of this split): "stressed market" gate on `noise30` (us100)
**Origin.** Idea panel, rank 3 (`lab/panel/gate_*.py`). **Idea.** When option dealers are short gamma, or simply
after a bad week for the S&P 500, hedgers have to trade with the move and intraday trends run further: the
validated us100 noise-area momentum sleeve would earn more per trade on those days. It adds no trade; a pass only
buys a size tilt.

**Two flags, both known before 09:30 New York** (file as in addendum B; columns `price`, `gex`). For a daily series
x, pct(x) = share of the previous 251 values that are strictly below today's value (window 252, at least 126).
- **G**: pct(previous day's `gex`) < 0.33.
- **P**: pct(sum of the last five daily log returns of `price`, up to the previous close) < 0.33.

**In sample.** `results/r2/idx_us/trades_is_noise30_us100.csv`; the script must reproduce the reviewer's split
(G: about +0.169 R on 591 trades against +0.026 R on 1,052; P: about +0.161 R against +0.021 R).

**Validation (lead, one logged look).** Trades of 2022–2025 already saved (`results/r2/recalc/trades/noise30__us100.parquet`,
about 850). For each flag, pass = all three: expectancy(flagged) − expectancy(unflagged) ≥ +0.10 R; PF of the
flagged trades ≥ 1.25; flagged better than unflagged in at least 3 of the 4 years. Decision table: neither passes
= no gate, the sleeve stays at equal risk and no other threshold, window or source is tried on 2022–2025; P passes
= the live gate is P alone; only G passes = G, after 60 demo sessions showing that the gamma estimate can be had
every morning. On a pass: 1.5 × risk on flagged days, 0.75 × otherwise (never more), never applied to the
opening-candle sleeve, reviewed once a year (off if flagged trades do not earn more per trade than the others
after at least 400 trades under the gate). Chance of a false pass: about 7 % per flag, 11 % for the pair.
