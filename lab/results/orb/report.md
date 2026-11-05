# Track `orb` — opening-range breakouts on XAUUSD

**Verdict: no opening-range breakout on gold clears the pre-registered bar.** The one finalist,
`orb_asia_2d_buf10` (Asian range breakout held about 2 days), narrowly **fails IS criterion 2**
(PF 1.196 < 1.20, t 1.99 < 2.0). It passes all the other IS criteria and nominally passes VAL
(PF 1.115, +0.074 R/trade), but its VAL t-stat is 0.84. Its edge came from whichever side
matched the period's big trend: shorts in IS (2013 crash), longs in VAL (2024-25 rally). On the
same signal traded every day (positions allowed to overlap), IS PF is only 1.06. I would not
build an EA on it. If the lead wants one ORB entry for the 2026 holdout, this is the only one,
at low conviction.

48 configurations were evaluated on IS (all logged in `results/orb/trials.jsonl`), 1 validation
access (`results/val_access.log`), 0 re-tuning after VAL.

## 1. Set-up (causality and costs)

* Engine: `goldlab.simulate` with the frozen cost model (Dukascopy bid/ask spread, 1.5 bp slippage per
  side on stop/market fills, $0.07/oz commission, swaps), `no_overlap=True` (one position at a
  time), and costs ×1.5 for the stress test via `evaluate_is`.
* Range = M1 bars whose **start** is in `[range_start, range_end)` in London or New York wall clock
  (DST handled per date with `tz_localize`). The range high is the **max Ask**, the low is the
  **min Bid**. Orders are only active from the first M1 bar starting at or after `range_end`, i.e.
  after the range's last minute has closed.
* OCO stop orders: the engine has no OCO (see §5), so `strategy.make_orders` scans forward from
  the range end. It finds the first M1 bar where Ask ≥ buy level or Bid ≤ sell level and sends a
  single stop-entry order filled on that bar (gap-aware fill by the engine). That is exactly what a
  live OCO pair does. If both levels are touched in the same minute, the level nearer the bar
  open is taken and the engine checks the stop inside the bar (pessimistic). This never happened
  for the finalist.
* Daily ATR(14) and trend filters use the last trading day (17:00 NY) completed before the range
  end (`merge_asof`, backward).
* Research harness (`tracks/orb/research.py`): orders are cut to IS dates **before** simulation, so
  no VAL trade was simulated during research. Every config is logged once (a cache prevents
  double-logging).

## 2. What was tested and why (48 trials, 6 stages, each declared before running)

| Stage | Trials | Question |
|---|---|---|
| 1 screen | 7 | Canonical ORB for each session: Asian range 00-07 LDN; London open 30/60 min; COMEX open 08:20 NY 15/30 min; US equity open 09:30 15 min; Zarattini-Aziz 5-min first-bar (10R target). OCO stops, opposite-side stop, exit 16:00 NY. |
| 2 cost/filters | 14 | Attack the cost share (0.5×ATR stop; skip if est. cost > 15% of risk; 2R target; 2-day hold), Crabel narrow-range filter, and drift controls (unconditional long/short 07:00 LDN→16:00 NY). |
| 3 hold | 5 | Hold-length profile 1/3/4 days on the Asia breakout; does a 2-day hold carry over to the London/US ranges? |
| 4 filters/exits | 5 | Ideas left from the brief, on the best base (A3): prior-day trend, SMA50 trend, 10% buffer, break-even at 1R, 4-day hold + 1×ATR trail. |
| 5 neighbours | 14 | Robustness of the pre-declared finalist F3 (±20% continuous, adjacent cell for clock/discrete params). |
| 6 diagnostic | 3 | Path dependence: same F3 signal with overlap allowed (every day traded), hold 1/2/3. |

### Key findings

