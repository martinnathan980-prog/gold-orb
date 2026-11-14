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

## Addendum D (2026-11-11, written before this rule is run in the lab engine and before any 2022+ result): `fx`, Tokyo fixing on settlement days
**Origin.** Idea panel, rank 4 (`lab/panel/tokyo_*.py`: a designer and a reviewer, in sample only). **Mechanism.** On
Japanese settlement days ("gotobi": the 5th, 10th, 15th, 20th, 25th and the last day of the month) banks buy dollars
for importers at the 09:55 Tokyo fixing, which pushes USD/JPY up into that minute; once the flow is done the price
falls back (Krohn, Mueller and Whelan, Journal of Finance 2024).

**Frozen rule `B6_tokyo_gotobi`.** USDJPY only. Days: each gotobi date, moved back to the previous Japanese bank
business day when it falls on a weekend or a bank holiday (bank business day = Monday–Friday, not a Japanese national
holiday — python `holidays` 0.108 `country_holidays("JP")` — and not 31 December, 2 or 3 January); **Bank of Japan
decision days are skipped** (last day of each Monetary Policy Meeting, list taken from the Bank's own schedule pages
https://www.boj.or.jp/en/mopo/mpmsche_minu/ and saved in `r2/tracks/fx/boj_decisions.json`). Entry: **sell** USDJPY
at market at the open of the first M1 bar at or after 09:55 Tokyo (00:55 UTC; dropped if more than 5 minutes late).
Exit: market at the open of the first M1 bar at or after 11:55 Tokyo. Disaster stop: 3 × ATR(24) of complete hourly
mid bars, from the fill. No filter.
Fallback, examined only if the frozen rule fails its in-sample bars at the measured cost: the same trade on
"gotobi days or Fridays" (`B7_tokyo_gotobi_fri`; found after the fact by the reviewer, +2.33 bp net in sample).
**Exactly one** of the two may go to validation.

**Cost.** The lab frame charges 0.71 bp all-in on USD/JPY (1.1 pip at 155). The Raw commission alone (6 USD per
100,000 USD) is 0.6 bp at any price, so the real figure is probably nearer 0.9–1.0 bp; it is read in the user's MT5
(commission from a demo round trip, spread between 00:50 and 01:00 UTC). Tonight the in-sample test is run on a
**grid of all-in costs** (0.71, 0.80, 0.90, 0.95, 1.00, 1.10, 1.20, 1.40 bp; slippage 0.1 bp per side on top), and
the row at or just above the measured cost is the one that counts.

**In sample (2013–2021).** PROTOCOL_V2 section 4 at that cost: n ≥ 250, PF ≥ 1.12, t ≥ 2.5, ≥ 60 % of years positive,
PF ≥ 1.04 with costs ×1.5, neighbours (entry 09:50 / 10:00 with exit 11:55; entry 09:55 with exit 11:00 / 13:00 /
15:00) median PF ≥ 1.06, random-entry null (lab `null_test`, mode "time": same side, stop and holding time at a random
day and time) ≥ 97.5th percentile.

**Validation (lead, one logged look, about 290 trades of 2022–2025, at the measured cost).** Pass = all of: mean net
result > 0 with t ≥ 1.5; PF ≥ 1.06; ≥ 3 of 4 years positive; still positive without its best day; and the mechanism
still visible: the fall of USD/JPY from 09:55 to 10:05 Tokyo on Japanese bank business days is positive with t ≥ 3 and
absent on Japanese bank holidays. Mechanism visible but net fails = closed as "real but too thin". No volatility
filter, no third variant.

**After a pass only.** Three months at 0.01 lot to measure the real cost at 09:55 Tokyo; stop if the median all-in
cost over 20 trades exceeds 1.5 bp.

## Addendum E (2026-11-11, evening; written before any 2022+ result of this kind): "green weeks, green days"
**The user's revised objective.** "Too many weeks in the red: emotionally too hard. Statistically green days, even
with small gains." The size of the gain is now secondary; the **share of winning weeks** comes first, the share of
winning days second. Costs are set aside while searching (gross first) but every figure shown to the user is given
both without and with costs.

**What is already known (in sample, common period 2018-02 → 2021, the ten validated rules, equal stake):** 49.6 % of
days, 58.3 % of weeks and 85.4 % of months are winning. Profit targets on every trade buy almost nothing (52.1 % of
days for −41 % of the profit). First scout of this addendum (seven stake rules, all logged below as trials 1–7):
raising the stake when the WEEK is in the red (cap 3×) gives 71–74 % winning weeks, 51–54 % winning days, with the
worst week 2.4 times larger at an unchanged base stake. Raising the stake within the day gives 52–54 % of days.
**Arithmetic that no rule escapes:** with little or no edge at the daily scale, a share p of winning days means the
average losing day is about p / (1 − p) average winning days (80 % → 4; 90 % → 9); the same holds for weeks.

**Families allowed.** (1) **Stake rules** on the trades of the validated rules (entries, stops and exits untouched):
catch-up within the week or the day, weekly / daily profit locks and loss stops, scaling of the base stake. The
stake of a trade may depend only on results CLOSED before its entry. (2) Exit shaping (already measured). (3) Other
structures with a high share of winning days, whatever the venue (carry), reported as such.

**Design, in sample only** (entries before 2022-01-01). At most 40 stake configurations, every one logged in
`results/r2/stake/trials.jsonl`. Reference = the ten rules at an equal stake. **Selection rule, fixed now:** scale
the base stake of each configuration so that its in-sample worst week equals the reference's; among the
configurations whose in-sample maximum drawdown is then no worse than the reference's, take the highest share of
winning weeks (tie: highest total). At most two frozen profiles ("soft", "strong").
**Zero-edge control, mandatory for every profile:** the same stake rule on the same trades with each trade's result
replaced by a draw with no edge (the trade's own R with a random sign after removing the sleeve's mean; 1,000
draws): share of winning weeks, worst week, probability of losing half the account. The user is shown it.
**Account realism:** the 1,000 EUR account (`goldlab/portfolio.py::run_account`: minimum lots, 6 positions, 2 per
market, stop at −50 %); a stake rule that the minimum lots make impossible on 1,000 EUR is reported as such, with the
account size from which it works.

**Validation (lead, one logged look per frozen profile, 2022–2025, account simulator).** Reported against the
reference: winning weeks / days / months, each year, worst day and week, maximum drawdown. A profile is offered to
the user only if: winning weeks ≥ reference + 8 points; worst week and maximum drawdown ≤ 1.25 × the reference's;
total profit > 0. No re-tuning after the look.

### Addendum D — clarification of 2026-11-11 (late evening), after the independent attack and BEFORE any 2022+ result
Two reviewers and a verifier re-implemented the rule (identical trades, no look-ahead found) and attacked the
evidence (`results/r2/fx/tokyo_review.json`). Nothing below changes the frozen rule or the pass criteria as coded.
1. **Units.** In the criteria, t, PF and "years positive" are computed on R = P&L / stop distance
   (`goldlab.metrics.report`), the mean is in basis points. On a fixed lot the same trades have t 2.04 at 0.95 bp
   (2.34 at 0.71): the in-sample bar is met in R only.
2. **Sample.** About 270 trades in 2022–2025 (68, 69, 67, 66 by calendar), not 290.
3. **How to read the look.** After correcting for the variants examined before the freeze, the in-sample t is worth
   about 1.8 to 2.7, not 3.06. Power of the registered look: about two thirds if the edge is intact, a quarter to a
   half realistically; false pass 2–6 %. A pass means "not contradicted"; a fail is final. "Mechanism visible but
   net fails" closes the idea, and no ten-minute version will be tested afterwards (the profit is a late-morning
   drift that is not specific to settlement days; the fixing leg only pays the cost).
4. **Cost rule, fixed before the cost is measured.** The measured cost is the HIGHER of two readings: the first
   session, and a settlement-day morning (Friday 13 November 2026, 00:50–01:00 UTC). If it is above 1.10 bp, the
   1.20 row passes in sample only thanks to the trade of 24 June 2016 (t 2.32 without it) and **the look is not
   spent on B6**. The fallback B7 stays as registered, with the same test (its in-sample pass at the measured cost
   must survive the removal of its best trade).
5. **A pass is not a go-live.** One minute late fails in sample (entry 09:56 at 0.95 bp: t 2.14). The order must be
   sent on a timer at 09:54:58–09:55:00 Tokyo; the loss inside the first seconds (32 days measured: none within
   1 s, about 0.3 bp at 2–5 s) is to be measured on every in-sample day before any live order. Size: risk about 2 %
   of equity against the 3 × ATR stop, at most 0.10 lot. Order of magnitude, in sample: about 50 EUR a year on
   1,000 EUR; 0.3 point of winning days for the portfolio.
6. **Citation.** Krohn, Mueller and Whelan cover all days on 1999–2019 with a longer window and report a decay since
   2013; the settlement-day restriction and the two-hour exit are the lab's own choices; outside the paper's sample
   the evidence is t 1.7 on 138 trades (2020–2021).
7. **Diagnostics printed by the same single run, declared here as NON-criteria:** t on a fixed lot (basis points);
   the result without the trades of 25 December (a retail broker is closed that day); entry at 09:54 and at 09:56
   (execution sensitivity; no variant can be adopted from them).

### Addendum E — clarification of 2026-11-11 (night), after the design and its independent attack, BEFORE any 2022+ result
The designer logged 39 stake configurations and froze two profiles by the selection rule (`r2/tracks/stake/`,
`results/r2/stake/`); a reviewer re-implemented everything, found no look-ahead and corrected how the result must be
read (`results/r2/stake/review.json`). Written before the look:
1. **Three profiles get the single look, not two.** `soft` (trial 28: catch-up on the crypto rules up to 3×, small
   stake once the week is ahead; base stake 0.58 of the reference's) and `strong` (trial 36: crypto up to 5×, us100
   up to 3×; base 0.39) are the two frozen by the rule. **`cushion_only`** (trial 33: no catch-up at all, only a
   small stake once the week is ahead; base 1.0) is added by the lead, as a declared deviation, because it is the
   only rule whose stake never exceeds the normal one and the only one that keeps the reference's worst week on a
   small account.
2. **Two readings of every criterion** (winning weeks ≥ reference + 8 points; worst week and maximum drawdown ≤ 1.25 ×
   the reference's; profit > 0): **as designed** (every signal taken, no compounding, the frozen base stake; the
   accounting of the search) and **on 1,000 EUR** (account loop with minimum lots, 6 positions, 2 per market, the
   account kept at 1,000 EUR, stop distances at TODAY's price level because the minimum lots bite at today's
   prices; the reference simulated the same way at 1 %). A profile is offered for the user's account only if it
   passes on 1,000 EUR; if it passes only as designed it is described as "from N EUR".
3. **Winning weeks are also counted on week-end equity** (trades still open at the end of the server week marked at
   the last price), because that is what the user sees: in sample the gain is then +12 points (soft), +16.5 (strong),
   +7 (cushion) instead of +17, +21, +9. The "+8 points" criterion must hold on this reading too.
4. **Reported with every profile, as the reviewer requires:** the number of weeks worse than −8 %; the same profit
   earned with a plain flat stake (its worst week and its weeks worse than −8 %); the in-sample behaviour at half
   the edge and with no edge (real order of the trades: 44.7 % winning weeks for the reference, 53.9 % soft, 61.2 %
   strong, 48.5 % cushion; the rule manufactures +4 to +22 points by itself); the chance of losing half the account
   with no edge (soft 53 %, strong 47 %, against 38 % and 22 % for a flat stake of the same size): **the stake rule
   does not lower the risk, it moves it from the number of red weeks to their size.**
5. On 1,000 EUR at today's prices the profiles take a quarter to a third of the signals (the reference itself 42 %):
   mostly the two ether rules. This is reported as what it is.

