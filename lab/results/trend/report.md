# Track `trend` — short-horizon trend following on XAUUSD (hold ≤ 5 trading days)

*(Written by the trend research agent; saved to file by the lead because the agent could not write .md files.)*

**Verdict (agent).** Nothing *robust* survives. The single finalist `donch4h_stop` (Turtle-style 10-trading-day breakout on 4 h bars, stop entries, 2 × ATR trailing stop) **passes all six pre-registered IS criteria and the VAL criterion**, but the every-signal diagnostic (`no_overlap=False`) gives VAL PF 0.91 vs 1.34 on IS: signals skipped by the one-position rule lost on VAL while on IS they matched those taken. VAL profit is entirely long and mostly from 2025. The agent considers it not validated in substance and does not recommend trading it; the 2026 holdout look is optional ("expect noise").

**Trials:** 50 logged (budget 150): 48 before the finalist decision; afterwards 1 IS-only check on MT5's server-time 4 h grid and 1 coordinator-requested every-signal diagnostic. VAL access: 5 lines in `val_access.log` (finalist + its ×1.5-cost run = one evaluation; one descriptive re-read of the same frozen config; the random benchmark; the every-signal diagnostic). Nothing re-tuned.

## 1. What was tested and why
**Prior.** Time-series momentum is documented at 1–12-month horizons (Moskowitz, Ooi & Pedersen 2012). Descriptive check on IS (not a trial): variance ratios 0.99–1.05 for 1 h returns over 2 h–120 h; 1.02 / 1.01 / 0.99 / 0.93 for daily returns over 2/5/10/20 days, sign flipping by year → gold 2013–21 has no unconditional short-horizon trend; any edge must be conditional (breakouts of extremes) with exits that let large moves run.

**Costs.** ≈ $0.75 per round trip (median spread ~$0.29 + 1.5 bp slippage/side + $0.07 commission + swap) ≈ 0.25 R on an ATR(1 h) stop but only ≈ 0.08 R on a 2 × ATR(4 h) stop → fast 1 h systems are ruled out.

**Families.** Donchian close-breakout on 1 h / 4 h / D (market entry next M1 bar); Donchian stop-entry (OCO stops at the n-bar high/low, side resolved by first touch on M1); Larry Williams volatility breakout (open ± k × previous-day range; anchors trading-day open, London 08:00, NY 08:00; Crabel NR7 filter); TSMOM (sign of L-day return, optional volatility regime).

**Phases** (each grid fixed before running): A screen (17) — only 4 h n = 60 Donchian passed the "promising" bar (PF ≥ 1.10, t ≥ 1.5, short side not losing): PF 1.26, t 1.54. B (16) — channel length, exits, filters: PF plateau 1.26–1.35 for n ≥ 60 with trailing exits, t 1.4–1.8; volatility breakout dead. C (5) — 2×2×2 factorial: tweaks not additive; the stop-entry version at untuned base parameters gave PF 1.356, t 2.37 → passes IS. Finalist decision: single finalist chosen on IS before any VAL access (`finalists_preval.json`). R (10) — neighbours. VAL — one shot via `validate.py` (which first asserts the IS numbers reproduce exactly). After VAL, diagnostics only: random-entry benchmark, server-time grid check, every-signal check.

## 2. Finalist rule (for the EA)
- Bars: 4 h on the UTC grid (00/04/…/20 UTC), mid prices.
- Entry: after each 4 h close, if flat, place a buy-stop at the highest mid-high and a sell-stop at the lowest mid-low of the last 60 bars (including the bar just closed). OCO, valid until the next 4 h close; buy-stop triggers on ask, sell-stop on bid.
- Stop: 2 × Wilder ATR14(4 h), frozen at the decision.
- Trailing stop: same 2 × ATR from the best M1 bid-high (longs) / ask-low (shorts), updated at each M1 close.
- Time stop: decision time + 5 NY trading days − 5 min; if that falls in a closure, the last bar before it.
- Sizing: one position at a time, fixed % risk per trade.
- Warm-up: ≥ 2 months of M1 (checked: identical orders).
- Causality test: orders built on data truncated at 3 arbitrary minutes match the longer frame exactly.

## 3. Results
| metric | IS | IS costs ×1.5 | VAL | VAL costs ×1.5 | VAL every signal |
|---|---|---|---|---|---|
| n (per yr) | 494 (55.1) | 494 | 243 (61.0) | 243 | 925 |
| win rate | 40.1 % | | 38.3 % | | 36.4 % |
| avg win / avg loss R | 1.19 / −0.59 | | 1.10 / −0.56 | | 0.95 / −0.60 |
| expectancy R | +0.125 | +0.095 | +0.080 | +0.056 | −0.033 |
| PF | **1.356** | 1.261 | **1.232** | 1.158 | **0.913** |
| t | 2.37 | | 1.19 | | — |
| years positive | 8/9 | | 3/4 | | 1/4 |
| % weeks positive | 31.1 | | 33.5 | | |
| max drawdown R | 9.4 | | 10.7 | | 93.0 |
| long n, R, PF | 242, +49.2, 1.63 | | 152, +28.8, 1.58 | | +32.8 R, 1.15 |
| short n, R, PF | 252, +12.6, 1.13 | | 91, −9.4, 0.72 | | −63.4 R, 0.50 |
| top 5 % of trades, share of total R | 144 % (−27.4 R without them) | | 193 % (−17.9 R without them) | | |

