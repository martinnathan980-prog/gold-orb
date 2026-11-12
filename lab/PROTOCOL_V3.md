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