### Addendum E — outcome of the single look (2026-11-11, `results/r2/stake/val_look.json`)
2022–2025, ten rules, 5,400 signals. Reference at an equal stake of 1 %: 53.1 % winning weeks (55.0 % on week-end
equity), 48.1 % winning days, 72.9 % winning months, total +428.6 %, worst week −13.7 %, maximum drawdown 36.8 %,
longest run of red weeks 5.
- **`cushion_only` passes on every reading**: 69.9 % winning weeks (66.0 % on equity), total +433.9 %, worst week
  −11.8 %, drawdown 29.8 %, longest red run 2; on a 1,000 EUR account at today's prices 66.5 % against 52.6 %, the
  same worst week (−7.1 %), drawdown 22.3 % against 24.8 %, +40.9 % a year against +45.6 %. The rule: the realised
  result w of the current server week, in base stakes; stake multiplier 1 if w ≤ 0, min(1, max(0.25, w / 4)) if
  w > 0. **Adopted for the robot** (the user may refuse). What it is not: evidence of an edge (with no edge it still
  shows +4 to +11 points of winning weeks); it leaves the share of winning days unchanged (48.5 %); green weeks are
  smaller (+5.0 % on average against +7.5 %), red weeks the same size (−4.7 %).
- `soft` and `strong` pass as designed (73.2 % and 77.0 % winning weeks, 84 % and 76 % of the reference's profit)
  but **fail on 1,000 EUR** (worst week 1.8 and 1.6 times the reference's): described as "from about 20,000 EUR",
  not offered for this account.
- **Winning days:** no construction passes. Stake rules add 1 to 6 points; a daily target on the account buys 65 %
  of green days for 86 % of the profit (in sample); the funding carry on bitcoin no longer pays more than a savings
  account for a French retail resident (`results/r2/carry/`, `results/r2/jours/`).
- Note on the 1,000 EUR account: at today's price levels the minimum lots let through only 45 % of the signals
  (reference) or 36 % (cushion); the earlier simulation `sim1000.py` (1,000 → 18,175 EUR) compounded and used the
  lower prices of 2022–2023.

## Addendum G (2026-11-11, night; written before any run): growth paths with a risk that starts high and falls as the account grows
The user's request: "at the start you can take much more risk to go much faster, and the higher the account, the lower
the risk; 1,000 EUR added every month; show me tables and charts". This is an ILLUSTRATION OF SIZING, not a selection
study: the lab selects no rule, parameter or schedule from its output. The user chooses a schedule, knowing that the
curves replay the same 2022–2025 trades that validated the rules (they flatter any sizing that leans on those years).
- **Trades:** the ten sleeves' 2022–2025 trades at FP costs, with the adopted `cushion_only` stake rule, at today's
  price level (minimum lots), read through one access logged in `results/val_access.log` (label
  `growth_paths:risk_schedules:illustration_no_selection`).
- **Account mechanics:** those of `r2/tracks/stake/account.py` (lots rounded down, a trade is skipped when the minimum
  lot is too large for its budget, 6 positions, 2 per market, margin check), compounding, plus 1,000 EUR paid in at
  the start of each month. No daily-loss lock. The −50 % stop is NOT applied (the user asked for no brake); the first
  time the hands' rule would have fired (balance at or below half of the reference capital, the reference following
  the payments as in the hands 1.11) is recorded. A balance that reaches zero stays at zero until the next payment.
- **Declared schedules** (risk per trade, % of the balance, by size of the balance): A 1 % always; B 2 % below
  5,000 EUR, then 1 %; C 5 % below 3,000, 3 % below 10,000, 2 % below 20,000, then 1 %; D 10 % / 5 % / 2 % / 1 % at the
  same three thresholds; E 20 % / 10 % / 5 % / 2 %. Nothing else is shown.
- **Edge scenarios:** each sleeve's mean result per trade multiplied by 1 (as in 2022–2025), 0.5, 0.25 and 0 (a
  constant per sleeve is subtracted from every trade's R; the spread of results is unchanged).
- **Two readings:** (1) the real order of 2022–2025 from 1,000 EUR, one path per schedule, edge ×1; (2) 2,000
  resampled paths of 36 months per schedule and scenario (weeks drawn in blocks of mean length 8 weeks, fixed seed,
  the same draws for every schedule and scenario), reported as percentiles of the balance by month, the share of paths
  above 15,000 / 26,000 / 52,000 EUR at 12, 24 and 36 months, the share of paths that hold less than the money paid
  in, and the share where the −50 % rule would have fired.
- **Self-check before the run:** with schedule A, no payment and the −50 % stop, the engine must reproduce
  `account.py` exactly (final balance, trades taken, skips), in sample and on the stored figures of
  `results/r2/stake/val_look.json`.
- **To be said with every figure:** past, on paper, same years as the validation; slippage on larger sizes, the
  broker's margin call and the minimum stop distance are not modelled beyond `account.py`'s margin check.

### Addendum F — adding to winning trades ("pyramiding"): in sample only, no finalist, no validation look (2026-11-11)
The user's question: "when a trade is winning, should we add trades to blow up the gain?". Definitions, grid (24
configurations: fixed-risk and free-risk add-ons at +1R / +2R, one or two adds, all sleeves or the trend sleeves) and
selection rule were fixed by the lead, written in `r2/tracks/pyramid/pyramid.py` and logged in
`results/r2/pyramid/run_log.jsonl` before any add-on result was computed. In sample (2018-02..2021, reference +787.4
stakes, drawdown 29.1): an add-on opened once the trade is +1R earns +0.134 R per unit of its own risk against +0.160 R
for a fresh trade; every configuration raises the total and raises the drawdown at least as much; profit at equal
drawdown is 0.82 to 1.08 times the reference (1.15 was required); winning weeks 58.3 % → 55.3–58.7 %; on a 1,000 EUR
account fewer than one add-on in ten can be placed and the account ends lower. An independent reviewer rebuilt it by
another method (add-ons as rows of the lab's own order table) and reproduced it exactly. **Finalist: none. No 2022–2025
look was made** (`results/r2/pyramid/`, `results/r2/pyramid/panel.json`).

### Addendum G — clarification of 2026-11-11 (late night), after the independent recomputation and critique
(`results/r2/stake/growth_review.json`), written BEFORE the corrected run
- **Defect corrected.** The first run let a payment leak into the stake rule's week result through a floating-point
  residue (balance + 1,000 − balance − 1,000 ≠ 0), which cut some stakes to a quarter after a payment. The real-order
  figures were unaffected; of the 3,940 published resampled figures 3,748 were within 1 %. The week and day results are
  now measured against a base that receives the payment itself; the self-check against `account.py` is unchanged.
- **Two scenarios added** (the first run had nothing below "the rules exactly cover their costs"): edge × −0.5 ("the
  rules are noise and the costs are paid": the reviewer puts a zero gross edge near × −0.44) and edge × 1 with the
  weeks of 2024 excluded from the draw (2024 carries 42 % of the total).
- **Two schedules added, declared here before any run:** C2 and D2 = the percentages and thresholds of C and D, the
  thresholds being compared with the larger of the balance and the money paid in, so that the risk also falls as money
  is paid in (in C and D it stays at its maximum for as long as the account does not grow, i.e. exactly when the rules
  earn nothing).
- **Schedule E is no longer shown** (kept in the result file): all its open stops together exceed the balance in 95 to
  99.7 % of paths; it is not executable.
- **Reporting.** Gains (balance minus money paid in) instead of milestones on the balance, which are reached by the
  payments alone; the gain the worst path in ten shows after one year; the first month from which the median path
  gains at least 1,000 EUR a month on a 6-month average for good; every amount rounded to two significant digits; the
  real-order curves are not shown (they end at sizes the cost model was never built for and are a top-decile sequence).
- **Assumed settings of the hands, to be said with the figures:** the risk cap follows the schedule, the daily lock is 6
  stakes instead of 6 % of the balance, the −50 % stop is off. Not in the curves: the 20× size limit (nothing up to 5 %
  risk, about one trade in ten at 10 %), the broker's real leverage per market (unverified), margin calls, taxes, the
  Friday-night closure of the hands.

### Addendum G — second clarification (2026-11-11, night), written BEFORE any run: plans that bound the loss
The user, after seeing the corrected figures: "how do we reduce the loss? we must increase the gain at the start and
reduce the risk". No rule creates gain and removes risk at once; what can be done is to bound the loss by construction
and pay for the risk with the robot's own gains. Declared plans, all on the same ten rules, the same 2,000 draws and the
same six scenarios, compared with A (1 % always) and C2 (5 % → 1 %, keyed on max(balance, money paid in)); nothing else
will be run:
- **P "steps"**: risk as C2. The first three payments (3,000 EUR) are made whatever happens; from the fourth on, the
  1,000 EUR of a month is paid in only if, at that moment, the balance is at least the money already paid in; otherwise
  that money stays outside the robot (it is not lost and not paid later). **P2**: the same, and a month that is paid
  also pays up to 1,000 EUR of the months skipped before.
- **G "gains pay for the risk"**: risk per trade = base + 10 % of the accumulated gain (balance minus money paid in, if
  positive), capped by the C2 percentage for the size (never under the base); base = 1 % of the balance, 0.5 % when the
  balance is more than 10 % under the money paid in, 0.25 % when more than 20 % under.
- **K70 / K50 "floor"**: risk per trade = 10 % of the cushion, the cushion being the balance minus 70 % (K70) or 50 %
  (K50) of the money paid in, capped by the C2 percentage for the size; no trade when the cushion is used up, until a
  payment rebuilds it.
- **GP, K70P**: G and K70 with the steps of P.
- **Reported:** for each plan and scenario, the gain or loss of the robot (balance minus the money really paid in) at 12
  and 36 months (median, 1 in 10 low and high), the money really paid in (median), the share of paths in loss, the
  month of a lasting 1,000 EUR a month on the median path, and the share of paths where the −50 % rule would have fired.
  Rounded to two significant digits on the page. The existing plans must come out unchanged (regression check).
- **To be said with it:** a bounded loss is paid for by a lower result when the robot works but starts badly; the plans
  are sizing rules chosen on simulations of the validation years; the cheapest protection is information obtained
  before real money (the measured costs, the untouched year 2026, the demo account).

### Addendum G — outcome of the plans that bound the loss (2026-11-11, `results/r2/stake/growth.json`, `growth_protect_review.json`)
An independent plain-Python implementation, written from the text above and frozen before reading the lab's code,
reproduces all 2,000 paths of every plan to the cent (5.77 million balances); the earlier plans are unchanged.
Robot's gain or loss after three years, median (worst path in ten), for 36,000 EUR set aside:
- rules worthless (edge × −0.5): flat 1 % −16,600 (−23,000); fast start C2 −18,800 (−24,400); **steps P −2,900 (−5,800),
  3,000 EUR paid in**; floor K70 −10,500 (never under −10,800 by construction); gains-funded G −8,400.
- half of the paper edge: flat 1 % +32,600 (+3,000); C2 +42,800 (+5,500); P +29,000 (−2,600), 31,000 EUR paid in on the
  median path; P2 +33,400; K70 +31,100; G +26,200.
- GP and K70P cut the loss under 1,000 EUR and kill the gain (median about −300 and −900 at half edge).
What the adversarial reading adds, to be said with these figures: P is not a ceiling (worst of 2,000 paths −15,700;
if the robot works for a year and then turns to noise the typical loss is about −7,400 against −9,500 to −13,100);
its protection comes from paying less into a losing robot, not from timing (the switch is slow: at month 4 it refuses
the payment in 44 % of the paths of a robot at half edge); at half edge P ends below C2 in nine paths out of ten and in
one path in ten the robot receives 5,000 EUR or less; no advantage when the rules just cover their costs (−2,800
against −2,300) nor in the first year; the −50 % stop of the hands must be off (with it P is stopped in three paths out
of four at half edge); the quarter-edge median is about zero (−900 to +1,500 across draws). A trial budget at 1 %
instead of 5 % (diagnostic, not a declared plan) loses about 1,000 EUR in the first year instead of 2,500 when the
rules are worthless and gains about 22,000 instead of 29,000 at half edge.

### Addendum G — third clarification (2026-11-12, night), written BEFORE any run: a loss that cannot go deep, a fast start that calms down
The user: "I need a very fast growth at the start that calms down with time; the losses must be limited; the worst is
consecutive losses; I cannot lose 50 % and wait a year for it to come back; you have a free hand". No sizing rule adds
edge: what a sizing rule can do is decide how deep a fall may go and how the risk moves with the size of the account.
Declared plans (the same ten rules, the same 2,000 draws, the same six scenarios; nothing else will be run):
- **Loss budget with a ratchet (R).** The robot may only risk what is left of a loss budget. Reference size = money paid
  in + the highest gain reached so far (the account's high, payments set aside). Budget = a share of that size, by
  brackets: **R1** 50 % of the first 3,000 EUR, 30 % of the next 7,000, 20 % of the next 10,000, 15 % beyond; **R2** 30 %,
  20 %, 15 %, 10 % on the same brackets. What is left = budget minus the fall already made from the high. Risk per trade =
  15 % of what is left (at most 6 positions: never more than 90 % of it at risk at once), capped by the C2 percentage for
  the size (5 % / 3 % / 2 % / 1 %). No trade when nothing is left, until a payment or a new high rebuilds it. So the fall
  from the high cannot exceed the budget (gaps aside), and gains once made are locked in the same proportion.
- **Payments:** `a` every month; `p` by steps (the first three whatever happens, then only when the balance is at
  least the money paid in); `s` soft steps (when under water, a quarter of the month's 1,000 EUR is paid and the rest
  stays outside). Plans: R1a, R1p, R1s, R2a, R2p, R2s.
- **Da:** the C2 schedule multiplied by max(0.2, 1 − fall from the high / 25 %), payments every month (the usual
  "trade smaller in a drawdown"; no hard limit).
- **Measured on every path, for these and for A, C2, P, K70:** the deepest fall from the high, payments set aside, at
  week ends (the high being paid-in money + best gain so far); the deepest fall of the balance as the user sees it
  (payments included) and the weeks it takes to see the previous high again; the longest run of losing weeks and of
  losing months; and the gains as before.
- **What "best" means, fixed here:** among all plans whose deepest fall stays at or under 25 % in 9 paths out of 10 both
  when the robot does half of its paper result and when the rules are worthless, the plan with the highest median gain
  after 12 months at half edge; ties and runners-up are shown.
- **To be said with it:** a limited fall is paid for by a robot that trades small, or not at all, after a bad run, so
  it climbs back more slowly; all of this is sizing on simulations of the validation years; figures rounded to two
  significant digits.

### Addendum G — fourth clarification (2026-11-12, night), written BEFORE the run: the reference line and a start that calms down
Outcome of the third clarification first (`results/r2/stake/growth.json`): **no declared plan meets the criterion** (deepest
fall at or under 25 % in 9 paths out of 10 at half edge and with worthless rules): closest are Da and R2a (27.7 %).
The loss budgets with a ratchet (R) do limit the fall to their budget, but the robot then trades small for most of the
time: median gain after three years at half edge +5,300 (R1a) and +540 (R2a) against +32,600 at a flat 1 %, and the
longest stretch under the high grows from 37 weeks to 92 and 106. The fast starts are what produces falls of 40 to
66 % (on small sums). The time spent under the high does not depend on the size of the stake.
Declared now, before any run, to show the user the real choice (nothing else will be run):
- **A05, A025:** 0.5 % and 0.25 % of the balance per trade, always (the reference line: smaller stake, smaller falls).
- **F "fast, then calm":** 5 % under 3,000 EUR, 2 % under 6,000, 1 % under 12,000, then 0.5 %, the thresholds read on the
  larger of the balance and the money paid in.
- **D1:** 1 % multiplied by max(0.2, 1 − fall from the high / 25 %).
- **Two more measures on every path:** the deepest fall from the high recorded after the twelfth month (share and
  euros), and the deepest fall in euros over the three years.
The same criterion applies; if nothing meets it, that is the result.

### Addendum G — fifth clarification (2026-11-12, night), written BEFORE the run: a stop that is armed once the start is over
Outcome of the fourth clarification (`results/r2/stake/growth.json`): by the declared criterion only **A025** (0.25 % per
trade) qualifies (deepest fall 10.5 % and 23.6 % in 9 paths out of 10 at half edge and with worthless rules); its median
gain at half edge is +510 EUR after one year and +6,600 after three. A05 fails only when the rules are worthless (43.8 %),
D1 by a hair (26.3 %). **F** (5 % under 3,000 EUR, 2 % under 6,000, 1 % under 12,000, then 0.5 %) has the first year of a
flat 1 % or better (+3,400 at half edge, +6,500 on paper) and, after the twelfth month, the falls of a flat 0.5 %
(15 % typical, 23 % one path in ten, at half edge); its deep falls (42 % typical) are those of the first months, on
small sums. With worthless rules every plan that keeps trading keeps falling: only a stop bounds that case.
Declared now, before any run (nothing else will be run):
- **FS:** plan F, with the hands' stop applied at −25 % of the reference capital (reference = max(reference + payment,
  balance right after it), as in the hands 1.11), **armed only once 12,000 EUR have been paid in**; when it fires the
  robot stops for good and nothing more is paid in.
- **A05S:** 0.5 % per trade always, the same stop at −25 % armed from the start.
Reported like the other plans, plus the share of paths stopped. The criterion is unchanged; a plan that stops is judged
on what the user has lost when it stops.

### Addendum G — outcome of the fifth clarification and of its review (2026-11-12, `results/r2/stake/growth.json`, `growth_final_review.json`)
An independent recomputation reproduces FS and A05S to the cent once the conventions are aligned. One measure was
wrong: the highest balance "as seen" was first read at the end of week one, so a fall that starts in the first week was
understated for the fast starts (FS at half edge: 36.8 % typical and 52.6 % one path in ten, not 32.2 % and 50.0 %).
Robot's gain or loss, median (one path in ten), 36,000 EUR set aside:
- **FS** (5 % → 2 % → 1 % → 0.5 %, stop at −25 % armed once 12,000 EUR are paid in): at half edge +3,400 (−750) after
  12 months and +17,200 (+2,200) after 36; stopped in 8.5 % of paths; after the twelfth month the deepest fall is 16 %
  (24 %). Worthless rules: −3,700 (−5,500) with 12,000 EUR paid in, stopped in 95 % of paths at month 11.
- **A05S** (0.5 % always, the same stop armed from the start): at half edge +1,200 (−400) and +14,600 (+2,500); deepest
  fall 15 % (21 %); stopped in 4.2 % of paths. Worthless rules: −4,500 (−6,900) with 22,000 EUR paid in, stopped in 88 %
  of paths at month 20.
- By the criterion declared in the third clarification still only A025 qualifies (A05S: 26.5 % with worthless rules,
  the stop being read at closes).
What the adversarial reading adds, to be said with these figures: the deep falls of FS are those of its first three
months — 41 % typical and 59 % one path in ten at half edge (34 % / 52 % on paper, 52 % / 68 % with worthless rules), a
fall of half the account or more in 12 % (paper), 23 % (half edge) and 58 % (worthless) of paths, on about 1,000 EUR
(1,600 one path in ten); over the first year the deepest fall is 1,400 to 1,900 EUR typical and 2,200 to 3,200 one path
in ten (3,800 / 5,300 with worthless rules); the stop fires wrongly in 8.5 % of paths at half edge (those paths end near
−2,000 EUR and would have ended near +6,100 without it); with worthless rules the stop costs about 31 % of the money
paid in, not 25 %; a good year followed by worthless rules gives the year's gain back; the robot's own gain stays more
than a year under its high in 27 % of FS paths at half edge (18 % for A05S); FS is ahead of a flat 1 % only for its
first six to nine months; hands 1.11 cannot run FS as simulated (no risk schedule, a daily lock in % of the balance
instead of stakes, no stop armed by the money paid in); on 1,000 EUR a 1 % stake cannot place 54 % of the signals at
FP's minimum lots (22 % at 2 %, 1.3 % at 5 %). A run of four losing weeks or more happens in 53 to 61 % of three-year
paths for a flat 1 %, FS and A05S alike (62 to 68 % at 0.25 %): the size of the stake changes what such a run costs
(the worst one after the first year: 21 to 24 % of the account at 1 %, 11 to 13 % for FS and A05S, 6 % at 0.25 %), not how
often it comes.

### Addendum G — sixth clarification (2026-11-12), written BEFORE the run: how fast a start, on one ladder
The user's words stay the rule: "a very fast growth at the start that calms down", "I cannot lose 50 % and wait a year".
FS breaks the second in its first three months and A05S breaks the first. Declared now, before any run (nothing else
will be run): the same plan with a slower start, so that the speed of the start is the only thing that changes.
- **F3:** 3 % under 3,000 EUR, 2 % under 6,000, 1 % under 12,000, then 0.5 %. **F2:** 2 % under 6,000, 1 % under 12,000,
  then 0.5 %. **F1:** 1 % under 12,000, then 0.5 %. Thresholds read on the larger of the balance and the money paid in,
  as F. **F3S, F2S, F1S:** the same with the stop of FS (−25 % of the reference capital, armed once 12,000 EUR are paid
  in). The ladder shown is A05S, F1S, F2S, F3S, FS (a start at 0.5, 1, 2, 3 and 5 %).
- **Measure corrected:** the highest balance "as seen" counts the starting 1,000 EUR (the defect found by the review).
- **Measures added on every path, all at week ends:** the deepest fall from the high (payments set aside) of the first
  13 weeks and of the first 52 weeks, as a share and in euros; the number of runs of four losing weeks or more; what the
  worst such run costs (loss of the run over the balance at its start), over the three years and among the runs that
  start after the twelfth month. Reported as shares of paths: a fall of 50 %, 30 % and 25 % or more; the robot's own
  gain more than 52 weeks under its high; the balance as seen more than 26 and more than 52 weeks under its high; at
  least one run of four losing weeks.
- **What "best" means on this ladder, fixed here from the user's words:** a plan qualifies when a fall of 50 % or more
  from the high (payments set aside, any time in the three years) happens in at most one path in twenty, both on paper
  and at half edge. Among the plans that qualify, the one with the highest median gain after 12 months at half edge is
  shown first; the rest of the ladder is shown beside it. With worthless rules every plan loses: what is shown there is
  the loss when the stop fires.
- **To be said with it:** this is sizing on simulations of the validation years, not a selection study; the earlier
  plans must come out unchanged apart from the corrected measure; no sizing changes how long the robot's own gain
  stays under its high, nor how often losing runs come.

### Addendum G — seventh clarification (2026-11-12), written BEFORE the run: a monthly check before the stop is armed
The user asked what would make us cut the robot ("if I lose too much: how much in euros? I leave it to you"). From the
twelfth payment on, the answer is the stop of the plan (−25 % of the reference capital). Before that, nothing stops a
robot whose rules are worthless. Declared now, before any run, for the five plans of the ladder (same engine, same
draws, nothing else will be run):
- **The figure looked at:** at each month end m = 1..11, the robot's gain G(m) = balance minus money paid in.
- **Orange line:** the 10th percentile of G(m) over the 2,000 half-edge paths. **Red line:** the q-th percentile of G(m)
  over the same paths, the same q every month, q being the largest value (on a grid of 0.1 %) for which at most 5 % of
  the half-edge paths are below the red line at one month end or more among months 1 to 11. **Rule tested:** the robot
  is stopped for good at the first month end where its gain is below the red line, and nothing more is paid in.
- **Reported, per plan:** q and the red line month by month; in each scenario (paper, without 2024, half, quarter,
  covers its costs, worthless) the share of paths cut and the median month of the cut; the gain or loss after 36
  months with and without the rule (median and one path in ten), the stop of the plan staying in place in both; what
  the half-edge paths that are cut would have earned without the rule.
- **What decides whether the rule is offered to the user, fixed here:** it is offered only if, for the plan he chooses,
  it cuts at least half of the worthless robots before month 9 AND lowers the median loss with worthless rules by at
  least 500 EUR (false cuts at half edge are at most 5 % by construction). Otherwise the result is: "the stop at the
  twelfth payment is the rule; nothing earlier tells a worthless robot from bad luck", and the two lines are shown as
  information only.
- The red line is calibrated and tested on the same paths; the false-cut rate is therefore checked on other draws
  (seed + 2), and reported as measured there.

### Addendum G — outcome of the seventh clarification (2026-11-12, `results/r2/stake/control.json`)
By the rule fixed before the run the monthly check is **not offered**: for every plan of the ladder it cuts fewer than
half of the worthless robots before month 9 (26 % for A05S, 39 % F1S, 45 % F2S, 47 % F3S and FS). What it would do for
F2S, for the record: red line at the 0.7th percentile of the half-edge paths (−300 EUR after one month, −1,060 after
three, −2,000 after six, −2,300 after nine, −3,000 after eleven); worthless rules: 59 % of paths cut, median month 6,
median loss −2,480 instead of −3,600; rules that cover their costs: 25 % cut; half edge: 4.7 % cut (6.5 % on the other
draws), and those paths would have ended at +8,600 (median) without the rule; paper: 0.7 %. Result as declared: the
stop at the twelfth payment is the rule; nothing earlier tells a worthless robot from bad luck well enough; the two
lines may be shown as information.

### Addendum G — eighth clarification (2026-11-12), written BEFORE the run: fewer losing weeks once the account is large enough
The user: "the worst is consecutive losses; it is inadmissible". Sizing by the size of the account does not change how
often losing weeks come (sixth clarification: a run of four losing weeks in 53 to 61 % of three-year paths whatever the
plan). The only validated lever on their frequency is in Addendum E: the frozen stake profiles `soft` and `strong`, which
raise the stake inside a week that starts badly (up to 3× on the crypto rules for soft; up to 5× on crypto and 3× on
us100 for strong) and lower it once the week is ahead; their base stake is 0.58 and 0.39 of the reference's so that the
worst week stays the same. On 2022–2025 they gave 73 % and 77 % of winning weeks against 70 % for the adopted cushion
rule (53 % at an equal stake), for 84 % and 76 % of the profit; they failed on a 1,000 EUR account (minimum lots) and
were described as "from about 20,000 EUR". Declared now, before any run (nothing else will be run):
- **F2S+soft, F2S+strong:** plan F2S; at the start of each server week, if the balance is at least 20,000 EUR, the week
  is traded with the frozen profile (its catch-up and cushion parameters; the risk per trade of the schedule
  multiplied by its base scale, 0.58 or 0.39); otherwise with the cushion rule, as now. The stop of F2S is unchanged.
- **Measures added on every path:** after the twelfth month, the share of winning weeks (among weeks with a result)
  and the worst week (its loss over the balance at its start). The share of paths with a run of four losing weeks
  that starts after the twelfth month is already reported.
- **Reported against F2S, in the six scenarios:** gains at 12 and 36 months, falls, the losing runs after the twelfth
  month (share of paths, cost), winning weeks and worst week after the twelfth month, share stopped, share of paths
  with a fall of 50 % or more.
- **What decides whether it is offered, fixed here:** offered as an option (not as the default) if, at half edge, the
  share of paths with a run of four losing weeks starting after the twelfth month falls by at least a third, the
  median gain after 36 months stays at or above 75 % of F2S's, and the fall after the twelfth month (one path in ten)
  does not exceed F2S's by more than a quarter. The price is said with it, as the reviewer of Addendum E required: these
  profiles do not lower the risk, they move it from the number of losing weeks to their size, and with no edge they
  raise the chance of a deep loss.

### Addendum G — outcome of the sixth clarification (2026-11-12, `results/r2/stake/growth.json`; review pending)
The earlier plans come out unchanged apart from the corrected measure (560,544 cells compared with the previous file:
only the fall of the balance "as seen" differs). The ladder at half edge, median (one path in ten):

| First risk per trade | Gain at 12 months | Gain at 36 months | Deepest fall of the first 13 weeks | Fall of 50 % or more (paper / half edge) | Stopped | Worthless rules: loss, paid in, month of the stop |
|---|---|---|---|---|---|---|
| 0.5 % (A05S) | +1,245 (−396) | +14,617 (+2,544) | 3.7 % (6.5 %), 100 EUR (194) | 0 % / 0 % | 4.2 % | −4,503, 22,000, 20 |
| 1 % (F1S) | +2,644 (−584) | +16,257 (+2,180) | 8.7 % (15.3 %), 241 EUR (446) | 0 % / 0 % | 7.2 % | −3,564, 14,000, 13 |
| 2 % (F2S) | +3,242 (−681) | +16,987 (+2,132) | 19.5 % (31.3 %), 552 EUR (964) | 0 % / 0.4 % | 8.2 % | −3,605, 12,000, 11 |
| 3 % (F3S) | +3,251 (−616) | +17,262 (+2,106) | 26.9 % (40.5 %), 693 EUR (1,157) | 0.7 % / 2.5 % | 8.2 % | −3,605, 12,000, 11 |
| 5 % (FS) | +3,358 (−746) | +17,228 (+2,171) | 41.3 % (59.1 %), 984 EUR (1,591) | 12.2 % / 23.7 % | 8.5 % | −3,663, 12,000, 11 |

On paper the 12-month gains are +2,489, +4,874, +5,988, +6,184 and +6,474.
- **By the rule fixed before the run, F3S comes first**: it qualifies (a fall of 50 % or more in 0.7 % and 2.5 % of
  paths) and has the highest median gain after 12 months at half edge among the plans that qualify. FS does not
  qualify.
- **Tie-break added AFTER the run, declared as such:** F2S is 9 EUR behind F3S on that median (+3,242 against +3,251),
  far inside the noise of 2,000 paths, with a first-quarter fall of 20 % / 31 % instead of 27 % / 41 % and a fall of
  50 % or more in 0.4 % of paths instead of 2.5 %. Among the qualifying plans whose 12-month median is within 5 % of the
  best, the plan shown as the advice is the one with the smallest typical fall of the first 13 weeks: **F2S** (2 % under
  6,000 EUR, 1 % under 12,000, then 0.5 %; stop at −25 % armed once 12,000 EUR are paid in). F3S and FS are shown beside it.
- **What the start does not change:** after the twelfth month every plan trades the same 0.5 % (deepest fall 15 to 16 %,
  one path in ten 21 to 24 %); the robot's own gain stays more than 52 weeks under its high in 18 to 27 % of paths at
  half edge (0.2 to 1.1 % on paper); a run of four losing weeks or more comes in 57 to 61 % of paths; with worthless
  rules the loss is about 3,600 EUR however fast the start, because the stop fires when it is armed.
- A start above 2 % buys almost nothing: +9 EUR (3 %) and +116 EUR (5 %) on the 12-month median at half edge, +196 and
  +486 on paper, for a first-quarter fall that goes from 20 % to 27 % and 41 %.

### Addendum G — diagnostic of 2026-11-12: what "double in a month" asks of the ten rules (`results/r2/stake/x2/x2.json`)
The user: "when I say fast, it is ×2 every month at the start, with losses of 10 %, perhaps 20 %". Not a plan, a measure:
flat risk per trade on 1,000 EUR, the first four weeks, 2,000 resampled paths of the validation trades. On paper the
typical month peaks at +12 % for a 5 % stake (a fall of 20 % or more in 58 % of months) and turns negative beyond 7.5 %;
the chance of doubling never exceeds 19 % (at 15 %, where the account loses half or more in 69 % of months); at half edge
it never exceeds 12 %. With the edge of every rule multiplied by f at unchanged noise (`x2b`, 1,000 paths), a typical
month reaches about +100 % with a fall of 20 % or more in under one month in ten only from f = 4 to 5 (stake 4 %): the
trades must earn about 0.35 R on average instead of 0.08. Sizing cannot close that gap; only better trades can.

## Addendum H (2026-11-12; written BEFORE any run): "understand the losses" — in sample only
The user: "understand the losses and correct them to turn them into gains; as a human I cut at once a trade that goes
hard the wrong way and I let run the one that goes well; the algorithm must adapt; do not stop where the others stop".
A study of the trades themselves, on the ten frozen sleeves, **in sample only** (entries before 2022-01-01; price frames
cut at 2021-12-31 before anything else; no 2022+ row is read, simulated or looked at). Six lenses, each with its own
directory under `r2/tracks/autopsy/` and `results/r2/autopsy/`, each logging every variant it simulates:
- **path** — what a trade shows after its entry: adverse and favourable excursions, the expectancy of the rest of a trade
  given its state after a given time; rules that cut early or exit on no progress (at most 12 variants per sleeve).
- **payoff** — the shape of the bet: stop distance at constant money risk, trailing exits and longer holds for winners,
  break-even (at most 14 variants per sleeve).
- **context** — when the signals lose: causal descriptors at the decision; filters and two-level stakes judged only on
  walk-forward years inside the sample (at most 10 filters and one regularised model per sleeve).
- **cluster** — losses that come together and adaptive rules at the level of the portfolio: one position per market and
  direction, pauses after losses, weights by trailing results, a daily lock (at most 30 variants).
- **breadth** — the frozen rules, unchanged, on instruments never tried, after an inventory of what the earlier tracks
  already tried (each rule × instrument pair is one trial).
- **entry** (added at the launch, before any of its simulations) — getting in better: the path of the price right after
  the signal; limit entries on a pullback, entries delayed until a close in the trade's direction, entries in two
  halves, a retest entry for the two gold stop-entry sleeves (their buffers are not retuned); filled and missed signals
  are both reported (at most 12 variants per sleeve).
- **What makes a candidate, fixed here:** for its sleeve (for the portfolio in `cluster`), net of FP costs: expectancy per
  trade up by at least 20 %, or average loss down by at least 20 % at an expectancy at least equal; total R not lower;
  the improvement has the same sign in at least 3 of the 4 years 2018–2021; it holds with costs × 1.5; the neighbouring
  parameter values improve too; it is causal (truncation test). For `breadth`: profit factor ≥ 1.15, positive in at
  least 3 years of 4, positive with costs × 1.5, unchanged parameters.
- **Every candidate is attacked by an independent re-implementation** written from its specification, before it is
  kept. At most one change per sleeve is carried forward.
- **No validation look in this addendum.** If candidates survive, the look at 2022–2025 is declared separately, once,
  with its criteria, before it is run. The 2026 holdout stays untouched.
- **To be said with any result:** improvements found by looking at the same in-sample trades that built the rules are
  optimistic by construction; the measure that counts is the validation look, and then the demo account.

### Addendum H — clarification (2026-11-12, 13:15 UTC), written BEFORE these runs: gain per unit of swing
The payoff lens ranked its qualifiers by expectancy with costs × 1.5, as declared. That ranking favours a larger position
(a tighter stop at the same money risk) or a longer exposure (a longer hold): both raise R per trade and the swings
alike. What the user asks, fast growth with small falls, depends on the gain per unit of swing. A supplementary round
therefore attacks, with the same attack text, each sleeve's qualifier of rank 1 by the lens's own per-trade Sharpe
ranking (`rank_by_sharpe_info_only` in `results/r2/autopsy/payoff/candidates.json`, reported by the lens as information
before any attack) where that qualifier was not attacked already: ocm4 T1, nq_btc_follow T1, donch4h_stop S0.75r,
brk72_24h_wd btcusd S0.75r, orb_asia_2d_buf10 S0.75r, noise30 S0.25. This ranking was made the selection rule after the
lens's table was seen: post hoc, and said so; each attacker counts the sleeve's variants of the lens as the selection
family. Besides the Addendum H criteria, each verdict reports the change in the sleeve's weekly Sharpe and in the
portfolio's weekly Sharpe at equal weekly volatility (2018-02 to 2021-12, FP costs and × 1.5). In sample only; no
validation look; the rule "at most one change per sleeve" still holds.

### Addendum G — outcome of the eighth clarification (2026-11-12, `results/r2/stake/growth.json`)
The extended engine reproduces every earlier cell (691,872 compared, none different). At half edge, F2S / F2S+soft /
F2S+strong (the profile switched on at the start of a server week whose opening balance is at least 20,000 EUR):
- a run of four losing weeks starting after the twelfth month: 41.2 % / 42.6 % / 15.2 % of paths; winning weeks after the
  twelfth month 62.9 % / 67.6 % / 72.4 %; worst week after the twelfth month 6.0 % / 6.8 % / 7.8 % of the account (one path
  in ten 6.4 / 7.2 / 8.1 %); median gain after 36 months +16,987 / +17,368 / +17,528; fall after the twelfth month, one
  path in ten, 23.3 / 23.9 / 21.9 %; stopped 8.2 / 8.6 / 6.2 %.
- on paper: runs after the twelfth month 38.5 / 32.5 / 8.7 %; winning weeks 67.6 / 73.3 / 77.1 %; median gain after 36
  months +43,793 / +37,574 / +32,704 (the strong profile earns a quarter less); with rules that cover their costs
  −1,968 / −947 / +175; worthless −3,605 / −3,548 / −3,505.
- By the rule fixed before the run, **F2S+strong is offered as an option** (runs down by 63 %, gain 103 % of F2S's,
  fall one path in ten lower); **F2S+soft is not** (it does not make the runs rarer). To be said with it: the option
  turns on only from 20,000 EUR (in the median half-edge path, after about 15 months); it makes losing weeks rarer by
  making the remaining ones larger (worst week 7.8 % instead of 6.0 %); on paper it costs a quarter of the gain; the
  hands 1.11 cannot run it (catch-up multipliers up to 5 within the week).

### Addendum G — outcome of the review of the sixth clarification (2026-11-12, `results/r2/stake/growth_sixth_review.json`)
An independent re-implementation from the text equals the lab's engine bit for bit (15,072,000 week-end balances) and
every published cell of the ladder once six conventions the text leaves open are aligned (168,087 cells compared): when
the stop is read, positions open at a stop, the worst-run cost on a path without a run (the lab counts 0), weeks without
a result after month 12, the month of a stop, the first-reach median. Over 21 other draws (7 seeds × blocks of 4, 8 and
16 weeks) the order of the plans on the 12-month median holds. **What was told to the user was too favourable**: the
gains quoted were the half-edge medians without saying so; the falls quoted covered the first 13 weeks only (first year
at half edge: −24 % typical, −38 % one path in ten for F2S); "less than 1 path in 100 loses half" fails when the robot
only covers its costs (1 in 50) or is worthless (1 in 9); runs of four losing weeks (one path in four in the first year)
were not said; the hands 1.11 cannot run the schedule nor this stop. By the rule fixed before the run F3S is first
(+9 EUR at 12 months at half edge, standard error 40 EUR: F3S wins 65 % of resampled path sets); F2S came from the
tie-break added after the run. No plan of the file dominates F2S; **F1S** (1 % under 12,000 EUR, then ½ %) answers the
user's "losses of 10 %, perhaps 20 %" better (first-year fall 17 % typical, 26 % one path in ten; a fall of 30 % or more
in 3 % of half-edge paths against 30 %; 18 % less gain in the first year, 4 % less after three years). Correction sent to
the user with both plans side by side (`results/r2/stake/images/12_depart_1_ou_2.png`, `r2/tracks/stake/start_choice_chart.py`);
the choice between 1 % and 2 % is put to him.

