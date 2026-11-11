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
