# ClaudeRobot — build specification v1

One MT5 Expert Advisor holding the ten validated rules, their sizing and protections, for FP Markets (Raw, `.r` symbols, hedging, 1:500) on the MetaQuotes VPS. New code only, in `lab/robot/` (`lab/robot/spike/` is read-only). Lab data in sample only (bars before 2022-01-01, sliced when read), `NUMBA_CACHE_DIR` under /tmp, never `lab/holdout_raw` or 2026.

## 0. Principles

1. A **paper chain** per sleeve: `goldlab/sim.py` run bar by bar on the broker's closed M1 bars. It alone decides entries, the one-position rule and exits; account skips never change it.
2. The account **follows**: market orders only, broker stop = paper stop, close when the paper exits.
3. **No persistent state**: every start and every bar revision rebuilds everything from the broker's history.
4. **Proof by replay**: the shipped file, translated to C++, replays in-sample bars against the lab code (spike: brk72 BTC 632 of 645 trades bit for bit; the 13 others are lab exits before closures nobody could foresee).

VPS, checked (mql5.com/en/vps/rules, MT5 migration help, MQL5 article 994): no DLL; EAs migrate with their chart, scripts do not; ≤ 500,000 bars; restarts for updates and maintenance; global variables not migrated, sync one-way (files written there count as lost, forum 363057); `TERMINAL_VPS` flags it; one EA may trade four symbols (ClaudeMains.mq5:56).

## 1. Layout

S0 creates every `src/` file with final signatures and stub bodies; each file then belongs to its step (§8) and only its owner edits it. Adding a rule = one rule file, one registry row with its `case` lines, one `ref_lab.py` entry.

| File | Owns | Step |
|---|---|---|
| `src/ClaudeRobot.mq5` | properties, inputs, includes | S0 |
| `src/CR_Types.mqh`, `CR_Registry.mqh` | §2.4 structs; symbol and sleeve tables, dispatch | S0 |
| `src/CR_Journal.mqh` | §2.6; French pushes with the hands' limits (ClaudeMains.mq5:163-184) | S0 |
| `src/CR_Main.mqh` | handlers, startup machine, minute driver | S0, then K |
| `src/CR_Clock.mqh` | §2.1 | A |
| `src/CR_Math.mqh`, `CR_Bars.mqh` | rolling primitives; §2.2 | B |
| `src/CR_Paper.mqh` | §2.5 | C |
| `src/CR_Rule_IdxUS.mqh` | session grid, daily ATR, N30, OC4 | D |
| `src/CR_Rule_Brk72.mqh`, `CR_Rule_F1.mqh`, generated `CR_F1Model.mqh` | BKB, BKE, F1B, F1E | E |
| `src/CR_Rule_NqBtc.mqh` | NQB | F |
| `src/CR_Rule_GoldFri.mqh`, `CR_Rule_Orb.mqh` | GFP, ORX | G |
| `src/CR_Rule_Donch.mqh` | D4H | H |
| `src/CR_Ledger.mqh`, `CR_Sizing.mqh` | §5 | I |
| `src/CR_Broker.mqh`, `CR_Follower.mqh`, `CR_Guards.mqh` | the only trade sender; §4; §6, instance lock, self-test | J |
| generated `src/CR_Golden.mqh`, `tools/gen_golden.py` | self-test vectors | K |
| `tools/amalgam.py`, `tools/gen_f1_model.py` | single file; F1 constants | S0, E |
| `check/to_cpp.py`, `mql5_shim.h`, `mock_replay.h` | the spike's three files, extended | S0 |
| `check/mock_faults.h` | broker failures (S0 includes a stub) | J |
| `check/export_frames.py`, `ref_lab.py`, `compare.py`, `run_tests.py` | §7 | S0 |

**Single file.** `amalgam.py` inlines the local includes recursively (once each, in order), keeps `<Trade\Trade.mqh>`, refuses non-ASCII, and writes `dist/ClaudeRobot.mq5` with `#define CR_BUILD "<12 hex of its sha256>"`, plus `dist/ClaudeRobot_debug.mq5` (`CR_DEBUG`: aggregate lines, bar dump). Integration tests translate the dist file.

**Install** (Mac, once): copy to MQL5/Experts and compile (0 errors, 0 warnings); Max bars in chart 500000, restart; show the four `.r` symbols, remove ClaudeMains; attach to one XAUUSD.r M1 chart, check `SELFTEST` and four `READY` lines; migrate "Experts and indicators". Inputs are changed locally, then migrated again.