## Addendum I (2026-11-12, 14:00 UTC; written BEFORE any run): gain per unit of swing — bet more where the odds are better
The user, again: "do not stop until you find it; carte blanche"; as a human he "lets run the trade that has chances and
cuts the one that has none". Addendum H judged changes by expectancy per trade with the total R not lower. For the
user's aim (fast growth with small falls) the measure that counts is the gain per unit of swing of the whole account,
because the stake can then be raised until the swings are as large as before. Removing trades that earn nothing, or
staking more where the odds are better, can raise that measure while lowering the total at a constant stake: Addendum H
could not see it. The context lens found strong, monotone, every-year differences inside the sleeves (crypto breakouts
taken just after their volatility unit expanded, against the 20-day move, or far from the 20-day extreme earn a small
fraction of the others; clock effects on noise30 and nq_btc_follow; trades taken while another sleeve holds the same side
of the same market earn more), but these weak contexts are less profitable rather than losing, so skip rules failed.
**In sample only** (entries before 2022-01-01, frames cut while read; nothing 2022+ is read, simulated or looked at).
Three lenses, each with its own directories `r2/tracks/sizing/<lens>/` and `results/r2/sizing/<lens>/`:
- **conviction** — a stake per trade from causal descriptors known at the decision (those of the context lens, and
  "agreement": another sleeve already holds the same side of the same market): stakes of 0, 0.5, 1, 1.5 or 2 times the
  base by terciles of one descriptor or of a regularised score; at most 30 variants.