**(a) Costs dominate intraday ORB on gold.** Round-trip cost is about **$0.80/trade** (spread +
2×1.5 bp slippage + commission). Median IS ranges are small: London 30 min $2.7, COMEX 15 min
$3.5, US 15 min $3.0, Asia 7 h $6.3. With range-based stops, cost is therefore 0.13-0.51 R per
trade. The table below decomposes the logged IS trades (`results/orb/gross_vs_net_is.json`). Cost = half
the bar spread at entry and at exit + slippage + commission + swap; gross = net + cost.

| config | gross R/trade | cost R/trade | net R/trade | gross long | gross short |
|---|---|---|---|---|---|
| S1 Asia 00-07 LDN, intraday | +0.109 | 0.134 | −0.025 | +0.046 | +0.172 |
| S2 London 08:00-08:30 | +0.190 | 0.288 | −0.097 | +0.116 | +0.264 |
| S3 London 08:00-09:00 | +0.143 | 0.229 | −0.085 | +0.067 | +0.215 |
| S4 COMEX 08:20-08:35 | +0.018 | 0.235 | −0.216 | +0.012 | +0.025 |
| S5 COMEX 08:20-08:50 | +0.028 | 0.191 | −0.162 | +0.034 | +0.023 |
| S6 US 09:30-09:45 | +0.162 | 0.260 | −0.098 | +0.145 | +0.180 |
| S7 Zarattini 5-min first bar | +0.088 | 0.512 | −0.424 | +0.022 | +0.154 |
| C1 control: short 07:00 LDN | +0.068 | 0.114 | −0.046 | – | +0.068 |
| C2 control: long 07:00 LDN | −0.041 | 0.114 | −0.156 | −0.041 | – |
| A3 Asia, hold 2 days | +0.257 | 0.160 | +0.097 | +0.220 | +0.292 |
| **F3 finalist** (A3 + 10% buffer) | +0.270 | 0.139 | +0.132 | +0.188 | +0.353 |

So there **is** a small gross breakout signal after the London open, the Asian range and the US
equity open: about +0.1-0.2 R, or roughly $0.3-0.6 per trade. It is smaller than the costs. There
is **none** at the COMEX 08:20 open (gross ≈ 0, so fading it is no better). The drift controls show
that London→NY hours drifted down in IS (short-minus-long ≈ 0.11 R). That is why shorts beat longs
in every London-based config: it is time-of-day drift in 2013-2021, not a breakout property.

**(b) Filters do not rescue the intraday versions.** Fixed 2R targets hurt (winners need room).
Narrow ranges (Crabel) are worse. The cost-share filter and the 0.5×ATR stop only bring results
up to about breakeven. Prior-day and SMA50 trend filters lower PF.

**(c) Only multi-day holding of the Asian-range breakout turns net positive**, because the cost
becomes small relative to a 2-day move. It is fragile:
* The hold-length profile is not smooth: PF 0.95 / 1.03 / 1.13 / 1.00 / 1.13 for 0-4 days with no
  buffer, and 1.03 / **1.20** / 1.02 for 1/2/3 days with the 10% buffer.
* It does not carry over: London 08-09 held 2 days gives PF 1.01; US 09:30 held 2 days gives PF 0.91.
* **Path dependence** (stage 6): trading every day's signal with overlap allowed gives IS PF
  0.99 / 1.06 / 1.08 for 1/2/3-day holds (t −0.2 / 0.85 / 1.0). Longs lose (PF 0.84-0.93) and only
  shorts win. F3's PF 1.196 comes mostly from which days the one-position rule happened to skip.
* The money is made in trend years: 2013 shorts give +79 R of F3's +135 R IS total. Without 2013,
  IS PF is 1.08 (+0.053 R/trade).

## 3. Finalist `orb_asia_2d_buf10` (chosen on IS before any VAL access)

Rules (EA-ready, London / New York wall clock):
1. At 07:00 London, take the Asian range 00:00-07:00 London: H = max Ask, L = min Bid,
   W = H − L. Skip the day if fewer than 50% of the minutes have data.
