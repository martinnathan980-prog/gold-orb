# ClaudeRobot — build specification v1

Contract for building the single MT5 Expert Advisor that runs the ten validated rules with their sizing and protections at FP Markets (Raw, `.r` symbols, hedging, 1:500) on the MetaQuotes VPS. All code is new, in `lab/robot/` (`lab/robot/spike/` is a read-only reference). Lab data: in sample only (bars before 2022-01-01, sliced when read), `NUMBA_CACHE_DIR` under /tmp, never `lab/holdout_raw` or 2026.

## 0. Principles

1. Each sleeve has a **paper chain**: `goldlab/sim.py` run bar by bar on the broker's closed M1 bars. It alone decides entries, the one-position rule and exits. Account skips never change it.
2. The account **follows** the paper: market orders only, broker stop = paper stop, and the EA closes when the paper exits.
3. **No persistent state.** Every start and every bar revision rebuilds rules, paper chains and the ledger from the broker's history.
4. The shipped `.mq5` is translated to C++ and replayed on in-sample bars against the lab code. This is the spike's method: brk72 BTC matched 632 of 645 trades bit for bit, and the other 13 were lab exits before closures nobody could foresee.

VPS facts checked (mql5.com/en/vps/rules; MT5 help, virtual hosting migration; MQL5 article 994; MQL5 docs, terminal properties):
- DLL calls are forbidden.
- EAs migrate with their chart; scripts do not.
- At most 500,000 bars are available.
- The terminal restarts for updates and maintenance (up to 15 min a weekday).
- Auto trading is always on there, and is switched off locally after migration.
- Terminal global variables are not migrated.
- Sync is one-way. Files written on the VPS are treated as lost: there is no official statement, only a community answer (forum 363057).
- `TERMINAL_VPS` identifies the VPS.
- One EA trading four symbols is standard MQL5; the hands already do it (ClaudeMains.mq5:56).

## 1. Layout

### 1.1 Files

S0 creates every `src/` file with its final signatures and stub bodies. Ownership then passes to the step shown (§8), and nobody edits a file they do not own. Adding a rule takes one rule file, one registry row with its three `case` lines, and one `ref_lab.py` entry.

| File | Owns | Step |
|---|---|---|
| `src/ClaudeRobot.mq5` | `#property`, inputs, include list | S0 |
| `src/CR_Types.mqh` | constants, structs (§2.4), byte-order string compare | S0 |
| `src/CR_Registry.mqh` | symbol and sleeve tables (§2.3), dispatch | S0 |
| `src/CR_Journal.mqh` | §2.6; French push texts with the hands' limits (`Notify`, ClaudeMains.mq5:163-184) | S0 |
| `src/CR_Main.mqh` | event handlers, startup state machine, minute driver | S0 → K |
| `src/CR_Clock.mqh` | §2.1 | A |
| `src/CR_Math.mqh`, `CR_Bars.mqh` | rings; rolling sum, max, min and median; Wilder step; §2.2 | B |
| `src/CR_Paper.mqh` | §2.5 | C |
| `src/CR_Rule_IdxUS.mqh` | session grid, daily ATR, N30, OC4 | D |
| `src/CR_Rule_Brk72.mqh`, `CR_Rule_F1.mqh`, `CR_F1Model.mqh` (generated) | BKB/BKE, F1B/F1E | E |
| `src/CR_Rule_NqBtc.mqh` | NQB | F |
| `src/CR_Rule_GoldFri.mqh`, `CR_Rule_Orb.mqh` | GFP, ORX | G |
| `src/CR_Rule_Donch.mqh` | D4H | H |
| `src/CR_Ledger.mqh`, `CR_Sizing.mqh` | §5 | I |
| `src/CR_Broker.mqh`, `CR_Follower.mqh`, `CR_Guards.mqh` | the only trade sender; §4; §6, instance lock, self-test | J |
| `src/CR_Golden.mqh` (generated) | self-test vectors | K |
| `tools/amalgam.py`, `gen_f1_model.py`, `gen_golden.py` | §1.2; F1 constants; golden vectors | S0, E, K |
| `check/to_cpp.py`, `mql5_shim.h`, `mock_replay.h` | the spike's translator, shim and mock, extended (§7) | S0 |
| `check/mock_faults.h` | broker failures, included through an S0 stub | J |
| `check/export_frames.py`, `ref_lab.py`, `compare.py`, `run_tests.py` | §7 | S0 |
| `check/test_<module>.cpp`, `test_<code>.py` | each owner's tests | owner |

### 1.2 Single file and install

`tools/amalgam.py` builds the one installed file:
- It inlines the local includes of `src/ClaudeRobot.mq5` recursively, once each and in order, and keeps `#include <Trade\Trade.mqh>`.
- It refuses any non-ASCII character.
- It writes `dist/ClaudeRobot.mq5` with `#define CR_BUILD "<first 12 hex of its sha256>"`.
- It also writes `dist/ClaudeRobot_debug.mq5`, which adds `#define CR_DEBUG` (aggregate lines and a bar dump).

Integration tests translate the dist file, so the tested text is the shipped text.

Install, once, on the Mac:
1. Copy the dist file to MQL5/Experts and compile it in MetaEditor: 0 errors, 0 warnings.
2. Set Options › Charts › Max bars in chart to 500000, then restart MT5.
3. Show the four `.r` symbols in Market Watch, and remove ClaudeMains from every chart.
4. Attach the EA to one XAUUSD.r M1 chart. Check for `SELFTEST` ok and four `READY` lines.
5. Run Virtual Hosting › Migrate "Experts and indicators", then check the hosting journal.