- **clock** — stakes or skips by hour of the decision and weekday (New York clock), per sleeve; at most 15 variants.
- **weights** — one stake per sleeve from walk-forward estimates of its mean and variance, shrunk toward equal stakes;
  a sleeve set to zero while its trailing two-year expectancy is not positive; at most 15 variants.
- **Walk-forward only**: every threshold, tercile, score or weight is fitted on the years before (expanding window, at
  least 7 days of purge) and applied to the next year. The out-of-fold years are 2019, 2020 and 2021 for every sleeve
  (earlier out-of-fold years where a frame allows are reported apart and judge nothing).
- **What makes a candidate, fixed here** (the portfolio of the ten sleeves, FP costs, the stakes of the variant scaled
  so that the weekly standard deviation of the portfolio's R equals the reference's on the out-of-fold years): (a) the
  weekly Sharpe (mean / standard deviation of weekly sums of R booked at the exit, every calendar week counted, × √52)
  is up by at least 10 % over 2019–2021 pooled; (b) it is up in at least 2 of the 3 out-of-fold years; (c) it holds with
  costs × 1.5; (d) the neighbouring parameter values improve too; (e) it is causal (truncation test); (f) stakes stay
  between 0 and 2 times the base and a variant fits at most 3 parameters per sleeve. Reported beside it for the user:
  losing trades per month, share of losing weeks, worst week and longest run of losing weeks at equal weekly swing.
