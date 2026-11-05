# Track `crossasset` — report (IS 2013–2021 only; VAL not accessed)

*(Written by the crossasset research agent; saved to file by the lead because the agent could not write .md files.)*

## Verdict
**Nothing passes the pre-registered IS criteria. No finalist; VAL not touched** (`results/val_access.log` has no `crossasset` entry). 77 trials logged.

1. **Other markets give no tradable edge on gold at these costs.** Gold absorbs dollar moves within the same 5-minute bar; a sharp USD move in the last bar has no predictive power for gold's next 5 min–8 h (1 % tail spread 0.1–1.4 bp vs a 5.9 bp round trip). The only consistent cross-asset lead is yen strength → gold strength over 1–8 h, ~3–9 bp ≈ the cost. A London-morning variant (session chosen after looking at IS data) reaches PF 1.19 but t = 0.96.
2. **No market lets simple, untuned rules work clearly better than on gold.** 4 generic families × 6 instruments: net PF 0.70–1.05, plus one 1.30 at n = 160 (t = 1.34). Before costs, gold has the largest breakout edge of the six (H4 channel gross PF 1.25), but gold is also the most expensive market per unit of volatility (a round trip = 25 % of an H1 ATR vs 8–13 % for DAX/FX). FX/DAX lower the cost hurdle 2–3× but show no edge there even before costs. On gold the binding constraint is **cost per trade in R**: anything that works needs ≲ 0.05 R/trade, i.e. wide R units and few trades.

## 1. Setup, accounting
Gold has real bid/ask; the 5 other markets are bid-only with fixed synthetic spreads (EURUSD 1.0 pip, GBPUSD 1.5 pip, USDJPY 1.2 pip, DAX 1.5 pt, WTI 4 c; slippage 0.2–1 bp/side vs 1.5 bp for gold) → non-gold results are indicative only and the cost model mildly favours non-gold markets. Engine: `gl.simulate`, one position at a time, `evaluate_is` (normal and ×1.5 costs); every decision used the IS cut.

Trials logged: 77 = Part A 19 configs + 9 overlap-mode diagnostics; Part B 24 distinct rule × instrument configs + 7 bug-fix re-runs + 18 overlap-mode diagnostics (logged because they were looked at). Zero-cost re-simulations (`gross_vs_net.csv`) are cost diagnostics of the same configs (not logged). Thresholds changed before any performance was seen: A2c and A3b z threshold 1.5 → 1.0 (order counts implied ~11 and ~19 trades/yr).

Causality: orders generated on data truncated at an arbitrary T equal the full-data orders before T (every cross-asset generator, two values of T); the live path (raw M1 frames) gives identical orders to the cached research path. Alignment: bars labelled by start, predictor bars on the same interval; decisions at the nominal end of the interval when both gold and predictor bars are closed; entry at `gl.entry_index(m1_gold, decision)`.

## 2. Descriptive analysis (IS, no trading rule) — `descriptive/*.txt`
USD basket u = mean(ΔEURUSD, ΔGBPUSD, −ΔUSDJPY) (u > 0 = weaker dollar); β = gold's rolling beta to u (past data only).

| question | result |
|---|---|
| Contemporaneous link | corr(gold,u) 0.38 (M5) to 0.43 (D); β 0.94–1.06; corr(gold,USDJPY) −0.35..−0.40; corr(gold,DAX) −0.05..−0.12; corr(gold,WTI) ≈ 0.05 |
| Does last bar's u predict gold? | No. M5 slope t 0.8 (k=1), 1.5–1.8 (k=3–12); 1 % tail spread 0.1–1.4 bp. M15/H1 t < 1.9 |
| Gold residual (gold − βu) | Reverts at M5 (t = −8) but only ~1 bp (¼ of the cost) |
| Yen lead (USDJPY z, H1) | z < −2.5: gold +4.4 bp over 8 h (t 1.8, 9/9 years same sign); z > +2.5: −2.8 bp; \|z\| > 2 sign-adjusted: London morning +8–9 bp, Asia +3–5, NY ≈ 0 |
| DAX extreme days (5 % tails) | After DAX down days gold −21 bp next day; after up days +7 bp (t ≈ 1.6) |
| Residual momentum (24 h residual z crossing ±2) | +32 bp over 72 h (naive t 3.6, overlapping events); raw gold +4.9 bp; USD part −0.7 bp |
| Does gold lead FX/DAX? | 0.2–0.9 bp effects, below their 1.3–1.7 bp costs |