2. Arm an OCO pair valid until 12:00 London: Buy Stop at H + 0.1·W (triggers on Ask), Sell Stop at
   L − 0.1·W (triggers on Bid). The day's signal is the FIRST touch of either level. Take it only
   if flat at that moment (a position from an earlier day may still be open). Otherwise there is no
   trade that day: one trade per day at most, no second chance.
3. Stop loss is the opposite level (long: L − 0.1·W; short: H + 0.1·W). No target, no trailing.
4. Time exit: close at 16:00 New York, two business days after the entry day. The longest IS hold
   was 159 h, which is within 5 trading days.
5. Size each trade as a fixed % risk on the distance from entry to stop.

### IS (2013-2021) vs VAL (2022-2025), normal costs

| metric | IS | VAL |
|---|---|---|
| trades | 1028 | 438 |
| trades / year | 114.2 | 109.8 |
| win rate | 33.7% | 34.5% |
| avg win / avg loss (R) | +2.385 / −1.012 | +2.096 / −0.989 |
| expectancy (R/trade) | +0.132 | +0.074 |
| profit factor (R) | **1.196** | **1.115** |
| t-stat | 1.99 | 0.84 |
| total R | +135.2 | +32.6 |
| years positive | 7/9 | 3/4 |
| % positive weeks (all weeks) | 46.4% | 49.8% |
| max drawdown (R) | 50.3 | 30.0 |
| worst week (R) | −5.2 | −5.3 |
| costs ×1.5: PF | 1.121 | 1.061 |
| **long**: n / PF / R/trade / t / total R | 517 / 1.057 / +0.039 / 0.46 / +20.3 | 233 / 1.219 / +0.139 / 1.13 / +32.3 |
| **short**: n / PF / R/trade / t / total R | 511 / 1.342 / +0.225 / 2.23 / +114.9 | 205 / 1.002 / +0.001 / 0.01 / +0.2 |
| avg / max hold (h) | 42.0 / 159.2 | 47.2 / 114.0 |

R by year:
* IS: 2013 +86.9 · 2014 +32.2 · 2015 +9.5 · 2016 +10.5 · 2017 +6.0 · 2018 −30.4 · 2019 +6.1 · 2020 +25.7 · 2021 −11.2
* VAL, long / short:
  * 2022: −17.1 / +2.2
  * 2023: +0.1 / +6.3
  * 2024: +26.6 / −10.1
  * 2025: +22.7 / +1.8

### Neighbour robustness (IS, one parameter at a time; F3 itself has PF 1.196)

| neighbour | n | PF | t | R/trade | yrs+ | stress PF | long PF | short PF |
|---|---|---|---|---|---|---|---|---|
| buffer 0.00 (A3) | 1146 | 1.134 | 1.41 | +0.097 | 7/9 | 1.062 | 1.066 | 1.199 |
| buffer 0.08 (−20%) | 1044 | 1.216 | 2.18 | +0.146 | 7/9 | 1.138 | 1.075 | 1.364 |
| buffer 0.12 (+20%) | 1006 | 1.213 | 2.11 | +0.141 | 7/9 | 1.140 | 1.083 | 1.348 |
| buffer 0.20 | 910 | 1.160 | 1.58 | +0.103 | 7/9 | 1.086 | 1.037 | 1.282 |
| hold 1 day | 1247 | **1.029** | 0.36 | +0.018 | 4/9 | 0.956 | 0.912 | 1.139 |
| hold 3 days | 894 | **1.021** | 0.20 | +0.016 | 5/9 | 0.969 | 0.921 | 1.124 |
| range end 06:00 | 1095 | 1.151 | 1.60 | +0.105 | 6/9 | 1.073 | 1.058 | 1.243 |
| range end 08:00 | 886 | 1.168 | 1.61 | +0.108 | 6/9 | 1.093 | 0.997 | 1.343 |
| range start 23:00 (prev. evening) | 989 | 1.115 | 1.20 | +0.076 | 7/9 | 1.043 | 0.998 | 1.234 |
| range start 01:00 | 1057 | 1.187 | 1.89 | +0.129 | 7/9 | 1.111 | 1.053 | 1.325 |
| entry until 11:00 | 1002 | 1.185 | 1.86 | +0.125 | 6/9 | 1.110 | 1.042 | 1.337 |
| entry until 13:00 | 1063 | 1.136 | 1.47 | +0.092 | 7/9 | 1.062 | 1.022 | 1.255 |
| exit 14:00 NY | 1028 | 1.180 | 1.85 | +0.121 | 7/9 | 1.105 | 1.063 | 1.303 |
| exit 18:00 NY | 1028 | 1.159 | 1.64 | +0.107 | 7/9 | 1.083 | 1.031 | 1.293 |
| stop at range midpoint | 1270 | 1.150 | 1.42 | +0.131 | 5/9 | 1.032 | 1.111 | 1.187 |