- **Every candidate is attacked by an independent re-implementation** before it is kept (selection counted). A final
  synthesis combines what survives with what survives of Addendum H, compares the portfolio with the unchanged one on
  the same measures, and writes the text of ONE look at 2022–2025 covering every kept change of H and I, to be declared
  before it is run. The 2026 holdout stays untouched.
- **To be said with any result**: found on the years that built the rules, so optimistic; the measure that counts is the
  validation look, then the demo account. Stakes below the broker's minimum lot are skipped on a small account (Addendum E).

### Addendum I — outcome (2026-11-12, `results/r2/sizing/synthesis.json`, `results/r2/sizing/workflow_result.json`)
**No stake rule survives.** On the out-of-fold years 2019–2021, FP costs, plain sum of the ten chains at equal weekly
swing (reference: 3,985 trades, weekly Sharpe 2.747, +556.2 R, 44.6 % losing weeks, worst week −12.5 R):
- **clock** (9 declared rules): ×0.933 to ×1.000; stakes chosen with perfect hindsight of each year reach ×1.18 (hour
  bands) and ×1.38 (weekdays), below the median of the same bound on shuffled labels (×1.22, ×1.41): no structure beyond
  noise.
- **weights** (15 variants): mean/variance ×0.938–0.985; inverse volatility ×1.007–1.059 with 2019 down at every
  shrinkage; switching a sleeve off on a non-positive trailing expectancy ×0.959–0.990; rank weights ×0.919–0.981.
- **conviction** (30 variants): per-sleeve descriptor terciles ×0.942–1.047 (on the six non-crypto sleeves every rule
  lowered the total); "agreement" stakes ×0.952–0.997 (the cluster lens's +0.24 against +0.14 R does not hold out of
  fold); the best, a pooled ridge score on the four crypto breakouts (V05), ×1.095 (2019 ×1.006, 2020 ×1.047, 2021
  ×1.339; the earlier 2018 fold ×0.944; on a 1,000 EUR account run as the live program would, ×0.954): below the ×1.10
  bar, verdict weakened, dropped. Nothing of Addendum I enters the look. Measured the same way, Addendum H's kept set
  (K1 + K2 + K3) gives ×1.123 in sample, mostly from 2019, with a deeper worst week (−14.0 against −12.5 R).
Lesson recorded for the user: staking by the odds, by the clock or by sleeve does not raise the gain per unit of swing
on these rules; the remaining gap to the user's demand (about ×4.4) is untouched by Addenda H and I.

## Addendum J (2026-11-12, 16:00 UTC; written BEFORE any run): round 4 — new rules on markets and clocks the ten do not cover
The user: "do not stop until you find it; carte blanche". Addenda H and I found that the ten rules cannot be made much
better: losses are full stops that cannot be sorted early, and stakes by the odds, the clock or the sleeve do not raise
the gain per unit of swing. The only lever left is breadth: new rules that are independent of the ten. An archivist
listed what the lab already tried (about 2,300 logged configurations, 3 independent clusters found), three idea teams
proposed 24 hypotheses, and a judge ranked them (`results/r2/round4_ideas.json`, sha256 `c81387985baf8e43d64caa339c75daf4d3ff936a925ef28d97ff94755b5e225a`, read only from files
the earlier tracks wrote; no data was run). Five are tested, each exactly as the judge's `rule` and `test_plan` texts in
that file say, which are frozen here:
1. **IDXRS_1000** — relative strength between us100, us500 and us30 from 10:00 to 15:55 New York, a hedged pair
   (12 configurations; prior of passing validation 8.8 %).
2. **FX weekend overreaction fade**, eight G10 pairs as one basket, decided Sunday 20:00 New York, out Monday 16:00
   (11 configurations; 2.8 %).
3. **ger40_noise30_xetra** — the frozen noise30 rule on the DAX's own cash clock (11 configurations; 3.3 %; also needs a
   weekly correlation of at most 0.30 with the sum of the ten over 2014–2021).
4. **FOMC-cycle even/odd weeks**, long-short us500, ger40 as a declared mechanism check (10 configurations; 1.5 %).
5. **LETF_CLOSE_PAIR** — us100 against us30 in the last half hour of big days (11 configurations; 1.6 %; both exit
   neighbours must keep PF ≥ 1.06).
- **In sample only** (2013–2021, frames cut while read). The verdict is read on each main configuration only; the
  others are its neighbours, its cost stress and its random-entry null. Pass = PROTOCOL_V3 section 4 bars (the basket
  bars for the FX basket), plus the extra condition the judge declared for each.
- **Every in-sample pass is attacked by an independent re-implementation** before it is kept. A kept rule gets ONE look
  at 2022–2025, declared separately before it is run.
- **Said before the run** (the judge's arithmetic): about 0.18 of the five are expected to pass validation (none: about
  83 %); if one passes with a forward Sharpe of about 0.6 and a low correlation, the account's weekly Sharpe (2.02 on
  2022–2025) rises by 2–4 %; the user's demand needs about ×4.4, which breadth from this pool cannot reach.

### Addendum J — outcome (2026-11-12, `results/r2/round4/synthesis.json`)
**None of the five passes in sample, so nothing is attacked, nothing is kept and no look at 2022–2025 is declared.**
55 configurations logged (12 + 11 + 11 + 10 + 11), each declared in its `declared.json` before its run. The lead analyst
recomputed every verdict from the engineers' files and got the same figures.
- **IDXRS_1000** fails one bar: t 2.15 against 2.5 (518 pairs, PF 1.288, +0.084 R per pair, 7/8 years, null
  percentile 100, PF 1.22 at costs ×1.5). Before costs t 3.10 (+6.1 bp per pair); FP costs of 1.6 bp take it under.
  2020 gives +19.7 of its +43.7 R (without 2020, t 1.29). Its neighbours with t ≥ 2.5 cannot replace it (selection).