| Input | Default | Meaning |
|---|---|---|
| `InpTrade` | true | false = paper only |
| `InpRiskTable` | `0:1;12000:0.5` | F1S (the lead's advice); F2S = `0:2;6000:1;12000:0.5`; `from:pct` pairs, from increasing from 0, pct in (0, 5]; rate = pct of the last pair with from ≤ max(balance, paid in) (growth.py:93-98, 118-120) |
| `InpPaidIn` | 0 | 0 = deal history; > 0 = this constant |
| `InpStopFallPct`, `InpStopArmPaid` | 25, 12000 | §6 |
| `InpSleeves` | ALL | codes allowed to trade (others: paper only) |
| `InpDailyLockStakes`, `InpFridayCloseHHMM` | 0, 0 | off (§6) |
| `InpExtraClosures` | "" | dates: extra NYSE closures, gold early-close Fridays |
| `InpRestartAfter` | 0 | restarts the plan after a permanent stop (§5) |
| `InpPush` | true | push notifications |

**MQL5 subset** (spike report §7): no pointers, virtual functions, templates, function macros, `#import`, `Sleep`; structs by reference; one global `CTrade`; `(datetime)` casts in range `CopyRates`; no `string + number`; `(long)` time differences; plain-typed inputs; 17-digit literals. Builds: `g++ -std=c++17 -O2 -ffp-contract=off`, plus one sanitizer build.

## 2. Conventions

### 2.1 Time (CR_Clock)
- UTC seconds inside. Server = NY + 7 h: UTC = server − 3 h if the US is on summer time at (server − 3 h), else − 2 h (pont.py:37-43). US summer time: 2nd Sunday of March 07:00 UTC to 1st Sunday of November 06:00 UTC; UK: last Sundays of March and October, 01:00 UTC.
- Server week from Monday 00:00 (stake.py:89-91, 131); the 17:00-NY trading day is the server date (data.py:45-49).
- `AddTradingDays(t, n)`: n business days later at the same server time; a weekend start counts Monday as day 1 (pandas BDay, trend/strategy.py:107-111).
- NYSE calendar: port of `us_holidays` (idxus_lib.py:52-83) + `InpExtraClosures`. Gold early-close Fridays: the day after Thanksgiving + `InpExtraClosures`.
- Closures, NY clock, the lab frames' shape (map `simulateur` facts 5-7): XAU 17:00-18:00 daily and Friday 17:00 to Sunday 18:00; US100 16:15-18:00 daily and Friday 16:15 to Sunday 18:00; crypto Friday 16:55 to Sunday 17:00. An earlier broker session end (`SymbolInfoSessionTrade`) wins.
- `ExitMinute(x)`, the lab's 30-minute rule (data.py:95-104): x inside a known closure [c0, c1) with x < c1 − 30 min → c0 − 1 min.

### 2.2 Bars, barrier, depth (CR_Bars)
- Names by `Resolve` (ClaudeMains.mq5:206-226). M1 only, read by time range (`CopyRates(sym, PERIOD_M1, from, to)`), never by position, which loses a just-closed bar (map `mains` pitfall 0). Chart mode must be bid.
- Bar = UTC start, bid O/H/L/C, spread. Ask = `NormalizeDouble(bid + spread × point, digits)` on all four prices; mid = (bid + ask)/2 — the lab frames' structure (build_fp_frames.py:41-45).
- Mask, counted: bid-flat bar equal to the previous close (prep_round2.py:49); server weekend (:53); crypto from Friday 23:55 server (build_fp_frames.py:31-33); US100 16:15-17:59 NY; XAU 17:00-17:59 NY.
- **Barrier M**: every symbol has ticked at or after M, or `TimeTradeServer()` ≥ M + 2 s, or is in a closure; bars before M are then final. A minute that ticked but whose bar is not returned is retried 30 s, then `GAP`. The last 3 bars are re-read each minute; a change → `LATEBAR` → rebuild (§4.6), at most one per 5 min.
- Depth: XAU 120 days, others 60. Decision: twice every measured warm-up and chain resync (maps `us100` 8, `ml` 8, `leadlag` 11, `or-seances` 7, `or-tendance` 18-19; donch ATR within 4e-15 at 120 days); about 120,000 gold bars. A symbol is ready when its history covers the depth and two reads 2 s apart agree; until then its sleeves are NOT_READY.

### 2.3 Identifiers

| id | code | lab sleeve (sort key) |
|---|---|---|
| 1, 2 | N30, OC4 | noise30_us100, ocm4_us100 |
| 3, 4 | BKB, BKE | brk72_24h_wd_btcusd, _ethusd |
| 5, 6 | F1B, F1E | F1_brk_ridge_filter_btcusd, _ethusd |
| 7 | NQB | nq_btc_follow_btcusd (reads US100) |
| 8, 9, 10 | GFP, D4H, ORX | GOLD_FRI_PM_xauusd, donch4h_stop_xauusd, orb_asia_2d_buf10_xauusd |

Magic = 20261200 + id (the hands: 20261110). Comment `CR <code> <yymmddhhmm>` (decision, UTC), informative only. Ids 11-12: orb_asia on BTC/ETH, registered, disabled; 13-19: Addendum J; never reused. Multi-leg rules give their legs one group number: all or none, closed together.

### 2.4 Rule interface
One class per rule, one object per sleeve, `switch(kind)` dispatch (no virtual calls): `Init(sleeve)` (frozen constants, each with its file:line); `OnBar(sym, const CrBar &b, CrOut &out)` for each kept closed bar of its symbols, in time order (ties by symbol id), **before** the paper engine; `OnMinute(M, CrOut &out)` after barrier M, on bars before M only; `LatestExit(dec)`, the time exit implied by a decision.

`CrOrder`: sleeve, oid (decision × 100 + id), side, etype (0 market, 1 stop, 2 limit, 3 OCO), level, level2; activation = window [t_from, t_to] (first bar starting inside) or `after_exit_of` an oid (first bar after its exit bar and before t_to; void with it); expiry_excl; stop or stop_dist; trail, be, target (0 = none); x_sched (exit at the first bar at or after it, through `ExitMinute` when the gap flag is set); dec; group. `CrExit`: oid + window, exit at the first bar inside (void if none). Rules keep the lab's own validity conditions; READY only gates real orders.

### 2.5 Paper engine (CR_Paper)
Port of sim.py `_run` (:68-211), fed after the rule's `OnBar`, for each closed bar b: (1) the open trade — time exit at b's open if b starts at or after the exit minute and is not the fill bar, then stop (at the stop on the fill bar, later at the worse of stop and open; reason `trail` once moved), then target, then best, trail and break-even for the next bar (:136-204); (2) orders activating on b — skipped if the trade is open or exited on b (:80-82); fills per :87-111; OCO with both levels touched → the side against the bar's move, bc ≥ bo → short (trend/strategy.py:303-317); stop absolute or fill ∓ dist, a wrong-side stop exits on the fill bar as `gap` (:117-127); the fill bar is then managed as in (1). Stamps: entry = fill bar start; exit = exit bar start, + 60 s unless `time` (:283-284). ss, sm = fp_costs.json slip_stop, slip_mkt bps × 1e-4 (XAU 1.0/0.3, US100 0.5/0.2, BTC 1.5/0.5, ETH 2.0/0.7). Ties keep emission order. Two pending orders of one sleeve at once = `ERROR` (sim.py settles it with future bars; it cannot occur in the ten rules). Events `PFILL`, `PEXIT`, `PSTOP`; no swap, no end-of-data exit.

### 2.6 Journal
`CR|<utc>|<EVENT>|<code>|k=v|…` (utc = lab time of the event) to `Print` and `MQL5/Files/ClaudeRobot/<yyyymmdd>.log` (30 days); doubles by `DoubleToString(x,-16)` (exact round trip). Events: INIT, SELFTEST, READY, NOTREADY, DEC, PFILL, PEXIT, PSTOP, SIZE, SEND, FILL, SLMOD, CLOSE, REFUSED, ADOPT, ORPHAN, DUP, MISSED, LATEBAR, GAP, REBUILD, CLOCK, STOP, GUARD, LOCK, ERROR. Pushes: STOP, GUARD, LOCK, CLOCK, ORPHAN, MISSED, REFUSED, ERROR, NOTREADY over 10 min, a daily summary.

## 3. The ten rules

[a, b] = the first bar starting in [a, b]; "gap" = exit through `ExitMinute`; NY times; formulas are ported exactly from the lines cited; "Dev" points to §9.

**N30 noise30 · US100** `{lookback 14, first_min 600, step 30, last_min 930, exit_min 955, vm 1.0}` idx_us/strategy.py:297-299; code :216-257; grid idxus_lib.py:113-158. Grid rows (shared with OC4): NY weekday dates with bars, not NYSE holidays; tradable = not a half day, from 2014-01-01 (:66, 114-116). O = mid open of [09:30, 09:31]; P(T) = mid close of the last bar before T, NaN if more than 11 min old. State pos ∈ {−1, 0, 1}, blind to paper stop-outs. At T = 10:00 … 15:30 every 30 min: s = mean of |P/O − 1| at the same check over the 14 previous rows (≥ 9 values); ub = fmax(O, pc)(1+s), lb = fmin(O, pc)(1−s), pc = the previous row's P(16:00); void unless P, s finite and [T, T+5] precedes the exit bar. Back inside (long: P < ub; short: P > lb) → `CrExit` [T, T+5], pos 0; then, pos 0 and P > ub (long) or P < lb (short) → market [T, T+5], or `after_exit_of` that exit (before the exit bar), absolute stop fmax(O, pc) long / fmin(O, pc) short, x 15:55 gap. State commits when the check's bar is seen. Dev 9.2 (1 exit in 8 years).

**OC4 ocm4 · US100** `{n 4, stop atr, k 0.3, exit_min 955, size_min 1.0, size_win 20, atr_n 14, sides both}` strategy.py:303-305; code :127-168; ATR idxus_lib.py:161-198. At 09:34 on tradable rows: O and C = P(09:34) finite, ≥ 3 bars in [09:30, 09:34), move = C/O − 1 ≠ 0, side = sign(move), |move| ≥ median of the 20 previous rows (≥ 10 values). ATR = mean of 14 TRs of 17:00-NY days with ≥ 600 bars (per-bar mid extremes, fmax TR), last day ended by 09:34. Market [09:34, 09:39], stop_dist 0.3 ATR, x 15:55 gap. Dev 9.2.

**BKB/BKE brk72_24h_wd · BTC, ETH** `{n 72, stop_atr 3, hold_h 24, dow weekday}` + defaults `{atr_n 24, max_delay_min 5}` crypto/strategy.py:242-243, 43-56; code :82-178; wrapper recalc.py:44-54. UTC hour bars of mids (per-bar mid extremes); empty hours absent. At each UTC hour D on a UTC weekday, with ≥ 73 bars: close strictly beyond the extreme of the 72 previous closes → side; ATR24 = mean TR (first TR = h − l) > 0. Market [D, D+5], stop_dist 3 ATR, x D + 24 h gap (Friday 23:54 server); dropped if the exit bar does not follow the entry bar. Dev 9.2 (spike: 13 of 645 BTC trades).

**F1B/F1E F1_brk_ridge_filter · BTC, ETH** `{stop_k 2.0, hold_h 13, model B1_ridge_full.json, q 0.5}` + `{n 14, h0 2, h1 16, last_dec_h 15, vol_n 70, exit_hm 1555, max_wait_min 5}` ml/strategy.py:295-297, 55-69; code :82-189; score :195-212. Session bars = UTC-hour **bid** bars with NY start hour 2-15 on NY weekdays; look-backs count session bars. At t_dec, the close of a session bar starting at or before 14:00: the 15 features of `candidates()` (seq and opp include 15:00 bars; pdd and dret use the previous NY date with session bars), a breakout, all finite, A > 0; score = intercept + Σ coef × clip(z, ±4) + 5 dummies, taken if ≥ 0.027922380451488427. `gen_f1_model.py` writes `B1_ridge_full.json["frozen"]` as `%.17g`, refusing it unless its sha256 is d191cbbcc2fc4d2cae31182f14f412069a194b69c2a9d9ae6bca0d0f5dee644e. Market [t_dec, t_dec+5], stop_dist 2A, x 15:55 the same day, gap. Dev 9.2 (3 BTC, 1 ETH orders).

**NQB nq_btc_follow · BTC, leader US100** `{leader us100, pred lead, sess uscash, dirn 1, k 1, z 6, hold 60, stop 2.0}` + `{sig_days 20}` leadlag/strategy.py:328-334, 188-189; code :188-238. Per UTC minute and market: r = log of the mid close over the last close within 4 minutes, when a bar exists; σ = RMS of the valid r of the previous 28,800 minutes, ≥ 4,800 values (:113-134); running sums, re-summed daily. At barrier g+1: g a NY weekday minute in [09:30, 16:00), bars of both markets at g, |r_L(g)| ≥ 6 σ_L(g), σ_B finite → BTC market [g+1, g+2] on the side of r_L, stop_dist 2 σ_B √60 × BTC mid close at g, x entry + 60 min gap. Dev 9.2.

**GFP GOLD_FRI_PM · XAU** `{NY, entry 13:30, exit 16:45, weekdays (4,), side 1, stop_atr 3, atr_n 14, atr_tf 1h, limit, limit_min 60, min_prev 0, skip_early_close}` + `tol_min 5` overnight/strategy.py:243-244, 100-103; code :100-211; ATR :71-97. Fridays at 13:30, except early-close Fridays or a broker session ending before 16:55 (replaces the after-the-fact test :129-137). Level = bid close of the last bar before 13:30; stop_dist = 3 × Wilder ATR (1/14, seeded with the second hour's TR) of UTC-hour bars (h = (max bh + max ah)/2, l likewise, c = last mid close), at the 12:00 hour. Limit buy activating on [13:30, 13:35], filling on bars starting before 14:30; x first bar ≥ 16:45, no gap rule. Dev 9.1, 9.3.

**D4H donch4h_stop · XAU** `{donchian, 4h, n 60, entry stop, stop_atr 2, trail_atr 2, max_days 5, atr_n 14, sides both, grid utc}` trend/strategy.py:427-429; code :257-318; bars data.py:61-77; ATR :88-92. UTC 4h bars: bid and ask aggregated apart, mid h = (max bh + max ah)/2, t_close = last bar + 1 min, empty buckets absent; Wilder ATR seeded with the second bar's TR. At each non-empty bucket end with 60 bars: OCO at the extremes of the last 60 including this one, activating on the first bar ≥ t_close and filling only within that bar's 4h bucket (the lab's window); skipped whole if the paper is busy at activation; stop_dist = trail = 2 ATR; x AddTradingDays(t_close, 5) − 5 min, gap. Dev 9.1, 9.2 (none in sample).

**ORX orb_asia_2d_buf10 · XAU** `{LDN, 00:00-07:00, entry_end 12:00, stop, buf_frac 0.1, opp, exit 16:00 NY, hold_days 2, min_bars_frac 0.5, sides both}` orb/strategy.py:276-287; code :95-271. London weekdays at 07:00 London: H = max ask high, L = min bid low of [00:00, 07:00) (≥ 210 bars, W = H − L > 0); levels H + 0.1W and L − 0.1W. The first bar in [07:00, 12:00) touching a level (both: the one nearer the mid open, tie long) uses up the day whatever the paper state; from `OnBar` at that bar: a stop order at that level, window = expiry = that bar, stop = the other level, x first bar ≥ 16:00 NY on the London date + 2 business days, no gap rule. Dev 9.1.

## 4. Follower (CR_Follower, CR_Broker)

At barrier M, after `OnBar` and `OnMinute(M)`:
1. **Entries.** A market order becomes an intent when it activates (the symbol's first tick at or after t_from, in a minute ≤ t_to) and its sleeve's paper trade ended on an earlier bar; stamp = that minute. A stop, limit or OCO order becomes an intent at its `PFILL` on bar i: stamp i, sent at barrier i+1. **Decision**: market one bar late — not broker pending orders or tick emulation — so real and paper never disagree on which trades exist; in-sample cost: donch −0.023 R a trade, orb +0.049 USD against the level (the lab assumes +1 bp), GFP +0.002 USD (maps `or-tendance` 22, `or-seances` 24 and 1.7). Intents are sized (§5) by stamp, then lab sleeve name in byte order (stake.py:108); sendable until stamp + 5 min (the lab's tolerance), then `MISSED`.
2. **Send** with the hands' DoOpen checks (ClaudeMains.mq5:760-860): tick ≤ 10 s old, hedging, Algo Trading on, volume floored to the step, notional ≤ 20 × balance, stop beyond `STOPS_LEVEL` on the right side, deviation 2 spreads; after the fill the stop is verified and the risk must be ≤ 1.25 × budget, else close (`REFUSED`). Positions and deals of the magic since the stamp are checked first: one intent, one trade; an unknown result is re-checked after 2 s.
3. **Stops.** Broker stop = paper stop on the tick grid, away from the price (spike `GridStop`, SpikeRobot.mq5:48-66), so a grid quote touches both together. Distance stops start from the quote and move to the paper stop at `PFILL`; `PSTOP` moves it again; a stop the price has already crossed → close.
4. **Exits** at the barrier of the paper's exit minute and on `PEXIT`. A real stop hit first leaves the sleeve busy until the paper exits. Retries every 10 s, 60 s if the market is closed (Watch, :698-739).
5. **Ownership**: magic 20261201-20261299 only; deals attach by `DEAL_POSITION_ID` (broker stop deals may carry magic 0: RobotDeals, :340-367).
6. **Startup and rebuild.** `OnInit` checks inputs and symbols, runs the self-test and starts a 100 ms timer. `OnTimer` then (a) waits for the connection and history; (b) rebuilds the ledger; (c) replays the history through rules, paper and dry sizing, orders off; (d) reconciles — a same-side robot position opened within 5 min of its sleeve's open paper trade's stamp → `ADOPT`, stop reset; any other → close (`ORPHAN`); duplicates → keep the first (`DUP`); a paper trade without position → nothing if its position already closed, an intent inside its send window, else `MISSED` or a sizing skip; (e) goes live. A NOT_READY sleeve enters nothing; its position keeps its stop and closes at `LatestExit(dec)` from the comment. `LATEBAR`, or a reconnection after more than 60 s, reruns (b)-(d).
7. **One trading copy.** Orders need `InpTrade`, and on a real account `TERMINAL_VPS` (the Mac copy observes; its journal is a twin). `GlobalVariableTemp` + `SetOnCondition` refuse a second instance.

## 5. Account (CR_Ledger, CR_Sizing)

- **Ledger** from `HistorySelect(0, now)` at startup and each `OnTradeTransaction`: payments = `DEAL_TYPE_BALANCE`, amount in `DEAL_PROFIT` (Capital(), :565-619); one close event per robot position, money = Σ profit + swap + commission + fee, stamped like the lab (sim.py:283-284): SL, TP or SO exit in minute X → X + 60 s, EA close → X; other money at its deal time. Σ deals must equal `ACCOUNT_BALANCE` within 60 s; a constant gap = one opening payment.
- **At stamp S** (payments ≤ S, then closes < S: growth.py:189-215): balance B; paid in P = Σ payments, or `InpPaidIn`; ref = first payment, then max(ref + A, balance just after) at each payment A (:212).
- **Week unit**, set at the week's first ledger event (a close or a sizing request): rate(max(B_w, P_w))% × B_w (:274). w = robot close money stamped this week before S / unit; deposits and manual trades never count.
- **m** = 1 if w ≤ 0, else min(1, max(0.25, w/4)) (stake.py:184-185; cushion_only :472-473).
- **Lots** = floor(B × rate(max(B, P)) × m / 100 / per_lot / step + 1e-9) × step (growth.py:295-296); per_lot = risk × tick_value_loss / tick_size; risk = |paper fill (else quote + lab slippage) − stop|, or stop_dist.
- **Checks** in the lab's order (growth.py:297-309, account.py:104-113): guards (`STOPPED`, `LOCK`, `FRIDAY`, `CLOCK`, `NOTREADY`, `OBSERVE`, `PREV_OPEN`), `MIN_LOT` (never rounded up), `CAP` (6 positions, or 2 per symbol, counting closes stamped ≥ S), `MARGIN` (Σ `OrderCalcMargin` + new > B). Skips never touch the paper.
- `InpRestartAfter` = T: history before T becomes one payment of B(T); the stop latch restarts.

## 6. Protections (CR_Guards)

- **Plan stop** (growth.py:245-252; F1S/F2S :75-76): after each booked close, P ≥ `InpStopArmPaid` and B ≤ ref × (1 − `InpStopFallPct`/100) → close all, stopped for good (`STOP`). Derived from history, it survives restarts.
- **Disaster guard** (constant): equity ≤ 50 % of ref → the same (`GUARD`). Outside the plan; F1S falls 50 % in no path on paper or at half edge (sixth review).
- **Daily lock** (X stakes): the server day's robot money ≤ −X × rate × the day's first balance → flat until the next day. Off by default: the plan has none, and the hands' 6 % lock fires early in most F2S paths (sixth review).
- **Friday close**: when set, close all and block entries from that Friday server time to Monday. Off by default: it cuts donch's PF 1.53 → 1.40 and orb's 1.34 → 1.19 in sample (map `mains` 12).
- **Clock**: hourly |TimeTradeServer − TimeGMT − rule| > 120 s → no entries (`CLOCK`).
- From the hands 1.11, kept: Resolve, RiskMoney, ToTick (as GridStop), CloseAll, the open checks, RobotDeals, Capital's settle and reference rules, Notify's limits, Watch's rhythm. Dropped: the bridge, heartbeat, TTL globals, InpResetLocks, the 6 % lock, the −50 % equity kill, and two limits the lab does not have: the 3-spread minimum stop and InpMaxRiskPct (its 1 % would cut F2S).

## 7. Harness and acceptance (check/)

- **Data**: `export_frames.py` turns `r2.load(sym, end="2022-01-01")` into binary broker bars (server time, bid rounded to 2 digits until the Mac says otherwise, spread = round((ao − bo)/point)) and writes the lab frame rebuilt from them (ask rounded half away from zero); references use it (spike: rounding changed no trade).
- **Engine**: the dist file through `to_cpp.py`; `mock_replay.h` serves N symbols (first ticks at T, a timer call at T + 2.5 s; fast mode checks stops at bar end with the lab rule; tick mode plays O→L→H→C or O→H→L→C); a hedging broker with deals, deposits, margin = lots × units × price × 0.89 / leverage, tick value = tick size × units × 0.89; restarts; `mock_faults.h`.
- **References**: `ref_lab.py` runs each `recalc.sleeves()` entry — `make_orders` (every signal) and `r2.run(sym, mk, params, "fp", True, m1)` (recalc.py:98) — and `growth.run_one`; `compare.py` matches the journal.
- **Tolerances**: times, sides, reasons, counts, lots, skips and prices taken from bars: equal. Rolling, Wilder and score values and the stops built on them: 1e-12 relative. Decisions within 1e-9 of a threshold: listed razors, compared again once both chains are flat. `HOLE_EXIT` (lab exits before unforeseen holes over 30 min) and GFP hole days: classified, never silent. Trades open at the frame end: excluded.
- **T1 clock**: hourly 2012-2035 and DST switches ± 3 h vs zoneinfo and `pont.server_to_utc`; NYSE vs `us_holidays`; `AddTradingDays` on all in-sample 4h closes; weeks vs `stake.prepare`. **T2 data**: store = rebuilt frame bit for bit; the mask drops nothing; aggregates = lab functions; barrier and revisions in the mock. **T3 paper**: ≥ 10,000 random orders per market (all etypes, OCO, wrong-side stops, trail, be, targets, gaps) vs `gl.simulate`, exact, plus the map `simulateur` §6 cases. **T4, T5**: every decision and every trade per rule over the whole in-sample period.
- **T6**: 100 restarts per sleeve from the §2.2 depth only, and 10 outages of 1-6 h: later paper trades unchanged, positions per §4.6. **T7**: the EA over 2018-02..2021-12, F1S and F2S, 1,000 EUR at the start and each month; `growth.engine` on the EA's trades and payments gives the same takes, skip reasons, lots, m and stop week, weekly balances within 0.01 EUR.
- **T8** (tick mode): clean ticks → real = paper (gold one bar late); then one scripted world each for refused stop or modify, requote and timeout (no duplicate), rewritten comments, magic-0 deals, late bar, short history, restart mid-trade, clock 1 h off, mid-week deposit and withdrawal (w unchanged), plan stop, guard, lock, Friday close, `InpTrade` false, real account off the VPS, second instance. **T9**: test_mains.py sections 2-4, 7, 9 and 11 ported to CR_Broker and CR_Ledger; the rest retires. **T10**: `gen_golden.py` vectors (60 clock instants, 40 NYSE dates, 20 AddTradingDays, 30 F1 scores, a Wilder and an SMA series) checked at `OnInit`; a mismatch blocks trading. **Speed**: full in-sample ten-sleeve run under 3 min; startup replay under 5 s.

## 8. Build steps

| Step | Files | Done when | Parallel |
|---|---|---|---|
| S0 contract | `ClaudeRobot.mq5`, `CR_Types`, `CR_Registry` (all rows and cases), `CR_Journal`, `CR_Main` skeleton, stubs of all other `src/` files, `amalgam.py`, the `check/` harness, `mock_faults.h` stub | dist compiles without warnings; an empty EA replays 2021 on four symbols with a parsable journal; `ref_lab.py` reproduces `results/r2/recalc/trades` (entries before 2022) | first |
| A clock | `CR_Clock.mqh`, `test_clock.cpp` | T1 | B–J |
| B data | `CR_Math.mqh`, `CR_Bars.mqh`, `test_bars.cpp` | T2; primitives within 1e-12 of pandas | A, C–J |
| C paper | `CR_Paper.mqh`, `test_paper.cpp` | T3 | A, B, D–J |
| D us100 | `CR_Rule_IdxUS.mqh`, tests | T4, T5 for N30, OC4 | A–C, E–J |
| E crypto | `CR_Rule_Brk72.mqh`, `CR_Rule_F1.mqh`, `gen_f1_model.py` | T4, T5 for BKB, BKE, F1B, F1E; wrong sha256 refused | A–D, F–J |
| F lead-lag | `CR_Rule_NqBtc.mqh`, tests | T4, T5 for NQB | A–E, G–J |
| G gold clock | `CR_Rule_GoldFri.mqh`, `CR_Rule_Orb.mqh`, tests | T4, T5 for GFP, ORX | A–F, H–J |
| H gold trend | `CR_Rule_Donch.mqh`, tests | T4, T5 for D4H | A–G, I, J |
| I account | `CR_Ledger.mqh`, `CR_Sizing.mqh`, `test_account.cpp` | T7; unit tests (risk table, m, lots, caps, margin, stamps, stop, `InpPaidIn`, `InpRestartAfter`, history gap) | A–H, J |
| J execution | `CR_Broker.mqh`, `CR_Follower.mqh`, `CR_Guards.mqh`, `mock_faults.h` | T8, T9 | A–I |
| K integration | final `CR_Main.mqh`, `gen_golden.py` | T6, T10, full run under sanitizers, speed | after A–J |

D-H code against the S0 stubs; their T5 passes once A-C have landed.

## 9. Accepted deviations from the lab

1. D4H, ORX and GFP fill for real one bar after the paper fill; paper and sizing keep the lab fill.
2. Lab exits before unforeseen holes over 30 min happen after the hole; known closures follow the lab.
3. GFP's early-close filter is a calendar plus the broker session.
4. Real stops trigger on ticks, paper stops on bars with one spread each; the paper decides.
5. Ask = bid + the bar spread, on FP's feed: only "EA = lab code on the broker's bars" is provable; razor-thin rules will differ from the Dukascopy-based lab (nq_btc keeps 58 % of its trades under 1 bp of noise, map `leadlag` 21).
6. Live EUR tick values and `OrderCalcMargin` replace 0.89 and fp_costs.json; for absolute stops the expected fill comes from the quote.
7. Gold intents are sized one minute after their stamp (it matters only when caps or margin bind).
8. Incremental statistics within 1e-12 of the lab; razor decisions may differ.
9. After a restart, an entry is joined only within 5 min of its stamp.
10. The disaster guard is outside the plan.
11. NYSE special closures after 2025-01-09 only through `InpExtraClosures`.

## 10. Only the user's Mac can settle (default meanwhile)

1. The MetaEditor compile and the self-test on the real compiler. Default: none (trading blocked).
2. A Strategy Tester run of the debug file on FP 2021 (real ticks, else 1-minute OHLC), `InpTrade` false; the harness replay of the dumped bars must reproduce the journal line for line. Default: none (trading blocked).
3. What `MqlRates.spread` holds (a moderator: the bar's minimum, forum 266519), vs ReleveFP files. Default: ask = bid + spread.
4. Server = NY + 7 h across a DST switch. Default: the rule; entries blocked on a mismatch.
5. FP sessions, crypto weekends, Friday close, holidays. Default: the lab mask, shortened by broker sessions.
6. Symbol specs (digits, sizes, US100 minimum lot, EUR tick values, stops and freeze levels, filling, margin, hedging). Default: read live; the harness uses fp_costs.json and 0.89.
7. Deposits as `DEAL_TYPE_BALANCE`, full history. Default: the history, a gap as opening payment, `InpPaidIn` override.
8. Stop deals' magic and reason; comments kept. Default: position id, magic and time.
9. VPS history depth, replay time, Max bars, `TERMINAL_VPS`. Default: NOT_READY until deep enough.
10. Tick timing, open slippage, `LATEBAR` rate. Default: 2 s grace, rebuild per revision.
11. Weekend crypto quotes (ids 11-12). Default: disabled.
12. Two shadow weeks, `InpTrade` false, VPS and Mac journals vs a harness replay; then `InpTrade` true.