To change an input, change it locally and migrate again.

### 1.3 Inputs

| Input | Default | Meaning |
|---|---|---|
| `InpTrade` | true | false = paper and journal only |
| `InpRiskTable` | `0:1;12000:0.5` | F1S (the lead's advice); F2S = `0:2;6000:1;12000:0.5`. Pairs `from:pct`, first `from` = 0, increasing, 0 < pct ≤ 5. Rate = pct of the last pair with from ≤ max(balance, paid in) (growth.py:93-98, 118-120) |
| `InpPaidIn` | 0 | 0 = from the deal history; > 0 = this constant |
| `InpStopFallPct`, `InpStopArmPaid` | 25, 12000 | §6 |
| `InpSleeves` | ALL | codes allowed to trade; the others run on paper |
| `InpDailyLockStakes`, `InpFridayCloseHHMM` | 0, 0 | off (§6) |
| `InpExtraClosures` | "" | `YYYY-MM-DD,…`: NYSE full closures and gold early-close Fridays |
| `InpRestartAfter` | 0 | datetime: restarts the plan after a permanent stop (§5) |
| `InpPush` | true | push notifications |

### 1.4 MQL5 subset

These limits let `to_cpp.py` translate the code (spike report §7):
- No pointers (`new`, `delete`, `*`, `->`, `this.`), virtual functions, templates, function macros, `#import` or `Sleep`.
- Structs are passed by reference only.
- One global `CTrade`.
- `(datetime)` casts in date-range `CopyRates`.
- No `string + number`.
- Time differences as `(long)a-(long)b`.
- Inputs only of type bool, int, long, double, string or datetime.
- Literals with 17 significant digits.

Tests build with `g++ -std=c++17 -O2 -ffp-contract=off`, and once with `-fsanitize=address,undefined`.

## 2. Conventions

### 2.1 Time (CR_Clock)

- **Clock.** Internal time is UTC seconds. Server time = NY + 7 h: UTC = server − 3 h if the US is on summer time at (server − 3 h), else server − 2 h (pont.py:37-43).
  - US summer time runs from the 2nd Sunday of March, 07:00 UTC, to the 1st Sunday of November, 06:00 UTC.
  - UK summer time runs from the last Sunday of March to the last Sunday of October, 01:00 UTC.
- **Days and weeks.** The server day is the date in server time. The server week starts Monday 00:00 (stake.py:89-91, 131). The trading day (17:00 NY roll) equals the server date (data.py:45-49).
- **`AddTradingDays(t, n)`** returns n business days later at the same server time. From a Saturday or Sunday, Monday counts as day 1 (pandas BDay, trend/strategy.py:107-111).
- **Calendars.** The NYSE calendar is a port of `us_holidays` (idxus_lib.py:52-83) plus `InpExtraClosures`. Gold early-close Fridays are the day after Thanksgiving plus `InpExtraClosures`.
- **Closures** follow the lab frames' shape, on the NY clock (map `simulateur`, facts 5-7):
  - XAU: daily 17:00-18:00, and Fri 17:00 → Sun 18:00.
  - US100: daily 16:15-18:00, and Fri 16:15 → Sun 18:00.
  - BTC/ETH: Fri 16:55 → Sun 17:00.
  - A broker session (`SymbolInfoSessionTrade`) that ends earlier moves the closure start earlier.
- **`ExitMinute(x, gap)`** applies the lab's 30-minute rule (data.py:95-104). If x lies inside a known closure [c0, c1) and x < c1 − 30 min, it returns c0 − 1 min; otherwise it returns x.

### 2.2 Bars, barrier, depth (CR_Bars)

- **Reading.** Symbols are resolved by `Resolve` (ClaudeMains.mq5:206-226). Only M1 is read, by time range (`CopyRates(sym, PERIOD_M1, from, to)`), never by position (map `mains`, pitfall 0). The chart mode must be bid.
- **Bar.** A bar holds its UTC start, bid O/H/L/C and spread in points. Each ask price = `NormalizeDouble(bid + spread × point, digits)`, on all four prices; mid = (bid + ask)/2. This is the lab frames' structure (build_fp_frames.py:41-45).
- **Lab-hours mask**, applied on ingestion and counted. It drops:
  - a bar whose bid O=H=L=C equals the previous close (prep_round2.py:49);
  - server Saturday and Sunday (:53);
  - crypto bars from server Friday 23:55 (build_fp_frames.py:31-33);
  - US100 bars 16:15-17:59 NY, and XAU bars 17:00-17:59 NY.
- **Barrier M** passes when every symbol has a tick ≥ M, or `TimeTradeServer()` ≥ M + 2 s, or is inside a known closure. All bars before M are then final. If a minute had a tick but `CopyRates` does not yet return its bar, retry for up to 30 s, then log `GAP`.
- **Revisions.** Every minute, re-read the last 3 closed bars. A difference raises `LATEBAR` and a rebuild (§4.6), at most once every 5 min.
- **Depth.** XAU 120 days, the others 60.
  - Decision: this is twice every measured warm-up and resync. us100 36 d, F1 29, nq_btc 20, GFP 40; donch resyncs its chain in 20 days, and its ATR is within 4e-15 at 120 days (maps `us100` 8, `ml` 8, `leadlag` 11, `or-seances` 7, `or-tendance` 18-19).
  - 120 days of gold is about 120,000 bars, under the 500,000 cap.
  - History is ready when two reads 2 s apart agree and start within 3 days of the target. Otherwise that symbol's sleeves are NOT_READY.

### 2.3 Identifiers

| id | code | lab sleeve (sort key) | symbol |
|---|---|---|---|
| 1 | N30 | noise30_us100 | US100 |
| 2 | OC4 | ocm4_us100 | US100 |
| 3 | BKB | brk72_24h_wd_btcusd | BTC |
| 4 | BKE | brk72_24h_wd_ethusd | ETH |
| 5 | F1B | F1_brk_ridge_filter_btcusd | BTC |
| 6 | F1E | F1_brk_ridge_filter_ethusd | ETH |
| 7 | NQB | nq_btc_follow_btcusd | BTC, reads US100 |
| 8 | GFP | GOLD_FRI_PM_xauusd | XAU |
| 9 | D4H | donch4h_stop_xauusd | XAU |
| 10 | ORX | orb_asia_2d_buf10_xauusd | XAU |

- Magic = 20261200 + id (the hands use 20261110).
- Comment `CR <code> <yymmddhhmm>`, the decision time in UTC. It is informative only.
- Ids 11-12 are orb_asia on BTC and ETH: same module, held over weekends, registered and disabled.
- Ids 13-19 are reserved for Addendum J. Ids are never reused.
- A multi-leg rule gives its legs one group number. They are opened all or none, and closed together.

### 2.4 Rule interface

Each rule is one class, with one global object per sleeve, dispatched by `switch(kind)`. It has four methods:
- `Init(sleeve)` holds the frozen parameters as constants, each with its file:line.
- `OnBar(sym, const CrBar &b, CrOut &out)` receives each kept closed bar of a subscribed symbol, in time order (ties by symbol id), **before** the paper engine sees it.
- `OnMinute(M, CrOut &out)` runs after barrier M and uses only bars before M.
- `LatestExit(dec)` returns the time exit implied by a decision (§4.6).

`CrOrder` fields:
- sleeve; oid (decision × 100 + id); side; etype (0 market, 1 stop, 2 limit, 3 OCO pair); level and level2;
- the activation: a window [t_from, t_to], meaning the first bar starting inside it; or `after_exit_of`, meaning the first bar after that oid's exit bar (void if that exit is void);
- expiry_excl: pending orders fill only on bars starting before it;
- stop (absolute) or stop_dist; trail, be, target (0 = none);
- x_sched, gap, dec, group.

`CrExit` holds an oid and a window [t_from, t_to]: a time exit at the first bar inside the window, void if there is none.

Rules keep the lab's own validity conditions. READY only gates real orders.

### 2.5 Paper engine (CR_Paper), a port of sim.py `_run` (sim.py:68-211)

For each closed bar b, after the rule's `OnBar`:
1. **Open trade**, checks in this order:
   - Time exit at b's open, if b starts at or after the exit minute and is not the fill bar: long at bo(1−sm), short at ao(1+sm), stamped b's start.
   - Else stop. Long: when bl ≤ cur, at (fill bar ? cur : min(cur, bo)) × (1−ss). Short: when ah ≥ cur, at max(cur, ao) × (1+ss). Reason `trail` once the stop has moved, else `stop`; stamped b's start + 60 s.
   - Else target (:146-163).
   - Then update best, trail and break-even for the next bar (:164-173, 194-203).
2. **Orders.** An order activating on b is skipped if the sleeve's trade is open or exited on b (:80-82).
   - Market fills at ao(1+sm) / bo(1−sm).
   - Stop fills at max(lv, ao)(1+ss) when ah ≥ lv, or min(lv, bo)(1−ss) when bl ≤ lv.
   - Limit fills at min(lv, ao) when al ≤ lv, or max(lv, bo) when bh ≥ lv (:87-111).
   - OCO: if both levels are touched, take the side against the bar's move, bc ≥ bo → short (trend/strategy.py:303-317).
   - The stop is absolute, or fill ∓ dist (:117). A stop on the wrong side exits on the fill bar at bo(1−ss) / ao(1+ss), reason `gap` (:122-127). Otherwise the fill bar is managed as in 1.
   - Unfilled pending orders vanish at expiry.
3. **Constants.** ss, sm = slip_stop_bps, slip_mkt_bps × 1e-4 (fp_costs.json: XAU 1.0/0.3, US100 0.5/0.2, BTC 1.5/0.5, ETH 2.0/0.7). Ties keep emission order. Two pending orders of one sleeve at once log `ERROR`: sim.py settles that case with future bars, and it cannot happen for the ten rules, whose windows never overlap.

Events: `PFILL`, `PEXIT`, `PSTOP` (effective from the next bar). No swap, no end-of-data exit.

### 2.6 Journal (CR_Journal)

- **Format.** `CR|<utc>|<EVENT>|<code or ->|k=v|…`, written to `Print` and to `MQL5/Files/ClaudeRobot/<yyyymmdd>.log` (30 days kept). utc is the event's lab time. Doubles use `DoubleToString(x,-16)`, which round-trips exactly.
- **Events.** INIT, SELFTEST, READY, NOTREADY, DEC, PFILL, PEXIT, PSTOP, SIZE, SEND, FILL, SLMOD, CLOSE, REFUSED, ADOPT, ORPHAN, DUP, MISSED, LATEBAR, GAP, REBUILD, CLOCK, STOP, GUARD, LOCK, ERROR.
- **Push notifications** for STOP, GUARD, LOCK, CLOCK, ORPHAN, MISSED, REFUSED, ERROR and NOTREADY lasting over 10 min, plus a daily summary at 23:00 server.

## 3. The ten rules

Notation: [a, b] = the first bar starting in [a, b]; "gap" = `ExitMinute` with the 30-min rule; times are NY.

**N30 noise30 (US100).** `{lookback 14, first_min 600, step 30, last_min 930, exit_min 955, vm 1.0}`, idx_us/strategy.py:297-299; logic :216-257; grid idxus_lib.py:113-158.
- **Session grid**, shared with OC4. One row per NY weekday date with at least one US100 bar that is not a full NYSE holiday. A row is tradable if it is not an early close and its date is on or after 2014-01-01 (strategy.py:66, 114-116).
  - O = mid open of the first bar in [09:30, 09:32).
  - P(T) = mid close of the last bar starting before T; NaN if that bar started more than 11 min before T (idxus_lib.py:149-155).
- **State**: pos ∈ {−1, 0, 1} and the open oid. It ignores paper stop-outs.
- **Checks** at T = 10:00, 10:30 … 15:30, on tradable rows with finite O:
  - s = mean of |P(T)/O − 1| over the previous 14 rows (NaN skipped, at least 9 values).
  - pc = previous row's P(16:00); hi = fmax(O, pc), lo = fmin(O, pc), or O alone if pc is NaN.
  - ub = hi(1+s), lb = lo(1−s).
  - The check is void unless P(T) and s are finite and a bar in [T, T+5] comes before the exit bar.
- **Exit**: if pos ≠ 0 and (long: P < ub; short: P > lb), emit `CrExit` [T, T+5] and set pos = 0. An entry at the same check is `after_exit_of` that exit.
- **Entry**: if pos = 0, go long when P > ub, short when P < lb. Market [T, T+5]; stop = hi (long) or lo (short); x = 15:55, gap.
- The state commits only when the check's bar is seen in `OnBar`.

**OC4 ocm4 (US100).** `{n 4, stop atr, k 0.3, exit_min 955, size_min 1.0, size_win 20, atr_n 14, sides both}`, strategy.py:303-305; logic :127-168; ATR idxus_lib.py:161-198.
- **Signal** at 09:34, on tradable rows:
  - O and C = P(09:34) finite;
  - at least 3 bars in [09:30, 09:34);
  - move = C/O − 1 ≠ 0;
  - |move| ≥ median of the previous 20 rows' |move| (NaN skipped, at least 10 values).
- **ATR**: 17:00-NY days with at least 600 bars. Day high/low = max/min of per-bar mid highs/lows; close = last mid close; TR = fmax(h − l, |h − pc|, |l − pc|). Mean of 14, taken from the last day ending at or before 09:34.
- **Order**: market [09:34, 09:39]; stop_dist = 0.3 ATR; x = 15:55, gap.

**BKB/BKE brk72_24h_wd (BTC, ETH).** `{n 72, stop_atr 3, hold_h 24, dow weekday}` + `{atr_n 24, max_delay_min 5}`, crypto/strategy.py:242-243, 43-56; logic :82-178; wrapper recalc.py:44-54.
- **Hour bars** on UTC hours: first mid open, max per-bar mid high, min per-bar mid low, last mid close. Empty hours are absent.
- **Signal** at each UTC hour D whose last hour has bars, given at least 73 hour bars:
  - side = +1 if c > max of the 72 previous closes, −1 if c < their min;
  - ATR24 = mean of 24 TRs (the first TR = h − l);
  - require UTC weekday(D) < 5 and ATR > 0.
- **Order**: market [D, D+5]; stop_dist = 3 ATR; x = D + 24 h, gap (Fri 23:54 server when D + 24 h falls in the weekend). Dropped if its exit bar would not follow its entry bar.

**F1B/F1E F1_brk_ridge_filter (BTC, ETH).** `{stop_k 2.0, hold_h 13, model B1_ridge_full.json, q 0.5}` + `{n 14, h0 2, h1 16, last_dec_h 15, vol_n 70, exit_hm 1555, max_wait_min 5}`, ml/strategy.py:295-297, 55-69; logic :82-189; score :195-212.
- **Session bars**: UTC-hour **bid** bars with NY start hour 2 to 15, on NY weekdays. Every look-back counts session bars only.
- **Features**, at the close of a session bar starting at or before 14:00 (t_dec = start + 1 h): the 15 features of `candidates()`, exactly.
  - A = mean range of the last 70 bars including this one; A_long the same over 280.
  - hh/ll over the 14 previous bars; pos on the 280-bar extremes including this bar.
  - seq/opp count the breakout flags of the 14 previous bars, 15:00 bars included.
  - pdd/dret use the previous NY date that has session bars; hour = start hour + 1.
  - Require a breakout, every feature finite, and A > 0.
- **Score** = intercept + Σ coef × clip((x − mean)/std, ±4) + dummies for hour 8-10, 11-12, 13-15, dow 0 and dow 4. Take the trade if score ≥ 0.027922380451488427.
  - `gen_f1_model.py` writes the constants of `B1_ridge_full.json["frozen"]` as `%.17g`. It refuses the file unless its sha256 is d191cbbcc2fc4d2cae31182f14f412069a194b69c2a9d9ae6bca0d0f5dee644e.
- **Order**: market [t_dec, t_dec+5]; stop_dist = 2A; x = 15:55 the same day, gap.

**NQB nq_btc_follow (BTC, leader US100).** `{leader us100, pred lead, sess uscash, dirn 1, k 1, z 6, hold 60, stop 2.0}` + `{sig_days 20}`, leadlag/strategy.py:328-334, 188-189; logic :188-238.
- **Returns**, per UTC minute g and market, with c = mid close: r(g) = ln(c(g)/c(g′)) when the market has a bar at g, where g′ is its last bar within g−1 … g−4 (:113-125, 197, 205-214).
- **Volatility**: σ(g) = sqrt(Σr²/n) over the valid r in [g − 28800, g − 1]; NaN if n < 4800 (:128-134). Running sums, re-summed in full every 1440 minutes.
- **Signal** at barrier g+1, when all of these hold: g is a NY weekday minute in [09:30, 16:00); both markets have a bar at g; r_L, σ_L and σ_B are finite; |r_L| ≥ 6σ_L. Then side = sign(r_L).
- **Order**: BTC market [g+1, g+2]; stop_dist = 2σ_B × √60 × BTC mid close at g; x = entry + 60 min, gap.

**GFP GOLD_FRI_PM (XAU).** `{NY, entry 13:30, exit 16:45, weekdays (4,), side 1, stop_atr 3, atr_n 14, atr_tf 1h, limit, limit_min 60, min_prev 0, skip_early_close}` + `tol_min 5`, overnight/strategy.py:243-244, 100-103; logic :100-211; ATR :71-97.
- **Days**: Fridays at 13:30, except early-close Fridays (§2.1) and days when the broker's XAU session ends before 16:55. This replaces the lab's after-the-fact filter (:129-137).
- **Level** = bid close of the last bar before 13:30.
- **ATR**: UTC-hour bars with h = (max bh + max ah)/2, l = (min bl + min al)/2, c = last mid close. Wilder 1/14, seeded with the 2nd hour's TR (the first 14 hours NaN). Use the 12:00 hour's value. stop_dist = 3 ATR.
- **Order**: limit buy activating in [13:30, 13:35], filling on bars starting before 14:30 (when al ≤ level, at min(level, ao)); x = first bar ≥ 16:45, no gap rule.

**D4H donch4h_stop (XAU).** `{donchian, 4h, n 60, entry stop, stop_atr 2, trail_atr 2, max_days 5, atr_n 14, sides both, grid utc}`, trend/strategy.py:427-429; logic :257-318; bars data.py:61-77; ATR :88-92.
- **4h bars** on UTC buckets 00/04…20. Bid and ask are aggregated separately; mid h = (max bh + max ah)/2, and likewise for the others. t_close = last bar + 1 min. Empty buckets are absent.
- **ATR**: Wilder 1/14 on mid bars, seeded with the 2nd bar's TR.
- **Bracket**, at the end of each non-empty bucket once 60 bars exist:
  - up = max h and dn = min l over the last 60 bars, including this one.
  - OCO order activating on the first bar ≥ t_close and filling only inside that bar's 4h bucket, which is the lab's window up to the next t_close.
  - stop_dist = trail = 2 ATR; x = AddTradingDays(t_close, 5) − 5 min, gap.
  - The whole bracket is skipped if the paper is busy at activation.

**ORX orb_asia_2d_buf10 (XAU).** `{LDN, 00:00-07:00, entry_end 12:00, stop, buf_frac 0.1, opp, exit 16:00 NY, hold_days 2, min_bars_frac 0.5, sides both}`, orb/strategy.py:276-287; logic :95-271.
- **Range**, on London weekdays at 07:00 London: H = max ask high and L = min bid low of the bars in [00:00, 07:00). Require at least 210 bars and W = H − L > 0. Levels: buy = H + 0.1W, sell = L − 0.1W.
- **Touch**: the first bar in [07:00, 12:00) London with ah ≥ buy or bl ≤ sell. If both levels are touched, take the level nearer the bar's mid open (a tie goes long). The touch uses up the day whatever the paper state.
- **Order**, emitted at the touch bar in `OnBar`, before the paper sees it: a stop order at the touched level, window = expiry = that bar, stop = the opposite level, x = first bar ≥ 16:00 NY on the London date + 2 business days, no gap rule (held over weekends).

## 4. Follower (CR_Follower, CR_Broker)

At barrier M, once the bars before M have gone through rules and paper and `OnMinute(M)` has run:

1. **Entries.**
   - A market order becomes an intent when it activates: the symbol's first tick ≥ t_from falls in a minute ≤ t_to, and the sleeve's paper trade ended on an earlier bar. The intent is stamped with that minute.
   - A stop, limit or OCO order becomes an intent at its `PFILL` on bar i. It is stamped i and sent at barrier i+1.
   - **Decision:** enter at market one bar late, rather than through broker pending orders or tick emulation, so real and paper never disagree on which trades exist. The in-sample cost: donch −0.023 R a trade; orb +0.049 USD against the level (the lab assumes +1 bp); GFP +0.002 USD against the lab fill (maps `or-tendance` 22, `or-seances` 24 and 1.7).
   - The intents of one barrier are sized (§5) by stamp, then by lab sleeve name in byte order (stake.py:108).
   - Sending is allowed until stamp + 5 min, the lab's own entry tolerance; after that, `MISSED`.
2. **Sending** applies the hands' DoOpen checks (ClaudeMains.mq5:760-860):
   - tick at most 10 s old; hedging account; Algo Trading on;
   - volume floored to the step and capped at the maximum; notional ≤ 20 × balance;
   - stop on the right side, beyond `STOPS_LEVEL`; deviation of 2 spreads.
   - After the fill, verify the stop: if absent, set it; if refused, close. The risk at the fill must be ≤ 1.25 × the budget, else close (`REFUSED`).
   - Before any send, look for a position or deal with this magic since the stamp: one intent, one trade. An unknown result is checked again after 2 s.
   - Dropped from the hands: the 3-spread minimum stop and the 1 % cap. The lab has neither, and the cap would cut F2S.
3. **Stops.**
   - Broker stop = paper stop on the tick grid, rounded away from the price (spike `GridStop`, SpikeRobot.mq5:48-66). A bid or ask on the grid then touches it exactly when it touches the paper stop.
   - A distance stop is first set from the quote, then moved to the paper stop at `PFILL`. `PSTOP` moves it again (donch).
   - A modification refused because the price has already crossed the stop → close.
4. **Exits.** Close at the barrier of the paper's exit minute, and on `PEXIT`. A real stop hit first leaves the sleeve busy until the paper exits. Retry every 10 s, or every 60 s while the market is closed (Watch, :698-739).
5. **Ownership.** Robot positions carry magic 20261201-20261299; nothing else is touched. Deals attach through `DEAL_POSITION_ID`, since stop deals may carry magic 0 (RobotDeals, :340-367).
6. **Startup and rebuild.** `OnInit` checks inputs, resolves symbols, runs the self-test, starts a 100 ms timer and returns. `OnTimer` then:
   1. waits for the connection and the history;
   2. replays every minute of the history through rules and paper, with orders off;
   3. rebuilds the ledger;
   4. reconciles:
      - a robot position on the same side, opened within [stamp, stamp + 5 min] of its sleeve's open paper trade → `ADOPT`, stop reset; any other robot position → close (`ORPHAN`);
      - two positions for one trade → keep the earliest (`DUP`);
      - a paper trade without a position: if one was already opened and closed (deals), nothing; if it is still inside its send window, an intent; else `MISSED` or a sizing skip;
   5. goes live.

   A NOT_READY sleeve enters nothing; its position keeps its stop and closes at `LatestExit(dec)`, read from the comment. `LATEBAR` and a reconnection after more than 60 s rerun steps 2-4.
7. **One trading copy.** Orders go out only if `InpTrade`, and on a real account only if `TERMINAL_VPS`; the Mac copy observes, and its journal is a twin. `GlobalVariableTemp` + `SetOnCondition` refuse a second instance.

## 5. Account (CR_Ledger, CR_Sizing)

- **Ledger**, from `HistorySelect(0, now)`, at startup and on each `OnTradeTransaction`.
  - Payments: `DEAL_TYPE_BALANCE`, amount in `DEAL_PROFIT` (Capital(), :565-619).
  - Robot closes: one event per position; money = Σ profit + swap + commission + fee over its deals. Stamped as the lab does (sim.py:283-284): an exit by SL, TP or SO in minute X → X + 60 s; an EA close in minute X → X.
  - Other money is stamped at its deal time.
  - Σ deals must equal `ACCOUNT_BALANCE` (60 s settle). A constant gap is missing early history, booked as one payment at the first deal.
- **State at stamp S**, in the growth engine's order (payments ≤ S, then closes < S; growth.py:189-215):
  - balance B(S);
  - paid in P(S) = Σ payments (deposits +, withdrawals −), or `InpPaidIn`;
  - reference: the first payment, then at each payment A, ref = max(ref + A, balance right after A) (:212).
- **Week unit.** At the server week's first ledger event (a robot close or a sizing request), take B_w and P_w; unit = rate(max(B_w, P_w))% × B_w (:230, 268, 274). w = Σ money of the robot closes stamped in the week before S, divided by the unit. This is the lab's (eq − week base)/unit, but deposits, withdrawals and manual trades never count.
- **Multiplier** m = 1 if w ≤ 0, else min(1, max(0.25, w/4)) (stake.py:184-185; cushion_only, :472-473).
- **Lots** = floor(B(S) × rate(max(B(S), P(S))) × m / 100 / per_lot / step + 1e-9) × step (growth.py:295-296).
  - per_lot = risk × tick_value_loss / tick_size.
  - risk = |expected fill − stop|, where the expected fill is the paper fill when known, else the quote with the lab slippage; or risk = stop_dist for distance stops.
- **Checks**, in the lab's order (growth.py:297-309, account.py:104-113):
  1. guards: `STOPPED`, `LOCK`, `FRIDAY`, `CLOCK`, `NOTREADY`, `OBSERVE`, `PREV_OPEN`;
  2. lots < minimum lot → `MIN_LOT`, never rounded up;
  3. 6 robot positions open, or 2 on this symbol, counting positions whose close is stamped ≥ S → `CAP`;
  4. Σ `OrderCalcMargin` of the open robot positions + this one > B(S) → `MARGIN`.

  A skip never touches the paper.
- **`InpRestartAfter` = T**: everything before T becomes one payment of B(T), and the stop latch restarts.

## 6. Protections (CR_Guards)

- **Plan stop** (growth.py:245-252; F1S/F2S :75-76). After each booked robot close, if P ≥ `InpStopArmPaid` and B ≤ ref × (1 − `InpStopFallPct`/100): close all and never enter again (`STOP`). It is derived from the history, so it survives restarts.
- **Disaster guard**, a constant. If equity ≤ 50 % of ref, checked at each timer call: same effect (`GUARD`). It is not in the plan; F1S never reaches it on paper or at half edge (sixth review).
- **Daily lock** (`InpDailyLockStakes` = X). If the server day's robot money (closed + floating) ≤ −X × rate(max(B_d, P_d))% × B_d: close all until the next server day. Off by default: the plan has no lock, and the hands' 6 % lock fires early in most F2S paths (sixth review).
- **Friday close** (`InpFridayCloseHHMM`): close all and block entries from that server time until Monday. Off by default: it cuts donch's PF from 1.53 to 1.40 and orb's from 1.34 to 1.19 (map `mains` 12).
- **Clock.** Every hour, if |TimeTradeServer − TimeGMT − the rule's offset| > 120 s: no entries, `CLOCK`.
- **Kept from the hands 1.11:** Resolve, RiskMoney, ToTick (as GridStop), the open checks, CloseAll, the hedging and trading checks, RobotDeals, Capital's settle and reference rules, Notify's limits, Watch's rhythm.
- **Dropped:** the file bridge, the heartbeat, the TTL globals, InpMaxRiskPct, InpResetLocks, the 6 % lock, and the −50 % equity kill (now the guard above).

## 7. Harness and acceptance (check/)

- **Data.** `export_frames.py` reads `r2.load(sym, end="2022-01-01")` and writes binary broker bars: server time; bid rounded to 2 digits, until the Mac says otherwise; spread = round((ao − bo)/point). It also writes the lab frame rebuilt from those numbers (ask = bid + spread × point, rounded half away from zero). References always use the rebuilt frame; in the spike, rounding changed no trade.
- **Engine.** The dist file goes through `to_cpp.py`. `mock_replay.h` serves N symbols: first ticks at T + 0 s, a timer call at T + 2.5 s.
  - Fast mode checks stops at bar end with the lab rule. Tick mode adds O→L→H→C or O→H→L→C ticks.
  - Hedging broker with deals and deposits; margin = lots × units × price × 0.89 / leverage; tick value = tick size × units × 0.89.
  - Restarts, and the faults of `mock_faults.h`.
- **References.** `ref_lab.py` runs, per sleeve, the `recalc.sleeves()` entry: `make_orders` (every signal) and `r2.run(sym, mk, params, "fp", True, m1)` (recalc.py:98), plus `growth.run_one`. `compare.py` matches journal lines against them.
- **Tolerances.**
  - Equal: times, sides, reasons, counts, lots, skips, and prices taken from bars (levels, fills, time exits).
  - 1e-12 relative: values built from rolling, Wilder or score computations, and the stops built on them.
  - Razor cases: decisions within 1e-9 of a threshold are listed; the sleeve is compared again once both chains are flat.
  - Classified, never silent: lab exits moved before an unforeseen hole of more than 30 min (`HOLE_EXIT`), and GFP days the lab dropped for a data hole.
  - Trades still open at the frame end are excluded.
- **Tests.**
  - **T1 clock.** Hourly 2012-2035 and each DST switch ± 3 h vs zoneinfo and `pont.server_to_utc`; NYSE 2012-2035 vs `us_holidays`; `AddTradingDays` on all in-sample 4h closes; server day and week vs `stake.prepare`.
  - **T2 data.** The store equals the rebuilt frame bit for bit; the mask drops nothing in sample; each aggregate equals its lab function; barrier and revision behave as specified in the mock.
  - **T3 paper.** At least 10,000 random orders per market (every etype including OCO, wrong-side stops, trail, be, targets, gaps) vs `gl.simulate`, exact; plus the scenarios of map `simulateur` §6.
  - **T4 and T5.** Decisions (every signal) and trades, per rule, over the whole in-sample period.
  - **T6 restarts.** 100 restarts per sleeve, each from the §2.2 depth only, plus 10 outages of 1-6 h. Later paper trades are unchanged, and positions are adopted or closed as §4.6 says.
  - **T7 account.** Run the EA over 2018-02..2021-12, for F1S and F2S, with 1,000 EUR at the start and at each server month. Feed `growth.engine` the EA's own trades (stamp, sizing risk and fill, real money) and the same payments. It must give the same take or skip and reason, the same lots, m and stop week, and weekly balances within ± 0.01 EUR.
  - **T8 whole EA**, in tick mode. With clean ticks, real = paper (gold one bar late). Then one scripted world per failure:
    - refused stop or modification;
    - requote and timeout, with no duplicate;
    - rewritten comments; magic-0 deals;
    - late bar; short history; restart mid-trade;
    - clock off by 1 h;
    - mid-week deposit and withdrawal (w unchanged);
    - stop and guard; lock and Friday close when enabled;
    - `InpTrade` false; a real account off the VPS; a second instance.
  - **T9 hands port.** test_mains.py sections 2-4, 7, 9 and 11, ported to CR_Broker and CR_Ledger. Sections 1, 5, 6, 8 and the TTL cases retire.
  - **T10 self-test.** `gen_golden.py` vectors (60 clock instants, 40 NYSE dates, 20 AddTradingDays, 30 F1 scores, a Wilder and an SMA series), checked at `OnInit`. A mismatch blocks trading.
  - **Speed.** A full in-sample run of the ten sleeves in under 3 min; the startup replay in under 5 s (g++).

## 8. Build steps

| Step | Files | Done when | Parallel |
|---|---|---|---|
| S0 contract | `ClaudeRobot.mq5`, `CR_Types`, `CR_Registry` (all rows and cases), `CR_Journal`, `CR_Main` skeleton, stubs of every other `src/` file, `amalgam.py`, `to_cpp.py`, `mql5_shim.h`, `mock_replay.h`, `mock_faults.h` stub, `export_frames.py`, `ref_lab.py`, `compare.py`, `run_tests.py` | dist builds and compiles without warnings; an empty EA replays 2021 on four symbols and its journal parses; `ref_lab.py` reproduces `results/r2/recalc/trades` (entries before 2022, exits inside the frame) | first |
| A clock | `CR_Clock.mqh`, `test_clock.cpp` | T1 | B–J |
| B data | `CR_Math.mqh`, `CR_Bars.mqh`, `test_bars.cpp` | T2; primitives vs pandas within 1e-12 | A, C–J |
| C paper | `CR_Paper.mqh`, `test_paper.cpp` | T3 | A, B, D–J |
| D us100 | `CR_Rule_IdxUS.mqh`, tests | T4, T5 for N30, OC4; 30 restarts each | A–C, E–J |
| E crypto | `CR_Rule_Brk72.mqh`, `CR_Rule_F1.mqh`, `gen_f1_model.py` | T4, T5 for BKB, BKE, F1B, F1E; the generator refuses a wrong sha256 | A–D, F–J |
| F lead-lag | `CR_Rule_NqBtc.mqh`, tests | T4, T5 for NQB | A–E, G–J |
| G gold clock | `CR_Rule_GoldFri.mqh`, `CR_Rule_Orb.mqh`, tests | T4, T5 for GFP, ORX | A–F, H–J |
| H gold trend | `CR_Rule_Donch.mqh`, tests | T4, T5 for D4H | A–G, I, J |
| I account | `CR_Ledger.mqh`, `CR_Sizing.mqh`, `test_account.cpp` | T7; unit tests of the risk table, m, lots, minimum lot, caps, margin, strict stamps, stop latch, `InpPaidIn`, `InpRestartAfter`, history gap | A–H, J |
| J execution | `CR_Broker.mqh`, `CR_Follower.mqh`, `CR_Guards.mqh`, `mock_faults.h` | T8, T9 | A–I |
| K integration | `CR_Main.mqh` final, `gen_golden.py` | T6 (100 restarts per sleeve), T10, a full run under sanitizers, speed | after A–J |

Steps D-H code against the S0 stubs and the lab references; their T5 passes once A-C have landed.

## 9. Accepted deviations from the lab

1. D4H, ORX and GFP entries are filled for real at the open of the bar after the paper fill; the paper and the sizing keep the lab fill (§4.1).
2. A lab exit moved before an unforeseen hole of more than 30 min happens live after the hole (spike: 13 of 645 BTC trades). Known closures are handled like the lab.
3. GFP's early-close filter is a calendar plus the broker session, not after the fact.
4. Real stops trigger on ticks, paper stops on bars with one spread each; the paper decides.
5. The ask is bid + the bar's spread field, on FP's feed. Only "EA = lab code on the broker's bars" is provable. nq_btc keeps 58 % of its trades under 1 bp of noise (map `leadlag` 21); 3 % of donch touches lie within 0.5 bp (map `or-tendance` 25).
6. Live EUR tick values and `OrderCalcMargin` replace 0.89 and fp_costs.json; for absolute stops, the expected fill comes from the quote.
7. A late gold entry is sized one minute after its stamp. This differs from byte order only if caps or margin bind.
8. Rolling statistics are incremental, within 1e-12 of the lab. Razor decisions may differ.
9. After a restart, a paper entry is joined only within 5 min of its stamp.
10. The disaster guard is not in the plan.
11. NYSE special closures after 2025-01-09 come only through `InpExtraClosures`.

## 10. Only the user's Mac can settle (default meanwhile)

1. The MetaEditor compile (0 errors, 0 warnings) and the self-test on the real compiler. Default: none; this blocks trading.
2. A Strategy Tester run of `ClaudeRobot_debug.mq5` on FP's 2021 history (real ticks, else 1-minute OHLC), with `InpTrade` false. The harness replays the dumped bars and must reproduce the journal line for line. Default: none; this blocks `InpTrade` true.
3. What `MqlRates.spread` holds at FP (a moderator says the bar's minimum, forum 266519), checked against ReleveFP tick files. Default: ask = bid + spread × point.
4. Whether the server clock is NY + 7 h across a DST switch. Default: the rule; entries are blocked on a mismatch.
5. FP sessions: US100 16:15-18:00, gold 17:00-18:00, crypto weekends, the Friday close, holidays. Default: the lab mask and closures, shortened by the broker sessions.
6. Symbol specifications: digits and tick size, contract size, US100 minimum lot, EUR tick values, stops and freeze levels, filling, margin, hedging. Default: read live; the harness uses fp_costs.json and 0.89.
7. Whether deposits appear as `DEAL_TYPE_BALANCE` in `DEAL_PROFIT`, with the full history. Default: the history; a gap is booked as an opening payment; `InpPaidIn` overrides.
8. Broker stop deals: their magic, reason and whether comments are kept. Default: attribution by position id, matching by magic and time.
9. On the VPS: history depth, replay time, Max bars migrated, `TERMINAL_VPS` true. Default: NOT_READY until the depth is there.
10. First-tick timing, slippage at minute opens, how often `LATEBAR` fires. Default: a 2 s grace, and a rebuild on each revision.
11. Weekend crypto quotes, before enabling ids 11-12. Default: disabled.
12. Two shadow weeks with `InpTrade` false (VPS and Mac journals vs a harness replay of the same bars), then `InpTrade` true.
