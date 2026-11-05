# Track `meanrev` — mean reversion / fading overextension on XAUUSD

*(Written by the meanrev research agent; saved to file by the lead because the agent could not write .md files.)*

**Verdict: NOTHING SURVIVES.** 30 exploration configs across 9 mean-reversion families and 3 timeframes; none met the pre-registered IS criteria (best frequency-feasible IS PF = 1.03). The best-effort finalist (chosen on IS by a pre-declared rule) fails 5/7 IS criteria and fails VAL (PF 0.69, 0/4 years). Gold 2013–2021 has no exploitable short-term reversal after costs: at daily horizon the classic fades' **pre-cost** edge is already ≤ 0 (costs are not the problem); at intraday horizons big moves **continue**, so fades lose even before costs.

Trials logged: **38 / 150** (30 exploration + 7 neighbour-robustness + 1 overlap diagnostic). VAL accessed once for the finalist, plus one coordinator-requested overlap diagnostic under a separate label (after the finalist had already failed); both in `results/val_access.log`.

## 1. Set-up (fixed before testing)
- `goldlab.simulate`, protocol costs, `no_overlap=True`. Research loaded M1 only up to 2022-01-10 (VAL could not leak).
- Causality: decisions at bar `t_close`; indicators rolling/recursive (Wilder RSI/ATR/ADX, rolling SMA/std/min/max; `shift(1)` for prior n-bar extremes and prior-day ATR); entries via `entry_index`; intraday signals dropped if the next tradable bar starts > 10 min after the decision.
- Daily decisions at the 17:00 NY close, **executed 120 min after the 18:00 NY reopen** (the reopen minute has median spread $0.85, mean $1.11, p90 $1.89 vs $0.29–0.35 otherwise); daily exits likewise.
- Every order has a stop; forced exit ≤ 166 h.
- Audits: truncation test (orders built on M1 cut at 3 random timestamps identical to those from longer data, for 4 family types → no future data used); full-history VAL run reproduces the IS trial exactly (n = 346, PF 1.026); hand-checks of trades (signal values, bid/ask fills with slippage, exit timing, stops) match raw data.

**EDA (IS only, before any strategy).** 1 h / 4 h / D consecutive returns essentially uncorrelated; after large moves gold tends to **continue** (after a > 3 sd up-hour the next hour averages +0.22 sd; after a > 2 sd day the next day moves a further 0.12–0.15 sd the same way). Faint reversal hints only after large 4 h up-bars and after 3-day selloffs (+0.19 sd over 3 days, n = 64) → trial #22, failed.