- **FX weekend fade**: PF 0.870, no gross edge (−0.19 bp per trade before costs). **ger40 on the Xetra clock**: PF
  1.027, t 0.37 (+0.66 bp gross against about 0.96 bp of cost). **FOMC even/odd weeks**: PF 0.977, the published effect
  is absent (−5 bp a week, t −0.24). **LETF close pair**: PF 0.755, loses in 7 of 8 years.
- Information only: even at its in-sample face value, IDXRS_1000 would have moved the ten's weekly Sharpe from 2.51 to
  2.53 (+0.8 %). The account stays the ten rules. The 2026 holdout was not touched.

### Addendum H — declaration of the single look at 2022–2025 (2026-11-12, 19:07 UTC), written BEFORE it is run
Track `autopsy_HI_look`. Spec `lab/r2/tracks/validation_hi/look_spec.json`, sha256
`b71f69d59999bdb97442bf0a1beff9a8512b883396886323426e69e55e277960` (the exact bytes that run). Harness
`lab/r2/tracks/validation_hi/`: every proof passes (`results/r2/validation_hi/proofs.json`: 13 proofs, 3,344 checks, 0 failed, at the in-sample CUT 2022-01-01).
Two independent rechecks (`results/r2/validation_hi/harness_final_recheck.json`, `harness_last_recheck.json`) found
no way for the look to read 2026 data, a holdout path or a declaration other than this protocol; their last two
hardening items were done by the lead and proven (`harness_lead_last_fix.json`): the protocol's identity is pinned
before the path rule, and the look runs only if this text equals the protocol committed at HEAD. Command, run ONCE:
`LOOK_DECLARED=/home/user/gold-orb/lab/PROTOCOL_V3.md NUMBA_CACHE_DIR=/tmp/numba_validation_hi PYTHONDONTWRITEBYTECODE=1 python3 /home/user/gold-orb/lab/r2/tracks/validation_hi/look.py --spec /home/user/gold-orb/lab/r2/tracks/validation_hi/look_spec.json --cut 2026-01-01`.
Trades entered 2022-01-01 to 2025-12-31. The 2026 holdout stays untouched: the guard refuses any read at or after
2026-01-01 and any holdout path. The single access line with track `autopsy_HI_look`, written to
`results/val_access.log` before anything is read, replaces the per-read logging that both syntheses named (synthesis
A: `goldlab.split.cut` with track `autopsy_synthesis_A`; synthesis B: track `autopsy_synthesis_B`).
- **Eight changes are judged, nothing else.** From synthesis B: **K1** (brk72_24h_wd ethusd skips a signal when its
  risk in bp is at or above T(Y), refitted every 1 January; T(2022) = 478.284 bp, skip side 'hi', 2,345 training
  signals, binding); **K2** and **K3** (the frozen gold rule orb_asia_2d_buf10 as a new sleeve on ethusd and on btcusd).
  From synthesis A: **ocm4 us100 T1**, **F1_brk_ridge_filter ethusd H2**, **brk72_24h_wd btcusd S0.75r**,
  **donch4h_stop xauusd S0.75r**, **orb_asia_2d_buf10 xauusd S0.75r**, at their frozen equal-swing factors 0.682408,
  0.750978, 0.771793, 0.885978, 0.764081. They run through the payoff lens's `variants.py`, which has the same logic as
  synthesis A's frozen functions in `synth.py` (checked by the recheck). No stake rule (Addendum I kept none) and no
  plugin.
- **Criteria**, as written in the spec. K1: with the skip, the sleeve's expectancy per trade is higher and its total R
  is not lower, with FP costs and with costs ×1.5, and the skipped signals taken alone earn less on average than the
  kept ones. K2 and K3, each: with FP costs PF ≥ 1.06, expectancy > 0, every-signal expectancy > 0, total R positive
  in at least 3 of the 4 years, expectancy > 0 with costs ×1.5, and the weekly mean / sd of the ten plus the sleeve at
  least that of the ten alone (the robot-as-is reading, entry one minute late and close-all on Friday 16:50 New York,
  is reported beside it: if it is ≤ 0, the sleeve waits for a robot that holds over the weekend). Synthesis A's five,
  each: V1 the sleeve's weekly Sharpe is higher with the change AND the ten-sleeve weekly Sharpe with the change at its
  frozen factor is higher (FP); V2 total R at a constant stake not lower (FP); V3 V1 and V2 also with costs ×1.5; V4 the
  equal-swing gain positive in at least 3 of the 4 entry years (FP); V5 expectancy > 0 and PF ≥ 1.06 (FP).
