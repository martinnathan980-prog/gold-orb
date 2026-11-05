# Seasonality track (XAUUSD) — report

*(Written by the seasonality research agent; saved to file by the lead because the agent could not write .md files.)*

**Verdict: NOTHING SURVIVES.** Gold has real, statistically robust intraday seasonal patterns in 2013–2021, but almost all are 1–2 bp per hour against a round-trip cost of ~5.7 bp. The only cost-sized effect — a gold-specific Friday-afternoon / weekend drift (+6 bp gross Fri 13:30→16:45 NY, t 4.9; +9 bp Fri 13:30 NY→Sun 22:00 NY, 9/9 years) — nets to ≈0 after costs, faded after 2016, fails every pre-registered profitability criterion on IS, and lost on VAL (PF 0.78 / 0.81) despite gold +136 % in 2022–2025. **No seasonality EA is recommended.**

24 engine configs evaluated and logged (budget 150); the descriptive phase examined ~450 overlapping cells (§2.8). Two finalists fixed on IS before VAL; both fail IS; each run once on VAL for information (`results/val_access.log`: WKND_LIM, FRI_PM_LIM, plus one diagnostic placebo).

## 1. Method and cost yardstick
- IS 2013–2021 only; the trial runner loads data only up to 2022-01-10, so no 2022–2025 trade was ever simulated during research.
- Descriptive stats: mid prices, log returns in bp, windows in local exchange time (London / New York / Beijing, DST-aware). Price at time T = open of the first M1 bar ≥ T. t = mean/(sd/√n). "yrs" = number of IS years (of 9) whose yearly mean has the same sign as the overall mean. Winsorised (1/99 %) t-stats checked — consistent.
- Cost yardstick at the IS mean price $1,398: spread 2.2 bp + slippage 1.5 bp × 2 + commission 0.5 bp ≈ **5.7 bp per round trip** (+1.4 bp swap if a long is held overnight). Confirmed by the engine (T01: +6.22 bp mid→mid, +0.39 bp fill→fill, −0.12 bp net).
- Long-beta check: in IS gold rose 9.2 % in 9 years, i.e. an unconditional drift of +0.017 bp per trading hour — negligible; a few-hour long trade in IS is not "gold went up". In VAL the drift is 0.37 bp/h → controlled with a placebo (§5).

## 2. Descriptive statistics (IS, gross, mid, bp)

### 2.1 Sessions ("gold up in Asia, down in US hours")
| session | n | mean bp | t | yrs same sign |
|---|---|---|---|---|
| Asia 18:00 NY(prev) → 08:00 LDN | 2238 | +1.59 | +1.79 | 7/9 |
| London 08:00 LDN → 08:20 NY | 2294 | −0.70 | −0.82 | 3/9 |
| US/COMEX 08:20 → 13:30 NY | 2241 | −1.64 | −1.23 | 7/9 |
| NY late 13:30 → 17:00 NY | 2222 | +0.33 | +0.50 | 5/9 |
| NYSE hours 09:30 → 16:00 NY | 2224 | −0.89 | −0.70 | 6/9 |
| outside NYSE hours | 1749 | +1.88 | +1.15 | 5/9 |

True in sign but weak (~±1.6 bp/day ≈ ¼ of the cost). As trades: T05 Asia-long PF 0.69 (0/9 years positive), T06 US-short PF 0.82 (1/9).

### 2.2 Hour of day (London clock)
| hour | bp | t | yrs |
|---|---|---|---|
| 07–08 | −1.27 | −3.44 | 8/9 |
| 06–07 | +0.79 | +2.54 | 6/9 |
| 14–15 | −1.49 | −2.36 | 8/9 |
| 05–06 | +0.49 | +2.06 | 7/9 |

All hours within ±1.5 bp. Weekday × hour grid (115 London cells): 8 with |t|>2 (5.2 expected by chance), 1 with |t|>3 (0.3 expected) = Friday 19:00 London (14:00 NY) +2.4 bp t 3.5, part of the Friday effect. NY clock (110 cells): 10 with |t|>2 (5.0 expected), none with |t|>3.