**Median neighbour PF = 1.159** (≥ 1.10, passes). The clock and buffer choices are not knife-edge,
but **hold length is**: 1 or 3 days gives PF ≈ 1.02-1.03. The ±20% buffer neighbours pass every IS
check while F3 itself misses by 0.004 PF. That is noise at the threshold, and I kept the
pre-declared F3 rather than switching to the best neighbour.

### Pass / fail against PROTOCOL.md

| # | criterion | value | result |
|---|---|---|---|
| 1 | n ≥ 200; 25-750 trades/yr | 1028; 114/yr | pass |
| 2 | PF ≥ 1.20 and t ≥ 2.0 | 1.196; 1.99 | **FAIL** (both, narrowly) |
| 3 | ≥ 2/3 of years positive | 7/9 | pass |
| 4 | max hold ≤ 5 trading days | 159 h | pass |
| 5 | median neighbour PF ≥ 1.10 | 1.159 | pass (hold-length neighbours 1.02-1.03) |
| 6 | costs ×1.5, PF ≥ 1.05 | 1.121 | pass |
| 7 | VAL PF ≥ 1.10 and expectancy > 0 | 1.115; +0.074 R | pass (nominal; t = 0.84) |
| 8 | HOLDOUT 2026 PF > 1.0 | – | not run (lead's call) |

Overall: **FAIL** under the protocol, because criterion 2 failed on IS. IS and VAL pooled give about
1466 trades at +0.115 R (t ≈ 2.1), before any adjustment for 48 trials. The near-identical buffer
neighbours and the hold-length cliff point to a weak, trend-year-dependent effect, not an edge.

## 4. Rejected ideas (one line each)

* **COMEX open 08:20 NY (15/30-min ORB)**: gross ≈ 0 R before costs (t −7 and −6 net). No breakout information, so a fade is no better.
* **Zarattini-Aziz 5-min first-bar at 08:20**: the 5-min range ($1.7) makes cost 0.51 R/trade, PF 0.57.
* **London open 30/60 min, US open 15 min, intraday**: real-looking gross +0.14-0.19 R, but cost 0.23-0.29 R. PF 0.85-0.88.
* **Asian range, intraday exit**: gross +0.11 R vs cost 0.13 R, PF 0.95.
* **0.5×ATR stop (decoupled from the range)**: about breakeven at best (PF 0.86-0.95).
* **Cost-share filter (est. cost ≤ 15% of risk)**: PF 0.92-0.98, fewer trades, no gain.
* **Fixed 2R target**: worse in all three families (PF 0.79-0.91). Winners need to run.
* **Crabel narrow-range filter (width ≤ ~median ATR fraction)**: worse (PF 0.81-0.91).
* **2-day hold on London/US ranges**: PF 1.01 / 0.91. The multi-day effect is Asia-only.
* **Prior-day or SMA50 trend filter**: lowers PF (1.07 / 1.08 vs 1.13) and leaves the long side negative.
* **Break-even at 1R; 4-day hold with 1×ATR trail**: PF 1.13 / 1.16, both below the 2-day F3. Not selected.
* **Day-of-week filter**: not tested. No prior rationale, and every weekday was positive for F3 in IS.

## 5. Engine / protocol concerns (no change made to `goldlab/`)

1. **No native OCO; same-`entry_i` pending orders are processed in row order.** With a buy-stop and
   a sell-stop both active from the same bar, the engine fills whichever row comes first, even if
   the other level is touched earlier. Minimal repro on synthetic data: price dips to 99 at minute 2
   then rallies to 103. Buy-stop 101.5 (row 0) and sell-stop 99.5 (row 1), both `entry_i=0`,
   `expiry_i=9`. Result: the long fills at 08:05 and the sell-stop touched at 08:02 is SKIPPED. A real
   OCO pair would have gone short at 08:02 and been stopped out at 101.5. Workaround used here:
   compute the first touch causally, then submit one order on that bar. Other tracks using paired
   stop orders should check this.
2. **`no_overlap` tests the activation index (`entry_i`), not the fill.** A pending order that
   activates while a trade is open is dropped even if it would fill after that trade closes. This is
   conservative, but it changes which signals are traded. It does not affect this track, since
   `entry_i` is the fill bar.
3. **Path dependence of single-path `no_overlap` results.** For multi-day holds, PF moved between 1.02
   and 1.20 just from which days got skipped. The every-day ensemble for the same signal gave PF
   ≈ 1.06. I suggest every track report an overlap-allowed diagnostic next to any multi-day result.
4. **Stress ×1.5 is applied after the orders are built.** Ranges and levels come from normal quotes,
   and only the fills and exits see the wider spread. This slightly understates the stress for
   strategies whose levels depend on bid/ask extremes. The effect is minor.
5. **`evaluate_is` returns the full trade frame, including VAL trades** (only the report is cut to IS),
   so a VAL peek is one line away. My harness cuts orders to IS before simulating.

## 6. Files

* `tracks/orb/strategy.py`: `make_orders(m1, **params)` (works on any M1 frame, checked on a
  6-week late-2025 frame) and `FINALISTS`.
* `tracks/orb/research.py`: IS-only harness (log, cache). `stage1.py` to `stage6.py`: the declared
  trial lists. `finalize.py`: candidates and neighbour stats. `val_run.py`: the single VAL access
  (it refuses a second one).
* `results/orb/trials.jsonl` (48 trials), `research_cache.jsonl`, `candidates.json`,
  `gross_vs_net_is.json`, and this report.

Reproduce: `cd lab/tracks/orb && python3 stage1.py && ... && python3 stage6.py && python3 finalize.py`.
Cached configs are not re-logged. Do NOT re-run `val_run.py`.

## Appendix: all 48 IS trials (normal costs; stress = costs ×1.5)

| # | label | stage | n | /yr | win | avgW R | avgL R | exp R | PF | t | yrs+ | DD R | stress PF | long PF | short PF |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | S1_asia_00-07ldn | 1-screen | 1993 | 221.6 | 0.393 | 1.303 | -0.884 | -0.025 | 0.954 | -0.79 | 3/9 | 114.7 | 0.865 | 0.841 | 1.07 |
| 2 | S2_ldn_08-0830 | 1-screen | 2260 | 251.3 | 0.235 | 3.105 | -1.078 | -0.097 | 0.882 | -2.05 | 1/9 | 301.9 | 0.766 | 0.794 | 0.97 |
| 3 | S3_ldn_08-09 | 1-screen | 2159 | 240.1 | 0.283 | 2.308 | -1.028 | -0.085 | 0.884 | -2.08 | 2/9 | 246.0 | 0.778 | 0.784 | 0.98 |
| 4 | S4_comex_0820-0835 | 1-screen | 2281 | 253.6 | 0.303 | 1.578 | -0.996 | -0.216 | 0.688 | -7.06 | 0/9 | 500.3 | 0.595 | 0.685 | 0.692 |
| 5 | S5_comex_0820-0850 | 1-screen | 2248 | 249.9 | 0.354 | 1.213 | -0.914 | -0.162 | 0.726 | -5.89 | 0/9 | 372.8 | 0.630 | 0.739 | 0.712 |
| 6 | S6_us_0930-0945 | 1-screen | 2278 | 253.3 | 0.343 | 1.589 | -0.979 | -0.098 | 0.848 | -2.8 | 2/9 | 265.8 | 0.721 | 0.828 | 0.872 |
| 7 | S7_zarattini_0820_5m | 1-screen | 2293 | 255.0 | 0.156 | 3.672 | -1.179 | -0.424 | 0.574 | -9.81 | 0/9 | 973.4 | 0.432 | 0.508 | 0.642 |
| 8 | A1_asia_atr0.5 | 2-cost/filters | 1992 | 221.6 | 0.441 | 0.894 | -0.743 | -0.020 | 0.951 | -0.87 | 4/9 | 91.3 | 0.867 | 0.829 | 1.082 |
| 9 | A2_asia_cost15 | 2-cost/filters | 1254 | 139.5 | 0.427 | 1.08 | -0.823 | -0.011 | 0.977 | -0.31 | 4/9 | 51.8 | 0.900 | 0.799 | 1.167 |
| 10 | A3_asia_hold2d | 2-cost/filters | 1146 | 127.3 | 0.298 | 2.766 | -1.033 | +0.097 | 1.134 | 1.41 | 7/9 | 43.8 | 1.062 | 1.066 | 1.199 |
| 11 | A4_asia_narrow0.30 | 2-cost/filters | 684 | 76.1 | 0.33 | 1.806 | -0.981 | -0.060 | 0.909 | -0.96 | 2/9 | 86.5 | 0.810 | 0.754 | 1.071 |
| 12 | A5_asia_tgt2R | 2-cost/filters | 1993 | 221.6 | 0.412 | 1.152 | -0.886 | -0.046 | 0.912 | -1.8 | 2/9 | 131.0 | 0.828 | 0.85 | 0.976 |
| 13 | L1_ldn60_atr0.5 | 2-cost/filters | 2158 | 240.0 | 0.433 | 0.852 | -0.713 | -0.035 | 0.914 | -1.63 | 2/9 | 108.6 | 0.825 | 0.836 | 0.993 |
| 14 | L2_ldn60_cost15 | 2-cost/filters | 387 | 43.4 | 0.351 | 1.548 | -0.913 | -0.048 | 0.918 | -0.61 | 3/9 | 57.5 | 0.856 | 0.652 | 1.215 |
| 15 | L3_ldn60_tgt2R | 2-cost/filters | 2159 | 240.1 | 0.344 | 1.551 | -1.031 | -0.144 | 0.787 | -5.25 | 0/9 | 328.4 | 0.690 | 0.709 | 0.865 |
| 16 | L4_ldn60_narrow0.15 | 2-cost/filters | 500 | 55.7 | 0.196 | 3.606 | -1.092 | -0.171 | 0.805 | -1.64 | 2/9 | 88.9 | 0.700 | 0.528 | 1.071 |
| 17 | U1_us15_atr0.5 | 2-cost/filters | 2277 | 253.3 | 0.437 | 0.57 | -0.514 | -0.041 | 0.860 | -2.7 | 3/9 | 109.4 | 0.749 | 0.836 | 0.885 |
| 18 | U2_us15_cost15 | 2-cost/filters | 299 | 33.3 | 0.421 | 0.957 | -0.731 | -0.019 | 0.954 | -0.32 | 3/9 | 17.1 | 0.848 | 0.859 | 1.022 |
| 19 | U3_us15_tgt2R | 2-cost/filters | 2278 | 253.3 | 0.374 | 1.313 | -0.98 | -0.123 | 0.799 | -4.92 | 1/9 | 303.9 | 0.684 | 0.697 | 0.917 |
| 20 | C1_ctrl_short0700 | 2-cost/filters | 2293 | 255.0 | 0.411 | 1.121 | -0.861 | -0.045 | 0.910 | -1.76 | 3/9 | 201.1 | 0.815 | - | 0.91 |
| 21 | C2_ctrl_long0700 | 2-cost/filters | 2293 | 255.0 | 0.369 | 1.073 | -0.873 | -0.156 | 0.717 | -6.57 | 1/9 | 361.7 | 0.636 | 0.717 | - |
| 22 | A6_asia_hold1d | 3-hold | 1387 | 154.1 | 0.335 | 2.052 | -1.0 | +0.021 | 1.032 | 0.39 | 4/9 | 88.1 | 0.962 | 0.944 | 1.113 |
| 23 | A7_asia_hold3d | 3-hold | 981 | 109.0 | 0.251 | 3.103 | -1.041 | -0.002 | 0.997 | -0.03 | 5/9 | 95.1 | 0.935 | 0.971 | 1.023 |
| 24 | A8_asia_hold4d | 3-hold | 871 | 96.8 | 0.239 | 3.78 | -1.054 | +0.101 | 1.126 | 1.1 | 5/9 | 61.6 | 1.052 | 1.065 | 1.186 |
| 25 | L5_ldn60_hold2d | 3-hold | 1466 | 162.9 | 0.181 | 4.968 | -1.09 | +0.005 | 1.006 | 0.07 | 5/9 | 117.2 | 0.913 | 0.92 | 1.088 |
| 26 | U4_us15_hold2d | 3-hold | 1570 | 174.6 | 0.159 | 5.373 | -1.118 | -0.088 | 0.906 | -1.12 | 4/9 | 272.4 | 0.826 | 0.834 | 0.982 |
| 27 | F1_A3_trend_prevday | 4-filters/exits | 747 | 83.0 | 0.274 | 2.954 | -1.044 | +0.053 | 1.071 | 0.62 | 5/9 | 64.4 | 0.987 | 0.957 | 1.184 |
| 28 | F2_A3_trend_sma50 | 4-filters/exits | 778 | 88.3 | 0.272 | 2.998 | -1.04 | +0.060 | 1.080 | 0.69 | 5/9 | 64.2 | 1.007 | 0.93 | 1.224 |
| 29 | F3_A3_buf0.1 | 4-filters/exits | 1028 | 114.2 | 0.337 | 2.385 | -1.012 | +0.132 | 1.196 | 1.99 | 7/9 | 50.3 | 1.121 | 1.057 | 1.342 |
| 30 | F4_A3_be1R | 4-filters/exits | 1270 | 141.1 | 0.198 | 3.056 | -0.669 | +0.070 | 1.131 | 1.23 | 6/9 | 67.1 | 1.057 | 1.037 | 1.226 |
| 31 | F5_asia_hold4_trail1atr | 4-filters/exits | 1004 | 111.5 | 0.278 | 2.884 | -0.955 | +0.112 | 1.162 | 1.44 | 5/9 | 53.9 | 1.087 | 1.048 | 1.284 |
| 32 | N01_buf0.08 | 5-neighbours-F3 | 1044 | 116.0 | 0.336 | 2.439 | -1.016 | +0.146 | 1.216 | 2.18 | 7/9 | 51.1 | 1.138 | 1.075 | 1.364 |
| 33 | N02_buf0.12 | 5-neighbours-F3 | 1006 | 111.8 | 0.344 | 2.329 | -1.007 | +0.141 | 1.213 | 2.11 | 7/9 | 48.1 | 1.140 | 1.083 | 1.348 |
| 34 | N03_buf0.20 | 5-neighbours-F3 | 910 | 101.1 | 0.357 | 2.082 | -0.997 | +0.103 | 1.160 | 1.58 | 7/9 | 49.1 | 1.086 | 1.037 | 1.282 |
| 35 | N04_hold1 | 5-neighbours-F3 | 1247 | 138.6 | 0.359 | 1.757 | -0.957 | +0.018 | 1.029 | 0.36 | 4/9 | 86.4 | 0.956 | 0.912 | 1.139 |
| 36 | N05_hold3 | 5-neighbours-F3 | 894 | 99.3 | 0.268 | 2.859 | -1.028 | +0.016 | 1.021 | 0.2 | 5/9 | 83.9 | 0.969 | 0.921 | 1.124 |
| 37 | N06_rangeend06 | 5-neighbours-F3 | 1095 | 121.6 | 0.316 | 2.543 | -1.021 | +0.105 | 1.151 | 1.6 | 6/9 | 53.6 | 1.073 | 1.058 | 1.243 |
| 38 | N07_rangeend08 | 5-neighbours-F3 | 886 | 98.6 | 0.348 | 2.17 | -0.99 | +0.108 | 1.168 | 1.61 | 6/9 | 36.0 | 1.093 | 0.997 | 1.343 |
| 39 | N08_rangestart23 | 5-neighbours-F3 | 989 | 109.9 | 0.339 | 2.186 | -1.004 | +0.076 | 1.115 | 1.2 | 7/9 | 55.0 | 1.043 | 0.998 | 1.234 |
| 40 | N09_rangestart01 | 5-neighbours-F3 | 1057 | 117.5 | 0.325 | 2.515 | -1.018 | +0.129 | 1.187 | 1.89 | 7/9 | 45.8 | 1.111 | 1.053 | 1.325 |
| 41 | N10_entryend11 | 5-neighbours-F3 | 1002 | 111.3 | 0.333 | 2.41 | -1.017 | +0.125 | 1.185 | 1.86 | 6/9 | 50.9 | 1.110 | 1.042 | 1.337 |
| 42 | N11_entryend13 | 5-neighbours-F3 | 1063 | 118.1 | 0.331 | 2.318 | -1.01 | +0.092 | 1.136 | 1.47 | 7/9 | 43.2 | 1.062 | 1.022 | 1.255 |
| 43 | N12_exit14ny | 5-neighbours-F3 | 1028 | 114.2 | 0.333 | 2.377 | -1.004 | +0.121 | 1.180 | 1.85 | 7/9 | 50.7 | 1.105 | 1.063 | 1.303 |
| 44 | N13_exit18ny | 5-neighbours-F3 | 1028 | 114.2 | 0.331 | 2.36 | -1.006 | +0.107 | 1.159 | 1.64 | 7/9 | 53.4 | 1.083 | 1.031 | 1.293 |
| 45 | N14_stopmid | 5-neighbours-F3 | 1270 | 141.3 | 0.195 | 5.141 | -1.085 | +0.131 | 1.150 | 1.42 | 5/9 | 68.9 | 1.032 | 1.111 | 1.187 |
| 46 | D1_F3_overlap_hold1 | 6-diag-overlap | 1805 | 200.6 | 0.354 | 1.729 | -0.961 | -0.009 | 0.986 | -0.22 | 3/9 | 121.7 | 0.915 | 0.839 | 1.133 |
| 47 | D2_F3_overlap_hold2 | 6-diag-overlap | 1805 | 200.6 | 0.309 | 2.391 | -1.009 | +0.042 | 1.060 | 0.85 | 5/9 | 123.7 | 0.984 | 0.896 | 1.228 |
| 48 | D3_F3_overlap_hold3 | 6-diag-overlap | 1805 | 200.6 | 0.279 | 2.872 | -1.032 | +0.058 | 1.078 | 1.01 | 6/9 | 130.9 | 1.003 | 0.927 | 1.231 |