Every-signal IS run: n 1694, PF 1.343, 7/9 years, long PF 1.55, short PF 1.12, stress PF 1.26.

R by year:
| side | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| long | −2.7 | 1.2 | 4.0 | 10.9 | 6.1 | −0.7 | 11.8 | 20.4 | −2.0 | −0.0 | 3.5 | 7.8 | 17.5 |
| short | 12.7 | 4.8 | 2.7 | 3.0 | −2.6 | −1.4 | −9.1 | −3.8 | 6.4 | −2.0 | 0.7 | −4.8 | −3.3 |

Shorts negative in 6 of the last 9 years.

Neighbours (IS):
| neighbour | PF | t | passes all IS criteria |
|---|---|---|---|
| n = 48 | 1.321 | 2.28 | yes |
| n = 72 | 1.308 | 2.02 | yes |
| stop 1.6 | 1.360 | 2.40 | yes |
| stop 2.4* | 1.354 | 2.36 | yes |
| trail 1.6 | 1.359 | 2.62 | yes |
| trail 2.4 | 1.405 | 2.46 | yes |
| time stop 4 d | 1.348 | 2.36 | yes |
| ATR 11 | 1.358 | 2.40 | yes |
| ATR 17 | 1.338 | 2.28 | yes |
| **median PF** | **1.354** | | |

\*Stop 2.4 is nearly degenerate (the 2.0 trail takes over from the second M1 bar). Extra checks: same rule on 1 h bars PF 1.378 (t 2.36); MT5 server-time 4 h grid PF 1.313 (t 2.12).

**Diagnostics**
- Random entries with the identical exit (20 seeds), PF median [max]: IS random side 0.85 [1.03], random long 0.83 [0.93], random short 0.87 [0.98]; VAL random side 0.93 [1.13], random long 1.19 [1.44], random short 0.64 [0.73]. On IS the breakout clearly beats random entries; on VAL, per signal, it does not (longs 1.15 vs 1.19 random; shorts 0.50 vs 0.64).
- Taken vs skipped signals: IS taken +0.125 R/trade (PF 1.356), IS skipped +0.126 R (PF 1.338); VAL taken +0.079 R, VAL skipped −0.073 R (derived from the two VAL reports; subset verified exact on IS) → the VAL pass depends on which signals the one-position rule happened to take.
- Selection: t 2.37 is the best of 48 correlated configs (roughly p ≈ 0.1 after selection).

## 4. Rejected ideas
1 h Donchian 1–5-day channels (PF 0.81–0.89, costs ~0.2 R); 4 h n = 20 README baseline (1.006 — channels < ~10 days carry no information; n = 40 gives 1.12); daily Donchian (0.96–1.11, too slow); close-entry refinements (session filter 1.35, SMA50 1.31, trail 3 1.30, 3-day stop 1.30, best factorial cell 1.37 t 1.96 — all t < 2 and not additive: trail 3 + 3-day stop = 1.09); exits without trailing (time-only 1.09, 2R target 1.05); volatility breakout (6 anchor/k combos 0.83–1.02; multi-day trailing 0.83–0.96; NR7 0.78); TSMOM 5/20/60 d (0.82–0.97; high-vol regime 0.69, low-vol 0.97).

## 5. Engine and data concerns
1. No OCO: row-order resolution of simultaneous pending orders (synthetic repro: a sell-stop touched at 10:02 loses to a long filling at 10:05 because it is listed first). Workaround `_first_touch` (resolve first touch on M1; adverse side if both in the same minute); the engine's fill bar matched on all 494 IS trades.
2. Time exits skip over closures: `entry_index` for a time stop that falls in a weekend/holiday/early close executes at the *next* open (holds of 235 h seen; `is_criteria` only flags > 192 h). Workaround `exit_index` (last bar before the closure).
3. Data gaps and stub days: ~28 non-holiday IS days with large M1 gaps (2014-01-10 NFP: 58 min; 2020-03-16: 120 min); `bars("D")` contains stub days (2013-01-01 1 min; Christmas/New Year 1 bar) → distorts previous-day range / daily ATR. Workaround `daily_bars` (≥ 600 min/day).
4. Costs ×1.5 run does not re-resolve the first-touch side — negligible.
5. Sizing: PF in R (1.36) > PF on equal-size positions (1.19) → live sizing must be fixed % risk per trade.
6. Coordinator caveats: 1 handled; 2 consistent with the rule (brackets only when flat at the 4 h close); 3 reported above; 4 n/a (research on M1 cut at 2022-01-10; all decisions on the IS cut).

## 6. Files
`lab/tracks/trend/`: `strategy.py` (`make_orders`, `FINALISTS`), `research.py`, `validate.py`, `benchmark.py`. `lab/results/trend/`: `trials.jsonl` (50), `trials_detail.jsonl`, `finalists_preval.json`, `val_results.json`, `benchmarks.json`, `diag_overlap.json`, `candidates.json`, `trades_is_donch4h_stop.csv`, `trades_val_donch4h_stop.csv`.