**Literature.** Documented intraday predictability in metals is mostly momentum; London-fix studies describe a time-of-day seasonality that beats the market only before costs (seasonality track's domain).

## 2. All trials
Stages (each list written down before being run): S1 one canonical config per family; S2 additions with a rationale (ADX ranging filter, Turtle Soup, multi-day reversal); S3a does the one positive result (#19) hold at lookbacks/timeframes reaching 25 trades/yr; S3b wider stop / longer hold; R neighbours. "gross" = R/trade before spread, slippage, commission, swap; "cost" = total cost in R/trade.

| id | stage | idea | n | /yr | win | PF | exp R | t | yrs+ | stressPF | longPF | shortPF | gross | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | S1 | Connors RSI2<10/>90 D +SMA200, exit SMA5, 5d, 3ATR stop | 96 | 11.8 | .49 | 0.68 | −.063 | −1.44 | 5/9 | 0.64 | 0.77 | 0.54 | −.030 | .033 |
| 2 | S1 | RSI2 D no trend filter | 296 | 32.9 | .56 | 0.78 | −.044 | −1.65 | 3/9 | 0.75 | 0.75 | 0.81 | −.013 | .030 |
| 3 | S1 | IBS<.2/>.8 D, 1-day hold | 666 | 74.1 | .47 | 0.77 | −.026 | −2.38 | 1/9 | 0.70 | 0.92 | 0.67 | −.003 | .023 |
| 4 | S1 | IBS D +SMA200 | 291 | 35.5 | .48 | 0.79 | −.023 | −1.51 | 3/9 | 0.71 | 1.06 | 0.55 | .000 | .023 |
| 5 | S1 | Bollinger(20,2) D fade → SMA20 | 134 | 15.1 | .43 | 0.64 | −.089 | −1.98 | 2/9 | 0.62 | 0.66 | 0.63 | −.055 | .034 |
| 6 | S1 | RSI2 H4 +SMA200 | 654 | 74.0 | .60 | 0.63 | −.069 | −4.09 | 0/9 | 0.54 | 0.54 | 0.76 | −.020 | .049 |
| 7 | S1 | RSI2 H4 no filter | 1683 | 187 | .58 | 0.65 | −.073 | −6.33 | 0/9 | 0.56 | 0.65 | 0.64 | −.023 | .050 |
| 8 | S1 | Bollinger(20,2.5) H4 fade | 395 | 44.0 | .47 | 0.69 | −.131 | −3.32 | 1/9 | 0.65 | 0.60 | 0.79 | −.067 | .065 |
| 9 | S1 | RSI2<5/>95 H1 +SMA200 | 1255 | 140 | .56 | 0.58 | −.083 | −6.75 | 0/9 | 0.42 | 0.64 | 0.50 | +.006 | .089 |
| 10 | S1 | Bollinger(20,2.5) H1 fade | 1699 | 189 | .47 | 0.73 | −.135 | −6.16 | 0/9 | 0.66 | 0.72 | 0.73 | −.033 | .102 |
| 11 | S1 | fade ≥1 ATR(D) from day open @11:00 NY | 195 | 22.1 | .38 | 0.47 | −.182 | −4.00 | 0/9 | 0.37 | 0.42 | 0.54 | −.072 | .110 |
| 12 | S1 | fade ≥.75 ATR from London open @11:00 NY | 256 | 29.0 | .42 | 0.57 | −.162 | −3.72 | 1/9 | 0.46 | 0.53 | 0.61 | −.050 | .113 |
| 13 | S1 | fade Asian overextension @03:00 NY | 52 | 6.1 | .42 | 0.65 | −.173 | −1.40 | 2/9 | 0.59 | 0.34 | 1.02 | −.077 | .096 |
| 14 | S1 | weekend gap fade (≥.1 ATR, target Fri close) | 99 | 11.4 | .58 | 0.87 | −.020 | −0.47 | 3/9 | 0.77 | 0.30 | 1.31 | +.024 | .044 |
| 15 | S2 | #2 + ADX(D)<20 | 102 | 12.2 | .54 | 0.78 | −.041 | −1.00 | 5/9 | 0.74 | 0.73 | 0.84 | −.007 | .034 |
| 16 | S2 | #8 + ADX(H4)<20 | 117 | 13.1 | .53 | 0.81 | −.079 | −1.05 | 4/9 | 0.77 | 0.76 | 0.85 | −.012 | .066 |
| 17 | S2 | #12 + ADX(D)<20 | 95 | 11.7 | .47 | 0.64 | −.114 | −1.73 | 2/9 | 0.51 | 0.63 | 0.66 | +.004 | .118 |
| 18 | S2 | Turtle Soup Plus One 20d (buy-stop at old low) | 41 | 4.7 | .44 | 0.95 | −.022 | −0.13 | 5/9 | 0.91 | 1.08 | 0.86 | +.071 | .094 |
| 19 | S2 | Turtle Soup close back inside 20d | 57 | 7.0 | .49 | **1.53** | +.240 | 1.18 | 7/9 | 1.44 | 1.73 | 1.41 | +.341 | .101 |
| 20 | S2 | Turtle Soup Plus One 10d | 47 | 5.4 | .38 | 0.89 | −.061 | −0.35 | 5/9 | 0.84 | 0.66 | 1.12 | +.025 | .086 |
| 21 | S2 | 5-day return z ±2 reversal | 62 | 7.2 | .45 | 0.94 | −.013 | −0.17 | 4/9 | 0.85 | 0.74 | 1.11 | +.024 | .038 |
| 22 | S2 | 3-day return z reversal (EDA-driven) | 74 | 8.6 | .50 | 0.72 | −.057 | −1.07 | 2/9 | 0.68 | 0.81 | 0.65 | −.032 | .025 |
| 23 | S3a | close-back-inside D n10 | 148 | 16.5 | .36 | 0.79 | −.120 | −1.17 | 2/9 | 0.83 | 0.77 | 0.81 | −.026 | .094 |
| 24 | S3a | close-back-inside D n5 | 394 | 44.1 | .41 | 0.90 | −.050 | −0.84 | 4/9 | 0.79 | 0.88 | 0.92 | +.052 | .102 |
| 25 | S3a | close-back-inside H4 n30 | 328 | 36.7 | .26 | 0.79 | −.161 | −1.61 | 4/9 | 0.73 | 0.80 | 0.79 | +.020 | .180 |
| 26 | S3a | close-back-inside H4 n60 | 199 | 22.3 | .29 | 0.82 | −.135 | −1.03 | 2/9 | 0.76 | 0.85 | 0.80 | +.041 | .176 |
| 27 | S3a | close-back-inside H1 n120 | 362 | 40.5 | .17 | 0.91 | −.088 | −0.49 | 4/9 | 0.80 | 0.90 | 0.91 | +.194 | .282 |
| **28** | S3b | **close-back-inside D n5, stop 1 ATR beyond extreme** | 346 | 38.7 | .46 | **1.03** | +.007 | 0.19 | 5/9 | 0.98 | 1.22 | 0.86 | +.057 | .050 |
| 29 | S3b | #27 with 1 ATR stop | 332 | 37.2 | .23 | 0.77 | −.186 | −1.68 | 4/9 | 0.72 | 0.81 | 0.74 | −.011 | .175 |
| 30 | S3b | #27 with ~5-day hold | 348 | 38.9 | .14 | 0.81 | −.189 | −1.17 | 3/9 | 0.73 | 0.96 | 0.64 | +.104 | .293 |
| 31–37 | R | neighbours of #28 (§4) | | | | 0.88–1.07 | | | | | | | | |
| 38 | diag | #28 with no_overlap=False | 538 | 60.1 | .46 | 0.95 | −.016 | −0.50 | 3/9 | 0.90 | 1.05 | 0.84 | | |

Reading: daily fades — costs only ~0.03 R/trade but pre-cost edge −0.055 to +0.02 R. H1/H4 fades — 0.05–0.10 R costs on ≈0 edge. Session-open overextension fades — −0.05 to −0.08 R even before costs (the move continues; e.g. 2013-04-12 the 11:00 NY fade was stopped 2 min later). Failed breakouts — the only family with positive pre-cost edge, driven by high-vol years (2013, 2019, 2020); the 20-day result (#19, n = 57) does not hold at n = 10 / n = 5 or on H4/H1.

## 3. Finalist selection (IS only, before VAL)
Pre-declared rule: highest IS PF among configs with IS n ≥ 200 and 25–750 trades/yr, ≤ 1 per family → #28 **`meanrev-A-failedbreak-D5`**. It already fails IS; carried through robustness and VAL only to document the pipeline. No second finalist (all other families IS PF ≤ 0.91).

Rule (daily bars ending 17:00 NY): if today's low < lowest low of the previous 5 days and today closes back above that level → BUY (mirror: SELL). Execute 120 min after the 18:00 NY reopen. Stop = today's extreme ∓ 1.0 × ATR14(D). Exit at the 3rd daily close after the signal (+120 min), max hold 166 h.

## 4. Finalist A — IS, stress, robustness, tails
| | n | /yr | win | avgW R | avgL R | PF | exp R | t | yrs+ | wk +/− | maxDD R | worst wk |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| IS | 346 | 38.7 | 46.2% | 0.63 | −0.53 | 1.026 | +0.007 | 0.19 | 5/9 | 31.3/36.8% | 18.2 | −1.9 |
| IS long | 173 | | 48.6% | 0.67 | −0.52 | 1.215 | +0.057 | 0.99 | 4/9 | | | |
| IS short | 173 | | 43.9% | 0.59 | −0.53 | 0.858 | −0.043 | −0.79 | 3/9 | | | |
| IS costs ×1.5 | | | | | | 0.975 | | | | | | |
| IS every signal traded | 538 | 60.1 | 45.9% | 0.59 | −0.53 | 0.946 | −0.016 | −0.50 | 3/9 | | 40.1 | −4.8 |

IS by year (R): 2013 +2.2, 2014 −5.1, 2015 +4.7, 2016 −5.6, 2017 −8.7, 2018 +3.4, 2019 +5.9, 2020 +8.8, 2021 −3.0. Exits: 294 time, 52 stop. Pre-cost edge ≈ +0.057 R/trade; costs ≈ 0.050 R (spread .012, slippage .016, commission .003, swap .019).

Neighbours (one parameter at a time): n = 4 → 1.002; n = 6 → 1.009; min_age = 2 → 0.875; stop_buf 0.8 → 1.012; stop_buf 1.2 → 1.003; max_bars 2 → 1.000; max_bars 4 → 1.070; **median 1.003**. The whole neighbourhood is PF ≈ 1.0 (no edge); long side 1.14–1.24 in every neighbour vs short ~0.8 → drift, not reversal.

Tails: worst 10 IS trades −1.18 R (2017-04-10 short, gap through stop) then nine stop-outs at −1.03 to −1.05 R. Worst IS weeks: 2017-06-05 −1.94 R, 2014-09-08 −1.74, 2014-02-10 −1.67, 2017-01-02 −1.50, 2018-01-08 −1.44.

IS criteria: n ≥ 200 ✓ (346); 25–750/yr ✓ (38.7); PF ≥ 1.20 ✗ (1.026); t ≥ 2 ✗ (0.19); ≥ 2/3 years ✗ (5/9); max hold ✓ (144 h); neighbour median ≥ 1.10 ✗ (1.003); stress PF ≥ 1.05 ✗ (0.975) → **FAIL**. (`weeks_pos_pct` counts no-trade weeks as flat.)

## 5. Finalist A — VAL 2022–2025 (one logged access, frozen params)
| | n | /yr | win | avgW R | avgL R | PF | exp R | t | yrs+ | wk+ | maxDD R | worst wk |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| VAL | 148 | 37.1 | 46.6% | 0.49 | −0.62 | **0.685** | **−0.104** | −1.84 | 0/4 | 29.7% | 20.9 | −2.0 |
| VAL long | 59 | | 50.8% | | | 1.072 | +0.019 | 0.21 | 3/4 | | | |
| VAL short | 89 | | 43.8% | | | 0.505 | −0.186 | −2.63 | 0/4 | | | |
| VAL every signal (diag) | 236 | 59.2 | 44.9% | 0.57 | −0.61 | 0.752 | −0.084 | −1.70 | 1/4 | | 28.5 | −2.6 |

VAL by year: 2022 −10.8, 2023 −1.3, 2024 −2.3, 2025 −1.1 R. Worst VAL weeks: 2022-02-07 −2.04 R, 2024-04-08 −2.03, 2022-08-15 −1.32, 2022-04-25 −1.32, 2023-07-10 −1.25. Worst VAL trade −1.32 R (2022-04-21 long, gap through stop). Criterion 7: **FAIL** — fading upside failed breakouts in the 2023–25 bull market lost (short PF 0.51); the long side is flat despite the tailwind.

## 6. Rejected ideas
Connors RSI(2) D ± SMA200/ADX (pre-cost ≤ 0, PF 0.68–0.78); IBS D (pre-cost ≈ 0; long-with-trend PF 1.06 at 18/yr = the uptrend); Bollinger/z fades D/H4/H1 (momentum dominates, PF 0.64–0.73); RSI(2) H4/H1 (0.05–0.09 R costs on no edge, PF 0.58–0.65); session-open and Asian overextension fades (lose before costs, PF 0.47–0.65); ADX < 20 filter (never flips the sign); weekend-gap fade (≤ 11/yr); Turtle Soup Plus One (PF 0.89–0.95, ≤ 5/yr); Turtle Soup 20d close-back-inside #19 (PF 1.53 but 7/yr and not robust to lookback → noise); 3-/5-day return reversal (PF 0.72–0.94); failed breakouts on H4/H1 (costs 0.18–0.29 R; wider stop kills pre-cost edge #29; longer hold no help #30). Not pursued: London fix / time-of-day (seasonality track), gold-vs-USD residual (cross-asset), gold/silver ratio (no silver data), 08:30 news-spike fades (no calendar; intraday fades already lose pre-cost).

## 7. Engine / data concerns
1. Whole UTC days missing from xauusd M1: 59 partial trading days (28 IS, 31 VAL, excl. Christmas/New Year), e.g. 2014-03-06, 2020-03-16, 2022-06-06, 2024-08-02. Repro: `len(gl.load_m1("xauusd").loc["2020-03-16"]) == 0`. Effects: stub daily bars enter rolling indicators as full days; open trades go ~21 h without stop checks then exit as a gap; a target crossed during the hole fills at max(target, open) — optimistic. *(Lead's note: confirmed as download failures; patching in progress.)*
2. Reopen spread trap: daily signals executed at the 18:00 NY reopen minute pay ~3× the normal spread (median $0.85).
3. `weeks_pos_pct` counts no-trade weeks as flat.
4. Live use: a partial last D bar exists if the frame ends mid-day → evaluate daily rules right after the 17:00 NY close.
5. Coordinator caveats: OCO n/a (market orders only); skip-on-activation affects only rejected #18/#20; overlap diagnostic done; IS-only decisions (truncated research data, all metrics from `cut("is")`).

## 8. Files
`lab/tracks/meanrev/`: `strategy.py` (`make_orders` for 7 families rsi/bb/ibs/sess/gap/soup/ret and `FINALISTS` — one best-effort entry, do not trade), `run.py`, `stage1.py`, `stage2.py`, `stage3a.py`, `stage3b.py`, `robustness.py`, `validate.py`, `overlap_diag.py`, `causality_check.py`, `analysis.py`, `finalize_is.py`, `trial_table.py`, `make_candidates.py`. `lab/results/meanrev/`: `trials.jsonl` (38), `trials_summary.csv`, `neighbours_A.json`, `finalist_A_is.json`, `val_meanrev-A-failedbreak-D5.json`, `overlap_diag_A.json`, `candidates.json`.

Sources: [Intraday momentum in metals futures](https://acfr.aut.ac.nz/__data/assets/pdf_file/0008/686816/4a-Z-Ivy-Zhou.pdf) · [Gold/silver futures short-term reversal (2003)](https://scholar.kyobobook.co.kr/article/detail/4010023856344) · [Gold-fix study (Bloomberg, 2014)](https://www.bloomberg.com/news/articles/2014-02-28/gold-fix-study-shows-signs-of-decade-of-bank-manipulation) · [Gold price dynamics around the clock (CBS thesis)](https://research.cbs.dk/en/studentProjects/gold-price-dynamics-around-the-clock/)