- **Check first**: the ten unchanged sleeves rebuilt by the harness must equal the official 2022–2025 trades (count,
  total R, trade by trade). In the harness it gates synthesis A's five only. Declared here, stricter: if it fails,
  nothing at all is adopted from this look (K1–K3's mechanical verdicts are recorded but not acted on); the failure is
  reported to the user and investigated.
- **Declared choices**: K1 labels with FP costs in both cost modes; live semantics 'entry_bar' with the Friday block on
  the decision and the entry; accounts judged on the plain sum; FP server weeks; synthesis B's convention for the ten,
  the payoff lens's for synthesis A's five.
- **Multiple testing, said before the run**: the eight changes were picked from about 845 in-sample variants (synthesis
  A: about 360 lens variants plus a post-hoc ranking; synthesis B: 330 + 29 + 126 lens trials). Synthesis A expected a
  gain of about zero for its five (verdicts weakened; on 2013–2017 they left the weekly Sharpe unchanged). A pass here
  is therefore weaker evidence than it reads; even with no real effect, some of the eight may pass by chance.
- **What follows**: a change that passes goes to the demo account first, never straight to real money; a change that
  fails is dropped for good; nothing is re-tuned after the look. The result is reported to the user whatever it is.

### Addendum H — outcome of the single look (2026-11-12, `results/r2/validation_hi/look/autopsy_HI_look__cut2026-01-01.json`)
Run once at 19:06 UTC with the declared command: one access line in `results/val_access.log`, the text judged is the
protocol committed at HEAD (sha256 `676fdfb1…`), synthesis A's frozen files checked before the access, every read
bounded at 2026-01-01, no holdout path. **Check first PASSED**: the ten unchanged sleeves rebuilt by the harness equal
the official 2022–2025 trades. Trades entered 2022–2025, FP costs:
- **Kept, 3 of 8.** **K1** (brk72_24h_wd ethusd skips the widest-risk signals): expectancy 0.063 → 0.080 R per trade,
  total 34.3 → 39.2 R; with costs ×1.5 0.030 → 0.044 R; the skipped signals taken alone −0.20 R against +0.13 R for the
  kept ones; account weekly Sharpe 2.016 → 2.047. **F1_brk_ridge_filter ethusd H2** (winners held two more days): sleeve
  weekly Sharpe 0.57 → 0.83, ten-sleeve weekly Sharpe at its frozen factor 2.016 → 2.066, V1–V5 all pass.
  **brk72_24h_wd btcusd S0.75r** (stop at 0.75 × the distance, same money risk): sleeve 0.52 → 0.85, ten-sleeve 2.016 →
  2.119, V1–V5 all pass. Synthesis A's two together, at equal swing: 2.016 → 2.169 (costs ×1.5: 1.564 → 1.753), total
  428.9 → 461.7 R.
- **Rejected, 5 of 8, dropped for good.** **K2** (the gold Asia breakout on ethusd): PF 0.93, −0.048 R per trade, 1 year
  of 4 positive. **K3** (the same on btcusd): PF 1.25, +0.165 R per trade, but 2 years of 4 positive and the account less
  regular (2.016 → 1.920). **ocm4 T1**: sleeve weekly Sharpe 1.22 → 0.69. **donch4h S0.75r**: 1.01 → 0.84. **orb gold
  S0.75r**: 0.76 → 0.71.
- **What it means.** The three kept changes are all on crypto sleeves. They were picked from about 845 in-sample
  variants, so a pass is weaker evidence than it reads (said before the run). As declared, they go to the demo account
  first, never straight to real money. The two families were not measured together by this look and no new measure is
  made on these years. Whatever their sum, it is a few percent on a weekly Sharpe of about 2.0, against about 8.9 for
  the user's demand. The 2026 holdout was not touched.

### Addendum G — the user's choice of start (2026-11-12, evening): "the one that earns the most"
Asked to choose between the 1 % start (F1S) and the 2 % start (F2S), the user answered: "je veux celui qui gagne le plus".
On `results/r2/stake/growth.json` the start that earns the most is **F3S** (3 % per trade below 3,000 EUR, 2 % below
6,000, 1 % below 12,000, then 0.5 %, read on the larger of the balance and the money paid in; the −25 % stop armed once
12,000 EUR are paid in): highest or tied-highest median gain in every case (3 years: paper +44,259, half +17,262, quarter
+6,473, covers costs −2,057, worthless −3,605 EUR), and the winner of the rule fixed before the sixth clarification's run.
The 5 % start (FS) earns no more (half: +17,228 EUR in 3 years) and loses half the account in 23.7 % of half-edge paths.
Told to the user with the choice: F3S's first-year fall is 29 % typical (1,840 EUR) and 42 % one path in ten, above the
10–20 % he first named; losing half within 3 years happens in 2.5 % of half-edge paths and 21.9 % if the rules are
worthless; the 2 % start earns almost the same (−275 EUR over 3 years at half edge) with fewer deep falls. F3S becomes
the stake plan of the robot unless the user changes it. A user decision, not a test: nothing was run.

### Addendum G — the user's second choice of start (2026-11-13): speed first, the risk of losing everything accepted
The user: "le meilleur robot ; au début je me fiche du risque de tout perdre ; je veux aller très vite ; c'est la seule
chose qui compte". Among the plans already simulated in `results/r2/stake/growth.json` (nothing new was run), the one
that reaches 10,000 EUR soonest without going to zero is **D2**: 10 % per trade below 3,000 EUR, 5 % below 10,000, 2 %
below 20,000, then 1 %, read on the larger of the balance and the money paid in, no plan stop. Paper / half edge:
10,000 EUR reached at month 5 / 8 (median), before month 6 in 64 % / 38 % of paths; gain after 1 year +20,151 / +9,440
EUR (covers costs −3,637, worthless −7,235), after 3 years +179,696 / +43,460 EUR (covers costs −4,695, worthless
−19,046) for 36,000 EUR paid in; a fall of 50 % or more in 73.2 % / 88.3 % of paths, typical first-year fall 65 % / 76 %.
E (20 % at the start) is not faster by month 6 (62 % / 37 %) and goes to zero in 18 % / 53 % of paths. Told to the user
with the choice: these are the validation years, so optimistic; the broker's margin on crypto is not in the simulation
and may refuse some trades at 10 %; with this plan the robot's −50 % disaster guard would stop it in most paths, so it is
switched off for this plan, as the user accepts the loss of the account. D2 replaces F3S as the robot's stake plan; F3S
stays available as an input. A user decision, not a test.

### Addendum G — ninth clarification (2026-11-13), written BEFORE the run: the gain for the risk, between 3 % and 10 %
The user, after choosing D2: "show me the best gain for the risk; if we reduce to 7-8 %, do we still gain a lot and
reduce the risk a lot?". One family of plans, declared before any run: **D2's shape scaled by its starting risk X** —
X % per trade below 3,000 EUR, X/2 % below 10,000, X/5 % below 20,000, X/10 % above, read on the larger of the balance
and the money paid in, no plan stop, no disaster guard — for **X = 3, 5, 6, 7, 8 and 10** (X = 10 is D2 itself, run again
as a check that the engine reproduces its stored cells exactly). Same engine (`r2/tracks/stake/growth.py`), same 2,000
resampled 3-year paths of the 2022–2025 trades, same cases (paper, without 2024, half, quarter, covers costs,
worthless), 1,000 EUR at the start and 1,000 EUR a month. Reported for each X, nothing chosen by the engine: months to
10,000 EUR (median; share of paths by months 4, 6 and 9), gain after 1 and 3 years (median and one path in ten), the
first-year fall (typical and one path in ten), the share of paths with a fall of 50 % or more, and the share that reach
zero. Every read is logged in `results/val_access.log` by the engine. Said with it: the validation years, so
optimistic; the broker's margin on crypto is not modelled; the user picks the X.

### Addendum G — outcome of the ninth clarification (2026-11-13, `results/r2/stake/growth_scaled.json`, `scaled_summary.json`)
The engine reproduces D2 exactly with S10 (20,994 numbers of the six cases, every path, 0 differences) and leaves every
other plan unchanged. Half of the paper edge (paper in brackets), X = 3 / 5 / 6 / 7 / 8 / 10 %:
- **10,000 EUR before month 6:** 15 / 31 / 35 / 38 / 40 / 41 % of paths (32 / 57 / 64 / 66 / 68 / 68 %); median month
  8 / 8 / 8 / 7 / 7 / 7 (7 / 6 / 6 / 6 / 5 / 5). By month 9 every smaller X gets there at least as often as 10 %.
- **Gain after 1 year (median):** +3,293 / +5,004 / +5,972 / +7,410 / +8,480 / +9,440 EUR (+6,515 / +11,076 / +13,050 /
  +14,934 / +16,626 / +20,151); one path in ten −841 / −2,047 / −2,728 / −3,454 / −4,131 / −5,614 EUR.
- **Fall of 50 % or more within 3 years:** 2.1 / 37.5 / 61.3 / 74.9 / 79.7 / 88.3 % (0.6 / 14.6 / 30.6 / 49.0 / 59.6 /
  73.2 %); typical first-year fall 30 / 46 / 54 / 61 / 67 / 76 %.
- **If the rules only cover their costs:** gain after 1 year 0 / −805 / −1,339 / −1,765 / −2,453 / −3,637 EUR.
Reading for the user, not a choice made by the lab: from 7 % to 10 % the speed to 10,000 EUR barely changes while the
risk of a 50 % fall and the loss in the weak cases grow; 5 % halves the risk of 7 % for about one month more. The
pictures are `results/r2/stake/images/15_gain_pour_le_risque.png`, `16_mois_pour_10000.png`, `17_compte_7_contre_10.png`
(independent review: 150 drawn numbers checked, 0 wrong; the worst cases were added).

## Addendum K (2026-11-14; written BEFORE any run): round 5 — one idea taken from the survey of public MQL5 robots
The user asked whether anything can be taken from the public MQL5 robots. The fact-checked survey
(`results/r2/mql5_survey.json`) found nothing credible near the user's demand and two ideas not covered by the ten
rules. The first is tested here; the second (night mean reversion on FX crosses) needs new data and is not tested now.
**Gold daily-reopen drift** (source: MQL5 Code Base 77060 'SessionReopenEA', backtest and research only, no live
signal), frozen now:
- Market XAUUSD, the lab's FP frames (M1 bid/ask), FP Raw costs (`r2/fp_costs.json`), stress at costs × 1.5.
- Sessions: the daily reopens of Monday to Thursday evenings, New York time (trading days Tuesday to Friday). Skip the
  Sunday weekly reopen, US holiday closures and early closes, and any evening with no gold quote between 18:00 and 18:15.
- Entry: buy at market on the first M1 bar at or after 18:15 New York. Stop: entry minus 2.0 × the mean (high − low) of
  the last 480 completed H1 bars (plain range, not ATR). No target. Exit at market on the first M1 bar at or after entry
  + 120 minutes. One trade per session, one position at a time, results in R.
- Neighbours (the budget, all logged): entry 18:10 and 18:30; hold 96 and 144 minutes; stop 1.6 and 2.4 — 7
  configurations with the main one.
- **In sample only (2013–2021), frames cut while read.** Pass = PROTOCOL_V2 section 4 bars on the main configuration:
  n ≥ 250, PF ≥ 1.12, t ≥ 2.5, ≥ 60 % of years positive, PF ≥ 1.04 at costs × 1.5, neighbours' median PF ≥ 1.06,
  every-signal expectancy > 0, random-time null ≥ 97.5th percentile; plus a weekly correlation with the sum of the ten
  of at most 0.30. A pass is attacked by an independent re-implementation before anything else; a kept rule gets ONE
  look at 2022–2025, declared separately. The 2026 holdout stays untouched.
- **Said before the run:** our own 2013–2021 hour table shows about +0.8 bp gross for the two hours after the reopen
  (all evenings), against about +2.5 bp needed for t ≥ 2.5 after costs; the prior of a pass is low. If it passes it adds
  a small independent sleeve, not a multiplier of gains.

### Addendum K — outcome (2026-11-14, `results/r2/round5/gold_reopen/results.json`, `attack.json`)
**The main configuration fails 7 of the 10 bars, so nothing is kept and no look at 2022–2025 is declared.** The
interpretation choices were written in `declared.json` (2026-11-14 04:09:10 UTC, sha256 `3bb98b52eb17…`) before any
return was computed; 7 configurations logged in `trials.jsonl`; frames read with the filter ts < 2022-01-01;
`val_access.log` unchanged; the 2026 holdout not touched.
- **Main** (buy at the first M1 bar at or after 18:15 New York, Monday–Thursday evenings, stop 2.0 × mean H1 range,
  exit after 120 min): 1,737 trades, PF 0.811, t −2.93, −0.0243 R per trade (−42.3 R in all, −1.20 bp net), 2 of 9
  years positive (2016, 2020), PF 0.728 at costs ×1.5, random-time null percentile 61.0, weekly correlation with the
  ten 0.067. Before any cost: PF 1.014, t 0.19, −0.01 bp per trade: there is no gross edge to pay the costs with.
- **Neighbours** (one parameter each): PF 0.846 / 0.798 (entry 18:10 / 18:30), 0.793 / 0.832 (hold 96 / 144 min),
  0.804 / 0.816 (stop 1.6 / 2.4); median 0.810.
- **Attack** (independent re-implementation: own holiday calendar, own H1 range, own simulator): **confirmed**. The
  main and all six neighbours are identical trade for trade (max |ΔR| = 0); stress and gross R within 0.0012 R
  because the lab's stress rebuilds the H1 range on the re-spread quotes (I1). Four minor points, none changes a
  verdict: I1; the holiday calendar and the frame disagree on four days (Columbus Day halts 2013/2014, 2019-07-04
  traded in the frame) (I2); six evenings of 2014 and 2017 pass the quote test on one stray 18:00 bar and enter at
  19:00 (I3); the null's random replays pay the swap at the 17:00 rollover, the rule never does, which favours the
  rule by about 0.004 R (I4; without it the percentile is about 50). Eight other readings keep PF within 0.805–0.821.
- Information only, not judged, not a new rule: on the same evenings gold's mid rises +1.36 bp from 18:00 to 20:00,
  of which +1.05 bp between 18:00 and 18:15, the minutes with the widest spreads of the day; from 18:15 to 20:15 it is
  +0.04 bp. Addendum K's pre-run figure (+0.8 bp for the two hours after the reopen) mostly lies in that first quarter
  hour. An earlier entry would be a new idea needing its own declaration, with real reopen spreads first.
- The account stays the ten rules.

## Addendum L (2026-11-14; written BEFORE any run): round 6 — night mean reversion on FX crosses (MQL5 survey, idea 2)
The user asked to go on with the tests ("continue les tests pour améliorer"). This round tests the second idea of the
survey (`results/r2/mql5_survey.json`): the "night scalpers" that fade small stretches after the 17:00 New York
rollover. Best evidence: signal 'Scalp IC Markets ECN' (https://www.mql5.com/en/signals/683917), a real account public
since July 2020: PF 1.79, 70.5 % winners, average win 3.43 against average loss 4.56 EUR, average hold 2 h, rules not
published. A review of about twenty public sources (open code, articles, vendor manuals, live signals, one independent
Dukascopy test; notes committed with this text as `results/r2/round6/night_fade/sources.md`) found no published rule,
only shared elements. The rule below is their common core written as one computable rule with one parameter set for
every cross; where the sources disagree, the alternatives are the neighbours. It replaces the survey's placeholder
(M15 bars, 18:30–23:45, six crosses), which was never declared. Of the new price files only header lines and one first
row (eurcad-m1-bid-2013, to check the time unit) were opened, and before the download the lead printed two rows of a
one-week test download (EURCAD bid, March 2021) to check the tool's format; nothing was computed on any price. Every reading of a
detail left open goes into `declared.json`, with its sha256, before any return is computed.

**Frozen rule `night_fade` (the main configuration).**
- **Basket**: all twelve crosses fixed in `dl_round6.py` before the research: EURCAD, GBPCAD, EURAUD, AUDCAD, EURGBP,
  EURCHF, GBPCHF, AUDNZD, NZDCAD, CADCHF, GBPAUD, EURNZD. None chosen on results; no major pair (the idea and its
  evidence are about crosses; one data source and one cost model). A cross leaves only by the coverage pre-check
  below.
- **Data**: Dukascopy M1 bid and ask (`data/raw_r6`, the 216 files of 2013–2021, all on disk), merged exactly as
  `prep_round3._merge` with the weekday rule of `prep_round3.fx`; frames asserted to end before 2022-01-01 and read
  with the filter ts < 2022-01-01 (`data/r6/<cross>_m1.parquet`). One pip = 0.0001 for all twelve.
- **Evenings** (New York wall clock, `America/New_York`): E = a date from Monday to Thursday; it opens trading day
  E+1. Skipped: E from 24 December to 1 January; E or E+1 an NYSE full holiday (`idxus_lib.us_holidays` minus
  `SPECIAL_CLOSURES`; half days are normal). That leaves 1,753 evenings, 2013-01-02 to 2021-12-22 (194–196 a year).
  For each cross an evening is tradable once 480 completed H1 bars exist at 17:15 (warm-up: about the first four weeks
  of 2013).
- **Band**: M5 bars = `goldlab.data.bars(base frame, "5min")` (clock grid; a bucket with no M1 bar has no bar), mid
  closes. For bar j: μ = mean of the closes of bar j and the 19 existing bars before it, σ = their population standard
  deviation, bands μ ± 2.0 σ; usable only if bar j−19 starts at most 120 minutes before bar j ends.
- **Signal**: decision times = the ends of the 5-minute buckets 17:15, 17:20, …, 19:55 of E (33 a night); the signal
  bar is the bar of the bucket that ends then (none, or band not usable: no signal). Close below the lower band: buy;
  above the upper band: sell (strict). D = |close − μ|.
- **Cost filter** (the scale-free form of the maximum-spread filter almost every source uses, measured against the
  trade's own target; BG Robonight and Night Hunter Pro similarly require a minimum channel width): the signal counts
  only if D ≥ 2.0 × C, C = ask close − bid close of the signal bucket's last M1 bar (base frame: Dukascopy spread plus
  commission).
- **Entry**: at market at the open of the first M1 bar starting at or after the decision time; dropped if that bar
  starts more than 5 minutes late, or if its open has already reached the target (buy: ask open ≥ μ; sell: bid
  open ≤ μ; a trade server refuses such a take-profit). A dropped order does not block later signals. A buy fills at
  the ask open + 0.1 bp, a sell at the bid open − 0.1 bp.
- **Exits** (`goldlab.sim.simulate` on M1 bid/ask highs and lows; stop first when both are touched in one bar).
  *Target* = μ of the signal bar, frozen, a resting limit with no slippage (a long exits when a bar's bid high reaches
  it, a short when a bar's ask low does; possible on the entry bar). *Stop* = 2.0 × the mean (mid high − mid low) of
  the 480 most recent completed H1 bars at the decision time (`bars(base frame, "1h")`;
  completed = start + 60 min ≤ decision time), set from the fill and fixed, 0.3 bp of slippage, the worse open on a
  gap. *Time* = at market at the open of the first M1 bar at or after 21:00 New York (`exit_index`, 30-minute gap
  rule), 0.1 bp. No trade crosses 17:00 New York, so the swap is 0 (asserted).
- **Positions**: one per cross (`no_overlap=True`: an order whose entry bar is at or before the open trade's exit bar
  is ignored); later signals of the evening may trade, on either side; no cap across crosses or per currency
  (reported). R = side × (exit fill − entry fill) / |entry fill − stop|.

**Costs.**
- **Base**: Dukascopy's own minute bid and ask, unclipped (each night's real widening, rollover tails included), plus
  FP Markets Raw commission, 6 USD per 100,000 units of base round trip, folded into the quotes (bid − h and ask + h
  on all four prices, h = ½ × c × the M1 bar's mid close) at fixed low-end USD values of the base (EUR 1.05, GBP 1.20,
  AUD 0.65, NZD 0.60, CAD 0.70; general knowledge, not measured, so the commission is if anything overstated):
  c = 0.5714 bp for the five EUR crosses, 0.5000 bp for the three GBP crosses, 0.9231 bp for AUDCAD and AUDNZD,
  1.0000 bp for NZDCAD and 0.8571 bp for CADCHF. Slippage 0.1 bp on market fills, 0.3 bp on stops, none on targets.
  Why not an FP spread model: FP's cross spreads are not verified, and its intraday shape clipped at 6 × the daily
  median would understate the minutes after 17:00. Known bias: Dukascopy's cross spreads were wider in 2013–2015 than
  ECN spreads are today.
- **Costs × 1.5** (base spread × 1.5 around the mid with `apply_spread_mult`, slippage × 1.5), two readings that must
  both pass: (a) orders rebuilt on the widened quotes (the lab's stress; the filter then sees 1.5 C); (b) the base
  orders replayed unchanged. **Gross** (information): the base orders on mid quotes, no slippage.

**Neighbours (each changes one thing; all logged; 7 configurations with the main).** (1) `first_hour`: decisions
17:15–17:55 (the hour the only independent test calls the core). (2) `moving_mid`: the same orders without a resting
target; exit at market at the open of the first M1 bar at or after the end of the first usable M5 bar that ends after
the entry bar starts and whose mid close is ≥ (long) / ≤ (short) its own middle band; stop and 21:00 exit unchanged.
(3) `width_2.5`: bands ± 2.5 σ. (4) `m15`: M15 bars (span limit 360 minutes), decisions at the ends of the 15-minute
buckets 17:15–19:45. (5) `stop_3.0`: stop 3.0 × the mean H1 range. (6) `one_per_night`: only the first order of each
cross and evening.

**In sample only (2013–2021), frames cut while read. The verdict is read on the main only; pass = all twelve bars:**
n ≥ 250; pooled PF ≥ 1.12; t on daily sums of R ≥ 2.5 (trading day of entry, days with a trade); at least 6 of the 9
calendar years positive (entry year; a year with no trade is not positive); pooled PF ≥ 1.04 at costs × 1.5 in both
readings; at least 8 of the 12 crosses with a positive expectancy (no trade = not positive); no cross above 25 % of
the pooled net R (a pooled total ≤ 0 fails); median pooled PF of the six neighbours ≥ 1.06; every-signal
expectancy > 0 (every order of the main, overlaps allowed); max hold ≤ 5 trading days; null ≥ 97.5th percentile;
|weekly correlation with the sum of the ten| ≤ 0.30.
- **Before the run (no return computed)**: a pre-check (frames, evenings, warm-up, signals and drops per
  configuration, spreads and all-in costs by cross and year at 17:15–21:00 and 16:55–17:30, the clock in UTC in both
  daylight-saving regimes); a cross with an M1 bar in [17:15, 21:00) on fewer than 90 % of the 1,753 evenings is
  dropped (the cross bars then apply to the crosses kept, 65 % rounded up); a synthetic test; a truncation test (μ, σ,
  side, D, C and the stop distance of at least 50 decisions per cross, recomputed on frames cut at the decision time,
  must be equal); a hand check from the raw quotes of the first main trade of 2013, 2015, 2017, 2019 and 2021.
- **Null** (section 4: same clock time, random day, same instrument): 200 replays, numpy `default_rng(0)`. Each main
  trade is re-entered on its cross, on an evening drawn uniformly with replacement among the cross's tradable
  evenings, at the open of the first M1 bar at or after the New York clock time of its entry bar (another evening if
  that bar is more than 5 minutes late; after 20 draws dropped and counted); same side; stop and target distances as
  fractions of its entry fill, scaled by the replay bar's mid open; resting target; time exit at 21:00 New York of
  that evening; base costs; every replay simulated (`no_overlap=False`). Statistic: the pooled mean R;
  percentile = share of the 200 means strictly below the main's.
- **Correlation**: Addendum K's convention (the ten's official trades read with entry_time < 2022-01-01, exits in 2022
  dropped; weekly R by exit week, W-SUN UTC, every week from 2014-01-01 to 2021-12-31 (418), an empty week = 0;
  Pearson).
- **Reported, not judged**: for every configuration, pooled and per cross: n, PF, t on daily sums and on trades,
  expectancy, R by year, long and short, win rate, average win and loss in R and their ratio (683917: 70.5 % winners,
  0.75), exits by reason, hold, net, gross and cost bp, target and stop distances in pips, all also at costs × 1.5
  (both readings) and gross. For the main: entries by New York hour, weekday and daylight-saving regime; first against
  later trades of the evening; drops by filter; evenings skipped by reason and cross; entries, stops and targets
  between 16:55 and 17:30; stop and target in one M1 bar; × 1.5 fills already past the target; expectancy by D / C
  (2–3, 3–4, ≥ 4); the AUD and NZD crosses against the other six; winning days, weeks and months; worst evening and
  week; maximum drawdown in R; crosses open at once and the most trades open on one currency and side; the account
  check at 7 % of 1,000 EUR (0.01 lot, 1:500); the break-even extra cost per round trip; the evenings of 2016-10-06
  (pound flash crash, about 19:07) and 2019-01-02 (yen and Australian-dollar flash crash, about 17:30–17:45), the week
  of 2021-11-22 and EURCHF before 2015-01-15, all of which stay in the test.
- **Bookkeeping**: `results/r2/round6/night_fade/trials.jsonl`, one line per configuration and cross plus one pooled
  line per configuration (91), whatever the result; the run refuses to run twice; `results/val_access.log` unchanged.
- **After the run**: a fail is final (another window, band, stop, filter, bar size or cross list is a new idea with
  its own declaration). A pass is attacked by an independent re-implementation (own frames, calendar, bands, H1 ranges
  and simulator; trade for trade; execution on the 1,000 EUR account). A confirmed pass gets ONE look at 2022–2025,
  declared separately; the crosses' 2022–2025 files are downloaded only after that declaration. Before any real use:
  FP's night quotes on the twelve crosses are read with `ReleveFP` v1.10 (InpSymbols = the twelve crosses,
  InpDays = 45: at least 20 Monday–Thursday evenings, a second run a month later if fewer) and the commission from a
  demo round trip; a cross whose FP median all-in cost over 17:15–21:00 New York exceeds 1.5 × the base frame's median
  at the same minutes over 2019–2021 is not traded; with fewer than 8 crosses left the rule is not used; then the demo
  account first. The 2026 holdout stays untouched.

**Said before the run.** The vendors' records are better than this test can be: they rest limit orders at the band (no
spread paid to enter), tune per pair, use low-spread ECN brokers and are survivors (22 of the 26 signal links on their
pages are gone); the lab enters at market after the bar closes and crosses the spread. Arithmetic: under the filter a
target win nets D − C/2 ≥ 0.75 D, with a stop several times D, so of the order of +0.1 to +0.4 R against losses up to
−1 R; PF 1.12 needs a net mean of about 5.7 % of the mean |R|. The lab's FX record: no FX rule among the ten;
round 3's FX edges were 1–2 bp gross at best; round 4's FX weekend fade had no gross edge (−0.19 bp per trade before
costs). Expected: a few thousand to about 15,000 trades, 60–75 % winners, a gross PF above 1 and, if it fails, failing
on PF, costs × 1.5 and years; the null can pass even then (it tests timing, not costs). Prior of an in-sample pass
about 8 %, of a later 2022–2025 pass about 3 %; |ρ| with the ten below 0.1. If it passed: a small sleeve on a clock
and a market the ten never touch, not a multiplier; at 7 % per trade a per-evening risk budget would be declared
before any real use.