### 2.3 Weekday, Friday afternoon, weekend
Close-to-close by weekday: Mon −1.0, Tue −3.6, Wed −0.7, Thu +1.8, Fri +5.5 bp (t 1.25, 7/9).

| window (NY) | mid bp | t | bid→bid | ask-buy/bid-sell | yrs |
|---|---|---|---|---|---|
| Fri 13:30 → 16:45 | +5.96 | +4.9 | +5.51 (t 4.6) | +3.33 | 8/9 |
| Mon–Thu 13:30 → 16:45 | −1.38 | −1.8 | | | 8/9 negative |
| Fri 16:50 → 17:00 | +0.73 | +2.9 | −1.72 | −5.00 | spread blow-out artifact |
| weekend gap (Fri 16:45 → Sun open) | +4.53 | +3.9 | +2.96 (t 2.5) | | 7/9 |
| Fri 13:30 → Sun 22:00 | +9.24 | +3.87 | | | 9/9 (sd 49.8) |

Decay of Fri 13:30–16:45 by year 2013→2021: 14.2, 7.9, 10.3, 8.4, 3.5, 0.8, −1.2, 10.1, 0.6 bp. NFP Fridays +10.0 bp vs other Fridays +4.8 (t 3.5). After a down week +8.2 bp (t 4.2) vs +4.2 after an up week (consistent with pre-weekend short covering). Gold-specific: EURUSD +0.4 bp (t 0.7) in the same window; USDJPY −0.3 bp Fri vs +1.4 Mon–Thu. Literature: [Weekday effects on gold (Tokyo, London, New York)](https://businessperspectives.org/index.php/journals/banks-and-bank-systems/issue-190/weekday-effects-on-gold-tokyo-london-and-new-york-markets); informal mechanism: [The Friday gold trade](https://beyondpassive.substack.com/p/the-friday-gold-trade-a-conditional).

### 2.4 London fix
| window | bp | t | yrs | old fix (<2015-03-20) / ICE auction |
|---|---|---|---|---|
| AM 15 min before | −0.82 | −5.2 | 5/9 | −0.97 / −0.77 |
| AM 5–15 min after | +0.69 | +5.3 | 9/9 | +0.93 / +0.61 |
| AM 2 h before | −1.38 | −2.8 | 4/9 | −5.22 (t −4.0) / −0.14 |
| PM 15 min before | −0.99 | −3.0 | 9/9 | −0.95 / −1.01 |
| PM 60 → 30 min before | −0.46 | −1.2 | 4/9 | −3.08 (t −3.9) / +0.39 |

Dip into the fix and rebound after it, but < 1 bp (smaller than the spread). The large pre-fix declines were a pre-2015 phenomenon and vanished with the ICE auction.

### 2.5 US data, NFP, FOMC
- 08:30 NY data window: no directional drift (< 1 bp), except 08:30→10:00 −1.8 bp (t −2.1).
- NFP (108 BLS release dates): pre-release −7.1 bp (t −1.5); first reaction ~47 bp in size but ≈0 on average; neither fading nor following works (t −0.15). NFP-day afternoon +9.6 bp = the Friday effect.
- FOMC (71 statement days, 14:00 NY): 24 h before +6.9 bp (t 0.9); first reaction tends to continue (corr +0.45): following it earns +15 bp by 16:45 (t 2.3) and +42 bp by the next day (t 2.3); day after FOMC −26.5 bp (t −1.8). Only 8 events/year → can never meet ≥25 trades/yr and n ≥ 200.

### 2.6 Turn of month, Monday gap, Beijing clock
- Turn of month (last day + first 3): +4.5 bp/day (t 1.0) vs −0.6 otherwise; 1 of 11 cells |t|>2 (chance).
- Monday gap: average weekend gap +4.2 bp; after a gap up the first hour fills −3.9 bp (t −1.9, n.s.; opening spread is wide).
- Beijing clock: 13:00–14:00 +1.35 bp (t 4.5), 10:00–11:00 +1.03 (t 3.5), 11:00–12:00 −0.73 (t −2.8) — real but ~1 bp.

### 2.7 What counts as robust
Bonferroni bar for ~450 cells (|t| ≳ 3.9) AND same sign ≥ 7/9 years AND a known mechanism. Qualifying: Friday PM / weekend drift, AM-fix dip/rebound, Beijing 13:00 hour, weekend gap (borderline). Only the Friday/weekend drift is cost-sized → the only effect turned into strategies.

### 2.8 Multiple-testing tally
~450 heavily overlapping cells examined. Under the null, ~20 would show |t|>2 and ~1 |t|>3 by chance.

## 3. Strategy trials (24 logged, IS)
Common: stop 3 × ATR(14) on 1 h bars at decision time (~80 bp, disaster stop); decision at a fixed local time; entry at the next M1 bar (market) or buy-limit at the last bid valid 60 min ("limit"); forced exit at a fixed local time.

| id | rule | n | PF (R) | t | yrs+ | stress PF |
|---|---|---|---|---|---|---|
| T01 | Fri 13:30→16:45 NY, market | 437 | 0.798 | −1.73 | 4/9 | 0.537 |
| T02 | Fri 13:30→Sun 22:00 NY, market | 447 | 0.981 | −0.15 | 3/9 | 0.793 |
| T03 | Fri 13:30→16:45, limit at bid | 360 | 0.953 | −0.33 | 4/9 | 0.706 |
| T04 | Fri 13:30→Sun 22:00, limit at bid | 368 | 1.039 | 0.26 | 4/9 | 0.851 |
| T05 | Asia long 19:00 NY→07:00 LDN | 2281 | 0.686 | −6.65 | 0/9 | 0.525 |
| T06 | US short 08:20→13:30 NY | 2238 | 0.817 | −3.80 | 1/9 | 0.708 |
| +18 | neighbours of T03/T04 | | 0.87–1.05 | | | |

The limit entry fills ~82 % of the time and saves the 1.5 bp entry slippage (PF 0.80→0.95 Friday, 0.98→1.04 weekend). In equal-notional returns the best variant reaches PF 1.16, but in the protocol's R units it is 1.04, because ATR sizing over-weights the quiet 2017–19 years when the effect had vanished. "After a down week" variant not run: ~24 trades/yr fails the ≥25/yr floor by construction.

## 4. Finalists (Fridays only; entry 13:30 NY buy-limit at last bid valid 60 min; stop 3 × ATR(14, 1 h))
WKND_LIM exits Sunday 22:00 NY (Mon 03:00 London); FRI_PM_LIM exits Friday 16:45 NY.

| metric | WKND IS | WKND IS ×1.5 | WKND VAL | FRI IS | FRI IS ×1.5 | FRI VAL |
|---|---|---|---|---|---|---|
| n | 368 | 351 | 162 | 360 | 344 | 159 |
| trades/yr | 41.0 | 39.1 | 40.8 | 40.1 | 38.4 | 40.1 |
| win rate | 0.508 | 0.467 | 0.426 | 0.458 | 0.407 | 0.465 |
| avg win / loss R | +0.378 / −0.376 | +0.374 / −0.386 | +0.427 / −0.408 | +0.196 / −0.174 | +0.190 / −0.185 | +0.173 / −0.187 |
| expectancy R | +0.0071 | −0.0306 | −0.0528 | −0.0044 | −0.0322 | −0.0193 |
| PF (R) | 1.039 | 0.851 | 0.775 | 0.953 | 0.706 | 0.807 |
| t | 0.26 | −1.09 | −1.27 | −0.33 | −2.35 | −0.96 |
| years positive | 4/9 | 2/9 | 0/4 | 4/9 | 4/9 | 1/4 |
| % positive weeks | 39.0 | 33.9 | 32.7 | 35.2 | 29.9 | 35.6 |
| max DD R | 13.1 | 22.1 | 16.2 | 10.1 | 15.4 | 5.5 |
| long n / R | 368 / +2.6 | 351 / −10.8 | 162 / −8.5 | 360 / −1.6 | 344 / −11.1 | 159 / −3.1 |

By-year R — WKND IS: 2013 +3.3, 2014 −0.2, 2015 +1.6, 2016 −2.7, 2017 −5.7, 2018 +1.2, 2019 −0.4, 2020 +8.9, 2021 −3.3; VAL 2022 −2.9, 2023 −3.8, 2024 −1.3, 2025 −0.5. FRI IS: +2.2, +1.9, +2.0, +1.3, −1.9, −1.7, −2.9, −0.4, −2.1; VAL +1.1, −1.9, −1.4, −0.8.

Neighbour robustness (9 each: entry ±30 min, adjacent exit, stop ±20 %, limit window ±20 %, limit offset +0.1 ATR): WKND median PF 1.026 (1.054 / 0.963 / 1.025 / 1.036 / 0.989 / 1.010 / 1.026 / 1.030 / 1.047); FRI median 0.953 (0.871 … 1.022). Smooth, flat around PF 1.

Pass/fail (both): n ≥ 200 ✓, 25–750/yr ✓, max hold ✓, PF ≥ 1.20 ✗, t ≥ 2 ✗, ≥ 2/3 years ✗, stress PF ≥ 1.05 ✗, neighbour median PF ≥ 1.10 ✗, VAL PF ≥ 1.10 ✗, VAL expectancy > 0 ✗. Overlap-allowed: identical trade set, nothing skipped.

## 5. VAL interpretation (post hoc, nothing re-tuned)
Gross VAL drifts: Fri 13:30–16:45 +3.4 bp (t 1.85); Mon–Thu same window +1.6 bp ≈ bull-market drift (0.37 bp/h × 3.25 h ≈ 1.2) → the Friday excess fell from ~+7.4 bp (IS) to ~+1.8 bp (VAL). Weekend gap +4.0 bp (4/4 years); Fri 13:30→Sun 22:00 +5.1 bp (vs +9.2 IS). Placebo (same rule Mon–Thu in VAL) PF 0.78 (n 688): the rally did not rescue a long-only rule because costs dominate. The effect roughly halved out of sample and is far below costs; VAL is consistent with IS.

## 6. Rejected ideas
Asia-long / US-short (±1.6 bp/day vs ~6 bp cost; PF 0.69 / 0.82); single-hour effects (~1 bp); London-fix dip/rebound (< 1 bp); turn of month (t≈1, 12 events/yr); FOMC momentum / day-after (8/yr); NFP drift/fade (none); 08:30 window (no drift); Monday gap fade (t −1.9, wide opening spread); Friday after a down week (~24/yr < 25 floor); month-of-year (9 obs/cell); pre-holiday (12 cases); exiting Friday 16:55–17:00 (spread doubles — artifact).

## 7. Engine / data concerns
1. ~60 non-holiday trading days have only 1–2 h of M1 data (e.g. 2014-01-10 NFP, 2022-03-16 FOMC, 2023-03-17, 2023-03-24, 2025-06-20, 2025-07-11, 2025-08-29). Date-keyed rules silently skip them. *(Lead's note: confirmed — these are download failures; a re-download returns full days. To be patched after all tracks finish.)*
2. Limit fills on touch at the level with no slippage — slightly optimistic (~+0.1 PF here).
3. PF in R vs PF in equal-notional returns can diverge a lot under ATR sizing (1.04 vs 1.16 here).
4. The coordinator's caveats (OCO, activation-bar skipping, overlap, evaluate_is returning all periods) do not affect this track.

## 8. Reproduction
`lab/tracks/seasonality/`: `strategy.py` (`make_orders`, `FINALISTS`; needs ≥ 14 completed 1 h bars before the first decision), `calendars.py` (FOMC / NFP dates), `common.py`, `desc1..7_*.py`, `trials.py`, `run_neighbors.py`, `cost_check.py`, `final_eval.py` (one-time VAL run). `lab/results/seasonality/`: `desc*.txt`, `trials.jsonl`, `trials_full.jsonl`, `trials_log.txt`, `neighbors.json`, `cost_check.txt`, `final_eval.txt`, `candidates.json`.

Sources: [FOMC calendars](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm) and federalreserve.gov `fomchistoricalYYYY` pages; [BLS Employment Situation archive](https://www.bls.gov/bls/news-release/empsit.htm); [Weekday effects on gold](https://businessperspectives.org/index.php/journals/banks-and-bank-systems/issue-190/weekday-effects-on-gold-tokyo-london-and-new-york-markets); [Beyond Passive — The Friday gold trade](https://beyondpassive.substack.com/p/the-friday-gold-trade-a-conditional).