## 3. Part A — trading tests on gold (IS)
Rationales fixed before running: A1 lead-lag (gold catches up a sharp dollar move); A2 divergence (gold reverts toward its basket-implied path); A3a yen (yen strength = risk-off, gold follows the yen); A3b DAX session at the European close (safe-haven follow-through vs Baur–Lucey give-back); A4 USD-trend filter (breakouts better when the dollar confirms); A5 residual momentum (suggested by A2's losses and Blitz–Huij–Martens 2011; A5b same rule on raw gold as control). Every order has a stop and a time exit (≤ 3 trading days, 5 for A4). gross PF = zero costs (mid fills, no slippage/commission/swap); overlap PF = every signal traded.

| config | n | tr/yr | win | avgW R | avgL R | PF | t | yrs+ | wk+% | maxDD R | long n/R | short n/R | stress PF | gross PF | overlap PF |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A1a lead-lag M5 3σ 60m | 2199 | 245.6 | .316 | .652 | −.658 | 0.458 | −13.84 | 0/9 | 23.7 | 535.6 | 1129/−266 | 1070/−270 | 0.332 | 0.941 | |
| A1b lead-lag M15 3σ 120m | 793 | 88.6 | .335 | .632 | −.640 | 0.499 | −7.51 | 0/9 | 21.4 | 169.0 | 417/−104 | 376/−65 | 0.385 | 0.831 | |
| A2a divergence revert 24h | 287 | 33.2 | .436 | .458 | −.557 | 0.634 | −3.03 | 1/9 | 17.9 | 33.2 | 137/−15.4 | 150/−17.6 | 0.578 | 0.830 | 0.679 |
| A2b divergence revert 72h | 109 | 12.6 | .404 | .497 | −.674 | 0.500 | −3.03 | 2/9 | 8.6 | 22.3 | 60/−8.8 | 49/−13.1 | 0.474 | 0.584 | 0.467 |
| A2c Asia residual revert @08 LDN | 313 | 36.0 | .476 | .628 | −.737 | 0.774 | −1.86 | 2/9 | 21.5 | 28.5 | 138/−10.2 | 175/−17.1 | 0.679 | 0.977 | |
| A3a yen shock H1 all hours | 1030 | 115.6 | .436 | .580 | −.523 | 0.856 | −1.86 | 1/9 | 40.1 | 56.2 | 582/−23.5 | 448/−20.2 | 0.717 | 1.273 | 0.857 |
| A3a yen shock London morning (post hoc) | 219 | 24.8 | .493 | .782 | −.639 | **1.190** | 0.96 | 6/9 | 17.7 | 9.9 | 121/4.9 | 98/8.7 | 1.079 | 1.556 | 1.112 |
| A3b risk-off follow 16:30→21:00 | 357 | 44.5 | .378 | .174 | −.218 | 0.486 | −4.77 | 1/9 | 20.0 | 25.5 | 189/−17.9 | 168/−7.0 | 0.378 | 0.808 | |
| A3b risk-off give-back 3d | 245 | 30.5 | .469 | .983 | −.805 | 1.080 | 0.50 | 5/9 | 26.0 | 16.0 | 108/11.4 | 137/−3.0 | 0.999 | 1.262 | 1.026 |
| A4a H4 breakout + USD confirms | 430 | 47.9 | .370 | 1.098 | −.606 | 1.063 | 0.44 | 5/9 | 26.4 | 11.9 | 220/2.1 | 210/8.3 | 0.965 | 1.337 | 0.912 |
| A4b H4 breakout, USD contradicts | 198 | 22.2 | .343 | 1.228 | −.638 | 1.006 | 0.03 | 4/9 | 12.9 | 12.6 | 111/8.6 | 87/−8.1 | 0.938 | 1.236 | 1.647 |
| A5a residual momentum 24h→3d | 216 | 24.9 | .500 | .544 | −.557 | 0.977 | −0.13 | 5/9 | 22.3 | 12.5 | 120/−5.8 | 96/4.4 | 0.934 | 1.164 | 1.305 |
| A5b raw-gold momentum (control) | 228 | 25.8 | .461 | .570 | −.562 | 0.865 | −0.84 | 3/9 | 21.0 | 14.4 | 112/−7.7 | 116/−1.6 | 0.827 | 1.003 | 0.977 |

Reading: lead-lag has no signal even before costs (net −0.24 R = the cost; dollar shocks coincide with wider gold spreads); M1 lead-lag fails on arithmetic (a 3σ USD shock ≈ 3 bp of gold < 5.9 bp round trip); divergence reversion is wrong-signed; residual momentum (A5a) is flat one-position-at-a-time. Cross-asset information is real but small — gross gain per trade: yen +0.065 R; USD confirmation of breakouts 0.087 → 0.112 R; residual vs raw momentum 0.04 vs 0.00 R — an order of magnitude below the +0.2 R/trade needed for PF ≥ 1.2. Cost per trade on these designs: 0.04–0.23 R.

### Best near-miss: A3a yen shock, London morning (NOT a finalist)
| criterion | value | pass |
|---|---|---|
| n ≥ 200 | 219 | ✓ |
| PF ≥ 1.20 | 1.19 | ✗ |
| t ≥ 2 | 0.96 | ✗ |
| years ≥ 2/3 | 6/9 | ✓ |
| 25–750 trades/yr | 24.8 | ✗ |
| max hold ≤ 5 d | 9 h | ✓ |
| stress PF ≥ 1.05 | 1.079 | ✓ |
| neighbour median PF ≥ 1.10 | 1.18 | ✓ |

Neighbours: z 2.0 (n 419) PF 1.11 t 0.80; z 3.0 (124) 1.37 / 1.29; hold 6 h (221) 1.02 / 0.09; hold 10 h (218) 1.26 / 1.25; session 06–11 (217) 1.25 / 1.19; session 08–13 (346) 1.04 / 0.27. By year R: 2013 −1.8, 2014 +1.2, 2015 +1.5, 2016 +8.9, 2017 −3.0, 2018 −4.4, 2019 +1.5, 2020 +8.0, 2021 +1.6. Not a finalist because the session window was chosen after looking at IS data, every neighbour has t ≤ 1.3 (t ≥ 2 at this edge would need ~950 trades), and the pre-specified all-hours version has PF 0.86. Kept in `strategy.REFERENCE`; VAL still clean for it; not recommended.

### Overlap diagnostic
A4b and A5a reach PF 1.65 / 1.31 when every signal is traded by stacking up to 8–9 concurrent positions in the 2019–2020 rallies: A4b best 5 weeks 82.7 R of 77.4 R total, weekly-aggregated t 1.68, skipped signals +0.58 R vs taken +0.00 R; A5a best 5 weeks 37.6 R of 36.7 R, t 1.53, skipped +0.15 R vs taken −0.01 R → episodic pyramiding, not a robust edge.

## 4. Part B — market choice (IS, fixed untuned parameters, identical on all instruments)
Parameters fixed before running: **orb** — London 08:00–09:00 opening range, only the first-touched side (scanned on M1), valid until 16:00, stop at the other side, exit 20:00 London; **channel H4** — Donchian 20 close-breakout, stop 2 ATR(14), trailing 2 ATR, ≤ 5 trading days; **rsi2** — daily RSI(2) < 10 long / > 90 short, exit first close beyond SMA5 or 5 days, stop 2 ATR(D); **channel D** — same channel on daily bars (added as a 4th family with low cost per trade after the gross-vs-net diagnostic).

Net PF / n (gross PF):

| instrument | orb | channel H4 | rsi2 | channel D |
|---|---|---|---|---|
| xauusd | 0.873 / 2290 (1.145) | 1.002 / 583 (**1.254**) | 0.699 / 315 (0.839) | 0.984 / 152 (1.18) |
| eurusd | 1.019 / 2310 (1.079) | 0.766 / 641 (0.882) | 0.747 / 295 (0.823) | 0.853 / 151 (0.953) |
| gbpusd | 1.012 / 2303 (1.216) | 0.878 / 644 (1.009) | 0.954 / 314 (1.036) | 0.874 / 159 (0.97) |
| usdjpy | 0.997 / 2312 (1.15) | 0.903 / 642 (1.081) | 0.967 / 322 (1.112) | 0.813 / 145 (0.927) |
| DAX | **1.046** / 1879 (1.132) | 1.022 / 525 (1.135) | 0.775 / 286 (0.871) | 0.773 / 147 (0.856) |
| WTI | 0.890 / 2268 (1.124) | 0.990 / 633 (1.152) | 0.836 / 300 (0.919) | 1.299 / 160 (1.468) |

None passes (full metrics in `candidates.json`, `partb_table*.csv`). DAX ORB is the steadiest (7/9 years; longs +57 R, shorts −17 R) but PF 1.05, t 0.76, stress 1.01. WTI daily channel PF 1.30 on n = 160, 18/yr, t 1.34, 5/9 years — 1 cell of 24. RSI(2) fade loses everywhere, worst on gold (gross 0.84) → gold tends to continue rather than reverse at the daily horizon.

Cost vs volatility (IS medians):

| | gold | EURUSD | GBPUSD | USDJPY | DAX | WTI |
|---|---|---|---|---|---|---|
| round trip, bp | 5.9 | 1.3 | 1.7 | 1.7 | 2.2 | 9.0 |
| as % of ATR(H1) | **24.8 %** | 10.4 % | 12.3 % | 13.4 % | 8.1 % | 17.3 % |
| as % of ATR(D) | **4.5 %** | 1.8 % | 2.2 % | 2.4 % | 1.6 % | 3.1 % |

**Is gold the right market?** Gold is not uniquely bad — its pre-cost momentum is as good as or better than the others' — but it is penalised by costs 2–3× higher in volatility units (real spread + 1.5 bp slippage/side). No other market shows a pre-cost edge that its lower costs would turn into a clear net one. The fix is lower turnover and lower cost per trade in R on gold, not a different market.

## 5. Finalists
None. Per the protocol nothing went to VAL. `FINALISTS = {}`; `REFERENCE` and `regenerate()` rebuild the near-misses on any data.

## 6. Rejected ideas
M5/M15 USD-shock catch-up (no lag; PF 0.46–0.50, gross < 1); M1 lead-lag (fails on arithmetic; not run); divergence reversion (wrong sign; 0.50–0.77); residual momentum (0.98 one-at-a-time; every-signal version depends on 5 weeks); yen shock all hours (gross +0.065 R < 0.11 R cost; PF 0.86); DAX risk-off follow-through (0.49); DAX risk-off give-back (1.08, t 0.5); USD-confirmed breakout (1.06, t 0.44; contra 1.01); oil as predictor (corr 0.05, no lead; not built); gold as predictor of FX/DAX (below those markets' costs; not built); generic rules on other markets (no clear winner).

## 7. Engine notes
No goldlab bug found. Coordinator caveats: (1) OCO — the ORB emits only the first-touched side, fillable only on its trigger bar; (2) n/a (market orders); (3) overlap diagnostic done; (4) every decision used the IS cut. Own bugs fixed and re-run (7 logged re-runs): RSI2 counted 5 bars instead of 5 trading days (data gaps allowed holds up to 289 h); time exits landing in a closure were filled at the reopening (`exit_index` now exits at the last bar before the closure); the gold H4 channel was logged at PF 1.005 under the old exit rule, 1.002 with the final code. For all tracks: (1) `entry_index` on a forced-exit time inside a closure silently extends the hold beyond 192 h (seen on DAX); (2) daily-close rules enter at the widest-spread 17:00 NY reopen; (3) lighter non-gold slippage favours other markets in comparisons.

## 8. Files
`tracks/crossasset/`: `strategy.py`, `parta.py`, `partb.py`, `explore_*.py`, `diag_*.py`, `make_candidates.py`, `common.py`. `results/crossasset/`: `trials.jsonl`, `candidates.json`, `gross_vs_net.csv`, `overlap_diag.csv`, `overlap_deep.csv`, `partb_table*.csv`, `descriptive/*.txt`.