### Addendum L — outcome (2026-11-14, `results/r2/round6/night_fade/results.json`, `run.json`)
**The main configuration fails 8 of the 12 bars. The fail is final: nothing is kept, nothing needs attacking and no
look at 2022–2025 is declared.** The readings were written in `declared.json` (2026-11-14 12:17:47 UTC, sha256
`c399625ef117…`) and committed with the frozen code (c9d94bf) before any return was computed; 91 lines in
`trials.jsonl`; frames read with the filter ts < 2022-01-01; `val_access.log` unchanged; the 2026 holdout not touched.
- **Before the run.** The independent review found 6 points (major: the `moving_mid` exit could fill before its own
  trigger bar closed when quotes had a gap of more than 30 minutes; minor: bars judged on rounded figures, reading (a)'s
  gross taken from other trades, the wording of L18, the write order of the run files, exit kinds). All were fixed with
  synthetic proofs (76/76 checks). The reviewer's own re-implementation scripts, re-run on the final code, match the
  main, readings (a) and (b), gross and the six neighbours trade for trade on noisy synthetic frames with quote holes.
  Pre-check: coverage 100 % for all twelve crosses (none dropped), truncation 720/720 exact. Hand checks from the raw
  quotes with independent code: entry side 5/5 and exit side 5/5 exact.
- **Main**: 12,138 trades, PF 0.711, t −8.90 on daily sums, −0.0485 R per trade (−589 R in all, −1.55 bp net per
  trade), 57.2 % winners, average win 0.21 R against average loss 0.39 R (ratio 0.53), 0 of 9 years positive (every
  year from −36 to −107 R), 0 of 12 crosses positive, PF 0.571 (a, rebuilt) and 0.493 (b, same orders) at costs × 1.5,
  every-signal expectancy −0.0494 R (28,238 orders), max hold 3.75 h, null percentile 100 (random evenings at the
  same clock times: −0.103 R per trade), weekly correlation with the ten 0.089. Exits: target 5,820, 21:00 5,543,
  stop 775.
- **Before any cost** (mid quotes, no slippage): PF 1.48, 67.8 % winners, +1.78 bp per trade. The all-in cost is
  3.34 bp per trade. On the same trades the costs would have to fall by 1.48 bp (44 %) to break even and by 2.0 bp
  (60 %) to reach PF 1.12. Every cross has a gross edge (gross PF 1.22–1.89) smaller than its costs, from EURGBP
  (+1.91 bp gross, 2.70 bp cost) to CADCHF (+1.23 bp gross, 4.51 bp cost).
- **Neighbours** (one change each): PF 0.824 (`first_hour`), 0.661 (`moving_mid`), 0.734 (`width_2.5`), 0.737
  (`m15`), 0.724 (`stop_3.0`), 0.690 (`one_per_night`); median 0.729; gross PF 1.46–1.83 for all six.
- **As said before the run**: it fails on PF, costs × 1.5 and years; the null passes (the timing is real, the costs
  are not paid); |ρ| < 0.1. The measured trade count (12,138) sits inside the expected range; the win rate (57 % net,
  68 % before costs) and the win/loss ratio (0.53) are below signal 683917's 70.5 % and 0.75.
- **Information only, not judged**: in MetaTrader 5 a buy limit triggers when the ask reaches it (a sell limit when
  the bid does), so resting orders at the band, as the vendors do, do not avoid the spread; they only change when the
  entry happens (a new idea, with its own declaration, if ever). Only night quotes well below half of Dukascopy's
  would change the arithmetic, which nothing in the sources suggests; the ReleveFP reading of the twelve crosses is
  therefore not needed. At 7 % per trade on 1,000 EUR the worst evening (2016-10-12) would have cost about 665 EUR:
  up to 12 crosses were open at once and up to 5 trades on one currency and side.
- Both ideas of the MQL5 survey are now closed (Addenda K and L). The account stays the ten rules.
