# Track `pivots` — pivot points and key price levels on XAUUSD

*(Written by the pivots research agent; saved to file by the lead because the agent could not write .md files.)*

**Verdict: NOTHING SURVIVES.**
- Classic pivot trading (floor P/S1/R1/S2/R2, Camarilla, weekly pivots, previous-day high/low; fade, break, rejection-candle and bias variants) loses about the trading costs, **and the same rules on randomly shifted levels do just as well** (placebo).
- Round numbers are the only levels with a real footprint beyond random: they break **through** at first touch rather than bounce (consistent with stop-loss clustering beyond round numbers).
- The best rule built on that footprint, `rn100_break_fresh` (breakout at the day's first touch of a $100 level, London/NY hours), passed every IS criterion and robustness check, then lost in 2022–2025 (PF 0.84, expectancy −0.07 R, 1/4 years). Status under Amendment 1: **ÉCHEC** (VAL PF would still be 0.94 with zero commission and zero slippage). Not promoted to the holdout.

## 1. Design
Two opposite hypotheses, long and short: **BOUNCE** (first touch rejected; resting limit at the level, or market order after an M5/M15 rejection candle; stop beyond the level; target next level or R-multiple) and **BREAK** (resting stop at the level = "tbreak", or M15/H1 close beyond = "acceptance").

| Family | Levels |
|---|---|
| Floor pivots | P, S1–S3, R1–R3 |
| Camarilla | L1–L4, H1–H4 |
| Previous day | PDH, PDL, PDC |
| Weekly floor | WP, WS1/2, WR1/2 |
| Round numbers | $10 / $25 / $50 / $100 |

Conditioning tested: open vs P, time of day, first touch of the day only ("fresh"), day's range already used vs ATR.

Causality: daily levels from the previous full NY-17:00 trading day on bid prices (like an MT5 D1 bar); days with < 600 M1 bars skipped (76 holiday stubs / data holes, never used for levels, never traded); weekly levels from the previous week; ATR = 14-day SMA of daily true range up to the previous day; London/NY wall-clock windows (DST-aware): arm 08:00 London, touches until 12:00 NY, forced exit 16:00 NY. Resting orders: `entry_i` computed as the first-touch bar with the engine's own fill rule, so several resting orders are simulated in true time order. Close-based orders: next M1 open. Every order has an absolute stop and a forced exit. Research frame loaded with `end="2022-01-01"`.

Placebo: same rules on the day's level set shifted by ±U(0.2, 0.4) × ATR with random sign (P shifted too); round-number grids get a random phase U(0.2, 0.8) × grid; 20 seeds in the event study, 10 pooled seeds per strategy placebo.

## 2. Trials
84 logged, all IS: 20 event-study entries (each vs 20 placebo seeds), 39 strategy configs (1 passed IS), 12 strategy placebos (10 seeds each), 10 finalist neighbours, 3 diagnostics (`no_overlap=False`, costs ×2, costs ×3). VAL accessed once (2 log lines: normal costs and ×1.5).

## 3. Are pivots special? Cost-free event study vs placebo (IS)
Statistic: after the first touch, does price move X in the bounce direction before moving X through the level (X = 0.25 × daily ATR ≈ $4)? p = bounce rate; z = (p_real − mean p_placebo) / sd p_placebo; negative z = breaks through more often than a random level.

Active window (armed 08:00 London):

| Family | Touches | p real | p placebo | z |
|---|---:|---:|---:|---:|
| Floor, all levels | 3434 | 0.469 | 0.470 | −0.1 |
| P | 1185 | 0.505 | 0.479 | +2.2 |
| S1 / R1 | 687 / 703 | 0.472 / 0.468 | 0.471 / 0.480 | +0.1 / −0.8 |
| S2 / R2 | 292 / 298 | 0.428 / 0.389 | 0.472 / 0.472 | −1.9 / −3.5 |
| PDH/PDL/PDC | 2821 | 0.454 | 0.491 | −4.5 |
| Round $50 | 576 | 0.417 | 0.502 | −5.5 |
| Round $10 | 2267 | 0.474 | 0.493 | −2.1 |

Full day (armed 18:00 NY): Floor 0.479 vs 0.479 (z −0.1); Camarilla 0.502 vs 0.494 (+1.7); Weekly 0.475 vs 0.489 (−1.5); PDH/PDL/PDC 0.473 vs 0.501 (−4.2); Round $50 0.433 vs 0.499 (−4.8); Round $10 0.482 vs 0.512 (−4.5).

Acceptance (first M15 close beyond), continuation rate: Floor 0.525 vs 0.521 (+0.6); PDH/PDL/PDC 0.519 vs 0.508 (+1.5; +3.8 at 0.15 ATR); Round $50 0.545 vs 0.495 (+1.9).

**Answer:** S1/R1, Camarilla and weekly pivots have no power beyond random levels; P has a small bounce effect (~+0.04 PF); PDH/PDL/PDC and round numbers are break-through levels, not bounce levels (Osler 2003; Aggarwal & Lucey 2007; Lucey & O'Connor 2016). The footprint (~4–8 points of win rate) is roughly the size of the costs: on a ±0.25 ATR bracket the spread alone takes a no-edge trade from 50 % to ~47 %, and stop-entry slippage costs another 1–2 points.

## 4. Textbook strategies (a-priori parameters), IS 2013–2021
Exit 16:00 NY unless noted; stops beyond the level in ATR units; placebo PF = median of 10 seeds [range].

| Rule | n | /yr | win | avg W/L (R) | PF | t | yrs+ | stress PF | Long / Short R | Placebo PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| S1/R1 fade, stop 0.25, target P | 1279 | 143 | .388 | 1.19 / −.99 | .762 | −4.5 | 1/9 | .67 | −104.8 / −80.2 | .756 [.67–.84] |
| P fade, target R1/S1 | 1307 | 146 | .382 | 1.24 / −.97 | .789 | −3.9 | 1/9 | .69 | −96.5 / −69.2 | .751 [.66–.86] |
| R1/S1 break on M15, target R2/S2 | 1064 | 119 | .467 | .68 / −.89 | .671 | −5.8 | 0/9 | .56 | −83.8 / −81.1 | .732 [.66–.82] |
| Camarilla H3/L3 fade, 1R | 1666 | 187 | .456 | .91 / −.99 | .770 | −5.2 | 0/9 | .69 | −115.3 / −91.5 | .738 [.64–.79] |
| Camarilla H4/L4 break on M15, 2R | 1010 | 113 | .383 | 1.11 / −.86 | .804 | −3.1 | 1/9 | .70 | −70.8 / −33.9 | .831 [.78–.90] |
| S1/R1 fade + open-vs-P bias | 388 | 43 | .402 | 1.03 / −.97 | .711 | −3.1 | 2/9 | .60 | −30.5 / −34.7 | – |
| R1/S1 break + bias | 767 | 86 | .473 | .70 / −.91 | .691 | −4.6 | 1/9 | .58 | −71.7 / −41.3 | – |
| Rejection candle M15 | 999 | 112 | .476 | .73 / −.90 | .744 | −4.2 | 2/9 | .63 | −69.1 / −50.9 | .736 [.61–.83] |
| Rejection candle M5 | 1072 | 120 | .451 | .85 / −.92 | .761 | −4.1 | 2/9 | .65 | −70.1 / −58.8 | – |
| Break on H1 close | 933 | 105 | .488 | .53 / −.81 | .628 | −6.0 | 0/9 | .52 | −63.8 / −79.5 | – |
| Fade only if day range ≥ 1 ATR | 78 | 9 | .410 | 1.16 / −.95 | .853 | −0.6 | 4/9 | .64 | −7.1 / +0.7 | – |
| Break only if day range < 0.6 ATR | 336 | 38 | .452 | .69 / −.94 | .605 | −4.3 | 0/9 | .49 | −45.5 / −22.6 | – |
| Weekly WS1/WR1 fade, hold ≤ 3 d | 352 | 39 | .295 | 1.67 / −1.04 | .676 | −3.4 | 1/9 | .65 | −63.7 / −19.8 | .798 [.74–.88] |
| Weekly WR1/WS1 break on H1, hold ≤ 3 d | 291 | 33 | .502 | 1.00 / −1.01 | 1.003 | 0.0 | 6/9 | .94 | −17.0 / +17.4 | 1.030 [.92–1.18] |

All lose roughly the costs; none beats its placebo; both sides lose (not an uptrend artefact).

## 5. Break-through stop orders at key levels (IS)
A-priori grid stop {0.25, 0.4, 0.6} ATR × target {1R, 2R, none}. Round $50 (n = 631, 71/yr):

| Stop | 1R | 2R | No target |
|---|---:|---:|---:|
| 0.25 ATR | 0.894 | 0.976 | 1.021 |
| 0.4 ATR | 1.023 | 1.022 | 1.024 |
| 0.6 ATR | 0.991 | 0.974 | 1.046 |

Placebo for $50: 0.766 [0.68–0.88] (stop 0.4 / 1R), 0.841 [0.73–0.96] (stop 0.6 / no target) → round numbers really are special, but only break even. PDH/PDL: PF 0.76–0.84 in all 9 cells (n ≈ 1270).

Pre-declared refinements:

| Variant | n | PF | t | Comment |
|---|---:|---:|---:|---|
| $50, entry 0.05 ATR beyond (Osler) | 562 | 1.001 | | |
| $50, window to 15:00 NY | 701 | 1.004 | | |
| $50, hold 2 d, stop 0.6, no target | 390 | 1.217 | 1.4 | 87 % of R from 5 trades in the 2013 crash; long side −8.6 R; rejected |
| $25 grid | 1259 | 0.829 | | |
| $100 grid | 373 | 1.175 | 1.45 | placebo 0.773 [0.66–0.90] |
| $50, fresh | 370 | 1.105 | | |
| **$100, fresh** | **225** | **1.379** | **2.26** | **finalist** |

Roundness gradient: $25 < $50 < $100.

## 6. Finalist `rn100_break_fresh` (chosen IS, before any VAL access)
Rule: at 17:00 NY take the nearest $100 multiple above (RA) and below (RB) the price; from 08:00 London to 12:00 NY place a buy-stop at RA and a sell-stop at RB, each valid only if that level is untouched since 17:00 NY; stop 0.4 × ATR14(D) back through the level; target 1R; else exit 16:00 NY. Levels are $100 apart → positions never overlap (`no_overlap=False` identical).

| Metric | IS 2013–21 | VAL 2022–25 |
|---|---:|---:|
| n / trades per year | 225 / 25.4 | 131 / 32.9 |
| Win rate | 0.582 | 0.481 |
| Avg win / avg loss (R) | 0.81 / −0.82 | 0.75 / −0.83 |
| Expectancy (R) | +0.129 | −0.071 |
| PF | 1.379 | 0.836 |
| t | 2.26 | −0.95 |
| Years positive | 8/9 | 1/4 |
| Weeks positive / negative (%) | 19.6 / 14.4 | 18.7 / 22.5 |
| Max drawdown (R) | 6.1 | 11.7 |
| Long (n / R) | 111 / +15.4 | 60 / +3.1 |
| Short (n / R) | 114 / +13.7 | 71 / −12.3 |
| PF at costs ×1.5 | 1.28 | 0.785 |
| PF, no commission & no slippage | 1.575 | 0.94 |

R by year IS: 2013 −0.5, 2014 +7.4, 2015 +0.1, 2016 +0.6, 2017 +1.0, 2018 +3.4, 2019 +6.5, 2020 +7.9, 2021 +2.7. VAL: 2022 −5.3 (L −2.3 / S −2.9), 2023 −6.4 (−2.6 / −3.8), 2024 +3.8 (+4.4 / −0.6), 2025 −1.4 (+3.6 / −5.0).

IS robustness: stop 0.32 / 0.48 ATR → 1.215 / 1.480; target 0.8R / 1.2R → 1.315 / 1.424; window start 07:00 / 09:00 London → 1.369 / 1.416; window end 11:00 / 13:00 NY → 1.459 / 1.383; exit 15:00 / 16:30 NY → 1.359 / 1.380; **median 1.381**. Structural: $50 grid 1.105; not fresh 1.175. Exact-rule placebo 0.741 [0.62–0.92]. Costs ×2 → 1.18, ×3 → 0.98 (edge ≈ $1.1/oz per trade on $8.7 risk).

Criteria: IS all pass (frequency 25.4/yr right at the floor), neighbours ✓, stress ✓, **VAL PF ✗ (0.836), VAL expectancy ✗ (−0.071) → FAIL**. VAL mechanics match IS (risk 0.411 ATR in both; fills at the level + modelled slippage): a genuine drop in win rate (41 %, 28 %, 62 %, 51 % by year), not a code issue. Likely cause (post hoc, untested): selection — the single pass among 39 configs reached through sequential choices; it also lost in 2022–23 at prices similar to late IS, so the price-level change is not the whole explanation.

## 7. For the user
Your S1/R1/P levels have no edge by themselves: traded mechanically after costs they lose ~0.1–0.2 R per trade, the same as random lines. Round numbers and yesterday's high/low are places where gold **accelerates through**, not where it reverses — fading them is worse than fading random levels. That acceleration is real but smaller than costs, and the only rule exploiting it in 2013–21 did not hold in 2022–25.

## 8. Rejected ideas
S1/R1 fade (= placebo); P fade (bounce too small for costs); M15/H1 breaks (worse than random levels); open-vs-P bias (worse); rejection candles (= placebo); range filters (too few trades / worse); Camarilla (= placebo); weekly fade (worse than placebo); weekly break (not level-specific); PDH/PDL break-through (0.76–0.84); round-number fade (not run — event study shows they bounce less than random); $50 break-through (break-even); Osler offset / extended window (no gain); $50 multi-day hold (5 outliers); $25 grid (like random); $100 not fresh (1.175, fails IS); $50 fresh (1.105, fails IS).

## 9. Engine notes
1. No OCO / activation order: worked around by setting `entry_i` to the first-touch bar (small residual in the ×1.5 stress: stop entries cannot trigger before the normal-cost touch bar; negligible).
2. `level` is not copied into the trades frame.
3. `weeks_pos_pct` counts no-trade weeks as flat.
4. 76 days with < 600 M1 bars (gaps; March–April 2014 missing ~1 h/day) — skip for daily OHLC.
5. No look-ahead found in `bars()` or `entry_index()`.
6. Round-number placebo on VAL not run (to keep VAL clean) — lead's call.

## 10. Files
`tracks/pivots/strategy.py` (`make_orders`, `FINALISTS`), `tracks/pivots/event_study*.py`, `harness.py`, `stage2-5*.py`, `stage6_val.py` (single VAL run); `results/pivots/trials.jsonl` (84), `candidates.json`, `event_study*.json`, `stage*.json`, `is_trades_*.csv`, `val_trades_*.csv`.

Sources: [Osler (2003), NY Fed staff report 125](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr125.pdf) · [Osler (2003), J. Finance (RePEc)](https://econpapers.repec.org/RePEc:bla:jfinan:v:58:y:2003:i:5:p:1791-1819) · [Aggarwal & Lucey, Psychological barriers in gold prices](https://www.tcd.ie/triss/assets/PDFs/iiis/iiisdp53.pdf) · [Aggarwal & Lucey (2007) (RePEc)](https://econpapers.repec.org/RePEc:wly:revfec:v:16:y:2007:i:2:p:217-230) · [Lucey & O'Connor (2016)](https://econpapers.repec.org/RePEc:eee:finlet:v:17:y:2016:i:c:p:135-140)
